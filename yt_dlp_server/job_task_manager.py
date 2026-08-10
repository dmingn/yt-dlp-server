from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import partial

from yt_dlp_server.models import JobId

ClaimNextJobFn = Callable[[], JobId | None]
ProcessJobFn = Callable[[JobId], Coroutine[object, object, None]]


class JobTaskManager:
    """Claims queued jobs and runs them as tasks, up to max_running."""

    def __init__(
        self,
        *,
        max_running: int,
        claim_next_job_fn: ClaimNextJobFn,
        process_job_fn: ProcessJobFn,
    ) -> None:
        self._max_running = max_running
        self._claim_next_job = claim_next_job_fn
        self._process_job = process_job_fn
        self._running_tasks: dict[JobId, asyncio.Task[None]] = {}
        self._closed = False

    async def claim_queued_jobs_up_to_max_running(self) -> None:
        if self._closed:
            return

        while len(self._running_tasks) < self._max_running:
            job_id = self._claim_next_job()

            if job_id is None:
                return

            if job_id in self._running_tasks:
                continue

            task = asyncio.create_task(
                self._process_job(job_id),
                name=f"job-{job_id}",
            )
            self._running_tasks[job_id] = task

            task.add_done_callback(partial(self._on_task_done, job_id))

    async def cancel(self, job_id: JobId) -> None:
        task = self._running_tasks.get(job_id)
        if task is None:
            return
        task.cancel()
        await asyncio.wait({task})

    async def shutdown(self) -> None:
        self._closed = True
        tasks = list(self._running_tasks.values())
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    def _on_task_done(self, job_id: JobId, task: asyncio.Task[None]) -> None:
        self._running_tasks.pop(job_id, None)

        if self._closed:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(self.claim_queued_jobs_up_to_max_running())
