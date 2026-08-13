from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from pydantic import BaseModel

from factful.llm.client import OpenRouterClient


class Dummy(BaseModel):
    name: str


def _client(handler: Callable[[httpx.Request], httpx.Response]) -> OpenRouterClient:
    return OpenRouterClient(
        model="m",
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
        _client=httpx.Client(transport=httpx.MockTransport(handler)),
    )


def _json_response() -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    return handler


def test_chat_completion_returns_validated_model() -> None:
    client = _client(_json_response())
    out = client.chat_completion(prompt="p", schema=Dummy)
    assert isinstance(out, Dummy)
    assert out.name == "x"


def test_builds_expected_request_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        captured["auth"] = request.headers.get("authorization")
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    _client(handler).chat_completion(prompt="hello", schema=Dummy)

    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "m"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_uses_full_endpoint_when_base_url_lacks_path() -> None:
    captured: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    client = OpenRouterClient(
        model="m",
        api_key="k",
        base_url="https://openrouter.ai/api/v1",
        _client=httpx.Client(transport=httpx.MockTransport(handler)),
    )
    client.chat_completion(prompt="p", schema=Dummy)
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"


def test_parses_markdown_fenced_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"choices": [{"message": {"content": '```json\n{"name":"x"}\n```'}}]},
        )

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"


def test_malformed_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(ValueError, match="malformed"):
        _client(handler).chat_completion(prompt="p", schema=Dummy)


def test_retries_then_succeeds_on_empty_body() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, text="")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    assert len(calls) == 2


def test_empty_body_raises_clear_error_after_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, text="")

    with pytest.raises(ValueError, match="unusable response"):
        _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert len(calls) == 3


def test_retries_on_read_timeout_then_succeeds() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    assert len(calls) == 2


def test_persistent_transport_error_raises_after_retries() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(httpx.ReadTimeout):
        _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert len(calls) == 3


def test_retries_when_model_echoes_schema() -> None:
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"content": '{"properties": {"status": {"type": "string"}}}'}}
                    ]
                },
            )
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    assert len(calls) == 2


def test_http_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).chat_completion(prompt="p", schema=Dummy)


def test_client_error_reports_provider_body() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400,
            json={"error": {"message": "context_length_exceeded: prompt too long"}},
        )

    with pytest.raises(ValueError, match="context_length_exceeded"):
        _client(handler).chat_completion(prompt="p", schema=Dummy)


def test_logs_timeout_retry_then_succeeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="factful.llm.client")
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            raise httpx.ReadTimeout("timed out", request=request)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    messages = [record.message for record in caplog.records]
    assert any("LLM request timed out, retrying (1/3)" in m for m in messages)


def test_logs_timeout_failure_after_retries_exhausted(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO, logger="factful.llm.client")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(httpx.ReadTimeout):
        _client(handler).chat_completion(prompt="p", schema=Dummy)
    messages = [record.message for record in caplog.records]
    assert any("LLM request timed out, retries exhausted" in m for m in messages)


def test_logs_5xx_failure_retry(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="factful.llm.client")
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(500, text="boom")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    messages = [record.message for record in caplog.records]
    assert any("LLM request failed (status 500), retrying (1/3)" in m for m in messages)


def test_logs_4xx_rejection(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="factful.llm.client")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": {"message": "context_length_exceeded"}})

    with pytest.raises(ValueError, match="context_length_exceeded"):
        _client(handler).chat_completion(prompt="p", schema=Dummy)
    messages = [record.message for record in caplog.records]
    assert any("LLM API rejected the request" in m for m in messages)


def test_logs_unusable_response_retry(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="factful.llm.client")
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(200, text="")
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    out = _client(handler).chat_completion(prompt="p", schema=Dummy)
    assert out.name == "x"
    messages = [record.message for record in caplog.records]
    assert any("LLM returned an unusable response, retrying (1/3)" in m for m in messages)
