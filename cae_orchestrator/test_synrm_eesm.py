"""Pruefungen der Reluktanz- und der fremderregten Maschine (Stufe F).

Beide Bauarten haben eine Eigenschaft, die still falsch gerechnet worden waere:

* **SynRM:** ihr Moment waechst QUADRATISCH mit dem Strom, weil derselbe Strom
  erst den Fluss aufbaut und dann das Moment macht. Ein ``Kt``, das als
  Konstante behandelt wird, ist hier sinnlos -- und das Dauermoment, das ueber
  ``T/Kt`` zurueckgerechnet wird, kam gemessen bei 178,7 Nm heraus, genauso hoch
  wie bei der PSM. Fuer eine Maschine ohne eingepraegten Fluss offensichtlich
  falsch, aber nichts widersprach.
* **EESM:** ihr Magnetisierungsstrom sitzt im LAEUFER, nicht im Stator. Wer sie
  wie die ASM rechnet, addiert ihn ein zweites Mal zum Statorstrom und nimmt ihr
  genau den Vorteil, fuer den sie gebaut wird.

Dazu die Normierungsbruecke: bei der ASM geht ``k_norm`` linear ein, bei der
SynRM **quadratisch** (beide Stroeme werden umgerechnet). Wer das verwechselt,
liegt um den Faktor ``k_norm`` -- hier rund vier -- daneben.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_asm
import ema_eesm as E
import ema_maschinenart as MA
import ema_synrm as S

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


GEOM = {"p": 3, "slots": 36, "conductorsPerSlot": 6,
        "rotorOD": 188.6, "shaftD": 60.0, "shaftBoreD": 0.0, "statorID": 190.0,
        "statorOD": 260.0, "axialLen": 80.0, "slotDepth": 22.0,
        "slotWidthRatio": 0.5, "magShape": "vasym", "magThick": 6.0,
        "magWidth": 32.0, "magDist": 13.5, "magAngle": 110.0, "magAngle2": 90.0,
        "magAsym": 0.0, "magDepthRel": 0.6, "magTangLen": 0.0,
        "magLayerGap": 8.0, "magLayers": 3, "magGapMm": 0.1,
        "nAx": 1, "nCirc": 1, "segPerPole": 6}
AXIAL = 80.0
PAYLOAD = {"geom": GEOM, "rotor_lam": "m270_35a", "stator_lam": "m270_35a",
           "hairpin_mat": "cu_etp", "cooling": "water", "axial_len": AXIAL}


# ── 1. SynRM: das Moment ist quadratisch, Kt keine Konstante ──────────────────

print("\n1. SynRM — das Moment waechst mit dem QUADRAT des Stroms")

c_rel = S.reluktanzkoeffizient(GEOM, AXIAL)
pruefe(c_rel > 0, f"der Reluktanzkoeffizient ist positiv ({c_rel:.3e} Nm/A^2)")

# T(I) = c_rel * I^2/2 bei MTPA. Doppelter Strom, vierfaches Moment.
t1 = c_rel * 200.0 ** 2 / 2.0
t2 = c_rel * 400.0 ** 2 / 2.0
pruefe(nah(t2 / t1, 4.0), "doppelter Strom gibt vierfaches Moment")

# Beide Lasten UNTER der Umrichtergrenze: an dieser Geometrie traegt die SynRM
# bei 800 A rund 7 Nm, darueber wird der Strom gedeckelt und Kt stuende zweimal
# gleich da -- nicht weil es konstant waere, sondern weil der Strom es ist.
bp1 = S.betriebspunkt(GEOM, AXIAL, 3000.0, 1.0)
bp2 = S.betriebspunkt(GEOM, AXIAL, 3000.0, 5.0)
pruefe(bp1["ok"] and bp2["ok"], "beide Betriebspunkte sind rechenbar")
pruefe(bp2["Kt_Nm_per_A"] > bp1["Kt_Nm_per_A"],
       f"Kt waechst mit dem Strom ({bp1['Kt_Nm_per_A']:.5f} bei "
       f"{bp1['I_s_A']:.0f} A gegen {bp2['Kt_Nm_per_A']:.5f} bei "
       f"{bp2['I_s_A']:.0f} A) — es ist keine Maschinenkonstante")
pruefe(bp1["Kt_konstant"] is False and bp2["Kt_konstant"] is False,
       "und das steht als 'Kt_konstant: False' im Ergebnis, statt sich zu verstecken")

# MTPA ist bei psi_pm = 0 exakt die Winkelhalbierende.
pruefe(nah(bp2["i_d_A"], bp2["i_q_A"], rel=1e-6),
       f"MTPA liegt exakt auf i_d = i_q ({bp2['i_d_A']:.1f} A) — das Maximum von "
       f"i_d*i_q bei festem i_d^2+i_q^2, keine Naeherung")
pruefe(nah(math.hypot(bp2["i_d_A"], bp2["i_q_A"]), bp2["I_s_A"], rel=1e-3),
       "und die beiden ergeben zusammen genau I_s")

# Ohne Salienz kein Moment -- und das wird gesagt, nicht gerechnet.
flach = dict(GEOM, magShape="spm")
bpf = S.betriebspunkt(flach, AXIAL, 3000.0, 100.0)
pruefe(not bpf.get("ok") and "Salienz" in bpf.get("grund", ""),
       f"ein Laeufer ohne Salienz wird abgewiesen: {bpf.get('grund','')[:70]}")


# ── 2. Die Normierungsbruecke geht QUADRATISCH ein ────────────────────────────

print("\n2. k_norm quadratisch — der Faktor, der sonst um vier danebenlaege")

kn = S.k_norm(GEOM)
ind = S.induktivitaeten(GEOM, AXIAL)
p = int(GEOM["p"])
# Das Moment muss dasselbe sein, ob man in Haus- oder in SI-Stroemen rechnet.
i_d_h = i_q_h = 300.0
t_haus = c_rel * i_d_h * i_q_h
t_phys = 1.5 * p * (ind["Lq_H"] - ind["Ld_H"]) * (i_d_h / kn) * (i_q_h / kn)
pruefe(nah(t_haus, t_phys, rel=1e-12),
       f"das Moment ist invariant: {t_haus:.3f} Nm in beiden Skalen")
falsch = 1.5 * p * (ind["Lq_H"] - ind["Ld_H"]) * i_d_h * i_q_h / kn
pruefe(abs(falsch / max(t_haus, 1e-12) - kn) < 1e-9,
       f"mit k_norm statt k_norm^2 laege es um den Faktor {kn:.2f} daneben — "
       f"und widerspraeche nicht")


# ── 3. Das Dauermoment der SynRM ──────────────────────────────────────────────

print("\n3. SynRM — das Dauermoment, das vorher zu hoch war")

import ema_thermal
t_geo = ema_thermal.rated_torque(GEOM, AXIAL, "water")
t_dauer = S.dauermoment(GEOM, AXIAL, "water",
                        S.betriebspunkt(GEOM, AXIAL, 3000.0, 5.0))["T_thermisch_Nm"]
pruefe(nah(t_dauer, t_geo / math.sqrt(2.0), rel=1e-3),
       f"T_dauer = T_kuehlbar/sqrt(2) = {t_dauer:.1f} Nm (kuehlbar "
       f"{t_geo:.1f} Nm) — bei MTPA macht nur die Haelfte des Stroms Moment")
pruefe(t_dauer < 0.75 * t_geo,
       "es liegt DEUTLICH unter dem kuehlbaren Moment — ueber den Kt-Weg kam "
       "es genauso hoch heraus wie bei der PSM")

# Und die zweite Grenze: der Umrichter. Bei der SynRM bindet er am haertesten,
# weil ihr Moment quadratisch mit dem Strom geht.
d = S.dauermoment(GEOM, AXIAL, "water", S.betriebspunkt(GEOM, AXIAL, 3000.0, 5.0))
pruefe(set(d) >= {"T_dauer_Nm", "T_thermisch_Nm", "T_umrichter_Nm", "begrenzt_durch"},
       "dauermoment gibt BEIDE Grenzen heraus und sagt, welche bindet")
pruefe(nah(d["T_dauer_Nm"], min(d["T_thermisch_Nm"], d["T_umrichter_Nm"]), rel=1e-9),
       "das gemeldete Dauermoment ist das kleinere der beiden")
pruefe(d["begrenzt_durch"] == "Umrichter" and d["T_umrichter_Nm"] < d["T_thermisch_Nm"],
       f"hier bindet der Umrichter ({d['T_umrichter_Nm']:.1f} gegen "
       f"{d['T_thermisch_Nm']:.1f} Nm kuehlbar) — das Dauermoment stand vorher "
       f"bei einem Strom da, der das Achtzehnfache der Grenze gewesen waere")


# ── 4. EESM: der Magnetisierungsstrom sitzt im Laeufer ────────────────────────

print("\n4. EESM — der Unterschied zur ASM in einer Zeile")

# UNTER der Umrichtergrenze: dort zeigt sich der Unterschied im Strom.
# Bei 120 Nm haengen beide am Deckel und ziehen zwangslaeufig dasselbe --
# ein Vergleich dort saehe wie Gleichstand aus und waere keiner.
bpe = E.betriebspunkt(GEOM, AXIAL, 3000.0, 20.0)
bpa = ema_asm.betriebspunkt(GEOM, AXIAL, 3000.0, 20.0)
pruefe(bpe["ok"], "die EESM ist an dieser Geometrie baubar")
pruefe(not bpe["strom_limit"] and not bpa["strom_limit"],
       f"bei 20 Nm haengt keine der beiden am Umrichter "
       f"(EESM {bpe['I_s_A']:.0f} A, ASM {bpa['I_s_A']:.0f} A)")
pruefe(nah(bpe["I_s_A"], bpe["i_q_A"], rel=1e-6) and bpe["i_mag_A"] == 0.0,
       f"der Stator der EESM fuehrt NUR den Momentstrom ({bpe['I_s_A']:.0f} A = i_q)")
pruefe(bpa["I_s_A"] > bpa["i_q_A"],
       f"die ASM traegt dagegen ihren Magnetisierungsstrom mit "
       f"({bpa['I_s_A']:.0f} A gegen {bpa['i_q_A']:.0f} A momentbildend)")
pruefe(bpe["I_s_A"] < bpa["I_s_A"],
       f"und braucht darum mehr Statorstrom als die EESM ({bpa['I_s_A']:.0f} "
       f"gegen {bpe['I_s_A']:.0f} A) — das ist der eigentliche Unterschied "
       f"zwischen den beiden magnetlosen Bauarten")

# AM Limit kehrt sich die Frage um: nicht wer weniger Strom braucht, sondern
# wer mit demselben Strom mehr Moment macht.
bpe_l = E.betriebspunkt(GEOM, AXIAL, 3000.0, 120.0)
bpa_l = ema_asm.betriebspunkt(GEOM, AXIAL, 3000.0, 120.0)
pruefe(nah(bpe_l["I_s_A"], bpa_l["I_s_A"], rel=1e-3),
       f"am Umrichterlimit ziehen beide denselben Strom "
       f"({bpe_l['I_s_A']:.0f} A) — der Deckel gilt fuer den STRANGSTROM, nicht "
       f"fuer seinen momentbildenden Anteil")
pruefe(bpe_l["T_ist_Nm"] > bpa_l["T_ist_Nm"],
       f"und die EESM macht daraus mehr Moment ({bpe_l['T_ist_Nm']:.1f} gegen "
       f"{bpa_l['T_ist_Nm']:.1f} Nm), weil ihr Magnetisierungsstrom im Laeufer "
       f"sitzt und den Stator nicht belegt")
pruefe(bpe["P_laeufer_W"] > 0,
       f"dafuer macht die EESM Laeuferverluste ({bpe['P_laeufer_W']:.0f} W: "
       f"{bpe['P_erreger_W']:.0f} W Erregung + {bpe['P_schleifring_W']:.0f} W "
       f"Schleifring)")


# ── 5. Der Erregerverlust haengt NICHT von der Windungszahl ab ────────────────

print("\n5. EESM — was von der Wickelentscheidung abhaengt und was nicht")

e10 = E.erregung(GEOM, AXIAL, i_f_A=10.0)
e40 = E.erregung(GEOM, AXIAL, i_f_A=40.0)
pruefe(nah(e10["P_erreger_W"], e40["P_erreger_W"], rel=1e-9),
       f"der Erregerverlust ist bei 10 A und bei 40 A derselbe "
       f"({e10['P_erreger_W']:.1f} W) — N_f kuerzt sich heraus, F_pol ist die "
       f"Groesse")
pruefe(e40["N_f_windungen"] < e10["N_f_windungen"],
       f"die Windungszahl faellt dafuer von {e10['N_f_windungen']:.0f} auf "
       f"{e40['N_f_windungen']:.0f}")
pruefe(e40["P_schleifring_W"] > 3.9 * e10["P_schleifring_W"],
       f"der Schleifringverlust waechst dagegen linear mit dem Strom "
       f"({e10['P_schleifring_W']:.0f} -> {e40['P_schleifring_W']:.0f} W) — "
       f"er haengt sehr wohl von der Wickelentscheidung ab")

# Die Stromdichte bemisst die Wicklung, das Fenster ist die Schranke.
e5 = E.erregung(GEOM, AXIAL, j_f_Apmm2=5.0)
e2 = E.erregung(GEOM, AXIAL, j_f_Apmm2=2.0)
pruefe(nah(e5["P_erreger_W"] / e2["P_erreger_W"], 2.5, rel=1e-2),
       f"der Erregerverlust geht LINEAR mit der Stromdichte: 5 statt 2 A/mm^2 "
       f"ist das 2,5-fache ({e2['P_erreger_W']:.0f} gegen "
       f"{e5['P_erreger_W']:.0f} W) — P = F_pol * J * rho * l, der "
       f"Querschnitt kuerzt sich gegen ihn weg")
pruefe(e5["fenster_reicht"] and e5["fenster_ausl"] < 1.0,
       f"die Wicklung passt ins Fenster ({100 * e5['fenster_ausl']:.0f} % belegt) "
       f"— das Fenster zu FUELLEN gab gemessen 15,7 kg Erregerkupfer bei "
       f"0,7 A/mm^2, eine Maschine, die niemand baut")
eng = E.erregung(GEOM, AXIAL, j_f_Apmm2=0.5)
pruefe(eng["J_f_Apmm2"] >= 0.5,
       "wird die Stromdichte so niedrig gewaehlt, dass das Fenster nicht "
       "reicht, steht die dann noetige hoehere Stromdichte im Ergebnis "
       "statt eines stillen Deckels")


# ── 5b. Die Polform geht in die Erregung ein ─────────────────────────────────

print("\n5b. Ein breiterer Polschuh braucht weniger Durchflutung")

e = E.erregung(GEOM, AXIAL)
soll = (4.0 / math.pi) * math.sin(E.POLBEDECKUNG * math.pi / 2.0)
pruefe(nah(e["formfaktor_pol"], soll, rel=1e-3),
       f"der Formfaktor ist (4/pi)*sin(alpha*pi/2) = {soll:.4f} und nicht eine "
       f"feste Zahl — vorher stand hier pi/4 = 0,785, das hing von der "
       f"Polbedeckung gar nicht ab und lag 12 % zu tief")

alt_pol = E.POLBEDECKUNG
try:
    f = []
    for a in (0.55, 0.68, 0.80):
        E.POLBEDECKUNG = a
        f.append(E.erregung(GEOM, AXIAL)["F_pol_A"])
finally:
    E.POLBEDECKUNG = alt_pol
pruefe(f[0] > f[1] > f[2],
       f"und er wirkt in der richtigen Richtung: {f[0]:.0f} > {f[1]:.0f} > "
       f"{f[2]:.0f} A bei 0,55 / 0,68 / 0,80 Polbedeckung")

# Die Probe an der Physik: mit der so bemessenen Durchflutung muss die
# Grundwelle des rechteckigen Polfeldes genau b_m ergeben.
b_scheitel = E.MU0 * e["F_pol_A"] / (E.K_CARTER *
                                     __import__("ema_analysis").luftspalt_mm(GEOM) / 1000.0)
b1 = (4.0 / math.pi) * b_scheitel * math.sin(E.POLBEDECKUNG * math.pi / 2.0)
# rel=1e-3, weil ``F_pol_A`` fuer die Ausgabe auf eine Stelle gerundet ist --
# die Ruecksubstitution traegt genau diese Rundung, keine Physik.
pruefe(nah(b1, e["B_m_T"], rel=1e-3),
       f"die Grundwelle des Polfeldes kommt damit auf {b1:.4f} T heraus — genau "
       f"das geforderte Ziel-Luftspaltfeld")


# ── 6. Beide sind im Begriff und im Paarvergleich angemeldet ──────────────────

print("\n6. Angemeldet — und nur da, wo sie wirklich tragen")

for code in ("synrm", "eesm"):
    art = MA.hole(code)
    pruefe(MA.traegt(code, "analytisch"),
           f"'{code}' traegt die analytische Stufe")
    for stufe in ("feld", "cad", "em3d"):
        pruefe(not MA.traegt(code, stufe),
               f"'{code}' traegt '{stufe}' NICHT — und sagt es")
    pruefe(not art.hat_magnete,
           f"'{code}' hat keine Magnete; Isc und Entmagnetisierung sind fuer sie "
           f"nicht null, sondern nicht vorhanden")

import ema_paarvergleich as P
import copy

zeilen = {}
for code in ("pmsm", "asm", "synrm", "eesm"):
    pl = copy.deepcopy(PAYLOAD)
    pl["magnet"] = "ndfeb_n42"
    pl["geom"]["machineType"] = code
    zeilen[code] = P._bewerte(pl, 12000.0, 3000.0, 120.0)
    pl["geom"].pop("machineType", None)

for code, r in zeilen.items():
    pruefe(r.get("ok"), f"'{code}' ist an derselben Geometrie baubar"
                        + ("" if r.get("ok") else f": {r.get('grund','')[:70]}"))

if all(r.get("ok") for r in zeilen.values()):
    print("      " + " ".join(f"{c:>9}" for c in zeilen))
    for k, lbl in (("Kt_Nm_per_A", "Kt"), ("I_s_A", "I_s [A]"),
                   ("T_dauer_Nm", "T_dauer"), ("P_verlust_W", "P_verl [W]"),
                   ("gesamt_kg", "Masse [kg]"), ("kosten_EUR", "Kosten [EUR]"),
                   ("magnet_kg", "Magnet [kg]")):
        print(f"  {lbl:<12}" + " ".join(f"{zeilen[c][k]:9.4g}" for c in zeilen))

    pruefe(zeilen["pmsm"]["magnet_kg"] > 0
           and all(zeilen[c]["magnet_kg"] == 0.0 for c in ("asm", "synrm", "eesm")),
           "nur die PSM braucht Magnete — bei den anderen dreien ist die 0 eine "
           "AUSSAGE und wird darum ausgerechnet, nicht unterdrueckt")
    pruefe(zeilen["synrm"]["T_dauer_Nm"] < zeilen["pmsm"]["T_dauer_Nm"],
           f"die SynRM traegt weniger Dauermoment als die PSM "
           f"({zeilen['synrm']['T_dauer_Nm']:.0f} gegen "
           f"{zeilen['pmsm']['T_dauer_Nm']:.0f} Nm)")
    pruefe(zeilen["eesm"]["T_dauer_Nm"] > zeilen["asm"]["T_dauer_Nm"],
           f"die EESM traegt am selben Umrichter mehr Dauermoment als die ASM "
           f"({zeilen['eesm']['T_dauer_Nm']:.1f} gegen "
           f"{zeilen['asm']['T_dauer_Nm']:.1f} Nm) — beide ziehen dort denselben "
           f"Strom, aber die ASM verbraucht einen Teil davon fuer ihr Feld")
    pruefe(zeilen["pmsm"]["P_verlust_W"] < zeilen["asm"]["P_verlust_W"]
           and zeilen["pmsm"]["P_verlust_W"] < zeilen["synrm"]["P_verlust_W"],
           f"die PSM bleibt die verlustaermste ({zeilen['pmsm']['P_verlust_W']:.0f} W) "
           f"— dafuer bezahlt sie mit {zeilen['pmsm']['magnet_kg']:.2f} kg Magnet")

pruefe("maschinenart" in P.ACHSEN
       and set(P.ACHSEN["maschinenart"]["werte"](None)) == set(MA.ARTEN),
       "die Achse 'maschinenart' fuehrt alle vier Bauarten")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
