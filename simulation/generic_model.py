"""
generic_model.py — Phase 1 generic (textbook) simulation model.

All equations come from 03_EQUATIONS.md (Sekhula-Mojela, 2026).
These are first-order / empirical estimates that give directional
predictions without requiring real training data.

Reactor configuration: CAS (Conventional Activated Sludge)
  Influent → Primary Settling Tank → Aeration Tank → Clarifier → Effluent
  RAS (Return Activated Sludge) from Clarifier → Aeration Tank inlet

IMPORTANT: Phase 1 values are textbook estimates only.
Phase 2 (data_model.py) will replace these with a scikit-learn
model trained on the researcher's actual lab measurements.
"""

from dataclasses import dataclass


# ── Reactor volume constants ───────────────────────────────────────────────────
REACTOR_VOLUME_L   = 12.0   # total volume (PST + Aeration + Clarifier)
AERATION_VOLUME_L  =  8.0   # aeration tank volume — used for biological HRT
                             # (the dominant vessel; PST and clarifier add ~2 L each)

# ── Primary Settling Tank removal fractions (typical CAS values) ──────────────
PST_COD_REMOVAL = 0.30   # 25–35% COD removed by physical settling
PST_TSS_REMOVAL = 0.60   # 55–65% TSS removed (textbook range)

# ── Compound-specific Kd table (solid-water partition coefficient, L/kg MLSS) ───
# Literature values from Higgins & Luthy (2006), Xiao et al. (2015),
# and Ahrens & Bundschuh (2014) for PFAS adsorption onto activated sludge.
# Used when a specific compound name is supplied.  The class fallbacks below
# are used when only the chain type ("short-chain" | "long-chain") is known.
PFAS_KD_TABLE: dict[str, float] = {
    # ── Long-chain PFAS ───────────────────────────────────────────────────────
    # Perfluoroalkyl sulfonates (C ≥ 6) — highest sorption
    "PFOS":   7.0,   # C8 sulfonate  — Higgins & Luthy 2006
    "PFHxS":  3.5,   # C6 sulfonate
    "PFNS":   5.5,   # C9 sulfonate
    "PFDS":  10.5,   # C10 sulfonate
    # Perfluoroalkyl carboxylates (C ≥ 8)
    "PFOA":   2.5,   # C8 carboxylate — Higgins & Luthy 2006
    "PFNA":   5.0,   # C9 carboxylate
    "PFDA":   9.0,   # C10 carboxylate
    "PFUnA": 15.0,   # C11 carboxylate
    "PFUnDA": 15.0,  # common alternate abbreviation for PFUnA
    "PFDoA": 22.0,   # C12 carboxylate
    # ── Short-chain PFAS ─────────────────────────────────────────────────────
    # Perfluoroalkyl sulfonates (C < 6)
    "PFBS":   0.5,   # C4 sulfonate
    "PFPeS":  1.0,   # C5 sulfonate
    # Perfluoroalkyl carboxylates (C < 8)
    "PFBA":   0.3,   # C4 carboxylate
    "PFPeA":  0.5,   # C5 carboxylate
    "PFHxA":  0.7,   # C6 carboxylate
    "PFHpA":  1.2,   # C7 carboxylate
}
# Class fallbacks (used when compound is unknown)
KD_SHORT_CHAIN = 0.8    # L/kg  (conservative class average)
KD_LONG_CHAIN  = 4.5    # L/kg  (class average)

# ── UI compound list: (display label, compound key) ──────────────────────────
# Ordered long-chain first (highest Kd / most regulated), then short-chain.
# Both UI screens import this so the list stays in one place.
PFAS_COMPOUND_LIST: list[tuple[str, str]] = [
    ("— class average —",                ""),
    ("PFOS  (C8 sulfonate,  long-chain)", "PFOS"),
    ("PFHxS (C6 sulfonate,  long-chain)", "PFHxS"),
    ("PFNS  (C9 sulfonate,  long-chain)", "PFNS"),
    ("PFDS  (C10 sulfonate, long-chain)", "PFDS"),
    ("PFOA  (C8 carboxylate, long-chain)","PFOA"),
    ("PFNA  (C9 carboxylate, long-chain)","PFNA"),
    ("PFDA  (C10 carboxylate, long-chain)","PFDA"),
    ("PFUnA (C11 carboxylate, long-chain)","PFUnA"),
    ("PFDoA (C12 carboxylate, long-chain)","PFDoA"),
    ("PFBS  (C4 sulfonate,  short-chain)","PFBS"),
    ("PFPeS (C5 sulfonate,  short-chain)","PFPeS"),
    ("PFBA  (C4 carboxylate, short-chain)","PFBA"),
    ("PFPeA (C5 carboxylate, short-chain)","PFPeA"),
    ("PFHxA (C6 carboxylate, short-chain)","PFHxA"),
    ("PFHpA (C7 carboxylate, short-chain)","PFHpA"),
]

# Maps compound key → chain type for auto-setting the type dropdown
PFAS_COMPOUND_CHAIN_TYPE: dict[str, str] = {
    "PFOS": "long-chain",  "PFHxS": "long-chain",  "PFNS": "long-chain",
    "PFDS": "long-chain",  "PFOA": "long-chain",   "PFNA": "long-chain",
    "PFDA": "long-chain",  "PFUnA": "long-chain",  "PFDoA": "long-chain",
    "PFBS": "short-chain", "PFPeS": "short-chain",
    "PFBA": "short-chain", "PFPeA": "short-chain", "PFHxA": "short-chain",
    "PFHpA": "short-chain",
}


def get_kd(pfas_compound: str, pfas_type: str) -> float:
    """
    Return the solid-water partition coefficient (L/kg MLSS) for a PFAS.

    Looks up the compound name first (case-insensitive) in PFAS_KD_TABLE;
    falls back to the class-average KD_SHORT_CHAIN / KD_LONG_CHAIN when the
    compound is not listed.
    """
    if pfas_compound:
        wanted = pfas_compound.strip().casefold()
        for compound, kd in PFAS_KD_TABLE.items():
            if compound.casefold() == wanted:
                return kd
    return KD_LONG_CHAIN if pfas_type == "long-chain" else KD_SHORT_CHAIN


# ── Monod kinetic constants for nitrification (ASM1 / Metcalf & Eddy 2014) ───
# Nitrosomonas (AOB) parameters — rate-limiting step for nitrification in CAS
MU_MAX_N   = 0.75   # /day    maximum AOB growth rate at 20°C
KS_N       = 0.74   # mg/L   NH4-N half-saturation constant (Metcalf & Eddy)
KO_N       = 0.50   # mg/L   DO half-saturation for AOB
B_N        = 0.08   # /day   AOB endogenous decay rate
THETA_N    = 1.072  # –       temperature correction for µmax_N (AOB)
THETA_B    = 1.029  # –       temperature correction for b_N


@dataclass
class SimInputs:
    """All operating parameters fed into the Phase 1 CAS model."""
    flow_rate_mlh:   float   # influent flow (mL/h)
    ras_ratio:       float   # RAS recycle ratio (unitless) — Clarifier → Aeration inlet
    do_mgl:          float   # aeration tank DO (mg/L)
    srt_days:        float   # sludge retention time (days)
    temp_c:          float   # temperature (°C)
    ph:              float   # pH (unitless)
    inf_cod:         float   # influent COD (mg/L)
    inf_nh4:         float   # influent NH4-N (mg/L)
    inf_tp:          float   # influent total phosphorus (mg/L)
    inf_pfas:        float   # influent PFAS concentration (µg/L)
    pfas_type:       str     # "short-chain" | "long-chain"
    mlss_mgl:        float   # mixed liquor SS in aeration tank (mg/L)
    pfas_compound:   str = ""  # specific compound name e.g. "PFOS", "PFOA"
                               # if provided, looks up Kd from PFAS_KD_TABLE


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
    # 90 % prediction intervals — (low, high) tuples; None when unavailable
    # Populated by Phase 2 RF inference; Phase 1 always leaves these as None.
    cod_ci:  tuple[float, float] | None = None   # % removal interval
    nh4_ci:  tuple[float, float] | None = None
    tp_ci:   tuple[float, float] | None = None
    pfas_ci: tuple[float, float] | None = None
    # Compound-level PFAS metadata
    pfas_compound_used: str = ""    # which compound was looked up (empty = class avg)
    monod_washout: bool = False      # True when Monod equation predicts nitrifier washout


def run_phase1(inputs: SimInputs) -> SimOutputs:
    """
    Run the Phase 1 generic CAS model and return predicted outputs.

    Process train: PST (physical) → Aeration Tank (biological) → Clarifier
    All equations are sourced from 03_EQUATIONS.md.
    Warning flags are generated for parameters outside recommended ranges.
    """
    warnings: list[str] = []

    # ── Hydraulic Retention Time ──────────────────────────────────────────────
    # Biological HRT uses the Aeration Tank volume only (not PST or Clarifier).
    # HRT = V_aeration / Q  →  convert mL/h → L/day first
    q_l_per_day    = inputs.flow_rate_mlh * 24 / 1000   # L/day
    hrt_bio_days   = AERATION_VOLUME_L / q_l_per_day if q_l_per_day > 0 else 0.0
    hrt_total_days = REACTOR_VOLUME_L  / q_l_per_day if q_l_per_day > 0 else 0.0

    # ── Warning checks ────────────────────────────────────────────────────────
    if not (1.0 <= inputs.do_mgl <= 4.0):
        warnings.append(
            f"DO {inputs.do_mgl:.1f} mg/L is outside the target range "
            f"(1.0–4.0 mg/L). Nitrification may be affected."
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

    # ── Temperature correction factor (Arrhenius-type θ^(T-20)) ─────────────
    # θ ≈ 1.06 blended value for the generic model.
    THETA = 1.06
    temp_factor = THETA ** (inputs.temp_c - 20.0)

    # ── Step 1: Primary Settling Tank (physical removal) ─────────────────────
    # PST removes a fraction of COD via physical sedimentation before
    # the Aeration Tank. This is the first treatment step in CAS.
    cod_after_pst = inputs.inf_cod * (1.0 - PST_COD_REMOVAL)

    # ── Step 2: COD removal in Aeration Tank (first-order aerobic kinetics) ──
    # From 03_EQUATIONS.md:  COD_removal_bio = 1 − 1/(1 + k_COD × HRT_bio)
    # Applied to COD entering the Aeration Tank (after PST).
    k_cod          = 1.2 * temp_factor   # base rate ~1.2 /day at 20°C
    cod_removal_bio = 1.0 - (1.0 / (1.0 + k_cod * hrt_bio_days))
    cod_removal_bio = max(0.0, min(0.98, cod_removal_bio))

    # Overall COD removal relative to raw influent
    eff_cod         = cod_after_pst * (1.0 - cod_removal_bio)
    cod_removal     = 1.0 - (eff_cod / inputs.inf_cod) if inputs.inf_cod > 0 else 0.0
    cod_removal     = max(0.0, min(0.99, cod_removal))

    # ── NH4 removal (Monod steady-state nitrification — ASM1, Metcalf & Eddy 2014) ──
    # At steady-state in a CSTR with SRT control, the effluent NH4 concentration is:
    #
    #   Se_nh4 = Ks_n · (1 + b_n_T · SRT)
    #            ─────────────────────────────────────────────────────
    #            SRT · [µmax_n_T · DO/(Ko_n + DO) − b_n_T]  −  1
    #
    # where µmax_n_T and b_n_T are temperature-corrected via separate θ values.
    # Denominator ≤ 0  → nitrifiers cannot grow (washout)
    # Se_nh4 < 0       → complete nitrification (cap effluent at ~0)
    mu_max_n_T = MU_MAX_N * (THETA_N ** (inputs.temp_c - 20.0))
    b_n_T      = B_N      * (THETA_B ** (inputs.temp_c - 20.0))
    do_factor  = inputs.do_mgl / (KO_N + inputs.do_mgl) if (KO_N + inputs.do_mgl) > 0 else 0.0
    mu_net_n   = mu_max_n_T * do_factor - b_n_T

    monod_washout = False
    denom = inputs.srt_days * mu_net_n - 1.0
    if denom <= 0 or inputs.srt_days <= 0:
        # Nitrifiers wash out — no biological NH4 removal
        nh4_removal  = 0.0
        monod_washout = True
    else:
        numer       = KS_N * (1.0 + b_n_T * inputs.srt_days)
        se_nh4      = numer / denom
        if se_nh4 < 0:
            se_nh4 = 0.0   # complete nitrification
        nh4_removal = 1.0 - (se_nh4 / inputs.inf_nh4) if inputs.inf_nh4 > 0 else 0.0
        nh4_removal = max(0.0, min(0.98, nh4_removal))

    # Minimum SRT for nitrifiers at current temperature (Metcalf & Eddy, 2014)
    # SRTmin = (1/µmax_n_T · DO/(Ko_n+DO) - b_n_T) + safety
    if mu_net_n > 0:
        nitrifier_min_srt = 1.0 / mu_net_n
    else:
        nitrifier_min_srt = 999.0  # effectively infinite at this temperature/DO
    if inputs.srt_days < nitrifier_min_srt * 1.5:
        warnings.append(
            f"Nitrifier washout risk: SRT {inputs.srt_days:.1f}d < recommended "
            f"minimum {nitrifier_min_srt * 1.5:.1f}d at {inputs.temp_c:.1f}°C. "
            f"NH₄ removal will be severely reduced."
        )

    # ── TP removal (luxury uptake in Aeration Tank) ───────────────────────────
    # CAS without dedicated anaerobic selector: lower bio-P than A²O.
    # RAS re-aeration encourages some luxury uptake.
    # Adjusted equation for CAS (no a-recycle term):
    #   TP_removal = min(0.75, 0.30 + RAS×0.04) × temp_factor
    tp_removal = (0.30 + inputs.ras_ratio * 0.04) * temp_factor
    tp_removal = max(0.0, min(0.75, tp_removal))

    # ── PFAS removal (solid-water partitioning via Kd) ────────────────────────
    # From 03_EQUATIONS.md:  adsorption_fraction = Kd×MLSS / (1 + Kd×MLSS)
    # MLSS must be in kg/L for unit consistency: mg/L ÷ 1,000,000 → kg/L
    # Uses compound-specific Kd from PFAS_KD_TABLE when pfas_compound is given.
    kd = get_kd(inputs.pfas_compound, inputs.pfas_type)
    mlss_kg_per_l = inputs.mlss_mgl / 1_000_000.0
    if mlss_kg_per_l > 0 and kd > 0:
        adsorption = (kd * mlss_kg_per_l) / (1.0 + kd * mlss_kg_per_l)
    else:
        adsorption = 0.0
    pfas_removal = max(0.0, min(0.99, adsorption))

    # ── Effluent concentrations ───────────────────────────────────────────────
    # eff_cod already calculated above (cascaded through PST then aeration)
    eff_nh4  = inputs.inf_nh4  * (1.0 - nh4_removal)
    eff_tp   = inputs.inf_tp   * (1.0 - tp_removal)
    eff_pfas = inputs.inf_pfas * (1.0 - pfas_removal)

    # ── Derived process metrics ───────────────────────────────────────────────
    # F:M ratio (kg COD/kg VSS/day) — uses Aeration Tank MLSS/MLVSS
    mlvss = inputs.mlss_mgl * 0.80   # MLVSS ≈ MLSS × 0.8
    cod_load = inputs.inf_cod * q_l_per_day   # mg/day (raw influent COD load)
    biomass  = mlvss * AERATION_VOLUME_L       # mg (only aeration tank biomass)
    fm_ratio = cod_load / biomass if biomass > 0 else 0.0

    # Alkalinity consumed by nitrification: ~7.14 g CaCO3 per g NH4-N nitrified
    nh4_removed_mgl  = inputs.inf_nh4 * nh4_removal
    alk_consumed_mgl = nh4_removed_mgl * 7.14

    return SimOutputs(
        cod_removal_pct      = cod_removal  * 100,
        nh4_removal_pct      = nh4_removal  * 100,
        tp_removal_pct       = tp_removal   * 100,
        pfas_removal_pct     = pfas_removal * 100,
        eff_cod              = max(0.0, eff_cod),
        eff_nh4              = max(0.0, eff_nh4),
        eff_tp               = max(0.0, eff_tp),
        eff_pfas             = max(0.0, eff_pfas),
        hrt_days             = hrt_total_days,
        kd_used              = kd,
        temp_factor          = temp_factor,
        fm_ratio             = fm_ratio,
        nitrifier_min_srt    = nitrifier_min_srt,
        alk_consumed_mgl     = alk_consumed_mgl,
        warnings             = warnings,
        monod_washout        = monod_washout,
        pfas_compound_used   = inputs.pfas_compound or "",
    )
