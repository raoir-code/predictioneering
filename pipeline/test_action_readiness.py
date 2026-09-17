#!/usr/bin/env python3

import argparse

from pipeline.action_readiness import (
    STRENGTH_TO_LOG_SCORE,
    score_action_readiness,
    signals_to_live_scores,
    zero_live_scores,
)
from pipeline.action_selector import (
    ACTION_TYPES,
    select_distribution,
)


def article(title, description=""):
    return {
        "title": title,
        "description": description,
        "publishedAt": "2026-09-17T12:00:00Z",
    }


def deterministic_tests():
    # --------------------------------------------------------
    # 1. Zero evidence == exact structural prior.
    # --------------------------------------------------------
    prior = {
        "gray_zone_incident": 0.20,
        "missile_strike": 0.30,
        "raid": 0.10,
        "seizure_boarding": 0.05,
        "airstrike": 0.15,
        "naval_blockade": 0.05,
        "ground_invasion": 0.10,
        "direct_engagement": 0.05,
    }

    zero = zero_live_scores()

    out = select_distribution(
        prior,
        live_scores=zero,
    )

    for action in ACTION_TYPES:
        assert abs(out[action] - prior[action]) < 1e-12

    # --------------------------------------------------------
    # 2. Semantic labels become deterministic log multipliers.
    # --------------------------------------------------------
    scores = signals_to_live_scores([
        {
            "action_type": "missile_strike",
            "direction": "up",
            "strength": "moderate",
            "evidence": "launchers dispersed",
        },
        {
            "action_type": "ground_invasion",
            "direction": "down",
            "strength": "weak",
            "evidence": "assault force returned to garrison",
        },
    ])

    assert abs(
        scores["missile_strike"]
        - STRENGTH_TO_LOG_SCORE["moderate"]
    ) < 1e-12

    assert abs(
        scores["ground_invasion"]
        + STRENGTH_TO_LOG_SCORE["weak"]
    ) < 1e-12

    for action in ACTION_TYPES:
        if action not in {"missile_strike", "ground_invasion"}:
            assert scores[action] == 0.0

    # --------------------------------------------------------
    # 3. Missile evidence redistributes conditional action mix.
    # --------------------------------------------------------
    missile_only = signals_to_live_scores([
        {
            "action_type": "missile_strike",
            "direction": "up",
            "strength": "strong",
            "evidence": "TELs in firing positions",
        }
    ])

    shifted = select_distribution(
        prior,
        live_scores=missile_only,
    )

    assert shifted["missile_strike"] > prior["missile_strike"]
    assert abs(sum(shifted.values()) - 1.0) < 1e-12

    # This layer remains a conditional distribution only.
    assert set(shifted) == set(ACTION_TYPES)

    # --------------------------------------------------------
    # 4. Duplicate action evidence is rejected rather than
    #    silently double-counted.
    # --------------------------------------------------------
    duplicate = [
        {
            "action_type": "missile_strike",
            "direction": "up",
            "strength": "weak",
            "evidence": "A",
        },
        {
            "action_type": "missile_strike",
            "direction": "up",
            "strength": "strong",
            "evidence": "same underlying event repeated",
        },
    ]

    try:
        signals_to_live_scores(duplicate)
    except ValueError:
        pass
    else:
        raise AssertionError("duplicate action evidence was accepted")

    print("ACTION READINESS DETERMINISTIC: PASS")


def run_fixture(name, initiator, target, packet):
    result = score_action_readiness(
        initiator,
        target,
        packet,
    )

    nonzero = {
        k: round(v, 4)
        for k, v in result["live_scores"].items()
        if abs(v) > 1e-12
    }

    print(f"\n{name}")
    print(" signals:", result["signals"])
    print(" scores: ", nonzero or "{}")
    print(" summary:", result["summary"])

    return result


def live_tests():
    # 1. Generic hostility must do nothing.
    quiet = run_fixture(
        "GENERIC HOSTILITY",
        "Iran",
        "Jordan",
        [
            article(
                "Iran warns Jordan against hostile policies",
                "Officials traded accusations as regional tensions remained high."
            )
        ],
    )
    assert all(
        abs(x) < 1e-12
        for x in quiet["live_scores"].values()
    )

    # 2. Missile preparation -> missile only.
    missile = run_fixture(
        "MISSILE PREPARATION",
        "Iran",
        "Jordan",
        [
            article(
                "Iran disperses ballistic missile launchers",
                "Missile units were placed on launch alert and mobile launchers "
                "moved into prepared firing positions."
            )
        ],
    )
    assert missile["live_scores"]["missile_strike"] > 0
    assert missile["live_scores"]["direct_engagement"] == 0
    assert missile["live_scores"]["ground_invasion"] == 0

    # 3. Amphibious preparation -> invasion.
    invasion = run_fixture(
        "AMPHIBIOUS PREPARATION",
        "China",
        "Taiwan",
        [
            article(
                "PLA landing ships load troops and armored vehicles",
                "Amphibious formations assembled at embarkation ports and "
                "landing craft began loading assault units."
            )
        ],
    )
    assert invasion["live_scores"]["ground_invasion"] > 0

    # 4. Direct opposing-force contact -> direct engagement.
    contact = run_fixture(
        "DIRECT FORCE CONTACT",
        "Turkey",
        "Greece",
        [
            article(
                "Turkish fighters vectored toward Greek jets over Aegean",
                "The opposing fighters maneuvered within weapons range and "
                "activated fire-control radars."
            )
        ],
    )
    assert contact["live_scores"]["direct_engagement"] > 0

    # 5. Target defense alone must not become initiator engagement.
    defense = run_fixture(
        "TARGET DEFENSE ONLY",
        "Iran",
        "Jordan",
        [
            article(
                "Jordan activates air defenses amid warnings of possible attack",
                "Jordanian fighters scrambled and air-defense batteries went "
                "on alert over concerns about possible Iranian missiles."
            )
        ],
    )
    assert defense["live_scores"]["direct_engagement"] == 0
    assert all(
        abs(x) < 1e-12
        for x in defense["live_scores"].values()
    )

    # 6. Blockade-specific deployment -> blockade.
    blockade = run_fixture(
        "BLOCKADE PREPARATION",
        "China",
        "Taiwan",
        [
            article(
                "Chinese naval and coast guard ships form cordon around Taiwan ports",
                "Authorities announced compulsory inspections while ships took "
                "positions intended to restrict commercial traffic."
            )
        ],
    )
    assert blockade["live_scores"]["naval_blockade"] > 0

    print("\nACTION READINESS LIVE SEMANTICS: PASS")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Also run Claude semantic acceptance fixtures.",
    )
    args = parser.parse_args()

    deterministic_tests()

    if args.live:
        live_tests()


if __name__ == "__main__":
    main()
