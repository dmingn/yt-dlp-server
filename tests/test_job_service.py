import pytest

from yt_dlp_server.job_service import JobCapacityFull, JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import JobStatus


def _make_jobs(*, max_jobs: int = 100, max_log_lines: int = 2000) -> JobService:
    return JobService(
        JobStore(max_jobs=max_jobs),
        max_log_lines=max_log_lines,
    )


def test_enqueue_and_summaries() -> None:
    # Arrange
    jobs = _make_jobs(max_jobs=10)

    # Act
    job = jobs.enqueue("https://example.com/a")

    # Assert
    assert job.status == JobStatus.queued
    assert jobs.get(job.id) is job
    assert jobs.list_summaries()[0].id == job.id
    assert jobs.list_summaries()[0].log_line_count == 0


def test_store_evicts_oldest_finished_jobs() -> None:
    # Arrange
    jobs = _make_jobs(max_jobs=2)
    first = jobs.enqueue("https://example.com/1")
    second = jobs.enqueue("https://example.com/2")
    jobs.mark_running(first.id)
    jobs.mark_succeeded(first.id)
    jobs.mark_running(second.id)
    jobs.mark_succeeded(second.id)

    # Act
    third = jobs.enqueue("https://example.com/3")

    # Assert
    assert jobs.get(first.id) is None
    assert jobs.get(second.id) is not None
    assert jobs.get(third.id) is not None


def test_enqueue_rejects_when_unfinished_at_capacity() -> None:
    # Arrange
    jobs = _make_jobs(max_jobs=2)
    jobs.enqueue("https://example.com/1")
    jobs.enqueue("https://example.com/2")

    # Act / Assert
    with pytest.raises(JobCapacityFull):
        jobs.enqueue("https://example.com/3")


@pytest.mark.asyncio
async def test_cancel_queued_job_marks_cancelled() -> None:
    # Arrange
    jobs = _make_jobs()
    job = jobs.enqueue("https://example.com/video")

    # Act
    cancelled = await jobs.cancel(job.id)

    # Assert
    assert cancelled is not None
    assert cancelled.status == JobStatus.cancelled
    assert jobs.get(job.id) is cancelled


@pytest.mark.asyncio
async def test_cancel_finished_job_returns_none() -> None:
    # Arrange
    jobs = _make_jobs()
    job = jobs.enqueue("https://example.com/video")
    jobs.mark_running(job.id)
    jobs.mark_succeeded(job.id)

    # Act
    cancelled = await jobs.cancel(job.id)

    # Assert
    assert cancelled is None
