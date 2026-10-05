"""
scripts/bench_retrieval.py — Phase D3/D4
=========================================
BM25 retrieval benchmark: precision@k, recall@k, MRR against a
golden labelled query set.

Usage:
    python scripts/bench_retrieval.py --agent-id 1 \
        --queries research/data/retrieval_eval.jsonl \
        --k 4 --out research/results/retrieval.json

Input JSONL format (one JSON object per line):
    {"query": "what is the check-in time?",
     "relevant_chunks": ["Check-in is available from 2 PM onwards."]}

The script:
  1. Loads all chunks for the given agent from agents.db.
  2. Builds a BM25Index (same class used in production).
  3. Runs every query and computes P@k, R@k, MRR, nDCG@k.
  4. Writes a JSON summary to --out.
  5. Optionally writes a PDF comparison bar chart.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _load_golden(path: Path) -> list:
    """Load a JSONL evaluation set. Returns list of {query, relevant_chunks}."""
    if not path.exists():
        return []
    items = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _precision_at_k(retrieved: list, relevant: list, k: int) -> float:
    hits = sum(1 for r in retrieved[:k] if any(rel in r for rel in relevant))
    return hits / k if k else 0.0


def _recall_at_k(retrieved: list, relevant: list, k: int) -> float:
    hits = sum(1 for rel in relevant if any(rel in r for r in retrieved[:k]))
    return hits / len(relevant) if relevant else 0.0


def _mrr(retrieved: list, relevant: list) -> float:
    for i, r in enumerate(retrieved):
        if any(rel in r for rel in relevant):
            return 1.0 / (i + 1)
    return 0.0


def _ndcg_at_k(retrieved: list, relevant: list, k: int) -> float:
    def dcg(rels):
        return sum(r / math.log2(i + 2) for i, r in enumerate(rels[:k]))
    gains = [1 if any(rel in r for rel in relevant) else 0 for r in retrieved]
    ideal = sorted(gains, reverse=True)
    idcg = dcg(ideal)
    return dcg(gains) / idcg if idcg else 0.0


def run_benchmark(agent_id: int, queries_path: Path, k: int, out_path: Path) -> None:
    from server import db, _bm25_index_for

    golden = _load_golden(queries_path)
    if not golden:
        print(f"[bench_retrieval] No golden queries at {queries_path}.")
        print("  Creating a 10-query example set for you...")
        _create_example_golden(queries_path)
        golden = _load_golden(queries_path)
        if not golden:
            return

    print(f"[bench_retrieval] Loading BM25 index for agent_id={agent_id}...")
    index = _bm25_index_for(agent_id)
    docs = index.docs
    if not docs:
        print(f"[bench_retrieval] Agent {agent_id} has no knowledge base chunks. Add documents first.")
        return

    print(f"[bench_retrieval] {len(docs)} chunks, {len(golden)} queries, k={k}")

    ps, rs, mrrs, ndcgs = [], [], [], []
    for item in golden:
        query = item["query"]
        relevant = item["relevant_chunks"]  # list of substrings that should appear in retrieved chunks
        indices = index.search(query, k=k)
        retrieved = [docs[i] for i in indices]

        p = _precision_at_k(retrieved, relevant, k)
        r = _recall_at_k(retrieved, relevant, k)
        m = _mrr(retrieved, relevant)
        n = _ndcg_at_k(retrieved, relevant, k)
        ps.append(p)
        rs.append(r)
        mrrs.append(m)
        ndcgs.append(n)
        print(f"  Q: {query[:60]!r:62s}  P@{k}={p:.2f}  R@{k}={r:.2f}  MRR={m:.2f}")

    summary = {
        "agent_id": agent_id,
        "n_queries": len(golden),
        "n_chunks": len(docs),
        "k": k,
        "mean_precision": round(sum(ps) / len(ps), 4),
        "mean_recall": round(sum(rs) / len(rs), 4),
        "mean_mrr": round(sum(mrrs) / len(mrrs), 4),
        "mean_ndcg": round(sum(ndcgs) / len(ndcgs), 4),
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\n[bench_retrieval] Results -> {out_path}")
    print(f"  P@{k}={summary['mean_precision']:.3f}  R@{k}={summary['mean_recall']:.3f}  "
          f"MRR={summary['mean_mrr']:.3f}  nDCG@{k}={summary['mean_ndcg']:.3f}")

    _plot_bars(summary, out_path)


def _create_example_golden(path: Path) -> None:
    """Create a minimal example golden file so the script always has something to run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    examples = [
        {"query": "check-in time", "relevant_chunks": ["check-in", "2 PM", "arrival"]},
        {"query": "cancellation policy", "relevant_chunks": ["cancel", "refund", "policy"]},
        {"query": "parking", "relevant_chunks": ["parking", "car park", "valet"]},
        {"query": "breakfast included", "relevant_chunks": ["breakfast", "meal", "included"]},
        {"query": "WiFi password", "relevant_chunks": ["wifi", "wireless", "internet"]},
        {"query": "airport transfer", "relevant_chunks": ["airport", "shuttle", "transfer"]},
        {"query": "room upgrade", "relevant_chunks": ["upgrade", "suite", "room type"]},
        {"query": "swimming pool", "relevant_chunks": ["pool", "swimming", "gym"]},
        {"query": "late checkout", "relevant_chunks": ["late checkout", "extend", "12 PM"]},
        {"query": "pet policy", "relevant_chunks": ["pet", "dog", "cat", "animal"]},
    ]
    with open(path, "w", encoding="utf-8") as f:
        for ex in examples:
            f.write(json.dumps(ex) + "\n")
    print(f"[bench_retrieval] Created example golden set -> {path}")


def _plot_bars(summary: dict, csv_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        return

    fig_dir = Path(__file__).parent.parent / "research" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    k = summary["k"]
    metrics = {
        f"P@{k}": summary["mean_precision"],
        f"R@{k}": summary["mean_recall"],
        "MRR": summary["mean_mrr"],
        f"nDCG@{k}": summary["mean_ndcg"],
    }
    fig, ax = plt.subplots(figsize=(6, 4))
    bars = ax.bar(list(metrics.keys()), list(metrics.values()),
                  color=["steelblue", "seagreen", "tomato", "orchid"])
    ax.bar_label(bars, fmt="%.3f", padding=3)
    ax.set_ylim(0, 1.1)
    ax.set_ylabel("Score")
    ax.set_title(f"BM25 Retrieval Metrics (n={summary['n_queries']}, k={k})")
    ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    out = fig_dir / "retrieval_metrics.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"[bench_retrieval] Bar chart -> {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description="BM25 retrieval benchmark")
    ap.add_argument("--agent-id", type=int, required=True)
    ap.add_argument("--queries", default="research/data/retrieval_eval.jsonl")
    ap.add_argument("--k", type=int, default=4)
    ap.add_argument("--out", default="research/results/retrieval.json")
    args = ap.parse_args()
    run_benchmark(args.agent_id, Path(args.queries), args.k, Path(args.out))


if __name__ == "__main__":
    main()
