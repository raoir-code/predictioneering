# Holy Days: fast research result (H1, first pass)

Stop building validation infrastructure and run a complete *exploratory*
multiyear model. This makes an actual first numerical research finding,
subject to explicit scientific validity qualifications.

## Run (from ~/predictioneering-research-test)

~~~bash
git pull --ff-only
"$HOME/.venvs/predictioneering-research/bin/python" -m pip install -r research/requirements.txt
"$HOME/.venvs/predictioneering-research/bin/python" -m unittest discover -s research/tests -q
"$HOME/.venvs/predictioneering-research/bin/python" -m research.factory.holiday_study --fetch --env-file "$HOME/predictioneering/.env"
~~~

The runner needs only the existing local myACLED credentials. It reuses
the verified October 2024 pilot and fetches other months (2022-2025)
through OAuth and cursor pagination. Finished, hash-verified months are
cached and skipped on later runs. The process stores licensed ACLED raw
records only under ignored, private research/inbox/acled/holy_days/h1_multiyear.

The outcome is **daily counts of Israeli-Actor1 remote-weapons events in
Lebanon**, for exact-day ACLED air/drone strikes and shelling/missiles.
It includes dates with zero observed events and deliberately does NOT
relabel event location Lebanon as the adversary's actual actor identity.

The holiday calendar is generated independently using pyluach and a
predeclared Israel-local list: Rosh Hashanah I/II, Yom Kippur, Sukkot I,
Shemini Atzeret, Pesach I/VII, Shavuot. A separate previous-day exposure
accounts approximately for holidays beginning at sunset. The first
estimator is Poisson GLM with **calendar-month-by-year and weekday fixed
effects**, weekly clustered standard errors, and an additional +21 day
placebo date shift. Optional --sensitivity runs slower leave-one-year-out
fits. The result is exploratory/observational, NOT a causal estimate.

Local outputs (do not upload raw notes):
- H1_EXPLORATORY_RESULTS.json: coefficients, IRRs, CI and caveats;
- H1_EXPLORATORY_README.md: readable summary;
- H1_DAILY_PANEL_PRIVATE.csv: daily counts + holiday exposure;
- month-scoped private raw JSONL with hashes in MANIFEST.json.

Read the main model and placebo. Paste the *aggregate JSON output* into
chat, not raw JSONL, descriptions or reviewed CSV.

### Boundaries

This is H1 **only**: a first own-holiday restraint screen for Israel's
remote use of weapons in Lebanon. It does not yet measure religious
holidays of a verified adversary (H2), genuine signed holiday truces (H3),
or causally isolate holy days from endogenous preparations, conflict-phase
trends and reporting. Actor1-as-weapons-user remains an unverified
research proxy supported by a limited, AI-assisted local review.

The corrected bargaining no-war benchmark and proposed repeated-game
friction are in:
research/examples/holy_days_repeated_bargaining_model_v0.md

Sources: https://pyluach.readthedocs.io/en/latest/dates.html
ACLED attribution: Armed Conflict Location & Event Data Project (ACLED)
https://acleddata.com/
