"""
make_tables.py — Phase A2 / Phase J
Generates LaTeX tables from results/*.json and results/*.csv
and writes them to research/generated/*.tex for \\input{} in the paper.

Tables generated:
  tab_rbac.tex          — RBAC permissions matrix (from guardrail.PERMISSIONS)
  tab_latency.tex       — Latency TTFF/E2E p50/p95/mean (from results/latency.csv)
  tab_pii.tex           — PII redaction P/R/F1 per type (from results/pii_eval.json)
  tab_bargein.tex       — Barge-in VAD P/R/F1 (from results/bargein_eval.json)
  tab_qpo_scaling.tex   — QPO solver scaling (from results/qpo_scaling.csv)
  tab_qpo_solvers.tex   — QPO solver comparison (from results/qpo_eval.json)

Usage:
    python research/make_tables.py
"""

import csv
import json
import math
import statistics
import sys
from pathlib import Path

# ── Paths ─────────────────────────────────────────────────────────────────────
HERE      = Path(__file__).parent
RESULTS   = HERE / "results"
GENERATED = HERE / "generated"
sys.path.insert(0, str(HERE.parent))   # so we can import server/guardrail


def _fmt(v, decimals=3):
    """Format a numeric value for LaTeX, returning em-dash for missing."""
    if v is None or v == "":
        return "---"
    if isinstance(v, float) and math.isnan(v):
        return "---"
    try:
        return f"{float(v):.{decimals}f}"
    except (TypeError, ValueError):
        return str(v)


def _percentile(vals: list, p: float) -> float:
    """Return the p-th percentile (0–1) of a sorted list."""
    if not vals:
        return float("nan")
    idx = min(int(p * len(vals)), len(vals) - 1)
    return vals[idx]


# ── 1. RBAC permissions table ─────────────────────────────────────────────────

def make_rbac_table() -> str:
    """Generate the RBAC permissions table directly from guardrail.PERMISSIONS."""
    from guardrail import PERMISSIONS, ROLES_LIST

    perm_labels = {
        "can_delete_agent":      "Delete agent",
        "can_edit_settings":     "Edit settings",
        "can_manage_members":    "Manage members",
        "can_manage_knowledge":  "Manage knowledge",
        "can_view_sensitive_data": "View PII",
        "can_edit_bookings":     "Edit bookings",
        "can_delete_bookings":   "Delete bookings",
        "can_call":              "Make calls",
    }

    col_header = " & ".join(r.capitalize() for r in ROLES_LIST)
    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{RBAC Permission Matrix (auto-generated from \texttt{guardrail.PERMISSIONS})}",
        r"\label{tab:rbac}",
        r"\begin{tabular}{l" + "c" * len(ROLES_LIST) + "}",
        r"\toprule",
        r"\textbf{Permission} & " + col_header + r" \\",
        r"\midrule",
    ]
    for perm_key, label in perm_labels.items():
        row = label
        for role in ROLES_LIST:
            val = PERMISSIONS[role].get(perm_key, False)
            row += r" & \checkmark" if val else r" & $\times$"
        lines.append(row + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ── 2. Latency table (from results/latency.csv) ───────────────────────────────

def make_latency_table() -> str:
    csv_path = RESULTS / "latency.csv"
    if not csv_path.exists():
        return "% latency.csv not yet generated --- run scripts/bench_latency.py first\n"

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))

    # Detect stub (server was not running)
    if rows and rows[0].get("query") == "STUB_NO_SERVER":
        return (
            "% latency.csv is a stub (server was not running during benchmark).\n"
            "% Run: python scripts/bench_latency.py --url http://localhost:8000\n"
        )

    ttffs = sorted([float(r["ttff_s"]) for r in rows if r.get("ttff_s")])
    e2es  = sorted([float(r["e2e_s"])  for r in rows if r.get("e2e_s")])

    def _row(label, vals):
        if not vals:
            return f"{label} & --- & --- & --- & --- \\\\"
        p50  = _percentile(vals, 0.50)
        p95  = _percentile(vals, 0.95)
        mean = statistics.mean(vals)
        sd   = statistics.stdev(vals) if len(vals) > 1 else 0.0
        return (
            f"{label} & {p50:.3f} & {p95:.3f} & "
            f"{mean:.3f}$\\pm${sd:.3f} \\\\"
        )

    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Latency benchmark: TTFF and E2E (seconds). "
        r"$N=" + str(len(rows)) + r"$, seed=42.}",
        r"\label{tab:latency}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"\textbf{Metric} & \textbf{P50} & \textbf{P95} & \textbf{Mean$\pm$SD} \\",
        r"\midrule",
        _row("TTFF (s)", ttffs),
        _row("E2E (s)", e2es),
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ── 3. PII evaluation table (from results/pii_eval.json) ─────────────────────

def make_pii_table() -> str:
    pii_path = RESULTS / "pii_eval.json"
    if not pii_path.exists():
        return "% pii_eval.json not yet generated --- run scripts/eval_pii.py first\n"

    data    = json.loads(pii_path.read_text(encoding="utf-8"))
    metrics = data.get("metrics", {})
    n_items = data.get("n_items", "?")

    # Order: individual types first, then MICRO
    type_order = [k for k in metrics if k != "MICRO"] + (["MICRO"] if "MICRO" in metrics else [])

    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{PII redaction accuracy by entity type "
        r"($N=" + str(n_items) + r"$ utterances, viewer role). "
        r"Auto-generated from \texttt{scripts/eval\_pii.py}.}",
        r"\label{tab:pii}",
        r"\begin{tabular}{lrrrrrr}",
        r"\toprule",
        r"\textbf{Entity} & \textbf{P} & \textbf{R} & \textbf{F1} "
        r"& \textbf{TP} & \textbf{FP} & \textbf{FN} \\",
        r"\midrule",
    ]

    for etype in type_order:
        m = metrics[etype]
        if etype == "MICRO":
            lines.append(r"\midrule")
            label = r"\textbf{Micro-avg}"
        else:
            label = etype
        lines.append(
            f"{label} & {m['precision']:.3f} & {m['recall']:.3f} & {m['f1']:.3f}"
            f" & {m['tp']} & {m['fp']} & {m['fn']} \\\\"
        )

    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ── 4. Barge-in VAD evaluation table (from results/bargein_eval.json) ─────────

def make_bargein_table() -> str:
    path = RESULTS / "bargein_eval.json"
    if not path.exists():
        return "% bargein_eval.json not yet generated --- run scripts/eval_bargein.py first\n"

    data   = json.loads(path.read_text(encoding="utf-8"))
    params = data.get("params", {})
    n      = data.get("n_cases", "?")

    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Barge-in VAD detection accuracy ($N=" + str(n) + r"$ synthetic cases). "
        r"Parameters: RMS floor=" + str(params.get("rms_floor", "")) + r", "
        r"bleed factor=" + str(params.get("bleed_factor", "")) + r"$\times$, "
        r"hits=" + str(params.get("n_hits", "")) + r", "
        r"grace=" + str(params.get("grace_frames", "")) + r"~frames.}",
        r"\label{tab:bargein}",
        r"\begin{tabular}{lrrrr}",
        r"\toprule",
        r"\textbf{Metric} & \textbf{Value} & \textbf{TP} & \textbf{FP} & \textbf{FN} \\",
        r"\midrule",
        f"Precision & {data['precision']:.3f} & {data['tp']} & {data['fp']} & --- \\\\",
        f"Recall    & {data['recall']:.3f} & {data['tp']} & --- & {data['fn']} \\\\",
        f"F1        & {data['f1']:.3f} & \\multicolumn{{3}}{{c}}{{---}} \\\\",
        f"Accuracy  & {data['accuracy']:.3f} & \\multicolumn{{3}}{{c}}{{---}} \\\\",
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines)


# ── 5. QPO solver scaling table (from results/qpo_scaling.csv) ───────────────

def make_qpo_scaling_table() -> str:
    csv_path = RESULTS / "qpo_scaling.csv"
    if not csv_path.exists():
        return (
            "% qpo_scaling.csv not yet generated "
            "--- run: python -m qpo.run_all\n"
        )

    rows = list(csv.DictReader(csv_path.open(encoding="utf-8")))
    if not rows:
        return "% qpo_scaling.csv is empty\n"

    cols   = list(rows[0].keys())
    header = " & ".join(f"\\textbf{{{c}}}" for c in cols)
    lines  = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{QPO solver scaling study: objective value and wall time by $n$ (seed=42). "
        r"Auto-generated from \texttt{qpo/run\_all.py}.}",
        r"\label{tab:qpo_scaling}",
        r"\begin{tabular}{" + "l" * len(cols) + "}",
        r"\toprule",
        header + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(str(row[c]) for c in cols) + r" \\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ── 6. QPO solver comparison table (from results/qpo_eval.json) ───────────────

def make_qpo_solvers_table() -> str:
    path = RESULTS / "qpo_eval.json"
    if not path.exists():
        return "% qpo_eval.json not yet generated --- run scripts/eval_qpo.py first\n"

    data    = json.loads(path.read_text(encoding="utf-8"))
    solvers = data.get("solvers", {})
    mae     = data.get("mean_mae", None)
    n_turns = data.get("n_turns", "?")

    lines = [
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{QPO solver comparison on $N=" + str(n_turns) + r"$ labelled turns "
        r"(mean MAE vs.\ ground-truth $\Phi$ scores: "
        + (_fmt(mae, 3) if mae is not None else "---") + r"). "
        r"QUBO energy: lower is better (maximisation problem, negated).}",
        r"\label{tab:qpo_solvers}",
        r"\begin{tabular}{lrrl}",
        r"\toprule",
        r"\textbf{Solver} & \textbf{QUBO Energy} & \textbf{\#Modules} & \textbf{Time (s)} \\",
        r"\midrule",
    ]

    for name, res in solvers.items():
        if "error" in res:
            lines.append(f"{name} & \\multicolumn{{3}}{{c}}{{Error: {res['error'][:40]}}} \\\\")
        else:
            t = res.get("wall_time_s", "---")
            lines.append(
                f"{name} & {res['qubo_energy']:.2f} & {res['n_selected']} & {_fmt(t, 4)} \\\\"
            )

    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines)


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    GENERATED.mkdir(parents=True, exist_ok=True)

    tables = {
        "tab_rbac.tex":         make_rbac_table,
        "tab_latency.tex":      make_latency_table,
        "tab_pii.tex":          make_pii_table,
        "tab_bargein.tex":      make_bargein_table,
        "tab_qpo_scaling.tex":  make_qpo_scaling_table,
        "tab_qpo_solvers.tex":  make_qpo_solvers_table,
    }
    for filename, fn in tables.items():
        content = fn()
        out_path = GENERATED / filename
        out_path.write_text(content, encoding="utf-8")
        print(f"[make_tables] Written {out_path}")


if __name__ == "__main__":
    main()
