"""Monotonic numeric progress for background generation jobs."""

from __future__ import annotations

from collections.abc import Callable

_STAGES_PER_PASS = 3  # write, fact-check, critique

_FINAL_CAP = 95  # reserves the last 5% as "not quite finished yet"


def total_steps(max_passes: int) -> int:
    """Number of progress steps for a full run: gather plus stages per pass."""
    return 1 + _STAGES_PER_PASS * max_passes


def percent_for(step: int, max_passes: int) -> int:
    """Map a 1-based step index to a percent, capped at _FINAL_CAP."""
    return min(_FINAL_CAP, (_FINAL_CAP * step) // total_steps(max_passes))


class ProgressTracker:
    """Counts pipeline stage boundaries and maps each to a capped percent."""

    def __init__(self, max_passes: int, on_mark: Callable[[int], None]) -> None:
        self._max_passes = max_passes
        self._on_mark = on_mark
        self._step = 0

    def mark(self) -> None:
        self._step += 1
        self._on_mark(percent_for(self._step, self._max_passes))
