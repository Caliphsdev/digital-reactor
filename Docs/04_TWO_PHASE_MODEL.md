# Digital Reactor — Two-Phase Model Plan

## The Core Idea
Two simulation models run side by side on the same platform:
- **Phase 1** is active immediately (generic, textbook-based)
- **Phase 2** activates after 6–12 months of real experimental data

The gap between Phase 1 predictions and Phase 2 predictions
tells a scientific story — and that story is a chapter in the PhD.

---

## Phase 1 — Generic Model

### When: Now (before experiments start)
### Purpose:
- Give Mahlatse a directional guide before the reactor runs
- Help plan experimental conditions
- Generate hypotheses before each run
  - *"Theory says at DO=2 mg/L and SRT=30 days I should see ~85%
    COD removal — let's test if that holds with PFAS present"*
- Provide a benchmark — when real results deviate from the generic
  model, THAT deviation is scientifically interesting
- Acts as a **hypothesis generator**

### How it works:
- Uses standard wastewater treatment equations (see 03_EQUATIONS.md)
- Uses OECD 303A guideline parameters as defaults
- User inputs operating conditions (DO, SRT, flow rate, recycle ratios)
- Model outputs expected removal efficiencies per parameter
- For PFAS: uses solid-water partition coefficient (Kd) approach
  with literature values for short-chain and long-chain PFAS

### Inputs:
- Flow rate (mL/h)
- RAS ratio
- a-recycle ratio
- Dissolved oxygen (mg/L)
- Sludge age / SRT (days)
- Influent concentrations (COD, NH₄, NO₃, TP, PFAS)
- PFAS type (short-chain / long-chain) for Kd selection
- Temperature (°C)
- pH

### Outputs:
- Expected effluent concentrations per parameter
- Expected removal efficiency (%) per parameter
- Expected mass load at each sampling point
- Warning flags if operating conditions are outside optimal range

---

## Phase 2 — Data-Driven Model

### When: After 6–12 months of real experimental data
### Trigger: Minimum ~50–100 data points per parameter
### Purpose:
- Replace textbook equations with model trained on HER reactor data
- Make what-if predictions based on actual observed behaviour
- Reveal how her specific reactor, sludge, and CECs behave
  vs what theory predicted

### How it works:
- Uses **scikit-learn** regression models
- Training data: all logged daily measurements from the app database
- Features (X): operating conditions (DO, SRT, flow, recycle ratios,
  temperature, pH, influent concentrations)
- Targets (y): removal efficiencies per parameter (COD, NH₄, TP, PFAS)
- Model selection: start with Random Forest Regressor (handles
  non-linear relationships well, robust with small datasets)
- Cross-validation to prevent overfitting on limited data

### Model upgrade path:
| Data points available | Recommended model |
|----------------------|-------------------|
| 50–100 | Linear Regression (simple, interpretable) |
| 100–200 | Random Forest Regressor |
| 200+ | Gradient Boosting or Neural Network |

### What-if engine (Phase 2):
User adjusts a slider (e.g. increase SRT from 30 to 45 days) and
the trained model predicts what the new removal efficiencies would be.
This is scientifically valid because it is based on HER real data.

---

## Side-by-Side Comparison Dashboard

### The most important feature of the whole app:

```
Parameter    | Generic Model | Data-Driven | Actual Measured | Deviation
-------------|---------------|-------------|-----------------|----------
COD removal  | 92%           | 87%         | 85%             | -7%
PFAS removal | 15%           | 22%         | 19%             | +4%
NH₄ removal  | 88%           | 91%         | 90%             | +2%
```

### Why this matters scientifically:
- Large deviations between Generic and Data-Driven = the real reactor
  behaves differently from theory
- Investigating WHY = a discussion chapter in the PhD
- Example finding: *"Generic model predicted 15% PFAS removal based
  on literature Kd values. However, observed removal was consistently
  22%, suggesting the specific sludge microbial community at DWWTP
  may have some capacity for short-chain PFAS biotransformation under
  extended SRT conditions."*

---

## Development Timeline

### Months 1–3 (Now):
- Build the full app with Phase 1 generic model active
- Data logging, mass balance calculator, reactor visualisation
- Mahlatse begins logging daily measurements

### Months 6–9:
- Enough data to attempt first Phase 2 model
- Train initial scikit-learn model, evaluate performance
- Add Phase 2 predictions to comparison dashboard

### Months 12+:
- Phase 2 model is robust and reliable
- What-if simulator is scientifically valid
- Comparison dashboard shows meaningful deviations
- Model itself may be a publishable contribution

### 2028 (Thesis submission):
- All data stored in app database
- All charts and tables generated from app
- Mass balance calculations verified and auditable
