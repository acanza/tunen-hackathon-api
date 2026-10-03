"""Conversiones de unidades, profundidad e incertidumbre (sin red).

Lee tablas de data/ref y umbrales de config.yaml. No inventa valores de referencia.
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_DEFAULT_KA5 = _ROOT / "data" / "ref" / "ka5_texture_classes.csv"

# Defaults si config no trae la clave (valores indicativos; ver config.yaml).
_DEFAULTS = {
    "texture_limit_sigma_inflate": 1.2,
    "ph_h2o_to_cacl2_offset": 0.55,
    "ph_conversion_sigma_extra": 0.3,
    "peat_humus_pct_threshold": 30.0,
    "humus_to_soc_factor": 1.72,
}


def _cfg_get(cfg: Mapping[str, Any] | None, *keys: str, default: Any) -> Any:
    """Navega cfg[keys...] o devuelve default."""
    if cfg is None:
        return default
    cur: Any = cfg
    for k in keys:
        if not isinstance(cur, Mapping) or k not in cur:
            return default
        cur = cur[k]
    return default if cur is None else cur


def soilgrids_texture_to_pct(g_per_kg: float) -> float:
    """SoilGrids textura (g/kg) → porcentaje."""
    return float(g_per_kg) / 10.0


def texture_limit_adjustment(
    sand: float,
    silt: float,
    clay: float,
    method: str = "none",
    cfg: Mapping[str, Any] | None = None,
) -> tuple[float, float, float, float, str]:
    """Ajusta (o documenta) el límite arena/limo 50 µm vs 63 µm.

    Returns:
        sand, silt, clay, factor de inflado de sigma, nota.
    """
    if method == "loglinear":
        raise NotImplementedError(
            "Ajuste log-lineal del límite 50→63 µm: necesita fracciones adicionales "
            "(no disponibles en SoilGrids estándar). Usa method='none'."
        )
    if method != "none":
        raise ValueError(f"method desconocido: {method!r} (usa 'none' o 'loglinear')")

    inflate = float(
        _cfg_get(cfg, "conversions", "texture_limit_sigma_inflate", default=_DEFAULTS["texture_limit_sigma_inflate"])
    )
    note = "límite arena/limo 50 µm frente a 63 µm, sin corregir"
    return float(sand), float(silt), float(clay), inflate, note


def ka5_class_to_pct(
    clase: str,
    csv_path: str | Path | None = None,
) -> tuple[float, float, float, float, float, float]:
    """KA5 texture class → (clay_center, silt_center, sand_center, clay_sd, silt_sd, sand_sd) %.

    Values derived from polygon vertices of the KA4/KA5 texture triangle
    (R package soiltexture, DE.BK94.TT). Do not edit by hand.

    Reads clay_center / silt_center / sand_center / clay_sd / silt_sd / sand_sd
    directly from the CSV. Never recompute midpoints or (max−min)/√12.
    Unknown class → ValueError. Missing/empty centre or SD cells → ValueError.
    """
    path = Path(csv_path) if csv_path else _DEFAULT_KA5
    if not path.exists():
        raise FileNotFoundError(f"Tabla KA5 no encontrada: {path}")

    # Values derived from polygon vertices of the KA4/KA5 texture triangle
    # (R package soiltexture, DE.BK94.TT). Do not edit by hand.
    df = pd.read_csv(path)
    key_col = "ka5_class" if "ka5_class" in df.columns else "clase"
    row = df.loc[df[key_col].astype(str) == str(clase)]
    if row.empty:
        raise ValueError(f"Clase KA5 desconocida: {clase!r}. Revisar {path.name}.")
    r = row.iloc[0]

    needed = [
        "clay_center", "silt_center", "sand_center",
        "clay_sd", "silt_sd", "sand_sd",
    ]
    missing = [c for c in needed if c not in r.index or pd.isna(r.get(c)) or str(r.get(c)).strip() == ""]
    if missing:
        fuente = r.get("source", r.get("fuente", ""))
        raise ValueError(
            f"Clase KA5 {clase!r}: centros/SD sin verificar ({', '.join(missing)}). "
            f"source={fuente!r}. No regenerar: usar centroides del triángulo KA4/KA5."
        )

    return (
        float(r["clay_center"]),
        float(r["silt_center"]),
        float(r["sand_center"]),
        float(r["clay_sd"]),
        float(r["silt_sd"]),
        float(r["sand_sd"]),
    )


def soilgrids_ph_to_cacl2(
    ph_x10: float,
    cfg: Mapping[str, Any] | None = None,
    offset: float | None = None,
) -> tuple[float, float]:
    """pH SoilGrids (×10 en H2O) → (pH CaCl2, sigma_extra)."""
    off = offset if offset is not None else float(
        _cfg_get(cfg, "conversions", "ph_h2o_to_cacl2_offset", default=_DEFAULTS["ph_h2o_to_cacl2_offset"])
    )
    sigma_extra = float(
        _cfg_get(cfg, "conversions", "ph_conversion_sigma_extra", default=_DEFAULTS["ph_conversion_sigma_extra"])
    )
    ph_h2o = float(ph_x10) / 10.0
    return ph_h2o - off, sigma_extra


def humus_to_soc(humus_pct: float, cfg: Mapping[str, Any] | None = None) -> float:
    """Humus (%) → SOC (g/kg). Factor van Bemmelen 1.72 (verificar)."""
    factor = float(
        _cfg_get(cfg, "conversions", "humus_to_soc_factor", default=_DEFAULTS["humus_to_soc_factor"])
    )
    return float(humus_pct) / factor * 10.0


def soilgrids_soc_to_gkg(dg_per_kg: float) -> float:
    """SoilGrids SOC (dg/kg) → g/kg."""
    return float(dg_per_kg) / 10.0


def depth_weighted_mean(
    values_by_layer: Sequence[float],
    layers_cm: Sequence[tuple[float, float]],
    target: tuple[float, float] = (0.0, 30.0),
) -> float:
    """Media ponderada por espesor en [target_top, target_bottom] cm.

    Recorta horizontes que sobresalen del intervalo objetivo.
    """
    if len(values_by_layer) != len(layers_cm):
        raise ValueError("values_by_layer y layers_cm deben tener la misma longitud")
    t0, t1 = float(target[0]), float(target[1])
    if t1 <= t0:
        raise ValueError(f"target inválido: {target}")

    num = 0.0
    den = 0.0
    for val, (top, bot) in zip(values_by_layer, layers_cm):
        top_f, bot_f = float(top), float(bot)
        if bot_f <= top_f:
            raise ValueError(f"horizonte inválido: ({top_f}, {bot_f})")
        lo = max(top_f, t0)
        hi = min(bot_f, t1)
        thickness = hi - lo
        if thickness <= 0:
            continue
        num += float(val) * thickness
        den += thickness
    if den <= 0:
        raise ValueError(f"ningún horizonte solapa el intervalo {target}")
    return num / den


def sigma_from_quantiles(q05: float, q95: float) -> float:
    """Sigma aproximada desde intervalo 90 %: (Q95 − Q05) / 3.29."""
    return (float(q95) - float(q05)) / 3.29


def age_adjusted_sigma(
    sigma: float,
    property: str,
    source_year: int,
    current_year: int,
    cfg: Mapping[str, Any] | None = None,
) -> float:
    """sigma × (1 + k × años / 10); k por propiedad en age_uncertainty (resto 0)."""
    k = float(_cfg_get(cfg, "age_uncertainty", property, default=0.0))
    years = max(0, int(current_year) - int(source_year))
    return float(sigma) * (1.0 + k * years / 10.0)


def is_peat_from_humus(
    humus_pct: float,
    cfg: Mapping[str, Any] | None = None,
    threshold: float | None = None,
) -> bool:
    """True si humus ≥ umbral KA5 de Torf (config; verificar)."""
    if threshold is not None:
        thr = float(threshold)
    else:
        thr = float(
            _cfg_get(cfg, "conversions", "peat_humus_pct_threshold", default=_DEFAULTS["peat_humus_pct_threshold"])
        )
        if cfg is None or "conversions" not in cfg or "peat_humus_pct_threshold" not in (cfg.get("conversions") or {}):
            warnings.warn(
                "Umbral de turba = 30 % humus (indicativo KA5 Torf, verificar en config).",
                UserWarning,
                stacklevel=2,
            )
    return float(humus_pct) >= thr


_DEFAULT_SAXTON = _ROOT / "data" / "ref" / "saxton_rawls_2006.csv"


def _load_saxton_coefs(csv_path: str | Path | None = None) -> dict[str, float]:
    path = Path(csv_path) if csv_path else _DEFAULT_SAXTON
    if not path.exists():
        raise FileNotFoundError(f"Coeficientes Saxton-Rawls no encontrados: {path}")
    df = pd.read_csv(path)
    needed = [
        "theta_1500t_S", "theta_1500t_C", "theta_1500t_OM", "theta_1500t_S_OM",
        "theta_1500t_C_OM", "theta_1500t_S_C", "theta_1500t_intercept",
        "theta_1500_a", "theta_1500_b",
        "theta_33t_S", "theta_33t_C", "theta_33t_OM", "theta_33t_S_OM",
        "theta_33t_C_OM", "theta_33t_S_C", "theta_33t_intercept",
        "theta_33_a", "theta_33_b", "theta_33_c",
    ]
    coefs = {}
    missing = []
    for name in needed:
        row = df.loc[df["nombre"] == name]
        if row.empty or pd.isna(row.iloc[0].get("valor")) or str(row.iloc[0].get("valor")).strip() == "":
            missing.append(name)
            continue
        coefs[name] = float(row.iloc[0]["valor"])
    if missing:
        raise ValueError(
            "Coeficientes Saxton-Rawls sin verificar: "
            + ", ".join(missing)
            + f". Rellenar {path.name} desde Saxton & Rawls (2006), Soil Sci. Soc. Am. J. 70: 1569-1578."
        )
    return coefs


def om_pct_from_soc(soc_gkg: float, cfg: Mapping[str, Any] | None = None) -> float:
    """SOC g/kg → materia orgánica % (factor van Bemmelen)."""
    factor = float(_cfg_get(cfg, "conversions", "humus_to_soc_factor", default=_DEFAULTS["humus_to_soc_factor"]))
    return float(soc_gkg) / 10.0 * factor


def nfk_from_texture_saxton_rawls(
    sand_pct: float,
    clay_pct: float,
    om_pct: float,
    csv_path: str | Path | None = None,
) -> float:
    """Agua disponible (% volumen) = θ33 − θ1500 (Saxton & Rawls 2006).

    S y C en fracción 0–1; OM en %. Devuelve % vol (0–100), no fracción.
    """
    c = _load_saxton_coefs(csv_path)
    S = float(sand_pct) / 100.0
    C = float(clay_pct) / 100.0
    OM = float(om_pct)
    t1500t = (
        c["theta_1500t_S"] * S + c["theta_1500t_C"] * C + c["theta_1500t_OM"] * OM
        + c["theta_1500t_S_OM"] * S * OM + c["theta_1500t_C_OM"] * C * OM
        + c["theta_1500t_S_C"] * S * C + c["theta_1500t_intercept"]
    )
    t1500 = t1500t + c["theta_1500_a"] * t1500t + c["theta_1500_b"]
    t33t = (
        c["theta_33t_S"] * S + c["theta_33t_C"] * C + c["theta_33t_OM"] * OM
        + c["theta_33t_S_OM"] * S * OM + c["theta_33t_C_OM"] * C * OM
        + c["theta_33t_S_C"] * S * C + c["theta_33t_intercept"]
    )
    t33 = t33t + c["theta_33_a"] * (t33t ** 2) + c["theta_33_b"] * t33t + c["theta_33_c"]
    awc_frac = max(0.0, float(t33) - float(t1500))
    return awc_frac * 100.0  # % volumen


def nfk_mm_from_awc(
    awc_pct_vol: float,
    root_depth_dm: float,
) -> tuple[float, float]:
    """mm = (% vol / 100) × profundidad_mm; también mm por dm.

    Returns:
        (nfk_mm, nfk_mm_per_dm)
    """
    depth_mm = float(root_depth_dm) * 100.0  # 1 dm = 100 mm
    nfk_mm = (float(awc_pct_vol) / 100.0) * depth_mm
    per_dm = (float(awc_pct_vol) / 100.0) * 100.0
    return nfk_mm, per_dm


def _layer_overlap_cm(top_cm: float, bot_cm: float, root_cm: float) -> float:
    """Espesor (cm) de [top, bot] que cae dentro de [0, root_cm]."""
    lo = max(float(top_cm), 0.0)
    hi = min(float(bot_cm), float(root_cm))
    return max(0.0, hi - lo)


def _awc_mm(sand_pct: float, clay_pct: float, soc_gkg: float, thickness_cm: float, cfg) -> tuple[float, float]:
    """Devuelve (mm en el espesor, AWC % vol)."""
    om = om_pct_from_soc(soc_gkg, cfg)
    awc = nfk_from_texture_saxton_rawls(sand_pct, clay_pct, om)
    mm = (awc / 100.0) * (float(thickness_cm) * 10.0)
    return mm, awc


def nfk_ptf_profile(
    layers: Sequence[Mapping[str, float]],
    *,
    texture_class: str = "franco",
    cfg: Mapping[str, Any] | None = None,
    n: int = 500,
    seed: int = 42,
    homogeneous: bool = False,
) -> dict[str, Any]:
    """nFK en zona de raíces: Saxton-Rawls por capa y suma de mm.

    Cada capa: top_cm, bot_cm, sand_pct, clay_pct, soc_gkg, sigma_sand, sigma_clay, sigma_soc.
    Si `homogeneous`, se usa la primera capa en todo el perfil (motivo al llamador).
    Recorta la última capa si las raíces acaban dentro. `nfk_mm_per_dm` es el de 0-30 cm.
    """
    import numpy as np

    if not layers:
        raise ValueError("nfk_ptf_profile: hace falta al menos una capa")
    root_map = _cfg_get(cfg, "nfk", "root_depth_dm", default={}) or {}
    root_dm = float(root_map.get(texture_class, root_map.get("franco", 10)))
    root_cm = root_dm * 10.0
    factor = float(_cfg_get(cfg, "nfk", "ptf_sigma_factor", default=1.5))
    extra = float(_cfg_get(cfg, "nfk", "homogeneous_sigma_inflate", default=1.5)) if homogeneous else 1.0

    def _sum_mm(draw_layers: Sequence[Mapping[str, float]]) -> tuple[float, float]:
        total = 0.0
        awc_030 = float("nan")
        if homogeneous:
            L0 = draw_layers[0]
            mm, awc = _awc_mm(L0["sand_pct"], L0["clay_pct"], L0["soc_gkg"], root_cm, cfg)
            return mm, awc
        for L in draw_layers:
            thick = _layer_overlap_cm(L["top_cm"], L["bot_cm"], root_cm)
            if thick <= 0:
                continue
            mm, awc = _awc_mm(L["sand_pct"], L["clay_pct"], L["soc_gkg"], thick, cfg)
            total += mm
            if float(L["top_cm"]) <= 0.0 and float(L["bot_cm"]) >= 30.0:
                awc_030 = awc
            elif float(L["top_cm"]) == 0.0 and not np.isfinite(awc_030):
                awc_030 = awc
        return total, awc_030

    nfk_mm, awc_030 = _sum_mm(layers)
    nfk_per_dm = float(awc_030) if np.isfinite(awc_030) else float("nan")

    rng = np.random.default_rng(seed)
    samples = []
    for _ in range(n):
        drawn = []
        for L in layers:
            sand = float(np.clip(rng.normal(L["sand_pct"], max(float(L.get("sigma_sand", 0.0)), 1e-6)), 0, 100))
            clay = float(np.clip(rng.normal(L["clay_pct"], max(float(L.get("sigma_clay", 0.0)), 1e-6)), 0, 100))
            clay = min(clay, 100.0 - sand)
            soc = float(np.clip(rng.normal(L["soc_gkg"], max(float(L.get("sigma_soc", 0.0)), 1e-6)), 0, None))
            drawn.append({**dict(L), "sand_pct": sand, "clay_pct": clay, "soc_gkg": soc})
        mm_i, _ = _sum_mm(drawn)
        samples.append(mm_i)
    sigma = float(np.std(samples, ddof=1)) * factor * extra
    return {
        "nfk_mm": float(nfk_mm),
        "nfk_mm_per_dm": float(nfk_per_dm) if np.isfinite(nfk_per_dm) else float(nfk_mm / max(root_dm, 1e-6)),
        "awc_pct_vol": float(awc_030) if np.isfinite(awc_030) else float("nan"),
        "sigma": max(sigma, 1e-3),
        "root_depth_dm": root_dm,
        "homogeneous": bool(homogeneous),
        "depth_raw": f"0-{root_cm:.0f}cm_por_capas",
    }


def nfk_ptf_row(
    sand_pct: float,
    clay_pct: float,
    soc_gkg: float,
    *,
    sigma_sand: float,
    sigma_clay: float,
    sigma_soc: float,
    texture_class: str = "franco",
    cfg: Mapping[str, Any] | None = None,
    n: int = 500,
    seed: int = 42,
) -> dict[str, Any]:
    """nFK homogéneo (una textura 0-30 cm extendida a la zona de raíces)."""
    layer = {
        "top_cm": 0.0, "bot_cm": 30.0,
        "sand_pct": float(sand_pct), "clay_pct": float(clay_pct), "soc_gkg": float(soc_gkg),
        "sigma_sand": float(sigma_sand), "sigma_clay": float(sigma_clay), "sigma_soc": float(sigma_soc),
    }
    return nfk_ptf_profile(
        [layer], texture_class=texture_class, cfg=cfg, n=n, seed=seed, homogeneous=True,
    )
