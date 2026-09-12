"""FluidX3D-Subprozess-Wrapper (analog `blender_runner` / `elmer_runner`).

FluidX3D (ProjectPhysX) ist ein OpenCL-Lattice-Boltzmann-Löser mit freier
Oberfläche. Anders als Blender, Elmer oder OpenFOAM ist er **kein Programm mit
Eingabedatei**: jeder Fall ist eine C++-Funktion ``main_setup()`` in
``src/setup.cpp``, und das Programm wird dafür **neu übersetzt** (gemessen
40 s auf dieser Maschine). Dieser Wrapper macht daraus denselben Ablauf, den
die übrigen Werkzeuge hier haben — Skript erzeugen, starten, Marker streamen,
abbrechen können.

**Es wird in einer KOPIE gearbeitet, nie im Quellbaum.** Der Quellbaum
(`~/ai-workspace/FluidX3D`) trägt die Fälle des Menschen — dort steht z. B. eine
Laval-Düse —, und ein Werkzeug, das die überschreibt, ist kein Werkzeug. Die
Kopie liegt unter ``$CAE_FLUIDX3D_HEIM`` (Vorgabe ``~/fluidx3d_cae``), also
ausserhalb des Repos, wie ``~/aster-build`` und ``~/blender_portable``.

Marker, die das erzeugte Setup druckt (``ema_fluidx3d`` erzeugt sie):

  FX3D_STAGE:<text>        — Statuszeile (an ``progress_cb``)
  FX3D_STEP:<i>/<n>        — Fortschritt in Ausgabeschritten
  FX3D_DONE                — sauberer Abschluss

**Ergebnisdaten gehen in DATEIEN, nicht durch die Leitung** — und das ist keine
Geschmacksfrage: FluidX3Ds eigene Fortschrittszeile wird mit ``\r``
ueberschrieben (``info.cpp:105``, ``reprint``) und aus einem NEBENLAEUFIGEN
Thread gedruckt (``main.cpp:159``). Zeilenweises Lesen sieht deshalb einen
einzigen, sehr langen "Satz", in dem die eigenen Marker mittendrin stehen und
an dessen Ende jederzeit weitere Fortschrittszeichen angehaengt werden koennen.
Ein base64-Feld haette das nicht ueberlebt. Das erzeugte Setup schreibt darum

  <ausgabe>/fest.bin            — Festkoerpermaske des Schnitts (uint8), einmal
  <ausgabe>/schnitt_%04d.bin    — Fuellstand phi im Schnitt (uint8), je Bild
  <ausgabe>/kennwerte.json      — Kennwerte + Zeitreihe

und ``laufen`` liest sie hinterher. Der Schnitt statt des Volumens: ein
phi-Feld von 208^3 sind 36 MB je Ausgabeschritt, der Schnitt daraus 43 kB.
Uebrig bleiben im Strom nur STAGE/STEP/DONE, und die vertragen eine
verstuemmelte Zeile.

**Lizenz (FluidX3D, ProjectPhysX):** keine kommerzielle und keine militärische
Nutzung, kein KI-Training auf dem Quelltext, der Lizenzhinweis bleibt stehen,
und wer Ergebnisse einer GEÄNDERTEN Fassung veröffentlicht, muss die geänderte
Quelle veröffentlichen. Das erzeugte ``setup.cpp`` ist eine solche Änderung und
sagt das in seinem Kopf; ``vorbereiten`` legt daneben eine ``HERKUNFT.txt``.
"""

import hashlib
import json
import os
import re
import shutil
import subprocess
import threading

# ── Quellbaum und Arbeitskopie ───────────────────────────────────────────────
_QUELLEN = ("~/ai-workspace/FluidX3D", "~/FluidX3D", "/opt/FluidX3D")


def _finde_quelle():
    env = os.environ.get("CAE_FLUIDX3D_QUELLE")
    kandidaten = ([env] if env else []) + list(_QUELLEN)
    for p in kandidaten:
        p = os.path.expanduser(p)
        if os.path.exists(os.path.join(p, "src", "lbm.cpp")):
            return p
    return None


QUELLE = _finde_quelle()
HEIM = os.path.expanduser(os.environ.get("CAE_FLUIDX3D_HEIM", "~/fluidx3d_cae"))
CXX = shutil.which("g++") or shutil.which("clang++")


def _opencl_da():
    """libOpenCL muss zum Linken da sein. FluidX3D bringt die Header mit, aber
    nicht die Bibliothek — die kommt vom Treiber."""
    for p in ("/usr/lib/x86_64-linux-gnu/libOpenCL.so", "/usr/lib/libOpenCL.so",
              "/usr/lib/x86_64-linux-gnu/libOpenCL.so.1"):
        if os.path.exists(p):
            return True
    return bool(shutil.which("clinfo"))


FLUIDX3D_OK = bool(QUELLE) and bool(CXX) and _opencl_da()

INSTALL_HINT = (
    "FluidX3D nicht einsatzbereit.\n"
    "  Quellbaum: %s\n  Übersetzer: %s\n  libOpenCL: %s\n"
    "FluidX3D von https://github.com/ProjectPhysX/FluidX3D holen und nach\n"
    "~/ai-workspace/FluidX3D legen (oder $CAE_FLUIDX3D_QUELLE setzen).\n"
    "Lizenz beachten: keine kommerzielle, keine militärische Nutzung, kein\n"
    "KI-Training auf dem Quelltext, geänderte Fassungen müssen bei einer\n"
    "Veröffentlichung von Ergebnissen offengelegt werden."
    % (QUELLE or "FEHLT", CXX or "FEHLT", "ok" if _opencl_da() else "FEHLT"))

HERKUNFT_TEXT = """Arbeitskopie von FluidX3D (ProjectPhysX) fuer cae_orchestrator.

Original: https://github.com/ProjectPhysX/FluidX3D
Kopiert aus: %s

Diese Kopie ist eine GEAENDERTE FASSUNG: src/setup.cpp und src/defines.hpp
werden von `ema_fluidx3d` erzeugt bzw. gesetzt. Der uebrige Quelltext ist
unveraendert, die Lizenzdatei (LICENSE.md) liegt daneben und bleibt stehen.

Lizenzpflichten, die daran haengen:
  * keine kommerzielle Nutzung
  * keine militaerische Nutzung
  * kein Training von KI-Modellen auf dem Quelltext
  * werden Ergebnisse einer geaenderten Fassung veroeffentlicht, ist die
    geaenderte Quelle mit zu veroeffentlichen
  * der Lizenzhinweis darf nicht entfernt werden
  * wissenschaftliche Veroeffentlichungen zitieren die in README.md genannten
    Arbeiten
"""


# ── defines.hpp setzen (rein, testbar) ───────────────────────────────────────
# Die Schalter, die dieser Pfad braucht. Gemessen: ohne SURFACE gibt es keine
# freie Oberflaeche, ohne EQUILIBRIUM_BOUNDARIES keinen offenen Rand, ohne
# VOLUME_FORCE keine Schwerkraft. GRAPHICS und PARTICLES kosten nur Speicher —
# gerendert wird hier in Python aus den Schnittdaten.
DEFINES_AN  = ("SURFACE", "VOLUME_FORCE", "EQUILIBRIUM_BOUNDARIES", "FP16S")
DEFINES_AUS = ("PARTICLES", "GRAPHICS", "INTERACTIVE_GRAPHICS", "FP16C",
               "TEMPERATURE", "SUBGRID", "MOVING_BOUNDARIES", "FORCE_FIELD",
               "BENCHMARK")


def defines_setzen(text, an=DEFINES_AN, aus=DEFINES_AUS):
    """Schaltet Erweiterungen in ``defines.hpp`` ein bzw. aus und gibt den neuen
    Text zurück. Rein — damit prüfbar, ohne FluidX3D zu haben.

    Die Zeilen tragen Zeilenendkommentare (``#define SURFACE // enables …``),
    ein einfaches ``str.replace`` auf die ganze Zeile greift deshalb nicht; es
    wird nur der Zeilenanfang ersetzt (derselbe Grund, aus dem ``.gitignore``
    hier keine Zeilenendkommentare verträgt)."""
    out = text
    for name in an:
        out = re.sub(r"(?m)^//\s*#define\s+%s\b" % re.escape(name),
                     "#define %s" % name, out)
    for name in aus:
        out = re.sub(r"(?m)^#define\s+%s\b" % re.escape(name),
                     "//#define %s" % name, out)
    return out


def defines_stand(text):
    """Welche Erweiterungen sind in diesem ``defines.hpp`` aktiv? (Für Tests und
    für den Debug-Log eines Laufs.)"""
    return sorted(set(re.findall(r"(?m)^#define\s+([A-Z0-9_]+)", text)))


# ── Arbeitskopie anlegen / auffrischen ───────────────────────────────────────
_NICHT_KOPIEREN = shutil.ignore_patterns(".git", "bin", "export", "temp", "*.o")


def vorbereiten(progress_cb=None, neu=False):
    """Legt die Arbeitskopie an (falls nötig) und setzt ``defines.hpp``.
    Returns (heim, log). Der Quellbaum wird **nur gelesen**."""
    def _log(m):
        if progress_cb:
            progress_cb(m, None)
    if not QUELLE:
        raise RuntimeError(INSTALL_HINT)
    if neu:
        shutil.rmtree(HEIM, ignore_errors=True)
    frisch = not os.path.exists(os.path.join(HEIM, "src", "lbm.cpp"))
    if frisch:
        _log("📦 Arbeitskopie von FluidX3D anlegen (%s → %s) …" % (QUELLE, HEIM))
        os.makedirs(os.path.dirname(HEIM.rstrip("/")) or "/", exist_ok=True)
        shutil.copytree(QUELLE, HEIM, ignore=_NICHT_KOPIEREN, dirs_exist_ok=True)
        with open(os.path.join(HEIM, "HERKUNFT.txt"), "w", encoding="utf-8") as f:
            f.write(HERKUNFT_TEXT % QUELLE)
    os.makedirs(os.path.join(HEIM, "bin"), exist_ok=True)
    dh = os.path.join(HEIM, "src", "defines.hpp")
    with open(dh, encoding="utf-8", errors="replace") as f:
        alt = f.read()
    neu_txt = defines_setzen(alt)
    if neu_txt != alt:
        with open(dh, "w", encoding="utf-8") as f:
            f.write(neu_txt)
        _log("⚙ defines.hpp gesetzt: " + ", ".join(DEFINES_AN))
    return HEIM, ("angelegt" if frisch else "vorhanden")


# ── Übersetzen ───────────────────────────────────────────────────────────────
def _uebersetzungsbefehl(heim):
    """Genau der ``Linux``-Zweig aus FluidX3Ds eigenem ``make.sh`` (ohne X11 —
    GRAPHICS ist aus). Nicht ``make.sh`` selbst: das führt das Programm am Ende
    gleich aus, und der Lauf gehört hier in ``laufen``."""
    return [CXX or "g++", "-std=c++17", "-pthread", "-O", "-Wno-comment",
            "-I./src/OpenCL/include", "-o", "bin/FluidX3D"] + \
           sorted(os.path.join("src", f) for f in os.listdir(os.path.join(heim, "src"))
                  if f.endswith(".cpp")) + \
           ["-L./src/OpenCL/lib", "-lOpenCL"]


def uebersetzen(heim, setup_code, progress_cb=None, timeout=900):
    """Schreibt ``src/setup.cpp`` und übersetzt. Ist der Code unverändert und die
    ausführbare Datei jünger, wird **nicht neu übersetzt** (gemessen 40 s je
    Übersetzung — dasselbe Argument wie der Netz-Cache in `ema_em3d`).
    Returns ``{ok, cached, error, log, binary}``."""
    def _log(m):
        if progress_cb:
            progress_cb(m, None)
    sp = os.path.join(heim, "src", "setup.cpp")
    binp = os.path.join(heim, "bin", "FluidX3D")
    marke = os.path.join(heim, "bin", "setup.sha1")
    sha = hashlib.sha1(setup_code.encode("utf-8")).hexdigest()
    alt_sha = ""
    if os.path.exists(marke):
        try:
            with open(marke) as f:
                alt_sha = f.read().strip()
        except OSError:
            pass
    if alt_sha == sha and os.path.exists(binp):
        _log("♻ Übersetzung wiederverwendet (Fall unverändert).")
        return {"ok": True, "cached": True, "error": None, "log": "", "binary": binp}

    with open(sp, "w", encoding="utf-8") as f:
        f.write(setup_code)
    try:
        os.remove(binp)                      # nie eine alte Datei weiterbenutzen
    except OSError:
        pass
    _log("🔨 FluidX3D übersetzen (C++, je Fall einmal) …")
    try:
        p = subprocess.run(_uebersetzungsbefehl(heim), cwd=heim, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False, "cached": False, "error": "Übersetzung Zeitüberschreitung",
                "log": "", "binary": None}
    if p.returncode != 0 or not os.path.exists(binp):
        fehler = [l for l in (p.stdout or "").splitlines() if "error" in l.lower()][:12]
        return {"ok": False, "cached": False,
                "error": "Übersetzung fehlgeschlagen:\n" + "\n".join(fehler or
                         [(p.stdout or "")[-800:]]),
                "log": p.stdout or "", "binary": None}
    with open(marke, "w") as f:
        f.write(sha)
    _log("✓ übersetzt")
    return {"ok": True, "cached": False, "error": None, "log": p.stdout or "",
            "binary": binp}


# ── Lauf ─────────────────────────────────────────────────────────────────────
_PROC_LOCK = threading.Lock()
_CURRENT_PROC = None
_ABORTED = False


def abort_current() -> bool:
    """Bricht den laufenden FluidX3D-Prozess ab (aus einem anderen Thread, dem
    /fluidx3d/abort-Handler). Ohne das liefe er bis ``timeout``."""
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = True
        p = _CURRENT_PROC
    if p is None:
        return False
    try:
        p.terminate()
        try:
            p.wait(timeout=8)
        except Exception:
            p.kill()
        return True
    except Exception:
        return False


def clear_abort():
    global _ABORTED
    with _PROC_LOCK:
        _ABORTED = False


_STEP_RE = re.compile(r"FX3D_STEP:(\d+)\s*/\s*(\d+)")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
# Je Art ein eigener Rumpf: STEP ist `<i>/<n>` und sonst nichts, STAGE laeuft
# bis zum Zeilen- oder Rahmenende. Ein gemeinsames "alles bis Zeilenende" haette
# an einen STEP-Marker noch das angehaengt, was FluidX3D danach in dieselbe
# Zeile schreibt.
_MARKE_RE = re.compile(r"FX3D_(?:(?P<stage>STAGE):(?P<stext>[^\r\n|]*)"
                       r"|(?P<step>STEP):(?P<snum>\d+\s*/\s*\d+)"
                       r"|(?P<done>DONE))")


def marker_aus(roh):
    """Zieht die FX3D-Marker aus einem Ausgabestueck heraus — an BELIEBIGER
    Stelle, nicht nur am Zeilenanfang. Rein und damit pruefbar.

    Grund: FluidX3Ds Fortschrittszeile traegt kein ``\n`` (sie wird mit ``\r``
    ueberschrieben), ein eigener Marker steht also mitten in einem sehr langen
    "Satz" und kann vorn wie hinten von Fortschrittszeichen eingerahmt sein.
    Abgeschnitten wird an ``\r`` und am Rahmenzeichen ``|`` der Zeile.
    Returns Liste von (art, rest)."""
    txt = _ANSI_RE.sub("", roh)
    out = []
    for m in _MARKE_RE.finditer(txt):
        if m.group("stage"):
            out.append(("STAGE", (m.group("stext") or "").strip()))
        elif m.group("step"):
            out.append(("STEP", m.group("snum").replace(" ", "")))
        else:
            out.append(("DONE", ""))
    return out


def laufen(heim, ausgabe, timeout=7200, progress_cb=None):
    """Fuehrt ``bin/FluidX3D`` aus, meldet den Fortschritt und liest hinterher
    die Ergebnisdateien aus ``ausgabe``.

    Returns ``{ok, aborted, metrics, schnitte, fest, n_frames, stdout, error}``
    — ``schnitte`` = sortierte Liste der Schnittdateien, ``fest`` = Pfad der
    Festkoerpermaske (oder None)."""
    global _CURRENT_PROC
    binp = os.path.join(heim, "bin", "FluidX3D")
    if not os.path.exists(binp):
        return {"ok": False, "error": "bin/FluidX3D fehlt", "stdout": "", "aborted": False}

    lines, done = [], False
    try:
        with _PROC_LOCK:
            if _ABORTED:
                return {"ok": False, "aborted": True, "error": "abgebrochen",
                        "stdout": "", "metrics": None}
            proc = subprocess.Popen([binp], cwd=heim, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            _CURRENT_PROC = proc
        try:
            for raw in proc.stdout:
                if "Error" in raw or "error" in raw:
                    lines.append(_ANSI_RE.sub("", raw.rstrip())[:400])
                for art, rest in marker_aus(raw):
                    if art == "STAGE":
                        lines.append("STAGE " + rest[:200])
                        if progress_cb:
                            progress_cb(rest, None)
                    elif art == "STEP":
                        m = _STEP_RE.search("FX3D_STEP:" + rest)
                        if m and progress_cb:
                            i, n = int(m.group(1)), int(m.group(2))
                            progress_cb("Bild %d/%d" % (i, n),
                                        20 + int(65.0 * i / max(1, n)))
                    elif art == "DONE":
                        done = True
                if len(lines) > 2000:
                    lines = lines[-1000:]
            proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.communicate()
            return {"ok": False, "error": "FluidX3D Zeitueberschreitung",
                    "stdout": "\n".join(lines), "aborted": False, "metrics": None}

        stdout = "\n".join(lines)
        if _ABORTED:
            return {"ok": False, "aborted": True, "error": "abgebrochen",
                    "stdout": stdout, "metrics": None}
        if proc.returncode is not None and proc.returncode < 0:
            # Von einem Signal beendet OHNE Nutzerabbruch — bei einem GPU-Loeser
            # praktisch immer Speichermangel. NICHT als "abgebrochen" melden,
            # sonst sieht der Nutzer einen Phantom-Abbruch statt der Ursache.
            return {"ok": False, "aborted": False,
                    "error": ("FluidX3D wurde vom System beendet (Signal %d) — "
                              "vermutlich Speichermangel. Fenster verkleinern "
                              "oder Aufloesung senken." % -proc.returncode),
                    "stdout": stdout, "metrics": None}
        return {**ergebnisdateien(ausgabe), "ok": bool(done) and proc.returncode == 0,
                "aborted": False, "stdout": stdout, "returncode": proc.returncode,
                "error": None if done and proc.returncode == 0
                         else "FluidX3D endete ohne FX3D_DONE"}
    except Exception as e:
        return {"ok": False, "error": str(e), "stdout": "\n".join(lines),
                "aborted": False, "metrics": None}
    finally:
        with _PROC_LOCK:
            _CURRENT_PROC = None


def ergebnisdateien(ausgabe):
    """Liest, was das Setup nach ``ausgabe`` geschrieben hat. Getrennt von
    ``laufen``, damit ein abgebrochener oder halb gelaufener Fall dieselben
    Teilergebnisse hergeben kann (Muster ``run_em3d_sweep``: Teilergebnis
    behalten statt wegwerfen)."""
    kw = os.path.join(ausgabe, "kennwerte.json")
    metrics = None
    if os.path.exists(kw):
        try:
            with open(kw) as f:
                metrics = json.load(f)
        except (OSError, ValueError):
            metrics = None
    schnitte = sorted(os.path.join(ausgabe, f) for f in os.listdir(ausgabe)
                      if f.startswith("schnitt_") and f.endswith(".bin")) \
               if os.path.isdir(ausgabe) else []
    fest = os.path.join(ausgabe, "fest.bin")
    return {"metrics": metrics, "schnitte": schnitte,
            "fest": fest if os.path.exists(fest) else None,
            "n_frames": len(schnitte)}
