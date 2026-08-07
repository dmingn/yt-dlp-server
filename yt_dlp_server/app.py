import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from yt_dlp_server.api import router as api_router
from yt_dlp_server.job_service import JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.settings import Settings
from yt_dlp_server.version import get_version
from yt_dlp_server.worker import worker

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        jobs = JobService(
            JobStore(max_jobs=settings.max_jobs),
            max_log_lines=settings.max_log_lines,
        )
        app.state.jobs = jobs
        app.state.settings = settings

        tasks = [
            asyncio.create_task(
                worker(
                    jobs,
                    output_dir=settings.output_dir,
                ),
                name=f"worker-{i}",
            )
            for i in range(settings.n_workers)
        ]
        try:
            yield
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(title="yt-dlp-server", lifespan=lifespan)
    app.state.settings = settings
    app.include_router(api_router)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/")
    async def index() -> HTMLResponse:
        html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(html.replace("__VERSION__", get_version(), 1))

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app


app = create_app()
