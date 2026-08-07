from pathlib import Path

import pytest
from pydantic import ValidationError

from factful.config import Settings, load_settings


def test_defaults_when_file_absent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FACTFUL_SETTINGS", raising=False)
    settings = load_settings(Path("does-not-exist.yaml"))
    assert settings.pipeline.max_passes == 3
    assert settings.pipeline.score_accept == 85
    assert settings.pipeline.epsilon == 1.0
    assert settings.pipeline.delta == 0.5
    assert settings.pipeline.revision_mode == "patch"
    assert settings.corroboration.min_sources == 2


def test_loads_yaml_values(tmp_path: Path) -> None:
    (tmp_path / "settings.yaml").write_text("pipeline:\n  max_passes: 5\n", encoding="utf-8")
    settings = load_settings(tmp_path / "settings.yaml")
    assert settings.pipeline.max_passes == 5
    assert settings.pipeline.score_accept == 85


def test_settings_is_pydantic() -> None:
    settings = Settings()
    assert settings.pipeline.model_dump()["epsilon"] == 1.0


def test_unknown_key_fails_fast() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"pipeline": {"max_passes": 3}, "typo_key": 1})
