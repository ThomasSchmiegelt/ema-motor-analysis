"""Tests fuer den eigenen Rechensatz (ema_deck) und den Z88-Pfad (ema_z88).

Beide Module sind neu und beide erzeugen Zahlen, die spaeter in ``results.json``
landen. Was hier geprueft wird und warum genau das:

* **Das Netz gegen OpenCASCADE.** Die Summe der Tet-Volumina wird gegen
  ``occ.getMass`` gestellt — eine voellig unabhaengige Rechnung im
  Geometriekern. Ein Netz, das die Taschen verfehlt oder den Sektor falsch
  schneidet, faellt hier auf, bevor irgendein Loeser laeuft.
* **Die Fliehkraft-Quadratur gegen die geschlossene Form.** Z88 kennt keine
  Rotationslast, die Knotenkraefte rechnet ``zentrifugal_lasten`` selbst. Der
  Test benutzt dafuer einen **taschenfreien** Ring, weil nur dort
  ``Integral rho w^2 r dV`` in geschlossener Form dasteht — so wird die Quadratur
  von der Geometrie getrennt gemessen.
* **Beide Loeser auf EINEM Netz.** Die Kernaussage des Vergleichs ist, dass
  CalculiX und Z88 dieselbe Zahl liefern. Der Test haelt das fest; laufen sie
  auseinander, ist ein Schreiber kaputt und nicht die Physik.
* **Die Starrkoerperfesseln.** Der volle Ring wird bewusst NICHT an der Bohrung
  eingespannt, sonst waere es ein anderes Problem als die analytische Formel.
  Der Test prueft, dass die drei Punktfesseln fast keine Kraft tragen.
* **Die Spaltenreihenfolge der .dat.** CalculiX schreibt dort
  ``sxx syy szz sxy sxz syz``, im .frd dagegen ``... sxy syz szx``. Ein
  vertauschtes Paar ergibt eine plausibel aussehende, falsche
  Vergleichsspannung — deshalb wird gegen das .frd gegengerechnet.

Lauf: ``python test_deck.py``        (braucht gmsh; ccx/z88 werden uebersprungen,
                                      wenn sie fehlen — mit Hinweis, nicht still)
"""

import math
import os
import shutil
import sys
import tempfile

import ema_deck as D
import ema_z88 as Z
from ema_rotorcheck import _bore_hoop_mpa

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


# Eine kleine, schnell vernetzbare Maschine. Grob genug fuer Sekunden, fein genug,
# dass die Taschen wirklich geschnitten werden.
GEOM = {"p": 3, "rotorOD": 188.6, "shaftD": 60.0, "axialLen": 60.0,
        "magShape": "v", "magDepthRel": 0.30, "magThick": 8.0, "magWidth": 30.0,
        "magDist": 18.0, "magAngle": 100.0, "magGapMm": 0.1, "magLayers": 1,
        "magLayerGap": 12.0, "magOrient": "transverse", "magAsym": 0.0,
        "magTangLen": 0.0, "poleArcFrac": 0.83, "segPerPole": 6}

# Derselbe Ring OHNE Magnete — fuer die Quadraturpruefung gegen die geschlossene Form.
GEOM_LEER = dict(GEOM, magShape="custom", customLegs=[])

MAT = {"label": "Pruefstahl", "density": 7650.0, "E": 200000.0, "nu": 0.30,
       "yield_mpa": 340.0}
RPM = 12000.0
MESH = 9.0


def test_netz_volumen():
    print("1. Netz: Tet-Volumen gegen OpenCASCADE")
    for sekt, name in ((1, "Polsektor"), (0, "Vollrotor")):
        n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=sekt)
        v_t, v_o = n.volumen_tets_mm3(), n.volumen_occ_mm3
        abw = abs(v_t - v_o) / v_o
        check(f"{name}: Volumen stimmt ({abw*100:.3f} %)", abw < 2e-3,
              f"Tets {v_t:.1f} mm^3 gegen OCC {v_o:.1f} mm^3")
        check(f"{name}: Knoten lueckenlos ab 1",
              sorted(n.knoten) == list(range(1, n.n_knoten + 1)))
        check(f"{name}: Elemente lueckenlos ab 1",
              sorted(n.elemente) == list(range(1, n.n_elemente + 1)))
        if sekt:
            check("Polsektor: Schnittflaechen paarweise zugeordnet",
                  len(n.paare) > 0 and len({a for a, _ in n.paare}) == len(n.paare),
                  f"{len(n.paare)} Paare")
        else:
            # Der volle Rotor muss genau ``poles`` mal so gross sein wie ein Sektor.
            s = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=1)
            v = abs(n.volumen_occ_mm3 - n.poles * s.volumen_occ_mm3) / n.volumen_occ_mm3
            check(f"Vollrotor = {n.poles} x Sektor ({v*100:.3f} %)", v < 1e-6)


def test_taschen_wirken():
    print("2. Die Magnettaschen werden wirklich geschnitten")
    voll = D.baue(GEOM_LEER, mesh_mm=MESH, ordnung=1, sektoren=1)
    mit  = D.baue(GEOM,      mesh_mm=MESH, ordnung=1, sektoren=1)
    anteil = 1.0 - mit.volumen_occ_mm3 / voll.volumen_occ_mm3
    check(f"Taschen entfernen Material ({anteil*100:.1f} %)", 0.02 < anteil < 0.5,
          f"leer {voll.volumen_occ_mm3:.0f} mm^3, mit Taschen {mit.volumen_occ_mm3:.0f} mm^3")
    # Der taschenfreie Ring muss dem analytischen Ringvolumen entsprechen.
    soll = (math.pi * (voll.r_rot**2 - voll.r_shaft**2) * voll.axial_len
            * voll.sektoren / voll.poles)
    check(f"leerer Sektor = analytisches Ringstueck "
          f"({abs(voll.volumen_occ_mm3-soll)/soll*100:.3f} %)",
          abs(voll.volumen_occ_mm3 - soll) / soll < 1e-6)


def test_fliehkraft_quadratur():
    print("3. Fliehkraft-Quadratur gegen die geschlossene Form (taschenfreier Ring)")
    for ordnung in (1, 2):
        et = f"Tet{4 if ordnung == 1 else 10}"
        n = D.baue(GEOM_LEER, mesh_mm=MESH, ordnung=ordnung, sektoren=0)
        lasten = D.zentrifugal_lasten(n, MAT["density"], RPM)
        # Die ordnungsunabhaengige Invariante: Sum f_i.x_i == Integral b.x dV.
        # Sum|f_i| taugt dafuer NICHT — bei Tet10 sind die Eckkraefte negativ.
        ist  = D.zentrifugal_arbeit(n, lasten)
        soll = D.zentrifugal_arbeit_analytisch(n, MAT["density"], RPM)
        abw  = abs(ist - soll) / soll
        check(f"{et}: Sum f.x trifft die Formel ({abw*100:.2f} %)",
              abw < 0.01, f"{ist:.1f} Nmm gegen {soll:.1f} Nmm")
        if ordnung == 1:
            summe = sum(math.hypot(f[0], f[1]) for f in lasten.values())
            s_soll = D.zentrifugal_summe_analytisch(n, MAT["density"], RPM)
            check(f"{et}: auch Sum|F| trifft (alle N_i >= 0) "
                  f"({abs(summe-s_soll)/s_soll*100:.2f} %)",
                  abs(summe - s_soll) / s_soll < 0.02)
        else:
            # Bei Tet10 zeigen die ECKkraefte nach innen und die KANTENkraefte nach
            # aussen (die klassische -1/20 / +1/5-Verteilung). Genau deshalb ist
            # Sum|f_i| als Pruefmass untauglich — das wird hier belegt, statt es
            # nur zu behaupten.
            ecken  = {i for ids in n.elemente.values() for i in ids[:4]}
            kanten = {i for ids in n.elemente.values() for i in ids[4:]} - ecken

            def radial(i):
                x, y, _z = n.knoten[i]
                r = math.hypot(x, y)
                f = lasten[i]
                return (f[0] * x + f[1] * y) / r if r > 1e-9 else 0.0

            e_neg = sum(1 for i in ecken if radial(i) < 0)
            k_pos = sum(1 for i in kanten if radial(i) > 0)
            check(f"{et}: Eckkraefte zeigen nach innen "
                  f"({e_neg}/{len(ecken)} = {100*e_neg/len(ecken):.0f} %)",
                  e_neg / len(ecken) > 0.8)
            check(f"{et}: Kantenkraefte zeigen nach aussen "
                  f"({k_pos}/{len(kanten)} = {100*k_pos/len(kanten):.0f} %)",
                  k_pos / len(kanten) > 0.95)
            summe_betrag = sum(math.hypot(f[0], f[1]) for f in lasten.values())
            s_soll = D.zentrifugal_summe_analytisch(n, MAT["density"], RPM)
            check(f"{et}: Sum|F| liegt darum DEUTLICH ueber dem Integral "
                  f"({summe_betrag/s_soll:.2f}-fach)", summe_betrag / s_soll > 1.2,
                  "sonst waere die obige Warnung gegenstandslos")
        # Am geschlossenen Ring muss sich die Fliehkraft aufheben.
        fx = sum(f[0] for f in lasten.values())
        fy = sum(f[1] for f in lasten.values())
        rest = math.hypot(fx, fy) / summe
        check(f"{et}: Resultierende hebt sich auf ({rest*100:.4f} %)", rest < 1e-3)
        check(f"{et}: keine Axialkraft",
              all(abs(f[2]) < 1e-9 for f in lasten.values()))


def test_fliehkraft_skaliert():
    print("4. Fliehkraft skaliert mit rpm^2")
    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=1)
    s1 = sum(math.hypot(f[0], f[1])
             for f in D.zentrifugal_lasten(n, MAT["density"], 5000.0).values())
    s2 = sum(math.hypot(f[0], f[1])
             for f in D.zentrifugal_lasten(n, MAT["density"], 10000.0).values())
    check(f"Verdopplung der Drehzahl vervierfacht die Last ({s2/s1:.4f})",
          abs(s2 / s1 - 4.0) < 1e-6)


def test_inp_form():
    print("5. Der CalculiX-Satz ist formal in Ordnung")
    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=1)
    with tempfile.TemporaryDirectory() as d:
        p = D.schreibe_inp(n, MAT, RPM, os.path.join(d, "r.inp"))
        text = open(p).read()
        zeilen = text.splitlines()
        check("genau ein *ELEMENT-Block", text.count("*ELEMENT,") == 1)
        check("Elementtyp C3D4", "TYPE=C3D4" in text)
        check("Fliehkraft als CENTRIF", ", CENTRIF," in text)
        check("zyklische Gleichungen vorhanden", "*EQUATION" in text)
        check("Integrationspunkt-Spannungen angefordert", "*EL PRINT" in text)
        n_el = sum(1 for z in zeilen
                   if z[:1].isdigit() and z.count(",") == 4)   # eid + 4 Knoten
        check(f"alle {n.n_elemente} Elemente geschrieben", n_el == n.n_elemente,
              f"gefunden {n_el}")
        # Kein Freiheitsgrad darf zugleich gefesselt und abhaengige Seite sein —
        # daran ist der erste Entwurf gescheitert.
        fest = set()
        i = zeilen.index("*BOUNDARY")
        for z in zeilen[i + 1:]:
            if z.startswith("*"):
                break
            t = [x.strip() for x in z.split(",")]
            if t[0].isdigit():
                fest.add((int(t[0]), int(t[1])))
        abhaengig = set()
        for k, z in enumerate(zeilen):
            if z == "*EQUATION":
                for zz in zeilen[k + 1:]:
                    if zz.startswith("*"):
                        break
                    t = [x.strip() for x in zz.split(",")]
                    if len(t) >= 3 and t[0].isdigit():
                        abhaengig.add((int(t[0]), int(t[1])))
        check("kein Freiheitsgrad zugleich gefesselt und MPC-abhaengig",
              not (fest & abhaengig), f"Ueberschneidung: {sorted(fest & abhaengig)[:3]}")


def test_ccx_loest():
    print("6. CalculiX loest den eigenen Satz")
    if not os.path.isfile(D.CCX_CMD):
        return ueberspringe("ccx-Lauf", f"kein ccx unter {D.CCX_CMD}")
    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=0)
    with tempfile.TemporaryDirectory() as d:
        D.schreibe_inp(n, MAT, RPM, os.path.join(d, "r.inp"))
        r = D.loese_ccx(os.path.join(d, "r.inp"))
        check("Lauf erfolgreich", r["solver_status"] == "OK", str(r)[:200])
        if r["solver_status"] != "OK":
            return
        sp = D.lies_dat_spannungen(r["dat"])
        check(f"Spannungen fuer alle {n.n_elemente} Elemente",
              len(sp) == n.n_elemente, f"gelesen {len(sp)}")
        k = D.kennzahlen(n, sp, MAT["yield_mpa"])
        a_m, b_m = n.r_shaft / 1e3, n.r_rot / 1e3
        w = 2 * math.pi * RPM / 60.0
        soll = _bore_hoop_mpa(a_m, b_m, MAT["density"], w, MAT["nu"] / (1 - MAT["nu"]))
        ist  = k["bore_hoop_median_MPa"]
        check(f"Ringspannung an der Bohrung nahe der Formel "
              f"({ist:.1f} gegen {soll:.1f} MPa, {100*(ist-soll)/soll:+.1f} %)",
              0.85 < ist / soll < 1.35,
              "Taschen heben sie an, aber nicht beliebig")
        # .dat gegen .frd: erkennt vertauschte Schubspalten
        from ema_pipeline import _parse_frd
        f = _parse_frd(r["frd"], yield_mpa=MAT["yield_mpa"])
        check(f"Mittelwert .dat ~ .frd ({k['stress_mean_MPa']:.1f} gegen "
              f"{f['mean_von_mises_MPa']:.1f} MPa)",
              abs(k["stress_mean_MPa"] - f["mean_von_mises_MPa"])
              / f["mean_von_mises_MPa"] < 0.25)


def test_z88_satz():
    print("7. Der Z88-Satz ist formal in Ordnung")
    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=0)
    with tempfile.TemporaryDirectory() as d:
        Z.schreibe_satz(n, MAT, RPM, d)
        for datei in ("z88i1.txt", "z88i2.txt", "z88i5.txt", "z88mat.txt",
                      "z88elp.txt", "z88int.txt", "z88man.txt", "z88.dyn"):
            check(f"{datei} geschrieben", os.path.isfile(os.path.join(d, datei)))
        kopf = open(os.path.join(d, "z88i1.txt")).readline().split()
        check("Z88I1-Kopf: IDIM NKP NE NFG KFLAG",
              len(kopf) == 5 and kopf[0] == "3" and kopf[4] == "0", str(kopf))
        check(f"NFG == 3 x NKP ({kopf[3]} == 3 x {kopf[1]})",
              int(kopf[3]) == 3 * int(kopf[1]))
        check(f"NKP/NE stimmen mit dem Netz ({n.n_knoten}/{n.n_elemente})",
              int(kopf[1]) == n.n_knoten and int(kopf[2]) == n.n_elemente)
        check("Elementtyp 17 (Tet4)",
              f" {D.Z88_TYP[1]}" in open(os.path.join(d, "z88i1.txt")).read())
        # Die Materialdatei: Leerzeichen, KEIN Komma — ein Komma ergibt still nue=0.
        werk = open(os.path.join(d, "z88werkstoff_0.txt")).read().strip()
        check(f"Materialdatei leerzeichengetrennt ({werk!r})",
              "," not in werk and len(werk.split()) == 2)
        check("Poissonzahl steht wirklich drin",
              abs(float(werk.split()[1]) - MAT["nu"]) < 1e-9)
        # Randbedingungszahl im Kopf muss zur Zeilenzahl passen
        z2 = open(os.path.join(d, "z88i2.txt")).read().splitlines()
        check(f"Z88I2-Kopfzahl passt ({z2[0].strip()} == {len(z2)-1})",
              int(z2[0]) == len(z2) - 1)
        # Der Sektor muss abgewiesen werden, statt still Unsinn zu rechnen.
        s = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=1)
        try:
            Z.schreibe_satz(s, MAT, RPM, os.path.join(d, "sekt"))
            check("Polsektor wird abgewiesen", False, "kein Fehler ausgeloest")
        except Z.Z88Fehler:
            check("Polsektor wird abgewiesen", True)


def test_beide_loeser():
    print("8. CalculiX und Z88 auf EINEM Netz — die Kernaussage")
    ok, warum = Z.verfuegbar()
    if not ok:
        return ueberspringe("Loeservergleich", warum)
    if not os.path.isfile(D.CCX_CMD):
        return ueberspringe("Loeservergleich", "kein ccx")

    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=0)
    with tempfile.TemporaryDirectory() as d:
        D.schreibe_inp(n, MAT, RPM, os.path.join(d, "r.inp"))
        rc = D.loese_ccx(os.path.join(d, "r.inp"))
        Z.schreibe_satz(n, MAT, RPM, os.path.join(d, "z88"))
        rz = Z.loese(os.path.join(d, "z88"), netz=n)
        check("beide Loeser durchgelaufen",
              rc["solver_status"] == "OK" and rz["solver_status"] == "OK",
              f"ccx={rc['solver_status']} z88={rz['solver_status']}")
        if rc["solver_status"] != "OK" or rz["solver_status"] != "OK":
            return

        k_c = D.kennzahlen(n, D.lies_dat_spannungen(rc["dat"]), MAT["yield_mpa"])
        k_z = D.kennzahlen(
            n, Z.spannungen_je_element(os.path.join(d, "z88", "z88o3.txt")),
            MAT["yield_mpa"])
        for schl in ("stress_mean_MPa", "stress_p99_MPa", "bore_hoop_median_MPa"):
            a, b = k_c[schl], k_z[schl]
            abw = abs(a - b) / abs(a)
            check(f"{schl}: ccx {a:.2f} ~ z88 {b:.2f} ({abw*100:.2f} %)", abw < 0.05)

        # Die Starrkoerperfesseln duerfen praktisch keine Kraft tragen.
        lasten = D.zentrifugal_lasten(n, MAT["density"], RPM)
        ges = sum(math.hypot(f[0], f[1]) for f in lasten.values())
        kr  = Z.lies_knotenkraefte(os.path.join(d, "z88", "z88o4.txt"))
        for kn, fg in D._ebene_fesseln(n):
            f = kr.get(kn, (0.0, 0.0, 0.0))
            anteil = math.hypot(f[0], f[1]) / ges
            check(f"Fessel an Knoten {kn} traegt fast nichts ({anteil*100:.4f} %)",
                  anteil < 1e-3)


def test_materialstufen():
    print("9. E-Modul je Element — der Zugang fuer die Topologieoptimierung")
    n = D.baue(GEOM, mesh_mm=MESH, ordnung=1, sektoren=0)
    e_je = {eid: (50000.0 if eid % 2 else 200000.0) for eid in n.elemente}
    stufen = D._materialstufen(n, MAT["E"], e_je, n_stufen=24)
    check(f"zwei Stufen erkannt ({len(stufen)})", len(stufen) == 2)
    check("jedes Element genau einer Stufe zugeordnet",
          sum(len(e) for _w, e in stufen) == n.n_elemente
          and len({eid for _w, e in stufen for eid in e}) == n.n_elemente)
    with tempfile.TemporaryDirectory() as d:
        p = D.schreibe_inp(n, MAT, RPM, os.path.join(d, "r.inp"), e_je_element=e_je)
        t = open(p).read()
        check("zwei *MATERIAL-Bloecke im .inp", t.count("*MATERIAL,") == 2)
        check("Eall bleibt fuer die Fliehkraft erhalten", "ELSET=Eall" in t)
        Z.schreibe_satz(n, MAT, RPM, os.path.join(d, "z88"), e_je_element=e_je)
        check("zwei Z88-Materialdateien",
              sum(1 for f in os.listdir(os.path.join(d, "z88"))
                  if f.startswith("z88werkstoff_")) == 2)
        mat_zeilen = open(os.path.join(d, "z88", "z88mat.txt")).read().splitlines()
        check(f"Z88MAT-Kopfzahl passt ({mat_zeilen[0].strip()} == {len(mat_zeilen)-1})",
              int(mat_zeilen[0]) == len(mat_zeilen) - 1)
        abgedeckt = set()
        for z in mat_zeilen[1:]:
            von, bis = int(z.split()[0]), int(z.split()[1])
            abgedeckt |= set(range(von, bis + 1))
        check("Z88MAT deckt jedes Element genau einmal ab",
              abgedeckt == set(n.elemente))


if __name__ == "__main__":
    for t in (test_netz_volumen, test_taschen_wirken, test_fliehkraft_quadratur,
              test_fliehkraft_skaliert, test_inp_form, test_ccx_loest,
              test_z88_satz, test_beide_loeser, test_materialstufen):
        t()
    print()
    if _uebersprungen:
        print(f"uebersprungen: {len(_uebersprungen)}  ->  " + ", ".join(_uebersprungen))
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
