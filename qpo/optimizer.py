"""
qpo/optimizer.py — ScheduleOptimizer interface + concrete adapters.

Implements the plan's §6 interface:
    optimize(problem, timeout) -> solution
    validate(solution, problem) -> bool
    get_solver_metadata() -> dict

Adapters:
  ClassicalOptimizer  — SA → tabu cascade, always available
  QAOAOptimizer       — Qiskit QAOA, optional; falls back to classical on failure/timeout
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

import numpy as np


# ── Problem / Solution types ──────────────────────────────────────────────────

@dataclass
class SchedulingProblem:
    """
    A one-hot selection problem encoded as a QUBO matrix.
    For prompt selection: n candidates, Q encodes their relative scores.
    constraint: exactly one variable must be 1 (one-hot).
    """
    Q: np.ndarray          # (n, n) QUBO — maximisation form
    n: int
    labels: list[str] = field(default_factory=list)


@dataclass
class SchedulingSolution:
    x: np.ndarray          # binary assignment vector
    objective: float
    solver_used: str
    wall_time_s: float
    quantum_hardware_used: bool = False
    fallback_reason: Optional[str] = None
    metadata: dict = field(default_factory=dict)


# ── Validator ─────────────────────────────────────────────────────────────────

def validate_solution(sol: SchedulingSolution, prob: SchedulingProblem) -> tuple[bool, str]:
    """
    Validates assignments per plan §6:
    - x ∈ {0, 1}^n
    - One-hot: exactly one variable is 1
    - len(x) matches problem n
    Returns (is_valid, reason).
    """
    x = sol.x
    if len(x) != prob.n:
        return False, f"Length mismatch: got {len(x)}, expected {prob.n}"
    if not all(v in (0.0, 1.0) for v in x):
        return False, f"Non-binary values in solution: {x}"
    ones = int(np.sum(x))
    if ones != 1:
        return False, f"One-hot violated: {ones} variables are 1 (expected exactly 1)"
    return True, "ok"


# ── Base interface ─────────────────────────────────────────────────────────────

class ScheduleOptimizer:
    def optimize(self, problem: SchedulingProblem, timeout: float = 5.0) -> SchedulingSolution:
        raise NotImplementedError

    def validate(self, solution: SchedulingSolution, problem: SchedulingProblem) -> tuple[bool, str]:
        return validate_solution(solution, problem)

    def get_solver_metadata(self) -> dict:
        raise NotImplementedError


# ── Classical baseline ────────────────────────────────────────────────────────

class ClassicalOptimizer(ScheduleOptimizer):
    """
    SA → tabu cascade. Guaranteed classical fallback; never fails.
    For one-hot problems SA/tabu naturally converge to argmax,
    but we enforce one-hot via post-processing argmax if needed.
    """

    def optimize(self, problem: SchedulingProblem, timeout: float = 5.0) -> SchedulingSolution:
        from qpo.solvers import simulated_annealing, tabu_search

        t0 = time.perf_counter()
        # Try SA first
        try:
            res = simulated_annealing(problem.Q, n_steps=5_000)
        except Exception:
            res = None

        # Try tabu if SA failed or timeout breached
        if res is None or (time.perf_counter() - t0) > timeout:
            try:
                res = tabu_search(problem.Q, n_iter=1_000)
            except Exception:
                res = None

        # Final fallback: pure argmax of diagonal (always O(n))
        if res is None:
            idx = int(np.argmax(np.diag(problem.Q)))
            x = np.zeros(problem.n, dtype=float)
            x[idx] = 1.0
            return SchedulingSolution(
                x=x,
                objective=float(problem.Q[idx, idx]),
                solver_used="argmax_fallback",
                wall_time_s=time.perf_counter() - t0,
                fallback_reason="SA and tabu both failed",
            )

        # Enforce one-hot: pick argmax of x @ Q @ x contribution per variable
        raw_x = res.x
        idx = int(np.argmax(raw_x)) if raw_x.sum() > 0 else int(np.argmax(np.diag(problem.Q)))
        x = np.zeros(problem.n, dtype=float)
        x[idx] = 1.0

        return SchedulingSolution(
            x=x,
            objective=float(x @ problem.Q @ x),
            solver_used=res.solver,
            wall_time_s=time.perf_counter() - t0,
            metadata=res.metadata,
        )

    def get_solver_metadata(self) -> dict:
        return {"provider": "classical", "solvers": ["simulated_annealing", "tabu_search", "argmax"]}


# ── QAOA / Qiskit adapter ─────────────────────────────────────────────────────

class QAOAOptimizer(ScheduleOptimizer):
    """
    Qiskit QAOA statevector adapter. Falls back to ClassicalOptimizer on any
    import error, timeout, or invalid result — never crashes the calling code.
    """

    def __init__(self, p: int = 1, shots: int = 512, maxiter: int = 30):
        self.p = p
        self.shots = shots
        self.maxiter = maxiter
        self._classical = ClassicalOptimizer()

    def optimize(self, problem: SchedulingProblem, timeout: float = 10.0) -> SchedulingSolution:
        from qpo.solvers import qaoa as _qaoa

        t0 = time.perf_counter()
        try:
            res = _qaoa(problem.Q, p=self.p, shots=self.shots, maxiter=self.maxiter)
            elapsed = time.perf_counter() - t0

            # Reject obviously bad results
            if res.objective == float("-inf") or "error" in res.metadata:
                raise RuntimeError(res.metadata.get("error", "QAOA returned -inf"))

            # Enforce one-hot
            raw_x = res.x
            idx = int(np.argmax(raw_x)) if raw_x.sum() > 0 else int(np.argmax(np.diag(problem.Q)))
            x = np.zeros(problem.n, dtype=float)
            x[idx] = 1.0
            sol = SchedulingSolution(
                x=x,
                objective=float(x @ problem.Q @ x),
                solver_used=res.solver,
                wall_time_s=elapsed,
                quantum_hardware_used=False,  # statevector simulation
                metadata={**res.metadata, "success_prob": res.success_prob},
            )

            # Validate before returning
            ok, reason = validate_solution(sol, problem)
            if not ok:
                raise RuntimeError(f"QAOA solution invalid: {reason}")

            return sol

        except Exception as e:
            print(f"[QAOA] falling back to classical: {e}")
            sol = self._classical.optimize(problem, timeout=max(1.0, timeout - (time.perf_counter() - t0)))
            sol.fallback_reason = str(e)
            return sol

    def validate(self, solution: SchedulingSolution, problem: SchedulingProblem) -> tuple[bool, str]:
        return validate_solution(solution, problem)

    def get_solver_metadata(self) -> dict:
        return {
            "provider": "qiskit_statevector",
            "algorithm": "QAOA",
            "p": self.p,
            "shots": self.shots,
            "quantum_hardware_used": False,
            "note": "Statevector simulation — not real QPU",
        }


# ── Convenience: build a one-hot QUBO from raw scores ────────────────────────

def scores_to_qubo(scores: list[float]) -> SchedulingProblem:
    """
    Converts a list of scalar scores into a diagonal QUBO for one-hot selection.
    Negative off-diagonal terms encode the one-hot constraint as a penalty.
    Q[i,i] = score[i] + penalty_diag, Q[i,j] = -penalty for i≠j.

    We use a simple diagonal QUBO since SA/QAOA enforce one-hot via post-processing
    anyway, and the diagonal encodes the objective exactly.
    """
    n = len(scores)
    Q = np.zeros((n, n), dtype=float)
    mn = min(scores) if scores else 0.0
    shifted = [s - mn for s in scores]  # shift to non-negative
    for i in range(n):
        Q[i, i] = shifted[i]
    # Mild pairwise penalty to discourage selecting multiple (helps SA converge)
    penalty = max(max(shifted) * 0.1, 1e-3) if shifted else 1e-3
    for i in range(n):
        for j in range(i + 1, n):
            Q[i, j] = -penalty
    return SchedulingProblem(Q=Q, n=n, labels=[])
