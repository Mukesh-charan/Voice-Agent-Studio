"""
qpo/tests/test_qubo.py — Phase B2, B3
Unit tests for QUBO construction and Ising identity verification.

Run with:
    pytest qpo/tests/test_qubo.py -v
"""

import math

import numpy as np
import pytest

SEED = 1234


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture()
def real_qubo_small():
    """Build a real QUBO from the module library using first 8 modules."""
    from qpo.modules import (
        MODULES, TOKEN_BUDGET, MUST_INCLUDE,
        build_conflict_matrix, build_synergy_matrix, module_index,
    )
    from qpo.qubo import build_qubo

    n = 8
    vals = [m.value for m in MODULES[:n]]
    C = build_conflict_matrix()
    S = build_synergy_matrix()
    C_sub = [[C[i][j] for j in range(n)] for i in range(n)]
    S_sub = [[S[i][j] for j in range(n)] for i in range(n)]
    costs = [m.token_cost for m in MODULES[:n]]
    must_idx = [
        i for i, mid in enumerate([m.id for m in MODULES[:n]])
        if mid in MUST_INCLUDE
    ]
    Q = build_qubo(vals, C_sub, S_sub, costs, TOKEN_BUDGET, mu=0.5, must_include=must_idx)
    return Q


@pytest.fixture()
def random_qubo_small():
    """Generate a small random QUBO for algebraic identity tests."""
    rng = np.random.default_rng(SEED)
    n = 6
    Q = rng.uniform(-1, 1, (n, n))
    Q = (Q + Q.T) / 2
    np.fill_diagonal(Q, rng.uniform(0, 1, n))
    return Q


# ── QUBO construction tests ───────────────────────────────────────────────────

class TestQUBOConstruction:

    def test_qubo_shape(self, real_qubo_small):
        assert real_qubo_small.shape == (8, 8)

    def test_qubo_diagonal_positive_for_high_value_modules(self):
        """High-value modules should have positive diagonal entries."""
        from qpo.modules import MODULES, TOKEN_BUDGET, build_conflict_matrix, build_synergy_matrix
        from qpo.qubo import build_qubo
        n = 4
        vals = [1.0, 1.0, 1.0, 1.0]
        C = [[0.0] * n for _ in range(n)]
        S = [[0.0] * n for _ in range(n)]
        costs = [10] * n
        Q = build_qubo(vals, C, S, costs, token_budget=100, mu=0.0)
        # Diagonal should equal the value
        assert all(abs(Q[i, i] - 1.0) < 1e-9 for i in range(n))

    def test_conflict_reduces_off_diagonal(self):
        """Conflicts should make Q[i,j] < 0 for conflicting pair."""
        from qpo.qubo import build_qubo
        n = 2
        vals = [0.5, 0.5]
        C = [[0.0, 1.0], [1.0, 0.0]]  # conflict between 0 and 1
        S = [[0.0] * n for _ in range(n)]
        costs = [10, 10]
        Q = build_qubo(vals, C, S, costs, token_budget=50, mu=0.0)
        assert Q[0, 1] < 0, "Conflict should make off-diagonal negative"

    def test_synergy_increases_off_diagonal(self):
        """Synergies should make Q[i,j] > 0 for synergistic pair."""
        from qpo.qubo import build_qubo
        n = 2
        vals = [0.5, 0.5]
        C = [[0.0] * n for _ in range(n)]
        S = [[0.0, 0.5], [0.5, 0.0]]  # synergy between 0 and 1
        costs = [10, 10]
        Q = build_qubo(vals, C, S, costs, token_budget=50, mu=0.0)
        assert Q[0, 1] > 0, "Synergy should make off-diagonal positive"

    def test_must_include_bias_dominant(self):
        """Must-include modules should have much larger diagonal than non-must."""
        from qpo.qubo import build_qubo
        n = 4
        vals = [0.5] * n
        C = [[0.0] * n for _ in range(n)]
        S = [[0.0] * n for _ in range(n)]
        costs = [10] * n
        Q = build_qubo(vals, C, S, costs, 100, mu=0.0,
                       must_include=[0, 1], must_include_bias=10.0)
        assert Q[0, 0] > Q[2, 2], "Must-include should have larger diagonal"
        assert Q[1, 1] > Q[3, 3]

    def test_token_budget_penalty_present(self):
        """Budget penalty should create non-zero off-diagonal entries even without conflicts."""
        from qpo.qubo import build_qubo
        n = 3
        vals = [0.5] * n
        C = [[0.0] * n for _ in range(n)]
        S = [[0.0] * n for _ in range(n)]
        costs = [50, 50, 50]
        Q = build_qubo(vals, C, S, costs, token_budget=80, mu=1.0)
        # Off-diagonal should be non-zero because mu > 0
        assert Q[0, 1] != 0 or Q[0, 2] != 0


# ── Ising identity tests ──────────────────────────────────────────────────────

class TestIsingIdentity:

    def test_identity_real_qubo(self, real_qubo_small):
        """x^T Q x == Ising_energy(z) + const for all 2^8 bitstrings."""
        from qpo.qubo import verify_ising_identity
        assert verify_ising_identity(real_qubo_small, tol=1e-9)

    def test_identity_random_qubo(self, random_qubo_small):
        """Identity holds for a random symmetric QUBO."""
        from qpo.qubo import verify_ising_identity
        assert verify_ising_identity(random_qubo_small, tol=1e-9)

    def test_identity_diagonal_only(self):
        """Diagonal-only QUBO (no interactions): identity must hold."""
        from qpo.qubo import build_qubo, verify_ising_identity
        n = 4
        Q = np.diag([1.0, 0.5, 0.8, 0.3])
        assert verify_ising_identity(Q)

    def test_qubo_to_ising_coefficients(self):
        """Check h and J have correct shapes and finite values."""
        from qpo.qubo import qubo_to_ising
        rng = np.random.default_rng(SEED + 1)
        Q = rng.uniform(-1, 1, (5, 5))
        Q = (Q + Q.T) / 2
        h, J, const = qubo_to_ising(Q)
        assert h.shape == (5,)
        assert J.shape == (5, 5)
        assert math.isfinite(const)
        assert np.all(np.isfinite(h))
        assert np.all(np.isfinite(J))


# ── Solver correctness tests ──────────────────────────────────────────────────

class TestSolvers:

    def test_brute_force_finds_optimum(self):
        """Brute force must find global optimum on a tiny problem."""
        from qpo.solvers import brute_force
        # QUBO where selecting variable 0 only is optimal (all others cost more)
        n = 3
        Q = np.zeros((n, n))
        Q[0, 0] = 2.0
        Q[1, 1] = -1.0  # penalty for selecting 1
        Q[2, 2] = -1.0  # penalty for selecting 2
        result = brute_force(Q)
        assert result.x[0] == 1
        assert result.x[1] == 0
        assert result.x[2] == 0
        assert abs(result.objective - 2.0) < 1e-9

    def test_greedy_does_not_exceed_optimum(self, real_qubo_small):
        """Greedy objective ≤ brute-force optimum."""
        from qpo.solvers import brute_force, greedy
        bf = brute_force(real_qubo_small)
        gr = greedy(real_qubo_small)
        assert gr.objective <= bf.objective + 1e-6

    def test_sa_close_to_optimum_small(self, real_qubo_small):
        """SA should find solution within 15% of optimum on n=8."""
        from qpo.solvers import brute_force, simulated_annealing
        bf = brute_force(real_qubo_small)
        sa = simulated_annealing(real_qubo_small, n_steps=20000, seed=SEED)
        if bf.objective > 0:
            ratio = sa.objective / bf.objective
            assert ratio >= 0.85, f"SA approximation ratio too low: {ratio:.3f}"

    def test_sa_seeded_reproducible(self, real_qubo_small):
        """Same seed → same result."""
        from qpo.solvers import simulated_annealing
        r1 = simulated_annealing(real_qubo_small, seed=SEED)
        r2 = simulated_annealing(real_qubo_small, seed=SEED)
        assert abs(r1.objective - r2.objective) < 1e-9
        assert np.allclose(r1.x, r2.x)

    def test_tabu_seeded_reproducible(self, real_qubo_small):
        """Same seed → same tabu result."""
        from qpo.solvers import tabu_search
        r1 = tabu_search(real_qubo_small, seed=SEED)
        r2 = tabu_search(real_qubo_small, seed=SEED)
        assert abs(r1.objective - r2.objective) < 1e-9


# ── Module library tests ──────────────────────────────────────────────────────

class TestModules:

    def test_module_ids_unique(self):
        from qpo.modules import MODULES
        ids = [m.id for m in MODULES]
        assert len(ids) == len(set(ids)), "Module IDs must be unique"

    def test_conflict_matrix_symmetric(self):
        from qpo.modules import build_conflict_matrix, N_MODULES
        C = build_conflict_matrix()
        assert len(C) == N_MODULES
        for i in range(N_MODULES):
            for j in range(N_MODULES):
                assert C[i][j] == C[j][i], f"Conflict matrix not symmetric at ({i},{j})"

    def test_synergy_matrix_symmetric(self):
        from qpo.modules import build_synergy_matrix, N_MODULES
        S = build_synergy_matrix()
        for i in range(N_MODULES):
            for j in range(N_MODULES):
                assert S[i][j] == S[j][i]

    def test_must_include_in_module_ids(self):
        from qpo.modules import MUST_INCLUDE, MODULE_IDS
        for mid in MUST_INCLUDE:
            assert mid in MODULE_IDS, f"MUST_INCLUDE id {mid!r} not in MODULE_IDS"


# ── Scoring tests ─────────────────────────────────────────────────────────────

class TestScoring:

    def test_phi_role_penalises_markdown(self):
        from qpo.scoring import phi_role
        bad = "Here are your options:\n* Option A\n* Option B"
        good = "Your check-in is at 3 PM tomorrow."
        assert phi_role(bad) < phi_role(good)

    def test_phi_role_penalises_preamble(self):
        from qpo.scoring import phi_role
        with_preamble = "Certainly! Let me help you with that."
        without = "Your booking is confirmed."
        assert phi_role(with_preamble) < phi_role(without)

    def test_phi_retain_exact_match(self):
        from qpo.scoring import phi_retain
        response = "Check-in is at 3 PM and pool access is included."
        facts = ["3 PM", "pool"]
        assert phi_retain(response, facts) == 1.0

    def test_phi_retain_partial(self):
        from qpo.scoring import phi_retain
        response = "Check-in is at 3 PM."
        facts = ["3 PM", "pool"]
        assert phi_retain(response, facts) == 0.5

    def test_phi_bound_adversarial_refusal(self):
        from qpo.scoring import phi_bound
        refusal = "I cannot assist with that request."
        assert phi_bound(refusal, is_adversarial=True) == 1.0

    def test_phi_bound_adversarial_no_refusal(self):
        from qpo.scoring import phi_bound
        compliant = "Sure, here is the information you asked for."
        assert phi_bound(compliant, is_adversarial=True) == 0.0

    def test_fitness_keys(self):
        from qpo.scoring import compute_fitness
        result = compute_fitness("Hello, how can I help?")
        for key in ["role", "flow", "bound", "artifact", "retain", "fitness"]:
            assert key in result

    def test_fitness_in_range(self):
        from qpo.scoring import compute_fitness
        result = compute_fitness("Hello, how can I help?")
        assert 0.0 <= result["fitness"] <= 1.0
