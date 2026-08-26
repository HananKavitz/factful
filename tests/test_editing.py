from __future__ import annotations

from dataclasses import dataclass

from factful import editing
from factful.schemas import Draft


@dataclass(frozen=True)
class RuntimeStub:
    settings: object
    searcher: object
    fetcher: object
    clients: object


def test_build_editor_strips_claim_tags_from_result(monkeypatch) -> None:
    clients = type("Clients", (), {"writer": "writer-client"})()
    runtime = RuntimeStub(settings="settings", searcher=None, fetcher=None, clients=clients)
    monkeypatch.setattr(editing, "build_runtime", lambda env: runtime)
    monkeypatch.setattr(
        editing,
        "apply_user_edit",
        lambda markdown, prompt, profile, *, client, settings, **kwargs: Draft(
            title="T", markdown=f"{prompt} [[c1]] revised"
        ),
    )

    edit = editing.build_editor(env={"LLM_API_KEY": "k"})
    result = edit("original body", "tighten it")

    assert result == "tighten it revised"


def test_build_editor_passes_client_and_profile(monkeypatch) -> None:
    clients = type("Clients", (), {"writer": "writer-client"})()
    runtime = RuntimeStub(settings="settings", searcher=None, fetcher=None, clients=clients)
    monkeypatch.setattr(editing, "build_runtime", lambda env: runtime)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        editing,
        "apply_user_edit",
        lambda markdown, prompt, profile, *, client, settings, **kwargs: (
            captured.update(
                markdown=markdown, prompt=prompt, profile=profile, client=client, settings=settings
            )
            or Draft(title="T", markdown="result")
        ),
    )

    edit = editing.build_editor(env={})
    edit("body", "rewrite the lead", "profile")

    assert captured["markdown"] == "body"
    assert captured["prompt"] == "rewrite the lead"
    assert captured["profile"] == "profile"
    assert captured["client"] == "writer-client"
    assert captured["settings"] == "settings"


def test_build_editor_falls_back_to_neutral_profile(monkeypatch) -> None:
    clients = type("Clients", (), {"writer": "writer-client"})()
    runtime = RuntimeStub(settings="settings", searcher=None, fetcher=None, clients=clients)
    monkeypatch.setattr(editing, "build_runtime", lambda env: runtime)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        editing,
        "apply_user_edit",
        lambda markdown, prompt, profile, *, client, settings, **kwargs: (
            captured.update(profile=profile) or Draft(title="T", markdown="result")
        ),
    )

    edit = editing.build_editor(env={})
    edit("body", "rewrite the lead")

    assert captured["profile"].name == "neutral"


def test_build_editor_forwards_sampling_params(monkeypatch) -> None:
    clients = type("Clients", (), {"writer": "writer-client"})()
    runtime = RuntimeStub(settings="settings", searcher=None, fetcher=None, clients=clients)
    monkeypatch.setattr(editing, "build_runtime", lambda env: runtime)
    captured: dict[str, object] = {}
    monkeypatch.setattr(
        editing,
        "apply_user_edit",
        lambda markdown, prompt, profile, *, client, settings, temperature, top_p: (
            captured.update(
                temperature=temperature,
                top_p=top_p,
                client=client,
                settings=settings,
            )
            or Draft(title="T", markdown="result")
        ),
    )

    edit = editing.build_editor(env={})
    edit("body", "rewrite the lead", "profile", 0.65, 0.8)

    assert captured["temperature"] == 0.65
    assert captured["top_p"] == 0.8
    assert captured["client"] == "writer-client"
    assert captured["settings"] == "settings"
