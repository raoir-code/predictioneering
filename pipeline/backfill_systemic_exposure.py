"""
One-time backfill: generate SystemicEconomicExposure, EconomicExposureInternalization,
and ThirdPartySanctionsRisk for every dyad already in dyad_configs.json that
predates these fields (2026-07-27). Same discipline as backfill_action_type.py --
a real Claude call per dyad using structural/geographic reasoning, not a
hardcoded table.

Deliberately does NOT pass crisis_context or label -- these are structural
judgments (is this dyad near a trade route / commodity hub / tourism economy;
would the likely initiator feel that damage; how exposed is the initiator to
international sanctions) that must stay independent of current-events framing,
same reasoning already established for action_type's backfill (crisis_context
was confirmed to corrupt structural judgments on 2026-07-23 -- truncation,
escalation-flavored bias, adversarial framing breaking JSON output).

Skips NON_BILATERAL dyads for the same reason action_type's backfill does.

Run: python3.11 pipeline/backfill_systemic_exposure.py
     python3.11 pipeline/backfill_systemic_exposure.py --dry-run
"""
import json
import os
import sys
import time
import requests
import shutil
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(__file__))
from dyad_registry import NON_BILATERAL

ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-opus-4-6"
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "dyad_configs.json")

SYSTEM_PROMPT = """You are an expert in international economics and conflict
analysis. Given a named dyad (pair of states), set three structural fields
capturing systemic/third-party economic costs of conflict -- a channel
distinct from ordinary bilateral trade interdependence between the two
states themselves.

- SystemicEconomicExposure (0.0 to 3.0): if conflict onset occurred for this
  dyad, how much economic disruption would it plausibly cause OUTSIDE the two
  belligerents themselves -- to global shipping/trade routes, concentrated
  commodity production, or tourism/services economies dependent on this
  region. Think broadly: a major shipping lane or strait, a globally-
  significant production hub (energy, minerals, semiconductors, agriculture),
  or a tourism-dependent regional economy in the blast radius.
  0.0 = essentially economically invisible to the rest of the world -- an
  isolated interior conflict with no trade route, no major production, no
  tourism exposure. THIS MUST SCORE NEAR ZERO for such cases -- do not
  inflate it just because a dyad sounds geopolitically serious. That is a
  deliberate falsification check: general salience is not economic exposure.
  3.0 = conflict here would meaningfully disrupt global commerce.

- EconomicExposureInternalization (0.0 to 1.0): of that broader disruption,
  how much would come back to hurt the LIKELY INITIATOR specifically -- via
  their own import dependence on the disrupted flow, their own export
  revenue from affected production, or pressure from allies/patrons who are
  themselves hurt. A country insulated from global trade (already heavily
  sanctioned, largely autarkic, or simply not dependent on the disrupted
  flow) should score LOW here even when SystemicEconomicExposure is high --
  the damage exists, but this specific actor barely feels it.

- ThirdPartySanctionsRisk (0.0 to 3.0): if this dyad's likely initiator
  committed significant aggression, how severe would internationally-
  coordinated economic punishment (sanctions, asset freezes, trade
  restrictions, diplomatic isolation) plausibly be? DIFFERENT mechanism from
  EconomicExposureInternalization above -- that is passive collateral damage;
  this is other countries DELIBERATELY punishing the initiator as a political
  response to the act itself (Russia 2022 is the reference case: minimal
  self-exposure to shipping disruption, but severe coordinated sanctions
  purely because it invaded). Consider: how normatively transgressive the
  action would be perceived as, how economically enmeshed the likely
  initiator is with states/blocs likely to sanction, and whether a shielding
  patron (e.g. a UNSC veto-holder) would blunt a coordinated response.

Be theoretically conservative -- reserve values above 2.0 for genuinely
extreme, unambiguous cases (a dyad literally adjacent to a top-tier global
shipping chokepoint; a dyad where the likely initiator is a G7/EU-aligned
state with deep exposure to Western-led sanctions coalitions).

Respond ONLY with valid JSON:
{"SystemicEconomicExposure": 0.0, "EconomicExposureInternalization": 0.0,
 "ThirdPartySanctionsRisk": 0.0, "reasoning": "one to two sentences naming
 the specific trade route/commodity/tourism dependency (or explicitly noting
 there is none) and the sanctions-exposure logic"}
"""


def classify_dyad(dyad_name):
    payload = {
        "model": MODEL,
        "max_tokens": 400,
        "system": SYSTEM_PROMPT,
        "messages": [{"role": "user", "content": f"Classify this dyad: {dyad_name}."}],
    }
    resp = requests.post(
        ANTHROPIC_API,
        headers={
            "Content-Type": "application/json",
            "x-api-key": os.environ["ANTHROPIC_API_KEY"],
            "anthropic-version": "2023-06-01",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    text = resp.json()["content"][0]["text"].strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        if text.startswith("json"):
            text = text[4:]
    return json.loads(text.strip())


def main():
    dry_run = "--dry-run" in sys.argv

    with open(CONFIG_PATH) as f:
        configs = json.load(f)

    targets = [
        k for k in configs
        if k not in NON_BILATERAL and "SystemicEconomicExposure" not in configs[k].get("baseline", {})
    ]

    print(f"{len(targets)} dyads need systemic-exposure backfill (of {len(configs)} total)\n")
    if dry_run:
        print("[DRY RUN] Will not write changes.\n")

    if not dry_run and targets:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        bak_path = f"{CONFIG_PATH}.bak.{stamp}"
        shutil.copy2(CONFIG_PATH, bak_path)
        print(f"backed up -> {bak_path}\n")

    results = {}
    errors = []
    zero_exposure_count = 0
    for i, dyad in enumerate(targets):
        try:
            result = classify_dyad(dyad)
            exposure = result.get("SystemicEconomicExposure")
            internalization = result.get("EconomicExposureInternalization")
            sanctions = result.get("ThirdPartySanctionsRisk")
            reasoning = result.get("reasoning", "")

            if not all(isinstance(v, (int, float)) for v in (exposure, internalization, sanctions)):
                errors.append(f"{dyad}: non-numeric field(s) returned: {result}")
                print(f"  {i+1:2}/{len(targets)}. ⚠️  {dyad}: INVALID VALUES -- skipped")
                continue

            results[dyad] = (exposure, internalization, sanctions, reasoning)
            if exposure == 0.0:
                zero_exposure_count += 1
            print(f"  {i+1:2}/{len(targets)}. {dyad:30} -> exposure={exposure} "
                  f"internalization={internalization} sanctions={sanctions} "
                  f"({reasoning[:60]})")

            if not dry_run:
                configs[dyad]["baseline"]["SystemicEconomicExposure"] = exposure
                configs[dyad]["baseline"]["EconomicExposureInternalization"] = internalization
                configs[dyad]["baseline"]["ThirdPartySanctionsRisk"] = sanctions

        except Exception as e:
            errors.append(f"{dyad}: {e}")
            print(f"  {i+1:2}/{len(targets)}. ❌ {dyad}: ERROR -- {e}")

        time.sleep(0.3)

    print(f"\n{zero_exposure_count}/{len(results)} dyads scored SystemicEconomicExposure=0.0 "
          f"(the falsification case -- sanity-check a few of these manually before trusting the batch)")

    if not dry_run and results:
        with open(CONFIG_PATH, "w") as f:
            json.dump(configs, f, indent=2, ensure_ascii=False)
            f.write("\n")
        print(f"\nWrote {len(results)} systemic-exposure baselines to {CONFIG_PATH}")

    if errors:
        print(f"\n{len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")


if __name__ == "__main__":
    main()
