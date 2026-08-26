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
    assert settings.retrieval.top_k_passages == 3
    assert settings.verify.max_currency_years == 2.0
    assert settings.writer.profile == "kevich"


def test_loads_yaml_values(tmp_path: Path) -> None:
    (tmp_path / "settings.yaml").write_text("pipeline:\n  max_passes: 5\n", encoding="utf-8")
    settings = load_settings(tmp_path / "settings.yaml")
    assert settings.pipeline.max_passes == 5
    assert settings.pipeline.score_accept == 85


def test_settings_is_pydantic() -> None:
    settings = Settings()
    assert settings.pipeline.model_dump()["epsilon"] == 1.0


def test_gather_defaults() -> None:
    assert Settings().gather.max_sources == 10


def test_gather_search_days_default() -> None:
    assert Settings().gather.search_days == 365


def test_gather_search_days_overridable() -> None:
    settings = Settings.model_validate({"gather": {"search_days": 90}})
    assert settings.gather.search_days == 90


def test_gather_search_days_rejects_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"gather": {"search_days": 0}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"gather": {"search_days": 366}})


def test_gather_max_sources_overridable() -> None:
    settings = Settings.model_validate({"gather": {"max_sources": 4}})
    assert settings.gather.max_sources == 4


def test_retrieval_verify_writer_overridable() -> None:
    settings = Settings.model_validate(
        {
            "retrieval": {"top_k_passages": 5},
            "verify": {"max_currency_years": 1.0},
            "writer": {"profile": "voice"},
        }
    )
    assert settings.retrieval.top_k_passages == 5
    assert settings.verify.max_currency_years == 1.0
    assert settings.writer.profile == "voice"


def test_writer_sampling_defaults() -> None:
    writer = Settings().writer
    assert writer.temperature == 0.8
    assert writer.top_p == 0.9


def test_writer_word_bounds_defaults() -> None:
    writer = Settings().writer
    assert writer.min_words == 1500
    assert writer.target_words == 2000
    assert writer.max_words == 2500


def test_writer_word_bounds_overridable() -> None:
    writer = Settings.model_validate({"writer": {"max_words": 2400}}).writer
    assert writer.max_words == 2400
    assert writer.min_words == 1500


def test_writer_word_bounds_reject_unordered_range() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {"writer": {"min_words": 2000, "target_words": 1200, "max_words": 1800}}
        )


def test_writer_sampling_overridable() -> None:
    settings = Settings.model_validate({"writer": {"temperature": 1.1, "top_p": 0.7}})
    assert settings.writer.temperature == 1.1
    assert settings.writer.top_p == 0.7


def test_writer_sampling_rejects_out_of_bounds() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"writer": {"temperature": -0.1}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"writer": {"temperature": 2.1}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"writer": {"top_p": 0.0}})
    with pytest.raises(ValidationError):
        Settings.model_validate({"writer": {"top_p": 1.1}})


def test_unknown_key_fails_fast() -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate({"pipeline": {"max_passes": 3}, "typo_key": 1})
