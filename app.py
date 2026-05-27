import io

import geopandas as gpd
import matplotlib.pyplot as plt
import pymongo
from fastapi import FastAPI

MONGO_URI = ""
MONGO_DB = ""
MONGO_COLLECTION = ""

app = FastAPI()


@app.get("/")
async def root():
    # mongo_client = pymongo.MongoClient(MONGO_URI)
    # mongo_db = mongo_client[MONGO_DB]
    # mongo_collection = mongo_db[MONGO_COLLECTION]
    # TODO fetch data from collection ...

    mock_data = [
        {
            "lat": 52.001611,
            "lng": 4.367306,
            "power": 1,
        },
        {
            "lat": 52.22265,
            "lng": 4.52110,
            "power": 2,
        },
        {
            "lat": 51.32582,
            "lng": 5.34205,
            "power": 3,
        },
    ]

    return {"msg": "AAAA"}
