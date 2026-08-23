import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from yt_dlp_server.app import create_app
from yt_dlp_server.settings import Settings


@pytest.fixture
def restore_umask() -> Iterator[int]:
    previous = os.umask(0)
    os.umask(previous)
    try:
        yield previous
    finally:
        os.umask(previous)


@pytest.mark.parametrize(
    ("umask", "before", "expected"),
    [
        pytest.param(None, 0o027, 0o027, id="unset"),
        pytest.param("22", 0o027, 0o022, id="octal"),
    ],
)
def test_create_app_umask(
    restore_umask: int,
    tmp_path: Path,
    umask: str | None,
    before: int,
    expected: int,
) -> None:
    # Arrange
    os.umask(before)
    settings = Settings(umask=umask, database_path=tmp_path / "jobs.sqlite3")

    # Act
    create_app(settings)

    # Assert
    current = os.umask(restore_umask)
    assert current == expected
