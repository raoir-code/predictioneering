"""
Worldwide class priors (Oct 20). Pairs = cross-border strikers in ACLED 2015-2025 (data/external/acled_world). Units of one
state are merged (Air Force, Navy, Mossad, IRGC ...); other suffixes are factions = de facto authorities (e.g. Yemen [Houthi]).
Maritime 'territories' dropped. CLASS BY A FIXED RULE (Adi, Oct 20), from who the strikes hit (ACLED actor2):
  1 coalition: actor1 is a multinational operation or coalition
  2 initiator itself a faction (de facto authority) -> defacto_authority
  3 else plurality of NAMED targets: state forces (any state) -> state_vs_state; faction-suffixed state forces -> defacto_authority;
    any other named armed actor -> cross_border_nonstate. Civilians / unnamed targets ignored. Ties: nonstate > defacto > state.
  4 no named targets -> state_vs_state
Pairs with >= 10 active days fitted with the same two-state model as analysis/pair_fits.py (air/drone + shelling/missile; imprecise
dates unobserved), then (log h, log mu) shrunk toward the class mean (DerSimonian-Laird; class needs >= 3 identified pairs, else
the world mean). A NEW pair with no history uses its class mean and spread. Output: pilot/priors_world.json, analysis/world_fits.json.
"""
import json, re, math, sys, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, str(Path(__file__).resolve().parent))
import numpy as np
import pair_fits as PF

ROOT = Path(__file__).resolve().parent.parent
WORLD, OUT, TAB = ROOT / "data" / "external" / "acled_world", ROOT / "pilot" / "priors_world.json", ROOT / "analysis" / "world_fits.json"
COALITION = re.compile(r"^(Operation |Global Coalition|NATO\b|Coalition)", re.I)
BRANCH = re.compile(r"^(Air Force|Navy|Naval Forces?|Army|Special Forces|Mossad|Gendarmerie|Marines?|Coast Guard|Intelligence.*|"
                    r"Islamic Revolutionary Guard Corps|Quds Force|Presidential Guard|Border Guard.*|National Guard|Military Police|Police.*)$", re.I)
SFX = re.compile(r"^Military Forces of (?:the )?(.+?) \([^)]*\)\s*(.*)$")
SUBS = {"Air/drone strike", "Shelling/artillery/missile attack"}
MARITIME = re.compile(r"Ocean|Sea\b|Gulf of|Strait", re.I)
D0, D1 = PF.D0, PF.D1

def ident(actor):
    a = actor or ""
    if COALITION.match(a): return a.split(":")[0].strip(), "coalition"
    m = SFX.match(a)
    if not m: return None, None
    country, suf = m.group(1), m.group(2).strip()
    return (country, "state") if (not suf or BRANCH.match(suf)) else (f"{country} [{suf}]", "defacto")

def target_kind(actor2):
    if not actor2 or re.search(r"civilian", actor2, re.I): return None
    _, kind = ident(actor2)
    return {"state": "state", "coalition": "state", "defacto": "defacto"}.get(kind, "nonstate")

def klass(ini_kind, tk):
    if ini_kind == "coalition": return "coalition"
    if ini_kind == "defacto": return "defacto_authority"
    if tk:
        top = max(("nonstate", "defacto", "state"), key=lambda k: (tk.get(k, 0), {"nonstate": 2, "defacto": 1, "state": 0}[k]))
        return {"state": "state_vs_state", "defacto": "defacto_authority", "nonstate": "cross_border_nonstate"}[top]
    return "state_vs_state"

def build():
    P = defaultdict(lambda: {"exact": set(), "inexact": set(), "tk": Counter(), "kind": None})
    for f in sorted(WORLD.glob("world_*.jsonl")):
        for l in f.read_text().splitlines():
            r = json.loads(l)
            if r.get("sub_event_type") not in SUBS or MARITIME.search(r.get("country") or ""): continue
            key, kind = ident(r.get("actor1"))
            if not key or key == r.get("country"): continue
            p = P[f"{key}->{r['country']}"]; p["kind"] = kind
            d = dt.date.fromisoformat(r["event_date"][:10])
            (p["exact"] if str(r.get("time_precision")) == "1" else p["inexact"]).add(d)
            t = target_kind(r.get("actor2"))
            if t: p["tk"][t] += 1
    return P

def series(p):
    days = [D0 + dt.timedelta(i) for i in range((D1 - D0).days + 1)]
    return [1 if d in p["exact"] else (None if d in p["inexact"] else 0) for d in days]

def fit_one(args):
    name, y = args
    act = sum(1 for v in y if v == 1); obs = sum(1 for v in y if v is not None); f = act / obs
    starts = [np.log([h, m, max(1e-4, f * 0.05), max(1e-3, -math.log(1 - min(0.9, 3 * f + 0.05)))]) for h, m in ((1/180, 1/30), (1/60, 1/14))]
    r = PF.fit(y, starts); th = r.x; sd = PF.hess_sd(th, y); h, mu, rN, d = np.exp(th)
    return name, {"active_days": act, "h_per_day": float(h), "mu_per_day": float(mu), "p_rec_F": float(1 - math.exp(-(rN + d))), "p_rec_N": float(1 - math.exp(-rN)),
                  "sd_log": dict(zip(["h", "mu", "rhoN", "d"], sd)) if sd else None}

def dl(vals):
    y = [v for v, _ in vals]; w = [1 / s ** 2 for _, s in vals]; k = len(y)
    mw = sum(a * b for a, b in zip(w, y)) / sum(w); Q = sum(a * (b - mw) ** 2 for a, b in zip(w, y))
    c = sum(w) - sum(a * a for a in w) / sum(w); tau2 = max(0.0, (Q - (k - 1)) / c) if k > 1 else 0.0
    ws = [1 / (s ** 2 + tau2) for _, s in vals]
    return sum(a * b for a, b in zip(ws, y)) / sum(ws), tau2

def main():
    P = build()
    todo = [(n, series(p)) for n, p in P.items() if sum(1 for v in series(p) if v == 1) >= 10]
    print(f"{len(P)} pairs, {len(todo)} with >= 10 active days; fitting in parallel...", flush=True)
    fits = {}
    with ProcessPoolExecutor() as ex:
        for i, (n, r) in enumerate(ex.map(fit_one, todo), 1):
            r["class"] = klass(P[n]["kind"], P[n]["tk"]); r["targets"] = dict(P[n]["tk"]); fits[n] = r
            print(f"  {i:2}/{len(todo)} {n[:44]:45} {r['class']:22} active {r['active_days']:5} | episode {math.log(2)/r['mu_per_day']:7.1f}d | onset wait {math.log(2)/r['h_per_day']:8.1f}d", flush=True)
    ok = lambda r: r["sd_log"] and all(isinstance(r["sd_log"][k], float) and math.isfinite(r["sd_log"][k]) and 0 < r["sd_log"][k] < 3 for k in ("h", "mu"))
    E = {n: {"h": (math.log(r["h_per_day"]), r["sd_log"]["h"]), "mu": (math.log(r["mu_per_day"]), r["sd_log"]["mu"])} for n, r in fits.items() if ok(r)}
    world = {k: dl([E[n][k] for n in E]) for k in ("h", "mu")}
    classes = {}
    for c in sorted({r["class"] for r in fits.values()} | {"state_vs_state", "cross_border_nonstate", "defacto_authority", "coalition"}):
        mem = [n for n in E if fits[n]["class"] == c]
        hyp = {k: dl([E[n][k] for n in mem]) for k in ("h", "mu")} if len(mem) >= 3 else world
        classes[c] = {"members_identified": mem, "source": "class" if len(mem) >= 3 else "world",
                      "log_h": {"mean": hyp["h"][0], "tau": math.sqrt(hyp["h"][1])}, "log_mu": {"mean": hyp["mu"][0], "tau": math.sqrt(hyp["mu"][1])},
                      "onset_median_wait_days": math.log(2) / math.exp(hyp["h"][0]), "episode_half_life_days": math.log(2) / math.exp(hyp["mu"][0])}
    pairs = {}
    for n, r in fits.items():
        c = classes[r["class"]]; post = {}
        for k, key in (("h", "log_h"), ("mu", "log_mu")):
            m, t = c[key]["mean"], c[key]["tau"]
            if n in E and t > 0:
                y, s = E[n][k]; prec = 1 / s ** 2 + 1 / t ** 2; post[k] = ((y / s ** 2 + m / t ** 2) / prec, prec ** -0.5)
            else:
                post[k] = (m, t if t > 0 else 1.0)
        pairs[n] = {"class": r["class"], "identified": n in E, "log_h": {"mean": post["h"][0], "sd": post["h"][1]}, "log_mu": {"mean": post["mu"][0], "sd": post["mu"][1]},
                    "onset_median_wait_days": math.log(2) / math.exp(post["h"][0]), "episode_half_life_days": math.log(2) / math.exp(post["mu"][0])}
    TAB.write_text(json.dumps(fits, indent=1) + "\n")
    OUT.write_text(json.dumps({"_doc": __doc__.strip(), "frozen": dt.date.today().isoformat(), "data": "ACLED 2015-2025 worldwide cross-border (data/external/acled_world/MANIFEST.json)",
                               "classes": classes, "pairs": pairs}, indent=1) + "\n")
    print("\n=== classes (pooled) ===")
    for c, v in classes.items():
        print(f"  {c:22} from {v['source']:5} ({len(v['members_identified']):2} identified pairs) | episode half-life {v['episode_half_life_days']:7.1f}d (tau {v['log_mu']['tau']:.2f}) | onset wait {v['onset_median_wait_days']:8.1f}d (tau {v['log_h']['tau']:.2f})")
    print("\n=== pairs we trade (pooled) ===")
    for n in ("Israel->Lebanon", "Israel->Syria", "Operation Restoring Hope->Yemen", "Israel->Yemen", "Israel->Iran", "Iran->Israel", "Iran->Iraq", "Pakistan->Afghanistan", "United States->Yemen", "Yemen [Houthi]->Saudi Arabia"):
        if n in pairs:
            v = pairs[n]; print(f"  {n:34} {v['class']:22} episode {v['episode_half_life_days']:7.1f}d | onset wait {v['onset_median_wait_days']:8.1f}d | identified {v['identified']}")
        else:
            print(f"  {n:34} not in the >= 10-day set")

if __name__ == "__main__":
    main()
