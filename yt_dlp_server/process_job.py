import asyncio

from yt_dlp_server.job_service import JobService
from yt_dlp_server.models import JobId, RunningJob, ScheduledRunningJob
from yt_dlp_server.yt_dlp_cmd import build_yt_dlp_cmd


async def _pump_stream(
    stream: asyncio.StreamReader, job_service: JobService, job_id: JobId
) -> None:
    while True:
        line = await stream.readline()
        if not line:
            break
        job_service.append_log_line(job_id, line.decode(errors="replace"))


async def process_job(
    job_service: JobService,
    job_id: JobId,
    *,
    output_dir: str,
    pot_base_url: str | None = None,
) -> None:
    job = job_service.get_job(job_id)
    if not isinstance(job, RunningJob):
        return

    proc: asyncio.subprocess.Process | None = None
    try:
        cmd = build_yt_dlp_cmd(
            url=str(job.url),
            output_dir=output_dir,
            pot_base_url=pot_base_url,
            wait_and_retry=isinstance(job, ScheduledRunningJob),
        )
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        # Always StreamReader with PIPE; assert narrows the Optional type.
        assert proc.stdout is not None
        assert proc.stderr is not None

        await asyncio.gather(
            _pump_stream(proc.stdout, job_service, job_id),
            _pump_stream(proc.stderr, job_service, job_id),
        )

        exit_code = await proc.wait()
        if exit_code == 0:
            job_service.mark_job_succeeded(job_id)
        else:
            job_service.mark_job_failed(
                job_id,
                error=f"yt-dlp exited with code {exit_code}",
                exit_code=exit_code,
            )
    except asyncio.CancelledError:
        # Do not update job status here. Why, for each cancel path:
        # - UI/API cancel: JobService.cancel_job already saved status=cancelled.
        # - Process shutdown (e.g. SIGINT): leave status as running so the
        #   next startup can re-queue the job.
        raise
    except Exception as exc:
        job_service.mark_job_failed(job_id, error=f"{type(exc).__name__}: {exc}")
    finally:
        if proc is not None and proc.returncode is None:
            proc.kill()
            await proc.wait()
