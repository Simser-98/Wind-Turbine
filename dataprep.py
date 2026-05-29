from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import requests

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("data_prep")

DATA_DIR = Path("data")
RAW_DIR = DATA_DIR / "raw"
PROC_DIR = DATA_DIR / "processed"
FIG_DIR = PROC_DIR / "figures"
for d in (RAW_DIR, PROC_DIR, FIG_DIR):
    d.mkdir(parents=True, exist_ok=True)

# Path to the SCADA CSV you downloaded from Kaggle.
# (Filename on Kaggle: "T1.csv")
SCADA_CSV = RAW_DIR / "T1.csv"

# Small, defensible set of Dutch locations spread across the country.
@dataclass(frozen=True)
class Location:
    name: str
    lat: float
    lon: float

# Area of the Netherlands
NL_LAT_MIN, NL_LAT_MAX = 50.75, 53.55
NL_LON_MIN, NL_LON_MAX = 3.35, 7.25

# 0.2 deg = 22 km lat / 14 km lon
GRID_STEP_DEG = 0.2

BATCH_SIZE = 100

# Turbine operating range used as a sanity / feature definition.
CUT_IN_SPEED  = 3.0   # m/s
CUT_OUT_SPEED = 25.0  # m/s


# SCADA preparation

def load_scada(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(
            f"SCADA file not found at {path}. "
            f"Download T1.csv from Kaggle and put it in {RAW_DIR}/"
        )
    df = pd.read_csv(path)
    df = df.rename(columns={
        "Date/Time":                  "timestamp",
        "LV ActivePower (kW)":        "active_power_kw",
        "Wind Speed (m/s)":           "wind_speed_ms",
        "Theoretical_Power_Curve (KWh)": "theoretical_power_kw",
        "Wind Direction (°)":         "wind_direction_deg",
    })
    log.info("SCADA loaded: %d rows, %d columns", *df.shape)
    return df


def clean_scada(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()

    # Timestamp parsing
    df["timestamp"] = pd.to_datetime(
        df["timestamp"], format="%d %m %Y %H:%M", errors="coerce"
    )

    n_before = len(df)

    # Drop rows where the core measurements are missing
    df = df.dropna(subset=["wind_speed_ms", "active_power_kw"])

    # Sanity bounds on wind speed (sensor stuck / fault)
    df = df[(df["wind_speed_ms"] >= 0) & (df["wind_speed_ms"] <= 40)]

    # Negative power -> 0 (documented decision)
    df["active_power_kw"] = df["active_power_kw"].clip(lower=0)

    log.info(
        "SCADA cleaned: kept %d / %d rows (%.1f%%)",
        len(df), n_before, 100 * len(df) / n_before,
    )

    # Drop the Turkish timestamp — explicitly not meaningful for NL context.
    return df.drop(columns=["timestamp"])


def build_power_curve(df_scada: pd.DataFrame, bin_width: float = 0.5) -> pd.DataFrame:

    bins = np.arange(0, 30 + bin_width, bin_width)
    df = df_scada.copy()
    df["wind_speed_bin"] = pd.cut(df["wind_speed_ms"], bins=bins, right=False)

    curve = (
        df.groupby("wind_speed_bin", observed=True)["active_power_kw"]
          .agg(["mean", "std", "count"])
          .reset_index()
    )
    # Use the left edge of each bin as the representative wind speed
    curve["wind_speed_ms"] = curve["wind_speed_bin"].apply(lambda b: b.left).astype(float)
    curve = curve[["wind_speed_ms", "mean", "std", "count"]]
    curve = curve.rename(columns={"mean": "power_kw_mean",
                                  "std":  "power_kw_std"})
    # Keep bins with enough samples for stable averages
    curve = curve[curve["count"] >= 20].reset_index(drop=True)

    log.info("Power curve built: %d wind-speed bins of %.1f m/s",
             len(curve), bin_width)
    return curve

def apply_power_curve(wind_speeds: np.ndarray, curve: pd.DataFrame) -> np.ndarray:
    xs = curve["wind_speed_ms"].to_numpy()
    ys = curve["power_kw_mean"].to_numpy()
    power = np.interp(wind_speeds, xs, ys, left=0.0, right=ys[-1])
    power = np.where(wind_speeds >= CUT_OUT_SPEED, 0.0, power)
    power = np.where(wind_speeds < CUT_IN_SPEED, 0.0, power)
    return power

# Open-Meteo preparation

def build_nl_grid(step_deg: float = GRID_STEP_DEG) -> list[Location]:
    lats = np.arange(NL_LAT_MIN, NL_LAT_MAX + 1e-9, step_deg)
    lons = np.arange(NL_LON_MIN, NL_LON_MAX + 1e-9, step_deg)
    points = [
        Location(name=f"grid_{lat:.2f}_{lon:.2f}",
                 lat=round(float(lat), 4),
                 lon=round(float(lon), 4))
        for lat in lats for lon in lons
    ]
    log.info("Built NL grid: %d points (step %.2f deg, %d x %d)",
             len(points), step_deg, len(lats), len(lons))
    return points

def fetch_openmeteo_batch(batch: list[Location]) -> pd.DataFrame:
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":        ",".join(f"{p.lat}" for p in batch),
        "longitude":       ",".join(f"{p.lon}" for p in batch),
        "current":         "wind_speed_100m,wind_direction_100m",
        "wind_speed_unit": "ms",
        "timezone":   "UTC",
    }
    log.info("Querying Open-Meteo for %s ...", len(batch))
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    payload = r.json()

    if isinstance(payload, dict):
        payload = [payload]

    rows = []
    for point, resp in zip(batch, payload):
        cur = resp.get("current", {})
        rows.append({
            "lat":                  point.lat,
            "lon":                  point.lon,
            "queried_at_utc":       cur.get("time"),
            "wind_speed_100m_ms":   cur.get("wind_speed_100m"),
            "wind_direction_100m":  cur.get("wind_direction_100m"),
        })
    return pd.DataFrame(rows)


def fetch_openmeteo_all(points: list[Location]) -> pd.DataFrame:
    frames = []
    for i in range(0, len(points), BATCH_SIZE):
        frames.append(fetch_openmeteo_batch(points[i:i + BATCH_SIZE]))
    df = pd.concat(frames, ignore_index=True)
    log.info("Open-Meteo combined: %d grid rows", len(df))
    return df


def clean_openmeteo(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()
    n_before = len(df)

    # Drop duplicate (location, timestamp) pairs if any
    df = df.drop_duplicates(subset=["lat", "lon"])

    n_missing = df["wind_speed_100m_ms"].isna().sum()
    if n_missing:
        log.warning("Dropping %d grid points with missing wind speed", n_missing)
    df = df.dropna(subset=["wind_speed_100m_ms"])

    #wind speeds beyond 50 m/s at 100 m are reanalysis errors
    df = df[(df["wind_speed_100m_ms"] >= 0) &
            (df["wind_speed_100m_ms"] <= 50)]

    log.info("Open-Meteo cleaned: kept %d / %d rows", len(df), n_before)
    return df


def grid_features(df: pd.DataFrame, power_curve: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["expected_power_kw"] = apply_power_curve(
        df["wind_speed_100m_ms"].to_numpy(), power_curve
    )
    df["in_operating_range"] = (
        (df["wind_speed_100m_ms"] >= CUT_IN_SPEED) &
        (df["wind_speed_100m_ms"] <= CUT_OUT_SPEED)
    )
    log.info("Built grid features for %d points", len(df))
    return df[[
        "lat", "lon", "queried_at_utc",
        "wind_speed_100m_ms", "wind_direction_100m",
        "expected_power_kw", "in_operating_range",
    ]]


# Minimal MVP visualisations


def plot_power_curve(curve: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(curve["wind_speed_ms"], curve["power_kw_mean"],
            marker="o", linewidth=1.5, label="Empirical mean")
    ax.fill_between(curve["wind_speed_ms"],
                    curve["power_kw_mean"] - curve["power_kw_std"],
                    curve["power_kw_mean"] + curve["power_kw_std"],
                    alpha=0.2, label="±1 std")
    ax.set_xlabel("Wind speed (m/s)")
    ax.set_ylabel("Active power (kW)")
    ax.set_title("Empirical power curve derived from SCADA data")
    ax.grid(True, alpha=0.3)
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG_DIR / "power_curve.png", dpi=120)
    plt.close(fig)
    log.info("Saved figure: power_curve.png")


def plot_grid_wind(feats: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    sc = ax.scatter(feats["lon"], feats["lat"],
                    c=feats["wind_speed_100m_ms"],
                    cmap="viridis", s=60, marker="s")
    plt.colorbar(sc, ax=ax, label="Wind speed at 100 m (m/s)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Current wind speed across NL grid")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "grid_wind_map.png", dpi=120)
    plt.close(fig)
    log.info("Saved figure: grid_wind_map.png")


def plot_grid_power(feats: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 7))
    sc = ax.scatter(feats["lon"], feats["lat"],
                    c=feats["expected_power_kw"],
                    cmap="plasma", s=60, marker="s")
    plt.colorbar(sc, ax=ax, label="Expected power (kW)")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.set_title("Expected turbine power across NL grid (SCADA curve)")
    ax.set_aspect("equal", adjustable="datalim")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "grid_power_map.png", dpi=120)
    plt.close(fig)
    log.info("Saved figure: grid_power_map.png")

# Pipeline entry point

def run_pipeline() -> None:
    log.info("=== Sprint 1 data preparation pipeline ===")

    # ---- SCADA branch -----------------------------------------------------
    scada_raw = load_scada(SCADA_CSV)
    scada = clean_scada(scada_raw)
    scada.to_csv(PROC_DIR / "scada_clean.csv", index=False)

    power_curve = build_power_curve(scada)
    power_curve.to_csv(PROC_DIR / "power_curve.csv", index=False)
    plot_power_curve(power_curve)

    # ---- Open-Meteo branch ------------------------------------------------
    grid_points = build_nl_grid()
    om_raw = fetch_openmeteo_all(grid_points)
    om_raw.to_csv(PROC_DIR / "openmeteo_raw.csv", index=False)

    om_clean = clean_openmeteo(om_raw)
    feats = grid_features(om_clean, power_curve)
    feats.to_csv(PROC_DIR / "grid_wind.csv", index=False)

    plot_grid_wind(feats)
    plot_grid_power(feats)

    log.info("=== Pipeline finished. Outputs in %s ===", PROC_DIR.resolve())


run_pipeline()