"""Pruefungen der radialen Ordnung (``ema_radien``, Stufe E).

Der Aussenlaeufer ist der Fall, in dem eine falsche Zahl am wenigsten
widerspricht. Alle drei Fehler, gegen die hier geprueft wird, waeren ohne
Absturz durchgelaufen:

* Der Luftspalt ``(statorID - rotorOD)/2`` ist an einem Aussenlaeufer
  **negativ** -- und mit der Klemme ``max(..., 0,3)`` dann 0,3 mm. Eine Zahl,
  die aussieht wie ein enger Luftspalt.
* Die Fliehkraft mit ``a = shaftD/2`` und ``b = rotorOD/2`` haette an einem
  Aussenlaeufer einen Ring gerechnet, der die halbe Maschine umfasst -- also
  eine Spannung an einer Stelle, an der gar kein Blech ist.
* Der Kerbfaktor der Magnettasche haette weitergegolten, obwohl am
  Aussenlaeufer kein Steg die Magnete haelt.

Dazu die Probe, dass sich am Innenlaeufer **nichts** bewegt: die Zusammenlegung
der neun Luftspalt-Kopien in ``ema_analysis`` ist eine Umstellung, keine
Aenderung.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_analysis
import ema_radien as R
import ema_rotorcheck as RC

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def nah(a, b, rel=1e-9):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-30)


INNEN = {"p": 3, "slots": 36, "statorID": 190.0, "statorOD": 280.0,
         "rotorOD": 188.6, "shaftD": 60.0}
AUSSEN = {"p": 3, "slots": 36, "statorID": 60.0, "statorOD": 180.0,
          "rotorID": 181.4, "rotorOD": 200.0, "shaftD": 40.0,
          "rotorPosition": "aussen"}
MAT = {"density": 7650.0, "nu": 0.30, "yield_mpa": 340.0}


# ── 1. Die Bauform wird erkannt, und die Vorgabe bleibt der Innenlaeufer ──────

print("\n1. Bauform")

pruefe(R.bauform({}) == "innen" and R.bauform({"rotorPosition": "quatsch"}) == "innen",
       "Vorgabe und Unbekanntes ergeben den Innenlaeufer — alles Bestehende "
       "gilt unveraendert")
for w in ("aussen", "außen", "outer", "Aussenlaeufer"):
    pruefe(R.bauform({"rotorPosition": w}) == "aussen",
           f"'{w}' wird als Aussenlaeufer gelesen")
pruefe(R.bauform({"geom": {"rotorPosition": "aussen"}}) == "aussen",
       "auch aus einem vollen Payload (geom-Ebene)")


# ── 2. Der Luftspalt — die Zahl, die still falsch gewesen waere ───────────────

print("\n2. Luftspalt: dieselben 0,7 mm, aber zwischen den richtigen Flaechen")

ri, ra = R.radien(INNEN), R.radien(AUSSEN)
pruefe(nah(ri["luftspalt_mm"], 0.7, rel=1e-6),
       f"Innenlaeufer: {ri['luftspalt_mm']:.3f} mm zwischen rotorOD und statorID")
pruefe(nah(ra["luftspalt_mm"], 0.7, rel=1e-6),
       f"Aussenlaeufer: {ra['luftspalt_mm']:.3f} mm zwischen statorOD und rotorID")

alt = max((AUSSEN["statorID"] - AUSSEN["rotorOD"]) / 2.0, 0.3)
pruefe(alt == 0.3 and not nah(alt, ra["luftspalt_mm"]),
       f"die alte Formel haette am Aussenlaeufer {alt:.1f} mm gemeldet "
       f"(negativ, dann geklemmt) statt {ra['luftspalt_mm']:.3f} mm — sie "
       f"widerspricht nicht, sie ist nur falsch")

pruefe(ri["nach_stator"] > 0 > ra["nach_stator"],
       "die Richtung zum Stator kehrt sich um (+1 gegen -1)")
pruefe(nah(ri["r_rotor_gap_mm"], 94.3) and nah(ra["r_rotor_gap_mm"], 90.7),
       "die Laeuferflaeche AM Luftspalt ist einmal rotorOD/2 und einmal "
       "rotorID/2 — wer nach Rolle fragt, muss die Bauform nicht kennen")

for name, g in (("innen", INNEN), ("aussen", AUSSEN)):
    pruefe(nah(ema_analysis.luftspalt_mm(g), R.radien(g)["luftspalt_mm"], rel=1e-9),
           f"ema_analysis.luftspalt_mm folgt ema_radien ({name})")
    r_soll = 0.5 * (R.radien(g)["r_rotor_gap_mm"] + R.radien(g)["r_stator_gap_mm"]) / 1000
    pruefe(nah(ema_analysis.r_gap_m(g), r_soll),
           f"und r_gap_m liegt in der Spaltmitte ({1000 * r_soll:.2f} mm, {name})")

# Fehlende Masse: klarer Fehler statt einer erfundenen Zahl.
try:
    R.radien({"rotorPosition": "aussen", "statorOD": 180.0, "rotorOD": 200.0,
              "rotorID": 179.0})
    pruefe(False, "ein Ring INNERHALB des Stators muss auffallen")
except ValueError as e:
    pruefe("Luftspalt nicht positiv" in str(e),
           "ein Laeuferring innerhalb des Stators gibt einen klaren Fehler")
try:
    R.radien({"rotorPosition": "aussen", "statorOD": 180.0, "rotorID": 181.4,
              "rotorOD": 181.5})
    pruefe(False, "ein Ring von 0,05 mm Wand muss auffallen")
except ValueError as e:
    pruefe("Wandstaerke" in str(e),
           "ein Ring von 0,05 mm Wand gibt einen klaren Fehler — geometrisch "
           "gueltig, physikalisch keiner, und die Lame-Loesung haette trotzdem "
           "eine Zahl ausgegeben")


# ── 3. Der Innenlaeufer bewegt sich nicht ─────────────────────────────────────

print("\n3. Am Innenlaeufer aendert sich nichts (Umstellung, keine Aenderung)")

pruefe(nah(ema_analysis.luftspalt_mm(INNEN),
           max((INNEN["statorID"] - INNEN["rotorOD"]) / 2.0, 0.3)),
       "der Luftspalt ist genau der alte Ausdruck")
pruefe(nah(ema_analysis.r_gap_m(INNEN),
           ((INNEN["statorID"] / 2) + (INNEN["rotorOD"] / 2)) / 2 / 1000),
       "und r_gap_m genau der alte Ausdruck")

perf = ema_analysis.compute_performance(INNEN, 0.85, rpm=3000, axial_mm=150)
pruefe(nah(float(perf["air_gap_mm"]), 0.7, rel=1e-3),
       f"compute_performance meldet weiterhin {perf['air_gap_mm']} mm Luftspalt")


# ── 4. Fliehkraft: ein anderer Ring, nicht ein anderes Vorzeichen ─────────────

print("\n4. Fliehkraft und Magnethaltung")

si = RC.rotor_stress_check(INNEN, MAT, {"n_max": 12000})
sa = RC.rotor_stress_check(AUSSEN, MAT, {"n_max": 12000})
pruefe(nah(si["a_mm"], 30.0) and nah(si["b_mm"], 94.3),
       f"Innenlaeufer: der tragende Ring geht von der Welle bis zum Luftspalt "
       f"({si['a_mm']:.1f}..{si['b_mm']:.1f} mm)")
pruefe(nah(sa["a_mm"], 90.7) and nah(sa["b_mm"], 100.0),
       f"Aussenlaeufer: vom Luftspalt nach aussen ({sa['a_mm']:.1f}.."
       f"{sa['b_mm']:.1f} mm) — mit shaftD als Innenradius waere ein Ring "
       f"gerechnet worden, an dem gar kein Blech ist")

# Was die alte Rechnung am Aussenlaeufer ergeben haette.
falsch = RC._bore_hoop_mpa(AUSSEN["shaftD"] / 2e3, AUSSEN["rotorOD"] / 2e3,
                           MAT["density"], 2 * math.pi * 12000 / 60,
                           MAT["nu"] / (1 - MAT["nu"]))
pruefe(abs(falsch - sa["sigma_bore_conservative_MPa"]) > 10.0,
       f"sie haette {falsch:.0f} MPa gemeldet statt "
       f"{sa['sigma_bore_conservative_MPa']:.0f} MPa — beides plausible Zahlen, "
       f"eine davon an der falschen Stelle")

mi, ma = R.magnethaltung(INNEN), R.magnethaltung(AUSSEN)
pruefe(mi["steg_traegt_magnete"] and not ma["steg_traegt_magnete"],
       "am Innenlaeufer haelt der Steg die Magnete, am Aussenlaeufer der Ring "
       "selbst — die Fliehkraft drueckt sie GEGEN ihn")
pruefe(si["kt_pocket"] == RC.KT_POCKET and sa["kt_pocket"] == 1.0,
       f"der Kerbfaktor der Magnettasche gilt nur dort, wo eine Tasche traegt "
       f"({si['kt_pocket']} gegen {sa['kt_pocket']}) — sonst waere er eine "
       f"erfundene Verschaerfung")
pruefe(si["bauform"] == "innen" and sa["bauform"] == "aussen",
       "die Bauform steht im Ergebnis, nicht nur in der Rechnung")


# ── 5. Was die Bauform NICHT traegt, wird abgewiesen ──────────────────────────

print("\n5. Das Tor — kein Innenlaeufer-Ergebnis unter fremdem Namen")

pruefe(R.pruefe_bauform(INNEN, "cad") == "innen",
       "der Innenlaeufer geht durch jede Stufe")
pruefe(R.pruefe_bauform(AUSSEN, "analytisch") == "aussen",
       "der Aussenlaeufer ist analytisch getragen")
for stufe in ("feld", "cad", "em3d"):
    try:
        R.pruefe_bauform(AUSSEN, stufe)
        pruefe(False, f"Stufe '{stufe}' muss den Aussenlaeufer abweisen")
    except R.BauformNichtUnterstuetzt as e:
        pruefe("traegt ihn noch nicht" in str(e),
               f"Stufe '{stufe}' weist den Aussenlaeufer ab, mit Begruendung")

import ema_pipeline
try:
    ema_pipeline._gate_maschinenart({"geom": dict(AUSSEN)}, None, "feld")
    pruefe(False, "das Pipeline-Tor muss den Aussenlaeufer abweisen")
except R.BauformNichtUnterstuetzt:
    pruefe(True, "das Pipeline-Tor weist ihn ab, bevor irgendeine Physik laeuft")

import copy

import ema_paarvergleich as P
pruefe("bauform" in P.ACHSEN
       and P.ACHSEN["bauform"]["werte"](None) == list(R.BAUFORMEN),
       "der Paarvergleich hat eine Achse 'bauform' aus derselben Liste")

# Die Achse muss die Maschine WIRKLICH umbauen, sonst haette sie nur eine
# baubare Option: ein Aussenlaeufer ohne Laeuferring hat keinen Luftspalt.
basis = {"geom": dict(INNEN, slotDepth=22.0, statorOD=260.0)}
um = copy.deepcopy(basis)
P.ACHSEN["bauform"]["setzen"](um, "aussen")
gu = um["geom"]
r_alt, r_neu = R.radien(basis["geom"]), R.radien(gu)
pruefe(r_neu["bauform"] == "aussen",
       "die Achse stellt die Bauform um")
pruefe(nah(r_neu["luftspalt_mm"], r_alt["luftspalt_mm"], rel=1e-9)
       and nah(r_neu["r_gap_mm"], r_alt["r_gap_mm"], rel=1e-9),
       f"und laesst den Luftspalt, wo er war ({r_neu['luftspalt_mm']:.3f} mm bei "
       f"r = {r_neu['r_gap_mm']:.2f} mm) — alles Uebrige gleich, sonst waere es "
       f"kein Vergleich")
pruefe(gu["rotorOD"] > gu["rotorID"] > gu["statorOD"] > gu["statorID"] > gu["shaftD"],
       f"die Ordnung stimmt: shaftD {gu['shaftD']:.0f} < statorID "
       f"{gu['statorID']:.1f} < statorOD {gu['statorOD']:.1f} < rotorID "
       f"{gu['rotorID']:.1f} < rotorOD {gu['rotorOD']:.1f}")

import ema_text2ema as T
pruefe(T.SCHEMA["rotorPosition"]["opts"] == list(R.BAUFORMEN)
       and T.SCHEMA["rotorPosition"]["def"] == R.VORGABE,
       "und das Schema fuehrt sie ebenfalls aus ema_radien")

# Die Zurechtrueckung im Schema darf die Bauform nicht aufheben.
roh = {k: v.get("def") for k, v in T.SCHEMA.items()}
roh.update(rotorPosition="aussen", statorOD=180, statorID=60, rotorOD=200,
           shaftD=40, rotorID=0)
v = T._validate(roh)
g = dict(v)
g["rotorPosition"] = v.get("rotorPosition", "innen")
pruefe(g["rotorPosition"] == "aussen" and g["rotorOD"] > g["rotorID"] > g["statorOD"],
       f"die Zurechtrueckung haelt die Ordnung des Aussenlaeufers "
       f"(statorOD {g['statorOD']} < rotorID {g['rotorID']} < rotorOD "
       f"{g['rotorOD']}) — vorher zog sie den Laeufer still wieder nach innen")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
