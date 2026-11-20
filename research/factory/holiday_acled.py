"""Research-only ACLED event pilot for Holy Days and Hard Bargains.

Explicit --fetch required. Credentials read locally, never saved or logged.
Raw licensed events remain under ignored research/inbox/acled. No Claude calls,
forecasting-system changes, or automatic Actor1-is-attacker assumptions.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .__main__ import HOME

TOKEN_URL = "https://acleddata.com/oauth/token"
EVENT_URL = "https://acleddata.com/api/acled/read"
OUT = HOME / "inbox" / "acled" / "holy_days"
EVENT_TYPES = (
    "Explosions/Remote violence", "Battles", "Violence against civilians",
)
FIELDS = (
    "event_id_cnty", "event_date", "year", "time_precision", "event_type",
    "sub_event_type", "actor1", "assoc_actor_1", "inter1", "actor2",
    "assoc_actor_2", "inter2", "country", "admin1", "location",
    "fatalities", "source", "source_scale", "notes", "timestamp",
)
ATTRIBUTION = "Armed Conflict Location & Event Data Project (ACLED); https://acleddata.com"
RETRY_CODES = {429, 500, 502, 503, 504}


def credentials(env_file=None):
    """Explicit environment or local .env file; never send secret to stdout."""
    values = {k: os.environ.get(k) for k in ("ACLED_USERNAME", "ACLED_PASSWORD")}
    path = Path(env_file).expanduser() if env_file else HOME.parent / ".env"
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(r"^\s*(?:export\s+)?(ACLED_USERNAME|ACLED_PASSWORD)\s*=\s*(.*?)\s*$", line)
            if match and not values[match[1]]:
                values[match[1]] = match[2].strip().strip('"').strip("'")
    if not all(values.values()):
        raise ValueError(
            "ACLED credentials not found. Set ACLED_USERNAME and ACLED_PASSWORD "
            "in your shell or pass --env-file /path/to/existing/.env"
        )
    return values["ACLED_USERNAME"], values["ACLED_PASSWORD"]


def request_json(method, url, *, params=None, body=None, bearer=None):
    if params:
        url += "?" + urlencode(params)
    headers = {"Accept": "application/json"}
    if bearer:
        headers["Authorization"] = "Bearer " + bearer
    data = None
    if body is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = urlencode(body).encode("utf-8")
    req = Request(url, data=data, headers=headers, method=method)
    with urlopen(req, timeout=180 if method == "GET" else 60) as response:
        parsed = json.load(response)
    if not isinstance(parsed, dict):
        raise ValueError("ACLED response is not a JSON object")
    return parsed


def get_token(username, password):
    try:
        token = request_json("POST", TOKEN_URL, body={
            "username": username, "password": password,
            "grant_type": "password", "client_id": "acled",
            "scope": "authenticated",
        }).get("access_token")
    except HTTPError as exc:
        raise RuntimeError(
            "ACLED authentication failed: HTTP " + str(exc.code) +
            (". Check myACLED consent, mandatory profile fields, and API "
             "access permissions; do not share credentials or tokens."
             if exc.code == 403 else
             ". Verify username/password are current in myACLED.")
        ) from None
    if not isinstance(token, str) or not token:
        raise ValueError("ACLED login returned no access token")
    return token


def fetch_page(params, state, username, password, sleep=time.sleep):
    """Retry transient errors; re-authenticate only for a 401."""
    for attempt in range(5):
        try:
            payload = request_json("GET", EVENT_URL, params=params, bearer=state[0])
            if payload.get("success") is False:
                raise ValueError("ACLED response marked unsuccessful")
            if payload.get("status") not in (None, 200, "200", "success"):
                raise ValueError("ACLED response reported non-success status")
            return payload
        except HTTPError as exc:
            if exc.code == 401 and attempt < 4:
                state[0] = get_token(username, password)
                continue
            if exc.code not in RETRY_CODES or attempt == 4:
                raise RuntimeError("ACLED events request failed: HTTP " + str(exc.code)) from None
        except (TimeoutError, URLError):
            if attempt == 4:
                raise RuntimeError("ACLED events request timed out after retries") from None
        sleep(min(10 * 2 ** attempt, 80))
    raise RuntimeError("ACLED request retries exhausted")


def classify_direction(row):
    """ACLED codebook: Actor1 is not generally aggressor.

    Violence against civilians is the coding exception: Actor2 is the civilian
    target, so Actor1 is the perpetrator for this class. Other event types
    require independent review of source/notes and actor roles.
    """
    if row.get("event_type") == "Violence against civilians":
        return "actor1_targets_civilians_coding_rule"
    return "undetermined_requires_notes_review"


def safe_slug(value):
    slug = re.sub(r"[^a-z0-9]+", "_", value.casefold()).strip("_")
    if not slug:
        raise ValueError("Invalid country name")
    return slug


def validate_window(start, end, *, today=None):
    begin, finish = date.fromisoformat(start), date.fromisoformat(end)
    today = today or date.today()
    if begin > finish:
        raise ValueError("Start must not be after end")
    if finish > today - timedelta(days=7):
        raise ValueError("End date must be at least 7 days before today (coding lag)")
    if (finish - begin).days > 62:
        raise ValueError("Pilot must cover no more than 63 days")
    return begin, finish


def file_for(country, start, end, event_type, out=OUT):
    label = {
        "Explosions/Remote violence": "remote",
        "Battles": "battles",
        "Violence against civilians": "civilians",
    }[event_type]
    return out / (safe_slug(country) + "_" + start + "_" + end + "_" + label + ".jsonl")


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def atomic_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as f:
        tmp = Path(f.name)
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")
    tmp.replace(path)


def fetch_one(country, start, end, event_type, *, out=OUT, max_pages=20,
              limit=5000, state, username, password):
    """Complete cursor stream or fail without publishing partial output."""
    dest = file_for(country, start, end, event_type, out)
    dest.parent.mkdir(parents=True, exist_ok=True)
    seen_cursor, cursor = set(), None
    fetched, exact, undirected, civilian_direction, duplicate = 0, 0, 0, 0, 0
    seen_ids = set()
    restrictions = None
    pages = 0
    temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8",
                                         dir=dest.parent, delete=False) as fp:
            temp = Path(fp.name)
            while True:
                if pages >= max_pages:
                    raise RuntimeError("ACLED max-pages reached before terminal cursor; no partial file saved")
                q = {
                    "country": country,
                    "event_date": start + "|" + end,
                    "event_date_where": "BETWEEN",
                    "event_type": event_type,
                    "limit": limit,
                    "fields": "|".join(FIELDS),
                }
                if cursor is not None:
                    q["cursor"] = cursor
                payload = fetch_page(q, state, username, password)
                rows = payload.get("data")
                if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                    raise ValueError("ACLED returned invalid or missing data; no file committed")
                pages += 1
                if "next_cursor" not in payload and len(rows) >= limit:
                    raise ValueError("Missing next_cursor on full page; refusing truncated extract")
                if restrictions is None:
                    restrictions = payload.get("data_query_restrictions")
                elif payload.get("data_query_restrictions") != restrictions:
                    raise ValueError("Account restrictions changed within query")
                for row in rows:
                    eid = row.get("event_id_cnty")
                    if eid and eid in seen_ids:
                        duplicate += 1
                        continue
                    if eid:
                        seen_ids.add(eid)
                    selected = {k: row.get(k) for k in FIELDS}
                    selected["direction_status"] = classify_direction(selected)
                    exact += (str(selected["time_precision"]) == "1")
                    if selected["direction_status"].startswith("undetermined"):
                        undirected += 1
                    else:
                        civilian_direction += 1
                    fp.write(json.dumps(selected, ensure_ascii=False) + "\n")
                    fetched += 1
                nxt = payload.get("next_cursor")
                if not rows or nxt is None or nxt == "":
                    break
                if str(nxt) in seen_cursor:
                    raise RuntimeError("Repeated ACLED cursor; refusing incomplete extract")
                seen_cursor.add(str(nxt))
                cursor = nxt
        temp.replace(dest)
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
    restricted = bool(restrictions) and (
        any(bool(v) for v in restrictions.values()) if isinstance(restrictions, dict)
        else True
    )
    return {
        "country": country, "start": start, "end": end, "event_type": event_type,
        "file": str(dest), "sha256": checksum(dest),
        "rows": fetched, "pages": pages, "exact_day_rows": exact,
        "direction_unknown_rows": undirected,
        "coded_perpetrator_to_civilians_rows": civilian_direction,
        "duplicate_ids_skipped": duplicate,
        "has_account_query_restrictions": restricted,
        "data_query_restrictions": restrictions,
        "pulled_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }


def pilot(country, start, end, *, fetch=False, env_file=None, out=OUT,
          refresh=False, max_pages=20):
    validate_window(start, end)
    if not country.strip() or len(country) > 100:
        raise ValueError("Provide one country name")
    out = Path(out)
    manifest_path = out / "MANIFEST.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) \
        if manifest_path.exists() else {"attribution": ATTRIBUTION, "queries": {}}
    requests = []
    for event_type in EVENT_TYPES:
        file = file_for(country, start, end, event_type, out)
        key = file.name
        current = manifest["queries"].get(key)
        cached = bool(current and file.is_file()
                      and current.get("sha256") == checksum(file))
        requests.append((event_type, key, cached))
    if not fetch:
        return {
            "status": "dry_run_no_network",
            "country": country, "start": start, "end": end,
            "queries": [{"event_type": t, "already_cached": done}
                        for t, _, done in requests],
            "next_step": "Add --fetch to make ACLED API requests locally",
            "notes": "No credentials, raw data, or API calls sent to ChatGPT/GitHub.",
        }
    username = password = None
    state = None
    updates = []
    for event_type, key, cached in requests:
        if cached and not refresh:
            entry = dict(manifest["queries"][key], cache_status="cached")
        else:
            if state is None:
                username, password = credentials(env_file)
                state = [get_token(username, password)]
            entry = fetch_one(country, start, end, event_type, out=out,
                              max_pages=max_pages, state=state,
                              username=username, password=password)
            manifest["queries"][key] = entry
            atomic_json(manifest_path, manifest)
            entry = dict(entry, cache_status="new")
        updates.append({
            "event_type": event_type, "cache_status": entry["cache_status"],
            "rows": entry["rows"], "exact_day_rows": entry["exact_day_rows"],
            "direction_unknown_rows": entry["direction_unknown_rows"],
            "coded_perpetrator_to_civilians_rows":
                entry["coded_perpetrator_to_civilians_rows"],
            "pages": entry["pages"],
            "has_account_query_restrictions": entry["has_account_query_restrictions"],
        })
    return {
        "status": "local_acled_pilot_complete",
        "attribution": ATTRIBUTION,
        "country": country, "start": start, "end": end,
        "manifest": str(manifest_path),
        "queries": updates,
        "limitations": (
            "For Battles and Explosions/Remote violence, actor order DOES NOT "
            "identify who initiated an attack. Do not create a directed pair-day "
            "panel from raw Actor1 and Actor2. Notes and source detail require "
            "careful local coding; no data were transmitted to an LLM."
        ),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Bounded local ACLED holiday paper pilot")
    parser.add_argument("--country", default="Lebanon")
    parser.add_argument("--start", default="2024-10-01")
    parser.add_argument("--end", default="2024-10-31")
    parser.add_argument("--env-file", type=Path, help="Path to existing private production .env")
    parser.add_argument("--fetch", action="store_true", help="Authorize API requests")
    parser.add_argument("--refresh", action="store_true", help="Refresh existing local extracts")
    parser.add_argument("--max-pages", type=int, default=20)
    args = parser.parse_args(argv)
    try:
        if not 1 <= args.max_pages <= 50:
            raise ValueError("max-pages must be between 1 and 50")
        result = pilot(args.country, args.start, args.end, fetch=args.fetch,
                       env_file=args.env_file, refresh=args.refresh,
                       max_pages=args.max_pages)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, TypeError, KeyError) as exc:
        print("ACLED holiday pilot stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
