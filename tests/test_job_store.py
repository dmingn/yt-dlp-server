from datetime import datetime
from pathlib import Path

from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import JobStatus, QueuedJob, RunningJob, SucceededJob


def _queued(
    job_id: str,
    *,
    url: str = "https://example.com/a",
    created_at: str,
) -> QueuedJob:
    return QueuedJob.model_validate(
        {
            "id": job_id,
            "url": url,
            "created_at": created_at,
        }
    )


def test_save_metadata_get_round_trip_with_logs(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )
    queued = QueuedJob.model_validate(
        {
            "id": "job-1",
            "url": "https://example.com/a",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    store.save_metadata(queued)
    running = store.get_job("job-1")
    assert isinstance(running, QueuedJob)
    started = running.start(started_at=running.created_at)
    store.save_metadata(started)
    store.append_log("job-1", "line-1\n")
    store.append_log("job-1", "line-2\n")

    # Act
    loaded = store.get_job("job-1")

    # Assert
    assert isinstance(loaded, RunningJob)
    assert loaded.log.lines == ("line-1\n", "line-2\n")
    store.close()


def test_append_log_respects_max_lines(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=2,
    )
    queued = QueuedJob.model_validate(
        {
            "id": "job-1",
            "url": "https://example.com/a",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    store.save_metadata(queued)
    running = queued.start(started_at=queued.created_at)
    store.save_metadata(running)

    # Act
    store.append_log("job-1", "a\n")
    store.append_log("job-1", "b\n")
    store.append_log("job-1", "c\n")

    # Assert
    loaded = store.get_job("job-1")
    assert isinstance(loaded, RunningJob)
    assert loaded.log.lines == ("b\n", "c\n")
    store.close()


def test_evict_deletes_log_lines(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=1,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )
    first = QueuedJob.model_validate(
        {
            "id": "job-1",
            "url": "https://example.com/1",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    store.save_metadata(first)
    running = first.start(started_at=first.created_at)
    store.save_metadata(running)
    store.append_log("job-1", "keep?\n")
    succeeded = store.get_job("job-1")
    assert isinstance(succeeded, RunningJob)
    store.save_metadata(succeeded.succeed(finished_at=succeeded.started_at))

    second = QueuedJob.model_validate(
        {
            "id": "job-2",
            "url": "https://example.com/2",
            "created_at": "2026-01-02T00:00:00+00:00",
        }
    )

    # Act
    store.save_metadata(second)

    # Assert
    assert store.get_job("job-1") is None
    remaining = store._conn.execute(
        "SELECT COUNT(*) AS n FROM job_log_lines WHERE job_id = ?",
        ("job-1",),
    ).fetchone()
    assert int(remaining["n"]) == 0
    assert isinstance(store.get_job("job-2"), QueuedJob)
    store.close()


def test_claim_oldest_queued_returns_none_when_empty(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )

    # Act / Assert
    assert (
        store.claim_oldest_queued(
            started_at=datetime.fromisoformat("2026-01-01T12:00:00+00:00")
        )
        is None
    )
    store.close()


def test_claim_oldest_queued_takes_oldest_and_marks_running(
    tmp_path: Path,
) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )
    store.save_metadata(_queued("older", created_at="2026-01-01T00:00:00+00:00"))
    store.save_metadata(
        _queued(
            "newer",
            url="https://example.com/b",
            created_at="2026-01-02T00:00:00+00:00",
        )
    )
    started_at = datetime.fromisoformat("2026-01-03T00:00:00+00:00")

    # Act
    claimed = store.claim_oldest_queued(started_at=started_at)

    # Assert
    assert isinstance(claimed, RunningJob)
    assert claimed.id == "older"
    assert claimed.started_at == started_at
    assert isinstance(store.get_job("older"), RunningJob)
    assert isinstance(store.get_job("newer"), QueuedJob)

    # Act
    second = store.claim_oldest_queued(
        started_at=datetime.fromisoformat("2026-01-03T01:00:00+00:00")
    )

    # Assert
    assert isinstance(second, RunningJob)
    assert second.id == "newer"
    assert store.claim_oldest_queued(started_at=started_at) is None
    store.close()


def test_claim_oldest_queued_skips_non_queued(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )
    queued = _queued("job-1", created_at="2026-01-01T00:00:00+00:00")
    store.save_metadata(queued)
    running = queued.start(
        started_at=datetime.fromisoformat("2026-01-01T01:00:00+00:00")
    )
    store.save_metadata(running)
    store.save_metadata(
        running.succeed(finished_at=datetime.fromisoformat("2026-01-01T02:00:00+00:00"))
    )

    store.save_metadata(
        _queued(
            "job-2",
            url="https://example.com/2",
            created_at="2026-01-02T00:00:00+00:00",
        )
    )
    started_at = datetime.fromisoformat("2026-01-03T00:00:00+00:00")

    # Act
    claimed = store.claim_oldest_queued(started_at=started_at)

    # Assert
    assert isinstance(claimed, RunningJob)
    assert claimed.id == "job-2"
    store.close()


def test_requeue_running_clears_logs(tmp_path: Path) -> None:
    # Arrange
    store = JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    )
    queued = QueuedJob.model_validate(
        {
            "id": "job-1",
            "url": "https://example.com/a",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    store.save_metadata(queued)
    running = queued.start(started_at=queued.created_at)
    store.save_metadata(running)
    store.append_log("job-1", "partial\n")

    # Act
    store.requeue_running()

    # Assert
    loaded = store.get_job("job-1")
    assert isinstance(loaded, QueuedJob)
    assert loaded.status == JobStatus.queued
    remaining = store._conn.execute(
        "SELECT COUNT(*) AS n FROM job_log_lines WHERE job_id = ?",
        ("job-1",),
    ).fetchone()
    assert int(remaining["n"]) == 0
    store.close()


def test_succeeded_job_survives_reopen(tmp_path: Path) -> None:
    # Arrange
    db_path = tmp_path / "jobs.sqlite3"
    store = JobStore(max_jobs=10, database_path=db_path, max_log_lines=100)
    queued = QueuedJob.model_validate(
        {
            "id": "job-1",
            "url": "https://example.com/a",
            "created_at": "2026-01-01T00:00:00+00:00",
        }
    )
    store.save_metadata(queued)
    running = queued.start(started_at=queued.created_at)
    store.save_metadata(running)
    store.append_log("job-1", "done\n")
    current = store.get_job("job-1")
    assert isinstance(current, RunningJob)
    store.save_metadata(current.succeed(finished_at=current.started_at))
    store.close()

    # Act
    reopened = JobStore(max_jobs=10, database_path=db_path, max_log_lines=100)
    loaded = reopened.get_job("job-1")

    # Assert
    assert isinstance(loaded, SucceededJob)
    assert loaded.log.lines == ("done\n",)
    reopened.close()
