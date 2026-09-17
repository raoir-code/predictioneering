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



def scoped_direction_key(
    initiator: str,
    target: str,
    scope_fingerprint: str,
) -> str:
    """
    Canonical key for a structural action prior.

    Direction alone is insufficient because identical actors can appear in
    contracts with materially different operational geography.
    """
    fp = str(scope_fingerprint).strip()

    if not fp:
        raise ValueError("scope_fingerprint must be non-empty")

    return (
        f"{direction_key(initiator, target)}"
        f"|scope={fp}"
    )



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



def _capped_simplex_projection(
    distribution: dict,
    caps: dict,
) -> dict:
    """
    Simultaneously enforce per-action hard ceilings:

        q_k = min(cap_k, lambda * p_k)

    with lambda chosen so the resulting distribution sums to one.

    Hard constraints must be applied jointly. Sequential cap-and-renormalize
    operations can cause a later renormalization to violate an earlier cap.
    """
    p = normalize_distribution(distribution)

    if set(caps) != set(ACTION_TYPES):
        raise ValueError(
            "caps must contain exactly all ACTION_TYPES"
        )

    clean_caps = {}

    for action in ACTION_TYPES:
        cap = float(caps[action])

        if not math.isfinite(cap):
            raise ValueError(
                f"Non-finite cap for {action}: {cap}"
            )

        if not 0.0 <= cap <= 1.0:
            raise ValueError(
                f"Cap outside [0,1] for {action}: {cap}"
            )

        clean_caps[action] = cap

    if sum(clean_caps.values()) < 1.0 - 1e-12:
        raise ValueError(
            "Hard caps are jointly infeasible."
        )

    if all(
        p[a] <= clean_caps[a] + 1e-12
        for a in ACTION_TYPES
    ):
        return p

    def mass(lam):
        return sum(
            min(clean_caps[a], lam * p[a])
            for a in ACTION_TYPES
        )

    lo = 0.0
    hi = 1.0

    while mass(hi) < 1.0:
        hi *= 2.0
        if hi > 1e15:
            raise RuntimeError(
                "Could not bracket capped-simplex solution"
            )

    for _ in range(200):
        mid = (lo + hi) / 2.0

        if mass(mid) < 1.0:
            lo = mid
        else:
            hi = mid

    out = {
        a: min(clean_caps[a], hi * p[a])
        for a in ACTION_TYPES
    }

    # Remove tiny floating-point excess without breaking caps.
    excess = sum(out.values()) - 1.0

    if excess > 0:
        for action in sorted(
            ACTION_TYPES,
            key=lambda a: out[a],
            reverse=True,
        ):
            delta = min(out[action], excess)
            out[action] -= delta
            excess -= delta

            if excess <= 1e-14:
                break

    deficit = 1.0 - sum(out.values())

    if deficit > 0:
        for action in sorted(
            ACTION_TYPES,
            key=lambda a: clean_caps[a] - out[a],
            reverse=True,
        ):
            if p[action] <= 0:
                continue

            slack = clean_caps[action] - out[action]

            if slack <= 0:
                continue

            delta = min(slack, deficit)
            out[action] += delta
            deficit -= delta

            if deficit <= 1e-14:
                break

    if abs(sum(out.values()) - 1.0) > 1e-10:
        raise AssertionError(
            "Joint cap projection does not sum to one"
        )

    for action in ACTION_TYPES:
        if out[action] > clean_caps[action] + 1e-10:
            raise AssertionError(
                f"Cap violation for {action}: "
                f"{out[action]} > {clean_caps[action]}"
            )

    return out


def apply_feasibility_guards(
    distribution: dict,
    feasibility: dict,
) -> dict:
    """
    Backward-compatible feasibility-only projection.
    """
    profile = normalize_feasibility_profile(feasibility)

    caps = {
        action: FEASIBILITY_CAPS[profile[action]]
        for action in ACTION_TYPES
    }

    return _capped_simplex_projection(
        distribution,
        caps,
    )


def apply_structural_constraints(
    distribution: dict,
    feasibility: dict | None = None,
    structural_flags: dict | None = None,
) -> dict:
    """
    Jointly apply every currently binding hard structural constraint.
    """
    caps = {
        action: 1.0
        for action in ACTION_TYPES
    }

    if feasibility is not None:
        profile = normalize_feasibility_profile(feasibility)

        for action in ACTION_TYPES:
            caps[action] = min(
                caps[action],
                FEASIBILITY_CAPS[profile[action]],
            )

    if structural_flags:
        if (
            structural_flags.get(
                "direct_engagement_contact_pathway"
            )
            is False
        ):
            caps["direct_engagement"] = min(
                caps["direct_engagement"],
                DIRECT_ENGAGEMENT_NO_CONTACT_CAP,
            )

    return _capped_simplex_projection(
        distribution,
        caps,
    )


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

    # Apply all hard ceilings in ONE projection. A later guard must
    # never renormalize probability back through an earlier ceiling.
    distribution = apply_structural_constraints(
        distribution,
        feasibility=feasibility,
        structural_flags=structural_flags,
    )
    return distribution


def top_action(distribution: dict) -> tuple[str, float]:
    p = normalize_distribution(distribution)
    action = max(ACTION_TYPES, key=p.get)
    return action, p[action]


def distribution_entropy(distribution: dict) -> float:
    p = normalize_distribution(distribution)
    return -sum(x * math.log(x) for x in p.values() if x > 0)
