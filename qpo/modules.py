"""
qpo/modules.py — Phase B1
Module library for modular prompt assembly.

Each PromptModule is a binary decision variable x_i ∈ {0, 1}.
The JSON-driven conflict and synergy matrices are also built here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

# ── Module definition ─────────────────────────────────────────────────────────

@dataclass
class PromptModule:
    """A single composable prompt module."""
    id: str                  # short snake_case name
    text: str                # text injected into the prompt
    token_cost: int          # approximate token count
    value: float             # base value score in [0, 1] (will be scaled)
    tags: list[str] = field(default_factory=list)

    def __repr__(self) -> str:
        return f"PromptModule({self.id!r}, cost={self.token_cost}, value={self.value:.2f})"


# ── Canonical module library (12–24 modules, hospitality + clinic) ────────────

MODULES: list[PromptModule] = [
    # ── Identity / persona ────────────────────────────────────────────────────
    PromptModule(
        id="persona_hospitality",
        text="You are Aria, a warm and professional concierge at Marina Bay Resort. "
             "Your purpose is to assist guests with reservations, amenities, and local recommendations.",
        token_cost=35, value=0.95,
        tags=["persona", "hospitality"],
    ),
    PromptModule(
        id="persona_clinic",
        text="You are Nova, a courteous scheduling assistant at Harmony Wellness Clinic. "
             "You help patients book appointments and answer general questions.",
        token_cost=32, value=0.95,
        tags=["persona", "clinic"],
    ),
    # ── Tone ──────────────────────────────────────────────────────────────────
    PromptModule(
        id="tone_warm",
        text="Speak in a warm, empathetic, and friendly tone. Show genuine interest in the guest's needs.",
        token_cost=18, value=0.60,
        tags=["tone"],
    ),
    PromptModule(
        id="tone_formal",
        text="Maintain a professional and formal register at all times. Avoid casual language.",
        token_cost=15, value=0.50,
        tags=["tone"],
    ),
    # ── Voice-output rules ────────────────────────────────────────────────────
    PromptModule(
        id="rule_brevity",
        text="Keep each response to 1–3 spoken sentences. Voice listeners cannot tolerate long walls of text.",
        token_cost=20, value=0.80,
        tags=["voice_rule", "brevity"],
    ),
    PromptModule(
        id="rule_one_question",
        text="Ask only one question per turn. Never stack multiple questions in a single response.",
        token_cost=16, value=0.70,
        tags=["voice_rule"],
    ),
    PromptModule(
        id="rule_no_markdown",
        text="Never use markdown formatting (no *, #, bullets, numbered lists, or emojis). "
             "Your output is read aloud by a TTS engine.",
        token_cost=24, value=0.85,
        tags=["voice_rule", "no_markdown"],
    ),
    PromptModule(
        id="rule_no_preamble",
        text='Do not begin responses with filler phrases like "Certainly!", "Sure!", or "Of course!". '
             "Start directly with the answer.",
        token_cost=22, value=0.75,
        tags=["voice_rule"],
    ),
    # ── Safety / guardrail ────────────────────────────────────────────────────
    PromptModule(
        id="policy_refusal",
        text="If asked anything outside your scope (politics, medical diagnosis, illegal activity), "
             "politely decline and redirect the caller to your area of expertise.",
        token_cost=30, value=0.80,
        tags=["guardrail", "refusal"],
    ),
    PromptModule(
        id="policy_pii",
        text="Never repeat, confirm, or elaborate on credit card numbers, passport numbers, or full addresses. "
             "Refer to a secure channel for sensitive data.",
        token_cost=28, value=0.85,
        tags=["guardrail", "pii"],
    ),
    # ── Knowledge / RAG grounding ─────────────────────────────────────────────
    PromptModule(
        id="kb_grounding",
        text="Base all factual answers strictly on the retrieved knowledge-base excerpts provided to you. "
             "If the knowledge base does not contain the answer, say so honestly.",
        token_cost=26, value=0.80,
        tags=["rag", "kb_grounding"],
    ),
    PromptModule(
        id="kb_refuse_unknown",
        text="If you do not know the answer and it is not in the retrieved context, say: "
             '"I\'m not sure about that. Let me connect you with a human agent."',
        token_cost=28, value=0.65,
        tags=["rag", "refusal"],
    ),
    # ── Date / booking handling ───────────────────────────────────────────────
    PromptModule(
        id="date_handling",
        text="Always confirm date and time details by repeating them back (e.g. 'That is Tuesday the 15th at 3 PM — correct?'). "
             "Use 12-hour clock format with AM/PM.",
        token_cost=30, value=0.70,
        tags=["booking", "date"],
    ),
    PromptModule(
        id="booking_flow",
        text="To complete a booking, collect: guest name, contact number, preferred date and time, "
             "and nature of service. Confirm each field before proceeding.",
        token_cost=32, value=0.75,
        tags=["booking"],
    ),
    # ── Escalation ────────────────────────────────────────────────────────────
    PromptModule(
        id="escalation",
        text="If the caller is frustrated, upset, or the request is beyond your capabilities, "
             "offer to transfer them to a human agent immediately.",
        token_cost=25, value=0.65,
        tags=["escalation"],
    ),
    # ── Verbose (conflict with brevity — included to create real QUBO structure) ─
    PromptModule(
        id="tone_verbose",
        text="Be thorough and detailed in your explanations. Walk the guest through each step clearly, "
             "even if that takes several sentences.",
        token_cost=22, value=0.30,  # low value on its own for voice
        tags=["tone", "verbose"],
    ),
]

# ── Module index helpers ──────────────────────────────────────────────────────

MODULE_IDS: list[str] = [m.id for m in MODULES]
N_MODULES: int = len(MODULES)

def get_module(module_id: str) -> PromptModule:
    for m in MODULES:
        if m.id == module_id:
            return m
    raise KeyError(f"Unknown module id: {module_id!r}")


def module_index(module_id: str) -> int:
    return MODULE_IDS.index(module_id)


# ── Conflict / synergy matrices ───────────────────────────────────────────────
# c_ij > 0 → conflict/redundancy penalty when both i and j are selected
# s_ij > 0 → synergy bonus when both i and j are selected

def build_conflict_matrix() -> list[list[float]]:
    """
    Returns an NxN conflict matrix C where C[i][j] is the penalty
    for selecting both module i and module j simultaneously.
    """
    n = N_MODULES
    C = [[0.0] * n for _ in range(n)]

    def _set_conflict(a: str, b: str, value: float) -> None:
        i, j = module_index(a), module_index(b)
        C[i][j] = value
        C[j][i] = value

    # Two persona modules — domain-exclusive (strong conflict)
    _set_conflict("persona_hospitality", "persona_clinic", 2.0)

    # Tone conflicts
    _set_conflict("tone_warm",    "tone_formal",  0.8)
    _set_conflict("rule_brevity", "tone_verbose", 1.5)

    # Two persona × tone_formal (formal already implied by clinic persona)
    _set_conflict("persona_clinic", "tone_warm", 0.3)

    return C


def build_synergy_matrix() -> list[list[float]]:
    """
    Returns an NxN synergy matrix S where S[i][j] is the bonus
    for selecting both module i and module j simultaneously.
    """
    n = N_MODULES
    S = [[0.0] * n for _ in range(n)]

    def _set_synergy(a: str, b: str, value: float) -> None:
        i, j = module_index(a), module_index(b)
        S[i][j] = value
        S[j][i] = value

    # RAG grounding + refuse-if-unknown → strong synergy
    _set_synergy("kb_grounding", "kb_refuse_unknown", 0.6)

    # Booking flow + date handling → synergy
    _set_synergy("booking_flow", "date_handling", 0.5)

    # No-markdown + brevity → reinforce each other
    _set_synergy("rule_no_markdown", "rule_brevity", 0.4)

    # PII policy + refusal → synergy for safety
    _set_synergy("policy_pii", "policy_refusal", 0.4)

    # Escalation + refusal → synergy
    _set_synergy("escalation", "policy_refusal", 0.3)

    return S


# ── Must-include module IDs (injected via large linear bias, not hard constraint) ─
MUST_INCLUDE: set[str] = {"rule_no_markdown", "policy_pii"}

# Token budget (soft quadratic penalty target)
TOKEN_BUDGET: int = 180  # tokens

if __name__ == "__main__":
    print(f"Module library: {N_MODULES} modules")
    for m in MODULES:
        print(f"  {m.id:30s}  cost={m.token_cost:3d}  value={m.value:.2f}  tags={m.tags}")
