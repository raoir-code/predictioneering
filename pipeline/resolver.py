"""
pipeline/resolver.py — Brier Score Tracker

Checks Polymarket daily for resolved markets that appear in predictions/log.jsonl.
When a market resolves, records the outcome and computes Brier score contribution.
Appends to predictions/brier_log.jsonl and updates predictions/brier_summary.json.

Usage:
    python3.11 pipeline/resolver.py          # check all tracked markets
    python3.11 pipeline/resolver.py --dry-run # print what would be recorded, no writes

Brier score: (conditional_p - outcome)^2
Lower is better. Perfect score = 0.0. Chance = 0.25.
"""

import json
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, date
from pathlib import Path
from collections import defaultdict

# ─────────────────────────────────────────────────────────────────────
# CONFIG
# ─────────────────────────────────────────────────────────────────────

PREDICTIONS_LOG  = Path("predictions/log.jsonl")
BRIER_LOG        = Path("predictions/brier_log.jsonl")
BRIER_SUMMARY    = Path("predictions/brier_summary.json")
CLASSIFIED_FEED  = Path("pipeline/classified_feed.json")

GAMMA_API        = "https://gamma-api.polymarket.com/markets/{market_id}"
DRY_RUN          = "--dry-run" in sys.argv

# ─────────────────────────────────────────────────────────────────────
# POLYMARKET RESOLUTION FETCH
# ─────────────────────────────────────────────────────────────────────

def fetch_market_status(market_id: str) -> dict | None:
    """
    Fetch current market status from Polymarket Gamma API.
    Returns dict with keys: resolved, outcome, end_date, question
    Returns None on failure.
    """
    url = GAMMA_API.format(market_id=market_id)
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "predictioneering-resolver/1.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read())

        # Gamma API returns a list for market queries
        if isinstance(data, list):
            if not data:
                return None
            data = data[0]

        closed       = bool(data.get("closed", False))
        uma_status   = data.get("umaResolutionStatus", "")
        resolved     = closed and uma_status == "resolved"
        end_date     = data.get("endDate") or data.get("end_date") or ""
        question     = data.get("question") or data.get("title") or ""

        # Outcome lives in outcomes/outcomePrices, not a resolutionTitle field
        outcome = None
        raw_resolution = ""
        if resolved:
            try:
                outcomes_list = json.loads(data.get("outcomes", "[]"))
                prices_list   = json.loads(data.get("outcomePrices", "[]"))
            except (json.JSONDecodeError, TypeError):
                outcomes_list, prices_list = [], []

            raw_resolution = f"{outcomes_list}:{prices_list}"

            if len(outcomes_list) == len(prices_list) and outcomes_list:
                for name, price in zip(outcomes_list, prices_list):
                    try:
                        p = float(price)
                    except (TypeError, ValueError):
                        continue
                    if p >= 0.99:
                        o = str(name).strip().lower()
                        if o in ("yes", "true", "1"):
                            outcome = 1
                        elif o in ("no", "false", "0"):
                            outcome = 0
                        break
            # If we can't parse, leave None — will skip Brier computation

        return {
            "resolved":   resolved,
            "outcome":    outcome,
            "end_date":   end_date[:10] if end_date else "",
            "question":   question,
            "raw_resolution": raw_resolution,
        }

    except urllib.error.HTTPError as e:
        print(f"    [resolver] HTTP {e.code} for market {market_id}")
        return None
    except Exception as e:
        print(f"    [resolver] fetch failed for {market_id}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────
# LOG PARSING
# ─────────────────────────────────────────────────────────────────────

def load_predictions() -> dict:
    """
    Load all predictions from log.jsonl.
    Returns dict: market_id -> list of daily prediction entries (chronological).
    We use the FIRST prediction for each market as the Brier anchor
    (timestamped before resolution — the only clean claim).
    """
    if not PREDICTIONS_LOG.exists():
        print(f"[resolver] {PREDICTIONS_LOG} not found")
        return {}

    by_market = defaultdict(list)
    with open(PREDICTIONS_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                mid = entry.get("market_id")
                if mid:
                    by_market[mid].append(entry)
            except json.JSONDecodeError:
                continue

    return dict(by_market)


def load_brier_log() -> set:
    """Return set of market_ids already recorded in brier_log.jsonl."""
    if not BRIER_LOG.exists():
        return set()
    seen = set()
    with open(BRIER_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                seen.add(entry.get("market_id"))
            except Exception:
                continue
    return seen



# ─────────────────────────────────────────────────────────────────────
# MARKET SUNSET — stop translator/predict from re-touching resolved markets
# ─────────────────────────────────────────────────────────────────────

def sunset_market_in_feed(market_id: str, outcome: int) -> bool:
    """
    Flag a resolved market in classified_feed.json so translator.py and
    predict.py stop re-processing it daily with a frozen market_price.
    Does NOT delete the entry — preserves it for audit/debugging.
    Returns True if a matching market was found and flagged.
    """
    if not CLASSIFIED_FEED.exists():
        print(f"    [resolver] {CLASSIFIED_FEED} not found — cannot sunset {market_id}")
        return False

    with open(CLASSIFIED_FEED) as f:
        feed = json.load(f)

    found = False
    for m in feed:
        if m.get("market_id") == market_id:
            m["resolved"]         = True
            m["resolved_outcome"] = outcome
            m["resolved_at"]      = datetime.now(timezone.utc).isoformat()
            found = True
            break

    if not found:
        return False

    with open(CLASSIFIED_FEED, "w") as f:
        json.dump(feed, f, indent=2, default=str)

    return True


# ─────────────────────────────────────────────────────────────────────
# BRIER COMPUTATION
# ─────────────────────────────────────────────────────────────────────

def compute_brier_entry(market_id: str, predictions: list,
                         status: dict) -> dict | None:
    """
    Given prediction history and resolution status, compute Brier entry.

    Dual-anchor scoring:
      - FIRST prediction with a valid conditional_p = OFFICIAL anchor.
        brier_conditional / brier_engine / brier_market are unchanged —
        this is what's published as the track record.
      - LAST prediction with a valid conditional_p before resolution =
        INFORMATIONAL-only anchor. brier_last / brier_market_last show
        what the score would be if judged at resolution instead of at
        posting. Never used as the official score, never backfilled
        onto already-scored entries.

    Returns None if we can't compute cleanly.
    """
    outcome = status.get("outcome")
    if outcome is None:
        print(f"    [resolver] {market_id}: resolved but outcome unparseable "
              f"(raw='{status.get('raw_resolution')}')")
        return None

    scored = sorted(
        [p for p in predictions if p.get("conditional_p") is not None],
        key=lambda x: x.get("timestamp", "")
    )

    if not scored:
        print(f"    [resolver] {market_id}: no conditional_p in any prediction — skipping")
        return None

    anchor = scored[0]    # official — behavior unchanged from before this patch
    last   = scored[-1]   # informational only

    conditional_p = anchor["conditional_p"]
    engine_p      = anchor.get("engine_p")
    market_p      = anchor.get("market_p")

    last_p        = last["conditional_p"]
    market_p_last = last.get("market_p")

    # Official Brier scores (first-anchor — unchanged)
    brier_engine      = round((engine_p - outcome) ** 2, 6) if engine_p is not None else None
    brier_conditional = round((conditional_p - outcome) ** 2, 6)
    brier_market      = round((market_p - outcome) ** 2, 6) if market_p is not None else None

    # Informational last-anchor scores
    brier_last         = round((last_p - outcome) ** 2, 6)
    brier_market_last  = round((market_p_last - outcome) ** 2, 6) if market_p_last is not None else None
    brier_delta         = round(brier_last - brier_conditional, 6)

    return {
        "resolved_at":        datetime.now(timezone.utc).isoformat(),
        "market_id":          market_id,
        "market_label":       anchor.get("market_label"),
        "dyad":               anchor.get("dyad"),
        "first_prediction_ts": anchor.get("timestamp"),
        "last_prediction_ts": last.get("timestamp"),
        "outcome":            outcome,
        "resolution_raw":     status.get("raw_resolution"),
        # Prediction anchors (from first logged prediction — OFFICIAL)
        "conditional_p":      conditional_p,
        "engine_p":           engine_p,
        "market_p_at_first":  market_p,
        # Prediction anchors (first/last pair — for dual-Brier display)
        "first_p":            conditional_p,
        "last_p":             last_p,
        "delta_p":            round(last_p - conditional_p, 6),
        "market_p_last":      market_p_last,
        # Brier scores
        "brier_conditional":  brier_conditional,
        "brier_engine":       brier_engine,
        "brier_market":       brier_market,
        "brier_last":         brier_last,
        "brier_market_last":  brier_market_last,
        "brier_delta":        brier_delta,
        # Context
        "contract_type":      anchor.get("contract_type"),
        "relation":           anchor.get("relation_to_engine_event"),
        "translator_verdict": anchor.get("translator_verdict"),
        "n_predictions_logged": len(predictions),
    }


# ─────────────────────────────────────────────────────────────────────
# SUMMARY COMPUTATION
# ─────────────────────────────────────────────────────────────────────

def recompute_summary() -> dict:
    """Read full brier_log and compute running summary stats."""
    if not BRIER_LOG.exists():
        return {}

    entries = []
    with open(BRIER_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except Exception:
                continue

    if not entries:
        return {}

    cond_scores   = [e["brier_conditional"] for e in entries if e.get("brier_conditional") is not None]
    engine_scores = [e["brier_engine"]      for e in entries if e.get("brier_engine")      is not None]
    market_scores = [e["brier_market"]      for e in entries if e.get("brier_market")      is not None]

    def mean(lst):
        return round(sum(lst) / len(lst), 6) if lst else None

    n = len(entries)
    summary = {
        "last_updated":           datetime.now(timezone.utc).isoformat(),
        "n_resolved":             n,
        "brier_conditional_mean": mean(cond_scores),
        "brier_engine_mean":      mean(engine_scores),
        "brier_market_mean":      mean(market_scores),
        "edge_vs_market":         round(mean(market_scores) - mean(cond_scores), 6)
                                  if mean(market_scores) and mean(cond_scores) else None,
        "resolved_markets":       [
            {
                "market_id":    e["market_id"],
                "market_label": e["market_label"],
                "dyad":         e["dyad"],
                "outcome":      e["outcome"],
                "conditional_p": e["conditional_p"],
                "market_p":     e["market_p_at_first"],
                "brier_conditional": e["brier_conditional"],
                "brier_market": e["brier_market"],
                "resolved_at":  e["resolved_at"],
            }
            for e in sorted(entries, key=lambda x: x.get("resolved_at", ""))
        ]
    }
    return summary


# ─────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────

def run_resolver():
    print(f"\nResolver {'[DRY RUN] ' if DRY_RUN else ''}— {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 60)

    predictions = load_predictions()
    already_resolved = load_brier_log()

    print(f"  Tracked markets: {len(predictions)}")
    print(f"  Already resolved: {len(already_resolved)}")

    candidates = {
        mid: preds for mid, preds in predictions.items()
        if mid not in already_resolved
    }
    print(f"  Checking: {len(candidates)} markets\n")

    new_resolutions = []

    for market_id, preds in candidates.items():
        label = (preds[0].get("market_label") or "")[:50]
        print(f"  Checking [{market_id}] {label}")

        status = fetch_market_status(market_id)
        if status is None:
            print(f"    → API failure, skipping")
            continue

        if not status["resolved"]:
            print(f"    → Not yet resolved")
            continue

        print(f"    → RESOLVED: outcome={status['outcome']} "
              f"(raw='{status['raw_resolution']}')")

        # Sunset immediately once resolved -- independent of whether a Brier
        # entry can be computed. A market that resolved without ever being
        # scored must still stop being re-processed daily, and its real
        # outcome must still reach the site, even with no prediction.
        if not DRY_RUN:
            sunset_ok = sunset_market_in_feed(market_id, status["outcome"])
            if sunset_ok:
                print(f"    → Sunset: flagged resolved in classified_feed.json")
            else:
                print(f"    → Sunset: market not present in classified_feed.json (already cycled out)")

        entry = compute_brier_entry(market_id, preds, status)
        if entry is None:
            continue

        print(f"    → Brier: conditional={entry['brier_conditional']} "
              f"engine={entry['brier_engine']} market={entry['brier_market']}")

        new_resolutions.append(entry)

    print(f"\n{'='*60}")
    print(f"  New resolutions found: {len(new_resolutions)}")

    if not new_resolutions:
        print("  Nothing to write.")
        if not DRY_RUN:
            # Still recompute summary in case brier_log exists from before
            if BRIER_LOG.exists():
                summary = recompute_summary()
                BRIER_SUMMARY.write_text(json.dumps(summary, indent=2))
                print(f"  Summary refreshed → {BRIER_SUMMARY}")
        return

    if DRY_RUN:
        print("\n  [DRY RUN] Would write:")
        for e in new_resolutions:
            print(f"    {e['market_label'][:50]} | outcome={e['outcome']} "
                  f"| brier_cond={e['brier_conditional']}")
        return

    # Write to brier_log.jsonl
    BRIER_LOG.parent.mkdir(exist_ok=True)
    with open(BRIER_LOG, "a") as f:
        for entry in new_resolutions:
            f.write(json.dumps(entry) + "\n")
    print(f"  Appended {len(new_resolutions)} entries → {BRIER_LOG}")

    # Recompute and write summary
    summary = recompute_summary()
    BRIER_SUMMARY.write_text(json.dumps(summary, indent=2))
    print(f"  Summary updated → {BRIER_SUMMARY}")
    print(f"\n  Running Brier (conditional): {summary.get('brier_conditional_mean')}")
    print(f"  Running Brier (market):      {summary.get('brier_market_mean')}")
    print(f"  Edge vs market:              {summary.get('edge_vs_market')}")


if __name__ == "__main__":
    run_resolver()
