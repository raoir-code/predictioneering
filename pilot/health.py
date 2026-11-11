"""
Morning health check (Oct 20). One screen: did the run finish and push, did each step run, any errors, who priced what,
biggest disagreements with the market, and expected excess Brier vs a calibrated market by pricing component.
  python pilot/health.py            latest run
"""
import json, re, glob, collections, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
import builtins as _bi
_OUT = []
def print(*a, **k):                        # Nov 11: keep every printed line, so the verdict at the end can list each FAILED / ACTION: line
    _OUT.append(" ".join(str(x) for x in a)); _bi.print(*a, **k)
log = sorted(glob.glob(str(ROOT / "logs" / "pipeline_*.log")))[-1]; txt = Path(log).read_text(errors="replace")
print(f"== run: {Path(log).name} | last written {dt.datetime.fromtimestamp(Path(log).stat().st_mtime):%m-%d %H:%M}")
start = dt.datetime.strptime(Path(log).stem.split("_", 1)[1], "%Y%m%d_%H%M%S")
hrs = (dt.datetime.fromtimestamp(Path(log).stat().st_mtime) - start).total_seconds() / 3600
print("   complete:", "FAILED (stale run, aborted before pricing)" if "STALE RUN" in txt else ("YES" if "Pipeline complete" in txt else "NO (still running, or died)"))
print(f"   started {start:%a %m-%d %H:%M}, ran {hrs:.1f}h" + ("  FAILED: over 3h" if hrs > 3 else "") + ("  FAILED: no run in the last 26h" if (dt.datetime.now() - start).total_seconds() > 26 * 3600 else ""))
print("   push:", "OK" if re.search(r"main -> main", txt) else ("FAILED" if re.search(r"Could not resolve|failed 5 times|! \[rejected\]|failed to push", txt) else "not seen"))
for tag, pat in (("during-war/unified", r"\[during-war\][^\n]*"), ("rules", r"\[rules\] stored[^\n]*"), ("news", r"new headlines labeled"),
                 ("policy", r"excluded by rule:[^\n]*"), ("scopes", r"resolved: *\d+"), ("meta", r"\[meta\] stored[^\n]*"),
                 ("strike|no war", r"\[strike\|no war\] empirical[^\n]*"), ("strike|war", r"\[strike\|war\] restored[^\n]*"),
                 ("feed sync", r"\[sync\] (?:prices refreshed|FAILED)[^\n]*"), ("new listings", r"\[sync\] appended[^\n]*"),
                 ("classify cache", r"\[cache\] \d+ from cache[^\n]*"), ("strike news", r"\[strike-news\] \d+ headlines fetched[^\n]*"),
                 ("scope rule", r"\[scope\] (?:de facto authority rule|rule FAILED)[^\n]*"), ("ceasefire tags", r"\[ceasefire\] tagged CORE[^\n]*")):
    m = re.findall(pat, txt); pick = (m[0] if tag == "classify cache" else m[-1]) if m else None   # cache: the sync/weekly line, not the retry step's 0/0
    if not pick and tag in ("feed sync", "new listings") and "Disciplinarian (full re-run" in txt:     # Nov 5: weekly days print no [sync] lines
        c = re.findall(r"Classifying \d+ markets", txt)
        pick = (f"weekly full re-run: {c[-1]}, complete" if "Classification complete" in txt and c else None)
    print(f"   {tag:18} {pick or 'NOT SEEN'}" + (f"  ({len(m)} dyads)" if tag == 'news' and m else ""))
# Step announcements ("[hh:mm:ss] ... ...") are not failures, even when they name one ("Retry markets left in ERROR").
errs = [l.strip() for l in txt.splitlines() if re.search(r"Traceback|ERROR|failed \(non-fatal\)|FAILED|Exception|\[strike-news\].*(?:failed|errors=)", l)
        and not re.match(r"^\[\d\d:\d\d:\d\d\] .*\.\.\.\s*$", l)]
print(f"   errors/failures: {len(errs)}"); [print("     ", e[:150]) for e in errs[-8:]]
# Nov 6 audit: messages that mean a component fell back or skipped work, but match none of the patterns above. Each is a counted
# degradation (the GNews HTTP 400 ran daily for weeks as "0 articles" because its line said "API error detail", not FAILED).
DEGRADED = (("market prices", r"\[warn\] (?:midpoints API returned|batch midpoints failed)"),
            ("context keeper", r"\[context_keeper\].*(?:after retry|Claude API error|generation call failed|not found, aborting)"),
            ("new dyad", r"NOT saved|LIKELY DUPLICATE DYAD"),
            ("news fetch", r"\[fetch_gnews\].*(?:WARNING: no query|FALLBACK --|NO FALLBACK)|\[error\] GNews failed"),
            ("node scoring", r"\[warn\] \u26a0|\[warn\] could not write"),
            ("resolver", r"\[resolver\] fetch failed|API failure, skipping"),
            ("dyad configs", r"not in dyad_registry|using fallback baseline"),
            ("state persistence", r"failed to persist"),
            ("translator", r"ontology error|\[coherence\] WARNING|fail-closed, no production|failed closed: [1-9]|\[during-war\] import failed|\[claude\] FAILED"),
            ("side steps", r"-- non-fatal|\(non-fatal[;)]|could not stage|\[talks\].* errors="))
deg = {tag: [l.strip() for l in txt.splitlines() if re.search(pat, l) and not re.match(r"^\[\d\d:\d\d:\d\d\] .*\.\.\.\s*$", l.strip())]
       for tag, pat in DEGRADED}   # step announcements are not failures (as for errs); end_date fallbacks are routine (Nov 6: 0 of 141 live contracts off by > 1 day)
print(f"   degraded (fallbacks): {sum(len(v) for v in deg.values())}" + "".join(f" | {t} {len(v)}" for t, v in deg.items() if v))
for t, v in deg.items():
    for e in v[-2:]: print(f"      [{t}] {e[:140]}")
plog = [json.loads(l) for l in open(ROOT / "predictions" / "log.jsonl") if l.strip()]
_last = max((r["timestamp"] for r in plog), default=None)
published = {str(r["market_id"]) for r in plog if r["timestamp"] == _last}   # Nov 2: NOISE markets carry a feed price but are never published
feed = json.load(open(ROOT / "pipeline" / "classified_feed.json")); feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
today = dt.date.today().isoformat()
live = [m for m in feed if not m.get("resolved") and m.get("conditional_p") is not None and m.get("market_price") is not None and str(m.get("end_date"))[:10] >= today and str(m.get("market_id")) in published]
comp = collections.Counter(m.get("pricing_component", "engine") for m in live)
print(f"== {len(live)} live markets published in the latest run, by component: {dict(comp)}")
ex = collections.defaultdict(float)
for m in live: ex[m.get("pricing_component", "engine")] += (m["conditional_p"] - m["market_price"]) ** 2
print("   expected excess Brier vs a calibrated market:", {k: round(v, 2) for k, v in sorted(ex.items(), key=lambda kv: -kv[1])}, "total", round(sum(ex.values()), 2))
_bad = [r for r in plog if r["timestamp"] == _last and r.get("bet_direction") in ("YES", "NO") and r.get("conditional_p") is not None
        and r.get("market_p") is not None and (r["bet_direction"] == "YES") != (r["conditional_p"] > r["market_p"])]
print(f"== bets against the published price: {len(_bad)}" + ("  FAILED: should be 0 (Nov 10)" if _bad else ""))
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
        k = "p_b_given_a_pre_role" if p.get("p_b_given_a_pre_role") is not None and r.get("p_b_given_a_pre_role") is not None else "p_b_given_a"
        a, b = p.get(k), r.get(k)              # Nov 11: both runs logged the pre-tilt value -> compare the LLM's own number, not the role tilt
        if isinstance(a, (int, float)) and isinstance(b, (int, float)) and abs(b - a) > thresh:
            out.append((r["market_label"], a, b, p["conditional_p"], r["conditional_p"]))
    return sorted(out, key=lambda x: -abs(x[2] - x[1]))


def _swing_tests():
    rows = [{"timestamp": "t1", "market_id": "1", "market_label": "A", "p_b_given_a": 0.41, "conditional_p": 0.39},
            {"timestamp": "t2", "market_id": "1", "market_label": "A", "p_b_given_a": 0.24, "conditional_p": 0.21},
            {"timestamp": "t1", "market_id": "2", "market_label": "B", "p_b_given_a": 0.50, "conditional_p": 0.10},
            {"timestamp": "t2", "market_id": "2", "market_label": "B", "p_b_given_a": 0.55, "conditional_p": 0.11}]
    assert pba_swings(rows) == [("A", 0.41, 0.24, 0.39, 0.21)]
    rows = [{"timestamp": "t1", "market_id": "3", "market_label": "C", "p_b_given_a": 0.30, "p_b_given_a_pre_role": 0.50, "conditional_p": 0.2},
            {"timestamp": "t2", "market_id": "3", "market_label": "C", "p_b_given_a": 0.30, "p_b_given_a_pre_role": 0.70, "conditional_p": 0.2},
            {"timestamp": "t1", "market_id": "4", "market_label": "D", "p_b_given_a": 0.50, "conditional_p": 0.2},
            {"timestamp": "t2", "market_id": "4", "market_label": "D", "p_b_given_a": 0.30, "p_b_given_a_pre_role": 0.50, "conditional_p": 0.2}]
    assert sorted(x[0] for x in pba_swings(rows)) == ["C", "D"]      # C: the LLM moved under an unchanged tilt; D: old row unlogged -> tilted vs tilted


_swing_tests()
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
try:                                                       # Nov 4: the honest scoreboard (pilot/fair_record.py)
    import sys as _s; _s.path.insert(0, str(ROOT / "pilot")); import fair_record as _FR
    print("== fair record (pre-event forecasts vs the market at the same moment; window contracts >= 72h before resolution):")
    [print(l) for l in _FR.report()]
except Exception as ex:
    print(f"== fair record FAILED: {ex!r}")


# Nov 11: autopilot checks. The machine should run for weeks on a weekly glance at this screen, so silent failures must print here.
import sys
print("== autopilot checks:")
_today = dt.date.today()
def _age(d):
    try: return (_today - dt.date.fromisoformat(str(d)[:10])).days
    except Exception: return None
# 1. Policy and state files: a missing or unreadable one silently switches a component off or back to its default.
_REQ = {"pipeline/episode_roles.json": "role-tilt labels", "pilot/unified_publish.json": "unified publishing policy",
        "pilot/holds_publish.json": "holds publishing", "pilot/c_policy.json": "agreement model choice",
        "pilot/during_war_config.json": "during-war pairs", "pipeline/theater_state.json": "theater state",
        "pipeline/node_memory_state.json": "node memory", "logs/node_scores_last_good.json": "node-score fallback cache"}
_files = {}
for _f in _REQ:
    try: _files[_f] = json.loads((ROOT / _f).read_text())
    except Exception as _ex: _files[_f] = None; print(f"   FAILED: {_f} ({_REQ[_f]}) unreadable: {type(_ex).__name__}")
print(f"   policy/state files readable: {sum(v is not None for v in _files.values())}/{len(_REQ)}")
if _files.get("pilot/unified_publish.json") is not None and not _files["pilot/unified_publish.json"].get("enabled"):
    print("   FAILED: pilot/unified_publish.json has enabled = false (the unified model publishes nothing)")
_lg = _files.get("logs/node_scores_last_good.json") or {}
_lg_age = min((a for a in (_age(v.get("as_of")) for v in _lg.values() if isinstance(v, dict)) if a is not None), default=None)
print(f"   node-score fallback cache: {len(_lg)} entries, newest {_lg_age} days old"
      + ("  ACTION: cache stale or empty, a failed node-scoring call would publish zeros" if _lg_age is None or _lg_age > 2 else ""))
# 2. Role-tilt labels (pipeline/episode_roles.json): valid, consistent, fresh, complete; and the tilt applied exactly once.
_R = _files.get("pipeline/episode_roles.json")
if _R is not None:
    _P = _R.get("pairs", {})
    _inval = sorted(k for k, v in _P.items() if (v or {}).get("role") not in ("initiator", "target", "unclear") or k.count("->") != 1)
    _contra = sorted({" / ".join(sorted((k, "->".join(k.split("->")[::-1])))) for k, v in _P.items() if k.count("->") == 1
                      and (v or {}).get("role") in ("initiator", "target")
                      and (_P.get("->".join(k.split("->")[::-1])) or {}).get("role") == v["role"]})
    _unl = re.findall(r"WARNING unlabeled pairs, no tilt: ([^\n]*)", txt)
    print(f"   role labels: {len(_P)} pairs as of {_R.get('as_of')}"
          + (f"  FAILED: invalid entries {_inval}" if _inval else "") + (f"  FAILED: both sides share a role: {_contra}" if _contra else "")
          + ("  ACTION: re-check the labels (monthly)" if (_age(_R.get("as_of")) or 0) > 35 else "")
          + (f"  ACTION: label these pairs: {_unl[-1]}" if _unl else ""))
try:
    sys.path.insert(0, str(ROOT / "pilot")); import directional_pba as _DP
    _tr = [r for r in plog if r["timestamp"] == _last and r.get("p_b_given_a_role") and r.get("p_b_given_a_pre_role") is not None]
    _off = [r["market_label"] for r in _tr if abs(round(_DP.tilt(r["p_b_given_a_pre_role"], r["p_b_given_a_role"].split(":")[-1]), 4) - r["p_b_given_a"]) > 1e-4]
    print(f"   role tilt applied once: {len(_tr) - len(_off)}/{len(_tr)} tilted contracts check out" if _tr else
          "   role tilt applied once: not logged yet (fields added Nov 11)")
    for _x in _off[:5]: print(f"   FAILED: tilt is not one step from the pre-tilt P(B|A) (compounding?): {_x[:90]}")
except Exception as _ex:
    print(f"   FAILED: role tilt check could not run ({_ex!r})")
# 3. Family tags: a ceasefire / agreement / withdrawal contract that lost its tag is priced by the onset engine (wrong model).
_untag = [r["market_label"] for r in plog if r["timestamp"] == _last and (r.get("pricing_component") or "engine") == "engine"
          and re.search(r"ceasefire|peace deal|agreement|truce|withdraw", r.get("market_label") or "", re.I)]
print(f"   family tags: {len(_untag)} ceasefire-like contracts priced by the onset engine" + ("  FAILED (tag missing)" if _untag else ""))
for _x in _untag[:5]: print(f"      {_x[:100]}")
# 4. Resolutions: contracts past their end date that the resolver hasn't closed (information; Polymarket can be slow).
_due = [m for m in feed if not m.get("resolved") and str(m.get("end_date") or "9999")[:10] < (_today - dt.timedelta(days=3)).isoformat()
        and str(m.get("market_id")) in {str(r["market_id"]) for r in plog}]
print(f"   unresolved > 3 days past their end date (published at least once): {len(_due)}")
# Verdict: every FAILED / ACTION: line printed above, in one place.
_flags = [l.strip() for l in _OUT if "FAILED" in l or "ACTION:" in l]
_ndeg = sum(len(v) for v in deg.values())
print("== VERDICT: " + ("all clear" if not _flags and not _ndeg else
                        f"{len(_flags)} line(s) to read" + (f", {_ndeg} degraded fallback(s) (see above)" if _ndeg else "")))
for _x in _flags[:15]: print("   " + _x[:160])
