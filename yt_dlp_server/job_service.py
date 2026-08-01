import asyncio
import uuid
from datetime import UTC, datetime

from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import (
    FailedJob,
    Job,
    JobSummary,
    QueuedJob,
    RunningJob,
    SucceededJob,
)


class JobCapacityFull(Exception):
    """Raised when unfinished jobs already reach max_jobs."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobService:
    def __init__(
        self,
        store: JobStore,
        *,
        max_log_lines: int,
    ) -> None:
        self._store = store
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._max_log_lines = max_log_lines

    def enqueue(self, url: str) -> QueuedJob:
        if self._store.unfinished_count() >= self._store.max_jobs:
            raise JobCapacityFull()
        job = QueuedJob.model_validate(
            {
                "id": str(uuid.uuid4()),
                "url": url,
                "created_at": _utcnow(),
            }
        )
        self._store.put(job)
        self._queue.put_nowait(job.id)
        return job

    async def claim_next(self) -> str:
        return await self._queue.get()

    def task_done(self) -> None:
        self._queue.task_done()

    def get(self, job_id: str) -> Job | None:
        return self._store.get(job_id)

    def list_summaries(self) -> list[JobSummary]:
        return [JobSummary.from_job(job) for job in self._store.list_jobs()]

    def mark_running(self, job_id: str) -> RunningJob | None:
        job = self._store.get(job_id)
        if not isinstance(job, QueuedJob):
            return None
        running = job.start(
            started_at=_utcnow(),
            max_log_lines=self._max_log_lines,
        )
        self._store.put(running)
        return running

    def append_log_line(self, job_id: str, line: str) -> None:
        job = self._store.get(job_id)
        if not isinstance(job, RunningJob):
            return
        self._store.put(job.append_log_line(line))

    def mark_succeeded(self, job_id: str) -> SucceededJob | None:
        job = self._store.get(job_id)
        if not isinstance(job, RunningJob):
            return None
        succeeded = job.succeed(finished_at=_utcnow())
        self._store.put(succeeded)
        return succeeded

    def mark_failed(
        self,
        job_id: str,
        *,
        error: str,
        exit_code: int | None = None,
    ) -> FailedJob | None:
        job = self._store.get(job_id)
        if not isinstance(job, RunningJob):
            return None
        failed = job.fail(
            finished_at=_utcnow(),
            error=error,
            exit_code=exit_code,
        )
        self._store.put(failed)
        return failed
