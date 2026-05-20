"""
data_model.py — Phase 2 data-driven simulation model.

Trains a scikit-learn Random Forest on the researcher's own lab measurements
and uses it to predict removal efficiencies.  Falls back to Phase 1 equations
when the model has not been trained yet or when data are insufficient.

Two separate models are maintained:
  * Main model  — COD / NH4 / TP removal (requires ≥ 50 complete daily rows)
  * PFAS model  — PFAS removal          (requires ≥ 15 paired CEC readings)
"""

import json
import numpy as np
import pandas as pd
import joblib
from datetime import datetime
from pathlib import Path

from sklearn.ensemble import RandomForestRegressor
from sklearn.multioutput import MultiOutputRegressor
from sklearn.model_selection import cross_val_score, KFold
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import r2_score

from core.models import DailyReading, FlowReading, CECReading
from core.calculations import calc_actual_srt, calc_removal_pct
from core.paths import MODELS_DIR
from simulation.generic_model import (
    SimInputs, SimOutputs, run_phase1, REACTOR_VOLUME_L, AERATION_VOLUME_L,
)

# ── Thresholds ─────────────────────────────────────────────────────────────────
MAIN_MODEL_THRESHOLD = 50   # complete daily rows needed to train the main model
PFAS_MODEL_THRESHOLD = 15   # paired CEC rows needed to train the PFAS model

# ── Feature column order — must stay constant after first training ─────────────
# Note: a_recycle_ratio removed (CAS reactor has no anoxic zone recycle)
MAIN_FEATURE_COLS = [
    "q_in_mlh", "ras_ratio",
    "do_mgl", "srt_days", "temp_c", "ph", "mlss_mgl",
    "inf_cod", "inf_nh4", "inf_tp",
]
PFAS_FEATURE_COLS = [
    "q_in_mlh", "ras_ratio",
    "do_mgl", "srt_days", "temp_c", "ph", "mlss_mgl",
    "inf_pfas", "pfas_type_encoded",  # 0 = short-chain, 1 = long-chain
]

# ── Persistence paths (all inside AppData\DigitalReactor\models\) ─────────────
MAIN_MODEL_PATH = MODELS_DIR / "phase2_main.joblib"
PFAS_MODEL_PATH = MODELS_DIR / "phase2_pfas.joblib"
METADATA_PATH   = MODELS_DIR / "metadata.json"

# ── Module-level model cache (avoids re-deserialising on every slider move) ────
_main_model_cache = None
_pfas_model_cache = None


# ──────────────────────────────────────────────────────────────────────────────
# Data extraction
# ──────────────────────────────────────────────────────────────────────────────

def get_training_data(session) -> pd.DataFrame:
    """
    Build the main training DataFrame from the DB.

    Joins four tables on (experiment_id, reading_date):
      - DailyReading zone='aerobic'   → operating conditions (features)
      - DailyReading zone='effluent'  → output concentrations (targets)
      - DailyReading zone='anaerobic' → influent proxy concentrations
      - FlowReading                   → flow and recycle parameters

    Returns a clean DataFrame with MAIN_FEATURE_COLS and target columns.
    Empty DataFrame is returned when no matching rows exist.
    """
    def _to_df(rows, cols: dict) -> pd.DataFrame:
        data = []
        for r in rows:
            data.append({k: getattr(r, v) for k, v in cols.items()})
        return pd.DataFrame(data)

    aeration_rows  = session.query(DailyReading).filter(DailyReading.zone == "aeration").all()
    effluent_rows  = session.query(DailyReading).filter(DailyReading.zone == "effluent").all()
    pst_rows       = session.query(DailyReading).filter(DailyReading.zone == "primary_settling").all()
    flow_rows      = session.query(FlowReading).all()

    if not aeration_rows or not effluent_rows or not pst_rows or not flow_rows:
        return pd.DataFrame()

    df_aer = _to_df(aeration_rows, {
        "experiment_id": "experiment_id",
        "reading_date":  "reading_date",
        "do_mgl":        "do_mgl",
        "temp_c":        "temperature_c",
        "ph":            "ph",
        "mlss_mgl":      "mlss_mgl",
    })

    df_eff = _to_df(effluent_rows, {
        "experiment_id": "experiment_id",
        "reading_date":  "reading_date",
        "eff_cod":       "cod_mgl",
        "eff_nh4":       "nh4_mgl",
        "eff_tp":        "tp_mgl",
    })

    df_ana = _to_df(pst_rows, {
        "experiment_id": "experiment_id",
        "reading_date":  "reading_date",
        "inf_cod":       "cod_mgl",
        "inf_nh4":       "nh4_mgl",
        "inf_tp":        "tp_mgl",
    })
    # tp_mgl may be NULL in early data (pre-migration v1)
    df_ana["inf_tp"] = df_ana["inf_tp"].fillna(0.0)

    df_flow = _to_df(flow_rows, {
        "experiment_id":   "experiment_id",
        "reading_date":    "reading_date",
        "q_in_mlh":        "q_in_mlh",
        "q_was_mlh":       "q_was_mlh",
        "ras_ratio":       "ras_ratio",
    })

    # INNER JOIN — all four must be present on the same day for a valid training row
    df = (df_aer
          .merge(df_eff,  on=["experiment_id", "reading_date"], how="inner")
          .merge(df_ana,  on=["experiment_id", "reading_date"], how="inner")
          .merge(df_flow, on=["experiment_id", "reading_date"], how="inner"))

    if df.empty:
        return df

    # Derived features
    df["srt_days"] = df.apply(
        lambda r: calc_actual_srt(r["mlss_mgl"], r["q_was_mlh"]), axis=1
    )
    # q_was = 0 means SRT is unconstrained — unreliable training row, drop it
    df = df[df["srt_days"] > 0]

    # Targets computed from actual measurements
    df["cod_removal_pct"] = df.apply(
        lambda r: calc_removal_pct(r["inf_cod"], r["eff_cod"]), axis=1
    )
    df["nh4_removal_pct"] = df.apply(
        lambda r: calc_removal_pct(r["inf_nh4"], r["eff_nh4"]), axis=1
    )
    df["tp_removal_pct"] = df.apply(
        lambda r: calc_removal_pct(r["inf_tp"], r["eff_tp"]), axis=1
    )

    required = MAIN_FEATURE_COLS + ["cod_removal_pct", "nh4_removal_pct", "tp_removal_pct"]
    df = df.dropna(subset=required)

    return df.reset_index(drop=True)


def get_pfas_training_data(session) -> pd.DataFrame:
    """
    Build the PFAS training DataFrame from CECReading (SP1 + SP4) joined
    to the main operational feature set.

    Returns a clean DataFrame with PFAS_FEATURE_COLS and pfas_removal_pct.
    Empty DataFrame when insufficient paired readings exist.
    """
    sp1_rows = (session.query(CECReading)
                .filter(CECReading.sampling_point == "SP1_influent").all())
    sp4_rows = (session.query(CECReading)
                .filter(CECReading.sampling_point == "SP4_effluent").all())

    if not sp1_rows or not sp4_rows:
        return pd.DataFrame()

    def _cec_df(rows, suffix: str) -> pd.DataFrame:
        return pd.DataFrame([{
            "experiment_id":          r.experiment_id,
            "reading_date":           r.reading_date,
            "cec_name":               r.cec_name,
            f"concentration{suffix}": r.concentration,
            f"below_detection{suffix}": r.below_detection,
            f"detection_limit{suffix}": r.detection_limit,
            f"cec_type{suffix}":       r.cec_type,
        } for r in rows])

    df_sp1 = _cec_df(sp1_rows, "_in")
    df_sp4 = _cec_df(sp4_rows, "_eff")

    df_cec = df_sp1.merge(
        df_sp4, on=["experiment_id", "reading_date", "cec_name"], how="inner"
    )
    if df_cec.empty:
        return df_cec

    # Drop rows where influent is below detection (removal % meaningless)
    df_cec = df_cec[df_cec["below_detection_in"] != True]

    # Effluent below detection → use half the detection limit (censored-data convention)
    mask_bdl = df_cec["below_detection_eff"] == True
    if mask_bdl.any():
        df_cec.loc[mask_bdl, "concentration_eff"] = (
            df_cec.loc[mask_bdl, "detection_limit_eff"].fillna(0.0) / 2.0
        )

    df_cec["pfas_type_encoded"] = (df_cec["cec_type_in"] == "long-chain").astype(int)
    df_cec["pfas_removal_pct"] = df_cec.apply(
        lambda r: calc_removal_pct(r["concentration_in"], r["concentration_eff"]), axis=1
    )
    df_cec["inf_pfas"] = df_cec["concentration_in"]

    # Pull operational features from the main training set
    ops_df = get_training_data(session)
    if ops_df.empty:
        return pd.DataFrame()

    ops_cols = ["experiment_id", "reading_date"] + [
        c for c in PFAS_FEATURE_COLS if c not in ("inf_pfas", "pfas_type_encoded")
    ]
    df_pfas = df_cec.merge(
        ops_df[ops_cols], on=["experiment_id", "reading_date"], how="inner"
    )

    required = PFAS_FEATURE_COLS + ["pfas_removal_pct"]
    df_pfas = df_pfas.dropna(subset=required)

    return df_pfas.reset_index(drop=True)


# ──────────────────────────────────────────────────────────────────────────────
# Model status
# ──────────────────────────────────────────────────────────────────────────────

def get_model_status() -> dict:
    """
    Return the current Phase 2 model status read from metadata.json.

    Always returns a dict with all expected keys — never raises.
    """
    defaults = {
        "main_trained":        False,
        "pfas_trained":        False,
        "n_samples_main":      0,
        "n_samples_pfas":      0,
        "last_trained":        None,
        "r2_cod":              None,
        "r2_nh4":              None,
        "r2_tp":               None,
        "r2_pfas":             None,
        "cv_r2_mean":          None,
        "feature_importances": None,
        "pfas_importances":    None,
    }
    if not METADATA_PATH.exists():
        return defaults
    try:
        data = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
        return {**defaults, **data}
    except Exception:
        return defaults


# ──────────────────────────────────────────────────────────────────────────────
# Training
# ──────────────────────────────────────────────────────────────────────────────

def train_phase2(session) -> dict:
    """
    Train Phase 2 Random Forest models on all available lab data.

    Returns a result dict with keys:
      status          "ok" | "insufficient_data" | "error"
      message         human-readable explanation
      n_samples_main  number of training rows for the main model
      n_samples_pfas  number of training rows for the PFAS model
      main_trained    bool
      pfas_trained    bool
      r2_cod / r2_nh4 / r2_tp / r2_pfas  in-sample R² (float | None)
      cv_r2_mean      cross-validated R² mean for the main model (float | None)
      last_trained    ISO datetime string
    """
    result = {
        "status":              "ok",
        "message":             "",
        "n_samples_main":      0,
        "n_samples_pfas":      0,
        "main_trained":        False,
        "pfas_trained":        False,
        "r2_cod":              None,
        "r2_nh4":              None,
        "r2_tp":               None,
        "r2_pfas":             None,
        "cv_r2_mean":          None,
        "feature_importances": None,   # {"cod": {feat: imp, ...}, "nh4": ..., "tp": ...}
        "pfas_importances":    None,   # {feat: imp, ...}
        "last_trained":        datetime.utcnow().isoformat(),
    }

    try:
        df      = get_training_data(session)
        df_pfas = get_pfas_training_data(session)

        result["n_samples_main"] = len(df)
        result["n_samples_pfas"] = len(df_pfas)

        if len(df) < MAIN_MODEL_THRESHOLD:
            result["status"]  = "insufficient_data"
            result["message"] = (
                f"Need {MAIN_MODEL_THRESHOLD} complete daily rows, "
                f"have {len(df)}."
            )
            return result

        MODELS_DIR.mkdir(parents=True, exist_ok=True)

        # ── Main model (COD / NH4 / TP) ────────────────────────────────────────
        X = df[MAIN_FEATURE_COLS].values
        y = df[["cod_removal_pct", "nh4_removal_pct", "tp_removal_pct"]].values

        base_rf = RandomForestRegressor(
            n_estimators=200,
            min_samples_leaf=2,
            random_state=42,
        )
        main_model = Pipeline([
            ("scaler", StandardScaler()),
            ("rf", MultiOutputRegressor(base_rf)),
        ])

        # Cross-validate when there are enough samples for at least 2 folds of ≥10 each
        n_splits = min(5, len(df) // 10)
        if n_splits >= 2:
            cv = KFold(n_splits=n_splits, shuffle=True, random_state=42)
            cv_scores = cross_val_score(main_model, X, y, cv=cv, scoring="r2")
            result["cv_r2_mean"] = float(cv_scores.mean())

        # Fit on full dataset after CV
        main_model.fit(X, y)

        y_pred = main_model.predict(X)
        result["r2_cod"] = float(r2_score(y[:, 0], y_pred[:, 0]))
        result["r2_nh4"] = float(r2_score(y[:, 1], y_pred[:, 1]))
        result["r2_tp"]  = float(r2_score(y[:, 2], y_pred[:, 2]))

        # ── Feature importances (per target) ─────────────────────────────────────
        multi_rf = main_model.named_steps["rf"]
        importances = {}
        for target, estimator in zip(["cod", "nh4", "tp"], multi_rf.estimators_):
            importances[target] = dict(
                zip(MAIN_FEATURE_COLS, [round(v, 6) for v in estimator.feature_importances_])
            )
        result["feature_importances"] = importances
        joblib.dump(main_model, MAIN_MODEL_PATH)
        result["main_trained"] = True

        # ── PFAS model (independent, lower threshold) ──────────────────────────
        if len(df_pfas) >= PFAS_MODEL_THRESHOLD:
            X_p = df_pfas[PFAS_FEATURE_COLS].values
            y_p = df_pfas["pfas_removal_pct"].values

            pfas_model = Pipeline([
                ("scaler", StandardScaler()),
                ("rf", RandomForestRegressor(
                    n_estimators=200,
                    min_samples_leaf=2,
                    random_state=42,
                )),
            ])
            pfas_model.fit(X_p, y_p)
            result["r2_pfas"] = float(r2_score(y_p, pfas_model.predict(X_p)))

            # Feature importances for PFAS model
            result["pfas_importances"] = dict(
                zip(PFAS_FEATURE_COLS,
                    [round(v, 6) for v in pfas_model.named_steps["rf"].feature_importances_])
            )

            joblib.dump(pfas_model, PFAS_MODEL_PATH)
            result["pfas_trained"] = True

        # ── Persist metadata ───────────────────────────────────────────────────
        metadata = {k: v for k, v in result.items() if k != "message"}
        METADATA_PATH.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    except Exception as exc:
        result["status"]  = "error"
        result["message"] = str(exc)

    return result


# ──────────────────────────────────────────────────────────────────────────────
# Inference
# ──────────────────────────────────────────────────────────────────────────────

def _load_main_model():
    global _main_model_cache
    if _main_model_cache is None and MAIN_MODEL_PATH.exists():
        try:
            _main_model_cache = joblib.load(MAIN_MODEL_PATH)
        except Exception:
            # Stale model — likely a scikit-learn version mismatch after an app
            # update.  Remove the file so the status card shows "not trained"
            # and prompts the researcher to retrain rather than crashing.
            MAIN_MODEL_PATH.unlink(missing_ok=True)
            METADATA_PATH.unlink(missing_ok=True)
    return _main_model_cache


def _load_pfas_model():
    global _pfas_model_cache
    if _pfas_model_cache is None and PFAS_MODEL_PATH.exists():
        try:
            _pfas_model_cache = joblib.load(PFAS_MODEL_PATH)
        except Exception:
            PFAS_MODEL_PATH.unlink(missing_ok=True)
    return _pfas_model_cache


def run_phase2(inputs: SimInputs) -> SimOutputs:
    """
    Run Phase 2 predictions.  Falls back to Phase 1 equations for any target
    whose model has not been trained yet.

    Never raises — callers always receive a valid SimOutputs.
    """
    warnings_out: list[str] = []

    # ── Shared intermediates (identical arithmetic to Phase 1) ────────────────
    THETA = 1.06
    q_l_per_day = inputs.flow_rate_mlh * 24 / 1000
    hrt_days    = REACTOR_VOLUME_L / q_l_per_day if q_l_per_day > 0 else 0.0
    temp_factor = THETA ** (inputs.temp_c - 20.0)

    mlvss    = inputs.mlss_mgl * 0.80
    cod_load = inputs.inf_cod * q_l_per_day
    biomass  = mlvss * AERATION_VOLUME_L
    fm_ratio = cod_load / biomass if biomass > 0 else 0.0

    nitrifier_min_srt = (3.0 * (1.123 ** (15.0 - inputs.temp_c))
                         if inputs.temp_c < 15 else 5.0)

    from simulation.generic_model import get_kd
    kd = get_kd(inputs.pfas_compound, inputs.pfas_type)

    # ── Main model (COD / NH4 / TP) ───────────────────────────────────────────
    main_model = _load_main_model()
    if main_model is not None:
        X = np.array([[
            inputs.flow_rate_mlh,
            inputs.ras_ratio,
            inputs.do_mgl,
            inputs.srt_days,
            inputs.temp_c,
            inputs.ph,
            inputs.mlss_mgl,
            inputs.inf_cod,
            inputs.inf_nh4,
            inputs.inf_tp,
        ]])
        pred = main_model.predict(X)[0]
        cod_removal_pct = float(np.clip(pred[0], 0.0, 100.0))
        nh4_removal_pct = float(np.clip(pred[1], 0.0, 100.0))
        tp_removal_pct  = float(np.clip(pred[2], 0.0, 100.0))

        # ── 90% prediction intervals from RF tree variance ────────────────────
        # Each estimator in MultiOutputRegressor is a separate RF (one per target).
        # We collect per-tree predictions to get the 5th/95th percentile interval.
        try:
            scaler   = main_model.named_steps["scaler"]
            multi_rf = main_model.named_steps["rf"]
            X_scaled = scaler.transform(X)
            cod_ci = nh4_ci = tp_ci = None
            for i, (target_ci_name, estimator) in enumerate(
                zip(["cod", "nh4", "tp"], multi_rf.estimators_)
            ):
                tree_preds = np.array(
                    [tree.predict(X_scaled)[0] for tree in estimator.estimators_]
                )
                low  = float(np.clip(np.percentile(tree_preds,  5), 0.0, 100.0))
                high = float(np.clip(np.percentile(tree_preds, 95), 0.0, 100.0))
                if i == 0:   cod_ci = (low, high)
                elif i == 1: nh4_ci = (low, high)
                else:        tp_ci  = (low, high)
        except Exception:
            cod_ci = nh4_ci = tp_ci = None
    else:
        p1 = run_phase1(inputs)
        cod_removal_pct = p1.cod_removal_pct
        nh4_removal_pct = p1.nh4_removal_pct
        tp_removal_pct  = p1.tp_removal_pct
        cod_ci = nh4_ci = tp_ci = None
        warnings_out.append(
            "Phase 2 main model not trained — COD/NH₄/TP from Phase 1 equations."
        )

    # ── PFAS model ────────────────────────────────────────────────────────────
    pfas_model = _load_pfas_model()
    if pfas_model is not None:
        X_p = np.array([[
            inputs.flow_rate_mlh,
            inputs.ras_ratio,
            inputs.do_mgl,
            inputs.srt_days,
            inputs.temp_c,
            inputs.ph,
            inputs.mlss_mgl,
            inputs.inf_pfas,
            1 if inputs.pfas_type == "long-chain" else 0,
        ]])
        pfas_removal_pct = float(np.clip(pfas_model.predict(X_p)[0], 0.0, 100.0))
        # ── PFAS 90% prediction interval ─────────────────────────────────────
        try:
            X_p_scaled      = pfas_model.named_steps["scaler"].transform(X_p)
            pfas_rf         = pfas_model.named_steps["rf"]
            pfas_tree_preds = np.array(
                [tree.predict(X_p_scaled)[0] for tree in pfas_rf.estimators_]
            )
            pfas_ci = (
                float(np.clip(np.percentile(pfas_tree_preds,  5), 0.0, 100.0)),
                float(np.clip(np.percentile(pfas_tree_preds, 95), 0.0, 100.0)),
            )
        except Exception:
            pfas_ci = None
    else:
        p1 = run_phase1(inputs)
        pfas_removal_pct = p1.pfas_removal_pct
        pfas_ci = None
        warnings_out.append(
            "Phase 2 PFAS model not trained — PFAS prediction from Phase 1 equations."
        )

    eff_cod  = max(0.0, inputs.inf_cod  * (1.0 - cod_removal_pct  / 100.0))
    eff_nh4  = max(0.0, inputs.inf_nh4  * (1.0 - nh4_removal_pct  / 100.0))
    eff_tp   = max(0.0, inputs.inf_tp   * (1.0 - tp_removal_pct   / 100.0))
    eff_pfas = max(0.0, inputs.inf_pfas * (1.0 - pfas_removal_pct / 100.0))

    alk_consumed_mgl = inputs.inf_nh4 * (nh4_removal_pct / 100.0) * 7.14

    return SimOutputs(
        cod_removal_pct   = cod_removal_pct,
        nh4_removal_pct   = nh4_removal_pct,
        tp_removal_pct    = tp_removal_pct,
        pfas_removal_pct  = pfas_removal_pct,
        eff_cod           = eff_cod,
        eff_nh4           = eff_nh4,
        eff_tp            = eff_tp,
        eff_pfas          = eff_pfas,
        hrt_days          = hrt_days,
        kd_used           = kd,
        temp_factor       = temp_factor,
        fm_ratio          = fm_ratio,
        nitrifier_min_srt = nitrifier_min_srt,
        alk_consumed_mgl  = alk_consumed_mgl,
        warnings          = warnings_out,
        cod_ci            = cod_ci,
        nh4_ci            = nh4_ci,
        tp_ci             = tp_ci,
        pfas_ci           = pfas_ci,
    )
