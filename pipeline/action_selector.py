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
seven-way distribution. Downstream action_coherence handles physical
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
)

ROOT = Path(__file__).resolve().parent
ACTION_PRIORS_PATH = ROOT / "action_priors.json"


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
    Validate and normalize a complete seven-action distribution.
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


def select_distribution(
    structural_prior: dict,
    live_scores: dict | None = None,
    temperature: float = 1.0,
) -> dict:
    """
    Combine structural prior with additive live log-evidence.

        logit_k = log(prior_k) + live_score_k

    followed by a seven-way softmax.

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

    return {
        action: weights[action] / denom
        for action in ACTION_TYPES
    }


def top_action(distribution: dict) -> tuple[str, float]:
    p = normalize_distribution(distribution)
    action = max(ACTION_TYPES, key=p.get)
    return action, p[action]


def distribution_entropy(distribution: dict) -> float:
    p = normalize_distribution(distribution)
    return -sum(x * math.log(x) for x in p.values() if x > 0)
