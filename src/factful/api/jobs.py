from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from factful.api.deps import get_current_user
from factful.api.schemas import JobStatus
from factful.jobstore import JobStore
from factful.models import User

router = APIRouter()


@router.get("/{job_id}", response_model=JobStatus)
def get_job(
    job_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JobStatus:
    job_store: JobStore = request.app.state.job_store
    record = job_store.get(job_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    return JobStatus.model_validate(record.snapshot())


@router.post("/{job_id}/cancel", response_model=JobStatus)
def cancel_job(
    job_id: str,
    request: Request,
    user: Annotated[User, Depends(get_current_user)],
) -> JobStatus:
    job_store: JobStore = request.app.state.job_store
    record = job_store.get(job_id)
    if record is None or record.user_id != user.id:
        raise HTTPException(status_code=404, detail="job not found")
    record.cancel()
    return JobStatus.model_validate(record.snapshot())
