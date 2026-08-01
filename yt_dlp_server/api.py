from fastapi import APIRouter, HTTPException, Request

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.models import Job, JobCreate, JobSummary, QueuedJob

router = APIRouter(prefix="/api")


def _jobs(request: Request) -> JobService:
    jobs = request.app.state.jobs
    assert isinstance(jobs, JobService)
    return jobs


@router.post("/jobs", response_model=Job, status_code=201)
async def create_job(body: JobCreate, request: Request) -> QueuedJob:
    try:
        return _jobs(request).enqueue(str(body.url))
    except JobCapacityFull:
        raise HTTPException(status_code=503, detail="Job capacity full") from None


@router.get("/jobs", response_model=list[JobSummary])
async def list_jobs(request: Request) -> list[JobSummary]:
    return _jobs(request).list_summaries()


@router.get("/jobs/{job_id}", response_model=Job)
async def get_job(job_id: str, request: Request) -> Job:
    job = _jobs(request).get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
