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
  q         walk-forward Beta(1,1) over the pair's resolved dailies, exactly as v1 (one change at a time).
v2a = resolutions only; v2b adds ceasefire-announcement evidence from the news collector.
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

ROOT = Path(__file__).resolve().parent.parent
CONFIG = ROOT / "pilot" / "during_war_config.json"
FEED = ROOT / "pipeline" / "classified_feed.json"
BRIER = ROOT / "predictions" / "brier_log.jsonl"
OUT = ROOT / "pilot" / "shadow_log_v2.jsonl"
VERSION = "shadow-v2a"
LN2 = math.log(2)
MON = "january february march april may june july august september october november december".split()

def T(s):
    x = dt.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    return x if x.tzinfo else x.replace(tzinfo=dt.timezone.utc)

def parse_day(text, pat, ref):
    m = pat.match(text or "")
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
        out[name] = {**p, "D": D, "pat": re.compile(p["label_regex"])}
    return out

def variants(D):
    base = {"mu": LN2 / D["mu_half_life_days"], "h": LN2 / D["h_half_life_days"],
            "q0": D["q0"], "kappa": 1.0, "pi_seed": 1.0}
    V = {"primary": base, "kappa_0.5": {**base, "kappa": 0.5}}
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
        if not pair["pat"].match(label):
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

def state_asof(res, as_of, pair):
    as_of_day = as_of.astimezone(ZoneInfo(pair["day_tz"])).date()
    known = [r for r in res if r["known"] < as_of]
    n, k = len(known), sum(r["outcome"] for r in known)
    q = (1 + k) / (2 + n)
    ev, dup = {}, 0
    for r in sorted(known, key=lambda r: r["known"]):
        if r["day"] is None or r["day"] > as_of_day:
            continue
        if r["day"] in ev:
            dup += 1; continue
        ev[r["day"]] = r["outcome"]
    seed = dt.date.fromisoformat(pair["seed_date"])
    pis = {}
    for name, P in variants(pair["D"]).items():
        sF, sN = math.exp(-P["mu"]), 1 - math.exp(-P["h"])
        pi, t = P["pi_seed"], seed
        while t < as_of_day:
            t += dt.timedelta(days=1)
            pi = pi * sF + (1 - pi) * sN
            if t in ev:
                y = ev[t]
                lF = (q if y else 1 - q) ** P["kappa"]
                lN = (P["q0"] if y else 1 - P["q0"]) ** P["kappa"]
                pi = pi * lF / (pi * lF + (1 - pi) * lN)
        pis[name] = (pi, P)
    return {"as_of_day": as_of_day, "q": q, "n": n, "k": k,
            "n_evidence_days": len(ev), "dup_days": dup, "pi": pis}

def price(st, ahead):
    out = {}
    for name, (pi, P) in st["pi"].items():
        sF, sN = math.exp(-P["mu"]), 1 - math.exp(-P["h"])
        pd = pi
        for _ in range(max(0, ahead)):
            pd = pd * sF + (1 - pd) * sN
        out[name] = round(pd * st["q"] + (1 - pd) * P["q0"], 4)
    return out

def v1_price(q, ahead):
    pd = math.exp(-(LN2 / 180) * ahead)          # v1 primary: pi = 1, h = 0, 180d half-life, q0 = 0.10
    return round(pd * q + (1 - pd) * 0.10, 4)

def live(dry):
    now = dt.datetime.now(dt.timezone.utc)
    feed = json.loads(FEED.read_text())
    feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    for name, pair in load_config().items():
        res, seen = load_resolved(pair)
        st = state_asof(res, now, pair)
        lines = []
        for m in feed:
            text = m.get("label") or m.get("question") or ""
            d = parse_day(text, pair["pat"], st["as_of_day"])
            mid = str(m.get("market_id"))
            if d is None or mid in seen or m.get("resolved"):
                continue
            ahead = (d - st["as_of_day"]).days
            if ahead < 0:
                continue
            pr = price(st, ahead)
            lines.append(json.dumps({
                "logged_at": now.isoformat(), "version": VERSION, "pair": name,
                "market_id": mid, "market_label": text, "contract_day": d.isoformat(), "days_ahead": ahead,
                "q": round(st["q"], 4), "q_n": st["n"], "q_yes": st["k"],
                "n_evidence_days": st["n_evidence_days"], "dup_days": st["dup_days"],
                "pi_now": round(st["pi"]["primary"][0], 4),
                "pi_now_variants": {k: round(v[0], 4) for k, v in st["pi"].items()},
                "shadow_p": pr["primary"], "shadow_variants": pr, "v1_equivalent": v1_price(st["q"], ahead),
                "production_p": m.get("conditional_p"), "market_p": m.get("market_price"),
                "spec": "during-war v0.4; v2a fighting-state filter, resolutions only"}))
            print(f"  {name} {d} (+{ahead}d)  v2a {pr['primary']:.3f}  v1 {v1_price(st['q'], ahead):.3f}  "
                  f"prod {m.get('conditional_p')}  mkt {m.get('market_price')}")
        if lines and not dry:
            with open(OUT, "a") as f:
                f.write("\n".join(lines) + "\n")
        print(f"[{VERSION}] {name}: pi_now {st['pi']['primary'][0]:.4f}, q {st['q']:.3f} ({st['k']}/{st['n']}), "
              f"{st['n_evidence_days']} evidence days, {len(lines)} open markets {'(dry, not written)' if dry else 'logged'}")

def replay():
    B = lambda p, y: (p - y) ** 2
    mean = lambda xs: sum(xs) / len(xs) if xs else float("nan")
    for name, pair in load_config().items():
        res, _ = load_resolved(pair)
        rows = []
        for r in sorted(res, key=lambda r: (r["first_ts"] or r["known"], r["day"] or dt.date.min)):
            if r["first_ts"] is None or r["day"] is None:
                continue
            st = state_asof(res, r["first_ts"], pair)
            ahead = (r["day"] - st["as_of_day"]).days
            if ahead < 0:
                continue
            rows.append((r, st, ahead, price(st, ahead), v1_price(st["q"], ahead)))
        print(f"=== replay {name}: {len(rows)} markets (of {len(res)} resolved), forecast days "
              f"{sorted({str(x[1]['as_of_day']) for x in rows})}")
        print("  day        ahead y  q_n  ev  pi_v2a   v1     v2a    mkt")
        for r, st, a, pr, v1 in rows:
            print(f"  {r['day']}  {a:>4}  {r['outcome']}  {st['n']:>3}  {st['n_evidence_days']:>2}  "
                  f"{st['pi']['primary'][0]:.3f}  {v1:.3f}  {pr['primary']:.3f}  {r['mkt_first']}")
        v1b = mean([B(v1, r["outcome"]) for r, st, a, pr, v1 in rows])
        v2b = mean([B(pr["primary"], r["outcome"]) for r, st, a, pr, v1 in rows])
        mk = [B(r["mkt_first"], r["outcome"]) for r, *_ in rows if r["mkt_first"] is not None]
        print(f"  Brier  v1 {v1b:.4f} | v2a {v2b:.4f} | market {mean(mk):.4f} (n={len(mk)})")
        for v in rows[0][3]:
            print(f"    v2a[{v}] {mean([B(pr[v], r['outcome']) for r, st, a, pr, v1 in rows]):.4f}")
        for day in sorted({x[1]["as_of_day"] for x in rows}):
            sub = [x for x in rows if x[1]["as_of_day"] == day]
            print(f"  batch {day} (n={len(sub)}, evidence days {sub[0][1]['n_evidence_days']}): "
                  f"v1 {mean([B(x[4], x[0]['outcome']) for x in sub]):.4f}  "
                  f"v2a {mean([B(x[3]['primary'], x[0]['outcome']) for x in sub]):.4f}")
        print(f"  CHECK harness: v1 = {v1b:.4f} vs Oct 16 replay 0.163 -> {'PASS' if abs(v1b - 0.163) <= 0.002 else 'FAIL: investigate before reading anything else'}")
        print(f"  CHECK rule: v2a - v1 = {v2b - v1b:+.4f} -> {'PASS' if v2b - v1b <= 0.005 else 'FAIL: see per-batch split (cold start vs evidence batches)'}")

if __name__ == "__main__":
    if "--replay" in sys.argv:
        replay()
    else:
        try:
            live("--dry" in sys.argv)
        except Exception as ex:
            print(f"[{VERSION}] failed ({ex!r}) -- non-fatal")
