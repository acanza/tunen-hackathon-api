"""Approximate KA5 (Bodenkundliche Kartieranleitung, 5th ed.) lookup values for available water.

APPROXIMATE: typed in from memory of the KA5 tables (nFK by Bodenart at medium effective bulk density
Ld3, humus surcharges, effective rooting depth for arable land). Magnitudes are right for this sandy
landscape, single values may be off by 1–3 vol %. Check against the printed table before production;
the layer that uses them carries the driver `lookup_table_approximate`.
"""
from __future__ import annotations

# nFK in vol % at Ld3, by KA5 Bodenart (fine-earth texture class)
NFK_LD3 = {
    # sands
    "gS": 5, "mS": 8, "fS": 12, "mSgs": 7, "mSfs": 9, "fSms": 11, "Ss": 9,
    "Sl2": 15, "Sl3": 17, "Sl4": 18, "Slu": 19, "St2": 14, "St3": 15,
    "Su2": 15, "Su3": 18, "Su4": 20,
    # loams
    "Ls2": 16, "Ls3": 15, "Ls4": 14, "Lt2": 15, "Lt3": 14, "Lts": 13, "Lu": 17, "Uls": 21,
    # silts
    "Us": 22, "Uu": 25, "Ut2": 24, "Ut3": 23, "Ut4": 21,
    # clays
    "Tl": 13, "Tu2": 14, "Tu3": 16, "Tu4": 18, "Tt": 12, "Ts2": 12, "Ts3": 12, "Ts4": 13,
}
NFK_PEAT = 45  # moderately decomposed fen peat (Hn), vol %

# effective bulk density class → correction to the Ld3 value, vol %
LD_CORRECTION = {"Ld1": 2, "Ld2": 1, "Ld3": 0, "Ld4": -1, "Ld5": -2}

# humus class → surcharge, vol % (KA5 adds water for organic matter in mineral horizons)
HUMUS_SURCHARGE = {"h0": 0, "h1": 0, "h2": 1, "h3": 2, "h4": 3, "h5": 5, "h6": 8}

# effective rooting depth (dm) for arable land by the texture group of the topsoil
WE_DM = {"S": 6, "Sl": 7, "Su": 7, "St": 6, "L": 9, "U": 11, "T": 9, "H": 4}


def nfk_vol(bodenart: str | None, ld: str | None, humus: str | None, peat: bool) -> float | None:
    if peat:
        return NFK_PEAT
    if not bodenart or bodenart not in NFK_LD3:
        return None
    return NFK_LD3[bodenart] + LD_CORRECTION.get(ld or "Ld3", 0) + HUMUS_SURCHARGE.get(humus or "h0", 0)


def texture_group(bodenart: str | None, peat: bool) -> str:
    if peat:
        return "H"
    if not bodenart:
        return "S"
    for g in ("Sl", "Su", "St"):
        if bodenart.startswith(g):
            return g
    return bodenart[0].upper() if bodenart[0].upper() in "SLUT" else "S"
