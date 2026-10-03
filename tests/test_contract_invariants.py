import os
import unittest

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GNEWS_API_KEY", "test-key")

from pipeline import engine
from pipeline.translator import bettor


class ContractInvariantTests(unittest.TestCase):

    def test_conflict_bound_zero_background_probability(self):
        clergy = {
            "p_b_given_a": 0.60,
            "p_b_given_not_a": 0.0,
            "p_b_given_not_a_reference_days": 365.0,
            "parent_event_relation": "conflict_bound",
        }

        scholar = {"contract_polarity": "conflict"}
        glass = {
            "outcome_observability": "high",
            "resolution_risk": "low",
        }

        out = bettor(
            engine_p=0.20,
            market_p=0.20,
            volume_usd=10000,
            scholar=scholar,
            clergy=clergy,
            glass=glass,
            days_remaining=30,
        )

        # P(B) = P(A)P(B|A) because P(B|¬A)=0
        self.assertAlmostEqual(
            out["conditional_p"],
            0.12,
            places=4,
        )

    def test_longer_horizon_cannot_reduce_probability(self):
        p = 0.20
        reference_days = engine.HORIZON_REFERENCE_DAYS

        def scale(days):
            horizon_scale = max(days, 1) / reference_days
            return 1.0 - (1.0 - p) ** horizon_scale

        p_7 = scale(7)
        p_30 = scale(30)
        p_90 = scale(90)
        p_180 = scale(180)

        self.assertLessEqual(p_7, p_30)
        self.assertLessEqual(p_30, p_90)
        self.assertLessEqual(p_90, p_180)

        self.assertAlmostEqual(p_90, p, places=12)


if __name__ == "__main__":
    unittest.main()
