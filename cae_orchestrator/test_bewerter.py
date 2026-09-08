"""Der Schnellbewerter sieht die Zeichnung — ohne Server, ohne FreeCAD.

Anlass steht in ``BEFUNDE.md`` (08.09.2026): ``_analytical_Bgap`` rechnete fuer
GEZEICHNETE Geometrien mit ``n_legs * geom["magWidth"]`` und ``perm(magThick)``,
also mit den PARAMETRISCHEN Feldern. Zwei Magnete zu 6 mm und zwei zu 60 mm Laenge
ergaben denselben Wert, 2 mm und 6 mm Dicke ebenso, 0 Grad und 60 Grad Neigung
ebenso — allein die Anzahl bewegte etwas, und die genau linear.

Das ist der Anker, an dem das FDM-Feld kalibriert wird; er traegt Kt, den Strom und
ueber ihn die Verluste. Der Magnetfeinschliff (``ema_design_optimize``) verschiebt
Magnetkoordinaten und bewertet damit — seine Zielgroesse aenderte sich also nie.

Aufruf: ``venv/bin/python test_bewerter.py``
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_analysis as A
import ema_design_ai as DAI
import ema_design_optimize as DOPT
import ema_optimize as OPT

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


GEOM = {"p": 3, "slots": 36, "statorOD": 280.0, "statorID": 190.0,
        "rotorOD": 188.6, "shaftD": 60.0, "axialLen": 80.0, "magThick": 6.0,
        "magWidth": 24.0, "magAngle": 120.0, "magAsym": 0.0,
        "magDepthRel": 0.68, "magDist": 5.0, "slotDepth": 30.0,
        "magGapMm": 0.1, "magLayers": 2, "magLayerGap": 8.0,
        "poleArcFrac": 0.85, "segPerPole": 6, "magAngle2": 100.0,
        "magTangLen": 12.0, "conductorsPerSlot": 6}


def _gez(n, laenge, dicke, neigung=60.0):
    """n gezeichnete Magnete, gleichmaessig ueber den Pol verteilt."""
    g = dict(GEOM)
    g["magShape"] = "custom"
    g["customLegs"] = [
        {"r_pos": 73.7, "offset": (i - (n - 1) / 2) * 8.0, "tilt_deg": neigung,
         "length": laenge, "thickness": dicke, "mag_sign": 1}
        for i in range(n)]
    return g


# ── 1. Die parametrischen Bauformen aendern sich um keine Stelle ────────────
# Der Anker fuer alles Weitere: waeren sie mitgewandert, waere jede alte Rechnung
# stillschweigend eine andere geworden.
print("1. Die parametrischen Bauformen sind unveraendert")
GOLD = {"v": 0.358013, "vasym": 0.358013, "vv": 0.716025, "u": 0.358013,
        "delta": 0.483317, "pmasynrm": 0.165359, "spm": 0.856799,
        "halbach": 0.942478, "spoke": 0.551197, "bar": 0.206699}
for form, soll in GOLD.items():
    g = dict(GEOM); g["magShape"] = form
    ist = A._analytical_Bgap(g)
    pruefe(abs(ist - soll) < 1e-6, f"{form:9s} {ist:.6f} T (unveraendert)")


# ── 2. Die Zeichnung bewegt die Zahl ────────────────────────────────────────
print("\n2. Laenge, Dicke und Neigung bewegen das Luftspaltfeld")
b = {name: A._analytical_Bgap(g) for name, g in {
    "24mm": _gez(2, 24, 6), "6mm": _gez(2, 6, 6), "60mm": _gez(2, 60, 6),
    "dick6": _gez(2, 24, 6), "duenn2": _gez(2, 24, 2),
    "t20": _gez(2, 24, 6, 20.0), "t60": _gez(2, 24, 6, 60.0),
    "t90": _gez(2, 24, 6, 90.0),
    "2x24": _gez(2, 24, 6), "4x12": _gez(4, 12, 6), "4x24": _gez(4, 24, 6),
}.items()}
pruefe(b["6mm"] < b["24mm"] < b["60mm"],
       f"Laenge: 6 mm {b['6mm']:.4f} < 24 mm {b['24mm']:.4f} < 60 mm {b['60mm']:.4f} T "
       f"(vorher alle drei 0,4134)")
pruefe(abs(b["60mm"] / b["6mm"] - 10.0) < 0.05,
       "und zwar linear — zehnfache Laenge, zehnfaches Feld")
pruefe(b["duenn2"] < b["dick6"],
       f"Dicke: 2 mm {b['duenn2']:.4f} < 6 mm {b['dick6']:.4f} T (ueber die Permeanz)")
pruefe(b["t20"] < b["t60"] < b["t90"],
       f"Neigung: 20° {b['t20']:.4f} < 60° {b['t60']:.4f} < 90° {b['t90']:.4f} T")
pruefe(abs(b["t60"] / b["t90"] - math.sin(math.radians(60))) < 1e-3,
       "die Neigung geht als |sin(tilt)| ein — die radiale Projektion der "
       "Magnetisierung, dieselbe wie in _orient_factor")

# Und der eigentliche Punkt: die ANZAHL entscheidet nicht mehr allein.
pruefe(abs(b["4x12"] - b["2x24"]) < 1e-9,
       f"4 kurze Magnete = 2 lange gleicher Gesamtlaenge ({b['4x12']:.4f} T) — "
       f"vorher waren 4 Magnete stets doppelt so gut wie 2")
pruefe(abs(b["4x24"] / b["2x24"] - 2.0) < 0.02,
       "doppelte Gesamtlaenge bleibt doppeltes Feld — die Anzahl wirkt ueber "
       "die Laenge, nicht neben ihr")


# ── 3. Gleichheitsprobe: parametrisch == gezeichnet ─────────────────────────
print("\n3. Dieselbe Geometrie, parametrisch und gezeichnet")
for form in ("v", "vasym", "u"):
    g = dict(GEOM); g["magShape"] = form
    gc = dict(g)
    gc["magShape"] = "custom"
    gc["customLegs"] = DOPT._mirror_legs(DAI._legs_to_canvas(g))
    bp, bc = A._analytical_Bgap(g), A._analytical_Bgap(gc)
    pruefe(abs(bc - bp) < 1e-6,
           f"{form:6s} parametrisch {bp:.6f} == gezeichnet {bc:.6f} T")
# Bei VV und Delta ist eine Abweichung RICHTIG und keine Panne: die
# parametrische Fassung mittelt (VV: EIN eta ueber zwei verschieden geneigte
# Lagen) bzw. traegt einen eigenen Beiwert (Delta: 0,9 fuer das tangentiale
# Deck). Die Fassung je Leg ist die genauere; das gehoert benannt, nicht
# weggerechnet.
for form in ("vv", "delta"):
    g = dict(GEOM); g["magShape"] = form
    gc = dict(g); gc["magShape"] = "custom"
    gc["customLegs"] = DOPT._mirror_legs(DAI._legs_to_canvas(g))
    bp, bc = A._analytical_Bgap(g), A._analytical_Bgap(gc)
    pruefe(bc != bp,
           f"{form:6s} weicht ab ({bp:.4f} gegen {bc:.4f} T) — die parametrische "
           f"Naeherung mittelt, die Fassung je Leg nicht")


# ── 4. Das Maxwell-Moment sagt, wenn es keines gibt ─────────────────────────
print("\n4. T_maxwell: None statt 0,0, wo der Luftspalt nicht aufgeloest ist")
g = dict(GEOM); g["magShape"] = "v"
for N in (140, 300, 800):
    perf = A.run_em_analysis(g, N=N, rotor_angle=0.0)["performance"]
    pruefe(perf["T_maxwell_Nm"] is None and "nicht aufgeloest" in perf["T_maxwell_grund"],
           f"N={N:3d}: None mit Begruendung — vorher stand hier 0,0 Nm mit der "
           f"Herkunft 'fdm2d' daneben")
# Mit weitem Spalt greift der Fit, und dann steht eine Zahl da (im Leerlauf 0,0 —
# ohne Statorstrom gibt es kein Moment, das ist richtig gerechnet).
gw = dict(g); gw["statorID"] = 196.0                      # 3,7 mm Spalt
perf = A.run_em_analysis(gw, N=800, rotor_angle=0.0)["performance"]
pruefe(perf["T_maxwell_Nm"] is not None and perf["T_maxwell_grund"] == "",
       "weiter Luftspalt bei N=800: der Fit laeuft, es steht eine Zahl da")

# Die Verbraucher muessen None aushalten.
import ema_steckbrief, ema_training
pruefe(ema_steckbrief._z(None, "Nm") == "—", "der Steckbrief zeigt '—'")
pruefe(ema_training._g(None, "Nm", 1) is None, "der Trainingssatz laesst es leer")
quelle = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "ema_thermal.py"), encoding="utf-8").read()
pruefe('perf.get("T_maxwell_Nm") or 0.0' in quelle,
       "die Lagerreibung rechnet mit 0, statt an None zu scheitern")
html = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         "ema.html"), encoding="utf-8").read()
pruefe("s.T_maxwell_Nm != null" in html, "die Oberflaeche ruft kein toFixed auf null")
pruefe("document.getElementById('opt-obj-metric').value = 'Kt';" in html,
       "und die Zielwertsuche steht nicht mehr auf einer Kennzahl, die es "
       "ohne aufgeloesten Luftspalt gar nicht gibt")


# ── 5. Der Feinschliff hat wieder ein Ziel ──────────────────────────────────
print("\n5. Der Magnetfeinschliff bewegt sich")
import random
g = dict(GEOM); g["magShape"] = "v"
mags = DAI._legs_to_canvas(g)
mats = OPT._materials({"geom": g, "magnet": "ndfeb_n35", "rotor_lam": "m270_35a",
                       "stator_lam": "m270_35a", "hairpin_mat": "cu_etp"})
op = {"rpm_thermal": 8000.0, "rpm_base": 2500.0, "load_nm": 100.0}
sweep = [round(8000 * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]
bounds, _t = DOPT._bounds(mags, g)
random.seed(7)
kt = []
for _ in range(4):
    _m, legs, bars = DOPT._apply_vec(mags, [], DOPT._random_vec(bounds), g)
    gc = dict(g); gc["magShape"] = "custom"
    gc["customLegs"] = legs; gc["customBarriers"] = bars
    kt.append(OPT._eval_geom(gc, 80.0, mats, op, "water", 25.0, sweep).get("Kt"))
pruefe(len(set(kt)) == len(kt),
       f"vier zufaellige Vektoren, vier verschiedene Kt ({', '.join(str(k) for k in kt)}) "
       f"— vorher lieferte jeder Vektor denselben Wert, die Optimierung "
       f"optimierte also nichts")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
