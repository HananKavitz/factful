"""Tests for the WebVTT subtitle builder and metadata merging."""

from __future__ import annotations

import json
from pathlib import Path

from factful.video.subtitles import build_vtt, merge_tts_metadata


def _write_jsonl(path: Path, offset: int, words: list[str]) -> None:
    lines = [
        json.dumps({"type": "WordBoundary", "offset": offset, "duration": 1_000_000, "text": w})
        for w in words
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class TestMergeTtsMetadata:
    def test_offsets_each_segment_by_its_start(self, tmp_path: Path) -> None:
        """RED: later scenes get their word offsets shifted by cumulative start."""
        first = tmp_path / "scene_0.jsonl"
        second = tmp_path / "scene_1.jsonl"
        _write_jsonl(first, 0, ["hello"])
        _write_jsonl(second, 0, ["world"])

        merged = tmp_path / "merged.jsonl"
        merge_tts_metadata([(first, 0.0), (second, 4.0)], merged)

        events = [json.loads(line) for line in merged.read_text().splitlines()]
        assert events[0]["offset"] == 0
        assert events[1]["offset"] == 4 * 10_000_000

    def test_missing_scene_file_is_skipped(self, tmp_path: Path) -> None:
        """RED: a missing jsonl contributes no events rather than crashing."""
        present = tmp_path / "scene_0.jsonl"
        _write_jsonl(present, 0, ["hello"])
        missing = tmp_path / "scene_1.jsonl"

        merged = tmp_path / "merged.jsonl"
        merge_tts_metadata([(present, 0.0), (missing, 5.0)], merged)

        events = [json.loads(line) for line in merged.read_text().splitlines()]
        assert len(events) == 1

    def test_merged_file_builds_vtt(self, tmp_path: Path) -> None:
        """RED: the merged file is a valid input for build_vtt()."""
        first = tmp_path / "scene_0.jsonl"
        second = tmp_path / "scene_1.jsonl"
        _write_jsonl(first, 0, ["hello", "there"])
        _write_jsonl(second, 0, ["world"])

        merged = tmp_path / "merged.jsonl"
        merge_tts_metadata([(first, 0.0), (second, 4.0)], merged)

        vtt = build_vtt(merged)
        assert vtt.startswith("WEBVTT")
        assert "hello there" in vtt
        assert "world" in vtt

    def test_empty_segments_writes_empty_file(self, tmp_path: Path) -> None:
        """RED: no segments yields an empty metadata file."""
        merged = tmp_path / "merged.jsonl"
        merge_tts_metadata([], merged)
        assert merged.read_text(encoding="utf-8") == ""
        assert build_vtt(merged) == ""
