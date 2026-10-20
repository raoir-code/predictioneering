"""
Unified during-war engine, piece A: exact math (spec v0.4 + ChatGPT review, Oct 19).
States N=0, F=1. Generator Q = [[-h, h], [mu, -mu]] per day. Qualifying-strike rates D = diag(nu, lam),
with q = 1 - exp(-lam) (P(strike day | F)) and q0 = 1 - exp(-nu) (P(strike day | N)).
Per day: M0 = expm(Q - D) (no qualifying strike), M1 = expm(Q) - M0 (>= 1 strike). Rows sum: M0 + M1 = expm(Q).
Contracts with the SAME rules are windows on one day timeline, handled exactly by tracking L = day of the last strike:
  YES [a, b]: at the end of day b keep only states with L >= a.   NO [a, b]: on each day t in [a, b] drop states with L == t.
Values of L older than every still-pending YES window's start are merged (exact: they can no longer affect any constraint).
A one-day contract is the window [d, d]. Run this file to execute the exactness tests.
"""
import math, itertools
import numpy as np
from scipy.linalg import expm

def mats(h, mu, q, q0):
    lam, nu = -math.log(1 - q), -math.log(1 - q0)
    Q = np.array([[-h, h], [mu, -mu]])
    E = expm(Q); M0 = expm(Q - np.diag([nu, lam]))
    return E, M0, E - M0

def stationary(h, mu):
    return np.array([mu / (h + mu), h / (h + mu)])

def forward(T, windows, h, mu, q, q0, p_start=None):
    """Days 0..T-1; windows = [(a, b, y)], y in {0, 1}. Returns (log-likelihood of all windows, P(N), P(F) at end of day T-1)."""
    E, M0, M1 = mats(h, mu, q, q0); M0, M1 = M0.tolist(), M1.tolist()
    p = stationary(h, mu) if p_start is None else np.asarray(p_start, float)
    st = {(0, None): float(p[0]), (1, None): float(p[1])}
    yes_end, no_days = {}, set()
    for a, b, y in windows:
        if y: yes_end.setdefault(b, []).append(a)
        else: no_days.update(range(a, b + 1))
    ll = 0.0
    for t in range(T):
        new = {}
        for (s, L), pr in st.items():
            for s2 in (0, 1):
                new[(s2, L)] = new.get((s2, L), 0.0) + pr * M0[s][s2]
                new[(s2, t)] = new.get((s2, t), 0.0) + pr * M1[s][s2]
        if t in no_days:
            new = {k: v for k, v in new.items() if k[1] != t}
        for a in yes_end.get(t, []):
            new = {k: v for k, v in new.items() if k[1] is not None and k[1] >= a}
        pend = [a for a, b, y in windows if y and b > t]
        cut = min(pend) if pend else None
        merged = {}
        for (s, L), v in new.items():
            key = (s, L if (cut is not None and L is not None and L >= cut) else None)
            merged[key] = merged.get(key, 0.0) + v
        z = sum(merged.values())
        if not z > 0:
            return -math.inf, None
        ll += math.log(z); st = {k: v / z for k, v in merged.items()}
    return ll, np.array([sum(v for (s, _), v in st.items() if s == 0), sum(v for (s, _), v in st.items() if s == 1)])

def p_any(pi, h, mu, q, q0, gap_days, length_days):
    """P(>= 1 qualifying strike in a window starting gap_days after the current state, lasting length_days)."""
    E, M0, _ = mats(h, mu, q, q0); mp = np.linalg.matrix_power
    return float(1 - np.asarray(pi) @ mp(E, gap_days) @ mp(M0, length_days) @ np.ones(2))

def forward_joint(T, windows, h, mu, q, q0, p_start=None, keep_from=None, news_days=(), news_ratio=1.0):
    """forward() that also keeps strike days L >= keep_from distinct (to price an open window starting at keep_from);
    returns (loglik, joint {(state, L): prob} at the end of day T-1).
    news_days: days t with a POSITIVE news report of a strike in [t-2, t]; weight 1 if L >= t-2 else news_ratio (= false-alarm / catch
    rate). Days without a report carry no information (coverage gaps are clustered, never read as quiet)."""
    E, M0, M1 = mats(h, mu, q, q0); M0, M1 = M0.tolist(), M1.tolist()
    p = stationary(h, mu) if p_start is None else np.asarray(p_start, float)
    st = {(0, None): float(p[0]), (1, None): float(p[1])}
    yes_end, no_days = {}, set()
    for a, b, y in windows:
        if y: yes_end.setdefault(b, []).append(a)
        else: no_days.update(range(a, b + 1))
    ll = 0.0
    for t in range(T):
        new = {}
        for (s, L), pr in st.items():
            for s2 in (0, 1):
                new[(s2, L)] = new.get((s2, L), 0.0) + pr * M0[s][s2]
                new[(s2, t)] = new.get((s2, t), 0.0) + pr * M1[s][s2]
        if t in no_days:
            new = {k: v for k, v in new.items() if k[1] != t}
        for a in yes_end.get(t, []):
            new = {k: v for k, v in new.items() if k[1] is not None and k[1] >= a}
        if t in news_days:
            new = {k: (v if (k[1] is not None and k[1] >= t - 2) else v * news_ratio) for k, v in new.items()}
        pend = [a for a, b, y in windows if y and b > t] + ([keep_from] if keep_from is not None else []) + [n - 2 for n in news_days if n > t]
        cut = min(pend) if pend else None
        merged = {}
        for (s, L), v in new.items():
            key = (s, L if (cut is not None and L is not None and L >= cut) else None)
            merged[key] = merged.get(key, 0.0) + v
        z = sum(merged.values())
        if not z > 0:
            return -math.inf, None
        ll += math.log(z); st = {k: v / z for k, v in merged.items()}
    return ll, st

def price_open(st, h, mu, q, q0, T, a, b):
    """P(YES) for an open window [a, b] (day indices), given the joint state at the end of day T-1. None if b < T (post-event)."""
    if b < T:
        return None
    marg = lambda keep: np.array([sum(v for (s, L), v in st.items() if s == k and keep(L)) for k in (0, 1)])
    if a >= T:
        return p_any(marg(lambda L: True), h, mu, q, q0, a - T, b - a + 1)
    past = sum(v for (s, L), v in st.items() if L is not None and L >= a)
    rest = marg(lambda L: not (L is not None and L >= a))
    return past if rest.sum() <= 0 else past + (1 - past) * p_any(rest / rest.sum(), h, mu, q, q0, 0, b - T + 1)

def _tests_news():
    h, mu, q, q0, r = 1 / 40, 1 / 15, 0.6, 0.03, 0.01; E, M0, M1 = mats(h, mu, q, q0); p = stationary(h, mu); res = []
    for hist, news in (([], {3}), ([(0, 1, 0)], {4, 6}), ([(2, 5, 1)], {7}), ([(0, 2, 0), (5, 7, 0)], {4})):
        brute = 0.0
        for z in itertools.product((0, 1), repeat=8):
            if not all((any(z[x:y + 1]) if v else not any(z[x:y + 1])) for x, y, v in hist): continue
            pr = p.copy()
            for zt in z: pr = pr @ (M1 if zt else M0)
            w = float(pr.sum())
            for n in news: w *= 1.0 if any(z[max(0, n - 2):n + 1]) else r
            brute += w
        ll, _ = forward_joint(8, hist, h, mu, q, q0, news_days=news, news_ratio=r)
        ok = abs(math.exp(ll) - brute) < 1e-12; res.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  news days {sorted(news)} + windows {hist}: {math.exp(ll):.12f} vs brute force {brute:.12f}")
    return all(res)

def _tests_pricing():
    h, mu, q, q0 = 1 / 50, 1 / 20, 0.7, 0.05; E, M0, M1 = mats(h, mu, q, q0); p = stationary(h, mu)
    hist, T = [(0, 1, 0), (3, 4, 1)], 5; res = []
    for (a, b) in ((2, 8), (6, 8), (5, 5), (0, 8)):
        num = den = 0.0
        for z in itertools.product((0, 1), repeat=9):
            if all((any(z[x:y + 1]) if v else not any(z[x:y + 1])) for x, y, v in hist):
                pr = p.copy()
                for zt in z: pr = pr @ (M1 if zt else M0)
                w = float(pr.sum()); den += w; num += w if any(z[a:b + 1]) else 0.0
        ll, st = forward_joint(T, hist, h, mu, q, q0, keep_from=a if a < T else None)
        got = price_open(st, h, mu, q, q0, T, a, b); ok = abs(got - num / den) < 1e-12; res.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  open window [{a},{b}] given evidence on days 0-4: {got:.12f} vs brute force {num / den:.12f}")
    l1, _ = forward(T, hist, h, mu, q, q0); l2, _ = forward_joint(T, hist, h, mu, q, q0, keep_from=2)
    ok = abs(l1 - l2) < 1e-12; res.append(ok); print(f"  {'PASS' if ok else 'FAIL'}  forward_joint loglik == forward loglik")
    return all(res)

def _tests():
    h, mu, q, q0 = 1 / 100, 1 / 30, 0.8, 0.05
    E, M0, M1 = mats(h, mu, q, q0); p = stationary(h, mu); one = np.ones(2); mp = np.linalg.matrix_power
    ok = lambda name, x, y: print(f"  {'PASS' if abs(x - y) < 1e-9 else 'FAIL'}  {name}: {x:.12f} vs {y:.12f}") or abs(x - y) < 1e-9
    r = []
    r.append(ok("rows of M0 + M1 sum to 1", float((M0 + M1).sum(axis=1).max()), 1.0))
    ll, pi = forward(50, [], h, mu, q, q0); r.append(ok("no evidence: loglik 0", ll, 0.0)); r.append(ok("no evidence: pi stationary", float(pi[1]), float(p[1])))
    ll, _ = forward(11, [(10, 10, 1)], h, mu, q, q0); r.append(ok("one-day YES = closed form", ll, math.log(p @ mp(E, 10) @ M1 @ one)))
    ll, _ = forward(20, [(5, 19, 0)], h, mu, q, q0); r.append(ok("NO window = closed form", ll, math.log(p @ mp(E, 5) @ mp(M0, 15) @ one)))
    a, _ = forward(30, [(5, 20, 1)], h, mu, q, q0); r.append(ok("YES window = closed form", a, math.log(1 - p @ mp(E, 5) @ mp(M0, 16) @ one)))
    r.append(ok("p_any matches forward", p_any(p, h, mu, q, q0, 5, 16), math.exp(a)))
    b, _ = forward(30, [(5, 20, 1), (5, 20, 1)], h, mu, q, q0); r.append(ok("duplicate YES not double-counted", b, a))
    c, _ = forward(30, [(5, 20, 1), (8, 12, 1)], h, mu, q, q0); d, _ = forward(30, [(8, 12, 1)], h, mu, q, q0); r.append(ok("nested YES = inner only", c, d))
    e, _ = forward(30, [(5, 10, 0), (5, 20, 1)], h, mu, q, q0)
    r.append(ok("NO + overlapping YES = closed form", e, math.log(p @ mp(E, 5) @ mp(M0, 6) @ (mp(E, 10) - mp(M0, 10)) @ one)))
    rng = np.random.default_rng(7); T = 8
    for trial in range(25):
        ws = []
        for _ in range(int(rng.integers(1, 5))):
            a0 = int(rng.integers(0, T)); b0 = int(rng.integers(a0, T)); ws.append((a0, b0, int(rng.integers(0, 2))))
        brute = 0.0
        for z in itertools.product((0, 1), repeat=T):
            if all((any(z[a0:b0 + 1]) if y else not any(z[a0:b0 + 1])) for a0, b0, y in ws):
                v = p.copy()
                for zt in z: v = v @ (M1 if zt else M0)
                brute += float(v @ one)
        ll, _ = forward(T, ws, h, mu, q, q0)
        if brute == 0:
            r.append(ll == -math.inf)
        elif abs(math.exp(ll) - brute) > 1e-12:
            print(f"  FAIL  brute force trial {trial}: windows {ws}: {math.exp(ll)} vs {brute}"); r.append(False)
        else:
            r.append(True)
    print(f"  brute force: 25 random overlapping-window sets on 8 days checked against all 256 strike patterns")
    print("ALL PASS" if all(r) else "SOME TESTS FAILED")
    return all(r)

if __name__ == "__main__":
    raise SystemExit(0 if (_tests() and _tests_pricing() and _tests_news()) else 1)
