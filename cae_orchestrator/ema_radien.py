"""Radiale Ordnung: Innenlaeufer und Aussenlaeufer aus EINER Funktion.

Warum das eine eigene Funktion ist und keine Fallunterscheidung
---------------------------------------------------------------

Die Annahme „der Laeufer liegt innen" steht im Werkzeug nicht als Schalter,
sondern als **Rechenrichtung** an rund sechzig Stellen: ``rotorOD < statorID``,
Luftspalt ``= (statorID - rotorOD)/2``, Fliehkraft von der Bohrung nach aussen,
Magnete, die ein Steg nach innen haelt, Bilder, die von innen nach aussen
gezeichnet werden. Jede dieser Stellen einzeln zu verzweigen hiesse, sechzig
Gelegenheiten fuer ein vergessenes Vorzeichen zu schaffen -- und ein vergessenes
Vorzeichen faellt hier nicht auf: die Zahl kommt heraus, sie ist nur falsch.

Deshalb gibt es **eine** Funktion, die die Ordnung ausspricht, und alle anderen
fragen sie. Sie liefert nicht „ist es ein Aussenlaeufer", sondern die Radien
selbst -- Laeufer innen/aussen, Stator innen/aussen, die beiden Spaltflaechen --
und dazu die Richtung ``nach_stator``. Wer damit rechnet, rechnet fuer beide
Bauformen richtig, ohne sie zu unterscheiden.

Wie die vorhandenen Schluessel gelesen werden
----------------------------------------------

Die vier gewachsenen Schluessel behalten ihre **woertliche** Bedeutung --
``statorID``/``statorOD`` sind Innen- und Aussendurchmesser des Stators,
``rotorOD`` der Aussendurchmesser des Laeufers, ``shaftD`` der der Welle. Neu ist
allein ``rotorID`` (Innendurchmesser des Laeufers), den der Innenlaeufer nicht
braucht (dort ist er die Welle).

    Innenlaeufer:  shaftD < rotorOD < statorID < statorOD
    Aussenlaeufer: shaftD < statorID < statorOD < rotorID < rotorOD

Der Luftspalt liegt in beiden Faellen zwischen den beiden **einander
zugewandten** Flaechen; welche das sind, sagt die Bauform. Damit ist keine Zahl
umgedeutet, und ein bestehender Payload bleibt Wort fuer Wort gueltig.

Was die Bauform WIRKLICH aendert
---------------------------------

Nicht nur die Reihenfolge der Radien:

* **Die Fliehkraft dreht sich um.** Beim Innenlaeufer sitzt die groesste
  Zugspannung an der Bohrung, und die Magnete haengen an einem Steg, der sie
  nach innen haelt. Beim Aussenlaeufer traegt der Ring sich selbst, und die
  Magnete werden **gegen** den Ring gedrueckt -- der Steg traegt die Magnete
  gar nicht mehr. Das ist keine Vorzeichenaenderung, sondern eine andere
  Aussage, und ``magnethaltung`` gibt sie getrennt heraus.
* **Der Laeuferring ist die aeussere Flaeche.** Umfangsgeschwindigkeit,
  Luftreibung und die Kuehlung liegen anders.

Was diese Fassung NICHT traegt -- ausgesprochen
------------------------------------------------

``pruefe_bauform(stufe)`` weist ab, was noch nicht gebaut ist, statt eine
Innenlaeufer-Rechnung unter fremdem Namen laufen zu lassen -- dasselbe Tor wie
in ``ema_maschinenart``, aus demselben Grund.
"""

from __future__ import annotations

import math

BAUFORMEN = ("innen", "aussen")
LABEL = {
    "innen":  "Innenlaeufer (Laeufer innen, Stator aussen)",
    "aussen": "Aussenlaeufer (Laeufer aussen, Stator innen)",
}
VORGABE = "innen"

# Welche Stufen den Aussenlaeufer heute wirklich tragen. Wie in
# ``ema_maschinenart``: die zweite Spalte ist der Sinn der Tabelle.
STUFEN_AUSSEN = ("analytisch",)


class BauformNichtUnterstuetzt(ValueError):
    """Diese Stufe traegt diese Bauform (noch) nicht."""


def bauform(quelle) -> str:
    """Bauform aus Payload **oder** ``geom``. Unbekannt -> Innenlaeufer."""
    d = quelle if isinstance(quelle, dict) else {}
    g = d.get("geom") if isinstance(d.get("geom"), dict) else d
    b = str(g.get("rotorPosition", "") or d.get("rotorPosition", "") or "").strip().lower()
    if b in ("aussen", "außen", "outer", "aussenlaeufer", "aussenläufer"):
        return "aussen"
    return VORGABE


def traegt(stufe: str) -> bool:
    return stufe in STUFEN_AUSSEN


def pruefe_bauform(quelle, stufe: str) -> str:
    """Traegt diese Stufe die Bauform? Sonst ein klarer Fehler, keine Ersatzrechnung."""
    b = bauform(quelle)
    if b == "innen" or stufe in STUFEN_AUSSEN:
        return b
    raise BauformNichtUnterstuetzt(
        f"{LABEL[b]}: die Stufe '{stufe}' traegt ihn noch nicht. Getragen: "
        f"{', '.join(STUFEN_AUSSEN)}. Ein Innenlaeufer-Ergebnis unter diesem "
        f"Namen waere schlimmer als keines.")


def radien(geom: dict) -> dict:
    """Alle Radien in **Millimetern**, in der Ordnung der jeweiligen Bauform.

    Die Rueckgabe ist bewusst nicht „rotorOD/statorID", sondern nach ROLLE
    benannt: ``r_rotor_gap`` ist die Laeuferflaeche AM Luftspalt, gleich welche
    Bauform. Wer damit rechnet, braucht die Bauform nicht mehr zu kennen.

    ``nach_stator`` ist +1, wenn der Stator radial AUSSERHALB des Laeufers
    liegt, sonst -1. Das ist die Richtung, in die das Luftspaltfeld vom Laeufer
    aus zeigt.
    """
    b = bauform(geom)
    # Nur die Masse verlangen, die die jeweilige Bauform WIRKLICH braucht. Der
    # Steckbrief zeigt Maschinen, deren Payload unvollstaendig ist; wer dort
    # ``shaftD`` einfordert, verliert die Luftspaltzeile ganz -- und ein
    # fehlender Luftspalt liest sich wie ein nicht gerechneter.
    def _d(name, vorgabe=None):
        v = geom.get(name)
        if v in (None, "", 0) and vorgabe is not None:
            return float(vorgabe)
        if v in (None, ""):
            raise KeyError(f"'{name}' fehlt -- fuer {LABEL[b]} wird es gebraucht")
        return float(v)

    r_wel = _d("shaftD", 0.0) / 2.0
    r_st_i = _d("statorID", 0.0 if b == "aussen" else None) / 2.0
    r_st_a = _d("statorOD", 0.0 if b == "innen" else None) / 2.0
    r_rot_a = _d("rotorOD") / 2.0

    if b == "innen":
        r_rot_i = float(geom.get("rotorID", 0) or geom.get("shaftD", 0) or 0.0) / 2.0
        spalt = r_st_i - r_rot_a
        r_rotor_gap, r_stator_gap = r_rot_a, r_st_i
        nach_stator = 1.0
    else:
        # Innendurchmesser des Laeuferrings: gesetzt, sonst aus Stator und Spalt.
        # ``airGap`` ist der uebliche Schluessel; ohne ihn wird der Ring direkt
        # an den Stator gesetzt und der Fehler unten faengt es ab.
        vorgabe = float(geom.get("rotorID", 0) or 0.0) / 2.0
        if vorgabe <= 0.0:
            vorgabe = r_st_a + float(geom.get("airGap", 0.0) or 0.0)
        r_rot_i = vorgabe
        spalt = r_rot_i - r_st_a
        r_rotor_gap, r_stator_gap = r_rot_i, r_st_a
        nach_stator = -1.0

    if spalt <= 0.0:
        raise ValueError(
            f"Luftspalt nicht positiv ({spalt:.3f} mm) bei {LABEL[b]}. "
            + ("Erwartet rotorOD < statorID." if b == "innen"
               else "Erwartet statorOD < rotorID (rotorID setzen oder airGap angeben)."))
    # Mindestwandstaerke des Laeuferrings. Nicht ``> 0``: ein Ring von 0,05 mm
    # ist geometrisch gueltig und physikalisch keiner -- er kann weder den
    # Jochfluss fuehren noch die Fliehkraft tragen, und die Lame-Loesung gaebe
    # dafuer trotzdem eine Zahl aus. Die Schranke ist eine RECHENgrenze und
    # keine Auslegungsregel, darum steht sie so niedrig wie moeglich: 1 mm oder
    # der Luftspalt, je nachdem was groesser ist.
    wand_min = max(1.0, spalt)
    if b == "aussen" and (r_rot_a - r_rot_i) < wand_min:
        raise ValueError(
            f"Laeuferring hat zu wenig Wandstaerke: {r_rot_a - r_rot_i:.2f} mm "
            f"(rotorOD {2 * r_rot_a:.1f}, rotorID {2 * r_rot_i:.1f}), "
            f"mindestens {wand_min:.2f} mm sind noetig, damit Jochfluss und "
            f"Fliehkraft ueberhaupt eine Traegerflaeche haben")

    return {
        "bauform": b, "label": LABEL[b],
        "r_welle_mm": r_wel,
        "r_rotor_innen_mm": r_rot_i, "r_rotor_aussen_mm": r_rot_a,
        "r_stator_innen_mm": r_st_i, "r_stator_aussen_mm": r_st_a,
        "r_rotor_gap_mm": r_rotor_gap, "r_stator_gap_mm": r_stator_gap,
        "r_gap_mm": 0.5 * (r_rotor_gap + r_stator_gap),
        "luftspalt_mm": spalt,
        "nach_stator": nach_stator,
        # Der Ring, der die Fliehkraft traegt: beim Innenlaeufer von der Welle
        # bis zum Luftspalt, beim Aussenlaeufer vom Luftspalt bis nach aussen.
        "r_traeger_innen_mm": r_rot_i if b == "aussen" else r_wel,
        "r_traeger_aussen_mm": r_rot_a,
        "u_umfang_mm": 2.0 * math.pi * r_rotor_gap,
    }


def magnethaltung(geom: dict) -> dict:
    """Was die Fliehkraft mit den Magneten macht -- und wer sie haelt.

    Der Unterschied ist keine Formel, sondern eine Aussage, und deshalb steht
    sie als Text da:

    * **Innenlaeufer**: die Magnete wollen nach aussen, gehalten wird sie der
      Blechsteg zum Luftspalt. Er ist damit das bindende Bauteil, und
      ``ema_rotorcheck`` prueft ihn.
    * **Aussenlaeufer**: die Magnete wollen ebenfalls nach aussen -- und da
      liegt der Ring. Sie werden gegen ihn gedrueckt. Der Steg traegt dann
      keine Magnetlast mehr; die bindende Groesse ist die Ringspannung selbst.

    Das ist ein wirklicher Vorteil des Aussenlaeufers und keine Umbuchung: ein
    Steg, der keine Magnete halten muss, darf duenn sein oder ganz entfallen,
    und das spart genau den Streufluss, den er sonst kurzschliesst.
    """
    b = bauform(geom)
    if b == "innen":
        return {"bauform": b,
                "haltendes_bauteil": "Blechsteg zum Luftspalt",
                "steg_traegt_magnete": True,
                "aussage": ("Die Fliehkraft zieht die Magnete nach aussen; "
                            "gehalten werden sie vom Blechsteg zum Luftspalt. "
                            "Er ist das bindende Bauteil.")}
    return {"bauform": b,
            "haltendes_bauteil": "der Laeuferring selbst",
            "steg_traegt_magnete": False,
            "aussage": ("Die Fliehkraft drueckt die Magnete GEGEN den Ring. "
                        "Der Steg traegt keine Magnetlast; bindend ist die "
                        "Ringspannung. Ein duennerer oder entfallender Steg "
                        "spart hier genau den Streufluss, den er sonst "
                        "kurzschliesst.")}


def uebersicht(geom: dict) -> str:
    r = radien(geom)
    m = magnethaltung(geom)
    z = [f"{r['label']}"]
    for name, k in (("Welle", "r_welle_mm"),
                    ("Laeufer innen", "r_rotor_innen_mm"),
                    ("Laeufer aussen", "r_rotor_aussen_mm"),
                    ("Stator innen", "r_stator_innen_mm"),
                    ("Stator aussen", "r_stator_aussen_mm")):
        z.append(f"  {name:<16} r = {r[k]:8.2f} mm")
    z.append(f"  Luftspalt        {r['luftspalt_mm']:8.3f} mm zwischen "
             f"r = {min(r['r_rotor_gap_mm'], r['r_stator_gap_mm']):.2f} und "
             f"{max(r['r_rotor_gap_mm'], r['r_stator_gap_mm']):.2f} mm")
    z.append(f"  Magnethaltung:   {m['haltendes_bauteil']}")
    z.append(f"  {m['aussage']}")
    return "\n".join(z)
