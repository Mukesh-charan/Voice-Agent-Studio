import os
import sys
from pathlib import Path
import asyncio
import pytest

ROOT_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT_DIR))

from qpo.task_parallelizer import (
    QuantumTaskParallelizer,
    TaskDefinition,
    dispatch_quantum_parallel_booking,
)


def test_qtp_scheduling_qubo():
    """Verify QUBO formulation and speedup calculation for concurrent call tasks."""
    qtp = QuantumTaskParallelizer(use_quantum=False)
    tasks = [
        TaskDefinition("db", "DB Insert", 50.0),
        TaskDefinition("tts", "TTS Synthesis", 200.0, can_parallel_with=["db"]),
        TaskDefinition("gcal", "Google Calendar", 300.0, depends_on=["db"]),
        TaskDefinition("gsheet", "Google Sheet", 250.0, depends_on=["db"], can_parallel_with=["gcal"]),
    ]

    res = qtp.schedule(tasks, n_stages=2)
    assert len(res.stages) >= 1
    assert res.theoretical_speedup > 1.0
    assert res.solver_used in ["simulated_annealing", "tabu_search", "qaoa_fallback_sa"]
    print(f"Test QTP Schedule Speedup: {res.theoretical_speedup}x across {len(res.stages)} stages")


@pytest.mark.asyncio
async def test_dispatch_quantum_parallel_booking():
    """Verify end-to-end parallel execution of DB, Google Suite sync, and speech synthesis."""
    saved_flag = False
    gcal_flag = False
    synth_flag = False

    def mock_save(agent_id, call_uid, args, agent, messages=None):
        nonlocal saved_flag
        saved_flag = True
        return True, {"id": 99, "name": args.get("name"), "datetime": args.get("datetime")}, ""

    async def mock_google(agent, booking):
        nonlocal gcal_flag
        await asyncio.sleep(0.01)
        gcal_flag = True

    async def mock_synth(text, voice="zira", rate=1.0):
        nonlocal synth_flag
        synth_flag = True
        return b"RIFF_FAKE_WAV_BYTES"

    hooks = {
        "validate_and_save_booking": mock_save,
        "auto_sync_booking_to_google": mock_google,
        "synthesize_speech_bytes": mock_synth,
    }

    agent = {"id": 1, "name": "Test Receptionist", "google_auto_sync_calendar": True}
    booking_args = {"name": "Sanjjey Arumugam", "datetime": "Tomorrow 3pm", "user_confirmed": True}

    res = await dispatch_quantum_parallel_booking(
        agent=agent,
        call_uid="test_call_123",
        booking_args=booking_args,
        messages=[],
        hooks=hooks,
        caller_phone="+1234567890",
    )

    assert res["is_valid"] is True
    assert res["booking"]["name"] == "Sanjjey Arumugam"
    assert saved_flag is True
    assert gcal_flag is True
    assert synth_flag is True
    assert res["reply_wav_bytes"] == b"RIFF_FAKE_WAV_BYTES"
    assert res["telemetry"]["theoretical_speedup"] > 1.0
    print("Test Dispatch Quantum Parallel Booking: PASSED", res["telemetry"])
