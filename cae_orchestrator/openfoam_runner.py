"""OpenFOAM-Subprozess-Wrapper (analog `elmer_runner`).

Führt OpenFOAM-Tools (blockMesh / surfaceFeatureExtract / snappyHexMesh / interFoam /
foamToVTK) in EINEM Bash-Aufruf aus, der zuerst die OpenFOAM-Umgebung sourct
(``etc/bashrc`` setzt ``WM_PROJECT_DIR`` + PATH). ``OPENFOAM_OK`` zeigt die Verfügbarkeit
fürs UI/Server-Gating.

Wie ``elmer_runner`` benutzt der Solver-Aufruf ``Popen`` statt ``subprocess.run`` und
hinterlegt den Prozess modul-global, damit ``abort_current()`` ihn aus einem anderen Thread
(dem /cfd/abort-Handler) SOFORT beenden kann — OpenFOAM-Solver reagieren auf SIGTERM und
schreiben den letzten Zeitschritt, bevor sie beenden.
"""

import os
import subprocess
import threading

# ESI-OpenACT v2406 (per apt `openfoam2406-default`). Über die bashrc gesourct, damit
# WM_PROJECT_DIR + PATH + Solver stimmen. $OPENFOAM_BASHRC überschreibt den Pfad.
FOAM_BASHRC = os.environ.get(
    "OPENFOAM_BASHRC", "/usr/lib/openfoam/openfoam2406/etc/bashrc")


def _foam_available() -> bool:
    if not os.path.exists(FOAM_BASHRC):
        return False
    try:
        p = subprocess.run(
            ["bash", "-lc", f"source '{FOAM_BASHRC}' >/dev/null 2>&1 && command -v interFoam"],
            capture_output=True, text=True, timeout=30)
        return p.returncode == 0 and bool(p.stdout.strip())
    except Exception:
        return False


OPENFOAM_OK = _foam_available()

INSTALL_HINT = (
    "OpenFOAM (v2406) nicht gefunden. Installation (ESI/OpenCFD, Ubuntu):\n"
    "  curl https://dl.openfoam.com/add-debian-repo.sh | sudo bash\n"
    "  sudo apt-get update && sudo apt-get install -y openfoam2406-default\n"
    f"Erwarteter Pfad der Umgebungsdatei: {FOAM_BASHRC}\n"
    "(oder $OPENFOAM_BASHRC auf die eigene etc/bashrc setzen)")

# Laufender OpenFOAM-Prozess (für Abbruch), analog elmer_runner.
_PROC_LOCK = threading.Lock()
_CURRENT_PROC = None
_ABORTED = False


def abort_current() -> bool:
    """Bricht den gerade laufenden OpenFOAM-Prozess ab (falls einer läuft). Setzt ein
    Abbruch-Flag, damit ``run_foam`` das Ergebnis als *abgebrochen* meldet. Gibt True zurück,
    wenn ein Prozess terminiert wurde."""
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = True
        p = _CURRENT_PROC
    if p is None:
        return False
    try:
        p.terminate()                       # SIGTERM: interFoam schreibt letzten Schritt
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()                        # notfalls hart
        return True
    except Exception:
        return False


def clear_abort():
    """Abbruch-Flag zurücksetzen (vom Start eines neuen Laufs aufzurufen)."""
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = False


def run_foam(app: str, case_dir: str, timeout: int = 3600, progress_cb=None,
             extra_args: str = "") -> dict:
    """Führt EIN OpenFOAM-Tool auf ``case_dir`` aus (``<app> -case <case_dir> <extra_args>``).

    Sourct zuerst die OpenFOAM-Umgebung. Streamt stdout zeilenweise an ``progress_cb`` (wie
    ``blender_runner.run_blender_script``). Rückgabe:
    ``{ok, aborted, returncode, tail, log_path}``. Der volle Log liegt in
    ``<case_dir>/log.<app>`` (OpenFOAM-Konvention)."""
    if not OPENFOAM_OK:
        return {"ok": False, "error": "OpenFOAM fehlt", "tail": INSTALL_HINT}
    global _CURRENT_PROC
    log_path = os.path.join(case_dir, f"log.{app}")
    cmd = f"source '{FOAM_BASHRC}' >/dev/null 2>&1 && {app} -case '{case_dir}' {extra_args} 2>&1"
    lines: list[str] = []
    try:
        with _PROC_LOCK:
            if _ABORTED:
                return {"ok": False, "aborted": True, "error": "abgebrochen", "tail": ""}
            proc = subprocess.Popen(["bash", "-lc", cmd], stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            _CURRENT_PROC = proc
        try:
            with open(log_path, "w") as lf:
                for line in proc.stdout:                 # zeilenweise streamen
                    lf.write(line)
                    lines.append(line.rstrip("\n"))
                    if len(lines) > 4000:                # Speicher zähmen
                        lines = lines[-2000:]
                    if progress_cb and (line.startswith("Time =")
                                        or line.startswith("Courant")):
                        progress_cb("FOAM_STAGE:" + line.rstrip("\n"))
        finally:
            proc.wait()
        with _PROC_LOCK:
            aborted = _ABORTED
        tail = "\n".join(lines[-40:])
        if aborted or proc.returncode < 0:
            return {"ok": False, "aborted": True, "error": "abgebrochen",
                    "returncode": proc.returncode, "tail": tail, "log_path": log_path}
        # OpenFOAM-Solver melden "End" am Ende eines erfolgreichen Laufs; die Mesh-Tools
        # geben returncode 0. Beides als Erfolg akzeptieren.
        ok = (proc.returncode == 0)
        return {"ok": ok, "aborted": False, "returncode": proc.returncode,
                "tail": tail, "log_path": log_path}
    except Exception as e:
        return {"ok": False, "error": str(e), "tail": str(e), "log_path": log_path}
    finally:
        with _PROC_LOCK:
            _CURRENT_PROC = None


# ── Dünne Convenience-Wrapper ────────────────────────────────────────────────

def run_blockmesh(case_dir, timeout=600, progress_cb=None):
    return run_foam("blockMesh", case_dir, timeout, progress_cb)


def run_surface_features(case_dir, timeout=300, progress_cb=None):
    # v2406: das Tool heißt surfaceFeatureExtract (liest system/surfaceFeatureExtractDict).
    return run_foam("surfaceFeatureExtract", case_dir, timeout, progress_cb)


def run_snappy(case_dir, timeout=1800, progress_cb=None):
    return run_foam("snappyHexMesh", case_dir, timeout, progress_cb, extra_args="-overwrite")


def run_solver(app, case_dir, timeout=7200, progress_cb=None):
    return run_foam(app, case_dir, timeout, progress_cb)


def run_foamtovtk(case_dir, timeout=600, progress_cb=None):
    return run_foam("foamToVTK", case_dir, timeout, progress_cb, extra_args="-ascii")
