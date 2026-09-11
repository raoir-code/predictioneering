"""
agglomeration.py — combine per-dyad probabilities into "any X" markets
========================================================================
Added 2026-09-11. Implements the July 3, 2026 disjunctive-market design
("Will Iran attack any Arab country?") plus the Aug 21 untracked-tail
shortcut, using host-weight-derived dependence (theater_registry.py)
instead of a hand-set lambda.

Distinct from theater_registry.py's job: that module gets each
CONSTITUENT dyad's own probability closer to correct (by propagating
shared hazard into it). This module takes those already-correct
per-dyad probabilities and combines them into the union probability
the aggregate contract actually asks about. Two different steps --
signal injection, then combination -- not the same problem twice.
"""

import json
import os

from pipeline import theater_registry as T
from pipeline.translator import _get_market_deadline

AGG_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "agglomeration_configs.json")

UNTRACKED_BASE_RATE_ANNUAL = 0.03
UNTRACKED_HORIZON_REFERENCE_DAYS = 90


def load_agglomeration_configs():
    if os.path.exists(AGG_CONFIG_PATH):
        with open(AGG_CONFIG_PATH) as f:
            return json.load(f)
    return {}


def untracked_probability(days_remaining):
    days_remaining = max(days_remaining, 1)
    return 1 - (1 - UNTRACKED_BASE_RATE_ANNUAL) ** (days_remaining / UNTRACKED_HORIZON_REFERENCE_DAYS)


def find_constituent_market(country_dyad, target_deadline, all_markets):
    for m in all_markets:
        if m.get("dyad") != country_dyad:
            continue
        d, _, _ = _get_market_deadline(m)
        if d == target_deadline:
            return m
    return None


def compute_any_of_probability(aggregate_dyad, aggregate_deadline, days_remaining,
                                all_markets, known_dyad_keys,
                                host_registry=None, agg_configs=None):
    host_registry = host_registry if host_registry is not None else T.load_host_registry()
    agg_configs = agg_configs if agg_configs is not None else load_agglomeration_configs()

    cfg = agg_configs.get(aggregate_dyad)
    if not cfg or cfg.get("is_enumerable") is False:
        return None, {"error": f"no usable agglomeration config for '{aggregate_dyad}'"}

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
        m = find_constituent_market(candidate_dyad, aggregate_deadline, all_markets)
        if m is None or m.get("our_prediction") is None:
            tracked_missing.append(country)
            continue
        role = T.resolve_dyad_role(candidate_dyad, registry=host_registry)
        weight = role.get("weight", 0.0) if role["role"] == "target" else 0.0
        tracked_found.append((country, candidate_dyad, m["our_prediction"], weight))

    tracked_probs_and_weights = [(p, w) for _, _, p, w in tracked_found]
    tracked_p_any = T.combine_any_of(tracked_probs_and_weights) if tracked_probs_and_weights else 0.0

    p_untracked_single = untracked_probability(days_remaining)
    base_rate_fallback_countries = tracked_missing + genuinely_untracked
    n_fallback = len(base_rate_fallback_countries)
    untracked_p_any = 1 - (1 - p_untracked_single) ** n_fallback if n_fallback else 0.0

    final_p = 1 - (1 - tracked_p_any) * (1 - untracked_p_any)

    diagnostics = {
        "tracked_found": tracked_found,
        "tracked_missing": tracked_missing,
        "genuinely_untracked": genuinely_untracked,
        "tracked_p_any": tracked_p_any,
        "untracked_p_any": untracked_p_any,
        "final_p": final_p,
    }
    return final_p, diagnostics
