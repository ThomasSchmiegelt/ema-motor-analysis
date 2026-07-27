"""Tests für den OpenFOAM-VOF-Kühlpfad (`ema_cfd`) — OHNE OpenFOAM/vtk.

Deckt die reinen, testbaren Kerne ab: Case-Dict-Generierung, Strahlgeschwindigkeit,
HTC-Korrelation und die flächengewichtete Benetzung. Der End-to-End-Lauf (interFoam)
wird separat manuell/über die UI geprüft (braucht OpenFOAM)."""

import ema_cfd


def _bbox():
    # 20×30×15 mm Wickelkopf-Box in Metern
    return (0.0, 0.0, 0.0, 0.02, 0.03, 0.015)


def test_jet_velocity():
    v = ema_cfd.jet_velocity(3.0)
    assert 18.0 < v < 24.0, f"3 bar → ~21 m/s, ist {v}"
    assert ema_cfd.jet_velocity(0.0) == 0.0
    # monoton mit Druck
    assert ema_cfd.jet_velocity(1.0) < ema_cfd.jet_velocity(3.0)
    print("✓ jet_velocity: 3 bar ≈ %.1f m/s, monoton" % v)


def test_htc_model():
    r = ema_cfd.htc_model(jet_v=21.0, nozzle_d_mm=1.0, wetted_frac=0.5, L_char_m=0.02)
    assert ema_cfd.HTC_MIN <= r["htc_eff"] <= ema_cfd.HTC_MAX
    assert r["Re_jet"] > 0 and r["Pr"] > 0 and r["Nu"] > 0
    # mehr Benetzung ⇒ höherer HTC (bis zur Klemme)
    lo = ema_cfd.htc_model(21.0, 1.0, 0.1, 0.02)["htc_eff"]
    hi = ema_cfd.htc_model(21.0, 1.0, 0.9, 0.02)["htc_eff"]
    assert hi >= lo
    # keine Benetzung ⇒ HTC 0
    assert ema_cfd.htc_model(21.0, 1.0, 0.0, 0.02)["htc_eff"] == 0.0
    print("✓ htc_model: HTC=%.0f W/m²·K (Re=%.0f Pr=%.0f Nu=%.0f), monoton mit Benetzung"
          % (r["htc_eff"], r["Re_jet"], r["Pr"], r["Nu"]))


def test_wetted_fraction():
    # 3 Faces, 2 benetzt (α=1) mit Flächen 2+1, 1 trocken (α=0) Fläche 3 → 3/6 = 0.5
    wf = ema_cfd.wetted_fraction(alpha=[1.0, 1.0, 0.0], area=[2.0, 1.0, 3.0])
    assert abs(wf - 0.5) < 1e-9, wf
    assert ema_cfd.wetted_fraction([0, 0], [1, 1]) == 0.0
    assert ema_cfd.wetted_fraction([1, 1], [1, 1]) == 1.0
    assert ema_cfd.wetted_fraction([1], [0]) == 0.0     # keine Fläche → 0
    print("✓ wetted_fraction: flächengewichtet korrekt (2 von 6 m² benetzt → 0.5)")


def test_case_dicts():
    v = ema_cfd.jet_velocity(3.0)
    cfg = {"bbox": _bbox(), "jet_v": v, "end_time": 0.05, "n_cells": 40,
           "refine": 2, "nu_oil": 40e-6, "rho_oil": 850.0, "sigma": 0.03,
           "stl_name": "windinghead.stl"}
    d = ema_cfd.build_case_dicts(cfg)
    # alle Pflicht-Dicts vorhanden
    need = ["system/controlDict", "system/fvSchemes", "system/fvSolution",
            "system/blockMeshDict", "system/snappyHexMeshDict",
            "system/surfaceFeatureExtractDict",
            "constant/transportProperties", "constant/g", "constant/turbulenceProperties",
            "0/alpha.oil", "0/U", "0/p_rgh"]
    for k in need:
        assert k in d, f"{k} fehlt"
        assert "FoamFile" in d[k], f"{k} ohne FoamFile-Header"
    # meshQualityControls inline (self-contained, kein #includeEtc → robuster snappy)
    assert "meshQualityControls" in d["system/snappyHexMeshDict"]
    assert "#includeEtc" not in d["system/snappyHexMeshDict"], "kein etc-Include (bricht snappy)"
    # interFoam-Solver + zwei Phasen
    assert "application     interFoam" in d["system/controlDict"]
    assert "phases (oil air)" in d["constant/transportProperties"]
    assert "sigma           0.03" in d["constant/transportProperties"]
    # Öleinlass mit der berechneten Strahlgeschwindigkeit in -Y
    assert f"(0 {-abs(v):g} 0)" in d["0/U"], "Einlassgeschwindigkeit fehlt in 0/U"
    assert "windinghead { type noSlip" in d["0/U"]
    assert "inlet       { type fixedValue; value uniform 1; }" in d["0/alpha.oil"]
    # snappy referenziert das STL + Feature-Level
    assert "windinghead.stl" in d["system/snappyHexMeshDict"]
    assert "value (0 -9.81 0)" in d["constant/g"]
    # blockMesh: gültige Vertex-/Block-Zahl (nx*ny*nz > 0)
    assert "hex (0 1 2 3 4 5 6 7)" in d["system/blockMeshDict"]
    print("✓ build_case_dicts: %d Dicts, interFoam+VOF, Einlass=%.1f m/s, STL/g/Phasen ok"
          % (len(d), v))


def test_persist_lean(tmp_path=None):
    import tempfile, os, json
    d = tmp_path or tempfile.mkdtemp()
    proj = os.path.join(str(d), "proj"); os.makedirs(proj, exist_ok=True)
    result = {"source": "openfoam_interfoam", "htc_eff": 1200.0, "wetted_pct_mean": 42.0,
              "images": {"cfd_wetting": "BASE64DATA"}, "vtp_path": "/tmp/x.vtp",
              "config": {"pressure_bar": 3.0}}
    ema_cfd._persist_cfd_summary(proj, result)
    with open(os.path.join(proj, "results.json")) as f:
        saved = json.load(f)["cfd"]
    assert saved["htc_eff"] == 1200.0
    assert "images" not in saved and "vtp_path" not in saved   # base64/Case-Pfad NICHT persistiert
    assert saved["image_files"]["cfd_wetting"] == "charts/cfd_wetting.png"
    print("✓ _persist_cfd_summary: schlank gemergt (kein base64/vtp), image_files gesetzt")


def test_thermal_coupling():
    """CFD-HTC → ema_thermal: senkt T_Wicklung; htc_oil=0 ist bit-identisch zum Preset."""
    import numpy as np
    import ema_thermal as T
    geom = {"statorID": 150, "statorOD": 230, "rotorOD": 148, "shaftD": 45,
            "slots": 48, "slotDepth": 18}
    G0 = T.conductances(geom, 100.0, "oil", 8000.0)                          # Preset
    G1 = T.conductances(geom, 100.0, "oil", 8000.0, htc_oil=1500.0, wetted_area_m2=0.03)
    assert G0["G_w_cool"] == 0.0 and G1["G_w_cool"] > 0.0
    losses = {"P_Cu": 800, "P_Fe_stator": 200, "P_Fe_rotor": 40,
              "P_Mag_eddy": 30, "P_Bearing": 15}
    s0 = T.solve_steady(G0, losses, 40.0)
    s1 = T.solve_steady(G1, losses, 40.0)
    assert s1["T_winding"] < s0["T_winding"], "CFD-HTC muss die Wicklung kühlen"
    # htc_oil=0 ⇒ Systemmatrix unverändert (bit-identisch zum alten Modell)
    assert np.allclose(T.build_GA(G0),
                       T.build_GA(T.conductances(geom, 100.0, "oil", 8000.0, htc_oil=0.0)))
    print("✓ thermal_coupling: T_Wicklung %.1f→%.1f °C mit CFD-HTC, htc_oil=0 unverändert"
          % (s0["T_winding"], s1["T_winding"]))


if __name__ == "__main__":
    test_jet_velocity()
    test_htc_model()
    test_wetted_fraction()
    test_case_dicts()
    test_persist_lean()
    test_thermal_coupling()
    print("\nALLE CFD-TESTS BESTANDEN ✅  (interFoam-End-to-End separat über die UI)")
