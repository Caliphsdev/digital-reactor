import unittest
from unittest.mock import MagicMock, patch

from simulation.data_model import (
    MAIN_MODEL_THRESHOLD,
    PFAS_MODEL_THRESHOLD,
    get_model_status,
    get_training_data,
    run_phase2,
    train_phase2,
)
from simulation.generic_model import SimInputs, run_phase1


# ── Shared helpers ─────────────────────────────────────────────────────────────

def _inputs(**overrides):
    base = {
        "flow_rate_mlh": 320.0,
        "ras_ratio": 1.0,
        "do_mgl": 2.0,
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
    base.update(overrides)
    return SimInputs(**base)


def _empty_session():
    """Mock SQLAlchemy session that returns no rows from any query."""
    session = MagicMock()
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.all.return_value = []
    return session


# ── Model status ───────────────────────────────────────────────────────────────

class ModelStatusTests(unittest.TestCase):
    def test_defaults_returned_when_metadata_file_absent(self):
        with patch("simulation.data_model.METADATA_PATH") as mock_path:
            mock_path.exists.return_value = False
            status = get_model_status()
        self.assertFalse(status["main_trained"])
        self.assertFalse(status["pfas_trained"])
        self.assertEqual(0, status["n_samples_main"])
        self.assertEqual(0, status["n_samples_pfas"])
        self.assertIsNone(status["r2_cod"])
        self.assertIsNone(status["last_trained"])

    def test_all_expected_keys_present_in_defaults(self):
        with patch("simulation.data_model.METADATA_PATH") as mock_path:
            mock_path.exists.return_value = False
            status = get_model_status()
        expected_keys = [
            "main_trained", "pfas_trained",
            "n_samples_main", "n_samples_pfas",
            "last_trained",
            "r2_cod", "r2_nh4", "r2_tp", "r2_pfas",
            "cv_r2_mean",
            "feature_importances", "pfas_importances",
        ]
        for key in expected_keys:
            self.assertIn(key, status, f"Missing key: {key}")

    def test_corrupt_metadata_file_falls_back_to_defaults(self):
        with patch("simulation.data_model.METADATA_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = "not valid json {{{"
            status = get_model_status()
        # Should not raise; should return defaults
        self.assertFalse(status["main_trained"])

    def test_valid_metadata_overrides_defaults(self):
        import json
        metadata = {"main_trained": True, "n_samples_main": 60, "r2_cod": 0.92}
        with patch("simulation.data_model.METADATA_PATH") as mock_path:
            mock_path.exists.return_value = True
            mock_path.read_text.return_value = json.dumps(metadata)
            status = get_model_status()
        self.assertTrue(status["main_trained"])
        self.assertEqual(60, status["n_samples_main"])
        self.assertAlmostEqual(0.92, status["r2_cod"])


# ── Training data extraction ───────────────────────────────────────────────────

class TrainingDataTests(unittest.TestCase):
    def test_empty_dataframe_when_no_db_rows(self):
        df = get_training_data(_empty_session())
        self.assertTrue(df.empty)

    def test_returns_dataframe_type(self):
        import pandas as pd
        df = get_training_data(_empty_session())
        self.assertIsInstance(df, pd.DataFrame)

    def test_missing_any_zone_produces_empty_dataframe(self):
        session = MagicMock()
        # aeration rows present but effluent missing → empty
        session.query.return_value.filter.return_value.all.side_effect = [
            [MagicMock()],  # aeration
            [],             # effluent
            [],             # primary_settling
        ]
        session.query.return_value.all.return_value = []
        df = get_training_data(session)
        self.assertTrue(df.empty)


# ── Training ───────────────────────────────────────────────────────────────────

class TrainPhase2Tests(unittest.TestCase):
    def test_insufficient_data_status_with_empty_db(self):
        result = train_phase2(_empty_session())
        self.assertEqual("insufficient_data", result["status"])
        self.assertFalse(result["main_trained"])

    def test_n_samples_main_is_zero_with_empty_db(self):
        result = train_phase2(_empty_session())
        self.assertEqual(0, result["n_samples_main"])
        self.assertLess(result["n_samples_main"], MAIN_MODEL_THRESHOLD)

    def test_result_has_all_expected_keys(self):
        result = train_phase2(_empty_session())
        required = [
            "status", "message",
            "n_samples_main", "n_samples_pfas",
            "main_trained", "pfas_trained",
            "r2_cod", "r2_nh4", "r2_tp", "r2_pfas",
            "cv_r2_mean", "last_trained",
        ]
        for key in required:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_message_explains_insufficient_data(self):
        result = train_phase2(_empty_session())
        self.assertIn(str(MAIN_MODEL_THRESHOLD), result["message"])

    def test_pfas_not_trained_when_main_not_trained(self):
        result = train_phase2(_empty_session())
        self.assertFalse(result["pfas_trained"])


# ── Phase 2 inference (fallback path) ─────────────────────────────────────────

class RunPhase2FallbackTests(unittest.TestCase):
    def _run_no_models(self):
        with patch("simulation.data_model._load_main_model", return_value=None), \
             patch("simulation.data_model._load_pfas_model", return_value=None):
            return run_phase2(_inputs())

    def test_fallback_matches_phase1_cod_removal(self):
        p1  = run_phase1(_inputs())
        p2  = self._run_no_models()
        self.assertAlmostEqual(p1.cod_removal_pct, p2.cod_removal_pct, places=4)

    def test_fallback_matches_phase1_nh4_removal(self):
        p1 = run_phase1(_inputs())
        p2 = self._run_no_models()
        self.assertAlmostEqual(p1.nh4_removal_pct, p2.nh4_removal_pct, places=4)

    def test_fallback_adds_phase2_warning_message(self):
        out = self._run_no_models()
        self.assertGreaterEqual(len(out.warnings), 1)
        self.assertTrue(any("Phase 2" in w for w in out.warnings))

    def test_all_removal_percentages_are_physical(self):
        out = self._run_no_models()
        for pct in [out.cod_removal_pct, out.nh4_removal_pct, out.tp_removal_pct, out.pfas_removal_pct]:
            self.assertGreaterEqual(pct, 0.0)
            self.assertLessEqual(pct, 100.0)

    def test_all_effluent_concentrations_are_non_negative(self):
        out = self._run_no_models()
        for conc in [out.eff_cod, out.eff_nh4, out.eff_tp, out.eff_pfas]:
            self.assertGreaterEqual(conc, 0.0)

    def test_ci_fields_are_none_when_no_model(self):
        out = self._run_no_models()
        self.assertIsNone(out.cod_ci)
        self.assertIsNone(out.nh4_ci)
        self.assertIsNone(out.tp_ci)
        self.assertIsNone(out.pfas_ci)

    def test_returns_siminputs_kd_for_pfas_compound(self):
        from simulation.generic_model import get_kd
        inp = _inputs(pfas_compound="PFOS", pfas_type="long-chain")
        with patch("simulation.data_model._load_main_model", return_value=None), \
             patch("simulation.data_model._load_pfas_model", return_value=None):
            out = run_phase2(inp)
        self.assertAlmostEqual(get_kd("PFOS", "long-chain"), out.kd_used, places=6)

    def test_hrt_is_positive_for_normal_flow(self):
        out = self._run_no_models()
        self.assertGreater(out.hrt_days, 0.0)

    def test_temp_factor_greater_than_one_above_20_degrees(self):
        # θ^(T-20) > 1 when T > 20°C
        with patch("simulation.data_model._load_main_model", return_value=None), \
             patch("simulation.data_model._load_pfas_model", return_value=None):
            out = run_phase2(_inputs(temp_c=25.0))
        self.assertGreater(out.temp_factor, 1.0)


if __name__ == "__main__":
    unittest.main()
