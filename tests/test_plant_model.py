import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from core.models import Base
from core.plant_catalog import seed_default_plants
from core.plant_catalog import DEFAULT_PLANTS
from core.plant_calibration import (
    calibrate_plant,
    compute_calibration_metrics,
    get_calibration_factors,
    import_monitoring_file,
    normalise_sampling_point,
)
from simulation.plant_model import (
    PlantTwinInputs,
    calc_plant_fm_ratio,
    g_day_from_ugl_mld,
    kg_day_from_mgl_mld,
    run_plant_twin,
)


def _plant(slug):
    return next(item for item in DEFAULT_PLANTS if item["slug"] == slug)


def _inputs(slug, **overrides):
    plant = _plant(slug)
    data = {
        "plant_slug": slug,
        "flow_mld": plant["default_flow_mld"],
        "hrt_hours": plant["default_hrt_hours"],
        "srt_days": plant["default_srt_days"] or 0.0,
        "mlss_mgl": plant["default_mlss_mgl"],
        "do_mgl": plant["default_do_mgl"],
        "temp_c": plant["default_temp_c"],
        "ph": plant["default_ph"],
        "recycle_ratio": plant["default_recycle_ratio"] or 0.0,
        "organic_loading": plant["default_organic_loading"] or 0.0,
        "nitrogen_loading": plant["default_nitrogen_loading"] or 0.0,
        "inf_cod_mgl": 350.0 if slug != "phola" else 450.0,
        "inf_nh4_mgl": 45.0,
        "inf_tn_mgl": 70.0,
        "inf_tp_mgl": 8.0,
        "inf_pfas_ugl": 50.0,
        "pfas_type": "short-chain",
    }
    data.update(overrides)
    return PlantTwinInputs(**data)


class PlantCatalogTests(unittest.TestCase):
    def test_v1_catalog_has_only_three_real_plants(self):
        self.assertEqual(["daspoort", "zeekoegat", "phola"], [p["slug"] for p in DEFAULT_PLANTS])

    def test_sampling_points_are_ordered_for_each_plant(self):
        for plant in DEFAULT_PLANTS:
            orders = [point.order for point in plant["sampling_points"]]
            self.assertEqual(sorted(orders), orders)
            self.assertGreaterEqual(len(orders), 3)

    def test_process_train_is_ordered_for_each_plant(self):
        for plant in DEFAULT_PLANTS:
            orders = [unit.order for unit in plant["units"]]
            self.assertEqual(sorted(orders), orders)
            self.assertGreaterEqual(len(orders), 4)

    def test_key_unit_order_matches_scientific_process_train(self):
        daspoort_units = [unit.name for unit in _plant("daspoort")["units"]]
        self.assertLess(daspoort_units.index("Primary Settling Tanks"), daspoort_units.index("Anaerobic Selector"))
        self.assertLess(daspoort_units.index("Anaerobic Selector"), daspoort_units.index("Anoxic Reactor"))
        self.assertLess(daspoort_units.index("Anoxic Reactor"), daspoort_units.index("Aerobic Reactor"))
        self.assertLess(daspoort_units.index("Aerobic Reactor"), daspoort_units.index("Secondary Settling Tanks"))

        phola_units = [unit.name for unit in _plant("phola")["units"]]
        self.assertLess(phola_units.index("Parallel Anaerobic Ponds"), phola_units.index("Biological Trickling Filter"))
        self.assertLess(phola_units.index("Biological Trickling Filter"), phola_units.index("Humus Tanks"))
        self.assertLess(phola_units.index("Humus Tanks"), phola_units.index("Reed Bed"))

    def test_sampling_points_progress_from_influent_to_final_effluent(self):
        for slug in ["daspoort", "zeekoegat", "phola"]:
            codes = [point.code for point in _plant(slug)["sampling_points"]]
            self.assertTrue(codes[0].startswith("SP1"))
            self.assertTrue(codes[-1].startswith("SP4"))


class PlantModelTests(unittest.TestCase):
    def test_plant_scale_mass_conversions(self):
        self.assertEqual(350.0, kg_day_from_mgl_mld(350.0, 1.0))
        self.assertEqual(50.0, g_day_from_ugl_mld(50.0, 1.0))

    def test_fm_ratio_uses_plant_volume_from_hrt(self):
        fm = calc_plant_fm_ratio(cod_mgl=350.0, flow_mld=38.0, mlss_mgl=3000.0, hrt_hours=12.0)
        self.assertGreater(fm, 0.0)
        self.assertLess(fm, 1.0)

    def test_daspoort_scientific_twin_returns_mass_balance(self):
        out = run_plant_twin(_inputs("daspoort"))
        self.assertGreater(out.cod_removal_pct, 50.0)
        self.assertGreater(out.nh4_removal_pct, 50.0)
        self.assertAlmostEqual(
            out.pfas_in_g_day,
            out.pfas_effluent_g_day + out.pfas_sludge_g_day + out.pfas_unresolved_g_day,
            places=6,
        )

    def test_calibration_factor_adjusts_daspoort_output(self):
        raw = run_plant_twin(_inputs("daspoort"))
        calibrated = run_plant_twin(_inputs(
            "daspoort",
            calibration_factors={"cod": 0.80, "pfas": 2.0},
        ))
        self.assertLess(calibrated.cod_removal_pct, raw.cod_removal_pct)
        self.assertGreater(calibrated.pfas_removal_pct, raw.pfas_removal_pct)
        self.assertIn("Partly calibrated", calibrated.confidence_label)

    def test_zeekoegat_modified_uct_improves_tp_assumption(self):
        base = run_plant_twin(_inputs("zeekoegat", bnr_mode="A2O / 3-stage Bardenpho"))
        modified = run_plant_twin(_inputs("zeekoegat", bnr_mode="Modified UCT"))
        self.assertGreater(modified.tp_removal_pct, base.tp_removal_pct)

    def test_phola_uses_pond_trickling_filter_path(self):
        out = run_plant_twin(_inputs("phola"))
        names = [unit.unit_name for unit in out.unit_results]
        self.assertIn("Anaerobic Ponds", names)
        self.assertIn("Trickling Filter and Humus Tanks", names)
        self.assertGreater(out.cod_removal_pct, 50.0)


class PlantCalibrationTests(unittest.TestCase):
    def test_sampling_point_aliases_normalise_to_sp_codes(self):
        self.assertEqual("SP1_influent", normalise_sampling_point("Influent"))
        self.assertEqual("SP4_effluent", normalise_sampling_point("final effluent"))

    def test_compute_calibration_metrics_uses_median_ratio(self):
        metrics = compute_calibration_metrics([
            {"date": None, "actual": 80.0, "predicted": 70.0},
            {"date": None, "actual": 90.0, "predicted": 75.0},
            {"date": None, "actual": 60.0, "predicted": 60.0},
        ])
        self.assertIsNotNone(metrics)
        self.assertEqual(3, metrics["n_samples"])
        self.assertGreater(metrics["multiplier"], 1.0)
        self.assertLess(metrics["mean_abs_error_pct"], 15.0)

    def test_import_and_calibrate_daspoort_monitoring_csv(self):
        engine = create_engine("sqlite:///:memory:")
        Base.metadata.create_all(bind=engine)
        Session = sessionmaker(bind=engine, expire_on_commit=False)

        with TemporaryDirectory() as tmp:
            csv_path = Path(tmp) / "daspoort_monitoring.csv"
            csv_path.write_text(
                "date,sampling_point,flow_mld,COD,NH4,TN,TP,pH,temperature,DO,MLSS,SRT,HRT,cec_name,concentration_ugl,cec_type\n"
                "2026-01-01,Influent,38,350,45,70,8,7.5,22,1.5,3000,30,12,,,\n"
                "2026-01-01,Final Effluent,38,50,5,20,1.5,7.4,22,1.5,3000,30,12,,,\n"
                "2026-01-01,Influent,38,,,,,7.5,22,1.5,3000,30,12,PFBS,50,short-chain\n"
                "2026-01-01,Final Effluent,38,,,,,7.4,22,1.5,3000,30,12,PFBS,48,short-chain\n",
                encoding="utf-8",
            )

            with Session() as session:
                seed_default_plants(session)
                result = import_monitoring_file(session, "daspoort", csv_path)
                self.assertEqual(4, result["imported"])

                calibration = calibrate_plant(session, "daspoort")
                self.assertIn("cod", calibration["targets"])
                self.assertIn("pfas", calibration["targets"])
                factors = get_calibration_factors(session, 1)
                self.assertIn("cod", factors)
                self.assertIn("pfas", factors)


if __name__ == "__main__":
    unittest.main()
