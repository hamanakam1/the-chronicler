"""Runtime configuration for The Chronicler (env-overridable via CHRONICLER_*)."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class ChroniclerConfig(BaseSettings):
    """Headless daemon configuration."""

    model_config = SettingsConfigDict(env_prefix="CHRONICLER_", env_file=".env", extra="ignore")

    # Local LLM brain
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3.8:latest"
    ollama_timeout_seconds: float = 120.0

    # EdgeRecord append-only ledger
    ledger_path: str = "/Users/michaelhamanaka/.taskrivet/ledger.sqlite"

    # Target repository receiving hardened rules + lore docs
    repo_root: str = "/Users/michaelhamanaka/Projects/taskrivet"
    rules_file: str = "RULES.json"
    skills_file: str = "SKILLS.md"
    lore_dir: str = "docs/lore"
    heuristic_store_dir: str = ".chronicler/heuristics"

    # Daemon state
    state_path: str = "/Users/michaelhamanaka/.chronicler/state.json"

    # Watcher tuning
    poll_interval_seconds: float = 30.0
    audit_batch_limit: int = 25

    # Git ninja
    git_remote: str = "origin"
    git_push: bool = True
