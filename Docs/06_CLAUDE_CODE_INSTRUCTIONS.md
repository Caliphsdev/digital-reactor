# Digital Reactor — Claude Code Instructions

## How to Use This Document
Paste the context block below as your FIRST message when starting
a new Claude Code session. This gives Claude everything it needs
to continue building without losing context.

---

## Context Block (paste this at the start of every Claude Code session)

```
I am building a PySide6 desktop application called the "Digital Reactor".
It is a digital twin of a laboratory-scale activated sludge reactor used
in a PhD study on PFAS and Contaminants of Emerging Concern (CECs) at
Tshwane University of Technology (TUT), Pretoria, South Africa.

RESEARCHER: Mahlatse Mapula Sekhula-Mojela (PhD Environmental Sciences)
PHYSICAL REACTOR: Behrotest lab-scale plant, 3 × 4L glass containers,
running under OECD 303A guidelines.

REACTOR LAYOUT:
FEED → [ANAEROBIC] → [ANOXIC] → [AEROBIC] → [CLARIFIER] → EFFLUENT
with RAS loop (clarifier back to anaerobic) and a-recycle (aerobic
back to anoxic) and daily WAS (waste activated sludge).

OPERATING CONDITIONS:
- Flow rate: 320 mL/h
- RAS ratio: 1:1
- a-recycle ratio: 1:4
- DO in aerobic zone: 1-2 mg/L
- Sludge age: 30 days
- Temperature: 20-25°C, pH: 7.5

TECH STACK: PySide6, SQLite, SQLAlchemy, PyQtGraph/Matplotlib,
scikit-learn (Phase 2). Target OS: Windows.

TWO-PHASE MODEL:
- Phase 1 (now): Generic textbook equations for removal estimation
- Phase 2 (6-12 months): scikit-learn model trained on real data

MASS BALANCE EQUATIONS (from proposal):
- Eq1: Mass load (mg/day) = C_eff × Q_eff
- Eq2: Q_eff = Q_in - Q_Psludge - Q_WAS
- Removal %: ((C_inf - C_eff) / C_inf) × 100

All planning docs are in the /docs folder of this project.
```

---

## Build Order (Screen by Screen)

Follow this order. Complete and test each step before moving to the next.

### Step 1 — Project scaffold
```
Create the folder structure from 05_ARCHITECTURE.md.
Set up main.py, requirements.txt, and the core/ database module.
Create all SQLAlchemy models from the schema in 05_ARCHITECTURE.md.
Test that the database creates successfully on first run.
```

### Step 2 — Main window shell
```
Build main_window.py with a sidebar navigation and content area.
Navigation items: Home, Experiments, Daily Log, CEC Tracker,
Mass Balance, Simulation, Comparison, Settings.
No content yet — just the shell with placeholder screens.
```

### Step 3 — Reactor diagram (QPainter)
```
Build reactor_diagram.py as a custom QWidget using QPainter.
Draw: three circles (anaerobic=purple, anoxic=blue, aerobic=green),
one triangle (clarifier=grey), connecting pipes with arrows,
RAS loop below, a-recycle loop above, WAS outlet, feed inlet,
effluent outlet, sampling point markers (SP1-SP4), zone labels.
Make it scale with window resize.
Animate flow with a QTimer (pulsing arrows every 500ms).
Show today's DO and pH values as overlaid text on each zone
if data exists for today.
```

### Step 4 — Experiment management
```
Build experiments.py screen.
New experiment form: name, start date, CECs being spiked,
spike concentration, description.
List of all experiments with status (active/complete).
Ability to set one experiment as "active" — all data entry
links to the active experiment.
```

### Step 5 — Daily data entry
```
Build data_entry.py screen.
Form with tabs for each zone: Anaerobic, Anoxic, Aerobic, Effluent.
Fields per zone: DO, pH, temperature, COD, NH4, NO3, SO4, PO4, MLSS.
Separate section for flow readings: Q_in, Q_WAS, Q_Psludge,
RAS ratio, a-recycle ratio.
Save to database. Show last 7 days as a table below the form.
Highlight values outside normal operating range in red.
```

### Step 6 — CEC tracker
```
Build cec_tracker.py screen.
Entry form: date, CEC name, CEC type (short/long chain),
concentration at each of the 4 sampling points (SP1-SP4),
below detection limit checkbox, detection limit value,
analysis method.
Show removal efficiency across treatment train automatically.
Plot concentration profile SP1 → SP2 → SP3 → SP4 as a line chart.
```

### Step 7 — Mass balance calculator
```
Build mass_balance.py screen.
Auto-populate from logged flow readings and CEC readings.
Show Equation 1 and 2 calculations with values filled in.
Show fate breakdown: % to effluent, % to sludge, % transformed.
Save results to mass_balance_results table.
Export to CSV button.
```

### Step 8 — Phase 1 generic simulation
```
Build simulation_screen.py with Phase 1 tab.
Sliders for all operating parameters (flow, DO, SRT, recycle ratios).
Input fields for influent concentrations (COD, NH4, TP, PFAS).
PFAS type selector (short-chain / long-chain).
Run button → calculates and displays predicted effluent concentrations
and removal efficiencies using equations from 03_EQUATIONS.md.
Show warning flags if parameters are outside recommended ranges.
Save simulation run to simulation_runs table.
```

### Step 9 — Comparison dashboard
```
Build dashboard.py screen.
Chart 1: Lab reactor removal % vs Daspoort WWTP removal % over time.
Chart 2: Generic model prediction vs actual measured values.
Chart 3: CEC concentration trends over experiment duration.
Chart 4: Daily parameter trends per zone (DO, pH, COD over time).
Export charts as PNG button.
```

### Step 10 — Phase 2 data-driven model
```
Build data_model.py in simulation/.
Load all logged data from database into a pandas DataFrame.
Check if enough data exists (minimum 50 rows) — if not, show
a message: "X more readings needed before data-driven model
can be trained."
If enough data: train a scikit-learn RandomForestRegressor.
Features: DO, SRT, flow, recycle ratios, temperature, pH, inf conc.
Targets: removal efficiency per parameter.
Show model performance metrics (R², MAE).
Add Phase 2 tab to simulation_screen.py — same slider interface
as Phase 1 but using trained model for predictions.
Add Phase 2 column to comparison dashboard.
```

---

## Important Notes for Claude Code

1. **Always include comments** in every function and class — the
   developer needs to follow along and maintain the code.

2. **Use SQLAlchemy ORM** — never raw SQL queries.

3. **Show placement markers** — when adding code snippets always
   indicate which file and which function they belong to.

4. **Explain before fixing** — when debugging, explain the cause
   of the bug before writing the fix.

5. **One screen at a time** — complete and test each step before
   starting the next. Don't build everything at once.

6. **PySide6 signals and slots** — use proper Qt signal/slot
   connections, not direct function calls between UI components.

7. **Error handling** — all database operations must be wrapped
   in try/except blocks. All numeric inputs must be validated
   before saving.

8. **The researcher is not a developer** — the UI must be
   extremely simple and intuitive. No technical jargon visible
   to the user. Use plain labels like "Today's Readings" not
   "Insert DailyReading record".
