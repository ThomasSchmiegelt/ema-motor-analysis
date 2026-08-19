"""Blender-Subprozess-Wrapper (analog `elmer_runner` / `freecad_runner`).

Führt ein generiertes Blender-Python-Skript **headless** aus:

    blender --background --python <script.py> -- <json-args>

und streamt dessen stdout Zeile für Zeile, um Fortschritts- und Ergebnis-Marker zu
parsen, die das Skript selbst druckt:

  OIL_STAGE:<text>            — Statuszeile (an ``progress_cb`` weitergereicht)
  OIL_FRAMES:<i>/<n>          — Bake-/Render-Fortschritt (Frame i von n)
  OIL_METRICS:<json>          — Benetzungs-/Sprüh-Kennwerte (Zeitreihen) als JSON
  OIL_DONE                    — sauberer Abschluss

Blender wird über PATH gesucht (``/usr/bin/blender``). ``BLENDER_OK`` gated das UI/den
Server. Ein laufender Bake lässt sich aus einem anderen Thread (dem /oilspray/abort-
Handler) über ``abort_current`` sofort beenden — sonst liefe er bis ``timeout``.
"""

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

def _find_blender():
    """Bevorzugt einen **portablen blender.org-Build** vor dem apt-Paket.

    Wichtig: Das Ubuntu-`apt`-Blender linkt gegen das SYSTEM-libpython → Mantaflow
    stürzt headless mit ``PyImport_AppendInittab() may not be called after
    Py_Initialize()`` ab (die Flüssigkeitssimulation ist damit unbrauchbar). Der
    portable blender.org-Build bringt sein eigenes Python mit und bäckt headless
    korrekt. Reihenfolge: $EMA_BLENDER → portable Builds unter ~/blender_portable →
    PATH (`blender`, nur als letzter Ausweg)."""
    import glob
    env = os.environ.get("EMA_BLENDER")
    if env and os.path.exists(env):
        return env
    home = os.path.expanduser("~")
    for pat in (os.path.join(home, "blender_portable", "blender-*", "blender"),
                os.path.join(home, "blender-*", "blender"),
                "/opt/blender-*/blender"):
        hits = sorted(glob.glob(pat))
        if hits:
            return hits[-1]                 # höchste Version
    return shutil.which("blender")


BLENDER = _find_blender()
# Der apt-Build (System-libpython) kann Mantaflow headless nicht bakken → nicht als
# einsatzfähig zählen (der Server 503t dann mit Install-Hinweis).
BLENDER_IS_APT = bool(BLENDER) and os.path.realpath(BLENDER) == "/usr/bin/blender"
BLENDER_OK = bool(BLENDER) and not BLENDER_IS_APT

INSTALL_HINT = ("Kein Mantaflow-taugliches Blender gefunden. Der apt-Build stürzt headless ab —\n"
                "portablen blender.org-Build installieren (bringt eigenes Python mit):\n"
                "  mkdir -p ~/blender_portable && cd ~/blender_portable\n"
                "  curl -O https://download.blender.org/release/Blender4.2/blender-4.2.9-linux-x64.tar.xz\n"
                "  tar xf blender-4.2.9-linux-x64.tar.xz\n"
                "  (oder Pfad in $EMA_BLENDER setzen)")

# Laufender Blender-Prozess (für Abbruch). ``run_blender_script`` benutzt Popen und
# hinterlegt den Prozess hier, damit ``abort_current()`` ihn terminieren kann.
_PROC_LOCK = threading.Lock()
_CURRENT_PROC = None
_ABORTED = False


def abort_current() -> bool:
    """Bricht den gerade laufenden Blender-Prozess ab (falls einer läuft). Setzt ein
    Abbruch-Flag, damit ``run_blender_script`` das Ergebnis als *abgebrochen* meldet.
    Gibt True zurück, wenn ein Prozess terminiert wurde."""
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = True
        p = _CURRENT_PROC
    if p is None:
        return False
    try:
        p.terminate()                       # SIGTERM; Blender beendet zeitnah
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


_FRAMES_RE = re.compile(r"OIL_FRAMES:(\d+)\s*/\s*(\d+)")


def run_blender_script(script_code: str, argv=None, cwd=None, timeout: int = 3600,
                       progress_cb=None) -> dict:
    """Führt ``script_code`` headless in Blender aus und parst die Marker-Zeilen.

    ``argv``       — zusätzliche Argumente nach ``--`` (das Skript liest sie via
                     ``sys.argv[sys.argv.index('--')+1:]``); hier als eine JSON-Zeichenkette.
    ``progress_cb`` — ``cb(msg, pct|None)`` für Live-Log/Fortschritt.
    Rückgabe: ``{ok, aborted, metrics, n_frames, stdout, error}``.
    """
    global _CURRENT_PROC
    if not BLENDER:
        return {"ok": False, "error": "Blender fehlt", "stdout": "", "aborted": False}

    fd, script_path = tempfile.mkstemp(suffix=".py", prefix="oilspray_")
    with os.fdopen(fd, "w") as f:
        f.write(script_code)

    cmd = [BLENDER, "--background", "--python", script_path]
    if argv:
        cmd += ["--"] + list(argv)

    metrics = None
    lines = []
    n_frames = 0
    done = False
    try:
        with _PROC_LOCK:
            if _ABORTED:                      # schon vor dem Start abgebrochen
                return {"ok": False, "aborted": True, "error": "abgebrochen",
                        "stdout": "", "metrics": None}
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True,
                                    cwd=cwd or os.getcwd(), bufsize=1)
            _CURRENT_PROC = proc
        try:
            for raw in proc.stdout:              # zeilenweises Streaming
                line = raw.rstrip("\n")
                lines.append(line)
                if len(lines) > 4000:            # Log nicht unbegrenzt wachsen lassen
                    lines = lines[-2000:]
                s = line.strip()
                if s.startswith("OIL_STAGE:"):
                    if progress_cb:
                        progress_cb(s[10:], None)
                elif s.startswith("OIL_FRAMES:"):
                    m = _FRAMES_RE.search(s)
                    if m:
                        i, n = int(m.group(1)), int(m.group(2))
                        n_frames = max(n_frames, i)
                        if progress_cb and n > 0:
                            progress_cb(f"Frame {i}/{n}", None)
                elif s.startswith("OIL_METRICS:"):
                    try:
                        metrics = json.loads(s[len("OIL_METRICS:"):])
                    except json.JSONDecodeError:
                        pass
                elif s.startswith("OIL_DONE"):
                    done = True
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.communicate()
            return {"ok": False, "error": "Blender Timeout", "stdout": "\n".join(lines),
                    "aborted": False, "metrics": metrics, "n_frames": n_frames}

        stdout = "\n".join(lines)
        if _ABORTED:
            return {"ok": False, "aborted": True, "error": "abgebrochen",
                    "stdout": stdout, "metrics": metrics, "n_frames": n_frames}
        if proc.returncode is not None and proc.returncode < 0:
            # Von einem Signal beendet OHNE Nutzer-Abbruch — praktisch immer der
            # Kernel-OOM-Killer (SIGKILL bei RAM-Erschöpfung; real gemessen: 512er
            # Fluid-Domain ~29 GB RSS). NICHT als "abgebrochen" melden, sonst sieht
            # der Nutzer einen Phantom-Abbruch statt der Ursache.
            sig = -proc.returncode
            return {"ok": False, "aborted": False,
                    "error": ("Blender wurde vom System beendet (Signal %d) — "
                              "vermutlich RAM-Mangel. Domain-Auflösung senken "
                              "oder Frames reduzieren." % sig),
                    "stdout": stdout, "metrics": metrics, "n_frames": n_frames}
        ok = bool(done) and proc.returncode == 0
        return {"ok": ok, "aborted": False, "metrics": metrics, "n_frames": n_frames,
                "stdout": stdout, "returncode": proc.returncode,
                "error": None if ok else "Blender endete ohne OIL_DONE"}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "\n".join(lines),
                "aborted": False, "metrics": metrics}
    finally:
        with _PROC_LOCK:
            _CURRENT_PROC = None
        try:
            os.unlink(script_path)
        except OSError:
            pass
