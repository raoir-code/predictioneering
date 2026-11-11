"""Nov 11, 2026: tests for the places that can fail silently while the machine runs unattended.
  1. The price adjusters (strike|no war, strike|war, declare war, role tilt) restore and re-apply each run without compounding,
     and the translator calls them in the order their docstrings require.
  2. Role labels (pipeline/episode_roles.json) are valid and consistent.
  3. Family tags: ceasefire / agreement / gap / war-outcome contracts are tagged; strike and invasion contracts are not; stale tags clear.
  4. The node-scoring last-good fallback: recent scores on the live run, zeros when too old, never on a backtest.
  5. Policy files the pipeline reads with a silent default are present and shaped as expected.
Run: python3.11 -m pytest -q tests
"""
import sys, os, json, copy, datetime as dt
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pilot")); sys.path.insert(0, str(ROOT / "pipeline"))
import strike_no_war as SNW, strike_given_war as SGW, declare_war as DW, directional_pba as ROLE

STRIKE = {"bucket": "CORE", "question": "Saudi Arabia military action against Iran by December 31, 2026?", "action_type": "airstrike",
          "contract_initiator": "Saudi Arabia", "contract_target": "Iran", "parent_event_relation": "overlap", "contract_polarity": "conflict",
          "our_prediction": 0.40, "p_b_given_a": 0.48, "p_b_given_not_a_scaled": 0.02, "conditional_p": 0.204, "days_remaining": 30}
DECLARE = {"bucket": "CORE", "question": "Will the US officially declare war on Iran by December 31, 2026?", "action_type": None,
           "contract_initiator": "US", "contract_target": "Iran", "contract_polarity": "conflict",
           "our_prediction": 0.10, "p_b_given_a": 0.30, "p_b_given_not_a_scaled": 0.001, "conditional_p": 0.0309}
P_SNW = {"table": {"Saudi Arabia->Iran": {"rates": {"30": 0.05}}}}
P_SGW = {"p": 0.60}
ROLES = {"Saudi Arabia->Iran": {"role": "target"}}

def _run(feed, sgw=P_SGW):
    """One daily run, as pipeline/translator.py does it: restores first (role tilt first), translation (worst case: leaves the
    restored values untouched), then the applies (role tilt last)."""
    ROLE.restore(feed); SGW.restore(feed); SNW.restore(feed); DW.restore(feed)
    SNW.apply(feed, P_SNW); SGW.apply(feed, sgw); DW.apply(feed); ROLE.apply(feed, ROLES)
    return [(m["conditional_p"], m["p_b_given_a"], m["p_b_given_not_a_scaled"]) for m in feed]

def test_adjusters_do_not_compound():
    feed = [copy.deepcopy(STRIKE), copy.deepcopy(DECLARE)]
    first = _run(feed)
    assert _run(feed) == first and _run(feed) == first                  # three runs, one published price
    b = ROLE.tilt(0.60, "target"); a = 0.40
    assert first[0] == (round(a * round(b, 4) + (1 - a) * 0.05, 4), round(b, 4), 0.05)
    assert first[1][1] == DW.P_DECLARE_GIVEN_A
    ROLE.restore(feed); SGW.restore(feed); SNW.restore(feed); DW.restore(feed)
    assert feed[0]["conditional_p"] == STRIKE["conditional_p"] and feed[0]["p_b_given_a"] == STRIKE["p_b_given_a"]
    assert feed[0]["p_b_given_not_a_scaled"] == STRIKE["p_b_given_not_a_scaled"] and feed[1]["conditional_p"] == DECLARE["conditional_p"]
    assert not [k for m in feed for k in m if k.endswith(("_pre_role", "_pre_empirical", "_pre_snw", "_pre_dw"))]

def test_role_tilt_does_not_compound_without_strike_given_war():
    # Production today: strike|war is off ({} = no table), so the role tilt acts on the LLM's own P(B|A); only its restore prevents compounding.
    feed = [copy.deepcopy(STRIKE)]
    first = _run(feed, sgw={})
    assert _run(feed, sgw={}) == first and _run(feed, sgw={}) == first
    assert first[0][1] == round(ROLE.tilt(0.48, "target"), 4)

def test_declaration_and_strike_adjusters_never_overlap():
    # declare_war restores last; that is only safe because no contract is adjusted by both it and a strike adjuster.
    assert not SGW.qualifies(DECLARE) and DW.qualifies(DECLARE) and not DW.qualifies(STRIKE)
    feed = json.loads((ROOT / "pipeline" / "classified_feed.json").read_text())
    both = [m.get("question") for m in feed if isinstance(m, dict) and DW.qualifies(m) and SGW.qualifies(m)]
    assert not both, both

def test_translator_calls_adjusters_in_order():
    src = (ROOT / "pipeline" / "translator.py").read_text()
    run = src[src.index("def run_translator"):]
    pos = lambda s: run.index(s)
    assert pos("_ROLE.restore(") < pos("_SGW.restore(") < pos("_SNW.restore(") < pos("_DW.restore(") < pos("translate_market(")
    assert pos("translate_market(") < pos("_SNW.apply(") < pos("_SGW.apply(") < pos("_DW.apply(") < pos("_ROLE.apply(")
    assert pos("_ROLE.apply(") < pos("_apply_during_war_pricing(feed)") < pos("_rebet_on_published(feed)")
    assert '"p_b_given_a_pre_role"' in src and '"bet_basis"' in src                           # logged fields the health checks read

def test_role_labels_valid_and_consistent():
    R = json.loads((ROOT / "pipeline" / "episode_roles.json").read_text())
    dt.date.fromisoformat(R["as_of"])
    P = R["pairs"]
    for k, v in P.items():
        assert k.count("->") == 1 and all(k.split("->")), k
        assert v.get("role") in ("initiator", "target", "unclear"), (k, v)
        rev = (P.get("->".join(k.split("->")[::-1])) or {}).get("role")
        if v["role"] in ("initiator", "target"):
            assert rev != v["role"], f"{k} and its reverse are both {v['role']}"

def test_family_tags():
    import ceasefire_holds as CH
    fx = json.loads((ROOT / "tests" / "fixtures" / "family_tags.json").read_text())
    feed = [{"question": f["question"], "description": f["description"], "bucket": "ADJACENT"} for f in fx]
    stale = {"question": fx[-1]["question"], "description": fx[-1]["description"], "bucket": "CORE", "contract_family": "HOLDS", "conditional_p": 0.5}
    CH.tag_feed(feed + [stale])
    for f, m in zip(fx, feed):
        assert m.get("contract_family") == f["family"], (f["question"], m.get("contract_family"))
        if f["family"]: assert m["bucket"] == "CORE"
    assert stale["contract_family"] is None and stale["bucket"] == "ADJACENT" and stale["conditional_p"] is None

def test_last_good_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", os.environ.get("ANTHROPIC_API_KEY", "test"))
    monkeypatch.setenv("GNEWS_API_KEY", os.environ.get("GNEWS_API_KEY", "test"))
    import importlib.util                                     # pipeline/engine.py by path: a top-level engine/ package shadows the name
    spec = importlib.util.spec_from_file_location("pipeline_engine", ROOT / "pipeline" / "engine.py")
    E = importlib.util.module_from_spec(spec); spec.loader.exec_module(E)
    monkeypatch.setattr(E, "NODE_SCORES_LAST_GOOD", tmp_path / "last_good.json")
    fields = ["CommitmentProblem", "TriggerType"]
    today = dt.datetime.utcnow().date()
    E._save_last_good("A-B", fields, today.isoformat(), True, {"CommitmentProblem": 0.5, "TriggerType": 2.0})
    assert E._fallback_scores("A-B", fields, today.isoformat(), True) == {"CommitmentProblem": 0.5, "TriggerType": 2.0}
    assert E._fallback_scores("C-D", fields, today.isoformat(), True) == {"CommitmentProblem": 0.0, "TriggerType": 0.0}
    assert E._fallback_scores("A-B", fields, "2026-01-05", True) == {"CommitmentProblem": 0.0, "TriggerType": 0.0}     # backtest date
    assert E._fallback_scores("A-B", fields, today.isoformat(), False) == {"CommitmentProblem": 0.0, "TriggerType": 0.0}
    cache = json.loads((tmp_path / "last_good.json").read_text())
    for v in cache.values(): v["as_of"] = (today - dt.timedelta(days=E.LAST_GOOD_MAX_AGE_DAYS + 1)).isoformat()
    (tmp_path / "last_good.json").write_text(json.dumps(cache))
    assert E._fallback_scores("A-B", fields, today.isoformat(), True) == {"CommitmentProblem": 0.0, "TriggerType": 0.0}  # too old
    E._save_last_good("A-B", fields, "2026-01-05", True, {"CommitmentProblem": 9.0, "TriggerType": 9.0})                # backtests never write
    assert all(v["scores"]["CommitmentProblem"] == 0.5 for v in json.loads((tmp_path / "last_good.json").read_text()).values())

def test_policy_files_shape():
    J = lambda f: json.loads((ROOT / f).read_text())
    u = J("pilot/unified_publish.json"); assert isinstance(u["enabled"], bool) and isinstance(u["excluded"], (list, dict))
    h = J("pilot/holds_publish.json"); assert isinstance(h["allowed"], list) and h["allowed"]
    assert J("pilot/c_policy.json")["model"]
    w = J("pilot/during_war_config.json"); assert isinstance(w["pairs"], dict) and w["pairs"]
