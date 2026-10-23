# Theory test 4 (pre-registered Oct 23, 2026): does peace harden?

H5 (Werner 1999; Fortna 2004; Hartzell, Hoddie & Rothchild 2001): the hazard that a directed pair RESUMES cross-border strikes
declines with the time since its last fighting episode ended (the quiet-side counterpart of the duration dependence found in tests 1-3).
Data: the local offline pull (2015-01 -> last complete day), same strike filter and actor rules as the unified world fit
(air/drone + shelling/missile; initiator = a state's military, coalition or de facto authority, striking outside its own country).
Episodes per directed pair: strike days split at gaps > G days, G in {14, 30, 60}. Quiet spell = from the day after an episode's
last strike to the first strike of the next episode (event) or the data end (censored). A pair's first episode opens no spell.
Model: discrete-time hazard logit on WEEKS of quiet spells; y = 1 in the week the next episode starts. Covariates:
log(weeks since the spell began), log(1 + prior episodes of the pair), log(length in days of the episode that preceded the spell),
class (state_vs_state / cross_border_nonstate / defacto_authority / coalition, by the world-fit rule). Errors clustered by pair.
Decision rule: H5 supported iff the log(weeks since) coefficient is < 0 with p < 0.05 under ALL THREE G. Anything else = not
supported. Reported in full either way (spells, events, pairs, censoring).
Robustness (reported, not part of the rule): adding the pair's restart rate in spells that ended before this one, to separate true
hardening from heterogeneity (hostile pairs restart fast, so declining hazards can arise from selection alone).
If supported: production use (a quiet-state restart rate that depends on peace duration) gets its own pre-registered replay gate.
