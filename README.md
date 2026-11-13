# Voice Agent Studio

> Low-latency conversational voice agent architecture with Quadratic Unconstrained Binary Optimization (QUBO) prompt selection, quantum-assisted task scheduling, and privacy guardrails.

---

## Architecture Overview

Voice Agent Studio decouples offline combinatorial optimization from a deterministic, real-time conversational runtime:

```
┌────────────────────────────────────────────────────────────────────────┐
│                   OFFLINE COMPILATION & OPTIMIZATION                   │
│  Candidate Modules ──► QUBO / Ising Formulation ──► IBM Qiskit (QAOA)  │
│                                                └──► Optimal Prompt     │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   RUNTIME CONVERSATIONAL PIPELINE                      │
│  User Audio ──► Silero VAD / Faster-Whisper STT                        │
│                           │                                            │
│                           ▼                                            │
│                 In-Memory BM25 RAG ──► Streaming LLM (SSE)             │
│                           │                  │                         │
│                           ▼                  ▼                         │
│                 Client Audio Playback ◄── Neural TTS (Edge / pyttsx3)  │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                   POST-CALL ASYNCHRONOUS EXECUTION                     │
│  Deterministic ACID Booking (SQLite WAL)                               │
│  Quantum Task Parallelizer (QTP DAG scheduler)                         │
│  Google Calendar & Sheets Sync + Webhooks                              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Core Subsystems

### 1. Quantum Prompt Optimizer (`qpo/`)
- Formulates multi-objective prompt module selection as a Quadratic Unconstrained Binary Optimization (QUBO) problem mapped to an Ising spin Hamiltonian.
- Balances token budgets, module importance values, domain synergies, and constraint penalties (e.g., zero markdown, strict brevity, PII safety).
- Solvers: IBM Qiskit QAOA (`qiskit-algorithms`), Simulated Annealing, Tabu Search, Greedy, and Brute Force.

### 2. Quantum Task Parallelizer (`qpo/task_parallelizer.py`)
- Dependency-aware DAG scheduler for concurrent post-call workloads (DB persist, TTS audio caching, Google Calendar/Sheets sync, CRM webhooks).
- Computes non-conflicting stage execution schedules via QUBO optimization with fallback to heuristic simulated annealing.

### 3. Speech & Acoustic Pipeline (`speech_service.py`, `static/call-engine.js`)
- **Speech-to-Text (STT):** Local `faster-whisper` (CUDA GPU acceleration or CPU fallback) and Web Speech API.
- **Voice Activity Detection (VAD) & Barge-In:** Real-time RMS acoustic energy thresholding allowing callers to interrupt agent speech seamlessly.
- **Text-to-Speech (TTS):** Low-latency synthesis via Microsoft Edge Neural TTS (`edge-tts`), Windows native SAPI5 (`pyttsx3`), or Piper.

### 4. Booking Engine & Tool Calling (`booking_engine.py`)
- Deterministic calendar slot validation with `BEGIN IMMEDIATE` SQLite transactions preventing concurrent double-bookings.
- Natural language relative date-time parsing (`"tomorrow at 3pm"`, `"next Friday afternoon"`).
- Outbox pattern for external dispatch resilience.

### 5. Guardrails & Role-Based Access Control (`guardrail.py`)
- **4-Tier RBAC:** `owner` (rank 4), `manager` (rank 3), `receptionist` (rank 2), and `viewer` (rank 1).
- **PII Redaction:** Automated regex masking of phone numbers (`[PHONE_REDACTED]`), emails, credit cards (Luhn algorithm validated), and personal identifiers.
- **Prompt Injection Defense:** Input pattern scanning to block delimiter hijack and role reassignment attempts.

---

## Repository Structure

```
├── booking_engine.py       # Deterministic booking logic & schema definitions
├── speech_service.py       # Faster-Whisper, VAD, and TTS integration
├── guardrail.py            # RBAC permissions and PII redaction filters
├── google_integration.py   # Google Calendar and Sheets synchronization
├── Dockerfile              # Container definition for API deployment
├── docker-compose.yml      # Multi-service stack (App, Nginx, Ollama)
├── nginx.conf              # Reverse proxy & TLS termination config
├── requirements.txt        # Pinned Python package dependencies
├── .env.example            # Environment configuration template
│
├── qpo/                    # Quantum Prompt Optimizer & QTP package
│   ├── modules.py          # Prompt module definitions & conflict matrices
│   ├── qubo.py             # QUBO formulation & Ising Hamiltonian mapping
│   ├── solvers.py          # QAOA, SA, Tabu, and classical solvers
│   ├── task_parallelizer.py# Quantum-assisted DAG task scheduler
│   └── run_all.py          # Benchmark scaling execution entrypoint
│
├── static/                 # Frontend assets, Web Audio, and VAD processor
│   ├── app.js              # Dashboard client logic
│   ├── call-engine.js      # WebRTC / audio streaming & barge-in handler
│   ├── index.html          # Agent management UI
│   └── ms_resort.html      # Demo resort booking landing page
│
├── research/               # Academic publication assets & benchmark scripts
│   ├── env_capture.py      # System environment capture (env.json)
│   ├── make_tables.py      # LaTeX table generator for research papers
│   └── research_paper_ieee.tex # Full IEEE manuscript
│
├── scripts/                # Evaluation & benchmark harnesses
│   ├── bench_latency.py    # Pipeline latency benchmark (TTFT, E2E)
│   ├── eval_bargein.py     # Acoustic interruption evaluation
│   ├── eval_pii.py         # Privacy redaction precision/recall harness
│   └── eval_qpo.py         # QUBO solver scaling analysis
│
└── tests/                  # Unit, integration, and audit tests
    ├── test_audit.py       # Mathematical claims & artifact verification
    ├── test_booking_concurrent.py # Race condition & SQLite WAL tests
    ├── test_guardrail_google.py   # RBAC & Google integration tests
    └── test_qtp.py         # QTP DAG scheduler tests
```

---

## Quick Start

### 1. Prerequisites
- Python 3.11+
- Git
- (Optional) NVIDIA GPU with CUDA for local Faster-Whisper acceleration
- (Optional) Docker & Docker Compose for containerized deployment

### 2. Environment Setup

Clone repository and create virtual environment:

```bash
git clone <repo-url>
cd voice-agent-mvp

python -m venv .venv

# Windows (PowerShell):
.venv\Scripts\Activate.ps1
# Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
```

Configure environment variables:

```bash
cp .env.example .env
```

Edit `.env` with your desired configuration:
- **Groq (Default Cloud LLM):** Set `LLM_API_KEY`, `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=llama-3.1-8b-instant`.
- **Ollama (Local LLM):** Set `LLM_BASE_URL=http://localhost:11434/v1`, `LLM_MODEL=qwen2.5:3b`.
- **Twilio (Optional Telephony):** Set `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_NUMBER`.

---

## Running the Application

### Local Development

Start the API and Web interface using Uvicorn:

```bash
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Open browser at `http://localhost:8000` to access the dashboard and demo voice interface.

### Docker Compose Deployment

Run the complete multi-service stack with Nginx reverse proxy:

```bash
docker compose up -d
docker compose logs -f app
```

---

## Testing & Research Verification

### 1. Run Unit & Regression Tests

```bash
python -m pytest qpo/tests/ tests/ -v
```

### 2. Audit Verification

Verify mathematical identities (Ising Hamiltonian proof, token budgets, matrix bounds):

```bash
python -m pytest tests/test_audit.py -v
```

### 3. Reproduce Experimental Results

Execute the standardized benchmark scripts:

```bash
# Capture hardware and environment baseline
python research/env_capture.py

# Run QUBO / QPO prompt solver scaling study
python -m qpo.run_all

# Evaluate PII guardrail precision and recall
python scripts/eval_pii.py

# Evaluate acoustic barge-in detection
python scripts/eval_bargein.py

# Regenerate LaTeX tables for paper publication
python research/make_tables.py
```

Detailed reproduction commands and parameters are documented in [REPRODUCE.md](file:///d:/project_phase_1/mukesh_v1/voice-agent-mvp/REPRODUCE.md).

---

## License

This project is licensed under the terms specified in the [LICENSE](file:///d:/project_phase_1/mukesh_v1/voice-agent-mvp/LICENSE) file.
