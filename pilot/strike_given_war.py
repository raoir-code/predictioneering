"""docs/strike_given_war_prereg.md + amendment: empirical P(B|A) for the onset engine's strike contracts. Used by
pipeline/translator.py (restore at the start of a run, apply as the last step before the during-war pass) and by
analysis/strike_given_war_compare.py (the same qualification rule). Off unless pilot/local/strike_given_war.json exists.
"""
import json
from pathlib import Path

LOCAL = Path(__file__).resolve().parent / "local"
COMPONENT = "empirical-sgw-v0"

def params():
    f = LOCAL / "strike_given_war.json"
    return json.loads(f.read_text()) if f.exists() else None

def qualifies(r):
    """Pre-registered conditions, on a feed market (P(A) = our_prediction) or a logged forecast row (P(A) = engine_p)."""
    pa = r.get("our_prediction", r.get("engine_p"))
    return bool(r.get("action_type") in ("airstrike", "missile_strike") and r.get("contract_initiator") and r.get("contract_target")
                and r.get("parent_event_relation") not in ("equivalent", "conflict_bound")
                and (r.get("contract_polarity") or "conflict") == "conflict"
                and pa is not None and r.get("p_b_given_not_a_scaled") is not None and r.get("p_b_given_a") is not None)

def restore(feed):
    """Put back the model's own P(B|A) and price saved by the previous run's apply(), so nothing compounds."""
    n = 0
    for m in feed:
        if isinstance(m, dict) and m.get("p_b_given_a_pre_empirical") is not None:
            m["p_b_given_a"], m["conditional_p"] = m["p_b_given_a_pre_empirical"], m.get("conditional_p_pre_empirical")
            for k in ("p_b_given_a_pre_empirical", "conditional_p_pre_empirical", "p_b_given_a_source"): m.pop(k, None)
            n += 1
    return n

def apply(feed, P=None):
    P = P if P is not None else params()
    if not P: return 0
    n = 0
    for m in feed:
        if not isinstance(m, dict) or m.get("resolved") or m.get("contract_family") or m.get("bucket") != "CORE" or not qualifies(m): continue
        if m.get("conditional_p") is None: continue
        a, c = float(m["our_prediction"]), float(m["p_b_given_not_a_scaled"])
        m["p_b_given_a_pre_empirical"], m["conditional_p_pre_empirical"] = m["p_b_given_a"], m["conditional_p"]
        m["p_b_given_a"] = round(P["p"], 4); m["conditional_p"] = round(a * P["p"] + (1 - a) * c, 4); m["p_b_given_a_source"] = COMPONENT
        n += 1
    return n

def _tests():
    m = {"bucket": "CORE", "action_type": "airstrike", "contract_initiator": "Ethiopia", "contract_target": "Eritrea", "parent_event_relation": "overlap",
         "contract_polarity": "conflict", "our_prediction": 0.5, "p_b_given_not_a_scaled": 0.04, "p_b_given_a": 0.47, "conditional_p": 0.255}
    eq = dict(m, parent_event_relation="equivalent", p_b_given_a=1.0); peace = dict(m, contract_polarity="peace"); inv = dict(m, action_type="ground_invasion")
    feed = [dict(m), eq, peace, inv]
    assert apply(feed, {"p": 0.8}) == 1 and feed[0]["conditional_p"] == round(0.5 * 0.8 + 0.5 * 0.04, 4) and feed[0]["p_b_given_a"] == 0.8
    assert apply(feed, {"p": 0.8}) == 1 and feed[0]["p_b_given_a_pre_empirical"] == 0.8      # without restore it would compound: restore first
    feed = [dict(m)]; apply(feed, {"p": 0.8}); assert restore(feed) == 1 and feed[0]["p_b_given_a"] == 0.47 and feed[0]["conditional_p"] == 0.255
    apply(feed, {"p": 0.8}); restore(feed); apply(feed, {"p": 0.8}); assert feed[0]["p_b_given_a_pre_empirical"] == 0.47     # restore -> apply is stable
    assert qualifies({"engine_p": 0.1, **{k: v for k, v in m.items() if k != "our_prediction"}})
    print("strike_given_war tests: OK")

if __name__ == "__main__":
    _tests()
