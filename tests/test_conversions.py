"""Pruebas sin red de harmonize.conversions."""

from pathlib import Path

import pandas as pd
import pytest

from harmonize import conversions as conv

ROOT = Path(__file__).resolve().parents[1]
KA5_CSV = ROOT / "data" / "ref" / "ka5_texture_classes.csv"


def test_depth_weighted_soilgrids_layers():
    # 0-5, 5-15, 15-30 con 10, 20, 30 → (50 + 200 + 450) / 30 = 23.333...
    mean = conv.depth_weighted_mean(
        [10.0, 20.0, 30.0],
        [(0, 5), (5, 15), (15, 30)],
        target=(0, 30),
    )
    assert mean == pytest.approx(23.333333, abs=0.01)


def test_depth_weighted_clips_horizon_past_30():
    # Horizonte 0-40 cm: solo cuenta 0-30
    mean = conv.depth_weighted_mean([42.0], [(0, 40)], target=(0, 30))
    assert mean == pytest.approx(42.0)


def test_soilgrids_ph_to_cacl2():
    ph, sigma_extra = conv.soilgrids_ph_to_cacl2(65, offset=0.55)
    assert ph == pytest.approx(5.95)
    assert sigma_extra == pytest.approx(0.3)


def test_humus_to_soc():
    assert conv.humus_to_soc(3.44) == pytest.approx(20.0, abs=0.01)


def test_ka5_sl2_centers():
    clay, silt, sand, *_ = conv.ka5_class_to_pct("Sl2", csv_path=KA5_CSV)
    assert clay == pytest.approx(6.5)
    assert silt == pytest.approx(17.5)
    assert sand == pytest.approx(76.0)


def test_ka5_triangle_centroids_not_midpoints():
    """Fails if the CSV is regenerated with range midpoints instead of polygon centroids."""
    clay_tt, silt_tt, *_ = conv.ka5_class_to_pct("Tt", csv_path=KA5_CSV)
    assert clay_tt == pytest.approx(76.7)
    assert silt_tt == pytest.approx(11.6)
    clay_tu2, silt_tu2, *_ = conv.ka5_class_to_pct("Tu2", csv_path=KA5_CSV)
    assert clay_tu2 == pytest.approx(52.8)
    assert silt_tu2 == pytest.approx(38.7)


def test_ka5_all_centers_sum_to_100():
    df = pd.read_csv(KA5_CSV)
    key = "ka5_class" if "ka5_class" in df.columns else "clase"
    assert len(df) == 31
    for clase in df[key].astype(str):
        clay, silt, sand, *_ = conv.ka5_class_to_pct(clase, csv_path=KA5_CSV)
        # Verified centroids can round to 100.1 (e.g. Tu2); keep a tight band.
        assert clay + silt + sand == pytest.approx(100.0, abs=0.15)


def test_ka5_unknown_class_raises():
    with pytest.raises(ValueError, match="desconocida"):
        conv.ka5_class_to_pct("Xx9", csv_path=KA5_CSV)


def test_age_adjusted_sigma_k0_unchanged():
    assert conv.age_adjusted_sigma(2.0, "clay_pct", 2000, 2020, cfg={"age_uncertainty": {}}) == 2.0


def test_age_adjusted_sigma_ph_20_years():
    cfg = {"age_uncertainty": {"ph_cacl2": 0.3}}
    # k=0.3, 20 años → 1 + 0.3*20/10 = 1.6
    assert conv.age_adjusted_sigma(1.0, "ph_cacl2", 2000, 2020, cfg=cfg) == pytest.approx(1.6)


def test_soilgrids_texture_and_soc_units():
    assert conv.soilgrids_texture_to_pct(250) == pytest.approx(25.0)
    assert conv.soilgrids_soc_to_gkg(200) == pytest.approx(20.0)


def test_sigma_from_quantiles():
    assert conv.sigma_from_quantiles(0.0, 32.9) == pytest.approx(10.0)


def test_texture_limit_none(cfg):
    sand, silt, clay, inflate, note = conv.texture_limit_adjustment(50, 30, 20, method="none", cfg=cfg)
    assert (sand, silt, clay) == (50.0, 30.0, 20.0)
    assert inflate == pytest.approx(1.2)
    assert "50" in note and "63" in note


def test_texture_limit_loglinear_not_implemented():
    with pytest.raises(NotImplementedError, match="fracciones"):
        conv.texture_limit_adjustment(50, 30, 20, method="loglinear")


def test_is_peat_from_humus():
    assert conv.is_peat_from_humus(30.0, threshold=30) is True
    assert conv.is_peat_from_humus(29.9, threshold=30) is False


def test_nfk_sand_less_awc_than_silty_loam():
    # Arena (poca arcilla) vs franco limoso
    awc_sand = conv.nfk_from_texture_saxton_rawls(85.0, 5.0, 1.0)
    awc_silty = conv.nfk_from_texture_saxton_rawls(20.0, 15.0, 1.0)  # silt implícito alto
    assert awc_sand < awc_silty


def test_nfk_more_om_does_not_lower_awc():
    base = conv.nfk_from_texture_saxton_rawls(40.0, 20.0, 1.0)
    richer = conv.nfk_from_texture_saxton_rawls(40.0, 20.0, 3.0)
    assert richer >= base


def test_nfk_empty_coefs_raise(tmp_path):
    csv = tmp_path / "saxton_empty.csv"
    csv.write_text(
        "nombre,ecuacion,valor,fuente\n"
        "theta_1500t_S,1,,TODO: verificar en el artículo\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="sin verificar|TODO|Coeficientes"):
        conv.nfk_from_texture_saxton_rawls(40.0, 20.0, 1.0, csv_path=csv)
