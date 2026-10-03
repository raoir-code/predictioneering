import os
import unittest

os.environ.setdefault(
    "ANTHROPIC_API_KEY",
    "test-key",
)
os.environ.setdefault(
    "GNEWS_API_KEY",
    "test-key",
)

from pipeline.agglomeration import (
    combine_any_of_formal,
    independent_any,
)


class FormalAgglomerationTests(unittest.TestCase):

    def test_independence_limit(self):
        items = [
            (0.20, 1.0),
            (0.30, 0.7),
            (0.10, 0.4),
        ]

        expected = independent_any(
            [0.20, 0.30, 0.10]
        )

        got = combine_any_of_formal(
            items,
            common_factor_rho_max=0.0,
            substitution_strength=0.0,
        )

        self.assertAlmostEqual(
            got,
            expected,
            places=12,
        )

    def test_positive_common_factor_reduces_union(self):
        items = [
            (0.30, 1.0),
            (0.30, 1.0),
            (0.30, 1.0),
        ]

        independent = independent_any(
            [0.30, 0.30, 0.30]
        )

        dependent = combine_any_of_formal(
            items,
            common_factor_rho_max=0.80,
            substitution_strength=0.0,
        )

        self.assertGreaterEqual(
            dependent,
            0.30,
        )
        self.assertLess(
            dependent,
            independent,
        )

    def test_substitution_raises_union_toward_upper_bound(self):
        items = [
            (0.20, 1.0),
            (0.25, 0.8),
            (0.15, 0.6),
        ]

        base = combine_any_of_formal(
            items,
            common_factor_rho_max=0.50,
            substitution_strength=0.0,
        )

        partial = combine_any_of_formal(
            items,
            common_factor_rho_max=0.50,
            substitution_strength=0.50,
        )

        maximal = combine_any_of_formal(
            items,
            common_factor_rho_max=0.50,
            substitution_strength=1.0,
        )

        upper = min(
            1.0,
            sum(p for p, _ in items),
        )

        self.assertGreater(
            partial,
            base,
        )
        self.assertGreater(
            maximal,
            partial,
        )
        self.assertAlmostEqual(
            maximal,
            upper,
            places=12,
        )

    def test_adding_eligible_target_is_monotone(self):
        two = [
            (0.20, 1.0),
            (0.15, 0.7),
        ]

        three = two + [
            (0.10, 0.5),
        ]

        p_two = combine_any_of_formal(
            two,
            common_factor_rho_max=0.40,
            substitution_strength=0.20,
        )

        p_three = combine_any_of_formal(
            three,
            common_factor_rho_max=0.40,
            substitution_strength=0.20,
        )

        self.assertGreaterEqual(
            p_three,
            p_two,
        )

    def test_frechet_bounds(self):
        items = [
            (0.60, 1.0),
            (0.40, 0.8),
            (0.20, 0.5),
        ]

        result = combine_any_of_formal(
            items,
            common_factor_rho_max=0.95,
            substitution_strength=0.35,
        )

        lower = max(
            p for p, _ in items
        )
        upper = min(
            1.0,
            sum(p for p, _ in items),
        )

        self.assertGreaterEqual(
            result,
            lower,
        )
        self.assertLessEqual(
            result,
            upper,
        )
        self.assertGreaterEqual(
            result,
            0.0,
        )
        self.assertLessEqual(
            result,
            1.0,
        )

    def test_order_invariance(self):
        items = [
            (0.12, 0.3),
            (0.27, 1.0),
            (0.18, 0.6),
            (0.09, 0.4),
        ]

        forward = combine_any_of_formal(
            items,
            common_factor_rho_max=0.45,
            substitution_strength=0.25,
        )

        backward = combine_any_of_formal(
            list(reversed(items)),
            common_factor_rho_max=0.45,
            substitution_strength=0.25,
        )

        self.assertAlmostEqual(
            forward,
            backward,
            places=12,
        )


if __name__ == "__main__":
    unittest.main()
