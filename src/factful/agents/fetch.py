from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Protocol

import httpx
from pydantic import BaseModel

_BLOCK_TAGS = {
    "address",
    "article",
    "aside",
    "blockquote",
    "br",
    "caption",
    "div",
    "footer",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "header",
    "li",
    "main",
    "p",
    "pre",
    "section",
    "td",
    "th",
    "tr",
}
_SKIP_TAGS = {"xjunk"}

_CDATA_TAG = re.compile(
    r"<(?P<clos>/?)\s*(?P<tag>bgsound|iframe|noscript|noembed|style|script)\b[^>]*>",
    re.IGNORECASE,
)

_WHITESPACE = re.compile(r"\s+")


class Page(BaseModel):
    url: str
    title: str
    publish_date: str
    text: str


class Fetcher(Protocol):
    def fetch(self, url: str) -> Page | None: ...


class _PageParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.chunks: list[str] = []
        self.title: str | None = None
        self.og_title: str | None = None
        self.publish_date: str | None = None
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if self._skip_depth and (tag in _BLOCK_TAGS or tag == "body"):
            self._skip_depth = 0
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.chunks.append("\n")
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            self._handle_meta(attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
        elif tag in {"body", "html"}:
            self._skip_depth = 0
        elif tag in _BLOCK_TAGS:
            self.chunks.append("\n")
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            if self.title is None:
                self.title = data.strip()
            return
        self.chunks.append(data)

    def _handle_meta(self, attrs: list[tuple[str, str | None]]) -> None:
        props = dict(attrs)
        property_value = (props.get("property") or "").lower()
        name_value = (props.get("name") or "").lower()
        content = props.get("content")
        if content is None:
            return
        if "published_time" in property_value or name_value in {"date", "published_time"}:
            if self.publish_date is None:
                self.publish_date = content
        if property_value == "og:title" and self.og_title is None:
            self.og_title = content


def _neutralize_cdata(html: str) -> str:
    return _CDATA_TAG.sub(
        lambda match: "<xjunk>" if not match.group("clos") else "</xjunk>",
        html,
    )


def _parse(html: str) -> _PageParser:
    parser = _PageParser()
    parser.feed(_neutralize_cdata(html))
    return parser


def html_to_text(html: str) -> str:
    raw_chunks = "".join(_parse(html).chunks)
    lines = [_WHITESPACE.sub(" ", line).strip() for line in raw_chunks.splitlines()]
    return "\n".join(line for line in lines if line)


def extract_title(html: str) -> str:
    parser = _parse(html)
    return parser.og_title or parser.title or ""


def extract_publish_date(html: str) -> str:
    return _parse(html).publish_date or ""


def extract_page(url: str, html: str) -> Page:
    return Page(
        url=url,
        title=extract_title(html),
        publish_date=extract_publish_date(html),
        text=html_to_text(html),
    )


class HttpxFetcher:
    def __init__(self, *, _client: httpx.Client | None = None, timeout: float = 30.0) -> None:
        self._client = _client or httpx.Client(timeout=timeout)

    def fetch(self, url: str) -> Page | None:
        try:
            response = self._client.get(url)
        except httpx.HTTPError:
            return None
        if response.status_code >= 400:
            return None
        return extract_page(url, response.text)
