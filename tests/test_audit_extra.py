import json, sys
from pathlib import Path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def test_retrieval_metrics():
    r = json.load(open(ROOT / "research/results/retrieval.json"))
    assert r["n_queries"] == 10
    assert r["n_chunks"] == 13
    assert r["mean_precision"] == 0.175
    assert r["mean_recall"] == 0.2667
    assert r["mean_mrr"] == 0.4833
    assert r["mean_ndcg"] == 0.5051

def test_bargein_eval():
    b = json.load(open(ROOT / "research/results/bargein_eval.json"))
    assert b["n_cases"] == 40
    assert b["precision"] == 1.0
    assert b["recall"] == 1.0
    assert b["f1"] == 1.0
    assert b["accuracy"] == 1.0
    assert b["tp"] == 15 and b["tn"] == 25

def test_pii_eval():
    p = json.load(open(ROOT / "research/results/pii_eval.json"))
    assert p["metrics"]["CARD"]["precision"] == 1.0
    assert p["metrics"]["EMAIL"]["precision"] == 1.0
    assert abs(p["metrics"]["PHONE"]["precision"] - 0.8889) < 0.001
    assert abs(p["metrics"]["MICRO"]["precision"] - 0.9524) < 0.001

def test_scoring_phi_role():
    from qpo.scoring import phi_role
    r = "Certainly! Here are your options:\n* Check-in at 3 PM\n* Check-out at 11 AM\n\n1. Pool access included."
    assert phi_role(r) < 1.0

def test_scoring_phi_retain():
    from qpo.scoring import phi_retain
    assert phi_retain("pool and 3 PM", ["pool", "3 PM"]) == 1.0
    assert phi_retain("nothing here", ["pool", "3 PM"]) == 0.0
    assert phi_retain("anything", []) == 1.0

def test_scoring_weights():
    from qpo.scoring import WEIGHTS
    assert abs(sum(WEIGHTS.values()) - 1.0) < 1e-9

def test_rbac_roles():
    from guardrail import ROLE_RANKS, has_permission
    assert ROLE_RANKS["owner"] == 4
    assert ROLE_RANKS["viewer"] == 1
    assert has_permission("owner", "can_view_sensitive_data") is True
    assert has_permission("viewer", "can_view_sensitive_data") is False

def test_luhn_check():
    from guardrail import _luhn_check
    assert _luhn_check("4532015112830366") is True
    assert _luhn_check("1234567890123456") is False

def test_task_parallelizer_schedule():
    from qpo.task_parallelizer import QuantumTaskParallelizer, TaskDefinition
    tasks = [
        TaskDefinition(task_id="a", name="A", estimated_duration_ms=10.0, depends_on=[]),
        TaskDefinition(task_id="b", name="B", estimated_duration_ms=20.0, depends_on=["a"]),
    ]
    sched = QuantumTaskParallelizer().schedule(tasks, n_stages=2)
    stage_of = {}
    for st in sched.stages:
        for t in st.tasks:
            stage_of[t.task_id] = st.stage_idx
    assert stage_of["b"] > stage_of["a"], "Dependency violated"

def test_no_retry_in_google_integration():
    src = open(ROOT / "google_integration.py").read()
    assert "hmac" not in src.lower()
    assert "idempot" not in src.lower()
    assert "backoff" not in src.lower()

def test_no_latency_artifact():
    assert not (ROOT / "research/results/latency.csv").exists()

def test_no_eval_prompts():
    assert not (ROOT / "research/data/eval_prompts.jsonl").exists()