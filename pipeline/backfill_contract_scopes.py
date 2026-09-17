#!/usr/bin/env python3
"""
Backfill semantic contract scope for active physical-action markets.

This does NOT forecast.

It converts market legalese + Translator direction into structural metadata:
- singular actor vs union vs collective actor;
- operational geography;
- downstream routing requirement.

Output:
    pipeline/contract_scopes.json
"""

import argparse
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from pipeline.contract_scope import (
    resolve_contract_scope,
    action_prior_fingerprint,
)


ROOT = Path(__file__).resolve().parent
CLASSIFIED_FEED = ROOT / "classified_feed.json"
TRANSLATOR_CACHE = ROOT / "translator_cache.json"
SCOPE_CACHE = ROOT / "contract_scopes.json"


def parse_date(value):
    if not value:
        return None

    text = str(value)

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except Exception:
        pass

    try:
        return datetime.strptime(
            text[:10],
            "%Y-%m-%d",
        ).date()
    except Exception:
        return None


def source_signature(
    initiator,
    target,
    question,
    description,
):
    payload = {
        "initiator": initiator,
        "target": target,
        "question": question or "",
        "description": description or "",
    }

    canonical = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()


def route_scope(scope):
    if not scope.get("direction_compatible"):
        return "fail_closed_direction"

    i_mode = scope["initiator_scope"]["mode"]
    t_mode = scope["target_scope"]["mode"]

    modes = {i_mode, t_mode}

    if "undefined_union" in modes:
        return "fail_closed_undefined_union"

    if (
        "enumerable_union" in modes
        or "named_group_union" in modes
    ):
        return "agglomeration_required"

    if "collective_actor" in modes:
        return "collective_actor"

    if (
        i_mode == "single_actor"
        and t_mode == "single_actor"
    ):
        return "scoped_bilateral"

    return "fail_closed_unsupported"


def load_json(path, default):
    if not path.exists():
        return default

    return json.loads(path.read_text())


def save_cache(data):
    tmp = SCOPE_CACHE.with_suffix(".json.tmp")

    tmp.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )

    tmp.replace(SCOPE_CACHE)


def active_physical_contracts():
    feed = load_json(CLASSIFIED_FEED, [])
    translator = load_json(TRANSLATOR_CACHE, {})

    rows = (
        feed
        if isinstance(feed, list)
        else feed.get(
            "markets",
            feed.get("data", []),
        )
    )

    today = date.today()
    out = []

    for market in rows:
        if not isinstance(market, dict):
            continue

        if market.get("bucket") != "CORE":
            continue

        end = parse_date(market.get("end_date"))

        if end is not None and end < today:
            continue

        market_id = market.get("market_id")

        if market_id is None:
            continue

        cached = translator.get(str(market_id))

        if not isinstance(cached, dict):
            continue

        clergy = cached.get("clergy")

        if not isinstance(clergy, dict):
            continue

        if (
            clergy.get("manifestation_family")
            != "kinetic_or_coercive_action"
        ):
            continue

        initiator = clergy.get("contract_initiator")
        target = clergy.get("contract_target")

        if not initiator or not target:
            continue

        if initiator == target:
            continue

        out.append({
            "market_id": str(market_id),
            "dyad": market.get("dyad"),
            "question": market.get("question") or "",
            "description": market.get("description") or "",
            "end_date": market.get("end_date"),
            "action_type": clergy.get("action_type"),
            "initiator": initiator,
            "target": target,
        })

    return out


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-resolve scopes even when source text is unchanged.",
    )

    parser.add_argument(
        "--limit",
        type=int,
        help="Resolve at most N contracts.",
    )

    args = parser.parse_args()

    markets = active_physical_contracts()

    if args.limit is not None:
        markets = markets[:args.limit]

    cache = load_json(SCOPE_CACHE, {})

    print(
        f"{len(markets)} active translated physical "
        f"contract(s) selected."
    )

    resolved = 0
    reused = 0
    failed = 0

    for i, market in enumerate(markets, 1):
        market_id = market["market_id"]

        sig = source_signature(
            market["initiator"],
            market["target"],
            market["question"],
            market["description"],
        )

        existing = cache.get(market_id)

        if (
            not args.force
            and isinstance(existing, dict)
            and existing.get("source_signature") == sig
        ):
            scope = existing["scope"]
            route = existing["route"]
            reused += 1

            print(
                f"{i:3}/{len(markets)} "
                f"{market['initiator']} -> "
                f"{market['target']} "
                f"| {route} | REUSED"
            )
            continue

        try:
            scope = resolve_contract_scope(
                initiator=market["initiator"],
                target=market["target"],
                question=market["question"],
                description=market["description"],
            )

            scope["action_prior_fingerprint"] = (
                action_prior_fingerprint(scope)
            )

            route = route_scope(scope)

            cache[market_id] = {
                "market_id": market_id,
                "dyad": market["dyad"],
                "question": market["question"],
                "end_date": market["end_date"],
                "action_type": market["action_type"],
                "initiator": market["initiator"],
                "target": market["target"],
                "source_signature": sig,
                "scope": scope,
                "route": route,
                "version": 1,
            }

            save_cache(cache)
            resolved += 1

            geo = scope["geography"]

            print(
                f"{i:3}/{len(markets)} "
                f"{market['initiator']} -> "
                f"{market['target']} "
                f"| {route}"
            )
            print(
                f"    action={market['action_type']} "
                f"| geo={geo['mode']}:{geo['places']} "
                f"| fp={scope['scope_fingerprint']}"
            )

        except Exception as exc:
            failed += 1

            print(
                f"{i:3}/{len(markets)} "
                f"{market['initiator']} -> "
                f"{market['target']} "
                f"| ERROR: {exc}"
            )

    print("\nSUMMARY")
    print(" resolved:", resolved)
    print(" reused:  ", reused)
    print(" failed:  ", failed)

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
