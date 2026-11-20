# Holy Days and Hard Bargains — Model 0: benchmark and identification

**Status:** An analytically checked starting point, **not a solved repeated-game equilibrium**, not a proof of all five hypotheses. This note specifies what has to be added before claiming that sacred holidays *cause* conflict onset, postponement, or truces.

## 1. A serious problem with the battle-plan's original ultimatum model

Let A's probability of prevailing in immediate conflict at date t be p_t, with winner-takes-all unit prize. Let h_{A,t}, h_{B,t} be indicators for each side's holiday, and let a_i >= 0 be additional own-holiday audience/fighting costs. Let c_i >= 0 be ordinary fighting costs. If B's holiday lowers B's combat readiness, it changes **both sides' probabilities**, not just A's, through p_t.

Correct outside options for fighting (ignoring time-discounted continuation for this static benchmark) are:

- W_A(t) = p_t - c_A - a_A h_{A,t} v_A
- W_B(t) = 1 - p_t - c_B - a_B h_{B,t} v_B

The original draft raised A's victory probability by delta on B's holiday but did **not** reduce B's own victory probability in B's rejection payoff. That violates consistency: the two winning probabilities must sum to one.

If A offers B x in an enforceable peaceful division of a unit prize, B accepts when x >= W_B. A prefers this deal over fighting if 1-x >= W_A. Thus a mutually acceptable peaceful bargain exists iff:

1 - W_A - W_B = c_A + c_B + a_A h_A v_A + a_B h_B v_B >= 0.

**Result:** With complete information, no indivisibility, no bargaining constraints and strictly positive fighting costs, *some peaceful bargain always exists*. Holiday asymmetries mostly shift the distribution of negotiated concessions. Simply changing p_t with holidays does NOT by itself imply more holiday attacks; the draft's H1/H2/H3 do not mathematically follow from the static benchmark.

## 2. An actual repeated bargaining game needs a friction

Make the date t public, with known deterministic religious calendars, and let h_t take four states:
(neither holiday), (A's only), (B's only), (both). The game continues each day, discount factor 0 < beta < 1. Each date each side can hold a fixed/contractual status quo, propose a temporary transfer or truce, accept/reject, or attack. An attack may cause a costly, persistent war state; a peaceful agreement may also require time to enforce.

At least one *explicit* friction is required for holiday-war predictions:
- private resolve/costs, so offers sometimes fail;
- commitment constraints, e.g. transfers cannot adjust daily or territory is indivisible;
- bargaining or mobilization deadlines;
- asymmetric information about whether the defender actually lowered its guard.

For a transparent **fixed-terms reduced-form strike threshold**, suppose A's peaceful continuation value P_A(t) is temporarily insensitive to the day's holiday. A launches if

  Delta_A(t) = p_t - c_A - a_A h_{A,t} v_A + W_A^war,continuation(t)
               - P_A(t) > 0.

For p_t = p_0 + d_B h_{B,t} - d_A h_{A,t}, and holding continuation terms fixed:

- own-holiday effect on strike incentive: -a_A v_A - d_A (negative);
- opponent-holiday effect: +d_B (positive);
- shared holiday: +d_B -d_A -a_A v_A, **not necessarily negative**.

This is a conditional strike-incentive result under a specific friction, **not an equilibrium frequency prediction**. Even predictable opponent-holiday vulnerability may disappear if the defender preemptively raises readiness, making d_B endogenous and history dependent. Shared-holiday *negotiated truces* additionally require both parties' participation and a formal agreement/enforcement mechanism; their sign must be derived, not asserted.

## 3. Measured hypotheses (first iteration)

**H1 (first-pass measurable):** On major Israeli Jewish religious holiday civil days, the count of Israeli weapons-use events within Lebanon differs from otherwise comparable days. The theory predicts restraint ONLY if public/audience costs or readiness reductions dominate competing considerations. The predeclared holiday set is Rosh Hashanah I/II, Yom Kippur, Sukkot I, Shemini Atzeret, Pesach I/VII and Shavuot (Israel calendar). Include a previous-day (sundown) sensitivity indicator. **This is not an Israel->Hezbollah directed-dyad estimate.**

**H2 (not yet identified):** Attacks on the target side's religious holidays require correctly identified *target-side* actor; the event country cannot stand in for the target's identity or religion.

**H3 (not yet identified):** A shared-holiday agreement requires a genuine, independent ceasefire-agreement dataset; a day with zero ACLED violence is *not* evidence of negotiated truce.

**H4/H5:** Learning and visibility require event histories/attribution salience and theoretically justified measure of publicity; victim fatalities or event category alone cannot index the entire mechanism.

## 4. Empirical deliverable now

The new **research-only** multiyear H1 runner downloads ACLED remote violence month-by-month with OAuth/cursor, maintains private hash-verified caches, builds zero-including daily counts, computes religious dates using pyluach, and fits an exploratory Poisson GLM with year-month/weekday fixed effects, weekly-clustered standard errors, a sundown-eve sensitivity, and a +21-day placebo. All source descriptions stay private.

Read the resulting _H1_EXPLORATORY_RESULTS.json_ as a **screening result** for whether this mechanism merits the full paper design, not as a publishable causal estimate. Main validity threats are conflict-phase dynamics, reporting-time changes, actor/country misclassification and date anticipation.

## 5. Next real research advancement

Once the first multiyear H1 estimate exists, compare attack rates under more credible date controls, a second theater, alternative observance definitions, and a genuinely solved repeated-bargaining game with one specified friction. Do not spend another cycle building intake infrastructure before recording the actual preliminary estimate.

Sources for the Jewish calendar implementation:
- https://pyluach.readthedocs.io/en/latest/dates.html
- https://www.hebcal.com/api-docs/
