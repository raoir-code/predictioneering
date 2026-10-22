# Ceasefire / peace contracts: scope rule (pre-registered Oct 22, 2026, before any reclassification)

Applies to Polymarket contracts whose question or event title mentions ceasefire, truce, armistice or peace.
The family is set by the RESOLUTION TEXT (description), never by the title or by actor type
(state vs non-state never decides scope). Assignment is deterministic (text rules), not LLM.

A. HOLDS: resolves NO iff a qualifying military action (Polymarket's strike definition: air strike or
   surface-to-surface missile strike that directly impacts the target's territory; the listed exclusions apply)
   occurs between market creation and the date, in the stated direction(s). -> CORE.
   Priced as P(no qualifying strike in the counted direction(s) from now to D | none since creation).
   Variants with a different event definition (e.g. "kinetic military action on Iranian soil" + confirmation
   window) are family A with their own structural fingerprint.
B. GAP: resolves YES iff a continuous N-day period without a qualifying action by the stated initiator begins
   by the date. -> CORE. Priced as a first-passage probability of an N-day strike-free spell.
C. AGREEMENT: resolves on announcement/confirmation of a mutually agreed suspension, deal, truce or extension.
   -> ADJACENT, unpriced, until a termination model passes its own pre-registered rule.
D. PROCESS: attendance, venue, whether talks occur, referendums, peacekeeping announcements, combos.
   -> out of scope, unpriced.

Conditions:
- A/B enter CORE only for pairs where every counted direction has a strike model; otherwise listed, unpriced.
- Polarity is explicit per contract (HOLDS: YES = no strike); resolver, Brier log, market truth and bettor
  must read it before any A/B contract is published.
- Tier 2: A/B contracts priced by the unified engine are inside the Tier 2 rule as written (it is defined by
  pricing component). They are also reported as a separate stratum. No A/B contract has been scored as of this commit.
- Ambiguous resolution text -> listed, unpriced, flagged for review.
