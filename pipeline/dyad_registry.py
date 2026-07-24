"""
Canonical dyad registry — single source of truth for bilateral dyad key naming.

Any code that writes or reads a `dyad` field should call canonicalize() rather
than trusting a raw string from an LLM call, a cache, or a log row. This exists
because disciplinarian.py's dyad-naming rule ("more powerful state first") is an
LLM prompt instruction, not a deterministic rule, and LLM calls do not have
memory of previously-established keys across separate invocations.
"""

ALIASES = {
    "NATO-Russia": ["Russia-NATO"],
    # Reversed 2026-07-23 from the log-majority default. NATO-Russia holds the
    # June 10-11 hand-verified PatronDeterrence=2.0 baseline (dedicated literature
    # session, Benson 2011 / Shea 2014 grounding). Russia-NATO was an unreviewed
    # auto-generated duplicate first introduced in the June 22 "suppressor cluster
    # rebuild" commit (PatronDeterrence=0.5) via disciplinarian.py's generate_baseline()
    # firing on a reversed-order classification. The majority of live log rows (144)
    # were generated under the WRONG (auto-generated) baseline -- this is a real
    # calibration bug being fixed, not just a naming cleanup. See work log 2026-07-23.
    "Israel-Iran": ["Iran-Israel"],
    "Israel-Qatar": ["Qatar-Israel"],
    "North Korea-US": ["US-North Korea"],
    "US-Russia": ["Russia-US"],
    "Cuba-Israel": ["Israel-Cuba"],
    "Indonesia-Israel": ["Israel-Indonesia"],
    "Bangladesh-Israel": ["Israel-Bangladesh"],
    "Turkey-Greece": ["Greece-Turkey"],
    "Israel-Saudi Arabia": ["Saudi Arabia-Israel", "Israel-SaudiArabia"],
    "Israel-Pakistan": ["Pakistan-Israel"],
    "US-Colombia": ["USA-Colombia"],
    "US-Denmark": ["USA-Denmark"],
    "US-Iran": ["USA-Iran"],
    "US-Venezuela": ["USA-Venezuela"],
    "North Korea-South Korea": ["NorthKorea-SouthKorea"],
}

NON_BILATERAL = {
    "Russia-Unknown",
    "US-Unknown",  # "any country expels a US ambassador" -- undefined counterparty,
                   # same pattern as Russia-Unknown. Added 2026-07-24.
    "US-Unknown",  # "any country expels a US ambassador" -- undefined counterparty,
                   # same pattern as Russia-Unknown. Added 2026-07-24.
    "US-LatinAmerica",
    "Israel-Multiple",
    "Europe(France/UK/Germany)-Iran",
    "France/UK/Germany-Iran",
    "Germany-Iran",
}

_ALIAS_TO_CANONICAL = {}
for canonical, aliases in ALIASES.items():
    for alias in aliases:
        _ALIAS_TO_CANONICAL[alias] = canonical

CANONICAL_KEYS = set(ALIASES.keys())


def _normalize(s):
    """Token-set normalization for fuzzy collision detection."""
    import re
    parts = re.split(r"[-_/]", s.lower().strip())
    return tuple(sorted(p.strip() for p in parts if p))


def find_fuzzy_match(raw_key, existing_keys):
    """Returns the existing key that raw_key is probably a reordered/respaced
    variant of, or None if raw_key looks like a genuinely new dyad."""
    target = _normalize(raw_key)
    for k in existing_keys:
        if _normalize(k) == target and k != raw_key:
            return k
    return None


class UnknownDyadError(ValueError):
    """Raised when a dyad key is neither a known canonical key, a known alias,
    nor a known non-bilateral key. Deliberate -- forces a conscious registry
    update rather than silent pass-through."""
    pass


def canonicalize(raw_key, known_bilateral_keys=None):
    """
    Resolve a raw dyad string to its canonical form.
    Returns: (canonical_key: str, is_bilateral: bool)
    """
    if raw_key in NON_BILATERAL:
        return raw_key, False

    if raw_key in _ALIAS_TO_CANONICAL:
        return _ALIAS_TO_CANONICAL[raw_key], True

    if raw_key in CANONICAL_KEYS:
        return raw_key, True

    if known_bilateral_keys is not None and raw_key in known_bilateral_keys:
        return raw_key, True

    raise UnknownDyadError(
        f"Dyad key '{raw_key}' is not in the canonical registry, alias table, "
        f"or NON_BILATERAL set, and was not found in known_bilateral_keys. "
        f"This is a new dyad or a new naming variant -- add it to dyad_registry.py "
        f"deliberately rather than letting it pass through silently."
    )
