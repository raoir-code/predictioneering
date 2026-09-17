"""
Directional conditional action selector.

Core estimand
-------------
P(primary_action_type = k |
  initiator undertakes a qualifying physical coercive/military action
  against target)

This is CONDITIONAL on an action occurring.

It must NEVER independently alter the engine's probability that conflict or
a coercive event occurs. The bargaining/onset/theater machinery owns that.

"Primary action type" means the action family that best characterizes the
operational objective of the next escalation episode, not necessarily the
first weapon physically fired.

Examples:
- missile barrage supporting an amphibious territorial operation:
    primary = ground_invasion
- boardings enforcing a sustained maritime quarantine:
    primary = naval_blockade
- standalone ballistic/drone volley:
    primary = missile_strike
- isolated vessel seizure:
    primary = seizure_boarding

This makes the selector categories mutually exclusive enough to form a
eight-way distribution. Downstream action_coherence handles physical
overlap/components between contracts.

Phase 1:
- directional structural priors
- deterministic normalization
- generic log-score/softmax update interface

Live action evidence and historical calibration are separate phases.
"""

import json
import math
from pathlib import Path


ACTION_TYPES = (
    "gray_zone_incident",
    "missile_strike",
    "raid",
    "seizure_boarding",
    "airstrike",
    "naval_blockade",
    "ground_invasion",
    "direct_engagement",
)

ROOT = Path(__file__).resolve().parent
ACTION_PRIORS_PATH = ROOT / "action_priors.json"


# Stable structural feasibility is separate from probability.
#
# Only the bottom two tiers impose hard ceilings. "feasible" and "natural"
# remain unconstrained so this layer cannot become a hand-tuned ranking system.
FEASIBILITY_TIERS = {
    "unavailable",
    "severely_constrained",
    "feasible",
    "natural",
}

FEASIBILITY_CAPS = {
    # "unavailable" is the actual hard sanity guard. Keep a tiny residual
    # rather than literal zero because the stored structural profile may be
    # stale or imperfect.
    "unavailable": 0.005,

    # These are diagnostic structural labels, not a second probability model.
    # Their difficulty should already be represented in the structural prior.
    "severely_constrained": 1.0,
    "feasible": 1.0,
    "natural": 1.0,
}

# direct_engagement means overt combat between already-deployed opposing
# forces. Without an ordinary force-contact pathway it should retain only
# tiny residual mass in case the structural profile is stale.
DIRECT_ENGAGEMENT_NO_CONTACT_CAP = 0.01




def direction_key(initiator: str, target: str) -> str:
    initiator = str(initiator).strip()
    target = str(target).strip()

    if not initiator or not target:
        raise ValueError("initiator and target must both be non-empty")
    if initiator == target:
        raise ValueError("initiator and target must differ")

    return f"{initiator}->{target}"


def normalize_distribution(raw: dict) -> dict:
    """
    Validate and normalize a complete eight-action distribution.
    """
    missing = [a for a in ACTION_TYPES if a not in raw]
    extra = [k for k in raw if k not in ACTION_TYPES]

    if missing:
        raise ValueError(f"Missing action probabilities: {missing}")
    if extra:
        raise ValueError(f"Unknown action probabilities: {extra}")

    cleaned = {}

    for action in ACTION_TYPES:
        try:
            value = float(raw[action])
        except (TypeError, ValueError):
            raise ValueError(
                f"Non-numeric probability for {action}: {raw[action]!r}"
            )

        if not math.isfinite(value):
            raise ValueError(f"Non-finite probability for {action}: {value}")
        if value < 0:
            raise ValueError(f"Negative probability for {action}: {value}")

        cleaned[action] = value

    total = sum(cleaned.values())
    if total <= 0:
        raise ValueError("Action distribution has zero total mass")

    return {
        action: cleaned[action] / total
        for action in ACTION_TYPES
    }



def normalize_feasibility_profile(raw: dict) -> dict:
    """
    Validate a complete feasibility profile for all action families.
    """
    if not isinstance(raw, dict):
        raise ValueError("Feasibility profile must be a dict")

    missing = [a for a in ACTION_TYPES if a not in raw]
    extra = [k for k in raw if k not in ACTION_TYPES]

    if missing:
        raise ValueError(f"Missing feasibility tiers: {missing}")
    if extra:
        raise ValueError(f"Unknown feasibility actions: {extra}")

    out = {}
    for action in ACTION_TYPES:
        tier = str(raw[action]).strip().lower()
        if tier not in FEASIBILITY_TIERS:
            raise ValueError(
                f"Invalid feasibility tier for {action}: {tier!r}"
            )
        out[action] = tier

    return out


def apply_feasibility_guards(
    raw_distribution: dict,
    feasibility: dict,
) -> dict:
    """
    Project a probability distribution onto structural feasibility ceilings.

    This is a capped-simplex projection that preserves the raw relative odds
    as much as possible:

        q_k = min(cap_k, lambda * p_k)

    with lambda chosen so sum(q)=1.

    The guard therefore does NOT manufacture rankings among actions that are
    feasible. It only prevents structurally unavailable or severely
    constrained modes from carrying implausibly large probability mass.
    """
    p = normalize_distribution(raw_distribution)
    tiers = normalize_feasibility_profile(feasibility)

    caps = {
        action: FEASIBILITY_CAPS[tiers[action]]
        for action in ACTION_TYPES
    }

    if sum(caps.values()) < 1.0 - 1e-12:
        raise ValueError(
            "Feasibility ceilings leave less than 1.0 total probability capacity"
        )

    def total(scale):
        return sum(
            min(caps[a], scale * p[a])
            for a in ACTION_TYPES
        )

    # Find an upper bound for the water-filling scale.
    lo = 0.0
    hi = 1.0
    while total(hi) < 1.0:
        hi *= 2.0
        if hi > 1e12:
            raise ValueError("Could not satisfy feasibility ceilings")

    # Binary search lambda.
    for _ in range(100):
        mid = (lo + hi) / 2.0
        if total(mid) < 1.0:
            lo = mid
        else:
            hi = mid

    scale = hi

    guarded = {
        a: min(caps[a], scale * p[a])
        for a in ACTION_TYPES
    }

    # Numerical cleanup only.
    z = sum(guarded.values())
    if z <= 0:
        raise ValueError("Guarded action distribution has zero mass")

    guarded = {
        a: guarded[a] / z
        for a in ACTION_TYPES
    }

    # Floating-point normalization must not defeat a hard ceiling.
    for a in ACTION_TYPES:
        if guarded[a] > caps[a] + 1e-9:
            raise AssertionError(
                f"Feasibility cap violated for {a}: "
                f"{guarded[a]} > {caps[a]}"
            )

    return guarded




def apply_structural_prerequisites(
    distribution: dict,
    structural_flags: dict | None,
) -> dict:
    """
    Apply action-specific logical prerequisites.

    Currently direct_engagement requires an ordinary pathway for the two
    actors' own deployed forces to encounter one another directly.
    """
    p = normalize_distribution(distribution)

    if not structural_flags:
        return p

    contact = structural_flags.get(
        "direct_engagement_contact_pathway"
    )

    if contact is not False:
        return p

    cap = DIRECT_ENGAGEMENT_NO_CONTACT_CAP

    # Capped-simplex projection preserving relative odds among all other
    # actions.
    direct = min(p["direct_engagement"], cap)

    remaining_actions = [
        a for a in ACTION_TYPES
        if a != "direct_engagement"
    ]

    other_mass = sum(p[a] for a in remaining_actions)

    if other_mass <= 0:
        raise ValueError(
            "No probability mass available outside direct_engagement"
        )

    target_other_mass = 1.0 - direct

    out = {
        a: (
            p[a] / other_mass * target_other_mass
            if a != "direct_engagement"
            else direct
        )
        for a in ACTION_TYPES
    }

    return out



def load_action_priors(path=ACTION_PRIORS_PATH) -> dict:
    path = Path(path)

    if not path.exists():
        return {}

    data = json.loads(path.read_text())

    if not isinstance(data, dict):
        raise ValueError("action_priors.json must contain a JSON object")

    return data


def save_action_priors(data: dict, path=ACTION_PRIORS_PATH):
    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    tmp.replace(path)


def get_structural_prior(
    initiator: str,
    target: str,
    priors: dict | None = None,
) -> dict | None:
    """
    Return the normalized structural prior for an explicit direction.

    No silent reverse-direction fallback is allowed.
    US->Iran and Iran->US are substantively different objects.
    """
    priors = load_action_priors() if priors is None else priors

    entry = priors.get(direction_key(initiator, target))
    if entry is None:
        return None

    raw = entry.get("probabilities", entry)
    return normalize_distribution(raw)



def get_structural_feasibility(
    initiator: str,
    target: str,
    priors: dict | None = None,
) -> dict | None:
    """
    Return the stored structural feasibility profile for a direction.
    """
    priors = load_action_priors() if priors is None else priors
    entry = priors.get(direction_key(initiator, target))

    if entry is None:
        return None

    raw = entry.get("feasibility")
    if raw is None:
        return None

    return normalize_feasibility_profile(raw)



def select_distribution(
    structural_prior: dict,
    live_scores: dict | None = None,
    temperature: float = 1.0,
    feasibility: dict | None = None,
    structural_flags: dict | None = None,
) -> dict:
    """
    Combine structural prior with additive live log-evidence.

        logit_k = log(prior_k) + live_score_k

    followed by a eight-way softmax.

    With zero live evidence and temperature=1, output equals prior.
    """
    if temperature <= 0:
        raise ValueError("temperature must be > 0")

    prior = normalize_distribution(structural_prior)
    live_scores = live_scores or {}

    unknown = [k for k in live_scores if k not in ACTION_TYPES]
    if unknown:
        raise ValueError(f"Unknown live-score action(s): {unknown}")

    logits = {}

    for action in ACTION_TYPES:
        evidence = float(live_scores.get(action, 0.0))
        if not math.isfinite(evidence):
            raise ValueError(
                f"Non-finite live score for {action}: {evidence}"
            )

        logits[action] = (
            math.log(max(prior[action], 1e-12)) + evidence
        ) / temperature

    max_logit = max(logits.values())

    weights = {
        action: math.exp(logits[action] - max_logit)
        for action in ACTION_TYPES
    }

    denom = sum(weights.values())

    distribution = {
        action: weights[action] / denom
        for action in ACTION_TYPES
    }

    # Hard structural constraints remain binding after live evidence.
    # A news headline cannot make an operationally unavailable mode suddenly
    # acquire large probability without first changing the structural profile.
    if feasibility is not None:
        distribution = apply_feasibility_guards(
            distribution,
            feasibility,
        )

    distribution = apply_structural_prerequisites(
        distribution,
        structural_flags,
    )

    return distribution


def top_action(distribution: dict) -> tuple[str, float]:
    p = normalize_distribution(distribution)
    action = max(ACTION_TYPES, key=p.get)
    return action, p[action]


def distribution_entropy(distribution: dict) -> float:
    p = normalize_distribution(distribution)
    return -sum(x * math.log(x) for x in p.values() if x > 0)
