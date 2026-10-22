# Theory test 3 (pre-registered Oct 22, 2026): power shifts and episode duration (state vs state)

H4 (Powell 2006 commitment problem from shifting power; Fearon 1995): state-vs-state episodes in dyads with a larger recent
shift in relative military capability last longer, i.e. have a LOWER daily termination hazard.

Data: UCDP GED v26.1, state-based violence (type_of_violence = 1), date precision <= 3, dated by date_start; INTERSTATE dyads
only: side_b names a government ("Government of ..."). SIPRI Military Expenditure Database 1949-2025 v1.2, constant 2024 US$
(sha256 6cc3a30b1064f9f02e60236667eef82e08cad42910ce630909d004ad2c398a9d). A side listing several governments = sum of their
expenditure. GED government names map to SIPRI country names by stripping "Government of" and parentheticals, plus a small
alias lookup table; unmatched names are reported, never guessed.
Episodes, exclusions, gaps: exactly as test 2 (per dyad, event days split at gaps > G, G in {7, 14, 30}; episodes starting before
1992-01-01 excluded; episodes ending within G days of the data end excluded).
Power shift at an episode starting in year y: |log(M_a/M_b)[y-1] - log(M_a/M_b)[y-4]| (three-year change in the log expenditure
ratio). Episodes with any missing expenditure in those years are excluded and counted.
Model: discrete-time hazard logit, one row per episode-day, y = 1 on the episode's last day. Covariates: power shift,
|log(M_a/M_b)[y-1]| (power gap level), log(elapsed days), log(1 + prior episodes of the dyad), log(1 + dyad age in years).
Errors clustered by dyad.
Decision rule: H4 supported iff the power-shift coefficient is < 0 with p < 0.05 under ALL THREE gap definitions. Anything else
= not supported. Results reported in full either way, including n episodes, n dyads and exclusions.
Caveats stated in advance: interstate GED episodes are few (low power); military expenditure misses nuclear latency, the shift most
relevant to the Iran case that motivated this test.
If supported: any production use gets its own replay gate before shipping.
