# Holy Days and Hard Bargains: ACLED event pilot

Goal: test local access and direction coding, not estimate a holiday effect.
Existing analysis/acled_fetch.py uses OAuth and cursor-enabled pull_full, but its
FULL_KEEP fields omit event notes, source and source_scale. Older pull paths use
deprecated page pagination. This pilot changes no production forecasting code.

## Run in the research checkout

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
