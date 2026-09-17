#!/usr/bin/env python3

from pipeline.action_readiness import score_action_readiness


def article(title, description=""):
    return {
        "title": title,
        "description": description,
        "publishedAt": "2026-09-17T12:00:00Z",
    }


def run(name, initiator, target, packet):
    result = score_action_readiness(
        initiator,
        target,
        packet,
    )

    nz = {
        k: round(v, 4)
        for k, v in result["live_scores"].items()
        if abs(v) > 1e-12
    }

    print(f"\n{name}")
    print(" signals:", result["signals"])
    print(" scores: ", nz or "{}")
    print(" summary:", result["summary"])
    return result


def all_zero(result):
    return all(
        abs(v) < 1e-12
        for v in result["live_scores"].values()
    )


# ============================================================
# 1. AIRSTRIKE vs MISSILE STRIKE
# ============================================================

r = run(
    "AIRSTRIKE NOT MISSILE",
    "State A",
    "State B",
    [
        article(
            "Strike aircraft loaded with precision bombs",
            "Combat aircraft were armed for attack while aerial tankers and "
            "electronic-warfare aircraft assembled into a strike package "
            "scheduled for departure."
        )
    ],
)

assert r["live_scores"]["airstrike"] > 0
assert r["live_scores"]["missile_strike"] == 0
assert r["live_scores"]["ground_invasion"] == 0


# ============================================================
# 2. RAID vs INVASION
# ============================================================

r = run(
    "RAID NOT INVASION",
    "State A",
    "State B",
    [
        article(
            "Special operations teams stage for overnight cross-border raid",
            "Helicopters and commandos assembled for a limited mission to "
            "destroy a radar site and withdraw before dawn. Orders specify "
            "that no territory is to be held."
        )
    ],
)

assert r["live_scores"]["raid"] > 0
assert r["live_scores"]["ground_invasion"] == 0


# ============================================================
# 3. SEIZURE vs BLOCKADE
# ============================================================

r = run(
    "SEIZURE NOT BLOCKADE",
    "State A",
    "State B",
    [
        article(
            "Boarding team ordered to seize single tanker",
            "Authorities ordered patrol vessels to intercept and board one "
            "named tanker. Other commercial traffic is not restricted."
        )
    ],
)

assert r["live_scores"]["seizure_boarding"] > 0
assert r["live_scores"]["naval_blockade"] == 0


# ============================================================
# 4. COMPLETED ACTION ALONE MUST NOT BECOME READINESS
# ============================================================

r = run(
    "COMPLETED STRIKE ONLY",
    "State A",
    "State B",
    [
        article(
            "Missiles struck military facility yesterday",
            "Officials confirmed that the attack ended overnight. No further "
            "launch preparations or follow-on operations were reported."
        )
    ],
)

assert all_zero(r)


# ============================================================
# 5. COMPLETED ACTION + CONCRETE FOLLOW-ON PREPARATION
#    SHOULD COUNT
# ============================================================

r = run(
    "FOLLOW-ON MISSILE PREPARATION",
    "State A",
    "State B",
    [
        article(
            "Additional missile units prepare follow-on salvo",
            "After yesterday's strike, additional mobile launchers dispersed "
            "into firing positions and crews began loading missiles for "
            "follow-on launches."
        )
    ],
)

assert r["live_scores"]["missile_strike"] > 0


# ============================================================
# 6. DUPLICATE NEWS MUST NOT DOUBLE COUNT
# ============================================================

r = run(
    "DUPLICATE REPORTING",
    "State A",
    "State B",
    [
        article(
            "Mobile missile launchers disperse to firing positions",
            "Several launch units left garrison and entered prepared firing sites."
        ),
        article(
            "Report: missile launchers seen leaving bases",
            "The same launcher movement was reported by a second outlet, "
            "describing units moving from garrison into prepared firing sites."
        ),
    ],
)

assert r["live_scores"]["missile_strike"] > 0

missile_signals = [
    x for x in r["signals"]
    if x.get("action_type") == "missile_strike"
]
assert len(missile_signals) == 1


# ============================================================
# 7. STAND-DOWN MUST REDUCE READINESS
# ============================================================

r = run(
    "INVASION STAND-DOWN",
    "State A",
    "State B",
    [
        article(
            "Amphibious force stands down",
            "Landing ships began unloading embarked troops and armored "
            "vehicles, assault formations returned to barracks, and the "
            "planned operation was cancelled."
        )
    ],
)

assert r["live_scores"]["ground_invasion"] < 0


# ============================================================
# 8. GENERIC MOBILIZATION MUST NOT BE SMEARED ACROSS ACTIONS
# ============================================================

r = run(
    "GENERIC MOBILIZATION",
    "State A",
    "State B",
    [
        article(
            "Military raises readiness level",
            "Reserve personnel were recalled and several units began moving, "
            "but officials gave no indication of an operational objective, "
            "target, weapon, or deployment pattern."
        )
    ],
)

assert all_zero(r)



# ============================================================
# 9. REGIONAL POSTURE MUST NOT BECOME TARGET-SPECIFIC READINESS
# ============================================================

r = run(
    "REGIONAL EXCLUSION NOT TARGETED",
    "Iran",
    "Saudi Arabia",
    [
        article(
            "Iran threatens maritime exclusion zone in Persian Gulf",
            "Iranian officials warned that foreign military traffic across "
            "parts of the Persian Gulf could be restricted. The statement "
            "did not identify Saudi Arabia, Saudi ports, Saudi vessels, or "
            "Saudi territory as objects of the restriction."
        )
    ],
)
assert all_zero(r)

print("\nACTION READINESS ADVERSARIAL: PASS")
