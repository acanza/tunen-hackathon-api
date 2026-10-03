"""Abstención graduada por propiedad y parcela (verde → rojo / no_aplicable).

Rellena nivel, motivos y que_faltaria sobre fused.parquet.
El peor filtro gana. Umbrales en config.yaml.
"""

from __future__ import annotations

import csv
import json
import re
import warnings
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from fuse.level_a import ALL_PROPERTIES, FUSED_COLUMNS, UNITS

NIVELES = ("verde", "ambar", "parcial", "rojo", "no_aplicable")
_SEVERITY = {"verde": 0, "ambar": 1, "parcial": 2, "rojo": 3, "no_aplicable": 4}

_ROOT = Path(__file__).resolve().parents[1]
_TEXTURE_PROPS = frozenset({"clay_pct", "silt_pct", "sand_pct"})
MOTIVO_GEOLOGIA_TEXTURA = "la geología no encaja con la textura estimada"
MOTIVO_GEOLOGIA_TURBERA = "geología de turbera"
MOTIVO_BODENART_TEXTURA = "la valoración oficial no encaja con la textura estimada"

# Plantillas fijas (nunca LLM).
_QUE_FALTARIA = {
    "rechazo_entrada": "Corregir la geometría o el tamaño de la parcela",
    "no_agricola_bodenzahl": "Bodenzahl solo se aplica en tierra agrícola",
    "sin_fuentes": "Un mapa de suelo del Land o una muestra de laboratorio de 0-30 cm",
    "una_fuente": "Un mapa de suelo más detallado del Land",
    "escala_gruesa": "Un mapa de suelo más detallado (mejor que 1:1.000.000)",
    "fuera_aoa": "Más puntos de calibración en esta zona",
    "incertidumbre": "Una muestra de laboratorio de 0-30 cm",
    "fuera_rango": "Revisar las fuentes: el valor sale del rango físico esperado",
    "intervalo_no_calculable": "Revisar las sigmas de las fuentes: no se pudo calcular el intervalo",
    "fuente_caida": "Reintentar la descarga de la fuente que no respondió",
    "sin_fuente_zona": "Un mapa de suelo del Land o una muestra de laboratorio de 0-30 cm",
    "desacuerdo": "Una medición de laboratorio para resolver el desacuerdo entre fuentes",
    "bodenzahl_cruzada": "Comprobar la Bodenschätzung oficial frente al suelo actual",
    "parcela_pequena": "Una parcela más grande o una muestra de laboratorio de 0-30 cm",
    "geologia_textura": "Una muestra de laboratorio de 0-30 cm para contrastar textura y geología",
    "geologia_turbera": "Confirmación de turba (mapa de suelo BÜK200 o humus de laboratorio)",
    "bodenart_textura": "Una muestra de laboratorio de 0-30 cm para contrastar textura y Bodenschätzung",
}


def _cfg_get(cfg: Mapping[str, Any] | None, *keys: str, default: Any) -> Any:
    cur: Any = cfg
    for k in keys:
        if not isinstance(cur, Mapping) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _worse(a: str, b: str) -> str:
    return a if _SEVERITY.get(a, 0) >= _SEVERITY.get(b, 0) else b


def _parse_flags(flags: Any) -> list[str]:
    if flags is None or (isinstance(flags, float) and np.isnan(flags)):
        return []
    if isinstance(flags, list):
        return [str(f) for f in flags]
    return [p for p in str(flags).split(";") if p]


def _n_sources(sources_used: Any) -> int:
    if sources_used is None or (isinstance(sources_used, float) and np.isnan(sources_used)):
        return 0
    if isinstance(sources_used, list):
        return len(sources_used)
    try:
        data = json.loads(sources_used) if isinstance(sources_used, str) else sources_used
        return len(data) if data is not None else 0
    except (TypeError, json.JSONDecodeError):
        return 0


def _parse_map_scale_denominator(scale: Any) -> float | None:
    """Devuelve N en '1:N' (puntos como separador de miles). None si no es escala de mapa."""
    if scale is None or (isinstance(scale, float) and np.isnan(scale)):
        return None
    s = str(scale).strip().lower()
    m = re.match(r"^1\s*:\s*([\d.\s]+)$", s)
    if not m:
        return None
    digits = m.group(1).replace(".", "").replace(" ", "")
    try:
        return float(digits)
    except ValueError:
        return None


def _width_threshold(prop: str, p50: float, cfg: Mapping[str, Any] | None) -> float:
    w = _cfg_get(cfg, "abstention", "width_amber", default={}) or {}
    if prop == "soc_gkg":
        frac = float(w.get("soc_gkg_frac_of_p50", 0.60))
        return abs(float(p50)) * frac
    # textura: usar umbral de arcilla si no hay propio
    if prop in w:
        return float(w[prop])
    if prop in ("sand_pct", "silt_pct", "clay_pct"):
        return float(w.get("clay_pct", 15.0))
    return float("inf")


def _is_finite(value: Any) -> bool:
    """True solo si es un número finito. None, NaN, pd.NA y texto son 'falta el dato'."""
    if value is None or value is pd.NA:
        return False
    try:
        return bool(np.isfinite(float(value)))
    except (TypeError, ValueError):
        return False


def _physical_ok(prop: str, p50: float, is_peat: bool, cfg: Mapping[str, Any] | None) -> bool:
    fr = _cfg_get(cfg, "fusion", "physical_range", default={}) or {}
    key = "soc_gkg_peat" if prop == "soc_gkg" and is_peat else prop
    pair = fr.get(key)
    if pair is None:
        defaults = {
            "ph_cacl2": (3.0, 9.0),
            "soc_gkg": (0.0, 200.0),
            "soc_gkg_peat": (0.0, 580.0),
            "nfk_mm": (0.0, 300.0),
            "bodenzahl": (7.0, 100.0),
            "sand_pct": (0.0, 100.0),
            "silt_pct": (0.0, 100.0),
            "clay_pct": (0.0, 100.0),
        }
        pair = defaults.get(prop)
    if pair is None:
        return True
    if not _is_finite(p50):
        return False
    lo, hi = float(pair[0]), float(pair[1])
    return lo <= float(p50) <= hi


def _out_of_physical_range(
    row: pd.Series,
    prop: str,
    is_peat: bool,
    cfg: Mapping[str, Any] | None,
) -> bool:
    """¿Vieron las fuentes un valor imposible? Se juzga ANTES del recorte de la fusión.

    `level_a` recorta p50 al rango físico, así que mirar p50 nunca detectaría nada:
    se usa la marca `out_of_range` y, si no está, `p50_raw`.
    """
    flag = row.get("out_of_range")
    if flag is not None and pd.notna(flag):
        return bool(flag)
    value = row.get("p50_raw")
    if not _is_finite(value):
        value = row.get("p50")
    if not _is_finite(value):
        return False  # dato ausente: lo marca el filtro de intervalo, no este
    return not _physical_ok(prop, value, is_peat, cfg)


def _scales_for_row(
    parcel_id: str,
    prop: str,
    source_values: pd.DataFrame | None,
) -> list[float]:
    """Denominadores de escala 1:N para las fuentes de esta fila."""
    if source_values is None or source_values.empty or "scale" not in source_values.columns:
        return []
    g = source_values[
        (source_values["parcel_id"].astype(str) == str(parcel_id))
        & (source_values["property"] == prop)
    ]
    out = []
    for s in g["scale"]:
        den = _parse_map_scale_denominator(s)
        if den is not None:
            out.append(den)
    return out


def load_texture_conflicts(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Conflict rules: grupo × property × op × threshold (thresholds in CSV only).

    Shared by GÜK200 geology and Bodenschätzung Bodenart (same schema).
    """
    p = Path(path) if path else _ROOT / "data" / "ref" / "geology_texture_conflicts.csv"
    if not p.exists():
        warnings.warn(f"Missing texture conflicts table: {p}", stacklevel=2)
        return []
    rows: list[dict[str, Any]] = []
    with p.open(encoding="utf-8", newline="") as fh:
        for raw in csv.DictReader(fh):
            try:
                thr = float(raw["threshold"])
            except (KeyError, TypeError, ValueError):
                continue
            rows.append(
                {
                    "grupo": (raw.get("grupo") or "").strip(),
                    "property": (raw.get("property") or "").strip(),
                    "op": (raw.get("op") or "").strip(),
                    "threshold": thr,
                }
            )
    return rows


def load_geology_texture_conflicts(path: str | Path | None = None) -> list[dict[str, Any]]:
    """Alias of :func:`load_texture_conflicts` (GÜK200 path default)."""
    return load_texture_conflicts(path)


def _op_holds(value: float, op: str, threshold: float) -> bool:
    if op == ">=":
        return value >= threshold
    if op == "<=":
        return value <= threshold
    if op == ">":
        return value > threshold
    if op == "<":
        return value < threshold
    if op == "==":
        return value == threshold
    return False


def geology_dominants(
    geology: pd.DataFrame | None,
) -> dict[str, tuple[str | None, float]]:
    """parcel_id → (dominant grupo, area fraction), ignoring TODO units."""
    if geology is None or geology.empty:
        return {}
    from ingest.guek import dominant_grupo

    out: dict[str, tuple[str | None, float]] = {}
    for pid, grp in geology.groupby(geology["parcel_id"].astype(str), sort=False):
        out[str(pid)] = dominant_grupo(grp.to_dict(orient="records"))
    return out


def geology_texture_conflict(
    grupo: str | None,
    prop: str,
    p50: float | None,
    conflicts: list[dict[str, Any]],
) -> bool:
    """True if fused texture contradicts a dominant soil/geology group (CSV rules).

    Used for GÜK200 geology and Bodenschätzung Bodenart — same mechanism.
    """
    if not grupo or p50 is None or not _is_finite(p50):
        return False
    if prop not in _TEXTURE_PROPS:
        return False
    for rule in conflicts:
        if rule["grupo"] != grupo or rule["property"] != prop:
            continue
        if _op_holds(float(p50), rule["op"], float(rule["threshold"])):
            return True
    return False


def bodenart_dominants(
    bodenart: pd.DataFrame | None,
) -> dict[str, tuple[str | None, float]]:
    """parcel_id → (dominant grupo, fraction) from Bodenschätzung covariate table."""
    if bodenart is None or bodenart.empty:
        return {}
    out: dict[str, tuple[str | None, float]] = {}
    for pid, grp in bodenart.groupby(bodenart["parcel_id"].astype(str), sort=False):
        # Expect columns grupo + area_fraction (one row per parcel OK).
        if "grupo" not in grp.columns:
            continue
        if "area_fraction" in grp.columns and len(grp) == 1:
            g0 = grp.iloc[0]
            grupo = g0["grupo"]
            out[str(pid)] = (
                None if grupo is None or (isinstance(grupo, float) and np.isnan(grupo)) else str(grupo),
                float(g0["area_fraction"]),
            )
            continue
        # Multiple rows: weight by area_fraction if present.
        weights: dict[str, float] = {}
        for _, r in grp.iterrows():
            g = r.get("grupo")
            if g is None or (isinstance(g, float) and np.isnan(g)) or not str(g).strip():
                continue
            w = float(r["area_fraction"]) if "area_fraction" in grp.columns else 1.0
            weights[str(g)] = weights.get(str(g), 0.0) + w
        if not weights:
            out[str(pid)] = (None, 0.0)
            continue
        total = sum(weights.values()) or 1.0
        best = max(weights, key=weights.get)
        out[str(pid)] = (best, weights[best] / total)
    return out


def evaluate_row(
    row: pd.Series,
    parcel: pd.Series | None,
    cfg: Mapping[str, Any] | None,
    source_values: pd.DataFrame | None = None,
    geology_dom: tuple[str | None, float] | None = None,
    geology_conflicts: list[dict[str, Any]] | None = None,
    bodenart_dom: tuple[str | None, float] | None = None,
    bodenart_conflicts: list[dict[str, Any]] | None = None,
) -> tuple[str, list[str], str, bool]:
    """Devuelve (nivel, motivos, que_faltaria, zonas_internas) para una fila fused."""
    nivel = "verde"
    motivos: list[str] = []
    faltaria_key: str | None = None
    zonas_internas = True

    flags = _parse_flags(parcel.get("input_flags") if parcel is not None else None)
    status = str(parcel.get("status", "ok")) if parcel is not None else "ok"
    reject = str(parcel.get("reject_reason", "") or "") if parcel is not None else ""
    is_peat = bool(parcel.get("is_peat", False)) if parcel is not None else False
    prop = str(row["property"])
    parcela_pequena = "parcela_pequena" in flags
    geo_grupo, geo_frac = geology_dom if geology_dom is not None else (None, 0.0)
    ba_grupo, ba_frac = bodenart_dom if bodenart_dom is not None else (None, 0.0)

    # --- 0. Entrada ---
    if status != "ok" or reject:
        nivel = _worse(nivel, "rojo")
        motivos.append(f"Parcela rechazada en la entrada ({reject or status})")
        faltaria_key = "rechazo_entrada"

    if prop == "bodenzahl" and "no_agricola" in flags:
        return (
            "no_aplicable",
            ["Bodenzahl solo existe en tierra agrícola"],
            _QUE_FALTARIA["no_agricola_bodenzahl"],
            False if parcela_pequena else zonas_internas,
        )

    if prop == "bodenzahl" and "fuera_de_alemania" in flags:
        return (
            "no_aplicable",
            ["fuente solo disponible en Alemania"],
            "Bodenzahl solo está disponible en Alemania",
            False if parcela_pequena else zonas_internas,
        )

    # Fuentes alemanas (nombre de source en sources_used)
    if "fuera_de_alemania" in flags:
        su = str(row.get("sources_used") or "")
        german_markers = ("BÜK", "BUEK", "Bodenschätzung", "Bodenschaetzung", "Hessen", "BGR")
        if any(m in su for m in german_markers):
            return (
                "no_aplicable",
                ["fuente solo disponible en Alemania"],
                "Fuente alemana no disponible fuera de Alemania",
                False if parcela_pequena else zonas_internas,
            )

    # --- 1. Cobertura ---
    n_src = _n_sources(row.get("sources_used"))
    if n_src == 0:
        nivel = _worse(nivel, "rojo")
        motivos.append("Ninguna fuente disponible")
        faltaria_key = "sin_fuentes"
    elif n_src == 1:
        nivel = _worse(nivel, "ambar")
        motivos.append("Una sola fuente")
        faltaria_key = faltaria_key or "una_fuente"

    coarse_min = float(_cfg_get(cfg, "abstention", "coarse_scale_min", default=1_000_000))
    dens = _scales_for_row(str(row["parcel_id"]), prop, source_values)
    if dens and all(d >= coarse_min for d in dens):
        nivel = _worse(nivel, "ambar")
        motivos.append("Solo fuentes a escala ≥ 1:1.000.000")
        faltaria_key = faltaria_key or "escala_gruesa"

    # --- 2. Dominio (AoA): se salta si la columna no existe o es NaN ---
    if "inside_aoa" in row.index and pd.notna(row.get("inside_aoa")):
        if not bool(row["inside_aoa"]):
            nivel = _worse(nivel, "parcial")
            motivos.append("Fuera del área de aplicabilidad del modelo")
            faltaria_key = faltaria_key or "fuera_aoa"

    # --- 3. Incertidumbre ---
    # Un intervalo con NaN no "pasa" el filtro: sin intervalo no hay respuesta.
    bounds = [row.get("p10"), row.get("p50"), row.get("p90")]
    if not all(_is_finite(v) for v in bounds):
        nivel = _worse(nivel, "rojo")
        motivos.append("Intervalo no calculable (falta p10, p50 o p90)")
        faltaria_key = faltaria_key or "intervalo_no_calculable"
    else:
        p10, p50, p90 = (float(v) for v in bounds)
        width = p90 - p10
        thr = _width_threshold(prop, p50, cfg)
        if np.isfinite(thr) and width > 2 * thr:
            nivel = _worse(nivel, "parcial")
            motivos.append(f"Intervalo muy ancho ({width:.2g} > 2×{thr:.2g})")
            faltaria_key = faltaria_key or "incertidumbre"
        elif np.isfinite(thr) and width > thr:
            nivel = _worse(nivel, "ambar")
            motivos.append(f"Intervalo ancho ({width:.2g} > {thr:.2g})")
            faltaria_key = faltaria_key or "incertidumbre"

    # --- 4. Coherencia ---
    if _out_of_physical_range(row, prop, is_peat, cfg):
        nivel = _worse(nivel, "rojo")
        motivos.append("Valor imposible en las fuentes")
        faltaria_key = "fuera_rango"

    agr = row.get("agreement")
    agr_thr = float(_cfg_get(cfg, "abstention", "agreement_amber", default=0.3))
    if pd.notna(agr) and float(agr) < agr_thr:
        nivel = _worse(nivel, "ambar")
        motivos.append(f"Poco acuerdo entre fuentes ({float(agr):.2f})")
        faltaria_key = faltaria_key or "desacuerdo"

    delta_thr = float(_cfg_get(cfg, "abstention", "bodenzahl_model_delta_amber", default=15))
    p50_cmp = float(row["p50"]) if _is_finite(row.get("p50")) else None
    if (
        prop == "bodenzahl"
        and p50_cmp is not None
        and "bodenzahl_modeled" in row.index
        and pd.notna(row.get("bodenzahl_modeled"))
    ):
        delta = abs(p50_cmp - float(row["bodenzahl_modeled"]))
        if delta > delta_thr:
            nivel = _worse(nivel, "ambar")
            motivos.append("La valoración oficial y el suelo actual no coinciden")
            faltaria_key = faltaria_key or "bodenzahl_cruzada"

    # Geología vs textura (aviso ámbar; nunca rojo). Umbral de cobertura en config.
    frac_min = float(
        _cfg_get(
            cfg,
            "abstention",
            "geology_dominant_frac_min",
            default=_cfg_get(cfg, "guek200", "dominant_frac_min", default=0.7),
        )
    )
    if (
        prop in _TEXTURE_PROPS
        and geo_grupo
        and geo_frac >= frac_min
        and geology_conflicts
        and p50_cmp is not None
        and geology_texture_conflict(geo_grupo, prop, p50_cmp, geology_conflicts)
    ):
        # Never escalate to rojo — amber warning only.
        if nivel != "rojo":
            nivel = _worse(nivel, "ambar")
        if MOTIVO_GEOLOGIA_TEXTURA not in motivos:
            motivos.append(MOTIVO_GEOLOGIA_TEXTURA)
        faltaria_key = faltaria_key or "geologia_textura"

    # Bodenschätzung Bodenart vs fused texture (same CSV mechanism as geology).
    ba_frac_min = float(
        _cfg_get(
            cfg,
            "abstention",
            "bodenart_dominant_frac_min",
            default=_cfg_get(cfg, "lbeg", "dominant_frac_min", default=0.7),
        )
    )
    if (
        prop in _TEXTURE_PROPS
        and ba_grupo
        and ba_frac >= ba_frac_min
        and bodenart_conflicts
        and p50_cmp is not None
        and geology_texture_conflict(ba_grupo, prop, p50_cmp, bodenart_conflicts)
    ):
        if nivel != "rojo":
            nivel = _worse(nivel, "ambar")
        if MOTIVO_BODENART_TEXTURA not in motivos:
            motivos.append(MOTIVO_BODENART_TEXTURA)
        faltaria_key = faltaria_key or "bodenart_textura"

    # Turba geológica: indicio para is_peat; por sí sola no marca is_peat = True.
    if geo_grupo == "turba" and geo_frac >= frac_min:
        if MOTIVO_GEOLOGIA_TURBERA not in motivos:
            motivos.append(MOTIVO_GEOLOGIA_TURBERA)
        if nivel != "rojo" and _SEVERITY.get(nivel, 0) < _SEVERITY["ambar"]:
            nivel = "ambar"
        faltaria_key = faltaria_key or "geologia_turbera"

    # Conservar motivo de fusión si era "una sola fuente" y no lo añadimos ya
    prev = row.get("motivos")
    if isinstance(prev, str) and prev and prev not in motivos:
        if prev == "una sola fuente" and n_src == 1:
            pass  # ya cubierto
        elif prev not in ("", "None"):
            motivos.append(prev)

    # Parcela pequeña: como máximo ámbar; sin zonas internas
    if parcela_pequena:
        zonas_internas = False
        if _SEVERITY.get(nivel, 0) < _SEVERITY["ambar"]:
            nivel = "ambar"
        if "Parcela pequeña: sin zonas internas" not in motivos:
            motivos.append("Parcela pequeña: sin zonas internas")
        faltaria_key = faltaria_key or "parcela_pequena"

    que = _QUE_FALTARIA.get(faltaria_key, "") if faltaria_key else ""
    if nivel == "verde":
        que = ""
    return nivel, motivos, que, zonas_internas


def _ingest_failed(parcel_id: str, ingest_log: pd.DataFrame | None) -> bool:
    """True si la ingesta de suelo de esa parcela quedó en error."""
    if ingest_log is None or ingest_log.empty or "parcel_id" not in ingest_log.columns:
        return False
    g = ingest_log[ingest_log["parcel_id"].astype(str) == str(parcel_id)]
    if g.empty or "source" not in g.columns or "status" not in g.columns:
        return False
    soil = g[g["source"].astype(str).isin(["soil", "soilgrids"])]
    return bool((soil["status"].astype(str) == "error").any())


def _empty_fused_row(parcel_id: str, prop: str, motivo: str, que: str) -> dict[str, Any]:
    row = {c: None for c in FUSED_COLUMNS}
    row.update({
        "parcel_id": str(parcel_id),
        "property": prop,
        "p10": float("nan"),
        "p50": float("nan"),
        "p90": float("nan"),
        "p10_raw": float("nan"),
        "p50_raw": float("nan"),
        "p90_raw": float("nan"),
        "out_of_range": False,
        "unit": UNITS.get(prop, ""),
        "sigma_fusion": float("nan"),
        "nivel": "rojo",
        "method": "A",
        "sources_used": "[]",
        "agreement": float("nan"),
        "motivos": motivo,
        "que_faltaria": que,
        "best_source": "",
        "best_value": float("nan"),
        "best_sigma": float("nan"),
    })
    return row


def ensure_complete_fused(
    fused: pd.DataFrame,
    parcels: pd.DataFrame | None,
    ingest_log: pd.DataFrame | None = None,
    properties: tuple[str, ...] = ALL_PROPERTIES,
) -> pd.DataFrame:
    """Producto cartesiano parcela × propiedad. Las celdas vacías entran en rojo."""
    if parcels is None or parcels.empty or "parcel_id" not in parcels.columns:
        return fused
    have: set[tuple[str, str]] = set()
    if fused is not None and not fused.empty:
        for _, r in fused.iterrows():
            have.add((str(r["parcel_id"]), str(r["property"])))
    extra = []
    for pid in parcels["parcel_id"].astype(str).unique():
        failed = _ingest_failed(pid, ingest_log)
        if failed:
            motivo = "fuente no respondió (fallo del servicio)"
            que = _QUE_FALTARIA["fuente_caida"]
        else:
            motivo = "no hay fuente para esta zona"
            que = _QUE_FALTARIA["sin_fuente_zona"]
        for prop in properties:
            if (pid, prop) not in have:
                extra.append(_empty_fused_row(pid, prop, motivo, que))
    if not extra:
        return fused if fused is not None else pd.DataFrame(columns=FUSED_COLUMNS)
    add = pd.DataFrame(extra, columns=FUSED_COLUMNS)
    if fused is None or fused.empty:
        return add
    # columnas nuevas de FUSED_COLUMNS que fused antiguo no trae
    for c in FUSED_COLUMNS:
        if c not in fused.columns:
            fused = fused.copy()
            fused[c] = None
    return pd.concat([fused, add], ignore_index=True)


def apply_abstention(
    fused: pd.DataFrame,
    parcels: pd.DataFrame | None = None,
    source_values: pd.DataFrame | None = None,
    cfg: Mapping[str, Any] | None = None,
    ingest_log: pd.DataFrame | None = None,
    geology: pd.DataFrame | None = None,
    bodenart: pd.DataFrame | None = None,
) -> pd.DataFrame:
    """Devuelve copia de fused con nivel, motivos y que_faltaria rellenados.

    Antes de filtrar, completa el producto parcela × propiedad: una celda sin fila
    nunca se queda en silencio (docs/auditoria.md §12a).

    ``geology`` is the GÜK200 table (data/features/geology.parquet): covariate only;
    coherence warnings are ámbar, never rojo. Peat geology adds a motivo but does
    not set parcels.is_peat.

    ``bodenart`` is the Bodenschätzung dominant-group table (parcel_id, grupo,
    area_fraction): same conflict mechanism, distinct farmer-facing motivo.
    """
    fused = ensure_complete_fused(fused, parcels, ingest_log=ingest_log)
    out = fused.copy()
    parcels_idx = None
    if parcels is not None and not parcels.empty:
        p = parcels.copy()
        p["parcel_id"] = p["parcel_id"].astype(str)
        parcels_idx = p.set_index("parcel_id", drop=False)

    conflicts_path = _cfg_get(cfg, "guek200", "texture_conflicts", default=None)
    if conflicts_path and not Path(str(conflicts_path)).is_absolute():
        conflicts_path = _ROOT / str(conflicts_path)
    conflicts = load_texture_conflicts(conflicts_path)
    dom_by_parcel = geology_dominants(geology)

    ba_path = _cfg_get(cfg, "lbeg", "texture_conflicts", default=None)
    if ba_path and not Path(str(ba_path)).is_absolute():
        ba_path = _ROOT / str(ba_path)
    ba_conflicts = load_texture_conflicts(ba_path) if ba_path else []
    ba_dom = bodenart_dominants(bodenart)

    niveles, motivos_l, faltaria_l, zonas_l = [], [], [], []
    for _, row in out.iterrows():
        parcel = None
        pid = str(row["parcel_id"])
        if parcels_idx is not None and pid in parcels_idx.index:
            parcel = parcels_idx.loc[pid]
            if isinstance(parcel, pd.DataFrame):
                parcel = parcel.iloc[0]
        nivel, motivos, que, zonas = evaluate_row(
            row,
            parcel,
            cfg,
            source_values,
            geology_dom=dom_by_parcel.get(pid),
            geology_conflicts=conflicts,
            bodenart_dom=ba_dom.get(pid),
            bodenart_conflicts=ba_conflicts,
        )
        if not que:
            que = str(row.get("que_faltaria") or "")
        # Geología / Bodenschätzung nunca endurecen a rojo por sí solas.
        if nivel == "rojo" and motivos == [MOTIVO_GEOLOGIA_TEXTURA]:
            nivel = "ambar"
        if nivel == "rojo" and motivos == [MOTIVO_GEOLOGIA_TURBERA]:
            nivel = "ambar"
        if nivel == "rojo" and motivos == [MOTIVO_BODENART_TEXTURA]:
            nivel = "ambar"
        niveles.append(nivel)
        motivos_l.append("; ".join(motivos) if motivos else "")
        faltaria_l.append(que)
        zonas_l.append(bool(zonas))

    out["nivel"] = niveles
    out["motivos"] = motivos_l
    out["que_faltaria"] = faltaria_l
    out["zonas_internas"] = zonas_l
    return out
