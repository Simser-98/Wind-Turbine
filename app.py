import io
import os
from contextlib import asynccontextmanager
from typing import Annotated

import aiocache
import contextily
import numpy as np
import scipy.interpolate
from fastapi import FastAPI, Query, Response
from geojson_pydantic import Point, Polygon
from geojson_pydantic.types import Position2D
from matplotlib import pyplot as plt
from pydantic import BaseModel, Field
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

Longitude = Annotated[float, Query(ge=-90, le=90)]
Latitude = Annotated[float, Query(ge=-180, le=180)]


class Prediction(BaseModel):
    location: Point
    expected_power_output: float = Field(alias="expectedPowerOutput")


class DiagramResponse(Response):
    media_type = "image/svg+xml"


@aiocache.cached(120)
async def get_nearest_prediction(location: Point) -> Prediction:
    result = await mongo.client[MONGO_DB][MONGO_COLLECTION].find_one(
        {"location": {"$near": {"$geometry": location.model_dump()}}}
    )
    return Prediction.model_validate(result)


@aiocache.cached(120)
async def get_all_predictions() -> list[Prediction]:
    results = await mongo.client[MONGO_DB][MONGO_COLLECTION].find().to_list()
    return [Prediction.model_validate(result) for result in results]


@app.get("/live")
async def live() -> None:
    return


@app.get("/map", response_class=DiagramResponse)
async def map_get() -> DiagramResponse:
    predictions = await get_all_predictions()

    lngs, lats, expected_power_outputs = np.transpose(
        [
            (*prediction.location.coordinates, prediction.expected_power_output)
            for prediction in predictions
        ]
    )

    figure, axes = plt.subplots(
        figsize=FIGURE_SIZE, dpi=FIGURE_DPI, layout="compressed"
    )
    axes.set_axis_off()

    grid_x, grid_y = np.meshgrid(
        np.linspace(lngs.min(), lngs.max()),
        np.linspace(lats.min(), lats.max()),
    )
    grid_z = scipy.interpolate.griddata(
        (lngs, lats),
        expected_power_outputs,
        (grid_x, grid_y),
        method="cubic",
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


@app.post("/map", response_class=DiagramResponse)
async def map_post(polygon: Polygon) -> DiagramResponse: ...


@app.get("/closest")
async def closest(lng: Longitude, lat: Latitude) -> Prediction:
    return await get_nearest_prediction(
        Point(type="Point", coordinates=Position2D(longitude=lng, latitude=lat))
    )


@app.get("/interpolated")
async def interpolated(lng: Longitude, lat: Latitude) -> Prediction: ...
