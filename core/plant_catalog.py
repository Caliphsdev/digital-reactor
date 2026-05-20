"""
plant_catalog.py — seeded real-plant profiles for the Scientific Twin module.

Only three South African plants are included in V1:
  * Daspoort WWTW
  * Zeekoegat WWTW
  * Phola WWTP

The values below are literature/default assumptions. Measured field data should
override them in calibration workflows once plant datasets are available.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import Plant, PlantSamplingPoint, PlantUnit


@dataclass(frozen=True)
class UnitSeed:
    order: int
    name: str
    unit_type: str
    role: str
    hrt_hours: float | None
    notes: str


@dataclass(frozen=True)
class SamplingSeed:
    order: int
    code: str
    name: str
    after_unit_order: int
    description: str


DEFAULT_PLANTS: list[dict] = [
    {
        "slug": "daspoort",
        "name": "Daspoort Wastewater Treatment Works",
        "municipality": "City of Tshwane",
        "province": "Gauteng",
        "process_family": "BNR activated sludge with heritage trickling filters",
        "capacity_mld": 55.0,
        "receiving_water": "Apies River system",
        "summary": (
            "Full-scale Pretoria works with screening, grit removal, primary "
            "settling, BNR activated sludge, secondary settling, disinfection, "
            "sludge digestion, drying beds, and historically important "
            "trickling-filter/anammox biology."
        ),
        "realism_notes": (
            "Scientific Twin uses literature operating values and mechanistic "
            "mass balances. It is not a live operational replica until Daspoort "
            "flow, lab, sludge, and SCADA/operations data are connected."
        ),
        "source_notes": (
            "WRC Water Wheel Daspoort history; WRC Report 2474; Water SA "
            "Daspoort trickling-filter/anammox paper."
        ),
        "default_flow_mld": 38.0,
        "default_hrt_hours": 12.0,
        "default_srt_days": 30.0,
        "default_mlss_mgl": 3000.0,
        "default_do_mgl": 1.5,
        "default_temp_c": 22.0,
        "default_ph": 7.5,
        "default_recycle_ratio": 4.0,
        "default_organic_loading": None,
        "default_nitrogen_loading": None,
        "units": [
            UnitSeed(1, "Inlet Works", "screening_grit", "Preliminary solids and grit removal", None, "Bar screens and grit removal protect downstream units."),
            UnitSeed(2, "Primary Settling Tanks", "primary_settling", "Settle primary solids and generate VFA-rich feed", 2.0, "Activated primary tank behaviour supports biological phosphorus removal."),
            UnitSeed(3, "Anaerobic Selector", "anaerobic", "PAO conditioning and phosphate release", 1.5, "No dissolved oxygen or nitrate should dominate this zone."),
            UnitSeed(4, "Anoxic Reactor", "anoxic", "Denitrification using nitrate recycle", 2.5, "Internal recycle controls nitrate delivery and denitrification capacity."),
            UnitSeed(5, "Aerobic Reactor", "aerobic", "COD removal, nitrification, and phosphorus uptake", 8.0, "Mechanical aeration maintains nitrifying biomass and oxygen transfer."),
            UnitSeed(6, "Secondary Settling Tanks", "secondary_clarifier", "Separate treated water from mixed liquor", 2.0, "RAS maintains biomass; WAS controls sludge age."),
            UnitSeed(7, "Disinfection", "disinfection", "Pathogen reduction", 0.5, "UV/chlorine barrier; not a PFAS destruction step."),
            UnitSeed(8, "Sludge Digestion and Drying Beds", "sludge_handling", "Stabilise and dewater sludge", None, "Important PFAS sink because sorbed mass follows solids."),
            UnitSeed(9, "Heritage Trickling Filters", "trickling_filter", "Fixed-film nitrogen-removal research layer", None, "Known for unusual nitrogen removal and possible anammox activity."),
        ],
        "sampling_points": [
            SamplingSeed(1, "SP1_influent", "Influent", 1, "Raw/settled wastewater entering biological treatment."),
            SamplingSeed(2, "SP2_primary", "Primary/BNR feed", 2, "After primary settling and before biological selectors."),
            SamplingSeed(3, "SP3_clarifier", "Secondary clarifier", 6, "Mixed liquor/settled solids interface for sludge fate."),
            SamplingSeed(4, "SP4_effluent", "Final effluent", 7, "Disinfected final effluent leaving the works."),
        ],
    },
    {
        "slug": "zeekoegat",
        "name": "Zeekoegat Wastewater Treatment Works",
        "municipality": "City of Tshwane",
        "province": "Gauteng",
        "process_family": "Flexible BNR activated sludge",
        "capacity_mld": 85.0,
        "receiving_water": "Roodeplaat Dam catchment",
        "summary": (
            "Large BNR works upgraded to 85 ML/d with process flexibility, "
            "tertiary treatment, sludge management, and configurable BNR "
            "modes including A2O/Bardenpho, UCT, Modified UCT, and Johannesburg."
        ),
        "realism_notes": (
            "Scientific Twin captures flexible BNR behaviour and high-MLSS, "
            "long-SRT assumptions. Exact mode selection and daily performance "
            "need plant records for calibration."
        ),
        "source_notes": (
            "Bigen Zeekoegat upgrade profile; WRC Report 2474; plant-wide "
            "BNR configuration modelling literature."
        ),
        "default_flow_mld": 45.0,
        "default_hrt_hours": 12.0,
        "default_srt_days": 40.0,
        "default_mlss_mgl": 5000.0,
        "default_do_mgl": 1.8,
        "default_temp_c": 22.0,
        "default_ph": 7.5,
        "default_recycle_ratio": 4.0,
        "default_organic_loading": None,
        "default_nitrogen_loading": None,
        "units": [
            UnitSeed(1, "Inlet Works", "screening_grit", "Screening and degritting", None, "Preliminary treatment before flow splitting."),
            UnitSeed(2, "Balancing Tank", "balancing", "Hydraulic and load equalisation", 2.0, "Balances feed and receives periodic primary tank contents."),
            UnitSeed(3, "Anaerobic Zone", "anaerobic", "EBPR phosphate release and VFA uptake", 1.5, "Configuration-dependent selector zone."),
            UnitSeed(4, "Anoxic Zone", "anoxic", "Denitrification", 2.5, "Receives nitrate-rich recycle depending on BNR mode."),
            UnitSeed(5, "Aerobic Zone", "aerobic", "COD removal, nitrification, phosphorus uptake", 8.0, "High MLSS and long SRT improve nitrification and PFAS sorption opportunity."),
            UnitSeed(6, "Secondary Settling Tanks", "secondary_clarifier", "Solids-water separation", 2.0, "Clarifier capture strongly controls sorbed contaminant removal."),
            UnitSeed(7, "Tertiary Treatment", "tertiary_filtration", "Final suspended-solids polishing", 1.0, "Improves particulate-associated contaminant capture."),
            UnitSeed(8, "Disinfection", "disinfection", "Pathogen barrier", 0.5, "Does not destroy PFAS under normal operation."),
            UnitSeed(9, "Sludge Handling", "sludge_handling", "Manage increased sludge production", None, "Critical for mass accounting of sorbed PFAS/PFCs."),
        ],
        "sampling_points": [
            SamplingSeed(1, "SP1_influent", "Balancing tank outlet", 2, "Feed to activated sludge after balancing."),
            SamplingSeed(2, "SP2_bnr", "BNR mixed liquor", 5, "Biological reactor performance point."),
            SamplingSeed(3, "SP3_clarifier", "Secondary settling outlet", 6, "Before tertiary polishing."),
            SamplingSeed(4, "SP4_effluent", "Final effluent", 8, "Final disinfected/polished discharge."),
        ],
    },
    {
        "slug": "phola",
        "name": "Phola Wastewater Treatment Plant",
        "municipality": "eMalahleni Local Municipality",
        "province": "Mpumalanga",
        "process_family": "PETRO pond plus trickling-filter system",
        "capacity_mld": 2.8,
        "receiving_water": "Nearby river downstream of reed bed",
        "summary": (
            "Small municipal works near Ogies using screens, vortex degritters, "
            "parallel anaerobic ponds, a biological trickling filter, humus "
            "tanks, disinfection, and reed-bed polishing."
        ),
        "realism_notes": (
            "Scientific Twin captures long pond retention and biofilm treatment. "
            "It is less controllable than activated sludge because pond biology, "
            "short-circuiting, rainfall, and seasonal effects need field data."
        ),
        "source_notes": "WRC Report 2474 Phola WWTP process description and operating table.",
        "default_flow_mld": 2.8,
        "default_hrt_hours": 38.4,
        "default_srt_days": None,
        "default_mlss_mgl": 800.0,
        "default_do_mgl": 0.8,
        "default_temp_c": 22.0,
        "default_ph": 7.4,
        "default_recycle_ratio": 0.0,
        "default_organic_loading": 0.23,
        "default_nitrogen_loading": 0.9,
        "units": [
            UnitSeed(1, "Inlet Screens", "screening", "Remove gross solids", None, "Protects pond and filter hydraulics."),
            UnitSeed(2, "Vortex Degritters", "grit", "Remove grit and heavy inorganics", None, "Two vortex degritters before flow splitting."),
            UnitSeed(3, "Parallel Anaerobic Ponds", "anaerobic_pond", "Long-retention anaerobic treatment", 38.4, "Approximate 1.6 day retention time."),
            UnitSeed(4, "Biological Trickling Filter", "trickling_filter", "Attached-growth BOD and nitrogen removal", None, "Organic loading around 3.7 g BOD/m2/d."),
            UnitSeed(5, "Humus Tanks", "humus_tank", "Settle sloughed biofilm solids", 2.0, "Solids capture after trickling filter."),
            UnitSeed(6, "Disinfection", "disinfection", "Pathogen reduction", 0.5, "Final barrier before wetland polishing."),
            UnitSeed(7, "Reed Bed", "reed_bed", "Wetland polishing and discharge buffer", 24.0, "May improve solids and biodegradable CEC polishing."),
            UnitSeed(8, "Drying Beds", "sludge_drying", "Pond sludge drying", None, "Anaerobic pond sludge is periodically discharged to drying beds."),
        ],
        "sampling_points": [
            SamplingSeed(1, "SP1_degritter", "After degritters", 2, "Raw wastewater after preliminary treatment."),
            SamplingSeed(2, "SP2_pond", "After anaerobic ponds", 3, "End of pond system before trickling filter."),
            SamplingSeed(3, "SP3_filter", "Trickling-filter discharge", 5, "After humus tanks/biological filter treatment."),
            SamplingSeed(4, "SP4_effluent", "Final reed-bed effluent", 7, "Final discharge after disinfection and reed bed."),
        ],
    },
]


def seed_default_plants(session) -> None:
    """
    Ensure the three V1 real-plant profiles exist.

    Existing plant rows are updated for core profile fields. Units/sampling
    points are only inserted when absent, preserving any future custom edits.
    """
    for plant_data in DEFAULT_PLANTS:
        units = plant_data["units"]
        sampling_points = plant_data["sampling_points"]
        profile = {
            k: v for k, v in plant_data.items()
            if k not in {"units", "sampling_points"}
        }

        plant = session.query(Plant).filter_by(slug=profile["slug"]).first()
        if plant is None:
            plant = Plant(**profile)
            session.add(plant)
            session.flush()
        else:
            for key, value in profile.items():
                setattr(plant, key, value)

        if not plant.units:
            for item in units:
                session.add(PlantUnit(
                    plant_id=plant.id,
                    unit_order=item.order,
                    name=item.name,
                    unit_type=item.unit_type,
                    hydraulic_role=item.role,
                    hrt_hours=item.hrt_hours,
                    notes=item.notes,
                ))

        if not plant.sampling_points:
            for item in sampling_points:
                session.add(PlantSamplingPoint(
                    plant_id=plant.id,
                    point_order=item.order,
                    code=item.code,
                    name=item.name,
                    after_unit_order=item.after_unit_order,
                    description=item.description,
                ))
