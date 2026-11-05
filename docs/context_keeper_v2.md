# Context keeper v2 (Nov 5, 2026)

Module: `pipeline/context_keeper.py`. Shipped as a correctness fix to the same component as `5eaec87` (no replay possible: past
contexts cannot be regenerated as of past dates without leakage). Scored forward; first run on v2: Nov 6, 17:00 ET.

## Problem (found Nov 5)

- The generator was asked for "explicit guidance on how to score specific named nodes" and to "preserve its routing-guidance
  STYLE". 48 of 63 contexts carried instructions to the node scorer ("nodes related to X should be scored at elevated or
  maximum levels"). One model was setting another model's scores; that is not evidence.
- The verifier rejected or quarantined updates that "silently delete still-relevant facts", so text never expired. Alarm
  language accumulated ("MOST DANGEROUS LEVEL", "week twenty-four" of a crisis begun 8 weeks earlier).
- `5eaec87` (claims vs confirmed) could not reach legacy text: Pakistan-Yemen still read "confirmed combatant" after the
  Nov 5 refresh.
- Third-party actions were written as the dyad's own fighting (Houthi attacks on Saudi Arabia under Iran-Saudi Arabia).
- The pairs with the highest old-path P(A) on Nov 5 (Israel-Iran 0.91, Iran-Saudi Arabia 0.88, Pakistan-Yemen 0.75) all
  showed these patterns. How much of their P(A) the context drives is not measured (Adi chose to go live, Nov 5).

## Change

1. **Facts only.** Format: STATUS (direct relationship now) / FACTS (dated, newest first) / ALREADY HAPPENED / THIRD PARTIES.
   A deterministic check rejects any scoring instruction, and any context without a STATUS line.
2. **Expiry.** Facts older than 30 days leave unless a recent headline shows they still hold. The verifier no longer
   requires old text to be kept.
3. **Scope.** Only actions between the two parties are the dyad's hostilities; others go under THIRD PARTIES.
4. **No alarm language.**
5. **One-time rebuild** (`python -m pipeline.context_keeper --rebase`): every context regenerated from up to 90 headlines
   over 30 days (at most 3 a day), old text withheld from generator and verifier. Non-approved dyads keep the old context and
   are listed.

## Record and rollback

- Every old and new context is in `pipeline/context_changelog.jsonl` (trigger `rebase_v2`); `dyad_configs.json` is in git
  daily; each run logs P(A) (`engine_p`) per contract.
- Diagnosis: compare Nov 5 and Nov 6 P(A) per dyad; the patch notes list what moved.
- Rollback: restore `crisis_context` from the last `rebase_v2` entries' `old_context`, revert this commit.
