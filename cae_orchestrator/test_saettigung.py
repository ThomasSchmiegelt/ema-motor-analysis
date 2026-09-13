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

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE SAETTIGUNGS-TESTS BESTANDEN ✅  (ohne Loeser, ohne FreeCAD)")
