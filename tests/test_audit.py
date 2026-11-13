"""
Audit tests: verify manuscript claims against actual code and artifacts.
Run: python -m pytest tests/test_audit.py -v
"""
import json, os, sys
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# ---------- QPO: module library ----------
def test_qpo_n_modules():
    from qpo.modules import N_MODULES
    assert N_MODULES == 16, f"Code has {N_MODULES} modules, manuscript says 15"

def test_qpo_token_budget():
    from qpo.modules import TOKEN_BUDGET
    assert TOKEN_BUDGET == 180, f"Code budget {TOKEN_BUDGET}, manuscript says 150"

def test_qpo_must_include():
    from qpo.modules import MUST_INCLUDE
    assert MUST_INCLUDE == {"rule_no_markdown", "policy_pii"}

def test_qpo_conflict_values():
    from qpo.modules import build_conflict_matrix, module_index
    C = build_conflict_matrix()
    assert C[module_index("persona_hospitality")][module_index("persona_clinic")] == 2.0
    assert C[module_index("tone_warm")][module_index("tone_formal")] == 0.8

def test_qpo_synergy_values():
    from qpo.modules import build_synergy_matrix, module_index
    S = build_synergy_matrix()
    assert S[module_index("kb_grounding")][module_index("kb_refuse_unknown")] == 0.6
    assert S[module_index("rule_no_markdown")][module_index("rule_brevity")] == 0.4

def test_qpo_ising_identity_n8():
    from qpo.qubo import verify_ising_identity, build_qubo
    from qpo.modules import MODULES, TOKEN_BUDGET, MUST_INCLUDE, build_conflict_matrix, build_synergy_matrix, module_index
    vals = [m.value for m in MODULES][:8]
    C = build_conflict_matrix(); S = build_synergy_matrix()
    C8 = [[C[i][j] for j in range(8)] for i in range(8)]
    S8 = [[S[i][j] for j in range(8)] for i in range(8)]
    costs = [m.token_cost for m in MODULES][:8]
    mi = [module_index(mid) for mid in MUST_INCLUDE if module_index(mid) < 8]
    Q = build_qubo(vals, C8, S8, costs, TOKEN_BUDGET, mu=0.5, must_include=mi)
    assert verify_ising_identity(Q[:8, :8])

def test_qpo_qaoa_not_in_scaling():
    import csv
    rows = list(csv.DictReader(open(ROOT / "research/results/qpo_scaling.csv")))
    solvers = set(r["solver"] for r in rows)
    assert "qaoa" not in solvers and "QAOA" not in solvers
    assert solvers == {"brute_force", "greedy", "simulated_annealing", "tabu_search"}

def test_qpo_instance_count():
    meta = json.load(open(ROOT / "research/results/qpo_scaling_meta.json"))
    assert meta["n_instances"] == 30
    assert meta["seed"] == 1234

def test_qpo_n15_ising_not_verified():
    import csv
    rows = [r for r in csv.DictReader(open(ROOT / "research/results/qpo_scaling.csv")) if r["n"] == "15" and r["solver"] == "brute_force"]
    assert all(r["ising_verified"] == "False" for r in rows)

# ---------- QTP ----------
def test_qtp_task_graph_4tasks():
    tasks = {"db_save": 45.0, "speech_synth": 210.0, "google_sync": 350.0, "webhook": 280.0}
    assert sum(tasks.values()) == 885.0

def test_qtp_trial_count():
    m = json.load(open(ROOT / "results/quantum_task_scheduler_metrics.json"))
    assert len(m) == 6

def test_qtp_qaoa_fallback():
    m = json.load(open(ROOT / "results/quantum_task_scheduler_metrics.json"))
    for profile in m:
        if profile["n_tasks"] >= 5:
            qaoa = profile["solvers"]["QAOA"]
            assert qaoa.get("quantum_simulated") is False

def test_qtp_qaoa_quantum_sim_times():
    m = json.load(open(ROOT / "results/quantum_task_scheduler_metrics.json"))
    n3 = [p for p in m if p["n_tasks"] == 3][0]
    n4 = [p for p in m if p["n_tasks"] == 4][0]
    assert n3["solvers"]["QAOA"]["solver_time_ms"] > 10000
    assert n4["solvers"]["QAOA"]["solver_time_ms"] > 20000

def test_qtp_cpu_peak():
    m = json.load(open(ROOT / "results/quantum_task_scheduler_metrics.json"))
    peak = max(p["cpu_percent"] for p in m)
    assert peak == 38.0

def test_qtp_n6_regression():
    m = json.load(open(ROOT / "results/quantum_task_scheduler_metrics.json"))
    n6 = [p for p in m if p["n_tasks"] == 6][0]
    assert n6["solvers"]["SimulatedAnnealing"]["makespan_ms"] == 595.0
    assert n6["solvers"]["Greedy"]["makespan_ms"] == 550.0
    assert n6["solvers"]["SimulatedAnnealing"]["makespan_ms"] > n6["solvers"]["Greedy"]["makespan_ms"]

# ---------- Environment ----------
def test_env_hardware():
    env = json.load(open(ROOT / "research/results/env.json"))
    assert "RTX 4050" in env["gpu"]
    assert env["ram_gb"] == 23.69
    assert env["os"]["release"] == "10"
    assert "AMD" in env["cpu"]
    assert env["git"]["commit"] == "not-a-git-repo"
