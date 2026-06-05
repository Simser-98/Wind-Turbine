import io
import os
from contextlib import asynccontextmanager

import contextily
import dotenv
import numpy as np
import scipy.interpolate
from fastapi import FastAPI, Response
from geojson_pydantic import Point
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
    client: AsyncMongoClient


mongo = Mongo()


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo.client = AsyncMongoClient(MONGO_URI)

    yield

    await mongo.client.close()


app = FastAPI(lifespan=lifespan)


class Prediction(BaseModel):
    location: Point
    expected_power_output: float = Field(alias="expectedPowerOutput")


class DiagramResponse(Response):
    media_type = "image/svg+xml"


async def get_nearest_prediction(location: Point) -> Prediction:
    result = await mongo.client[MONGO_DB][MONGO_COLLECTION].find_one(
        {"location": {"$near": {"$geometry": location.model_dump()}}}
    )
    return Prediction.model_validate(result)


async def get_all_predictions() -> list[Prediction]:
    results = await mongo.client[MONGO_DB][MONGO_COLLECTION].find().to_list()
    return [Prediction.model_validate(result) for result in results]


@app.get("/nearest")
async def nearest_prediction(location: Point) -> Prediction:
    return await get_nearest_prediction(location)


@app.get("/prediction-interpolated")
async def interpolated_prediction(location: Point) -> Prediction: ...


@app.get("/map")
async def map() -> DiagramResponse:
    predictions = await get_all_predictions()

    coords = np.array([prediction.location.coordinates for prediction in predictions])
    lngs = coords[:, 0]
    lats = coords[:, 1]
    expected_power_outputs = np.array(
        [prediction.expected_power_output for prediction in predictions]
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
