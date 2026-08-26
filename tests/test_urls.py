"""Tests for URL extraction from free-text prompts."""

from __future__ import annotations

from factful.agents._urls import extract_urls


def test_empty_text() -> None:
    assert extract_urls("") == []


def test_no_urls() -> None:
    assert extract_urls("What is the state of AI in Europe?") == []


def test_bare_domain_no_scheme_no_www() -> None:
    """'example.com' without scheme or www. prefix is not matched."""
    assert extract_urls("Check example.com for details") == []


def test_https_url() -> None:
    assert extract_urls("See https://example.com/report") == ["https://example.com/report"]


def test_http_url() -> None:
    assert extract_urls("http://example.com/report is useful") == ["http://example.com/report"]


def test_bare_www_host() -> None:
    assert extract_urls("Data at www.example.com") == ["https://www.example.com"]


def test_bare_www_with_path() -> None:
    assert extract_urls("Read www.example.com/article/2024") == [
        "https://www.example.com/article/2024"
    ]


def test_www_with_query_and_fragment() -> None:
    result = extract_urls("Source: www.example.com/data?year=2024#section")
    assert result == ["https://www.example.com/data?year=2024#section"]


def test_deduplication() -> None:
    result = extract_urls("Visit https://example.com and also www.example.com")
    # https://example.com and https://www.example.com are distinct
    # normalized strings because one has www. and the other does not.
    assert len(result) == 2


def test_duplicate_exact_url_deduped() -> None:
    result = extract_urls("First https://example.com/report then https://example.com/report again")
    assert result == ["https://example.com/report"]


def test_duplicate_www_deduped() -> None:
    result = extract_urls("www.example.com and www.example.com")
    assert result == ["https://www.example.com"]


def test_mixed_schemes_and_www() -> None:
    result = extract_urls("Use https://example.com/a, http://other.org/b, and www.third.net/c")
    assert result == [
        "https://example.com/a",
        "http://other.org/b",
        "https://www.third.net/c",
    ]


def test_url_inside_parentheses() -> None:
    result = extract_urls("The report (https://example.com/report) shows growth.")
    assert result == ["https://example.com/report"]


def test_url_at_end_of_sentence() -> None:
    result = extract_urls("Check https://example.com/report.")
    assert result == ["https://example.com/report"]


def test_no_false_positive_on_ip_address() -> None:
    """IPs like 127.0.0.1 aren't URLs unless prefixed with scheme."""
    result = extract_urls("Server at 127.0.0.1")
    assert result == []


def test_no_false_positive_on_email() -> None:
    result = extract_urls("Contact user@example.com for access")
    assert result == []


def test_instructions_with_url_and_text_preserved() -> None:
    """URL extraction only — doesn't strip or modify the original text."""
    text = "Use www.example.com/report as the main source. Focus on figures."
    result = extract_urls(text)
    assert result == ["https://www.example.com/report"]
