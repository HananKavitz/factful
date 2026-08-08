from __future__ import annotations

import json
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
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"name":"x"}'}}]})

    _client(handler).chat_completion(prompt="hello", schema=Dummy)

    assert captured["auth"] == "Bearer k"
    assert captured["body"]["model"] == "m"
    assert captured["body"]["messages"] == [{"role": "user", "content": "hello"}]
    assert captured["body"]["response_format"] == {"type": "json_object"}


def test_malformed_json_raises() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "not json"}}]})

    with pytest.raises(ValueError, match="malformed"):
        _client(handler).chat_completion(prompt="p", schema=Dummy)


def test_http_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    with pytest.raises(httpx.HTTPStatusError):
        _client(handler).chat_completion(prompt="p", schema=Dummy)
