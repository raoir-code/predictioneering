# Refit of the unified engine's world priors — pre-registered Oct 23, 2026, before any refit is run

What changes: analysis/world_fits.py's model, pair rules, classes and pooling are unchanged. Two inputs change:
  (1) data: an offline worldwide pull, 2015-01 -> 2026-10, same event filter as the current fit (air/drone + shelling/missile,
      actor1 = a state's military or coalition outside its own country); kept locally, never committed;
  (2) the fit window ends at the last complete day of the data, not a fixed date (the current fit counts ~70 days after its data
      ended, Oct 21 - Dec 31 2025, as quiet days for every pair).
Held-out validation (leakage guard): a HELD-OUT fit ends 2026-06-30. The unified replay (same machinery as production: each resolved
contract priced at production's first-forecast time, outcomes usable only after their close time) is run on contracts whose first
forecast is on or after 2026-07-01, under (a) the current repo priors and (b) the held-out priors; both vs the market at the same
moment. Brier and log loss, YES/NO split, by pair; cluster bootstrap by pair (2,000 draws) of Brier(b) - Brier(a).
Adoption rule: the PRODUCTION fit (window to the data's last complete day) goes live iff Brier(b) <= Brier(a) on that replay;
otherwise the current priors stay. The unified publish policy then recomputes by its existing rule (no hand edits).
Outputs: written only to gitignored local paths (pilot/local/), read by the engine when present. Reported regardless of outcome.
