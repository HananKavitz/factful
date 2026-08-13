import logging
import re

import pytest

from factful import cli
from factful.cli import main
from factful.pipeline import PipelineResult
from factful.schemas import (
    Citation,
    CritiqueReport,
    FactVerdict,
    SourceBundle,
)
from factful.state import PipelineState


def make_result() -> PipelineResult:
    citation = Citation(
        claim_id="c1",
        claim="Revenue hit $4B in 2024",
        source_url="https://example.com/report",
        source_title="Annual Report",
        publisher="example.com",
        publish_date="2024-01-01",
        key_stat="$4B",
        quote_snippet="Revenue hit $4B in 2024.",
        passage_ref="para-2",
        retrieved_at="2024-01-02T00:00:00Z",
    )
    state = PipelineState(
        topic="AI trends",
        angle="data angle",
        source_bundle=SourceBundle(topic="AI trends", angle="data angle", citations=[citation]),
    )
    state.add_verdict(FactVerdict(claim_id="c1", status="verified", confidence=0.9, reason="ok"))
    state.add_critique(CritiqueReport(score=90, issues=[], verdict="pass"))
    state.record_pass(score=90, draft="The market grew 12% [[c1]].")
    return PipelineResult(
        state=state,
        decision="publish",
        reason="hard gate passed",
        unresolved=[],
    )


def set_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-or-test")
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "factful" in capsys.readouterr().out


def test_generate_requires_llm_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    with pytest.raises(SystemExit, match="LLM_API_KEY is not set"):
        main(["generate", "AI trends"])


def test_generate_requires_tavily_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "load_dotenv", lambda: None)
    set_keys(monkeypatch)
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="TAVILY_API_KEY is not set"):
        main(["generate", "AI trends"])


def test_no_command_prints_help_and_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main([])
    assert rc == 0
    assert "generate" in capsys.readouterr().out


def test_style_without_api_key_fails_fast(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(SystemExit, match="LLM_API_KEY is not set"):
        main(["style", "docs/samples/arab-weakness-exposed.md"])


def test_generate_writes_artifacts(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,
) -> None:
    set_keys(monkeypatch)
    monkeypatch.setattr(cli, "run_pipeline", lambda *a, **k: make_result())
    out = tmp_path / "out"
    rc = main(["generate", "AI trends", "--out", str(out)])
    assert rc == 0
    assert "AI trends" in capsys.readouterr().out
    draft = out / "ai-trends" / "draft.md"
    report_md = out / "ai-trends" / "report.md"
    report_json = out / "ai-trends" / "report.json"
    assert draft.read_text(encoding="utf-8") == "The market grew 12% [[c1]]."
    assert "hard gate passed" in report_md.read_text(encoding="utf-8")
    assert '"decision": "publish"' in report_json.read_text(encoding="utf-8")


def test_generate_passes_angle_and_max_sources(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: object,
) -> None:
    set_keys(monkeypatch)
    captured: dict = {}

    def fake_run(topic, angle, *, max_sources=None, **kwargs):
        captured["topic"] = topic
        captured["angle"] = angle
        captured["max_sources"] = max_sources
        return make_result()

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    out = tmp_path / "out"
    rc = main(
        ["generate", "AI trends", "--angle", "chip supply", "--max-sources", "4", "--out", str(out)]
    )
    assert rc == 0
    assert captured == {"topic": "AI trends", "angle": "chip supply", "max_sources": 4}


def test_generate_verbose_emits_info_to_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,
) -> None:
    set_keys(monkeypatch)

    def fake_run(*a, **k):
        logging.getLogger("factful.pipeline").info("gathered 3 citations")
        return make_result()

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    out = tmp_path / "out"
    rc = main(["generate", "AI trends", "--verbose", "--out", str(out)])
    assert rc == 0
    err = capsys.readouterr().err
    assert "gathered 3 citations" in err
    assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", err)


def test_generate_without_verbose_suppresses_info(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: object,
) -> None:
    set_keys(monkeypatch)

    def fake_run(*a, **k):
        logging.getLogger("factful.pipeline").info("gathered 3 citations")
        return make_result()

    monkeypatch.setattr(cli, "run_pipeline", fake_run)
    out = tmp_path / "out"
    rc = main(["generate", "AI trends", "--out", str(out)])
    assert rc == 0
    assert "gathered 3 citations" not in capsys.readouterr().err
