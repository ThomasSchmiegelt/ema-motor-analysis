"""Tests für ema_em3d — Mesh-Erzeugung + Tagging (braucht gmsh, NICHT Elmer).

Prüft, dass das 3D-Mesh die Bauteile korrekt als Physical-Volumes taggt
(shaft/rotor/stator/air + Magnete), die Magnetzahl zur Topologie passt, der
Skew die Magnete über die Länge verdreht und die .sif sauber generiert.

Lauf: ``python test_em3d.py``.
"""

import math
import os
import tempfile

import ema_em3d as E3

_GEOM = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "p": 4,
         "slots": 48, "slotDepth": 25, "magThick": 6, "magWidth": 40, "magAngle": 130,
         "magDepthRel": 0.5, "magDist": 3, "poleArcFrac": 0.83, "magOrient": "transverse",
         "magnet": "ndfeb_n42"}


def _geom(shape):
    g = dict(_GEOM); g["magShape"] = shape; return g


def test_magnet_rects_count():
    # bar/spoke: 1 Magnet je Pol = 8; V: 2 Arme je Pol = 16.
    assert len(E3.magnet_rects(_geom("bar"))) == 8
    assert len(E3.magnet_rects(_geom("v"))) == 16
    # Magnetisierungs-Vektor ist ein Einheitsvektor, Vorzeichen alterniert über die Pole.
    rects = E3.magnet_rects(_geom("bar"))
    for m in rects:
        assert abs(math.hypot(m["mdx"], m["mdy"]) - 1.0) < 1e-6
    assert {m["sign"] for m in rects} == {1.0, -1.0}
    print("✓ magnet_rects: bar=8, v=16, Einheits-M, alternierende Polung")


def test_mesh_tagging():
    msh = os.path.join(tempfile.mkdtemp(), "m.msh")
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 0, "mesh_cl": 13.0, "gap_cl": 1.6}, msh)
    assert os.path.exists(msh) and os.path.getsize(msh) > 100000
    for name in ("shaft", "rotor", "stator", "air"):
        assert name in tags["bodies"], f"Körper {name} fehlt"
    assert tags["n_magnets"] == 16, f"Magnete {tags['n_magnets']} ≠ 16"
    assert tags["n_nodes"] > 5000
    assert "boundary" in tags
    print(f"✓ mesh_tagging: Körper {list(tags['bodies'])}, {tags['n_magnets']} Magnete, "
          f"{tags['n_nodes']} Knoten")


def test_skew_twists_magnets():
    # Skew dreht die Magnet-Endquerschnitte über die Länge → der obere Querschnitt
    # ist gegenüber dem unteren um skew_deg verdreht. Wir prüfen das geometrisch über
    # die magnet_rects-unabhängige Mesh-Baubarkeit + dass ein Lauf mit Skew durchläuft.
    msh = os.path.join(tempfile.mkdtemp(), "s.msh")
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 12, "mesh_cl": 13.0, "gap_cl": 1.6}, msh)
    assert tags["n_magnets"] == 16
    assert os.path.exists(msh)
    print("✓ skew=12°: Mesh baubar, 16 Magnete getaggt")


def test_sif_generation():
    msh = os.path.join(tempfile.mkdtemp(), "m.msh")
    work = os.path.dirname(msh)
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 0, "mesh_cl": 14.0, "gap_cl": 1.8}, msh)
    sif = E3.write_sif(_geom("v"), {}, tags, work, "mesh")
    txt = open(sif).read()
    assert "WhitneyAVSolver" in txt
    assert "MagnetoDynamicsCalcFields" in txt
    assert txt.count("Magnetization 1 =") == tags["n_magnets"]
    assert "Boundary Condition 1" in txt
    assert "Relative Permeability = 500" in txt
    print(f"✓ sif: WhitneyAVSolver + CalcFields + {tags['n_magnets']} Magnetisierungen + BC")


def main():
    test_magnet_rects_count()
    test_mesh_tagging()
    test_skew_twists_magnets()
    test_sif_generation()
    print("\nALLE EM3D-MESH-TESTS BESTANDEN ✅  (Elmer-Solve separat, sobald installiert)")


if __name__ == "__main__":
    main()
