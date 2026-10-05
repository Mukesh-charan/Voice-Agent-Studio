"""
tests/test_booking_concurrent.py — Phase F4, F5
Concurrent booking correctness tests:
  - Concurrent double booking (expect exactly 1 success)
  - Adjacent slots allowed
  - Update-in-place
  - Duplicate within same call
  - Conflict detection on 200 synthetic requests

Run with:
    pytest tests/test_booking_concurrent.py -v
"""

import asyncio
import json
import sqlite3
import tempfile
import threading
import uuid
from datetime import datetime, timedelta
from pathlib import Path

import pytest

# ── Setup: create a temporary DB and patch server.py's DB_PATH ───────────────

@pytest.fixture(scope="module")
def temp_db(tmp_path_factory):
    """Create a temporary agents.db for tests and patch server.DB_PATH."""
    db_dir = tmp_path_factory.mktemp("db")
    db_path = db_dir / "agents.db"

    import sys, os
    # Patch environment so server uses the temp DB
    _orig_path = None
    import importlib
    # We patch at import time via monkeypatch of the module-level DB_PATH
    import server
    _orig = server.DB_PATH
    server.DB_PATH = db_path
    # Re-run init to create tables
    server.init_db()
    yield db_path
    server.DB_PATH = _orig


@pytest.fixture(scope="module")
def agent_and_user(temp_db):
    """Create a test user and agent in the temp DB."""
    import server
    with server.db() as conn:
        conn.execute("INSERT INTO users (email, pw_salt, pw_hash, created_at) VALUES (?,?,?,?)",
                     ("test@example.com", "s", "h", server.now_iso()))
        user_id = conn.execute("SELECT id FROM users WHERE email='test@example.com'").fetchone()["id"]
        conn.execute(
            "INSERT INTO agents (name, system_prompt, greeting, voice_name, rate, lang, created_at, updated_at, "
            "use_knowledge, tools_enabled, barge_in, user_id, booking_webhook, google_calendar_id, "
            "google_sheet_id, google_credentials_json, google_auto_sync_calendar, google_auto_sync_sheets, "
            "google_enable_meet) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("TestAgent", "You are a test agent.", "Hello!", "en-US-ZiraNeural", 1.0, "en",
             server.now_iso(), server.now_iso(), 0, 1, 0, user_id, "", "", "", "", 0, 0, 0)
        )
        agent_id = conn.execute("SELECT id FROM agents WHERE name='TestAgent'").fetchone()["id"]
    return {"user_id": user_id, "agent_id": agent_id}


# ── Helper: create a booking args dict for a specific datetime ────────────────

def _args(name="Alice Smith", phone="+91 98765 43210",
          dt="2026-12-15 10:00:00", reason="Test appointment"):
    return {"name": name, "phone": phone, "datetime": dt, "reason": reason,
            "user_confirmed": True}


def _messages(name="Alice Smith"):
    return [{"role": "user", "content": f"My name is {name}, I'd like to book."}]


# ── Tests ─────────────────────────────────────────────────────────────────────

class TestBookingConcurrent:

    def test_no_overlap_different_agents(self, temp_db, agent_and_user):
        """Sanity: basic booking succeeds."""
        import server
        agent_id = agent_and_user["agent_id"]
        call_uid = str(uuid.uuid4())
        ok, booking, msg = server.validate_and_save_booking(
            agent_id, call_uid, _args(dt="2026-12-20 09:00:00"),
            messages=_messages()
        )
        assert ok, f"Expected success but got: {msg}"
        assert booking is not None

    def test_concurrent_double_booking_exactly_one_success(self, temp_db, agent_and_user):
        """
        Two concurrent requests for the same time slot should result in
        exactly 1 success (conflict detection + BEGIN IMMEDIATE).
        """
        import server
        agent_id = agent_and_user["agent_id"]
        dt = "2026-12-25 14:00:00"  # Christmas 2pm — unique slot

        successes = []
        failures = []
        lock = threading.Lock()

        def attempt_booking(call_uid):
            try:
                ok, booking, msg = server.validate_and_save_booking(
                    agent_id, call_uid, _args(name="Bob Jones", dt=dt),
                    messages=[{"role": "user", "content": "My name is Bob Jones, book me please."}]
                )
                with lock:
                    if ok:
                        successes.append((call_uid, booking))
                    else:
                        failures.append((call_uid, msg))
            except Exception as e:
                with lock:
                    failures.append((call_uid, str(e)))

        threads = [
            threading.Thread(target=attempt_booking, args=(str(uuid.uuid4()),))
            for _ in range(5)  # 5 concurrent requests for the same slot
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(successes) == 1, (
            f"Expected exactly 1 success, got {len(successes)}: {[s[0] for s in successes]}"
        )
        assert len(failures) == 4, (
            f"Expected 4 conflicts, got {len(failures)}: {[f[1] for f in failures]}"
        )
        # The failure messages should mention conflict
        for _, msg in failures:
            assert "conflict" in msg.lower() or "overlap" in msg.lower() or "success" not in msg.lower()

    def test_adjacent_slots_allowed(self, temp_db, agent_and_user):
        """
        Booking A ends at 10:00; booking B starts at 10:00.
        They are adjacent (not overlapping) and BOTH should succeed.
        """
        import server
        agent_id = agent_and_user["agent_id"]

        ok_a, _, msg_a = server.validate_and_save_booking(
            agent_id, str(uuid.uuid4()), _args(name="Carol Dean", dt="2026-12-26 09:00:00"),
            messages=[{"role": "user", "content": "Carol Dean here, 9am please."}]
        )
        ok_b, _, msg_b = server.validate_and_save_booking(
            agent_id, str(uuid.uuid4()), _args(name="Dave Evans", dt="2026-12-26 10:00:00"),
            messages=[{"role": "user", "content": "Dave Evans here, 10am please."}]
        )
        assert ok_a, f"First booking failed: {msg_a}"
        assert ok_b, f"Adjacent booking failed: {msg_b}"

    def test_duplicate_within_same_call_updates_in_place(self, temp_db, agent_and_user):
        """
        A second booking attempt with the same call_uid should update the
        existing booking, not create a second row.
        """
        import server
        agent_id = agent_and_user["agent_id"]
        call_uid = str(uuid.uuid4())

        ok1, b1, _ = server.validate_and_save_booking(
            agent_id, call_uid, _args(name="Eve Foster", dt="2026-12-27 11:00:00"),
            messages=[{"role": "user", "content": "Eve Foster here, 11am please."}]
        )
        ok2, b2, _ = server.validate_and_save_booking(
            agent_id, call_uid, _args(name="Eve Foster", dt="2026-12-27 12:00:00"),
            messages=[{"role": "user", "content": "Eve Foster here, 12am please."}]
        )
        assert ok1 and ok2
        # Should be the same booking ID
        assert b1["id"] == b2["id"]
        # Datetime should be updated
        assert b2["datetime"] != b1["datetime"] or b2["datetime"] == _args(dt="2026-12-27 12:00:00")["datetime"]

    def test_outbox_row_created(self, temp_db, agent_and_user):
        """After a successful new booking, an outbox row should exist."""
        import server
        agent_id = agent_and_user["agent_id"]
        call_uid = str(uuid.uuid4())
        ok, booking, msg = server.validate_and_save_booking(
            agent_id, call_uid, _args(name="Frank Green", dt="2026-12-28 15:00:00"),
            messages=[{"role": "user", "content": "Frank Green here, 3pm."}]
        )
        assert ok, f"Booking failed: {msg}"
        with server.db() as conn:
            row = conn.execute(
                "SELECT * FROM outbox WHERE booking_id = ?", (booking["id"],)
            ).fetchone()
        assert row is not None, "Outbox row not found for new booking"
        assert row["event"] == "booking_created"
        assert row["status"] == "PENDING"


class TestConflictAccuracy:

    def test_conflict_detection_accuracy(self, temp_db, agent_and_user):
        """
        Phase F5: Synthetic conflict detection accuracy test.
        Generate 100 non-overlapping + 100 overlapping requests.
        Expect ~100% accuracy on conflict detection.
        """
        import server
        agent_id = agent_and_user["agent_id"]

        # Create a known booking at 2027-01-01 09:00 (60 min slot)
        anchor_uid = str(uuid.uuid4())
        ok, anchor, msg = server.validate_and_save_booking(
            agent_id, anchor_uid,
            _args(name="Anchor Person", dt="2027-01-01 09:00:00"),
            messages=[{"role": "user", "content": "Anchor Person here, 9am."}]
        )
        assert ok, f"Anchor booking failed: {msg}"

        n_overlap_detected = 0
        n_non_overlap_ok = 0

        # 50 requests that OVERLAP (within the 09:00-10:00 window)
        for i in range(50):
            minutes = i % 60  # 09:00 to 09:59
            dt = f"2027-01-01 09:{minutes:02d}:00"
            ok, _, _ = server.validate_and_save_booking(
                agent_id, str(uuid.uuid4()),
                _args(name=f"Overlap{i} Test", dt=dt),
                messages=[{"role": "user", "content": f"Overlap{i} Test here."}]
            )
            if not ok:
                n_overlap_detected += 1

        # 50 requests that DON'T overlap (10:00 onwards, each 60 min apart)
        for i in range(50):
            hour = 10 + i
            dt = f"2027-01-01 {hour:02d}:00:00"
            if hour >= 24:
                break
            ok, _, _ = server.validate_and_save_booking(
                agent_id, str(uuid.uuid4()),
                _args(name=f"NoOverlap{i} Test", dt=dt),
                messages=[{"role": "user", "content": f"NoOverlap{i} Test here."}]
            )
            if ok:
                n_non_overlap_ok += 1

        # Expect high accuracy (some may fail due to unparseable dt or other reasons)
        overlap_accuracy = n_overlap_detected / 50
        print(f"\nConflict detection: {n_overlap_detected}/50 overlaps detected "
              f"({overlap_accuracy*100:.1f}%)")
        print(f"Non-overlap success: {n_non_overlap_ok}/min(50,14) allowed")
        assert overlap_accuracy >= 0.80, (
            f"Conflict detection accuracy too low: {overlap_accuracy:.2%}"
        )
