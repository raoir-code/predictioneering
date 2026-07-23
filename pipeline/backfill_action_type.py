"""
One-time backfill: generate `action_type` + `action_type_reasoning` for every
dyad already in dyad_configs.json that predates the field. Uses the same
geography/basing/doctrine reasoning discipline as generate_baseline() in
disciplinarian.py -- NOT a hardcoded table, a real Claude call per dyad.

Skips NON_BILATERAL dyads (disjunctive markets -- action_type doesn't apply
the same way there, revisit when the disjunctive module gets built).

Run: python3.11 pipeline/backfill_action_type.py
     python3.11 pipeline/backfill_action_type.py --dry-run   (prints only, no writes)
"""
import json
import os
import sys
import time
import requests
import shutil
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from dyad_registry import NON_BILATERAL

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-6"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "dyad_configs.json")

SYSTEM_PROMPT = """You are a military-geography analyst. Given a named dyad
(pair of states), classify the FASTEST physically plausible military action
this dyad's likely initiator could realistically execute, from this exact
7-value set: gray_zone_incident, missile_strike, raid, seizure_boarding,
airstrike, naval_blockade, ground_invasion.

This is a minimum-feasibility floor used to gate implausibly-fast market
resolutions -- it is NOT a prediction of what will happen or what is most
likely, only the fastest thing that is physically possible given real
constraints. Reason like a military planner, not a pundit:
- gray_zone_incident: near-zero lead time. Use when forces are ALREADY
  co-located in contested space and an incident needs no new deployment --
  coast guard ramming, water cannon use, cable-cutting, drone harassment.
  E.g. China-Philippines (vessels already present in disputed shoals).
- seizure_boarding: ~1 day lag. Intercepting/boarding a vessel or aircraft --
  faster than a raid on land territory, but needs a dispatched
  interceptor/boarding team, so not zero-lag like gray_zone_incident.
- missile_strike / airstrike / raid: fastest deployable kinetic strike
  options once forces are dispatched.
- naval_blockade / ground_invasion: sustained denial-of-access or
  territorial-control operations, longest lead times.
- Do the two states share a land border? If yes, a fast raid or limited
  ground action may be faster than any naval option -- but shared border
  alone does NOT justify ground_invasion. Allied or friction-free
  neighbors (e.g. Gulf Cooperation Council states) should NOT default to
  ground_invasion just because a border exists; that requires corroborating
  history of friction, disputed territory, or active hostility, not
  geography alone.
- Is the initiator's most relevant force separated by open ocean or a strait?
  If so, any kinetic action realistically requires naval/air assets first --
  do not default to ground_invasion just because that is the dramatic outcome.
- Does the initiator already have forward-deployed bases, carrier presence,
  or missile range covering the target? This can make missile_strike or
  airstrike plausible even across long distances.
- Does the target have a coastline that is economically or militarily
  chokepoint-relevant (e.g. a strait, a major port)? This can make
  naval_blockade the realistic fast option even without land access.
- Are opposing vessels/aircraft/patrols already routinely co-located in
  contested space (e.g. South China Sea shoals, disputed strait)? If so,
  gray_zone_incident is very likely the true fastest-plausible floor --
  do not overlook it in favor of a more dramatic category.
- If there is genuinely no plausible near-term conflict channel (no border,
  no basing, no history of friction, allied or non-adjacent states), still
  pick the least-implausible category rather than refusing -- default toward
  airstrike/missile_strike as the lowest-commitment placeholder, and say so
  plainly in the reasoning.
Bare-minimum discipline only -- categorical judgment using general knowledge
of geography and force posture, not a targeting-grade calculation.

Note: this field does NOT cover political/speech acts (e.g. a blockade
ANNOUNCEMENT vs. an actual blockade) or reactive engagements (e.g. air
defenses firing in response to an incoming strike). Classify only the
fastest INITIATED physical action.

Respond ONLY with valid JSON:
{"action_type": "one of the 7 values", "action_type_reasoning": "one sentence"}
"""


def classify_dyad(dyad_name):
    # Deliberately NOT passing label or crisis_context here. action_type is a
    # structural feasibility judgment (geography/basing/doctrine) and must stay
    # independent of current-events/likelihood framing -- crisis_context is
    # exactly that kind of signal, and feeding it in was confirmed (2026-07-23)
    # to corrupt the answer: truncation mid-sentence produced garbled/empty
    # output on US-Cuba, escalation-flavored language pulled US-Mexico toward
    # ground_invasion, and adversarial "vs." label framing broke JSON output
    # on Saudi Arabia-UAE. Raw dyad-name-only calls gave clean, correct answers
    # for all three. See work log 2026-07-23.
    payload = {
        "model": MODEL,
        "max_tokens": 300,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Classify this dyad: {dyad_name}."}],
    }
    resp = requests.post(
        ANTHROPIC_API,
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main():
    dry_run = "--dry-run" in sys.argv

    with open(CONFIG_PATH) as f:
        configs = json.load(f)

    targets = [
        k for k in configs
        if k not in NON_BILATERAL and "action_type" not in configs[k]
    ]

    print(f"{len(targets)} dyads need action_type backfill (of {len(configs)} total)\n")
    if dry_run:
        print("[DRY RUN] Will not write changes.\n")

    if not dry_run:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        bak_path = f"{CONFIG_PATH}.bak.{stamp}"
        shutil.copy2(CONFIG_PATH, bak_path)
        print(f"backed up -> {bak_path}\n")

    results = {}
    errors = []
    for i, dyad in enumerate(targets):
        entry = configs[dyad]
        try:
            result = classify_dyad(dyad)
            action_type = result.get("action_type")
            reasoning = result.get("action_type_reasoning", "")
            valid = {"gray_zone_incident", "missile_strike", "raid", "seizure_boarding",
                     "airstrike", "naval_blockade", "ground_invasion"}
            if action_type not in valid:
                errors.append(f"{dyad}: invalid action_type returned: {action_type!r}")
                print(f"  {i+1:2}/{len(targets)}. ⚠️  {dyad}: INVALID VALUE '{action_type}' -- skipped")
                continue

            results[dyad] = (action_type, reasoning)
            print(f"  {i+1:2}/{len(targets)}. {dyad:30} -> {action_type:16} ({reasoning[:70]})")

            if not dry_run:
                configs[dyad]["action_type"] = action_type
                configs[dyad]["action_type_reasoning"] = reasoning

        except Exception as e:
            errors.append(f"{dyad}: {e}")
            print(f"  {i+1:2}/{len(targets)}. ❌ {dyad}: ERROR -- {e}")

        time.sleep(0.3)

    if not dry_run:
        with open(CONFIG_PATH, "w") as f:
            json.dump(configs, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nWrote {len(results)} action_type values to {CONFIG_PATH}")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
