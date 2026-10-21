"""Local LLM brain: Ollama client + prompt construction for The Chronicler."""

import json
from typing import Any

import httpx

from chronicler.config import ChroniclerConfig
from chronicler.errors import OllamaError
from chronicler.schemas import DocUpdatePayload
from chronicler.schemas.audit_log import ExecutionAuditLog
from chronicler.schemas.heuristic import ExtractedHeuristic
from chronicler.llm.prompts import DOC_SYNTHESIS_SYSTEM_PROMPT, build_doc_prompt


def _strip_json_fence(content: str) -> str:
    """Strip markdown code fences that local LLMs occasionally wrap around JSON."""
    text = content.strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    return text


class OllamaClient:
    """Async client for the local Ollama chat endpoint (OpenAI-compatible /api/chat)."""

    def __init__(self, config: ChroniclerConfig, transport: httpx.AsyncTransport | None = None) -> None:
        self.base_url = config.ollama_base_url.rstrip("/")
        self.model = config.ollama_model
        self.timeout = httpx.Timeout(config.ollama_timeout_seconds)
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout, transport=transport)

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def endpoint(self) -> str:
        return f"{self.base_url}/api/chat"

    async def ping(self) -> bool:
        """Cheap liveness probe against the local Ollama server."""
        try:
            response = await self._client.get("/api/tags")
            response.raise_for_status()
            return True
        except Exception:  # noqa: BLE001 - liveness probe must never raise
            return False

    async def ask(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        """Fire a prompt at the local LLM and return raw text content."""
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [],
            "stream": False,
            "format": "json" if json_mode else "auto",
        }
        if system is not None:
            payload["messages"].append({"role": "system", "content": system})
        payload["messages"].append({"role": "user", "content": prompt})

        try:
            response = await self._client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as exc:
            raise OllamaError(f"local Ollama request failed at {self.endpoint}: {exc}") from exc
        except ValueError as exc:
            raise OllamaError(f"local Ollama returned malformed response: {exc}") from exc

        message = data.get("message") or {}
        content = message.get("content") or ""
        if json_mode:
            content = _strip_json_fence(str(content))
        return content

    async def ask_for_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """Ask the local LLM for strict JSON and parse it into a dict."""
        content = await self.ask(prompt, system=system, json_mode=True)
        try:
            parsed = json.loads(content)
        except json.JSONDecodeError as exc:
            raise OllamaError(f"local LLM returned non-JSON output: {content[:200]}") from exc
        if not isinstance(parsed, dict):
            raise OllamaError("local LLM JSON response was not an object")
        return parsed

    async def synthesize_document(self, heuristic: ExtractedHeuristic, audit: ExecutionAuditLog) -> DocUpdatePayload:
        """Synthesize a lore doc payload from a learned heuristic + raw audit."""
        prompt = build_doc_prompt(heuristic, audit)
        data = await self.ask_for_json(prompt, system=DOC_SYNTHESIS_SYSTEM_PROMPT)
        payload = DocUpdatePayload.model_validate(
            {
                "payload_id": f"doc-{heuristic.heuristic_id}",
                "title": str(data.get("title") or f"Chronicler Lore: {heuristic.failure_category}"),
                "summary": str(data.get("summary") or heuristic.insight),
                "format": data.get("format") or "markdown",
                "content_markdown": str(data.get("content_markdown") or ""),
                "target_paths": [f"docs/lore/{heuristic.heuristic_id}.md"],
                "heuristic_ids": [heuristic.heuristic_id],
            }
        )
        return payload
