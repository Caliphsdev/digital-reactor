"""
calculations.py — Mass balance, removal efficiency, and kinetic helper functions.

These are pure functions (no database access) so they can be used by
both the Mass Balance screen and the Simulation screen without coupling.

All equations come from the PhD proposal:
    Eq1: mass_eff  = C_eff × Q_eff
    Eq2: Q_eff     = Q_in - Q_psludge - Q_WAS
    Removal %:     = (C_inf - C_eff) / C_inf × 100

Kinetic parameters (F:M, SRT, Yobs, nitrification rate) follow standard
activated sludge process design (Metcalf & Eddy, OECD 303A).
"""

# ── Reactor geometry constants ────────────────────────────────────────────────
REACTOR_VOLUME_L      = 12.0   # Total active volume (3 zones × 4 L)
ZONE_VOLUME_L         = 4.0    # Volume per zone
AEROBIC_VOLUME_L      = 4.0    # Aerobic zone volume (L)
ANOXIC_VOLUME_L       = 4.0    # Anoxic zone volume (L)
# Default VSS/MLSS fraction when VSS not measured directly
DEFAULT_VSS_MLSS_RATIO = 0.80  # typical for domestic/lab wastewater sludge


def calc_q_eff(q_in_mlh: float, q_psludge_mlh: float, q_was_mlh: float) -> float:
    """
    Equation 2 — Calculate effluent flow rate.

    Q_eff = Q_in - Q_psludge - Q_WAS

    Args:
        q_in_mlh:       Influent flow rate (mL/h)
        q_psludge_mlh:  Primary sludge flow rate (mL/h)
        q_was_mlh:      Waste activated sludge flow rate (mL/h)

    Returns:
        Effluent flow rate (mL/h). Returns 0.0 if result would be negative.
    """
    q_eff = q_in_mlh - q_psludge_mlh - q_was_mlh
    return max(q_eff, 0.0)


def calc_mass_load(concentration_ugl: float, flow_mlh: float) -> float:
    """
    Equation 1 — Calculate mass load (ug/day) from concentration and flow.

    mass (ug/day) = C (ug/L) × Q (mL/h) × 24h/day ÷ 1000 mL/L

    Args:
        concentration_ugl:  Concentration in ug/L
        flow_mlh:           Flow rate in mL/h

    Returns:
        Mass load in ug/day.
    """
    return concentration_ugl * flow_mlh * 24 / 1000


def calc_removal_pct(c_inf: float, c_eff: float) -> float:
    """
    Calculate removal efficiency as a percentage.

    Removal % = (C_inf - C_eff) / C_inf × 100

    Args:
        c_inf:  Influent concentration (any consistent unit)
        c_eff:  Effluent concentration (same unit)

    Returns:
        Removal percentage (0–100). Returns 0.0 if c_inf is 0 or negative.
    """
    if c_inf <= 0:
        return 0.0
    removal = (c_inf - c_eff) / c_inf * 100
    # Clamp between 0 and 100 — negative removal (increase) is shown as 0
    return max(0.0, min(100.0, removal))


def calc_mass_transformed(
    mass_in: float, mass_eff: float, mass_sludge: float
) -> float:
    """
    Calculate the mass of CEC that was transformed/degraded inside the reactor.

    mass_transformed = mass_in - mass_eff - mass_sludge

    Args:
        mass_in:      Mass entering reactor (ug/day)
        mass_eff:     Mass leaving via effluent (ug/day)
        mass_sludge:  Mass leaving via waste sludge (ug/day)

    Returns:
        Transformed/degraded mass (ug/day). Can be 0 if all mass is accounted for.
    """
    transformed = mass_in - mass_eff - mass_sludge
    return max(transformed, 0.0)


def calc_fm_ratio(
    cod_inf_mgl: float,
    q_in_mlh: float,
    mlss_mgl: float,
    vss_mgl: float | None = None,
) -> float:
    """
    Calculate the Food-to-Microorganism (F:M) ratio.

    F:M = (COD_inf × Q_in) / (MLVSS × V_reactor)
          [kg COD/day / kg VSS] = [kg COD / kg VSS / day]

    If VSS is not provided, MLVSS is estimated as MLSS × 0.80
    (typical VSS/MLSS ratio for activated sludge on domestic wastewater).

    Typical targets for extended aeration (SRT ~30d): 0.05–0.15 kg/kg/day

    Args:
        cod_inf_mgl: Influent COD (mg/L)
        q_in_mlh:    Influent flow (mL/h)
        mlss_mgl:    Mixed Liquor Suspended Solids (mg/L)
        vss_mgl:     Volatile Suspended Solids (mg/L) — optional

    Returns:
        F:M ratio in kg COD/kg VSS/day. Returns 0.0 if inputs are zero.
    """
    if mlss_mgl <= 0 or q_in_mlh <= 0:
        return 0.0
    mlvss = vss_mgl if (vss_mgl and vss_mgl > 0) else mlss_mgl * DEFAULT_VSS_MLSS_RATIO
    if mlvss <= 0:
        return 0.0
    # COD load in mg/day: mg/L × mL/h × 24h ÷ 1000 mL/L
    cod_load_mg_day = cod_inf_mgl * q_in_mlh * 24 / 1000
    # Biomass in mg: mg/L × L
    biomass_mg = mlvss * REACTOR_VOLUME_L
    if biomass_mg <= 0:
        return 0.0
    return cod_load_mg_day / biomass_mg   # mg/mg/day = kg/kg/day (dimensionless)


def calc_actual_srt(
    mlss_mgl: float,
    q_was_mlh: float,
) -> float:
    """
    Calculate actual Solids Retention Time (SRT) from daily WAS flow.

    SRT = (V_reactor × MLSS) / (Q_WAS × MLSS)
        = V_reactor / Q_WAS

    Args:
        mlss_mgl:  Mixed Liquor Suspended Solids (mg/L) — cancels out
        q_was_mlh: Waste Activated Sludge flow (mL/h)

    Returns:
        Actual SRT in days. Returns 0.0 if Q_WAS is zero.
    """
    if q_was_mlh <= 0:
        return 0.0
    # Q_WAS in L/day
    q_was_l_day = q_was_mlh * 24 / 1000
    if q_was_l_day <= 0:
        return 0.0
    return REACTOR_VOLUME_L / q_was_l_day


def calc_hrt(q_in_mlh: float) -> float:
    """
    Calculate Hydraulic Retention Time (HRT) for the whole reactor.

    HRT = V_reactor / Q_in

    Args:
        q_in_mlh: Influent flow (mL/h)

    Returns:
        HRT in hours. Returns 0.0 if Q_in is zero.
    """
    if q_in_mlh <= 0:
        return 0.0
    q_in_l_h = q_in_mlh / 1000
    return REACTOR_VOLUME_L / q_in_l_h


def calc_nitrification_rate(
    nh4_inf_mgl: float,
    nh4_eff_mgl: float,
    q_in_mlh: float,
) -> float:
    """
    Calculate the apparent nitrification rate (NH4 removed per day per L aerobic volume).

    Rate = (NH4_in - NH4_eff) × Q_in / V_aerobic
           [mg N / L / day]

    Args:
        nh4_inf_mgl: Influent NH4-N (mg/L)
        nh4_eff_mgl: Effluent NH4-N (mg/L)
        q_in_mlh:    Influent flow (mL/h)

    Returns:
        Nitrification rate in mg N/L/day.
    """
    if q_in_mlh <= 0 or nh4_inf_mgl <= nh4_eff_mgl:
        return 0.0
    q_in_l_day = q_in_mlh * 24 / 1000
    nh4_removed = (nh4_inf_mgl - nh4_eff_mgl) * q_in_l_day  # mg/day
    return nh4_removed / AEROBIC_VOLUME_L   # mg N / L / day


def calc_denitrification_rate(
    no3_anoxic_in_mgl: float,
    no3_anoxic_out_mgl: float,
    q_recycle_mlh: float,
) -> float:
    """
    Calculate apparent denitrification rate across the anoxic zone.

    Rate = (NO3_in - NO3_out) × Q_recycle / V_anoxic
           [mg N / L / day]

    Args:
        no3_anoxic_in_mgl:  NO3 entering anoxic zone (mg/L)
        no3_anoxic_out_mgl: NO3 leaving anoxic zone (mg/L)
        q_recycle_mlh:      Internal recycle flow to anoxic zone (mL/h)

    Returns:
        Denitrification rate in mg N/L/day.
    """
    if q_recycle_mlh <= 0 or no3_anoxic_in_mgl <= no3_anoxic_out_mgl:
        return 0.0
    q_rec_l_day = q_recycle_mlh * 24 / 1000
    no3_removed = (no3_anoxic_in_mgl - no3_anoxic_out_mgl) * q_rec_l_day
    return no3_removed / ANOXIC_VOLUME_L


def calc_observed_yield(
    mlss_change_mgl: float,
    cod_removed_mgl: float,
) -> float:
    """
    Calculate observed yield (Yobs) — net biomass produced per unit COD removed.

    Yobs = ΔMLSS / ΔCOD   [mg VSS / mg COD]

    Typical range: 0.3–0.6 for aerobic heterotrophs at SRT 10–30d.

    Args:
        mlss_change_mgl: Change in MLSS concentration (mg/L)
        cod_removed_mgl: COD removed (mg/L) — inf COD minus eff COD

    Returns:
        Observed yield (dimensionless, mg/mg). Returns 0.0 if COD removed ≤ 0.
    """
    if cod_removed_mgl <= 0:
        return 0.0
    return mlss_change_mgl / cod_removed_mgl


def check_nitrifier_washout_risk(srt_days: float, temp_c: float) -> str | None:
    """
    Return a warning string if conditions risk nitrifier washout, else None.

    Nitrifiers (AOB/NOB) are slow-growing and wash out at low SRT.
    Minimum SRT increases with decreasing temperature (Arrhenius-type).

    Rule of thumb (Metcalf & Eddy, 2014):
      SRT_min ≈ 3.0 × 1.123^(15-T) days   for T < 15°C
      SRT_min ≈ 5.0 days                   for T ≥ 15°C

    Args:
        srt_days: Current or target SRT (days)
        temp_c:   Temperature (°C)

    Returns:
        Warning string, or None if conditions are safe.
    """
    if temp_c < 15.0:
        srt_min = 3.0 * (1.123 ** (15.0 - temp_c))
    else:
        srt_min = 5.0

    safety_factor = 1.5   # design safety factor over minimum SRT
    if srt_days < srt_min * safety_factor:
        return (
            f"Nitrifier washout risk: SRT {srt_days:.1f}d is below the "
            f"recommended minimum of {srt_min * safety_factor:.1f}d "
            f"at {temp_c:.1f}°C (min SRT × 1.5 safety factor)."
        )
    return None


def full_mass_balance(
    c_inf_ugl: float,
    c_eff_ugl: float,
    c_sludge_ugl: float,
    q_in_mlh: float,
    q_was_mlh: float,
    q_psludge_mlh: float,
) -> dict:
    """
    Run the complete mass balance calculation for one CEC on one day.

    Returns a dictionary with all intermediate and final values so the
    Mass Balance screen can display the working in full.

    Args:
        c_inf_ugl:      Influent CEC concentration (ug/L)
        c_eff_ugl:      Effluent CEC concentration (ug/L)
        c_sludge_ugl:   Sludge CEC concentration (ug/L) — use 0 if unknown
        q_in_mlh:       Influent flow (mL/h)
        q_was_mlh:      Waste activated sludge flow (mL/h)
        q_psludge_mlh:  Primary sludge flow (mL/h)

    Returns:
        dict with keys:
            q_eff_mlh, mass_in_ugday, mass_eff_ugday, mass_sludge_ugday,
            mass_transformed_ugday, removal_pct
    """
    q_eff = calc_q_eff(q_in_mlh, q_psludge_mlh, q_was_mlh)

    mass_in      = calc_mass_load(c_inf_ugl,    q_in_mlh)
    mass_eff     = calc_mass_load(c_eff_ugl,    q_eff)
    mass_sludge  = calc_mass_load(c_sludge_ugl, q_was_mlh)
    mass_transf  = calc_mass_transformed(mass_in, mass_eff, mass_sludge)
    removal      = calc_removal_pct(c_inf_ugl, c_eff_ugl)

    return {
        "q_eff_mlh":            q_eff,
        "mass_in_ugday":        mass_in,
        "mass_eff_ugday":       mass_eff,
        "mass_sludge_ugday":    mass_sludge,
        "mass_transformed_ugday": mass_transf,
        "removal_pct":          removal,
    }
