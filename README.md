# Wind Turbine Location Suitability Pipeline Overview

This project estimates wind turbine power output across the Netherlands using a model trained on real SCADA turbine data, then serves the predictions through a MongoDB-backed API.

The pipeline runs in five stages, each handled by a separate script:

```
dataprep.py  ->  eda.py  ->  ml.py  ->  data_setup.py  ->  app.py
```

---

## 1. `dataprep.py` - Data Preparation

Loads and cleans the two raw data sources, and builds the empirical power curve used for exploratory analysis.

**SCADA branch (Turkish turbine data):**
- Renames raw columns to consistent snake_case names.
- Drops rows missing wind speed or active power.
- Applies sanity bounds on wind speed (0 to 40 m/s) to remove faulty sensor readings.
- Clips negative power readings to 0 (turbine briefly consuming rather than generating power).
- **Removes downtime/curtailment rows**: rows where wind speed exceeds cut-in speed (3 m/s) but active power stays below 50 kW are dropped. These represent the turbine being offline, under maintenance, or curtailed (not real wind-to-power behavior) and would otherwise teach the model that strong wind can produce near-zero power.
- Drops the timestamp column, since the SCADA data (Turkey) and Open-Meteo data (Netherlands) can't be aligned on time.
- Builds an empirical power curve by binning wind speed into 0.5 m/s buckets and averaging active power per bin (bins need >= 20 samples to be kept).

**Open-Meteo branch (Dutch weather grid):**
- Builds a ~300-point grid covering the Netherlands (0.2° spacing).
- Queries Open-Meteo's API in batches of 100 for current wind speed/direction at 100 m height.
- Cleans duplicates, missing values, and physically impossible wind speeds (>50 m/s).
- Applies the empirical power curve to estimate expected power per grid point.

**Outputs:** `scada_clean.csv`, `power_curve.csv`, `grid_wind.csv`, plus exploratory figures (`power_curve.png`, `grid_wind_map.png`, `grid_power_map.png`).

---

## 2. `eda.py` - Feature Engineering & Exploratory Analysis

Loads `scada_clean.csv` and engineers the features used for modeling, while generating the exploratory plots used in the report.

**Engineered features:**
- `wind_power_density`:  `0.5 * 1.225 * wind_speed^3` (W/m^3); captures the cubic relationship between wind speed and available energy.
- `capacity_factor`:  actual power divided by the dataset's maximum theoretical power; normalizes output to a 0 to 1 scale.
- `power_efficiency`:  actual power divided by theoretical power (only where theoretical > 10 kW, to avoid division instability near zero).
- `dir_sin` / `dir_cos`:  sine/cosine decomposition of wind direction, preserving its circular nature (359° and 1° are nearly identical but numerically far apart otherwise).

**Outputs**:
- Actual vs. theoretical power curve scatter plot.
- Wind speed distribution histogram.
- Capacity factor and power efficiency distribution histograms.
-  `scada_features.csv`, which is the final feature table used for model training.

---

## 3. `ml.py` - Model Training & Evaluation

Loads `scada_features.csv` and trains the prediction model.

- **Features:** `wind_speed_ms`, `dir_sin`, `dir_cos`, `wind_power_density`
- **Target:** `active_power_kw`
- **Split:** 80/20 train/test, fixed random seed for reproducibility.
- **Model:** `XGBRegressor` (300 estimators, max depth 6, learning rate 0.05, 0.8 subsample/colsample), whcih was chosen over the Sprint 1 Random Forest baseline for better handling of the non-linear wind-power relationship.

**Outputs:**
- Predicted vs. actual scatter plot.
- Feature importance bar chart (confirms `wind_power_density` and `wind_speed_ms` dominate. Wind direction contributes almost nothing, consistent with turbines having active yaw control).
- Residual plot (checks for systematic bias).
- `model.pkl`, whcih is the trained model packaged to be ready for usage.

---

## 4. `data_setup.py` - Inference & MongoDB Population

Loads the trained model and the Open-Meteo grid data, generates predictions for every grid point, and writes the results into MongoDB.

- Re-derives the same four features (`wind_speed_ms`, `dir_sin`, `dir_cos`, `wind_power_density`) from the raw grid wind speed/direction, matching the training feature space exactly.
- Runs inference with the trained model to get `predicted_power` per grid point.
- Classifies each point into `low` (<500 kW), `medium` (500 to 1500 kW), or `high` (>=1500 kW) suitability.
- Clears the MongoDB collection and inserts one document per grid point as GeoJSON:

```json
{
  "location": { "type": "Point", "coordinates": [lon, lat] },
  "expected_power_output": 1234.5,
  "power_category": "medium"
}
```

This structure supports a `2dsphere` index for geospatial queries (e.g. nearest-point lookups, radius searches).

---

## 5. `app.py` - API Layer


---

## Running the Pipeline

```bash
pip install -r requirements.txt # to install the necessary packages
python dataprep.py      # clean raw data, build power curve, query Open-Meteo
python eda.py            # engineer features, generate exploratory plots
python ml.py              # train and evaluate the model
python data_setup.py     # run inference, populate MongoDB
```

---
