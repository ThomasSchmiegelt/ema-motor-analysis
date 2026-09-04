"""Was gerade arbeitet -- fuer die schmale Leiste unter der Ergebnisspalte.

Warum es sie gibt
-----------------

Ein Agentenlauf sieht von aussen minutenlang gleich aus: links laeuft Text,
rechts steht nichts Neues. Ob dabei gerade eine Internetrecherche haengt, der
Loeser rechnet, die Grafikkarte das Sprachmodell traegt -- oder ob schlicht
nichts passiert -- war nicht zu unterscheiden. Wer das nicht sieht, bricht
entweder zu frueh ab oder wartet auf etwas, das gar nicht laeuft.

Die Leiste ist deshalb bewusst **schmal und faktisch**: fuenf Leuchten, jede mit
einer Zahl daran, keine Balken und keine Verlaufskurven. Sie beantwortet eine
einzige Frage -- „arbeitet gerade etwas, und was?".

Was hier NICHT geraten wird
---------------------------

Es gibt keinen ehrlichen Weg, „das Modell denkt gerade" von aussen zu messen:
Ollama meldet ueber ``/api/ps`` nur, welches Modell im Speicher **liegt**, nicht
ob es gerade rechnet. Darum steht hier das geladene Modell mit seinem
Speicherbedarf, und die **Grafikkartenlast** daneben -- die ist auf dieser
Maschine der einzige GPU-Verbraucher und damit der belastbare Hinweis. Eine
Leuchte „Modell denkt", die in Wahrheit nur „Modell geladen" heisst, waere
schlechter als keine.

Ebenso wird die Recherche nicht aus dem Werkzeugtext des Agenten geraten,
sondern von ``ema_recherche`` selbst als Puls gesetzt (``puls()``): nur der Ort,
der tatsaechlich ins Netz greift, weiss, dass er es tut.

Kosten
------

Die Leiste wird im Sekundentakt abgefragt, also darf sie nichts Teures tun.
``nvidia-smi`` und die Ollama-Abfrage sind darum **zwischengespeichert**
(``_CACHE_SEK``); der Prozessdurchgang liest nur ``/proc/*/comm``, was ein
paar Millisekunden kostet und keine Unterprozesse startet.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

PROJEKTE = os.path.expanduser("~/cae_projekte")
PULS_DATEI = os.path.join(PROJEKTE, "_session", "recherche.puls")

# Wie lange eine Messung wiederverwendet wird, bevor neu gemessen wird.
_CACHE_SEK = 2.0
# Wie lange nach dem letzten Netzgriff die Recherche noch als „laeuft" gilt.
# Grosszuegig, weil zwischen zwei Seitenabrufen echte Pausen liegen -- eine
# Leuchte, die zwischen zwei Treffern ausgeht, flackert nur.
PULS_FENSTER = 20.0

# Loeser und Werkzeuge, die eigene Prozesse sind. Gegen ``/proc/<pid>/comm``
# geprueft, also gegen den ProzessNAMEN und nicht gegen die Kommandozeile: ein
# `grep ccx` in irgendeiner Shell soll die Leuchte nicht anschalten.
LOESER = {
    "ccx": "CalculiX", "ccx_2.23": "CalculiX",
    "ElmerSolver": "Elmer", "ElmerSolver_mpi": "Elmer",
    "ElmerGrid": "Elmer",
    "z88r": "Z88", "z88n": "Z88",
    "gmsh": "Gmsh",
    "FreeCAD": "FreeCAD", "FreeCADCmd": "FreeCAD",
    "simpleFoam": "OpenFOAM", "buoyantSimpleFoam": "OpenFOAM",
    "chtMultiRegionFoam": "OpenFOAM", "blockMesh": "OpenFOAM",
    "snappyHexMesh": "OpenFOAM",
    "blender": "Blender",
}

_cache: dict = {}


def _gecacht(name: str, dauer: float, fn):
    jetzt = time.time()
    eintrag = _cache.get(name)
    if eintrag and jetzt - eintrag[0] < dauer:
        return eintrag[1]
    try:
        wert = fn()
    except Exception:                                        # noqa: BLE001
        wert = None
    _cache[name] = (jetzt, wert)
    return wert


# ── Recherche ───────────────────────────────────────────────────────────────
def puls() -> None:
    """„Ich greife gerade ins Netz." Von ``ema_recherche`` gerufen.

    Eine Datei mit der Uhrzeit, kein Zustand im Server: die Recherche laeuft im
    **CLI-Unterprozess** des Agenten, nicht im Serverprozess. Ein Feld in einem
    Python-Dict waere von dort aus unerreichbar.
    """
    try:
        os.makedirs(os.path.dirname(PULS_DATEI), exist_ok=True)
        with open(PULS_DATEI, "w") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def recherche_laeuft() -> dict:
    try:
        with open(PULS_DATEI) as f:
            t = float(f.read().strip())
    except (OSError, ValueError):
        return {"an": False}
    alter = time.time() - t
    return {"an": alter <= PULS_FENSTER, "vor_sek": round(alter, 1)}


# ── Grafikkarte ─────────────────────────────────────────────────────────────
def _gpu_messen() -> dict | None:
    aus = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used,memory.total",
         "--format=csv,noheader,nounits"],
        capture_output=True, text=True, timeout=5)
    if aus.returncode != 0 or not aus.stdout.strip():
        return None
    teile = [t.strip() for t in aus.stdout.strip().splitlines()[0].split(",")]
    if len(teile) < 4:
        return None
    return {"name": teile[0], "last_pct": int(float(teile[1])),
            "mb_belegt": int(float(teile[2])), "mb_gesamt": int(float(teile[3]))}


def gpu() -> dict:
    g = _gecacht("gpu", _CACHE_SEK, _gpu_messen)
    if not g:
        return {"da": False}
    # Die Schwelle ist gemessen, nicht gesetzt: diese Karte zeigt im LEERLAUF
    # 18-24 % Last bei 758 MB (der Schreibtisch des angemeldeten Benutzers, kein
    # Modell geladen). Eine Leuchte bei 12 % waere also dauernd an und saehe
    # nach Arbeit aus, wo keine ist. Ab 50 % rechnet wirklich etwas.
    return {"da": True, "an": g["last_pct"] >= 50, **g}


# ── Sprachmodell ────────────────────────────────────────────────────────────
def _ollama_messen() -> dict | None:
    with urllib.request.urlopen("http://localhost:11434/api/ps", timeout=2) as r:
        d = json.load(r)
    modelle = d.get("models") or []
    if not modelle:
        return {"da": True, "geladen": []}
    return {"da": True, "geladen": [
        {"name": m.get("name") or m.get("model", ""),
         "mb": int((m.get("size_vram") or m.get("size") or 0) / 1048576)}
        for m in modelle]}


def modell() -> dict:
    m = _gecacht("ollama", _CACHE_SEK, _ollama_messen)
    return m or {"da": False, "geladen": []}


# ── Loeser ──────────────────────────────────────────────────────────────────
def loeser() -> dict:
    """Welche Loeserprozesse gerade laufen -- ueber ``/proc``, ohne Unterprozess.

    ``psutil`` waere hier eine Abhaengigkeit fuer fuenf Zeilen; der
    Verzeichnisdurchgang kostet auf dieser Maschine unter 5 ms.
    """
    gefunden: dict = {}
    try:
        for eintrag in os.listdir("/proc"):
            if not eintrag.isdigit():
                continue
            try:
                with open(f"/proc/{eintrag}/comm") as f:
                    name = f.read().strip()
            except OSError:
                continue
            label = LOESER.get(name)
            if label:
                gefunden[label] = gefunden.get(label, 0) + 1
    except OSError:
        return {"an": False, "was": []}
    return {"an": bool(gefunden),
            "was": [{"name": k, "n": v} for k, v in sorted(gefunden.items())]}


# ── Zusammenzug ─────────────────────────────────────────────────────────────
def stand(rechnungen: dict | None = None) -> dict:
    """Alles auf einmal. ``rechnungen`` kommt aus dem Server (seine Zustandsdicts).

    Der Server reicht sie herein, statt dass dieses Modul ihn importierte: eine
    Rueckwaertsabhaengigkeit vom Messmodul auf den Server waere ein Importzirkel
    und machte das Modul zudem unpruefbar ohne laufenden Flask.
    """
    r = dict(rechnungen or {})
    laufend = [{"name": k, "fortschritt": v.get("progress")}
               for k, v in r.items()
               if isinstance(v, dict) and str(v.get("status", "idle")) not in
               ("idle", "done", "error", "fertig", "")]
    return {"zeit": round(time.time(), 1),
            "rechnung": {"an": bool(laufend), "was": laufend},
            "recherche": recherche_laeuft(),
            "gpu": gpu(),
            "modell": modell(),
            "loeser": loeser()}
