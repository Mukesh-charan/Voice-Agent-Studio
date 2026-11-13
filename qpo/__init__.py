# qpo/__init__.py
"""
QPO: Quantum Prompt Optimization package.

Sub-modules:
  modules   — prompt module library, conflict/synergy matrices
  scoring   — shared fitness evaluation (Phi_role, Phi_flow, Phi_bound, Phi_artifact, Phi_retain)
  qubo      — QUBO matrix builder + QUBO/Ising conversion with identity verification
  solvers   — brute_force, greedy, simulated_annealing, tabu_search, numpy_eigensolver, qaoa
  assemble  — binary vector -> prompt string
  optimizer — ScheduleOptimizer interface + ClassicalOptimizer + QAOAOptimizer adapters
  run_all   — end-to-end scaling study script
"""

from qpo.modules import MODULES, N_MODULES, PromptModule, get_module
from qpo.scoring import compute_fitness, score_module_selection
from qpo.qubo import build_qubo, qubo_to_ising, verify_ising_identity
from qpo.assemble import assemble_prompt, assemble_from_ids
from qpo.optimizer import (
    ScheduleOptimizer, ClassicalOptimizer, QAOAOptimizer,
    SchedulingProblem, SchedulingSolution,
    scores_to_qubo, validate_solution,
)
from qpo.task_parallelizer import (
    QuantumTaskParallelizer, TaskDefinition, ParallelStage,
    QuantumScheduleResult, dispatch_quantum_parallel_booking,
)

__all__ = [
    "MODULES", "N_MODULES", "PromptModule", "get_module",
    "compute_fitness", "score_module_selection",
    "build_qubo", "qubo_to_ising", "verify_ising_identity",
    "assemble_prompt", "assemble_from_ids",
    "ScheduleOptimizer", "ClassicalOptimizer", "QAOAOptimizer",
    "SchedulingProblem", "SchedulingSolution",
    "scores_to_qubo", "validate_solution",
    "QuantumTaskParallelizer", "TaskDefinition", "ParallelStage",
    "QuantumScheduleResult", "dispatch_quantum_parallel_booking",
]
