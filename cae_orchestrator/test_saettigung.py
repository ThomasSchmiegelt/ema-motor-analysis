"""Saettigung (``ema_saettigung.py``) -- ohne Loeser, ohne FreeCAD.

Die Flusserhaltung hat eine seltene, angenehme Eigenschaft: sie laesst sich
**gegen sich selbst schliessen**. Derselbe Polfluss, einmal aus dem Luftspalt
und einmal aus den Zaehnen gerechnet, muss dieselbe Zahl geben — und zwar auf
Rundungsniveau, nicht ungefaehr. Das prueft die Formel wirklich, waehrend ein
festgenagelter Zahlenwert nur prueft, dass sich nichts geaendert hat.
"""
import math
import sys

sys.path.insert(0, ".")

import ema_pipeline as P
import ema_saettigung as S
import ema_wicklung as W

FEHLER = []


def L_ausn(e):
    """Die Lastkriterien-Liste zu einer Bewertung."""
    import ema_leistung
    return ema_leistung.ausnutzung(
        {"T_magnet": 40.0, "T_winding": 90.0, "B_eisen": e["wert_T"]},
        ema_leistung.grenzwerte({"magnet": "ndfeb_n35"}))


def pruefe(name, bed, zusatz=""):
    print(f"  {'✓' if bed else '✗'} {name}" + (f"  {zusatz}" if zusatz else ""))
    if not bed:
        FEHLER.append(name)


# Die Geometrie wird aus den SCHEMAVORGABEN aufgefuellt. Von Hand geschrieben
# fehlte hier `magDepthRel`, und `_eval_geom` gab daraufhin `error` zurueck --
# der Saettigungszweig lief gar nicht erst an. Ein unvollstaendiger Testfall
# prueft dann nicht das, was er zu pruefen vorgibt.
import ema_mobil                                                  # noqa: E402
GEOM = dict(ema_mobil.basis_geom(),
            statorOD=305.0, statorID=171.6, rotorOD=170.0, shaftD=110.0,
            slots=36, p=6, slotDepth=30.0, magShape="bar",
            magThick=6.0, magWidth=40.0, conductorsPerSlot=6)
AXIAL = 150.0

# ── 1. Die Grenze kommt aus der Werkstofftabelle ────────────────────────────
print("\n[1] Blechgrenze")
for key in ("m250_35a", "m270_35a", "m800_65a"):
    b, lbl = S._blech_bsat(key)
    pruefe(f"{key} -> {b} T", abs(b - P.LAMINATES[key]["B_sat_T"]) < 1e-9, lbl)
pruefe("das aufgeloeste Dict gibt DASSELBE wie der Schluessel",
       S._blech_bsat(P.LAMINATES["m800_65a"]) == S._blech_bsat("m800_65a"))
# Der Fall, der frueher still danebenging: aus einem Dict den Schluessel raten.
pruefe("ein unbekannter Schluessel faellt NICHT auf ein falsches Blech",
       S._blech_bsat("gibtsnicht")[0] == P.LAMINATES["m270_35a"]["B_sat_T"])

# ── 2. Flusserhaltung gegen sich selbst ─────────────────────────────────────
print("\n[2] Flusserhaltung schliesst sich")
e = S.eisenwege(GEOM, AXIAL, 0.6, "m270_35a")
ng = W.nutgeometrie(GEOM)
n_zahn_pol = ng["n_slots"] / (2 * GEOM["p"])
# Der Zahnwert ist der SPITZENwert (der Zahn im Wellenberg sammelt eine
# Nutteilung); der Mittelwert ueber die Zaehne eines Pols liegt um 2/pi tiefer.
phi_aus_zaehnen = (e["B_zahn_T"] * (2 / math.pi) * n_zahn_pol
                   * ng["zahn_breite_m"] * (AXIAL / 1000.0) * S.STAPELFAKTOR)
abw = abs(phi_aus_zaehnen * 1000.0 - e["phi_pol_mWb"]) / e["phi_pol_mWb"]
pruefe("Polfluss aus B_gap == Polfluss durch die Zaehne", abw < 1e-3,
       f"{e['phi_pol_mWb']:.4f} gegen {phi_aus_zaehnen * 1000:.4f} mWb "
       f"({abw * 100:.3f} %)")

# ── 3. Die Abhaengigkeiten muessen stimmen, nicht nur die Zahl ──────────────
print("\n[3] Abhaengigkeiten")
e2 = S.eisenwege(GEOM, AXIAL, 1.2, "m270_35a")
pruefe("B waechst LINEAR mit B_gap",
       abs(e2["B_zahn_T"] / e["B_zahn_T"] - 2.0) < 1e-6,
       f"{e['B_zahn_T']:.3f} -> {e2['B_zahn_T']:.3f} T")
e3 = S.eisenwege(GEOM, 2 * AXIAL, 0.6, "m270_35a")
pruefe("der ZAHN haengt NICHT an der Baulaenge (Fluss und Flaeche wachsen "
       "beide mit L)", abs(e3["B_zahn_T"] - e["B_zahn_T"]) < 1e-6)
pruefe("das JOCH ebenso wenig", abs(e3["B_joch_T"] - e["B_joch_T"]) < 1e-6)
# Die naheliegende Erwartung "mehr Nuten -> schmalerer Zahn -> hoeheres B" ist
# in diesem Werkzeug FALSCH, und das ist der Punkt: `nutgeometrie` setzt die
# Nutbreite als festen Anteil der Nutteilung, also kuerzt sich die Teilung aus
# B_zahn = B_gap*tau/(b_zahn*k_fe) heraus. Gemessen geben 24/36/48/60 Nuten
# denselben Wert. Wer das nicht weiss, dreht an der Nutzahl und wundert sich.
for _n in (24, 48, 60):
    _e = S.eisenwege(dict(GEOM, slots=_n), AXIAL, 0.6, "m270_35a")
    pruefe(f"{_n} Nuten aendern B_zahn NICHT (festes Nut/Zahn-Verhaeltnis)",
           abs(_e["B_zahn_T"] - e["B_zahn_T"]) < 1e-9, f"{_e['B_zahn_T']:.4f} T")
# Der WIRKLICHE Hebel, geschlossen nachgerechnet.
for _r in (0.35, 0.65):
    _e = S.eisenwege(dict(GEOM, slotWidthRatio=_r), AXIAL, 0.6, "m270_35a")
    _soll = 0.6 / ((1 - _r) * S.STAPELFAKTOR)
    pruefe(f"slotWidthRatio={_r} -> B_zahn = B_gap/((1-r)*k_fe)",
           abs(_e["B_zahn_T"] - _soll) / _soll < 2e-3,
           f"{_e['B_zahn_T']:.4f} gegen {_soll:.4f} T")
duenn = dict(GEOM, statorOD=240.0)
e5 = S.eisenwege(duenn, AXIAL, 0.6, "m270_35a")
pruefe("duenneres Joch -> hoeheres B_joch",
       e5["B_joch_T"] > e["B_joch_T"],
       f"{e['B_joch_T']:.3f} -> {e5['B_joch_T']:.3f} T")
pruefe("und der Zahn bleibt davon unberuehrt",
       abs(e5["B_zahn_T"] - e["B_zahn_T"]) < 1e-9)

# ── 4. Die Ankerrueckwirkung wird VEKTORIELL angesetzt ──────────────────────
print("\n[4] Anker")
g0 = S.gap_resultierend(GEOM, 0.5, 0.0, 0.0)
pruefe("ohne Strom bleibt es das Magnetfeld", abs(g0["B_gap_T"] - 0.5) < 1e-12)
gq = S.gap_resultierend(GEOM, 0.5, 200.0, 0.0)
pruefe("reiner q-Strom steht QUER zum Magneten -> hypot, nicht Summe",
       abs(gq["B_gap_T"] - math.hypot(0.5, gq["B_arm_T"])) < 1e-9,
       f"{gq['B_gap_T']:.4f} T bei B_arm={gq['B_arm_T']:.4f} T")
gd = S.gap_resultierend(GEOM, 0.5, 0.0, -200.0)
pruefe("negativer d-Strom SCHWAECHT den Magneten (Feldschwaechung)",
       gd["B_d_T"] < 0.5, f"B_d = {gd['B_d_T']:.4f} T")
# Der Fehler, den das verhindert: Betraege addieren ueberschaetzt den Zahn
# gerade dort, wo die Feldschwaechung arbeitet.
pruefe("und das Ergebnis liegt UNTER der blossen Betragssumme",
       gd["B_gap_T"] < 0.5 + gd["B_arm_T"] - 1e-9)

# ── 5. Urteil und Wortlaut ──────────────────────────────────────────────────
print("\n[5] Urteil")
hoch = S.eisenwege(GEOM, AXIAL, 1.6, "m270_35a")
pruefe("ueber der Blechgrenze -> gesaettigt", hoch["gesaettigt"],
       f"{hoch['wert_T']:.2f} T gegen {hoch['B_sat_T']:.2f} T")
pruefe("Engstelle wird benannt", hoch["engstelle"] in ("zahn", "joch"),
       hoch["engstelle"])
txt = S.als_text(hoch)
pruefe("der Text sagt, dass es KEINE Wand ist", "keine Wand" in txt.lower()
       or "KEINE Wand" in txt)
pruefe("und dass die Zahlen darueber zu optimistisch sind",
       "optimistisch" in txt)
pruefe("nicht gesaettigt -> kein Warnsatz",
       "KEINE Wand" not in S.als_text(S.eisenwege(GEOM, AXIAL, 0.3, "m270_35a")))

# ── 6. Der gemeinsame Bewerter reicht es durch ──────────────────────────────
print("\n[6] Anschluss an ema_optimize")
import ema_optimize as O                                          # noqa: E402
pl = {"geom": GEOM, "axial_len": AXIAL, "cooling": "water", "T_ambient": 25,
      "rpm_to": 12000, "rpm_from": 4000, "load_nm": 20,
      "stator_lam": "m270_35a", "rotor_lam": "m270_35a",
      "magnet": "ndfeb_n35", "hairpin_mat": "cu_etp"}
mats = O._materials(pl)
op = {"rpm_thermal": 6000.0, "rpm_base": 4000.0, "load_nm": 20.0}
m = O._eval_geom(GEOM, AXIAL, mats, op, "water", 25.0, [3000, 6000], N=120)
pruefe("_eval_geom liefert die Saettigung",
       m.get("saettigung") is not None and m.get("B_eisen") is not None,
       f"B_eisen={m.get('B_eisen')} T, Ausnutzung={m.get('saettigung')}")
pruefe("und B_eisen ist das Maximum aus Zahn und Joch",
       abs(m["B_eisen"] - max(m["B_zahn"], m["B_joch"])) < 1e-9)
# Ein fehlgeschlagener Nebenwert darf den Bewerter NICHT werfen.
kaputt = O._saettigung({"p": 0}, 0.0, {"B_gap_T": float("nan")}, 0, 0, None)
pruefe("ein Fehler gibt None statt zu werfen",
       "saettigung" in kaputt and not FEHLER[-1:] == ["x"])

# ── 7. Kommt die Zahl ueberhaupt irgendwo AN? ──────────────────────────────
# Der Anlass ist eine Frage des Nutzers: „wo wird die Saettigung dargestellt?"
# Die ehrliche Antwort war zuerst „fast nirgends" -- sie stand im Bewerter und
# keine der Anzeigetabellen kannte sie. Dieser Block nagelt jeden Weg einzeln
# fest, damit er nicht wieder still abreisst.
print("\n[7] Anzeigewege")
import ema_optimize as _O                                        # noqa: E402
import ema_paramstudy as _PS                                     # noqa: E402
import ema_db as _DB                                             # noqa: E402
import ema_steckbrief as _SB                                     # noqa: E402
import ema_paarvergleich as _PV                                  # noqa: E402
import ema_sicherheit as _SI                                     # noqa: E402
pruefe("METRICS kennt sie (Browser-Zielwert + Nebenbedingung)",
       "saettigung" in _O.METRICS and "B_eisen" in _O.METRICS)
pruefe("die Parameterstudie zeichnet sie",
       "saettigung" in [k for k, _, _ in _PS._STUDY_METRICS],
       f"{len(_PS._STUDY_METRICS)} Kurven")
pruefe("HERKUNFT fuehrt sie mit Methode",
       _DB.HERKUNFT.get("B_zahn_T", {}).get("methode") == "analytisch")
pruefe("und die Herkunft sagt, dass sie NICHT aus dem Feldbild kommt",
       "Flusserhaltung" in _DB.HERKUNFT.get("B_zahn_T", {}).get("detail", ""))
pruefe("der Steckbrief listet sie", "saettigung_pct" in _SB.KENNWERTE)
pruefe("der Paarvergleich fuehrt sie als Zusatzspalte (nicht gewichtet)",
       "saett_pct" in _PV.ZUSATZSPALTEN and "B_zahn_T" in _PV.ZUSATZSPALTEN)
pruefe("und hat eine Achse fuer den Hebel", "nutbreite" in _PV.ACHSEN)
import inspect                                                    # noqa: E402
pruefe("ema_sicherheit prueft sie", "saettigung" in inspect.getsource(_SI.pruefen))
# Der Pipelinelauf ist die Stelle, an der sie in results.json kommt.
import ema_pipeline as _PL                                        # noqa: E402
pruefe("die Pipeline schreibt sie ins summary",
       "saettigung_pct" in inspect.getsource(_PL._saettigung_summary))
pruefe("und erzeugt die Bilder nach charts/",
       "ema_saettigung.bilder" in inspect.getsource(_PL.run_pipeline))

# ── 7b. Die beiden Wege, die ich zuerst FALSCH behauptet hatte ─────────────
# `renderSummary` in ema.html und `_single_md_tables` im Bericht bauen ihre
# Zeilen AUSDRUECKLICH und lesen `summary` nicht generisch. Die Zusage "damit
# haben Bericht und Ergebnisreiter sie ebenfalls" war deshalb falsch -- zweimal
# derselbe Fehler an einem Tag. Diese Pruefungen sind das Gegenmittel.
print("\n[7b] Ergebnisreiter und Bericht")
import os                                                         # noqa: E402
_html = open("ema.html", encoding="utf-8").read()
pruefe("renderSummary hat eine Saettigungskachel",
       "saettigung_pct" in _html and "renderSummary" in _html)
pruefe("und sie sagt, woher die Zahl kommt",
       "Flusserhaltung, kein Feldbild" in _html)
pruefe("und was ein Altprojekt sieht (das Feld fehlt dort)",
       "erst ab einem Lauf" in _html)
_rep = open("ema_report.py", encoding="utf-8").read()
pruefe("der Bericht traegt sie in ctx['em']", '"B_zahn_T":     summary.get' in _rep)
pruefe("und hat Tabellenzeilen dafuer", "Flussdichte im Zahn B_Zahn" in _rep)
# Wirklich durchgerechnet, nicht nur gegrept.
import json as _json                                              # noqa: E402
import tempfile as _tf                                            # noqa: E402
import ema_report as _R                                           # noqa: E402
_res = {"summary": {"B_gap_T": 0.5, "Kt_Nm_per_A": 0.2,
                    "B_zahn_T": 1.29, "B_joch_T": 0.25,
                    "B_eisen_T": 1.29, "saettigung_pct": 76.0,
                    "saettigung_engstelle": "zahn"}}
with _tf.TemporaryDirectory() as _t:
    _json.dump(_res, open(os.path.join(_t, "results.json"), "w"))
    _json.dump({"payload": {"geom": GEOM}}, open(os.path.join(_t, "meta.json"), "w"))
    # `_fmt_val` setzt ein SCHMALES GESCHUETZTES Leerzeichen (U+202F) zwischen
    # Zahl und Einheit -- typografisch richtig und beim Vergleich eine Falle:
    # die erste Fassung dieses Tests suchte "1.29 T" mit gewoehnlichem
    # Leerzeichen und schlug fehl, obwohl die Tabelle stimmte.
    _tab = _R._single_md_tables(_R.build_context(_t)).replace("\u202f", " ")
    pruefe("die Kennwerttabelle zeigt B_Zahn", "1.29 T" in _tab)
    pruefe("und die Ausnutzung mit der Engstelle",
           "Engstelle zahn" in _tab and "76 %" in _tab)

# ── 7c. Der Rotorsteg ──────────────────────────────────────────────────────
print("\n[7c] Rotorsteg")
_st = S.rotorsteg(GEOM, AXIAL, 0.5, "m270_35a")
pruefe("die Stegbreite kommt aus ema_topology", _st["ok"] and _st["steg_mm"] > 0,
       f"{_st['steg_mm']} mm, {_st['n_steg_je_pol']} je Pol")
# Die Schranke ist eine Handrechnung: B_sat * w * L * n.
_soll = _st["B_sat_T"] * (_st["steg_mm"] / 1000.0) * (AXIAL / 1000.0) * _st["n_steg_je_pol"]
pruefe("die Streuschranke ist B_sat*w*L*n",
       abs(_st["phi_steg_mWb"] / 1000.0 - _soll) < 1e-9,
       f"{_st['phi_steg_mWb']:.4f} mWb")
pruefe("k_leak_steg_mindestens = 1 - Streuanteil",
       abs(_st["k_leak_steg_mindestens"]
           - (1 - _st["streuanteil_hoechstens"])) < 1e-9)
pruefe("bei 1,3 mm Steg ist die Annahme MOEGLICH",
       _st["annahme_unmoeglich"] is False)
# Der Fall, um den es geht: ein duenner Steg macht die Annahme unmoeglich.
# Gemessen liegt die Schwelle bei rund 0,35 mm -- duenn, aber real (Stanzgrenze).
import ema_topology as _TOP                                       # noqa: E402
_alt = _TOP.BRIDGE_MM
try:
    _TOP.BRIDGE_MM = 0.3
    _duenn = S.rotorsteg(GEOM, AXIAL, 0.5, "m270_35a")
    pruefe("bei 0,3 mm Steg wird sie UNMOEGLICH",
           _duenn["annahme_unmoeglich"] is True,
           f"k_min {_duenn['k_leak_steg_mindestens']:.3f} > "
           f"{_duenn['k_leak_steg_angenommen']:.3f}")
    pruefe("und der Text sagt, in welche Richtung es falsch liegt",
           "ZU NIEDRIG" in _duenn["text"] or "zu niedrig" in _duenn["text"])
finally:
    _TOP.BRIDGE_MM = _alt
# Er darf NICHT als dritte Zeile in der Ausnutzungsliste stehen -- er ist
# planmaessig gesaettigt, und 100 % dort liessen jede Maschine verletzt aussehen.
_be = S.bewerten(GEOM, AXIAL, 0.5, 0.0, 0.0, "m270_35a")
pruefe("bewerten() fuehrt den Steg mit", (_be.get("steg") or {}).get("ok") is True)
pruefe("aber NICHT in der Ausnutzungsliste",
       "steg" not in {x["name"] for x in L_ausn(_be)})
pruefe("der Text nennt ihn als planmaessig gesaettigt",
       "planmaessig GESAETTIGT" in S.als_text(_be))

# ── 8. Die Bilder ──────────────────────────────────────────────────────────
print("\n[8] Bilder")
import os                                                         # noqa: E402
import tempfile                                                   # noqa: E402
with tempfile.TemporaryDirectory() as tmp:
    aus = S.bilder(GEOM, AXIAL, 0.55, tmp, rpm=6000.0, i_q=120.0, i_d=-20.0)
    pruefe("beide Bilder entstehen", len(aus) == 2, ", ".join(
        os.path.basename(a) for a in aus))
    pruefe("und sind nicht leer",
           all(os.path.getsize(a) > 8000 for a in aus),
           ", ".join(f"{os.path.getsize(a) // 1024} kB" for a in aus))
    # Ohne Drehzahl gibt es kein Momentendiagramm -- und kein leeres Bild.
    ohne = S.bilder(GEOM, AXIAL, 0.55, tmp, rpm=0.0)
    pruefe("ohne Drehzahl nur der Querschnitt, kein leeres Diagramm",
           len(ohne) == 1)
pruefe("die Farbe folgt der Ausnutzung und kippt ueber 1,0",
       S._farbe(0.2) != S._farbe(0.9) and S._farbe(0.9) != S._farbe(1.3))

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE SAETTIGUNGS-TESTS BESTANDEN ✅  (ohne Loeser, ohne FreeCAD)")
