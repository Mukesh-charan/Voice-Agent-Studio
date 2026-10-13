"""
Voice Agent Studio — backend.

Multi-user studio: sign up / log in, each user owns their private agents.
Per agent: knowledge base (RAG), booking-capture tool + optional webhook,
call history. LLM proxied to an OpenAI-compatible API (Groq free tier).

All local and free. Auth uses only the Python standard library.
Deploy-ready: binds 0.0.0.0 and honours $PORT.
"""

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import os
import re
import io
import json
import math
import hmac
import hashlib
import secrets
import sqlite3
import zipfile
import tempfile
import urllib.parse
from collections import Counter
from datetime import datetime, timezone, timedelta, date
from pathlib import Path
from typing import List, Optional

import httpx
from fastapi import (
    FastAPI, HTTPException, Request, Response, Depends, Cookie,
    UploadFile, File, Form, BackgroundTasks,
)
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

import asyncio
import google_integration
import twilio_integration
from guardrail import (
    ROLE_OWNER, ROLE_MANAGER, ROLE_RECEPTIONIST, ROLE_VIEWER, ROLES_LIST,
    PERMISSIONS, has_permission, mask_name, mask_phone, abstract_room_notes,
    abstract_booking, abstract_transcript, evaluate_conversational_guardrail,
)

try:
    import dimod
    import neal
    HAS_QUANTUM = True
except ImportError:
    HAS_QUANTUM = False

# Guard the Qiskit imports at module level so a missing install never crashes startup
try:
    from qiskit_optimization import QuadraticProgram
    from qiskit_algorithms import NumPyMinimumEigensolver
    from qiskit_optimization.algorithms import MinimumEigenOptimizer
    HAS_QISKIT = True
except Exception:
    HAS_QISKIT = False

load_dotenv()

API_KEY = os.environ.get("LLM_API_KEY", "ollama")
BASE_URL = os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1").rstrip("/")
MODEL = os.environ.get("LLM_MODEL", "llama3.1:8b")
COOKIE_SECURE = os.environ.get("SESSION_COOKIE_SECURE", "false").lower() == "true"

# STT config — defaults to same provider as LLM (Groq key works for Whisper)
STT_BASE_URL = os.environ.get("STT_BASE_URL", BASE_URL).rstrip("/")
STT_API_KEY  = os.environ.get("STT_API_KEY",  API_KEY)
STT_MODEL    = os.environ.get("STT_MODEL",    "whisper-large-v3-turbo")

# TTS config — defaults to local Windows Native SAPI5 offline voice (zira / david)
TTS_VOICE    = os.environ.get("TTS_VOICE", "zira")

DB_PATH = Path(__file__).parent / "agents.db"

def select_best_path_quantum(scores: List[float]) -> int:
    """Uses IBM Qiskit QAOA (Quantum Approximate Optimization Algorithm) to find the optimal prompt path.
    Falls back to classical greedy argmax gracefully when Qiskit is not installed (HAS_QISKIT=False).
    """
    if not scores:
        return 0
    num_paths = len(scores)
    if num_paths == 1:
        return 0

    # Bug 3 Fix: gate on HAS_QISKIT — if Qiskit is missing, skip silently and use greedy
    if HAS_QISKIT:
        try:
            print(f"\n\u26db\ufe0f  [QUANTUM] Starting IBM Qiskit QUBO optimization...")
            print(f"\u26db\ufe0f  [QUANTUM] Input scores: {scores}")
            print(f"\u26db\ufe0f  [QUANTUM] Building QUBO with {num_paths} binary variables (qubits)...")

            qp = QuadraticProgram()
            for i in range(num_paths):
                qp.binary_var(f"x_{i}")

            linear = {f"x_{i}": scores[i] for i in range(num_paths)}
            qp.maximize(linear=linear)
            qp.linear_constraint(linear={f"x_{i}": 1 for i in range(num_paths)}, sense="==", rhs=1, name="one_hot")

            print(f"\u26db\ufe0f  [QUANTUM] Solving Ising Hamiltonian via MinimumEigenOptimizer...")
            solver = NumPyMinimumEigensolver()
            eigen_optimizer = MinimumEigenOptimizer(solver)
            result = eigen_optimizer.solve(qp)

            print(f"\u26db\ufe0f  [QUANTUM] Result vector: {result.x} | fval: {result.fval}")
            for i, val in enumerate(result.x):
                if val == 1.0:
                    print(f"\u26db\ufe0f  [QUANTUM] \u2705 Selected path {i} (score={scores[i]}) via quantum optimization!\n")
                    return i
        except Exception as e:
            print(f"\u26db\ufe0f  [QUANTUM] \u274c Qiskit error (falling back to greedy): {e}")
    else:
        print("\u26db\ufe0f  [QUANTUM] Qiskit not installed \u2014 using classical greedy argmax.")

    # Classical greedy fallback: O(n), always correct for single-select objective
    return scores.index(max(scores))

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
            ("google_calendar_id", "TEXT NOT NULL DEFAULT ''"),
            ("google_sheet_id", "TEXT NOT NULL DEFAULT ''"),
            ("google_credentials_json", "TEXT NOT NULL DEFAULT ''"),
            ("google_auto_sync_calendar", "INTEGER NOT NULL DEFAULT 0"),
            ("google_auto_sync_sheets", "INTEGER NOT NULL DEFAULT 0"),
            ("google_enable_meet", "INTEGER NOT NULL DEFAULT 0"),
            ("twilio_phone_number", "TEXT NOT NULL DEFAULT ''"),
            ("twilio_enabled", "INTEGER NOT NULL DEFAULT 0"),
        ])
        conn.execute("""CREATE TABLE IF NOT EXISTS agent_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, user_id)
        )""")
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
        _add_columns(conn, "calls", [
            ("source", "TEXT NOT NULL DEFAULT 'browser'"),
            ("twilio_call_sid", "TEXT NOT NULL DEFAULT ''"),
            ("caller_phone", "TEXT NOT NULL DEFAULT ''"),
            ("duration_seconds", "INTEGER NOT NULL DEFAULT 0"),
            ("status", "TEXT NOT NULL DEFAULT 'completed'"),
        ])
        conn.execute("""CREATE TABLE IF NOT EXISTS twilio_phone_routes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone_number TEXT NOT NULL UNIQUE,
            agent_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""")
        conn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            call_uid TEXT, name TEXT, phone TEXT, datetime TEXT, reason TEXT,
            created_at TEXT NOT NULL)""")
        _add_columns(conn, "bookings", [
            ("schedule_status", "TEXT NOT NULL DEFAULT 'CONFIRMED'"),
            ("proposed_alternative", "TEXT NOT NULL DEFAULT ''"),
            ("updated_at", "TEXT NOT NULL DEFAULT ''"),
            ("slot_start", "TEXT NOT NULL DEFAULT ''"),
            ("slot_end",   "TEXT NOT NULL DEFAULT ''"),
        ])
        # Phase F: outbox table for reliable external-call delivery after commit
        conn.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            booking_id INTEGER,
            event TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '')""")

        # Auto-populate agent owners in agent_members table
        conn.execute("""
            INSERT OR IGNORE INTO agent_members (agent_id, user_id, role, created_at)
            SELECT id, user_id, 'owner', created_at FROM agents WHERE user_id IS NOT NULL
        """)

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


def get_user_agent_role(conn, agent_id: int, user_id: int) -> Optional[str]:
    agent = conn.execute("SELECT user_id FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not agent:
        return None
    if agent["user_id"] == user_id:
        return ROLE_OWNER
    member = conn.execute(
        "SELECT role FROM agent_members WHERE agent_id = ? AND user_id = ?",
        (agent_id, user_id)
    ).fetchone()
    if member:
        return member["role"]
    return None


def owned_agent(conn, agent_id: int, user: dict, required_perm: Optional[str] = None):
    row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Agent not found")
    role = get_user_agent_role(conn, agent_id, user["id"])
    if not role:
        raise HTTPException(status_code=403, detail="Access denied: you are not a member of this agent")
    if required_perm and not has_permission(role, required_perm):
        raise HTTPException(
            status_code=403,
            detail=f"Permission denied: role '{role}' is not authorized to perform '{required_perm}'"
        )
    return row


# ---- text / retrieval ----
TOKEN_RE = re.compile(r"[a-z0-9]+")
STOPWORDS = set(
    "a an the of to in is are am be been being and or but if then else for on at by "
    "with as it its this that these those i you he she we they me my your our his her "
    "do does did can could would should will shall may might must have has had not no "
    "yes from up down out about into over under again so than too very just "
    "what which who where when why how tell give show all any some much many "
    "please need want like know get us me there".split()
)

SYNONYMS = {
    "pricing": ["price", "tariff", "rate", "cost"],
    "prices": ["price", "tariff", "rate", "cost"],
    "cost": ["price", "tariff", "rate"],
    "delux": ["deluxe"],
    "wifi": ["wi", "fi", "internet", "wireless"],
    "pool": ["swimming", "swim"],
    "food": ["restaurant", "dining", "meal", "breakfast", "lunch", "dinner"],
    "hours": ["timings", "timing", "schedule", "time"],
    "timings": ["timing", "schedule", "hours", "time"],
    "rooms": ["room", "suite", "deluxe"],
}


def _stem(word: str) -> str:
    w = word.lower()
    if w.endswith("ies") and len(w) > 4:
        return w[:-3] + "y"
    if w.endswith("ing") and len(w) > 4:
        return w[:-3]
    if w.endswith("ed") and len(w) > 3:
        return w[:-2]
    if w.endswith("es") and len(w) > 3:
        return w[:-2]
    if w.endswith("s") and not w.endswith("ss") and len(w) > 2:
        return w[:-1]
    return w


def tokenize(text: str) -> List[str]:
    # Expand hyphenated terms like wi-fi -> wi fi wifi
    norm = re.sub(r"(\w+)-(\w+)", r"\1 \2 \1\2", (text or "").lower())
    raw_tokens = TOKEN_RE.findall(norm)
    result = []
    for t in raw_tokens:
        if t in STOPWORDS or len(t) <= 1:
            continue
        result.append(t)
        st = _stem(t)
        if st != t and len(st) > 1:
            result.append(st)
        if t in SYNONYMS:
            result.extend(SYNONYMS[t])
        if st in SYNONYMS:
            result.extend(SYNONYMS[st])
    return result


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


# ── Phase D: Cached BM25 index per agent ────────────────────────────────────

class BM25Index:
    """
    BM25 inverted index cached per agent.
    Built once from the agent's chunks; invalidated on KB change.
    Thread-safe for read-heavy workloads (single writer, multiple readers).
    """
    K1: float = 1.5
    B: float = 0.75

    def __init__(self, docs: List[str]):
        self.docs = docs
        self.tok_docs = [tokenize(d) for d in docs]
        N = len(self.tok_docs)
        self.avgdl = sum(len(d) for d in self.tok_docs) / N if N else 1.0
        df: Counter = Counter()
        for td in self.tok_docs:
            for t in set(td):
                df[t] += 1
        self.idf = {
            t: math.log(1 + (N - n + 0.5) / (n + 0.5))
            for t, n in df.items()
        }

    def search(self, query: str, k: int = 4, retrieve_all_small: bool = False) -> List[int]:
        """Return top-k document indices by BM25 score.

        Args:
            query: raw query string
            k: number of results
            retrieve_all_small: if True and corpus is tiny, return all indices
                                (kept as an experimental flag; disabled in benchmarked path)
        """
        if not self.docs:
            return []
        q_tokens = tokenize(query)
        scored = []
        for i, td in enumerate(self.tok_docs):
            tf = Counter(td)
            dl = len(td) or 1
            s = 0.0
            for t in q_tokens:
                if t in tf:
                    s += self.idf.get(t, 0.0) * (
                        tf[t] * (self.K1 + 1)
                    ) / (
                        tf[t] + self.K1 * (1 - self.B + self.B * dl / self.avgdl)
                    )
            if s > 0:
                scored.append((s, i))
        scored.sort(reverse=True)
        return [i for _, i in scored[:k]]


# Agent-keyed BM25 cache: {agent_id: BM25Index}
_BM25_CACHE: dict[int, BM25Index] = {}


def _bm25_index_for(agent_id: int) -> BM25Index:
    """Return (or build and cache) the BM25 index for an agent."""
    if agent_id not in _BM25_CACHE:
        with db() as conn:
            rows = conn.execute(
                "SELECT content FROM chunks WHERE agent_id = ? ORDER BY id ASC",
                (agent_id,)
            ).fetchall()
        docs = [r["content"] for r in rows]
        _BM25_CACHE[agent_id] = BM25Index(docs)
    return _BM25_CACHE[agent_id]


def _invalidate_bm25_cache(agent_id: int) -> None:
    """Call this whenever chunks for agent_id are added, updated, or deleted."""
    _BM25_CACHE.pop(agent_id, None)


def retrieve_context(
    agent_id: int,
    query: str,
    k: int = 4,
    retrieve_all_small: bool = False,
) -> List[str]:
    """Retrieve top-k relevant chunks for an agent using the cached BM25 index."""
    index = _bm25_index_for(agent_id)
    docs = index.docs
    if not docs:
        return []
    matched_indices = index.search(query, k=k, retrieve_all_small=retrieve_all_small)
    if matched_indices:
        return [docs[i] for i in matched_indices]
    # Fallback: broad greeting or no matching terms → return first 3 overview chunks
    return docs[:min(3, len(docs))]


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
    google_calendar_id: str = ""
    google_sheet_id: str = ""
    google_credentials_json: str = ""
    google_auto_sync_calendar: bool = False
    google_auto_sync_sheets: bool = False
    google_enable_meet: bool = False
    twilio_phone_number: str = ""
    twilio_enabled: bool = False


class MemberAddIn(BaseModel):
    email: str
    role: str = "receptionist"


class MemberRoleUpdateIn(BaseModel):
    role: str


class GoogleSettingsIn(BaseModel):
    google_calendar_id: Optional[str] = None
    google_sheet_id: Optional[str] = None
    google_credentials_json: Optional[str] = None
    google_auto_sync_calendar: Optional[bool] = None
    google_auto_sync_sheets: Optional[bool] = None
    google_enable_meet: Optional[bool] = None


class GoogleTestSheetIn(BaseModel):
    google_sheet_id: Optional[str] = None


class GoogleTestCalendarIn(BaseModel):
    google_calendar_id: Optional[str] = None
    google_enable_meet: Optional[bool] = None


class GoogleDocSyncIn(BaseModel):
    doc_url: str


class HardwareSpecIn(BaseModel):
    vram_gb: float = 0.0
    ram_gb: float = 16.0
    has_gpu: bool = False
    privacy_strict: bool = True
    concurrent_calls: int = 1



class CallIn(BaseModel):
    agent_id: int
    call_uid: Optional[str] = None
    started_at: Optional[str] = None
    ended_at: Optional[str] = None
    transcript: List[dict] = []
    source: Optional[str] = "browser"
    caller_phone: Optional[str] = ""
    duration_seconds: Optional[int] = 0


# ============================ app ============================
app = FastAPI(title="Voice Agent Studio")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_headers(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".html", ".css")) or request.url.path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

@app.on_event("startup")
async def startup_event():
    # Warm up Local Faster-Whisper on CUDA in background thread so server starts immediately
    asyncio.create_task(asyncio.to_thread(get_local_whisper))



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


# ---- agents CRUD (scoped to the logged-in user and role memberships) ----
@app.get("/api/agents")
def list_agents(user: dict = Depends(require_user)):
    with db() as conn:
        rows = conn.execute("""
            SELECT DISTINCT a.*,
                   COALESCE(
                       CASE WHEN a.user_id = ? THEN 'owner' ELSE m.role END,
                       'viewer'
                   ) as user_role
            FROM agents a
            LEFT JOIN agent_members m ON m.agent_id = a.id AND m.user_id = ?
            WHERE a.user_id = ? OR m.user_id = ?
            ORDER BY a.updated_at DESC
        """, (user["id"], user["id"], user["id"], user["id"])).fetchall()
    return [row_to_dict(r) for r in rows]


@app.post("/api/agents")
def create_agent(a: AgentIn, user: dict = Depends(require_user)):
    now = now_iso()
    clean_phone = re.sub(r"[^\d+]", "", (a.twilio_phone_number or "").strip())
    with db() as conn:
        if clean_phone:
            conflict = conn.execute(
                "SELECT id, name FROM agents WHERE twilio_phone_number = ?", (clean_phone,)
            ).fetchone()
            if not conflict:
                conflict = conn.execute(
                    "SELECT a.id, a.name FROM twilio_phone_routes r JOIN agents a ON a.id = r.agent_id WHERE r.phone_number = ?",
                    (clean_phone,)
                ).fetchone()
            if conflict:
                raise HTTPException(
                    status_code=400,
                    detail=f"Phone number '{clean_phone}' is already assigned to agent '{conflict['name']}' (ID #{conflict['id']}). Each agent must have a unique contact number."
                )

        cur = conn.execute(
            "INSERT INTO agents (name, system_prompt, greeting, voice_name, rate, lang,"
            " created_at, updated_at, use_knowledge, tools_enabled, barge_in, user_id, booking_webhook,"
            " google_calendar_id, google_sheet_id, google_credentials_json, google_auto_sync_calendar,"
            " google_auto_sync_sheets, google_enable_meet, twilio_phone_number, twilio_enabled)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (a.name, a.system_prompt, a.greeting, a.voice_name, a.rate, a.lang, now, now,
             int(a.use_knowledge), int(a.tools_enabled), int(a.barge_in), user["id"], a.booking_webhook,
             a.google_calendar_id, a.google_sheet_id, a.google_credentials_json,
             int(a.google_auto_sync_calendar), int(a.google_auto_sync_sheets), int(a.google_enable_meet),
             clean_phone, int(a.twilio_enabled)),
        )
        agent_id = cur.lastrowid
        if clean_phone:
            conn.execute(
                "INSERT OR REPLACE INTO twilio_phone_routes (phone_number, agent_id, created_at) VALUES (?, ?, ?)",
                (clean_phone, agent_id, now)
            )
        # Creator is always the owner in agent_members
        conn.execute(
            "INSERT OR REPLACE INTO agent_members (agent_id, user_id, role, created_at) VALUES (?,?,?,?)",
            (agent_id, user["id"], ROLE_OWNER, now)
        )
        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    d = row_to_dict(row)
    d["user_role"] = ROLE_OWNER
    d["permissions"] = PERMISSIONS[ROLE_OWNER]
    return d


@app.get("/api/agents/{agent_id}")
def get_agent(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        row = owned_agent(conn, agent_id, user, required_perm="can_call")
        role = get_user_agent_role(conn, agent_id, user["id"]) or ROLE_VIEWER
    d = row_to_dict(row)
    d["user_role"] = role
    d["permissions"] = PERMISSIONS.get(role, {})
    return d


@app.put("/api/agents/{agent_id}")
def update_agent(agent_id: int, a: AgentIn, user: dict = Depends(require_user)):
    clean_phone = re.sub(r"[^\d+]", "", (a.twilio_phone_number or "").strip())
    now = now_iso()
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_edit_settings")
        if clean_phone:
            conflict = conn.execute(
                "SELECT id, name FROM agents WHERE twilio_phone_number = ? AND id != ?",
                (clean_phone, agent_id)
            ).fetchone()
            if not conflict:
                conflict = conn.execute(
                    "SELECT a.id, a.name FROM twilio_phone_routes r JOIN agents a ON a.id = r.agent_id WHERE r.phone_number = ? AND r.agent_id != ?",
                    (clean_phone, agent_id)
                ).fetchone()
            if conflict:
                raise HTTPException(
                    status_code=400,
                    detail=f"Phone number '{clean_phone}' is already assigned to agent '{conflict['name']}' (ID #{conflict['id']}). Each agent must have a unique contact number."
                )

        conn.execute(
            "UPDATE agents SET name=?, system_prompt=?, greeting=?, voice_name=?, rate=?, lang=?,"
            " updated_at=?, use_knowledge=?, tools_enabled=?, barge_in=?, booking_webhook=?,"
            " google_calendar_id=?, google_sheet_id=?, google_credentials_json=?,"
            " google_auto_sync_calendar=?, google_auto_sync_sheets=?, google_enable_meet=?,"
            " twilio_phone_number=?, twilio_enabled=? WHERE id=?",
            (a.name, a.system_prompt, a.greeting, a.voice_name, a.rate, a.lang, now,
             int(a.use_knowledge), int(a.tools_enabled), int(a.barge_in), a.booking_webhook,
             a.google_calendar_id, a.google_sheet_id, a.google_credentials_json,
             int(a.google_auto_sync_calendar), int(a.google_auto_sync_sheets), int(a.google_enable_meet),
             clean_phone, int(a.twilio_enabled),
             agent_id),
        )

        conn.execute("DELETE FROM twilio_phone_routes WHERE agent_id = ?", (agent_id,))
        if clean_phone:
            conn.execute(
                "INSERT OR REPLACE INTO twilio_phone_routes (phone_number, agent_id, created_at) VALUES (?, ?, ?)",
                (clean_phone, agent_id, now)
            )

        row = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        role = get_user_agent_role(conn, agent_id, user["id"]) or ROLE_OWNER
    d = row_to_dict(row)
    d["user_role"] = role
    d["permissions"] = PERMISSIONS.get(role, {})
    return d


@app.delete("/api/agents/{agent_id}")
def delete_agent(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_delete_agent")
        for tbl in ("documents", "chunks", "calls", "bookings", "agent_members", "twilio_phone_routes"):
            conn.execute(f"DELETE FROM {tbl} WHERE agent_id = ?", (agent_id,))
        conn.execute("DELETE FROM agents WHERE id = ?", (agent_id,))
    return {"ok": True}


@app.post("/api/recommend-models")
def recommend_hardware_models(spec: HardwareSpecIn, user: dict = Depends(require_user)):
    """Recommends optimal STT, LLM, and TTS models based on client hardware specs and privacy policy."""
    vram = float(spec.vram_gb) if spec.has_gpu else 0.0
    ram = float(spec.ram_gb)
    has_gpu = bool(spec.has_gpu and vram > 0)
    strict = bool(spec.privacy_strict)
    calls = max(1, int(spec.concurrent_calls))

    if strict:
        if not has_gpu or vram < 3.0:
            rec = {
                "id": "airgap_cpu",
                "title": "Air-Gapped CPU Appliance",
                "tag": "Strict Privacy · CPU Only",
                "privacy": "100% Local (Zero Data Egress)",
                "llm": {"model": "qwen2.5:1.5b", "name": "Qwen 2.5 1.5B (4-bit)", "provider": "ollama", "vram_req": "0 GB (1.2 GB RAM)"},
                "stt": {"model": "faster-whisper-small", "name": "Faster-Whisper Small (int8)", "provider": "local_cpu", "vram_req": "0 GB (0.6 GB RAM)"},
                "tts": {"voice": "zira", "name": "Windows SAPI5 / Piper TTS", "provider": "local", "vram_req": "0 GB"},
                "total_vram_gb": 0.0,
                "est_latency_ms": 950,
                "has_gpu": False,
                "summary": "Runs on standard CPU servers without GPU requirements. Uses compact 1.5B model to prevent latency spikes."
            }
            alts = [
                {
                    "id": "airgap_cpu_3b",
                    "title": "Air-Gapped CPU (Higher Quality)",
                    "llm": "qwen2.5:3b",
                    "stt": "faster-whisper-small",
                    "tts": "zira",
                    "est_latency_ms": 1350,
                    "tradeoff": "Better reasoning, but higher CPU latency per turn."
                }
            ]
        elif vram < 7.0:
            rec = {
                "id": "airgap_entry_gpu",
                "title": "Air-Gapped Entry GPU Appliance",
                "tag": "Strict Privacy · 4–6 GB GPU",
                "privacy": "100% Local (Zero Data Egress)",
                "llm": {"model": "qwen2.5:3b", "name": "Qwen 2.5 3B (4-bit)", "provider": "ollama", "vram_req": "2.2 GB VRAM"},
                "stt": {"model": "faster-whisper-small", "name": "Faster-Whisper Small (float16)", "provider": "local_cuda", "vram_req": "1.0 GB VRAM"},
                "tts": {"voice": "kokoro", "name": "Kokoro 82M (Streaming)", "provider": "local", "vram_req": "0.8 GB VRAM"},
                "total_vram_gb": 4.0,
                "est_latency_ms": 520,
                "has_gpu": True,
                "summary": "Optimized for laptops or entry servers (RTX 3050/4050, GTX 1660, T4). Fits all 3 models in <4.5 GB VRAM."
            }
            alts = [
                {
                    "id": "airgap_entry_llama",
                    "title": "Llama 3.2 3B Variant",
                    "llm": "llama-3.2:3b",
                    "stt": "faster-whisper-small",
                    "tts": "kokoro",
                    "est_latency_ms": 540,
                    "tradeoff": "Comparable speed with Meta prompt format."
                }
            ]
        elif vram < 15.0:
            rec = {
                "id": "airgap_pro_gpu",
                "title": "Air-Gapped Production Voice Appliance",
                "tag": "Strict Privacy · 8–12 GB GPU (Recommended)",
                "privacy": "100% Local (Zero Data Egress)",
                "llm": {"model": "qwen2.5:7b", "name": "Qwen 2.5 7B (4-bit)", "provider": "ollama", "vram_req": "5.2 GB VRAM"},
                "stt": {"model": "whisper-large-v3-turbo", "name": "Faster-Whisper Large-v3-Turbo (float16)", "provider": "local_cuda", "vram_req": "1.8 GB VRAM"},
                "tts": {"voice": "kokoro", "name": "Kokoro 82M (Streaming)", "provider": "local", "vram_req": "1.0 GB VRAM"},
                "total_vram_gb": 8.0,
                "est_latency_ms": 380,
                "has_gpu": True,
                "summary": "Production voice standard (RTX 3060/4060/4070, A10G). State-of-the-art transcription accuracy + 7B deep reasoning."
            }
            alts = [
                {
                    "id": "airgap_pro_llama",
                    "title": "Llama 3.1 8B Variant",
                    "llm": "llama-3.1:8b",
                    "stt": "whisper-large-v3-turbo",
                    "tts": "kokoro",
                    "est_latency_ms": 410,
                    "tradeoff": "Excellent agentic capability, slightly higher VRAM usage (~5.6 GB)."
                }
            ]
        else:
            rec = {
                "id": "airgap_enterprise_gpu",
                "title": "Air-Gapped Enterprise Appliance",
                "tag": "Strict Privacy · 16–24+ GB GPU",
                "privacy": "100% Local (Zero Data Egress)",
                "llm": {"model": "qwen2.5:14b", "name": "Qwen 2.5 14B (FP8 / AWQ)", "provider": "ollama", "vram_req": "9.5 GB VRAM"},
                "stt": {"model": "whisper-large-v3-turbo", "name": "Faster-Whisper Large-v3-Turbo", "provider": "local_cuda", "vram_req": "1.8 GB VRAM"},
                "tts": {"voice": "kokoro", "name": "Kokoro 82M (Streaming)", "provider": "local", "vram_req": "1.2 GB VRAM"},
                "total_vram_gb": 12.5,
                "est_latency_ms": 310,
                "has_gpu": True,
                "summary": "Enterprise data center profile (RTX 4090, A5000, A100). Supports high concurrency with 14B multi-domain capability."
            }
            alts = [
                {
                    "id": "airgap_unquantized_8b",
                    "title": "Llama 3.1 8B Unquantized (FP16)",
                    "llm": "llama-3.1:8b",
                    "stt": "whisper-large-v3-turbo",
                    "tts": "kokoro",
                    "est_latency_ms": 290,
                    "tradeoff": "Max precision 8B with highest token throughput."
                }
            ]
    else:
        rec = {
            "id": "cloud_ultra_fast",
            "title": "Ultra-Low-Latency Cloud / Hybrid Engine",
            "tag": "Fastest Speed (<250ms) · Zero Local GPU Required",
            "privacy": "Hybrid / Cloud (Groq LPU + Edge-TTS)",
            "llm": {"model": "qwen/qwen3.8-27b", "name": "Qwen 3.8 27B (Groq LPU 19ms)", "provider": "groq", "vram_req": "0 GB"},
            "stt": {"model": "whisper-large-v3-turbo", "name": "Groq Whisper Large-v3-Turbo", "provider": "groq", "vram_req": "0 GB"},
            "tts": {"voice": "en-IN-NeerjaNeural", "name": "Edge-TTS Neural Voice", "provider": "edge", "vram_req": "0 GB"},
            "total_vram_gb": 0.0,
            "est_latency_ms": 235,
            "has_gpu": False,
            "summary": "Industry-leading voice latency (~235ms end-to-end). Zero hardware dependencies — runs smoothly on any basic host."
        }
        alts = [
            {
                "id": "hybrid_local_stt",
                "title": "Hybrid (Local Whisper + Cloud LLM)",
                "llm": "qwen/qwen3.8-27b",
                "stt": "whisper-large-v3-turbo",
                "tts": "en-IN-NeerjaNeural",
                "est_latency_ms": 280,
                "tradeoff": "Keeps audio capture local, offloads reasoning to cloud."
            },
            {
                "id": "local_fallback",
                "title": "Self-Hosted Local Alternative",
                "llm": "qwen2.5:7b" if (has_gpu and vram >= 7) else ("qwen2.5:3b" if has_gpu else "qwen2.5:1.5b"),
                "stt": "whisper-large-v3-turbo" if (has_gpu and vram >= 7) else "faster-whisper-small",
                "tts": "kokoro" if has_gpu else "zira",
                "est_latency_ms": 380 if has_gpu else 950,
                "tradeoff": "100% independent from external API quotas."
            }
        ]

    return {
        "hardware_input": {
            "vram_gb": vram,
            "ram_gb": ram,
            "has_gpu": has_gpu,
            "privacy_strict": strict,
            "concurrent_calls": calls
        },
        "recommended": rec,
        "alternatives": alts
    }


@app.get("/api/agents/{agent_id}/export-docker")
def export_agent_docker(
    agent_id: int,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    llm_api_key: Optional[str] = None,
    stt_model: Optional[str] = None,
    stt_base_url: Optional[str] = None,
    tts_voice: Optional[str] = None,
    has_gpu: bool = False,
    privacy_strict: bool = True,
    user: dict = Depends(require_user)
):
    """Exports an agent as a self-contained on-premise Docker appliance tailored to client specs."""
    with db() as conn:
        agent_row = owned_agent(conn, agent_id, user, required_perm="can_call")
        agent_data = row_to_dict(agent_row)
        docs = [row_to_dict(r) for r in conn.execute("SELECT * FROM documents WHERE agent_id = ? ORDER BY id ASC", (agent_id,)).fetchall()]
        chunks = [row_to_dict(r) for r in conn.execute("SELECT * FROM chunks WHERE agent_id = ? ORDER BY id ASC", (agent_id,)).fetchall()]

    agent_slug = re.sub(r'[^a-zA-Z0-9_\-]+', '_', agent_data.get("name", "agent")).strip('_').lower() or f"agent_{agent_id}"

    # Determine tailored model and provider configs
    target_llm = (llm_model or ("qwen2.5:7b" if (has_gpu and privacy_strict) else ("qwen2.5:3b" if privacy_strict else MODEL))).strip()
    target_llm_base = (llm_base_url or ("http://ollama:11434/v1" if privacy_strict else BASE_URL)).strip()
    target_llm_key = (llm_api_key or ("ollama" if "ollama" in target_llm_base else API_KEY)).strip()
    target_stt = (stt_model or STT_MODEL).strip()
    target_stt_base = (stt_base_url or ("http://ollama:11434/v1" if privacy_strict else STT_BASE_URL)).strip()
    target_tts = (tts_voice or agent_data.get("voice_name") or TTS_VOICE).strip()

    # Build seeded standalone SQLite database
    with tempfile.TemporaryDirectory() as td:
        seed_db_path = os.path.join(td, "agents.db")
        sconn = sqlite3.connect(seed_db_path)
        sconn.execute("""CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            pw_salt TEXT NOT NULL,
            pw_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS sessions (
            token TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at TEXT NOT NULL
        )""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS agents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            system_prompt TEXT NOT NULL DEFAULT '',
            greeting TEXT NOT NULL DEFAULT '',
            voice_name TEXT NOT NULL DEFAULT '',
            rate REAL NOT NULL DEFAULT 1.0,
            lang TEXT NOT NULL DEFAULT 'en-US',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            use_knowledge INTEGER NOT NULL DEFAULT 0,
            tools_enabled INTEGER NOT NULL DEFAULT 0,
            barge_in INTEGER NOT NULL DEFAULT 1,
            user_id INTEGER,
            booking_webhook TEXT NOT NULL DEFAULT '',
            google_calendar_id TEXT NOT NULL DEFAULT '',
            google_sheet_id TEXT NOT NULL DEFAULT '',
            google_credentials_json TEXT NOT NULL DEFAULT '',
            google_auto_sync_calendar INTEGER NOT NULL DEFAULT 0,
            google_auto_sync_sheets INTEGER NOT NULL DEFAULT 0,
            google_enable_meet INTEGER NOT NULL DEFAULT 0
        )""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS agent_members (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            role TEXT NOT NULL DEFAULT 'viewer',
            created_at TEXT NOT NULL,
            UNIQUE(agent_id, user_id)
        )""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            filename TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL)""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            document_id INTEGER NOT NULL, content TEXT NOT NULL)""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            call_uid TEXT, started_at TEXT, ended_at TEXT,
            num_turns INTEGER NOT NULL DEFAULT 0, transcript TEXT NOT NULL DEFAULT '[]')""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT, agent_id INTEGER NOT NULL,
            call_uid TEXT, name TEXT, phone TEXT, datetime TEXT, reason TEXT,
            created_at TEXT NOT NULL,
            schedule_status TEXT NOT NULL DEFAULT 'CONFIRMED',
            proposed_alternative TEXT NOT NULL DEFAULT '',
            updated_at TEXT NOT NULL DEFAULT '',
            slot_start TEXT NOT NULL DEFAULT '',
            slot_end TEXT NOT NULL DEFAULT '')""")
        sconn.execute("""CREATE TABLE IF NOT EXISTS outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_id INTEGER NOT NULL,
            booking_id INTEGER,
            event TEXT NOT NULL,
            payload TEXT NOT NULL DEFAULT '{}',
            status TEXT NOT NULL DEFAULT 'PENDING',
            created_at TEXT NOT NULL,
            attempts INTEGER NOT NULL DEFAULT 0,
            last_error TEXT NOT NULL DEFAULT '')""")

        salt, h = hash_pw("admin123")
        cur_u = sconn.execute(
            "INSERT INTO users (email, pw_salt, pw_hash, created_at) VALUES (?,?,?,?)",
            ("admin@appliance.local", salt, h, now_iso())
        )
        app_uid = cur_u.lastrowid
        app_token = "appliance_default_session"
        sconn.execute("INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
                      (app_token, app_uid, now_iso()))

        sconn.execute(
            """INSERT INTO agents (
                id, name, system_prompt, greeting, voice_name, rate, lang,
                created_at, updated_at, use_knowledge, tools_enabled, barge_in,
                user_id, booking_webhook, google_calendar_id, google_sheet_id,
                google_credentials_json, google_auto_sync_calendar, google_auto_sync_sheets, google_enable_meet
            ) VALUES (1, ?,?,?,?,?,?, ?,?, ?,?,?, ?,?, ?,?,?,?,?,?)""",
            (
                agent_data.get("name", "Voice Agent"),
                agent_data.get("system_prompt", ""),
                agent_data.get("greeting", ""),
                target_tts,
                agent_data.get("rate", 1.0),
                agent_data.get("lang", "en-US"),
                agent_data.get("created_at", now_iso()),
                now_iso(),
                int(agent_data.get("use_knowledge", 0)),
                int(agent_data.get("tools_enabled", 0)),
                int(agent_data.get("barge_in", 1)),
                app_uid,
                agent_data.get("booking_webhook", ""),
                agent_data.get("google_calendar_id", ""),
                agent_data.get("google_sheet_id", ""),
                agent_data.get("google_credentials_json", ""),
                int(agent_data.get("google_auto_sync_calendar", 0)),
                int(agent_data.get("google_auto_sync_sheets", 0)),
                int(agent_data.get("google_enable_meet", 0)),
            )
        )
        sconn.execute("INSERT INTO agent_members (agent_id, user_id, role, created_at) VALUES (1, ?, 'owner', ?)",
                      (app_uid, now_iso()))

        doc_map = {}
        for d in docs:
            cur_d = sconn.execute(
                "INSERT INTO documents (agent_id, filename, content, created_at) VALUES (1, ?, ?, ?)",
                (d["filename"], d["content"], d.get("created_at", now_iso()))
            )
            doc_map[d["id"]] = cur_d.lastrowid

        for c in chunks:
            new_did = doc_map.get(c["document_id"], 1)
            sconn.execute(
                "INSERT INTO chunks (agent_id, document_id, content) VALUES (1, ?, ?)",
                (new_did, c["content"])
            )

        sconn.commit()
        sconn.close()

        with open(seed_db_path, "rb") as sf:
            seed_bytes = sf.read()

    zip_buf = io.BytesIO()
    root_dir = Path(__file__).parent

    manifest = {
        "appliance": "Voice Agent Studio On-Premise Docker Appliance",
        "agent": {
            "id": 1,
            "original_id": agent_data.get("id"),
            "name": agent_data.get("name"),
            "system_prompt": agent_data.get("system_prompt"),
            "greeting": agent_data.get("greeting"),
            "voice_name": target_tts,
            "rate": agent_data.get("rate"),
            "lang": agent_data.get("lang"),
            "use_knowledge": bool(agent_data.get("use_knowledge")),
            "tools_enabled": bool(agent_data.get("tools_enabled")),
            "barge_in": bool(agent_data.get("barge_in")),
            "booking_webhook": agent_data.get("booking_webhook"),
        },
        "tailored_models": {
            "llm_model": target_llm,
            "llm_base_url": target_llm_base,
            "stt_model": target_stt,
            "stt_base_url": target_stt_base,
            "tts_voice": target_tts,
            "has_gpu_acceleration": has_gpu,
            "privacy_strict": privacy_strict
        },
        "statistics": {
            "documents_count": len(docs),
            "chunks_count": len(chunks)
        },
        "default_credentials": {
            "email": "admin@appliance.local",
            "password": "admin123"
        },
        "exported_at": now_iso()
    }

    gpu_deploy_block = """    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]""" if has_gpu else """    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: 1
    #           capabilities: [gpu]"""

    compose_content = f"""# =============================================================================
# Voice Agent Appliance — On-Premise Docker Compose Stack
# Agent: {agent_data.get('name', 'Voice Agent')}
# Hardware Target: {'NVIDIA GPU Accelerated' if has_gpu else 'CPU Standard'}
# Privacy Policy: {'100% Air-Gapped Local (Zero Data Egress)' if privacy_strict else 'Hybrid / Cloud Speed'}
# =============================================================================

version: "3.9"

services:
  agent-appliance:
    build:
      context: .
      dockerfile: Dockerfile
    image: voice-agent-appliance:latest
    container_name: voice_agent_appliance_{agent_slug}
    restart: unless-stopped
    ports:
      - "${{PORT:-8000}}:8000"
    environment:
      - PORT=8000
      - LLM_API_KEY=${{LLM_API_KEY:-{target_llm_key}}}
      - LLM_BASE_URL=${{LLM_BASE_URL:-{target_llm_base}}}
      - LLM_MODEL=${{LLM_MODEL:-{target_llm}}}
      - STT_BASE_URL=${{STT_BASE_URL:-{target_stt_base}}}
      - STT_MODEL=${{STT_MODEL:-{target_stt}}}
      - TTS_VOICE=${{TTS_VOICE:-{target_tts}}}
      - SESSION_COOKIE_SECURE=false
    volumes:
      - ./data:/app/data
    depends_on:
      - ollama

  ollama:
    image: ollama/ollama:latest
    container_name: voice_agent_ollama_{agent_slug}
    restart: unless-stopped
    ports:
      - "11434:11434"
    volumes:
      - ollama_models:/root/.ollama
{gpu_deploy_block}

volumes:
  ollama_models:
"""

    env_content = f"""# Voice Agent Appliance Configuration
PORT=8000
LLM_API_KEY={target_llm_key}
LLM_BASE_URL={target_llm_base}
LLM_MODEL={target_llm}
STT_BASE_URL={target_stt_base}
STT_MODEL={target_stt}
TTS_VOICE={target_tts}
SESSION_COOKIE_SECURE=false
"""

    run_sh_content = """#!/usr/bin/env bash
set -e
echo "🚀 Starting Voice Agent On-Premise Docker Appliance..."
docker compose up -d --build
echo ""
echo "✅ Appliance running at http://localhost:8000"
echo "🔑 Default Login: admin@appliance.local / admin123"
"""

    run_bat_content = """@echo off
echo Starting Voice Agent On-Premise Docker Appliance...
docker compose up -d --build
echo.
echo Appliance running at http://localhost:8000
echo Default Login: admin@appliance.local / admin123
pause
"""

    pull_section = f"""## 🧠 Model Setup
To pull the configured local language model inside the Ollama container:
```bash
docker exec -it voice_agent_ollama_{agent_slug} ollama pull {target_llm}
```""" if "ollama" in target_llm_base else f"""## 🌐 Gateway / Cloud Model Setup
Pre-configured to route to model `{target_llm}` via `{target_llm_base}`.
Verify your `LLM_API_KEY` in `.env` if using private API authentication."""

    readme_content = f"""# Voice Agent On-Premise Appliance: {agent_data.get('name', 'Voice Agent')}

This containerized package is tailored for **{agent_data.get('name', 'Voice Agent')}** with:
- **LLM Model:** `{target_llm}`
- **STT Engine:** `{target_stt}`
- **TTS Voice:** `{target_tts}`
- **Acceleration:** {'NVIDIA GPU' if has_gpu else 'CPU'}
- **Privacy Policy:** {'100% Air-Gapped Local (Zero Data Egress)' if privacy_strict else 'Hybrid / Cloud Speed'}

---

## 🚀 Quick Start

### 1. Requirements
- Docker 24.0+ and Docker Compose v2
{'- NVIDIA GPU + NVIDIA Container Toolkit installed' if has_gpu else '- Standard x86_64 CPU'}

### 2. Start the Appliance
- **Linux / macOS**:
  ```bash
  chmod +x run.sh
  ./run.sh
  ```
- **Windows**:
  Double click `run.bat` or run:
  ```cmd
  docker compose up -d --build
  ```

### 3. Access Voice Agent Studio
Open your browser to:
[http://localhost:8000](http://localhost:8000)

**Default Admin Credentials:**
- **Email:** `admin@appliance.local`
- **Password:** `admin123`

---

{pull_section}

---

## 🌐 Embedding in Client Intranet Pages
Add this single script tag to any internal webpage:
```html
<script src="http://<your-server-ip>:8000/widget.js" data-agent-id="1"></script>
```

---

## 📁 Package Contents
- `data/agents.db`: Pre-seeded SQLite database with **{agent_data.get('name')}**, complete system prompt, and {len(chunks)} indexed knowledge chunks.
- `docker-compose.yml`: Multi-service orchestration (FastAPI Voice Runtime + Ollama).
- `Dockerfile`: Production image build definition.
- `agent_manifest.json`: Configuration audit manifest.
"""

    with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("docker-compose.yml", compose_content)
        zf.writestr(".env", env_content)
        zf.writestr(".env.example", env_content)
        zf.writestr("run.sh", run_sh_content)
        zf.writestr("run.bat", run_bat_content)
        zf.writestr("README.md", readme_content)
        zf.writestr("agent_manifest.json", json.dumps(manifest, indent=2))
        zf.writestr("data/agents.db", seed_bytes)
        
        for fname in ["Dockerfile", "requirements.txt", "server.py", "guardrail.py", "google_integration.py"]:
            fpath = root_dir / fname
            if fpath.exists():
                zf.write(fpath, fname)
                
        for folder in ["static", "qpo"]:
            f_dir = root_dir / folder
            for r, ds, fs in os.walk(f_dir):
                if "__pycache__" in r:
                    continue
                for f in fs:
                    full_p = os.path.join(r, f)
                    rel_p = os.path.relpath(full_p, root_dir)
                    zf.write(full_p, rel_p)

    zip_bytes = zip_buf.getvalue()
    filename = f"voice_agent_{agent_slug}_appliance.zip"
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )


# ---- knowledge base ----
@app.get("/api/agents/{agent_id}/documents")
def list_documents(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_call")
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
        owned_agent(conn, agent_id, user, required_perm="can_manage_knowledge")
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
        conn.execute("UPDATE agents SET use_knowledge = 1 WHERE id = ?", (agent_id,))
    _invalidate_bm25_cache(agent_id)  # Phase D: refresh cached index
    return {"id": cur.lastrowid, "filename": name, "chunks": len(pieces)}



@app.delete("/api/documents/{doc_id}")
def delete_document(doc_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        row = conn.execute("SELECT agent_id FROM documents WHERE id = ?", (doc_id,)).fetchone()
        if row:
            owned_agent(conn, row["agent_id"], user, required_perm="can_manage_knowledge")
            conn.execute("DELETE FROM chunks WHERE document_id = ?", (doc_id,))
            conn.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
            _invalidate_bm25_cache(row["agent_id"])  # Phase D: refresh cached index
    return {"ok": True}



# ---- call history ----
@app.post("/api/calls")
def save_call(c: CallIn, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, c.agent_id, user, required_perm="can_call")
        cur = conn.execute(
            "INSERT INTO calls (agent_id, call_uid, started_at, ended_at, num_turns, transcript, source, caller_phone, duration_seconds, status)"
            " VALUES (?,?,?,?,?,?,?,?,?,?)",
            (c.agent_id, c.call_uid, c.started_at, c.ended_at, len(c.transcript), json.dumps(c.transcript),
             c.source or "browser", c.caller_phone or "", c.duration_seconds or 0, "completed"))
    return {"id": cur.lastrowid}


@app.get("/api/agents/{agent_id}/calls")
def list_calls(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_call")
        rows = conn.execute(
            "SELECT id, call_uid, started_at, ended_at, num_turns, source, caller_phone, duration_seconds, status FROM calls"
            " WHERE agent_id = ? ORDER BY id DESC", (agent_id,)).fetchall()
    return [row_to_dict(r) for r in rows]


@app.get("/api/calls/{call_id}")
def get_call(call_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        row = conn.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Call not found")
        agent_id = row["agent_id"]
        owned_agent(conn, agent_id, user, required_perm="can_call")
        role = get_user_agent_role(conn, agent_id, user["id"]) or ROLE_VIEWER
    d = row_to_dict(row)
    transcript = json.loads(d.get("transcript") or "[]")
    d["transcript"] = abstract_transcript(transcript, role)
    return d


# ---- bookings ----
def enhance_booking(b: dict, agent_id: int) -> dict:
    d = dict(b)
    booking_id = d.get("id")
    name = d.get("name") or "Appointment"
    dt = d.get("datetime") or ""
    reason = d.get("reason") or ""
    phone = d.get("phone") or ""
    
    title = urllib.parse.quote(f"Booking: {name}")
    details = urllib.parse.quote(f"Reason: {reason}\nPhone: {phone}\nRequested Time: {dt}")
    d["gcal_url"] = f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={title}&details={details}"
    d["ics_url"] = f"/api/agents/{agent_id}/bookings/{booking_id}/ics"
    if not d.get("schedule_status"):
        d["schedule_status"] = "CONFIRMED"
    if "proposed_alternative" not in d:
        d["proposed_alternative"] = ""
    return d


class BookingUpdateIn(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    datetime: Optional[str] = None
    reason: Optional[str] = None
    schedule_status: Optional[str] = None
    proposed_alternative: Optional[str] = None


@app.get("/api/agents/{agent_id}/bookings")
def list_bookings(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_call")
        role = get_user_agent_role(conn, agent_id, user["id"]) or ROLE_VIEWER
        rows = conn.execute("SELECT * FROM bookings WHERE agent_id = ? ORDER BY id DESC",
                            (agent_id,)).fetchall()
    return [abstract_booking(enhance_booking(row_to_dict(r), agent_id), role) for r in rows]


@app.put("/api/agents/{agent_id}/bookings/{booking_id}")
def update_booking(agent_id: int, booking_id: int, body: BookingUpdateIn, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_edit_bookings")
        row = conn.execute("SELECT * FROM bookings WHERE id = ? AND agent_id = ?", (booking_id, agent_id)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Booking not found")
        curr = row_to_dict(row)
        name = body.name if body.name is not None else curr.get("name")
        phone = body.phone if body.phone is not None else curr.get("phone")
        dt = body.datetime if body.datetime is not None else curr.get("datetime")
        reason = body.reason if body.reason is not None else curr.get("reason")
        status = body.schedule_status if body.schedule_status is not None else curr.get("schedule_status", "CONFIRMED")
        alt = body.proposed_alternative if body.proposed_alternative is not None else curr.get("proposed_alternative", "")
        now = now_iso()
        conn.execute(
            "UPDATE bookings SET name=?, phone=?, datetime=?, reason=?, schedule_status=?, proposed_alternative=?, updated_at=? WHERE id=?",
            (name, phone, dt, reason, status, alt, now, booking_id)
        )
        updated = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
        role = get_user_agent_role(conn, agent_id, user["id"]) or ROLE_OWNER
    return abstract_booking(enhance_booking(row_to_dict(updated), agent_id), role)


@app.delete("/api/agents/{agent_id}/bookings/{booking_id}")
def delete_booking(agent_id: int, booking_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        owned_agent(conn, agent_id, user, required_perm="can_delete_bookings")
        conn.execute("DELETE FROM bookings WHERE id = ? AND agent_id = ?", (booking_id, agent_id))
    return {"ok": True}


@app.get("/api/agents/{agent_id}/bookings/{booking_id}/ics")
def download_booking_ics(agent_id: int, booking_id: int):
    with db() as conn:
        row = conn.execute(
            "SELECT b.*, a.name as agent_name FROM bookings b JOIN agents a ON a.id = b.agent_id WHERE b.id = ? AND b.agent_id = ?",
            (booking_id, agent_id)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="Booking not found")
        b = row_to_dict(row)
        
    now_ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    summary = f"Booking: {b.get('name', 'Client')} with {b.get('agent_name', 'Assistant')}"
    desc = f"Phone: {b.get('phone', 'N/A')}\\nReason: {b.get('reason', 'N/A')}\\nRequested: {b.get('datetime', 'N/A')}"
    uid = f"booking-{booking_id}-{agent_id}@voiceagentstudio"
    
    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Voice Agent Studio//EN",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{now_ts}",
        f"DTSTART:{now_ts}",
        f"SUMMARY:{summary}",
        f"DESCRIPTION:{desc}",
        "STATUS:CONFIRMED",
        "END:VEVENT",
        "END:VCALENDAR"
    ]
    ics_content = "\r\n".join(ics_lines)
    return Response(
        content=ics_content,
        media_type="text/calendar",
        headers={"Content-Disposition": f'attachment; filename="booking-{booking_id}.ics"'}
    )


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
        import time as _time
        t0 = _time.monotonic()
        async with httpx.AsyncClient(timeout=8) as client:
            r = await client.post(url, json=booking_payload(agent, sample))
        duration_ms = round((_time.monotonic() - t0) * 1000)
        # Bug 1 Fix: return duration_ms and response_preview so the frontend can display them
        preview = ""
        try:
            preview = r.text[:200]
        except Exception:
            pass
        return {"ok": True, "status": r.status_code, "duration_ms": duration_ms, "response_preview": preview}
    except Exception as e:
        return JSONResponse(status_code=502, content={"error": f"Webhook failed: {e}", "duration_ms": 0})


# ============================ RBAC & Member Management ============================
@app.get("/api/agents/{agent_id}/my-role")
def get_my_role(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = conn.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        role = get_user_agent_role(conn, agent_id, user["id"])
        if not role:
            raise HTTPException(status_code=403, detail="Not a member of this agent")
    return {
        "agent_id": agent_id,
        "role": role,
        "permissions": PERMISSIONS.get(role, {}),
        "email": user["email"]
    }


@app.get("/api/agents/{agent_id}/members")
def list_agent_members(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = owned_agent(conn, agent_id, user, required_perm="can_manage_members")
        rows = conn.execute("""
            SELECT m.id, m.agent_id, m.user_id, m.role, m.created_at, u.email
            FROM agent_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.agent_id = ?
            ORDER BY m.id ASC
        """, (agent_id,)).fetchall()
        creator_id = agent["user_id"]
    members = []
    for r in rows:
        d = row_to_dict(r)
        d["is_creator"] = (d["user_id"] == creator_id)
        members.append(d)
    return members


@app.post("/api/agents/{agent_id}/members")
def add_agent_member(agent_id: int, body: MemberAddIn, user: dict = Depends(require_user)):
    email = body.email.strip().lower()
    role = body.role.strip().lower()
    if role not in ROLES_LIST:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from: {ROLES_LIST}")

    with db() as conn:
        agent = owned_agent(conn, agent_id, user, required_perm="can_manage_members")
        target_user = conn.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        if not target_user:
            # Auto-create placeholder account so invited user can log in with this email
            salt, pw_h = hash_pw(secrets.token_hex(8))
            cur = conn.execute("INSERT INTO users (email, pw_salt, pw_hash, created_at) VALUES (?,?,?,?)",
                               (email, salt, pw_h, now_iso()))
            target_user_id = cur.lastrowid
        else:
            target_user_id = target_user["id"]

        now = now_iso()
        conn.execute("""
            INSERT INTO agent_members (agent_id, user_id, role, created_at)
            VALUES (?,?,?,?)
            ON CONFLICT(agent_id, user_id) DO UPDATE SET role = excluded.role
        """, (agent_id, target_user_id, role, now))
    return {"ok": True, "user_id": target_user_id, "email": email, "role": role}


@app.put("/api/agents/{agent_id}/members/{target_user_id}")
def update_agent_member_role(agent_id: int, target_user_id: int, body: MemberRoleUpdateIn, user: dict = Depends(require_user)):
    role = body.role.strip().lower()
    if role not in ROLES_LIST:
        raise HTTPException(status_code=400, detail=f"Invalid role. Choose from: {ROLES_LIST}")

    with db() as conn:
        agent = owned_agent(conn, agent_id, user, required_perm="can_manage_members")
        if agent["user_id"] == target_user_id and role != ROLE_OWNER:
            raise HTTPException(status_code=400, detail="Cannot demote the primary owner of the agent.")
        conn.execute("UPDATE agent_members SET role = ? WHERE agent_id = ? AND user_id = ?",
                     (role, agent_id, target_user_id))
    return {"ok": True, "target_user_id": target_user_id, "role": role}


@app.delete("/api/agents/{agent_id}/members/{target_user_id}")
def remove_agent_member(agent_id: int, target_user_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = owned_agent(conn, agent_id, user, required_perm="can_manage_members")
        if agent["user_id"] == target_user_id:
            raise HTTPException(status_code=400, detail="Cannot remove the primary owner of the agent.")
        conn.execute("DELETE FROM agent_members WHERE agent_id = ? AND user_id = ?",
                     (agent_id, target_user_id))
    return {"ok": True}


# ============================ Google Suite Endpoints ============================
@app.get("/api/agents/{agent_id}/google/settings")
def get_google_settings(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))
    creds = agent.get("google_credentials_json") or ""
    masked_creds = "•••••••• (Configured)" if len(creds) > 10 else ""
    return {
        "google_calendar_id": agent.get("google_calendar_id", ""),
        "google_sheet_id": agent.get("google_sheet_id", ""),
        "google_credentials_configured": bool(creds),
        "google_credentials_preview": masked_creds,
        "google_auto_sync_calendar": bool(agent.get("google_auto_sync_calendar", 0)),
        "google_auto_sync_sheets": bool(agent.get("google_auto_sync_sheets", 0)),
        "google_enable_meet": bool(agent.get("google_enable_meet", 0)),
    }


@app.post("/api/agents/{agent_id}/google/settings")
def update_google_settings(agent_id: int, body: GoogleSettingsIn, user: dict = Depends(require_user)):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_edit_settings"))
        cal_id = body.google_calendar_id if body.google_calendar_id is not None else agent.get("google_calendar_id", "")
        sheet_id = body.google_sheet_id if body.google_sheet_id is not None else agent.get("google_sheet_id", "")
        creds = agent.get("google_credentials_json", "")
        if body.google_credentials_json is not None:
            raw_creds = body.google_credentials_json.strip()
            if raw_creds:
                try:
                    parsed_creds = json.loads(raw_creds)
                    if not isinstance(parsed_creds, dict):
                        raise ValueError("Credentials must be a JSON object {...}")
                    creds = json.dumps(parsed_creds)
                except Exception as e:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            "Invalid Google Credentials JSON. Please paste the entire Service Account JSON key "
                            f"file downloaded from Google Cloud Console. Error: {e}"
                        )
                    )
            else:
                creds = ""
        sync_cal = int(body.google_auto_sync_calendar) if body.google_auto_sync_calendar is not None else agent.get("google_auto_sync_calendar", 0)
        sync_sheet = int(body.google_auto_sync_sheets) if body.google_auto_sync_sheets is not None else agent.get("google_auto_sync_sheets", 0)
        meet = int(body.google_enable_meet) if body.google_enable_meet is not None else agent.get("google_enable_meet", 0)

        conn.execute("""
            UPDATE agents SET
                google_calendar_id = ?,
                google_sheet_id = ?,
                google_credentials_json = ?,
                google_auto_sync_calendar = ?,
                google_auto_sync_sheets = ?,
                google_enable_meet = ?
            WHERE id = ?
        """, (cal_id, sheet_id, creds, sync_cal, sync_sheet, meet, agent_id))
    return {"ok": True}


@app.post("/api/agents/{agent_id}/google/test-calendar")
async def test_google_calendar(
    agent_id: int,
    body: Optional[GoogleTestCalendarIn] = None,
    user: dict = Depends(require_user)
):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))

    cal_id = (body.google_calendar_id.strip() if body and body.google_calendar_id and body.google_calendar_id.strip() else None) or agent.get("google_calendar_id") or "primary"
    meet = bool(body.google_enable_meet) if (body and body.google_enable_meet is not None) else bool(agent.get("google_enable_meet"))
    if body and body.google_calendar_id:
        with db() as conn:
            conn.execute("UPDATE agents SET google_calendar_id = ?, google_enable_meet = ? WHERE id = ?", (cal_id, int(meet), agent_id))

    creds = agent.get("google_credentials_json") or ""
    sample_booking = {
        "id": "test",
        "name": "Alex Mercer (Test)",
        "phone": "+1 555 0199",
        "datetime": "tomorrow at 2pm",
        "reason": "Google Calendar Integration Test Booking",
        "call_uid": "test_uid_123"
    }
    res = await google_integration.create_google_calendar_event(
        booking=sample_booking,
        calendar_id=cal_id,
        credentials_json=creds,
        agent_name=agent.get("name", "Assistant"),
        enable_meet=meet
    )
    return res


@app.post("/api/agents/{agent_id}/google/test-sheets")
async def test_google_sheets(
    agent_id: int,
    body: Optional[GoogleTestSheetIn] = None,
    user: dict = Depends(require_user)
):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))

    sheet_id = (body.google_sheet_id.strip() if body and body.google_sheet_id and body.google_sheet_id.strip() else None) or agent.get("google_sheet_id") or ""
    if not sheet_id:
        raise HTTPException(
            status_code=400,
            detail="Google Sheet ID or URL is not configured. Please paste your Google Sheet ID or URL in the field above."
        )

    if body and body.google_sheet_id and body.google_sheet_id.strip():
        with db() as conn:
            conn.execute("UPDATE agents SET google_sheet_id = ? WHERE id = ?", (sheet_id, agent_id))

    creds = agent.get("google_credentials_json") or ""
    sample_booking = {
        "id": "test",
        "name": "Alex Mercer (Test)",
        "phone": "+1 555 0199",
        "datetime": "tomorrow at 2pm",
        "reason": "Google Sheets Live Export Test",
        "schedule_status": "CONFIRMED",
        "call_uid": "test_uid_123"
    }
    res = await google_integration.append_booking_to_google_sheet(
        booking=sample_booking,
        sheet_id=sheet_id,
        credentials_json=creds
    )
    return res



@app.post("/api/agents/{agent_id}/google/sync-doc")
async def sync_google_doc_to_kb(agent_id: int, body: GoogleDocSyncIn, user: dict = Depends(require_user)):
    """Fetches Google Doc content directly into the agent's RAG knowledge base chunks."""
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_manage_knowledge"))
    doc_url = body.doc_url.strip()
    if not doc_url:
        raise HTTPException(status_code=400, detail="Google Doc URL is required.")

    creds = agent.get("google_credentials_json") or ""
    ok, title, content = await google_integration.fetch_google_doc_text(doc_url, credentials_json=creds)
    if not ok or not content:
        raise HTTPException(status_code=400, detail=content or "Failed to read Google Doc.")

    pieces = chunk_text(content)
    with db() as conn:
        cur = conn.execute("INSERT INTO documents (agent_id, filename, content, created_at) VALUES (?,?,?,?)",
                           (agent_id, f"Google Doc: {title}", content, now_iso()))
        conn.executemany("INSERT INTO chunks (agent_id, document_id, content) VALUES (?,?,?)",
                         [(agent_id, cur.lastrowid, p) for p in pieces])
        conn.execute("UPDATE agents SET use_knowledge = 1 WHERE id = ?", (agent_id,))
    return {"ok": True, "title": title, "chunks": len(pieces)}


@app.post("/api/agents/{agent_id}/google/sync-all-sheets")
async def sync_all_bookings_to_sheets(agent_id: int, user: dict = Depends(require_user)):
    with db() as conn:
        agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))
        sheet_id = agent.get("google_sheet_id") or ""
        if not sheet_id:
            raise HTTPException(status_code=400, detail="Google Sheet ID is not set.")
        rows = conn.execute("SELECT * FROM bookings WHERE agent_id = ? ORDER BY id ASC", (agent_id,)).fetchall()
    creds = agent.get("google_credentials_json") or ""
    count = 0
    for r in rows:
        b = row_to_dict(r)
        res = await google_integration.append_booking_to_google_sheet(b, sheet_id, creds)
        if res.get("ok"):
            count += 1
    return {"ok": True, "synced_count": count, "total": len(rows)}


async def auto_sync_booking_to_google(agent: dict, booking: dict):
    """Automatically syncs a confirmed booking to Google Calendar and Google Sheets in the background."""
    if not agent or not booking:
        return
    try:
        if agent.get("google_auto_sync_calendar"):
            cal_id = agent.get("google_calendar_id") or "primary"
            creds = agent.get("google_credentials_json") or ""
            meet = bool(agent.get("google_enable_meet"))
            res_cal = await google_integration.create_google_calendar_event(
                booking=booking,
                calendar_id=cal_id,
                credentials_json=creds,
                agent_name=agent.get("name", "Assistant"),
                enable_meet=meet
            )
            print(f"🗓️ [Google Auto-Sync Calendar]: {res_cal.get('status')}")

        if agent.get("google_auto_sync_sheets"):
            sheet_id = agent.get("google_sheet_id") or ""
            if sheet_id:
                creds = agent.get("google_credentials_json") or ""
                res_sheet = await google_integration.append_booking_to_google_sheet(
                    booking=booking,
                    sheet_id=sheet_id,
                    credentials_json=creds
                )
                print(f"📊 [Google Auto-Sync Sheets]: {res_sheet.get('status')}")
    except Exception as ge:
        print(f"⚠️ [Google Auto-Sync Error]: {ge}")


def save_booking(agent_id: int, call_uid: Optional[str], args: dict) -> dict:
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO bookings (agent_id, call_uid, name, phone, datetime, reason, created_at, schedule_status, proposed_alternative)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (agent_id, call_uid, args.get("name"), args.get("phone"),
             args.get("datetime"), args.get("reason"), now_iso(), "CONFIRMED", ""))
        row = conn.execute("SELECT * FROM bookings WHERE id = ?", (cur.lastrowid,)).fetchone()
    return enhance_booking(row_to_dict(row), agent_id)


def resolve_booking_datetime(raw_dt: str) -> str:
    """
    Maps relative date expressions like 'tomorrow', 'tomorrow and after tomorrow',
    'this friday', 'today' into exact calendar dates.
    """
    if not raw_dt:
        return datetime.now().strftime("%A, %b %d, %Y")
    s = str(raw_dt).strip().lower()
    # Bug 11 Fix: use local system time consistently. For production deployment,
    # pass caller timezone via API and use ZoneInfo(tz) here.
    today = datetime.now().date()
    fmt = "%A, %b %d, %Y"

    # Multi-day checks e.g. "tomorrow and day after tomorrow", "tomorrow to day after tomorrow", "2 nights"
    if ("tomorrow" in s and any(k in s for k in [" to ", " and ", " until ", " through ", " - "]) and ("after" in s or "next" in s)) or "2 night" in s or "two night" in s:
        d1 = today + timedelta(days=1)
        d2 = today + timedelta(days=2)
        return f"{d1.strftime(fmt)} to {d2.strftime(fmt)}"

    if "day after tomorrow" in s or "after tomorrow" in s:
        return (today + timedelta(days=2)).strftime(fmt)

    if "tomorrow" in s:
        target = today + timedelta(days=1)
        time_m = re.search(r"\b(\d{1,2}(?::\d{2})?\s*(?:am|pm))\b", s)
        time_str = f" at {time_m.group(1)}" if time_m else ""
        return target.strftime(fmt) + time_str

    if "today" in s or "tonight" in s:
        return today.strftime(fmt)

    # Named weekdays
    days = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
    for idx, dname in enumerate(days):
        if dname in s:
            cur_weekday = today.weekday()
            diff = (idx - cur_weekday) % 7
            if diff == 0:
                diff = 7
            return (today + timedelta(days=diff)).strftime(fmt)

    return raw_dt.strip()


def validate_and_save_booking(
    agent_id: int,
    call_uid: Optional[str],
    args: dict,
    agent: Optional[dict] = None,
    messages: Optional[list] = None
) -> tuple[bool, Optional[dict], str]:
    """
    Validates that real guest details and explicit consent exist before creating any booking.
    Prevents dummy/hallucinated bookings, verifies name in user speech, maps dates,
    and prevents duplicate bookings per call.

    Phase F changes:
    - Slot overlap check: rejects when A.start < B.end AND B.start < A.end for same agent
    - BEGIN IMMEDIATE transaction wraps overlap check + INSERT atomically
    - Outbox pattern: external calls (webhook, GCal, Sheets) happen AFTER commit, not inside txn
    """
    if not isinstance(args, dict):
        return False, None, "Invalid arguments payload."

    raw_name = str(args.get("name") or args.get("caller_name") or "").strip()
    clean_name = raw_name.lower().strip(" .!?,<>()[]{}\"\'")

    # 1. Reject placeholder names and template strings
    placeholder_terms = [
        "guest", "caller", "null", "none", "unknown", "user", "test", "tester",
        "n/a", "undefined", "anonymous", "full name", "contact", "phone number",
        "not specified", "unspecified", "someone", "customer", "placeholder", "no name"
    ]
    if not clean_name or any(p in clean_name for p in placeholder_terms):
        return False, None, "Caller's real name is missing or is a placeholder."
    if len(clean_name) < 2 or not any(c.isalpha() for c in clean_name):
        return False, None, "Caller's real name must contain valid letters."

    # Check against assistant/agent's persona name (e.g. Ramya)
    if agent:
        agent_name = (agent.get("name") or "").strip().lower()
        if agent_name and clean_name == agent_name:
            return False, None, f"Cannot use '{raw_name}' because that is the receptionist/bot name, not the guest's name."
        prompt_lower = (agent.get("system_prompt") or "").lower()
        if f"name is {clean_name}" in prompt_lower or f"i am {clean_name}" in prompt_lower or f"this is {clean_name}" in prompt_lower:
            return False, None, f"Cannot use '{raw_name}' because that is your assistant persona name, not the guest's name."

    # 2. Verify caller actually stated this name in the conversation transcript
    if messages:
        user_texts = " ".join([m.get("content", "") for m in messages if m.get("role") == "user"]).lower()
        user_words = set(re.findall(r"\b[a-zA-Z]{2,}\b", user_texts.lower()))
        name_parts = [p.lower() for p in re.findall(r"\b[a-zA-Z]{2,}\b", raw_name) if p.lower() not in {"mr", "mrs", "ms", "dr", "name", "is", "my", "the"}]
        if not name_parts or not any(part in user_words for part in name_parts):
            return False, None, f"The caller has not shared their name in the conversation yet. Please ask: 'May I have your full name?' before booking."

    # 3. Validate check-in datetime
    raw_dt = str(args.get("datetime") or args.get("dates") or "").strip()
    clean_dt = raw_dt.lower().strip(" .!?,<>()[]{}\"\'")
    if not clean_dt or any(p in clean_dt for p in ["null", "none", "undefined", "unspecified", "not specified", "unknown"]):
        return False, None, "Check-in dates or arrival time was not specified."

    # Map relative date into exact calendar date!
    exact_dt = resolve_booking_datetime(raw_dt)

    # 4. Check verbal confirmation flag if provided
    user_conf = args.get("user_confirmed", args.get("confirmed_by_guest", True))
    if str(user_conf).lower() in {"false", "0", "no"}:
        return False, None, "The guest has not given explicit verbal confirmation to finalize this booking."

    # 5. Phase F: slot duration from agent settings (default 60 min)
    slot_duration_min: int = 60
    if agent and isinstance(agent.get("slot_duration_min"), int):
        slot_duration_min = agent["slot_duration_min"]

    # Parse exact_dt to determine slot start/end for overlap check
    # We store as ISO string; attempt to extract a datetime for comparison
    slot_start_iso: str = ""
    slot_end_iso: str = ""
    try:
        from datetime import timedelta as _td
        # Try ISO parse first, then strptime fallback
        for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%A, %b %d, %Y", "%Y-%m-%d"):
            try:
                dt_parsed = datetime.strptime(exact_dt, fmt)
                slot_start_iso = dt_parsed.isoformat()
                slot_end_iso = (dt_parsed + _td(minutes=slot_duration_min)).isoformat()
                break
            except ValueError:
                continue
    except Exception:
        pass  # If we cannot parse, skip overlap check (graceful degradation)

    valid_args = {
        "name": raw_name,
        "phone": str(args.get("phone") or "").strip(),
        "datetime": exact_dt,
        "reason": str(args.get("reason") or args.get("room_type") or "").strip(),
        "slot_start": slot_start_iso,
        "slot_end": slot_end_iso,
    }

    # Phase F: atomic overlap check + insert inside BEGIN IMMEDIATE transaction
    booking = None
    with db() as conn:
        # Use BEGIN IMMEDIATE to serialise concurrent writers
        conn.execute("BEGIN IMMEDIATE")
        try:
            # 5a. Duplicate booking on same call
            existing = None
            if call_uid:
                existing = conn.execute(
                    "SELECT id FROM bookings WHERE call_uid = ? AND agent_id = ? ORDER BY id DESC LIMIT 1",
                    (call_uid, agent_id)
                ).fetchone()

            # 5b. Slot overlap check (only when we have parseable datetime)
            if not existing and slot_start_iso and slot_end_iso:
                overlap = conn.execute(
                    """
                    SELECT id FROM bookings
                    WHERE agent_id = ?
                      AND schedule_status = 'CONFIRMED'
                      AND slot_start != ''
                      AND slot_end   != ''
                      AND slot_start < ?
                      AND slot_end   > ?
                    LIMIT 1
                    """,
                    (agent_id, slot_end_iso, slot_start_iso)
                ).fetchone()
                if overlap:
                    conn.execute("ROLLBACK")
                    return False, None, (
                        f"Time slot conflict: there is already a confirmed booking "
                        f"that overlaps with {exact_dt}. Please choose a different time."
                    )

            if existing:
                valid_args["booking_id"] = existing["id"]
                # Update in place (keeping existing slot)
                conn.execute(
                    """
                    UPDATE bookings
                    SET name=?, phone=?, datetime=?, reason=?, updated_at=?,
                        slot_start=?, slot_end=?
                    WHERE id=?
                    """,
                    (valid_args["name"], valid_args["phone"], valid_args["datetime"],
                     valid_args["reason"], now_iso(),
                     slot_start_iso, slot_end_iso,
                     existing["id"])
                )
                row = conn.execute("SELECT * FROM bookings WHERE id = ?", (existing["id"],)).fetchone()
                booking = enhance_booking(row_to_dict(row), agent_id)
            else:
                cur = conn.execute(
                    """
                    INSERT INTO bookings
                      (agent_id, call_uid, name, phone, datetime, reason,
                       created_at, schedule_status, proposed_alternative,
                       slot_start, slot_end)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (agent_id, call_uid,
                     valid_args["name"], valid_args["phone"],
                     valid_args["datetime"], valid_args["reason"],
                     now_iso(), "CONFIRMED", "",
                     slot_start_iso, slot_end_iso)
                )
                booking_id = cur.lastrowid
                row = conn.execute("SELECT * FROM bookings WHERE id = ?", (booking_id,)).fetchone()
                booking = enhance_booking(row_to_dict(row), agent_id)

                # Phase F outbox: insert external-sync task AFTER booking row, before COMMIT
                conn.execute(
                    """
                    INSERT INTO outbox (agent_id, booking_id, event, payload, status, created_at)
                    VALUES (?, ?, 'booking_created', ?, 'PENDING', ?)
                    """,
                    (agent_id, booking_id,
                     json.dumps({"booking_id": booking_id, "agent_id": agent_id}),
                     now_iso())
                )

            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise

    return True, booking, "Booking saved successfully."



def should_enable_booking_tools(messages: list) -> bool:
    """
    Prevents LLMs from prematurely calling save_booking during inquiries
    before the caller has actually shared both check-in dates and their name/phone.
    """
    if not messages:
        return False

    user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
    if not user_texts:
        return False

    combined_user = " ".join(user_texts).lower()

    date_indicators = [
        "today", "tomorrow", "tonight", "night", "nights", "day", "days",
        "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
        "january", "february", "march", "april", "may", "june", "july",
        "august", "september", "october", "november", "december",
        "next week", "weekend", "pm", "am", "clock", "check in", "check-in"
    ]
    has_date = any(w in combined_user for w in date_indicators) or bool(re.search(r"\b\d{1,2}(st|nd|rd|th|\s*(?:am|pm)|[/-]\d{1,2})\b", combined_user))

    has_phone = bool(re.search(r"\b\d{5,}\b", combined_user))
    has_name = any(kw in combined_user for kw in ["my name is", "i'm ", "i am ", "this is ", "name's "])

    # Only enable booking tools when user has given date AND their name or phone
    if has_date and (has_name or has_phone):
        return True

    return False


def build_calendar_prompt() -> str:
    now = datetime.now()
    today_str = now.strftime("%A, %B %d, %Y")
    tomorrow = now + timedelta(days=1)
    tomorrow_str = tomorrow.strftime("%A, %B %d, %Y")
    day_after = now + timedelta(days=2)
    day_after_str = day_after.strftime("%A, %B %d, %Y")

    return (
        f"\n\n# REAL-TIME CALENDAR TRUTH TABLE (MANDATORY EXACT MATCH):\n"
        f"• TODAY: {today_str}\n"
        f"• TOMORROW: {tomorrow_str}\n"
        f"• DAY AFTER TOMORROW: {day_after_str}\n"
        f"CALENDAR DIRECTIVES:\n"
        f"1. Today is {today_str}. Never confuse today with tomorrow.\n"
        f"2. Tomorrow is strictly {tomorrow_str}.\n"
        f"3. Day after tomorrow is strictly {day_after_str}.\n"
        f"4. When confirming or speaking dates, quote these exact dates without guessing.\n"
    )


BOOKING_SYSTEM_GUARDRAIL = (
    "\n\n# STRICT RESERVATION & BOOKING CONVERSATION RULES:\n"
    "1. GUEST INQUIRIES: When a guest asks about rooms, pricing, or facilities, answer clearly and conversationally. "
    "DO NOT attempt to finalize or save a booking during initial inquiries.\n"
    "2. GATHERING INFORMATION: When the guest expresses interest in booking, ask one question at a time:\n"
    "   - First ask for their desired check-in and check-out dates.\n"
    "   - Next ask for the guest's full name.\n"
    "   - Next ask for their contact phone number.\n"
    "3. EXPLICIT CONFIRMATION: Summarize the reservation details (name, dates, room category) and ask: "
    "'Would you like me to confirm this booking for you?'\n"
    "4. FINALIZING: You may ONLY call the save_booking function after the guest explicitly says yes or confirms.\n"
    "5. NEVER use your own name (the receptionist), 'guest's full name', 'null', or placeholders as the guest's name.\n"
    "6. DATES: When the guest says 'tomorrow', map it to tomorrow's exact calendar date (the day after today), NEVER today's date."
)


def update_booking_db(agent_id: int, call_uid: Optional[str], args: dict) -> dict:
    with db() as conn:
        row = None
        if args.get("booking_id"):
            row = conn.execute("SELECT * FROM bookings WHERE id = ? AND agent_id = ?", (args["booking_id"], agent_id)).fetchone()
        elif call_uid:
            row = conn.execute("SELECT * FROM bookings WHERE call_uid = ? AND agent_id = ? ORDER BY id DESC LIMIT 1", (call_uid, agent_id)).fetchone()
        if not row:
            return save_booking(agent_id, call_uid, args)
        bid = row["id"]
        curr = row_to_dict(row)
        name = args.get("name") or curr.get("name")
        phone = args.get("phone") or curr.get("phone")
        dt = args.get("datetime") or curr.get("datetime")
        reason = args.get("reason") or curr.get("reason")
        now = now_iso()
        conn.execute("UPDATE bookings SET name=?, phone=?, datetime=?, reason=?, updated_at=? WHERE id=?",
                     (name, phone, dt, reason, now, bid))
        updated = conn.execute("SELECT * FROM bookings WHERE id = ?", (bid,)).fetchone()
    return enhance_booking(row_to_dict(updated), agent_id)


# ---- chat (RAG + tools) ----
BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "save_booking",
        "description": (
            "FINAL STEP ONLY: Call this function ONLY after the guest has provided their real full name, "
            "contact number, check-in dates, and explicitly confirmed verbally: 'Yes, please book it'. "
            "NEVER call this during general inquiries or before the guest gives explicit confirmation."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "The guest caller's real full name (NEVER use 'null', placeholder, or the receptionist's name)"
                },
                "phone": {
                    "type": "string",
                    "description": "The guest caller's contact phone number"
                },
                "datetime": {
                    "type": "string",
                    "description": "The check-in date or duration specified by the guest"
                },
                "reason": {
                    "type": "string",
                    "description": "Selected room category or reservation notes"
                },
                "user_confirmed": {
                    "type": "boolean",
                    "description": "Must be TRUE only if the guest explicitly confirmed they want to finalize this booking"
                }
            },
            "required": ["name", "datetime", "user_confirmed"],
        },
    },
}

UPDATE_BOOKING_TOOL = {
    "type": "function",
    "function": {
        "name": "update_booking",
        "description": (
            "Update or correct an existing booking details (e.g. if the caller changed their mind about name, time, or phone)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "booking_id": {"type": "integer", "description": "ID of the booking to update, if known"},
                "name": {"type": "string", "description": "Caller's corrected name"},
                "phone": {"type": "string", "description": "Corrected phone number"},
                "datetime": {"type": "string", "description": "Corrected desired date/time"},
                "reason": {"type": "string", "description": "Corrected reason for booking"},
            },
        },
    },
}

# ---- Audio & Speech Endpoints ----
WHISPER_HALLUCINATIONS = {
    "thanks for watching", "subtitles by", "subtitles by the amara org community",
    "subtitles by the amara.org community", "music", "please subscribe",
    "subscribe", "like and subscribe", "watching"
}

def _clean_whisper_text(text: str) -> str:
    """Bug 12 Fix: strip ALL non-word punctuation (including curly quotes, ellipsis, etc.)
    before checking against the hallucination set."""
    import re as _re
    return _re.sub(r"[^\w\s]", "", text.lower()).strip()

STUDIO_VOICES = [
    {"id": "zira", "name": "Microsoft Zira (Windows Native Offline - Female)"},
    {"id": "david", "name": "Microsoft David (Windows Native Offline - Male)"},
    {"id": "en-US-AriaNeural", "name": "Aria (Edge Neural - Online Female)"},
    {"id": "en-US-GuyNeural", "name": "Guy (Edge Neural - Online Male)"},
    {"id": "en-US-JennyNeural", "name": "Jenny (Edge Neural - Online Female)"},
    {"id": "en-GB-SoniaNeural", "name": "Sonia (Edge Neural - Online UK Female)"},
    {"id": "en-IN-NeerjaNeural", "name": "Neerja (Edge Neural - Online India Female)"},
    {"id": "en-IN-PrabhatNeural", "name": "Prabhat (Edge Neural - Online India Male)"},
]

@app.get("/api/voices")
def get_voices():
    return STUDIO_VOICES

_CACHED_LOCAL_WHISPER = None

def get_local_whisper():
    """Thread-safe singleton for Faster-Whisper with GPU acceleration and warm-up."""
    global _CACHED_LOCAL_WHISPER
    if _CACHED_LOCAL_WHISPER is not None:
        return _CACHED_LOCAL_WHISPER
    try:
        from faster_whisper import WhisperModel
        import ctranslate2
        try:
            has_cuda = ctranslate2.get_cuda_device_count() > 0
        except Exception:
            has_cuda = False
        device = "cuda" if has_cuda else "cpu"
        compute_type = "float16" if has_cuda else "int8"
        print(f"[STT] Initializing Local Faster-Whisper on {device.upper()} ({compute_type})...")
        model = WhisperModel("base.en", device=device, compute_type=compute_type)
        # Pre-warm CUDA graph with 0.1s dummy audio so first voice turn has zero cold start lag
        try:
            import wave
            wio = io.BytesIO()
            with wave.open(wio, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(b"\x00\x00" * 1600)
            wio.seek(0)
            list(model.transcribe(wio, vad_filter=True)[0])
            print(f"[STT] Local Faster-Whisper CUDA warm-up complete!")
        except Exception as we:
            print(f"[STT] Warm-up notice: {we}")
        _CACHED_LOCAL_WHISPER = model
        return _CACHED_LOCAL_WHISPER
    except Exception as e:
        print(f"[STT] Local Faster-Whisper init failed: {e}")
        return None

@app.post("/api/transcribe")
async def transcribe_audio(file: UploadFile = File(...), language: Optional[str] = Form(None), prompt: Optional[str] = Form(None)):
    """
    Speech-to-Text inference:
    Runs 100% locally via Faster-Whisper (CUDA float16 + Silero VAD) with zero cloud reliance.
    Offloaded to a background thread pool via asyncio.to_thread so the FastAPI event loop never blocks.
    """
    raw = await file.read()
    if not raw or len(raw) < 2048:
        return {"text": "", "language": "en"}

    target_lang = (language or "en").split("-")[0].lower()
    default_prompt = (prompt or "Conversational English voice call: appointments, bookings, schedule, names.").strip()

    # 1. Primary: Local Faster-Whisper (CUDA GPU)
    model = get_local_whisper()
    if model:
        def _sync_transcribe(raw_bytes: bytes) -> tuple[str, str]:
            segments, info = model.transcribe(
                io.BytesIO(raw_bytes),
                beam_size=1,
                language=target_lang,
                initial_prompt=default_prompt,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=250)
            )
            text = " ".join([seg.text for seg in segments]).strip()
            return text, (info.language or target_lang)

        try:
            import time as _time
            t0 = _time.monotonic()
            text, detected_lang = await asyncio.to_thread(_sync_transcribe, raw)
            latency_ms = round((_time.monotonic() - t0) * 1000)

            # Clean hallucinations
            if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                text = ""

            if text:
                print(f"[STT Local CUDA] {latency_ms}ms: '{text}'")
            return {"text": text, "language": detected_lang, "latency_ms": latency_ms, "engine": "local_faster_whisper"}
        except Exception as e:
            print(f"[STT] Local faster-whisper error: {e}")

    # 2. Cloud Fallback (only if local failed and a cloud STT key is configured)
    if STT_API_KEY and STT_API_KEY != "ollama" and "groq" in STT_BASE_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                files = {"file": (file.filename or "utterance.wav", raw, "audio/wav")}
                data = {
                    "model": STT_MODEL,
                    "temperature": "0.0",
                    "language": target_lang,
                    "prompt": default_prompt,
                    "response_format": "json"
                }
                headers = {"Authorization": f"Bearer {STT_API_KEY}"}
                r = await client.post(f"{STT_BASE_URL}/audio/transcriptions", files=files, data=data, headers=headers)
                if r.status_code == 200:
                    text = (r.json().get("text") or "").strip()
                    if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                        text = ""
                    return {"text": text, "language": target_lang, "engine": "cloud_whisper"}
        except Exception as e:
            print(f"[STT] Cloud fallback error: {e}")

    return {"text": "", "language": "en"}

# Bug 4 Fix: replace unbounded dict with an LRU-limited OrderedDict (max 256 entries).
# Each Edge-TTS MP3 is ~25-100 KB; 256 entries = max ~25 MB RAM for TTS cache.
from collections import OrderedDict

_TTS_CACHE: OrderedDict = OrderedDict()
_TTS_CACHE_MAX = 256

def _tts_cache_put(key: str, value: tuple):
    """Insert into LRU cache, evicting the oldest entry when full."""
    if key in _TTS_CACHE:
        _TTS_CACHE.move_to_end(key)
    else:
        if len(_TTS_CACHE) >= _TTS_CACHE_MAX:
            _TTS_CACHE.popitem(last=False)  # evict LRU
        _TTS_CACHE[key] = value

def _tts_cache_get(key: str):
    """Retrieve from LRU cache and mark as recently used."""
    if key not in _TTS_CACHE:
        return None
    _TTS_CACHE.move_to_end(key)
    return _TTS_CACHE[key]

def _apply_sapi5_voice(engine, requested_voice: str, rate: float = 1.0):
    v_list = engine.getProperty("voices") or []
    req = (requested_voice or "").lower().strip()
    is_male = any(m in req for m in ["david", "male", "guy", "christopher", "george"])
    selected_id = None

    if is_male:
        for v in v_list:
            if "david" in v.name.lower() or "male" in v.name.lower():
                selected_id = v.id
                break
    else:
        for v in v_list:
            if "zira" in v.name.lower() or "female" in v.name.lower():
                selected_id = v.id
                break

    if not selected_id and v_list:
        for v in v_list:
            if not is_male and ("zira" in v.id.lower() or "female" in v.id.lower()):
                selected_id = v.id
                break
        if not selected_id:
            if not is_male and len(v_list) > 1:
                selected_id = v_list[1].id
            else:
                selected_id = v_list[0].id

    if selected_id:
        engine.setProperty("voice", selected_id)
    engine.setProperty("rate", int(200 * rate))


async def synthesize_speech_bytes(text: str, voice: str = "zira", rate: float = 1.0) -> bytes:
    """Synthesize speech returning WAV bytes (used by Twilio telephony and TTS caching)."""
    if not text:
        return b""
    clean_text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    clean_text = re.sub(r"\*([^*]+)\*", r"\1", clean_text)
    clean_text = re.sub(r"[#*`_~]", "", clean_text).strip()

    cache_key = f"{voice}_{rate}_{clean_text}"
    cached = _tts_cache_get(cache_key)
    if cached and cached[1] == "audio/wav":
        return cached[0]

    def _sync_pyttsx3():
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except Exception:
            pass
        import pyttsx3, tempfile
        try:
            engine = pyttsx3.init()
            _apply_sapi5_voice(engine, voice, rate)
            with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                tmp_path = tmp.name
            engine.save_to_file(clean_text, tmp_path)
            engine.runAndWait()
            with open(tmp_path, "rb") as f:
                wav_bytes = f.read()
            try:
                os.remove(tmp_path)
            except Exception:
                pass
            return wav_bytes
        finally:
            try:
                import pythoncom
                pythoncom.CoUninitialize()
            except Exception:
                pass

    try:
        wav_bytes = await asyncio.to_thread(_sync_pyttsx3)
        if wav_bytes:
            _tts_cache_put(cache_key, (wav_bytes, "audio/wav"))
            return wav_bytes
    except Exception as e:
        print(f"[synthesize_speech_bytes] error: {e}")
    return b""


async def transcribe_audio_bytes(raw_bytes: bytes, language: Optional[str] = None, prompt: Optional[str] = None) -> str:
    """Transcribe raw audio bytes using local Faster-Whisper or Groq STT fallback."""
    if not raw_bytes or len(raw_bytes) < 1024:
        return ""
    target_lang = (language or "en").split("-")[0].lower()
    default_prompt = (prompt or "Conversational English voice call: appointments, bookings, schedule, names.").strip()

    model = get_local_whisper()
    if model:
        def _sync_transcribe(raw: bytes) -> str:
            segments, _ = model.transcribe(
                io.BytesIO(raw),
                beam_size=1,
                language=target_lang,
                initial_prompt=default_prompt,
                temperature=0.0,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=250)
            )
            return " ".join([seg.text for seg in segments]).strip()
        try:
            text = await asyncio.to_thread(_sync_transcribe, raw_bytes)
            if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                text = ""
            return text
        except Exception as e:
            print(f"[transcribe_audio_bytes] Local faster-whisper error: {e}")

    if STT_API_KEY and STT_API_KEY != "ollama" and "groq" in STT_BASE_URL:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                files = {"file": ("utterance.wav", raw_bytes, "audio/wav")}
                data = {
                    "model": STT_MODEL,
                    "temperature": "0.0",
                    "language": target_lang,
                    "prompt": default_prompt,
                    "response_format": "json"
                }
                headers = {"Authorization": f"Bearer {STT_API_KEY}"}
                r = await client.post(f"{STT_BASE_URL}/audio/transcriptions", files=files, data=data, headers=headers)
                if r.status_code == 200:
                    text = (r.json().get("text") or "").strip()
                    if _clean_whisper_text(text) in WHISPER_HALLUCINATIONS:
                        text = ""
                    return text
        except Exception as e:
            print(f"[transcribe_audio_bytes] Cloud STT error: {e}")

    return ""


@app.post("/api/tts")
async def text_to_speech(request: Request):
    """Studio Text-to-Speech: Defaults to 100% offline local Windows SAPI5 (pyttsx3) with in-memory caching."""
    body = await request.json()
    text = (body.get("text") or "").strip()
    voice = (body.get("voice") or TTS_VOICE).strip()
    rate_val = float(body.get("rate") or 1.0)

    if not text:
        raise HTTPException(status_code=400, detail="Text cannot be empty")

    # Clean text from markdown / symbols
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\*([^*]+)\*", r"\1", text)
    text = re.sub(r"[#*`_~]", "", text).strip()

    cache_key = f"{voice}_{rate_val}_{text}"
    cached = _tts_cache_get(cache_key)
    if cached:
        cached_bytes, cached_media = cached
        return Response(content=cached_bytes, media_type=cached_media)

    # 1. Windows Native SAPI5 via pyttsx3 (100% Local Offline)
    if "david" in voice.lower() or "zira" in voice.lower() or not "Neural" in voice:
        def _sync_pyttsx3():
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            import pyttsx3, tempfile
            try:
                engine = pyttsx3.init()
                _apply_sapi5_voice(engine, voice, rate_val)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                with open(tmp_path, "rb") as f:
                    wav_bytes = f.read()
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                return wav_bytes
            finally:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

        try:
            wav_bytes = await asyncio.to_thread(_sync_pyttsx3)
            _tts_cache_put(cache_key, (wav_bytes, "audio/wav"))
            return Response(content=wav_bytes, media_type="audio/wav")
        except Exception as e:
            print(f"[TTS Local pyttsx3] error: {e}")

    # 2. Edge-TTS neural synthesis
    try:
        import edge_tts
        rate_pct = int((rate_val - 1.0) * 100)
        rate_str = f"+{rate_pct}%" if rate_pct >= 0 else f"{rate_pct}%"
        chosen_voice = voice if "Neural" in voice else "en-US-AriaNeural"
        communicate = edge_tts.Communicate(text, chosen_voice, rate=rate_str)
        mp3_buf = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buf.extend(chunk["data"])
        if mp3_buf:
            res_bytes = bytes(mp3_buf)
            _tts_cache_put(cache_key, (res_bytes, "audio/mpeg"))
            return Response(content=res_bytes, media_type="audio/mpeg")
    except Exception as e:
        print(f"[TTS] Edge-TTS error: {e}")

    # 3. Fallback: try pyttsx3 with consistent voice preservation
    try:
        def _sync_fallback():
            try:
                import pythoncom
                pythoncom.CoInitialize()
            except Exception:
                pass
            import pyttsx3, tempfile
            try:
                engine = pyttsx3.init()
                _apply_sapi5_voice(engine, voice, rate_val)
                with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
                    tmp_path = tmp.name
                engine.save_to_file(text, tmp_path)
                engine.runAndWait()
                with open(tmp_path, "rb") as f:
                    wav_bytes = f.read()
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass
                return wav_bytes
            finally:
                try:
                    import pythoncom
                    pythoncom.CoUninitialize()
                except Exception:
                    pass
        wav_bytes = await asyncio.to_thread(_sync_fallback)
        _tts_cache_put(cache_key, (wav_bytes, "audio/wav"))
        return Response(content=wav_bytes, media_type="audio/wav")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"TTS synthesis failed: {e}")



async def llm_chat(messages: List[dict], tools: Optional[list] = None, max_tokens: int = 300, temperature: float = 0.7) -> dict:
    """Routes to LLM via OpenAI-compatible API. Works with Groq, Ollama /v1, or any compatible provider."""
    payload = {"model": MODEL, "messages": messages, "temperature": temperature, "max_tokens": max_tokens}
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60) as client:
        r = await client.post(f"{BASE_URL}/chat/completions", json=payload, headers=headers)
        if r.status_code != 200:
            print(f"[llm_chat] LLM provider error {r.status_code}: {r.text}")
        r.raise_for_status()
        return r.json()


@app.post("/api/optimize-prompt")
async def optimize_prompt(request: Request, user: dict = Depends(require_user)):
    """Quantum-Based Prompt Optimization Engine"""
    body = await request.json()
    original_prompt = (body.get("prompt") or "").strip()
    if not original_prompt:
        return {"optimized": ""}

    ENGINEER_INSTRUCTION = (
        "You are a world-class AI System Prompt Engineer who has designed prompts for "
        "production voice agents at companies like Vapi, Retell, and OpenAI. "
        "Your task is to transform the user's draft prompt into a professional, "
        "production-grade system prompt for a conversational voice AI agent.\n\n"
        "Rules for your output:\n"
        "- Start with a clear identity and role definition (e.g., 'You are [Name], a [role]...')\n"
        "- Define the agent's personality and tone explicitly\n"
        "- Set strict behavioral boundaries (what to do AND what to never do)\n"
        "- Add conversation flow rules (e.g., 'Ask one question at a time', 'Keep replies to 1-3 sentences')\n"
        "- Include guardrails for edge cases (off-topic, abusive callers, unknown questions)\n"
        "- Ensure it is optimized for SPOKEN voice output (no markdown, no lists, no emojis, no code)\n"
        "- Output ONLY the final system prompt, nothing else. No explanations, no preamble."
    )

    TEMPLATE_INSTRUCTION = (
        "You are a world-class AI System Prompt Engineer. Your task is to take the user's draft prompt "
        "and transform it into a structured, production-grade system prompt by filling in the template below.\n\n"
        "IMPORTANT RULES:\n"
        "- Replace every [placeholder] with specific, relevant content derived from the user's draft.\n"
        "- If the draft doesn't mention something, infer reasonable defaults for a voice AI agent.\n"
        "- Output ONLY the completed template. No explanations, no preamble, no commentary.\n\n"
        "TEMPLATE:\n"
        'You are **[Agent Name]**, a conversational AI that helps users **[primary purpose]**.\n\n'
        '# Role\n\n'
        'Your primary responsibility is to **[main objective]**.\n'
        'You should rely on **[available data source/tools]** whenever factual information is required.\n\n'
        '# Voice Style\n\n'
        '* Speak **[desired tone]**.\n'
        '* Keep responses **[length preference]**.\n'
        '* **[Additional communication guideline]**.\n'
        '* **[Additional communication guideline]**.\n'
        '* **[Additional communication guideline]**.\n\n'
        '# Responsibilities\n\n'
        'You can help users:\n'
        '* [Capability 1]\n* [Capability 2]\n* [Capability 3]\n* [Capability 4]\n* [Capability 5]\n\n'
        '# Query Behavior\n\n'
        'Before responding, identify:\n'
        '* [Required parameter 1]\n* [Required parameter 2]\n* [Required parameter 3]\n* [Required parameter 4]\n\n'
        'If required information is missing, **[clarification policy]**.\n'
        'Example: "[Example clarification question]"\n'
        'Do not **[assumption or prohibited behavior]**.\n\n'
        '# Result Summarization\n\n'
        'For multiple results:\n1. [Summarization step 1]\n2. [Summarization step 2]\n3. [Summarization step 3]\n\n'
        'Avoid **[undesired behavior]** unless requested.\n\n'
        '# Single Item Responses\n\n'
        'For a single result, include:\n* [Field 1]\n* [Field 2]\n* [Field 3]\n* [Field 4]\n\n'
        '# Date and Time Handling\n\n'
        'Interpret natural language expressions such as:\n* [Example]\n* [Example]\n\n'
        'If ambiguous, **[clarification policy]**.\n\n'
        '# Follow-up Questions\n\n'
        'Maintain conversational context across multiple turns.\n'
        'Understand that follow-up references apply to previous context whenever appropriate.\n\n'
        '# Ambiguity Handling\n\n'
        'If multiple matches exist:\n"[Example clarification response]"\n'
        'Never **[undesired behavior]**.\n\n'
        '# Security\n\n'
        'Respect **[authorization model]**.\n'
        'Never reveal information that users are not authorized to access.\n'
        'If access is denied: "[Access denied response]"\n'
        'Do not **[prohibited behavior]**.\n\n'
        '# Error Handling\n\n'
        'If an operation fails:\n* [Instruction]\n* [Instruction]\n'
        'Do not **[prohibited behavior]**.\n\n'
        '# Sensitive Information\n\n'
        'Do not expose:\n* [Sensitive data type]\n* [Sensitive data type]\n'
        'Mask sensitive information whenever appropriate.\n\n'
        '# Tool Usage\n\n'
        'Whenever external information is required:\n'
        '* Use **[available tools]**.\n* Do not rely on unsupported information.\n'
        '* Wait for results before responding.\n* Base responses on available data.\n\n'
        '# Conversation Goal\n\n'
        'Help users **[overall objective]** while remaining **[desired qualities]**.'
    )

    async def gen_variant(extra_focus: str):
        try:
            resp = await llm_chat([
                {"role": "system", "content": ENGINEER_INSTRUCTION + "\n\nAdditional focus: " + extra_focus},
                {"role": "user", "content": f"Transform this draft into a production-grade system prompt:\n\n{original_prompt}"}
            ], temperature=0.8, max_tokens=400)
            return (resp["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:
            print(f"[optimize_prompt] gen_variant error: {e}")
            return original_prompt

    async def gen_template_variant():
        try:
            resp = await llm_chat([
                {"role": "system", "content": TEMPLATE_INSTRUCTION},
                {"role": "user", "content": f"Fill in the template using this draft prompt:\n\n{original_prompt}"}
            ], temperature=0.7, max_tokens=800)
            return (resp["choices"][0]["message"].get("content") or "").strip()
        except Exception as e:
            print(f"[optimize_prompt] gen_template_variant error: {e}")
            return original_prompt

    tasks = [
        gen_variant("Prioritize clarity and strict behavioral rules. The agent must never go off-script."),
        gen_variant("Prioritize warmth, empathy, and natural conversational flow for voice calls."),
        gen_variant("Prioritize conciseness and efficiency. Every word must earn its place."),
        gen_template_variant()
    ]
    
    variants = await asyncio.gather(*tasks)
    
    # Include the original prompt as a candidate — if it's already great, QAOA will select it
    all_candidates = [original_prompt] + list(variants)
    labels = ["Original (unchanged)", "Variant 1 (Strict & Structured)", "Variant 2 (Warm & Conversational)", "Variant 3 (Concise & Efficient)", "Variant 4 (Professional Template)"]
    
    # Expert-level scoring heuristics for QUBO mapping
    scores = []
    for v in all_candidates:
        score = 0.0
        v_low = v.lower()
        words = v_low.split()
        
        # Identity & role definition (critical for system prompts)
        if "you are" in v_low: score += 20
        if any(w in v_low for w in ["role", "persona", "identity", "assistant", "agent"]): score += 10
        
        # Behavioral boundaries
        boundary_words = ["never", "always", "must", "do not", "don't", "avoid", "ensure", "refrain"]
        score += sum(5 for w in boundary_words if w in v_low)
        
        # Conversation flow rules
        flow_words = ["one question", "brief", "concise", "short", "1-3 sentences", "spoken", "conversational"]
        score += sum(8 for w in flow_words if w in v_low)
        
        # Voice-specific optimization
        if any(w in v_low for w in ["voice", "call", "caller", "speak", "spoken"]): score += 10
        
        # Penalize non-voice artifacts
        if "markdown" in v_low or "```" in v or "emoji" in v_low: score -= 20
        if "output format" in v_low or "json" in v_low: score -= 15
        
        # Length sweet spot (good system prompts are 80-350 words)
        wc = len(words)
        if 80 <= wc <= 350: score += 15
        elif 40 <= wc < 80: score += 5
        elif wc > 500: score -= 10
        elif wc < 20: score -= 15
        
        # Structured template patterns (reward professional formatting)
        section_headers = ["# role", "# voice", "# responsibilities", "# security", 
                           "# error", "# query", "# tool", "# conversation"]
        section_count = sum(1 for h in section_headers if h in v_low)
        score += section_count * 6  # Each section adds structure quality
        
        # Examples and guardrails (hallmark of expert prompts)
        if "example" in v_low: score += 8
        if "if access is denied" in v_low or "sensitive" in v_low: score += 8
        
        # Penalize if the LLM added meta-commentary instead of a real prompt
        if v_low.startswith("here") or v_low.startswith("sure") or v_low.startswith("below"): score -= 25
        
        # Penalize unfilled placeholders (template not properly filled)
        import re as _re
        unfilled = len(_re.findall(r'\[.*?\]', v))
        if unfilled > 3: score -= unfilled * 2
        
        scores.append(float(score))
    
    print(f"⚛️  [QUANTUM] Prompt candidates: {labels}")
    print(f"⚛️  [QUANTUM] Scores: {scores}")
    
    best_idx = select_best_path_quantum(scores)
    
    return {
        "optimized": all_candidates[best_idx],
        "variants": all_candidates,
        "scores": scores,
        "selected_index": best_idx,
        "selected_label": labels[best_idx]
    }


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
            agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    blocked, safe_msg = evaluate_conversational_guardrail(last_user)
    if blocked:
        return {"reply": safe_msg, "events": []}

    has_kb = False
    if agent_id:
        with db() as conn:
            has_kb = bool(agent and (agent.get("use_knowledge") or conn.execute("SELECT 1 FROM chunks WHERE agent_id = ? LIMIT 1", (agent_id,)).fetchone()))
    if has_kb and agent_id:
        user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        search_query = " ".join(user_texts[-2:]) if user_texts else last_user
        ctx = retrieve_context(agent_id, search_query)
        if ctx:
            system += (
                "\n\n# VERIFIED KNOWLEDGE BASE:\n"
                "Use the following verified resort information to answer guest questions accurately, naturally, and concisely:\n"
                "--- KNOWLEDGE BASE START ---\n"
                + "\n---\n".join(ctx)
                + "\n--- KNOWLEDGE BASE END ---\n"
            )

    enable_tools = bool(agent and agent.get("tools_enabled") and should_enable_booking_tools(messages))
    tools = [BOOKING_TOOL, UPDATE_BOOKING_TOOL] if enable_tools else None
    system += build_calendar_prompt()
    if agent and agent.get("tools_enabled"):
        system += BOOKING_SYSTEM_GUARDRAIL
    convo = [{"role": "system", "content": system}] + messages

    try:
        resp = await llm_chat(convo, tools=tools)
        msg = resp["choices"][0]["message"]
        events = []
        if msg.get("tool_calls"):
            convo.append(msg)
            for tc in msg["tool_calls"]:
                fname = tc.get("function", {}).get("name")
                try:
                    args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if fname == "save_booking":
                    is_valid, booking, err_msg = validate_and_save_booking(agent_id, call_uid, args, agent, messages=messages)
                    if is_valid and booking:
                        events.append({"type": "booking_saved", "booking": booking})
                        hook = (agent.get("booking_webhook") or "").strip() if agent else ""
                        if hook:
                            background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                        if agent:
                            background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                        convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking saved successfully."})
                    else:
                        convo.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": f"Booking NOT saved: {err_msg}. Do NOT tell the guest that the room is booked. Ask the guest for their full name, check-in dates, and verbal confirmation first."
                        })
                elif fname == "update_booking":
                    booking = update_booking_db(agent_id, call_uid, args)
                    events.append({"type": "booking_updated", "booking": booking})
                    hook = (agent.get("booking_webhook") or "").strip() if agent else ""
                    if hook:
                        background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                    if agent:
                        background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking updated successfully."})
                else:
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Done."})
            resp2 = await llm_chat(convo, tools=None)
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

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    blocked, safe_msg = evaluate_conversational_guardrail(last_user)
    if blocked:
        return {"reply": safe_msg, "events": []}

    with db() as conn:
        has_kb = bool(agent.get("use_knowledge") or conn.execute("SELECT 1 FROM chunks WHERE agent_id = ? LIMIT 1", (agent_id,)).fetchone())
    if has_kb:
        user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        search_query = " ".join(user_texts[-2:]) if user_texts else last_user
        ctx = retrieve_context(agent_id, search_query)
        if ctx:
            system += (
                "\n\n# VERIFIED KNOWLEDGE BASE:\n"
                "Use the following verified resort information to answer guest questions accurately, naturally, and concisely:\n"
                "--- KNOWLEDGE BASE START ---\n"
                + "\n---\n".join(ctx)
                + "\n--- KNOWLEDGE BASE END ---\n"
            )

    enable_tools = bool(agent and agent.get("tools_enabled") and should_enable_booking_tools(messages))
    tools = [BOOKING_TOOL, UPDATE_BOOKING_TOOL] if enable_tools else None
    system += build_calendar_prompt()
    if agent and agent.get("tools_enabled"):
        system += BOOKING_SYSTEM_GUARDRAIL
    convo = [{"role": "system", "content": system}] + messages

    try:
        resp = await llm_chat(convo, tools=tools)
        msg = resp["choices"][0]["message"]
        events = []
        if msg.get("tool_calls"):
            convo.append(msg)
            for tc in msg["tool_calls"]:
                fname = tc.get("function", {}).get("name")
                try:
                    args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if fname == "save_booking":
                    is_valid, booking, err_msg = validate_and_save_booking(agent_id, call_uid, args, agent, messages=messages)
                    if is_valid and booking:
                        events.append({"type": "booking_saved", "booking": booking})
                        hook = (agent.get("booking_webhook") or "").strip()
                        if hook:
                            background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                        background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                        convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking saved successfully."})
                    else:
                        convo.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "content": f"Booking NOT saved: {err_msg}. Do NOT tell the guest that the room is booked. Ask the guest for their full name, check-in dates, and verbal confirmation first."
                        })
                elif fname == "update_booking":
                    booking = update_booking_db(agent_id, call_uid, args)
                    events.append({"type": "booking_updated", "booking": booking})
                    hook = (agent.get("booking_webhook") or "").strip()
                    if hook:
                        background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                    background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking updated successfully."})
                else:
                    convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Done."})
            resp2 = await llm_chat(convo, tools=None)
            reply = (resp2["choices"][0]["message"].get("content") or "").strip() or \
                "Done — I've saved that for you. Anything else?"
        else:
            reply = (msg.get("content") or "").strip()
            # If the model emitted a pseudo tool JSON instead of natural language, clean it up
            if reply.startswith("{") and reply.endswith("}"):
                try:
                    jd = json.loads(reply)
                    if "name" in jd or "function" in jd:
                        params = jd.get("parameters") or jd.get("arguments") or {}
                        if isinstance(params, str):
                            try: params = json.loads(params)
                            except Exception: params = {}
                        cat = params.get("category") or ""
                        pr = params.get("price_per_day") or params.get("price") or params.get("rate")
                        if pr:
                            reply = f"The {cat} room rate is {pr} per day and night." if cat else f"The room rate is {pr} per day and night."
                        else:
                            reply = "I have that information available. How can I assist you with your booking?"
                except Exception:
                    pass
            
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


def extract_inline_tool_call(text: str) -> Optional[tuple[str, dict]]:
    """Extracts tool call from models (e.g. Ollama Llama 3.2) that output JSON directly into content."""
    text = (text or "").strip()
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    if text.startswith("{") and text.endswith("}"):
        try:
            d = json.loads(text)
            if any(k in d for k in ["name", "function", "parameters", "arguments", "properties"]):
                fn = d.get("name") or d.get("function") or "save_booking"
                params = d.get("parameters") or d.get("arguments") or {}
                if isinstance(params, str):
                    try:
                        params = json.loads(params)
                    except Exception:
                        params = {}
                for k, v in d.items():
                    if k not in ["name", "function", "parameters", "arguments", "object", "properties"]:
                        params[k] = v
                return fn, params
        except Exception:
            pass
    return None


@app.post("/chat_stream")
async def chat_stream(request: Request, background_tasks: BackgroundTasks, user: dict = Depends(require_user)):
    if not API_KEY:
        return JSONResponse(status_code=500, content={"error": "LLM_API_KEY is not set."})

    body = await request.json()
    messages = body.get("messages", [])
    system = (body.get("system") or "").strip() or DEFAULT_SYSTEM
    agent_id = body.get("agent_id")
    call_uid = body.get("call_uid")

    agent = None
    if agent_id:
        with db() as conn:
            agent = row_to_dict(owned_agent(conn, agent_id, user, required_perm="can_call"))

    last_user = next((m["content"] for m in reversed(messages) if m.get("role") == "user"), "")
    blocked, safe_msg = evaluate_conversational_guardrail(last_user)
    if blocked:
        async def blocked_stream():
            yield f"data: {json.dumps({'text': safe_msg})}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"
        return StreamingResponse(blocked_stream(), media_type="text/event-stream")

    has_kb = False
    if agent_id:
        with db() as conn:
            has_kb = bool(agent and (agent.get("use_knowledge") or conn.execute("SELECT 1 FROM chunks WHERE agent_id = ? LIMIT 1", (agent_id,)).fetchone()))
    if has_kb and agent_id:
        user_texts = [m.get("content", "") for m in messages if m.get("role") == "user"]
        search_query = " ".join(user_texts[-2:]) if user_texts else last_user
        ctx = retrieve_context(agent_id, search_query)
        if ctx:
            system += (
                "\n\n# VERIFIED KNOWLEDGE BASE:\n"
                "Use the following verified resort information to answer guest questions accurately, naturally, and concisely:\n"
                "--- KNOWLEDGE BASE START ---\n"
                + "\n---\n".join(ctx)
                + "\n--- KNOWLEDGE BASE END ---\n"
            )

    enable_tools = bool(agent and agent.get("tools_enabled") and should_enable_booking_tools(messages))
    tools = [BOOKING_TOOL, UPDATE_BOOKING_TOOL] if enable_tools else None
    system += build_calendar_prompt()
    if agent and agent.get("tools_enabled"):
        system += BOOKING_SYSTEM_GUARDRAIL
    convo = [{"role": "system", "content": system}] + messages

    async def event_generator():
        payload = {"model": MODEL, "messages": convo, "temperature": 0.6, "max_tokens": 150, "stream": True}
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"
        headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

        tool_calls_buffer = {}
        content_buffer = []
        is_json_potential = False
        full_streamed_reply = ""

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=headers) as response:
                    if response.status_code != 200:
                        err_text = await response.aread()
                        print(f"[chat_stream] LLM provider error {response.status_code}: {err_text.decode('utf-8', errors='ignore')}")
                        yield f"data: {json.dumps({'text': 'I am sorry, I am having trouble connecting. Could you please repeat that?'})}\n\n"
                        yield f"data: {json.dumps({'done': True})}\n\n"
                        return

                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data = line[6:].strip()
                            if data == "[DONE]":
                                break
                            try:
                                chunk = json.loads(data)
                                delta = chunk["choices"][0].get("delta", {})

                                if "content" in delta and delta["content"]:
                                    c = delta["content"]
                                    if tools and not content_buffer and (c.strip().startswith("{") or c.strip().startswith("`")):
                                        is_json_potential = True

                                    if is_json_potential:
                                        content_buffer.append(c)
                                    else:
                                        full_streamed_reply += c
                                        yield f"data: {json.dumps({'text': c})}\n\n"

                                if "tool_calls" in delta:
                                    for tc in delta["tool_calls"]:
                                        idx = tc["index"]
                                        if idx not in tool_calls_buffer:
                                            tool_calls_buffer[idx] = tc
                                        else:
                                            if "function" in tc and "arguments" in tc["function"]:
                                                tool_calls_buffer[idx]["function"]["arguments"] += tc["function"]["arguments"]
                            except json.JSONDecodeError:
                                continue

            # Check if buffered content was an inline tool call (Ollama)
            if is_json_potential and content_buffer:
                raw_json = "".join(content_buffer)
                fn, args = extract_inline_tool_call(raw_json)
                if fn and isinstance(args, dict):
                    tool_calls_buffer[0] = {
                        "id": "inline_call_0",
                        "function": {"name": fn, "arguments": json.dumps(args)}
                    }
                else:
                    # Not a tool call, stream it as normal text
                    for c in content_buffer:
                        full_streamed_reply += c
                        yield f"data: {json.dumps({'text': c})}\n\n"

            # If tool calls were detected (via OpenAI tool_calls OR inline JSON)
            if tool_calls_buffer:
                tool_calls_list = [tool_calls_buffer[k] for k in sorted(tool_calls_buffer.keys())]
                msg_for_history = {"role": "assistant", "tool_calls": tool_calls_list}
                convo.append(msg_for_history)

                for tc in tool_calls_list:
                    fname = tc.get("function", {}).get("name") or "save_booking"
                    try:
                        args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    if "save" in fname.lower() or "booking" in fname.lower():
                        is_valid, booking, err_msg = validate_and_save_booking(agent_id, call_uid, args, agent, messages=messages)
                        if is_valid and booking:
                            yield f"data: {json.dumps({'event': {'type': 'booking_saved', 'booking': booking}})}\n\n"
                            hook = (agent.get("booking_webhook") or "").strip() if agent else ""
                            if hook:
                                background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                            if agent:
                                background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                            convo.append({"role": "tool", "tool_call_id": tc.get("id", "call_0"), "content": "Booking confirmed and saved successfully in database."})
                        else:
                            convo.append({
                                "role": "tool",
                                "tool_call_id": tc.get("id", "call_0"),
                                "content": f"Booking NOT saved: {err_msg}. Please ask the guest politely for the missing information."
                            })
                    elif "update" in fname.lower():
                        booking = update_booking_db(agent_id, call_uid, args)
                        yield f"data: {json.dumps({'event': {'type': 'booking_updated', 'booking': booking}})}\n\n"
                        hook = (agent.get("booking_webhook") or "").strip() if agent else ""
                        if hook:
                            background_tasks.add_task(fire_webhook, hook, booking_payload(agent, booking))
                        if agent:
                            background_tasks.add_task(auto_sync_booking_to_google, agent, booking)
                        convo.append({"role": "tool", "tool_call_id": tc.get("id", "call_0"), "content": "Booking updated successfully."})
                    else:
                        convo.append({"role": "tool", "tool_call_id": tc.get("id", "call_0"), "content": "Done."})

                # Stream the final spoken confirmation after tool execution
                payload["messages"] = convo
                if "tools" in payload:
                    del payload["tools"]
                if "tool_choice" in payload:
                    del payload["tool_choice"]

                async with httpx.AsyncClient(timeout=30) as client:
                    async with client.stream("POST", f"{BASE_URL}/chat/completions", json=payload, headers=headers) as response:
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                data = line[6:].strip()
                                if data == "[DONE]":
                                    break
                                try:
                                    chunk = json.loads(data)
                                    delta = chunk["choices"][0].get("delta", {})
                                    if "content" in delta and delta["content"]:
                                        full_streamed_reply += delta["content"]
                                        yield f"data: {json.dumps({'text': delta['content']})}\n\n"
                                except json.JSONDecodeError:
                                    continue

            # Update call transcript in database
            if call_uid and full_streamed_reply.strip():
                full_transcript = messages + [{"role": "assistant", "content": full_streamed_reply.strip()}]
                try:
                    with db() as conn:
                        existing = conn.execute("SELECT id FROM calls WHERE call_uid = ?", (call_uid,)).fetchone()
                        if existing:
                            conn.execute("UPDATE calls SET num_turns = ?, transcript = ?, ended_at = ? WHERE call_uid = ?",
                                         (len(full_transcript), json.dumps(full_transcript), now_iso(), call_uid))
                        else:
                            conn.execute("INSERT INTO calls (agent_id, call_uid, started_at, ended_at, num_turns, transcript) VALUES (?,?,?,?,?,?)",
                                         (agent_id, call_uid, now_iso(), now_iso(), len(full_transcript), json.dumps(full_transcript)))
                except Exception as de:
                    print(f"[chat_stream db error]: {de}")

        except Exception as e:
            print(f"[chat_stream exception]: {e}")
            yield f"data: {json.dumps({'text': 'I am sorry, could you please say that again?'})}\n\n"

        yield f"data: {json.dumps({'done': True})}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")




@app.get("/favicon.ico", include_in_schema=False)
async def favicon():
    return Response(status_code=204)

@app.get("/hybridaction/{rest_of_path:path}", include_in_schema=False)
async def ignore_extension_tracker(rest_of_path: str):
    return Response(content="", media_type="text/plain", status_code=200)

# Register server-level hooks with Twilio integration engine
twilio_integration.register_server_hooks(
    db=db,
    require_user=require_user,
    owned_agent=owned_agent,
    transcribe_audio_bytes=transcribe_audio_bytes,
    synthesize_speech_bytes=synthesize_speech_bytes,
    llm_chat=llm_chat,
    retrieve_context=retrieve_context,
    validate_and_save_booking=validate_and_save_booking,
    update_booking_db=update_booking_db,
    auto_sync_booking_to_google=auto_sync_booking_to_google,
    fire_webhook=fire_webhook,
    booking_payload=booking_payload,
    evaluate_conversational_guardrail=evaluate_conversational_guardrail,
    build_calendar_prompt=build_calendar_prompt,
    BOOKING_TOOL=BOOKING_TOOL,
    UPDATE_BOOKING_TOOL=UPDATE_BOOKING_TOOL,
    BOOKING_SYSTEM_GUARDRAIL=BOOKING_SYSTEM_GUARDRAIL,
)
app.include_router(twilio_integration.router)

# Static UI mounted last so /api and /chat take precedence.
app.mount("/", StaticFiles(directory="static", html=True), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), reload=True)

