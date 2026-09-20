"""WebVTT subtitle builder from edge-tts WordBoundary metadata.

Each TTS call produces a JSONL file with one line per word:

    {"type": "WordBoundary", "offset": 10000000, "duration": 3750000, "text": "hello"}

Offset/duration are in 100-ns ticks (10 000 000 = 1 s).  This module
converts them to a single WebVTT string with phrase-level cues (not
one word per cue, which would flicker).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_VTT_HEADER = "WEBVTT\n\n"
_TARGET_WORDS_PER_CUE = 8
_MAX_WORDS_PER_CUE = 15
_MAX_CUE_SECONDS = 30.0
_MIN_WORDS_FOR_FORCE_BREAK = 3


def _format_ts(us: float) -> str:
    """Microseconds → ``HH:MM:SS.mmm``."""
    s = us / 1_000_000.0
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = s % 60
    return f"{h:02d}:{m:02d}:{sec:06.3f}"


def _parse_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a JSONL file and return list of WordBoundary events."""
    if not path.exists():
        return []
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            ev = json.loads(line)
        except json.JSONDecodeError:
            continue
        if ev.get("type") != "WordBoundary":
            continue
        events.append(ev)
    return events


def _batch_cues(events: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Group word events into phrase-level batches."""
    if not events:
        return []
    cues: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    for w in events:
        current.append(w)
        n = len(current)
        if n >= _TARGET_WORDS_PER_CUE:
            cues.append(current)
            current = []
            continue
        if n >= _MAX_WORDS_PER_CUE:
            cues.append(current)
            current = []
            continue
        if n >= _MIN_WORDS_FOR_FORCE_BREAK:
            span = w["offset"] - current[0]["offset"]
            if span > _MAX_CUE_SECONDS * 10_000_000:
                cues.append(current)
                current = []
    if current:
        cues.append(current)
    return cues


def merge_tts_metadata(
    segments: list[tuple[Path, float]],
    output_path: Path,
) -> Path:
    """Merge per-scene edge-tts JSONL files into one offset-corrected file.

    Each segment is ``(jsonl_path, start_seconds)``; every WordBoundary
    event's ``offset`` is shifted by the segment's start so the combined
    file is a valid timeline for the concatenated voiceover.

    Missing scene files are skipped.  Raises nothing for empty input —
    the written file may simply contain no events.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    lines: list[str] = []
    for path, start_seconds in segments:
        shift = int(start_seconds * 10_000_000)
        for ev in _parse_jsonl(path):
            ev = dict(ev)
            ev["offset"] = int(ev.get("offset", 0)) + shift
            lines.append(json.dumps(ev, ensure_ascii=False))
    output_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return output_path


def build_vtt(metadata_path: Path) -> str:
    """Convert a single edge-tts JSONL file to a WebVTT subtitle string.

    Args:
        metadata_path: Path to the ``.jsonl`` WordBoundary file.

    Returns:
        Complete WebVTT string (UTF-8), or empty string if no events.
    """
    events = _parse_jsonl(metadata_path)
    if not events:
        return ""

    cues = _batch_cues(events)
    if not cues:
        return ""

    lines: list[str] = [_VTT_HEADER]
    for i, batch in enumerate(cues, start=1):
        start = batch[0]["offset"] // 10  # 100ns → µs
        if i < len(cues):
            end = cues[i][0]["offset"] // 10
        else:
            end = (batch[-1]["offset"] + batch[-1]["duration"]) // 10

        text = " ".join(w.get("text", "") for w in batch)
        lines.append(str(i))
        lines.append(f"{_format_ts(start)} --> {_format_ts(end)}")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)
