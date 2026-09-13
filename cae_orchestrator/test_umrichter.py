"""Mehrere Leistungselektroniken (``ema_umrichter.py``) -- ohne Loeser.

Die Wickelregel laesst sich gegen Faelle pruefen, deren Antwort man ausrechnen
kann (36 Nuten teilen sich durch 3k fuer k = 1,2,3,4,6 und fuer kein anderes
k ≤ 8), und die Aufteilung gegen die Invariante, um die es geht: **die
Durchflutung bleibt**.
"""
import os
import sys
import tempfile

sys.path.insert(0, ".")

import ema_analysis as EA
import ema_mobil
import ema_umrichter as U

FEHLER = []


def pruefe(name, bed, zusatz=""):
    print(f"  {'✓' if bed else '✗'} {name}" + (f"  {zusatz}" if zusatz else ""))
    if not bed:
        FEHLER.append(name)


GEOM = dict(ema_mobil.basis_geom(), statorOD=305.0, statorID=171.6,
            rotorOD=170.0, shaftD=120.0, shaftBoreD=110.0, slots=36, p=6,
            slotDepth=30.0, inverterVdc=800.0, inverterImax=800.0)

# ── 1. Vorgaben und Klemmen ─────────────────────────────────────────────────
print("\n[1] Vorgaben")
pruefe("ohne Angabe EIN Modul", U.anzahl({}) == 1)
pruefe("und verschachtelt", U.topologie({}) == "verschachtelt")
pruefe("geklemmt nach oben", U.anzahl({"inverterAnzahl": 99}) == U.ANZAHL_SPANNE[1])
pruefe("geklemmt nach unten", U.anzahl({"inverterAnzahl": 0}) == 1)
pruefe("Unsinn faellt auf 1 zurueck statt zu werfen",
       U.anzahl({"inverterAnzahl": "vier"}) == 1)
pruefe("unbekannte Topologie faellt auf die Vorgabe zurueck",
       U.topologie({"inverterTopologie": "sternfoermig"}) == "verschachtelt")

# ── 2. Die Wickelregel gegen ausrechenbare Faelle ───────────────────────────
print("\n[2] Wickelregel (36 Nuten, 12 Pole, q = 1)")
teilbar = [k for k in range(1, 9) if 36 % (3 * k) == 0]
pruefe("teilbar genau fuer k = 1,2,3,4,6", teilbar == [1, 2, 3, 4, 6], str(teilbar))
for k in (1, 2, 3, 4, 6):
    w = U.wickelbar(GEOM, k, "sektoriert")
    pruefe(f"k={k} sektoriert geht", w["ok"], f"{w['nuten_je_system']:.0f} Nuten/System")
for k in (5, 7, 8):
    w = U.wickelbar(GEOM, k, "sektoriert")
    pruefe(f"k={k} wird abgewiesen", not w["ok"])
    pruefe(f"  und nennt die moeglichen k", "moeglich waeren" in w["grund"],
           w["grund"][-28:])

# Der Sektor braucht zusaetzlich eine ganze Polzahl -- ein Fall, den die
# Nutteilbarkeit allein durchlaesst.
g8 = dict(GEOM, slots=24, p=5)          # 24/(3*4)=2 ✓ aber 10 Pole / 4 = 2,5
w8 = U.wickelbar(g8, 4, "sektoriert")
pruefe("Nuten teilbar, Pole aber nicht -> sektoriert abgewiesen", not w8["ok"],
       w8["grund"][:56])
pruefe("verschachtelt geht in genau diesem Fall trotzdem",
       U.wickelbar(g8, 4, "verschachtelt")["ok"])

# Der Versatz ist ein HINWEIS, kein Ausschluss -- die Unterscheidung war ein
# Fehler im ersten Entwurf (alle Befunde wurden nach dem Gesamturteil gefaerbt).
w4 = U.wickelbar(GEOM, 4, "verschachtelt")
pruefe("verschachtelt bei q=1 ist zulaessig", w4["ok"])
pruefe("aber ohne Versatz", w4["versatz_moeglich"] is False)
pruefe("und der Befund ist WEICH, kein Ausschluss",
       all(not b["hart"] for b in w4["befunde"]))
gq = dict(GEOM, slots=72)               # q = 72/(12*3) = 2
pruefe("bei q=2 ist Versatz fuer k=2 moeglich",
       U.wickelbar(gq, 2, "verschachtelt")["versatz_moeglich"] is True)

# ── 3. Zuordnung Nut -> System ──────────────────────────────────────────────
print("\n[3] Welche Nut gehoert wem")
sek = U.system_je_nut(36, 4, "sektoriert")
ver = U.system_je_nut(36, 4, "verschachtelt")
pruefe("sektoriert bildet BLOECKE", sek[:9] == [0] * 9 and sek[9:18] == [1] * 9)
pruefe("verschachtelt geht reihum", ver[:8] == [0, 1, 2, 3, 0, 1, 2, 3])
for z, name in ((sek, "sektoriert"), (ver, "verschachtelt")):
    pruefe(f"{name}: jedes System bekommt gleich viele Nuten",
           all(z.count(j) == 9 for j in range(4)))
pruefe("k=1 gibt alles einem System", set(U.system_je_nut(36, 1, "sektoriert")) == {0})

# ── 4. Die Aufteilung -- und die Invariante dahinter ────────────────────────
print("\n[4] Aufteilung")
z1 = U.zerlegung(GEOM, 10000.0)
pruefe("k=1: die Maschine sieht das Modul", abs(z1["v_maschine_V"] - 800.0) < 1e-9)
for k in (2, 4):
    zk = U.zerlegung(dict(GEOM, inverterAnzahl=k), 10000.0)
    pruefe(f"k={k}: Spannung mal {k}", abs(zk["v_maschine_V"] - 800.0 * k) < 1e-9,
           f"{zk['v_maschine_V']:.0f} V")
    pruefe(f"k={k}: Strom UNveraendert",
           abs(zk["i_maschine_A"] - z1["i_maschine_A"]) < 1e-9)
    pruefe(f"k={k}: Scheinleistung teilt sich auf {k} Module",
           abs(zk["S_gesamt_kVA"] - k * zk["S_modul_kVA"]) < 0.2,
           f"{zk['S_modul_kVA']:.0f} kVA je Modul")
# Rueckwaertskompatibilitaet ist hier eine Zusicherung: JEDE Altrechnung laeuft
# ueber `umrichter()`, und ein stiller Faktor dort verschoebe alles.
a = EA.umrichter(GEOM, 10000.0)
b = EA.umrichter(dict(GEOM, inverterAnzahl=1), 10000.0)
pruefe("ohne Angabe == k=1, Ziffer fuer Ziffer",
       a["v_dc_V"] == b["v_dc_V"] and a["i_max_1t"] == b["i_max_1t"]
       and a["v_dc_1t"] == b["v_dc_1t"])
pruefe("umrichter() meldet die Modulzahl und den Modulwert",
       EA.umrichter(dict(GEOM, inverterAnzahl=4), 0)["n_module"] == 4
       and abs(EA.umrichter(dict(GEOM, inverterAnzahl=4), 0)["v_modul_V"]
               - 800.0) < 1e-9)

# ── 5. n-1 ──────────────────────────────────────────────────────────────────
print("\n[5] Ausfall")
_echt = EA.power_envelope


def _stub(geom, adv, rpm_max, T_rated_Nm=0.0, v_dc=None, i_max=None, n_pts=80):
    """Gestellt: die Leistung soll schlicht mit der Spannungsgrenze gehen.

    Der Rueckfall auf `umrichter()[v_dc_1t]` bei `v_dc=None` ist nicht Zierde,
    sondern noetig: die ECHTE `power_envelope` tut genau das, und ein Stub, der
    statt dessen 1,0 einsetzt, vergleicht den Vollfall mit einer anderen
    Bezugsgroesse als den Ausfall — der erste Entwurf lieferte darum ein
    Verhaeltnis von 2400 statt 0,75.
    """
    v = v_dc if v_dc is not None else EA.umrichter(geom, rpm_max)["v_dc_1t"]
    return {"rpm": [0, rpm_max], "P_peak_kW": [0.0, 100.0 * v],
            "P_max_kW": 100.0 * v, "T_peak_Nm": [1.0, 1.0],
            "T_cont_Nm": [1.0, 1.0], "P_cont_kW": [0.0, 1.0]}


EA.power_envelope = _stub
try:
    aus = U.ausfall(dict(GEOM, inverterAnzahl=4), {}, 10000.0, 100.0)
    pruefe("3 von 4 bleiben", aus["rest_module"] == 3 and aus["k"] == 4)
    pruefe("der Anteil ist (k-1)/k", abs(aus["anteil"] - 0.75) < 1e-9)
    pruefe("und die Restleistung folgt ihm",
           abs(aus["P_rest_kW"] / aus["P_voll_kW"] - 0.75) < 1e-6,
           f"{aus['P_anteil']}")
    e1 = U.ausfall(GEOM, {}, 10000.0, 100.0)
    pruefe("bei EINEM Modul ist der Ausfall der Totalausfall",
           not e1["moeglich"] and "Totalausfall" in e1["grund"])
    pruefe("die sektorierte Warnung reist mit",
           "Magnetzug" in (U.ausfall(dict(GEOM, inverterAnzahl=2,
                                          inverterTopologie="sektoriert"),
                                     {}, 10000.0, 100.0)["warnung"] or ""))
finally:
    EA.power_envelope = _echt

# ── 6. Der Text sagt zuerst das Wichtigste ──────────────────────────────────
print("\n[6] Wortlaut")
t = U.als_text(U.zerlegung(dict(GEOM, inverterAnzahl=4), 10000.0))
pruefe("er sagt, dass Aufteilen nicht staerker macht", "NICHT staerker" in t)
pruefe("und was die Maschine sieht", "die Maschine sieht" in t)
pruefe("bei k=1 steht der Satz NICHT da (er waere sinnlos)",
       "NICHT staerker" not in U.als_text(U.zerlegung(GEOM, 10000.0)))

# ── 7. Bilder ───────────────────────────────────────────────────────────────
print("\n[7] Bilder")
with tempfile.TemporaryDirectory() as tmp:
    raus = U.bilder(dict(GEOM, inverterAnzahl=4, inverterTopologie="sektoriert"),
                    tmp, None)
    pruefe("der Querschnitt entsteht", len(raus) == 1
           and os.path.getsize(raus[0]) > 8000,
           f"{os.path.getsize(raus[0]) // 1024} kB")
    pruefe("ohne Ausfallrechnung KEIN leeres Diagramm",
           not os.path.exists(os.path.join(tmp, "umrichter_ausfall.png")))

# ── 8. Oberflaeche und Agenten ──────────────────────────────────────────────
print("\n[8] Anschluss")
_html = open("ema.html", encoding="utf-8").read()
for feld in ("inv_vdc", "inv_imax", "inv_anzahl", "inv_topologie", "inv_bezug"):
    pruefe(f"die Maske hat {feld}", f'id="{feld}"' in _html)
pruefe("buildPayload schreibt sie nach geom", "inverterAnzahl:" in _html)
pruefe("applyPayload holt sie zurueck (sonst erbt die Vorlage fremde Werte)",
       "_setField('inv_anzahl'" in _html)
pruefe("die Maske rechnet NICHT selbst, sie fragt den Server",
       "fetch('/umrichter'" in _html)
_srv = open("server.py", encoding="utf-8").read()
pruefe("und die Route gibt es", '@app.route("/umrichter"' in _srv)
_sk = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".agents",
                   "skills", "cae-orchestrator", "SKILL.md")
if os.path.exists(_sk):
    _t = open(_sk, encoding="utf-8").read()
    pruefe("SKILL.md nennt das Verb", "`umrichter`" in _t)
    pruefe("und sagt, dass Aufteilen nicht staerker macht",
           "nicht stärker" in _t or "NICHT stärker" in _t)

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE UMRICHTER-TESTS BESTANDEN ✅  (ohne Loeser, ohne FreeCAD)")
