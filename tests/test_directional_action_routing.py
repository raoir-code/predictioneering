import os
import unittest
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GNEWS_API_KEY", "test-key")

from pipeline import predict


class DirectionalActionRoutingTests(unittest.TestCase):

    def test_opposite_directions_use_distinct_priors_and_readiness(self):
        scope_index = {
            "m1": {
                "route": "scoped_bilateral",
                "initiator": "US",
                "target": "Iran",
                "action_type": "airstrike",
                "scope": {"action_prior_fingerprint": "fp_us_iran"},
            },
            "m2": {
                "route": "scoped_bilateral",
                "initiator": "Iran",
                "target": "US",
                "action_type": "airstrike",
                "scope": {"action_prior_fingerprint": "fp_iran_us"},
            },
        }

        priors = {
            "US->Iran|scope=fp_us_iran": {
                "probabilities": {
                    "airstrike": 0.8,
                    "missile_strike": 0.2,
                },
                "feasibility": None,
                "structural_flags": None,
                "method": "test",
            },
            "Iran->US|scope=fp_iran_us": {
                "probabilities": {
                    "airstrike": 0.3,
                    "missile_strike": 0.7,
                },
                "feasibility": None,
                "structural_flags": None,
                "method": "test",
            },
        }

        readiness_cache = {}

        def fake_readiness(initiator, target, articles):
            return {
                "live_scores": {
                    "airstrike": 0.0,
                    "missile_strike": 0.0,
                },
                "signals": [],
                "summary": f"{initiator}->{target}",
            }

        # For this routing test, return the supplied structural distribution
        # unchanged. We are testing identity/routing, not selector math.
        def fake_select_distribution(
            structural_prior,
            live_scores=None,
            temperature=1.0,
            feasibility=None,
            structural_flags=None,
        ):
            return dict(structural_prior)

        with (
            patch.object(
                predict,
                "score_action_readiness",
                side_effect=fake_readiness,
            ) as scorer,
            patch.object(
                predict,
                "select_distribution",
                side_effect=fake_select_distribution,
            ),
        ):
            us_to_iran = {"market_id": "m1", "our_prediction": 0.1}
            iran_to_us = {"market_id": "m2", "our_prediction": 0.1}

            predict._attach_action_selector_shadow(
                us_to_iran,
                [{"title": "test"}],
                scope_index,
                priors,
                readiness_cache,
            )

            predict._attach_action_selector_shadow(
                iran_to_us,
                [{"title": "test"}],
                scope_index,
                priors,
                readiness_cache,
            )

        self.assertEqual(
            set(readiness_cache),
            {("US", "Iran"), ("Iran", "US")},
        )

        self.assertEqual(scorer.call_count, 2)

        scorer.assert_any_call(
            "US",
            "Iran",
            [{"title": "test"}],
        )
        scorer.assert_any_call(
            "Iran",
            "US",
            [{"title": "test"}],
        )

        self.assertEqual(
            us_to_iran[
                "action_selector_shadow_structural_distribution"
            ]["airstrike"],
            0.8,
        )

        self.assertEqual(
            iran_to_us[
                "action_selector_shadow_structural_distribution"
            ]["airstrike"],
            0.3,
        )

        self.assertEqual(
            us_to_iran["action_selector_shadow_readiness_summary"],
            "US->Iran",
        )
        self.assertEqual(
            iran_to_us["action_selector_shadow_readiness_summary"],
            "Iran->US",
        )

    def test_missing_direction_fails_closed(self):
        market = {"market_id": "m1", "our_prediction": 0.1}

        scope_index = {
            "m1": {
                "route": "scoped_bilateral",
                "initiator": None,
                "target": "Iran",
                "action_type": "airstrike",
                "scope": {"action_prior_fingerprint": "x"},
            }
        }

        predict._attach_action_selector_shadow(
            market,
            [],
            scope_index,
            {},
            {},
        )

        self.assertEqual(
            market["action_selector_shadow_status"],
            "incomplete_scope",
        )


if __name__ == "__main__":
    unittest.main()
