"""Persist and load a StyleProfile as YAML."""

from __future__ import annotations

from pathlib import Path

import yaml

from factful.style.schema import StyleProfile


def profile_to_yaml(profile: StyleProfile) -> str:
    return yaml.safe_dump(profile.model_dump(), sort_keys=False)


def load_profile(path: str | Path) -> StyleProfile:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid style profile: {path}")
    return StyleProfile.model_validate(data)
