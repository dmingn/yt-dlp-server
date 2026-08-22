from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    max_running: int = Field(
        default=1,
        ge=1,
        description="Max concurrently running download tasks",
    )
    max_jobs: int = Field(
        default=100,
        ge=1,
        description=(
            "Max unfinished (queued/scheduled/running) jobs; "
            "also max retained finished jobs"
        ),
    )
    max_log_lines: int = Field(default=2000, ge=1)
    database_path: Path = Path("jobs.sqlite3")
    output_dir: str = "/out"
    pot_base_url: AnyHttpUrl | None = None
    host: str = "0.0.0.0"
    port: int = 8000
