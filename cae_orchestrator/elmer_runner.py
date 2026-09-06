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
import threading

ELMERGRID = shutil.which("ElmerGrid")
ELMERSOLVER = shutil.which("ElmerSolver")
ELMER_OK = bool(ELMERGRID and ELMERSOLVER)

# Laufender ElmerSolver-Prozess (für Abbruch). run_elmersolver benutzt Popen statt
# subprocess.run und hinterlegt den Prozess hier, damit `abort_current()` ihn aus einem
# anderen Thread (dem /em3d/abort-Handler) sofort beenden kann — sonst würde ein Abbruch
# erst nach dem laufenden Solve (bis zu Minuten/`timeout`) greifen.
_PROC_LOCK = threading.Lock()
_CURRENT_PROC = None
_ABORTED = False


def abort_current() -> bool:
    """Bricht den gerade laufenden ElmerSolver-Prozess ab (falls einer läuft). Setzt ein
    Abbruch-Flag, damit ``run_elmersolver`` das Ergebnis als *abgebrochen* meldet. Gibt True
    zurück, wenn ein Prozess terminiert wurde."""
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = True
        p = _CURRENT_PROC
    if p is None:
        return False
    try:
        p.terminate()                       # SIGTERM; ElmerSolver beendet zeitnah
        try:
            p.wait(timeout=5)
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


# MUMPS meldet seine Fehler auf stdout, nicht ueber den Rueckgabewert des
# Prozesses -- und Elmer bricht darauf nicht ab. Die Meldung sieht so aus:
#
#      ** ERROR RETURN ** FROM ZMUMPS INFO(1)=  -13
#      ** INFO(2)=           -5525
#
# ``DMUMPS`` fuer reelle, ``ZMUMPS`` fuer komplexe Systeme.
_MUMPS_GRUND = {
    -13: "Speicheranforderung fehlgeschlagen (Netz zu gross fuer den Arbeitsspeicher)",
    -9:  "Arbeitsfeld zu klein",
    -8:  "Arbeitsfeld zu klein (ganzzahliger Teil)",
    -3:  "falsche Aufrufreihenfolge (Folgefehler eines frueheren Abbruchs)",
}


def _mumps_fehler(stdout: str) -> list:
    """Die MUMPS-Fehlercodes aus der Bildschirmausgabe, im Klartext."""
    import re
    aus = []
    for m in re.finditer(r"ERROR RETURN \*\* FROM [DZ]MUMPS\s+INFO\(1\)=\s*(-?\d+)",
                         stdout or ""):
        code = int(m.group(1))
        aus.append(f"INFO(1)={code} ({_MUMPS_GRUND.get(code, 'unbekannter Code')})")
    return aus


def run_elmersolver(sif_path: str, cwd: str, timeout: int = 3600) -> dict:
    """Löst eine Elmer-Fallbeschreibung. ``sif_path`` relativ zu ``cwd`` (ElmerSolver
    sucht standardmäßig ELMERSOLVER_STARTINFO / case.sif im cwd)."""
    if not ELMERSOLVER:
        return {"ok": False, "error": "ElmerSolver fehlt", "stdout": "", "stderr": INSTALL_HINT}
    global _CURRENT_PROC
    try:
        with _PROC_LOCK:
            if _ABORTED:                     # schon vor dem Start abgebrochen
                return {"ok": False, "aborted": True, "error": "abgebrochen",
                        "stdout": "", "stderr": ""}
            proc = subprocess.Popen([ELMERSOLVER, os.path.basename(sif_path)],
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, cwd=cwd)
            _CURRENT_PROC = proc
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.communicate()
            return {"ok": False, "error": "ElmerSolver Timeout", "stdout": "", "stderr": ""}
        out = out or ""
        if _ABORTED or proc.returncode < 0:  # terminiert/gekillt (Signal → negativer Code)
            return {"ok": False, "aborted": True, "error": "abgebrochen",
                    "stdout": out, "stderr": err or ""}
        ok = "ELMER SOLVER FINISHED" in out.upper() or "*** Elmer Solver: ALL DONE" in out
        # „FINISHED" heisst NICHT „gerechnet". Gemessen an einem 1,1-Mio.-Netz:
        # MUMPS steigt mit „** ERROR RETURN ** FROM ZMUMPS INFO(1)= -13" aus
        # (Speicher), Elmer rechnet mit einem Nullvektor weiter, schreibt eine
        # Ergebnisdatei und meldet ordnungsgemaess FINISHED. Der Aufrufer
        # bekommt daraufhin Verluste von 0,0 W und ein Moment von 0,000 Nm --
        # Zahlen, die wie Ergebnisse aussehen.
        #
        # MUMPS-Rueckgabecodes (INFO(1) < 0) sind Fehler, keine Warnungen:
        # -13 Speicheranforderung fehlgeschlagen, -9/-8 Arbeitsfeld zu klein,
        # -3 falsche Aufrufreihenfolge (Folgefehler). Sie werden hier zum
        # Fehlschlag gemacht, damit sie dort auffallen, wo sie entstehen.
        mumps = _mumps_fehler(out)
        if mumps:
            return {"ok": False, "stdout": out, "stderr": err or "",
                    "returncode": proc.returncode, "mumps": mumps,
                    "error": "Der direkte Loeser (MUMPS) ist ausgestiegen: "
                             + "; ".join(mumps)
                             + ". Elmer meldet trotzdem FINISHED und schreibt "
                               "eine Ergebnisdatei — sie enthaelt aber kein "
                               "Feld. Haeufigste Ursache: zu grosses Netz "
                               "(gemessen ging 437.000 Tetraeder, 1.111.000 "
                               "nicht mehr)."}
        return {"ok": ok, "stdout": out, "stderr": err or "",
                "returncode": proc.returncode}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "", "stderr": str(e)}
    finally:
        with _PROC_LOCK:
            _CURRENT_PROC = None
