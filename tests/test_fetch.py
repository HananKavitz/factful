from __future__ import annotations

from collections.abc import Callable

import httpx

from factful.agents.fetch import HttpxFetcher, Page, extract_page, html_to_text

HTML = """
<html><head>
<title>Market Report 2024</title>
<meta property="article:published_time" content="2024-06-01T09:00:00Z">
</head>
<body>
<p>Revenue grew 12% in Q1.</p>
<p>By 2025 the firm will employ <b>3,000</b> people.</p>
</body></html>
"""


def _fetcher(
    handler: Callable[[httpx.Request], httpx.Response],
) -> HttpxFetcher:
    return HttpxFetcher(_client=httpx.Client(transport=httpx.MockTransport(handler)))


def _ok(url: str = "https://example.com/article") -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=HTML, request=request)

    return handler


def test_html_to_text_strips_tags_and_keeps_paragraphs() -> None:
    text = html_to_text(HTML)
    assert "Revenue grew 12% in Q1." in text
    assert "3,000" in text
    assert "<p>" not in text
    assert text.count("\n") >= 1


def test_html_to_text_separates_table_cells() -> None:
    table = "<table><tr><td>Revenue</td><td>42%</td></tr></table>"
    text = html_to_text(table)
    assert "Revenue\n42%" in text
    assert "Revenue42%" not in text


def test_html_to_text_tolerates_unclosed_script() -> None:
    broken = "keep this<script>var x = '<div>junk</div>';<p>after</p>"
    text = html_to_text(broken)
    assert "keep this" in text
    assert "after" in text
    assert "var x" not in text


def test_extract_page_metadata() -> None:
    page = extract_page("https://example.com/article", HTML)
    assert page.url == "https://example.com/article"
    assert page.title == "Market Report 2024"
    assert page.publish_date == "2024-06-01T09:00:00Z"


def test_fetch_returns_page() -> None:
    page = _fetcher(_ok()).fetch("https://example.com/article")
    assert isinstance(page, Page)
    assert page is not None
    assert "12%" in page.text
    assert "3,000" in page.text


def test_fetch_missing_page_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, text="nope", request=request)

    assert _fetcher(handler).fetch("https://example.com/gone") is None


def test_fetch_transport_error_returns_none() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    assert _fetcher(handler).fetch("https://example.com/down") is None
