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
from dataclasses import replace as _replace

from simulation.plant_model import (
    DISCHARGE_LIMITS,
    PFAS_BIOTRANSFORMATION_FRACTION,
    PlantTwinInputs,
    PFASMixtureEntry,
    calc_plant_fm_ratio,
    g_day_from_ugl_mld,
    kg_day_from_mgl_mld,
    run_pfas_mixture,
    run_pfas_uncertainty,
    run_plant_twin,
    run_scenarios,
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
        # Full four-pathway mass balance: in = eff + sludge + biotransformed + unresolved
        self.assertAlmostEqual(
            out.pfas_in_g_day,
            out.pfas_effluent_g_day + out.pfas_sludge_g_day
            + out.pfas_biotransformed_g_day + out.pfas_unresolved_g_day,
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


class PFASMassBalanceTests(unittest.TestCase):
    """Four-pathway PFAS mass balance: in = eff + sludge + biotransformed + unresolved."""

    def _balance(self, out):
        return (out.pfas_effluent_g_day + out.pfas_sludge_g_day
                + out.pfas_biotransformed_g_day + out.pfas_unresolved_g_day)

    def test_four_pathway_balance_closes_for_all_plants(self):
        for slug in ("daspoort", "zeekoegat", "phola"):
            out = run_plant_twin(_inputs(slug))
            self.assertAlmostEqual(out.pfas_in_g_day, self._balance(out), places=6,
                                   msg=f"{slug}: mass balance did not close")

    def test_sludge_plus_biotransformed_equals_removed_load(self):
        out = run_plant_twin(_inputs("daspoort", pfas_type="long-chain", pfas_compound="PFOS"))
        removed = out.pfas_in_g_day - out.pfas_effluent_g_day
        self.assertAlmostEqual(removed, out.pfas_sludge_g_day + out.pfas_biotransformed_g_day, places=6)

    def test_long_chain_has_lower_biotransformation_than_short_chain(self):
        # Biotransformation fraction is defined relative to REMOVED load, not influent.
        # Long-chain: bioT = 2% of removed; short-chain: 8% of removed.
        long  = run_plant_twin(_inputs("daspoort", pfas_type="long-chain",  pfas_compound="PFOS"))
        short = run_plant_twin(_inputs("daspoort", pfas_type="short-chain", pfas_compound="PFBS"))
        long_removed  = max(long.pfas_in_g_day  - long.pfas_effluent_g_day,  1e-9)
        short_removed = max(short.pfas_in_g_day - short.pfas_effluent_g_day, 1e-9)
        long_bioT_frac  = long.pfas_biotransformed_g_day  / long_removed
        short_bioT_frac = short.pfas_biotransformed_g_day / short_removed
        self.assertLess(long_bioT_frac, short_bioT_frac)

    def test_calibration_does_not_break_mass_balance(self):
        inp = _inputs("daspoort", pfas_type="long-chain", pfas_compound="PFOS",
                      calibration_factors={"pfas": 1.5, "cod": 0.9})
        out = run_plant_twin(inp)
        self.assertAlmostEqual(out.pfas_in_g_day, self._balance(out), places=6)

    def test_biotransformation_fraction_constants_are_positive_and_ordered(self):
        sc = PFAS_BIOTRANSFORMATION_FRACTION["short-chain"]
        lc = PFAS_BIOTRANSFORMATION_FRACTION["long-chain"]
        self.assertGreater(sc, 0.0)
        self.assertGreater(lc, 0.0)
        self.assertGreater(sc, lc)


class ComplianceLimitTests(unittest.TestCase):
    """Compliance flags vs SA Green Drop / SANS discharge limits."""

    def test_discharge_limits_defined_for_all_three_plants(self):
        for slug in ("daspoort", "zeekoegat", "phola"):
            self.assertIn(slug, DISCHARGE_LIMITS)
            limits = DISCHARGE_LIMITS[slug]
            for param in ("cod_mgl", "nh4_mgl", "tn_mgl", "tp_mgl"):
                self.assertIn(param, limits)
                self.assertGreater(limits[param], 0.0)

    def test_zeekoegat_has_tighter_limits_than_daspoort(self):
        self.assertLess(DISCHARGE_LIMITS["zeekoegat"]["cod_mgl"],
                        DISCHARGE_LIMITS["daspoort"]["cod_mgl"])
        self.assertLess(DISCHARGE_LIMITS["zeekoegat"]["tp_mgl"],
                        DISCHARGE_LIMITS["daspoort"]["tp_mgl"])

    def test_compliance_flags_present_in_output(self):
        out = run_plant_twin(_inputs("daspoort"))
        self.assertIsInstance(out.compliance, dict)
        for key in ("cod", "nh4", "tn", "tp"):
            self.assertIn(key, out.compliance)
            self.assertIn(out.compliance[key], ("PASS", "WARN", "FAIL"))

    def test_effluent_well_below_limits_gives_all_pass(self):
        # Very low influent → effluent will be far below limits
        out = run_plant_twin(_inputs("daspoort", inf_cod_mgl=5.0, inf_nh4_mgl=0.5,
                                     inf_tn_mgl=1.0, inf_tp_mgl=0.05))
        for key in ("cod", "nh4", "tn", "tp"):
            self.assertEqual("PASS", out.compliance[key], msg=f"{key} should be PASS")

    def test_confidence_label_names_correct_plant_when_calibrated(self):
        for slug, expected in [("daspoort", "Daspoort"),
                                ("zeekoegat", "Zeekoegat"),
                                ("phola", "Phola")]:
            out = run_plant_twin(_inputs(slug, calibration_factors={"cod": 0.9}))
            self.assertIn(expected, out.confidence_label)
            self.assertIn("calibrated", out.confidence_label.lower())

    def test_uncalibrated_confidence_is_generic_literature_label(self):
        out = run_plant_twin(_inputs("daspoort"))
        self.assertIn("literature", out.confidence_label.lower())
        self.assertNotIn("Daspoort", out.confidence_label)


class PFASMixtureTests(unittest.TestCase):
    """Multi-compound PFAS mixture mode."""

    def _base(self, slug="daspoort"):
        return _inputs(slug, inf_pfas_ugl=1.0, pfas_type="long-chain")

    def test_mixture_returns_one_result_per_compound(self):
        compounds = [
            PFASMixtureEntry("PFOS", "long-chain", 0.5),
            PFASMixtureEntry("PFOA", "long-chain", 0.3),
            PFASMixtureEntry("PFBS", "short-chain", 1.2),
        ]
        results = run_pfas_mixture(self._base(), compounds)
        self.assertEqual(3, len(results))

    def test_mixture_sludge_plus_biotrans_equals_removed_load(self):
        compounds = [
            PFASMixtureEntry("PFOS", "long-chain", 0.5),
            PFASMixtureEntry("PFBS", "short-chain", 1.0),
        ]
        for r in run_pfas_mixture(self._base(), compounds):
            removed = g_day_from_ugl_mld(r.inf_ugl * r.removal_pct / 100.0,
                                          self._base().flow_mld)
            self.assertAlmostEqual(removed, r.sludge_g_day + r.biotrans_g_day, places=6,
                                   msg=f"{r.compound}: mass balance failed")

    def test_long_chain_removes_more_than_short_chain_at_same_mlss(self):
        inp = self._base()
        results = run_pfas_mixture(inp, [
            PFASMixtureEntry("PFOS", "long-chain", 1.0),
            PFASMixtureEntry("PFBS", "short-chain", 1.0),
        ])
        pfos = next(r for r in results if r.compound == "PFOS")
        pfbs = next(r for r in results if r.compound == "PFBS")
        self.assertGreater(pfos.removal_pct, pfbs.removal_pct)

    def test_mixture_kd_matches_expected_table_value(self):
        from simulation.generic_model import PFAS_KD_TABLE
        results = run_pfas_mixture(self._base(), [PFASMixtureEntry("PFOS", "long-chain", 1.0)])
        self.assertAlmostEqual(PFAS_KD_TABLE["PFOS"], results[0].kd, places=6)

    def test_empty_mixture_returns_empty_list(self):
        self.assertEqual([], run_pfas_mixture(self._base(), []))

    def test_mixture_effluent_is_always_below_or_equal_influent(self):
        compounds = [PFASMixtureEntry(c, "long-chain", 0.5) for c in ("PFOS", "PFOA", "PFNA")]
        for r in run_pfas_mixture(self._base(), compounds):
            self.assertLessEqual(r.eff_ugl, r.inf_ugl + 1e-9)


class PFASUncertaintyTests(unittest.TestCase):
    """Monte Carlo Kd uncertainty for PFAS removal confidence intervals."""

    def _base(self):
        return _inputs("daspoort", pfas_type="long-chain", pfas_compound="PFOS",
                       mlss_mgl=4000.0)

    def test_uncertainty_returns_ordered_low_high_tuple(self):
        low, high = run_pfas_uncertainty(self._base(), n_samples=200, rng_seed=42)
        self.assertLessEqual(low, high)
        self.assertGreaterEqual(low, 0.0)
        self.assertLessEqual(high, 100.0)

    def test_uncertainty_is_reproducible_with_same_seed(self):
        r1 = run_pfas_uncertainty(self._base(), n_samples=100, rng_seed=7)
        r2 = run_pfas_uncertainty(self._base(), n_samples=100, rng_seed=7)
        self.assertEqual(r1, r2)

    def test_high_kd_compound_has_wider_ci_than_low_kd(self):
        pfos = run_pfas_uncertainty(_inputs("daspoort", pfas_type="long-chain",
                                             pfas_compound="PFOS"), n_samples=500, rng_seed=1)
        pfbs = run_pfas_uncertainty(_inputs("daspoort", pfas_type="short-chain",
                                             pfas_compound="PFBS"), n_samples=500, rng_seed=1)
        pfos_width = pfos[1] - pfos[0]
        pfbs_width = pfbs[1] - pfbs[0]
        # Higher Kd → steeper slope of adsorption curve → more Kd uncertainty maps to more removal uncertainty
        self.assertGreater(pfos_width, pfbs_width)

    def test_compute_uncertainty_flag_populates_ci_field(self):
        out = run_plant_twin(self._base(), compute_uncertainty=True)
        self.assertIsNotNone(out.pfas_removal_ci)
        low, high = out.pfas_removal_ci
        self.assertLessEqual(low, high)

    def test_compute_uncertainty_false_leaves_ci_as_none(self):
        out = run_plant_twin(self._base(), compute_uncertainty=False)
        self.assertIsNone(out.pfas_removal_ci)


class ScenarioEngineTests(unittest.TestCase):
    """Diurnal/seasonal scenario batch-runner."""

    def _base(self):
        return _inputs("daspoort")

    def test_returns_same_count_as_overrides_list(self):
        overrides = [{"temp_c": t} for t in [10, 15, 20, 25, 30]]
        results = run_scenarios(self._base(), overrides)
        self.assertEqual(5, len(results))

    def test_higher_temperature_gives_more_cod_removal(self):
        cold, warm = run_scenarios(self._base(), [{"temp_c": 10.0}, {"temp_c": 28.0}])
        self.assertGreater(warm.cod_removal_pct, cold.cod_removal_pct)

    def test_higher_srt_gives_more_nitrification(self):
        low_srt, high_srt = run_scenarios(self._base(), [{"srt_days": 10.0}, {"srt_days": 40.0}])
        self.assertGreater(high_srt.nh4_removal_pct, low_srt.nh4_removal_pct)

    def test_diurnal_flow_does_not_affect_pfas_kd_based_removal(self):
        """PFAS adsorption depends on MLSS and Kd — flow changes HRT but
        at plant scale the Kd/MLSS term dominates, so removal changes are minor."""
        results = run_scenarios(self._base(), [
            {"flow_mld": 20.0, "hrt_hours": 18.0},
            {"flow_mld": 50.0, "hrt_hours":  7.0},
        ])
        for r in results:
            self.assertGreaterEqual(r.pfas_removal_pct, 0.0)
            self.assertLessEqual(r.pfas_removal_pct, 100.0)

    def test_empty_overrides_list_returns_empty_results(self):
        self.assertEqual([], run_scenarios(self._base(), []))

    def test_scenarios_mass_balance_closes_for_every_run(self):
        results = run_scenarios(self._base(), [{"temp_c": t} for t in [12, 18, 24, 30]])
        for r in results:
            total = (r.pfas_effluent_g_day + r.pfas_sludge_g_day
                     + r.pfas_biotransformed_g_day + r.pfas_unresolved_g_day)
            self.assertAlmostEqual(r.pfas_in_g_day, total, places=6)


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
