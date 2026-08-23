import sys
from typing import Final

OUTPUT_NAME_TEMPLATE: Final[str] = (
    "%(extractor)s/%(channel)s - %(channel_id)s/"
    "%(playlist)s - %(playlist_id)s/"
    "%(title)s - %(id)s.%(ext)s"
)
CACHE_DIR: Final[str] = "/tmp/yt-dlp-cache"


def build_output_template(output_dir: str) -> str:
    return f"{output_dir.rstrip('/')}/{OUTPUT_NAME_TEMPLATE}"


def build_yt_dlp_cmd(
    *,
    url: str,
    output_dir: str,
    pot_base_url: str | None = None,
    wait_and_retry: bool = False,
) -> tuple[str, ...]:
    cmd: list[str] = [
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "-o",
        build_output_template(output_dir),
        "--cache-dir",
        CACHE_DIR,
        "--no-progress",
    ]

    if wait_and_retry:
        cmd.extend(
            (
                "--wait-for-video",
                "15-60",
                "--retries",
                "infinite",
                "--fragment-retries",
                "infinite",
            )
        )

    # When POT_BASE_URL is set, use mweb + GVS PO Token via bgutil HTTP.
    # Official recommendation: https://github.com/yt-dlp/yt-dlp/wiki/PO-Token-Guide
    # Unset leaves yt-dlp defaults (no these extractor-args).
    if pot_base_url:
        # bgutil concatenates `{base_url}/ping`; AnyHttpUrl str() keeps a
        # trailing slash, which would request `//ping` and 404.
        cmd.extend(
            (
                "--extractor-args",
                "youtube:player_client=mweb",
                "--extractor-args",
                f"youtubepot-bgutilhttp:base_url={pot_base_url.rstrip('/')}",
            )
        )

    cmd.append(url)
    return tuple(cmd)
