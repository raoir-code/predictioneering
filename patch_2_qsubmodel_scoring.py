#!/usr/bin/env python3.11
"""
Patch 2 — replace the single 10-node score_nodes() scorer with the full
Q-submodel scoring layer: Q0/Q_PARENTS_* constants, the onset + live rubric
text, the shared _call_claude_json() helper (also fixes the missing
temperature=0 on this file's Claude calls), score_nodes_call_a/b, and the
post-hoc decomposition layer (ONSET_ONLY_KEYS/LIVE_ONLY_KEYS,
load_dyad_q_static, build_q_components, q_with_subset).

This patch only ADDS the new scoring machinery — it does not yet call it
from anywhere. Patches 3 and 4 wire it into run_leakage_check() and
run_backtest(). Apply all three before running the backtest.

Run from repo root: python3.11 patch_2_qsubmodel_scoring.py
"""
from pathlib import Path

path = Path("pipeline/backtest.py")
content = path.read_text()

old = r'''
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
'''

new = r'''
# ── Q-SUBMODEL — new q-parents, June 17 2026 spec ──────────────────────
# logit(q_t) = q0 + xi*kappa_commit + Sum(onset-valid) + Sum(live dynamic)
# Strictly additive in logit space, v1 — no interactions.
#
# Q0 is a placeholder. The spec did not carry forward an ICB-regression
# intercept (only per-parent slopes). Treated as 0 until/unless a real
# intercept exists -- this affects q's absolute level, not the relative
# TP-vs-TN discrimination test this run is actually for.
Q0 = 0.0

# Onset-valid, LLM-scored each snapshot from the current precipitating event.
# NOTE: the spec's "5 onset-valid fields" includes ProtractedConflict and
# GeographicProximity, but both are explicitly defined as static dyad
# metadata "never scored from news" -- so only 3 of the 5 go through the
# LLM. The other 2 come from dyad_configs.json (Q_PARENTS_STATIC below).
Q_PARENTS_ONSET_LLM = ["TriggerType", "ValueThreatGravity", "ThirdPartyMilitaryInvolvement"]

# Live dynamic, LLM-scored each snapshot, own call to protect field quality.
Q_PARENTS_LIVE = ["LiveNonviolentMilitaryPressure", "LiveViolenceObserved",
                  "LiveUltimatumDeadline", "LiveMediationAccepted", "LiveAbatementSignal"]

# Static dyad metadata, set once in dyad_configs.json under "q_static", never scored from news.
Q_PARENTS_STATIC = ["ProtractedConflict", "GeographicProximity"]

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
Score these 5 live-dynamic q-parents from the headlines below. Each has its own recency window -- only count evidence dated within that window before the snapshot date; ignore anything older.

- LiveNonviolentMilitaryPressure (7-day window): 0 = routine exercise. 0.25 = unusual movement / show of force. 0.60 = mobilization / alert / major deployment / offensive posture shift. 1.00 = offensive posture shift WITH a deadline or high-value threat present. Signal class: call-ups, reserve activation, conscription, alert status, fleets leaving port, bomber/tanker surges, missile dispersal, exclusion zones.

- LiveViolenceObserved (7-day window): 0 = no violence this window. 0.50 = minor/isolated incident. 0.90 = serious clash / strike / raid / attack on military personnel / cross-border fire. A full-scale attack is excluded (it becomes the outcome, not a predictor).
    IMPORTANT: {trigger_context}

- LiveUltimatumDeadline (14-day window): 0 = none. 0.20 = vague threat. 0.60 = explicit deadline / red line / exclusion zone / "withdraw by X" / "we will respond if".

- LiveMediationAccepted (14-day window): report the MAGNITUDE only (0, 0.30, or 0.60) -- sign is applied downstream in code, do not output a negative number. 0 = none, or offered-not-accepted. 0.30 = accepted talks / third-party mediation. 0.60 = active serious mediation, both parties engaged. ("Calls for restraint" alone do not count.)

- LiveAbatementSignal (21-day window): report the MAGNITUDE only (0 or 0.50) -- sign is applied downstream in code. 0.50 = withdrawal, stand-down, reopened borders/channels, ceasefire implementation, canceled exercises, de-alerting, prisoner exchange, accepted inspection, resumed talks, or explicit de-escalatory concession. 0 = none of the above.

Return ONLY valid JSON, no preamble: {{"LiveNonviolentMilitaryPressure": 0, "LiveViolenceObserved": 0, "LiveUltimatumDeadline": 0, "LiveMediationAccepted": 0, "LiveAbatementSignal": 0}}
"""

def _call_claude_json(prompt, expected_fields, max_tokens):
    """Shared Claude call + JSON parse, used by both Call A and Call B."""
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
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers=headers, json=body, timeout=60)
    resp = r.json()
    if "content" not in resp:
        print(f"    [warn] Claude API error: {resp.get('error', {}).get('message', 'unknown')}")
        return {n: 0.0 for n in expected_fields}
    text = resp["content"][0]["text"].strip()

    try:
        if "```" in text:
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        parsed = json.loads(text.strip())
        return {n: float(parsed.get(n, 0.0)) for n in expected_fields}
    except Exception:
        print(f"    [warn] Node scoring parse error, using zeros")
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

{NODE_RUBRICS}
{RUBRIC_ONSET_ADDITION}"""

    return _call_claude_json(prompt, expected, max_tokens=700)

def score_nodes_call_b(dyad, articles, as_of_date, trigger_was_violent):
    """Call B: 5 live-dynamic q-parents, separate call to protect field quality.

    trigger_was_violent: bool, from Call A's TriggerType this same snapshot.
    Collision fix (spec checklist item): TriggerType fires once at actual
    crisis onset; LiveViolenceObserved must require violence ADDITIONAL to
    whatever already set TriggerType, or the same triggering event gets
    double-counted for the rest of its 7-day rolling window.
    """
    expected = Q_PARENTS_LIVE
    if not articles:
        return {n: 0.0 for n in expected}

    headlines = "\n".join(
        f"- {a['title']} ({a['publishedAt'][:10]})"
        for a in articles
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

{RUBRIC_LIVE_TEMPLATE.format(trigger_context=trigger_context)}"""

    return _call_claude_json(prompt, expected, max_tokens=400)

# ── Q-SUBMODEL DECOMPOSITION ────────────────────────────────────────────
# Pure arithmetic, additive in logit space -- free post-hoc attribution
# from a single backtest run, no sequential ablations needed.

ONSET_ONLY_KEYS = ["base", "CommitmentProblem", "TriggerType", "ValueThreatGravity",
                   "ThirdPartyMilitaryInvolvement", "ProtractedConflict", "GeographicProximity"]
LIVE_ONLY_KEYS  = ["base", "CommitmentProblem", "LiveNonviolentMilitaryPressure",
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
        "TriggerType":                   call_a.get("TriggerType", 0.0),
        "ValueThreatGravity":            call_a.get("ValueThreatGravity", 0.0),
        "ThirdPartyMilitaryInvolvement": call_a.get("ThirdPartyMilitaryInvolvement", 0.0),
        "ProtractedConflict":            q_static.get("ProtractedConflict", 0.0),
        "GeographicProximity":           q_static.get("GeographicProximity", 0.0),
        "LiveNonviolentMilitaryPressure":call_b.get("LiveNonviolentMilitaryPressure", 0.0),
        "LiveViolenceObserved":          call_b.get("LiveViolenceObserved", 0.0),
        "LiveUltimatumDeadline":         call_b.get("LiveUltimatumDeadline", 0.0),
        "LiveMediationAccepted":         -call_b.get("LiveMediationAccepted", 0.0),
        "LiveAbatementSignal":           -call_b.get("LiveAbatementSignal", 0.0),
    }

def q_with_subset(q_components, include_keys=None):
    keys = include_keys if include_keys is not None else list(q_components.keys())
    subset_logit = sum(v for k, v in q_components.items() if k in keys)
    return 1 / (1 + math.exp(-subset_logit))
'''

assert old in content, "OLD BLOCK NOT FOUND — aborting, no changes made. Has backtest.py already been patched, or modified since clone?"
assert content.count(old) == 1, "OLD BLOCK NOT UNIQUE — aborting, refusing to guess which occurrence to replace"

content = content.replace(old, new)
path.write_text(content)
print("Patch 2 applied — Q-submodel scoring layer added (score_nodes_call_a/b, decomposition helpers).")
print("Old single-call score_nodes() is now UNUSED — patches 3 and 4 replace its call sites.")
