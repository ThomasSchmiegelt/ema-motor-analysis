"""Die Laeufer im CAD — ohne FreeCAD geprueft, am ERZEUGTEN Skript.

Warum am Skript und nicht am Koerper: ``ema_freecad`` schreibt Python-Text fuer
einen fremden Prozess, und ein FreeCAD-Lauf kostet 40 s Start plus Rechenzeit.
Was hier falsch werden kann, steht aber im Text: welche Bauteile ueberhaupt
entstehen, wieviele Nuten, wieviele Schraegungssegmente, und ob ein Laeufer ohne
Magnete welche bekommt. Der echte Bau laeuft in ``smoke_test.py --cad``.

Der tragende Punkt: **die Zahl wird am erzeugten Koerper nachgemessen, nicht am
Parameter, aus dem er entstand.** Ein Test, der ``CAGE["n"] == stabzahl(geom)``
prueft, prueft eine Zuweisung; hier wird die Schleife wirklich ausgefuehrt und
gezaehlt, was dabei herauskommt.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_asm
import ema_freecad
import ema_maschinenart
import ema_mobil

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def geom(**kw):
    g = ema_mobil.basis_geom()
    g.update(p=3, slots=36, rpm_to=6000, axialLen=100)
    g.update(kw)
    return g


def skript(g, axial=100.0):
    return ema_freecad.build_full_motor_script(g, axial, "/tmp/unbenutzt.FCStd")


class _Zaehler:
    """Ein Stellvertreter fuer ``Part``, der zaehlt statt zu bauen.

    Damit laesst sich das erzeugte Skript wirklich AUSFUEHREN, ohne FreeCAD --
    und dann steht in den Zaehlern, was der Bauer tatsaechlich erzeugt hat.
    """

    def __init__(self):
        self.boxen, self.zylinder, self.objekte = [], [], {}
        self.drehungen = []


def lauf(code):
    """Das erzeugte Skript mit gestelltem FreeCAD ausfuehren und mitzaehlen."""
    z = _Zaehler()

    class _Vec:
        # Das erzeugte Skript rechnet mit Vektoren (der Kronen-Sweep ruft
        # sub/add/cross/normalize/Length). Ohne die Arithmetik bricht es ab,
        # BEVOR die Laeuferkoerper entstehen -- und dann prueft dieser Test
        # nichts und meldet trotzdem gruen fuer alles danach.
        def __init__(self, *a):
            if a and hasattr(a[0], "x"):
                self.x, self.y, self.z = a[0].x, a[0].y, a[0].z
                return
            self.x, self.y, self.z = (list(a) + [0, 0, 0])[:3]

        def sub(self, o):
            return _Vec(self.x - o.x, self.y - o.y, self.z - o.z)

        def add(self, o):
            return _Vec(self.x + o.x, self.y + o.y, self.z + o.z)

        def multiply(self, f):
            return _Vec(self.x * f, self.y * f, self.z * f)

        def cross(self, o):
            return _Vec(self.y * o.z - self.z * o.y,
                        self.z * o.x - self.x * o.z,
                        self.x * o.y - self.y * o.x)

        def dot(self, o):
            return self.x * o.x + self.y * o.y + self.z * o.z

        def normalize(self):
            n = self.Length or 1.0
            return _Vec(self.x / n, self.y / n, self.z / n)

        def negative(self):
            return _Vec(-self.x, -self.y, -self.z)

        @property
        def Length(self):
            return math.sqrt(self.x ** 2 + self.y ** 2 + self.z ** 2)

        def __add__(self, o):
            return self.add(o)

        def __sub__(self, o):
            return self.sub(o)

        def __mul__(self, f):
            return self.multiply(f)

        __rmul__ = __mul__

    class _Mat:
        def rotateZ(self, a):
            self.a = a

    class _Rot:
        # App.Rotation(achse, winkel) bzw. (v_von, v_nach)
        def __init__(self, *a):
            self.a = a

        def multVec(self, v):
            return v

    class _Plc:
        # App.Placement(ort, drehung) -- der Kronen-Sweep setzt damit die
        # Schnittebenen. Fuer diesen Test zaehlt nur, DASS es durchlaeuft.
        def __init__(self, *a):
            self.a = a

        def multVec(self, v):
            return v

    class _Shape:
        def __init__(self, art, masse=None):
            self.art = art
            self.masse = masse or {}
            self.winkel = None

        def rotate(self, mitte, achse, grad):
            self.winkel = grad
            z.drehungen.append((self.art, grad))

        def translate(self, v):
            return self

        def transformGeometry(self, m):
            neu = _Shape(self.art, self.masse)
            neu.winkel = getattr(m, "a", None)
            return neu

        def cut(self, other):
            return self

        def fuse(self, other):
            return self

        def common(self, other):
            return self

        def removeSplitter(self):
            return self

        def isValid(self):
            return True

        def extrude(self, v):
            return self

        @property
        def Volume(self):
            return 1.0

        @property
        def Solids(self):
            return [self]

        # Der SAVE-Block am Ende liest Flaechen und exportiert STEP. Fuer
        # diesen Test zaehlt nur, dass er durchlaeuft -- was er dort SCHREIBT
        # (CAD_FACES/CAD_VOLUME) prueft `smoke_test.py --cad` am echten Bau.
        @property
        def Faces(self):
            return []

        def isNull(self):
            return False

        def exportStep(self, pfad):
            pass

    class _Part:
        @staticmethod
        def makeBox(a, b, c, v=None):
            sh = _Shape("box", {"a": a, "b": b, "c": c,
                                "x": getattr(v, "x", 0.0), "z": getattr(v, "z", 0.0)})
            z.boxen.append(sh)
            return sh

        @staticmethod
        def makeCylinder(r, h, v=None, ax=None, ang=None):
            sh = _Shape("cyl", {"r": r, "h": h, "z": getattr(v, "z", 0.0)})
            z.zylinder.append(sh)
            return sh

        @staticmethod
        def makeCompound(shapes):
            sh = _Shape("compound")
            sh.teile = list(shapes)
            return sh

        @staticmethod
        def makePolygon(pts):
            return _Shape("poly")

        @staticmethod
        def makeLoft(wires, solid=False, ruled=False, closed=False):
            return _Shape("loft")

        @staticmethod
        def Wire(edges):
            return _Shape("wire")

        @staticmethod
        def LineSegment(a, b):
            return _Shape("line")

        @staticmethod
        def Face(w):
            return _Shape("face")

    class _Obj:
        def __init__(self, name):
            self.Name = name
            self.Shape = None
            self.ViewObject = type("V", (), {})()

    class _Doc:
        def __init__(self):
            self.Objects = []

        def addObject(self, typ, name):
            o = _Obj(name)
            self.Objects.append(o)
            z.objekte[name] = o
            return o

        def getObject(self, name):
            return z.objekte.get(name)

        def removeObject(self, name):
            z.objekte.pop(name, None)

        def recompute(self):
            pass

        def saveAs(self, p):
            pass

        def save(self):
            pass

    class _App:
        Vector = _Vec
        Matrix = _Mat

        @staticmethod
        def newDocument(n):
            return _Doc()

        class Units:
            @staticmethod
            def Quantity(s):
                return 1.0

    # Das erzeugte Skript beginnt mit ``import FreeCAD as App`` / ``import Part``.
    # Die Namen im Gueltigkeitsbereich vorzubelegen genuegt deshalb NICHT -- der
    # Import ueberschreibt sie. Die Stellvertreter muessen als MODULE in
    # ``sys.modules`` stehen, und hinterher wieder heraus.
    import types
    m_fc = types.ModuleType("FreeCAD")
    m_fc.Vector, m_fc.Matrix = _Vec, _Mat
    m_fc.Rotation, m_fc.Placement = _Rot, _Plc
    m_fc.newDocument = _App.newDocument
    m_fc.Units = _App.Units
    m_part = types.ModuleType("Part")
    for _n in ("makeBox", "makeCylinder", "makeCompound", "makePolygon", "Face",
               "makeLoft", "Wire", "LineSegment"):
        setattr(m_part, _n, getattr(_Part, _n))
    alt_mod = {k: sys.modules.get(k) for k in ("FreeCAD", "Part")}
    sys.modules["FreeCAD"], sys.modules["Part"] = m_fc, m_part
    umgebung = {"print": lambda *a, **k: None, "__name__": "gen"}
    try:
        exec(compile(code, "<gen>", "exec"), umgebung)
    except Exception as exc:                                 # noqa: BLE001
        import traceback
        z.fehler = f"{type(exc).__name__}: {exc}"
        z.spur = traceback.format_exc()
    else:
        z.fehler = None
    finally:
        for k, v in alt_mod.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return z


# ──────────────────────────────────────────────────────────────────────────────
print("1. Eine Bauart OHNE Magnete bekommt keine Magnete — und keine Taschen")

for art in ("asm", "synrm", "eesm"):
    g = geom(machineType=art)
    code = skript(g)
    pruefe("Magnets_N" not in code.split("if GEN_MAGNETS:")[0]
           and f"GEN_MAGNETS = False" in code,
           f"{art}: GEN_MAGNETS ist False, egal was genMagnets sagt")
    z = lauf(code)
    pruefe(z.fehler is None, f"{art}: das erzeugte Skript laeuft ({z.fehler or 'ok'})")
    pruefe("Magnets_N" not in z.objekte and "Magnets_S" not in z.objekte,
           f"{art}: es entsteht KEIN Magnetkoerper")

# Die Gegenprobe: die PSM bekommt sie sehr wohl.
zp = lauf(skript(geom(machineType="pmsm")))
pruefe("Magnets_N" in zp.objekte and "Magnets_S" in zp.objekte,
       "pmsm: Magnete entstehen weiterhin (Gegenprobe)")

# Und genMagnets=False blendet sie aus, OHNE die Taschen zu verlieren --
# das ist der stufenweise Aufbau und nicht dasselbe wie „hat keine".
g_aus = geom(machineType="pmsm", genMagnets=False)
pruefe("GEN_MAGNETS = False" in skript(g_aus) and "HAT_MAGNETE = True" in skript(g_aus),
       "pmsm mit genMagnets=False: Magnete aus, Bauart-Tatsache bleibt True")


print("\n2. Der Kaefig: Nutzahl und Schraegung am gebauten Koerper gezaehlt")

g = geom(machineType="asm", rotorType="kaefig")
kf = ema_asm.kaefig(g, 100.0)
n_stab = int(kf["n_stab"])
segs = ema_asm.SCHRAEG_SEGMENTE
z = lauf(skript(g))
stab = z.objekte.get("Cage_Bars")
pruefe(stab is not None, "es gibt einen Koerper Cage_Bars")
if stab is not None:
    pruefe(len(stab.Shape.teile) == n_stab * segs,
           f"{len(stab.Shape.teile)} Stabsegmente = {n_stab} Staebe x {segs} "
           f"Schraegungssegmente")
ringe = z.objekte.get("Cage_Rings")
pruefe(ringe is not None and len(ringe.Shape.teile) == 2,
       "zwei Kurzschlussringe — der Grund, warum die analytische Stufe einen "
       "Zuschlag traegt und das 2-D-Feld nicht")

# Die Schraegung muss sich in den DREHUNGEN zeigen, nicht nur im Parameter.
# Gemessen wird am ERSTEN Stab (die ersten `segs` Drehungen): ein Winkelfilter
# ueber alle Staebe mischt benachbarte Nuten, weil die Schraegung hier gerade
# eine ganze Laeufernutteilung betraegt.
# Verglichen wird gegen den Wert, der WIRKLICH im Skript steht: er ist beim
# Einbetten auf vier Stellen gerundet, und eine Toleranz von 1e-6 auf eine
# Spanne von 9,7° faellt genau darauf herein. Dass die Rundung den Winkel nicht
# verschiebt, wird daneben eigens geprueft.
import json as _j
skew_soll = ema_asm.schraegung_grad(g)
skew = float(_j.loads(skript(g).split("CAGE = ")[1].split("   #")[0])["skew_deg"])
erste = [w for _, w in z.drehungen[:segs]]
pruefe(abs(skew - skew_soll) < 1e-4,
       f"die eingebettete Schraegung {skew}° trifft ema_asm.schraegung_grad "
       f"({skew_soll:.6f}°) auf die Rundung genau")
pruefe(skew > 0.1, f"Vorgabe-Schraegung des Kaefigs: {skew:.2f}° mechanisch "
                   f"(= eine Laeufernutteilung, 360/{n_stab})")
pruefe(len(set(round(w, 6) for w in erste)) == segs,
       f"die {segs} Segmente des ersten Stabes liegen auf {segs} verschiedenen "
       f"Winkeln")
spanne = max(erste) - min(erste)
pruefe(abs(spanne - skew * (segs - 1) / segs) < 1e-6,
       f"gemessene Winkelspanne {spanne:.3f}° = Schraegung x (n-1)/n "
       f"({skew * (segs - 1) / segs:.3f}°) — gestufte Schraegung, nicht tordiert")
pruefe(abs(sum(erste) / len(erste)) < 1e-9 * max(1.0, skew),
       f"und der Mittelwert der Segmentwinkel ist 0 — die Schraegung VERDREHT "
       f"die Nut, sie verschiebt sie nicht")

# Ohne Schraegung genau ein Segment je Stab.
z0 = lauf(skript(geom(machineType="asm", rotorType="kaefig", rotorSkewSlots=0)))
pruefe(len(z0.objekte["Cage_Bars"].Shape.teile) == n_stab,
       f"rotorSkewSlots=0: {n_stab} Staebe, ein Stueck je Stab")


print("\n3. Ein nicht auslegbarer Kaefig wird NICHT gezeichnet")

# Der Ventilatorfall: die Magnetisierung frisst die ganze Umrichtergrenze.
g_eng = geom(machineType="asm", rotorType="kaefig",
             statorOD=120, statorID=90, rotorOD=89.3, shaftD=30, p=1, slots=24)
kf_eng = ema_asm.kaefig(g_eng, 60.0)
if kf_eng.get("erreichbar", True):
    # Die Beispielgeometrie ist auslegbar — dann wird die Weigerung ueber einen
    # gestellten Befund geprueft statt gar nicht.
    print("     (Beispielgeometrie ist auslegbar — Weigerung mit gestelltem Befund)")
    import unittest.mock as _mk
    with _mk.patch.object(ema_asm, "kaefig",
                          return_value=dict(kf_eng, erreichbar=False,
                                            grund="kein momentbildender Strom")):
        try:
            skript(g_eng, 60.0)
            pruefe(False, "ein nicht auslegbarer Kaefig wird abgewiesen")
        except ValueError as e:
            pruefe("nicht auslegbar" in str(e) and "Fertigungs" in str(e),
                   f"abgewiesen mit Begruendung: {str(e)[:70]}…")
        # ... und mit ausdruecklicher Freigabe doch gezeichnet.
        try:
            skript(dict(g_eng, kaefigFreigabe=True), 60.0)
            pruefe(True, "mit geom.kaefigFreigabe wird trotzdem gezeichnet")
        except ValueError:
            pruefe(False, "mit geom.kaefigFreigabe wird trotzdem gezeichnet")
else:
    try:
        skript(g_eng, 60.0)
        pruefe(False, "ein nicht auslegbarer Kaefig wird abgewiesen")
    except ValueError as e:
        pruefe("nicht auslegbar" in str(e), f"abgewiesen: {str(e)[:70]}…")


print("\n4. Der Schleifringlaeufer: Wicklung, drei Ringe, drei Buersten")

gs = geom(machineType="asm", rotorType="schleifring")
lw = ema_asm.laeuferwicklung(gs, 100.0)
zs = lauf(skript(gs))
pruefe(zs.fehler is None, f"das Skript laeuft ({zs.fehler or 'ok'})")
w = zs.objekte.get("Rotor_Winding")
pruefe(w is not None and len(w.Shape.teile) == int(lw["n_nut"]),
       f"{len(w.Shape.teile) if w else 0} Wicklungsbuendel = {lw['n_nut']} Nuten")
pruefe("Cage_Bars" not in zs.objekte and "Cage_Rings" not in zs.objekte,
       "kein Kaefig daneben — die beiden Bauformen schliessen sich aus")
r = zs.objekte.get("Slip_Rings")
b = zs.objekte.get("Brushes")
pruefe(r is not None and len(r.Shape.teile) == 3,
       "drei Schleifringe (Drehstrom)")
pruefe(b is not None and len(b.Shape.teile) == 3,
       "drei Buersten — eine je Ring")

# Die Nutzahl folgt der DREHSTROMregel, nicht der Kaefigregel.
pruefe(int(lw["n_nut"]) % 3 == 0,
       f"{lw['n_nut']} Laeufernuten sind durch 3 teilbar (drei gleiche Straenge)")
pruefe(int(lw["n_nut"]) != int(gs["slots"]),
       f"und nicht gleich der Statornutzahl ({gs['slots']}) — sonst klebt sie")
pruefe(ema_asm.laeufernuten(gs) != ema_asm.stabzahl(gs),
       f"die beiden Regeln liefern verschiedene Zahlen "
       f"(Wicklung {ema_asm.laeufernuten(gs)}, Kaefig {ema_asm.stabzahl(gs)})")


print("\n5. Die Nuttiefe folgt dem STROM, nicht dem Platz")

pruefe(lw["nut_tiefe_mm"] < lw["nutraum_mm"],
       f"Nuttiefe {lw['nut_tiefe_mm']} mm gegen {lw['nutraum_mm']} mm "
       f"verfuegbaren Blechraum — der Laeufer wird NICHT bis zum Deckel gefuellt "
       f"(genau der Fehler, der den Kaefigwiderstand einmal um Faktor 5 "
       f"danebenliegen liess)")
pruefe(abs(lw["J2_Apmm2"] - ema_asm.J_LAEUFER_APMM2) < 0.2,
       f"die erreichte Stromdichte {lw['J2_Apmm2']} A/mm² trifft die "
       f"Auslegungsvorgabe {ema_asm.J_LAEUFER_APMM2} — die Rechnung schliesst "
       f"sich gegen sich selbst")
lw_dicht = ema_asm.laeuferwicklung(dict(gs, rotorCurrentDensity=10.0), 100.0)
pruefe(lw_dicht["nut_tiefe_mm"] < lw["nut_tiefe_mm"],
       f"doppelte Stromdichte -> flachere Nut ({lw_dicht['nut_tiefe_mm']} gegen "
       f"{lw['nut_tiefe_mm']} mm)")


print("\n6. Der Anlasswiderstand: Schlupf ja, Laeufererwaermung nein")

bp0 = ema_asm.betriebspunkt(gs, 100.0, 3000.0, 80.0)
bp1 = ema_asm.betriebspunkt(gs, 100.0, 3000.0, 80.0,
                            r_zusatz_ohm=lw["R2_Ohm"])
# Schranke relativ: der Schlupf haengt jetzt am Widerstand BEI
# BETRIEBSTEMPERATUR, und `schlupf` kommt gerundet zurueck -- eine Gleichheit
# auf 1e-9 pruefte die Rundung statt der Verdopplung.
pruefe(abs(bp1["schlupf"] / max(bp0["schlupf"], 1e-12) - 2.0) < 1e-3,
       f"doppelter Laeuferwiderstand -> doppelter Schlupf "
       f"({bp0['schlupf_pct']:.3f} -> {bp1['schlupf_pct']:.3f} %) — das ist die "
       f"Aussage ueber den Anlauf, nicht eine Faustregel")
pruefe(bp1["laeuferwicklung"]["P_wicklung_W"]
       == bp0["laeuferwicklung"]["P_wicklung_W"],
       f"die Verlustleistung IN der Maschine bleibt gleich "
       f"({bp1['laeuferwicklung']['P_wicklung_W']} W) — der Zusatz heizt "
       f"AUSSEN, und genau deshalb kann der Schleifringlaeufer mit vollem "
       f"Moment anfahren")
pruefe(bp1["P_zusatz_W"] > 0 and bp0["P_zusatz_W"] == 0,
       f"und wird getrennt ausgewiesen ({bp1['P_zusatz_W']} W)")
pruefe(bp0["T_ist_Nm"] == bp1["T_ist_Nm"],
       "das Moment am Betriebspunkt aendert sich dabei nicht")


print("\n7. Der Kaefiglauf bleibt Ziffer fuer Ziffer, was er war")

gk = geom(machineType="asm", rotorType="kaefig")
bpk = ema_asm.betriebspunkt(gk, 100.0, 3000.0, 80.0)
pruefe(bpk["laeufer_art"] == "kaefig" and bpk["laeuferwicklung"] is None,
       "der Kaefigzweig fasst die Wicklung nicht an")
# Ohne rotorType gesetzt ist es derselbe Lauf.
g_ohne = geom(machineType="asm")
g_ohne.pop("rotorType", None)
bpo = ema_asm.betriebspunkt(g_ohne, 100.0, 3000.0, 80.0)
pruefe(all(bpk.get(k) == bpo.get(k) for k in
           ("T_ist_Nm", "I_s_A", "schlupf", "P_kaefig_W", "I_stab_A")),
       "und ohne rotorType-Angabe kommt dasselbe heraus (Vorgabe = Kaefig)")


print("\n8. Der Querschnitt zeigt, was gerechnet wurde")

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import ema_pipeline


def schnitt_zaehlen(g):
    fig, ax = plt.subplots(figsize=(4, 4))
    ema_pipeline.render_cross_section(g, ax, beschriftung=False)
    n = len(ax.patches)
    plt.close(fig)
    return n


n_pm = schnitt_zaehlen(geom(machineType="pmsm"))
n_kf = schnitt_zaehlen(geom(machineType="asm", rotorType="kaefig"))
n_sr = schnitt_zaehlen(geom(machineType="asm", rotorType="schleifring"))
pruefe(n_pm > 0 and n_kf > 0 and n_sr > 0,
       f"alle drei zeichnen ({n_pm} / {n_kf} / {n_sr} Flaechen)")
# Der Kaefig hat mehr Nuten als der gewickelte Laeufer -> mehr Flaechen.
pruefe(n_kf - n_sr == ema_asm.stabzahl(geom(machineType="asm"))
       - ema_asm.laeufernuten(geom(machineType="asm", rotorType="schleifring")),
       f"der Unterschied zwischen beiden Bildern ist genau die Nutzahl "
       f"({n_kf} - {n_sr} = {n_kf - n_sr})")

# Und die Masse im Bild kommen aus DERSELBEN Funktion wie im CAD.
gk = geom(machineType="asm", rotorType="kaefig")
kf = ema_asm.kaefig(gk, float(gk["axialLen"]))
code = skript(gk, float(gk["axialLen"]))
import json as _json
cage = _json.loads(code.split("CAGE = ")[1].split("   #")[0])
pruefe(cage["n"] == int(kf["n_stab"]) and abs(cage["b"] - kf["stabbreite_mm"]) < 1e-9
       and abs(cage["t"] - kf["nuttiefe_mm"]) < 1e-9,
       "CAD und Querschnitt lesen dieselbe ema_asm.kaefig — Ziffer fuer Ziffer")


print("\n9. Der Schenkelpollaeufer (EESM)")

import ema_eesm
import ema_eesm_cad
import ema_schleifring

ge = geom(machineType="eesm", p=3, slots=18)
k = ema_eesm_cad.koerper(ge, 100.0)
ze = lauf(skript(ge))
pruefe(ze.fehler is None, f"das Skript laeuft ({ze.fehler or 'ok'})")
pruefe("Magnets_N" not in ze.objekte and "Cage_Bars" not in ze.objekte,
       "weder Magnete noch Kaefig — der Fluss kommt aus der Erregerwicklung")
for name in ("Field_Coils_N", "Field_Coils_S"):
    o = ze.objekte.get(name)
    # EIN geschlossener Rahmen je Pol -- nicht mehr zwei lose Quader links und
    # rechts des Kerns. Zwei Quader sind zwei Leiterstaebe und keine Wicklung:
    # die Stuecke an den STIRNSEITEN fehlten ganz, und damit war die Spule im
    # CAD nicht geschlossen. Gemeldet, gemessen (10 Flaechen, eine Schale,
    # Fuellgrad 0,17 -- ein Rahmen mit Loch), behoben.
    pruefe(o is not None and len(o.Shape.teile) == k["poles"] // 2,
           f"{name}: {len(o.Shape.teile) if o else 0} Spulen = "
           f"{k['poles'] // 2} Pole dieser Polaritaet, je EINE geschlossene")
r = ze.objekte.get("Slip_Rings")
pruefe(r is not None and len(r.Shape.teile) == 2,
       "ZWEI Schleifringe — der Erregerkreis ist Gleichstrom, kein Drehstrom "
       "(die ASM bekommt drei)")
pruefe(len(ze.objekte["Brushes"].Shape.teile) == 2, "und zwei Buersten")

print("\n10. Die Polmasse kommen aus dem MAGNETKREIS, nicht aus dem Platz")

pg = ema_eesm.polgeometrie(ge, 100.0)
er = ema_eesm.erregung(ge, 100.0)
pruefe(abs(k["b_schuh_mm"] - pg["b_pol_mm"]) < 1e-9,
       f"die Polschuhbreite {k['b_schuh_mm']} mm ist die der Polbedeckung "
       f"({ema_eesm.POLBEDECKUNG}) aus ema_eesm.polgeometrie")
pruefe(abs(k["A_cu_mm2"] - er["A_cu_mm2"]) < 1e-9,
       f"der Kupferquerschnitt {k['A_cu_mm2']} mm² kommt aus erregung() — also "
       f"aus der Stromdichte, nicht aus dem Fenster")
# Mehr Strom durch dieselbe Wicklung -> dickere Spule. Dass die Zeichnung dem
# folgt, ist der eigentliche Punkt: sonst zeigt sie eine andere Maschine.
k_dicht = ema_eesm_cad.koerper(dict(ge, fieldCurrentDensity=2.5), 100.0)
pruefe(k_dicht["d_spule_mm"] > k["d_spule_mm"],
       f"halbe Stromdichte -> dickere Spule ({k_dicht['d_spule_mm']} gegen "
       f"{k['d_spule_mm']} mm)")
# Und ein Pol, der nicht mehr auf die Teilung passt, wird NICHT gezeichnet.
ge_eng = geom(machineType="eesm", p=8, slots=48, rotorOD=120, statorID=121.4,
              shaftD=90)
k_eng = ema_eesm_cad.koerper(ge_eng, 60.0)
if k_eng["passt"]:
    print("     (Beispielgeometrie passt — Weigerung mit gestelltem Befund)")
    import unittest.mock as _mk2
    with _mk2.patch.object(ema_eesm_cad, "koerper",
                           return_value=dict(k_eng, passt=False, grund="zu eng")):
        try:
            skript(ge_eng, 60.0)
            pruefe(False, "ein nicht passender Pol wird abgewiesen")
        except ValueError as e:
            pruefe("nicht zeichenbar" in str(e),
                   f"abgewiesen: {str(e)[:60]}…")
else:
    try:
        skript(ge_eng, 60.0)
        pruefe(False, "ein nicht passender Pol wird abgewiesen")
    except ValueError as e:
        pruefe("nicht zeichenbar" in str(e), f"abgewiesen: {str(e)[:60]}…")

print("\n11. Die Schleifringe haben EINE Quelle")

rg_asm = ema_asm.schleifringe(geom(machineType="asm"), 200.0, rpm_max=6000)
rg_ees = ema_schleifring.geometrie(geom(machineType="eesm"), 200.0, 2,
                                   rpm_max=6000)
pruefe(rg_asm["n_ringe"] == 3 and rg_ees["n_ringe"] == 2,
       "drei Ringe fuer den Drehstromlaeufer, zwei fuer den Erregerkreis")
pruefe(rg_asm["b_ring_mm"] == rg_ees["b_ring_mm"],
       f"bei gleichem Strom dieselbe Ringbreite ({rg_asm['b_ring_mm']} mm) — "
       f"eine Quelle, nicht zwei Fassungen")
pruefe(ema_schleifring.U_BUERSTE_V == ema_eesm.U_BUERSTE_V,
       "und derselbe Buerstenspannungsabfall wie in ema_eesm")
# Die Umfangsgeschwindigkeit ist die Grenze dieser Bauart — und ohne
# Drehzahlangabe steht dort None, nicht „ok".
schnell = ema_schleifring.geometrie(geom(), 200.0, 3, rpm_max=30000)
pruefe(schnell["v_ok"] is False and schnell["v_ring_mps"] > 45,
       f"bei 30.000 1/min reisst die Grenze ({schnell['v_ring_mps']} m/s gegen "
       f"{ema_schleifring.V_RING_MAX_MPS})")
ohne = ema_schleifring.geometrie({"shaftD": 60}, 200.0, 3)
pruefe(ohne["v_ok"] is None,
       "ohne Hoechstdrehzahl steht None da — nicht geprueft ist nicht bestanden")

print("\n12. Der Schenkelpol im Querschnitt — und das Tor davor")

import ema_pipeline as _P
n_eesm = schnitt_zaehlen(ge)
pruefe(n_eesm > 0, f"der Querschnitt zeichnet ihn ({n_eesm} Flaechen)")
_st = {"log": [], "progress": 0}
_P._gate_laeufer({"geom": ge, "axial_len": 100, "rpm_to": 6000}, _st)
pruefe(any("Schenkelpol" in l and "OK" in l for l in _st["log"]),
       "das Laeufertor prueft Kern + Spule gegen die Polteilung")
pruefe(any("NICHT gerechnet" in l for l in _st["log"]),
       "und sagt, was es NICHT prueft (Polbefestigung, Fliehkraft am Polfuss) — "
       "Schweigen laese sich als „geprueft\" lesen")


print("\n13. Das Tor laesst die ASM jetzt ins CAD")

pruefe("cad" in ema_maschinenart.ARTEN["asm"].stufen,
       "ARTEN['asm'].stufen fuehrt 'cad'")
try:
    ema_maschinenart.pruefe_stufe("asm", "cad")
    pruefe(True, "pruefe_stufe('asm','cad') laesst durch")
except ema_maschinenart.ArtNichtUnterstuetzt:
    pruefe(False, "pruefe_stufe('asm','cad') laesst durch")
pruefe("cad" in ema_maschinenart.ARTEN["eesm"].stufen,
       "und die EESM ebenfalls — Schenkelpol, Erregerspulen, zwei Schleifringe")
pruefe("feld" not in ema_maschinenart.ARTEN["eesm"].stufen,
       "aber NICHT die Feldstufe: die 2-D-FDM ist reell und magnetostatisch und "
       "kann eine Gleichstrom-Erregerwicklung so wenig darstellen wie einen "
       "Kaefig — das steht als Luecke da statt als stille Vollstaendigkeit")
try:
    ema_maschinenart.pruefe_stufe("synrm", "cad")
    pruefe(False, "synrm wird von der CAD-Stufe noch abgewiesen")
except ema_maschinenart.ArtNichtUnterstuetzt:
    pruefe(True, "synrm wird von der CAD-Stufe noch abgewiesen "
                 "(ehrlich, statt PSM-Geometrie unter falschem Namen)")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
