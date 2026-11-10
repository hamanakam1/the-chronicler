"""The generated ASCII art must match what the generator script produces.

`scripts/build_lowrider_art.py` rewrites the lowrider art embedded in the
package. If the committed art drifts from the generator output, the art is
edited in two places and only one of them wins. This test runs the generator
and asserts nothing changes.

The README header is a separate, hand-authored brand mark and is
intentionally *not* the CLI banner, so it is not covered here. The README
shows the lowrider through the terminal screenshots in "What it looks like".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _run(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / script)],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )


def test_art_generator_is_idempotent():
    """Regenerating the art must not change the committed file."""
    art_module = REPO / "src" / "chronicler" / "ascii_art.py"
    before = art_module.read_text()

    result = _run("build_lowrider_art.py")
    assert result.returncode == 0, result.stderr

    assert art_module.read_text() == before, (
        "src/chronicler/ascii_art.py is out of sync with scripts/build_lowrider_art.py. "
        "Run 'python3 scripts/build_lowrider_art.py' and commit the result."
    )


def test_cli_banner_contains_the_wordmark_and_the_lowrider():
    sys.path.insert(0, str(REPO / "src"))
    from chronicler.ascii_art import CHRONICLER_TAGLINE, LOWRIDER_ART, render_banner

    banner = render_banner()

    assert CHRONICLER_TAGLINE in banner
    # The lowrider is the CLI's identity: a wire wheel and the chop-top roof.
    assert ":OOOOO" in banner, "the CLI banner is missing the wire wheels"
    assert "_______" in LOWRIDER_ART, "the lowrider art is missing its roofline"
