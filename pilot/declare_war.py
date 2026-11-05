"""docs/declare_war_prereg.md: empirical P(B|A) for formal declarations of war (Nov 5, 2026). Replaces the Clergyman's
political-act anchor range [0.3, 0.9], which clamped the LLM's own 0.04 up to 0.30 ("US officially declare war on Iran").
Rule by contract text, not by pair: any contract whose question asks for a declaration of war. Used by pipeline/translator.py
(restore at the start of a run, apply after strike|war, before the during-war pass). Own field names: never collides with
strike_given_war / strike_no_war.
  python pilot/declare_war.py      tests
"""
import re

COMPONENT = "empirical-mid-declaration-v0"
P_DECLARE_GIVEN_A = 0.02      # MID (GML) post-1945: 0 of 403 serious disputes (A1) with hiact = declaration of war; allowance for
                              # declarations masked by war codes (hiact >= 20). See docs/declare_war_prereg.md.
PATTERN = re.compile(r"\bdeclar(?:e|es|ed|ation of)\s+(?:a\s+)?war\b", re.I)

def qualifies(m):
    q = m.get("question") or m.get("market_label") or ""
    return bool(PATTERN.search(q) and (m.get("contract_polarity") or "conflict") == "conflict"
                and m.get("our_prediction") is not None and m.get("p_b_given_not_a_scaled") is not None and m.get("p_b_given_a") is not None)

def restore(feed):
    """Put back the model's own P(B|A) and price saved by the previous run's apply(), so nothing compounds."""
    n = 0
    for m in feed:
        if isinstance(m, dict) and m.get("p_b_given_a_pre_dw") is not None:
            m["p_b_given_a"], m["conditional_p"] = m["p_b_given_a_pre_dw"], m.get("conditional_p_pre_dw")
            for k in ("p_b_given_a_pre_dw", "conditional_p_pre_dw"): m.pop(k, None)
            if m.get("p_b_given_a_source") == COMPONENT: m.pop("p_b_given_a_source", None)
            n += 1
    return n

def apply(feed, p=P_DECLARE_GIVEN_A):
    n = 0
    for m in feed:
        if not isinstance(m, dict) or m.get("resolved") or m.get("contract_family") or m.get("bucket") != "CORE" or not qualifies(m): continue
        if m.get("conditional_p") is None: continue
        a, c = float(m["our_prediction"]), float(m["p_b_given_not_a_scaled"])
        m["p_b_given_a_pre_dw"], m["conditional_p_pre_dw"] = m["p_b_given_a"], m["conditional_p"]
        m["p_b_given_a"] = round(p, 4); m["conditional_p"] = round(a * p + (1 - a) * c, 4); m["p_b_given_a_source"] = COMPONENT
        n += 1
    return n

def _tests():
    m = {"bucket": "CORE", "question": "Will the US officially declare war on Iran by December 31, 2026?", "contract_polarity": "conflict",
         "our_prediction": 0.8513, "p_b_given_not_a_scaled": 0.000782, "p_b_given_a": 0.3, "conditional_p": 0.2555}
    strike = dict(m, question="Will the US strike Iran by December 31, 2026?")
    feed = [dict(m), strike, dict(m, resolved=True), dict(m, bucket="NOISE"), dict(m, contract_family="HOLDS")]
    assert apply(feed) == 1 and feed[0]["p_b_given_a"] == 0.02 and feed[0]["conditional_p"] == round(0.8513 * 0.02 + 0.1487 * 0.000782, 4)
    assert feed[0]["p_b_given_a_source"] == COMPONENT and "p_b_given_a_pre_dw" not in feed[1]
    assert restore(feed) == 1 and feed[0]["p_b_given_a"] == 0.3 and feed[0]["conditional_p"] == 0.2555 and "p_b_given_a_source" not in feed[0]
    apply(feed); restore(feed); apply(feed); assert feed[0]["p_b_given_a_pre_dw"] == 0.3            # restore -> apply is stable
    for q in ("Will Russia declare war on Ukraine?", "US declaration of war on Venezuela by June 30?", "Will Congress declare a war?"):
        assert qualifies(dict(m, question=q)), q
    for q in ("Will Israel declare a ceasefire?", "Will the war be declared over?", "Russia x Ukraine ceasefire by ...?"):
        assert not qualifies(dict(m, question=q)), q
    other = dict(m, p_b_given_a_source="empirical-sgw-v0", p_b_given_a_pre_empirical=0.47)
    assert restore([other]) == 0 and other["p_b_given_a_source"] == "empirical-sgw-v0"                   # never touches the other modules
    print("declare_war tests: OK")

if __name__ == "__main__":
    _tests()
