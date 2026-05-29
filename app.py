import io
import os

import contextily
import matplotlib.pyplot as plt
import numpy as np
import pymongo
import pyproj
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from data_setup import get_model_predictions

MONGO_URI = os.environ.get("MONGO_URI")
MONGO_DB = os.environ.get("MONGO_DB")
MONGO_COLLECTION = os.environ.get("MONGO_COLLECTION")

FIGURE_SIZE: tuple[int, int] = (12, 10)
FIGURE_DPI: int = 150

app = FastAPI()


@app.get("/")
async def root():
    # mongo_client = pymongo.MongoClient(MONGO_URI)
    # mongo_db = mongo_client[MONGO_DB]
    # mongo_collection = mongo_db[MONGO_COLLECTION]
    # documents = list(mongo_collection.find())
    # mongo_client.close()

    documents = get_model_predictions()

    lngs = np.array([document["location"]["coordinates"][0] for document in documents])
    lats = np.array([document["location"]["coordinates"][1] for document in documents])
    power_output = np.array([document["expectedPowerOutput"] for document in documents])

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
    color_bar.set_label("Power Output [MW]")

    output_buffer = io.BytesIO()
    figure.savefig(output_buffer, format="png")
    plt.close(figure)

    output_buffer.seek(0)
    return StreamingResponse(output_buffer, media_type="image/png")
