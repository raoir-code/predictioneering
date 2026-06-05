"""
predict.py
----------
RAO CORP — Live Fronttest Predictor

For each CORE market in docs/classified_feed.json:
  1. Pull GNews headlines for the dyad (last 7 days, t-3 cutoff)
  2. Ask Claude to score each DAG node (delta from baseline)
  3. Run predict() with alpha from alpha/conflict_onset.json
  4. Write our_prediction + prediction_at back to the JSON

Usage:
    export ANTHROPIC_API_KEY="sk-ant-..."
    export GNEWS_API_KEY="..."
    python pipeline/predict.py [--dry-run] [--dyad "China-Taiwan"]
"""

import os
import sys
import json
import math
import time
import argparse
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Tuple, Any

import requests

# ============================================================
# PATHS
# ============================================================
CLASSIFIED_FEED = "docs/classified_feed.json"
ALPHA_FILE      = "alpha/conflict_onset.json"

# ============================================================
# ENGINE CONFIG
# ============================================================
BASE_RATE_ANNUAL = 0.10
ANTHROPIC_URL    = "https://api.anthropic.com/v1/messages"
GNEWS_URL        = "https://gnews.io/api/v4/search"

# ============================================================
# NODE CONFIG — v3 names
# ============================================================
NODES = [
    "WinProbability",
    "WarCosts",
    "HardlineClaims",
    "CommitmentProblem",
    "PreferenceAlignment",
    "Patience",
    "DemocraticPeace",
]

TOGGLE_RANGES = {
    "WinProbability":      (-2.0, 2.0),
    "WarCosts":            (-2.0, 2.0),
    "HardlineClaims":      (0.0,  3.0),
    "CommitmentProblem":   (0.0,  2.0),
    "PreferenceAlignment": (-2.0, 2.0),
    "Patience":            (-2.0, 2.0),
    "DemocraticPeace":     (-2.0, 2.0),
}

MAX_WEEKLY_DELTA = {n: 0.5 for n in NODES}

# ============================================================
# DYAD CONFIGS
# ============================================================
DYAD_CONFIGS = {
    "China-Taiwan": {
        "label": "China and Taiwan",
        "baseline": {
            "WinProbability":      0.5,
            "WarCosts":           -1.0,
            "HardlineClaims":      2.0,
            "CommitmentProblem":   0.5,
            "PreferenceAlignment": -1.5,
            "Patience":           -0.5,
            "DemocraticPeace":     1.0,
        },
        "query": '"China" AND ("Taiwan" OR "PLA" OR "strait" OR "invasion" OR "blockade")',
    },
    "Russia-Ukraine": {
        "label": "Russia and Ukraine",
        "baseline": {
            "WinProbability":      0.0,
            "WarCosts":           -0.5,
            "HardlineClaims":      2.0,
            "CommitmentProblem":   1.5,
            "PreferenceAlignment": -2.0,
            "Patience":            0.0,
            "DemocraticPeace":     1.0,
        },
        "query": '"Russia" AND ("Ukraine" OR "Zelensky" OR "Putin" OR "Kyiv" OR "ceasefire")',
    },
    "US-Iran": {
        "label": "United States and Iran",
        "baseline": {
            "WinProbability":     -1.0,
            "WarCosts":            1.0,
            "HardlineClaims":      0.5,
            "CommitmentProblem":   1.0,
            "PreferenceAlignment": -1.5,
            "Patience":            0.0,
            "DemocraticPeace":     1.5,
        },
        "query": '"Iran" AND ("United States" OR US OR "American" OR Tehran OR "nuclear") NOT Venezuela',
    },
    "Israel-Iran": {
        "label": "Israel and Iran",
        "baseline": {
            "WinProbability":      0.5,
            "WarCosts":           -0.5,
            "HardlineClaims":      1.0,
            "CommitmentProblem":   1.0,
            "PreferenceAlignment": -2.0,
            "Patience":           -0.5,
            "DemocraticPeace":     1.0,
        },
        "query": '"Iran" AND ("Israel" OR "IDF" OR "nuclear" OR "strike" OR "airstrike")',
    },
    "North Korea-US": {
        "label": "North Korea and the United States",
        "baseline": {
            "WinProbability":     -2.0,
            "WarCosts":            0.5,
            "HardlineClaims":      1.0,
            "CommitmentProblem":   0.5,
            "PreferenceAlignment": -2.0,
            "Patience":           -1.0,
            "DemocraticPeace":     2.0,
        },
        "query": '"North Korea" AND ("United States" OR "Kim" OR "missile" OR "nuclear" OR "ICBM")',
    },
    "India-Pakistan": {
        "label": "India and Pakistan",
        "baseline": {
            "WinProbability":      0.5,
            "WarCosts":           -0.5,
            "HardlineClaims":      1.5,
            "CommitmentProblem":   0.5,
            "PreferenceAlignment": -1.5,
            "Patience":           -0.5,
            "DemocraticPeace":     0.5,
        },
        "query": '"India" AND ("Pakistan" OR "Kashmir" OR "LOC" OR "strike" OR "airstrike")',
    },
}

FALLBACK_BASELINE = {
    "WinProbability":      0.0,
    "WarCosts":            0.0,
    "HardlineClaims":      0.5,
    "CommitmentProblem":   0.5,
    "PreferenceAlignment": -1.0,
    "Patience":            0.0,
    "DemocraticPeace":     0.5,
}

# ============================================================
# NODE SYSTEM PROMPT + RUBRICS
# ============================================================
STRICT_NODE_SYSTEM = """
You are operating a conflict-forecasting toggle engine for a geopolitical prediction system.

Use ONLY the evidence packet provided. Do not use outside knowledge. Do not browse. Do not speculate.

Core interpretation:
- Each node is a latent structural condition derived from a formal bargaining model.
- Your task: detect whether a NEW discrete shock occurred this week that meaningfully changes this node.
- delta = 0 is the DEFAULT and should be the most common output.
- delta = +0.5 means one concrete event this week created a meaningful upward shock.
- delta = -0.5 means one concrete event this week created a meaningful downward shock.
- Continued hostility, repeated rhetoric, and ongoing tensions are NOT new shocks.
- If there is any doubt, return 0.

A nonzero move requires ALL of:
1. A specific dated event in the packet from this week.
2. That event directly matches the ontology of this node.
3. It represents a NEW change, not repetition or commentary.
4. Strong enough that a human forecaster would treat it as a real weekly shock.

Hierarchy: In a NORMAL week, ZERO nodes move. In an UNUSUAL week, ONE node moves.

Return valid JSON only:
{"delta": -0.5 | 0 | 0.5, "event": "One sentence naming the specific event, or 'none'."}
"""

NODE_RUBRICS = {
    "WinProbability":      "Did a NEW concrete operational balance shift occur: deployment of forces, mobilization, withdrawal, major arms delivery, or readiness change? Rhetoric does NOT count.",
    "WarCosts":            "Did a NEW concrete economic policy or enforcement action occur: sanctions imposed, embargo, blockade, seizure, tariff action, or restoration of trade ties?",
    "HardlineClaims":      "Did a NEW operational flashpoint occur: strike, seizure, border clash, naval confrontation, airspace incident, or direct sovereignty challenge?",
    "CommitmentProblem":   "Did a NEW event change the credibility or urgency of threats: public ultimatums, force deployments near the adversary, events that make today's deal harder to sustain tomorrow?",
    "PreferenceAlignment": "Did a NEW formal diplomatic alignment shift occur: signed agreement, formal rupture, diplomatic recognition, coalition change, or explicit policy reversal?",
    "Patience":            "Did a NEW domestic political instability event occur affecting leadership survival or time horizon: protests, coup signals, election shocks, elite rupture, or resignation risk?",
    "DemocraticPeace":     "Did a NEW major institutional rupture occur: coup, emergency rule, election cancellation, or constitutional suspension? This should almost ALWAYS be 0.",
}

NODE_GATES = {
    "WinProbability":      ["deploy", "carrier", "troops", "base", "mobiliz", "arms", "weapon"],
    "PreferenceAlignment": ["agreement", "rupture", "recognition", "accord", "reversal", "withdraw"],
    "DemocraticPeace":     ["coup", "emergency", "cancel", "suspend", "constitutional"],
}

# ============================================================
# HELPERS
# ============================================================
def clamp(name: str, value: float) -> float:
    lo, hi = TOGGLE_RANGES.get(name, (-3.0, 3.0))
    return max(lo, min(hi, float(value)))


def load_alpha() -> Dict[str, float]:
    with open(ALPHA_FILE) as f:
        data = json.load(f)
    alpha = dict(data["alpha"])
    alpha["Credibility_A"] = -0.30
    alpha["Credibility_B"] = -0.30
    return alpha


def predict_probability(toggles: Dict[str, float], days_remaining: int, alpha: Dict[str, float]) -> Dict[str, float]:
    log_odds_shift = sum(alpha.get(k, 0.0) * v for k, v in toggles.items())
    base_log_odds  = math.log(BASE_RATE_ANNUAL / (1 - BASE_RATE_ANNUAL))
    p_annual       = 1 / (1 + math.exp(-(base_log_odds + log_odds_shift)))
    lam            = -math.log(max(1e-12, 1 - p_annual))
    p_window       = 1 - math.exp(-lam * (max(1, days_remaining) / 365.0))
    return {
        "p_annual":        round(p_annual, 4),
        "p_window":        round(p_window, 4),
        "log_odds_shift":  round(log_odds_shift, 4),
    }


def days_until(end_date_str: str) -> int:
    try:
        end   = datetime.fromisoformat(end_date_str.replace("Z", "+00:00")).date()
        today = datetime.now(timezone.utc).date()
        return max(1, (end - today).days)
    except Exception:
        return 180


# ============================================================
# GNEWS
# ============================================================
def fetch_gnews(query: str) -> Tuple[List[Dict], Dict]:
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

    seen, out = set(), []
    for a in articles:
        key = (a.get("title", "").strip().lower(), a.get("publishedAt", ""))
        if key not in seen:
            seen.add(key)
            out.append(a)

    conflict_words = ["strike", "airstrike", "seized", "missile", "blockade", "raid", "coup", "deploy", "troops"]
    official_hints = ["whitehouse.gov", "state.gov", "defense.gov", "white house", "department of defense"]

    conflict_hits = sum(
        any(w in (a.get("title", "") + " " + a.get("description", "")).lower() for w in conflict_words)
        for a in out
    )
    official_hits = sum(
        any(h in ((a.get("source") or {}).get("url", "") + " " + (a.get("source") or {}).get("name", "")).lower()
            for h in official_hints)
        for a in out
    )

    features = {
        "article_volume": len(out),
        "conflict_hits":  int(conflict_hits),
        "official_hits":  int(official_hits),
    }

    packet = [
        {
            "publishedAt": a.get("publishedAt"),
            "title":       a.get("title"),
            "description": a.get("description"),
            "source_name": (a.get("source") or {}).get("name"),
            "url":         a.get("url"),
        }
        for a in out[:8]
    ]

    return packet, features


# ============================================================
# ANTHROPIC
# ============================================================
def _post(payload: Dict, max_retries: int = 5, base_sleep: float = 2.0) -> Dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")

    headers = {
        "x-api-key":         api_key,
        "anthropic-version": "2023-06-01",
        "content-type":      "application/json",
    }

    last_err = None
    for attempt in range(max_retries):
        try:
            resp = requests.post(ANTHROPIC_URL, headers=headers, json=payload, timeout=90)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            last_err = e
            if getattr(e.response, "status_code", None) == 529:
                time.sleep(base_sleep * (2 ** attempt))
                continue
            raise
        except Exception as e:
            last_err = e
            time.sleep(base_sleep * (2 ** attempt))

    raise last_err


def _extract_text(data: Dict) -> str:
    return "".join(
        b.get("text", "") for b in data.get("content", []) if b.get("type") == "text"
    ).strip()


def gate_delta(node: str, delta: float, event_text: str) -> float:
    if node not in NODE_GATES:
        return delta
    if not any(w in (event_text or "").lower() for w in NODE_GATES[node]):
        return 0.0
    return delta


def score_node(node: str, dyad_label: str, packet: List[Dict], features: Dict) -> Dict:
    today      = datetime.now(timezone.utc).strftime("%B %d, %Y")
    week_start = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%B %d, %Y")

    user_prompt = f"""
Dyad: {dyad_label}
Node: {node}
Week: {week_start} to {today}

Node rubric:
{NODE_RUBRICS[node]}

Objective weekly news features:
{json.dumps(features, indent=2)}

Evidence packet:
{json.dumps(packet, indent=2)}

Return:
{{"delta": -0.5|0|0.5, "event": "..."}}
"""

    payload = {
        "model":    "claude-sonnet-4-20250514",
        "max_tokens": 220,
        "system":   STRICT_NODE_SYSTEM,
        "messages": [{"role": "user", "content": user_prompt}],
    }

    data = _post(payload)
    text = _extract_text(data)

    try:
        s   = text.find("{")
        e   = text.rfind("}") + 1
        raw = json.loads(text[s:e])
        raw_delta = float(raw.get("delta", 0))
        event     = str(raw.get("event", "none")).strip()
        gated     = gate_delta(node, raw_delta, event)
        return {"delta": gated, "event": event}
    except Exception:
        return {"delta": 0.0, "event": "parse_error"}


def score_all_nodes(dyad_label: str, packet: List[Dict], features: Dict) -> Tuple[Dict[str, float], Dict[str, str]]:
    deltas   = {}
    evidence = {}

    for node in NODES:
        result = score_node(node, dyad_label, packet, features)
        if abs(result["delta"]) > 1e-9:
            deltas[node] = result["delta"]
        evidence[node] = result["event"]
        time.sleep(0.3)

    return deltas, evidence


# ============================================================
# MAIN
# ============================================================
def run(dry_run: bool = False, filter_dyad: str = None):
    alpha = load_alpha()
    print(f"[predict.py] Alpha loaded. {len(alpha)} nodes.")

    with open(CLASSIFIED_FEED) as f:
        markets = json.load(f)

    core = [m for m in markets if m.get("bucket") == "CORE" and m.get("our_prediction") is None]
    if filter_dyad:
        core = [m for m in core if filter_dyad.lower() in (m.get("dyad") or "").lower()]

    print(f"[predict.py] {len(core)} CORE markets without predictions.")

    if dry_run:
        core = core[:3]
        print(f"[predict.py] DRY RUN — capped at 3 markets.")

    dyad_groups: Dict[str, List] = {}
    for m in core:
        dyad = m.get("dyad") or "Unknown"
        dyad_groups.setdefault(dyad, []).append(m)

    for dyad, dyad_markets in dyad_groups.items():
        print(f"\n{'='*60}")
        print(f"DYAD: {dyad} ({len(dyad_markets)} markets)")
        print(f"{'='*60}")

        config = DYAD_CONFIGS.get(dyad)
        if config is None:
            for key in DYAD_CONFIGS:
                if any(part.lower() in dyad.lower() for part in key.split("-")):
                    config = DYAD_CONFIGS[key]
                    print(f"  [warn] No exact config for '{dyad}', using '{key}'")
                    break

        if config is None:
            print(f"  [warn] No config for '{dyad}', using fallback baseline.")
            config = {
                "label":    dyad,
                "baseline": FALLBACK_BASELINE.copy(),
                "query":    f'"{dyad}"',
            }

        label    = config["label"]
        baseline = config["baseline"].copy()
        query    = config["query"]

        print(f"  Fetching GNews for: {label}...")
        try:
            packet, features = fetch_gnews(query)
            print(f"  Articles: {features['article_volume']} | conflict_hits: {features['conflict_hits']} | official_hits: {features['official_hits']}")
        except Exception as ex:
            print(f"  [error] GNews failed: {ex}")
            packet, features = [], {"article_volume": 0, "conflict_hits": 0, "official_hits": 0}

        print(f"  Scoring {len(NODES)} nodes via Claude...")
        deltas, evidence = score_all_nodes(label, packet, features)
        print(f"  Moves this week: {list(deltas.keys()) or ['none']}")

        toggles = baseline.copy()
        for node, delta in deltas.items():
            if node in toggles:
                toggles[node] = clamp(node, toggles[node] + delta)

        print(f"  Toggles: {json.dumps({k: round(v,3) for k,v in toggles.items()})}")

        now_utc = datetime.now(timezone.utc).isoformat()

        for m in dyad_markets:
            days_rem = days_until(m.get("end_date", ""))
            result   = predict_probability(toggles, days_rem, alpha)

            m["our_prediction"]  = result["p_window"]
            m["prediction_at"]   = now_utc
            m["_toggles"]        = toggles
            m["_deltas"]         = deltas
            m["_evidence"]       = evidence
            m["_log_odds_shift"] = result["log_odds_shift"]

            edge = round((result["p_window"] - (m.get("market_price") or 0)) * 100, 1)
            print(f"  ✓ {m['question'][:70]}")
            print(f"    engine={result['p_window']:.3f}  market={m.get('market_price',0):.3f}  edge={edge:+.1f}pp  days={days_rem}")

    if dry_run:
        print("\n[DRY RUN] Not writing to disk.")
        return

    with open(CLASSIFIED_FEED, "w") as f:
        json.dump(markets, f, indent=2)

    print(f"\n[predict.py] Written to {CLASSIFIED_FEED}")
    print("Now run: git add docs/classified_feed.json && git commit -m 'Predictions: first fronttest batch' && git push")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dyad", type=str, default=None)
    args = parser.parse_args()
    run(dry_run=args.dry_run, filter_dyad=args.dyad)
