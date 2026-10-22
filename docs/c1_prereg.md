# Family C v1 ("agreement-v1") — pre-registered Oct 22, 2026, before any C1 replay

1. Likelihood bug fix (ChatGPT review): overlapping YES windows are no longer intersected (that assumed one event caused every YES).
   They are evaluated exactly with the unified engine's last-event tracking (pilot/unified.py forward) on a one-state process.
2. External prior from the right estimand: PA-X v10 (2,257 agreements; Bell & Badanjak 2019) linked to UCDP Conflict Termination
   v4-2024 by PA-X's UcdpCon field. Event = a distinct (conflict, date) with >= 1 multiparty agreement of the mapped stage, dated in an
   active UCDP conflict-year or the year after. Exposure = active conflict-years 1990-2024.
     CEASEFIRE <- Stage "Cea"; EXTENSION <- Stage "Ren", exposure = conflict-years with a ceasefire-stage agreement in the previous
     12 months; DEAL <- Stage "SubComp" or StageSub "FrAg"; BREAKDOWN unchanged (UCDP recurrence; PA-X records no breakdowns).
   Interstate and intrastate pooled (interstate has 5 ceasefire events in 48 conflict-years: too few to separate).
   Prior on an actor set's rate: log-normal(mu, sigma) fitted by Poisson-lognormal marginal likelihood across conflicts
   (between-conflict heterogeneity). No hand-set spread.
3. Pair evidence unchanged: the actor set's own resolved Polymarket contracts of the same type, usable only after close time.
4. Comparison on all resolved C contracts, walk-forward (priced 24h after listing): C0 (shipped), C0 + fix, C1, market.
   Brier and log loss (p clipped to [0.001, 0.999]), YES/NO split, by actor set; cluster bootstrap by actor set (2,000 draws) of
   Brier(C1) - Brier(C0).
5. Production switch: C1 replaces C0 iff Brier(C1) < Brier(C0) on this replay; otherwise C0 + fix replaces C0 iff it beats C0.
   Publication is unaffected (everything in scope is published).
6. Caveat: development data -- C0's failure on these contracts motivated C1. Not confirmation; the real test is forward.
7. Out of scope here: the talks state (C2), provisions (family E).
8. Amendment (Oct 22, before any C1 replay; made after seeing only the PA-X prior fit, no Polymarket outcome): a type with
   < 20 PA-X events has an unidentified between-conflict spread (EXTENSION: 6 events, MLE sigma 0.05 at the grid boundary).
   Such types keep their own median rate and take the CEASEFIRE sigma (2.0, the best-identified heterogeneity).
