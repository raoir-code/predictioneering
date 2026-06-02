"""
GOD'S DAG ENGINE — RAO CORP (v2)
=================================
Moment-centric version of the original God's DAG engine.

Key upgrade:
  - v1 treated one study as one moment condition
  - v2 treats one reported coefficient as one candidate moment condition
  - coefficients are clustered by study/model for diagnostics and bootstrap

Backwards compatibility:
  - old single-coefficient `Study(...)` inputs still work
  - new multi-coefficient `StudyModel(..., moments=[...])` inputs are preferred
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple, Any

import networkx as nx
import numpy as np
from scipy.linalg import svd
from scipy.optimize import minimize


# ============================================================
# DATA STRUCTURES
# ============================================================

@dataclass
class Edge:
    source: str
    target: str
    sign: Optional[int] = None
    hard_zero: bool = False
    initial_value: float = 0.3


@dataclass
class Moment:
    """
    One reported coefficient from one regression table/model.
    """
    variable: str
    beta_hat: float
    se: float
    role: str = "control"  # hero / control / interaction / other
    admissibility: str = "candidate"  # candidate / valid / mediator / collider / post_treatment / proxy / unmapped / heretic
    note: str = ""
    node_override: Optional[str] = None

    # Populated during normalization/classification
    treatment: Optional[str] = None
    outcome: Optional[str] = None
    node_map: dict = field(default_factory=dict)
    study_name: str = ""
    cluster_id: str = ""
    estimator: str = ""
    controls: list = field(default_factory=list)
    status: str = "unclassified"  # saint / sinner / complicated / heretic / excluded
    status_reason: str = ""
    bias_open_paths: list = field(default_factory=list)


@dataclass
class StudyModel:
    """
    One regression table/model that can contain many reported coefficients.
    """
    name: str
    outcome: str
    estimator: str
    controls: list
    moments: List[Moment]
    node_map: dict = field(default_factory=dict)
    cluster_id: Optional[str] = None


@dataclass
class Study:
    """
    Backwards-compatible v1 single-coefficient study object.
    Internally converted into a one-moment StudyModel.
    """
    treatment: str
    outcome: str
    beta_hat: float
    se: float
    controls: list
    estimator: str
    name: str
    node_map: dict = field(default_factory=dict)

    status: str = "unclassified"
    status_reason: str = ""
    bias_open_paths: list = field(default_factory=list)


@dataclass
class DAGSpec:
    nodes: list
    edges: list
    primitives: list
    confounders: list
    outcome_node: str


# ============================================================
# NORMALIZATION
# ============================================================


def _single_study_to_model(study: Study) -> StudyModel:
    moment = Moment(
        variable=study.treatment,
        beta_hat=study.beta_hat,
        se=study.se,
        role="hero",
    )
    return StudyModel(
        name=study.name,
        outcome=study.outcome,
        estimator=study.estimator,
        controls=copy.deepcopy(study.controls),
        moments=[moment],
        node_map=copy.deepcopy(study.node_map),
        cluster_id=study.name,
    )


def normalize_inputs(studies: list) -> Tuple[List[StudyModel], List[Moment]]:
    """
    Convert a mixed list of v1 Study or v2 StudyModel into canonical StudyModel + Moment objects.
    """
    study_models: List[StudyModel] = []
    all_moments: List[Moment] = []

    for item in studies:
        if isinstance(item, Study):
            model = _single_study_to_model(item)
        elif isinstance(item, StudyModel):
            model = copy.deepcopy(item)
        else:
            raise TypeError(f"Unsupported study input type: {type(item)}")

        if model.cluster_id is None:
            model.cluster_id = model.name

        controls_unique = list(dict.fromkeys(model.controls))
        model.controls = controls_unique

        for m in model.moments:
            m.treatment = m.variable
            m.outcome = model.outcome
            m.node_map = copy.deepcopy(model.node_map)
            m.study_name = model.name
            m.cluster_id = model.cluster_id
            m.estimator = model.estimator
            # controls are the full table conditioning set EXCEPT the coefficient itself
            m.controls = [c for c in controls_unique if c != m.variable]
            all_moments.append(m)

        study_models.append(model)

    return study_models, all_moments


# ============================================================
# DAG HELPERS
# ============================================================


def build_nx_graph(dag: DAGSpec) -> nx.DiGraph:
    G = nx.DiGraph()
    G.add_nodes_from(dag.nodes)
    for e in dag.edges:
        if not e.hard_zero:
            G.add_edge(e.source, e.target, sign=e.sign, hard_zero=e.hard_zero)
    return G


def get_all_paths(G: nx.DiGraph, source: str, target: str) -> list:
    try:
        return list(nx.all_simple_paths(G, source, target))
    except (nx.NetworkXError, nx.NodeNotFound):
        return []


def get_backdoor_paths(G: nx.DiGraph, treatment: str, outcome: str, confounders: list) -> list:
    backdoors = []
    for conf in confounders:
        paths_to_treatment = get_all_paths(G, conf, treatment)
        paths_to_outcome = get_all_paths(G, conf, outcome)
        if paths_to_treatment and paths_to_outcome:
            for p1 in paths_to_treatment:
                for p2 in paths_to_outcome:
                    backdoors.append(
                        {
                            "confounder": conf,
                            "path_to_treatment": p1,
                            "path_to_outcome": p2,
                        }
                    )
    return backdoors


def is_path_blocked(path: list, controls: list) -> bool:
    return any(node in controls for node in path[1:])


def get_causal_paths_edges(G: nx.DiGraph, treatment_node: str, outcome_node: str) -> list:
    paths = get_all_paths(G, treatment_node, outcome_node)
    edge_paths = []
    for path in paths:
        edge_path = [(path[i], path[i + 1]) for i in range(len(path) - 1)]
        edge_paths.append(edge_path)
    return edge_paths


# ============================================================
# CLASSIFICATION
# ============================================================


def classify_moment(moment: Moment, dag: DAGSpec, G: nx.DiGraph) -> Moment:
    treatment_node = moment.node_override or moment.node_map.get(moment.treatment, moment.treatment)
    outcome_node = moment.node_map.get(moment.outcome, moment.outcome)

    if moment.admissibility not in {"candidate", "valid"}:
        moment.status = "excluded"
        moment.status_reason = f"Excluded by admissibility tag: {moment.admissibility}"
        return moment

    if treatment_node not in dag.nodes:
        moment.status = "heretic"
        moment.status_reason = f"Treatment node '{treatment_node}' not in DAG"
        return moment

    if outcome_node not in dag.nodes:
        moment.status = "heretic"
        moment.status_reason = f"Outcome node '{outcome_node}' not in DAG"
        return moment

    if moment.estimator.lower() == "ols":
        moment.status = "heretic"
        moment.status_reason = "OLS estimator — cannot convert to hazard/logit-style moment"
        return moment

    causal_paths = get_all_paths(G, treatment_node, outcome_node)
    mediators = set()
    for path in causal_paths:
        mediators.update(path[1:-1])

    mapped_controls = [moment.node_map.get(c, c) for c in moment.controls]
    controlled_mediators = sorted({ctrl for ctrl in mapped_controls if ctrl in mediators})

    if controlled_mediators:
        moment.status = "complicated"
        moment.status_reason = f"Controls for mediator(s): {controlled_mediators}"
        return moment

    backdoors = get_backdoor_paths(G, treatment_node, outcome_node, dag.confounders)
    open_backdoors = []
    for bd in backdoors:
        confounder = bd["confounder"]
        if confounder in mapped_controls:
            continue
        full_path = bd["path_to_treatment"] + bd["path_to_outcome"][1:]
        if not is_path_blocked(full_path, mapped_controls):
            open_backdoors.append(bd)

    if open_backdoors:
        moment.status = "sinner"
        moment.status_reason = f"{len(open_backdoors)} open backdoor path(s)"
        moment.bias_open_paths = open_backdoors
    else:
        moment.status = "saint"
        moment.status_reason = "All backdoor paths blocked"

    return moment


# Backwards-compatible alias
classify_study = classify_moment


# ============================================================
# FORWARD MAP
# ============================================================


def build_edge_index(dag: DAGSpec) -> dict:
    idx = {}
    i = 0
    for edge in dag.edges:
        if not edge.hard_zero:
            idx[(edge.source, edge.target)] = i
            i += 1
    return idx


def forward_map_saint(alpha: np.ndarray, moment: Moment, dag: DAGSpec, G: nx.DiGraph, edge_index: dict) -> float:
    treatment_node = moment.node_override or moment.node_map.get(moment.treatment, moment.treatment)
    outcome_node = moment.node_map.get(moment.outcome, moment.outcome)
    edge_paths = get_causal_paths_edges(G, treatment_node, outcome_node)

    total_effect = 0.0
    for edge_path in edge_paths:
        path_product = 1.0
        for (src, tgt) in edge_path:
            idx = edge_index.get((src, tgt))
            if idx is None:
                path_product = 0.0
                break
            path_product *= alpha[idx]
        total_effect += path_product
    return total_effect


def forward_map_sinner(alpha: np.ndarray, moment: Moment, dag: DAGSpec, G: nx.DiGraph, edge_index: dict) -> float:
    causal_effect = forward_map_saint(alpha, moment, dag, G, edge_index)

    bias = 0.0
    for bd in moment.bias_open_paths:
        conf_to_treat = 1.0
        for i in range(len(bd["path_to_treatment"]) - 1):
            src, tgt = bd["path_to_treatment"][i], bd["path_to_treatment"][i + 1]
            idx = edge_index.get((src, tgt))
            if idx is None:
                conf_to_treat = 0.0
                break
            conf_to_treat *= alpha[idx]

        conf_to_outcome = 1.0
        for i in range(len(bd["path_to_outcome"]) - 1):
            src, tgt = bd["path_to_outcome"][i], bd["path_to_outcome"][i + 1]
            idx = edge_index.get((src, tgt))
            if idx is None:
                conf_to_outcome = 0.0
                break
            conf_to_outcome *= alpha[idx]

        bias += conf_to_treat * conf_to_outcome

    return causal_effect + bias


def forward_map(alpha: np.ndarray, moment: Moment, dag: DAGSpec, G: nx.DiGraph, edge_index: dict) -> float:
    if moment.status == "saint":
        return forward_map_saint(alpha, moment, dag, G, edge_index)
    if moment.status == "sinner":
        return forward_map_sinner(alpha, moment, dag, G, edge_index)
    raise ValueError(f"Cannot compute forward map for {moment.status} moment")


# ============================================================
# OPTIMIZER
# ============================================================


def _cluster_weights(kosher_moments: List[Moment]) -> Dict[str, float]:
    counts: Dict[str, int] = {}
    for m in kosher_moments:
        counts[m.cluster_id] = counts.get(m.cluster_id, 0) + 1
    return {cid: 1.0 / n for cid, n in counts.items()}


def build_loss(moments: list, dag: DAGSpec, G: nx.DiGraph, edge_index: dict, lambda_ridge: float = 0.01) -> callable:
    kosher = [m for m in moments if m.status in ("saint", "sinner")]
    cluster_w = _cluster_weights(kosher)

    def loss(alpha):
        total = 0.0
        for moment in kosher:
            se = max(moment.se, 1e-8)
            weight = cluster_w[moment.cluster_id] * (1.0 / (se ** 2))
            predicted = forward_map(alpha, moment, dag, G, edge_index)
            total += weight * (moment.beta_hat - predicted) ** 2
        total += lambda_ridge * np.sum(alpha ** 2)
        return total

    return loss


def apply_constraints(dag: DAGSpec, edge_index: dict) -> list:
    n = len(edge_index)
    bounds = [(None, None)] * n
    for edge in dag.edges:
        if edge.hard_zero:
            continue
        idx = edge_index.get((edge.source, edge.target))
        if idx is None:
            continue
        if edge.sign == 1:
            bounds[idx] = (0.0, None)
        elif edge.sign == -1:
            bounds[idx] = (None, 0.0)
        else:
            bounds[idx] = (None, None)
    return bounds


def run_optimizer(moments: list, dag: DAGSpec, G: nx.DiGraph, edge_index: dict, lambda_ridge: float = 0.01, n_restarts: int = 5):
    loss_fn = build_loss(moments, dag, G, edge_index, lambda_ridge)
    bounds = apply_constraints(dag, edge_index)
    n_params = len(edge_index)

    best_result = None
    best_loss = np.inf
    for _ in range(n_restarts):
        x0 = np.zeros(n_params)
        for edge in dag.edges:
            if edge.hard_zero:
                continue
            idx = edge_index.get((edge.source, edge.target))
            if idx is None:
                continue
            if edge.sign == 1:
                x0[idx] = np.random.uniform(0.05, 0.8)
            elif edge.sign == -1:
                x0[idx] = np.random.uniform(-0.8, -0.05)
            else:
                x0[idx] = np.random.uniform(-0.5, 0.5)

        result = minimize(
            loss_fn,
            x0,
            method="L-BFGS-B",
            bounds=bounds,
            options={"maxiter": 10000, "ftol": 1e-12},
        )
        if result.fun < best_loss:
            best_loss = result.fun
            best_result = result
    return best_result


# ============================================================
# IDENTIFICATION DIAGNOSTICS
# ============================================================


def compute_jacobian(alpha: np.ndarray, moments: list, dag: DAGSpec, G: nx.DiGraph, edge_index: dict, eps: float = 1e-6) -> np.ndarray:
    kosher = [m for m in moments if m.status in ("saint", "sinner")]
    n_moments = len(kosher)
    n_params = len(edge_index)
    J = np.zeros((n_moments, n_params))

    for j in range(n_params):
        alpha_plus = alpha.copy()
        alpha_minus = alpha.copy()
        alpha_plus[j] += eps
        alpha_minus[j] -= eps
        for k, moment in enumerate(kosher):
            f_plus = forward_map(alpha_plus, moment, dag, G, edge_index)
            f_minus = forward_map(alpha_minus, moment, dag, G, edge_index)
            J[k, j] = (f_plus - f_minus) / (2 * eps)
    return J


def identification_diagnostics(alpha: np.ndarray, moments: list, dag: DAGSpec, G: nx.DiGraph, edge_index: dict) -> dict:
    J = compute_jacobian(alpha, moments, dag, G, edge_index)
    _, s, _ = svd(J, full_matrices=False)

    rank = int(np.sum(s > 1e-6))
    n_params = len(edge_index)
    kosher = [m for m in moments if m.status in ("saint", "sinner")]
    n_moments = len(kosher)
    n_clusters = len({m.cluster_id for m in kosher})
    col_norms = np.linalg.norm(J, axis=0)
    idx_to_edge = {v: k for k, v in edge_index.items()}

    param_id_status = {}
    for j in range(n_params):
        edge = idx_to_edge[j]
        param_id_status[edge] = "point-identified" if col_norms[j] > 1e-4 else "weakly-identified"

    return {
        "n_params": n_params,
        "n_moments": n_moments,
        "n_clusters": n_clusters,
        "jacobian_rank": rank,
        "condition_number": float(s[0] / s[-1]) if len(s) and s[-1] > 1e-10 else np.inf,
        "singular_values": s.tolist(),
        "param_identification": param_id_status,
        "is_identified": rank >= n_params,
    }


# ============================================================
# UNCERTAINTY ESTIMATION
# ============================================================


def bootstrap_uncertainty(study_models: list, dag: DAGSpec, G: nx.DiGraph, edge_index: dict, alpha_star: np.ndarray, n_bootstrap: int = 200, lambda_ridge: float = 0.01) -> np.ndarray:
    """
    Cluster bootstrap by study/model, not raw coefficient.
    """
    kosher_models = []
    for model in study_models:
        kept = [m for m in model.moments if m.status in ("saint", "sinner")]
        if kept:
            cloned = copy.deepcopy(model)
            cloned.moments = kept
            kosher_models.append(cloned)

    if not kosher_models:
        return np.array([alpha_star])

    boot_alphas = []
    for _ in range(n_bootstrap):
        sampled_models = [copy.deepcopy(kosher_models[i]) for i in np.random.choice(len(kosher_models), len(kosher_models), replace=True)]
        sampled_moments = [m for model in sampled_models for m in model.moments]
        try:
            result = run_optimizer(sampled_moments, dag, G, edge_index, lambda_ridge=lambda_ridge, n_restarts=2)
            if result.success or result.fun < 1.0:
                boot_alphas.append(result.x)
        except Exception:
            continue

    return np.array(boot_alphas) if boot_alphas else np.array([alpha_star])


# ============================================================
# MAIN ENGINE
# ============================================================


class GodsDagEngine:
    def __init__(self, dag: DAGSpec, studies: list, lambda_ridge: float = 0.01, n_bootstrap: int = 200):
        self.dag = dag
        self.original_inputs = studies
        self.lambda_ridge = lambda_ridge
        self.n_bootstrap = n_bootstrap
        self.G = build_nx_graph(dag)
        self.edge_index = build_edge_index(dag)
        self.study_models, self.moments = normalize_inputs(studies)
        self.results = None

    def run(self):
        print("=" * 60)
        print("GOD'S DAG ENGINE — RAO CORP (v2)")
        print("=" * 60)

        print("\n[1] CLASSIFYING MOMENTS")
        print("-" * 40)
        for moment in self.moments:
            classify_moment(moment, self.dag, self.G)
            icon = {"saint": "✓", "sinner": "~", "complicated": "!", "heretic": "✗", "excluded": "-"}.get(moment.status, "?")
            print(f"  {icon} {moment.study_name} :: {moment.variable}: {moment.status.upper()} — {moment.status_reason}")

        kosher = [m for m in self.moments if m.status in ("saint", "sinner")]
        dropped = [m for m in self.moments if m.status not in ("saint", "sinner")]
        print(f"\n  Raw moments:      {len(self.moments)}")
        print(f"  Kosher moments:   {len(kosher)}")
        print(f"  Study clusters:   {len({m.cluster_id for m in kosher})}")
        print(f"  Dropped moments:  {len(dropped)}")
        print(f"  Unknowns:         {len(self.edge_index)}")

        if not kosher:
            print("  ERROR: No kosher moments. Check mappings and admissibility.")
            return None

        print("\n[2] RUNNING JOINT OPTIMIZER")
        print("-" * 40)
        result = run_optimizer(kosher, self.dag, self.G, self.edge_index, self.lambda_ridge)
        alpha_star = result.x
        print(f"  Converged: {result.success}  |  Final loss: {result.fun:.6f}")

        print("\n[3] IDENTIFICATION DIAGNOSTICS")
        print("-" * 40)
        diag = identification_diagnostics(alpha_star, kosher, self.dag, self.G, self.edge_index)
        print(f"  Unknowns:       {diag['n_params']}")
        print(f"  Moments:        {diag['n_moments']}")
        print(f"  Clusters:       {diag['n_clusters']}")
        print(f"  Jacobian rank:  {diag['jacobian_rank']}")
        print(f"  Condition #:    {diag['condition_number']:.2f}")
        print(f"  Identified:     {'YES' if diag['is_identified'] else 'NO — set-identified'}")
        for edge, status in diag["param_identification"].items():
            print(f"    {edge[0]} → {edge[1]}: {status}")

        print(f"\n[4] BOOTSTRAP UNCERTAINTY ({self.n_bootstrap} samples)")
        print("-" * 40)
        boot_alphas = bootstrap_uncertainty(
            self.study_models,
            self.dag,
            self.G,
            self.edge_index,
            alpha_star,
            self.n_bootstrap,
            self.lambda_ridge,
        )

        idx_to_edge = {v: k for k, v in self.edge_index.items()}
        edge_results = {}
        for j, (src, tgt) in idx_to_edge.items():
            mean_boot = np.mean(boot_alphas[:, j]) if len(boot_alphas) > 1 else alpha_star[j]
            se_boot = np.std(boot_alphas[:, j]) if len(boot_alphas) > 1 else np.nan
            ci_lo = np.percentile(boot_alphas[:, j], 2.5) if len(boot_alphas) > 1 else np.nan
            ci_hi = np.percentile(boot_alphas[:, j], 97.5) if len(boot_alphas) > 1 else np.nan
            edge_results[(src, tgt)] = {
                "alpha_star": alpha_star[j],
                "boot_mean": mean_boot,
                "boot_se": se_boot,
                "ci_95": (ci_lo, ci_hi),
            }

        reason_counts: Dict[str, int] = {}
        for m in dropped:
            reason_counts[m.status] = reason_counts.get(m.status, 0) + 1

        self.results = {
            "alpha_star": alpha_star,
            "edge_results": edge_results,
            "diagnostics": diag,
            "optimizer": result,
            "moment_classifications": {
                f"{m.study_name}::{m.variable}": {"status": m.status, "reason": m.status_reason}
                for m in self.moments
            },
            "counts": {
                "raw_moments": len(self.moments),
                "kosher_moments": len(kosher),
                "dropped_moments": len(dropped),
                "study_clusters": len({m.cluster_id for m in kosher}),
                "drop_reasons": reason_counts,
            },
        }

        print("\n[5] RECOVERED STRUCTURAL PARAMETERS")
        print("-" * 40)
        for (src, tgt), res in edge_results.items():
            ci_lo, ci_hi = res["ci_95"]
            print(f"  α({src} → {tgt}): {res['alpha_star']:+.4f}  [95% CI: {ci_lo:+.4f}, {ci_hi:+.4f}]")

        print("\n" + "=" * 60)
        print("DONE.")
        return self.results

    def predict_conflict_probability(self, covariate_values: dict, base_rate: float = 0.04) -> dict:
        if self.results is None:
            raise RuntimeError("Run engine.run() first.")

        alpha_star = self.results["alpha_star"]
        log_odds_shift = 0.0
        for node, value in covariate_values.items():
            if node == self.dag.outcome_node:
                continue
            paths = get_all_paths(self.G, node, self.dag.outcome_node)
            for path in paths:
                path_effect = value
                for i in range(len(path) - 1):
                    src, tgt = path[i], path[i + 1]
                    idx = self.edge_index.get((src, tgt))
                    if idx is None:
                        path_effect = 0.0
                        break
                    path_effect *= alpha_star[idx]
                log_odds_shift += path_effect

        base_log_odds = np.log(base_rate / (1 - base_rate))
        final_log_odds = base_log_odds + log_odds_shift
        predicted_prob = 1 / (1 + np.exp(-final_log_odds))
        return {
            "base_rate": base_rate,
            "log_odds_shift": log_odds_shift,
            "predicted_probability": predicted_prob,
            "covariate_values": covariate_values,
        }
