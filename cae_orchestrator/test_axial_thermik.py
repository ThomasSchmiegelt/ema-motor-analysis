"""Pruefungen des Scheiben-LPTN (``ema_axial_thermik``).

Gegen INVARIANTEN, nicht gegen festgenagelte Zahlen: was eine Formel wirklich
prueft, ist, dass sie sich gegen sich selbst schliesst -- ein eingetragener
Zahlenwert prueft nur, dass sich nichts geaendert hat.

    python test_axial_thermik.py
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_axial_thermik as AT
import ema_fluss as F
import ema_pipeline as P
import ema_thermal as TH

_ok = _fehl = 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


SEITE = dict(ro=130, lam=0.577, poles=16, q=48, bnut=6, spalt=1, zahn=25,
             jochS=0, jochR=13, magd=6, alpha=0.85, welle=60, wkI=14,
             stapel=1, magSegU=1, magSegR=1, magFuge=1, qr=0,
             topo="esdr", laeufer="sektor")
import cae_cli
_voll = cae_cli.frischer_payload()
_voll["geom"].update(F.aus_seite(SEITE))
G = _voll["geom"]            # wie der Payload, den der Reiter ablegt
G_rein = F.aus_seite(SEITE)  # und die reine Scheibe, ohne radiale Reste
MAT = (P.LAMINATES["m270_35a"], P.LAMINATES["m270_35a"],
       P.HAIRPIN_MATS["cu_etp"], P.MAGNETS["ndfeb_n35"])

print("— 1. Das Netz steht auf der SCHEIBE, nicht auf dem Zylinder —")
L = AT.leitwerte(G, "water", 3000.0)
ax = L["_axial"]
# Der Ringraum ist pi*(Ro^2-Ri^2) -- nachgerechnet, nicht uebernommen.
ro, ri = 0.130, 0.577 * 0.130
pruefe(abs(ax["A_ring_m2"] - math.pi * (ro * ro - ri * ri)) < 1e-6,
       f"Ringflaeche {ax['A_ring_m2'] * 1e4:.1f} cm^2 = pi(Ro^2-Ri^2)")
# Die Nutwand laeuft RADIAL: (Ro-Ri) lang, Zahnlaenge hoch, zwei Flanken.
pruefe(abs(ax["A_nutwand_m2"] - 48 * 2 * (ro - ri) * 0.025) < 1e-6,
       "Nutwand = Q x 2 x (Ro-Ri) x Zahnlaenge — die Nut laeuft radial, "
       "nicht axial")

print("\n— 2. Die beiden Kanten, die es NUR axial gibt —")
pruefe(L["G_w_h"] > 0,
       f"Wickelkopf → Gehaeuse {L['G_w_h']:.1f} W/K — beim YASA der "
       f"Hauptweg; radial gibt es ihn so nicht")
pruefe(L["G_ri_h"] > 0,
       f"Laeuferrueckseite → Gehaeuse {L['G_ri_h']:.1f} W/K — radial "
       f"ist der Laeufer eingeschlossen")
# Und der radiale Weg darf davon NICHTS merken.
import numpy as np
_G0 = dict(G_w_si=50, G_si_h=30, G_si_m=3, G_w_m=0, G_m_ri=300,
           G_ri_sh=5, G_sh_h=2, G_h_amb=160)
pruefe(np.array_equal(TH.build_GA(_G0),
                      TH.build_GA({**_G0, "G_w_h": 0.0, "G_ri_h": 0.0})),
       "mit beiden Kanten auf 0 ist build_GA bitgleich zum radialen Stand")

print("\n— 3. Die rotierende Scheibe —")
h0, re0, art0 = AT._h_scheibe(300.0, ro)
h1, re1, art1 = AT._h_scheibe(6000.0, ro)
pruefe(abs(re1 / re0 - 20.0) < 1e-9 and h1 > h0,
       f"Re waechst linear mit der Drehzahl ({re0:.1e} → {re1:.1e}), "
       f"h von {h0:.0f} auf {h1:.0f} W/m^2K")
pruefe(art0 == "laminar" and art1 == "turbulent",
       f"und der Ast wechselt bei Re = {AT.SCHEIBE_RE_KRIT:.1e} "
       f"({art0} → {art1})")
# Im turbulenten Ast MUSS Nu = 0,015 Re^0,8 gelten -- gegen die Formel, nicht
# gegen eine Zahl.
_nu = AT.SCHEIBE_C_TURB * re1 ** AT.SCHEIBE_N_TURB
pruefe(abs(h1 - _nu * AT.K_LUFT / ro) < 1e-9,
       "h = Nu k/Ro mit Nu = 0,015 Re^0,8 (Cobb/Saunders, Dorfman)")

print("\n— 4. Die Bauform bewegt das Netz —")
_yasa = AT.leitwerte(G, "natural", 3000.0)
_torus = AT.leitwerte({**G, "axialJochStaenderMm": 12.0}, "natural", 3000.0)
pruefe(_torus["G_si_h"] > _yasa["G_si_h"],
       f"mit Staenderjoch waechst das Randband {_yasa['G_si_h']:.1f} → "
       f"{_torus['G_si_h']:.1f} W/K — jochlos hat das Eisen fast keinen Weg")
_eins = AT.leitwerte({**G, "axialBauform": "einseitig"}, "natural", 3000.0)
pruefe(_eins["G_ri_h"] < _yasa["G_ri_h"],
       f"eine Laeuferscheibe statt zweier halbiert die Rueckseite "
       f"({_yasa['G_ri_h']:.1f} → {_eins['G_ri_h']:.1f} W/K)")

print("\n— 5. Massen: Kreisringscheiben, keine Zylinderringe —")
m = AT.masse(G, *MAT)
m2 = AT.masse({**G, "axialMagnetDicke": 12.0}, *MAT)
pruefe(abs(m2["magnet"] / m["magnet"] - 2.0) < 1e-9,
       "doppelte Magnetdicke gibt doppelte Magnetmasse (linear, wie es muss)")
m3 = AT.masse({**G, "axialAktivOD": 260.0 * 2}, *MAT)
pruefe(m3["magnet"] > 3.5 * m["magnet"],
       f"doppelter Aussendurchmesser bei gleichem lambda vervierfacht die "
       f"Ringflaeche ({m3['magnet'] / m['magnet']:.2f}x Magnetmasse)")

print("\n— 6. Durch die ganze Kette —")
r = TH.run_thermal_analysis(G, 25.0, 3000.0, 100.0, {"B_gap_T": 0.814}, *MAT,
                            cooling="water", T_amb=25.0)
st = r["steady"]
pruefe(st["T_winding"] > st["T_housing"] > r["steady"]["T_ambient"],
       f"Waerme fließt von der Wicklung ({st['T_winding']} °C) ueber "
       f"das Gehaeuse ({st['T_housing']} °C) nach aussen")
pruefe(any("Cobb" in str(w) for w in r["warnings"]),
       "die Grenzen des Netzes stehen an JEDEM Ergebnis, nicht nur im Modulkopf")
_kalt = TH.run_thermal_analysis(G, 25.0, 3000.0, 100.0, {"B_gap_T": 0.814}, *MAT,
                                cooling="natural", T_amb=25.0)
pruefe(_kalt["steady"]["T_winding"] > st["T_winding"] + 50,
       f"freie Luft statt Wasser: {st['T_winding']:.0f} → "
       f"{_kalt['steady']['T_winding']:.0f} °C")

print("\n— 7. Das Tor: welche Stufen die Scheibe traegt —")
for satz, soll in (({"thermal", "drivecycle"}, True),
                   ({"field", "thermal"}, True),
                   # `geometry` traegt seit dem 07.10.2026: das CAD der Scheibe
                   # baut `ema_axial_cad` (radiale Nuten, Sektormagnete), nicht
                   # der Vollmotorerzeuger. Was NICHT traegt, ist die
                   # Struktur-FEM -- sie rechnet Fliehkraft, die Hauptlast der
                   # Scheibe ist der axiale Anzug.
                   ({"geometry", "thermal"}, True),
                   ({"structural"}, False)):
    try:
        F.stufen_pruefen(G, satz)
        geht = True
    except F.FlusswegNichtUnterstuetzt:
        geht = False
    pruefe(geht == soll,
           f"{sorted(satz)} → {'laeuft' if soll else 'abgewiesen'}")

pruefe("ema_axial_thermik.py" in __import__("ema_werkzeugstand").PHYSIK,
       "ema_axial_thermik.py steht im Fingerabdruck — es bewegt Temperaturen")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
