# Digital Reactor — Equations & Calculations Reference

## Source
All equations taken directly from the PhD proposal (Sekhula-Mojela, 2026).
Sections 7.6 and 7.3.

---

## Core Mass Balance Equations

### Equation 1 — Mass Load
```
Mass load (mg/day) = C_eff × Q_eff
```
**Where:**
- `C_eff` = effluent concentration of the compound (mg/ML)
- `Q_eff` = effluent flow rate (ML/day)

**What it means:**
How much of a CEC is leaving the system per day in the treated water.
Multiply concentration by flow rate to get total mass leaving per day.

---

### Equation 2 — Effluent Flow Rate
```
Q_eff = Q_in - Q_Psludge - Q_WAS
```
**Where:**
- `Q_eff`     = effluent flow rate (ML/day)
- `Q_in`      = influent flow rate (ML/day)
- `Q_Psludge` = primary sludge flow rate (ML/day)
- `Q_WAS`     = waste activated sludge flow rate (ML/day)

**What it means:**
Effluent flow cannot be measured directly so it is calculated.
Total water in minus what left as primary sludge minus what left
as waste activated sludge = what came out as treated effluent.
This is conservation of mass applied to water flow.

---

## Derived Calculations (Not in Proposal — Standard Practice)

### Removal Efficiency
```
Removal (%) = ((C_inf - C_eff) / C_inf) × 100
```
**Where:**
- `C_inf` = influent concentration of compound (mg/L)
- `C_eff` = effluent concentration of compound (mg/L)

**What it means:**
What percentage of the CEC was removed by the treatment process.
Higher = better removal. For PFAS, expect low values (poor removal).

---

### Full Mass Balance (Fate Determination)
```
Mass_in = Mass_effluent + Mass_sludge + Mass_transformed
```
**Where:**
- `Mass_in`          = C_inf × Q_in
- `Mass_effluent`    = C_eff × Q_eff         (Equation 1)
- `Mass_sludge`      = C_sludge × Q_WAS
- `Mass_transformed` = Mass_in - Mass_effluent - Mass_sludge

**What it means:**
If Mass_in ≠ Mass_effluent + Mass_sludge, something happened:
- Positive difference → CEC biodegraded or volatilised
- Negative difference → CEC is accumulating somewhere in the system
- For PFAS: expect accumulation in sludge, not biodegradation

---

### Sludge Age (SRT — Solids Retention Time)
```
SRT (days) = Total sludge in system (g) / Sludge wasted per day (g/day)
```
Target SRT = 30 days (as per Table 3.1 / Table 7.2 of proposal)

---

### Mass Load at Each Sampling Point
```
Mass_SP(n) (mg/day) = C_SP(n) × Q_SP(n)
```
Calculate at each of the 4 sampling points to track CEC fate
through the treatment train:
- SP1 → SP2 → SP3 → SP4
- Difference between consecutive points = what was removed in that stage

---

## Unit Conversions Used in This Project
| From | To | Factor |
|------|----|--------|
| mL/h | L/day | × 0.024 |
| L/day | ML/day | ÷ 1,000,000 |
| mg/L | mg/mL | ÷ 1000 |
| mL/h (320) | L/day | = 7.68 L/day |

> The reactor runs at 320 mL/h = 7.68 L/day influent flow rate

---

## Statistical Methods (Section 7.8 of Proposal)
- **Software:** IBM SPSS + Microsoft Excel (current plan)
  → Our app will handle this instead
- **Reliability test:** Test-retest method over 2 months
  - Results must correlate with score > 0.60 to be reliable
- **Significance test:** Paired sample t-test (comparing two sets
  of results — e.g. lab reactor vs Daspoort WWTP)
- **Descriptive statistics:** Mean, standard deviation, min, max
  per parameter per zone per experimental run

---

## Phase 1 Generic Model Equations

### COD Removal (Aerobic biological treatment)
```
COD_removal (%) = 1 - (1 / (1 + k_COD × HRT))
```
Where `k_COD` is the first-order removal rate constant (~0.5–2.0 /day)
and HRT is hydraulic retention time in days.

### Nitrification (NH₄ → NO₃)
```
NH4_removal (%) = min(0.98, 0.55 + DO × 0.12 + SRT × 0.01)
```
Increases with dissolved oxygen and sludge age.

### Denitrification (NO₃ → N₂)
```
NO3_removal (%) = min(0.85, 0.30 + (a_recycle / 6) × 0.40)
```
Increases with a-recycle ratio.

### Phosphorus Removal (Bio-P)
```
TP_removal (%) = min(0.92, 0.40 + a_recycle × 0.08)
```

### PFAS Removal (Generic — Conservative Estimate)
```
PFAS_removal (%) = adsorption_fraction × 100
adsorption_fraction = Kd × MLSS / (1 + Kd × MLSS)
```
Where `Kd` is the solid-water partition coefficient (compound-specific).
For short-chain PFAS: Kd is very low → most passes to effluent.
For long-chain PFAS: Kd is higher → more adsorbs to sludge.

> Phase 1 generic values are **textbook estimates only**.
> They serve as a directional guide and hypothesis generator.
> Phase 2 will replace these with values fitted to real data.
