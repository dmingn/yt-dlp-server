from __future__ import annotations

import asyncio
import logging
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
    ScheduledJob,
    SucceededJob,
)

ProcessJobFn = Callable[["JobService", JobId], Coroutine[object, object, None]]

_logger = logging.getLogger(__name__)


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
        poll_interval_seconds: float = 1,
        utcnow_fn: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._store = store
        self._max_running = max_running
        self._poll_interval_seconds = poll_interval_seconds
        self._utcnow_fn = utcnow_fn
        self._task_manager = JobTaskManager(
            process_job_fn=lambda job_id: process_job_fn(self, job_id),
        )
        self._poll_task: asyncio.Task[None] | None = None

    def create_job(
        self, url: str, *, scheduled_at: datetime | None = None
    ) -> QueuedJob | ScheduledJob:
        if self._store.unfinished_count() >= self._store.max_jobs:
            raise JobCapacityFull()
        if scheduled_at is None:
            job: QueuedJob | ScheduledJob = QueuedJob.model_validate(
                {
                    "id": JobId(str(uuid.uuid4())),
                    "url": url,
                    "created_at": self._utcnow_fn(),
                }
            )
        else:
            job = ScheduledJob.model_validate(
                {
                    "id": JobId(str(uuid.uuid4())),
                    "url": url,
                    "created_at": self._utcnow_fn(),
                    "scheduled_at": scheduled_at,
                }
            )
        self._store.save_metadata(job)
        return job

    async def submit(self, url: str, *, scheduled_at: datetime | None = None) -> JobId:
        return self.create_job(url, scheduled_at=scheduled_at).id

    def try_start_jobs(self) -> None:
        now = self._utcnow_fn()

        while not self._task_manager.closed:
            due_job = self._store.claim_due_scheduled(now=now)
            if due_job is None:
                break
            self._task_manager.spawn(due_job.id)

        while (
            not self._task_manager.closed
            and self._task_manager.running_count < self._max_running
        ):
            queued_job = self._store.claim_oldest_queued(started_at=now)
            if queued_job is None:
                return
            self._task_manager.spawn(queued_job.id)

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
        succeeded = job.succeed(finished_at=self._utcnow_fn())
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
            finished_at=self._utcnow_fn(),
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
            immediate_cancelled = job.cancel(finished_at=self._utcnow_fn())
            self._store.save_metadata(immediate_cancelled)
            return immediate_cancelled

        if isinstance(job, ScheduledJob):
            scheduled_cancelled = job.cancel(finished_at=self._utcnow_fn())
            self._store.save_metadata(scheduled_cancelled)
            return scheduled_cancelled

        if isinstance(job, RunningJob):
            cancelled = job.cancel(finished_at=self._utcnow_fn())
            self._store.save_metadata(cancelled)
            await self._task_manager.cancel(job_id)
            return cancelled

        assert_never(job)

    def restore_waiting_jobs(self) -> None:
        self._store.restore_waiting_jobs()

    async def start_polling(self) -> None:
        if self._poll_task is not None:
            return
        self._poll_task = asyncio.create_task(
            self._poll_loop(),
            name="try-start-jobs",
        )

    async def _poll_loop(self) -> None:
        while True:
            try:
                self.try_start_jobs()
            except Exception:
                _logger.exception("try_start_jobs failed")
            await asyncio.sleep(self._poll_interval_seconds)

    async def shutdown(self) -> None:
        if self._poll_task is not None:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
            self._poll_task = None
        await self._task_manager.shutdown()
