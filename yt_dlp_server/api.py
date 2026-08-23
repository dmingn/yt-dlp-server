from fastapi import APIRouter, HTTPException, Request
from pydantic import AnyHttpUrl, AwareDatetime, BaseModel

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.models import (
    CancelledJob,
    Job,
    JobId,
    JobSummary,
    QueuedJob,
    ScheduledJob,
)


class CreateJobRequest(BaseModel):
    url: AnyHttpUrl
    scheduled_at: AwareDatetime | None = None


class GetJobRequest(BaseModel):
    id: JobId


class CancelJobRequest(BaseModel):
    id: JobId


class RescheduleJobRequest(BaseModel):
    id: JobId
    scheduled_at: AwareDatetime


router = APIRouter(prefix="/api")


def _job_service_from_request(request: Request) -> JobService:
    job_service = request.app.state.job_service
    assert isinstance(job_service, JobService)
    return job_service


@router.post("/createJob", response_model=QueuedJob | ScheduledJob, status_code=201)
async def create_job(
    body: CreateJobRequest, request: Request
) -> QueuedJob | ScheduledJob:
    job_service = _job_service_from_request(request)

    try:
        return job_service.create_job(
            str(body.url),
            scheduled_at=body.scheduled_at,
        )
    except JobCapacityFull:
        raise HTTPException(status_code=503, detail="Job capacity full") from None


@router.post("/listJobs", response_model=list[JobSummary])
async def list_jobs(request: Request) -> list[JobSummary]:
    return _job_service_from_request(request).list_summaries()


@router.post("/getJob", response_model=Job)
async def get_job(body: GetJobRequest, request: Request) -> Job:
    job = _job_service_from_request(request).get_job(body.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/cancelJob", response_model=CancelledJob)
async def cancel_job(body: CancelJobRequest, request: Request) -> CancelledJob:
    job_service = _job_service_from_request(request)

    if job_service.get_job(body.id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    cancelled_job = await job_service.cancel_job(body.id)
    if cancelled_job is None:
        raise HTTPException(status_code=409, detail="Job already finished")

    return cancelled_job


@router.post("/rescheduleJob", response_model=ScheduledJob)
async def reschedule_job(body: RescheduleJobRequest, request: Request) -> ScheduledJob:
    job_service = _job_service_from_request(request)

    if job_service.get_job(body.id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    rescheduled_job = job_service.reschedule_job(
        body.id, scheduled_at=body.scheduled_at
    )
    if rescheduled_job is None:
        raise HTTPException(status_code=409, detail="Job status is not scheduled")

    return rescheduled_job
