import unittest

from core.calculations import (
    calc_actual_srt,
    calc_denitrification_rate,
    calc_fm_ratio,
    calc_hrt,
    calc_mass_load,
    calc_mass_transformed,
    calc_nitrification_rate,
    calc_q_eff,
    calc_removal_pct,
    check_nitrifier_washout_risk,
    full_mass_balance,
)


class FlowAndMassBalanceEquationTests(unittest.TestCase):
    def test_effluent_flow_equation_and_negative_clamp(self):
        self.assertEqual(305.0, calc_q_eff(320.0, 5.0, 10.0))
        self.assertEqual(0.0, calc_q_eff(10.0, 8.0, 8.0))

    def test_mass_load_equation_uses_ug_per_l_and_ml_per_h(self):
        self.assertAlmostEqual(384.0, calc_mass_load(50.0, 320.0), places=6)

    def test_removal_percentage_is_clamped_to_physical_range(self):
        self.assertEqual(60.0, calc_removal_pct(100.0, 40.0))
        self.assertEqual(0.0, calc_removal_pct(0.0, 40.0))
        self.assertEqual(0.0, calc_removal_pct(100.0, 140.0))
        self.assertEqual(100.0, calc_removal_pct(100.0, -10.0))

    def test_mass_transformed_never_goes_negative(self):
        self.assertEqual(15.0, calc_mass_transformed(100.0, 75.0, 10.0))
        self.assertEqual(0.0, calc_mass_transformed(100.0, 110.0, 5.0))

    def test_full_mass_balance_returns_all_worked_values(self):
        result = full_mass_balance(
            c_inf_ugl=50.0,
            c_eff_ugl=10.0,
            c_sludge_ugl=5.0,
            q_in_mlh=320.0,
            q_was_mlh=20.0,
            q_psludge_mlh=10.0,
        )
        self.assertAlmostEqual(290.0, result["q_eff_mlh"], places=6)
        self.assertAlmostEqual(384.0, result["mass_in_ugday"], places=6)
        self.assertAlmostEqual(69.6, result["mass_eff_ugday"], places=6)
        self.assertAlmostEqual(2.4, result["mass_sludge_ugday"], places=6)
        self.assertAlmostEqual(312.0, result["mass_transformed_ugday"], places=6)
        self.assertAlmostEqual(80.0, result["removal_pct"], places=6)


class KineticEquationTests(unittest.TestCase):
    def test_fm_ratio_uses_vss_fraction_when_vss_is_missing(self):
        self.assertAlmostEqual(0.08, calc_fm_ratio(300.0, 320.0, 3000.0), places=6)

    def test_actual_srt_and_hrt_equations(self):
        self.assertAlmostEqual(30.0, calc_actual_srt(3000.0, 16.6666667), places=5)
        self.assertAlmostEqual(37.5, calc_hrt(320.0), places=6)

    def test_apparent_nitrification_and_denitrification_rates(self):
        self.assertAlmostEqual(67.2, calc_nitrification_rate(40.0, 5.0, 320.0), places=6)
        self.assertAlmostEqual(115.2, calc_denitrification_rate(20.0, 5.0, 1280.0), places=6)

    def test_nitrifier_washout_warning_responds_to_srt_and_temperature(self):
        self.assertIsNone(check_nitrifier_washout_risk(30.0, 22.0))
        self.assertIsNotNone(check_nitrifier_washout_risk(2.0, 10.0))


if __name__ == "__main__":
    unittest.main()
