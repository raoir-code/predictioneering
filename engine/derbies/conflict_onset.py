"""
conflict_onset.py — importable derby (v3)

Used by pipeline/run_derby.py via: import conflict_onset as derby
Exposes: results (GodsDagEngine.run() output)

For interactive use, open conflict_onset.ipynb in JupyterLab instead.
To change the DAG or swap studies: edit studies/conflict_onset_studies.json.
Do not hardcode anything in this file.
"""

import json, importlib, numpy as np, sys, os
sys.path.insert(0, os.path.expanduser('~/predictioneering/engine'))

import gods_dag_v2
importlib.reload(gods_dag_v2)
from gods_dag_v2 import DAGSpec, Edge, StudyModel, Moment, GodsDagEngine

np.random.seed(42)

BASE = os.path.expanduser('~/predictioneering')

with open(f'{BASE}/studies/conflict_onset_studies.json') as f:
    ROSTER = json.load(f)
with open(f'{BASE}/library/hazard_library_v4.json') as f:
    HLIB = json.load(f)

# ── Aliases ───────────────────────────────────────────────────────────────────
ALIASES = {
    'jointdemo': 'joint democracy', 'democratic dyad': 'joint democracy',
    'both democracies': 'joint democracy', 'democracy low': 'democracy (low)',
    'lower of democracy scores': 'democracy (low)',
    'allied': 'alliance', 'ally': 'alliance', 'allies': 'alliance',
    'joint alliance': 'alliance', 'countries are allied': 'alliance',
    'defense pact': 'alliance', 'defensive alliance t-1': 'alliance',
    'capabilities ratio': 'capability ratio',
    'capability ratio (log)': 'log capability ratio',
    'ln(capability ratio)': 'log capability ratio',
    'capratio': 'capability ratio', 'relative capabilities': 'relative capabilities',
    'log trade': 'log trade', 'trade dependency': 'trade dependence',
    'dependencyl': 'trade dependence',
    'territorial disputes': 'territorial dispute', 'territory': 'territorial dispute',
    'territorial rivalry (strategic)': 'territorial rivalry strategic',
    'expected shift in the distribution of power': 'expected power shift',
    'systemic diff.': 'systemic difference',
    's score': 's-score', 'dyadic s-score': 's-score',
    'similarity in foreign policy interests': 'foreign policy similarity',
    'democracyl': 'democracy',
    'brevity of peace (5-year half-life)': 'brevity of peace',
    "target's polity": 'target polity',
}

def canon(x):
    if x is None: return x
    x = x.strip().lower()
    return ALIASES.get(x, x)

# ── Build DAGSpec ─────────────────────────────────────────────────────────────
dag = DAGSpec(
    nodes=ROSTER['dag_nodes'],
    edges=[Edge(e['from'], e['to'], sign=e['sign'], initial_value=e['initial_value'])
           for e in ROSTER['dag_edges']],
    primitives=ROSTER['primitives'],
    confounders=ROSTER['confounders'],
    outcome_node=ROSTER['outcome_node'],
)

# ── Build StudyModels ─────────────────────────────────────────────────────────
study_models = []
for s in ROSTER['studies']:
    name = s['study_name']
    if name not in HLIB:
        print(f'[WARN] Study not in library: {name} — skipping')
        continue
    entry = HLIB[name]
    node_map = {canon(k): v for k, v in s['node_map'].items()}
    node_map['Conflict'] = 'Conflict'
    moments = []
    for hv in s['hero_vars']:
        if hv not in entry['variables']:
            print(f'[WARN] Hero var "{hv}" not in {name} — skipping')
            continue
        v = entry['variables'][hv]
        moments.append(Moment(variable=canon(v['variable_name']),
                              beta_hat=float(v['beta']), se=float(v['se']),
                              role='hero', admissibility='candidate'))
    for em in s.get('extra_moments', []):
        if em['var'] not in entry['variables']: continue
        v = entry['variables'][em['var']]
        moments.append(Moment(variable=canon(v['variable_name']),
                              beta_hat=float(v['beta']), se=float(v['se']),
                              role=em.get('role', 'control'), admissibility='candidate',
                              note=em.get('note', '')))
    study_models.append(StudyModel(
        name=name, outcome='Conflict', estimator=s.get('estimator', 'cox'),
        controls=[canon(c) for c in entry['conditioning_set']],
        node_map=node_map, moments=moments))

# ── Run engine — results exposed at module level for run_derby.py ─────────────
engine = GodsDagEngine(dag=dag, studies=study_models, lambda_ridge=0.001, n_bootstrap=100)
results = engine.run()
