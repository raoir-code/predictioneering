# Unified engine: past-day, unsettled dailies — pre-registered Oct 23, 2026, before any replay

Change: the unified engine also prices open daily contracts whose day has ended in the pair's time zone but which have not settled,
up to 3 days after the day (beyond that the onset engine keeps them, as now). Price = P(>= 1 qualifying strike on that day | all
evidence up to the forecast), from the same posterior (exact, last-strike-day tracking). The contract still being open is NOT used
as evidence (the resolution-delay model failed its rule on Oct 21). No change to any contract whose day has not ended.
Replay (REPORT ONLY; publication follows the change regardless, as for every in-scope contract): every resolved unified-group daily
that was still open 12 hours after its day ended is priced at that moment (outcomes usable only after their close time) and compared
with the market at the same moment; Brier, log loss, YES/NO split, by pair.
Scoring note: official scores anchor on the first forecast; this affects last-forecast scores only.
