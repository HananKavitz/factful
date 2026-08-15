from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable
from typing import Protocol

import httpx
from pydantic import BaseModel

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"

logger = logging.getLogger(__name__)


def _retry_suffix(attempt: int, attempts: int) -> str:
    if attempt < attempts - 1:
        return f", retrying ({attempt + 1}/{attempts})"
    return ", retries exhausted"


def _chat_completions_endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    return f"{base_url.rstrip('/')}/chat/completions"


def _response_format(schema: type[BaseModel]) -> dict[str, object]:
    return {
        "type": "json_schema",
        "json_schema": {
            "name": schema.__name__,
            "schema": schema.model_json_schema(),
        },
    }


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
        backoff_base: float = 1.0,
        backoff_cap: float = 30.0,
        _client: httpx.Client | None = None,
        _sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._model = model
        self._api_key = api_key
        self._base_url = _chat_completions_endpoint(base_url)
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap
        self._client = _client
        self._sleep = _sleep

    def _backoff_delay(self, attempt: int) -> float:
        raw: float = self._backoff_base * float(2**attempt)
        return min(raw, self._backoff_cap)

    def _wait_before_retry(self, attempt: int) -> None:
        if attempt >= self._max_retries:
            return
        self._sleep(self._backoff_delay(attempt))

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
                        "response_format": _response_format(schema),
                    },
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                if 400 <= exc.response.status_code < 500:
                    logger.info(
                        "LLM API rejected the request (status %d): %s",
                        exc.response.status_code,
                        exc.response.text[:300],
                    )
                    raise ValueError(
                        f"LLM API rejected the request "
                        f"(status {exc.response.status_code}): {exc.response.text[:300]}"
                    ) from exc
                logger.info(
                    "LLM request failed (status %d)%s",
                    exc.response.status_code,
                    _retry_suffix(attempt, attempts),
                )
                if attempt < attempts - 1:
                    self._wait_before_retry(attempt)
                    continue
                raise
            except httpx.HTTPError as exc:
                if isinstance(exc, httpx.TimeoutException):
                    kind = "timed out"
                else:
                    kind = "failed"
                logger.info("LLM request %s%s", kind, _retry_suffix(attempt, attempts))
                if attempt < attempts - 1:
                    self._wait_before_retry(attempt)
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
                logger.info(
                    "LLM returned an unusable response%s",
                    _retry_suffix(attempt, attempts),
                )
                if attempt < attempts - 1:
                    self._wait_before_retry(attempt)
                    continue
                raise ValueError(
                    f"LLM returned an unusable response (status {response.status_code}): "
                    f"{response.text[:200]!r}"
                ) from exc
            try:
                return _parse_and_validate(raw, schema)
            except ValueError as exc:
                logger.info(
                    "LLM response failed schema validation%s: %s (content: %r)",
                    _retry_suffix(attempt, attempts),
                    str(exc)[:300],
                    raw[:200],
                )
                if attempt < attempts - 1:
                    self._wait_before_retry(attempt)
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
