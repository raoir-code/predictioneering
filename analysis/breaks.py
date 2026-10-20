"""
Structural breaks (Oct 20). When a country's government is overthrown or collapses, its conflict relationships change, so for
any pair where EITHER side has a break, war-length / restart priors use ONLY post-break history. < 10 active days after the
break -> the pair uses its class prior. Registry = dated, sourced, ex ante events (never chosen from outcomes); adding a country
is one line, applied to every pair that touches it.
  python analysis/breaks.py      refit affected pairs on post-break ACLED data, update pilot/priors_world.json (pre-break kept)
"""
import json, math, sys, datetime as dt
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import world_fits as WF, pair_fits as PF

BREAKS = {
    "Syria": ("2024-12-08", "Fall of the Assad government (HTS-led offensive); widely reported, e.g. Reuters / AP Dec 8 2024"),
    "Afghanistan": ("2021-08-15", "Taliban capture Kabul; Ghani government collapses; widely reported Aug 15 2021"),
}
ROOT = Path(__file__).resolve().parent.parent; PW = ROOT / "pilot" / "priors_world.json"

def main():
    W = json.loads(PW.read_text()); P = WF.build(); ln2 = math.log(2)
    for key, p in P.items():
        ini, ter = key.split("->")
        hits = [(c, BREAKS[c]) for c in (ter, ini.split(" [")[0]) if c in BREAKS]
        if not hits or key not in W["pairs"]: continue
        c, (bdate, src) = max(hits, key=lambda x: x[1][0]); b = dt.date.fromisoformat(bdate)
        days = [b + dt.timedelta(i) for i in range((WF.D1 - b).days + 1)]
        y = [1 if d in p["exact"] else (None if d in p["inexact"] else 0) for d in days]
        act = sum(1 for v in y if v == 1); cls = W["pairs"][key]["class"]; C = W["classes"][cls]; old = dict(W["pairs"][key])
        if act < 10:
            post = {"h": (C["log_h"]["mean"], C["log_h"]["tau"]), "mu": (C["log_mu"]["mean"], C["log_mu"]["tau"])}; how = f"class prior ({act} active days after break)"
        else:
            f = act / sum(1 for v in y if v is not None)
            starts = [np.log([h, m, max(1e-4, f * 0.05), max(1e-3, -math.log(1 - min(0.9, 3 * f + 0.05)))]) for h, m in ((1/180, 1/30), (1/60, 1/14))]
            r = PF.fit(y, starts); sd = PF.hess_sd(r.x, y); post = {}
            for i, k in ((0, "h"), (1, "mu")):
                m, t = C[f"log_{k}"]["mean"], C[f"log_{k}"]["tau"]; yv = float(r.x[i])
                s = sd[i] if sd and math.isfinite(sd[i]) and 0 < sd[i] < 3 else None
                if s and t > 0:
                    prec = 1 / s ** 2 + 1 / t ** 2; post[k] = ((yv / s ** 2 + m / t ** 2) / prec, prec ** -0.5)
                else:
                    post[k] = (m, t if t > 0 else 1.0)
            how = f"refit on {act} post-break active days, shrunk to {cls}"
        W["pairs"][key].update({"log_h": {"mean": post["h"][0], "sd": post["h"][1]}, "log_mu": {"mean": post["mu"][0], "sd": post["mu"][1]},
                                "onset_median_wait_days": ln2 / math.exp(post["h"][0]), "episode_half_life_days": ln2 / math.exp(post["mu"][0]),
                                "break": {"country": c, "date": bdate, "source": src, "how": how},
                                "pre_break": {k: old[k] for k in ("log_h", "log_mu", "onset_median_wait_days", "episode_half_life_days")}})
        print(f"  {key:44} break {c} {bdate}: war {old['episode_half_life_days']:6.1f}d -> {W['pairs'][key]['episode_half_life_days']:6.1f}d | "
              f"restart {old['onset_median_wait_days']:7.1f}d -> {W['pairs'][key]['onset_median_wait_days']:7.1f}d | {how}")
    W["_breaks"] = {k: {"date": v[0], "source": v[1]} for k, v in BREAKS.items()}
    PW.write_text(json.dumps(W, indent=1) + "\n")

if __name__ == "__main__":
    main()
