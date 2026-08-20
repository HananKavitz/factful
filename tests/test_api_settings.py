from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from factful.api import settings as settings_api
from factful.api.app import create_app
from factful.config import LLM, Settings
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile


def make_profile(name: str) -> StyleProfile:
    return StyleProfile(
        name=name,
        metrics=StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0),
        extraction=StyleExtraction(voice="wry", tone="dry", hook_patterns=["question"]),
    )


def make_client() -> TestClient:
    app = create_app(
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "AUTH_MODE": "mock",
            "SESSION_SECRET": "test-secret",
            "LLM_API_KEY": "k",
            "TAVILY_API_KEY": "t",
        }
    )
    app.state.style_extractor = lambda samples, name: make_profile(name)
    return TestClient(app)


def login(client: TestClient, email: str = "alice@example.com") -> None:
    response = client.post("/api/auth/mock", json={"email": email})
    assert response.status_code == 200


@pytest.fixture()
def client() -> TestClient:
    return make_client()


def test_get_settings_requires_auth(client: TestClient) -> None:
    assert client.get("/api/settings").status_code == 401


def test_get_settings_returns_null_when_unset(client: TestClient) -> None:
    login(client)
    response = client.get("/api/settings")
    assert response.status_code == 200
    assert response.json()["style"] is None


def test_analyze_and_save_persists_profile(client: TestClient) -> None:
    login(client)
    response = client.post("/api/settings/style", json={"samples": "Sample body here."})
    assert response.status_code == 200
    body = response.json()
    assert body["style"]["name"] == "my style"
    assert body["style"]["extraction"]["voice"] == "wry"

    fetched = client.get("/api/settings")
    assert fetched.json()["style"]["name"] == "my style"


def test_analyze_requires_valid_body(client: TestClient) -> None:
    login(client)
    assert client.post("/api/settings/style", json={}).status_code == 422
    assert client.post("/api/settings/style", json={"samples": ""}).status_code == 422


def test_clear_style_removes_profile(client: TestClient) -> None:
    login(client)
    client.post("/api/settings/style", json={"samples": "Sample body here."})
    response = client.delete("/api/settings/style")
    assert response.status_code == 204
    assert client.get("/api/settings").json()["style"] is None


def test_analyze_propagates_extractor_failure(client: TestClient) -> None:
    login(client)

    def boom(samples: list[str], name: str) -> StyleProfile:
        raise RuntimeError("LLM down")

    client.app.state.style_extractor = boom
    response = client.post("/api/settings/style", json={"samples": "x"})
    assert response.status_code == 502
    assert "LLM down" in response.json()["detail"]


def test_build_style_extractor_resolves_style_model(monkeypatch) -> None:
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        settings_api,
        "OpenRouterClient",
        lambda **kwargs: captured.update(kwargs) or object(),
    )
    monkeypatch.setattr(
        settings_api,
        "extract_style",
        lambda samples, name, client: (
            captured.update(samples=samples, name=name) or make_profile(name)
        ),
    )
    settings = Settings(llm=LLM(models={"style": "test/style-model"}))
    extractor = settings_api.build_style_extractor(settings=settings, env={"LLM_API_KEY": "k"})

    profile = extractor(["Sample body here."], "voice")

    assert profile.name == "voice"
    assert captured["model"] == "test/style-model"
    assert captured["api_key"] == "k"
    assert captured["samples"] == ["Sample body here."]


def test_build_style_extractor_requires_api_key() -> None:
    settings = Settings(llm=LLM(models={"style": "test/style-model"}))
    extractor = settings_api.build_style_extractor(settings=settings, env={})
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        extractor(["Sample body here."], "voice")
