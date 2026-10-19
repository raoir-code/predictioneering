"""
Shadow pricer v2a: fighting-state filter (during-war spec v0.4).
Generic over initiator->territory pairs in pilot/during_war_config.json.
LOGS ONLY to pilot/shadow_log_v2.jsonl. v1 (tag shadow-v1) is the sole version scored in Tier 1 part 2.

Two-state chain per pair, daily steps (F fighting, N not fighting):
  drift     P(F tomorrow | F) = exp(-mu)     mu = ln2 / mu_half_life  (cessation: the accepted-offer event)
            P(F tomorrow | N) = 1 - exp(-h)  h  = ln2 / h_half_life   (re-entry; theory: SSPE onset hazard,
                                              engine value is a lower bound; Phase 5 wires it in)
  evidence  each resolved daily = one battle-round outcome, used only if resolved before the forecast time.
            YES: L_F = q, L_N = q0.  NO: L_F = 1-q, L_N = 1-q0.  Likelihoods ** kappa (primary 1.0).
  price     P(YES on day d) = pi_d * q + (1 - pi_d) * q0; pi_d = today's filtered pi carried forward by the drift.
  q         v2c: q = (k + w*m) / (n + w), w = prior_weight (2, unchanged from Beta(1,1)); m = theater center
            (other pairs' (YES+1)/(resolved+2), walk-forward); m = 0.5 when they have no data, i.e. v1's Beta(1,1).
            Variants: pool_off (center 0.5 = v2b), pool_w8 (w = 8). v1_equivalent always uses the unpooled q.
v2b: + ceasefire-announcement evidence (pilot/ceasefire_news.py); each NEW_AGREEMENT event multiplies the odds
          of fighting by 1/announcement_lr on the day our system first held it. Variant news_off = v2a exactly.
Known limit, stated before the replay: with no resolutions yet (cold start) pi is only the chain's drift
from the seed, so v2a holds less information than v1's hard-coded pi = 1.

  python pilot/fighting_state.py            live: append a row per open daily, every configured pair
  python pilot/fighting_state.py --dry      live prices, print only
  python pilot/fighting_state.py --replay   walk-forward replay on resolved dailies vs v1 and market
"""
import json, math, re, sys, datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ceasefire_news as cn

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pilot" / "during_war_config.json"
FEED = ROOT / "pipeline" / "classified_feed.json"
BRIER = ROOT / "predictions" / "brier_log.jsonl"
OUT = ROOT / "pilot" / "shadow_log_v2.jsonl"
VERSION = "during-war-v2e"
LN2 = math.log(2)
MON = "january february march april may june july august september october november december".split()
_M = "January|February|March|April|May|June|July|August|September|October|November|December"
DAY = re.compile(r"\bon (" + _M + r") (\d{1,2})(?:, (\d{4}))?\?\s*$", re.I)
TEMPLATE = re.compile(r"^(?:Will there be )?(.+?) military action against (.+?) on (?:" + _M + r")\b", re.I)
TC_PATH = ROOT / "pipeline" / "translator_cache.json"
_TC = None
DISAGREE = []

def _norm(x):
    return re.sub(r"[^a-z]", "", (x or "").lower())

def belongs(mid, text, pair):
    """Generic membership for single-day contracts. Clergyman initiator/target when present, else the standard
    Polymarket template '<A> military action against <B> on <date>?'. If both exist they must agree."""
    global _TC
    if _TC is None:
        try:
            _TC = json.loads(TC_PATH.read_text())
        except Exception:
            _TC = {}
    if not DAY.search(text or ""):
        return False
    c = _TC.get(str(mid)); c = c.get("clergy") if isinstance(c, dict) else None
    gc = (_norm(c.get("contract_initiator")), _norm(c.get("contract_target"))) if isinstance(c, dict) and c.get("contract_initiator") and c.get("contract_target") else None
    m = TEMPLATE.match(text or "")
    gt = (_norm(m.group(1)), _norm(m.group(2))) if m else None
    if gc and gt and gc != gt:
        DISAGREE.append((str(mid), gc, gt)); return False
    return (gc or gt) == (_norm(pair["initiator"]), _norm(pair["territory"]))

def T(s):
    x = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)

def parse_day(text, pat, ref):
    m = DAY.search(text or "")   # generic single-day form; pat unused, kept for call compatibility
    if not m:
        return None
    y = int(m.group(3)) if m.group(3) else ref.year
    d = dt.date(y, MON.index(m.group(1).lower()) + 1, int(m.group(2)))
    if not m.group(3):
        if (d - ref).days > 200:
            d = d.replace(year=y - 1)
        elif (d - ref).days < -200:
            d = d.replace(year=y + 1)
    return d

def load_config():
    c = json.loads(CONFIG.read_text())
    out = {}
    for name, p in c["pairs"].items():
        D = {**c["theater_defaults"][p["theater"]], **p.get("overrides", {})}
        out[name] = {**p, "name": name, "D": D, "pat": None}
    return out

def variants(D):
    base = {"mu": LN2 / D["mu_half_life_days"], "h": LN2 / D["h_half_life_days"],
            "q0": D["q0"], "kappa": 1.0, "pi_seed": 1.0, "announcement_lr": D["announcement_lr"], "pool": D.get("pool", True), "prior_w": D.get("prior_weight", 2.0)}
    V = {"primary": base, "kappa_0.5": {**base, "kappa": 0.5}}
    V["news_off"] = {**base, "announcement_lr": 1.0}   # reproduces v2a exactly
    V["lr_4"] = {**base, "announcement_lr": 4.0}
    V["lr_2"] = {**base, "announcement_lr": 2.0}
    V["pool_off"] = {**base, "pool": False}         # = v2b
    V["pool_w8"] = {**base, "pool": True, "prior_w": 8.0}
    V["pool_on"] = {**base, "pool": True}
    for hl in (90, 365):
        V[f"mu_hl_{hl}"] = {**base, "mu": LN2 / hl}
    for hl in (14, 90, 365):
        V[f"h_hl_{hl}"] = {**base, "h": LN2 / hl}
    for q0 in (0.05, 0.20):
        V[f"q0_{q0}"] = {**base, "q0": q0}
    return V

def load_resolved(pair):
    rows = defaultdict(list)
    for l in BRIER.read_text().splitlines():
        if l.strip():
            r = json.loads(l); rows[str(r["market_id"])].append(r)
    tz = ZoneInfo(pair["day_tz"]); res = []
    for mid, rs in rows.items():
        label = rs[-1].get("market_label") or ""
        if not belongs(mid, label, pair):
            continue
        ts = [T(x["resolved_at"]) for x in rs if x.get("resolved_at")]
        if not ts:
            continue
        o = rs[-1]["outcome"]
        assert o in (0, 1), f"unexpected outcome {o!r} for market {mid}"
        known = min(ts)
        first = [T(x["first_prediction_ts"]) for x in rs if x.get("first_prediction_ts")]
        last = rs[-1]
        mk = last.get("market_p_true_first")
        res.append({"market_id": mid, "label": label, "known": known, "outcome": int(o),
                    "day": parse_day(label, pair["pat"], known.astimezone(tz).date()),
                    "first_ts": min(first) if first else None,
                    "mkt_first": mk if mk is not None else last.get("market_p_at_first"),
                    "prod_first": last.get("first_p")})
    return res, set(rows)

def theater_others(cfg, name):
    th = cfg[name]["theater"]
    return [load_resolved(p)[0] for n2, p in cfg.items() if n2 != name and p["theater"] == th]

def state_asof(res, as_of, pair, others=()):
    as_of_day = as_of.astimezone(ZoneInfo(pair["day_tz"])).date()
    known = [r for r in res if r["known"] < as_of]
    n, k = len(known), sum(r["outcome"] for r in known)
    q = (1 + k) / (2 + n)   # unpooled Beta(1,1): v1 and pool_off
    ko = no = 0
    for o in others:
        for r in o:
            if r["known"] < as_of:
                no += 1; ko += r["outcome"]
    m = (ko + 1) / (no + 2)
    ev, dup = {}, 0
    for r in sorted(known, key=lambda r: r["known"]):
        if r["day"] is None or r["day"] > as_of_day:
            continue
        if r["day"] in ev:
            dup += 1; continue
        ev[r["day"]] = r["outcome"]
    try:
        ann = sorted({e["first"].astimezone(ZoneInfo(pair["day_tz"])).date() for e in cn.events(pair["name"], pair, as_of)})
        news_status = "ok"
    except Exception as ex:
        ann, news_status = [], f"error: {ex!r}"[:200]
    ann_set = set(ann)
    seed = dt.date.fromisoformat(pair["seed_date"])
    pis = {}
    for name, P in variants(pair["D"]).items():
        sF, sN = math.exp(-P["mu"]), 1 - math.exp(-P["h"])
        pi, t = P["pi_seed"], seed
        qv = (k + P["prior_w"] * (m if P["pool"] else 0.5)) / (n + P["prior_w"])
        while t < as_of_day:
            t += dt.timedelta(days=1)
            pi = pi * sF + (1 - pi) * sN
            if t in ev:
                y = ev[t]
                lF = (qv if y else 1 - qv) ** P["kappa"]
                lN = (P["q0"] if y else 1 - P["q0"]) ** P["kappa"]
                pi = pi * lF / (pi * lF + (1 - pi) * lN)
            if t in ann_set and P["announcement_lr"] != 1.0:
                fac = (1.0 / P["announcement_lr"]) ** P["kappa"]
                pi = pi * fac / (pi * fac + (1 - pi))
        pis[name] = (pi, P, qv)
    return {"as_of_day": as_of_day, "q": pis["primary"][2], "q_v1": q, "theater_m": m, "theater_n": no, "n": n, "k": k,
            "n_evidence_days": len(ev), "dup_days": dup, "pi": pis,
            "announcements": [d.isoformat() for d in ann], "news_status": news_status}

def price(st, ahead):
    out = {}
    for name, (pi, P, qv) in st["pi"].items():
        sF, sN = math.exp(-P["mu"]), 1 - math.exp(-P["h"])
        pd = pi
        for _ in range(max(0, ahead)):
            pd = pd * sF + (1 - pd) * sN
        out[name] = round(pd * qv + (1 - pd) * P["q0"], 4)
    return out

def v1_price(q, ahead):
    pd = math.exp(-(LN2 / 180) * ahead)          # v1 primary: pi = 1, h = 0, 180d half-life, q0 = 0.10
    return round(pd * q + (1 - pd) * 0.10, 4)

def live(dry):
    now = dt.datetime.now(dt.timezone.utc)
    feed = json.loads(FEED.read_text())
    feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    cfg = load_config()
    for name, pair in cfg.items():
        res, seen = load_resolved(pair)
        st = state_asof(res, now, pair, theater_others(cfg, name))
        lines = []
        for m in feed:
            text = m.get("label") or m.get("question") or ""
            d = parse_day(text, pair["pat"], st["as_of_day"])
            mid = str(m.get("market_id"))
            if d is None or mid in seen or m.get("resolved") or not belongs(mid, text, pair):
                continue
            ahead = (d - st["as_of_day"]).days
            if ahead < 0:
                continue
            pr = price(st, ahead)
            lines.append(json.dumps({
                "logged_at": now.isoformat(), "version": VERSION, "pair": name,
                "market_id": mid, "market_label": text, "contract_day": d.isoformat(), "days_ahead": ahead,
                "q": round(st["q"], 4), "q_unpooled": round(st["q_v1"], 4), "theater_m": round(st["theater_m"], 4), "theater_n": st["theater_n"], "q_n": st["n"], "q_yes": st["k"],
                "n_evidence_days": st["n_evidence_days"], "dup_days": st["dup_days"],
                "announcement_days": st["announcements"], "news_status": st["news_status"],
                "pi_now": round(st["pi"]["primary"][0], 4),
                "pi_now_variants": {k: round(v[0], 4) for k, v in st["pi"].items()},
                "shadow_p": pr["primary"], "shadow_variants": pr, "v1_equivalent": v1_price(st["q_v1"], ahead),
                "production_p": m.get("conditional_p"), "market_p": m.get("market_price"),
                "spec": "during-war v0.4; v2b fighting-state filter: resolutions + ceasefire announcements"}))
            print(f"  {name} {d} (+{ahead}d)  v2a {pr['primary']:.3f}  v1 {v1_price(st['q_v1'], ahead):.3f}  "
                  f"prod {m.get('conditional_p')}  mkt {m.get('market_price')}")
        if lines and not dry:
            with open(OUT, "a") as f:
                f.write("\n".join(lines) + "\n")
        print(f"[{VERSION}] {name}: pi_now {st['pi']['primary'][0]:.4f}, q {st['q']:.3f} ({st['k']}/{st['n']}), "
              f"{st['n_evidence_days']} evidence days, {len(st['announcements'])} announcements (news {st['news_status']}), {len(lines)} open markets {'(dry, not written)' if dry else 'logged'}")

def replay():
    B = lambda p, y: (p - y) ** 2
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    cfg = load_config()
    for name, pair in cfg.items():
        res, _ = load_resolved(pair)
        others = theater_others(cfg, name)
        rows = []
        for r in sorted(res, key=lambda r: (r["first_ts"] or r["known"], r["day"] or dt.date.min)):
            if r["first_ts"] is None or r["day"] is None:
                continue
            st = state_asof(res, r["first_ts"], pair, others)
            ahead = (r["day"] - st["as_of_day"]).days
            if ahead < 0:
                continue
            rows.append((r, st, ahead, price(st, ahead), v1_price(st["q_v1"], ahead)))
        print(f"=== replay {name}: {len(rows)} markets (of {len(res)} resolved), forecast days "
              f"{sorted({str(x[1]['as_of_day']) for x in rows})}")
        print("  day        ahead y  q_n  ev  pi_v2a   v1     v2a    mkt")
        for r, st, a, pr, v1 in rows:
            print(f"  {r['day']}  {a:>4}  {r['outcome']}  {st['n']:>3}  {st['n_evidence_days']:>2}  "
                  f"{st['pi']['primary'][0]:.3f}  {v1:.3f}  {pr['primary']:.3f}  {r['mkt_first']}")
        v1b = mean([B(v1, r["outcome"]) for r, st, a, pr, v1 in rows])
        v2b = mean([B(pr["primary"], r["outcome"]) for r, st, a, pr, v1 in rows])
        mk = [B(r["mkt_first"], r["outcome"]) for r, *_ in rows if r["mkt_first"] is not None]
        print(f"  Brier  v1 {v1b:.4f} | {VERSION} {v2b:.4f} | market {mean(mk):.4f} (n={len(mk)})")
        for v in rows[0][3]:
            print(f"    {VERSION}[{v}] {mean([B(pr[v], r['outcome']) for r, st, a, pr, v1 in rows]):.4f}")
        for day in sorted({x[1]["as_of_day"] for x in rows}):
            sub = [x for x in rows if x[1]["as_of_day"] == day]
            print(f"  batch {day} (n={len(sub)}, evidence days {sub[0][1]['n_evidence_days']}): "
                  f"v1 {mean([B(x[4], x[0]['outcome']) for x in sub]):.4f}  "
                  f"v2a {mean([B(x[3]['primary'], x[0]['outcome']) for x in sub]):.4f}")
        fq = []
        for r in res:
            if r["first_ts"] is None: continue
            kn = [x for x in res if x is not r and x["known"] < r["first_ts"]]
            fq.append((((1 + sum(x["outcome"] for x in kn)) / (2 + len(kn))) - r["outcome"]) ** 2)
        print(f"  CHECK harness: flat-q (Oct 16 definition) = {mean(fq):.4f}, n={len(fq)} -> "
              f"{'PASS' if len(fq) != 36 or abs(mean(fq) - 0.1625) <= 0.002 else 'FAIL: harness drifted, investigate'}"
              f"{' (n changed since Oct 16: new resolutions, target no longer applies)' if len(fq) != 36 else ''}")
        print(f"  CHECK rule: v2a - v1 = {v2b - v1b:+.4f} -> {'PASS' if v2b - v1b <= 0.005 else 'FAIL: see per-batch split (cold start vs evidence batches)'}")

_PROD = {"cfg": None, "st": {}}

def price_for_market(market_id, text, now=None):
    """PRODUCTION entry point (Oct 19: Adi decided to patch production directly).
    Returns the v2c price for a single-day contract on a configured pair with publish=true, else None.
    Contract days already over return None (no post-event prices). Any error -> None + a loud print,
    so the caller falls back to the engine visibly, never silently."""
    try:
        now = now or dt.datetime.now(dt.timezone.utc)
        if _PROD["cfg"] is None:
            _PROD["cfg"] = load_config()
        cfg = _PROD["cfg"]
        for name, pair in cfg.items():
            if not pair.get("publish", False) or not belongs(market_id, text, pair):
                continue
            if name not in _PROD["st"]:
                res, _ = load_resolved(pair)
                _PROD["st"][name] = state_asof(res, now, pair, theater_others(cfg, name))
            st = _PROD["st"][name]
            d = parse_day(text, None, st["as_of_day"])
            ahead = (d - st["as_of_day"]).days
            if ahead < 0:
                return None   # contract day over: a price now would be post-event, leave as is
            pr = price(st, ahead)
            return {"p": pr["primary"], "model_version": VERSION, "pair": name, "days_ahead": ahead,
                    "pi_now": round(st["pi"]["primary"][0], 4), "q": round(st["q"], 4), "q_n": st["n"],
                    "news_status": st["news_status"], "variants": pr}
        return None
    except Exception as ex:
        print(f"  [during-war] ERROR pricing {market_id}: {ex!r} -- falling back to engine")
        return None

if __name__ == "__main__":
    if "--replay" in sys.argv:
        replay()
    else:
        try:
            live("--dry" in sys.argv)
        except Exception as ex:
            print(f"[{VERSION}] failed ({ex!r}) -- non-fatal")
