"""
Voice Agent Studio — Twilio Voice Integration Engine.

Bridges real-world PSTN phone calls into the voice agent ecosystem:
1. Inbound Call Webhook (TwiML generation & routing):
   - Accepts incoming phone calls from Twilio numbers.
   - Routes to specific agents via phone routing table or phone number mapping.
   - Emits TwiML <Connect><Stream> connecting call audio to real-time WebSocket.
2. Bidirectional Audio Streaming (μ-law 8kHz <-> PCM 16kHz):
   - Transcodes incoming μ-law 8kHz Twilio audio to 16kHz PCM for Whisper STT.
   - Synthesizes bot responses via TTS and converts to μ-law 8kHz for PSTN streaming.
3. Conversational Pipeline on Phone:
   - Energy VAD for speech detection and turn finalization.
   - Barge-in support: interrupts assistant speech when caller speaks.
   - RAG knowledge retrieval and tool execution (booking capture, Google Calendar/Sheets sync).
   - Enterprise PII sanitization and conversational guardrails.
4. Outbound Dialing:
   - Initiate outbound agent phone calls via Twilio REST API.
5. Call Lifecycle & Status Tracking:
   - Call status callback handling (ringing, in-progress, completed, duration).
   - Full transcript recording into database with source='twilio'.
6. Local Sandbox Mode:
   - Graceful fallback when Twilio credentials are not yet configured.
"""

import os
import re
import io
import json
import wave
import base64
import audioop
import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple

import httpx
from fastapi import APIRouter, Request, Response, WebSocket, WebSocketDisconnect, HTTPException, Depends
from pydantic import BaseModel

# Twilio Client & TwiML
try:
    from twilio.rest import Client as TwilioClient
    from twilio.twiml.voice_response import VoiceResponse, Connect, Stream, Say
    from twilio.request_validator import RequestValidator
    HAS_TWILIO = True
except ImportError:
    HAS_TWILIO = False
    TwilioClient = None
    VoiceResponse = None
    Connect = None
    Stream = None
    Say = None
    RequestValidator = None


router = APIRouter()

# --- Environment Configuration ---
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "").strip()
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "").strip()
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER", "").strip()
TWILIO_WEBHOOK_BASE_URL = os.environ.get("TWILIO_WEBHOOK_BASE_URL", "").strip().rstrip("/")
TWILIO_VALIDATE_SIGNATURE = os.environ.get("TWILIO_VALIDATE_SIGNATURE", "false").lower() == "true"


def is_twilio_configured() -> bool:
    """Check if valid Twilio credentials and phone number are present."""
    return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER)


def get_twilio_client() -> Optional[Any]:
    """Return an authenticated Twilio REST client if configured, else None."""
    if not (HAS_TWILIO and TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN):
        return None
    try:
        return TwilioClient(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
    except Exception as e:
        print(f"[Twilio] Client initialization failed: {e}")
        return None


def validate_twilio_request(url: str, params: dict, signature: str) -> bool:
    """Validate X-Twilio-Signature against Auth Token."""
    if not TWILIO_VALIDATE_SIGNATURE:
        return True
    if not (HAS_TWILIO and TWILIO_AUTH_TOKEN and signature):
        return False
    try:
        validator = RequestValidator(TWILIO_AUTH_TOKEN)
        return validator.validate(url, params, signature)
    except Exception as e:
        print(f"[Twilio] Signature validation error: {e}")
        return False


# --- Audio Transcoding Utilities ---

def ulaw_to_pcm16k(ulaw_bytes: bytes) -> bytes:
    """Convert 8000Hz 8-bit mu-law audio to 16000Hz 16-bit linear PCM."""
    if not ulaw_bytes:
        return b""
    pcm_8k = audioop.ulaw2lin(ulaw_bytes, 2)
    pcm_16k, _ = audioop.ratecv(pcm_8k, 2, 1, 8000, 16000, None)
    return pcm_16k


def pcm16k_to_wav(pcm_16k: bytes) -> bytes:
    """Package raw 16kHz 16-bit mono PCM into standard WAV byte array."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(pcm_16k)
    return buf.getvalue()


def wav_to_ulaw8k(wav_bytes: bytes) -> bytes:
    """Convert WAV audio bytes to 8000Hz 8-bit mu-law for Twilio streaming."""
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            frames = wf.readframes(wf.getnframes())

        # Convert to mono if stereo
        if n_channels == 2:
            frames = audioop.tomono(frames, sampwidth, 0.5, 0.5)
        # Convert to 16-bit linear PCM if needed
        if sampwidth != 2:
            frames = audioop.lin2lin(frames, sampwidth, 2)
        # Resample to 8000Hz
        if framerate != 8000:
            frames, _ = audioop.ratecv(frames, 2, 1, framerate, 8000, None)

        return audioop.lin2ulaw(frames, 2)
    except Exception as e:
        print(f"[Twilio Audio] Failed to convert WAV to ulaw: {e}")
        return b""


def pcm16k_to_ulaw8k(pcm_16k: bytes) -> bytes:
    """Convert 16kHz 16-bit PCM directly to 8kHz mu-law."""
    if not pcm_16k:
        return b""
    pcm_8k, _ = audioop.ratecv(pcm_16k, 2, 1, 16000, 8000, None)
    return audioop.lin2ulaw(pcm_8k, 2)


# --- Voice Activity Detector (VAD) ---

class TwilioVAD:
    """
    Adaptive energy-based VAD for telephone streams.
    Twilio streams 20ms frames (160 samples ulaw -> 320 samples 16kHz PCM).
    Detects speech onset, tracks silence, and marks turn completion.
    """
    def __init__(
        self,
        energy_threshold: int = 400,
        silence_threshold_ms: int = 650,
        min_speech_ms: int = 280,
    ):
        self.energy_threshold = energy_threshold
        self.silence_threshold_ms = silence_threshold_ms
        self.min_speech_ms = min_speech_ms
        self.is_speaking = False
        self.speech_ms = 0
        self.silence_ms = 0
        self.buffer = bytearray()

    def feed_frame(self, pcm_16k: bytes, frame_ms: int = 20) -> bool:
        """
        Process a 20ms frame of 16kHz PCM.
        Returns True when caller finishes speaking (speech followed by sustained silence).
        """
        rms = audioop.rms(pcm_16k, 2) if len(pcm_16k) >= 2 else 0

        if rms > self.energy_threshold:
            self.is_speaking = True
            self.speech_ms += frame_ms
            self.silence_ms = 0
            self.buffer.extend(pcm_16k)
            return False
        else:
            if self.is_speaking:
                self.silence_ms += frame_ms
                self.buffer.extend(pcm_16k)
                if self.silence_ms >= self.silence_threshold_ms:
                    if self.speech_ms >= self.min_speech_ms:
                        self.is_speaking = False
                        self.speech_ms = 0
                        self.silence_ms = 0
                        return True
                    else:
                        # Reject transient spikes (coughs, line clicks)
                        self.reset()
            return False

    def reset(self):
        self.is_speaking = False
        self.speech_ms = 0
        self.silence_ms = 0
        self.buffer.clear()

    def get_audio_wav(self) -> bytes:
        data = bytes(self.buffer)
        self.buffer.clear()
        return pcm16k_to_wav(data)


# --- Request Models ---

class TwilioDialIn(BaseModel):
    phone_number: str
    greeting: Optional[str] = None


class TwilioRouteIn(BaseModel):
    phone_number: str
    agent_id: int


class TwilioConfigIn(BaseModel):
    account_sid: Optional[str] = None
    auth_token: Optional[str] = None
    phone_number: Optional[str] = None
    webhook_base_url: Optional[str] = None
    validate_signature: Optional[bool] = None


# --- Server Hook References ---
# These functions are injected by server.py on startup to share DB, STT, LLM, and TTS pipelines.
_SERVER_HOOKS = {
    "db": None,
    "require_user": None,
    "owned_agent": None,
    "transcribe_audio_bytes": None,
    "synthesize_speech_bytes": None,
    "llm_chat": None,
    "retrieve_context": None,
    "validate_and_save_booking": None,
    "update_booking_db": None,
    "auto_sync_booking_to_google": None,
    "fire_webhook": None,
    "evaluate_conversational_guardrail": None,
    "booking_payload": None,
    "build_calendar_prompt": None,
    "BOOKING_TOOL": None,
    "UPDATE_BOOKING_TOOL": None,
    "BOOKING_SYSTEM_GUARDRAIL": None,
}


def register_server_hooks(**kwargs):
    """Register server-level helper functions for shared execution."""
    _SERVER_HOOKS.update(kwargs)


def _get_db():
    fn = _SERVER_HOOKS.get("db")
    if fn:
        return fn()
    raise RuntimeError("Database hook not registered")


# --- Route Resolution Helper ---

def resolve_agent_for_call(to_number: str, query_agent_id: Optional[int] = None) -> Optional[dict]:
    """Find the agent assigned to this phone number or fallback to default agent."""
    with _get_db() as conn:
        # 1. Direct agent query param
        if query_agent_id:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (query_agent_id,)).fetchone()
            if row:
                return dict(row)

        clean_to = re.sub(r"[^\d+]", "", to_number or "")

        # 2. Match from twilio_phone_routes table
        route = conn.execute(
            "SELECT agent_id FROM twilio_phone_routes WHERE phone_number = ? LIMIT 1",
            (clean_to,)
        ).fetchone()
        if route:
            row = conn.execute("SELECT * FROM agents WHERE id = ?", (route["agent_id"],)).fetchone()
            if row:
                return dict(row)

        # 3. Match from agents.twilio_phone_number
        row = conn.execute(
            "SELECT * FROM agents WHERE twilio_phone_number = ? LIMIT 1",
            (clean_to,)
        ).fetchone()
        if row:
            return dict(row)

        # 4. Fallback: first agent with twilio_enabled = 1 or simply agent #1
        fallback = conn.execute(
            "SELECT * FROM agents WHERE twilio_enabled = 1 ORDER BY id ASC LIMIT 1"
        ).fetchone() or conn.execute("SELECT * FROM agents ORDER BY id ASC LIMIT 1").fetchone()

        return dict(fallback) if fallback else None


# --- Twilio Voice Webhooks & Endpoints ---

@router.post("/api/twilio/voice")
async def twilio_inbound_voice(request: Request):
    """
    Primary Twilio Voice Webhook.
    Invoked by Twilio when an incoming call lands on a configured phone number.
    Returns TwiML that connects the call to our WebSocket Media Stream.
    """
    form_data = await request.form()
    params = dict(form_data)
    call_sid = params.get("CallSid", f"call_sim_{int(datetime.now().timestamp())}")
    from_number = params.get("From", "unknown")
    to_number = params.get("To", TWILIO_PHONE_NUMBER or "unknown")

    # Optional signature verification
    sig = request.headers.get("X-Twilio-Signature", "")
    full_url = str(request.url)
    if not validate_twilio_request(full_url, params, sig):
        raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    # Resolve agent
    agent_id_param = request.query_params.get("agent_id")
    agent_id = int(agent_id_param) if agent_id_param and agent_id_param.isdigit() else None
    agent = resolve_agent_for_call(to_number, query_agent_id=agent_id)
    resolved_id = agent["id"] if agent else 1

    # Record initial call entry in calls table
    now_str = datetime.now(timezone.utc).isoformat()
    try:
        with _get_db() as conn:
            conn.execute(
                """INSERT INTO calls (agent_id, call_uid, source, twilio_call_sid, caller_phone, started_at, num_turns, transcript, status)
                   VALUES (?, ?, 'twilio', ?, ?, ?, 0, '[]', 'in-progress')""",
                (resolved_id, call_sid, call_sid, from_number, now_str)
            )
    except Exception as e:
        print(f"[Twilio Voice] Failed to record call entry: {e}")

    # Determine public host for WebSocket stream
    host = request.headers.get("host", "localhost:8000")
    base_url = (TWILIO_WEBHOOK_BASE_URL or os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")).strip().rstrip("/") or f"http://{host}"
    ws_host = base_url.replace("https://", "").replace("http://", "")
    ws_protocol = "wss" if base_url.startswith("https") else "ws"
    ws_url = f"{ws_protocol}://{ws_host}/api/twilio/media-stream"

    # Build TwiML response
    if HAS_TWILIO and VoiceResponse:
        vr = VoiceResponse()
        connect = Connect()
        stream = Stream(url=ws_url)
        stream.parameter(name="agent_id", value=str(resolved_id))
        stream.parameter(name="call_sid", value=str(call_sid))
        stream.parameter(name="caller_phone", value=str(from_number))
        connect.append(stream)
        vr.append(connect)
        twiml_xml = str(vr)
    else:
        # Standard fallback XML format
        twiml_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Connect>
        <Stream url="{ws_url}">
            <Parameter name="agent_id" value="{resolved_id}" />
            <Parameter name="call_sid" value="{call_sid}" />
            <Parameter name="caller_phone" value="{from_number}" />
        </Stream>
    </Connect>
</Response>"""

    return Response(content=twiml_xml, media_type="application/xml")


@router.websocket("/api/twilio/media-stream")
async def twilio_media_stream_websocket(websocket: WebSocket):
    """
    Real-time Twilio Media Stream WebSocket.
    Processes bidirectional telephone audio:
    - Caller speech -> mu-law -> 16kHz PCM -> VAD -> STT -> RAG/LLM/Tools -> TTS -> mu-law -> Caller.
    - Handles barge-in by clearing Twilio audio playback queue when caller speaks.
    """
    await websocket.accept()

    stream_sid = None
    call_sid = None
    agent = None
    agent_id = None
    caller_phone = None
    transcript: List[Dict[str, str]] = []
    messages: List[Dict[str, str]] = []

    vad = TwilioVAD(energy_threshold=400, silence_threshold_ms=650, min_speech_ms=280)
    is_agent_speaking = False
    current_playback_task: Optional[asyncio.Task] = None

    async def send_audio_frames(ulaw_audio: bytes):
        """Send mu-law audio to Twilio in 20ms chunks (160 bytes at 8kHz)."""
        nonlocal is_agent_speaking
        is_agent_speaking = True
        try:
            chunk_size = 160
            for i in range(0, len(ulaw_audio), chunk_size):
                if not is_agent_speaking:
                    break
                chunk = ulaw_audio[i:i + chunk_size]
                if len(chunk) < chunk_size:
                    chunk = chunk + b"\xff" * (chunk_size - len(chunk))
                payload = base64.b64encode(chunk).decode("ascii")
                await websocket.send_text(json.dumps({
                    "event": "media",
                    "streamSid": stream_sid,
                    "media": {"payload": payload}
                }))
                await asyncio.sleep(0.019)  # ~20ms pace
        except Exception as err:
            print(f"[Twilio WS] Audio stream error: {err}")
        finally:
            is_agent_speaking = False

    async def interrupt_speech():
        """Send Twilio 'clear' event to immediately silence bot playback."""
        nonlocal is_agent_speaking, current_playback_task
        if is_agent_speaking:
            is_agent_speaking = False
            if current_playback_task and not current_playback_task.done():
                current_playback_task.cancel()
            try:
                await websocket.send_text(json.dumps({
                    "event": "clear",
                    "streamSid": stream_sid
                }))
            except Exception:
                pass

    try:
        while True:
            raw_msg = await websocket.receive_text()
            data = json.loads(raw_msg)
            event = data.get("event")

            if event == "start":
                stream_sid = data.get("start", {}).get("streamSid")
                call_sid = data.get("start", {}).get("callSid")
                custom_params = data.get("start", {}).get("customParameters", {})
                agent_id_str = custom_params.get("agent_id")
                caller_phone = custom_params.get("caller_phone", "unknown")

                if agent_id_str and agent_id_str.isdigit():
                    agent_id = int(agent_id_str)
                    agent = resolve_agent_for_call("", query_agent_id=agent_id)
                else:
                    agent = resolve_agent_for_call("")
                    agent_id = agent["id"] if agent else 1

                print(f"[Twilio WS] Stream started: streamSid={stream_sid}, callSid={call_sid}, agent_id={agent_id}")

                # Deliver greeting if configured
                greeting = (agent.get("greeting") or "").strip() if agent else ""
                if greeting:
                    transcript.append({"role": "assistant", "content": greeting, "time": datetime.now(timezone.utc).isoformat()})
                    messages.append({"role": "assistant", "content": greeting})
                    synth_fn = _SERVER_HOOKS.get("synthesize_speech_bytes")
                    if synth_fn:
                        voice = agent.get("voice_name") or "zira"
                        rate = float(agent.get("rate") or 1.0)
                        wav_bytes = await synth_fn(greeting, voice=voice, rate=rate)
                        if wav_bytes:
                            ulaw_data = wav_to_ulaw8k(wav_bytes)
                            current_playback_task = asyncio.create_task(send_audio_frames(ulaw_data))

            elif event == "media":
                media_info = data.get("media", {})
                payload_b64 = media_info.get("payload", "")
                if not payload_b64:
                    continue

                ulaw_chunk = base64.b64decode(payload_b64)
                pcm_16k = ulaw_to_pcm16k(ulaw_chunk)

                # Check for caller barge-in during bot playback
                if is_agent_speaking:
                    rms = audioop.rms(pcm_16k, 2) if len(pcm_16k) >= 2 else 0
                    if rms > 500:  # Confident barge-in threshold
                        await interrupt_speech()

                # Process VAD
                utterance_done = vad.feed_frame(pcm_16k, frame_ms=20)
                if utterance_done:
                    wav_audio = vad.get_audio_wav()
                    stt_fn = _SERVER_HOOKS.get("transcribe_audio_bytes")
                    user_text = ""
                    if stt_fn:
                        user_text = await stt_fn(wav_audio, language=agent.get("lang", "en-US") if agent else "en")

                    user_text = (user_text or "").strip()
                    if not user_text:
                        continue

                    print(f"[Twilio PSTN Turn] Caller: '{user_text}'")
                    now_turn = datetime.now(timezone.utc).isoformat()
                    transcript.append({"role": "user", "content": user_text, "time": now_turn})
                    messages.append({"role": "user", "content": user_text})

                    # Conversational Guardrail check
                    guardrail_fn = _SERVER_HOOKS.get("evaluate_conversational_guardrail")
                    blocked = False
                    reply_text = ""
                    if guardrail_fn:
                        blocked, safe_msg = guardrail_fn(user_text)
                        if blocked:
                            reply_text = safe_msg

                    # RAG Knowledge Context
                    if not blocked and agent and agent.get("use_knowledge"):
                        retriever_fn = _SERVER_HOOKS.get("retrieve_context")
                        if retriever_fn:
                            ctx_chunks = retriever_fn(agent["id"], user_text)
                            if ctx_chunks:
                                kb_prompt = (
                                    "\n\n# VERIFIED KNOWLEDGE BASE:\n"
                                    + "\n---\n".join(ctx_chunks)
                                    + "\n--- END ---\n"
                                )
                            else:
                                kb_prompt = ""
                        else:
                            kb_prompt = ""
                    else:
                        kb_prompt = ""

                    # LLM Generation with Tools
                    if not reply_text:
                        sys_prompt = (agent.get("system_prompt") or "").strip() if agent else ""
                        if not sys_prompt:
                            sys_prompt = "You are a warm, concise phone receptionist. Answer in 1-2 spoken sentences."
                        sys_prompt += kb_prompt

                        cal_prompt_fn = _SERVER_HOOKS.get("build_calendar_prompt")
                        if cal_prompt_fn:
                            sys_prompt += cal_prompt_fn()

                        tools_enabled = bool(agent and agent.get("tools_enabled"))
                        if tools_enabled and _SERVER_HOOKS.get("BOOKING_SYSTEM_GUARDRAIL"):
                            sys_prompt += _SERVER_HOOKS.get("BOOKING_SYSTEM_GUARDRAIL")

                        tools = None
                        if tools_enabled:
                            b_tool = _SERVER_HOOKS.get("BOOKING_TOOL")
                            u_tool = _SERVER_HOOKS.get("UPDATE_BOOKING_TOOL")
                            if b_tool and u_tool:
                                tools = [b_tool, u_tool]

                        convo = [{"role": "system", "content": sys_prompt}] + messages
                        llm_fn = _SERVER_HOOKS.get("llm_chat")

                        if llm_fn:
                            llm_resp = await llm_fn(convo, tools=tools)
                            msg = llm_resp.get("choices", [{}])[0].get("message", {})

                            if msg.get("tool_calls"):
                                convo.append(msg)
                                for tc in msg["tool_calls"]:
                                    fname = tc.get("function", {}).get("name")
                                    try:
                                        t_args = json.loads(tc.get("function", {}).get("arguments") or "{}")
                                    except Exception:
                                        t_args = {}

                                    if fname == "save_booking":
                                        save_fn = _SERVER_HOOKS.get("validate_and_save_booking")
                                        if save_fn:
                                            # Provide caller phone number if not present in tool args
                                            if not t_args.get("phone") and caller_phone and caller_phone != "unknown":
                                                t_args["phone"] = caller_phone
                                            is_valid, booking, err_msg = save_fn(agent_id, call_sid, t_args, agent, messages=messages)
                                            if is_valid and booking:
                                                convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking saved successfully."})
                                                # Background Google & Webhook sync
                                                hook_url = (agent.get("booking_webhook") or "").strip()
                                                if hook_url and _SERVER_HOOKS.get("fire_webhook"):
                                                    p_fn = _SERVER_HOOKS.get("booking_payload")
                                                    asyncio.create_task(_SERVER_HOOKS["fire_webhook"](hook_url, p_fn(agent, booking) if p_fn else booking))
                                                if _SERVER_HOOKS.get("auto_sync_booking_to_google"):
                                                    asyncio.create_task(_SERVER_HOOKS["auto_sync_booking_to_google"](agent, booking))
                                            else:
                                                convo.append({"role": "tool", "tool_call_id": tc["id"], "content": f"Booking NOT saved: {err_msg}"})
                                    elif fname == "update_booking":
                                        upd_fn = _SERVER_HOOKS.get("update_booking_db")
                                        if upd_fn:
                                            booking = upd_fn(agent_id, call_sid, t_args)
                                            convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Booking updated successfully."})
                                    else:
                                        convo.append({"role": "tool", "tool_call_id": tc["id"], "content": "Done."})

                                # Generate response after tool execution
                                llm_resp2 = await llm_fn(convo, tools=None)
                                reply_text = (llm_resp2.get("choices", [{}])[0].get("message", {}).get("content") or "").strip()
                            else:
                                reply_text = (msg.get("content") or "").strip()

                    if not reply_text:
                        reply_text = "I'm with you. How else can I help?"

                    # Clean markdown symbols for natural speech
                    reply_text = re.sub(r"[#*`_~]", "", reply_text).strip()
                    transcript.append({"role": "assistant", "content": reply_text, "time": datetime.now(timezone.utc).isoformat()})
                    messages.append({"role": "assistant", "content": reply_text})

                    # Synthesize and stream audio back to caller
                    synth_fn = _SERVER_HOOKS.get("synthesize_speech_bytes")
                    if synth_fn:
                        voice = agent.get("voice_name") or "zira"
                        rate = float(agent.get("rate") or 1.0)
                        wav_bytes = await synth_fn(reply_text, voice=voice, rate=rate)
                        if wav_bytes:
                            ulaw_data = wav_to_ulaw8k(wav_bytes)
                            current_playback_task = asyncio.create_task(send_audio_frames(ulaw_data))

            elif event == "stop":
                print(f"[Twilio WS] Call stopped: callSid={call_sid}")
                break

    except WebSocketDisconnect:
        print(f"[Twilio WS] Client disconnected: callSid={call_sid}")
    except Exception as e:
        print(f"[Twilio WS] Unexpected stream error: {e}")
    finally:
        # Finalize and persist call record
        if call_sid and agent_id:
            now_end = datetime.now(timezone.utc).isoformat()
            try:
                with _get_db() as conn:
                    # Calculate duration if started_at exists
                    row = conn.execute("SELECT started_at FROM calls WHERE twilio_call_sid = ?", (call_sid,)).fetchone()
                    duration = 0
                    if row and row["started_at"]:
                        try:
                            start_dt = datetime.fromisoformat(row["started_at"])
                            duration = max(0, int((datetime.now(timezone.utc) - start_dt).total_seconds()))
                        except Exception:
                            duration = 0

                    conn.execute(
                        """UPDATE calls SET ended_at = ?, duration_seconds = ?, num_turns = ?, transcript = ?, status = 'completed'
                           WHERE twilio_call_sid = ?""",
                        (now_end, duration, len(transcript), json.dumps(transcript), call_sid)
                    )
            except Exception as e:
                print(f"[Twilio WS] Failed to update call transcript: {e}")


# --- Outbound Call Endpoint ---

@router.post("/api/agents/{agent_id}/twilio/dial")
async def dial_outbound_call(agent_id: int, body: TwilioDialIn, request: Request):
    """
    Initiate an outbound phone call from the agent to a destination phone number.
    Uses Twilio REST API calls.create.
    """
    require_user_fn = _SERVER_HOOKS.get("require_user")
    owned_agent_fn = _SERVER_HOOKS.get("owned_agent")
    user = require_user_fn(request.cookies.get("session")) if require_user_fn else {"id": 1}

    with _get_db() as conn:
        agent = dict(owned_agent_fn(conn, agent_id, user, required_perm="can_call")) if owned_agent_fn else {}

    client = get_twilio_client()
    from_number = agent.get("twilio_phone_number") or TWILIO_PHONE_NUMBER

    host = request.headers.get("host", "localhost:8000")
    base_url = (TWILIO_WEBHOOK_BASE_URL or os.environ.get("TWILIO_WEBHOOK_BASE_URL", "")).strip().rstrip("/") or f"http://{host}"
    webhook_url = f"{base_url}/api/twilio/voice?agent_id={agent_id}"
    status_callback_url = f"{base_url}/api/twilio/call-status"

    if client and from_number:
        if "localhost" in base_url or "127.0.0.1" in base_url:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Invalid webhook URL '{webhook_url}': Twilio cloud cannot call localhost. "
                    "Configure TWILIO_WEBHOOK_BASE_URL in .env with your public HTTPS ngrok URL (e.g. https://xxxx.ngrok-free.app) and restart server."
                )
            )
        try:
            call = client.calls.create(
                to=body.phone_number,
                from_=from_number,
                url=webhook_url,
                status_callback=status_callback_url,
                status_callback_event=["initiated", "ringing", "answered", "completed"],
            )
            return {
                "success": True,
                "call_sid": call.sid,
                "status": call.status,
                "to": body.phone_number,
                "from": from_number,
                "mode": "live_twilio"
            }
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"Twilio call dispatch failed: {e}")
    else:
        # Local Sandbox simulation mode when credentials not configured
        sim_sid = f"CA_sim_{int(datetime.now().timestamp())}_{agent_id}"
        now_str = datetime.now(timezone.utc).isoformat()
        with _get_db() as conn:
            conn.execute(
                """INSERT INTO calls (agent_id, call_uid, source, twilio_call_sid, caller_phone, started_at, num_turns, transcript, status)
                   VALUES (?, ?, 'twilio', ?, ?, ?, 0, '[]', 'simulated_queued')""",
                (agent_id, sim_sid, sim_sid, body.phone_number, now_str)
            )
        return {
            "success": True,
            "call_sid": sim_sid,
            "status": "queued",
            "to": body.phone_number,
            "from": from_number or "+15550009999",
            "mode": "sandbox_simulated",
            "note": "Twilio live credentials not configured. Created simulated outbound test call."
        }


# --- Call Lifecycle Status Webhook ---

@router.post("/api/twilio/call-status")
async def twilio_call_status_callback(request: Request):
    """
    Twilio Call Status Callback Webhook.
    Handles events: initiated, ringing, answered, completed, busy, failed, no-answer.
    """
    form_data = await request.form()
    params = dict(form_data)
    call_sid = params.get("CallSid")
    call_status = params.get("CallStatus", "completed")
    call_duration = int(params.get("CallDuration", 0))

    if call_sid:
        with _get_db() as conn:
            conn.execute(
                """UPDATE calls SET status = ?, duration_seconds = COALESCE(NULLIF(?, 0), duration_seconds)
                   WHERE twilio_call_sid = ?""",
                (call_status, call_duration, call_sid)
            )
    return Response(content="<Response></Response>", media_type="application/xml")


# --- Twilio Configuration & Route Endpoints ---

@router.get("/api/twilio/config")
def get_twilio_status(request: Request):
    """Get active Twilio integration status."""
    require_user_fn = _SERVER_HOOKS.get("require_user")
    if require_user_fn:
        require_user_fn(request.cookies.get("session"))

    return {
        "configured": is_twilio_configured(),
        "has_credentials": bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN),
        "phone_number": TWILIO_PHONE_NUMBER,
        "webhook_base_url": TWILIO_WEBHOOK_BASE_URL,
        "validate_signature": TWILIO_VALIDATE_SIGNATURE,
    }


@router.post("/api/twilio/config")
def update_twilio_config(body: TwilioConfigIn, request: Request):
    """Dynamically update Twilio settings (runtime memory)."""
    global TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, TWILIO_WEBHOOK_BASE_URL, TWILIO_VALIDATE_SIGNATURE

    require_user_fn = _SERVER_HOOKS.get("require_user")
    if require_user_fn:
        require_user_fn(request.cookies.get("session"))

    if body.account_sid is not None:
        TWILIO_ACCOUNT_SID = body.account_sid.strip()
    if body.auth_token is not None:
        TWILIO_AUTH_TOKEN = body.auth_token.strip()
    if body.phone_number is not None:
        TWILIO_PHONE_NUMBER = body.phone_number.strip()
    if body.webhook_base_url is not None:
        TWILIO_WEBHOOK_BASE_URL = body.webhook_base_url.strip().rstrip("/")
    if body.validate_signature is not None:
        TWILIO_VALIDATE_SIGNATURE = bool(body.validate_signature)

    return {
        "success": True,
        "configured": is_twilio_configured(),
        "phone_number": TWILIO_PHONE_NUMBER,
        "webhook_base_url": TWILIO_WEBHOOK_BASE_URL,
    }


@router.get("/api/twilio/routes")
def list_phone_routes(request: Request):
    """List phone number to agent routing mappings."""
    require_user_fn = _SERVER_HOOKS.get("require_user")
    if require_user_fn:
        require_user_fn(request.cookies.get("session"))

    with _get_db() as conn:
        rows = conn.execute("""
            SELECT r.id, r.phone_number, r.agent_id, r.created_at, a.name as agent_name
            FROM twilio_phone_routes r
            JOIN agents a ON a.id = r.agent_id
            ORDER BY r.id DESC
        """).fetchall()
    return [dict(r) for r in rows]


@router.post("/api/twilio/routes")
def add_phone_route(body: TwilioRouteIn, request: Request):
    """Map a phone number to an agent."""
    require_user_fn = _SERVER_HOOKS.get("require_user")
    if require_user_fn:
        require_user_fn(request.cookies.get("session"))

    clean_phone = re.sub(r"[^\d+]", "", body.phone_number.strip())
    if not clean_phone:
        raise HTTPException(status_code=400, detail="Invalid phone number format.")

    now_str = datetime.now(timezone.utc).isoformat()
    with _get_db() as conn:
        conflict = conn.execute(
            "SELECT a.id, a.name FROM twilio_phone_routes r JOIN agents a ON a.id = r.agent_id WHERE r.phone_number = ? AND r.agent_id != ?",
            (clean_phone, body.agent_id)
        ).fetchone()
        if not conflict:
            conflict = conn.execute(
                "SELECT id, name FROM agents WHERE twilio_phone_number = ? AND id != ?",
                (clean_phone, body.agent_id)
            ).fetchone()
        if conflict:
            raise HTTPException(
                status_code=400,
                detail=f"Phone number '{clean_phone}' is already assigned to agent '{conflict['name']}' (ID #{conflict['id']}). Each agent must have a unique contact number."
            )

        # Clear existing route for this agent to keep strict 1-to-1 mapping
        conn.execute("DELETE FROM twilio_phone_routes WHERE agent_id = ?", (body.agent_id,))
        conn.execute(
            """INSERT INTO twilio_phone_routes (phone_number, agent_id, created_at)
               VALUES (?, ?, ?)
               ON CONFLICT(phone_number) DO UPDATE SET agent_id = excluded.agent_id""",
            (clean_phone, body.agent_id, now_str)
        )
        conn.execute(
            "UPDATE agents SET twilio_phone_number = ?, twilio_enabled = 1 WHERE id = ?",
            (clean_phone, body.agent_id)
        )
    return {"success": True, "phone_number": clean_phone, "agent_id": body.agent_id}


@router.delete("/api/twilio/routes/{route_id}")
def delete_phone_route(route_id: int, request: Request):
    """Delete a phone route mapping."""
    require_user_fn = _SERVER_HOOKS.get("require_user")
    if require_user_fn:
        require_user_fn(request.cookies.get("session"))

    with _get_db() as conn:
        route = conn.execute("SELECT agent_id, phone_number FROM twilio_phone_routes WHERE id = ?", (route_id,)).fetchone()
        if route:
            conn.execute(
                "UPDATE agents SET twilio_phone_number = '', twilio_enabled = 0 WHERE id = ? AND twilio_phone_number = ?",
                (route["agent_id"], route["phone_number"])
            )
        conn.execute("DELETE FROM twilio_phone_routes WHERE id = ?", (route_id,))
    return {"success": True}
