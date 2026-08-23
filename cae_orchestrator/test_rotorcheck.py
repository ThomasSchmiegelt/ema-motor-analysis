"""Regressionstests fuer die Rotor-Tore (ema_rotorcheck) und den Sliver-Purge
(ema_purge) — beides kam ohne Test in den Baum und beides aendert Zahlen, die
in gespeicherten ``results.json`` landen.

Warum diese Tests und nicht andere:

* ``_bore_hoop_mpa`` ersetzt eine Formel, die um rund den Faktor 2 zu niedrig
  lag. Der Test prueft sie deshalb NICHT gegen sich selbst, sondern gegen die
  geschlossene Lehrbuchloesung der rotierenden Kreisringscheibe, unabhaengig
  hingeschrieben. Ohne diesen Anker koennte die Korrektur still zurueckfallen.
* ``_struct_sweep`` speist ``max_safe_rpm``. Seine Spannungen haben sich durch
  die Korrektur verdoppelt — der Test haelt den Zusammenhang zur Formel und die
  rpm^2-Skalierung fest.
* ``ema_purge`` existiert ZWEIMAL: als Modul und als Textkopie in
  ``_STANDALONE``, die in das FreeCAD-Kindskript gespleisst wird. Nichts hielt
  die beiden bisher zusammen; der Test laesst beide dieselbe Datei bearbeiten.

Lauf: ``python test_rotorcheck.py``  (keine externen Loeser noetig)
"""

import math
import os
import sys
import tempfile

import ema_purge
from ema_rotorcheck import (KT_POCKET, _bore_hoop_mpa, rotor_layout_check,
                            rotor_stress_check)

_fails = []


def check(name, cond, detail=""):
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        _fails.append(name)


def near(a, b, rel=1e-9):
    return abs(a - b) <= rel * max(abs(a), abs(b), 1e-30)


# ── 1. Bohrungs-Ringspannung gegen die unabhaengige Lehrbuchform ──────────────

def _lehrbuch_sigma_theta_bore(a, b, rho, w, nu):
    """sigma_theta(r=a) der rotierenden Kreisringscheibe, ebener SPANNUNGSzustand.

    Unabhaengig aus der allgemeinen Verteilung hingeschrieben
        sigma_theta(r) = (3+nu)/8 * rho w^2 * [a^2 + b^2 + a^2 b^2 / r^2
                                               - (1+3nu)/(3+nu) * r^2]
    und bei r = a ausgewertet — bewusst NICHT in der Form, die der Code benutzt.
    """
    return ((3.0 + nu) / 8.0 * rho * w * w
            * (a * a + b * b + a * a * b * b / (a * a)
               - (1.0 + 3.0 * nu) / (3.0 + nu) * a * a)) / 1e6


def test_bore_hoop():
    print("1. Bohrungs-Ringspannung")
    a, b, rho, nu = 0.030, 0.0943, 7650.0, 0.30      # 60 mm Welle, 188,6 mm Rotor
    w = 2.0 * math.pi * 20000.0 / 60.0                # 20 000 U/min
    ist  = _bore_hoop_mpa(a, b, rho, w, nu)           # ebener Spannungszustand
    soll = _lehrbuch_sigma_theta_bore(a, b, rho, w, nu)
    check("ebener Spannungszustand == Lehrbuchloesung",
          near(ist, soll, 1e-12), f"{ist:.6f} vs {soll:.6f} MPa")

    # Ebener Dehnungszustand ist die konservative Schranke und MUSS hoeher liegen.
    lam_strain = nu / (1.0 - nu)
    konservativ = _bore_hoop_mpa(a, b, rho, w, lam_strain)
    check("ebener Dehnungszustand > ebener Spannungszustand",
          konservativ > ist, f"{konservativ:.1f} vs {ist:.1f} MPa")

    # Groessenordnung festnageln: die alte /8-Form lag hier bei rund der Haelfte.
    check("Wert in erwarteter Groessenordnung (150…400 MPa)",
          150.0 < konservativ < 400.0, f"{konservativ:.1f} MPa")

    # Vollscheibe (a -> 0): sigma_theta(0) = (3+lam)/4 * rho w^2 b^2
    voll = _bore_hoop_mpa(0.0, b, rho, w, nu)
    check("Grenzfall Vollscheibe",
          near(voll, (3.0 + nu) / 4.0 * rho * w * w * b * b / 1e6, 1e-12))

    # Quadratische Drehzahlabhaengigkeit
    check("sigma ~ n^2",
          near(_bore_hoop_mpa(a, b, rho, 2 * w, nu), 4.0 * ist, 1e-12))


# ── 2. _struct_sweep haengt an derselben Formel ───────────────────────────────

def test_struct_sweep():
    print("2. Strukturkennlinie (_struct_sweep)")
    from ema_pipeline import LAMINATES, _struct_sweep
    geom = {"rotorOD": 188.6, "shaftD": 60.0}
    mat  = LAMINATES["m800_65a"]
    rpms = [10000.0, 20000.0]
    sweep = _struct_sweep(geom, mat, rpms)
    check("ein Eintrag je Drehzahl", len(sweep) == 2)

    w20 = 2.0 * math.pi * 20000.0 / 60.0
    erwartet = _bore_hoop_mpa(0.030, 0.0943, mat["density"], w20,
                              mat["nu"] / (1.0 - mat["nu"])) * KT_POCKET
    check("sigma == Ringspannung (ebener Dehnungszustand) x Kt",
          near(sweep[1]["sigma_max_MPa"], round(erwartet, 2), 1e-6),
          f"{sweep[1]['sigma_max_MPa']} vs {round(erwartet, 2)} MPa")

    check("sigma ~ n^2 ueber den Sweep",
          near(sweep[1]["sigma_max_MPa"], 4.0 * sweep[0]["sigma_max_MPa"], 2e-3),
          f"{sweep[1]['sigma_max_MPa']} vs {4 * sweep[0]['sigma_max_MPa']}")

    check("SF = Fliessgrenze / sigma",
          near(sweep[1]["safety_factor"],
               round(mat["yield_mpa"] / sweep[1]["sigma_max_MPa"], 2), 1e-6))


# ── 3. Layout-Tor: echte Geometrie besteht, gestauchte faellt durch ───────────

_GEOM_OK = {   # aus dem realen Lauf 20260812_073601_Traktionsmotor_Vorstellung
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60,
    "slots": 36, "p": 3, "magShape": "delta", "magAngle": 94, "magAngle2": 94,
    "magDepthRel": 0.3, "magWidth": 37, "magThick": 6, "magDist": 13.5,
    "magLayers": 3, "magLayerGap": 13.5, "poleArcFrac": 0.83, "magGapMm": 0.1,
    "airGap": 0.7, "magAsym": 0, "magTangLen": 0, "segPerPole": 6,
}


def test_layout_gate():
    print("3. Layout-Tor (rotor_layout_check)")
    ok = rotor_layout_check(dict(_GEOM_OK))
    check("reale Auslegung besteht", ok["ok"], "; ".join(ok.get("fatal", [])))
    check("Bericht nennt Taschenzahl und Mindestabstand",
          ok["layout"]["pockets_total"] > 0
          and ok["layout"]["min_web_found_mm"] is not None)
    check("gefundener Abstand >= gefordertem",
          ok["layout"]["min_web_found_mm"] >= ok["layout"]["min_web_req_mm"],
          f"{ok['layout']['min_web_found_mm']} < {ok['layout']['min_web_req_mm']}")

    # Lagen aufeinanderschieben -> Taschen muessen sich ueberschneiden.
    kollision = dict(_GEOM_OK, magLayerGap=0.0, magDist=0.0)
    bad = rotor_layout_check(kollision)
    check("kollidierende Lagen werden abgewiesen", not bad["ok"])
    check("Ablehnung ist begruendet", bool(bad.get("fatal")))

    # Magnete radial nach aussen ueber den Rotorrand schieben.
    ausbruch = dict(_GEOM_OK, magDepthRel=0.999, magThick=25.0)
    out = rotor_layout_check(ausbruch)
    check("Durchbruch am Rotorrand wird abgewiesen", not out["ok"])


# ── 4. Festigkeits-Tor ────────────────────────────────────────────────────────

def test_stress_gate():
    print("4. Festigkeits-Tor (rotor_stress_check)")
    from ema_pipeline import LAMINATES
    mat = LAMINATES["m800_65a"]
    st = rotor_stress_check(dict(_GEOM_OK), mat, {"n_max": 20000.0})
    check("beide ebenen Zustaende ausgewiesen",
          st["sigma_bore_conservative_MPa"] > st["sigma_bore_plane_stress_MPa"])
    check("Peak = konservativ x Kt",
          near(st["sigma_peak_MPa"],
               round(st["sigma_bore_conservative_MPa"] * st["kt_pocket"], 1), 0.02),
          f"{st['sigma_peak_MPa']} vs {st['sigma_bore_conservative_MPa'] * st['kt_pocket']}")
    check("SF_peak = Fliessgrenze / Peak",
          near(st["safety_factor_peak"],
               round(st["yield_mpa"] / st["sigma_peak_MPa"], 2), 0.02))

    langsam = rotor_stress_check(dict(_GEOM_OK), mat, {"n_max": 3000.0})
    check("bei 3000 U/min unkritisch", langsam["safety_factor_peak"] > 1.0)
    schnell = rotor_stress_check(dict(_GEOM_OK), mat, {"n_max": 60000.0})
    check("bei 60000 U/min faellt es durch", schnell["safety_factor_peak"] < 1.0)


# ── 5. Modul und Standalone-Textkopie muessen dasselbe tun ────────────────────

# Das Netz muss GROSS genug sein: ``_drop_ids`` bricht ab, wenn mehr als 5 % der
# Tets verdaechtig sind (Schutz vor Parserfehlern). Ein Zwei-Element-Netz mit einem
# Sliver laege bei 50 % und wuerde den Riegel ausloesen statt den Sliver zu entfernen.
_N_GUT = 40


def _baue_inp(pfad, n_gut=_N_GUT):
    """Schreibt ein .inp mit ``n_gut`` sauberen Tets (V = 1/6) und EINEM flachen."""
    knoten, elemente = [], []
    nid = 1
    for i in range(n_gut):
        x = float(i)
        basis = nid
        knoten += [(nid,     x,       0.0, 0.0),
                   (nid + 1, x + 1.0, 0.0, 0.0),
                   (nid + 2, x,       1.0, 0.0),
                   (nid + 3, x,       0.0, 1.0)]
        elemente.append((i + 1, basis, basis + 1, basis + 2, basis + 3))
        nid += 4
    # ein entarteter Tet: vierter Knoten praktisch in der Grundebene
    basis = nid
    knoten += [(nid,     0.0, 0.0, 0.0),
               (nid + 1, 1.0, 0.0, 0.0),
               (nid + 2, 0.0, 1.0, 0.0),
               (nid + 3, 0.0, 0.0, 1e-10)]
    eid_sliver = n_gut + 1
    elemente.append((eid_sliver, basis, basis + 1, basis + 2, basis + 3))

    with open(pfad, "w") as f:
        f.write("*Node\n")
        for k in knoten:
            f.write("%d, %.10f, %.10f, %.10f\n" % k)
        f.write("*Element, TYPE=C3D4, ELSET=Evolumes\n")
        for e in elemente:
            f.write("%d, %d, %d, %d, %d\n" % e)
        f.write("*NSET, NSET=Fixed\n1\n2\n")
    return eid_sliver


def test_purge_paritaet():
    print("5. Sliver-Purge: Modul == Standalone-Textkopie")
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.inp")
        b = os.path.join(d, "b.inp")
        eid = _baue_inp(a)
        _baue_inp(b)

        n_a, tot_a = ema_purge.purge_slivers_inp(a)

        ns = {}
        exec(compile(ema_purge._STANDALONE, "<standalone>", "exec"), ns)
        n_b, tot_b = ns["purge_slivers_inp"](b)

        check("gleiche Zaehlung", (n_a, tot_a) == (n_b, tot_b),
              f"{(n_a, tot_a)} vs {(n_b, tot_b)}")
        check("gleiche Ausgabedatei",
              open(a).read() == open(b).read())
        check("genau der flache Tet ist weg",
              n_a == 1 and tot_a == _N_GUT + 1, f"{(n_a, tot_a)}")
        txt = open(a).read()
        # Nur Elementzeilen pruefen: Knotenzeilen beginnen ebenfalls mit einer ID,
        # ein reines startswith() traefe den gleichnamigen Knoten mit.
        def _elementzeilen(t):
            for z in t.splitlines():
                teile = z.split(",")
                if len(teile) == 5 and all(x.strip().isdigit() for x in teile):
                    yield int(teile[0].strip())
        check("Sliver-Elementzeile entfernt", eid not in set(_elementzeilen(txt)))
        check("alle guten Tets bleiben",
              sum(1 for z in txt.splitlines()
                  if z and not z.startswith("*") and len(z.split(",")) == 5
                  and all(t.strip().isdigit() for t in z.split(","))) == _N_GUT)
        check("Knoten bleiben unangetastet", txt.count("*Node") == 1)
        check("NSET-Zeilen unangetastet", "*NSET, NSET=Fixed" in txt)

        # Idempotent
        n2, _ = ema_purge.purge_slivers_inp(a)
        check("zweiter Lauf entfernt nichts mehr", n2 == 0)


def test_purge_volcut_ohne_nachwirkung():
    print("6. Sliver-Purge: volcut wirkt nur fuer den einen Aufruf")
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.inp")
        _baue_inp(a)
        try:
            ema_purge.purge_slivers_inp(a, volcut=1e9)   # alles verdaechtig
        except ValueError:
            pass                                          # 5-%-Riegel greift: gewollt
        check("Modulglobale unveraendert", ema_purge._VOLCUT == 1e-6,
              f"_VOLCUT = {ema_purge._VOLCUT}")

        b = os.path.join(d, "b.inp")
        _baue_inp(b)
        n, tot = ema_purge.purge_slivers_inp(b)
        check("Folgeaufruf verhaelt sich wie zuvor", (n, tot) == (1, _N_GUT + 1),
              f"{(n, tot)}")


def test_purge_riegel():
    print("7. Sliver-Purge: 5-%-Riegel laesst die Datei unangetastet")
    with tempfile.TemporaryDirectory() as d:
        a = os.path.join(d, "a.inp")
        _baue_inp(a)
        vorher = open(a).read()
        try:
            ema_purge.purge_slivers_inp(a, volcut=1e9)
            check("ValueError erwartet", False, "kein Fehler ausgeloest")
        except ValueError:
            check("ValueError ausgeloest", True)
        check("Datei unveraendert", open(a).read() == vorher)


if __name__ == "__main__":
    for t in (test_bore_hoop, test_struct_sweep, test_layout_gate,
              test_stress_gate, test_purge_paritaet,
              test_purge_volcut_ohne_nachwirkung, test_purge_riegel):
        t()
    print()
    if _fails:
        print(f"FEHLGESCHLAGEN: {len(_fails)}  ->  " + ", ".join(_fails))
        sys.exit(1)
    print("Alle Pruefungen bestanden.")
