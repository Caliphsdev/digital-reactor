import unittest

from core.validators import (
    ValidationIssue,
    summarize_issues,
    validate_cec_payload,
    validate_daily_payload,
)


def _flow(**overrides):
    base = {
        "q_in_mlh": 320.0,
        "q_was_mlh": 10.0,
        "q_psludge_mlh": 5.0,
        "ras_ratio": 1.0,
    }
    base.update(overrides)
    return base


def _zones(**overrides):
    base = {
        "aeration": {
            "do_mgl": 2.0,
            "ph": 7.2,
            "temperature_c": 22.0,
            "mlss_mgl": 3000.0,
        },
        "effluent": {
            "cod_mgl": 30.0,
            "nh4_mgl": 5.0,
        },
    }
    base.update(overrides)
    return base


def _cec_sample(sp1_conc=50.0, sp4_conc=5.0):
    return {
        "SP1_influent": {
            "concentration": sp1_conc,
            "below_detection": False,
            "detection_limit": None,
        },
        "SP4_effluent": {
            "concentration": sp4_conc,
            "below_detection": False,
            "detection_limit": None,
        },
    }


class DailyPayloadFlowValidationTests(unittest.TestCase):
    def test_valid_payload_has_no_errors(self):
        issues = validate_daily_payload(_zones(), _flow())
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual([], errors)

    def test_zero_flow_is_an_error(self):
        issues = validate_daily_payload({}, _flow(q_in_mlh=0.0))
        errors = [i for i in issues if i.severity == "error" and i.scope == "flow"]
        self.assertGreaterEqual(len(errors), 1)

    def test_none_flow_is_an_error(self):
        issues = validate_daily_payload({}, _flow(q_in_mlh=None))
        errors = [i for i in issues if i.severity == "error"]
        self.assertGreaterEqual(len(errors), 1)

    def test_was_plus_ps_at_least_qin_is_an_error(self):
        # 300 + 25 = 325 >= 320
        issues = validate_daily_payload({}, _flow(q_was_mlh=300.0, q_psludge_mlh=25.0))
        error_msgs = [i.message for i in issues if i.severity == "error"]
        self.assertTrue(any("Q_eff" in m or "Q_WAS" in m for m in error_msgs))

    def test_out_of_envelope_flow_is_a_warning(self):
        issues = validate_daily_payload({}, _flow(q_in_mlh=500.0))
        warnings = [i for i in issues if i.severity == "warning" and i.scope == "flow"]
        self.assertGreaterEqual(len(warnings), 1)

    def test_out_of_range_ras_is_a_warning(self):
        issues = validate_daily_payload({}, _flow(ras_ratio=3.0))
        warnings = [i for i in issues if i.severity == "warning" and i.scope == "flow"]
        self.assertGreaterEqual(len(warnings), 1)

    def test_normal_ras_ratio_generates_no_flow_warnings(self):
        issues = validate_daily_payload({}, _flow(ras_ratio=1.0))
        flow_warnings = [i for i in issues if i.scope == "flow"]
        self.assertEqual([], flow_warnings)


class DailyPayloadZoneValidationTests(unittest.TestCase):
    def test_low_ph_in_aeration_zone_is_a_warning(self):
        zones = {"aeration": {"do_mgl": 2.0, "ph": 5.0, "temperature_c": 22.0, "mlss_mgl": 3000.0}}
        issues = validate_daily_payload(zones, _flow())
        warnings = [i for i in issues if i.severity == "warning" and "aeration" in i.scope]
        self.assertGreaterEqual(len(warnings), 1)

    def test_high_ph_in_aeration_zone_is_a_warning(self):
        zones = {"aeration": {"do_mgl": 2.0, "ph": 10.0, "temperature_c": 22.0, "mlss_mgl": 3000.0}}
        issues = validate_daily_payload(zones, _flow())
        warnings = [i for i in issues if i.severity == "warning" and "aeration" in i.scope]
        self.assertGreaterEqual(len(warnings), 1)

    def test_high_aeration_mlss_is_a_warning(self):
        zones = {"aeration": {"do_mgl": 2.0, "ph": 7.2, "temperature_c": 22.0, "mlss_mgl": 8000.0}}
        issues = validate_daily_payload(zones, _flow())
        self.assertGreaterEqual(len([i for i in issues if i.severity == "warning"]), 1)

    def test_low_aeration_do_is_a_warning(self):
        zones = {"aeration": {"do_mgl": 0.3, "ph": 7.2, "temperature_c": 22.0, "mlss_mgl": 3000.0}}
        issues = validate_daily_payload(zones, _flow())
        warnings = [i for i in issues if i.severity == "warning" and "aeration" in i.scope]
        self.assertGreaterEqual(len(warnings), 1)

    def test_high_clarifier_mlss_is_a_warning(self):
        zones = {"clarifier": {"mlss_mgl": 2000.0}}
        issues = validate_daily_payload(zones, _flow())
        self.assertGreaterEqual(len([i for i in issues if "clarifier" in i.scope]), 1)

    def test_high_effluent_cod_is_a_warning(self):
        zones = {"effluent": {"cod_mgl": 300.0}}
        issues = validate_daily_payload(zones, _flow())
        self.assertGreaterEqual(len([i for i in issues if "effluent" in i.scope]), 1)

    def test_high_effluent_nh4_is_a_warning(self):
        zones = {"effluent": {"nh4_mgl": 60.0}}
        issues = validate_daily_payload(zones, _flow())
        self.assertGreaterEqual(len([i for i in issues if "effluent" in i.scope]), 1)

    def test_high_primary_settling_do_is_a_warning(self):
        zones = {"primary_settling": {"do_mgl": 3.0}}
        issues = validate_daily_payload(zones, _flow())
        self.assertGreaterEqual(len([i for i in issues if "primary_settling" in i.scope]), 1)

    def test_cold_temperature_in_any_zone_is_a_warning(self):
        zones = {"aeration": {"do_mgl": 2.0, "ph": 7.2, "temperature_c": 10.0, "mlss_mgl": 3000.0}}
        issues = validate_daily_payload(zones, _flow())
        warnings = [i for i in issues if i.severity == "warning" and "aeration" in i.scope]
        self.assertGreaterEqual(len(warnings), 1)


class CECPayloadValidationTests(unittest.TestCase):
    def test_valid_payload_has_no_errors(self):
        issues = validate_cec_payload(_cec_sample())
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual([], errors)

    def test_bdl_without_detection_limit_is_an_error(self):
        data = {
            "SP1_influent": {"concentration": None, "below_detection": True, "detection_limit": None},
            "SP4_effluent": {"concentration": 5.0,  "below_detection": False, "detection_limit": None},
        }
        issues = validate_cec_payload(data)
        errors = [i for i in issues if i.severity == "error"]
        self.assertGreaterEqual(len(errors), 1)
        self.assertTrue(any("detection limit" in i.message.lower() or "below_detection" in i.message.lower() or "Below-detection" in i.message for i in errors))

    def test_no_usable_concentrations_is_an_error(self):
        data = {
            "SP1_influent": {"concentration": None, "below_detection": False, "detection_limit": None},
            "SP4_effluent": {"concentration": None, "below_detection": False, "detection_limit": None},
        }
        issues = validate_cec_payload(data)
        errors = [i for i in issues if i.severity == "error"]
        self.assertTrue(any("No usable" in i.message for i in errors))

    def test_missing_sp1_is_an_error(self):
        data = {
            "SP4_effluent": {"concentration": 5.0, "below_detection": False, "detection_limit": None},
        }
        issues = validate_cec_payload(data)
        errors = [i for i in issues if i.severity == "error"]
        self.assertTrue(any("SP1" in i.message for i in errors))

    def test_sp4_greater_than_sp1_is_a_warning(self):
        # Effluent higher than influent → negative apparent removal
        issues = validate_cec_payload(_cec_sample(sp1_conc=5.0, sp4_conc=50.0))
        warnings = [i for i in issues if i.severity == "warning"]
        self.assertGreaterEqual(len(warnings), 1)
        self.assertTrue(any("negative" in i.message.lower() or "higher than SP1" in i.message for i in warnings))

    def test_bdl_with_detection_limit_counts_as_usable_and_no_error(self):
        # BDL + valid DL → effective concentration = DL/2, which is a valid data point
        data = {
            "SP1_influent": {"concentration": 50.0, "below_detection": False, "detection_limit": None},
            "SP4_effluent": {"concentration": None, "below_detection": True, "detection_limit": 10.0},
        }
        issues = validate_cec_payload(data)
        errors = [i for i in issues if i.severity == "error"]
        self.assertEqual([], errors)

    def test_bdl_sp4_less_than_sp1_raises_no_negative_removal_warning(self):
        # SP4 BDL effective = 5.0 (10/2); SP1 = 50 → removal is positive, no warning
        data = {
            "SP1_influent": {"concentration": 50.0, "below_detection": False, "detection_limit": None},
            "SP4_effluent": {"concentration": None, "below_detection": True, "detection_limit": 10.0},
        }
        issues = validate_cec_payload(data)
        negative_warnings = [i for i in issues if "negative" in i.message.lower()]
        self.assertEqual([], negative_warnings)


class SummarizeIssuesTests(unittest.TestCase):
    def test_empty_list_returns_empty_string(self):
        self.assertEqual("", summarize_issues([]))

    def test_error_issues_formatted_with_error_label(self):
        issues = [ValidationIssue("error", "flow", "Flow too low.")]
        self.assertIn("[ERROR]", summarize_issues(issues))

    def test_warning_issues_formatted_with_warn_label(self):
        issues = [ValidationIssue("warning", "zone:aeration", "DO out of range.")]
        self.assertIn("[WARN]", summarize_issues(issues))

    def test_message_content_appears_in_summary(self):
        issues = [ValidationIssue("error", "flow", "Q_in must be > 0.")]
        self.assertIn("Q_in must be > 0.", summarize_issues(issues))

    def test_max_items_truncation_adds_remainder_line(self):
        issues = [ValidationIssue("warning", "flow", f"Issue {i}") for i in range(15)]
        summary = summarize_issues(issues, max_items=5)
        self.assertIn("more", summary)
        lines = summary.splitlines()
        # 5 issues + 1 "... and N more" line
        self.assertEqual(6, len(lines))

    def test_default_max_items_is_ten(self):
        issues = [ValidationIssue("warning", "flow", f"W{i}") for i in range(12)]
        summary = summarize_issues(issues)
        lines = summary.splitlines()
        self.assertEqual(11, len(lines))  # 10 items + 1 "more" line

    def test_exactly_max_items_produces_no_truncation_line(self):
        issues = [ValidationIssue("warning", "flow", f"W{i}") for i in range(5)]
        summary = summarize_issues(issues, max_items=5)
        self.assertNotIn("more", summary)


if __name__ == "__main__":
    unittest.main()
