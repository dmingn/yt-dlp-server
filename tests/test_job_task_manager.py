import asyncio
from collections.abc import Callable

import pytest

from yt_dlp_server.job_task_manager import JobTaskManager
from yt_dlp_server.models import JobId


def _claim_from(pending: list[JobId]) -> Callable[[], JobId | None]:
    def claim() -> JobId | None:
        if not pending:
            return None
        return pending.pop(0)

    return claim


@pytest.mark.asyncio
async def test_claim_queued_jobs_up_to_max_running() -> None:
    # Arrange
    job_id_1 = JobId("job-1")
    job_id_2 = JobId("job-2")
    job_id_1_began = asyncio.Event()
    running: list[JobId] = []
    pending = [job_id_1, job_id_2]

    async def hang(job_id: JobId) -> None:
        running.append(job_id)
        if job_id == job_id_1:
            job_id_1_began.set()
        await asyncio.Future()

    task_manager = JobTaskManager(
        max_running=1,
        claim_next_job_fn=_claim_from(pending),
        process_job_fn=hang,
    )

    # Act
    await task_manager.claim_queued_jobs_up_to_max_running()
    await job_id_1_began.wait()

    # Assert
    assert running == [job_id_1]
    assert pending == [job_id_2]

    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_claim_queued_jobs_up_to_max_running_starts_multiple() -> None:
    # Arrange
    job_id_1 = JobId("job-1")
    job_id_2 = JobId("job-2")
    both_began = asyncio.Event()
    running: list[JobId] = []
    pending = [job_id_1, job_id_2]

    async def hang(job_id: JobId) -> None:
        running.append(job_id)
        if len(running) == 2:
            both_began.set()
        await asyncio.Future()

    task_manager = JobTaskManager(
        max_running=2,
        claim_next_job_fn=_claim_from(pending),
        process_job_fn=hang,
    )

    # Act
    await task_manager.claim_queued_jobs_up_to_max_running()
    await both_began.wait()

    # Assert
    assert running == [job_id_1, job_id_2]
    assert pending == []

    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_claim_queued_jobs_up_to_max_running_continues_as_tasks_finish() -> None:
    # Arrange
    job_id_1 = JobId("job-1")
    job_id_2 = JobId("job-2")
    process_order: list[JobId] = []
    job_id_1_began = asyncio.Event()
    job_id_2_began = asyncio.Event()
    allow_finish = asyncio.Event()
    pending = [job_id_1, job_id_2]

    async def process_and_block_until_allowed(job_id: JobId) -> None:
        process_order.append(job_id)
        if job_id == job_id_1:
            job_id_1_began.set()
        elif job_id == job_id_2:
            job_id_2_began.set()
        await allow_finish.wait()

    task_manager = JobTaskManager(
        max_running=1,
        claim_next_job_fn=_claim_from(pending),
        process_job_fn=process_and_block_until_allowed,
    )

    # Act
    await task_manager.claim_queued_jobs_up_to_max_running()
    await job_id_1_began.wait()
    assert process_order == [job_id_1]
    allow_finish.set()
    await job_id_2_began.wait()

    # Assert
    assert process_order == [job_id_1, job_id_2]
    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_cancel_stops_running_task() -> None:
    # Arrange
    job_id = JobId("job-1")
    job_began = asyncio.Event()
    process_task_cancelled = asyncio.Event()
    pending = [job_id]

    async def hang(_job_id: JobId) -> None:
        job_began.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            process_task_cancelled.set()
            raise

    task_manager = JobTaskManager(
        max_running=1,
        claim_next_job_fn=_claim_from(pending),
        process_job_fn=hang,
    )
    await task_manager.claim_queued_jobs_up_to_max_running()
    await job_began.wait()

    # Act
    await task_manager.cancel(job_id)

    # Assert
    assert process_task_cancelled.is_set()
    await task_manager.shutdown()


@pytest.mark.asyncio
async def test_shutdown_cancels_running_tasks() -> None:
    # Arrange
    job_id_1 = JobId("job-1")
    job_id_2 = JobId("job-2")
    job_began = asyncio.Event()
    cancelled_count = 0
    pending = [job_id_1, job_id_2]

    async def hang(_job_id: JobId) -> None:
        nonlocal cancelled_count
        job_began.set()
        try:
            await asyncio.Future()
        except asyncio.CancelledError:
            cancelled_count += 1
            raise

    task_manager = JobTaskManager(
        max_running=2,
        claim_next_job_fn=_claim_from(pending),
        process_job_fn=hang,
    )
    await task_manager.claim_queued_jobs_up_to_max_running()
    await job_began.wait()

    # Act
    await task_manager.shutdown()

    # Assert
    assert cancelled_count == 2
