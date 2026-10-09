"""Read-only SQLite connection factory for the frozen store."""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from typing import Iterator, Optional
from urllib.parse import quote

from .settings import ApplicationSettings, get_settings


def open_read_only_connection(
    settings: Optional[ApplicationSettings] = None,
) -> sqlite3.Connection:
    """Open the store database with SQLite's read-only URI mode."""

    path = (settings or get_settings()).database_path.resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Store database does not exist: {path}")

    database_uri = f"file:{quote(str(path), safe='/')}?mode=ro"
    return sqlite3.connect(database_uri, uri=True)


@contextmanager
def read_only_connection(
    settings: Optional[ApplicationSettings] = None,
) -> Iterator[sqlite3.Connection]:
    """Yield a read-only connection and always close it afterwards."""

    connection = open_read_only_connection(settings)
    try:
        yield connection
    finally:
        connection.close()
