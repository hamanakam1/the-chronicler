"""Only completed, well-formed model responses may reach generated outputs."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from chronicler.config import ChroniclerConfig
from chronicler.errors import OllamaError
from chronicler.llm.client import OllamaClient
from conftest import FakeCommitter, FakeLedgerReader, build_brain


def _client(payload: Any) -> OllamaClient:
    return OllamaClient(
        ChroniclerConfig(),
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=json.dumps(payload))),
    )


def _ask(payload: Any, *, json_mode: bool = False) -> str:
    async def run() -> str:
        client = _client(payload)
        try:
            return await client.ask("synthetic prompt", json_mode=json_mode)
        finally:
            await client.close()

    return asyncio.run(run())


@pytest.mark.parametrize("payload", [None, [], "synthetic malformed envelope", 3, True])
def test_ask_rejects_nonobject_response_envelopes(payload: Any) -> None:
    with pytest.raises(OllamaError, match="response.*object"):
        _ask(payload)


@pytest.mark.parametrize("done", [False, None, 0, 1, "true", [], {}])
def test_ask_requires_boolean_completion_marker(done: Any) -> None:
    with pytest.raises(OllamaError, match="completed"):
        _ask({"done": done, "message": {"content": '{"insight": "synthetic partial"}'}})


def test_ask_rejects_missing_completion_marker() -> None:
    with pytest.raises(OllamaError, match="completed"):
        _ask({"message": {"content": '{"insight": "synthetic partial"}'}})


@pytest.mark.parametrize("error", ["synthetic generation failure", None, False, ""])
def test_error_envelope_cannot_supply_plausible_json(error: Any) -> None:
    async def run() -> None:
        client = _client({
            "error": error, "done": True,
            "message": {"content": '{"insight": "synthetic partial", "generalized_rule": "synthetic rule"}'},
        })
        try:
            with pytest.raises(OllamaError, match="error response"):
                await client.ask_for_json("synthetic prompt")
        finally:
            await client.close()

    asyncio.run(run())


@pytest.mark.parametrize("message", [None, [], "synthetic malformed message", 3, False])
def test_ask_rejects_nonobject_messages(message: Any) -> None:
    with pytest.raises(OllamaError, match="message.*object"):
        _ask({"done": True, "message": message})


def test_ask_rejects_missing_message() -> None:
    with pytest.raises(OllamaError, match="message.*object"):
        _ask({"done": True})


@pytest.mark.parametrize("content", [None, [], {"synthetic": "content"}, 3, False])
@pytest.mark.parametrize("json_mode", [False, True])
def test_ask_never_coerces_nonstring_content(content: Any, json_mode: bool) -> None:
    with pytest.raises(OllamaError, match="content.*string"):
        _ask({"done": True, "message": {"content": content}}, json_mode=json_mode)


def test_ask_rejects_missing_content() -> None:
    with pytest.raises(OllamaError, match="content.*string"):
        _ask({"done": True, "message": {}})


@pytest.mark.parametrize("content", ["synthetic answer", ""])
def test_completed_plain_text_is_preserved(content: str) -> None:
    assert _ask({"done": True, "message": {"content": content}}) == content


@pytest.mark.parametrize("content", ['{"synthetic": "answer"}', '```json\n{"synthetic": "answer"}\n```'])
def test_completed_json_and_fenced_json_are_preserved(content: str) -> None:
    async def run() -> dict[str, Any]:
        client = _client({"done": True, "message": {"content": content}})
        try:
            return await client.ask_for_json("synthetic prompt")
        finally:
            await client.close()

    assert asyncio.run(run()) == {"synthetic": "answer"}


@pytest.mark.parametrize("content", ["", "[]", "null"])
def test_json_caller_still_requires_a_json_object(content: str) -> None:
    async def run() -> None:
        client = _client({"done": True, "message": {"content": content}})
        try:
            with pytest.raises(OllamaError):
                await client.ask_for_json("synthetic prompt")
        finally:
            await client.close()

    asyncio.run(run())


def test_incomplete_response_cannot_write_or_commit_generated_rules(make_audit) -> None:
    async def run() -> None:
        client = _client({
            "done": False,
            "message": {
                "content": '{"insight": "synthetic partial", "generalized_rule": "synthetic rule"}',
            },
        })
        committer = FakeCommitter()
        brain = build_brain(FakeLedgerReader([[make_audit()]]), llm=client, committer=committer)
        try:
            report = await brain.run_cycle()
        finally:
            await client.close()

        assert len(report.failed_audits) == 1
        assert report.failed_audits[0]["error_type"] == "OllamaError"
        assert report.heuristics == []
        assert report.written_paths == []
        assert report.receipts == []
        assert committer.writes == []
        assert committer.commit_calls == []

    asyncio.run(run())
