"""docs/strike_feed_detection_prereg.md: does the new strike feed (pilot/strike_news_fetch.py, 95ef80c) see strikes well enough
for silence to count as quiet? Its query is backfilled day by day through GNews's historical search, labeled with the production
labeler (pilot/news_strikes.py, prompt v2), and scored against the local event data with the estimators of
analysis/detection_rate.py. Analysis only: files and labels go to pilot/local/ (gitignored), never to the production cache or
labels, so no engine evidence and no published price changes.
  --probe             one historical request (checks the plan serves past dates)
  --fetch [--max N]   backfill file days Jul 1 .. last complete event day; resumable; stops after N GNews calls (default 1500)
  --label             label new backfilled headlines (resumable)
  --measure           d, alpha, gates -> pilot/local/strike_feed_detection.json + printed summary
  --synthetic         offline checks
"""
import sys, os, json, time, random, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "analysis")); sys.path.insert(0, str(ROOT / "pilot"))
import detection_rate as DR, news_strikes as NS, strike_news_fetch as SF

START = dt.date(2026, 7, 1)
RUN_UTC = dt.time(13, 0)                                 # file day f = the 9am ET run: articles published in [f 13:00Z - 48h, f 13:00Z]
OUT = ROOT / "pilot" / "local" / "strike_backfill"; LABELS = ROOT / "pilot" / "local" / "strike_backfill_labels.jsonl"
GATE_D, GATE_A, MIN_SD = 0.50, 0.10, 5                   # pre-registered gates (see the pre-registration)

def window(f):
    to = dt.datetime.combine(f, RUN_UTC, dt.timezone.utc); return to - dt.timedelta(hours=SF.WINDOW_H), to

def path(dyad, f): return OUT / f"{dyad}_{f:%Y%m%d}.json"

def bf_files(dyad):
    out = []
    for p in sorted(OUT.glob(f"{dyad}_2026*.json")):
        d = json.loads(p.read_text()); f = dt.datetime.strptime(p.stem[-8:], "%Y%m%d").date()
        out.append((f, [a for a in d.get("articles", []) if a.get("title")] if not d.get("errors") else []))
    return out

def bf_labels():
    lab = {}
    if LABELS.exists():
        for l in LABELS.read_text().splitlines():
            if l.strip():
                r = json.loads(l)
                if r.get("prompt_version") == NS.PROMPT_VERSION: lab[(r["dyad"], r["key"])] = r["label"]
    return lab

def end_day():
    import refit_local as RL
    return RL.last_complete_day()

# ── fetch / label ────────────────────────────────────────────────────────────────────────────────────────────────────
def fetch(max_calls):
    SF.load_env(); import requests; key = os.environ["GNEWS_API_KEY"]; OUT.mkdir(parents=True, exist_ok=True)
    end = end_day(); calls = 0; f = START
    while f <= end:
        for dyad, (A, B) in NS.DYADS.items():
            p = path(dyad, f)
            if p.exists() and not json.loads(p.read_text()).get("errors"): continue
            if calls >= max_calls: print(f"[backfill] stopped at {max_calls} calls, next {dyad} {f}; re-run to continue"); return
            lo, hi = window(f); q = SF.query(A, B)
            arts, total, errors, pages = _collect(requests, key, q, lo, hi)
            calls += pages
            p.write_text(json.dumps({"query": q, "from": lo.isoformat(), "to": hi.isoformat(), "total_reported": total, "pages_read": pages,
                                     "errors": errors, "articles": [{"title": a.get("title"), "url": a.get("url"), "publishedAt": a.get("publishedAt")} for a in arts]}))
        if f.day == 1 or f == end: print(f"  [backfill] through {f}, {calls} calls this run", flush=True)
        f += dt.timedelta(1)
    print(f"[backfill] complete through {end}; {calls} calls this run")

def _collect(requests, key, q, lo, hi):
    """SF.collect with an explicit historical window (same paging and retries)."""
    base = {"q": q, "lang": "en", "max": SF.PER_PAGE, "sortby": "publishedAt", "apikey": key,
            "from": lo.strftime("%Y-%m-%dT%H:%M:%SZ"), "to": hi.strftime("%Y-%m-%dT%H:%M:%SZ")}
    arts, total, seen, page = [], None, set(), 0
    for page in range(1, SF.MAX_PAGES + 1):
        b = None
        for attempt in (1, 2, 3):
            try: b = requests.get("https://gnews.io/api/v4/search", params={**base, "page": page}, timeout=30).json(); break
            except Exception: time.sleep(2 * attempt)
        if b is None or b.get("errors"): return arts, total, (b or {}).get("errors") or "request failed", page
        total = b.get("totalArticles", total)
        batch = [a for a in b.get("articles", []) if a.get("url") not in seen]
        if not batch: break
        for a in batch: seen.add(a.get("url")); arts.append(a)
        if total is not None and len(arts) >= total: break
        time.sleep(1)
    time.sleep(1)
    return arts, total, None, page

def label():
    lab = bf_labels()
    with open(LABELS, "a") as fh:
        for dyad, (A, B) in NS.DYADS.items():
            todo, seen = [], set()
            for f, arts in bf_files(dyad):
                for a in arts:
                    k = NS.key(a["title"])
                    if (dyad, k) not in lab and k not in seen: seen.add(k); todo.append(a["title"])
            for b in range(0, len(todo), NS.BATCH):
                chunk = todo[b:b + NS.BATCH]
                for attempt in (1, 2):
                    try: got = NS.classify(A, B, chunk); break
                    except Exception as ex:
                        if attempt == 2: raise
                        time.sleep(5)
                now = dt.datetime.now(dt.timezone.utc).isoformat()
                for j, t in enumerate(chunk):
                    fh.write(json.dumps({"dyad": dyad, "key": NS.key(t), "label": got[j], "prompt_version": NS.PROMPT_VERSION, "title": t, "labeled_at": now}) + "\n")
                fh.flush()
            print(f"  {dyad}: {len(todo)} labeled", flush=True)

# ── measure ──────────────────────────────────────────────────────────────────────────────────────────────────────────
def files_for(dyad, direction, lab, end):
    out = {}
    for f, arts in bf_files(dyad):
        if f > end: continue
        pubs = []
        for a in arts:
            if lab.get((dyad, NS.key(a["title"]))) == direction:
                try: pubs.append(dt.date.fromisoformat(str(a.get("publishedAt"))[:10]))
                except ValueError: pubs.append(f)
        out[f] = (len(arts), pubs)
    return out

def macro_boot(tables, B=2000, seed=13):
    """Mean of per-direction d over directions with >= MIN_SD strike days; bootstrap over (direction, ISO week) blocks."""
    def macro(rows_by):
        ds = [sum(o for s, o in r if s) / n for r in rows_by.values() if (n := sum(1 for s, _ in r if s)) >= MIN_SD]
        return sum(ds) / len(ds) if ds else None
    point = macro({k: [(s, o) for _, s, o in t] for k, t in tables.items()})
    blocks = defaultdict(list)
    for k, t in tables.items():
        for f, s, o in t: blocks[(k, f.isocalendar()[:2])].append((s, o))
    keys = list(blocks); rnd = random.Random(seed); vals = []
    for _ in range(B):
        by = defaultdict(list)
        for kk in (rnd.choice(keys) for _ in keys): by[kk[0]] += blocks[kk]
        m = macro(by)
        if m is not None: vals.append(m)
    vals.sort(); return point, ((round(vals[int(0.025 * len(vals))], 3), round(vals[int(0.975 * len(vals)) - 1], 3)) if vals else None)

def verdict(d_ci, a_ci, macro_ci):
    if not d_ci or not a_ci or not macro_ci: return "INCONCLUSIVE"
    return "PASS" if d_ci[0] >= GATE_D and a_ci[1] < GATE_A and macro_ci[0] >= GATE_D else "FAIL"

def measure():
    end = end_day(); lab = bf_labels(); T = DR.truth_days(DR.PRIMARY, end); C = DR.contract_directions()
    tables, old, res = {}, {}, {"end": str(end), "directions": {}}
    for dyad, (A, B) in NS.DYADS.items():
        for dirn, (x, y) in (("A_STRIKES_B", (A, B)), ("B_STRIKES_A", (B, A))):
            fl = files_for(dyad, dirn, lab, end)
            if not fl: continue
            name = f"{x}->{y}"; t = DR.day_table(T.get((x, y), set()), fl); r = DR.rates(t)
            r["d_ci"] = DR.jeffreys(r["hits_on_strike_days"], r["n_strike_days"]); r["persistence"] = DR.persistence(t)
            ofl = {f: v for f, v in DR.news_files(dyad, dirn).items() if f in fl}       # old stream, same days, for comparison
            r["old_stream"] = DR.rates(DR.day_table(T.get((x, y), set()), ofl)) if ofl else None
            res["directions"][name] = r
            if name in C: tables[name] = t
    rows = [row for t in tables.values() for row in t]; p = DR.rates(rows); p["d_ci"], p["alpha_ci"] = DR.cluster_boot(tables)
    p["macro_d"], p["macro_d_ci"] = macro_boot(tables); res["pooled"] = p; res["pooled_over"] = sorted(tables)
    res["verdict"] = verdict(p["d_ci"], p["alpha_ci"], p["macro_d_ci"])
    (ROOT / "pilot" / "local" / "strike_feed_detection.json").write_text(json.dumps(res, indent=1, default=str))
    print(f"[strike-feed detection] event data through {end}; pooled over {len(tables)} contract directions")
    print(f"  pooled d {p['d']:.3f} {p['d_ci']} | alpha {p['alpha']:.3f} {p['alpha_ci']} | macro d {p['macro_d']} {p['macro_d_ci']}")
    print(f"  {'direction':30} {'strike d':>8} {'d':>6} {'95%':>14} {'alpha':>6} {'old d':>6} {'P(miss|miss)':>12}")
    for n, r in sorted(res["directions"].items(), key=lambda kv: -kv[1]["n_strike_days"]):
        od = r["old_stream"]["d"] if r["old_stream"] and r["old_stream"]["d"] is not None else None
        pm = r["persistence"]
        print(f"  {n[:30]:30} {r['n_strike_days']:8d} {(r['d'] or 0):6.2f} {str(r['d_ci']):>14} {(r['alpha'] or 0):6.3f} "
              f"{(f'{od:.2f}' if od is not None else '-'):>6} {str(pm['p_miss_after_miss']):>6} vs {pm['p_miss']}" + ("" if n in tables else "  (not pooled)"))
    print(f"  VERDICT (d lower >= {GATE_D}, alpha upper < {GATE_A}, macro d lower >= {GATE_D}): {res['verdict']}")

# ── synthetic ────────────────────────────────────────────────────────────────────────────────────────────────────────
def synthetic():
    global OUT, LABELS
    ok = True
    def chk(name, cond, detail):
        nonlocal ok; ok &= bool(cond); print(f"  {'PASS' if cond else 'FAIL'}  {name}: {detail}")
    lo, hi = window(dt.date(2026, 8, 3))
    chk("window = 48h ending 13:00Z on the file day", hi.isoformat() == "2026-08-03T13:00:00+00:00" and (hi - lo) == dt.timedelta(hours=48), f"{lo} .. {hi}")
    chk("output stays in pilot/local", str(OUT).startswith(str(ROOT / "pilot" / "local")) and str(LABELS).startswith(str(ROOT / "pilot" / "local")), str(OUT))
    import tempfile
    o0, l0 = OUT, LABELS; OUT = Path(tempfile.mkdtemp()); LABELS = OUT / "lab.jsonl"
    try:
        A = lambda t, p: {"title": t, "publishedAt": p, "url": t}
        path("X_Y", dt.date(2026, 8, 1)).write_text(json.dumps({"articles": [A("x strikes y", "2026-08-01T05:00Z"), A("talks", "2026-08-01T06:00Z")]}))
        path("X_Y", dt.date(2026, 8, 2)).write_text(json.dumps({"errors": "quota", "articles": [A("lost", "2026-08-02T01:00Z")]}))
        path("X_Y", dt.date(2026, 8, 3)).write_text(json.dumps({"articles": []}))
        LABELS.write_text(json.dumps({"dyad": "X_Y", "key": NS.key("x strikes y"), "label": "A_STRIKES_B", "prompt_version": NS.PROMPT_VERSION}) + "\n")
        fl = files_for("X_Y", "A_STRIKES_B", bf_labels(), dt.date(2026, 8, 31))
        chk("labels joined; error days unobserved", fl[dt.date(2026, 8, 1)] == (2, [dt.date(2026, 8, 1)]) and fl[dt.date(2026, 8, 2)] == (0, []), f"{fl}")
        t = DR.day_table({dt.date(2026, 8, 1)}, fl)
        chk("empty and error days skipped by day_table", len(t) == 1 and t[0][1] and t[0][2], f"{t}")
    finally:
        OUT, LABELS = o0, l0
    rnd = random.Random(2); D0 = dt.date(2026, 7, 1)
    def tab(d, a): return [(D0 + dt.timedelta(i), s, (rnd.random() < (d if s else a))) for i in range(100) for s in [rnd.random() < 0.4]]
    good = {f"p{i}": tab(0.85, 0.03) for i in range(6)}; bad = {f"p{i}": tab(0.3, 0.03) for i in range(6)}
    v1 = verdict(*DR.cluster_boot(good, B=300), macro_boot(good, B=300)[1]); v2 = verdict(*DR.cluster_boot(bad, B=300), macro_boot(bad, B=300)[1])
    chk("good stream passes, blind stream fails", v1 == "PASS" and v2 == "FAIL", f"{v1}, {v2}")
    print("SYNTHETIC:", "ALL PASS" if ok else "FAILED"); return ok

if __name__ == "__main__":
    a = sys.argv
    if "--synthetic" in a: sys.exit(0 if synthetic() else 1)
    elif "--probe" in a:
        SF.load_env(); import requests; lo, hi = window(dt.date(2026, 7, 15))
        print(_collect(requests, os.environ["GNEWS_API_KEY"], SF.query("Israel", "Lebanon"), lo, hi)[1:], "(total, errors, pages) for Israel-Lebanon, Jul 13-15")
    elif "--fetch" in a: fetch(int(a[a.index("--max") + 1]) if "--max" in a else 1500)
    elif "--label" in a: label()
    elif "--measure" in a: measure()
    else: print(__doc__)
