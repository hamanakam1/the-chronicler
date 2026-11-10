"""Runtime configuration for The Chronicler (env-overridable via CHRONICLER_*)."""

from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_ledger_path() -> str:
    """The current user's Taskrivet ledger."""
    return str(Path.home() / ".taskrivet" / "ledger.sqlite")


def _default_state_path() -> str:
    """The current user's Chronicler daemon state."""
    return str(Path.home() / ".chronicler" / "state.json")


def _default_repo_root() -> str:
    """The checkout the daemon was started in."""
    return str(Path.cwd())


class ChroniclerConfig(BaseSettings):
    """Headless daemon configuration."""

    model_config = SettingsConfigDict(env_prefix="CHRONICLER_", env_file=".env", extra="ignore")

    # Local LLM brain
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.8:latest"
    ollama_timeout_seconds: float = 120.0

    # EdgeRecord append-only ledger
    ledger_path: str = Field(default_factory=_default_ledger_path)

    # Target repository receiving hardened rules + lore docs.
    # Defaults to the checkout the daemon was started in.
    repo_root: str = Field(default_factory=_default_repo_root)

    # Paths written inside the target repo
    rules_file: str = "RULES.json"
    skills_file: str = "SKILLS.md"
    lore_dir: str = "docs/lore"

    # Daemon state
    state_path: str = Field(default_factory=_default_state_path)

    # Watcher tuning
    poll_interval_seconds: float = 30.0
    audit_batch_limit: int = 25

    # Git ninja
    git_remote: str = "origin"
    git_push: bool = True

    @field_validator("ledger_path", "repo_root", "state_path")
    @classmethod
    def _expand_user(cls, value: str) -> str:
        """Expand a leading ``~`` so shell-style paths work in the environment.

        Relative paths are left alone: they are resolved against the target
        repository by the committer, not against the daemon's cwd.
        """
        if value.startswith("~"):
            return str(Path(value).expanduser())
        return value
