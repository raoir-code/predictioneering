"""Symbolic indifference verification for finite simultaneous 2x2 games.

Finds an INTERIOR mixed-equilibrium candidate and proves algebraic
indifference identities, not parameter-domain admissibility, existence
throughout parameter space, or a complete equilibrium classification.
"""
from __future__ import annotations

import json
from pathlib import Path
import sys

from .paper_sprint import safe_expr, NAME


def verify(model):
    import sympy as sp
    game = model.get("normal_form_2x2")
    if not isinstance(game, dict):
        raise ValueError("Model lacks an explicit 2x2 normal-form payoff matrix")
    params = model.get("parameters", {})
    if not isinstance(params, dict) or not params:
        raise ValueError("Parameters required")
    for k, typ in params.items():
        if not NAME.fullmatch(k) or typ not in ("real", "positive", "nonnegative"):
            raise ValueError("Unsafe or unspecified game parameter")
    symbols = {k: sp.Symbol(k, real=True, **(
        {"positive": True} if typ == "positive"
        else {"nonnegative": True} if typ == "nonnegative" else {}))
        for k, typ in params.items()}

    def matrix(key):
        raw = game.get(key)
        if not isinstance(raw, list) or len(raw) != 2 or any(
                not isinstance(row, list) or len(row) != 2 for row in raw):
            raise ValueError(key + " requires exactly two rows and two columns")
        return [[safe_expr(x, symbols) for x in row] for row in raw]

    row = matrix("row_payoffs")
    col = matrix("column_payoffs")
    for key in ("row_actions", "column_actions"):
        actions = game.get(key)
        if (not isinstance(actions, list) or len(actions) != 2 or
                not all(isinstance(a, str) and a.strip() for a in actions) or
                actions[0] == actions[1]):
            raise ValueError("Two distinct " + key + " required")
    p, q = sp.symbols("_row_mix _column_mix", real=True)

    # q makes the row player indifferent between first and second row.
    row_difference = sp.expand(q * (row[0][0] - row[1][0]) +
                               (1 - q) * (row[0][1] - row[1][1]))
    # p makes the column player indifferent between first and second column.
    col_difference = sp.expand(p * (col[0][0] - col[0][1]) +
                               (1 - p) * (col[1][0] - col[1][1]))
    q_sol = sp.solve(row_difference, q)
    p_sol = sp.solve(col_difference, p)
    if len(q_sol) != 1 or len(p_sol) != 1:
        raise ValueError("No unique interior mixing candidate under generic parameters")
    q_star, p_star = sp.factor(q_sol[0]), sp.factor(p_sol[0])
    if (sp.simplify(row_difference.subs(q, q_star)) != 0 or
            sp.simplify(col_difference.subs(p, p_star)) != 0):
        raise ValueError("Algebraic indifference identities failed")

    eq = model.get("equilibrium", {})
    if eq.get("choice") != "p":
        raise ValueError("2x2 normal-form adapter requires row attack probability choice p")
    candidate = safe_expr(eq.get("expression"), symbols)
    if sp.simplify(candidate - p_star) != 0:
        raise ValueError("Asserted row-player equilibrium probability disagrees with payoff matrix")
    if game.get("column_mix_probability") is not None:
        claimed_q = safe_expr(game["column_mix_probability"], symbols)
        if sp.simplify(claimed_q - q_star) != 0:
            raise ValueError("Claimed column-player mixing probability disagrees with payoff matrix")

    return {
        "status": "symbolic_indifference_verified_INTERIOR_ADMISSIBILITY_PENDING",
        "row_player_first_action_probability": str(p_star),
        "column_player_first_action_probability": str(q_star),
        "row_player_first_action_probability_latex": sp.latex(p_star),
        "column_player_first_action_probability_latex": sp.latex(q_star),
        "row_indifference_expression": str(row_difference),
        "column_indifference_expression": str(col_difference),
        "algebraic_indifference_identically_zero": True,
        "necessary_interior_conditions": [
            "0 < (" + str(p_star) + ") < 1",
            "0 < (" + str(q_star) + ") < 1",
            "Denominators nonzero and payoffs valid in the entire stated parameter domain"],
        "full_equilibrium_optimality_verified": False,
        "complete_equilibrium_classification_verified": False,
        "holiday_mechanism_empirically_verified": False,
    }


def main(argv=None):
    import argparse
    a = argparse.ArgumentParser(description="Partial symbolic verification of a 2x2 game")
    a.add_argument("model_json", type=Path)
    args = a.parse_args(argv)
    try:
        result = verify(json.loads(args.model_json.read_text(encoding="utf-8")))
        print(json.dumps(result, indent=2))
        return 0
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print("Two-by-two model audit stopped safely: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
