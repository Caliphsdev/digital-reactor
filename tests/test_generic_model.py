import unittest

from simulation.generic_model import (
    SimInputs, get_kd, run_phase1,
    PFAS_KD_TABLE, KD_SHORT_CHAIN, KD_LONG_CHAIN,
)


def _inputs(**overrides):
    data = {
        "flow_rate_mlh": 320.0,
        "ras_ratio": 1.0,
        "do_mgl": 1.5,
        "srt_days": 30.0,
        "temp_c": 22.0,
        "ph": 7.5,
        "inf_cod": 300.0,
        "inf_nh4": 40.0,
        "inf_tp": 6.0,
        "inf_pfas": 50.0,
        "pfas_type": "short-chain",
        "mlss_mgl": 3500.0,
    }
    data.update(overrides)
    return SimInputs(**data)


class GenericModelTests(unittest.TestCase):
    def test_kd_lookup_prefers_compound_then_chain_fallback(self):
        self.assertEqual(7.0, get_kd("pfos", "short-chain"))
        self.assertEqual(0.8, get_kd("", "short-chain"))
        self.assertEqual(4.5, get_kd("unknown", "long-chain"))

    def test_phase1_outputs_are_physical_and_mass_consistent(self):
        inputs = _inputs()
        out = run_phase1(inputs)
        for pct in [out.cod_removal_pct, out.nh4_removal_pct, out.tp_removal_pct, out.pfas_removal_pct]:
            self.assertGreaterEqual(pct, 0.0)
            self.assertLessEqual(pct, 100.0)
        self.assertAlmostEqual(inputs.inf_cod * (1 - out.cod_removal_pct / 100.0), out.eff_cod, places=6)
        self.assertAlmostEqual(inputs.inf_nh4 * (1 - out.nh4_removal_pct / 100.0), out.eff_nh4, places=6)
        self.assertAlmostEqual(inputs.inf_tp * (1 - out.tp_removal_pct / 100.0), out.eff_tp, places=6)
        self.assertAlmostEqual(inputs.inf_pfas * (1 - out.pfas_removal_pct / 100.0), out.eff_pfas, places=6)

    def test_low_srt_triggers_nitrifier_washout(self):
        out = run_phase1(_inputs(srt_days=1.0))
        self.assertTrue(out.monod_washout)
        self.assertEqual(0.0, out.nh4_removal_pct)
        self.assertTrue(any("washout" in warning.casefold() for warning in out.warnings))

    def test_long_chain_pfas_sorbs_more_than_short_chain(self):
        short = run_phase1(_inputs(pfas_type="short-chain"))
        long = run_phase1(_inputs(pfas_type="long-chain"))
        self.assertGreater(long.pfas_removal_pct, short.pfas_removal_pct)
        self.assertLess(long.eff_pfas, short.eff_pfas)

    def test_out_of_range_operating_conditions_report_warnings(self):
        out = run_phase1(_inputs(flow_rate_mlh=800.0, do_mgl=0.2, temp_c=10.0, ph=5.8))
        self.assertGreaterEqual(len(out.warnings), 4)


class GenericModelEdgeCaseTests(unittest.TestCase):
    def test_compound_lookup_is_case_insensitive(self):
        self.assertEqual(get_kd("PFOS", "long-chain"), get_kd("pfos", "long-chain"))
        self.assertEqual(get_kd("PFOS", "long-chain"), get_kd("Pfos", "long-chain"))
        self.assertEqual(7.0, get_kd("pfos", "long-chain"))

    def test_all_kd_table_values_are_positive(self):
        for compound, kd in PFAS_KD_TABLE.items():
            self.assertGreater(kd, 0.0, f"{compound} has non-positive Kd: {kd}")

    def test_class_fallback_values_are_positive(self):
        self.assertGreater(KD_SHORT_CHAIN, 0.0)
        self.assertGreater(KD_LONG_CHAIN, 0.0)
        self.assertGreater(KD_LONG_CHAIN, KD_SHORT_CHAIN)

    def test_higher_temperature_increases_cod_removal(self):
        out_cold = run_phase1(_inputs(temp_c=15.0))
        out_warm = run_phase1(_inputs(temp_c=25.0))
        self.assertGreater(out_warm.cod_removal_pct, out_cold.cod_removal_pct)
        self.assertGreater(out_warm.temp_factor, out_cold.temp_factor)

    def test_do_zero_causes_nitrification_washout(self):
        # DO=0 → do_factor=0 → mu_net_n<0 → denom≤0 → washout
        out = run_phase1(_inputs(do_mgl=0.0))
        self.assertTrue(out.monod_washout)
        self.assertEqual(0.0, out.nh4_removal_pct)

    def test_hrt_decreases_with_increasing_flow(self):
        out_low  = run_phase1(_inputs(flow_rate_mlh=200.0))
        out_high = run_phase1(_inputs(flow_rate_mlh=400.0))
        self.assertGreater(out_low.hrt_days, out_high.hrt_days)

    def test_alkalinity_consumed_equals_nh4_removed_times_stoichiometry(self):
        # Stoichiometric constant: 7.14 mg CaCO3 per mg NH4-N nitrified
        inp = _inputs()
        out = run_phase1(inp)
        nh4_removed_mgl = inp.inf_nh4 - out.eff_nh4
        self.assertAlmostEqual(out.alk_consumed_mgl, nh4_removed_mgl * 7.14, places=5)

    def test_fm_ratio_increases_with_higher_flow(self):
        out_low  = run_phase1(_inputs(flow_rate_mlh=200.0))
        out_high = run_phase1(_inputs(flow_rate_mlh=400.0))
        self.assertGreater(out_high.fm_ratio, out_low.fm_ratio)

    def test_pfas_removal_increases_with_mlss(self):
        out_low  = run_phase1(_inputs(mlss_mgl=1000.0))
        out_high = run_phase1(_inputs(mlss_mgl=5000.0))
        self.assertGreater(out_high.pfas_removal_pct, out_low.pfas_removal_pct)

    def test_zero_flow_returns_zero_hrt_and_fm(self):
        # Flow=0 should not raise; outputs should be clamped to zero
        out = run_phase1(_inputs(flow_rate_mlh=0.0))
        self.assertEqual(0.0, out.hrt_days)
        self.assertEqual(0.0, out.fm_ratio)

    def test_unknown_compound_falls_back_to_chain_class(self):
        kd_short = get_kd("no_such_compound", "short-chain")
        kd_long  = get_kd("no_such_compound", "long-chain")
        self.assertEqual(KD_SHORT_CHAIN, kd_short)
        self.assertEqual(KD_LONG_CHAIN, kd_long)

    def test_empty_compound_falls_back_to_chain_class(self):
        self.assertEqual(KD_SHORT_CHAIN, get_kd("", "short-chain"))
        self.assertEqual(KD_LONG_CHAIN,  get_kd("", "long-chain"))


if __name__ == "__main__":
    unittest.main()
