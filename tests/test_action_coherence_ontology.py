import unittest

from pipeline.action_coherence import (
    ACTION_PAIR_RELATIONS,
    COMPONENT_FRACTIONS,
    check_action_coherence,
)


ACTION_TYPES = {
    "gray_zone_incident",
    "seizure_boarding",
    "raid",
    "missile_strike",
    "airstrike",
    "naval_blockade",
    "ground_invasion",
    "direct_engagement",
}


class ActionCoherenceOntologyTests(unittest.TestCase):

    def test_complete_eight_type_pair_table(self):
        expected = {
            frozenset({a, b})
            for a in ACTION_TYPES
            for b in ACTION_TYPES
            if a < b
        }

        self.assertEqual(set(ACTION_PAIR_RELATIONS), expected)
        self.assertEqual(len(ACTION_PAIR_RELATIONS), 28)

    def test_direct_engagement_has_relation_with_every_other_type(self):
        for other in ACTION_TYPES - {"direct_engagement"}:
            self.assertIn(
                frozenset({"direct_engagement", other}),
                ACTION_PAIR_RELATIONS,
            )

    def test_direct_engagement_airstrike_exclusive_ceiling(self):
        markets = [
            {
                "market_id": "direct",
                "action_type": "direct_engagement",
                "p_b_given_a": 0.90,
                "days_remaining": 30,
            },
            {
                "market_id": "air",
                "action_type": "airstrike",
                "p_b_given_a": 0.80,
                "days_remaining": 30,
            },
        ]

        out = check_action_coherence(markets)

        self.assertAlmostEqual(
            sum(m["p_b_given_a"] for m in out),
            1.25,
            places=4,
        )

        self.assertTrue(
            any(
                "EXCLUSIVE ceiling" in note
                for m in out
                for note in m["coherence_notes"]
            )
        )

    def test_direct_engagement_component_of_ground_invasion(self):
        self.assertEqual(
            COMPONENT_FRACTIONS[
                ("direct_engagement", "ground_invasion")
            ],
            0.55,
        )

        markets = [
            {
                "market_id": "direct",
                "action_type": "direct_engagement",
                "p_b_given_a": 0.10,
                "days_remaining": 30,
            },
            {
                "market_id": "invasion",
                "action_type": "ground_invasion",
                "p_b_given_a": 0.80,
                "days_remaining": 30,
            },
        ]

        out = check_action_coherence(markets)

        direct = next(
            m for m in out
            if m["action_type"] == "direct_engagement"
        )

        self.assertEqual(direct["p_b_given_a"], 0.44)
        self.assertTrue(
            any(
                "COMPONENT floor" in note
                for note in direct["coherence_notes"]
            )
        )


if __name__ == "__main__":
    unittest.main()
