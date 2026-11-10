"""A failed checkpoint must leave the daemon's previous progress recoverable."""

from __future__ import annotations

import json
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from chronicler.brain.state import ChroniclerState
from chronicler.brain.state_store import JsonStateStore


def _state(cycle: int) -> ChroniclerState:
    return ChroniclerState(
        last_watermark=datetime(2026, 1, 1, 0, cycle, tzinfo=UTC),
        processed_heuristic_ids=[f"synthetic-heuristic-{cycle}"],
        cycles_completed=cycle,
        audits_seen=cycle * 2,
        last_commit_sha=f"synthetic-sha-{cycle}",
    )


def test_successful_save_is_complete_after_restart(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "state.json"
    store = JsonStateStore(str(path))
    assert store.load() == ChroniclerState()

    store.save(_state(1))
    store.save(_state(2))

    assert JsonStateStore(str(path)).load() == _state(2)
    assert list(path.parent.iterdir()) == [path]


def test_partial_checkpoint_write_preserves_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    store = JsonStateStore(str(path))
    store.save(_state(1))
    original_temporary_file = tempfile.NamedTemporaryFile
    original_write_text = Path.write_text

    def interrupted_path_write(self: Path, content: str, *args: Any, **kwargs: Any) -> int:
        original_write_text(self, content[: len(content) // 2], *args, **kwargs)
        raise OSError("synthetic disk full")

    def interrupted_temporary_file(*args: Any, **kwargs: Any) -> Any:
        temporary = original_temporary_file(*args, **kwargs)
        write = temporary.write

        def interrupted_write(content: str) -> None:
            write(content[: len(content) // 2])
            temporary.flush()
            raise OSError("synthetic disk full")

        temporary.write = interrupted_write
        return temporary

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", interrupted_temporary_file)
    monkeypatch.setattr(Path, "write_text", interrupted_path_write)

    with pytest.raises(OSError, match="synthetic disk full"):
        store.save(_state(2))

    assert JsonStateStore(str(path)).load() == _state(1)
    assert list(tmp_path.iterdir()) == [path]


def test_failed_checkpoint_replace_preserves_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    store = JsonStateStore(str(path))
    store.save(_state(1))

    def interrupted_replace(self: Path, target: Path) -> Path:
        assert self.parent == path.parent
        assert target == path
        # A reader racing the final replacement must still see the old checkpoint.
        assert JsonStateStore(str(path)).load() == _state(1)
        raise OSError("synthetic replace failure")

    monkeypatch.setattr(Path, "replace", interrupted_replace)

    with pytest.raises(OSError, match="synthetic replace failure"):
        store.save(_state(2))

    assert JsonStateStore(str(path)).load() == _state(1)
    assert list(tmp_path.iterdir()) == [path]


def test_failed_serialization_preserves_previous_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "state.json"
    store = JsonStateStore(str(path))
    store.save(_state(1))

    def interrupted_serialization(*args: Any, **kwargs: Any) -> str:
        raise TypeError("synthetic serialization failure")

    monkeypatch.setattr(json, "dumps", interrupted_serialization)

    with pytest.raises(TypeError, match="synthetic serialization failure"):
        store.save(_state(2))

    assert JsonStateStore(str(path)).load() == _state(1)
    assert list(tmp_path.iterdir()) == [path]


def test_save_preserves_unrelated_temporary_file(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    unrelated = tmp_path / ".state.json.tmp"
    unrelated.write_text("synthetic earlier writer", encoding="utf-8")

    JsonStateStore(str(path)).save(_state(1))

    assert JsonStateStore(str(path)).load() == _state(1)
    assert unrelated.read_text(encoding="utf-8") == "synthetic earlier writer"
    assert set(tmp_path.iterdir()) == {path, unrelated}
