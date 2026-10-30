"""Systematische Magnetsuche -- statt von Hand zu probieren.

Gemessen am 30.10.2026: ein Agent rief ``magnetschluss`` 46-mal mit je anderen ``--set``-Werten und kam in 90
Minuten nicht ueber Phase 1 hinaus. Hier macht das Werkzeug dieselbe Arbeit planvoll:

1. **Ziehen** aus Bereichen, die der Agent nennt (Vorgabe: die Schemagrenzen der Magnetparameter), gleichverteilt.
2. **Filtern** mit dem Layouttor -- 0,4 ms je Kandidat, hier fallen die meisten heraus (kein Messlauf verschwendet).
3. **Streuen**: aus den gueltigen die ``messen`` am weitesten auseinanderliegenden (Farthest-Point im normierten
   Parameterraum), damit jede Messung etwas Neues zeigt statt Nachbarn desselben Fleckens.
4. **Messen** parallel (``ema_magnetschluss.messen_stabil``, ca. 45 s je Lauf allein, parallel mit den Kernen).
5. **Ordnen**: Stufe zuerst (ok < auffaellig < kurzschluss), darunter das groesste analytische ``B_gap``.

Eine ueberschlaegige Vorhersage der Streuzahl gibt es mit Absicht nicht: an 40 gemessenen Geometrien erreichte die
beste Naeherungsformel r = 0,5 und traf die Stufe in 40-60 % der Faelle. Gemessen wird deshalb immer; die
Naeherung steht nirgends als Urteil. Das Ergebnis sagt nur etwas ueber Magnetschluss und Layout -- Sicherheit,
Leistung und Kosten sind danach mit ``sicherheit``/``entscheide`` zu pruefen.
"""
from __future__ import annotations

import math
import random
import time
from multiprocessing import Pool

import ema_magnetheilung as H
import ema_text2ema as _T2E

RANG = {"ok": 0, "unsicher": 1, "auffaellig": 1, "kurzschluss": 2}
SEK_JE_MESSUNG = 45          # allein gemessen; parallel eher 130-190 s je Lauf bei acht Prozessen
UNGEPRUEFT = ("spoke", "bar")


def standard_bereiche(geom: dict) -> dict:
    wand = max(5.0, (float(geom["rotorOD"]) - float(geom["shaftD"])) / 2.0)
    b = {"magWidth": (max(H.UNTERGRENZE.get("magWidth", 4.0), 0.3 * wand), min(90.0, 1.3 * wand)),
         "magThick": (2.0, 12.0), "magDist": (0.0, 0.35 * wand), "magDepthRel": (0.45, 0.9)}
    shape = str(geom.get("magShape", "v"))
    if shape in ("v", "vasym", "vv", "u", "delta", "pmasynrm"):
        b["magAngle"] = (60.0, 160.0)
    if shape in ("vv", "pmasynrm"):
        b["magLayerGap"] = (1.0, 0.5 * wand)
    return {k: (max(_T2E.SCHEMA[k]["lo"], lo), min(_T2E.SCHEMA[k]["hi"], hi)) for k, (lo, hi) in b.items()}


def _messe(arg):
    g, n = arg
    import ema_magnetschluss as MS
    t = time.time()
    try:
        r = MS.messen_stabil(g, N=n)
    except Exception as e:                                       # noqa: BLE001
        r = {"ok": False, "grund": f"{type(e).__name__}: {str(e)[:80]}"}
    r["s"] = round(time.time() - t, 1)
    return r


def _fern(punkte: list, k: int, rng: random.Random) -> list:
    """Indizes von k Punkten, jeder am weitesten von den bisherigen (Farthest-Point)."""
    if not punkte:
        return []
    k = min(k, len(punkte))
    gew = [rng.randrange(len(punkte))]
    d = [math.dist(p, punkte[gew[0]]) for p in punkte]
    while len(gew) < k:
        i = max(range(len(punkte)), key=lambda j: d[j])
        gew.append(i)
        d = [min(d[j], math.dist(punkte[j], punkte[i])) for j in range(len(punkte))]
    return gew


def suche(geom: dict, bereiche: dict | None = None, kandidaten: int = 400, messen: int = 8,
          wellen: int = 1, seed: int = 1, prozesse: int = 8, n: int = 300, nur_planen: bool = False,
          log=print) -> dict:
    rng = random.Random(seed)
    ber = dict(standard_bereiche(geom))
    ber.update(bereiche or {})
    ber = {k: v for k, v in ber.items() if k in geom or k in _T2E.SCHEMA}
    keys = list(ber)
    gueltig, abgelehnt = [], 0
    for _ in range(int(kandidaten)):
        g = dict(geom)
        for k in keys:
            lo, hi = ber[k]
            g[k] = H._runde(k, rng.uniform(lo, hi))
        if H._gueltig(g):
            gueltig.append(g)
        else:
            abgelehnt += 1
    plan = {"bereiche": {k: [round(a, 2), round(b, 2)] for k, (a, b) in ber.items()},
            "gezogen": int(kandidaten), "gueltig": len(gueltig), "abgelehnt_layout": abgelehnt,
            "messungen_geplant": min(len(gueltig), int(messen) * int(wellen)),
            "geschaetzt_min": round(math.ceil(min(len(gueltig), messen) / max(1, prozesse)) * wellen
                                    * SEK_JE_MESSUNG * 3.5 / 60.0, 1)}
    if str(geom.get("magShape")) in UNGEPRUEFT:
        plan["warnung"] = (f"magShape={geom.get('magShape')}: die Streuzahl ist fuer diese Bauform NICHT geprueft "
                           "(ema_magnetschluss); ein Urteil ist ein Hinweis, kein Beleg.")
    if nur_planen or not gueltig:
        return {"ok": bool(gueltig), "plan": plan, "ergebnisse": [], "beste": None}

    norm = lambda g: [(float(g[k]) - ber[k][0]) / ((ber[k][1] - ber[k][0]) or 1.0) for k in keys]
    rest = list(gueltig)
    ergebnisse = []
    import ema_analysis
    for w in range(int(wellen)):
        if not rest:
            break
        idx = _fern([norm(g) for g in rest], int(messen), rng)
        wahl = [rest[i] for i in idx]
        rest = [g for i, g in enumerate(rest) if i not in set(idx)]
        log(f"Welle {w + 1}/{wellen}: {len(wahl)} Messungen auf {min(prozesse, len(wahl))} Prozessen …")
        with Pool(min(prozesse, len(wahl))) as pool:
            res = pool.map(_messe, [(g, n) for g in wahl])
        for g, r in zip(wahl, res):
            try:
                bg = round(float(ema_analysis._analytical_Bgap(g)), 3)
            except Exception:                                    # noqa: BLE001
                bg = None
            ergebnisse.append({"set": {k: g[k] for k in keys}, "geom": g, "ok": bool(r.get("ok")),
                               "streu": r.get("streuanteil"), "stufe": r.get("stufe"), "grund": r.get("grund"),
                               "B_gap_T": bg, "s": r.get("s")})
        if any(e["stufe"] == "ok" for e in ergebnisse):
            break
    messbar = [e for e in ergebnisse if e["ok"]]
    messbar.sort(key=lambda e: (RANG.get(e["stufe"], 3), -(e["B_gap_T"] or 0.0)))
    return {"ok": True, "plan": plan, "ergebnisse": messbar,
            "nicht_messbar": [e for e in ergebnisse if not e["ok"]],
            "beste": messbar[0] if messbar else None}
