#!/usr/bin/env python3
"""Der Axialfluss-Sektor in Elmer 3-D -- Netz und ``case.sif`` OHNE Elmer.

Nach dem Muster von ``test_em3d.py``: gebaut und geprueft wird, was ohne
Loeser nachmessbar ist -- die Schichtung, der Sektorwinkel, die Magnetzahl,
die Randbedingungen und die Einheit. Der physikalische Teil (``lauf``,
``vergleich``) braucht Elmer und laeuft nur mit ``--echt``.

**Warum dieses Modul einen eigenen Test braucht und nicht an
``test_axial_fdm.py`` haengt:** es ist die GEGENRECHNUNG zum Mehrschnitt. Ein
Fehler darin sieht aus wie ein Fehler im Mehrschnitt, und am 06.10.2026 war es
umgekehrt -- der Sektor hatte recht und die Eichung der Feldstufe nicht (s.
``BEFUNDE.md``). Ein Pruefwerk, das beide Seiten in einer Datei hat, verleitet
dazu, die eine an der anderen festzunageln; dann messen zwei Wege dasselbe.
"""
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_axial                                                   # noqa: E402
import ema_axial_em3d as E3                                        # noqa: E402
import ema_axial_fdm as AF                                         # noqa: E402
import ema_text2ema as T                                           # noqa: E402

_ok = _fehl = 0
ECHT = "--echt" in sys.argv


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def _geom(**zu):
    g = {k: v.get("default") for k, v in T.SCHEMA.items() if v.get("geom")}
    g.update({"fluxPath": "axial", "p": 8, "slots": 48, "axialLen": 80,
              "axialAktivOD": 260.0, "axialLambda": 0.577, "axialSpalte": 2,
              "axialBauform": "yasa", "axialSpaltMm": 1.0,
              "axialMagnetDicke": 6.0, "axialPolbedeckung": 0.85,
              "axialZahnform": "parallel", "axialNabeD": 0,
              "axialBminMm": 2.0, "axialNutBreiteMm": 6.0,
              "axialZahnLaengeMm": 25.0, "axialJochStaenderMm": 0.0,
              "axialJochLaeuferMm": 13.0, "axialWickelkopfMm": 14.0,
              "axialStapel": 1, "axialLaeuferart": "sektor",
              "axialMagSegUmfang": 1, "axialMagSegRadial": 1,
              "axialMagFugeMm": 1.0, "axialLaeuferStaebe": 0,
              "shaftD": 60.0, "magnet": "ndfeb_n35"})
    g.update(zu)
    return g


G = _geom()

print("— 1. Die Schichtung kommt aus EINER Quelle —")

lag = E3._lagen(G)
bf = AF._BAUFORMEN[ema_axial.auslegung(G)["bauform"]]
pruefe([l["art"] for l in lag] == [a for a, _ in bf["stapel"] if True][:len(lag)]
       or all(l["art"] in dict(bf["stapel"]) for l in lag),
       f"jede Lage ist eine Lage der Bauform: {[l['art'] for l in lag]}")
pruefe(all(abs(lag[i]["z1"] - lag[i + 1]["z0"]) < 1e-9
           for i in range(len(lag) - 1)),
       "die Lagen stossen lueckenlos aneinander (kein Luftspalt aus Versehen)")
hoehe = lag[-1]["z1"]
pruefe(abs(hoehe - sum(l["d"] for l in lag)) < 1e-9,
       f"die Bauhoehe {hoehe:.2f} mm ist die Summe der Lagen")

# Der eigentliche Punkt: dieselbe Hoehe wie die Stufe, gegen die gemessen wird.
h_fdm = AF.stapelhoehe(G)
pruefe(abs(hoehe / h_fdm - 1.0) < 1e-6,
       f"und sie ist Ziffer fuer Ziffer die des Mehrschnitts "
       f"({hoehe:.3f} gegen {h_fdm:.3f} mm) — der erste Entwurf kam hier auf "
       f"90 statt 65 mm und hat damit eine andere Maschine vernetzt")

sp = [l for l in lag if l["art"] == "spalt"]
pruefe(len(sp) == ema_axial.auslegung(G)["n_spalte"],
       f"{len(sp)} Spaltschicht(en) — genau so viele, wie "
       f"ema_axial.auslegung sagt ({ema_axial.auslegung(G)['n_spalte']})")
pruefe(all(abs(l["d"] - ema_axial.auslegung(G)["luftspalt_m"] * 1000) < 1e-9
           for l in sp),
       "und jede ist genau der gezeichnete Luftspalt dick")

print("\n— 2. Das MAGNETVORZEICHEN unterscheidet die Bauformen —")

mg = [l["kenn"] for l in E3._lagen(_geom(axialBauform="yasa")) if l["art"] == "magnet"]
pruefe(len(mg) >= 1, f"YASA traegt {len(mg)} Magnetlage(n)")
_t = _geom(axialBauform="afir")
mt = [l["kenn"] for l in E3._lagen(_t) if l["art"] == "magnet"]
pruefe(len(mt) >= 1, f"AFIR traegt {len(mt)} Magnetlage(n)")
# Das Vorzeichenpaar ist der ganze Unterschied NS (YASA) gegen NN (TORUS), und
# es muss aus ``_BAUFORMEN`` kommen und nicht hier noch einmal entschieden
# werden. Geprueft wird deshalb gegen die Quelle, Lage fuer Lage.
for _b in ("yasa", "afir", "einseitig", "torus_nn"):
    try:
        _g = _geom(axialBauform=_b)
        _lg = E3._lagen(_g)
    except Exception:                                              # noqa: BLE001
        continue
    _soll = [k for a, k in AF._BAUFORMEN[
        ema_axial.auslegung(_g)["bauform"]]["stapel"] if a == "magnet"]
    _ist = [l["kenn"] for l in _lg if l["art"] == "magnet"]
    pruefe(_ist == _soll[:len(_ist)],
           f"{_b}: Magnetvorzeichen {_ist} kommt aus _BAUFORMEN, nicht von hier")

print("\n— 3. Der Sektor: EIN Pol, und der Winkel folgt der Polzahl —")

try:
    import gmsh                                                    # noqa: F401
    HAT_GMSH = True
except Exception:                                                  # noqa: BLE001
    HAT_GMSH = False

if not HAT_GMSH:
    pruefe(False, "gmsh fehlt — der Netzteil wurde NICHT geprueft "
                  "(venv: ./venv/bin/python test_axial_em3d.py)")
else:
    with tempfile.TemporaryDirectory() as td:
        netz = E3.baue_netz(G, os.path.join(td, "m.msh"), lc_mm=6.0,
                            lc_spalt_mm=1.2)
        poles = ema_axial.auslegung(G)["poles"]
        pruefe(abs(netz["alpha"] - 2 * math.pi / poles) < 1e-9,
               f"Sektorwinkel {math.degrees(netz['alpha']):.2f}° ist genau "
               f"360°/{poles} — eine Polteilung")
        pruefe(netz["knoten"] > 1000 and netz["tets"] > 1000,
               f"das Netz traegt {netz['knoten']} Knoten / {netz['tets']} Tets")
        pruefe(netz["n_magnet"] == len([l for l in lag if l["art"] == "magnet"]),
               f"{netz['n_magnet']} Magnetkoerper — einer je Magnetlage, "
               f"weil der Sektor EIN Pol ist")
        pruefe(abs(netz["hoehe_mm"] - hoehe) < 1e-6,
               "das Netz ist so hoch wie die Schichtung")
        pruefe(netz["ro_mm"] > netz["ri_mm"] > 0,
               f"der Ringraum steht: {netz['ri_mm']:.1f}…{netz['ro_mm']:.1f} mm")
        # Die Luftkappen liegen AUSSERHALB des Eisens, sonst waere der Rand im Modell.
        pruefe(netz["r_in_mm"] < netz["ri_mm"] and netz["r_out_mm"] > netz["ro_mm"],
               f"und die Luft reicht darueber hinaus "
               f"({netz['r_in_mm']:.1f}…{netz['r_out_mm']:.1f} mm) — ohne das "
               f"saesse die Randbedingung auf dem Eisen")
        pruefe(netz["lc_spalt_mm"] < netz["lc_mm"],
               f"der Spalt ist feiner vernetzt als der Rest "
               f"({netz['lc_spalt_mm']:.2f} gegen {netz['lc_mm']:.2f} mm)")

        print("\n— 4. Die ``case.sif``: Einheit, Antiperiodik, Magnetrichtung —")

        sif = E3.schreibe_sif(G, netz, td)
        txt = open(sif, encoding="utf-8").read()
        pruefe("WhitneyAVSolver" in txt, "Magnetostatik ueber WhitneyAVSolver")
        pruefe("Coordinate Scaling" not in txt,
               "KEIN Coordinate Scaling — gerechnet wird in Millimetern wie "
               "im radialen 3-D-Pfad. Zwei Einheitensysteme in einer Kette "
               "sind die Stelle, an der jemand den Faktor 1000 sucht")
        pruefe("Periodic BC = 1" in txt
               and "Periodic BC Scale = Real -1" in txt
               and "Periodic BC Rotate(3)" in txt,
               "die beiden Winkelflaechen sind ANTI-periodisch gekoppelt "
               "(Periodic BC + Rotate + Scale = -1)")
        pruefe("Periodic BC Use Lagrange Coefficient = Logical True" in txt,
               "mit Lagrange — sonst bindet die Kopplung die Kanten-DOF der "
               "Whitney-Basis nicht")
        pruefe(f"{math.degrees(netz['alpha']):.4f}" in txt
               or f"{math.degrees(netz['alpha']):.1f}" in txt,
               f"und der Drehwinkel der Kopplung ist der Sektorwinkel "
               f"({math.degrees(netz['alpha']):.2f}°) — nicht 360°/Nut oder "
               f"sonst eine Teilung")
        pruefe("Linear System Direct" in txt or "MUMPS" in txt.upper(),
               "Direkt/MUMPS — iterativ stagniert auf Tets (Hausregel)")

        import re
        m3 = re.findall(r"Magnetization 3 = Real ([-\d.eE+]+)", txt)
        m1 = re.findall(r"Magnetization 1 = Real ([-\d.eE+]+)", txt)
        m2 = re.findall(r"Magnetization 2 = Real ([-\d.eE+]+)", txt)
        pruefe(len(m3) == netz["n_magnet"],
               f"je Magnet eine Body Force: {len(m3)} bei "
               f"{netz['n_magnet']} Magnetkoerpern")
        pruefe(bool(m3) and all(abs(float(v)) > 1e5 for v in m3),
               f"Magnetization 3 (AXIAL) traegt die Koerzitivfeldstaerke: "
               f"{[f'{float(v):.3e}' for v in m3]} A/m")
        pruefe(all(abs(float(v)) < 1e-9 for v in m1 + m2) if (m1 or m2) else False,
               "und Magnetization 1/2 (radial, umfangs) sind null — das ist der "
               "ganze Unterschied zur Radialmaschine und die Stelle, an der ein "
               "uebernommener Radialzweig still falsch waere")
        # Das Vorzeichen traegt die Bauform: YASA gleichsinnig, TORUS gegensinnig.
        _vz = [1.0 if float(v) > 0 else -1.0 for v in m3]
        _soll = [l["kenn"] for l in netz["lagen"] if l["art"] == "magnet"]
        pruefe(_vz == [float(k) for k in _soll],
               f"und die Vorzeichen {_vz} sind die der Bauform {_soll} — YASA "
               f"gleichsinnig (NS), TORUS gegensinnig (NN)")
        # Elmer-Hausfalle: Body-Nummern konsekutiv ab 1.
        bodies = sorted(int(x) for x in re.findall(r"\nBody (\d+)\n", txt))
        pruefe(bodies == list(range(1, len(bodies) + 1)),
               f"die Body-Nummern laufen konsekutiv ab 1 ({len(bodies)} Koerper) "
               f"— sonst sagt Elmer 'Body 1 missing'")

        print("\n— 5. Die Grenzen reisen mit dem Ergebnis —")
        gr = E3.grenzen(netz)
        pruefe(isinstance(gr, list) and gr, f"{len(gr)} Grenze(n) benannt")
        pruefe(any("LEERLAUF" in g or "Staenderstrom" in g for g in gr),
               "der LEERLAUF ist darunter — nur dort unterscheiden sich "
               "Mehrschnitt und 3-D in der Geometrie und sonst in nichts")
        pruefe(any("Luftrand" in g for g in gr),
               "und der Luftrand — zu schmal gewaehlt klemmt er genau den "
               "seitlichen Austritt ab, fuer den es diesen Sektor gibt")
        pruefe(any("MU_R_IRON" in g or "Lineares Eisen" in g for g in gr),
               "und das lineare Eisen — beide Seiten rechnen mit demselben "
               "mu_r = 500, damit eine Abweichung zuzuordnen ist")

if ECHT and HAT_GMSH:
    print("\n— 6. Der echte Lauf gegen den Mehrschnitt (--echt) —")
    with tempfile.TemporaryDirectory() as td:
        v = E3.vergleich(G, td, k_schnitte=5, N=300, lc_mm=6.0, lc_spalt_mm=1.2)
        if not v.get("ok"):
            pruefe(False, f"Lauf gescheitert: {v.get('grund')}")
        else:
            pruefe(abs(v["abw_mittel_pct"]) < 15.0,
                   f"3-D und Mehrschnitt liegen im Mittel {v['abw_mittel_pct']:+.1f} % "
                   f"auseinander (vor der Eichberichtigung am 06.10.2026: +49 %)")
            b3 = v["B_3d_T"]
            pruefe(b3[-1] > b3[0],
                   f"und das 3-D-Feld STEIGT nach aussen ({b3[0]:.3f} → "
                   f"{b3[-1]:.3f} T) — genau der d/dr-Term, den der "
                   f"Mehrschnitt fallen laesst")
else:
    print("\n  (ohne --echt: der physikalische Teil braucht Elmer)")

print("\n— Fingerabdruck —")
import ema_werkzeugstand                                           # noqa: E402
pruefe("ema_axial_em3d.py" in ema_werkzeugstand.PHYSIK,
       "ema_axial_em3d.py steht im Fingerabdruck — es ist der Massstab, "
       "an dem die Feldstufe gemessen wird")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
