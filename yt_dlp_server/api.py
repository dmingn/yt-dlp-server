from fastapi import APIRouter, HTTPException, Request
from pydantic import AnyHttpUrl, BaseModel

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.models import (
    CancelledJob,
    Job,
    JobSummary,
    QueuedJob,
)


class CreateJobRequest(BaseModel):
    url: AnyHttpUrl


class GetJobRequest(BaseModel):
    id: str


class CancelJobRequest(BaseModel):
    id: str


router = APIRouter(prefix="/api")


def _job_service_from_request(request: Request) -> JobService:
    jobs = request.app.state.jobs
    assert isinstance(jobs, JobService)
    return jobs


@router.post("/createJob", response_model=Job, status_code=201)
async def create_job(body: CreateJobRequest, request: Request) -> QueuedJob:
    try:
        return _job_service_from_request(request).enqueue(str(body.url))
    except JobCapacityFull:
        raise HTTPException(status_code=503, detail="Job capacity full") from None


@router.post("/listJobs", response_model=list[JobSummary])
async def list_jobs(request: Request) -> list[JobSummary]:
    return _job_service_from_request(request).list_summaries()


@router.post("/getJob", response_model=Job)
async def get_job(body: GetJobRequest, request: Request) -> Job:
    job = _job_service_from_request(request).get(body.id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.post("/cancelJob", response_model=Job)
async def cancel_job(body: CancelJobRequest, request: Request) -> CancelledJob:
    jobs = _job_service_from_request(request)
    if jobs.get(body.id) is None:
        raise HTTPException(status_code=404, detail="Job not found")
    cancelled = await jobs.cancel(body.id)
    if cancelled is None:
        raise HTTPException(status_code=409, detail="Job already finished")
    return cancelled
