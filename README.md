# Digital Reactor 🔬

A desktop research application for tracking the fate and removal of **PFAS (per- and polyfluoroalkyl substances)** and other **Contaminants of Emerging Concern (CECs)** through a lab-scale activated sludge wastewater treatment reactor.

Built for PhD research at the **Department of Environmental Management**, as a digital companion to a physical lab reactor designed to OECD Guideline 303A standards.

---

## Features

- **Live Reactor Diagram** — Animated process flow showing all zones, recycle streams, and sampling points with real-time data overlays
- **Experiment Management** — Create and manage experimental runs; link all data to a specific experiment
- **Daily Log** — Enter water quality measurements per zone (DO, pH, COD, NH₄, NO₃, PO₄, MLSS, and 9 advanced parameters including VSS, ORP, Alkalinity, OUR, BOD, Total-N/P)
- **CEC Tracker** — Log PFAS/CEC concentrations at 4 sampling points with automatic removal efficiency calculations
- **Mass Balance Calculator** — Quantify CEC fate: effluent vs sludge vs transformation using proposal equations
- **Simulation** — Phase 1 generic model (textbook equations); Phase 2 data-driven ML model (activates after ≥50 data points)
- **Comparison Dashboard** — Lab reactor vs Daspoort WWTP field data across 4 chart tabs
- **Process Metrics** — Automatic calculation of HRT, actual SRT, F:M ratio, and nitrifier washout risk
- **Built-in Manual** — 13-topic in-app reference covering all equations, process science, and how-to guides
- **Data Safety** — Automatic schema migrations (data survives app updates), one-click backup/restore, Excel export
- **Settings** — Backup management, simulation defaults, about screen

---

## Reactor Configuration

| Property | Value |
|---|---|
| Reactor type | Lab-scale Activated Sludge |
| Standard | OECD Guideline 303A |
| Total volume | 12 L (3 zones × 4 L) |
| Configuration | Anaerobic → Anoxic → Aerobic → Clarifier |
| Design flow | 320 mL/h |
| Target SRT | 30 days |
| RAS ratio | 1:1 |
| a-recycle ratio | 1:4 |

---

## Tech Stack

| Layer | Technology |
|---|---|
| UI Framework | [PySide6](https://doc.qt.io/qtforpython/) (Qt 6 for Python) |
| Database | SQLite + [SQLAlchemy](https://www.sqlalchemy.org/) ORM |
| Charts | [PyQtGraph](https://www.pyqtgraph.org/) + Matplotlib |
| ML (Phase 2) | [scikit-learn](https://scikit-learn.org/) |
| Data processing | Pandas, NumPy |
| Excel export | OpenPyXL |
| Icons | [qtawesome](https://github.com/spyder-ide/qtawesome) (Font Awesome 6) |

---

## Installation

### Prerequisites

- Python 3.11 or later
- Windows 10/11 (developed and tested on Windows)

### Setup

```bash
# 1. Clone the repository
git clone https://github.com/your-username/digital-reactor.git
cd digital-reactor

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate the virtual environment
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt

# 5. Run the app
python main.py
```

On first run, `reactor.db` is created automatically in the project folder with all required tables.

---

## Project Structure

```
digital-reactor/
│
├── main.py                    # Application entry point
├── requirements.txt           # Python dependencies
│
├── core/                      # Data layer (no UI dependencies)
│   ├── models.py              # SQLAlchemy ORM models (8 tables)
│   ├── database.py            # Engine, session manager, init_db()
│   ├── calculations.py        # Pure scientific calculation functions
│   └── migrations.py         # Incremental schema migration runner
│
├── simulation/                # Scientific models
│   ├── generic_model.py       # Phase 1: textbook equations (OECD 303A)
│   └── data_model.py          # Phase 2: scikit-learn ML (placeholder)
│
├── ui/                        # PySide6 screens and widgets
│   ├── main_window.py         # Main window + collapsible sidebar
│   ├── theme.py               # Centralized stylesheet and colors
│   ├── home_screen.py         # Live reactor diagram + process metrics
│   ├── reactor_diagram.py     # Animated QPainter reactor visualization
│   ├── experiments.py         # Experiment CRUD management
│   ├── data_entry.py          # Daily measurement input (zone tabs)
│   ├── cec_tracker.py         # CEC concentration tracking
│   ├── mass_balance.py        # Mass balance calculator
│   ├── simulation_screen.py   # Phase 1 & 2 simulator
│   ├── dashboard.py           # Comparison dashboard (4 chart tabs)
│   ├── settings.py            # Backup, defaults, about
│   ├── help_screen.py         # Built-in user manual (13 topics)
│   └── docking_utils.py       # Qt docking widget helpers
│
└── Docs/                      # Scientific documentation
    ├── 01_PROJECT_OVERVIEW.md
    ├── 02_REACTOR_SCIENCE.md
    ├── 03_EQUATIONS.md
    ├── 04_TWO_PHASE_MODEL.md
    └── 05_ARCHITECTURE.md
```

---

## Database

The app uses a local SQLite database (`reactor.db`) with 8 tables:

| Table | Purpose |
|---|---|
| `experiments` | Experimental runs (startup to shutdown) |
| `daily_readings` | Zone water quality measurements (18 parameters) |
| `flow_readings` | Flow rates for mass balance |
| `cec_readings` | CEC concentrations at 4 sampling points |
| `mass_balance_results` | Auto-calculated CEC fate results |
| `simulation_runs` | Saved what-if simulation scenarios |
| `daspoort_monitoring` | Quarterly Daspoort WWTP field data |
| `sludge_characterization` | Weekly SVI settling test results |

> **Note:** `reactor.db` is excluded from version control (`.gitignore`) as it contains research data. Back it up regularly using **Settings → Data Management → Backup Now**.

### Schema Migrations

New app versions may add database columns. The migration system (`core/migrations.py`) runs automatically on startup — existing data is **never deleted**. New columns appear as blank for old rows until values are entered.

---

## Scientific Equations

All equations are documented in `Docs/03_EQUATIONS.md` and in the built-in Manual (sidebar → **Manual**). Key equations:

```
Mass load:     mass (µg/day) = C (µg/L) × Q (mL/h) × 24 / 1000
Effluent flow: Q_eff = Q_in − Q_psludge − Q_WAS
Removal:       % = (C_inf − C_eff) / C_inf × 100
HRT:           HRT (h) = V_reactor / Q_in
SRT:           SRT (days) = V_reactor / Q_WAS
F:M ratio:     F:M = (COD_inf × Q_in) / (MLVSS × V_reactor)
PFAS removal:  fraction = (Kd × MLSS_kg/L) / (1 + Kd × MLSS_kg/L)
Temp. factor:  Rate_T = Rate_20°C × 1.06^(T − 20)
```

---

## Data Safety

Before installing a new app version:

1. Open **Settings → Data Management**
2. Click **Backup Now**
3. Install the new version — schema migrations run automatically
4. If anything goes wrong, use **Restore** to recover from the backup

---

## Developer

**Caliphs Zvinowanda**
📞 +27 65 235 7607

---

## Version

**v1.0** — Initial release
- Core data entry and tracking screens
- Phase 1 generic simulation model
- Built-in manual (13 topics)
- Automatic schema migration system
- Backup / restore / Excel export
