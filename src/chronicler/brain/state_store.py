"""State persistence for The Chronicler's brain."""

import json
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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(state.model_dump(mode="json"), indent=2), encoding="utf-8")
