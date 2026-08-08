from __future__ import annotations

import json
from typing import Protocol

import httpx
from pydantic import BaseModel

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
JSON_FALLBACK = "json_object"


class ChatClient(Protocol):
    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel: ...


class OpenRouterClient:
    """POST an OpenAI-compatible chat completion and validate a JSON payload."""

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = OPENROUTER_URL,
        timeout: float = 60.0,
        _client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = base_url
        self._timeout = timeout
        self._client = _client

    def chat_completion(self, *, prompt: str, schema: type[BaseModel]) -> BaseModel:
        client = self._client or httpx.Client(timeout=self._timeout)
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
        raw = response.json()["choices"][0]["message"]["content"]
        return _parse_and_validate(raw, schema)


def _parse_and_validate(raw: str, schema: type[BaseModel]) -> BaseModel:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("LLM returned malformed JSON") from exc
    return schema.model_validate(data)
