"""Elmer-FEM-Subprozess-Wrapper (analog `freecad_runner`).

Stellt die beiden Schritte der Elmer-Toolchain als Funktionen bereit:
  run_elmergrid(msh_path, out_dir)  — Gmsh-MSH → Elmer-Mesh-Verzeichnis (ElmerGrid 14 2).
  run_elmersolver(sif_path, cwd)    — löst case.sif (ElmerSolver).

Binaries werden über PATH gesucht (nach `apt install elmerfem-csc`). `ELMER_OK` zeigt die
Verfügbarkeit fürs UI/Server-Gating.
"""

import os
import shutil
import subprocess

ELMERGRID = shutil.which("ElmerGrid")
ELMERSOLVER = shutil.which("ElmerSolver")
ELMER_OK = bool(ELMERGRID and ELMERSOLVER)

INSTALL_HINT = ("Elmer nicht gefunden. Installation:\n"
                "  sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa\n"
                "  sudo apt-get update && sudo apt-get install -y elmerfem-csc")


def run_elmergrid(msh_path: str, out_dir: str, timeout: int = 600) -> dict:
    """Konvertiert ein Gmsh-MSH (2.2) in ein Elmer-Mesh-Verzeichnis ``out_dir``.

    ElmerGrid 14 2 <msh> -out <out_dir>  (14 = Gmsh-Eingang, 2 = Elmer-Ausgang)."""
    if not ELMERGRID:
        return {"ok": False, "error": "ElmerGrid fehlt", "stdout": "", "stderr": INSTALL_HINT}
    # WICHTIG: das Mesh-Verzeichnis bei JEDEM Lauf frisch aufsetzen. Sonst bleibt bei einer
    # geänderten Geometrie das alte mesh.* eines früheren Laufs liegen (das Normalisieren
    # unten verschiebt nur, wenn noch keine mesh.header existiert) und Elmer rechnet auf
    # dem ALTEN Modell weiter („Geometrie ändert sich nicht"). Vollständig leeren + neu anlegen.
    shutil.rmtree(out_dir, ignore_errors=True)
    os.makedirs(out_dir, exist_ok=True)
    try:
        proc = subprocess.run(
            [ELMERGRID, "14", "2", msh_path, "-out", out_dir, "-autoclean"],
            capture_output=True, text=True, timeout=timeout)
        # ElmerGrid schreibt mesh.* nach <out_dir>/<basename> — auf out_dir normalisieren.
        base = os.path.splitext(os.path.basename(msh_path))[0]
        nested = os.path.join(out_dir, base)
        if os.path.isdir(nested) and not os.path.exists(os.path.join(out_dir, "mesh.header")):
            for fn in os.listdir(nested):
                shutil.move(os.path.join(nested, fn), os.path.join(out_dir, fn))
        ok = os.path.exists(os.path.join(out_dir, "mesh.header"))
        return {"ok": ok, "stdout": proc.stdout, "stderr": proc.stderr,
                "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ElmerGrid Timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": str(e)}


def run_elmersolver(sif_path: str, cwd: str, timeout: int = 3600) -> dict:
    """Löst eine Elmer-Fallbeschreibung. ``sif_path`` relativ zu ``cwd`` (ElmerSolver
    sucht standardmäßig ELMERSOLVER_STARTINFO / case.sif im cwd)."""
    if not ELMERSOLVER:
        return {"ok": False, "error": "ElmerSolver fehlt", "stdout": "", "stderr": INSTALL_HINT}
    try:
        proc = subprocess.run([ELMERSOLVER, os.path.basename(sif_path)],
                              capture_output=True, text=True, timeout=timeout, cwd=cwd)
        out = proc.stdout or ""
        ok = "ELMER SOLVER FINISHED" in out.upper() or "*** Elmer Solver: ALL DONE" in out
        return {"ok": ok, "stdout": out, "stderr": proc.stderr or "",
                "returncode": proc.returncode}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "ElmerSolver Timeout", "stdout": "", "stderr": ""}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": str(e)}
