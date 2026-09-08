"""Das Recht auf „Nein" — der ASM-Betriebspunkt, den es nicht gibt.

Anlass ist der Ventilatorlauf vom 08.09.2026 (siehe ``BEFUNDE.md``): eine
netzgespeiste Kleinmaschine wurde durch die Kette geschickt, und statt „nicht
darstellbar" kamen ``T_ist = 0,0 Nm`` und ``2,8e20 W`` heraus. Diese Pruefungen
halten fest, dass ein begruendetes Nein jetzt ein Ergebnis ist — und dass die
Maschinen, fuer die das Modell gebaut ist, davon unberuehrt bleiben.

Ohne Server, ohne Loeser: ``venv/bin/python test_asm_grenze.py``
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_asm
import ema_paarvergleich
import ema_referenz

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


# Der Ventilatorfall, so weit aus dem Lauf rekonstruierbar: 24 Nuten, p=1,
# Rotor 88,6 mm. Die Zahl, die alles nach sich zieht, faellt daraus.
VENTILATOR = {"p": 1, "slots": 24, "rotorOD": 88.6, "statorID": 90.0,
              "statorOD": 140.0, "shaftD": 20.0, "axialLen": 60.0,
              "slotDepth": 14.0, "machineType": "asm"}
# Eine Maschine der Klasse, fuer die das Modell gebaut ist (Traktion).
TRAKTION = {"p": 3, "slots": 36, "rotorOD": 188.6, "statorID": 190.0,
            "statorOD": 280.0, "shaftD": 60.0, "axialLen": 80.0,
            "slotDepth": 30.0, "machineType": "asm"}


print("1. Der Ventilator: das Modell sagt Nein, und sagt warum")
bp = ema_asm.betriebspunkt(VENTILATOR, 60.0, 2800.0, 0.43)
pruefe(bp["erreichbar"] is False, "erreichbar = False")
pruefe(round(bp["i_mag_A"]) == 1686,
       f"der Magnetisierungsstrom ist die Ursache: {bp['i_mag_A']:.0f} A gegen "
       f"{bp['i_lim_A']:.0f} A Grenze — dieselbe Zahl wie im gemessenen Lauf")
for stueck in ("1686", "800", "inverterImax", "kein momentbildender Strom"):
    pruefe(stueck in bp["grund"], f"der Grund nennt '{stueck}'")
pruefe(bp["T_ist_Nm"] is None and bp["i_q_A"] is None and bp["schlupf"] is None,
       "die abgeleiteten Groessen sind None, NICHT 0,0 — eine Null liest sich "
       "wie ein gerechnetes Ergebnis, und genau so wurde sie gelesen")
pruefe(ema_asm.nicht_erreichbar_text(bp) == bp["grund"],
       "und alle Verbraucher drucken denselben einen Satz")

print("\n2. Keine 2,8e20 W mehr — es wird gar nicht erst gerechnet")
verl = ema_asm.verluste(VENTILATOR, 60.0, 2800.0, 0.43, bp,
                        ema_asm.LAMINATES["m270_35a"],
                        ema_asm.LAMINATES["m270_35a"],
                        ema_asm.HAIRPIN_MATS["cu_etp"], "air")
pruefe(verl["erreichbar"] is False and verl["P_total"] is None,
       "verluste() gibt den Grund zurueck, keine Leistung")
pruefe(all(v is None or not isinstance(v, float) or abs(v) < 1e12
           for v in verl.values() if isinstance(v, (int, float))),
       "und nichts in der Naehe von 1e20 steht darin")
quelle = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "ema_asm.py"), encoding="utf-8").read()
pruefe('max(bp["i_q_A"], 1e-9)' not in quelle,
       "der Boden 1e-9 unter i_q ist weg — er war die Quelle der Zahl")
pruefe(ema_asm.dauermoment(VENTILATOR, 60.0, "air", bp)["erreichbar"] is False,
       "auch das Dauermoment rechnet ohne Betriebspunkt nicht")

print("\n3. Der Kaefig faellt nicht still auf den Fertigungsboden zurueck")
kf = ema_asm.kaefig(VENTILATOR, 60.0)
pruefe(kf["erreichbar"] is False and kf["bemessung"] == "nicht auslegbar",
       "die Nut ist als nicht bemessbar markiert, statt mit 2,0 mm dazustehen, "
       "als waere sie ausgelegt")
pruefe(kf["grund"] == bp["grund"], "mit derselben Begruendung")

print("\n4. Die Verbraucher drucken das Nein statt einer Zahl")
r = ema_paarvergleich._bewerte_asm(
    {"geom": VENTILATOR, "axial_len": 60.0, "rpm_from": 2800,
     "rpm_to": 2800, "load_nm": 0.43, "cooling": "air"},
    3200.0, 2800.0, 0.43)
pruefe(r["ok"] is False and "Nicht darstellbar" in r["grund"],
       "der Paarvergleich weist die Option ab wie eine verletzte "
       "Fliehkraftgrenze — vorher stand eine 0,0-Nm-Zeile neben echten Zahlen")
e2d = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "ema_em2d_harm.py"), encoding="utf-8").read()
pruefe("nicht_erreichbar_text(bp)" in e2d,
       "die 2-D-Stufe vernetzt keinen Rotor, den es nicht gibt")

print("\n5. Die Traktionsklasse bleibt unberuehrt")
bt = ema_asm.betriebspunkt(TRAKTION, 80.0, 3000.0, 120.0)
pruefe(bt["erreichbar"] is True and bt["grund"] == "",
       "erreichbar = True")
pruefe(isinstance(bt["T_ist_Nm"], float) and bt["T_ist_Nm"] > 0,
       f"ein Moment kommt heraus ({bt['T_ist_Nm']:.1f} Nm)")
vt = ema_asm.verluste(TRAKTION, 80.0, 3000.0, 120.0, bt,
                      ema_asm.LAMINATES["m270_35a"],
                      ema_asm.LAMINATES["m270_35a"],
                      ema_asm.HAIRPIN_MATS["cu_etp"], "water")
pruefe(0 < vt["P_total"] < 1e6, f"und eine Verlustleistung ({vt['P_total']:.0f} W)")
kt = ema_asm.kaefig(TRAKTION, 80.0)
pruefe(kt["erreichbar"] is True and kt["bemessung"] != "nicht auslegbar",
       f"der Kaefig ist bemessen ({kt['bemessung']})")

print("\n6. Die Schwelle ist eine Groesse, kein Rundungsrest")
pruefe(ema_asm.I_Q_MIN_ANTEIL == 1e-3,
       "ein Tausendstel der Stromgrenze — darunter liegt auch das Moment unter "
       "einem Tausendstel dessen, was die Maschine koennte")
pruefe(ema_asm._i_q_schwelle(800.0) == 0.8,
       "bei 800 A Grenze also 0,8 A")

print("\n7. Der Geltungsbereich benennt die Klasse")
e = {x["feld"]: x for x in ema_referenz.geltung_pruefen(
    VENTILATOR, {"geom": VENTILATOR, "rpm_from": 2800, "load_nm": 0.43})}
pruefe("Speisung" in e and e["Speisung"]["befund"] == "ausserhalb",
       "Speisung: ausserhalb — Netzbetrieb ist nicht modelliert")
pruefe("netzbetrieb" in e["Speisung"]["text"].lower(),
       "und das steht wortwoertlich da, statt dass jemand raet")
pruefe("Leistung" in e and "ausserhalb dessen, was in diesem Bestand" in
       e["Leistung"]["text"],
       "Leistung: ausserhalb — gemessen am eigenen Bestand, nicht behauptet")
pruefe("Umrichter" in e and e["Umrichter"]["befund"] == "Vorgabe",
       "und dass gar kein Umrichter gesetzt ist, steht auch da")

et = {x["feld"] for x in ema_referenz.geltung_pruefen(
    TRAKTION, {"geom": TRAKTION, "rpm_from": 3000, "load_nm": 120.0})
    if x["befund"] == "ausserhalb"}
pruefe(not et, "und die Traktionsmaschine liegt in der Klasse (keine Abweichung)")

band = ema_referenz.leistungsband()
pruefe(band["da"] and band["min_kW"] > 0,
       f"das Leistungsband ist GEMESSEN ({band['min_kW']}–{band['max_kW']} kW "
       f"aus {band['n']} Laeufen), nicht hingeschrieben")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
