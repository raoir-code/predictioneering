"""
theater_registry.py — shared actor/theater-level escalation state
====================================================================
Rewritten 2026-09-11 (agglomeration session) to replace 2026-09-10's
hand-picked Iran-only `theater_groups.json`. That version worked for
Iran this week and would have done nothing for any other conflict --
overfit to the one crisis in front of us. This version derives
membership from a general fact about the world (who hosts whose
military assets) instead of a hand-picked list, so the SAME logic
covers China/Taiwan, Russia/NATO, etc. without new code -- only a new
row in host_registry.json.

Core idea: a strike doesn't propagate because "Iran and Jordan are
linked" -- it propagates because Jordan hosts assets belonging to
whichever patron (the US) Iran is actually escalating with. The
causal object is a hosting relation between (initiator, patron), not
a hand-picked dyad group.

Two files:
  - host_registry.json (hand-maintained, read-only from here): real-
    world basing data, patron -> {host_country: weight}. Conflict-
    agnostic -- doesn't change when Iran calms down or China flares up.
  - theater_state.json  (read-write, owned by this module): persisted,
    decaying hazard per (initiator, patron) pair. Same half-life/decay
    pattern as predict.py's node_memory_state.json (Phase 0b, 2026-09-10).

One small piece of hand-maintained config survives: AGGREGATE_LABELS,
declaring which dyad strings are synthetic aggregates (e.g.
"Iran-ArabStates" isn't a real country, so it can't be resolved from
the registry). Everything else -- membership, weights, propagation --
is derived, not hand-picked.
"""

import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST_REGISTRY_PATH = os.path.join(os.path.dirname(__file__), "host_registry.json")
THEATER_STATE_PATH = os.path.join(os.path.dirname(__file__), "theater_state.json")

THEATER_HAZARD_HALF_LIFE_DAYS = 10
THEATER_DECAY_FACTOR = 0.5 ** (1.0 / THEATER_HAZARD_HALF_LIFE_DAYS)

AGGREGATE_LABELS = {
    "Iran-ArabStates": {"initiator": "Iran", "patron": "US"},
}


def load_host_registry():
    if os.path.exists(HOST_REGISTRY_PATH):
        with open(HOST_REGISTRY_PATH) as f:
            return json.load(f)
    return {}


def load_theater_state():
    if os.path.exists(THEATER_STATE_PATH):
        with open(THEATER_STATE_PATH) as f:
            return json.load(f)
    return {}


def save_theater_state(state):
    tmp = THEATER_STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, THEATER_STATE_PATH)


def _split_dyad(dyad):
    if not dyad or "-" not in dyad:
        return None
    a, b = dyad.split("-", 1)
    return a, b


def _state_key(initiator, patron):
    return f"{initiator}|{patron}"


def resolve_dyad_role(dyad, registry=None):
    """
    Parses `dyad` against the host registry with zero Iran-specific
    logic -- only the registry's data determines the answer.

    Returns a dict:
      {"role": "trigger", "initiator": ..., "patron": ...}
      {"role": "target",  "initiator": ..., "patron": ..., "weight": ...}
      {"role": None}   -- not part of any registered theater
    """
    registry = registry if registry is not None else load_host_registry()

    if dyad in AGGREGATE_LABELS:
        agg = AGGREGATE_LABELS[dyad]
        return {"role": "aggregate", "initiator": agg["initiator"], "patron": agg["patron"]}

    parts = _split_dyad(dyad)
    if not parts:
        return {"role": None}
    a, b = parts

    for patron, cfg in registry.items():
        hosts = cfg.get("hosts", {})
        if a == patron and b not in hosts:
            return {"role": "trigger", "initiator": b, "patron": patron}
        if b == patron and a not in hosts:
            return {"role": "trigger", "initiator": a, "patron": patron}
        if b in hosts:
            return {"role": "target", "initiator": a, "patron": patron, "weight": hosts[b]}
        if a in hosts:
            return {"role": "target", "initiator": b, "patron": patron, "weight": hosts[a]}

    return {"role": None}


def aggregate_weight(initiator, patron, known_dyad_keys, registry=None):
    """For a synthetic aggregate, its own weight = the max hosting weight
    among the initiator's ACTUALLY-TRACKED host-country dyads (the
    aggregate's risk is driven by whichever single constituent is most
    exposed, not diluted by averaging in low-weight ones)."""
    registry = registry if registry is not None else load_host_registry()
    hosts = registry.get(patron, {}).get("hosts", {})
    weights = []
    for country, w in hosts.items():
        candidate = f"{initiator}-{country}"
        if candidate in known_dyad_keys:
            weights.append(w)
    return max(weights) if weights else 0.0


def get_news_inheritance_sources(dyad, known_dyad_keys, registry=None):
    """Phase 1d equivalent: if `dyad` is a synthetic aggregate, return the
    initiator's other ACTUALLY-TRACKED host-country dyads whose GNews
    should be merged into its own fetch. General version of yesterday's
    hand-picked sibling list."""
    registry = registry if registry is not None else load_host_registry()
    role = resolve_dyad_role(dyad, registry=registry)
    if role["role"] != "aggregate":
        return []
    initiator, patron = role["initiator"], role["patron"]
    hosts = registry.get(patron, {}).get("hosts", {})
    sources = []
    for country in hosts:
        candidate = f"{initiator}-{country}"
        if candidate in known_dyad_keys and candidate != dyad:
            sources.append(candidate)
    return sources


def decayed_hazard(initiator, patron, today, state=None):
    state = state if state is not None else load_theater_state()
    entry = state.get(_state_key(initiator, patron))
    if not entry:
        return 0.0
    as_of = entry.get("as_of")
    hazard = entry.get("hazard", 0.0)
    if not as_of:
        return 0.0
    days_elapsed = max((today - date.fromisoformat(as_of)).days, 0)
    return hazard * (THEATER_DECAY_FACTOR ** days_elapsed)


def update_hazard(initiator, patron, today, today_local_acute_core, state=None):
    """Contribution side is UNWEIGHTED -- any member's confirmed local
    evidence is real evidence about the initiator's overall posture
    toward this patron, regardless of that specific member's own
    hosting weight. Weighting only applies on the READ side
    (weighted_hazard below) -- how relevant the shared posture is to
    a SPECIFIC target, not how much a target's own evidence counts
    toward the shared estimate."""
    state = state if state is not None else load_theater_state()
    prior_decayed = decayed_hazard(initiator, patron, today, state=state)
    new_hazard = max(today_local_acute_core, prior_decayed)
    state[_state_key(initiator, patron)] = {"hazard": new_hazard, "as_of": today.isoformat()}
    return state


def weighted_hazard(initiator, patron, weight, today, state=None):
    """The READ side: a target's own hosting weight scales how much of
    the shared hazard actually applies to it. A country with no US
    assets to speak of shouldn't inherit the same alarm as Qatar does."""
    return weight * decayed_hazard(initiator, patron, today, state=state)


def dependence_multiplier(weight_i, weight_j):
    """Derives the July 3 design's hand-set lambda_ij from real hosting
    weights instead of picking one of four buckets (0.75/1.00/1.25/1.50)
    by eyeball. lambda = 1.0 + 0.5*min(w_i, w_j): floors at 1.0 (no
    shared driver -> back to independence) and caps at 1.5 (both
    maximally exposed to the same patron -- the July 3 "same deployment/
    ultimatum/campaign logic" bucket's own top value). Uses min(), not
    average or max, deliberately: two dyads' shared-driver correlation
    should be bounded by whichever of the two is LESS tied to that
    driver -- Jordan (0.4) paired with Qatar (1.0) shouldn't leap to the
    full 1.5 just because Qatar is highly exposed; Jordan's own risk
    has other drivers too.
    Does NOT model the July 3 design's negative/substitution side
    (lambda=0.75, capacity-constraint) -- hosting weight only speaks to
    the positive shared-disposition force. That fallback stays hand-set
    until a substitution signal exists to derive it from too."""
    return 1.0 + 0.5 * min(weight_i, weight_j)


def combine_any_of(probs_and_weights):
    """First-order (pairwise) inclusion-exclusion per the July 3 design:
    P(any) ~= sum(p_i) - sum_{i<j} lambda_ij * p_i * p_j
    `probs_and_weights`: list of (p_i, weight_i) tuples for TRACKED
    dyads only -- the untracked-country tail is a separate, already-
    designed shortcut (Aug 21: base-rate default + heavy market-blend),
    not this function's job. Clamped to [0, 1] since pairwise truncation
    can overshoot for a large N with high individual probabilities --
    a known limitation of the near-term approximation, not a bug."""
    total = sum(p for p, _ in probs_and_weights)
    n = len(probs_and_weights)
    correction = 0.0
    for i in range(n):
        p_i, w_i = probs_and_weights[i]
        for j in range(i + 1, n):
            p_j, w_j = probs_and_weights[j]
            correction += dependence_multiplier(w_i, w_j) * p_i * p_j
    return max(0.0, min(1.0, total - correction))
