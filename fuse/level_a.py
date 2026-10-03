"""Fusión nivel A: media ponderada por precisión (línea base).

Entrada: source_values (contrato §3). Salida: fused.parquet.
La abstención (nivel, motivos) la rellena confidence/abstention.py.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

SCALAR_PROPERTIES = ("ph_cacl2", "soc_gkg", "nfk_mm", "bodenzahl")
TEXTURE_PROPERTIES = ("sand_pct", "silt_pct", "clay_pct")
ALL_PROPERTIES = SCALAR_PROPERTIES + TEXTURE_PROPERTIES

UNITS = {
    "clay_pct": "%",
    "silt_pct": "%",
    "sand_pct": "%",
    "soc_gkg": "g/kg",
    "ph_cacl2": "pH",
    "nfk_mm": "mm",
    "bodenzahl": "—",
}

# Base ilr: sand vs silt; (sand,silt) vs clay
_ILR_V = np.array(
    [
        [1 / math.sqrt(2), 1 / math.sqrt(6)],
        [-1 / math.sqrt(2), 1 / math.sqrt(6)],
        [0.0, -2 / math.sqrt(6)],
    ]
)

FUSED_COLUMNS = [
    "parcel_id", "property", "p10", "p50", "p90", "unit", "sigma_fusion",
    "nivel", "method", "sources_used", "agreement", "di", "inside_aoa",
    "motivos", "que_faltaria",
    "best_source", "best_value", "best_sigma",
    # Antes del recorte al rango físico: lo que dijeron las fuentes de verdad.
    "p10_raw", "p50_raw", "p90_raw", "out_of_range",
]


def _cfg_get(cfg: Mapping[str, Any] | None, *keys: str, default: Any) -> Any:
    cur: Any = cfg
    for k in keys:
        if not isinstance(cur, Mapping) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def _effective_sigma(row: pd.Series) -> float:
    if "sigma_age_adj" in row.index and pd.notna(row["sigma_age_adj"]):
        s = float(row["sigma_age_adj"])
    else:
        s = float(row["sigma"])
    if not np.isfinite(s) or s <= 0:
        raise ValueError(f"sigma inválida para {row.get('source')}/{row.get('property')}: {s}")
    return s


def _physical_range(prop: str, is_peat: bool, cfg: Mapping[str, Any] | None) -> tuple[float, float]:
    fr = _cfg_get(cfg, "fusion", "physical_range", default={}) or {}
    if prop == "soc_gkg" and is_peat:
        key = "soc_gkg_peat"
    else:
        key = prop
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
        return defaults.get(prop, (-np.inf, np.inf))
    return float(pair[0]), float(pair[1])


def _clip_interval(
    p50: float, sigma: float, z: float, lo: float, hi: float
) -> tuple[float, float, float, bool]:
    """Recorta el intervalo al rango físico sin ocultar que el valor era imposible.

    Returns:
        p10, p50, p90, out_of_range. `out_of_range` es True si el p50 sin recortar
        caía fuera de [lo, hi] (o no era finito): abstention lo convierte en rojo.
    """
    if not np.isfinite(p50):
        # Dato ausente, no dato imposible: lo recoge el filtro de intervalo no calculable.
        return float("nan"), float("nan"), float("nan"), False
    out_of_range = not (lo <= p50 <= hi)
    # Ambos extremos contra ambos límites: así el intervalo nunca sale invertido.
    p10 = min(max(p50 - z * sigma, lo), hi)
    p90 = min(max(p50 + z * sigma, lo), hi)
    p50c = min(max(p50, lo), hi)
    p10, p90 = min(p10, p90), max(p10, p90)
    p50c = min(max(p50c, p10), p90)
    return p10, p50c, p90, out_of_range


def _regional_std(prop: str, cfg: Mapping[str, Any] | None, fallback: float) -> float:
    rs = _cfg_get(cfg, "fusion", "regional_std", default={}) or {}
    if prop in rs and rs[prop] is not None:
        return float(rs[prop])
    return max(fallback, 1e-6)


def _agreement(values: np.ndarray, regional_std: float) -> tuple[float, str]:
    if len(values) < 2:
        return float("nan"), "una sola fuente"
    deviation = float(np.std(values, ddof=1)) if len(values) > 1 else 0.0
    agr = 1.0 - (deviation / max(regional_std, 1e-6))
    return float(np.clip(agr, 0.0, 1.0)), ""


def _sources_used_json(rows: pd.DataFrame) -> str:
    items = []
    for _, r in rows.iterrows():
        cite = r["citation"] if "citation" in r.index and pd.notna(r.get("citation")) else r["source"]
        items.append({"source": str(r["source"]), "citation": str(cite)})
    # únicos preservando orden
    seen = set()
    uniq = []
    for it in items:
        if it["source"] not in seen:
            seen.add(it["source"])
            uniq.append(it)
    return json.dumps(uniq, ensure_ascii=False)


def replace_texture_zeros(
    sand: float,
    silt: float,
    clay: float,
    delta: float = 0.1,
) -> tuple[np.ndarray, bool]:
    """Reemplazo multiplicativo de ceros (Martín-Fernández): δ a los ≤0, el resto baja a proporción.

    `delta` está en puntos porcentuales (por defecto 0,1 %). Devuelve composición en % que suma 100
    y si hubo reemplazo.
    """
    x = np.array([float(sand), float(silt), float(clay)], dtype=float)
    x = np.where(np.isfinite(x), x, 0.0)
    zero = x <= 0
    n_z = int(zero.sum())
    if n_z == 0:
        total = float(x.sum())
        if total <= 0:
            return np.full(3, 100.0 / 3.0), True
        return x / total * 100.0, False
    if n_z == 3 or float(x[~zero].sum()) <= 0:
        return np.full(3, 100.0 / 3.0), True
    added = n_z * float(delta)
    pos_sum = float(x[~zero].sum())
    out = x.copy()
    out[zero] = float(delta)
    out[~zero] = out[~zero] * (pos_sum - added) / pos_sum
    total = float(out.sum())
    if total <= 0:
        return np.full(3, 100.0 / 3.0), True
    return out / total * 100.0, True


def replace_texture_zeros_rows(arr: np.ndarray, delta: float = 0.1) -> np.ndarray:
    """Igual que `replace_texture_zeros` fila a fila. `arr` es (n, 3) en %."""
    out = np.empty_like(arr, dtype=float)
    for i, row in enumerate(arr):
        out[i], _ = replace_texture_zeros(row[0], row[1], row[2], delta)
    return out


def composition_to_ilr(
    sand: float,
    silt: float,
    clay: float,
    delta: float = 0.1,
) -> np.ndarray:
    """(sand, silt, clay) en % → coordenadas ilr (2,). Ceros sustituidos antes del log."""
    x, _ = replace_texture_zeros(sand, silt, clay, delta)
    x = np.clip(x, 1e-12, None)
    x = x / x.sum()
    return _ILR_V.T @ np.log(x)


def ilr_to_composition(ilr: np.ndarray) -> np.ndarray:
    """ilr (2,) → (sand, silt, clay) en % que suman 100."""
    clr = _ILR_V @ np.asarray(ilr, dtype=float)
    parts = np.exp(clr)
    parts = parts / parts.sum() * 100.0
    return parts


def fuse_scalar_group(
    group: pd.DataFrame,
    prop: str,
    cfg: Mapping[str, Any] | None,
    is_peat: bool = False,
) -> dict[str, Any]:
    """Fusiona una propiedad escalar para una parcela."""
    values = group["value_std"].astype(float).to_numpy()
    sigmas = np.array([_effective_sigma(r) for _, r in group.iterrows()], dtype=float)
    inv_var = 1.0 / (sigmas ** 2)
    p50 = float(np.sum(values * inv_var) / np.sum(inv_var))
    sigma_fusion = float(1.0 / math.sqrt(np.sum(inv_var)))

    reg = _regional_std(prop, cfg, fallback=float(np.std(values)) if len(values) > 1 else abs(p50) * 0.2 + 1e-3)
    agreement, motivo = _agreement(values, reg)

    inflate_thr = float(_cfg_get(cfg, "fusion", "agreement_inflate_threshold", default=0.5))
    inflate_factor = float(_cfg_get(cfg, "fusion", "agreement_inflate_factor", default=1.5))
    if np.isfinite(agreement) and agreement < inflate_thr:
        sigma_fusion *= inflate_factor

    z = float(_cfg_get(cfg, "fusion", "p_interval_z", default=1.28))
    lo, hi = _physical_range(prop, is_peat, cfg)
    p10_raw, p90_raw = p50 - z * sigma_fusion, p50 + z * sigma_fusion
    p10, p50c, p90, out_of_range = _clip_interval(p50, sigma_fusion, z, lo, hi)

    best_i = int(np.argmin(sigmas))
    best = group.iloc[best_i]

    motivos = motivo
    # Pedotransferencia de agua útil
    if prop == "nfk_mm" and group["source"].astype(str).str.contains("Pedotransferencia|ptf", case=False, regex=True).any():
        extra = "agua útil calculada desde la textura, no medida"
        motivos = f"{motivos}; {extra}" if motivos else extra

    return {
        "property": prop,
        "p10": p10,
        "p50": p50c,
        "p90": p90,
        "unit": UNITS.get(prop, ""),
        "sigma_fusion": sigma_fusion,
        "nivel": None,
        "method": "A",
        "sources_used": _sources_used_json(group),
        "agreement": agreement,
        "di": None,
        "inside_aoa": None,
        "motivos": motivos,
        "que_faltaria": None,
        "best_source": str(best["source"]),
        "best_value": float(best["value_std"]),
        "best_sigma": float(sigmas[best_i]),
        "p10_raw": float(p10_raw),
        "p50_raw": float(p50),
        "p90_raw": float(p90_raw),
        "out_of_range": bool(out_of_range),
    }


def fuse_texture_group(
    wide: pd.DataFrame,
    cfg: Mapping[str, Any] | None,
) -> list[dict[str, Any]]:
    """Fusiona textura en ilr. `wide` tiene una fila por fuente con sand/silt/clay + sigmas."""
    n_mc = int(_cfg_get(cfg, "fusion", "texture_mc_samples", default=500))
    seed = int(_cfg_get(cfg, "fusion", "texture_mc_seed", default=42))
    rng = np.random.default_rng(seed)
    z = float(_cfg_get(cfg, "fusion", "p_interval_z", default=1.28))
    inflate_thr = float(_cfg_get(cfg, "fusion", "agreement_inflate_threshold", default=0.5))
    inflate_factor = float(_cfg_get(cfg, "fusion", "agreement_inflate_factor", default=1.5))
    delta = float(_cfg_get(cfg, "fusion", "ilr_zero_replacement_pct", default=0.1))
    replaced = False

    ilrs = []
    weights = []
    clay_vals = []
    source_meta = []
    for _, row in wide.iterrows():
        sand, silt, clay = float(row["sand_pct"]), float(row["silt_pct"]), float(row["clay_pct"])
        _, did = replace_texture_zeros(sand, silt, clay, delta)
        replaced = replaced or did
        sigs = np.array([
            float(row["sigma_sand"]),
            float(row["sigma_silt"]),
            float(row["sigma_clay"]),
        ])
        sigs = np.clip(sigs, 1e-6, None)
        w_sigma = float(np.mean(sigs))
        ilrs.append(composition_to_ilr(sand, silt, clay, delta))
        weights.append(1.0 / (w_sigma ** 2))
        clay_vals.append(clay)
        source_meta.append(row)

    ilrs_a = np.vstack(ilrs)
    w = np.asarray(weights, dtype=float)
    w = w / w.sum()
    ilr_mean = (ilrs_a * w[:, None]).sum(axis=0)

    # sigma en ilr: MC por fuente y media ponderada de muestras
    samples = []
    for _, row in wide.iterrows():
        sand = float(row["sand_pct"])
        silt = float(row["silt_pct"])
        clay = float(row["clay_pct"])
        ss = max(float(row["sigma_sand"]), 1e-6)
        si = max(float(row["sigma_silt"]), 1e-6)
        sc = max(float(row["sigma_clay"]), 1e-6)
        draw = np.column_stack([
            rng.normal(sand, ss, n_mc),
            rng.normal(silt, si, n_mc),
            rng.normal(clay, sc, n_mc),
        ])
        draw = replace_texture_zeros_rows(draw, delta)
        ilr_s = np.array([composition_to_ilr(*d, delta) for d in draw])
        samples.append(ilr_s)

    # precisión por fuente ~ 1/var media de ilr
    inv_vars = []
    for s in samples:
        var = np.var(s, axis=0).mean()
        inv_vars.append(1.0 / max(var, 1e-12))
    inv_vars_a = np.asarray(inv_vars)
    # muestras fusionadas: mezcla ponderada de ilr means muestrales no; usar ponderación de draws
    # Aprox: ilr_fusion_samples = sum_s (w_s * sample_s)
    w_s = inv_vars_a / inv_vars_a.sum()
    fused_ilr_samples = sum(ws * s for ws, s in zip(w_s, samples))
    # p50 desde ilr_mean (punto) para estabilidad; percentiles desde MC
    comp_p50 = ilr_to_composition(ilr_mean)
    comps = np.array([ilr_to_composition(v) for v in fused_ilr_samples])

    reg = _regional_std("clay_pct", cfg, fallback=12.0)
    agreement, motivo = _agreement(np.asarray(clay_vals, dtype=float), reg)
    if replaced:
        extra = (
            f"fracción de textura 0 % sustituida por {str(delta).replace('.', ',')} % para el cálculo"
        )
        motivo = f"{motivo}; {extra}" if motivo else extra

    # sigma_fusion escalar proxy: media del std muestral de componentes
    sigma_components = comps.std(axis=0, ddof=1)
    if np.isfinite(agreement) and agreement < inflate_thr:
        sigma_components = sigma_components * inflate_factor
        # re-ensanchar percentiles de forma aproximada
        comps = comp_p50 + (comps - comp_p50) * inflate_factor

    # mejor fuente: menor sigma media
    best_i = int(np.argmin([np.mean([r["sigma_sand"], r["sigma_silt"], r["sigma_clay"]]) for r in source_meta]))
    best = source_meta[best_i]
    sources_df = pd.DataFrame(source_meta)

    rows_out = []
    for j, prop in enumerate(TEXTURE_PROPERTIES):
        p10_raw = float(np.percentile(comps[:, j], 10))
        p90_raw = float(np.percentile(comps[:, j], 90))
        p50_raw = float(comp_p50[j])
        lo, hi = _physical_range(prop, False, cfg)
        out_of_range = not (np.isfinite(p50_raw) and lo <= p50_raw <= hi)
        p10 = min(max(p10_raw, lo), hi)
        p90 = min(max(p90_raw, lo), hi)
        p50 = min(max(p50_raw, lo), hi)
        p10, p90 = min(p10, p90), max(p10, p90)
        p50 = min(max(p50, p10), p90)
        rows_out.append({
            "property": prop,
            "p10": p10,
            "p50": p50,
            "p90": p90,
            "p10_raw": p10_raw,
            "p50_raw": p50_raw,
            "p90_raw": p90_raw,
            "out_of_range": out_of_range,
            "unit": UNITS[prop],
            "sigma_fusion": float(sigma_components[j]),
            "nivel": None,
            "method": "A",
            "sources_used": _sources_used_json(sources_df),
            "agreement": agreement,
            "di": None,
            "inside_aoa": None,
            "motivos": motivo,
            "que_faltaria": None,
            "best_source": str(best["source"]),
            "best_value": float(best[prop]),
            "best_sigma": float(best[f"sigma_{prop.replace('_pct', '')}"]),
        })
    # Garantizar suma 100 en p50, sin salirse del intervalo propio
    total = sum(r["p50"] for r in rows_out)
    if total > 0:
        for r in rows_out:
            r["p50"] = min(max(r["p50"] * 100.0 / total, r["p10"]), r["p90"])
    return rows_out


def _texture_wide(group: pd.DataFrame) -> pd.DataFrame | None:
    """Pivota sand/silt/clay por fuente. Omite fuentes incompletas."""
    rows = []
    for source, g in group.groupby("source"):
        props = {r["property"]: r for _, r in g.iterrows()}
        if not all(p in props for p in TEXTURE_PROPERTIES):
            continue
        rows.append({
            "source": source,
            "citation": props["sand_pct"].get("citation", source),
            "sand_pct": float(props["sand_pct"]["value_std"]),
            "silt_pct": float(props["silt_pct"]["value_std"]),
            "clay_pct": float(props["clay_pct"]["value_std"]),
            "sigma_sand": _effective_sigma(props["sand_pct"]),
            "sigma_silt": _effective_sigma(props["silt_pct"]),
            "sigma_clay": _effective_sigma(props["clay_pct"]),
        })
    return pd.DataFrame(rows) if rows else None


def fuse_level_a(
    source_values: pd.DataFrame,
    cfg: Mapping[str, Any] | None = None,
    is_peat: Mapping[str, bool] | None = None,
) -> pd.DataFrame:
    """Fusiona source_values → tabla fused (método A)."""
    if source_values.empty:
        return pd.DataFrame(columns=FUSED_COLUMNS)

    is_peat = is_peat or {}
    out_rows: list[dict[str, Any]] = []

    for parcel_id, pgrp in source_values.groupby("parcel_id"):
        peat = bool(is_peat.get(str(parcel_id), False))

        for prop in SCALAR_PROPERTIES:
            g = pgrp[pgrp["property"] == prop]
            if g.empty:
                continue
            # SoilGrids water / PTF is 0–30 cm (or profile-derived) — not nFKWe.
            # Kept as property nfk_soilgrids_0_30 for audit; never fuse into nfk_mm.
            if prop == "nfk_mm":
                src = g["source"].astype(str)
                g = g[
                    ~src.str.contains("SoilGrids|soilgrids", case=False, regex=True, na=False)
                ]
                if g.empty:
                    continue
            row = fuse_scalar_group(g, prop, cfg, is_peat=peat)
            row["parcel_id"] = str(parcel_id)
            out_rows.append(row)

        tex = pgrp[pgrp["property"].isin(TEXTURE_PROPERTIES)]
        if not tex.empty:
            wide = _texture_wide(tex)
            if wide is not None and len(wide):
                for row in fuse_texture_group(wide, cfg):
                    row["parcel_id"] = str(parcel_id)
                    out_rows.append(row)

    return pd.DataFrame(out_rows, columns=FUSED_COLUMNS)


def fuse_file(
    source_path: str | Path,
    out_path: str | Path,
    cfg: Mapping[str, Any] | None = None,
    parcels_path: str | Path | None = None,
) -> pd.DataFrame:
    """Lee source_values.parquet, escribe fused.parquet."""
    src = pd.read_parquet(source_path)
    peat_map: dict[str, bool] = {}
    if parcels_path and Path(parcels_path).exists():
        parcels = pd.read_parquet(parcels_path)
        if "is_peat" in parcels.columns:
            peat_map = {
                str(r["parcel_id"]): bool(r["is_peat"])
                for _, r in parcels.iterrows()
            }
    fused = fuse_level_a(src, cfg=cfg, is_peat=peat_map)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fused.to_parquet(out_path, index=False)
    return fused
