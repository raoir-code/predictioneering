# Family F, war outcomes ("war-outcome-v0") — scope + model, pre-registered Oct 22, 2026, before any replay

Scope (deterministic, title + resolution text; everything in scope is priced and published, docs/ceasefire_publish_amendment.md):
  CAPTURE     a named armed actor captures / recaptures / retakes / takes control of a named place or territory
  ENTRY       named armed forces / troops / an armed group enter a named place
  WITHDRAWAL  a state withdraws (all / ground) forces from a named place or territory
  The resolution text must concern armed forces, territory or control. Out: treaty or organization withdrawals (NATO, NPT),
  economic thresholds ("fall to"), individuals entering a country.
Event = the series (the question with its deadline removed). One-shot: the first occurrence resolves every remaining deadline.
Model: constant hazard lambda per series; P(by D) = 1 - E[exp(-lambda * days remaining)].
  Prior: pooled over OTHER series of the same type with close time before the forecast; events = series that resolved YES,
  exposure = days from listing to resolution (union of each series' resolved windows); log-normal, spread by the C1b moment
  formula (docs/c1b_prereg.md), mean-matched. Fewer than 3 series of the type: pool all war-outcome types; still fewer than 3:
  log-normal median 1/yr, log-sd 2.0 (stated now, before any data).
  Own evidence: the series' resolved earlier deadlines (exact likelihood, as C1). Close-time guard throughout.
Replay (REPORT ONLY; publication does not depend on it): each resolved contract priced 24h after listing vs the market at the
same moment; Brier, log loss, YES/NO, by type; cluster bootstrap by series.
Component war-outcome-v0; outside Tier 2 (own stratum).
Caveats stated in advance: v0 ignores distance to the front line, the obvious main driver of capture timing; resolution sources
differ by series (ISW map shading vs official announcements); one-shot series sharing an offensive are correlated.
