import io
import os
from contextlib import asynccontextmanager
from typing import cast

import contextily
import dotenv
import numpy as np
import scipy.interpolate
from fastapi import FastAPI, Response
from geojson_pydantic import Point
from geojson_pydantic.types import Position
from matplotlib import pyplot as plt
from pydantic import BaseModel, Field
from pymongo import AsyncMongoClient

FIGURE_SIZE: tuple[int, int] = (12, 10)
FIGURE_DPI: int = 150

dotenv.load_dotenv()
MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB = os.environ["MONGO_DB"]
MONGO_COLLECTION = os.environ["MONGO_COLLECTION"]


class Mongo:
    """
    Wrapper class for the MongoDB client.
    """

    client: AsyncMongoClient


mongo = Mongo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Controls the lifespan of the MongoDB client based on the state of the API.
    """
    mongo.client = AsyncMongoClient(MONGO_URI)
    yield

    await mongo.client.close()


app = FastAPI(lifespan=lifespan)


class Prediction(BaseModel):
    """
    Prediction of wind turbine power generation at specific location.
    """

    location: Point
    expected_power_output: float = Field(alias="expectedPowerOutput")


class DiagramResponse(Response):
    """
    Diagram API response in SVG format.
    """

    media_type = "image/svg+xml"


async def get_nearest_prediction(location: Point) -> Prediction:
    """
    Query MongoDB for the nearest prediction to a given geographic location.

    Args:
        location: GeoJSON Point specifying target coordinates (lng, lat).

    Returns:
        Nearest wind turbine power prediction record in the collection.
    """
    result = await mongo.client[MONGO_DB][MONGO_COLLECTION].find_one(
        {"location": {"$near": {"$geometry": location.model_dump()}}}
    )
    return Prediction.model_validate(result)


async def get_all_predictions() -> list[Prediction]:
    """
    Retrieve all prediction documents from the MongoDB collection.

    Returns:
        All wind turbine power prediction records in the collection.
    """
    results = await mongo.client[MONGO_DB][MONGO_COLLECTION].find().to_list()
    return [Prediction.model_validate(result) for result in results]


@app.get("/health")
async def health():
    """
    Liveness health endpoint.
    """
    return {"status": "ok"}


@app.get("/nearest")
async def nearest_prediction(lng: float, lat: float) -> Prediction:
    """
    Return the closest prediction in the dataset to the given location.
    """
    return await get_nearest_prediction(
        Point(type="Point", coordinates=cast(Position, [lng, lat]))
    )


@app.get("/prediction-interpolated")
async def interpolated_prediction(lng: float, lat: float) -> Prediction: ...


@app.get("/map", responses={200: {"content": {"image/svg+xml": {}}}})
async def map() -> DiagramResponse:
    """
    Generate and return a heatmap SVG of predicted wind turbine power outputs.

    Fetches all predictions from the database, interpolates them onto a regular
    grid using cubic interpolation, and overlays the heatmap on a geographic basemap.
    """
    predictions = await get_all_predictions()

    lngs, lats, expected_power_outputs = np.array(
        [
            (*prediction.location.coordinates, prediction.expected_power_output)
            for prediction in predictions
        ]
    ).T

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
