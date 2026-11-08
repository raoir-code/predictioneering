# Directional P(B|A): result (prereg 64f739d, role labels a9393a3), Nov 8, 2026

OR (dyadic MID 3.1, disputes starting 1946-2010, primary initiators vs targets): initiator 0.900 (n=1219), target 0.585 (n=1223),
OR 0.156 [95% 0.118, 0.203]; tilt +/- 0.930 on the logit scale.

| gate | with | without | |
|---|---|---|---|
| (1) MID out of time: fit 1946-89, Brier on 1990-2010 directions (n=800) | role 0.1971 | pooled 0.2118 | PASS |
| (2) contract replay, 54 resolved (37 YES, 17 NO; 17 tilted: 15 initiator, 2 target) | 0.3373 | 0.3412 (market 0.1049) | PASS |

(2): Brier(with) - Brier(without) = -0.0039, cluster bootstrap by dyad 95% [-0.0144, +0.0003]. Log loss 1.012 vs 1.034 (market 0.342).
By role: initiator 0.4054 vs 0.4192 (n=15); target 0.0123 vs 0.0134 (n=2); unclear unchanged (n=37).
ADOPTION RULE -> adopted. Goes live with live role labels (as of the switch date) for every qualifying pair.

Reported, not gating: OR all years 0.097 [0.075, 0.124]; 1990-2010 only 0.276 [0.175, 0.416]; joiners included 0.181.

Reading: the pass is narrow. On this set the gap to the market (0.34 vs 0.10) is P(A), not P(B|A): Iran -> Iraq had P(A) 0.001-0.09 and
priced 0.006-0.41 against a market near 0.93, all YES. The tilt matters where P(A) is high (Saudi -> Iran today: P(A) 0.67, P(B|A)
0.48 -> 0.27 as target). The role gap shrinks over time (OR 0.10 before 1990, 0.28 in 1990-2010), so the pre-registered 1946-2010 OR
probably over-tilts today; a recent-era OR is a new pre-registration on new data, not a retry.
