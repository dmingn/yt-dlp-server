from yt_dlp_server.models import JobLog


def test_job_log_append_drops_oldest_when_over_max_lines() -> None:
    # Arrange
    log = JobLog(max_lines=2)

    # Act
    log = log.append("a").append("b").append("c")

    # Assert
    assert log.lines == ("b", "c")
    assert len(log) == 2
