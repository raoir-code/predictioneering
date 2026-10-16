"""
Shadow pricer, Israel -> Lebanon single-day contracts.
During-War spec v0.4, pilot fallback branch (ledger sensitivity 0.26 < 0.6, Oct 16).
LOGS ONLY: never publishes, never writes production files.

  P(YES on day d) = pi_d * q + (1 - pi_d) * q0
  q    walk-forward Beta(1,1) mean over resolved Israel->Lebanon dailies, using only
       resolutions recorded before now (earliest resolved_at per market)
  pi   fighting probability now. v1 = 1.0: ceasefire detector not built yet (logged).
  pi_d pi * exp(-mu * days_ahead); h = 0 short-run (provisional); mu = ln2 / half-life
  q0   0.10 provisional; only matters once pi < 1
  Primary half-life 180 days; 90 and 365 logged as sensitivity.
Tier 1 part 2 scoring rule (pre-registered Oct 16): each market is scored on the first day
shadow logged it, against production's and the market's values from that same day.
Writes pilot/shadow_log.jsonl.
"""
import json, math, re, datetime as dt
from collections import defaultdict
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
FEED = ROOT / "pipeline" / "classified_feed.json"
BRIER = ROOT / "predictions" / "brier_log.jsonl"
OUT = ROOT / "pilot" / "shadow_log.jsonl"
PAT = re.compile(r"Israel military action against Lebanon on (\w+) (\d+)(?:, (\d{4}))?\?")
MON = "january february march april may june july august september october november december".split()
HALF_LIVES = {"primary_180": 180, "sens_90": 90, "sens_365": 365}
Q0, PI_NOW = 0.10, 1.0
T = lambda s: dt.datetime.fromisoformat(s.replace("Z", "+00:00"))

def contract_day(text, today):
    m = PAT.match(text or "")
    if not m:
        return None
    y = int(m.group(3)) if m.group(3) else today.year
    d = dt.date(y, MON.index(m.group(1).lower()) + 1, int(m.group(2)))
    return d if (d - today).days > -200 else dt.date(y + 1, d.month, d.day)

def main():
    now = dt.datetime.now(dt.timezone.utc)
    today_jlm = now.astimezone(ZoneInfo("Asia/Jerusalem")).date()
    rows = defaultdict(list)
    for l in BRIER.read_text().splitlines():
        if l.strip():
            r = json.loads(l); rows[str(r["market_id"])].append(r)
    resolved = []
    for rs in rows.values():
        if PAT.match(rs[-1].get("market_label") or "") and any(x.get("resolved_at") for x in rs):
            known = min(T(x["resolved_at"]) for x in rs if x.get("resolved_at"))
            if known < now:
                resolved.append(rs[-1]["outcome"])
    n, k = len(resolved), sum(resolved)
    q = (1 + k) / (2 + n)
    feed = json.loads(FEED.read_text())
    feed = feed if isinstance(feed, list) else feed.get("markets", feed.get("data", []))
    resolved_ids = set(rows)
    written = 0
    with open(OUT, "a") as f:
        for m in feed:
            text = m.get("label") or m.get("question") or ""
            d = contract_day(text, today_jlm)
            mid = str(m.get("market_id"))
            if d is None or mid in resolved_ids or m.get("resolved"):
                continue
            ahead = (d - today_jlm).days
            if ahead < 0:
                continue  # contract day already over, awaiting resolution: not a forecast
            prices = {}
            for name, hl in HALF_LIVES.items():
                pi_d = PI_NOW * math.exp(-(math.log(2) / hl) * ahead)
                prices[name] = round(pi_d * q + (1 - pi_d) * Q0, 4)
            f.write(json.dumps({
                "logged_at": now.isoformat(), "market_id": mid, "market_label": text,
                "contract_day_jlm": d.isoformat(), "days_ahead": ahead,
                "q": round(q, 4), "q_n": n, "q_yes": k, "pi_now": PI_NOW,
                "pi_source": "v1 constant: ceasefire detector not built",
                "q0": Q0, "shadow_p": prices["primary_180"], "shadow_sensitivity": prices,
                "production_p": m.get("conditional_p"), "market_p": m.get("market_price"),
                "spec": "during-war v0.4 pilot fallback"}) + "\n")
            written += 1
            print(f"  {d} (+{ahead}d)  shadow {prices['primary_180']:.3f}  "
                  f"prod {m.get('conditional_p')}  mkt {m.get('market_price')}")
    print(f"[shadow] q = {q:.3f} from {n} resolved ({k} YES); {written} open markets logged")

if __name__ == "__main__":
    try:
        main()
    except Exception as ex:
        print(f"[shadow] failed ({ex}) -- non-fatal")
