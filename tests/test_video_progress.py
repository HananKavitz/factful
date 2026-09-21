"""Tests for monotonic video generation progress mapping."""

from __future__ import annotations

from factful.video.progress import VideoProgressTracker

# Emission order for the direct-FFmpeg composer path.
_DIRECT_PATH: list[tuple[str, float]] = [
    ("script_director", 0.0),
    ("tts", 0.0),
    ("tts", 0.5),
    ("tts", 1.0),
    ("fetching_clips", 0.0),
    ("fetching_clips", 0.5),
    ("fetching_clips", 1.0),
    ("composing", 0.0),
    ("composing_clips", 1.0),
    ("mixing_audio", 1.0),
    ("concatenating", 1.0),
    ("composing", 1.0),
    ("encoding", 0.0),
    ("encoding", 0.5),
    ("encoding", 1.0),
    ("finalizing", 1.0),
]

# Emission order for the legacy moviepy composer path.
_MOVIEPY_PATH: list[tuple[str, float]] = [
    ("script_director", 0.0),
    ("tts", 0.0),
    ("tts", 1.0),
    ("fetching_clips", 0.0),
    ("fetching_clips", 1.0),
    ("composing", 0.0),
    ("composing_clips", 0.0),
    ("composing_clips", 1.0),
    ("mixing_audio", 0.0),
    ("concatenating", 0.0),
    ("encoding", 0.0),
    ("encoding", 1.0),
    ("finalizing", 1.0),
]


def _run(events: list[tuple[str, float]]) -> list[int]:
    emitted: list[int] = []
    tracker = VideoProgressTracker(on_percent=emitted.append)
    for stage, fraction in events:
        tracker.report(stage, fraction)
    return emitted


def test_starts_at_zero_on_first_stage() -> None:
    assert _run([("script_director", 0.0)]) == [0]


def test_reaches_one_hundred_on_finalizing() -> None:
    emitted = _run(_DIRECT_PATH)
    assert emitted[-1] == 100
    assert max(emitted) == 100


def test_direct_path_is_monotonic() -> None:
    emitted = _run(_DIRECT_PATH)
    assert emitted == sorted(emitted)


def test_moviepy_path_is_monotonic() -> None:
    emitted = _run(_MOVIEPY_PATH)
    assert emitted == sorted(emitted)


def test_late_composing_echo_does_not_regress() -> None:
    """The ``composing`` echo after the sub-stages must not pull the bar back."""
    tracker = VideoProgressTracker(on_percent=lambda _pct: None)
    for stage, fraction in _DIRECT_PATH:
        tracker.report(stage, fraction)
        if stage == "composing" and fraction == 1.0:
            echo_percent = tracker.percent
            break
    assert echo_percent == 83


def test_encoding_carries_most_of_the_compose_block() -> None:
    """Encoding is real work; the instant composing placeholders are not."""
    tracker = VideoProgressTracker(on_percent=lambda _pct: None)
    for stage, fraction in [
        ("fetching_clips", 1.0),
        ("composing", 0.0),
        ("composing_clips", 1.0),
        ("mixing_audio", 1.0),
        ("concatenating", 1.0),
    ]:
        tracker.report(stage, fraction)
    before_encoding = tracker.percent
    tracker.report("encoding", 1.0)
    assert tracker.percent - before_encoding >= 15


def test_generating_clips_is_an_alias_for_fetching_clips() -> None:
    assert _run([("generating_clips", 1.0)]) == _run([("fetching_clips", 1.0)])


def test_unknown_stage_preserves_current_percent() -> None:
    assert _run([("tts", 1.0), ("mystery", 0.5)]) == [32, 32]


def test_hundred_is_only_reached_by_finalizing() -> None:
    assert max(_run(_DIRECT_PATH[:-1])) < 100
