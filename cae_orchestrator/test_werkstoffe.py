#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Leiterwerkstoffe: Temperatur, Druckguss und die EINE Quelle dafuer.

Zwei Befunde stehen dahinter, beide recherchiert und gemessen:

1. **Jeder Leiterwiderstand im Werkzeug wurde bei 20 °C gerechnet** — Staender,
   Kaefig, Erregung, Anker, und auch die Leitfaehigkeit, mit der Elmer den
   Kaefig loest. Ein Motor laeuft nicht bei 20 °C: eine Klasse-F-Wicklung hat
   bei 155 °C **53 % mehr Widerstand** (IEC 60228, alpha_20 = 0,00393/K fuer
   Kupfer, 0,00403/K fuer Aluminium).
2. **Der Kaefig rechnete mit einer KNETlegierung.** ``KAEFIG_VORGABE`` war
   ``al_1350`` (61 % IACS) und der Kommentar daneben sagte „Aludruckguss";
   ein echter Druckgusslaeufer erreicht gemessen 40–45 % IACS.

Geprueft wird deshalb nicht „es gibt jetzt ein alpha", sondern: dass die
Formel stimmt, dass sie an ALLEN Stellen greift (auch bei Elmer), dass ein
Gusswerkstoff kein Staender-Hairpin werden kann, und dass die Listen
ABGELEITET sind statt danebengeschrieben.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HIER = os.path.dirname(os.path.abspath(__file__))

import ema_pipeline as P                                     # noqa: E402

_ok = _bad = 0


def pruefe(bed, text):
    global _ok, _bad
    if bed:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


IACS = 1.7241e-8          # 100 % IACS [Ohm*m], die Bezugsgroesse der Prozente


print("\n1. Der Temperaturbeiwert und seine Formel")

cu = P.HAIRPIN_MATS["cu_etp"]
al = P.HAIRPIN_MATS["al_1350"]
pruefe(abs(cu["alpha_20"] - 0.00393) < 1e-9
       and abs(al["alpha_20"] - 0.00403) < 1e-9,
       "IEC 60228: Kupfer 0,00393/K, Aluminium 0,00403/K")
pruefe(P.rho_bei(cu, P.T_REF_LEITER_C) == cu["rho_el"],
       "bei 20 °C kommt der Tabellenwert heraus — die Bezugstemperatur ist "
       "benannt und nicht in die Formel gerechnet")
# Die Probe ist die RECHERCHIERTE Zahl, nicht der Code gegen sich selbst:
# eine Klasse-F-Wicklung hat bei 155 °C rund 53 % mehr Widerstand.
_f = P.rho_bei(cu, 155.0) / cu["rho_el"] - 1.0
pruefe(abs(_f - 0.531) < 0.002,
       f"Klasse F bei 155 °C: {_f*100:.1f} % mehr Widerstand (recherchiert: 53 %)")
pruefe(P.rho_bei({"rho_el": 1e-8}, 200.0) == 1e-8,
       "ohne alpha bleibt der Wert stehen, statt eine Temperatur "
       "vorzutaeuschen, die das Datenblatt nicht hergibt")


print("\n2. Der Kaefig wird GEGOSSEN")

ag, cg = P.HAIRPIN_MATS["al_guss"], P.HAIRPIN_MATS["cu_guss"]
pruefe(42.0 <= IACS / ag["rho_el"] * 100 <= 45.0,
       f"Al-Druckguss {IACS/ag['rho_el']*100:.1f} % IACS — im gemessenen Band "
       f"40–45 %, nicht die 61 % der Knetlegierung")
pruefe(88.0 <= IACS / cg["rho_el"] * 100 <= 100.0,
       f"Cu-Druckguss {IACS/cg['rho_el']*100:.1f} % IACS (Band 90–100 %)")
pruefe(ag["rho_el"] > P.HAIRPIN_MATS["al_1350"]["rho_el"],
       f"und der Guss ist WIDERSTANDSREICHER als der Draht "
       f"({ag['rho_el']:.3g} gegen {P.HAIRPIN_MATS['al_1350']['rho_el']:.3g} "
       f"Ohm*m) — der Kaefigwiderstand lag um rund 40 % zu niedrig")

import ema_asm                                               # noqa: E402

pruefe(ema_asm.KAEFIG_VORGABE == "al_guss",
       "die Vorgabe des Kaefigs ist der Gusswerkstoff — Absicht und Wert "
       "sagen jetzt dasselbe")


print("\n3. Sie greift ueberall — auch bei Elmer")

quellen = {
    "ema_thermal.py":   ("Staenderkupfer", 2),
    "ema_wicklung.py":  ("Strangwiderstand", 1),
    "ema_asm.py":       ("Kaefigstab", 1),
    "ema_eesm.py":      ("Erregerwicklung", 1),
    "ema_gsm.py":       ("Ankerwicklung", 1),
    "ema_em2d_harm.py": ("Elmer 2-D: sigma des Kaefigs", 1),
    "ema_em3d_harm.py": ("Elmer 3-D: sigma des Kaefigs", 1),
}
for datei, (was, n) in quellen.items():
    txt = open(os.path.join(HIER, datei), encoding="utf-8").read()
    pruefe(txt.count("rho_bei") >= n,
           f"{was} rechnet ueber rho_bei ({datei})")

# Die Gegenprobe ist die wichtigere: NIRGENDS darf noch ein roher
# Tabellenwert als Widerstand durchgehen.
import re                                                    # noqa: E402

for datei in ("ema_thermal.py", "ema_wicklung.py", "ema_asm.py", "ema_gsm.py",
              "ema_eesm.py", "ema_em2d_harm.py", "ema_em3d_harm.py"):
    txt = open(os.path.join(HIER, datei), encoding="utf-8").read()
    # Zeilen, die rho_el LESEN, ohne Kommentar und ohne den Magnet-Platzhalter
    # (der ist ein Wirbelstrom-Kennwert, keine Wicklung).
    roh = [z.strip() for z in txt.splitlines()
           if 'rho_el"]' in z and not z.strip().startswith("#")
           and "mag_platzhalter" not in z and "rho_bei" not in z]
    pruefe(not roh,
           f"{datei}: kein roher 20-°C-Wert mehr als Widerstand"
           + (f" — offen: {roh[0][:60]}" if roh else ""))


print("\n4. Ein Gusswerkstoff ist kein Staender-Hairpin")

import ema_text2ema as T2E                                   # noqa: E402
import ema_paarvergleich as PV                               # noqa: E402

pruefe(all(not P.HAIRPIN_MATS[k].get("guss")
           for k in T2E.SCHEMA["hairpin_mat"]["opts"]),
       "die Hairpin-Auswahl bietet keinen Druckguss an")
pruefe("al_guss" in T2E.SCHEMA["barMat"]["opts"]
       and "cu_guss" in T2E.SCHEMA["barMat"]["opts"],
       "die Kaefig-Auswahl bietet beide Gusswerkstoffe an")
# Die Listen sind ABGELEITET: ein neuer Werkstoff in der Tabelle muss ohne
# weiteres Zutun in Schema, CLI, Parametertabelle und Browser erscheinen.
pruefe(set(T2E.SCHEMA["hairpin_mat"]["opts"])
       == {k for k, v in P.HAIRPIN_MATS.items() if not v.get("guss")},
       "und sie ist aus der Werkstofftabelle abgeleitet, nicht danebengeschrieben")

_ax = PV.ACHSEN if hasattr(PV, "ACHSEN") else {}
pruefe("kaefigwerkstoff" in _ax,
       "der Paarvergleich hat eine Achse fuer den Kaefigwerkstoff — die "
       "Entscheidung war im Payload lesbar und nirgends waehlbar")
pruefe(all(not P.HAIRPIN_MATS[w].get("guss")
           for w in _ax["leiterwerkstoff"]["werte"](None)),
       "und die Staenderachse laesst den Guss weg")


print("\n5. Die Temperatur ist einstellbar und WIRKT")

pruefe(P.leitertemperatur({}) == P.T_LEITER_AUSLEGUNG_C,
       f"ohne Angabe die benannte Vorgabe ({P.T_LEITER_AUSLEGUNG_C:.0f} °C)")
pruefe(P.leitertemperatur({"tLeiterC": 60.0}) == 60.0,
       "mit `geom.tLeiterC` die gewaehlte")
pruefe("tLeiterC" in T2E.SCHEMA,
       "und sie steht im Schema — sonst waere sie fuer CLI und Agent "
       "nicht vorhanden")

import ema_analysis as EA                                    # noqa: E402
import ema_thermal as TH                                     # noqa: E402
import cae_cli                                               # noqa: E402

_p = cae_cli.frischer_payload()
_L = float(_p["axial_len"])
_M = (P.LAMINATES["m270_35a"], P.LAMINATES["m270_35a"],
      P.HAIRPIN_MATS["cu_etp"], P.MAGNETS["ndfeb_n42"])
_pcu = {}
for _T in (20.0, 115.0):
    _g = dict(_p["geom"])
    _g["tLeiterC"] = _T
    _perf = EA.run_em_analysis(_g, N=120, rotor_angle=0.0, axial_mm=_L)["performance"]
    _pcu[_T] = TH.design_point_losses(_g, _L, 5000.0, 60.0, _perf, *_M, "water")["P_Cu"]
_zu = _pcu[115.0] / _pcu[20.0] - 1.0
# Schranke passend zur AUSGABE: `P_Cu` kommt auf 0,1 W gerundet zurueck, eine
# Gleichheit auf 1e-6 pruefte die Rundung statt der Proportionalitaet.
pruefe(abs(_zu - (P.rho_bei(P.HAIRPIN_MATS["cu_etp"], 115.0)
                  / P.HAIRPIN_MATS["cu_etp"]["rho_el"] - 1.0)) < 2e-3,
       f"der Kupferverlust steigt GENAU wie rho ({_zu*100:.1f} % von 20 auf "
       f"115 °C: {_pcu[20.0]:.1f} -> {_pcu[115.0]:.1f} W)")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
