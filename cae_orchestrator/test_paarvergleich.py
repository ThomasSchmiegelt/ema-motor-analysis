"""Tests fuer den Paarvergleich (`ema_paarvergleich`).

Der Paarvergleich ist die erste Stelle, an der ein Agent ueber die Gestalt der
Maschine redet. Wenn er hier etwas Falsches sagt, faellt das nie wieder auf --
danach wird nur noch verfeinert. Fuenf Zusagen werden deshalb festgehalten:

1. **Der Magnetwerkstoff wirkt wirklich.** ``_analytical_Bgap`` liest eine
   Modul-Globale, nicht den Payload. Ohne das Umsetzen von
   ``ema_analysis.Br_NdFeB`` waere die ganze Achse still wirkungslos -- und eine
   Tabelle, in der jede Magnetsorte dasselbe Kt hat, sieht nach einem Befund aus.
2. **Und sie wird zurueckgesetzt**, auch wenn die Bewertung mittendrin scheitert.
   Eine haengengebliebene Globale wuerde jede spaetere Rechnung im selben Prozess
   verfaelschen.
3. **Was sich nicht bewegen DARF, bewegt sich nicht.** Leiterzahl, Kuehlung und
   Blech lassen Kt unberuehrt -- das ist auf dieser Stufe keine Schwaeche, sondern
   die Modellgrenze, und sie muss nachpruefbar bleiben.
4. **Jede als baubar gemeldete Option besteht das echte Layouttor.** Dieselbe
   Disziplin wie bei der Vorauswahl.
5. **Die Skalierung ist wirklich geometrisch aehnlich** -- und der Luftspalt
   bleibt dabei stehen, weil er fertigungsbedingt ist.
"""

import math
import os
import sys

import ema_analysis
import ema_paarvergleich as PV
from ema_pipeline import LAMINATES, MAGNETS
from ema_rotorcheck import rotor_layout_check

_n_ok = _n_bad = 0


def pruefe(bedingung, text):
    global _n_ok, _n_bad
    if bedingung:
        _n_ok += 1
        print(f"  ✓ {text}")
    else:
        _n_bad += 1
        print(f"  ✗ {text}")


BASIS = {
    "geom": {
        "p": 3, "slots": 36, "conductorsPerSlot": 6,
        "rotorOD": 188.6, "shaftD": 60.0, "shaftBoreD": 0.0,
        "statorID": 190.0, "statorOD": 260.0, "axialLen": 80.0, "slotDepth": 22.0,
        "slotWidthRatio": 0.5,
        "magShape": "vasym", "magThick": 6.0, "magWidth": 32.0, "magDist": 13.5,
        "magAngle": 110.0, "magAngle2": 90.0, "magAsym": 0.0, "magDepthRel": 0.6,
        "magTangLen": 0.0, "magLayerGap": 8.0, "magLayers": 3, "magGapMm": 0.1,
        "nAx": 1, "nCirc": 1, "segPerPole": 6,
    },
    "rotor_lam": "m270_35a", "stator_lam": "m270_35a", "hairpin_mat": "cu_etp",
    "magnet": "ndfeb_n42", "cooling": "water", "axial_len": 80.0,
    "load_nm": 120.0, "rpm_from": 5000.0, "target": {"n_max": 12000.0},
}


def _opt(erg, achse, name_teil):
    for o in erg["achsen"][achse]["optionen"]:
        if name_teil.lower() in o["name"].lower():
            return o
    raise KeyError(f"{name_teil} nicht in {achse}")


print("1. Alle Achsen laufen und liefern vergleichbare Optionen")
import time
t0 = time.time()
erg = PV.vergleiche(BASIS)
dauer = time.time() - t0
pruefe(set(erg["achsen"]) == set(PV.ACHSEN),
       f"alle {len(PV.ACHSEN)} Achsen ausgewertet in {dauer:.2f} s")
duenn = [n for n, a in erg["achsen"].items() if a["brauchbar"] < 2]
pruefe(not duenn, f"jede Achse hat mindestens zwei baubare Optionen ({duenn})")
for name, a in erg["achsen"].items():
    n = len(a["paare"])
    soll = a["brauchbar"] * (a["brauchbar"] - 1) // 2
    if n != soll:
        pruefe(False, f"{name}: {n} Paare statt {soll}")
        break
else:
    pruefe(True, "je Achse genau n·(n−1)/2 Paare")


print("\n2. Der Magnetwerkstoff wirkt — und wird zurueckgesetzt")
kt = {o["wert"]: o.get("Kt_Nm_per_A") for o in erg["achsen"]["magnetwerkstoff"]["optionen"]
      if o.get("ok")}
pruefe(len(set(kt.values())) == len(kt),
       f"jede Magnetsorte ergibt ein eigenes Kt ({kt})")
nach_br = sorted(kt, key=lambda k: MAGNETS[k]["Br"])
pruefe(all(kt[a] < kt[b] for a, b in zip(nach_br, nach_br[1:])),
       "Kt waechst monoton mit der Remanenz Br")
pruefe(abs(ema_analysis.Br_NdFeB - 1.15) < 1e-9 and abs(ema_analysis.MU_R_MAG - 1.05) < 1e-9,
       f"die Modul-Globalen stehen wieder auf ihrem Ausgangswert "
       f"({ema_analysis.Br_NdFeB}, {ema_analysis.MU_R_MAG})")

# Auch wenn es mittendrin knallt: das finally muss greifen.
_br, _mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
_echt = ema_analysis.compute_performance
try:
    def _knall(*a, **k):
        raise RuntimeError("absichtlich")
    ema_analysis.compute_performance = _knall
    PV.compute_performance = _knall
    try:
        PV._bewerte({**BASIS, "geom": dict(BASIS["geom"])}, 12000.0, 5000.0, 120.0)
    except RuntimeError:
        pass
finally:
    ema_analysis.compute_performance = _echt
    PV.compute_performance = _echt
pruefe(ema_analysis.Br_NdFeB == _br and ema_analysis.MU_R_MAG == _mu,
       "nach einem Fehler mitten in der Bewertung sind die Globalen unveraendert")


print("\n3. Was sich nicht bewegen darf, bewegt sich nicht")
for achse in ("hairpins", "kuehlung", "blech", "leiterwerkstoff"):
    sp = erg["achsen"][achse]["spannweite"].get("Kt_Nm_per_A")
    pruefe(sp is not None and sp["spanne_pct"] < 0.5,
           f"{achse}: Kt unbewegt ({sp['spanne_pct'] if sp else '?'} %)")
sp_kt = erg["achsen"]["anordnung"]["spannweite"]["Kt_Nm_per_A"]["spanne_pct"]
pruefe(sp_kt > 50, f"die Anordnung bewegt Kt dagegen deutlich ({sp_kt:.0f} %)")


print("\n4. Die Kuehlung ordnet das Dauermoment richtig")
td = {o["wert"]: o["T_dauer_Nm"] for o in erg["achsen"]["kuehlung"]["optionen"] if o["ok"]}
reihe = ["natural", "forced", "water", "oil"]
pruefe(all(td[a] < td[b] for a, b in zip(reihe, reihe[1:])),
       f"natural < forced < water < oil ({[td[k] for k in reihe]})")
pruefe(erg["achsen"]["kuehlung"]["spannweite"]["gesamt_kg"]["spanne_pct"] < 0.5,
       "die Kuehlung aendert die Masse nicht")


print("\n5. Jede baubar gemeldete Option besteht das echte Tor")
# Wie bei der Vorauswahl: nicht der Naeherung glauben, sondern rotor_layout_check
# ueber die zurueckgegebene Geometrie fahren.
fehl = []
for name, a in erg["achsen"].items():
    achse = PV.ACHSEN[name]
    for o in a["optionen"]:
        if not o.get("ok"):
            continue
        p = {k: v for k, v in BASIS.items() if k != "geom"}
        p["geom"] = dict(BASIS["geom"])
        achse["setzen"](p, o["wert"])
        from ema_screen import einpassen
        g = einpassen(p["geom"], None)["geom"]
        if not rotor_layout_check(g)["ok"]:
            fehl.append((name, o["name"]))
pruefe(not fehl, f"alle als baubar gemeldeten Optionen bestehen das Tor ({fehl[:3]})")


print("\n6. Durchmesser: geometrisch aehnlich, Luftspalt bleibt")
spalt0 = (BASIS["geom"]["statorID"] - BASIS["geom"]["rotorOD"]) / 2
for f in (0.8, 1.2):
    p = {k: v for k, v in BASIS.items() if k != "geom"}
    p["geom"] = dict(BASIS["geom"])
    PV._setz_durchmesser(p, BASIS["geom"]["statorOD"] * f)
    g = p["geom"]
    spalt = (g["statorID"] - g["rotorOD"]) / 2
    pruefe(abs(spalt - spalt0) < 1e-6,
           f"Faktor {f}: Luftspalt bleibt {spalt:.2f} mm (vorher {spalt0:.2f})")
    pruefe(abs(g["shaftD"] / BASIS["geom"]["shaftD"] - f) < 1e-6
           and abs(g["magWidth"] / BASIS["geom"]["magWidth"] - f) < 1e-3,
           f"Faktor {f}: Welle und Magnetkoerper skalieren mit")
massen = [o["gesamt_kg"] for o in erg["achsen"]["durchmesser"]["optionen"] if o["ok"]]
pruefe(all(a < b for a, b in zip(massen, massen[1:])),
       f"die Masse waechst monoton mit dem Durchmesser ({massen})")


print("\n7. Laenge wirkt linear")
opt_l = [o for o in erg["achsen"]["laenge"]["optionen"] if o["ok"]]
paare = list(zip(opt_l, opt_l[1:]))
verh = [(b["gesamt_kg"] / a["gesamt_kg"]) / (b["wert"] / a["wert"]) for a, b in paare]
pruefe(all(0.80 < v < 1.05 for v in verh),
       f"Masse ~ proportional zur Laenge (Verhaeltnisse {[round(v, 3) for v in verh]})")
kt_l = [o["Kt_Nm_per_A"] for o in opt_l]
pruefe(all(a < b for a, b in zip(kt_l, kt_l[1:])),
       f"Kt waechst mit der Laenge ({kt_l})")


print("\n8. Paare: Richtung und Bilanz stimmen")
d = erg["achsen"]["durchmesser"]
p0 = d["paare"][0]
pruefe(set(p0["spricht_fuer_a"]) & set(p0["spricht_fuer_b"]) == set(),
       "keine Kennzahl spricht fuer beide Seiten")
kl = [m for m, (_l, _e, r, z) in PV.METRIKEN.items() if r == "klein" and z]
for m in kl:
    dd = p0["deltas"].get(m)
    if dd and not dd["gleich"]:
        richtig = (dd["fuer"] == "a") == (dd["a"] < dd["b"])
        pruefe(richtig, f"'{PV.METRIKEN[m][0]}' (klein ist besser): "
                        f"{dd['a']} vs {dd['b']} -> spricht fuer "
                        f"{'links' if dd['fuer'] == 'a' else 'rechts'}")
        break
gr = [m for m, (_l, _e, r, z) in PV.METRIKEN.items() if r == "gross" and z]
for m in gr:
    dd = p0["deltas"].get(m)
    if dd and not dd["gleich"]:
        richtig = (dd["fuer"] == "a") == (dd["a"] > dd["b"])
        pruefe(richtig, f"'{PV.METRIKEN[m][0]}' (gross ist besser): "
                        f"{dd['a']} vs {dd['b']} -> spricht fuer "
                        f"{'links' if dd['fuer'] == 'a' else 'rechts'}")
        break
pruefe(all(int(p["bilanz"].split(":")[0]) == len(p["spricht_fuer_a"])
           and int(p["bilanz"].split(":")[1]) == len(p["spricht_fuer_b"])
           for a in erg["achsen"].values() for p in a["paare"]),
       "die Bilanz zaehlt genau die genannten Kennzahlen")
abgeleitet = [m for m, (_l, _e, _r, z) in PV.METRIKEN.items() if not z]
pruefe(all(m not in p["spricht_fuer_a"] and m not in p["spricht_fuer_b"]
           for a in erg["achsen"].values() for p in a["paare"] for m in abgeleitet),
       f"abgeleitete Kennzahlen zaehlen nicht mit ({abgeleitet})")


print("\n9. Rangfolge — welche Entscheidung zuerst")
pruefe(erg["rangfolge"]["Kt_Nm_per_A"][0][0] in ("magnetwerkstoff", "anordnung"),
       f"Kt wird am staerksten von {erg['rangfolge']['Kt_Nm_per_A'][0][0]} bewegt")
pruefe(erg["rangfolge"]["T_dauer_Nm"][0][0] == "kuehlung",
       f"das Dauermoment von {erg['rangfolge']['T_dauer_Nm'][0][0]}")
pruefe(erg["rangfolge"]["kosten_EUR"][0][0] in ("durchmesser", "laenge"),
       f"die Kosten von {erg['rangfolge']['kosten_EUR'][0][0]}")


print("\n10. Bedienfehler fallen durch, statt still etwas anderes zu tun")
try:
    PV.vergleiche(BASIS, achsen=["gibtesnicht"])
    pruefe(False, "unbekannte Achse haette abgewiesen werden muessen")
except ValueError as e:
    pruefe("gibtesnicht" in str(e) and "Bekannt" in str(e),
           "unbekannte Achse wird mit Vorschlagsliste abgewiesen")
try:
    PV.vergleiche({"rotor_lam": "m270_35a"})
    pruefe(False, "Payload ohne geom haette abgewiesen werden muessen")
except ValueError as e:
    pruefe("geom" in str(e), "Payload ohne geom wird abgewiesen")


print("\n11. Der gemeinsame Betriebspunkt ist wirklich gemeinsam")
e2 = PV.vergleiche(BASIS, achsen=["kuehlung"], last_nm=80.0, rpm=3000.0)
pruefe(e2["last_nm"] == 80.0 and e2["rpm_betriebspunkt"] == 3000.0,
       "Last und Drehzahl werden uebernommen und mitgemeldet")
v_gross = PV.vergleiche(BASIS, achsen=["kuehlung"], last_nm=200.0)
p_klein = [o["P_verlust_W"] for o in e2["achsen"]["kuehlung"]["optionen"] if o["ok"]]
p_gross = [o["P_verlust_W"] for o in v_gross["achsen"]["kuehlung"]["optionen"] if o["ok"]]
pruefe(all(a < b for a, b in zip(p_klein, p_gross)),
       "mehr Last ergibt bei jeder Kuehlart mehr Verlust")


print("\n12. Textausgabe")
t = PV.als_text(erg, max_paare=2)
pruefe("WAS BEWEGT WAS" in t and "Paare" in t, "Kopf und Paarliste stehen im Text")
pruefe("kein Feldlauf" in t, "die Scope-Grenze steht im Text")
pruefe(all(a["titel"] in t for a in erg["achsen"].values()), "jede Achse ist ueberschrieben")

print("\n" + "=" * 60)
print(f"{_n_ok} bestanden, {_n_bad} fehlgeschlagen")
sys.exit(1 if _n_bad else 0)
