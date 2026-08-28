from __future__ import annotations

import threading
import time

import pytest
from fastapi.testclient import TestClient

from factful.api.app import create_app
from factful.generation import GenerationRequest
from factful.models import Story, User
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile


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
    app.state.generation_runner = make_runner(app)
    app.state.editor = make_editor()
    return TestClient(app)


def make_runner(app):
    def runner(record, request: GenerationRequest) -> None:
        with app.state.sessions() as db:
            story = Story(
                user_id=request.user_id,
                prompt=request.prompt,
                angle=request.angle,
                instructions=request.instructions,
                title=f"About {request.prompt}",
                markdown=f"# About {request.prompt}\n\nBody.",
                score=90.0,
                report='{"decision": "publish"}',
            )
            db.add(story)
            db.commit()
            db.refresh(story)
            record.set_stage("writing draft")
            record.set_story_id(story.id)

    return runner


def make_editor():
    def edit(markdown: str, prompt: str, style=None, temperature=None, top_p=None) -> str:
        return markdown.replace("Body.", f"Body. (edited: {prompt})")

    return edit


def make_user_profile() -> StyleProfile:
    return StyleProfile(
        name="my-voice",
        metrics=StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0),
        extraction=StyleExtraction(voice="wry", tone="dry"),
    )


def set_style(client: TestClient, email: str = "alice@example.com") -> StyleProfile:
    profile = make_user_profile()
    with client.app.state.sessions() as db:
        user = db.query(User).filter_by(email=email).one()
        user.style_profile = profile.model_dump_json()
        db.commit()
    return profile


def set_sampling(
    client: TestClient, *, temperature: float, top_p: float, email: str = "alice@example.com"
) -> None:
    with client.app.state.sessions() as db:
        user = db.query(User).filter_by(email=email).one()
        user.temperature = temperature
        user.top_p = top_p
        db.commit()


def login(client: TestClient, email: str = "alice@example.com") -> dict:
    response = client.post("/api/auth/mock", json={"email": email})
    assert response.status_code == 200
    return response.json()


def wait_for_job(client: TestClient, job_id: str, timeout: float = 5.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        response = client.get(f"/api/jobs/{job_id}")
        assert response.status_code == 200
        body = response.json()
        if body["status"] in ("done", "error"):
            return body
        time.sleep(0.01)
    raise AssertionError(f"job {job_id} did not finish within {timeout}s")


@pytest.fixture()
def client() -> TestClient:
    return make_client()


def test_list_stories_requires_auth(client: TestClient) -> None:
    assert client.get("/api/stories").status_code == 401


def test_create_story_kicks_off_job(client: TestClient) -> None:
    login(client)
    response = client.post("/api/stories", json={"prompt": "Chip demand", "instructions": "short"})
    assert response.status_code == 202
    body = response.json()
    assert body["status"] in ("queued", "running")
    assert body["stage"] is None

    done = wait_for_job(client, body["job_id"])
    assert done["status"] == "done"
    assert done["story_id"] is not None
    assert done["progress"] == 100

    story = client.get(f"/api/stories/{done['story_id']}").json()
    assert story["prompt"] == "Chip demand"
    assert story["instructions"] == "short"
    assert story["markdown"].startswith("# About Chip demand")


def test_list_stories_shows_only_owned(client: TestClient) -> None:
    alice = login(client)
    assert alice["email"] == "alice@example.com"
    client.post("/api/stories", json={"prompt": "Chip demand"})
    client.post("/api/stories", json={"prompt": "Solar cells"})

    bob = make_client()
    login(bob)
    assert bob.get("/api/stories").json() == []

    mine = client.get("/api/stories").json()
    assert [s["prompt"] for s in mine] == ["Solar cells", "Chip demand"]


def test_get_story_is_owner_scoped(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    other = make_client()
    login(other, email="bob@example.com")
    assert other.get(f"/api/stories/{story_id}").status_code == 404


def test_update_story_title_and_markdown(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    response = client.put(
        f"/api/stories/{story_id}",
        json={"title": "New title", "markdown": "# New title\n\nEdited."},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["title"] == "New title"
    assert body["markdown"] == "# New title\n\nEdited."

    fetched = client.get(f"/api/stories/{story_id}").json()
    assert fetched["title"] == "New title"


def test_update_unknown_story_404(client: TestClient) -> None:
    login(client)
    assert client.put("/api/stories/999", json={"title": "x"}).status_code == 404


def test_job_status_is_owner_scoped(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()

    other = make_client()
    login(other, email="bob@example.com")
    assert other.get(f"/api/jobs/{job['job_id']}").status_code == 404


def test_unknown_job_404(client: TestClient) -> None:
    login(client)
    assert client.get("/api/jobs/does-not-exist").status_code == 404


def test_cancel_job_marks_cancelled(client: TestClient) -> None:
    login(client)
    started = threading.Event()
    release = threading.Event()

    def blocking_runner(record, request) -> None:
        started.set()
        release.wait(timeout=5)
        record.set_stage("writing draft")
        record.set_story_id(99)

    client.app.state.generation_runner = blocking_runner
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    assert started.wait(timeout=5)

    response = client.post(f"/api/jobs/{job['job_id']}/cancel")
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"

    release.set()
    time.sleep(0.05)
    assert client.get(f"/api/jobs/{job['job_id']}").json()["status"] == "cancelled"


def test_cancel_job_requires_auth(client: TestClient) -> None:
    assert client.post("/api/jobs/whatever/cancel").status_code == 401


def test_cancel_job_is_owner_scoped(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()

    other = make_client()
    login(other, email="bob@example.com")
    assert other.post(f"/api/jobs/{job['job_id']}/cancel").status_code == 404


def test_cancel_unknown_job_404(client: TestClient) -> None:
    login(client)
    assert client.post("/api/jobs/does-not-exist/cancel").status_code == 404


def test_edit_story_applies_prompt(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    response = client.post(f"/api/stories/{story_id}/edit", json={"prompt": "make it punchier"})
    assert response.status_code == 200
    body = response.json()
    assert "Body. (edited: make it punchier)" in body["markdown"]

    fetched = client.get(f"/api/stories/{story_id}").json()
    assert "Body. (edited: make it punchier)" in fetched["markdown"]


def test_edit_story_requires_valid_prompt(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    assert client.post(f"/api/stories/{story_id}/edit", json={"prompt": ""}).status_code == 422


def test_edit_unknown_story_404(client: TestClient) -> None:
    login(client)
    assert client.post("/api/stories/999/edit", json={"prompt": "shorten"}).status_code == 404


def test_edit_story_is_owner_scoped(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    other = make_client()
    login(other, email="bob@example.com")
    response = other.post(f"/api/stories/{story_id}/edit", json={"prompt": "shorten"})
    assert response.status_code == 404


def test_delete_story_removes_it(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    assert client.delete(f"/api/stories/{story_id}").status_code == 204
    assert client.get(f"/api/stories/{story_id}").status_code == 404


def test_delete_story_is_owner_scoped(client: TestClient) -> None:
    login(client)
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    other = make_client()
    login(other, email="bob@example.com")
    assert other.delete(f"/api/stories/{story_id}").status_code == 404
    assert client.get(f"/api/stories/{story_id}").status_code == 200


def test_delete_unknown_story_404(client: TestClient) -> None:
    login(client)
    assert client.delete("/api/stories/999").status_code == 404


def test_delete_story_requires_auth(client: TestClient) -> None:
    assert client.delete("/api/stories/1").status_code == 401


def test_create_story_passes_user_style_profile(client: TestClient) -> None:
    login(client)
    profile = set_style(client)
    captured: dict[str, object] = {}

    def runner(record, request: GenerationRequest) -> None:
        captured["style_profile"] = request.style_profile
        record.set_status("done")

    client.app.state.generation_runner = runner
    response = client.post("/api/stories", json={"prompt": "Chip demand"})
    assert response.status_code == 202
    assert captured["style_profile"] == profile


def test_create_story_passes_none_without_profile(client: TestClient) -> None:
    login(client)
    captured: dict[str, object] = {}

    def runner(record, request: GenerationRequest) -> None:
        captured["style_profile"] = request.style_profile
        record.set_status("done")

    client.app.state.generation_runner = runner
    response = client.post("/api/stories", json={"prompt": "Chip demand"})
    assert response.status_code == 202
    assert captured["style_profile"] is None


def test_create_story_passes_user_sampling_params(client: TestClient) -> None:
    login(client)
    set_sampling(client, temperature=1.2, top_p=0.6)
    captured: dict[str, object] = {}

    def runner(record, request: GenerationRequest) -> None:
        captured["temperature"] = request.temperature
        captured["top_p"] = request.top_p
        record.set_status("done")

    client.app.state.generation_runner = runner
    response = client.post("/api/stories", json={"prompt": "Chip demand"})
    assert response.status_code == 202
    assert captured["temperature"] == 1.2
    assert captured["top_p"] == 0.6


def test_edit_story_uses_user_sampling_params(client: TestClient) -> None:
    login(client)
    set_sampling(client, temperature=0.9, top_p=0.75)
    captured: dict[str, object] = {}

    def editor(markdown: str, prompt: str, style=None, temperature=None, top_p=None) -> str:
        captured["temperature"] = temperature
        captured["top_p"] = top_p
        return markdown

    client.app.state.editor = editor
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    response = client.post(f"/api/stories/{story_id}/edit", json={"prompt": "tighten"})
    assert response.status_code == 200
    assert captured["temperature"] == 0.9
    assert captured["top_p"] == 0.75


def test_edit_story_uses_user_style_profile(client: TestClient) -> None:
    login(client)
    profile = set_style(client)
    captured: dict[str, object] = {}

    def editor(markdown: str, prompt: str, style=None, temperature=None, top_p=None) -> str:
        captured["style"] = style
        return markdown

    client.app.state.editor = editor
    job = client.post("/api/stories", json={"prompt": "Chip demand"}).json()
    story_id = wait_for_job(client, job["job_id"])["story_id"]

    response = client.post(f"/api/stories/{story_id}/edit", json={"prompt": "tighten"})
    assert response.status_code == 200
    assert captured["style"] == profile
