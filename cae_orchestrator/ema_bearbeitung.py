"""Bearbeitungsaufwand -- der Kostenposten zwischen Werkstoff und Montage.

``ema_screen`` rechnete Werkstoff mal Masse, ``ema_montage`` die Handgriffe beim Zusammenbau.
Dazwischen liegt, was dem Teil angetan wird, bevor es montiert werden kann: das Blech wird
geschnitten oder gestanzt, die Welle gedreht und gebohrt, ein duenner Sintermagnet
zugeschliffen. Ohne diesen Posten ist ein Rotor mit zwanzig Taschen und Flussbarrieren so
billig wie einer ohne, und eine Hohlwelle ist nur leichter -- nie teurer.

Gerechnet wird nach dem, was die Bearbeitung WIRKLICH treibt:

* **Schnittlaenge je Blech** (Nuten des Stators; Magnettaschen, Barrieren, Wuchtbohrungen,
  Wellenbohrung des Rotors) mal Blechzahl: mehr Kontur, mehr Schnitt und ein aufwaendigeres
  Stanzwerkzeug (je Kontur ein Zuschlag).
* **Welle**: Drehen als Festbetrag, eine Bohrung nach abgetragenem Volumen.
* **Magnete**: Zuschnitt je Stueck, duenner als ``DUENN_MM`` kostet mehr (Ausschuss, Schleifen).

Wie ``ema_montage`` sind die Betraege **Platzhalter zum Rangieren**; wichtig ist die
Ordnung. Alles liegt in den Konstanten unten.
"""
from __future__ import annotations

import math

import ema_maschinenart
from ema_topology import balance_bolt_holes, flux_barrier_slots, magnet_legs

SCHNITT_EUR_M = 0.003       # je Meter Schnittlaenge und Blech-Stapel normiert (Platzhalter)
KONTUR_EUR = 0.35           # Werkzeugzuschlag je Kontur im Schnittbild (Tasche, Nut, Barriere, Bohrung)
BLECH_MM = 0.35             # Blechdicke fuer die Blechzahl
WELLE_DREHEN_EUR = 4.0
BOHREN_FIX_EUR = 6.0
BOHREN_EUR_CM3 = 0.012
MAGNET_ZUSCHNITT_EUR = 0.20
DUENN_MM = 4.0              # darunter Zuschlag
DUENN_FAKTOR = 1.0          # +100 % bei Dicke -> 0


def bearbeitung(payload: dict) -> dict:
    """Bearbeitungskosten [EUR] mit allen Positionen. ``gesamt_EUR`` ist die Summe."""
    g = payload.get("geom") or {}
    L = float(g.get("axialLen") or payload.get("axial_len") or 80.0)
    p = max(1, int(g.get("p", 3) or 3))
    slots = int(g.get("slots", 0) or 0)
    art = ema_maschinenart.art_code(payload)
    bleche = L / BLECH_MM
    pos: dict[str, float] = {}

    # Stator: Nutkontur
    t_nut = float(g.get("slotDepth", 0) or 0)
    b_nut = float(g.get("slotWidth", 0) or 0) or max(3.0, t_nut / 3.0)
    l_stator = slots * (2.0 * t_nut + b_nut) * 1e-3
    pos["stator_schnitt"] = l_stator * bleche * SCHNITT_EUR_M + slots * 0.0 + KONTUR_EUR * min(slots, 12)

    # Rotor: Taschen, Barrieren, Wuchtbohrungen, Wellenbohrung
    konturen, laenge = 1, math.pi * float(g.get("shaftD", 0) or 0) * 1e-3
    hat = ema_maschinenart.hole(art).hat_magnete
    legs = []
    if hat:
        legs, _ = magnet_legs(g)
        for l in legs:
            laenge += 2.0 * (l.length + l.thickness) * 2 * p * 1e-3
        konturen += len(legs)
    else:
        n_rot = int(g.get("rotorSlots", 0) or max(0, int(slots * 0.8)))
        laenge += n_rot * 2.0 * (t_nut * 0.6 + 4.0) * 1e-3
        konturen += min(n_rot, 12)
    try:
        for sl in flux_barrier_slots(g):
            laenge += 2.0 * (sl["depth"] + sl["width"]) * 1e-3
            konturen += 1
        for h in balance_bolt_holes(g):
            laenge += 2.0 * math.pi * h["r"] * 1e-3
            konturen += 1
    except Exception:                                             # noqa: BLE001
        pass
    pos["rotor_schnitt"] = laenge * bleche * SCHNITT_EUR_M + KONTUR_EUR * konturen

    # Welle
    d_wel = float(g.get("shaftD", 0) or 0)
    d_bohr = min(float(g.get("shaftBoreD", 0) or 0), max(0.0, d_wel - 2.0))
    pos["welle_drehen"] = WELLE_DREHEN_EUR
    if d_bohr > 0:
        v_cm3 = math.pi / 4 * d_bohr ** 2 * (L + 80.0) * 1e-3
        pos["welle_bohren"] = BOHREN_FIX_EUR + BOHREN_EUR_CM3 * v_cm3

    # Magnete
    if legs:
        segmente = max(1, int(g.get("skew_segments", 1) or 1))
        stueck = (2 * p * len(legs) * max(1, int(g.get("nAx", 1) or 1))
                  * max(1, int(g.get("nCirc", 1) or 1)) * segmente)
        dick = min((l.thickness for l in legs), default=DUENN_MM)
        zu = 1.0 + DUENN_FAKTOR * max(0.0, (DUENN_MM - dick) / DUENN_MM)
        pos["magnet_zuschnitt"] = stueck * MAGNET_ZUSCHNITT_EUR * zu

    pos = {k: round(v, 1) for k, v in pos.items()}
    return {"gesamt_EUR": round(sum(pos.values()), 0), "positionen": pos,
            "hinweis": "Platzhalter je Schnitt/Bohrung/Zuschnitt, zum Rangieren -- kein Angebot."}
