from datetime import datetime

import pytest
from pydantic import ValidationError

from factful.schemas import Citation, CritiqueReport, Issue, SourceBundle


def make_citation(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "claim_id": "c1",
        "claim": "Sales grew 12% in Q1",
        "source_url": "https://example.com/report",
        "source_title": "Annual Report",
        "publisher": "Example Corp",
        "publish_date": "2025-01-01",
        "key_stat": "12%",
        "quote_snippet": "revenue rose 12 percent",
        "passage_ref": "para-3",
        "retrieved_at": "2025-01-02T00:00:00Z",
    }
    base.update(overrides)
    return Citation.model_validate(base)


def test_citation_parses() -> None:
    c = make_citation()
    assert c.claim_id == "c1"
    assert isinstance(c.retrieved_at, datetime)
    assert c.retrieved_at.tzinfo is not None


def test_citation_requires_claim_id() -> None:
    with pytest.raises(ValidationError):
        make_citation(claim_id="")


def test_source_bundle_holds_citations() -> None:
    bundle = SourceBundle(topic="Growth", angle="FY outlook", citations=[make_citation()])
    assert bundle.topic == "Growth"
    assert bundle.citations[0].key_stat == "12%"


def test_issue_and_critique_report() -> None:
    issue = Issue(type="hook", severity="high", message="weak hook")
    report = CritiqueReport.model_validate(
        {"score": 70, "issues": [issue.model_dump()], "verdict": "rework"}
    )
    assert report.score == 70
    assert report.verdict == "rework"
    assert report.issues[0].revision is None


def test_critique_score_bounds() -> None:
    with pytest.raises(ValidationError):
        CritiqueReport.model_validate({"score": 101, "issues": [], "verdict": "pass"})


def test_critique_verdict_enum() -> None:
    with pytest.raises(ValidationError):
        CritiqueReport.model_validate({"score": 50, "issues": [], "verdict": "maybe"})
