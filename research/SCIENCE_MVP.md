# Research Factory — fast MVP workflow

**Status:** runnable orchestration, **not** an autonomous scientist or a validated paper.
Data and paper drafts stay in private, gitignored local folders; no paid API calls.

## 1. One-time upgrade (preserves Holy Days revision 3 puzzle and revision 2 literature approvals)

```bash
cd ~/predictioneering-research-test
git pull --ff-only
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m unittest discover -s research/tests -q
"$P" -m research.factory.review_workflow activate-mvp holy-days
"$P" -m research.factory.science_mvp status holy-days
```

The opt-in **10-stage profile** is:

`puzzle → literature+contribution → formal_model → hypotheses → design → data → analysis → validation → manuscript → qc`

Existing Diagnosis/Novelty approval files and their hashes remain unchanged and readable.
It does **not** automatically claim that the current preliminary literature screen establishes novelty.

### Fastest visible demonstration (Holy Days, synthetic)

```bash
"$P" -m research.factory.paper_sprint holy-days-demo
```

Creates a real empirical calculation, two PDF figures, and an Overleaf ZIP under
`research/projects/factory_runs/holy_days_synthetic_demo/package/`, but all
**event dates and outcomes are fabricated**. The game is a conditional
inspection-game **candidate** and the holiday indicator is not a real holiday calendar.
It verifies indifference algebra from the actual 2x2 payoff matrix, not the
full equilibrium parameter domain or historical evidence.

We also committed `research/examples/HOLY_DAYS_2X2_MODEL_CANDIDATE.json` and
`research/examples/HOLY_DAYS_STUDY_CANDIDATE.json` as **reviewable starting
points only**. The latter requires an authorized private, direction-validated
interstate dyad-day risk panel and is not presently data-complete.

## 2. Continue a real project

Write an original `formal_model.json` with actual players, actions, timing, payoffs, equilibrium argument and comparative statics. Use `research/examples/FORMAL_MODEL_TEMPLATE.json` for **format only** (its game is synthetic). The formal model's equilibrium still requires independent proof.

```bash
"$P" -m research.factory.science_mvp produce holy-days formal_model --model /path/to/formal_model.json
```

Read `research/projects/factory_runs/holy-days/human_gates/review_packets/formal_model.md`.
To sign off: `"$P" -m research.factory.review_workflow approve holy-days formal_model --reviewer Researcher --notes "Checked the model and conditions."`

Subsequent steps run only after the previous stage has been explicitly approved:

| Ready stage | Command |
|---|---|
| `hypotheses` | `"$P" -m research.factory.science_mvp produce holy-days hypotheses` |
| `design` | `"$P" -m research.factory.science_mvp produce holy-days design --spec /path/to/study.json` |
| `data` | `"$P" -m research.factory.science_mvp produce holy-days data` |
| `analysis` | `"$P" -m research.factory.science_mvp produce holy-days analysis` |
| `validation` | `"$P" -m research.factory.science_mvp produce holy-days validation` |
| `manuscript` | `"$P" -m research.factory.science_mvp produce holy-days manuscript` |
| `qc` | `"$P" -m research.factory.science_mvp produce holy-days qc` |

The `study.json` must contain prespecified variables/estimation, and an authorized local CSV;
see `research/examples/factory_spec_template.json`. In MVP mode the **design is approved before data procurement**; the worker checks missing data at the data stage. Each stage produces a review packet and **stops without approval**. Commands use the exact hashed and human-approved artifacts from upstream stages.

## 3. Fast mechanical acceptance test

```bash
"$P" -m unittest discover -s research/tests -p 'test_science_mvp.py' -v
"$P" -m research.factory.paper_sprint demo
```

These generate synthetic data and a real Overleaf-ready ZIP; they do **not** prove a holiday model, validate causal identification, or establish novelty. `PAPER_QC.json` intentionally fails scientific signoff until original-paper, equilibrium, robustness and replication checks are independently completed.

**Current blockers for Holy Days:** full-text source/novelty audit, justified solved game, valid attacker–defender conflict data, honest identification, and human source/proof/results review. Do not publish a synthetic or unreviewed template as a scientific finding.
