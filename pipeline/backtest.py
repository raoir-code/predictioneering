#!/usr/bin/env python3.11
"""
backtest.py — Mach 2 Calibration Backtest
==========================================
Pulls historical Polymarket price data + resolutions, runs Mach 2 engine
at multiple snapshots per market, compares Brier scores vs. market.

Usage:
    python3.11 pipeline/backtest.py               # full run
    python3.11 pipeline/backtest.py --dry-run     # first 2 markets only
    python3.11 pipeline/backtest.py --leakage     # contamination check only
"""

import os, sys, json, time, argparse, math
from datetime import datetime, timedelta, date
from pathlib import Path
import requests

# ── Paths ─────────────────────────────────────────────────────────────
ROOT       = Path(__file__).parent.parent
CACHE_DIR  = ROOT / "cache"
GNEWS_CACHE = CACHE_DIR / "gnews"
POLY_CACHE  = CACHE_DIR / "polymarket"
RESULTS_OUT = ROOT / "pipeline" / "backtest_results.json"

for d in [GNEWS_CACHE, POLY_CACHE]:
    d.mkdir(parents=True, exist_ok=True)

# ── API keys ──────────────────────────────────────────────────────────
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]
GNEWS_KEY     = os.environ["GNEWS_API_KEY"]

# ── Load alpha directly from real engine ─────────────────────────────
import sys as _sys
_sys.path.insert(0, str(ROOT))
from pipeline.load_alpha import load_alpha as _load_alpha
ALPHA = _load_alpha()
# Convenience remaps for the predict function
ALPHA["WinProbability"] = ALPHA.get("WinProbability_prior", 0.25)
ALPHA["PatronDeterrence_w"] = ALPHA.get("PatronDeterrence_deterrence", -0.80)
ALPHA["NuclearDeterrence_expert"] = ALPHA.get("NuclearDeterrence", -0.35)

BASE_RATE_ANNUAL = 0.06  # Polymarket-conditional (June 11 evening fix)

# ── The 10-market backtest slate ──────────────────────────────────────
# Fields: slug, dyad, resolution (1/0/None=live), end_date, notes
SLATE = [
    # ── Resolved No (true negatives) ──────────────────────────────
    {
        "slug":       "will-china-invade-taiwan-in-2024",
        "dyad":       "China-Taiwan",
        "resolution": 0,
        "end_date":   "2024-12-31",
        "label":      "China invades Taiwan 2024",
    },
    {
        "slug":       "will-china-invade-taiwan-in-2025",
        "dyad":       "China-Taiwan",      # stress test — model should output ~0
        "resolution": 0,
        "end_date":   "2025-12-31",
        "label":      "China invades Taiwan 2025",
    },
    {
        "slug":       "trump-wins-ends-ukraine-war-in-90-days",
        "dyad":       "Russia-Ukraine",
        "resolution": 0,
        "end_date":   "2025-04-19",
        "label":      "Trump ends Ukraine war 90 days",
    },
    {
        "slug":       "will-china-invade-taiwan-in-2025",
        "dyad":       "China-Taiwan",
        "resolution": 0,
        "end_date":   "2025-12-31",
        "label":      "China invades Taiwan 2025",
    },
    # ── Resolved Yes (true positives) ─────────────────────────────
    {
        "slug":       "us-x-venezuela-military-engagement-by",
        "dyad":       "US-Venezuela",
        "resolution": 1,
        "end_date":   "2026-01-15",
        "label":      "US military action vs Venezuela (Jan 15)",
        "sub_market": "January 15, 2026",
    },
    {
        "slug":       "us-strikes-iran-by",
        "dyad":       "US-Iran",
        "resolution": 1,
        "end_date":   "2026-02-28",
        "label":      "US strikes Iran by Feb 28 2026",
        "sub_market": "February 28",
    },
    {
        "slug":       "india-strike-on-pakistan-by",
        "dyad":       "India-Pakistan",
        "resolution": 0,
        "end_date":   "2025-12-31",
        "label":      "India strikes Pakistan by Dec 31 2025 (No)",
        "sub_market": "December 31",
    },
    # ── Live / unresolved (compare vs current market price) ───────
    {
        "slug":       "will-china-invade-taiwan-by-june-30-2026",
        "dyad":       "China-Taiwan",
        "resolution": None,
        "end_date":   "2026-06-30",
        "label":      "China invades Taiwan by Jun 30 2026 (live)",
    },
    {
        "slug":       "will-china-invade-taiwan-in-2026",
        "dyad":       "China-Taiwan",
        "resolution": None,
        "end_date":   "2026-12-31",
        "label":      "China invades Taiwan 2026 (live)",
    },
    {
        "slug":       "india-strike-on-pakistan-by",
        "dyad":       "India-Pakistan",
        "resolution": None,
        "end_date":   "2026-12-31",
        "label":      "India strikes Pakistan by Dec 31 2026 (live)",
        "sub_market": "December 31, 2026",
    },
]

# ── Snapshot offsets (days before end_date) ───────────────────────────
SNAPSHOT_OFFSETS = list(range(90, 0, -1))

# ─────────────────────────────────────────────────────────────────────
# POLYMARKET DATA LAYER
# ─────────────────────────────────────────────────────────────────────

GAMMA = "https://gamma-api.polymarket.com"
CLOB  = "https://clob.polymarket.com"

def get_resolution(market):
    if not market.get("closed"):
        return None
    try:
        outcomes = json.loads(market["outcomes"])
        prices   = [float(p) for p in json.loads(market["outcomePrices"])]
        yes_idx  = outcomes.index("Yes")
        return 1 if prices[yes_idx] > 0.95 else 0
    except Exception:
        return None

def fetch_price_history(token_id):
    cache_file = POLY_CACHE / f"{token_id[:20]}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())
    r = requests.get(f"{CLOB}/prices-history", params={
        "market": token_id, "interval": "max", "fidelity": 1440
    }, timeout=30)
    data = r.json()
    history = data.get("history", [])
    cache_file.write_text(json.dumps(history))
    time.sleep(0.2)
    return history

def get_market_price_at(history, target_date):
    """Get the market price closest to (but not after) target_date."""
    target_ts = datetime.combine(target_date, datetime.min.time()).timestamp()
    best = None
    for point in history:
        if point["t"] <= target_ts:
            best = point["p"]
        else:
            break
    return float(best) if best is not None else None

def fetch_polymarket_data(market_config):
    """Returns list of sub-markets with history + resolution."""
    slug = market_config["slug"]
    cache_file = POLY_CACHE / f"event_{slug[:40]}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    r = requests.get(f"{GAMMA}/events", params={"slug": slug}, timeout=30)
    events = r.json()
    if not events:
        print(f"  ✗ No event found for slug: {slug}")
        return []

    event = events[0]
    results = []
    for m in event["markets"]:
        tokens     = json.loads(m["clobTokenIds"])
        label      = m.get("groupItemTitle") or m.get("question", "")
        resolution = get_resolution(m)
        end_date   = (m.get("endDateIso") or m.get("endDate", ""))[:10]
        history    = fetch_price_history(tokens[0])
        if history:
            results.append({
                "label":      label,
                "end_date":   end_date,
                "resolution": resolution,
                "history":    history,
            })
        time.sleep(0.15)

    cache_file.write_text(json.dumps(results))
    return results

def pick_sub_market(sub_markets, market_config):
    """Pick the right sub-market from an event with multiple contracts."""
    target_label = market_config.get("sub_market")
    target_end   = market_config.get("end_date")

    if target_label:
        for sm in sub_markets:
            if target_label.lower() in sm["label"].lower():
                return sm

    # Fall back: match by end_date
    if target_end:
        for sm in sub_markets:
            if sm["end_date"] == target_end:
                return sm

    # Fall back: pick the one whose resolution matches what we expect
    expected_res = market_config.get("resolution")
    if expected_res is not None:
        for sm in sub_markets:
            if sm["resolution"] == expected_res:
                return sm

    # Last resort: first sub-market
    return sub_markets[0] if sub_markets else None

# ─────────────────────────────────────────────────────────────────────
# GNEWS LAYER
# ─────────────────────────────────────────────────────────────────────

DYAD_QUERIES = {
    "China-Taiwan":   '"China" AND ("Taiwan" OR "PLA" OR "strait")',
    "Russia-Ukraine": '"Russia" AND ("Ukraine" OR "Zelensky" OR "Kyiv")',
    "US-Iran":        '"United States" AND "Iran"',
    "US-Venezuela":   '"United States" AND "Venezuela"',
    "India-Pakistan": '"India" AND "Pakistan"',
    "US-domestic":    '"United States" AND ("civil unrest" OR "militia")',
}

def fetch_gnews(dyad, as_of_date):
    """Fetch GNews headlines for a dyad, date-locked to as_of_date. Cached."""
    cache_key = f"{dyad.replace('-','_')}_{as_of_date.strftime('%Y%m%d')}"
    cache_file = GNEWS_CACHE / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    query = DYAD_QUERIES.get(dyad, dyad)
    # GNews: to= param locks the date ceiling
    params = {
        "q":        query,
        "lang":     "en",
        "max":      10,
        "to":       as_of_date.strftime("%Y-%m-%dT23:59:59Z"),
        "from":     (as_of_date - timedelta(days=7)).strftime("%Y-%m-%dT00:00:00Z"),
        "apikey":   GNEWS_KEY,
        "sortby":   "publishedAt",
    }
    r = requests.get("https://gnews.io/api/v4/search", params=params, timeout=30)
    articles = r.json().get("articles", [])
    result = [{"title": a["title"], "description": a.get("description", ""),
               "publishedAt": a["publishedAt"]} for a in articles]
    cache_file.write_text(json.dumps(result))
    time.sleep(0.5)
    return result

# ─────────────────────────────────────────────────────────────────────
# CLAUDE NODE SCORER
# ─────────────────────────────────────────────────────────────────────

NODES = [
    "WinProbability", "WarCosts", "PatronDeterrence", "NuclearDeterrence",
    "CommitmentProblem", "Patience", "DemocraticPeace",
    "PreferenceAlignment", "HardlineClaims", "AudienceCosts",
    "MobilizationSignal",
]

NODE_RUBRICS = """
Score each node as a delta from baseline: -2.0 (strongly dampens conflict), -1.0 (moderately dampens), 0 (no signal), +1.0 (moderately escalates), +2.0 (strongly escalates). Use the full range — reserve ±2.0 for acute crisis signals like carrier group deployments, direct strikes, formal declarations.

- WinProbability: military balance shifts, capability demonstrations, exercises, troop deployment/presence/withdrawal. Only move if explicit military-operational signals. Do NOT score mobilization/call-up/conscription orders here -- those belong to MobilizationSignal.
- WarCosts: trade disruption, sanctions, economic decoupling increases costs (→ -0.5). Economic normalization decreases costs (→ +0.5).
- PatronDeterrence: patron commitment signals (US to Taiwan, etc). Strong commitment → -0.5. Weakening/ambiguity → +0.5.
- NuclearDeterrence: nuclear tests, alerts, deployment signals only. Almost always 0.
- CommitmentProblem: power shift fears, arms race signals → +0.5. Stabilization → -0.5.
- Patience: elections, leadership instability, domestic pressure to act → +0.5. Stability → -0.5.
- DemocraticPeace: democratic backsliding → +0.5. Institutional strengthening → -0.5.
- PreferenceAlignment: formal diplomatic breakdown → +0.5. Talks/agreements → -0.5.
- HardlineClaims: territorial rhetoric, sovereignty claims escalating → +0.5. De-escalation → -0.5.
- AudienceCosts: domestic political pressure to act -- protests, nationalist rallies, public pressure → +0.5. Public war fatigue → -0.5. (NOT military mobilization -- that belongs to MobilizationSignal.)
- MobilizationSignal: ONLY score this for an explicit reserve call-up, conscription order, formal mobilization decree, or military alert-status escalation -- the act of activating/calling up forces, not their presence or deployment location (that is WinProbability). Clear mobilization order → +1.0 to +2.0. Generic troop movement, exercises, or presence without an explicit call-up order → 0 (the literature finds this channel statistically null; do not infer mobilization from deployment alone). Almost always 0.

Return ONLY valid JSON, no preamble: {"WinProbability": 0, "WarCosts": 0, ...}
"""

def score_nodes(dyad, articles, as_of_date):
    """Call Claude to score 10 DAG nodes from headlines."""
    if not articles:
        return {n: 0.0 for n in NODES}

    headlines = "\n".join(
        f"- {a['title']} ({a['publishedAt'][:10]})"
        for a in articles
    )

    prompt = f"""Dyad: {dyad}
Date: {as_of_date}
Headlines:
{headlines}

{NODE_RUBRICS}"""

    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": "claude-opus-4-6",
        "max_tokens": 300,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers=headers, json=body, timeout=60)
    resp = r.json()
    if "content" not in resp:
        print(f"    [warn] Claude API error: {resp.get('error', {}).get('message', 'unknown')}")
        return {n: 0.0 for n in NODES}
    text = resp["content"][0]["text"].strip()

    try:
        # Strip markdown fences if present
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        return json.loads(text.strip())
    except Exception:
        print(f"    [warn] Node scoring parse error, using zeros")
        return {n: 0.0 for n in NODES}

# ─────────────────────────────────────────────────────────────────────
# MACH 2 FORMULA
# ─────────────────────────────────────────────────────────────────────

def predict_probability(toggles, days_remaining):
    """
    Four-tier Mach 2 formula from predict.py (June 11 session).
    toggles: dict of node_name → score (baseline + delta)
    """
    a = ALPHA

    t = toggles  # shorthand

    # Tier 2: war payoffs + effective weights
    w     = (a["WinProbability"]        * t.get("WinProbability", 0)
           + a["WarCosts"]              * t.get("WarCosts", 0)
           + a["PatronDeterrence_w"]    * t.get("PatronDeterrence", 0)
           + a.get("NuclearDeterrence_expert", a["NuclearDeterrence"])
                                        * t.get("NuclearDeterrence", 0))

    Omega = (a["CommitmentProblem"]     * t.get("CommitmentProblem", 0)
           + a["Patience"]              * t.get("Patience", 0)
           + a.get("MobilizationSignal", 0.0) * t.get("MobilizationSignal", 0))

    # Tier 3: credibility-adjusted war value
    w_over_pi = w + a["DemocraticPeace"] * t.get("DemocraticPeace", 0)

    # Tier 4: war pressure
    WarPayoff   = Omega + w_over_pi
    WarPolitics = (a["PreferenceAlignment"] * t.get("PreferenceAlignment", 0)
                 + a["AudienceCosts"]       * t.get("AudienceCosts", 0))

    # HardlineClaims goes direct to Conflict (fixed edge = 1.0)
    HardlineDirect = t.get("HardlineClaims", 0)

    log_odds_shift = WarPayoff + WarPolitics + HardlineDirect

    # Convert annual base rate to window probability, then to log-odds
    # Correct compounding: p_window = 1 - (1 - p_annual)^(days/365)
    p_window_base   = 1 - (1 - BASE_RATE_ANNUAL) ** (days_remaining / 365)
    base_window_log_odds = math.log(p_window_base / (1 - p_window_base))
    window_log_odds = base_window_log_odds + log_odds_shift

    p = 1 / (1 + math.exp(-window_log_odds))
    return round(p, 4)

# ─────────────────────────────────────────────────────────────────────
# BASELINE TOGGLES PER DYAD
# (loads from dyad_configs.json — falls back to neutral if missing)
# ─────────────────────────────────────────────────────────────────────

def load_dyad_baseline(dyad):
    config_path = ROOT / "pipeline" / "dyad_configs.json"
    if config_path.exists():
        configs = json.loads(config_path.read_text())
        if dyad in configs:
            return configs[dyad]["baseline"]
    # Neutral fallback — everything at 0
    return {n: 0.0 for n in NODES}

def apply_deltas(baseline, deltas):
    result = dict(baseline)
    for k, v in deltas.items():
        if k in result:
            result[k] = result[k] + v
    return result

# ─────────────────────────────────────────────────────────────────────
# CONTAMINATION CHECK
# ─────────────────────────────────────────────────────────────────────

def run_leakage_check():
    """
    Score US-Iran at T-90 (Nov 28 2025) using:
    (A) correct Nov 2025 headlines
    (B) wrong headlines — July 2024 China-Taiwan news
    If scores barely differ, model is using training memory not headlines.
    """
    print("\n" + "="*60)
    print("  CONTAMINATION CHECK — US-Iran T-90")
    print("="*60)

    target_date = date(2026, 2, 28)
    snapshot    = target_date - timedelta(days=90)  # Nov 30 2025

    # A: correct headlines
    articles_correct = fetch_gnews("US-Iran", snapshot)
    scores_correct   = score_nodes("US-Iran", articles_correct, snapshot)

    # B: wrong headlines (China-Taiwan, July 2024 — wrong dyad, wrong time)
    wrong_date       = date(2024, 7, 15)
    articles_wrong   = fetch_gnews("China-Taiwan", wrong_date)
    scores_wrong     = score_nodes("US-Iran", articles_wrong, snapshot)

    print(f"\n  Snapshot date: {snapshot}")
    print(f"  Correct headlines ({len(articles_correct)}): US-Iran Nov 2025")
    print(f"  Wrong headlines   ({len(articles_wrong)}): China-Taiwan Jul 2024\n")
    print(f"  {'Node':<22} {'Correct':>8} {'Wrong':>8} {'Delta':>8}")
    print("  " + "-"*48)

    max_delta = 0
    for node in NODES:
        c = scores_correct.get(node, 0)
        w = scores_wrong.get(node, 0)
        d = abs(c - w)
        max_delta = max(max_delta, d)
        flag = " ← MOVES" if d > 0.2 else ""
        print(f"  {node:<22} {c:>8.2f} {w:>8.2f} {d:>8.2f}{flag}")

    print(f"\n  Max delta across nodes: {max_delta:.2f}")
    if max_delta >= 0.3:
        print("  ✓ PASS — GNews headlines are doing the work. Proceed with full backtest.")
    else:
        print("  ✗ FAIL — Scores barely move. Training data contamination likely.")
        print("    Recommendation: restrict backtest to post-Aug 2025 markets only.")

    return max_delta >= 0.3

# ─────────────────────────────────────────────────────────────────────
# MAIN BACKTEST LOOP
# ─────────────────────────────────────────────────────────────────────

def run_backtest(dry_run=False):
    slate = SLATE[:2] if dry_run else SLATE
    rows  = []

    for mkt in slate:
        print(f"\n── {mkt['label']} ──")

        # 1. Fetch price history + resolution
        sub_markets = fetch_polymarket_data(mkt)
        if not sub_markets:
            print("  ✗ No Polymarket data — skipping")
            continue

        sm = pick_sub_market(sub_markets, mkt)
        if not sm:
            print("  ✗ Could not pick sub-market — skipping")
            continue

        resolution = mkt["resolution"]
        if resolution is None:
            resolution = sm["resolution"]  # for live markets, use whatever Gamma says

        end_date = date.fromisoformat(mkt["end_date"])
        dyad     = mkt["dyad"]
        baseline = load_dyad_baseline(dyad)

        print(f"  Sub-market: {sm['label']} | Resolution: {resolution} | "
              f"History: {len(sm['history'])} days")

        # 2. Run snapshots
        for offset in SNAPSHOT_OFFSETS:
            snapshot_date = end_date - timedelta(days=offset)

            # Skip future snapshots for resolved markets
            if snapshot_date > date.today():
                continue

            # Get contemporaneous market price
            mkt_price = get_market_price_at(sm["history"], snapshot_date)
            if mkt_price is None:
                continue

            days_remaining = (end_date - snapshot_date).days

            # Fetch headlines + score nodes
            articles = fetch_gnews(dyad, snapshot_date)
            deltas   = score_nodes(dyad, articles, snapshot_date)
            toggles  = apply_deltas(baseline, deltas)

            # Run Mach 2
            engine_p = predict_probability(toggles, days_remaining)

            # Brier scores (only for resolved markets)
            b_engine = (engine_p - resolution)**2 if resolution is not None else None
            b_market = (mkt_price - resolution)**2 if resolution is not None else None

            row = {
                "market":        mkt["label"],
                "dyad":          dyad,
                "snapshot_date": snapshot_date.isoformat(),
                "days_remaining":days_remaining,
                "resolution":    resolution,
                "engine_p":      engine_p,
                "market_p":      mkt_price,
                "b_engine":      b_engine,
                "b_market":      b_market,
                "n_articles":    len(articles),
            }
            rows.append(row)

            res_str = str(resolution) if resolution is not None else "live"
            beat    = ""
            if b_engine is not None and b_market is not None:
                beat = "✓" if b_engine < b_market else "✗"
            print(f"  {beat} T-{offset:3d} ({snapshot_date}) | "
                  f"Engine: {engine_p:.1%} | Market: {mkt_price:.1%} | "
                  f"Res: {res_str} | Articles: {len(articles)}")

    return rows

# ─────────────────────────────────────────────────────────────────────
# SCORING + OUTPUT
# ─────────────────────────────────────────────────────────────────────

def print_results(rows):
    resolved = [r for r in rows if r["resolution"] is not None]
    live     = [r for r in rows if r["resolution"] is None]

    if not resolved:
        print("\nNo resolved markets to score yet.")
        return

    mean_b_engine = sum(r["b_engine"] for r in resolved) / len(resolved)
    mean_b_market = sum(r["b_market"] for r in resolved) / len(resolved)
    wins = sum(1 for r in resolved if r["b_engine"] < r["b_market"])

    print("\n" + "█"*60)
    print("  BACKTEST RESULTS — Mach 2")
    print("█"*60)
    print(f"\n  Resolved rows:  {len(resolved)}")
    print(f"  Live rows:      {len(live)}")
    print(f"\n  Engine Brier:   {mean_b_engine:.4f}")
    print(f"  Market Brier:   {mean_b_market:.4f}")
    delta = mean_b_engine - mean_b_market
    sign  = "+" if delta > 0 else ""
    print(f"  Delta:          {sign}{delta:.4f}  "
          f"({'engine WORSE' if delta > 0 else 'engine BETTER'})")
    print(f"\n  Engine beats market: {wins}/{len(resolved)} snapshots")

    # By resolution
    yes_rows = [r for r in resolved if r["resolution"] == 1]
    no_rows  = [r for r in resolved if r["resolution"] == 0]
    print(f"\n  BY RESOLUTION:")
    if yes_rows:
        print(f"    Resolved Yes (n={len(yes_rows)}): "
              f"Engine {sum(r['b_engine'] for r in yes_rows)/len(yes_rows):.4f} | "
              f"Market {sum(r['b_market'] for r in yes_rows)/len(yes_rows):.4f}")
    if no_rows:
        print(f"    Resolved No  (n={len(no_rows)}): "
              f"Engine {sum(r['b_engine'] for r in no_rows)/len(no_rows):.4f} | "
              f"Market {sum(r['b_market'] for r in no_rows)/len(no_rows):.4f}")

    # By snapshot offset
    print(f"\n  BY SNAPSHOT:")
    for offset in SNAPSHOT_OFFSETS:
        offset_rows = [r for r in resolved if r["days_remaining"] == offset]
        if offset_rows:
            print(f"    T-{offset:3d}: Engine {sum(r['b_engine'] for r in offset_rows)/len(offset_rows):.4f} | "
                  f"Market {sum(r['b_market'] for r in offset_rows)/len(offset_rows):.4f}")

    # Calibration table
    print(f"\n  CALIBRATION TABLE (engine bins vs actual resolution rate):")
    bins = [(0, 0.10), (0.10, 0.30), (0.30, 0.60), (0.60, 1.01)]
    for lo, hi in bins:
        bin_rows = [r for r in resolved if lo <= r["engine_p"] < hi]
        if bin_rows:
            actual = sum(r["resolution"] for r in bin_rows) / len(bin_rows)
            print(f"    {lo:.0%}–{hi:.0%}: n={len(bin_rows)}, actual rate={actual:.0%}")

    # Live market comparison
    if live:
        print(f"\n  LIVE MARKETS (no Brier — comparison only):")
        for r in live:
            edge = r["engine_p"] - r["market_p"]
            sign = "+" if edge > 0 else ""
            print(f"    {r['market'][:50]:<50} "
                  f"Engine {r['engine_p']:.1%} | Market {r['market_p']:.1%} | "
                  f"Edge {sign}{edge:.1%}")

    print()

# ─────────────────────────────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run",  action="store_true", help="First 2 markets only")
    parser.add_argument("--leakage",  action="store_true", help="Contamination check only")
    args = parser.parse_args()

    if args.leakage:
        run_leakage_check()
        sys.exit(0)

    # Always run leakage check first on a fresh run
    if not args.dry_run:
        passed = run_leakage_check()
        if not passed:
            print("\n  ⚠ Contamination check failed. Run with --leakage to review.")
            print("  Continuing anyway — interpret results with caution.\n")

    rows = run_backtest(dry_run=args.dry_run)

    # Save results
    RESULTS_OUT.write_text(json.dumps(rows, indent=2))
    print(f"\n  Results saved → {RESULTS_OUT}")

    print_results(rows)
