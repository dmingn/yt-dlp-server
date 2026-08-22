from fastapi import APIRouter, HTTPException, Request
from pydantic import AnyHttpUrl, AwareDatetime, BaseModel

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.models import CancelledJob, Job, JobId, JobSummary


class CreateJobRequest(BaseModel):
    url: AnyHttpUrl
    scheduled_at: AwareDatetime | None = None


class GetJobRequest(BaseModel):
    id: JobId


class CancelJobRequest(BaseModel):
    id: JobId


router = APIRouter(prefix="/api")


def _job_service_from_request(request: Request) -> JobService:
    job_service = request.app.state.job_service
    assert isinstance(job_service, JobService)
    return job_service


@router.post("/createJob", response_model=Job, status_code=201)
async def create_job(body: CreateJobRequest, request: Request) -> Job:
    job_service = _job_service_from_request(request)

    try:
        job_id = await job_service.submit(
            str(body.url),
            scheduled_at=body.scheduled_at,
        )
    except JobCapacityFull:
        raise HTTPException(status_code=503, detail="Job capacity full") from None

    job = job_service.get(job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="Created job not found")

    return job


@router.post("/listJobs", response_model=list[JobSummary])
async def list_jobs(request: Request) -> list[JobSummary]:
    return _job_service_from_request(request).list_summaries()


@router.post("/getJob", response_model=Job)
async def get_job(body: GetJobRequest, request: Request) -> Job:
    job = _job_service_from_request(request).get(body.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/cancelJob", response_model=CancelledJob)
async def cancel_job(body: CancelJobRequest, request: Request) -> CancelledJob:
    job_service = _job_service_from_request(request)

    if job_service.get(body.id) is None:
        raise HTTPException(status_code=404, detail="Job not found")

    cancelled = await job_service.cancel(body.id)
    if cancelled is None:
        raise HTTPException(status_code=409, detail="Job already finished")

    return cancelled
