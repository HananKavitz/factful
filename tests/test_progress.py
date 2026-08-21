from factful.progress import ProgressTracker, percent_for, total_steps


def test_total_steps_is_gather_plus_stages_per_pass() -> None:
    assert total_steps(3) == 10
    assert total_steps(2) == 7
    assert total_steps(1) == 4


def test_percent_for_is_monotonic_and_capped_at_95() -> None:
    previous = 0
    for step in range(1, total_steps(3) + 1):
        current = percent_for(step, 3)
        assert 0 <= current <= 95
        assert current >= previous
        previous = current
    assert percent_for(total_steps(3), 3) == 95


def test_percent_for_spans_from_low_to_95() -> None:
    assert percent_for(1, 3) == 9
    assert percent_for(5, 3) == 47
    assert percent_for(10, 3) == 95


def test_tracker_emits_percent_per_mark() -> None:
    emitted: list[int] = []
    tracker = ProgressTracker(max_passes=3, on_mark=lambda pct: emitted.append(pct))
    for _ in range(6):
        tracker.mark()
    assert emitted == [percent_for(i, 3) for i in range(1, 7)]


def test_tracker_never_exceeds_95_when_overrun() -> None:
    emitted: list[int] = []
    tracker = ProgressTracker(max_passes=2, on_mark=lambda pct: emitted.append(pct))
    for _ in range(10):
        tracker.mark()
    assert emitted == [percent_for(i, 2) for i in range(1, 11)]
    assert max(emitted) == 95
