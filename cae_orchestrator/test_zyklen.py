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

import numpy as np

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
# Bis zum 06.09.2026 stand hier, die 800 V/800 A seien FEST verdrahtet -- der Test
# hielt einen Mangel fest, statt eine Eigenschaft. Jetzt sind sie einstellbar, und
# der Hinweis muss sagen WIE, samt der Windungszahl, ohne die eine Klemmenspannung
# in dieser Rechnung nicht darstellbar ist.
_strom = next(p for p in cae_cli.PFLICHTPUNKTE if p["name"] == "stromrichter")
pruefe(_strom["quelle"] == "schema" and "inverterVdc" in _strom["hinweis"]
       and "inverterImax" in _strom["hinweis"],
       "der Stromrichter ist einstellbar, und der Hinweis nennt die beiden Schluessel")
pruefe("Windung" in _strom["hinweis"] and "turnsPerSlot" in _strom["hinweis"],
       "und sagt dazu, dass die Windungszahl der Umrechnungsschluessel ist — ohne sie "
       "heisst '24 V' in dieser Rechnung nichts")
pruefe(all(p["quelle"] != "aufgabe" or "erfragt" in p["hinweis"] or
           "nicht ableitbar" in p["hinweis"] or "Bauraum" in p["frage"] or
           "Schemagrenzen" in p["hinweis"]
           for p in cae_cli.PFLICHTPUNKTE),
       "was nur der Auftraggeber weiss, ist als solches gekennzeichnet")


print("\n8. Das Lastspiel — ein Lastfall fuer alles, was dreht ohne zu fahren")
# Der Fall, aus dem das entstanden ist: ein Roboterarm-Antrieb. Der Agent erkannte
# richtig, dass kein abgelegter Zyklus passt, und baute sich einen -- konnte das aber
# nur in km/h. Um "2200 1/min" zu schreiben, erfand er Rad 0,12 m und Uebersetzung 4,
# und der Lauf meldete fuer ein Gelenk 14,2 km bei 345 kWh/100 km.
import ema_drivecycle
import ema_zyklen

_csv_ls = ema_zyklen.aus_lastspiel(
    ema_zyklen.lastspiel_lesen("0:0:5,2200:6:4,2200:6:20,0:-3:4,0:0:12"))
pruefe(_csv_ls.splitlines()[0] == "t_s,rpm,T_Nm",
       "aus_lastspiel schreibt Zeit, Drehzahl und Moment — keine Geschwindigkeit")
pruefe(ema_zyklen.art_von(_csv_ls) == "lastspiel"
       and ema_zyklen.art_von("t_s,v_kmh\n0,0\n1,5\n2,10\n3,15\n4,20") == "fahrt",
       "die Art steht in den Punkten selbst (3 Spalten / 2 Spalten), nicht in einer "
       "zweiten Quelle, die abweichen koennte")

_z = ema_drivecycle.load_csv_cycle(_csv_ls)
pruefe(_z["art"] == "lastspiel" and abs(_z["rpm"].max() - 2200) < 1e-6
       and abs(_z["T_Nm"].min() + 3.0) < 1e-6,
       "load_csv_cycle liest Drehzahl und Moment zurueck, negatives Moment (Bremsen) "
       "bleibt erhalten")

_drv = ema_drivecycle.compute_drivetrain(_z, {})
pruefe(_drv["art"] == "lastspiel"
       and abs(_drv["rpm_motor"].max() - 2200) < 1e-6
       and float(np.abs(_drv["v_ms"]).max()) == 0.0,
       "compute_drivetrain reicht die Welle DURCH — ohne Fahrzeug, ohne Rad, ohne "
       "Geschwindigkeit (das Fahrzeugmodell wird gar nicht erst angefasst)")

_n = len(_drv["t"])
_verluste = {"P_Cu": np.full(_n, 30.0), "P_Fe_stator": np.full(_n, 5.0),
             "P_Fe_rotor": np.zeros(_n), "P_Mag_eddy": np.zeros(_n),
             "P_Bearing": np.zeros(_n), "T_rated": 3.0}
_e = ema_drivecycle.cycle_energy(_drv, _verluste, {})
pruefe(_e["distance_km"] is None and _e["E_per_100km_Wh"] is None
       and _e["v_max_kmh"] is None,
       "Weg, Verbrauch je 100 km und v_max sind None — NICHT 0: eine 0 liest sich "
       "wie ein Messwert, und genau daraus wurde '14,2 km' fuer ein Gelenk")
pruefe(_e["T_rms"] > 0 and _e["rpm_max"] == 2200 and _e["overload_warning"],
       f"was ein Lastspiel WIRKLICH beantwortet, steht da: T_eff {_e['T_rms']} Nm "
       f"gegen {_e['T_rated_Nm']} Nm Dauermoment, samt Ueberlastwarnung")

_conn = ema_db.oeffne()
try:
    ema_zyklen.speichern(_conn, "_pruef_lastspiel", _csv_ls, fahrzeug_dict={"mass_kg": 15})
    pruefe(False, "ein Lastspiel MIT Fahrzeug muss abgewiesen werden")
except ValueError as _e2:
    pruefe("kein Fahrzeug" in str(_e2),
           "ein Lastspiel mit Fahrzeug wird abgewiesen — Drehzahl und Moment stehen "
           "schon in den Punkten, ein Fahrzeug daneben koennte ihnen widersprechen")
ema_zyklen.speichern(_conn, "_pruef_lastspiel", _csv_ls)
_p = ema_zyklen.anwenden({"vehicle": {"mass_kg": 1600}}, "_pruef_lastspiel", _conn)
pruefe(_p["cycle"] == "lastspiel" and "vehicle" not in _p,
       "anwenden ENTFERNT ein geerbtes Fahrzeug — sonst stuende neben der "
       "Wellenvorgabe ein 1600-kg-Pkw")
_liste = {z["name"]: z for z in ema_zyklen.liste(_conn)}
pruefe(_liste["_pruef_lastspiel"]["art"] == "lastspiel"
       and "n_max_rpm" in _liste["_pruef_lastspiel"]
       and "weg_km" not in _liste["_pruef_lastspiel"],
       "die Liste zeigt ein Lastspiel mit n_max und T_eff statt mit v_max und Weg")
ema_zyklen.loeschen(_conn, "_pruef_lastspiel")

pruefe(all(e.get("art") == "fahrt" for k, e in ema_zyklen.EINGEBAUT.items() if k != "off"),
       "alle mitgelieferten Zyklen sind Fahrzyklen — deshalb muss die Frage nach der "
       "ART vor der Frage nach dem Namen kommen")
_lf = next(p for p in cae_cli.PFLICHTPUNKTE if p["name"] == "lastfall")
pruefe("Lastspiel" in _lf["frage"] and "Fahrzyklus" in _lf["frage"],
       "die Pflichtfrage lautet ZUERST 'faehrt sie oder dreht sie nur?' und erst "
       "dann 'welcher Zyklus?'")
pruefe(cae_cli._ist_lastspiel(_csv_ls) and not cae_cli._ist_lastspiel("t,v\n0,0\n1,5"),
       "die CLI erkennt ein Lastspiel am Kopf der Punkte, ohne NumPy zu laden")


print("\n9. Der Luftspalt im FDM-Netz ist der gezeichnete — oder er sagt es")
# Gemessen am 06.09.2026: der Rasterer oeffnete das Luftband IMMER auf 2,5 mm, indem
# er Rotorrandeisen wegnahm. Am 75-mm-Antrieb endete der Laeufer bei r=25,50 statt
# 27,30 mm und der Spalt war 2,50 statt 0,70 mm -- bei JEDER Aufloesung gleich.
import ema_analysis

pruefe(ema_analysis.AIRGAP_MIN_PX == 1.0 and not hasattr(ema_analysis, "AIRGAP_MIN_MM"),
       "die Mindestbreite steht in BILDPUNKTEN (1 px), nicht in Millimetern — ein "
       "Millimeterwert ist an eine Maschinengroesse gebunden, ein Netz nicht")

_g75 = dict(statorOD=75, statorID=56, rotorOD=54.6, shaftD=16, p=5, slots=24,
            magShape="bar", magWidth=10.9697, magThick=2.6625, magDist=4.8,
            magLayerGap=9.6, slotDepth=8, magDepthRel=0.55)
for _N in (300, 600):
    _d = ema_analysis.luftspalt_im_netz(_g75, _N)
    pruefe(not _d["air_gap_widened"] and _d["air_gap_effective_mm"] == 0.7,
           f"75-mm-Antrieb bei N={_N}: gerechnet wird der gezeichnete Spalt 0,700 mm "
           f"({_d['air_gap_px']:.1f} Bildpunkte)")

_mu, _J, _sc, _ctr = ema_analysis._rasterise(_g75, 600)[:4]
_ix = np.arange(600) - _ctr
_X, _Y = np.meshgrid(_ix, _ix)
_R = np.hypot(_X, _Y) / _sc
_eisen = _mu > 5
_r_rot = float(_R[_eisen & (_R < 27.65)].max())
pruefe(abs(_r_rot - 27.3) < 0.05,
       f"und das Rotoreisen endet im Raster bei r={_r_rot:.3f} mm, wo es gezeichnet "
       f"ist (27,300) — vorher bei 25,50, also 1,8 mm zu klein")

_grob = ema_analysis.luftspalt_im_netz(
    dict(statorOD=280, statorID=190, rotorOD=188.6, shaftD=60), 180)
pruefe(_grob["air_gap_widened"] and _grob["air_gap_effective_mm"] > 1.9,
       f"wo das Netz den Spalt wirklich nicht traegt (0,4 Bildpunkte), wird auf einen "
       f"Bildpunkt aufgeweitet ({_grob['air_gap_effective_mm']:.3f} mm) — und das "
       f"steht im Ergebnis, statt in einer Konstanten zu verschwinden")

import ema_grenzen
_z_lsp = [z for z in ema_grenzen.cad_gegen_feld(
              dict(statorOD=280, statorID=190, rotorOD=188.6, shaftD=60, p=3, slots=54,
                   axialLen=80, magShape="v", magWidth=24.72, magThick=6.0, magDist=8.0,
                   magLayerGap=16.0, slotDepth=25, conductorsPerSlot=4,
                   windingType="hairpin", fdm_resolution=180))["zeilen"]
          if "Luftspalt" in z["groesse"]][0]
pruefe(not _z_lsp["gleich"] and _z_lsp["feld"] > 1.9,
       "cad_gegen_feld fragt den RASTERER, nicht noch einmal dieselben zwei "
       "Durchmesser — sonst verglich die Probe den Spalt mit sich selbst und meldete "
       "'gleich', waehrend das Feld mit einem anderen rechnete")


print("\n10. Umrichterspannung und -strom sind einstellbar")
# Bis zum 06.09.2026 waren 800 V / 800 A Modulglobale. ``aufgabe`` sagte „FEST
# verdrahtet" an, gerechnet wurde trotzdem damit -- fuer einen 24-V-Roboterantrieb
# ist jede daraus abgeleitete Aussage die einer anderen Maschine.
import ema_analysis as _A
import ema_sicherheit as _S
import ema_text2ema as _T

_g75 = dict(statorOD=75, statorID=56, rotorOD=54.6, shaftD=16, p=5, slots=24,
            magShape="bar", magWidth=10.9697, magThick=2.6625, magDist=4.8,
            magLayerGap=9.6, slotDepth=8, magDepthRel=0.55, axialLen=60,
            conductorsPerSlot=2)

pruefe({"inverterVdc", "inverterImax"} <= set(_T.SCHEMA),
       "beide stehen im Schema und sind damit ueber --set erreichbar")
pruefe(all(_T.SCHEMA[k]["geom"] and not _T.SCHEMA[k].get("adv")
           for k in ("inverterVdc", "inverterImax")),
       "und zwar auf der GRUNDebene, nicht bei den Feinparametern — sie beschreiben "
       "die Quelle, an der die Maschine haengt")
pruefe("windungenProNut" not in _T.SCHEMA,
       "die Windungszahl bekommt KEINEN zweiten Schluessel: sie steht schon in "
       "turnsPerSlot, wo auch Strangwiderstand und Kupfermasse sie lesen")

_u0 = _A.umrichter(_g75)
pruefe(_u0["v_dc_V"] == 800.0 and _u0["i_max_A"] == 800.0 and _u0["n_wdg"] == 1
       and _u0["n_quelle"] == "bezugswicklung",
       "ohne Vorgabe bleibt alles wie bisher: 800 V / 800 A auf 1 Wdg/Nut — jede "
       "Altrechnung bleibt Ziffer fuer Ziffer dieselbe")
pruefe(_A.estimate_dq_currents(_g75, 2000, 6.0, b_gap_t=0.463, rpm_base=1500)
       == _A.estimate_dq_currents(dict(_g75, inverterVdc=800, inverterImax=800),
                                  2000, 6.0, b_gap_t=0.463, rpm_base=1500),
       "und die Vorgabe ausdruecklich hinzuschreiben aendert nichts")

_u = _A.umrichter(dict(_g75, inverterVdc=24, inverterImax=200,
                       umrichterBezug="wicklung"))
pruefe(_u["n_wdg"] == 2 and _u["n_quelle"] == "wicklung"
       and _u["v_dc_1t"] == 12.0 and _u["i_max_1t"] == 400.0,
       f"wer eine Klemmenspannung vorgibt, meint eine wirkliche Klemme: 24 V / 200 A "
       f"an {_u['n_wdg']} Wdg/Nut sind {_u['v_dc_1t']:.0f} V / {_u['i_max_1t']:.0f} A "
       f"auf die eine Windung, mit der Kt und psi rechnen")
pruefe(_u["v_dc_1t"] * _u["n_wdg"] == _u["v_dc_V"]
       and _u["i_max_1t"] / _u["n_wdg"] == _u["i_max_A"],
       "u ~ N und i ~ 1/N — bei fester Geometrie und festem Moment liegen die "
       "Amperewindungen fest, die Windungszahl tauscht nur Strom gegen Spannung")

_iq_klein, _ = _A.estimate_dq_currents(dict(_g75, inverterImax=50), 2000, 60.0,
                                       b_gap_t=0.463, rpm_base=1500)
pruefe(_iq_klein <= 50.0 * 2 + 1e-6,
       f"ein kleiner Umrichter deckelt wirklich: i_q {_iq_klein:.1f} A statt der "
       f"800-A-Vorgabe")

_p = _A.umrichter_passt(dict(_g75, inverterVdc=24, inverterImax=200,
                            umrichterBezug="wicklung"), 2500)
pruefe(_p["ok"] and 0.4 <= _p["spannungsausnutzung"] <= _p["reserve"],
       f"zwei Windungen passen zu 24 V: die Gegen-EMK belegt "
       f"{_p['spannungsausnutzung']*100:.0f} % der Klemmenspannung")
_p_viel = _A.umrichter_passt(dict(_g75, inverterVdc=24, turnsPerSlot=10,
                                 umrichterBezug="wicklung"), 2500)
pruefe(not _p_viel["ok"] and _p_viel["spannungsausnutzung"] > 1.0
       and _p_viel["n_soll"] == 2,
       f"zehn Windungen passen nicht — {_p_viel['spannungsausnutzung']*100:.0f} % der "
       f"Spannung, die Maschine erreicht die Drehzahl nicht; passend waeren "
       f"{_p_viel['n_soll']}")
_p_wenig = _A.umrichter_passt(dict(_g75, inverterVdc=400, turnsPerSlot=2,
                                  umrichterBezug="wicklung"), 2500)
pruefe(not _p_wenig["ok"] and _p_wenig["spannungsausnutzung"] < 0.4
       and _p_wenig["n_soll"] > 2,
       f"und zu WENIGE Windungen sind auch ein Befund: der Umrichter bleibt bei "
       f"{_p_wenig['spannungsausnutzung']*100:.0f} % ungenutzt, es fliesst unnoetig "
       f"Strom; passend waeren {_p_wenig['n_soll']}")

_krit = {k["name"]: k for k in _S.pruefen(
    {"summary": {}}, {"payload": dict(_g75, rpm_to=2500, inverterVdc=24,
                                      inverterImax=200, turnsPerSlot=10,
                                      umrichterBezug="wicklung")})["kriterien"]}
pruefe("umrichter" in _krit and not _krit["umrichter"]["ok"]
       and "turnsPerSlot=2" in _krit["umrichter"]["text"],
       "'sicherheit' beanstandet eine Wicklung, die nicht zum Umrichter passt, und "
       "nennt die Windungszahl, die passen wuerde")
_krit_falle = {k["name"]: k for k in _S.pruefen(
    {"summary": {}}, {"payload": dict(_g75, rpm_to=2500, inverterVdc=24)})["kriterien"]}
pruefe(not _krit_falle["umrichter"]["ok"]
       and "umrichterBezug=wicklung" in _krit_falle["umrichter"]["text"],
       "wer eine Klemmenspannung setzt und den Bezug vergisst, wird beanstandet — "
       "sonst gaelten die 24 V still fuer eine Einwindungswicklung")

_krit0 = {k["name"] for k in _S.pruefen(
    {"summary": {}}, {"payload": dict(_g75, rpm_to=2500)})["kriterien"]}
pruefe("umrichter" not in _krit0,
       "ohne vorgegebenen Umrichter wird nichts beanstandet — die 1 Wdg/Nut sind "
       "dort eine Bezugsgroesse und keine Wicklung, die passen muesste")


print("\n11. Rastmoment — die Groesse hinter 'sehr praezise'")
import ema_paarvergleich as _PV
import ema_rastmoment as _RM

_g75r = dict(_g75, axialLen=60)
_B = _A._analytical_Bgap(_g75r)

# (a) Was EXAKT ist: die Zaehlerei ueber Nut- und Polzahl.
_o = _RM.ordnung(_g75r)
pruefe(_o["n_c"] == 120 and abs(_o["periode_grad"] - 3.0) < 1e-9
       and abs(_o["rastfaktor"] - 2.0) < 1e-9,
       "24 Nuten und 10 Pole geben kgV 120: 120 Rastperioden je Umdrehung, alle 3,0 "
       "Grad, Rastfaktor 2,0 — reine Zaehlerei, kein Modell")

# (b) Die Schraegung ist ein Integral, keine Naeherung: eine ganze Nutteilung
#     loescht die Grundwelle EXAKT aus.
_nt = 360.0 / 24
pruefe(_RM.schraegungsfaktor(dict(_g75r, skew_deg=_nt))["faktor"] < 1e-9,
       f"eine Schraegung um genau eine Nutteilung ({_nt:.1f} Grad) loescht die "
       f"Grundwelle exakt aus — das ist das Integral ueber eine volle Periode")
pruefe(0.12 < _RM.schraegungsfaktor(dict(_g75r, skew_deg=_nt / 2))["faktor"] < 0.14,
       "eine halbe Nutteilung laesst noch rund 13 % stehen — dazwischen geht es "
       "nicht linear zu")
pruefe(_RM.schraegungsfaktor(dict(_g75r, skew_deg=_nt, skew_segments=3))["faktor"] < 1e-9,
       "und gestaffelt in 3 Stufen ueber dieselbe Weite ebenso (Zonenfaktor)")
pruefe(_RM.schraegungsfaktor(_g75r)["faktor"] == 1.0,
       "ohne Schraegung bleibt alles stehen")

# (c) Die TRENDS des geschaetzten Teils. Absolut ist es eine Schaetzung, aber die
#     Richtungen muessen stimmen, sonst taugt der Vergleich nichts.
def _t(gg, nb=None):
    return _RM.bewerte(gg, _A._analytical_Bgap(gg), 60.0, 6.0,
                       nut_breite_mm=nb)["T_rast_Nm"]
_basis = _t(_g75r)
pruefe(_t(_g75r, 1.0) < 0.4 * _basis and _t(_g75r, 0.5) < 0.2 * _basis,
       f"ein engerer Nutschlitz senkt das Rastmoment stark ({_basis:.3f} -> "
       f"{_t(_g75r, 1.0):.3f} -> {_t(_g75r, 0.5):.3f} Nm bei 4,03 / 1,0 / 0,5 mm) — "
       f"die alte Zeile in compute_performance kannte die Nutoeffnung gar nicht")
pruefe(_t(dict(_g75r, statorID=57.0)) < 0.5 * _basis,
       "ein weiterer Luftspalt glaettet — die Nutwelle klingt ueber ihn ab")
pruefe(_t(dict(_g75r, slots=27)) < 0.1 * _basis,
       "27 Nuten (kgV 270) rasten viel feiner als 24 (kgV 120)")
pruefe(_t(dict(_g75r, slots=30)) > 10.0 * _basis,
       "und 30 Nuten zu 10 Polen (kgV 30, ganzzahlige Lochzahl) sind die "
       "schlechteste Wahl — genau das sagt der Rastfaktor voraus")

# (d) Ohne Abklingen ueber den Luftspalt taugte das Modell nicht.
pruefe(_RM._abklingen(5, 0.00733, 0.00035) < 0.25
       and _RM._abklingen(10, 0.00651, 0.00035) < 0.05,
       "hohe Ordnungen kommen ueber den Spalt kaum an (Laplace) — ohne das lag eine "
       "27-Nut-Auslegung mit kgV 270 kaum besser als eine 24-Nut mit kgV 120, was "
       "der Erfahrung widerspricht")

# (e) Es steht als SCHAETZUNG da, und warum nicht gemessen wird.
_bw = _RM.bewerte(_g75r, _B, 60.0, 6.0)
pruefe(_bw["guete"] == "schaetzung", "die Guete steht im Ergebnis")
_txt = " ".join(_RM.als_text(_bw))
pruefe("GESCHAETZT" in _txt and "FDM" in _txt,
       "und der Text sagt beides: dass es geschaetzt ist, und dass der FDM es nicht "
       "kann (die gedrehte Rastergeometrie erzeugt ein groesseres Scheinmoment)")
pruefe(any("OFFEN" in h for h in _bw["hinweise"]),
       "die offene Nut wird benannt — dieses Werkzeug zeichnet keinen Nutverschluss, "
       "und das ist der staerkste einzelne Beitrag")

# (f) Im Paarvergleich: drei neue Achsen, und das Rastmoment als stehende Spalte.
for _a in ("schraegung", "spannung", "strom"):
    pruefe(_a in _PV.ACHSEN, f"Achse '{_a}' ist da")
pruefe("T_rast_pct" in _PV.METRIKEN and not _PV.METRIKEN["T_rast_pct"][3],
       "das Rastmoment ist eine Kennzahl, zaehlt aber NICHT in der Bilanz: wie "
       "wichtig Drehgenauigkeit ist, entscheidet der Einsatz und nicht das Werkzeug")
pruefe("T_rast_pct" in _PV.ZUSATZSPALTEN,
       "es wird trotzdem IMMER angezeigt — sonst stuende unter der Schraegungsachse "
       "'bewegt NICHT: alles', obwohl sie genau das bewegt, wofuer sie da ist")
pruefe(_PV.SCHRAEGUNG_ANTEILE[-1] == 1.0 and _PV.SCHRAEGUNG_ANTEILE[0] == 0.0,
       "die Schraegungsachse faehrt Anteile EINER Nutteilung, nicht runde Gradzahlen "
       "— zehn Grad sagen ohne die Nutzahl nichts")

# (g) Der Bezug der Umrichtergrenzen wird GESAGT, nicht aus dem Wert erraten.
_ei = _A.umrichter(dict(_g75, inverterImax=400))
_wi = _A.umrichter(dict(_g75, inverterImax=400, umrichterBezug="wicklung"))
pruefe(_ei["n_wdg"] == 1 and _wi["n_wdg"] == 2,
       "umrichterBezug entscheidet, nicht der Zahlenwert — der erste Entwurf schloss "
       "aus 'weicht von der Vorgabe ab' auf 'ist eine Klemme', und dann lieferten in "
       "der Stromachse 800 A weniger Moment als 400 A")

_kr = {k["name"]: k for k in _S.pruefen(
    {"summary": {"T_dauer_Nm": 6.0}},
    {"payload": dict(_g75r, rpm_to=2500, axial_len=60)})["kriterien"]}
pruefe("rastmoment" in _kr and "GESCHAETZT" in _kr["rastmoment"]["text"],
       "'sicherheit' fuehrt das Rastmoment mit — als Einordnung samt Stufe, nicht "
       "als Tor mit fester Schranke")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
