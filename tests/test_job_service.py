import pytest

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import JobStatus


def _make_job_service(*, max_jobs: int = 100, max_log_lines: int = 2000) -> JobService:
    return JobService(
        JobStore(max_jobs=max_jobs),
        max_log_lines=max_log_lines,
    )


def test_enqueue_and_summaries() -> None:
    # Arrange
    job_service = _make_job_service(max_jobs=10)

    # Act
    job = job_service.enqueue("https://example.com/a")

    # Assert
    assert job.status == JobStatus.queued
    assert job_service.get(job.id) is job
    assert job_service.list_summaries()[0].id == job.id
    assert job_service.list_summaries()[0].log_line_count == 0


def test_store_evicts_oldest_finished_jobs() -> None:
    # Arrange
    job_service = _make_job_service(max_jobs=2)
    first = job_service.enqueue("https://example.com/1")
    second = job_service.enqueue("https://example.com/2")
    job_service.mark_running(first.id)
    job_service.mark_succeeded(first.id)
    job_service.mark_running(second.id)
    job_service.mark_succeeded(second.id)

    # Act
    third = job_service.enqueue("https://example.com/3")

    # Assert
    assert job_service.get(first.id) is None
    assert job_service.get(second.id) is not None
    assert job_service.get(third.id) is not None


def test_enqueue_rejects_when_unfinished_at_capacity() -> None:
    # Arrange
    job_service = _make_job_service(max_jobs=2)
    job_service.enqueue("https://example.com/1")
    job_service.enqueue("https://example.com/2")

    # Act / Assert
    with pytest.raises(JobCapacityFull):
        job_service.enqueue("https://example.com/3")


@pytest.mark.asyncio
async def test_cancel_queued_job_marks_cancelled() -> None:
    # Arrange
    job_service = _make_job_service()
    job = job_service.enqueue("https://example.com/video")

    # Act
    cancelled = await job_service.cancel(job.id)

    # Assert
    assert cancelled is not None
    assert cancelled.status == JobStatus.cancelled
    assert job_service.get(job.id) is cancelled


@pytest.mark.asyncio
async def test_cancel_finished_job_returns_none() -> None:
    # Arrange
    job_service = _make_job_service()
    job = job_service.enqueue("https://example.com/video")
    job_service.mark_running(job.id)
    job_service.mark_succeeded(job.id)

    # Act
    cancelled = await job_service.cancel(job.id)

    # Assert
    assert cancelled is None
