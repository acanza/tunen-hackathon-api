import copy
from pathlib import Path

import pytest

from tunen_ingest.config import Cfg, load_config

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def cfg(tmp_path):
    c = load_config(ROOT / "config.yaml")
    c = Cfg(copy.deepcopy(dict(c)))
    c["data_dir"] = str(tmp_path / "data")
    return c


@pytest.fixture
def sample_path():
    return ROOT / "examples" / "sample_parcels.geojson"
