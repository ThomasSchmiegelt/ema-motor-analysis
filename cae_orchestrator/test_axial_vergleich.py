# -*- coding: utf-8 -*-
"""Der axiale Paarvergleich (``ema_axial_vergleich``) -- ohne Loeser, ohne Server.

Geprueft wird gegen **Invarianten** und nicht gegen festgenagelte Zahlen: was
eine Vergleichsstufe wirklich leisten muss, ist, dass jede Achse das bewegt,
wofuer es sie gibt -- und dass sie es SAGT, wo sie nichts bewegt. Eine Tabelle
mit sechs gleichen Zeilen sieht nach einem Rechenfehler aus; drei der
vierzehn Achsen waren beim ersten Lauf genau das, und zwei davon zu Unrecht
(der Magnetwerkstoff wirkt ueber Modul-Globale, die Blechsorte ueber ein
Argument, das niemand uebergab).

    python test_axial_vergleich.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cae_cli
import ema_analysis
import ema_axial_vergleich as AV
import ema_fluss as F
import ema_pipeline as P

_ok = _fehl = 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


BASIS = cae_cli.frischer_payload("axial")


def _opt(achse, basis=None):
    e = AV.vergleiche(basis or BASIS, [achse])
    return e["achsen"][achse]


print("— 1. Das Tor: das hier ist der AXIALE Vergleich —")
try:
    AV.vergleiche(cae_cli.frischer_payload("radial"))
    pruefe(False, "ein radialer Payload muss abgewiesen werden")
except ValueError as e:
    pruefe("ema_paarvergleich" in str(e),
           "ein radialer Payload wird abgewiesen UND auf ema_paarvergleich "
           "verwiesen — absagen allein ist keine Auskunft")
try:
    AV.vergleiche(BASIS, ["gibtsnicht"])
    pruefe(False, "eine unbekannte Achse muss abgewiesen werden")
except ValueError as e:
    pruefe("Bekannt:" in str(e),
           "eine unbekannte Achse wird abgewiesen und die bekannten genannt")


print("\n— 2. Jede Achse bewegt das, wofuer es sie gibt —")
# Der Magnetwerkstoff wirkt ueber die MODUL-GLOBALEN `ema_analysis.Br_NdFeB`/
# `MU_R_MAG` (Muster `run_pipeline`, `ema_paarvergleich._setz_magnet`). Ohne
# das Umsetzen lieferte diese Achse gemessen viermal dieselben 0,8137 T, von
# N35 bis Ferrit Y30.
_mw = _opt("magnetwerkstoff")
_bg = {o["label"]: o["B_gap_T"] for o in _mw["optionen"] if o.get("ok")}
pruefe(len(set(round(v, 6) for v in _bg.values())) == len(_bg) and len(_bg) >= 2,
       f"Magnetwerkstoff: jede Sorte hat ihr eigenes B_gap ({_bg})")
_ferrit = [o for o in _mw["optionen"] if o["wert"] == "ferrite"][0]
_n35 = [o for o in _mw["optionen"] if o["wert"] == "ndfeb_n35"][0]
pruefe(_ferrit["B_gap_T"] < _n35["B_gap_T"],
       f"… und Ferrit liegt unter N35 ({_ferrit['B_gap_T']:.4f} gegen "
       f"{_n35['B_gap_T']:.4f} T) — die Richtung, nicht nur ein Unterschied")
pruefe(_mw.get("notiz") and "Preis" in _mw["notiz"],
       "… und die Achse sagt dazu, dass Masse und Kosten je Magnetsorte NICHT "
       "unterschieden werden (eine Preisliste, keine Tabelle)")

# **Die Globalen werden auch zurueckgesetzt** -- sonst faerbt die letzte
# gerechnete Option jede spaetere Rechnung im selben Prozess ein.
_br, _mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
AV.vergleiche(BASIS, ["magnetwerkstoff"])
pruefe((ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG) == (_br, _mu),
       f"Br_NdFeB/MU_R_MAG stehen danach wieder auf {_br}/{_mu}")

# Die Blechsorte wirkt NUR ueber B_sat -- also darueber, welche Optionen
# uebrig bleiben. `zahnform` fiel ohne das Argument auf seine Modulvorgabe
# 1,70 T zurueck, und die Achse war damit vollstaendig wirkungslos.
_bl = _opt("blech")
_sat = {o["label"]: o.get("grund", "") for o in _bl["optionen"]}
pruefe(any(not o.get("ok") for o in _bl["optionen"])
       and any(o.get("ok") for o in _bl["optionen"]),
       "Blechsorte: die Saettigungsgrenze trennt die Optionen wirklich "
       f"({sum(1 for o in _bl['optionen'] if o.get('ok'))} von "
       f"{len(_bl['optionen'])} baubar)")
_m250 = [o for o in _bl["optionen"] if o["wert"] == "m250_35a"][0]
pruefe(not _m250.get("ok") and "1.65" in _m250["grund"],
       "… und zwar mit dem B_sat der gewaehlten Sorte im Text "
       f"({_m250['grund'][:60]})")

# Die Bauform entscheidet die Spaltzahl und damit das Dauermoment.
_bf = {o["wert"]: o for o in _opt("bauform")["optionen"]}
pruefe(abs(_bf["einseitig"]["T_dauer_Nm"] * 2 - _bf["yasa"]["T_dauer_Nm"]) < 1e-6,
       f"Bauform: ein Luftspalt gibt das halbe Dauermoment "
       f"({_bf['einseitig']['T_dauer_Nm']:.1f} gegen "
       f"{_bf['yasa']['T_dauer_Nm']:.1f} Nm)")
pruefe(not _bf["einseitig"]["anzug_hebt_auf"] and _bf["yasa"]["anzug_hebt_auf"],
       "… und nur beim einseitigen Aufbau liegt der Anzug am Lager")
pruefe(_bf["torus_nn"]["masse_kg"] > _bf["yasa"]["masse_kg"],
       f"… und das Umfangsjoch von TORUS-NN wiegt "
       f"({_bf['torus_nn']['masse_kg']:.1f} gegen "
       f"{_bf['yasa']['masse_kg']:.1f} kg) — bis 16.10.2026 waren beide gleich")
pruefe(_bf["afir"]["magnet_kg"] < _bf["yasa"]["magnet_kg"],
       "… und AFIR traegt EINE Laeuferscheibe, also halb so viel Magnet")

# lambda ist die eine Groesse, die es radial gar nicht gibt -- und das Moment
# faellt monoton mit ihr.
_lm = [o for o in _opt("lambda")["optionen"] if o.get("ok")]
pruefe(len(_lm) >= 3 and all(a["magnet_kg"] > b["magnet_kg"]
                             for a, b in zip(_lm, _lm[1:])),
       "lambda: die Magnetmasse faellt monoton — der Ringraum schrumpft")


print("\n— 3. Was NICHTS bewegt, sagt warum —")
for _name in ("polzahl", "blech"):
    _a = _opt(_name)
    pruefe(_a["wirkungslos"] and _a["wirkungslos_grund"],
           f"{_name}: als flach erkannt UND begruendet")
# **Die Nutzahl ist nur BEDINGT flach**, und deshalb ist ihr Grund eine
# Funktion des Payloads: mit abgeleiteter Nutbreite (`axialNutBreiteMm = 0`)
# kuerzt sich die Teilung heraus, mit einem Millimetermass nicht. Ein fester
# Satz waere in einem der beiden Faelle eine Behauptung gegen die Messung.
_mm = _opt("nutzahl")
pruefe(not _mm["wirkungslos"],
       "Nutzahl mit Nutbreite in MILLIMETERN: sie bewegt den Zahn "
       f"({min(o['B_zahn_T'] for o in _mm['optionen'] if o.get('ok')):.3f} .. "
       f"{max(o['B_zahn_T'] for o in _mm['optionen'] if o.get('ok')):.3f} T)")
# Mit abgeleiteter Nutbreite saettigt der Zahn dieser Maschine bei 1,994 T;
# damit die Achse ueberhaupt zwei baubare Optionen hat (sonst ist „flach“
# nicht die richtige Auskunft, sondern „keine baubar“), bekommt sie ein Blech
# mit 2,0 T Grenze. Das ist keine Beschoenigung — es ist die Bedingung, unter
# der die Aussage ueberhaupt pruefbar ist.
_abgeleitet = {**BASIS, "stator_lam": "steel_s235",
               "geom": {**BASIS["geom"], "axialNutBreiteMm": 0.0}}
_ma = _opt("nutzahl", _abgeleitet)
pruefe(sum(1 for o in _ma["optionen"] if o.get("ok")) >= 2
       and _ma["wirkungslos"]
       and "slotWidthRatio" in (_ma["wirkungslos_grund"] or ""),
       "… und mit ABGELEITETER Nutbreite ist sie flach und nennt den "
       "richtigen Hebel (slotWidthRatio)")
# Und ohne zwei baubare Optionen heisst es NICHT „flach“ — das waere ein
# Urteil ueber eine Achse, die gar nicht verglichen werden konnte.
_leer = AV.vergleiche({**BASIS, "geom": {**BASIS["geom"],
                                         "axialNutBreiteMm": 0.0}},
                      ["nutzahl"])["achsen"]["nutzahl"]
pruefe(not _leer["wirkungslos"]
       and sum(1 for o in _leer["optionen"] if o.get("ok")) < 2,
       "ist keine Option baubar, heisst das nicht „bewegt nichts“ — die "
       "Zeile „0 von 6 baubar“ ist selbst die Auskunft")
# Eine Spanne von 0,0 % ist keine Spanne -- sonst war das Dict nie leer und
# die Erkennung blind.
pruefe(all(v > 0 for v in _ma["spannweite"].values()),
       "keine Nullzeile in der Spannweite")


print("\n— 4. Die Rangliste und die Lasten —")
_e = AV.vergleiche(BASIS)
_zaehlt = {lab for _s, lab, z in AV.SPALTEN if z}
_nicht = {lab for _s, lab, z in AV.SPALTEN if not z}
_alle = set()
for _a in _e["achsen"].values():
    _alle |= set(_a["spannweite"])
pruefe(_alle <= _zaehlt and not (_alle & _nicht),
       "Anzug, Rueckenblech, Durchbiegung, Magnetkraft und Kleber gehen NICHT "
       "in die Rangliste ein — sie sind Lasten, keine Guete")
pruefe(all(p["fuer_a"] or p["fuer_b"] or p["bewegt_nicht"]
           for a in _e["achsen"].values() for p in a["paare"]),
       "jedes Paar sagt etwas — fuer links, fuer rechts oder „bewegt NICHT“")
pruefe(all(o.get("ok") for a in _e["achsen"].values() for p in a["paare"]
           for o in a["optionen"] if o["label"] in (p["a"], p["b"])),
       "verglichen werden nur BAUBARE Optionen")

_txt = AV.als_text(_e)
pruefe("Stufe 1, analytisch" in _txt and "ARBEITSGERADEN" in _txt,
       "unter jeder Ausgabe steht, was diese Stufe NICHT rechnet")


print("\n— 5. Das Verb verzweigt nach dem FLUSSWEG —")
import inspect
_q = inspect.getsource(cae_cli.cmd_paarvergleich)
pruefe("_paarvergleich_axial" in _q and "flussweg" in _q,
       "cae_cli.cmd_paarvergleich fragt den Flussweg und verzweigt — EIN "
       "Verb, zwei Saetze Achsen (Muster feld2d)")
pruefe(all(a in cae_cli._AV_ACHSEN for a in ("bauform", "lambda", "rueckenblech")),
       "… und der Hilfetext nennt die axialen Achsen aus der EINEN Quelle")
# Der radiale Weg bleibt unberuehrt: sein Tor sagt weiterhin ab, nur ruft das
# Verb es nicht mehr an.
import ema_paarvergleich as PV
try:
    PV.vergleiche(BASIS)
    pruefe(False, "ema_paarvergleich muss den Axialfluss weiter abweisen")
except PV.AxialNichtVerglichen as e:
    pruefe("paarvergleich" in str(e).lower() or "axial" in str(e).lower(),
           "ema_paarvergleich selbst weist ihn weiter ab — es ist und bleibt "
           "der radiale Satz")


print("\n— 6. Der Fingerabdruck —")
import ema_werkzeugstand as W
pruefe("ema_axial_vergleich.py" in W.PHYSIK,
       "ema_axial_vergleich.py steht im Fingerabdruck — seine Tore "
       "entscheiden, welche Option ueberhaupt erscheint")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
