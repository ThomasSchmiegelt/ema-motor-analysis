"""Live-Vorschau: rechnet sie die GEZEICHNETE Maschine? (``ema.html`` + Route)

Bis zum 13.09.2026 nicht. ``PHYS`` trug feste Werte -- ``Psi 0,09``,
``Ld 0,3 mH``, ``Lq 0,8 mH``, 800 V --, und die Stromgrenze (800 A), die
Eckdrehzahl (5000) und das d/q-Verhaeltnis (-0,4) standen als Literale im
Quelltext. Das FELDBILD der Vorschau nutzte die gezeichnete Geometrie, das
dq-Modell darueber eine erfundene Maschine; gemessen lag Ld um Faktor 18
daneben.

Der Kern dieses Tests ist der **Spiegel**: die MTPA-Formel steht notgedrungen
zweimal -- die Vorschau rechnet sechzig Mal je Sekunde und kann nicht fragen.
Also wird die JS-Fassung mit ``node`` ausgefuehrt und gegen die Python-Fassung
gehalten, so wie ``test_topology.py`` es fuer ``magnetLegs`` tut.
"""
import json
import math
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, ".")

FEHLER = []
HTML = open("ema.html", encoding="utf-8").read()


def pruefe(name, bed, zusatz=""):
    print(f"  {'✓' if bed else '✗'} {name}" + (f"  {zusatz}" if zusatz else ""))
    if not bed:
        FEHLER.append(name)


# ── 1. Die Festwerte sind weg ───────────────────────────────────────────────
print("\n[1] Keine Literale mehr im Regelkreis")
blk = HTML[HTML.index("function stepPhysics()"):]
blk = blk[:blk.index("PHYS.torque =")]
pruefe("die Stromgrenze kommt aus PHYS.iMax", "PHYS.iMax" in blk)
pruefe("und nicht mehr als 800 aus dem Quelltext", ", 800)" not in blk)
pruefe("die Eckdrehzahl kommt aus PHYS.rpmBase", "PHYS.rpmBase" in blk)
pruefe("und nicht mehr als 5000", "> 5000" not in blk)
pruefe("d/q kommt aus MTPA, nicht aus -0.4",
       "_mtpaId(" in blk and "-0.4*tiq" not in blk)

# ── 2. Der Spiegel: dieselbe MTPA-Formel in JS und Python ───────────────────
print("\n[2] MTPA-Spiegel JS ↔ Python")
m = re.search(r"// <<MTPA-START>>(.*?)// <<MTPA-END>>", HTML, re.S)
pruefe("der markierte Block existiert", bool(m))
if m:
    faelle = [(0.0248, 1.67e-5, 3.58e-5, iq) for iq in (0, 1, 50, 200, 800)]
    faelle += [(0.09, 3e-4, 8e-4, 300.0),          # der alte Festwert-Satz
               (0.05, 2e-4, 2e-4, 400.0),          # nicht salient: dL = 0
               (0.0, 1e-5, 5e-5, 100.0)]           # ohne Magnet
    js = m.group(1) + "\nconst F=" + json.dumps(faelle) + ";\n" \
         "console.log(JSON.stringify(F.map(a=>_mtpaId(a[0],a[1],a[2],a[3]))));"
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(js)
        pfad = f.name
    try:
        aus = subprocess.run(["node", pfad], capture_output=True, text=True,
                             timeout=30)
        got = json.loads(aus.stdout.strip())
    finally:
        os.unlink(pfad)

    def py_mtpa(psi, Ld, Lq, iq):
        """Wortgleich der Ausdruck aus estimate_dq_currents (ema_analysis:1345)."""
        dL = Lq - Ld
        if not (dL > 1e-12) or not (psi > 0):
            return 0.0
        return (psi - math.sqrt(psi ** 2 + 8.0 * dL ** 2 * iq ** 2)) / (4.0 * dL)

    soll = [py_mtpa(*a) for a in faelle]
    schlimm = max(abs(g - s) for g, s in zip(got, soll))
    pruefe("alle acht Faelle stimmen ueberein", schlimm < 1e-12,
           f"groesste Abweichung {schlimm:.2e}")
    pruefe("und der salient Fall gibt wirklich einen NEGATIVEN d-Strom",
           soll[3] < -1.0, f"iq=200 A -> i_d={soll[3]:.1f} A")
    pruefe("nicht salient (dL=0) gibt exakt 0", soll[6] == 0.0)

# ── 3. Die Bedienung ────────────────────────────────────────────────────────
print("\n[3] Bedienung")
pruefe("es gibt den Knopf", "livePhysikLaden()" in HTML)
pruefe("und den Ausfallschalter", 'id="chk_modul_aus"' in HTML)
pruefe("PHYS merkt sich, ob die Werte ECHT sind", "echt: false" in HTML)
pruefe("die Anzeige warnt, solange sie es nicht sind",
       "FESTWERTE" in HTML)
pruefe("das ausgefallene System fuehrt keinen Strom",
       "PHYS.ausfallSystem >= 0 && PHYS.sysJeNut" in HTML)
pruefe("ohne mehrere Module gibt es keinen n-1-Fall",
       "PHYS.kModule > 1) ? 0 : -1" in HTML)

# ── 4. Die Route liefert, was die Vorschau braucht ──────────────────────────
print("\n[4] Route")
SRV = open("server.py", encoding="utf-8").read()
for k in ("psi_pm_Wb", "Ld_H", "Lq_H", "rpm_base", "i_max_A", "n_module"):
    pruefe(f"/umrichter gibt {k} heraus", f'"{k}"' in SRV)
pruefe("und die Nutzuordnung (statt sie in JS nachzubauen)",
       "system_je_nut" in SRV and "system_je_nut" in HTML)
pruefe("xi wird unter dem RICHTIGEN Schluessel gelesen",
       'adv.get("xi")' in SRV and 'adv.get("xi_LqLd")' not in SRV)
pruefe("die Eckdrehzahl wird gerechnet, nicht geraten",
       "_rpm_base_von" in SRV)

# ── 5. Gegen die echte Maschine -- mit Loeser, aber ohne Server ─────────────
print("\n[5] Die Zahlen der Probemaschine")
_p = os.path.expanduser("~/cae_projekte/20260913_201143_saettigungsprobe/meta.json")
if os.path.exists(_p):
    import ema_analysis as EA
    pl = json.load(open(_p, encoding="utf-8"))["payload"]
    g = pl["geom"]
    ax = float(pl.get("axial_len") or 80.0)
    em = EA.run_em_analysis(g, N=140, rotor_angle=0.0, axial_mm=ax)
    adv = EA.compute_advanced_em(g, em["performance"], ax, 600.0, 18500.0, 40.0)
    # Der eigentliche Punkt: die Festwerte lagen NICHT nur ein bisschen daneben.
    pruefe("Ld der Maschine weicht stark vom alten Festwert 0,3 mH ab",
           abs(adv["Ld_mH"] / 0.3 - 1) > 0.5,
           f"{adv['Ld_mH']:.4f} mH statt 0,3 mH")
    pruefe("psi ebenso (Festwert war 0,09 Wb)",
           abs(adv["psi_pm_Wb"] / 0.09 - 1) > 0.3,
           f"{adv['psi_pm_Wb']:.4f} Wb")
    pruefe("xi ist wirklich > 1 (salient)", adv["xi"] > 1.2, f"ξ={adv['xi']:.2f}")
else:
    print("   (Probeprojekt nicht da — uebersprungen)")

print()
if FEHLER:
    print(f"FEHLGESCHLAGEN ({len(FEHLER)}): " + ", ".join(FEHLER))
    sys.exit(1)
print("ALLE LIVE-SIM-TESTS BESTANDEN ✅")
