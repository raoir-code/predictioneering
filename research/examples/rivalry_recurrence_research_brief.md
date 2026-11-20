# Research Factory pilot: War costs, commitment problems, and recurrence

**Status:** substantive research *candidate*, not an established gap or a verified finding.  
**Input:** local PDF excerpts from the November 20, 2026 Puzzle Finder bridge; local Zotero metadata screen (18 candidates) and hazard index screen (12 possible estimates). The 18/12 results are **candidates**, not vetted evidence. No external literature search was performed in the local-only run.

## Immediate novelty test (possible reason to kill)

Morey (2011), *When War Brings Peace*, **already proposes** that war costs concentrated in time reduce support for fighting and can end rivalry (indexed PDF p. 2, profile evidence `p2-8c697688d6`). The basic hypothesis "costly war causes peace" is **not a novel contribution**. Do not submit a manuscript around that simple result.

Colaresi and Thompson (2005), *Alliances, Arms Buildups and Recurrent Conflict*, test how crises, alliances, territorial disputes and buildups combine to escalate war (indexed PDF pp. 11, 17; provisional evidence `p11-922fd0dd22` and `p17-948f653cf7`). This is a complementary conditional escalation explanation, **not** evidence of a logical contradiction with Morey. Their dependent variable and risk set differ from post-war conflict recurrence.

The plausible new question is narrower: **When do concentrated war costs suppress future conflict despite persistent territorial/commitment problems, and when do they merely postpone renewed escalation?** A new mechanism or empirical benchmark must improve on Morey and the intervening recurrence/termination literature.

## Candidate mechanism — model to derive, not a solved equilibrium

Two states bargain repeatedly over a divisible issue. Each government decides whether to accept a peaceful division or escalate, conditional on state power, future commitment problems, accumulated rivalry and domestic support for fighting. An acute war imposes concentrated costs, lowering domestic willingness to fight, while unresolved territorial or power-transition commitment problems can preserve incentives for renewed crises. Domestic support may recover over time, potentially producing a **time-dependent** (not necessarily monotonic) recurrence risk.

A formal-model development pass should explicitly define:
- Players and timeline; whether both states can initiate a crisis, reject bargains, mobilize or fight
- Bargaining surplus, each side's war payoff, military power and enforceability of agreements
- Endogenous or exogenous cost intensity and what qualifies as "concentrated" costs
- State variables for rivalry, domestic support and unresolved commitment wedge
- Law of motion for political support, costs and interstate hostility
- Equilibrium concept and conditions for durable settlement versus temporary restraint
- Testable comparative statics, including the **interaction** between concentrated costs and unresolved commitment problems

**No theorem or equilibrium condition is claimed here.** Bas and Coe (2016), *A Dynamic Theory of Nuclear Proliferation and Preventive War*, is a *possible* reference for commitment/preventive incentives, not direct evidence of post-war rivalry dynamics. Their nuclear and wartime context requires an explicit transportability argument.

## Empirical and forecasting design

- **Unit and risk set:** dyad-war episodes, followed by a dyad-year/event-time panel; include nonrecurrent and right-censored cases. Carefully decide how to handle dyads with overlapping wars and multiple episodes.
- **Outcomes:** first renewed interstate militarized dispute or crisis within 1/3/5/10 years and time-to-next-dispute. Do **not** use a retrospectively defined "rivalry terminated after 10–15 years with no dispute" label as if it were observable at the prediction date.
- **Main candidate exposure:** war-cost concentration for **both states**, ideally casualties or losses per unit time relative to population/capability. A single total-casualties count is not equivalent to a concentration measure. Check the published source's actual operationalization before constructing it.
- **Moderators:** unresolved territorial claims, bargaining/commitment indicators, changing power, alliance asymmetries, prior crises, and settlement type. Record which indicators are observable at the forecast date.
- **Baselines:** prior crises/rivalry intensity, contiguity/territory, power ratio, war termination characteristics, calendar time. Fit discrete-time hazard or survival models with conflict/dyad dependence; avoid leakage between time splits.
- **Predictive test:** expanding-window out-of-sample forecasts; Brier score and calibration for fixed horizons, log score and survival calibration when appropriate. Ablate concentrated-cost terms and the interaction. Report uncertainty and subgroup sample sizes.
- **Causal limits:** neither baseline hazard estimates nor predictive lift establishes that war **caused** peace; war onset, severity, settlement and observation are endogenous. Only claim causal effects with separately justified identification.

## Evidence status and review priorities

| Source | Most relevant lead | Present verification |
|---|---|---|
| Morey (2011), pp. 2, 7, 10–11 indexed PDF | Cost concentration, domestic support, simulations / cases and subsequent rivalry | Verbatim quotes matched; interpretation, coding and statistical test unreviewed |
| Colaresi & Thompson (2005), pp. 11, 16–17 indexed PDF | Prior crises, alliances, arms buildups and war escalation | Verbatim quotes matched; methods and coefficients unreviewed |
| Tir & Jasinski (2008), pp. 18–19 indexed PDF | Domestic political diversion incentives | **Peripheral**: domestic ethnic repression, not direct dyadic recurrence evidence |
| Bas & Coe (2016), pp. 29–30 indexed PDF | Temporary incentives for preventive attacks during war | **Peripheral**: nuclear proliferation model, not recurrence test |

The local Zotero metadata screen surfaces **War as a Commitment Problem**, **Bargaining and War**, **How Initiators End Their Wars**, **The War Puzzle Revisited** and other potentially closer sources. Bibliographic hits are not full-text evidence. At least some of the 18 hits address unrelated cyber or macroeconomic topics: do not count all as relevant. The 12 hazard-index hits likewise need variables, outcomes and original study IDs inspected before reuse.

## Decision gate for pursuing a real paper

1. Examine **Morey (2011) fully**: what post-war effect is already estimated, unit and time at risk, causal claims and whether concentration × unresolved issues is already tested.
2. Screen the closest Zotero full texts, particularly war termination, commitment bargaining, rivalry recurrence and conditional escalation. If a published paper already answers the interaction question, **kill or reformulate** the pilot.
3. Establish availability of dyad-level war costs, duration, and subsequent crisis/dispute panel before committing to a causal study.
4. If the interaction is not preempted and data are viable, formulate and solve the repeated-bargaining model, then pre-register the observational and OOS predictive comparisons.

**Research Factory output:** a falsifiable, source-anchored paper candidate with clearly specified unknowns—not an automated novelty claim, solved mathematical model or completed paper.
