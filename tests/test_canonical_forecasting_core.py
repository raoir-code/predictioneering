import os

# Stub required import-time environment variables.
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GNEWS_API_KEY", "test-key")

import inspect
import unittest

from pipeline import engine
from pipeline import predict


class CanonicalForecastingCoreTests(unittest.TestCase):

    def test_live_predict_uses_engine_probability_function(self):
        self.assertIs(
            predict._predict_probability,
            engine.predict_probability,
        )

    def test_live_predict_uses_engine_q_functions(self):
        self.assertIs(
            predict.build_q_components,
            engine.build_q_components,
        )
        self.assertIs(
            predict.q_with_subset,
            engine.q_with_subset,
        )

    def test_live_predict_uses_engine_weibull_transport(self):
        self.assertIs(
            predict._weibull_residual,
            engine._weibull_residual,
        )
        self.assertEqual(
            predict.HORIZON_REFERENCE_DAYS,
            engine.HORIZON_REFERENCE_DAYS,
        )

    def test_no_duplicate_probability_implementation_in_predict(self):
        source = inspect.getsource(predict)
        self.assertNotIn(
            "_LEGACY_UNUSED_predict_probability",
            source,
        )

    def test_backtest_is_explicitly_legacy(self):
        doc = inspect.getdoc(engine.run_backtest) or ""
        self.assertIn("Legacy", doc)
        self.assertIn(
            "NOT a second production forecasting engine",
            doc,
        )


if __name__ == "__main__":
    unittest.main()
