"""ASM-Feld harmonisch in 3-D (Elmer ``WhitneyAVHarmonicSolver``) -- Stufe D.

Wozu, wenn Stufe B schon rechnet
---------------------------------

Weil Stufe B eine Sache **grundsaetzlich** nicht kann und das auch sagt: ein
2-D-Querschnitt hat keine Stirnseite. Die Kaefigstaebe sind dort ideal
kurzgeschlossen, der **Kurzschlussring fehlt**. Die analytische Stufe schlaegt
ihn rechnerisch auf. Bis zu dieser Stufe stand dort eine **Konstante**
(``KURZSCHLUSSRING_ZUSCHLAG = 0,20``), gesetzt und nie gemessen; heute rechnet
``ema_asm.kurzschlussring_zuschlag`` ihn aus der Geometrie, und genau diese
Stufe hat die Konstante abgeloest.

Diese Stufe misst sie. Gerechnet wird dieselbe Maschine, mit demselben
Querschnitt (``ema_em2d_harm.quer_flaechen`` -- eine Geometrie, nicht zwei),
aber in die Laenge gezogen und mit beiden Ringen. Der Unterschied zwischen
Stufe B und Stufe D ist damit **genau der Ring** und sonst nichts.

Das ist der Sinn einer Gegenrechnung: nicht ein zweites, besseres Ergebnis,
sondern eine Aussage darueber, was im ersten fehlte.

Wie das Modell gebaut ist
--------------------------

* Der 2-D-Querschnitt wird ueber die Paketlaenge extrudiert. Alle Koerper
  (Welle, Laeuferblech, Staebe, Stege, Luftspalt, Statoreisen, Nuten) behalten
  ihre Rolle.
* An beiden Stirnseiten sitzt je ein **Kurzschlussring** mit dem Querschnitt,
  den ``ema_asm.kaefig`` ansetzt -- derselbe Wert, der im CAD gezeichnet wird.
* Um die Stirnseiten liegt **Luft**, sonst haette das Stirnfeld keinen Weg und
  der Ring waere wieder nur ein Widerstand ohne Feld.
* Leitfaehigkeit ``sigma_eff = s*sigma`` auf Staeben UND Ringen -- dieselbe
  Herleitung wie in Stufe B (dort im Modulkopf), damit beide Stufen denselben
  Betriebspunkt meinen.
* Statorstrom als Stromdichte je Nut, aus derselben 60-Grad-Zonenwicklung
  (``ema_em2d_harm.stator_stroeme``).

Der Statorleiter geht von Deckel zu Deckel -- und warum das kein Wickelkopf ist
-------------------------------------------------------------------------------

Die Statornut wird NICHT ueber das Blechpaket extrudiert und dann von einem
Wickelkopf fortgesetzt, sondern durch die Stirnluft hindurch bis auf den
Aussenrand. Der Strom tritt damit durch den Dirichlet-Rand ein und aus, der
Rueckschluss liegt ausserhalb des Gebiets -- genau die stillschweigende Annahme
der 2-D-Stufe. Die beiden Stufen meinen so denselben Stator, und der Vergleich
ist einer.

Ein wirklicher Wickelkopf ist das nicht. Er ist hier auch nicht der Gegenstand:
Gegenstand ist der KURZSCHLUSSRING im Laeufer, und der ist als leitender
Koerper gebaut, nicht als eingepraegte Quelle.

Der Grund fuer diesen Bau ist gemessen. Endete der Nutstrom am Paketende mitten
in der Stirnluft, war die eingepraegte Stromdichte dort nicht divergenzfrei --
die rechte Seite des curl-curl-Systems also unvertraeglich:

    Leiter endet in der Stirnluft, mit Wickelkopfwelle
        B_Spalt 1,98 T    12,6 % des Volumens ueber 20 T
    Leiter endet in der Stirnluft, ohne Wickelkopfwelle
        B_Spalt 1,40 T    10,8 %
    Leiter bis auf den Rand  (dieser Bau)
        B_Spalt 0,305 T    0,001 %      2-D am selben Punkt: 0,287 T

Zwei Fehler, die dabei gefunden wurden und die jeden treffen werden
--------------------------------------------------------------------

**1. ``Use Tree Gauge`` muss ausdruecklich AUS.** Elmers Voreinstellung ist
True; die Zeile wegzulassen aendert also nichts. Gemessen, dasselbe Netz, nur
diese Zeile verschieden:

    Tree Gauge = True    B_Spalt 44,06 T   3,28 % ueber 20 T
    Zeile entfernt       B_Spalt 44,06 T   3,28 %      (= Vorgabe True)
    Tree Gauge = False   B_Spalt  0,390 T  0,01 %
    2-D am selben Punkt  B_Spalt  0,399 T

Die Eichung zerstoert dabei NUR den Imaginaerteil. Mit ``sigma = 0`` zerfaellt
das harmonische System in zwei entkoppelte Bloecke mit demselben Operator --
dieselbe rechte Seite muss also dieselbe Loesung geben. Sie tut es nicht:

    Quelle im Realteil         max |B| 3,9e+02 T    0,00 % wild
    dieselbe Quelle im Imag.   max |B| 2,4e+08 T    3,28 % wild
    eine einzige Nut, real     max |B| 9 T
    eine einzige Nut, imag.    max |B| 1,1e+08 T

Der Ausreisser haengt an nichts Physikalischem: ``mu``, ``sigma``, ``omega``
geaendert -- das Maximum bleibt auf drei Stellen dasselbe. Das ist der Nullraum
(Gradientenfelder), den die Eichung im imaginaeren Block nicht entfernt,
sondern anregt. Ohne Eichung ist das System singulaer, aber vertraeglich; ein
DIREKTER Loeser (MUMPS) liefert darauf eine gueltige Teilloesung, deren Rotation
stimmt -- dreimal wiederholt, bitgleich. Ein iterativer Loeser darf hier
deshalb nicht eingesetzt werden.

**2. Von fuenf Schreibweisen der Randbedingung bindet eine einzige die
Kanten-Freiheitsgrade.** Gemessen, jede mit einem eigenen Lauf:

    AV re {e} / AV im {e}      wirkt
    AV {e}                     WIRKUNGSLOS
    AV {e} 1 / AV {e} 2        WIRKUNGSLOS
    nur AV re / AV im          WIRKUNGSLOS
    gar keine Randbedingung    dasselbe wie die drei wirkungslosen

Elmer meldet dazu **nichts** -- kein unbekanntes Schluesselwort, keine Warnung.
Wer aus ``ema_em3d`` das dort richtige ``AV {e}`` uebernimmt (die Variable ist
dort reell), bekommt hier stillschweigend gar keine Randbedingung.

Zwei weitere Fehler, die auf dem Weg behoben wurden, ohne die Ursache zu sein:
der Aussenrand war an beiden Stirnflaechen OFFEN (absoluter Meter-Vergleich, der
nie traf; 1129 cm^2 Randflaeche gegen 2359 cm^2 danach), und
``Fix Input Current Density`` verstaerkte den Fehler, statt ihn zu bereinigen --
das Jfix-Problem ist ein reines Neumann-Poisson-System und damit singulaer.
Beides steht an Ort und Stelle im Quelltext.

Was diese Stufe misst
----------------------

Den **Ringverlust je Stabverlust** -- woertlich die Groesse, die
``ema_asm.kurzschlussring_zuschlag`` ansetzt (dort:
``P_kaefig = P_stab * (1 + Zuschlag)``). Sie faellt in EINEM Lauf an, auf einem
Netz, und braucht keinen Vergleichslauf.

Gemessen an der Beispielmaschine (p=3, 36 Nuten, 28 Staebe, 190 mm Bohrung,
4000 min^-1, 150 Nm), Ring 5,0 x 12,3 mm:

    L =  60 mm   P_Stab  513,3 W   P_Ring 449,7 W   Ring/Stab 87,6 %
    L = 120 mm   P_Stab 1343,1 W   P_Ring 592,8 W   Ring/Stab 44,1 %
    L = 180 mm   P_Stab 2753,9 W   P_Ring 820,9 W   Ring/Stab 29,8 %

Angesetzt waren pauschal 20 %. Der Anteil ist also **keine Konstante**: er haengt
an der Paketlaenge, denn der Ring wird nicht laenger, wenn das Paket es wird --
doppelte Laenge, halber Anteil. ``ema_asm.kurzschlussring_zuschlag`` rechnet ihn
seitdem aus der Geometrie und trifft diese drei Messpunkte auf 1,13 / 1,12 /
1,11 -- ein gleichbleibender Versatz, kein Auseinanderlaufen. Der 180-mm-Punkt
kam dabei NACH der Formel herein.

Der zweite Lauf (Ringe isolierend) ist KEIN „Kaefig ohne Ring": mit isolierenden
Ringen kann der Stabstrom seinen Kreis gar nicht schliessen, es gibt dann also
gar keinen Kaefig (gemessen 0,001 Nm gegen 2,299 Nm). Er zeigt, dass das Modell
den Ring wirklich fuehrt -- mehr nicht.


Was hier bewusst NICHT gerechnet wird
--------------------------------------

* **Keine Schraegung.** Sie waere in 3-D moeglich und ist ein eigener Schritt.
* **Lineares Eisen** wie in Stufe B, Steg gesaettigt angesetzt.
* **Kein wirklicher Wickelkopf** -- s. oben; der Statorleiter geht gerade
  durch bis auf den Rand.

Wie weit die Zahl auskonvergiert ist -- gemessen, nicht behauptet
------------------------------------------------------------------

Dieselbe Maschine, dasselbe Modell, nur das groesste Element im Eisen kleiner
(60 mm Paket; der Luftspalt hat in allen dreien EINE Elementlage, radial laesst
er sich so gar nicht verfeinern, s. u.):

    lc_eisen 8,0 mm    166.614 Tets   B_Spalt 0,2726 T   Ring/Stab 87,5 %
    lc_eisen 5,0 mm    437.294 Tets   B_Spalt 0,2915 T   Ring/Stab 93,0 %
    lc_eisen 3,5 mm  1.111.784 Tets   MUMPS: kein Arbeitsspeicher
    2-D am selben Punkt                B_Spalt 0,2870 T

Zwei Dinge stehen damit fest und eines ausdruecklich nicht:

* Die Luftspalt-Grundwelle laeuft auf den 2-D-Wert zu (0,2726 -> 0,2915 gegen
  0,2870) -- das Modell rechnet dieselbe Maschine.
* Das Verhaeltnis Ring/Stab ist **nicht auskonvergiert**: es steigt um 6 %, und
  der Abstand zur analytischen Formel (``ema_asm.kurzschlussring_zuschlag``,
  99,1 % an dieser Maschine) faellt dabei von 13 % auf 6,6 %. Die Vermutung, der
  Abstand komme vom Netz, ist damit gestuetzt und nicht bewiesen -- die Formel
  hat ihre eigenen Annahmen (sinusfoermige Stabstromverteilung), und 6,6 % sind
  auch dafuer eine uebliche Groessenordnung.
* Nicht bekannt ist der Grenzwert. Er laege oberhalb dessen, was diese Maschine
  rechnen kann.

**Die Obergrenze ist der Arbeitsspeicher, nicht die Geduld.** Bei 1,1 Mio.
Tetraedern bricht MUMPS mit ``INFO(1) = -13`` ab -- und Elmer rechnet danach mit
einem Nullvektor weiter, meldet FINISHED und schreibt eine Ergebnisdatei. Das
faengt jetzt ``elmer_runner`` ab (der MUMPS-Code steht in der Bildschirmausgabe,
nicht im Rueckgabewert); vorher kamen daraus 0,0 W und 0,000 Nm, also Zahlen.
Zwischen 437.000 und 1.111.000 Tetraedern liegt die Grenze dieser Maschine.

Der Luftspalt ist hier NICHT aufgeloest -- und warum das trotzdem geht
-----------------------------------------------------------------------

Das ist die wichtigste Einschraenkung dieser Stufe, und sie ist gemessen:

    Verfeinerungsband auf den Luftspalt (0,7 mm), 150 mm Paket:
        nach 1 h 56 min abgebrochen, kein Netz
        zweiter Versuch, 500 s Deckel: kein Netz
    ohne Verfeinerungsband, 3 mm kleinstes Element, 30 mm Paket:
        30.010 Tetraeder in 3 s
    ohne Verfeinerungsband, 2 mm kleinstes Element, 60 mm Paket:
        79.345 Tetraeder in 14 s
    volles Modell mit Ringen und Stirnluft, 1,5 mm, 60 mm Paket:
        138.666 Tetraeder in 26 s (Geometrie davon 10 s)

Ein Luftspalt von 0,7 mm ueber 0,6 m Umfang und 0,15 m Laenge braucht in 3-D
Millionen Elemente -- auf dieser Maschine nicht rechenbar. Mit 2-3 mm grossen
Elementen ist der Spalt dagegen gar nicht aufgeloest, und das **absolute**
Moment aus einem solchen Netz waere keine Aussage.

Das Netz ist damit NICHT der teure Teil dieser Stufe -- der Loeser ist es. Ein
harmonisches Kantenelement-System ist komplex und hat doppelt so viele
Unbekannte wie das magnetostatische; ``netzkosten()`` laesst sich deshalb
einzeln aufrufen, um die Netzgroesse zu kennen, BEVOR ein Lauf gestartet wird.

Deshalb misst diese Stufe kein absolutes Moment, sondern **Verhaeltnisse**:
Ringverlust je Stabverlust (in einem Lauf, s. oben) und -- als Probe, dass das
Modell den Ring wirklich fuehrt -- zweimal dasselbe Netz mit leitenden und mit
isolierenden Ringen. Der Netzfehler steckt in beiden Laeufen gleich und faellt
weitgehend heraus.

Wie gross er ist, laesst sich trotzdem beziffern, seit das Feld gueltig ist:
die Luftspalt-Grundwelle kommt mit 0,3047 T gegen die 0,2870 T der 2-D-Stufe
heraus -- 6 % bei einem Spalt, der mit 1,5-mm-Elementen ueber 0,7 mm gar nicht
aufgeloest ist. Das ist die Groessenordnung des Netzfehlers, und sie steht damit
nicht mehr als Vermutung da.
"""

from __future__ import annotations

import math
import os

import elmer_runner
import ema_em2d_harm as H

MU0 = H.MU0

# Physikalische Gruppen-Nummern der 3-D-Stufe. Wieder luecklos ab 1, aus dem
# Grund, der in ``ema_em2d_harm`` steht: ``ElmerGrid -autoclean`` nummeriert um.
GID_WELLE  = 1
GID_ROTOR  = 2
GID_STAEBE = 3
GID_STEG   = 4
GID_LUFT   = 5
GID_STATOR = 6
GID_RING   = 7          # beide Kurzschlussringe (Laeufer)
GID_STIRN  = 8          # Luft an den Stirnseiten
GID_NUT0   = 9          # Nut k -> GID_NUT0 + k
GID_RAND   = 1          # Aussenflaeche (eigener Nummernkreis, 2D)

# Axiale Laenge der Stirnluft, als Vielfaches der Ringbreite. Zu kurz gewaehlt
# klemmt die Randbedingung das Stirnfeld ab und der Ring erscheint wirkungslos.
STIRNLUFT_FAKTOR = 3.0

# Ab wievielen Tetraedern der direkte Loeser auf DIESER Maschine kippt.
# Gemessen: 437.294 rechnen (56 s), 1.111.784 nicht mehr -- MUMPS bricht mit
# INFO(1) = -13 ab (Speicher). Die Zahl ist eine Warnschwelle, kein Tor: sie
# haengt am Arbeitsspeicher, und wer mehr hat, soll es versuchen duerfen. Sie
# steht hier, damit ``netzkosten()`` es sagen kann, BEVOR jemand eine Stunde
# wartet und dann ein Nullfeld bekommt.
TETS_WARNUNG = 600000


def baue_netz(geom: dict, kaefig: dict, axial_mm: float, msh_pfad: str,
              gap_lagen: int = 2, lc_eisen_mm: float = 0.0,
              lagen_axial: int = 6) -> dict:
    """3-D-Netz: Querschnitt extrudiert, plus beide Ringe und die Stirnluft."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add("asm3d")
        occ = gmsh.model.occ
        q = H.quer_flaechen(gmsh, geom, kaefig)
        m = q["masse"]
        L = float(axial_mm) / 1000.0

        # Ringquerschnitt als Rechteck mit dem Seitenverhaeltnis des Stabes --
        # dieselbe Umrechnung wie im CAD (ema_freecad), damit Modell und
        # Zeichnung denselben Ring meinen.
        a_ring = m["A_ring_m2"]
        ring_h = math.sqrt(a_ring * m["t_stab"] / max(m["b_stab"], 1e-6))
        ring_w = math.sqrt(a_ring * m["b_stab"] / max(m["t_stab"], 1e-6))
        ring_h = min(ring_h, m["r_stab_a"] - m["r_wel"] - 1e-3)
        tief = ring_w
        stirn = max(STIRNLUFT_FAKTOR * ring_w, 2.0 * tief)
        z_lo, z_hi = -(tief + stirn), L + tief + stirn

        # Blechpaket, Welle, Kaefig, Luftspalt: nur ueber die Paketlaenge.
        paket = [(2, t) for t in q["welle"] + q["rotor"] + q["staebe"]
                 + q["stege"] + q["luft"] + q["stator"]]
        aus = occ.extrude(paket, 0, 0, L)
        occ.synchronize()

        # ``extrude`` gibt je Eingangsflaeche vier Eintraege zurueck
        # (Deckflaeche, Volumen, Mantelflaechen); das Volumen ist der Eintrag
        # mit dim == 3. Die Reihenfolge folgt der Eingabe, also laesst sich
        # jedem Koerper sein Volumen ohne Schwerpunktsuche zuordnen.
        vols = [t for (d, t) in aus if d == 3]
        if len(vols) != len(paket):
            raise RuntimeError(f"Extrusion gab {len(vols)} Volumen fuer "
                               f"{len(paket)} Flaechen")
        i = 0
        gruppen = {}
        for name in ("welle", "rotor", "staebe", "stege", "luft", "stator"):
            n = len(q[name])
            gruppen[name] = vols[i:i + n]
            i += n

        # Der Statorleiter geht von DECKEL zu DECKEL, nicht nur ueber das Paket.
        #
        # Das ist der Punkt, an dem diese Stufe vorher falsch rechnete. Endete
        # der Nutstrom am Paketende mitten in der Stirnluft, war die
        # eingepraegte Stromdichte dort nicht divergenzfrei -- und die rechte
        # Seite des curl-curl-Systems damit unvertraeglich. Ein Rueckleiter als
        # stetige Wickelkopfwelle heilte das nicht (er ist selbst nicht diskret
        # divergenzfrei), und die nachtraegliche Projektion (Jfix) machte es
        # schlimmer. Gemessen, dasselbe Netz, nur das Ende verschieden:
        #
        #     Leiter endet in der Stirnluft, mit Wickelkopfwelle
        #         B_Spalt 1,98 T   12,6 % des Volumens ueber 20 T
        #     Leiter endet in der Stirnluft, ohne Wickelkopfwelle
        #         B_Spalt 1,40 T   10,8 %
        #     Leiter bis auf den Rand  (dieser Bau)
        #         B_Spalt 0,305 T   0,001 %      2-D am selben Punkt: 0,287 T
        #
        # Physikalisch heisst das: der Strom tritt durch den Dirichlet-Rand ein
        # und aus, der Rueckschluss liegt ausserhalb des Gebiets. Genau das ist
        # auch die stillschweigende Annahme der 2-D-Stufe -- die beiden Stufen
        # meinen damit denselben Stator, und der Vergleich ist einer. Ein
        # wirklicher Wickelkopf ist das nicht; er ist hier auch nicht der
        # Gegenstand. Gegenstand ist der KURZSCHLUSSRING im Laeufer, und der
        # ist als leitender Koerper gebaut, nicht als eingepraegte Quelle.
        nut_v = []
        for f in q["nut_f"]:
            kopien = occ.copy([(2, t) for t in f])
            occ.translate(kopien, 0, 0, z_lo)
            a2 = occ.extrude(kopien, 0, 0, z_hi - z_lo)
            nut_v.append([t for (d, t) in a2 if d == 3])
        occ.synchronize()

        # Kurzschlussringe an beiden Stirnseiten (Laeufer).
        ringe = []
        for z0 in (-ring_w, L):
            aussen = occ.addCylinder(0, 0, z0, 0, 0, ring_w, m["r_stab_a"])
            innen = occ.addCylinder(0, 0, z0 - 1e-4, 0, 0, ring_w + 2e-4,
                                    max(m["r_stab_a"] - ring_h, 1e-4))
            r, _ = occ.cut([(3, aussen)], [(3, innen)])
            ringe.append(r[0][1])

        # Stirnluft: zwei Zylinder bis r_so, aus denen Ringe und Nutleiter
        # geschnitten werden. Zu kurz gewaehlt klemmt die Randbedingung das
        # Stirnfeld ab und der Ring erschiene wirkungslos.
        stirnluft = [occ.addCylinder(0, 0, z0, 0, 0, tief + stirn, m["r_so"])
                     for z0 in (z_lo, L)]
        werkzeug = ([(3, t) for t in ringe]
                    + [(3, t) for v in nut_v for t in v])
        _, abb = occ.fragment([(3, t) for t in stirnluft], werkzeug)
        occ.synchronize()
        # Was aus einem Ring kam, IST der Ring; was aus einem Nutleiter kam, ist
        # der Nutleiter; der Rest ist Luft. Zugeordnet wird ueber die Abbildung
        # von ``fragment``, nicht ueber Schwerpunkte -- keine Toleranz, an der
        # eine Zuordnung kippen koennte.
        n_s = len(stirnluft)
        ring_v = set()
        for grp in abb[n_s:n_s + len(ringe)]:
            ring_v.update(t for (d, t) in grp if d == 3)
        nut_neu, k_ = [], n_s + len(ringe)
        for v in nut_v:
            teile = set()
            for grp in abb[k_:k_ + len(v)]:
                teile.update(t for (d, t) in grp if d == 3)
            k_ += len(v)
            nut_neu.append(sorted(teile))
        stirn_v = set()
        for grp in abb[:n_s]:
            stirn_v.update(t for (d, t) in grp if d == 3)
        stirn_v -= ring_v
        for v in nut_neu:
            stirn_v -= set(v)
        fehlend = [k for k, v in enumerate(nut_neu) if not v]
        if not ring_v or fehlend:
            raise RuntimeError("Nach dem Verschneiden nicht wiedergefunden: "
                               f"{len(ring_v)} Ringstuecke, {len(fehlend)} "
                               f"Nutleiter ohne Volumen")

        # Alles zusammenkleben, damit die Felder ueber die Stirnflaeche stetig sind.
        alle = ([(3, t) for t in vols] + [(3, t) for t in sorted(ring_v)]
                + [(3, t) for t in sorted(stirn_v)]
                + [(3, t) for v in nut_neu for t in v])
        _, abb2 = occ.fragment(alle[:1], alle[1:])
        occ.synchronize()
        # Ein Wörterbuch statt einer linearen Suche je Koerper: bei 36 Nuten,
        # die jetzt in mehrere Stuecke zerfallen, lief die alte Schleife ueber
        # ``alle`` je Eintrag noch einmal durch die ganze Liste.
        pos = {t: idx for idx, (d, t) in enumerate(alle)}

        def neu(alte):
            aus_ = []
            for t in alte:
                if t in pos:
                    aus_ += [v for (d, v) in abb2[pos[t]] if d == 3]
            return sorted(set(aus_))

        gmsh.model.addPhysicalGroup(3, neu(gruppen["welle"]), GID_WELLE, "welle")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["rotor"]), GID_ROTOR, "rotoreisen")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["staebe"]), GID_STAEBE, "staebe")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["stege"]), GID_STEG, "stege")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["luft"]), GID_LUFT, "luftspalt")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["stator"]), GID_STATOR, "statoreisen")
        gmsh.model.addPhysicalGroup(3, neu(sorted(ring_v)), GID_RING, "ringe")
        gmsh.model.addPhysicalGroup(3, neu(sorted(stirn_v)), GID_STIRN, "stirnluft")
        for k, v in enumerate(nut_neu):
            gmsh.model.addPhysicalGroup(3, neu(v), GID_NUT0 + k, f"nut{k}")

        # Aussenrand: alle Flaechen auf r_so plus die beiden aeusseren Stirnflaechen.
        # Aussenrand: Mantel UND beide Stirnflaechen.
        #
        # Die Stirnflaechen fehlten. Sie wurden ueber ``abs(z - (L+tief+stirn))
        # < 1e-9`` gesucht -- ein absoluter Vergleich auf Meter, waehrend die
        # Grenze selbst aus Ringbreiten zusammengerechnet ist und die Huellbox
        # von OCC gerundet zurueckkommt. Der Vergleich traf nie, und damit war
        # das Gebiet an beiden Enden OFFEN: dort ist A unbestimmt, und genau
        # dort sass das unsinnige Feld (gemessen 18 % des Volumens ueber
        # 1000 T, angefuehrt von der Stirnluft). Mit Quellen null kam trotzdem
        # exakt null heraus -- ein unbestimmter, aber unangeregter Nullraum
        # meldet sich nicht.
        #
        # Gesucht wird jetzt gegen die WIRKLICHE Huellbox des Modells, mit einer
        # Toleranz, die sich an ihr bemisst. Und es wird nachgezaehlt: ohne die
        # beiden Deckel ist die Randflaeche unvollstaendig, und das ist ein
        # Fehler und keine Warnung.
        bb_all = gmsh.model.getBoundingBox(-1, -1)
        z_min, z_max = bb_all[2], bb_all[5]
        tol = 1e-6 + 1e-6 * max(abs(z_min), abs(z_max), m["r_so"])
        rand, n_mantel, n_deckel = [], 0, 0
        for (d, t) in gmsh.model.getEntities(2):
            bb = gmsh.model.getBoundingBox(2, t)
            weite = max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0
            zf_lo, zf_hi = bb[2], bb[5]
            flach = abs(zf_hi - zf_lo) <= tol
            if abs(weite - m["r_so"]) < 1e-4 * m["r_so"] + 1e-9 and not flach:
                rand.append(t); n_mantel += 1
            elif flach and (abs(zf_lo - z_min) <= tol or abs(zf_lo - z_max) <= tol):
                rand.append(t); n_deckel += 1
        if not n_mantel or not n_deckel:
            raise ValueError(
                f"Aussenrand unvollstaendig: {n_mantel} Mantelflaechen, "
                f"{n_deckel} Stirnflaechen. Fehlt ein Deckel, ist das Gebiet "
                f"dort offen und das Vektorpotential unbestimmt — das Ergebnis "
                f"sieht dann aus wie ein Feld.")
        gmsh.model.addPhysicalGroup(2, rand, GID_RAND, "aussenrand")

        # KEIN Verfeinerungsband auf den Luftspalt (anders als in 2-D). Gemessen:
        # mit Band bricht das Netzen bei 0,7 mm Spalt und 150 mm Paket nach
        # 1 h 56 min ohne Ergebnis ab; ohne Band stehen 30.010 Tetraeder in 3 s.
        # Der Spalt ist damit nicht aufgeloest -- das absolute Moment aus diesem
        # Netz waere keine Aussage, das Verhaeltnis zweier Laeufe darauf schon
        # (s. Modulkopf und ``ring_wirkung``).
        lc_eisen = (lc_eisen_mm / 1000.0) if lc_eisen_mm > 0 else max(
            L / max(int(lagen_axial), 1), 4.0e-3)
        lc_gap = max(m["gap_m"] / max(int(gap_lagen), 1), 1.5e-3)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", lc_gap)
        gmsh.option.setNumber("Mesh.MeshSizeMax", lc_eisen)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)      # HXT, schnell
        gmsh.model.mesh.generate(3)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        os.makedirs(os.path.dirname(os.path.abspath(msh_pfad)) or ".", exist_ok=True)
        gmsh.write(msh_pfad)
        knoten = len(gmsh.model.mesh.getNodes()[0])
        _, el, _ = gmsh.model.mesh.getElements(3)
        tets = sum(len(e) for e in el)
    finally:
        gmsh.finalize()

    return {"msh": msh_pfad, "knoten": int(knoten), "tets": int(tets),
            "n_stab": m["n_stab"], "n_nut": len(q["nuten"]),
            "L_m": L, "ring_h_m": ring_h, "ring_w_m": ring_w,
            "A_ring_m2": a_ring, "stirn_m": stirn, "tief_m": tief,
            "z_lo_m": z_lo, "z_hi_m": z_hi,
            "rand_mantel": n_mantel, "rand_deckel": n_deckel,
            "r_wel": m["r_wel"], "r_rot": m["r_rot"], "r_si": m["r_si"],
            "r_so": m["r_so"], "gap_m": m["gap_m"],
            "lc_gap_m": lc_gap, "lc_eisen_m": lc_eisen,
            "A_nut_m2": q["A_nut_m2"], "A_stab_m2": float(kaefig["A_stab_mm2"]) * 1e-6}


def schreibe_sif(netz: dict, omega1: float, sigma_eff: float, j_nut: dict,
                 work_dir: str, mu_r_steg: float, mesh_name: str = "mesh",
                 ring_leitet: bool = True) -> str:
    """``case.sif`` fuer ``WhitneyAVHarmonicSolver`` (3-D, komplex)."""
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)
    n_nut = int(netz["n_nut"])

    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n"
         "  Max Output Level = 4\n"
         "  Coordinate System = Cartesian\n"
         "  Simulation Type = Steady State\n"
         "  Steady State Max Iterations = 1\n"
         "  Output Intervals = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0:.12e}\nEnd\n"]

    koerper = [(GID_WELLE, 1, None), (GID_ROTOR, 1, None), (GID_STAEBE, 3, None),
               (GID_STEG, 4, None), (GID_LUFT, 2, None), (GID_STATOR, 1, None),
               (GID_RING, 3 if ring_leitet else 2, None), (GID_STIRN, 2, None)]
    koerper += [(GID_NUT0 + k, 2, k + 1) for k in range(n_nut)]
    for i, (gid, mat, bf) in enumerate(koerper, start=1):
        S.append(f"Body {i}\n  Target Bodies(1) = {gid}\n  Equation = 1\n"
                 f"  Material = {mat}\n"
                 + (f"  Body Force = {bf}\n" if bf else "") + "End\n")

    S.append(f"Material 1\n  Relative Permeability = {H.MU_R_EISEN}\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    S.append("Material 2\n  Relative Permeability = 1.0\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    # Staebe UND Ringe leiten. Der Ring ist der ganze Grund fuer diese Stufe:
    # in 2-D gibt es ihn nicht, hier traegt er Strom und Feld.
    S.append("! sigma_eff = s*sigma (Herleitung im Kopf von ema_em2d_harm).\n"
             f"Material 3\n  Relative Permeability = 1.0\n"
             f"  Electric Conductivity = {sigma_eff:.6e}\nEnd\n")
    S.append(f"Material 4\n  Relative Permeability = {mu_r_steg}\n"
             "  Electric Conductivity = 0.0\nEnd\n")

    for k in range(n_nut):
        j = j_nut.get(H.GID_NUT0 + k, 0j)
        S.append(f"Body Force {k + 1}\n"
                 f"  Current Density 3 = Real {j.real:.6e}\n"
                 f"  Current Density Im 3 = Real {j.imag:.6e}\nEnd\n")

    # Direkter Loeser (MUMPS), NICHT iterativ. ``ema_em3d`` hat denselben Fehler
    # schon einmal gelernt und im Modulkopf festgehalten: „der iterative
    # BiCGStabL stagniert ohne aufwaendige Vorkonditionierung" am
    # curl-curl-Kantenelement-System. Gemessen hier: 6000 Iterationen, Residuum
    # bleibt bei 1,5, neunzehn Minuten Rechenzeit und am Ende kein Feld. Hier
    # kommt ein zweiter Grund dazu: ohne Baum-Eichung (s. Solver 1) ist das
    # System singulaer -- vertraeglich, aber singulaer. Ein direkter Loeser
    # liefert darauf eine gueltige Teilloesung, ein iterativer nicht.
    #
    # Einen Wickelkopf-Rueckleiter gibt es hier NICHT mehr. Er war der Versuch,
    # einen im Gebiet endenden Nutstrom zu schliessen; der Nutleiter geht jetzt
    # von Deckel zu Deckel (Herleitung und Messreihe in ``baue_netz``).

    S.append("Solver 1\n"
             '  Equation = "MgDyn3DHarmonic"\n'
             '  Procedure = "MagnetoDynamics" "WhitneyAVHarmonicSolver"\n'
             '  Variable = "AV[AV re:1 AV im:1]"\n'
             f"  Angular Frequency = Real {omega1:.9e}\n"
             # Die Baum-Eichung ist AUS -- und das ist die Zeile, an der diese
             # Stufe fuenf Anlaeufe lang gescheitert ist. Sie muss ausdruecklich
             # auf False stehen: Elmers Voreinstellung ist True, die Zeile
             # WEGZULASSEN aendert also nichts.
             #
             # Gemessen, alles auf demselben Netz, nur diese eine Zeile anders:
             #
             #     Tree Gauge = True    B_Spalt 44,06 T   3,28 % ueber 20 T
             #     Zeile entfernt       B_Spalt 44,06 T   3,28 %   (= Vorgabe True)
             #     Tree Gauge = False   B_Spalt  0,390 T  0,01 %
             #     2-D am selben Punkt  B_Spalt  0,399 T
             #
             # Warum es so lange verborgen blieb: die Eichung zerstoert nur den
             # IMAGINAERTEIL. Mit sigma = 0 zerfaellt das harmonische System in
             # zwei entkoppelte Bloecke mit DEMSELBEN Operator -- dieselbe rechte
             # Seite muss also dieselbe Loesung geben. Sie tut es nicht:
             #
             #     Quelle im Realteil       max |B| 3,9e+02 T   0,00 % wild
             #     dieselbe Quelle im Im.   max |B| 2,4e+08 T   3,28 % wild
             #     eine einzige Nut, real   max |B| 9 T
             #     eine einzige Nut, imag.  max |B| 1,1e+08 T
             #
             # Der Ausreisser haengt dabei an nichts Physikalischem: mu, sigma,
             # omega geaendert -- das Maximum bleibt auf drei Stellen dasselbe.
             # Das ist der Nullraum (Gradientenfelder), den die Eichung im
             # imaginaeren Block nicht entfernt, sondern anregt.
             #
             # Ohne Eichung ist das System singulaer, aber vertraeglich; der
             # DIREKTE Loeser (MUMPS, s. unten) liefert darauf eine gueltige
             # Teilloesung, deren Rotation stimmt. Dreimal wiederholt: bitgleich.
             # Ein iterativer Loeser darf hier deshalb NICHT eingesetzt werden.
             "  Use Tree Gauge = Logical False\n"
             # Jfix bleibt AUS. Er war eingeschaltet, weil die eingepraegte
             # Stromdichte nicht exakt divergenzfrei ist -- die Nutstroeme sind
             # je Nut konstant, der Rueckstrom im Ring eine stetige Welle. Der
             # Gedanke war richtig, die Wirkung das Gegenteil:
             #
             #     Jfix AN   Median 0,221 T   20,3 % ueber 20 T   B_Spalt 3,25 T
             #     Jfix AUS  Median 0,002 T    2,7 % ueber 20 T   B_Spalt 0,02 T
             #
             # Elmer meldet dazu „JfixPotentialSolver: No Dirichlet conditions
             # used to define Jfix level!" -- das Jfix-Problem ist ein reines
             # Neumann-Poisson-System und damit singulaer. Bei einer rechten
             # Seite, die nicht exakt vertraeglich ist, laeuft der iterative
             # Loeser darin davon und legt seinen Fehler auf das Feld. Er
             # bereinigte also nicht die Divergenz, er erzeugte den Ausreisser.
             #
             # Der richtige Weg waere eine diskret divergenzfreie Einpraegung
             # (Ringstrom je Nut statt als stetige Welle), nicht eine
             # nachtraegliche Projektion.
             "  Fix Input Current Density = Logical False\n"
             "  Linear System Solver = Direct\n"
             "  Linear System Direct Method = MUMPS\n"
             "  Steady State Convergence Tolerance = 1.0e-8\n"
             "End\n")
    # Der Nachbearbeitungsloeser braucht seinen EIGENEN Gleichungsloeser. Ohne
    # ihn bricht Elmer nach dem Hauptlauf ab:
    #     ERROR:: SolveLinearSystem: Give "Linear System Solver"
    # Das kostet den ganzen Lauf, und zwar NACH der teuren Rechnung -- der
    # Fehler faellt also erst auf, wenn alles gerechnet ist. Dieselben
    # Einstellungen wie in ``ema_em3d`` (CG + ILU0): das Feld-System dort ist
    # symmetrisch positiv definit und braucht kein BiCGStabL.
    S.append("Solver 2\n"
             '  Equation = "MgDynCalc"\n'
             '  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"\n'
             '  Potential Variable = String "AV"\n'
             "  Calculate Magnetic Field Strength = Logical True\n"
             "  Calculate Joule Heating = Logical True\n"
             "  Calculate Current Density = Logical True\n"
             "  Linear System Solver = Iterative\n"
             "  Linear System Iterative Method = CG\n"
             "  Linear System Preconditioning = ILU0\n"
             "  Linear System Max Iterations = 5000\n"
             "  Linear System Convergence Tolerance = 1.0e-8\n"
             "End\n")
    S.append("Solver 3\n"
             '  Equation = "ErgebnisAusgabe"\n'
             '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
             '  Output File Name = "asm3d"\n'
             '  Output Format = String "vtu"\n'
             "  Save Geometry Ids = Logical True\n"
             '  Output Directory = "results"\n'
             "  Vtu Format = Logical True\n"
             "End\n")
    S.append("Equation 1\n  Active Solvers(3) = 1 2 3\nEnd\n")
    S.append(f"Boundary Condition 1\n  Target Boundaries(1) = {GID_RAND}\n"
             "  AV re {e} = Real 0.0\n  AV im {e} = Real 0.0\n"
             "  AV re = Real 0.0\n  AV im = Real 0.0\nEnd\n")

    pfad = os.path.join(work_dir, "case.sif")
    with open(pfad, "w") as fh:
        fh.write("\n".join(S))
    with open(os.path.join(work_dir, "ELMERSOLVER_STARTINFO"), "w") as fh:
        fh.write("case.sif\n1\n")
    return pfad


def netzkosten(geom: dict, kaefig: dict, axial_mm: float, work_dir: str,
               gap_lagen: int = 2, lagen_axial: int = 6,
               lc_eisen_mm: float = 0.0, log=None) -> dict:
    """Nur das Netz bauen und **messen**, was diese Stufe kostet.

    Getrennt aufrufbar, weil die Netzgroesse in 3-D die eigentliche Frage ist:
    ein Luftspalt von 0,7 mm ueber 0,6 m Umfang laesst sich beliebig teuer
    aufloesen. Wer wissen will, ob ein Lauf ueberhaupt in Frage kommt, soll das
    erfahren, ohne ihn zu starten.
    """
    import time
    t0 = time.time()
    msh = os.path.join(work_dir, "asm3d.msh")
    os.makedirs(work_dir, exist_ok=True)
    netz = baue_netz(geom, kaefig, axial_mm, msh, gap_lagen=gap_lagen,
                     lc_eisen_mm=lc_eisen_mm, lagen_axial=lagen_axial)
    netz["netzzeit_s"] = round(time.time() - t0, 1)
    netz["zu_gross"] = bool(netz["tets"] > TETS_WARNUNG)
    if log:
        log(f"3-D-Netz: {netz['tets']} Tetraeder, {netz['knoten']} Knoten "
            f"in {netz['netzzeit_s']:.0f} s")
        if netz["zu_gross"]:
            log(f"ACHTUNG: {netz['tets']} Tetraeder liegen ueber der gemessenen "
                f"Grenze dieser Maschine ({TETS_WARNUNG}). Der direkte Loeser "
                f"bricht dort mit fehlendem Arbeitsspeicher ab — der Lauf endet "
                f"dann mit einem Fehler, nicht mit einem Ergebnis.")
    return netz


def _loese(ctx: dict, ring_leitet: bool, timeout: int) -> dict:
    """EIN 3-D-Lauf auf dem vorhandenen Netz."""
    schreibe_sif(ctx["netz"], ctx["omega1"], ctx["sigma_eff"], ctx["j_nut"],
                 ctx["work_dir"], ctx["mu_r_steg"], ring_leitet=ring_leitet)
    rs = elmer_runner.run_elmersolver(os.path.join(ctx["work_dir"], "case.sif"),
                                      ctx["work_dir"], timeout=timeout)
    if not rs.get("ok"):
        raise RuntimeError("ElmerSolver (3-D): "
                           + (rs.get("stderr") or rs.get("error", ""))[:400]
                           + "\n" + rs.get("stdout", "")[-1500:])
    vtu = _finde_vtu(os.path.join(ctx["work_dir"], "results"))
    if not vtu:
        raise RuntimeError("Keine Ergebnisdatei geschrieben — "
                           "ResultOutputSolver pruefen")
    # ERST pruefen, ob es ueberhaupt ein Feld ist. Ein offener Strompfad gibt
    # keine Fehlermeldung, sondern Zahlen -- und die sehen aus wie Ergebnisse.
    feld = pruefe_feld(vtu)
    p_je_koerper = verluste_je_koerper(vtu)
    joule = sum(p_je_koerper.get(g, 0.0) for g in (GID_STAEBE, GID_RING))
    s = ctx["schlupf"]
    omega_syn_mech = ctx["omega1"] / ctx["p"]
    return {"P_luftspalt_W": round(joule, 1),
            "P_laeufer_W": round(s * joule, 1),
            "T_leistung_Nm": round(joule / max(omega_syn_mech, 1e-12), 3),
            "P_staebe_W": round(p_je_koerper.get(GID_STAEBE, 0.0), 1),
            "P_ringe_W": round(p_je_koerper.get(GID_RING, 0.0), 1),
            "B_max_T": feld["B_max_T"], "B_p999_T": feld["B_p999_T"],
            "wild_anteil_pct": feld["wild_anteil_pct"],
            # Die Zahl, an der 2-D und 3-D sich vergleichen lassen.
            "B_gap_1_T": round(luftspalt_grundwelle(vtu, ctx["netz"], ctx["p"]), 4),
            "vtu": vtu, "ring_leitet": ring_leitet}


def _aufbau(payload: dict, rpm: float, last_nm: float, work_dir: str,
            schlupf: float, mu_r_steg: float, gap_lagen: int,
            lagen_axial: int, lc_eisen_mm: float, log=None) -> dict:
    """Betriebspunkt, Netz und ElmerGrid -- alles, was beide Laeufe teilen."""
    import ema_asm
    import ema_maschinenart
    import ema_radien
    from ema_pipeline import HAIRPIN_MATS

    geom = payload.get("geom", payload)
    art = ema_maschinenart.art_code(payload)
    ema_maschinenart.pruefe_stufe(art, "em3d")
    ema_radien.pruefe_bauform(payload, "em3d")   # Netz ist auf Innenlaeufer gebaut
    if art != "asm":
        raise ema_maschinenart.ArtNichtUnterstuetzt(
            f"Die harmonische 3-D-Stufe ist die Kaefiglaeufer-Stufe; "
            f"'{art}' gehoert nicht hierher.")

    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    p = max(int(geom["p"]), 1)
    bp = ema_asm.betriebspunkt(geom, axial, rpm, last_nm)
    kf = dict(bp["kaefig"])
    kf["steg_mm"] = ema_asm.KAEFIG_STEG_MM
    s = max(float(schlupf) or float(bp["schlupf"]), H.S_MIN)
    mu = float(mu_r_steg) or H.MU_R_STEG

    mat = HAIRPIN_MATS.get(geom.get("barMat") or ema_asm.KAEFIG_VORGABE,
                           HAIRPIN_MATS[ema_asm.KAEFIG_VORGABE])
    sigma_eff = s * (1.0 / float(mat["rho_el"]))
    omega1 = 2.0 * math.pi * p * float(rpm) / 60.0

    netz = netzkosten(geom, kf, axial, work_dir, gap_lagen=gap_lagen,
                      lagen_axial=lagen_axial, lc_eisen_mm=lc_eisen_mm, log=log)
    mesh_dir = os.path.join(work_dir, "mesh")
    if log:
        log("ElmerGrid: 3-D-Netz umsetzen…")
    rg = elmer_runner.run_elmergrid(netz["msh"], mesh_dir)
    if not rg.get("ok"):
        raise RuntimeError("ElmerGrid: " + (rg.get("stderr") or rg.get("error", ""))[:300])
    # Derselbe Waechter wie in 2-D. Er fehlte hier, obwohl der Kommentar bei den
    # Gruppennummern ihn beschreibt: ``ElmerGrid -autoclean`` nummeriert die
    # Koerper um, und wenn die sif dann ins Leere zielt, gibt der Loeser ein
    # leeres Feld aus, ohne zu widersprechen.
    H.pruefe_koerpernummern(mesh_dir, GID_NUT0 - 1 + netz["n_nut"])

    i_pk_phys = float(bp["I_s_A"]) / max(ema_asm.k_norm(geom), 1e-12)
    return {"geom": geom, "p": p, "bp": bp, "netz": netz, "work_dir": work_dir,
            "omega1": omega1, "sigma_eff": sigma_eff, "schlupf": s,
            "mu_r_steg": mu, "axial_mm": axial,
            "j_nut": H.stator_stroeme(geom, i_pk_phys, netz["A_nut_m2"]),
            "stabmaterial": mat["label"], "i_pk_phys": i_pk_phys}


def ring_wirkung(payload: dict, rpm: float, last_nm: float, work_dir: str,
                 schlupf: float = 0.0, mu_r_steg: float = 0.0,
                 gap_lagen: int = 1, lagen_axial: int = 6,
                 lc_eisen_mm: float = 8.0, timeout: int = 7200,
                 log=None) -> dict:
    """Was der Kurzschlussring ausmacht -- zweimal dasselbe Netz, einmal ohne ihn.

    Der einzige Unterschied zwischen den beiden Laeufen ist die Leitfaehigkeit
    der Ringe. Netz, Betriebspunkt, Statorstrom, Schlupf, Steg-Permeabilitaet:
    identisch. Der Netzfehler eines nicht aufgeloesten Luftspalts steckt damit in
    beiden Zahlen gleich und faellt im Verhaeltnis weitgehend heraus.

    Verglichen wird gegen ``ema_asm.kurzschlussring_zuschlag`` -- den Wert, den
    die analytische Stufe fuer DIESE Geometrie rechnet. Bis zu dieser Messung
    stand dort eine Konstante (0,20), die nie gemessen war; sie lag um den Faktor
    vier daneben.
    """
    import ema_asm

    def _log(t):
        if log:
            log(t)

    ctx = _aufbau(payload, rpm, last_nm, work_dir, schlupf, mu_r_steg,
                  gap_lagen, lagen_axial, lc_eisen_mm, log=log)
    _log(f"ElmerSolver: 3-D harmonisch MIT Ring "
         f"({ctx['netz']['tets']} Tetraeder)…")
    mit = _loese(ctx, True, timeout)
    _log("ElmerSolver: derselbe Lauf OHNE Ring (Ringe isolierend)…")
    ohne = _loese(ctx, False, timeout)

    t_mit, t_ohne = mit["T_leistung_Nm"], ohne["T_leistung_Nm"]
    anteil = (t_mit - t_ohne) / max(abs(t_mit), 1e-12)
    # Der Ringverlust als Anteil des Stabverlusts -- WOERTLICH die Groesse, die
    # ``ema_asm.kurzschlussring_zuschlag`` ansetzt (dort: P_kaefig = P_stab *
    # (1 + Zuschlag)). Sie faellt in EINEM Lauf an, auf einem Netz, und braucht
    # den Vergleichslauf gar nicht -- der Vergleich sagt etwas anderes, naemlich
    # was der Ring am MOMENT aendert.
    ring_je_stab = mit["P_ringe_W"] / max(mit["P_staebe_W"], 1e-12)
    return {
        "T_mit_Ring_Nm": t_mit, "T_ohne_Ring_Nm": t_ohne,
        "P_mit_Ring_W": mit["P_luftspalt_W"], "P_ohne_Ring_W": ohne["P_luftspalt_W"],
        "P_staebe_W": mit["P_staebe_W"], "P_ringe_W": mit["P_ringe_W"],
        "ring_je_stab": round(ring_je_stab, 4),
        "ring_je_stab_pct": round(100.0 * ring_je_stab, 1),
        "B_gap_1_mit_T": mit["B_gap_1_T"], "B_gap_1_ohne_T": ohne["B_gap_1_T"],
        "ring_anteil": round(anteil, 4),
        "ring_anteil_pct": round(100.0 * anteil, 2),
        # Verglichen wird gegen den Wert, den die analytische Stufe FUER DIESE
        # Geometrie rechnet -- nicht mehr gegen eine Konstante. Genau diese
        # Messung hat die Konstante abgeloest.
        "zuschlag_analytisch_pct": round(
            100.0 * ema_asm.kurzschlussring_zuschlag(ctx["bp"]["kaefig"], ctx["p"]), 1),
        "schlupf": ctx["schlupf"], "mu_r_steg": ctx["mu_r_steg"],
        "f1_Hz": round(ctx["omega1"] / (2 * math.pi), 2),
        "tets": ctx["netz"]["tets"], "knoten": ctx["netz"]["knoten"],
        "netzzeit_s": ctx["netz"]["netzzeit_s"],
        "ring_h_mm": round(1000 * ctx["netz"]["ring_h_m"], 2),
        "ring_w_mm": round(1000 * ctx["netz"]["ring_w_m"], 2),
        "gap_aufgeloest": bool(ctx["netz"]["lc_gap_m"] <= ctx["netz"]["gap_m"]),
        "work_dir": work_dir, "analytisch": ctx["bp"],
    }


def rechne(payload: dict, rpm: float, last_nm: float, work_dir: str,
           schlupf: float = 0.0, mu_r_steg: float = 0.0, gap_lagen: int = 1,
           lagen_axial: int = 6, lc_eisen_mm: float = 8.0,
           timeout: int = 7200, log=None) -> dict:
    """EIN 3-D-Lauf. Das absolute Moment steht unter dem Vorbehalt des Netzes.

    Wer wissen will, was der Kurzschlussring ausmacht, nimmt ``ring_wirkung`` --
    dort faellt der Netzfehler im Verhaeltnis heraus. Diese Funktion gibt den
    einzelnen Lauf, und sie sagt im Ergebnis (``gap_aufgeloest``), ob der
    Luftspalt ueberhaupt aufgeloest war.
    """
    ctx = _aufbau(payload, rpm, last_nm, work_dir, schlupf, mu_r_steg,
                  gap_lagen, lagen_axial, lc_eisen_mm, log=log)
    if log:
        log(f"ElmerSolver: 3-D harmonisch, {ctx['netz']['tets']} Tetraeder, "
            f"{ctx['omega1'] / (2 * math.pi):.1f} Hz, "
            f"Schlupf {100 * ctx['schlupf']:.2f} %…")
    r = _loese(ctx, True, timeout)
    r.update({
        "schlupf": ctx["schlupf"], "mu_r_steg": ctx["mu_r_steg"],
        "f1_Hz": round(ctx["omega1"] / (2 * math.pi), 2),
        "sigma_eff_S_m": round(ctx["sigma_eff"], 1),
        "tets": ctx["netz"]["tets"], "knoten": ctx["netz"]["knoten"],
        "netzzeit_s": ctx["netz"]["netzzeit_s"],
        "ring_h_mm": round(1000 * ctx["netz"]["ring_h_m"], 2),
        "ring_w_mm": round(1000 * ctx["netz"]["ring_w_m"], 2),
        "gap_aufgeloest": bool(ctx["netz"]["lc_gap_m"] <= ctx["netz"]["gap_m"]),
        "work_dir": work_dir, "analytisch": ctx["bp"],
    })
    return r


# Groesste Flussdichte, die in einer Maschine noch vorstellbar ist. Kobalt-Eisen
# saettigt bei rund 2,3 T; an einer Kante rechnet ein P1-Netz auch einmal das
# Doppelte. 20 T ist also grosszuegig um den Faktor zehn -- wer darueber liegt,
# hat kein Feld, sondern einen Rechenfehler. Genau dieser Fall ist hier
# eingetreten (gemessen 2,7*10^6 T, s. Modulkopf).
B_UNMOEGLICH_T = 20.0

# Wieviel Volumen ueber dieser Schranke liegen darf, bevor das Ergebnis
# verworfen wird. Nicht null: an einer Nutecke rechnet ein P1-Netz auf einem
# einzelnen Element auch einmal 40 T, und das tut es in einem gesunden Feld
# ebenso wie in einem kranken. Gemessen liegen die beiden Faelle vier
# Zehnerpotenzen auseinander (0,001 % gegen 12,6 %), s. ``pruefe_feld``.
WILD_ANTEIL = 0.001

# Untergrenze: unterhalb dieser Flussdichte ist gar kein Feld gerechnet worden.
# Der Waechter fing bis hierher nur den Fall „zu wild" ab -- den Fall „gar
# nichts" nicht, und der sieht von aussen wie ein Ergebnis aus.
#
# Der Anlass, gemessen an einem 1,1-Mio.-Netz: MUMPS steigt mit
# „** ERROR RETURN ** FROM ZMUMPS INFO(1)= -13" (Speicher) aus, Elmer rechnet
# mit einem Nullvektor weiter, meldet ordnungsgemaess FINISHED, schreibt eine
# VTU -- und die Auswertung meldete 0,0 W Verlust und 0,000 Nm Moment.
#
# **Gefangen wird dieser Fall in ``elmer_runner``** (der MUMPS-Code ist
# eindeutig, und dort steht er am Entstehungsort). Diese Schranke ist der
# zweite Riegel und faengt WENIGER: im gemessenen Fall blieben immerhin
# 0,1428 T stehen, sie haette also nicht ausgeloest. Sie greift nur, wenn
# wirklich nichts uebrig ist. Das steht hier, damit niemand sie fuer den
# vollstaendigen Schutz haelt.
B_LEER_T = 1.0e-3


def _finde_vtu(ordner: str) -> str:
    """Die juengste Ergebnisdatei im Ausgabeordner."""
    if not os.path.isdir(ordner):
        return ""
    treffer = sorted(f for f in os.listdir(ordner) if f.endswith(".vtu"))
    return os.path.join(ordner, treffer[-1]) if treffer else ""


def _lies_vtu_zellen(vtu_pfad: str):
    """Zellwerte der Ergebnisdatei: Koerper-Id, Volumen, Joule-Dichte, |B|.

    Ausgewertet werden die ZELLfelder (``… e``), nicht die Knotenfelder: die
    Joule-Dichte ist eine Groesse je Element, und ihr Volumenintegral ist die
    Verlustleistung. Ueber die Knoten gemittelt waere sie das nicht.
    """
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    rd = vtk.vtkXMLUnstructuredGridReader()
    rd.SetFileName(vtu_pfad)
    rd.Update()
    grid = rd.GetOutput()
    cd = grid.GetCellData()

    def hole(name):
        a = cd.GetArray(name)
        return vtk_to_numpy(a) if a is not None else None

    gid = hole("GeometryIds")
    if gid is None:
        raise KeyError("GeometryIds fehlen in der VTU "
                       "(Save Geometry Ids = Logical True gesetzt?)")
    joule = hole("joule heating e")
    b_re, b_im = hole("magnetic flux density re e"), hole("magnetic flux density im e")

    # Tetraedervolumen vektorisiert. Die naheliegende Schleife ueber
    # ``grid.GetCell(i)`` legt je Zelle vier numpy-Arrays an; bei 52.000 Zellen
    # ist das der langsamste Teil der ganzen Auswertung — und er steht hinter
    # einem Loeserlauf, faellt also erst auf, wenn man schon gewartet hat.
    pts3 = vtk_to_numpy(grid.GetPoints().GetData())
    cells = grid.GetCells()
    conn = vtk_to_numpy(cells.GetConnectivityArray())
    offs = vtk_to_numpy(cells.GetOffsetsArray())
    laenge = np.diff(offs)
    n = grid.GetNumberOfCells()
    vol = np.zeros(n)
    tet = laenge == 4
    if tet.any():
        idx = conn[np.repeat(offs[:-1][tet], 4) + np.tile(np.arange(4), int(tet.sum()))]
        q = pts3[idx].reshape(-1, 4, 3)
        vol[tet] = np.abs(np.einsum("ij,ij->i", q[:, 1] - q[:, 0],
                                    np.cross(q[:, 2] - q[:, 0], q[:, 3] - q[:, 0]))) / 6.0

    ctr = np.zeros((n, 3))
    if tet.any():
        ctr[tet] = q.mean(axis=1)

    b_abs = None
    if b_re is not None and b_im is not None:
        b_abs = np.sqrt((b_re ** 2).sum(axis=1) + (b_im ** 2).sum(axis=1))
    return {"gid": gid.astype(np.int64), "vol": vol, "joule": joule,
            "B_abs": b_abs, "B_re": b_re, "B_im": b_im, "ctr": ctr, "tet": tet}


def pruefe_feld(vtu_pfad: str) -> dict:
    """Ist das gerechnete Feld ueberhaupt eines? Sonst ein klarer Fehler.

    Ein offener Strompfad gibt in 3-D keine Fehlermeldung, sondern ein
    Vektorpotential, das ins Unermessliche laeuft -- und daraus dann Momente und
    Verluste, die wie Zahlen aussehen. Diese Pruefung faengt das ab, BEVOR eine
    einzige Kennzahl gebildet wird.

    Gemessen wird der VOLUMENANTEIL ueber der Schranke, nicht das Maximum. Der
    Grund steht in ``ema_em2d_harm.kennzahlen`` schon einmal: an einer Nutecke
    steht auf einem einzigen Element ein Gradientensprung -- dort wurden in 2-D
    56 T gemessen, in einem Feld, dessen beide Momentwege auf 0,00 % passen. Ein
    Maximum verwirft ein gesundes Ergebnis wegen eines Splitters; ein
    Volumenanteil sagt, ob das FELD krank ist. Gemessen an dieser Maschine:

        Nutstrom endet in der Stirnluft   12,6 % des Volumens ueber 20 T
        Nutleiter bis auf den Rand         0,001 %  (groesstes Element 39,6 T)

    Zwischen den beiden liegen vier Zehnerpotenzen -- die Schranke muss sie also
    nicht fein treffen.
    """
    import numpy as np
    d = _lies_vtu_zellen(vtu_pfad)
    if d["B_abs"] is None:
        raise RuntimeError("Die Ergebnisdatei enthaelt keine Flussdichte — "
                           "MagnetoDynamicsCalcFields hat nicht gerechnet.")
    b, vol, tet = d["B_abs"], d["vol"], d["tet"]
    v_ges = float(vol.sum()) or 1.0
    anteil = float(vol[(b > B_UNMOEGLICH_T) & tet].sum()) / v_ges
    b_max = float(np.max(b[tet])) if tet.any() else 0.0
    o = np.argsort(b[tet])
    w = np.cumsum(vol[tet][o])
    b_p999 = float(b[tet][o][int(np.searchsorted(w, 0.999 * w[-1]))]) if tet.any() else 0.0
    if b_max < B_LEER_T:
        raise RuntimeError(
            f"Es ist gar kein Feld gerechnet worden: groesste Flussdichte im "
            f"ganzen Modell {b_max:.3g} T. Der Statorstrom ist eingepraegt, "
            f"also kann das kein Ergebnis sein — der Loeser hat abgebrochen und "
            f"Elmer mit einem Nullvektor weitergerechnet. Haeufigste Ursache: "
            f"MUMPS ohne genug Arbeitsspeicher (Netz zu gross).")
    if anteil > WILD_ANTEIL:
        raise RuntimeError(
            f"Das Feld ist keines: {100 * anteil:.2f} % des Volumens liegen "
            f"ueber {B_UNMOEGLICH_T:.0f} T (groesster Wert {b_max:.3g} T, "
            f"99,9. Perzentil {b_p999:.3g} T). Erlaubt sind "
            f"{100 * WILD_ANTEIL:.2f} %. Die Feldstufe dieser Bauart traegt "
            f"dann weiterhin cae_cli.py feld2d (Elmer 2-D).")
    return {"B_max_T": round(b_max, 4), "B_p999_T": round(b_p999, 4),
            "wild_anteil_pct": round(100 * anteil, 4),
            "zellen": int(len(d["gid"]))}


def luftspalt_grundwelle(vtu_pfad: str, netz: dict, p: int) -> float:
    """Die p-te Raumharmonische von ``B_r`` im Luftspalt, in der Paketmitte [T].

    Dieselbe Groesse wie ``ema_em2d_harm.kennzahlen``: der komplexe Zeiger, ohne
    Faktor 2 (eine umlaufende Welle, kein reeller Kosinus). Damit ist sie die
    EINE Zahl, an der 2-D und 3-D sich vergleichen lassen -- und die Probe
    dafuer, dass die 3-D-Stufe dieselbe Maschine rechnet.

    Genommen wird nur das mittlere Halbe des Pakets: an den Paketenden zieht die
    Stirnstreuung das Feld herunter, und das ist ein wirklicher Unterschied zur
    2-D-Stufe, kein Fehler -- er gehoert aber nicht in die Vergleichszahl.
    """
    import numpy as np
    d = _lies_vtu_zellen(vtu_pfad)
    if d["B_re"] is None:
        return 0.0
    L = float(netz["L_m"])
    m = (d["gid"] == GID_LUFT) & d["tet"] & (np.abs(d["ctr"][:, 2] - 0.5 * L) < 0.25 * L)
    if not m.any():
        return 0.0
    x, y = d["ctr"][m, 0], d["ctr"][m, 1]
    r = np.hypot(x, y)
    r = np.where(r < 1e-12, 1e-12, r)
    cs, sn = x / r, y / r
    br = ((d["B_re"][m, 0] * cs + d["B_re"][m, 1] * sn)
          + 1j * (d["B_im"][m, 0] * cs + d["B_im"][m, 1] * sn))
    w = d["vol"][m]
    th = np.arctan2(y, x)
    return float(abs(np.sum(br * np.exp(1j * max(int(p), 1) * th) * w)
                     / max(w.sum(), 1e-30)))


def verluste_je_koerper(vtu_pfad: str) -> dict:
    """Verlustleistung [W] je Koerper -- Volumenintegral der Joule-Dichte.

    Frueher wurde die Joule-Leistung aus der **Bildschirmausgabe** von Elmer
    gelesen. Sie steht dort nicht: gemessen schreibt dieser Elmer keine Zeile
    „Joule Heating" auf stdout, und die Auswertung gab darum immer 0,0 W --
    kommentarlos, und daraus dann ein Moment von 0,000 Nm. Eine angenommene
    Ausgabe ist keine Schnittstelle; die Ergebnisdatei ist eine.
    """
    import numpy as np
    d = _lies_vtu_zellen(vtu_pfad)
    gid, vol, joule = d["gid"], d["vol"], d["joule"]
    if joule is None:
        raise KeyError("'joule heating e' fehlt in der VTU — "
                       "Calculate Joule Heating im Solver gesetzt?")
    aus = {}
    for k in np.unique(gid):
        m = gid == k
        aus[int(k)] = float(np.sum(joule[m] * vol[m]))
    return aus


def bericht(kz: dict) -> str:
    """Was der Kurzschlussring ausmacht -- die Zahl, fuer die es Stufe D gibt."""
    z = []
    z.append(f"ASM-Feld harmonisch in 3-D (Elmer), {kz['f1_Hz']:.1f} Hz, "
             f"Schlupf {100 * kz['schlupf']:.2f} %")
    z.append(f"  Netz  {kz['tets']} Tetraeder, {kz['knoten']} Knoten, "
             f"{kz['netzzeit_s']:.0f} s. Ring "
             f"{kz['ring_h_mm']:.1f} x {kz['ring_w_mm']:.1f} mm.")
    if kz.get("B_gap_1_mit_T") is not None:
        z.append(f"  Luftspalt-Grundwelle {kz['B_gap_1_mit_T']:.4f} T "
                 f"(die Zahl, an der sich 2-D und 3-D vergleichen lassen).")
    if not kz.get("gap_aufgeloest", False):
        z.append("  ACHTUNG: der Luftspalt ist in diesem Netz NICHT aufgeloest. "
                 "Das absolute Moment ist damit keine Aussage; die Verhaeltnisse "
                 "unten schon.")
    z.append(f"  Stabverlust {kz['P_staebe_W']:9.1f} W")
    z.append(f"  Ringverlust {kz['P_ringe_W']:9.1f} W")
    z.append(f"  -> Der Ring kostet {kz['ring_je_stab_pct']:.1f} % des "
             f"Stabverlusts. ema_asm setzt "
             f"{kz['zuschlag_analytisch_pct']:.0f} % an "
             f"(kurzschlussring_zuschlag).")
    z.append(f"     Das ist der Faktor "
             f"{kz['ring_je_stab'] / max(0.01 * kz['zuschlag_analytisch_pct'], 1e-9):.1f}. "
             f"Der Ringanteil haengt an der Paketlaenge: je kuerzer das Paket, "
             f"desto mehr Ring je Stab. Ein fester Zuschlag kann das nicht "
             f"treffen.")
    z.append(f"  Moment MIT  Kurzschlussring {kz['T_mit_Ring_Nm']:9.3f} Nm")
    z.append(f"  Moment OHNE Kurzschlussring {kz['T_ohne_Ring_Nm']:9.3f} Nm")
    z.append("     Der zweite Wert ist KEIN „Kaefig ohne Ring\u201c: mit "
             "isolierenden Ringen kann der Stabstrom seinen Kreis gar nicht "
             "schliessen, es gibt also keinen Kaefig. Der Vergleich zeigt "
             "damit, dass das Modell den Ring wirklich fuehrt -- die Zahl, die "
             "ema_asm braucht, steht darueber.")
    return "\n".join(z)
