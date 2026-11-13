"""
Unit and Integration Test Suite for Twilio Voice Integration in Voice Agent Studio.
Verifies:
1. Audio Transcoding (mu-law 8kHz <-> PCM 16kHz <-> WAV)
2. Voice Activity Detection (TwilioVAD speech detection, hysteresis, silence threshold)
3. TwiML Generation & Inbound Call Routing
4. Phone Route Management & Agent Resolution
5. Outbound Call Dispatching (Sandbox simulation mode)
6. Call Status Callback & Transcript Persistence
7. Request Signature Validation
"""

import os
import sys
import json
import base64
import audioop
import sqlite3
from pathlib import Path
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

# Ensure root dir is in sys.path
ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

import server
import twilio_integration
from twilio_integration import (
    ulaw_to_pcm16k,
    pcm16k_to_wav,
    wav_to_ulaw8k,
    pcm16k_to_ulaw8k,
    TwilioVAD,
    resolve_agent_for_call,
    validate_twilio_request,
)


@pytest.fixture(scope="module")
def client():
    server.init_db()
    with TestClient(server.app) as c:
        yield c


def test_audio_transcoding_ulaw_to_pcm():
    """Test 8kHz mu-law audio conversion to 16kHz 16-bit linear PCM."""
    # 160 bytes of mu-law (20ms at 8000Hz)
    ulaw_chunk = b"\xff" * 160
    pcm_16k = ulaw_to_pcm16k(ulaw_chunk)

    assert isinstance(pcm_16k, bytes)
    # At 16kHz 16-bit mono, 20ms = ~320 samples = ~640 bytes (ratecv edge rounding +/- 1 sample)
    assert abs(len(pcm_16k) - 640) <= 4


def test_audio_transcoding_pcm_to_wav():
    """Test packaging 16kHz PCM into a valid WAV file byte array."""
    pcm_data = b"\x00\x00" * 320  # 320 samples = 640 bytes
    wav_bytes = pcm16k_to_wav(pcm_data)

    assert wav_bytes.startswith(b"RIFF")
    assert b"WAVE" in wav_bytes
    assert len(wav_bytes) > len(pcm_data)


def test_audio_transcoding_wav_to_ulaw8k():
    """Test converting standard WAV bytes into 8kHz mu-law for Twilio streaming."""
    # Generate test 16kHz sine-like signal
    pcm_data = b"\x10\x20" * 1600  # 100ms at 16kHz
    wav_bytes = pcm16k_to_wav(pcm_data)

    ulaw_data = wav_to_ulaw8k(wav_bytes)
    assert isinstance(ulaw_data, bytes)
    # 100ms at 8kHz mu-law = 800 bytes
    assert len(ulaw_data) == 800


def test_audio_transcoding_pcm16k_to_ulaw8k():
    """Test direct conversion from 16kHz PCM to 8kHz mu-law."""
    pcm_16k = b"\x05\x05" * 320  # 20ms at 16kHz
    ulaw_data = pcm16k_to_ulaw8k(pcm_16k)

    assert len(ulaw_data) == 160


def test_twilio_vad_speech_and_silence():
    """Test Twilio VAD detecting voice onset, accumulating frames, and triggering end-of-utterance."""
    vad = TwilioVAD(energy_threshold=300, silence_threshold_ms=100, min_speech_ms=60)

    # 1. Silence frames (RMS near 0) -> no utterance triggered
    silence_frame = b"\x00\x00" * 320
    assert vad.feed_frame(silence_frame, frame_ms=20) is False
    assert vad.is_speaking is False

    # 2. Loud speech frames (high amplitude) -> speech detected
    speech_frame = b"\x50\x20" * 320  # high energy
    for _ in range(4):  # 80ms speech (>= min_speech_ms of 60ms)
        done = vad.feed_frame(speech_frame, frame_ms=20)
        assert done is False
    assert vad.is_speaking is True

    # 3. Trailing silence -> should mark utterance complete when silence exceeds 100ms
    # 5 frames of 20ms = 100ms silence
    completed = False
    for _ in range(5):
        if vad.feed_frame(silence_frame, frame_ms=20):
            completed = True
            break

    assert completed is True
    # Verify WAV extraction
    wav_audio = vad.get_audio_wav()
    assert wav_audio.startswith(b"RIFF")
    # Buffer should be reset
    assert len(vad.buffer) == 0


def test_twilio_vad_reject_click_noise():
    """Transient click shorter than min_speech_ms should be rejected."""
    vad = TwilioVAD(energy_threshold=300, silence_threshold_ms=60, min_speech_ms=100)

    # 1 frame (20ms) of click noise
    click_frame = b"\x50\x20" * 320
    vad.feed_frame(click_frame, frame_ms=20)

    # Then silence
    silence_frame = b"\x00\x00" * 320
    for _ in range(4):  # 80ms silence
        vad.feed_frame(silence_frame, frame_ms=20)

    # Should reset without triggering completion
    assert vad.is_speaking is False
    assert len(vad.buffer) == 0


def test_inbound_voice_webhook_twiml(client):
    """Test POST /api/twilio/voice returns valid TwiML pointing to WebSocket media stream."""
    response = client.post(
        "/api/twilio/voice?agent_id=1",
        data={
            "CallSid": "CA_test_unit_123",
            "From": "+14155551234",
            "To": "+18005559999",
            "CallStatus": "ringing",
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    xml = response.text
    assert "<Response>" in xml
    assert "<Connect>" in xml
    assert "<Stream" in xml
    assert "/api/twilio/media-stream" in xml
    assert "agent_id" in xml
    assert "CA_test_unit_123" in xml

    # Verify call was recorded in database
    with server.db() as conn:
        call = conn.execute("SELECT * FROM calls WHERE twilio_call_sid = ?", ("CA_test_unit_123",)).fetchone()
        assert call is not None
        assert call["source"] == "twilio"
        assert call["caller_phone"] == "+14155551234"


def test_phone_routing_resolution():
    """Verify phone routing resolves via custom route table, agent phone, and query param."""
    unique_suffix = f"{int(datetime.now().timestamp()) % 1000000:06d}"
    agent_phone = f"+155599{unique_suffix}"
    route_phone = f"+155544{unique_suffix}"
    with server.db() as conn:
        # Create test agent
        cur = conn.execute(
            """INSERT INTO agents (name, system_prompt, greeting, twilio_phone_number, created_at, updated_at)
               VALUES ('Phone Receptionist', 'Test prompt', 'Hello phone caller', ?, datetime('now'), datetime('now'))""",
            (agent_phone,)
        )
        agent_id = cur.lastrowid

        # Insert dedicated phone route
        conn.execute(
            """INSERT OR REPLACE INTO twilio_phone_routes (phone_number, agent_id, created_at)
               VALUES (?, ?, datetime('now'))""",
            (route_phone, agent_id)
        )

    # 1. Resolve via explicit query parameter
    a1 = resolve_agent_for_call("+19999999999", query_agent_id=agent_id)
    assert a1 is not None
    assert a1["id"] == agent_id

    # 2. Resolve via twilio_phone_routes table mapping
    a2 = resolve_agent_for_call(route_phone)
    assert a2 is not None
    assert a2["id"] == agent_id

    # 3. Resolve via agents.twilio_phone_number
    a3 = resolve_agent_for_call(agent_phone)
    assert a3 is not None
    assert a3["id"] == agent_id


def test_twilio_config_and_routes_endpoints(client):
    """Test configuration status and route CRUD endpoints."""
    # Register and login test user
    email = f"twilio_tester_{int(datetime.now().timestamp())}@test.com"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    client.post("/api/auth/login", json={"email": email, "password": "password123"})

    # 1. Get Twilio config status
    cfg_resp = client.get("/api/twilio/config")
    assert cfg_resp.status_code == 200
    cfg = cfg_resp.json()
    assert "configured" in cfg
    assert "has_credentials" in cfg

    # 2. Add phone route
    add_resp = client.post(
        "/api/twilio/routes",
        json={"phone_number": "+15558881234", "agent_id": 1}
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["success"] is True

    # 3. List phone routes
    list_resp = client.get("/api/twilio/routes")
    assert list_resp.status_code == 200
    routes = list_resp.json()
    matching = [r for r in routes if r["phone_number"] == "+15558881234"]
    assert len(matching) >= 1
    route_id = matching[0]["id"]

    # 4. Delete phone route
    del_resp = client.delete(f"/api/twilio/routes/{route_id}")
    assert del_resp.status_code == 200
    assert del_resp.json()["success"] is True


def test_outbound_dial_sandbox_mode(client):
    """Test outbound call initiation falls back gracefully to sandbox simulation when live credentials absent."""
    # Ensure authenticated
    email = f"dial_tester_{int(datetime.now().timestamp())}@test.com"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    client.post("/api/auth/login", json={"email": email, "password": "password123"})

    # Create agent
    ag_resp = client.post("/api/agents", json={"name": "Outbound Dial Agent"})
    agent_id = ag_resp.json()["id"]

    # Trigger outbound call
    dial_resp = client.post(
        f"/api/agents/{agent_id}/twilio/dial",
        json={"phone_number": "+14155557777"}
    )
    assert dial_resp.status_code == 200
    data = dial_resp.json()
    assert data["success"] is True
    assert "call_sid" in data
    assert data["to"] == "+14155557777"
    assert data["mode"] in ("sandbox_simulated", "live_twilio")


def test_call_status_callback(client):
    """Test POST /api/twilio/call-status updates call status and duration in database."""
    test_sid = "CA_status_callback_999"
    with server.db() as conn:
        conn.execute(
            """INSERT INTO calls (agent_id, call_uid, source, twilio_call_sid, caller_phone, started_at, status)
               VALUES (1, ?, 'twilio', ?, '+14155550000', datetime('now'), 'ringing')""",
            (test_sid, test_sid)
        )

    response = client.post(
        "/api/twilio/call-status",
        data={
            "CallSid": test_sid,
            "CallStatus": "completed",
            "CallDuration": "45",
        }
    )
    assert response.status_code == 200

    with server.db() as conn:
        row = conn.execute("SELECT status, duration_seconds FROM calls WHERE twilio_call_sid = ?", (test_sid,)).fetchone()
        assert row is not None
        assert row["status"] == "completed"
        assert row["duration_seconds"] == 45


def test_twilio_signature_validator():
    """Verify request validator behavior."""
    # When signature validation is turned off (default for dev/local), returns True
    assert validate_twilio_request("https://example.com/api/twilio/voice", {}, "") is True


def test_unique_phone_number_enforcement(client):
    """Verify no two agents can claim or share the same phone number."""
    ts = int(datetime.now().timestamp())
    email = f"phone_conflict_{ts}@test.com"
    client.post("/api/auth/register", json={"email": email, "password": "password123"})
    client.post("/api/auth/login", json={"email": email, "password": "password123"})

    test_phone = f"+1555{ts % 10000000:07d}"
    test_phone_b = f"+1556{ts % 10000000:07d}"

    # 1. Create Agent A with phone number
    res_a = client.post("/api/agents", json={
        "name": "Agent A",
        "twilio_phone_number": test_phone,
        "twilio_enabled": True
    })
    assert res_a.status_code == 200
    agent_a_id = res_a.json()["id"]

    # 2. Creating Agent B with the same phone number must fail with 400
    res_b = client.post("/api/agents", json={
        "name": "Agent B",
        "twilio_phone_number": test_phone,
        "twilio_enabled": True
    })
    assert res_b.status_code == 400
    assert "already assigned" in res_b.json()["detail"]

    # 3. Create Agent B with a different phone number
    res_b_ok = client.post("/api/agents", json={
        "name": "Agent B",
        "twilio_phone_number": test_phone_b,
        "twilio_enabled": True
    })
    assert res_b_ok.status_code == 200
    agent_b_id = res_b_ok.json()["id"]

    # 4. Updating Agent B to use Agent A's phone number must fail with 400
    res_update_conflict = client.put(f"/api/agents/{agent_b_id}", json={
        "name": "Agent B",
        "twilio_phone_number": test_phone,
        "twilio_enabled": True
    })
    assert res_update_conflict.status_code == 400
    assert "already assigned" in res_update_conflict.json()["detail"]

    # 5. Mapping route via /api/twilio/routes for Agent B with Agent A's phone must fail with 400
    res_route_conflict = client.post("/api/twilio/routes", json={
        "phone_number": test_phone,
        "agent_id": agent_b_id
    })
    assert res_route_conflict.status_code == 400
    assert "already assigned" in res_route_conflict.json()["detail"]

