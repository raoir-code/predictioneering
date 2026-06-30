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

import os, sys, json, time, argparse, math, re
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
ALPHA["OperationalFeasibility_w"] = ALPHA.get("OperationalFeasibility", -1.50)
ALPHA["InitiatorSurvivalRisk_w"]  = ALPHA.get("InitiatorSurvivalRisk",  -1.20)
ALPHA["PatronMoralHazard_w"]      = ALPHA.get("PatronMoralHazard",       +0.60)
ALPHA["SubstitutionPath_w"]       = ALPHA.get("SubstitutionPath",        -1.10)

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

_DYAD_CONFIGS_CACHE = None

def _load_dyad_query(dyad):
    """
    Resolve the GNews query string for a dyad, in priority order:
      1. pipeline/dyad_configs.json "query" field (the real, curated queries)
      2. Legacy DYAD_QUERIES dict (small hardcoded fallback set)
      3. The bare dyad string itself (last resort -- usually yields 0 articles,
         since dyad names like "Israel-Yemen" rarely appear verbatim in headlines)
    """
    global _DYAD_CONFIGS_CACHE
    if _DYAD_CONFIGS_CACHE is None:
        config_path = ROOT / "pipeline" / "dyad_configs.json"
        if config_path.exists():
            _DYAD_CONFIGS_CACHE = json.loads(config_path.read_text())
        else:
            _DYAD_CONFIGS_CACHE = {}

    cfg = _DYAD_CONFIGS_CACHE.get(dyad)
    if cfg and cfg.get("query"):
        return cfg["query"]

    if dyad in DYAD_QUERIES:
        return DYAD_QUERIES[dyad]

    print(f"    [fetch_gnews] WARNING: no query found for dyad '{dyad}' in "
          f"dyad_configs.json or DYAD_QUERIES -- falling back to bare dyad "
          f"string as query (likely yields 0 articles).")
    return dyad


def fetch_gnews(dyad, as_of_date):
    """Fetch GNews headlines for a dyad, date-locked to as_of_date. Cached."""
    safe_dyad = re.sub(r'[^A-Za-z0-9_]+', '_', dyad)
    cache_key = f"{safe_dyad}_{as_of_date.strftime('%Y%m%d')}"
    cache_file = GNEWS_CACHE / f"{cache_key}.json"
    if cache_file.exists():
        return json.loads(cache_file.read_text())

    query = _load_dyad_query(dyad)
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
    body = r.json()
    articles = body.get("articles", [])
    if not articles:
        print(f"    [fetch_gnews] {dyad}: 0 articles. status={r.status_code} "
              f"query={query!r} response_keys={list(body.keys())}")
        if "errors" in body:
            print(f"    [fetch_gnews] {dyad}: API error detail: {body['errors']}")
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

# ── Q-SUBMODEL — new q-parents, June 17 2026 spec ──────────────────────
# logit(q_t) = q0 + xi*kappa_commit + Sum(onset-valid) + Sum(live dynamic)
# Strictly additive in logit space, v1 — no interactions.
#
# Q0 and ICB_COEF below come from a real logistic regression on ICB
# System-Level data (June 18 2026, via ChatGPT, critiqued/verified by Claude),
# NOT hand-set. DV = VIOL>=3 ("serious clashes or full-scale war"), N=509,
# positives=227 (44.6%), McFadden pseudo-R^2=0.198. Independent variables
# were recoded onto this pipeline's exact rubric scale (crosswalk documented
# in the work log) BEFORE fitting, so these coefficients are correctly
# composable with the raw rubric outputs in build_q_components() below --
# a first-pass version of this regression used ICB's native categorical
# codings instead and was not directly composable.
#
# IMPORTANT: this is a crisis-conditioned intercept, not a normal dyad-day
# base rate. ICB's whole sample is already-recognized international crises
# (threat to basic values + time pressure + heightened probability of
# military hostilities), so it cannot speak to "ordinary, nothing-happening
# day" calibration -- confirmed explicitly by the regression's own author
# when asked. Expect this to still read somewhat too high on truly quiet
# snapshots; that's a known, documented limitation, not a bug to chase now.
#
# Coefficient confidence varies. TriggerType, ValueThreatGravity, and
# ThirdPartyMilitaryInvolvement are robustly significant (each >3x their own
# SE). ProtractedConflict and GeographicProximity are NOT statistically
# distinguishable from zero in this fit (coefficient smaller than or
# comparable to its own SE) -- consistent with this pipeline's own June 18
# backtest finding that those two terms were confounded/unreliable, since
# only 2 of 5 dyads ever resolved Yes. Used here as the best available point
# estimate rather than zeroed out, but flagged as the least trustworthy part
# of this equation.
Q0 = -3.407  # SE 0.398

ICB_COEF = {
    "TriggerType":                   3.680,  # SE 0.455, robustly significant
    "ValueThreatGravity":            3.674,  # SE 0.620, robustly significant
    "ThirdPartyMilitaryInvolvement": 2.474,  # SE 0.771, significant, medium-confidence mapping (GPINVTP/USINV/SUINV/CHINV aggregated)
    "ProtractedConflict":            0.535,  # SE 0.715 -- NOT significant, use with caution
    "GeographicProximity":           1.045,  # SE 0.757 -- NOT significant, use with caution
}

# Mach 3 regime classification (June 18 2026).
# Z_t=0: quiet dyad -- use Mach 2 structural formula.
# Z_t=1: active pre-war crisis -- use q_full as primary probability.
#        Counterfactual validated: Brier 0.0675 vs market 0.1043.
# Z_t=2: ongoing war, inverted-polarity market -- exclude from Brier.
DYAD_REGIME = {
    "China-Taiwan":   0,
    "India-Pakistan": 0,
    "US-Iran":        1,
    "US-Venezuela":   1,
    "Russia-Ukraine": 2,
}

# Onset-valid, LLM-scored each snapshot from the current precipitating event.
# NOTE: the spec's "5 onset-valid fields" includes ProtractedConflict and
# GeographicProximity, but both are explicitly defined as static dyad
# metadata "never scored from news" -- so only 3 of the 5 go through the
# LLM. The other 2 come from dyad_configs.json (Q_PARENTS_STATIC below).
Q_PARENTS_ONSET_LLM = ["TriggerType", "ValueThreatGravity", "ThirdPartyMilitaryInvolvement"]

# Live dynamic, LLM-scored each snapshot, own call to protect field quality.
Q_PARENTS_LIVE = ["RoutineMilitaryPressure", "OperationalPreparation", "LiveViolenceObserved",
                  "LiveUltimatumDeadline", "LiveMediationAccepted", "LiveAbatementSignal"]

# Static dyad metadata, set once in dyad_configs.json under "q_static", never scored from news.
Q_PARENTS_STATIC = ["ProtractedConflict", "GeographicProximity"]

NODE_RUBRICS = """
Score each node as a delta from baseline: -2.0 (strongly dampens conflict), -1.0 (moderately dampens), 0 (no signal), +1.0 (moderately escalates), +2.0 (strongly escalates). Use the full range — reserve ±2.0 for acute crisis signals like carrier group deployments, direct strikes, formal declarations.

CRITICAL — DOUBLE-COUNTING GUARD: Each nonzero delta must be justified by a DISTINCT evidence atom. A single headline justifies ONE nonzero node delta only. If the same event plausibly fires multiple nodes, score ONLY the most direct mechanism and zero the rest. Examples: "Deal signed" → PreferenceAlignment only. "Ceasefire violated, retaliatory strike" → HardlineClaims only if outside ceasefire framework, else 0. "Arms sale approved" → PatronDeterrence only. "Mobilization order" → MobilizationSignal only. When in doubt, score the most structurally upstream node and zero the rest.

- WinProbability: military balance shifts, capability demonstrations, exercises, troop deployment/presence/withdrawal. Only move if explicit military-operational signals. Do NOT score mobilization/call-up/conscription orders here -- those belong to MobilizationSignal.
- WarCosts: trade disruption, sanctions, economic decoupling increases costs (→ -0.5). Economic normalization decreases costs (→ +0.5).
- PatronDeterrence: patron commitment signals (US to Taiwan, etc). Strong commitment → -0.5. Weakening/ambiguity → +0.5.
- NuclearDeterrence: nuclear tests, alerts, deployment signals only. Almost always 0.
- CommitmentProblem: power shift fears, arms race signals → +0.5. Stabilization → -0.5.
- Patience: elections, leadership instability, domestic pressure to act → +0.5. Stability → -0.5.
- DemocraticPeace: democratic backsliding → +0.5. Institutional strengthening → -0.5.
- PreferenceAlignment: formal diplomatic breakdown, framework collapse, official withdrawal from deal → +0.5. Ceasefire announced, deal signed, formal agreement reached, talks resumed after collapse → -0.5. IMPORTANT: mere talks scheduled or envoys meeting score 0 — only concrete formal shifts qualify. Routine ceasefire violations managed within the framework do NOT fire this node.
- HardlineClaims: territorial rhetoric, sovereignty claims escalating → +0.5. De-escalation → -0.5. IMPORTANT: retaliatory strikes or exchanges that occur WITHIN an active ceasefire/truce framework score 0 — the ceasefire framework is the dominant mechanism (PreferenceAlignment), not the individual exchange. Only score +0.5 for NEW escalation outside any existing framework.
- AudienceCosts: domestic political pressure to act -- protests, nationalist rallies, public pressure → +0.5. Public war fatigue → -0.5. (NOT military mobilization -- that belongs to MobilizationSignal.)
- MobilizationSignal: ONLY score this for an explicit reserve call-up, conscription order, formal mobilization decree, or military alert-status escalation -- the act of activating/calling up forces, not their presence or deployment location (that is WinProbability). Clear mobilization order → +1.0 to +2.0. Generic troop movement, exercises, or presence without an explicit call-up order → 0 (the literature finds this channel statistically null; do not infer mobilization from deployment alone). Almost always 0.
"""

RUBRIC_ONSET_ADDITION = """
Also score these 3 onset-context q-parents, as PART OF THE SAME JSON object (absolute weights, not deltas from baseline -- output exactly the value implied by the category, not a delta):

- TriggerType: the PRECIPITATING event of the current dispute/crisis (not general background tension).
    0     = verbal or economic trigger only
    0.10 to 0.25 = political, internal-regime, or external-change trigger (higher = more acute regime/political shock)
    0     = nonviolent military trigger (mobilization/show-of-force alone, no engagement) -- do NOT score this positively
    0.60  = indirect OR direct violent trigger (border clash, strike, bombing, cross-border raid, airspace engagement, attack on ally/client, ship seizure/sinking, attack on military personnel) -- both treated identically
    Use 0 if no clear precipitating event this snapshot.

- ValueThreatGravity: severity of what's explicitly framed as at stake.
    0    = low / economic
    0.25 = political, territorial, or influence
    0.60 = grave damage explicitly framed
    0.80 = existential threat explicitly framed (regime survival, territorial integrity/annexation, mass casualties, national survival) -- requires explicit framing, do NOT infer from a country's general importance.

- ThirdPartyMilitaryInvolvement: concrete content only -- generic "watching closely" or statements of concern do not count.
    0    = none, or diplomatic restraint/mediation only
    0.20 = covert/semi-military (arms shipments, advisors, sanctions-as-coercion)
    0.45 = direct military (troop deployment, airstrikes, naval deployment, direct intervention) by a third party

Return ONLY valid JSON containing ALL fields together (the nodes above AND these 3), no preamble.
"""

RUBRIC_LIVE_TEMPLATE = """
{crisis_context}

Score these 6 live-dynamic q-parents from the headlines below. Each has its own recency window -- only count evidence dated within that window before the snapshot date; ignore anything older.

CRITICAL DISTINCTION for military pressure nodes:
- RoutineMilitaryPressure: exercises, patrols, standard ADIZ incursions, arms sale reactions, capability announcements, post-conflict rhetoric, speeches, warnings, NOTAMs for routine drills. These are CHRONIC features of rivalries and do NOT indicate imminent action.
- OperationalPreparation: force packages moving into strike range, airspace/maritime closure, evacuation orders, confirmed logistics/munitions buildup, force protection upgrades, allied operational coordination, specific time-bounded ultimatums with visible military backing. These indicate a DECISION to use force may be imminent.

- RoutineMilitaryPressure (7-day window): 0 = none or genuinely quiet. 0.25 = standard exercises / patrols / symbolic demonstrations / post-conflict rhetoric. 0.60 = elevated rhetoric with capability claims but no operational movement. Do NOT score operational preparation here.

- OperationalPreparation (7-day window): SCORE HIGH ONLY for irreversible operational acts. 0 = no operational signals, OR routine exercises, ADIZ violations, rhetoric, arms sale announcements, patrols, capability claims — score ZERO even if alarming in tone. 0.25 = unusual but genuinely ambiguous movement (not standard exercises). 0.60 = confirmed irreversible act: strike packages moving to forward positions, named airspace/maritime closure zones activated, evacuation orders issued, confirmed munitions/logistics buildup at forward bases, allied operational coordination for specific contingency. 1.00 = 0.60 criteria MET AND a binding named deadline with stated consequences exists publicly. CRITICAL: chronic rivalry features (PLA exercises, ADIZ incursions, naval patrols, missile tests, diplomatic protests) score 0 here — use RoutineMilitaryPressure.

- LiveViolenceObserved (7-day window): 0 = no violence this window. 0.50 = minor/isolated incident. 0.90 = serious clash / strike / raid / attack on military personnel / cross-border fire. A full-scale attack is excluded (it becomes the outcome, not a predictor).
    IMPORTANT: {trigger_context}

- LiveUltimatumDeadline (14-day window): 0 = none. 0.20 = vague threat. 0.60 = explicit deadline / red line / exclusion zone / "withdraw by X" / "we will respond if".

- LiveMediationAccepted (14-day window): report the MAGNITUDE only (0, 0.30, or 0.60) -- sign is applied downstream in code, do not output a negative number. 0 = none, or offered-not-accepted. 0.30 = talks scheduled or ongoing (procedural diplomacy -- weak signal). 0.60 = concrete stand-down agreement, verified withdrawal, or ceasefire implementation in progress. NOTE: talks/negotiations continuing alongside military pressure are NOT strong de-escalation signals.

- LiveAbatementSignal (21-day window): report the MAGNITUDE only (0 or 0.50) -- sign is applied downstream in code. 0.50 = verified concrete stand-down: withdrawal orders executed, ceasefire confirmed, exclusion zones lifted, forces visibly stood down. 0 = none of the above. Talks alone do NOT qualify.

Return ONLY valid JSON, no preamble: {{"RoutineMilitaryPressure": 0, "OperationalPreparation": 0, "LiveViolenceObserved": 0, "LiveUltimatumDeadline": 0, "LiveMediationAccepted": 0, "LiveAbatementSignal": 0}}
"""

def _call_claude_json(prompt, expected_fields, max_tokens, retries=1):
    """Shared Claude call + JSON parse, used by both Call A and Call B.

    The network call is wrapped separately from the JSON-parsing step below --
    a dropped connection or read timeout (e.g. from a laptop sleep/wake cycle)
    is a different failure mode than the model returning malformed JSON, and
    previously crashed the whole script since nothing caught it. Retries once
    before falling back to zeros, since a fresh attempt right after a timeout
    usually just works.
    """
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = None
    for attempt in range(retries + 1):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body, timeout=60)
            resp = r.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                print(f"    [warn] API request failed ({type(e).__name__}), retrying once...")
                continue
            print(f"    [warn] API request failed ({type(e).__name__}) after retry, using zeros")
            return {n: 0.0 for n in expected_fields}
        except ValueError:
            print(f"    [warn] API returned non-JSON response, using zeros")
            return {n: 0.0 for n in expected_fields}

    if "content" not in resp:
        print(f"    [warn] Claude API error: {resp.get('error', {}).get('message', 'unknown')}")
        return {n: 0.0 for n in expected_fields}
    text = resp["content"][0]["text"].strip()

    # Three-tier JSON extraction (June 18 2026):
    # Tier 1 -- direct parse (clean JSON, happy path).
    # Tier 2 -- strip markdown code fences (```json...```).
    # Tier 3 -- brace extraction: find first { and last } and parse
    #   that substring -- handles preamble text before the JSON object.
    # On total failure: log first 300 chars of raw response.
    def _fence_strip(t):
        if "```" not in t:
            return t
        part = t.split("```")[1].lstrip("json").strip()
        return re.sub(r'": \+(\d)', r'": \1', part)

    def _brace_extract(t):
        lo, hi = t.find("{"), t.rfind("}")
        return t[lo:hi+1] if lo != -1 and hi != -1 else ""

    for label, candidate in [
        ("direct",        text),
        ("fence-strip",   _fence_strip(text)),
        ("brace-extract", _brace_extract(text)),
    ]:
        try:
            parsed = json.loads(candidate)
            return {n: float(parsed.get(n, 0.0)) for n in expected_fields}
        except Exception:
            continue
    print(f"    [warn] Node scoring parse error (all 3 tiers), using zeros")
    print(f"    [warn] raw response (first 300 chars): {text[:300]!r}")
    return {n: 0.0 for n in expected_fields}

def score_nodes_call_a(dyad, articles, as_of_date):
    """Call A: existing 11 primitives + 3 new onset-context q-parents, one call."""
    expected = NODES + Q_PARENTS_ONSET_LLM
    if not articles:
        return {n: 0.0 for n in expected}

    headlines = "\n".join(
        f"- {a['title']} ({a['publishedAt'][:10]})"
        for a in articles
    )
    prompt = f"""Dyad: {dyad}
Date: {as_of_date}
Headlines:
{headlines}

EVIDENCE RELEVANCE GATE (apply BEFORE scoring any node):
Before using any headline as evidence, verify it genuinely concerns THIS dyad's
named actors in direct relationship to each other -- not a different conflict,
a different country pair, or a third party that merely shares a keyword with
one of the actors. Examples of false matches to exclude: a ship "flagged" to
a country is not that country acting; a missile or strike in an unrelated war
involving only one of the two actors is not evidence for THIS dyad even if the
headline matched this dyad's search terms. If a headline is not genuinely
about this specific dyad's actors interacting, exclude it entirely from
consideration for every node -- do not let it influence any score, even
indirectly or partially.

{NODE_RUBRICS}
{RUBRIC_ONSET_ADDITION}

Return ONLY valid JSON with no preamble, explanation, or markdown. Example: {{"WinProbability": 0, "WarCosts": 0}}"""

    return _call_claude_json(prompt, expected, max_tokens=700)

def score_nodes_call_b(dyad, articles, as_of_date, trigger_was_violent):
    """Call B: 5 live-dynamic q-parents, separate call to protect field quality.

    trigger_was_violent: bool, from Call A's TriggerType this same snapshot.
    Collision fix (spec checklist item): TriggerType fires once at actual
    crisis onset; LiveViolenceObserved must require violence ADDITIONAL to
    whatever already set TriggerType, or the same triggering event gets
    double-counted for the rest of its 7-day rolling window.
    """
    _crisis_ctx = ""  # default; overwritten below from dyad_configs if available
    expected = Q_PARENTS_LIVE
    if not articles:
        return {n: 0.0 for n in expected}

    # Deduplicate near-identical headlines before scoring
    seen_titles = set()
    deduped = []
    for a in articles:
        title = a.get('title', '').strip().lower()[:80]
        if title not in seen_titles:
            seen_titles.add(title)
            deduped.append(a)
    headlines = "\n".join(
        f"- {a['title']} ({a['publishedAt'][:10]})"
        for a in deduped
    )
    trigger_context = (
        "The precipitating violent event for this crisis was already scored under "
        "TriggerType in a separate call. Do NOT count that same triggering incident "
        "again here -- only score violence ADDITIONAL to whatever already set TriggerType."
        if trigger_was_violent else
        "No violent triggering event has been scored for this crisis yet -- score any "
        "violence observed in the headlines normally."
    )
    prompt = f"""Dyad: {dyad}
Date: {as_of_date}
Headlines:
{headlines}

EVIDENCE RELEVANCE GATE (apply BEFORE scoring any node):
Before using any headline as evidence, verify it genuinely concerns THIS dyad's
named actors in direct relationship to each other -- not a different conflict,
a different country pair, or a third party that merely shares a keyword with
one of the actors. Examples of false matches to exclude: a ship "flagged" to
a country is not that country acting; a missile or strike in an unrelated war
involving only one of the two actors is not evidence for THIS dyad even if the
headline matched this dyad's search terms. If a headline is not genuinely
about this specific dyad's actors interacting, exclude it entirely from
consideration for every node -- do not let it influence any score, even
indirectly or partially.

{RUBRIC_LIVE_TEMPLATE.format(trigger_context=trigger_context, crisis_context=_crisis_ctx)}

Return ONLY valid JSON with no preamble, explanation, or markdown. Example: {{"LiveNonviolentMilitaryPressure": 0, "LiveViolenceObserved": 0, "LiveUltimatumDeadline": 0, "LiveMediationAccepted": 0, "LiveAbatementSignal": 0}}"""

    return _call_claude_json(prompt, expected, max_tokens=400)

# ── Q-SUBMODEL DECOMPOSITION ────────────────────────────────────────────
# Pure arithmetic, additive in logit space -- free post-hoc attribution
# from a single backtest run, no sequential ablations needed.

ONSET_ONLY_KEYS = ["base", "CommitmentProblem", "TriggerType", "ValueThreatGravity",
                   "ThirdPartyMilitaryInvolvement", "ProtractedConflict", "GeographicProximity"]
LIVE_ONLY_KEYS  = ["base", "CommitmentProblem", "OperationalPreparation", "RoutineMilitaryPressure",
                   "LiveViolenceObserved", "LiveUltimatumDeadline",
                   "LiveMediationAccepted", "LiveAbatementSignal"]

def load_dyad_q_static(dyad):
    config_path = ROOT / "pipeline" / "dyad_configs.json"
    if config_path.exists():
        configs = json.loads(config_path.read_text())
        if dyad in configs and "q_static" in configs[dyad]:
            return configs[dyad]["q_static"]
    return {n: 0.0 for n in Q_PARENTS_STATIC}

def build_q_components(toggles, call_a, call_b, q_static):
    """toggles: post-delta node values (for CommitmentProblem reuse).
    call_a/call_b: raw LLM outputs. q_static: dyad_configs.json q_static dict."""
    return {
        "base":                          Q0,
        "CommitmentProblem":             ALPHA["CommitmentProblem"] * toggles.get("CommitmentProblem", 0),
        "TriggerType":                   ICB_COEF["TriggerType"] * call_a.get("TriggerType", 0.0),
        "ValueThreatGravity":            ICB_COEF["ValueThreatGravity"] * call_a.get("ValueThreatGravity", 0.0),
        "ThirdPartyMilitaryInvolvement": ICB_COEF["ThirdPartyMilitaryInvolvement"] * call_a.get("ThirdPartyMilitaryInvolvement", 0.0),
        "ProtractedConflict":            ICB_COEF["ProtractedConflict"] * q_static.get("ProtractedConflict", 0.0),
        "GeographicProximity":           ICB_COEF["GeographicProximity"] * q_static.get("GeographicProximity", 0.0),
        "OperationalPreparation":(
            call_b.get("OperationalPreparation", 0.0) * 1.0),
        "RoutineMilitaryPressure":(
            call_b.get("RoutineMilitaryPressure", 0.0) * 1.0
        ),
        "LiveViolenceObserved":          call_b.get("LiveViolenceObserved", 0.0),
        "LiveUltimatumDeadline":         call_b.get("LiveUltimatumDeadline", 0.0),
        "LiveMediationAccepted":         -call_b.get("LiveMediationAccepted", 0.0),
        "LiveAbatementSignal":           -call_b.get("LiveAbatementSignal", 0.0),
    }

def q_with_subset(q_components, include_keys=None):
    keys = include_keys if include_keys is not None else list(q_components.keys())
    subset_logit = sum(v for k, v in q_components.items() if k in keys)
    return 1 / (1 + math.exp(-subset_logit))

# ─────────────────────────────────────────────────────────────────────
# MACH 2 FORMULA
# ─────────────────────────────────────────────────────────────────────

def predict_probability(toggles, days_remaining, q_logit=0.0):
    """
    Four-tier Mach 2 formula from predict.py (June 11 session), extended
    June 18 2026 to fold in the q-submodel's logit contribution.

    q_logit: sum of build_q_components(...).values() -- i.e. logit(q) itself,
    since q_full is already constructed as sigmoid(that same sum). Added here
    with weight 1.0, consistent with the logit-additivity discipline already
    used inside the q-submodel -- no separate calibration weight invented.
    Defaults to 0.0 so any other caller of this function is unaffected.
    """
    a = ALPHA

    t = toggles  # shorthand

    # Tier 2: war payoffs + effective weights
    w     = (a["WinProbability"]        * t.get("WinProbability", 0)
           + a["WarCosts"]              * t.get("WarCosts", 0)
           + a["PatronDeterrence_w"]    * t.get("PatronDeterrence", 0)
           + a.get("NuclearDeterrence_expert", a["NuclearDeterrence"])
                                        * t.get("NuclearDeterrence", 0)
           + a.get("OperationalFeasibility_w", -1.50) * (1.0 - t.get("OperationalFeasibility", 0.5))
           + a.get("InitiatorSurvivalRisk_w",  -1.20) * t.get("InitiatorSurvivalRisk", 0.5)
           + a.get("PatronMoralHazard_w",       +0.60) * t.get("PatronMoralHazard", 0.0)
           + a.get("SubstitutionPath_w",        -1.10) * t.get("SubstitutionPath", 0.5))

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

    # Mach 3.1: Q0 (ICB crisis-conditioned) is sole anchor; peacetime intercept dropped.
    # SSPE structural deviations at 0.25 shrinkage (signs transport, magnitudes dont).
    SSPE_SHRINKAGE  = 0.25
    sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
    window_log_odds = q_logit + SSPE_SHRINKAGE * sspe_deviations

    p = 1 / (1 + math.exp(-window_log_odds))
    return round(p, 4)

# ─────────────────────────────────────────────────────────────────────
# BASELINE TOGGLES PER DYAD
# (loads from dyad_configs.json — falls back to neutral if missing)
# ─────────────────────────────────────────────────────────────────────

def load_dyad_suppressor_static(dyad):
    config_path = ROOT / "pipeline" / "dyad_configs.json"
    if config_path.exists():
        configs = json.loads(config_path.read_text())
        if dyad in configs and "suppressor_static" in configs[dyad]:
            return configs[dyad]["suppressor_static"]
    return {"OperationalFeasibility": 0.5, "InitiatorSurvivalRisk": 0.5, "SubstitutionPath": 0.5}

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
    call_a_correct    = score_nodes_call_a("US-Iran", articles_correct, snapshot)
    trigger_violent_c = call_a_correct.get("TriggerType", 0.0) >= 0.60
    call_b_correct    = score_nodes_call_b("US-Iran", articles_correct, snapshot, trigger_violent_c)
    scores_correct    = {**call_a_correct, **call_b_correct}

    # B: wrong headlines (China-Taiwan, July 2024 — wrong dyad, wrong time)
    wrong_date        = date(2024, 7, 15)
    articles_wrong    = fetch_gnews("China-Taiwan", wrong_date)
    call_a_wrong       = score_nodes_call_a("US-Iran", articles_wrong, snapshot)
    trigger_violent_w  = call_a_wrong.get("TriggerType", 0.0) >= 0.60
    call_b_wrong       = score_nodes_call_b("US-Iran", articles_wrong, snapshot, trigger_violent_w)
    scores_wrong       = {**call_a_wrong, **call_b_wrong}

    all_scored_fields = NODES + Q_PARENTS_ONSET_LLM + Q_PARENTS_LIVE

    print(f"\n  Snapshot date: {snapshot}")
    print(f"  Correct headlines ({len(articles_correct)}): US-Iran Nov 2025")
    print(f"  Wrong headlines   ({len(articles_wrong)}): China-Taiwan Jul 2024\n")
    print(f"  {'Node':<32} {'Correct':>8} {'Wrong':>8} {'Delta':>8}")
    print("  " + "-"*58)

    max_delta = 0
    for node in all_scored_fields:
        c = scores_correct.get(node, 0)
        w = scores_wrong.get(node, 0)
        d = abs(c - w)
        max_delta = max(max_delta, d)
        flag = " ← MOVES" if d > 0.2 else ""
        print(f"  {node:<32} {c:>8.2f} {w:>8.2f} {d:>8.2f}{flag}")

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


# Shrinkage vector: transports ICB crisis-conditioned q toward full dyad-year population
Q_SHRINKAGE = {
    'base':                           1.00,
    'LiveViolenceObserved':           0.90,
    'LiveUltimatumDeadline':          0.90,
    'OperationalPreparation':         0.80,
    'RoutineMilitaryPressure':         0.20,
    'MobilizationSignal':             0.70,
    'ThirdPartyMilitaryInvolvement':  0.20,
    'CommitmentProblem':              0.25,
    'TriggerType':                    0.08,
    'ValueThreatGravity':             0.06,
    'GeographicProximity':            0.00,
    'ProtractedConflict':             0.00,
    'LiveMediationAccepted':          0.15,
    'LiveAbatementSignal':            0.20,
}

HALF_LIFE_DAYS = {
    'LiveUltimatumDeadline':          2,
    'LiveMediationAccepted':          2,
    'LiveAbatementSignal':            5,
    'OperationalPreparation':         7,
    'RoutineMilitaryPressure':         14,
    'MobilizationSignal':             7,
    'LiveViolenceObserved':           10,
    'TriggerType':                    21,
    'ThirdPartyMilitaryInvolvement':  30,
    'ValueThreatGravity':             30,
    'CommitmentProblem':              30,
    'GeographicProximity':            None,
    'ProtractedConflict':             None,
    'base':                           None,
}
DECAY_FACTOR = {k: (0.5 ** (1.0/v) if v else 1.0)
                for k, v in HALF_LIFE_DAYS.items()}

# ── ICB Weibull transport (Patch 19) ─────────────────────────────────────────
ICB_TRANSPORT_RHO = 3.0

def _weibull_residual(A, D, scale=14.2, shape=0.65):
    import math
    FA  = 1 - math.exp(-((max(A, 0) / scale) ** shape))
    FAD = 1 - math.exp(-((max(A + D, 0) / scale) ** shape))
    denom = 1 - FA
    if denom < 1e-9:
        return 1.0
    return (FAD - FA) / denom

def _parse_date_str(s):
    if not s:
        return None
    from datetime import datetime as _dtt
    return _dtt.strptime(s, "%Y-%m-%d").date()

# ── end ICB transport helpers ─────────────────────────────────────────────────

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
        q_static   = load_dyad_q_static(dyad)
        suppressor_static = load_dyad_suppressor_static(dyad)
        baseline = {**baseline, **suppressor_static}
        # ICB transport: load full dyad config for onset/event dates
        _dcfg_path = ROOT / 'pipeline' / 'dyad_configs.json'
        _dcfg_all  = json.loads(_dcfg_path.read_text()) if _dcfg_path.exists() else {}
        _dyad_meta = _dcfg_all.get(dyad)

        print(f"  Sub-market: {sm['label']} | Resolution: {resolution} | "
              f"History: {len(sm['history'])} days")

        # 2. Run snapshots
        market_window = min(max(SNAPSHOT_OFFSETS), len(sm['history']))  # actual days in this market
        node_memory = {}  # decay memory — reset per dyad
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

            # Fetch headlines + score nodes (two-call structure, June 17 spec)
            articles = fetch_gnews(dyad, snapshot_date)
            call_a   = score_nodes_call_a(dyad, articles, snapshot_date)
            trigger_was_violent = call_a.get("TriggerType", 0.0) >= 0.60
            call_b   = score_nodes_call_b(dyad, articles, snapshot_date, trigger_was_violent)

            toggles  = apply_deltas(baseline, call_a)  # only NODES keys get applied; new fields ignored here

            # Q-submodel: compute logit(q) decomposition for this snapshot
            q_components = build_q_components(toggles, call_a, call_b, q_static)
            q_full        = q_with_subset(q_components)
            q_onset_only  = q_with_subset(q_components, ONSET_ONLY_KEYS)
            q_live_only   = q_with_subset(q_components, LIVE_ONLY_KEYS)

            # Mach 3 regime routing (June 18 2026):
            # Z_t=0 -> Mach 2 structural formula.
            # Z_t=1 -> q_full as primary probability (crisis reference class).
            # Z_t=2 -> Mach 2 stored but excluded from Brier in print_results.
            for node, today_val in q_components.items():
                hl = HALF_LIFE_DAYS.get(node)
                if hl is None:
                    node_memory[node] = today_val
                else:
                    decayed = node_memory.get(node, 0.0) * DECAY_FACTOR.get(node, 1.0)
                    node_memory[node] = max(today_val, decayed)
            q_logit  = sum(v * Q_SHRINKAGE.get(k, 0.50) for k, v in node_memory.items())
            z_t      = DYAD_REGIME.get(dyad, 0)
            # Mach 3.1 + ICB transport (Patch 19).
            engine_p_raw = predict_probability(toggles, days_remaining, q_logit=q_logit)
            # Horizon scaling on SSPE structural prior only.
            horizon_scale = max(days_remaining, 1) / market_window
            engine_p_scaled = 1 - (1 - engine_p_raw) ** horizon_scale
            engine_p_base = round(1 - engine_p_scaled, 4) if z_t == 2 else round(engine_p_scaled, 4)

            # ── ICB Weibull transport ──────────────────────────────────────
            import math as _math
            # Gate removed (Run 21): Weibull boost fires always.
            # Discrimination comes from suppressor cluster (structural) +
            # acute q node scores from LLM (semantic). If OP≈0 (Taiwan
            # chronic exercises), _acute_core≈0 → boost≈0 naturally.
            _acute_onset  = _parse_date_str(_dyad_meta.get('acute_phase_onset_date') if _dyad_meta else None)
            _event_date   = _parse_date_str(_dyad_meta.get('event_date') if _dyad_meta else None)
            _icb_boost = 0.0
            _clock = _acute_onset if (_acute_onset and snapshot_date >= _acute_onset) else snapshot_date
            _A = max((snapshot_date - _clock).days, 0)
            _F = _weibull_residual(_A, max(days_remaining, 0))
            _qc = q_components
            _acute_core = (
                _qc.get('OperationalPreparation', 0)
              + _qc.get('LiveViolenceObserved',   0)
              + _qc.get('LiveUltimatumDeadline',  0)
              + _qc.get('MobilizationSignal',     0)
            )
            _abatement  = abs(_qc.get('LiveAbatementSignal', 0))
            _live_boost = _F * max(0.0, _acute_core - _abatement)
            _icb_boost  = ICB_TRANSPORT_RHO * _live_boost
            _bl = _math.log(max(engine_p_base,1e-6)/max(1-engine_p_base,1e-6))
            engine_p = round(1/(1+_math.exp(-(_bl+_icb_boost))),4)
            # ── end ICB transport ──────────────────────────────────────────

            # Brier scores (resolved markets; Z_t=2 filtered in print_results)
            _post_res = bool(_event_date and snapshot_date >= _event_date)
            b_engine = None if _post_res else (
                (engine_p - resolution)**2 if resolution is not None else None
            )
            b_market = (mkt_price - resolution)**2 if resolution is not None else None

            row = {
                "market":        mkt["label"],
                "dyad":          dyad,
                "snapshot_date": snapshot_date.isoformat(),
                "days_remaining":days_remaining,
                "resolution":    resolution,
                "z_t":           z_t,
                "engine_p":      engine_p,
                "market_p":      mkt_price,
                "b_engine":      b_engine,
                "b_market":      b_market,
                "n_articles":    len(articles),
                "q_components":  q_components,
                "q_full":        round(q_full, 4),
                "icb_boost":     round(_icb_boost, 4),
                "post_res":      _post_res,
                "q_onset_only":  round(q_onset_only, 4),
                "q_live_only":   round(q_live_only, 4),
            }
            rows.append(row)

            res_str = str(resolution) if resolution is not None else "live"
            beat    = ""
            if b_engine is not None and b_market is not None:
                beat = "✓" if b_engine < b_market else "✗"
            print(f"  {beat} T-{offset:3d} ({snapshot_date}) | "
                  f"Engine: {engine_p:.1%} | Market: {mkt_price:.1%} | "
                  f"Res: {res_str} | Articles: {len(articles)}")

        # Checkpoint: save progress after each market finishes, so a crash
        # mid-run (e.g. a network timeout) doesn't lose everything back to
        # the start -- only loses whatever wasn't checkpointed yet.
        RESULTS_OUT.write_text(json.dumps(rows, indent=2))
        print(f"  [checkpoint] {len(rows)} rows saved → {RESULTS_OUT}")

    return rows

# ─────────────────────────────────────────────────────────────────────
# SCORING + OUTPUT
# ─────────────────────────────────────────────────────────────────────

def print_results(rows):
    all_resolved = [r for r in rows if r["resolution"] is not None]
    live         = [r for r in rows if r["resolution"] is None]
    resolved  = [r for r in all_resolved if r.get("z_t", 0) != 2]
    excluded2 = [r for r in all_resolved if r.get("z_t", 0) == 2]

    if not resolved:
        print("\nNo resolved markets to score yet.")
        return

    resolved_scored = [r for r in resolved if r["b_engine"] is not None]
    mean_b_engine = sum(r["b_engine"] for r in resolved_scored) / len(resolved_scored) if resolved_scored else float("nan")
    mean_b_market = sum(r["b_market"] for r in resolved) / len(resolved)
    wins = sum(1 for r in resolved_scored if r["b_engine"] < r["b_market"])

    print("\n" + "█"*60)
    print("  BACKTEST RESULTS — Mach 3.1 (unified formula, polarity flip)")
    print("█"*60)
    print(f"\n  Resolved rows:  {len(resolved)}  (Z_t=2 excluded: {len(excluded2)})")
    print(f"  Live rows:      {len(live)}")
    print(f"\n  Engine Brier:   {mean_b_engine:.4f}")
    print(f"  Market Brier:   {mean_b_market:.4f}")
    delta = mean_b_engine - mean_b_market
    sign  = "+" if delta > 0 else ""
    print(f"  Delta:          {sign}{delta:.4f}  "
          f"({'engine WORSE' if delta > 0 else 'engine BETTER'})")
    print(f"\n  Engine beats market: {wins}/{len(resolved)} snapshots")

    # By resolution
    yes_rows = [r for r in resolved if r["resolution"] == 1 and r["b_engine"] is not None]
    no_rows  = [r for r in resolved if r["resolution"] == 0 and r["b_engine"] is not None]
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
            offset_rows_scored = [r for r in offset_rows if r['b_engine'] is not None]
            if not offset_rows_scored: continue
            print(f"    T-{offset:3d}: Engine {sum(r['b_engine'] for r in offset_rows_scored)/len(offset_rows_scored):.4f} | "
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
