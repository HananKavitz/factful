import time

from factful.jobstore import JobRecord, JobStore


def test_create_returns_unique_queued_records() -> None:
    store = JobStore()
    first = store.create()
    second = store.create()
    assert first.id != second.id
    assert first.snapshot()["status"] == "queued"
    store.shutdown()


def test_get_returns_record_and_missing_is_none() -> None:
    store = JobStore()
    record = store.create()
    assert store.get(record.id) is record
    assert store.get("nope") is None
    store.shutdown()


def test_submit_runs_worker() -> None:
    store = JobStore()
    record = store.create()
    seen: list[str] = []

    def run(rec: JobRecord) -> None:
        time.sleep(0.01)
        seen.append(rec.id)
        rec.set_stage("writing draft")

    store.submit(record, run)
    store.shutdown(wait=True)
    snapshot = record.snapshot()
    assert seen == [record.id]
    assert snapshot["stage"] == "writing draft"


def test_submit_captures_errors() -> None:
    store = JobStore()
    record = store.create()

    def run(rec: JobRecord) -> None:
        raise RuntimeError("boom")

    store.submit(record, run)
    store.shutdown(wait=True)
    snapshot = record.snapshot()
    assert snapshot["status"] == "error"
    assert snapshot["error"] == "boom"


def test_set_story_id_marks_done() -> None:
    record = JobRecord("j1")
    record.set_status("running")
    record.set_story_id(42)
    snapshot = record.snapshot()
    assert snapshot["status"] == "done"
    assert snapshot["story_id"] == 42
    assert snapshot["error"] is None
