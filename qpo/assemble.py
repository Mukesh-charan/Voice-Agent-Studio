"""
qpo/assemble.py — Phase B1
Converts a binary selection vector x (one entry per module) into
the final assembled prompt string.
"""

from __future__ import annotations

import numpy as np

from qpo.modules import MODULES, PromptModule


def assemble_prompt(x: np.ndarray, separator: str = "\n\n") -> str:
    """
    Assemble the final prompt from a binary selection vector x.

    Args:
        x: binary numpy array of length N_MODULES; x[i]=1 means module i is selected
        separator: string inserted between consecutive module texts

    Returns:
        Assembled prompt string.
    """
    selected: list[PromptModule] = [
        MODULES[i] for i in range(len(MODULES)) if i < len(x) and x[i] == 1
    ]
    if not selected:
        return ""
    return separator.join(m.text for m in selected)


def assemble_from_ids(selected_ids: list[str], separator: str = "\n\n") -> str:
    """
    Assemble a prompt from a list of module ID strings.

    Args:
        selected_ids: list of module id strings (e.g. ['persona_hospitality', 'rule_no_markdown'])
        separator: string inserted between consecutive module texts

    Returns:
        Assembled prompt string.
    """
    id_set = set(selected_ids)
    selected = [m for m in MODULES if m.id in id_set]
    return separator.join(m.text for m in selected)


def describe_selection(x: np.ndarray) -> str:
    """Return a human-readable summary of the selected modules."""
    lines = ["Selected modules:"]
    total_tokens = 0
    for i, m in enumerate(MODULES):
        if i < len(x) and x[i] == 1:
            lines.append(f"  ✓ {m.id:30s}  cost={m.token_cost:3d}  value={m.value:.2f}")
            total_tokens += m.token_cost
    lines.append(f"  Total token cost: {total_tokens}")
    return "\n".join(lines)


if __name__ == "__main__":
    # Example: select a few modules
    x = np.zeros(len(MODULES), dtype=float)
    x[0] = 1  # persona_hospitality
    x[4] = 1  # rule_brevity
    x[6] = 1  # rule_no_markdown
    x[8] = 1  # policy_refusal

    print(describe_selection(x))
    print("\n--- Assembled Prompt ---")
    print(assemble_prompt(x))
