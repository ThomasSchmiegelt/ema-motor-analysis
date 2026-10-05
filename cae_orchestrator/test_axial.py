"""Pruefungen des Axialflusses (``ema_axial``, Stufe 1 aus ``AXIALFLUSS.md``).

Geprueft wird gegen **Invarianten und geschlossene Formen**, nicht gegen
festgenagelte Zahlen: ein Test, der nur nachsieht, dass sich nichts geaendert
hat, faellt bei der naechsten richtigen Verbesserung rot aus und sagt nichts
darueber, ob die Physik stimmt.

Vier Pruefungen tragen die Stufe:

* **Der Plattenloeser gegen den Kragstreifen** im Grenzfall des schmalen Rings
  -- dort MUSS er dagegen konvergieren, und er ist der einzige Teil von Stufe 1,
  der ueberhaupt eine Differentialgleichung loest.
* **lambda ist monoton**, es gibt also kein inneres Optimum. Das widerlegt die
  erste Fassung von ``AXIALFLUSS.md``, die 1/sqrt(3) als „klassischen Wert"
  fuehrte, und die Gegenprobe steht ausdruecklich als Test da -- sonst schleicht
  sich die Konstante beim naechsten Umbau zurueck.
* **Zwei Integrale, nicht ein Ersatzradius**: Fluss waechst mit r^1, Moment mit
  r^2, und ihr Verhaeltnis zum Radialfall ist deshalb VERSCHIEDEN (1,49 gegen
  1,66). Faellt diese Pruefung, ist jemand zu einer Ersatzflaeche
  zurueckgegangen.
* **Am Radialfluss bewegt sich nichts.** ``compute_performance`` und
  ``rated_torque`` gehen seit Stufe 1 durch ``ema_fluss.flaechen``; die
  Invarianz ist die erste Abnahmebedingung des ganzen Umbaus.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import numpy as np

import ema_analysis
import ema_axial as AX
import ema_fluss as F
import ema_text2ema as T
import ema_thermal

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def geom(**auf):
    g = {k: v.get("def") for k, v in T.SCHEMA.items() if v.get("geom")}
    g["axialLen"] = T.SCHEMA["axialLen"]["def"]
    g.update(fluxPath="axial", axialAktivOD=260.0, p=8, slots=48, shaftD=60)
    g.update(auf)
    return g


print("\n— 1. Der Kreisringplatten-Loeser —")

E, NU, Q = 200e9, 0.30, 345.8e3
D_ST = E * 0.012 ** 3 / (12 * (1 - NU ** 2))
for L, tol in ((0.004, 0.02), (0.001, 0.01)):
    a = 0.130 - L
    pl = AX._platte(a, 0.130, 0.012, Q, a)          # Last auf dem ganzen Ring
    soll = Q * L ** 4 / (8 * D_ST)                  # Kragstreifen, Plattensteifigkeit
    pruefe(abs(pl["w_max_m"] / soll - 1.0) < tol,
           f"schmaler Ring L={L*1e3:.0f} mm -> Kragstreifen "
           f"({pl['w_max_m']/soll:.4f}x, Toleranz {tol:.0%})")
pruefe(abs(AX._platte(0.030, 0.130, 0.012, Q, 0.0751)["randrest"]) < 1e-12,
       "freier Rand erfuellt: M_r(b) = 0 bis auf Rundung")

p1 = AX._platte(0.030, 0.130, 0.012, Q, 0.0751)
p2 = AX._platte(0.030, 0.130, 0.012, 2 * Q, 0.0751)
p3 = AX._platte(0.030, 0.130, 0.024, Q, 0.0751)
pruefe(abs(p2["w_max_m"] / p1["w_max_m"] - 2.0) < 1e-9,
       f"linear in q: {p2['w_max_m']/p1['w_max_m']:.6f}x (soll 2)")
pruefe(abs(p1["w_max_m"] / p3["w_max_m"] - 8.0) < 1e-6,
       f"w ~ 1/t^3: {p1['w_max_m']/p3['w_max_m']:.6f}x (soll 8)")

print("\n— 2. lambda: monoton, also kein inneres Optimum —")

g = geom()
m = [AX.moment(geom(axialLambda=lam), 40.0, 80) for lam in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8)]
pruefe(all(m[i] > m[i + 1] for i in range(len(m) - 1)),
       f"T faellt streng mit lambda ({m[0]:.1f} -> {m[-1]:.1f} Nm)")
# Die Mitteldurchmesser-Naeherung erzeugt ein Maximum, das das exakte Integral
# NICHT hat -- genau daraus stammt der Literaturwert.
t_ex = lambda lam: 2 * math.pi * (1 - lam ** 3) / 3
t_na = lambda lam: math.pi * (1 + lam) ** 2 * (1 - lam) / 2
best = max(np.linspace(0.001, 0.999, 9999), key=t_na)
pruefe(abs(best - 1 / 3) < 0.01,
       f"die Naeherung hat ihr Maximum bei lambda = {best:.4f} (= 1/3)")
pruefe(abs(t_na(0.0) / t_ex(0.0) - 0.75) < 1e-9,
       "und sie liegt bei lambda -> 0 um 25 % zu niedrig — daher das Scheinoptimum")
pruefe(abs(1 / math.sqrt(3) - 1 / 3) > 0.2,
       "1/sqrt(3) ist KEINER der beiden Werte (erste Fassung von AXIALFLUSS.md war falsch)")

lg = AX.lambda_grenze(geom(slots=48, slotWidthRatio=0.5))
pruefe(lg["monoton"] and lg["bindet"] in ("Nut", "Zahn"),
       f"lambda_min kommt aus der Zeichnung: {lg['lambda_min']:.4f}, bindend {lg['bindet']}")
lg2 = AX.lambda_grenze(geom(slots=72, slotWidthRatio=0.5))
pruefe(lg2["lambda_min"] > lg["lambda_min"],
       f"mehr Nuten -> groesseres lambda_min ({lg['lambda_min']:.4f} -> "
       f"{lg2['lambda_min']:.4f}), weil die Nutteilung am Innenrand schrumpft")
lg3 = AX.lambda_grenze(geom(slotWidthRatio=0.8))
pruefe(lg3["bindet"] == "Zahn",
       "bei swr = 0,8 bindet der ZAHN (die Nut hat reichlich Platz)")
pruefe(not AX.lambda_grenze(geom(axialLambda=0.10))["lambda_haelt"],
       "ein lambda unter der Zeichengrenze wird als nicht zeichenbar gemeldet")

print("\n— 3. Zahnform: die Kuerzung gilt nur auf EINEM Radius —")

zk = AX.zahnform(geom(axialZahnform="keil"), 0.63)
zp = AX.zahnform(geom(axialZahnform="parallel"), 0.63)
pruefe(abs(zk["ueberhoehung"] - 1.0) < 1e-12,
       f"Keilzahn: B_zahn ueber r konstant ({zk['b_zahn_aussen_t']:.3f} T)")
lam = AX.auslegung(geom())["lambda"]
pruefe(abs(zp["ueberhoehung"] - 1 / lam) < 1e-9,
       f"paralleler Zahn: Innenrand {zp['ueberhoehung']:.3f}x = 1/lambda "
       f"({zp['b_zahn_innen_t']:.3f} gegen {zp['b_zahn_aussen_t']:.3f} T)")
pruefe(zp["b_zahn_innen_t"] > zp["b_sat_t"] > zp["b_zahn_aussen_t"] and not zp["haelt"],
       "und genau dadurch reisst er innen, waehrend er aussen haelt — "
       "ein Faktor 1,73 auf die bindende Stelle")

print("\n— 4. Der axiale Anzug —")

az = AX.anzug(geom(), 0.9573)
pruefe(round(az["sigma_n_pa"] / 1e3, 1) == 345.7,
       f"<B_n^2>/2mu0 = {az['sigma_n_pa']/1e3:.1f} kPa — die Scheibenprobe "
       f"(axialfluss_scheibenprobe.py) misst 345,8")
pruefe(round(az["kraft_je_spalt_N"] / 1e3, 2) == 12.23,
       f"{az['kraft_je_spalt_N']/1e3:.2f} kN Anzug je Luftspalt")
pruefe(round(az["sigma_n_pa"] / 40e3, 1) == 8.6,
       f"Verhaeltnis zum momentbildenden Schub (40 kPa): "
       f"{az['sigma_n_pa']/40e3:.1f} : 1")
# Die negative Steifigkeit hat eine geschlossene Form: dF/dd|_0 = 4*sigma*A/g
k_soll = 4 * az["sigma_n_pa"] * az["ringflaeche_je_spalt_m2"] / 0.001
pruefe(abs(az["negative_steifigkeit_N_per_m"] / k_soll - 1.0) < 1e-12,
       f"negative Steifigkeit = 4*sigma*A/g = {k_soll/1e6:.1f} MN/m")
d, r20 = 0.02, az["restschub"][0.02]
f_num = (az["sigma_n_pa"] * ((1 / (1 - d)) ** 2 - (1 / (1 + d)) ** 2)
         * az["ringflaeche_je_spalt_m2"])
pruefe(abs(r20["kraft_N"] / f_num - 1.0) < 1e-9,
       f"Restschub bei 2 % Versatz {r20['kraft_N']/1e3:.2f} kN "
       f"({r20['anteil']*100:.1f} % einer Spaltkraft)")
pruefe(AX.anzug(geom(), 2 * 0.9573)["sigma_n_pa"] / az["sigma_n_pa"] == 4.0,
       "sigma ~ B^2: doppeltes Feld -> vierfache Kraft")
pruefe(not AX.anzug(geom(axialBauform="einseitig", axialSpalte=1),
                    0.9573)["hebt_sich_auf"],
       "einseitig hebt sich nichts auf — die Kraft liegt am Lager")

print("\n— 5. Rueckenblech: magnetisch gegen Durchbiegung —")

rk = AX.ruecken(geom(p=8), 0.9573)
pruefe(rk["randrest"] < 1e-12 and rk["steifigkeit_erreichbar"],
       f"magnetisch {rk['t_magnetisch_m']*1e3:.2f} mm, aus der Durchbiegung "
       f"{rk['t_steifigkeit_m']*1e3:.2f} mm")
pruefe(rk["bindet"] in ("Fluss", "Durchbiegung")
       and abs(rk["w_anteil_spalt"] - AX.W_ZUL_ANTEIL) < 0.02,
       f"bindend: {rk['bindet']}; bei t_soll liegt w bei "
       f"{rk['w_anteil_spalt']*100:.1f} % des Spalts")
# Die magnetische Forderung faellt mit der Polzahl, die Steifigkeit NICHT.
tm = [AX.ruecken(geom(p=pp), 0.9573)["t_magnetisch_m"] for pp in (4, 8, 12, 20)]
ts = [AX.ruecken(geom(p=pp), 0.9573)["t_steifigkeit_m"] for pp in (4, 8, 12, 20)]
pruefe(all(tm[i] > tm[i + 1] for i in range(len(tm) - 1)),
       f"magnetisch faellt mit 2p ({tm[0]*1e3:.1f} -> {tm[-1]*1e3:.1f} mm)")
pruefe(max(ts) - min(ts) < 1e-9,
       f"die Steifigkeitsforderung ist POLZAHLUNABHAENGIG ({ts[0]*1e3:.2f} mm) — "
       f"sie haengt am Druck, nicht an der Flussaufteilung")
pruefe(AX.ruecken(geom(p=4), 0.9573)["bindet"] == "Fluss"
       and AX.ruecken(geom(p=20), 0.9573)["bindet"] == "Durchbiegung",
       "und deshalb KREUZEN sie sich: bei 2p=8 bindet der Fluss, bei 2p=40 die Durchbiegung")
# Die Nabe ist der Haupthebel.
w_eng = AX.ruecken(geom(axialNabeD=60.0), 0.9573)["t_steifigkeit_m"]
w_weit = AX.ruecken(geom(axialNabeD=150.0), 0.9573)["t_steifigkeit_m"]
pruefe(w_weit < w_eng / 1.5,
       f"Nabe 30 -> 75 mm Radius senkt die noetige Dicke von {w_eng*1e3:.2f} "
       f"auf {w_weit*1e3:.2f} mm — die Nabe bemisst, nicht das Blech")

print("\n— 6. Bandage: die Fliehkraft wechselt die Ebene —")

b6 = AX.bandage(geom(), 6000.0)
b12 = AX.bandage(geom(), 12000.0)
pruefe(not b6["steg_vorhanden"] and not b6["bandage_werkstoff_im_werkzeug"],
       "kein Blechsteg, und es gibt keine Bandagen-Werkstofftabelle — beides gesagt")
pruefe(abs(b12["kraft_gesamt_N"] / b6["kraft_gesamt_N"] - 4.0) < 1e-9,
       f"F ~ n^2: {b6['kraft_gesamt_N']/1e3:.1f} -> {b12['kraft_gesamt_N']/1e3:.1f} kN")
ro, ri = 0.130, AX.auslegung(geom())["r_innen_m"]
pruefe(abs(b6["r_mass_m"] - (2 / 3) * (ro ** 3 - ri ** 3) / (ro ** 2 - ri ** 2)) < 1e-12,
       f"massenmittlerer Radius = (2/3)(Ro^3-Ri^3)/(Ro^2-Ri^2) = "
       f"{b6['r_mass_m']*1e3:.2f} mm")
pruefe("t_bandage_m" not in b6,
       "ohne zulaessige Spannung wird KEIN Querschnitt erfunden")
bz = AX.bandage(geom(), 12000.0, sigma_zul_mpa=1000.0)
pruefe(abs(bz["t_bandage_m"] - bz["kraft_gesamt_N"]
           / (2 * math.pi * AX.auslegung(geom())["magnet_dicke_m"] * 1e9)) < 1e-12,
       f"t_band = F/(2*pi*t_mag*sigma) = {bz['t_bandage_m']*1e3:.2f} mm "
       f"— unabhaengig von Ro")
pruefe(b12["klebescherspannung_pa"] > b6["klebescherspannung_pa"] > 0,
       f"Klebescherspannung {b6['klebescherspannung_pa']/1e6:.2f} -> "
       f"{b12['klebescherspannung_pa']/1e6:.2f} MPa")

print("\n— 7. Die zwei Integrale, und die Invarianz des Radialfalls —")

gr = {k: v.get("def") for k, v in T.SCHEMA.items() if v.get("geom")}
gr["axialLen"] = 80
fr, fa = F.flaechen(gr, 80), F.flaechen(geom(axialLambda=0.5774, axialSpalte=2), 80)
v_f = fa["a_fluss_m2"] / fr["a_fluss_m2"]
v_m = fa["a_moment_m3"] / fr["a_moment_m3"]
pruefe(round(v_f, 2) == 1.49 and round(v_m, 2) == 1.66,
       f"Fluss x{v_f:.2f}, Moment x{v_m:.2f} — VERSCHIEDEN, ein Ersatzradius "
       f"trifft nur eines")
pruefe(round(AX.moment(geom(axialLambda=0.5774), 40.0, 80), 1) == 297.2,
       f"T_axial(water, 2 Spalte) = {AX.moment(geom(axialLambda=0.5774), 40.0, 80):.1f} Nm")
pruefe(round(ema_thermal.rated_torque(gr, 80, "water"), 1) == 178.8,
       "und 178,8 Nm radial bleibt 178,8 Nm (Invarianz, erste Abnahmebedingung)")
soll = ema_analysis.r_gap_m(gr) * ema_analysis.stapellaenge_m(gr, 80)
pruefe(fr["a_fluss_m2"] == soll,
       "a_fluss radial ist ziffernweise r_gap_m*L")
pruefe(abs(ema_thermal.rated_torque(gr, 80, "water")
           - 2 * math.pi * 40e3 * fr["a_moment_m3"]) < 1e-9,
       "T = 2*pi*sigma*a_moment deckt sich mit rated_torque")

print("\n— 8. Die Tore: was NICHT axial gerechnet wird, sagt es —")

import ema_rotorcheck
import ema_saettigung
ax = geom()
r = ema_rotorcheck.rotor_layout_check(ax)
pruefe(not r["ok"] and "Scheibe" in r["fatal"][0] and "ema_axial.bandage" in r["fatal"][0],
       "rotor_layout_check weist ab und nennt ema_axial.bandage")
for fn, name in (
        (lambda: ema_rotorcheck.rotor_stress_check(
            ax, {"density": 7650, "nu": 0.3, "yield_mpa": 340}, {"n_max": 12000}),
         "rotor_stress_check (Lame-Ring)"),
        (lambda: ema_saettigung.bewerten(ax, 80, 0.63),
         "ema_saettigung.bewerten (Nutteilung)")):
    try:
        fn()
        pruefe(False, f"{name} muesste abweisen")
    except F.FlusswegNichtUnterstuetzt as e:
        pruefe("ema_axial" in str(e), f"{name} weist ab und nennt den Weg")
pruefe(ema_rotorcheck.rotor_layout_check(gr).get("flussweg") is None,
       "und der Radialfall laeuft unveraendert durch dieselbe Funktion")

print("\n— 9. Maschinenart x Flussweg, Stufen, Schema —")

pruefe(F.STUFEN_AXIAL == ("analytisch",),
       "analytisch traegt den Axialfluss, die uebrigen Stufen nicht")
for stufe in ("feld", "cad", "em3d", "lauf"):
    try:
        F.pruefe_flussweg({"geom": ax}, stufe)
        pruefe(False, f"Stufe '{stufe}' muesste abweisen")
    except F.FlusswegNichtUnterstuetzt:
        pruefe(True, f"Stufe '{stufe}' weist Axialfluss weiterhin ab")
pruefe(F.pruefe_flussweg({"geom": ax}, "analytisch") == "axial",
       "analytisch laeuft durch")
for art, soll in (("pmsm", True), ("gsm", True), ("eesm", True),
                  ("asm", False), ("synrm", False)):
    q = {"geom": dict(ax, machineType=art)}
    try:
        F.pruefe_art_flussweg(q)
        pruefe(soll, f"{art}: axial getragen")
    except F.FlusswegNichtUnterstuetzt as e:
        pruefe(not soll, f"{art}: axial abgewiesen ({str(e).split(':')[1].strip()[:44]}…)")
pruefe(F.pruefe_art_flussweg({"geom": dict(gr, machineType="synrm")}) == "radial",
       "und radial ist jede Art unberuehrt")

import ema_werkzeugstand
pruefe("ema_axial.py" in ema_werkzeugstand.PHYSIK
       and "ema_fluss.py" in ema_werkzeugstand.PHYSIK,
       "beide Module stehen im Fingerabdruck — sie bewegen Kt und das Dauermoment")
for k in ("axialAktivOD", "axialLambda", "axialSpalte", "axialBauform",
          "axialSpaltMm", "axialMagnetDicke", "axialPolbedeckung",
          "axialZahnform", "axialNabeD", "axialBminMm"):
    pruefe(T.SCHEMA[k].get("geom") is True and T.SCHEMA[k].get("adv") is True,
           f"Schema fuehrt {k} als geom-Feinparameter")
pruefe(sorted(T.SCHEMA["axialZahnform"]["opts"]) == ["keil", "parallel"],
       "die Zahnformen kommen aus einer Quelle")
roh = {k: v.get("def") for k, v in T.SCHEMA.items()}
roh.update(fluxPath="axial", axialAktivOD=260.0, axialZahnform="parallel",
           axialNabeD=90.0)
v = T._validate(roh)
pruefe(v.get("axialZahnform") == "parallel" and float(v.get("axialNabeD")) == 90.0,
       "_validate reicht alle axialen Masse durch (sonst feuerte das Tor nie)")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
