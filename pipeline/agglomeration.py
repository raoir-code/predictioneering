"""
agglomeration.py — combine per-dyad probabilities into "any X" markets
========================================================================
Added 2026-09-11.

The production fallback is the original first-order pairwise approximation
in theater_registry.combine_any_of().

The formal model added 2026-10-03 is an opt-in one-factor Gaussian latent
state model with an optional bounded substitution correction.

Conceptually:

    common campaign/theater state
                ↓
      correlated target hazards
                ↓
       P(any target is hit)

Positive dependence comes from a shared latent factor whose loading is
modulated by each target's theater/host weight.

Negative dependence / target substitution is represented conservatively
by interpolating from the positively-dependent union probability toward
the Frechet upper bound min(1, sum(p_i)). This preserves the supplied
marginals and avoids inventing an invalid multivariate correlation matrix.

Formal aggregation is NOT production-active unless the aggregate config
explicitly contains:

    "formal_dependence": {
        "enabled": true,
        "common_factor_rho_max": ...,
        "substitution_strength": ...
    }

Otherwise the original approximation remains the fallback.
"""

import json
import math
import os
from statistics import NormalDist

from pipeline import theater_registry as T
from pipeline.translator import _get_market_deadline


AGG_CONFIG_PATH = os.path.join(
    os.path.dirname(__file__),
    "agglomeration_configs.json",
)

UNTRACKED_BASE_RATE_ANNUAL = 0.03
UNTRACKED_HORIZON_REFERENCE_DAYS = 90

_NORMAL = NormalDist()


def load_agglomeration_configs():
    if os.path.exists(AGG_CONFIG_PATH):
        with open(AGG_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def untracked_probability(days_remaining):
    days_remaining = max(days_remaining, 1)
    return 1 - (1 - UNTRACKED_BASE_RATE_ANNUAL) ** (
        days_remaining / UNTRACKED_HORIZON_REFERENCE_DAYS
    )


def find_constituent_market(
    country_dyad,
    target_deadline,
    all_markets,
):
    for m in all_markets:
        if m.get("dyad") != country_dyad:
            continue

        d, _, _ = _get_market_deadline(m)

        if d == target_deadline:
            return m

    return None


def independent_any(probabilities):
    """Exact union probability under mutual independence."""
    p_none = 1.0

    for p in probabilities:
        p = max(0.0, min(1.0, float(p)))
        p_none *= 1.0 - p

    return 1.0 - p_none


def _normal_pdf(z):
    return math.exp(-0.5 * z * z) / math.sqrt(2.0 * math.pi)


def _one_factor_gaussian_any(
    probs_and_weights,
    common_factor_rho_max,
    integration_bound=8.0,
    integration_intervals=320,
):
    """
    One-factor Gaussian Bernoulli union model.

    For target i:

        Y_i = loading_i * Z
              + sqrt(1-loading_i^2) * epsilon_i

        event_i = 1[Y_i <= Phi^-1(p_i)]

    where Z and epsilon_i are independent standard normals.

    Pairwise latent correlation is:

        corr(Y_i, Y_j) = loading_i * loading_j

    with:

        loading_i = sqrt(rho_max) * theater_weight_i

    Thus a target with little exposure to the shared theater state receives
    little common-factor dependence even if another target is highly exposed.
    """

    items = []

    for p, weight in probs_and_weights:
        p = max(0.0, min(1.0, float(p)))
        weight = max(0.0, min(1.0, float(weight)))

        if p >= 1.0:
            return 1.0

        if p > 0.0:
            items.append((p, weight))

    if not items:
        return 0.0

    probabilities = [p for p, _ in items]

    rho_max = max(
        0.0,
        min(0.999, float(common_factor_rho_max)),
    )

    # Exact independence limit.
    if rho_max == 0.0:
        return independent_any(probabilities)

    sqrt_rho = math.sqrt(rho_max)

    loadings = [
        sqrt_rho * weight
        for _, weight in items
    ]

    if max(loadings) <= 1e-12:
        return independent_any(probabilities)

    thresholds = [
        _NORMAL.inv_cdf(p)
        for p in probabilities
    ]

    def integrand(z):
        p_none_given_z = 1.0

        for threshold, loading in zip(
            thresholds,
            loadings,
        ):
            residual_sd = math.sqrt(
                max(1e-12, 1.0 - loading * loading)
            )

            conditional_p = _NORMAL.cdf(
                (threshold - loading * z)
                / residual_sd
            )

            p_none_given_z *= 1.0 - conditional_p

        return _normal_pdf(z) * p_none_given_z

    # Simpson integration over essentially all standard-normal mass.
    n = int(integration_intervals)

    if n < 20:
        n = 20

    if n % 2:
        n += 1

    a = -abs(float(integration_bound))
    b = abs(float(integration_bound))
    h = (b - a) / n

    total = integrand(a) + integrand(b)

    for i in range(1, n):
        z = a + i * h
        total += (
            4.0 if i % 2 else 2.0
        ) * integrand(z)

    p_none = total * h / 3.0
    p_any = 1.0 - p_none

    # Enforce exact Frechet bounds against numerical error.
    lower = max(probabilities)
    upper = min(1.0, sum(probabilities))

    return max(
        lower,
        min(upper, p_any),
    )


def combine_any_of_formal(
    probs_and_weights,
    common_factor_rho_max=0.35,
    substitution_strength=0.0,
):
    """
    Formal tracked-target union model.

    Step 1:
        One-factor Gaussian model captures positive dependence from the
        shared initiator/campaign/theater state.

    Step 2:
        substitution_strength in [0,1] represents target competition /
        finite-capacity substitution.

        0 -> no additional substitution correction
        1 -> maximal mutual-exclusivity limit permitted by the marginals

    For fixed marginals, negative dependence raises P(any) because it
    suppresses co-occurrence. The logical upper bound is min(1, sum p_i).
    """

    if not probs_and_weights:
        return 0.0

    probabilities = [
        max(0.0, min(1.0, float(p)))
        for p, _ in probs_and_weights
    ]

    positive_dependence_any = _one_factor_gaussian_any(
        probs_and_weights,
        common_factor_rho_max,
    )

    substitution_strength = max(
        0.0,
        min(1.0, float(substitution_strength)),
    )

    upper_bound = min(
        1.0,
        sum(probabilities),
    )

    final_p = (
        positive_dependence_any
        + substitution_strength
        * (upper_bound - positive_dependence_any)
    )

    lower_bound = max(probabilities)

    return max(
        lower_bound,
        min(upper_bound, final_p),
    )


def compute_any_of_probability(
    aggregate_dyad,
    aggregate_deadline,
    days_remaining,
    all_markets,
    known_dyad_keys,
    host_registry=None,
    agg_configs=None,
):
    host_registry = (
        host_registry
        if host_registry is not None
        else T.load_host_registry()
    )

    agg_configs = (
        agg_configs
        if agg_configs is not None
        else load_agglomeration_configs()
    )

    cfg = agg_configs.get(aggregate_dyad)

    if not cfg or cfg.get("is_enumerable") is False:
        return None, {
            "error":
                f"no usable agglomeration config for "
                f"'{aggregate_dyad}'"
        }

    initiator = cfg["initiator"]
    countries = cfg["qualifying_countries"]

    tracked_found = []
    tracked_missing = []
    genuinely_untracked = []

    for country in countries:
        candidate_dyad = f"{initiator}-{country}"

        if candidate_dyad not in known_dyad_keys:
            genuinely_untracked.append(country)
            continue

        m = find_constituent_market(
            candidate_dyad,
            aggregate_deadline,
            all_markets,
        )

        if m is None or m.get("our_prediction") is None:
            tracked_missing.append(country)
            continue

        role = T.resolve_dyad_role(
            candidate_dyad,
            registry=host_registry,
        )

        weight = (
            role.get("weight", 0.0)
            if role["role"] == "target"
            else 0.0
        )

        tracked_found.append(
            (
                country,
                candidate_dyad,
                m["our_prediction"],
                weight,
            )
        )

    tracked_probs_and_weights = [
        (p, w)
        for _, _, p, w in tracked_found
    ]

    formal_cfg = cfg.get("formal_dependence") or {}
    formal_enabled = bool(
        formal_cfg.get("enabled", False)
    )

    if tracked_probs_and_weights:
        if formal_enabled:
            rho_max = formal_cfg.get(
                "common_factor_rho_max",
                0.35,
            )
            substitution_strength = formal_cfg.get(
                "substitution_strength",
                0.0,
            )

            tracked_p_any = combine_any_of_formal(
                tracked_probs_and_weights,
                common_factor_rho_max=rho_max,
                substitution_strength=substitution_strength,
            )

            aggregation_model = (
                "one_factor_gaussian_with_substitution"
            )

        else:
            # Existing production approximation remains the fallback.
            tracked_p_any = T.combine_any_of(
                tracked_probs_and_weights
            )

            rho_max = None
            substitution_strength = None
            aggregation_model = (
                "pairwise_inclusion_exclusion_fallback"
            )

    else:
        tracked_p_any = 0.0
        rho_max = None
        substitution_strength = None
        aggregation_model = (
            "no_tracked_constituents"
        )

    p_untracked_single = untracked_probability(
        days_remaining
    )

    base_rate_fallback_countries = (
        tracked_missing
        + genuinely_untracked
    )

    n_fallback = len(
        base_rate_fallback_countries
    )

    untracked_p_any = (
        1
        - (1 - p_untracked_single) ** n_fallback
        if n_fallback
        else 0.0
    )

    # The untracked tail remains the pre-existing fallback approximation.
    # We do not pretend to know its covariance with tracked targets.
    final_p = (
        1
        - (1 - tracked_p_any)
        * (1 - untracked_p_any)
    )

    final_p = max(
        0.0,
        min(1.0, final_p),
    )

    diagnostics = {
        "tracked_found": tracked_found,
        "tracked_missing": tracked_missing,
        "genuinely_untracked": genuinely_untracked,
        "tracked_p_any": tracked_p_any,
        "untracked_p_any": untracked_p_any,
        "final_p": final_p,
        "aggregation_model": aggregation_model,
        "formal_dependence_enabled": formal_enabled,
        "common_factor_rho_max": rho_max,
        "substitution_strength": substitution_strength,
    }

    return final_p, diagnostics
