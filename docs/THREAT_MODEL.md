# Threat Model & Security Configuration Matrix

**Voice Agent Studio — Security Analysis**
Version: 1.0 | Date: 2026-10-05

---

## 1. System Overview

```
┌──────────────┐     HTTPS      ┌─────────────────┐    SQLite WAL
│  Browser /   │ ─────────────▶ │  FastAPI Server │ ─────────────▶ agents.db
│  WebRTC mic  │                │  (Uvicorn)      │
└──────────────┘                └────────┬────────┘
                                         │
                          ┌──────────────┼──────────────┐
                          ▼              ▼              ▼
                    Ollama (LLM)  Whisper (STT)   Google APIs
                    localhost     localhost       (optional)
```

**Trust boundaries:**
- Browser ↔ Server: authenticated session cookie (HMAC-SHA256, 32-byte secret)
- Server ↔ LLM/STT: localhost (trusted); in cloud: use TLS mutual auth
- Server ↔ Google: OAuth2 service account JSON
- DB: file-system permissions (Linux: 600, Windows: private)

---

## 2. STRIDE Threat Analysis

### 2.1 Spoofing

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| Session hijacking (cookie theft) | `HttpOnly; SameSite=Strict; Secure` flag; HMAC-signed token | Low |
| API key theft (LLM_API_KEY) | Stored in `.env`, never sent to client | Low |
| Google service-account impersonation | Credentials stored per-agent, never exposed via API | Low |
| Multi-user agent access without permission | RBAC via `agent_members` table + `owned_agent()` guard on every endpoint | Low |

### 2.2 Tampering

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| DB manipulation | SQLite WAL mode; all writes via parameterised queries (no string concat) | Low |
| Prompt injection via user input | `evaluate_conversational_guardrail()` in `guardrail.py` scans for injection patterns | Medium |
| Booking data corruption | `BEGIN IMMEDIATE` transaction + overlap check | Low |
| Knowledge base poisoning | `can_manage_knowledge` permission required; file content sanitised | Medium |

### 2.3 Repudiation

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| Denied booking creation | Outbox table records all booking events with `created_at` and `booking_id` | Low |
| Denied API call | `calls` table stores full transcript per `call_uid` | Low |

### 2.4 Information Disclosure

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| PII in transcripts | `abstract_transcript()` redacts [PHONE_REDACTED], [CARD_REDACTED], [EMAIL_REDACTED] using Luhn + regex | Medium |
| Cross-user agent data leakage | `owned_agent()` checks `agent_members` on every DB-touching endpoint | Low |
| Google credentials exposure | `/api/agents/{id}/google/settings` returns masked preview only | Low |
| LLM API key leakage | Never included in any API response; server-side only | Low |

### 2.5 Denial of Service

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| Large file upload (KB poisoning) | `chunk_text()` caps at 700-char pieces; upstream: add `Content-Length` check | Medium |
| Runaway LLM streaming | `httpx.stream` timeout enforced | Low |
| SQLite lock contention | WAL mode; `BEGIN IMMEDIATE` only in booking path | Low |

### 2.6 Elevation of Privilege

| Threat | Control | Residual Risk |
|--------|---------|---------------|
| Viewer tries to edit settings | `has_permission(role, "can_edit_settings")` enforced on every write endpoint | Low |
| Self-role escalation | `can_manage_members` required; owner cannot be demoted | Low |
| Booking tool prematurely called | `should_enable_booking_tools()` gate before tool list is sent to LLM | Low |

---

## 3. Configuration Matrix

The table below shows which security controls are active for each deployment tier.

| Control | Dev (localhost) | Single-tenant VPS | Multi-tenant Cloud |
|---------|:--------------:|:-----------------:|:-----------------:|
| HTTPS / TLS | ✗ | ✅ (reverse proxy) | ✅ (LB TLS termination) |
| `SESSION_COOKIE_SECURE=true` | ✗ | ✅ | ✅ |
| Rate limiting (Nginx / WAF) | ✗ | Recommended | ✅ |
| DB encryption at rest | ✗ | Recommended (LUKS) | ✅ (cloud KMS) |
| Google credentials isolation | Per-agent JSON | Per-agent JSON | Secret Manager |
| PII redaction (viewer role) | ✅ | ✅ | ✅ |
| RBAC 4-tier | ✅ | ✅ | ✅ |
| Booking overlap lock | ✅ | ✅ | ✅ |
| Outbox / audit trail | ✅ | ✅ | ✅ |
| Prompt injection scan | ✅ | ✅ | ✅ |
| Content-Length upload cap | ✗ | Recommended | ✅ |
| Structured logging / SIEM | ✗ | Recommended | ✅ |

---

## 4. Data Flow & PII Boundaries

```
User audio → Whisper STT → plaintext transcript
  │
  ├──► LLM prompt (assembled from: system_prompt + RAG chunks + transcript)
  │      System prompt: never contains real PII
  │      RAG chunks: operator-controlled KB (treat as trusted input)
  │      Transcript: may contain PII if user speaks it
  │
  └──► DB storage (calls.transcript)
         Served via GET /api/calls/{id}
         Filtered through abstract_transcript(role)
         Viewer / Receptionist: PII redacted
         Manager / Owner: full transcript
```

**PII never stored in:** agent rows, system_prompt field, chunk content (unless operator pastes it).

---

## 5. Assumptions & Out-of-Scope

**Assumptions (must hold for the model to be valid):**
- The operator controls who has `owner` / `manager` roles on each agent.
- The LLM service (Ollama / Groq) is either localhost-trusted or accessed over TLS.
- The server process runs under a non-root OS user.

**Out of scope (separate mitigations needed):**
- Telephony/SIP layer security (handled by carrier/VoIP provider).
- Browser/WebRTC media security (handled by browser security model).
- LLM model jailbreaking beyond the in-call guardrail.
- Compliance (GDPR Art. 30 records, HIPAA BAA) — operator responsibility.

---

## 6. Residual Risks (To-Do)

| Risk | Mitigation Plan | Priority |
|------|----------------|----------|
| Knowledge-base file size DoS | Add `MAX_UPLOAD_BYTES = 10_000_000` check in `add_document` | High |
| Prompt injection not caught by regex | Add embedding-based semantic similarity check | Medium |
| SQLite not suitable for >100 concurrent users | Migrate to PostgreSQL (replace `sqlite3` with `asyncpg`) | Medium |
| No CSRF protection on state-changing POST endpoints | Add CSRF token or verify `Origin` header | Medium |
| Google credentials stored in DB plaintext | Encrypt with Fernet before DB insert | Low |
