"""Application settings for the frozen POC store."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_STORE_ROOT = REPOSITORY_ROOT / "docs" / "poc" / "store"
STORE_ROOT_ENVIRONMENT_VARIABLE = "TUNEN_STORE_ROOT"


@dataclass(frozen=True)
class ApplicationSettings:
    """Validated filesystem configuration for the local precomputed store."""

    repository_root: Path
    store_root: Path

    @property
    def database_path(self) -> Path:
        """Return the metadata database path inside the configured store."""

        return self.store_root / "soil.sqlite"


def _resolve_store_root(configured_root: Optional[str]) -> Path:
    store_root = Path(configured_root) if configured_root else DEFAULT_STORE_ROOT
    if not store_root.is_absolute():
        store_root = REPOSITORY_ROOT / store_root
    store_root = store_root.resolve()

    try:
        store_root.relative_to(REPOSITORY_ROOT)
    except ValueError as error:
        raise ValueError("The store root must be located inside the repository") from error

    if not store_root.is_dir():
        raise FileNotFoundError(f"Store directory does not exist: {store_root}")

    database_path = store_root / "soil.sqlite"
    if not database_path.is_file():
        raise FileNotFoundError(f"Store database does not exist: {database_path}")

    return store_root


@lru_cache(maxsize=1)
def get_settings() -> ApplicationSettings:
    """Load and validate settings for the current repository."""

    configured_root = os.getenv(STORE_ROOT_ENVIRONMENT_VARIABLE)
    return ApplicationSettings(
        repository_root=REPOSITORY_ROOT,
        store_root=_resolve_store_root(configured_root),
    )
