import pickle
from pathlib import Path
import pandas as pd
import numpy as np
import requests

# Load trained model
model_path = Path("model.pkl")

with open(model_path, "rb") as f:
    model = pickle.load(f)

print("Model loaded successfully!")
print("Model type:", type(model))

if hasattr(model, "feature_names_in_"):
    print("Features expected by the model:")
    print(model.feature_names_in_)


# Function to get wind data from Open-Meteo
def get_open_meteo_features(latitude, longitude):
    url = "https://api.open-meteo.com/v1/forecast"

    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "wind_speed_10m,wind_direction_10m",
        "wind_speed_unit": "ms",
        "timezone": "auto"
    }

    response = requests.get(url, params=params)
    response.raise_for_status()

    data = response.json()

    wind_speed = data["current"]["wind_speed_10m"]
    wind_direction = data["current"]["wind_direction_10m"]

    # Convert wind direction from degrees to radians
    direction_rad = np.deg2rad(wind_direction)

    # Create sin and cos features from wind direction
    dir_sin = np.sin(direction_rad)
    dir_cos = np.cos(direction_rad)

    # Approximate wind power density
    # Formula: 0.5 * air density * wind speed^3
    air_density = 1.225
    wind_power_density = 0.5 * air_density * (wind_speed ** 3)

    X = pd.DataFrame({
        "wind_speed_ms": [wind_speed],
        "dir_sin": [dir_sin],
        "dir_cos": [dir_cos],
        "wind_power_density": [wind_power_density]
    })

    return X, wind_speed, wind_direction


# Example location: Rotterdam
latitude = 51.9244
longitude = 4.4777

X, wind_speed, wind_direction = get_open_meteo_features(latitude, longitude)

print("Open-Meteo wind speed:", wind_speed)
print("Open-Meteo wind direction:", wind_direction)
print("Input features:")
print(X)

prediction = model.predict(X)

print("Prediction:", prediction)
print("Predicted power output:", prediction[0])