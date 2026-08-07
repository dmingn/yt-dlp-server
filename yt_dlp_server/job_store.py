from yt_dlp_server.models import FinishedJob, Job, UnfinishedJob


class JobStore:
    """In-memory job registry with a bounded number of retained jobs."""

    def __init__(self, *, max_jobs: int) -> None:
        self._max_jobs = max_jobs
        self._jobs: dict[str, Job] = {}

    @property
    def max_jobs(self) -> int:
        return self._max_jobs

    def put(self, job: Job) -> None:
        self._jobs[job.id] = job
        self._evict()

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return sorted(
            self._jobs.values(),
            key=lambda job: job.created_at,
            reverse=True,
        )

    def unfinished_count(self) -> int:
        return sum(1 for job in self._jobs.values() if isinstance(job, UnfinishedJob))

    def _evict(self) -> None:
        while len(self._jobs) > self._max_jobs:
            finished = [
                job for job in self._jobs.values() if isinstance(job, FinishedJob)
            ]
            if not finished:
                break
            oldest = min(finished, key=lambda job: job.created_at)
            del self._jobs[oldest.id]
