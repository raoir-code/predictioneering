"""
Offline refit of the unified world priors (docs/refit_prereg.md). Model and rules: analysis/world_fits.py, unchanged.
Input: data/external/local_full/*_explosions.jsonl (gitignored). Output: gitignored paths under pilot/local/.

  python analysis/refit_local.py --heldout      fit window ends 2026-06-30   -> pilot/local/heldout/
  python analysis/refit_local.py --production   fit window ends at the data's last complete day -> pilot/local/candidate/

Last complete day = the latest event date in the data minus 7 days (the newest week is still being coded; fixed before any fit).
Rows dated after the window end are dropped before pairs and classes are built (no future data in the held-out fit).
"""
import sys, json, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import world_fits as WF
from collections import defaultdict, Counter

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "external" / "local_full"
LOCAL = ROOT / "pilot" / "local"
HELDOUT_END = dt.date(2026, 6, 30)

def rows():
    for f in sorted(SRC.glob("*_explosions.jsonl")):
        for l in f.read_text().splitlines():
            if l.strip(): yield json.loads(l)

def last_complete_day():
    return max(dt.date.fromisoformat(r["event_date"][:10]) for r in rows()) - dt.timedelta(7)

def build(end):
    def _build():
        P = defaultdict(lambda: {"exact": set(), "inexact": set(), "tk": Counter(), "kind": None})
        for r in rows():
            d = dt.date.fromisoformat(r["event_date"][:10])
            if d > end or d < WF.D0: continue
            if r.get("sub_event_type") not in WF.SUBS or WF.MARITIME.search(r.get("country") or ""): continue
            key, kind = WF.ident(r.get("actor1"))
            if not key or key == r.get("country"): continue
            p = P[f"{key}->{r['country']}"]; p["kind"] = kind
            (p["exact"] if str(r.get("time_precision")) == "1" else p["inexact"]).add(d)
            t = WF.target_kind(r.get("actor2"))
            if t: p["tk"][t] += 1
        return P
    return _build

def run(end, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    WF.D1 = end; WF.build = build(end); WF.OUT = outdir / "priors_world.json"; WF.TAB = outdir / "world_fits.json"
    WF.main()
    d = json.loads(WF.OUT.read_text()); d["data"] = f"offline refit, window {WF.D0} .. {end}"; d["frozen"] = dt.date.today().isoformat()
    WF.OUT.write_text(json.dumps(d, indent=1) + "\n")
    print(f"\nwrote {WF.OUT} and {WF.TAB} (window {WF.D0} .. {end}; local only, gitignored)")

if __name__ == "__main__":
    if "--heldout" in sys.argv: run(HELDOUT_END, LOCAL / "heldout")
    elif "--production" in sys.argv:
        e = last_complete_day(); print(f"last complete day: {e}"); run(e, LOCAL / "candidate")
    else: print(__doc__)
