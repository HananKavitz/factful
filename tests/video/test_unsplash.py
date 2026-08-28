"""Tests for the Unsplash image source."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from factful.video.sources import ImageSourceError
from factful.video.unsplash import UnsplashSource


def _mock_photo(
    photo_id: str = "abc123",
    tags: list[str] | None = None,
    alt_description: str | None = "A scenic view",
    urls_raw: str | None = None,
) -> dict:
    return {
        "id": photo_id,
        "urls": {"raw": urls_raw or f"https://images.unsplash.com/{photo_id}"},
        "alt_description": alt_description,
        "tags": [{"title": t} for t in (tags or ["nature", "landscape"])],
    }


def _mock_search_response(photos: list[dict]) -> dict:
    return {"results": photos, "total": len(photos), "total_pages": 1}


def _mock_random_response(photo: dict) -> list[dict]:
    return [photo]


def test_validate_with_valid_key_passes() -> None:
    transport = httpx.MockTransport(
        lambda req: httpx.Response(
            200, json=_mock_search_response([_mock_photo()])
        )
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
    transport = httpx.MockTransport(
        lambda req: httpx.Response(200, json=_mock_search_response([]))
    )
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


def test_fetch_success_returns_path() -> None:
    photo = _mock_photo(tags=["ai", "technology", "computer"])
    image_bytes = b"fake-jpeg-bytes"

    def handler(req: httpx.Request) -> httpx.Response:
        if "/photos/random" in req.url.path:
            return httpx.Response(200, json=_mock_random_response(photo))
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


def test_fetch_retries_on_irrelevant_image(tmp_path: Path) -> None:
    call_count = 0
    image_bytes = b"fake-jpeg-final"

    def handler(req: httpx.Request) -> httpx.Response:
        nonlocal call_count
        if "images.unsplash.com" in req.url.host:
            return httpx.Response(200, content=image_bytes)
        call_count += 1
        # Return photos with tags that don't match "AI Technology"
        photo = _mock_photo(
            photo_id=str(call_count),
            tags=["cooking", "food", "kitchen"],
            alt_description="A kitchen",
            urls_raw=f"https://images.unsplash.com/photo-{call_count}",
        )
        return httpx.Response(200, json=_mock_random_response(photo))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)
    source = UnsplashSource("key", http_client=client)

    out = tmp_path / "result.jpg"
    # On the last retry, the image should be accepted despite relevance failure
    result = source.fetch(heading="AI Technology", body="", output_path=out)
    assert result == out
    assert out.read_bytes() == image_bytes
    assert call_count == 3  # 2 retries + final acceptance


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


def test_validate_with_403_returns_error() -> None:
    transport = httpx.MockTransport(lambda req: httpx.Response(403))
    client = httpx.Client(transport=transport)
    source = UnsplashSource("bad-key", http_client=client)
    result = source.validate(heading="Tech", body="")
    assert result is not None
    assert "invalid" in result or "rate-limited" in result


def test_implements_image_source_protocol() -> None:
    from factful.video.sources import ImageSource

    source = UnsplashSource("key")
    assert isinstance(source, ImageSource)