#!/usr/bin/env python3.11
"""
Patch 5 — wrap the Anthropic API call in _call_claude_json with proper
exception handling and one retry. Root cause of last night's crash: the
network call itself (requests.post) had zero exception handling, unlike
the JSON-parsing step right after it. A read timeout (e.g. from a laptop
sleep/wake cycle, or just a slow response) was an uncaught exception that
took down the entire script -- and since results only save once at the
very end, that meant losing the whole run's progress, not just one row.

Run from repo root: python3.11 patch_5_network_retry.py
"""
from pathlib import Path

path = Path("pipeline/backtest.py")
content = path.read_text()

old = r'''def _call_claude_json(prompt, expected_fields, max_tokens):
    """Shared Claude call + JSON parse, used by both Call A and Call B."""
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }
    r = requests.post("https://api.anthropic.com/v1/messages",
                      headers=headers, json=body, timeout=60)
    resp = r.json()
'''

new = r'''def _call_claude_json(prompt, expected_fields, max_tokens, retries=1):
    """Shared Claude call + JSON parse, used by both Call A and Call B.

    The network call is wrapped separately from the JSON-parsing step below --
    a dropped connection or read timeout (e.g. from a laptop sleep/wake cycle)
    is a different failure mode than the model returning malformed JSON, and
    previously crashed the whole script since nothing caught it. Retries once
    before falling back to zeros, since a fresh attempt right after a timeout
    usually just works.
    """
    headers = {
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    body = {
        "model": "claude-opus-4-6",
        "max_tokens": max_tokens,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
    }

    resp = None
    for attempt in range(retries + 1):
        try:
            r = requests.post("https://api.anthropic.com/v1/messages",
                              headers=headers, json=body, timeout=60)
            resp = r.json()
            break
        except requests.exceptions.RequestException as e:
            if attempt < retries:
                print(f"    [warn] API request failed ({type(e).__name__}), retrying once...")
                continue
            print(f"    [warn] API request failed ({type(e).__name__}) after retry, using zeros")
            return {n: 0.0 for n in expected_fields}
        except ValueError:
            print(f"    [warn] API returned non-JSON response, using zeros")
            return {n: 0.0 for n in expected_fields}

'''

assert old in content, "OLD BLOCK NOT FOUND — aborting, no changes made. Run patches in order and only once each."
assert content.count(old) == 1, "OLD BLOCK NOT UNIQUE — aborting, refusing to guess which occurrence to replace"

content = content.replace(old, new)
path.write_text(content)
print("Patch 5 applied — network call now retries once on timeout/connection error before falling back to zeros, instead of crashing the whole script.")
