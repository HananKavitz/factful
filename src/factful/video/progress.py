"""Monotonic 0-100 progress mapping for video generation stages."""

from __future__ import annotations

from collections.abc import Callable

# Stage names that describe the same phase of the pipeline.
_STAGE_ALIASES: dict[str, str] = {
    "generating_clips": "fetching_clips",
}

# ``(stage, share)`` in emission order. ``composing`` is a zero-weight
# marker emitted both before and after the composition sub-stages, so it
# never advances the bar on its own. Shares sum to 1.0.
#
# Calibrated against a real 16-scene stock render (video id 59):
# script_director 8%, tts 24%, clip fetch/rank/trim 50%, encode 17%.
# The instant ``composing_clips``/``mixing_audio``/``concatenating``
# placeholders are given almost no weight; the real encoding work gets
# the encoding share.
_PHASES: tuple[tuple[str, float], ...] = (
    ("script_director", 0.08),
    ("tts", 0.24),
    ("fetching_clips", 0.49),
    ("composing", 0.0),
    ("composing_clips", 0.02),
    ("mixing_audio", 0.0),
    ("concatenating", 0.0),
    ("encoding", 0.16),
    ("finalizing", 0.01),
)


def _clamp_fraction(fraction: float) -> float:
    return max(0.0, min(1.0, fraction))


class VideoProgressTracker:
    """Maps ``(stage, fraction)`` events onto a monotonic 0-100 percent.

    The tracker remembers the highest percent seen so stages that are
    reported out of order (e.g. the ``composing`` echo after the
    composition sub-stages) can never move the bar backwards.
    """

    def __init__(self, on_percent: Callable[[int], None]) -> None:
        self._on_percent = on_percent
        self._percent = 0

    @property
    def percent(self) -> int:
        """The highest percent emitted so far."""
        return self._percent

    def report(self, stage: str, fraction: float) -> None:
        """Record a stage event and emit the current monotonic percent."""
        canonical = _STAGE_ALIASES.get(stage, stage)
        offset = 0.0
        for name, weight in _PHASES:
            if name == canonical:
                offset += weight * _clamp_fraction(fraction)
                break
            offset += weight
        else:
            # Unknown stage: keep the current percent rather than fabricate.
            self._on_percent(self._percent)
            return
        self._percent = max(self._percent, round(offset * 100))
        self._on_percent(self._percent)
