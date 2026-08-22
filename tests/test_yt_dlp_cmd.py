import sys

from yt_dlp_server.yt_dlp_cmd import build_output_template, build_yt_dlp_cmd


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
        "--no-progress",
        url,
    )


def test_build_yt_dlp_cmd_with_pot_base_url() -> None:
    # Arrange
    url = "https://example.com/video"
    output_dir = "/data"
    pot_base_url = "http://pot-provider:4416"

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
        "--no-progress",
        "--extractor-args",
        "youtube:player_client=mweb",
        "--extractor-args",
        f"youtubepot-bgutilhttp:base_url={pot_base_url}",
        url,
    )


def test_build_output_template_strips_trailing_slash() -> None:
    # Act
    with_slash = build_output_template("/out/")
    without_slash = build_output_template("/out")

    # Assert
    assert with_slash == without_slash
