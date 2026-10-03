"""Safe resolution of precomputed store artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .settings import ApplicationSettings, get_settings


def resolve_store_artifact(
    relative_path: str,
    settings: Optional[ApplicationSettings] = None,
) -> Path:
    """Resolve an existing artifact while keeping it inside the configured store."""

    if not relative_path or "\x00" in relative_path or "\\" in relative_path:
        raise ValueError("artifact path must be a non-empty POSIX-relative path")

    requested_path = Path(relative_path)
    if requested_path.is_absolute() or ".." in requested_path.parts:
        raise ValueError("artifact path must be relative to the store")

    configured_settings = settings or get_settings()
    store_root = configured_settings.store_root.resolve()
    artifact_path = (store_root / requested_path).resolve()
    try:
        artifact_path.relative_to(store_root)
    except ValueError as error:
        raise ValueError("artifact path resolves outside the store") from error

    if not artifact_path.is_file():
        raise FileNotFoundError(f"Store artifact does not exist: {relative_path}")
    return artifact_path
