"""
Pilot event ledger, Israel -> Lebanon (During-War spec v0.4, frozen Oct 16 2026).

Read-only on production. Classifies each DISTINCT cached GNews headline once:
  - broad_fighting:    an actual use of force, Israel <-> armed actors in Lebanon, either direction
  - qualifying_strike: Polymarket daily-contract definition (Israel attacker + Lebanese land +
                       airstrike / SSM / one-way drone; artillery, FPV, ATGM, naval, intercepted excluded)
  - occurrence date range in Jerusalem time
A headline repeated within a file is kept once (dup_in_file counts copies). A headline already
classified on an earlier day reuses that label (reused=true) and is never a new event.
first_seen_at = cache file mtime. Writes pilot/ledger_israel_lebanon.jsonl. Resumable; fails closed.
"""
import argparse, json, os, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "gnews"
OUT = ROOT / "pilot" / "ledger_israel_lebanon.jsonl"
PROMPT_VERSION = "ledger-v2"
MODEL = "claude-sonnet-4-6"  # same as pipeline/translator.py CLAUDE_MODEL
LABEL_KEYS = ("broad_fighting", "qualifying_strike", "occurred_earliest", "occurred_latest",
              "initiator", "target_actor", "confidence", "reason")

PROMPT = """You are coding news headlines into an event ledger for one question: did Israel carry out a qualifying strike on Lebanese territory on a given day? Be strict: when a headline does not clearly report a specific use of force, both flags are false.

Definitions:
- broad_fighting: the headline reports an actual use of force between Israel and an armed actor in Lebanon, in either direction: a strike, shelling, a clash, a raid, or rockets or drones fired from Lebanon at Israel. NOT broad_fighting: occupation, obstruction, deployments, threats, statements, diplomacy, negotiations, funerals, casualty tallies with no new attack, weapons seizures, and anything outside Israel-Lebanon (Iran, Syria, Gaza, West Bank, attacks on US bases).
- qualifying_strike: ALL THREE must hold: (1) Israel is the attacker; (2) the target is on Lebanese land, with Lebanon or a Lebanese place named; (3) the weapon is an airstrike (bombs, air-to-surface missiles, air-launched drones) or a surface-to-surface missile or one-way attack drone that hit. NOT qualifying: artillery or shelling, small arms, ground incursions or demolitions, naval gunfire, FPV drones, anti-tank missiles, intercepted munitions. A headline saying only "Israeli strike(s)" on a named Lebanese place counts, with confidence "medium". If any condition is missing, qualifying_strike is false.
- A qualifying strike is always also broad_fighting. Broad fighting can occur without a qualifying strike (e.g. artillery only).
- occurred dates: the Jerusalem-time calendar day(s) the reported attack happened. Jerusalem is UTC+3 until 2026-10-25, then UTC+2. Use the text ("overnight", "on Tuesday", "earlier today") and publishedAt. An attack cannot occur after it was published. If unsure, give the widest honest range. Dates are null only when both flags are false.

Return ONLY a JSON array, one object per headline, in input order:
{"i": <index>, "broad_fighting": true|false, "qualifying_strike": true|false, "occurred_earliest": "YYYY-MM-DD"|null, "occurred_latest": "YYYY-MM-DD"|null, "initiator": "Israel"|"Hezbollah"|"other"|"unclear"|null, "target_actor": "Hezbollah"|"other_armed_group"|"lebanese_state"|"civilian_or_unclear"|null, "confidence": "high"|"medium"|"low", "reason": "<15 words max>"}

Headlines:
<<HEADLINES>>"""

def load_env():
    p = ROOT / ".env"
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

def key(a):
    return (a.get("title") or "").strip().lower()

def load_ledger():
    rows = [json.loads(l) for l in OUT.read_text().splitlines() if l.strip()] if OUT.exists() else []
    labels = {}
    for r in rows:
        if not r.get("reused"):
            labels.setdefault(r["title_key"], {k: r.get(k) for k in LABEL_KEYS})
    return {r["source_file"] for r in rows}, labels

def classify(client, arts):
    lines = "\n".join(
        f"[{i}] publishedAt={a.get('publishedAt')} | {a.get('title', '')} -- {a.get('description', '')}"
        for i, a in enumerate(arts))
    resp = client.messages.create(model=MODEL, max_tokens=6000,
        messages=[{"role": "user", "content": PROMPT.replace("<<HEADLINES>>", lines)}])
    text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text")
    import re
    m = re.search(r"\[\s*\{", text)
    if not m:
        raise ValueError("no JSON array in response")
    arr, _ = json.JSONDecoder().raw_decode(text[m.start():])
    if len(arr) != len(arts) or [r.get("i") for r in arr] != list(range(len(arts))):
        raise ValueError(f"output does not line up with input ({len(arr)} vs {len(arts)})")
    return arr

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="process at most N new files")
    args = ap.parse_args()
    load_env()
    import anthropic
    client = anthropic.Anthropic()
    OUT.parent.mkdir(exist_ok=True)
    done, labels = load_ledger()
    files = [p for p in sorted(CACHE.glob("Israel_Lebanon_*.json")) if p.name not in done]
    if args.limit:
        files = files[:args.limit]
    print(f"{len(done)} files already in ledger; processing {len(files)}")
    for p in files:
        raw = json.load(open(p))
        copies, uniq = {}, []
        for a in raw:
            k = key(a)
            copies[k] = copies.get(k, 0) + 1
            if copies[k] == 1:
                uniq.append(a)
        new = [a for a in uniq if key(a) not in labels]
        try:
            try:
                fresh = classify(client, new) if new else []
            except Exception:
                fresh = classify(client, new)  # one retry
        except Exception as ex:
            print(f"  {p.name}: FAILED CLOSED ({ex}) -- nothing written, rerun later")
            continue
        for a, lab in zip(new, fresh):
            labels[key(a)] = {k: lab.get(k) for k in LABEL_KEYS}
        file_date = f"{p.stem[-8:-4]}-{p.stem[-4:-2]}-{p.stem[-2:]}"
        seen = dt.datetime.fromtimestamp(p.stat().st_mtime, dt.timezone.utc).isoformat()
        new_keys = {key(a) for a in new}
        with open(OUT, "a") as f:
            for j, a in enumerate(uniq):
                f.write(json.dumps({
                    "headline_id": f"{file_date}-{j}", "source_file": p.name, "title_key": key(a),
                    "file_date_utc": file_date, "first_seen_at": seen,
                    "published_at": a.get("publishedAt"), "title": a.get("title"),
                    "description": a.get("description"), "dup_in_file": copies[key(a)],
                    "reused": key(a) not in new_keys, **labels[key(a)],
                    "prompt_version": PROMPT_VERSION, "model": MODEL}) + "\n")
        nq = sum(bool(labels[k].get("qualifying_strike")) for k in new_keys)
        nb = sum(bool(labels[k].get("broad_fighting")) for k in new_keys)
        print(f"  {p.name}: {len(raw)} raw | {len(uniq)} distinct | {len(new)} new | new broad {nb} | new qualifying {nq}")

if __name__ == "__main__":
    main()
