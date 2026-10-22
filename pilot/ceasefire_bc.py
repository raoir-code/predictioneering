"""
Families B ("effective ceasefire" = N-day strike-free spell) and C ("agreement") — docs/ceasefire_scope_rule.md as amended Oct 22
(docs/ceasefire_publish_amendment.md: every in-scope contract is priced and published; replays are reported, never gate).

B, component "unified-gap-v0". YES iff a continuous N-day period with no qualifying strike (one or both directions) begins after the
  most recent strike (or market creation) on or before the date. Exact first-passage on the unified engine's two-state chain:
  state (fighting regime, quiet-run length r); a strike on a day <= D resets r, a strike after D ends the contract; r = N absorbs.
  Start: posterior over (regime, day of last strike) from the pair's unified evidence (same machinery as unified-v1); states whose quiet
  run already reached N since creation contradict an open contract and are dropped. Two directions: independent chains (v0).
C, component "agreement-v0". Events (a qualifying agreement/deal/breakdown, per the contract's own wording) arrive at rate lambda per
  (actor set, type). Prior: log-normal around the UCDP Conflict Termination hazard at the current episode's age
  (pilot/agreement_priors.json; CEASEFIRE/EXTENSION -> any agreement, DEAL -> peace agreement, BREAKDOWN -> recurrence), log-sd 1.5
  because UCDP counts episode-ending agreements while contracts also pay on short general truces. Likelihood: the actor set's own
  resolved Polymarket contracts of the same type, on one day timeline (no-event days = union of NO windows; overlapping YES windows
  intersected), each usable only after its close time. Price = 1 - E[exp(-lambda * remaining days)].

  python pilot/ceasefire_bc.py --replay     walk-forward replay of both families vs market (report only) -> pilot/bc_replay.json
  python pilot/ceasefire_bc.py --dry        today's prices vs market
  python pilot/ceasefire_bc.py --test       offline tests
"""
import json, re, sys, math, datetime as dt
from collections import defaultdict, Counter
from pathlib import Path
from zoneinfo import ZoneInfo
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pilot"))
import unified_data as UD, unified as U, ceasefire_holds as CH

UTC = dt.timezone.utc
PRI = json.loads((ROOT / "pilot" / "agreement_priors.json").read_text())
PAX = json.loads((ROOT / "pilot" / "agreement_priors_pax.json").read_text()) if (ROOT / "pilot" / "agreement_priors_pax.json").exists() else None
CPOL = ROOT / "pilot" / "c_policy.json"            # which C model production uses (written once by --compare, docs/c1_prereg.md)
LAMX = np.exp(np.linspace(math.log(1e-3), math.log(30.0), 100))      # grid for the exact likelihood (C0+fix, C1)
COMPONENT = {"C0": "agreement-v0", "C0fix": "agreement-v0.1", "C1": "agreement-v1"}
REPLAY = ROOT / "pilot" / "bc_replay.json"
PRIOR_SD = 1.5
LAM = np.exp(np.linspace(math.log(1e-3), math.log(30.0), 400))       # events per year
K1, K2 = 60, 25                                                       # posterior components kept (one / two directions)

ACTORS = [(r"\brussia", "russia"), (r"\bukrain", "ukraine"), (r"\bisrael", "israel"), (r"\bhamas", "hamas"), (r"\bhezbollah", "hezbollah"),
          (r"\blebanon", "lebanon"), (r"\biran", "iran"), (r"\bu\.?s\.?(?=[\s\-x])|united states", "us"), (r"\bsaudi", "saudi"),
          (r"\bhouthi", "houthi"), (r"\bsudan", "sudan"), (r"\bthailand", "thailand"), (r"\bcambodia", "cambodia"), (r"\bpakistan", "pakistan"),
          (r"\bafghanistan", "afghanistan"), (r"\bvenezuela", "venezuela"), (r"\byemen", "yemen"), (r"\bindia\b", "india"),
          (r"\barmenia", "armenia"), (r"\bazerbaijan", "azerbaijan"), (r"\bethiopia", "ethiopia"), (r"\beritrea", "eritrea"),
          (r"\bcongo|\bdrc\b", "drc"), (r"\brwanda", "rwanda"), (r"\bm23\b", "m23")]       # lookup table, not per-pair logic
PRIOR_KEY = {"CEASEFIRE": "agree", "EXTENSION": "agree", "DEAL": "peace", "BREAKDOWN": "recur"}

def actor_key(title):
    t = (title or "").lower(); return "|".join(sorted({k for p, k in ACTORS if re.search(p, t)}))

# ---------------------------------------------------------------- classification (resolution text decides the family)
_GAP1 = re.compile(r"continuous (\d+)-day period during which (?:the )?(.+?) does not take a qualifying military action against (?:the )?(.+?)(?: that|,|\.| between| following)", re.I)
_GAP2 = re.compile(r"continuous (\d+)-day period during which neither (?:the )?(.+?) nor (?:the )?(.+?) takes? a qualifying military action against the other", re.I)

def dir_pair(ini, ter):
    import unified_price as UP
    f = lambda x: (UD.norm(x)[:-1] if UD.norm(x).endswith("s") and UD.norm(x)[:-1] in UP.FACTION else UD.norm(x))
    a, b = f(ini), f(ter)
    return f"{a}->{UP.FACTION_HOME.get(b, b)}"

def classify_all(q, desc):
    h = CH.classify(q, desc)
    if h and h["family"] == "HOLDS": return h
    d = re.sub(r"\s+", " ", desc or "")
    if h and h["family"] == "GAP":
        m2, m1 = _GAP2.search(d), _GAP1.search(d)
        if m2: return {"family": "GAP", "N": int(m2.group(1)), "dirs": [dir_pair(m2.group(2), m2.group(3)), dir_pair(m2.group(3), m2.group(2))]}
        if m1: return {"family": "GAP", "N": int(m1.group(1)), "dirs": [dir_pair(m1.group(2), m1.group(3))]}
        return {"family": "GAP", "N": None, "dirs": None}
    t = (q or "").lower(); dl = d.lower()
    if not re.search(r"ceasefire|cease-fire|truce|armistice|peace", t): return None
    if re.search(r"attend|take place|\btalks\b|referendum|peacekeep|combo|meeting|summit|nobel|envoy", t): return {"family": "PROCESS"}
    if not re.search(r"agree|deal|signed|announce|cancel|framework|extension|halt|suspension", dl): return None
    if re.search(r"cancel|collapse|terminat|broken|\bends?\b|\blast\b", t): typ = "BREAKDOWN"
    elif re.search(r"extension|extend", t): typ = "EXTENSION"
    elif re.search(r"peace deal|peace agreement|permanent peace|phase ii|\bsigns?\b", t): typ = "DEAL"
    else: typ = "CEASEFIRE"
    return {"family": "AGREEMENT", "type": typ, "actors": actor_key(q)}

_BY = re.compile(r"\b(?:by|through|before|on) (" + UD._M + r") (\d{1,2})(?:,? (\d{4}))?", re.I)

def due_date(q, desc, created, end_iso=None):
    for txt in (q or "", desc or ""):
        m = _BY.search(txt)
        if m:
            mon, day = UD.MON[m.group(1).lower()], int(m.group(2)); y = int(m.group(3)) if m.group(3) else created.year
            d = dt.date(y, mon, day)
            if not m.group(3) and d < created.date() - dt.timedelta(1): d = dt.date(y + 1, mon, day)
            return d
    m = re.search(r"before (\d{4})", q or "", re.I)
    if m: return dt.date(int(m.group(1)) - 1, 12, 31)
    m = re.search(r"(?:end of|in) (\d{4})", q or "", re.I)
    if m: return dt.date(int(m.group(1)), 12, 31)
    if re.search(r"\bEOY\b|end of (?:the )?year", q or "", re.I): return dt.date(created.year, 12, 31)
    if end_iso:
        try: return UD.T(str(end_iso).replace("Z", "+00:00")).date()
        except Exception: pass
    return None

def store():
    return json.loads(CH.STORE.read_text()) if CH.STORE.exists() else {}

# ---------------------------------------------------------------- C: agreement rate model
def episode_age_years(actors, as_of):
    st = PRI["episode_start"]
    cands = [actors] + ([actors.replace("houthi", "yemen")] if "houthi" in actors else [])
    for k in cands:
        if k in st: return max(0.0, (as_of.date() - dt.date.fromisoformat(st[k])).days / 365.25)
    return None

def prior_rate(typ, actors, as_of):
    H = PRI[PRIOR_KEY[typ]]; age = episode_age_years(actors, as_of) if typ != "BREAKDOWN" else None
    if age is not None:
        for b in H["bins"]:
            if b["lo"] <= age < b["hi"] and b["rate_per_year"]: return b["rate_per_year"], f"UCDP {PRIOR_KEY[typ]} hazard at episode age {age:.1f}y"
    return H["pooled_rate_per_year"], f"UCDP {PRIOR_KEY[typ]} pooled hazard"

def agreement_contracts(S=None):
    out = []
    for mid, r in (S or store()).items():
        info = classify_all(r.get("question"), r.get("description"))
        if not info or info.get("family") != "AGREEMENT" or not info["actors"]: continue
        created = CH._ts(r.get("createdAt"))
        if not created: continue
        known = CH._ts(r.get("closedTime")) if r.get("closed") else None
        d = due_date(r.get("question"), r.get("description"), created, r.get("endDate")) or (known.date() if known else None)
        if not d: continue
        tok = json.loads(r.get("clobTokenIds") or "[]")
        out.append({"id": str(mid), "actors": info["actors"], "type": info["type"], "start": created.date(), "created": created, "end": d,
                    "y": CH.holds_outcome(r), "known": known, "open": not r.get("closed"), "q": r.get("question"), "tok": tok[0] if tok else None})
    return out

def _days(a, b): return {a + dt.timedelta(i) for i in range((b - a).days + 1)} if b >= a else set()

def loglik(wins):
    """wins: [(a, b, y)] dates. One timeline: no-event days = union of NO windows; overlapping YES windows are intersected."""
    no = set().union(*[_days(a, b) for a, b, y in wins if y == 0]) if wins else set()
    ll = -LAM * len(no) / 365.25
    groups = []
    for a, b in sorted((a, b) for a, b, y in wins if y == 1):
        if groups and a <= groups[-1][1] and max(a, groups[-1][0]) <= min(b, groups[-1][1]):
            groups[-1] = (max(a, groups[-1][0]), min(b, groups[-1][1]))
        else: groups.append((a, b))
    used = 0
    for a, b in groups:
        n = len(_days(a, b) - no)
        if n > 0: ll = ll + np.log1p(-np.exp(-LAM * n / 365.25)); used += 1
    return ll, len(no), used

def loglik_exact(wins, grid):
    """Exact: one-state Poisson process on the day timeline, last-event tracking (pilot/unified.py forward). Overlapping YES
    windows can be satisfied by different events (docs/c1_prereg.md item 1)."""
    if not wins: return np.zeros(len(grid)), 0, 0
    d0 = min(a for a, _, _ in wins); T = (max(b for _, b, _ in wins) - d0).days + 1
    W = [((a - d0).days, (b - d0).days, y) for a, b, y in wins if b >= a]
    out = np.empty(len(grid))
    for i, lam in enumerate(grid):
        q0 = 1 - math.exp(-lam / 365.25)
        out[i] = U.forward(T, W, 0.0, 1.0, q0, q0, p_start=[1.0, 0.0])[0]
    no = set().union(*[_days(a, b) for a, b, y in wins if y == 0])
    return out, len(no), sum(1 for _, _, y in wins if y == 1)

def prior_pax(typ):
    """C1 prior (docs/c1_prereg.md items 2 and 8): log-normal(log_mu, log_sigma) per year; types with < 20 events take the CEASEFIRE sigma."""
    if typ == "BREAKDOWN" or not PAX: return None
    r = PAX["rates"][typ if typ in PAX["rates"] else "CEASEFIRE"]
    sg = r["log_sigma"] if r["events"] >= 20 else PAX["rates"]["CEASEFIRE"]["log_sigma"]
    return r["log_mu"], sg, f"PA-X {typ.lower()} rate: median {math.exp(r['log_mu']):.3f}/yr, log-sd {sg:.2f}"

def model_in_use():
    try: return json.loads(CPOL.read_text())["model"]
    except Exception: return "C0"

def agreement_price(c, allc, as_of, model=None):
    model = model or model_in_use()
    mu, why = prior_rate(c["type"], c["actors"], as_of)
    lmu, lsd = math.log(mu), PRIOR_SD
    if model == "C1":
        px = prior_pax(c["type"])
        if px: lmu, lsd, why = px
    wins = []
    for x in allc:
        if x["actors"] != c["actors"] or x["type"] != c["type"] or x["id"] == c["id"] or x["y"] is None: continue
        if not (x["known"] and x["known"] < as_of): continue
        b = min(x["end"], x["known"].date()) if x["y"] == 1 else x["end"]
        wins.append((x["start"], b, x["y"]))
    days = (c["end"] - as_of.date()).days + 1
    if days <= 0: return None, None
    grid = LAM if model == "C0" else LAMX
    ll, nno, nyes = loglik(wins) if model == "C0" else loglik_exact(wins, grid)
    if not np.isfinite(ll).any():          # contradictory windows (a YES window inside known no-event days): skip those YES windows, as C0 does
        no = set().union(*[_days(a, b) for a, b, y in wins if y == 0])
        wins = [(a, b, y) for a, b, y in wins if y == 0 or (_days(a, b) - no)]
        ll, nno, nyes = loglik_exact(wins, grid)
        if not np.isfinite(ll).any(): ll, nno, nyes = loglik_exact([(a, b, y) for a, b, y in wins if y == 0], grid)
    lp = -0.5 * ((np.log(grid) - lmu) / lsd) ** 2
    w = np.exp(ll + lp - (ll + lp).max()); w /= w.sum()
    p = float(1 - np.dot(w, np.exp(-grid * days / 365.25)))
    lam_med = float(grid[min(len(grid) - 1, np.searchsorted(np.cumsum(w), 0.5))])
    return round(p, 4), {"model": model, "prior": why, "own_no_days": nno, "own_yes_windows": nyes, "rate_median_per_year": round(lam_med, 3)}

# ---------------------------------------------------------------- B: N-day strike-free spell, exact first passage
def gap_contracts(S=None):
    out = []
    for mid, r in (S or store()).items():
        info = classify_all(r.get("question"), r.get("description"))
        if not info or info.get("family") != "GAP" or not info.get("dirs") or not info.get("N"): continue
        created = CH._ts(r.get("createdAt")); d = due_date(r.get("question"), r.get("description"), created, r.get("endDate")) if created else None
        if not created or not d: continue
        tok = json.loads(r.get("clobTokenIds") or "[]")
        out.append({"id": str(mid), "dirs": info["dirs"], "N": info["N"], "created": created, "end": d, "y": CH.holds_outcome(r),
                    "known": CH._ts(r.get("closedTime")) if r.get("closed") else None, "open": not r.get("closed"), "q": r.get("question"),
                    "tok": tok[0] if tok else None})
    return out

def _dir_state(pair, G, as_of, keep, K):
    import unified_price as UP
    cands = [g for (p, f), g in G.items() if p == pair]
    if not cands: return None, f"{pair}: no unified group"
    grp = max(cands, key=lambda g: (len(UD.windows(g, as_of)[2]), len(g)))
    P = UP.params(pair)
    if not P: return None, f"{pair}: no parameters"
    z = ZoneInfo(UD.group_tz(grp)); today = as_of.astimezone(z).date()
    ev, npairs, linked = UP.evidence(grp, pair, as_of, G)
    nd = set().union(*[UP.news_dates(p, as_of, z) for p in npairs])
    seed = None
    if not ev and not nd:
        pi = UP.reverse_seed(pair, G, as_of)
        if pi is not None: seed = np.array([1 - pi, pi])
    d0n = min([today - dt.timedelta(keep + 1)] + [a for a, _, _ in ev] + ([today - dt.timedelta(60)] if nd else []))
    wins = [((a - d0n).days, (b - d0n).days, y) for a, b, y in ev]; Tn = (today - d0n).days
    nds = {(d - d0n).days for d in nd if d >= d0n}
    w, rows = UP.grid(P, Tn, wins, p_start=seed, nds=nds)
    if not len(rows): return None, f"{pair}: contradictory evidence"
    idx = np.argsort(-w)[:K]; ww = w[idx] / w[idx].sum(); comps = []
    for i, wi in zip(idx, ww):
        _, q, q0, st, mu = rows[i]
        st2 = U.forward_joint(Tn, wins, P["h"], mu, q, q0, p_start=seed, keep_from=Tn - keep, news_days=nds, news_ratio=UP.NEWS_FALSE / UP.NEWS_CATCH)[1]
        if st2 is None: continue
        _, M0, M1 = U.mats(P["h"], mu, q, q0)
        comps.append((float(wi), {k: v for k, v in st2.items()}, np.asarray(M0), np.asarray(M1)))
    tot = sum(c[0] for c in comps)
    return {"today": today, "Tn": Tn, "comps": [(c[0] / tot,) + c[1:] for c in comps], "src": f"{pair}: {len(ev)} windows, {len(nd)} news days"}, None

def _first_passage(init, M0, M1, N, horizon, last_reset):
    """init: array (S, N) mass over (state, quiet run r). Day t = 0..horizon-1; a strike resets r if t <= last_reset, else kills."""
    v = init.copy(); absorbed = 0.0
    for t in range(horizon):
        tot = v.sum(axis=1)
        ns = M0.T @ v                                         # (S, N): no strike today, r -> r+1
        absorbed += ns[:, N - 1].sum()
        nv = np.zeros_like(v); nv[:, 1:] = ns[:, :-1]
        if t <= last_reset: nv[:, 0] += M1.T @ tot
        v = nv
        if v.sum() < 1e-12: break
    return absorbed

def gap_price(c, G, as_of):
    N = c["N"]; keep = N + 2; parts = []
    for pair in c["dirs"]:
        s, err = _dir_state(pair, G, as_of, keep, K1 if len(c["dirs"]) == 1 else K2)
        if err: return None, {"unpriced": err}
        parts.append(s)
    today = parts[0]["today"]; since_created = max(0, (today - c["created"].astimezone(ZoneInfo("UTC")).date()).days)
    last_reset = (c["end"] - today).days; horizon = last_reset + N + 1
    if horizon <= 0: return None, {"unpriced": "past its date"}
    def runs(part):
        out = []
        for w, st, M0, M1 in part["comps"]:
            S = 2; dist = np.zeros((S, N + 1))
            for (s, L), p in st.items():
                r = (part["Tn"] - 1 - L) if L is not None else N
                dist[s, min(r, N)] += p
            out.append((w, dist, M0, M1))
        return out
    A = runs(parts[0]); B = runs(parts[1]) if len(parts) > 1 else [(1.0, None, None, None)]
    p_tot = 0.0; wsum = 0.0
    for wa, da, M0a, M1a in A:
        for wb, db, M0b, M1b in B:
            if db is None:
                joint, M0, M1 = da, M0a, M1a
            else:
                joint = np.einsum("ar,bs->abrs", da, db).reshape(4, N + 1, N + 1)
                rr = np.minimum.outer(np.arange(N + 1), np.arange(N + 1))
                j2 = np.zeros((4, N + 1))
                for k in range(N + 1): j2[:, k] = joint[:, rr == k].sum(axis=1)
                joint = j2; M0 = np.kron(M0a, M0b); M1 = np.kron(M0a + M1a, M0b + M1b) - M0
            S = joint.shape[0]; init = np.zeros((S, N))
            for r in range(N + 1):
                re_ = min(r, since_created)
                if re_ < N: init[:, re_] += joint[:, r]
            m = init.sum()
            if m < 1e-9: init = np.zeros((S, N)); init[:, 0] = joint.sum(axis=1); m = init.sum()
            p_tot += wa * wb * _first_passage(init / m, M0, M1, N, horizon, last_reset); wsum += wa * wb
    return round(p_tot / wsum, 4), {"source": " + ".join(p["src"] for p in parts), "N": N}

# ---------------------------------------------------------------- production hook + replay
def price_all(PP, G, now):
    S = store(); ng = na = 0
    for c in gap_contracts(S):
        if not c["open"]: continue
        try: p, d = gap_price(c, G, now)
        except Exception as ex: print(f"[gap] {c['id']} FAILED {ex!r}"); continue
        if p is None: print(f"[gap] {c['id']} unpriced: {d}"); continue
        PP[c["id"]] = {"p": p, "group": "gap:" + "+".join(c["dirs"]), "source": d["source"], "q": None, "pi": None, "component": "unified-gap-v0"}; ng += 1
    allc = agreement_contracts(S); model = model_in_use()
    for c in allc:
        if not c["open"]: continue
        p, d = agreement_price(c, allc, now, model)
        if p is None: continue
        PP[c["id"]] = {"p": p, "group": f"agreement:{c['actors']}:{c['type']}", "source": json.dumps(d), "q": None, "pi": None, "component": COMPONENT[model]}; na += 1
    print(f"[ceasefire-bc] priced {ng} effective-ceasefire (gap) and {na} agreement contracts")

def replay():
    cs, _ = UD.load(); G = UD.groups(cs); S = store()
    cache = json.loads(CH.PRICES.read_text()) if CH.PRICES.exists() else {}
    rows, skip = [], Counter()
    for c in gap_contracts(S):
        if c["y"] is None: continue
        as_of = c["created"] + dt.timedelta(hours=24)
        if not c["known"] or c["known"] <= as_of: skip["gap: resolved before first run"] += 1; continue
        if c["end"] < as_of.date(): skip["gap: past date"] += 1; continue
        p, d = gap_price(c, G, as_of)
        if p is None: skip["gap: " + str(d)[:50]] += 1; continue
        rows.append({"fam": "B", "series": "+".join(c["dirs"]), "y": c["y"], "u": p, "m": CH.market_price(c["tok"], as_of, cache) if c["tok"] else None, "q": c["q"], "date": str(c["end"])})
    allc = agreement_contracts(S)
    for c in allc:
        if c["y"] is None: continue
        as_of = c["created"] + dt.timedelta(hours=24)
        if not c["known"] or c["known"] <= as_of: skip["agreement: resolved before first run"] += 1; continue
        p, d = agreement_price(c, allc, as_of)
        if p is None: skip["agreement: past date"] += 1; continue
        rows.append({"fam": "C", "series": f"{c['actors']}:{c['type']}", "y": c["y"], "u": p, "m": CH.market_price(c["tok"], as_of, cache) if c["tok"] else None, "q": c["q"], "date": str(c["end"])})
    CH.PRICES.write_text(json.dumps(cache) + "\n")
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    res = {}
    print(f"\n=== B/C REPLAY (report only; publishing does not depend on it): {len(rows)} contracts | skipped {dict(skip)}")
    for fam in ("B", "C"):
        xs = [x for x in rows if x["fam"] == fam and x["m"] is not None]
        if xs: print(f"  FAMILY {fam}: n={len(xs)} unified/agreement {B(xs, 'u'):.4f} market {B(xs, 'm'):.4f}"); res[fam] = {"n": len(xs), "brier_model": round(B(xs, "u"), 4), "brier_market": round(B(xs, "m"), 4)}
        for s in sorted({x["series"] for x in xs}):
            ys = [x for x in xs if x["series"] == s]
            print(f"    {s:40} n={len(ys):3} (YES {sum(x['y'] for x in ys)}) model {B(ys, 'u'):.4f} market {B(ys, 'm'):.4f}")
            res[f"{fam}:{s}"] = {"n": len(ys), "yes": sum(x["y"] for x in ys), "brier_model": round(B(ys, "u"), 4), "brier_market": round(B(ys, "m"), 4)}
    REPLAY.write_text(json.dumps({"results": res, "skipped": dict(skip), "rows": rows, "computed_at": dt.datetime.now(UTC).isoformat()}, indent=1) + "\n")
    return rows

def compare(write=True):
    """docs/c1_prereg.md items 4-5: C0 vs C0+fix vs C1 vs market on every resolved C contract (24h after listing); switch rule."""
    S = store(); allc = agreement_contracts(S); cache = json.loads(CH.PRICES.read_text()) if CH.PRICES.exists() else {}
    rows, skip = [], Counter()
    for c in allc:
        if c["y"] is None: continue
        as_of = c["created"] + dt.timedelta(hours=24)
        if not c["known"] or c["known"] <= as_of: skip["resolved before first run"] += 1; continue
        ps = {m: agreement_price(c, allc, as_of, m)[0] for m in ("C0", "C0fix", "C1")}
        if any(v is None for v in ps.values()): skip["past date"] += 1; continue
        mk = CH.market_price(c["tok"], as_of, cache) if c["tok"] else None
        if mk is None: skip["no market price"] += 1; continue
        rows.append({"id": c["id"], "actors": c["actors"], "type": c["type"], "y": c["y"], "m": mk, **ps, "q": c["q"]})
    CH.PRICES.write_text(json.dumps(cache) + "\n")
    cl = lambda p: min(0.999, max(0.001, p))
    B = lambda xs, k: sum((x[k] - x["y"]) ** 2 for x in xs) / len(xs)
    LL = lambda xs, k: -sum(math.log(cl(x[k]) if x["y"] else 1 - cl(x[k])) for x in xs) / len(xs)
    M = ("C0", "C0fix", "C1", "m")
    print(f"\n=== C1 COMPARISON (docs/c1_prereg.md): n={len(rows)} | skipped {dict(skip)}")
    print("  overall   " + " | ".join(f"{k}: Brier {B(rows, k):.4f} logloss {LL(rows, k):.3f}" for k in M))
    for y in (1, 0):
        s = [x for x in rows if x["y"] == y]
        if s: print(f"  {'YES' if y else 'NO '} n={len(s):3} " + " | ".join(f"{k} {B(s, k):.4f}" for k in M))
    for a in sorted({(x["actors"], x["type"]) for x in rows}):
        s = [x for x in rows if (x["actors"], x["type"]) == a]
        print(f"    {a[0] + ':' + a[1]:34} n={len(s):3} YES {sum(x['y'] for x in s):2} " + " | ".join(f"{k} {B(s, k):.3f}" for k in M))
    groups = sorted({x["actors"] for x in rows}); rng = np.random.default_rng(20261022); diffs = []
    for _ in range(2000):
        pick = rng.choice(groups, len(groups)); xs = [x for g in pick for x in rows if x["actors"] == g]
        diffs.append(B(xs, "C1") - B(xs, "C0"))
    lo, hi = np.percentile(diffs, [2.5, 97.5])
    print(f"  cluster bootstrap by actor set (2,000): Brier(C1) - Brier(C0) = {B(rows, 'C1') - B(rows, 'C0'):+.4f}  95% [{lo:+.4f}, {hi:+.4f}]")
    pick = "C1" if B(rows, "C1") < B(rows, "C0") else ("C0fix" if B(rows, "C0fix") < B(rows, "C0") else "C0")
    print(f"  SWITCH RULE -> production model: {pick} ({COMPONENT[pick]})")
    print("  caveat: development data (C0's failure here motivated C1); not confirmation.")
    if write:
        CPOL.write_text(json.dumps({"model": pick, "rule": "docs/c1_prereg.md item 5", "n": len(rows),
                                    "brier": {k: round(B(rows, k), 4) for k in M}, "logloss": {k: round(LL(rows, k), 4) for k in M},
                                    "bootstrap_c1_minus_c0": [round(float(lo), 4), round(float(hi), 4)],
                                    "computed_at": dt.datetime.now(UTC).isoformat()}, indent=2) + "\n")
        (ROOT / "pilot" / "c1_comparison_rows.json").write_text(json.dumps(rows, indent=1) + "\n")
    return rows

def dry():
    cs, _ = UD.load(); G = UD.groups(cs); now = dt.datetime.now(UTC); PP = {}; price_all(PP, G, now)
    S = store()
    for k, v in sorted(PP.items(), key=lambda kv: (kv[1]["component"], str((S.get(kv[0]) or {}).get("question")))):
        r = S.get(k, {}); mk = None
        try: mk = float(json.loads(r.get("outcomePrices") or "[]")[0])
        except Exception: pass
        print(f"  {v['component']:15} ours {v['p']:.3f} mkt {mk if mk is None else round(mk, 3)} | {(r.get('question') or k)[:70]}")

def _tests():
    il = "This market will resolve to “Yes” if there is a continuous 14-day period during which Israel does not take a qualifying military action against Lebanon that begins at any time between market creation and the specified date."
    hs = "This market will resolve to \"Yes\" if there is a continuous 14-day period during which neither the Houthis nor Saudi Arabia takes a qualifying military action against the other, following a qualifying military action."
    ru = "This market will resolve to “Yes” if there is a ceasefire agreement between Russia and Ukraine by the specified date. A ceasefire agreement refers to any mutually-agreed suspension of direct military engagement."
    assert classify_all("Israel x Lebanon Effective Ceasefire by October 31?", il) == {"family": "GAP", "N": 14, "dirs": ["israel->lebanon"]}
    assert classify_all("Houthi x Saudi Arabia effective ceasefire by October 31?", hs) == {"family": "GAP", "N": 14, "dirs": ["houthi->saudiarabia", "saudiarabia->yemen"]}
    assert classify_all("Russia x Ukraine ceasefire agreement by October 31, 2026?", ru) == {"family": "AGREEMENT", "type": "CEASEFIRE", "actors": "russia|ukraine"}
    assert classify_all("Ukraine signs peace deal with Russia before 2027?", "resolve Yes if Ukraine and Russia sign a peace deal agreement")["type"] == "DEAL"
    assert classify_all("Israel x Hamas ceasefire cancelled by December 31?", "resolve Yes if the ceasefire agreement is cancelled")["type"] == "BREAKDOWN"
    assert classify_all("Will Steve Witkoff attend a US x Iran diplomatic meeting by December 31, 2026?", "x")  is None
    assert classify_all("Russia-Ukraine peace talks by October 31, 2026?", "agree")["family"] == "PROCESS"
    c0 = dt.datetime(2026, 5, 13, tzinfo=UTC)
    assert due_date("Russia x Ukraine ceasefire agreement by October 31, 2026?", "", c0) == dt.date(2026, 10, 31)
    assert due_date("Ukraine signs peace deal with Russia before 2027?", "", c0) == dt.date(2026, 12, 31)
    assert due_date("US-Iran ceasefire continues through the midterms?", "by November 3, 2026, 11:59 PM ET", c0) == dt.date(2026, 11, 3)
    # loglik: overlapping YES windows intersect, NO days are removed from them
    d = dt.date
    ll, nno, ny = loglik([(d(2026, 1, 1), d(2026, 3, 31), 0), (d(2026, 4, 1), d(2026, 5, 31), 1), (d(2026, 5, 1), d(2026, 6, 30), 1)])
    assert nno == 90 and ny == 1
    # exact likelihood: two overlapping YES windows satisfied by two separate events is possible (intersection would forbid it)
    w2 = [(d(2026, 1, 1), d(2026, 1, 5), 1), (d(2026, 1, 4), d(2026, 1, 9), 1), (d(2026, 1, 4), d(2026, 1, 5), 0)]
    le, _, _ = loglik_exact(w2, np.array([10.0]))
    assert np.isfinite(le[0])                                            # events on days 1-3 and 6-9 satisfy both
    li, _, _ = loglik(w2); assert len(li) == len(LAM)
    le1, _, _ = loglik_exact([(d(2026, 1, 1), d(2026, 1, 10), 1)], np.array([36.525]))   # P(>=1 in 10 days) at 0.1/day
    assert abs(le1[0] - math.log(1 - (1 - (1 - math.exp(-0.1))) ** 10)) < 1e-9
    # first passage: a chain that never strikes reaches N quiet days with certainty; one that always strikes never does
    N = 3; init = np.zeros((2, N)); init[0, 0] = 1
    assert abs(_first_passage(init, np.eye(2), np.zeros((2, 2)), N, 10, 5) - 1) < 1e-12
    assert _first_passage(init, np.zeros((2, 2)), np.eye(2), N, 10, 5) == 0
    # strikes after the date end the contract: always strike until day 2, never after -> YES only if reset allowed through day 2
    print("ceasefire_bc tests: OK")

if __name__ == "__main__":
    if "--test" in sys.argv: _tests()
    if "--replay" in sys.argv: replay()
    if "--dry" in sys.argv: dry()
    if "--compare" in sys.argv: compare()
