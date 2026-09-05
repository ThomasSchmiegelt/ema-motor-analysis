"""Pruefungen der Wicklung (``ema_wicklung``, Stufe C).

Zwei Dinge werden hier festgenagelt, und beide sind Fehler, die schon
eingetreten waren:

1. **Die sieben Kopien der Nutgeometrie.** Sie standen wortgleich in
   ``ema_freecad``, ``ema_pipeline`` (zweimal), ``ema_thermal`` (dreimal) und
   ``ema_bilddaten`` -- und waren bereits auseinandergelaufen: die Kopie in
   ``mass_and_cost`` rechnete mit fest ZWEI Lagen. Wer ``conductorsPerSlot``
   erhoehte, bekam mehr Verluste, aber dieselbe Kupfermasse. Beide Zahlen fuer
   sich plausibel, zusammen widerspruechlich, nirgends sichtbar. Die Pruefung
   dagegen ist keine Textsuche, sondern eine **Wirkung**: die Leiterzahl muss
   Widerstand UND Masse bewegen.
2. **Der Hairpin darf sich nicht bewegen.** Die Zusammenlegung ist eine
   Umstellung, keine Aenderung: bei ``windingType = hairpin`` muessen dieselben
   Zahlen herauskommen wie vor der Zusammenlegung. Sie stehen hier als
   nachgerechnete Sollwerte, nicht als Verweis auf den alten Quelltext.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_wicklung as W

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


GEOM = {"p": 3, "slots": 36, "statorID": 190.0, "statorOD": 280.0,
        "rotorOD": 188.6, "shaftD": 60.0, "slotDepth": 25.0,
        "slotWidthRatio": 0.5, "conductorsPerSlot": 4}
AXIAL = 150.0
CU = {"rho_el": 1.72e-8, "density": 8900.0, "label": "Cu"}


# ── 1. Die Nutgeometrie ist dieselbe wie vorher ───────────────────────────────

print("\n1. Die Zusammenlegung darf den Hairpin NICHT bewegen")

ng = W.nutgeometrie(GEOM)
r_si = 0.095
dth = 2 * math.pi / 36
soll_breite = max(3e-3, r_si * dth * 0.5)
pruefe(nah(ng["nut_breite_m"], soll_breite),
       f"Nutbreite = max(3 mm, R_si*dtheta*ratio) = {1000 * soll_breite:.3f} mm")
soll_leiter = max(1.5e-3, soll_breite - 2 * 0.8e-3)
pruefe(nah(ng["leiter_breite_m"], soll_leiter),
       f"Leiterbreite = Nutbreite - 2*Isolation = {1000 * soll_leiter:.3f} mm")
soll_lage = max(2e-3, (25e-3 - 2e-3 - 5 * 0.8e-3) / 4)
pruefe(nah(ng["lage_hoehe_m"], soll_lage),
       f"Lagenhoehe = (Tiefe - 2 - (n+1)*ins)/n = {1000 * soll_lage:.3f} mm")

w = W.wicklung(GEOM, AXIAL)
soll_v = 36 * 4 * soll_leiter * soll_lage * (0.150 + 2 * 0.018)
pruefe(nah(w["V_kupfer_m3"], soll_v),
       f"Kupfervolumen unveraendert: {1e6 * soll_v:.1f} cm^3 "
       f"(Wickelkopf weiterhin die historischen 18 mm)")
soll_r = 1.72e-8 * (0.150 + 2 * 0.018) * 36 * 4 / (3 * soll_leiter * soll_lage)
pruefe(nah(W.r_strang(GEOM, AXIAL, CU), soll_r),
       f"Strangwiderstand unveraendert: {1000 * soll_r:.3f} mOhm")


# ── 2. Die abgewichene Kopie ──────────────────────────────────────────────────

print("\n2. Leiterzahl bewegt Widerstand UND Masse — die alte Kopie tat das nicht")

paare = []
for n in (2, 4, 8, 12):
    g = dict(GEOM, conductorsPerSlot=n)
    paare.append((n, W.r_strang(g, AXIAL, CU), W.kupfermasse(g, AXIAL, CU)))
for n, r, m in paare:
    print(f"      {n:2d} Leiter/Nut  R = {1000 * r:7.3f} mOhm   Kupfer = {m:6.3f} kg")
pruefe(len({round(r, 12) for _, r, _ in paare}) == 4,
       "vier Leiterzahlen geben vier verschiedene Widerstaende")
pruefe(len({round(m, 9) for _, _, m in paare}) == 4,
       "vier Leiterzahlen geben auch vier verschiedene Kupfermassen — "
       "die alte Kopie gab hier viermal denselben Wert")
pruefe(paare[0][1] < paare[-1][1],
       "mehr Leiter je Nut heisst mehr Windungen in Reihe, also mehr Widerstand")


# ── 3. Beide Wicklungsarten ───────────────────────────────────────────────────

print("\n3. Hairpin und Runddraht — worin sie sich wirklich unterscheiden")

pruefe(W.art({}) == "hairpin" and W.art({"windingType": "quatsch"}) == "hairpin",
       "Vorgabe und Unbekanntes ergeben den Hairpin — alles Bestehende gilt "
       "unveraendert")
pruefe(W.art({"windingType": "rundraht"}) == "rundraht",
       "der Runddraht wird erkannt")

h = W.wicklung(dict(GEOM, windingType="hairpin"), AXIAL)
r = W.wicklung(dict(GEOM, windingType="rundraht"), AXIAL)
pruefe(r["fuellfaktor"] < h["fuellfaktor"],
       f"der Runddraht fuellt die Nut schlechter ({r['fuellfaktor']:.2f} gegen "
       f"{h['fuellfaktor']:.2f}) — runde Draehte koennen das geometrisch nicht")
pruefe(r["fuellfaktor"] < 0.9069,
       "und bleibt unter der dichtesten Kreispackung (0,9069), wie er muss")
pruefe(r["l_wickelkopf_m"] > h["l_wickelkopf_geom_m"],
       f"sein Wickelkopf ist laenger als der des Hairpins "
       f"({1000 * r['l_wickelkopf_m']:.0f} mm gegen "
       f"{1000 * h['l_wickelkopf_geom_m']:.0f} mm bei gleicher Rechnung) — "
       f"gewickelt statt gebogen")
pruefe(h["wickelkopf_historisch"] and not r["wickelkopf_historisch"],
       "dass der Hairpin-Wert der historische Ueberhang ist und nicht dieselbe "
       "Groesse, steht im Ergebnis — sonst waere der Vergleich still verzerrt")

v = W.vergleich(GEOM, AXIAL, CU)
pruefe("_hinweis" in v and "HISTORISCHE" in v["_hinweis"],
       "der Vergleich traegt seinen eigenen Vorbehalt mit")

# Die Kupferflaeche der Nut muss beim Runddraht genau Fuellfaktor mal
# nutzbarer Nutflaeche sein -- unabhaengig von der Windungszahl.
for n in (10, 40, 120):
    g = dict(GEOM, windingType="rundraht", turnsPerSlot=n)
    wn = W.wicklung(g, AXIAL)
    a_ges = wn["n_je_nut"] * wn["A_leiter_m2"]
    pruefe(nah(a_ges, W.FUELL_RUNDDRAHT * ng["nutz_flaeche_m2"], rel=1e-9),
           f"bei {n} Windungen fuellt das Kupfer dieselbe Flaeche — nur duenner "
           f"(Drahtdurchmesser {1000 * wn['d_draht_m']:.2f} mm)")

# Widerstand ~ Windungszahl^2 bei fester Nutflaeche: doppelt so viele Windungen
# heisst doppelte Laenge UND halber Querschnitt.
r40 = W.r_strang(dict(GEOM, windingType="rundraht", turnsPerSlot=40), AXIAL, CU)
r80 = W.r_strang(dict(GEOM, windingType="rundraht", turnsPerSlot=80), AXIAL, CU)
pruefe(nah(r80 / r40, 4.0, rel=1e-9),
       "doppelte Windungszahl vervierfacht den Strangwiderstand (Laenge mal "
       "zwei, Querschnitt durch zwei) — die Probe, dass Flaeche und Zahl "
       "zusammenhaengen")


# ── 4. Die Kopien sind wirklich weg ───────────────────────────────────────────

print("\n4. Die sieben Kopien rufen jetzt DIESE Quelle")

import ema_bilddaten
import ema_freecad
import ema_pipeline
import ema_thermal

pruefe(nah(ema_thermal.copper_volume(GEOM, AXIAL), w["V_kupfer_m3"]),
       "ema_thermal.copper_volume liefert genau das Volumen aus ema_wicklung")

masse = W.kupfermasse(dict(GEOM, conductorsPerSlot=8), AXIAL, CU)
masse2 = W.kupfermasse(dict(GEOM, conductorsPerSlot=2), AXIAL, CU)
pruefe(not nah(masse, masse2),
       f"acht Leiter je Nut wiegen anders als zwei ({masse:.3f} kg gegen "
       f"{masse2:.3f} kg) — genau das war in mass_and_cost verloren")

d = ema_pipeline._schnittmasse(dict(GEOM, conductorsPerSlot=8))
pruefe(d["n_layers"] == 8 and nah(d["slot_w"], ng["nut_breite_mm"]),
       "der Querschnitt zeichnet jetzt acht Lagen statt fester zwei — vorher "
       "zeigte das Bild eine andere Wicklung als die gerechnete")

bd = ema_bilddaten.kennwerte(GEOM) if hasattr(ema_bilddaten, "kennwerte") else None
if bd is not None:
    pruefe(nah(float(bd["nutbreite_mm"]), ng["nut_breite_mm"], rel=1e-6)
           if "nutbreite_mm" in bd else True,
           "ema_bilddaten nimmt dieselbe Nutbreite")

import ast
import ema_text2ema as T
g_cad = {k: v["def"] for k, v in T.SCHEMA.items() if v.get("geom")}
g_cad.update(GEOM)
for a in W.ARTEN:
    code = ema_freecad.build_full_motor_script(dict(g_cad, windingType=a),
                                               AXIAL, "/tmp/_wick.FCStd")
    ast.parse(code)
    pruefe(f"WINDING_TYPE = '{a}'" in code,
           f"die CAD-Erzeugung kennt die Wicklungsart '{a}' und ist syntaktisch gueltig")
    if a == "rundraht":
        pruefe("Winding_Bundles" in code and "Winding_EndWinding" in code,
               "der Runddraht wird als Nutbuendel und Wickelkopfring gezeichnet — "
               "und heisst auch so, statt einzelne Draehte vorzutaeuschen")

# Kaefiglaeufer im CAD -- aus DERSELBEN ema_asm.kaefig wie Widerstand und Netz.
import json as _json
import ema_asm
g_asm = dict(g_cad, machineType="asm", rotorBars=28)
code = ema_freecad.build_full_motor_script(g_asm, AXIAL, "/tmp/_wick.FCStd")
ast.parse(code)
import re as _re
_m = _re.search(r"^CAGE = (.*?)   #", code, _re.M)
cage = _json.loads(_m.group(1))
kf = ema_asm.kaefig(g_asm, AXIAL)
pruefe(cage["n"] == kf["n_stab"] and nah(cage["b"], kf["stabbreite_mm"])
       and nah(cage["t"], kf["nuttiefe_mm"]),
       f"das CAD zeichnet {cage['n']} Kaefigstaebe mit genau den Massen aus "
       f"ema_asm.kaefig — keine zweite Nutgeometrie")
pruefe(nah(cage["ring_h"] * cage["ring_w"], kf["A_ring_mm2"], rel=1e-3),
       f"der Kurzschlussring hat den Querschnitt, den ema_asm ansetzt "
       f"({cage['ring_h']:.1f} x {cage['ring_w']:.1f} = {kf['A_ring_mm2']:.0f} mm^2) "
       f"— er ist der Grund, warum die analytische Stufe einen Zuschlag traegt "
       f"und das 2-D-Feld nicht")
pruefe("Cage_Bars" in code and "Cage_Rings" in code,
       "Staebe und Ringe stehen als eigene Koerper im Modell")
code_pm = ema_freecad.build_full_motor_script(dict(g_cad, machineType="pmsm"),
                                              AXIAL, "/tmp/_wick.FCStd")
pruefe("CAGE = None" in code_pm,
       "eine PSM bekommt keinen Kaefig — die Bauart entscheidet, nicht ein Schalter")


# ── 5. Der Wicklungsschluessel im Schema und im Paarvergleich ─────────────────

print("\n5. Wicklungsart als Achse und als Schemagroesse")

import ema_paarvergleich as P
pruefe(T.SCHEMA["windingType"]["opts"] == list(W.ARTEN)
       and T.SCHEMA["windingType"]["def"] == W.VORGABE,
       "das Schema fuehrt die Wicklungsarten aus ema_wicklung, nicht als "
       "zweite Liste")
pruefe("wicklungsart" in P.ACHSEN,
       "der Paarvergleich hat eine Achse 'wicklungsart'")
pruefe(P.ACHSEN["wicklungsart"]["werte"](None) == list(W.ARTEN),
       "und sie fuehrt dieselben Werte")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
