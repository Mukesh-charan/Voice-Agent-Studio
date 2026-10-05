"""
qpo/run_all.py — Phase B3, B4
Master script that runs the full QPO evaluation pipeline:
  1. Build the QUBO from module library
  2. Verify Ising identity (unit test embedded)
  3. Solver scaling study: sweep n in {8, 12, 16} and 30 random instances
  4. Write results/qpo_scaling.csv
  5. Generate figures/qpo_gap_vs_n.pdf and figures/qpo_time_vs_n.pdf

Usage:
    python -m qpo.run_all
"""

from __future__ import annotations

import csv
import json
import random
import sys
import time
from pathlib import Path

import numpy as np

SEED = 1234
rng = np.random.default_rng(SEED)
rng_py = random.Random(SEED)

RESULTS_DIR = Path(__file__).parent.parent / "research" / "results"
FIGURES_DIR = Path(__file__).parent.parent / "research" / "figures"


def _make_random_qubo(n: int, seed: int) -> np.ndarray:
    """Generate a random symmetric QUBO of size n for benchmarking."""
    local_rng = np.random.default_rng(seed)
    Q = local_rng.uniform(-1, 1, (n, n))
    Q = (Q + Q.T) / 2  # symmetrize
    # Make diagonal dominant-ish for typical structure
    np.fill_diagonal(Q, local_rng.uniform(0.2, 1.5, n))
    return Q


def run_scaling_study(n_sizes: list[int], n_instances: int, solvers_to_run: list[str]) -> list[dict]:
    """Sweep problem sizes and collect solver statistics."""
    from qpo.solvers import brute_force, greedy, simulated_annealing, tabu_search

    from qpo.modules import (
        MODULES, TOKEN_BUDGET, MUST_INCLUDE,
        build_conflict_matrix, build_synergy_matrix, module_index,
    )
    from qpo.qubo import build_qubo, verify_ising_identity

    rows = []

    for n in n_sizes:
        print(f"\n=== n={n} ===")
        for inst in range(n_instances):
            instance_seed = SEED + n * 1000 + inst

            if n <= len(MODULES):
                # Use a sub-problem of the real module library
                idx = list(range(n))
                vals = [MODULES[i].value for i in idx]
                C = build_conflict_matrix()
                S = build_synergy_matrix()
                C_sub = [[C[i][j] for j in idx] for i in idx]
                S_sub = [[S[i][j] for j in idx] for i in idx]
                costs = [MODULES[i].token_cost for i in idx]
                must_idx = [ii for ii, mid in enumerate([MODULES[i].id for i in idx])
                            if mid in MUST_INCLUDE]
                Q = build_qubo(vals, C_sub, S_sub, costs, TOKEN_BUDGET,
                               mu=0.5, must_include=must_idx)
            else:
                # Random synthetic instance
                Q = _make_random_qubo(n, instance_seed)

            # Ising identity check (only for small n to keep runtime reasonable)
            ising_ok = False
            if n <= 12:
                try:
                    from qpo.qubo import verify_ising_identity
                    ising_ok = verify_ising_identity(Q[:min(n, 12), :min(n, 12)])
                except Exception:
                    ising_ok = False

            # Ground truth
            bf = brute_force(Q[:min(n, 20), :min(n, 20)]) if n <= 20 else None
            opt_obj = bf.objective if bf else None

            solver_map = {
                "brute_force": lambda: brute_force(Q[:min(n, 20), :min(n, 20)]) if n <= 20 else None,
                "greedy": lambda: greedy(Q),
                "simulated_annealing": lambda: simulated_annealing(Q, seed=instance_seed),
                "tabu_search": lambda: tabu_search(Q, seed=instance_seed),
            }

            for solver_name in solvers_to_run:
                if solver_name not in solver_map:
                    continue
                if solver_name == "brute_force" and n > 20:
                    continue  # too slow

                try:
                    res = solver_map[solver_name]()
                    if res is None:
                        continue
                except Exception as e:
                    print(f"  {solver_name} FAILED: {e}")
                    continue

                gap = None
                approx_ratio = None
                if opt_obj is not None and opt_obj != 0:
                    gap = opt_obj - res.objective
                    approx_ratio = res.objective / opt_obj if opt_obj > 0 else None

                row = {
                    "n": n,
                    "instance": inst,
                    "solver": solver_name,
                    "objective": round(res.objective, 6),
                    "optimum": round(opt_obj, 6) if opt_obj is not None else "",
                    "gap": round(gap, 6) if gap is not None else "",
                    "approx_ratio": round(approx_ratio, 4) if approx_ratio is not None else "",
                    "wall_time_s": round(res.wall_time_s, 6),
                    "ising_verified": ising_ok if solver_name == "brute_force" else "",
                    "seed": instance_seed,
                }
                rows.append(row)
                print(f"  {solver_name:22s}  obj={res.objective:8.4f}  "
                      f"gap={gap or 0:.4f}  t={res.wall_time_s:.3f}s")

    return rows


def write_csv(rows: list[dict], path: Path) -> None:
    if not rows:
        print("No rows to write.")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[run_all] Written {path}")


def make_figures(rows: list[dict]) -> None:
    """Generate gap and timing plots."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("[run_all] matplotlib not installed — skipping figures")
        return

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    import collections
    solvers = sorted(set(r["solver"] for r in rows))
    n_sizes = sorted(set(r["n"] for r in rows))

    # Group by (solver, n) -> list of approx_ratios / wall times
    gap_data: dict = collections.defaultdict(list)
    time_data: dict = collections.defaultdict(list)
    for r in rows:
        key = (r["solver"], r["n"])
        if r["gap"] != "":
            gap_data[key].append(float(r["gap"]))
        time_data[key].append(float(r["wall_time_s"]))

    # Figure 1: Gap vs n
    fig, ax = plt.subplots(figsize=(7, 4))
    for solver in solvers:
        xs, ys, errs = [], [], []
        for n in n_sizes:
            vals = gap_data.get((solver, n), [])
            if vals:
                xs.append(n)
                ys.append(float(np.mean(vals)))
                errs.append(float(np.std(vals)))
        if xs:
            ax.errorbar(xs, ys, yerr=errs, label=solver, marker="o", capsize=4)
    ax.set_xlabel("Problem size n")
    ax.set_ylabel("Optimality gap (optimum − solver obj)")
    ax.set_title("QPO Solver Optimality Gap vs Problem Size")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "qpo_gap_vs_n.pdf")
    plt.close(fig)
    print(f"[run_all] Written {FIGURES_DIR / 'qpo_gap_vs_n.pdf'}")

    # Figure 2: Wall time vs n
    fig, ax = plt.subplots(figsize=(7, 4))
    for solver in solvers:
        xs, ys = [], []
        for n in n_sizes:
            vals = time_data.get((solver, n), [])
            if vals:
                xs.append(n)
                ys.append(float(np.mean(vals)))
        if xs:
            ax.plot(xs, ys, label=solver, marker="s")
    ax.set_xlabel("Problem size n")
    ax.set_ylabel("Wall time (s)")
    ax.set_title("QPO Solver Wall Time vs Problem Size")
    ax.set_yscale("log")
    ax.legend()
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "qpo_time_vs_n.pdf")
    plt.close(fig)
    print(f"[run_all] Written {FIGURES_DIR / 'qpo_time_vs_n.pdf'}")


def main() -> None:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)

    print("=== QPO Scaling Study ===")
    print(f"SEED={SEED}")

    # n_sizes: keep small for feasibility without a real QPU
    n_sizes = [8, 12, 15]  # expandable to 16, 20, 24 when QAOA is added
    n_instances = 30
    solvers_to_run = ["brute_force", "greedy", "simulated_annealing", "tabu_search"]

    rows = run_scaling_study(n_sizes, n_instances, solvers_to_run)

    csv_path = RESULTS_DIR / "qpo_scaling.csv"
    write_csv(rows, csv_path)
    make_figures(rows)

    # Write a summary JSON too
    summary = {
        "seed": SEED,
        "n_sizes": n_sizes,
        "n_instances": n_instances,
        "solvers": solvers_to_run,
        "total_rows": len(rows),
    }
    (RESULTS_DIR / "qpo_scaling_meta.json").write_text(
        json.dumps(summary, indent=2), encoding="utf-8"
    )
    print("\n=== Done ===")


if __name__ == "__main__":
    main()
