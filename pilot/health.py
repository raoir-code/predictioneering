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
print("   complete:", "YES" if "Pipeline complete" in txt else "NO (still running, or died)")
print("   push:", "OK" if re.search(r"main -> main", txt) else ("FAILED" if re.search(r"Could not resolve|failed 5 times|rejected", txt) else "not seen"))
for tag, pat in (("during-war/unified", r"\[during-war\][^\n]*"), ("rules", r"\[rules\] stored[^\n]*"), ("news", r"new headlines labeled"),
                 ("policy", r"excluded by rule:[^\n]*"), ("scopes", r"resolved: *\d+"), ("meta", r"\[meta\] stored[^\n]*")):
    m = re.findall(pat, txt); print(f"   {tag:18} {m[-1] if m else 'NOT SEEN'}" + (f"  ({len(m)} dyads)" if tag == 'news' and m else ""))
errs = [l.strip() for l in txt.splitlines() if re.search(r"Traceback|ERROR|failed \(non-fatal\)|FAILED|Exception", l)]
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
