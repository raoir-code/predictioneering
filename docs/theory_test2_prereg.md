# Theory test 2 (pre-registered Oct 21, 2026): recurrence and episode duration

H3 (Werner 1999; Fortna 2004; commitment-problem reading): episodes in pairs with more PRIOR episodes last
longer, i.e. have a LOWER daily termination hazard.

Data: UCDP GED v26.1, state-based violence only (type_of_violence = 1), events with date precision <= 3
(within about a week), dated by date_start.
Episodes: per UCDP dyad, event days split at gaps > G days, G in {7, 14, 30}. Episode end = last event day.
Exclusions: episodes starting before 1992-01-01 (burn-in so prior counts aren't truncated at the 1989 data
start); episodes ending within G days of the data end (right-censored).
Model: discrete-time hazard logit, one row per episode-day, y = 1 on the episode's last day.
Covariates: log(elapsed days), log(1 + prior episodes of the dyad), log(1 + dyad age in years).
Errors clustered by dyad.
Decision rule: H3 supported iff the prior-episodes coefficient is < 0 with p < 0.05 under ALL THREE gap
definitions. Anything else = not supported. Results reported in full either way.
If supported: the production use (prior episodes shifting each pair's war-length prior) gets its own
replay gate before shipping.
