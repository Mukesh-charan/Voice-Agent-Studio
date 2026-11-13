# Reproducing All Results

> One command per table / figure as required by the paper.
> All commands assume the repository root is `voice-agent-mvp/`.

## 0. Prerequisites

```bash
# Python 3.11 recommended
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Copy `.env.example` to `.env` and fill in your API keys:

```bash
cp .env.example .env
# Edit .env with your LLM_API_KEY, etc.
```

## 1. Capture environment (reproduces results/env.json)

```bash
python research/env_capture.py
```

Expected output: `research/results/env.json` containing OS, GPU, Python, and package versions.

## 2. QUBO / QPO scaling study (reproduces Table 2 and Figures 3–4)

```bash
python -m qpo.run_all
```

Outputs:
- `research/results/qpo_scaling.csv` — solver comparison table
- `research/results/qpo_prompt_eval.csv` — downstream prompt quality
- `research/figures/qpo_gap_vs_n.pdf`
- `research/figures/qpo_time_vs_n.pdf`

## 3. Latency benchmark (reproduces Table 3 and Figure 5)

```bash
# Requires WAV files in research/data/eval_wavs/ (300+ utterances)
python scripts/bench_latency.py --config cloud-hybrid
python scripts/bench_latency.py --config local-gpu
python scripts/bench_latency.py --config naive-cascade
```

Outputs: `research/results/latency_raw.jsonl`, `research/results/latency_ablation.csv`,
`research/figures/latency_cdf.pdf`, `research/figures/latency_stacked.pdf`

## 4. BM25 retrieval benchmark (reproduces Table 4)

```bash
python scripts/bench_retrieval.py
```

Outputs: `research/results/retrieval_benchmark.csv`

## 5. PII guardrail evaluation (reproduces Table 5)

```bash
python scripts/eval_pii.py
```

Outputs: `research/results/pii_eval.json`

## 6. Barge-in evaluation (reproduces Figure 6)

```bash
python scripts/eval_bargein.py
```

Outputs: `research/results/bargein.csv`, `research/figures/bargein_tradeoff.pdf`

## 7. Booking correctness (reproduces Table 6)

```bash
pytest tests/test_booking_concurrent.py -v
```

## 8. Generate all LaTeX tables from results

```bash
python research/make_tables.py
```

Outputs: `research/generated/tab_*.tex` — these are `\input{}`-ed by the paper.

## 9. Build the paper (requires LaTeX + latexmk)

```bash
cd research
latexmk -pdf research_paper_ieee.tex
```

## Seed

All experiments use `SEED=1234` (set in each script). Random state is fully pinned.

## Hardware used

See `research/results/env.json` after running step 1.
