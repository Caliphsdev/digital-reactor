"""
plant_calibration.py — Daspoort monitoring import and calibration utilities.

V1 intentionally calibrates only Daspoort. The same table structures can serve
Zeekoegat and Phola later, but calibration should be rolled out plant-by-plant
once the monitoring data and process assumptions are defensible.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean, median
from typing import Any

import pandas as pd

from core.models import Plant, PlantCalibration, PlantMonitoringReading
from simulation.plant_model import PlantTwinInputs, run_plant_twin


DASPOORT_SLUG = "daspoort"
CALIBRATION_TARGETS = ("cod", "nh4", "tn", "tp", "pfas")

POINT_ALIASES = {
    "sp1": "SP1_influent",
    "sp1_influent": "SP1_influent",
    "influent": "SP1_influent",
    "raw_influent": "SP1_influent",
    "inlet": "SP1_influent",
    "sp2": "SP2_primary",
    "sp2_primary": "SP2_primary",
    "primary": "SP2_primary",
    "primary_effluent": "SP2_primary",
    "bnr_feed": "SP2_primary",
    "sp3": "SP3_clarifier",
    "sp3_clarifier": "SP3_clarifier",
    "clarifier": "SP3_clarifier",
    "secondary_clarifier": "SP3_clarifier",
    "sp4": "SP4_effluent",
    "sp4_effluent": "SP4_effluent",
    "effluent": "SP4_effluent",
    "final_effluent": "SP4_effluent",
    "outlet": "SP4_effluent",
}

COLUMN_ALIASES = {
    "sampling_date": ["sampling_date", "sample_date", "date", "sampling day"],
    "sampling_point_code": ["sampling_point_code", "sampling_point", "sample_point", "point", "location", "site"],
    "flow_mld": ["flow_mld", "flow", "q_mld", "flow_ml_day", "flow_ml/d"],
    "cod_mgl": ["cod_mgl", "cod", "cod_mg_l", "cod mg/l"],
    "bod_mgl": ["bod_mgl", "bod", "bod5", "bod_mg_l", "bod mg/l"],
    "nh4_mgl": ["nh4_mgl", "nh4", "nh4_n", "ammonia", "ammonia_mgl", "ammonia mg/l"],
    "no3_mgl": ["no3_mgl", "no3", "nitrate", "nitrate_mgl", "nitrate mg/l"],
    "tn_mgl": ["tn_mgl", "tn", "total_n", "total_nitrogen", "total nitrogen"],
    "tp_mgl": ["tp_mgl", "tp", "total_p", "total_phosphorus", "total phosphorus"],
    "tss_mgl": ["tss_mgl", "tss", "tss_mg_l", "tss mg/l"],
    "do_mgl": ["do_mgl", "do", "dissolved_oxygen", "dissolved oxygen"],
    "mlss_mgl": ["mlss_mgl", "mlss", "mlss_mg_l", "mlss mg/l"],
    "srt_days": ["srt_days", "srt", "sludge_age", "sludge age"],
    "hrt_hours": ["hrt_hours", "hrt", "hydraulic_retention_time", "hydraulic retention time"],
    "recycle_ratio": ["recycle_ratio", "a_recycle", "a_recycle_ratio", "internal_recycle"],
    "ph": ["ph", "pH"],
    "temperature_c": ["temperature_c", "temp_c", "temperature", "temp"],
    "cec_name": ["cec_name", "compound", "contaminant", "pfas", "pfas_name", "analyte"],
    "cec_type": ["cec_type", "pfas_type", "chain_type"],
    "concentration_ugl": ["concentration_ugl", "cec_concentration", "pfas_concentration", "concentration", "conc_ugl", "ug_l"],
    "below_detection": ["below_detection", "bdl", "below_dl", "non_detect"],
    "detection_limit_ugl": ["detection_limit_ugl", "detection_limit", "dl", "lod", "loq"],
}


def _norm(value: Any) -> str:
    return str(value).strip().casefold().replace("µ", "u").replace("/", "_").replace(" ", "_")


def _column_map(columns) -> dict[str, str]:
    lookup = {_norm(col): col for col in columns}
    mapped: dict[str, str] = {}
    for canonical, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            key = _norm(alias)
            if key in lookup:
                mapped[canonical] = lookup[key]
                break
    return mapped


def _value(row, mapped: dict[str, str], key: str):
    col = mapped.get(key)
    if col is None:
        return None
    value = row.get(col)
    if pd.isna(value):
        return None
    return value


def _float_or_none(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        return float(value)
    except Exception:
        return None


def _bool_value(value) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return value
    text = str(value).strip().casefold()
    return text in {"1", "true", "yes", "y", "bdl", "below", "<dl", "non_detect"}


def _date_value(value):
    if value is None:
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def normalise_sampling_point(value) -> str | None:
    if value is None:
        return None
    key = _norm(value)
    return POINT_ALIASES.get(key)


def _read_table(path: str | Path) -> pd.DataFrame:
    file_path = Path(path)
    suffix = file_path.suffix.casefold()
    if suffix in {".xlsx", ".xls"}:
        return pd.read_excel(file_path)
    if suffix == ".csv":
        return pd.read_csv(file_path)
    raise ValueError("Use a CSV or Excel file (.csv, .xlsx, .xls).")


def import_monitoring_file(session, plant_slug: str, path: str | Path) -> dict:
    """
    Import Daspoort monitoring rows from CSV/XLSX into plant_monitoring_readings.

    Rows are matched by plant/date/sampling point/CEC name to avoid duplicates
    when the same file is imported again.
    """
    if plant_slug != DASPOORT_SLUG:
        raise ValueError("V1 calibration import is enabled for Daspoort only.")

    plant = session.query(Plant).filter_by(slug=plant_slug).first()
    if plant is None:
        raise ValueError("Daspoort plant profile was not found.")

    df = _read_table(path)
    mapped = _column_map(df.columns)
    missing = [key for key in ("sampling_date", "sampling_point_code") if key not in mapped]
    if missing:
        raise ValueError("Import file must include date and sampling point columns.")

    point_ids = {p.code: p.id for p in plant.sampling_points}
    imported = 0
    updated = 0
    skipped = 0
    warnings: list[str] = []
    source = Path(path).name

    for row_i, row in df.iterrows():
        sampling_date = _date_value(_value(row, mapped, "sampling_date"))
        point_code = normalise_sampling_point(_value(row, mapped, "sampling_point_code"))
        if not sampling_date or not point_code:
            skipped += 1
            warnings.append(f"Row {row_i + 2}: skipped because date or sampling point is invalid.")
            continue

        cec_name_raw = _value(row, mapped, "cec_name")
        cec_name = str(cec_name_raw).strip() if cec_name_raw not in (None, "") else None

        query = (
            session.query(PlantMonitoringReading)
            .filter_by(
                plant_id=plant.id,
                sampling_date=sampling_date,
                sampling_point_code=point_code,
            )
        )
        if cec_name:
            query = query.filter(PlantMonitoringReading.cec_name == cec_name)
        else:
            query = query.filter(PlantMonitoringReading.cec_name.is_(None))

        record = query.first()
        if record is None:
            record = PlantMonitoringReading(
                plant_id=plant.id,
                sampling_date=sampling_date,
                sampling_point_code=point_code,
                sampling_point_id=point_ids.get(point_code),
            )
            session.add(record)
            imported += 1
        else:
            updated += 1

        record.cec_name = cec_name
        record.cec_type = _value(row, mapped, "cec_type")
        record.concentration_ugl = _float_or_none(_value(row, mapped, "concentration_ugl"))
        record.below_detection = _bool_value(_value(row, mapped, "below_detection"))
        record.detection_limit_ugl = _float_or_none(_value(row, mapped, "detection_limit_ugl"))
        record.cod_mgl = _float_or_none(_value(row, mapped, "cod_mgl"))
        record.bod_mgl = _float_or_none(_value(row, mapped, "bod_mgl"))
        record.nh4_mgl = _float_or_none(_value(row, mapped, "nh4_mgl"))
        record.no3_mgl = _float_or_none(_value(row, mapped, "no3_mgl"))
        record.tn_mgl = _float_or_none(_value(row, mapped, "tn_mgl"))
        record.tp_mgl = _float_or_none(_value(row, mapped, "tp_mgl"))
        record.tss_mgl = _float_or_none(_value(row, mapped, "tss_mgl"))
        record.do_mgl = _float_or_none(_value(row, mapped, "do_mgl"))
        record.mlss_mgl = _float_or_none(_value(row, mapped, "mlss_mgl"))
        record.srt_days = _float_or_none(_value(row, mapped, "srt_days"))
        record.hrt_hours = _float_or_none(_value(row, mapped, "hrt_hours"))
        record.recycle_ratio = _float_or_none(_value(row, mapped, "recycle_ratio"))
        record.ph = _float_or_none(_value(row, mapped, "ph"))
        record.temperature_c = _float_or_none(_value(row, mapped, "temperature_c"))
        record.flow_mld = _float_or_none(_value(row, mapped, "flow_mld"))
        record.source = source

    return {
        "imported": imported,
        "updated": updated,
        "skipped": skipped,
        "warnings": warnings[:8],
    }


def compute_calibration_metrics(pairs: list[dict]) -> dict | None:
    """Compute a robust multiplier and error metrics from prediction/actual pairs."""
    clean = [
        p for p in pairs
        if p.get("predicted") is not None
        and p.get("actual") is not None
        and p["predicted"] > 0
    ]
    if not clean:
        return None

    ratios = [p["actual"] / p["predicted"] for p in clean]
    multiplier = max(0.25, min(2.5, median(ratios)))
    calibrated = [max(0.0, min(99.0, p["predicted"] * multiplier)) for p in clean]
    actual = [p["actual"] for p in clean]
    errors = [c - a for c, a in zip(calibrated, actual)]
    abs_errors = [abs(e) for e in errors]
    rmse = (sum(e * e for e in errors) / len(errors)) ** 0.5

    y_mean = mean(actual)
    ss_tot = sum((a - y_mean) ** 2 for a in actual)
    ss_res = sum((a - c) ** 2 for a, c in zip(actual, calibrated))
    r2 = None if ss_tot == 0 else 1.0 - ss_res / ss_tot

    dates = [p["date"] for p in clean if p.get("date")]
    return {
        "multiplier": multiplier,
        "n_samples": len(clean),
        "rmse_pct": rmse,
        "mean_abs_error_pct": mean(abs_errors),
        "r2": r2,
        "actual_mean_pct": mean(actual),
        "predicted_mean_pct": mean([p["predicted"] for p in clean]),
        "date_start": min(dates) if dates else None,
        "date_end": max(dates) if dates else None,
    }


def _first(*values, fallback=0.0):
    for value in values:
        if value is not None:
            return value
    return fallback


def _actual_removal(inf: float | None, eff: float | None) -> float | None:
    if inf is None or eff is None or inf <= 0:
        return None
    return max(0.0, min(100.0, (inf - eff) / inf * 100.0))


def _conc(row: PlantMonitoringReading) -> float | None:
    if row.concentration_ugl is None:
        if row.below_detection and row.detection_limit_ugl:
            return row.detection_limit_ugl / 2.0
        return None
    return row.concentration_ugl


def _inputs_from_rows(plant: Plant, influent, effluent, pfas_value: float | None = None, pfas_type: str = "short-chain", pfas_name: str = "") -> PlantTwinInputs:
    return PlantTwinInputs(
        plant_slug=plant.slug,
        flow_mld=_first(influent.flow_mld, effluent.flow_mld, plant.default_flow_mld, fallback=1.0),
        hrt_hours=_first(influent.hrt_hours, effluent.hrt_hours, plant.default_hrt_hours, fallback=12.0),
        srt_days=_first(influent.srt_days, effluent.srt_days, plant.default_srt_days, fallback=30.0),
        mlss_mgl=_first(influent.mlss_mgl, effluent.mlss_mgl, plant.default_mlss_mgl, fallback=3000.0),
        do_mgl=_first(influent.do_mgl, effluent.do_mgl, plant.default_do_mgl, fallback=1.5),
        temp_c=_first(influent.temperature_c, effluent.temperature_c, plant.default_temp_c, fallback=22.0),
        ph=_first(influent.ph, effluent.ph, plant.default_ph, fallback=7.5),
        recycle_ratio=_first(influent.recycle_ratio, effluent.recycle_ratio, plant.default_recycle_ratio, fallback=4.0),
        organic_loading=plant.default_organic_loading or 0.0,
        nitrogen_loading=plant.default_nitrogen_loading or 0.0,
        inf_cod_mgl=_first(influent.cod_mgl, fallback=350.0),
        inf_nh4_mgl=_first(influent.nh4_mgl, fallback=45.0),
        inf_tn_mgl=_first(influent.tn_mgl, fallback=70.0),
        inf_tp_mgl=_first(influent.tp_mgl, fallback=8.0),
        inf_pfas_ugl=pfas_value if pfas_value is not None else 50.0,
        pfas_type=pfas_type or "short-chain",
        pfas_compound=pfas_name or "",
    )


def _rows_by_date_and_point(rows):
    grouped = defaultdict(dict)
    for row in rows:
        if row.cec_name:
            continue
        grouped[row.sampling_date][row.sampling_point_code] = row
    return grouped


def _calibration_pairs(plant: Plant, rows: list[PlantMonitoringReading]) -> dict[str, list[dict]]:
    pairs: dict[str, list[dict]] = {target: [] for target in CALIBRATION_TARGETS}
    conventional = _rows_by_date_and_point(rows)

    attr_map = {
        "cod": ("cod_mgl", "cod_removal_pct"),
        "nh4": ("nh4_mgl", "nh4_removal_pct"),
        "tn": ("tn_mgl", "tn_removal_pct"),
        "tp": ("tp_mgl", "tp_removal_pct"),
    }
    for sample_date, by_point in conventional.items():
        inf = by_point.get("SP1_influent")
        eff = by_point.get("SP4_effluent")
        if not inf or not eff:
            continue
        outputs = run_plant_twin(_inputs_from_rows(plant, inf, eff))
        for target, (row_attr, output_attr) in attr_map.items():
            actual = _actual_removal(getattr(inf, row_attr), getattr(eff, row_attr))
            if actual is None:
                continue
            pairs[target].append({
                "date": sample_date,
                "actual": actual,
                "predicted": getattr(outputs, output_attr),
            })

    cec_rows = [row for row in rows if row.cec_name]
    cec_grouped = defaultdict(dict)
    for row in cec_rows:
        cec_grouped[(row.sampling_date, row.cec_name)][row.sampling_point_code] = row
    for (sample_date, cec_name), by_point in cec_grouped.items():
        inf = by_point.get("SP1_influent")
        eff = by_point.get("SP4_effluent")
        if not inf or not eff:
            continue
        inf_conc = _conc(inf)
        eff_conc = _conc(eff)
        actual = _actual_removal(inf_conc, eff_conc)
        if actual is None:
            continue
        outputs = run_plant_twin(_inputs_from_rows(
            plant, inf, eff, pfas_value=inf_conc,
            pfas_type=inf.cec_type or "short-chain",
            pfas_name=cec_name,
        ))
        pairs["pfas"].append({
            "date": sample_date,
            "actual": actual,
            "predicted": outputs.pfas_removal_pct,
        })

    return pairs


def calibrate_plant(session, plant_slug: str = DASPOORT_SLUG) -> dict:
    """Fit and persist Daspoort target multipliers from imported monitoring data."""
    if plant_slug != DASPOORT_SLUG:
        raise ValueError("V1 calibration is enabled for Daspoort only.")

    plant = session.query(Plant).filter_by(slug=plant_slug).first()
    if plant is None:
        raise ValueError("Daspoort plant profile was not found.")

    rows = session.query(PlantMonitoringReading).filter_by(plant_id=plant.id).all()
    pairs = _calibration_pairs(plant, rows)
    saved: dict[str, dict] = {}

    for target, target_pairs in pairs.items():
        metrics = compute_calibration_metrics(target_pairs)
        if metrics is None:
            continue

        existing = (
            session.query(PlantCalibration)
            .filter_by(plant_id=plant.id, target=target)
            .first()
        )
        calibration = existing or PlantCalibration(plant_id=plant.id, target=target)
        if existing is None:
            session.add(calibration)

        calibration.multiplier = metrics["multiplier"]
        calibration.n_samples = metrics["n_samples"]
        calibration.rmse_pct = metrics["rmse_pct"]
        calibration.mean_abs_error_pct = metrics["mean_abs_error_pct"]
        calibration.r2 = metrics["r2"]
        calibration.actual_mean_pct = metrics["actual_mean_pct"]
        calibration.predicted_mean_pct = metrics["predicted_mean_pct"]
        calibration.date_start = metrics["date_start"]
        calibration.date_end = metrics["date_end"]
        calibration.method = "median actual/predicted removal multiplier"
        calibration.notes = "Daspoort v1 calibration from imported SP1 to SP4 monitoring pairs."
        calibration.calibrated_at = datetime.now(timezone.utc)
        saved[target] = metrics

    return {
        "targets": saved,
        "row_count": len(rows),
        "pair_counts": {target: len(target_pairs) for target, target_pairs in pairs.items()},
    }


def get_calibration_factors(session, plant_id: int) -> dict[str, float]:
    """Return persisted multipliers for the plant, keyed by target."""
    rows = session.query(PlantCalibration).filter_by(plant_id=plant_id).all()
    return {row.target: row.multiplier for row in rows if row.n_samples > 0}


def get_calibration_summary(session, plant_id: int) -> list[PlantCalibration]:
    """Return calibration rows in target order for display."""
    rows = session.query(PlantCalibration).filter_by(plant_id=plant_id).all()
    order = {target: i for i, target in enumerate(CALIBRATION_TARGETS)}
    return sorted(rows, key=lambda row: order.get(row.target, 99))
