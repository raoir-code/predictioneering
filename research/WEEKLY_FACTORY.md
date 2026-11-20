# Research Factory — local weekly operating loop v0.3

**Purpose:** Advance a growing queue of *researcher-supplied puzzle briefs* through existing intake approval, local bibliography screening, research-design review, statistical estimation and draft generation. The weekly runner is offline and makes **no Claude/API calls**, does not read production Predictioneering logs, and never runs automatically unless the researcher chooses to install a scheduler.

## One time: verify and prepare a private inbox

~~~bash
cd ~/predictioneering-research-test
git pull --ff-only
P="$HOME/.venvs/predictioneering-research/bin/python"
"$P" -m unittest discover -s research/tests -q
mkdir -p research/inbox/weekly
~~~

Put short, user-written **JSON puzzle briefs** in research/inbox/weekly/, one per file. Each requires: title, research_question, mechanism (or proposed_mechanism/candidate_mechanism) and testable_prediction (or hypotheses[0].prediction). Example:

~~~json
{
  "title": "Why do rivalries persist after ceasefires?",
  "research_question": "Under what conditions do nominal ceasefires coexist with repeated violence?",
  "mechanism": "Both parties may prefer a limited-violence equilibrium to total war.",
  "testable_prediction": "Higher enforcement asymmetry predicts lower retaliatory escalation."
}
~~~

The same folder can hold local .md/.txt worklogs, which will be **inventoried for review only**, not automatically sent to Claude or converted to unsupported research claims.

## Weekly commands

~~~bash
# Preview imports and statuses: absolutely no mutation, network or API costs.
"$P" -m research.factory.weekly plan --inbox research/inbox/weekly

# Explicitly import structured briefs and advance existing approved studies.
"$P" -m research.factory.weekly run --inbox research/inbox/weekly --execute

# Show all intake and workflow states without rerunning estimation.
"$P" -m research.factory.weekly status
~~~

run is resumable: duplicate briefs yield the same card ID and completed analysis is cached by source/spec/data hashes. New cards **always** stop before human intake approval. Approved cards advance to local literature and human novelty gates; pre-approved, correctly specified studies progress through estimation, OOS scoring and manuscript drafting. The report research/projects/factory_runs/weekly/weekly_YYYY-Www.json is private and overwritten within the same ISO week. Every individual project has its own workflow.json.

The preexisting CLI supplies necessary human gates:

~~~bash
"$P" -m research.factory list
"$P" -m research.factory approve 16_DIGIT_HEX_ID
"$P" -m research.factory.pipeline run 16_DIGIT_HEX_ID
~~~

Full-text novelty approval has a *separate, mandatory* research.factory.pipeline approve ... --full-text-checked step. See research/FACTORY_PIPELINE.md for details. Failure to verify novelty is not a software failure: the pipeline intentionally stops and reports the obligation.

## Optional Mac Monday 9 AM launchd definition (not installed)

~~~bash
"$P" -m research.factory.weekly make-launchd --inbox research/inbox/weekly
~~~

This writes a private, inert .plist for inspection. **Generating the file does not activate any scheduled job.** If the researcher elects to install it, they must review all paths/environment and manage launchd themselves. Unattended runs will still stop at human gates; no paid API or external data transfer is authorized by the scheduler.

## What is not solved

This is a weekly *operational* loop rather than an autonomous scientific discovery system. It does not automatically infer puzzles from raw forecast misses, generate/verify formal equilibria, choose exogenous identification strategies, retrieve full texts online, invent missing variables, or bypass human novelty/research-design checks. No manuscripts are declared publishable merely because an estimate is computed. Worklog-to-puzzle AI and autonomous source reading would require a separate design and explicit API/copyright/data permissions.
