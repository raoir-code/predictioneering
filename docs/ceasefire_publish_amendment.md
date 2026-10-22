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
