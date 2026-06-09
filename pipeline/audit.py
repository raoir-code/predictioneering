"""
audit.py
--------
RAO CORP -- Mechanism Gap Auditor

For each target dyad:
  1. Pull GNews headlines (same call as predict.py)
  2. Ask Claude: what mechanisms are showing up in these headlines
     that the 7 DAG nodes have NO vocabulary for?
  3. Write gap report to pipeline/audit_report.json
  4. Print human-readable summary

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    export GNEWS_API_KEY="..."
    python pipeline/audit.py
    python pipeline/audit.py --dyad "China-Taiwan"
"""

import os
import sys
import json
import time
import requests
from datetime import datetime, timezone, timedelta

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
GNEWS_URL     = "https://gnews.io/api/v4/search"
MODEL         = "claude-opus-4-6"

DYAD_CONFIGS_PATH  = os.path.join(os.path.dirname(__file__), "dyad_configs.json")
AUDIT_REPORT_PATH  = os.path.join(os.path.dirname(__file__), "audit_report.json")

# Target dyads for audit -- the ones that matter most
TARGET_DYADS = [
    "US-Iran",
    "China-Taiwan",
    "NATO-Russia",
    "India-Pakistan",
    "US-Venezuela",
    "NorthKorea-SouthKorea",
    "China-Philippines",
    "Israel-Iran",
]

DAG_DESCRIPTION = """The current forecasting model has exactly 7 causal nodes derived from the Fearon bargaining framework:

1. WinProbability -- military capability balance between the two states (p). Captures: troop deployments, arms deliveries, military readiness shifts, capability ratios.

2. WarCosts -- economic interdependence and trade costs of conflict (C). Captures: sanctions, trade volumes, economic ties, embargoes, tariff actions.

3. HardlineClaims -- active territorial disputes and hardline bargaining positions (x-bar). Captures: border clashes, airspace violations, naval confrontations, sovereignty challenges, direct strikes.

4. CommitmentProblem -- power shift risk making deals hard to sustain (q). Captures: ultimatums, force deployments near adversary, events that make today's deal harder to sustain tomorrow.

5. PreferenceAlignment -- alignment of interests between the two states (S). Captures: formal diplomatic agreements, ruptures, coalition changes, policy reversals.

6. Patience -- leader time horizon and domestic political stability (delta). Captures: protests, leadership instability, election shocks, elite rupture signals.

7. DemocraticPeace -- regime type effect (alpha). Captures: coups, emergency rule, constitutional suspensions, major institutional ruptures.

IMPORTANT: The model is purely BILATERAL. It only models the two named states. It has NO nodes for:
- Third party actors (patrons, allies, mediators, international organizations)
- Nuclear deterrence or escalation constraints
- International law or institutional constraints (UN, ICC, IAEA)
- Economic sanctions by third parties
- Public opinion or media effects
- Historical memory or past conflict legacy
- Geographic or logistical constraints"""

AUDIT_SYSTEM_PROMPT = """You are an expert IR theorist auditing a conflict forecasting model for mechanism gaps.

You will be given:
1. A description of the model's current 7 causal nodes and what they capture
2. A packet of recent news headlines for a specific dyad

Your task: identify mechanisms that are CLEARLY PRESENT in the headlines but that NONE of the 7 nodes can capture. These are the model's blind spots.

Rules:
- Only flag mechanisms that actually appear in the provided headlines -- cite the specific headline
- Do not flag things the existing nodes already cover
- Be specific about the theoretical mechanism, not just the topic
- Rank gaps by how often they appear across the headlines (frequency = importance)
- Suggest a candidate node name and theoretical grounding for each gap
- Maximum 4 gaps per dyad -- only the most important ones

Respond ONLY with valid JSON:
{
  "gaps": [
    {
      "mechanism": "short name for the missing mechanism",
      "description": "one sentence theoretical description",
      "evidence": "which headline(s) triggered this, quoted briefly",
      "frequency": "how many of the headlines touch this (e.g. 4/10)",
      "candidate_node": "suggested DAG node name",
      "theoretical_grounding": "which IR theory or study tradition would identify this"
    }
  ],
  "summary": "two sentence overall assessment of the model's blind spots for this dyad"
}"""


def fetch_gnews(query):
    api_key = os.environ.get("GNEWS_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing GNEWS_API_KEY")

    now    = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=3)
    start  = cutoff - timedelta(days=7)

    params = {
        "q":       query,
        "from":    start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "to":      cutoff.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "lang":    "en",
        "country": "us",
        "max":     10,
        "sortby":  "publishedAt",
        "apikey":  api_key,
    }

    resp = requests.get(GNEWS_URL, params=params, timeout=60)
    resp.raise_for_status()
    articles = resp.json().get("articles", [])

    return [
        {
            "publishedAt": a.get("publishedAt"),
            "title":       a.get("title"),
            "description": a.get("description"),
            "source_name": (a.get("source") or {}).get("name"),
        }
        for a in articles[:10]
    ]


def audit_dyad(dyad, config):
    label  = config.get("label", dyad)
    query  = config.get("query", '"' + dyad + '"')

    print("  Fetching headlines for: " + label + "...")
    try:
        packet = fetch_gnews(query)
        print("  " + str(len(packet)) + " articles retrieved.")
    except Exception as e:
        print("  GNews failed: " + str(e))
        return None

    if not packet:
        print("  No articles -- skipping.")
        return None

    user_prompt = """Dyad: """ + label + """

Model description:
""" + DAG_DESCRIPTION + """

Recent headlines (last 7 days):
""" + json.dumps(packet, indent=2) + """

Identify mechanism gaps -- things present in these headlines that the model cannot capture."""

    payload = {
        "model":      MODEL,
        "max_tokens": 1500,
        "system":     AUDIT_SYSTEM_PROMPT,
        "messages":   [{"role": "user", "content": user_prompt}],
    }

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    resp = requests.post(
        ANTHROPIC_URL,
        headers={
            "Content-Type":      "application/json",
            "x-api-key":         api_key,
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=60,
    )

    if resp.status_code != 200:
        print("  Claude error: " + str(resp.status_code))
        return None

    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]

    try:
        # Strip markdown fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        # Find outermost JSON object
        s = text.find("{")
        e = text.rfind("}") + 1
        return json.loads(text[s:e])
    except Exception as ex:
        print("  Parse error: " + str(ex))
        print("  Raw response: " + text[:200])
        return None


def run(filter_dyad=None):
    with open(DYAD_CONFIGS_PATH) as f:
        dyad_configs = json.load(f)

    targets = TARGET_DYADS
    if filter_dyad:
        targets = [d for d in targets if filter_dyad.lower() in d.lower()]

    print("MECHANISM GAP AUDIT")
    print("=" * 60)
    print("Auditing " + str(len(targets)) + " dyads...\n")

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "dyads": {}
    }

    for dyad in targets:
        print("\n" + "=" * 60)
        print("DYAD: " + dyad)
        print("=" * 60)

        config = dyad_configs.get(dyad)
        if config is None:
            print("  No config found -- skipping.")
            continue

        result = audit_dyad(dyad, config)
        time.sleep(1.0)

        if result is None:
            continue

        report["dyads"][dyad] = result

        gaps = result.get("gaps", [])
        summary = result.get("summary", "")

        print("\n  GAPS FOUND: " + str(len(gaps)))
        for i, gap in enumerate(gaps):
            print("\n  [" + str(i+1) + "] " + gap.get("mechanism", "?").upper())
            print("      Description: " + gap.get("description", ""))
            print("      Evidence:    " + gap.get("evidence", ""))
            print("      Frequency:   " + gap.get("frequency", ""))
            print("      Node name:   " + gap.get("candidate_node", ""))
            print("      Theory:      " + gap.get("theoretical_grounding", ""))

        print("\n  SUMMARY: " + summary)

    with open(AUDIT_REPORT_PATH, "w") as f:
        json.dump(report, f, indent=2)

    print("\n" + "=" * 60)
    print("Audit complete. Report saved to pipeline/audit_report.json")

    # Cross-dyad summary -- which gaps appear most often
    gap_counts = {}
    for dyad, result in report["dyads"].items():
        for gap in result.get("gaps", []):
            node = gap.get("candidate_node", "unknown")
            gap_counts[node] = gap_counts.get(node, 0) + 1

    if gap_counts:
        print("\nMOST COMMON MISSING MECHANISMS (across all dyads):")
        for node, count in sorted(gap_counts.items(), key=lambda x: -x[1]):
            print("  " + str(count) + "x  " + node)


if __name__ == "__main__":
    filter_dyad = None
    for i, arg in enumerate(sys.argv[1:]):
        if arg == "--dyad" and i + 1 < len(sys.argv) - 1:
            filter_dyad = sys.argv[i + 2]
    run(filter_dyad=filter_dyad)
