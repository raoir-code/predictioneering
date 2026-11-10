"""Nov 10: label NNA articles (cache/nna/articles, from pilot/nna_fetch.py) for the NNA detection test
(docs/nna_detection_prereg.md). Prompt PROMPT_VERSION is frozen by the pre-registration commit: changing it means a new
version and a new hand-check. Labels go to cache/nna/labels.jsonl (local; gitignored with the rest of cache/).

  python3.11 pilot/nna_label.py --preview 2026-11-06 2026-11-08   label those days if needed, print them
  python3.11 pilot/nna_label.py 2026-07-01 2026-11-10              label every article in the range
  python3.11 pilot/nna_label.py --sample                           hand-check sample -> cache/nna/validation_sample.txt
  python3.11 pilot/nna_label.py --test                             offline tests
"""
import os, re, sys, json, glob, random, datetime as dt
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "cache" / "nna"
LABELS = CACHE / "labels.jsonl"
MODEL = "claude-sonnet-4-6"
PROMPT_VERSION = "nna-v1"
BATCH = 25
CLASSES = ("QUALIFYING", "BORDERLINE", "OTHER_ACTION", "NONE")
RANK = {c: i for i, c in enumerate(reversed(CLASSES))}          # NONE 0 < OTHER_ACTION 1 < BORDERLINE 2 < QUALIFYING 3

PROMPT = """You label news items from Lebanon's National News Agency (NNA). For each item, decide whether it reports an Israeli
military action in Lebanon, and of which kind, using these classes (they follow a prediction-market contract's rules):

QUALIFYING: an Israeli air strike or surface-to-surface missile strike that hit Lebanese land. Air strike = bombs, air-to-surface
missiles, or air-launched drones: warplane raids, airstrikes, air raids, a drone strike or drone-fired missile hitting a car,
house, motorcycle, people or an area. Surface-to-surface = one-way attack drones, cruise or ballistic missiles.
BORDERLINE: a drone dropping a small munition: a grenade, sound bomb, stun bomb, incendiary, or "explosive materials".
OTHER_ACTION: any other Israeli action in Lebanon: artillery or tank shells, mortars, shelling, machine-gun or small-arms fire,
demolitions or explosions set off by ground troops, incursions, sweeps, combing operations, bulldozing, arrests or abductions,
overflights, warplanes or drones circling, sound barrier breaks, flares, anti-tank guided missiles, FPV drones, short-range
loitering munitions, munitions intercepted before impact.
NONE: anything else, including Israeli strikes outside Lebanon, threats or statements, actions by Hezbollah or others,
casualty tolls or funerals that report no new action, and unrelated news.

Rules: "the enemy" in NNA means Israel. Only Lebanese land counts (not the sea, not the airspace). If an item reports several
actions, give the highest class (QUALIFYING > BORDERLINE > OTHER_ACTION > NONE).
event_day: "same" if the action happened on the publication day (Beirut time); "previous" if the text says it happened
yesterday or last night before midnight; "unclear" otherwise. Use "same" for NONE.

Return JSON only: {{"labels": [{{"i": 0, "cls": "QUALIFYING|BORDERLINE|OTHER_ACTION|NONE", "event_day": "same|previous|unclear",
"why": "at most 12 words"}}, ...]}} with one entry per item, in order.

Items:
{items}"""


def api_key():
    k = os.environ.get("ANTHROPIC_API_KEY")
    if k: return k
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            m = re.match(r"\s*ANTHROPIC_API_KEY\s*=\s*(.+)\s*$", line)
            if m: return m.group(1).strip('"').strip("'")
    raise SystemExit("ANTHROPIC_API_KEY not found in environment or .env")


def call(prompt, key):
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
                      json={"model": MODEL, "max_tokens": 4000, "temperature": 0,
                            "messages": [{"role": "user", "content": prompt}]}, timeout=180)
    r.raise_for_status()
    return "".join(b.get("text", "") for b in r.json()["content"])


def parse(text, n):
    """The last complete {"labels": [...]} object; validated to n entries with known classes."""
    dec = json.JSONDecoder()
    for i in [m.start() for m in re.finditer(r"\{", text)][::-1]:
        try:
            obj, _ = dec.raw_decode(text[i:])
        except Exception:
            continue
        if isinstance(obj, dict) and isinstance(obj.get("labels"), list):
            L = obj["labels"]
            if len(L) != n or any(x.get("cls") not in CLASSES or x.get("event_day") not in ("same", "previous", "unclear") for x in L):
                raise ValueError(f"bad labels: {len(L)} for {n} items")
            return sorted(L, key=lambda x: x.get("i", 0))
    raise ValueError("no labels object")


def articles(d0=None, d1=None):
    A = [json.loads(Path(f).read_text()) for f in glob.glob(str(CACHE / "articles" / "*.json"))]
    return sorted([a for a in A if a.get("beirut_day") and (d0 is None or d0 <= a["beirut_day"] <= d1)],
                  key=lambda a: (a["published_utc"], a["id"]))


def load_labels():
    out = {}
    if LABELS.exists():
        for line in LABELS.read_text().splitlines():
            if line.strip():
                x = json.loads(line)
                if x.get("v") == PROMPT_VERSION: out[x["id"]] = x
    return out


def beirut_hhmm(a):
    from zoneinfo import ZoneInfo
    return dt.datetime.fromisoformat(a["published_utc"].replace("Z", "+00:00")).astimezone(ZoneInfo("Asia/Beirut")).strftime("%H:%M")


def label(d0, d1, caller=None):
    done = load_labels(); todo = [a for a in articles(d0, d1) if a["id"] not in done]
    print(f"[nna-label] {d0}..{d1}: {len(todo)} articles to label ({PROMPT_VERSION})", flush=True)
    if not todo: return
    caller = caller or (lambda p, k=api_key(): call(p, k))
    LABELS.parent.mkdir(parents=True, exist_ok=True)
    with open(LABELS, "a") as f:
        for b in range(0, len(todo), BATCH):
            chunk = todo[b:b + BATCH]
            items = "\n".join(f"[{j}] (published {a['beirut_day']} {beirut_hhmm(a)} Beirut) {a['title']} -- {a['description'][:400]}"
                              for j, a in enumerate(chunk))
            for attempt in (1, 2, 3):
                try:
                    L = parse(caller(PROMPT.format(items=items)), len(chunk)); break
                except Exception as e:
                    print(f"[nna-label] batch {b // BATCH + 1}: attempt {attempt} failed ({e!r})", flush=True)
                    if attempt == 3: raise
            for a, x in zip(chunk, L):
                ev = a["beirut_day"]
                if x["event_day"] == "previous": ev = (dt.date.fromisoformat(ev) - dt.timedelta(days=1)).isoformat()
                f.write(json.dumps({"id": a["id"], "beirut_day": a["beirut_day"], "event_date": ev if x["event_day"] != "unclear" else a["beirut_day"],
                                    "event_day": x["event_day"], "cls": x["cls"], "why": str(x.get("why", ""))[:120], "v": PROMPT_VERSION}) + "\n")
            f.flush()
            print(f"[nna-label] {min(b + BATCH, len(todo))}/{len(todo)}", flush=True)


def day_hits(d0, d1, borderline_counts=False):
    """{day: True/False} for every day in range with at least one fetched article (days with none are unobserved)."""
    lab = load_labels(); seen, hit = set(), set()
    ok = {"QUALIFYING", "BORDERLINE"} if borderline_counts else {"QUALIFYING"}
    for a in articles(d0, d1):
        seen.add(a["beirut_day"]); x = lab.get(a["id"])
        if x and x["cls"] in ok and d0 <= x["event_date"] <= d1: hit.add(x["event_date"])
    return {d: d in hit for d in sorted(seen | hit)}


def preview(d0, d1):
    label(d0, d1); lab = load_labels()
    for a in articles(d0, d1):
        x = lab.get(a["id"], {})
        if x.get("cls", "NONE") != "NONE":
            print(f"  {a['beirut_day']} {beirut_hhmm(a)}  {x['cls']:12s} {x['event_day']:8s} {a['title'][:70]}  | {x['why']}")
    for d, h in day_hits(d0, d1).items():
        print(f"  {d}: {'HIT' if h else 'no qualifying strike reported'}"
              + ("  (borderline only)" if not h and day_hits(d0, d1, True).get(d) else ""))


def sample(seed=1110):
    lab = load_labels(); A = {a["id"]: a for a in articles()}
    rng = random.Random(seed); by = {c: [i for i, x in lab.items() if x["cls"] == c and i in A] for c in CLASSES}
    isr = [i for i in by["NONE"] if re.search(r"israel|enemy|drone|strike|raid|shell", (A[i]["title"] + A[i]["description"]).lower())]
    pick = [(c, i) for c, n, pool in (("QUALIFYING", 10, by["QUALIFYING"]), ("OTHER_ACTION", 10, by["OTHER_ACTION"]),
                                      ("BORDERLINE", 5, by["BORDERLINE"]), ("NONE", 5, isr or by["NONE"]))
            for i in rng.sample(pool, min(n, len(pool)))]
    rng.shuffle(pick); out = CACHE / "validation_sample.txt"
    with open(out, "w") as f:
        f.write(f"NNA labels ({PROMPT_VERSION}) hand-check: for each item, write AGREE or the class you would give.\n"
                "Classes: QUALIFYING (air strike / drone strike / missile on Lebanese land), BORDERLINE (drone drops a small munition),\n"
                "OTHER_ACTION (artillery, gunfire, demolition, incursion, overflight, ATGM, FPV...), NONE.\n\n")
        for k, (c, i) in enumerate(pick, 1):
            a, x = A[i], lab[i]
            f.write(f"{k:2d}. [{x['cls']} / {x['event_day']}] {a['beirut_day']}  {a['title']}\n    {a['description'][:400]}\n    you: \n\n")
    print(f"[nna-label] {len(pick)} items -> {out}")


def _tests():
    global LABELS, CACHE
    import tempfile
    CACHE = Path(tempfile.mkdtemp()); LABELS = CACHE / "labels.jsonl"; (CACHE / "articles").mkdir()
    arts = [("1", "2026-11-07T13:42:00.000Z", "Four artillery shells land in Beit Yahoun", "Israeli artillery fire."),
            ("2", "2026-11-07T16:30:00.000Z", "Israeli drone drops explosive materials", "A drone dropped explosive materials."),
            ("3", "2026-11-08T05:10:00.000Z", "Enemy drone strikes car in Bint Jbeil", "Last night an Israeli drone struck a car."),
            ("4", "2026-11-08T09:00:00.000Z", "Minister meets ambassador", "Talks.")]
    for i, pub, t, d in arts:
        day = dt.datetime.fromisoformat(pub.replace("Z", "+00:00")).astimezone(__import__("zoneinfo").ZoneInfo("Asia/Beirut")).date().isoformat()
        (CACHE / "articles" / f"{i}.json").write_text(json.dumps({"id": i, "url": "", "title": t, "description": d, "published_utc": pub, "beirut_day": day}))
    reply = ('Sure. {"labels": [{"i": 0, "cls": "OTHER_ACTION", "event_day": "same", "why": "artillery"},'
             '{"i": 1, "cls": "BORDERLINE", "event_day": "same", "why": "drone drop"},'
             '{"i": 2, "cls": "QUALIFYING", "event_day": "previous", "why": "drone strike last night"},'
             '{"i": 3, "cls": "NONE", "event_day": "same", "why": "politics"}]}')
    calls = []
    label("2026-11-07", "2026-11-08", caller=lambda p: calls.append(p) or reply)
    assert len(calls) == 1 and "[2] (published 2026-11-08 07:10 Beirut) Enemy drone strikes car" in calls[0], calls[0][-400:]
    lab = load_labels(); assert lab["3"]["event_date"] == "2026-11-07" and lab["2"]["cls"] == "BORDERLINE", lab
    assert day_hits("2026-11-07", "2026-11-08") == {"2026-11-07": True, "2026-11-08": False}
    label("2026-11-07", "2026-11-08", caller=lambda p: 1 / 0)                      # nothing left to label: no call
    try: parse('{"labels": [{"i": 0, "cls": "STRIKE", "event_day": "same"}]}', 1); raise AssertionError("bad class accepted")
    except ValueError: pass
    try: parse('{"labels": []}', 2); raise AssertionError("short list accepted")
    except ValueError: pass
    print("nna_label tests: OK")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a == ["--test"]: _tests()
    elif a[:1] == ["--preview"] and len(a) == 3: preview(a[1], a[2])
    elif a == ["--sample"]: sample()
    elif len(a) == 2: label(a[0], a[1])
    else: print(__doc__)
