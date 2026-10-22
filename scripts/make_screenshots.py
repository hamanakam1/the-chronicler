#!/usr/bin/env python3
"""Render the README's terminal screenshots from real Chronicler output.

Every pixel in ``docs/screenshots/*.png`` comes from a real ``chronicler``
invocation. Nothing is drawn by hand and nothing is pasted from a terminal
that happened to look good: the script drives the CLI, captures the bytes it
writes, and paints those bytes into a window frame.

Usage::

    python3 -m pip install pillow
    python3 scripts/make_screenshots.py            # regenerate every shot

The script needs Pillow, which is a *development* dependency only. The
Chronicler itself still has zero runtime dependencies beyond its own.

What gets captured:

``doctor.png``
    ``chronicler doctor``: the local black-ops health check. It reports
    whether Ollama is reachable, whether the EdgeRecord ledger is readable,
    and whether the target repository is a Git repository.

``cycle.png``
    ``chronicler run --once``: a single orchestration cycle against the same
    ledger, reporting the audits it read, the heuristics it extracted, the
    documents it wrote and the commit receipts it captured.

The Chronicler prints its ASCII banner before every payload. The banner is
stripped here so the screenshot shows the *result* rather than the wordmark;
the command line shown above each block is the real command.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO / "docs" / "screenshots"

sys.path.insert(0, str(Path(__file__).resolve().parent))

from term2png import FontBook, session  # noqa: E402


def run_cli(args: list[str]) -> str:
    """Run the real CLI and return exactly what it printed."""

    import os
    import subprocess

    env = dict(os.environ)
    env["PYTHONPATH"] = str(REPO / "src")
    env["FORCE_COLOR"] = "1"
    env["COLUMNS"] = "200"
    env.pop("NO_COLOR", None)
    completed = subprocess.run(
        [sys.executable, "-m", "chronicler", *args],
        cwd=str(REPO),
        env=env,
        capture_output=True,
        text=True,
    )
    return completed.stdout + completed.stderr


def strip_banner(text: str) -> str:
    """Drop the ASCII banner the CLI prints before its payload.

    The banner is real output, but it is the wordmark rather than the
    result, and it would bury the payload under forty lines of art. The
    payload is the last top-level JSON object the command printed.
    """

    lines = text.split("\n")
    for index in range(len(lines) - 1, -1, -1):
        if lines[index].startswith("{"):
            return "\n".join(lines[index:])
    return text


def build() -> int:
    fonts = FontBook()
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []

    # -- doctor.png -----------------------------------------------------
    doctor_output = strip_banner(run_cli(["doctor"]))
    shot = session("chronicler doctor", [("chronicler doctor", doctor_output)], fonts)
    path = OUTPUT_DIR / "doctor.png"
    shot.save(path, optimize=True)
    written.append(path)

    # -- cycle.png ------------------------------------------------------
    cycle_output = strip_banner(run_cli(["run", "--once"]))
    shot = session(
        "chronicler run --once",
        [("chronicler run --once", cycle_output)],
        fonts,
    )
    path = OUTPUT_DIR / "cycle.png"
    shot.save(path, optimize=True)
    written.append(path)

    for path in written:
        size = path.stat().st_size
        print(f"wrote {path.relative_to(REPO)} · {size // 1024} KiB")
    return 0


def main(argv: list[str] | None = None) -> int:
    return build()


if __name__ == "__main__":
    raise SystemExit(main())
