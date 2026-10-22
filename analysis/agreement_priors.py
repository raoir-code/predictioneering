"""
Priors for family C ("agreement" contracts): hazard of an agreement during an ongoing armed-conflict episode, by episode age,
from the UCDP Conflict Termination dataset v4-2024 (Kreutz 2010), dyad level. Offline only; writes pilot/agreement_priors.json.

  agree:  first ceasefire OR peace agreement date in the episode (d_cfiredate / d_peagdate), else episode end coded 1/2
  peace:  peace agreement (d_peagdate, else end coded 1)
  recur:  after an episode that ended by agreement (outcome 1/2), time to the next episode of the same dyad
Exposure is episode-years; ongoing episodes censored at 2024-12-31. These count agreements that UCDP ties to an episode, so they
UNDERSTATE "any announced general pause" (holiday truces): the pricing prior is wide (log-sd 1.5) and pair data dominate.
Also writes current-episode start dates for actor sets (ongoing episodes, all named actors present), used for episode age.

  python analysis/agreement_priors.py [path/to/UCDPConflictTerminationDataset_v4_2024_Dyad.csv]
"""
import csv, sys, json, hashlib, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "external" / "ucdp" / "UCDPConflictTerminationDataset_v4_2024_Dyad.csv"
OUT = ROOT / "pilot" / "agreement_priors.json"
CENS = dt.date(2024, 12, 31)
BINS = [(0, 1), (1, 2), (2, 5), (5, 10), (10, 99)]
NAMES = {"russia": "Russia", "ukraine": "Ukraine", "israel": "Israel", "hamas": "Hamas", "hezbollah": "Hezbollah", "iran": "Iran",
         "us": "United States", "saudi": "Saudi", "houthi": "Ansarallah", "sudan": "Sudan", "yemen": "Yemen", "lebanon": "Lebanon",
         "pakistan": "Pakistan", "afghanistan": "Afghanistan", "thailand": "Thailand", "cambodia": "Cambodia", "venezuela": "Venezuela",
         "india": "India", "china": "China", "taiwan": "Taiwan", "armenia": "Armenia", "azerbaijan": "Azerbaijan", "ethiopia": "Ethiopia",
         "eritrea": "Eritrea", "drc": "DR Congo", "rwanda": "Rwanda", "m23": "M23"}      # lookup table: actor key -> UCDP name fragment

D = lambda s: dt.date.fromisoformat(s[:10]) if s and len(s) >= 10 else None

def episodes(path):
    ep = defaultdict(list)
    for x in csv.DictReader(open(path, encoding="utf-8", errors="replace")): ep[x["d_epid"]].append(x)
    E = []
    for k, xs in ep.items():
        xs.sort(key=lambda x: int(x["year"])); f, l = xs[0], xs[-1]
        s = D(f["start_date2"]) or D(f["start_date"])
        if not s: continue
        E.append({"id": k, "dyad": f["dyad_id"], "epno": int(f["d_epno"] or 0), "start": s, "end": D(l["d_ependdate"]), "out": l["d_outcome"],
                  "cf": D(l["d_cfiredate"]), "pa": D(l["d_peagdate"]), "type": f["type_of_conflict"],
                  "text": " | ".join(f[c] for c in ("side_a", "side_a_2nd", "side_b", "side_b_2nd", "location"))})
    return E

def hazard(pool, ev_fn, t0_fn=lambda e: e["start"], stop_fn=lambda e: e["end"] or CENS):
    ev, ex = Counter(), Counter()
    for e in pool:
        t0, stop = t0_fn(e), stop_fn(e)
        if not t0 or not stop or stop < t0: continue
        te = ev_fn(e)
        if te and t0 <= te <= stop: stop = te
        else: te = None
        dur = (stop - t0).days / 365.25
        for lo, hi in BINS: ex[(lo, hi)] += max(0.0, min(dur, hi) - lo)
        if te:
            y = (te - t0).days / 365.25
            for lo, hi in BINS:
                if lo <= y < hi: ev[(lo, hi)] += 1
    tot_e, tot_x = sum(ev.values()), sum(ex.values())
    return {"bins": [{"lo": lo, "hi": hi, "events": ev[(lo, hi)], "exposure_years": round(ex[(lo, hi)], 1),
                      "rate_per_year": round(ev[(lo, hi)] / ex[(lo, hi)], 5) if ex[(lo, hi)] else None} for lo, hi in BINS],
            "pooled_rate_per_year": round(tot_e / tot_x, 5), "events": tot_e, "exposure_years": round(tot_x, 1)}

def main():
    E = episodes(SRC)
    agree = lambda e: min([d for d in (e["cf"], e["pa"]) if d] or [None]) if (e["cf"] or e["pa"]) else (e["end"] if e["out"] in ("1", "2") else None)
    peace = lambda e: e["pa"] or (e["end"] if e["out"] == "1" else None)
    nxt = {}
    by = defaultdict(list)
    for e in E: by[e["dyad"]].append(e)
    for d, xs in by.items():
        xs.sort(key=lambda e: e["start"])
        for a, b in zip(xs, xs[1:]): nxt[a["id"]] = b["start"]
    ended = [e for e in E if e["out"] in ("1", "2") and e["end"]]
    recur = hazard(ended, lambda e: nxt.get(e["id"]), t0_fn=lambda e: e["end"], stop_fn=lambda e: CENS)
    starts = {}
    ongoing = [e for e in E if e["end"] is None]
    import itertools
    keys = sorted(NAMES)
    for r in (1, 2):
        for combo in itertools.combinations(keys, r):
            m = [e for e in ongoing if all(NAMES[k] in e["text"] for k in combo)]
            if m: starts["|".join(combo)] = str(max(e["start"] for e in m))
    out = {"source": str(SRC.name), "sha256": hashlib.sha256(SRC.read_bytes()).hexdigest(), "episodes": len(E),
           "citation": "Kreutz, J. (2010). How and when armed conflicts end. Journal of Peace Research 47(2). UCDP Conflict Termination v4-2024.",
           "agree": hazard(E, agree), "peace": hazard(E, peace), "recur": recur, "episode_start": starts,
           "computed_at": dt.datetime.now(dt.timezone.utc).isoformat()}
    OUT.write_text(json.dumps(out, indent=1) + "\n")
    for k in ("agree", "peace", "recur"):
        print(k, "pooled", out[k]["pooled_rate_per_year"], [(b["lo"], b["rate_per_year"], b["events"]) for b in out[k]["bins"]])
    print("episode starts:", {k: v for k, v in starts.items() if "|" in k})

if __name__ == "__main__":
    main()
