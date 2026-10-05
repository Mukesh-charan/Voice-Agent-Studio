"""
scripts/eval_pii.py — Phase G2/G3
====================================
Evaluates the PII redaction guardrail (abstract_transcript) on a
labelled test set.

Computes Precision, Recall, F1 for each entity type:
  PHONE, CARD, EMAIL

Usage:
    python scripts/eval_pii.py --data research/data/pii_eval.jsonl \
        --out research/results/pii_eval.json

Input JSONL format:
    {"text": "Call me at +91 98765 43210.", "entities": [{"type": "PHONE", "span": "+91 98765 43210"}]}
    {"text": "Card: 4111 1111 1111 1111", "entities": [{"type": "CARD", "span": "4111 1111 1111 1111"}]}
    {"text": "Email me: alice@example.com", "entities": [{"type": "EMAIL", "span": "alice@example.com"}]}

The evaluation role is always 'viewer' (no can_view_sensitive_data).
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Redaction tokens emitted by guardrail.py (Phase G)
TOKEN_MAP = {
    "PHONE": "[PHONE_REDACTED]",
    "CARD":  "[CARD_REDACTED]",
    "EMAIL": "[EMAIL_REDACTED]",
}


def _load_eval(path: Path) -> list:
    if not path.exists():
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _redact(text: str, role: str = "viewer") -> str:
    """Apply guardrail abstract_transcript to a single text string."""
    from guardrail import abstract_transcript
    turns = [{"role": "user", "content": text}]
    redacted = abstract_transcript(turns, role)
    return redacted[0]["content"] if redacted else text


def evaluate(items: list) -> dict:
    """
    For each item, check whether every entity was redacted (TP) or missed (FN),
    and check for false positive redactions of non-entity spans.
    Returns metrics per type and overall.
    """
    tp: dict = defaultdict(int)
    fn: dict = defaultdict(int)
    fp: dict = defaultdict(int)

    for item in items:
        text = item["text"]
        entities = item.get("entities", [])
        redacted = _redact(text)

        for ent in entities:
            etype = ent["type"]
            span = ent["span"]
            token = TOKEN_MAP.get(etype, f"[{etype}_REDACTED]")

            # True positive: the span was replaced by the token
            if span not in redacted and token in redacted:
                tp[etype] += 1
            # False negative: span is still present in redacted text
            elif span in redacted:
                fn[etype] += 1

        # False positive heuristic: count [_REDACTED] tokens that were NOT expected
        expected_tokens = {TOKEN_MAP[e["type"]] for e in entities if e["type"] in TOKEN_MAP}
        for token in TOKEN_MAP.values():
            if token in redacted and token not in expected_tokens:
                etype = [k for k, v in TOKEN_MAP.items() if v == token][0]
                fp[etype] += 1

    all_types = sorted(set(list(tp.keys()) + list(fn.keys()) + list(fp.keys())))
    results = {}
    total_tp = total_fp = total_fn = 0

    for etype in all_types:
        t, f, p = tp[etype], fn[etype], fp[etype]
        precision = t / (t + p) if (t + p) else 0.0
        recall    = t / (t + f) if (t + f) else 0.0
        f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        results[etype] = {"precision": round(precision, 4), "recall": round(recall, 4),
                           "f1": round(f1, 4), "tp": t, "fp": p, "fn": f}
        total_tp += t; total_fp += p; total_fn += f

    # Micro-average
    micro_p = total_tp / (total_tp + total_fp) if (total_tp + total_fp) else 0.0
    micro_r = total_tp / (total_tp + total_fn) if (total_tp + total_fn) else 0.0
    micro_f1 = 2 * micro_p * micro_r / (micro_p + micro_r) if (micro_p + micro_r) else 0.0
    results["MICRO"] = {"precision": round(micro_p, 4), "recall": round(micro_r, 4),
                         "f1": round(micro_f1, 4), "tp": total_tp, "fp": total_fp, "fn": total_fn}
    return results


def _print_table(results: dict) -> None:
    header = f"{'Type':<10} {'P':>8} {'R':>8} {'F1':>8} {'TP':>5} {'FP':>5} {'FN':>5}"
    print("\n" + header)
    print("-" * len(header))
    for etype, m in results.items():
        print(f"{etype:<10} {m['precision']:>8.3f} {m['recall']:>8.3f} {m['f1']:>8.3f}"
              f" {m['tp']:>5} {m['fp']:>5} {m['fn']:>5}")


def _create_example_pii_set(path: Path) -> None:
    """Create a 30-example labelled PII test set if none exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    items = [
        # PHONE — various formats
        {"text": "Call me at +91 98765 43210.", "entities": [{"type": "PHONE", "span": "+91 98765 43210"}]},
        {"text": "My number is 9876543210.", "entities": [{"type": "PHONE", "span": "9876543210"}]},
        {"text": "Reach me on 044-2345-6789.", "entities": [{"type": "PHONE", "span": "044-2345-6789"}]},
        {"text": "Office: +1 (800) 555-0199.", "entities": [{"type": "PHONE", "span": "+1 (800) 555-0199"}]},
        {"text": "WhatsApp: +44 7911 123456.", "entities": [{"type": "PHONE", "span": "+44 7911 123456"}]},
        {"text": "Contact us at 1800 102 4567.", "entities": [{"type": "PHONE", "span": "1800 102 4567"}]},
        {"text": "Fax: 0091-11-23456789.", "entities": [{"type": "PHONE", "span": "0091-11-23456789"}]},
        {"text": "Call 555-0100 for reservations.", "entities": [{"type": "PHONE", "span": "555-0100"}]},
        # CARD — Luhn-valid numbers
        {"text": "Card ending 4111 1111 1111 1111.", "entities": [{"type": "CARD", "span": "4111 1111 1111 1111"}]},
        {"text": "Visa: 4532015112830366", "entities": [{"type": "CARD", "span": "4532015112830366"}]},
        {"text": "MC: 5425233430109903", "entities": [{"type": "CARD", "span": "5425233430109903"}]},
        {"text": "Amex: 374251018720955", "entities": [{"type": "CARD", "span": "374251018720955"}]},
        {"text": "Discover: 6011111111111117", "entities": [{"type": "CARD", "span": "6011111111111117"}]},
        # EMAIL
        {"text": "Email me at alice@example.com.", "entities": [{"type": "EMAIL", "span": "alice@example.com"}]},
        {"text": "Send to support@hotel.co.in.", "entities": [{"type": "EMAIL", "span": "support@hotel.co.in"}]},
        {"text": "Contact: john.doe+tag@gmail.com", "entities": [{"type": "EMAIL", "span": "john.doe+tag@gmail.com"}]},
        {"text": "Booking confirmation to ram_kumar@yahoo.co.in.", "entities": [{"type": "EMAIL", "span": "ram_kumar@yahoo.co.in"}]},
        {"text": "Reply to no-reply@bookings.org.", "entities": [{"type": "EMAIL", "span": "no-reply@bookings.org"}]},
        # Negative examples — should NOT be redacted
        {"text": "The booking ref is BK-20241205.", "entities": []},
        {"text": "Price: Rs. 1500 per night.", "entities": []},
        {"text": "Date: 2024-12-05 at 14:30.", "entities": []},
        {"text": "Room 204 on floor 2.", "entities": []},
        {"text": "Order ID: 1234567.", "entities": []},
        # Mixed — phone + email in same turn
        {"text": "My name is Raj, phone +91 98100 00001, email raj@example.in.",
         "entities": [{"type": "PHONE", "span": "+91 98100 00001"}, {"type": "EMAIL", "span": "raj@example.in"}]},
        {"text": "Billing card 4111 1111 1111 1111, email admin@corp.com.",
         "entities": [{"type": "CARD", "span": "4111 1111 1111 1111"}, {"type": "EMAIL", "span": "admin@corp.com"}]},
        # Edge cases
        {"text": "No PII here, just text.", "entities": []},
        {"text": "I live at 42, Baker Street.", "entities": []},
        {"text": "My zip code is 600001.", "entities": []},
        {"text": "PIN: 1234.", "entities": []},
        {"text": "Invoice #INV-2024-00123 for Rs 2,499.", "entities": []},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")
    print(f"[eval_pii] Created 30-example PII eval set -> {path}")


def run(data_path: Path, out_path: Path) -> None:
    items = _load_eval(data_path)
    if not items:
        print(f"[eval_pii] No data at {data_path}. Creating example set...")
        _create_example_pii_set(data_path)
        items = _load_eval(data_path)
        if not items:
            return

    print(f"[eval_pii] Evaluating {len(items)} items...")
    results = evaluate(items)
    _print_table(results)

    summary = {"n_items": len(items), "metrics": results}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"[eval_pii] Written -> {out_path}")

    _plot_bars(results, out_path)


def _plot_bars(results: dict, out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        return

    fig_dir = Path(__file__).parent.parent / "research" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    types = [t for t in results if t != "MICRO"]
    x = np.arange(len(types))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 4))
    bars_p = ax.bar(x - width, [results[t]["precision"] for t in types], width, label="Precision", color="steelblue")
    bars_r = ax.bar(x,          [results[t]["recall"]    for t in types], width, label="Recall",    color="seagreen")
    bars_f = ax.bar(x + width,  [results[t]["f1"]        for t in types], width, label="F1",        color="tomato")
    for bars in (bars_p, bars_r, bars_f):
        ax.bar_label(bars, fmt="%.2f", padding=2, fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(types)
    ax.set_ylim(0, 1.2)
    ax.set_ylabel("Score")
    ax.set_title("PII Redaction: Precision / Recall / F1 per Entity Type")
    ax.legend()
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = fig_dir / "pii_eval.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"[eval_pii] Bar chart -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="PII redaction evaluation")
    ap.add_argument("--data", default="research/data/pii_eval.jsonl")
    ap.add_argument("--out", default="research/results/pii_eval.json")
    args = ap.parse_args()
    run(Path(args.data), Path(args.out))


if __name__ == "__main__":
    main()
