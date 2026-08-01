import sys
from typing import Final

OUTPUT_NAME_TEMPLATE: Final[str] = (
    "%(extractor)s/%(channel)s - %(channel_id)s/"
    "%(playlist)s - %(playlist_id)s/"
    "%(title)s - %(id)s.%(ext)s"
)


def build_output_template(output_dir: str) -> str:
    return f"{output_dir.rstrip('/')}/{OUTPUT_NAME_TEMPLATE}"


def build_yt_dlp_cmd(*, url: str, output_dir: str) -> tuple[str, ...]:
    return (
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "-o",
        build_output_template(output_dir),
        "--no-progress",
        url,
    )
