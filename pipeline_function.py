from dataprep_functions import *

def run_pipeline() -> None:
    log.info("=== Data preparation pipeline ===")

    # ---- SCADA branch -----------------------------------------------------
    scada_raw = load_scada(SCADA_CSV)
    scada = clean_scada(scada_raw)
    scada.to_csv(PROC_DIR / "scada_clean.csv", index=False)

    # Validation figure BEFORE dropping, so the non-operational band is visible
    plot_power_scatter(scada)

    # Remove downtime / curtailment / fault rows, then save the operational set
    scada_op = filter_nonoperational(scada)
    scada_op.to_csv(PROC_DIR / "scada_operational.csv", index=False)

    power_curve = build_power_curve(scada_op)
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