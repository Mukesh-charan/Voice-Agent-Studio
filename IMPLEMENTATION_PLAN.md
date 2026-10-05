# Implementation Plan: Code + Journal Revisions

Target repo: `Project-Phase-final_project/voice-agent-mvp/`
Target manuscript: `research/research_paper_ieee.tex` (this is the only .tex in the zip; there is no `journal.tex`. Either rename it or create `research/journal.tex` from it in Phase J.)

---

## 0. Rules for the coding agent (read first)

1. **Never invent or hand-type a number.** Every number in the paper must come from a file in `research/results/*.json` or `*.csv` written by a script. If a measurement cannot be run, delete the claim from the paper instead.
2. **Generate LaTeX tables from results** with `research/make_tables.py` -> `research/generated/*.tex`, and `\input{}` them. No manual copy-paste of numbers.
3. Fix seeds (`SEED=1234`), log library versions and hardware to `research/results/env.json` on every run.
4. After each phase: run `pytest tests/ -q`, commit with a message `phase-X: ...`, and tick the acceptance checklist.
5. If code and paper disagree, **the code is the truth**; change the paper unless the phase says to change the code.

---

## 1. Audit: paper claims vs. what the code actually does

| # | Paper claim | What the zip contains | Action |
|---|---|---|---|
| 1 | In-memory BM25 inverted index, 0.08 ms | `bm25_search()` in `server.py` re-reads chunks from SQLite and re-tokenizes **every document on every query**. Also returns all chunks if <= 8 | Phase D: build a real cached index, then measure |
| 2 | QAOA solves QUBO | `select_best_path_quantum()` uses `NumPyMinimumEigensolver` (exact classical eigensolver), not QAOA. One-hot problem = `argmax` | Phase B: redesign problem + add real QAOA run |
| 3 | Fitness Eqs. 3-8 with weights | `/api/optimize-prompt` uses a different ad-hoc scoring; `research/evaluate_prompt_optimization.py` has another | Phase B: one shared scoring module used by both |
| 4 | Barge-in via interim transcript, theta_words >= 2 | `call-engine.js` uses **RMS energy threshold + 5 consecutive hits** | Phase E: implement or rewrite claim |
| 5 | Conflict detection Eq. 15, ACID transaction, UUID, ICS, Sheets inside txn | `validate_and_save_booking()` has **no time-overlap check**; no explicit transaction; external calls are after the write | Phase F |
| 6 | Redaction tokens `[PHONE_REDACTED]`, Luhn-valid cards | `guardrail.py` uses `[PHONE REDACTED]`, `[CARD REDACTED]`, a loose regex, no Luhn | Phase G |
| 7 | 5-container Docker stack, Caddy, Piper, hardened | **No Dockerfile, compose, Caddyfile, or STT service in the zip** (README mentions a Dockerfile; it is missing) | Phase H: build it or delete the claim |
| 8 | Local Faster-Whisper, "zero network" | STT defaults to **Groq `whisper-large-v3-turbo`** (cloud); TTS is Edge-TTS (calls Microsoft online) | Phase I: define configurations honestly |
| 9 | Latency 347.5 ms | No latency harness exists. `calculate_metrics.py` times isolated components. The tex says RTX 4060 + Ollama; the earlier PDF says Groq + RTX 4090. Same numbers appear in both | Phase C: measure for real |
| 10 | Abstract says Groq Whisper; Table says Faster-Whisper CUDA | Internal contradiction inside the .tex | Phase J |

---

## Phase A: Repo hygiene and reproducibility (0.5 day)

Tasks
- A1. Create `research/results/`, `research/generated/`, `research/figures/`, `research/data/`.
- A2. Add `research/env_capture.py` writing `results/env.json` (CPU, GPU, RAM, OS, Python, package versions, git commit, LLM model + quantization, STT model, TTS engine).
- A3. Delete from the repo before submission: `docs/~$review_1_v1 (3).pptx`, the duplicate `review_1_v1 (3) - Copy.pptx`, `.env` if present. Add `agents.db` to `.gitignore`.
- A4. Create `LICENSE` and a top-level `REPRODUCE.md` (one command per table/figure).
- A5. Pin `requirements.txt` exactly; remove unused packages (`pennylane`, `docplex`, `pyttsx3`) unless a script imports them.

Acceptance: fresh clone + `pip install -r requirements.txt` + `pytest` passes.

---

## Phase B: Redesign the QUBO so it is non-trivial (2-3 days)

**Why:** with one-hot + independent scores the optimum is `argmax`, so reviewers will say QAOA adds nothing. Make it a real combinatorial problem.

### B1. New formulation: modular prompt assembly
Define `m` prompt **modules** (binary variable `x_i`), e.g. persona, tone-warm, tone-formal, 1-3-sentence rule, one-question rule, no-markdown rule, no-preamble rule, refusal policy, PII policy, booking-flow, KB-grounding rule, date-handling rule, escalation rule, etc. Target m = 12 to 24.

Each module has: `text`, `token_cost`, `value` (voice-compliance + guardrail + retention contribution, from the shared scorer).

Objective (maximize):
`sum_i v_i x_i  -  sum_{i<j} c_ij x_i x_j  +  sum_{i<j} s_ij x_i x_j  -  mu * (sum_i t_i x_i - T_budget)^2`
- `c_ij` conflict/redundancy penalties (e.g. "be verbose" vs "1-3 sentences"; two tone modules)
- `s_ij` synergy bonuses (e.g. KB-grounding + refuse-if-unknown)
- budget term: token budget `T_budget` as a soft quadratic penalty (a genuine QUBO term with off-diagonals)
- Must-include modules (persona, no-markdown) handled by large linear bias, not hard constraints.

Create `qpo/` package:
```
qpo/
  modules.py        # module library + conflict/synergy matrices (JSON-driven)
  scoring.py        # ONE scoring implementation (Eqs. for retention, role, flow, bound, artifact)
  qubo.py           # build Q matrix (numpy), QUBO -> Ising (h, J, const)
  solvers.py        # brute_force, greedy, simulated_annealing, tabu, qaoa (qiskit), numpy_eigen
  assemble.py       # selected bits -> final prompt string
  tests/test_qubo.py
```
`server.py` `/api/optimize-prompt` and `research/evaluate_prompt_optimization.py` must both import `qpo.scoring` (delete the duplicated heuristics).

### B2. Fix the Ising mapping (paper Eq. 13 has sign errors)
With `x_i = (1 - z_i)/2` and `Q = sum(-S_i - lambda) x_i + 2*lambda*sum_{i<j} x_i x_j + lambda`:
- `J_ij = lambda/2`
- `h_i = (S_i + lambda)/2 - (lambda/2)(n-1)`   (paper has the opposite sign on both terms)
- `const = lambda - sum_i (S_i + lambda)/2 + (lambda/4) n (n-1)`

Implement the general conversion `Q -> (h, J, const)` in `qubo.py` for any symmetric Q, and write a unit test: for all 2^n bitstrings (n <= 12) assert `x^T Q x == Ising_energy(z) + const` to 1e-9.

### B3. Solvers and honest comparison
- Exact brute force (ground truth) up to n = 24.
- Greedy (add best marginal gain), simulated annealing (own implementation, seeded), tabu search.
- QAOA via Qiskit `QAOA` + `COBYLA`, Aer statevector for n <= 20; depth p in {1, 2, 3}; report approximation ratio and probability of sampling the optimum. Use a real `QAOA`, not `NumPyMinimumEigensolver` (keep that only as a labelled "exact eigensolver" reference).
- Sweep n in {8, 12, 16, 20, 24}, 30 random instances per n (random conflict/synergy draws plus the real instance). Record: objective, gap to optimum, wall time, success rate.
- For one-hot (original) case keep a single row to show it is trivially argmax.

Outputs: `results/qpo_scaling.csv`, `figures/qpo_gap_vs_n.pdf`, `figures/qpo_time_vs_n.pdf`.

Expected honest outcome: greedy likely falls short of optimum on instances with strong conflicts; SA/tabu probably match brute force; QAOA at small p gives approximation ratio < 1. **Report whatever you get.** Do not claim quantum advantage.

### B4. Real downstream evaluation (replace "simulated N=50")
- Build `research/data/eval_prompts.jsonl`: >= 200 user turns across 2 domains (hospitality, clinic) + 60 adversarial/out-of-scope turns + 40 booking turns.
- Run the candidate prompts (baseline human, random modules, greedy, SA, QAOA-selected, and an **LLM-as-optimizer baseline** that asks the LLM to rewrite the prompt) through the actual LLM at temperature 0 and 3 seeds.
- Metrics, automatic where possible:
  - Voice-rule violations: regex for `*`, `#`, bullets, numbered lists, emojis, preambles ("Certainly", "Sure", "Here is") plus sentence count > 3.
  - Detail retention: key-fact recall against gold facts per question (exact/lemma match) AND an LLM-judge score (flag as such).
  - Guardrail: refusal correctness on adversarial set.
- Report mean +/- 95% CI (bootstrap) and McNemar or paired bootstrap tests between methods.

Acceptance: `python -m qpo.run_all` regenerates `results/qpo_*.csv`; unit tests pass; Ising identity test passes.

---

## Phase C: Real latency measurement, baselines, ablations (2-3 days)

### C1. Instrumentation
- In `server.py` `/chat_stream` and `/api/transcribe`, `/api/tts`: record `time.perf_counter()` stamps (t_request, t_retrieval_done, t_llm_first_token, t_first_sentence, t_tts_first_byte) and return them in an SSE `event: timing` frame or `Server-Timing` header.
- In `static/call-engine.js`: log browser `performance.now()` at VAD speech-end, request sent, first audio sample played (use `AudioContext` `onended`/`start` times). Post to `/api/metrics` -> append JSONL to `results/latency_raw.jsonl`.
- **Define the metric precisely** and write it in the paper: `voice-to-voice = time from end-of-user-speech (VAD endpoint) to first audio sample`. If your VAD endpoint wait (check `vad-processor.js`, ~400 ms silence) is included or excluded, say so. Report both "post-endpoint" and "from last speech sample".

### C2. Benchmark harness (`scripts/bench_latency.py`)
- Replay a fixed set of >= 300 pre-recorded WAV turns (record or synthesize with a TTS different from the agent's, plus an accented subset) so runs are repeatable without a human.
- Configurations (one run each, same hardware, same turns):
  1. **Cloud-hybrid**: Groq Whisper + Groq Llama + Edge-TTS
  2. **Local GPU**: Faster-Whisper + Ollama (quantized) + local TTS (Piper) if built in Phase H, else Edge-TTS
  3. **Naive cascade baseline** (the thing you compare against): wait for full transcript, non-streaming LLM, full-reply TTS, dense-embedding RAG
- Report P50/P90/P95/P99, mean, std, 95% CI, and CDF plot. Save raw per-turn rows.

### C3. Ablation (remove one at a time)
(a) no sentence-level streaming, (b) dense RAG instead of BM25, (c) no VAD pre-filter, (d) larger/smaller Whisper, (e) quantization Q4 vs Q8, (f) optimized vs baseline prompt (does prompt length change TTFT?).
Output `results/latency_ablation.csv`, `figures/latency_cdf.pdf`, `figures/latency_stacked.pdf`.

### C4. Other measurements to add
- ASR **WER** on >= 100 utterances incl. Indian-English accents (`scripts/test_accent_stt.py` exists; extend with ground truth; compute WER with `jiwer`).
- Concurrency: 1, 2, 5, 10, 20 simultaneous calls -> latency + VRAM + CPU.
- Energy/cost: measured wattage if available, else clearly mark estimated.

Acceptance: `results/latency_raw.jsonl` exists; every number in the latency table is derived from it; baseline row exists.

---

## Phase D: Retrieval (1-2 days)

- D1. Replace `bm25_search` with a class `BM25Index` cached per agent in a dict `{agent_id: index}`; build on document add/delete/Google-doc-sync; keep tokenizer + synonyms. Remove the "<= 8 chunks return everything" shortcut from the benchmarked path (keep it as a flag `RETRIEVE_ALL_SMALL=false` for experiments).
- D2. Unit tests: ranking identical to the old implementation on a fixture; index invalidates on KB change.
- D3. Retrieval benchmark `scripts/bench_retrieval.py`: 100-200 entity-style and 50 paraphrase-style queries over the resort guide (`docs/ms_resort_guide.pdf`) and a clinic KB with gold chunk ids. Compare BM25 (yours), BM25 without synonyms, dense (`bge-small-en` via `sentence-transformers`, CPU and GPU). Report P@1, P@3, MRR, latency P50/P95 with corpus sizes 100, 1k, 10k chunks.
- D4. Rewrite paper claim: say "BM25 is faster and competitive on entity queries" **only if** D3 shows it; if dense wins on paraphrase queries, say so and propose hybrid.

---

## Phase E: Barge-in (1 day)

Pick one:
- **Option 1 (recommended, keep code):** rewrite the paper to describe the actual method: energy-based detection with adaptive speaker-bleed threshold (`max(0.060, bleed*2.2)`), grace period 600 ms, 5 consecutive frames. Parameterize `K` (hits) and grace period in the agent settings.
- **Option 2:** implement interim-transcript confirmation (theta_words) in `call-engine.js` using Web Speech interim results, but note it sends audio to the browser vendor (privacy caveat).

Evaluation script (needs a small recorded set): conditions headphones / laptop speaker low / high volume; sweep the hit count or threshold; report false-trigger rate and genuine-interruption latency with counts (n trials) and CIs. Output `results/bargein.csv` and a trade-off curve figure. Remove the "94.2% suppression" and "5.8% FTR" numbers unless they come from this run.

---

## Phase F: Booking correctness (1 day)

- F1. Implement overlap check in `validate_and_save_booking` / `save_booking`: given slot duration (agent setting, default 30/60 min) reject when `A.start < B.end and B.start < A.end` for the same agent (and resource/room if modeled).
- F2. Wrap check + insert in one SQLite transaction (`BEGIN IMMEDIATE`) to make it race-safe. Add UNIQUE index on `(agent_id, slot_start)` where applicable.
- F3. **Outbox pattern:** commit booking first, insert a row into `outbox(event, payload, status)`; a background task sends webhook / Google Calendar / Sheets and retries. Never call external APIs inside the transaction. Update Algorithm 2 in the paper to match.
- F4. Tests: concurrent double booking (use `asyncio.gather` / threads, expect exactly 1 success), adjacent slots allowed, update-in-place, duplicate within a call.
- F5. Measure: conflict detection accuracy on 200 synthetic requests (expect 100%), and transaction time.

---

## Phase G: PII guardrail (1 day)

- G1. Unify redaction tokens with the paper (or change the paper): `[PHONE_REDACTED]`, `[CARD_REDACTED]`; add `[EMAIL_REDACTED]`; add Luhn check function for cards; avoid redacting booking IDs, dates, prices.
- G2. Label a test set of >= 300 transcript lines (phones in several formats incl. Indian +91, cards, emails, spoken digits "nine eight seven ...", names). Compute precision/recall/F1 for the regex pipeline. Spoken-digit forms from ASR are the hard case; report honestly.
- G3. RBAC tests: parametrize all 4 roles x each endpoint in `tests/test_api_guardrails_google.py`; assert 403/masking. Auto-generate the paper's RBAC table **from `guardrail.PERMISSIONS`** so it cannot drift.
- G4. Note: the paper's matrix says Manager cannot edit agent settings; code agrees. Keep.

---

## Phase H: Docker edge deployment (2-3 days, or delete the claim)

Decision gate: if you cannot build and run it, **remove Section 6 and all "air-gapped/Docker" claims** and call it "deployable with Ollama on-premises" instead. If you build it:

Create
```
Dockerfile                  # python:3.11-slim, non-root user, pinned deps, HEALTHCHECK
docker-compose.yml          # no `version:` key; pinned image tags (no :latest)
stt-service/                # FastAPI + faster-whisper, /transcribe, /health
Caddyfile                   # `tls internal` (internal CA) for air-gapped; Let's Encrypt only in the online profile
.dockerignore
```
Requirements
- Services: `voice-core`, `local-llm` (Ollama), `local-tts` (Piper; build your own image, `rhasspy/piper:latest` is not a reliable official tag; give it GPU only if truly used), `local-stt`, `proxy`.
- Hardening actually present in compose: `user: "1000:1000"`, `read_only: true` + `tmpfs`, `cap_drop: [ALL]`, `security_opt: [no-new-privileges:true]`, internal network `internal: true` for backend services (only proxy exposes ports).
- `voice-core` must call local-stt / local-tts when `STT_BASE_URL`/`TTS_PROVIDER` point to them: add a `TTS_PROVIDER=piper|edge` switch and `STT_PROVIDER=faster-whisper-local|groq` in `server.py`.
- Offline proof: run the stack with the host's internet disabled (or `docker network` with no egress), execute 20 calls, capture `tcpdump` showing zero external packets. Save as `results/airgap_check.txt`.
- Recovery test: kill each container mid-call, record recovery time.
- Measure latency (Phase C configuration 2) and resource footprint with `docker stats`.

---

## Phase I: Threat model and configuration matrix (0.5 day, writing)

Add `docs/THREAT_MODEL.md` and a paper table listing, per configuration, what leaves the machine:

| Configuration | STT | LLM | TTS | Data leaves network? |
|---|---|---|---|---|
| Cloud-hybrid (current default) | Groq Whisper | Groq | Edge-TTS (Microsoft) | Audio + text yes |
| Browser-speech variant | Web Speech API (vendor server) | any | any | Audio yes |
| Local (Ollama + Faster-Whisper + Piper) | local | local | local | No (verified by Phase H capture) |

Also state: architecture supports GDPR/HIPAA compliance but does not by itself make a deployment compliant; recorded-call consent is the operator's responsibility.

---

## Phase J: Rewrite the journal .tex (3-4 days)

### J0. File and venue
- Decide venue first (suggested: IEEE Access, Expert Systems with Applications, Speech Communication, or Applied Sciences). Switch `\documentclass[conference]{IEEEtran}` to `[journal]` (IEEE Access: `ieeeaccess.cls`; Elsevier: `elsarticle`). Remove the "Received/Accepted" lines. Fix title block (`thanks`, author order consistent with the PDF).
- Add packages: `algorithm`, `algpseudocode` (replace deprecated `algorithmic`), `siunitx`, `pgfplots` or include PDFs from `figures/`, `subcaption`.

### J1. Choose ONE thesis
Recommended: **"A measured, privacy-aware low-latency voice-agent pipeline with a combinatorial (QUBO) prompt-assembly stage."** Latency + prompt compliance are core; RBAC, Google sync, Docker are supporting system description. Proposed title:
*"Low-Latency, Privacy-Aware Conversational Voice Agents with QUBO-Based Prompt Assembly: Design and Measured Evaluation"*

### J2. Contributions (state exactly 3, same count in abstract, intro, conclusion)
1. QUBO formulation of modular prompt assembly with pairwise conflicts/synergies, verified Ising mapping, and a scaling study against exact/classical/QAOA solvers.
2. A streaming voice pipeline with a measured latency decomposition, naive-cascade baseline and ablations.
3. An on-premises configuration with role-based PII shielding and a verified no-egress deployment (only if Phase H done).

### J3. Section-by-section edits
- **Abstract:** rewrite after results exist. 150-200 words, only numbers from `results/`. Delete "88.9% / 100% / 65.8%" unless reproduced. Remove "provably", "guarantee".
- **Introduction:** cut by ~1/3; remove marketing language; end with the 3 contributions and a roadmap.
- **Related work:** compress to ~1 page; add comparison vs. DSPy/APE/OPRO (prompt optimization), Pipecat/LiveKit (open pipelines), recent full-duplex S2S systems; keep the taxonomy table but label latency figures as "reported in literature", not measured by you.
- **System architecture:** match the code (Groq/Faster-Whisper options, Edge-TTS vs Piper, energy-based barge-in, cached BM25). Add timing diagram figure (from `latency_raw.jsonl`).
- **QPO section:** replace Eqs. 9-13 with the modular formulation (B1), the corrected Ising coefficients (B2), the QAOA mixer note (penalty-based constraint handling with X-mixer; mention XY-mixer for hard one-hot as alternative), parameter table (lambda, mu, p, optimizer, shots, simulator). Make Eq. 7 artifact penalty use regex patterns (not raw `-`). Use consistent weights (normalize each Phi to [0,1] before applying w).
- **Booking engine:** update Algorithm 2 (check + insert inside transaction; outbox after commit).
- **RBAC/PII:** keep short; table generated from `guardrail.PERMISSIONS`; add the PII P/R/F1 table. Drop "mathematically grounded".
- **Docker:** compress to one figure + short table; move compose listing to the supplementary repo / appendix.
- **Experiments:** new subsections: setup (hardware, models, datasets sizes, seeds), QPO scaling, prompt-quality evaluation, latency decomposition + baseline + ablation, retrieval comparison, WER by accent, barge-in trade-off, concurrency, PII accuracy, booking correctness, air-gap verification. Every table/figure `\input` from `generated/`.
- **Discussion:** include honest statements: QAOA vs classical at small n; limits of regex PII on spoken digits; prompt-length effect on TTFT (the old table showed 158 vs 148 ms).
- **Limitations (new):** simulated QAOA only, English-centric, two domains, single GPU, no telephony/PSTN, N turns, LLM-judge bias, Edge-TTS and Groq are cloud.
- **Ethics/Compliance and Data/Code availability (new).**
- **Conclusion:** restate only measured results; future work = real QPU runs with error mitigation, hybrid retrieval, multilingual.

### J4. Fixes that must be applied (known errors in current text)
- STT inconsistency (abstract "Groq Whisper" vs table "Faster-Whisper CUDA"); testbed (RTX 4060 + Ollama Llama-3.2-3B) vs PDF (RTX 4090 + Llama-3.1-8B + Groq). Use only the hardware you really measured on.
- Percent share sentence ("STT 28%, LLM 53%") must be computed, not typed.
- "Quantum optimization achieves ..." -> say "QUBO formulation solved by QAOA simulation matches classical optimum for n <= X".
- "QUBO scales polynomially in circuit depth while exhaustive search is exponential": remove or qualify (QAOA depth/parameter optimization is not guaranteed polynomial-time to optimum).
- "Random templates reduce fitness by 68.5%": regenerate with new data or delete.
- "2.1 seconds extra audio from markdown verbalization": must be measured (TTS duration with/without markdown) or deleted.
- Remove "unexplored academically", "no existing system", "mathematically rigorous".

### J5. References (do this carefully; fabricated/mismatched citations cause desk rejection)
- Look up each entry in Google Scholar/DOI before keeping it. Known suspicious or mismatched entries from the earlier draft: Faster-Whisper "SoftwareX" paper (no such paper; cite the GitHub/CTranslate2 repo as software), Stiefelhagen CLEAR (about tracking, not dialogue latency), Bravyi graph-coloring paper used for a prompt-selection claim, Larson & Traum (verify), Park & Kim RFC 5545 paper, Anagnostopoulos, Cao, Sandnes.
- Add real, verifiable citations: Levinson & Torreira 2015 (turn-taking), Stivers et al. 2009 (PNAS, turn-taking timing), Robertson & Zaragoza 2009, Farhi et al. 2014, Glover et al. 2019, Radford et al. 2023 (Whisper), Kim et al. 2021 (VITS), Frantar 2023 (GPTQ), Lin 2023 (AWQ), Kwon 2023 (vLLM), Khattab 2023 (DSPy), Zhou 2023 (APE), Yang et al. 2023 (OPRO), Lewis 2020 (RAG), Karpukhin 2020 (DPR), Izacard 2022 (Contriever), Temme 2017 (ZNE).
- Remove every `\bibitem` not cited; use BibTeX (`references.bib` + `\bibliographystyle{IEEEtran}`) instead of a hand-written list.

### J6. Build
- `make paper`: runs `make_tables.py`, compiles with `latexmk -pdf`. Zero warnings for undefined refs/citations. Page limit per venue.

---

## Phase K: Final checklist before submission

- [ ] Every number in abstract/intro/conclusion appears in a generated table
- [ ] Contribution count identical in abstract, intro, conclusion
- [ ] Baseline measured on the same hardware; CIs reported
- [ ] QUBO scaling study with n >= 20 and exact optimum reference
- [ ] No claim without a corresponding code path (Docker, theta_words, ACID, Luhn)
- [ ] Privacy configuration table present; Web Speech/Groq/Edge-TTS flagged as cloud
- [ ] Limitations, ethics, data/code availability sections present
- [ ] All references verified; unused removed
- [ ] Repo cleaned; `REPRODUCE.md` works from scratch
- [ ] Proofread by someone else; plagiarism/similarity check (earlier PDF, `.docx`, `.md` drafts overlap heavily with the .tex; ensure only one canonical version is submitted)

---

## Suggested order and effort

| Order | Phase | Effort |
|---|---|---|
| 1 | A, then B (QUBO redesign) | 3-4 days |
| 2 | C (latency + baselines) | 2-3 days |
| 3 | D, F, G (retrieval, booking, PII) | 3-4 days |
| 4 | E (barge-in) | 1 day |
| 5 | H (Docker) or delete claim | 2-3 days |
| 6 | I, J, K (writing + verification) | 4-5 days |

If time is short: do A, B, C, D, J, K and delete the Docker and barge-in claims. A smaller paper whose every number is measured is far more likely to be accepted than a broad one with unverifiable claims.
