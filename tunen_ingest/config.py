"""Carga de config.yaml con acceso por atributos."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


class Cfg(dict):
    """Diccionario que también permite cfg.sentinel2.bands."""

    def __getattr__(self, key: str) -> Any:
        try:
            value = self[key]
        except KeyError as exc:
            raise AttributeError(key) from exc
        return Cfg(value) if isinstance(value, dict) else value


def load_config(path: str | Path = "config.yaml") -> Cfg:
    with open(path, encoding="utf-8") as fh:
        cfg = Cfg(yaml.safe_load(fh))
    cfg["data_dir"] = str(Path(cfg.get("data_dir", "data")))
    return cfg
