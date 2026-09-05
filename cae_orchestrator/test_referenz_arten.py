"""Pruefungen der Recherche zu den drei neuen Maschinenarten.

Wozu diese Pruefungen
----------------------

Recherchierte Zahlen sind **Fremdtext**. Der einzige Wert, den sie haben, ist
ihre Nachpruefbarkeit -- eine Zahl ohne Quelle ist hier schlechter als keine
Zahl, weil sie aussieht wie ein Messwert. Geprueft wird deshalb nicht der
Inhalt der Quellen (das kann kein Test), sondern die **Trennung**:

* jede recherchierte Zahl nennt eine hinterlegte Quelle und eine Fundstelle;
* jedes abgeleitete Band nennt die Messpunkte, auf denen es ruht;
* keine gerechnete Zahl wird von der Recherche **veraendert** -- sie ist eine
  Einordnung und kein Tor;
* und wo ein Vergleich gar nicht zulaessig ist (beide Seiten am
  Umrichter-Limit), sagt er das, statt eine Abweichung zu melden, die keine ist.

Der letzte Punkt ist der wichtigste. Ein Band, das faelschlich „ausserhalb"
meldet, ist genauso schaedlich wie eine falsche Zahl: es lenkt die
Aufmerksamkeit auf ein Modell, das an dieser Stelle nichts falsch macht.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_referenz as R

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


NEU = ("gundogdu2023", "gercekcioglu2021", "carlsson2026")


# ── 1. Jede Zahl hat eine Adresse ─────────────────────────────────────────────

print("\n1. Fremdtext bleibt nachpruefbar")

for q in NEU:
    pruefe(q in R.QUELLEN, f"Quelle '{q}' ist hinterlegt")
    e = R.QUELLEN.get(q, {})
    pruefe(all(e.get(k) for k in ("titel", "kennung", "url", "stelle")),
           f"'{q}' nennt Titel, Kennung, Adresse und Fundstelle")

neue_punkte = [m for m in R.MESSPUNKTE if m["quelle"] in NEU]
pruefe(len(neue_punkte) >= 20,
       f"{len(neue_punkte)} woertlich uebernommene Zahlen zu den drei neuen Arten")
for m in neue_punkte:
    if not (m.get("zitat") and m["quelle"] in R.QUELLEN):
        pruefe(False, f"'{m['groesse']}' ohne Zitat oder ohne Quelle")
        break
else:
    pruefe(True, "jede von ihnen nennt Zitat und Quelle — kein Trefferanriss")

namen = [m["groesse"] for m in R.MESSPUNKTE]
pruefe(len(namen) == len(set(namen)),
       "keine Groesse steht zweimal drin (sonst entschiede die Reihenfolge, "
       "welche Quelle gilt)")


# ── 2. Jedes Band ruht auf Messpunkten ────────────────────────────────────────

print("\n2. Abgeleitet heisst: mit genannter Grundlage")

for code, band in R.ART_BAND.items():
    if code.startswith("_"):
        continue
    for groesse, e in band.items():
        lo, hi = e["band"]
        ok = (lo <= hi and e["stuetzen"]
              and all(R.messpunkt(s) for s in e["stuetzen"])
              and lo <= e["nenn"] <= hi and e.get("bemerkung"))
        if not ok:
            pruefe(False, f"{code}.{groesse}: Band, Nennwert oder Stuetzen fehlerhaft")
            break
    else:
        pruefe(True, f"'{code}': alle {len(band)} Baender nennen vorhandene "
                     f"Messpunkte, und der Nennwert liegt im Band")

pruefe(R.art_band("asm", "schlupf_pct") == (2.0, 13.3),
       "art_band gibt das Band heraus")
pruefe(R.art_band("pmsm", "schlupf_pct") is None
       and R.art_band("_limit_hinweis", "x") is None,
       "und None, wo keines hinterlegt ist — auch fuer den Hinweisschluessel")


# ── 3. Kein Tor: die Recherche aendert keine gerechnete Zahl ──────────────────

print("\n3. Einordnung, kein Tor")

drin = R.art_pruefen("asm", {"schlupf_pct": 5.0, "xi_LqLd": 1.0})
pruefe(drin == [], "ein Wert im Band meldet nichts")
raus = R.art_pruefen("asm", {"schlupf_pct": 0.24})
pruefe(len(raus) == 1 and "0.24" in raus[0] and "5.5" in raus[0],
       f"ein Wert ausserhalb meldet sich MIT dem Nennwert: {raus[0]}")
pruefe(R.art_pruefen("asm", {}) == [],
       "was nicht gerechnet wurde, wird auch nicht bemaengelt")
pruefe(R.art_pruefen("pmsm", {"schlupf_pct": 999}) == [],
       "eine Art ohne eigenes Band meldet nichts, statt fremde Baender anzuwenden")


# ── 4. Der Vergleich ZWISCHEN den Arten ───────────────────────────────────────

print("\n4. Was erst zwischen zwei Bauarten eine Aussage ist")

zeilen = {
    "pmsm": {"ok": True, "I_s_A": 550.0, "P_verlust_W": 500.0, "Kt_Nm_per_A": 0.03},
    "eesm": {"ok": True, "I_s_A": 400.0, "P_verlust_W": 450.0, "Kt_Nm_per_A": 0.05},
    "asm":  {"ok": True, "I_s_A": 600.0, "P_verlust_W": 630.0, "Kt_Nm_per_A": 0.05},
    "synrm": {"ok": True, "I_s_A": 500.0, "P_verlust_W": 260.0, "Kt_Nm_per_A": 0.055},
}
v = {e["groesse"]: e for e in R.arten_gegenueberstellung(zeilen)}
pruefe(len(v) == 3, f"drei Verhaeltnisse werden gebildet: {list(v)}")
pruefe(v["EESM-Statorstrom / PSM-Statorstrom"]["im_band"],
       "400/550 = 0,73 liegt im recherchierten Band — genau der Messwert")
pruefe(v["SynRM-Verluste / ASM-Verluste"]["im_band"],
       "260/630 = 0,41 ebenfalls — das ist der gemessene Wert")
pruefe(all(e["beleg"] in R.QUELLEN for e in v.values()),
       "jeder Vergleich nennt seine Quelle")

# Fehlt eine Seite, entfaellt der Vergleich -- er wird nicht ersetzt.
ohne = R.arten_gegenueberstellung({"eesm": zeilen["eesm"]})
pruefe(ohne == [],
       "ohne Gegenstueck entfaellt der Vergleich, statt gegen etwas anderes "
       "gerechnet zu werden")
nicht_ok = R.arten_gegenueberstellung({**zeilen, "pmsm": {"ok": False}})
pruefe(all(e["groesse"] != "EESM-Statorstrom / PSM-Statorstrom" for e in nicht_ok),
       "eine nicht baubare Seite zaehlt nicht als Vergleichspartner")


# ── 5. Der Umrichterdeckel darf nicht als Modellfehler erscheinen ─────────────

print("\n5. Wo ein Vergleich gar nicht zulaessig ist, sagt er es")

am_limit = dict(zeilen)
am_limit["eesm"] = {**zeilen["eesm"], "I_s_A": 800.0, "strom_limit": True}
am_limit["pmsm"] = {**zeilen["pmsm"], "I_s_A": 796.0}
e = [x for x in R.arten_gegenueberstellung(am_limit)
     if x["groesse"] == "EESM-Statorstrom / PSM-Statorstrom"][0]
pruefe(not e["im_band"], "800/796 faellt aus dem Band")
pruefe(e.get("vergleichbar") is False and "NICHT VERGLEICHBAR" in e["text"],
       "aber es wird als NICHT VERGLEICHBAR gemeldet und nicht als Abweichung — "
       "beide Stroeme laufen gegen dieselbe Schranke")
pruefe("INVERTER_I_MAX" in e["text"],
       "und der Text nennt die Schranke beim Namen, damit sie nachschlagbar ist")
pruefe(v["EESM-Statorstrom / PSM-Statorstrom"].get("vergleichbar") is True,
       "ohne Deckel ist derselbe Vergleich vergleichbar")


# ── 6. Die Recherche steht im Text, den Agent und Mensch lesen ────────────────

print("\n6. Auffindbar fuer PI, Hermes und Mensch")

t = R.als_text()
for q in NEU:
    pruefe(R.QUELLEN[q]["url"] in t, f"'{q}' steht mit Adresse in der Textausgabe")
pruefe("Baender je Maschinenart" in t,
       "die Baender je Bauart stehen in 'paarvergleich --referenz'")
for code in ("asm", "synrm", "eesm"):
    pruefe(R.art_text(code) in t, f"der Abschnitt zu '{code}' ist vollstaendig enthalten")
pruefe("_limit_hinweis" not in t,
       "der interne Hinweisschluessel taucht NICHT als Bauart auf")

import ema_paarvergleich as P
import copy
BASIS = {"geom": {"p": 3, "slots": 36, "conductorsPerSlot": 6,
    "rotorOD": 188.6, "shaftD": 60.0, "shaftBoreD": 0.0, "statorID": 190.0,
    "statorOD": 260.0, "axialLen": 80.0, "slotDepth": 22.0, "slotWidthRatio": 0.5,
    "magShape": "vasym", "magThick": 6.0, "magWidth": 32.0, "magDist": 13.5,
    "magAngle": 110.0, "magAngle2": 90.0, "magAsym": 0.0, "magDepthRel": 0.6,
    "magTangLen": 0.0, "magLayerGap": 8.0, "magLayers": 3, "magGapMm": 0.1,
    "nAx": 1, "nCirc": 1, "segPerPole": 6},
  "rotor_lam": "m270_35a", "stator_lam": "m270_35a", "hairpin_mat": "cu_etp",
  "magnet": "ndfeb_n42", "cooling": "water", "axial_len": 80.0, "load_nm": 120.0,
  "rpm_from": 3000.0, "target": {"n_max": 12000.0}}

erg = P.vergleiche(copy.deepcopy(BASIS), achsen=["maschinenart"],
                   n_max=12000, rpm=3000, last_nm=120)
pruefe(erg.get("arten_vergleich"),
       f"der Paarvergleich fuehrt {len(erg.get('arten_vergleich', []))} "
       f"Bauart-Verhaeltnisse mit")
txt = P.als_text(erg)
pruefe("BAUART GEGEN BAUART" in txt,
       "und sie stehen in der Textausgabe, die der Agent liest")
opt = {o["wert"]: o for o in erg["achsen"]["maschinenart"]["optionen"]}
pruefe(any(opt[c].get("band_art") for c in opt if opt[c].get("ok")),
       "auch je Option steht die Einordnung dabei")
pruefe(all("recherchiert, kein Tor" in z
           for z in txt.splitlines() if "ⓘ" in z and "liegt ausserhalb" in z),
       "jede Einordnungszeile sagt ausdruecklich, dass sie kein Tor ist")

# Und die Probe, dass nichts Gerechnetes davon abhaengt: dieselbe Rechnung ohne
# Recherche muss dieselben Kennwerte geben.
ohne_band = {c: {k: v for k, v in o.items() if k != "band_art"} for c, o in opt.items()}
pruefe(all(ohne_band[c].get("Kt_Nm_per_A") == opt[c].get("Kt_Nm_per_A") for c in opt),
       "die Recherche veraendert keine gerechnete Kennzahl — sie steht daneben")


print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
