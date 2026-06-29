"""
pipeline/translator.py — The Translator Layer
Orchestrates Legal Scholar → Clergyman → Spyglass → Bettor
Sits between predict.py and the prediction logger.

Run after predict.py has written engine_p to classified_feed.json.

Usage:
    python3.11 pipeline/translator.py                # full run
    python3.11 pipeline/translator.py --scholar-only # classification pass only, no log append
"""

import json
import math
import os
import sys
import hashlib
import time
from datetime import datetime, timezone, date
from pathlib import Path
import urllib.request

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────

CLASSIFIED_FEED  = Path("pipeline/classified_feed.json")
TRANSLATOR_CACHE = Path("pipeline/translator_cache.json")
PREDICTIONS_LOG  = Path("predictions/log.jsonl")

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CLAUDE_MODEL      = "claude-sonnet-4-6"  # unified model string across pipeline
MAX_TOKENS        = 900
API_URL           = "https://api.anthropic.com/v1/messages"

SCHOLAR_ONLY      = "--scholar-only" in sys.argv

BLEND_WEIGHT_CAP  = 0.50
BANKROLL          = 500.0
KELLY_FRACTION    = 0.25

# Dyads that are not scoreable — skip entirely
UNSCORABLE_DYADS  = {
    None, "", "None", "unknown", "Unknown",
    "Russia-Unknown", "US-LatinAmerica",
}

# ─────────────────────────────────────────────────────────────────────
# HYGIENE FILTER
# ─────────────────────────────────────────────────────────────────────

def _is_expired(market: dict) -> bool:
    end = market.get("end_date", "")
    if not end:
        return False
    try:
        return date.fromisoformat(end[:10]) < date.today()
    except ValueError:
        return False


def _is_scoreable(market: dict) -> bool:
    """Hard gates before any Claude call."""
    if _is_expired(market):
        return False
    dyad = market.get("dyad") or ""
    if dyad in UNSCORABLE_DYADS:
        return False
    return True


# ─────────────────────────────────────────────────────────────────────
# UTILITIES
# ─────────────────────────────────────────────────────────────────────

def _claude_call(system_prompt: str, user_content: str) -> dict | None:
    """Single Claude API call. Returns parsed JSON dict or None on failure."""
    payload = json.dumps({
        "model": CLAUDE_MODEL,
        "max_tokens": MAX_TOKENS,
        "system": system_prompt,
        "messages": [{"role": "user", "content": user_content}]
    }).encode()

    req = urllib.request.Request(
        API_URL,
        data=payload,
        headers={
            "x-api-key": ANTHROPIC_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        },
        method="POST"
    )

    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read())
                text = body["content"][0]["text"].strip()
                # Strip markdown fences robustly
                if "```" in text:
                    parts = text.split("```")
                    for part in parts:
                        part = part.strip()
                        if part.startswith("json"):
                            part = part[4:].strip()
                        try:
                            return json.loads(part)
                        except Exception:
                            continue
                return json.loads(text)
        except json.JSONDecodeError as e:
            print(f"    [claude] JSON parse error attempt {attempt+1}: {e}")
        except Exception as e:
            print(f"    [claude] attempt {attempt+1} failed: {e}")
        time.sleep(2 ** attempt)
    return None


def _contract_hash(market: dict) -> str:
    text = (market.get("question") or "") + (market.get("description") or "")
    return hashlib.md5(text.encode()).hexdigest()[:12]


def _cache_key(market: dict) -> str:
    mid = market.get("market_id") or ""
    if mid:
        return mid
    # Fallback: hash of question text
    return "hash_" + hashlib.md5(
        (market.get("question") or "").encode()
    ).hexdigest()[:12]


def _load_cache() -> dict:
    if TRANSLATOR_CACHE.exists():
        try:
            return json.loads(TRANSLATOR_CACHE.read_text())
        except Exception:
            return {}
    return {}


def _save_cache(cache: dict):
    TRANSLATOR_CACHE.write_text(json.dumps(cache, indent=2))


def _polymarket_volume(market: dict) -> float:
    return float(market.get("volume") or 0.0)


def _liquidity_weight(volume_usd: float, max_volume: float = 50_000_000) -> float:
    if volume_usd <= 0 or max_volume <= 1:
        return 0.0
    return min(1.0, math.log(max(volume_usd, 1)) / math.log(max_volume))


# ─────────────────────────────────────────────────────────────────────
# DETERMINISTIC ROUTING
# ─────────────────────────────────────────────────────────────────────

def _derive_route(relation: str, confidence: str) -> str:
    """
    Ignore Claude's suggested translator_route.
    Derive deterministically from relation + confidence.
    """
    if relation == "equivalent" and confidence == "high":
        return "TRANSLATE"
    if relation == "subset" and confidence == "high":
        return "TRANSLATE"
    if relation == "unsupported":
        return "UNSUPPORTED"
    return "PASS_TRANSLATION"


# ─────────────────────────────────────────────────────────────────────
# LEGAL SCHOLAR
# ─────────────────────────────────────────────────────────────────────

LEGAL_SCHOLAR_SYSTEM = """You are the Legal Scholar module in a geopolitical prediction-market translator.

The engine estimates event A:
A = probability of interstate conflict onset, kinetic military action, or violent escalation involving the specified dyad within the relevant horizon.

Your job is NOT to estimate probabilities. Your job is to read the market contract and decide whether the contract's YES condition is the same probability object as A, a subset of A, the complement of A, an overlapping event, a termination/de-escalation event, unrelated, or unsupported.

Be conservative. If the market asks about peace, ceasefire, war ending, negotiations succeeding, territorial control, leader identity, sanctions only, elections, regime collapse, or vague political outcomes, do not treat it as a normal conflict-onset market.

IMPORTANT — what does NOT qualify as "equivalent":
- Boots on the ground specifically (that is subset)
- Airstrike on a named facility (that is subset)
- Naval blockade specifically (that is subset)
- Formal declaration of war (that is subset — declarations often lag or never accompany actual conflict)
- Conflict involving a DIFFERENT actor pair than the dyad specified (that is superset or overlap)
- "Regime survives" or "regime falls" questions (that is overlap or unrelated — regime change is not conflict onset)

Return ONLY valid JSON with these exact keys:
{
  "contract_type": "binary_onset|binary_peace|binary_threshold|count|leader_identity|territorial_control|negotiation_deal|termination|unsupported",
  "contract_polarity": "conflict|peace|status_quo|ambiguous",
  "relation_to_engine_event": "equivalent|subset|superset|complement|overlap|termination|unrelated|unsupported",
  "win_condition_summary": "one sentence in plain English describing exactly what must happen for YES",
  "legalese_flags": ["list any hyper-specific resolution conditions, thresholds, named actors, deadlines, exclusions, or ambiguity in the resolution criteria"],
  "confidence": "high|medium|low",
  "rationale": "one sentence explaining the classification"
}

Relation definitions:
- equivalent: contract YES condition is essentially conflict onset or kinetic military action by the dyad
- subset: YES is a narrower form of conflict onset (specific strike type, target, weapon, location, actor)
- superset: YES includes conflict onset but also includes other outcomes outside A
- complement: YES means no conflict/no strike/no invasion by the deadline
- overlap: contract concerns a bargaining outcome related to conflict risk but is not itself conflict onset (deals, concessions, negotiations)
- termination: contract asks whether an ongoing war ends, pauses, reaches ceasefire/peace deal, or de-escalates
- unrelated: engine has no direct probability-object traction
- unsupported: cannot be classified safely from the text

Note: "deal/no-deal" markets (Greenland, Panama, etc.) are overlap — the engine's conflict probability partially informs them but they are not onset markets."""


def legal_scholar(market: dict, dyad: str) -> dict | None:
    label       = market.get("label") or market.get("question") or ""
    question    = market.get("question") or label
    description = market.get("description") or ""
    res_source  = market.get("resolution_source") or ""
    deadline    = market.get("end_date") or "unknown"

    user_content = f"""Market title: {label}
Market question: {question}
Resolution criteria: {description[:600]}
Resolution source: {res_source[:200]}
Dyad: {dyad}
Deadline: {deadline}"""

    result = _claude_call(LEGAL_SCHOLAR_SYSTEM, user_content)
    if result:
        relation   = result.get("relation_to_engine_event", "unsupported")
        confidence = result.get("confidence", "low")
        route      = _derive_route(relation, confidence)
        result["translator_route"] = route  # overwrite Claude's suggestion
        print(f"    [scholar] {relation} | {route} | {confidence} | "
              f"{result.get('win_condition_summary','')[:60]}")
    return result


# ─────────────────────────────────────────────────────────────────────
# CLERGYMAN
# ─────────────────────────────────────────────────────────────────────

CLERGYMAN_SYSTEM = """You are the Clergyman module in a geopolitical prediction-market translator.

The engine estimates P(A) = probability of conflict onset between the specified dyad.
The Legal Scholar has determined the relation between contract event B and engine event A.

Your job: estimate two conditional probabilities using historical knowledge of this dyad's conflict patterns and base rates of this type of military action.

P(B|A)   = probability that, given conflict onset occurs, it takes the specific form in the contract
P(B|¬A)  = probability that, given NO conflict onset, the contract still resolves YES

For strict subsets: P(B|¬A) ≈ 0
For overlap/deal markets: both terms may be non-zero
For equivalent markets: P(B|A)=1.0, P(B|¬A)=0.0

The full formula is: P(B) = P(B|A)×P(A) + P(B|¬A)×(1−P(A))

Be honest. Return null for both if too uncertain to estimate reliably.

IMPORTANT: p_b_given_not_a must be expressed as a rate over a REFERENCE PERIOD.
Also output p_b_given_not_a_reference_days: the number of days your p_b_given_not_a estimate implicitly assumes.
Example: if you think Israel strikes Damascus ~35% of months, set p_b_given_not_a=0.35 and p_b_given_not_a_reference_days=30.
The Bettor will scale this to the actual contract window deterministically. Do NOT pre-scale it yourself.

Return ONLY valid JSON:
{
  "p_b_given_a": 0.75,
  "p_b_given_not_a": 0.05,
  "p_b_given_not_a_reference_days": 30,
  "confidence": "high|medium|low",
  "rationale": "one sentence"
}"""


def clergyman(market: dict, dyad: str, scholar_output: dict) -> dict | None:
    label    = market.get("label") or market.get("question") or ""
    relation = scholar_output.get("relation_to_engine_event", "subset")
    win_cond = scholar_output.get("win_condition_summary", "")
    flags    = scholar_output.get("legalese_flags", [])
    desc     = market.get("description", "")[:300]

    user_content = f"""Market: {label}
Dyad: {dyad}
Relation to engine event: {relation}
Win condition: {win_cond}
Resolution criteria excerpt: {desc}
Legalese flags: {'; '.join(flags) if flags else 'none'}"""

    result = _claude_call(CLERGYMAN_SYSTEM, user_content)
    if result:
        pba  = result.get("p_b_given_a")
        pbna = result.get("p_b_given_not_a")
        print(f"    [clergy] P(B|A)={pba} P(B|¬A)={pbna} conf={result.get('confidence')}")
    return result


# ─────────────────────────────────────────────────────────────────────
# SPYGLASS
# ─────────────────────────────────────────────────────────────────────

SPYGLASS_SYSTEM = """You are the Spyglass module in a geopolitical prediction-market translator.

Assess how reliably the market's resolution criterion will be publicly verifiable from open-source reporting (BBC, Reuters, AP, official statements) within a reasonable time after the event.

High: reported immediately and unambiguously by major wire services.
Medium: likely reported but may have delays, conflicting accounts, or threshold ambiguity.
Low: may not be reported, or reporting unreliable (e.g. North Korea casualty figures, covert ops).

Also assess resolution_risk: whether the contract might fail to resolve correctly even if the event occurs, due to legalese, threshold ambiguity, or Polymarket admin discretion.

Return ONLY valid JSON:
{
  "outcome_observability": "high|medium|low",
  "resolution_risk": "low|medium|high",
  "rationale": "one sentence"
}"""


def spyglass(market: dict, dyad: str, scholar_output: dict) -> dict | None:
    label    = market.get("label") or market.get("question") or ""
    win_cond = scholar_output.get("win_condition_summary", "")
    flags    = scholar_output.get("legalese_flags", [])

    user_content = f"""Market: {label}
Dyad: {dyad}
Win condition: {win_cond}
Legalese flags: {'; '.join(flags) if flags else 'none'}"""

    result = _claude_call(SPYGLASS_SYSTEM, user_content)
    if result:
        print(f"    [spyglass] observability={result.get('outcome_observability')} "
              f"resolution_risk={result.get('resolution_risk')}")
    return result


# ─────────────────────────────────────────────────────────────────────
# BETTOR
# ─────────────────────────────────────────────────────────────────────

def bettor(engine_p: float, market_p: float, volume_usd: float,
           scholar: dict, clergy: dict, glass: dict,
           days_remaining: float = 365.0) -> dict:
    """Pure math — no Claude call."""
    polarity        = scholar.get("contract_polarity", "conflict")
    p_b_given_a     = clergy.get("p_b_given_a")
    p_b_given_not_a_raw      = clergy.get("p_b_given_not_a")
    ref_days        = clergy.get("p_b_given_not_a_reference_days") or 365.0

    # Deterministic horizon scaling of P(B|¬A)
    # Converts from reference-period rate to contract-window rate
    p_b_given_not_a = None
    if p_b_given_not_a_raw is not None:
        if p_b_given_not_a_raw > 0.0:
            scale = min(days_remaining, ref_days) / ref_days
            p_b_given_not_a = round(
                1.0 - (1.0 - p_b_given_not_a_raw) ** scale, 6
            )
        else:
            p_b_given_not_a = 0.0

    # Flag if p_b_given_not_a_raw is suspiciously high (CGPT flag)
    if p_b_given_not_a_raw is not None and p_b_given_not_a_raw > 0.05:
        print(f"    [bettor] ⚠️  p_b_given_not_a_raw={p_b_given_not_a_raw} > 0.05 "
              f"(ref={ref_days}d → scaled={p_b_given_not_a})")
    observability   = glass.get("outcome_observability", "medium")
    resolution_risk = glass.get("resolution_risk", "medium")

    # Conditional probability — full two-term formula
    conditional_p = None
    if p_b_given_a is not None and p_b_given_not_a is not None:
        if polarity == "peace":
            ep_effective = 1 - engine_p
        else:
            ep_effective = engine_p
        conditional_p = round(
            ep_effective * p_b_given_a + (1 - ep_effective) * p_b_given_not_a, 4
        )

    # Blend weight
    fidelity_discount = 1.0 - (p_b_given_a or 1.0)
    liq_weight        = _liquidity_weight(volume_usd)
    blend_weight      = round(min(BLEND_WEIGHT_CAP, fidelity_discount * liq_weight), 4)

    # Blended p (logged, not published)
    blended_p = None
    if conditional_p is not None and market_p is not None:
        blended_p = round(
            conditional_p * (1 - blend_weight) + market_p * blend_weight, 4
        )

    # Kelly sizing — dampened by observability and resolution risk
    obs_mult  = {"high": 1.0, "medium": 0.5, "low": 0.0}.get(observability, 0.5)
    risk_mult = {"low": 1.0, "medium": 0.7, "high": 0.3}.get(resolution_risk, 0.7)
    kelly_fraction = 0.0
    bet_direction  = "PASS"

    if conditional_p is not None and market_p is not None:
        edge = conditional_p - market_p
        if abs(edge) > 0.02 and 0 < market_p < 1:
            if edge > 0:
                b = (1.0 / market_p) - 1.0
                raw_kelly = (conditional_p * b - (1 - conditional_p)) / b
            else:
                b = (1.0 / (1 - market_p)) - 1.0
                raw_kelly = ((1 - conditional_p) * b - conditional_p) / b
            raw_kelly      = max(0.0, raw_kelly)
            kelly_fraction = round(
                KELLY_FRACTION * raw_kelly * obs_mult * risk_mult, 4
            )
            if kelly_fraction > 0:
                bet_direction = "YES" if edge > 0 else "NO"

    kelly_dollars = round(kelly_fraction * BANKROLL, 2)

    print(f"    [bettor] conditional_p={conditional_p} blended_p={blended_p} "
          f"blend_weight={blend_weight} kelly=${kelly_dollars} dir={bet_direction}")

    return {
        "conditional_p":  conditional_p,
        "blended_p":      blended_p,
        "blend_weight":   blend_weight,
        "kelly_fraction": kelly_fraction,
        "kelly_dollars":  kelly_dollars,
        "bet_direction":  bet_direction,
        "observability":  observability,
        "resolution_risk": resolution_risk,
    }


# ─────────────────────────────────────────────────────────────────────
# ORCHESTRATOR
# ─────────────────────────────────────────────────────────────────────

def _pass_fields(market: dict, scholar: dict | None, reason: str) -> dict:
    """Populate all translator fields for a PASS/filtered market."""
    market.update({
        "translator_route":           "PASS_TRANSLATION",
        "translator_verdict":         reason,
        "relation_to_engine_event":   scholar.get("relation_to_engine_event") if scholar else None,
        "contract_type":              scholar.get("contract_type") if scholar else None,
        "contract_polarity":          scholar.get("contract_polarity") if scholar else None,
        "win_condition_summary":      scholar.get("win_condition_summary") if scholar else None,
        "legalese_flags":             scholar.get("legalese_flags", []) if scholar else [],
        "scholar_confidence":         scholar.get("confidence") if scholar else None,
        "scholar_rationale":          scholar.get("rationale") if scholar else None,
        "p_b_given_a":                None,
        "p_b_given_not_a":            None,
        "clergy_confidence":          None,
        "clergy_rationale":           None,
        "outcome_observability":      None,
        "resolution_risk":            None,
        "conditional_p":              None,
        "blended_p":                  None,
        "blend_weight":               None,
        "kelly_fraction":             0.0,
        "kelly_dollars":              0.0,
        "bet_direction":              "PASS",
    })
    return market


def translate_market(market: dict, cache: dict) -> dict:
    market_id = _cache_key(market)
    dyad      = market.get("dyad") or "unknown"
    engine_p  = market.get("our_prediction")
    market_p  = market.get("market_price")
    volume    = _polymarket_volume(market)
    chash     = _contract_hash(market)

    label = (market.get("label") or market.get("question") or "")[:60]
    print(f"\n  [{dyad}] {label}")

    # ── Hygiene filter ────────────────────────────────────────────────
    if not _is_scoreable(market):
        reason = "EXPIRED" if _is_expired(market) else "UNSCORABLE_DYAD"
        print(f"    [filter] {reason} — skipping")
        return _pass_fields(market, None, reason)

    # ── Cache check for static agent outputs ──────────────────────────
    cached    = cache.get(market_id, {})
    cache_hit = cached.get("contract_hash") == chash
    scholar   = cached.get("scholar") if cache_hit else None
    clergy    = cached.get("clergy")  if cache_hit else None
    glass     = cached.get("glass")   if cache_hit else None

    # ── Legal Scholar ─────────────────────────────────────────────────
    if scholar is None:
        scholar = legal_scholar(market, dyad)
        if scholar is None:
            print("    [scholar] FAILED")
            return _pass_fields(market, None, "SCHOLAR_ERROR")

    route = scholar.get("translator_route", "PASS_TRANSLATION")

    if route != "TRANSLATE":
        cache[market_id] = {"contract_hash": chash, "scholar": scholar,
                            "clergy": None, "glass": None}
        return _pass_fields(market, scholar, route)

    # ── Scholar-only mode: stop here ──────────────────────────────────
    if SCHOLAR_ONLY:
        cache[market_id] = {"contract_hash": chash, "scholar": scholar,
                            "clergy": None, "glass": None}
        market.update({
            "translator_route":         "TRANSLATE",
            "translator_verdict":       "SCHOLAR_ONLY",
            "relation_to_engine_event": scholar.get("relation_to_engine_event"),
            "contract_type":            scholar.get("contract_type"),
            "contract_polarity":        scholar.get("contract_polarity"),
            "win_condition_summary":    scholar.get("win_condition_summary"),
            "legalese_flags":           scholar.get("legalese_flags", []),
            "scholar_confidence":       scholar.get("confidence"),
            "scholar_rationale":        scholar.get("rationale"),
            "conditional_p":            None,
            "blended_p":                None,
            "blend_weight":             None,
            "kelly_fraction":           0.0,
            "kelly_dollars":            0.0,
            "bet_direction":            "PASS",
        })
        return market

    # ── Clergyman ─────────────────────────────────────────────────────
    if clergy is None:
        clergy = clergyman(market, dyad, scholar)
        if clergy is None:
            clergy = {"p_b_given_a": None, "p_b_given_not_a": None,
                      "confidence": "low", "rationale": "API failure"}

    # ── Spyglass ──────────────────────────────────────────────────────
    if glass is None:
        glass = spyglass(market, dyad, scholar)
        if glass is None:
            glass = {"outcome_observability": "medium",
                     "resolution_risk": "medium", "rationale": "API failure"}

    # ── Cache ─────────────────────────────────────────────────────────
    cache[market_id] = {"contract_hash": chash, "scholar": scholar,
                        "clergy": clergy, "glass": glass}

    # ── Bettor ────────────────────────────────────────────────────────
    if engine_p is None:
        print("    [bettor] no engine_p — PASS")
        bet = {"conditional_p": None, "blended_p": None, "blend_weight": None,
               "kelly_fraction": 0.0, "kelly_dollars": 0.0,
               "bet_direction": "PASS", "observability": None,
               "resolution_risk": None}
    else:
        # Compute days remaining for horizon scaling
        end_date_str = market.get("end_date", "")
        try:
            from datetime import date as _date
            end_dt = _date.fromisoformat(end_date_str[:10])
            days_remaining = max(1.0, float((end_dt - _date.today()).days))
        except Exception:
            days_remaining = 365.0

        bet = bettor(float(engine_p), float(market_p or 0),
                     volume, scholar, clergy, glass,
                     days_remaining=days_remaining)

    market.update({
        "translator_route":           "TRANSLATE",
        "translator_verdict":         "TRANSLATED",
        "relation_to_engine_event":   scholar.get("relation_to_engine_event"),
        "contract_type":              scholar.get("contract_type"),
        "contract_polarity":          scholar.get("contract_polarity"),
        "win_condition_summary":      scholar.get("win_condition_summary"),
        "legalese_flags":             scholar.get("legalese_flags", []),
        "scholar_confidence":         scholar.get("confidence"),
        "scholar_rationale":          scholar.get("rationale"),
        "p_b_given_a":                clergy.get("p_b_given_a"),
        "p_b_given_not_a":            clergy.get("p_b_given_not_a"),
        "clergy_confidence":          clergy.get("confidence"),
        "clergy_rationale":           clergy.get("rationale"),
        "outcome_observability":      bet.get("observability"),
        "resolution_risk":            bet.get("resolution_risk"),
        "conditional_p":              bet["conditional_p"],
        "blended_p":                  bet["blended_p"],
        "blend_weight":               bet["blend_weight"],
        "kelly_fraction":             bet["kelly_fraction"],
        "kelly_dollars":              bet["kelly_dollars"],
        "bet_direction":              bet["bet_direction"],
    })
    return market


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def run_translator():
    assert ANTHROPIC_API_KEY, "ANTHROPIC_API_KEY not set"

    feed  = json.loads(CLASSIFIED_FEED.read_text())
    cache = _load_cache()
    core  = [m for m in feed if m.get("bucket") == "CORE"]

    mode = "SCHOLAR-ONLY" if SCHOLAR_ONLY else "FULL"
    print(f"\nTranslator [{mode}]: {len(core)} CORE markets")
    print("=" * 60)

    translated = passed = filtered = errors = 0

    for market in core:
        try:
            enriched = translate_market(market, cache)
            verdict  = enriched.get("translator_verdict", "")
            if verdict == "TRANSLATED":
                translated += 1
            elif verdict == "SCHOLAR_ONLY":
                translated += 1  # counts as processed
            elif verdict in ("EXPIRED", "UNSCORABLE_DYAD"):
                filtered += 1
            elif "PASS" in verdict or "UNSUPPORTED" in verdict:
                passed += 1
            else:
                errors += 1
            # Write back
            for i, m in enumerate(feed):
                if (m.get("market_id") or m.get("question")) == \
                   (enriched.get("market_id") or enriched.get("question")):
                    feed[i] = enriched
                    break
        except Exception as e:
            print(f"    [error] {e}")
            errors += 1

        _save_cache(cache)

    CLASSIFIED_FEED.write_text(json.dumps(feed, indent=2))

    print(f"\n{'='*60}")
    print(f"  Processed: {translated} | Passed: {passed} | "
          f"Filtered: {filtered} | Errors: {errors}")
    print(f"  Wrote → {CLASSIFIED_FEED}")

    if not SCHOLAR_ONLY:
        _append_log(feed)


def _append_log(feed: list):
    """Append one entry per scored CORE market to predictions/log.jsonl."""
    PREDICTIONS_LOG.parent.mkdir(exist_ok=True)
    now = datetime.now(timezone.utc).isoformat()
    written = 0

    with open(PREDICTIONS_LOG, "a") as f:
        for market in feed:
            if market.get("bucket") != "CORE":
                continue
            if market.get("our_prediction") is None:
                continue
            entry = {
                "timestamp":                now,
                "market_id":                market.get("market_id"),
                "market_label":             market.get("label") or market.get("question"),
                "dyad":                     market.get("dyad"),
                "engine_p":                 market.get("our_prediction"),
                "market_p":                 market.get("market_price"),
                "volume_usd":               market.get("volume"),
                "conditional_p":            market.get("conditional_p"),
                "blended_p":                market.get("blended_p"),
                "blend_weight":             market.get("blend_weight"),
                "contract_polarity":        market.get("contract_polarity"),
                "contract_type":            market.get("contract_type"),
                "relation_to_engine_event": market.get("relation_to_engine_event"),
                "translator_route":         market.get("translator_route"),
                "translator_verdict":       market.get("translator_verdict"),
                "p_b_given_a":              market.get("p_b_given_a"),
                "p_b_given_not_a":          market.get("p_b_given_not_a"),
                "outcome_observability":    market.get("outcome_observability"),
                "resolution_risk":          market.get("resolution_risk"),
                "kelly_fraction":           market.get("kelly_fraction"),
                "kelly_dollars":            market.get("kelly_dollars"),
                "bet_direction":            market.get("bet_direction"),
                "win_condition_summary":    market.get("win_condition_summary"),
                "legalese_flags":           market.get("legalese_flags"),
            }
            f.write(json.dumps(entry) + "\n")
            written += 1

    print(f"  Appended {written} entries → {PREDICTIONS_LOG}")


if __name__ == "__main__":
    run_translator()
