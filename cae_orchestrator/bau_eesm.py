#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Nur die fremderregte Synchronmaschine bauen — und nachmessen, was herauskam.

Warum es diese Datei gibt
-------------------------

Der Schenkelpollaeufer entsteht sonst mitten in ``ema_freecad.
build_full_motor_script``: einem 1200-Zeilen-Erzeuger, der Welle, Rotorblech,
Magnete, Staender, Hairpins, Wickelkoepfe, Lager und Isolierpapier in EINEM
Skript zusammensetzt und es an einen fremden Prozess schickt. Wer dort eine
Polform beurteilen will, baut vierzig Sekunden lang eine ganze Maschine und
sucht das Ergebnis in einem Modellbaum mit zwanzig Koerpern.

Hier laeuft NUR der Laeufer: Joch, Pole, Polschuhe, Erregerspulen, wahlweise
Daempferkaefig und Schleifringe. Kein Staender, keine Wicklung, kein Magnet.
Das Skript ist zum LESEN und zum Aendern gedacht — es ist die Werkbank fuer
diese eine Bauart.

Was es ausdruecklich NICHT tut
------------------------------

**Es rechnet keine Geometrie.** Jede Zahl kommt aus ``ema_eesm_cad.koerper``
und ``ema_schenkelpol`` — denselben Funktionen, aus denen die Pipeline, das
Querschnittsbild und die Leinwand zeichnen. Ein zweiter Satz Formeln hier waere
genau die Stelle, an der die Werkbank eine andere Maschine zeigt als das
Werkzeug, und beide saehen richtig aus.

Gemessen wird dafuer am GEBAUTEN Koerper und nicht am Parameter, aus dem er
entstand: Zahl der Festkoerper, Volumen, groesster und kleinster Radius,
Ueberstand ueber den Laeuferrand. Das ist der Zweck — eine Zeichnung, die man
nur ansieht, ist eine Behauptung.

Aufruf
------

    python3 bau_eesm.py                          # frischer Payload, Rechteckspule
    python3 bau_eesm.py --spule kegel            # kegelig gewickelt
    python3 bau_eesm.py --p 4 --daempfer         # 8 Pole mit Daempferkaefig
    python3 bau_eesm.py --vergleich              # beide Spulenformen nebeneinander
    python3 bau_eesm.py --nur-zahlen             # ohne FreeCAD, nur die Masse
    python3 bau_eesm.py --bild                   # dazu das Querschnittsbild

Ohne ``--aus`` landet alles in ``~/cae_projekte/_werkbank_eesm/``.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys

HIER = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HIER)

AUS_VORGABE = os.path.expanduser("~/cae_projekte/_werkbank_eesm")


# ── Die Masse. Gelesen, nicht gerechnet. ─────────────────────────────────────

def masse(geom: dict, axial: float) -> dict:
    """Alles, was der Bau braucht — aus den Funktionen, die die Maschine rechnen."""
    import ema_eesm
    import ema_eesm_cad
    import ema_schenkelpol
    import ema_schleifring

    k = ema_eesm_cad.koerper(geom, axial)
    d = ema_schenkelpol.daempferkaefig(geom, axial)
    n_max = float(geom.get("rpm_to") or 0.0)
    b = ema_schenkelpol.befestigung(geom, axial, n_max) if n_max > 0 else None
    rg = ema_schleifring.geometrie(geom, float(k["I_f_A"]),
                                   ema_eesm.RING_ZAHL, n_max or None)
    return {"koerper": k, "daempfer": d, "befestigung": b, "ringe": rg,
            "axial": float(axial),
            # Die HOHLWELLE. `shaftBoreD` ist ein Schemaparameter wie jeder
            # andere, aber der Schenkelpolpfad las ihn nirgends -- gezeichnet
            # wurde immer eine Vollwelle. Ob die Bohrung magnetisch zulaessig
            # ist, sagt `cae_cli.py welle` (ein echter Feldlauf); hier wird
            # nur gezeichnet, was gefordert ist.
            "r_bohrung": max(float(geom.get("shaftBoreD") or 0.0) / 2.0, 0.0)}


# ── Der Bau. Ein Skript fuer FreeCAD, so kurz wie die Sache erlaubt. ─────────
#
# KEIN Docstring in den erzeugten Bloecken: der Text wandert in eine
# f-Zeichenkette, und ein dreifaches Anfuehrungszeichen beendet sie dort
# (zweimal passiert, s. BEFUNDE.md). Kommentare mit `#`.

def skript(m: dict, fcstd: str, step: str) -> str:
    k, d, rg = m["koerper"], m["daempfer"], m["ringe"]
    axial = m["axial"]
    bohrung = m["r_bohrung"]
    return f'''# -*- coding: utf-8 -*-
import json, math
import FreeCAD as App, Part

# Die Masse als PYTHON-Literale, nicht als JSON. `json.dumps` schreibt
# `true`/`false`/`null`, und das sind in einem Python-Skript drei undefinierte
# Namen -- FreeCAD scheitert mit "name 'true' is not defined". Genau dagegen
# gibt es ``zeichenmasse`` in ema_eesm_cad; hier werden auch Urteile gebraucht
# (`aktiv`, `passt`), also `repr`.
K = {k!r}
D = {d!r}
RG = {rg!r}
L = {axial!r}
Z0 = -L / 2.0

doc = App.newDocument("EESM")
teile = {{}}


def _add(name, shape, farbe):
    # `FreeCADCmd` laeuft ohne Oberflaeche: `ViewObject` ist dort None (nicht
    # etwa abwesend), ein `hasattr` genuegt also nicht. Die Farbe wird trotzdem
    # gesetzt, wenn es sie gibt -- beim Oeffnen in der GUI ist sie die einzige
    # Stelle, an der man Polfolge und Bauteile auseinanderhaelt.
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    vo = getattr(o, "ViewObject", None)
    if vo is not None:
        try:
            vo.ShapeColor = farbe
        except Exception:
            pass
    teile[name] = shape
    return o


# ── 1. Welle -- hohl, wenn eine Bohrung gesetzt ist ─────────────────────────
welle = Part.makeCylinder(K["r_welle_mm"], L * 1.6,
                          App.Vector(0, 0, Z0 - 0.3 * L))
R_BOHRUNG = {bohrung!r}
if R_BOHRUNG > 0:
    welle = welle.cut(Part.makeCylinder(R_BOHRUNG, L * 1.8,
                                        App.Vector(0, 0, Z0 - 0.4 * L)))

# ── 2. Joch: nur noch, wenn eines uebrigbleibt ─────────────────────────────
#
# Der Polkoerper laeuft bis auf die Wellenbohrung durch; zwei benachbarte
# Koerper ueberdecken sich nahe der Bohrung und BILDEN dort das Joch (die
# Nabe). Ein eigener Ring entsteht deshalb nur, wo `r_joch_aussen_mm` noch
# ueber dem Wellenradius liegt -- fuer einen gespeicherten Masssatz aus der
# Zeit davor.
joch = None
if K["r_joch_aussen_mm"] > K["r_welle_mm"] + 0.05:
    joch = Part.makeCylinder(K["r_joch_aussen_mm"], L, App.Vector(0, 0, Z0))
    joch = joch.cut(Part.makeCylinder(K["r_welle_mm"], L + 2,
                                      App.Vector(0, 0, Z0 - 1)))


def _b_kern_bei(r):
    # Die Kernbreite an einem beliebigen Radius -- die GERADE, nicht geklemmt.
    #
    # Beide Innenschneider (Spule und Tasche) reichen um 1 mm ueber den Kern
    # hinaus, damit OCC sauber schneidet. Interpoliert man ihre Breite zwischen
    # den beiden Endradien, bekommt der Schneider beim kegeligen Pol eine
    # ANDERE Neigung als der Kern und schneidet in ihn hinein -- gemessen
    # 0,03 mm3 Kupfer im Blech. Hier wird deshalb dieselbe Gerade ausgewertet,
    # aus der auch der Kern gebaut ist.
    u = ((r - K["r_fuss_mm"])
         / max(K["r_kern_aussen_mm"] - K["r_fuss_mm"], 1e-9))
    return (K["b_kern_innen_mm"]
            + (K["b_kern_aussen_mm"] - K["b_kern_innen_mm"]) * u)


# ── 3. Ein Pol: Schuh (Kreisbogen) + Kern (Trapez) ──────────────────────────
#
# Der Schuh ist ein Segment am Rand, der Kern ein radiales Trapez darunter.
# Beide ueberlappen um UEBERLAPP, damit `fuse` EINEN Festkoerper liefert und
# nicht Joch + 2p lose Stuecke -- die Struktur-FEM vernetzt genau diesen einen.
UEBERLAPP = 0.5

# Wo die Innenkante des Polkoerpers liegt [mm] -- ein Stueck JENSEITS der
# Achse, nicht davor.
#
# Bei 0,1 mm davor bleibt zwischen zwei gegenueberliegenden Koerpern ein
# 0,2 mm breiter Schlitz ueber die ganze Bauhoehe stehen. Bei vier und mehr
# Polen deckt ein anderer Arm ihn zu; bei ZWEI Polen liegen die beiden Arme
# auf einer Geraden, und der Schlitz zerschneidet den Laeufer -- gemessen
# 6 Festkoerper statt einem. Ein halber Millimeter Ueberlappung ueber die
# Achse kostet nichts: alles innerhalb der Bohrung wird ohnehin abgezogen.
ACHSE_MM = -0.5


def _trapez(r0, r1, b0, b1, grad):
    # Vier Ecken je Stirnflaeche, dazwischen ein Zugkoerper. b0 liegt bei r0
    # (innen, am Joch), b1 bei r1 (aussen, unter dem Schuh).
    def _wire(z):
        p = [App.Vector(r0, -b0 / 2.0, z), App.Vector(r1, -b1 / 2.0, z),
             App.Vector(r1, b1 / 2.0, z), App.Vector(r0, b0 / 2.0, z)]
        return Part.makePolygon(p + [p[0]])
    s = Part.makeLoft([_wire(Z0), _wire(Z0 + L)], True)
    s.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), grad)
    return s


def _schuh(grad):
    halb = math.degrees((K["b_schuh_mm"] / 2.0) / max(K["r_rotor_mm"], 1e-9))
    aussen = Part.makeCylinder(K["r_rotor_mm"], L, App.Vector(0, 0, Z0),
                               App.Vector(0, 0, 1), 2 * halb)
    innen = Part.makeCylinder(max(K["r_kern_aussen_mm"] - UEBERLAPP, 0.1),
                              L + 2, App.Vector(0, 0, Z0 - 1))
    s = aussen.cut(innen)
    mat = App.Matrix()
    mat.rotateZ(math.radians(grad - halb))
    return s.transformGeometry(mat)


# ZWEI Abschnitte je Pol: Schuh (Bogen) und KOERPER, der mit voller Breite bis
# auf den Jochring durchlaeuft. Der frueher dazwischen gezeichnete FUSS oeffnete
# sich ueber den unteren 5,8 mm von 21,7 auf 43,9 mm und stand damit als Keil im
# Zwischenpolraum -- gemeldet als „unten ist dort eine Art Keil". Er stammte aus
# der Zeit, als der Kern selbst noch ein nach innen schmaleres Trapez war und
# zum Joch hin ein Dreieck klaffte; seit der Kern ein Rechteck ist, schloss er
# eine Luecke, die es nicht mehr gibt. Der wirkliche Fuss liegt UNTER dem Joch
# (Schwalbenschwanz in einer Nut, `ema_schenkelpol.befestigung`) und ist im
# Schnitt ohnehin unsichtbar, weil Joch und Pol EIN Festkoerper werden.
pole = []
for i in range(int(K["poles"])):
    g = 360.0 * i / int(K["poles"])
    pole.append(_schuh(g))
    # Der Koerper laeuft bis an die ACHSE, die Bohrung wird danach abgezogen.
    #
    # Kurz vor der Bohrung enden zu lassen genuegt NICHT, und das ist gemessen:
    # die Stirnflaeche des Arms ist eine ebene Sehne, sie erreicht den
    # Bohrungskreis also nur innerhalb von acos(r0/r_welle) um die eigene
    # Achse -- bei r0 = 18,5 und r_welle = 19 sind das +-13,2 Grad, waehrend
    # die halbe Polteilung bei acht Polen 22,5 Grad betraegt. Dazwischen bleibt
    # die Bohrung unbedeckt, und heraus kam ein VIELZAHN statt eines Kreises.
    # Ab der Achse deckt derselbe Arm +-89,7 Grad, die Luecke kann nicht mehr
    # entstehen. Die Breite kommt aus derselben Kerngeraden, damit der kegelige
    # Pol seine Neigung behaelt.
    pole.append(_trapez(ACHSE_MM, K["r_kern_aussen_mm"],
                        _b_kern_bei(ACHSE_MM), K["b_kern_aussen_mm"], g))

# Die Welle wird ZULETZT abgezogen: die Koerper sind bis auf die Achse
# gezeichnet, damit sie sich nahe der Bohrung wirklich ueberdecken.
laeufer = (joch.fuse(pole) if joch is not None
           else pole[0].fuse(pole[1:]))
laeufer = laeufer.cut(Part.makeCylinder(K["r_welle_mm"], L + 2,
                                        App.Vector(0, 0, Z0 - 1)))
laeufer = laeufer.removeSplitter()

# ── 4. Daempferbohrungen -- durch das ganze Paket ───────────────────────────
lagen = []
if D.get("aktiv") and D.get("passt"):
    rd, nd = D["r_ring_mm"], int(D["n_stab_je_pol"])
    hd = math.degrees((D["teilung_mm"] * (nd - 1) / 2.0) / max(rd, 1e-9))
    for i in range(int(K["poles"])):
        g0 = 360.0 * i / int(K["poles"])
        for j in range(nd):
            fr = 0.0 if nd == 1 else (j / (nd - 1.0) - 0.5) * 2.0
            a = math.radians(g0 + fr * hd)
            lagen.append((rd * math.cos(a), rd * math.sin(a)))
    for cx, cy in lagen:
        laeufer = laeufer.cut(Part.makeCylinder(
            D["d_stab_mm"] / 2.0, L + 4, App.Vector(cx, cy, Z0 - 2)))

_add("Welle", welle, (0.35, 0.35, 0.38))


# ── 5. Erregerspulen: ein geschlossener Rahmen je Pol ───────────────────────
#
# Aussenkoerper minus Innenkoerper. Zwei getrennte Quader links und rechts des
# Kerns waeren zwei Leiterstaebe und keine Wicklung -- die Stuecke an den
# STIRNSEITEN fehlten dann ganz.
# Eine Spule ist GEWICKELT: an den Ecken laeuft der Draht im Bogen um den
# Kern, nicht auf Gehrung. Gerundet werden die vier langen Kanten (die in
# radialer Richtung laufen) -- innen und aussen getrennt, damit auch das Loch
# oval wird und nicht nur der Umriss. Scheitert das Runden an einem Radius,
# den die Kante nicht hergibt, bleibt die scharfe Form stehen und es wird
# GESAGT; eine stillschweigend eckige Spule saehe aus wie Absicht.
RUND_GESCHEITERT = []

# Luft zwischen Wicklung und Blech [mm] -- die Tasche ist um diesen Betrag
# groesser als die Spule.
ISOLIERLUFT = 0.3

# Wie weit die Tasche seitlich UEBER die Schuhkante hinaus schneidet [mm].
# Nur Luft -- sie sorgt dafuer, dass die flache Schuhunterseite wirklich bis an
# die Kante reicht und dort kein Bogenrest stehenbleibt.
TASCHE_UEBERSTAND_MM = 0.5

# Wie viel Schuh ueber der Taschendecke stehenbleiben MUSS [mm].
TASCHE_STEG_MM = 1.0


def _lange_kanten(s):
    # Die Kanten, die in x (radial) laufen -- an ihnen sitzt die Rundung.
    aus = []
    for e in s.Edges:
        v = e.Vertexes
        if len(v) != 2:
            continue
        dx = abs(v[0].X - v[1].X)
        dy = abs(v[0].Y - v[1].Y)
        dz = abs(v[0].Z - v[1].Z)
        if dx > dy and dx > dz:
            aus.append(e)
    return aus


def _runden(s, r, marke):
    if r <= 0.05:
        return s
    kanten = _lange_kanten(s)
    if not kanten:
        RUND_GESCHEITERT.append(marke + ": keine radialen Kanten")
        return s
    # Leiter statt EIN Versuch: OCC scheitert am gestreckten Trapez-Zugkoerper
    # der ausgefuellten Spule mit grossem Radius ("BRep_API: command not done"),
    # kommt mit einem kleineren aber zurecht. Eine ungerundete Spule ist
    # schlimmer als eine schwach gerundete -- ihre scharfen Ecken stecken im
    # Blech, weil die Tasche daneben sehr wohl gerundet ist (gemessen als
    # Durchdringung). Der zuletzt gelungene Radius steht im Ergebnis.
    fehler = ""
    for _f in (1.0, 0.6, 0.35, 0.2):
        _r = r * _f
        if _r <= 0.05:
            break
        try:
            _s = s.makeFillet(_r, kanten)
            if _f < 1.0:
                RUND_GESCHEITERT.append(
                    "%s: nur r=%.2f statt %.2f moeglich" % (marke, _r, r))
            return _s
        except Exception as e:
            fehler = str(e)[:60]
    RUND_GESCHEITERT.append(marke + ": " + fehler)
    return s


def _spulenradius():
    # Der Innenradius der Wicklung -- EINE Formel fuer die Spule UND fuer die
    # Tasche, die aus dem Laeufer geschnitten wird. Zwei Abschriften liefen um
    # Hundertstel auseinander und liessen Kupfer im Blech stehen.
    r0 = K["r_spule_innen_mm"]
    r1 = max(min(K["r_spule_aussen_mm"], K["r_kern_aussen_mm"] - UEBERLAPP),
             r0 + 0.6)
    bi, ba = K["b_kern_spuleanfang_mm"], K["b_kern_spulenende_mm"]
    # 0,45 und NICHT 0,5: `0.5 * b` ist genau die halbe Breite, also der
    # Radius, bei dem die Verrundung entartet -- OCC meldet dann
    # "BRep_API: command not done" und die Ecke bleibt scharf. Das fiel erst
    # bei der ausgefuellten Spule auf (b = 20,24 mm, Radius 10,12) und traf
    # dort BEIDE Koerper; vorher lag der Radius immer weit genug darunter.
    r_in = min(0.45 * min(bi, ba), 0.45 * L)
    return max(min(r_in, 0.45 * (r1 - r0)), 0.0)


def _spule(grad):
    # Die Spule ist ein BUENDEL unter dem Polschuh, kein Film am ganzen Kern:
    # Anfang und Ende kommen aus `ema_eesm_cad`, die Breiten dort dazu.
    r0 = K["r_spule_innen_mm"]
    r1 = max(min(K["r_spule_aussen_mm"], K["r_kern_aussen_mm"] - UEBERLAPP),
             r0 + 0.6)
    bi, ba = K["b_kern_spuleanfang_mm"], K["b_kern_spulenende_mm"]
    # ZWEI Dicken: bei der Rechteckspule gleich, bei der ausgefuellten innen
    # duenner -- die Polteilung schrumpft nach innen, also der Platz neben dem
    # Kern auch. Axial zaehlt die groessere (das ist der Wickelkopf).
    ds_i = K.get("d_spule_innen_mm", K["d_spule_mm"])
    ds_a = K.get("d_spule_aussen_mm", K["d_spule_mm"])
    ds, sp = max(ds_i, ds_a), 0.05

    def _prisma(ri, ra, b_i, b_a, h, z):
        def _wire(zz):
            p = [App.Vector(ri, -b_i / 2.0, zz), App.Vector(ra, -b_a / 2.0, zz),
                 App.Vector(ra, b_a / 2.0, zz), App.Vector(ri, b_i / 2.0, zz)]
            return Part.makePolygon(p + [p[0]])
        return Part.makeLoft([_wire(z), _wire(z + h)], True)

    # Innenradius = halbe Kernbreite quer, gedeckelt auf die halbe Kernhoehe;
    # der Aussenradius ist um die Spulendicke groesser, dann sind die beiden
    # Konturen ueberall gleich weit auseinander -- das ist die Wicklung.
    r_in = _spulenradius()
    aussen = _prisma(r0, r1, bi + 2 * ds_i, ba + 2 * ds_a, L + 2 * ds, Z0 - ds)
    innen = _prisma(r0 - 1.0, r1 + 1.0,
                    _b_kern_bei(r0 - 1.0) + 2 * sp,
                    _b_kern_bei(r1 + 1.0) + 2 * sp, L + 2 * sp, Z0 - sp)
    # Der AEUSSERE Radius ist nicht einfach `r_in + ds`: er muss auf den
    # Aussenumriss passen. Bei der ausgefuellten Spule war `r_in + ds` = 16,03
    # und die halbe Aussenbreite ebenfalls 16,03 -- ein Radius so gross wie die
    # halbe Breite entartet, OCC meldete "BRep_API: command not done" und die
    # Spule blieb eckig. Gedeckelt auf 0,45 der kleinsten Abmessung gelingt er.
    _ra = min(r_in + min(ds_i, ds_a),
              0.45 * min(bi + 2 * ds_i, ba + 2 * ds_a, r1 - r0))
    aussen = _runden(aussen, _ra, "aussen")
    innen = _runden(innen, r_in, "innen")
    s = aussen.cut(innen)
    s.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), grad)
    return s


def _spulentasche(grad):
    # Der Koerper, der GESCHNITTEN wird -- nicht die Spule selbst.
    #
    # Zwei Unterschiede, und beide hat das Bild gezeigt:
    #
    #  * Sie reicht radial bis unter den POLSCHUH (`r_kern_aussen`), nicht nur
    #    bis zur Spulenoberkante. Der Schuh ist der Querbalken des T; darunter
    #    darf kein Eisen stehenbleiben, sonst sitzt die Wicklung in einer
    #    Nische statt unter ihrem Ueberstand.
    #  * Sie ist NICHT gerundet. Die Rundung gehoert dem Draht, der um den Kern
    #    laeuft -- die Tasche im Blech ist gestanzt und hat oben eine Kante.
    #    Eine gerundete Tasche liesse ausgerechnet unter dem Schuh einen
    #    Eisenwulst stehen.
    #  * Sie reicht seitlich bis unter die SCHUHKANTE, nicht nur bis zur
    #    Spule. Der Schuh ist unten ein Bogen, die Tasche oben eine Ebene --
    #    am Taschenrand tauchte der Bogen gemessen 1,85 mm unter die Ebene und
    #    blieb als Keil aus Schuheisen stehen. Bis zur Kante geschnitten
    #    bekommt der Schuh eine FLACHE Unterseite, und genau so sitzt eine
    #    Erregerspule: sie stuetzt sich flaechig gegen den Ueberstand ab.
    #  * Sie endet unten dort, wo die Spule endet, und NICHT an der Bohrung.
    #    Der Zwischenpolraum darunter ist ohnehin leer -- dort steht gar kein
    #    Koerper. Bis zur Bohrung durchgezogen wuerde die Tasche dagegen die
    #    NACHBARPOLE wegschneiden: ihre halbe Breite ist 17,6 mm, die halbe
    #    Polteilung an der Bohrung aber nur 7,9 mm, und genau dort ueberdecken
    #    sich die Koerper zur Nabe.
    r0 = K["r_spule_innen_mm"] - ISOLIERLUFT
    # Die Kernbreiten AN r0 UND r1, ausgewertet auf der Kerngeraden -- mit
    # einer anderen Neigung schnitte der Innenschneider beim kegeligen Pol in
    # den Kern hinein (gemessen 102 mm3 bei 2p = 6).
    ba = K["b_kern_aussen_mm"]
    ds_i = K.get("d_spule_innen_mm", K["d_spule_mm"]) + ISOLIERLUFT
    ds_a = K.get("d_spule_aussen_mm", K["d_spule_mm"]) + ISOLIERLUFT
    ds = max(ds_i, ds_a)
    sp = 0.05
    _halb = min((K["b_schuh_mm"] / 2.0) / max(K["r_rotor_mm"], 1e-9),
                0.5 * math.pi - 1e-3)

    # ── Wie hoch darf die Taschendecke liegen? ────────────────────────────
    #
    # Sie ist eine EBENE, der Laeuferrand ein Kreis. Ueber der Breite, die die
    # Spule braucht (`ya0`), muss oberhalb der Decke noch Eisen stehen, sonst
    # schneidet die Tasche den Polschuh in Stuecke -- gemessen bei 2p = 2
    # (halber Schuhwinkel 49,5 Grad): vier abgetrennte Schuhspitzen zu je
    # 23.347 mm3. Also `r1 <= sqrt(r_rotor^2 - ya0^2) - TASCHE_STEG_MM`.
    # Bei acht Polen bindet das nicht (91,6 gegen 84,98 mm), bei zwei Polen
    # senkt es die Decke von 84,98 auf 82,50 mm -- der Schuh behaelt dort
    # seinen Bogen, statt flach abgeschnitten zu werden.
    ya0 = ba / 2.0 + ds_a
    r1 = min(K["r_kern_aussen_mm"],
             math.sqrt(max(K["r_rotor_mm"] ** 2 - ya0 ** 2, 1.0))
             - TASCHE_STEG_MM)
    # Aber niemals so tief, dass die Spule wieder im Eisen steckt: die Decke
    # liegt mindestens eine Isolierluft ueber ihrer Oberkante (bei 2p = 2
    # fehlten sonst 0,03 mm und es blieben 25,95 mm3 Kupfer im Blech).
    r1 = max(r1, min(K["r_kern_aussen_mm"],
                     K["r_spule_aussen_mm"] + ISOLIERLUFT), r0 + 1.0)
    bi = _b_kern_bei(r0)
    # Halbe Taschenbreite an der Schuhunterseite: die Schuhflanke ist eine
    # radiale Ebene, also y = r1 * tan(halber Schuhwinkel). `tan` waechst dabei
    # ueber alle Grenzen (bei 2p = 2 auf 97 mm), deshalb derselbe Steg-Deckel
    # noch einmal.
    y_schuh_max = math.sqrt(
        max(K["r_rotor_mm"] ** 2 - (r1 + TASCHE_STEG_MM) ** 2, 0.0))
    ya = max(ya0, min(r1 * math.tan(_halb) + TASCHE_UEBERSTAND_MM,
                      y_schuh_max))
    yi = max(bi / 2.0 + ds_i, ya - (r1 - r0) * math.tan(_halb))

    def _prisma(ri, ra, b_i, b_a, h, z):
        def _wire(zz):
            p = [App.Vector(ri, -b_i / 2.0, zz), App.Vector(ra, -b_a / 2.0, zz),
                 App.Vector(ra, b_a / 2.0, zz), App.Vector(ri, b_i / 2.0, zz)]
            return Part.makePolygon(p + [p[0]])
        return Part.makeLoft([_wire(z), _wire(z + h)], True)

    aussen = _prisma(r0, r1, 2 * yi, 2 * ya, L + 2 * ds, Z0 - ds)
    # ── Das LOCH ist dasselbe wie das der Spule, einschliesslich Rundung ──
    #
    # Sonst blieb genau dort Eisen stehen, wo die Spule um die Ecke laeuft:
    # ihr Innenloch ist gerundet (der Draht kann nicht scharf knicken), der
    # gestanzte Kern war eckig, und an den vier Ecken steckte das Kupfer im
    # Blech -- gemessen 4867 mm³ je Polfolge. Mit demselben Loch schneidet die
    # Tasche dem Polkern genau diese Rundung an, und die braucht er ohnehin.
    innen = _prisma(r0 - 1.0, r1 + 1.0,
                    _b_kern_bei(r0 - 1.0) + 2 * sp,
                    _b_kern_bei(r1 + 1.0) + 2 * sp, L + 2 * sp, Z0 - sp)
    # Der Radius wird mit den ZAHLEN DER SPULE gerechnet, nicht mit denen der
    # Tasche. Beide Formeln sahen gleich aus und liefen doch um Hundertstel
    # auseinander (die Tasche misst die Kernbreite an ihrem eigenen Anfang,
    # 0,3 mm weiter innen) -- gemessen blieben 26,33 mm3 Kupfer im Blech.
    innen = _runden(innen, _spulenradius(), "tasche_innen")
    s = aussen.cut(innen)
    s.rotate(App.Vector(0, 0, 0), App.Vector(0, 0, 1), grad)
    return s


sp_n, sp_s, spulen = [], [], []
for i in range(int(K["poles"])):
    _s = _spule(360.0 * i / int(K["poles"]))
    spulen.append(_s)
    (sp_n if i % 2 == 0 else sp_s).append(_s)

# ── Die Spule wird aus dem LAEUFER HERAUSGESCHNITTEN ───────────────────────
#
# Vorher wurden beide Koerper nebeneinander gebaut und mussten sich von selbst
# vertragen -- taten sie nicht: Trapezueberblendung, Rundung und
# POL_UEBERLAPP treffen sich nicht auf den Mikrometer, und heraus kam ein
# Kupfer, das im Eisen steckt. Gemeldet als „die Wicklung kollidiert mit dem
# Rotor".
#
# Jetzt entscheidet EIN Koerper: der Laeufer bekommt die Spule (samt
# Isolierluft) abgezogen. Damit KANN es keine Durchdringung mehr geben -- das
# ist derselbe Weg, den die Magnettaschen seit jeher gehen (`pocket_shapes`
# werden aus dem Rotor geschnitten, nicht danebengelegt).
_vol_vor = laeufer.Volume
for _i in range(int(K["poles"])):
    laeufer = laeufer.cut(_spulentasche(360.0 * _i / int(K["poles"])))
laeufer = laeufer.removeSplitter()
# Was der Schnitt WEGGENOMMEN hat, ist genau das Eisen, in dem die Spule
# vorher steckte. Diese Zahl ist die Gegenprobe zum „keine Durchdringung":
# waere sie null, haette der Schnitt nichts getan und das gruene Haekchen
# saehe gut aus, ohne etwas zu bedeuten.
print("SPULENSCHNITT:%.2f" % (_vol_vor - laeufer.Volume))

_add("Rotor", laeufer, (0.55, 0.57, 0.60))
_add("Erregerspulen_N", Part.makeCompound(sp_n), (0.80, 0.42, 0.18))
_add("Erregerspulen_S", Part.makeCompound(sp_s), (0.35, 0.55, 0.85))

# ── 6. Daempferstaebe und ihre Kurzschlussringe ─────────────────────────────
if lagen:
    ue = 0.05 * L
    dmp = [Part.makeCylinder(D["d_stab_mm"] / 2.0, L + 2 * ue,
                             App.Vector(cx, cy, Z0 - ue)) for cx, cy in lagen]
    a_ring = D.get("A_ring_mm2") or 0.0
    if a_ring > 0:
        tax = 3.0 * (D["d_stab_mm"] / 2.0)
        wr = max(a_ring / max(tax, 1e-9), 1.0)
        ra = D["r_ring_mm"] + wr / 2.0
        ri = max(D["r_ring_mm"] - wr / 2.0, 0.5)
        for zz in (Z0 - ue - tax, Z0 + L + ue):
            ring = Part.makeCylinder(ra, tax, App.Vector(0, 0, zz))
            ring = ring.cut(Part.makeCylinder(ri, tax + 2,
                                              App.Vector(0, 0, zz - 1)))
            dmp.append(ring)
    _add("Daempferkaefig", Part.makeCompound(dmp), (0.72, 0.45, 0.20))

# ── 7. Schleifringe: zwei, fuer den Erregerkreis ────────────────────────────
ringe = []
zr = Z0 + L + 12.0
for i in range(int(RG["n_ringe"])):
    ro = Part.makeCylinder(RG["d_ring_mm"] / 2.0, RG["b_ring_mm"],
                           App.Vector(0, 0, zr))
    ri = Part.makeCylinder(K["r_welle_mm"], RG["b_ring_mm"] + 2,
                           App.Vector(0, 0, zr - 1))
    ringe.append(ro.cut(ri))
    zr += RG["b_ring_mm"] + RG["spalt_mm"]
_add("Schleifringe", Part.makeCompound(ringe), (0.75, 0.60, 0.25))

doc.recompute()

# ── 8. Nachmessen — am KOERPER, nicht am Parameter ──────────────────────────
mess = {{}}
for name, sh in teile.items():
    rmax = rmin = None
    for v in sh.Vertexes:
        r = math.hypot(v.X, v.Y)
        rmax = r if rmax is None else max(rmax, r)
        rmin = r if rmin is None else min(rmin, r)
    # Wieviele Flaechen GEKRUEMMT sind. Das ist die Probe auf „oval": eine
    # Spule aus lauter Ebenen ist eckig, egal wie das Bild aussieht.
    rund = 0
    for f in sh.Faces:
        if f.Surface.__class__.__name__ not in ("Plane",):
            rund += 1
    mess[name] = {{"solids": len(sh.Solids), "vol_mm3": round(sh.Volume, 1),
                  "r_max": round(rmax or 0, 3), "r_min": round(rmin or 0, 3),
                  "faces": len(sh.Faces), "rund": rund,
                  "gueltig": bool(sh.isValid())}}
# Die Probe: was steckt in was? `common().Volume` ueber alle Paare der
# benannten Koerper. Eine Zeichnung, die man nur ansieht, ist eine Behauptung
# -- und genau hier ist dreimal etwas uebersehen worden.
kollision = {{}}
_namen = [n for n in teile if n not in ("Schleifringe",)]
for _i in range(len(_namen)):
    for _j in range(_i + 1, len(_namen)):
        _a, _b = _namen[_i], _namen[_j]
        try:
            _v = teile[_a].common(teile[_b]).Volume
        except Exception:
            _v = -1.0
        if _v > 0.01:
            kollision[_a + " x " + _b] = round(_v, 2)
print("KOLLISION:" + json.dumps(kollision))
print("MESS:" + json.dumps(mess))
if RUND_GESCHEITERT:
    print("RUND_FEHLER:" + json.dumps(RUND_GESCHEITERT[:4]))

doc.saveAs(r"{fcstd}")
print("SAVED:" + r"{fcstd}")
try:
    Part.export([doc.getObject(n) for n in
                 ["Rotor", "Welle", "Erregerspulen_N", "Erregerspulen_S"]
                 + (["Daempferkaefig"] if lagen else []) + ["Schleifringe"]],
                r"{step}")
    print("STEP_SAVED:" + r"{step}")
except Exception as e:
    print("STEP_FAIL:" + str(e))
print("CAD_VOLUME:%.2f" % teile["Rotor"].Volume)
print("CAD_SUCCESS")
'''


# ── Bericht ─────────────────────────────────────────────────────────────────

_OEFFNE_MAKRO = """# erzeugt von bau_eesm.py
import FreeCAD as App
import FreeCADGui as Gui

doc = App.openDocument(r"@@PFAD@@")
Gui.ActiveDocument = Gui.getDocument(doc.Name)


def _zeigen():
    try:
        gdoc = Gui.getDocument(doc.Name)
        for obj in doc.Objects:
            vp = gdoc.getObject(obj.Name) if gdoc else None
            if vp is not None:
                try:
                    vp.Visibility = True
                except Exception:
                    pass
        v = Gui.activeDocument().activeView()
        v.viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
    except Exception as e:
        App.Console.PrintWarning("zeigen: " + str(e) + chr(10))


_zeigen()
try:
    from PySide6.QtCore import QTimer
except ImportError:
    try:
        from PySide2.QtCore import QTimer
    except ImportError:
        QTimer = None
if QTimer is not None:
    QTimer.singleShot(400, _zeigen)
    QTimer.singleShot(1200, _zeigen)
"""


def in_freecad_oeffnen(fcstd: str) -> str:
    """Die gebaute Datei in der FreeCAD-OBERFLAECHE oeffnen.

    Kopfloses Speichern laesst die ViewProvider unverbunden: wer die Datei dann
    in der GUI oeffnet, sieht einen leeren Bildschirm neben einem vollen
    Modellbaum. Deshalb dasselbe Makro wie ``server.open_freecad`` -- die
    Sichtbarkeit einmal sofort setzen und zweimal ueber den Qt-Zeitgeber
    nachziehen, wenn die Ereignisschleife durchgelaufen ist. `@@PFAD@@` wird
    gesetzt statt formatiert: das Makro ist voller geschweifter Klammern.
    """
    import subprocess
    import freecad_runner

    makro = os.path.join(os.path.dirname(fcstd), "_oeffne_eesm.FCMacro")
    with open(makro, "w", encoding="utf-8") as f:
        f.write(_OEFFNE_MAKRO.replace("@@PFAD@@", fcstd))

    umg = freecad_runner.child_env()
    umg.setdefault("DISPLAY", os.environ.get("DISPLAY", ":1"))
    subprocess.Popen(
        ["pixi", "run", "--manifest-path",
         os.path.join(freecad_runner.FREECAD_ROOT, "pixi.toml"), "--",
         "build/release/bin/FreeCAD", makro],
        cwd=freecad_runner.FREECAD_ROOT, env=umg,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return makro


# ── Ein REFERENZBILD ausmessen ──────────────────────────────────────────────
#
# Drei Runden „der Rotor ist noch falsch" haben gezeigt, dass Beschreibungen
# hier nicht tragen: „zu breit", „passt nicht", „falsche Richtung" sind wahr
# und trotzdem nicht rechenbar. Ein Bild eines gebauten Laeufers ist dagegen
# eine Messung -- man muss sie nur vornehmen.
#
# Gemessen wird ueber die FARBEN eines Schnittbildes (FEMM, Ansys, Lehrbuch):
# Eisen, Kupfer, Luft. Heraus kommen VERHAELTNISSE und keine Millimeter -- ein
# Bild hat keinen Massstab, aber Verhaeltnisse sind genau das, was hier
# entschieden wird (Polbedeckung, Kernanteil, Nabenanteil).

FARBKLASSEN = {
    # name: (Pruefung auf (r,g,b) in 0..255)
    "eisen_laeufer": lambda r, g, b: r > 240 and 150 < g < 235 and 150 < b < 235,
    "eisen_staender": lambda r, g, b: r > 200 and g < 200 and b > 200,
    "kupfer": lambda r, g, b: g > 200 and r < 200 and b < 200,
}


def messe_bild(pfad: str) -> dict:
    """Verhaeltnisse eines Schnittbildes -- Nabe, Pol, Schuh, Wicklung.

    Keine Millimeter: ein Bild hat keinen Massstab. Alles wird auf den
    LAEUFERRADIUS bezogen, und genau in diesen Groessen entscheidet man einen
    Schenkelpol.
    """
    import numpy as np
    from PIL import Image

    a = np.asarray(Image.open(pfad).convert("RGB")).astype(int)
    h, w, _ = a.shape
    r_, g_, b_ = a[:, :, 0], a[:, :, 1], a[:, :, 2]
    fe_l = (r_ > 240) & (g_ > 150) & (g_ < 235) & (b_ > 150) & (b_ < 235)
    fe_s = (r_ > 200) & (g_ < 200) & (b_ > 200)
    cu = (g_ > 200) & (r_ < 200) & (b_ < 200)

    ys, xs = np.nonzero(fe_l | fe_s | cu)
    if not len(xs):
        raise ValueError("keine erkennbaren Farbflaechen im Bild")
    cx, cy = (xs.min() + xs.max()) / 2.0, (ys.min() + ys.max()) / 2.0
    r_aussen = (xs.max() - xs.min()) / 2.0
    yy, xx = np.mgrid[0:h, 0:w]
    rr = np.hypot(xx - cx, yy - cy)
    th = np.degrees(np.arctan2(yy - cy, xx - cx)) % 360.0

    def fuellung(maske, r):
        band = (rr >= r - 0.6) & (rr < r + 0.6)
        n = band.sum()
        if n < 40:
            return 0.0, 0
        winkel = np.sort(th[band & maske])
        if len(winkel) < 3:
            return len(winkel) / n, 0
        luecken = int(np.sum(np.diff(winkel) > 3.0))
        bloecke = luecken + (0 if (winkel[0] < 2 and winkel[-1] > 358) else 1)
        return len(winkel) / n, bloecke

    # Der Laeuferradius: der aeusserste Radius mit nennenswertem Laeufereisen.
    r_laeufer = 0.0
    for r in range(int(r_aussen), 4, -1):
        if fuellung(fe_l, r)[0] > 0.15:
            r_laeufer = float(r)
            break
    if r_laeufer <= 0:
        raise ValueError("kein Laeufereisen erkannt")

    # Das Profil von innen nach aussen.
    prof = []
    for r in range(3, int(r_laeufer) + 1):
        f_fe, n_fe = fuellung(fe_l, r)
        f_cu, n_cu = fuellung(cu, r)
        prof.append((r, f_fe, n_fe, f_cu, n_cu))

    # Welle: innen, wo noch KEIN Laeufereisen steht.
    r_welle = 0.0
    for r, f_fe, _n, _c, _d in prof:
        if f_fe > 0.5:
            r_welle = float(r - 1)
            break
    # Nabe: solange das Eisen einen VOLLEN Ring bildet.
    r_nabe = r_welle
    for r, f_fe, _n, _c, _d in prof:
        if r <= r_welle:
            continue
        if f_fe > 0.90:
            r_nabe = float(r)
        elif r_nabe > r_welle:
            break
    # Pole: darueber. Polzahl aus der haeufigsten Blockzahl.
    import collections
    bl = collections.Counter(n for r, f, n, _c, _d in prof
                             if r > r_nabe and 0.1 < f < 0.9 and n > 1)
    poles = bl.most_common(1)[0][0] if bl else 0
    # Wicklung: das Band mit Kupfer im Laeufer.
    cu_r = [r for r, _f, _n, f_cu, n_cu in prof if f_cu > 0.05 and r > r_nabe]
    r_cu = (min(cu_r), max(cu_r)) if cu_r else (0, 0)
    # Koerper und Schuh trennt die WICKLUNG, nicht ein Schwellwert auf der
    # Fuellung: die Spule sitzt neben dem Koerper, ueber ihr faengt der Schuh
    # an. Ein Minimum-Kriterium fiel dagegen auf die abgeschraegte Polkante
    # herein und meldete einen Schuh der Hoehe null.
    import statistics as _st
    fe = {r: f for r, f, _n, _c, _d in prof}
    if r_cu[1] > r_cu[0]:
        r_schuh = float(r_cu[1]) + 1.0
        koerper = [fe[r] for r in range(int(r_cu[0]), int(r_cu[1]) + 1) if r in fe]
    else:
        r_schuh = r_nabe + 0.7 * (r_laeufer - r_nabe)
        koerper = [f for r, f in fe.items() if r_nabe < r < r_schuh]
    schuh = [f for r, f in fe.items() if r_schuh <= r <= r_laeufer - 1]
    f_koerper = _st.median(koerper) if koerper else 0.0
    f_schuh = _st.median(schuh) if schuh else f_koerper

    return {
        "bild": pfad,
        "poles": int(poles),
        "r_laeufer_px": r_laeufer,
        "r_welle_rel": round(r_welle / r_laeufer, 3),
        "r_nabe_rel": round(r_nabe / r_laeufer, 3),
        "polhoehe_rel": round((r_laeufer - r_nabe) / r_laeufer, 3),
        "schuhanteil": round((r_laeufer - r_schuh) / max(r_laeufer - r_nabe, 1e-9), 3),
        "polbedeckung": round(f_schuh, 3),
        "kernanteil": round(f_koerper / max(f_schuh, 1e-9), 3),
        "spule_rel": (round(r_cu[0] / r_laeufer, 3), round(r_cu[1] / r_laeufer, 3)),
        "spulenhoehe_rel": round((r_cu[1] - r_cu[0]) / max(r_laeufer - r_nabe, 1e-9), 3),
        "kupferfuellung": round(max((f for r, _f, _n, f, _d in
                                     [(p[0], p[1], p[2], p[3], p[4]) for p in prof]
                                     if r_cu[0] <= r <= r_cu[1]), default=0.0), 3),
    }


def vergleich_tabelle(mess: dict, k: dict, geom: dict) -> str:
    """Das Bild gegen die gerechnete Auslegung -- in denselben Verhaeltnissen."""
    import math
    r_l = float(k["r_rotor_mm"])
    poles = int(k["poles"])
    tau_schuh = 2.0 * math.pi * r_l / max(poles, 1)
    eigen = {
        "poles": poles,
        "r_welle_rel": float(k["r_welle_mm"]) / r_l,
        "r_nabe_rel": float(k["r_joch_aussen_mm"]) / r_l,
        "polhoehe_rel": (r_l - float(k["r_joch_aussen_mm"])) / r_l,
        "schuhanteil": float(k["h_s2_mm"]) / max(float(k["h_s2_mm"])
                                                 + float(k["h_bd_mm"]), 1e-9),
        "polbedeckung": float(k["w_s2_mm"]) / tau_schuh,
        "kernanteil": float(k["w_bd_mm"]) / max(float(k["w_s2_mm"]), 1e-9),
        "spulenhoehe_rel": float(k["h_spule_mm"]) / max(r_l - float(k["r_joch_aussen_mm"]), 1e-9),
    }
    namen = {
        "poles": "Polzahl",
        "r_welle_rel": "Welle / Laeuferradius",
        "r_nabe_rel": "Nabe (Joch) / Laeuferradius",
        "polhoehe_rel": "Polhoehe / Laeuferradius",
        "schuhanteil": "Schuhhoehe / Polhoehe   h_s2",
        "polbedeckung": "Polbedeckung  w_s2/tau",
        "kernanteil": "Kernanteil   w_bd/w_s2",
        "spulenhoehe_rel": "Spulenhoehe / Polhoehe",
    }
    z = ["", "  Bild gegen Rechnung — VERHAELTNISSE, weil ein Bild keinen "
             "Massstab hat:", "",
         "    %-32s %8s %8s   %s" % ("", "Bild", "hier", "Abweichung")]
    for s, n in namen.items():
        b, e = mess.get(s), eigen.get(s)
        if b is None or e is None:
            continue
        if s == "poles":
            z.append("    %-32s %8d %8d   %s" % (n, b, e,
                     "gleich" if b == e else "VERSCHIEDEN"))
            continue
        d = (e - b) / b * 100.0 if b else float("nan")
        marke = "  <<<" if abs(d) > 25 else ""
        z.append("    %-32s %8.3f %8.3f   %+6.0f %%%s" % (n, b, e, d, marke))
    z.append("")
    z.append("    (<<< = mehr als ein Viertel daneben)")
    return "\n".join(z)



_GEOM_FUER_BERICHT: dict = {}


def bericht(m: dict, mess: dict | None) -> str:
    k, d, b, rg = m["koerper"], m["daempfer"], m["befestigung"], m["ringe"]
    poles = int(k["poles"])
    z = []
    z.append(f"Schenkelpollaeufer — {poles} Pole, Paket {m['axial']:.0f} mm")
    z.append("")
    z.append("  Radien (mm)          Welle %6.2f  Joch %6.2f  Kernkopf %6.2f  Rand %6.2f"
             % (k["r_welle_mm"], k["r_joch_aussen_mm"],
                k["r_kern_aussen_mm"], k["r_rotor_mm"]))
    tau_j = 2 * math.pi * k["r_joch_aussen_mm"] / poles
    tau_k = 2 * math.pi * k["r_kern_aussen_mm"] / poles
    z.append("")
    z.append("  Die Polteilung SCHRUMPFT nach innen — dort ist der Wickelraum eng:")
    z.append("    am Joch      Teilung %6.2f   Kern %6.2f   frei %6.2f mm"
             % (tau_j, k["b_kern_innen_mm"], tau_j - k["b_kern_innen_mm"]))
    z.append("    unterm Schuh Teilung %6.2f   Kern %6.2f   frei %6.2f mm"
             % (tau_k, k["b_kern_aussen_mm"], tau_k - k["b_kern_aussen_mm"]))
    _richtung = ("zum Joch hin SCHMALER (folgt der Teilung)"
                 if k["b_kern_innen_mm"] < k["b_kern_aussen_mm"] - 1e-6
                 else ("zum Joch hin BREITER (gegen die Teilung)"
                       if k["b_kern_innen_mm"] > k["b_kern_aussen_mm"] + 1e-6
                       else "durchgehend gleich breit"))
    z.append(f"    Kegel: {k['spulenform']} — {_richtung}")
    z.append("")
    # In den Bezeichnungen der Literatur -- damit eine Auslegung ohne Umrechnen
    # neben einer Veroeffentlichung steht. Dieselben Zahlen, andere Namen.
    z.append("  In den Symbolen der Literatur (Rotor):")
    z.append("    w_s2 %7.2f   h_s2 %6.2f      (Polschuh: Breite, Hoehe)"
             % (k["w_s2_mm"], k["h_s2_mm"]))
    z.append("    w_bd %7.2f   h_bd %6.2f      (Polkoerper: Breite, Hoehe)"
             % (k["w_bd_mm"], k["h_bd_mm"]))
    try:
        import ema_wicklung
        _n = ema_wicklung.nutgeometrie(_GEOM_FUER_BERICHT)
        z.append("  In den Symbolen der Literatur (Staender):")
        z.append("    D_o  %7.2f   D_i  %6.2f      (Aussen-, Bohrungsdurchmesser)"
                 % (_GEOM_FUER_BERICHT["statorOD"], _GEOM_FUER_BERICHT["statorID"]))
        # `nutgeometrie` fuehrt die Zahnbreite nur in METERN (`zahn_breite_m`);
        # ein `zahn_breite_mm` gibt es dort nicht, und der KeyError verschwand
        # stillschweigend im `except` -- die halbe Staenderzeile fehlte.
        z.append("    w_t  %7.2f   h_s  %6.2f      (Zahnbreite, Nuthoehe)"
                 % (_n["zahn_breite_m"] * 1000.0, _n["nut_tiefe_mm"]))
        z.append("    b_s0 %7.2f                    (Nutoeffnung = Nutbreite:"
                 " dieses Werkzeug zeichnet OFFENE Nuten, es gibt keinen"
                 " Nutverschluss)" % _n["nut_breite_mm"])
    except Exception as _e:                                  # noqa: BLE001
        z.append("    (Staendermasse nicht lesbar: %s: %s)"
                 % (type(_e).__name__, _e))
    z.append("")
    z.append("  Polschuh  %6.2f mm breit, %5.2f mm hoch" % (k["b_schuh_mm"], k["h_schuh_mm"]))
    z.append("  Spule     2 x %5.2f…%5.2f mm dick x %5.2f mm hoch, r %6.2f…%6.2f"
             % (k.get("d_spule_innen_mm", k["d_spule_mm"]),
                k.get("d_spule_aussen_mm", k["d_spule_mm"]),
                k["h_spule_mm"], k["r_spule_innen_mm"], k["r_spule_aussen_mm"]))
    z.append("            Schlankheit h/d = %.1f (ein Buendel, kein Film — "
             "hoechstens %.1f)" % (k["spule_schlankheit"],
                                   __import__("ema_eesm_cad").SPULE_SCHLANKHEIT_MAX))
    z.append("  Fuellung  %s (Polbedeckung wirksam %.3f%s)"
             % (k.get("fuellung", "vorgabe"), k.get("bedeckung_eff", 0.0),
                ", gewachsen" if k.get("bedeckung_eff", 0.0)
                > float(k.get("polbedeckung_vorgabe", k.get("bedeckung_eff", 0.0)))
                + 1e-9 else ""))
    z.append("  Wickelraum %6.0f mm² gefordert, %6.0f mm² gezeichnet"
             % (k["A_wickelraum_mm2"], 2 * k["d_spule_mm"] * k["h_spule_mm"]))
    z.append("  Polkern   B = %.2f T von %.2f T (%s) — %s"
             % (k["B_kern_T"], k["B_kern_grenze_T"], k["blech"],
                "SAETTIGT" if k["kern_saettigt"] else "ok"))
    z.append("  Nabe      %.2f mm hoch (bis r %.2f, wo sich zwei Polkoerper "
             "treffen)" % (k["h_nabe_mm"], k["r_nabe_mm"]))
    z.append("            der Fluss verlangt %.2f mm — %s;  B = %s T von %.2f T"
             % (k["h_joch_fluss_mm"],
                "reicht" if k["nabe_reicht"] else "REICHT NICHT",
                ("%.2f" % k["B_nabe_T"]) if k["B_nabe_T"] is not None else "—",
                k["B_kern_grenze_T"]))
    if not k["nabe_zusammen"]:
        z.append("            ⚠ die Polkoerper beruehren sich an der Bohrung "
                 "NICHT — der Laeufer zerfaellt in Einzelarme")
    z.append("  bindende Schranke: %s   —   passt: %s"
             % (k["bindend"], "ja" if k["passt"] else "NEIN"))
    if not k["passt"]:
        z.append("    " + k["grund"])
    z.append("  Ecke im Laeufer: Kern %6.2f  Spule %6.2f  (Rand %6.2f) -> %s"
             % (k["r_ecke_kern_mm"], k["r_ecke_spule_mm"], k["r_rotor_mm"],
                "drin" if k["im_laeufer"] else "DRAUSSEN"))
    if b:
        z.append("")
        z.append("  Polbefestigung (%s): %.2f kg je Pol, %.1f kN bei %.0f 1/min"
                 % (b["art"], b["m_pol_kg"], b["F_flieh_kN"], b["rpm"]))
        z.append("    Sicherheit %.2f (Ziel %.1f), zulaessig bis %.0f 1/min — %s"
                 % (b["SF"], b["SF_ziel"], b["n_zulaessig_1pmin"],
                    "OK" if b["haelt"] else "ABGELEHNT"))
    if d.get("aktiv"):
        z.append("")
        z.append("  Daempferkaefig: %d x %.2f mm je Pol, Teilung %.2f mm (%.2f x Nut) — %s"
                 % (d["n_stab_je_pol"], d["d_stab_mm"], d["teilung_mm"],
                    d["teilungsverhaeltnis"], "passt" if d["passt"] else "PASST NICHT"))
        if d["grund"]:
            z.append("    " + d["grund"])
    z.append("")
    z.append("  Schleifringe: %d x Ø%.1f mm, %.1f mm breit, v = %s"
             % (rg["n_ringe"], rg["d_ring_mm"], rg["b_ring_mm"],
                "nicht geprueft" if rg["v_ring_mps"] is None
                else "%.1f m/s (Grenze %.0f)" % (rg["v_ring_mps"], rg["v_grenze_mps"])))
    if mess:
        z.append("")
        z.append("  GEBAUT (am Koerper gemessen, nicht am Parameter):")
        for name, mm in mess.items():
            warn = ""
            if name == "Rotor" and mm["solids"] != 1:
                warn = "  <-- KEIN einzelner Festkoerper!"
            if mm["r_max"] > k["r_rotor_mm"] + 0.01 and name not in (
                    "Schleifringe", "Welle"):
                warn += "  <-- ragt ueber den Laeuferrand"
            z.append("    %-16s %d Solid(s) %9.0f mm³  r %6.2f…%6.2f  "
                     "%d Flaechen (%d gekruemmt)  %s%s"
                     % (name, mm["solids"], mm["vol_mm3"], mm["r_min"],
                        mm["r_max"], mm.get("faces", 0), mm.get("rund", 0),
                        "gueltig" if mm["gueltig"] else "UNGUELTIG", warn))
    return "\n".join(z)


# ── Ablauf ──────────────────────────────────────────────────────────────────

def _geom(args) -> tuple:
    import cae_cli
    p = cae_cli.frischer_payload()
    g = dict(p["geom"])
    g["machineType"] = "eesm"
    g["erregerSpuleForm"] = args.spule
    g["erregerSpuleFuellung"] = args.fuellung
    g["daempferkaefig"] = "ja" if args.daempfer else "nein"
    if args.p:
        g["p"] = args.p
    if args.polbedeckung:
        g["polbedeckung"] = args.polbedeckung
    g["rpm_to"] = args.rpm
    for zuweisung in args.set or []:
        schluessel, _, wert = zuweisung.partition("=")
        try:
            g[schluessel] = json.loads(wert)
        except json.JSONDecodeError:
            g[schluessel] = wert
    return g, float(args.axial or p["axial_len"])


def einmal(args, g: dict, axial: float, marke: str) -> int:
    global _GEOM_FUER_BERICHT
    _GEOM_FUER_BERICHT = g
    m = masse(g, axial)
    mess = None
    if not args.nur_zahlen:
        import freecad_runner
        os.makedirs(args.aus, exist_ok=True)
        fcstd = os.path.join(args.aus, f"eesm_{marke}.FCStd")
        step = os.path.join(args.aus, f"eesm_{marke}.step")
        code = skript(m, fcstd, step)
        erg = freecad_runner.run_freecad_script(code, timeout=args.timeout)
        rund_fehler, kollision, schnitt = [], None, None
        for zeile in (erg.get("stdout") or "").splitlines():
            if zeile.startswith("MESS:"):
                mess = json.loads(zeile[5:])
            elif zeile.startswith("RUND_FEHLER:"):
                rund_fehler = json.loads(zeile[12:])
            elif zeile.startswith("KOLLISION:"):
                kollision = json.loads(zeile[10:])
            elif zeile.startswith("SPULENSCHNITT:"):
                schnitt = float(zeile[14:])
        if not erg.get("cad_success"):
            print(bericht(m, mess))
            print("\nFreeCAD hat NICHT gebaut:")
            print((erg.get("stderr") or erg.get("stdout") or "")[-1800:])
            return 1
        print(bericht(m, mess))
        if kollision is not None:
            if kollision:
                print("  \u26A0 DURCHDRINGUNG (gemessen ueber common().Volume):")
                for paar, vol in sorted(kollision.items(),
                                        key=lambda x: -x[1]):
                    print("      %-34s %10.2f mm³" % (paar, vol))
            else:
                print("  \u2713 keine Durchdringung — alle Koerper gemessen "
                      "(common().Volume = 0)")
            if schnitt is not None:
                print("      Gegenprobe: der Spulenschnitt hat %.0f mm³ Eisen "
                      "entfernt — genau das Eisen," % schnitt)
                print("      in dem die Wicklung vorher steckte. Waere es "
                      "null, hiesse das gruene Haekchen nichts.")
        for f in rund_fehler:
            print("  \u26A0 Spule nicht gerundet — " + f)
        print(f"\n  {fcstd}\n  {step}")
        if args.gui:
            in_freecad_oeffnen(fcstd)
            print("  -> in FreeCAD geoeffnet (DISPLAY=%s)"
                  % os.environ.get("DISPLAY", ":1"))
    else:
        print(bericht(m, None))
    if args.referenzbild:
        try:
            _mess = messe_bild(args.referenzbild)
            print(vergleich_tabelle(_mess, m["koerper"], g))
        except Exception as _e:                              # noqa: BLE001
            print("  Referenzbild nicht auswertbar: %s: %s"
                  % (type(_e).__name__, _e))
    if args.bild:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import ema_pipeline
        os.makedirs(args.aus, exist_ok=True)
        fig, ax = plt.subplots(figsize=(7, 7), dpi=120)
        ema_pipeline.render_cross_section(dict(g, axialLen=axial), ax,
                                          beschriftung=True)
        p = os.path.join(args.aus, f"eesm_{marke}.png")
        fig.savefig(p, bbox_inches="tight")
        plt.close(fig)
        print(f"  {p}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Nur den EESM-Laeufer bauen und nachmessen.")
    ap.add_argument("--spule", choices=["rechteck", "kegel"], default="rechteck")
    ap.add_argument("--p", type=int, default=0, help="Polpaare")
    ap.add_argument("--polbedeckung", type=float, default=0.0)
    ap.add_argument("--fuellung", choices=("vorgabe", "max"), default="vorgabe",
                    help="was die Erregerspule bemisst: die Stromdichte "
                         "(vorgabe) oder der gezeichnete Bauraum (max)")
    ap.add_argument("--daempfer", action="store_true")
    ap.add_argument("--rpm", type=float, default=6000.0,
                    help="Drehzahl fuer die Polbefestigung (0 = nicht pruefen)")
    ap.add_argument("--axial", type=float, default=0.0)
    ap.add_argument("--set", action="append", metavar="KEY=WERT")
    ap.add_argument("--aus", default=AUS_VORGABE)
    ap.add_argument("--bild", action="store_true")
    ap.add_argument("--nur-zahlen", action="store_true", dest="nur_zahlen")
    ap.add_argument("--vergleich", action="store_true",
                    help="beide Spulenformen nacheinander")
    ap.add_argument("--referenzbild", metavar="PNG",
                    help="ein Schnittbild ausmessen und dagegenhalten")
    ap.add_argument("--gui", action="store_true",
                    help="die gebaute Datei danach in FreeCAD oeffnen")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args(argv)

    formen = ["rechteck", "kegel"] if args.vergleich else [args.spule]
    rc = 0
    for f in formen:
        args.spule = f
        g, axial = _geom(args)
        if len(formen) > 1:
            print("\n" + "=" * 70)
            print(f"  Spulenform: {f}")
            print("=" * 70)
        rc |= einmal(args, g, axial, f + ("_daempfer" if args.daempfer else ""))
    return rc


if __name__ == "__main__":
    sys.exit(main())
