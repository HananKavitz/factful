from __future__ import annotations

from typing import Protocol

import httpx
from pydantic import BaseModel

TAVILY_SEARCH_URL = "https://api.tavily.com/search"


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
        search_depth: str = "high",
        timeout: float = 30.0,
        _client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._max_results = max_results
        self._search_depth = search_depth
        self._client = _client or httpx.Client(timeout=timeout)

    def search(self, query: str) -> list[SearchResult]:
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
        data = response.json()
        results = data.get("results") or []
        return [SearchResult(url=item["url"], title=item.get("title") or "") for item in results]
