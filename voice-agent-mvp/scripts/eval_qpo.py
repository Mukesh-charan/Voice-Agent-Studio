"""
scripts/eval_qpo.py — Phase B4
================================
Evaluates QPO solver outputs against the ground-truth eval dataset.

Usage:
    python scripts/eval_qpo.py \
        --data research/data/eval_prompts.jsonl \
        --out research/results/qpo_eval.json

What it does:
  1. For each QPO variant in the dataset, assembles the prompt string.
  2. Runs the RULE-BASED Phi scorers from qpo/scoring.py against each turn.
  3. Computes Mean Absolute Error vs. the labelled phi_* values.
  4. Compares greedy vs SA vs tabu solver outputs (using build_qubo + fixed seed).
  5. Writes JSON summary and a PDF radar chart.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_data(path: Path) -> list:
    if not path.exists():
        print(f"[eval_qpo] Data not found at {path}")
        return []
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    return raw.get("turns", [])


def _score_turn(variant: str, role: str, content: str) -> dict:
    """Score a single turn using the rule-based Phi scorers.

    Signatures (from qpo/scoring.py):
        phi_role(response: str) -> float
        phi_flow(response: str, booking_fields: list | None = None) -> float
        phi_bound(response: str, is_adversarial: bool = False) -> float
        phi_artifact(response: str) -> float
        phi_retain(response: str, gold_facts: list | None = None) -> float
    """
    from qpo.scoring import phi_role, phi_flow, phi_bound, phi_artifact, phi_retain
    # Extract booking fields from variant name for phi_flow
    booking_fields = [v.strip() for v in variant.split("+") if v.strip()]
    scores = {
        "phi_role":     phi_role(content),
        "phi_flow":     phi_flow(content, booking_fields=booking_fields),
        "phi_bound":    phi_bound(content),
        "phi_artifact": phi_artifact(content),
        "phi_retain":   phi_retain(content),
    }
    return scores


def _mae(predicted: dict, expected: dict) -> float:
    keys = [k for k in expected if k in predicted]
    if not keys:
        return 0.0
    return statistics.mean(abs(predicted[k] - expected[k]) for k in keys)


def _compare_solvers() -> dict:
    """Run all solvers on the QPO QUBO and compare their selected module sets."""
    from qpo.modules import (
        MODULE_IDS, MODULES, N_MODULES, TOKEN_BUDGET,
        build_conflict_matrix, build_synergy_matrix,
    )
    from qpo.qubo import build_qubo
    from qpo.solvers import brute_force, greedy, simulated_annealing, tabu_search

    n = N_MODULES
    values = [m.value for m in MODULES]
    costs  = [m.token_cost for m in MODULES]
    C = build_conflict_matrix()
    S = build_synergy_matrix()
    Q = build_qubo(values, C, S, costs, token_budget=TOKEN_BUDGET, mu=0.5)

    import numpy as np
    results = {}
    solver_list = [
        ("greedy", greedy,             {"Q": Q}),
        ("sa",     simulated_annealing, {"Q": Q, "seed": 42, "n_steps": 2000, "T_start": 2.0, "T_end": 0.01}),
        ("tabu",   tabu_search,         {"Q": Q, "seed": 42, "n_iter": 500, "tabu_tenure": 5}),
    ]
    # brute_force only feasible for small n
    if n <= 20:
        solver_list.insert(0, ("brute_force", brute_force, {"Q": Q}))

    for name, fn, kwargs in solver_list:
        try:
            result = fn(**kwargs)
            x = result.x
            selected = [MODULE_IDS[i] for i in range(n) if x[i] == 1]
            energy = float(np.array(x) @ Q @ np.array(x))
            results[name] = {
                "modules": selected,
                "n_selected": len(selected),
                "qubo_energy": round(energy, 4),
                "wall_time_s": round(result.wall_time_s, 4),
            }
        except Exception as e:
            results[name] = {"error": str(e)}

    return results




def run(data_path: Path, out_path: Path) -> None:
    turns = _load_data(data_path)
    if not turns:
        print("[eval_qpo] No turns to evaluate. Run with the provided eval_prompts.jsonl.")
        return

    print(f"[eval_qpo] Scoring {len(turns)} turns...")
    maes = []
    per_turn = []
    for t in turns:
        pred = _score_turn(t["variant"], t["role"], t["content"])
        mae = _mae(pred, t["expected"])
        maes.append(mae)
        per_turn.append({"id": t["id"], "variant": t["variant"], "mae": round(mae, 4),
                          "predicted": {k: round(v, 4) for k, v in pred.items()},
                          "expected": t["expected"]})
        print(f"  [{t['id']:3d}] MAE={mae:.3f}  variant={t['variant'][:40]}")

    print(f"\n  Mean MAE over all turns: {statistics.mean(maes):.4f}")

    print("\n[eval_qpo] Comparing solvers...")
    solver_results = _compare_solvers()
    for name, res in solver_results.items():
        if "error" in res:
            print(f"  {name}: ERROR — {res['error']}")
        else:
            print(f"  {name}: {res['n_selected']} modules, energy={res['qubo_energy']}")

    summary = {
        "n_turns": len(turns),
        "mean_mae": round(statistics.mean(maes), 4),
        "per_turn": per_turn,
        "solvers": solver_results,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[eval_qpo] Written -> {out_path}")

    _plot_radar(solver_results)


def _plot_radar(solver_results: dict) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return

    fig_dir = Path(__file__).parent.parent / "research" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    solvers = [k for k, v in solver_results.items() if "error" not in v]
    if not solvers:
        return

    names = solvers
    energies = [solver_results[k]["qubo_energy"] for k in names]
    counts = [solver_results[k]["n_selected"] for k in names]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))
    colors = ["steelblue", "seagreen", "tomato", "orchid"]

    bars = ax1.bar(names, [abs(e) for e in energies], color=colors[:len(names)])
    ax1.bar_label(bars, [f"{e:.2f}" for e in energies], padding=3)
    ax1.set_title("QUBO Energy (lower = better selection)")
    ax1.set_ylabel("|Energy|")
    ax1.grid(True, axis="y", alpha=0.3)

    bars2 = ax2.bar(names, counts, color=colors[:len(names)])
    ax2.bar_label(bars2, padding=3)
    ax2.set_title("Modules Selected by Each Solver")
    ax2.set_ylabel("# Modules")
    ax2.grid(True, axis="y", alpha=0.3)

    fig.suptitle("QPO Solver Comparison", fontsize=13)
    fig.tight_layout()
    out = fig_dir / "qpo_solver_comparison.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"[eval_qpo] Solver comparison chart -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="QPO prompt evaluation")
    ap.add_argument("--data", default="research/data/eval_prompts.jsonl")
    ap.add_argument("--out", default="research/results/qpo_eval.json")
    args = ap.parse_args()
    run(Path(args.data), Path(args.out))


if __name__ == "__main__":
    main()
