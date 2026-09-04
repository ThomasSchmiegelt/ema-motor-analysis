"""Vollwelle oder Hohlwelle -- entschieden am Feld, nicht am Gefuehl.

Die Frage
---------

``shaftBoreD`` ist die Wellenbohrung (0 = Vollwelle). Eine Bohrung spart Masse
und Traegheit und nimmt Kuehlmittel oder eine Steckverzahnung auf -- sie ist
also erst einmal erwuenscht. Sie ist nur dann falsch, wenn **durch die Welle
Fluss laeuft**: dann sitzt die Bohrung im magnetischen Pfad, das verbleibende
Eisen saettigt, und Moment geht verloren.

Genau das laesst sich messen, statt es zu entscheiden.

Wie gemessen wird
-----------------

Ein FDM-Lauf auf der Geometrie, dann das **radiale Profil von |B| im Rotor**:
je Radius der Mittelwert und das 95. Perzentil ueber den vollen Umfang. Von
innen nach aussen gesucht wird der Radius, ab dem der Fluss einsetzt --
``r_frei`` ist der groesste Radius, unter dem ueberall |B| < ``SCHWELLE_T``
bleibt. Alles darunter traegt keinen Fluss und darf heraus.

Daraus folgen drei Antworten:

* ``r_frei`` **groesser** als der halbe Wellendurchmesser: die Welle liegt
  ohnehin im flussfreien Kern -- Bohrung unbedenklich, und es steht sogar da,
  wie gross sie hoechstens sein darf.
* ``r_frei`` **kleiner** als der halbe Wellendurchmesser: durch die Welle
  laeuft Fluss. Dann ist die Vollwelle noetig, und eine Bohrung kostet Moment.
* Dazwischen: die Bohrung ist moeglich, aber kleiner als die Welle.

Was hier NICHT behauptet wird
-----------------------------

Der Befund ist **magnetisch**. Ob die Welle das Moment und die Fliehkraft
traegt, ist eine Festigkeitsfrage und steht in ``ema_rotorcheck`` bzw. der
Struktur-FEM -- eine magnetisch unbedenkliche Bohrung kann mechanisch
unzulaessig sein. Das sagt der Befund auch, statt es zu verschweigen.
"""

from __future__ import annotations

import math

import numpy as np

# Ab wann ein Bereich als "fuehrt Fluss" gilt. Konservativ: 0,05 T ist weit
# unter allem, was im Eisen zaehlt (Rotorjoch 1,2-1,8 T), und weit ueber dem
# Zahlenrauschen des Loesers. Wer hoeher ansetzt, erklaert Streufluss zu Fluss.
SCHWELLE_T = 0.05

# Sicherheitsabstand zwischen dem gemessenen flussfreien Kern und der Bohrung,
# die empfohlen wird. Der Loeser rastert, und die Grenze ist kein Sprung,
# sondern ein Anstieg -- ohne Abstand laege die Empfehlung genau auf der Kante.
ABSTAND_MM = 2.0

# Unter dieser Bohrung lohnt sich keine: sie spart weder nennenswert Masse noch
# nimmt sie eine Passung, eine Steckverzahnung oder eine Kuehlmittelzufuhr auf.
# Dann ist die Vollwelle die einfachere Antwort.
MIN_BOHRUNG_MM = 10.0


def _profil(B: np.ndarray, r_mm: np.ndarray, r_max: float,
            schritt: float = 0.5) -> list:
    """|B| ueber dem Radius: je Ring Mittelwert und 95. Perzentil."""
    aus = []
    r = schritt
    while r <= r_max:
        ring = (r_mm >= r - schritt) & (r_mm < r)
        werte = B[ring]
        werte = werte[np.isfinite(werte)]
        if werte.size:
            aus.append({"r_mm": round(r - schritt / 2, 2),
                        "b_mittel_T": round(float(werte.mean()), 4),
                        "b_p95_T": round(float(np.percentile(werte, 95)), 4),
                        "n": int(werte.size)})
        r += schritt
    return aus


def pruefen(geom: dict, *, N: int = 420, iq: float = 0.0, id_: float = 0.0,
            rotor_angle: float = 0.0, schwelle: float = SCHWELLE_T) -> dict:
    """Traegt die Welle Fluss? Ein FDM-Lauf, ein radiales Profil, ein Befund."""
    import ema_feldbild as FB

    d_welle = float(geom.get("shaftD", 0) or 0)
    d_bohrung = float(geom.get("shaftBoreD", 0) or 0)
    r_welle, r_bohrung = d_welle / 2.0, d_bohrung / 2.0
    r_rotor = float(geom.get("rotorOD", 0) or 0) / 2.0
    if r_welle <= 0 or r_rotor <= r_welle:
        return {"ok": False, "grund": "shaftD/rotorOD fehlen oder sind unstimmig"}

    f = FB.feld_rechnen(geom, N=N, rotor_angle=rotor_angle, iq=iq, id_=id_)
    B, r_mm = f["B"], f["r_mm"]
    profil = _profil(B, r_mm, r_rotor)

    # Der groesste Radius, unter dem NIRGENDS Fluss steht. Von innen nach
    # aussen, und beim ersten Ring ueber der Schwelle ist Schluss -- nicht das
    # Maximum ueber alle Ringe: ein flussfreier Ring WEITER AUSSEN sagt nichts
    # darueber, ob der Kern frei ist.
    r_frei = 0.0
    for ring in profil:
        if ring["b_p95_T"] >= schwelle:
            break
        r_frei = ring["r_mm"] + 0.25

    # Was in der Welle selbst steht -- die eigentliche Frage.
    in_welle = (r_mm <= r_welle) & np.isfinite(B)
    b_welle_p95 = float(np.percentile(B[in_welle], 95)) if in_welle.any() else 0.0
    b_welle_max = float(np.nanmax(B[in_welle])) if in_welle.any() else 0.0

    # Die Entscheidung haengt am flussfreien KERN, nicht am Mittelwert ueber die
    # ganze Welle. Der Unterschied ist keiner auf dem Papier: gemessen fuehrt
    # bei einer dicken Welle (120 mm) der aeussere Ring Fluss, waehrend der Kern
    # bis r = 54 mm frei bleibt. Ueber den Mittelwert entschieden hiesse das
    # "Vollwelle noetig" -- und im selben Befund stuende "Bohrung bis 104 mm
    # unbedenklich". Beides zugleich kann nicht stimmen.
    fuehrt = b_welle_p95 >= schwelle          # beschreibend, nicht entscheidend
    d_max = max(0.0, 2.0 * (r_frei - ABSTAND_MM))
    # Deckel bei ``shaftD - 2``: genau dort setzt ``ema_text2ema`` die Bohrung
    # wieder auf 0 (kein Restquerschnitt mehr). Ohne diesen Deckel empfaehle der
    # Befund bei einer 60-mm-Welle eine 60-mm-Bohrung -- also die Welle
    # wegzubohren -- und das Schema wuerfe sie stillschweigend weg. Wie viel
    # Wand die Welle WIRKLICH braucht, ist eine Festigkeitsfrage; das steht im
    # Vorbehalt und wird hier nicht behauptet.
    d_max = min(d_max, max(0.0, d_welle - 2.0))

    if d_max < MIN_BOHRUNG_MM:
        empfehlung = "vollwelle"
        satz = (f"VOLLWELLE. Der flussfreie Kern reicht nur bis "
                f"r = {r_frei:.1f} mm; abzueglich {ABSTAND_MM:.0f} mm Abstand "
                f"bliebe eine Bohrung von {d_max:.1f} mm — unter "
                f"{MIN_BOHRUNG_MM:.0f} mm spart sie weder nennenswert Masse "
                f"noch nimmt sie eine Passung auf. "
                + (f"Durch die Welle laeuft Fluss (|B| p95 "
                   f"{b_welle_p95:.3f} T ueber {schwelle} T); eine Bohrung "
                   f"saesse im magnetischen Pfad und kostete Moment."
                   if fuehrt else
                   f"Fluss fuehrt sie dabei kaum (|B| p95 "
                   f"{b_welle_p95:.3f} T) — es ist schlicht kein Platz."))
    else:
        empfehlung = "hohlwelle"
        satz = (f"HOHLWELLE moeglich: bis shaftBoreD = {d_max:.1f} mm. Der "
                f"flussfreie Kern reicht bis r = {r_frei:.1f} mm. "
                + (f"Der AEUSSERE Ring der Welle fuehrt zwar Fluss "
                   f"(|B| p95 ueber die ganze Welle {b_welle_p95:.3f} T), der "
                   f"Kern aber nicht — die Bohrung bleibt darunter."
                   if fuehrt else
                   f"Fluss laeuft dort ohnehin keiner "
                   f"(|B| p95 {b_welle_p95:.3f} T < {schwelle} T)."))

    soll = 0.0 if empfehlung == "vollwelle" else d_max
    return {
        "ok": True, "empfehlung": empfehlung, "satz": satz,
        "fuehrt_fluss": bool(fuehrt),
        "schwelle_T": schwelle,
        "welle": {"d_mm": d_welle, "b_p95_T": round(b_welle_p95, 4),
                  "b_max_T": round(b_welle_max, 4)},
        "bohrung": {"jetzt_mm": d_bohrung, "hoechstens_mm": round(d_max, 1)},
        "r_flussfrei_mm": round(r_frei, 2),
        "aendern": (None if abs(d_bohrung - soll) < 0.5
                    else {"shaftBoreD": round(soll, 1)}),
        "profil": profil,
        "vorbehalt": ("Der Befund ist MAGNETISCH. Ob die Welle Moment und "
                      "Fliehkraft traegt, sagt die Festigkeit ('struktur', "
                      "'sicherheit') — eine magnetisch unbedenkliche Bohrung "
                      "kann mechanisch unzulaessig sein."),
    }


def als_text(b: dict) -> str:
    if not b.get("ok"):
        return f"FEHLER: {b.get('grund', 'kein Befund')}"
    z = [f"WELLE: {b['empfehlung'].upper()}", "", "  " + b["satz"], "",
         f"  Welle-D            : {b['welle']['d_mm']:.1f} mm",
         f"  |B| in der Welle   : p95 {b['welle']['b_p95_T']:.3f} T, "
         f"max {b['welle']['b_max_T']:.3f} T  (Schwelle {b['schwelle_T']} T)",
         f"  flussfreier Kern   : bis r = {b['r_flussfrei_mm']:.1f} mm",
         f"  Bohrung jetzt      : {b['bohrung']['jetzt_mm']:.1f} mm",
         f"  Bohrung hoechstens : {b['bohrung']['hoechstens_mm']:.1f} mm"]
    if b.get("aendern"):
        k, v = next(iter(b["aendern"].items()))
        z += ["", f"  Aenderung: --set {k}={v}"]
    z += ["", "  " + b["vorbehalt"]]
    return "\n".join(z)
