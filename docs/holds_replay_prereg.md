# Family A ("ceasefire holds") replay rule — pre-registered Oct 22, 2026, before any replay is run

Scope: resolved Polymarket "ceasefire continues through D" contracts whose resolution is Polymarket's qualifying-military-action
strike definition (docs/ceasefire_scope_rule.md, family A). Series in scope today: US->Iran, Israel<->Iran (either side), US->Yemen.
Model: unified engine, unchanged math. A holds contract = by-date strike window [market creation, D] with polarity flipped.
  holds YES -> no-strike window for every counted direction; holds NO -> strike window (single-direction only; a two-direction
  NO cannot be attributed and is not used, counted). Two directions: P(YES) = product of (1 - P(strike)) (independence, v0.1;
  known bias: understates "holds" when retaliation correlates strikes).
Holds contracts form their own groups (structural fingerprint prefixed "H"): they do not change any existing strike group's price.
Class-prior pairs (no world prior, e.g. US->Iran): priced if the pair has >= 10 settled windows of its own OR positive evidence of
  fighting (amends the existing "positive evidence only" rule, for holds groups only).
Walk-forward: each resolved contract is priced as of 24h after market creation (first daily run after listing), using only
  outcomes whose close time precedes that moment. Skipped if already resolved or past its date at that moment.
Comparator: Polymarket YES price at the same moment (CLOB price history, last point at or before; else first point within 24h after).
Rule, per series (direction set): n >= 5 replayed contracts AND Brier(unified) <= Brier(market) + 0.03 -> published.
  Otherwise listed, unpriced. Recomputed daily from the same rule; never hand-edited.
Tier 2: published holds contracts are inside Tier 2 as written, reported as a separate stratum.
Reported regardless of outcome: n per series, Brier unified / market, YES/NO split, effective-sample caveat (one quiet spell per series).
