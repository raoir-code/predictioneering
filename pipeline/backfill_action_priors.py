"""
Generate structural priors for the directional action selector.

Estimand:
    P(primary action family = k |
      INITIATOR undertakes a qualifying physical coercive/military action
      against TARGET)

This is NOT:
- P(conflict)
- P(action occurs)
- a forecast using today's news
- the fastest physically possible action
- a list of every action that might happen later in a war

Priors are keyed directionally:
    US->Iran
    Iran->US

Never reverse one direction as a fallback for the other.

Examples:
    python3.11 -m pipeline.backfill_action_priors \
        --dry-run --direction 'US->Iran'

    python3.11 -m pipeline.backfill_action_priors \
        --dry-run \
        --direction 'US->Iran' \
        --direction 'Iran->US'

    python3.11 -m pipeline.backfill_action_priors \
        --discover --dry-run --limit 10
"""

import argparse
import json
import os
import shutil
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from pipeline.action_selector import (
    ACTION_PRIORS_PATH,
    ACTION_TYPES,
    direction_key,
    load_action_priors,
    normalize_distribution,
    save_action_priors,
)


ROOT = Path(__file__).resolve().parent
CLASSIFIED_FEED_PATH = ROOT / "classified_feed.json"

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-6"


SYSTEM_PROMPT = """
You are constructing a STRUCTURAL PRIOR for a geopolitical action selector.

The direction is explicit:

    INITIATOR -> TARGET

Assume the initiator DOES undertake a qualifying physical coercive or
military action against the target.

Do NOT estimate whether such action is likely to occur.

Estimate instead:

    P(PRIMARY ACTION FAMILY = k | ACTION OCCURS)

where PRIMARY ACTION FAMILY means the single action category that best
characterizes the operational objective of the NEXT escalation episode.

This is not necessarily the first weapon fired.

Use exactly these seven categories:

1. gray_zone_incident
   Limited physical coercion short of a larger discrete operation:
   dangerous intercept, ramming, water cannon, physical maritime harassment,
   operational drone harassment, border friction, cable interference, etc.

2. missile_strike
   A standalone standoff strike episode primarily characterized by ballistic,
   cruise, loitering-munition, or one-way attack-drone employment.

   For this ontology, a drone/missile salvo whose operational purpose is
   simply to strike the target belongs here.

3. raid
   A discrete limited incursion, special-operations mission, hostage/capture
   operation, or short cross-border ground action whose objective is narrower
   than sustained territorial conquest.

4. seizure_boarding
   A discrete interception, boarding, detention, or seizure of a vessel or
   aircraft, when it is NOT merely an enforcement component of a broader
   blockade.

5. airstrike
   A standalone strike episode primarily characterized by combat aircraft or
   other conventional air-delivered attack, rather than missile_strike.

6. naval_blockade
   A sustained maritime quarantine, exclusion, denial-of-access, or blockade
   operation.

   If boardings/interceptions are primarily enforcing a larger blockade,
   classify the episode as naval_blockade, not seizure_boarding.

7. ground_invasion
   A sustained ground operation whose objective includes entering, seizing,
   holding, occupying, or controlling meaningful territory.

   If missiles/airstrikes are preparatory fires for an invasion whose central
   objective is territorial control, classify the PRIMARY episode as
   ground_invasion.

MUTUAL-EXCLUSIVITY DISCIPLINE

Real operations are multimodal. You must still distribute probability over
the PRIMARY operational form.

Examples:
- amphibious invasion preceded by missile strikes -> ground_invasion
- blockade enforced through boarding ships -> naval_blockade
- standalone tanker seizure -> seizure_boarding
- standalone ballistic/drone volley -> missile_strike
- fighter bombing without territorial-control objective -> airstrike
- limited special-forces border incursion -> raid
- dangerous coast-guard encounter without broader operation ->
  gray_zone_incident

STRUCTURAL INFORMATION YOU MAY USE

- geography and borders
- distance
- coastlines and chokepoints
- real military reach and force posture
- basing/access
- logistical requirements
- recurring historical interaction patterns
- doctrine
- demonstrated capabilities
- target vulnerability
- whether forces are routinely co-located

DO NOT USE

- today's headlines
- today's crisis intensity
- current political rhetoric
- prediction-market prices
- today's theater-hazard score
- whether conflict is likely in the first place

CRITICAL REALISM RULES

Do not give substantial probability merely because an action is imaginable.

A mode requiring an enormous qualitative jump in logistics, access, force
posture, or political commitment should receive very little mass unless it
is genuinely a structurally natural option for this actor-target pair.

Examples:
- no meaningful expeditionary route -> ground invasion should generally be
  tiny, even if physically possible in science-fiction terms
- no relevant maritime interaction -> seizure/boarding should be tiny
- no plausible sustained sea-control mechanism -> blockade should be tiny
- no practical air access -> airstrike should be suppressed
- actors already confronting one another with coast guards/patrols ->
  gray-zone actions can be substantial

Do not confuse "possible eventually in a total war" with "structurally
plausible as the primary form of the next action episode."

Probability mass should be concentrated when military geography clearly
favors a few modes, but retain reasonable uncertainty when several genuine
options exist.

Return ONLY JSON:

{
  "gray_zone_incident": 0.10,
  "missile_strike": 0.30,
  "raid": 0.10,
  "seizure_boarding": 0.05,
  "airstrike": 0.25,
  "naval_blockade": 0.10,
  "ground_invasion": 0.10,
  "reasoning": "One concise sentence.",
  "confidence": "high|medium|low"
}

The seven probabilities should sum approximately to 1.
"""


def parse_direction(value: str) -> tuple[str, str]:
    if "->" not in value:
        raise argparse.ArgumentTypeError(
            "direction must have form INITIATOR->TARGET"
        )

    initiator, target = value.split("->", 1)
    initiator = initiator.strip()
    target = target.strip()

    if not initiator or not target or initiator == target:
        raise argparse.ArgumentTypeError(
            "direction must contain two different non-empty actors"
        )

    return initiator, target


def extract_json(text: str) -> dict:
    text = text.strip()

    if "```" in text:
        for part in text.split("```"):
            part = part.strip()
            if part.startswith("json"):
                part = part[4:].strip()
            try:
                return json.loads(part)
            except Exception:
                pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def classify_direction(
    initiator: str,
    target: str,
) -> tuple[dict, str, str]:

    prompt = f"""
INITIATOR: {initiator}
TARGET: {target}

Conditional on {initiator} undertaking a qualifying physical coercive or
military action against {target}, estimate the seven-way structural
distribution over the PRIMARY action family of the next escalation episode.
"""

    body = {
        "model": MODEL,
        "max_tokens": 700,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }

    response = requests.post(
        ANTHROPIC_API,
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json=body,
        timeout=60,
    )

    response.raise_for_status()
    payload = response.json()

    if "content" not in payload:
        raise RuntimeError(
            payload.get("error", {}).get("message", "Claude API error")
        )

    parsed = extract_json(payload["content"][0]["text"])

    raw = {
        action: parsed.get(action)
        for action in ACTION_TYPES
    }

    probs = normalize_distribution(raw)

    reasoning = str(parsed.get("reasoning", "")).strip()
    confidence = str(parsed.get("confidence", "medium")).strip().lower()

    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    return probs, reasoning, confidence


def discover_directions() -> list[tuple[str, str]]:
    """
    Discover only directions that the translator has explicitly identified
    on current physical contracts.

    This deliberately does not infer direction from canonical dyad ordering.
    """
    if not CLASSIFIED_FEED_PATH.exists():
        return []

    data = json.loads(CLASSIFIED_FEED_PATH.read_text())
    rows = data if isinstance(data, list) else data.get(
        "markets",
        data.get("data", []),
    )

    found = set()

    for market in rows:
        if not isinstance(market, dict):
            continue

        if (
            market.get("manifestation_family")
            != "kinetic_or_coercive_action"
        ):
            continue

        initiator = market.get("contract_initiator")
        target = market.get("contract_target")

        if not initiator or not target or initiator == target:
            continue

        found.add((str(initiator), str(target)))

    return sorted(found)


def format_distribution(probs: dict) -> str:
    ranked = sorted(
        probs.items(),
        key=lambda item: item[1],
        reverse=True,
    )

    return ", ".join(
        f"{action}={p:.3f}"
        for action, p in ranked
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--direction",
        action="append",
        default=[],
        help="Explicit direction, e.g. 'Iran->US'. May repeat.",
    )

    parser.add_argument(
        "--discover",
        action="store_true",
        help=(
            "Also use explicit contract directions already present in "
            "classified_feed.json."
        ),
    )

    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int)

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate directions that already have priors.",
    )

    args = parser.parse_args()

    directions = []

    for raw in args.direction:
        directions.append(parse_direction(raw))

    if args.discover:
        directions.extend(discover_directions())

    directions = sorted(set(directions))

    if not directions:
        raise SystemExit(
            "No directions selected. Use --direction and/or --discover."
        )

    priors = load_action_priors()

    if not args.force:
        directions = [
            pair
            for pair in directions
            if direction_key(*pair) not in priors
        ]

    if args.limit is not None:
        directions = directions[:args.limit]

    print(
        f"{len(directions)} directional action prior(s) selected."
    )

    if args.dry_run:
        print("[DRY RUN] No action_priors.json write.\n")
    else:
        if ACTION_PRIORS_PATH.exists():
            stamp = datetime.now(timezone.utc).strftime(
                "%Y%m%dT%H%M%S"
            )
            backup = ACTION_PRIORS_PATH.with_name(
                ACTION_PRIORS_PATH.name + f".bak.{stamp}"
            )
            shutil.copy2(ACTION_PRIORS_PATH, backup)
            print(f"Backup -> {backup}\n")

    successes = 0
    errors = []

    for i, (initiator, target) in enumerate(directions, 1):
        key = direction_key(initiator, target)

        try:
            probs, reasoning, confidence = classify_direction(
                initiator,
                target,
            )

            mode = max(probs, key=probs.get)

            print(f"{i:3}/{len(directions)} {key}")
            print(
                f"    mode: {mode} ({probs[mode]:.3f})"
            )
            print(f"    {format_distribution(probs)}")
            print(
                f"    confidence={confidence} | {reasoning}"
            )

            if not args.dry_run:
                priors[key] = {
                    "initiator": initiator,
                    "target": target,
                    "probabilities": {
                        action: round(probs[action], 6)
                        for action in ACTION_TYPES
                    },
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "version": 2,
                    "estimand": (
                        "primary_next_action_given_action_occurs"
                    ),
                }

            successes += 1

        except Exception as exc:
            errors.append((key, str(exc)))
            print(
                f"{i:3}/{len(directions)} {key}: "
                f"ERROR — {exc}"
            )

        time.sleep(0.25)

    if not args.dry_run:
        save_action_priors(priors)
        print(
            f"\nWrote {successes} directional structural prior(s) "
            f"to {ACTION_PRIORS_PATH}"
        )

    if errors:
        print(f"\n{len(errors)} error(s):")
        for key, error in errors:
            print(f"  {key}: {error}")


if __name__ == "__main__":
    main()
