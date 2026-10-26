"""Runtime configuration for The Chronicler (env-overridable via CHRONICLER_*)."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ChroniclerConfig(BaseSettings):
    """Headless daemon configuration."""

    model_config = SettingsConfigDict(env_prefix="CHRONICLER_", env_file=".env", extra="ignore")

    # Local LLM brain
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.8:latest"
    ollama_timeout_seconds: float = 120.0

    # EdgeRecord append-only ledger
    ledger_path: str = Field(default_factory=lambda: str(Path.home() / ".taskrivet" / "ledger.sqlite"))

    # Target repository receiving hardened rules + lore docs
    repo_root: str | None = None
    rules_file: str = "RULES.json"
    skills_file: str = "SKILLS.md"
    lore_dir: str = "docs/lore"
    heuristic_store_dir: str = ".chronicler/heuristics"

    # Daemon state
    state_path: str = Field(default_factory=lambda: str(Path.home() / ".chronicler" / "state.json"))

    # Watcher tuning
    poll_interval_seconds: float = 30.0
    audit_batch_limit: int = 25

    # Git ninja
    git_remote: str = "origin"
    git_push: bool = False

    @field_validator("ledger_path", "state_path", "repo_root")
    @classmethod
    def expand_user_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("configured path must not be blank")
        return str(Path(value).expanduser())
