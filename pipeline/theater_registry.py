"""
theater_registry.py — shared actor/theater-level escalation state
====================================================================
Added 2026-09-10 (Phase 1a/1b), following the Sept 5 forensics on the
Aug 30-31 Iran-Jordan/UAE miss. Root cause: the engine was too dyad-local
-- "Iran-Jordan waits for Jordan-specific evidence" instead of "US hits
Iran -> Iran's retaliation hazard rises -> propagates to plausible
regional targets before any target-specific headline exists."

Symmetric group design: every member dyad both CONTRIBUTES to and READS
FROM the shared hazard for its initiator. This matches the real observed
cascade (Jordan/UAE hit Aug 31 raised risk for Bahrain/Iraq/Kuwait too,
not just an abstract US-Iran tension reading) better than an earlier
one-way trigger->target split would have. Safe against feedback loops
because the combination rule is max(), not additive -- a member
re-contributing a signal that originated elsewhere is a no-op.

This module is deliberately lightweight (no heavy engine.py import,
same pattern as dyad_registry.py) so it can be imported without
requiring ANTHROPIC_API_KEY/GNEWS_API_KEY to be set.

Two files:
  - theater_groups.json  (hand-maintained, read-only from here): which
    dyads belong to each initiator's shared theater group.
  - theater_state.json    (read-write, this module owns it): persisted,
    decaying hazard level per initiator, same half-life/decay pattern
    as predict.py's node_memory_state.json (Phase 0b).
"""

import json
import os
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THEATER_GROUPS_PATH = os.path.join(os.path.dirname(__file__), "theater_groups.json")
THEATER_STATE_PATH  = os.path.join(os.path.dirname(__file__), "theater_state.json")

# Half-life for the shared theater hazard itself, in days. Matches
# LiveViolenceObserved's half-life (engine.py HALF_LIFE_DAYS) since a real
# strike is the dominant driver of this signal and should linger
# comparably to how a strike's own LiveViolenceObserved score lingers.
THEATER_HAZARD_HALF_LIFE_DAYS = 10
THEATER_DECAY_FACTOR = 0.5 ** (1.0 / THEATER_HAZARD_HALF_LIFE_DAYS)


def load_theater_groups():
    if os.path.exists(THEATER_GROUPS_PATH):
        with open(THEATER_GROUPS_PATH) as f:
            return json.load(f)
    return {}


def load_theater_state():
    if os.path.exists(THEATER_STATE_PATH):
        with open(THEATER_STATE_PATH) as f:
            return json.load(f)
    return {}


def save_theater_state(state):
    # Atomic write -- same reasoning as predict.py's node_memory_state.json:
    # read-then-written on every member dyad, every day, indefinitely.
    tmp = THEATER_STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, THEATER_STATE_PATH)


def get_initiator_for_member(dyad, groups=None):
    """If `dyad` belongs to some initiator's theater group, return that
    initiator's name. Otherwise None."""
    groups = groups if groups is not None else load_theater_groups()
    for initiator, cfg in groups.items():
        if dyad in cfg.get("members", []):
            return initiator
    return None


def get_group_members(dyad, groups=None):
    """If `dyad` is a member of some group, return the OTHER members of
    that group. Otherwise []."""
    groups = groups if groups is not None else load_theater_groups()
    for initiator, cfg in groups.items():
        members = cfg.get("members", [])
        if dyad in members:
            return [m for m in members if m != dyad]
    return []


def get_news_inheritance_sources(dyad, groups=None):
    """Phase 1d: if `dyad` is the designated news-inheritance AGGREGATE for
    its group (e.g. Iran-ArabStates), return the other group members whose
    GNews articles should be merged into its own daily fetch -- explicitly
    excluding the initiator's own direct-combatant dyads (e.g. US-Iran,
    Israel-Iran aren't Arab states; their headlines wouldn't be appropriate
    evidence for an "Iran attacks any Arab country" market). Returns []
    for any dyad that isn't a designated aggregate, including ordinary
    bilateral members -- Jordan should NOT inherit UAE's articles into its
    own local scoring, that would blur local specificity for no reason.
    The theater hazard mechanism (update_hazard/decayed_hazard) is the
    correct channel for cross-dyad signal; this is only for the aggregate's
    own news blindness (Sept 5 forensics finding #18)."""
    groups = groups if groups is not None else load_theater_groups()
    for initiator, cfg in groups.items():
        if cfg.get("aggregate") == dyad:
            # Simplest correct rule for this codebase's naming convention:
            # Arab-state bilateral dyads are named "Initiator-Country"
            # (Iran-Jordan, Iran-UAE, ...). US-Iran/Israel-Iran don't match
            # that prefix and are correctly excluded -- their headlines
            # wouldn't be appropriate evidence for an Arab-states market.
            siblings = [m for m in cfg.get("members", []) if m != dyad]
            return [m for m in siblings if m.startswith(f"{initiator}-")]
    return []


def decayed_hazard(initiator, today, state=None):
    """Return today's decayed hazard level for `initiator`, given the
    persisted state. Does not mutate state or touch disk."""
    state = state if state is not None else load_theater_state()
    entry = state.get(initiator)
    if not entry:
        return 0.0
    as_of = entry.get("as_of")
    hazard = entry.get("hazard", 0.0)
    if not as_of:
        return 0.0
    days_elapsed = max((today - date.fromisoformat(as_of)).days, 0)
    return hazard * (THEATER_DECAY_FACTOR ** days_elapsed)


def update_hazard(initiator, today, today_local_acute_core, state=None):
    """Called when processing ANY member dyad. Combines today's local
    acute signal for that dyad with the decayed prior hazard via max()
    (same combination rule as engine.py's node_memory decay: max(today_val,
    decayed)), then returns the updated state dict (caller persists it).
    Does not write to disk itself -- caller decides when (and whether,
    e.g. respecting --dry-run)."""
    state = state if state is not None else load_theater_state()
    prior_decayed = decayed_hazard(initiator, today, state=state)
    new_hazard = max(today_local_acute_core, prior_decayed)
    state[initiator] = {"hazard": new_hazard, "as_of": today.isoformat()}
    return state
