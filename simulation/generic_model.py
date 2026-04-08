"""
generic_model.py — Phase 1 generic (textbook) simulation model.

All equations come from 03_EQUATIONS.md (Sekhula-Mojela, 2026).
These are first-order / empirical estimates that give directional
predictions without requiring real training data.

IMPORTANT: Phase 1 values are textbook estimates only.
Phase 2 (data_model.py) will replace these with a scikit-learn
model trained on the researcher's actual lab measurements.
"""

from dataclasses import dataclass


# ── Reactor volume constants (OECD 303A — 3 × 4 L vessels) ───────────────────
REACTOR_VOLUME_L = 12.0   # total active volume (3 zones × 4 L)

# ── Kd values (solid-water partition coefficient, L/kg MLSS) ─────────────────
# Literature values for PFAS adsorption onto activated sludge.
# Short-chain: low Kd  → most stays in water → passes to effluent
# Long-chain:  high Kd → more adsorbs to sludge → less in effluent
KD_SHORT_CHAIN = 0.8    # L/kg  (conservative — e.g. PFBA, PFBS)
KD_LONG_CHAIN  = 4.5    # L/kg  (e.g. PFOS, PFOA)


@dataclass
class SimInputs:
    """All operating parameters fed into the Phase 1 model."""
    flow_rate_mlh:  float   # influent flow (mL/h)
    ras_ratio:      float   # RAS recycle ratio (unitless)
    a_recycle:      float   # a-recycle ratio (unitless)
    do_mgl:         float   # aerobic zone DO (mg/L)
    srt_days:       float   # sludge retention time (days)
    temp_c:         float   # temperature (°C)
    ph:             float   # pH (unitless)
    inf_cod:        float   # influent COD (mg/L)
    inf_nh4:        float   # influent NH4-N (mg/L)
    inf_tp:         float   # influent total phosphorus (mg/L)
    inf_pfas:       float   # influent PFAS concentration (µg/L)
    pfas_type:      str     # "short-chain" | "long-chain"
    mlss_mgl:       float   # mixed liquor SS (mg/L) — for PFAS adsorption


@dataclass
class SimOutputs:
    """Predicted effluent concentrations and removal efficiencies."""
    # Removal percentages (0–100)
    cod_removal_pct:  float
    nh4_removal_pct:  float
    tp_removal_pct:   float
    pfas_removal_pct: float
    # Predicted effluent concentrations
    eff_cod:  float   # mg/L
    eff_nh4:  float   # mg/L
    eff_tp:   float   # mg/L
    eff_pfas: float   # µg/L
    # Intermediate values for display
    hrt_days:   float
    kd_used:    float
    temp_factor: float   # θ^(T-20) applied to all biological rates
    fm_ratio:   float    # predicted F:M ratio (kg COD/kg VSS/day)
    nitrifier_min_srt: float  # minimum SRT for nitrifiers at this temperature (days)
    alk_consumed_mgl: float   # estimated alkalinity consumed by nitrification (mg CaCO3/L)
    warnings: list[str]


def run_phase1(inputs: SimInputs) -> SimOutputs:
    """
    Run the Phase 1 generic model and return predicted outputs.

    All equations are sourced from 03_EQUATIONS.md.
    Warning flags are generated for parameters outside recommended
    operating ranges so the researcher can see risky conditions.
    """
    warnings: list[str] = []

    # ── HRT (Hydraulic Retention Time) ────────────────────────────────────────
    # HRT = V / Q  →  convert mL/h to L/day first
    q_l_per_day = inputs.flow_rate_mlh * 24 / 1000   # L/day
    hrt_days    = REACTOR_VOLUME_L / q_l_per_day if q_l_per_day > 0 else 0.0

    # ── Warning checks ────────────────────────────────────────────────────────
    if not (1.0 <= inputs.do_mgl <= 2.0):
        warnings.append(
            f"DO {inputs.do_mgl:.1f} mg/L is outside the target range "
            f"(1.0–2.0 mg/L). Nitrification may be affected."
        )
    if not (6.5 <= inputs.ph <= 8.0):
        warnings.append(
            f"pH {inputs.ph:.1f} is outside the recommended range (6.5–8.0). "
            f"Biological activity may be inhibited."
        )
    if not (18.0 <= inputs.temp_c <= 28.0):
        warnings.append(
            f"Temperature {inputs.temp_c:.1f}°C is outside the optimal range "
            f"(18–28°C). Biological rates will be reduced."
        )
    if not (200 <= inputs.flow_rate_mlh <= 450):
        warnings.append(
            f"Flow rate {inputs.flow_rate_mlh:.0f} mL/h deviates from the "
            f"design value of 320 mL/h (range 200–450)."
        )
    if inputs.srt_days < 10:
        warnings.append(
            f"SRT {inputs.srt_days:.1f} days is below 10 days — "
            f"nitrifiers may wash out. Target is 30 days."
        )
    if inputs.a_recycle < 1:
        warnings.append(
            f"a-recycle ratio {inputs.a_recycle:.1f} is very low. "
            f"Denitrification will be minimal."
        )

    # ── Temperature correction factor (Arrhenius-type θ^(T-20)) ─────────────
    # Applied consistently to ALL biological rates.
    # θ = 1.072 for nitrification (IAWQ ASM1); ~1.05 for heterotrophs.
    # We use a blended θ ≈ 1.06 for the generic model to affect all processes.
    THETA = 1.06
    temp_factor = THETA ** (inputs.temp_c - 20.0)

    # ── COD removal (first-order aerobic kinetics) ────────────────────────────
    # From 03_EQUATIONS.md:  COD_removal = 1 − 1/(1 + k_COD × HRT)
    # k_COD is temperature-corrected.
    k_cod       = 1.2 * temp_factor   # base rate ~1.2 /day at 20°C
    cod_removal = 1.0 - (1.0 / (1.0 + k_cod * hrt_days))
    cod_removal = max(0.0, min(0.98, cod_removal))

    # ── NH4 removal (nitrification) ───────────────────────────────────────────
    # From 03_EQUATIONS.md:  NH4_removal = min(0.98, 0.55 + DO×0.12 + SRT×0.01)
    # Temperature correction: nitrifiers are sensitive — temp_factor scales the base rate.
    # θ_nitrification = 1.072; modelled here via the global temp_factor.
    nh4_removal = (0.55 + inputs.do_mgl * 0.12 + inputs.srt_days * 0.01) * temp_factor
    nh4_removal = max(0.0, min(0.98, nh4_removal))

    # Minimum SRT for nitrifiers at current temperature (Metcalf & Eddy, 2014)
    nitrifier_min_srt = 3.0 * (1.123 ** (15.0 - inputs.temp_c)) if inputs.temp_c < 15 else 5.0
    if inputs.srt_days < nitrifier_min_srt * 1.5:
        warnings.append(
            f"Nitrifier washout risk: SRT {inputs.srt_days:.1f}d < recommended "
            f"minimum {nitrifier_min_srt * 1.5:.1f}d at {inputs.temp_c:.1f}°C. "
            f"NH₄ removal will be severely reduced."
        )

    # ── TP removal (bio-P enhanced by a-recycle) ──────────────────────────────
    # From 03_EQUATIONS.md:  TP_removal = min(0.92, 0.40 + a_recycle×0.08)
    # Bio-P organisms (PAOs) are also temperature sensitive.
    tp_removal = (0.40 + inputs.a_recycle * 0.08) * temp_factor
    tp_removal = max(0.0, min(0.92, tp_removal))

    # ── PFAS removal (solid-water partitioning via Kd) ────────────────────────
    # From 03_EQUATIONS.md:  adsorption_fraction = Kd×MLSS / (1 + Kd×MLSS)
    # MLSS must be in kg/L for unit consistency: mg/L ÷ 1,000,000 → kg/L
    kd = KD_LONG_CHAIN if inputs.pfas_type == "long-chain" else KD_SHORT_CHAIN
    mlss_kg_per_l = inputs.mlss_mgl / 1_000_000.0
    if mlss_kg_per_l > 0 and kd > 0:
        adsorption = (kd * mlss_kg_per_l) / (1.0 + kd * mlss_kg_per_l)
    else:
        adsorption = 0.0
    pfas_removal = max(0.0, min(0.99, adsorption))

    # ── Effluent concentrations ───────────────────────────────────────────────
    eff_cod  = inputs.inf_cod  * (1.0 - cod_removal)
    eff_nh4  = inputs.inf_nh4  * (1.0 - nh4_removal)
    eff_tp   = inputs.inf_tp   * (1.0 - tp_removal)
    eff_pfas = inputs.inf_pfas * (1.0 - pfas_removal)

    # ── Derived process metrics ───────────────────────────────────────────────
    # F:M ratio (kg COD/kg VSS/day)
    # MLVSS estimated as MLSS × 0.8 (typical ratio)
    mlvss = inputs.mlss_mgl * 0.80
    q_l_day_for_fm = inputs.flow_rate_mlh * 24 / 1000
    cod_load = inputs.inf_cod * q_l_day_for_fm   # mg/day
    biomass  = mlvss * REACTOR_VOLUME_L           # mg
    fm_ratio = cod_load / biomass if biomass > 0 else 0.0

    # Alkalinity consumed by nitrification: ~7.14 g CaCO3 per g NH4-N nitrified
    nh4_removed_mgl = inputs.inf_nh4 * nh4_removal
    alk_consumed_mgl = nh4_removed_mgl * 7.14

    return SimOutputs(
        cod_removal_pct    = cod_removal  * 100,
        nh4_removal_pct    = nh4_removal  * 100,
        tp_removal_pct     = tp_removal   * 100,
        pfas_removal_pct   = pfas_removal * 100,
        eff_cod            = max(0.0, eff_cod),
        eff_nh4            = max(0.0, eff_nh4),
        eff_tp             = max(0.0, eff_tp),
        eff_pfas           = max(0.0, eff_pfas),
        hrt_days           = hrt_days,
        kd_used            = kd,
        temp_factor        = temp_factor,
        fm_ratio           = fm_ratio,
        nitrifier_min_srt  = nitrifier_min_srt,
        alk_consumed_mgl   = alk_consumed_mgl,
        warnings           = warnings,
    )
