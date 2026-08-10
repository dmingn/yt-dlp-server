from __future__ import annotations

import uuid
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import assert_never

from yt_dlp_server.job_store import JobStore
from yt_dlp_server.job_task_manager import JobTaskManager
from yt_dlp_server.models import (
    CancelledJob,
    FailedJob,
    FinishedJob,
    Job,
    JobId,
    JobSummary,
    QueuedJob,
    RunningJob,
    SucceededJob,
)

ProcessJobFn = Callable[["JobService", JobId], Coroutine[object, object, None]]


class JobCapacityFull(Exception):
    """Raised when unfinished jobs already reach max_jobs."""


def _utcnow() -> datetime:
    return datetime.now(UTC)


class JobService:
    def __init__(
        self,
        store: JobStore,
        *,
        max_running: int,
        process_job_fn: ProcessJobFn,
    ) -> None:
        self._store = store
        self._task_manager = JobTaskManager(
            max_running=max_running,
            claim_next_job_fn=self._claim_next_job,
            process_job_fn=lambda job_id: process_job_fn(self, job_id),
        )

    def _claim_next_job(self) -> JobId | None:
        claimed = self._store.claim_oldest_queued(started_at=_utcnow())
        return None if claimed is None else claimed.id

    def enqueue(self, url: str) -> QueuedJob:
        if self._store.unfinished_count() >= self._store.max_jobs:
            raise JobCapacityFull()
        job = QueuedJob.model_validate(
            {
                "id": JobId(str(uuid.uuid4())),
                "url": url,
                "created_at": _utcnow(),
            }
        )
        self._store.save_metadata(job)
        return job

    async def submit(self, url: str) -> JobId:
        job = self.enqueue(url)
        await self._task_manager.claim_queued_jobs_up_to_max_running()
        return job.id

    def get(self, job_id: JobId) -> Job | None:
        return self._store.get_job(job_id)

    def list_summaries(self) -> list[JobSummary]:
        return [JobSummary.from_job(job) for job in self._store.list_jobs()]

    def append_log_line(self, job_id: JobId, line: str) -> None:
        job = self._store.get_job(job_id)
        if not isinstance(job, RunningJob):
            return
        self._store.append_log(job_id, line)

    def mark_succeeded(self, job_id: JobId) -> SucceededJob | None:
        job = self._store.get_job(job_id)
        if not isinstance(job, RunningJob):
            return None
        succeeded = job.succeed(finished_at=_utcnow())
        self._store.save_metadata(succeeded)
        return succeeded

    def mark_failed(
        self,
        job_id: JobId,
        *,
        error: str,
        exit_code: int | None = None,
    ) -> FailedJob | None:
        job = self._store.get_job(job_id)
        if not isinstance(job, RunningJob):
            return None
        failed = job.fail(
            finished_at=_utcnow(),
            error=error,
            exit_code=exit_code,
        )
        self._store.save_metadata(failed)
        return failed

    async def cancel(self, job_id: JobId) -> CancelledJob | None:
        job = self._store.get_job(job_id)

        if job is None:
            return None
        if isinstance(job, FinishedJob):
            return None

        if isinstance(job, QueuedJob):
            cancelled = job.cancel(finished_at=_utcnow())
            self._store.save_metadata(cancelled)
            return cancelled

        if isinstance(job, RunningJob):
            cancelled = job.cancel(finished_at=_utcnow())
            self._store.save_metadata(cancelled)
            await self._task_manager.cancel(job_id)
            return cancelled

        assert_never(job)

    async def requeue_unfinished_jobs(self) -> None:
        self._store.requeue_running()
        await self._task_manager.claim_queued_jobs_up_to_max_running()

    async def shutdown(self) -> None:
        await self._task_manager.shutdown()
