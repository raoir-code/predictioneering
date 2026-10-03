import os
import unittest
from datetime import date
from unittest.mock import patch

os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("GNEWS_API_KEY", "test-key")

from pipeline import agglomeration


class AgglomerationScopeDirectionTests(unittest.TestCase):

    def test_only_in_scope_correct_direction_constituents_are_aggregated(self):
        deadline = date(2026, 12, 31)

        # Aggregate asks specifically:
        # Iran -> {Bahrain, Kuwait}
        configs = {
            "Iran-ArabStates": {
                "initiator": "Iran",
                "qualifying_countries": [
                    "Bahrain",
                    "Kuwait",
                ],
                "is_enumerable": True,
                "formal_dependence": {
                    "enabled": True,
                    "common_factor_rho_max": 0.35,
                    "substitution_strength": 0.0,
                },
            }
        }

        markets = [
            # Correct direction + in scope
            {
                "dyad": "Iran-Bahrain",
                "our_prediction": 0.20,
                "_test_deadline": deadline,
            },
            {
                "dyad": "Iran-Kuwait",
                "our_prediction": 0.30,
                "_test_deadline": deadline,
            },

            # WRONG DIRECTION — must never enter aggregate
            {
                "dyad": "Bahrain-Iran",
                "our_prediction": 0.99,
                "_test_deadline": deadline,
            },

            # Correct initiator, but OUT OF SCOPE
            {
                "dyad": "Iran-Oman",
                "our_prediction": 0.99,
                "_test_deadline": deadline,
            },
        ]

        known_dyads = {
            "Iran-Bahrain",
            "Iran-Kuwait",
            "Bahrain-Iran",
            "Iran-Oman",
        }

        def fake_deadline(market):
            return market["_test_deadline"], "test", False

        def fake_role(dyad, registry=None):
            return {
                "role": "target",
                "weight": 1.0,
            }

        with (
            patch.object(
                agglomeration,
                "_get_market_deadline",
                side_effect=fake_deadline,
            ),
            patch.object(
                agglomeration.T,
                "resolve_dyad_role",
                side_effect=fake_role,
            ),
        ):
            p_any, diag = agglomeration.compute_any_of_probability(
                "Iran-ArabStates",
                deadline,
                89,
                markets,
                known_dyads,
                host_registry={},
                agg_configs=configs,
            )

        found_dyads = {
            row[1]
            for row in diag["tracked_found"]
        }

        # Exactly the directed, in-scope constituents.
        self.assertEqual(
            found_dyads,
            {
                "Iran-Bahrain",
                "Iran-Kuwait",
            },
        )

        self.assertNotIn(
            "Bahrain-Iran",
            found_dyads,
        )
        self.assertNotIn(
            "Iran-Oman",
            found_dyads,
        )

        self.assertEqual(
            diag["aggregation_model"],
            "one_factor_gaussian_with_substitution",
        )

        # The two bogus 0.99 markets must not contaminate the result.
        self.assertLess(p_any, 0.99)


if __name__ == "__main__":
    unittest.main()
