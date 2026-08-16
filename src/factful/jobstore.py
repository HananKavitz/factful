from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Literal

JobStatus = Literal["queued", "running", "done", "error", "cancelled"]


class JobRecord:
    """Thread-safe status holder for a background generation job."""

    def __init__(self, job_id: str, user_id: int | None = None) -> None:
        self._id = job_id
        self._lock = threading.Lock()
        self._user_id = user_id
        self._status: JobStatus = "queued"
        self._stage: str | None = None
        self._error: str | None = None
        self._story_id: int | None = None
        self._cancelled = threading.Event()

    @property
    def id(self) -> str:
        return self._id

    @property
    def user_id(self) -> int | None:
        return self._user_id

    def set_stage(self, stage: str) -> None:
        with self._lock:
            self._stage = stage

    def set_status(self, status: JobStatus) -> None:
        with self._lock:
            self._status = status

    def set_error(self, error: str) -> None:
        with self._lock:
            self._status = "error"
            self._error = error

    def set_story_id(self, story_id: int) -> None:
        with self._lock:
            if self._status == "cancelled":
                return
            self._status = "done"
            self._story_id = story_id

    def cancel(self) -> None:
        with self._lock:
            if self._status in ("done", "error", "cancelled"):
                return
            self._cancelled.set()
            self._status = "cancelled"

    def is_cancelled(self) -> bool:
        return self._cancelled.is_set()

    def snapshot(self) -> dict[str, str | int | None]:
        with self._lock:
            return {
                "job_id": self._id,
                "status": self._status,
                "stage": self._stage,
                "error": self._error,
                "story_id": self._story_id,
            }


class JobStore:
    """In-memory job registry with a single background worker."""

    def __init__(self, max_workers: int = 1) -> None:
        self._jobs: dict[str, JobRecord] = {}
        self._lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="factful-job"
        )

    def create(self, user_id: int | None = None) -> JobRecord:
        record = JobRecord(uuid.uuid4().hex, user_id=user_id)
        with self._lock:
            self._jobs[record.id] = record
        return record

    def get(self, job_id: str) -> JobRecord | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, record: JobRecord, fn: Callable[[JobRecord], None]) -> None:
        record.set_status("running")
        self._executor.submit(_guard, record, fn)

    def shutdown(self, wait: bool = False) -> None:
        self._executor.shutdown(wait=wait)


def _guard(record: JobRecord, fn: Callable[[JobRecord], None]) -> None:
    try:
        fn(record)
    except Exception as exc:
        record.set_error(str(exc))
