from collections.abc import Iterator
from datetime import datetime
from pathlib import Path

import pytest

from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import (
    CancelledJob,
    FailedJob,
    Job,
    JobLog,
    JobStatus,
    QueuedJob,
    RunningJob,
    SucceededJob,
)

_CREATED_AT = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
_CREATED_AT_2 = datetime.fromisoformat("2026-01-02T00:00:00+00:00")
_CREATED_AT_3 = datetime.fromisoformat("2026-01-03T00:00:00+00:00")
_STARTED_AT = datetime.fromisoformat("2026-01-01T01:00:00+00:00")
_STARTED_AT_2 = datetime.fromisoformat("2026-01-02T01:00:00+00:00")
_FINISHED_AT = datetime.fromisoformat("2026-01-01T02:00:00+00:00")


@pytest.fixture
def job_store(tmp_path: Path) -> Iterator[JobStore]:
    with JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    ) as store:
        yield store


@pytest.mark.parametrize(
    "job",
    [
        pytest.param(
            QueuedJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
            ),
            id="queued",
        ),
        pytest.param(
            RunningJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                log=JobLog(),
            ),
            id="running",
        ),
        pytest.param(
            RunningJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                log=JobLog(lines=("line-1\n", "line-2\n")),
            ),
            id="running-with-logs",
        ),
        pytest.param(
            SucceededJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                exit_code=0,
                log=JobLog(lines=("done\n",)),
            ),
            id="succeeded",
        ),
        pytest.param(
            FailedJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                exit_code=1,
                log=JobLog(lines=("err\n",)),
                error="boom",
            ),
            id="failed",
        ),
        pytest.param(
            CancelledJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                finished_at=_FINISHED_AT,
                log=JobLog(),
            ),
            id="cancelled",
        ),
        pytest.param(
            CancelledJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                log=JobLog(lines=("partial\n",)),
            ),
            id="cancelled-from-running",
        ),
    ],
)
def test_save_job_round_trip(job_store: JobStore, job: Job) -> None:
    # Arrange
    job_store.save_metadata(job)
    log = getattr(job, "log", None)
    if log is not None:
        for line in log.lines:
            job_store.append_log(job.id, line)

    # Act
    loaded = job_store.get_job(job.id)

    # Assert
    assert loaded == job


def test_append_log_respects_max_lines(tmp_path: Path) -> None:
    # Arrange
    with JobStore(
        max_jobs=10,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=2,
    ) as job_store:
        job_store.save_metadata(
            RunningJob(
                id="job-1",
                url="https://example.com/a",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                log=JobLog(),
            )
        )

        # Act
        job_store.append_log("job-1", "a\n")
        job_store.append_log("job-1", "b\n")
        job_store.append_log("job-1", "c\n")

        # Assert
        loaded = job_store.get_job("job-1")
        assert isinstance(loaded, RunningJob)
        assert loaded.log.lines == ("b\n", "c\n")


def test_evict_removes_oldest_finished(tmp_path: Path) -> None:
    # Arrange
    with JobStore(
        max_jobs=2,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    ) as job_store:
        job_store.save_metadata(
            SucceededJob(
                id="older",
                url="https://example.com/1",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                exit_code=0,
                log=JobLog(),
            )
        )
        job_store.save_metadata(
            SucceededJob(
                id="newer",
                url="https://example.com/2",
                created_at=_CREATED_AT_2,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                exit_code=0,
                log=JobLog(),
            )
        )

        # Act
        job_store.save_metadata(
            QueuedJob(
                id="third",
                url="https://example.com/3",
                created_at=_CREATED_AT_3,
            )
        )

        # Assert
        assert job_store.get_job("older") is None
        assert job_store.get_job("newer") is not None
        assert job_store.get_job("third") is not None


def test_evict_does_not_remove_unfinished(tmp_path: Path) -> None:
    # Arrange
    with JobStore(
        max_jobs=1,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    ) as job_store:
        job_store.save_metadata(
            QueuedJob(
                id="first",
                url="https://example.com/1",
                created_at=_CREATED_AT,
            )
        )

        # Act
        job_store.save_metadata(
            QueuedJob(
                id="second",
                url="https://example.com/2",
                created_at=_CREATED_AT_2,
            )
        )

        # Assert
        assert job_store.get_job("first") is not None
        assert job_store.get_job("second") is not None


def test_evict_deletes_log_lines(tmp_path: Path) -> None:
    # Arrange
    with JobStore(
        max_jobs=1,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=100,
    ) as job_store:
        job_store.save_metadata(
            SucceededJob(
                id="job-1",
                url="https://example.com/1",
                created_at=_CREATED_AT,
                started_at=_STARTED_AT,
                finished_at=_FINISHED_AT,
                exit_code=0,
                log=JobLog(),
            )
        )
        job_store.append_log("job-1", "keep?\n")

        # Act
        job_store.save_metadata(
            QueuedJob(
                id="job-2",
                url="https://example.com/2",
                created_at=_CREATED_AT_2,
            )
        )

        # Assert
        assert job_store.get_job("job-1") is None
        remaining = job_store._conn.execute(
            "SELECT COUNT(*) AS n FROM job_log_lines WHERE job_id = ?",
            ("job-1",),
        ).fetchone()
        assert int(remaining["n"]) == 0
        assert isinstance(job_store.get_job("job-2"), QueuedJob)


def test_claim_oldest_queued_returns_none_when_empty(job_store: JobStore) -> None:
    # Act / Assert
    assert job_store.claim_oldest_queued(started_at=_STARTED_AT) is None


def test_claim_oldest_queued_claims_in_created_order(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        QueuedJob(
            id="older",
            url="https://example.com/a",
            created_at=_CREATED_AT,
        )
    )
    job_store.save_metadata(
        QueuedJob(
            id="newer",
            url="https://example.com/b",
            created_at=_CREATED_AT_2,
        )
    )

    # Act
    first = job_store.claim_oldest_queued(started_at=_STARTED_AT)
    second = job_store.claim_oldest_queued(started_at=_STARTED_AT_2)

    # Assert
    assert isinstance(first, RunningJob)
    assert first.id == "older"
    assert first.started_at == _STARTED_AT
    assert isinstance(second, RunningJob)
    assert second.id == "newer"
    assert second.started_at == _STARTED_AT_2
    assert job_store.claim_oldest_queued(started_at=_STARTED_AT) is None


def test_claim_oldest_queued_skips_non_queued(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        SucceededJob(
            id="job-1",
            url="https://example.com/a",
            created_at=_CREATED_AT,
            started_at=_STARTED_AT,
            finished_at=_FINISHED_AT,
            exit_code=0,
            log=JobLog(),
        )
    )
    job_store.save_metadata(
        QueuedJob(
            id="job-2",
            url="https://example.com/2",
            created_at=_CREATED_AT_2,
        )
    )

    # Act
    claimed = job_store.claim_oldest_queued(started_at=_STARTED_AT)

    # Assert
    assert isinstance(claimed, RunningJob)
    assert claimed.id == "job-2"


def test_requeue_running_clears_logs(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        RunningJob(
            id="job-1",
            url="https://example.com/a",
            created_at=_CREATED_AT,
            started_at=_STARTED_AT,
            log=JobLog(),
        )
    )
    job_store.append_log("job-1", "partial\n")

    # Act
    job_store.requeue_running()

    # Assert
    loaded = job_store.get_job("job-1")
    assert isinstance(loaded, QueuedJob)
    assert loaded.status == JobStatus.queued
    remaining = job_store._conn.execute(
        "SELECT COUNT(*) AS n FROM job_log_lines WHERE job_id = ?",
        ("job-1",),
    ).fetchone()
    assert int(remaining["n"]) == 0


def test_list_jobs_orders_by_created_at_desc(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        QueuedJob(
            id="older",
            url="https://example.com/a",
            created_at=_CREATED_AT,
        )
    )
    job_store.save_metadata(
        QueuedJob(
            id="newer",
            url="https://example.com/b",
            created_at=_CREATED_AT_2,
        )
    )

    # Act
    jobs = job_store.list_jobs()

    # Assert
    assert [job.id for job in jobs] == ["newer", "older"]


def test_unfinished_count(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        QueuedJob(
            id="queued",
            url="https://example.com/a",
            created_at=_CREATED_AT,
        )
    )
    job_store.save_metadata(
        RunningJob(
            id="running",
            url="https://example.com/b",
            created_at=_CREATED_AT_2,
            started_at=_STARTED_AT_2,
            log=JobLog(),
        )
    )
    job_store.save_metadata(
        SucceededJob(
            id="done",
            url="https://example.com/c",
            created_at=_CREATED_AT_3,
            started_at=_STARTED_AT,
            finished_at=_FINISHED_AT,
            exit_code=0,
            log=JobLog(),
        )
    )

    # Act / Assert
    assert job_store.unfinished_count() == 2


def test_unfinished_ids_orders_by_created_at_asc(job_store: JobStore) -> None:
    # Arrange
    job_store.save_metadata(
        SucceededJob(
            id="done",
            url="https://example.com/a",
            created_at=_CREATED_AT,
            started_at=_STARTED_AT,
            finished_at=_FINISHED_AT,
            exit_code=0,
            log=JobLog(),
        )
    )
    job_store.save_metadata(
        QueuedJob(
            id="older",
            url="https://example.com/b",
            created_at=_CREATED_AT_2,
        )
    )
    job_store.save_metadata(
        RunningJob(
            id="running",
            url="https://example.com/c",
            created_at=_CREATED_AT_3,
            started_at=_STARTED_AT_2,
            log=JobLog(),
        )
    )

    # Act / Assert
    assert job_store.unfinished_ids() == ["older", "running"]
