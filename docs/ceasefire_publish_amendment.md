# Ceasefire contracts: publish-everything amendment (Oct 22, 2026)

Decision (Adi, Oct 22): every in-scope ceasefire contract is priced and published. No in-scope contract is "listed, unpriced".
Same principle as the Oct 21 standing decision (publish every forecast, even when we expect to be wrong).

Amends docs/ceasefire_scope_rule.md (5044a35):
- Family A (HOLDS): all series published (unified-v1).
- Family B (GAP, N-day strike-free spell): published, component unified-gap-v0 (pilot/ceasefire_bc.py).
- Family C (AGREEMENT): moved to CORE, published, component agreement-v0 (pilot/ceasefire_bc.py). It no longer waits for a model
  to pass a rule.
- Family D (PROCESS: attendance, venue, whether talks occur, referendums, peacekeeping announcements, combos): still out of scope.
- Only contracts with no parseable date, or whose date has passed, stay unpriced (nothing to price).

Amends docs/holds_replay_prereg.md (5c91369): the replay no longer gates publication; it is recomputed daily and reported.
For the record: this amendment was made after the family-A replay had been run (both series passed it). It is not result-driven:
it applies to every series and makes publication independent of any replay result.

Families B and C (v0) are frozen as of this commit. Their first replay (report only) is in the commit message. Any change to
either model is pre-registered (rule + spec) before it is replayed again.

Tier 2: unified-v1 (A) and unified-gap-v0 (B) are inside the Tier 2 rule as written (unified machinery); agreement-v0 (C) is
reported as its own stratum, outside Tier 2.

## Scope addition (Oct 22, afternoon): normalization between conflict dyads (family E2)
- "X and Y normalize relations" contracts (resolution: both officially announce diplomatic relations / a formal normalization
  agreement) are family C, type DEAL, priced by the production C model, when X|Y is a conflict dyad: an actor pair we already
  price CORE strike contracts for (data-derived from the feed, no hand list). Third-country normalization (e.g. Israel-Saudi,
  Abraham Accords joiners) and recognitions stay out of scope (diplomacy, not conflict).
- Not yet in scope, by event class (a new family, not withheld): (E1) a deal containing a named term ("Ukraine agrees to cede
  territory", "give up the rest of Donbas", "agrees not to join NATO") and war outcomes (withdrawals, territorial control).
  Reason: no defensible reference class yet for P(term | this deal); PA-X has 14 interstate deals (3 with territorial provisions),
  and a generic rate repeats the reference-class error C0 and C1 made.

## Oct 23: war outcomes
War outcomes are split by event class (docs/war_outcomes_prereg.md amendment): withdrawals are in scope (withdrawal-v0);
captures of places and entries into sub-national places are out of scope (operational battlefield progress, not bargaining);
entries into another country are onset, priced by the engine where the classifier tags them CORE.

## Oct 23: event races
"X before <an event>" (the other leg is an event, not a date: "Israel x Iran ceasefire ends before Netanyahu out?", "US x Iran
ceasefire before Trump visits China?") resolves on which of two events happens first, a different quantity from "X by a date".
Until now family C priced them as by-date contracts (the market's end date stood in for the other leg). Now family RACE, deterministic
(pilot/ceasefire_bc.py):
- other leg a political or economic event (a leader leaving office, a visit, an election, a price level): OUT OF SCOPE (not conflict).
- other leg a conflict event (another ceasefire, a deal, a ceasefire ending): NOT YET IN SCOPE, by event class (no race model), the
  same status as E1; listed, not withheld.
Of 270 stored ceasefire contracts, 5 are races (3 political, 2 conflict); one is open (political). No other contract changes family.
Replays of family C from this commit on exclude races by scope; the C1b adoption (decided on the earlier set) stands.
Tagging also clears a family tag left by an earlier run when a contract no longer qualifies, and keeps PROCESS and RACE contracts
out of CORE, so they are never priced by the onset engine.
