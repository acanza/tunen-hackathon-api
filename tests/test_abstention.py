"""Pruebas de confidence.abstention (sin red)."""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from confidence.abstention import apply_abstention, evaluate_row
from tunen_ingest.config import load_config

ROOT = Path(__file__).resolve().parents[1]


def _cfg():
    return load_config(ROOT / "config.yaml")


def _fused_row(**kwargs):
    base = {
        "parcel_id": "P1",
        "property": "ph_cacl2",
        "p10": 5.5,
        "p50": 6.0,
        "p90": 6.5,
        "unit": "pH",
        "sigma_fusion": 0.4,
        "nivel": None,
        "method": "A",
        "sources_used": '[{"source": "A", "citation": "A"}, {"source": "B", "citation": "B"}]',
        "agreement": 0.9,
        "di": None,
        "inside_aoa": None,
        "motivos": "",
        "que_faltaria": None,
        "best_source": "A",
        "best_value": 6.0,
        "best_sigma": 0.4,
    }
    base.update(kwargs)
    return pd.Series(base)


def _parcel(**kwargs):
    base = {
        "parcel_id": "P1",
        "status": "ok",
        "reject_reason": "",
        "input_flags": "",
        "is_peat": False,
    }
    base.update(kwargs)
    return pd.Series(base)


def test_filter_entrada_rojo():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(),
        _parcel(status="reject", reject_reason="area_600ha_above_max"),
        _cfg(),
    )
    assert nivel == "rojo"
    assert "rechazada" in motivos[0].lower() or "Parcela" in motivos[0]


def test_bodenzahl_bosque_no_aplicable_not_rojo():
    nivel, motivos, que, _ = evaluate_row(
        _fused_row(property="bodenzahl", p10=40, p50=50, p90=60),
        _parcel(input_flags="no_agricola"),
        _cfg(),
    )
    assert nivel == "no_aplicable"
    assert nivel != "rojo"
    assert "agrícola" in motivos[0]
    assert "agrícola" in que.lower() or "agrícola" in que


def test_cobertura_sin_fuentes_rojo():
    nivel, _, que, _ = evaluate_row(_fused_row(sources_used="[]"), _parcel(), _cfg())
    assert nivel == "rojo"
    assert "laboratorio" in que.lower() or "mapa" in que.lower()


def test_cobertura_una_fuente_ambar():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(sources_used='[{"source": "SoilGrids", "citation": "SG"}]'),
        _parcel(),
        _cfg(),
    )
    assert nivel == "ambar"
    assert any("sola fuente" in m.lower() for m in motivos)


def test_dominio_aoa_parcial():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(inside_aoa=False),
        _parcel(),
        _cfg(),
    )
    assert nivel == "parcial"
    assert any("aplicabilidad" in m.lower() for m in motivos)


def test_aoa_ausente_no_falla():
    row = _fused_row()
    row = row.drop(labels=["inside_aoa"])
    nivel, _, _, _ = evaluate_row(row, _parcel(), _cfg())
    assert nivel == "verde"


def test_incertidumbre_ambar_y_parcial():
    # umbral pH = 1.0 → ancho 1.5 ámbar; ancho 2.5 parcial
    n1, _, _, _ = evaluate_row(_fused_row(p10=5.0, p50=6.0, p90=6.5), _parcel(), _cfg())  # width 1.5
    assert n1 == "ambar"
    n2, _, _, _ = evaluate_row(_fused_row(p10=4.5, p50=6.0, p90=7.0), _parcel(), _cfg())  # width 2.5
    assert n2 == "parcial"


def test_coherencia_fuera_rango_rojo():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(property="ph_cacl2", p10=11, p50=12, p90=13),
        _parcel(),
        _cfg(),
    )
    assert nivel == "rojo"
    assert any("imposible" in m.lower() for m in motivos)


def test_agreement_bajo_ambar():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(agreement=0.1, p10=5.8, p50=6.0, p90=6.2),
        _parcel(),
        _cfg(),
    )
    assert nivel == "ambar"
    assert any("acuerdo" in m.lower() for m in motivos)


def test_bodenzahl_cruzada_ambar():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(
            property="bodenzahl",
            p10=40, p50=50, p90=60,
            bodenzahl_modeled=70,
            sources_used='[{"source": "A"}, {"source": "B"}]',
        ),
        _parcel(),
        _cfg(),
    )
    assert nivel == "ambar"
    assert any("no coinciden" in m for m in motivos)


def test_peor_gana_rojo_sobre_ambar():
    # rechazo (rojo) + una sola fuente (ámbar) → rojo
    nivel, _, _, _ = evaluate_row(
        _fused_row(sources_used='[{"source": "A"}]'),
        _parcel(status="reject", reject_reason="too_small"),
        _cfg(),
    )
    assert nivel == "rojo"


def test_turba_soc_300_no_rojo():
    nivel, _, _, _ = evaluate_row(
        _fused_row(
            property="soc_gkg",
            p10=280, p50=300, p90=320,
            sources_used='[{"source": "A"}, {"source": "B"}]',
            agreement=0.8,
        ),
        _parcel(is_peat=True),
        _cfg(),
    )
    assert nivel != "rojo"


def test_apply_abstention_batch():
    fused = pd.DataFrame([
        _fused_row(parcel_id="OK", p10=5.8, p50=6.0, p90=6.2),
        _fused_row(parcel_id="BAD", property="ph_cacl2", p10=0, p50=1, p90=2),
    ])
    parcels = pd.DataFrame([
        {"parcel_id": "OK", "status": "ok", "reject_reason": "", "input_flags": "", "is_peat": False},
        {"parcel_id": "BAD", "status": "ok", "reject_reason": "", "input_flags": "", "is_peat": False},
    ])
    out = apply_abstention(fused, parcels=parcels, cfg=_cfg())
    assert out.loc[out.parcel_id == "OK", "nivel"].iloc[0] == "verde"
    assert out.loc[out.parcel_id == "BAD", "nivel"].iloc[0] == "rojo"


def test_fuera_de_alemania_bodenzahl_no_aplicable():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(property="bodenzahl", p10=40, p50=50, p90=60,
                   sources_used='[{"source": "Bodenschätzung"}]'),
        _parcel(input_flags="fuera_de_alemania"),
        _cfg(),
    )
    assert nivel == "no_aplicable"
    assert any("Alemania" in m for m in motivos)


def test_de_sin_flag_bodenzahl_no_es_no_aplicable_por_pais():
    nivel, motivos, _, _ = evaluate_row(
        _fused_row(
            property="bodenzahl", p10=40, p50=50, p90=60,
            sources_used='[{"source": "A"}, {"source": "B"}]',
            agreement=0.9,
        ),
        _parcel(input_flags=""),
        _cfg(),
    )
    assert nivel != "no_aplicable"


def test_parcela_pequena_cap_ambar_sin_zonas():
    nivel, motivos, que, zonas = evaluate_row(
        _fused_row(p10=5.8, p50=6.0, p90=6.2),
        _parcel(input_flags="parcela_pequena"),
        _cfg(),
    )
    assert nivel == "ambar"
    assert zonas is False
    assert any("pequeña" in m.lower() for m in motivos)
    assert que


def test_parcela_pequena_no_suaviza_rojo():
    nivel, _, _, zonas = evaluate_row(
        _fused_row(sources_used="[]"),
        _parcel(input_flags="parcela_pequena"),
        _cfg(),
    )
    assert nivel == "rojo"
    assert zonas is False


def test_apply_abstention_zonas_internas_column():
    fused = pd.DataFrame([
        _fused_row(parcel_id="S", p10=5.8, p50=6.0, p90=6.2),
        _fused_row(parcel_id="P", p10=5.8, p50=6.0, p90=6.2),
    ])
    parcels = pd.DataFrame([
        {"parcel_id": "S", "status": "ok", "reject_reason": "", "input_flags": "", "is_peat": False},
        {"parcel_id": "P", "status": "ok", "reject_reason": "", "input_flags": "parcela_pequena", "is_peat": False},
    ])
    out = apply_abstention(fused, parcels=parcels, cfg=_cfg())
    assert bool(out.loc[out.parcel_id == "S", "zonas_internas"].iloc[0]) is True
    assert bool(out.loc[out.parcel_id == "P", "zonas_internas"].iloc[0]) is False
    assert out.loc[out.parcel_id == "P", "nivel"].iloc[0] == "ambar"
