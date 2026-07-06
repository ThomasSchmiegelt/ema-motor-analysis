"""Tests für die ROI-Verfeinerung (Bereich besonderen Interesses höher auflösen).

Ansatz: KEIN echtes Submodell mit BC-Übertragung (das explodiert in diesem Elmer-Build —
ein auf der geschlossenen Box vorgegebenes, abgetastetes Motor-B-Feld erzeugt an den 12
Boxkanten widersprüchliche Kanten-A-Randwerte, s. memory project_em3d_submodel_bc), sondern
das VOLLE Modell wird mit einem lokal feineren Quader neu vernetzt und komplett neu gelöst.

Zwei Ebenen:
- OHNE Elmer (immer): das ROI-Box-Feld im Gmsh-Mesh verfeinert den Quader → mehr Knoten +
  ``mesh_zones["roi_cl"]`` gesetzt; ohne ROI bleibt das Mesh unverändert.
- MIT Elmer (``ELMER_OK``): ``run_em3d_refine`` löst das volle, lokal feinere Modell. Das Feld
  bleibt physikalisch (kein Aufblasen) UND stimmt im ROI mit einem Grob-Lauf überein (gleiche
  Physik, nur feiner) — der Korrektheitsbeweis des Verfahrens.

Lauf: ``python test_em3d_submodel.py``.
"""

import os
import tempfile

import numpy as np

import ema_em3d as E3
import elmer_runner as ER

_GEOM = {"statorOD": 120, "statorID": 80, "rotorOD": 78.6, "shaftD": 26, "p": 4,
         "slots": 48, "slotDepth": 12, "magThick": 5, "magWidth": 18, "magAngle": 130,
         "magDepthRel": 0.5, "magDist": 3, "poleArcFrac": 0.83, "magOrient": "transverse",
         "magnet": "ndfeb_n42", "magShape": "v"}
_AXIAL = 60.0
# Bewusst GROBES Basisnetz: lässt unter dem Knoten-Cap (EM3D_MAX_NODES) genug Luft, damit die
# ROI-Verfeinerung die Knotenzahl messbar erhöht (sonst vergröbert der Cap-Retry alles zurück).
_OPTS = {"skew_deg": 0, "mesh_cl": 11.0, "gap_cl": 2.8}


def _roi():
    """Quader Luftspalt→Statorzahn auf der +x-Seite (enthält Magnet, Spalt, Zahn)."""
    r_si = _GEOM["statorID"] / 2.0
    r_rot = _GEOM["rotorOD"] / 2.0
    return {"xmin": r_rot - 8.0, "xmax": r_si + 9.0, "ymin": -15.0, "ymax": 15.0,
            "zmin": _AXIAL * 0.30, "zmax": _AXIAL * 0.70}


def test_roi_box_refines_mesh():
    """Das ROI-Box-Feld verfeinert das volle Mesh lokal: mehr Knoten + mesh_zones["roi_cl"]."""
    work = tempfile.mkdtemp()
    msh0 = os.path.join(work, "plain.msh")
    tags0 = E3.build_mesh(_GEOM, _AXIAL, _OPTS, msh0)
    msh1 = os.path.join(work, "roi.msh")
    tags1 = E3.build_mesh(_GEOM, _AXIAL, {**_OPTS, "roi_box": _roi(), "roi_refine": 3.0}, msh1)
    assert "roi_cl" in tags1.get("mesh_zones", {}), "ROI-Zellgröße nicht im mesh_zones vermerkt"
    rc = tags1["mesh_zones"]["roi_cl"]
    assert rc < min(_OPTS["gap_cl"], tags1["mesh_zones"]["mag_cl"]) + 1e-9, f"roi_cl {rc} nicht feiner"
    assert tags1["n_nodes"] > tags0["n_nodes"] * 1.1, \
        f"ROI verfeinert das Mesh nicht (plain {tags0['n_nodes']} → roi {tags1['n_nodes']})"
    # Magnete/Körper bleiben erhalten (volles Modell, nicht beschnitten).
    assert tags1["n_magnets"] == tags0["n_magnets"] and tags1["n_magnets"] >= 1
    print(f"✓ ROI verfeinert Mesh: {tags0['n_nodes']} → {tags1['n_nodes']} Knoten, "
          f"roi_cl={rc:.3f} mm, {tags1['n_magnets']} Magnete erhalten")


def test_refine_full_resolve():
    """KORREKTHEIT: das lokal feinere Vollmodell bleibt physikalisch UND stimmt im ROI mit
    dem Grob-Lauf überein (gleiche Physik). Nur mit Elmer."""
    if not ER.ELMER_OK:
        print("• übersprungen (Elmer nicht installiert) — Mesh-Verfeinerung ist ohne Elmer geprüft")
        return
    # Grob-Lauf.
    cproj = tempfile.mkdtemp(prefix="coarse_")
    cres = E3.run_em3d({"geom": _GEOM, "axial_len": _AXIAL, **_OPTS}, cproj)
    assert cres.get("vtu_path"), "Grob-Lauf ohne VTU"

    # Verfeinerter Lauf.
    rproj = tempfile.mkdtemp(prefix="refine_")
    roi = _roi()
    rres = E3.run_em3d_refine({"geom": _GEOM, "axial_len": _AXIAL, "roi_box": roi,
                               "refine_factor": 3.0, **_OPTS}, rproj)
    assert rres.get("vtu_path"), "Verfeinerter Lauf ohne VTU"
    assert rres["mesh"]["n_nodes"] > cres["mesh"]["n_nodes"], \
        f"Verfeinerung erhöht die Knoten nicht ({cres['mesh']['n_nodes']} → {rres['mesh']['n_nodes']})"
    sgrid = E3._read_grid(rres["vtu_path"]); sbname = E3._b_array_name(sgrid)

    from vtk.util import numpy_support as ns
    smax = float(np.linalg.norm(ns.vtk_to_numpy(sgrid.GetPointData().GetArray(sbname))
                                .reshape(-1, 3), axis=1).max())
    # Explosionsschutz: ein echtes Submodell mit B-Rand sprengte auf >1000 T. Hier nur die
    # bekannte LINEARE Ecksingularität (μr=500, keine Sättigung) an scharfen Zahn-/Magnetkanten,
    # die unter Verfeinerung lokal wächst — kein Aufblasen.
    assert smax < 50.0, f"Verfeinertes Feld aufgeblasen (|B|max={smax:.1f} T)"

    # Korrektheit: NICHT punktweise gegen das (bewusst grobe) Grobfeld — Verfeinerung ÄNDERT das
    # Feld dort, wo grob falsch war (genau ihr Zweck). Stattdessen die netzrobuste Kopfgröße
    # vergleichen, die BEIDE Läufe liefern: die Luftspalt-Spitzenflussdichte b_gap_mid_peak
    # (dedizierte Spalt-Abtastung). Gleiche Physik → derselbe Betriebspunkt → ähnlicher Wert.
    bgc = cres.get("b_gap_mid_peak"); bgr = rres.get("b_gap_mid_peak")
    assert bgc and bgr, f"b_gap fehlt (grob {bgc}, fein {bgr})"
    rel = abs(bgr - bgc) / bgc
    print(f"✓ Verfeinerung physikalisch + konsistent: {cres['mesh']['n_nodes']} → "
          f"{rres['mesh']['n_nodes']} Knoten, |B|max {smax:.2f} T, "
          f"B_gap grob {bgc:.3f} → fein {bgr:.3f} T (Δ {rel*100:.1f}%)")
    assert rel < 0.35, f"Luftspalt-Flussdichte weicht zu stark ab (Δ {rel*100:.1f}%)"


_GEOM_BAR = {**_GEOM, "genFluxBarrierQ": True, "genFluxBarrierD": True,
             "fluxBarrierWidth": 3.0, "fluxBarrierDepth": 10.0}


def test_sector_mesh_and_sif():
    """Ein-Pol-Sektor-Mesh + sif OHNE Elmer: anti-periodische Winkelflächen + Außenrand,
    Magnete + Nuten + **Flussbarrieren**, konforme Periodikflächen (keine Warnung), gestufte
    Verfeinerung, Periodik-BC im sif, KEINE Coordinate Scaling."""
    work = tempfile.mkdtemp()
    msh = os.path.join(work, "sector.msh")
    tags = E3._build_sector_mesh(_GEOM_BAR, _AXIAL, {"mesh_cl": 3.0, "gap_cl": 1.0}, msh)
    assert os.path.exists(msh) and os.path.getsize(msh) > 50000
    assert tags["n_nodes"] > 3000, f"zu wenige Knoten: {tags['n_nodes']}"
    assert tags["poles"] == _GEOM_BAR["p"] * 2
    assert tags["n_magnets"] >= 1, "kein Magnet im Sektor"
    assert tags["n_barriers"] >= 1, "keine Flussbarriere im Sektor"
    assert not tags.get("warnings"), f"Sektor-Warnungen: {tags.get('warnings')}"  # Periodikflächen paaren
    # Gestufte Verfeinerung: Luftspalt < Magnet/Barriere < grob.
    mz = tags["mesh_zones"]
    assert mz["gap_cl"] <= mz["mag_cl"] <= mz["mesh_cl"], f"Zonen-Abstufung verletzt: {mz}"
    for k in ("outer_pid", "master_pid", "slave_pid"):
        assert k in tags, f"{k} fehlt"
    assert "rotor" in tags["bodies"] and "stator" in tags["bodies"]

    sif = E3.write_sector_sif(_GEOM, tags, work, {})
    txt = open(sif).read()
    assert "WhitneyAVSolver" in txt
    assert "Periodic BC =" in txt and "Periodic BC Rotate" in txt
    assert "Periodic BC Scale = Real -1.0" in txt, "anti-periodisch fehlt"
    assert "Use Lagrange Coefficient = Logical True" in txt
    assert txt.count("AV {e} = Real 0") == 1, "Außenrand A×n=0 fehlt/doppelt"
    assert txt.count("Magnetization 1 =") == tags["n_magnets"]
    assert "Coordinate Scaling" not in txt, "Sektor rechnet in mm (skaleninvariant, wie Vollmodell)"
    print(f"✓ Sektor mesh+sif: {tags['n_nodes']} Knoten, {tags['n_magnets']} Magnete, "
          f"{tags['n_slots']} Nuten, {tags['n_barriers']} Barrieren, α={tags['alpha']*57.2958:.0f}°, "
          f"Zonen {tags['mesh_zones']['gap_cl']:.2f}/{tags['mesh_zones']['mag_cl']:.2f}/"
          f"{tags['mesh_zones']['mesh_cl']:.2f}, anti-periodisch+Außenrand")


def test_sector_full_resolve():
    """KORREKTHEIT: Ein-Pol-Sektor (MIT Flussbarrieren) anti-periodisch → physikalisches Feld +
    korrekte Anti-Periodizität im Eisen + bis ~max_nodes ausgereizt + zum vollen Motor
    gespiegelt. Nur mit Elmer."""
    if not ER.ELMER_OK:
        print("• übersprungen (Elmer nicht installiert) — Sektor-Mesh/sif sind ohne Elmer geprüft")
        return
    proj = tempfile.mkdtemp(prefix="sector_")
    res = E3.run_em3d_sector({"geom": _GEOM_BAR, "axial_len": _AXIAL}, proj)
    assert res.get("source") == "sector"
    assert res.get("vtu_path") and os.path.exists(res["vtu_path"]), "kein voller-Motor-VTU"
    assert res.get("vtp_path") and res.get("lines_path"), "Browser-Export fehlt"
    assert res["mesh"].get("n_barriers", 0) >= 1, "Flussbarrieren nicht im Sektor"
    # Knoten-Budget ausgereizt (im Zielband, unter dem Solver-Limit).
    n = res["mesh"]["n_nodes"]
    assert 0.5 * E3.EM3D_MAX_NODES <= n <= E3.EM3D_MAX_NODES, f"Knotenbudget nicht ausgereizt: {n}"
    b = res.get("b_stats") or {}
    assert b.get("max", 99) < 50.0, f"Feld aufgeblasen (|B|max={b.get('max')} T)"
    ap = res.get("antiperiodic_err")
    assert ap is not None and ap < 0.15, f"Anti-Periodizität im Eisen zu hoch ({ap})"
    # Voller Motor = poles Kopien → deutlich mehr Zellen als ein Pol.
    sg = E3._read_grid(res["vtu_path"])
    assert sg.GetNumberOfCells() > n, "Spiegelung zum vollen Motor unplausibel"
    print(f"✓ Sektor reproduziert physikalisch: {n} Knoten/Pol (max {E3.EM3D_MAX_NODES}), "
          f"{res['mesh']['n_barriers']} Barrieren, Anti-Periodizität {ap*100:.1f}%, "
          f"|B|max {b.get('max')} T, voller Motor {sg.GetNumberOfCells()} Zellen ({res['poles']} Pole)")


def main():
    test_roi_box_refines_mesh()
    test_refine_full_resolve()
    test_sector_mesh_and_sif()
    test_sector_full_resolve()
    print("\nALLE VERFEINERUNGS-/SEKTOR-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
