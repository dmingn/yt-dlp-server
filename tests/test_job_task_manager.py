import asyncio

import pytest

from yt_dlp_server.job_task_manager import JobTaskManager
from yt_dlp_server.models import JobId


@pytest.mark.asyncio
async def test_spawn_starts_task() -> None:
    # Arrange
    job_id = JobId("job")
    job_began = asyncio.Event()

    async def hang(_job_id: JobId) -> None:
        job_began.set()
        await asyncio.Future()

    task_manager = JobTaskManager(process_job_fn=hang)

    # Act
    task_manager.spawn(job_id)
    await job_began.wait()

    # Assert
    assert task_manager.running_count == 1
    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_spawn_ignores_duplicate_id() -> None:
    # Arrange
    job_id = JobId("job")
    job_began = asyncio.Event()
    started: list[JobId] = []

    async def hang(_job_id: JobId) -> None:
        started.append(_job_id)
        job_began.set()
        await asyncio.Future()

    task_manager = JobTaskManager(process_job_fn=hang)

    # Act
    task_manager.spawn(job_id)
    task_manager.spawn(job_id)
    await job_began.wait()

    # Assert
    assert started == [job_id]
    assert task_manager.running_count == 1
    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_spawn_after_shutdown_is_ignored() -> None:
    # Arrange
    async def hang(_job_id: JobId) -> None:
        await asyncio.Future()

    task_manager = JobTaskManager(process_job_fn=hang)
    await task_manager.shutdown()

    # Act
    task_manager.spawn(JobId("job"))

    # Assert
    assert task_manager.running_count == 0


@pytest.mark.asyncio
async def test_cancel_stops_running_task() -> None:
    # Arrange
    job_id = JobId("job")
    job_began = asyncio.Event()
    process_task_cancelled = asyncio.Event()

    async def hang(_job_id: JobId) -> None:
        job_began.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            process_task_cancelled.set()
            raise

    task_manager = JobTaskManager(process_job_fn=hang)
    task_manager.spawn(job_id)
    await job_began.wait()

    # Act
    await task_manager.cancel(job_id)

    # Assert
    assert process_task_cancelled.is_set()
    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_running_tasks() -> None:
    # Arrange
    job_began = asyncio.Event()
    cancelled_count = 0

    async def hang(_job_id: JobId) -> None:
        nonlocal cancelled_count
        job_began.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled_count += 1
            raise

    task_manager = JobTaskManager(process_job_fn=hang)
    task_manager.spawn(JobId("job-1"))
    task_manager.spawn(JobId("job-2"))
    await job_began.wait()

    # Act
    await task_manager.shutdown()

    # Assert
    assert cancelled_count == 2
