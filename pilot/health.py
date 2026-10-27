"""
Morning health check (Oct 20). One screen: did the run finish and push, did each step run, any errors, who priced what,
biggest disagreements with the market, and expected excess Brier vs a calibrated market by pricing component.
  python pilot/health.py            latest run
"""
import json, re, glob, collections, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
log = sorted(glob.glob(str(ROOT / "logs" / "pipeline_*.log")))[-1]; txt = Path(log).read_text(errors="replace")
print(f"== run: {Path(log).name} | last written {dt.datetime.fromtimestamp(Path(log).stat().st_mtime):%m-%d %H:%M}")
start = dt.datetime.strptime(Path(log).stem.split("_", 1)[1], "%Y%m%d_%H%M%S")
hrs = (dt.datetime.fromtimestamp(Path(log).stat().st_mtime) - start).total_seconds() / 3600
print("   complete:", "FAILED (stale run, aborted before pricing)" if "STALE RUN" in txt else ("YES" if "Pipeline complete" in txt else "NO (still running, or died)"))
print(f"   started {start:%a %m-%d %H:%M}, ran {hrs:.1f}h" + ("  FAILED: over 3h" if hrs > 3 else "") + ("  FAILED: no run started today" if start.date() != dt.date.today() else ""))
print("   push:", "OK" if re.search(r"main -> main", txt) else ("FAILED" if re.search(r"Could not resolve|failed 5 times|! \[rejected\]|failed to push", txt) else "not seen"))
for tag, pat in (("during-war/unified", r"\[during-war\][^\n]*"), ("rules", r"\[rules\] stored[^\n]*"), ("news", r"new headlines labeled"),
                 ("policy", r"excluded by rule:[^\n]*"), ("scopes", r"resolved: *\d+"), ("meta", r"\[meta\] stored[^\n]*"),
                 ("strike|no war", r"\[strike\|no war\] empirical[^\n]*"), ("strike|war", r"\[strike\|war\] restored[^\n]*"),
                 ("feed sync", r"\[sync\] (?:prices refreshed|FAILED)[^\n]*"), ("new listings", r"\[sync\] appended[^\n]*"),
                 ("classify cache", r"\[cache\] \d+ from cache[^\n]*")):
    m = re.findall(pat, txt); print(f"   {tag:18} {m[-1] if m else 'NOT SEEN'}" + (f"  ({len(m)} dyads)" if tag == 'news' and m else ""))
# Step announcements ("[hh:mm:ss] ... ...") are not failures, even when they name one ("Retry markets left in ERROR").
errs = [l.strip() for l in txt.splitlines() if re.search(r"Traceback|ERROR|failed \(non-fatal\)|FAILED|Exception", l)
        and not re.match(r"^\[\d\d:\d\d:\d\d\] .*\.\.\.\s*$", l)]
print(f"   errors/failures: {len(errs)}"); [print("     ", e[:150]) for e in errs[-8:]]
feed = json.load(open(ROOT / "pipeline" / "classified_feed.json")); feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
today = dt.date.today().isoformat()
live = [m for m in feed if not m.get("resolved") and m.get("conditional_p") is not None and m.get("market_price") is not None and str(m.get("end_date"))[:10] >= today]
comp = collections.Counter(m.get("pricing_component", "engine") for m in live)
print(f"== {len(live)} live published markets by component: {dict(comp)}")
ex = collections.defaultdict(float)
for m in live: ex[m.get("pricing_component", "engine")] += (m["conditional_p"] - m["market_price"]) ** 2
print("   expected excess Brier vs a calibrated market:", {k: round(v, 2) for k, v in sorted(ex.items(), key=lambda kv: -kv[1])}, "total", round(sum(ex.values()), 2))
print("== biggest disagreements (|ours - market| > 0.35):")
for m in sorted(live, key=lambda m: -abs(m["conditional_p"] - m["market_price"]))[:12]:
    if abs(m["conditional_p"] - m["market_price"]) > 0.35:
        print(f"   {m.get('pricing_component', 'engine'):16} {(m.get('question') or '')[:62]:62} ours {m['conditional_p']:.2f} mkt {m['market_price']:.2f}")
# Stage times (Oct 27): the gap after each "[HH:MM:SS] ..." line is how long that step took. Slowest first.
stamps = [(dt.datetime.strptime(m.group(1), "%H:%M:%S"), m.group(2).strip()[:70]) for m in re.finditer(r"^\[(\d\d:\d\d:\d\d)\] (.*)$", txt, re.M)]
gaps = [((b[0] - a[0]).total_seconds() % 86400 / 60, a[1]) for a, b in zip(stamps, stamps[1:])]
print(f"== slowest steps (of {len(gaps)}; minutes):"); [print(f"   {g:6.1f}  {s}") for g, s in sorted(gaps, reverse=True)[:6]]


def pba_swings(rows, thresh=0.10):
    """P(B|A) moves > thresh between the last two runs on the same contract (the LLM re-estimates it when inputs change)."""
    runs = sorted({r["timestamp"] for r in rows})
    if len(runs) < 2: return []
    prev = {r["market_id"]: r for r in rows if r["timestamp"] == runs[-2]}
    out = []
    for r in rows:
        p = prev.get(r["market_id"])
        if r["timestamp"] != runs[-1] or not p or r.get("conditional_p") is None or p.get("conditional_p") is None: continue
        a, b = p.get("p_b_given_a"), r.get("p_b_given_a")
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(b - a) > thresh:
            out.append((r["market_label"], a, b, p["conditional_p"], r["conditional_p"]))
    return sorted(out, key=lambda x: -abs(x[2] - x[1]))


def _swing_tests():
    rows = [{"timestamp": "t1", "market_id": "1", "market_label": "A", "p_b_given_a": 0.41, "conditional_p": 0.39},
            {"timestamp": "t2", "market_id": "1", "market_label": "A", "p_b_given_a": 0.24, "conditional_p": 0.21},
            {"timestamp": "t1", "market_id": "2", "market_label": "B", "p_b_given_a": 0.50, "conditional_p": 0.10},
            {"timestamp": "t2", "market_id": "2", "market_label": "B", "p_b_given_a": 0.55, "conditional_p": 0.11}]
    assert pba_swings(rows) == [("A", 0.41, 0.24, 0.39, 0.21)]


_swing_tests()
plog = [json.loads(l) for l in open(ROOT / "predictions" / "log.jsonl") if l.strip()]
sw = pba_swings(plog)
print(f"== P(B|A) swings > 0.10 since the previous run: {len(sw)}  (LLM re-estimate; not a model change)")
for lab, a, b, ca, cb in sw[:8]:
    print(f"   {lab[:58]:58} P(B|A) {a:.2f}->{b:.2f}  published {ca:.2f}->{cb:.2f}")

# API spend (Oct 27): tokens per calling function from logs/api_usage_<run date>.jsonl; estimate only, the Console is authoritative.
import importlib.util as _iu
_sp = _iu.spec_from_file_location("pq_api_usage", ROOT / "pipeline" / "api_usage.py"); AU = _iu.module_from_spec(_sp); _sp.loader.exec_module(AU)
_us = AU.summary(ROOT / "logs" / f"api_usage_{start:%Y%m%d}.jsonl")
if not _us:
    print(f"== API spend: no usage log for {start:%m-%d} (it starts with the first run after the Oct 27 patch)")
else:
    print(f"== API spend {start:%m-%d}: ~${sum(v[3] for v in _us.values()):.2f} est. over {sum(v[0] for v in _us.values())} calls (Console is authoritative)")
    for (step, caller, model), (n, ti, to, usd) in sorted(_us.items(), key=lambda kv: -kv[1][3])[:8]:
        print(f"   ${usd:6.2f}  {n:4d} calls  {ti / 1e3:7.0f}k in {to / 1e3:6.0f}k out  {model.replace('claude-', ''):11} {step}:{caller}")
