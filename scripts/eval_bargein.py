"""
scripts/eval_bargein.py — Phase E
===================================
Barge-in detection evaluation.

The VAD barge-in logic lives in static/call-engine.js (browser JS, not Python).
This script evaluates the *equivalent Python model* of that logic against a
labelled audio corpus.

Algorithm (mirrors call-engine.js lines 89-127):
  - A "barge-in" is triggered when RMS > threshold for >= N_HITS consecutive frames
  - threshold = max(RMS_FLOOR, speaker_bleed_rms * BLEED_FACTOR)
  - Grace period: first GRACE_FRAMES after TTS starts are ignored

Parameters (configurable; defaults match call-engine.js):
  RMS_FLOOR    = 0.060
  BLEED_FACTOR = 2.2
  N_HITS       = 5
  GRACE_FRAMES = 8    (approx 600ms at 128-sample/frame, 16kHz)

Usage:
    python scripts/eval_bargein.py --data research/data/bargein_eval.jsonl \
        --out research/results/bargein_eval.json

JSONL format (one object per test case):
    {
      "id": 1,
      "description": "Clear user interruption during TTS",
      "frames_rms": [0.01, 0.02, 0.08, 0.09, 0.12, 0.15, 0.18, 0.20, 0.22],
      "speaker_bleed_rms": 0.03,
      "is_speaking_tts": true,
      "grace_frame_idx": 0,
      "label": true
    }

If no data file exists, a 40-case synthetic set is generated.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Parameters mirroring call-engine.js
RMS_FLOOR    = 0.060
BLEED_FACTOR = 2.2
N_HITS       = 5
GRACE_FRAMES = 8   # frames to ignore at TTS start (≈600 ms at 16kHz/128-sample frames)


def _detect_bargein(
    frames_rms: list,
    speaker_bleed_rms: float,
    is_speaking_tts: bool,
    grace_frame_idx: int,
    rms_floor: float = RMS_FLOOR,
    bleed_factor: float = BLEED_FACTOR,
    n_hits: int = N_HITS,
    grace_frames: int = GRACE_FRAMES,
) -> bool:
    """
    Python re-implementation of the call-engine.js barge-in detector.
    Returns True if a barge-in was detected in the given frame sequence.
    """
    if not is_speaking_tts:
        return False
    threshold = max(rms_floor, speaker_bleed_rms * bleed_factor)
    hits = 0
    for frame_i, rms in enumerate(frames_rms):
        abs_frame = grace_frame_idx + frame_i
        if abs_frame < grace_frames:
            hits = 0
            continue
        if rms > threshold:
            hits += 1
            if hits >= n_hits:
                return True
        else:
            hits = max(0, hits - 1)
    return False


def _create_synthetic_set(path: Path) -> None:
    """Generate 40 labelled synthetic test cases covering TP, TN, FP, FN scenarios."""
    path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(42)
    cases = []

    # True Positives: sustained loud voice during TTS (after grace period)
    for i in range(10):
        bleed = rng.uniform(0.01, 0.04)
        thr = max(RMS_FLOOR, bleed * BLEED_FACTOR) + 0.01
        frames = [rng.uniform(0.0, 0.02)] * GRACE_FRAMES + [thr + rng.uniform(0, 0.05)] * N_HITS
        cases.append({
            "id": len(cases) + 1,
            "description": f"TP: sustained user voice above threshold #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": round(bleed, 4),
            "is_speaking_tts": True,
            "grace_frame_idx": 0,
            "label": True,
        })

    # True Negatives: low-level ambient noise, no interruption
    for i in range(10):
        bleed = rng.uniform(0.02, 0.05)
        frames = [rng.uniform(0.005, 0.04)] * 20
        cases.append({
            "id": len(cases) + 1,
            "description": f"TN: ambient noise only #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": round(bleed, 4),
            "is_speaking_tts": True,
            "grace_frame_idx": 0,
            "label": False,
        })

    # Edge: voice during grace period only — should NOT trigger
    for i in range(5):
        bleed = rng.uniform(0.01, 0.03)
        thr = max(RMS_FLOOR, bleed * BLEED_FACTOR) + 0.02
        frames = [thr + rng.uniform(0, 0.05)] * GRACE_FRAMES + [0.01] * 5
        cases.append({
            "id": len(cases) + 1,
            "description": f"TN: transient during grace period #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": round(bleed, 4),
            "is_speaking_tts": True,
            "grace_frame_idx": 0,
            "label": False,
        })

    # Edge: not speaking TTS — barge-in irrelevant
    for i in range(5):
        frames = [rng.uniform(0.1, 0.3)] * 15
        cases.append({
            "id": len(cases) + 1,
            "description": f"TN: TTS not active #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": 0.02,
            "is_speaking_tts": False,
            "grace_frame_idx": 0,
            "label": False,
        })

    # Edge: exactly N_HITS-1 loud frames — should NOT trigger
    for i in range(5):
        bleed = 0.02
        thr = max(RMS_FLOOR, bleed * BLEED_FACTOR) + 0.01
        frames = [0.01] * GRACE_FRAMES + [thr] * (N_HITS - 1) + [0.01] * 5
        cases.append({
            "id": len(cases) + 1,
            "description": f"TN: exactly N_HITS-1 loud frames #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": round(bleed, 4),
            "is_speaking_tts": True,
            "grace_frame_idx": 0,
            "label": False,
        })

    # Edge: grace_frame_idx > 0 (TTS has been playing a while)
    for i in range(5):
        bleed = 0.02
        thr = max(RMS_FLOOR, bleed * BLEED_FACTOR) + 0.01
        frames = [thr + 0.01] * N_HITS + [0.01] * 3
        cases.append({
            "id": len(cases) + 1,
            "description": f"TP: late interrupt (grace already passed) #{i+1}",
            "frames_rms": [round(f, 4) for f in frames],
            "speaker_bleed_rms": round(bleed, 4),
            "is_speaking_tts": True,
            "grace_frame_idx": GRACE_FRAMES + 10,  # well past grace
            "label": True,
        })

    with open(path, "w", encoding="utf-8") as f:
        for c in cases:
            f.write(json.dumps(c) + "\n")
    print(f"[eval_bargein] Created {len(cases)}-case synthetic set -> {path}")


def _load(path: Path) -> list:
    if not path.exists():
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def run(data_path: Path, out_path: Path) -> None:
    items = _load(data_path)
    if not items:
        print(f"[eval_bargein] No data at {data_path}. Generating synthetic set...")
        _create_synthetic_set(data_path)
        items = _load(data_path)
        if not items:
            return

    print(f"[eval_bargein] Evaluating {len(items)} cases...")
    tp = tn = fp = fn = 0
    for item in items:
        pred = _detect_bargein(
            frames_rms=item["frames_rms"],
            speaker_bleed_rms=item.get("speaker_bleed_rms", 0.02),
            is_speaking_tts=item.get("is_speaking_tts", True),
            grace_frame_idx=item.get("grace_frame_idx", 0),
        )
        label = item["label"]
        status = "TP" if (pred and label) else "TN" if (not pred and not label) else \
                 "FP" if (pred and not label) else "FN"
        if status == "TP": tp += 1
        elif status == "TN": tn += 1
        elif status == "FP": fp += 1
        else: fn += 1
        print(f"  [{item['id']:3d}] {status:2s}  pred={int(pred)}  label={int(label)}  {item['description'][:55]}")

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall    = tp / (tp + fn) if (tp + fn) else 0.0
    f1        = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy  = (tp + tn) / len(items)

    print(f"\n  P={precision:.3f}  R={recall:.3f}  F1={f1:.3f}  Acc={accuracy:.3f}")
    print(f"  TP={tp}  TN={tn}  FP={fp}  FN={fn}")

    summary = {
        "n_cases": len(items),
        "params": {"rms_floor": RMS_FLOOR, "bleed_factor": BLEED_FACTOR,
                   "n_hits": N_HITS, "grace_frames": GRACE_FRAMES},
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "accuracy": round(accuracy, 4),
        "tp": tp, "tn": tn, "fp": fp, "fn": fn,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[eval_bargein] Written -> {out_path}")
    _plot(summary, out_path)


def _plot(summary: dict, out_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig_dir = Path(__file__).parent.parent / "research" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Confusion matrix
    conf = [[summary["tn"], summary["fp"]], [summary["fn"], summary["tp"]]]
    im = ax1.imshow(conf, cmap="Blues")
    for i in range(2):
        for j in range(2):
            ax1.text(j, i, conf[i][j], ha="center", va="center", color="black", fontsize=14)
    ax1.set_xticks([0, 1]); ax1.set_xticklabels(["Pred: No", "Pred: Yes"])
    ax1.set_yticks([0, 1]); ax1.set_yticklabels(["True: No", "True: Yes"])
    ax1.set_title("Barge-In Confusion Matrix")

    # Metrics bar chart
    metrics = {"Precision": summary["precision"], "Recall": summary["recall"],
               "F1": summary["f1"], "Accuracy": summary["accuracy"]}
    bars = ax2.bar(list(metrics.keys()), list(metrics.values()),
                   color=["steelblue", "seagreen", "tomato", "orchid"])
    ax2.bar_label(bars, fmt="%.3f", padding=3)
    ax2.set_ylim(0, 1.2)
    ax2.set_ylabel("Score")
    ax2.set_title("Barge-In Detection Metrics")
    ax2.grid(True, axis="y", alpha=0.3)

    params = summary["params"]
    fig.suptitle(
        f"Barge-In VAD (floor={params['rms_floor']}, bleed={params['bleed_factor']}x, "
        f"hits={params['n_hits']}, grace={params['grace_frames']}f)",
        fontsize=10
    )
    fig.tight_layout()
    out = fig_dir / "bargein_eval.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"[eval_bargein] Chart -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Barge-in VAD evaluation")
    ap.add_argument("--data", default="research/data/bargein_eval.jsonl")
    ap.add_argument("--out", default="research/results/bargein_eval.json")
    args = ap.parse_args()
    run(Path(args.data), Path(args.out))


if __name__ == "__main__":
    main()
