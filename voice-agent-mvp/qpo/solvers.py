"""
qpo/solvers.py — Phase B3
All solvers for the QUBO / Ising problem:

  1. brute_force       — exact optimum (ground truth) for n ≤ 24
  2. greedy            — add best marginal gain
  3. simulated_annealing — seeded SA (own implementation)
  4. tabu_search       — seeded tabu
  5. numpy_eigensolver — exact via NumPy (labelled "exact eigensolver")
  6. qaoa              — Qiskit QAOA + COBYLA, Aer statevector (n ≤ 20)

Each solver returns a SolverResult dataclass.
"""

from __future__ import annotations

import math
import random
import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np

SEED = 1234


# ── Result container ──────────────────────────────────────────────────────────

@dataclass
class SolverResult:
    solver: str
    x: np.ndarray          # binary solution vector
    objective: float       # QUBO objective value (higher = better)
    wall_time_s: float
    gap_to_optimum: Optional[float] = None   # filled in by benchmark
    approx_ratio: Optional[float] = None     # filled in by benchmark
    success_prob: Optional[float] = None     # QAOA: prob of sampling optimum
    metadata: dict = field(default_factory=dict)


def _qubo_obj(Q: np.ndarray, x: np.ndarray) -> float:
    return float(x @ Q @ x)


# ── 1. Brute force ────────────────────────────────────────────────────────────

def brute_force(Q: np.ndarray) -> SolverResult:
    """Exact optimum by exhaustive enumeration. Ground truth for n ≤ 24."""
    n = Q.shape[0]
    assert n <= 24, f"brute_force: n={n} too large (max 24)"
    t0 = time.perf_counter()
    best_x = np.zeros(n, dtype=float)
    best_obj = -math.inf

    for bits in range(2 ** n):
        x = np.array([(bits >> i) & 1 for i in range(n)], dtype=float)
        obj = _qubo_obj(Q, x)
        if obj > best_obj:
            best_obj = obj
            best_x = x.copy()

    return SolverResult(
        solver="brute_force",
        x=best_x,
        objective=best_obj,
        wall_time_s=time.perf_counter() - t0,
    )


# ── 2. Greedy ────────────────────────────────────────────────────────────────

def greedy(Q: np.ndarray) -> SolverResult:
    """Greedy: add variable that gives best marginal improvement, no removal."""
    n = Q.shape[0]
    t0 = time.perf_counter()
    x = np.zeros(n, dtype=float)
    remaining = set(range(n))

    while remaining:
        best_i, best_delta = -1, -math.inf
        for i in remaining:
            x[i] = 1
            delta = _qubo_obj(Q, x) - _qubo_obj(Q, x * (x != x))  # incremental
            # Simpler: just compute full objective
            delta = _qubo_obj(Q, x)
            x[i] = 0
            if delta > best_delta:
                best_delta = delta
                best_i = i
        # Only add if it actually improves
        x_test = x.copy()
        x_test[best_i] = 1
        if _qubo_obj(Q, x_test) > _qubo_obj(Q, x):
            x[best_i] = 1
            remaining.discard(best_i)
        else:
            break  # no more improvement possible

    return SolverResult(
        solver="greedy",
        x=x,
        objective=_qubo_obj(Q, x),
        wall_time_s=time.perf_counter() - t0,
    )


# ── 3. Simulated annealing ────────────────────────────────────────────────────

def simulated_annealing(
    Q: np.ndarray,
    n_steps: int = 10_000,
    T_start: float = 2.0,
    T_end: float = 0.01,
    seed: int = SEED,
) -> SolverResult:
    """Seeded simulated annealing on the QUBO objective."""
    rng = random.Random(seed)
    n = Q.shape[0]
    t0 = time.perf_counter()

    x = np.array([rng.randint(0, 1) for _ in range(n)], dtype=float)
    current_obj = _qubo_obj(Q, x)
    best_x = x.copy()
    best_obj = current_obj

    for step in range(n_steps):
        T = T_start * (T_end / T_start) ** (step / n_steps)
        i = rng.randint(0, n - 1)
        x[i] = 1 - x[i]  # flip
        new_obj = _qubo_obj(Q, x)
        delta = new_obj - current_obj
        if delta > 0 or rng.random() < math.exp(delta / T):
            current_obj = new_obj
            if new_obj > best_obj:
                best_obj = new_obj
                best_x = x.copy()
        else:
            x[i] = 1 - x[i]  # revert

    return SolverResult(
        solver="simulated_annealing",
        x=best_x,
        objective=best_obj,
        wall_time_s=time.perf_counter() - t0,
        metadata={"n_steps": n_steps, "T_start": T_start, "T_end": T_end, "seed": seed},
    )


# ── 4. Tabu search ───────────────────────────────────────────────────────────

def tabu_search(
    Q: np.ndarray,
    n_iter: int = 2_000,
    tabu_tenure: int = 10,
    seed: int = SEED,
) -> SolverResult:
    """Tabu search on the QUBO objective."""
    rng = random.Random(seed)
    n = Q.shape[0]
    t0 = time.perf_counter()

    x = np.array([rng.randint(0, 1) for _ in range(n)], dtype=float)
    best_x = x.copy()
    best_obj = _qubo_obj(Q, x)
    tabu: dict[int, int] = {}  # variable index -> iteration when tabu expires

    for it in range(n_iter):
        # Find best non-tabu flip
        best_i, best_delta = -1, -math.inf
        for i in range(n):
            if tabu.get(i, 0) > it:
                continue
            x[i] = 1 - x[i]
            delta = _qubo_obj(Q, x) - _qubo_obj(Q, x * 0 + (1 - x))
            # Simpler: compute full
            new_obj = _qubo_obj(Q, x)
            delta = new_obj - _qubo_obj(Q, x * (1 if x[i] == 0 else 0) + 0)
            x[i] = 1 - x[i]  # revert
            if new_obj > best_delta:
                best_delta = new_obj
                best_i = i

        if best_i == -1:
            break

        x[best_i] = 1 - x[best_i]
        tabu[best_i] = it + tabu_tenure
        current_obj = _qubo_obj(Q, x)
        if current_obj > best_obj:
            best_obj = current_obj
            best_x = x.copy()

    return SolverResult(
        solver="tabu_search",
        x=best_x,
        objective=best_obj,
        wall_time_s=time.perf_counter() - t0,
        metadata={"n_iter": n_iter, "tabu_tenure": tabu_tenure, "seed": seed},
    )


# ── 5. NumPy exact eigensolver (reference, NOT QAOA) ─────────────────────────

def numpy_eigensolver(Q: np.ndarray) -> SolverResult:
    """
    Exact solution via NumPy eigensolver used as a labelled 'exact eigensolver'
    reference (NOT QAOA). Only valid for small n (≤ 20).
    Uses Qiskit's NumPyMinimumEigensolver under the hood if available.
    Falls back to brute_force otherwise.
    """
    n = Q.shape[0]
    t0 = time.perf_counter()
    try:
        from qiskit_optimization import QuadraticProgram
        from qiskit_algorithms import NumPyMinimumEigensolver
        from qiskit_optimization.algorithms import MinimumEigenOptimizer

        qp = QuadraticProgram()
        for i in range(n):
            qp.binary_var(name=f"x{i}")
        # Convert maximisation QUBO to minimisation (negate)
        Q_min = {(i, j): -float(Q[i, j]) for i in range(n) for j in range(n) if Q[i, j] != 0}
        qp.minimize(quadratic=Q_min)

        solver = MinimumEigenOptimizer(NumPyMinimumEigensolver())
        result = solver.solve(qp)
        x = np.array([result.x[i] for i in range(n)], dtype=float)
        obj = _qubo_obj(Q, x)
        return SolverResult(
            solver="numpy_eigensolver",
            x=x,
            objective=obj,
            wall_time_s=time.perf_counter() - t0,
            metadata={"backend": "qiskit.NumPyMinimumEigensolver"},
        )
    except Exception as e:
        # Fallback to brute force
        res = brute_force(Q)
        res.solver = "numpy_eigensolver_fallback"
        res.wall_time_s = time.perf_counter() - t0
        res.metadata["fallback_reason"] = str(e)
        return res


# ── 6. QAOA ──────────────────────────────────────────────────────────────────

def qaoa(
    Q: np.ndarray,
    p: int = 1,
    shots: int = 1024,
    seed: int = SEED,
    optimizer: str = "COBYLA",
) -> SolverResult:
    """
    Real QAOA via Qiskit + Aer statevector simulator.
    Uses X-mixer (standard). n ≤ 20.

    Returns best sample + success probability (fraction of shots that are optimal).
    NOTE: This uses a QUANTUM SIMULATION, not a real QPU.
    """
    n = Q.shape[0]
    assert n <= 20, f"qaoa: n={n} too large for statevector simulation (max 20)"
    t0 = time.perf_counter()

    try:
        from qiskit_optimization import QuadraticProgram
        from qiskit_algorithms import QAOA
        from qiskit_algorithms.optimizers import COBYLA as CoblayaOpt, SLSQP
        from qiskit_optimization.algorithms import MinimumEigenOptimizer
        from qiskit_optimization.converters import QuadraticProgramToQubo
        from qiskit.primitives import StatevectorSampler

        # Build minimisation QP (negate Q)
        qp = QuadraticProgram()
        for i in range(n):
            qp.binary_var(name=f"x{i}")
        Q_min = {}
        for i in range(n):
            for j in range(n):
                if Q[i, j] != 0:
                    Q_min[(i, j)] = -float(Q[i, j])
        qp.minimize(quadratic=Q_min)

        sampler = StatevectorSampler(seed=seed)
        opt = CoblayaOpt(maxiter=200) if optimizer == "COBYLA" else SLSQP(maxiter=200)
        algo = QAOA(sampler=sampler, optimizer=opt, reps=p, seed=seed)
        meo = MinimumEigenOptimizer(algo)
        result = meo.solve(qp)

        x = np.array([result.x[i] for i in range(n)], dtype=float)
        obj = _qubo_obj(Q, x)

        # Estimate success probability from samples if available
        success_prob = None
        if hasattr(result, "samples"):
            bf_result = brute_force(Q)
            opt_obj = bf_result.objective
            n_success = sum(
                1 for s in result.samples
                if abs(_qubo_obj(Q, np.array([s.x[i] for i in range(n)], dtype=float)) - opt_obj) < 1e-6
            )
            success_prob = n_success / len(result.samples) if result.samples else None

        return SolverResult(
            solver=f"qaoa_p{p}",
            x=x,
            objective=obj,
            wall_time_s=time.perf_counter() - t0,
            success_prob=success_prob,
            metadata={"p": p, "shots": shots, "seed": seed, "optimizer": optimizer,
                      "backend": "qiskit.StatevectorSampler"},
        )

    except ImportError as e:
        # Return a labelled failure so benchmarks can skip gracefully
        return SolverResult(
            solver=f"qaoa_p{p}",
            x=np.zeros(n, dtype=float),
            objective=float("-inf"),
            wall_time_s=time.perf_counter() - t0,
            metadata={"error": f"Qiskit not available: {e}"},
        )
    except Exception as e:
        return SolverResult(
            solver=f"qaoa_p{p}",
            x=np.zeros(n, dtype=float),
            objective=float("-inf"),
            wall_time_s=time.perf_counter() - t0,
            metadata={"error": str(e)},
        )


if __name__ == "__main__":
    rng = np.random.default_rng(SEED)
    n = 6
    Q_test = rng.standard_normal((n, n))
    Q_test = (Q_test + Q_test.T) / 2  # symmetric
    np.fill_diagonal(Q_test, rng.uniform(0, 1, n))

    bf = brute_force(Q_test)
    gr = greedy(Q_test)
    sa = simulated_annealing(Q_test, n_steps=5000)
    tb = tabu_search(Q_test)

    print(f"n={n}  brute_force={bf.objective:.4f}  greedy={gr.objective:.4f}  "
          f"SA={sa.objective:.4f}  tabu={tb.objective:.4f}")
    print("Solvers self-test complete.")
