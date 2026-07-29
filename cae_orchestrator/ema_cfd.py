"""Quantitative Spritzöl-Wickelkopfkühlung mit OpenFOAM VOF (interFoam).

Eigenständiger On-Demand-Pfad **neben** dem qualitativen Mantaflow-Pfad (`ema_oilspray`):
auf DEMSELBEN Wickelkopf-STL-Ausschnitt läuft eine VOF-Zweiphasen-Simulation (Öl/Luft,
`interFoam`) → benetzte Fläche %, Filmverteilung und ein daraus abgeleiteter **effektiver
Wärmeübergangskoeffizient (HTC)**, der in `ema_thermal` einen echten Wicklung→Kühlmittel-Pfad
speisen kann. Spiegelt die vorhandene Elmer-3D-Architektur (`ema_em3d`): Case-Generator +
Subprozess-Wrapper (`openfoam_runner`) + threaded Server-State + `/cfd`-Routen + Job-Queue.

**Scope-Ehrlichkeit (steht im UI):** `interFoam` ist ISOTHERM — es löst die Strömung/Benetzung
exakt, liefert aber selbst KEIN Temperaturfeld. Der HTC ist ein **korrelationsbasierter Kennwert**
(Prallstrahl-Nusselt über der gerechneten Benetzung, Stufe 1). Ein vollständig aufgelöster
konjugierter HTC wäre die spätere CHT-Ausbaustufe (`chtMultiRegionFoam`, gleiches Gerüst).

Getrennt gebaut, damit OHNE OpenFOAM/vtk testbar (`test_cfd.py`):
  * `build_case_dicts(cfg)` — reine Text-Templates aller OpenFOAM-Dicts (system/constant/0).
  * `jet_velocity` / `htc_model` — reine Physik (numpy), unit-testbar.
Nur `run_cfd`/`_prep_case`/`_parse` brauchen die Solver/vtk.
"""

import base64
import json
import math
import os

# ── Stoffwerte Öl (Stufe-1-Defaults, per Payload überschreibbar) ─────────────
RHO_OIL   = 850.0        # kg/m³
CP_OIL    = 2000.0       # J/kg·K  (typisches Getriebe-/Kühlöl)
K_OIL     = 0.14         # W/m·K
NU_OIL    = 40.0e-6      # m²/s    kinematische Viskosität (~40 cSt warm)
SIGMA_OIL = 0.03         # N/m     Oberflächenspannung Öl/Luft
CD_NOZZLE = 0.8          # Düsen-Ausflussbeiwert (wie ema_oilspray)

RHO_AIR = 1.2
NU_AIR  = 1.5e-5

# HTC-Klemmen (physikalisch plausibles Ölspray-Band, hält den Stufe-1-Kennwert ehrlich)
HTC_MIN, HTC_MAX = 100.0, 8000.0

SCOPE_NOTE = ("Quantitative OpenFOAM-VOF-Studie (interFoam). Die Strömung/Benetzung wird "
              "gelöst; interFoam ist ISOTHERM, daher ist der HTC ein korrelationsbasierter "
              "Kennwert (Prallstrahl-Nusselt über der gerechneten Benetzung, Stufe 1) — KEIN "
              "aufgelöstes konjugiertes Temperaturfeld. CHT wäre die Folgestufe.")


# ── reine Physik (unit-testbar) ──────────────────────────────────────────────

def jet_velocity(pressure_bar: float) -> float:
    """Strahlgeschwindigkeit aus dem Öldruck via Bernoulli (wie ema_oilspray):
    v = Cd·√(2·Δp/ρ). 3 bar ≈ 21 m/s."""
    dp = max(0.0, float(pressure_bar)) * 1e5
    return CD_NOZZLE * math.sqrt(2.0 * dp / RHO_OIL)


def htc_model(jet_v: float, nozzle_d_mm: float, wetted_frac: float,
              L_char_m: float, props: dict | None = None) -> dict:
    """Effektiver HTC (Stufe 1) aus der gerechneten Benetzung + einer dokumentierten
    Prallstrahl-Nusselt-Korrelation.

    Modell (frei-oberflächen-Prallstrahl, flächengemittelt):
        Re = v·D/ν,  Pr = ν·ρ·cp/k,  Nu = 0.585·Re^0.5·Pr^0.4   (Mittelwert, Größenordnung)
        h_local = Nu·k / L_char        (L_char = benetzte Wickelkopf-Charakteristik)
        h_eff   = wetted_frac · h_local   (nur die benetzte Fläche überträgt)
    geklemmt auf ein physikalisch plausibles Ölspray-Band. Rückgabe enthält alle
    Zwischengrößen, damit sie im Bericht dokumentierbar sind."""
    p = props or {}
    nu = float(p.get("nu", NU_OIL)); rho = float(p.get("rho", RHO_OIL))
    cp = float(p.get("cp", CP_OIL)); k = float(p.get("k", K_OIL))
    d = max(1e-4, float(nozzle_d_mm) * 1e-3)
    L = max(2e-3, float(L_char_m))
    v = max(0.0, float(jet_v))
    Re = v * d / nu
    Pr = nu * rho * cp / k
    Nu = 0.585 * (Re ** 0.5) * (Pr ** 0.4) if Re > 0 else 0.0
    h_local = Nu * k / L
    h_eff = max(0.0, min(1.0, float(wetted_frac))) * h_local
    h_eff = max(HTC_MIN, min(HTC_MAX, h_eff)) if h_eff > 0 else 0.0
    return {"htc_eff": round(h_eff, 1), "h_local": round(h_local, 1),
            "Re_jet": round(Re, 1), "Pr": round(Pr, 1), "Nu": round(Nu, 1),
            "L_char_mm": round(L * 1e3, 2), "jet_v_mps": round(v, 2)}


# ── OpenFOAM-Case-Dicts (reine Text-Templates, unit-testbar) ─────────────────

_FOAM_HEAD = ("/*--------------------------------*- C++ -*----------------------------------*\\\n"
              "| ema_cfd generated case (OpenFOAM VOF / interFoam)                         |\n"
              "\\*---------------------------------------------------------------------------*/\n")


def _foam_file(cls: str, obj: str, location: str = "") -> str:
    loc = f'    location    "{location}";\n' if location else ""
    return (_FOAM_HEAD +
            "FoamFile\n{\n    version 2.0;\n    format  ascii;\n"
            f"    class   {cls};\n{loc}    object  {obj};\n}}\n"
            "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n")


def build_case_dicts(cfg: dict) -> dict:
    """Alle OpenFOAM-Dicts als ``{relpath: content}``. REIN (kein Dateisystem/Solver) →
    unit-testbar. ``cfg`` erwartet:
      bbox   = (xmin,ymin,zmin, xmax,ymax,zmax)  [m]  Wickelkopf-Bounding-Box
      jet_v  [m/s], end_time [s], write_interval [s], n_cells (Hintergrund-Grundauflösung),
      refine (snappy-Level), nu_oil, rho_oil, sigma, stl_name (Datei in constant/triSurface).
    Öl kommt als Curtain vom **+Y-Rand** (Ring-Seite) mit -Y-Geschwindigkeit, Schwerkraft -Y;
    der Wickelkopf ist eine no-slip-Wand (aus dem STL via snappy). Atmosphäre an den übrigen
    Rändern (Ablauf)."""
    bx = [float(v) for v in cfg["bbox"]]
    xmin, ymin, zmin, xmax, ymax, zmax = bx
    jet_v   = float(cfg.get("jet_v", 21.0))
    end_t   = float(cfg.get("end_time", 0.05))
    dt      = float(cfg.get("delta_t", 1e-5))
    wint    = float(cfg.get("write_interval", max(end_t / 20.0, 1e-3)))
    ncell   = int(cfg.get("n_cells", 40))
    refine  = int(cfg.get("refine", 2))
    nu_oil  = float(cfg.get("nu_oil", NU_OIL))
    rho_oil = float(cfg.get("rho_oil", RHO_OIL))
    sigma   = float(cfg.get("sigma", SIGMA_OIL))
    stl     = cfg.get("stl_name", "windinghead.stl")

    # Hintergrund-Zellzahl je Achse ~ konstante Zellgröße
    span = [xmax - xmin, ymax - ymin, zmax - zmin]
    smax = max(span) or 1.0
    nx, ny, nz = (max(6, int(round(ncell * s / smax))) for s in span)
    # Innenpunkt für snappy locationInMesh (nahe Domänen-Zentrum, ausserhalb des STL nach -Z-Rand)
    loc = ((xmin + xmax) / 2.0, (ymin + ymax) / 2.0, zmin + 0.05 * span[2])

    d: dict[str, str] = {}

    # --- system/controlDict ---
    d["system/controlDict"] = _foam_file("dictionary", "controlDict", "system") + (
        "application     interFoam;\n"
        "startFrom       startTime;\nstartTime       0;\n"
        f"stopAt          endTime;\nendTime         {end_t:g};\n"
        f"deltaT          {dt:g};\n"
        "writeControl    adjustableRunTime;\n"
        f"writeInterval   {wint:g};\n"
        "purgeWrite      0;\nwriteFormat     ascii;\nwritePrecision  6;\n"
        "writeCompression off;\ntimeFormat      general;\ntimePrecision   6;\n"
        "runTimeModifiable yes;\n"
        "adjustTimeStep  yes;\nmaxCo           0.9;\nmaxAlphaCo      0.9;\n"
        f"maxDeltaT       {wint:g};\n")

    # --- system/fvSchemes (interFoam Standard) ---
    d["system/fvSchemes"] = _foam_file("dictionary", "fvSchemes", "system") + (
        "ddtSchemes { default Euler; }\n"
        "gradSchemes { default Gauss linear; }\n"
        "divSchemes\n{\n"
        "    div(rhoPhi,U)         Gauss linearUpwind grad(U);\n"
        "    div(phi,alpha)        Gauss vanLeer;\n"
        "    div(phirb,alpha)      Gauss linear;\n"
        "    div(((rho*nuEff)*dev2(T(grad(U))))) Gauss linear;\n"
        "    default               none;\n}\n"
        "laplacianSchemes { default Gauss linear corrected; }\n"
        "interpolationSchemes { default linear; }\n"
        "snGradSchemes { default corrected; }\n")

    # --- system/fvSolution (interFoam Standard) ---
    d["system/fvSolution"] = _foam_file("dictionary", "fvSolution", "system") + (
        "solvers\n{\n"
        '    "alpha.oil.*"\n    {\n'
        "        nAlphaCorr      2;\n        nAlphaSubCycles 1;\n        cAlpha          1;\n"
        "        MULESCorr       yes;\n        nLimiterIter    5;\n"
        "        solver          smoothSolver;\n        smoother        symGaussSeidel;\n"
        "        tolerance       1e-8;\n        relTol          0;\n    }\n"
        '    "pcorr.*"\n    {\n        solver PCG; preconditioner DIC; tolerance 1e-5; relTol 0;\n    }\n'
        "    p_rgh\n    {\n        solver PCG; preconditioner DIC; tolerance 1e-7; relTol 0.05;\n    }\n"
        "    p_rghFinal\n    {\n        $p_rgh; relTol 0;\n    }\n"
        '    "(U|k|omega|epsilon).*"\n    {\n        solver smoothSolver; smoother symGaussSeidel;\n'
        "        tolerance 1e-7; relTol 0;\n    }\n}\n"
        "PIMPLE\n{\n    momentumPredictor no;\n    nOuterCorrectors 1;\n    nCorrectors 3;\n"
        "    nNonOrthogonalCorrectors 0;\n}\n")

    # --- system/blockMeshDict (Hintergrund-Box, meter) ---
    verts = [(xmin, ymin, zmin), (xmax, ymin, zmin), (xmax, ymax, zmin), (xmin, ymax, zmin),
             (xmin, ymin, zmax), (xmax, ymin, zmax), (xmax, ymax, zmax), (xmin, ymax, zmax)]
    vtxt = "\n".join(f"    ({v[0]:.6g} {v[1]:.6g} {v[2]:.6g})" for v in verts)
    d["system/blockMeshDict"] = _foam_file("dictionary", "blockMeshDict", "system") + (
        "scale 1;\n\nvertices\n(\n" + vtxt + "\n);\n\n"
        f"blocks\n(\n    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)\n);\n\n"
        "edges ();\n\n"
        "boundary\n(\n"
        "    inlet   { type patch; faces ( (3 7 6 2) ); }\n"           # +Y (Ring-Seite) = Öleinlass
        "    atmosphere { type patch; faces ( (1 5 4 0) (0 4 7 3) (2 6 5 1) (0 3 2 1) (4 5 6 7) ); }\n"
        ");\n\nmergePatchPairs ();\n")

    # --- system/surfaceFeatureExtractDict ---
    d["system/surfaceFeatureExtractDict"] = _foam_file(
        "dictionary", "surfaceFeatureExtractDict", "system") + (
        f"{stl}\n{{\n    extractionMethod extractFromSurface;\n"
        "    extractFromSurfaceCoeffs { includedAngle 150; }\n"
        "    writeObj no;\n}\n")

    # --- system/snappyHexMeshDict ---
    surf_feat = stl.replace(".stl", ".eMesh")
    d["system/snappyHexMeshDict"] = _foam_file("dictionary", "snappyHexMeshDict", "system") + (
        "castellatedMesh true;\nsnap true;\naddLayers false;\n\n"
        "geometry\n{\n"
        f"    {stl}\n    {{\n        type triSurfaceMesh;\n        name windinghead;\n    }}\n}}\n\n"
        "castellatedMeshControls\n{\n"
        "    maxLocalCells 1000000;\n    maxGlobalCells 3000000;\n    minRefinementCells 10;\n"
        "    nCellsBetweenLevels 2;\n    resolveFeatureAngle 30;\n    allowFreeStandingZoneFaces true;\n"
        "    features\n    (\n"
        f"        {{ file \"{surf_feat}\"; level {refine}; }}\n    );\n"
        "    refinementSurfaces\n    {\n"
        f"        windinghead {{ level ({refine} {refine}); patchInfo {{ type wall; }} }}\n    }}\n"
        "    refinementRegions {}\n"
        f"    locationInMesh ({loc[0]:.6g} {loc[1]:.6g} {loc[2]:.6g});\n"
        "}\n\n"
        "snapControls\n{\n    nSmoothPatch 3;\n    tolerance 2.0;\n    nSolveIter 30;\n"
        "    nRelaxIter 5;\n    nFeatureSnapIter 10;\n    implicitFeatureSnap false;\n"
        "    explicitFeatureSnap true;\n    multiRegionFeatureSnap false;\n}\n\n"
        "addLayersControls\n{\n    relativeSizes true;\n    layers {}\n    expansionRatio 1.0;\n"
        "    finalLayerThickness 0.3;\n    minThickness 0.1;\n    nGrow 0;\n"
        "    featureAngle 60;\n    nRelaxIter 3;\n    nSmoothSurfaceNormals 1;\n"
        "    nSmoothNormals 3;\n    nSmoothThickness 10;\n    maxFaceThicknessRatio 0.5;\n"
        "    maxThicknessToMedialRatio 0.3;\n    minMedialAxisAngle 90;\n    nBufferCellsNoExtrude 0;\n"
        "    nLayerIter 50;\n}\n\n"
        "meshQualityControls\n{\n"
        "    maxNonOrtho 65;\n    maxBoundarySkewness 20;\n    maxInternalSkewness 4;\n"
        "    maxConcave 80;\n    minVol 1e-13;\n    minTetQuality 1e-15;\n    minArea -1;\n"
        "    minTwist 0.02;\n    minDeterminant 0.001;\n    minFaceWeight 0.02;\n"
        "    minVolRatio 0.01;\n    minTriangleTwist -1;\n    nSmoothScale 4;\n"
        "    errorReduction 0.75;\n    relaxed { maxNonOrtho 75; }\n}\n"
        "writeFlags ( scalarLevels );\nmergeTolerance 1e-6;\n")

    # --- constant/transportProperties (Öl + Luft) ---
    d["constant/transportProperties"] = _foam_file("dictionary", "transportProperties", "constant") + (
        "phases (oil air);\n\n"
        "oil\n{\n    transportModel  Newtonian;\n"
        f"    nu              {nu_oil:g};\n    rho             {rho_oil:g};\n}}\n\n"
        "air\n{\n    transportModel  Newtonian;\n"
        f"    nu              {NU_AIR:g};\n    rho             {RHO_AIR:g};\n}}\n\n"
        f"sigma           {sigma:g};\n")

    # --- constant/g ---
    d["constant/g"] = _foam_file("uniformDimensionedVectorField", "g", "constant") + (
        "dimensions [0 1 -2 0 0 0 0];\nvalue (0 -9.81 0);\n")

    # --- constant/turbulenceProperties ---
    d["constant/turbulenceProperties"] = _foam_file(
        "dictionary", "turbulenceProperties", "constant") + "simulationType laminar;\n"

    # --- 0/alpha.oil ---
    d["0/alpha.oil"] = _foam_file("volScalarField", "alpha.oil", "0") + (
        "dimensions [0 0 0 0 0 0 0];\ninternalField uniform 0;\n\nboundaryField\n{\n"
        "    inlet       { type fixedValue; value uniform 1; }\n"
        "    atmosphere  { type inletOutlet; inletValue uniform 0; value uniform 0; }\n"
        "    windinghead { type zeroGradient; }\n}\n")

    # --- 0/U ---
    d["0/U"] = _foam_file("volVectorField", "U", "0") + (
        "dimensions [0 1 -1 0 0 0 0];\ninternalField uniform (0 0 0);\n\nboundaryField\n{\n"
        f"    inlet       {{ type fixedValue; value uniform (0 {-abs(jet_v):g} 0); }}\n"
        "    atmosphere  { type pressureInletOutletVelocity; value uniform (0 0 0); }\n"
        "    windinghead { type noSlip; }\n}\n")

    # --- 0/p_rgh ---
    d["0/p_rgh"] = _foam_file("volScalarField", "p_rgh", "0") + (
        "dimensions [1 -1 -2 0 0 0 0];\ninternalField uniform 0;\n\nboundaryField\n{\n"
        "    inlet       { type fixedFluxPressure; value uniform 0; }\n"
        "    atmosphere  { type totalPressure; p0 uniform 0; value uniform 0; }\n"
        "    windinghead { type fixedFluxPressure; value uniform 0; }\n}\n")

    return d


# ── benetzte Fläche (Kern unit-testbar) ──────────────────────────────────────

def wetted_fraction(alpha, area, thresh: float = 0.5) -> float:
    """Flächengewichteter Öl-Benetzungsanteil einer Wand: Σ Fläche(α>thresh) / Σ Fläche.
    ``alpha``/``area`` = gleich lange Sequenzen (pro Randface). REIN → unit-testbar."""
    import numpy as np
    a = np.asarray(alpha, dtype=float)
    ar = np.asarray(area, dtype=float)
    tot = float(ar.sum())
    if tot <= 0:
        return 0.0
    return float(ar[a > thresh].sum() / tot)


# ── STL-Skalierung + Domäne (brauchen vtk) ───────────────────────────────────

def _scale_stl_to_meters(src: str, dst: str, scale: float = 1e-3):
    """STL (FreeCAD-mm) → skalierte ASCII-STL (Meter) via vtk. Rückgabe: (bounds_m, n_tris).
    bounds_m = (xmin,ymin,zmin, xmax,ymax,zmax) in Metern."""
    import vtk
    rd = vtk.vtkSTLReader(); rd.SetFileName(src); rd.Update()
    poly = rd.GetOutput()
    tf = vtk.vtkTransform(); tf.Scale(scale, scale, scale)
    tpd = vtk.vtkTransformPolyDataFilter(); tpd.SetTransform(tf)
    tpd.SetInputData(poly); tpd.Update()
    out = tpd.GetOutput()
    wr = vtk.vtkSTLWriter(); wr.SetFileName(dst); wr.SetFileTypeToASCII()
    wr.SetInputData(out); wr.Write()
    b = out.GetBounds()   # (xmin,xmax, ymin,ymax, zmin,zmax)
    bounds_m = (b[0], b[2], b[4], b[1], b[3], b[5])
    return bounds_m, out.GetNumberOfCells()


def _domain_from_bounds(bm, up_margin=1.2, down_margin=1.3, side_margin=0.4):
    """Domänen-Box um die Wickelkopf-Bounds: Platz oben (+Y, Ring/Einlass), unten (-Y, Ablauf)
    und seitlich. Rückgabe (xmin,ymin,zmin, xmax,ymax,zmax) in Metern + charakteristische Länge."""
    xmin, ymin, zmin, xmax, ymax, zmax = bm
    sx, sy, sz = (xmax - xmin), (ymax - ymin), (zmax - zmin)
    s = max(sx, sy, sz, 1e-3)
    dom = (xmin - side_margin * s, ymin - down_margin * s, zmin - side_margin * s,
           xmax + side_margin * s, ymax + up_margin * s, zmax + side_margin * s)
    L_char = max(2e-3, 0.5 * (sx + sz))   # radiale/axiale Wickelkopf-Charakteristik
    return dom, L_char


# ── Case bauen + lösen (brauchen OpenFOAM) ───────────────────────────────────

def _write_case(case_dir: str, cfg: dict, stl_src_m: str):
    """Schreibt alle Dicts + kopiert die (bereits meter-skalierte) STL nach
    constant/triSurface/windinghead.stl."""
    import shutil
    dicts = build_case_dicts(cfg)
    for rel, content in dicts.items():
        p = os.path.join(case_dir, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(content)
    tri = os.path.join(case_dir, "constant", "triSurface")
    os.makedirs(tri, exist_ok=True)
    shutil.copy(stl_src_m, os.path.join(tri, cfg.get("stl_name", "windinghead.stl")))


def _prep_case(payload, work_dir, progress_cb=None):
    """Geometrie exportieren (FreeCAD-STL, geteilt mit 💧), auf Meter skalieren, Domäne bestimmen,
    Case schreiben, Netz bauen (blockMesh → surfaceFeatureExtract → snappyHexMesh).
    Rückgabe: (case_dir, cfg) — cfg trägt bbox/jet_v/L_char für den Parser."""
    import openfoam_runner as ofr
    import ema_oilspray
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)

    geom  = payload.get("geom") or {}
    axial = float(payload.get("axial_len", geom.get("axialLen", 100.0)))
    cfd   = payload.get("cfd") or {}
    section_slots = int(cfd.get("section_slots", 3))

    case_dir = os.path.join(work_dir, "cfd_case")
    os.makedirs(case_dir, exist_ok=True)

    # 1) Wickelkopf-Ausschnitt als STL (nur Wickelkopf, kein Kern → fokussiertes, sauberes Netz)
    _log("🧩 Wickelkopf-Ausschnitt in FreeCAD exportieren …", 8)
    parts, plog = ema_oilspray._export_winding_stl(
        geom, axial, work_dir, section_slots, include_core=False,
        progress_cb=lambda m, p=None: _log(m, p))
    if not parts or "winding" not in parts:
        raise RuntimeError(f"Wickelkopf-STL-Export fehlgeschlagen: {plog}")
    stl_mm = parts["winding"]

    # 2) auf Meter skalieren + Bounds
    _log("📐 STL auf Meter skalieren + Domäne bestimmen …", 16)
    stl_m = os.path.join(work_dir, "windinghead_m.stl")
    bounds_m, n_tris = _scale_stl_to_meters(stl_mm, stl_m)
    dom, L_char = _domain_from_bounds(bounds_m)

    jet_v = jet_velocity(float(cfd.get("pressure_bar", 3.0)))
    visc  = float(cfd.get("viscosity", NU_OIL))
    end_t = float(cfd.get("end_time", 0.05))
    cfg = {"bbox": dom, "jet_v": jet_v, "end_time": end_t,
           "delta_t": float(cfd.get("delta_t", 1e-5)),
           "write_interval": float(cfd.get("write_interval", max(end_t / 20.0, 1e-3))),
           "n_cells": int(cfd.get("n_cells", 44)), "refine": int(cfd.get("refine", 2)),
           "nu_oil": visc, "rho_oil": float(cfd.get("rho_oil", RHO_OIL)),
           "sigma": float(cfd.get("sigma", SIGMA_OIL)),
           "stl_name": "windinghead.stl",
           # Parser-Kennwerte:
           "L_char": L_char, "nozzle_d_mm": float(cfd.get("nozzle_d_mm", 1.0)),
           "n_tris": n_tris}

    # 3) Case schreiben + Netz
    _log("🧱 OpenFOAM-Case schreiben …", 22)
    _write_case(case_dir, cfg, stl_m)
    _log("🔲 blockMesh …", 26)
    r = ofr.run_blockmesh(case_dir, progress_cb=lambda m: _log(m))
    if not r.get("ok"):
        raise RuntimeError("blockMesh fehlgeschlagen: " + (r.get("tail") or ""))
    _log("📎 surfaceFeatureExtract …", 30)
    ofr.run_surface_features(case_dir, progress_cb=lambda m: _log(m))
    _log("🪚 snappyHexMesh (Netz um den Wickelkopf) …", 34)
    r = ofr.run_snappy(case_dir, progress_cb=lambda m: _log(m))
    if not r.get("ok"):
        raise RuntimeError("snappyHexMesh fehlgeschlagen: " + (r.get("tail") or ""))
    return case_dir, cfg


def _solve(case_dir, cfg, progress_cb=None, cancel_cb=None):
    import openfoam_runner as ofr
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    _log("🌊 interFoam (VOF-Zweiphasenströmung) …", 45)
    r = ofr.run_solver("interFoam", case_dir, progress_cb=lambda m: _log(m, None))
    if r.get("aborted"):
        return "aborted"
    if not r.get("ok"):
        raise RuntimeError("interFoam fehlgeschlagen: " + (r.get("tail") or ""))
    return "done"


# ── Ergebnis parsen (foamToVTK + vtk) ────────────────────────────────────────

def _wetted_from_vtp(vtp_path: str, thresh: float = 0.5):
    """Liest ein windinghead-Rand-VTP (foamToVTK) → (wetted_frac, total_area_m2).
    Nutzt die Zellflächen als Gewicht und das α_oil-Feld."""
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy
    rd = vtk.vtkXMLPolyDataReader(); rd.SetFileName(vtp_path); rd.Update()
    poly = rd.GetOutput()
    cs = vtk.vtkCellSizeFilter(); cs.SetInputData(poly)
    cs.ComputeAreaOn(); cs.ComputeVolumeOff(); cs.ComputeLengthOff(); cs.ComputeVertexCountOff()
    cs.SetAreaArrayName("Area"); cs.Update()
    out = cs.GetOutput()
    cd = out.GetCellData()
    area = vtk_to_numpy(cd.GetArray("Area"))
    a = cd.GetArray("alpha.oil")
    if a is None:                                     # foamToVTK schreibt Punkt- ODER Zelldaten
        pd = out.GetPointData().GetArray("alpha.oil")
        if pd is not None:                            # Punkt→Zelle mitteln
            p2c = vtk.vtkPointDataToCellData(); p2c.SetInputData(out); p2c.Update()
            a = p2c.GetOutput().GetCellData().GetArray("alpha.oil")
    alpha = vtk_to_numpy(a) if a is not None else area * 0.0
    return wetted_fraction(alpha, area, thresh), float(area.sum())


def _find_boundary_vtps(case_dir: str):
    """Alle windinghead-Rand-VTPs (je Schreibzeitpunkt), nach Zeit sortiert."""
    import glob
    pats = [os.path.join(case_dir, "VTK", "**", "windinghead*.vtp"),
            os.path.join(case_dir, "VTK", "windinghead", "*.vtp")]
    files = []
    for p in pats:
        files += glob.glob(p, recursive=True)
    # nach eingebetteter Zeit-/Indexnummer sortieren
    def _key(f):
        import re
        m = re.findall(r"(\d+)", os.path.basename(f))
        return int(m[-1]) if m else 0
    return sorted(set(files), key=_key)


def _parse(case_dir, cfg, charts_dir, progress_cb=None):
    """foamToVTK → Benetzung je Zeitschritt → HTC (Stufe-1-Korrelation) + Film-Chart."""
    import openfoam_runner as ofr
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    _log("📤 foamToVTK (Randflächen exportieren) …", 82)
    ofr.run_foamtovtk(case_dir, progress_cb=lambda m: _log(m))
    vtps = _find_boundary_vtps(case_dir)
    if not vtps:
        raise RuntimeError("Keine Randflächen-VTP von foamToVTK gefunden (windinghead).")
    series, total_area = [], 0.0
    for i, f in enumerate(vtps):
        try:
            wf, ta = _wetted_from_vtp(f)
        except Exception:
            continue
        series.append(round(100.0 * wf, 2)); total_area = ta or total_area
    if not series:
        raise RuntimeError("Benetzung nicht auswertbar (α_oil fehlt im Rand-VTP).")
    # stabiler Endwert: Mittel der letzten 3 Schreibzeitpunkte
    tail = series[-3:] if len(series) >= 3 else series
    wetted_mean = round(sum(tail) / len(tail), 2)
    wetted_peak = round(max(series), 2)
    wetted_frac = wetted_mean / 100.0
    wetted_area_m2 = round(wetted_frac * total_area, 6)

    htc = htc_model(cfg["jet_v"], cfg.get("nozzle_d_mm", 1.0), wetted_frac,
                    cfg.get("L_char", 0.02),
                    props={"nu": cfg.get("nu_oil", NU_OIL)})

    chart = _film_chart(series, charts_dir)
    last_vtp = vtps[-1]
    return {"series_pct": series, "wetted_pct_mean": wetted_mean, "wetted_pct_peak": wetted_peak,
            "wetted_area_m2": wetted_area_m2, "total_area_m2": round(total_area, 6),
            "htc": htc, "chart": chart, "vtp_path": last_vtp}


def _film_chart(series_pct, charts_dir):
    """Benetzte Fläche % über die Schreibzeitpunkte → base64 + Datei charts/cfd_wetting.png."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(charts_dir, exist_ok=True)
    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.plot(range(len(series_pct)), series_pct, color="#2c7fb8", lw=2, marker="o", ms=3)
    ax.fill_between(range(len(series_pct)), series_pct, color="#2c7fb8", alpha=0.15)
    ax.set_xlabel("Schreibzeitpunkt"); ax.set_ylabel("benetzte Wickelkopf-Fläche [%]")
    ax.set_title("VOF-Benetzung über die Zeit (interFoam)")
    ax.grid(alpha=0.3)
    import io
    buf = io.BytesIO(); fig.tight_layout(); fig.savefig(buf, format="png", dpi=110)
    plt.close(fig)
    b64 = base64.b64encode(buf.getvalue()).decode()
    try:
        with open(os.path.join(charts_dir, "cfd_wetting.png"), "wb") as f:
            f.write(base64.b64decode(b64))
    except OSError:
        pass
    return b64


# ── 3D-Visualisierung: Öl-Isofläche (alpha.oil=0.5) + Video + Browser-VTP ─────
#
# interFoam rechnet die Öl/Luft-Grenzfläche über die Zeit (`alpha.oil` je Zeitschritt in
# `VTK/cfd_case_<N>/internal.vtu`). Daraus wird — physikalisch gerechnet, im Gegensatz zum
# qualitativen Mantaflow-💧 — die Öloberfläche als **Isofläche alpha.oil=0.5** getract und
#   (a) je Zeitschritt offscreen gerendert → `frames_cfd/anim.mp4` (Strahlflug/Aufprall/Film),
#   (b) der letzte Zeitschritt als schlanke .vtp für den eingebetteten vtk.js-Browser-Viewer
#       exportiert (Öl-Isofläche nach |U| eingefärbt + Wickelkopf-Oberfläche als Kontext).
# Reuse: `ema_em3d._write_vtp` (vtk.js-lesbares .vtp) + `ema_em3d._encode_video` (ffmpeg).

_ISO = 0.5                        # alpha.oil-Isowert = Öl/Luft-Grenzfläche
_OIL_RGB = (0.95, 0.62, 0.12)     # Bernstein (Öl)
_SOLID_RGB = (0.72, 0.45, 0.20)   # Kupfer (Wickelkopf)


def _internal_vtus(case_dir: str):
    """Alle internen Volumen-VTUs (je Schreibzeitpunkt), nach eingebettetem Index sortiert.
    Der Zeitschritt 0 (Startfeld, kein Öl) wird übersprungen."""
    import glob, re
    files = glob.glob(os.path.join(case_dir, "VTK", "*", "internal.vtu"))

    def _idx(f):
        m = re.findall(r"_(\d+)", os.path.basename(os.path.dirname(f)))
        return int(m[-1]) if m else 0
    files = sorted(set(files), key=_idx)
    return [f for f in files if _idx(f) > 0] or files


def _read_vtu(path: str):
    import vtk
    rd = vtk.vtkXMLUnstructuredGridReader(); rd.SetFileName(path); rd.Update()
    return rd.GetOutput()


def _with_umag_points(grid):
    """Sorgt für Punkt-Arrays ``alpha.oil`` (für den Contour) und ``Umag`` (|U|, Einfärbung).
    foamToVTK schreibt beide als Punkt- UND Zelldaten; fehlt das Punkt-α, aus Zelle mitteln."""
    import vtk
    import numpy as np
    from vtk.util import numpy_support as ns
    pd = grid.GetPointData()
    if pd.GetArray("alpha.oil") is None:
        p2c = vtk.vtkCellDataToPointData(); p2c.SetInputData(grid); p2c.Update()
        grid = p2c.GetOutput(); pd = grid.GetPointData()
    U = pd.GetArray("U")
    if U is not None:
        umag = np.linalg.norm(ns.vtk_to_numpy(U).reshape(-1, 3), axis=1).astype(np.float32)
        ua = ns.numpy_to_vtk(umag); ua.SetName("Umag"); pd.AddArray(ua)
    return grid


def _oil_isosurface(grid):
    """Öl/Luft-Grenzfläche als vtkPolyData (Isofläche ``alpha.oil=0.5``), Punkt-Skalar ``Umag``."""
    import vtk
    grid = _with_umag_points(grid)
    grid.GetPointData().SetActiveScalars("alpha.oil")
    cont = vtk.vtkContourFilter(); cont.SetInputData(grid)
    cont.SetValue(0, _ISO); cont.ComputeScalarsOff(); cont.ComputeNormalsOn()
    cont.Update()
    return cont.GetOutput()


def _winding_surface(case_dir: str):
    """Wickelkopf-Wandfläche (letztes windinghead-Rand-VTP) als vtkPolyData — statischer
    Geometrie-Kontext für Video + Viewer (Benetzung α_oil als Punkt-Skalar bleibt erhalten)."""
    import vtk
    vtps = _find_boundary_vtps(case_dir)
    if not vtps:
        return None
    rd = vtk.vtkXMLPolyDataReader(); rd.SetFileName(vtps[-1]); rd.Update()
    return rd.GetOutput()


def _lean_scalar_poly(poly, keep: str):
    """Behält nur EIN Punkt-Skalar als **float32** (klein + vtk.js-lesbar); Zelldaten leeren."""
    import numpy as np
    from vtk.util import numpy_support as ns
    if poly is None:
        return None
    pdp = poly.GetPointData()
    src = pdp.GetArray(keep)
    if src is not None:                          # als float32 neu setzen (Alignment für vtk.js)
        vals = ns.vtk_to_numpy(src).astype(np.float32)
        arr = ns.numpy_to_vtk(vals); arr.SetName(keep)
        for nm in [pdp.GetArrayName(i) for i in range(pdp.GetNumberOfArrays())]:
            pdp.RemoveArray(nm)
        pdp.AddArray(arr); pdp.SetActiveScalars(keep)
    else:
        for nm in [pdp.GetArrayName(i) for i in range(pdp.GetNumberOfArrays())]:
            pdp.RemoveArray(nm)
    poly.GetCellData().Initialize()
    return poly


def export_browser_cfd(case_dir: str, out_oil: str, out_solid: str):
    """Schreibt zwei schlanke .vtp für den vtk.js-Browser-Viewer:
      * ``out_oil``   — Öl-Isofläche des LETZTEN Zeitschritts, Skalar ``Umag`` (|U|),
      * ``out_solid`` — Wickelkopf-Oberfläche, Skalar ``alpha.oil`` (Benetzung).
    Rückgabe (oil_path|None, solid_path|None)."""
    import ema_em3d
    op = sp = None
    vtus = _internal_vtus(case_dir)
    if vtus:
        try:
            iso = _lean_scalar_poly(_oil_isosurface(_read_vtu(vtus[-1])), "Umag")
            if iso is not None and iso.GetNumberOfPoints() > 0:
                ema_em3d._write_vtp(iso, out_oil); op = out_oil
        except Exception:
            op = None
    try:
        solid = _lean_scalar_poly(_winding_surface(case_dir), "alpha.oil")
        if solid is not None and solid.GetNumberOfPoints() > 0:
            ema_em3d._write_vtp(solid, out_solid); sp = out_solid
    except Exception:
        sp = None
    return op, sp


def _cfd_video(case_dir: str, frames_dir: str, cfg: dict, progress_cb=None):
    """Rendert je Zeitschritt die Öl-Isofläche + den Wickelkopf offscreen (feste Kamera,
    |U|-Einfärbung mit fester Skala 0..jet_v → das Feldwachstum bleibt vergleichbar) und
    encodiert die Frames zu ``frames_cfd/anim.mp4``. Rückgabe: True bei erfolgreichem Video."""
    import vtk
    import ema_em3d
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    vtus = _internal_vtus(case_dir)
    if not vtus:
        return False
    os.makedirs(frames_dir, exist_ok=True)

    solid = _winding_surface(case_dir)
    vmax = max(1e-3, float(cfg.get("jet_v", 21.0)))
    ctf = vtk.vtkColorTransferFunction()
    ctf.AddRGBPoint(0.0,        0.10, 0.20, 0.55)   # langsam = blau
    ctf.AddRGBPoint(0.35 * vmax, 0.15, 0.65, 0.75)
    ctf.AddRGBPoint(0.70 * vmax, 0.95, 0.62, 0.12)  # Öl-Bernstein
    ctf.AddRGBPoint(vmax,       0.95, 0.25, 0.15)   # schnell = rot

    ren = vtk.vtkRenderer(); ren.SetBackground(0.05, 0.05, 0.08)
    rw = vtk.vtkRenderWindow(); rw.SetOffScreenRendering(1); rw.AddRenderer(ren)
    rw.SetSize(900, 760)

    # statischer Wickelkopf (grau/kupfer, opak) als Geometrie-Kontext
    if solid is not None and solid.GetNumberOfPoints() > 0:
        sm = vtk.vtkPolyDataMapper(); sm.SetInputData(solid); sm.ScalarVisibilityOff()
        sa = vtk.vtkActor(); sa.SetMapper(sm)
        sa.GetProperty().SetColor(*_SOLID_RGB)
        sa.GetProperty().SetAmbient(0.3); sa.GetProperty().SetDiffuse(0.8)
        ren.AddActor(sa)

    oil_mapper = vtk.vtkPolyDataMapper(); oil_mapper.SetLookupTable(ctf)
    oil_mapper.SetScalarModeToUsePointFieldData(); oil_mapper.SelectColorArray("Umag")
    oil_mapper.SetScalarRange(0.0, vmax); oil_mapper.InterpolateScalarsBeforeMappingOn()
    oil_actor = vtk.vtkActor(); oil_actor.SetMapper(oil_mapper)
    oil_actor.GetProperty().SetOpacity(0.72)
    ren.AddActor(oil_actor)

    # feste Kamera aus den Wickelkopf-Bounds (leichte Iso-Perspektive)
    ref = solid if (solid is not None and solid.GetNumberOfPoints() > 0) else _oil_isosurface(_read_vtu(vtus[-1]))
    b = ref.GetBounds()
    cx, cy, cz = (b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2
    diag = max(1e-3, math.dist((b[0], b[2], b[4]), (b[1], b[3], b[5])))
    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(cx, cy, cz)
    cam.SetPosition(cx + 0.9 * diag, cy + 0.55 * diag, cz + 1.1 * diag)
    cam.SetViewUp(0, 1, 0)
    ren.ResetCameraClippingRange()

    n = len(vtus)
    for i, vtu in enumerate(vtus):
        try:
            iso = _oil_isosurface(_read_vtu(vtu))
        except Exception:
            iso = vtk.vtkPolyData()
        oil_mapper.SetInputData(iso)
        oil_mapper.Modified()
        rw.Render()
        w2i = vtk.vtkWindowToImageFilter(); w2i.SetInput(rw); w2i.Update()
        wr = vtk.vtkPNGWriter()
        wr.SetFileName(os.path.join(frames_dir, "frame_%04d.png" % i))
        wr.SetInputConnection(w2i.GetOutputPort()); wr.Write()
        if progress_cb and n:
            _log("🎬 Video-Frame %d/%d …" % (i + 1, n), 88 + int(8 * (i + 1) / n))
    mp4 = ema_em3d._encode_video(frames_dir, fps=8)
    return bool(mp4)


# ── Orchestrator + Persistenz ────────────────────────────────────────────────

def run_cfd(payload, project_dir, progress_cb=None, cancel_cb=None):
    """End-to-End: STL → Case+Netz → interFoam → Benetzung/HTC → persistiert results["cfd"].
    Rückgabe = das schlanke cfd-Ergebnisdict (mit base64-Chart, wie run_oilspray)."""
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    work = os.path.join(project_dir, "cfd")
    os.makedirs(work, exist_ok=True)
    charts_dir = os.path.join(project_dir, "charts")

    _log("🌊 OpenFOAM-VOF-Kühlung startet …", 2)
    case_dir, cfg = _prep_case(payload, work, progress_cb=_log)
    if cancel_cb and cancel_cb():
        return {"aborted": True}
    st = _solve(case_dir, cfg, progress_cb=_log, cancel_cb=cancel_cb)
    if st == "aborted":
        return {"aborted": True}
    parsed = _parse(case_dir, cfg, charts_dir, progress_cb=_log)

    # 3D-Öloberfläche: Browser-VTPs (Isofläche + Wickelkopf) + Animations-Video.
    oil_vtp = solid_vtp = None
    has_video = False
    make_video = bool((payload.get("cfd") or {}).get("make_video", True))
    try:
        _log("🧊 Öl-Isofläche für den Browser-Viewer exportieren …", 84)
        oil_vtp, solid_vtp = export_browser_cfd(
            case_dir, os.path.join(work, "cfd_oil.vtp"), os.path.join(work, "cfd_solid.vtp"))
    except Exception as e:
        _log("⚠ Isoflächen-Export übersprungen: %s" % e)
    if make_video:
        try:
            has_video = _cfd_video(case_dir, os.path.join(project_dir, "frames_cfd"), cfg,
                                   progress_cb=_log)
        except Exception as e:
            _log("⚠ Video-Erzeugung übersprungen: %s" % e)

    htc = parsed["htc"]
    result = {
        "source": "openfoam_interfoam",
        "config": {"pressure_bar": float((payload.get("cfd") or {}).get("pressure_bar", 3.0)),
                   "section_slots": int((payload.get("cfd") or {}).get("section_slots", 3)),
                   "end_time": cfg["end_time"], "n_cells": cfg["n_cells"],
                   "refine": cfg["refine"], "nu_oil": cfg["nu_oil"],
                   "nozzle_d_mm": cfg.get("nozzle_d_mm", 1.0), "jet_v_mps": round(cfg["jet_v"], 2)},
        "htc_eff": htc["htc_eff"],
        "htc_detail": htc,
        "wetted_pct_mean": parsed["wetted_pct_mean"],
        "wetted_pct_peak": parsed["wetted_pct_peak"],
        "wetted_area_m2": parsed["wetted_area_m2"],
        "total_area_m2": parsed["total_area_m2"],
        "series_pct": parsed["series_pct"],
        "images": {"cfd_wetting": parsed["chart"]},
        "vtp_path": parsed["vtp_path"],
        "oil_vtp_path": oil_vtp,
        "solid_vtp_path": solid_vtp,
        "video": has_video,
        "scope_note": SCOPE_NOTE,
    }
    _persist_cfd_summary(project_dir, result)
    _log("✓ OpenFOAM-VOF-Kühlung fertig — HTC_eff = %.0f W/m²·K (benetzt ⌀ %.1f %%)."
         % (htc["htc_eff"], parsed["wetted_pct_mean"]), 100)
    return result


def _persist_cfd_summary(project_dir, result):
    """Schlanke Zusammenfassung (ohne base64-Bilder; Chart liegt als Datei in charts/) in die
    results.json mergen (Muster ema_oilspray._persist / ema_em3d._persist_em3d_summary).
    Legt results.json an, falls sie fehlt (CFD-Lauf ohne vorherige Analyse)."""
    rj = os.path.join(project_dir, "results.json")
    try:
        data = {}
        if os.path.exists(rj):
            with open(rj) as f:
                data = json.load(f)
        _drop = ("images", "vtp_path", "oil_vtp_path", "solid_vtp_path")
        lean = {k: v for k, v in result.items() if k not in _drop}
        lean["image_files"] = {k: "charts/%s.png" % k for k in result.get("images", {})}
        # transiente Case-Pfade NICHT persistieren; nur das Video-Flag bleibt (bool).
        data["cfd"] = lean
        tmp = rj + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, rj)
    except (OSError, ValueError):
        pass
