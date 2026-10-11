"""Smoke test: package imports and the CLI reports its version."""

import os
import subprocess
import sys
from pathlib import Path

import tokenscope


def test_version_is_set() -> None:
    assert tokenscope.__version__


def test_cli_version() -> None:
    src = str(Path(__file__).resolve().parents[1] / "src")
    env = {**os.environ, "PYTHONPATH": os.pathsep.join([src, os.environ.get("PYTHONPATH", "")])}
    proc = subprocess.run(
        [sys.executable, "-m", "tokenscope", "--version"], capture_output=True, text=True, env=env
    )
    assert proc.returncode == 0
    assert tokenscope.__version__ in proc.stdout
