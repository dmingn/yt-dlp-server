from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from yt_dlp_server.api import router as api_router
from yt_dlp_server.job_service import JobService
from yt_dlp_server.job_store import JobStore
from yt_dlp_server.process_job import process_job
from yt_dlp_server.settings import Settings
from yt_dlp_server.version import get_version

STATIC_DIR = Path(__file__).resolve().parent / "static"


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        with JobStore(
            max_jobs=settings.max_jobs,
            database_path=settings.database_path,
            max_log_lines=settings.max_log_lines,
        ) as store:
            job_service = JobService(
                store,
                max_running=settings.max_running,
                process_job_fn=lambda job_service, job_id: process_job(
                    job_service,
                    job_id,
                    output_dir=settings.output_dir,
                    pot_base_url=(
                        None
                        if settings.pot_base_url is None
                        else str(settings.pot_base_url)
                    ),
                ),
            )
            job_service.restore_waiting_jobs()
            await job_service.start_polling()
            app.state.job_service = job_service
            app.state.settings = settings

            try:
                yield
            finally:
                await job_service.shutdown()

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
