import sys

from yt_dlp_server.yt_dlp_cmd import build_output_template, build_yt_dlp_cmd


def test_build_yt_dlp_cmd_shape() -> None:
    # Arrange
    url = "https://example.com/video"
    output_dir = "/data"

    # Act
    cmd = build_yt_dlp_cmd(url=url, output_dir=output_dir)

    # Assert
    assert cmd[:4] == (sys.executable, "-u", "-m", "yt_dlp")
    assert "-o" in cmd
    assert cmd[cmd.index("-o") + 1] == build_output_template(output_dir)
    assert "--no-progress" in cmd
    assert cmd[-1] == url


def test_build_output_template_strips_trailing_slash() -> None:
    # Act
    with_slash = build_output_template("/out/")
    without_slash = build_output_template("/out")

    # Assert
    assert with_slash == without_slash
