"""Naechste gueltige Magnetanordnung -- die ueberschlaegige Rechnung vor dem Messen.

Warum es das gibt: ``rotor_layout_check`` sagt in 0,4 ms „Kollision: Tasche (Pol 3, …)", aber
nicht, WAS man aendern soll. Ein Agent dreht dann blind an ``magWidth``/``magDist``/... (gemessen:
46 Aufrufe in 90 Minuten, die letzten acht fast alle „Layout ungueltig"). Hier wird das Tor
selbst als Rechnung benutzt: die kleinste Aenderung (in Schema-Bruchteilen, 1 bis 3 Parameter)
suchen, mit der es besteht. Das ist ein reiner Geometriebefund -- ueber den Magnetschluss
(Streuanteil) sagt er NICHTS; der wird erst am gueltigen Layout gemessen.
"""
from __future__ import annotations

import itertools

import ema_rotorcheck
import ema_text2ema as _T2E

PARAMETER = ("magWidth", "magThick", "magDist", "magDepthRel", "magLayerGap", "magAngle", "magTangLen")
#: Raster je Parameter und Zahl gleichzeitig geaenderter Parameter -- 3 Parameter x 6 Werte x 35 Paare ~ 7.500 Pruefungen ~ 3 s
RASTER = {1: 25, 2: 12, 3: 7}
#: ``magWidth = 0`` hiesse „Slot fuellen" (nur Wandmodus) -- keine Heilung dorthin
UNTERGRENZE = {"magWidth": 4.0}


def _spec(key: str):
    s = _T2E.SCHEMA.get(key)
    return s if s and s.get("kind") == "num" else None


def _gueltig(geom: dict) -> bool:
    try:
        return bool(ema_rotorcheck.rotor_layout_check(geom).get("ok"))
    except Exception:                                             # noqa: BLE001
        return False


def _runde(key: str, wert: float):
    s = _spec(key)
    wert = max(UNTERGRENZE.get(key, s["lo"]), min(s["hi"], float(wert)))
    return int(round(wert)) if s.get("int") else round(wert, 2)


def heile(geom: dict, max_parameter: int = 3) -> dict:
    """``{"gueltig": bool, "aenderung": {key: (alt, neu)}, "set": ["k=v", ...], "geom": dict}``.

    Ist das Layout schon gueltig, bleibt ``aenderung`` leer. Gefunden wird die Loesung mit der
    KLEINSTEN Zahl geaenderter Parameter, darunter die mit der kleinsten Aenderung (Summe der
    Abstaende in Bruchteilen des Schema-Bereichs)."""
    if _gueltig(geom):
        return {"gueltig": True, "aenderung": {}, "set": [], "geom": dict(geom), "hinweis": "Layout war schon gueltig."}
    keys = [k for k in PARAMETER if _spec(k) and k in geom]
    for n in range(1, max_parameter + 1):
        best = None
        for kombi in itertools.combinations(keys, n):
            achsen = []
            for k in kombi:
                s = _spec(k)
                lo, hi = UNTERGRENZE.get(k, s["lo"]), s["hi"]
                m = RASTER[n]
                achsen.append([lo + (hi - lo) * i / (m - 1) for i in range(m)])
            for werte in itertools.product(*achsen):
                dist = sum(abs(w - float(geom[k])) / (_spec(k)["hi"] - _spec(k)["lo"] or 1.0)
                           for k, w in zip(kombi, werte))
                if best is not None and dist >= best[0]:
                    continue
                g = dict(geom)
                for k, w in zip(kombi, werte):
                    g[k] = _runde(k, w)
                if _gueltig(g):
                    best = (dist, kombi, g)
        if best:
            dist, kombi, g = best
            aend = {k: (geom[k], g[k]) for k in kombi if g[k] != geom[k]}
            return {"gueltig": False, "aenderung": aend, "set": [f"{k}={v[1]}" for k, v in aend.items()],
                    "geom": g, "abstand": round(dist, 3),
                    "hinweis": f"Kleinste gefundene Aenderung ({n} Parameter). Nur die Geometrie ist geprueft -- "
                               "Magnetschluss, Sicherheit und Leistung sind damit NICHT beurteilt."}
    return {"gueltig": False, "aenderung": {}, "set": [], "geom": dict(geom),
            "hinweis": "Mit hoechstens drei der Magnetparameter ist kein gueltiges Layout erreichbar -- "
                       "Polzahl, Rotordurchmesser oder Bauform (magShape) muessen sich aendern."}
