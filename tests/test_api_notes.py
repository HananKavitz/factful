from __future__ import annotations

from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from factful.api.app import create_app
from factful.notes import NoteOutput, build_note_generator


def make_client():
    app = create_app(
        env={
            "DATABASE_URL": "sqlite:///:memory:",
            "AUTH_MODE": "mock",
            "SESSION_SECRET": "test-secret",
            "LLM_API_KEY": "k",
            "TAVILY_API_KEY": "t",
        }
    )
    return TestClient(app)


def login(client: TestClient, email: str = "alice@example.com") -> dict:
    response = client.post("/api/auth/mock", json={"email": email})
    assert response.status_code == 200
    return response.json()


@pytest.fixture()
def client() -> TestClient:
    return make_client()


def test_generate_note_requires_auth(client: TestClient) -> None:
    assert (
        client.post("/api/stories/1/note", json={"title": "T", "markdown": "Body."}).status_code
        == 401
    )


def test_generate_note_rejects_empty_body(client: TestClient) -> None:
    login(client)
    url = "/api/stories/1/note"
    assert client.post(url, json={"title": "", "markdown": ""}).status_code == 422
    assert client.post(url, json={"title": "T", "markdown": ""}).status_code == 422
    assert client.post(url, json={"title": "", "markdown": "Body."}).status_code == 422


def test_generate_note_invokes_note_generator(client: TestClient) -> None:
    captured: dict[str, object] = {}

    def fake_generator(title: str, markdown: str, instructions: str | None) -> str:
        captured["title"] = title
        captured["markdown"] = markdown
        return "Check out my latest! →"

    client.app.state.note_generator = fake_generator
    login(client)

    response = client.post(
        "/api/stories/1/note", json={"title": "My Story", "markdown": "# My Story\n\nBody content."}
    )
    assert response.status_code == 200
    assert response.json() == {"note": "Check out my latest! →"}
    assert captured["title"] == "My Story"
    assert captured["markdown"] == "# My Story\n\nBody content."


def test_generate_note_forwards_instructions(client: TestClient) -> None:
    captured: dict[str, object] = {}

    def fake_generator(title: str, markdown: str, instructions: str | None) -> str:
        captured["title"] = title
        captured["markdown"] = markdown
        captured["instructions"] = instructions
        return "Note."

    client.app.state.note_generator = fake_generator
    login(client)

    response = client.post(
        "/api/stories/1/note",
        json={
            "title": "My Story",
            "markdown": "# My Story\n\nBody content.",
            "instructions": "Keep it under 20 words.",
        },
    )
    assert response.status_code == 200
    assert captured["title"] == "My Story"
    assert captured["markdown"] == "# My Story\n\nBody content."
    assert captured["instructions"] == "Keep it under 20 words."


def test_generate_note_forwards_empty_instructions(client: TestClient) -> None:
    captured: dict[str, object] = {}

    def fake_generator(title: str, markdown: str, instructions: str | None) -> str:
        captured["instructions"] = instructions
        return "Note."

    client.app.state.note_generator = fake_generator
    login(client)

    response = client.post("/api/stories/1/note", json={"title": "My Story", "markdown": "# Body."})
    assert response.status_code == 200
    assert captured["instructions"] is None


def test_generate_note_propagates_generator_error(client: TestClient) -> None:
    def failing_generator(title: str, markdown: str, instructions: str | None) -> str:
        raise ValueError("LLM failed")

    client.app.state.note_generator = failing_generator
    login(client)

    response = client.post(
        "/api/stories/1/note", json={"title": "My Story", "markdown": "# My Story\n\nBody."}
    )
    assert response.status_code == 502
    assert "LLM failed" in response.json()["detail"]


def test_generate_note_unknown_story_not_needed(client: TestClient) -> None:
    """The endpoint doesn't need a valid story_id — it uses the provided title + markdown."""
    captured: dict[str, object] = {}

    def fake_generator(title: str, markdown: str, instructions: str | None) -> str:
        captured["title"] = title
        captured["markdown"] = markdown
        return "Note."

    client.app.state.note_generator = fake_generator
    login(client)

    response = client.post("/api/stories/999/note", json={"title": "T", "markdown": "Body."})
    assert response.status_code == 200
    assert response.json() == {"note": "Note."}
    assert captured["title"] == "T"
    assert captured["markdown"] == "Body."


def test_build_note_generator_formats_prompt_with_instructions(monkeypatch) -> None:
    """The real generator must build the prompt (catching placeholder mismatches)."""
    captured: dict[str, object] = {}

    class _Writer:
        def chat_completion(self, *, prompt: str, schema, **kwargs):
            captured["prompt"] = prompt
            return schema(note="Done.")

    monkeypatch.setattr(
        "factful.runtime.build_runtime",
        lambda _env: SimpleNamespace(clients=SimpleNamespace(writer=_Writer())),
    )

    generator = build_note_generator(env={"LLM_API_KEY": "k"})
    generator("My Title", "# Body", "Keep it under 20 words.")

    assert "Keep it under 20 words." in captured["prompt"]


def test_build_note_generator_omits_instructions_block_when_empty(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeWriter:
        def chat_completion(self, *, prompt: str, schema, **kwargs):
            captured["prompt"] = prompt
            return NoteOutput(note="Note")

    monkeypatch.setattr(
        "factful.runtime.build_runtime",
        lambda _env: SimpleNamespace(clients=SimpleNamespace(writer=FakeWriter())),
    )
    generator = build_note_generator(env={"LLM_API_KEY": "k"})
    generator("Title", "# Body")

    assert "additional instructions" not in captured["prompt"]
