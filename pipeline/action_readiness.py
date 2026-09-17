#!/usr/bin/env python3
"""
Live directional action-readiness scorer.

Estimand contribution:
    evidence about WHICH action family is unusually ready right now,
    conditional on a qualifying physical action occurring.

This module NEVER estimates P(action occurs) and never alters the parent
conflict probability.

LLM role:
    semantic extraction only.

Deterministic role:
    convert ordinal evidence strength to additive log scores.

Interpretation:
    weak      -> odds x1.25
    moderate  -> odds x2
    strong    -> odds x4

These are explicit v1 heuristic evidence weights, not empirically calibrated
coefficients. Historical calibration is a later phase.
"""

import json
import math
import os
import time
from typing import Any

import requests

from pipeline.action_selector import ACTION_TYPES


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"

STRENGTH_TO_LOG_SCORE = {
    "weak": math.log(1.25),
    "moderate": math.log(2.0),
    "strong": math.log(4.0),
}

DIRECTIONS = {"up", "down"}


SYSTEM_PROMPT = """
You are the live ACTION-READINESS classifier for a geopolitical forecasting
engine.

You are NOT forecasting whether conflict or coercive action occurs.

The parent engine already owns that probability.

Your only task is:

Given that INITIATOR undertakes a qualifying physical coercive/military action
against TARGET, does THIS EVIDENCE PACKET contain new, concrete evidence that
one particular action family is more or less operationally ready than its
enduring structural baseline?

Use ONLY the supplied evidence packet.
Do not use outside knowledge.
Do not browse.
Do not infer unreported preparations.

ACTION FAMILIES

1. gray_zone_incident
   Limited physical coercion below overt combat: dangerous intercepts,
   ramming, water cannon, physical harassment, maritime militia/coast-guard
   coercion, limited physical sovereignty enforcement.

2. missile_strike
   Standalone ballistic, cruise-missile, rocket, or one-way attack-drone
   strike whose primary operational form is standoff fires.

3. raid
   Limited incursion or strike by troops/SOF whose objective is not sustained
   territorial control.

4. seizure_boarding
   Discrete boarding, interdiction, capture, or seizure of a vessel/platform.

5. airstrike
   Combat-aircraft strike whose primary operational form is aerial attack.

6. naval_blockade
   Sustained maritime quarantine/blockade/interdiction designed to deny
   traffic or access.

7. ground_invasion
   Ground/amphibious operation intended to enter, seize, hold, occupy, or
   control meaningful territory.

8. direct_engagement
   Deliberate overt kinetic combat between already-deployed opposing forces:
   air-to-air combat, SAM engagement against opposing military aircraft,
   ship-to-ship fire, border artillery/direct fire, DMZ firefight.

CRITICAL: READINESS, NOT GENERIC ESCALATION

A signal must contain concrete operational information specific to an action
family.

Valid examples:
- missile launchers dispersed into firing positions -> missile_strike
- strike aircraft loaded / tanker-SEAD package assembled -> airstrike
- landing ships loading troops and armor -> ground_invasion
- ships establishing an exclusion cordon around ports -> naval_blockade
- boarding teams/vessels ordered to intercept a named ship -> seizure_boarding
- SOF or limited assault units staging for a cross-border incursion -> raid
- opposing fighters/vessels/artillery maneuvering into direct weapons contact
  -> direct_engagement
- coast-guard/militia units positioning for physical harassment -> gray_zone

NOT readiness:
- generic hostility
- threats
- sanctions
- speeches
- "tensions are high"
- diplomatic breakdown by itself
- casualties by themselves
- generic mobilization with no action-specific operational form
- ordinary exercises
- routine patrols
- commentary/speculation by journalists
- historical examples
- capabilities that have existed for years

TARGET-RESPONSE GUARD

Classify INITIATOR'S action only.

If TARGET activates defenses, scrambles fighters, intercepts missiles, or
otherwise prepares to respond, that is NOT evidence for INITIATOR's
direct_engagement.

Example:
"Iran may launch missiles; Jordan activates air defenses."
This provides no Iran->Jordan direct_engagement readiness signal.

Likewise, proxy or militia activity is not INITIATOR's direct action unless
the evidence explicitly says INITIATOR's own forces are undertaking it.

COMPLETED-ACTION GUARD

A completed strike/raid/boarding/etc. by itself is not automatically a
readiness signal for another such action.

It may qualify only when the packet also reports concrete continuation
evidence such as:
- additional launchers entering firing positions
- another strike package preparing
- follow-on assault forces assembling
- blockade forces remaining deployed under continuing orders.

DIRECTION

"up":
new concrete evidence increases readiness for that action family.

"down":
new concrete evidence specifically reduces readiness for that family:
stand-down order, dispersal cancelled, assault force withdrawn, launch units
returned to garrison, blockade cordon dismantled, etc.

STRENGTH

weak:
real and action-specific, but preliminary or limited.

moderate:
clear operational preparation/readiness change.

strong:
immediate, costly, difficult-to-fake preparation strongly specific to that
action family.

DOUBLE-COUNTING

Return at most ONE signal per action family.
Merge duplicate reporting of the same underlying fact.
One evidence atom should normally map to ONE primary action family.
Do not smear "things are escalating" across multiple action types.

If there is no qualifying action-specific evidence, return an empty signals
array.

Return ONLY valid JSON:

{
  "signals": [
    {
      "action_type": "missile_strike",
      "direction": "up",
      "strength": "moderate",
      "evidence": "Concise concrete fact from the packet."
    }
  ],
  "summary": "One short sentence, or 'No action-specific readiness evidence.'"
}
"""


def zero_live_scores() -> dict:
    return {action: 0.0 for action in ACTION_TYPES}


def _extract_json(text: str) -> dict:
    text = text.strip()

    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
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


def signals_to_live_scores(signals: list[dict]) -> dict:
    """
    Convert semantic evidence labels into deterministic additive log scores.

    At most one signal per action is accepted. This prevents duplicated
    headlines or LLM repetition from multiplying the same fact.
    """
    scores = zero_live_scores()
    seen = set()

    if not isinstance(signals, list):
        raise ValueError("signals must be a list")

    for signal in signals:
        if not isinstance(signal, dict):
            raise ValueError("each signal must be an object")

        action = str(signal.get("action_type", "")).strip()
        direction = str(signal.get("direction", "")).strip().lower()
        strength = str(signal.get("strength", "")).strip().lower()

        if action not in ACTION_TYPES:
            raise ValueError(f"unknown action_type: {action!r}")
        if action in seen:
            raise ValueError(
                f"duplicate readiness signal for action: {action}"
            )
        if direction not in DIRECTIONS:
            raise ValueError(
                f"invalid readiness direction for {action}: {direction!r}"
            )
        if strength not in STRENGTH_TO_LOG_SCORE:
            raise ValueError(
                f"invalid readiness strength for {action}: {strength!r}"
            )

        magnitude = STRENGTH_TO_LOG_SCORE[strength]
        scores[action] = magnitude if direction == "up" else -magnitude
        seen.add(action)

    return scores


def score_action_readiness(
    initiator: str,
    target: str,
    articles: list[dict],
    *,
    max_retries: int = 3,
) -> dict[str, Any]:
    """
    Score action-specific live readiness from an already-fetched news packet.

    Returns:
      {
        "live_scores": {action: additive_log_score, ...},
        "signals": [...],
        "summary": "...",
      }
    """
    initiator = str(initiator).strip()
    target = str(target).strip()

    if not initiator or not target or initiator == target:
        raise ValueError("initiator and target must be distinct actors")

    if not articles:
        return {
            "live_scores": zero_live_scores(),
            "signals": [],
            "summary": "No evidence packet.",
        }

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")

    packet = []
    for article in articles:
        if not isinstance(article, dict):
            continue
        packet.append({
            "title": article.get("title", ""),
            "description": article.get("description", ""),
            "publishedAt": article.get("publishedAt", ""),
        })

    prompt = f"""
INITIATOR: {initiator}
TARGET: {target}

EVIDENCE PACKET:
{json.dumps(packet, indent=2, ensure_ascii=False)}

Identify only NEW action-specific readiness signals for:
{initiator} -> {target}

TARGET-NEXUS GUARD — MANDATORY:
A readiness signal is valid only when the evidence supports an action by
INITIATOR that is specifically directed against TARGET.

Concrete target nexus includes TARGET's territory, forces, military assets,
government vessels, ports, airspace, infrastructure, or another object that
the evidence explicitly identifies as belonging to or being defended by
TARGET.

Do NOT infer target nexus merely because:
- INITIATOR acts somewhere in the same region or theater;
- TARGET might be indirectly affected;
- TARGET is an ally, neighbor, host state, or coalition member;
- INITIATOR announces a general regional posture, maritime exclusion zone,
  Strait closure, patrol, mobilization, or warning;
- an action is directed against a third party;
- a proxy associated with INITIATOR acts against TARGET.

A general maritime exclusion zone or chokepoint restriction is NOT evidence
of naval_blockade readiness against this TARGET unless the evidence
specifically indicates that TARGET's ports, coast, shipping, vessels, or
access are objects of the restriction.

Proxy activity does not count as INITIATOR's own action merely because the
proxy is supported by INITIATOR.

If the TARGET nexus is ambiguous, emit NO signal.
"""

    payload = {
        "model": MODEL,
        "max_tokens": 900,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": prompt}],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(
                ANTHROPIC_API,
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()

            body = response.json()
            text = body["content"][0]["text"]
            parsed = _extract_json(text)

            signals = parsed.get("signals", [])
            live_scores = signals_to_live_scores(signals)

            return {
                "live_scores": live_scores,
                "signals": signals,
                "summary": str(parsed.get("summary", "")).strip(),
            }

        except Exception as exc:
            last_error = exc
            if attempt + 1 < max_retries:
                time.sleep(1.5 * (attempt + 1))

    raise last_error


if __name__ == "__main__":
    print("action_readiness.py: import this module from tests/predict.py")
