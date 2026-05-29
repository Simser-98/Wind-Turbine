import io
import os

import contextily
import matplotlib.pyplot as plt
import numpy as np
import pymongo
import pyproj
from fastapi import FastAPI
from fastapi.responses import StreamingResponse

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

    documents = [
        {
            "_id": "doc_1",
            "location": {"type": "Point", "coordinates": [4.746094, 52.217704]},
            "expectedPowerOutput": 19.63,
        },
        {
            "_id": "doc_2",
            "location": {"type": "Point", "coordinates": [4.367875, 52.001839]},
            "expectedPowerOutput": 97.47,
        },
        {
            "_id": "doc_3",
            "location": {"type": "Point", "coordinates": [4.825745, 52.761230]},
            "expectedPowerOutput": 30.1,
        },
        {
            "_id": "doc_4",
            "location": {"type": "Point", "coordinates": [6.578064, 53.214257]},
            "expectedPowerOutput": 1.44,
        },
        {
            "_id": "doc_5",
            "location": {"type": "Point", "coordinates": [6.163330, 52.226117]},
            "expectedPowerOutput": 87.28,
        },
        {
            "_id": "doc_6",
            "location": {"type": "Point", "coordinates": [5.313860, 51.487193]},
            "expectedPowerOutput": 81.56,
        },
        {
            "_id": "doc_7",
            "location": {"type": "Point", "coordinates": [5.822754, 51.284253]},
            "expectedPowerOutput": 12.13,
        },
        {
            "_id": "doc_8",
            "location": {"type": "Point", "coordinates": [5.877686, 50.878777]},
            "expectedPowerOutput": 48.3,
        },
        {
            "_id": "doc_9",
            "location": {"type": "Point", "coordinates": [5.350342, 52.422523]},
            "expectedPowerOutput": 68.58,
        },
        {
            "_id": "doc_10",
            "location": {"type": "Point", "coordinates": [5.581055, 53.179704]},
            "expectedPowerOutput": 62.92,
        },
        {
            "_id": "doc_11",
            "location": {"type": "Point", "coordinates": [4.443970, 51.589016]},
            "expectedPowerOutput": 55.06,
        },
        {
            "_id": "doc_12",
            "location": {"type": "Point", "coordinates": [3.817749, 51.721924]},
            "expectedPowerOutput": 15.13,
        },
        {
            "_id": "doc_13",
            "location": {"type": "Point", "coordinates": [3.641968, 51.558290]},
            "expectedPowerOutput": 94.21,
        },
        {
            "_id": "doc_14",
            "location": {"type": "Point", "coordinates": [3.573687, 51.478496]},
            "expectedPowerOutput": 42.84,
        },
        {
            "_id": "doc_15",
            "location": {"type": "Point", "coordinates": [3.903580, 51.269648]},
            "expectedPowerOutput": 74.65,
        },
        {
            "_id": "doc_16",
            "location": {"type": "Point", "coordinates": [5.595629, 51.716298]},
            "expectedPowerOutput": 35.96,
        },
        {
            "_id": "doc_17",
            "location": {"type": "Point", "coordinates": [5.866699, 52.331982]},
            "expectedPowerOutput": 88.56,
        },
        {
            "_id": "doc_18",
            "location": {"type": "Point", "coordinates": [6.978001, 53.124712]},
            "expectedPowerOutput": 91.09,
        },
        {
            "_id": "doc_19",
            "location": {"type": "Point", "coordinates": [6.652222, 52.321911]},
            "expectedPowerOutput": 68.61,
        },
        {
            "_id": "doc_20",
            "location": {"type": "Point", "coordinates": [4.784546, 53.077528]},
            "expectedPowerOutput": 5.23,
        },
        {
            "_id": "doc_21",
            "location": {"type": "Point", "coordinates": [6.778564, 53.452896]},
            "expectedPowerOutput": 38.12,
        },
        {
            "_id": "doc_22",
            "location": {"type": "Point", "coordinates": [6.696167, 51.978959]},
            "expectedPowerOutput": 10.64,
        },
        {
            "_id": "doc_23",
            "location": {"type": "Point", "coordinates": [7.014771, 52.244620]},
            "expectedPowerOutput": 20.56,
        },
        {
            "_id": "doc_24",
            "location": {"type": "Point", "coordinates": [5.336716, 51.818473]},
            "expectedPowerOutput": 39.07,
        },
        {
            "_id": "doc_25",
            "location": {"type": "Point", "coordinates": [5.314636, 51.920556]},
            "expectedPowerOutput": 81.27,
        },
    ]

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
