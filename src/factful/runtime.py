"""Shared factory for pipeline runtime dependencies (CLI and web app)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from factful.agents.fetch import Fetcher, HttpxFetcher
from factful.agents.search import Searcher, TavilySearcher
from factful.config import Settings, load_settings
from factful.llm import ModelRouter, OpenRouterClient
from factful.pipeline import PipelineClients


@dataclass(frozen=True)
class PipelineRuntime:
    settings: Settings
    searcher: Searcher
    fetcher: Fetcher
    clients: PipelineClients


def build_runtime(env: dict[str, str] | None = None) -> PipelineRuntime:
    env = env if env is not None else dict(os.environ)
    api_key = env.get("LLM_API_KEY")
    if not api_key:
        raise RuntimeError("LLM_API_KEY is not set; cannot run article generation")
    tavily_key = env.get("TAVILY_API_KEY")
    if not tavily_key:
        raise RuntimeError("TAVILY_API_KEY is not set; cannot run article generation")
    settings = load_settings()
    router = ModelRouter(settings, env=env)
    base_url = settings.llm.base_url
    clients = PipelineClients(
        gather=OpenRouterClient(model=router.resolve("gather"), api_key=api_key, base_url=base_url),
        writer=OpenRouterClient(model=router.resolve("writer"), api_key=api_key, base_url=base_url),
        factcheck=OpenRouterClient(
            model=router.resolve("factcheck"), api_key=api_key, base_url=base_url
        ),
        critic=OpenRouterClient(model=router.resolve("critic"), api_key=api_key, base_url=base_url),
    )
    return PipelineRuntime(
        settings=settings,
        searcher=TavilySearcher(api_key=tavily_key, days=settings.gather.search_days),
        fetcher=HttpxFetcher(),
        clients=clients,
    )
