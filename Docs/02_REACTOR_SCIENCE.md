# Digital Reactor — Science & Process Reference

## Physical Reactor Specifications
- **Make:** Behrotest laboratory-scale wastewater plant
- **Standard:** OECD Guideline 303A (Testing of Chemicals)
- **Container volumes:** 3 × 4 litres glass containers
- **Configuration:** Continuous flow, synthetic wastewater feed

## Reactor Layout (Left to Right)
```
FEED → [ANAEROBIC] → [ANOXIC] → [AEROBIC] → [CLARIFIER] → EFFLUENT
             ↑                       |              |
             |         a-recycle ←───┘              |
             |                                      |
             └──────────── RAS ←────────────────────┘
                                                    |
                                                   WAS (daily waste)
```

## Operating Conditions (Table 7.2 from Proposal)
| Parameter | Value |
|-----------|-------|
| Flow rate | 320 mL/h |
| RAS recycle ratio | 1:1 |
| a-recycle ratio (mixed liquor) | 1:4 |
| Dissolved oxygen — aeration tank | 1–2 mg/L |
| Sludge age | 30 days |
| Temperature | 20–25 °C |
| pH | 7.5 |

---

## Zone-by-Zone Science

### 1. Anaerobic Zone
- **Oxygen:** None
- **Nitrate:** None
- **Key biological process:** Biological Phosphorus Removal (Bio-P)
  - Phosphorus Accumulating Organisms (PAOs) absorb volatile fatty
    acids and RELEASE phosphate here
- **For CECs:** Hydrophobic compounds (like long-chain PFAS) may begin
  adsorbing onto sludge particles in this zone
- **No** nitrification or denitrification occurring here

### 2. Anoxic Zone
- **Oxygen:** None
- **Nitrate:** Present (supplied via a-recycle from aerobic zone)
- **Key biological process:** Denitrification
  - Bacteria use NO₃ as electron acceptor instead of O₂
  - Nitrate → Nitrogen gas (N₂) which escapes to atmosphere
  - This is why the a-recycle ratio is critical — it controls how
    much nitrate gets recycled back here
- **For CECs:** Biodegradable CECs may begin breaking down depending
  on their molecular structure and susceptibility to anaerobic/anoxic
  degradation

### 3. Aerobic Zone
- **Oxygen:** 1–2 mg/L (automatically controlled by DO probe)
- **Key biological processes:**
  1. **Nitrification:** NH₄ → NO₂ → NO₃ (by nitrifying bacteria)
  2. **COD removal:** Aerobic bacteria consume organic matter
  3. **Phosphate uptake:** PAOs take up phosphate (opposite of
     anaerobic zone) — luxury uptake
- **For CECs:**
  - Some aerobic biodegradation of susceptible compounds
  - **PFAS specifically resist this** — the C-F bond (carbon-fluorine)
    is one of the strongest bonds in organic chemistry. Biological
    processes cannot break it. PFAS either pass through to effluent
    or adsorb onto sludge.
- **a-recycle** pumps mixed liquor from HERE back to anoxic zone

### 4. Clarifier
- **Biological activity:** None — purely physical settling
- **Process:** Sludge settles by gravity, clear effluent overflows
- **RAS:** Settled sludge pumped back to anaerobic zone to maintain
  biomass (MLSS target)
- **WAS:** Excess sludge wasted daily to control sludge age (30 days)
- **For CECs:** Whatever has adsorbed onto sludge particles concentrates
  here. Critical for PFAS — what doesn't dissolve ends up in sludge.

---

## PFAS-Specific Science (Key Research Focus)

### Why PFAS Are Problematic
- **C-F bond** is the strongest bond in organic chemistry
- Biological processes in the reactor **cannot break it**
- Therefore PFAS are **not biodegraded** — they either:
  1. Pass straight through into effluent (especially short-chain PFAS)
  2. Adsorb onto sludge (especially long-chain PFAS)

### Long-chain vs Short-chain PFAS
| Type | Examples | Behaviour in reactor |
|------|----------|---------------------|
| Long-chain | PFOS, PFOA | More hydrophobic, stick to sludge |
| Short-chain | PFBS, PFBA | More water-soluble, pass to effluent |

> **Note:** Long-chain PFAS are now restricted. Mahlatse is specifically
> targeting short-chain PFAS (SCCPs) because information on their
> presence in South African water resources is scarce.

### Why This Research Matters
- The activated sludge process was **never designed** to remove PFAS
- Studying exactly HOW they behave in each zone is new knowledge
- Especially valuable in South African context where CEC regulations
  are in their infancy or non-existent

---

## Parameters Measured Daily
- Dissolved Oxygen (DO) — mg/L
- pH
- COD (Chemical Oxygen Demand) — mg/L
- Ammonia (NH₄) — mg/L
- Nitrate (NO₃) — mg/L
- Sulfate (SO₄) — mg/L
- Phosphate (PO₄) — mg/L
- Temperature — °C
- MLSS (Mixed Liquor Suspended Solids) — mg/L

## CEC Sampling Points (Table 7.1 from Proposal)
| Point | Location |
|-------|----------|
| SP1 | Influent (feed into anaerobic zone) |
| SP2 | Primary settling inlet (upstream) |
| SP3 | Clarifier tank |
| SP4 | Final effluent (discharge point) |

> Quarterly monitoring also done at Daspoort WWTP at same points
> for comparison against lab reactor results.
