from __future__ import annotations

import asyncio
from collections.abc import Callable, Coroutine
from functools import partial

from yt_dlp_server.models import JobId

ProcessJobFn = Callable[[JobId], Coroutine[object, object, None]]


class JobTaskManager:
    """Runs claimed jobs as asyncio tasks."""

    def __init__(self, *, process_job_fn: ProcessJobFn) -> None:
        self._process_job = process_job_fn
        self._running_tasks: dict[JobId, asyncio.Task[None]] = {}
        self._closed = False

    @property
    def running_count(self) -> int:
        return len(self._running_tasks)

    @property
    def closed(self) -> bool:
        return self._closed

    def spawn(self, job_id: JobId) -> None:
        if self._closed or job_id in self._running_tasks:
            return

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
