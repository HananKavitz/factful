"""Tests for the Unsplash image source."""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from factful.video.sources import ImageSourceError
from factful.video.unsplash import UnsplashSource


def _mock_photo(
    photo_id: str = "abc123",
    tags: list[str] | None = None,
    alt_description: str | None = "A scenic view",
    description: str | None = None,
    urls_raw: str | None = None,
) -> dict:
    return {
        "id": photo_id,
        "urls": {"raw": urls_raw or f"https://images.unsplash.com/{photo_id}"},
        "alt_description": alt_description,
        "description": description,
        "tags": [{"title": t} for t in (tags or ["nature", "landscape"])],
    }


def _mock_search_response(photos: list[dict]) -> dict:
    return {"results": photos, "total": len(photos), "total_pages": 1}


def test_validate_with_valid_key_passes() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=_mock_search_response([_mock_photo()]))
    )
    client = httpx.Client(transport=transport)
    source = UnsplashSource("valid-key", http_client=client)
    assert source.validate(heading="Technology", body="AI") is None


def test_validate_with_empty_key_fails() -> None:
    source = UnsplashSource("")
    result = source.validate(heading="Tech", body="")
    assert result is not None
    assert "not configured" in result


def test_validate_with_no_results_returns_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(200, json=_mock_search_response([])))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)
    result = source.validate(heading="XyzzyUnknown", body="")
    assert result is not None
    assert "no Unsplash images found" in result


def test_validate_with_api_error_returns_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)
    result = source.validate(heading="Tech", body="")
    assert result is not None


def test_validate_with_403_returns_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(403))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("bad-key", http_client=client)
    result = source.validate(heading="Tech", body="")
    assert result is not None
    assert "invalid" in result or "rate-limited" in result


def test_fetch_success_returns_path() -> None:
    photo = _mock_photo(tags=["ai", "technology", "computer"])
    image_bytes = b"fake-jpeg-bytes"

    def handler(req: httpx.Request) -> httpx.Response:
        if "/search/photos" in req.url.path:
            return httpx.Response(200, json=_mock_search_response([photo]))
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_output.jpg")
    try:
        result = source.fetch(heading="AI Technology", body="", output_path=out)
        assert result == out
        assert out.read_bytes() == image_bytes
    finally:
        out.unlink(missing_ok=True)


def test_fetch_with_empty_key_raises() -> None:
    source = UnsplashSource("")
    with pytest.raises(ImageSourceError, match="not configured"):
        source.fetch(heading="Tech", body="", output_path=Path("x.jpg"))


def test_fetch_rate_limit_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(403))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    with pytest.raises(ImageSourceError, match="rejected"):
        source.fetch(heading="Tech", body="", output_path=Path("x.jpg"))


def test_fetch_network_error_raises() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(500))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    with pytest.raises(ImageSourceError):
        source.fetch(heading="Tech", body="", output_path=Path("x.jpg"))


def test_fetch_returns_best_available_when_none_meet_threshold(tmp_path: Path) -> None:
    call_count = 0
    image_bytes = b"fake-jpeg-final"

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        call_count += 1
        photo = _mock_photo(
            photo_id=str(call_count),
            tags=["cooking", "food", "kitchen"],
            alt_description="A kitchen",
            urls_raw=f"https://images.unsplash.com/photo-{call_count}",
        )
        return httpx.Response(200, json=_mock_search_response([photo]))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = tmp_path / "result.jpg"
    result = source.fetch(heading="AI Technology", body="", output_path=out)
    assert result == out
    assert out.read_bytes() == image_bytes
    assert call_count == 3


def test_fetch_body_enriches_query_for_generic_heading() -> None:
    photo = _mock_photo(tags=["introduction", "neural", "networks", "ai"])
    image_bytes = b"fake-jpeg-bytes"
    captured_query: str | None = None

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_query
        if "/search/photos" in req.url.path:
            captured_query = req.url.params.get("query")
            return httpx.Response(200, json=_mock_search_response([photo]))
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_output.jpg")
    try:
        source.fetch(
            heading="Introduction",
            body="Neural networks have transformed artificial intelligence",
            output_path=out,
        )
        assert captured_query is not None
        assert "neural" in captured_query
        assert "artificial" in captured_query
        assert "intelligence" in captured_query
    finally:
        out.unlink(missing_ok=True)


def test_fetch_body_does_not_duplicate_heading_tokens() -> None:
    photo = _mock_photo(tags=["ai", "technology", "computer"])
    image_bytes = b"fake-jpeg-bytes"
    captured_query: str | None = None

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_query
        if "/search/photos" in req.url.path:
            captured_query = req.url.params.get("query")
            return httpx.Response(200, json=_mock_search_response([photo]))
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_output2.jpg")
    try:
        source.fetch(
            heading="AI Technology",
            body="Modern artificial intelligence technology is advancing rapidly",
            output_path=out,
        )
        assert captured_query is not None
        tokens = captured_query.split()
        assert tokens.count("ai") == 1
        assert tokens.count("technology") == 1
    finally:
        out.unlink(missing_ok=True)


def test_fetch_uses_body_for_validate_too() -> None:
    captured_query: str | None = None

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_query
        if "/search/photos" in req.url.path:
            captured_query = req.url.params.get("query")
            return httpx.Response(200, json=_mock_search_response([_mock_photo()]))
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    source.validate(
        heading="Introduction",
        body="Neural networks and deep learning have revolutionized AI",
    )
    assert captured_query is not None
    assert "neural" in captured_query
    assert "learning" in captured_query
    assert "introduction" not in captured_query
    assert len(captured_query.split()) > 1


def test_fetch_generic_heading_uses_body_for_query() -> None:
    photo = _mock_photo(tags=["neural", "networks", "ai"])
    image_bytes = b"fake-jpeg-bytes"
    captured_query: str | None = None

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal captured_query
        if "/search/photos" in req.url.path:
            captured_query = req.url.params.get("query")
            return httpx.Response(200, json=_mock_search_response([photo]))
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_generic.jpg")
    try:
        source.fetch(
            heading="Introduction",
            body="Neural networks have transformed artificial intelligence",
            output_path=out,
        )
        assert captured_query is not None
        assert "introduction" not in captured_query
        assert "neural" in captured_query
    finally:
        out.unlink(missing_ok=True)


def test_fetch_scores_combined_photo_text() -> None:
    """alt_description and description should both count for relevance."""
    photo = _mock_photo(
        tags=["nature", "landscape"],
        alt_description="A computer running AI algorithms",
    )
    image_bytes = b"fake-jpeg-bytes"

    def handler(req: httpx.Request) -> httpx.Response:
        if "/search/photos" in req.url.path:
            return httpx.Response(200, json=_mock_search_response([photo]))
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_combined.jpg")
    try:
        result = source.fetch(heading="AI Technology", body="", output_path=out)
        assert result == out
    finally:
        out.unlink(missing_ok=True)


def test_fetch_picks_best_result_from_search() -> None:
    """When multiple results are returned, the most relevant one is chosen."""
    bad_photo = _mock_photo(
        photo_id="bad",
        tags=["food", "cooking"],
        alt_description="A delicious meal",
        urls_raw="https://images.unsplash.com/bad",
    )
    good_photo = _mock_photo(
        photo_id="good",
        tags=["ai", "technology", "robot"],
        alt_description="A robot using artificial intelligence",
        urls_raw="https://images.unsplash.com/good",
    )
    good_bytes = b"fake-jpeg-good"

    def handler(req: httpx.Request) -> httpx.Response:
        if "/search/photos" in req.url.path:
            return httpx.Response(200, json=_mock_search_response([bad_photo, good_photo]))
        if "images.unsplash.com" in req.url.host:
            if "good" in str(req.url):
                return httpx.Response(200, content=good_bytes)
            return httpx.Response(200, content=b"fake-jpeg-bad")
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = Path("test_best.jpg")
    try:
        result = source.fetch(heading="AI Technology", body="", output_path=out)
        assert result == out
        assert out.read_bytes() == good_bytes
    finally:
        out.unlink(missing_ok=True)


def test_implements_image_source_protocol() -> None:
    from factful.video.sources import ImageSource

    source = UnsplashSource("key")
    assert isinstance(source, ImageSource)
