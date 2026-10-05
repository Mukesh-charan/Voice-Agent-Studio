# Voice Agent Studio (browser "call", $0 to run)

A multi-user Vapi-style studio: **sign up**, build voice agents, give them a
**knowledge base**, let them **capture bookings** (with optional webhook), **call**
them in the browser, and **review transcripts**. No phone line, no GPU, no paid services.

- **Accounts** — sign up / log in; each user's agents are private to them
- **Agent designer** — create / edit / delete agents (local SQLite)
- **Knowledge base (RAG)** — upload `.txt` / `.md` / `.pdf` or paste text; keyword retrieval
- **Tools** — agent can call `save_booking`; optionally POST each booking to a **webhook**
- **Call history** — full transcripts per call
- **Barge-in** — interrupt the agent while it speaks (per-agent toggle)
- **Speech in/out** — browser Web Speech API (free) · **Brain** — Groq free tier (Llama 3.1 8B)

## Run locally

> New deps were added; re-run the install.

```powershell
cd "voice-agent-mvp"
copy .env.example .env          # paste your free Groq key into LLM_API_KEY
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn server:app --port 8000
```

Open **http://localhost:8000** in **Chrome/Edge** → **create an account** (the first
account adopts the demo agent) → build, save, and call.

Free Groq key: <https://console.groq.com> (no card).

## Using it

1. **Sign up / log in.**
2. **Dashboard** — your agents (badges show enabled features). Create one.
3. **Setup** — name, prompt, greeting, voice, language, and toggles: *knowledge base*,
   *capture bookings*, *barge-in*. Optional **booking webhook URL** + "Send test booking".
4. **Knowledge** — upload a file or paste text (save the agent first).
5. **Call** — press Start and talk. The agent answers from its KB and can capture a booking.
6. **History / Bookings** — review past calls and captured leads.

## Make bookings actionable (webhook)

Set a **Booking webhook URL** on an agent. Each captured booking is POSTed as JSON:

```json
{ "event": "booking_captured",
  "agent": { "id": 1, "name": "Aria" },
  "booking": { "name": "...", "phone": "...", "datetime": "...", "reason": "...", "created_at": "..." } }
```

Point it at a **Zapier / Make / n8n** hook or a **Google Apps Script** web app to turn
bookings into emails, calendar events, or spreadsheet rows — all on free tiers.

## Deploy it (so others can use it)

Browser speech needs a **secure context**, so deploy over **HTTPS** (these hosts give it
automatically). The app honours `$PORT` and binds `0.0.0.0`.

**Option A — quick share via tunnel (no hosting account):**
```powershell
uvicorn server:app --port 8000      # in one terminal
# in another (install cloudflared or ngrok):
cloudflared tunnel --url http://localhost:8000     # gives an https URL
```

**Option B — host (Render / Railway / VPS):**
1. Push this folder to a Git repo.
2. Create a Python web service (start command: `uvicorn server:app --host 0.0.0.0 --port $PORT`).
3. Set env vars: `LLM_API_KEY`, `SESSION_COOKIE_SECURE=true`.
4. Deploy → you get an `https://…` URL anyone can use.

> ⚠️ **Data persistence:** SQLite lives in `agents.db`. On hosts with an ephemeral filesystem,
> that resets on each redeploy. For durable data, use persistent storage or migrate to PostgreSQL.

## Switching the brain (still free, no code change)

OpenAI-compatible — edit `.env` only. Local **Ollama** (`qwen2.5:3b`, offline) for the
private path, or `llama-3.3-70b-versatile` on Groq for stronger tool-calling.

## Notes & limits

- **Auth** is cookie-session based (passwords hashed with PBKDF2). Fine for an MVP; for
  production add HTTPS-only cookies (`SESSION_COOKIE_SECURE=true`), rate limiting, and CSRF.
- **Knowledge base & bookings need a *saved* agent.** Unsaved test calls still converse.
- **Chrome/Edge only** for calls. **Barge-in + laptop speakers** can self-trigger from echo
  (a 2-word threshold helps; toggle it off for pure turn-based).
- Retrieval is **keyword (BM25)**; replies capped at 300 tokens.
