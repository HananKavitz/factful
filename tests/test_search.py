from __future__ import annotations

import json
import logging
from collections.abc import Callable
from typing import Any

import httpx
import pytest

from factful.agents.search import SearchResult, TavilySearcher

TAVILY_URL = "https://api.tavily.com/search"


def _handler(results: list[dict[str, Any]]) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": results}, request=request)

    return handler


def _searcher(
    handler: Callable[[httpx.Request], httpx.Response],
    **kwargs: Any,
) -> TavilySearcher:
    return TavilySearcher(
        api_key="tavily-secret",
        max_results=5,
        _client=httpx.Client(transport=httpx.MockTransport(handler)),
        **kwargs,
    )


def test_search_returns_parsed_results() -> None:
    results = [
        {"url": "https://a.example/report", "title": "Annual Report"},
        {"url": "https://b.example/data", "title": "Data Sheet"},
    ]
    searcher = _searcher(_handler(results))
    out = searcher.search("query")
    assert out == [
        SearchResult(url="https://a.example/report", title="Annual Report"),
        SearchResult(url="https://b.example/data", title="Data Sheet"),
    ]


def test_search_posts_expected_body() -> None:
    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = request.read()
        return httpx.Response(200, json={"results": []}, request=request)

    _searcher(handler).search("climate figures")

    body = json.loads(captured["body"])
    assert body["api_key"] == "tavily-secret"
    assert body["query"] == "climate figures"
    assert body["search_depth"] == "advanced"
    assert body["max_results"] == 5


def test_search_handles_null_results() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"results": None}, request=request)

    assert _searcher(handler).search("climate change") == []


def test_http_error_propagates() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom", request=request)

    with pytest.raises(httpx.HTTPStatusError):
        _searcher(handler).search("climate change")


def test_logs_timeout_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="factful.agents.search")

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(httpx.ReadTimeout):
        _searcher(handler).search("climate change")
    messages = [record.message for record in caplog.records]
    assert any("Tavily search timed out" in m for m in messages)


def test_logs_http_error_failure(caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.INFO, logger="factful.agents.search")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom", request=request)

    with pytest.raises(httpx.HTTPStatusError):
        _searcher(handler).search("climate change")
    messages = [record.message for record in caplog.records]
    assert any("Tavily search failed (status 500)" in m for m in messages)
