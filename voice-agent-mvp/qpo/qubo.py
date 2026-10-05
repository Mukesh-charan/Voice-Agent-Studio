"""
qpo/qubo.py — Phase B1, B2
Builds the QUBO matrix Q for modular prompt assembly and converts it to
Ising (h, J, const) with a verified bijection.

Objective (maximise, so QUBO is negated for minimisation):
    F(x) = Σ_i v_i x_i
          - Σ_{i<j} c_ij x_i x_j      # conflict penalties
          + Σ_{i<j} s_ij x_i x_j      # synergy bonuses
          - mu * (Σ_i t_i x_i - T)^2  # token-budget soft penalty

The QUBO matrix Q encodes this as  x^T Q x  (upper-triangular convention).

Ising conversion uses x_i = (1 - z_i) / 2 (z_i ∈ {-1, +1}).
Verified by unit test: for all 2^n bitstrings (n ≤ 12),
    x^T Q x == Ising_energy(z) + const   (to 1e-9 tolerance)
"""

from __future__ import annotations

import numpy as np
from typing import Optional


SEED = 1234


# ── QUBO builder ──────────────────────────────────────────────────────────────

def build_qubo(
    values: list[float],
    conflicts: list[list[float]],
    synergies: list[list[float]],
    token_costs: list[int],
    token_budget: int,
    mu: float = 0.5,
    must_include: Optional[list[int]] = None,
    must_include_bias: float = 10.0,
) -> np.ndarray:
    """
    Build the QUBO matrix Q (n×n, upper-triangular convention) such that
    the objective x^T Q x is maximised when x encodes the best module set.

    Sign convention: Q is NEGATIVE of the minimisation problem (we maximise).
    Diagonal Q[i][i] = value for x_i; off-diagonal Q[i][j] = interaction.

    Args:
        values:        module base values v_i
        conflicts:     c_ij conflict matrix (penalty when both selected)
        synergies:     s_ij synergy matrix (bonus when both selected)
        token_costs:   t_i token cost per module
        token_budget:  T soft target token budget
        mu:            weight on the quadratic token penalty term
        must_include:  list of module indices with large positive bias
        must_include_bias: additional value added to diagonal for must-include modules

    Returns:
        Q: (n, n) numpy array (upper-triangular QUBO for maximisation)
    """
    n = len(values)
    Q = np.zeros((n, n), dtype=float)

    # ── Linear terms: value bias ──────────────────────────────────────────────
    for i in range(n):
        Q[i, i] += values[i]

    # ── Must-include modules: large diagonal bias ─────────────────────────────
    if must_include:
        for i in must_include:
            Q[i, i] += must_include_bias

    # ── Conflict penalties (off-diagonal, subtracted) ─────────────────────────
    for i in range(n):
        for j in range(i + 1, n):
            if conflicts[i][j] != 0:
                Q[i, j] -= conflicts[i][j]

    # ── Synergy bonuses (off-diagonal, added) ─────────────────────────────────
    for i in range(n):
        for j in range(i + 1, n):
            if synergies[i][j] != 0:
                Q[i, j] += synergies[i][j]

    # ── Token budget soft penalty: -mu*(Σ t_i x_i - T)^2 ────────────────────
    # Expand: -mu*(Σ t_i x_i)^2 + 2*mu*T*(Σ t_i x_i) - mu*T^2
    # Since x_i^2 = x_i:
    #   diagonal += -mu*t_i^2 + 2*mu*T*t_i
    #   off-diagonal Q[i,j] -= 2*mu*t_i*t_j   (i<j, upper triangle)
    t = np.array(token_costs, dtype=float)
    for i in range(n):
        Q[i, i] += -mu * t[i] ** 2 + 2 * mu * token_budget * t[i]
    for i in range(n):
        for j in range(i + 1, n):
            Q[i, j] -= 2 * mu * t[i] * t[j]

    return Q


def qubo_energy(Q: np.ndarray, x: np.ndarray) -> float:
    """Evaluate the QUBO objective x^T Q x for a binary vector x."""
    return float(x @ Q @ x)


# ── QUBO → Ising conversion (B2, corrected) ──────────────────────────────────

def qubo_to_ising(Q: np.ndarray) -> tuple[np.ndarray, np.ndarray, float]:
    """
    Convert a QUBO matrix Q (upper-triangular) to Ising (h, J, const).

    Q is upper-triangular: x^T Q x = Σ_i Q[i,i]*x_i + Σ_{i<j} Q[i,j]*x_i*x_j

    Substitution:  x_i = (1 - z_i) / 2,  z_i ∈ {-1, +1}

    Diagonal term (x_i^2 = x_i for binary x_i):
        Q[i,i] * x_i = Q[i,i] * (1-z_i)/2
        Contributes:  Q[i,i]/2  to const,  -Q[i,i]/2  to h_i

    Off-diagonal term:
        Q[i,j] * x_i*x_j = Q[i,j] * (1-z_i)(1-z_j)/4
                          = Q[i,j]/4 * (1 - z_i - z_j + z_i z_j)
        Contributes:  Q[i,j]/4  to const,
                     -Q[i,j]/4  to h_i AND h_j,
                     +Q[i,j]/4  to J[i,j]

    Ising energy convention: E(z) = Σ_i h_i z_i + Σ_{i<j} J_ij z_i z_j

    Resulting coefficients (for upper-triangular input Q):
        h_i   = -Q[i,i]/2 - Σ_{j>i} Q[i,j]/4 - Σ_{j<i} Q[j,i]/4
        J_ij  = Q[i,j]/4        (i < j, upper triangle)
        const = Σ_i Q[i,i]/2 + Σ_{i<j} Q[i,j]/4

    Verification: x^T Q x = E(z) + const  ∀ x ∈ {0,1}^n
    """
    n = Q.shape[0]
    # Project to upper-triangular: combine lower triangle into upper.
    # For off-diagonal pairs (i<j): effective Q_ij = Q[i,j] + Q[j,i]
    # Diagonal stays as-is (Q[i,i]).
    Q_up = np.zeros((n, n), dtype=float)
    for i in range(n):
        Q_up[i, i] = Q[i, i]
        for j in range(i + 1, n):
            Q_up[i, j] = Q[i, j] + Q[j, i]

    h = np.zeros(n, dtype=float)
    J = np.zeros((n, n), dtype=float)

    # Diagonal contribution: Q_up[i,i] * x_i = Q_up[i,i] * (1-z_i)/2
    for i in range(n):
        h[i] -= Q_up[i, i] / 2.0

    # Off-diagonal contribution (upper triangle)
    for i in range(n):
        for j in range(i + 1, n):
            if Q_up[i, j] != 0:
                h[i] -= Q_up[i, j] / 4.0
                h[j] -= Q_up[i, j] / 4.0
                J[i, j] = Q_up[i, j] / 4.0

    # Constant
    const = 0.0
    for i in range(n):
        const += Q_up[i, i] / 2.0
    for i in range(n):
        for j in range(i + 1, n):
            const += Q_up[i, j] / 4.0

    return h, J, const





def ising_energy(h: np.ndarray, J: np.ndarray, z: np.ndarray) -> float:
    """
    Compute Ising energy: E(z) = Σ_i h_i z_i + Σ_{i<j} J[i,j] z_i z_j
    z ∈ {-1, +1}^n
    """
    n = len(z)
    linear = float(h @ z)
    quad = 0.0
    for i in range(n):
        for j in range(i + 1, n):
            quad += J[i, j] * z[i] * z[j]
    return linear + quad



def verify_ising_identity(Q: np.ndarray, tol: float = 1e-9) -> bool:
    """
    Brute-force verification: for all 2^n bitstrings (n ≤ 12),
    assert x^T Q x == Ising_energy(z) + const to within tol.

    Returns True if identity holds for all bitstrings, raises AssertionError otherwise.
    """
    n = Q.shape[0]
    assert n <= 12, f"Too many variables for brute-force verification: n={n}"
    h, J, const = qubo_to_ising(Q)

    for bits in range(2 ** n):
        x = np.array([(bits >> i) & 1 for i in range(n)], dtype=float)
        z = 1 - 2 * x  # x_i=0 -> z_i=1, x_i=1 -> z_i=-1

        qubo_val = qubo_energy(Q, x)
        ising_val = ising_energy(h, J, z) + const

        assert abs(qubo_val - ising_val) < tol, (
            f"Ising identity FAILED at bits={bits:0{n}b}: "
            f"QUBO={qubo_val:.6f}, Ising+const={ising_val:.6f}"
        )
    return True


# ── Quick self-test ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    from qpo.modules import (
        MODULES, N_MODULES, TOKEN_BUDGET, MUST_INCLUDE,
        build_conflict_matrix, build_synergy_matrix, module_index,
    )

    values = [m.value for m in MODULES]
    conflicts = build_conflict_matrix()
    synergies = build_synergy_matrix()
    token_costs = [m.token_cost for m in MODULES]
    must_idx = [module_index(mid) for mid in MUST_INCLUDE]

    Q = build_qubo(values, conflicts, synergies, token_costs, TOKEN_BUDGET,
                   mu=0.5, must_include=must_idx)

    print(f"QUBO shape: {Q.shape}")
    print(f"Diagonal range: [{Q.diagonal().min():.3f}, {Q.diagonal().max():.3f}]")

    # Verify Ising identity on a small sub-problem (first 8 modules)
    Q_small = Q[:8, :8]
    ok = verify_ising_identity(Q_small)
    print(f"Ising identity verification (n=8): {'PASS' if ok else 'FAIL'}")
    print("QUBO builder self-test complete.")
    sys.exit(0)
