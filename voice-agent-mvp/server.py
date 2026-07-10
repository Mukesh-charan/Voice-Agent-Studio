"""
Voice Agent Studio — backend.

Multi-user studio: sign up / log in, each user owns their private agents.
Per agent: knowledge base (RAG), booking-capture tool + optional webhook,
call history. LLM proxied to an OpenAI-compatible API (Groq free tier).

All local and free. Auth uses only the Python standard library.
Deploy-ready: binds 0.0.0.0 and honours $PORT.
"""

import os
import re
import io
import json
import math
import hmac
import hashlib
import secrets
import sqlite3
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import (
    FastAPI, HTTPException, Request, Response, Depends, Cookie,
    UploadFile, File, Form, BackgroundTasks,
)
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.environ.get("LLM_API_KEY", "")
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "llama-3.1-8b-instant")
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

DB_PATH = Path(__file__).parent / "agents.db"

DEFAULT_SYSTEM = (
    "You are a friendly voice assistant on a phone-style call. "
    "Keep every reply short, natural, and conversational — one to three sentences, "
    "as if speaking aloud. Never use lists, markdown, emojis, or code. "
    "Ask one question at a time."
)


# ============================ database ============================
def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _add_columns(conn, table, columns):
    existing = {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}
    for col, ddl in columns:
        if col not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def init_db():
    with db() as conn:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL,
                pw_salt TEXT NOT NULL,
                pw_hash TEXT NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS agents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                system_prompt TEXT NOT NULL DEFAULT '',
                greeting TEXT NOT NULL DEFAULT '',
                voice_name TEXT NOT NULL DEFAULT '',
                rate REAL NOT NULL DEFAULT 1.0,
                lang TEXT NOT NULL DEFAULT 'en-US',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        _add_columns(conn, "agents", [
            ("use_knowledge", "INTEGER NOT NULL DEFAULT 0"),
            ("tools_enabled", "INTEGER NOT NULL DEFAULT 0"),
            ("barge_in", "INTEGER NOT NULL DEFAULT 1"),
            ("user_id", "INTEGER"),
            ("booking_webhook", "TEXT NOT NULL DEFAULT ''"),
        ])
        conn.execute("""CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            filename TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL, content TEXT NOT NULL)""")
        conn.execute("""CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            call_uid TEXT, started_at TEXT, ended_at TEXT,
            num_turns INTEGER NOT NULL DEFAULT 0, transcript TEXT NOT NULL DEFAULT '[]')""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            call_uid TEXT, name TEXT, phone TEXT, datetime TEXT, reason TEXT,
            created_at TEXT NOT NULL)""")

        if conn.execute("SELECT COUNT(*) AS n FROM agents").fetchone()["n"] == 0:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "INSERT INTO agents (name, system_prompt, greeting, voice_name, rate, lang,"
                " created_at, updated_at, use_knowledge, tools_enabled, barge_in)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                ("Aria — Reception",
                 "You are Aria, a warm and concise receptionist for a small clinic. "
                 "Greet callers, answer questions briefly, and help them book an appointment. "
                 "If a knowledge base is provided, answer from it. "
                 "Keep replies to 1-3 spoken sentences. Ask one question at a time.",
                 "Hi! Thanks for calling the clinic. How can I help you today?",
                 "", 1.0, "en-US", now, now, 0, 1, 1),
            )


init_db()


# ============================ helpers ============================
def row_to_dict(row) -> dict:
    return {k: row[k] for k in row.keys()}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- auth ----
def hash_pw(password: str, salt: Optional[str] = None):
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 200_000).hex()
    return salt, h


def verify_pw(password: str, salt: str, expected: str) -> bool:
    _, h = hash_pw(password, salt)
    return hmac.compare_digest(h, expected)


def make_session(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    with db() as conn:
        conn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
                     (token, user_id, now_iso()))
    return token


def set_session_cookie(resp: Response, token: str):
    resp.set_cookie("session", token, max_age=60 * 60 * 24 * 30,
                    httponly=True, samesite="lax", secure=COOKIE_SECURE)


def require_user(session: Optional[str] = Cookie(default=None)) -> dict:
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")
    with db() as conn:
        row = conn.execute(
            "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
            (session,),
        ).fetchone()
    if not row:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return row_to_dict(row)


def owned_agent(conn, agent_id: int, user: dict):
    row = conn.execute("SELECT * FROM agents WHERE id = ? AND user_id = ?",
                       (agent_id, user["id"])).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    return row


# ---- text / retrieval ----
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "a an the of to in is are am be been being and or but if then else for on at by "
    "with as it its this that these those i you he she we they me my your our his her "
    "do does did can could would should will shall may might must have has had not no "
    "yes from up down out about into over under again so than too very just".split()
)


def tokenize(text: str) -> List[str]:
    return [t for t in TOKEN_RE.findall((text or "").lower()) if t not in STOPWORDS and len(t) > 1]


def chunk_text(text: str, size: int = 700, overlap: int = 100) -> List[str]:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text:
        return []
    chunks, i, n = [], 0, len(text)
    while i < n:
        end = min(i + size, n)
        if end < n:
            br = text.rfind(" ", i + size // 2, end)
            if br != -1:
                end = br
        piece = text[i:end].strip()
        if piece:
            chunks.append(piece)
        if end >= n:
            break
        i = max(end - overlap, i + 1)
    return chunks


def bm25_search(query: str, docs: List[str], k: int = 3) -> List[int]:
    if not docs:
        return []
    tok_docs = [tokenize(d) for d in docs]
    N = len(tok_docs)
    avgdl = sum(len(d) for d in tok_docs) / N if N else 0
    df = Counter()
    for d in tok_docs:
        for t in set(d):
            df[t] += 1
    idf = {t: math.log(1 + (N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    q, k1, b = tokenize(query), 1.5, 0.75
    scored = []
    for i, d in enumerate(tok_docs):
        tf, dl, s = Counter(d), len(d) or 1, 0.0
        for t in q:
            if t in tf:
                s += idf.get(t, 0.0) * (tf[t] * (k1 + 1)) / (tf[t] + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scored.append((s, i))
    scored.sort(reverse=True)
    return [i for _, i in scored[:k]]


def retrieve_context(agent_id: int, query: str, k: int = 3) -> List[str]:
    with db() as conn:
        rows = conn.execute("SELECT content FROM chunks WHERE agent_id = ?", (agent_id,)).fetchall()
    docs = [r["content"] for r in rows]
    return [docs[i] for i in bm25_search(query, docs, k=k)]


def extract_text(filename: str, raw: bytes) -> str:
    if (filename or "").lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            return "\n".join((p.extract_text() or "") for p in reader.pages)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Could not read PDF: {e}")
    return raw.decode("utf-8", errors="ignore")


# ---- webhook ----
def booking_payload(agent: dict, booking: dict) -> dict:
    return {
        "event": "booking_captured",
        "agent": {"id": agent.get("id"), "name": agent.get("name")},
        "booking": {k: booking.get(k) for k in ("name", "phone", "datetime", "reason", "created_at")},
    }


async def fire_webhook(url: str, payload: dict):
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            await client.post(url, json=payload)
    except Exception:
        pass  # best-effort; never break the call


# ============================ models ============================
class AuthIn(BaseModel):
    email: str
    password: str


class AgentIn(BaseModel):
    name: str = "Untitled Agent"
    system_prompt: str = ""
    greeting: str = ""
    voice_name: str = ""
    rate: float = 1.0
    lang: str = "en-US"
    use_knowledge: bool = False
    tools_enabled: bool = False
    barge_in: bool = True
    booking_webhook: str = ""


class CallIn(BaseModel):
    agent_id: int
    call_uid: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    transcript: List[dict] = []


# ============================ app ============================
app = FastAPI(title="Voice Agent Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- auth ----
@app.post("/api/auth/register")
def register(body: AuthIn, response: Response):
    email = body.email.strip().lower()
    if not email or not body.password:
        raise HTTPException(status_code=400, detail="Email and password are required.")
    if len(body.password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    with db() as conn:
        if conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone():
            raise HTTPException(status_code=409, detail="That email is already registered.")
        salt, h = hash_pw(body.password)
        cur = conn.execute("INSERT INTO users (email, pw_salt, pw_hash, created_at) VALUES (?,?,?,?)",
                           (email, salt, h, now_iso()))
        uid = cur.lastrowid
        # First user adopts any pre-account (orphan) agents so the seed/demo isn't lost.
        if conn.execute("SELECT COUNT(*) AS n FROM users").fetchone()["n"] == 1:
            conn.execute("UPDATE agents SET user_id = ? WHERE user_id IS NULL", (uid,))
    set_session_cookie(response, make_session(uid))
    return {"email": email}


@app.post("/api/auth/login")
def login(body: AuthIn, response: Response):
    email = body.email.strip().lower()
    with db() as conn:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not row or not verify_pw(body.password, row["pw_salt"], row["pw_hash"]):
        raise HTTPException(status_code=401, detail="Wrong email or password.")
    set_session_cookie(response, make_session(row["id"]))
    return {"email": email}


@app.post("/api/auth/logout")
def logout(response: Response, session: Optional[str] = Cookie(default=None)):
    if session:
        with db() as conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (session,))
    response.delete_cookie("session")
    return {"ok": True}


@app.get("/api/me")
def me(user: dict = Depends(require_user)):
    return {"email": user["email"]}


# ---- agents CRUD (scoped to the logged-in user) ----
@app.get("/api/agents")
def list_agents(user: dict = Depends(require_user)):
    with db() as conn:
        rows = conn.execute("SELECT * FROM agents WHERE user_id = ? ORDER BY updated_at DESC",
                            (user["id"],)).fetchall()
    return [row_to_dict(r) for r in rows]


@app.post("/api/agents")
def create_agent(a: AgentIn, user: dict = Depends(require_user)):
    now = now_iso()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO agents (name, system_prompt, greeting, voice_name, rate, lang,"
            " created_at, updated_at, use_knowledge, tools_enabled, barge_in, user_id, booking_webhook)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.name, a.system_prompt, a.greeting, a.voice_name, a.rate, a.lang, now, now,
             int(a.use_knowledge), int(a.tools_enabled), int(a.barge_in), user["id"], a.booking_webhook),
        )
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        return row_to_dict(owned_agent(conn, agent_id, user))


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, a: AgentIn, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
        conn.execute(
            "UPDATE agents SET name=?, system_prompt=?, greeting=?, voice_name=?, rate=?, lang=?,"
            " updated_at=?, use_knowledge=?, tools_enabled=?, barge_in=?, booking_webhook=? WHERE id=?",
            (a.name, a.system_prompt, a.greeting, a.voice_name, a.rate, a.lang, now_iso(),
             int(a.use_knowledge), int(a.tools_enabled), int(a.barge_in), a.booking_webhook, agent_id),
        )
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    return row_to_dict(row)


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
        for tbl in ("documents", "chunks", "calls", "bookings"):
            conn.execute(f"DELETE FROM {tbl} WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    return {"ok": True}


# ---- knowledge base ----
@app.get("/api/agents/{agent_id}/documents")
def list_documents(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
        rows = conn.execute(
            "SELECT d.id, d.filename, d.created_at,"
            " (SELECT COUNT(*) FROM chunks c WHERE c.document_id = d.id) AS chunks"
            " FROM documents d WHERE d.agent_id = ? ORDER BY d.created_at DESC",
            (agent_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


@app.post("/api/agents/{agent_id}/documents")
async def add_document(agent_id: int, file: Optional[UploadFile] = File(None),
                       text: Optional[str] = Form(None), filename: Optional[str] = Form(None),
                       user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
    if file is not None:
        content = extract_text(file.filename or "upload", await file.read())
        name = file.filename or "upload"
    elif text:
        content, name = text, (filename or "pasted.txt")
    else:
        raise HTTPException(status_code=400, detail="Provide a file or text.")
    content = content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="No readable text found.")
    pieces = chunk_text(content)
    with db() as conn:
        cur = conn.execute("INSERT INTO documents (agent_id, filename, content, created_at) VALUES (?,?,?,?)",
                           (agent_id, name, content, now_iso()))
        conn.executemany("INSERT INTO chunks (agent_id, document_id, content) VALUES (?,?,?)",
                         [(agent_id, cur.lastrowid, p) for p in pieces])
    return {"id": cur.lastrowid, "filename": name, "chunks": len(pieces)}


@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        row = conn.execute("SELECT agent_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row:
            owned_agent(conn, row["agent_id"], user)
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    return {"ok": True}


# ---- call history ----
@app.post("/api/calls")
def save_call(c: CallIn, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, c.agent_id, user)
        cur = conn.execute(
            "INSERT INTO calls (agent_id, call_uid, started_at, ended_at, num_turns, transcript)"
            " VALUES (?,?,?,?,?,?)",
            (c.agent_id, c.call_uid, c.started_at, c.ended_at, len(c.transcript), json.dumps(c.transcript)))
    return {"id": cur.lastrowid}


@app.get("/api/agents/{agent_id}/calls")
def list_calls(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
        rows = conn.execute(
            "SELECT id, call_uid, started_at, ended_at, num_turns FROM calls"
            " WHERE agent_id = ? ORDER BY id DESC", (agent_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/api/calls/{call_id}")
def get_call(call_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call not found")
        owned_agent(conn, row["agent_id"], user)
    d = row_to_dict(row)
    d["transcript"] = json.loads(d.get("transcript") or "[]")
    return d


# ---- bookings ----
@app.get("/api/agents/{agent_id}/bookings")
def list_bookings(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user)
        rows = conn.execute("SELECT * FROM bookings WHERE agent_id = ? ORDER BY id DESC",
                            (agent_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


@app.post("/api/agents/{agent_id}/test-webhook")
async def test_webhook(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user))
    url = (agent.get("booking_webhook") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="No webhook URL set on this agent.")
    sample = {"name": "Test Caller", "phone": "+1 555 0100", "datetime": "tomorrow 3pm",
              "reason": "Webhook test", "created_at": now_iso()}
    try:
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(url, json=booking_payload(agent, sample))
        return {"ok": True, "status": r.status_code}
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Webhook failed: {e}"})


def save_booking(agent_id: int, call_uid: Optional[str], args: dict) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (agent_id, call_uid, name, phone, datetime, reason, created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (agent_id, call_uid, args.get("name"), args.get("phone"),
             args.get("datetime"), args.get("reason"), now_iso()))
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


# ---- chat (RAG + tools) ----
BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "save_booking",
        "description": (
            "Save a booking or lead. Call this once you have the caller's name and at least "
            "one of: a phone number or a desired date/time."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Caller's name"},
                "phone": {"type": "string", "description": "Phone number, if given"},
                "datetime": {"type": "string", "description": "Desired date/time in the caller's words"},
                "reason": {"type": "string", "description": "Reason for the booking/visit"},
            },
            "required": ["name"],
        },
    },
}


async def groq_chat(messages: List[dict], tools: Optional[list] = None) -> dict:
    payload = {"model": MODEL, "messages": messages, "temperature": 0.7, "max_tokens": 300}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
    if r.status_code != 200:
        raise RuntimeError(f"LLM provider error {r.status_code}: {r.text[:400]}")
    return r.json()


@app.post("/chat")
async def chat(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_user)):
    if not API_KEY:
        return JSONResponse(status_code=500,
                            content={"error": "LLM_API_KEY is not set. Add your free Groq key to .env."})

    body = await request.json()
    messages = body.get("messages", [])
    system = (body.get("system") or "").strip() or DEFAULT_SYSTEM
    agent_id = body.get("agent_id")
    call_uid = body.get("call_uid")

    agent = None
    if agent_id:
        with db() as conn:
            agent = row_to_dict(owned_agent(conn, agent_id, user))

    if agent and agent.get("use_knowledge"):
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        ctx = retrieve_context(agent_id, last_user)
        if ctx:
            system += ("\n\nKNOWLEDGE BASE — use only this to answer factual questions. "
                       "If the answer isn't here, say you don't have that information:\n"
                       + "\n---\n".join(ctx))

    tools = [BOOKING_TOOL] if (agent and agent.get("tools_enabled")) else None
    convo = [{"role": "system", "content": system}] + messages

    try:
        resp = await groq_chat(convo, tools=tools)
        msg = resp["choices"][0]["message"]
        events = []
        if msg.get("tool_calls"):
            convo.append(msg)
            for tc in msg["tool_calls"]:
                if tc.get("function", {}).get("name") == "save_booking":
                    try:
                        args = json.loads(tc["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    booking = save_booking(agent_id, call_uid, args)
                    events.append({"type": "booking_saved", "booking": booking})
                    hook = (agent.get("booking_webhook") or "").strip() if agent else ""
                    if hook:
                        background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking saved successfully."})
                else:
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Done."})
            resp2 = await groq_chat(convo, tools=None)
            reply = (resp2["choices"][0]["message"].get("content") or "").strip() or \
                "Done — I've saved that for you. Anything else?"
        else:
            reply = (msg.get("content") or "").strip()
        return {"reply": reply, "events": events}
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Could not reach LLM provider: {e}"})


@app.post("/api/public/chat")
async def public_chat(request: Request, background_tasks: BackgroundTasks):
    if not API_KEY:
        return JSONResponse(status_code=500,
                            content={"error": "LLM_API_KEY is not set."})

    body = await request.json()
    messages = body.get("messages", [])
    agent_id = body.get("agent_id")
    call_uid = body.get("call_uid")

    if not agent_id:
        return JSONResponse(status_code=400, content={"error": "agent_id is required."})

    with db() as conn:
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not row:
            return JSONResponse(status_code=404, content={"error": "Agent not found."})
        agent = row_to_dict(row)

    system = agent.get("system_prompt") or DEFAULT_SYSTEM

    if agent.get("use_knowledge"):
        last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
        ctx = retrieve_context(agent_id, last_user)
        if ctx:
            system += ("\n\nKNOWLEDGE BASE — use only this to answer factual questions. "
                       "If the answer isn't here, say you don't have that information:\n"
                       + "\n---\n".join(ctx))

    tools = [BOOKING_TOOL] if agent.get("tools_enabled") else None
    convo = [{"role": "system", "content": system}] + messages

    try:
        resp = await groq_chat(convo, tools=tools)
        msg = resp["choices"][0]["message"]
        events = []
        if msg.get("tool_calls"):
            convo.append(msg)
            for tc in msg["tool_calls"]:
                if tc.get("function", {}).get("name") == "save_booking":
                    try:
                        args = json.loads(tc["function"].get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    booking = save_booking(agent_id, call_uid, args)
                    events.append({"type": "booking_saved", "booking": booking})
                    hook = (agent.get("booking_webhook") or "").strip()
                    if hook:
                        background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking saved successfully."})
                else:
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Done."})
            resp2 = await groq_chat(convo, tools=None)
            reply = (resp2["choices"][0]["message"].get("content") or "").strip() or \
                "Done — I've saved that for you. Anything else?"
        else:
            reply = (msg.get("content") or "").strip()
            
        if call_uid:
            full_transcript = messages + [{"role": "assistant", "content": reply}]
            with db() as conn:
                existing = conn.execute("SELECT id FROM calls WHERE call_uid = ?", (call_uid,)).fetchone()
                if existing:
                    conn.execute("UPDATE calls SET num_turns = ?, transcript = ?, ended_at = ? WHERE call_uid = ?",
                                 (len(full_transcript), json.dumps(full_transcript), now_iso(), call_uid))
                else:
                    conn.execute("INSERT INTO calls (agent_id, call_uid, started_at, ended_at, num_turns, transcript) VALUES (?,?,?,?,?,?)",
                                 (agent_id, call_uid, now_iso(), now_iso(), len(full_transcript), json.dumps(full_transcript)))
                                 
        return {"reply": reply, "events": events}
    except RuntimeError as e:
        return JSONResponse(status_code=502, content={"error": str(e)})
    except httpx.RequestError as e:
        return JSONResponse(status_code=502, content={"error": f"Could not reach LLM provider: {e}"})


# Static UI mounted last so /api and /chat take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")))
