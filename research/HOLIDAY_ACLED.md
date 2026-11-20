# Holy Days and Hard Bargains: ACLED event pilot

Goal: test local access and direction coding, not estimate a holiday effect.
Existing analysis/acled_fetch.py uses OAuth and cursor-enabled pull_full, but its
FULL_KEEP fields omit event notes, source and source_scale. Older pull paths use
deprecated page pagination. This pilot changes no production forecasting code.

## Run in the research checkout

## Local Python dependency

The holiday ACLED pilot imports `requests`, matching the working production
fetcher. A bare Homebrew Python in the separate research checkout may not have
that package. Use an isolated virtual environment **outside the repository**:

~~~bash
python3 -m venv "$HOME/.venvs/predictioneering-research"
"$HOME/.venvs/predictioneering-research/bin/python" -m pip install -r research/requirements.txt
"$HOME/.venvs/predictioneering-research/bin/python" -m unittest discover -s research/tests -q
"$HOME/.venvs/predictioneering-research/bin/python" -m research.factory.holiday_acled --fetch --env-file "$HOME/predictioneering/.env"
~~~

If the import fails with `ModuleNotFoundError: No module named 'requests'`, the
API was **not** contacted; it is an installation issue, not a 403 or credential
failure. All other research modules remain standard-library based.

~~~bash
# Preview only, no network or credentials:
python3 -m research.factory.holiday_acled

# Fetch one month in Lebanon, 3 event types:
python3 -m research.factory.holiday_acled --fetch

# If credentials are in the separate production checkout:
python3 -m research.factory.holiday_acled --fetch --env-file "/path/to/production/.env"

# Test the code with mocked API responses:
python3 -m unittest discover -s research/tests -q
~~~

ACLED_USERNAME and ACLED_PASSWORD come from shell variables or a local .env
in the checkout root (or the file named by --env-file). Tokens/passwords
never appear in program output. Raw notes, event/source fields and actor
fields are retained solely in research/inbox/acled/holy_days, gitignored.
No call is made unless --fetch is present. Cached files are hash-checked;
--refresh forces re-fetch.

The pilot requests Battles, Explosions/Remote violence and Violence against
civilians, using OAuth bearer tokens, cursor pagination, bounded retries and
per-file manifests. It records query restrictions, rows, source attribution,
date-precision, and whether direction is known from ACLED coding rules.

CAUTION: Actor1 is normally NOT the aggressor. Only Violence against civilians
has a codebook rule that Actor2 is the civilian target. This does not establish
an interstate A->B attack or an actor's religion. A later validation and
actor-calendar mapping pass is needed before fitting directed pair-day models.
Historical samples can have revisions; recent days are excluded (>=7-day lag).

ACLED's November 2026 license requires attribution and authorization; it
restricts AI/ML use of its content without appropriate express permission.
Keep raw events and notes local and do not upload them to public GitHub,
ChatGPT, Claude or third-party API services without authorization.

Source: Armed Conflict Location & Event Data Project (ACLED)
https://acleddata.com
https://acleddata.com/api-documentation/elements-acleds-api
https://acleddata.com/methodology/acled-codebook
https://acleddata.com/eula


## HTTP 403 at OAuth login (November 20 follow-up)

The production fetcher in `analysis/acled_fetch.py` reportedly authenticated and
fetched six month/type extracts earlier the same day using Python `requests`,
with `username`, `password`, `grant_type=password`, and `client_id=acled`.
Its OAuth request contains **no** `scope` field and does **not** cache a token.

The initial research pilot instead used `urllib` (default Python-urllib User-Agent)
and returned HTTP 403. Adding `scope=authenticated` did not fix the problem,
so the research pilot now uses **the same requests-based transport and token
form as production**. A request-User-Agent / perimeter-security issue is
plausible but **not confirmed** by a four-way comparison. Do not assume
ACLED account consent or permissions are broken based on this one 403.

The research API fetch still requires `--fetch`; the production engine
and authentication module remain unchanged. If a 403 persists, check
environment-variable overrides and compare status codes using safe
local diagnostics; never print passwords, bearer tokens or raw event notes.

Run:

~~~bash
git pull --ff-only
python3 -m unittest discover -s research/tests -q
python3 -m research.factory.holiday_acled --fetch --env-file "$HOME/predictioneering/.env"
~~~


## First empirical data-quality gate: direction audit

The October 2024 Lebanon pilot retrieved 2,982 remote-violence and 64
battle records; 3,038 of 3,046 had precise event dates (99.7%). The
separate Violence against civilians query returned zero, which does
NOT mean no civilian injuries or deaths: ACLED counts remote attacks
harming civilians under Explosions/Remote violence in many cases.

Run this *offline* after downloading the pilot:

~~~bash
python3 -m research.factory.holiday_audit --review
~~~

The command checks raw file hashes, prints counts of usable exact dates,
source-note coverage, Actor2 coverage, subevents and most frequent
actor pairs, and writes a **private** direction-coding sample at
research/inbox/acled/holy_days/DIRECTION_REVIEW_PRIVATE.csv.
This worksheet contains licensed source notes and must **not** be
uploaded to chat, Anthropic, or GitHub unless ACLED rights allow it.
The worksheet's coding columns are deliberately blank; review notes
and record the *actual attacker and target* from source details.
Do not interpret actor1 as aggressor, or count remote-violence
observations as individual projectiles/strikes.

Only paste the command's aggregate JSON summary here. Do not paste
the CSV. The audit refuses to overwrite reviewed annotations unless
--overwrite-review is explicitly supplied. Zero evidence of direction
validity is not evidence against the paper: it tells us whether we need
different coding, additional sources, or a different feasible design.

The next *scientific* step, once direction can be measured, is to
expand beyond October 2024 to multiple holiday dates and years, and
fix a religious calendar/actor crosswalk before estimating effects.
