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
    ImmediateRunningJob,
    ImmediateSucceededJob,
    JobId,
    JobLog,
    JobStatus,
    QueuedJob,
    RunningJob,
    ScheduledJob,
    ScheduledRunningJob,
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
        poll_interval_seconds: float = 1,
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
            poll_interval_seconds=poll_interval_seconds,
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
async def test_submit_leaves_job_queued(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service(max_running=1)

    # Act
    job_id = await job_service.submit("https://example.com/a")

    # Assert
    job = job_service.get(job_id)
    assert isinstance(job, QueuedJob)
    assert job.id == job_id


@pytest.mark.asyncio
async def test_try_start_jobs_starts_queued_up_to_max_running(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    async def hang(_job_service: JobService, _job_id: JobId) -> None:
        await asyncio.Future()

    job_service = make_job_service(max_running=1, process_job_fn=hang)
    first_id = await job_service.submit("https://example.com/a")
    second_id = await job_service.submit("https://example.com/b")

    # Act
    job_service.try_start_jobs()

    # Assert
    assert isinstance(job_service.get(first_id), RunningJob)
    assert isinstance(job_service.get(second_id), QueuedJob)
    await job_service.shutdown()


@pytest.mark.asyncio
async def test_try_start_jobs_after_shutdown_does_not_claim(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_service = make_job_service(max_running=1)
    job_id = await job_service.submit("https://example.com/a")
    await job_service.shutdown()

    # Act
    job_service.try_start_jobs()

    # Assert
    assert isinstance(job_service.get(job_id), QueuedJob)


@pytest.mark.asyncio
async def test_poll_loop_continues_after_try_start_jobs_raises(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    job_began = asyncio.Event()

    async def hang(_job_service: JobService, _job_id: JobId) -> None:
        job_began.set()
        await asyncio.Future()

    job_service = make_job_service(
        max_running=1,
        process_job_fn=hang,
        poll_interval_seconds=0.01,
    )
    calls = 0
    original = job_service.try_start_jobs

    def flaky_try_start_jobs() -> None:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError("boom")
        original()

    job_service.try_start_jobs = flaky_try_start_jobs  # type: ignore[method-assign]
    await job_service.submit("https://example.com/a")

    # Act
    await job_service.start_polling()
    await asyncio.wait_for(job_began.wait(), timeout=1)

    # Assert
    assert calls >= 2
    await job_service.shutdown()


@pytest.mark.asyncio
async def test_try_start_jobs_starts_next_after_slot_frees(
    make_job_service: Callable[..., JobService],
) -> None:
    # Arrange
    first_began = asyncio.Event()
    second_began = asyncio.Event()
    allow_finish = asyncio.Event()
    started: list[JobId] = []

    async def process(_job_service: JobService, job_id: JobId) -> None:
        started.append(job_id)
        if len(started) == 1:
            first_began.set()
            await allow_finish.wait()
            return
        second_began.set()
        await asyncio.Future()

    job_service = make_job_service(max_running=1, process_job_fn=process)
    first_id = await job_service.submit("https://example.com/a")
    second_id = await job_service.submit("https://example.com/b")
    job_service.try_start_jobs()
    await first_began.wait()
    first_task = job_service._task_manager._running_tasks[first_id]

    # Act
    allow_finish.set()
    await first_task
    job_service.try_start_jobs()
    await second_began.wait()

    # Assert
    assert started == [first_id, second_id]
    assert isinstance(job_service.get(second_id), RunningJob)
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
    job_service.try_start_jobs()
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
            ImmediateSucceededJob(
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
@pytest.mark.parametrize(
    ("running", "expected"),
    [
        (
            ImmediateRunningJob(
                id=JobId("running"),
                url=_URL,
                created_at=_CREATED,
                started_at=_STARTED,
                log=JobLog(),
            ),
            QueuedJob(
                id=JobId("running"),
                url=_URL,
                created_at=_CREATED,
            ),
        ),
        (
            ScheduledRunningJob(
                id=JobId("running"),
                url=_URL,
                created_at=_CREATED,
                started_at=_STARTED,
                scheduled_at=datetime.fromisoformat("2026-01-01T03:00:00+00:00"),
                log=JobLog(),
            ),
            ScheduledJob(
                id=JobId("running"),
                url=_URL,
                created_at=_CREATED,
                scheduled_at=datetime.fromisoformat("2026-01-01T03:00:00+00:00"),
            ),
        ),
    ],
)
async def test_restore_waiting_jobs_from_running(
    tmp_path: Path,
    running: RunningJob,
    expected: QueuedJob | ScheduledJob,
) -> None:
    # Arrange
    db_path = tmp_path / "jobs.sqlite3"

    with JobStore(max_jobs=10, database_path=db_path, max_log_lines=100) as store:
        store.save_metadata(running)
        job_service = JobService(
            store,
            max_running=0,
            process_job_fn=_noop_process_job,
        )

        # Act
        job_service.restore_waiting_jobs()

        # Assert
        assert job_service.get(running.id) == expected
