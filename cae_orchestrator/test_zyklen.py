"""Fahrzyklus-Wahl und Sicherheitskriterien — ohne Server, ohne FreeCAD.

Der Anlass steht in beiden Modulkoepfen: ein Fahrrad-Nabenmotor wurde ueber WLTP
und 220 km/h Autobahn gerechnet, weil der Payload den Fahrzyklus gar nicht kannte
und ``--set cycle=off`` deshalb abgewiesen wurde. Diese Tests halten die drei
Stellen fest, an denen das wieder passieren koennte.
"""

import io
import json
import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cae_cli
import ema_db
import ema_drivecycle
import ema_sicherheit
import ema_zyklen

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


print("1. Der frische Payload kennt den Lastfall — und waehlt ihn NICHT selbst")
pl = cae_cli.frischer_payload()
pruefe(pl.get("cycle") == "off",
       "ohne Wahl wird kein Fahrzyklus gerechnet (cycle=off), statt still auf wltp3 "
       "zu fallen")
pruefe("vehicle" in pl and pl["vehicle"]["mass_kg"] == ema_drivecycle.DEFAULT_VEHICLE["mass_kg"],
       "das Fahrzeug steht sichtbar im Payload — vorher war es unerreichbar")
cae_cli._SCHEMA_CACHE = {"p": {"key": "p", "kind": "num", "in_geom": True,
                               "lo": 1, "hi": 40, "def": 4, "int": True}}
_, fehler = cae_cli.apply_sets(dict(pl), ["cycle=stadtland", "vehicle.mass_kg=140"],
                               url="<ungenutzt>")
pruefe(not fehler, f"und beides ist mit --set erreichbar ({fehler})")

print("\n2. Eigene Zyklen: bauen, ablegen, wiederfinden")
_tmp = tempfile.mkdtemp(prefix="zyklen_")
conn = ema_db.oeffne(os.path.join(_tmp, "t.db"))
csv = ema_zyklen.aus_phasen(ema_zyklen.phasen_lesen("0:5,25:20,25:300,0:15"))
zeilen = csv.splitlines()
z = ema_drivecycle.load_csv_cycle(csv)
pruefe(zeilen[0].startswith("t_s") and len(zeilen) == 342 and z["duration"] == 340,
       f"aus Phasen wird ein 1-Hz-CSV: 5+20+300+15 = {z['duration']:.0f} s, "
       f"{len(zeilen)-1} Punkte (Startpunkt zaehlt mit)")
pruefe(abs(float(max(z["v_kmh"])) - 25.0) < 1e-6,
       "die Pipeline liest es zurueck und trifft die Zielgeschwindigkeit")
ema_zyklen.speichern(conn, "rad", csv, "Radweg",
                     {"mass_kg": 140, "r_wheel_m": 0.35, "gear_ratio": 1.0})
namen = [x["name"] for x in ema_zyklen.liste(conn)]
pruefe("rad" in namen and "wltp3" in namen,
       "die Liste zeigt Eingebautes UND Eigenes")
p2 = {}
ema_zyklen.anwenden(p2, "rad", conn)
pruefe(p2["cycle"] == "csv" and p2["vehicle"]["gear_ratio"] == 1.0 and p2["cycle_csv"],
       "anwenden setzt Zyklus UND Fahrzeug — ein eigener Zyklus am Pkw-Modell "
       "ergaebe wieder die Momente eines Autos")
p3 = {}
ema_zyklen.anwenden(p3, "stadtland", conn)
pruefe(p3["cycle"] == "stadtland" and "cycle_csv" not in p3,
       "ein eingebauter Zyklus geht als Name durch, nicht als CSV")
try:
    ema_zyklen.speichern(conn, "wltp3", csv)
    doppelt = False
except ValueError:
    doppelt = True
pruefe(doppelt, "ein eingebauter Name laesst sich nicht ueberschreiben")
try:
    ema_zyklen.fahrzeug(masse=140)
    unbekannt = False
except ValueError:
    unbekannt = True
pruefe(unbekannt, "eine erfundene Fahrzeuggroesse wird abgewiesen, nicht geschluckt")
pruefe(ema_zyklen.loeschen(conn, "rad") and not ema_zyklen.holen(conn, "rad"),
       "loeschen entfernt ihn wieder")
conn.close()
shutil.rmtree(_tmp, ignore_errors=True)

print("\n3. Der Lastfall steht VOR dem Lauf da")
z1 = cae_cli._lastfall_zeile({"cycle": "wltp3", "vehicle": ema_drivecycle.DEFAULT_VEHICLE})
pruefe("Autobahn-Volllast" in z1,
       "dass wltp3 die Autobahnfahrt nach sich zieht, steht dabei")
z2 = cae_cli._lastfall_zeile({"cycle": "off"})
pruefe("kein Fahrzyklus" in z2, "off sagt, dass keiner gerechnet wird")
z3 = cae_cli._lastfall_zeile({})
pruefe("KEIN Zyklus im Payload" in z3 and "1600" in z3,
       "und ein Payload ohne Zyklus sagt, was die Pipeline dann selbst nimmt")

print("\n4. Werte aus Dateien — sonst passt ein eigener Zyklus nicht auf die Zeile")
_f = tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8")
_f.write(csv); _f.close()
pruefe(cae_cli._parse_value("@" + _f.name).splitlines()[0].startswith("t_s"),
       "--set cycle_csv=@datei liest den Wert aus der Datei")
os.unlink(_f.name)

print("\n5. Sicherheitskriterien")
befund = ema_sicherheit.pruefen(
    {"summary": {"safety_factor_fem": 2.0, "max_safe_rpm": 6000,
                 "T_winding_C": 90, "T_magnet_C": 70},
     "em_advanced": {"demag": {"risk": False, "margin_T": 0.4}}},
    {"payload": {"rpm_to": 6000, "magnet": "ndfeb_n35", "cycle": "off",
                 "vehicle": {"mass_kg": 140}}})
pruefe(befund["ok"], f"eine saubere Auslegung besteht ({befund['n_verletzt']} verletzt)")

heiss = ema_sicherheit.pruefen(
    {"summary": {"safety_factor_fem": 2.0, "max_safe_rpm": 6000,
                 "T_winding_C": 45, "T_magnet_C": 46},
     "drivecycle": {"cycle_name": "WLTP", "thermal":
                    {"avg": {"T_winding": 207, "T_magnet": 210},
                     "peak": {"T_winding": 216, "T_magnet": 210}}}},
    {"payload": {"rpm_to": 6000, "magnet": "ndfeb_n35", "cycle": "wltp3"}})
namen = {k["name"]: k for k in heiss["kriterien"]}
pruefe(not namen["magnet_dauer"]["ok"] and "210" in namen["magnet_dauer"]["text"],
       "die Temperaturen aus dem ZYKLUS zaehlen mit — am Auslegungspunkt waren es 46 °C")
pruefe("80 °C" in namen["magnet_dauer"]["text"],
       "die Magnetgrenze kommt aus der Werkstofftabelle (N35: 80 °C), nicht aus 150")
kalt = ema_sicherheit.pruefen(
    {"summary": {"safety_factor_fem": 2.0, "T_magnet_C": 118}},
    {"payload": {"magnet": "ferrite"}})
pruefe([k for k in kalt["kriterien"] if k["name"] == "magnet_dauer"][0]["ok"],
       "und fuer Ferrit (250 °C) sind 118 °C in Ordnung — eine feste Zahl waere hier falsch")

ohne_fem = ema_sicherheit.pruefen(
    {"summary": {"safety_factor_fem": None, "structural_basis": "analytisch"}}, {})
f = [k for k in ohne_fem["kriterien"] if k["name"] == "festigkeit"][0]
pruefe(not f["ok"] and f["schwere"] == "hinweis",
       "eine fehlende FEM ist ein eigener Befund — null heisst nicht 'sicher'")

ohne_zyklus = ema_sicherheit.pruefen({"summary": {}}, {"payload": {"rpm_to": 500}})
fp = [k for k in ohne_zyklus["kriterien"] if k["name"] == "fahrprofil"][0]
pruefe(not fp["ok"] and "1600" in fp["text"],
       "ein Payload ohne Fahrprofil wird beanstandet — genau der Fahrrad-Fall")

print("\n6. Bericht und Werkzeug faellen EIN Urteil")
import ema_report
row = {"safety_factor_fem": 2.0, "T_magnet_C": 118, "T_winding_C": 150,
       "magnet": "NdFeB N35"}
pruefe(ema_report._variant_verdict(row) == ema_sicherheit.beurteile(row),
       "_variant_verdict reicht an ema_sicherheit durch")
pruefe(not ema_report._variant_verdict(row)["empfohlen"],
       "118 °C auf N35 sind NICHT empfehlenswert — die alte 150-°C-Schranke liess "
       "das durch, waehrend das Laufprotokoll daneben vor Entmagnetisierung warnte")

print("\n7. Aufgabenzerlegung — der Schritt VOR der Recherche")
_pflicht = {p["name"] for p in cae_cli.PFLICHTPUNKTE}
pruefe({"lastfall", "betriebspunkt", "bauraum", "stromrichter"} <= _pflicht,
       f"die Pflichtliste nennt Lastfall, Betriebspunkt, Bauraum und Stromrichter "
       f"({len(_pflicht)} Punkte)")
_fest = [p for p in cae_cli.PFLICHTPUNKTE if p["quelle"] == "fest"]
pruefe(any("800" in p["hinweis"] for p in _fest),
       "und sagt, dass 800 V / 800 A fest verdrahtet sind — fuer ein 48-V-System falsch "
       "und NICHT einstellbar")
pruefe(all(p["quelle"] != "aufgabe" or "erfragt" in p["hinweis"] or
           "nicht ableitbar" in p["hinweis"] or "Bauraum" in p["frage"] or
           "Schemagrenzen" in p["hinweis"]
           for p in cae_cli.PFLICHTPUNKTE),
       "was nur der Auftraggeber weiss, ist als solches gekennzeichnet")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
