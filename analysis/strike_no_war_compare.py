"""docs/strike_no_war_prereg.md + amendment 1: gate 2 (contract replay) and the adoption rule.
Replay: every resolved qualifying contract (whole-state direction in the universe) at its first logged forecast whose published price was
the engine's and that carries the logged fields: logged price (without) vs the same P(A), P(B|A) with the HELD-OUT P(B|not A) (data
through the day before that forecast, the selected L, W = days remaining) (with). Gates only with >= 10 contracts and both outcomes.
Rule: adopt iff gate 1 passed AND (gate 2 not informative OR Brier(with) <= Brier(without)). Adopting copies
pilot/local/strike_no_war_candidate.json -> pilot/local/strike_no_war.json; otherwise that file is removed.
  python analysis/strike_no_war_fit.py --production && python analysis/strike_no_war_compare.py
"""
import sys, json, math, random, shutil, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "analysis"))
import strike_no_war as SNW, strike_no_war_fit as F, refit_local as RL
LOCAL = RL.LOCAL

def replay(L):
    outc = {}
    for l in (ROOT / "predictions" / "brier_log.jsonl").read_text().splitlines():
        if l.strip(): b = json.loads(l); outc[str(b["market_id"])] = b.get("outcome")
    first = {}
    for l in (ROOT / "predictions" / "log.jsonl").read_text().splitlines():
        if not l.strip(): continue
        r = json.loads(l); mid = str(r.get("market_id"))
        if mid in first or outc.get(mid) not in (0, 1) or r.get("pricing_component") not in (None, "engine"): continue
        if not SNW._sgw_qualifies(r) or SNW.key(r) is None or r.get("conditional_p") is None or r.get("days_remaining") is None: continue
        first[mid] = r
    if not first: return []
    end = RL.last_complete_day(); S = F.series(end, {"Air/drone strike"})
    byk = {f"{'+'.join(k[0])}->{k[1]}": v for k, v in S.items()}
    xs = []
    for mid, r in first.items():
        k = SNW.key(r)
        if k not in byk: continue
        ps, pw, _ = byk[k]; day = dt.date.fromisoformat(r["timestamp"][:10]) - dt.timedelta(days=1)
        t = min((day - F.D0).days, len(ps) - 2); W = max(1, int(round(float(r["days_remaining"]))))
        e = F.estimate(ps, pw, t, L, W)
        if e is None: continue
        a, pba = float(r["engine_p"]), float(r.get("p_b_given_a_pre_empirical") or r["p_b_given_a"])
        was = float(r.get("conditional_p_pre_snw") or r.get("conditional_p_pre_empirical") or r["conditional_p"])
        xs.append({"pair": k, "y": outc[mid], "a": was, "b": round(a * pba + (1 - a) * e[0], 4), "m": r.get("market_p"),
                   "q": (r.get("market_label") or "")[:60], "pbna_was": r.get("p_b_given_not_a_scaled"), "pbna_emp": round(e[0], 4)})
    return xs

def main():
    v = json.loads((LOCAL / "strike_no_war_validation.json").read_text()); cand = LOCAL / "strike_no_war_candidate.json"
    assert cand.exists(), "run analysis/strike_no_war_fit.py --production first"
    xs = replay(v["L"])
    B = lambda s, k: sum((x[k] - x["y"]) ** 2 for x in s if x[k] is not None) / max(1, len([x for x in s if x[k] is not None]))
    ys = {x["y"] for x in xs}; informative = len(xs) >= 10 and ys == {0, 1}
    print(f"=== GATE 2, CONTRACT REPLAY: {len(xs)} resolved contracts ({sum(x['y'] for x in xs)} YES) | informative: {informative}")
    if xs:
        for k, lab in (("a", "logged (LLM P(B|not A))"), ("b", "with held-out empirical"), ("m", "market")): print(f"  {lab:26} Brier {B(xs, k):.4f}")
        for x in sorted(xs, key=lambda x: -abs(x["b"] - x["a"]))[:10]:
            print(f"    {x['q']:60} y={x['y']} P(B|notA) {x['pbna_was']} -> {x['pbna_emp']} | price {x['a']:.3f} -> {x['b']:.3f} (market {x['m']})")
    g2 = (not informative) or B(xs, "b") <= B(xs, "a")
    adopt = bool(v["gate1_pass"]) and g2
    print(f"  rule: gate 1 {'PASS' if v['gate1_pass'] else 'FAIL'} (Brier {v['brier_emp']:.4f} vs {v['brier_llm']:.4f}) AND gate 2 "
          f"{'not informative' if not informative else ('PASS' if g2 else 'FAIL')}")
    if adopt: shutil.copy(cand, LOCAL / "strike_no_war.json"); print("  ADOPTION RULE -> empirical P(strike | no war) ADOPTED (local override)")
    else: (LOCAL / "strike_no_war.json").unlink(missing_ok=True); print("  ADOPTION RULE -> NOT adopted")
    c = json.loads(cand.read_text())
    print(f"  frozen table: data through {c['data_end']}, L = {c['L']}, {len(c['table'])} directions")
    (LOCAL / "strike_no_war_compare_result.json").write_text(json.dumps({"n": len(xs), "informative": informative,
        "brier": {k: round(B(xs, k), 4) for k in "abm"} if xs else None, "gate1": v["gate1_pass"], "adopted": adopt}, indent=2) + "\n")

if __name__ == "__main__":
    main()
