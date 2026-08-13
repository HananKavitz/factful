from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import BaseModel

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JSON_FALLBACK = "json_object"


def _chat_completions_endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url.rstrip('/')}/chat/completions"


class ChatClient(Protocol):
    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel: ...


class OpenRouterClient:
    """POST an OpenAI-compatible chat completion and validate a JSON payload."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = OPENROUTER_URL,
        timeout: float = 180.0,
        max_retries: int = 2,
        _client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = _chat_completions_endpoint(base_url)
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = _client

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        client = self._client or httpx.Client(timeout=self._timeout)
        attempts = self._max_retries + 1
        for attempt in range(attempts):
            try:
                response = client.post(
                    self._base_url,
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json={
                        "model": self._model,
                        "messages": [{"role": "user", "content": prompt}],
                        "response_format": {"type": JSON_FALLBACK},
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    raise ValueError(
                        f"LLM API rejected the request "
                        f"(status {exc.response.status_code}): {exc.response.text[:300]}"
                    ) from exc
                if attempt < attempts - 1:
                    continue
                raise
            except httpx.HTTPError:
                if attempt < attempts - 1:
                    continue
                raise
            try:
                raw = response.json()["choices"][0]["message"]["content"]
                if not raw.strip():
                    raise ValueError("LLM returned empty content")
            except (
                json.JSONDecodeError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
            ) as exc:
                if attempt < attempts - 1:
                    continue
                raise ValueError(
                    f"LLM returned an unusable response (status {response.status_code}): "
                    f"{response.text[:200]!r}"
                ) from exc
            try:
                return _parse_and_validate(raw, schema)
            except ValueError:
                if attempt < attempts - 1:
                    continue
                raise
        raise RuntimeError("unreachable")


def _strip_code_fences(raw: str) -> str:
    text = raw.strip()
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


def _parse_and_validate(raw: str, schema: type[BaseModel]) -> BaseModel:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        try:
            data = json.loads(_strip_code_fences(raw))
        except json.JSONDecodeError as exc:
            raise ValueError("LLM returned malformed JSON") from exc
    return schema.model_validate(data)
