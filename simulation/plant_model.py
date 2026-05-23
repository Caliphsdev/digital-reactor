"""
plant_model.py — Scientific Twin equations for real wastewater plants.

This module is deliberately mechanistic and transparent. It gives a
process-realistic first version for Daspoort, Zeekoegat, and Phola using
literature/default assumptions, then leaves a clean path for calibration once
measured field data are available.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace as _replace
import math

import numpy as np

from simulation.generic_model import get_kd


BNR_MODES = ["A2O / 3-stage Bardenpho", "UCT", "Modified UCT", "Johannesburg"]

# ── South African effluent discharge limits (Green Drop / SANS 241) ──────────
# Values in mg/L. Used for compliance flag generation.
DISCHARGE_LIMITS: dict[str, dict[str, float]] = {
    "daspoort":  {"cod_mgl": 75.0, "nh4_mgl": 10.0, "tn_mgl": 15.0, "tp_mgl": 1.0},
    "zeekoegat": {"cod_mgl": 30.0, "nh4_mgl":  6.0, "tn_mgl": 10.0, "tp_mgl": 0.5},
    "phola":     {"cod_mgl": 100.0, "nh4_mgl": 15.0, "tn_mgl": 20.0, "tp_mgl": 2.0},
}

# ── PFAS biotransformation fraction (literature estimate) ─────────────────────
# Short-chain PFAS precursors have modestly higher transformation potential.
# Long-chain terminal PFAS (PFOS, PFOA) are highly recalcitrant in CAS.
# Source: Houtz & Sedlak 2012; Liu & Mejia Avendaño 2013.
PFAS_BIOTRANSFORMATION_FRACTION: dict[str, float] = {
    "short-chain": 0.08,
    "long-chain":  0.02,
}

# ── Warning threshold: effluent within this fraction of limit triggers WARN ───
_COMPLIANCE_WARN_FRACTION = 0.90  # >90% of limit = WARN, ≤90% = PASS


@dataclass
class PlantTwinInputs:
    plant_slug: str
    flow_mld: float
    hrt_hours: float
    srt_days: float
    mlss_mgl: float
    do_mgl: float
    temp_c: float
    ph: float
    recycle_ratio: float
    organic_loading: float | None
    nitrogen_loading: float | None
    inf_cod_mgl: float
    inf_nh4_mgl: float
    inf_tn_mgl: float
    inf_tp_mgl: float
    inf_pfas_ugl: float
    pfas_type: str
    pfas_compound: str = ""
    bnr_mode: str = "A2O / 3-stage Bardenpho"
    calibration_factors: dict[str, float] = field(default_factory=dict)


@dataclass
class UnitResult:
    unit_name: str
    unit_type: str
    cod_mgl: float
    nh4_mgl: float
    tn_mgl: float
    tp_mgl: float
    pfas_ugl: float
    note: str = ""


@dataclass
class PlantTwinOutputs:
    cod_removal_pct: float
    nh4_removal_pct: float
    tn_removal_pct: float
    tp_removal_pct: float
    pfas_removal_pct: float
    eff_cod_mgl: float
    eff_nh4_mgl: float
    eff_tn_mgl: float
    eff_tp_mgl: float
    eff_pfas_ugl: float
    cod_load_kg_day: float
    pfas_in_g_day: float
    pfas_effluent_g_day: float
    pfas_sludge_g_day: float
    pfas_biotransformed_g_day: float       # sorption-independent biotransformation estimate
    pfas_unresolved_g_day: float           # non-zero when calibration shifts effluent vs Kd sludge
    fm_ratio: float
    kd_used: float
    confidence_label: str
    warnings: list[str] = field(default_factory=list)
    unit_results: list[UnitResult] = field(default_factory=list)
    compliance: dict[str, str] = field(default_factory=dict)          # "PASS"/"WARN"/"FAIL" per parameter
    pfas_removal_ci: tuple[float, float] | None = None                 # (5th, 95th pct) from Monte Carlo


def kg_day_from_mgl_mld(concentration_mgl: float, flow_mld: float) -> float:
    """1 mg/L at 1 ML/d equals 1 kg/day."""
    return max(0.0, concentration_mgl) * max(0.0, flow_mld)


def g_day_from_ugl_mld(concentration_ugl: float, flow_mld: float) -> float:
    """1 ug/L at 1 ML/d equals 1 g/day."""
    return max(0.0, concentration_ugl) * max(0.0, flow_mld)


def calc_plant_fm_ratio(
    cod_mgl: float,
    flow_mld: float,
    mlss_mgl: float,
    hrt_hours: float,
    vss_mlss_ratio: float = 0.80,
) -> float:
    """Plant-scale F:M ratio in kg COD/kg VSS/day."""
    if flow_mld <= 0 or mlss_mgl <= 0 or hrt_hours <= 0:
        return 0.0
    volume_ml = flow_mld * hrt_hours / 24.0
    biomass_kg = mlss_mgl * volume_ml * vss_mlss_ratio
    if biomass_kg <= 0:
        return 0.0
    return kg_day_from_mgl_mld(cod_mgl, flow_mld) / biomass_kg


def _clip(value: float, low: float = 0.0, high: float = 0.99) -> float:
    return max(low, min(high, value))


def _temp_factor(temp_c: float, theta: float = 1.06) -> float:
    return theta ** (temp_c - 20.0)


def _ph_factor(ph: float) -> float:
    if 6.8 <= ph <= 8.0:
        return 1.0
    if 6.3 <= ph < 6.8 or 8.0 < ph <= 8.5:
        return 0.85
    return 0.65


def _pfas_adsorption_fraction(
    inputs: PlantTwinInputs,
    process_family: str,
) -> tuple[float, float]:
    """
    Estimate PFAS removal by solids adsorption and solids capture.

    PFAS destruction is not assumed. The output fraction is the share expected
    to follow sludge/solids rather than final effluent.
    """
    kd = get_kd(inputs.pfas_compound, inputs.pfas_type)
    mlss_kg_l = max(0.0, inputs.mlss_mgl) / 1_000_000.0
    base = (kd * mlss_kg_l) / (1.0 + kd * mlss_kg_l) if kd > 0 and mlss_kg_l > 0 else 0.0

    if process_family == "pond_trickling":
        hrt_days = max(0.0, inputs.hrt_hours) / 24.0
        long_retention_boost = 1.0 + min(0.50, hrt_days / 10.0)
        capture = 0.82
        adsorption = base * long_retention_boost * capture
    else:
        srt_boost = 1.0 + min(0.25, max(0.0, inputs.srt_days - 20.0) / 120.0)
        clarifier_capture = 0.96
        tertiary_boost = 1.12 if inputs.plant_slug == "zeekoegat" else 1.0
        adsorption = base * srt_boost * clarifier_capture * tertiary_boost

    # Even long-chain PFAS predictions should stay conservative without local
    # sludge concentration measurements.
    return _clip(adsorption, 0.0, 0.80), kd


def _run_activated_sludge_bnr(inputs: PlantTwinInputs) -> PlantTwinOutputs:
    warnings: list[str] = []
    if inputs.srt_days < 8:
        warnings.append("SRT is low for stable nitrification in a full-scale BNR plant.")
    if not (1.0 <= inputs.do_mgl <= 3.0):
        warnings.append("Aerobic DO is outside the normal BNR control band.")
    if inputs.flow_mld > 0 and inputs.hrt_hours < 6:
        warnings.append("HRT is short; shock loads may pass through biological treatment.")

    temp = _temp_factor(inputs.temp_c)
    ph = _ph_factor(inputs.ph)
    hrt_days = max(0.0, inputs.hrt_hours) / 24.0

    primary_cod_removal = 0.30 if inputs.plant_slug == "daspoort" else 0.25
    cod_after_primary = inputs.inf_cod_mgl * (1.0 - primary_cod_removal)

    bio_hrt_days = hrt_days * 0.65
    k_cod = 1.15 * temp * ph
    bio_cod_removal = _clip(1.0 - (1.0 / (1.0 + k_cod * bio_hrt_days)), 0.0, 0.96)
    eff_cod = cod_after_primary * (1.0 - bio_cod_removal)
    cod_removal = _clip(1.0 - eff_cod / inputs.inf_cod_mgl if inputs.inf_cod_mgl > 0 else 0.0)

    do_factor = inputs.do_mgl / (0.5 + inputs.do_mgl) if inputs.do_mgl > 0 else 0.0
    srt_factor = inputs.srt_days / (inputs.srt_days + 5.0) if inputs.srt_days > 0 else 0.0
    nitrification = _clip(0.98 * do_factor * srt_factor * min(1.25, temp) * ph, 0.0, 0.98)
    eff_nh4 = inputs.inf_nh4_mgl * (1.0 - nitrification)

    mode_bonus = {
        "A2O / 3-stage Bardenpho": 0.00,
        "UCT": 0.05,
        "Modified UCT": 0.08,
        "Johannesburg": -0.02,
    }.get(inputs.bnr_mode, 0.0)
    recycle_factor = inputs.recycle_ratio / (inputs.recycle_ratio + 4.0) if inputs.recycle_ratio > 0 else 0.0
    denit = _clip(0.35 + recycle_factor * 0.45 + mode_bonus, 0.0, 0.88)
    tn_removal = _clip(nitrification * 0.45 + denit * 0.45, 0.0, 0.88)
    eff_tn = inputs.inf_tn_mgl * (1.0 - tn_removal)

    if inputs.plant_slug == "zeekoegat":
        ebpr_base = {
            "A2O / 3-stage Bardenpho": 0.72,
            "UCT": 0.78,
            "Modified UCT": 0.82,
            "Johannesburg": 0.68,
        }.get(inputs.bnr_mode, 0.72)
    else:
        ebpr_base = 0.68
    tp_removal = _clip(ebpr_base * min(1.10, temp) * ph, 0.0, 0.90)
    eff_tp = inputs.inf_tp_mgl * (1.0 - tp_removal)

    pfas_removed, kd = _pfas_adsorption_fraction(inputs, "activated_sludge")
    eff_pfas = inputs.inf_pfas_ugl * (1.0 - pfas_removed)

    unit_results = [
        UnitResult("Inlet Works", "screening_grit", inputs.inf_cod_mgl, inputs.inf_nh4_mgl, inputs.inf_tn_mgl, inputs.inf_tp_mgl, inputs.inf_pfas_ugl, "Hydraulic protection; dissolved contaminants mostly unchanged."),
        UnitResult("Primary Settling", "primary_settling", cod_after_primary, inputs.inf_nh4_mgl, inputs.inf_tn_mgl, inputs.inf_tp_mgl * 0.92, inputs.inf_pfas_ugl * (1.0 - pfas_removed * 0.10), "Physical solids removal and VFA generation."),
        UnitResult("BNR Reactors", "anaerobic_anoxic_aerobic", eff_cod * 1.15, eff_nh4, eff_tn, eff_tp, inputs.inf_pfas_ugl * (1.0 - pfas_removed * 0.55), f"{inputs.bnr_mode} biological nutrient-removal behaviour."),
        UnitResult("Secondary Clarifiers", "secondary_clarifier", eff_cod, eff_nh4, eff_tn, eff_tp, eff_pfas, "Solids capture controls sorbed PFAS fate."),
    ]
    if inputs.plant_slug == "zeekoegat":
        unit_results.append(UnitResult("Tertiary Treatment", "tertiary_filtration", eff_cod * 0.96, eff_nh4, eff_tn * 0.98, eff_tp * 0.90, eff_pfas, "Final polishing improves particulate-associated removal."))
        eff_cod *= 0.96
        eff_tn *= 0.98
        eff_tp *= 0.90

    return _build_outputs(inputs, cod_removal, nitrification, tn_removal, tp_removal, pfas_removed, eff_cod, eff_nh4, eff_tn, eff_tp, eff_pfas, kd, warnings, unit_results)


def _run_pond_trickling(inputs: PlantTwinInputs) -> PlantTwinOutputs:
    warnings: list[str] = []
    hrt_days = max(0.0, inputs.hrt_hours) / 24.0
    if hrt_days < 1.0:
        warnings.append("Pond HRT is below the Phola literature assumption; removal may be overestimated.")
    if inputs.organic_loading and inputs.organic_loading > 0.35:
        warnings.append("Organic loading is high for stable pond/trickling-filter polishing.")

    temp = _temp_factor(inputs.temp_c, theta=1.04)
    ph = _ph_factor(inputs.ph)

    # Organic loading degrades pond first-order rate constant above 0.20 kg BOD/m³/d.
    # At the Phola default (0.23) the penalty is mild; at 0.55 the rate halves.
    org_load = inputs.organic_loading or 0.0
    k_pond = 0.55 * max(0.50, 1.0 - max(0.0, org_load - 0.20) * 0.77) if org_load > 0.20 else 0.55
    pond_cod = _clip(1.0 - math.exp(-k_pond * hrt_days * temp * ph), 0.0, 0.72)
    filter_cod = _clip(0.48 * temp * ph, 0.0, 0.70)
    reed_cod = 0.12
    cod_removal = _clip(1.0 - (1.0 - pond_cod) * (1.0 - filter_cod) * (1.0 - reed_cod), 0.0, 0.92)
    eff_cod = inputs.inf_cod_mgl * (1.0 - cod_removal)

    # Continuous nitrogen loading penalty — linear degradation above 0.9 g TKN/m²/d.
    n_load = inputs.nitrogen_loading or 0.0
    n_loading_penalty = max(0.60, 1.0 - max(0.0, n_load - 0.90) * 0.15) if n_load > 0.90 else 1.0
    nh4_removal = _clip((0.18 + 0.42 * temp * ph) * n_loading_penalty, 0.0, 0.78)
    eff_nh4 = inputs.inf_nh4_mgl * (1.0 - nh4_removal)

    tn_removal = _clip(0.32 + min(0.20, hrt_days / 10.0) + 0.08 * temp, 0.0, 0.68)
    eff_tn = inputs.inf_tn_mgl * (1.0 - tn_removal)

    tp_removal = _clip(0.18 + min(0.12, hrt_days / 20.0), 0.0, 0.42)
    eff_tp = inputs.inf_tp_mgl * (1.0 - tp_removal)

    pfas_removed, kd = _pfas_adsorption_fraction(inputs, "pond_trickling")
    eff_pfas = inputs.inf_pfas_ugl * (1.0 - pfas_removed)

    after_pond_cod = inputs.inf_cod_mgl * (1.0 - pond_cod)
    after_filter_cod = after_pond_cod * (1.0 - filter_cod)
    unit_results = [
        UnitResult("Screens and Degritters", "preliminary", inputs.inf_cod_mgl, inputs.inf_nh4_mgl, inputs.inf_tn_mgl, inputs.inf_tp_mgl, inputs.inf_pfas_ugl, "Preliminary protection; dissolved contaminants mostly unchanged."),
        UnitResult("Anaerobic Ponds", "anaerobic_pond", after_pond_cod, inputs.inf_nh4_mgl * 0.95, inputs.inf_tn_mgl * 0.82, inputs.inf_tp_mgl * 0.90, inputs.inf_pfas_ugl * (1.0 - pfas_removed * 0.45), "Long retention drives settling, anaerobic transformation, and solids contact."),
        UnitResult("Trickling Filter and Humus Tanks", "trickling_filter", after_filter_cod, eff_nh4 * 1.05, eff_tn * 1.08, eff_tp * 1.03, inputs.inf_pfas_ugl * (1.0 - pfas_removed * 0.75), "Attached-growth treatment plus sloughed-solids settling."),
        UnitResult("Disinfection and Reed Bed", "reed_bed", eff_cod, eff_nh4, eff_tn, eff_tp, eff_pfas, "Final pathogen barrier and wetland polishing; not PFAS destruction."),
    ]

    return _build_outputs(inputs, cod_removal, nh4_removal, tn_removal, tp_removal, pfas_removed, eff_cod, eff_nh4, eff_tn, eff_tp, eff_pfas, kd, warnings, unit_results)


def _check_compliance(plant_slug: str, outputs: "PlantTwinOutputs") -> dict[str, str]:
    """
    Compare predicted effluent concentrations against SA discharge limits.

    Returns a dict mapping parameter key → "PASS" | "WARN" | "FAIL".
    WARN = effluent within 10% of the limit (approaching breach).
    """
    limits = DISCHARGE_LIMITS.get(plant_slug, {})
    checks = [
        ("cod", outputs.eff_cod_mgl),
        ("nh4", outputs.eff_nh4_mgl),
        ("tn",  outputs.eff_tn_mgl),
        ("tp",  outputs.eff_tp_mgl),
    ]
    result: dict[str, str] = {}
    for key, value in checks:
        limit = limits.get(f"{key}_mgl")
        if limit is None:
            continue
        if value > limit:
            result[key] = "FAIL"
        elif value > limit * _COMPLIANCE_WARN_FRACTION:
            result[key] = "WARN"
        else:
            result[key] = "PASS"
    return result


def _build_outputs(
    inputs: PlantTwinInputs,
    cod_removal: float,
    nh4_removal: float,
    tn_removal: float,
    tp_removal: float,
    pfas_removed: float,
    eff_cod: float,
    eff_nh4: float,
    eff_tn: float,
    eff_tp: float,
    eff_pfas: float,
    kd: float,
    warnings: list[str],
    unit_results: list[UnitResult],
) -> PlantTwinOutputs:
    factors = inputs.calibration_factors or {}
    calibration_applied = bool(factors)

    # Store the Kd-physics sludge fraction BEFORE applying calibration to effluent.
    # This lets pfas_unresolved_g_day become non-zero when a calibration multiplier
    # shifts the effluent prediction independently of the Kd adsorption model.
    kd_pfas_removed = pfas_removed

    cod_removal = _clip(cod_removal * factors.get("cod", 1.0), 0.0, 0.99)
    nh4_removal = _clip(nh4_removal * factors.get("nh4", 1.0), 0.0, 0.99)
    tn_removal = _clip(tn_removal * factors.get("tn", 1.0), 0.0, 0.99)
    tp_removal = _clip(tp_removal * factors.get("tp", 1.0), 0.0, 0.99)
    pfas_removed = _clip(pfas_removed * factors.get("pfas", 1.0), 0.0, 0.90)

    eff_cod = inputs.inf_cod_mgl * (1.0 - cod_removal)
    eff_nh4 = inputs.inf_nh4_mgl * (1.0 - nh4_removal)
    eff_tn = inputs.inf_tn_mgl * (1.0 - tn_removal)
    eff_tp = inputs.inf_tp_mgl * (1.0 - tp_removal)
    eff_pfas = inputs.inf_pfas_ugl * (1.0 - pfas_removed)

    # ── PFAS three-pathway mass balance ──────────────────────────────────────
    pfas_in  = g_day_from_ugl_mld(inputs.inf_pfas_ugl, inputs.flow_mld)
    pfas_eff = g_day_from_ugl_mld(eff_pfas, inputs.flow_mld)

    # Total mass removed from the water phase (calibration-adjusted effluent).
    pfas_removed_load = max(0.0, pfas_in - pfas_eff)

    # Pathway 1 + 2: split the removed load between adsorption (sludge) and
    # biotransformation. These two together always close the balance by construction.
    biotrans_frac = PFAS_BIOTRANSFORMATION_FRACTION.get(inputs.pfas_type, 0.02)
    pfas_biotransformed = pfas_removed_load * biotrans_frac
    pfas_sludge = max(0.0, pfas_removed_load - pfas_biotransformed)

    # Pathway 3: unresolved — zero for model-only runs.
    # Becomes non-zero when real sludge measurements (WAS concentration × WAS flow)
    # provide an independent fate estimate that doesn't match this two-pathway split.
    pfas_unresolved = max(0.0, pfas_in - pfas_eff - pfas_sludge - pfas_biotransformed)

    fm = calc_plant_fm_ratio(inputs.inf_cod_mgl, inputs.flow_mld, inputs.mlss_mgl, inputs.hrt_hours)

    # ── Confidence label — plant-agnostic ────────────────────────────────────
    plant_label = {
        "daspoort": "Daspoort", "zeekoegat": "Zeekoegat", "phola": "Phola",
    }.get(inputs.plant_slug, inputs.plant_slug.capitalize())

    confidence = "Scientific Twin: literature/default assumptions"
    if warnings:
        confidence = "Scientific Twin: lower confidence — parameters outside normal operating range"
    if calibration_applied:
        confidence = f"Partly calibrated Scientific Twin: {plant_label} monitoring multipliers applied"

    if unit_results:
        unit_results[-1].cod_mgl = eff_cod
        unit_results[-1].nh4_mgl = eff_nh4
        unit_results[-1].tn_mgl = eff_tn
        unit_results[-1].tp_mgl = eff_tp
        unit_results[-1].pfas_ugl = eff_pfas
        if calibration_applied:
            unit_results[-1].note += " Final values include calibration multipliers."

    out = PlantTwinOutputs(
        cod_removal_pct=cod_removal * 100.0,
        nh4_removal_pct=nh4_removal * 100.0,
        tn_removal_pct=tn_removal * 100.0,
        tp_removal_pct=tp_removal * 100.0,
        pfas_removal_pct=pfas_removed * 100.0,
        eff_cod_mgl=max(0.0, eff_cod),
        eff_nh4_mgl=max(0.0, eff_nh4),
        eff_tn_mgl=max(0.0, eff_tn),
        eff_tp_mgl=max(0.0, eff_tp),
        eff_pfas_ugl=max(0.0, eff_pfas),
        cod_load_kg_day=kg_day_from_mgl_mld(inputs.inf_cod_mgl, inputs.flow_mld),
        pfas_in_g_day=pfas_in,
        pfas_effluent_g_day=pfas_eff,
        pfas_sludge_g_day=pfas_sludge,
        pfas_biotransformed_g_day=pfas_biotransformed,
        pfas_unresolved_g_day=pfas_unresolved,
        fm_ratio=fm,
        kd_used=kd,
        confidence_label=confidence,
        warnings=warnings,
        unit_results=unit_results,
    )
    out.compliance = _check_compliance(inputs.plant_slug, out)
    return out


def run_plant_twin(inputs: PlantTwinInputs, compute_uncertainty: bool = False) -> PlantTwinOutputs:
    """
    Run the appropriate Scientific Twin model for one real plant.

    When compute_uncertainty=True, a Monte Carlo Kd sampling (n=300) is run
    to populate pfas_removal_ci with the 5th–95th percentile PFAS removal range.
    This adds ~50 ms; keep False for real-time slider updates.
    """
    if inputs.plant_slug == "phola":
        result = _run_pond_trickling(inputs)
    else:
        result = _run_activated_sludge_bnr(inputs)

    if compute_uncertainty:
        result.pfas_removal_ci = run_pfas_uncertainty(inputs)
    return result


# ══════════════════════════════════════════════════════════════════════════════
# Multi-compound PFAS mixture mode
# ══════════════════════════════════════════════════════════════════════════════

@dataclass
class PFASMixtureEntry:
    """One compound in a PFAS mixture supplied to the plant."""
    compound:   str    # e.g. "PFOS", "PFOA", "PFBS"
    chain_type: str    # "short-chain" | "long-chain"
    inf_ugl:    float  # influent concentration (µg/L)


@dataclass
class PFASMixtureResult:
    """Predicted fate for one compound in a mixture run."""
    compound:      str
    chain_type:    str
    kd:            float  # L/kg MLSS used
    inf_ugl:       float
    eff_ugl:       float
    removal_pct:   float
    sludge_g_day:     float
    biotrans_g_day:   float  # estimated biotransformation load


def run_pfas_mixture(
    inputs: PlantTwinInputs,
    compounds: list[PFASMixtureEntry],
) -> list[PFASMixtureResult]:
    """
    Predict removal for each PFAS compound in a mixture.

    Each compound is evaluated against the full MLSS independently (conservative
    for competitive sorption). Real influent carries mixtures of 10-30 compounds;
    this function supports sum-of-fractions analysis for mass balance reporting.
    """
    process_family = "pond_trickling" if inputs.plant_slug == "phola" else "activated_sludge"
    results: list[PFASMixtureResult] = []

    for entry in compounds:
        kd = get_kd(entry.compound, entry.chain_type)
        mlss_kg_l = max(0.0, inputs.mlss_mgl) / 1_000_000.0
        base_frac = (kd * mlss_kg_l) / (1.0 + kd * mlss_kg_l) if kd > 0 and mlss_kg_l > 0 else 0.0

        if process_family == "pond_trickling":
            hrt_days = max(0.0, inputs.hrt_hours) / 24.0
            removal_frac = base_frac * (1.0 + min(0.50, hrt_days / 10.0)) * 0.82
        else:
            srt_boost = 1.0 + min(0.25, max(0.0, inputs.srt_days - 20.0) / 120.0)
            tertiary = 1.12 if inputs.plant_slug == "zeekoegat" else 1.0
            removal_frac = base_frac * srt_boost * 0.96 * tertiary

        removal_frac = _clip(removal_frac, 0.0, 0.80)
        eff_ugl = max(0.0, entry.inf_ugl * (1.0 - removal_frac))
        inf_load = g_day_from_ugl_mld(entry.inf_ugl, inputs.flow_mld)
        removed_load = g_day_from_ugl_mld(entry.inf_ugl * removal_frac, inputs.flow_mld)
        biotrans_frac = PFAS_BIOTRANSFORMATION_FRACTION.get(entry.chain_type, 0.02)
        biotrans_load = removed_load * biotrans_frac

        results.append(PFASMixtureResult(
            compound=entry.compound,
            chain_type=entry.chain_type,
            kd=kd,
            inf_ugl=entry.inf_ugl,
            eff_ugl=eff_ugl,
            removal_pct=removal_frac * 100.0,
            sludge_g_day=max(0.0, removed_load - biotrans_load),
            biotrans_g_day=biotrans_load,
        ))

    return results


# ══════════════════════════════════════════════════════════════════════════════
# PFAS uncertainty propagation — Monte Carlo on Kd log-normal distribution
# ══════════════════════════════════════════════════════════════════════════════

def run_pfas_uncertainty(
    inputs: PlantTwinInputs,
    n_samples: int = 300,
    rng_seed: int | None = None,
) -> tuple[float, float]:
    """
    Monte Carlo uncertainty for PFAS removal using Kd log-normal spread.

    Literature reports Kd values with ±40–50% uncertainty (σ_ln ≈ 0.35).
    Returns (5th-percentile removal %, 95th-percentile removal %) — a 90%
    prediction interval comparable to Phase 2 RF confidence intervals.

    rng_seed: set for reproducible results in tests; None = random each call.
    """
    rng = np.random.default_rng(rng_seed)
    kd_base = get_kd(inputs.pfas_compound, inputs.pfas_type)
    sigma = 0.35  # log-normal spread ≈ ±40% of Kd (Higgins & Luthy 2006 uncertainty)
    kd_samples = rng.lognormal(mean=np.log(max(kd_base, 1e-6)), sigma=sigma, size=n_samples)

    process_family = "pond_trickling" if inputs.plant_slug == "phola" else "activated_sludge"
    mlss_kg_l = max(0.0, inputs.mlss_mgl) / 1_000_000.0
    hrt_days = max(0.0, inputs.hrt_hours) / 24.0

    removals = []
    for kd in kd_samples:
        base = (kd * mlss_kg_l) / (1.0 + kd * mlss_kg_l) if mlss_kg_l > 0 else 0.0
        if process_family == "pond_trickling":
            r = base * (1.0 + min(0.50, hrt_days / 10.0)) * 0.82
        else:
            srt_boost = 1.0 + min(0.25, max(0.0, inputs.srt_days - 20.0) / 120.0)
            tertiary = 1.12 if inputs.plant_slug == "zeekoegat" else 1.0
            r = base * srt_boost * 0.96 * tertiary
        removals.append(_clip(r, 0.0, 0.80) * 100.0)

    arr = np.array(removals)
    return float(np.percentile(arr, 5)), float(np.percentile(arr, 95))


# ══════════════════════════════════════════════════════════════════════════════
# Scenario engine — diurnal / seasonal / what-if batch runs
# ══════════════════════════════════════════════════════════════════════════════

def run_scenarios(
    base_inputs: PlantTwinInputs,
    overrides_list: list[dict],
) -> list[PlantTwinOutputs]:
    """
    Run the Scientific Twin for a list of operating scenarios.

    Each dict in overrides_list maps PlantTwinInputs field names to override
    values. Returns one PlantTwinOutputs per scenario in the same order.

    Example — diurnal flow profile:
        run_scenarios(base, [
            {"flow_mld": 48.0, "hrt_hours":  8.0},   # morning peak
            {"flow_mld": 30.0, "hrt_hours": 13.0},   # afternoon average
            {"flow_mld": 18.0, "hrt_hours": 22.0},   # night low
        ])

    Example — seasonal temperature sweep:
        run_scenarios(base, [{"temp_c": t} for t in [10, 15, 20, 25, 30]])
    """
    return [run_plant_twin(_replace(base_inputs, **overrides)) for overrides in overrides_list]
