"""docs/hardening_prereg.md: beta (theory test 4's ROBUST G = 30 coefficient) and K (exposure-weighted mean of t^beta over quiet
spell-weeks), from the local data. Gitignored outputs:
  python analysis/hardening_fit.py --heldout      data through 2026-06-30 -> pilot/local/hardening_heldout.json
  python analysis/hardening_fit.py --production   data through the last complete day -> pilot/local/hardening_candidate.json
"""
import sys, json, math, datetime as dt
from pathlib import Path
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parent))
import theory_test4 as T4, refit_local as RL

def fit(end, out):
    P, cls, e = T4.strike_days(end)
    df = T4.design(P, cls, e, 30, robust=True); r = T4.fit(df, robust=True)
    beta = float(r.params["lw"]); K = float(np.mean(np.exp(df["lw"].values) ** beta))
    res = {"beta": beta, "K": K, "G": 30, "spell_weeks": int(len(df)), "restarts": int(df.y.sum()), "p": float(r.pvalues["lw"]),
           "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, indent=2) + "\n")
    print(f"beta {beta:+.4f} (p {res['p']:.3g}) | K {K:.4f} | m(1 wk) {1 / K:.2f}, m(13 wk) {13 ** beta / K:.2f}, m(52 wk) {52 ** beta / K:.2f}, "
          f"m(260 wk) {260 ** beta / K:.2f} -> {out}")

def anchors():
    """Frozen per-pair strike-date table from the local data (world-fit pair names, same strike filter); local only."""
    P, cls, e = T4.strike_days()
    out = {n: sorted(d.isoformat() for d in days) for n, days in P.items()}
    f = RL.LOCAL / "last_strike.json"; f.parent.mkdir(parents=True, exist_ok=True); f.write_text(json.dumps(out) + "\n")
    for n in ("Israel->Iran", "Iran->Israel", "United States->Iran", "United States->Yemen", "Israel->Syria", "Iran->Saudi Arabia"):
        print(f"  {n:22} last strike {out.get(n, ['none'])[-1]}")
    print(f"{len(out)} pairs -> {f} (frozen; local only)")

if __name__ == "__main__":
    if "--heldout" in sys.argv: fit(dt.date(2026, 6, 30), RL.LOCAL / "hardening_heldout.json")
    elif "--production" in sys.argv: fit(None, RL.LOCAL / "hardening_candidate.json")
    elif "--anchors" in sys.argv: anchors()
    else: print(__doc__)
