from __future__ import annotations

import logging
from typing import Protocol

import httpx
from pydantic import BaseModel

TAVILY_SEARCH_URL = "https://api.tavily.com/search"

logger = logging.getLogger(__name__)


class SearchResult(BaseModel):
    url: str
    title: str


class Searcher(Protocol):
    def search(self, query: str) -> list[SearchResult]: ...


class TavilySearcher:
    def __init__(
        self,
        api_key: str,
        *,
        max_results: int = 5,
        search_depth: str = "advanced",
        timeout: float = 30.0,
        _client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_results = max_results
        self._search_depth = search_depth
        self._client = _client or httpx.Client(timeout=timeout)

    def search(self, query: str) -> list[SearchResult]:
        try:
            response = self._client.post(
                TAVILY_SEARCH_URL,
                json={
                    "api_key": self._api_key,
                    "query": query,
                    "search_depth": self._search_depth,
                    "max_results": self._max_results,
                },
            )
            response.raise_for_status()
        except httpx.HTTPError as exc:
            if isinstance(exc, httpx.TimeoutException):
                logger.info("Tavily search timed out for query %r", query)
            elif isinstance(exc, httpx.HTTPStatusError):
                logger.info(
                    "Tavily search failed (status %d) for query %r",
                    exc.response.status_code,
                    query,
                )
            else:
                logger.info("Tavily search failed for query %r", query)
            raise
        data = response.json()
        results = data.get("results") or []
        return [SearchResult(url=item["url"], title=item.get("title") or "") for item in results]
