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


def METRIKEN_ZAEHLT(name):
    return PV.METRIKEN[name][3]


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
opt_k = {o["wert"]: o for o in erg["achsen"]["kuehlung"]["optionen"] if o["ok"]}
reihe = ["natural", "forced", "water", "oil"]
# Geprueft wird das KUEHLBARE Moment: das ist es, was die Kuehlung ordnet.
th = {k: opt_k[k]["T_dauer_therm_Nm"] for k in reihe}
pruefe(all(th[a] < th[b] for a, b in zip(reihe, reihe[1:])),
       f"kuehlbar: natural < forced < water < oil ({[th[k] for k in reihe]})")

# Und die zweite Grenze, die es bis hierher gar nicht gab: der Umrichter. Wo er
# bindet, aendert die Kuehlung NICHTS -- und genau das muss dastehen, statt
# vier verschiedene Dauermomente vorzuspiegeln, die keines davon liefern kann.
td = {k: opt_k[k]["T_dauer_Nm"] for k in reihe}
bind = {k: opt_k[k]["dauer_begrenzt_durch"] for k in reihe}
pruefe(all(td[k] <= th[k] + 1e-9 for k in reihe),
       "das gemeldete Dauermoment ist nie groesser als das kuehlbare")
gebunden = [k for k in reihe if bind[k] == "Umrichter"]
pruefe(gebunden,
       f"an dieser Geometrie bindet der Umrichter bei {', '.join(gebunden)} — "
       f"vorher stand hier ein Moment, fuer das das 6,8-fache des zulaessigen "
       f"Stroms noetig gewesen waere")
pruefe(len({round(td[k], 3) for k in gebunden}) == 1,
       f"und wo er bindet, ist die Kuehlung wirkungslos: alle {len(gebunden)} "
       f"liefern {td[gebunden[0]]:.1f} Nm")
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
# ``maschinenart`` steht jetzt mit vorn und meist ganz vorn: zwischen PSM,
# ASM, SynRM und EESM liegt beim Kt ein Faktor drei, zwischen N35 und N50 rund
# ein Fuenftel. Das ist kein aufgeweichter Test, sondern die Bestaetigung
# dessen, was ema_maschinenart behauptet -- die Wahl der Bauart ist die erste
# Entscheidung, weil sie die groesste ist.
pruefe(erg["rangfolge"]["Kt_Nm_per_A"][0][0] in ("maschinenart", "magnetwerkstoff",
                                                 "anordnung"),
       f"Kt wird am staerksten von {erg['rangfolge']['Kt_Nm_per_A'][0][0]} bewegt")
# Sobald der Umrichter bindet, ordnet nicht mehr die Kuehlung das Dauermoment,
# sondern das, was Kt bewegt — und das ist die Maschinenart. Die Rangfolge sagt
# damit die Wahrheit ueber DIESE Maschine, nicht eine allgemeine Regel.
pruefe(erg["rangfolge"]["T_dauer_Nm"][0][0] in ("kuehlung", "maschinenart"),
       f"das Dauermoment von {erg['rangfolge']['T_dauer_Nm'][0][0]}")
# Auch bei den Kosten steht die Maschinenart inzwischen mit vorn: Magnete gegen
# keine Magnete sind gemessen 149 gegen 76 EUR (96 %), waehrend +-20 % im
# Durchmesser rund 79 % ausmachen. Dazu kommt, dass das Nut-Tor die kleinste
# Durchmesser-Variante ausschliesst — sechs Hairpins passen in die flachere Nut
# nicht mehr, und genau das soll es sagen.
pruefe(erg["rangfolge"]["kosten_EUR"][0][0] in ("maschinenart", "durchmesser",
                                                "laenge"),
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

print("\n13. Verschraubung, Barrieren und Wellenverbindung")
from ema_rotorcheck import zusatzteile_check

# Die Verbindung ist die einzige Achse, die T_verbind_Nm bewegt.
tv = {o["wert"]: o["T_verbind_Nm"] for o in erg["achsen"]["wellenverbindung"]["optionen"]
      if o["ok"]}
pruefe(len(set(tv.values())) == 3,
       f"jede Wellenverbindung traegt ein eigenes Moment ({tv})")
pruefe(tv["spline"] > tv["press"] and tv["polygon"] > tv["press"],
       "Formschluss (Keilwelle, Polygon) traegt mehr als der Reibschluss")
for achse in ("anordnung", "hairpins", "kuehlung", "magnetwerkstoff"):
    sp = erg["achsen"][achse]["spannweite"].get("T_verbind_Nm")
    if sp is not None:
        pruefe(sp["spanne_pct"] < 0.5,
               f"{achse} bewegt das Wellenmoment nicht ({sp['spanne_pct']} %)")
        break

# Verschraubung und Barrieren nehmen Eisen weg -- sonst waere die Achse wirkungslos.
mv = [o["gesamt_kg"] for o in erg["achsen"]["verschraubung"]["optionen"] if o["ok"]]
pruefe(all(a >= b for a, b in zip(mv, mv[1:])) and mv[0] > mv[-1],
       f"groessere Schrauben nehmen mehr Eisen weg ({mv})")
mb = {o["wert"]: o["gesamt_kg"] for o in erg["achsen"]["flussbarrieren"]["optionen"]
      if o["ok"]}
pruefe(mb["aus"] > mb["q"] and mb["q"] > mb["qd"],
       f"mehr Barrieren = weniger Eisen ({mb})")
pruefe(erg["achsen"]["flussbarrieren"]["spannweite"]["Kt_Nm_per_A"]["spanne_pct"] < 0.5,
       "Barrieren bewegen Kt auf dieser Stufe NICHT — das kann erst der Feldlauf")

# Der neue Durchbruch-Check.
g_frei = dict(BASIS["geom"], genFluxBarrierQ=True, fluxBarrierWidth=2.0,
              fluxBarrierDepth=6.0)
g_durch = dict(BASIS["geom"], genFluxBarrierD=True, fluxBarrierWidth=8.0,
               fluxBarrierDepth=60.0)
pruefe(zusatzteile_check(dict(BASIS["geom"]))["aktiv"] is False,
       "ohne Barrieren und Schrauben meldet der Check 'nicht aktiv'")
z_frei, z_durch = zusatzteile_check(g_frei), zusatzteile_check(g_durch)
pruefe(z_frei["ok"], f"flache q-Barrieren gehen durch ({z_frei['min_abstand_mm']} mm)")
pruefe(not z_durch["ok"] and z_durch["min_abstand_mm"] < 0,
       f"tiefe, breite d-Barrieren schneiden die Tasche "
       f"({z_durch['min_abstand_mm']} mm)")
pruefe(len(z_durch["befunde"]) < 4 and "gleichartig" in " ".join(z_durch["befunde"]),
       f"drehsymmetrische Wiederholungen werden zusammengefasst "
       f"({len(z_durch['befunde'])} Zeilen)")

# Und: der Befund bleibt eine WARNUNG, das Tor verweigert deswegen nicht.
tor = rotor_layout_check(g_durch)
pruefe(any("Magnettasche" in w for w in tor["warnings"]),
       "das Layouttor traegt den Befund als Warnung")
pruefe(tor["ok"] == rotor_layout_check(dict(BASIS["geom"]))["ok"],
       "und aendert sein Urteil dadurch NICHT — Zusatzteile schliessen nicht aus")

# In der Paarbilanz muss der Durchbruch zaehlen.
e_fb = PV.vergleiche(dict(BASIS, geom=dict(BASIS["geom"], fluxBarrierWidth=8.0,
                                           fluxBarrierDepth=60.0)),
                     achsen=["flussbarrieren"])
paare = e_fb["achsen"]["flussbarrieren"]["paare"]
mit_zusatz = [p for p in paare if "_zusatz" in p["spricht_fuer_a"] + p["spricht_fuer_b"]]
pruefe(mit_zusatz, f"'Platz im Blech' taucht in {len(mit_zusatz)} von {len(paare)} Paaren auf")
t_fb = PV.als_text(e_fb)
pruefe("⚠" in t_fb and "Platz im Blech" in t_fb,
       "Warnung und Bilanzgrund stehen im Text")


print("\n14. Die Geometrie der Zusatzteile steht an EINER Stelle")
from ema_topology import balance_bolt_holes, flux_barrier_slots
g = dict(BASIS["geom"], genBalanceBolts=True, balanceBoltThread="M8", p=4)
loecher = balance_bolt_holes(g)
pruefe(len(loecher) == 8, f"Lochzahl = Polzahl ({len(loecher)})")
pruefe(abs(loecher[0]["r"] - (8.0 + 0.4) / 2) < 1e-9,
       "Lochradius = Gewindenennmass + 0,4 mm Spiel")
r_soll = g["shaftD"] / 2 + (g["rotorOD"] / 2 - g["shaftD"] / 2) * 0.5
pruefe(abs(loecher[0]["pitch_r"] - r_soll) < 1e-6,
       f"ohne Angabe sitzt der Lochkreis auf halber Strecke ({loecher[0]['pitch_r']:.2f} mm)")
pruefe(all(abs(math.hypot(h["x"], h["y"]) - r_soll) < 1e-6 for h in loecher),
       "alle Loecher liegen auf demselben Kreis")
sl = flux_barrier_slots(dict(BASIS["geom"], genFluxBarrierQ=True, genFluxBarrierD=True, p=4))
pruefe(len(sl) == 16 and {x["family"] for x in sl} == {"q", "d"},
       f"q und d ergeben je Pol einen Schlitz ({len(sl)})")
pruefe(abs(sl[0]["r_out"] - (BASIS["geom"]["rotorOD"] / 2 - 2.0)) < 1e-9,
       "der Aussensteg von 2 mm bleibt stehen")
pruefe(flux_barrier_slots(BASIS["geom"]) == [] and balance_bolt_holes(BASIS["geom"]) == [],
       "abgeschaltet liefern beide nichts")


print("\n15. Reluktanzmoment: die Anordnungen unterscheiden sich wirklich")
import ema_referenz as REF
from ema_topology import _BUILDERS

# (a) Das recherchierte Band greift und ordnet die Formen -- vorher lieferte
#     estimate_saliency fuer v/u/vv/delta/spoke bei gleicher Magnetdicke denselben
#     Wert, weil sie nur Luftspalt und Magnetdicke las.
xi = {k: ema_analysis.estimate_saliency(dict(BASIS["geom"], magShape=k))
      for k in _BUILDERS if k != "custom"}
pruefe(len(set(round(xi[k], 3) for k in ("bar", "v", "u", "vv", "delta", "pmasynrm"))) == 6,
       f"jede Innenlaeufer-Form bekommt ein eigenes xi ({ {k: xi[k] for k in ('bar','v','u','vv','delta','pmasynrm')} })")
pruefe(xi["bar"] < xi["v"] < xi["u"] < xi["vv"] < xi["pmasynrm"],
       "die Reihenfolge folgt der Recherche: Balken < V < U < Doppel-V < PMa-SynRM")
pruefe(xi["spm"] < 1.1 and xi["halbach"] < 1.1,
       f"Oberflaechenmagnete bleiben ohne Salienz ({xi['spm']:.2f})")
for code, (lo, hi, _st, _b) in REF.SALIENZ_BAND.items():
    pruefe(lo - 1e-9 <= xi[code] <= hi + 1e-9,
           f"{code}: xi {xi[code]:.2f} liegt im recherchierten Band {lo}–{hi}")

# (b) Die Geometrie bewegt den Wert INNERHALB seines Bandes weiter -- das Band
#     ersetzt die Rechnung nicht, es verortet sie.
duenn = ema_analysis.estimate_saliency(dict(BASIS["geom"], magShape="v", magThick=3))
dick = ema_analysis.estimate_saliency(dict(BASIS["geom"], magShape="v", magThick=12))
pruefe(duenn < xi["v"] < dick,
       f"dickere Magnete heben xi innerhalb des Bandes ({duenn:.2f} < {xi['v']:.2f} < {dick:.2f})")

# (c) Der Strom ist die Kennzahl, in der sich das zeigt -- und er zaehlt.
erg15 = PV.vergleiche(BASIS, achsen=["anordnung"])
opt = {o["wert"]: o for o in erg15["achsen"]["anordnung"]["optionen"] if o.get("ok")}
pruefe(METRIKEN_ZAEHLT("I_s_A"), "I_s_A zaehlt in der Bilanz mit")
pruefe(not METRIKEN_ZAEHLT("xi_LqLd") and not METRIKEN_ZAEHLT("T_rel_pct"),
       "xi und Reluktanzanteil sind Einordnung, keine Bilanzposten")
frei = [o for o in opt.values() if not o.get("strom_limit")]
pruefe(len(frei) >= 4, f"{len(frei)} Optionen bleiben unter dem Umrichter-Limit")
pruefe(opt["pmasynrm"]["I_s_A"] < opt["v"]["I_s_A"],
       f"PMa-SynRM braucht weniger Strom als V ({opt['pmasynrm']['I_s_A']} vs {opt['v']['I_s_A']} A) "
       f"-- OBWOHL sein Kt kleiner ist ({opt['pmasynrm']['Kt_Nm_per_A']} vs {opt['v']['Kt_Nm_per_A']})")
pruefe(opt["vv"]["I_s_A"] < opt["v"]["I_s_A"],
       f"Doppel-V braucht weniger Strom als einfaches V ({opt['vv']['I_s_A']} vs {opt['v']['I_s_A']} A)")
spanne = erg15["achsen"]["anordnung"]["spannweite"]
pruefe(spanne["I_s_A"]["spanne_pct"] > 20,
       f"die Anordnung bewegt den Strom deutlich ({spanne['I_s_A']['spanne_pct']:.0f} %)")

# (d) Am Limit ist I_s KEIN Messwert -- das muss dastehen, sonst liest man 800 A
#     als Ergebnis statt als Anschlag.
txt15 = PV.als_text(erg15, paare=False)
if any(o.get("strom_limit") for o in opt.values()):
    pruefe("Umrichter-Limit" in txt15, "gedeckelte Optionen sind im Text als solche markiert")
else:
    pruefe(True, "keine Option laeuft ins Limit (nichts zu markieren)")


print("\n16. V-Oeffnungswinkel und Wellendurchmesser als eigene Achsen")
erg16 = PV.vergleiche(BASIS, achsen=["v_oeffnung", "wellendurchmesser"])
vo = [o for o in erg16["achsen"]["v_oeffnung"]["optionen"] if o.get("ok")]
pruefe(len(vo) >= 4, f"{len(vo)} Oeffnungswinkel sind baubar")
kt_v = [o["Kt_Nm_per_A"] for o in vo]
pruefe(kt_v == sorted(kt_v),
       f"Kt waechst mit dem Oeffnungswinkel ({kt_v}) — die eine Haelfte des Zielkonflikts")
pruefe(any(str(REF.V_OEFFNUNG_GRAD["kompromiss"]).startswith(str(int(o["wert"]))) or
           abs(o["wert"] - REF.V_OEFFNUNG_GRAD["kompromiss"]) < 1e-6 for o in vo),
       f"der recherchierte Kompromiss {REF.V_OEFFNUNG_GRAD['kompromiss']:.0f}° steht in der Reihe")
pruefe("Literatur-Kompromiss" in PV.als_text(erg16, paare=False),
       "und ist als solcher beschriftet, nicht als Sollwert")

# Die Achse ist bei Formen ohne magAngle bedeutungslos -- und sagt das, statt
# stumm "bewegt NICHT" zu melden (das waere ein Befund, den es nicht gibt).
erg_bar = PV.vergleiche(dict(BASIS, geom=dict(BASIS["geom"], magShape="bar")),
                        achsen=["v_oeffnung"])
pruefe("ohne Bedeutung" in erg_bar["achsen"]["v_oeffnung"]["hinweis"],
       "bei einer Balkenform meldet die Achse ihre Bedeutungslosigkeit")
pruefe(not PV.vergleiche(BASIS, achsen=["v_oeffnung"])["achsen"]["v_oeffnung"]["hinweis"],
       "bei einer V-Form nicht")

wd = [o for o in erg16["achsen"]["wellendurchmesser"]["optionen"] if o.get("ok")]
pruefe(len(wd) == len(PV.WELLEN_FAKTOREN), f"alle {len(wd)} Wellendurchmesser sind baubar")
pruefe([o["T_verbind_Nm"] for o in wd] == sorted(o["T_verbind_Nm"] for o in wd),
       f"die dickere Welle traegt mehr ({[o['T_verbind_Nm'] for o in wd]})")
g_gross = dict(BASIS["geom"])
PV._setz_welle({"geom": g_gross}, BASIS["geom"]["shaftD"] * 1.3)
pruefe(abs(g_gross["rotorOD"] - BASIS["geom"]["rotorOD"]) < 1e-9
       and abs(g_gross["statorOD"] - BASIS["geom"]["statorOD"]) < 1e-9,
       "Rotor und Stator bleiben dabei stehen — das ist der Unterschied zur Durchmesser-Achse")


print("\n17. Recherchierte Werte bleiben von den gerechneten getrennt")
pruefe(all(m["quelle"] in REF.QUELLEN for m in REF.MESSPUNKTE),
       f"jeder der {len(REF.MESSPUNKTE)} Messpunkte nennt eine hinterlegte Quelle")
pruefe(all(m["zitat"].strip() for m in REF.MESSPUNKTE),
       "und jeder eine Fundstelle im Originaltext")
pruefe(all(q["url"].startswith("https://") for q in REF.QUELLEN.values()),
       "jede Quelle ist mit Adresse nachschlagbar")
pruefe(all(any(REF.messpunkt(x) for x in st)
           for _lo, _hi, st, _b in REF.SALIENZ_BAND.values()),
       "jedes abgeleitete Band nennt die Messpunkte, auf denen es ruht")
kopf = REF.als_text()[:400]
pruefe("nicht gerechnet" in kopf and "Fremdtext" in kopf.upper() or "FREMDTEXT" in kopf.upper(),
       "die Ausgabe traegt die Herkunftsmarke")
# Kein Tor: ein Entwurf ausserhalb der Vorbilder wird gemeldet, aber nicht abgelehnt.
weit = dict(BASIS["geom"], shaftD=BASIS["geom"]["rotorOD"] * 0.85)
pruefe(REF.bauband_pruefen(weit), "eine ueberdicke Welle faellt als 'ausserhalb' auf")
pruefe(PV._bewerte(dict(BASIS, geom=weit), 12000.0, 5000.0, 120.0).get("ok") in (True, False),
       "und wird trotzdem bewertet statt abgelehnt — das Band ist kein Tor")


print("\n" + "=" * 60)
print(f"{_n_ok} bestanden, {_n_bad} fehlgeschlagen")
sys.exit(1 if _n_bad else 0)
