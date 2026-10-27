# Pre-registration: GDELT as a second, independent live source for seeing strikes (Oct 27, 2026)

Written before any GDELT data is compared with the reference. Scripts: `analysis/gdelt_pull.py` (download) and
`analysis/gdelt_detection.py` (test). Synthetic checks pass (`--synthetic`), and the real-data path was smoke-tested on
fabricated rows. Report only. Nothing here changes production.

## Why

`docs/detection_result.md`: our news stream sees too few strikes for silence to mean anything. Pooled d was 0.20, and
its misses come in clusters. By that study's pre-registered rule, quiet-day evidence waits for a second, independent
live source. GDELT is open, updates every 15 minutes and has history, so its d and alpha can be measured now, while the
local event data is still available.

## Data

- **GDELT 2.0 event files,** 2026-01-01 to 2026-10-16. Kept: CAMEO root code 19 ("fight"), where the acting
  country is in our country set and the event's location is a different country in the set.
- **Walk-forward:** an event counts on day f only if GDELT published it (`DATEADDED`) by 13:00 UTC on f, the time of the
  9am ET run. Its event date must be in [f-2, f], the same three-day window as the news stream.
- **Reference:** the same local offline event data and true-strike definition as `docs/detection_prereg.md` (state forces
  of X, air/drone strike or shelling/artillery/missile attack, located in Y).

## Estimands

The same as the first study:

- **d = P(GDELT hit on f | true strike in [f-2, f])**
- **alpha = P(GDELT hit on f | no true strike in [f-2, f])**

Both are computed per direction. Pooled numbers use contract directions (directions that strike contracts have priced)
whose target country has at least one event of any type in the local data since Jan 1, 2026. Directions whose target
the local data does not cover are listed and excluded; this fixes the first study's Pakistan and Ethiopia caveat.

## Choosing GDELT's evidence rule (on Jan 1 to Jun 30, 2026 only)

- **Candidate code sets:**
  - air/artillery: CAMEO base codes 194 and 195 (195 includes drones and precision-guided munitions, 1951 and 1952)
  - plus generic force: 190, 194 and 195
- **Candidate minimum article counts (k):** 1, 2, 3, 5 and 10.
- **Chosen:** the pair with the highest pooled Youden index (d − alpha) in the selection window.

## The test (once, on Jul 1 to the event data's last complete day)

1. **GDELT alone:** pooled d and alpha, with block-bootstrap intervals over (direction, ISO week).
2. **News or GDELT,** on days with a news file:
   - the combined d and alpha, and
   - whether misses are independent: P(GDELT miss | news missed) vs P(GDELT miss), on true-strike days.

## Decision rule (fixed now; the same thresholds as the first study)

- **GDELT alone may carry quiet-day evidence** in the next stage if its pooled d's lower 95% bound is at least 0.50 and
  its pooled alpha is at most 0.10.
- **Otherwise, the combination (news or GDELT) may**, if it meets the same two thresholds.
- **If neither passes,** quiet-day evidence stays off. The next candidate source gets its own pre-registration.
- **Passing permits only a pre-registered model stage** (the quiet-days plan, Part 4). That stage is tested and adopted
  by its own rule. Passing this test changes nothing in production by itself.

## Known limits

- **The reference is itself compiled from news,** and GDELT reads much of the same press. When both miss the same
  strike, d is overstated.
- **GDELT's actor coding is noisy.** Proxies and wrongly attributed actors add to alpha. The alpha threshold guards
  against that.
- **Licensing** of any live use of GDELT is the operator's decision. This test uses public files only.
