#!/usr/bin/env python3
"""Refresh the README ASCII art block from chronicler.ascii_art."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "src"))

from chronicler.ascii_art import CHRONICLER_ASCII, LOWRIDER_ART  # noqa: E402

README = REPO / "README.md"

block = "\n".join(
    [
        "<div align=\"center\">",
        "",
        "```text",
        CHRONICLER_ASCII.strip("\n"),
        "```",
        "",
        "```text",
        LOWRIDER_ART.strip("\n"),
        "```",
        "",
        "</div>",
    ]
)

text = README.read_text()
pattern = re.compile(
    r'<div align="center">\s*\n\s*```text\n.*?\n```\s*\n\s*```text\n.*?\n```\s*\n\s*</div>',
    re.S,
)
new_text, count = pattern.subn(lambda _m: block, text, count=1)
if count != 1:
    raise SystemExit("could not find the README art block to replace")
README.write_text(new_text)
print("README art block refreshed")
