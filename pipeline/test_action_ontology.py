"""
Action-ontology regression test for direct_engagement (added 2026-09-16).

STATUS: partial reconstruction, not the original Sept 11 40-case test.

The original 40-case test (built 2026-09-11) is not reproducible from this
repo -- it ran in a ChatGPT session against a standalone mock classifier
(a direct API call with its own separate prompt), NOT the real
disciplinarian.py/translator.py clergyman() pipeline. Its 36/40 result
measured whether a 7-category taxonomy plus a mock prompt were internally
coherent -- it never exercised the production code path.

The 8 cases below were identified via ChatGPT's account of that session
(case IDs, scenario text, reasoning) -- treat as reliable secondhand report,
not a verified verbatim artifact -- and independently confirmed here against
the REAL clergyman() function with live API calls on 2026-09-16, after
adding the direct_engagement category. This is a stronger result than the
original test in one respect (real production code, not a mock) and weaker
in another (8 of 40 cases, not all 40 -- the other ~32 passing cases'
verbatim text was not recovered).

7 cases should return direct_engagement:
  C04, C11, C16, C17, C32, C33, C34
1 case is a negative control -- must NOT return direct_engagement
(reconstructed scenario, original C31 text unrecovered):
  C31-reconstructed (standalone mine-laying)

KNOWN OPEN FINDING from this run: the real production schema has no
NO_CLEAN_FIT escape valve -- Clergyman must choose among the 8 defined
categories (or null, for non-physical/political acts only). On the
mine-laying negative control, it fell back to gray_zone_incident rather
than refusing to classify. Worth a backlog item (a genuine "does not fit"
outcome, or explicit acceptance that gray_zone_incident is the correct
doctrinal fallback for standalone covert/indirect actions) -- not fixed
here, flagged so it isn't silently lost.

TODO: get the full verbatim 40-case list + original harness from ChatGPT
if recoverable, and extend this file to cover all 40 through the real
pipeline. Deliberately partial until then.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipeline.translator import clergyman


# (case_id, dyad, question, description, win_condition_summary, expected_set)
CASES = [
    ("C04", "China-Philippines",
     "Will a Chinese fighter deliberately shoot down a Philippine military aircraft?",
     "Resolves YES if a Chinese fighter deliberately shoots down a Philippine military aircraft in an air-to-air engagement.",
     "Chinese fighter shoots down Philippine aircraft in air-to-air engagement.",
     {"direct_engagement"}),

    ("C11", "Thailand-Cambodia",
     "Will Thai and Cambodian army units exchange artillery and direct fire across their border without crossing it?",
     "Resolves YES if Thai and Cambodian army units deliberately exchange artillery and direct fire across their border, with neither side crossing it.",
     "Thai and Cambodian forces exchange cross-border fire, no territorial crossing.",
     {"direct_engagement"}),

    ("C16", "Turkey-Greece",
     "Will a Turkish fighter jet deliberately shoot down a Greek fighter jet?",
     "Resolves YES if a Turkish military aircraft deliberately shoots down a Greek military aircraft.",
     "Turkish fighter shoots down Greek fighter.",
     {"direct_engagement"}),

    ("C17", "Turkey-Greece",
     "Will Turkish and Greek naval vessels exchange naval gunfire?",
     "Resolves YES if Turkish and Greek naval vessels already in contact exchange gunfire.",
     "Turkish and Greek ships exchange naval-gun fire.",
     {"direct_engagement"}),

    ("C32", "US-Iran",
     "Will Iranian air defenses deliberately shoot down a U.S. military aircraft flying over Iran?",
     "Resolves YES if Iranian air defenses deliberately shoot down a U.S. military aircraft flying over Iran.",
     "Iranian air defenses shoot down US aircraft over Iran.",
     {"direct_engagement"}),

    ("C33", "Thailand-Cambodia",
     "Will Cambodian artillery shell a Thai military base across the border?",
     "Resolves YES if Cambodian artillery units fire across the border and shell a Thai military base.",
     "Cambodian artillery shells Thai base across border.",
     {"direct_engagement"}),

    ("C34", "North Korea-South Korea",
     "Will North Korean and South Korean forces exchange fire across the DMZ this month?",
     "Resolves YES if forces on either side of the DMZ engage in a direct firefight this month.",
     "DMZ forces on both sides exchange fire.",
     {"direct_engagement"}),

    ("C31-reconstructed", "Iran-UAE",
     "Will Iran lay naval mines in international waters near the UAE coast?",
     "Resolves YES if Iran lays naval mines in international or contested waters near the UAE coast, absent any broader military operation.",
     "Iran lays naval mines near UAE waters, standalone action.",
     {"gray_zone_incident", "seizure_boarding"}),  # must NOT be direct_engagement
]


def run():
    passes = 0
    fails = []
    print("=== ACTION ONTOLOGY REGRESSION (direct_engagement, partial 8/40) ===\n")

    for case_id, dyad, question, description, win_cond, expected in CASES:
        market = {"question": question, "description": description, "_toggles": {}}
        scholar = {
            "relation_to_engine_event": "subset",
            "win_condition_summary": win_cond,
            "legalese_flags": [],
        }
        try:
            out = clergyman(market, dyad, scholar)
            got = out.get("action_type") if out else None
            ok = got in expected
        except Exception as exc:
            got = f"ERROR: {exc}"
            ok = False

        print(f"{case_id} {'PASS' if ok else 'FAIL'}  dyad={dyad}")
        print(f"  Q:    {question}")
        print(f"  GOT:  {got}")
        print(f"  WANT: {' or '.join(sorted(expected))}\n")

        if ok:
            passes += 1
        else:
            fails.append((case_id, got, expected))

    print("=" * 72)
    print(f"RESULT: {passes}/{len(CASES)} pass")
    if fails:
        print("\nFAILURES:")
        for case_id, got, expected in fails:
            print(f"  {case_id}: got={got!r} want={sorted(expected)}")
    return passes, len(CASES), fails


if __name__ == "__main__":
    run()
