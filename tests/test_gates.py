from datetime import UTC, date, datetime

from factful.verify.gates import numeric_gates, parse_date

NOW = datetime(2024, 6, 1, tzinfo=UTC).date()


def test_percentage_over_100_flagged() -> None:
    flags = numeric_gates(
        "Growth hit 150%",
        "150%",
        "the index rose by 150 percent, a record",
        "2023-01-01",
        now=NOW,
    )
    assert any("implausible percentage" in f for f in flags)


def test_sane_percentage_not_flagged() -> None:
    flags = numeric_gates(
        "Growth reached 85%",
        "85%",
        "the index rose 85 percent.",
        "2023-01-01",
        now=NOW,
    )
    assert not any("implausible percentage" in f for f in flags)


def test_fresh_source_not_flagged_stale() -> None:
    flags = numeric_gates("x", "12%", "grew 12 percent.", "2024-01-01", now=NOW)
    assert not any("years old" in f for f in flags)


def test_stale_source_flagged() -> None:
    flags = numeric_gates(
        "x", "12%", "grew 12 percent.", "2023-01-01", max_currency_years=1, now=NOW
    )
    assert any("years old" in f for f in flags)


def test_percent_point_confusion_flagged() -> None:
    flags = numeric_gates(
        "Rates jumped by 30%",
        "30%",
        "the rate rose from 10 percent to 40 percent.",
        "2024-01-01",
        now=NOW,
    )
    assert any("percent-point" in f for f in flags)


def test_unparseable_date_skipped() -> None:
    flags = numeric_gates("x", "12%", "grew 12 percent.", "not-a-date", now=NOW)
    assert all("years old" not in f for f in flags)


def test_parse_date_iso() -> None:
    assert parse_date("2024-03-05") == date(2024, 3, 5)


def test_parse_date_rfc3339_offset() -> None:
    assert parse_date("2023-01-01T10:00:00-05:00") == date(2023, 1, 1)


def test_parse_date_utc_zulu() -> None:
    assert parse_date("2023-01-01T10:00:00Z") == date(2023, 1, 1)


def test_rfc3339_offset_stale_detected() -> None:
    flags = numeric_gates(
        "x",
        "12%",
        "grew 12 percent.",
        "2023-01-01T10:00:00-05:00",
        max_currency_years=1,
        now=date(2024, 6, 1),
    )
    assert any("years old" in f for f in flags)


def test_parse_date_none_for_garbage() -> None:
    assert parse_date("garbage") is None
