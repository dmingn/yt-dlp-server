import sys

import pytest

from yt_dlp_server.yt_dlp_cmd import (
    CACHE_DIR,
    build_output_template,
    build_yt_dlp_cmd,
)


def test_build_yt_dlp_cmd_without_pot() -> None:
    # Arrange
    url = "https://example.com/video"
    output_dir = "/data"

    # Act
    cmd = build_yt_dlp_cmd(url=url, output_dir=output_dir)

    # Assert
    assert cmd == (
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "-o",
        build_output_template(output_dir),
        "--cache-dir",
        CACHE_DIR,
        "--no-progress",
        url,
    )


@pytest.mark.parametrize(
    "pot_base_url",
    [
        pytest.param("http://pot-provider:4416", id="no-trailing-slash"),
        pytest.param("http://pot-provider:4416/", id="trailing-slash"),
    ],
)
def test_build_yt_dlp_cmd_with_pot_base_url(pot_base_url: str) -> None:
    # Arrange
    url = "https://example.com/video"
    output_dir = "/data"

    # Act
    cmd = build_yt_dlp_cmd(
        url=url,
        output_dir=output_dir,
        pot_base_url=pot_base_url,
    )

    # Assert
    assert cmd == (
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "-o",
        build_output_template(output_dir),
        "--cache-dir",
        CACHE_DIR,
        "--no-progress",
        "--extractor-args",
        "youtube:player_client=mweb",
        "--extractor-args",
        "youtubepot-bgutilhttp:base_url=http://pot-provider:4416",
        url,
    )


def test_build_yt_dlp_cmd_wait_and_retry() -> None:
    # Arrange
    url = "https://example.com/video"
    output_dir = "/data"

    # Act
    cmd = build_yt_dlp_cmd(url=url, output_dir=output_dir, wait_and_retry=True)

    # Assert
    assert cmd == (
        sys.executable,
        "-u",
        "-m",
        "yt_dlp",
        "-o",
        build_output_template(output_dir),
        "--cache-dir",
        CACHE_DIR,
        "--no-progress",
        "--wait-for-video",
        "15-60",
        "--retries",
        "infinite",
        "--fragment-retries",
        "infinite",
        url,
    )


def test_build_output_template_strips_trailing_slash() -> None:
    # Act
    with_slash = build_output_template("/out/")
    without_slash = build_output_template("/out")

    # Assert
    assert with_slash == without_slash
