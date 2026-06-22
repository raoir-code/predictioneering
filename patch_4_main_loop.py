#!/usr/bin/env python3.11
"""
Patch 4 — wire the main run_backtest() snapshot loop over to the two-call
structure, compute q_components/q_full/q_onset_only/q_live_only per
snapshot, and log them into backtest_results.json. The Mach 2 engine_p
formula itself is left completely untouched — q-submodel output is
diagnostic-only this run, not yet feeding the scored prediction.
Requires Patch 2 applied first.

Run from repo root: python3.11 patch_4_main_loop.py
"""
from pathlib import Path

path = Path("pipeline/backtest.py")
content = path.read_text()

old = r'''
        baseline = load_dyad_baseline(dyad)

        print(f"  Sub-market: {sm['label']} | Resolution: {resolution} | "
              f"History: {len(sm['history'])} days")

        # 2. Run snapshots
        for offset in SNAPSHOT_OFFSETS:
            snapshot_date = end_date - timedelta(days=offset)

            # Skip future snapshots for resolved markets
            if snapshot_date > date.today():
                continue

            # Get contemporaneous market price
            mkt_price = get_market_price_at(sm["history"], snapshot_date)
            if mkt_price is None:
                continue

            days_remaining = (end_date - snapshot_date).days

            # Fetch headlines + score nodes
            articles = fetch_gnews(dyad, snapshot_date)
            deltas   = score_nodes(dyad, articles, snapshot_date)
            toggles  = apply_deltas(baseline, deltas)

            # Run Mach 2
            engine_p = predict_probability(toggles, days_remaining)

            # Brier scores (only for resolved markets)
            b_engine = (engine_p - resolution)**2 if resolution is not None else None
            b_market = (mkt_price - resolution)**2 if resolution is not None else None

            row = {
                "market":        mkt["label"],
                "dyad":          dyad,
                "snapshot_date": snapshot_date.isoformat(),
                "days_remaining":days_remaining,
                "resolution":    resolution,
                "engine_p":      engine_p,
                "market_p":      mkt_price,
                "b_engine":      b_engine,
                "b_market":      b_market,
                "n_articles":    len(articles),
            }
            rows.append(row)
'''

new = r'''
        baseline = load_dyad_baseline(dyad)
        q_static = load_dyad_q_static(dyad)

        print(f"  Sub-market: {sm['label']} | Resolution: {resolution} | "
              f"History: {len(sm['history'])} days")

        # 2. Run snapshots
        for offset in SNAPSHOT_OFFSETS:
            snapshot_date = end_date - timedelta(days=offset)

            # Skip future snapshots for resolved markets
            if snapshot_date > date.today():
                continue

            # Get contemporaneous market price
            mkt_price = get_market_price_at(sm["history"], snapshot_date)
            if mkt_price is None:
                continue

            days_remaining = (end_date - snapshot_date).days

            # Fetch headlines + score nodes (two-call structure, June 17 spec)
            articles = fetch_gnews(dyad, snapshot_date)
            call_a   = score_nodes_call_a(dyad, articles, snapshot_date)
            trigger_was_violent = call_a.get("TriggerType", 0.0) >= 0.60
            call_b   = score_nodes_call_b(dyad, articles, snapshot_date, trigger_was_violent)

            toggles  = apply_deltas(baseline, call_a)  # only NODES keys get applied; new fields ignored here

            # Run Mach 2 (unchanged formula — q-submodel is diagnostic-only this run)
            engine_p = predict_probability(toggles, days_remaining)

            # Q-submodel: compute logit(q) decomposition for this snapshot
            q_components = build_q_components(toggles, call_a, call_b, q_static)
            q_full        = q_with_subset(q_components)
            q_onset_only  = q_with_subset(q_components, ONSET_ONLY_KEYS)
            q_live_only   = q_with_subset(q_components, LIVE_ONLY_KEYS)

            # Brier scores (only for resolved markets)
            b_engine = (engine_p - resolution)**2 if resolution is not None else None
            b_market = (mkt_price - resolution)**2 if resolution is not None else None

            row = {
                "market":        mkt["label"],
                "dyad":          dyad,
                "snapshot_date": snapshot_date.isoformat(),
                "days_remaining":days_remaining,
                "resolution":    resolution,
                "engine_p":      engine_p,
                "market_p":      mkt_price,
                "b_engine":      b_engine,
                "b_market":      b_market,
                "n_articles":    len(articles),
                "q_components":  q_components,
                "q_full":        round(q_full, 4),
                "q_onset_only":  round(q_onset_only, 4),
                "q_live_only":   round(q_live_only, 4),
            }
            rows.append(row)
'''

assert old in content, "OLD BLOCK NOT FOUND — aborting, no changes made. Run patches in order (1,2,3,4) and only once each."
assert content.count(old) == 1, "OLD BLOCK NOT UNIQUE — aborting, refusing to guess which occurrence to replace"

content = content.replace(old, new)
path.write_text(content)
print("Patch 4 applied — main loop now logs q_components/q_full/q_onset_only/q_live_only per snapshot.")
