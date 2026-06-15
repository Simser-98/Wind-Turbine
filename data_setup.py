import pickle
import pandas as pd
import numpy as np
from pymongo import MongoClient
from pathlib import Path

# config
MODEL_PATH = Path("data/processed/model.pkl")
CSV_PATH = Path("grid_wind.csv")

MONGO_URI = "INSERT URI HERE"
DB_NAME = "wind_db"
COLLECTION_NAME = "predictions"

# load ml model
with open(MODEL_PATH, "rb") as f:
    model = pickle.load(f)

print("Model loaded")

# load csv
df = pd.read_csv(CSV_PATH)
print(f"Loaded {len(df)} rows")


df["dir_rad"] = np.deg2rad(df["wind_direction_100m"])

df["dir_sin"] = np.sin(df["dir_rad"])
df["dir_cos"] = np.cos(df["dir_rad"])

# wind power density
df["wind_power_density"] = df["wind_speed_100m_ms"] ** 3

# model input
X = df[[
    "wind_speed_100m_ms",
    "dir_sin",
    "dir_cos",
    "wind_power_density"
]].copy()

# Rename column to match model training
X = X.rename(columns={
    "wind_speed_100m_ms": "wind_speed_ms"
})

# predictions
predictions = model.predict(X)
df["predicted_power"] = predictions

print("Predictions generated")

# power threshold classification
def classify_power(power):
    if power < 500:
        return "low"
    elif power < 1500:
        return "medium"
    else:
        return "high"

df["power_category"] = df["predicted_power"].apply(classify_power)

print("Power classification added")

# -----------------------------
# MONGODB CONNECTION
# -----------------------------
client = MongoClient(MONGO_URI)
db = client[DB_NAME]
collection = db[COLLECTION_NAME]

# clears database to avoid duplicate entries
collection.delete_many({})

# insert data into mongo
documents = []

for _, row in df.iterrows():
    doc = {
        "location": {
            "type": "Point",
            "coordinates": [float(row["lon"]), float(row["lat"])]
        },
        "expected_power_output": float(row["predicted_power"]),
        "power_category": row["power_category"]
    }
    documents.append(doc)

if documents:
    collection.insert_many(documents)

print(f"Inserted {len(documents)} documents into MongoDB")