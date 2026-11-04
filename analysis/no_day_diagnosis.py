"""docs/no_day_diagnosis_prereg.md: where does the engine lose on NO outcomes? Diagnosis before choosing a fix (roadmap step 1).
Joins two outputs already on disk (no new pricing, no new data):
  pilot/local/degradation_replay.json   FULL-arm price and market price per resolved strike contract (T3)
  pilot/local/answer_key_agreement.json local strike days in each contract's window (T2)
Each NO contract is classed:
  A  fighting, no qualifying strike: the local data has a strike day in the window (broad definition: shelling counts)
  B  true quiet: no local strike day in the window
and the excess Brier over the market (u^2 - m^2 on a NO) is summed by class. The pre-registered rule picks the lever.
  python analysis/no_day_diagnosis.py --synthetic
  python analysis/no_day_diagnosis.py --measure     -> pilot/local/no_day_diagnosis.json
Report only.
"""
import sys, json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent; LOCAL = ROOT / "pilot" / "local"
DR, AK, OUT = LOCAL / "degradation_replay.json", LOCAL / "answer_key_agreement.json", LOCAL / "no_day_diagnosis.json"
SHARE = 0.5

def classify(rows, ref):
    """rows: [{id, pair, y, full, m}]; ref: {id: local_yes}. -> per-class sums for NO contracts in both files."""
    out = {"A": [], "B": []}
    for x in rows:
        if x["y"] != 0 or x["id"] not in ref or x["m"] is None: continue
        out["A" if ref[x["id"]] else "B"].append(x)
    return out

def excess(xs): return sum(x["full"] ** 2 - x["m"] ** 2 for x in xs)

def verdict(cls):
    ea, eb = excess(cls["A"]), excess(cls["B"]); tot = ea + eb
    if tot <= 0: return None, "NO EXCESS LOSS on NO outcomes (in the joined set): no NO-side fix"
    sa = ea / tot
    return round(sa, 3), ("LEVER = q (fighting days without a qualifying strike: definition-consistent strike rate)" if sa >= SHARE
                          else "LEVER = state (true quiet the engine did not see: regime persistence / exit, quiet-day information)")

def measure():
    rows = json.loads(DR.read_text())["rows"]; ak = json.loads(AK.read_text())
    ref = {d["id"]: d["ref"] for d in ak["contracts"]}
    cls = classify(rows, ref); share, v = verdict(cls)
    n_no = sum(1 for x in rows if x["y"] == 0)
    res = {"no_contracts_in_replay": n_no, "joined": {k: len(v) for k, v in cls.items()},
           "excess_brier": {k: round(excess(v), 4) for k, v in cls.items()}, "share_A": share, "verdict": v,
           "by_pair": {}, "contracts": {k: [{"id": x["id"], "pair": x["pair"], "ours": x["full"], "market": x["m"]} for x in v] for k, v in cls.items()}}
    for k, xs in cls.items():
        for x in xs:
            p = res["by_pair"].setdefault(x["pair"], {"A": 0, "B": 0, "excess_A": 0.0, "excess_B": 0.0})
            p[k] += 1; p["excess_" + k] = round(p["excess_" + k] + x["full"] ** 2 - x["m"] ** 2, 4)
    bins = defaultdict(lambda: [0, 0, 0.0])
    for x in rows:
        b = min(int(x["full"] * 10), 9); bins[b][0] += 1; bins[b][1] += x["y"]; bins[b][2] += x["full"]
    res["calibration_full"] = {f"{b / 10:.1f}-{(b + 1) / 10:.1f}": {"n": n, "mean_p": round(s / n, 3), "freq_yes": round(y / n, 3)}
                               for b, (n, y, s) in sorted(bins.items())}
    OUT.write_text(json.dumps(res, indent=1))
    print(f"NO contracts in the T3 replay: {n_no}; joined with T2's local strike days: A {len(cls['A'])}, B {len(cls['B'])}")
    print(f"excess Brier over the market on NO outcomes: A (fighting, no qualifying strike) {res['excess_brier']['A']:+.4f} | "
          f"B (true quiet) {res['excess_brier']['B']:+.4f}  -> share A {share}")
    print(f"VERDICT: {v}")
    for p, v2 in sorted(res["by_pair"].items(), key=lambda kv: -(kv[1]["excess_A"] + kv[1]["excess_B"])):
        print(f"  {p:28} A {v2['A']:2} ({v2['excess_A']:+.3f})  B {v2['B']:2} ({v2['excess_B']:+.3f})")
    print("calibration of FULL prices (all 119 contracts):")
    for b, v2 in res["calibration_full"].items(): print(f"  {b}  n {v2['n']:3}  mean p {v2['mean_p']:.3f}  freq YES {v2['freq_yes']:.3f}")

def synthetic():
    rows = [{"id": "1", "pair": "a", "y": 0, "full": 0.9, "m": 0.2}, {"id": "2", "pair": "a", "y": 0, "full": 0.5, "m": 0.5},
            {"id": "3", "pair": "b", "y": 0, "full": 0.3, "m": 0.1}, {"id": "4", "pair": "b", "y": 1, "full": 0.9, "m": 0.8},
            {"id": "5", "pair": "b", "y": 0, "full": 0.9, "m": 0.1}]
    cls = classify(rows, {"1": 1, "2": 0, "3": 0, "4": 1})
    assert [x["id"] for x in cls["A"]] == ["1"] and [x["id"] for x in cls["B"]] == ["2", "3"]   # 4 is YES, 5 not in T2
    s, v = verdict(cls); assert abs(s - 0.77 / (0.77 + 0.08)) < 1e-3 and v.startswith("LEVER = q"), (s, v)
    s, v = verdict({"A": [], "B": [{"full": 0.6, "m": 0.1}]}); assert s == 0 and v.startswith("LEVER = state")
    print("synthetic: all checks pass")

if __name__ == "__main__":
    a = sys.argv[1:] or ["--synthetic"]
    {"--synthetic": synthetic, "--measure": measure}[a[0]]()
