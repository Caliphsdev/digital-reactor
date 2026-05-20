import unittest

from simulation.generic_model import SimInputs, get_kd, run_phase1


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


if __name__ == "__main__":
    unittest.main()
