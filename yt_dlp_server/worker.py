import asyncio

from yt_dlp_server.job_service import JobService
from yt_dlp_server.yt_dlp_cmd import build_yt_dlp_cmd


async def _pump_stream(
    stream: asyncio.StreamReader, jobs: JobService, job_id: str
) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        jobs.append_log_line(job_id, line.decode(errors="replace"))


async def _kill_process(proc: asyncio.subprocess.Process | None) -> None:
    if proc is None or proc.returncode is not None:
        return
    proc.kill()
    await proc.wait()


async def process_job(
    jobs: JobService,
    job_id: str,
    *,
    output_dir: str,
) -> None:
    job = jobs.mark_running(job_id)
    if job is None:
        return

    proc: asyncio.subprocess.Process | None = None
    try:
        cmd = build_yt_dlp_cmd(url=str(job.url), output_dir=output_dir)
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Always StreamReader with PIPE; assert narrows the Optional type.
        assert proc.stdout is not None
        assert proc.stderr is not None

        await asyncio.gather(
            _pump_stream(proc.stdout, jobs, job_id),
            _pump_stream(proc.stderr, jobs, job_id),
        )

        exit_code = await proc.wait()
        if exit_code == 0:
            jobs.mark_succeeded(job_id)
        else:
            jobs.mark_failed(
                job_id,
                error=f"yt-dlp exited with code {exit_code}",
                exit_code=exit_code,
            )
    except asyncio.CancelledError:
        jobs.mark_failed(job_id, error="cancelled")
        raise
    except Exception as exc:
        jobs.mark_failed(job_id, error=f"{type(exc).__name__}: {exc}")
    finally:
        await _kill_process(proc)


async def worker(
    jobs: JobService,
    *,
    output_dir: str,
) -> None:
    while True:
        job_id = await jobs.claim_next()
        try:
            await process_job(
                jobs,
                job_id,
                output_dir=output_dir,
            )
        finally:
            jobs.task_done()
