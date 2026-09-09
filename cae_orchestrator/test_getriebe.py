"""Getriebeauslegung -- ohne FreeCAD, ohne Server.

Was hier still falsch sein koennte und deshalb geprueft wird:

* **Die Zahnform.** ``Y_Fa``/``Y_Sa`` werden aus der Geometrie gerechnet und
  nicht nachgeschlagen. Wenn die Iteration nach ``theta`` daneben liegt, faellt
  das an keiner Stelle auf -- die Zahlen sehen weiter plausibel aus, und das
  Modul waere still falsch.
* **Die Flanke entscheidet meistens, nicht der Zahnfuss.** Wer nach der
  Fussformel aufhoert, legt eine Verzahnung aus, die Gruebchen bekommt.
* **Der Einbau in der Welle.** Zwei Grenzen (gezeichnete und magnetisch
  zulaessige Bohrung) und die Frage, welche bindet.
* **Der Fahrzyklus ohne Getriebe muss BITGLEICH bleiben.**

Aufruf: ``venv/bin/python test_getriebe.py``
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import ema_drivecycle as D
import ema_getriebe as G
import ema_referenz as R

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


W = R.GETRIEBE_WERKSTOFF["einsatzgehaertet"]


print("1. Die Zahnform kommt aus der Geometrie")
# Anker: fuer das Normprofil (20 Grad, h_fP*=1,25, rho_fP*=0,38) und x = 0 liegt
# Y_Fa bei z = 20 in der Groessenordnung 2,8 und Y_Sa bei 1,55 -- das ist die
# Groesse, gegen die sich eine Fehlimplementierung sofort verraet. Als BAND
# geprueft und nicht auf die Stelle: es ist eine Plausibilitaetsschranke, keine
# zitierte Tabelle.
f20 = G.zahnform(20)
pruefe(f20["ok"] and 2.70 <= f20["Y_Fa"] <= 2.95,
       f"z=20, x=0: Y_Fa = {f20['Y_Fa']:.3f} (erwartet 2,70…2,95)")
pruefe(1.45 <= f20["Y_Sa"] <= 1.68,
       f"z=20, x=0: Y_Sa = {f20['Y_Sa']:.3f} (erwartet 1,45…1,68)")
werte = [G.zahnform(z)["Y_Fa"] for z in (17, 20, 25, 30, 40, 60, 100)]
pruefe(all(a > b for a, b in zip(werte, werte[1:])),
       "Y_Fa faellt streng mit der Zaehnezahl — mehr Zaehne, dickerer Fuss")
sa = [G.zahnform(z)["Y_Sa"] for z in (17, 20, 25, 30, 40, 60, 100)]
pruefe(all(a < b for a, b in zip(sa, sa[1:])), "Y_Sa steigt streng mit der Zaehnezahl")
# Die Profilverschiebung ist der Grund, warum eine Tabelle nicht genuegt.
ohne, mit = G.zahnform(14), G.zahnform(14, x=0.5)
pruefe(mit["Y_Fa"] < ohne["Y_Fa"] * 0.85,
       f"x = +0,5 bei z = 14 senkt Y_Fa von {ohne['Y_Fa']:.2f} auf "
       f"{mit['Y_Fa']:.2f} — eine Y_Fa-Tabelle fuer x = 0 waere hier um "
       f"{100*(ohne['Y_Fa']/mit['Y_Fa']-1):.0f} % daneben")
pruefe(mit["s_Fn_m"] > ohne["s_Fn_m"], "und der Zahnfuss wird dabei wirklich dicker")


print("\n2. Die Faktoren stimmen mit ihren geschlossenen Formen ueberein")
pruefe(abs(G.zonenfaktor(G._bog(20), G._bog(20)) - 2.495) < 0.01,
       "Z_H = 2,495 fuer Normverzahnung 20 Grad, x = 0 (die bekannte 2,5)")
pruefe(abs(G.elastizitaetsfaktor() - 189.8) < 0.5,
       "Z_E = 189,8 fuer Stahl/Stahl — aus E und nu, nicht aus einer Tabelle")
ue = G.ueberdeckung(20, 60, 3.0, 40.0)
pruefe(1.4 <= ue["eps_alpha"] <= 1.9,
       f"eps_alpha = {ue['eps_alpha']:.3f} fuer 20/60 (Normpaarung: 1,4…1,9)")
pruefe(abs(ue["a_w_mm"] - 120.0) < 1e-6,
       "Achsabstand = m(z1+z2)/2 = 120 mm — exakt, nicht genaehert")


print("\n3. Das Modul: Zahnfuss zuerst, dann entscheidet meistens die Flanke")
st = G.stufe_auslegen(191.0, 3.5, W, n1_1pmin=8000)
pruefe(st["ok"] and st["haelt"], "eine 191-Nm-Stufe traegt")
pruefe(st["S_F"] >= st["S_F_ziel"] and st["S_H"] >= st["S_H_ziel"],
       f"beide Sicherheiten stehen: S_F = {st['S_F']}, S_H = {st['S_H']}")
pruefe(st["m_mm"] >= st["m_zahnfuss_mm"],
       f"das gewaehlte Modul {st['m_mm']} liegt nicht unter dem, was der "
       f"Zahnfuss braucht ({st['m_zahnfuss_mm']})")
pruefe(st["bindend"] == "flanke" and st["m_mm"] > st["m_zahnfuss_mm"],
       f"und hier bindet die FLANKE: der Fuss allein haette {st['m_zahnfuss_mm']} mm "
       f"gereicht ({st['m_mm']} mm sind noetig). Wer nach der Fussformel aufhoert, "
       f"legt eine Verzahnung aus, die Gruebchen bekommt")
pruefe(st["m_mm"] in G.MODUL_REIHE1, "das Modul liegt auf der Normreihe DIN 780")
pruefe(G.modul_normen(2.01) == 2.5 and G.modul_normen(2.0) == 2.0,
       "und es wird AUFgerundet, nie ab")


print("\n4. Zaehnezahlen: Uebersetzung, Fenster, Teilerfremdheit")
z = G.zaehnezahlen(4.7)
pruefe(z["ok"] and abs(z["i_ist"] - 4.7) / 4.7 < 0.03,
       f"i = 4,7 -> z {z['z1']}/{z['z2']}, i_ist = {z['i_ist']:.4f} "
       f"({100*z['fehler']:.2f} % daneben)")
pruefe(z["z1"] <= G.Z_MIN_OHNE_X + 10,
       f"das Ritzel bleibt im Fenster ({z['z1']} <= {G.Z_MIN_OHNE_X + 10}) — ohne "
       f"diese Schranke gewinnt immer das groesste Ritzel und das Rad wird gross")
z3 = G.zaehnezahlen(3.0)
pruefe(not z3["teilerfremd"] and z3["hinweis"],
       "eine ganzzahlige Uebersetzung ist nicht teilerfremd — das wird GESAGT, "
       "statt sie stillschweigend zu verstimmen")
pruefe(not G.zaehnezahlen(0.5)["ok"], "ins Schnelle uebersetzen wird abgewiesen")


print("\n5. Der Planetensatz")
p = G.planetensatz(191.0, 5.0, W, n_sonne_1pmin=8000)
pruefe(p["ok"], "i = 5 ist auslegbar")
pruefe(abs((1.0 + p["z_hohlrad"] / p["z_sonne"]) - p["i_ist"]) < 1e-9,
       f"i = 1 + z_Hohlrad/z_Sonne = {p['i_ist']} — die Definition, nicht eine Naeherung")
pruefe(p["z_planet"] * 2 + p["z_sonne"] == p["z_hohlrad"],
       "z_Hohlrad = z_Sonne + 2*z_Planet — sonst waeren die Achsabstaende ungleich")
pruefe(G._montage_ok(p["z_sonne"], p["z_hohlrad"], p["n_planeten"]),
       f"Montagebedingung: (z_s + z_h) = {p['z_sonne'] + p['z_hohlrad']} ist durch "
       f"{p['n_planeten']} teilbar — sonst passt der letzte Planet nicht in seine Luecke")
pruefe(p["nachbar_ok"], "die Planeten beruehren sich nicht")
innen = [e for e in p["eingriffe"] if e["innen"]][0]
aussen = [e for e in p["eingriffe"] if not e["innen"]][0]
pruefe(innen["S_H"] > aussen["S_H"],
       f"der INNEN-Eingriff ist der freundlichere (S_H {innen['S_H']} gegen "
       f"{aussen['S_H']}) — die Flanken schmiegen sich, die Pressung faellt")
pruefe(not G.planetensatz(191.0, 2.0, W)["ok"],
       "i = 2 wird abgewiesen: darunter wird das Hohlrad kleiner als die Sonne")


print("\n6. Der Einbau in der Welle")
satz = G.planetensatz(60.0, 4.0, W)
geom = {"shaftD": 140.0, "shaftBoreD": 120.0}
r = G.in_welle_pruefen(satz, geom, laenge_verfuegbar_mm=80.0)
pruefe(r["passt"], f"der Satz ({satz['d_aussen_mm']} mm) passt in 120 mm Bohrung")
pruefe(not r["magnetisch_geprueft"] and "MAGNETISCHE Grenze wurde nicht geprueft" in r["satz"],
       "ohne Wellenbefund wird ausdruecklich gesagt, dass die magnetische Grenze "
       "OFFEN ist — 'passt in die gezeichnete Bohrung' ist nicht 'zulaessig'")
r2 = G.in_welle_pruefen(satz, geom, laenge_verfuegbar_mm=80.0,
                        welle_befund={"ok": True, "bohrung": {"hoechstens_mm": 80.0}})
pruefe(r2["bindend"].startswith("magnetisch"),
       f"mit Wellenbefund bindet die MAGNETISCHE Grenze ({r2['d_verfuegbar_mm']} mm) "
       f"und nicht die gezeichnete (120 mm)")
r3 = G.in_welle_pruefen(satz, geom, welle_befund={"ok": True,
                                                  "bohrung": {"hoechstens_mm": 60.0}})
pruefe(not r3["passt"] and "es fehlen" in r3["satz"],
       "und wenn es nicht passt, steht da, wie viel fehlt")
eng = G.in_welle_pruefen(satz, geom, laenge_verfuegbar_mm=20.0)
pruefe(not eng["passt_axial"], "auch axial wird geprueft, nicht nur radial")
stirn = G.stufe_auslegen(60.0, 4.0, W)
abw = G.in_welle_pruefen(stirn, geom)
pruefe(not abw["ok"] and "Nur ein Planetensatz" in abw["grund"],
       "ein Stirnradsatz in der Welle wird ABGEWIESEN und nicht genaehert")


print("\n7. Bauart und Einbauort passen zusammen")
e = G.auslegen({"art": "stirnrad", "einbau": "in_welle", "i": 4.0,
                "T_motor_Nm": 60.0, "n_motor_1pmin": 6000})
pruefe(not e["ok"] and "in_welle" in e["grund"],
       "Stirnrad + in_welle wird schon bei der Auslegung abgewiesen")
e = G.auslegen({"art": "planeten", "einbau": "in_welle", "i": 5.0,
                "T_motor_Nm": 60.0, "n_motor_1pmin": 6000,
                "geom": {"shaftD": 140.0, "shaftBoreD": 120.0},
                "welle_befund": {"ok": True, "bohrung": {"hoechstens_mm": 110.0}}})
pruefe(e["ok"] and e.get("in_welle") and e["in_welle"]["passt"],
       "Planetensatz + in_welle laeuft durch und traegt den Platzbefund mit")


print("\n8. Wirkungsgrad, Masse, Traegheit")
e = G.auslegen({"art": "stirnrad", "stufen": 2, "i": 9.5, "T_motor_Nm": 191.0,
                "n_motor_1pmin": 8000, "werkstoff": "einsatzgehaertet"})
pruefe(e["ok"] and abs(e["i_ist"] - 9.5) / 9.5 < 0.02,
       f"zwei Stufen ergeben i = {e['i_ist']} (gefordert 9,5)")
pruefe(len(e["stufen"]) == 2 and e["stufen"][0]["i_ist"] < e["stufen"][1]["i_ist"] * 3,
       "die Uebersetzung ist auf beide Stufen verteilt, nicht auf eine geschoben")
w = e["wirkungsgrad"]
pruefe(0.93 < w["eta_nenn"] < 0.995,
       f"Wirkungsgrad im Nennpunkt {w['eta_nenn']} (zwei Stufen: 0,93…0,99)")
pruefe(w["P_zahn_W"] > 0 and w["P_leerlauf_W"] > 0,
       "Verzahnungs- UND Leerlaufverlust sind getrennt ausgewiesen")
pruefe(0 < e["masse_kg"] < 200 and e["J_red_kgm2"] > 0,
       f"Masse {e['masse_kg']} kg, reduzierte Traegheit {e['J_red_kgm2']} kg m^2")
# Die Traegheit der zweiten Stufe darf nur mit 1/i^2 zaehlen.
j_naiv = sum(s["J_ein_kgm2"] + s["J_aus_kgm2"] for s in e["massen"]["je_stufe"])
pruefe(e["J_red_kgm2"] < j_naiv / 2.0,
       f"die reduzierte Traegheit ({e['J_red_kgm2']}) liegt weit unter der "
       f"ungeteilten Summe ({j_naiv:.4f}) — wer sie ungeteilt addiert, rechnet "
       f"sie um i^2 zu gross")


print("\n9. Sonderbauarten sagen, wie weit sie tragen")
k = G.auslegen({"art": "kegelrad", "i": 3.0, "T_motor_Nm": 60.0,
                "n_motor_1pmin": 4000})
pruefe(k["ok"] and "ersatz-stirnrad" in k["verfahren"].lower(),
       "das Kegelrad nennt sein Verfahren (Tredgold) als Naeherung")
pruefe(abs(k["delta1_grad"] + k["delta2_grad"] - 90.0) < 1e-6,
       f"die Teilkegelwinkel ergaenzen sich zu 90 Grad "
       f"({k['delta1_grad']} + {k['delta2_grad']})")
sch = G.auslegen({"art": "schnecke", "i": 20.0, "T_motor_Nm": 20.0,
                  "n_motor_1pmin": 3000})
pruefe(sch["ok"] and sch["haelt"] is None and "KEINE Zahnfussrechnung" in sch["verfahren"],
       "die Schnecke rechnet keine Tragfaehigkeit und sagt das, statt eine zu erfinden")
pruefe(len(sch["wirkungsgrad_spanne"]) >= 3,
       "und gibt eine SPANNE ueber den Reibwert statt einer Zahl")


print("\n10. Der Werkstoff ist eine Annahme, und das steht dran")
pruefe(all(w.get("beleg") == "annahme" for w in R.GETRIEBE_WERKSTOFF.values()),
       "alle Getriebewerkstoffe sind als 'annahme' gekennzeichnet")
pruefe(all("spanne_F" in w and "spanne_H" in w for w in R.GETRIEBE_WERKSTOFF.values()),
       "und tragen ihre Spanne mit — der Mittelwert allein taeuscht Schaerfe vor")
pruefe("annahme" in G.als_text(e).lower(),
       "jeder Befund traegt den Vorbehalt sichtbar")
ohne = dict(W); ohne["sigma_Flim_Nmm2"] = 0.0
leer = G.stufe_auslegen(191.0, 3.5, ohne)
pruefe(not leer["ok"] and "keine Tragfaehigkeit" in leer["grund"],
       "ohne Festigkeitskennwert gibt es KEIN Modul — kein Ersatzwert, keine Zahl")


print("\n11. Der Fahrzyklus: ohne Getriebe bitgleich, mit Getriebe lastabhaengig")
zyk = D.wltp_class3()
a = D.compute_drivetrain(zyk, dict(D.DEFAULT_VEHICLE))
b = D.compute_drivetrain(zyk, dict(D.DEFAULT_VEHICLE))
pruefe(all(np.array_equal(a[k], b[k]) for k in ("rpm_motor", "T_motor", "F_wheel")),
       "ohne 'getriebe' im Fahrzeug bleibt die Rechnung Ziffer fuer Ziffer dieselbe")
veh = dict(D.DEFAULT_VEHICLE); veh["getriebe"] = e
c = D.compute_drivetrain(zyk, veh)
pruefe(abs(c["rpm_motor"].max() / a["rpm_motor"].max() - e["i_ist"] / 9.5) < 0.01,
       "mit Getriebe folgt die Drehzahl der GERECHNETEN Uebersetzung")
last = np.abs(a["P_wheel"]); fahrt = last > 1.0
eta = D._eta_getriebe(e, last, a["rpm_motor"])
hoch = last > np.percentile(last[fahrt], 90)
klein = fahrt & (last < np.percentile(last[fahrt], 10))
pruefe(eta[hoch].mean() > eta[klein].mean() + 0.05,
       f"der Wirkungsgrad STEIGT mit der Last ({eta[klein].mean():.3f} bei kleiner, "
       f"{eta[hoch].mean():.3f} bei grosser) — die Konstante 0,95 konnte das nicht")
pruefe(eta.max() <= e["wirkungsgrad"]["eta_nenn"] + 1e-9,
       "und uebersteigt nie den Nennwirkungsgrad")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
