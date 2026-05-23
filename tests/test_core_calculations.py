import unittest

from core.calculations import (
    calc_actual_srt,
    calc_denitrification_rate,
    calc_fm_ratio,
    calc_hrt,
    calc_mass_load,
    calc_mass_transformed,
    calc_nitrification_rate,
    calc_observed_yield,
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


class ObservedYieldTests(unittest.TestCase):
    def test_normal_yield_calculation(self):
        self.assertAlmostEqual(0.4, calc_observed_yield(80.0, 200.0), places=6)

    def test_zero_cod_removed_returns_zero(self):
        self.assertEqual(0.0, calc_observed_yield(50.0, 0.0))

    def test_negative_cod_removed_returns_zero(self):
        self.assertEqual(0.0, calc_observed_yield(50.0, -10.0))

    def test_yield_is_dimensionless_ratio(self):
        # Doubling both numerator and denominator keeps Yobs the same
        self.assertAlmostEqual(
            calc_observed_yield(100.0, 250.0),
            calc_observed_yield(200.0, 500.0),
            places=9,
        )


class MassBalanceEdgeCaseTests(unittest.TestCase):
    def test_zero_sludge_concentration_gives_zero_sludge_mass(self):
        result = full_mass_balance(50.0, 10.0, 0.0, 320.0, 20.0, 10.0)
        self.assertEqual(0.0, result["mass_sludge_ugday"])

    def test_zero_influent_gives_zero_removal_pct(self):
        result = full_mass_balance(0.0, 0.0, 0.0, 320.0, 20.0, 10.0)
        self.assertEqual(0.0, result["removal_pct"])

    def test_effluent_higher_than_influent_clamps_removal_to_zero(self):
        # Negative removal (concentration increase) should report 0 %, not negative
        result = full_mass_balance(10.0, 50.0, 0.0, 320.0, 5.0, 5.0)
        self.assertEqual(0.0, result["removal_pct"])

    def test_q_eff_matches_expected_mass_flow(self):
        # q_eff = q_in - q_was - q_ps = 320 - 20 - 10 = 290
        result = full_mass_balance(50.0, 10.0, 5.0, 320.0, 20.0, 10.0)
        self.assertAlmostEqual(290.0, result["q_eff_mlh"], places=6)


class KineticEdgeCaseTests(unittest.TestCase):
    def test_nitrification_rate_zero_flow_returns_zero(self):
        self.assertEqual(0.0, calc_nitrification_rate(40.0, 5.0, 0.0))

    def test_nitrification_rate_eff_higher_than_inf_returns_zero(self):
        self.assertEqual(0.0, calc_nitrification_rate(5.0, 40.0, 320.0))

    def test_denitrification_rate_zero_recycle_returns_zero(self):
        self.assertEqual(0.0, calc_denitrification_rate(20.0, 5.0, 0.0))

    def test_denitrification_rate_equal_concentrations_returns_zero(self):
        self.assertEqual(0.0, calc_denitrification_rate(15.0, 15.0, 320.0))

    def test_hrt_zero_flow_returns_zero(self):
        self.assertEqual(0.0, calc_hrt(0.0))

    def test_hrt_proportional_to_inverse_flow(self):
        # Doubling flow should halve HRT
        hrt1 = calc_hrt(200.0)
        hrt2 = calc_hrt(400.0)
        self.assertAlmostEqual(hrt1, hrt2 * 2.0, places=6)

    def test_actual_srt_zero_was_returns_zero(self):
        self.assertEqual(0.0, calc_actual_srt(3000.0, 0.0))

    def test_fm_ratio_zero_mlss_returns_zero(self):
        self.assertEqual(0.0, calc_fm_ratio(300.0, 320.0, 0.0))

    def test_fm_ratio_uses_provided_vss_over_mlss_estimate(self):
        # With VSS provided, result should differ from the 0.80 × MLSS estimate
        fm_estimated = calc_fm_ratio(300.0, 320.0, 3000.0)
        fm_measured  = calc_fm_ratio(300.0, 320.0, 3000.0, vss_mgl=2000.0)
        self.assertNotAlmostEqual(fm_estimated, fm_measured, places=4)

    def test_washout_risk_none_when_srt_and_temp_are_adequate(self):
        self.assertIsNone(check_nitrifier_washout_risk(30.0, 22.0))

    def test_washout_risk_string_when_conditions_are_marginal(self):
        result = check_nitrifier_washout_risk(2.0, 10.0)
        self.assertIsInstance(result, str)
        self.assertIn("washout", result.lower())


if __name__ == "__main__":
    unittest.main()
