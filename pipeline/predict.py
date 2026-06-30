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
CLASSIFIED_FEED = "pipeline/classified_feed.json"
ALPHA_FILE      = "alpha/conflict_onset.json"

# ============================================================
# BACKTEST ENGINE IMPORTS — predict.py is a thin orchestration shell.
# All scoring logic lives in backtest.py (the calibrated engine).
# ─────────────────────────────────────────────────────────────────────
from pipeline.backtest import (
    predict_probability     as _predict_probability,
    score_nodes_call_a,
    score_nodes_call_b,
    build_q_components,
    q_with_subset,
    apply_deltas            as _apply_deltas,
    load_dyad_suppressor_static,
    load_dyad_baseline      as _load_dyad_baseline,
    ALPHA                   as _ALPHA,
    Q0,
    Q_SHRINKAGE,
    DYAD_REGIME,
    HALF_LIFE_DAYS,
    DECAY_FACTOR,
    _weibull_residual,
    _parse_date_str,
)

# ENGINE CONFIG
# ============================================================
BASE_RATE_ANNUAL = 0.03
ANTHROPIC_URL    = "https://api.anthropic.com/v1/messages"
GNEWS_URL        = "https://gnews.io/api/v4/search"

# ============================================================
# NODE CONFIG — v3 names
# ============================================================
NODES = [
    "WinProbability",
    "WarCosts",
    "PatronDeterrence",
    "NuclearDeterrence",
    "CommitmentProblem",
    "Patience",
    "DemocraticPeace",
    "PreferenceAlignment",
    "HardlineClaims",
    "AudienceCosts",
    "MobilizationSignal",
    "SubstitutionPath",
]

TOGGLE_RANGES = {
    "WinProbability":      (-2.0, 2.0),
    "WarCosts":            (-2.0, 2.0),
    "PatronDeterrence":    (0.0,  3.0),
    "NuclearDeterrence":   (0.0,  3.0),
    "CommitmentProblem":   (0.0,  2.0),
    "Patience":            (-2.0, 2.0),
    "DemocraticPeace":     (-2.0, 2.0),
    "PreferenceAlignment": (-2.0, 2.0),
    "HardlineClaims":      (0.0,  3.0),
    "SubstitutionPath":    (-3.0, 3.0),
    "AudienceCosts":       (0.0,  3.0),
    "MobilizationSignal":  (0.0,  2.0),
}

MAX_WEEKLY_DELTA = {n: 0.5 for n in NODES}

# ============================================================
# DYAD CONFIGS — loaded from pipeline/dyad_configs.json
# ============================================================
DYAD_CONFIGS_PATH = os.path.join(os.path.dirname(__file__), "dyad_configs.json")

FALLBACK_BASELINE = {
    "WinProbability":      0.0,
    "WarCosts":            0.0,
    "PatronDeterrence":    0.5,
    "NuclearDeterrence":   0.0,
    "CommitmentProblem":   0.5,
    "Patience":            0.0,
    "DemocraticPeace":     0.5,
    "PreferenceAlignment": -1.0,
    "HardlineClaims":      0.5,
    "AudienceCosts":       0.5,
    "MobilizationSignal":  0.0,
}


def load_dyad_configs():
    if os.path.exists(DYAD_CONFIGS_PATH):
        with open(DYAD_CONFIGS_PATH) as f:
            return json.load(f)
    return {}

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

Hierarchy: In a NORMAL week, ZERO nodes move. In an UNUSUAL week, ONE or TWO nodes move.

CRITICAL — DOUBLE-COUNTING GUARD:
Each nonzero delta must be justified by a DISTINCT evidence atom in the headlines.
A single headline can only justify ONE nonzero node delta.
If the same event would plausibly fire multiple nodes, score ONLY the most direct mechanism
and zero the others. Examples:
- "Deal signed" → PreferenceAlignment -0.5 only. NOT also CommitmentProblem and AudienceCosts.
- "Ceasefire violated, retaliatory strike" → CommitmentProblem +0.5 only. NOT also HardlineClaims.
- "Arms sale approved" → PatronDeterrence +0.5 only. NOT also WinProbability.
- "Mobilization order issued" → MobilizationSignal +0.5 only. NOT also WinProbability.
If in doubt about which node is primary, score the most structurally upstream node and zero the rest.

Return valid JSON only:
{"delta": -0.5 | 0 | 0.5, "event": "One sentence naming the specific event, or 'none'."}
"""

NODE_RUBRICS = {
    "WinProbability":      "Did a NEW concrete operational balance shift occur: deployment of forces, withdrawal, major arms delivery, or readiness change? +0.5 = initiator gains military advantage (carrier group deployed, force buildup). -0.5 = defender gains advantage (defensive fortifications, third-party military support to defender). Rhetoric does NOT count. NOTE: mobilization/call-up/conscription orders belong to MobilizationSignal, not here -- score generic troop deployment/presence here, score the act of activating reserves or issuing call-up orders under MobilizationSignal.",
    "WarCosts":            "Did a NEW concrete economic policy or enforcement action occur: sanctions imposed, embargo, blockade, seizure, tariff action, or restoration of trade ties? +0.5 = economic ties severed (raises war costs for initiator). -0.5 = new economic interdependence created.",
    "PatronDeterrence":    "Did a NEW patron commitment signal occur: explicit security guarantee reaffirmed, patron military assets moved to theater, patron issued credible deterrence statement, or patron withdrew support? +0.5 = patron visibly committed to defender (deters initiator). -0.5 = patron signal weakened or withdrawn.",
    "NuclearDeterrence":   "Did a NEW nuclear signal occur: nuclear test, new delivery system deployment, nuclear alert status change, or explicit nuclear threat? +0.5 = nuclear threat escalated. -0.5 = nuclear de-escalation. This should almost ALWAYS be 0.",
    "CommitmentProblem":   "Did a NEW event change the credibility or urgency of threats: public ultimatums, force deployments near the adversary, events that make today's deal harder to sustain tomorrow? +0.5 = commitment problem worsened. -0.5 = credible commitment mechanism created.",
    "MobilizationSignal":  "Did a NEW costly military mobilization signal occur, specifically: reserve call-up, conscription order, formal mobilization decree, military alert status escalation, or troop activation orders? This is DISTINCT from WinProbability (capability balance) and PatronDeterrence (alliance signaling) -- score this node ONLY for the act of mobilizing/activating forces, not for generic troop presence, deployment location, or base posture (those belong to WinProbability). +0.5 to +1.0 = clear mobilization order issued (the literature shows this predicts escalation risk, Levin-Banchik 2021). 0 = generic troop movement, exercises, or presence without a mobilization/call-up order -- the literature (Fuhrmann & Sechser 2014) finds this channel statistically null, do NOT score it as mobilization. Almost always 0 unless an explicit call-up/activation order is reported.",
    "Patience":            "Did a NEW domestic political instability event occur affecting leadership survival or time horizon: protests, coup signals, election shocks, elite rupture, or resignation risk? +0.5 = leadership under pressure, shorter time horizon. -0.5 = leadership consolidated, longer horizon.",
    "DemocraticPeace":     "Did a NEW major institutional rupture occur: coup, emergency rule, election cancellation, or constitutional suspension? This should almost ALWAYS be 0. +0.5 = democratic institutions weakened. -0.5 = democratic consolidation.",
    "PreferenceAlignment": "Did a NEW formal diplomatic alignment shift occur: signed agreement, ceasefire, truce, formal rupture, diplomatic recognition, coalition change, or explicit policy reversal? +0.5 = preferences diverged (rupture, breakdown, withdrawal from talks). -0.5 = preferences converged (ceasefire announced, deal signed, talks resumed, de-escalation agreement). IMPORTANT: a ceasefire or truce announcement — even fragile or partial — scores -0.5 here as a substitution path opening. A ceasefire violation that collapses the framework scores +0.5.",
    "HardlineClaims":      "Did a NEW operational flashpoint occur: strike, seizure, border clash, naval confrontation, airspace incident, or direct sovereignty challenge? +0.5 = new territorial/issue escalation. -0.5 = territorial/issue resolution or de-escalation. IMPORTANT: retaliatory strikes or exchanges that occur WITHIN an active ceasefire/truce framework score 0 here — the ceasefire framework itself is the dominant mechanism (PreferenceAlignment), not the individual exchange. Only score +0.5 if this represents a NEW escalation outside any existing framework.",
    "AudienceCosts":       "Did a NEW domestic political event raise the cost of backing down: nationalist mobilization, public commitment by leader, domestic pressure to act, or major protest demanding action? +0.5 = audience costs raised (harder to back down). -0.5 = domestic pressure reduced.",
    "SubstitutionPath":    "Did a NEW event open or close a viable off-ramp — a concrete mechanism by which the initiator can get what they want WITHOUT fighting? +0.5 = substitution path opened: ceasefire framework announced, interim deal reached, monitoring channel established, verified halt-attack commitment, mediator mechanism activated, asset-release or maritime reopening implementation begun. -0.5 = substitution path closed: talks formally collapsed, framework rejected, ultimatum issued with no negotiation offer, ceasefire formally abandoned, mediator quit. CRITICAL: mere talks scheduled, envoys meeting, or rhetorical calls for negotiations score 0 — cheap talk is NOT a substitution path. Only concrete implementation mechanisms qualify. Ongoing mechanisms already in place score 0 (not new). Score 0 if ambiguous.",
}

NODE_GATES = {
    "WinProbability":      ["deploy", "carrier", "troops", "base", "arms", "weapon", "forces", "readiness"],
    "PatronDeterrence":    ["guarantee", "commitment", "alliance", "patron", "support", "deterr", "deploy", "carrier", "arms sale", "arms package", "weapons sale", "security assistance", "military aid", "defense package"],
    "NuclearDeterrence":   ["nuclear", "missile", "warhead", "deterr", "test", "launch"],
    "PreferenceAlignment": ["agreement", "rupture", "recognition", "accord", "reversal", "withdraw", "signed", "ceasefire", "truce", "de-escalat", "talks", "negotiat", "deal"],
    "DemocraticPeace":     ["coup", "emergency", "cancel", "suspend", "constitutional"],
    "AudienceCosts":       ["protest", "nationalist", "rally", "domestic", "pressure", "demand"],
    "MobilizationSignal":  ["mobiliz", "call-up", "callup", "conscript", "reserve activ", "activate reserv", "alert status", "general mobilization"],
    "SubstitutionPath":    ["ceasefire", "peace talk", "halt attack", "halt fire", "stand down", "mediator", "deal framework", "talks collapsed", "talks failed", "ultimatum", "framework rejected", "de-escalat", "doha", "implementation", "monitoring channel", "diplomatic channel", "asset release", "maritime reopen"],
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
    # alpha/conflict_onset.json is nested: data["alpha"] contains node -> float
    alpha = {k: float(v) for k, v in data["alpha"].items()}
    # WinProbability = 0 from literature (sign cancellation) — expert prior
    alpha["WinProbability"] = 0.25
    # NuclearDeterrence expert prior (sparse literature)
    if not alpha.get("NuclearDeterrence"):
        alpha["NuclearDeterrence"] = -0.35
    # PatronDeterrence deterrence channel expert prior (Huth 1988)
    # The optimizer estimated near-zero because studies measure moral hazard not deterrence.
    # Override with theoretically grounded prior for the w-channel only.
    alpha["PatronDeterrence_w"] = -0.80
    return alpha


def predict_probability(toggles: Dict[str, float], days_remaining: int, alpha: Dict[str, float]) -> Dict[str, float]:
    # Mach 2 four-tier structured DAG formula
    # Tier 2: war payoff and effective weight
    w     = (alpha.get("WinProbability", 0.0) * toggles.get("WinProbability", 0.0)
           + alpha.get("WarCosts", 0.0)       * toggles.get("WarCosts", 0.0)
           + alpha.get("PatronDeterrence_w", alpha.get("PatronDeterrence", 0.0)) * toggles.get("PatronDeterrence", 0.0)
           + alpha.get("NuclearDeterrence", 0.0) * toggles.get("NuclearDeterrence", 0.0)
           + alpha.get("OperationalFeasibility_w", -1.50) * (1.0 - toggles.get("OperationalFeasibility", 0.5))
           + alpha.get("InitiatorSurvivalRisk_w",  -1.20) * toggles.get("InitiatorSurvivalRisk", 0.5)
           + alpha.get("PatronMoralHazard_w",       +0.60) * toggles.get("PatronMoralHazard", 0.0)
           + alpha.get("SubstitutionPath_w",        -1.10) * toggles.get("SubstitutionPath", 0.5))
    Omega = (alpha.get("CommitmentProblem", 0.0) * toggles.get("CommitmentProblem", 0.0)
           + alpha.get("Patience", 0.0)          * toggles.get("Patience", 0.0)
           + alpha.get("MobilizationSignal", 0.0) * toggles.get("MobilizationSignal", 0.0))
    # Tier 3: credibility-adjusted war value
    w_over_pi = w + alpha.get("DemocraticPeace", 0.0) * toggles.get("DemocraticPeace", 0.0)
    # Tier 4: WarPayoff and WarPolitics
    WarPayoff   = Omega + w_over_pi
    WarPolitics = (alpha.get("PreferenceAlignment", 0.0) * toggles.get("PreferenceAlignment", 0.0)
                 + alpha.get("HardlineClaims", 0.0)      * toggles.get("HardlineClaims", 0.0)
                 + alpha.get("AudienceCosts", 0.0)        * toggles.get("AudienceCosts", 0.0))
    # HardlineClaims direct channel (matches backtest.py)
    HardlineDirect = toggles.get("HardlineClaims", 0.0)

    # SSPE shrinkage — matches backtest.py Mach 3.1
    SSPE_SHRINKAGE  = 0.25
    sspe_deviations = WarPayoff + WarPolitics + HardlineDirect
    log_odds_shift  = SSPE_SHRINKAGE * sspe_deviations
    base_log_odds   = math.log(BASE_RATE_ANNUAL / (1 - BASE_RATE_ANNUAL))
    p_annual        = 1 / (1 + math.exp(-(base_log_odds + log_odds_shift)))
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
    cutoff = now
    start  = now - timedelta(days=3)

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
        "model":    "claude-sonnet-4-6",
        "max_tokens": 220,
        "temperature": 0,
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

    core = [m for m in markets if m.get("bucket") == "CORE" and not m.get("resolved")]
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

        dyad_configs = load_dyad_configs()
        config = dyad_configs.get(dyad)
        if config is None:
            print(f"  [warn] No config for '{dyad}' in dyad_configs.json — using fallback baseline.")

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
        today = datetime.now(timezone.utc).date()
        try:
            articles = score_nodes_call_a.__globals__["fetch_gnews"](dyad, today)
            print(f"  Articles: {len(articles)}")
        except Exception as ex:
            print(f"  [error] GNews failed: {ex}")
            articles = []

        # Two-call scoring — matches backtest.py exactly
        print(f"  Scoring nodes via Claude (call A: SSPE + onset)...")
        call_a = score_nodes_call_a(dyad, articles, today)
        trigger_was_violent = call_a.get("TriggerType", 0.0) >= 0.60
        print(f"  Scoring nodes via Claude (call B: live acute)...")
        call_b = score_nodes_call_b(dyad, articles, today, trigger_was_violent)

        # Apply SSPE deltas to baseline (call_a contains SSPE node deltas)
        suppressor_static = config.get("suppressor_static", {})
        baseline_with_suppressors = {**baseline, **suppressor_static}
        toggles = _apply_deltas(baseline_with_suppressors, call_a)

        # Build q_logit from node memory (no decay for daily pipeline — use today's values)
        q_static = config.get("q_static", {})
        q_components = build_q_components(toggles, call_a, call_b, q_static)
        node_memory = {}
        for node, val in q_components.items():
            hl = HALF_LIFE_DAYS.get(node)
            if hl is None:
                node_memory[node] = val
            else:
                node_memory[node] = val  # no decay on daily pipeline
        q_logit = sum(v * Q_SHRINKAGE.get(k, 0.50) for k, v in node_memory.items())

        print(f"  q_logit={q_logit:.3f} | TriggerType={call_a.get('TriggerType',0):.2f} | OP={call_b.get('OperationalPreparation',0):.2f} | LVO={call_b.get('LiveViolenceObserved',0):.2f}")
        print(f"  Toggles: {json.dumps({k: round(v,3) for k,v in toggles.items() if k in baseline})}") 

        try:
            from pipeline import context_keeper
            context_keeper.maybe_refresh_event_triggered(dyad, call_a, call_b, today)
        except Exception as ex:
            print(f"  [warn] context_keeper failed (non-fatal, predictions unaffected): {ex}")

        now_utc = datetime.now(timezone.utc).isoformat()

        # Weibull transport params from dyad config
        dyad_meta    = config
        acute_onset  = _parse_date_str(dyad_meta.get("acute_phase_onset_date"))
        event_date   = _parse_date_str(dyad_meta.get("event_date"))
        z_t          = DYAD_REGIME.get(dyad, 0)

        for m in dyad_markets:
            days_rem    = days_until(m.get("end_date", ""))
            market_window = max(days_rem, 1)

            # Use backtest's predict_probability with q_logit
            engine_p_raw = _predict_probability(toggles, days_rem, q_logit=q_logit)

            # ICB Weibull transport — matches backtest.py Run 21 exactly
            _clock = acute_onset if (acute_onset and today >= acute_onset) else today
            _A = max((today - _clock).days, 0)
            _F = _weibull_residual(_A, max(days_rem, 0))
            _acute_core = (
                q_components.get("OperationalPreparation", 0)
                + q_components.get("LiveViolenceObserved", 0)
                + q_components.get("LiveUltimatumDeadline", 0)
                + q_components.get("MobilizationSignal", 0)
            )
            _abatement  = abs(q_components.get("LiveAbatementSignal", 0))
            _live_boost = _F * max(0.0, _acute_core - _abatement)
            _icb_boost  = 3.0 * _live_boost  # ICB_TRANSPORT_RHO = 3.0

            # Apply boost in log-odds space (matches backtest.py exactly)
            import math as _math
            _post_res = bool(event_date and today >= event_date)
            if _post_res:
                _icb_boost = 0.0
            _bl = _math.log(max(engine_p_raw, 1e-6) / max(1 - engine_p_raw, 1e-6))
            engine_p_boosted = round(1 / (1 + _math.exp(-(_bl + _icb_boost))), 4)

            # Horizon scaling
            horizon_scale = max(days_rem, 1) / market_window
            engine_p_scaled = 1 - (1 - engine_p_boosted) ** horizon_scale
            engine_p_final = round(
                1 - engine_p_scaled if z_t == 2 else engine_p_scaled, 4
            )

            m["our_prediction"]  = engine_p_final
            m["prediction_at"]   = now_utc
            m["_toggles"]        = toggles
            m["_q_logit"]        = round(q_logit, 4)
            m["_icb_boost"]      = round(_icb_boost, 4)
            m["_acute_core"]     = round(_acute_core, 4)
            m["_z_t"]            = z_t

            edge = round((engine_p_final - (m.get("market_price") or 0)) * 100, 1)
            print(f"  ✓ {m['question'][:70]}")
            print(f"    engine={engine_p_final:.4f}  market={m.get('market_price',0):.3f}  edge={edge:+.1f}pp  days={days_rem}  boost={_icb_boost:.4f}")

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
