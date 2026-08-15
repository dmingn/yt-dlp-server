import sqlite3
from pathlib import Path

import pytest

from yt_dlp_server.db import SCHEMA_VERSION, SchemaVersionError, _migrate_to_1, connect
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import JobId, JobStatus, QueuedJob

_JOBS_COLUMNS = (
    "id",
    "url",
    "status",
    "created_at",
    "started_at",
    "finished_at",
    "exit_code",
    "error",
    "scheduled_at",
)


def test_connect_applies_schema_version(tmp_path: Path) -> None:
    # Arrange / Act
    conn = connect(tmp_path / "jobs.sqlite3")

    # Assert
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert version == SCHEMA_VERSION
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "jobs" in tables
    assert "job_log_lines" in tables
    columns = tuple(
        str(row[1]) for row in conn.execute("PRAGMA table_info(jobs)").fetchall()
    )
    assert columns == _JOBS_COLUMNS
    conn.close()


def test_migrate_rejects_newer_schema(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "jobs.sqlite3"
    conn = connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    # Act / Assert
    with pytest.raises(SchemaVersionError):
        connect(path)


def test_migrate_from_v1_keeps_existing_jobs(tmp_path: Path) -> None:
    # Arrange: schema v1 database with one queued job
    path = tmp_path / "jobs.sqlite3"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    _migrate_to_1(conn)
    conn.execute("PRAGMA user_version = 1")
    conn.execute(
        """
        INSERT INTO jobs (id, url, status, created_at, started_at, finished_at, exit_code, error)
        VALUES (?, ?, ?, ?, NULL, NULL, NULL, NULL)
        """,
        (
            "job-1",
            "https://example.com/a",
            JobStatus.queued.value,
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    # Act
    with JobStore(max_jobs=10, database_path=path, max_log_lines=100) as store:
        job = store.get_job(JobId("job-1"))

    # Assert
    assert isinstance(job, QueuedJob)
    assert job.id == "job-1"
    assert str(job.url) == "https://example.com/a"
