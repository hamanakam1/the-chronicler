"""State persistence for The Chronicler's brain."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Protocol

from chronicler.brain.state import ChroniclerState


class StateStore(Protocol):
    """Port for chronicler brain state persistence."""

    def load(self) -> ChroniclerState: ...

    def save(self, state: ChroniclerState) -> None: ...


class InMemoryStateStore:
    """Process-local state store used by tests and single-cycle runs."""

    def __init__(self) -> None:
        self.state = ChroniclerState()

    def load(self) -> ChroniclerState:
        return self.state

    def save(self, state: ChroniclerState) -> None:
        self.state = state


class JsonStateStore:
    """File-backed state store persisted under CHRONICLER_STATE_PATH."""

    def __init__(self, path: str) -> None:
        self.path = Path(path)

    def load(self) -> ChroniclerState:
        if not self.path.exists():
            return ChroniclerState()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return ChroniclerState.model_validate(data)

    def save(self, state: ChroniclerState) -> None:
        """Keep the previous checkpoint readable until its replacement is complete."""
        serialized = json.dumps(state.model_dump(mode="json"), indent=2)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_path = Path(temporary.name)
                temporary.write(serialized)
                temporary.flush()
                os.fsync(temporary.fileno())
            temporary_path.replace(self.path)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)
