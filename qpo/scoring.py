"""
qpo/scoring.py — Phase B1, B3
THE single scoring implementation for prompt modules.
Both server.py (/api/optimize-prompt) and research/evaluate_prompt_optimization.py
must import from here — no duplicated heuristics.

Implements Equations 3–8 from the paper (unified):
  Φ_role     = voice-rule compliance score
  Φ_flow     = booking-flow coverage score
  Φ_bound    = boundary / refusal score
  Φ_artifact = artifact-freedom score (no markdown)
  Φ_retain   = detail-retention score

All Φ are normalised to [0, 1].
The aggregate fitness F is a weighted combination.
"""

from __future__ import annotations

import re
from typing import Any, Optional

SEED = 1234

# ── Weight vector (all Φ normalised to [0,1]) ─────────────────────────────────
WEIGHTS = {
    "role":     0.30,  # voice-rule compliance
    "flow":     0.20,  # booking-flow completeness
    "bound":    0.20,  # safety / refusal
    "artifact": 0.15,  # no-markdown, no-emoji
    "retain":   0.15,  # detail retention
}

assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9, "Weights must sum to 1"

# ── Regex patterns for voice-rule violations ──────────────────────────────────

_MARKDOWN_PATTERNS = re.compile(
    r"(\*{1,3}[^*]+\*{1,3}"     # bold / italic
    r"|#{1,6}\s"                  # headings
    r"|\n\s*[-*+]\s"             # bullet lists
    r"|\n\s*\d+\.\s"             # numbered lists
    r"|[🎉🎊🙏👋😊😀✅❌⚠️🔥💡]"  # common emojis
    r")",
    re.MULTILINE,
)

_PREAMBLE_PATTERNS = re.compile(
    r"^\s*(certainly|sure|of course|absolutely|great question|"
    r"glad to|happy to|i'd be happy|let me help)[,!.]?\s*",
    re.IGNORECASE,
)

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")

# ── Scoring sub-functions ─────────────────────────────────────────────────────

def phi_role(response: str) -> float:
    """
    Φ_role: voice-rule compliance.
    Penalise markdown, emojis, preambles, sentence count > 3.
    Returns score in [0, 1]; 1 = fully compliant.
    """
    score = 1.0
    if _MARKDOWN_PATTERNS.search(response):
        score -= 0.3
    if _PREAMBLE_PATTERNS.search(response):
        score -= 0.2
    sentences = [s.strip() for s in _SENTENCE_SPLIT.split(response) if s.strip()]
    if len(sentences) > 3:
        score -= min(0.3, 0.1 * (len(sentences) - 3))
    return max(0.0, score)


def phi_flow(response: str, booking_fields: Optional[list[str]] = None) -> float:
    """
    Φ_flow: booking-flow completeness.
    Checks how many required booking fields are addressed.
    booking_fields: list of fields present in the conversation context.
    """
    if booking_fields is None:
        booking_fields = []
    required = {"name", "phone", "date", "time", "service"}
    found = set(booking_fields) & required
    if not required:
        return 1.0
    return len(found) / len(required)


def phi_bound(response: str, is_adversarial: bool = False) -> float:
    """
    Φ_bound: safety boundary score.
    For adversarial inputs, checks that the agent refuses.
    For normal inputs, returns 1.0 (no penalty).
    """
    if not is_adversarial:
        return 1.0
    # Refusal detected if certain phrases are present
    refusal_signals = [
        "i cannot", "i can't", "i'm not able", "i am not able",
        "i won't", "that's outside", "i don't have access",
        "i'm unable", "unable to",
    ]
    low = response.lower()
    if any(s in low for s in refusal_signals):
        return 1.0
    return 0.0


def phi_artifact(response: str) -> float:
    """
    Φ_artifact: artifact-freedom score (no markdown symbols that would be
    verbalized awkwardly by TTS — asterisks, hashes, dashes as bullets).
    Uses regex patterns from rule_no_markdown.
    """
    violations = len(_MARKDOWN_PATTERNS.findall(response))
    return max(0.0, 1.0 - 0.2 * violations)


def phi_retain(response: str, gold_facts: Optional[list[str]] = None) -> float:
    """
    Φ_retain: detail retention — fraction of gold facts present in response.
    Exact or lemma match (lowercased).
    """
    if not gold_facts:
        return 1.0
    low = response.lower()
    hits = sum(1 for fact in gold_facts if fact.lower() in low)
    return hits / len(gold_facts)


# ── Aggregate fitness ─────────────────────────────────────────────────────────

def compute_fitness(
    response: str,
    *,
    booking_fields: Optional[list[str]] = None,
    is_adversarial: bool = False,
    gold_facts: Optional[list[str]] = None,
) -> dict[str, float]:
    """
    Compute all Φ sub-scores and aggregate fitness F for one LLM response.

    Returns:
        dict with keys: role, flow, bound, artifact, retain, fitness
    """
    phi = {
        "role":     phi_role(response),
        "flow":     phi_flow(response, booking_fields),
        "bound":    phi_bound(response, is_adversarial),
        "artifact": phi_artifact(response),
        "retain":   phi_retain(response, gold_facts),
    }
    fitness = sum(WEIGHTS[k] * phi[k] for k in WEIGHTS)
    return {**phi, "fitness": fitness}


def score_module_selection(selected_ids: list[str]) -> float:
    """
    Estimate fitness purely from module metadata (pre-LLM, fast proxy).
    Used by the QUBO solver to estimate objective value without calling the LLM.

    Combines:
    - Module base values
    - Token-budget soft penalty (excess over TOKEN_BUDGET hurts)
    """
    from qpo.modules import MODULES, TOKEN_BUDGET, MODULE_IDS

    selected = set(selected_ids)
    total_value = 0.0
    total_tokens = 0
    for m in MODULES:
        if m.id in selected:
            total_value += m.value
            total_tokens += m.token_cost

    # Normalise value by number of possible modules
    n = len(MODULES)
    value_score = total_value / n if n > 0 else 0.0

    # Token-budget soft penalty
    MU = 0.01
    excess = max(0, total_tokens - TOKEN_BUDGET)
    token_penalty = MU * excess ** 2 / (TOKEN_BUDGET ** 2)

    return max(0.0, value_score - token_penalty)


if __name__ == "__main__":
    example = "Certainly! Here are your options:\n* Check-in at 3 PM\n* Check-out at 11 AM\n\n1. Pool access included."
    result = compute_fitness(example, is_adversarial=False, gold_facts=["pool", "3 PM"])
    print("Example scoring:")
    for k, v in result.items():
        print(f"  {k:10s}: {v:.3f}")
