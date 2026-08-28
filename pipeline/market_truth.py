"""
pipeline/market_truth.py — TRUE market prices at posting/resolution,
pulled directly from Polymarket's own price-history API.

Replaces market_p / market_p_last as the source for published Market
Brier scores. Root cause (Aug 28): those fields were frozen at whatever
classified_feed.json held at the last weekly disciplinarian.py run, not
a live or concluding price. This module queries Polymarket's own
history instead, anchored on two real timestamps we already have:
first_prediction_ts (posting) and the resolution detection time.

This only fetches third-party market data -- never touches our own
conditional_p / brier_conditional -- so backfilling it onto already-
resolved markets does not violate the never-backfill-our-own-
predictions rule.
"""

import json
import time
import datetime
import requests

CLOB  = "https://clob.polymarket.com"
GAMMA = "https://gamma-api.polymarket.com"


def _to_epoch(iso: str) -> int:
    return int(datetime.datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp())


def _nearest(history, target_epoch):
    if not history:
        return None
    return min(history, key=lambda pt: abs(pt["t"] - target_epoch))


def _query_history(token, start_ts, end_ts, fidelity=10, retries=2):
    """Single prices-history call with basic retry. 400 (window too long)
    is not retried -- retrying won't change a structural rejection."""
    for attempt in range(retries + 1):
        try:
            r = requests.get(f"{CLOB}/prices-history", params={
                "market": token, "startTs": start_ts, "endTs": end_ts, "fidelity": fidelity,
            }, timeout=15)
            if r.status_code == 200:
                return r.json().get("history", [])
            if r.status_code == 400:
                return []
        except requests.RequestException:
            pass
        time.sleep(1.5 * (attempt + 1))
    return []


def fetch_token_for_market(market_id, local_lookup=None):
    """market_id -> CLOB token_yes. Local classified_feed.json lookup first
    (free, no network), Gamma API by id as fallback for aged-out markets."""
    if local_lookup and str(market_id) in local_lookup and local_lookup[str(market_id)]:
        return local_lookup[str(market_id)]
    try:
        r = requests.get(f"{GAMMA}/markets/{market_id}", timeout=15)
        if r.status_code == 200:
            m = r.json()
            tokens = m.get("clobTokenIds")
            tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
            if tokens:
                return tokens[0]
    except requests.RequestException:
        pass
    return None


def fetch_true_prices(token, first_prediction_ts, resolved_ts):
    """
    Returns:
      {"true_first_p": float|None, "true_first_t": iso|None,
       "true_last_p":  float|None, "true_last_t":  iso|None,
       "ok": bool}
    true_first_p = nearest history point to first_prediction_ts (±1d window)
    true_last_p  = last history point before resolved_ts (3d lookback)
    fidelity=10min keeps both windows well under the API's ~2-week span cap,
    regardless of how long the market's full life was.
    """
    assert token, "fetch_true_prices called with empty token"
    first_epoch = _to_epoch(first_prediction_ts)
    resolved_epoch = _to_epoch(resolved_ts)

    h1 = _query_history(token, first_epoch - 86400, first_epoch + 86400)
    p1 = _nearest(h1, first_epoch)
    time.sleep(0.5)

    h2 = _query_history(token, resolved_epoch - 3 * 86400, resolved_epoch + 3600)
    p2 = h2[-1] if h2 else None
    time.sleep(0.5)

    return {
        "true_first_p": p1["p"] if p1 else None,
        "true_first_t": datetime.datetime.utcfromtimestamp(p1["t"]).isoformat() if p1 else None,
        "true_last_p":  p2["p"] if p2 else None,
        "true_last_t":  datetime.datetime.utcfromtimestamp(p2["t"]).isoformat() if p2 else None,
        "ok": p1 is not None and p2 is not None,
    }
