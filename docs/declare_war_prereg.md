# Pre-registration: empirical P(B|A) for formal declarations of war (Nov 5, 2026)

Written before any change to production. Module: `pilot/declare_war.py`. Wiring: `pipeline/translator.py` (restore at the start
of a run; apply after strike|war, before the during-war pass).

## Problem

- The old path prices a contract as P(A)·P(B|A) + (1 − P(A))·P(B|not A). A is "a serious interstate violent episode in the dyad
  within the horizon (≈ ICB VIOL ≥ 3)".
- For "political act" contracts the Clergyman's P(B|A) is clamped into a hand-set anchor range, **[0.3, 0.9]**.
- Nov 4, "Will the US officially declare war on Iran by Dec 31, 2026?": the LLM's own P(B|A) was **0.04**; the anchor clamped it to
  **0.30**; published 0.2555 vs market 0.023.
- The anchor range has no empirical basis for declarations of war.

## Evidence

GML MID data (Gibler, Miller & Little; via the `peacesciencer` R package), directed dyad-disputes at onset, post-1945. A serious
episode is approximated two ways:

- **A1:** hostility level 5 (war), or level 4 (use of force) with any fatalities.
- **A2:** level 5, or level 4 with ≥ 26 fatalities.

| Sample | Serious disputes | Highest action = declaration of war |
|---|---|---|
| 1946–2014, A1 | 403 (1,384 directed dyads) | **0** |
| 1946–2014, A2 | 159 (810) | **0** |
| 1990–2014, A1 | 122 (438) | **0** |

- **Caveat (masking):** the highest-action code hides a declaration inside a dispute coded as interstate war (≥ 20); 9–22% of
  serious disputes (dispute-weighted) reach war.
- **The allowance:** even if one in ten of those wars carried a formal declaration, P(declaration | A) ≈ 0.01–0.02. The
  observed-code rate alone has a Jeffreys 95% upper bound of about 0.006 (0 of 403).
- **Value adopted: 0.02.** It is the upper end of the masking allowance, so it is conservative toward YES.

## Rule

- **Which contracts:** any open CORE contract whose question asks for a declaration of war (regex in the module: declare /
  declares / declared / declaration of + optional "a" + war), conflict polarity, with P(A) and P(B|not A) present.
- **What changes:** P(B|A) = 0.02, and the price is recomputed from the same P(A) and P(B|not A). Nothing else changes.
- **It is a rule by contract text, not by pair:** every future declared-war contract gets it.
- **Not touched:** other political acts (e.g. NATO Article 5 invocation: a different act, with no evidence gathered here).

## Adoption

- **No replay is possible:** no declared-war contract has resolved with a scored forecast. Adoption rests on the evidence above
  replacing an unsupported anchor (theory and data over hand-set numbers).
- **Live from the next run, no shadow period.** Scored forward on the fair record like everything else.
- **Re-open if:** a formal declaration of war occurs in a contract we priced, or a hand-checked count of post-1945 declarations
  (inside wars) puts the rate above 0.05.

## Expected effect (Nov 4 inputs)

- US declares war on Iran by Dec 31: 0.2555 → about 0.017 (P(A) 0.851, P(B|not A) 0.00078). Market 0.023.
- No other open contract qualifies today.
