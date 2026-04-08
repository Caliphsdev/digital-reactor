# Digital Reactor — Project Overview

## What This Is
A PySide6 desktop application that serves as a **digital twin** of a
laboratory-scale activated sludge reactor being used in a PhD study at
Tshwane University of Technology (TUT), Pretoria, South Africa.

## The Research Context
- **Researcher:** Mahlatse Mapula Sekhula-Mojela
- **Degree:** Doctor of Philosophy — Environmental Sciences (TUT)
- **Supervisors:** Prof. O.J. Okonkwo, Prof. L. Mpenyana-Monyatsi
- **Study duration:** 2026 – 2028
- **Base plant:** Daspoort Wastewater Treatment Plant (DWWTP), Pretoria
  - Built 1913–1920
  - Operational capacity: 55 ML/day

## The Core Research Question
What happens to PFAS (per- and polyfluoroalkyl substances) and other
Contaminants of Emerging Concern (CECs) when they pass through a
wastewater treatment plant? Do they get removed, partially removed,
transformed, or do they escape into the environment? What happens when
multiple CECs exist together — do they interact (synergistic effects)?

## Why a Lab Reactor?
Rather than studying the full-scale Daspoort plant (uncontrollable
variables), Mahlatse uses a **Behrotest laboratory-scale reactor** with
three 4-litre glass containers to simulate a real WWTP under controlled
conditions. The reactor is **spiked with predetermined concentrations**
of CECs so experiments are repeatable and measurable.

## The Two Physical Reactors
1. **Activated sludge reactor** — three biological zones + clarifier
   (the main focus, shown in photos)
2. **Anaerobic digestion reactor** — separate setup to study CECs
   adsorbed onto sludge (sludge side is often ignored in CEC research)

## What the Digital Reactor Must Do
1. **Visualise** the reactor layout accurately (matching the physical setup)
2. **Log** daily measurements per zone and sampling point
3. **Calculate** mass balance automatically using the proposal equations
4. **Track** CEC concentrations across all sampling points
5. **Simulate** expected behaviour (Phase 1: generic model)
6. **Predict** behaviour from real data (Phase 2: data-driven model)
7. **Compare** lab results vs Daspoort WWTP quarterly monitoring data

## Technology Stack
- **UI & visualisation:** PySide6
- **Database:** SQLite (local, single file, no server needed)
- **ORM:** SQLAlchemy (or Django ORM if preferred)
- **Charts:** PyQtGraph or Matplotlib embedded in PySide6
- **ML (Phase 2):** scikit-learn
- **Target OS:** Windows (lab computer)
