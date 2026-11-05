"""
Fair record (Nov 4): our pre-event forecasts vs the market price logged at the same moment, by model family.
  daily contracts:  the last forecast made before the contract's day starts (its rules' time zone)
  window contracts: the first forecast made at least BUFFER_H hours before resolution (resolution lags the event; later
                    forecasts can postdate a strike the market already knows about)
New models = the unified engine and its families; standalone = the DAG/engine path. Report only.
  python pilot/fair_record.py
"""
import json, sys, datetime as dt
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
NEW = {"unified-v1", "unified-gap-v0", "agreement-v1b", "withdrawal-v0", "during-war-v2e", "war-outcome-v0"}
BUFFER_H = 72

def T(s): return dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))

def rows(buffer_h=BUFFER_H):
    import unified_data as UD
    log = defaultdict(list)
    for l in (ROOT / "predictions" / "log.jsonl").read_text().splitlines():
        if l.strip(): r = json.loads(l); log[str(r["market_id"])].append(r)
    br = {}
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip():
            r = json.loads(l)
            if r.get("outcome") is not None and r.get("resolved_at"): br[str(r["market_id"])] = r
    cs, _ = UD.load(); daily = {c["id"]: c for c in cs if c["kind"] == "daily"}
    out = []
    for mid, b in br.items():
        L = sorted(log.get(mid, []), key=lambda r: r["timestamp"])
        if not L: continue
        cut, kind = (daily[mid]["start"], "daily") if mid in daily else (T(b["resolved_at"]) - dt.timedelta(hours=buffer_h), "window")
        for model, sel in (("new", lambda r: r.get("pricing_component") in NEW), ("standalone", lambda r: r.get("pricing_component") not in NEW)):
            S = [r for r in L if sel(r) and T(r["timestamp"]) < cut and r.get("conditional_p") is not None and r.get("market_p") is not None]
            if S:
                r = S[-1] if kind == "daily" else S[0]
                out.append({"model": model, "kind": kind, "y": int(b["outcome"]), "p": float(r["conditional_p"]), "m": float(r["market_p"]),
                            "resolved": b["resolved_at"][:10], "q": b.get("market_label") or "", "holds": "ceasefire continues" in (b.get("market_label") or "")})
    return out

def summary(rs, days=None):
    if days:
        lim = (dt.date.today() - dt.timedelta(days=days)).isoformat(); rs = [r for r in rs if r["resolved"] >= lim]
    if not rs: return None
    B = lambda k: sum((r[k] - r["y"]) ** 2 for r in rs) / len(rs)
    return {"n": len(rs), "ours": round(B("p"), 4), "market": round(B("m"), 4)}

def report(prefix="   "):
    rs = rows(); lines = []
    for model in ("new", "standalone"):
        s = [r for r in rs if r["model"] == model]
        for lab, sub in (("all", s), ("excl. holds", [r for r in s if not r["holds"]]), ("holds", [r for r in s if r["holds"]])):
            a, w = summary(sub), summary(sub, 14)
            if a: lines.append(f"{prefix}{model:10} {lab:12} all-time n {a['n']:3} ours {a['ours']:.4f} mkt {a['market']:.4f}" +
                               (f" | last 14d n {w['n']:3} ours {w['ours']:.4f} mkt {w['market']:.4f}" if w else ""))
    return lines

if __name__ == "__main__":
    print("\n".join(report("")))
