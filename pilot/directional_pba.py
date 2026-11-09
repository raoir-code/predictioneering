"""docs/directional_pba_prereg.md (64f739d) + docs/directional_pba_result.md (d2fd18d): the engine's own P(B|A) on strike contracts,
tilted by the contract initiator's role in the current episode (pipeline/episode_roles.json). Same qualifying contracts as
strike_given_war.qualifies(). In pipeline/translator.py: restore() FIRST (before strike_no_war's restore, since this is applied after
it), apply() after strike_no_war / strike_given_war / declare_war, before the during-war pass. A pair with no label gets no tilt and is
reported. If strike_given_war ever goes live, this tilts its empirical rate instead of the LLM's: revisit then.
"""
import json, math, collections
from pathlib import Path
from strike_given_war import qualifies

ROLES = Path(__file__).resolve().parent.parent / "pipeline" / "episode_roles.json"
COMPONENT = "role-tilt-v0"
OR = 0.1556                 # dyadic MID 3.1, disputes starting 1946-2010: odds(target uses force) / odds(initiator uses force)
H = 0.5 * math.log(OR)      # -0.930 on the logit scale: target +H, initiator -H

def load_roles(path=ROLES):
    return json.loads(Path(path).read_text())["pairs"]

def tilt(b, role):
    b = min(max(float(b), 1e-4), 1 - 1e-4)
    return 1 / (1 + math.exp(-(math.log(b / (1 - b)) + (H if role == "target" else -H))))

def restore(feed):
    """Put back the P(B|A) and price this module saw before last run's apply(), so the tilt never compounds."""
    n = 0
    for m in feed:
        if isinstance(m, dict) and m.get("p_b_given_a_pre_role") is not None:
            m["p_b_given_a"], m["conditional_p"] = m["p_b_given_a_pre_role"], m.get("conditional_p_pre_role")
            for k in ("p_b_given_a_pre_role", "conditional_p_pre_role", "p_b_given_a_role"): m.pop(k, None)
            n += 1
    return n

def apply(feed, roles=None):
    """Returns (counts by role, sorted unlabeled pairs)."""
    roles = load_roles() if roles is None else roles
    n, unlabeled = collections.Counter(), set()
    for m in feed:
        if not isinstance(m, dict) or m.get("resolved") or m.get("contract_family") or m.get("bucket") != "CORE" or not qualifies(m): continue
        if m.get("conditional_p") is None: continue
        key = f"{m['contract_initiator']}->{m['contract_target']}"
        role = (roles.get(key) or {}).get("role")
        if role is None: n["unlabeled"] += 1; unlabeled.add(key); continue
        if role not in ("initiator", "target"): n["unclear"] += 1; continue
        a, c = float(m["our_prediction"]), float(m["p_b_given_not_a_scaled"])
        b2 = tilt(m["p_b_given_a"], role)
        m["p_b_given_a_pre_role"], m["conditional_p_pre_role"] = m["p_b_given_a"], m["conditional_p"]
        m["p_b_given_a"] = round(b2, 4); m["conditional_p"] = round(a * b2 + (1 - a) * c, 4); m["p_b_given_a_role"] = f"{COMPONENT}:{role}"
        n[role] += 1
    return n, sorted(unlabeled)

def _tests():
    base = {"bucket": "CORE", "action_type": "airstrike", "contract_initiator": "Saudi Arabia", "contract_target": "Iran", "parent_event_relation": "overlap",
            "contract_polarity": "conflict", "our_prediction": 0.65, "p_b_given_not_a_scaled": 0.01, "p_b_given_a": 0.48, "conditional_p": 0.3155}
    R = {"Saudi Arabia->Iran": {"role": "target"}, "Iran->Saudi Arabia": {"role": "initiator"}, "Israel->Lebanon": {"role": "unclear"}}
    ini = dict(base, contract_initiator="Iran", contract_target="Saudi Arabia"); unc = dict(base, contract_initiator="Israel", contract_target="Lebanon")
    unl = dict(base, contract_initiator="US", contract_target="Cuba"); fam = dict(base, contract_family="AGREEMENT"); res = dict(base, resolved=True)
    feed = [dict(base), ini, unc, unl, fam, res]
    n, u = apply(feed, R)
    assert n == {"target": 1, "initiator": 1, "unclear": 1, "unlabeled": 1} and u == ["US->Cuba"], (n, u)
    assert abs(feed[0]["p_b_given_a"] - 0.2675) < 0.001 and feed[0]["p_b_given_a"] < 0.48 < feed[1]["p_b_given_a"]
    assert feed[0]["conditional_p"] == round(0.65 * feed[0]["p_b_given_a"] + 0.35 * 0.01, 4)
    assert feed[2]["conditional_p"] == 0.3155 and "p_b_given_a_pre_role" not in feed[3] and "p_b_given_a_pre_role" not in feed[4]
    assert restore(feed) == 2 and feed[0]["p_b_given_a"] == 0.48 and feed[0]["conditional_p"] == 0.3155 and "p_b_given_a_role" not in feed[0]
    apply(feed, R); restore(feed); apply(feed, R); assert feed[0]["p_b_given_a_pre_role"] == 0.48          # restore -> apply is stable
    # composes with strike_no_war: restore this first, then its own; apply after it
    import strike_no_war as S
    m = dict(base); m["p_b_given_not_a_pre_empirical"], m["conditional_p_pre_snw"] = 0.02, 0.32; feed = [m]
    apply(feed, R); assert restore(feed) == 1 and feed[0]["conditional_p"] == 0.3155; S.restore(feed); assert feed[0]["conditional_p"] == 0.32
    print("directional_pba tests: OK")

if __name__ == "__main__":
    _tests()
