import pytest

from factful.config import Settings
from factful.llm import ModelRouter

MODELS = {
    "gather": "g:model",
    "writer": "w:model",
    "factcheck": "f:model",
    "critic": "c:model",
}


def router(env: dict[str, str] | None = None) -> ModelRouter:
    return ModelRouter(Settings(llm={"models": MODELS}), env=env)


def test_route_writer() -> None:
    assert router().resolve("writer") == "w:model"


def test_missing_env_raises() -> None:
    with pytest.raises(KeyError):
        router(env={}).api_key()


def test_api_key_from_injected_env() -> None:
    assert router(env={"LLM_API_KEY": "secret"}).api_key() == "secret"


def test_unknown_agent_raises() -> None:
    with pytest.raises(KeyError):
        router().resolve("nope")


def test_no_os_env_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "host-secret")
    assert router(env={"LLM_API_KEY": "injected"}).api_key() == "injected"
    with pytest.raises(KeyError):
        router(env={}).api_key()
