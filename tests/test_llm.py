"""Tests for The Chronicler's local LLM brain: prompts and Ollama client."""

import asyncio
import json
from typing import Any

import httpx
import pytest

from chronicler.config import ChroniclerConfig
from chronicler.errors import OllamaError
from chronicler.llm.client import OllamaClient
from chronicler.llm.prompts import (
    THE_PERMANENT_FIX_QUESTION,
    build_doc_prompt,
    build_extraction_prompt,
)
from chronicler.schemas import DocFormat, DocUpdatePayload


def test_extraction_prompt_contains_canonical_question(make_audit) -> None:
    audit = make_audit(task_id="task-42", category="dns", fingerprint="sha256:cafe", summary="NXDOMAIN on resolver")
    prompt = build_extraction_prompt(audit)
    assert THE_PERMANENT_FIX_QUESTION in prompt
    assert "task-42" in prompt
    assert "dns" in prompt
    assert "NXDOMAIN on resolver" in prompt


def test_doc_prompt_includes_heuristic_and_battle_scar(make_audit) -> None:
    from chronicler.schemas import ExtractedHeuristic

    heuristic = ExtractedHeuristic(
        heuristic_id="heur-abc123",
        source_fingerprint="sha256:x",
        task_id="task-1",
        failure_category="network_config",
        insight="The bot guessed the gateway.",
        generalized_rule="Always resolve the gateway from the compose file.",
    )
    audit = make_audit(summary="Could not resolve host gateway")
    prompt = build_doc_prompt(heuristic, audit)
    assert "Always resolve the gateway from the compose file." in prompt
    assert "Could not resolve host gateway" in prompt


def test_ollama_client_ask_for_json_uses_mock_transport() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        captured["url"] = str(request.url)
        captured["json"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": "qwen3.8:latest",
                "message": {"role": "assistant", "content": '{"insight": "gw missing", "generalized_rule": "use compose"}'},
                "done": True,
            },
        )

    client = OllamaClient(ChroniclerConfig(), transport=httpx.MockTransport(handler))
    payload = asyncio.run(client.ask_for_json("What did the bots mess up, and what's the permanent fix?"))
    assert payload["insight"] == "gw missing"
    assert captured["json"]["format"] == "json"
    assert captured["json"]["model"] == "qwen3.8:latest"
    assert captured["url"].endswith("/api/chat")


def test_ollama_client_error_wraps_http_failure() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = OllamaClient(ChroniclerConfig(), transport=httpx.MockTransport(handler))

    async def _probe() -> bool:
        return await client.ping()

    assert asyncio.run(_probe()) is False


def test_ollama_client_ask_raises_on_http_failure() -> None:

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = OllamaClient(ChroniclerConfig(), transport=httpx.MockTransport(handler))

    async def _ask() -> str:
        return await client.ask("hello", system="sys", json_mode=False)

    with pytest.raises(OllamaError):
        asyncio.run(_ask())


def test_doc_update_payload_from_llm_is_valid() -> None:
    payload = DocUpdatePayload.model_validate(
        {
            "payload_id": "doc-heur-abc123",
            "title": "Chronicler Lore: network_config",
            "summary": "The bot guessed the gateway.",
            "format": "markdown",
            "content_markdown": "# Lore",
            "heuristic_ids": ["heur-abc123"],
        }
    )
    assert payload.format is DocFormat.MARKDOWN
