"""Montagekosten -- der Posten, der in der Materialrechnung fehlte.

``ema_screen.massen_und_kosten`` rechnete Werkstoff mal Masse. Damit ist eine Maschine mit
72 einzelnen Magnetstuecken genauso billig wie eine mit 12, und eine gestaffelte Schraegung
(zwoelf gedrehte Segmente) kostet nichts -- obwohl dort die Arbeit steckt. Eine
Preisvariante, die Montage nicht kennt, belohnt genau die Auslegungen, die sich nicht
bauen lassen.

Gerechnet wird je **Handgriff**, nicht je Kilogramm: Magnetstueck setzen, Leiter formen
und einsetzen, Schweissstelle, Wicklung impraegnieren, Blechpaket paketieren, Welle
fuegen, Wuchten. Die Betraege sind **Platzhalter zum Rangieren** (wie
``ema_screen.PREISE_EUR_KG``), keine Kalkulation: wichtig ist die Ordnung -- ein
Magnetstueck kostet Sekunden, eine Schweissstelle etwas mehr, ein Spezialwerkzeug fuer
eine Schraegung ein Vielfaches. Alles liegt in ``STUECK_EUR`` / ``FIX_EUR`` und ist dort
zu aendern, an keiner anderen Stelle.

Je Maschinenart kommt nur vor, was es dort gibt: Magnete nur bei der PSM, der Kaefig bei
der ASM (Druckguss), die Erregerspulen bei der EESM, Kommutator und Ankerwicklung bei
der GSM.
"""
from __future__ import annotations

import math

import ema_maschinenart
from ema_topology import magnet_legs

#: EUR je Stueck / Handgriff -- Platzhalter.
STUECK_EUR = {
    "magnet_einsetzen":   0.30,   # Magnetstueck in die Tasche setzen und kleben
    "magnet_aufkleben":   0.50,   # Oberflaechenmagnet kleben und ausrichten
    "magnet_schraege":    0.20,   # Zuschlag je Stueck bei gestaffelten Segmenten (Versatz ausrichten)
    "leiter_hairpin":     0.10,   # Stab formen und in die Nut einsetzen
    "schweissung":        0.15,   # eine Schweissstelle (zwei Leiterenden)
    "nut_rundraht":       0.40,   # eine Nut wickeln und einziehen
    "nut_anker":          0.50,   # Ankernut der GSM
    "pol_spule":          1.50,   # eine Erregerspule samt Polschuh (EESM)
    "wuchtbolzen":        0.15,
}
#: EUR je Maschine.
FIX_EUR = {
    "blechpaket_stator":   6.0,
    "blechpaket_rotor":    4.0,
    "impraegnieren":       3.0,
    "bandage":             3.0,   # Oberflaechenmagnete brauchen sie
    "schraege_werkzeug":   5.0,   # kontinuierliche Schraegung: Verdrehen des Pakets
    "kaefig_druckguss":    9.0,
    "kommutator":         18.0,
    "wuchten":             4.0,
    "lager_gehaeuse":      6.0,
}
WELLE_EUR = {"press": 2.0, "spline": 5.0, "polygon": 9.0}


def _geom(payload: dict) -> dict:
    return payload.get("geom") or {}


def montage(payload: dict) -> dict:
    """Montagekosten [EUR] mit allen Positionen. ``gesamt_EUR`` ist die Summe."""
    g = _geom(payload)
    art = ema_maschinenart.art_code(payload)
    slots = int(g.get("slots", 0) or 0)
    p = max(1, int(g.get("p", 3) or 3))
    pos: dict[str, float] = {}

    pos["blechpakete"] = FIX_EUR["blechpaket_stator"] + FIX_EUR["blechpaket_rotor"]
    pos["lager_gehaeuse"] = FIX_EUR["lager_gehaeuse"]
    pos["wuchten"] = FIX_EUR["wuchten"] + STUECK_EUR["wuchtbolzen"] * (
        2 * p if g.get("genBalanceBolts") else 0)
    pos["welle_fuegen"] = WELLE_EUR.get(str(g.get("shaftConnection") or "press"), WELLE_EUR["press"])

    # Statorwicklung -- alle Arten ausser der GSM (deren Stator tragen die Feldpole)
    if art != "gsm":
        if str(g.get("windingType") or "hairpin") == "rundraht":
            pos["wicklung"] = slots * STUECK_EUR["nut_rundraht"] + FIX_EUR["impraegnieren"]
        else:
            n_leiter = slots * int(g.get("conductorsPerSlot", 4) or 4)
            pos["wicklung"] = (n_leiter * STUECK_EUR["leiter_hairpin"]
                               + (n_leiter / 2.0) * STUECK_EUR["schweissung"]
                               + FIX_EUR["impraegnieren"])

    segmente = max(1, int(g.get("skew_segments", 1) or 1))
    schraeg = float(g.get("skew_deg", 0) or 0) > 0

    if ema_maschinenart.hole(art).hat_magnete:
        legs, _ = magnet_legs(g)
        stueck = (2 * p * len(legs) * max(1, int(g.get("nAx", 1) or 1))
                  * max(1, int(g.get("nCirc", 1) or 1)) * segmente)
        oberflaeche = all(getattr(l, "placement", "interior") == "surface" for l in legs) if legs else False
        je = STUECK_EUR["magnet_aufkleben" if oberflaeche else "magnet_einsetzen"]
        pos["magnete_setzen"] = stueck * je
        if oberflaeche:
            pos["bandage"] = FIX_EUR["bandage"]
        if segmente > 1:
            pos["schraege_segmente"] = stueck * STUECK_EUR["magnet_schraege"]
    if schraeg and segmente <= 1:
        pos["schraege_werkzeug"] = FIX_EUR["schraege_werkzeug"]

    if art == "asm":
        pos["kaefig"] = FIX_EUR["kaefig_druckguss"]
    elif art == "eesm":
        pos["erregerspulen"] = 2 * p * STUECK_EUR["pol_spule"]
    elif art == "gsm":
        pos["kommutator"] = FIX_EUR["kommutator"]
        pos["anker"] = slots * STUECK_EUR["nut_anker"] + FIX_EUR["impraegnieren"]

    pos = {k: round(v, 1) for k, v in pos.items()}
    return {"gesamt_EUR": round(sum(pos.values()), 0), "positionen": pos,
            "hinweis": "Platzhalter je Handgriff, zum Rangieren -- kein Angebot."}
