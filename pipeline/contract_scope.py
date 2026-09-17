#!/usr/bin/env python3
"""
Contract-scope semantics for physical geopolitical markets.

Purpose
-------
Separate WHO can satisfy a contract and WHERE it must occur from:

- the canonical dyad used by the conflict engine;
- the action family;
- the forecast probability.

This module does NOT forecast.

It resolves contract semantics into reusable structural metadata.

Examples
--------
"US invades Greenland"
    initiator = single_actor(US)
    target    = single_actor(Denmark)
    geography = subterritory(Greenland)

"Any European country strikes Iran"
    initiator = enumerable_union([...])
    target    = single_actor(Iran)

"Russia invades a NATO country"
    initiator = single_actor(Russia)
    target    = named_group_union(NATO)

"NATO/EU troops fighting Russia in Ukraine"
    initiator = named_group_union(NATO, EU)
    target    = single_actor(Russia)
    geography = third_party_theater(Ukraine)
"""

import hashlib
import json
import os
import time
from typing import Any

import requests


ANTHROPIC_API = "https://api.anthropic.com/v1/messages"
MODEL = "claude-sonnet-4-6"


PARTY_MODES = {
    "single_actor",
    "enumerable_union",
    "named_group_union",
    "collective_actor",
    "undefined_union",
}

ENTITY_TYPES = {
    "state",
    "nonstate_actor",
    "intergovernmental_org",
    "coalition",
    "mixed",
    "unknown",
}

GEOGRAPHY_MODES = {
    "target_wide",
    "subterritory",
    "third_party_theater",
    "multiple",
    "unspecified",
}

GEOGRAPHY_PRIOR_RELEVANCE = {
    "structural_theater",
    "resolution_only",
}


SYSTEM_PROMPT = """
You resolve the semantic SCOPE of prediction-market contracts.

You are NOT forecasting.
Do not estimate probabilities.
Do not assess likelihood.
Do not use current news.
Do not add actors or locations that are not required by the contract.

The forecasting engine needs to know:

1. WHO may perform the qualifying action;
2. WHO/WHAT is the counterparty or target;
3. WHERE the qualifying physical action must occur.

PARTY MODES

single_actor
    Exactly one actor satisfies this side of the contract.

enumerable_union
    The contract explicitly enumerates a bounded list of actors and ANY ONE
    member may satisfy the contract.

named_group_union
    The contract refers to ANY MEMBER of a named organization/group/class,
    but does not itself provide the full member list.
    Examples: "any NATO country", "any EU member".

collective_actor
    The organization/coalition itself must act as a collective entity.
    Example: "NATO launches an operation" where action by an individual
    NATO member alone would not suffice.

undefined_union
    The contract permits an open-ended or undefined set such as "any country"
    with no bounded list or named membership rule.

IMPORTANT:
"any NATO country" is named_group_union, NOT collective_actor.
"NATO conducts an operation" can be collective_actor.

ENTITY TYPES

state
nonstate_actor
intergovernmental_org
coalition
mixed
unknown

GEOGRAPHY MODES

Also classify geography.prior_relevance:

structural_theater
    The named location defines a genuinely different operational theater or
    geographic target and could change the relative feasibility of MULTIPLE
    action families. Examples: Greenland rather than Denmark proper; Greater
    Beirut rather than Lebanon generally; Ukraine as a third-party combat
    theater.

resolution_only
    The geographic detail exists only because of the legal definition of the
    PARTICULAR action/event being asked about. It must NOT condition the
    structural action-family prior. Examples: a blockade contract naming
    ports/airports; an invasion definition specifying that inhabited but not
    uninhabited islands count; a strike definition requiring impact inside
    recognized borders.

CRITICAL ANTI-CIRCULARITY RULE:
Do not let details intrinsic to the contract's requested action leak into the
structural action prior. If the geographic restriction would largely disappear
or change if the same actors were asked about a different action family, mark
it resolution_only.

target_wide
    Ordinary action against the target's generally recognized territory or
    forces; no narrower special geography controls the contract.

subterritory
    The contract is specifically restricted to a named portion, dependency,
    autonomous territory, island, province, etc. of the target.
    Example: Greenland within the Kingdom of Denmark.

third_party_theater
    The action must occur in territory/theater that is neither simply the
    initiator nor target's general territory.
    Example: NATO/EU troops fighting Russia in Ukraine.

multiple
    Several specifically named operational geographies qualify.

unspecified
    The contract does not provide meaningful geographic restriction.

RULES

- Use ONLY the supplied contract text and assigned direction.
- Preserve explicit enumerated lists.
- Do not silently replace an enumerable union with an aggregate fictional
  actor.
- Do not infer current membership of NATO, EU, ECOWAS, etc. If the contract
  uses a named membership rule without listing members, use named_group_union
  and record the group name.
- An autonomous territory can be operational geography while its sovereign
  state remains the target actor.
- Do not change the assigned initiator/target merely because contract wording
  is awkward. Scope metadata supplements routing metadata.
- If the assigned direction is clearly incompatible with the contract, set
  direction_compatible=false. Do not silently repair it.
- Resolution restrictions on weapon/action type are NOT party/geographic
  scope. Do not encode them as geography.

Return ONLY JSON:

{
  "initiator_scope": {
    "mode": "single_actor|enumerable_union|named_group_union|collective_actor|undefined_union",
    "canonical_actor": "string or null",
    "entity_type": "state|nonstate_actor|intergovernmental_org|coalition|mixed|unknown",
    "members": [],
    "group_names": []
  },
  "target_scope": {
    "mode": "single_actor|enumerable_union|named_group_union|collective_actor|undefined_union",
    "canonical_actor": "string or null",
    "entity_type": "state|nonstate_actor|intergovernmental_org|coalition|mixed|unknown",
    "members": [],
    "group_names": []
  },
  "geography": {
    "mode": "target_wide|subterritory|third_party_theater|multiple|unspecified",
    "places": [],
    "prior_relevance": "structural_theater|resolution_only"
  },
  "direction_compatible": true,
  "confidence": "high|medium|low",
  "reasoning": "brief semantic explanation"
}
"""


def _extract_json(text: str) -> dict:
    text = text.strip()

    if "```" in text:
        for part in text.split("```"):
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            try:
                return json.loads(candidate)
            except Exception:
                pass

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            return json.loads(text[start:end + 1])
        raise


def _normalize_party(raw: dict, label: str) -> dict:
    if not isinstance(raw, dict):
        raise ValueError(f"{label} must be an object")

    mode = str(raw.get("mode", "")).strip()
    if mode not in PARTY_MODES:
        raise ValueError(f"{label}: invalid mode {mode!r}")

    entity_type = str(raw.get("entity_type", "unknown")).strip()
    if entity_type not in ENTITY_TYPES:
        raise ValueError(
            f"{label}: invalid entity_type {entity_type!r}"
        )

    canonical = raw.get("canonical_actor")
    if canonical is not None:
        canonical = str(canonical).strip() or None

    members = raw.get("members", [])
    groups = raw.get("group_names", [])

    if not isinstance(members, list):
        raise ValueError(f"{label}.members must be a list")
    if not isinstance(groups, list):
        raise ValueError(f"{label}.group_names must be a list")

    members = sorted({
        str(x).strip()
        for x in members
        if str(x).strip()
    })
    groups = sorted({
        str(x).strip()
        for x in groups
        if str(x).strip()
    })

    if mode == "single_actor" and not canonical:
        raise ValueError(
            f"{label}: single_actor requires canonical_actor"
        )

    if mode == "enumerable_union" and not members:
        raise ValueError(
            f"{label}: enumerable_union requires members"
        )

    if mode == "named_group_union" and not groups:
        raise ValueError(
            f"{label}: named_group_union requires group_names"
        )

    return {
        "mode": mode,
        "canonical_actor": canonical,
        "entity_type": entity_type,
        "members": members,
        "group_names": groups,
    }


def normalize_scope(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("scope must be an object")

    initiator = _normalize_party(
        raw.get("initiator_scope"),
        "initiator_scope",
    )

    target = _normalize_party(
        raw.get("target_scope"),
        "target_scope",
    )

    geography = raw.get("geography")
    if not isinstance(geography, dict):
        raise ValueError("geography must be an object")

    geo_mode = str(
        geography.get("mode", "")
    ).strip()

    if geo_mode not in GEOGRAPHY_MODES:
        raise ValueError(
            f"invalid geography mode: {geo_mode!r}"
        )

    places = geography.get("places", [])
    if not isinstance(places, list):
        raise ValueError("geography.places must be a list")

    places = sorted({
        str(x).strip()
        for x in places
        if str(x).strip()
    })

    prior_relevance = str(
        geography.get("prior_relevance", "")
    ).strip()

    if prior_relevance not in GEOGRAPHY_PRIOR_RELEVANCE:
        raise ValueError(
            "geography.prior_relevance must be "
            "structural_theater or resolution_only"
        )

    # target_wide/unspecified already encode their geography completely.
    # Repeating the target name in places is semantically redundant and
    # would make equivalent scopes hash differently.
    if geo_mode in {"target_wide", "unspecified"}:
        places = []

    compatible = raw.get("direction_compatible")
    if not isinstance(compatible, bool):
        raise ValueError(
            "direction_compatible must be boolean"
        )

    confidence = str(
        raw.get("confidence", "medium")
    ).strip().lower()

    if confidence not in {"high", "medium", "low"}:
        confidence = "medium"

    return {
        "initiator_scope": initiator,
        "target_scope": target,
        "geography": {
            "mode": geo_mode,
            "places": places,
            "prior_relevance": prior_relevance,
        },
        "direction_compatible": compatible,
        "confidence": confidence,
        "reasoning": str(
            raw.get("reasoning", "")
        ).strip(),
    }



def apply_direction_authority(
    scope: dict,
    initiator: str,
    target: str,
) -> dict:
    """
    Routing metadata is authoritative for singular/collective parties.

    The semantic resolver may elaborate scope, but it may not rename the
    already-resolved contract direction. Union scopes remain unions.
    """
    s = normalize_scope(scope)

    for side, assigned in (
        ("initiator_scope", initiator),
        ("target_scope", target),
    ):
        party = s[side]

        if party["mode"] in {
            "single_actor",
            "collective_actor",
        }:
            party["canonical_actor"] = str(assigned).strip()

    return s



def scope_core(scope: dict) -> dict:
    """
    Structural fields only.

    Excludes confidence/reasoning so identical semantics produce the same
    fingerprint even if explanatory prose changes.
    """
    s = normalize_scope(scope)

    return {
        "initiator_scope": s["initiator_scope"],
        "target_scope": s["target_scope"],
        "geography": s["geography"],
        "direction_compatible": s["direction_compatible"],
    }


def scope_fingerprint(scope: dict) -> str:
    canonical = json.dumps(
        scope_core(scope),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:16]



def action_prior_scope_core(scope: dict) -> dict:
    """
    Projection of contract scope that is safe to condition the structural
    action-family prior on.

    Resolution-only geography is deliberately erased to prevent the action
    requested by the market from leaking back into its own prior.
    """
    s = normalize_scope(scope)

    geography = s["geography"]

    if geography["prior_relevance"] == "structural_theater":
        prior_geo = {
            "mode": geography["mode"],
            "places": geography["places"],
        }
    else:
        prior_geo = {
            "mode": "target_wide",
            "places": [],
        }

    return {
        "initiator_scope": s["initiator_scope"],
        "target_scope": s["target_scope"],
        "geography": prior_geo,
        "direction_compatible": s["direction_compatible"],
    }


def action_prior_fingerprint(scope: dict) -> str:
    canonical = json.dumps(
        action_prior_scope_core(scope),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )

    return hashlib.sha256(
        canonical.encode("utf-8")
    ).hexdigest()[:16]


def action_prior_structural_context(scope: dict) -> str:
    return json.dumps(
        action_prior_scope_core(scope),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )



def structural_context(scope: dict) -> str:
    """
    Human-readable structural context for the action-prior generator.
    """
    s = normalize_scope(scope)

    return json.dumps(
        scope_core(s),
        indent=2,
        ensure_ascii=False,
        sort_keys=True,
    )


def resolve_contract_scope(
    *,
    initiator: str,
    target: str,
    question: str,
    description: str,
    max_retries: int = 3,
) -> dict[str, Any]:

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("Missing ANTHROPIC_API_KEY")

    prompt = f"""
ASSIGNED INITIATOR: {initiator}
ASSIGNED TARGET: {target}

QUESTION:
{question}

RESOLUTION CRITERIA:
{description[:8000]}
"""

    payload = {
        "model": MODEL,
        "max_tokens": 1600,
        "temperature": 0,
        "system": SYSTEM_PROMPT,
        "messages": [
            {"role": "user", "content": prompt}
        ],
    }

    headers = {
        "Content-Type": "application/json",
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
    }

    last_error = None

    for attempt in range(max_retries):
        try:
            response = requests.post(
                ANTHROPIC_API,
                headers=headers,
                json=payload,
                timeout=60,
            )

            response.raise_for_status()
            body = response.json()

            parsed = _extract_json(
                body["content"][0]["text"]
            )

            normalized = apply_direction_authority(
                parsed,
                initiator,
                target,
            )
            normalized["scope_fingerprint"] = (
                scope_fingerprint(normalized)
            )

            return normalized

        except Exception as exc:
            last_error = exc

            if attempt + 1 < max_retries:
                time.sleep(1.5 * (attempt + 1))

    raise last_error
