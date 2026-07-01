"""
pipeline/context_keeper.py
Automated crisis_context maintenance for predictioneering dyads.

Two trigger paths converge on refresh_context():
  1. Event-triggered -- called from predict.py's daily loop, once per dyad,
     right after call_a/call_b complete. TODAY this is a fixed-threshold
     (OperationalPreparation or LiveViolenceObserved >= 0.5) plus a per-dyad
     cooldown, because there is no historical node-score data yet to compute
     a rolling median against. This file ALSO logs raw node scores to
     node_score_history.jsonl every day specifically so that once ~7+ days
     of history exist for a dyad, the trigger can be upgraded to
     |today - rolling_7d_median| > threshold (evidence-state-surprise,
     per the design discussion June 30) -- a more statistically grounded
     trigger that doesn't keep re-firing on a dyad that's simply been hot
     for weeks. See check_event_trigger() for the upgrade hook.
  2. Calendar backstop (weekly sweep) -- called from run_pipeline.sh on the
     same cadence as disciplinarian, for dyads with DYAD_REGIME != 0 or an
     acute_phase_onset_date set. Catches slow drift that never crosses the
     acute threshold (e.g. a ceasefire framework gradually eroding).

Every refresh attempt, regardless of outcome, goes through:
  1. Generate candidate update (cached GNews + old context -> new context).
  2. Deterministic validators (cheap, catches obvious garbage).
  3. Independent verifier call (APPROVE / REJECT / QUARANTINE) -- this is
     NOT a human-review substitute, it's an automated redundancy check
     against context corruption. A changelog alone is auditable after the
     fact but not preventative; this is the preventative half.
  4. Auto-apply ONLY on APPROVE. REJECT keeps the old context unchanged.
     QUARANTINE does not apply but is logged for later inspection.
  5. Log every attempt -- approved, rejected, or quarantined -- to
     context_changelog.jsonl. No silent failures, no silent overwrites.

No human approval gate anywhere in this file, by design (per June 30
discussion: the system runs unattended for months, a manual review step
doesn't scale and defeats the point). The verifier call is the substitute
for that gate, not a placeholder for one.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

import requests

ROOT = Path(__file__).resolve().parent.parent
DYAD_CONFIGS_PATH   = ROOT / "pipeline" / "dyad_configs.json"
CHANGELOG_PATH       = ROOT / "pipeline" / "context_changelog.jsonl"
COOLDOWN_STATE_PATH  = ROOT / "pipeline" / ".context_cooldown_state.json"
NODE_HISTORY_PATH    = ROOT / "pipeline" / "node_score_history.jsonl"
GNEWS_CACHE          = ROOT / "pipeline" / "cache" / "gnews"

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

COOLDOWN_HOURS  = 60     # 48-72h range per design discussion, midpoint
ACUTE_THRESHOLD = 0.5    # fixed-threshold fallback trigger (OP or LVO >= this)
MIN_CONTEXT_LEN = 80
MAX_CONTEXT_LEN = 3000
HEADLINE_WINDOW_DAYS = 7


# ----------------------------------------------------------------------
# Shared Clade call helper -- mirrors backtest.py's _call_claude_json
# conventions (raw requests, claude-opus-4-6, temperature 0, retry once)
# ------------------------------------------------------------------------

def _call_claude_raw(prompt, system=None, max_tokens=600, retries=1):
    """Returns raw text response, or None on total failure."""
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
    if system:
        body["system"] = system

    for attempt in range(retries + 1):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body, timeout=60)
            resp = r.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                print(f"    [context_keeper] API request failed ({type(e).__name__}), retrying once...")
                continue
            print(f"    [context_keeper] API request failed ({type(e).__name__}) after retry")
            return None
        except ValueError:
            print(f"    [context_keeper] API returned non-JSON response")
            return None

    if "content" not in resp:
        print(f"    [context_keeper] Claude API error: {resp.get('error', {}).get('message', 'unknown')}")
        return None
    return resp["content"][0]["text"].strip()


# ----------------------------------------------------------------------
# Node score history -- lightweight logging for the future rolling-median
# upgrade. Cheap, append-only, written every day regardless of trigger.
# ---------------------------------------------------------------------

def log_node_history(dyad, as_of_date, call_a, call_b):
    entry = {
        "dyad": dyad,
        "date": str(as_of_date),
        "TriggerType":             call_a.get("TriggerType", 0.0),
        "OperationalPreparation":  call_b.get("OperationalPreparation", 0.0),
        "LiveViolenceObserved":    call_b.get("LiveViolenceObserved", 0.0),
        "logged_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(NODE_HISTORY_PATH, "a") as f:
        f.write(json.dumps(entry) + "\n")


# ----------------------------------------------------------------
# Cooldown state -- prevents a single volatile news day from triggering
# repeated rewrites of the same dyad's context.
# ----------------------------------------------------------------

def _load_cooldowns():
    if COOLDOWN_STATE_PATH.exists():
        try:
            return json.loads(COOLDOWN_STATE_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_cooldowns(state):
    COOLDOWN_STATE_PATH.write_text(json.dumps(state, indent=2))


def _cooldown_active(dyad):
    state = _load_cooldowns()
    last = state.get(dyad)
    if not last:
        return False
    last_dt = datetime.fromisoformat(last)
    return (datetime.now(timezone.utc) - last_dt) < timedelta(hours=COOLDOWN_HOURS)


def _mark_refreshed(dyad):
    state = _load_cooldowns()
    state[dyad] = datetime.now(timezone.utc).isoformat()
    _save_cooldowns(state)


# -----------------------------------------------------------------
# Trigger logic
# -----------------------------------------------------------------

def check_event_trigger(dyad, call_a, call_b):
    """
    TODAY: fixed-threshold-plus-cooldown.
    UPGRADE PATH (once node_score_history.jsonl has >=7 days for this dyad):
    replace the threshold check below with
        recent = [e for e in history if e["dyad"]==dyad][-7:]
        median_op = statistics.median(e["OperationalPreparation"] for e in recent)
        median_lvo = statistics.median(e["LiveViolenceObserved"] for e in recent)
        surprise = max(abs(op - median_op), abs(lvo - median_lvo))
        return surprise > SURPRISE_THRESHOLD and not _cooldown_active(dyad)
    This is deliberately not implemented yet -- there is no history to
    compute a median against on day one, and a fake/bootstrapped median
    would be worse than the honest fixed threshold below.
    """
    op  = call_b.get("OperationalPreparation", 0.0)
    lvo = call_b.get("LiveViolenceObserved", 0.0)
    if max(op, lvo) < ACUTE_THRESHOLD:
        return False
    if _cooldown_active(dyad):
        return False
    return True


# ----------------------------------------------------------------
# Headline retrieval -- reuses already-cached GNews data, zero marginal cost
# ----------------------------------------------------------------

def _load_recent_headlines(dyad, as_of_date, days=HEADLINE_WINDOW_DAYS):
    headlines = []
    safe_dyad = re.sub(r'[^A-Za-z0-9_]+', '_', dyad)
    for i in range(days):
        d = as_of_date - timedelta(days=i)
        cache_file = GNEWS_CACHE / f"{safe_dyad}_{d.strftime('%Y%m%d')}.json"
        if cache_file.exists():
            try:
                articles = json.loads(cache_file.read_text())
                if isinstance(articles, list):
                    headlines.extend(articles)
            except Exception:
                pass

    seen, deduped = set(), []
    for a in headlines:
        t = a.get("title", "").strip().lower()[:80]
        if t and t not in seen:
            seen.add(t)
            deduped.append(a)
    return deduped


# -----------------------------------------------------------------
# Deterministic validators -- cheap, run before spending a verifier call
# -----------------------------------------------------------------

def _validate_candidate(old_context, new_context, dyad):
    if not new_context or len(new_context) < MIN_CONTEXT_LEN:
        return False, "too short / empty"
    if len(new_context) > MAX_CONTEXT_LEN:
        return False, "too long"
    if new_context.strip() == (old_context or "").strip():
        return False, "no actual change (identical to old context)"

    actors = [p.strip() for p in dyad.replace("Europe(", "").replace(")", "").split("-")
              if len(p.strip()) > 2]
    if actors and not any(a.lower() in new_context.lower() for a in actors):
        return False, f"doesn't mention any of this dyad's actors ({actors})"

    return True, "ok"


# ----------------------------------------------------------------
# Generation + verification calls
# ----------------------------------------------------------------

def _generate_candidate(dyad, old_context, headlines, trigger_reason):
    headline_text = "\n".join(
        f"- {a.get('title','')} ({a.get('publishedAt','')[:10]})" for a in headlines[:25]
    )
    prompt = f"""Dyad: {dyad}
Trigger reason: {trigger_reason}

CURRENT crisis_context:
{old_context if old_context else "(none set yet -- this dyad has no prior context)"}

Recent headlines (trailing ~{HEADLINE_WINDOW_DAYS} days, already actor-relevance-filtered upstream):
{headline_text if headline_text else "(no cached headlines available)"}

Task: propose an UPDATED crisis_context for this dyad. This text gets injected
directly into a node-scoring prompt to help an LLM correctly route evidence to
the right structural nodes -- e.g. distinguishing routine posturing from
genuine operational preparation, or noting that a precipitating event already
happened so it isn't re-scored as new. If prior context exists, preserve its
routing-guidance STYLE and update the FACTUAL anchor to reflect what's
changed. If nothing has materially changed, return the old context unchanged.
If there is no prior context, write a new one from scratch using the same
style: a CRISIS CONTEXT summary followed by explicit guidance on how to score
specific named nodes given this dyad's current situation.

Respond with ONLY the new crisis_context text. No preamble, no markdown, no
JSON wrapper -- just the raw text that will be stored directly."""

    return _call_claude_raw(prompt, max_tokens=600)


VERIFIER_SYSTEM = """You are an independent quality-control reviewer for an automated
geopolitical forecasting system. Your ONLY job is to check whether a proposed
update to a dyad's crisis context is a coherent, evidence-grounded incremental
update -- you do not write or improve the content yourself.

Approve only if:
- The new context is consistent with the provided headlines (no claims that
  aren't supported by them or by the prior context).
- It does not silently delete or contradict still-relevant facts from the old
  context without explanation.
- It does not claim a future event as having already happened, or vice versa.
- It's a genuine update reflecting new information, not a degenerate
  paraphrase loop of the old text.

Respond with ONLY valid JSON in this exact form, no other text:
{"verdict": "APPROVE", "reason": "<one sentence>"}
or {"verdict": "REJECT", "reason": "<one sentence>"}
or {"verdict": "QUARANTINE", "reason": "<one sentence>"}

QUARANTINE means: plausible but you are not confident enough to auto-apply it.
Do not apply it, but do not treat the underlying signal as wrong either."""


def _verify_candidate(dyad, old_context, new_context, headlines):
    headline_text = "\n".join(
        f"- {a.get('title','')} ({a.get('publishedAt','')[:10]})" for a in headlines[:25]
    )
    prompt = f"""Dyad: {dyad}

OLD crisis_context:
{oold_context if old_context else "(none)"}

PROPOSED NEW crisis_context:
{new_context}

Headlines used to generate the proposal:
{headline_text if headline_text else "(none)"}

Evaluate per your system instructions."""

    text = _call_claude_raw(prompt, system=VERIFIER_SYSTEM, max_tokens=200)
    if text is None:
        return "QUARANTINE", "verifier API call failed"

    # Tolerant parse: direct JSON, then brace-extraction fallback
    for candidate in (text, text[text.find("{"):text.rfind("}")+1] if "{" in text else ""):
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
            verdict = parsed.get("verdict", "QUARANTINE")
            reason  = parsed.get("reason", "")
            if verdict in ("APPROVE", "REJECT", "QUARANTINE"):
                return verdict, reason
        except Exception:
            continue

    return "QUARANTINE", f"verifier response not parseable as JSON: {text[:200]}"


# -----------------------------------------------------------------
# Changelog -- full audit trail, every attempt, no silent outcomes
# -----------------------------------------------------------------

def _append_changelog(entry):
    with open(CHANGELOG_PATH, "a") as f:
        f.write(json.dumps(entry, default=str) + "\n")


# ----------------------------------------------------------------
# Main entry point
# ----------------------------------------------------------------

def refresh_context(dyad, trigger_reason, as_of_date=None):
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()

    if not DYAD_CONFIGS_PATH.exists():
        print(f"  [context_keeper] {DYAD_CONFIGS_PATH} not found, aborting")
        return

    configs = json.loads(DYAD_CONFIGS_PATH.read_text())
    cfg = configs.get(dyad, {})
    old_context = cfg.get("crisis_context", "")

    headlines = _load_recent_headlines(dyad, as_of_date)

    new_context = _generate_candidate(dyad, old_context, headlines, trigger_reason)
    if new_context is None:
        _append_changelog({
            "dyad": dyad, "date": str(as_of_date), "trigger_reason": trigger_reason,
            "stage": "generation_failed",
        })
        print(f"  [context_keeper] {dyad}: generation call failed")
        return

    ok, reason = _validate_candidate(old_context, new_context, dyad)
    if not ok:
        _append_changelog({
            "dyad": dyad, "date": str(as_of_date), "trigger_reason": trigger_reason,
            "stage": "validator_rejected", "reason": reason,
            "old_context": old_context, "candidate": new_context,
        })
        print(f"  [context_keeper] {dyad}: validator rejected ({reason})")
        return

    verdict, verifier_reason = _verify_candidate(dyad, old_context, new_context, headlines)

    log_entry = {
        "dyad": dyad, "date": str(as_of_date), "trigger_reason": trigger_reason,
        "stage": "verified", "verdict": verdict, "verifier_reason": verifier_reason,
        "old_context": old_context, "new_context": new_context,
    }

    if verdict == "APPROVE":
        configs[dyad] = configs.get(dyad, {})
        configs[dyad]["crisis_context"] = new_context
        DYAD_CONFIGS_PATH.write_text(json.dumps(configs, indent=2))
        _mark_refreshed(dyad)
        print(f"  [context_keeper] {dyad}: APPROVED and applied ({verifier_reason})")
    elif verdict == "QUARANTINE":
        print(f"  [context_keeper] {dyad}: QUARANTINED, not applied ({verifier_reason})")
    else:
        print(f"  [context_keeper] {dyad}: REJECTED ({verifier_reason})")

    _append_changelog(log_entry)


def maybe_refresh_event_triggered(dyad, call_a, call_b, as_of_date=None):
    """Called from predict.py's daily loop, once per dyad, right after
    call_a/call_b complete. Always logs history; only refreshes on trigger."""
    if as_of_date is None:
        as_of_date = datetime.now(timezone.utc).date()
    log_node_history(dyad, as_of_date, call_a, call_b)
    if check_event_trigger(dyad, call_a, call_b):
        op  = call_b.get("OperationalPreparation", 0.0)
        lvo = call_b.get("LiveViolenceObserved", 0.0)
        refresh_context(dyad, trigger_reason=f"event: OP={op:.2f} LVO={lvo:.2f}", as_of_date=as_of_date)


def weekly_sweep(active_dyads, as_of_date=None):
    """Calendar backstop -- called from run_pipeline.sh on the same weekly
    cadence as disciplinarian, for dyads with DYAD_REGIME != 0 or an
    acute_phase_onset_date set."""
    for dyad in active_dyads:
        if _cooldown_active(dyad):
            print(f"  [context_keeper] {dyad}: skipped, cooldown active")
            continue
        refresh_context(dyad, trigger_reason="weekly_calendar_sweep", as_of_date=as_of_date)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "--sweep":
        configs = json.loads(DYAD_CONFIGS_PATH.read_text())
        # Active = has acute_phase_onset_date OR already has crisis_context
        # (a reasonable proxy for "this dyad matters enough to maintain")
        active = [k for k, v in configs.items()
                  if v.get("acute_phase_onset_date") or v.get("crisis_context")]
        print(f"[context_keeper] weekly sweep: {len(active)} active dyads")
        weekly_sweep(active)
    else:
        print("Usage: python3 -m pipeline.context_keeper --sweep")
        print("(event-triggered refresh is called from predict.py directly, not this CLI)")
