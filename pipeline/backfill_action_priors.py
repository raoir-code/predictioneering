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
    apply_feasibility_guards,
    normalize_feasibility_profile,
    apply_structural_prerequisites,
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

Use exactly these eight categories:

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

8. direct_engagement
   Deliberate overt kinetic combat between already-deployed opposing forces
   when the primary operation is not itself a raid, strike, blockade, seizure,
   or territorial invasion. Examples include standalone air-to-air combat,
   SAM engagements, ship-to-ship gunfire, cross-border artillery/direct fire,
   and border/DMZ firefights.

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

DIRECTIONAL ATTRIBUTION DISCIPLINE

You are classifying the INITIATOR'S own primary action against TARGET.

Do NOT assign probability to direct_engagement merely because TARGET would
defend itself, intercept incoming weapons, fire back, or otherwise respond.

Examples:
- Iran fires missiles at Jordan and Jordan shoots them down:
  Iran's action = missile_strike, NOT direct_engagement.
- China conducts an airstrike and defending fighters intercept the package:
  China's primary action remains airstrike.
- A standalone Chinese fighter deliberately attacks a Philippine fighter:
  China's action = direct_engagement.

Do NOT use attacks by proxies, militias, or partners as evidence for the
initiator's direct action unless the contract explicitly attributes those
actors' actions to INITIATOR. This structural prior is directional and literal.

DIRECT_ENGAGEMENT CONTACT TEST

Before assigning probability OR feasibility to direct_engagement, ask:

"Does INITIATOR have an ordinary pathway to deliberately fire on TARGET's
already-deployed forces as the primary action, without first performing some
other action family?"

Typical pathways include:
- opposing forces sharing a land frontier or DMZ;
- recurring close naval/coast-guard interaction;
- recurring military air contact/intercepts;
- both states having deployed military forces in the same operating theater.

If the only reason the forces would make contact is that TARGET intercepts
INITIATOR's missiles, drones, aircraft, or raid, that is NOT evidence for
direct_engagement. Classify the INITIATOR by the action it initiated.

Examples:
- Iran launches missiles at Jordan; Jordan fires SAMs:
  Iran -> Jordan = missile_strike.
- Israel intercepts a missile launched from Yemen:
  this provides NO evidence for Israel -> Yemen direct_engagement.
- Turkish fighter deliberately fires on a Greek fighter during an Aegean
  encounter:
  Turkey -> Greece = direct_engagement.
- North Korean troops deliberately fire across the DMZ:
  North Korea -> South Korea = direct_engagement.

If there is no ordinary force-contact pathway, direct_engagement should
normally be severely_constrained or unavailable rather than feasible/natural.

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

DIRECT-ENGAGEMENT STRUCTURAL FLAG

Also return:

"direct_engagement_contact_pathway": true|false

Set TRUE only when INITIATOR's own deployed forces have an ordinary structural
pathway to encounter TARGET's own deployed forces directly, such as:

- shared land frontier or DMZ;
- recurring fighter/interceptor contact;
- recurring naval/coast-guard contact;
- both actors maintaining forces in the same operating theater.

Set FALSE when direct contact would exist only because:
- TARGET intercepts INITIATOR's missiles, drones, aircraft, or raids;
- proxies or militias operate near TARGET;
- INITIATOR would require a major new deployment merely to create contact.

Examples:
Iran -> Jordan: false
Israel -> Yemen: false
Iran -> Bahrain: true
Turkey -> Greece: true
China -> Taiwan: true
North Korea -> South Korea: true

STRUCTURAL FEASIBILITY PROFILE

Separately classify every action family from stable structural facts only.
Do NOT use current headlines, today's crisis intensity, or market prices.

Use exactly one feasibility tier per action:

- unavailable:
  No ordinary operational pathway exists under the enduring geography,
  capability, access, or force relationship. It would require a fundamentally
  different force posture, theater, or major new capability.

- severely_constrained:
  Physically possible, but requires exceptional access, logistics, deployment,
  sea/air control, or political-military commitment not normally available.

- feasible:
  A credible operational option if action occurs, but not especially favored
  by the enduring structural relationship.

- natural:
  Particularly well matched to enduring geography, force posture, doctrine,
  recurring interaction, or demonstrated capability.

Feasibility is NOT probability.
Several action families can simultaneously be feasible or natural.
Do not downgrade one merely because another is more likely.

Return ONLY JSON:

{
  "gray_zone_incident": 0.10,
  "missile_strike": 0.30,
  "raid": 0.10,
  "seizure_boarding": 0.05,
  "airstrike": 0.23,
  "naval_blockade": 0.10,
  "ground_invasion": 0.08,
  "direct_engagement": 0.04,
  "feasibility": {
    "gray_zone_incident": "feasible",
    "missile_strike": "natural",
    "raid": "feasible",
    "seizure_boarding": "severely_constrained",
    "airstrike": "natural",
    "naval_blockade": "severely_constrained",
    "ground_invasion": "unavailable",
    "direct_engagement": "feasible"
  },
  "reasoning": "One concise sentence explaining the enduring structural pattern.",
  "confidence": "high|medium|low"
}

The eight probabilities should sum approximately to 1.
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
) -> tuple[dict, dict, dict, dict, str, str]:
    prompt = f"""
INITIATOR: {initiator}
TARGET: {target}

Conditional on {initiator} undertaking a qualifying physical coercive or
military action against {target}, estimate the eight-way structural
distribution over the PRIMARY action family of the next escalation episode.
"""

    body = {
        "model": MODEL,
        "max_tokens": 1000,
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

    raw_probs = normalize_distribution(raw)

    feasibility = normalize_feasibility_profile(
        parsed.get("feasibility", {})
    )

    contact_pathway = parsed.get(
        "direct_engagement_contact_pathway"
    )

    if not isinstance(contact_pathway, bool):
        raise ValueError(
            "direct_engagement_contact_pathway must be true or false"
        )

    structural_flags = {
        "direct_engagement_contact_pathway": contact_pathway,
    }

    guarded_probs = apply_feasibility_guards(
        raw_probs,
        feasibility,
    )

    guarded_probs = apply_structural_prerequisites(
        guarded_probs,
        structural_flags,
    )

    reasoning = str(parsed.get("reasoning", "")).strip()

    confidence = str(
        parsed.get("confidence", "medium")
    ).strip().lower()

    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    return (
        guarded_probs,
        raw_probs,
        feasibility,
        structural_flags,
        reasoning,
        confidence,
    )


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
            (
                probs,
                raw_probs,
                feasibility,
                structural_flags,
                reasoning,
                confidence,
            ) = classify_direction(
                initiator,
                target,
            )

            mode = max(probs, key=probs.get)

            print(f"{i:3}/{len(directions)} {key}")
            print(
                f"    mode: {mode} ({probs[mode]:.3f})"
            )
            print(
                f"    raw:     {format_distribution(raw_probs)}"
            )
            print(
                f"    guarded: {format_distribution(probs)}"
            )
            print(
                "    feasibility: "
                + ", ".join(
                    f"{action}={feasibility[action]}"
                    for action in ACTION_TYPES
                )
            )
            print(
                "    contact_pathway: "
                f"{structural_flags['direct_engagement_contact_pathway']}"
            )
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
                    "raw_probabilities": {
                        action: round(raw_probs[action], 6)
                        for action in ACTION_TYPES
                    },
                    "feasibility": {
                        action: feasibility[action]
                        for action in ACTION_TYPES
                    },
                    "structural_flags": structural_flags,
                    "reasoning": reasoning,
                    "confidence": confidence,
                    "version": 3,
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
