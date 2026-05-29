import pickle
import pandas as pd
import numpy as np
from pymongo import MongoClient
from pathlib import Path



# config
MODEL_PATH = Path("model.pkl")
CSV_PATH = Path("data/processed/grid_wind.csv")


MONGO_URI = "INSERT URI HERE"
DB_NAME = "wind_db"
COLLECTION_NAME = "predictions"


# load ML model
with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

print("Model loaded")

# load gid map of netherlands
df = pd.read_csv(CSV_PATH)

print(f"Loaded {len(df)} rows")


# Convert direction to radians
df["dir_rad"] = np.deg2rad(df["wind_direction_100m"])

df["dir_sin"] = np.sin(df["dir_rad"])
df["dir_cos"] = np.cos(df["dir_rad"])

# wind_power_density
df["wind_power_density"] = df["wind_speed_100m_ms"] ** 3


X = df[[
    "wind_speed_100m_ms",
    "dir_sin",
    "dir_cos",
    "wind_power_density"
]].copy()

# rename column to match training exactly
X = X.rename(columns={
    "wind_speed_100m_ms": "wind_speed_ms"
})

# run prediction model
predictions = model.predict(X)

df["predicted_power"] = predictions

print("Predictions generated")


documents = []

for _, row in df.iterrows():
    doc = {
        "location": {
            "type": "Point",
            "coordinates": [float(row["lon"]), float(row["lat"])]
        },
        "expectedPowerOutput": float(row["predicted_power"])
    }
    documents.append(doc)


client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# Insert
if documents:
    collection.insert_many(documents)