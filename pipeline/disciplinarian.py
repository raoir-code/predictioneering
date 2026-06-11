"""
disciplinarian.py
-----------------
Reads pipeline/live_feed.json, classifies each market into:
  CORE       — directly about interstate conflict onset/escalation, DAG has traction
  ADJACENT   — geopolitics-adjacent but model has weak traction
  NOISE      — unrelated to interstate conflict

Also auto-generates baselines for unknown dyads and saves to dyad_configs.json.

Run: python pipeline/disciplinarian.py
     python pipeline/disciplinarian.py --dry-run   (first 5 only, for testing)
"""

import json
import os
import sys
import time
import requests
from datetime import datetime, timezone

# ── Config ──────────────────────────────────────────────────────────────────

ANTHROPIC_API     = "https://api.anthropic.com/v1/messages"
MODEL             = "claude-opus-4-6"
DYAD_CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "dyad_configs.json")

NODES = [
    "WinProbability", "WarCosts", "HardlineClaims",
    "CommitmentProblem", "PreferenceAlignment", "Patience", "DemocraticPeace",
]

# DAG nodes and their theoretical meaning
DAG_NODES = {
    "WinProbability":      "military capability balance between parties (p)",
    "WarCosts":            "economic interdependence / trade costs of conflict (C)",
    "HardlineClaims":      "territorial disputes / hardline bargaining positions (x-bar)",
    "CommitmentProblem":   "power shift risk / credibility of commitments (q)",
    "PreferenceAlignment": "preference distance / alignment of interests (S)",
    "Patience":            "leader time horizon / domestic political survival (delta)",
    "DemocraticPeace":     "regime type / democratic peace mechanism (alpha)",
}

# ── Prompts ──────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are a disciplinarian for a structural IR forecasting model based on the Fearon bargaining framework.

The model estimates structural parameters for the following causal nodes:
- WinProbability: military capability balance between parties (p)
- WarCosts: economic interdependence / trade costs of conflict (C)
- HardlineClaims: territorial disputes / hardline bargaining positions (x-bar)
- CommitmentProblem: power shift risk / credibility of commitments (q)
- PreferenceAlignment: preference distance / alignment of interests (S)
- Patience: leader time horizon / domestic political survival (delta)
- DemocraticPeace: regime type / democratic peace mechanism (alpha)

The model is designed to forecast INTERSTATE CONFLICT ONSET between two named state actors (a dyad). It is NOT designed for:
- Intrastate conflict (civil wars, insurgencies)
- Diplomatic events without conflict risk
- Elections, referenda, or leadership changes (unless directly tied to a dyad conflict question)
- Market/economic events
- Terrorism (non-state actors)

For each Polymarket question, classify it as exactly one of:
- CORE: The question is directly about whether interstate conflict will occur or escalate between a specific dyad. The model DAG nodes are directly relevant.
- ADJACENT: The question is geopolitics-related and involves state actors but the model has only partial traction. Examples: ceasefire timing, peace deal questions, sanctions, specific military incidents that are not full conflict onset, territorial advance or battlefield progress questions (will X capture city Y, will X control territory Z by date, will X reach location Y).
- NOISE: Not about interstate conflict between state actors. Skip.

Respond ONLY with valid JSON in this exact format:
{
  "bucket": "CORE or ADJACENT or NOISE",
  "reason": "one sentence explaining the classification",
  "dyad": "StateA-StateB or null",
  "relevant_nodes": ["NodeName1", "NodeName2"]
}

relevant_nodes must only contain node names from this list: WinProbability, WarCosts, HardlineClaims, CommitmentProblem, PreferenceAlignment, Patience, DemocraticPeace
For NOISE, return empty arrays and null dyad.

Dyad naming rules: Always use the shortest standard English name. Use "US" not "USA". Use "North Korea" not "DPRK". Format is always "CountryA-CountryB" with the more powerful or initiating state first. Never reverse an established dyad direction."""

BASELINE_SYSTEM_PROMPT = """You are an expert in international relations and the Fearon bargaining model of conflict.

Given a dyad (pair of states), set theoretically defensible baseline toggle values for the following 10 nodes. These represent STRUCTURAL CONDITIONS for this dyad -- slow-moving features that do not change week to week.

Nodes and their meaning:
- WinProbability: military capability balance. Positive = challenger has advantage. Range: -2.0 to 2.0.
- WarCosts: economic interdependence / trade costs of conflict. Negative = high costs (peace-inducing). Range: -2.0 to 2.0.
- PatronDeterrence: strength of external patron commitment to the defender. Higher = stronger patron guarantee (e.g. US commitment to Taiwan). Range: 0.0 to 3.0.
- NuclearDeterrence: nuclear weapons presence creating mutual destruction constraint. Higher = stronger nuclear deterrence. Range: 0.0 to 3.0.
- CommitmentProblem: power shift risk making deals hard to sustain. Higher = more commitment problems. Range: 0.0 to 2.0.
- Patience: leader time horizon / domestic stability. Negative = impatient/unstable leaders. Range: -2.0 to 2.0.
- DemocraticPeace: regime type / credibility effect. Positive = one or both autocratic. Range: -2.0 to 2.0.
- PreferenceAlignment: alignment of interests. Negative = opposed interests (conflict-inducing). Range: -2.0 to 2.0.
- HardlineClaims: active territorial disputes / hardline bargaining positions. Higher = more contested. Range: 0.0 to 3.0.
- AudienceCosts: domestic political pressure making backing down costly. Higher = more locked in. Range: 0.0 to 3.0.

Rules:
- Use your knowledge of IR history, territorial disputes, regime types, and military balance.
- Be theoretically conservative -- only set extreme values (2.0+) for genuinely extreme cases.
- PatronDeterrence should be high (2.0+) only where a major power has an explicit defense commitment (e.g. US-Taiwan, US-South Korea).
- NuclearDeterrence should be high only where both sides have nuclear weapons or one side has them and they are relevant to the dyad.
- Also generate a GNews search query (boolean, English) that would pull relevant headlines for this dyad.

Respond ONLY with valid JSON in this exact format:
{
  "label": "human readable dyad name",
  "baseline": {
    "WinProbability": 0.0,
    "WarCosts": 0.0,
    "PatronDeterrence": 0.0,
    "NuclearDeterrence": 0.0,
    "CommitmentProblem": 0.0,
    "Patience": 0.0,
    "DemocraticPeace": 0.0,
    "PreferenceAlignment": 0.0,
    "HardlineClaims": 0.0,
    "AudienceCosts": 0.0
  },
  "query": "boolean GNews search query string",
  "reasoning": "two sentences explaining the key baseline choices"
}"""


# ── Dyad config helpers ───────────────────────────────────────────────────────

def load_dyad_configs():
    if os.path.exists(DYAD_CONFIGS_PATH):
        with open(DYAD_CONFIGS_PATH) as f:
            return json.load(f)
    return {}


def save_dyad_configs(configs):
    with open(DYAD_CONFIGS_PATH, "w") as f:
        json.dump(configs, f, indent=2)


def generate_baseline(dyad):
    payload = {
        "model": MODEL,
        "max_tokens": 400,
        "system": BASELINE_SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": "Generate a baseline for this dyad: " + dyad}],
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

    if resp.status_code != 200:
        raise RuntimeError("API error " + str(resp.status_code) + ": " + resp.text[:200])

    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    result = json.loads(text)
    result["baseline_source"] = "auto"
    return result


# ── Classification ────────────────────────────────────────────────────────────

def classify_market(question, event_title):
    user_msg = "Event: " + event_title + "\nQuestion: " + question

    payload = {
        "model": MODEL,
        "max_tokens": 200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
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

    if resp.status_code != 200:
        raise RuntimeError("API error " + str(resp.status_code) + ": " + resp.text[:200])

    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    return json.loads(text)


# ── Main ──────────────────────────────────────────────────────────────────────

def run_disciplinarian(dry_run=False):
    base     = os.path.dirname(__file__)
    in_path  = os.path.join(base, "live_feed.json")
    out_path = os.path.join(base, "classified_feed.json")

    with open(in_path) as f:
        markets = json.load(f)

    if dry_run:
        markets = markets[:5]
        print("[DRY RUN] Processing first 5 markets only\n")

    print("Classifying " + str(len(markets)) + " markets...\n")

    counts = {"CORE": 0, "ADJACENT": 0, "NOISE": 0, "ERROR": 0}
    dyad_configs = load_dyad_configs()
    new_configs_added = 0

    for i, m in enumerate(markets):
        question    = m.get("question", "")
        event_title = m.get("event_title", "")

        try:
            result = classify_market(question, event_title)
            m["bucket"]         = result.get("bucket", "NOISE")
            m["bucket_reason"]  = result.get("reason", "")
            m["dyad"]           = result.get("dyad")
            m["relevant_nodes"] = result.get("relevant_nodes", [])
            counts[m["bucket"]] = counts.get(m["bucket"], 0) + 1

            bucket_icon = {"CORE": "✅", "ADJACENT": "🟡", "NOISE": "❌"}.get(m["bucket"], "?")
            print("  " + str(i+1).rjust(3) + ". " + bucket_icon + " [" + m["bucket"].ljust(8) + "] " + question[:65])
            if m["dyad"]:
                print("        Dyad: " + str(m["dyad"]) + " | Nodes: " + str(m["relevant_nodes"]))

            # Auto-generate baseline for unknown dyads
            dyad_key = result.get("dyad")
            if dyad_key and dyad_key not in dyad_configs:
                try:
                    print("        [new dyad] Generating baseline for '" + dyad_key + "'...")
                    new_config = generate_baseline(dyad_key)
                    dyad_configs[dyad_key] = new_config
                    new_configs_added += 1
                    print("        [new dyad] saved (auto) -- " + new_config.get("reasoning", ""))
                except Exception as be:
                    print("        [new dyad] baseline generation failed: " + str(be))

        except Exception as e:
            m["bucket"]        = "ERROR"
            m["bucket_reason"] = str(e)
            counts["ERROR"] += 1
            print("  " + str(i+1).rjust(3) + ". ERROR: " + question[:65])
            print("        " + str(e))

        time.sleep(0.3)

    with open(out_path, "w") as f:
        json.dump(markets, f, indent=2, default=str)

    if new_configs_added > 0:
        save_dyad_configs(dyad_configs)
        print("\n  [dyad_configs] " + str(new_configs_added) + " new baseline(s) saved to dyad_configs.json")

    print("\n" + "="*60)
    print("Classification complete:")
    print("  CORE:     " + str(counts["CORE"]))
    print("  ADJACENT: " + str(counts["ADJACENT"]))
    print("  NOISE:    " + str(counts["NOISE"]))
    if counts["ERROR"]:
        print("  ERRORS:   " + str(counts["ERROR"]))
    print("\nSaved -> " + out_path)

    core = [m for m in markets if m["bucket"] == "CORE"]
    if core:
        print("\nCORE markets (" + str(len(core)) + "):")
        for m in core:
            price_str = (str(round(m["market_price"]*100, 1)) + "%") if m["market_price"] else "?%"
            print("  [" + price_str + "] " + m["question"][:70])
            print("   Dyad: " + str(m["dyad"]) + " | Ends: " + str(m["end_date"]))


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_disciplinarian(dry_run=dry_run)
