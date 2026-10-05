# Final Submission Checklist — Voice Agent Studio

**Version:** 1.0 | **Date:** 2026-10-05

This checklist must be completed in order before submitting the paper/artefact.

---

## Phase K — Pre-submission Checklist

### K1. Reproducibility

- [ ] `python research/env_capture.py` runs cleanly → `research/results/env.json` written
- [ ] `git log --oneline -1` is recorded in `env.json` (field: `git.commit`)
- [ ] All scripts accept `--seed` and default to `42`
- [ ] `REPRODUCE.md` lists exact commands to regenerate every table and figure
- [ ] `requirements.txt` is pinned (no `>=` without upper bound)

### K2. Tests

- [ ] `python -m pytest qpo/tests/ tests/ -v` → **34/34 pass**
- [ ] No test uses `time.sleep` or network calls without mocking
- [ ] Ising identity verified: `x^T Q x == E(z) + const` to 1e-9 for all 2^n bitstrings

### K3. Tables (auto-generated, never manually typed)

- [ ] `python research/make_tables.py` → all `research/generated/tab_*.tex` regenerated
- [ ] `tab_rbac.tex` matches `guardrail.py:PERMISSIONS` exactly
- [ ] `tab_latency.tex` reads from `research/results/latency.csv`
- [ ] `tab_pii.tex` reads from `research/results/pii_eval.json`
- [ ] `tab_qpo_scaling.tex` reads from `research/results/qpo_scaling.csv`

### K4. Figures (auto-generated)

- [ ] `python -m qpo.run_all` → `research/figures/qpo_scaling.pdf`
- [ ] `python scripts/eval_pii.py` → `research/figures/pii_eval.pdf`
- [ ] `python scripts/eval_bargein.py` → `research/figures/bargein_eval.pdf`
- [ ] `python scripts/eval_qpo.py` → `research/figures/qpo_solver_comparison.pdf`
- [ ] `python scripts/bench_latency.py` → `research/figures/latency_cdf.pdf`
  *(latency script requires a running server; stubs gracefully if offline)*
- [ ] No figure is a screenshot or hand-drawn; all are programmatic

### K5. Claims vs Evidence

| Paper claim | Evidence file | Check |
|-------------|--------------|-------|
| "BM25 cached per agent" | `server.py:BM25Index` + `_bm25_index_for()` | [ ] |
| "Slot overlap check (BEGIN IMMEDIATE)" | `server.py:validate_and_save_booking` | [ ] |
| "Outbox pattern for external calls" | `server.py:outbox` table + INSERT | [ ] |
| "PII tokens [PHONE_REDACTED]…" | `guardrail.py:abstract_transcript` | [ ] |
| "Luhn validation for card numbers" | `guardrail.py:_luhn_check` | [ ] |
| "Ising identity corrected (Eq. 13)" | `qpo/qubo.py:qubo_to_ising` + test | [ ] |
| "RBAC 4-tier (owner/manager/receptionist/viewer)" | `guardrail.py:PERMISSIONS` | [ ] |
| "Barge-in: RMS threshold VAD" | `static/call-engine.js:bargeInThreshold` | [ ] |
| "Docker deployment" | `Dockerfile` + `docker-compose.yml` | [ ] |
| "15 prompt modules, real QUBO" | `qpo/modules.py` + `qpo/qubo.py` | [ ] |

### K6. Paper Fixes (after measurements)

- [ ] Remove or qualify the "Docker-based deployment" claim if Docker was not benchmarked
- [ ] Update TTFF/E2E numbers in §4.3 from `research/results/latency.csv` (p50, p95)
- [ ] Update PII P/R/F1 in §4.5 from `research/results/pii_eval.json`
- [ ] Update QUBO solver comparison table in §3.4 from `research/results/qpo_eval.json`
- [ ] Cite `env.json` for hardware/software environment (§5 Experimental Setup)
- [ ] Replace "In future work, barge-in…" with actual VAD metrics from `bargein_eval.json`

### K7. Code Quality

- [ ] `python -c "import ast; ast.parse(open('server.py').read())"` → no syntax error
- [ ] `python -c "import ast; ast.parse(open('guardrail.py').read())"` → no syntax error
- [ ] No `print` statements left in `guardrail.py` or `qpo/` package (use `logging`)
- [ ] No hardcoded API keys in any committed file
- [ ] `.gitignore` excludes `agents.db`, `*.env`, `research/results/`, `research/generated/`

### K8. Artefact Packaging

- [ ] `git tag v1.0-camera-ready` on the commit used for the paper
- [ ] `git archive --format=zip HEAD -o voice-agent-studio-v1.0.zip` produces a clean archive
- [ ] Archive unpacks and `pip install -r requirements.txt && python server.py` works
- [ ] `REPRODUCE.md` has been proof-read by a co-author

---

## Quick-run All Checks

```powershell
# 1. Tests
python -m pytest qpo/tests/ tests/ -v

# 2. Env capture
python research/env_capture.py

# 3. All eval scripts (server must be running for latency)
python scripts/eval_pii.py
python scripts/eval_bargein.py
python scripts/eval_qpo.py
python scripts/bench_latency.py

# 4. QPO scaling study + figures
pip install matplotlib
python -m qpo.run_all

# 5. LaTeX tables
python research/make_tables.py

# 6. Syntax check
python -c "import ast; [ast.parse(open(f).read()) for f in ['server.py','guardrail.py']]"
echo "All checks passed"
```
