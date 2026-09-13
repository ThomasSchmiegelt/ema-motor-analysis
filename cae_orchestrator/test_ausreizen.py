"""Ausreizen (``ema_ausreizen.py``) -- der Kern ohne Loeser.

Die Suche wird gegen eine Zielfunktion geprueft, deren Optimum **feststeht**:
der Bewerter wird gestellt (wie das Sprachmodell in ``test_chat_werkzeuge``).
Damit prueft der Test die SUCHE und nicht die Physik -- und wenn er rot wird,
weiss man auch, welche der beiden gemeint ist.
"""
import math
import sys

sys.path.insert(0, ".")

import ema_ausreizen as A
import ema_optimize as O

FEHLER = []


def pruefe(name, bed, zusatz=""):
    print(f"  {'✓' if bed else '✗'} {name}" + (f"  {zusatz}" if zusatz else ""))
    if not bed:
        FEHLER.append(name)


import ema_mobil                                                  # noqa: E402
GEOM = dict(ema_mobil.basis_geom(), statorOD=305.0, statorID=171.6,
            rotorOD=170.0, shaftD=120.0, slots=36, p=6, slotDepth=30.0,
            magWidth=27.0, magThick=6.0, slotWidthRatio=0.5)
PAYLOAD = {"geom": GEOM, "axial_len": 150.0, "cooling": "water",
           "T_ambient": 25, "rpm_to": 14000, "rpm_from": 4000, "load_nm": 30,
           "stator_lam": "m270_35a", "rotor_lam": "m270_35a",
           "magnet": "ndfeb_n35", "hairpin_mat": "cu_etp"}

# ── 1. Der Hebel, ohne den gegen die Saettigung nichts auszurichten ist ─────
print("\n[1] Parametertabelle")
pruefe("slotWidthRatio ist ein freier Parameter",
       "slotWidthRatio" in O.FREE_PARAMS)
pruefe("und enger geklemmt als das Schema (0,2-0,8)",
       O.FREE_PARAMS["slotWidthRatio"]["lo"] >= 0.2
       and O.FREE_PARAMS["slotWidthRatio"]["hi"] <= 0.8,
       f"{O.FREE_PARAMS['slotWidthRatio']['lo']}...{O.FREE_PARAMS['slotWidthRatio']['hi']}")

# ── 2. Hin und zurueck: gelesen == gesetzt ──────────────────────────────────
print("\n[2] startwerte ist die Gegenrichtung zu _apply_params")
x = A.startwerte(PAYLOAD, list(O.FREE_PARAMS))
pruefe("liest magWidth aus der Geometrie", abs(x["magWidth"] - 27.0) < 1e-9)
pruefe("liest die Baulaenge aus axial_len", abs(x["axial"] - 150.0) < 1e-9)
pruefe("leitet den Luftspalt aus statorID-rotorOD ab",
       abs(x["airgap"] - 0.8) < 1e-9, f"{x['airgap']:.3f} mm")
# Der eigentliche Test: setzen und wieder lesen muss dasselbe ergeben.
pl2 = A._payload_mit(PAYLOAD, dict(x, magWidth=31.0, airgap=1.25, axial=200.0))
y = A.startwerte(pl2, list(O.FREE_PARAMS))
pruefe("gesetzt -> gelesen ist identisch (magWidth)", abs(y["magWidth"] - 31.0) < 1e-9)
pruefe("gesetzt -> gelesen ist identisch (airgap)", abs(y["airgap"] - 1.25) < 1e-9,
       f"{y['airgap']:.4f} mm")
pruefe("gesetzt -> gelesen ist identisch (axial)", abs(y["axial"] - 200.0) < 1e-9)
pruefe("und der Ausgangspayload bleibt unberuehrt",
       abs(PAYLOAD["geom"]["magWidth"] - 27.0) < 1e-9
       and abs(PAYLOAD["axial_len"] - 150.0) < 1e-9)

# ── 3. Die SUCHE, gegen ein bekanntes Optimum ──────────────────────────────
print("\n[3] Musterschritt gegen ein ausrechenbares Ziel")
_echt = A.bewerten
RUFE = {"n": 0}


def _parabel(payload, params, ziel=A.ZIEL_VORGABE, rpms=None, N=110):
    """Ziel mit Maximum bei magWidth=40 und slotDepth=20 -- Optimum bekannt."""
    RUFE["n"] += 1
    mw = float(params.get("magWidth", 0.0))
    sd = float(params.get("slotDepth", 0.0))
    wert = 100.0 - (mw - 40.0) ** 2 - 2.0 * (sd - 20.0) ** 2
    return {"ok": True, "ziel": wert, "P_kW": wert, "masse_kg": 1.0,
            "bindend": "test", "rpm": 1000,
            "ausnutzung": [{"name": "magnet_dauer", "wert": 40.0, "grenze": 80.0,
                            "einheit": "°C", "quotient": 0.5},
                           {"name": "saettigung", "wert": 1.7, "grenze": 1.7,
                            "einheit": "T", "quotient": 1.0}],
            "payload": payload, "kennlinie": {}}


A.bewerten = _parabel
try:
    erg = A.ausreizen(PAYLOAD, ziel="leistung",
                      frei=["magWidth", "slotDepth"], budget=400)
    pruefe("findet das bekannte Optimum magWidth=40",
           abs(erg["params"]["magWidth"] - 40.0) < 0.5,
           f"{erg['params']['magWidth']:.3f}")
    pruefe("findet das bekannte Optimum slotDepth=20",
           abs(erg["params"]["slotDepth"] - 20.0) < 0.5,
           f"{erg['params']['slotDepth']:.3f}")
    pruefe("der Zielwert stieg", erg["best"]["ziel"] > erg["start"]["ziel"],
           f"{erg['start']['ziel']:.2f} -> {erg['best']['ziel']:.2f}")
    pruefe("jeder Griff steht im Protokoll", len(erg["protokoll"]) > 0,
           f"{len(erg['protokoll'])} Griffe")
    pruefe("und jeder Griff nennt Parameter, Von und Nach",
           all({"parameter", "von", "nach"} <= set(p) for p in erg["protokoll"]))
    pruefe("das Budget wird eingehalten", erg["auswertungen"] <= 400,
           f"{erg['auswertungen']} Auswertungen")

    # Determinismus ist hier eine Zusicherung, keine Nebensache: ohne ihn ist
    # ein abgelegter Entwurf nicht nachvollziehbar.
    RUFE["n"] = 0
    erg2 = A.ausreizen(PAYLOAD, ziel="leistung",
                       frei=["magWidth", "slotDepth"], budget=400)
    pruefe("zweimal derselbe Lauf gibt denselben Entwurf",
           erg2["params"] == erg["params"]
           and erg2["auswertungen"] == erg["auswertungen"])

    # Budget 1: es darf NICHTS passieren ausser der Startbewertung.
    knapp = A.ausreizen(PAYLOAD, ziel="leistung", frei=["magWidth"], budget=1)
    pruefe("Budget 1 aendert nichts und wirft nicht",
           knapp["auswertungen"] <= 2 and not knapp["protokoll"])
finally:
    A.bewerten = _echt

# ── 4. Ein unzulaessiger Ausgangsentwurf ist ein Ergebnis, kein Absturz ─────
print("\n[4] Unzulaessiger Start")


def _nie(payload, params, ziel=A.ZIEL_VORGABE, rpms=None, N=110):
    return {"ok": False, "ziel": -math.inf, "grund": "kein zulaessiger Punkt",
            "payload": payload, "kennlinie": {}}


A.bewerten = _nie
try:
    e = A.ausreizen(PAYLOAD, frei=["magWidth"], budget=20)
    pruefe("meldet einen Fehler statt zu werfen", bool(e.get("error")))
    pruefe("und sagt WARUM", "zulaessig" in str(e.get("error")))
    pruefe("als_text macht daraus einen Satz",
           "nicht moeglich" in A.als_text(e))
finally:
    A.bewerten = _echt

# ── 5. Unbekannte Eingaben werden abgewiesen ───────────────────────────────
print("\n[5] Abweisungen")
for ziel, frei, was in (("gibtsnicht", None, "unbekanntes Ziel"),
                        ("dichte", ["quatsch"], "unbekannter Parameter")):
    try:
        A.ausreizen(PAYLOAD, ziel=ziel, frei=frei, budget=5)
        pruefe(f"{was} wird abgewiesen", False)
    except ValueError as exc:
        pruefe(f"{was} wird abgewiesen", True, str(exc)[:48])

# ── 6. Brachliegende Grenzen -- der eigentliche Ertrag ─────────────────────
print("\n[6] brachliegend")
AUSN = [{"name": "magnet_dauer", "wert": 40.0, "grenze": 80.0, "einheit": "°C",
         "quotient": 0.5},
        {"name": "saettigung", "wert": 1.7, "grenze": 1.7, "einheit": "T",
         "quotient": 1.0}]


def _empfindlich(payload, params, ziel=A.ZIEL_VORGABE, rpms=None, N=110):
    """Nur magWidth hebt die Magnettemperatur -- die richtige Antwort steht fest."""
    mw = float(params.get("magWidth", 27.0))
    q = min(1.0, 0.5 + (mw - 27.0) * 0.02)
    return {"ok": True, "ziel": 1.0, "P_kW": 1.0, "masse_kg": 1.0,
            "bindend": "", "rpm": 1000, "payload": payload, "kennlinie": {},
            "ausnutzung": [{"name": "magnet_dauer", "wert": q * 80.0,
                            "grenze": 80.0, "einheit": "°C", "quotient": q},
                           {"name": "saettigung", "wert": 1.7, "grenze": 1.7,
                            "einheit": "T", "quotient": 1.0}]}


A.bewerten = _empfindlich
try:
    b = A.brachliegend(PAYLOAD, x, AUSN, frei=["magWidth", "slotDepth"])
    pruefe("die ausgereizte Grenze taucht NICHT auf",
           "saettigung" not in b["offen"], f"offen: {b['offen']}")
    pruefe("die brachliegende schon", "magnet_dauer" in b["offen"])
    h = next(h for h in b["hinweise"] if h["grenze"] == "magnet_dauer")
    pruefe("und der richtige Parameter wird GEMESSEN benannt",
           h["parameter"] == "magWidth", f"{h['parameter']} {h.get('richtung')}")
    pruefe("samt Richtung und Hebelwirkung",
           h.get("richtung") == "hoch" and h.get("delta_pp", 0) > 0,
           f"+{h.get('delta_pp')} Prozentpunkte")
    # Nichts brach -> die Aussage muss "alles ausgereizt" sein, nicht Schweigen.
    b2 = A.brachliegend(PAYLOAD, x, [dict(a, quotient=1.0) for a in AUSN],
                        frei=["magWidth"])
    pruefe("alles ausgereizt -> keine Hinweise, keine Auswertungen",
           not b2["offen"] and b2["auswertungen"] == 0)
    pruefe("und als_text sagt es ausdruecklich",
           "ausgereizt" in A.als_text(
               {"ziel": "dichte", "ziel_text": "x", "einheit": "kW/kg",
                "start": {"ziel": 1.0, "P_kW": 1, "masse_kg": 1, "bindend": ""},
                "best": {"ziel": 1.0, "P_kW": 1, "masse_kg": 1, "bindend": "",
                         "ausnutzung": AUSN},
                "protokoll": [], "auswertungen": 1}, b2))
finally:
    A.bewerten = _echt

# ── 6b. Das Tor, das _clamp fehlt ──────────────────────────────────────────
# Gemessener Anlass: der erste Lauf des Optimierers fuhr shaftD auf 39,3 mm und
# shaftBore zugleich auf 190,1 mm. Jeder Wert fuer sich zulaessig, die
# Kombination nicht -- und `ema_screen` rechnete daraus -49,05 kg Wellenmasse,
# womit Leistung/Masse beliebig steigerbar war (s. BEFUNDE.md).
print("\n[6b] Stimmigkeit der Radien")
pruefe("_clamp laesst die unmoegliche Kombination durch (das ist der Punkt)",
       O._clamp({"shaftD": 39.32, "shaftBore": 190.1}) ==
       {"shaftD": 39.32, "shaftBore": 190.1})
_bad = {"statorOD": 305.0, "statorID": 171.6, "rotorOD": 170.0,
        "shaftD": 39.32, "shaftBoreD": 190.1}
pruefe("_stimmig weist sie ab", O._stimmig(_bad)["stimmig"] is False,
       O._stimmig(_bad)["stimmig_grund"][:52])
pruefe("und die gesunde Geometrie durch",
       O._stimmig(dict(_bad, shaftD=120.0, shaftBoreD=110.0))["stimmig"] is True)
for _k, _bad2 in (("statorOD <= statorID", dict(_bad, statorOD=100.0,
                                                shaftD=120.0, shaftBoreD=0.0)),
                  ("rotorOD <= shaftD", dict(_bad, shaftD=180.0,
                                             shaftBoreD=0.0))):
    pruefe(f"{_k} wird erkannt", O._stimmig(_bad2)["stimmig"] is False)
pruefe("_violation rangiert Unstimmiges wie Unbaubares",
       O._violation({"stimmig": False}, []) >= 1e8)
import ema_screen as _S                                           # noqa: E402
_m = _S.massen_und_kosten({"geom": dict(GEOM, shaftD=39.32, shaftBoreD=190.1),
                           "axial_len": 150.0})
pruefe("die Wellenmasse kann nicht mehr negativ werden",
       _m["welle_kg"] >= 0.0, f"{_m['welle_kg']} kg (war -49.05)")

# ── 6c. Eine kleinere Maschine ist eine ANDERE Maschine ────────────────────
print("\n[6c] Groessenaenderung wird benannt")
_g = A._groesse(
    {"masse_kg": 74.2, "payload": {"geom": {"axialLen": 150.0}}},
    {"masse_kg": 20.5, "payload": {"geom": {"axialLen": 39.3}}})
pruefe("eine geviertelte Baulaenge gilt als wesentlich", _g["wesentlich"] is True,
       f"{_g['laenge_pct']:+.0f} % Laenge, {_g['masse_pct']:+.0f} % Masse")
_gleich = A._groesse(
    {"masse_kg": 74.2, "payload": {"geom": {"axialLen": 150.0}}},
    {"masse_kg": 73.0, "payload": {"geom": {"axialLen": 149.0}}})
pruefe("eine unveraenderte Maschine NICHT", _gleich["wesentlich"] is False)
_txt = A.als_text({"ziel": "dichte", "ziel_text": "x", "einheit": "kW/kg",
                   "groesse": _g,
                   "start": {"ziel": 0.18, "P_kW": 13.0, "masse_kg": 74.2,
                             "bindend": "magnet_dauer"},
                   "best": {"ziel": 1.63, "P_kW": 33.5, "masse_kg": 20.5,
                            "bindend": "magnet_dauer", "ausnutzung": AUSN},
                   "protokoll": [], "auswertungen": 10})
pruefe("der Text warnt davor", "ANDERE Maschine" in _txt)
pruefe("und nennt den Ausweg (--frei ohne die Groessenparameter)",
       "--frei" in _txt and "axial" in _txt)

# ── 7. Der Agent muss das Verb sehen ───────────────────────────────────────
print("\n[7] SKILL.md")
import os                                                         # noqa: E402
_sk = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..",
                   ".agents", "skills", "cae-orchestrator", "SKILL.md")
if os.path.exists(_sk):
    _t = open(_sk, encoding="utf-8").read()
    pruefe("SKILL.md nennt das Verb", "`ausreizen`" in _t)
    pruefe("und den Unterschied dichte/leistung",
           "dichte" in _t and "Symptom" in _t)
    pruefe("und dass der Sieger ein Vorschlag ist", "Vorschlag" in _t)

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE AUSREIZ-TESTS BESTANDEN ✅  (ohne Loeser, ohne FreeCAD)")
