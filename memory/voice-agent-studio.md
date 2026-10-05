---
name: voice-agent-studio
description: The user's ongoing project — a Vapi-like voice-agent product, current MVP stack and constraints
metadata:
  type: project
---

The user is building a **Vapi/Twilio alternative**: a website where users configure AI call agents. Long-term vision (decided): **B2B, deployed to the customer's own server/VPC for privacy**, with local open-source LLMs (the production runtime = Pipecat + faster-whisper + vLLM/Llama on a GPU box; spec in `runtime-appliance-spec.md`). Telephony deferred (Twilio/PSTN can't be offline; compliance: 10DLC/TCPA).

**Hard constraint: no extra cost.** They do NOT want paid APIs. Claude API is not included in their Pro plan, so we use **free** services. They confirmed: "if it costs extra I don't want Claude, we can change model."

**Current build — "Voice Agent Studio" MVP** at `Desktop/Project Phase/voice-agent-mvp/`. Browser-based, $0 stack:
- STT + TTS = browser **Web Speech API** (Chrome/Edge, free, no GPU)
- LLM = **Groq free tier** (`llama-3.1-8b-instant`), OpenAI-compatible
- Backend = **FastAPI** + **SQLite**; frontend = vanilla HTML/JS (`call-engine.js` = the STT→LLM→TTS loop)
- Features built & headless-tested: agent CRUD/designer, knowledge base (BM25 keyword RAG, txt/md/pdf), `save_booking` tool + optional booking **webhook** (POST JSON), call history/transcripts, barge-in, **multi-user accounts** (stdlib PBKDF2 + cookie sessions, per-user data isolation + ownership checks), and **deploy-ready** (Dockerfile, `$PORT`, `SESSION_COOKIE_SECURE`; README covers free HTTPS hosts + cloudflared tunnel).
- Token-streaming was deferred (shipped sentence-chunked speech + barge-in instead). Self-hosted/local-model path NOT started yet (deferred — needs GPU).

**Hardware:** their machine = i5 laptop, **no GPU**. Max available = colleague's RTX 4050 (6GB). MVP runs fine on the i5 (no GPU needed). For production-latency tests, rent a cloud GPU (~$0.50/hr).

**Why/how to apply:** Default to free/local options and the OpenAI-compatible interface (so Groq→Ollama/vLLM is a one-line `.env` swap, which is also the bridge to the private self-hosted product). Browser/mic features can't be tested headless — flag those for the user to verify. They like structured AskUserQuestion choices and a recommendation. See [[voice-agent-next-stages]].
