from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Self

from yt_dlp_server.db import connect
from yt_dlp_server.models import (
    FINISHED_STATUSES,
    JOB_ADAPTER,
    UNFINISHED_STATUSES,
    ImmediateRunningJob,
    Job,
    JobId,
    JobLog,
    JobStatus,
    QueuedJob,
    RunningJob,
)


class JobStore:
    """SQLite-backed job registry with a bounded number of retained jobs."""

    def __init__(
        self,
        *,
        max_jobs: int,
        database_path: Path,
        max_log_lines: int,
    ) -> None:
        self._max_jobs = max_jobs
        self._max_log_lines = max_log_lines
        self._conn = connect(database_path)

    @property
    def max_jobs(self) -> int:
        return self._max_jobs

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    def save_metadata(self, job: Job) -> None:
        with self._conn:
            self._upsert_metadata(job)
        self._evict_finished()

    def get_job(self, job_id: JobId) -> Job | None:
        row = self._conn.execute(
            "SELECT * FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row is None:
            return None
        return self._job_from_row(row)

    def list_jobs(self) -> list[Job]:
        rows = self._conn.execute(
            "SELECT * FROM jobs ORDER BY created_at DESC",
        ).fetchall()
        return [self._job_from_row(row) for row in rows]

    def unfinished_count(self) -> int:
        placeholders = ",".join("?" * len(UNFINISHED_STATUSES))
        row = self._conn.execute(
            f"SELECT COUNT(*) AS n FROM jobs WHERE status IN ({placeholders})",
            UNFINISHED_STATUSES,
        ).fetchone()
        return int(row["n"])

    def append_log(self, job_id: JobId, line: str) -> None:
        with self._conn:
            next_seq_row = self._conn.execute(
                "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM job_log_lines WHERE job_id = ?",
                (job_id,),
            ).fetchone()
            next_seq = int(next_seq_row["max_seq"]) + 1
            self._conn.execute(
                "INSERT INTO job_log_lines (job_id, seq, line) VALUES (?, ?, ?)",
                (job_id, next_seq, line),
            )
            self._conn.execute(
                """
                DELETE FROM job_log_lines
                WHERE job_id = ?
                  AND seq <= (
                    SELECT MAX(seq) FROM job_log_lines WHERE job_id = ?
                  ) - ?
                """,
                (job_id, job_id, self._max_log_lines),
            )

    def claim_oldest_queued(
        self, *, started_at: datetime
    ) -> ImmediateRunningJob | None:
        """Take ownership of the oldest queued job by marking it running."""
        with self._conn:
            row = self._conn.execute(
                """
                SELECT * FROM jobs
                WHERE status = ?
                ORDER BY created_at ASC
                LIMIT 1
                """,
                (JobStatus.queued.value,),
            ).fetchone()
            if row is None:
                return None

            job = self._job_from_row(row)
            assert isinstance(job, QueuedJob)

            running = job.start(started_at=started_at)
            self._upsert_metadata(running)
            return running

    def restore_waiting_jobs(self) -> None:
        running = [job for job in self.list_jobs() if isinstance(job, RunningJob)]
        for job in running:
            with self._conn:
                self._upsert_metadata(job.to_waiting())
                self._conn.execute(
                    "DELETE FROM job_log_lines WHERE job_id = ?",
                    (job.id,),
                )
            self._evict_finished()

    def _upsert_metadata(self, job: Job) -> None:
        row = job.model_dump(mode="json", exclude={"log"})
        self._conn.execute(
            """
            INSERT INTO jobs (
              id, url, status, created_at, started_at, finished_at,
              exit_code, error, scheduled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
              url = excluded.url,
              status = excluded.status,
              created_at = excluded.created_at,
              started_at = excluded.started_at,
              finished_at = excluded.finished_at,
              exit_code = excluded.exit_code,
              error = excluded.error,
              scheduled_at = excluded.scheduled_at
            """,
            (
                row["id"],
                row["url"],
                row["status"],
                row["created_at"],
                row.get("started_at"),
                row.get("finished_at"),
                row.get("exit_code"),
                row.get("error"),
                row.get("scheduled_at"),
            ),
        )

    def _evict_finished(self) -> None:
        with self._conn:
            while True:
                count_row = self._conn.execute(
                    "SELECT COUNT(*) AS n FROM jobs"
                ).fetchone()
                if int(count_row["n"]) <= self._max_jobs:
                    return
                placeholders = ",".join("?" * len(FINISHED_STATUSES))
                oldest = self._conn.execute(
                    f"""
                    SELECT id FROM jobs
                    WHERE status IN ({placeholders})
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    FINISHED_STATUSES,
                ).fetchone()
                if oldest is None:
                    return
                self._conn.execute("DELETE FROM jobs WHERE id = ?", (oldest["id"],))

    def _log_lines(self, job_id: JobId) -> tuple[str, ...]:
        rows = self._conn.execute(
            """
            SELECT line FROM job_log_lines
            WHERE job_id = ?
            ORDER BY seq ASC
            """,
            (job_id,),
        ).fetchall()
        return tuple(str(row["line"]) for row in rows)

    def _job_from_row(self, row: sqlite3.Row) -> Job:
        return JOB_ADAPTER.validate_python(
            {
                **dict(row),
                "log": JobLog(lines=self._log_lines(JobId(str(row["id"])))),
            }
        )
