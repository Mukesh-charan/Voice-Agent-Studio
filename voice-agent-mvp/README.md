# Voice Agent Studio

Enterprise-grade multi-user voice AI studio: build, optimize, guardrail, and deploy real-time voice agents in browser and production environments.

Integrates real-time speech, RAG knowledge retrieval, transactional booking capture, Google Workspace sync, 4-tier RBAC with PII guardrails, Quantum Prompt Optimization (QPO), and containerized deployments.

---

## Key Features

- **Multi-Tenant Studio**: User authentication with session cookies, isolated agent workspaces, and customizable system prompts.
- **Dual Speech Pipeline**:
  - *Browser Mode*: Zero-cost Web Speech API (SpeechRecognition + SpeechSynthesis).
  - *Server-Side Mode*: Faster-Whisper / Groq Whisper (`whisper-large-v3-turbo`) STT, Edge-TTS, and RMS energy-based VAD barge-in (`vad-processor.js`).
- **Knowledge Base (RAG)**: BM25 keyword index per agent with support for `.txt`, `.md`, `.pdf`, and direct text ingestion; supports Google Docs / Drive sync.
- **Transactional Booking Engine**: Concurrency-safe slot validation (`BEGIN IMMEDIATE` SQLite transactions), webhook dispatch, and an internal reliable outbox table.
- **Google Workspace Suite Integration**:
  - **Google Calendar**: Automatic event scheduling, conflict checks, and attendee booking.
  - **Google Meet**: Automated video conference link generation.
  - **Google Sheets**: Real-time row appending and bulk booking synchronization.
  - **Google Docs & Drive**: Direct document parsing into agent RAG knowledge bases.
  - Multi-mode auth: Service Account JSON, OAuth 2.0, or local simulated sandbox.
- **Twilio Real-Time Voice Telephony (PSTN)**:
  - **Inbound Calls**: TwiML `<Connect><Stream>` webhook with multi-agent phone number routing.
  - **Bidirectional WebSocket Media Stream**: Real-time μ-law 8kHz <-> 16kHz PCM transcoding.
  - **Hardware/Cloud Pipeline**: Energy VAD, barge-in interruption, Whisper STT, LLM + tools, SAPI5/Edge-TTS.
  - **Outbound Calls**: Trigger direct phone calls to real phone numbers with sandbox fallback.
  - **Call History**: Call SID tracking, duration, caller ID redaction, and full transcripts.
- **Enterprise Guardrails & RBAC**:
  - 4-Tier access control: `owner`, `manager`, `receptionist`, `viewer`.
  - PII masking: caller phone redaction, guest name masking, Luhn algorithm credit card verification, room note sanitization.
  - In-call conversational guardrail preventing cross-guest data leaks.
- **Quantum Prompt Optimization (QPO)**:
  - Quadratic Unconstrained Binary Optimization (QUBO) module selection.
  - IBM Qiskit QAOA / NumPyMinimumEigensolver integration with fallback to classical simulated annealing (`dimod`/`neal`) and greedy solvers.
- **Evaluation & Reproducibility**: Complete research benchmark suite for latency CDF, PII detection, barge-in trade-offs, and QPO scaling.

---

## Project Structure

```text
voice-agent-mvp/
├── server.py              # Main FastAPI application & API routes
├── twilio_integration.py  # Twilio Voice PSTN, WebSocket streaming, VAD & dialing
├── guardrail.py           # RBAC permissions & PII sanitization engine
├── google_integration.py  # Google Calendar, Meet, Sheets, Docs/Drive integration
├── qpo/                   # Quantum Prompt Optimization package (QUBO, solvers)
│   ├── assemble.py        # Prompt assembly from binary solution vectors
│   ├── modules.py         # 15 contextual prompt modules
│   ├── qubo.py            # Objective matrix & constraint formulation
│   ├── solvers.py         # Qiskit QAOA, Neal SA, Exact solvers
│   └── run_all.py         # End-to-end QPO benchmarking pipeline
├── static/                # Frontend UI, call engine, audio worklets
│   ├── app.js             # Studio dashboard & management UI
│   ├── call-engine.js     # WebRTC/audio streaming and speech orchestrator
│   ├── vad-processor.js   # AudioWorklet RMS energy VAD for barge-in
│   └── ms_resort.html     # White-label hospitality demo portal
├── scripts/               # Latency, PII, ASR, and retrieval benchmark scripts
├── research/              # Academic paper assets, LaTeX tables, evaluation outputs
├── tests/                 # Unit, concurrency, and guardrail test suites
├── Dockerfile             # Container definition for FastAPI backend
├── docker-compose.yml     # Multi-service stack (App + Ollama + Nginx)
├── nginx.conf             # Reverse proxy configuration with SSL termination
├── requirements.txt       # Pinned dependencies
├── CHECKLIST.md           # Pre-submission verification checklist
└── REPRODUCE.md           # Step-by-step benchmark reproduction guide
```

---

## Quick Start (Local)

### 1. Prerequisites
- Python 3.11+
- Free Groq API Key (<https://console.groq.com>) or local Ollama instance

### 2. Environment Setup
```powershell
cd voice-agent-mvp
copy .env.example .env
```

Edit `.env`:
```env
LLM_API_KEY=your_groq_api_key_here
LLM_BASE_URL=https://api.groq.com/openai/v1
LLM_MODEL=llama-3.1-8b-instant
SESSION_COOKIE_SECURE=false
```

### 3. Install Dependencies
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 4. Run Application
```powershell
uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Open `http://localhost:8000` in Chrome or Edge. Register initial user (automatically granted demo agent ownership).

---

## Production Deployment (Docker Compose)

Production stack includes FastAPI app, local Ollama LLM/Whisper service, and Nginx reverse proxy with TLS termination.

```powershell
# Copy environment file
copy .env.example .env

# Start stack
docker compose up -d

# View logs
docker compose logs -f app
```

Set `SESSION_COOKIE_SECURE=true` and place SSL certificates under `./certs/` for HTTPS production environments.

---

## Environment Variables

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `LLM_API_KEY` | `ollama` | API key for LLM provider (Groq, OpenAI, Ollama) |
| `LLM_BASE_URL` | `http://localhost:11434/v1` | Base URL for OpenAI-compatible LLM endpoint |
| `LLM_MODEL` | `llama-3.1-8b-instant` | Target LLM model name |
| `STT_BASE_URL` | Same as `LLM_BASE_URL` | STT provider endpoint |
| `STT_API_KEY` | Same as `LLM_API_KEY` | STT provider authorization key |
| `STT_MODEL` | `whisper-large-v3-turbo` | Speech-to-text model name |
| `TTS_VOICE` | `zira` | Offline SAPI5 / Edge-TTS voice profile |
| `SESSION_COOKIE_SECURE`| `false` | Enable Secure flag on session cookies (require HTTPS) |
| `SESSION_SECRET` | System-generated random | HMAC key for signing user session cookies |
| `TWILIO_ACCOUNT_SID` | Empty | Twilio Account SID for telephony |
| `TWILIO_AUTH_TOKEN` | Empty | Twilio Auth Token |
| `TWILIO_PHONE_NUMBER` | Empty | Twilio registered phone number (E.164) |
| `TWILIO_WEBHOOK_BASE_URL` | Empty | Public HTTPS domain for Twilio webhooks (e.g. ngrok or production) |
| `TWILIO_VALIDATE_SIGNATURE` | `false` | Verify Twilio request signature header |

---

## Twilio Voice Telephony Setup

Connect real-world telephone calls to your agents:

1. **Environment Setup**: Add credentials to `.env`:
   ```env
   TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
   TWILIO_AUTH_TOKEN=your_auth_token_here
   TWILIO_PHONE_NUMBER=+12345678901
   TWILIO_WEBHOOK_BASE_URL=https://your-domain.com
   ```
2. **Inbound Webhook**: In the [Twilio Console](https://console.twilio.com/) -> Phone Numbers -> Configure:
   - **Voice Configuration**: "A Call Comes In" -> **Webhook (HTTP POST)**
   - **URL**: `https://your-domain.com/api/twilio/voice`
3. **Outbound Calling**: Use the studio's "📞 Twilio Phone" tab or call `POST /api/agents/{id}/twilio/dial`.
4. **Sandbox Simulation**: When Twilio credentials are omitted, outbound dialing and webhooks run in intelligent simulated sandbox mode for local offline testing.

---

## Google Workspace Integration Setup

Configure integrations in Agent Setup -> Integrations or via service account:

1. **Service Account**: Place `service_account.json` in root or paste JSON in studio integration settings.
2. **OAuth 2.0**: Supply client ID and refresh tokens.
3. **Sandbox Mode**: When credentials omitted, system falls back to mock responses for testing.

Supported operations:
- `POST /api/agents/{id}/google/sync-sheets` — Sync bookings to Google Sheets.
- `POST /api/agents/{id}/google/import-doc` — Parse Google Doc directly into agent knowledge base.
- `POST /api/agents/{id}/google/test-calendar` — Verify Google Calendar event creation.

---

## Testing & Research Benchmarks

### Run Automated Tests
```powershell
python -m pytest qpo/tests/ tests/ -v
```

### Run Benchmarks
Refer to [REPRODUCE.md](REPRODUCE.md) for full commands:
- **QPO Solvers Evaluation**: `python -m qpo.run_all`
- **PII Guardrail Evaluation**: `python scripts/eval_pii.py`
- **Barge-in VAD Tradeoff**: `python scripts/eval_bargein.py`
- **Latency Benchmark**: `python scripts/bench_latency.py --config cloud-hybrid`
- **Generate LaTeX Tables**: `python research/make_tables.py`
- **Verify Checklist**: See [CHECKLIST.md](CHECKLIST.md)
