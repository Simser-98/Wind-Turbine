import io
import os
from typing import Literal
import dotenv

import contextily
import matplotlib.pyplot as plt
import numpy as np
import pymongo
import pyproj
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

FIGURE_SIZE: tuple[int, int] = (12, 10)
FIGURE_DPI: int = 150

dotenv.load_dotenv()
MONGO_URI = os.environ["MONGO_URI"]
MONGO_DB = os.environ["MONGO_DB"]
MONGO_COLLECTION = os.environ["MONGO_COLLECTION"]

app = FastAPI()


class Location(BaseModel):
    type: Literal["Point"]
    coordinates: tuple[float, float]


class Document(BaseModel):
    location: Location
    expected_power_output: float = Field(alias="expectedPowerOutput")


@app.get("/")
async def root() -> StreamingResponse:
    mongo_client = pymongo.MongoClient(MONGO_URI)
    mongo_db = mongo_client[MONGO_DB]
    mongo_collection = mongo_db[MONGO_COLLECTION]
    documents = list(mongo_collection.find())
    mongo_client.close()

    parsed_docs = [Document.model_validate(document) for document in documents]

    lngs = np.array([document.location.coordinates[0] for document in parsed_docs])
    lats = np.array([document.location.coordinates[1] for document in parsed_docs])
    power_output = np.array(
        [document.expected_power_output for document in parsed_docs]
    )

    projection_transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", "EPSG:3857", always_xy=True
    )
    x_coordinates, y_coordinates = projection_transformer.transform(lngs, lats)

    figure, axes = plt.subplots(
        figsize=FIGURE_SIZE, dpi=FIGURE_DPI, layout="compressed"
    )
    axes.set_axis_off()

    scatter = axes.scatter(x_coordinates, y_coordinates, c=power_output)

    contextily.add_basemap(axes)

    color_bar = figure.colorbar(scatter)
    color_bar.set_label("Power Output [KW]")

    output_buffer = io.BytesIO()
    figure.savefig(output_buffer, format="svg")
    plt.close(figure)

    output_buffer.seek(0)
    return StreamingResponse(output_buffer, media_type="image/svg+xml")
