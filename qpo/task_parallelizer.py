"""
qpo/task_parallelizer.py — Quantum Task Parallelization (QTP) Engine.

Formulates concurrent live-call operations (Local DB Capture, Google Sheets Sync,
Google Calendar Event, Webhook Dispatch, and Confirmation Speech Synthesis)
into a Resource-Constrained Task Scheduling QUBO.

Solves the optimal concurrency DAG using QAOA quantum simulation or
fast Simulated Annealing / Tabu Search, then executes non-conflicting tasks
simultaneously via asyncio.gather().
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine, Dict, List, Optional, Tuple

import numpy as np


# ── Task Specification ────────────────────────────────────────────────────────

@dataclass
class TaskDefinition:
    """Definition of an operational unit in a voice call workflow."""
    task_id: str
    name: str
    estimated_duration_ms: float
    depends_on: list[str] = field(default_factory=list)
    can_parallel_with: list[str] = field(default_factory=list)
    coroutine_func: Optional[Callable[..., Coroutine[Any, Any, Any]]] = None
    args: tuple = field(default_factory=tuple)
    kwargs: dict = field(default_factory=dict)


@dataclass
class ParallelStage:
    stage_idx: int
    tasks: list[TaskDefinition] = field(default_factory=list)


@dataclass
class QuantumScheduleResult:
    stages: list[ParallelStage]
    objective: float
    solver_used: str
    quantum_hardware_used: bool
    wall_time_s: float
    theoretical_serial_ms: float
    theoretical_parallel_ms: float
    theoretical_speedup: float
    metadata: dict = field(default_factory=dict)


# ── QUBO Construction for Task Parallelization ───────────────────────────────

def build_task_scheduling_qubo(
    tasks: list[TaskDefinition],
    n_stages: int = 2,
    penalty_onehot: float = 25.0,
    penalty_precedence: float = 40.0,
    reward_concurrency: float = 10.0,
) -> tuple[np.ndarray, list[tuple[str, int]]]:
    """
    Constructs a QUBO matrix Q for scheduling N tasks across K execution stages.

    Binary variable x_{i, k} = 1 iff Task i is scheduled in Stage k.
    Objective: Minimise makespan while enforcing:
      1. Every task runs in exactly one stage (one-hot per task).
      2. If task j depends on task i, stage(j) >= stage(i) + 1.
      3. Non-conflicting I/O tasks are rewarded for sharing the same parallel stage.
      4. Earlier stages penalised less to promote eager execution.
    """
    n_tasks = len(tasks)
    n_vars = n_tasks * n_stages
    task_idx_map = {t.task_id: i for i, t in enumerate(tasks)}

    var_map: list[tuple[str, int]] = []
    for i in range(n_tasks):
        for k in range(n_stages):
            var_map.append((tasks[i].task_id, k))

    def var_index(t_idx: int, s_idx: int) -> int:
        return t_idx * n_stages + s_idx

    Q = np.zeros((n_vars, n_vars), dtype=float)

    # 1. One-hot per task: (sum_k x_{i,k} - 1)^2
    for i in range(n_tasks):
        for k in range(n_stages):
            idx = var_index(i, k)
            Q[idx, idx] += -penalty_onehot
            # Eager bias: slight preference for earlier stages
            Q[idx, idx] += 0.2 * k * (tasks[i].estimated_duration_ms / 50.0)

        for k in range(n_stages):
            for l in range(k + 1, n_stages):
                idx_k = var_index(i, k)
                idx_l = var_index(i, l)
                Q[idx_k, idx_l] += 2.0 * penalty_onehot

    # 2. Precedence constraints: If j depends on i, stage(j) must be > stage(i)
    for j_idx, task_j in enumerate(tasks):
        for dep_id in task_j.depends_on:
            if dep_id not in task_idx_map:
                continue
            i_idx = task_idx_map[dep_id]

            for k in range(n_stages):
                for m in range(k + 1):  # m <= k violates dependency
                    idx_i = var_index(i_idx, k)
                    idx_j = var_index(j_idx, m)
                    if idx_i == idx_j:
                        continue
                    low, high = min(idx_i, idx_j), max(idx_i, idx_j)
                    Q[low, high] += penalty_precedence

    # 3. Concurrency synergy reward: If task i and task j can parallelize cleanly,
    # award a negative energy bonus if they share stage k
    for i in range(n_tasks):
        for j in range(i + 1, n_tasks):
            t_i = tasks[i]
            t_j = tasks[j]

            is_parallel_safe = (
                t_j.task_id in t_i.can_parallel_with
                or t_i.task_id in t_j.can_parallel_with
                or (not t_i.depends_on and not t_j.depends_on and t_i.task_id != t_j.task_id)
            )
            if t_i.task_id in t_j.depends_on or t_j.task_id in t_i.depends_on:
                is_parallel_safe = False

            if is_parallel_safe:
                for k in range(n_stages):
                    idx_i = var_index(i, k)
                    idx_j = var_index(j, k)
                    low, high = min(idx_i, idx_j), max(idx_i, idx_j)
                    Q[low, high] -= reward_concurrency

    return Q, var_map


# ── Quantum Task Scheduler ───────────────────────────────────────────────────

class QuantumTaskParallelizer:
    """
    Schedules and parallelizes operational tasks during active voice calls
    using QAOA quantum simulation or fast Simulated Annealing on QUBO.
    """

    def __init__(self, use_quantum: bool = False):
        self.use_quantum = use_quantum

    def schedule(
        self,
        tasks: list[TaskDefinition],
        n_stages: int = 2,
        timeout: float = 2.0,
    ) -> QuantumScheduleResult:
        t0 = time.perf_counter()

        if not tasks:
            return QuantumScheduleResult(
                stages=[],
                objective=0.0,
                solver_used="empty",
                quantum_hardware_used=False,
                wall_time_s=0.0,
                theoretical_serial_ms=0.0,
                theoretical_parallel_ms=0.0,
                theoretical_speedup=1.0,
            )

        # 1. Build Scheduling QUBO (minimisation form)
        Q, var_map = build_task_scheduling_qubo(tasks, n_stages=n_stages)
        n_vars = len(var_map)

        # Convert to maximisation for QPO solvers
        Q_max = -Q

        solver_name = "simulated_annealing"
        quantum_used = False

        if self.use_quantum and n_vars <= 16:
            try:
                from qpo.solvers import qaoa
                res = qaoa(Q_max, p=1, shots=256, maxiter=20)
                if res.objective != float("-inf") and "error" not in res.metadata:
                    sol_x = res.x
                    solver_name = res.solver
                    quantum_used = True
                else:
                    from qpo.solvers import simulated_annealing
                    res = simulated_annealing(Q_max, n_steps=2000)
                    sol_x = res.x
                    solver_name = "qaoa_fallback_sa"
            except Exception:
                from qpo.solvers import simulated_annealing
                res = simulated_annealing(Q_max, n_steps=2000)
                sol_x = res.x
                solver_name = "classical_sa"
        else:
            from qpo.solvers import simulated_annealing
            res = simulated_annealing(Q_max, n_steps=2000)
            sol_x = res.x
            solver_name = "simulated_annealing"

        elapsed = time.perf_counter() - t0

        # 2. Decode assignments: per task, pick the stage with highest activation
        stages_dict: dict[int, list[TaskDefinition]] = {k: [] for k in range(n_stages)}

        for i, task in enumerate(tasks):
            stage_vals = []
            for k in range(n_stages):
                var_idx = i * n_stages + k
                val = sol_x[var_idx] if var_idx < len(sol_x) else 0.0
                stage_vals.append(val)

            # If all 0 or multiple, select argmax or stage 0
            chosen_stage = int(np.argmax(stage_vals)) if any(v > 0 for v in stage_vals) else 0

            # Dependency invariant: stage(task) >= max(stage(dep)) + 1
            max_dep_stage = -1
            for dep_id in task.depends_on:
                for s_k, s_tasks in stages_dict.items():
                    if any(st.task_id == dep_id for st in s_tasks):
                        max_dep_stage = max(max_dep_stage, s_k)

            if max_dep_stage >= chosen_stage:
                chosen_stage = min(n_stages - 1, max_dep_stage + 1)

            stages_dict[chosen_stage].append(task)

        # 3. Format output stages
        scheduled_stages: list[ParallelStage] = []
        for k in range(n_stages):
            if stages_dict[k]:
                scheduled_stages.append(ParallelStage(stage_idx=k, tasks=stages_dict[k]))

        # Calculate metrics
        serial_ms = sum(t.estimated_duration_ms for t in tasks)
        parallel_ms = sum(
            max((t.estimated_duration_ms for t in st.tasks), default=0.0)
            for st in scheduled_stages
        )
        speedup = (serial_ms / parallel_ms) if parallel_ms > 0 else 1.0

        return QuantumScheduleResult(
            stages=scheduled_stages,
            objective=float(res.objective),
            solver_used=solver_name,
            quantum_hardware_used=quantum_used,
            wall_time_s=elapsed,
            theoretical_serial_ms=serial_ms,
            theoretical_parallel_ms=parallel_ms,
            theoretical_speedup=round(speedup, 2),
            metadata={
                "n_tasks": len(tasks),
                "n_stages": len(scheduled_stages),
            },
        )

    async def execute(
        self,
        schedule_result: QuantumScheduleResult,
    ) -> dict[str, Any]:
        """
        Executes scheduled stages sequentially, running all tasks within
        each stage concurrently via asyncio.gather().
        """
        execution_results: dict[str, Any] = {}
        stage_timings: list[dict] = []

        for stage in schedule_result.stages:
            st_t0 = time.perf_counter()
            coros = []
            task_ids = []

            for task in stage.tasks:
                if task.coroutine_func is not None:
                    coros.append(task.coroutine_func(*task.args, **task.kwargs))
                    task_ids.append(task.task_id)

            if coros:
                raw_outputs = await asyncio.gather(*coros, return_exceptions=True)
                for tid, out in zip(task_ids, raw_outputs):
                    if isinstance(out, Exception):
                        execution_results[tid] = {"status": "error", "error": str(out)}
                    else:
                        execution_results[tid] = out

            st_elapsed = (time.perf_counter() - st_t0) * 1000.0
            stage_timings.append({
                "stage_idx": stage.stage_idx,
                "tasks": [t.task_id for t in stage.tasks],
                "duration_ms": round(st_elapsed, 2),
            })

        return {
            "results": execution_results,
            "timings": stage_timings,
            "speedup": schedule_result.theoretical_speedup,
            "solver": schedule_result.solver_used,
        }


# ── High-Level Parallel Booking Dispatcher ───────────────────────────────────

async def dispatch_quantum_parallel_booking(
    agent: dict,
    call_uid: Optional[str],
    booking_args: dict,
    messages: list,
    hooks: dict[str, Any],
    caller_phone: str = "",
    use_quantum: bool = False,
) -> dict[str, Any]:
    """
    Quantum Parallel Booking Dispatcher:
    Instead of waiting for:
      Listen -> Transcribe -> DB Insert -> Google Sheets -> Google Calendar -> Webhook -> LLM -> TTS
    in a blocking serial queue, this builds an optimal concurrency wave:
      - Wave 0: Local SQLite DB ACID capture + Eager Verbal Confirmation Speech pre-synthesis
      - Wave 1 (Concurrent): Google Calendar + Google Sheets + Webhook Dispatch
      - Returns booking data, pre-rendered speech audio, and quantum execution telemetry.
    """
    t0 = time.perf_counter()
    agent_id = agent.get("id", 1)

    # 1. Fill caller phone if missing
    if not booking_args.get("phone") and caller_phone and caller_phone != "unknown":
        booking_args["phone"] = caller_phone

    # 2. Local DB Validation & Persistence Coroutine
    db_save_fn = hooks.get("validate_and_save_booking")
    booking_holder: dict[str, Any] = {"is_valid": False, "booking": None, "err_msg": ""}

    async def _task_db_save() -> dict:
        if not db_save_fn:
            return {"status": "skipped", "reason": "no db_save_fn"}
        is_valid, booking, err_msg = db_save_fn(agent_id, call_uid, booking_args, agent, messages=messages)
        booking_holder["is_valid"] = is_valid
        booking_holder["booking"] = booking
        booking_holder["err_msg"] = err_msg
        return {"status": "success" if is_valid else "rejected", "booking": booking, "error": err_msg}

    # 3. Google Suite Sync Coroutine (Sheets + Calendar in parallel)
    auto_sync_fn = hooks.get("auto_sync_booking_to_google")

    async def _task_google_sync() -> dict:
        if not auto_sync_fn or not booking_holder.get("booking"):
            return {"status": "skipped"}
        try:
            await auto_sync_fn(agent, booking_holder["booking"])
            return {"status": "synced"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # 4. Webhook Dispatch Coroutine
    fire_webhook_fn = hooks.get("fire_webhook")
    booking_payload_fn = hooks.get("booking_payload")

    async def _task_webhook() -> dict:
        hook_url = (agent.get("booking_webhook") or "").strip()
        if not hook_url or not fire_webhook_fn or not booking_holder.get("booking"):
            return {"status": "skipped"}
        try:
            b = booking_holder["booking"]
            payload = booking_payload_fn(agent, b) if booking_payload_fn else b
            await fire_webhook_fn(hook_url, payload)
            return {"status": "delivered"}
        except Exception as e:
            return {"status": "failed", "error": str(e)}

    # 5. Confirmation Voice Speech Synthesis Coroutine
    synth_fn = hooks.get("synthesize_speech_bytes")
    guest_name = booking_args.get("name") or "there"
    guest_dt = booking_args.get("datetime") or "your requested time"
    confirmation_text = f"You're all set, {guest_name}! Your booking for {guest_dt} is confirmed."

    async def _task_speech_synth() -> dict:
        if not synth_fn:
            return {"status": "skipped", "text": confirmation_text}
        try:
            voice = agent.get("voice_name") or "zira"
            rate = float(agent.get("rate") or 1.0)
            wav_bytes = await synth_fn(confirmation_text, voice=voice, rate=rate)
            return {"status": "synthesized", "wav_bytes": wav_bytes, "text": confirmation_text}
        except Exception as e:
            return {"status": "failed", "error": str(e), "text": confirmation_text}

    # 6. Define Tasks for Quantum Scheduler
    tasks = [
        TaskDefinition(
            task_id="db_save",
            name="ACID SQLite Transaction",
            estimated_duration_ms=45.0,
            depends_on=[],
            can_parallel_with=["speech_synth"],
            coroutine_func=_task_db_save,
        ),
        TaskDefinition(
            task_id="speech_synth",
            name="Confirmation Voice Synthesis (TTS)",
            estimated_duration_ms=210.0,
            depends_on=[],
            can_parallel_with=["db_save", "google_sync", "webhook"],
            coroutine_func=_task_speech_synth,
        ),
        TaskDefinition(
            task_id="google_sync",
            name="Google Sheets & Calendar Sync",
            estimated_duration_ms=350.0,
            depends_on=["db_save"],
            can_parallel_with=["webhook", "speech_synth"],
            coroutine_func=_task_google_sync,
        ),
        TaskDefinition(
            task_id="webhook",
            name="External Outbound Webhook",
            estimated_duration_ms=280.0,
            depends_on=["db_save"],
            can_parallel_with=["google_sync", "speech_synth"],
            coroutine_func=_task_webhook,
        ),
    ]

    # 7. Quantum Schedule & Execute
    parallelizer = QuantumTaskParallelizer(use_quantum=use_quantum)
    schedule_plan = parallelizer.schedule(tasks, n_stages=2, timeout=2.0)
    exec_outcome = await parallelizer.execute(schedule_plan)

    total_wall_ms = (time.perf_counter() - t0) * 1000.0

    return {
        "is_valid": booking_holder["is_valid"],
        "booking": booking_holder["booking"],
        "err_msg": booking_holder["err_msg"],
        "reply_text": confirmation_text,
        "reply_wav_bytes": exec_outcome["results"].get("speech_synth", {}).get("wav_bytes"),
        "telemetry": {
            "wall_time_ms": round(total_wall_ms, 2),
            "theoretical_speedup": schedule_plan.theoretical_speedup,
            "solver_used": schedule_plan.solver_used,
            "quantum_hardware_used": schedule_plan.quantum_hardware_used,
            "stages_executed": len(schedule_plan.stages),
            "timings": exec_outcome["timings"],
        },
    }
