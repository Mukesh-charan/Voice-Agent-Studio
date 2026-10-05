"""
scripts/bench_latency.py — Phase C
===================================
Latency benchmarking harness for the Voice Agent Studio.

Measures three metrics on the /api/agents/{id}/chat streaming endpoint:
  - TTFF  : time-to-first-token (seconds) — from POST to first SSE chunk
  - E2E   : end-to-end latency (seconds) — from POST to last SSE chunk
  - RTF   : real-time factor = E2E / audio_duration (only when audio is played)

Usage (all optional flags):
    python scripts/bench_latency.py --url http://localhost:8000 ^
        --agent-id 1 --n 50 --seed 42 --out research/results/latency.csv

Reproducibility:
  - Random seed is fixed (--seed 42 by default)
  - All prompts drawn from a deterministic permutation of QUERY_BANK
  - Requires a running server; will SKIP cleanly if server is unreachable
"""

from __future__ import annotations

import argparse
import csv
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Optional

# ── Query bank — 50 diverse booking-domain queries ───────────────────────────
QUERY_BANK = [
    "Hello, I'd like to make a booking.",
    "What time slots do you have available tomorrow?",
    "My name is Priya Sharma, I want to book for this Friday at 3pm.",
    "Can I bring my dog along?",
    "Is the cancellation free?",
    "I need to reschedule my appointment to next Monday.",
    "Do you have availability on December 25th?",
    "What is the price for a standard room?",
    "My phone number is +91 98765 43210.",
    "I confirmed the booking, what's the reference number?",
    "Can you repeat the booking details please?",
    "Is parking available at your location?",
    "I'll be checking in on Tuesday evening.",
    "Do you offer group discounts?",
    "I need a room for two nights.",
    "What's the earliest check-in time?",
    "Is breakfast included in the price?",
    "I need wheelchair accessibility.",
    "Can I book for three people?",
    "My email is john.doe@example.com for the confirmation.",
    "I want to cancel my existing booking.",
    "What amenities are included?",
    "Is there a pool?",
    "I'd like a sea-view room.",
    "Can I pay at the door?",
    "Is there a gym?",
    "How far are you from the airport?",
    "Do you have late checkout?",
    "What's the refund policy?",
    "I want to book for my anniversary.",
    "My name is David Williams, phone 9876500001.",
    "I'll arrive at 11pm, is that OK?",
    "Do you have a conference room?",
    "Can I get a baby cot?",
    "I need to update my booking date to next week.",
    "What documents do I need to check in?",
    "Is there a restaurant on-site?",
    "Do you accept credit cards?",
    "Can I get an invoice?",
    "How many guests can one room accommodate?",
    "I want the booking confirmed by email.",
    "What's the address?",
    "Is the WiFi free?",
    "Do you have 24-hour reception?",
    "I need a non-smoking room.",
    "Can I upgrade my room?",
    "What's the checkout time?",
    "I'd like to book a suite.",
    "Do you have valet parking?",
    "Can I see the room before booking?",
]


def _try_import_httpx():
    try:
        import httpx
        return httpx
    except ImportError:
        print("[bench_latency] ERROR: httpx not installed. Run: pip install httpx", file=sys.stderr)
        sys.exit(1)


def bench_stream(
    httpx,
    url: str,
    agent_id: int,
    session_cookie: str,
    messages: list,
    timeout: float = 30.0,
) -> tuple:
    """POST a chat request and measure TTFF and E2E. Returns (ttff, e2e) or (None, None)."""
    payload = {
        "agent_id": agent_id,
        "messages": messages,
        "call_uid": f"bench_{int(time.time()*1000)}",
    }
    t0 = time.perf_counter()
    ttff = None
    try:
        with httpx.stream(
            "POST",
            f"{url}/api/agents/{agent_id}/chat",
            json=payload,
            headers={"Cookie": f"session={session_cookie}"},
            timeout=timeout,
        ) as resp:
            if resp.status_code not in (200, 206):
                return None, None
            for chunk in resp.iter_bytes():
                if chunk and ttff is None:
                    ttff = time.perf_counter() - t0
        e2e = time.perf_counter() - t0
        return ttff, e2e
    except Exception as exc:
        print(f"  [warn] request failed: {exc}", file=sys.stderr)
        return None, None


def _login(httpx, url: str, email: str, password: str) -> Optional[str]:
    try:
        r = httpx.post(f"{url}/api/auth/login", json={"email": email, "password": password}, timeout=10)
        if r.status_code == 200:
            return r.cookies.get("session")
    except Exception:
        pass
    return None


def _ensure_bench_user(httpx, url: str) -> Optional[str]:
    email, pwd = "bench@internal.test", "bench_internal_pw_99"
    for _ in range(2):
        sess = _login(httpx, url, email, pwd)
        if sess:
            return sess
        try:
            httpx.post(f"{url}/api/auth/register", json={"email": email, "password": pwd}, timeout=10)
        except Exception:
            return None
    return None


def _first_agent(httpx, url: str, session: str) -> Optional[int]:
    try:
        r = httpx.get(f"{url}/api/agents", headers={"Cookie": f"session={session}"}, timeout=10)
        if r.status_code == 200:
            agents = r.json()
            if agents:
                return agents[0]["id"]
    except Exception:
        pass
    return None


def _write_stub(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["i", "query", "ttff_s", "e2e_s"])
        w.writeheader()
        w.writerow({"i": 0, "query": "STUB_NO_SERVER", "ttff_s": "", "e2e_s": ""})
    print(f"[bench_latency] Wrote stub -> {out_path}")


def _write_csv(out_path: Path, results: list) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["i", "query", "ttff_s", "e2e_s"])
        w.writeheader()
        w.writerows(results)
    print(f"[bench_latency] Written -> {out_path}")


def _print_summary(results: list) -> None:
    ttffs = [r["ttff_s"] for r in results if r["ttff_s"] != ""]
    e2es = [r["e2e_s"] for r in results if r["e2e_s"] != ""]
    if ttffs:
        p50, p95 = statistics.median(ttffs), sorted(ttffs)[int(0.95 * len(ttffs))]
        print(f"\n  TTFF  p50={p50:.3f}s  p95={p95:.3f}s  mean={statistics.mean(ttffs):.3f}s")
    if e2es:
        p50, p95 = statistics.median(e2es), sorted(e2es)[int(0.95 * len(e2es))]
        print(f"  E2E   p50={p50:.3f}s  p95={p95:.3f}s  mean={statistics.mean(e2es):.3f}s")
    print(f"  Success rate: {len(ttffs)}/{len(results)}")


def _plot_cdf(results: list, csv_path: Path) -> None:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("[bench_latency] matplotlib not installed -- skipping CDF plot.")
        return

    fig_dir = Path(__file__).parent.parent / "research" / "figures"
    fig_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, key, label in [
        (axes[0], "ttff_s", "TTFF (s)"),
        (axes[1], "e2e_s", "E2E latency (s)"),
    ]:
        vals = sorted([r[key] for r in results if r[key] != ""])
        if not vals:
            ax.set_title(f"{label} -- no data")
            continue
        ys = np.arange(1, len(vals) + 1) / len(vals)
        ax.plot(vals, ys, linewidth=2, color="steelblue")
        ax.axvline(np.percentile(vals, 50), color="C1", linestyle="--", label="p50")
        ax.axvline(np.percentile(vals, 95), color="C2", linestyle="--", label="p95")
        ax.set_xlabel(label)
        ax.set_ylabel("CDF")
        ax.set_title(f"Latency CDF -- {label}")
        ax.legend()
        ax.grid(True, alpha=0.3)

    fig.suptitle("Voice Agent Studio -- Latency Benchmark", fontsize=13)
    fig.tight_layout()
    out = fig_dir / "latency_cdf.pdf"
    fig.savefig(out, bbox_inches="tight")
    print(f"[bench_latency] CDF plot -> {out}")


def run_benchmark(url: str, agent_id: Optional[int], n: int, seed: int, out_path: Path) -> None:
    httpx = _try_import_httpx()

    try:
        httpx.get(f"{url}/api/agents", timeout=5)
    except Exception:
        print(f"[bench_latency] Server unreachable at {url} -- SKIPPING benchmark.", file=sys.stderr)
        _write_stub(out_path)
        return

    session = _ensure_bench_user(httpx, url)
    if not session:
        print("[bench_latency] Could not authenticate. SKIPPING.", file=sys.stderr)
        _write_stub(out_path)
        return

    if agent_id is None:
        agent_id = _first_agent(httpx, url, session)
    if agent_id is None:
        print("[bench_latency] No agents found. Create one first. SKIPPING.", file=sys.stderr)
        _write_stub(out_path)
        return

    rng = random.Random(seed)
    queries = rng.sample(QUERY_BANK * ((n // len(QUERY_BANK)) + 1), n)

    print(f"[bench_latency] Benchmarking {n} calls -> agent_id={agent_id}, url={url}")
    results = []
    for i, q in enumerate(queries):
        messages = [{"role": "user", "content": q}]
        ttff, e2e = bench_stream(httpx, url, agent_id, session, messages)
        row = {"i": i + 1, "query": q,
               "ttff_s": round(ttff, 4) if ttff else "",
               "e2e_s": round(e2e, 4) if e2e else ""}
        results.append(row)
        status = f"TTFF={ttff:.3f}s  E2E={e2e:.3f}s" if ttff else "FAILED"
        print(f"  [{i+1:3d}/{n}] {status}")

    _write_csv(out_path, results)
    _print_summary(results)
    _plot_cdf(results, out_path)


def main() -> None:
    ap = argparse.ArgumentParser(description="Latency benchmark for Voice Agent Studio")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--agent-id", type=int, default=None)
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="research/results/latency.csv")
    args = ap.parse_args()
    run_benchmark(args.url.rstrip("/"), args.agent_id, args.n, args.seed, Path(args.out))


if __name__ == "__main__":
    main()
