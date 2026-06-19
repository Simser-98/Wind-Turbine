import io
import os
from contextlib import asynccontextmanager
from typing import Annotated, Literal, Optional

import aiocache
import contextily
import numpy as np
import scipy.interpolate
from fastapi import APIRouter, FastAPI, Query, Response
from geojson_pydantic import Feature, FeatureCollection, Point, Polygon
from geojson_pydantic.types import Position2D
from matplotlib import pyplot as plt
from numpy import dtype, float64, ndarray
from pydantic import BaseModel, BeforeValidator, Field
from pymongo import AsyncMongoClient

FIGURE_SIZE: tuple[int, int] = (12, 10)
FIGURE_DPI: int = 150

try:
    import dotenv

    dotenv.load_dotenv()
except ImportError:
    pass
MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB = os.environ["MONGO_DB"]
MONGO_COLLECTION = os.environ["MONGO_COLLECTION"]


class Mongo:
    client: AsyncMongoClient


mongo = Mongo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.client = AsyncMongoClient(MONGO_URI)
    await mongo.client[MONGO_DB][MONGO_COLLECTION].create_index(
        {"location": "2dsphere"}
    )
    yield

    await mongo.client.close()


app = FastAPI(lifespan=lifespan)
router = APIRouter(prefix="/api/v1")

Longitude = Annotated[float, Query(ge=-180, le=180)]
Latitude = Annotated[float, Query(ge=-90, le=90)]


class Prediction(BaseModel):
    id: Annotated[str, BeforeValidator(str)] = Field(validation_alias="_id")
    location: Point
    expected_power_output: float = Field(serialization_alias="expectedPowerOutput")
    power_category: Literal["low"] | Literal["medium"] | Literal["high"] = Field(
        serialization_alias="powerCategory"
    )


class DiagramResponse(Response):
    media_type = "image/svg+xml"


@aiocache.cached(120)
async def get_nearest_prediction(location: Point) -> Prediction:
    result = await mongo.client[MONGO_DB][MONGO_COLLECTION].find_one(
        {"location": {"$near": {"$geometry": location.model_dump()}}}
    )
    return Prediction.model_validate(result)


@aiocache.cached(120)
async def get_nearest_predictions(
    location: Point, count: Optional[int] = None
) -> list[Prediction]:
    query = mongo.client[MONGO_DB][MONGO_COLLECTION].find(
        {"location": {"$near": {"$geometry": location.model_dump()}}}
    )

    if count is not None:
        query.limit(count)

    results = await query.to_list()

    return [Prediction.model_validate(result) for result in results]


@aiocache.cached(120)
async def get_all_predictions() -> list[Prediction]:
    results = await mongo.client[MONGO_DB][MONGO_COLLECTION].find().to_list()
    return [Prediction.model_validate(result) for result in results]


def generate_heatmap(predictions: list[Prediction]) -> DiagramResponse:
    lngs: ndarray[tuple[int], dtype[float64]]
    lats: ndarray[tuple[int], dtype[float64]]
    expected_power_outputs: ndarray[tuple[int], dtype[float64]]
    lngs, lats, expected_power_outputs = np.transpose(
        [(*p.location.coordinates, p.expected_power_output) for p in predictions]
    )

    figure, axes = plt.subplots(
        figsize=FIGURE_SIZE, dpi=FIGURE_DPI, layout="compressed"
    )
    axes.set_axis_off()

    grid_x: ndarray[tuple[int], dtype[float64]]
    grid_y: ndarray[tuple[int], dtype[float64]]
    grid_z: ndarray[tuple[int, int], dtype[float64]]
    grid_x, grid_y = np.meshgrid(
        np.linspace(lngs.min(), lngs.max()),
        np.linspace(lats.min(), lats.max()),
    )
    grid_z = scipy.interpolate.griddata(
        (lngs, lats), expected_power_outputs, (grid_x, grid_y)
    )

    heatmap = axes.imshow(
        grid_z,
        aspect="auto",
        alpha=0.6,
        origin="lower",
        extent=(lngs.min(), lngs.max(), lats.min(), lats.max()),
        zorder=1,
    )

    contextily.add_basemap(axes, crs="EPSG:4326")

    color_bar = figure.colorbar(heatmap)
    color_bar.set_label("Predicted Power Output [KW]")

    output_buffer = io.BytesIO()
    figure.savefig(output_buffer, format="svg")
    plt.close(figure)

    output_buffer.seek(0)
    return DiagramResponse(output_buffer.getbuffer())


@router.get("/live")
async def live() -> None:
    return


@router.get("/map", response_class=DiagramResponse)
async def map_get() -> DiagramResponse:
    predictions = await get_all_predictions()
    return generate_heatmap(predictions)


@router.post("/map", response_class=DiagramResponse)
async def map_post(polygon: Polygon) -> DiagramResponse:
    results = (
        await mongo.client[MONGO_DB][MONGO_COLLECTION]
        .find({"location": {"$geoWithin": {"$geometry": polygon.model_dump()}}})
        .to_list()
    )
    predictions = [Prediction.model_validate(result) for result in results]
    return generate_heatmap(predictions)


@router.get("/predictions/bbox")
async def predictions_bbox(
    west: Longitude, south: Latitude, east: Longitude, north: Latitude
) -> FeatureCollection:
    results = (
        await mongo.client[MONGO_DB][MONGO_COLLECTION]
        .find({"location": {"$geoWithin": {"$box": [[west, south], [east, north]]}}})
        .to_list()
    )
    predictions = [Prediction.model_validate(result) for result in results]
    return FeatureCollection(
        type="FeatureCollection",
        features=[
            Feature(
                type="Feature",
                id=prediction.id,
                geometry=prediction.location,
                properties={
                    "expectedPowerOutput": prediction.expected_power_output,
                    "powerCategory": prediction.power_category,
                },
            )
            for prediction in predictions
        ],
    )


@router.get("/nearest")
async def nearest(lng: Longitude, lat: Latitude) -> Prediction:
    return await get_nearest_prediction(
        Point(type="Point", coordinates=Position2D(longitude=lng, latitude=lat))
    )


@router.get("/interpolated")
async def interpolated(lng: Longitude, lat: Latitude) -> Prediction: ...


app.include_router(router)
