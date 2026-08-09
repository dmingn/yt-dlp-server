import sqlite3
from collections.abc import Callable
from pathlib import Path

SCHEMA_VERSION = 1

_Upgrade = Callable[[sqlite3.Connection], None]


class SchemaVersionError(Exception):
    """Raised when the database schema is newer than this application supports."""


def _migrate_to_1(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY,
          url TEXT NOT NULL,
          status TEXT NOT NULL,
          created_at TEXT NOT NULL,
          started_at TEXT,
          finished_at TEXT,
          exit_code INTEGER,
          error TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE job_log_lines (
          job_id TEXT NOT NULL REFERENCES jobs(id) ON DELETE CASCADE,
          seq INTEGER NOT NULL,
          line TEXT NOT NULL,
          PRIMARY KEY (job_id, seq)
        )
        """
    )


_MIGRATIONS: tuple[tuple[int, _Upgrade], ...] = ((1, _migrate_to_1),)


def migrate(conn: sqlite3.Connection) -> None:
    current = int(conn.execute("PRAGMA user_version").fetchone()[0])
    if current > SCHEMA_VERSION:
        raise SchemaVersionError(
            f"database schema version {current} is newer than supported "
            f"{SCHEMA_VERSION}"
        )
    with conn:
        for version, upgrade in _MIGRATIONS:
            if current < version:
                upgrade(conn)
                conn.execute(f"PRAGMA user_version = {version}")
                current = version


def connect(database_path: Path) -> sqlite3.Connection:
    if database_path.parent != Path("."):
        database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    migrate(conn)
    return conn
