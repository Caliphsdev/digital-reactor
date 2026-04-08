# Digital Reactor — App Architecture & Database Schema

## Folder Structure
```
digital-reactor/
│
├── main.py                  # App entry point
├── requirements.txt         # All dependencies
├── reactor.db               # SQLite database (auto-created on first run)
│
├── core/
│   ├── __init__.py
│   ├── database.py          # SQLAlchemy setup and session management
│   ├── models.py            # All database table models
│   └── calculations.py      # Mass balance + removal efficiency functions
│
├── simulation/
│   ├── __init__.py
│   ├── generic_model.py     # Phase 1 — textbook equation model
│   └── data_model.py        # Phase 2 — scikit-learn trained model
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py       # Main application window
│   ├── reactor_diagram.py   # QPainter reactor visualisation widget
│   ├── data_entry.py        # Daily measurement input forms
│   ├── cec_tracker.py       # CEC concentration entry and tracking
│   ├── mass_balance.py      # Mass balance calculator screen
│   ├── simulation_screen.py # Phase 1 & Phase 2 what-if simulator
│   ├── dashboard.py         # Comparison dashboard + charts
│   └── reports.py           # Export results to CSV / charts
│
├── assets/
│   ├── styles.qss           # PySide6 stylesheet
│   └── icons/               # App icons
│
└── docs/                    # Copy of these .md planning files
```

---

## Database Schema (SQLAlchemy Models)

### Table: experiments
Represents a single experimental run (reactor startup to shutdown).
```python
class Experiment(Base):
    id            = Integer, primary key
    name          = String   # e.g. "Run 1 - PFOS spike 50ug/L"
    start_date    = Date
    end_date      = Date (nullable)
    description   = Text
    cec_spiked    = String   # which CECs were added
    spike_conc    = Float    # concentration spiked (ug/L)
    notes         = Text
    created_at    = DateTime
```

### Table: daily_readings
One row per day per zone per experiment.
```python
class DailyReading(Base):
    id             = Integer, primary key
    experiment_id  = ForeignKey(Experiment)
    reading_date   = Date
    zone           = String  # "anaerobic" | "anoxic" | "aerobic" | "effluent"
    do_mgl         = Float   # Dissolved oxygen (mg/L)
    ph             = Float
    temperature_c  = Float
    cod_mgl        = Float   # Chemical Oxygen Demand (mg/L)
    nh4_mgl        = Float   # Ammonia (mg/L)
    no3_mgl        = Float   # Nitrate (mg/L)
    so4_mgl        = Float   # Sulfate (mg/L)
    po4_mgl        = Float   # Phosphate (mg/L)
    mlss_mgl       = Float   # Mixed Liquor Suspended Solids (mg/L)
    notes          = Text
    created_at     = DateTime
```

### Table: flow_readings
Daily flow measurements for mass balance calculations.
```python
class FlowReading(Base):
    id               = Integer, primary key
    experiment_id    = ForeignKey(Experiment)
    reading_date     = Date
    q_in_mlh         = Float  # Influent flow (mL/h)
    q_was_mlh        = Float  # Waste activated sludge flow (mL/h)
    q_psludge_mlh    = Float  # Primary sludge flow (mL/h)
    ras_ratio        = Float  # RAS recycle ratio
    a_recycle_ratio  = Float  # a-recycle ratio
    notes            = Text
```

### Table: cec_readings
CEC concentrations at each sampling point.
```python
class CECReading(Base):
    id              = Integer, primary key
    experiment_id   = ForeignKey(Experiment)
    reading_date    = Date
    cec_name        = String  # e.g. "PFOS", "PFBA", "PFBS"
    cec_type        = String  # "short-chain" | "long-chain"
    sampling_point  = String  # "SP1_influent" | "SP2_primary" |
                              # "SP3_clarifier" | "SP4_effluent"
    concentration   = Float   # ug/L
    below_detection = Boolean # True if below detection limit
    detection_limit = Float   # instrument detection limit (ug/L)
    analysis_method = String  # "TOF-MS" | "GC-MS"
    notes           = Text
    created_at      = DateTime
```

### Table: mass_balance_results
Calculated results — auto-generated, not manually entered.
```python
class MassBalanceResult(Base):
    id               = Integer, primary key
    experiment_id    = ForeignKey(Experiment)
    calculation_date = Date
    cec_name         = String
    mass_in_mgday    = Float  # C_inf × Q_in
    mass_eff_mgday   = Float  # C_eff × Q_eff (Equation 1)
    mass_sludge_mgday= Float  # C_sludge × Q_WAS
    mass_transformed = Float  # mass_in - mass_eff - mass_sludge
    removal_pct      = Float  # removal efficiency %
    q_eff_mlday      = Float  # calculated Q_eff (Equation 2)
    notes            = Text
```

### Table: simulation_runs
Stores Phase 1 generic model runs (what-if scenarios).
```python
class SimulationRun(Base):
    id              = Integer, primary key
    run_date        = DateTime
    model_type      = String   # "generic" | "data_driven"
    # Input conditions
    flow_rate_mlh   = Float
    ras_ratio       = Float
    a_recycle       = Float
    do_mgl          = Float
    srt_days        = Float
    temp_c          = Float
    ph              = Float
    inf_cod         = Float
    inf_nh4         = Float
    inf_tp          = Float
    inf_pfas        = Float
    pfas_type       = String   # "short-chain" | "long-chain"
    # Output predictions
    pred_cod_removal  = Float  # predicted % removal
    pred_nh4_removal  = Float
    pred_tp_removal   = Float
    pred_pfas_removal = Float
    pred_eff_cod      = Float  # predicted effluent concentration
    pred_eff_nh4      = Float
    pred_eff_tp       = Float
    pred_eff_pfas     = Float
    notes             = Text
```

### Table: daspoort_monitoring
Quarterly Daspoort WWTP field data for comparison.
```python
class DaspoortMonitoring(Base):
    id               = Integer, primary key
    sampling_date    = Date
    quarter          = String   # "Q1 2026", "Q2 2026" etc.
    sampling_point   = String   # matches SP1–SP4
    cec_name         = String
    concentration    = Float    # ug/L
    cod_mgl          = Float
    nh4_mgl          = Float
    no3_mgl          = Float
    ph               = Float
    notes            = Text
```

---

## App Screens (UI Navigation)

```
Main Window
│
├── 🏠 Home / Dashboard
│     └── Live reactor diagram + today's key metrics
│
├── 📋 Experiments
│     ├── New experiment setup
│     ├── Active experiment
│     └── Experiment history
│
├── 📊 Daily Log
│     ├── Enter today's readings (per zone)
│     ├── Enter flow measurements
│     └── View log history + charts
│
├── 🧪 CEC Tracker
│     ├── Enter CEC concentrations per sampling point
│     ├── Removal efficiency across treatment train
│     └── CEC fate chart (SP1 → SP2 → SP3 → SP4)
│
├── ⚖️ Mass Balance
│     ├── Auto-calculated from logged data
│     ├── Equation 1 & 2 results displayed
│     └── Fate breakdown (effluent / sludge / transformed)
│
├── 🔬 Simulation
│     ├── Phase 1: Generic model (always active)
│     ├── Phase 2: Data-driven model (activates when enough data)
│     └── What-if scenario runner
│
├── 📈 Comparison
│     ├── Lab reactor vs Daspoort WWTP
│     ├── Generic model vs Data-driven vs Actual
│     └── Export charts
│
└── ⚙️ Settings
      ├── Operating conditions defaults
      ├── Detection limits per instrument
      └── Export / backup database
```

---

## Dependencies (requirements.txt)
```
PySide6>=6.6.0
SQLAlchemy>=2.0.0
matplotlib>=3.7.0
pyqtgraph>=0.13.0
scikit-learn>=1.3.0
pandas>=2.0.0
numpy>=1.24.0
openpyxl>=3.1.0
```
