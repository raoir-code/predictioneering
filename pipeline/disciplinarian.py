"""
disciplinarian.py
-----------------
Reads pipeline/live_feed.json, classifies each market into:
  CORE       — directly about interstate conflict onset/escalation, DAG has traction
  ADJACENT   — geopolitics-adjacent but model has weak traction
  NOISE      — unrelated to interstate conflict

Adds bucket, bucket_reason, dyad, relevant_nodes to each market row.
Outputs: pipeline/classified_feed.json

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

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL         = "claude-opus-4-6"

# DAG nodes and their theoretical meaning — fed directly into the system prompt
# so the disciplinarian knows what the model can/cannot speak to
DAG_NODES = {
    "WinProbability":     "military capability balance between parties (p)",
    "WarCosts":           "economic interdependence / trade costs of conflict (C)",
    "HardlineClaims":     "territorial disputes / hardline bargaining positions (x̄)",
    "CommitmentProblem":  "power shift risk / credibility of commitments (q)",
    "PreferenceAlignment":"preference distance / alignment of interests (S)",
    "Patience":           "leader time horizon / domestic political survival (δ̃)",
    "DemocraticPeace":    "regime type / democratic peace mechanism (α)",
}

SYSTEM_PROMPT = f"""You are a disciplinarian for a structural IR forecasting model based on the Fearon bargaining framework.

The model estimates structural parameters for the following causal nodes:
{json.dumps(DAG_NODES, indent=2)}

The model is designed to forecast INTERSTATE CONFLICT ONSET between two named state actors (a dyad). It is NOT designed for:
- Intrastate conflict (civil wars, insurgencies)
- Diplomatic events without conflict risk
- Elections, referenda, or leadership changes (unless directly tied to a dyad conflict question)
- Market/economic events
- Terrorism (non-state actors)

For each Polymarket question, classify it as exactly one of:
- CORE: The question is directly about whether interstate conflict will occur or escalate between a specific dyad. The model's DAG nodes are directly relevant.
- ADJACENT: The question is geopolitics-related and involves state actors but the model has only partial traction. Examples: ceasefire timing, peace deal questions, sanctions, specific military incidents that aren't full conflict onset.
- NOISE: Not about interstate conflict between state actors. Skip.

Respond ONLY with valid JSON in this exact format:
{{
  "bucket": "CORE" | "ADJACENT" | "NOISE",
  "reason": "one sentence explaining the classification",
  "dyad": "StateA-StateB" or null,
  "relevant_nodes": ["NodeName1", "NodeName2"]
}}

relevant_nodes must only contain node names from this list: {list(DAG_NODES.keys())}
For NOISE, return empty arrays and null dyad.
"""


def classify_market(question: str, event_title: str) -> dict:
    """Call Claude to classify one market. Returns the JSON dict."""
    
    user_msg = f"Event: {event_title}\nQuestion: {question}"
    
    payload = {
        "model": MODEL,
        "max_tokens": 200,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": user_msg}],
    }
    
    resp = requests.post(
        ANTHROPIC_API,
        headers={"Content-Type": "application/json", "x-api-key": __import__("os").environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        json=payload,
        timeout=30,
    )
    
    if resp.status_code != 200:
        raise RuntimeError(f"API error {resp.status_code}: {resp.text[:200]}")
    
    text = resp.json()["content"][0]["text"].strip()
    
    # Strip markdown fences if present
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    
    return json.loads(text)


def run_disciplinarian(dry_run: bool = False):
    base = os.path.dirname(__file__)
    in_path  = os.path.join(base, "live_feed.json")
    out_path = os.path.join(base, "classified_feed.json")
    
    with open(in_path) as f:
        markets = json.load(f)
    
    if dry_run:
        markets = markets[:5]
        print("[DRY RUN] Processing first 5 markets only\n")
    
    print(f"Classifying {len(markets)} markets...\n")
    
    counts = {"CORE": 0, "ADJACENT": 0, "NOISE": 0, "ERROR": 0}
    
    for i, m in enumerate(markets):
        question    = m.get("question", "")
        event_title = m.get("event_title", "")
        
        try:
            result = classify_market(question, event_title)
            m["bucket"]        = result.get("bucket", "NOISE")
            m["bucket_reason"] = result.get("reason", "")
            m["dyad"]          = result.get("dyad")
            m["relevant_nodes"] = result.get("relevant_nodes", [])
            counts[m["bucket"]] = counts.get(m["bucket"], 0) + 1
            
            bucket_icon = {"CORE": "✅", "ADJACENT": "🟡", "NOISE": "❌"}.get(m["bucket"], "?")
            print(f"  {i+1:3d}. {bucket_icon} [{m['bucket']:<8}] {question[:65]}")
            if m["dyad"]:
                print(f"        Dyad: {m['dyad']} | Nodes: {m['relevant_nodes']}")
        
        except Exception as e:
            m["bucket"]        = "ERROR"
            m["bucket_reason"] = str(e)
            counts["ERROR"] += 1
            print(f"  {i+1:3d}. ⚠️  ERROR: {question[:65]}")
            print(f"        {e}")
        
        # Polite rate limiting — Claude API is fast but let's not hammer it
        time.sleep(0.3)
    
    # Write output
    with open(out_path, "w") as f:
        json.dump(markets, f, indent=2, default=str)
    
    print(f"\n{'='*60}")
    print(f"Classification complete:")
    print(f"  ✅ CORE:     {counts['CORE']}")
    print(f"  🟡 ADJACENT: {counts['ADJACENT']}")
    print(f"  ❌ NOISE:    {counts['NOISE']}")
    if counts["ERROR"]:
        print(f"  ⚠️  ERRORS:   {counts['ERROR']}")
    print(f"\nSaved → {out_path}")
    
    # Show only the CORE markets as a quick preview
    core = [m for m in markets if m["bucket"] == "CORE"]
    if core:
        print(f"\nCORE markets ({len(core)}):")
        for m in core:
            price_str = f"{m['market_price']*100:.1f}%" if m["market_price"] else "?%"
            print(f"  [{price_str}] {m['question'][:70]}")
            print(f"   Dyad: {m['dyad']} | Ends: {m['end_date']}")


if __name__ == "__main__":
    dry_run = "--dry-run" in sys.argv
    run_disciplinarian(dry_run=dry_run)
