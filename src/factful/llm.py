from __future__ import annotations

from dataclasses import dataclass

from factful.config import Settings

API_KEY_ENV = "LLM_API_KEY"


@dataclass(frozen=True)
class ModelRouter:
    settings: Settings
    env: dict[str, str] | None = None

    def resolve(self, agent: str) -> str:
        try:
            return self.settings.llm.models[agent]
        except KeyError as exc:
            raise KeyError(f"no model configured for agent {agent!r}") from exc

    def api_key(self) -> str:
        env = self.env or {}
        try:
            return env[API_KEY_ENV]
        except KeyError as exc:
            raise KeyError(f"{API_KEY_ENV} is not set") from exc
