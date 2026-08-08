from __future__ import annotations

from pathlib import Path

from factful.style.io import load_profile, profile_to_yaml
from factful.style.schema import StyleExtraction, StyleMetrics, StyleProfile

PROFILE = StyleProfile(
    name="kevich",
    metrics=StyleMetrics(avg_sentence_words=16.0, avg_paragraph_sentences=3.0),
    extraction=StyleExtraction(
        voice="long-form, opinionated",
        tone="acerbic, skeptical",
        characterization=[{"label": "sarcasm", "count": 4, "excerpt": "golden palaces"}],
    ),
)


def test_profile_yaml_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "kevich.yaml"
    path.write_text(profile_to_yaml(PROFILE), encoding="utf-8")
    loaded = load_profile(path)
    assert loaded == PROFILE


def test_load_profile_rejects_non_dict(tmp_path: Path) -> None:
    path = tmp_path / "bad.yaml"
    path.write_text("- just\n- a\n- list", encoding="utf-8")
    try:
        load_profile(path)
    except ValueError as exc:
        assert "invalid style profile" in str(exc)
    else:
        raise AssertionError("expected ValueError")
