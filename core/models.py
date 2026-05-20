"""
models.py — SQLAlchemy ORM models for all Digital Reactor database tables.

Each class maps to one table in reactor.db.
Tables are created automatically when the app first runs (see database.py).
"""

from datetime import datetime, timezone
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, Date, DateTime, Text,
    ForeignKey
)
from sqlalchemy.orm import relationship, DeclarativeBase


class Base(DeclarativeBase):
    """Shared declarative base — all models inherit from this."""
    pass


def utc_now() -> datetime:
    """Timezone-aware UTC timestamp for SQLAlchemy default factories."""
    return datetime.now(timezone.utc)


class Plant(Base):
    """
    Real wastewater treatment plant profile used by the Scientific Twin module.

    These rows describe full-scale plants without changing the lab-reactor
    experiment schema. Literature/default values are starting assumptions and
    can later be overridden by measured plant monitoring data.
    """
    __tablename__ = "plants"

    id                    = Column(Integer, primary_key=True, autoincrement=True)
    slug                  = Column(String, nullable=False, unique=True)
    name                  = Column(String, nullable=False)
    municipality          = Column(String, nullable=True)
    province              = Column(String, nullable=True)
    process_family        = Column(String, nullable=False)
    capacity_mld          = Column(Float, nullable=True)
    receiving_water       = Column(String, nullable=True)
    summary               = Column(Text, nullable=True)
    realism_notes         = Column(Text, nullable=True)
    source_notes          = Column(Text, nullable=True)

    default_flow_mld      = Column(Float, nullable=True)
    default_hrt_hours     = Column(Float, nullable=True)
    default_srt_days      = Column(Float, nullable=True)
    default_mlss_mgl      = Column(Float, nullable=True)
    default_do_mgl        = Column(Float, nullable=True)
    default_temp_c        = Column(Float, nullable=True)
    default_ph            = Column(Float, nullable=True)
    default_recycle_ratio = Column(Float, nullable=True)
    default_organic_loading = Column(Float, nullable=True)
    default_nitrogen_loading = Column(Float, nullable=True)

    created_at            = Column(DateTime, default=utc_now)

    units = relationship(
        "PlantUnit",
        back_populates="plant",
        cascade="all, delete-orphan",
        order_by="PlantUnit.unit_order",
    )
    sampling_points = relationship(
        "PlantSamplingPoint",
        back_populates="plant",
        cascade="all, delete-orphan",
        order_by="PlantSamplingPoint.point_order",
    )
    monitoring_readings = relationship(
        "PlantMonitoringReading",
        back_populates="plant",
        cascade="all, delete-orphan",
    )
    calibrations = relationship(
        "PlantCalibration",
        back_populates="plant",
        cascade="all, delete-orphan",
    )

    def __repr__(self):
        return f"<Plant id={self.id} slug={self.slug!r} name={self.name!r}>"


class PlantUnit(Base):
    """Ordered process unit within a full-scale plant process train."""
    __tablename__ = "plant_units"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    plant_id       = Column(Integer, ForeignKey("plants.id"), nullable=False)
    unit_order     = Column(Integer, nullable=False)
    name           = Column(String, nullable=False)
    unit_type      = Column(String, nullable=False)
    hydraulic_role = Column(String, nullable=True)
    hrt_hours      = Column(Float, nullable=True)
    notes          = Column(Text, nullable=True)

    plant = relationship("Plant", back_populates="units")

    def __repr__(self):
        return f"<PlantUnit plant_id={self.plant_id} order={self.unit_order} name={self.name!r}>"


class PlantSamplingPoint(Base):
    """Plant-specific sampling location mapped onto the process train."""
    __tablename__ = "plant_sampling_points"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    plant_id         = Column(Integer, ForeignKey("plants.id"), nullable=False)
    point_order      = Column(Integer, nullable=False)
    code             = Column(String, nullable=False)
    name             = Column(String, nullable=False)
    after_unit_order = Column(Integer, nullable=True)
    description      = Column(Text, nullable=True)

    plant = relationship("Plant", back_populates="sampling_points")
    monitoring_readings = relationship(
        "PlantMonitoringReading",
        back_populates="sampling_point",
    )

    def __repr__(self):
        return f"<PlantSamplingPoint plant_id={self.plant_id} code={self.code!r}>"


class PlantMonitoringReading(Base):
    """
    Field monitoring row for a real plant.

    V1 uses these rows for future calibration and comparison. The Scientific
    Twin runs from literature defaults when no measured rows are available.
    """
    __tablename__ = "plant_monitoring_readings"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    plant_id            = Column(Integer, ForeignKey("plants.id"), nullable=False)
    sampling_point_id   = Column(Integer, ForeignKey("plant_sampling_points.id"), nullable=True)
    sampling_date       = Column(Date, nullable=False)
    sampling_point_code = Column(String, nullable=True)
    cec_name            = Column(String, nullable=True)
    cec_type            = Column(String, nullable=True)
    concentration_ugl   = Column(Float, nullable=True)
    below_detection     = Column(Boolean, default=False)
    detection_limit_ugl = Column(Float, nullable=True)
    cod_mgl             = Column(Float, nullable=True)
    bod_mgl             = Column(Float, nullable=True)
    nh4_mgl             = Column(Float, nullable=True)
    no3_mgl             = Column(Float, nullable=True)
    tn_mgl              = Column(Float, nullable=True)
    tp_mgl              = Column(Float, nullable=True)
    tss_mgl             = Column(Float, nullable=True)
    do_mgl              = Column(Float, nullable=True)
    mlss_mgl            = Column(Float, nullable=True)
    srt_days            = Column(Float, nullable=True)
    hrt_hours           = Column(Float, nullable=True)
    recycle_ratio       = Column(Float, nullable=True)
    ph                  = Column(Float, nullable=True)
    temperature_c       = Column(Float, nullable=True)
    flow_mld            = Column(Float, nullable=True)
    source              = Column(String, nullable=True)
    notes               = Column(Text, nullable=True)
    created_at          = Column(DateTime, default=utc_now)

    plant = relationship("Plant", back_populates="monitoring_readings")
    sampling_point = relationship(
        "PlantSamplingPoint",
        back_populates="monitoring_readings",
    )

    def __repr__(self):
        return f"<PlantMonitoringReading plant_id={self.plant_id} date={self.sampling_date}>"


class PlantCalibration(Base):
    """
    Calibration coefficient fitted from real plant monitoring data.

    V1 stores one multiplier per plant/target. The multiplier adjusts the
    mechanistic Scientific Twin removal prediction toward observed SP1→SP4
    removal while preserving the transparent process model underneath.
    """
    __tablename__ = "plant_calibrations"

    id                  = Column(Integer, primary_key=True, autoincrement=True)
    plant_id            = Column(Integer, ForeignKey("plants.id"), nullable=False)
    target              = Column(String, nullable=False)  # cod | nh4 | tn | tp | pfas
    multiplier          = Column(Float, nullable=False, default=1.0)
    n_samples           = Column(Integer, nullable=False, default=0)
    rmse_pct            = Column(Float, nullable=True)
    mean_abs_error_pct  = Column(Float, nullable=True)
    r2                  = Column(Float, nullable=True)
    actual_mean_pct     = Column(Float, nullable=True)
    predicted_mean_pct  = Column(Float, nullable=True)
    date_start          = Column(Date, nullable=True)
    date_end            = Column(Date, nullable=True)
    method              = Column(String, nullable=True)
    notes               = Column(Text, nullable=True)
    calibrated_at       = Column(DateTime, default=utc_now)

    plant = relationship("Plant", back_populates="calibrations")

    def __repr__(self):
        return f"<PlantCalibration plant_id={self.plant_id} target={self.target!r} multiplier={self.multiplier}>"


class Experiment(Base):
    """
    Represents one experimental run of the reactor from startup to shutdown.
    All daily readings, CEC readings, and mass balance results link back
    to an Experiment via experiment_id.
    """
    __tablename__ = "experiments"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    name        = Column(String, nullable=False)     # e.g. "Run 1 - PFOS spike 50ug/L"
    start_date  = Column(Date, nullable=False)
    end_date    = Column(Date, nullable=True)         # null while still running
    description = Column(Text, nullable=True)
    cec_spiked  = Column(String, nullable=True)       # which CECs were added
    spike_conc  = Column(Float, nullable=True)        # concentration spiked (ug/L)
    is_active   = Column(Boolean, default=False)      # True = currently selected experiment
    notes       = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=utc_now)

    # Relationships — allows experiment.daily_readings etc.
    daily_readings          = relationship("DailyReading",          back_populates="experiment", cascade="all, delete-orphan")
    flow_readings           = relationship("FlowReading",           back_populates="experiment", cascade="all, delete-orphan")
    cec_readings            = relationship("CECReading",            back_populates="experiment", cascade="all, delete-orphan")
    mass_balance_results    = relationship("MassBalanceResult",     back_populates="experiment", cascade="all, delete-orphan")
    sludge_characterizations= relationship("SludgeCharacterization",back_populates="experiment", cascade="all, delete-orphan")

    def __repr__(self):
        return f"<Experiment id={self.id} name={self.name!r}>"


class DailyReading(Base):
    """
    One row per day per zone per experiment.
    Stores all water quality parameters measured in the lab each day.
    Zones: anaerobic | anoxic | aerobic | effluent
    """
    __tablename__ = "daily_readings"

    id            = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    reading_date  = Column(Date, nullable=False)
    zone          = Column(String, nullable=False)
    # Current physical layout: "primary_settling" | "aeration" | "clarifier" | "effluent"
    # Historical zone names (pre-CAS overhaul): "anaerobic" | "anoxic" | "aerobic" | "effluent"
    do_mgl        = Column(Float, nullable=True)     # Dissolved Oxygen (mg/L)
    ph            = Column(Float, nullable=True)
    temperature_c = Column(Float, nullable=True)
    cod_mgl       = Column(Float, nullable=True)     # Chemical Oxygen Demand (mg/L)
    nh4_mgl       = Column(Float, nullable=True)     # Ammonia (mg/L)
    no3_mgl       = Column(Float, nullable=True)     # Nitrate (mg/L)
    so4_mgl       = Column(Float, nullable=True)     # Sulfate (mg/L)
    po4_mgl       = Column(Float, nullable=True)     # Phosphate (mg/L)
    mlss_mgl      = Column(Float, nullable=True)     # Mixed Liquor Suspended Solids (mg/L)
    # ── Advanced parameters (added via migration v1) ───────────────────────────
    vss_mgl        = Column(Float, nullable=True)    # Volatile Suspended Solids (mg/L)
    tss_mgl        = Column(Float, nullable=True)    # Total Suspended Solids (mg/L)
    orp_mv         = Column(Float, nullable=True)    # Oxidation-Reduction Potential (mV)
    alkalinity_mgl = Column(Float, nullable=True)    # Alkalinity as CaCO3 (mg/L)
    turbidity_ntu  = Column(Float, nullable=True)    # Turbidity (NTU)
    our_mgl_h      = Column(Float, nullable=True)    # Oxygen Uptake Rate (mg/L/h) — aerobic only
    bod_mgl        = Column(Float, nullable=True)    # BOD5 (mg/L)
    tn_mgl         = Column(Float, nullable=True)    # Total Nitrogen (mg/L)
    tp_mgl         = Column(Float, nullable=True)    # Total Phosphorus (mg/L)
    notes         = Column(Text, nullable=True)
    created_at    = Column(DateTime, default=utc_now)

    experiment = relationship("Experiment", back_populates="daily_readings")

    def __repr__(self):
        return f"<DailyReading id={self.id} date={self.reading_date} zone={self.zone!r}>"


class FlowReading(Base):
    """
    Daily flow measurements used in mass balance calculations.
    Captures influent flow, waste sludge, and recycle ratios.
    """
    __tablename__ = "flow_readings"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id   = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    reading_date    = Column(Date, nullable=False)
    q_in_mlh        = Column(Float, nullable=True)   # Influent flow (mL/h)
    q_was_mlh       = Column(Float, nullable=True)   # Waste activated sludge flow (mL/h)
    q_psludge_mlh   = Column(Float, nullable=True)   # Primary sludge flow (mL/h)
    ras_ratio       = Column(Float, nullable=True)   # RAS recycle ratio (e.g. 1.0 = 1:1)
    a_recycle_ratio = Column(Float, nullable=True)   # a-recycle ratio (e.g. 4.0 = 1:4)
    notes           = Column(Text, nullable=True)

    experiment = relationship("Experiment", back_populates="flow_readings")

    def __repr__(self):
        return f"<FlowReading id={self.id} date={self.reading_date}>"


class CECReading(Base):
    """
    CEC (Contaminants of Emerging Concern) concentrations measured at
    each of the four sampling points in the treatment train.
    SP1=influent, SP2=primary, SP3=clarifier, SP4=effluent.
    """
    __tablename__ = "cec_readings"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id   = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    reading_date    = Column(Date, nullable=False)
    cec_name        = Column(String, nullable=False)  # e.g. "PFOS", "PFBA", "PFBS"
    cec_type        = Column(String, nullable=True)   # "short-chain" | "long-chain"
    sampling_point  = Column(String, nullable=False)  # "SP1_influent" | "SP2_primary" | "SP3_clarifier" | "SP4_effluent"
    concentration   = Column(Float, nullable=True)    # ug/L (null if below detection)
    below_detection = Column(Boolean, default=False)  # True = reading is < detection limit
    detection_limit = Column(Float, nullable=True)    # instrument detection limit (ug/L)
    analysis_method = Column(String, nullable=True)   # "TOF-MS" | "GC-MS"
    notes           = Column(Text, nullable=True)
    created_at      = Column(DateTime, default=utc_now)

    experiment = relationship("Experiment", back_populates="cec_readings")

    def __repr__(self):
        return f"<CECReading id={self.id} cec={self.cec_name!r} point={self.sampling_point!r}>"


class MassBalanceResult(Base):
    """
    Auto-calculated mass balance results — never entered manually.
    Generated by the Mass Balance screen using logged flow and CEC data.
    Equations from proposal:
        mass_in   = C_inf × Q_in
        mass_eff  = C_eff × Q_eff  (Equation 1)
        Q_eff     = Q_in - Q_psludge - Q_WAS  (Equation 2)
        removal % = (C_inf - C_eff) / C_inf × 100
    """
    __tablename__ = "mass_balance_results"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id     = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    calculation_date  = Column(Date, nullable=False)
    cec_name          = Column(String, nullable=False)
    mass_in_mgday     = Column(Float, nullable=True)     # C_inf × Q_in
    mass_eff_mgday    = Column(Float, nullable=True)     # C_eff × Q_eff (Eq 1)
    mass_sludge_mgday = Column(Float, nullable=True)     # C_sludge × Q_WAS
    mass_transformed  = Column(Float, nullable=True)     # mass_in - mass_eff - mass_sludge
    removal_pct       = Column(Float, nullable=True)     # removal efficiency %
    q_eff_mlday       = Column(Float, nullable=True)     # calculated Q_eff (Eq 2)
    notes             = Column(Text, nullable=True)

    experiment = relationship("Experiment", back_populates="mass_balance_results")

    def __repr__(self):
        return f"<MassBalanceResult id={self.id} cec={self.cec_name!r} removal={self.removal_pct}%>"


class SimulationRun(Base):
    """
    Stores one what-if simulation run — either Phase 1 (generic equations)
    or Phase 2 (data-driven scikit-learn model).
    Inputs are operating conditions; outputs are predicted removal efficiencies.
    """
    __tablename__ = "simulation_runs"

    id               = Column(Integer, primary_key=True, autoincrement=True)
    run_date         = Column(DateTime, default=utc_now)
    model_type       = Column(String, nullable=False)   # "generic" | "data_driven"

    # --- Input operating conditions ---
    flow_rate_mlh    = Column(Float, nullable=True)
    ras_ratio        = Column(Float, nullable=True)
    a_recycle        = Column(Float, nullable=True)
    do_mgl           = Column(Float, nullable=True)
    srt_days         = Column(Float, nullable=True)
    temp_c           = Column(Float, nullable=True)
    ph               = Column(Float, nullable=True)
    inf_cod          = Column(Float, nullable=True)     # influent COD (mg/L)
    inf_nh4          = Column(Float, nullable=True)     # influent NH4 (mg/L)
    inf_tp           = Column(Float, nullable=True)     # influent total phosphorus (mg/L)
    inf_pfas         = Column(Float, nullable=True)     # influent PFAS (ug/L)
    pfas_type        = Column(String, nullable=True)    # "short-chain" | "long-chain"

    # --- Output predictions ---
    pred_cod_removal  = Column(Float, nullable=True)   # predicted % COD removal
    pred_nh4_removal  = Column(Float, nullable=True)   # predicted % NH4 removal
    pred_tp_removal   = Column(Float, nullable=True)   # predicted % TP removal
    pred_pfas_removal = Column(Float, nullable=True)   # predicted % PFAS removal
    pred_eff_cod      = Column(Float, nullable=True)   # predicted effluent COD (mg/L)
    pred_eff_nh4      = Column(Float, nullable=True)   # predicted effluent NH4 (mg/L)
    pred_eff_tp       = Column(Float, nullable=True)   # predicted effluent TP (mg/L)
    pred_eff_pfas     = Column(Float, nullable=True)   # predicted effluent PFAS (ug/L)
    notes             = Column(Text, nullable=True)

    def __repr__(self):
        return f"<SimulationRun id={self.id} type={self.model_type!r} date={self.run_date}>"


class SludgeCharacterization(Base):
    """
    Weekly settleability and biomass characterization tests.

    Tracked separately from DailyReading because these tests are run
    weekly (not daily) and require a dedicated settling column test.
    SVI (Sludge Volume Index) is the key output — it indicates how well
    activated sludge settles and directly impacts clarifier design.

    SVI < 100 mL/g = good settling
    SVI 100-150    = acceptable
    SVI > 150      = bulking sludge — investigate
    """
    __tablename__ = "sludge_characterization"

    id                = Column(Integer, primary_key=True, autoincrement=True)
    experiment_id     = Column(Integer, ForeignKey("experiments.id"), nullable=False)
    test_date         = Column(Date, nullable=False)
    zone              = Column(String, nullable=False, default="aerobic")
    svi_30_ml_g       = Column(Float, nullable=True)   # 30-min SVI (mL/g MLSS)
    svi_5_ml_g        = Column(Float, nullable=True)   # 5-min SVI (mL/g MLSS)
    tsv_ml            = Column(Float, nullable=True)   # Total Settled Volume at 30 min (mL/L)
    settleability_pct = Column(Float, nullable=True)   # % settled in 30 min
    notes             = Column(Text, nullable=True)
    created_at        = Column(DateTime, default=utc_now)

    experiment = relationship("Experiment", back_populates="sludge_characterizations")

    def __repr__(self):
        return f"<SludgeCharacterization id={self.id} date={self.test_date} svi30={self.svi_30_ml_g}>"


class DaspoortMonitoring(Base):
    """
    Quarterly field measurements from Daspoort WWTP (Pretoria).
    Used in the Comparison dashboard to benchmark the lab reactor
    against the full-scale treatment plant.
    """
    __tablename__ = "daspoort_monitoring"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    sampling_date   = Column(Date, nullable=False)
    quarter         = Column(String, nullable=True)    # e.g. "Q1 2026"
    sampling_point  = Column(String, nullable=True)    # matches SP1–SP4
    cec_name        = Column(String, nullable=True)
    concentration   = Column(Float, nullable=True)     # ug/L
    cod_mgl         = Column(Float, nullable=True)
    nh4_mgl         = Column(Float, nullable=True)
    no3_mgl         = Column(Float, nullable=True)
    ph              = Column(Float, nullable=True)
    notes           = Column(Text, nullable=True)

    def __repr__(self):
        return f"<DaspoortMonitoring id={self.id} date={self.sampling_date} cec={self.cec_name!r}>"
