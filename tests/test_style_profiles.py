from __future__ import annotations

from factful.style.io import load_profile

FORBIDDEN_TERMS = ("Nasser", "Saddam", "Gaddafi", "Sheikh", "Qatar", "Arab")


def _shipped_kevich_profile_text() -> str:
    profile = load_profile("src/factful/style/profiles/kevich.yaml")
    return str(profile.extraction.model_dump())


def test_shipped_kevich_profile_leaks_no_topic_bound_proper_nouns() -> None:
    text = _shipped_kevich_profile_text()
    for term in FORBIDDEN_TERMS:
        assert term not in text, f"kevich profile leaks topic-bound term: {term!r}"
