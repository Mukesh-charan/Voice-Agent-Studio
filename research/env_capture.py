"""
env_capture.py — Phase A2
Writes results/env.json with reproducibility metadata:
  CPU, GPU, RAM, OS, Python version, package versions,
  git commit, LLM model + quantization, STT model, TTS engine.

Usage:
    python research/env_capture.py
"""

import json
import os
import platform
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SEED = 1234
RESULTS_DIR = Path(__file__).parent / "results"


def _run(cmd: list[str], fallback: str = "unknown") -> str:
    try:
        return subprocess.check_output(cmd, stderr=subprocess.DEVNULL, text=True).strip()
    except Exception:
        return fallback


def _pkg_version(name: str) -> str:
    try:
        import importlib.metadata
        return importlib.metadata.version(name)
    except Exception:
        return "not-installed"


def capture() -> dict:
    """Collect environment metadata and return as a dict."""
    # CPU info
    cpu_info = platform.processor() or platform.machine()
    try:
        import psutil
        ram_gb = round(psutil.virtual_memory().total / (1024 ** 3), 2)
    except ImportError:
        ram_gb = "unknown (install psutil)"

    # GPU info via nvidia-smi
    gpu_info = _run(
        ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"],
        fallback="no NVIDIA GPU or nvidia-smi not found",
    )

    # Git commit
    git_commit = _run(["git", "rev-parse", "--short", "HEAD"], fallback="not-a-git-repo")
    git_branch = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"], fallback="unknown")

    # Key package versions
    packages = [
        "fastapi", "uvicorn", "httpx", "python-dotenv", "python-multipart",
        "pypdf", "qiskit", "qiskit-aer", "qiskit-optimization", "qiskit-algorithms",
        "edge-tts", "faster-whisper", "numpy", "scipy", "scikit-learn",
        "sentence-transformers", "jiwer",
    ]
    pkg_versions = {pkg: _pkg_version(pkg) for pkg in packages}

    # LLM / STT / TTS from env
    env = {
        "LLM_BASE_URL": os.environ.get("LLM_BASE_URL", "http://localhost:11434/v1"),
        "LLM_MODEL": os.environ.get("LLM_MODEL", "llama3.1:8b"),
        "STT_MODEL": os.environ.get("STT_MODEL", "whisper-large-v3-turbo"),
        "STT_BASE_URL": os.environ.get("STT_BASE_URL", ""),
        "TTS_VOICE": os.environ.get("TTS_VOICE", "zira"),
        "TTS_PROVIDER": os.environ.get("TTS_PROVIDER", "edge"),
        "STT_PROVIDER": os.environ.get("STT_PROVIDER", "groq"),
    }

    return {
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "seed": SEED,
        "os": {
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
        },
        "python": {
            "version": sys.version,
            "executable": sys.executable,
        },
        "cpu": cpu_info,
        "ram_gb": ram_gb,
        "gpu": gpu_info,
        "git": {
            "commit": git_commit,
            "branch": git_branch,
        },
        "packages": pkg_versions,
        "runtime": env,
    }


def main():
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    info = capture()
    out_path = RESULTS_DIR / "env.json"
    out_path.write_text(json.dumps(info, indent=2, default=str), encoding="utf-8")
    print(f"[env_capture] Written to {out_path}")
    print(f"  git commit : {info['git']['commit']}")
    print(f"  Python     : {info['python']['version'].split()[0]}")
    print(f"  GPU        : {info['gpu']}")
    print(f"  LLM model  : {info['runtime']['LLM_MODEL']}")
    print(f"  STT model  : {info['runtime']['STT_MODEL']}")


if __name__ == "__main__":
    main()
