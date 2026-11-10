"""The README must keep describing the code it documents.

A config variable that was renamed, or a module that moved, leaves the
documentation quietly wrong. These tests run the consistency checker so the
drift is caught by CI rather than by a reader.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CHECKER = REPO / "scripts" / "check_readme_consistency.py"


def _run_checker() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECKER)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def test_readme_matches_the_code():
    result = _run_checker()
    assert result.returncode == 0, f"README drift detected:\n{result.stdout}\n{result.stderr}"


def test_checker_actually_catches_drift(tmp_path):
    """The checker must fail when the README drifts, or it proves nothing."""
    drifted = REPO / "README.md"
    original = drifted.read_text()
    try:
        drifted.write_text(original + "\n`CHRONICLER_DOES_NOT_EXIST` is a variable.\n")
        result = _run_checker()
        assert result.returncode == 1
        assert "CHRONICLER_DOES_NOT_EXIST" in result.stdout
    finally:
        drifted.write_text(original)
