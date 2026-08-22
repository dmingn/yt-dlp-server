import asyncio
from collections.abc import Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

import pytest
from pydantic import AnyHttpUrl

from yt_dlp_server.job_service import JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import (
    FailedJob,
    ImmediateRunningJob,
    JobId,
    JobLog,
    JobStatus,
    RunningJob,
    ScheduledRunningJob,
    SucceededJob,
)
from yt_dlp_server.process_job import process_job

_URL = AnyHttpUrl("https://example.com/video")
_CREATED = datetime.fromisoformat("2026-01-01T00:00:00+00:00")
_STARTED = datetime.fromisoformat("2026-01-01T01:00:00+00:00")
_SCHEDULED = datetime.fromisoformat("2026-02-01T00:00:00+00:00")


async def _noop_process_job(_job_service: JobService, _job_id: JobId) -> None:
    return


@pytest.fixture
def running_job_service(tmp_path: Path) -> Iterator[tuple[JobService, JobId]]:
    """JobService plus a RunningJob already in the store (process_job's precondition)."""
    job_id = JobId("running")
    with JobStore(
        max_jobs=100,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=2000,
    ) as store:
        store.save_metadata(
            ImmediateRunningJob(
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
        yield job_service, job_id


class _FakeStream:
    def __init__(self, lines: list[bytes]) -> None:
        self._lines = lines
        self._idx = 0

    async def readline(self) -> bytes:
        if self._idx >= len(self._lines):
            return b""
        line = self._lines[self._idx]
        self._idx += 1
        return line


class _FakeProc:
    def __init__(
        self,
        stdout_lines: list[bytes],
        stderr_lines: list[bytes],
        exit_code: int,
    ) -> None:
        self.stdout = _FakeStream(stdout_lines)
        self.stderr = _FakeStream(stderr_lines)
        self._exit_code = exit_code
        self.returncode: int | None = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        if self.returncode is None:
            self.returncode = self._exit_code
        return self.returncode


class _BlockingStream:
    def __init__(self, started: asyncio.Event) -> None:
        self._started = started

    async def readline(self) -> bytes:
        self._started.set()
        await asyncio.Future()
        return b""


class _BlockingProc:
    def __init__(self, started: asyncio.Event) -> None:
        self.stdout = _BlockingStream(started)
        self.stderr = _BlockingStream(started)
        self.returncode: int | None = None
        self.killed = False

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        assert self.returncode is not None
        return self.returncode


@pytest.mark.asyncio
async def test_process_job_marks_succeeded_on_zero_exit(
    monkeypatch: pytest.MonkeyPatch,
    running_job_service: tuple[JobService, JobId],
) -> None:
    # Arrange
    job_service, job_id = running_job_service

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        return _FakeProc(stdout_lines=[], stderr_lines=[], exit_code=0)

    monkeypatch.setattr(
        "yt_dlp_server.process_job.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    # Act
    await process_job(job_service, job_id, output_dir="/out")

    # Assert
    finished = job_service.get(job_id)
    assert isinstance(finished, SucceededJob)
    assert finished.status == JobStatus.succeeded
    assert finished.exit_code == 0


@pytest.mark.asyncio
async def test_process_job_appends_stdout_and_stderr_to_log(
    monkeypatch: pytest.MonkeyPatch,
    running_job_service: tuple[JobService, JobId],
) -> None:
    # Arrange
    job_service, job_id = running_job_service

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        return _FakeProc(
            stdout_lines=[b"hello-stdout\n"],
            stderr_lines=[b"hello-stderr\n"],
            exit_code=0,
        )

    monkeypatch.setattr(
        "yt_dlp_server.process_job.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    # Act
    await process_job(job_service, job_id, output_dir="/out")

    # Assert
    finished = job_service.get(job_id)
    assert isinstance(finished, SucceededJob)
    assert "hello-stdout\n" in finished.log.lines
    assert "hello-stderr\n" in finished.log.lines


@pytest.mark.asyncio
async def test_process_job_marks_failed_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
    running_job_service: tuple[JobService, JobId],
) -> None:
    # Arrange
    job_service, job_id = running_job_service

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        return _FakeProc(stdout_lines=[], stderr_lines=[b"boom\n"], exit_code=1)

    monkeypatch.setattr(
        "yt_dlp_server.process_job.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    # Act
    await process_job(job_service, job_id, output_dir="/out")

    # Assert
    finished = job_service.get(job_id)
    assert isinstance(finished, FailedJob)
    assert finished.status == JobStatus.failed
    assert finished.exit_code == 1
    assert finished.error is not None


@pytest.mark.asyncio
async def test_process_job_on_task_cancel_kills_proc_and_keeps_running(
    monkeypatch: pytest.MonkeyPatch,
    running_job_service: tuple[JobService, JobId],
) -> None:
    # Arrange
    job_service, job_id = running_job_service
    proc_started = asyncio.Event()
    proc = _BlockingProc(proc_started)

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _BlockingProc:
        return proc

    monkeypatch.setattr(
        "yt_dlp_server.process_job.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    task = asyncio.create_task(process_job(job_service, job_id, output_dir="/out"))
    await proc_started.wait()

    # Act
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert
    current = job_service.get(job_id)
    assert isinstance(current, RunningJob)
    assert current.status == JobStatus.running
    assert proc.killed


@pytest.mark.asyncio
async def test_process_job_enables_wait_and_retry_for_scheduled(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    # Arrange
    captured: dict[str, object] = {}

    def fake_build_yt_dlp_cmd(**kwargs: object) -> tuple[str, ...]:
        captured.update(kwargs)
        return ("true",)

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        return _FakeProc(stdout_lines=[], stderr_lines=[], exit_code=0)

    monkeypatch.setattr(
        "yt_dlp_server.process_job.build_yt_dlp_cmd",
        fake_build_yt_dlp_cmd,
    )
    monkeypatch.setattr(
        "yt_dlp_server.process_job.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    job_id = JobId("scheduled-running")
    with JobStore(
        max_jobs=100,
        database_path=tmp_path / "jobs.sqlite3",
        max_log_lines=2000,
    ) as store:
        store.save_metadata(
            ScheduledRunningJob(
                id=job_id,
                url=_URL,
                created_at=_CREATED,
                started_at=_STARTED,
                scheduled_at=_SCHEDULED,
                log=JobLog(),
            )
        )
        job_service = JobService(
            store,
            max_running=0,
            process_job_fn=_noop_process_job,
        )

        # Act
        await process_job(job_service, job_id, output_dir="/out")

    # Assert
    assert captured["wait_and_retry"] is True
