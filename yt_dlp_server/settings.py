from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_ignore_empty=True)

    n_workers: int = Field(default=1, ge=1)
    max_jobs: int = Field(
        default=100,
        ge=1,
        description=(
            "Max unfinished (queued/running) jobs; also max retained finished jobs"
        ),
    )
    max_log_lines: int = Field(default=2000, ge=1)
    output_dir: str = "/out"
    host: str = "0.0.0.0"
    port: int = 8000
