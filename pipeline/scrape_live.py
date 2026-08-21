"""
scrape_live.py (v3 — POST batch midpoints, correct API format)
"""

import requests
import json
import time
from datetime import datetime, timezone

# Reuses the already-proven, already-production-hardened deadline parser
# from translator.py (question-text-first, end_date as cross-check only —
# see _get_market_deadline's docstring for its own bug history). This is
# the same function translator.py's expiry gate and predict.py's Weibull
# horizon math already rely on; applying it here means the STORED end_date
# in classified_feed.json (and therefore the frontend display) stays
# consistent with what the scoring layer actually uses internally.
from pipeline.translator import _get_market_deadline

GAMMA = "https://gamma-api.polymarket.com"
CLOB  = "https://clob.polymarket.com"

CONFLICT_TAGS = [
    100265, 79, 502, 1346, 464, 193, 593, 863, 1308,
    334, 335, 415, 721, 97, 612, 103027, 102620, 471,
    101409, 100674, 103089, 101872, 102107, 582, 103074,
    96, 78, 180, 61, 303, 867, 95, 114, 738, 351, 102850, 297, 153,
]

def get_active_events_by_tag(tag_id):
    events = []
    offset = 0
    while True:
        try:
            resp = requests.get(f"{GAMMA}/events", params={
                "tag_id": tag_id, "active": "true", "closed": "false",
                "limit": 100, "offset": offset,
            }, timeout=30)
            data = resp.json()
            if not data:
                break
            events.extend(data)
            offset += 100
            if len(data) < 100:
                break
            time.sleep(0.1)
        except Exception as e:
            print(f"  [warn] tag {tag_id}: {e}")
            break
    return events


def batch_midpoints(token_ids):
    """POST /midpoints with array of {token_id} objects. Returns {token_id: float}."""
    if not token_ids:
        return {}
    try:
        payload = [{"token_id": tid} for tid in token_ids]
        resp = requests.post(
            f"{CLOB}/midpoints",
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=30,
        )
        data = resp.json()
        # Response is a flat dict: {token_id: "0.45", ...}
        if isinstance(data, dict) and "error" not in data:
            return {k: float(v) for k, v in data.items() if v is not None}
        else:
            print(f"  [warn] midpoints API returned: {str(data)[:120]}")
            return {}
    except Exception as e:
        print(f"  [warn] batch midpoints failed: {e}")
        return {}


def scrape_live_feed():
    # Step 1: collect unique active events
    print("Fetching active conflict events...")
    all_events = {}
    for tag_id in CONFLICT_TAGS:
        for e in get_active_events_by_tag(tag_id):
            eid = e.get("id")
            if eid and eid not in all_events:
                all_events[eid] = e
        print(f"  tag {tag_id:<8d} → {len(all_events)} unique events")
        time.sleep(0.1)

    print(f"\nTotal unique active conflict events: {len(all_events)}")

    # Step 2: extract all binary sub-markets
    print("\nExtracting sub-markets...")
    scraped_at = datetime.now(timezone.utc).isoformat()
    raw_markets = []

    for event in all_events.values():
        for m in event.get("markets", []):
            if m.get("closed") or m.get("resolved"):
                continue
            try:
                outcomes = json.loads(m["outcomes"]) if isinstance(m["outcomes"], str) else m["outcomes"]
                if set(outcomes) != {"Yes", "No"}:
                    continue
            except Exception:
                continue
            try:
                tokens = json.loads(m["clobTokenIds"]) if isinstance(m["clobTokenIds"], str) else m["clobTokenIds"]
                token_yes = tokens[0]
            except Exception:
                continue

            question_text = m.get("question", "") or m.get("groupItemTitle", "")
            raw_end_date  = (m.get("endDateIso") or m.get("endDate") or "")[:10]

            # Cross-check Gamma's raw end_date against question-text parsing.
            # If they disagree and question text parses cleanly, trust the
            # text (same rule already proven in translator.py/predict.py).
            # If nothing parses, keep the raw value unchanged -- no
            # regression for markets we genuinely can't independently verify.
            _deadline, _source, _mismatch = _get_market_deadline({
                "question":   question_text,
                "end_date":   raw_end_date,
                "scraped_at": scraped_at,
            })
            end_date_final = _deadline.isoformat() if _deadline else raw_end_date
            if _mismatch:
                print(f"    [SCRAPE_END_DATE_CORRECTED] {m.get('id','')}: "
                      f"Gamma said {raw_end_date}, question text said {end_date_final} — using question text")

            raw_markets.append({
                "event_title":    event.get("title", ""),
                "event_slug":     event.get("slug", ""),
                "question":       question_text,
                "market_id":      m.get("id", ""),
                "description":    m.get("description", "") or "",
                "resolution_source": m.get("resolutionSource", "") or "",
                "token_yes":      token_yes,
                "market_price":   None,
                "end_date":       end_date_final,
                "volume":         m.get("volumeNum", 0) or 0,
                "liquidity":      m.get("liquidityNum", 0) or 0,
                "scraped_at":     scraped_at,
                "bucket":         None,
                "bucket_reason":  None,
                "dyad":           None,
                "relevant_nodes": [],
                "our_prediction": None,
                "prediction_at":  None,
            })

    print(f"Found {len(raw_markets)} binary sub-markets. Fetching prices in batches...")

    # Step 3: POST batch midpoints, 100 at a time
    all_token_ids = [m["token_yes"] for m in raw_markets]
    price_map = {}
    batch_size = 100
    n_batches = (len(all_token_ids) - 1) // batch_size + 1

    for i in range(0, len(all_token_ids), batch_size):
        batch = all_token_ids[i:i+batch_size]
        prices = batch_midpoints(batch)
        price_map.update(prices)
        batch_num = i // batch_size + 1
        print(f"  Batch {batch_num}/{n_batches} — got {len(prices)}/{len(batch)} prices")
        time.sleep(0.2)

    # Step 4: attach prices
    for m in raw_markets:
        m["market_price"] = price_map.get(m["token_yes"])

    raw_markets.sort(key=lambda x: x["volume"], reverse=True)

    got_prices = sum(1 for m in raw_markets if m["market_price"] is not None)
    print(f"\nTotal live markets with prices: {got_prices}/{len(raw_markets)}")
    return raw_markets


if __name__ == "__main__":
    import os
    feed = scrape_live_feed()

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_feed.json")
    with open(out_path, "w") as f:
        json.dump(feed, f, indent=2, default=str)

    print(f"\nSaved {len(feed)} markets → {out_path}")
    print("\nTop 10 by volume:")
    for i, m in enumerate(feed[:10]):
        price_str = f"{m['market_price']*100:.1f}%" if m["market_price"] is not None else "?%"
        print(f"  {i+1:2d}. [{price_str}] {m['question'][:75]}")
        print(f"       Vol: ${m['volume']:,.0f} | Ends: {m['end_date']}")
