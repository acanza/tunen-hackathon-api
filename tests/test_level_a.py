"""Pruebas sin red de fuse.level_a con source_values sintéticos."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from fuse.level_a import (
    FUSED_COLUMNS,
    composition_to_ilr,
    fuse_level_a,
    ilr_to_composition,
)
from tunen_ingest.config import load_config
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _cfg():
    return load_config(ROOT / "config.yaml")


def _row(parcel_id, prop, source, value, sigma, citation=None, sigma_age_adj=None):
    return {
        "parcel_id": parcel_id,
        "property": prop,
        "source": source,
        "value_raw": value,
        "unit_raw": "",
        "method_raw": "test",
        "depth_raw": "0-30",
        "value_std": value,
        "unit_std": "",
        "sigma": sigma,
        "sigma_age_adj": sigma_age_adj,
        "scale": "test",
        "source_year": 2020,
        "coverage_fraction": 1.0,
        "record_id": f"{parcel_id}-{source}-{prop}",
        "citation": citation or source,
    }


def test_ilr_roundtrip():
    sand, silt, clay = 60.0, 25.0, 15.0
    back = ilr_to_composition(composition_to_ilr(sand, silt, clay))
    assert back.sum() == pytest.approx(100.0)
    assert back[0] == pytest.approx(sand, abs=0.05)
    assert back[1] == pytest.approx(silt, abs=0.05)
    assert back[2] == pytest.approx(clay, abs=0.05)


def test_two_equal_sources_halves_sigma():
    cfg = _cfg()
    df = pd.DataFrame([
        _row("P1", "ph_cacl2", "A", 6.0, 1.0),
        _row("P1", "ph_cacl2", "B", 6.0, 1.0),
    ])
    out = fuse_level_a(df, cfg=cfg).set_index("property")
    row = out.loc["ph_cacl2"]
    assert row["p50"] == pytest.approx(6.0)
    assert row["sigma_fusion"] == pytest.approx(1.0 / math.sqrt(2))
    assert row["method"] == "A"
    assert row["agreement"] == pytest.approx(1.0)
    assert list(fuse_level_a(df, cfg=cfg).columns) == FUSED_COLUMNS


def test_lower_sigma_dominates():
    cfg = _cfg()
    df = pd.DataFrame([
        _row("P1", "soc_gkg", "coarse", 40.0, 20.0),
        _row("P1", "soc_gkg", "fine", 10.0, 1.0),
    ])
    out = fuse_level_a(df, cfg=cfg).iloc[0]
    assert out["p50"] == pytest.approx(10.0, abs=1.0)
    assert out["best_source"] == "fine"


def test_texture_sums_100():
    cfg = _cfg()
    rows = []
    for src, sand, silt, clay, sig in [
        ("S1", 50, 30, 20, 5),
        ("S2", 55, 25, 20, 8),
    ]:
        rows += [
            _row("P1", "sand_pct", src, sand, sig),
            _row("P1", "silt_pct", src, silt, sig),
            _row("P1", "clay_pct", src, clay, sig),
        ]
    out = fuse_level_a(pd.DataFrame(rows), cfg=cfg)
    tex = out[out["property"].isin(["sand_pct", "silt_pct", "clay_pct"])]
    assert tex["p50"].sum() == pytest.approx(100.0, abs=0.01)


def test_disagreement_widens_interval():
    cfg = _cfg()
    # Fuentes muy distintas → agreement bajo → sigma inflada
    disagree = pd.DataFrame([
        _row("P1", "ph_cacl2", "A", 4.0, 0.5),
        _row("P1", "ph_cacl2", "B", 8.0, 0.5),
    ])
    agree = pd.DataFrame([
        _row("P2", "ph_cacl2", "A", 6.0, 0.5),
        _row("P2", "ph_cacl2", "B", 6.1, 0.5),
    ])
    out_d = fuse_level_a(disagree, cfg=cfg).iloc[0]
    out_a = fuse_level_a(agree, cfg=cfg).iloc[0]
    assert out_d["agreement"] < out_a["agreement"]
    assert out_d["agreement"] < 0.5
    width_d = out_d["p90"] - out_d["p10"]
    width_a = out_a["p90"] - out_a["p10"]
    assert width_d > width_a
    assert out_d["sigma_fusion"] > out_a["sigma_fusion"]


def test_single_source_agreement_nan():
    cfg = _cfg()
    df = pd.DataFrame([_row("P1", "nfk_mm", "only", 90.0, 10.0)])
    out = fuse_level_a(df, cfg=cfg).iloc[0]
    assert np.isnan(out["agreement"])
    assert "una sola fuente" in str(out["motivos"])


def test_sigma_age_adj_preferred():
    cfg = _cfg()
    df = pd.DataFrame([
        _row("P1", "ph_cacl2", "A", 6.0, 1.0, sigma_age_adj=2.0),
        _row("P1", "ph_cacl2", "B", 6.0, 1.0, sigma_age_adj=2.0),
    ])
    out = fuse_level_a(df, cfg=cfg).iloc[0]
    assert out["sigma_fusion"] == pytest.approx(2.0 / math.sqrt(2))


def test_peat_soc_range_not_clipped_low():
    cfg = _cfg()
    # SOC alto en turba: no debe recortar p50 a 200
    df = pd.DataFrame([_row("PEAT", "soc_gkg", "SG", 300.0, 20.0)])
    out = fuse_level_a(df, cfg=cfg, is_peat={"PEAT": True}).iloc[0]
    assert out["p50"] == pytest.approx(300.0)
    assert out["p90"] <= 580.0
