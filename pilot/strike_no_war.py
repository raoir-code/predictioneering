"""docs/strike_no_war_prereg.md + amendment 1: empirical P(B|not A) for the onset engine's strike contracts. Used by
pipeline/translator.py (restore at the start of a run, apply as the last step before the during-war pass, before strike|war) and by
analysis/strike_no_war_compare.py. Off unless pilot/local/strike_no_war.json exists (the adopted frozen table).
"""
import re, json
from pathlib import Path
from strike_given_war import qualifies as _sgw_qualifies

LOCAL = Path(__file__).resolve().parent / "local"
COMPONENT = "empirical-snw-v0"
NAMES = {"US": "United States", "USA": "United States", "UK": "United Kingdom", "UAE": "United Arab Emirates"}

def params():
    f = LOCAL / "strike_no_war.json"
    return json.loads(f.read_text()) if f.exists() else None

def parse(q):
    """Same rule as analysis/strike_no_war_fit.py: (initiators, target) from the question text."""
    m = re.match(r"^(?:Will )?(.+?) (?:military action against|target|strike|attack) (.+?) (?:by|on|before) ", q or "")
    if not m: return None, None
    ini = [x.strip() for x in re.split(r",\s*(?:or\s+)?|\s+or\s+", m.group(1)) if x.strip()]
    tgt = re.sub(r"^(?:the|on) ", "", m.group(2).strip())
    return [NAMES.get(x, x) for x in ini], NAMES.get(tgt, tgt)

def key(m):
    """Table key for a market, or None if it is not a whole-state direction (sub-state or group targets keep the LLM value)."""
    ini, tgt = parse(m.get("question") or m.get("market_label"))
    if not ini or not tgt or tgt != NAMES.get(m.get("contract_target"), m.get("contract_target")): return None
    return f"{'+'.join(sorted(ini))}->{tgt}"

def rate(m, P):
    k = key(m); row = (P.get("table") or {}).get(k) if k else None
    if not row: return None
    W = max(1, min(120, int(round(float(m.get("days_remaining") or 1)))))
    v = row["rates"].get(str(W), row["rates"].get(W))
    return None if v is None else float(v)

def restore(feed):
    """Put back the model's own P(B|not A) and price saved by the previous run's apply(), so nothing compounds."""
    n = 0
    for m in feed:
        if isinstance(m, dict) and m.get("p_b_given_not_a_pre_empirical") is not None:
            m["p_b_given_not_a_scaled"], m["conditional_p"] = m["p_b_given_not_a_pre_empirical"], m.get("conditional_p_pre_snw")
            for k in ("p_b_given_not_a_pre_empirical", "conditional_p_pre_snw", "p_b_given_not_a_source"): m.pop(k, None)
            n += 1
    return n

def apply(feed, P=None):
    P = P if P is not None else params()
    if not P: return 0
    n = 0
    for m in feed:
        if not isinstance(m, dict) or m.get("resolved") or m.get("contract_family") or m.get("bucket") != "CORE" or not _sgw_qualifies(m): continue
        if m.get("conditional_p") is None: continue
        c = rate(m, P)
        if c is None: continue
        a, pba = float(m["our_prediction"]), float(m["p_b_given_a"])
        m["p_b_given_not_a_pre_empirical"], m["conditional_p_pre_snw"] = m["p_b_given_not_a_scaled"], m["conditional_p"]
        m["p_b_given_not_a_scaled"] = round(c, 6); m["conditional_p"] = round(a * pba + (1 - a) * c, 4); m["p_b_given_not_a_source"] = COMPONENT
        n += 1
    return n

def _tests():
    P = {"table": {"Israel->Syria": {"rates": {"5": 0.4, "35": 0.8}}, "France+Germany+United Kingdom->Yemen": {"rates": {"5": 0.1}}}}
    m = {"bucket": "CORE", "action_type": "airstrike", "contract_initiator": "Israel", "contract_target": "Syria", "parent_event_relation": "overlap",
         "contract_polarity": "conflict", "our_prediction": 0.02, "p_b_given_not_a_scaled": 0.92, "p_b_given_a": 0.5, "conditional_p": 0.9116,
         "days_remaining": 35.0, "question": "Israel military action against Syria by November 30, 2026?"}
    beirut = dict(m, question="Israel military action against Greater Beirut by October 31?", contract_target="Lebanon")
    group = dict(m, question="France, UK, or Germany military action against Yemen by October 31, 2026?", contract_initiator="UK", contract_target="Yemen", days_remaining=5.0)
    arab = dict(m, question="Will Iran target an Arab country by October 31, 2026?", contract_initiator="Iran", contract_target="Saudi Arabia")
    feed = [dict(m), beirut, group, arab]
    assert apply(feed, P) == 2, "Israel->Syria and the European group only"
    assert feed[0]["conditional_p"] == round(0.02 * 0.5 + 0.98 * 0.8, 4) and feed[0]["p_b_given_not_a_source"] == COMPONENT
    assert feed[2]["p_b_given_not_a_scaled"] == 0.1 and "p_b_given_not_a_source" not in feed[1] and "p_b_given_not_a_source" not in feed[3]
    assert restore(feed) == 2 and feed[0]["conditional_p"] == 0.9116 and feed[0]["p_b_given_not_a_scaled"] == 0.92
    apply(feed, P); restore(feed); apply(feed, P); assert feed[0]["p_b_given_not_a_pre_empirical"] == 0.92      # restore -> apply is stable
    assert apply([dict(m, days_remaining=6.0)], P) == 0, "no rate for that W -> LLM value kept"
    assert apply([dict(m, resolved=True)], P) == 0 and apply([dict(m, bucket="NOISE")], P) == 0 and apply([dict(m)], {}) == 0
    print("strike_no_war tests: OK")

if __name__ == "__main__":
    import sys; sys.path.insert(0, str(Path(__file__).resolve().parent)); _tests()
