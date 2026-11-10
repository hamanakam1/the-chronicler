"""GitHub Actions must be pinned to immutable commit SHAs.

A tag such as ``actions/checkout@v4`` is a moving reference: whoever
controls that tag controls the code that runs in this repository's CI, with
the repository's token. Pinning to a commit SHA removes the indirection.

This test fails when a workflow starts using a tag or branch again.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO / ".github" / "workflows"

#: `uses: owner/repo@ref`
USES = re.compile(r"uses:\s*(?P<action>[\w.-]+/[\w.-]+(?:/[\w.-]+)?)@(?P<ref>\S+)")
SHA = re.compile(r"^[0-9a-f]{40}$")


def _workflow_files() -> list[Path]:
    return sorted(WORKFLOWS.glob("*.yml")) + sorted(WORKFLOWS.glob("*.yaml"))


def test_there_are_workflows_to_check():
    assert _workflow_files(), "no workflow files were found"


def test_every_action_is_pinned_to_a_commit_sha():
    unpinned: list[str] = []
    for path in _workflow_files():
        text = path.read_text(encoding="utf-8")
        for match in USES.finditer(text):
            ref = match.group("ref")
            if not SHA.match(ref):
                unpinned.append(f"{path.name}: {match.group('action')}@{ref}")
    assert not unpinned, "actions must be pinned to a 40-character commit SHA:\n" + "\n".join(unpinned)


def test_the_pinned_actions_are_consistent_across_workflows():
    """One checkout, one setup-python: a single reviewed set of commits."""
    by_action: dict[str, set[str]] = {}
    for path in _workflow_files():
        text = path.read_text(encoding="utf-8")
        for match in USES.finditer(text):
            by_action.setdefault(match.group("action"), set()).add(match.group("ref"))

    inconsistent = {action: refs for action, refs in by_action.items() if len(refs) > 1}
    assert not inconsistent, f"actions pinned to different commits: {inconsistent}"
