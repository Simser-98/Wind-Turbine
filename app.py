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

app = FastAPI()


@app.get("/")
async def root():
    # mongo_client = pymongo.MongoClient(MONGO_URI)
    # mongo_db = mongo_client[MONGO_DB]
    # mongo_collection = mongo_db[MONGO_COLLECTION]
    # TODO fetch data from collection ...
    # mongo_client.close()

    documents = [
        {"_id": "doc_2", "lng": 4.367875, "lat": 52.001839, "power": 97.47},
        {"_id": "doc_3", "lng": 4.825745, "lat": 52.761230, "power": 30.1},
        {"_id": "doc_4", "lng": 6.578064, "lat": 53.214257, "power": 1.44},
        {"_id": "doc_5", "lng": 6.163330, "lat": 52.226117, "power": 87.28},
        {"_id": "doc_6", "lng": 5.313860, "lat": 51.487193, "power": 81.56},
        {"_id": "doc_7", "lng": 5.822754, "lat": 51.284253, "power": 12.13},
        {"_id": "doc_8", "lng": 5.877686, "lat": 50.878777, "power": 48.3},
        {"_id": "doc_9", "lng": 5.350342, "lat": 52.422523, "power": 68.58},
        {"_id": "doc_10", "lng": 5.581055, "lat": 53.179704, "power": 62.92},
        {"_id": "doc_11", "lng": 4.443970, "lat": 51.589016, "power": 55.06},
        {"_id": "doc_12", "lng": 3.817749, "lat": 51.721924, "power": 15.13},
        {"_id": "doc_13", "lng": 3.641968, "lat": 51.558290, "power": 94.21},
        {"_id": "doc_14", "lng": 3.573687, "lat": 51.478496, "power": 42.84},
        {"_id": "doc_15", "lng": 3.903580, "lat": 51.269648, "power": 74.65},
        {"_id": "doc_16", "lng": 5.595629, "lat": 51.716298, "power": 35.96},
        {"_id": "doc_17", "lng": 5.866699, "lat": 52.331982, "power": 88.56},
        {"_id": "doc_18", "lng": 6.978001, "lat": 53.124712, "power": 91.09},
        {"_id": "doc_19", "lng": 6.652222, "lat": 52.321911, "power": 68.61},
        {"_id": "doc_20", "lng": 4.784546, "lat": 53.077528, "power": 5.23},
        {"_id": "doc_21", "lng": 6.778564, "lat": 53.452896, "power": 38.12},
        {"_id": "doc_22", "lng": 6.696167, "lat": 51.978959, "power": 10.64},
        {"_id": "doc_23", "lng": 7.014771, "lat": 52.244620, "power": 20.56},
        {"_id": "doc_24", "lng": 5.336716, "lat": 51.818473, "power": 39.07},
        {"_id": "doc_25", "lng": 5.314636, "lat": 51.920556, "power": 81.27},
        {"_id": "doc_26", "lng": 4.746094, "lat": 52.217704, "power": 19.63},
    ]

    lngs = np.array([document["lng"] for document in documents])
    lats = np.array([document["lat"] for document in documents])
    powers = np.array([document["power"] for document in documents])

    projection_transformer = pyproj.Transformer.from_crs(
        "EPSG:4326", "EPSG:3857", always_xy=True
    )
    x_coordinates, y_coordinates = projection_transformer.transform(lngs, lats)

    figure, axes = plt.subplots(figsize=(12, 10), dpi=150)
    axes.set_axis_off()

    scatter = axes.scatter(x_coordinates, y_coordinates, c=powers)

    contextily.add_basemap(axes)

    figure.colorbar(scatter, ax=axes)

    output_buffer = io.BytesIO()
    figure.savefig(output_buffer, format="png", bbox_inches="tight", pad_inches=0)
    plt.close(figure)

    output_buffer.seek(0)
    return StreamingResponse(output_buffer, media_type="image/png")
