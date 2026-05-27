import io

import contextily as ctx
import geopandas as gpd
import matplotlib.colors as mcolors
import matplotlib.pyplot as plt
import pymongo
from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from shapely.geometry import Point

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
    # mongo_client.close()

    documents = [
        {"_id": "doc_1", "lat": 51.77833, "lng": 6.78223, "power": 97.47},
        {"_id": "doc_2", "lat": 52.15591, "lng": 7.01844, "power": 30.1},
        {"_id": "doc_3", "lat": 52.31844, "lng": 6.34013, "power": 1.44},
        {"_id": "doc_4", "lat": 53.19846, "lng": 6.11939, "power": 87.28},
        {"_id": "doc_5", "lat": 51.59061, "lng": 5.04703, "power": 81.56},
        {"_id": "doc_6", "lat": 53.41198, "lng": 4.60011, "power": 12.13},
        {"_id": "doc_7", "lat": 52.71468, "lng": 4.96533, "power": 48.3},
        {"_id": "doc_8", "lat": 52.92529, "lng": 4.36435, "power": 68.58},
        {"_id": "doc_9", "lat": 50.82856, "lng": 3.40092, "power": 62.92},
        {"_id": "doc_10", "lat": 53.07924, "lng": 5.17709, "power": 55.06},
        {"_id": "doc_11", "lat": 52.92375, "lng": 6.75091, "power": 15.13},
        {"_id": "doc_12", "lat": 52.24187, "lng": 3.85807, "power": 94.21},
        {"_id": "doc_13", "lat": 52.5973, "lng": 5.77718, "power": 42.84},
        {"_id": "doc_14", "lat": 50.92295, "lng": 3.37658, "power": 74.65},
        {"_id": "doc_15", "lat": 52.84518, "lng": 5.5208, "power": 35.96},
        {"_id": "doc_16", "lat": 52.87438, "lng": 5.41689, "power": 88.56},
        {"_id": "doc_17", "lat": 51.34928, "lng": 6.1066, "power": 91.09},
        {"_id": "doc_18", "lat": 50.98701, "lng": 6.73958, "power": 68.61},
        {"_id": "doc_19", "lat": 50.9945, "lng": 5.35055, "power": 5.23},
        {"_id": "doc_20", "lat": 51.65684, "lng": 5.47742, "power": 38.12},
        {"_id": "doc_21", "lat": 51.95949, "lng": 4.73879, "power": 10.64},
        {"_id": "doc_22", "lat": 53.29293, "lng": 7.11015, "power": 20.56},
        {"_id": "doc_23", "lat": 51.55481, "lng": 5.62837, "power": 39.07},
        {"_id": "doc_24", "lat": 53.31487, "lng": 6.0716, "power": 81.27},
        {"_id": "doc_25", "lat": 52.01937, "lng": 4.81022, "power": 19.63},
        {"_id": "doc_26", "lat": 53.49723, "lng": 6.60531, "power": 1.8},
        {"_id": "doc_27", "lat": 50.91283, "lng": 5.82921, "power": 16.89},
        {"_id": "doc_28", "lat": 51.16893, "lng": 4.6408, "power": 13.66},
        {"_id": "doc_29", "lat": 52.08349, "lng": 4.71282, "power": 32.24},
        {"_id": "doc_30", "lat": 53.18169, "lng": 4.07988, "power": 32.24},
        {"_id": "doc_31", "lat": 51.08662, "lng": 5.24695, "power": 50.75},
        {"_id": "doc_32", "lat": 51.11415, "lng": 4.33534, "power": 88.65},
        {"_id": "doc_33", "lat": 53.01453, "lng": 3.59027, "power": 59.08},
        {"_id": "doc_34", "lat": 52.6881, "lng": 6.00437, "power": 9.57},
        {"_id": "doc_35", "lat": 52.91991, "lng": 3.45623, "power": 34.17},
        {"_id": "doc_36", "lat": 50.91805, "lng": 4.09376, "power": 48.16},
        {"_id": "doc_37", "lat": 52.23745, "lng": 6.7397, "power": 30.06},
        {"_id": "doc_38", "lat": 51.78103, "lng": 5.76585, "power": 68.52},
        {"_id": "doc_39", "lat": 53.01309, "lng": 3.5101, "power": 71.24},
        {"_id": "doc_40", "lat": 51.18751, "lng": 3.40277, "power": 86.73},
        {"_id": "doc_41", "lat": 52.00382, "lng": 5.22706, "power": 52.08},
        {"_id": "doc_42", "lat": 53.3948, "lng": 3.46064, "power": 55.31},
        {"_id": "doc_43", "lat": 51.28702, "lng": 5.57462, "power": 73.81},
        {"_id": "doc_44", "lat": 53.13047, "lng": 4.01422, "power": 59.16},
        {"_id": "doc_45", "lat": 52.83425, "lng": 6.72828, "power": 52.6},
        {"_id": "doc_46", "lat": 53.23419, "lng": 3.88252, "power": 5.62},
        {"_id": "doc_47", "lat": 50.86908, "lng": 5.06439, "power": 32.09},
        {"_id": "doc_48", "lat": 51.63242, "lng": 5.19605, "power": 92.68},
        {"_id": "doc_49", "lat": 50.98623, "lng": 7.18872, "power": 74.25},
        {"_id": "doc_50", "lat": 52.59625, "lng": 5.61758, "power": 4.68},
    ]

    gdf = gpd.GeoDataFrame(
        documents,
        geometry=[Point(d["lng"], d["lat"]) for d in documents],
        crs="EPSG:4326",
    ).to_crs(
        epsg=3857
    )  # Web Mercator, required by contextily

    fig, ax = plt.subplots(figsize=(6, 8))

    norm = mcolors.Normalize(vmin=gdf["power"].min(), vmax=gdf["power"].max())
    cmap = plt.cm.RdYlGn

    gdf.plot(
        ax=ax,
        c=gdf["power"],
        cmap=cmap,
        norm=norm,
        markersize=30,
        alpha=0.85,
        edgecolor="white",
        linewidth=0.3,
        zorder=5,
    )

    ctx.add_basemap(ax, source=ctx.providers.CartoDB.Positron, zoom=7)

    ax.set_axis_off()
    plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap=cmap),
        ax=ax,
        orientation="vertical",
        pad=0.02,
        fraction=0.03,
        label="Power",
    )
    ax.set_title("Power Map — Netherlands", fontsize=13, fontweight="bold", pad=10)
    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return StreamingResponse(buf, media_type="image/png")
