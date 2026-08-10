import asyncio
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

import pytest
from pydantic import AnyHttpUrl

from yt_dlp_server.job_service import JobCapacityFull, JobService, ProcessJobFn
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import (
    CancelledJob,
    JobId,
    JobLog,
    JobStatus,
    QueuedJob,
    RunningJob,
    SucceededJob,
)

_URL = AnyHttpUrl("https://example.com/video")
_CREATED = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
_STARTED = datetime.fromisoformat("2026-01-01T01:00:00+00:00")
_FINISHED = datetime.fromisoformat("2026-01-01T02:00:00+00:00")


async def _noop_process_job(_job_service: JobService, _job_id: JobId) -> None:
    return


@pytest.fixture
def make_job_service(tmp_path: Path) -> Callable[..., JobService]:
    def _make(
        *,
        max_jobs: int = 100,
        max_log_lines: int = 2000,
        max_running: int = 0,
        process_job_fn: ProcessJobFn | None = None,
    ) -> JobService:
        store = JobStore(
            max_jobs=max_jobs,
            database_path=tmp_path / "jobs.sqlite3",
            max_log_lines=max_log_lines,
        )
        return JobService(
            store,
            max_running=max_running,
            process_job_fn=process_job_fn or _noop_process_job,
        )

    return _make


def test_enqueue_persists_queued_job(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service(max_jobs=10)

    # Act
    job = job_service.enqueue("https://example.com/a")

    # Assert
    assert job.status == JobStatus.queued
    assert job_service.get(job.id) == job


def test_enqueue_rejects_when_unfinished_at_capacity(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service(max_jobs=2)
    job_service.enqueue("https://example.com/1")
    job_service.enqueue("https://example.com/2")

    # Act / Assert
    with pytest.raises(JobCapacityFull):
        job_service.enqueue("https://example.com/3")


@pytest.mark.asyncio
async def test_submit_returns_job_id(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service(max_running=0)

    # Act
    job_id = await job_service.submit("https://example.com/a")

    # Assert
    job = job_service.get(job_id)
    assert isinstance(job, QueuedJob)
    assert job.id == job_id


@pytest.mark.asyncio
async def test_submit_claims_queued_job(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    async def hang(_job_service: JobService, _job_id: JobId) -> None:
        await asyncio.Future()

    job_service = make_job_service(max_running=1, process_job_fn=hang)

    # Act
    job_id = await job_service.submit("https://example.com/a")

    # Assert
    assert isinstance(job_service.get(job_id), RunningJob)
    await job_service.shutdown()


@pytest.mark.asyncio
async def test_cancel_queued_job_marks_cancelled(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service()
    job = job_service.enqueue("https://example.com/video")

    # Act
    cancelled = await job_service.cancel(job.id)

    # Assert
    assert cancelled is not None
    assert cancelled.status == JobStatus.cancelled
    assert job_service.get(job.id) == cancelled


@pytest.mark.asyncio
async def test_cancel_running_job_marks_cancelled(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_began = asyncio.Event()
    process_task_cancelled = asyncio.Event()

    async def hang_until_cancelled(_job_service: JobService, _job_id: JobId) -> None:
        job_began.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            process_task_cancelled.set()
            raise

    job_service = make_job_service(
        max_running=1,
        process_job_fn=hang_until_cancelled,
    )
    job_id = await job_service.submit("https://example.com/video")
    await job_began.wait()

    # Act
    cancelled = await job_service.cancel(job_id)

    # Assert
    assert cancelled is not None
    assert cancelled.status == JobStatus.cancelled
    assert isinstance(job_service.get(job_id), CancelledJob)
    assert process_task_cancelled.is_set()
    await job_service.shutdown()


@pytest.mark.asyncio
async def test_cancel_finished_job_returns_none(tmp_path: Path) -> None:
    # Arrange
    job_id = JobId("finished")

    with JobStore(
        max_jobs=100,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=2000,
    ) as store:
        store.save_metadata(
            SucceededJob(
                id=job_id,
                url=_URL,
                created_at=_CREATED,
                started_at=_STARTED,
                finished_at=_FINISHED,
                exit_code=0,
                log=JobLog(),
            )
        )
        job_service = JobService(
            store,
            max_running=0,
            process_job_fn=_noop_process_job,
        )

        # Act
        cancelled = await job_service.cancel(job_id)

    # Assert
    assert cancelled is None


@pytest.mark.asyncio
async def test_requeue_unfinished_jobs_requeues_running(tmp_path: Path) -> None:
    # Arrange
    job_id = JobId("running")
    db_path = tmp_path / "jobs.sqlite3"

    with JobStore(max_jobs=10, database_path=db_path, max_log_lines=100) as store:
        store.save_metadata(
            RunningJob(
                id=job_id,
                url=_URL,
                created_at=_CREATED,
                started_at=_STARTED,
                log=JobLog(),
            )
        )
        job_service = JobService(
            store,
            max_running=0,
            process_job_fn=_noop_process_job,
        )

        # Act
        await job_service.requeue_unfinished_jobs()

        # Assert
        assert isinstance(job_service.get(job_id), QueuedJob)
