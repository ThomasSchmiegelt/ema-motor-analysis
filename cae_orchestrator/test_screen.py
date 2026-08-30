"""Tests fuer die Vorauswahl (`ema_screen`) und den Stadt/Land-Zyklus.

Der Schwerpunkt liegt auf der EINPASSUNG. Sie ist der Teil, an dem die Vorauswahl
steht und faellt: eine Vorauswahl, die 80 % ihrer Varianten am Taschenlayout
aussortiert, hat nichts vorausgewaehlt, sondern nur sich selbst. Die Tests halten
darum vor allem drei Zusagen fest:

1. **Kein Fehlurteil.** Was die Einpassung als brauchbar meldet, muss das echte Tor
   ``rotor_layout_check`` bestaetigen. Waehrend der Entwicklung war das dreimal
   verletzt (Vorfilter zu klein, ``magWidth``-Rueckschreib ohne Nachpruefung,
   Nachbarpole statt aller Pole) -- jedes Mal sah das Ergebnis besser aus, als es war.
2. **Ausbeute.** Alle Bauformen muessen bei mehreren Polzahlen erreichbar sein.
3. **Nachvollziehbarkeit.** Jede Verkleinerung steht im Protokoll.
"""

import math
import os
import sys

import ema_drivecycle as DC
import ema_screen as S
from ema_rotorcheck import rotor_layout_check
from ema_topology import BRIDGE_MM

BASIS_GEOM = {
    "p": 3, "slots": 36, "conductorsPerSlot": 6,
    "rotorOD": 188.6, "shaftD": 60.0, "shaftBoreD": 0.0,
    "statorID": 190.0, "statorOD": 260.0, "axialLen": 80.0, "slotDepth": 22.0,
    "magShape": "vasym", "magThick": 6.0, "magWidth": 32.0, "magDist": 13.5,
    "magAngle": 110.0, "magAngle2": 90.0, "magAsym": 0.0, "magDepthRel": 0.6,
    "magTangLen": 0.0, "magLayerGap": 8.0, "magLayers": 3, "magGapMm": 0.1,
    "nAx": 1, "nCirc": 1, "segPerPole": 6,
}
BASIS = {"geom": dict(BASIS_GEOM), "rotor_lam": "m270_35a", "stator_lam": "m270_35a",
         "hairpin_mat": "cu_etp", "magnet": "n42", "axial_len": 80.0,
         "target": {"n_max": 12000.0}}

_n_ok = _n_bad = 0


def pruefe(bedingung, text):
    global _n_ok, _n_bad
    if bedingung:
        _n_ok += 1
        print(f"  ✓ {text}")
    else:
        _n_bad += 1
        print(f"  ✗ {text}")


# ── 1. Einpassung stimmt mit dem Tor ueberein ────────────────────────────────

print("1. Einpassung vs. Tor -- kein Fehlurteil")
formen = [k for k in S.ACHSEN_VORGABE["magShape"]]
fehl = []
for shape in formen:
    for p in (2, 3, 4, 5):
        g = dict(BASIS_GEOM); g["magShape"] = shape
        pas = S.einpassen(g, p)
        tor = rotor_layout_check(pas["geom"])
        if pas["ok"] != tor["ok"]:
            fehl.append((shape, p, pas["ok"], tor["ok"], (tor["fatal"] or [""])[0][:60]))
pruefe(not fehl, f"32 Kombinationen: Einpassung und Tor einig ({fehl[:2]})")

print("\n2. Ausbeute -- jede Bauform bei mehreren Polzahlen erreichbar")
je_form = {}
for shape in formen:
    je_form[shape] = sum(1 for p in (2, 3, 4, 5)
                         if S.einpassen(dict(BASIS_GEOM, magShape=shape), p)["ok"])
for shape, n in sorted(je_form.items()):
    pruefe(n >= 2, f"{shape:9s} bei {n}/4 Polzahlen baubar")

print("\n3. Was eingepasst wurde, steht im Protokoll")
p_alt = BASIS_GEOM["p"]
pas = S.einpassen(dict(BASIS_GEOM, magShape="pmasynrm"), 2)
pruefe(set(pas) >= {"s_koerper", "s_lage", "magDepthRel", "steg_im_pol",
                    "steg_zw_polen", "grund", "ok", "geom"},
       "Protokoll fuehrt Massstaebe, Sitz und beide Stege")
pruefe(0 < pas["s_koerper"] <= 1.0, f"Koerpermassstab im Bereich (0,1]: {pas['s_koerper']}")
pruefe(pas["s_lage"] > 0, f"Anordnungsmassstab positiv: {pas['s_lage']}")

print("\n4. Der Koerper wird nie vergroessert, nur verkleinert")
zu_gross = []
for shape in formen:
    for p in (2, 3, 4, 5):
        r = S.einpassen(dict(BASIS_GEOM, magShape=shape), p)
        if r["s_koerper"] > 1.0 + 1e-9:
            zu_gross.append((shape, p, r["s_koerper"]))
pruefe(not zu_gross, f"kein Magnet ueber Ausgangsgroesse hinaus vergroessert ({zu_gross[:2]})")

print("\n5. Die Anordnung folgt der Polteilung")
r2 = S.einpassen(dict(BASIS_GEOM, magShape="bar"), 2)
r5 = S.einpassen(dict(BASIS_GEOM, magShape="bar"), 5)
pruefe(r2["s_lage"] > r5["s_lage"],
       f"weniger Pole = weiter (p=2 {r2['s_lage']} > p=5 {r5['s_lage']})")
pruefe(abs(S.einpassen(dict(BASIS_GEOM), p_alt)["s_lage"] - 1.0) < 0.51,
       "bei unveraenderter Polzahl bleibt die Anordnung nahe 1,0")

print("\n6. Die zurueckgegebene Geometrie ist die GEMESSENE")
abw = []
for shape in formen:
    r = S.einpassen(dict(BASIS_GEOM, magShape=shape), 4)
    if not r["ok"]:
        continue
    m = S._masse(r["geom"])
    if (abs(m["steg_im_pol"] - r["steg_im_pol"]) > 1e-3
            or abs(m["steg_zw_polen"] - r["steg_zw_polen"]) > 1e-3):
        abw.append((shape, r["steg_im_pol"], m["steg_im_pol"]))
pruefe(not abw, f"Protokollwerte == Nachmessung an der Rueckgabe ({abw[:2]})")

print("\n7. Stege halten die Mindestdicke")
duenn = []
for shape in formen:
    for p in (2, 3, 4, 5):
        r = S.einpassen(dict(BASIS_GEOM, magShape=shape), p)
        if r["ok"] and min(r["steg_im_pol"], r["steg_zw_polen"]) < BRIDGE_MM - 1e-6:
            duenn.append((shape, p, r["steg_im_pol"], r["steg_zw_polen"]))
pruefe(not duenn, f"kein brauchbares Ergebnis unter {BRIDGE_MM} mm ({duenn[:2]})")

# ── 2. Wicklung ──────────────────────────────────────────────────────────────

print("\n8. Wicklungskriterium")
pruefe(S.wicklung_moeglich(48, 8), "48 Nuten / 8 Pole ist symmetrisch")
pruefe(S.wicklung_moeglich(36, 6), "36/6 ist symmetrisch")
pruefe(not S.wicklung_moeglich(24, 6), "24/6 ist es nicht (24/ggT=4, nicht durch 3)")
pruefe(not S.wicklung_moeglich(40, 8), "40 Nuten sind nicht durch 3 teilbar")
pruefe(not S.wicklung_moeglich(0, 8) and not S.wicklung_moeglich(36, 0),
       "Nullwerte fallen durch statt zu teilen")

# ── 3. Zielerkennung ─────────────────────────────────────────────────────────

print("\n9. Ziel aus dem Auslegungsauftrag")
z = S.ziel_aus_text("Ein guenstiger Antrieb, magnetarm und wirtschaftlich")
pruefe(z["ziel"] == "guenstig" and z["belege_guenstig"], f"kostenorientiert erkannt: {z['belege_guenstig'][:3]}")
z = S.ziel_aus_text("Sportlicher Antrieb mit maximaler Spitzenleistung, hochdrehend")
pruefe(z["ziel"] == "leistung" and z["belege_leistung"], f"leistungsorientiert erkannt: {z['belege_leistung'][:3]}")
z = S.ziel_aus_text("Ein Elektromotor fuer ein Fahrzeug")
pruefe(z["ziel"] == "ausgewogen" and not z["sicher"],
       "ohne Belegwoerter ausgewogen UND als unsicher gekennzeichnet")
z = S.ziel_aus_text("guenstig und leistungsstark zugleich")
pruefe(z["ziel"] == "ausgewogen" and not z["sicher"],
       "Gleichstand faellt auf ausgewogen zurueck und gilt als unsicher")
pruefe(S.ziel_aus_text("")["ziel"] == "ausgewogen", "leerer Text bricht nicht")

# ── 4. Bewertung und Rangliste ───────────────────────────────────────────────

print("\n10. Bewertung einer Variante")
b = S.bewerte(BASIS, 12000.0)
pruefe(b["ok"], f"der Ausgangsentwurf selbst ist brauchbar ({b.get('grund')})")
for k in ("B_gap_T", "Kt_Nm_per_A", "safety_factor", "magnet_kg", "kosten_EUR"):
    pruefe(isinstance(b.get(k), (int, float)), f"Kennwert {k} vorhanden: {b.get(k)}")
schlecht = {**BASIS, "geom": dict(BASIS_GEOM, slots=40)}
pruefe(not S.bewerte(schlecht, 12000.0)["ok"], "40 Nuten fallen an der Wicklung durch")

print("\n11. Gewichte")
for ziel, g in S.GEWICHTE.items():
    pruefe(abs(sum(g.values()) - 1.0) < 1e-9, f"Gewichte {ziel} summieren auf 1,0")
pruefe(S.GEWICHTE["guenstig"]["kosten"] > S.GEWICHTE["leistung"]["kosten"],
       "guenstig gewichtet Kosten hoeher als leistung")
pruefe(S.GEWICHTE["leistung"]["kt"] > S.GEWICHTE["guenstig"]["kt"],
       "leistung gewichtet die Momentkonstante hoeher")

print("\n12. Vorauswahl als Ganzes")
achsen = {"p": [2, 4], "slots": [36, 48], "magShape": ["v", "bar", "spoke", "u"],
          "conductorsPerSlot": [6]}
erg = S.screene(BASIS, "ausgewogen", achsen=achsen)
pruefe(erg["geprueft"] == 16, f"16 Kombinationen geprueft ({erg['geprueft']})")
pruefe(erg["brauchbar"] > 0, f"{erg['brauchbar']} brauchbar")
pruefe(len(erg["rangliste"]) == erg["brauchbar"], "Rangliste enthaelt genau die brauchbaren")
punkte = [z["punkte"] for z in erg["rangliste"]]
pruefe(punkte == sorted(punkte, reverse=True), "absteigend nach Punkten sortiert")
pruefe(all("teilnoten" in z for z in erg["rangliste"]), "jede Zeile traegt ihre Teilnoten")
nach = [rotor_layout_check(dict(BASIS_GEOM, magShape=z["magShape"], p=z["p"]))
        for z in erg["rangliste"][:0]]
pruefe(erg["ziel"] == "ausgewogen" and erg["gewichte"] == S.GEWICHTE["ausgewogen"],
       "Ziel und Gewichte werden mitgegeben")
try:
    S.screene(BASIS, "schnell")
    pruefe(False, "unbekanntes Ziel muss abgewiesen werden")
except ValueError:
    pruefe(True, "unbekanntes Ziel wird abgewiesen")
try:
    S.screene(BASIS, "ausgewogen", grenze=4)
    pruefe(False, "Kombinationsgrenze muss greifen")
except ValueError:
    pruefe(True, "Kombinationsgrenze greift statt stundenlang zu rechnen")

print("\n13. Verschiedene Ziele ordnen verschieden")
a = S.screene(BASIS, "guenstig", achsen=achsen)["rangliste"]
b2 = S.screene(BASIS, "leistung", achsen=achsen)["rangliste"]
if a and b2:
    pruefe(a[0]["punkte"] != b2[0]["punkte"] or a[0]["magShape"] != b2[0]["magShape"],
           "guenstig und leistung liefern nicht dieselbe Spitze")
else:
    pruefe(False, "beide Ziele muessen brauchbare Varianten finden")

print("\n14. Textausgabe")
txt = S.bestenliste_text(erg, 5)
pruefe("Ziel:" in txt and "brauchbar" in txt, "Kopfzeile mit Ziel und Ausbeute")
pruefe(all(k in txt for k in ("kt", "kosten", "rundlauf")), "Gewichte stehen im Text")

# ── 4b. Nachbaubarkeit — der Fund aus dem Agentenlauf ────────────────────────

print("\n16. Jede Empfehlung ist mit ihren eigenen --set-Werten nachbaubar")
# Das ist die wichtigste Zusage dieses Moduls, und sie war verletzt. Ein echter
# Agentenlauf nahm die Empfehlung (p=5, V-Anordnung), pruefte sie mit
# `rotor-check --set p=5 --set magShape=v` nach, bekam "Kollision, Ueberlappung
# 6,20 mm" -- und meldete dem Nutzer, die eigene Empfehlung sei unbaubar. Sie war
# baubar, nur mit verkleinertem Magneten; die dafuer noetigen Masse standen nirgends.
achsen_nb = {"p": [2, 3, 4, 5], "slots": [24, 36], "conductorsPerSlot": [4],
             "magShape": ["v", "u", "spoke", "vv", "pmasynrm", "delta", "vasym", "bar"]}
erg_nb = S.screene(BASIS, "ausgewogen", achsen=achsen_nb)
pruefe(erg_nb["brauchbar"] > 0, f"{erg_nb['brauchbar']} Empfehlungen zu pruefen")
pruefe(bool(erg_nb.get("basis_geom")), "die Basisgeometrie liegt dem Ergebnis bei")

nicht_nachbaubar = []
for r in erg_nb["rangliste"]:
    sets = S.uebernahme(r, erg_nb["basis_geom"])
    g = dict(BASIS_GEOM)
    for zuweisung in sets:
        schluessel, wert = zuweisung.split("=", 1)
        g[schluessel] = float(wert) if "." in wert else (
            wert if not wert.lstrip("-").isdigit() else int(wert))
    if not rotor_layout_check(g)["ok"]:
        nicht_nachbaubar.append((r["magShape"], r["p"], sets))
pruefe(not nicht_nachbaubar,
       f"alle {len(erg_nb['rangliste'])} bestehen das echte Tor ({nicht_nachbaubar[:2]})")

geschrumpft = [r for r in erg_nb["rangliste"] if r.get("s_koerper", 1) < 0.999]
pruefe(geschrumpft, f"{len(geschrumpft)} Zeilen mussten den Magneten verkleinern")
fehlend = [r["magShape"] for r in geschrumpft
           if not any(s.startswith(("magWidth=", "magThick=", "magDist="))
                      for s in S.uebernahme(r, erg_nb["basis_geom"]))]
pruefe(not fehlend,
       f"jede verkleinerte Zeile gibt die geaenderten Magnetmasse mit ({fehlend[:3]})")

txt_nb = S.bestenliste_text(erg_nb, 8)
pruefe("Mag" in txt_nb.split("\n")[3],
       "der Magnetmassstab steht als Spalte in der Rangliste")
pruefe("Uebernahme" in txt_nb and "--set magShape=" in txt_nb,
       "der Uebernahmebefehl steht unter der Tabelle")
if geschrumpft:
    pruefe("VERKLEINERTEM Magneten" in txt_nb,
           "eine Verkleinerung wird im Klartext benannt, nicht nur als Zahl")

print("\n17. Ohne Aenderung keine ueberfluessigen --set")
r_gleich = S.bewerte(BASIS, 12000.0)
r_gleich.update({"geom": {}, "s_koerper": 1.0})
sets_gleich = S.uebernahme(r_gleich, BASIS_GEOM)
pruefe(all(s.split("=")[0] in ("p", "slots", "magShape", "conductorsPerSlot")
           for s in sets_gleich),
       f"unveraenderte Geometrie erzeugt keine Geometrie-Zuweisungen: {sets_gleich}")

# ── 4c. Der geplante Versuch (Selbstlernmodus) ───────────────────────────────

print("\n18. Systematischer Versuch ueber alle Bauformen und Polzahlen")
achsen_v = {"p": [2, 3, 5], "slots": [36, 48], "conductorsPerSlot": [4],
            "magShape": ["v", "u", "spoke", "bar"]}
bef = S.durchprobieren(BASIS, achsen=achsen_v)
pruefe(bef["geprueft"] == 24, f"24 Kombinationen abgefahren ({bef['geprueft']})")
pruefe(set(bef["karte"]) == {"v", "u", "spoke", "bar"},
       f"jede Bauform kartiert: {sorted(bef['karte'])}")
for form, k in bef["karte"].items():
    alle_p = sorted(k["volle_groesse"] + [x[0] for x in k["nur_verkleinert"]]
                    + k["gar_nicht"])
    pruefe(alle_p == [2, 3, 5],
           f"{form}: jede Polzahl genau einmal eingeordnet ({alle_p})")

pruefe(bef["unbewegt"]["Kt_Nm_per_A"]["slots"] is True,
       "gemessen: Kt haengt auf dieser Stufe nicht von der Nutzahl ab")
pruefe(any("u" in g and "v" in g for g in bef["ununterscheidbar"]),
       f"gemessen: V und U sind analytisch ununterscheidbar ({bef['ununterscheidbar']})")
pruefe(all(S.wicklung_moeglich(sl, po) for sl, po in bef["wicklungspaare"]),
       "die gemeldeten Wicklungspaare erfuellen das Kriterium wirklich")

# Die Kartierung muss mit dem echten Tor uebereinstimmen — sonst lernt der Speicher
# etwas Falsches, und das ist schlimmer als nichts zu lernen.
falsch = []
for form, k in bef["karte"].items():
    for pp in k["volle_groesse"]:
        r = S.einpassen(dict(BASIS_GEOM, magShape=form), pp)
        if not (r["ok"] and r["s_koerper"] > 0.999 and rotor_layout_check(r["geom"])["ok"]):
            falsch.append((form, pp, "als voll gemeldet"))
    for pp in k["gar_nicht"]:
        if S.einpassen(dict(BASIS_GEOM, magShape=form), pp)["ok"]:
            falsch.append((form, pp, "als unbaubar gemeldet, ist aber baubar"))
pruefe(not falsch, f"die Karte stimmt mit dem echten Tor ueberein ({falsch[:2]})")

txt_v = S.versuch_text(bef)
for stueck in ("volle Magnetgroesse", "NICHT unterscheiden",
               "Drehstromwicklung", "ANALYTISCHEN Stufe"):
    pruefe(stueck in txt_v, f"Befundtext nennt '{stueck}'")

print("\n19. Der Lernspeicher nimmt nur Belegtes auf")
import tempfile

import ema_lernen as L

# In eine WEGWERFDATEI schreiben. Der erste Anlauf dieses Tests hing am echten
# Speicher unter ~/cae_projekte/_lernen/ und hat dort Testsaetze hinterlassen -- ein
# Test, der die Daten des Nutzers veraendert, ist selbst ein Fehler.
_echt = L.ERFAHRUNGEN
L.ERFAHRUNGEN = os.path.join(tempfile.mkdtemp(), "erfahrungen.jsonl")
saetze = []
for regel, beleg in [
        ("Bauform 'v' ist bei p=2,3 in voller Groesse baubar.",
         "Geplanter Versuch ueber 24 Kombinationen, Layouttor auf jeder einzelnen."),
        ("zu kurz", "Beleg mit 123 Zahlen drin und lang genug"),
        ("Eine ausreichend lange und nachvollziehbare Regelaussage.", "ohne Zahl")]:
    try:
        L.merke(regel, beleg, quelle="test", conn=None)
        saetze.append("angenommen")
    except L.OhneBeleg:
        saetze.append("abgewiesen")
    except Exception:                                        # noqa: BLE001
        saetze.append("fehler")
pruefe(saetze[0] == "angenommen", "belegte Regel wird angenommen")
pruefe(saetze[1] == "abgewiesen", "zu kurze Regel wird abgewiesen")
pruefe(saetze[2] == "abgewiesen", "Beleg ohne Zahl wird abgewiesen")
pruefe(os.path.isfile(L.ERFAHRUNGEN) and L.ERFAHRUNGEN != _echt,
       "geschrieben wurde in die Wegwerfdatei, nicht in den echten Speicher")
L.ERFAHRUNGEN = _echt

# ── 5. Stadt/Land-Zyklus ─────────────────────────────────────────────────────

print("\n15. Stadt/Land-Zyklus")
z = DC.stadtland_cycle()
t = list(z["t"]); v = [x / 3.6 for x in z["v_kmh"]]
pruefe(len(t) == len(v) > 100, f"{len(t)} Stuetzstellen")
pruefe(all(t[i] < t[i + 1] for i in range(len(t) - 1)), "Zeit ist streng monoton")
pruefe(min(v) >= -1e-9, "keine negative Geschwindigkeit")
dauer = t[-1] - t[0]
pruefe(1000 < dauer < 1800, f"Dauer {dauer:.0f} s liegt zwischen WLTP-Kurzform und Vollzyklus")
v_max = max(v) * 3.6
pruefe(80 < v_max < 110, f"Spitze {v_max:.1f} km/h -- Landstrasse, nicht Autobahn")
weg_km = sum((v[i] + v[i + 1]) / 2 * (t[i + 1] - t[i]) for i in range(len(t) - 1)) / 1000
pruefe(10 < weg_km < 30, f"Weglaenge {weg_km:.2f} km")
steh = sum(1 for x in v if x < 0.1) / len(v)
pruefe(0.05 < steh < 0.30, f"Standanteil {steh:.0%} -- Stadtanteil vorhanden")
pruefe(z.get("name") and len(z.get("phases", [])) >= 3,
       f"benannt ({z.get('name')}) und in {len(z.get('phases', []))} Abschnitte gegliedert")
pruefe(abs(z["duration"] - dauer) < 2, f"gemeldete Dauer {z['duration']} s passt zur Zeitreihe")

print("\n" + "=" * 60)
print(f"{_n_ok} bestanden, {_n_bad} fehlgeschlagen")
sys.exit(1 if _n_bad else 0)
