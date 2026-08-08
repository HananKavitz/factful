import pytest

from factful.cli import main


def test_version_flag(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as excinfo:
        main(["--version"])
    assert excinfo.value.code == 0
    assert "factful" in capsys.readouterr().out


def test_generate_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    rc = main(["generate", "AI trends"])
    assert rc == 0
    captured = capsys.readouterr()
    assert "AI trends" in captured.out


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
