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

sys.path.insert(0, os.path.dirname(__file__))
from clergyman_ontology import get_anchor_range, clamp_to_range, derive_severity_band, deterministic_position_within_range
import urllib.request
import re as _re
import calendar as _calendar

# ─────────────────────────────────────────────────────────────────────
# PROMPT VERSIONS
#
# The cache previously only invalidated on contract TEXT changes
# (question + description). It had no idea when we changed our own
# instructions to an agent. That meant the July 23 Clergyman two-axis
# ontology fix silently had zero effect on any market that was already
# cached before it shipped -- same market text, so "cache hit," so the
# stale pre-fix answer got reused forever.
#
# Bump the relevant *_PROMPT_VERSION any time that agent's system
# prompt changes. Old cache entries (which have no version field at
# all) will automatically miss on first read after this change ships,
# which is exactly what we want -- it forces a one-time re-score under
# the current prompt for everything already cached, retroactively
# applying whatever fix is live right now.
# ─────────────────────────────────────────────────────────────────────
LEGAL_SCHOLAR_PROMPT_VERSION = "v3"
CLERGYMAN_PROMPT_VERSION     = "v5"  # v5 = blend LLM guess with a deterministic position-within-range formula for kinetic contracts (LLM's raw number wasn't tracking WarCosts/WinProbability/PatronDeterrence/NuclearDeterrence despite correct rationale text -- was mostly narration, not real sensitivity) (Jul 27)
SPYGLASS_PROMPT_VERSION      = "v1"

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

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12
}

def _parse_deadline_from_question(question: str, scraped_date_hint: date = None):
    """
    Question text is the authoritative deadline source (endDate from Polymarket's
    Gamma API is unreliable for grouped/serial markets -- confirmed July 1-2, 2026).
    Returns a date, or None if unparseable.

    scraped_date_hint is used as a fallback anchor for year-less deadlines ("by
    July 21") only if today's real date is unavailable for some reason -- it is
    NOT the primary anchor. Using scraped_at as primary was a live bug (found
    2026-07-27): the weekly disciplinarian cadence means scraped_at can trail
    today by up to ~7 days, and if a year-less deadline falls in that gap, the
    old logic concluded "already past scraped_at, must mean next year" and
    silently rolled a genuinely-expired-6-days-ago market a full year into the
    future instead of flagging it as expired. Anchoring to today fixes this.
    """
    q = (question or "").lower().strip()
    _today = date.today()
    _anchor = max(scraped_date_hint, _today) if scraped_date_hint else _today

    m = _re.search(r'(?:by|in|on)\s+(\w+)\s+(\d{1,2}),?\s*(\d{4})', q)
    if m and m.group(1) in _MONTHS:
        try:
            return date(int(m.group(3)), _MONTHS[m.group(1)], int(m.group(2)))
        except ValueError:
            pass

    m = _re.search(r'before (\d{4})', q)
    if m:
        return date(int(m.group(1)) - 1, 12, 31)

    m = _re.search(r'(?:by end of|in) (\d{4})', q)
    if m:
        return date(int(m.group(1)), 12, 31)

    m = _re.search(r'by (\w+)\s+(\d{4})', q)
    if m and m.group(1) in _MONTHS:
        month, year = _MONTHS[m.group(1)], int(m.group(2))
        last_day = _calendar.monthrange(year, month)[1]
        return date(year, month, last_day)

    m = _re.search(r'by (\w+)\s+(\d{1,2})\??\s*$', q)
    if m and m.group(1) in _MONTHS:
        month, day = _MONTHS[m.group(1)], int(m.group(2))
        try:
            cand = date(_anchor.year, month, day)
        except ValueError:
            cand = None
        if cand is not None:
            # Only roll forward a year if the naive candidate is implausibly
            # stale (~10+ months in the past) -- that pattern only happens
            # near a real calendar year boundary (e.g. scraped late Dec,
            # deadline "Jan 5"). A candidate that's merely a few days past
            # the anchor almost certainly means the deadline just passed and
            # this market should be flagged expired, NOT silently pushed a
            # full year into the future (found live, 2026-07-27: "by July 21"
            # scraped July 24 was rolling to 2027-07-21 instead of correctly
            # reading as an already-expired 2026-07-21 market).
            if (_anchor - cand).days > 300:
                try:
                    cand = date(_anchor.year + 1, month, day)
                except ValueError:
                    pass
            return cand

    m = _re.search(r'by (\w+)\??\s*$', q)
    if m and m.group(1) in _MONTHS:
        month = _MONTHS[m.group(1)]
        last_day = _calendar.monthrange(_anchor.year, month)[1]
        cand = date(_anchor.year, month, last_day)
        if (_anchor - cand).days > 300:
            next_last_day = _calendar.monthrange(_anchor.year + 1, month)[1]
            cand = date(_anchor.year + 1, month, next_last_day)
        return cand

    return None


def _get_market_deadline(market: dict):
    """Returns (deadline_or_None, source_tag, mismatch_flag)."""
    question = market.get("question", "")
    end_raw  = (market.get("end_date") or "")[:10]

    scraped_hint = None
    scraped_at = market.get("scraped_at")
    if scraped_at:
        try:
            scraped_hint = datetime.fromisoformat(scraped_at.replace("Z", "+00:00")).date()
        except Exception:
            pass

    q_deadline = _parse_deadline_from_question(question, scraped_hint)

    end_deadline = None
    if end_raw:
        try:
            end_deadline = date.fromisoformat(end_raw)
        except ValueError:
            pass

    if q_deadline:
        mismatch = bool(end_deadline and end_deadline != q_deadline)
        if mismatch:
            print(f"    [DATE_MISMATCH] question says {q_deadline}, end_date says {end_deadline} — using question text")
        return q_deadline, "question_text", mismatch

    if end_deadline:
        print(f"    [DATE_MISMATCH_FALLBACK] unparseable question text, falling back to end_date={end_deadline} — UNVERIFIED")
        return end_deadline, "endDate_fallback", False

    return None, "unknown", False


def _is_expired(market: dict) -> bool:
    """Question text is authoritative; end_date is a cross-check only (see _get_market_deadline)."""
    deadline, _source, _mismatch = _get_market_deadline(market)
    if deadline is None:
        return False
    return deadline < date.today()


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
  "relation_confidence": "high|medium|low",
  "rationale": "one sentence explaining the classification"
}

relation_confidence reflects ONLY how sure you are that relation_to_engine_event is
correctly classified (equivalent/subset/superset/etc) -- NOT how clean, complete, or
truncated the resolution criteria text is. A contract can have messy or truncated
resolution language and still get HIGH relation_confidence if the core win condition
is clearly a subset/equivalent/etc of interstate conflict onset. Text-quality issues
(truncation, ambiguous exclusions, unclear thresholds) belong ONLY in legalese_flags --
never let them lower relation_confidence.

high: the relation type is clear and would not change even with the full untruncated text
medium: you can rule out most relation types but there's a plausible alternative reading
low: you genuinely cannot tell which relation type applies

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
Resolution criteria: {description[:4000]}
Resolution source: {res_source[:200]}
Dyad: {dyad}
Deadline: {deadline}"""

    result = _claude_call(LEGAL_SCHOLAR_SYSTEM, user_content)
    if result:
        relation   = result.get("relation_to_engine_event", "unsupported")
        confidence = result.get("relation_confidence", "low")
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

Your job has two parts:

PART 1 -- CLASSIFY the contract onto two axes (deterministic code will use these
to assign a probability range; you do NOT set the range yourself):

manifestation_family: one of
  - "political_act": the contract resolves on an announcement, declaration,
    authorization, or other political/speech act -- NOT a physical operation.
    E.g. "will X announce a blockade" is political_act even though "blockade"
    appears in the text. Do not treat this as a weak version of the physical
    event -- it is a different event family with its own base rate.
  - "kinetic_or_coercive_action": the contract resolves on an actual physical
    military action occurring.

If manifestation_family is "political_act", ALSO classify political_act_formality:
  - "formal_official": a government body or official acting in their OFFICIAL
    CAPACITY makes a binding or quasi-binding statement -- e.g. State
    Department or Defense Department statement, presidential executive order
    or proclamation, formal Congressional authorization, official military
    command announcement. These carry real audience costs: a government that
    formally announces something and does not follow through pays a
    credibility price (domestically and internationally), so a formal
    announcement is meaningful signal, NOT cheap talk. It can still occur via
    brinkmanship, deterrent signaling, or contingency authorization without
    actual conflict onset, but it is closer to a costly signal than to noise.
  - "informal_rhetorical": an offhand remark, a social media post, a campaign
    or rally statement, or a single official's personal opinion not issued
    through official channels or not representing settled policy. This IS
    cheap talk -- low cost to say, easy to walk back, minimal binding force.
  Use null only if manifestation_family is "kinetic_or_coercive_action".

requirement_burden: one of, in order of INCREASING restrictiveness (each tier
adds a necessary condition beyond the previous, which can only hold or lower
the true probability, never raise it):
  - "broad": any qualifying action in a wide category satisfies this (e.g.
    "any US military action against Iran")
  - "method_specific": a particular method/action type is named (e.g.
    "a naval blockade", "an airstrike") but no specific target or duration
  - "target_specific": a particular target, location, or actor is named
    (e.g. "a strike on Fordow", "action in Damascus specifically")
  - "persistent": the contract requires the action to be SUSTAINED over time,
    not a single instance (e.g. "a blockade lasting 7+ days")
  - "territorial_control": the contract requires establishing or holding
    territory, the most restrictive tier (e.g. "invade AND hold territory")

Also record action_type (reuse this dyad\'s known action_type categories:
gray_zone_incident, missile_strike, raid, seizure_boarding, airstrike,
naval_blockade, ground_invasion) if the contract\'s method is physical and
identifiable -- null if manifestation_family is political_act or the method
is unspecified.

PART 2 -- ESTIMATE, using historical knowledge of this dyad\'s conflict patterns:

P(B|A)   = probability that, given conflict onset occurs, it takes the specific
           form in the contract. Reason using conjunctive logic: each additional
           requirement (method, target, duration, territorial control) can only
           hold this probability flat or lower it relative to a broader
           contract on the same dyad -- never raise it. A blockade is MORE
           dramatic than a single airstrike but requires persistence and
           geographic coverage, which makes it LESS likely given conflict
           occurs, not more -- severity and conditional probability are
           different axes, do not conflate them.
P(B|¬A)  = probability that, given NO conflict onset, the contract still resolves YES

For strict subsets, P(B|¬A) depends on manifestation_family -- do NOT apply a
single blanket rule:
  - kinetic_or_coercive_action subsets: P(B|¬A) ≈ 0. A specific physical
    action (a strike, a blockade actually being enforced) cannot occur
    without some form of conflict onset already having happened.
  - political_act subsets, formal_official: P(B|¬A) is NOT ≈0. A formal
    government announcement/authorization can happen through brinkmanship,
    deterrent posturing, or contingency planning even when no conflict onset
    occurs -- it is a real, non-trivial event on its own base rate. Estimate
    P(B|¬A) from how often this dyad's government has issued this specific
    TYPE of formal statement absent an actual onset. Do not default to 0.
  - political_act subsets, informal_rhetorical: closer to the old assumption
    of low, but still estimate a real (not automatically zero) base rate --
    rhetoric of this kind still has a frequency, it is just cheaper and less
    predictive than a formal statement.
For overlap/deal markets: both terms may be non-zero
For equivalent markets: P(B|A)=1.0, P(B|¬A)=0.0

The full formula is: P(B) = P(B|A)×P(A) + P(B|¬A)×(1−P(A))

Be honest. Return null for both if too uncertain to estimate reliably.

PART 3 -- USE REAL STRUCTURAL CONTEXT WHEN AVAILABLE (Option B, 2026-07-27):

If a STRUCTURAL CONTEXT block is provided below, it contains this specific
dyad's actual Mach 2 primitive values -- not generic historical pattern-
matching, the real computed state of THIS relationship today. Use it to
decide WHERE within your assigned anchor range to land, the same way a real
analyst would condition on the belligerents' actual capabilities and
constraints rather than a generic base rate. You still do NOT get to move
outside the range the deterministic ontology assigned you -- this only
changes your positioning within it, and your rationale must name which
specific primitive(s) moved you and in which direction.

General reasoning patterns (not rigid rules -- reason like an analyst, not
a lookup table):
- WarCosts very negative (high cost of war) + a "persistent" or
  "territorial_control" tier contract (sustained/costly options: blockade,
  invasion) -> lean toward the LOW end of your range. The structural cost
  of sustaining that specific option is real and should suppress it.
- WarCosts near zero or positive (cheap war) -> less reason to suppress
  costly-tier options; can sit higher in the range if other signals support it.
- WinProbability strongly favorable (decisive capability edge) -> a swift,
  decisive form of the contract's named action becomes relatively more
  plausible; lean higher within the range for that specific action type.
  WinProbability unfavorable -> lean lower, especially for anything requiring
  sustained commitment.
- NuclearDeterrence high -> large-scale/sustained kinetic options
  (persistent, territorial_control tiers) become LESS plausible (nuclear
  deterrence suppresses escalation to that level) -- lean toward the low end
  for those tiers specifically. This can push political_act contracts the
  OTHER way (toward the high end) since limited signaling substitutes for
  action that's structurally deterred.
- PatronDeterrence high for the TARGET of the contract's action -> the
  named action becomes less plausible (a committed external patron raises
  the cost/risk of escalating against their client) -- lean lower.
- AudienceCosts high -> a leader who has publicly committed faces real
  pressure to follow through visibly; this can support leaning higher for
  formal_official political-act contracts specifically (the credibility
  cost of an empty formal announcement is higher, so formal announcements
  become more informative/likely when domestic audience costs are already
  elevated), independent of the kinetic-tier effects above.

If no STRUCTURAL CONTEXT block is provided (older cached markets, or a dyad
without toggle data yet), fall back to PART 2's historical-pattern reasoning
alone -- do not invent numbers.

IMPORTANT: p_b_given_not_a must be expressed as a rate over a REFERENCE PERIOD.
Also output p_b_given_not_a_reference_days: the number of days your p_b_given_not_a estimate implicitly assumes.
Example: if you think Israel strikes Damascus ~35% of months, set p_b_given_not_a=0.35 and p_b_given_not_a_reference_days=30.
The Bettor will scale this to the actual contract window deterministically. Do NOT pre-scale it yourself.

Return ONLY valid JSON:
{
  "manifestation_family": "political_act|kinetic_or_coercive_action",
  "political_act_formality": "formal_official|informal_rhetorical (omit or use JSON null if manifestation_family is kinetic_or_coercive_action)",
  "requirement_burden": "broad|method_specific|target_specific|persistent|territorial_control",
  "action_type": "one of the 7 categories, or null",
  "p_b_given_a": 0.75,
  "p_b_given_not_a": 0.05,
  "p_b_given_not_a_reference_days": 30,
  "confidence": "high|medium|low",
  "used_structural_context": true,
  "rationale": "one sentence -- must name which requirement_burden modifiers drove your estimate, AND which structural primitive(s) if a STRUCTURAL CONTEXT block was provided"
}"""


def _format_structural_context(toggles: dict) -> str:
    """Formats the subset of Mach 2 structural primitives relevant to
    instrument-choice reasoning (Option B) into a labeled block for the
    Clergyman prompt. Returns "" if toggles is empty/missing so callers can
    cleanly omit the whole block rather than send an empty section header.
    """
    if not toggles:
        return ""

    relevant = ["WinProbability", "WarCosts", "PatronDeterrence",
                "NuclearDeterrence", "AudienceCosts"]
    present = {k: toggles.get(k) for k in relevant if toggles.get(k) is not None}
    if not present:
        return ""

    lines = [
        "STRUCTURAL CONTEXT (this dyad's real current Mach 2 primitive values, "
        "not generic history -- see PART 3 for how to use these):",
    ]
    legend = {
        "WinProbability":   "positive = challenger capability advantage, negative = disadvantage",
        "WarCosts":         "negative = HIGH cost of war (peace-inducing), positive = low cost",
        "PatronDeterrence": "0-3, higher = stronger external patron commitment to the target",
        "NuclearDeterrence": "0-3, higher = stronger mutual nuclear deterrence constraint",
        "AudienceCosts":    "0-3, higher = more domestic political lock-in on leaders",
    }
    for k, v in present.items():
        lines.append(f"  {k} = {v}  ({legend[k]})")
    return "\n".join(lines)


def clergyman(market: dict, dyad: str, scholar_output: dict) -> dict | None:
    label    = market.get("label") or market.get("question") or ""
    relation = scholar_output.get("relation_to_engine_event", "subset")
    win_cond = scholar_output.get("win_condition_summary", "")
    flags    = scholar_output.get("legalese_flags", [])
    desc     = market.get("description", "")[:300]
    structural_block = _format_structural_context(market.get("_toggles", {}))

    user_content = f"""Market: {label}
Dyad: {dyad}
Relation to engine event: {relation}
Win condition: {win_cond}
Resolution criteria excerpt: {desc}
Legalese flags: {'; '.join(flags) if flags else 'none'}"""
    if structural_block:
        user_content += f"\n\n{structural_block}"

    result = _claude_call(CLERGYMAN_SYSTEM, user_content)
    if result:
        result["used_structural_context"] = bool(structural_block)
        # Claude sometimes returns the JSON string "null" (in quotes) instead
        # of a bare JSON null for political_act_formality on kinetic markets,
        # per the schema's "formal_official|informal_rhetorical|null" hint --
        # that's valid on Claude's end (it's following the literal string in
        # the schema) but Python parses '"null"' as the truthy string "null",
        # not None. Normalize here, once, before anything downstream reads it
        # (the debug print, the log write, and any future consumer).
        if result.get("political_act_formality") in ("null", "None", ""):
            result["political_act_formality"] = None

        manifestation_family = result.get("manifestation_family", "kinetic_or_coercive_action")
        requirement_burden   = result.get("requirement_burden", "broad")
        raw_pba               = result.get("p_b_given_a")
        toggles_for_position  = market.get("_toggles", {})
        war_costs_for_range   = toggles_for_position.get("WarCosts")

        try:
            anchor_range = get_anchor_range(manifestation_family, requirement_burden,
                                             war_costs=war_costs_for_range)
            clamped_pba, was_clamped = clamp_to_range(raw_pba, anchor_range)
        except ValueError as e:
            print(f"    [clergy] ⚠️  ontology error: {e} -- using raw value unclamped")
            anchor_range, clamped_pba, was_clamped = None, raw_pba, False

        # Blend LLM judgment with a deterministic position estimate for
        # kinetic contracts (2026-07-27 finding: Clergyman's raw guess was
        # nearly identical -- 0.06 both times -- across a WarCosts=-1.8 vs
        # +1.5 swing, even though its rationale correctly described the
        # right direction in words. The deterministic range-shift was doing
        # all the real work; the LLM's point estimate wasn't tracking the
        # data. Fix: don't rely on the LLM's raw number as the primary
        # driver of WHERE within the range to sit -- compute that
        # deterministically from WinProbability/PatronDeterrence/
        # NuclearDeterrence too, and let the LLM's guess be a minority
        # input (tie-breaker / sanity check), not the main signal.
        # Political-act contracts are NOT blended -- no deterministic
        # position formula has been built for that family, left to the LLM
        # as before; scope discipline, not an oversight.
        LLM_BLEND_WEIGHT = 0.3
        deterministic_pba = None
        if (manifestation_family == "kinetic_or_coercive_action"
                and anchor_range is not None and clamped_pba is not None):
            deterministic_pba = deterministic_position_within_range(
                toggles_for_position, anchor_range, requirement_burden
            )
            blended_pba = round(
                LLM_BLEND_WEIGHT * clamped_pba
                + (1 - LLM_BLEND_WEIGHT) * deterministic_pba,
                4,
            )
        else:
            blended_pba = clamped_pba

        result["p_b_given_a_raw"]      = raw_pba
        result["p_b_given_a_llm_clamped"] = clamped_pba
        result["p_b_given_a_deterministic"] = deterministic_pba
        result["p_b_given_a"]          = blended_pba
        result["anchor_range"]         = list(anchor_range) if anchor_range else None
        result["was_clamped"]          = was_clamped
        result["war_costs_used_for_range"] = war_costs_for_range
        result["severity_band"]        = derive_severity_band(result.get("action_type"))

        pba  = result.get("p_b_given_a")
        pbna = result.get("p_b_given_not_a")
        formality = result.get("political_act_formality")
        formality_note = f"/{formality}" if formality else ""
        range_note = f" range={anchor_range}" if war_costs_for_range is not None else ""
        clamp_note = f" [CLAMPED from {raw_pba}]" if was_clamped else ""
        blend_note = (f" [llm={result.get('p_b_given_a_llm_clamped')} "
                      f"det={result.get('p_b_given_a_deterministic')} -> blended]"
                      if deterministic_pba is not None else "")
        print(f"    [clergy] {manifestation_family}{formality_note}/{requirement_burden}{range_note} "
              f"P(B|A)={pba}{clamp_note}{blend_note} P(B|¬A)={pbna} conf={result.get('confidence')}")
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

    # Kelly sizing — dampened by observability, resolution risk, and now
    # Clergyman's own confidence + whether its raw guess had to be clamped
    # into the deterministic anchor range.
    #
    # Rationale (Adi, 2026-07-27): Kelly previously only looked at the SIZE
    # of the edge (conditional_p vs market_p), with zero awareness of how
    # confident Clergyman actually was when it produced conditional_p. A
    # big edge built on a "confidence: low" guess is not the same bet as
    # the same-sized edge built on a "confidence: high" guess -- the first
    # is a real risk of betting real money behind a shaky number that only
    # LOOKS strong on paper. was_clamped is a second, related signal: it
    # means Clergyman's own freehand estimate disagreed with the calibrated
    # range enough to need correcting, which is itself evidence the raw
    # judgment wasn't especially reliable, independent of the stated
    # confidence label.
    obs_mult  = {"high": 1.0, "medium": 0.5, "low": 0.0}.get(observability, 0.5)
    risk_mult = {"low": 1.0, "medium": 0.7, "high": 0.3}.get(resolution_risk, 0.7)
    clergy_confidence = clergy.get("confidence", "medium")
    clergy_conf_mult  = {"high": 1.0, "medium": 0.6, "low": 0.25}.get(clergy_confidence, 0.5)
    was_clamped       = bool(clergy.get("was_clamped"))
    clamp_mult        = 0.75 if was_clamped else 1.0
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
                KELLY_FRACTION * raw_kelly * obs_mult * risk_mult
                * clergy_conf_mult * clamp_mult, 4
            )
            if kelly_fraction > 0:
                bet_direction = "YES" if edge > 0 else "NO"

    kelly_dollars = round(kelly_fraction * BANKROLL, 2)

    clamp_note = " [clamped]" if was_clamped else ""
    print(f"    [bettor] conditional_p={conditional_p} blended_p={blended_p} "
          f"blend_weight={blend_weight} clergy_conf={clergy_confidence}{clamp_note} "
          f"kelly=${kelly_dollars} dir={bet_direction}")

    return {
        "conditional_p":  conditional_p,
        "blended_p":      blended_p,
        "blend_weight":   blend_weight,
        "kelly_fraction": kelly_fraction,
        "kelly_dollars":  kelly_dollars,
        "bet_direction":  bet_direction,
        "observability":  observability,
        "resolution_risk": resolution_risk,
        "clergy_confidence_mult": clergy_conf_mult,
        "clergy_was_clamped":     was_clamped,
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
        "scholar_confidence":         scholar.get("relation_confidence") if scholar else None,
        "scholar_rationale":          scholar.get("rationale") if scholar else None,
        "p_b_given_a":                None,
        "p_b_given_a_raw":            None,
        "p_b_given_not_a":            None,
        "manifestation_family":       None,
        "political_act_formality":    None,
        "used_structural_context":    None,
        "requirement_burden":         None,
        "severity_band":              None,
        "anchor_range":               None,
        "was_clamped":                None,
        "war_costs_used_for_range":   None,
        "p_b_given_a_llm_clamped":    None,
        "p_b_given_a_deterministic":  None,
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
    # Per-agent: text match AND prompt-version match, independently.
    # A Clergyman-only prompt bump re-scores Clergyman without wasting
    # a Scholar/Spyglass call that's still valid under its own version.
    cached      = cache.get(market_id, {})
    text_match  = cached.get("contract_hash") == chash
    scholar_hit = text_match and cached.get("scholar_version") == LEGAL_SCHOLAR_PROMPT_VERSION
    clergy_hit  = text_match and cached.get("clergy_version")  == CLERGYMAN_PROMPT_VERSION
    glass_hit   = text_match and cached.get("glass_version")   == SPYGLASS_PROMPT_VERSION
    scholar   = cached.get("scholar") if scholar_hit else None
    clergy    = cached.get("clergy")  if clergy_hit  else None
    glass     = cached.get("glass")   if glass_hit   else None

    # ── Legal Scholar ─────────────────────────────────────────────────
    if scholar is None:
        scholar = legal_scholar(market, dyad)
        if scholar is None:
            print("    [scholar] FAILED")
            return _pass_fields(market, None, "SCHOLAR_ERROR")

    route = scholar.get("translator_route", "PASS_TRANSLATION")

    if route != "TRANSLATE":
        print(f"    [filter] {route} -- skipping")
        cache[market_id] = {"contract_hash": chash,
                            "scholar": scholar, "scholar_version": LEGAL_SCHOLAR_PROMPT_VERSION,
                            "clergy": None, "clergy_version": None,
                            "glass": None, "glass_version": None}
        return _pass_fields(market, scholar, route)

    # ── Scholar-only mode: stop here ──────────────────────────────────
    if SCHOLAR_ONLY:
        cache[market_id] = {"contract_hash": chash,
                            "scholar": scholar, "scholar_version": LEGAL_SCHOLAR_PROMPT_VERSION,
                            "clergy": None, "clergy_version": None,
                            "glass": None, "glass_version": None}
        market.update({
            "translator_route":         "TRANSLATE",
            "translator_verdict":       "SCHOLAR_ONLY",
            "relation_to_engine_event": scholar.get("relation_to_engine_event"),
            "contract_type":            scholar.get("contract_type"),
            "contract_polarity":        scholar.get("contract_polarity"),
            "win_condition_summary":    scholar.get("win_condition_summary"),
            "legalese_flags":           scholar.get("legalese_flags", []),
            "scholar_confidence":       scholar.get("relation_confidence"),
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
    cache[market_id] = {"contract_hash": chash,
                        "scholar": scholar, "scholar_version": LEGAL_SCHOLAR_PROMPT_VERSION,
                        "clergy": clergy, "clergy_version": CLERGYMAN_PROMPT_VERSION,
                        "glass": glass, "glass_version": SPYGLASS_PROMPT_VERSION}

    # ── Bettor ────────────────────────────────────────────────────────
    if engine_p is None:
        print("    [bettor] no engine_p — PASS")
        bet = {"conditional_p": None, "blended_p": None, "blend_weight": None,
               "kelly_fraction": 0.0, "kelly_dollars": 0.0,
               "bet_direction": "PASS", "observability": None,
               "resolution_risk": None}
    else:
        # Compute days remaining for horizon scaling. Was reading end_date
        # directly (same bug as predict.py's days_rem -- fixed 2026-07-27):
        # route through _get_market_deadline() instead, since that's the
        # whole reason this function exists and it was previously only
        # wired into the boolean _is_expired() gate, not here.
        _deadline, _deadline_source, _deadline_mismatch = _get_market_deadline(market)
        if _deadline is not None:
            days_remaining = max(1.0, float((_deadline - date.today()).days))
        else:
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
        "scholar_confidence":         scholar.get("relation_confidence"),
        "scholar_rationale":          scholar.get("rationale"),
        "p_b_given_a":                clergy.get("p_b_given_a"),
        "p_b_given_a_raw":            clergy.get("p_b_given_a_raw"),
        "p_b_given_not_a":            clergy.get("p_b_given_not_a"),
        "manifestation_family":       clergy.get("manifestation_family"),
        "political_act_formality":    clergy.get("political_act_formality"),
        "used_structural_context":    clergy.get("used_structural_context"),
        "requirement_burden":         clergy.get("requirement_burden"),
        "severity_band":              clergy.get("severity_band"),
        "anchor_range":               clergy.get("anchor_range"),
        "was_clamped":                clergy.get("was_clamped"),
        "war_costs_used_for_range":   clergy.get("war_costs_used_for_range"),
        "p_b_given_a_llm_clamped":    clergy.get("p_b_given_a_llm_clamped"),
        "p_b_given_a_deterministic":  clergy.get("p_b_given_a_deterministic"),
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
        "kelly_clergy_confidence_mult": bet.get("clergy_confidence_mult"),
    })
    return market


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def run_translator():
    assert ANTHROPIC_API_KEY, "ANTHROPIC_API_KEY not set"

    feed  = json.loads(CLASSIFIED_FEED.read_text())
    cache = _load_cache()
    core  = [m for m in feed if m.get("bucket") == "CORE" and not m.get("resolved")]

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
            if market.get("resolved"):
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
                "p_b_given_a_raw":          market.get("p_b_given_a_raw"),
                "p_b_given_not_a":          market.get("p_b_given_not_a"),
                "manifestation_family":     market.get("manifestation_family"),
                "political_act_formality":  market.get("political_act_formality"),
                "used_structural_context":  market.get("used_structural_context"),
                "requirement_burden":       market.get("requirement_burden"),
                "severity_band":            market.get("severity_band"),
                "anchor_range":             market.get("anchor_range"),
                "was_clamped":              market.get("was_clamped"),
                "war_costs_used_for_range": market.get("war_costs_used_for_range"),
                "p_b_given_a_llm_clamped":  market.get("p_b_given_a_llm_clamped"),
                "p_b_given_a_deterministic": market.get("p_b_given_a_deterministic"),
                "outcome_observability":    market.get("outcome_observability"),
                "resolution_risk":          market.get("resolution_risk"),
                "kelly_fraction":           market.get("kelly_fraction"),
                "kelly_dollars":            market.get("kelly_dollars"),
                "bet_direction":            market.get("bet_direction"),
                "kelly_clergy_confidence_mult": market.get("kelly_clergy_confidence_mult"),
                "win_condition_summary":    market.get("win_condition_summary"),
                "legalese_flags":           market.get("legalese_flags"),
            }
            f.write(json.dumps(entry) + "\n")
            written += 1

    print(f"  Appended {written} entries → {PREDICTIONS_LOG}")


if __name__ == "__main__":
    run_translator()
