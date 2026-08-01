import asyncio
import sys
from typing import Any

import pytest

from yt_dlp_server.job_service import JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.models import FailedJob, JobStatus, SucceededJob
from yt_dlp_server.worker import process_job


def _make_jobs(*, max_jobs: int = 100, max_log_lines: int = 2000) -> JobService:
    return JobService(
        JobStore(max_jobs=max_jobs),
        max_log_lines=max_log_lines,
    )


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
async def test_process_job_succeeds_and_appends_logs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    jobs = _make_jobs()
    job = jobs.enqueue("https://example.com/video")
    await jobs.claim_next()

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        assert cmd[:4] == (sys.executable, "-u", "-m", "yt_dlp")
        return _FakeProc(
            stdout_lines=[b"hello-stdout\n"],
            stderr_lines=[b"hello-stderr\n"],
            exit_code=0,
        )

    monkeypatch.setattr(
        "yt_dlp_server.worker.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    # Act
    await process_job(jobs, job.id, output_dir="/out")

    # Assert
    finished = jobs.get(job.id)
    assert isinstance(finished, SucceededJob)
    assert finished.status == JobStatus.succeeded
    assert finished.exit_code == 0
    assert "hello-stdout\n" in finished.log.lines
    assert "hello-stderr\n" in finished.log.lines


@pytest.mark.asyncio
async def test_process_job_marks_failed_on_nonzero_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    jobs = _make_jobs()
    job = jobs.enqueue("https://example.com/video")
    await jobs.claim_next()

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _FakeProc:
        return _FakeProc(stdout_lines=[], stderr_lines=[b"boom\n"], exit_code=1)

    monkeypatch.setattr(
        "yt_dlp_server.worker.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    # Act
    await process_job(jobs, job.id, output_dir="/out")

    # Assert
    finished = jobs.get(job.id)
    assert isinstance(finished, FailedJob)
    assert finished.status == JobStatus.failed
    assert finished.exit_code == 1
    assert finished.error is not None


@pytest.mark.asyncio
async def test_process_job_cancelled_kills_and_marks_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Arrange
    jobs = _make_jobs()
    job = jobs.enqueue("https://example.com/video")
    await jobs.claim_next()

    started = asyncio.Event()
    proc = _BlockingProc(started)

    async def fake_create_subprocess_exec(
        *cmd: str,
        stdout: Any = None,
        stderr: Any = None,
    ) -> _BlockingProc:
        return proc

    monkeypatch.setattr(
        "yt_dlp_server.worker.asyncio.create_subprocess_exec",
        fake_create_subprocess_exec,
    )

    task = asyncio.create_task(process_job(jobs, job.id, output_dir="/out"))
    await started.wait()

    # Act
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    # Assert
    finished = jobs.get(job.id)
    assert isinstance(finished, FailedJob)
    assert finished.error == "cancelled"
    assert proc.killed
