"""
News strike detector (Oct 20): a LIVE, walk-forward-clean observation stream for the fighting-state model.
Source: the pipeline's own daily headline caches, cache/gnews/<Dyad>_<YYYYMMDD>.json (written that morning: each file holds
only what existed then). An LLM labels each headline A_STRIKES_B / B_STRIKES_A / OTHER for the dyad, using Polymarket's
qualifying-action definition (air, drone or missile strike that HITS the territory). Interceptions, threats, ground clashes,
talks, strikes on third countries and recounted older events are OTHER. Labels cached per headline; fixed tests must pass first.
Day observation for direction X->Y on file day d: 1 if any headline labeled X->Y with publishedAt in [d-2, d]; 0 if the file
had headlines but none; None if no file or an empty file (no information, never 'quiet').
  python pilot/news_strikes.py --test | --label | --report
"""
import json, re, sys, glob, hashlib, time, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ceasefire_news as CN

ROOT = Path(__file__).resolve().parent.parent
LABELS = ROOT / "pilot" / "news_strike_labels.jsonl"
PROMPT_VERSION = "v2"   # v1 false positives: recounted strikes, wrong pair, wrong territory, unattributed, vague (Oct 20 review)
BATCH = 40
DYADS = {"Israel_Lebanon": ("Israel", "Lebanon"), "Saudi_Arabia_Yemen": ("Saudi Arabia", "Yemen"), "Israel_Syria": ("Israel", "Syria"),
         "Israel_Yemen": ("Israel", "Yemen"), "Israel_Iran": ("Israel", "Iran"), "Israel_Iraq": ("Israel", "Iraq"),
         "Iran_UAE": ("Iran", "United Arab Emirates"), "Iran_Bahrain": ("Iran", "Bahrain"), "Iran_Jordan": ("Iran", "Jordan"),
         "Iran_Iraq": ("Iran", "Iraq"), "Iran_Qatar": ("Iran", "Qatar"), "Iran_Kuwait": ("Iran", "Kuwait"), "Iran_Saudi_Arabia": ("Iran", "Saudi Arabia"),
         "Iran_Oman": ("Iran", "Oman"), "Iran_Egypt": ("Iran", "Egypt"), "Pakistan_Afghanistan": ("Pakistan", "Afghanistan"),
         "Eritrea_Ethiopia": ("Eritrea", "Ethiopia"), "Pakistan_Yemen": ("Pakistan", "Yemen")}
PEACEFUL = {"China_Taiwan": ("China", "Taiwan"), "US_Denmark": ("United States", "Denmark"), "China_Japan": ("China", "Japan"),
            "US_Panama": ("United States", "Panama"), "China_India": ("China", "India")}    # false-alarm calibration only
VALID = {"A_STRIKES_B", "B_STRIKES_A", "OTHER"}

PROMPT = """You are labeling news headlines for a conflict-forecasting system. Country A = {A}. Country B = {B}.
For EACH item choose exactly one label:
A_STRIKES_B: the item reports, AS NEW NEWS, that {A}'s forces carried out an air strike, drone strike or missile strike that HIT {B}'s territory within roughly 48 hours before publication.
B_STRIKES_A: the item reports, AS NEW NEWS, that {B}'s forces, or an armed group operating from {B}'s territory, carried out an air, drone or missile strike that HIT {A}'s territory within roughly 48 hours before publication.
Use a strike label ONLY if ALL hold: (1) the strike itself is the news, not background to a statement, interview, analysis, investigation, damage assessment or reaction; (2) the attacker is named in the item as that side; (3) the target country is named specifically, not "the region" or "Gulf neighbors"; (4) the strike hit that country's own territory, not its forces located inside another country; (5) the attacker is not a group operating from a third country; (6) a hit is reported, not only sirens, alerts or explosions heard.
OTHER: everything else, including interceptions, threats, ground fighting or artillery without an air/drone/missile strike, talks, sanctions, strikes on any third country, and older events recounted.
Judge only from the item's text. Return JSON only, one entry per item: {{"labels": [{{"i": 0, "label": "OTHER"}}, ...]}}

Items:
{items}"""

TESTS = [("Israel", "Lebanon", [("Israeli airstrike kills two in southern Lebanon village", "A_STRIKES_B"),
                                ("Israeli drone strike hits car near Tyre, Lebanese health ministry says", "A_STRIKES_B"),
                                ("Hezbollah fires rockets at northern Israel, army says", "B_STRIKES_A"),
                                ("Israel intercepts drone launched from Lebanon over the Galilee", "OTHER"),
                                ("Lebanon and Israel hold US-mediated talks on the border", "OTHER"),
                                ("Israeli jets strike targets near Damascus", "OTHER"),
                                ("Israeli troops clash with Hezbollah fighters in border village", "OTHER"),
                                ("Israeli PM threatens to hit Beirut if attacks continue", "OTHER")]),
         ("Iran", "United Arab Emirates", [("Iranian missiles strike port facility in the UAE, officials say", "A_STRIKES_B"),
                                           ("UAE condemns Iranian threats against Gulf shipping", "OTHER"),
                                           ("Iran fires missiles at Gulf states after US raids", "OTHER"),
                                           ("Sirens sound in Abu Dhabi as air defenses activated", "OTHER"),
                                           ("Iran-backed militias in Iraq launch drones at UAE oil site", "OTHER"),
                                           ("Iranian drone hits oil facility in Fujairah, UAE says", "A_STRIKES_B")]),
         ("Israel", "Lebanon", [("Minister recalls last year's Israeli strike on Beirut in parliament speech", "OTHER"),
                                ("Analysis: what Israel's strikes in Lebanon mean for the truce", "OTHER"),
                                ("Airstrike kills family in southern Lebanon village", "OTHER"),
                                ("Israeli drone hits Hezbollah fighters who crossed into northern Israel", "OTHER")])]

def key(t):
    return hashlib.sha1(re.sub(r"\s+", " ", (t or "").strip().lower()).encode()).hexdigest()[:16]

def classify(A, B, items):
    txt = "\n".join(f"[{j}] {t}" for j, t in enumerate(items))
    out = {int(x["i"]): x["label"] for x in CN.call(PROMPT.format(A=A, B=B, items=txt), CN.api_key())}
    assert set(out) == set(range(len(items))) and set(out.values()) <= VALID, f"bad response: {out}"
    return out

def test():
    ok = True
    for A, B, cases in TESTS:
        got = classify(A, B, [t for t, _ in cases])
        for j, (t, want) in enumerate(cases):
            good = got[j] == want; ok &= good
            print(f"  {'ok ' if good else 'BAD'} [{A}/{B}] want {want:12} got {got[j]:12} {t}")
    print(f"[news strike tests, prompt {PROMPT_VERSION}] {'ALL PASS' if ok else 'FAILED'}")
    return ok

def files(dyad):
    out = []
    for f in sorted(glob.glob(str(ROOT / "cache" / "gnews" / f"{dyad}_2026*.json"))):
        m = re.search(r"_(\d{8})\.json$", f)
        try:
            d = json.load(open(f)); arts = d.get("articles", d) if isinstance(d, dict) else d
        except Exception:
            arts = []
        out.append((dt.datetime.strptime(m.group(1), "%Y%m%d").date(), [a for a in arts if isinstance(a, dict) and a.get("title")]))
    return out

def load_labels():
    lab = {}
    if LABELS.exists():
        for l in LABELS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("prompt_version") == PROMPT_VERSION: lab[(r["dyad"], r["key"])] = r["label"]
    return lab

def label():
    lab = load_labels()
    with open(LABELS, "a") as fh:
        for dyad, (A, B) in ({**DYADS, **PEACEFUL} if '--with-peaceful' in sys.argv else DYADS).items():
            todo, seen = [], set()
            for d, arts in files(dyad):
                for a in arts:
                    k = key(a["title"])
                    if (dyad, k) not in lab and k not in seen: seen.add(k); todo.append(a["title"])
            for b in range(0, len(todo), BATCH):
                chunk = todo[b:b + BATCH]
                for attempt in (1, 2):
                    try: got = classify(A, B, chunk); break
                    except Exception as ex:
                        if attempt == 2: raise
                        print(f"  retry {dyad}: {ex!r}"); time.sleep(5)
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                for j, t in enumerate(chunk):
                    fh.write(json.dumps({"dyad": dyad, "key": key(t), "label": got[j], "prompt_version": PROMPT_VERSION, "title": t, "labeled_at": now}) + "\n")
                fh.flush()
            print(f"  {dyad}: {len(todo)} new headlines labeled", flush=True)

def day_obs(dyad, direction):
    """direction 'A_STRIKES_B' or 'B_STRIKES_A' -> {date: 1 | 0} (days with no file / empty file are absent = unobserved)."""
    lab = load_labels(); out = {}
    for d, arts in files(dyad):
        if not arts: continue
        hit = 0
        for a in arts:
            if lab.get((dyad, key(a["title"]))) == direction:
                try: pub = dt.date.fromisoformat(str(a.get("publishedAt"))[:10])
                except ValueError: pub = d
                if d - dt.timedelta(2) <= pub <= d: hit = 1
        out[d] = hit
    return out

def report():
    for dyad, (A, B) in {**DYADS, **PEACEFUL}.items():
        for dirn, (x, y) in (("A_STRIKES_B", (A, B)), ("B_STRIKES_A", (B, A))):
            o = day_obs(dyad, dirn); hits = [d for d, v in o.items() if v]
            tag = " (peaceful: every hit is a false alarm)" if dyad in PEACEFUL else ""
            print(f"  {x[:14]:15} -> {y[:22]:23} observed {len(o):3} days, strike reported on {len(hits):3}, latest {max(hits) if hits else '-'}{tag}")

if __name__ == "__main__":
    if "--test" in sys.argv: sys.exit(0 if test() else 1)
    elif "--label" in sys.argv: label()
    else: report()
