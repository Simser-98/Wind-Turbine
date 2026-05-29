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

DUTCH_LOCATIONS: list[Location] = [
    Location("Den Helder (coast, N)",   52.96, 4.76),
    Location("IJmuiden (coast)",        52.46, 4.55),
    Location("Lelystad (Flevoland)",    52.51, 5.47),
    Location("Groningen (NE inland)",   53.22, 6.57),
    Location("Rotterdam (delta)",       51.92, 4.48),
    Location("Eindhoven (S inland)",    51.44, 5.48),
    Location("Maastricht (SE inland)",  50.85, 5.69),
    Location("Terschelling (Wadden)",   53.40, 5.34),
]

# Historical period — 1 full year is enough for the MVP (seasonality covered).
ARCHIVE_START = "2023-01-01"
ARCHIVE_END   = "2023-12-31"

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


# Open-Meteo preparation

def fetch_openmeteo_location(loc: Location,
                             start: str = ARCHIVE_START,
                             end: str = ARCHIVE_END) -> pd.DataFrame:

    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude":   loc.lat,
        "longitude":  loc.lon,
        "start_date": start,
        "end_date":   end,
        "hourly":     "wind_speed_100m,wind_direction_100m",
        "wind_speed_unit": "ms",
        "timezone":   "UTC",
    }
    log.info("Querying Open-Meteo for %s ...", loc.name)
    r = requests.get(url, params=params, timeout=60)
    r.raise_for_status()
    j = r.json()

    df = pd.DataFrame({
        "timestamp":           pd.to_datetime(j["hourly"]["time"]),
        "wind_speed_100m_ms":  j["hourly"]["wind_speed_100m"],
        "wind_direction_100m": j["hourly"]["wind_direction_100m"],
    })
    df["location"] = loc.name
    df["lat"] = loc.lat
    df["lon"] = loc.lon
    return df


def fetch_openmeteo_all(locations: list[Location]) -> pd.DataFrame:

    frames = [fetch_openmeteo_location(loc) for loc in locations]
    df = pd.concat(frames, ignore_index=True)
    log.info("Open-Meteo combined: %d rows across %d locations",
             len(df), len(locations))
    return df


def clean_openmeteo(df: pd.DataFrame) -> pd.DataFrame:

    df = df.copy()
    n_before = len(df)

    # Drop duplicate (location, timestamp) pairs if any
    df = df.drop_duplicates(subset=["location", "timestamp"])

    # Missing-value report (per location)
    na_report = df.groupby("location")["wind_speed_100m_ms"].apply(
        lambda s: s.isna().mean() * 100
    )
    for loc, pct in na_report.items():
        if pct > 0:
            log.warning("  %s: %.2f%% missing wind speed", loc, pct)

    df = df.dropna(subset=["wind_speed_100m_ms"])

    #wind speeds beyond 50 m/s at 100 m are reanalysis errors
    df = df[(df["wind_speed_100m_ms"] >= 0) &
            (df["wind_speed_100m_ms"] <= 50)]

    log.info("Open-Meteo cleaned: kept %d / %d rows", len(df), n_before)
    return df


def location_features(df: pd.DataFrame) -> pd.DataFrame:

    g = df.groupby("location")
    feats = pd.DataFrame({
        "lat":              g["lat"].first(),
        "lon":              g["lon"].first(),
        "mean_wind_ms":     g["wind_speed_100m_ms"].mean(),
        "median_wind_ms":   g["wind_speed_100m_ms"].median(),
        "std_wind_ms":      g["wind_speed_100m_ms"].std(),
        "p90_wind_ms":      g["wind_speed_100m_ms"].quantile(0.90),
        "pct_hours_in_operating_range":
            g["wind_speed_100m_ms"].apply(
                lambda s: ((s >= CUT_IN_SPEED) & (s <= CUT_OUT_SPEED)).mean() * 100
            ),
        "pct_hours_calm":   g["wind_speed_100m_ms"].apply(
            lambda s: (s < CUT_IN_SPEED).mean() * 100
        ),
        "n_hours":          g["wind_speed_100m_ms"].count(),
    }).reset_index()
    log.info("Built per-location features for %d locations", len(feats))
    return feats


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


def plot_location_mean_wind(feats: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(9, 5))
    order = feats.sort_values("mean_wind_ms", ascending=False)
    ax.bar(order["location"], order["mean_wind_ms"])
    ax.set_ylabel("Mean wind speed at 100 m (m/s)")
    ax.set_title(f"Mean wind speed by Dutch location "
                 f"({ARCHIVE_START} → {ARCHIVE_END})")
    plt.xticks(rotation=30, ha="right")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "location_mean_wind.png", dpi=120)
    plt.close(fig)
    log.info("Saved figure: location_mean_wind.png")



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
    om_raw = fetch_openmeteo_all(DUTCH_LOCATIONS)
    om_raw.to_csv(PROC_DIR / "openmeteo_raw.csv", index=False)

    om_clean = clean_openmeteo(om_raw)
    feats = location_features(om_clean)
    feats.to_csv(PROC_DIR / "openmeteo_location_features.csv", index=False)
    plot_location_mean_wind(feats)

    log.info("=== Pipeline finished. Outputs in %s ===", PROC_DIR.resolve())


run_pipeline()