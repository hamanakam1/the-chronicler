"""Portable settings use the current user's home and explicit write targets."""

import os
from pathlib import Path

import pytest
from pydantic import ValidationError

from chronicler.config import ChroniclerConfig


@pytest.fixture(autouse=True)
def isolated_settings(monkeypatch, tmp_path):
    for key in os.environ:
        if key.startswith("CHRONICLER_"):
            monkeypatch.delenv(key)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def test_defaults_are_computed_for_each_user_without_creating_paths(monkeypatch, tmp_path):
    for name in ("first-user", "second-user"):
        home = tmp_path / name
        monkeypatch.setattr(Path, "home", lambda home=home: home)
        config = ChroniclerConfig()
        assert config.ledger_path == str(home / ".taskrivet" / "ledger.sqlite")
        assert config.state_path == str(home / ".chronicler" / "state.json")
        assert config.repo_root is None
        assert config.git_push is False
        assert not home.exists()


@pytest.mark.parametrize("field", ["ledger_path", "state_path", "repo_root"])
def test_configured_user_paths_expand_tilde(field, monkeypatch, tmp_path):
    monkeypatch.setenv(f"CHRONICLER_{field.upper()}", "~/example/path")
    config = ChroniclerConfig()
    assert getattr(config, field) == str(tmp_path / "home" / "example" / "path")


@pytest.mark.parametrize("field", ["ledger_path", "state_path", "repo_root"])
@pytest.mark.parametrize("value", ["", " ", "\t\n"])
def test_explicit_blank_paths_are_rejected(field, value):
    with pytest.raises(ValidationError, match="must not be blank"):
        ChroniclerConfig(**{field: value})


def test_explicit_paths_and_push_opt_in_are_preserved(tmp_path):
    config = ChroniclerConfig(
        ledger_path=str(tmp_path / "audit.sqlite"),
        state_path="local-state.json",
        repo_root="example-repo",
        git_push=True,
    )
    assert config.ledger_path == str(tmp_path / "audit.sqlite")
    assert config.state_path == "local-state.json"
    assert config.repo_root == "example-repo"
    assert config.git_push is True
    assert config.ollama_base_url == "http://localhost:11434"
    assert config.ollama_model == "qwen3.8:latest"


def test_dotenv_paths_and_explicit_environment_precedence(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text(
        'CHRONICLER_REPO_ROOT="~/example-repo"\nCHRONICLER_GIT_PUSH=true\n', encoding="utf-8",
    )
    from_file = ChroniclerConfig()
    assert from_file.repo_root == str(tmp_path / "home" / "example-repo")
    assert from_file.git_push is True
    monkeypatch.setenv("CHRONICLER_GIT_PUSH", "false")
    assert ChroniclerConfig().git_push is False


def test_output_paths_remain_repo_relative():
    config = ChroniclerConfig()
    assert (config.rules_file, config.skills_file, config.lore_dir, config.heuristic_store_dir) == (
        "RULES.json", "SKILLS.md", "docs/lore", ".chronicler/heuristics",
    )
