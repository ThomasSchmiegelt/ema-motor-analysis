"""Magnetostatik in Elmer 2-D -- die Gegenrechnung zum hauseigenen FDM.

Wozu ein zweiter Loeser neben ``ema_em2d_harm``: der dort ist **harmonisch**
und fuer den Kaefig gebaut (``MagnetoDynamics2DHarmonic``, Kreisfrequenz,
Leitfaehigkeit je Koerper).  SynRM und EESM sind aber magnetostatisch -- im
Laeufer fliesst kein induzierter Strom, die Erregerwicklung fuehrt
Gleichstrom.  Sie durch den harmonischen Loeser zu schicken hiesse, ein
Zeitverhalten zu rechnen, das es nicht gibt.  Getrennt wie ``ema_em3d`` und
``ema_em3d_harm``, und aus demselben Grund.

**Wozu es dieses Modul ueberhaupt gibt.**  Seit dem 20.09.2026 baut
``ema_analysis._rasterise`` den Laeufer einer magnetlosen Bauart aus
``ema_laeuferbild.teile()`` -- derselben Quelle, aus der die Leinwand zeichnet.
Damit rechnet der FDM zum ersten Mal die richtige Maschine.  Ob er sie auch
richtig rechnet, sagt das nicht: Bild und Feld koennen jetzt nicht mehr
auseinanderlaufen, aber sie koennen gemeinsam daneben liegen.  Dafuer braucht
es einen zweiten Loeser, der dieselbe Geometrie **unabhaengig** aufbaut --
hier als koerperangepasstes Dreiecksnetz statt als kartesisches Raster.

**Was verglichen werden DARF, und was nicht.**  Der FDM eicht seine Amplitude
auf ``_analytical_Bgap`` -- eine Magnetformel, die fuer eine magnetlose
Maschine gemessen dieselben 0,63 T liefert wie fuer die PSM daneben (der
Ausdruck kennt die Maschinenart nicht).  Ein Vergleich der absoluten Hoehe
waere deshalb kein Vergleich, sondern das Nachmessen einer Konstanten.
Belastbar sind die Groessen, die **keine** Eichung tragen:

* die **FORM** der Luftspaltwelle ``B_r(theta)``, jede Seite auf ihren eigenen
  Effektivwert normiert -- sie haengt allein an Geometrie und Loeser;
* das **Verhaeltnis zweier Betriebspunkte** desselben Laeufers, weil sich der
  Eichfaktor darin herauskuerzt.  Beim SynRM ist genau das die Bauart: die
  Grundwelle bei Staenderdurchflutung in der d-Achse gegen die in der q-Achse.

Damit der Unterschied wirklich Geometrie und Verfahren misst und nicht die
Werkstoffannahme, rechnet dieses Modul mit **demselben linearen Eisen wie der
FDM** (``ema_analysis.MU_R_IRON``, ohne Saettigungsdurchgang).  Das ist keine
Aussage ueber die Wirklichkeit -- es ist die Bedingung dafuer, dass die
Abweichung zuzuordnen ist.
"""

from __future__ import annotations

import math
import os

#: Ab welchem Anteil der Laeuferflaeche ein unbelegter Rest noch ein eigener
#: Koerper ist. Darunter sind es Rundungssplitter der Booleschen Operationen,
#: und ein Splitter als physikalische Gruppe laesst `zuordnen` abbrechen.
REST_MIN_ANTEIL = 1e-3

MU0 = 4.0e-7 * math.pi

# Eisen linear -- BEWUSST derselbe Wert wie ``ema_analysis.MU_R_IRON``.  Er
# wird von dort gelesen und nicht danebengeschrieben: eine zweite Konstante
# waere genau der stille Faktor, der die Messung wertlos machte.
from ema_analysis import MU_R_IRON as MU_R_EISEN          # noqa: E402

GAP_LAGEN = 6

# Wieviele Luftspaltdreiecke ein Winkelfach mindestens bekommt.
MIN_JE_FACH = 6

# Rollen aus ``ema_laeuferbild`` -> was sie magnetisch sind.  ``pol`` ist der
# Schenkelpolkoerper, also Eisen; ``luft``/``kupfer``/``alu`` sind es nicht
# (mu_r ~ 1, s. ``ema_laeuferbild.UNMAGNETISCH``).
ROLLE_EISEN = ("eisen", "pol")


# ── Geometrie: die Formen aus ``ema_laeuferbild`` als OCC-Flaechen ───────────

def _ring(occ, r_i: float, r_a: float) -> int:
    a = occ.addDisk(0, 0, 0, r_a, r_a)
    if r_i <= 0:
        return a
    i = occ.addDisk(0, 0, 0, r_i, r_i)
    out, _ = occ.cut([(2, a)], [(2, i)])
    return out[0][1]


def _keil(occ, g0: float, g1: float, r_gross: float) -> int:
    """Kreissektor als Polygon -- Ursprung plus Bogenpunkte auf ``r_gross``.

    Nicht als Dreieck: bei grossen Oeffnungswinkeln laege dessen Aussenkante
    als Sehne innerhalb von ``r_gross`` und schnitte den Sektor an.  Mit einem
    Punkt alle 5 Grad liegt die Polygonkante ueberall ueber 0,999*r_gross, und
    ``r_gross`` ist ohnehin mit Zuschlag gewaehlt.
    """
    n = max(2, int(math.ceil(abs(g1 - g0) / math.radians(5.0))))
    pts = [occ.addPoint(0.0, 0.0, 0.0)]
    for i in range(n + 1):
        a = g0 + (g1 - g0) * i / n
        pts.append(occ.addPoint(r_gross * math.cos(a), r_gross * math.sin(a), 0.0))
    lin = [occ.addLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    lin.append(occ.addLine(pts[-1], pts[0]))
    return occ.addPlaneSurface([occ.addCurveLoop(lin)])


#: Zwei Ecken naeher beieinander als das sind EINE Ecke (Meter, also 1 nm).
#: Weit unter jeder Zeichengroesse hier und weit ueber dem Rundungsrauschen
#: der Drehung, die jede Ecke durchlaeuft.
_ECKE_GLEICH_M = 1e-9


def _polygon(occ, ecken) -> int:
    """Ein Polygonzug als OCC-Flaeche -- **entartete Ecken fallen heraus**.

    Ein Zeichenteil ist nicht notwendig ein Viereck: die Zwischenpolluft des
    Schenkelpollaeufers kommt als ``trapez`` mit der inneren Breite **null**
    herein (``y0i = -0.0``, ``y1i = 0.0``), ist also ein DREIECK. Fuer den
    Rasterer ist das harmlos -- er prueft Punkt-in-Polygon, und eine doppelte
    Ecke aendert daran nichts. ``occ.addLine`` auf zwei gleiche Punkte
    dagegen scheitert mit ``Could not create line``, und zwar erst beim
    Netzbau: gemessen am 20.09.2026 brach die EESM in ``vorbereiten`` ab,
    waehrend Leinwand und FDM-Raster dieselbe Geometrie klaglos zeichneten.

    Das ist genau die Sorte Fehler, gegen die der Kopf dieser Datei warnt --
    dieselbe Geometrie in drei Fassungen, und nur eine davon ist empfindlich.
    Behoben wird sie deshalb HIER, im gemeinsamen Polygonbauer, und nicht im
    ``trapez``-Zweig: jede kuenftige Form kann eine entartete Ecke liefern.
    """
    ecken = list(ecken)
    sauber = []
    for x, y in ecken:
        if sauber and (abs(x - sauber[-1][0]) < _ECKE_GLEICH_M
                       and abs(y - sauber[-1][1]) < _ECKE_GLEICH_M):
            continue
        sauber.append((x, y))
    # Der Ringschluss zaehlt mit: die letzte Ecke darf nicht auf der ersten
    # liegen, sonst entsteht dieselbe Nulllinie beim Schliessen des Zuges.
    while len(sauber) > 1 and (abs(sauber[-1][0] - sauber[0][0]) < _ECKE_GLEICH_M
                               and abs(sauber[-1][1] - sauber[0][1]) < _ECKE_GLEICH_M):
        sauber.pop()
    if len(sauber) < 3:
        raise ValueError(
            f"Zeichenteil ohne Flaeche: {len(sauber)} verschiedene Ecken aus "
            f"{len(ecken)} -- das ist eine Linie, kein Koerper.")

    pts = [occ.addPoint(x, y, 0.0) for (x, y) in sauber]
    lin = [occ.addLine(pts[i], pts[(i + 1) % len(pts)]) for i in range(len(pts))]
    return occ.addPlaneSurface([occ.addCurveLoop(lin)])


def teil_flaeche(occ, t: dict, mm_m: float = 1e-3) -> int:
    """EIN Zeichenteil als OCC-Flaeche, in Metern.

    Die Formen sind zeichengetreu die aus ``ema_laeuferbild._stempel`` bzw.
    ``ema_laeufer.js`` -- dieselben Felder, dieselbe Reihenfolge der Drehungen.
    Das ist die dritte Fassung derselben Geometrie (Leinwand, FDM-Raster,
    hier), und sie ist wie die zweite gegen die erste festgenagelt: die
    Flaeche, die hier herauskommt, muss die des gerasterten Teils sein
    (``test_em2d_stat.py``).
    """
    form = str(t.get("form"))
    grad = math.radians(float(t.get("grad") or 0.0))

    if form == "ring":
        return _ring(occ, float(t["r_i"]) * mm_m, float(t["r_a"]) * mm_m)

    if form == "segment":
        r_a = float(t["r_a"]) * mm_m
        r_i = max(r_a - float(t["dicke"]) * mm_m, 1e-6)
        halb = math.radians(float(t["halb"]))
        if halb >= math.pi - 1e-9:
            return _ring(occ, r_i, r_a)
        ring = _ring(occ, r_i, r_a)
        keil = _keil(occ, grad - halb, grad + halb, r_a * 1.5)
        out, _ = occ.intersect([(2, ring)], [(2, keil)])
        return out[0][1]

    if form in ("rechteck", "trapez"):
        r0, r1 = float(t["r0"]) * mm_m, float(t["r1"]) * mm_m
        if form == "rechteck":
            y0i = y0a = float(t["y0"]) * mm_m
            y1i = y1a = float(t["y1"]) * mm_m
        else:
            y0i, y1i = float(t["y0i"]) * mm_m, float(t["y1i"]) * mm_m
            y0a, y1a = float(t["y0a"]) * mm_m, float(t["y1a"]) * mm_m
        ca, sa = math.cos(grad), math.sin(grad)

        def g(r, w):
            return (r * ca - w * sa, r * sa + w * ca)

        return _polygon(occ, [g(r0, y0i), g(r1, y0a), g(r1, y1a), g(r0, y1i)])

    if form == "tasche":
        lng = float(t["laenge"]) * mm_m
        hr = float(t["hoehe"]) * mm_m / 2.0
        rect = occ.addRectangle(0.0, -hr, 0.0, max(lng, 1e-9), 2.0 * hr)
        k0 = occ.addDisk(0.0, 0.0, 0.0, hr, hr)
        k1 = occ.addDisk(lng, 0.0, 0.0, hr, hr)
        out, _ = occ.fuse([(2, rect)], [(2, k0), (2, k1)])
        s = out[0][1]
        occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, math.radians(float(t["tilt_grad"])))
        occ.translate([(2, s)], float(t["r_pos"]) * mm_m,
                      float(t["offset"]) * mm_m, 0.0)
        occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, grad)
        return s

    if form == "polygon":
        # Die Flussbarriere des Reluktanzlaeufers -- ein Polygonzug im
        # gedrehten Rahmen wie Rechteck und Trapez.
        ca, sa = math.cos(grad), math.sin(grad)
        return _polygon(occ, [((u * ca - v * sa) * mm_m, (u * sa + v * ca) * mm_m)
                              for u, v in t["punkte"]])

    if form == "kreis":
        return occ.addDisk(float(t["cx"]) * mm_m, float(t["cy"]) * mm_m, 0.0,
                           float(t["r"]) * mm_m, float(t["r"]) * mm_m)

    raise ValueError(f"unbekannte Form '{form}'")


# ── Netz ─────────────────────────────────────────────────────────────────────

def baue_netz(geom: dict, msh_pfad: str, axial_mm: float | None = None,
              gap_lagen: int = GAP_LAGEN, lc_eisen_mm: float = 0.0,
              teile: list | None = None) -> dict:
    """2-D-Querschnitt in Metern nach ``msh_pfad`` (MSH 2.2 fuer ElmerGrid).

    Der Laeufer kommt aus ``ema_laeuferbild.teile()`` -- **derselben** Quelle
    wie Leinwand und FDM-Raster.  Ein eigener Laeuferbauer waere die vierte
    Fassung derselben Geometrie, und dann verglichen zwei Loeser zwei
    Maschinen.

    Die Koerpernummern werden **fortlaufend ab 1** vergeben: ElmerGrid
    nummeriert sonst um, und eine ``Target Bodies``-Zeile ins Leere meldet der
    Loeser nicht -- er rechnet ein Feld ohne Quellen (s.
    ``ema_em2d_harm.pruefe_koerpernummern``).
    """
    import gmsh
    import ema_em3d
    import ema_laeuferbild as LB

    r_wel = float(geom["shaftD"]) / 2000.0
    r_rot = float(geom["rotorOD"]) / 2000.0
    r_si = float(geom["statorID"]) / 2000.0
    r_so = float(geom["statorOD"]) / 2000.0
    if r_si <= r_rot:
        raise ValueError(f"Luftspalt nicht positiv: rotorOD={geom['rotorOD']} "
                         f"statorID={geom['statorID']}")

    # `teile=[]` ist der **glatte Laeufer**: Vollzylinder aus Blech, keine
    # Taschen, keine Pole.  Das ist der Bezugsfall mit bekannter Antwort --
    # dort MUSS die Luftspaltwelle bei Staenderdurchflutung in d- und in
    # q-Richtung dieselbe Amplitude haben (ein glatter Laeufer hat keine
    # Vorzugsrichtung).  Ohne so einen Fall waere jede gemessene Salienz eine
    # Behauptung ueber einen Loeser, den niemand geprueft hat.
    if teile is None:
        lb = LB.teile(geom, axial_mm)
        if lb.get("fehler"):
            raise ValueError(f"Laeufergeometrie: {lb['fehler']}")
        laeufer = list(lb.get("teile") or [])
        if not laeufer:
            raise ValueError(
                f"Die Bauart '{lb.get('art')}' liefert keine Laeuferteile -- "
                f"dieser Loeser ist fuer die magnetlosen Bauarten gebaut; eine "
                f"PSM rechnet die Pipeline ueber `ema_analysis`/`ema_em3d`.")
    else:
        lb = {"art": "glatt"}
        laeufer = list(teile)

    gmsh.initialize(interruptible=False)   # s. `ema_em3d`: ohne die Flagge
    # setzt gmsh einen Signalhandler, und das geht nur im Hauptthread --
    # aus einem Flask-Arbeiter scheitert die Vernetzung mit "signal only
    # works in main thread of the main interpreter". Also genau dann, wenn
    # der Weg im BROWSER benutzt wird, und nie im Test.
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add("stat2d")
        occ = gmsh.model.occ

        nuten = ema_em3d.slot_rects(geom)
        if not nuten:
            raise ValueError("Statornuten fehlen (slots/slotDepth)")

        welle = occ.addDisk(0, 0, 0, r_wel, r_wel)
        rotor = _ring(occ, r_wel, r_rot)
        luft = _ring(occ, r_rot, r_si)
        stator = _ring(occ, r_si, r_so)

        lt = [teil_flaeche(occ, t) for t in laeufer]
        nut_tags = []
        for n in nuten:
            s = occ.addRectangle(-float(n["length"]) / 2000.0,
                                 -float(n["thick"]) / 2000.0, 0.0,
                                 float(n["length"]) / 1000.0,
                                 float(n["thick"]) / 1000.0)
            occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, float(n["ang"]))
            occ.translate([(2, s)], float(n["cx"]) / 1000.0,
                          float(n["cy"]) / 1000.0, 0)
            nut_tags.append(s)

        fest = [welle, rotor, luft, stator]
        eingang = fest + lt + nut_tags
        _, abb = occ.fragment([(2, eingang[0])], [(2, t) for t in eingang[1:]])
        occ.synchronize()
        aus = [[t for (d, t) in grp if d == 2] for grp in abb]

        f_rotor, f_stator = set(aus[1]), set(aus[3])
        # Nur der Anteil, der WIRKLICH im Laeuferblech liegt.  Ein Teil, das
        # ueber den Rand ragte, kaeme sonst als Luftspaltkoerper heraus --
        # derselbe Riegel wie in ``ema_em2d_harm.quer_flaechen``.
        # **Was spaeter in der Liste steht, gewinnt** -- dieselbe Regel wie in
        # `ema_laeufer.zeichne` und `ema_laeuferbild.rastere`. Ueberlappen sich
        # zwei Teile (beim Schenkelpol schneidet die Zwischenpolluft unter dem
        # Schuh in den Schuh), gehoert die gemeinsame Flaeche dem SPAETEREN.
        # Ohne diese Regel haengt dieselbe Flaeche in zwei physikalischen
        # Gruppen, und welche Elmer nimmt, entscheidet niemand.
        lt_f, vergeben = [None] * len(lt), set()
        for j in range(len(lt) - 1, -1, -1):
            eigen = sorted(f_rotor.intersection(aus[4 + j]) - vergeben)
            lt_f[j] = eigen
            vergeben.update(eigen)
        nut_f = [sorted(f_stator.intersection(aus[4 + len(lt) + k]))
                 for k in range(len(nut_tags))]
        fehlend = [k for k, f in enumerate(nut_f) if not f]
        if fehlend:
            raise ValueError(f"{len(fehlend)} Statornuten liegen nicht im "
                             f"Statorblech -- slotDepth pruefen")

        belegt = set()
        for f in lt_f + nut_f:
            belegt.update(f)

        # Nummern fortlaufend ab 1 -- s. Docstring.
        gid = {}
        lauf = [0]

        flaeche = {}

        def gruppe(flaechen, name):
            if not flaechen:
                return 0
            lauf[0] += 1
            f = sorted(set(flaechen))
            gmsh.model.addPhysicalGroup(2, f, lauf[0], name)
            gid[name] = lauf[0]
            # Flaeche UND Schwerpunkt sind der Griff, an dem die Gruppe nach
            # ElmerGrid wiedererkannt wird -- s. `zuordnen`. Die Flaeche allein
            # genuegt nicht: die 54 Statornuten sind flaechengleich, und der
            # Schwerpunkt von Luftspaltring und Laeuferblech liegt beidemal im
            # Ursprung. Erst zusammen sind sie eindeutig.
            ms = [occ.getMass(2, x) for x in f]
            cs = [occ.getCenterOfMass(2, x) for x in f]
            a_ = sum(ms) or 1e-30
            flaeche[name] = (sum(ms),
                             sum(m * c[0] for m, c in zip(ms, cs)) / a_,
                             sum(m * c[1] for m, c in zip(ms, cs)) / a_)
            return lauf[0]

        gruppe(aus[0], "welle")
        # ``rotoreisen`` ist eine RESTgruppe: das Laeuferblech, soweit es nicht
        # von einem Zeichenteil belegt ist. Beim Schenkelpollaeufer kacheln die
        # Teile (12 Polschuhe, 12 Kerne, 12 Spulen, Jochring) die Scheibe
        # vollstaendig -- uebrig bleiben nur Rundungssplitter. Gemessen am
        # 06.10.2026: 2,2 mm^2 bei einem Laeufer von 27.936 mm^2, also 0,008 %.
        #
        # Daraus eine physikalische Gruppe zu machen heisst, ElmerGrid einen
        # Koerper zu geben, den `zuordnen` hinterher nicht wiedererkennen kann
        # (Flaeche und Schwerpunkt eines Splitters am Ursprung sind kein Griff)
        # -- und dann bricht der Lauf ab, obwohl die Geometrie in Ordnung ist.
        # Ein Rest unter `REST_MIN_ANTEIL` ist deshalb KEIN Koerper, und das
        # steht im Ergebnis statt dass es verschwiegen wird.
        _rest = sorted(f_rotor - belegt)
        _a_rest = sum(occ.getMass(2, x) for x in _rest) if _rest else 0.0
        _a_rotor = sum(occ.getMass(2, x) for x in sorted(f_rotor)) or 1e-30
        if _rest and _a_rest / _a_rotor < REST_MIN_ANTEIL:
            _rest_befund = (
                f"Laeuferblech restlos von den Zeichenteilen belegt: "
                f"{_a_rest:.2f} mm^2 Rest bei {_a_rotor:.0f} mm^2 "
                f"({_a_rest / _a_rotor * 100:.3f} %) — keine eigene Gruppe "
                f"`rotoreisen`. Das Blech steckt in `laeuferpole`.")
            _rest = []
        else:
            _rest_befund = ""
        gruppe(_rest, "rotoreisen")
        # Eisenteile des Laeufers (Schenkelpol) gehoeren magnetisch zum Blech,
        # bekommen aber eine eigene Gruppe: so ist im Ergebnis nachzusehen, ob
        # der Pol ueberhaupt getroffen wurde.
        eisen_t = [f for j, f in enumerate(lt_f)
                   if str(laeufer[j].get("rolle")) in ROLLE_EISEN]
        gruppe([x for f in eisen_t for x in f], "laeuferpole")
        # Alles Unmagnetische OHNE Strom in EINE Gruppe -- magnetisch sind
        # Luft, Kupfer und Alu dasselbe.
        still = [f for j, f in enumerate(lt_f)
                 if str(laeufer[j].get("rolle")) not in ROLLE_EISEN
                 and abs(float(laeufer[j].get("durchflutung_A") or 0.0)) < 1e-9]
        gruppe([x for f in still for x in f], "laeuferluft")
        gruppe(aus[2], "luftspalt")
        gruppe(sorted(f_stator - belegt), "statoreisen")

        # Jede stromfuehrende Laeuferspule und jede Nut braucht eine EIGENE
        # Gruppe: jede traegt ihre eigene Stromdichte.
        spulen = []
        for j, f in enumerate(lt_f):
            a = float(laeufer[j].get("durchflutung_A") or 0.0)
            if abs(a) < 1e-9 or not f:
                continue
            g = gruppe(f, f"spule{len(spulen)}")
            spulen.append({"gid": g, "A": a,
                           "flaeche_m2": sum(gmsh.model.occ.getMass(2, x) for x in f)})
        nut_gid = []
        for k, f in enumerate(nut_f):
            nut_gid.append(gruppe(f, f"nut{k}"))

        rand = []
        for (d, t) in gmsh.model.getEntities(1):
            bb = gmsh.model.getBoundingBox(1, t)
            weite = max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0
            if abs(weite - r_so) < 1e-4 * r_so + 1e-9:
                rand.append(t)
        if not rand:
            raise ValueError("Aussenrand nicht gefunden")
        gmsh.model.addPhysicalGroup(1, rand, 1, "aussenrand")

        gap = r_si - r_rot
        lc_eisen = (lc_eisen_mm / 1000.0) if lc_eisen_mm > 0 else min(
            3.0e-3, float(nuten[0]["thick"]) / 3000.0, r_rot / 25.0)
        lc_gap = _groessenfeld(gmsh, r_rot, r_si, gap_lagen, lc_eisen)
        gmsh.option.setNumber("Mesh.Algorithm", 6)
        gmsh.model.mesh.generate(2)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        os.makedirs(os.path.dirname(os.path.abspath(msh_pfad)) or ".", exist_ok=True)
        gmsh.write(msh_pfad)
        knoten = len(gmsh.model.mesh.getNodes()[0])
        _, elems, _ = gmsh.model.mesh.getElements(2)
        dreiecke = sum(len(e) for e in elems)
    finally:
        gmsh.finalize()

    return {"msh": msh_pfad, "knoten": int(knoten), "dreiecke": int(dreiecke),
            "art": lb.get("art"), "gid": gid, "flaeche": flaeche, "n_koerper": lauf[0],
            "spulen": spulen, "nut_gid": nut_gid, "n_nut": len(nuten),
            "r_wel": r_wel, "r_rot": r_rot, "r_si": r_si, "r_so": r_so,
            "gap_m": gap, "lc_gap_m": lc_gap,
            "A_nut_m2": float(nuten[0]["length"]) * float(nuten[0]["thick"]) * 1e-6,
            "n_teile": len(laeufer),
            # Wo das Laeuferblech restlos belegt ist, steht das im Ergebnis --
            # sonst sucht beim naechsten Mal wieder jemand nach `rotoreisen`.
            "rest_befund": _rest_befund}


def _groessenfeld(gmsh, r_rot: float, r_si: float, lagen: int,
                  lc_eisen_m: float) -> float:
    lc_gap = (r_si - r_rot) / max(int(lagen), 1)
    lc_eisen = max(lc_eisen_m, lc_gap)
    r_m = 0.5 * (r_rot + r_si)
    f = gmsh.model.mesh.field.add("MathEval")
    rr = "sqrt(x*x+y*y)"
    u = f"(({rr}-{r_m!r})/{2.0 * (r_si - r_rot)!r})"
    gmsh.model.mesh.field.setString(
        f, "F", f"{lc_eisen!r} + ({lc_gap!r} - {lc_eisen!r})*exp(-{u}*{u})")
    gmsh.model.mesh.field.setAsBackgroundMesh(f)
    gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
    gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
    gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
    return lc_gap


def zuordnen(mesh_dir: str, netz: dict) -> dict:
    """Welche Elmer-Koerpernummer ist WELCHE Gruppe -- an der Flaeche gemessen.

    ``ElmerGrid ... -autoclean`` nummeriert die Koerper um, und zwar nach der
    Reihenfolge, in der sie ihm im Elementstrom begegnen -- nicht nach dem
    physikalischen Kennzeichen aus gmsh.  Die Nummern bleiben dabei
    ``1..N`` und bestehen damit die Pruefung von
    ``ema_em2d_harm.pruefe_koerpernummern``; nur bedeuten sie etwas anderes.

    **Gemessen am 20.09.2026:** beim Reluktanzlaeufer tauschten Luftspalt und
    Flussbarrieren die Nummer.  Die Folge war keine Fehlermeldung, sondern eine
    Luftspaltwelle, die in Wirklichkeit das Feld IN den Barrieren war -- 0,0042
    statt 0,669 T, also Faktor 160.  Genau die Sorte Fehler, gegen die
    ``pruefe_koerpernummern`` geschrieben wurde, nur eine Ebene tiefer: dort
    ging es darum, DASS die Nummern stimmen, hier darum, WAS sie bedeuten.

    Wiedererkannt wird an der Flaeche, weil die aus gmsh exakt bekannt ist und
    zwei Koerper dieser Modelle sich darin um Groessenordnungen unterscheiden.
    Bleibt eine Gruppe mehrdeutig, wird das **gesagt** statt geraten.
    """
    kn = os.path.join(mesh_dir, "mesh.nodes")
    el = os.path.join(mesh_dir, "mesh.elements")
    for f in (kn, el):
        if not os.path.exists(f):
            raise RuntimeError(f"{os.path.basename(f)} fehlt in {mesh_dir}")
    xy = {}
    with open(kn) as fh:
        for z in fh:
            t = z.split()
            if len(t) >= 5:
                xy[int(t[0])] = (float(t[2]), float(t[3]))
    ist = {}
    with open(el) as fh:
        for z in fh:
            t = z.split()
            if len(t) < 6 or not t[2].startswith("3"):
                continue
            k = int(t[1])
            (x0, y0), (x1, y1), (x2, y2) = (xy[int(t[3 + i])] for i in range(3))
            fl = 0.5 * abs((x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0))
            s_ = ist.setdefault(k, [0.0, 0.0, 0.0])
            s_[0] += fl
            s_[1] += fl * (x0 + x1 + x2) / 3.0
            s_[2] += fl * (y0 + y1 + y2) / 3.0
    for k, v in ist.items():
        v[1] /= max(v[0], 1e-30)
        v[2] /= max(v[0], 1e-30)

    soll = netz.get("flaeche") or {}
    bezug = max(float(netz.get("r_so") or 1.0), 1e-9)
    zu, frei = {}, dict(ist)
    for name, (a, cx, cy) in sorted(soll.items(), key=lambda kv: -kv[1][0]):
        best, punkte = None, None
        for k, (b, bx, by) in frei.items():
            d_a = abs(b - a) / max(a, 1e-15)
            d_c = math.hypot(bx - cx, by - cy) / bezug
            if d_a > 0.02 or d_c > 0.02:
                continue
            w = d_a + d_c
            if punkte is None or w < punkte:
                best, punkte = k, w
        if best is None:
            raise RuntimeError(
                f"Koerper '{name}' ({a * 1e6:.1f} mm^2 bei "
                f"({cx * 1e3:.1f}|{cy * 1e3:.1f}) mm) nicht wiedererkannt -- "
                f"die Zuordnung Name->Elmer-Nummer waere geraten")
        zu[name] = best
        del frei[best]
    return zu


# ── Anregung ─────────────────────────────────────────────────────────────────

def nutstroeme(geom: dict, iq: float, id_: float, rotor_angle: float = 0.0) -> list:
    """Amperewindungen je Statornut -- zeichengetreu die Regel des FDM.

    ``ema_analysis._rasterise`` traegt je Nut ``id*cos(p*theta - p*theta_r) -
    iq*sin(...)`` ein.  Genau diese Verteilung wird hier eingepraegt: der
    Vergleich soll Geometrie und Verfahren messen, nicht zwei verschiedene
    Wicklungsmodelle.  Der gemeinsame Vorfaktor ist beliebig und kuerzt sich in
    jeder hier ausgewerteten Groesse heraus (s. Modulkopf).

    **Achtung, und es ist eine Falle:** ``id_``/``iq`` benennen die Phase der
    STROMVERTEILUNG, nicht die Achse der Durchflutung. Ein Belag
    ``i(theta) ~ cos(p*theta)`` ergibt die Durchflutung
    ``F(theta) ~ sin(p*theta)`` -- ihr Scheitel liegt also **90 Grad
    elektrisch daneben**, bei ``p*theta = 90 Grad``. Wer ``id_`` setzt und
    „Feld auf der d-Achse" liest, misst in Wirklichkeit die q-Achse. Gemessen
    am Reluktanzlaeufer: ``id_`` liefert 0,54 T und ``iq`` 0,93 T -- die
    grosse Zahl gehoert zum EISENpfad. `mmf_achse` rechnet es aus, statt dass
    es jeder Aufrufer neu herleitet. Die Regel selbst bleibt zeichengetreu die
    des FDM; sie zu „berichtigen" hiesse, zwei verschiedene Wicklungen zu
    vergleichen.
    """
    n = int(geom["slots"])
    p = max(int(geom["p"]), 1)
    aus = []
    for k in range(n):
        th = 2.0 * math.pi * k / n
        el = p * th - p * float(rotor_angle)
        aus.append(float(id_) * math.cos(el) - float(iq) * math.sin(el))
    return aus


def mmf_achse(iq: float, id_: float, p: int, rotor_angle: float = 0.0) -> float:
    """Wo der Scheitel der Durchflutung LIEGT -- mechanischer Winkel [rad].

    Aus ``i(theta) ~ id*cos(p*theta) - iq*sin(p*theta)`` folgt
    ``F(theta) ~ [id*sin(p*theta) + iq*cos(p*theta)]/p``; der Scheitel liegt
    bei ``p*theta = atan2(id, iq)``. Fuer reines ``id_`` sind das 90 Grad
    elektrisch, fuer reines ``iq`` 0 Grad -- s. die Falle in `nutstroeme`.
    """
    return (math.atan2(float(id_), float(iq)) / max(int(p), 1)
            + float(rotor_angle))


def schreibe_sif(netz: dict, geom: dict, work_dir: str,
                 nut_A: list | None = None, mesh_name: str = "mesh") -> str:
    """``case.sif`` fuer ``MagnetoDynamics2D`` (magnetostatisch, reell)."""
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)
    gid = netz["gid"]

    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n"
         "  Max Output Level = 4\n"
         "  Coordinate System = Cartesian 2D\n"
         "  Simulation Type = Steady State\n"
         "  Steady State Max Iterations = 1\n"
         "  Output Intervals = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0:.12e}\nEnd\n"]

    # Material 1 = Eisen (linear, s. Modulkopf), 2 = Luft.
    koerper = []
    for name in ("welle", "rotoreisen", "laeuferpole", "statoreisen"):
        if gid.get(name):
            koerper.append((gid[name], 1, None))
    for name in ("laeuferluft", "luftspalt"):
        if gid.get(name):
            koerper.append((gid[name], 2, None))
    bf_zu = {}
    bf = 0
    for sp in netz["spulen"]:
        bf += 1
        bf_zu[sp["gid"]] = bf
        koerper.append((sp["gid"], 2, bf))
    for g in netz["nut_gid"]:
        bf += 1
        bf_zu[g] = bf
        koerper.append((g, 2, bf))

    # **Die `Body`-Reihenfolge MUSS die Koerpernummer sein.**  Elmers
    # ``Save Geometry Ids`` schreibt in die VTU nicht die Nummer aus
    # ``Target Bodies``, sondern den Index des ``Body``-Blocks -- gemessen am
    # 20.09.2026, und der Unterschied ist kein Schoenheitsfehler: sortiert man
    # nach Werkstoff (erst alles Eisen, dann alle Luft), liegt das Statorblech
    # auf Nummer 3 und die Auswertung liest unter „Luftspalt" die
    # Flussbarrieren.  Gemessen kamen so 0,0042 statt 0,669 T heraus, Faktor
    # 160, ohne jede Fehlermeldung.  ``ema_em2d_harm`` haelt dieselbe
    # Bedingung ein -- nur zufaellig, weil seine Liste in der Reihenfolge der
    # ``GID_*``-Konstanten steht.  Hier steht sie als Bedingung da.
    koerper.sort(key=lambda t: t[0])
    for i, (g, mat, b) in enumerate(koerper, start=1):
        if g != i:
            raise RuntimeError(
                f"Koerpernummern nicht luecken- und reihenfolgetreu: "
                f"Body {i} zeigt auf {g}. Die VTU zaehlt die Body-Reihenfolge, "
                f"die Auswertung waere damit einem anderen Koerper zugeordnet")
        S.append(f"Body {i}\n  Target Bodies(1) = {g}\n  Equation = 1\n"
                 f"  Material = {mat}\n"
                 + (f"  Body Force = {b}\n" if b else "") + "End\n")

    S.append(f"Material 1\n  Relative Permeability = {float(MU_R_EISEN)}\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    S.append("Material 2\n  Relative Permeability = 1.0\n"
             "  Electric Conductivity = 0.0\nEnd\n")

    bf = 0
    for sp in netz["spulen"]:
        bf += 1
        j = sp["A"] / max(sp["flaeche_m2"], 1e-15)
        S.append(f"Body Force {bf}\n  Current Density = Real {j:.6e}\nEnd\n")
    nut_A = list(nut_A or [0.0] * netz["n_nut"])
    for k, _g in enumerate(netz["nut_gid"]):
        bf += 1
        j = float(nut_A[k]) / max(netz["A_nut_m2"], 1e-15)
        S.append(f"Body Force {bf}\n  Current Density = Real {j:.6e}\nEnd\n")

    S.append("Solver 1\n"
             '  Equation = "MgDyn2D"\n'
             '  Procedure = "MagnetoDynamics2D" "MagnetoDynamics2D"\n'
             '  Variable = "Potential"\n'
             "  Linear System Solver = Direct\n"
             "  Linear System Direct Method = UMFPACK\n"
             "  Steady State Convergence Tolerance = 1.0e-8\n"
             "End\n")
    S.append("Solver 2\n"
             '  Equation = "ErgebnisAusgabe"\n'
             '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
             '  Output File Name = "stat2d"\n'
             '  Output Format = String "vtu"\n'
             "  Save Geometry Ids = Logical True\n"
             '  Output Directory = "results"\n'
             "  Vtu Format = Logical True\n"
             "End\n")
    S.append("Equation 1\n  Active Solvers(2) = 1 2\nEnd\n")
    S.append("Boundary Condition 1\n  Target Boundaries(1) = 1\n"
             "  Potential = Real 0.0\nEnd\n")

    pfad = os.path.join(work_dir, "case.sif")
    with open(pfad, "w") as fh:
        fh.write("\n".join(S))
    with open(os.path.join(work_dir, "ELMERSOLVER_STARTINFO"), "w") as fh:
        fh.write("case.sif\n1\n")
    return pfad


# ── Auswertung ───────────────────────────────────────────────────────────────

def _lies_vtu(vtu_pfad: str):
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    rd = vtk.vtkXMLUnstructuredGridReader()
    rd.SetFileName(vtu_pfad)
    rd.Update()
    grid = rd.GetOutput()
    pts = vtk_to_numpy(grid.GetPoints().GetData())[:, :2]
    pd = grid.GetPointData()
    namen = [pd.GetArrayName(i) for i in range(pd.GetNumberOfArrays())]
    treffer = [n for n in namen if n and n.lower().strip() == "potential"]
    if not treffer:
        treffer = [n for n in namen if n and "potential" in n.lower()]
    if not treffer:
        raise KeyError(f"'potential' nicht in der VTU (vorhanden: {namen})")
    a = vtk_to_numpy(pd.GetArray(treffer[0]))

    n_c = grid.GetNumberOfCells()
    conn = np.empty((n_c, 3), dtype=np.int64)
    gute = np.zeros(n_c, dtype=bool)
    for i in range(n_c):
        c = grid.GetCell(i)
        if c.GetNumberOfPoints() == 3:
            ids = c.GetPointIds()
            conn[i] = (ids.GetId(0), ids.GetId(1), ids.GetId(2))
            gute[i] = True
    cd = grid.GetCellData().GetArray("GeometryIds")
    if cd is None:
        raise KeyError("GeometryIds fehlen in der VTU")
    gid = vtk_to_numpy(cd).astype(np.int64)
    return pts, conn[gute], gid[gute], np.asarray(a, dtype=float)


def luftspaltwelle(vtu_pfad: str, netz: dict, n_theta: int | None = None) -> dict:
    """``B_r(theta)`` in der Mitte des Luftspalts, flaechengewichtet gebinnt.

    Ausgewertet werden die Dreiecke der Gruppe ``luftspalt`` -- ihr B ist bei
    P1-Ansatz elementweise konstant und exakt.  Gebinnt statt an Stuetzstellen
    abgetastet: eine Punktsuche im Netz ist die Stelle, an der eine Toleranz
    ueber das Ergebnis entscheidet, und das soll sie hier nicht.
    """
    import numpy as np
    pts, conn, gid, a = _lies_vtu(vtu_pfad)
    x = pts[conn, 0]
    y = pts[conn, 1]
    v = a[conn]
    zf = ((x[:, 1] - x[:, 0]) * (y[:, 2] - y[:, 0])
          - (x[:, 2] - x[:, 0]) * (y[:, 1] - y[:, 0]))
    sicher = np.where(np.abs(zf) < 1e-20, 1e-20, zf)
    dadx = (v[:, 0] * (y[:, 1] - y[:, 2]) + v[:, 1] * (y[:, 2] - y[:, 0])
            + v[:, 2] * (y[:, 0] - y[:, 1])) / sicher
    dady = (v[:, 0] * (x[:, 2] - x[:, 1]) + v[:, 1] * (x[:, 0] - x[:, 2])
            + v[:, 2] * (x[:, 1] - x[:, 0])) / sicher
    bx, by, fl = dady, -dadx, 0.5 * np.abs(zf)

    mx, my = x.mean(axis=1), y.mean(axis=1)
    r = np.hypot(mx, my)
    luft = gid == netz["gid"]["luftspalt"]
    if not luft.any():
        raise RuntimeError("Kein Luftspaltkoerper in der VTU gefunden")
    th = np.mod(np.arctan2(my, mx), 2.0 * math.pi)
    br = (bx * np.where(r < 1e-12, 0.0, mx / np.where(r < 1e-12, 1.0, r))
          + by * np.where(r < 1e-12, 0.0, my / np.where(r < 1e-12, 1.0, r)))

    # Die Winkelaufloesung folgt dem NETZ statt einer runden Zahl: mehr
    # Faecher als Dreiecke ergaeben leere Faecher, und die muessten
    # interpoliert werden -- dann glaettet die Auswertung die Welle, die sie
    # messen soll.  Mindestens `MIN_JE_FACH` Dreiecke je Fach.
    if n_theta is None:
        n_theta = int(max(60, min(720, int(luft.sum()) // MIN_JE_FACH)))
        n_theta -= n_theta % 12

    k = np.floor(th[luft] / (2.0 * math.pi) * n_theta).astype(int) % n_theta
    w = fl[luft]
    s = np.bincount(k, weights=w * br[luft], minlength=n_theta)
    n = np.bincount(k, weights=w, minlength=n_theta)
    leer = n <= 0
    if leer.any():
        # Ein leeres Fach heisst zu grobes Netz fuer diese Winkelauflösung --
        # nachbarlich fuellen statt eine 0 auszugeben, die sich wie ein
        # Messwert liest.
        idx = np.arange(n_theta)
        voll = idx[~leer]
        if len(voll) == 0:
            raise RuntimeError("Luftspaltring leer")
        s[leer] = np.interp(idx[leer], voll, (s / np.where(n <= 0, 1, n))[voll],
                            period=n_theta)
        n[leer] = 1.0
    return {"theta": (np.arange(n_theta) + 0.5) * 2.0 * math.pi / n_theta,
            "Br": s / n, "leere_faecher": int(leer.sum()),
            "n_theta": int(n_theta), "n_luft": int(luft.sum())}


def _harmonische(theta, werte, p: int, m_max: int = 9) -> dict:
    """Amplituden der Polpaar-Harmonischen ``m*p`` und der Klirranteil."""
    import numpy as np
    th = np.asarray(theta)
    w = np.asarray(werte, dtype=float)
    amp = {}
    for m in range(1, m_max + 1):
        c = 2.0 * np.mean(w * np.cos(m * p * th))
        s = 2.0 * np.mean(w * np.sin(m * p * th))
        amp[m] = float(math.hypot(c, s))
    g = amp[1]
    ober = math.sqrt(sum(amp[m] ** 2 for m in range(2, m_max + 1)))
    return {"amplituden": {m: round(v, 6) for m, v in amp.items()},
            "grundwelle": round(g, 6),
            "klirr_pct": round(100.0 * ober / g, 3) if g > 1e-12 else None,
            "rms": float(np.sqrt(np.mean(w * w)))}


def vergleiche(theta_a, br_a, theta_b, br_b, p: int) -> dict:
    """Zwei Luftspaltwellen gegeneinander -- FORM, nicht Hoehe.

    Jede Seite wird auf ihren eigenen Effektivwert normiert (s. Modulkopf: die
    Hoehe des FDM haengt an einer Eichung, die fuer eine magnetlose Maschine
    nichts aussagt).  Verglichen werden dann die Abweichung der normierten
    Wellen, ihre Korrelation und der Klirranteil beider.
    """
    import numpy as np
    th = np.asarray(theta_a, dtype=float)
    a = np.asarray(br_a, dtype=float)
    b = np.interp(th, np.asarray(theta_b, dtype=float),
                  np.asarray(br_b, dtype=float), period=2.0 * math.pi)
    ha = _harmonische(th, a, p)
    hb = _harmonische(th, b, p)
    ra = ha["rms"] or 1e-30
    rb = hb["rms"] or 1e-30
    an, bn = a / ra, b / rb
    # Das Vorzeichen ist eine Frage der Zaehlrichtung, nicht des Ergebnisses.
    if float(np.mean(an * bn)) < 0:
        bn = -bn
    abw = float(np.sqrt(np.mean((an - bn) ** 2)) / math.sqrt(np.mean(an * an)))
    korr = float(np.mean(an * bn) / math.sqrt(np.mean(an ** 2) * np.mean(bn ** 2)))
    return {"form_abweichung_pct": round(100.0 * abw, 2),
            "korrelation": round(korr, 5),
            "klirr_a_pct": ha["klirr_pct"], "klirr_b_pct": hb["klirr_pct"],
            "rms_a_T": round(ra, 5), "rms_b_T": round(rb, 5),
            "grundwelle_a_T": ha["grundwelle"], "grundwelle_b_T": hb["grundwelle"],
            "harmonische_a": ha["amplituden"], "harmonische_b": hb["amplituden"]}


# ── Lauf ─────────────────────────────────────────────────────────────────────

def vorbereiten(geom: dict, work_dir: str, axial_mm: float | None = None,
                gap_lagen: int = GAP_LAGEN, lc_eisen_mm: float = 0.0,
                teile: list | None = None, melde=None) -> dict:
    """Netz bauen und einmalig nach Elmer uebersetzen. Wird je Punkt wiederverwendet."""
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        raise RuntimeError("Elmer fehlt (ElmerGrid/ElmerSolver nicht im PATH)")
    os.makedirs(work_dir, exist_ok=True)
    msh = os.path.join(work_dir, "stat2d.msh")
    netz = baue_netz(geom, msh, axial_mm=axial_mm, gap_lagen=gap_lagen,
                     lc_eisen_mm=lc_eisen_mm, teile=teile)
    if melde:
        melde(f"Netz: {netz['dreiecke']} Dreiecke, {netz['knoten']} Knoten, "
              f"{netz['n_koerper']} Koerper")
    mesh_dir = os.path.join(work_dir, "mesh")
    rg = elmer_runner.run_elmergrid(msh, mesh_dir)
    if not rg.get("ok"):
        raise RuntimeError("ElmerGrid: "
                           + (rg.get("stderr") or rg.get("error", ""))[:300])
    from ema_em2d_harm import pruefe_koerpernummern
    pruefe_koerpernummern(mesh_dir, netz["n_koerper"])
    # Und jetzt die zweite Haelfte derselben Frage: die Nummern sind 1..N, aber
    # WELCHE ist welche? Gemessen statt geglaubt -- s. `zuordnen`.
    zu = zuordnen(mesh_dir, netz)
    getauscht = sorted(k for k, v in zu.items() if netz["gid"].get(k) != v)
    netz["gid"] = zu
    netz["nut_gid"] = [zu[f"nut{k}"] for k in range(netz["n_nut"])]
    netz["spulen"] = [dict(sp, gid=zu[f"spule{i}"])
                      for i, sp in enumerate(netz["spulen"])]
    if melde and getauscht:
        melde(f"ElmerGrid hat {len(getauscht)} Koerper umnummeriert "
              f"(u. a. {', '.join(getauscht[:4])}) -- neu zugeordnet")
    return {"geom": dict(geom), "netz": netz, "work_dir": work_dir,
            "p": max(int(geom["p"]), 1), "umnummeriert": getauscht}


def loese(ctx: dict, iq: float = 0.0, id_: float = 0.0,
          rotor_angle: float = 0.0, erregung: float = 1.0,
          timeout: int = 1800) -> dict:
    """EIN magnetostatischer Punkt. Netz wird wiederverwendet.

    ``erregung`` skaliert die Laeuferdurchflutung (0 = Staender allein).
    """
    import elmer_runner
    netz = dict(ctx["netz"])
    netz["spulen"] = [dict(s, A=s["A"] * float(erregung)) for s in netz["spulen"]]
    nut_A = nutstroeme(ctx["geom"], iq, id_, rotor_angle)
    schreibe_sif(netz, ctx["geom"], ctx["work_dir"], nut_A=nut_A)
    rs = elmer_runner.run_elmersolver(os.path.join(ctx["work_dir"], "case.sif"),
                                      ctx["work_dir"], timeout=timeout)
    if not rs.get("ok"):
        raise RuntimeError("ElmerSolver: "
                           + (rs.get("stderr") or rs.get("error", ""))[:400]
                           + "\n" + rs.get("stdout", "")[-1200:])
    from ema_em2d_harm import _finde_vtu
    vtu = _finde_vtu(os.path.join(ctx["work_dir"], "results"))
    if not vtu:
        raise RuntimeError("Keine VTU geschrieben")
    w = luftspaltwelle(vtu, ctx["netz"])
    h = _harmonische(w["theta"], w["Br"], ctx["p"])
    return {"theta": w["theta"], "Br": w["Br"], "vtu": vtu,
            "leere_faecher": w["leere_faecher"], "n_theta": w["n_theta"],
            "n_luft": w["n_luft"], **h}
