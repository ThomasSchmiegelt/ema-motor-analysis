"""Mehrkoerper-Rotor: Eisen UND Magnete gerechnet, verbunden ueber Anlageflaechen.

Wo dieser Weg neben den anderen steht
--------------------------------------

Es gibt jetzt drei Stufen fuer dieselbe Frage „haelt der Laeufer":

1. ``ema_rotorcheck.rotor_stress_check`` -- Ringspannung, geschlossene Formel,
   Millisekunden. Kennt weder Taschen noch Magnete.
2. ``ema_freecad``/``ema_deck`` + ``ema_magnetlast`` -- das Rotor**eisen** mit
   seinen Taschen vernetzt, die Magnetfliehkraft als Knotenkraefte **verschmiert
   ueber die ganze Taschenwand**. Sekunden bis Minuten.
3. **dieser Weg** -- Eisen und Magnete als getrennte Koerper, dazwischen
   Kontakt an **kleinen Anlageflaechen**. Minuten.

Stufe 2 nimmt an, der Magnet liege auf der ganzen Wand an. Das tut er nicht: die
Tasche ist um den Klebespalt groesser als der Magnet, er beruehrt sie nur dort,
wo das Blech ihn traegt. Gemessen an derselben Geometrie und demselben Netzmass
(frischer Payload, 12.000 1/min, 6 mm):

| | verschmiert | mit Anlageflaechen |
|---|---:|---:|
| Eisen P99 | 127,5 MPa | **237,7 MPa** (x1,86) |
| Eisen Median | 46,0 MPa | 39,8 MPa (x0,87) |
| Rechenzeit | 3 s | 212 s |

Beides zusammen ist das Bild: die massgebende Spannung steigt, weil dieselbe
Kraft durch viel kleinere Flaechen geht -- und der Blechkoerper als Ganzes wird
**entlastet**, weil die Magnete jetzt mittragen.

Die rpm²-Skalierung UEBERLEBT -- und das ist nicht selbstverstaendlich
---------------------------------------------------------------------

Kontakt ist eine nichtlineare Randbedingung, und die ganze Nachbearbeitung
dieser Kette (drei Betriebspunkte aus EINER Loesung, Berstdrehzahl, Video) ruht
darauf, dass Spannung und Verschiebung exakt mit ``omega²`` wachsen. Der Grund,
warum es hier trotzdem gilt: die Anlagen liegen von Anfang an **spaltfrei** an,
und die Fliehkraft kann sie nur zudruecken -- der Kontaktzustand aendert sich
also nie, und ein Kontakt, der immer geschlossen ist, ist eine lineare
Kopplung. Nachgemessen statt behauptet, an denselben zwei Laeufen:

    Eisen max   190,3 -> 761,3 MPa   Verhaeltnis 4,001
    Eisen P99    59,4 -> 237,7 MPa               4,002
    Magnet Zug    6,6 ->  26,5 MPa               4,015

bei exakt verdoppelter Drehzahl. ``linearitaetsprobe()`` faehrt genau das
nach -- wer an den Anlagen etwas aendert (Spalt statt Beruehrung), muss sie
wieder laufen lassen, sonst skaliert die Kette eine Nichtlinearitaet.

Die Anlageflaechen -- und was die Zeichnung NICHT hergibt
----------------------------------------------------------

Eine Taschenwand ist ``laenge + 2*spalt`` lang; der Magnet liegt nicht ueberall
an. Modelliert werden deshalb **Anlagen**: kleine Eisenstege, die den
Klebespalt oertlich fuellen und den Magneten spaltfrei beruehren.

* **Flankenanlagen** (``anlageProFlanke``, Vorgabe 2 je Flanke, Breite
  ``anlageBreiteMm``) tragen die Normalkomponente.
* **Endanschlag** (``anlageEndeMm``) traegt die Komponente entlang der
  Magnetachse.

Der Endanschlag ist der unbequeme Teil, und er wird hier **ausgesprochen statt
versteckt**: die gezeichnete Tasche laesst den Magneten in seiner Laengsrichtung
frei. Die Kappe ist ein Halbzylinder vom Radius ``dicke/2 + spalt``, der Magnet
endet flach -- zwischen Magnetstirn und Kappenkuppe stehen am Beispiel **3,1 mm
Luft**. Nachgerechnet reicht Reibung nicht, um ihn dort zu halten: die
Laengskomponente ist am V-Schenkel 0,747 der Fliehkraft, die Reibung an der
Flanke hoechstens ``mu * 0,664`` davon, bei mu = 0,2 also 0,133 -- der Magnet
RUTSCHT, bis er irgendwo ansteht. Also steht er an, und das Modell sagt wo.

**Der Preis steht daneben:** der Anschlag ist Eisen in der Luftkappe, und die
Luftkappe ist ein Streupfad-Sperrglied. ``anlage_kennzahlen`` rechnet aus, wie
viel der Kappenflaeche er einnimmt. **Das Feldmodell weiss davon nichts** --
``ema_topology`` zeichnet keine Anlagen, der FDM-Rasterer auch nicht. Wer den
Anschlag wirklich baut, hat einen magnetischen Kurzschluss, den diese Kette
nicht rechnet; wer ihn nicht baut, hat einen Magneten, den nichts haelt. Beides
steht in ``grenzen()`` und in ``BEFUNDE.md``.

Nur CalculiX
------------

``*CONTACT PAIR`` gibt es in Z88 nicht und in der ``.mail``-Fassung, die
``ema_aster`` schreibt, auch nicht. Der Loeservergleich (``beide``/``alle``)
bleibt deshalb bei Stufe 2 -- er prueft ohnehin den LOESER auf einem Netz, und
das ist hier nicht die Frage.
"""

from __future__ import annotations

import collections
import math
import os
from dataclasses import dataclass, field

from ema_topology import leg_center, magnet_legs

# ── Vorgaben der Anlageflaechen ──────────────────────────────────────────────
#
# Keine davon ist gemessen -- es sind Entwurfsgroessen, und sie stehen deshalb
# als benannte Konstanten hier und als Schluessel im Payload, statt im Code
# verstreut zu sein. Wer eine Maschine mit anderen Anlagen baut, setzt sie.
ANLAGE_BREITE_MM   = 3.0      # Breite einer Flankenanlage entlang der Magnetachse
ANLAGE_JE_FLANKE   = 2        # wie viele je Flanke
ANLAGE_ENDE_MM     = 1.5      # Hoehe des Endanschlags quer zur Magnetachse
ANLAGE_REIBUNG     = 0.2      # Reibbeiwert Blech/Magnet -- ANNAHME

# Strafsteifigkeit des Kontakts. CalculiX empfiehlt fuer
# ``PRESSURE-OVERCLOSURE=LINEAR`` ein Vielfaches von E/h; 10 ist der mittlere
# Wert aus dem empfohlenen Band 5...50. Zu weich laesst die Koerper
# durchdringen, zu hart macht die Gleichungen schlecht konditioniert.
KONTAKT_K_FAKTOR   = 10.0

# CalculiX-Flaechennummern eines C3D4 ueber seine LOKALEN Eckennummern.
# Jede der vier Dreierkombinationen kommt genau einmal vor -- deshalb laesst
# sich aus einem Dreieck die Flaeche eindeutig zurueckrechnen.
_FLAECHE = {frozenset((0, 1, 2)): "S1", frozenset((0, 1, 3)): "S2",
            frozenset((1, 2, 3)): "S3", frozenset((0, 2, 3)): "S4"}


class KontaktFehler(RuntimeError):
    """Der Mehrkoerperlauf ist fuer diese Auslegung nicht aufstellbar."""


@dataclass
class KontaktNetz:
    """Netz aus MEHREREN Koerpern plus den Kontaktpaaren dazwischen.

    Traegt BEIDE Dimensionen (``dim`` 3 = Tet4 raeumlich, 2 = Dreieck eben).
    Ein zweiter Netztyp daneben haette eine zweite ``kennzahlen`` nach sich
    gezogen, und dann lieferten zwei Auswertungen zwei Zahlen, ohne dass die
    DIMENSION daran schuld sein muesste -- genau die Frage, die der ebene Lauf
    beantworten soll.
    """
    knoten: dict                         # id -> (x, y, z) [mm]; eben: z = 0
    elemente: dict                       # id -> (n1..n4) bzw. (n1..n3)
    ist_eisen: dict                      # elementid -> bool
    magnet_von: dict                     # elementid -> Magnetnummer (sonst None)
    kontakte: list = field(default_factory=list)   # [(slave_faces, master_faces)]
    nset_stirn: list = field(default_factory=list)
    nset_bohrung: list = field(default_factory=list)
    fesseln: list = field(default_factory=list)    # [(knoten, freiheitsgrad)]
    anlagen: list = field(default_factory=list)    # die Entwurfsangaben
    r_rot: float = 0.0
    r_shaft: float = 0.0
    axial_len: float = 0.0
    poles: int = 0
    n_magnete: int = 0
    vol_eisen_mm3: float = 0.0
    vol_magnet_mm3: float = 0.0
    netz_grund_mm: float = 0.0
    netz_anlage_mm: float = 0.0
    netz_magnet_mm: float = 0.0
    dim: int = 3
    ebener_zustand: str = ""             # eben: 'dehnung' | 'spannung'
    ordnung: int = 1                     # 1 = CPE3/C3D4, 2 = CPE6

    @property
    def n_knoten(self) -> int:
        return len(self.knoten)

    @property
    def n_elemente(self) -> int:
        return len(self.elemente)


# ── Die Anlagen als reine Zahlen (ohne gmsh, damit pruefbar) ────────────────

def anlage_vorgaben(geom: dict) -> dict:
    """Die vier Entwurfsgroessen aus dem Payload, geklemmt und benannt."""
    return {
        "breite_mm": max(0.5, min(20.0, float(geom.get("anlageBreiteMm",
                                                       ANLAGE_BREITE_MM)))),
        "je_flanke": max(1, min(6, int(geom.get("anlageProFlanke",
                                                ANLAGE_JE_FLANKE)))),
        "ende_mm":   max(0.0, min(20.0, float(geom.get("anlageEndeMm",
                                                       ANLAGE_ENDE_MM)))),
        "reibung":   max(0.0, min(0.6, float(geom.get("anlageReibung",
                                                      ANLAGE_REIBUNG)))),
    }


def _gezeichnete_anlagen(geom: dict) -> dict:
    """``geom["customAnlagen"]`` -> ``{leg_index: [{f, u, b}, ...]}``.

    Der Designer zeichnet sie je Magnet; ohne Eintrag bleibt es bei den
    parametrischen (``anlageBreiteMm``/``anlageProFlanke``/``anlageEndeMm``).
    Eine LEERE Liste fuer einen Magneten ist ausdruecklich etwas anderes als
    gar kein Eintrag: sie heisst „dieser Magnet hat KEINE Anlagen", und dann
    haelt ihn nichts -- das meldet ``baue`` als Fehler, statt stillschweigend
    die Vorgaben einzusetzen.
    """
    roh = geom.get("customAnlagen")
    if not isinstance(roh, (list, tuple)):
        return {}
    aus: dict = {}
    for i, eintrag in enumerate(roh):
        if eintrag is None:
            continue
        liste = []
        for a in (eintrag or []):
            try:
                f = str(a["f"])
                if f not in ("flanke+", "flanke-", "kappe+", "kappe-"):
                    continue
                liste.append({"f": f, "u": float(a.get("u", 0.0)),
                              "b": float(a.get("b", ANLAGE_BREITE_MM))})
            except (KeyError, TypeError, ValueError):
                continue
        aus[i] = liste
    return aus


def anlagen(geom: dict, axial_mm: float) -> list[dict]:
    """Je Magnet seine Anlageflaechen -- Lage, Groesse, welche Magnetflaeche.

    **Gezeichnet schlaegt parametrisch.** Liegt fuer einen Magneten ein Eintrag
    in ``geom["customAnlagen"]`` (aus dem Designer), gilt der; sonst die
    parametrischen Vorgaben. Beides nebeneinander waere die Stelle, an der zwei
    Quellen ueber dieselbe Geometrie reden.

    Das pole-lokale Bezugssystem ist dasselbe wie ueberall hier (x radial,
    y tangential), die Taschenmasse sind die von ``ema_freecad`` Ziffer fuer
    Ziffer: Rechteck ``(L + 2g) x (T + 2g)``, Kappenradius ``T/2 + g``,
    Kappenmitte bei ``+-L/2``.

    Rueckgabe je Eintrag: ``magnet`` (laufende Nummer), ``flaeche``
    (``flanke+``/``flanke-``/``kappe+``/``kappe-``), ``cx``/``cy`` die Mitte der
    **Beruehrflaeche** (dort, wo Magnet und Anlage sich treffen), ``mitte_x``/
    ``mitte_y``/``winkel``/``laenge``/``dicke`` die des Pad-Rechtecks.
    """
    import ema_magnetlast as ml

    v = anlage_vorgaben(geom)
    gap = ml.klebespalt_mm(geom)
    poles = max(2, int(geom.get("p", 3)) * 2)
    gezeichnet = _gezeichnete_anlagen(geom)
    alle = magnet_legs(geom)[0]
    legs = [(li, lg) for li, lg in enumerate(alle)
            if lg.placement == "interior" and lg.length > 0 and lg.thickness > 0]
    aus: list[dict] = []
    mi = 0
    for li, lg in legs:
        ht = lg.thickness / 2.0 + gap          # halbe Taschendicke = Kappenradius
        # Die Flankenanlage darf nicht laenger sein als der Magnet: bei
        # ``je_flanke`` Stueck auf ``laenge`` muss jede hineinpassen, sonst
        # waere sie keine ANLAGE mehr, sondern die ganze Wand -- und damit
        # genau das Modell, von dem dieser Weg wegwill.
        b_fl = min(v["breite_mm"], lg.length / (2.0 * v["je_flanke"]))
        b_en = min(v["ende_mm"], lg.thickness * 0.9)
        # Die Vorgaben dieses Magneten: gezeichnet, sonst parametrisch. Sie
        # stehen EINMAL je Magnet und gelten fuer alle Pole -- die Anlagen
        # wiederholen sich mit der Teilung wie die Tasche selbst.
        if li in gezeichnet:
            vorgaben = [{"f": a["f"],
                         "u": max(-lg.length / 2.0,
                                  min(lg.length / 2.0, a["u"])),
                         "b": (min(max(0.3, a["b"]), lg.length)
                               if a["f"].startswith("flanke")
                               else min(max(0.3, a["b"]), lg.thickness * 0.95)),
                         "quelle": "gezeichnet"}
                        for a in gezeichnet[li]]
        else:
            vorgaben = []
            for sg_ in (+1, -1):
                for k in range(v["je_flanke"]):
                    vorgaben.append({
                        "f": f"flanke{'+' if sg_ > 0 else '-'}",
                        "u": (k - (v["je_flanke"] - 1) / 2.0) * (lg.length * 0.5),
                        "b": b_fl, "quelle": "parametrisch"})
                if b_en > 0.0:
                    vorgaben.append({"f": f"kappe{'+' if sg_ > 0 else '-'}",
                                     "u": 0.0, "b": b_en,
                                     "quelle": "parametrisch"})
        cx0, cy0 = leg_center(lg)
        for pol in range(poles):
            pa = pol * 2.0 * math.pi / poles
            ca, sa = math.cos(pa), math.sin(pa)
            cx = cx0 * ca - cy0 * sa
            cy = cx0 * sa + cy0 * ca
            th = lg.tilt + pa
            ux, uy = math.cos(th), math.sin(th)
            vx, vy = -uy, ux
            for vg in vorgaben:
                sg = 1.0 if vg["f"].endswith("+") else -1.0
                if vg["f"].startswith("flanke"):
                    uo = vg["u"]
                    aus.append({
                        "magnet": mi, "flaeche": vg["f"], "art": "flanke",
                        "cx": cx + uo * ux + sg * (lg.thickness / 2.0) * vx,
                        "cy": cy + uo * uy + sg * (lg.thickness / 2.0) * vy,
                        "mitte_x": cx + uo * ux + sg * (lg.thickness / 2.0
                                                        + gap / 2.0) * vx,
                        "mitte_y": cy + uo * uy + sg * (lg.thickness / 2.0
                                                        + gap / 2.0) * vy,
                        "winkel": th, "laenge": vg["b"], "dicke": gap,
                        "flaeche_mm2": vg["b"] * axial_mm,
                        "quelle": vg["quelle"]})
                else:
                    aus.append({
                        "magnet": mi, "flaeche": vg["f"], "art": "kappe",
                        "cx": cx + sg * (lg.length / 2.0) * ux,
                        "cy": cy + sg * (lg.length / 2.0) * uy,
                        "mitte_x": cx + sg * (lg.length / 2.0 + ht / 2.0) * ux,
                        "mitte_y": cy + sg * (lg.length / 2.0 + ht / 2.0) * uy,
                        "winkel": th, "laenge": ht, "dicke": vg["b"],
                        "flaeche_mm2": vg["b"] * axial_mm,
                        "kappe_r": ht, "quelle": vg["quelle"]})
            mi += 1
    return aus


def magnetflaechen(geom: dict, axial_mm: float) -> dict:
    """Mittelpunkt jeder Magnet-Aussenflaeche -- die Gegenseite der Anlagen."""
    import ema_magnetlast as ml

    gap = ml.klebespalt_mm(geom)
    _ = gap
    poles = max(2, int(geom.get("p", 3)) * 2)
    legs = [lg for lg in magnet_legs(geom)[0]
            if lg.placement == "interior" and lg.length > 0 and lg.thickness > 0]
    aus: dict = {}
    mi = 0
    for lg in legs:
        cx0, cy0 = leg_center(lg)
        for pol in range(poles):
            pa = pol * 2.0 * math.pi / poles
            ca, sa = math.cos(pa), math.sin(pa)
            cx = cx0 * ca - cy0 * sa
            cy = cx0 * sa + cy0 * ca
            th = lg.tilt + pa
            ux, uy = math.cos(th), math.sin(th)
            vx, vy = -uy, ux
            for sg in (+1, -1):
                aus[(mi, f"flanke{'+' if sg > 0 else '-'}")] = (
                    cx + sg * (lg.thickness / 2.0) * vx,
                    cy + sg * (lg.thickness / 2.0) * vy)
                aus[(mi, f"kappe{'+' if sg > 0 else '-'}")] = (
                    cx + sg * (lg.length / 2.0) * ux,
                    cy + sg * (lg.length / 2.0) * uy)
            mi += 1
    return aus


def anlage_kennzahlen(geom: dict, axial_mm: float) -> dict:
    """Was die Anlagen kosten -- Flaeche, und wie viel Luftkappe der Anschlag frisst.

    Die zweite Zahl ist die unbequeme: der Endanschlag ist Eisen in der
    Luftkappe am Magnetende, und diese Kappe ist im Magnetkreis ein
    Streupfad-Sperrglied. **Das Feldmodell dieser Kette kennt ihn nicht** --
    ``ema_topology`` zeichnet keine Anlagen. Wer den Anschlag baut, hat einen
    magnetischen Nebenschluss, den hier niemand rechnet.
    """
    import ema_magnetlast as ml

    an = anlagen(geom, axial_mm)
    if not an:
        return {"n_anlagen": 0}
    gap = ml.klebespalt_mm(geom)
    legs = [lg for lg in magnet_legs(geom)[0]
            if lg.placement == "interior" and lg.length > 0]
    kappe_flaeche = sum(math.pi * (lg.thickness / 2.0 + gap) ** 2 / 2.0
                        for lg in legs) or 1.0
    enden = [a for a in an if a["art"] == "kappe"]
    anschlag_flaeche = sum(a["dicke"] * a["laenge"] for a in enden[:len(legs) * 2])
    je_magnet = len(an) // max(1, len({a["magnet"] for a in an}))
    return {
        "n_anlagen": len(an),
        "n_anlagen_je_magnet": je_magnet,
        "flaeche_je_magnet_mm2": round(
            sum(a["flaeche_mm2"] for a in an if a["magnet"] == 0), 1),
        "anteil_an_der_wand_pct": round(
            100.0 * sum(a["flaeche_mm2"] for a in an if a["magnet"] == 0
                        and a["art"] == "flanke")
            / max(1e-9, 2.0 * (legs[0].length + 2 * gap) * axial_mm), 1),
        "endanschlag": bool(enden),
        "endanschlag_anteil_luftkappe_pct": (
            round(100.0 * anschlag_flaeche / (2.0 * kappe_flaeche), 1)
            if enden else 0.0),
        **anlage_vorgaben(geom),
    }


# ── Netzbau ──────────────────────────────────────────────────────────────────

def baue(geom: dict, axial_mm: float, mesh_mm: float = 6.0,
         mesh_anlage_mm: float | None = None,
         saum_faktor: float = 3.0,
         mesh_magnet_mm: float | None = None) -> KontaktNetz:
    """Eisen (mit Taschen UND Anlagen) plus jeden Magneten als eigenen Koerper.

    **Nicht fragmentiert.** Eisen und Magnete bleiben getrennte OCC-Koerper,
    damit gmsh an der Beruehrflaeche DOPPELTE Knoten erzeugt -- das ist der
    Unterschied zwischen Kontakt und Verklebung. Wer hier ``occ.fragment`` ruft,
    bekommt ein konformes Netz und damit eine Verbindung, die auch ZUG
    uebertraegt; ein Klebespalt tut das nicht.

    **An den Anlagen wird VERFEINERT**, und das ist keine Kosmetik: dort sitzt
    die Spannungsspitze, um derentwillen es diesen Rechenweg gibt, und dort ist
    eine gleichmaessige Zellgroesse am ungeeignetsten -- eine 3-mm-Anlage traegt
    bei 6 mm Netz nicht einmal ein Element in ihrer Breite. ``mesh_anlage_mm``
    (Vorgabe ``mesh_mm/3``, mindestens 0,4 mm) gilt AUF den Anlageflaechen und
    laeuft ueber ``saum_faktor * mesh_anlage_mm`` auf das Grundmass aus
    (Distance → Threshold, dasselbe Muster wie die zonale Verfeinerung in
    ``ema_em3d``). Der Saum ist noetig: ein Sprung von 0,8 auf 6 mm auf einer
    Elementkante gibt entartete Tetraeder, und die bringt CalculiX nicht durch.
    """
    import gmsh

    v = anlage_vorgaben(geom)
    an = anlagen(geom, axial_mm)
    # Ein Magnet OHNE Anlagen schwimmt in seiner Tasche -- das ist kein
    # Netzproblem, sondern ein Starrkoerpermodus, und CalculiX bricht damit
    # kryptisch ab. Eine leere gezeichnete Liste ist ausdruecklich etwas
    # anderes als kein Eintrag (der faellt auf die Vorgaben zurueck), also
    # wird sie benannt statt stillschweigend gefuellt.
    _mit = {a["magnet"] for a in an}
    _alle_m = {i for i in range(len([
        lg for lg in magnet_legs(geom)[0]
        if lg.placement == "interior" and lg.length > 0 and lg.thickness > 0])
        * max(2, int(geom.get("p", 3)) * 2))}
    _ohne = sorted(_alle_m - _mit)
    if _ohne:
        raise KontaktFehler(
            f"{len(_ohne)} Magnete haben KEINE Anlageflaeche (erster: Nr. "
            f"{_ohne[0]}). Ein Magnet ohne Anlage schwimmt in seiner Tasche; "
            f"der Loeser bricht daran mit einem Starrkoerpermodus ab. Entweder "
            f"im Designer Anlagen setzen oder den Eintrag in customAnlagen "
            f"weglassen (dann gelten die parametrischen Vorgaben).")
    if not an:
        raise KontaktFehler(
            "keine eingelassenen Magnete -- der Mehrkoerperlauf rechnet den "
            "Kontakt zwischen Blech und Magnet; ohne Magnete in Taschen gibt "
            "es keinen. Oberflaechenmagnete (SPM/Halbach) sitzen aussen auf "
            "und brauchen eine Bandage, keine Taschenanlage.")
    import ema_magnetlast as ml
    gap = ml.klebespalt_mm(geom)
    poles = max(2, int(geom.get("p", 3)) * 2)
    r_rot = float(geom["rotorOD"]) / 2.0
    r_sh = float(geom["shaftD"]) / 2.0
    legs = [lg for lg in magnet_legs(geom)[0]
            if lg.placement == "interior" and lg.length > 0 and lg.thickness > 0]
    mfl = magnetflaechen(geom, axial_mm)

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ

        def _rect(cx, cy, th, a, b):
            s = occ.addRectangle(-a / 2, -b / 2, 0, a, b)
            occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, th)
            occ.translate([(2, s)], cx, cy, 0)
            return s

        ring = occ.cut([(2, occ.addDisk(0, 0, 0, r_rot, r_rot))],
                       [(2, occ.addDisk(0, 0, 0, r_sh, r_sh))])[0]
        taschen, magnete = [], []
        for lg in legs:
            ht = lg.thickness / 2.0 + gap
            cx0, cy0 = leg_center(lg)
            for pol in range(poles):
                pa = pol * 2.0 * math.pi / poles
                ca, sa = math.cos(pa), math.sin(pa)
                cx = cx0 * ca - cy0 * sa
                cy = cx0 * sa + cy0 * ca
                th = lg.tilt + pa
                ux, uy = math.cos(th), math.sin(th)
                taschen.append((2, _rect(cx, cy, th, lg.length + 2 * gap,
                                         lg.thickness + 2 * gap)))
                for sg in (+1, -1):
                    taschen.append((2, occ.addDisk(
                        cx + sg * (lg.length / 2.0) * ux,
                        cy + sg * (lg.length / 2.0) * uy, 0, ht, ht)))
                magnete.append((2, _rect(cx, cy, th, lg.length, lg.thickness)))
        pads = [(2, _rect(a["mitte_x"], a["mitte_y"], a["winkel"],
                          a["laenge"], a["dicke"])) for a in an]
        eisen = occ.fuse(occ.cut(ring, taschen)[0], pads)[0]
        occ.synchronize()
        ve = [t for d, t in occ.extrude(eisen, 0, 0, axial_mm) if d == 3]
        vm = [t for d, t in occ.extrude(magnete, 0, 0, axial_mm) if d == 3]
        occ.synchronize()
        if len(ve) != 1:
            raise KontaktFehler(
                f"das Rotorblech zerfaellt in {len(ve)} Koerper -- eine Anlage "
                f"haengt in der Luft statt am Eisen (gemessen passiert das, "
                f"wenn der Endanschlag die Kappenkuppe nicht erreicht).")
        if len(vm) != len({a['magnet'] for a in an}):
            raise KontaktFehler(f"{len(vm)} Magnetkoerper gegen "
                                f"{len({a['magnet'] for a in an})} erwartete")
        vol_e = float(occ.getMass(3, ve[0]))
        vol_m = float(sum(occ.getMass(3, t) for t in vm))

        # ── Flaechen suchen, SOLANGE die Geometrie noch roh ist ──────────
        # Zweimal brauchen wir sie: fuer das Verfeinerungsfeld (vor dem Netz)
        # und fuer die Kontaktpaare (nach dem Netz). Zweimal suchen waere zwei
        # Gelegenheiten, verschiedene Flaechen zu finden.
        flaechen = _flaechen_suchen(gmsh, ve, vm, an, mfl, axial_mm)

        fein = (max(0.4, mesh_mm / 3.0) if mesh_anlage_mm is None
                else max(0.2, float(mesh_anlage_mm)))
        fein = min(fein, mesh_mm)
        magn = (float(mesh_mm) if mesh_magnet_mm is None
                else min(float(mesh_mm), max(0.2, float(mesh_magnet_mm))))

        felder = []
        alle_pads = sorted({s for ss in flaechen["slaves"].values() for s in ss})
        if alle_pads and fein < mesh_mm:
            fd = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(fd, "SurfacesList", alle_pads)
            gmsh.model.mesh.field.setNumber(fd, "Sampling", 24)
            ft = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(ft, "InField", fd)
            gmsh.model.mesh.field.setNumber(ft, "SizeMin", fein)
            gmsh.model.mesh.field.setNumber(ft, "SizeMax", mesh_mm)
            gmsh.model.mesh.field.setNumber(ft, "DistMin", 0.0)
            gmsh.model.mesh.field.setNumber(ft, "DistMax",
                                            max(1e-6, saum_faktor * fein))
            felder.append(ft)
        # Der MAGNETKOERPER selbst. Das Pad-Feld sitzt auf den Anlagen, und die
        # liegen auf der Eisenseite: der Magnet blieb damit bis zum 22.10.2026
        # auf dem Grundmass, also bei 6 mm Netz ETWA EIN Element ueber seine
        # 6 mm Dicke. Gemessen war das der Grund, warum der 3-D-Lauf am
        # Magneten nur die Haelfte der Hauptzugspannung fand, die der
        # 2-D-Lauf konvergiert ausgibt (s. BEFUNDE.md). ``None`` laesst jeden
        # Altlauf Ziffer fuer Ziffer stehen.
        if vm and magn < mesh_mm:
            fk = gmsh.model.mesh.field.add("Constant")
            gmsh.model.mesh.field.setNumbers(fk, "VolumesList",
                                             [float(t) for t in vm])
            gmsh.model.mesh.field.setNumber(fk, "VIn", magn)
            gmsh.model.mesh.field.setNumber(fk, "VOut", mesh_mm)
            felder.append(fk)

        if felder:
            if len(felder) == 1:
                hg = felder[0]
            else:
                hg = gmsh.model.mesh.field.add("Min")
                gmsh.model.mesh.field.setNumbers(hg, "FieldsList",
                                                 [float(f) for f in felder])
            gmsh.model.mesh.field.setAsBackgroundMesh(hg)
            # Das Hintergrundfeld gewinnt -- sonst ueberschreibt die
            # Grundzellgroesse es wieder.
            gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
            gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_mm)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin",
                              min(fein, magn, mesh_mm / 6.0))
        gmsh.option.setNumber("Mesh.ElementOrder", 1)
        gmsh.model.mesh.generate(3)

        netz = _ernte(gmsh, ve, vm, flaechen, axial_mm, r_rot, r_sh, poles,
                      vol_e, vol_m)
        netz.netz_anlage_mm = fein
        netz.netz_grund_mm = float(mesh_mm)
        netz.netz_magnet_mm = magn
    finally:
        gmsh.finalize()
    netz.anlagen = an
    return netz


# ── Derselbe Fall EBEN (dim = 2) ─────────────────────────────────────────────
#
# Der Lastfall ist planar: die Fliehkraft liegt im Querschnitt, und der
# raeumliche Lauf haelt BEIDE Stirnflaechen in z fest -- das ist der ebene
# Verzerrungszustand. Die dritte Dimension kostet damit ~126.000 Tetraeder und
# traegt nichts bei, was die Scheibe nicht auch sagt.
#
# Zwei Dinge gewinnt der ebene Lauf, und beide sind gemessen:
#
# 1. **Die Verfeinerung an den Anlagen wird bezahlbar.** Raeumlich kostete das
#    feinste Anlagennetz (1,25 mm) 50.277 Knoten und 286 s; eben kostet
#    0,3 mm 34.391 Knoten und 27 s -- also ein Vielfaches der Aufloesung dort,
#    wo die Spitze sitzt, zum Zehntel der Zeit.
# 2. **BEIDE ebenen Zustaende lassen sich rechnen** und klammern die Antwort
#    ein, so wie ``rotor_stress_check`` es analytisch schon tut. Gemessen
#    liegen sie dicht beieinander (Blech P99 220,4 gegen 227,4 MPa), und genau
#    das macht die ebene Antwort belastbar: die Wahl des Zustands entscheidet
#    hier nichts.
#
# Was eben NICHT drin ist, steht in ``grenzen()``: kein axialer Verlauf, also
# keine Aussage ueber die Stirnseiten, keine Schraegung und keine axial
# unterbrochene Anlage. Die Anlagen dieser Kette laufen ueber die ganze
# Paketlaenge (``magnetflaechen``), deshalb trifft die Scheibe sie exakt --
# wer eine axial geteilte Anlage baut, braucht den raeumlichen Lauf.

EBENE_ZUSTAENDE = ("dehnung", "spannung")

# Kante -> CalculiX-Flaeche am Dreieck. CPE3/CPS3: S1 = 1-2, S2 = 2-3,
# S3 = 3-1 -- das Gegenstueck zu ``_FLAECHE`` am Tetraeder.
_KANTE = {frozenset((0, 1)): "S1", frozenset((1, 2)): "S2",
          frozenset((0, 2)): "S3"}


def baue_eben(geom: dict, axial_mm: float, mesh_mm: float = 3.0,
              mesh_anlage_mm: float | None = None,
              saum_faktor: float = 3.0,
              ebener_zustand: str = "dehnung",
              ordnung: int = 1) -> KontaktNetz:
    """Den Mehrkoerperfall als EBENE Scheibe vernetzen (``dim = 2``).

    Dieselben Anlagen (``anlagen``), dieselben Magnetflaechen
    (``magnetflaechen``), dieselben Reib- und Steifigkeitsgroessen, dieselbe
    Auswertung (``kennzahlen``) -- nur eine Dimension tiefer. Verdoppelt wird
    hier ausdruecklich nur, was die zweite Dimension IST: der OCC-Aufbau aus
    Rechtecken statt Kaesten, die Suche der Beruehr-KURVEN statt -flaechen und
    der Elementtyp.

    ``ebener_zustand`` waehlt zwischen ``dehnung`` (CPE3, eps_z = 0 -- der
    Fall, den der raeumliche Lauf mit seinen gehaltenen Stirnflaechen rechnet,
    deshalb die Vorgabe) und ``spannung`` (CPS3, sig_z = 0 -- die duenne
    Scheibe). Die Magnete bleiben wie raeumlich **ungefragmentiert**: ein
    ``occ.fragment`` gaebe ein konformes Netz, also eine Verklebung, die auch
    ZUG uebertraegt, und ein Klebespalt tut das nicht.
    """
    import collections

    import gmsh

    from ema_topology import leg_center, magnet_legs
    import ema_magnetlast as _ml

    if ebener_zustand not in EBENE_ZUSTAENDE:
        raise KontaktFehler(
            f"ebener_zustand: {ebener_zustand!r} -- erlaubt sind "
            f"{' und '.join(EBENE_ZUSTAENDE)}")
    ordnung = int(ordnung)
    if ordnung not in (1, 2):
        raise KontaktFehler(f"ordnung: {ordnung} -- erlaubt sind 1 und 2")

    p_pol = int(geom.get("p", 3))
    poles = 2 * p_pol
    r_rot = float(geom["rotorOD"]) / 2.0
    r_sh = float(geom["shaftD"]) / 2.0
    gap = _ml.klebespalt_mm(geom)
    an = anlagen(geom, axial_mm)
    mfl = magnetflaechen(geom, axial_mm)
    legs = [l for l in magnet_legs(geom)[0]
            if l.placement == "interior" and l.length > 0]
    if not legs:
        raise KontaktFehler(
            "keine vergrabenen Magnete -- der Mehrkoerperlauf braucht Magnete "
            "in Taschen (Oberflaechenmagnete haben keine Anlageflaechen).")
    if not an:
        raise KontaktFehler(
            "kein Magnet hat eine Anlageflaeche -- ein Magnet ohne Anlage "
            "schwimmt in seiner Tasche, und CalculiX bricht daran mit einem "
            "Starrkoerpermodus ab.")

    fein = (max(0.2, mesh_mm / 3.0) if mesh_anlage_mm is None
            else max(0.1, float(mesh_anlage_mm)))
    fein = min(fein, mesh_mm)

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ

        def _rechteck(cx, cy, winkel, a, b):
            t = occ.addRectangle(-a / 2.0, -b / 2.0, 0.0, a, b)
            occ.rotate([(2, t)], 0, 0, 0, 0, 0, 1, winkel)
            occ.translate([(2, t)], cx, cy, 0.0)
            return t

        ring = occ.cut([(2, occ.addDisk(0, 0, 0, r_rot, r_rot))],
                       [(2, occ.addDisk(0, 0, 0, r_sh, r_sh))])[0]
        taschen, magnete = [], []
        for lg in legs:
            ht = lg.thickness / 2.0 + gap
            cx0, cy0 = leg_center(lg)
            for pol in range(poles):
                pa = pol * 2.0 * math.pi / poles
                ca, sa = math.cos(pa), math.sin(pa)
                cx, cy = cx0 * ca - cy0 * sa, cx0 * sa + cy0 * ca
                th = lg.tilt + pa
                ux, uy = math.cos(th), math.sin(th)
                taschen.append((2, _rechteck(cx, cy, th, lg.length + 2 * gap,
                                             lg.thickness + 2 * gap)))
                # Die Endkappen sind Halbkreise vom Radius dicke/2 + Spalt --
                # dieselbe Langloch-Tasche wie raeumlich.
                for sg in (+1, -1):
                    taschen.append((2, occ.addDisk(
                        cx + sg * (lg.length / 2.0) * ux,
                        cy + sg * (lg.length / 2.0) * uy, 0.0, ht, ht)))
                magnete.append((2, _rechteck(cx, cy, th, lg.length,
                                             lg.thickness)))
        pads = [(2, _rechteck(a["mitte_x"], a["mitte_y"], a["winkel"],
                              a["laenge"], a["dicke"])) for a in an]
        eisen = occ.fuse(occ.cut(ring, taschen)[0], pads)[0]
        occ.synchronize()
        se = [t for d, t in eisen if d == 2]
        sm = [t for d, t in magnete if d == 2]
        if len(se) != 1:
            raise KontaktFehler(
                f"das Rotorblech zerfaellt in {len(se)} Flaechen -- eine "
                f"Anlage haengt in der Luft statt am Eisen.")
        if len(sm) != len({a["magnet"] for a in an}):
            raise KontaktFehler(f"{len(sm)} Magnetflaechen gegen "
                                f"{len({a['magnet'] for a in an})} erwartete")
        vol_e = float(occ.getMass(2, se[0])) * float(axial_mm)
        vol_m = float(sum(occ.getMass(2, t) for t in sm)) * float(axial_mm)

        # ── Beruehrkurven suchen, SOLANGE die Geometrie roh ist ──────────
        # Wie raeumlich: das Verfeinerungsfeld braucht sie VOR dem Netz, die
        # Kontaktpaare danach -- zweimal suchen waeren zwei Gelegenheiten,
        # verschiedene zu finden.
        rand = {t: [abs(c) for d, c
                    in gmsh.model.getBoundary([(2, t)], oriented=False)
                    if d == 1] for t in se + sm}
        com = {c: occ.getCenterOfMass(1, c) for t in rand for c in rand[t]}

        def _naechste(kandidaten, punkt, tol=0.5):
            best, bd = None, 1e9
            for c in kandidaten:
                d = math.hypot(com[c][0] - punkt[0], com[c][1] - punkt[1])
                if d < bd:
                    best, bd = c, d
            return best if bd <= tol else None

        slaves = collections.defaultdict(list)
        ohne = 0
        for a in an:
            c = _naechste(rand[se[0]], (a["cx"], a["cy"]))
            if c is None:
                ohne += 1
            else:
                slaves[(a["magnet"], a["flaeche"])].append(c)
        masters = {}
        for (mi, schl), pt in mfl.items():
            if mi >= len(sm):
                continue
            c = _naechste(rand[sm[mi]], pt)
            if c is not None:
                masters[(mi, schl)] = c
        if not slaves or not masters:
            raise KontaktFehler(
                f"keine Beruehrkurven gefunden ({len(slaves)} Slave-Gruppen, "
                f"{len(masters)} Master, {ohne} Anlagen ohne Kurve).")

        alle_pads = sorted({c for cc in slaves.values() for c in cc})
        if alle_pads and fein < mesh_mm:
            fd = gmsh.model.mesh.field.add("Distance")
            gmsh.model.mesh.field.setNumbers(fd, "CurvesList",
                                             [float(c) for c in alle_pads])
            gmsh.model.mesh.field.setNumber(fd, "Sampling", 40)
            ft = gmsh.model.mesh.field.add("Threshold")
            gmsh.model.mesh.field.setNumber(ft, "InField", fd)
            gmsh.model.mesh.field.setNumber(ft, "SizeMin", fein)
            gmsh.model.mesh.field.setNumber(ft, "SizeMax", mesh_mm)
            gmsh.model.mesh.field.setNumber(ft, "DistMin", 0.0)
            gmsh.model.mesh.field.setNumber(ft, "DistMax",
                                            max(1e-6, saum_faktor * fein))
            gmsh.model.mesh.field.setAsBackgroundMesh(ft)
            gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
            gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
            gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_mm)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin",
                              min(fein, mesh_mm / 6.0))
        gmsh.option.setNumber("Mesh.ElementOrder", ordnung)
        if ordnung == 2:
            # Gmsh projiziert die Mittenknoten auf die Geometrie, und auf den
            # stark gekruemmten Taschenkappen kippt dabei ein Element um: ccx
            # brach mit "nonpositive jacobian determinant in element 7760" ab.
            # Das sah wie ein Kontaktproblem aus und war ein Netzproblem. Die
            # Mittenknoten bleiben deshalb auf der Sehne.
            gmsh.option.setNumber("Mesh.SecondOrderLinear", 1)
            gmsh.option.setNumber("Mesh.HighOrderOptimize", 0)
        gmsh.model.mesh.generate(2)

        # ── Ernten ──────────────────────────────────────────────────────
        tags, koords, _ = gmsh.model.mesh.getNodes()
        roh = {int(t): (float(koords[3 * i]), float(koords[3 * i + 1]), 0.0)
               for i, t in enumerate(tags)}
        elemente, ist_eisen, magnet_von = {}, {}, {}
        # Gmsh-Elementtyp: 2 = Dreieck mit 3 Knoten, 9 = mit 6.
        dreieck_typ, nje = (2, 3) if ordnung == 1 else (9, 6)
        eid = 0
        for t in se + sm:
            ets, ens = gmsh.model.mesh.getElementsByType(dreieck_typ, t)
            mi = sm.index(t) if t in sm else None
            for i in range(len(ets)):
                eid += 1
                elemente[eid] = tuple(int(n)
                                      for n in ens[i * nje:(i + 1) * nje])
                ist_eisen[eid] = t in se
                magnet_von[eid] = mi
        if not elemente:
            raise KontaktFehler("das ebene Netz hat kein einziges Dreieck.")
        benutzt = sorted({n for ids in elemente.values() for n in ids})
        neu_nr = {a: i + 1 for i, a in enumerate(benutzt)}
        knoten = {neu_nr[a]: roh[a] for a in benutzt}
        elemente = {e: tuple(neu_nr[n] for n in ids)
                    for e, ids in elemente.items()}

        # Die Kante wird ueber ihre ECKknoten erkannt -- bei Ordnung 2 traegt
        # sie zusaetzlich einen Mittenknoten, und der steht in der
        # Elementliste hinter den Ecken (gmsh: Ecken 0..2, dann Mitten 3..5).
        k2e = collections.defaultdict(list)
        for e, ids in elemente.items():
            for lok, nm in _KANTE.items():
                k2e[frozenset(ids[i] for i in lok)].append((e, nm))

        def _kanten(kurven, eisen_seite):
            aus = []
            # Randkurve: Typ 1 = Linie mit 2 Knoten, 8 = mit 3. In einem Netz
            # 2. Ordnung gibt es KEINE Typ-1-Elemente -- die Abfrage kam leer
            # zurueck, und damit standen 0 Kontaktpaare im Satz; ccx brach
            # dann mit einem Starrkoerpermodus ab (rc = 201), was wie ein
            # Loeserproblem aussieht und keines ist.
            linien_typ = 1 if ordnung == 1 else 8
            nje1 = 2 if ordnung == 1 else 3
            for c in kurven:
                ets, ens = gmsh.model.mesh.getElementsByType(linien_typ, c)
                for i in range(len(ets)):
                    # Die ersten zwei Eintraege sind die Ecken.
                    kn = frozenset(neu_nr[int(n)]
                                   for n in ens[i * nje1:i * nje1 + 2]
                                   if int(n) in neu_nr)
                    if len(kn) != 2:
                        continue
                    for e, nm in k2e.get(kn, []):
                        if ist_eisen[e] is eisen_seite:
                            aus.append((e, nm))
                            break
            return aus

        kontakte = []
        for schl, cc in sorted(slaves.items()):
            if schl not in masters:
                continue
            fs = _kanten(sorted(set(cc)), True)
            fm = _kanten([masters[schl]], False)
            if fs and fm:
                kontakte.append((fs, fm))
        if not kontakte:
            raise KontaktFehler(
                "kein einziges Kontaktpaar im Satz -- CalculiX bricht daran "
                "mit einem Starrkoerpermodus ab (rc = 201), was wie ein "
                "Loeserproblem aussieht und keines ist.")

        # Drei Starrkoerperfesseln an der Bohrung -- dieselbe Regel wie
        # raeumlich: eingespannt wird NICHT, das waere ein anderes Problem als
        # der frei rotierende Ring der analytischen Formel.
        bohr = [i for i, (x, y, _) in knoten.items()
                if abs(math.hypot(x, y) - r_sh) < 0.5]
        if len(bohr) < 3:
            raise KontaktFehler("zu wenige Knoten auf der Bohrung fuer die "
                                "Starrkoerperfesseln.")

        def _nah(phi):
            return min(bohr, key=lambda i: abs(
                ((math.atan2(knoten[i][1], knoten[i][0]) - phi + math.pi)
                 % (2 * math.pi)) - math.pi))

        fesseln = [(_nah(0.0), 2), (_nah(math.pi), 2), (_nah(math.pi / 2), 1)]

        netz = KontaktNetz(
            knoten=knoten, elemente=elemente, ist_eisen=ist_eisen,
            magnet_von=magnet_von, kontakte=kontakte,
            nset_stirn=[], nset_bohrung=sorted(bohr), fesseln=fesseln,
            r_rot=r_rot, r_shaft=r_sh, axial_len=float(axial_mm),
            poles=poles, n_magnete=len(sm),
            vol_eisen_mm3=vol_e, vol_magnet_mm3=vol_m,
            netz_grund_mm=float(mesh_mm), netz_anlage_mm=fein,
            netz_magnet_mm=float(mesh_mm),
            dim=2, ebener_zustand=ebener_zustand, ordnung=ordnung)
    finally:
        gmsh.finalize()
    netz.anlagen = an
    return netz


def _flaechen_suchen(gmsh, ve, vm, an, mfl, axial_mm) -> dict:
    """Welche Modellflaeche gehoert zu welcher Anlage -- VOR dem Vernetzen.

    Die Paare werden NICHT hinterher erraten. Ein erster Entwurf suchte Flaechen
    mit gleichem Schwerpunkt auf zwei Koerpern -- das findet nur die
    Endanschlaege (deren Beruehrflaeche mittig auf der Magnetstirn sitzt) und
    keine einzige Flankenanlage, weil das Pad kleiner ist als die Magnetflanke
    und sein Schwerpunkt woanders liegt. Gemessen: 24 von 72.

    Gesucht wird hier und nicht in ``_ernte``, weil das Verfeinerungsfeld die
    Flaechen schon vor dem Netz braucht -- und zweimal suchen waeren zwei
    Gelegenheiten, verschiedene zu finden.
    """
    occ = gmsh.model.occ
    rand = {v: [abs(t) for d, t in gmsh.model.getBoundary([(3, v)],
                                                          oriented=False)
                if d == 2] for v in ve + vm}
    com = {s: occ.getCenterOfMass(2, s) for v in rand for s in rand[v]}
    zm = axial_mm / 2.0

    def _suche(kand, punkt, tol=0.5):
        best, bd = None, 1e9
        for s in kand:
            d = math.dist(com[s], (punkt[0], punkt[1], zm))
            if d < bd:
                best, bd = s, d
        return best if bd <= tol else None

    slaves: dict = collections.defaultdict(list)
    ohne = 0
    for a in an:
        s = _suche(rand[ve[0]], (a["cx"], a["cy"]))
        if s is None:
            ohne += 1
        else:
            slaves[(a["magnet"], a["flaeche"])].append(s)
    masters = {}
    for (mi, schl), pt in mfl.items():
        if mi >= len(vm):
            continue
        s = _suche(rand[vm[mi]], pt)
        if s is not None:
            masters[(mi, schl)] = s
    if ohne:
        raise KontaktFehler(
            f"{ohne} von {len(an)} Anlageflaechen haben im Modell keine Flaeche "
            f"gefunden -- die Anlage liegt dann nicht am Magneten an und die "
            f"Last fehlt. Das ist kein Rundungsfehler, sondern eine andere "
            f"Geometrie als gedacht.")
    return {"slaves": dict(slaves), "masters": masters}


def _ernte(gmsh, ve, vm, flaechen, axial_mm, r_rot, r_sh, poles,
           vol_e, vol_m) -> KontaktNetz:
    """Netz einsammeln und die Kontaktpaare auf die gefundenen Flaechen legen."""
    slaves, masters = flaechen["slaves"], flaechen["masters"]
    tags, koords, _ = gmsh.model.mesh.getNodes()
    roh = {int(t): (float(koords[3 * i]), float(koords[3 * i + 1]),
                    float(koords[3 * i + 2])) for i, t in enumerate(tags)}
    elemente, ist_eisen, magnet_von = {}, {}, {}
    eid = 0
    for v in ve + vm:
        ets, ens = gmsh.model.mesh.getElementsByType(4, v)
        for i in range(len(ets)):
            eid += 1
            elemente[eid] = tuple(int(n) for n in ens[i * 4:(i + 1) * 4])
            ist_eisen[eid] = v in ve
            magnet_von[eid] = None if v in ve else vm.index(v)
    if not elemente:
        raise KontaktFehler("Gmsh hat keine Tetraeder erzeugt")
    benutzt = sorted({n for ids in elemente.values() for n in ids})
    neu = {a: i + 1 for i, a in enumerate(benutzt)}
    knoten = {neu[a]: roh[a] for a in benutzt}
    elemente = {e: tuple(neu[n] for n in ids) for e, ids in elemente.items()}

    tri2el = collections.defaultdict(list)
    for e, ids in elemente.items():
        for lok, nm in _FLAECHE.items():
            tri2el[frozenset(ids[i] for i in lok)].append((e, nm))

    def _faces(sfts, eisen_seite):
        aus = []
        for s in (sfts if isinstance(sfts, list) else [sfts]):
            _ets, ens = gmsh.model.mesh.getElementsByType(2, s)
            for i in range(len(_ets)):
                tri = frozenset(neu[int(n)] for n in ens[i * 3:(i + 1) * 3]
                                if int(n) in neu)
                if len(tri) != 3:
                    continue
                for e, nm in tri2el.get(tri, []):
                    if ist_eisen[e] == eisen_seite:
                        aus.append((e, nm))
                        break
        return aus

    kontakte = []
    for schl, sfts in sorted(slaves.items()):
        if schl not in masters:
            continue
        fs = _faces(sorted(set(sfts)), True)
        fm = _faces(masters[schl], False)
        if fs and fm:
            kontakte.append((fs, fm))
    if not kontakte:
        raise KontaktFehler("keine Kontaktflaechen im Netz gefunden")

    tol = max(1e-6, 1e-4 * r_rot)
    stirn = sorted(i for i, (_x, _y, z) in knoten.items()
                   if abs(z) < tol or abs(z - axial_mm) < tol)
    bohr = [i for i, (x, y, _z) in knoten.items()
            if abs(math.hypot(x, y) - r_sh) < max(0.5, 2 * tol)]
    if len(bohr) < 3:
        raise KontaktFehler("zu wenige Bohrungsknoten fuer die Starrkoerperfesseln")

    def _naechster(phi):
        return min(bohr, key=lambda i: abs(
            ((math.atan2(knoten[i][1], knoten[i][0]) - phi + math.pi)
             % (2 * math.pi)) - math.pi))

    # Drei Fesseln gegen die Starrkoerpermoden des EISENS -- dieselbe
    # Begruendung wie in ``ema_deck``: die Fliehkraft des vollen Rings ist
    # selbstausgeglichen, eingespannt wird die Bohrung ausdruecklich NICHT.
    fesseln = [(_naechster(0.0), 2), (_naechster(math.pi), 2),
               (_naechster(math.pi / 2), 1)]

    return KontaktNetz(
        knoten=knoten, elemente=elemente, ist_eisen=ist_eisen,
        magnet_von=magnet_von, kontakte=kontakte,
        nset_stirn=stirn, nset_bohrung=sorted(bohr), fesseln=fesseln,
        r_rot=r_rot, r_shaft=r_sh, axial_len=axial_mm, poles=poles,
        n_magnete=len(vm), vol_eisen_mm3=vol_e, vol_magnet_mm3=vol_m)


# ── CalculiX-Satz ────────────────────────────────────────────────────────────

def schreibe_inp(netz: KontaktNetz, mat: dict, mag: dict, rpm: float,
                 pfad: str, reibung: float = ANLAGE_REIBUNG,
                 mesh_mm: float = 6.0) -> str:
    """Den Mehrkoerper-Rechensatz schreiben; gibt den Pfad zurueck.

    ``mat`` ist das Rotorblech (``LAMINATES``), ``mag`` der Magnetwerkstoff
    (``MAGNETS``). Die Fliehkraft wirkt ueber ``*DLOAD CENTRIF`` auf ALLE
    Elemente -- Eisen wie Magnete; dass der Magnet schwerer ist als das Blech,
    das er verdraengt, steht damit automatisch drin und muss nicht mehr als
    Ersatzlast aufgetragen werden.
    """
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    om2 = (2.0 * math.pi * float(rpm) / 60.0) ** 2
    e_fe = float(mat["E"])
    k_kontakt = KONTAKT_K_FAKTOR * e_fe / max(0.5, float(mesh_mm))
    eben = netz.dim == 2
    if eben:
        grund = "CPE" if netz.ebener_zustand != "spannung" else "CPS"
        typ = f"{grund}{3 if netz.ordnung == 1 else 6}"
    else:
        typ = "C3D4"
    # Bei Ordnung 2 scheitert die FLAECHE-zu-Flaeche-Strafkopplung gemessen:
    # ccx bricht mit "too many cutbacks" ab (nach behobener
    # Jacobi-Entartung). Die Mittenknoten einer quadratischen Kante tragen
    # eine andere Lastaufteilung als die Ecken; mit KNOTEN-zu-Flaeche
    # konvergiert derselbe Fall in 13 s.
    kontaktart = "NODE TO SURFACE" if netz.ordnung == 2 else "SURFACE TO SURFACE"

    z = ["** Mehrkoerper-Rotor (ema_kontakt): Eisen + Magnete, Kontakt an "
         "Anlageflaechen",
         f"** {netz.n_knoten} Knoten, {netz.n_elemente} {typ}, "
         f"{netz.n_magnete} Magnete, {len(netz.kontakte)} Kontaktpaare, "
         f"{rpm:.0f} min-1",
         "*NODE, NSET=Nall"]
    for i in sorted(netz.knoten):
        x, y, zz = netz.knoten[i]
        z.append(f"{i}, {x:.9g}, {y:.9g}, {zz:.9g}")
    z.append(f"*ELEMENT, TYPE={typ}, ELSET=Eall")
    for e in sorted(netz.elemente):
        z.append(f"{e}, " + ", ".join(str(n) for n in netz.elemente[e]))
    for name, flag in (("EISEN", True), ("MAGNET", False)):
        ids = [e for e in sorted(netz.elemente) if netz.ist_eisen[e] is flag]
        z.append(f"*ELSET, ELSET=E_{name}")
        z.extend(_zeilen(ids))
    z += ["*MATERIAL, NAME=BLECH", "*ELASTIC",
          f"{e_fe:.6g}, {float(mat['nu']):.6g}",
          "*DENSITY", f"{float(mat['density']) / 1e12:.9g}",
          "*MATERIAL, NAME=MAGNETWERKSTOFF", "*ELASTIC",
          f"{float(mag.get('E', 160000)):.6g}, {float(mag.get('nu', 0.24)):.6g}",
          "*DENSITY", f"{float(mag.get('density', 7500)) / 1e12:.9g}",
          "*SOLID SECTION, ELSET=E_EISEN, MATERIAL=BLECH"]
    # Eben traegt der Querschnitt seine DICKE -- die Paketlaenge. Ohne sie
    # rechnet ccx mit 1 mm, und jede Kraft waere um den Faktor der Baulaenge
    # zu klein, waehrend die SPANNUNGEN richtig aussehen.
    if eben:
        z.append(f"{float(netz.axial_len):.6g}")
    z.append("*SOLID SECTION, ELSET=E_MAGNET, MATERIAL=MAGNETWERKSTOFF")
    if eben:
        z.append(f"{float(netz.axial_len):.6g}")
    for k, (fs, fm) in enumerate(netz.kontakte):
        z.append(f"*SURFACE, NAME=SL{k}, TYPE=ELEMENT")
        z += [f"{e}, {nm}" for e, nm in fs]
        z.append(f"*SURFACE, NAME=MA{k}, TYPE=ELEMENT")
        z += [f"{e}, {nm}" for e, nm in fm]
    z += ["*SURFACE INTERACTION, NAME=ANLAGE",
          "*SURFACE BEHAVIOR, PRESSURE-OVERCLOSURE=LINEAR", f"{k_kontakt:.6g}"]
    if reibung > 0:
        # Die zweite Zahl ist die Schubsteifigkeit bis zum Gleiten, nicht der
        # Beiwert. Zu gross macht die Gleichungen schlecht konditioniert.
        z += ["*FRICTION", f"{reibung:.4g}, {k_kontakt / 10.0:.6g}"]
    for k in range(len(netz.kontakte)):
        z.append(f"*CONTACT PAIR, INTERACTION=ANLAGE, TYPE={kontaktart}")
        z.append(f"SL{k}, MA{k}")

    # Raeumlich werden beide Stirnflaechen axial gehalten -- das IST der ebene
    # VERZERRUNGSzustand. Eben steckt er schon im Elementtyp (CPE), ein
    # z-Freiheitsgrad gibt es dort nicht; ein `3, 3` darauf waere ein Fehler.
    if not eben:
        z.append("*NSET, NSET=Nstirn")
        z.extend(_zeilen(netz.nset_stirn))
        z += ["*BOUNDARY", "Nstirn, 3, 3, 0.0"]
        for kn, fg in netz.fesseln:
            z.append(f"{kn}, {fg}, {fg}, 0.0")
    else:
        z.append("*BOUNDARY")
        for kn, fg in netz.fesseln:
            z.append(f"{kn}, {fg}, {fg}, 0.0")

    z += ["*STEP, INC=200", "*STATIC", "0.25, 1.0, 1e-5, 1.0",
          "*DLOAD",
          f"Eall, CENTRIF, {om2:.9g}, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0",
          "*NODE FILE", "U", "*EL FILE", "S",
          "*EL PRINT, ELSET=Eall", "S", "*END STEP"]
    with open(pfad, "w") as f:
        f.write("\n".join(z) + "\n")
    return pfad


def _zeilen(ids, je_zeile: int = 8) -> list[str]:
    return [", ".join(str(i) for i in ids[k:k + je_zeile])
            for k in range(0, len(ids), je_zeile)]


# ── Auswertung ───────────────────────────────────────────────────────────────

def kennzahlen(netz: KontaktNetz, spannungen: dict, mat: dict,
               mag: dict) -> dict:
    """Kennzahlen JE KOERPER -- und fuer den Magneten die richtige Groesse.

    Fuer das Blech zaehlt die Vergleichsspannung gegen die Fliessgrenze. Fuer
    den Magneten **nicht**: ein gesinterter Magnet ist sproede und traegt auf
    Druck rund das Dreizehnfache dessen, was er auf Zug traegt. Massgebend ist
    deshalb die groesste HAUPTZUGSPANNUNG -- und die kann klein sein, waehrend
    die Vergleichsspannung gross aussieht (gemessen am Beispiel 26,5 gegen
    36,9 MPa). Wer den Magneten ueber von Mises beurteilt, beurteilt ihn mit
    dem Kriterium eines zaehen Werkstoffs.
    """
    import ema_deck as deck

    vm_fe, vm_mg, zug_mg = [], [], []
    vol_fe, vmvol_fe = 0.0, 0.0
    gew_fe, gew_mg, vol_mg = [], [], 0.0
    for eid, sig in spannungen.items():
        if eid not in netz.elemente:
            continue
        v = deck.von_mises(*sig)
        w = _elvol(netz, eid)
        if netz.ist_eisen.get(eid, True):
            vm_fe.append(v)
            gew_fe.append(w)
            vol_fe += w
            vmvol_fe += v * w
        else:
            vm_mg.append(v)
            zug_mg.append(_hauptzug(sig))
            gew_mg.append(w)
            vol_mg += w
    if not vm_fe:
        return {"solver_status": "KEINE_SPANNUNGEN"}

    def _p99(w):
        w = sorted(w)
        return w[min(len(w) - 1, int(0.99 * len(w)))]

    def _p99_vol(werte, gewichte):
        """Das 99. Hundertstel ueber das VOLUMEN statt ueber die Elementzahl.

        Dieselbe Begruendung wie bei ``stress_mean_vol_MPa``: eine
        Verfeinerung legt viele kleine Elemente in einen kleinen Bereich, und
        ein Hundertstel ueber ELEMENTE zaehlt die wie grosse -- der
        Schwellwert wanderte dann mit dem Netz, obwohl sich am Koerper nichts
        aendert. Gegeben wird der Wert, unter dem 99 % des Volumens liegen.
        """
        paare = sorted(zip(werte, gewichte))
        ges = sum(gewichte)
        if ges <= 0:
            return None
        lauf = 0.0
        for wert, g in paare:
            lauf += g
            if lauf >= 0.99 * ges:
                return wert
        return paare[-1][0]

    sigy = float(mat.get("yield_mpa", 340.0))
    aus = {
        "solver_status": "OK",
        "rechensatz": "kontakt",
        "stress_peak_MPa": round(max(vm_fe), 2),
        "stress_p99_MPa": round(_p99(vm_fe), 2),
        "stress_mean_MPa": round(sum(vm_fe) / len(vm_fe), 2),
        # Der VOLUMENgewichtete Mittelwert daneben, und der ist der
        # belastbarere. Gemessen an der Konvergenzreihe (Anlagennetz 6 -> 1,25
        # mm) faellt der elementgewichtete um 19 %, obwohl sich am Blechkoerper
        # nichts aendert -- die Verfeinerung legt viele kleine Elemente in
        # einen kleinen Bereich, und ein Mittel ueber ELEMENTE zaehlt die wie
        # grosse. Das ist eine Eigenschaft der Kennzahl, nicht der Maschine.
        # `stress_mean_MPa` bleibt elementgewichtet, damit er mit
        # `ema_deck.kennzahlen` vergleichbar bleibt.
        "stress_mean_vol_MPa": (round(vmvol_fe / vol_fe, 2) if vol_fe > 0
                                else None),
        "stress_p99_vol_MPa": (round(_p99_vol(vm_fe, gew_fe), 2)
                               if vol_fe > 0 else None),
        "volumen_eisen_mm3": round(vol_fe, 1),
        "n_elemente_eisen": len(vm_fe),
        "safety_factor_p99": round(sigy / _p99(vm_fe), 3) if _p99(vm_fe) else None,
    }
    if zug_mg:
        zug_grenze = float(mag.get("zug_mpa", 80.0))
        zug_p99 = _p99(zug_mg)
        aus["magnet"] = {
            "n_elemente": len(vm_mg),
            "von_mises_max_MPa": round(max(vm_mg), 2),
            "hauptzug_max_MPa": round(max(zug_mg), 2),
            "hauptzug_p99_MPa": round(zug_p99, 2),
            "hauptzug_p99_vol_MPa": (round(_p99_vol(zug_mg, gew_mg), 2)
                                     if vol_mg > 0 else None),
            "volumen_magnet_mm3": round(vol_mg, 1),
            "zug_grenze_MPa": zug_grenze,
            "druck_grenze_MPa": float(mag.get("druck_mpa", 1050.0)),
            "sf_zug_p99": round(zug_grenze / zug_p99, 2) if zug_p99 > 1e-9 else None,
            "werkstoff": mag.get("label", "?"),
            "beleg": mag.get("mech_beleg", "?"),
            "hinweis": ("Massgebend ist die groesste HauptZUGspannung, nicht die "
                        "Vergleichsspannung: gesinterte Magnete sind sproede."),
        }
    return aus


def _elvol(netz: KontaktNetz, eid: int) -> float:
    """Volumen eines Elements [mm³] -- das Gewicht der Mittelung.

    Raeumlich das Tetraedervolumen, eben die Dreiecksflaeche mal der
    Scheibendicke (``*SOLID SECTION``). Beides ist ein Volumen in mm³, also
    wiegt ``kennzahlen`` in beiden Dimensionen dasselbe und die Zahlen sind
    gegeneinander lesbar.
    """
    ids = netz.elemente[eid]
    if netz.dim == 2:
        a, b, c = (netz.knoten[i] for i in ids[:3])
        flaeche = abs((b[0] - a[0]) * (c[1] - a[1])
                      - (c[0] - a[0]) * (b[1] - a[1])) / 2.0
        return flaeche * float(netz.axial_len)
    a, b, c, d = (netz.knoten[i] for i in ids[:4])
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    w = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
    return abs(u[0] * (v[1] * w[2] - v[2] * w[1])
               - u[1] * (v[0] * w[2] - v[2] * w[0])
               + u[2] * (v[0] * w[1] - v[1] * w[0])) / 6.0


# Alter Name, damit nichts ausserhalb bricht.
_tetvol = _elvol


def _hauptzug(sig) -> float:
    """Groesste Hauptspannung eines Spannungstensors [MPa] -- ohne numpy.

    Geschlossene Loesung ueber die Invarianten (Cardano), damit das Modul auch
    ohne numpy ladbar bleibt und der Wert nicht von einer Bibliotheksfassung
    abhaengt. Fuer symmetrische 3x3 sind alle Eigenwerte reell.
    """
    sxx, syy, szz, sxy, sxz, syz = sig
    i1 = sxx + syy + szz
    i2 = (sxx * syy + syy * szz + szz * sxx
          - sxy * sxy - syz * syz - sxz * sxz)
    i3 = (sxx * syy * szz + 2 * sxy * syz * sxz
          - sxx * syz * syz - syy * sxz * sxz - szz * sxy * sxy)
    p = i1 * i1 / 3.0 - i2
    if p <= 1e-12:
        return i1 / 3.0
    q = i1 * i1 * i1 / 13.5 - i1 * i2 / 3.0 + i3
    r = max(-1.0, min(1.0, 1.5 * q * math.sqrt(3.0 / p) / p))
    phi = math.acos(r) / 3.0
    return i1 / 3.0 + 2.0 / 3.0 * math.sqrt(3.0 * p) * math.cos(phi)


def linearitaetsprobe(a: dict, b: dict, rpm_a: float, rpm_b: float) -> dict:
    """Skaliert der Kontaktlauf wirklich mit omega²? Die Probe, nicht die Annahme.

    Die ganze Nachbearbeitung dieser Kette (drei Betriebspunkte aus EINER
    Loesung, Berstdrehzahl, Video) ruht auf ``sigma ~ rpm²``. Bei einem
    KONTAKTproblem gilt das nur, solange der Kontaktzustand sich nicht aendert.
    Hier tut er das nicht, weil die Anlagen spaltfrei anliegen und die
    Fliehkraft sie nur zudrueckt -- aber das ist eine Behauptung, bis man sie
    misst. Gemessen (6000 gegen 12000 1/min): 4,001 / 4,002 / 4,015.
    """
    soll = (rpm_b / rpm_a) ** 2 if rpm_a > 0 else 0.0
    aus = {"rpm_a": rpm_a, "rpm_b": rpm_b, "soll": round(soll, 6), "werte": {}}
    schlimmste = 0.0
    for schl in ("stress_peak_MPa", "stress_p99_MPa", "stress_mean_MPa"):
        va, vb = a.get(schl), b.get(schl)
        if not va or not vb:
            continue
        ist = vb / va
        aus["werte"][schl] = round(ist, 4)
        schlimmste = max(schlimmste, abs(ist - soll) / soll if soll else 0.0)
    ma, mb = a.get("magnet") or {}, b.get("magnet") or {}
    if ma.get("hauptzug_max_MPa") and mb.get("hauptzug_max_MPa"):
        ist = mb["hauptzug_max_MPa"] / ma["hauptzug_max_MPa"]
        aus["werte"]["magnet_hauptzug_max_MPa"] = round(ist, 4)
        schlimmste = max(schlimmste, abs(ist - soll) / soll if soll else 0.0)
    aus["abweichung_pct"] = round(100.0 * schlimmste, 3)
    aus["linear"] = schlimmste < 0.02
    aus["bedeutung"] = (
        "linear -> die rpm²-Skalierung der Kette gilt auch hier"
        if aus["linear"] else
        "NICHT linear -> der Kontaktzustand aendert sich mit der Drehzahl; "
        "Berstdrehzahl und die abgeleiteten Betriebspunkte sind dann nicht "
        "aus EINER Loesung zu gewinnen")
    return aus


def konvergenz(dim: int = 3) -> dict:
    """WELCHE Zahl dieses Laufs belastbar ist -- gemessen, nicht vermutet.

    Konvergenzreihe am frischen Payload (Grundnetz 6 mm, Anlagennetz 6 / 3 / 2 /
    1,25 mm, 12.000 1/min, vier echte Kontaktlaeufe):

    ======================  =======  =======  =======  =======
    Anlagennetz [mm]           6,00     3,00     2,00     1,25
    ======================  =======  =======  =======  =======
    sigma max [MPa]           527,4    726,2    851,1    505,0
    sigma P99 [MPa]           247,8    225,9    229,6    219,5
    Mittel je Element [MPa]   57,40    52,27    51,27    46,28
    Mittel je Volumen [MPa]   45,84    45,40    45,38    45,31
    Magnet Zug P99 [MPa]       8,43     7,63     7,14     7,18
    Eisenvolumen [1e6 mm³]    1,741    1,744    1,743    1,743
    ======================  =======  =======  =======  =======

    Drei Befunde daraus:

    * **``stress_peak_MPa`` konvergiert NICHT** (527 -> 726 -> 851 -> 505, es
      springt). An der Kante, wo die Anlage auf die Taschenwand trifft, ist die
      Spannung theoretisch unendlich; ein feineres Netz tastet nur naeher an
      den singulaeren Punkt. Dieselbe Sorte Zahl wie das Rohmaximum an der
      Taschenecke -- und ebenso wenig als Tor tauglich.
    * **``stress_p99_MPa`` setzt sich** (ab 3 mm bei 225 +- 5, von 3,0 auf 1,25
      noch -2,8 %). Der UNverfeinerte Lauf ist der Ausreisser: eine 3-mm-Anlage
      traegt bei 6 mm Netz ein bis zwei Elemente, die Last haengt an wenigen
      Knoten, und das treibt die Spannung kuenstlich hoch. Damit ist die
      Vorgabe ``mesh_anlage = mesh/3`` belegt und nicht geraten.
    * **``stress_mean_MPa`` ist mesh-abhaengig, ``stress_mean_vol_MPa`` nicht**
      (-19 % gegen -1,2 % ueber dieselbe Reihe). Der erste mittelt ueber
      ELEMENTE und zaehlt ein kleines wie ein grosses; die Verfeinerung legt
      viele kleine in einen kleinen Bereich. Das ist eine Eigenschaft der
      Kennzahl, nicht der Maschine. Er bleibt trotzdem stehen, weil
      ``ema_deck.kennzahlen`` denselben bildet und die beiden vergleichbar
      bleiben sollen -- der volumengewichtete steht daneben.

    Dasselbe gilt am Magneten: ``hauptzug_max_MPa`` springt (46,9 / 16,2 /
    24,2 / 12,7), ``hauptzug_p99_MPa`` setzt sich bei ~7,2. Beurteilt wird
    deshalb an P99, und ``sf_zug_p99`` heisst genau deshalb so.

    Das Eisenvolumen steht ueber alle vier Netze auf 1,74e6 mm³ -- die
    unabhaengige Gegenprobe, dass sie denselben Koerper beschreiben.
    """
    if dim == 2:
        # EBENE Reihe, dieselbe Geometrie und dieselbe Drehzahl, fuenf echte
        # Laeufe (Grundnetz/Anlagennetz 6,0/1,25 -- 3,0/1,0 -- 2,0/0,6 --
        # 1,5/0,4 -- 1,0/0,3 mm):
        #
        # Knoten            3.061   5.947  10.672  17.256  34.391
        # ccx [s]             1,8     3,8     7,7    12,3    27,2
        # sigma max         358,2   368,4   399,4   429,0   475,6
        # sigma P99 (Elem.) 237,6   235,3   220,4   215,8   212,5
        # sigma P99 (Vol.)      -   173,9   185,3   189,2       -
        # Mittel je Volumen 46,98   48,27   48,73   49,01   49,25
        # Magnet Zug P99    11,43   13,56   15,56   16,01   16,50
        # Eisenvolumen [1e6] 1,740  1,740   1,740   1,739   1,739
        #
        # Was daran anders ist als raeumlich -- und es ist mehr als die
        # Dimension:
        #
        # * ``stress_peak_MPa`` steigt hier MONOTON (358 -> 476) statt zu
        #   springen. Das ist dieselbe Singularitaet an der Anlagenkante, nur
        #   ohne das Rauschen eines freien Tetraedernetzes: eben ist sie als
        #   Singularitaet zu ERKENNEN. Als Tor bleibt sie untauglich.
        # * **Die beiden P99 laufen gegeneinander** (237,6 -> 212,5 je
        #   Element, 173,9 -> 189,2 je Volumen). Der elementgewichtete faellt,
        #   weil die Verfeinerung viele kleine Elemente in die heisse Zone
        #   legt und sie dadurch UEBERvertreten ist; der volumengewichtete
        #   steigt, weil er die Spitze erst aufloest. Die belastbare Aussage
        #   ist deshalb die KLAMMER 189...216 MPa am feinsten Netz, nicht eine
        #   der beiden Zahlen. (Raeumlich sah der elementgewichtete P99 ueber
        #   seine vier Punkte wie konvergiert aus -- dass das zum Teil die
        #   Aufhebung zweier Netzeffekte war, zeigt erst diese Reihe.)
        # * ``hauptzug_p99_MPa`` am Magneten steigt noch (+3,1 % im letzten
        #   Schritt) und laeuft gegen ~16,7 MPa. Element- und
        #   Volumengewichtung stimmen dort ab 2 mm ueberein (15,56/15,57 und
        #   16,01/16,07), es ist also keine Gewichtungsfrage.
        return {
            "belastbar": ["stress_p99_MPa", "stress_p99_vol_MPa",
                          "stress_mean_vol_MPa", "magnet.hauptzug_p99_MPa",
                          "magnet.hauptzug_p99_vol_MPa"],
            "nicht_konvergent": ["stress_peak_MPa",
                                 "magnet.hauptzug_max_MPa"],
            "mesh_abhaengig": ["stress_mean_MPa"],
            # Am FEINSTEN Netz (1,0/0,3 mm), nicht am zweitfeinsten: dort
            # sind die beiden P99 am dichtesten beieinander, und genau ihr
            # Abstand ist die Unsicherheit.
            "klammer_p99_MPa": [197.3, 212.5],
            "gemessen": ("eben, Netz 6,0/1,25 ... 1,0/0,3 mm (5 Laeufe): P99 "
                         "je Element 237,6 / 235,3 / 220,4 / 215,8 / 212,5 "
                         "MPa, je Volumen - / 173,9 / 185,3 / 189,2 / - MPa "
                         "-- sie laufen GEGENEINANDER, belastbar ist die "
                         "Klammer 197...213 MPa; Magnet Zug P99 11,43 / 13,56 "
                         "/ 15,56 / 16,01 / 16,50 MPa (steigt noch, gegen "
                         "~16,7); ccx 1,8 bis 27,2 s"),
            "ebener_zustand": ("Dehnung gegen Spannung bei 2,0/0,6 mm: Blech "
                               "P99 220,4 gegen 227,4 MPa (3,2 %), Magnet Zug "
                               "P99 15,56 gegen 15,34 MPa (1,4 %), Mittel je "
                               "Volumen 48,73 gegen 59,48 MPa (22 %) -- fuer "
                               "das Tor entscheidet die Wahl wenig, fuer eine "
                               "Aussage ueber den Blechkoerper viel"),
            # Die Magnetzahl ist DREIFACH belegt, auf drei unabhaengigen
            # Wegen: CPE3 am feinsten Netz 16,50 -- CPE6 am groben Netz 16,07
            # -- CPS6 (anderer ebener Zustand!) bei 2,0/0,6 16,55 MPa. Drei
            # Verfahren, die sich in Elementgrad, Netz UND Zustand
            # unterscheiden, auf 3 % -- das ist der Beleg, dass ~16,4 MPa die
            # Zahl der Maschine ist und kein Artefakt eines Weges.
            "magnet_belegt": ("hauptzug_p99 ~ 16,4 MPa aus drei unabhaengigen "
                              "Wegen: CPE3 1,0/0,3 = 16,50 | CPE6 3,0/1,0 = "
                              "16,07 | CPS6 2,0/0,6 = 16,55 MPa"),
            "empfehlung": ("mesh 2,0 / mesh_anlage 0,6 mm kostet 8 s und "
                           "liegt beim Blech-P99 3,7 % ueber dem feinsten "
                           "Netz; am MAGNETEN lohnt 1,5/0,4 (dort fehlen bei "
                           "2,0/0,6 noch 2,8 %)"),
        }
    return {
        "belastbar": ["stress_p99_MPa", "stress_mean_vol_MPa",
                      "magnet.hauptzug_p99_MPa", "magnet.sf_zug_p99"],
        "nicht_konvergent": ["stress_peak_MPa", "magnet.hauptzug_max_MPa"],
        "mesh_abhaengig": ["stress_mean_MPa"],
        "gemessen": ("Anlagennetz 6 / 3 / 2 / 1,25 mm: P99 247,8 / 225,9 / "
                     "229,6 / 219,5 MPa; Spitze 527 / 726 / 851 / 505 MPa; "
                     "Mittel je Volumen 45,84 / 45,40 / 45,38 / 45,31 MPa"),
        # Diese vier Laeufe entstanden VOR dem Teillast-Waechter
        # (`ema_deck._ccx_schrittzeit`, 23.10.2026). Dass ccx einen nicht
        # durchgelaufenen Lastschritt mit Exit 0 und gueltiger .frd meldet, war
        # damals nicht geprueft -- und die springenden Spalten (Spitze
        # 527/726/851/505, Magnet Zug max 46,9/16,2/24,2/12,7) haben genau das
        # Muster, das eine Teillast erzeugt. Als Singularitaet gedeutet ist es
        # moeglich, als Teillast auch; die Rohdaten sind nicht mehr da. Siehe
        # BEFUNDE.md 2026-10-23 (c).
        "vorbehalt": ("ohne Teillast-Waechter gemessen -- die springenden "
                      "Spalten (Spitze, Magnet Zug max) sind nachzumessen, "
                      "bevor sie als Netzeigenschaft erklaert werden"),
        # Der Magnet ist auf diesem Weg NICHT belastbar, und das gehoert an
        # die Kennzahl und nicht nur in BEFUNDE.md: das Verfeinerungsfeld
        # sitzt auf den Anlagen (Eisenseite), der Magnetkoerper blieb auf dem
        # Grundmass. Gemessen 7,18 -> 11,01 MPa, wenn NUR das Magnetnetz
        # halbiert wird (Eisen bewegt sich dabei um 0,07 %), und der ebene
        # Lauf belegt ~16,4 MPa auf drei unabhaengigen Wegen.
        "magnet_nicht_belastbar": (
            "hauptzug_p99_MPa ist hier zu OPTIMISTISCH: der Magnetkoerper "
            "liegt auf dem Grundnetz (bei 6 mm etwa zwei Elemente ueber 6 mm "
            "Dicke), und ein C3D4 ist ein Element konstanter Dehnung -- zu "
            "steif heisst zu wenig Spannung. Gemessen ueber mesh_magnet_mm = "
            "6,0 / 3,0 / 2,0 mm: 7,18 / 11,01 / 13,46 MPa (monoton, +87 %) "
            "bei 309 / 344 / 528 s, waehrend das Eisen um 0,18 % wandert -- "
            "und selbst bei 2 mm fehlen noch 18 % zu den ~16,4 MPa, die der "
            "ebene Lauf dreifach belegt. Raeumlich ist diese Zahl auf dieser "
            "Maschine also nicht bezahlbar zu konvergieren. Fuer eine Aussage "
            "ueber den Magneten: konvergenz(2) bzw. "
            "struct_solver='kontakt_eben'."),
        "empfehlung": ("mesh_anlage <= mesh/3 -- darunter bewegt sich P99 um "
                       "weniger als 3 %"),
    }


def grenzen(dim: int = 3) -> list[str]:
    """Was dieser Lauf NICHT ist -- haengt an jedem Ergebnis.

    ``dim = 2`` haengt an, was die EBENE Scheibe zusaetzlich nicht sagt.
    """
    gemeinsam = [
        "Die Anlageflaechen sind eine ENTWURFSANNAHME. Die gezeichnete Tasche "
        "hat keine; dieses Modell setzt sie, weil ein Magnet ohne Anlage in der "
        "Tasche schwimmt. Zahl, Breite und Lage sind Parameter "
        "(anlageBreiteMm / anlageProFlanke / anlageEndeMm), keine Messung.",
        "Der Endanschlag ist EISEN in der Luftkappe am Magnetende, und das "
        "Feldmodell dieser Kette kennt ihn nicht (ema_topology zeichnet keine "
        "Anlagen). Wer ihn baut, hat dort einen magnetischen Nebenschluss, den "
        "hier niemand rechnet; wer ihn weglaesst, hat einen Magneten, den in "
        "seiner Laengsrichtung nichts haelt -- Reibung reicht nachgerechnet "
        "nicht (0,133 gegen 0,747 der Fliehkraft am V-Schenkel).",
        "Die Klebung traegt nichts. Der Magnet gilt als lose anliegendes Teil, "
        "gehalten allein von Blech und Reibung -- die unsicherere Richtung.",
        "Der Reibbeiwert (Vorgabe 0,2) ist eine Annahme ohne Beleg in dieser "
        "Werkzeugkette.",
        "E, nu und die Festigkeiten des Magneten sind Literaturgroessen der "
        "Werkstoffklasse (MAGNETS[...]['mech_beleg'] == 'annahme'), keine "
        "Messung an diesem Werkstoff.",
        "Nur CalculiX. Z88 und Code Aster bekommen hier keinen Satz "
        "geschrieben, der Loeservergleich bleibt beim verschmierten Modell.",
        "Kein Schrumpfsitz, keine Waermedehnung, keine Magnetkraefte -- wie im "
        "uebrigen Strukturpfad.",
    ]
    if dim != 2:
        return gemeinsam
    return gemeinsam + [
        "EBENE Scheibe (ein Querschnitt, Dicke = Paketlaenge): kein Verlauf "
        "ueber der Baulaenge, also keine Aussage ueber die Stirnseiten und "
        "keine ueber eine Schraegung. Die Anlagen dieser Kette laufen ueber "
        "die ganze Paketlaenge, deshalb trifft die Scheibe sie exakt -- wer "
        "eine axial GETEILTE Anlage baut, braucht den raeumlichen Lauf.",
        "Der ebene Zustand ist eine WAHL und steht in 'ebener_zustand': "
        "'dehnung' (eps_z = 0) ist der Fall, den der raeumliche Lauf mit "
        "seinen gehaltenen Stirnflaechen rechnet, 'spannung' (sig_z = 0) die "
        "duenne Scheibe. Welche Kennzahl man ansieht, entscheidet, wie viel "
        "die Wahl austraegt: gemessen bei 2,0/0,6 mm bewegt sie das Blech-P99 "
        "um 3,2 % (220,4 gegen 227,4 MPa) und die Magnet-Hauptzugspannung um "
        "1,4 % (15,56 gegen 15,34) -- das volumengewichtete MITTEL aber um "
        "22 % (48,73 gegen 59,48 MPa). Fuer das Tor entscheidet sie also "
        "wenig, fuer eine Aussage ueber den Blechkoerper viel. Der ebene "
        "Verzerrungszustand ist dabei der Fall, der zum raeumlichen Lauf "
        "dieser Kette passt.",
        "Der ELEMENTGRAD bewegt das Blech-P99, und zwar mehr als das Netz: "
        "am selben Netz (3,0/1,0 mm) gibt CPE3 220...235 MPa und CPE6 "
        "263 MPa. Das Blech-P99 ist deshalb KEINE konvergierte Groesse -- es "
        "haengt zum Teil an der Singularitaet an der Anlagenkante, und ein "
        "besseres Element loest die besser auf statt sie wegzurechnen. "
        "Konvergiert sind das volumengewichtete Mittel (1,5 % ueber beide "
        "Grade) und die Hauptzugspannung im Magneten (CPE6 am groben Netz "
        "16,07 MPa gegen CPE3 am sechsfach feineren 16,50 MPa). Wer am "
        "Blech-P99 ein Tor fuehrt, fuehrt es an einer Zahl, die mit dem "
        "Elementgrad um 12 % springt -- gemessen kippt der Sicherheitsfaktor "
        "dadurch von 1,54 auf 1,29.",
        "Zweite Ordnung braucht KNOTEN-zu-Flaeche-Kontakt: mit "
        "Flaeche-zu-Flaeche bricht CalculiX mit 'too many cutbacks' ab (nach "
        "behobener Jacobi-Entartung, gemessen 288 s bis zum Abbruch). "
        "schreibe_inp schaltet darauf um, sobald ordnung == 2 -- die beiden "
        "Grade rechnen damit nicht denselben Kontaktalgorithmus. Und wie weit "
        "die zweite Ordnung traegt, haengt am ebenen ZUSTAND: bei 2,0/0,6 mm "
        "erreichte CPE6 (Dehnung) nur 0,136 von 1,0 Lastschritt "
        "(Inkrementlimit, Kennzahlen um Faktor 8 zu niedrig -- gefangen vom "
        "Teillast-Waechter in ema_deck.loese_ccx), waehrend CPS6 (Spannung) "
        "am selben Netz in 242 s durchlief. Der ebene Spannungszustand ist "
        "weicher (kein eps_z = 0), und die Kontaktiteration konvergiert "
        "dort. Wer zweite Ordnung auf einem feineren Netz braucht, nimmt "
        "deshalb 'spannung' -- und sagt dazu, dass das ein anderer Zustand "
        "ist.",
    ]
