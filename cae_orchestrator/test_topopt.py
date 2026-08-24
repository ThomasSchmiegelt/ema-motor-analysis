"""Tests fuer die Topologieoptimierung (ema_topopt).

Das Verfahren hat beim Bau zwei Fehler gemacht, die beide plausibel aussahen und
falsch waren. Beide sind hier festgenagelt:

1. **Dichte muss mit der Steifigkeit sinken.** Der erste Entwurf hat je Element den
   E-Modul gesenkt und die Dichte stehen lassen. Bei einer Volumenlast ist das
   sinnlos: volle Masse haengt an weichem Material, die steifen Reste tragen alles.
   Gemessen kam eine Spitzenspannung von 1822 MPa gegen eine Fliessgrenze von
   340 MPa heraus. Der Test prueft direkt, dass die Fliehkraft mit rho skaliert.
2. **Die Regelung muss multiplikativ sein.** Additiv geregelt und mit sigma/rho auf
   das Vollmaterial zurueckgerechnet, springen die Dichten zwischen 0,001 und 1
   (gemessen: max_aenderung ~0,9 ueber 40 Iterationen ohne Konvergenz). Der Test
   verlangt, dass die Aenderung faellt und das Verfahren VOR dem Iterationsdeckel
   stehen bleibt.

Dazu die Sperrbereiche — ohne sie rechnet das Verfahren die Flusspfade weg.

Lauf: ``python test_topopt.py``   (braucht gmsh und ccx)
"""

import math
import os
import sys
import tempfile

import ema_deck as D
import ema_topopt as T

_fails = []
_uebersprungen = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _fails.append(name)


def ueberspringe(name, warum):
    print(f"  – {name}  ({warum})")
    _uebersprungen.append(name)


GEOM = {"p": 3, "rotorOD": 188.6, "shaftD": 60.0, "axialLen": 40.0,
        "magShape": "v", "magDepthRel": 0.30, "magThick": 8.0, "magWidth": 30.0,
        "magDist": 18.0, "magAngle": 100.0, "magGapMm": 0.1, "magLayers": 1,
        "magLayerGap": 12.0, "magOrient": "transverse", "magAsym": 0.0,
        "magTangLen": 0.0, "poleArcFrac": 0.83, "segPerPole": 6}
MAT  = {"label": "Pruefstahl", "density": 7650.0, "E": 200000.0, "nu": 0.30,
        "yield_mpa": 340.0}
RPM  = 18000.0
MESH = 9.0


def _netz():
    return D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=1)


def test_dichtekopplung():
    print("1. Weiches Material ist auch leichtes Material")
    n = _netz()
    voll = D.zentrifugal_lasten(n, MAT["density"], RPM)
    halb = D.zentrifugal_lasten(n, MAT["density"], RPM,
                                rho_je_element={e: 0.5 for e in n.elemente})
    sv = sum(math.hypot(f[0], f[1]) for f in voll.values())
    sh = sum(math.hypot(f[0], f[1]) for f in halb.values())
    check(f"rho=0,5 halbiert die Fliehkraft ({sh/sv:.6f})", abs(sh / sv - 0.5) < 1e-9)

    leer = D.zentrifugal_lasten(n, MAT["density"], RPM,
                                rho_je_element={e: 0.0 for e in n.elemente})
    check("rho=0 traegt keine Last",
          all(abs(f[0]) < 1e-12 and abs(f[1]) < 1e-12 for f in leer.values()))

    # Und im geschriebenen Satz muss BEIDES stehen: kleineres E und kleinere Dichte.
    with tempfile.TemporaryDirectory() as d:
        rho = {e: (0.2 if e % 2 else 1.0) for e in n.elemente}
        t = open(D.schreibe_inp(n, MAT, RPM, os.path.join(d, "r.inp"),
                                rho_je_element=rho)).read()
        z = t.splitlines()
        dichten, module = [], []
        for i, zeile in enumerate(z):
            if zeile == "*DENSITY":
                dichten.append(float(z[i + 1]))
            if zeile == "*ELASTIC":
                module.append(float(z[i + 1].split(",")[0]))
        check(f"zwei verschiedene Dichten im Satz ({len(set(dichten))})",
              len(set(dichten)) == 2, str(sorted(dichten)))
        check(f"zwei verschiedene E-Moduln im Satz ({len(set(module))})",
              len(set(module)) == 2, str(sorted(module)))
        check("E und Dichte laufen im gleichen Verhaeltnis",
              abs(min(module) / max(module) - min(dichten) / max(dichten)) < 1e-6,
              f"E {min(module)/max(module):.4f} gegen rho {min(dichten)/max(dichten):.4f}")


def test_sperrbereiche():
    print("2. Sperrbereiche — ohne sie verschwinden die Flusspfade")
    n = _netz()
    fest = T.sperrbereiche(n, GEOM, bohrung_mm=3.0, rand_mm=2.0, tasche_mm=1.5)
    check(f"es gibt Sperrbereiche ({len(fest)} von {n.n_elemente})",
          0 < len(fest) < n.n_elemente)
    # JEDES gesperrte Element muss seinen Grund tragen: Bohrung, Rand oder Tasche.
    from ema_topology import leg_records, magnet_legs
    recs = [rr for rr in leg_records(magnet_legs(GEOM)[0])
            if rr["placement"] == "interior"]
    schritt = 2 * math.pi / n.poles
    ohne_grund, an_tasche = [], 0
    for eid in fest:
        x, y, _z = D.element_mitte(n, eid)
        r = math.hypot(x, y)
        if r - n.r_shaft <= 3.0 or n.r_rot - r <= 2.0:
            continue
        phi = math.atan2(y, x)
        lokal = phi - round(phi / schritt) * schritt
        lx, ly = r * math.cos(lokal), r * math.sin(lokal)
        if any(T._abstand_rechteck(lx, ly, rc) <= 1.5 for rc in recs):
            an_tasche += 1
        else:
            ohne_grund.append(eid)
    check(f"jedes gesperrte Element hat einen Grund "
          f"({an_tasche} an Taschen, {len(ohne_grund)} ohne)", not ohne_grund,
          f"grundlos gesperrt: {ohne_grund[:5]}")
    check(f"es sind wirklich Taschensaeume dabei ({an_tasche})", an_tasche > 0)
    # Und kein FREIES Element darf einen der drei Gruende erfuellen.
    frei_falsch = []
    for eid in set(n.elemente) - fest:
        x, y, _z = D.element_mitte(n, eid)
        r = math.hypot(x, y)
        if r - n.r_shaft <= 3.0 or n.r_rot - r <= 2.0:
            frei_falsch.append(eid)
    check(f"kein freies Element liegt an Bohrung oder Rand", not frei_falsch,
          f"{frei_falsch[:5]}")
    # Ein groesserer Saum muss MEHR sperren — sonst greift der Parameter nicht.
    weit = T.sperrbereiche(n, GEOM, bohrung_mm=3.0, rand_mm=2.0, tasche_mm=6.0)
    check(f"groesserer Taschensaum sperrt mehr ({len(fest)} -> {len(weit)})",
          len(weit) > len(fest))
    check("der kleinere Saum ist im groesseren enthalten", fest <= weit)


def test_sko_konvergiert():
    print("3. SKO konvergiert und haelt die Sperrbereiche")
    if not os.path.isfile(D.CCX_CMD):
        return ueberspringe("SKO-Lauf", "kein ccx")
    n = _netz()
    with tempfile.TemporaryDirectory() as d:
        r = T.sko(n, GEOM, MAT, RPM, d, iterationen=25)
        v = r["verlauf"]
        check(f"vor dem Deckel stehen geblieben ({len(v)} von 25 Iterationen)",
              len(v) < 25, "sonst konvergiert das Verfahren nicht")
        check(f"Aenderung faellt ({v[0]['max_aenderung']:.4f} -> "
              f"{v[-1]['max_aenderung']:.4f})",
              v[-1]["max_aenderung"] < v[0]["max_aenderung"] / 5)
        check(f"Volumenanteil sinkt ({v[0]['volumenanteil']:.3f} -> "
              f"{v[-1]['volumenanteil']:.3f})",
              v[-1]["volumenanteil"] < v[0]["volumenanteil"])

        fest = set(r["sperrbereiche"])
        check("Sperrbereiche behalten rho = 1 EXAKT",
              all(r["dichte"][e] == 1.0 for e in fest))
        check("im freien Bereich wurde wirklich Material weich",
              min(r["dichte"][e] for e in n.elemente if e not in fest) < 0.5)
        check("keine Dichte unter der unteren Schranke",
              min(r["dichte"].values()) >= T.E_MIN_REL - 1e-12)
        check("keine Dichte ueber 1", max(r["dichte"].values()) <= 1.0 + 1e-12)

        # Die Spitzenspannung darf nicht davonlaufen — das war der Dichtefehler.
        spitze = max(z["stress_peak_MPa"] for z in v)
        check(f"Spitzenspannung bleibt im Rahmen ({spitze:.0f} MPa gegen "
              f"Fliessgrenze {MAT['yield_mpa']:.0f})", spitze < 3 * MAT["yield_mpa"],
              "bei fehlender Dichtekopplung waren es 1822 MPa")

        # Alles muss JSON-schreibbar sein — gmsh liefert numpy-Zahlen, und die
        # kaeme der stdlib-Kodierer erst beim Speichern von results.json nicht ueber.
        import json
        try:
            json.dumps({"verlauf": v,
                        "dichte": {str(k): val for k, val in r["dichte"].items()}})
            check("Ergebnis ist JSON-schreibbar (keine numpy-Zahlen)", True)
        except TypeError as e:
            check("Ergebnis ist JSON-schreibbar (keine numpy-Zahlen)", False, str(e))


def test_ableseempfehlung():
    print("4. Ableseempfehlung rechnet auf die Parametrik zurueck")
    n = _netz()
    fest = T.sperrbereiche(n, GEOM)
    # Kuenstliches Feld: aussen voll, innen leer — die Empfehlung muss das finden.
    dichte = {}
    for eid in n.elemente:
        x, y, _z = D.element_mitte(n, eid)
        rel = (math.hypot(x, y) - n.r_shaft) / (n.r_rot - n.r_shaft)
        dichte[eid] = 1.0 if (eid in fest or rel > 0.6) else 0.05
    a = T.ableseempfehlung(n, GEOM, {"dichte": dichte, "sperrbereiche": sorted(fest)})
    check("ein Radialprofil kommt zurueck", len(a["radialprofil"]) > 5)
    check("der entlastete Bereich wird erkannt", "entlastet_von_mm" in a)
    if "entlastet_von_mm" in a:
        grenze = n.r_shaft + 0.6 * (n.r_rot - n.r_shaft)
        check(f"er liegt innen ({a['entlastet_bis_mm']:.1f} mm < {grenze:.1f} mm)",
              a["entlastet_bis_mm"] < grenze + 5.0)
    check("der Hinweis auf die Grenzen steht dabei",
          "kein Bauteil" in a["hinweis"] and "EM-Rechnung" in a["empfehlung"])


def test_filter():
    print("5. Der Dichtefilter mittelt ueber die Nachbarschaft")
    n = _netz()
    kante = T._kantenlaenge(n)
    nb = T._nachbarn(n, 2.0 * kante)
    check(f"jedes Element hat Nachbarn (typische Kante {kante:.2f} mm)",
          all(len(v) >= 1 for v in nb.values()))
    check("jedes Element ist sein eigener Nachbar",
          all(any(k == eid for k, _g in nb[eid]) for eid in list(nb)[:200]))
    # Ein Schachbrett muss deutlich glatter werden.
    schach = {e: (1.0 if e % 2 else 0.0) for e in n.elemente}
    glatt = T._filtere(schach, nb)
    spanne_v = max(schach.values()) - min(schach.values())
    spanne_n = max(glatt.values()) - min(glatt.values())
    check(f"Schachbrett wird geglaettet (Spanne {spanne_v:.2f} -> {spanne_n:.2f})",
          spanne_n < 0.8 * spanne_v)
    check("der Mittelwert bleibt ungefaehr erhalten",
          abs(sum(glatt.values()) / len(glatt)
              - sum(schach.values()) / len(schach)) < 0.05)


if __name__ == "__main__":
    for t in (test_dichtekopplung, test_sperrbereiche, test_sko_konvergiert,
              test_ableseempfehlung, test_filter):
        t()
    print()
    if _uebersprungen:
        print(f"uebersprungen: {len(_uebersprungen)}  ->  " + ", ".join(_uebersprungen))
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
