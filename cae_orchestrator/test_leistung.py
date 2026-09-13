"""Leistungsermittlung (``ema_leistung.py``) -- ohne Loeser, ohne FreeCAD.

Der Kern ist absichtlich so geschnitten, dass er pruefbar ist: ``hoechstlast``
bekommt seinen Bewerter uebergeben. Damit laesst sich die Suche gegen ein
Modell pruefen, dessen richtige Antwort man AUSRECHNEN kann, statt sie aus einem
Loeserlauf zu glauben.
"""
import math
import sys

sys.path.insert(0, ".")

import ema_leistung as L
import ema_sicherheit

FEHLER = []


def pruefe(name, bed, zusatz=""):
    print(f"  {'✓' if bed else '✗'} {name}" + (f"  {zusatz}" if zusatz else ""))
    if not bed:
        FEHLER.append(name)


# ── 1. Die Grenzen kommen aus ema_sicherheit, nicht aus einer zweiten Liste ──
print("\n[1] Grenzwerte")
g35 = L.grenzwerte({"magnet": "ndfeb_n35"})
pruefe("Magnetgrenze folgt dem Werkstoff (N35)",
       abs(g35["magnet_dauer"]["grenze"] - 80.0) < 1e-9,
       f"{g35['magnet_dauer']['grenze']:.0f} °C")
pruefe("Wicklungsgrenze ist ema_sicherheit.ISOLIERKLASSE_C",
       g35["wicklung_dauer"]["grenze"] == ema_sicherheit.ISOLIERKLASSE_C,
       f"{g35['wicklung_dauer']['grenze']:.0f} °C")
# Ein anderer Werkstoff MUSS eine andere Grenze liefern -- sonst waere die
# Tabelle nur Zierde und jede Auslegung liefe gegen 80 °C.
import ema_pipeline as _P                                        # noqa: E402
_ferrit = next((k for k, v in _P.MAGNETS.items()
                if float(v.get("T_op_max", 0)) > 150), None)
if _ferrit:
    gf = L.grenzwerte({"magnet": _ferrit})
    pruefe("anderer Magnetwerkstoff -> andere Grenze",
           gf["magnet_dauer"]["grenze"] != g35["magnet_dauer"]["grenze"],
           f"{_ferrit}: {gf['magnet_dauer']['grenze']:.0f} °C")

# ── 2. Ausnutzung ────────────────────────────────────────────────────────────
print("\n[2] Ausnutzungsgrad")
a = L.ausnutzung({"T_magnet": 40.0, "T_winding": 90.0}, g35)
q = {x["name"]: x["quotient"] for x in a}
pruefe("Magnet 40/80 = 50 %", abs(q["magnet_dauer"] - 0.5) < 1e-9)
pruefe("Wicklung 90/180 = 50 %", abs(q["wicklung_dauer"] - 0.5) < 1e-9)
fehlend = L.ausnutzung({"T_magnet": None, "T_winding": 90.0}, g35)
pruefe("fehlender Wert wird None und nicht 0",
       [x for x in fehlend if x["name"] == "magnet_dauer"][0]["quotient"] is None)

# ── 3. hoechstlast gegen ein AUSRECHENBARES Modell ───────────────────────────
print("\n[3] Bisektion")
# Magnettemperatur linear: 20 °C + 1,5 °C je Nm. 80 °C werden bei genau 40 Nm
# erreicht -- die richtige Antwort steht also vorher fest.
def linear(T):
    return {"T_magnet": 20.0 + 1.5 * T, "T_winding": 20.0 + 0.5 * T}

e = L.hoechstlast(linear, g35, t_obergrenze=1000.0)
pruefe("findet die geschlossen bekannte Grenze 40,0 Nm",
       e["ok"] and abs(e["T_Nm"] - 40.0) <= L.TOLERANZ_NM,
       f"{e['T_Nm']:.3f} Nm")
pruefe("benennt das bindende Kriterium", e["bindend"] == "magnet_dauer",
       e["bindend"])
pruefe("liegt UNTER der Grenze, nie darueber",
       linear(e["T_Nm"])["T_magnet"] <= g35["magnet_dauer"]["grenze"] + 1e-9)

# Das Kriterium, das NICHT bindet, muss trotzdem mit seiner Ausnutzung
# dastehen -- es ist die Angabe, aus der eine Auslegung folgt.
qn = {x["name"]: x["quotient"] for x in e["ausnutzung"]}
pruefe("das nicht bindende Kriterium wird mitgefuehrt",
       qn.get("wicklung_dauer") is not None and qn["wicklung_dauer"] < 0.5,
       f"Wicklung {qn['wicklung_dauer'] * 100:.1f} %")

# ── 4. Der Fall, um den es eigentlich geht: es reisst im LEERLAUF ────────────
print("\n[4] Leerlauf reisst")
def zu_heiss(T):
    # 110 °C ohne jede Last -- die drehzahlabhaengigen Verluste allein.
    return {"T_magnet": 110.0 + 1.5 * T, "T_winding": 30.0}

e2 = L.hoechstlast(zu_heiss, g35, t_obergrenze=1000.0)
pruefe("meldet NICHT ok", not e2["ok"])
pruefe("T bleibt None statt 0,0 Nm", e2["T_Nm"] is None)
pruefe("sagt, dass die Verluste binden und nicht das Moment",
       e2.get("leerlauf_reisst") is True and "Moment" in e2["grund"])

# ── 5. Der elektrische Deckel bindet ─────────────────────────────────────────
print("\n[5] Umrichterdeckel")
def kalt(T):
    return {"T_magnet": 20.0 + 0.01 * T, "T_winding": 20.0 + 0.01 * T}

e3 = L.hoechstlast(kalt, g35, t_obergrenze=25.0)
pruefe("stoppt am Deckel", e3["ok"] and abs(e3["T_Nm"] - 25.0) < 1e-6,
       f"{e3['T_Nm']:.1f} Nm")
pruefe("nennt den Umrichter als bindend", e3["bindend"] == "umrichter",
       e3["bindend"])

# ── 6. Die Ehrlichkeit steht IMMER im Text ───────────────────────────────────
print("\n[6] Ungeprueftes wird gedruckt")
txt = L.als_text({"P_max_kW": 10.0, "P_max_rpm": 3000, "P_max_bindend": "magnet_dauer",
                  "punkte": [{"rpm": 3000, "T_Nm": 31.8, "P_kW": 10.0,
                              "T_elektrisch_Nm": 100.0, "bindend": "magnet_dauer",
                              "moeglich": True, "grund": "",
                              "ausnutzung": L.ausnutzung(
                                  {"T_magnet": 80.0, "T_winding": 75.0}, g35)}],
                  "ungeprueft": list(L.UNGEPRUEFT), "grenzen": g35})
pruefe("die Saettigungsluecke steht im Text", "Saettigung" in txt)
pruefe("und WARUM sie eine ist", "linear" in txt)
pruefe("und wie man sie schliesst", "_saturate_field" in txt or "em2d" in txt)
pruefe("die Ausnutzung des besten Punktes steht da", "100.0 %" in txt)

# Ein Ergebnis ohne zulaessigen Punkt darf nicht wie ein Ergebnis aussehen.
txt0 = L.als_text({"P_max_kW": 0.0, "P_max_rpm": None, "punkte": [],
                   "ungeprueft": list(L.UNGEPRUEFT)})
pruefe("kein zulaessiger Punkt wird als solcher gesagt",
       "Kein zulaessiger Betriebspunkt" in txt0)

# ── 7. Fehlerfall ────────────────────────────────────────────────────────────
print("\n[7] Fehler")
e4 = L.hoechstlast(lambda T: {"error": "Feldlauf gescheitert"}, g35, 100.0)
pruefe("ein Bewerterfehler wird durchgereicht, nicht als 0 Nm gebucht",
       not e4["ok"] and e4["T_Nm"] is None and "Feldlauf" in str(e4["grund"]))

# ── 8. Der Agent muss das Verb SEHEN ────────────────────────────────────────
print("\n[8] SKILL.md")
import os                                                        # noqa: E402
_skill = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                      ".agents", "skills", "cae-orchestrator", "SKILL.md")
if os.path.exists(_skill):
    _t = open(_skill, encoding="utf-8").read()
    pruefe("SKILL.md nennt das Verb", "`leistung`" in _t)
    # Ein Verb ohne seine Grenze ist gefaehrlicher als keines: der Agent wuerde
    # die Zahl fuer vollstaendig halten.
    pruefe("und nennt die Saettigungsluecke dazu", "Sättigung" in _t or
           "Saettigung" in _t)

# ── 9. Der Widerspruch wird an einer ECHTEN Auslegung gefunden ──────────────
# Der einzige Test hier, der den Loeser braucht (gemessen ~2 s). Er muss sein:
# die Gegenprobe gegen ``rated_torque`` ist der Grund, aus dem dieses Modul
# ueberhaupt einen BEFUNDE.md-Eintrag hat, und eine stillschweigend kaputte
# Gegenprobe waere schlimmer als gar keine.
print("\n[9] Gegenprobe gegen rated_torque (mit Loeser)")
import glob                                                      # noqa: E402
import json                                                      # noqa: E402
_kand = sorted(glob.glob(os.path.expanduser("~/cae_projekte/*/meta.json")))
_pl = None
for _m in reversed(_kand):
    try:
        _d = json.load(open(_m, encoding="utf-8")).get("payload") or {}
        if _d.get("geom"):
            _pl = _d
            break
    except Exception:                                            # noqa: BLE001
        continue
if _pl is None:
    print("  … kein abgelegtes Projekt gefunden — uebersprungen")
else:
    erg = L.kennlinie(_pl)
    pruefe("Kennlinie kommt ohne Fehler zurueck", not erg.get("error"),
           str(erg.get("error") or ""))
    pruefe("jeder Punkt nennt sein bindendes Kriterium ODER einen Grund",
           all(p.get("bindend") or p.get("grund") or p.get("moeglich")
               for p in erg.get("punkte", [])))
    pruefe("das Feld 'widerspruch' existiert (None ist erlaubt)",
           "widerspruch" in erg)
    w = erg.get("widerspruch")
    if w:
        pruefe("der Widerspruch nennt Moment, Drehzahl und Kriterium",
               all(k in w for k in ("T_rated_Nm", "rpm", "bindend", "ausnutzung")))
        pruefe("und verweist auf BEFUNDE.md", "BEFUNDE" in w["text"])
        pruefe("und steht im Text", "WIDERSPRUCH" in L.als_text(erg))
        print(f"    gemessen: {w['T_rated_Nm']} Nm -> {w['bindend']} "
              f"bei {w['ausnutzung'] * 100:.0f} %")
    else:
        print("    (kein Widerspruch an dieser Auslegung — zulaessig)")

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE LEISTUNGS-TESTS BESTANDEN ✅  (ohne Loeser, ohne FreeCAD)")
