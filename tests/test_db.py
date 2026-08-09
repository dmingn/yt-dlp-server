from pathlib import Path

import pytest

from yt_dlp_server.db import SCHEMA_VERSION, SchemaVersionError, connect


def test_connect_applies_schema_version(tmp_path: Path) -> None:
    # Arrange / Act
    conn = connect(tmp_path / "jobs.sqlite3")

    # Assert
    version = int(conn.execute("PRAGMA user_version").fetchone()[0])
    assert version == SCHEMA_VERSION
    tables = {
        str(row[0])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    }
    assert "jobs" in tables
    assert "job_log_lines" in tables
    conn.close()


def test_migrate_rejects_newer_schema(tmp_path: Path) -> None:
    # Arrange
    path = tmp_path / "jobs.sqlite3"
    conn = connect(path)
    conn.execute(f"PRAGMA user_version = {SCHEMA_VERSION + 1}")
    conn.commit()
    conn.close()

    # Act / Assert
    with pytest.raises(SchemaVersionError):
        connect(path)
