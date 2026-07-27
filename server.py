"""E-Maschinen Analyse-Server: serves ema.html + full analysis pipeline."""

import json, os, threading, time, urllib.error


def _fix_fontconfig_env():
    """Setzt FONTCONFIG_FILE/PATH auf die System-Config, falls sie leer/ungültig sind.
    Die pixi/conda-Umgebungen (FreeCAD/CCX) exportieren FONTCONFIG_FIL="" → libfontconfig
    meldet dann bei JEDEM Unterprozess (FreeCAD/Blender/Elmer/matplotlib) »Cannot load default
    config file: No such file: (null)«. Wir setzen die Variablen VOR allen weiteren Imports auf
    die vorhandene System-Config; da alle Runner env=os.environ.copy() nutzen, erben die
    Unterprozesse die Korrektur (verifiziert: pixi überschreibt einen gesetzten Wert nicht)."""
    sys_conf = "/etc/fonts/fonts.conf"
    if os.path.exists(sys_conf):
        if not (os.environ.get("FONTCONFIG_FILE") or "").strip():
            os.environ["FONTCONFIG_FILE"] = sys_conf
        if not (os.environ.get("FONTCONFIG_PATH") or "").strip():
            os.environ["FONTCONFIG_PATH"] = os.path.dirname(sys_conf)


_fix_fontconfig_env()

from flask import Flask, request, jsonify, send_from_directory, send_file, Response

app = Flask(__name__, static_folder=os.path.dirname(__file__))

WORKSPACE = os.path.join(os.path.dirname(__file__), "workspace")
PROJECTS_ROOT = os.path.expanduser("~/cae_projekte")
os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(PROJECTS_ROOT, exist_ok=True)

_state  = {"status": "idle", "progress": 0, "log": [],
           "results": None, "project_dir": None, "project_id": None}
# Field animation frames (base64 PNG) keyed by mode bucket: rotate/react/load.
_frames = {"rotate": [], "react": [], "load": []}
# mode bucket → on-disk subdir (must match ema_pipeline.FIELD_SUBDIRS)
FIELD_SUBDIRS = {"rotate": "frames", "react": "frames_react", "load": "frames_load"}

# Report generation state (separate from analysis pipeline)
_report_state = {"status": "idle", "progress": 0, "log": [],
                 "pdf_path": None, "project_id": None}

# Target-value optimisation state (LLM-steered fast search)
_opt_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}

# KI-Auslegung (Designer): LLM entwirft komplette Maschinen (Maße + gezeichnete Geometrie)
_design_state     = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
# Per-Magnet-Fein-Optimierung eines gezeichneten Custom-Designs
_design_opt_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}

# Parameter-study state (one parameter swept at a fixed speed, fast evaluator)
_study_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
# Field-line frames/video of the most recent parameter study (overwritten each run)
STUDY_FIELD_DIR = os.path.join(PROJECTS_ROOT, "_paramstudy")
os.makedirs(STUDY_FIELD_DIR, exist_ok=True)

# Geometry-only CAD preview + smoke-test state (staged workflow, separate threads)
_cad_state   = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
_smoke_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}

# STEP-Import: erkennt Magnetlage aus einer hochgeladenen Motor-STEP, schreibt
# motor.FCStd (Rotor benannt) und liefert die erkannte Geometrie an den Designer.
_import_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}

# Echte 3D-Magnetfeldberechnung (Elmer FEM): On-Demand-Job neben dem 2D-Pfad.
_em3d_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
# Abbruch-Flag (mutabel, damit der Worker-Thread die Änderung sieht): /em3d/abort setzt es +
# killt den laufenden ElmerSolver; der Sweep-Loop fragt es zwischen den Punkten ab und behält
# das Teilergebnis. Jeder Start setzt es zurück.
_em3d_abort = {"v": False}
# Benannte 3D-Läufe (Config + Kennwerte + Feld) zum Speichern/Aufrufen — jetzt PROJEKT-
# gebunden: pro Lauf ein Ordner <aktives Projekt>/em3d_runs/<id>/ mit config.json/
# result.json + kopierten VTU/VTP (s. _em3d_runs_root). Kein globaler Store mehr.


def _em3d_project_dir(data):
    """Resolve the project dir for an em3d job (so VTU/VTP land in the active project):
    honour an explicit ``project_id`` like /analyse's reuse_id, else the active _state
    project, else a fresh '…_em3d' project. Sets _state so the viewer/save routes follow."""
    from ema_pipeline import create_project_dir
    reuse_id  = (data or {}).get("project_id")
    reuse_dir = (os.path.join(PROJECTS_ROOT, reuse_id)
                 if reuse_id and _safe_name(reuse_id) else None)
    if reuse_dir and os.path.isdir(reuse_dir):
        proj_dir, proj_id = reuse_dir, reuse_id
    else:
        pd = _state.get("project_dir")
        if pd and os.path.isdir(pd):
            proj_dir, proj_id = pd, _state.get("project_id")
        else:
            proj_dir, proj_id = create_project_dir(
                PROJECTS_ROOT, (data or {}).get("project_name") or "em3d")
    _state["project_dir"], _state["project_id"] = proj_dir, proj_id
    return proj_dir, proj_id


def _em3d_runs_root():
    """Per-project store for saved 3D runs: <active project>/em3d_runs/. Returns None
    when no project is active (the save/list/load routes then refuse / return empty)."""
    pd = _state.get("project_dir")
    if pd and os.path.isdir(pd):
        d = os.path.join(pd, "em3d_runs")
        os.makedirs(d, exist_ok=True)
        return d
    return None


# ── Static ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(os.path.dirname(__file__), "ema.html")


# ── Analysis pipeline ─────────────────────────────────────────────────────────

@app.route("/analyse", methods=["POST", "OPTIONS"])
def analyse():
    if request.method == "OPTIONS":
        return "", 200
    if _state["status"] == "running":
        return jsonify({"error": "Pipeline läuft bereits"}), 409

    data = request.get_json(force=True)
    _state.update({"status": "running", "progress": 0, "log": [], "results": None})
    for _b in _frames.values():
        _b.clear()

    t = threading.Thread(target=_run, args=(data,), daemon=True)
    t.start()
    return jsonify({"status": "started"}), 202


# ── Staged workflow: CAD-only preview + smoke test ──────────────────────────────

@app.route("/cad_preview", methods=["POST", "OPTIONS"])
def cad_preview():
    """Build ONLY the geometry (FreeCAD + STEP + 2D images), no analysis — so the
    user can look at the CAD model before running the real calculation."""
    if request.method == "OPTIONS":
        return "", 200
    if _state["status"] == "running":
        return jsonify({"error": "Analyse läuft bereits"}), 409
    if _cad_state["status"] == "running":
        return jsonify({"error": "CAD-Vorschau läuft bereits"}), 409
    data = request.get_json(force=True)
    _cad_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})
    threading.Thread(target=_run_cad_preview, args=(data,), daemon=True).start()
    return jsonify({"status": "started"}), 202


def _run_cad_preview(data):
    from ema_pipeline import build_cad_preview, create_project_dir
    try:
        proj_dir, proj_id = create_project_dir(
            PROJECTS_ROOT, data.get("project_name") or "cad_vorschau")
        _state["project_dir"] = proj_dir   # so /open_freecad + /download_step work
        _state["project_id"]  = proj_id
        _cad_state["result"]   = build_cad_preview(data, _cad_state, proj_dir)
        _cad_state["status"]   = "done"
        _cad_state["progress"] = 100
    except Exception as e:
        import traceback
        _cad_state["error"] = str(e)
        _cad_state["log"].append("⚠ " + str(e))
        _cad_state["log"].append(traceback.format_exc()[:500])
        _cad_state["status"] = "error"


@app.route("/cad_preview/status")
def cad_preview_status():
    return jsonify({k: _cad_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


# ── STEP-Import: Magnet-Erkennung + Festigkeits-/EM-Analyse eines fertigen Motors ─

@app.route("/import_step", methods=["POST", "OPTIONS"])
def import_step():
    """Multipart-Upload einer Motor-STEP. Legt ein Projekt an, speichert die STEP,
    erkennt im Hintergrund die Magnetlage + Maße und schreibt motor.FCStd (mit
    benanntem "Rotor"). Das Ergebnis (applyDesignToCanvas-Form) wird über
    /import_step/status abgeholt; der Nutzer bestätigt es im Designer und rechnet
    dann wie gewohnt über /analyse (Payload mit imported=true)."""
    if request.method == "OPTIONS":
        return "", 200
    if _import_state["status"] == "running":
        return jsonify({"error": "Import läuft bereits"}), 409
    f = request.files.get("file")
    if not f or not f.filename:
        return jsonify({"error": "keine Datei"}), 400
    if not f.filename.lower().endswith((".step", ".stp")):
        return jsonify({"error": "Bitte eine STEP-Datei (.step/.stp) hochladen"}), 400

    from ema_pipeline import create_project_dir
    proj_dir, proj_id = create_project_dir(PROJECTS_ROOT, "import")
    step_path = os.path.join(proj_dir, "import.step")
    f.save(step_path)
    _state["project_dir"] = proj_dir   # so /open_freecad + /download_step work
    _state["project_id"]  = proj_id

    _import_state.update({"status": "running", "progress": 0, "log": [],
                          "result": None, "error": None})

    def _worker():
        import ema_step_import
        def cb(msg, pct=None):
            _import_state["log"].append(msg)
            if pct is not None:
                _import_state["progress"] = int(pct)
        try:
            res = ema_step_import.run_import(step_path, proj_dir, progress_cb=cb)
            res["project_id"] = proj_id
            _import_state["result"]   = res
            _import_state["status"]   = "done"
            _import_state["progress"] = 100
        except Exception as e:
            import traceback
            _import_state["error"] = str(e)
            _import_state["log"].append("⚠ " + str(e))
            _import_state["log"].append(traceback.format_exc()[:500])
            _import_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


@app.route("/import_step/status")
def import_step_status():
    return jsonify({k: _import_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


# ── Echte 3D-Magnetfeldberechnung (Elmer FEM) ───────────────────────────────────

@app.route("/em3d", methods=["POST", "OPTIONS"])
def em3d_start():
    """Startet die 3D-Magnetostatik (Gmsh-Mesh → Elmer). Body = normaler Analyse-
    Payload (geom + axial_len) + 3D-Optionen (skew_deg, mesh_cl, gap_cl, airbox_factor).
    503 wenn Elmer fehlt."""
    if request.method == "OPTIONS":
        return "", 200
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return jsonify({"error": elmer_runner.INSTALL_HINT, "need_install": True}), 503
    if _em3d_state["status"] == "running":
        return jsonify({"error": "3D-Berechnung läuft bereits"}), 409
    data = request.get_json(force=True) or {}

    proj_dir, proj_id = _em3d_setup(data)
    threading.Thread(target=_em3d_body, args=(data, proj_dir, proj_id),
                     daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


def _em3d_setup(data):
    """Gemeinsames Setup eines em3d-Laufs (Route + Job-Warteschlange): Projekt binden,
    Abort-Flags zurücksetzen, State auf running."""
    import elmer_runner
    proj_dir, proj_id = _em3d_project_dir(data)
    _em3d_abort["v"] = False
    elmer_runner.clear_abort()
    _em3d_state.update({"status": "running", "progress": 0, "log": [],
                        "result": None, "error": None})
    return proj_dir, proj_id


def _em3d_body(data, proj_dir, proj_id):
    """Synchroner Lauf-Körper von /em3d (ex-_worker) — auch von der Job-Warteschlange
    direkt (ohne eigenen Thread) aufgerufen."""
    import ema_em3d
    def cb(msg, pct=None):
        _em3d_state["log"].append(msg)
        if pct is not None:
            _em3d_state["progress"] = int(pct)
    try:
        res = ema_em3d.run_em3d(data, proj_dir, progress_cb=cb)
        res["project_id"] = proj_id
        _em3d_state["result"]   = res
        _em3d_state["status"]   = "done"
        _em3d_state["progress"] = 100
    except Exception as e:
        _em3d_finish_error(e)


def _em3d_finish_error(e):
    """Fehler-/Abbruch-Abschluss eines em3d-Workers: ein vom Nutzer ausgelöster Abbruch
    (``_em3d_abort``) ist KEIN Fehler → Status ``aborted`` (die UI gibt den Start wieder frei),
    sonst normaler Fehlerstatus."""
    import traceback
    if _em3d_abort["v"]:
        _em3d_state["log"].append("⛔ Abgebrochen.")
        _em3d_state["status"] = "aborted"
        _em3d_state["error"] = None
    else:
        _em3d_state["error"] = str(e)
        _em3d_state["log"].append("⚠ " + str(e))
        _em3d_state["log"].append(traceback.format_exc()[:600])
        _em3d_state["status"] = "error"


@app.route("/em3d_sweep", methods=["POST", "OPTIONS"])
def em3d_sweep_start():
    """Startet den 3D-Betriebspunkt-Sweep (Drehzahlband mit wechselnden Lasten). Body wie
    /em3d + ``sweep`` (Liste {rpm, load_nm, excitation}) + optional ``detail_index``. Baut das
    Mesh nur einmal und löst je Punkt. Teilt ``_em3d_state`` (Status/VTU/VTP/ParaView) mit
    /em3d — der Detailpunkt liefert das volle 3D-Feld. 503 wenn Elmer fehlt."""
    if request.method == "OPTIONS":
        return "", 200
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return jsonify({"error": elmer_runner.INSTALL_HINT, "need_install": True}), 503
    if _em3d_state["status"] == "running":
        return jsonify({"error": "3D-Berechnung läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    if not (data.get("sweep") or []):
        return jsonify({"error": "Kein Betriebspunkt im Drehzahlband (sweep ist leer)"}), 400

    proj_dir, proj_id = _em3d_setup(data)
    threading.Thread(target=_em3d_sweep_body, args=(data, proj_dir, proj_id),
                     daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


def _em3d_sweep_body(data, proj_dir, proj_id):
    """Synchroner Lauf-Körper von /em3d_sweep (ex-_worker) — auch von der Job-Warteschlange
    direkt aufgerufen."""
    import ema_em3d
    def cb(msg, pct=None):
        _em3d_state["log"].append(msg)
        if pct is not None:
            _em3d_state["progress"] = int(pct)
    try:
        res = ema_em3d.run_em3d_sweep(data, proj_dir, progress_cb=cb,
                                      cancel_cb=lambda: _em3d_abort["v"])
        res["project_id"] = proj_id
        # /em3d/vtu|vtp|paraview servieren die Dateipfade des Detailpunkts; die
        # per-Punkt-VTP/Linien (sweep_vtp/sweep_lines) bedient /em3d/vtp?i= / streamlines?i=.
        det = res.get("detail") or {}
        if det.get("vtu_path"):
            res["vtu_path"] = det["vtu_path"]
        if det.get("vtp_path"):
            res["vtp_path"] = det["vtp_path"]
        if det.get("lines_path"):
            res["lines_path"] = det["lines_path"]
        _em3d_state["result"]   = res
        # Abbruch mit Teilergebnis: als „aborted" melden (Start wieder frei), Ergebnis bleibt
        # gesetzt → die UI kann die gerechneten Punkte anzeigen/speichern.
        _em3d_state["status"]   = "aborted" if res.get("aborted") else "done"
        _em3d_state["progress"] = 100
    except Exception as e:
        _em3d_finish_error(e)


@app.route("/em3d/sector", methods=["POST", "OPTIONS"])
def em3d_sector_start():
    """Startet die Ein-Pol-Sektor-Berechnung (Symmetrie-Submodell): rechnet EINE Pol-Teilung
    fein, anti-periodisch gekoppelt, und spiegelt sie zum vollen Motor. Body wie /em3d.
    Robustes, schnelles, feines Leerlauf-Feld. Teilt ``_em3d_state`` + alle Viewer-Routen
    (/em3d/status|vtu|vtp|streamlines|paraview) mit /em3d. 503 wenn Elmer fehlt."""
    if request.method == "OPTIONS":
        return "", 200
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return jsonify({"error": elmer_runner.INSTALL_HINT, "need_install": True}), 503
    if _em3d_state["status"] == "running":
        return jsonify({"error": "3D-Berechnung läuft bereits"}), 409
    data = request.get_json(force=True) or {}

    proj_dir, proj_id = _em3d_project_dir(data)

    _em3d_abort["v"] = False
    elmer_runner.clear_abort()
    _em3d_state.update({"status": "running", "progress": 0, "log": [],
                        "result": None, "error": None})

    def _worker():
        import ema_em3d
        def cb(msg, pct=None):
            _em3d_state["log"].append(msg)
            if pct is not None:
                _em3d_state["progress"] = int(pct)
        try:
            res = ema_em3d.run_em3d_sector(data, proj_dir, progress_cb=cb)
            res["project_id"] = proj_id
            _em3d_state["result"] = res
            _em3d_state["status"] = "done"
            _em3d_state["progress"] = 100
        except Exception as e:
            _em3d_finish_error(e)

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


@app.route("/em3d/abort", methods=["POST", "OPTIONS"])
def em3d_abort():
    """Bricht den laufenden 3D-Lauf ab: setzt das Abbruch-Flag (der Sweep-Loop hält nach dem
    aktuellen Punkt an und behält das Teilergebnis) UND killt den gerade laufenden ElmerSolver-
    Prozess, damit der Abbruch SOFORT greift (statt erst nach dem laufenden Solve)."""
    if request.method == "OPTIONS":
        return "", 200
    import elmer_runner
    if _em3d_state.get("status") != "running":
        return jsonify({"status": "idle", "note": "kein laufender 3D-Lauf"})
    _em3d_abort["v"] = True
    killed = elmer_runner.abort_current()
    _em3d_state["log"].append("⛔ Abbruch angefordert…" + (" (Löser gestoppt)" if killed else ""))
    return jsonify({"status": "aborting", "killed": killed})


@app.route("/em3d/status")
def em3d_status():
    return jsonify({k: _em3d_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


# ── Experimentelle Spritzöl-Kühlung (Blender/Mantaflow) ──────────────────────
_oil_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
_oil_abort = {"v": False}


@app.route("/oilspray", methods=["POST", "OPTIONS"])
def oilspray_start():
    """Startet die experimentelle Spritzöl-Simulation am Wickelkopf (Blender/Mantaflow-FLIP).
    Body = normaler Analyse-Payload (geom + axial_len) + ``oil``-Optionen (resolution, frames,
    section_slots, viscosity, surface_tension, jet_speed, engine). 503 wenn kein Mantaflow-
    taugliches Blender vorhanden. QUALITATIV — kein Temperaturfeld/Wärmeübergang."""
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if not blender_runner.BLENDER_OK:
        return jsonify({"error": blender_runner.INSTALL_HINT, "need_install": True}), 503
    if _oil_state["status"] == "running":
        return jsonify({"error": "Spritzöl-Simulation läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    proj_dir, proj_id = _oil_setup(data)
    threading.Thread(target=_oil_body, args=(data, proj_dir, proj_id),
                     daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


def _oil_setup(data):
    """Gemeinsames Setup eines Spritzöl-Laufs (Route + Job-Warteschlange)."""
    import blender_runner
    proj_dir, proj_id = _em3d_project_dir(data)
    _oil_abort["v"] = False
    blender_runner.clear_abort()
    _oil_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})
    return proj_dir, proj_id


def _oil_body(data, proj_dir, proj_id):
    """Synchroner Lauf-Körper von /oilspray (ex-_worker) — auch von der Job-Warteschlange
    direkt aufgerufen."""
    import ema_oilspray, traceback
    def cb(msg, pct=None):
        _oil_state["log"].append(msg)
        if pct is not None:
            _oil_state["progress"] = int(pct)
    try:
        res = ema_oilspray.run_oilspray(data, proj_dir, progress_cb=cb,
                                        cancel_cb=lambda: _oil_abort["v"])
        res["project_id"] = proj_id
        _oil_state["result"]   = res
        _oil_state["status"]   = "done"
        _oil_state["progress"] = 100
    except Exception as e:
        if _oil_abort["v"] or "abgebrochen" in str(e).lower():
            _oil_state["log"].append("⛔ Abgebrochen.")
            _oil_state["status"] = "aborted"
            _oil_state["error"] = None
        else:
            _oil_state["error"] = str(e)
            _oil_state["log"].append("⚠ " + str(e))
            _oil_state["log"].append(traceback.format_exc()[:600])
            _oil_state["status"] = "error"


@app.route("/oilspray/preview", methods=["POST", "OPTIONS"])
def oilspray_preview():
    """Schnelle Zwischenansicht VOR dem Bake: rendert nur Geometrie + Düsen + Strahl-Ziellinien
    als EIN Standbild (kein Mantaflow-Bake). Teilt sich Status/Job mit /oilspray (``_oil_state``)."""
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if not blender_runner.BLENDER_OK:
        return jsonify({"error": blender_runner.INSTALL_HINT, "need_install": True}), 503
    if _oil_state["status"] == "running":
        return jsonify({"error": "Spritzöl-Job läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    proj_dir, proj_id = _em3d_project_dir(data)
    _oil_abort["v"] = False
    blender_runner.clear_abort()
    _oil_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})

    def _worker():
        import ema_oilspray, traceback
        def cb(msg, pct=None):
            _oil_state["log"].append(msg)
            if pct is not None:
                _oil_state["progress"] = int(pct)
        try:
            res = ema_oilspray.preview_oilspray(data, proj_dir, progress_cb=cb,
                                                cancel_cb=lambda: _oil_abort["v"])
            res["preview"] = True
            res["project_id"] = proj_id
            _oil_state["result"] = res
            _oil_state["status"] = "done"
            _oil_state["progress"] = 100
        except Exception as e:
            if _oil_abort["v"] or "abgebrochen" in str(e).lower():
                _oil_state["log"].append("⛔ Abgebrochen.")
                _oil_state["status"] = "aborted"
                _oil_state["error"] = None
            else:
                _oil_state["error"] = str(e)
                _oil_state["log"].append("⚠ " + str(e))
                _oil_state["log"].append(traceback.format_exc()[:600])
                _oil_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id, "preview": True}), 202


@app.route("/oilspray/abort", methods=["POST", "OPTIONS"])
def oilspray_abort():
    """Bricht die laufende Spritzöl-Simulation ab (Flag + Blender-Prozess terminieren)."""
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if _oil_state.get("status") != "running":
        return jsonify({"status": "idle", "note": "keine laufende Spritzöl-Simulation"})
    _oil_abort["v"] = True
    killed = blender_runner.abort_current()
    _oil_state["log"].append("⛔ Abbruch angefordert…" + (" (Blender gestoppt)" if killed else ""))
    return jsonify({"status": "aborting", "killed": killed})


@app.route("/oilspray/status")
def oilspray_status():
    return jsonify({k: _oil_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


# ── Benannte 💧-Darstellungs-Presets (gute Einstellungen + Rechen-Pakete) ────────────
@app.route("/oilspray/presets", methods=["GET", "POST", "OPTIONS"])
def oilspray_presets():
    if request.method == "OPTIONS":
        return ("", 204)
    import ema_oilspray
    if request.method == "GET":
        return jsonify(ema_oilspray.list_presets())
    data = request.get_json(force=True) or {}
    payload = data.get("payload")
    if not isinstance(payload, dict) or not payload:
        return jsonify({"error": "payload fehlt"}), 400
    return jsonify(ema_oilspray.save_preset(data.get("name"), payload))


@app.route("/oilspray/presets/<pid>/delete", methods=["POST", "OPTIONS"])
def oilspray_preset_delete(pid: str):
    if request.method == "OPTIONS":
        return ("", 204)
    import ema_oilspray
    return jsonify({"ok": bool(ema_oilspray.delete_preset(pid))})


# ── Quantitative Spritzöl-Kühlung (OpenFOAM VOF / interFoam) ──────────────────
# On-Demand-Pfad NEBEN Mantaflow (💧): löst die Strömung/Benetzung quantitativ und leitet
# einen effektiven HTC ab, der (bei Ölkühlung) die Thermik speist. Spiegelt /oilspray + /em3d.
_cfd_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
_cfd_abort = {"v": False}


@app.route("/cfd", methods=["POST", "OPTIONS"])
def cfd_start():
    """Startet die OpenFOAM-VOF-Kühlrechnung (STL → snappyHexMesh → interFoam → HTC).
    Body = Analyse-Payload (geom + axial_len) + ``cfd``-Optionen (pressure_bar, section_slots,
    end_time, n_cells, refine, viscosity). 503 wenn OpenFOAM fehlt."""
    if request.method == "OPTIONS":
        return "", 200
    import openfoam_runner
    if not openfoam_runner.OPENFOAM_OK:
        return jsonify({"error": openfoam_runner.INSTALL_HINT, "need_install": True}), 503
    if _cfd_state["status"] == "running":
        return jsonify({"error": "CFD-Berechnung läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    proj_dir, proj_id = _cfd_setup(data)
    threading.Thread(target=_cfd_body, args=(data, proj_dir, proj_id), daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


def _cfd_setup(data):
    """Gemeinsames Setup eines CFD-Laufs (Route + Job-Warteschlange): Projekt binden,
    Abort-Flags zurücksetzen, State auf running."""
    import openfoam_runner
    proj_dir, proj_id = _em3d_project_dir(data)     # projektgebunden wie em3d/oil
    _cfd_abort["v"] = False
    openfoam_runner.clear_abort()
    _cfd_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})
    return proj_dir, proj_id


def _cfd_body(data, proj_dir, proj_id):
    """Synchroner Lauf-Körper von /cfd — auch von der Job-Warteschlange direkt aufgerufen."""
    import ema_cfd, traceback
    def cb(msg, pct=None):
        _cfd_state["log"].append(msg)
        if pct is not None:
            _cfd_state["progress"] = int(pct)
    try:
        res = ema_cfd.run_cfd(data, proj_dir, progress_cb=cb,
                              cancel_cb=lambda: _cfd_abort["v"])
        res["project_id"] = proj_id
        if res.get("aborted"):
            _cfd_state["log"].append("⛔ Abgebrochen.")
            _cfd_state["status"] = "aborted"
        else:
            _cfd_state["result"] = res
            _cfd_state["status"] = "done"
            _cfd_state["progress"] = 100
    except Exception as e:
        if _cfd_abort["v"] or "abgebrochen" in str(e).lower():
            _cfd_state["log"].append("⛔ Abgebrochen.")
            _cfd_state["status"] = "aborted"
            _cfd_state["error"] = None
        else:
            _cfd_state["error"] = str(e)
            _cfd_state["log"].append("⚠ " + str(e))
            _cfd_state["log"].append(traceback.format_exc()[:600])
            _cfd_state["status"] = "error"


@app.route("/cfd/status")
def cfd_status():
    return jsonify({k: _cfd_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


@app.route("/cfd/abort", methods=["POST", "OPTIONS"])
def cfd_abort():
    """Bricht die laufende CFD-Simulation ab (Flag + OpenFOAM-Prozess terminieren)."""
    if request.method == "OPTIONS":
        return "", 200
    import openfoam_runner
    if _cfd_state.get("status") != "running":
        return jsonify({"status": "idle", "note": "keine laufende CFD-Simulation"})
    _cfd_abort["v"] = True
    killed = openfoam_runner.abort_current()
    _cfd_state["log"].append("⛔ Abbruch angefordert…" + (" (Solver gestoppt)" if killed else ""))
    return jsonify({"status": "aborting", "killed": killed})


@app.route("/project/<pid>/oilspray")
def project_oilspray(pid: str):
    """Gespeicherten Spritzöl-Lauf eines Projekts laden (results.json["oilspray"] + Chart-
    Dateien als base64) — die „Speicherfunktion" des 💧-Tabs: Ergebnis ohne Neurechnen ansehen."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültig"}), 403
    base = os.path.join(PROJECTS_ROOT, pid) if pid != "current" else _state.get("project_dir")
    if not base or not os.path.isdir(base):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_oilspray
    saved = ema_oilspray.load_saved(base)
    if not saved:
        return jsonify({"error": "Kein gespeicherter Spritzöl-Lauf in diesem Projekt"}), 404
    saved["project_id"] = pid if pid != "current" else _state.get("project_id")
    return jsonify(saved)


def _oil_project_base(pid):
    """Projektverzeichnis für die Spritzöl-Varianten-Routen (pid oder aktives Projekt)."""
    if pid == "current":
        return _state.get("project_dir")
    if not _safe_name(pid):
        return None
    base = os.path.join(PROJECTS_ROOT, pid)
    return base if os.path.isdir(base) else None


@app.route("/project/<pid>/oilspray/saved")
def project_oilspray_saved_list(pid: str):
    """Liste aller automatisch gespeicherten Spritzöl-Varianten eines Projekts."""
    base = _oil_project_base(pid)
    if not base:
        return jsonify([])
    import ema_oilspray
    return jsonify(ema_oilspray.list_saved_runs(base))


@app.route("/project/<pid>/oilspray/saved/<rid>")
def project_oilspray_saved_load(pid: str, rid: str):
    """Eine gespeicherte Spritzöl-Variante laden (ohne Neurechnen) → run_oilspray-Format."""
    base = _oil_project_base(pid)
    if not base or not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_oilspray
    run = ema_oilspray.load_saved_run(base, rid)
    if not run:
        return jsonify({"error": "Variante nicht gefunden"}), 404
    run["project_id"] = pid if pid != "current" else _state.get("project_id")
    run["video_src"] = f"/project/{pid}/oilspray/saved/{rid}/video"
    return jsonify(run)


@app.route("/project/<pid>/oilspray/saved/<rid>/video")
def project_oilspray_saved_video(pid: str, rid: str):
    base = _oil_project_base(pid)
    if not base or not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_oilspray
    mp4 = ema_oilspray.saved_run_video(base, rid)
    if not mp4:
        return jsonify({"error": "Kein Video für diese Variante"}), 404
    return send_file(mp4, mimetype="video/mp4", as_attachment=True,
                     download_name=f"{pid}_oil_{rid}.mp4")


@app.route("/project/<pid>/oilspray/saved/<rid>/delete", methods=["POST", "OPTIONS"])
def project_oilspray_saved_delete(pid: str, rid: str):
    if request.method == "OPTIONS":
        return "", 200
    base = _oil_project_base(pid)
    if not base or not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_oilspray
    ok = ema_oilspray.delete_saved_run(base, rid)
    return jsonify({"status": "deleted" if ok else "missing"})


# ── 🧪 Spray-Test-Prüfstand (iteratives Spray-Tuning, Blender/Mantaflow) ──────
# Projektunabhängig (Store unter ~/cae_projekte/_spraytest); gleiche Job-Mechanik
# wie /oilspray (ein Lauf, Daemon-Thread, Abbruch via Flag + Blender-Kill).
_spraytest_state = {"status": "idle", "progress": 0, "log": [], "result": None, "error": None}
_spraytest_abort = {"v": False}


@app.route("/spraytest", methods=["POST", "OPTIONS"])
def spraytest_start():
    """Startet EINE Spray-Test-Runde: sampelt n Varianten (Runde ≥2 um die markierten
    Eltern), bäckt sie sequenziell auf dem Prüfstand (horizontale Düse + Kupferstäbe)
    und speichert die Runde unter ~/cae_projekte/_spraytest/rounds/<rid>/."""
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if not blender_runner.BLENDER_OK:
        return jsonify({"error": blender_runner.INSTALL_HINT, "need_install": True}), 503
    if _spraytest_state["status"] == "running" or _oil_state["status"] == "running":
        return jsonify({"error": "Es läuft bereits ein Blender-Job (Spritzöl/Spray-Test)"}), 409
    data = request.get_json(force=True) or {}

    _spraytest_abort["v"] = False
    blender_runner.clear_abort()
    _spraytest_state.update({"status": "running", "progress": 0, "log": [],
                             "result": None, "error": None})

    def _worker():
        import ema_spraytest, traceback
        def cb(msg, pct=None):
            _spraytest_state["log"].append(msg)
            if pct is not None:
                _spraytest_state["progress"] = int(pct)
        try:
            res = ema_spraytest.run_round(data, progress_cb=cb,
                                          cancel_cb=lambda: _spraytest_abort["v"])
            _spraytest_state["result"] = res
            _spraytest_state["status"] = "aborted" if res.get("aborted") else "done"
            _spraytest_state["progress"] = 100
        except Exception as e:
            if _spraytest_abort["v"] or "abgebrochen" in str(e).lower():
                _spraytest_state["log"].append("⛔ Abgebrochen.")
                _spraytest_state["status"] = "aborted"
                _spraytest_state["error"] = None
            else:
                _spraytest_state["error"] = str(e)
                _spraytest_state["log"].append("⚠ " + str(e))
                _spraytest_state["log"].append(traceback.format_exc()[:600])
                _spraytest_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/spraytest/status")
def spraytest_status():
    return jsonify({k: _spraytest_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


@app.route("/spraytest/abort", methods=["POST", "OPTIONS"])
def spraytest_abort():
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if _spraytest_state.get("status") != "running":
        return jsonify({"status": "idle", "note": "keine laufende Spray-Test-Runde"})
    _spraytest_abort["v"] = True
    killed = blender_runner.abort_current()
    _spraytest_state["log"].append("⛔ Abbruch angefordert…" + (" (Blender gestoppt)" if killed else ""))
    return jsonify({"status": "aborting", "killed": killed})


@app.route("/spraytest/rounds")
def spraytest_rounds():
    import ema_spraytest
    return jsonify(ema_spraytest.list_rounds())


@app.route("/spraytest/round/<rid>")
def spraytest_round(rid: str):
    if not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_spraytest
    data = ema_spraytest.load_round(rid)
    if not data:
        return jsonify({"error": "Runde nicht gefunden"}), 404
    return jsonify(data)


@app.route("/spraytest/round/<rid>/marked", methods=["POST", "OPTIONS"])
def spraytest_round_marked(rid: str):
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_spraytest
    ids = (request.get_json(force=True) or {}).get("marked") or []
    data = ema_spraytest.set_marked(rid, ids)
    if data is None:
        return jsonify({"error": "Runde nicht gefunden"}), 404
    return jsonify({"status": "ok", "marked": data.get("marked")})


@app.route("/spraytest/round/<rid>/delete", methods=["POST", "OPTIONS"])
def spraytest_round_delete(rid: str):
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(rid):
        return jsonify({"error": "ungültig"}), 403
    import ema_spraytest
    ok = ema_spraytest.delete_round(rid)
    return jsonify({"status": "deleted" if ok else "missing"})


@app.route("/spraytest/video/<rid>/<vid>")
def spraytest_video(rid: str, vid: str):
    if not (_safe_name(rid) and _safe_name(vid)):
        return jsonify({"error": "ungültig"}), 403
    import ema_spraytest
    beauty = str(request.args.get("beauty") or "") not in ("", "0", "false")
    mp4 = ema_spraytest.video_path(rid, vid, beauty=beauty)
    if not mp4:
        return jsonify({"error": "Kein Video für diese Variante"}), 404
    return send_file(mp4, mimetype="video/mp4")


@app.route("/spraytest/favorites", methods=["GET", "POST", "OPTIONS"])
def spraytest_favorites():
    """💾 Spray-Favoriten: GET = Liste, POST = {name, params, sim, src} speichern."""
    if request.method == "OPTIONS":
        return "", 200
    import ema_spraytest
    if request.method == "GET":
        return jsonify(ema_spraytest.list_favorites())
    fav = ema_spraytest.save_favorite(request.get_json(force=True) or {})
    return jsonify({"status": "ok", "favorite": fav})


@app.route("/spraytest/favorites/<fid>/delete", methods=["POST", "OPTIONS"])
def spraytest_favorite_delete(fid: str):
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(fid):
        return jsonify({"error": "ungültig"}), 403
    import ema_spraytest
    ok = ema_spraytest.delete_favorite(fid)
    return jsonify({"status": "deleted" if ok else "missing"})


@app.route("/spraytest/beauty", methods=["POST", "OPTIONS"])
def spraytest_beauty():
    """✨ Schönheits-Render: EINE Variante einer Runde hochauflösend neu backen
    (Body {rid, vid, resolution?, frames?, slowmo?}); teilt _spraytest_state."""
    if request.method == "OPTIONS":
        return "", 200
    import blender_runner
    if not blender_runner.BLENDER_OK:
        return jsonify({"error": blender_runner.INSTALL_HINT, "need_install": True}), 503
    if _spraytest_state["status"] == "running" or _oil_state["status"] == "running":
        return jsonify({"error": "Es läuft bereits ein Blender-Job (Spritzöl/Spray-Test)"}), 409
    data = request.get_json(force=True) or {}
    rid, vid = str(data.get("rid") or ""), str(data.get("vid") or "")
    if not (_safe_name(rid) and _safe_name(vid)):
        return jsonify({"error": "ungültig"}), 403

    _spraytest_abort["v"] = False
    blender_runner.clear_abort()
    _spraytest_state.update({"status": "running", "progress": 0, "log": [],
                             "result": None, "error": None})

    def _worker():
        import ema_spraytest, traceback
        def cb(msg, pct=None):
            _spraytest_state["log"].append(msg)
            if pct is not None:
                _spraytest_state["progress"] = int(pct)
        try:
            res = ema_spraytest.run_beauty(rid, vid, opts=data, progress_cb=cb,
                                           cancel_cb=lambda: _spraytest_abort["v"])
            _spraytest_state["result"] = res
            if res.get("aborted"):
                _spraytest_state["status"] = "aborted"
            elif res.get("ok"):
                _spraytest_state["status"] = "done"
            else:
                _spraytest_state["error"] = res.get("error")
                _spraytest_state["status"] = "error"
            _spraytest_state["progress"] = 100
        except Exception as e:
            if _spraytest_abort["v"] or "abgebrochen" in str(e).lower():
                _spraytest_state["log"].append("⛔ Abgebrochen.")
                _spraytest_state["status"] = "aborted"
                _spraytest_state["error"] = None
            else:
                _spraytest_state["error"] = str(e)
                _spraytest_state["log"].append("⚠ " + str(e))
                _spraytest_state["log"].append(traceback.format_exc()[:600])
                _spraytest_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/em3d/preview", methods=["POST", "OPTIONS"])
def em3d_preview():
    """Schnelle 3D-MODELL-Vorschau (Gmsh-Mesh → vtk-Render), OHNE Elmer. Teilt sich
    Status/Anzeige mit /em3d (``_em3d_state``)."""
    if request.method == "OPTIONS":
        return "", 200
    if _em3d_state["status"] == "running":
        return jsonify({"error": "3D-Job läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    proj_dir, proj_id = _em3d_project_dir(data)
    _em3d_state.update({"status": "running", "progress": 0, "log": [],
                        "result": None, "error": None})

    def _worker():
        import ema_em3d
        def cb(msg, pct=None):
            _em3d_state["log"].append(msg)
            if pct is not None:
                _em3d_state["progress"] = int(pct)
        try:
            res = ema_em3d.render_model_preview(data, proj_dir, progress_cb=cb)
            res["project_id"] = proj_id
            _em3d_state.update({"result": res, "status": "done", "progress": 100})
        except Exception as e:
            import traceback
            _em3d_state["error"] = str(e)
            _em3d_state["log"].append("⚠ " + str(e))
            _em3d_state["log"].append(traceback.format_exc()[:600])
            _em3d_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


@app.route("/em3d/vtu")
def em3d_vtu():
    """Lädt die VTU-Ergebnisdatei (ParaView) des letzten 3D-Laufs herunter."""
    res = _em3d_state.get("result") or {}
    vtu = res.get("vtu_path")
    if not vtu or not os.path.exists(vtu):
        return jsonify({"error": "keine VTU vorhanden"}), 404
    return send_file(vtu, as_attachment=True, download_name="motor_3d_feld.vtu")


def _em3d_point_path(list_key, single_key):
    """Löst den Browser-VTP-/Linien-Pfad auf: optional ``?i=<index>`` wählt beim Sweep
    den i-ten Betriebspunkt (``sweep_vtp``/``sweep_lines``); sonst der Detail-/Einzelpfad."""
    res = _em3d_state.get("result") or {}
    i = request.args.get("i")
    if i is not None:
        try:
            idx = int(i)
            paths = res.get(list_key) or []
            if 0 <= idx < len(paths) and paths[idx]:
                return paths[idx]
        except (ValueError, TypeError):
            pass
    return res.get(single_key)


@app.route("/em3d/vtp")
def em3d_vtp():
    """Serviert die schlanke .vtp (Festkörper-Oberfläche, |B|) für den eingebetteten
    vtk.js-Browser-Viewer. ``?i=`` wählt beim Sweep den jeweiligen Drehzahl-Punkt."""
    vtp = _em3d_point_path("sweep_vtp", "vtp_path")
    if not vtp or not os.path.exists(vtp):
        return jsonify({"error": "keine VTP vorhanden"}), 404
    return send_file(vtp, mimetype="application/octet-stream")


@app.route("/em3d/streamlines")
def em3d_streamlines():
    """Serviert die Feldlinien-.vtp (Polylinien, |B|) für den Browser-Viewer.
    ``?i=`` wählt beim Sweep den jeweiligen Drehzahl-Punkt."""
    lines = _em3d_point_path("sweep_lines", "lines_path")
    if not lines or not os.path.exists(lines):
        return jsonify({"error": "keine Feldlinien vorhanden"}), 404
    return send_file(lines, mimetype="application/octet-stream")


@app.route("/vendor/<path:name>")
def vendor_file(name):
    """Lokal eingebettete JS-Bibliotheken (z. B. vtk.js für den 3D-Browser-Viewer)."""
    if not _safe_name(name):
        return jsonify({"error": "ungültiger Name"}), 403
    vdir = os.path.join(os.path.dirname(__file__), "vendor")
    if not os.path.exists(os.path.join(vdir, name)):
        return jsonify({"error": "nicht gefunden"}), 404
    return send_from_directory(vdir, name)


@app.route("/em3d/paraview")
def em3d_paraview():
    """Öffnet die VTU des letzten 3D-Laufs direkt in der ParaView-GUI (wie „🔧 FreeCAD"
    das FCStd öffnet). Lädt die Datei, färbt nach |B| und passt die Kamera an."""
    import subprocess, shutil
    res = _em3d_state.get("result") or {}
    vtu = res.get("vtu_path")
    if not vtu or not os.path.exists(vtu):
        return jsonify({"error": "Keine 3D-Ergebnisdatei — erst 3D-Feld berechnen"}), 404
    pv = shutil.which("paraview")
    if not pv:
        return jsonify({"error": "ParaView nicht gefunden. Installation: sudo apt install paraview",
                        "need_install": True}), 503
    # --data lädt die VTU direkt als Quelle (robust über alle ParaView-Builds; das
    # Einfärben nach |B| ist dann ein Klick auf „magnetic flux density"/„Apply").
    try:
        subprocess.Popen([pv, "--data=" + vtu],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return jsonify({"error": f"ParaView starten fehlgeschlagen: {e}"}), 500
    return jsonify({"status": "launched", "file": vtu})


@app.route("/em3d/submodel", methods=["POST", "OPTIONS"])
def em3d_submodel():
    """ROI-Verfeinerung: rechnet das VOLLE Modell mit dem im Body übergebenen Quader
    (``roi_box`` xmin..zmax mm, ``refine_factor``) lokal feiner neu und löst komplett neu
    (normaler Außenrand, KEINE BC-Übertragung — ein echtes Submodell mit B-Rand explodiert in
    diesem Elmer-Build, s. memory project_em3d_submodel_bc). Teilt ``_em3d_state`` + alle
    Viewer-Routen mit /em3d (eigene VTU/VTP). 503 wenn Elmer fehlt."""
    if request.method == "OPTIONS":
        return "", 200
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return jsonify({"error": elmer_runner.INSTALL_HINT, "need_install": True}), 503
    if _em3d_state["status"] == "running":
        return jsonify({"error": "3D-Berechnung läuft bereits"}), 409
    data = request.get_json(force=True) or {}
    if not data.get("roi_box"):
        return jsonify({"error": "Kein Verfeinerungsgebiet (roi_box) angegeben"}), 400

    proj_dir, proj_id = _em3d_project_dir(data)

    _em3d_state.update({"status": "running", "progress": 0, "log": [],
                        "result": None, "error": None})

    def _worker():
        import ema_em3d
        def cb(msg, pct=None):
            _em3d_state["log"].append(msg)
            if pct is not None:
                _em3d_state["progress"] = int(pct)
        try:
            res = ema_em3d.run_em3d_refine(data, proj_dir, progress_cb=cb)
            res["project_id"] = proj_id
            _em3d_state["result"] = res
            _em3d_state["status"] = "done"
            _em3d_state["progress"] = 100
        except Exception as e:
            import traceback
            _em3d_state["error"] = str(e)
            _em3d_state["log"].append("⚠ " + str(e))
            _em3d_state["log"].append(traceback.format_exc()[:600])
            _em3d_state["status"] = "error"

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started", "project_id": proj_id}), 202


# ── 3D-Lauf speichern / aufrufen (benannter Store, unabhängig vom Analyse-Projekt) ──

_EM3D_RUN_FILEKEYS = ("vtu_path", "vtp_path", "lines_path")


def _em3d_copy_run_files(res, dest):
    """Kopiert die Feld-Dateien eines 3D-Ergebnisses (VTU/VTP/Feldlinien + alle Sweep-
    Punkte) nach ``dest`` und gibt ein neues Result-Dict mit auf ``dest`` umgeschriebenen
    Pfaden zurück (base64-Bilder bleiben inline → Viewer ohne Neurechnen)."""
    import shutil, copy
    out = copy.deepcopy(res)
    os.makedirs(dest, exist_ok=True)

    def _cp(src):
        if src and os.path.exists(src):
            dst = os.path.join(dest, os.path.basename(src))
            try:
                shutil.copy(src, dst); return dst
            except Exception:
                return src
        return src
    for k in _EM3D_RUN_FILEKEYS:
        if out.get(k):
            out[k] = _cp(out[k])
    for lk in ("sweep_vtp", "sweep_lines"):
        if isinstance(out.get(lk), list):
            out[lk] = [_cp(p) for p in out[lk]]
    det = out.get("detail")
    if isinstance(det, dict):
        for k in _EM3D_RUN_FILEKEYS:
            if det.get(k):
                det[k] = _cp(det[k])
    return out


def _em3d_store_run(res, name, config):
    """Legt einen 3D-Lauf benannt im Store des aktiven Projekts ab (``em3d_runs/<id>/``):
    kopiert die Feld-Dateien (VTU/VTP/Feldlinien) hinein und schreibt ``result.json`` +
    ``config.json``. Gibt ``(rid, None)`` bei Erfolg zurück, sonst ``(None, fehlermeldung)``.
    Von der /em3d/save-Route UND vom Job-Auto-Speichern (``_exec_em3d*``) genutzt."""
    name = (name or "").strip() or time.strftime("%Y%m%d_%H%M%S")
    rid = time.strftime("%Y%m%d_%H%M%S") + "_" + "".join(
        c for c in name if c.isalnum() or c in "-_")[:40]
    if not _safe_name(rid):
        return None, "ungültiger Name"
    runs_root = _em3d_runs_root()
    if not runs_root:
        return None, "Kein aktives Projekt – bitte erst ein Projekt wählen"
    dest = os.path.join(runs_root, rid)
    try:
        stored = _em3d_copy_run_files(res, dest)
        stored["saved_id"] = rid
        with open(os.path.join(dest, "result.json"), "w") as f:
            json.dump(stored, f, ensure_ascii=False)
        with open(os.path.join(dest, "config.json"), "w") as f:
            json.dump({"name": name, "timestamp": time.strftime("%Y-%m-%d %H:%M"),
                       "config": config or {}}, f, ensure_ascii=False)
    except Exception as e:
        return None, f"Speichern fehlgeschlagen: {e}"
    return rid, None


@app.route("/em3d/save", methods=["POST", "OPTIONS"])
def em3d_save():
    """Speichert den zuletzt fertig berechneten 3D-Lauf benannt ab (Config aus dem Body +
    Kennwerte/Feld aus ``_em3d_state``). Body = {name, config}."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(force=True) or {}
    res = _em3d_state.get("result")
    if not res or _em3d_state.get("status") != "done":
        return jsonify({"error": "Kein fertiger 3D-Lauf zum Speichern"}), 400
    name = (data.get("name") or "").strip() or time.strftime("%Y%m%d_%H%M%S")
    rid, err = _em3d_store_run(res, name, data.get("config") or {})
    if err:
        code = 400 if "Projekt" in err else (403 if "ungültig" in err else 500)
        return jsonify({"error": err}), code
    return jsonify({"status": "saved", "id": rid, "name": name})


@app.route("/em3d/saved")
def em3d_saved_list():
    """Liste gespeicherter 3D-Läufe des aktiven Projekts (id, Name, Zeit, B_gap, …)."""
    out = []
    runs_root = _em3d_runs_root()
    if not runs_root:
        return jsonify(out)
    for rid in sorted(os.listdir(runs_root), reverse=True):
        d = os.path.join(runs_root, rid)
        cfgp = os.path.join(d, "config.json")
        if not os.path.isdir(d) or not os.path.exists(cfgp):
            continue
        try:
            with open(cfgp) as f:
                cfg = json.load(f)
            res = {}
            rp = os.path.join(d, "result.json")
            if os.path.exists(rp):
                with open(rp) as f:
                    res = json.load(f)
            op = res.get("operating_point") or {}
            out.append({"id": rid, "name": cfg.get("name", rid),
                        "timestamp": cfg.get("timestamp", ""),
                        "b_gap": res.get("b_gap_mid_peak"),
                        "excitation": op.get("excitation"),
                        "is_sweep": bool(res.get("sweep")),
                        "is_submodel": res.get("source") in ("submodel", "refine")})
        except Exception:
            continue
    return jsonify(out)


@app.route("/em3d/saved/<rid>")
def em3d_saved_load(rid):
    """Lädt einen gespeicherten 3D-Lauf: setzt ``_em3d_state['result']`` (Pfade zeigen in
    den Store) → die Viewer-Routen /em3d/vtp|vtu|streamlines|paraview bedienen ihn ohne
    Neurechnen. Liefert {config, result}."""
    if not _safe_name(rid):
        return jsonify({"error": "ungültiger Name"}), 403
    runs_root = _em3d_runs_root()
    if not runs_root:
        return jsonify({"error": "Kein aktives Projekt"}), 400
    d = os.path.join(runs_root, rid)
    rp = os.path.join(d, "result.json")
    if not os.path.exists(rp):
        return jsonify({"error": "Lauf nicht gefunden"}), 404
    if _em3d_state.get("status") == "running":
        return jsonify({"error": "3D-Berechnung läuft gerade"}), 409
    try:
        with open(rp) as f:
            res = json.load(f)
        cfg = {}
        cfgp = os.path.join(d, "config.json")
        if os.path.exists(cfgp):
            with open(cfgp) as f:
                cfg = json.load(f)
    except Exception as e:
        return jsonify({"error": f"Laden fehlgeschlagen: {e}"}), 500
    _em3d_state.update({"status": "done", "progress": 100, "log": [], "error": None,
                        "result": res})
    return jsonify({"config": cfg.get("config") or {}, "result": res,
                    "name": cfg.get("name", rid)})


@app.route("/em3d/saved/<rid>/delete", methods=["POST", "OPTIONS"])
def em3d_saved_delete(rid):
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(rid):
        return jsonify({"error": "ungültiger Name"}), 403
    runs_root = _em3d_runs_root()
    if not runs_root:
        return jsonify({"error": "Kein aktives Projekt"}), 400
    d = os.path.join(runs_root, rid)
    if not os.path.isdir(d):
        return jsonify({"error": "Lauf nicht gefunden"}), 404
    import shutil
    shutil.rmtree(d, ignore_errors=True)
    return jsonify({"status": "deleted", "id": rid})


@app.route("/smoke_test", methods=["POST", "OPTIONS"])
def smoke_test_run():
    """Run smoke_test.py (fast ~15 s sanity check, no FreeCAD) in a subprocess."""
    if request.method == "OPTIONS":
        return "", 200
    if _smoke_state["status"] == "running":
        return jsonify({"error": "Smoke-Test läuft bereits"}), 409
    _smoke_state.update({"status": "running", "progress": 0, "log": [],
                         "result": None, "error": None})
    threading.Thread(target=_run_smoke, daemon=True).start()
    return jsonify({"status": "started"}), 202


def _run_smoke():
    import subprocess, sys, re
    _ansi = re.compile(r"\x1b\[[0-9;]*m")
    try:
        script = os.path.join(os.path.dirname(__file__), "smoke_test.py")
        proc = subprocess.Popen(
            [sys.executable, script], cwd=os.path.dirname(__file__),
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)
        for line in proc.stdout:
            _smoke_state["log"].append(_ansi.sub("", line.rstrip("\n")))
            _smoke_state["log"] = _smoke_state["log"][-300:]
        proc.wait()
        ok = (proc.returncode == 0)
        summary = next((l for l in reversed(_smoke_state["log"]) if "RESULT:" in l), "")
        _smoke_state["result"] = {"ok": ok, "returncode": proc.returncode,
                                  "summary": summary}
        _smoke_state["progress"] = 100
        _smoke_state["status"]   = "done" if ok else "error"
    except Exception as e:
        _smoke_state["error"]  = str(e)
        _smoke_state["log"].append("⚠ " + str(e))
        _smoke_state["status"] = "error"


@app.route("/smoke_test/status")
def smoke_test_status():
    return jsonify({k: _smoke_state[k]
                    for k in ("status", "progress", "log", "result", "error")})


@app.route("/preview_field", methods=["POST", "OPTIONS"])
def preview_field():
    """Render a single field frame (no FreeCAD/FEM/animation) for a quick preview."""
    if request.method == "OPTIONS":
        return "", 200
    if _state["status"] == "running":
        return jsonify({"error": "Pipeline läuft bereits"}), 409
    data = request.get_json(force=True)
    try:
        from ema_pipeline import render_preview_frame
        out = render_preview_frame(data)
        return jsonify(out)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()[:400]}), 500


@app.route("/optimize", methods=["POST", "OPTIONS"])
def optimize_start():
    """Start an LLM-steered target-value optimisation (fast analytical evaluator).
    Body = {base_payload, objective, constraints, free, iterations, batch}."""
    if request.method == "OPTIONS":
        return "", 200
    if _opt_state["status"] == "running":
        return jsonify({"error": "Optimierung läuft bereits"}), 409
    spec = request.get_json(force=True)
    _opt_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})
    threading.Thread(target=_optimize_body, args=(spec,), daemon=True).start()
    return jsonify({"status": "started"}), 202


def _optimize_body(spec):
    """Synchroner Lauf-Körper der Zielwertoptimierung — von der Route (im Thread) UND der
    Job-Warteschlange (direkt) genutzt. Erwartet, dass ``_opt_state`` bereits auf running
    gesetzt wurde."""
    import ema_optimize
    def cb(msg, pct=None):
        _opt_state["log"].append(msg)
        if pct is not None:
            _opt_state["progress"] = int(pct)
    try:
        _opt_state["result"] = ema_optimize.optimize(spec, progress_cb=cb)
        _opt_state["status"] = "done"
        _opt_state["progress"] = 100
    except Exception as e:
        import traceback
        _opt_state["error"] = str(e)
        _opt_state["log"].append("⚠ " + str(e))
        _opt_state["status"] = "error"
        print(traceback.format_exc())


@app.route("/optimize/status")
def optimize_status():
    return jsonify({
        "status":   _opt_state["status"],
        "progress": _opt_state["progress"],
        "log":      _opt_state["log"][-40:],
        "result":   _opt_state["result"],
        "error":    _opt_state["error"],
    })


@app.route("/text2ema", methods=["POST", "OPTIONS"])
def text2ema():
    """Derive an IPM parameter set from a free-text application description (LLM).
    Body: {description}. Returns {params, begruendung, model}."""
    if request.method == "OPTIONS":
        return "", 200
    import ema_text2ema
    data = request.get_json(force=True)
    try:
        return jsonify(ema_text2ema.derive(data.get("description", "")))
    except urllib.error.URLError:
        return jsonify({"error": "Ollama nicht erreichbar (localhost:11434)."}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/optimize/meta")
def optimize_meta():
    """Available free parameters + metrics for the optimiser UI."""
    import ema_optimize
    fp = {k: {"label": v["label"], "lo": v["lo"], "hi": v["hi"],
              "int": v["type"] is int}
          for k, v in ema_optimize.FREE_PARAMS.items()}
    return jsonify({"free_params": fp, "metrics": ema_optimize.METRICS})


@app.route("/design_ai", methods=["POST", "OPTIONS"])
def design_ai_start():
    """KI entwirft komplette Maschinen aus einer Beschreibung (Designer-Pfad).
    Body = {brief, n, model?, max_regen?}. Jeder Entwurf wird FreeCAD/FEM-frei
    vorsortiert; „schlechte" werden bis ``max_regen`` mal neu generiert. Returns
    variants (mit ``quality``-Urteil) + rejected/regenerated."""
    if request.method == "OPTIONS":
        return "", 200
    if _design_state["status"] == "running":
        return jsonify({"error": "KI-Entwurf läuft bereits"}), 409
    body  = request.get_json(force=True) or {}
    brief = body.get("brief", "") or body.get("description", "")
    n     = int(body.get("n", 3))
    max_regen = int(body.get("max_regen", 2))
    model = body.get("model") or "ministral-3:14b"
    _design_state.update({"status": "running", "progress": 0, "log": [],
                          "result": None, "error": None})

    def _worker():
        import ema_design_ai
        def cb(msg, pct=None):
            _design_state["log"].append(msg)
            if pct is not None:
                _design_state["progress"] = int(pct)
        try:
            _design_state["result"] = ema_design_ai.design_variants(
                brief, n=n, model=model, max_regen=max_regen, progress_cb=cb)
            _design_state["status"] = "done"
            _design_state["progress"] = 100
        except Exception as e:
            import traceback
            _design_state["error"] = str(e)
            _design_state["log"].append("⚠ " + str(e))
            _design_state["status"] = "error"
            print(traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/design_ai_ranged", methods=["POST", "OPTIONS"])
def design_ai_ranged_start():
    """Bereichs-/Zufalls-Entwurf (Designer-Pfad). Body = {ranges, n, model?, max_regen?}
    mit ranges = {statorOD:[lo,hi], axialLen:[lo,hi], shaftD:[lo,hi]} (Luftspalt fest
    0,5–2 mm). Pro Variante werden die Maße zufällig gezogen + erzwungen, das LLM
    zeichnet Magnete/Barrieren. Gerechnet wird an festen Drehzahlen (result.rpm_list).
    Teilt sich Status/Polling mit ``/design_ai`` (``_design_state``)."""
    if request.method == "OPTIONS":
        return "", 200
    if _design_state["status"] == "running":
        return jsonify({"error": "KI-Entwurf läuft bereits"}), 409
    body   = request.get_json(force=True) or {}
    ranges = body.get("ranges") or {}
    brief  = body.get("brief", "") or ""
    n      = int(body.get("n", 3))
    max_regen = int(body.get("max_regen", 2))
    model  = body.get("model") or "ministral-3:14b"
    _design_state.update({"status": "running", "progress": 0, "log": [],
                          "result": None, "error": None})

    def _worker():
        import ema_design_ai
        def cb(msg, pct=None):
            _design_state["log"].append(msg)
            if pct is not None:
                _design_state["progress"] = int(pct)
        try:
            _design_state["result"] = ema_design_ai.design_variants_ranged(
                ranges, n=n, model=model, max_regen=max_regen, progress_cb=cb, brief=brief)
            _design_state["status"] = "done"
            _design_state["progress"] = 100
        except Exception as e:
            import traceback
            _design_state["error"] = str(e)
            _design_state["log"].append("⚠ " + str(e))
            _design_state["status"] = "error"
            print(traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/design_ai/status")
def design_ai_status():
    return jsonify({
        "status":   _design_state["status"],
        "progress": _design_state["progress"],
        "log":      _design_state["log"][-40:],
        "result":   _design_state["result"],
        "error":    _design_state["error"],
    })


@app.route("/design_optimize", methods=["POST", "OPTIONS"])
def design_optimize_start():
    """Per-Magnet-Fein-Optimierung eines gezeichneten Custom-Designs.
    Body = {base_payload, magnets, barriers, objective, constraints, iterations, batch}."""
    if request.method == "OPTIONS":
        return "", 200
    if _design_opt_state["status"] == "running":
        return jsonify({"error": "Magnet-Optimierung läuft bereits"}), 409
    spec = request.get_json(force=True)
    _design_opt_state.update({"status": "running", "progress": 0, "log": [],
                              "result": None, "error": None})

    def _worker():
        import ema_design_optimize
        def cb(msg, pct=None):
            _design_opt_state["log"].append(msg)
            if pct is not None:
                _design_opt_state["progress"] = int(pct)
        try:
            _design_opt_state["result"] = ema_design_optimize.optimize_custom(spec, progress_cb=cb)
            _design_opt_state["status"] = "done"
            _design_opt_state["progress"] = 100
        except Exception as e:
            import traceback
            _design_opt_state["error"] = str(e)
            _design_opt_state["log"].append("⚠ " + str(e))
            _design_opt_state["status"] = "error"
            print(traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/design_optimize/status")
def design_optimize_status():
    return jsonify({
        "status":   _design_opt_state["status"],
        "progress": _design_opt_state["progress"],
        "log":      _design_opt_state["log"][-40:],
        "result":   _design_opt_state["result"],
        "error":    _design_opt_state["error"],
    })


@app.route("/param_study", methods=["POST", "OPTIONS"])
def param_study_start():
    """Sweep ONE parameter from x to y in N steps at a FIXED speed (fast evaluator).
    Body = {payload, param, lo, hi, steps, rpm}."""
    if request.method == "OPTIONS":
        return "", 200
    if _study_state["status"] == "running":
        return jsonify({"error": "Parameterstudie läuft bereits"}), 409
    data = request.get_json(force=True)
    _study_state.update({"status": "running", "progress": 0, "log": [],
                         "result": None, "error": None,
                         "payload": data.get("payload")})   # kept for the study report
    threading.Thread(target=_param_study_body, args=(data,), daemon=True).start()
    return jsonify({"status": "started"}), 202


def _param_study_body(data):
    """Synchroner Lauf-Körper der Parameterstudie — von der Route (im Thread) UND der
    Job-Warteschlange (direkt) genutzt. Erwartet ``_study_state`` bereits auf running +
    ``payload`` gesetzt."""
    import ema_paramstudy
    def cb(msg, pct=None):
        _study_state["log"].append(msg)
        if pct is not None:
            _study_state["progress"] = int(pct)
    try:
        _study_state["result"] = ema_paramstudy.run_study(
            data["payload"], data["param"], data["lo"], data["hi"],
            steps=int(data.get("steps", 100)), rpm=data.get("rpm"),
            field_frames=int(data.get("field_frames", 0)),
            field_N=int(data.get("field_N", 300)),
            out_dir=STUDY_FIELD_DIR, progress_cb=cb)
        _study_state["status"] = "done"
        _study_state["progress"] = 100
    except Exception as e:
        import traceback
        _study_state["error"] = str(e)
        _study_state["log"].append("⚠ " + str(e))
        _study_state["status"] = "error"
        print(traceback.format_exc())


@app.route("/param_study/status")
def param_study_status():
    return jsonify({
        "status":   _study_state["status"],
        "progress": _study_state["progress"],
        "log":      _study_state["log"][-40:],
        "result":   _study_state["result"],
        "error":    _study_state["error"],
    })


@app.route("/param_study/csv")
def param_study_csv():
    """Per-step values of the most recent study as CSV (parameter + all metrics)."""
    res = _study_state.get("result")
    if not res:
        return jsonify({"error": "keine Parameterstudie"}), 404
    xs   = res.get("x", [])
    mets = res.get("metrics", {})
    meta = res.get("metric_meta", [])
    keys = [m["key"] for m in meta]
    header = [res.get("label", res.get("param", "param"))] + \
             [f"{m['label']} [{m['unit']}]" if m['unit'] else m['label'] for m in meta]
    lines = [";".join(header)]
    for i, x in enumerate(xs):
        row = [f"{x:g}"] + [("" if mets.get(k, [None]*len(xs))[i] is None
                             else f"{mets[k][i]:g}") for k in keys]
        lines.append(";".join(row))
    csv = "\n".join(lines)
    return Response(csv, mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=parameterstudie.csv"})


@app.route("/param_study/video")
def param_study_video():
    """Serve the field-line animation of the most recent parameter study (if rendered)."""
    path = os.path.join(STUDY_FIELD_DIR, "anim.mp4")
    if not os.path.exists(path):
        return jsonify({"error": "kein Video"}), 404
    return send_file(path, mimetype="video/mp4")


# Parameter-study LLM report (study data is the basis of the prompt)
_study_report_state = {"status": "idle", "progress": 0, "log": [],
                       "pdf_path": None, "error": None}


@app.route("/param_study/report", methods=["POST", "OPTIONS"])
def param_study_report():
    if request.method == "OPTIONS":
        return "", 200
    if _study_report_state["status"] == "running":
        return jsonify({"error": "Studienbericht läuft bereits"}), 409
    if not (_study_state.get("result")):
        return jsonify({"error": "Keine Parameterstudie vorhanden — erst eine Studie rechnen"}), 400
    model = (request.get_json(silent=True) or {}).get("model") or "ministral-3:14b"
    study   = _study_state["result"]
    payload = _study_state.get("payload") or {}
    _study_report_state.update({"status": "running", "progress": 0, "log": [],
                                "pdf_path": None, "error": None})

    def _worker():
        import ema_report
        def cb(msg, pct=None):
            _study_report_state["log"].append(msg)
            if pct is not None:
                _study_report_state["progress"] = int(pct)
        try:
            r = ema_report.generate_paramstudy_report(
                study, payload, STUDY_FIELD_DIR, model=model, progress_cb=cb)
            _study_report_state["pdf_path"] = r["pdf"]
            _study_report_state["status"]   = "done"
            _study_report_state["progress"] = 100
        except Exception as e:
            import traceback
            _study_report_state["error"] = str(e)
            _study_report_state["log"].append("⚠ " + str(e))
            _study_report_state["status"] = "error"
            print(traceback.format_exc())

    threading.Thread(target=_worker, daemon=True).start()
    return jsonify({"status": "started"}), 202


@app.route("/param_study/report/status")
def param_study_report_status():
    return jsonify({
        "status":   _study_report_state["status"],
        "progress": _study_report_state["progress"],
        "log":      _study_report_state["log"][-40:],
        "error":    _study_report_state["error"],
        "has_pdf":  bool(_study_report_state.get("pdf_path") and
                         os.path.exists(_study_report_state["pdf_path"])),
    })


@app.route("/param_study/report/download")
def param_study_report_download():
    path = _study_report_state.get("pdf_path")
    if not path or not os.path.exists(path):
        return jsonify({"error": "kein Bericht"}), 404
    return send_file(path, as_attachment=True, download_name="parameterstudie.pdf")


def _run(data):
    from ema_pipeline import run_pipeline, create_project_dir
    try:
        # In ein BESTEHENDES Projekt rechnen, wenn der Client ein aktives Projekt
        # mitschickt (Projekt-Tab: zuerst anlegen, dann hineinrechnen). Akzeptiert,
        # sobald der Ordner existiert — auch leere Projekte (status "neu") ohne
        # motor.FCStd werden wiederverwendet, statt jedes Mal ein neues anzulegen.
        # STEP-Import nutzt denselben Weg: die erkannte motor.FCStd (benanntes "Rotor")
        # bleibt erhalten, sonst würde run_pipeline die Geometrie parametrisch neu bauen.
        reuse_id  = data.get("project_id")
        reuse_dir = (os.path.join(PROJECTS_ROOT, reuse_id)
                     if reuse_id and _safe_name(reuse_id) else None)
        if reuse_dir and os.path.isdir(reuse_dir):
            proj_dir, proj_id = reuse_dir, reuse_id
        else:
            proj_dir, proj_id = create_project_dir(PROJECTS_ROOT, data.get("project_name", ""))
        _state["project_dir"] = proj_dir
        _state["project_id"]  = proj_id
        run_pipeline(data, _state, _frames, WORKSPACE, proj_dir)
    except Exception as e:
        import traceback
        _state["log"].append(f"FATAL: {e}\n{traceback.format_exc()[:600]}")
        _state["status"] = "error"


@app.route("/status")
def status():
    return jsonify({
        "status":     _state["status"],
        "progress":   _state["progress"],
        "log":        _state["log"][-30:],
        "project_id": _state.get("project_id"),
    })


@app.route("/results")
def results():
    if _state["results"] is None:
        return jsonify({"error": "no results"}), 404
    return jsonify(_state["results"])


@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    """LLM Q&A over the loaded project's results, or over a variant comparison.
    Body: {message, history:[{role,content}], scope:"project"|"compare", ids:[...]}.
    """
    if request.method == "OPTIONS":
        return "", 200
    import ema_chat
    data = request.get_json(force=True)
    msg = (data.get("message") or "").strip()
    if not msg:
        return jsonify({"error": "leere Nachricht"}), 400
    history = data.get("history") or []
    scope = data.get("scope", "project")
    try:
        if scope == "compare":
            import ema_compare
            ids = [i for i in (data.get("ids") or []) if _safe_name(i)]
            variants = ema_compare.load_projects(PROJECTS_ROOT, ids)
            if len(variants) < 2:
                return jsonify({"error": "Mindestens 2 Projekte für den Vergleichs-Chat wählen"}), 400
            reply = ema_chat.chat_compare(msg, history, variants)
        else:
            results = _state.get("results")
            if not results:
                return jsonify({"error": "Kein Projekt geladen — erst eine Analyse ausführen oder ein Projekt laden"}), 400
            # Load the project's meta.json so the chat is grounded on its parameter
            # datasheet (results.json holds outputs only, not the input parameters).
            meta = {}
            pd = _state.get("project_dir")
            if pd and os.path.exists(os.path.join(pd, "meta.json")):
                try:
                    with open(os.path.join(pd, "meta.json")) as f:
                        meta = json.load(f)
                except Exception:
                    meta = {}
            # Projektakte als gemeinsame Quelle: Notizen erden den Assistenten; bei
            # Altprojekten ohne meta.json liefert die synthetisierte Akte das Payload.
            if pd:
                try:
                    import ema_projekt
                    man = ema_projekt.load_or_synthesize(pd, write_back=False)
                    if not meta:
                        meta = {"label": man.get("label", ""),
                                "payload": (man.get("inputs") or {}).get("payload", {})}
                    if man.get("notes"):
                        meta["notes"] = man["notes"]
                except Exception:
                    pass
            reply = ema_chat.chat_results(msg, history, results, meta=meta,
                                          project_dir=pd)
        return jsonify({"reply": reply})
    except urllib.error.URLError:
        return jsonify({"error": "Ollama nicht erreichbar (localhost:11434). Läuft der Dienst?"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/field/<int:n>")
def field_frame(n: int):
    return field_frame_mode("rotate", n)   # legacy alias → rotate bucket


@app.route("/field/<mode>/<int:n>")
def field_frame_mode(mode: str, n: int):
    import base64
    bucket = _frames.get(mode, [])
    if n >= len(bucket):
        return "", 404
    img = base64.b64decode(bucket[n])
    return Response(img, mimetype="image/png",
                    headers={"Cache-Control": "no-store"})


# ── Image / file lookup helpers ──────────────────────────────────────────────

def _safe_name(name: str) -> bool:
    """Block path-traversal."""
    import re
    return not re.search(r'[^\w\-.]', name) and ".." not in name


def _resolve_image(rel: str) -> str | None:
    """Find image either in current project dir or workspace fallback."""
    pd = _state.get("project_dir")
    for base in [pd, WORKSPACE] if pd else [WORKSPACE]:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            return p
    return None


@app.route("/cad_image/<path:name>")
def cad_image(name: str):
    if not _safe_name(name):
        return "", 403
    path = _resolve_image(os.path.join("cad_images", name))
    if not path:
        return "", 404
    resp = send_file(path, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/chart/<path:name>")
def chart_image(name: str):
    if not _safe_name(name):
        return "", 403
    path = _resolve_image(os.path.join("charts", name))
    if not path:
        return "", 404
    resp = send_file(path, mimetype="image/png")
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/file/<path:name>")
def project_file(name: str):
    """Generic project-file download (motor.FCStd, motor.step, results.json)."""
    if not _safe_name(name):
        return "", 403
    pd = _state.get("project_dir") or WORKSPACE
    path = os.path.join(pd, name)
    if not os.path.exists(path):
        return "", 404
    return send_file(path, as_attachment=True)


# ── FreeCAD launching ────────────────────────────────────────────────────────
# FreeCAD 1.1.1 is built in ~/freecad_1.1_quellcode. The /opt/freecad-1.1
# binaries are actually 1.2 with a known visualisation bug, so we route
# everything through `pixi run` to pick up the working 1.1.1 build and its
# conda env. `pixi run --manifest-path <path> -- <cmd…>` runs inside the env.

FREECAD_ROOT = os.path.expanduser("~/freecad_1.1_quellcode")


def _pixi_freecad_cmd(*args: str) -> list[str]:
    return ["pixi", "run", "--manifest-path",
            os.path.join(FREECAD_ROOT, "pixi.toml"), "--",
            "build/release/bin/FreeCAD", *args]


def _pixi_freecadcmd_cmd(*args: str) -> list[str]:
    return ["pixi", "run", "--manifest-path",
            os.path.join(FREECAD_ROOT, "pixi.toml"), "--",
            "build/release/bin/FreeCADCmd", *args]


def _freecad_available() -> bool:
    return os.path.exists(os.path.join(FREECAD_ROOT, "build/release/bin/FreeCAD"))


def _current_fcstd() -> str | None:
    pd = _state.get("project_dir")
    candidates = []
    if pd:
        candidates += [os.path.join(pd, "motor.FCStd"),
                       os.path.join(pd, "rotor.FCStd")]
    candidates += [os.path.join(WORKSPACE, "motor.FCStd"),
                   os.path.join(WORKSPACE, "rotor.FCStd")]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


@app.route("/open_freecad")
def open_freecad():
    import subprocess
    fcstd = _current_fcstd()
    if not fcstd:
        return jsonify({"error": "Keine FCStd-Datei gefunden — erst Analyse starten"}), 404
    if not _freecad_available():
        return jsonify({"error": f"FreeCAD 1.1.1 nicht gefunden in {FREECAD_ROOT}"}), 500

    # Deferred visibility via QTimer — when FreeCAD opens a doc that was saved
    # headlessly, ViewProviders attach AFTER openDocument returns, so setting
    # Visibility immediately is racy. Queue it onto the Qt event loop.
    macro_dir = os.path.dirname(fcstd)
    macro_path = os.path.join(macro_dir, "_open_motor.FCMacro")
    macro_code = f'''# Auto-generated launcher
import FreeCAD as App
import FreeCADGui as Gui

_PATH = r"{fcstd}"
doc = App.openDocument(_PATH)
Gui.ActiveDocument = Gui.getDocument(doc.Name)

def _show_all():
    try:
        gdoc = Gui.getDocument(doc.Name)
        for obj in doc.Objects:
            vp = gdoc.getObject(obj.Name) if gdoc else None
            if vp is not None:
                try: vp.Visibility = True
                except Exception: pass
            try:
                if obj.ViewObject is not None:
                    obj.ViewObject.Visibility = True
            except Exception:
                pass
        v = Gui.activeDocument().activeView()
        v.viewIsometric()
        Gui.SendMsgToActiveView("ViewFit")
    except Exception as e:
        App.Console.PrintWarning(f"show_all failed: {{e}}\\n")

# First attempt immediately
_show_all()

# Re-attempt after event loop drained (covers async ViewProvider init)
try:
    from PySide6.QtCore import QTimer
except ImportError:
    try:
        from PySide2.QtCore import QTimer
    except ImportError:
        QTimer = None

if QTimer is not None:
    QTimer.singleShot(400,  _show_all)
    QTimer.singleShot(1200, _show_all)
'''
    with open(macro_path, "w") as f:
        f.write(macro_code)

    try:
        subprocess.Popen(_pixi_freecad_cmd(macro_path),
                         cwd=FREECAD_ROOT,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as e:
        return jsonify({"error": f"FreeCAD starten fehlgeschlagen: {e}"}), 500
    return jsonify({"status": "launched", "file": fcstd, "version": "1.1.1"})


@app.route("/export_step")
def export_step():
    """Export the current motor.FCStd as STEP (.step) and return file path."""
    import subprocess
    fcstd = _current_fcstd()
    if not fcstd:
        return jsonify({"error": "Keine FCStd-Datei gefunden — erst Analyse starten"}), 404
    if not _freecad_available():
        return jsonify({"error": "FreeCAD 1.1.1 nicht gefunden"}), 500

    step_path = os.path.splitext(fcstd)[0] + ".step"
    macro = f'''
import FreeCAD as App
import Part
doc = App.openDocument(r"{fcstd}")
shapes = [o.Shape for o in doc.Objects if hasattr(o, "Shape") and o.Shape and not o.Shape.isNull()]
if not shapes:
    raise RuntimeError("Keine Geometrie im Dokument")
compound = Part.makeCompound(shapes)
compound.exportStep(r"{step_path}")
print("STEP_OK")
'''
    macro_path = os.path.join(os.path.dirname(fcstd), "_export_step.py")
    with open(macro_path, "w") as f:
        f.write(macro)
    try:
        res = subprocess.run(_pixi_freecadcmd_cmd(macro_path),
                             cwd=FREECAD_ROOT,
                             capture_output=True, text=True, timeout=180)
    except Exception as e:
        return jsonify({"error": f"STEP-Export fehlgeschlagen: {e}"}), 500

    if "STEP_OK" not in res.stdout or not os.path.exists(step_path):
        return jsonify({"error": "STEP-Export fehlgeschlagen",
                        "stderr": (res.stderr or "")[-400:],
                        "stdout": (res.stdout or "")[-400:]}), 500
    return jsonify({"status": "ok", "step_path": step_path,
                    "filename": os.path.basename(step_path),
                    "size_kb": round(os.path.getsize(step_path) / 1024, 1)})


@app.route("/download_step")
def download_step():
    """Download the STEP file (auto-exports if missing)."""
    fcstd = _current_fcstd()
    if not fcstd:
        return jsonify({"error": "Keine FCStd-Datei gefunden"}), 404
    step_path = os.path.splitext(fcstd)[0] + ".step"
    if not os.path.exists(step_path):
        # Auto-export
        r = export_step()
        if isinstance(r, tuple) and r[1] != 200:
            return r
    return send_file(step_path, as_attachment=True,
                     download_name=os.path.basename(step_path))


# ── Project management ──────────────────────────────────────────────────────

_SUMMARY_CACHE: dict = {}   # pid -> (mtime, summary_dict)


def _project_summary(path: str, pid: str) -> dict:
    """results.json['summary'] for a project, cached by mtime. results.json is
    ~1 MB (inline base64), so it is parsed at most once per change — only used
    for the detailed project gallery, not the lightweight dropdown/compare list."""
    rp = os.path.join(path, "results.json")
    try:
        mt = os.path.getmtime(rp)
    except OSError:
        return {}
    cached = _SUMMARY_CACHE.get(pid)
    if cached and cached[0] == mt:
        return cached[1]
    try:
        with open(rp) as f:
            summary = (json.load(f) or {}).get("summary", {}) or {}
    except Exception:
        summary = {}
    _SUMMARY_CACHE[pid] = (mt, summary)
    return summary


@app.route("/projects")
def list_projects():
    """List all saved projects. ?detail=1 adds topology + headline metrics for the
    project gallery (mtime-cached); the bare call stays light (meta.json only)."""
    from ema_topology import TOPOLOGY_LABELS
    detail = request.args.get("detail") == "1"
    if not os.path.isdir(PROJECTS_ROOT):
        return jsonify({"projects": []})
    projs = []
    for name in sorted(os.listdir(PROJECTS_ROOT), reverse=True):
        path = os.path.join(PROJECTS_ROOT, name)
        if not os.path.isdir(path) or name.startswith("_"):
            continue
        meta_path = os.path.join(path, "meta.json")
        meta = {}
        if os.path.exists(meta_path):
            try:
                with open(meta_path) as f: meta = json.load(f)
            except Exception:
                pass
        has_results = os.path.exists(os.path.join(path, "results.json"))
        has_fcstd   = os.path.exists(os.path.join(path, "motor.FCStd"))
        has_step    = os.path.exists(os.path.join(path, "motor.step"))
        report_file = _latest_report(path)
        geom = meta.get("geom", {}) or {}
        card = {
            "id":          name,
            "label":       meta.get("label", name),
            "created":     meta.get("created", ""),
            "rpm_range":   meta.get("rpm_range", ""),
            "has_results": has_results,
            "has_fcstd":   has_fcstd,
            "has_step":    has_step,
            "has_thumb":   os.path.exists(os.path.join(path, "cad_images", "motor_cross_section.png")),
            "has_em_field": os.path.exists(os.path.join(path, "charts", "em_field.png")),
            "has_report":  bool(report_file),
            "report_file": report_file or "",
        }
        if detail:
            card["topology"] = TOPOLOGY_LABELS.get(geom.get("magShape", "v"), geom.get("magShape"))
            card["p"]         = geom.get("p")
            card["stator_od"] = geom.get("statorOD")
            card["axial"]     = meta.get("axial_len") or geom.get("axialLen")
            card["cooling"]   = meta.get("cooling")
            # Projektakte-Kennzeichen (Status/Abstammung/Verknüpfungen/Stufen) — nur
            # aus dem leichten Manifest gelesen, falls vorhanden (kein Synthese-Aufwand).
            try:
                import ema_projekt
                man = ema_projekt.load(path)
                if man:
                    card["status"]          = man.get("status")
                    card["tags"]            = man.get("tags", [])
                    card["parent"]          = (man.get("lineage") or {}).get("parent")
                    card["links_count"]     = len(man.get("links", []))
                    card["evolution_count"] = len(man.get("evolution", []))
            except Exception:
                pass
            if has_results:
                s = _project_summary(path, name)
                card["metrics"] = {
                    "Kt":           s.get("Kt_Nm_per_A"),
                    "T_maxwell":    s.get("T_maxwell_Nm"),
                    "max_safe_rpm": s.get("max_safe_rpm"),
                    "T_magnet":     s.get("T_magnet_C"),
                    "mass_g":       s.get("mass_g"),
                    "P_total":      s.get("P_total_W"),
                    "verbrauch":    s.get("cycle_kWh100km"),
                }
        projs.append(card)
    return jsonify({"projects": projs, "current": _state.get("project_id")})


@app.route("/project/<pid>/thumb")
def project_thumb(pid: str):
    """Serve a project's cross-section thumbnail for the gallery."""
    if not _safe_name(pid):
        return "", 403
    base = os.path.join(PROJECTS_ROOT, pid, "cad_images")
    for fn in ("motor_cross_section.png", "motor_side_view.png"):
        p = os.path.join(base, fn)
        if os.path.exists(p):
            resp = send_file(p, mimetype="image/png")
            resp.headers["Cache-Control"] = "max-age=3600"
            return resp
    return "", 404


@app.route("/project/<pid>/em_field")
def project_em_field(pid: str):
    """Serve a project's high-res EM-simulation field map for the gallery (open
    circuit). Falls back to the loaded-field image if only that one exists."""
    if not _safe_name(pid):
        return "", 403
    base = os.path.join(PROJECTS_ROOT, pid, "charts")
    for fn in ("em_field.png", "em_field_load.png"):
        p = os.path.join(base, fn)
        if os.path.exists(p):
            resp = send_file(p, mimetype="image/png")
            resp.headers["Cache-Control"] = "max-age=3600"
            return resp
    return "", 404


def _latest_report(path: str) -> str | None:
    """Basename of the most recently generated report PDF in a project (by mtime),
    or None. Honours "immer nur der letzte Bericht" when the UI links to it."""
    cands = []
    for fn in ("bericht.pdf", "bericht_agentisch.pdf"):
        p = os.path.join(path, fn)
        if os.path.exists(p):
            cands.append((os.path.getmtime(p), fn))
    return max(cands)[1] if cands else None


def _reload_frames_from_disk(path: str) -> dict:
    """Re-populate every field-mode bucket in `_frames` from its subdir on disk.
    Returns {bucket: count}. Shared by /project/<id>/load and the partial recompute
    (so the viewer keeps its frames when the field stage isn't re-run)."""
    import base64 as _b64
    counts = {}
    for bucket, subdir in FIELD_SUBDIRS.items():
        _frames[bucket].clear()
        fdir = os.path.join(path, subdir)
        if not os.path.isdir(fdir):
            counts[bucket] = 0
            continue
        n = len([f for f in os.listdir(fdir) if f.endswith(".png")])
        for i in range(n):
            fp = os.path.join(fdir, f"frame_{i:04d}.png")
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    _frames[bucket].append(_b64.b64encode(f.read()).decode())
        counts[bucket] = len(_frames[bucket])
    return counts


@app.route("/project/<pid>/recompute", methods=["POST", "OPTIONS"])
def project_recompute(pid: str):
    """Re-run only the SELECTED (forgotten) pipeline stages on an existing project,
    merging into its saved results. Stages ⊆ {field, structural, thermal, drivecycle};
    geometry/EM are reused from disk. Uses the CURRENT form payload so the forgotten
    calc can be (re)configured. Reuses _state + /status + /results like /analyse."""
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    path = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(path) or not os.path.exists(os.path.join(path, "results.json")):
        return jsonify({"error": "Projekt nicht gefunden (results.json fehlt)"}), 404
    if _state["status"] == "running":
        return jsonify({"error": "Pipeline läuft bereits"}), 409

    data    = request.get_json(force=True)
    allowed = {"field", "structural", "thermal", "drivecycle"}
    stages  = {s for s in (data.get("stages") or []) if s in allowed}
    if not stages:
        return jsonify({"error": "Keine gültige Stufe gewählt"}), 400

    # Preload existing frames so the viewer keeps them when "field" is not re-run.
    _reload_frames_from_disk(path)
    _state.update({"status": "running", "progress": 0, "log": [], "results": None})
    threading.Thread(target=_run_partial, args=(data, path, pid, stages),
                     daemon=True).start()
    return jsonify({"status": "started", "stages": sorted(stages)}), 202


def _run_partial(data, proj_dir, pid, stages):
    from ema_pipeline import run_pipeline
    try:
        _state["project_dir"] = proj_dir
        _state["project_id"]  = pid
        run_pipeline(data, _state, _frames, WORKSPACE, proj_dir, stages=stages)
    except Exception as e:
        import traceback
        _state["log"].append(f"FATAL: {e}\n{traceback.format_exc()[:600]}")
        _state["status"] = "error"


@app.route("/project/<pid>/load")
def load_project(pid: str):
    """Set a previously saved project as the active one and return its results."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    path = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(path):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    res_path = os.path.join(path, "results.json")
    if not os.path.exists(res_path):
        return jsonify({"error": "results.json fehlt in diesem Projekt"}), 404
    try:
        with open(res_path) as f:
            results = json.load(f)
    except Exception as e:
        return jsonify({"error": f"results.json lesen fehlgeschlagen: {e}"}), 500

    # Re-populate every field-mode bucket from its subdir on disk
    counts = _reload_frames_from_disk(path)

    _state["results"]     = results
    _state["project_dir"] = path
    _state["project_id"]  = pid
    _state["status"]      = "done"
    return jsonify({"status": "loaded", "id": pid,
                    "n_frames": len(_frames["rotate"]),
                    "frame_counts": counts,
                    "summary": results.get("summary", {})})


@app.route("/project/<pid>/activate", methods=["POST", "OPTIONS"])
def activate_project(pid: str):
    """Lightweight: mark a project as the server-side active one (``_state``) WITHOUT
    loading its results/frames. Lets the Tab-1 'Aktiv'-click steer report + em3d (which
    read ``_state['project_dir']``) at the chosen project. Returns whether it has results."""
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    path = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(path):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    _state["project_dir"] = path
    _state["project_id"]  = pid
    return jsonify({"status": "active", "id": pid,
                    "has_results": os.path.exists(os.path.join(path, "results.json"))})


def _label_to_key(table: dict, label: str, default: str) -> str:
    """Reverse-lookup a material key by its 'label' (for legacy projects whose
    meta.json stored only the material label, not the key)."""
    for k, v in table.items():
        if v.get("label") == label:
            return k
    return default


def _reconstruct_payload(meta: dict) -> dict:
    """Build a form-loadable payload from a legacy meta.json (no stored payload).

    Carries over what meta has (geom + the handful of run settings); material keys
    are recovered from their labels. Anything absent (resolutions, field modes,
    vehicle…) is simply omitted so the form keeps its current/default values.
    """
    from ema_pipeline import LAMINATES, HAIRPIN_MATS, MAGNETS
    mats = meta.get("materials", {}) or {}
    rng  = (meta.get("rpm_range") or "").replace("U/min", "").strip()
    rpm_from = rpm_to = None
    for sep in ("–", "-", "—"):
        if sep in rng:
            a, b = rng.split(sep, 1)
            try: rpm_from, rpm_to = float(a), float(b)
            except ValueError: pass
            break
    p = {
        "geom":       meta.get("geom", {}),
        "axial_len":  meta.get("axial_len"),
        "load_nm":    meta.get("load_nm"),
        "cooling":    meta.get("cooling"),
        "T_ambient":  meta.get("T_ambient"),
        "rpm_step":   meta.get("rpm_step"),
        "n_frames":   meta.get("frames_per_rpm"),
        "rotor_lam":  _label_to_key(LAMINATES,    mats.get("rotor", ""),   "m270_35a"),
        "stator_lam": _label_to_key(LAMINATES,    mats.get("stator", ""),  "m270_35a"),
        "hairpin_mat":_label_to_key(HAIRPIN_MATS, mats.get("hairpin", ""), "cu_etp"),
        "magnet":     _label_to_key(MAGNETS,      mats.get("magnet", ""),  "ndfeb_n35"),
    }
    if rpm_from is not None: p["rpm_from"] = rpm_from
    if rpm_to   is not None: p["rpm_to"]   = rpm_to
    return {k: v for k, v in p.items() if v is not None}


@app.route("/project/<pid>/template")
def project_template(pid: str):
    """Return a project's input payload so the UI can use it as a template for a
    new run (repopulate the form, then the user tweaks + re-analyses). Prefers the
    Projektakte's stored payload (covers cloned/seeded projects without a meta.json)."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    meta = {}
    meta_path = os.path.join(proj, "meta.json")
    if os.path.exists(meta_path):
        try:
            with open(meta_path) as f:
                meta = json.load(f)
        except Exception:
            meta = {}
    payload = meta.get("payload")
    label = meta.get("label", "")
    reconstructed = "payload" not in meta
    if not payload:
        # Manifest als Quelle (geklonte/gesäte Projekte, Altprojekte)
        try:
            import ema_projekt
            man = ema_projekt.load_or_synthesize(proj, write_back=False)
            payload = (man.get("inputs") or {}).get("payload") or {}
            label = label or man.get("label", "")
        except Exception:
            payload = {}
        if not payload:
            payload = _reconstruct_payload(meta)
    payload = dict(payload)
    payload.pop("cycle_csv", None)
    return jsonify({"payload": payload, "label": label,
                    "reconstructed": reconstructed})


@app.route("/project/<pid>/clone", methods=["POST"])
def project_clone(pid: str):
    """Seed a NEW project directory from the whole Projektakte (Eingaben + Notizen +
    Tags + Projekt-RAG), recording lineage.parent. No heavy results/charts/FCStd are
    copied — the clone is an input seed; the user runs /analyse to populate it.
    Body: {name?, copy_links?}. Returns {id, payload} so the UI can switch + fill."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    src = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(src):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_projekt
    from ema_pipeline import create_project_dir
    body = request.get_json(silent=True) or {}
    sman = ema_projekt.load_or_synthesize(src, write_back=False)
    name = str(body.get("name", "")) or (sman.get("label") or pid) + "_Kopie"

    new_dir, new_id = create_project_dir(PROJECTS_ROOT, name,
                                         origin="clone", parent=pid)
    payload = dict((sman.get("inputs") or {}).get("payload") or {})
    payload.pop("cycle_csv", None)
    # Akte des Klons mit Eingaben/Notizen/Tags/Design seeden
    patch = {"inputs": {"payload": payload},
             "notes": sman.get("notes", ""),
             "tags": list(sman.get("tags", [])),
             "design": dict(sman.get("design", {})),
             "datasheet": sman.get("datasheet", "")}
    if body.get("copy_links"):
        patch["links"] = list(sman.get("links", []))
    ema_projekt.update(new_dir, **patch)
    ema_projekt.append_evolution(new_dir, {"action": "clone", "ref": pid,
                                           "note": f"geklont aus {pid}"})
    # Projekt-RAG mitnehmen (best effort)
    try:
        import shutil
        src_rag = os.path.join(src, "rag")
        if os.path.isdir(src_rag):
            shutil.copytree(src_rag, os.path.join(new_dir, "rag"))
            _sync_rag_inventory(new_id)
    except Exception:
        pass
    # Vermerk im Eltern-Manifest (best effort)
    try:
        ema_projekt.append_evolution(src, {"action": "clone",
                                           "ref": new_id, "note": f"geklont nach {new_id}"})
    except Exception:
        pass
    return jsonify({"status": "cloned", "id": new_id, "label": name,
                    "payload": payload})


@app.route("/project/<pid>/bundle")
def project_bundle(pid: str):
    """Export the WHOLE project directory as a single .emaproj zip (Weitergabe/Backup)."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    src = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(src):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import io, zipfile
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, _dirs, files in os.walk(src):
            for fn in files:
                fp = os.path.join(root, fn)
                zf.write(fp, os.path.relpath(fp, src))
    buf.seek(0)
    return Response(buf.read(), mimetype="application/zip",
                    headers={"Content-Disposition":
                             f'attachment; filename="{pid}.emaproj"'})


@app.route("/import_bundle", methods=["POST"])
def import_bundle():
    """Import a .emaproj (zip) into a NEW project directory. Zip-slip-safe; the new
    manifest gets a fresh id and lineage.origin='import'."""
    import io, zipfile
    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"error": "keine Datei"}), 400
    f = files[0]
    name = os.path.splitext(os.path.basename(f.filename))[0][:48]
    from ema_pipeline import create_project_dir
    new_dir, new_id = create_project_dir(PROJECTS_ROOT, name, origin="import")
    try:
        with zipfile.ZipFile(io.BytesIO(f.read())) as zf:
            for member in zf.namelist():
                # Zip-Slip-Schutz: Zielpfad muss im new_dir bleiben
                dest = os.path.realpath(os.path.join(new_dir, member))
                if not dest.startswith(os.path.realpath(new_dir) + os.sep):
                    continue
                if member.endswith("/"):
                    os.makedirs(dest, exist_ok=True)
                    continue
                os.makedirs(os.path.dirname(dest), exist_ok=True)
                with zf.open(member) as srcf, open(dest, "wb") as out:
                    out.write(srcf.read())
    except zipfile.BadZipFile:
        import shutil
        shutil.rmtree(new_dir, ignore_errors=True)
        return jsonify({"error": "keine gültige .emaproj/Zip-Datei"}), 400
    # Manifest-id auf das neue Verzeichnis ziehen + Import-Abstammung vermerken
    try:
        import ema_projekt
        ema_projekt.update(new_dir, id=new_id,
                           lineage={"parent": None, "origin": "import"})
        ema_projekt.append_evolution(new_dir, {"action": "import",
                                               "note": f"importiert aus {f.filename}"})
    except Exception:
        pass
    return jsonify({"status": "imported", "id": new_id, "label": name})


# ── Report generation (LLM → PDF) ────────────────────────────────────────────

@app.route("/project/<pid>/report", methods=["POST"])
def make_report(pid: str):
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    if _report_state["status"] == "running":
        return jsonify({"error": "Berichtgenerierung läuft bereits"}), 409

    body          = request.get_json(silent=True) or {}
    model         = body.get("model", "ministral-3:14b")
    mode          = body.get("mode", "standard")          # "standard" | "agentic"
    expert_model  = body.get("expert_model", None)        # defaults to model

    _report_state.update({"status": "running", "progress": 0, "log": [],
                          "pdf_path": None, "project_id": pid, "mode": mode})

    def _cb(msg, pct):
        _report_state["log"].append(msg)
        if pct is not None: _report_state["progress"] = int(pct)

    def _run_report():
        try:
            if mode == "agentic":
                from ema_report import generate_report_agentic
                r = generate_report_agentic(
                    proj, model=model, expert_model=expert_model, progress_cb=_cb)
            else:
                from ema_report import generate_report
                r = generate_report(proj, model=model, progress_cb=_cb)
            _report_state["pdf_path"] = r["pdf"]
            _report_state["rag_md_path"] = r.get("rag_md")
            # "Immer nur der letzte Bericht": drop the other-mode PDF so exactly one
            # report stays in the project (and thus a single entry in the gallery).
            _keep = os.path.basename(r["pdf"])
            for _other in ("bericht.pdf", "bericht_agentisch.pdf"):
                if _other != _keep:
                    try: os.remove(os.path.join(proj, _other))
                    except OSError: pass
            _report_state["status"]   = "done"
            _report_state["progress"] = 100
            # Projektakte: Bericht erzeugt → Asset + Status 'berichtet'. Soft.
            try:
                import ema_projekt
                ema_projekt.update(proj, status="berichtet",
                                   assets={"report": os.path.basename(r["pdf"])})
                ema_projekt.append_evolution(proj, {"action": "report",
                                                    "ref": os.path.basename(r["pdf"])})
            except Exception:
                pass
        except Exception as e:
            import traceback
            _report_state["log"].append(
                f"FATAL: {e}\n{traceback.format_exc()[:400]}")
            _report_state["status"] = "error"

    threading.Thread(target=_run_report, daemon=True).start()
    return jsonify({"status": "started", "project": pid,
                    "model": model, "mode": mode}), 202


@app.route("/report/status")
def report_status():
    return jsonify({
        "status":     _report_state["status"],
        "progress":   _report_state["progress"],
        "log":        _report_state["log"][-30:],
        "project_id": _report_state.get("project_id"),
        "has_pdf":    bool(_report_state.get("pdf_path") and
                            os.path.exists(_report_state["pdf_path"])),
        "has_rag_md": bool(_report_state.get("rag_md_path") and
                            os.path.exists(_report_state["rag_md_path"])),
    })


@app.route("/project/<pid>/report/download")
def download_report(pid: str):
    if not _safe_name(pid):
        return "", 403
    mode = request.args.get("mode", "standard")
    if mode == "latest":
        fname = _latest_report(os.path.join(PROJECTS_ROOT, pid)) or "bericht.pdf"
    else:
        fname = "bericht_agentisch.pdf" if mode == "agentic" else "bericht.pdf"
    pdf = os.path.join(PROJECTS_ROOT, pid, fname)
    if not os.path.exists(pdf):
        # fall back to whichever exists
        for fallback in ("bericht_agentisch.pdf", "bericht.pdf"):
            alt = os.path.join(PROJECTS_ROOT, pid, fallback)
            if os.path.exists(alt):
                pdf = alt
                fname = fallback
                break
        else:
            return jsonify({"error": "Bericht noch nicht erzeugt"}), 404
    return send_file(pdf, as_attachment=True, download_name=f"{pid}_{fname}")


@app.route("/project/<pid>/report/rag_md")
def download_report_rag_md(pid: str):
    """Download the value-free RAG markdown (bericht_rag.md) of a project."""
    if not _safe_name(pid):
        return "", 403
    path = os.path.join(PROJECTS_ROOT, pid, "bericht_rag.md")
    if not os.path.exists(path):
        return jsonify({"error": "RAG-Markdown noch nicht erzeugt"}), 404
    return send_file(path, as_attachment=True, download_name=f"{pid}_bericht_rag.md")


@app.route("/project/<pid>/report/rag_md/add", methods=["POST"])
def add_report_rag_md(pid: str):
    """Add the project's value-free RAG markdown to the knowledge base (category 'doku')."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    path = os.path.join(PROJECTS_ROOT, pid, "bericht_rag.md")
    if not os.path.exists(path):
        return jsonify({"error": "RAG-Markdown noch nicht erzeugt"}), 404
    try:
        with open(path, encoding="utf-8") as f:
            text = f.read()
        import ema_rag
        res = ema_rag.add_text(text, title=f"Auslegungsbericht {pid}",
                               category="doku")
        return jsonify({"status": "added", **(res if isinstance(res, dict) else {})})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/compare")
def compare():
    """Compare up to 4 projects. ?ids=A,B,C,D"""
    ids_raw = request.args.get("ids", "")
    ids = [i.strip() for i in ids_raw.split(",") if i.strip() and _safe_name(i.strip())]
    if not ids:
        return jsonify({"error": "Keine Projekt-IDs angegeben"}), 400
    if len(ids) > 10:
        ids = ids[:10]
    from ema_compare import run_compare
    try:
        result = run_compare(PROJECTS_ROOT, ids)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()[:600]}), 500
    return jsonify(result)


@app.route("/project/<pid>/links", methods=["GET", "POST"])
def project_links(pid: str):
    """Persistente Vergleichs-Verknüpfungen eines Projekts.
    GET → aufgelöste Liste (tote Ziele übersprungen).
    POST {other, note?, label?, bidirectional?} → Link hinzufügen."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_projekt
    if request.method == "GET":
        return jsonify({"links": ema_projekt.resolved_links(proj, PROJECTS_ROOT)})

    body = request.get_json(silent=True) or {}
    other = str(body.get("other", "")).strip()
    if not _safe_name(other):
        return jsonify({"error": "ungültiges Zielprojekt"}), 400
    other_dir = os.path.join(PROJECTS_ROOT, other)
    if not os.path.isdir(other_dir):
        return jsonify({"error": "Zielprojekt nicht gefunden"}), 404
    # Label aus dem Ziel-Manifest (Fallback id)
    olabel = body.get("label") or ""
    if not olabel:
        try:
            om = ema_projekt.load_or_synthesize(other_dir, write_back=False)
            olabel = om.get("label") or other
        except Exception:
            olabel = other
    note = str(body.get("note", ""))
    ema_projekt.add_link(proj, other, label=olabel, note=note)
    if body.get("bidirectional"):
        try:
            sm = ema_projekt.load_or_synthesize(proj, write_back=False)
            ema_projekt.add_link(other_dir, pid, label=sm.get("label") or pid, note=note)
        except Exception:
            pass
    return jsonify({"status": "linked",
                    "links": ema_projekt.resolved_links(proj, PROJECTS_ROOT)})


@app.route("/project/<pid>/links/remove", methods=["POST"])
def project_links_remove(pid: str):
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    body = request.get_json(silent=True) or {}
    other = str(body.get("other", "")).strip()
    import ema_projekt
    ema_projekt.remove_link(proj, other)
    return jsonify({"status": "removed",
                    "links": ema_projekt.resolved_links(proj, PROJECTS_ROOT)})


@app.route("/project/<pid>/meta", methods=["POST"])
def project_meta_update(pid: str):
    """Status / Tags / Notizen der Projektakte setzen (Ergebnis-Tab-Panel)."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_projekt
    body = request.get_json(silent=True) or {}
    patch = {}
    if "status" in body and body["status"] in ema_projekt.VALID_STATUS:
        patch["status"] = body["status"]
    if "notes" in body:
        patch["notes"] = str(body["notes"])
    if "tags" in body and isinstance(body["tags"], list):
        patch["tags"] = [str(t)[:40] for t in body["tags"]][:20]
    if not patch:
        return jsonify({"error": "nichts zu ändern"}), 400
    ema_projekt.update(proj, **patch)
    man = ema_projekt.load(proj) or {}
    return jsonify({"status": "saved", "manifest_status": man.get("status"),
                    "tags": man.get("tags", []), "notes": man.get("notes", "")})


@app.route("/project/new", methods=["POST", "OPTIONS"])
def project_new():
    """Leeres Projekt SOFORT anlegen (Projekt-Tab: erst anlegen, dann hineinrechnen).
    Legt Verzeichnis + project.json (status 'neu', origin 'manual') auf Platte an und
    übernimmt optional Name/Tags/Notizen, damit wiss. Dokumente/Organisatorisches
    schon vor dem ersten Lauf hinterlegt werden können. Gibt {id, name} zurück."""
    if request.method == "OPTIONS":
        return ("", 204)
    from ema_pipeline import create_project_dir
    import ema_projekt
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    proj_dir, proj_id = create_project_dir(PROJECTS_ROOT, name, origin="manual")
    patch = {}
    if isinstance(body.get("tags"), list):
        patch["tags"] = [str(t)[:40] for t in body["tags"]][:20]
    if "notes" in body:
        patch["notes"] = str(body["notes"])
    if patch:
        ema_projekt.update(proj_dir, **patch)
    return jsonify({"id": proj_id, "name": name or proj_id})


@app.route("/project/<pid>/manifest")
def project_manifest(pid: str):
    """Volle Projektakte (für das Ergebnis-Tab-Panel: Evolution/Links/Status/Tags)."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_projekt
    man = ema_projekt.load_or_synthesize(proj, write_back=False)
    man["links"] = ema_projekt.resolved_links(proj, PROJECTS_ROOT)
    return jsonify(man)


@app.route("/project/<pid>/delete", methods=["POST"])
def delete_project(pid: str):
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    import shutil
    path = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(path):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    shutil.rmtree(path)
    if _state.get("project_id") == pid:
        _state["project_id"] = None
        _state["project_dir"] = None
    return jsonify({"status": "deleted"})


# ── Field-animation video download ───────────────────────────────────────────

@app.route("/project/<pid>/video/<mode>")
def project_video(pid: str, mode: str):
    # field-animation modes + structural deformation ramp + 3D-Lastprofil (frames_em3d)
    video_subdirs = {**FIELD_SUBDIRS, "struct": "frames_struct", "em3d": "frames_em3d",
                     "oil": "frames_oil"}
    if not _safe_name(pid) or mode not in video_subdirs:
        return jsonify({"error": "ungültig"}), 403
    base = os.path.join(PROJECTS_ROOT, pid) if pid and pid != "current" else _state.get("project_dir")
    if not base or not os.path.isdir(base):
        base = _state.get("project_dir")
    mp4 = os.path.join(base, video_subdirs[mode], "anim.mp4") if base else None
    if not mp4 or not os.path.exists(mp4):
        return jsonify({"error": "Kein Video für diesen Modus"}), 404
    return send_file(mp4, mimetype="video/mp4", as_attachment=True,
                     download_name=f"{pid}_{mode}.mp4")


# ── Comparison report (multiple variants → one PDF) ──────────────────────────

@app.route("/compare/report", methods=["POST"])
def compare_report():
    if _report_state["status"] == "running":
        return jsonify({"error": "Berichtgenerierung läuft bereits"}), 409
    body = request.get_json(force=True) or {}
    ids = [i.strip() for i in body.get("ids", []) if _safe_name(str(i).strip())]
    if len(ids) < 2:
        return jsonify({"error": "Mindestens 2 Projekte wählen"}), 400
    ids = ids[:10]
    model = body.get("model", "ministral-3:14b")
    agentic = bool(body.get("agentic")) or body.get("mode") == "agentic"

    import time
    out_dir = os.path.join(PROJECTS_ROOT, "_comparisons",
                           time.strftime("%Y%m%d_%H%M%S"))
    os.makedirs(out_dir, exist_ok=True)
    _report_state.update({"status": "running", "progress": 0, "log": [],
                          "pdf_path": None, "project_id": os.path.basename(out_dir),
                          "mode": "comparison"})

    def _cb(msg, pct):
        _report_state["log"].append(msg)
        if pct is not None:
            _report_state["progress"] = int(pct)

    def _run_cmp():
        try:
            if agentic:
                from ema_report import generate_comparison_report_agentic
                r = generate_comparison_report_agentic(ids, PROJECTS_ROOT, out_dir,
                                                       model=model, progress_cb=_cb)
            else:
                from ema_report import generate_comparison_report
                r = generate_comparison_report(ids, PROJECTS_ROOT, out_dir,
                                               model=model, progress_cb=_cb)
            _report_state["pdf_path"] = r["pdf"]
            _report_state["status"] = "done"
            _report_state["progress"] = 100
        except Exception as e:
            import traceback
            _report_state["log"].append(f"FATAL: {e}\n{traceback.format_exc()[:400]}")
            _report_state["status"] = "error"

    threading.Thread(target=_run_cmp, daemon=True).start()
    return jsonify({"status": "started", "ids": ids, "model": model}), 202


@app.route("/compare/report/download")
def compare_report_download():
    pdf = _report_state.get("pdf_path")
    if _report_state.get("mode") != "comparison" or not pdf or not os.path.exists(pdf):
        return jsonify({"error": "Kein Vergleichsbericht erzeugt"}), 404
    return send_file(pdf, as_attachment=True, download_name="vergleichsbericht.pdf")


# ── Variant sets (parameter studies) ─────────────────────────────────────────
# A variant set is a JSON file holding up to 10 analysis payloads, so the user
# can store a parameter study and batch-run / compare it.

VARIANTS_ROOT = os.path.join(PROJECTS_ROOT, "_variants")
os.makedirs(VARIANTS_ROOT, exist_ok=True)


@app.route("/variants/list")
def variants_list():
    sets = []
    for fn in sorted(os.listdir(VARIANTS_ROOT)):
        if not fn.endswith(".json"):
            continue
        path = os.path.join(VARIANTS_ROOT, fn)
        try:
            with open(path) as f:
                data = json.load(f)
            sets.append({"name": fn[:-5],
                         "label": data.get("name", fn[:-5]),
                         "created": data.get("created", ""),
                         "n_variants": len(data.get("variants", []))})
        except Exception:
            continue
    return jsonify({"sets": sets})


@app.route("/variants/save", methods=["POST"])
def variants_save():
    body = request.get_json(force=True) or {}
    name = str(body.get("name", "")).strip()
    if not name or not _safe_name(name):
        return jsonify({"error": "ungültiger Set-Name"}), 400
    vset = {
        "schema_version": 1,
        "kind": "ema_variant_set",
        "name": name,
        "created": body.get("created", ""),
        "variants": body.get("variants", [])[:10],
    }
    tmp = os.path.join(VARIANTS_ROOT, f".{name}.tmp")
    final = os.path.join(VARIANTS_ROOT, f"{name}.json")
    with open(tmp, "w") as f:
        json.dump(vset, f, indent=2, ensure_ascii=False)
    os.replace(tmp, final)
    return jsonify({"status": "saved", "name": name,
                    "n_variants": len(vset["variants"])})


@app.route("/variants/load/<name>")
def variants_load(name: str):
    if not _safe_name(name):
        return jsonify({"error": "ungültiger Set-Name"}), 403
    path = os.path.join(VARIANTS_ROOT, f"{name}.json")
    if not os.path.exists(path):
        return jsonify({"error": "Set nicht gefunden"}), 404
    with open(path) as f:
        return jsonify(json.load(f))


@app.route("/variants/delete/<name>", methods=["POST"])
def variants_delete(name: str):
    if not _safe_name(name):
        return jsonify({"error": "ungültiger Set-Name"}), 403
    path = os.path.join(VARIANTS_ROOT, f"{name}.json")
    if os.path.exists(path):
        os.remove(path)
    return jsonify({"status": "deleted"})


# ── Last-Sitzung (serverseitige Sicherung der Eingabe-Maske) ─────────────────
# Spiegelt das clientseitige localStorage-Autosave server-/geräteübergreifend: die
# zuletzt benutzte Formular-Konfiguration (ohne Einmal-CSV) liegt als EINE Datei,
# damit sie auch in einem anderen Browser/auf einem anderen Rechner wieder da ist.
SESSION_PATH = os.path.join(PROJECTS_ROOT, "_session", "last_session.json")
os.makedirs(os.path.dirname(SESSION_PATH), exist_ok=True)


@app.route("/session/save", methods=["POST", "OPTIONS"])
def session_save():
    if request.method == "OPTIONS":
        return "", 200
    body = request.get_json(force=True) or {}
    payload = body.get("payload")
    if not isinstance(payload, dict):
        return jsonify({"error": "kein payload"}), 400
    payload.pop("cycle_csv", None)            # Einmal-Upload nie persistieren
    rec = {"t": int(body.get("t") or (time.time() * 1000)), "payload": payload}
    tmp = SESSION_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(rec, f, ensure_ascii=False)
    os.replace(tmp, SESSION_PATH)
    return jsonify({"status": "saved", "t": rec["t"]})


@app.route("/session/load")
def session_load():
    if not os.path.exists(SESSION_PATH):
        return jsonify({})                    # noch keine Sitzung gesichert
    try:
        with open(SESSION_PATH) as f:
            return jsonify(json.load(f))
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/session/clear", methods=["POST"])
def session_clear():
    if os.path.exists(SESSION_PATH):
        os.remove(SESSION_PATH)
    return jsonify({"status": "cleared"})


# ── Wissensbasis (RAG) — gemeinsame Basis, Kategorien "maschinen" / "doku" ───
@app.route("/rag/list")
def rag_list():
    import ema_rag
    return jsonify({"documents": ema_rag.list_documents(), "stats": ema_rag.stats()})


@app.route("/rag/add", methods=["POST", "OPTIONS"])
def rag_add():
    """Plain-text document. Body: {text, title, category}."""
    if request.method == "OPTIONS":
        return "", 200
    import ema_rag
    d = request.get_json(force=True) or {}
    try:
        res = ema_rag.add_text(d.get("text", ""), d.get("title", ""),
                               d.get("category", "") or "allgemein")
        return jsonify({"status": "added", **res})
    except urllib.error.URLError:
        return jsonify({"error": "Ollama-Embeddings nicht erreichbar (localhost:11434)."}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/rag/upload", methods=["POST"])
def rag_upload():
    """Multipart upload of ONE or MANY files (txt/md/csv/pdf) + form fields category,
    title. With several files the per-file `title` is ignored (filename is used)."""
    import ema_rag
    files = request.files.getlist("file")
    files = [f for f in files if f and f.filename]
    if not files:
        return jsonify({"error": "keine Datei"}), 400
    category = request.form.get("category", "") or "allgemein"
    title    = request.form.get("title", "")
    added, errors = [], []
    for f in files:
        t = title if len(files) == 1 else ""
        try:
            added.append(ema_rag.add_file(f.filename, f.read(), category, title=t or f.filename))
        except urllib.error.URLError:
            return jsonify({"error": "Ollama-Embeddings nicht erreichbar (localhost:11434)."}), 503
        except Exception as e:
            errors.append(f"{f.filename}: {e}")
    if not added:
        return jsonify({"error": "; ".join(errors) or "Upload fehlgeschlagen"}), 400
    # backward-compatible: single upload keeps the flat shape
    if len(files) == 1 and not errors:
        return jsonify({"status": "added", **added[0]})
    return jsonify({"status": "added", "n_added": len(added), "added": added,
                    "errors": errors})


@app.route("/rag/delete/<doc_id>", methods=["POST"])
def rag_delete(doc_id: str):
    import ema_rag
    return jsonify({"status": "deleted" if ema_rag.delete_document(doc_id) else "missing"})


@app.route("/rag/delete", methods=["POST", "OPTIONS"])
def rag_delete_many():
    """Bulk delete. Body: {ids:[…]}."""
    if request.method == "OPTIONS":
        return "", 200
    import ema_rag
    ids = (request.get_json(force=True) or {}).get("ids", [])
    return jsonify({"status": "deleted", "n_deleted": ema_rag.delete_documents(ids)})


def _project_rag_dir(pid: str) -> str:
    return os.path.join(PROJECTS_ROOT, pid, "rag")


def _sync_rag_inventory(pid: str) -> None:
    """Mirror the per-project RAG document list into the Projektakte. Soft."""
    try:
        import ema_rag, ema_projekt
        docs = ema_rag.list_documents(store_dir=_project_rag_dir(pid))
        ema_projekt.update(os.path.join(PROJECTS_ROOT, pid),
                           rag={"docs": docs})
    except Exception:
        pass


@app.route("/project/<pid>/rag", methods=["GET"])
def project_rag_list(pid: str):
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    import ema_rag
    store = _project_rag_dir(pid)
    return jsonify({"documents": ema_rag.list_documents(store_dir=store),
                    "stats": ema_rag.stats(store_dir=store)})


@app.route("/project/<pid>/rag/add", methods=["POST", "OPTIONS"])
def project_rag_add(pid: str):
    """Per-Projekt-Wissensbasis: Text ODER Datei-Upload in <projekt>/rag.
    JSON {text,title,category} oder multipart (file)."""
    if request.method == "OPTIONS":
        return "", 200
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_rag
    store = _project_rag_dir(pid)
    try:
        files = [f for f in request.files.getlist("file") if f and f.filename]
        if files:
            added = []
            for f in files:
                added.append(ema_rag.add_file(f.filename, f.read(),
                             request.form.get("category", "") or "projekt",
                             title=f.filename, store_dir=store))
            _sync_rag_inventory(pid)
            return jsonify({"status": "added", "n_added": len(added), "added": added})
        d = request.get_json(silent=True) or {}
        res = ema_rag.add_text(d.get("text", ""), d.get("title", ""),
                               d.get("category", "") or "projekt", store_dir=store)
        _sync_rag_inventory(pid)
        return jsonify({"status": "added", **res})
    except urllib.error.URLError:
        return jsonify({"error": "Ollama-Embeddings nicht erreichbar (localhost:11434)."}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 400


@app.route("/project/<pid>/rag/<doc_id>/delete", methods=["POST"])
def project_rag_delete(pid: str, doc_id: str):
    if not _safe_name(pid) or not _safe_name(doc_id):
        return jsonify({"error": "ungültiger Name"}), 403
    import ema_rag
    ok = ema_rag.delete_document(doc_id, store_dir=_project_rag_dir(pid))
    _sync_rag_inventory(pid)
    return jsonify({"status": "deleted" if ok else "missing"})


@app.route("/project/<pid>/attachments", methods=["GET", "POST"])
def project_attachments(pid: str):
    """Anhänge-Ordner <projekt>/attachments. GET → Liste. POST (multipart file) legt
    Dateien ab UND speist sie automatisch in die Projekt-RAG (txt/md/csv/pdf)."""
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    proj = os.path.join(PROJECTS_ROOT, pid)
    if not os.path.isdir(proj):
        return jsonify({"error": "Projekt nicht gefunden"}), 404
    import ema_projekt
    adir = os.path.join(proj, "attachments")
    if request.method == "GET":
        return jsonify({"attachments": ema_projekt.scan_attachments(proj)})

    files = [f for f in request.files.getlist("file") if f and f.filename]
    if not files:
        return jsonify({"error": "keine Datei"}), 400
    os.makedirs(adir, exist_ok=True)
    import ema_rag
    saved, rag_added = [], 0
    for f in files:
        name = os.path.basename(f.filename)
        if not _safe_name(name):
            continue
        raw = f.read()
        with open(os.path.join(adir, name), "wb") as out:
            out.write(raw)
        saved.append(name)
        # automatisch in die Projekt-RAG (best effort, Textformate)
        if os.path.splitext(name)[1].lower() in (".txt", ".md", ".csv", ".pdf"):
            try:
                ema_rag.add_file(name, raw, "anhang", title=name,
                                 store_dir=_project_rag_dir(pid))
                rag_added += 1
            except Exception:
                pass
    ema_projekt.update(proj, attachments=ema_projekt.scan_attachments(proj))
    if rag_added:
        _sync_rag_inventory(pid)
    return jsonify({"status": "saved", "saved": saved, "rag_added": rag_added,
                    "attachments": ema_projekt.scan_attachments(proj)})


@app.route("/rag/search")
def rag_search():
    """Debug/preview retrieval: ?q=…&category=…&k=…"""
    import ema_rag
    q = request.args.get("q", "")
    cat = request.args.get("category") or None
    k = int(request.args.get("k", 5))
    if not q:
        return jsonify({"error": "q fehlt"}), 400
    try:
        return jsonify({"hits": ema_rag.search(q, category=cat, k=k)})
    except urllib.error.URLError:
        return jsonify({"error": "Ollama-Embeddings nicht erreichbar."}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── Parameter table schema (für den Spalten-Editor „Parameter-Tabelle") ──────
# Liefert den kuratierten Parametersatz (Labels/Ranges/Enums) aus ema_text2ema.SCHEMA,
# angereichert um lesbare Enum-Labels aus den Material-/Topologie-Tabellen, damit
# das Frontend die Tabelle aufbauen und Dropdown-Zellen befüllen kann.

@app.route("/param_schema")
def param_schema():
    import ema_text2ema as T2E
    from ema_pipeline import LAMINATES, HAIRPIN_MATS, MAGNETS
    try:
        import ema_report as R
        topo_labels = R.TOPOLOGY_LABELS
    except Exception:
        topo_labels = {}
    cool_labels = {"natural": "Selbstkühlung", "forced": "Zwangsluft",
                   "water": "Wasserkühlung", "oil": "Ölkühlung"}

    def _opts(keys, table=None, labelmap=None):
        out = []
        for k in keys:
            if table is not None and k in table:
                out.append({"value": k, "label": table[k].get("label", k)})
            elif labelmap is not None:
                out.append({"value": k, "label": labelmap.get(k, k)})
            else:
                out.append({"value": k, "label": k})
        return out

    enum_opts = {
        "magShape":    _opts(getattr(T2E, "_SHAPE", []), labelmap=topo_labels),
        "rotor_lam":   _opts(getattr(T2E, "_LAM", []),  table=LAMINATES),
        "stator_lam":  _opts(getattr(T2E, "_LAM", []),  table=LAMINATES),
        "hairpin_mat": _opts(getattr(T2E, "_HAIR", []), table=HAIRPIN_MATS),
        "magnet":      _opts(getattr(T2E, "_MAG", []),  table=MAGNETS),
        "cooling":     _opts(getattr(T2E, "_COOL", []), labelmap=cool_labels),
    }
    # geom keys vs. top-level payload keys (für den Frontend-Payload-Bau)
    geom_keys = {"statorOD", "statorID", "rotorOD", "shaftD", "shaftBoreD",
                 "slots", "slotDepth", "p", "magShape", "magAngle", "magDepthRel",
                 "magWidth", "magThick", "magDist", "nAx", "nCirc"}
    params = []
    for key, spec in T2E.SCHEMA.items():
        p = {"key": key, "desc": spec.get("desc", key),
             "kind": spec.get("kind", "num"),
             "in_geom": key in geom_keys}
        if spec.get("kind") == "num":
            p.update({"lo": spec.get("lo"), "hi": spec.get("hi"),
                      "def": spec.get("def"), "int": bool(spec.get("int"))})
        else:
            p["options"] = enum_opts.get(key, _opts(spec.get("opts", [])))
            p["def"] = spec.get("def")
        params.append(p)
    return jsonify({"params": params})


# ── Bewertung „gut/schlecht" + fortlaufendes Trainingsfile ───────────────────

@app.route("/project/<pid>/rating", methods=["GET", "POST"])
def project_rating(pid: str):
    if not _safe_name(pid):
        return jsonify({"error": "ungültiger Projektname"}), 403
    import ema_training
    if request.method == "GET":
        rec = ema_training.get_record(pid)
        if rec is None:
            return jsonify({"label": None, "comment": "", "exists": False})
        # Heuristik-Vorschlag mitliefern (Frontend zeigt ihn, wenn unbewertet)
        proj = os.path.join(PROJECTS_ROOT, pid)
        results, meta = {}, {}
        try:
            with open(os.path.join(proj, "results.json")) as f: results = json.load(f)
            with open(os.path.join(proj, "meta.json")) as f: meta = json.load(f)
        except Exception:
            pass
        return jsonify({"label": rec.get("label"), "comment": rec.get("comment", ""),
                        "exists": True, "label_source": rec.get("label_source"),
                        "auto_label": rec.get("auto_label"),
                        "design_source": rec.get("design_source"),
                        "auto": ema_training.auto_label(results, meta)})

    body = request.get_json(silent=True) or {}
    label = body.get("label")            # "gut" | "schlecht" | null
    comment = str(body.get("comment", ""))
    if label not in ("gut", "schlecht", None):
        return jsonify({"error": "label muss 'gut', 'schlecht' oder null sein"}), 400
    rec = ema_training.set_label(pid, label, comment)
    if rec is None:
        # Zeile fehlt (z.B. Altprojekt) → aus den gespeicherten Dateien neu anlegen
        proj = os.path.join(PROJECTS_ROOT, pid)
        try:
            with open(os.path.join(proj, "results.json")) as f: results = json.load(f)
            with open(os.path.join(proj, "meta.json")) as f: meta = json.load(f)
            rec = ema_training.upsert(pid, meta, results, label=label,
                                      comment=comment, project_dir=proj)
        except Exception as e:
            return jsonify({"error": f"Projektdaten nicht ladbar: {e}"}), 404
    # Projektakte: Bewertung als Evolutionsstufe + Status 'bewertet'. Soft.
    try:
        import ema_projekt
        proj = os.path.join(PROJECTS_ROOT, pid)
        ema_projekt.append_evolution(proj, {
            "action": "rating", "note": comment,
            "ref": label, "key_metrics": {}})
        if label is not None:
            ema_projekt.update(proj, status="bewertet")
    except Exception:
        pass
    return jsonify({"status": "saved", "label": rec.get("label"),
                    "comment": rec.get("comment", "")})


@app.route("/training/design_rejected", methods=["POST"])
def training_design_rejected():
    """Schreibt eine vom Nutzer mit 👎 bewertete (NICHT gerechnete) KI-Variante als
    „schlecht" ins Trainingsfile. Body = {payload, metrics, project_name?}: payload ist
    der volle `_dsnBuildPayload()`-Body (Geometrie/Material/Brief), metrics die schnellen
    FreeCAD/FEM-freien Kennwerte aus der Vorab-Bewertung. Es wird nichts gerechnet."""
    import ema_training, datetime, random
    body = request.get_json(force=True) or {}
    payload = body.get("payload") or {}
    m = body.get("metrics") or {}
    meta = {
        "design_source": "ki",
        "design_brief":  payload.get("design_brief", ""),
        "payload":       payload,
        "materials": {"rotor": payload.get("rotor_lam"), "stator": payload.get("stator_lam"),
                      "hairpin": payload.get("hairpin_mat"), "magnet": payload.get("magnet")},
        "rpm_range":     f"{payload.get('rpm_from')}–{payload.get('rpm_to')} U/min",
        "cooling":       payload.get("cooling"),
        "T_ambient":     payload.get("T_ambient"),
        "label":         body.get("project_name") or "KI-Variante (abgelehnt)",
    }
    # Schnell-Kennwerte (_eval_geom) → summary-Schema fürs Trainingsfile
    summary = {
        "B_gap_T":      m.get("B_gap"),       "Kt_Nm_per_A":  m.get("Kt"),
        "T_maxwell_Nm": m.get("T_maxwell"),   "max_safe_rpm": m.get("max_safe_rpm"),
        "mass_g":       m.get("mass_g"),      "P_total_W":    m.get("P_total"),
        "T_winding_C":  m.get("T_winding"),   "T_magnet_C":   m.get("T_magnet"),
        "cooling":      payload.get("cooling"),
    }
    results = {"summary": {k: v for k, v in summary.items() if v is not None}}
    pid = "ki_abgelehnt_" + datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f") \
          + f"_{random.randint(100, 999)}"
    rec = ema_training.upsert(pid, meta, results, label="schlecht",
                              comment="Vom Nutzer mit 👎 verworfen (nicht gerechnet).")
    return jsonify({"status": "ok", "project_id": pid, "label": rec.get("label")})


@app.route("/training/stats")
def training_stats():
    import ema_training
    return jsonify(ema_training.stats())


@app.route("/training/download")
def training_download():
    import ema_training
    if not os.path.exists(ema_training.SFT_FILE):
        return jsonify({"error": "Noch keine Trainingsdaten vorhanden"}), 404
    return send_file(ema_training.SFT_FILE, as_attachment=True,
                     download_name="ema_dataset_sft.jsonl",
                     mimetype="application/x-ndjson")


@app.route("/training/vlm/export", methods=["POST"])
def training_vlm_export():
    """Regeneriert das VLM-Manifest aus den SFT-Records und liefert die Statistik."""
    import ema_training
    n = ema_training.export_vlm()
    return jsonify({"status": "ok", "n_vlm": n, **ema_training.stats()})


@app.route("/training/vlm/download")
def training_vlm_download():
    import ema_training
    if not os.path.exists(ema_training.VLM_FILE):
        return jsonify({"error": "Noch kein VLM-Manifest vorhanden"}), 404
    return send_file(ema_training.VLM_FILE, as_attachment=True,
                     download_name="ema_dataset_vlm.jsonl",
                     mimetype="application/x-ndjson")


# ── Job-Warteschlange (persistente Server-Jobs, s. ema_jobs) ──────────────────
# Jobs laufen server-seitig weiter, wenn der Browser geschlossen wird; Job-Reihen
# (Varianten/Param-Tabelle/KI-Entwürfe) werden hier statt in Client-JS-Schleifen
# abgearbeitet. Die Executors laufen SYNCHRON im ema_jobs-Worker und schreiben in
# dieselben Modul-State-Dicts wie die Direkt-Routen → die Tab-UIs zeigen weiter
# Live-Fortschritt und die 409-Guards der Routen greifen automatisch.
import ema_jobs


def _exec_analyse(payload):
    _state.update({"status": "running", "progress": 0, "log": [], "results": None})
    for _b in _frames.values():
        _b.clear()
    _run(payload)
    ok = _state["status"] == "done"
    return {"status": "fertig" if ok else "fehler",
            "project_id": _state.get("project_id"),
            "error": None if ok else (_state["log"][-1] if _state["log"] else "Fehler")}


def _em3d_job_outcome(proj_id, payload=None):
    st = _em3d_state["status"]
    status = {"done": "fertig", "aborted": "abgebrochen"}.get(st, "fehler")
    res = _em3d_state.get("result") or {}
    # Job-Lauf AUTOMATISCH im Projekt-Store ablegen, sobald ein Ergebnis vorliegt (auch bei
    # „aborted" mit Teilergebnis) — sonst lässt sich eine als Job gerechnete 3D-Berechnung
    # später NICHT im 3D-Feld-Tab aufrufen (Direktläufe müssen weiter manuell gespeichert
    # werden, ein Job aber schließt den Browser → das Ergebnis wäre sonst nur flüchtig).
    saved_id = None
    if res and status in ("fertig", "abgebrochen"):
        title = (payload or {}).get("_job_title") or "3D-Feld-Job"
        try:
            saved_id, serr = _em3d_store_run(res, title, _em3d_job_config(payload, res))
            if saved_id:
                _em3d_state["log"].append("💾 Job-Lauf gespeichert (%s) → Tab ① »Gespeicherte 3D-Läufe«" % saved_id)
        except Exception as e:
            _em3d_state["log"].append("⚠ Auto-Speichern des 3D-Job-Laufs fehlgeschlagen: %s" % e)
    return {"status": status, "project_id": res.get("project_id") or proj_id,
            "error": _em3d_state.get("error"), "saved_id": saved_id}


def _em3d_job_config(payload, res):
    """Schlanke Config zum Wiederherstellen der 3D-Feld-Formularfelder aus einem Job-Lauf
    (spiegelt die Client-``_e3BuildConfig``-Schlüssel, die ``_e3ApplyConfig`` liest)."""
    p = payload or {}
    return {"skew_deg": p.get("skew_deg"), "coil_currents": p.get("coil_currents"),
            "hex_mesh": p.get("hex_mesh"), "sweep": p.get("sweep"),
            "detail_index": p.get("detail_index"),
            "geom_payload": {k: p.get(k) for k in ("geom", "axial_len", "rpm", "load_nm",
                                                   "excitation") if p.get(k) is not None}}


def _exec_em3d(payload):
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return {"status": "fehler", "error": elmer_runner.INSTALL_HINT}
    proj_dir, proj_id = _em3d_setup(payload)
    _em3d_body(payload, proj_dir, proj_id)
    return _em3d_job_outcome(proj_id, payload)


def _exec_em3d_sweep(payload):
    import elmer_runner
    if not elmer_runner.ELMER_OK:
        return {"status": "fehler", "error": elmer_runner.INSTALL_HINT}
    if not (payload.get("sweep") or []):
        return {"status": "fehler", "error": "Kein Betriebspunkt im Drehzahlband (sweep ist leer)"}
    proj_dir, proj_id = _em3d_setup(payload)
    _em3d_sweep_body(payload, proj_dir, proj_id)
    return _em3d_job_outcome(proj_id, payload)


def _exec_oilspray(payload):
    import blender_runner
    if not blender_runner.BLENDER_OK:
        return {"status": "fehler", "error": blender_runner.INSTALL_HINT}
    proj_dir, proj_id = _oil_setup(payload)
    _oil_body(payload, proj_dir, proj_id)
    st = _oil_state["status"]
    status = {"done": "fertig", "aborted": "abgebrochen"}.get(st, "fehler")
    return {"status": status, "project_id": proj_id, "error": _oil_state.get("error")}


def _exec_param_study(payload):
    """Job-Executor der Parameterstudie (Tab ④ Berechnung). Payload = derselbe Body wie
    ``POST /param_study`` ({payload, param, lo, hi, steps, rpm, field_frames, field_N})."""
    if not (payload.get("payload") and payload.get("param")):
        return {"status": "fehler", "error": "Parameterstudie-Job unvollständig (payload/param fehlt)"}
    _study_state.update({"status": "running", "progress": 0, "log": [],
                         "result": None, "error": None,
                         "payload": payload.get("payload")})
    _param_study_body(payload)
    ok = _study_state["status"] == "done"
    return {"status": "fertig" if ok else "fehler", "project_id": None,
            "error": None if ok else _study_state.get("error")}


def _exec_optimize(payload):
    """Job-Executor der Zielwertoptimierung (Tab ④ Berechnung). Payload = derselbe Spec wie
    ``POST /optimize`` ({base_payload, objective, constraints, free, iterations, batch})."""
    if not (payload.get("free") and payload.get("objective")):
        return {"status": "fehler", "error": "Optimierungs-Job unvollständig (free/objective fehlt)"}
    _opt_state.update({"status": "running", "progress": 0, "log": [],
                       "result": None, "error": None})
    _optimize_body(payload)
    ok = _opt_state["status"] == "done"
    return {"status": "fertig" if ok else "fehler", "project_id": None,
            "error": None if ok else _opt_state.get("error")}


def _jobs_abort_em3d():
    import elmer_runner
    _em3d_abort["v"] = True
    elmer_runner.abort_current()


def _exec_cfd(payload):
    import openfoam_runner
    if not openfoam_runner.OPENFOAM_OK:
        return {"status": "fehler", "error": openfoam_runner.INSTALL_HINT}
    proj_dir, proj_id = _cfd_setup(payload)
    _cfd_body(payload, proj_dir, proj_id)
    st = _cfd_state["status"]
    status = {"done": "fertig", "aborted": "abgebrochen"}.get(st, "fehler")
    return {"status": status, "project_id": proj_id, "error": _cfd_state.get("error")}


def _jobs_abort_cfd():
    import openfoam_runner
    _cfd_abort["v"] = True
    openfoam_runner.abort_current()


def _jobs_abort_oil():
    import blender_runner
    _oil_abort["v"] = True
    blender_runner.abort_current()


# type → State-Dict des laufenden Jobs (für die Live-Anreicherung in GET /jobs)
_JOB_STATES = {"analyse": _state, "em3d": _em3d_state,
               "em3d_sweep": _em3d_state, "oilspray": _oil_state,
               "param_study": _study_state, "optimize": _opt_state,
               "cfd": _cfd_state}


@app.route("/jobs")
def jobs_list():
    out = ema_jobs.list_jobs()
    for j in out["jobs"]:
        if j.get("status") == "läuft":
            st = _JOB_STATES.get(j.get("type"))
            if st:
                j["progress"] = st.get("progress", 0)
                lg = st.get("log") or []
                j["log_line"] = lg[-1] if lg else ""
    return jsonify(out)


@app.route("/jobs/add", methods=["POST", "OPTIONS"])
def jobs_add():
    """Reiht Jobs ein: Body {jobs:[{type,title,payload}]} — type ∈ registrierte
    Executors (analyse/em3d/em3d_sweep/oilspray)."""
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(force=True) or {}
    try:
        ids = ema_jobs.add_jobs(data.get("jobs") or [])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify({"status": "queued", "ids": ids, "n": len(ids)}), 202


@app.route("/jobs/<jid>/cancel", methods=["POST", "OPTIONS"])
def jobs_cancel(jid):
    if request.method == "OPTIONS":
        return "", 200
    try:
        r = ema_jobs.cancel(jid)
    except KeyError:
        return jsonify({"error": "Job nicht gefunden"}), 404
    except ValueError as e:
        return jsonify({"error": str(e)}), 409
    return jsonify({"status": r})


@app.route("/jobs/clear_done", methods=["POST", "OPTIONS"])
def jobs_clear_done():
    if request.method == "OPTIONS":
        return "", 200
    return jsonify({"status": "ok", "removed": ema_jobs.clear_finished()})


@app.route("/jobs/config", methods=["POST", "OPTIONS"])
def jobs_config():
    if request.method == "OPTIONS":
        return "", 200
    data = request.get_json(force=True) or {}
    paused = ema_jobs.set_paused(bool(data.get("paused")))
    return jsonify({"status": "ok", "paused": paused})


ema_jobs.init({
    "analyse":    {"run": _exec_analyse,
                   "busy": lambda: _state["status"] == "running",
                   "abort": None},
    "em3d":       {"run": _exec_em3d,
                   "busy": lambda: _em3d_state["status"] == "running",
                   "abort": _jobs_abort_em3d},
    "em3d_sweep": {"run": _exec_em3d_sweep,
                   "busy": lambda: _em3d_state["status"] == "running",
                   "abort": _jobs_abort_em3d},
    "oilspray":   {"run": _exec_oilspray,
                   "busy": lambda: (_oil_state["status"] == "running"
                                    or _spraytest_state["status"] == "running"),
                   "abort": _jobs_abort_oil},
    "param_study":{"run": _exec_param_study,
                   "busy": lambda: _study_state["status"] == "running",
                   "abort": None},
    "optimize":   {"run": _exec_optimize,
                   "busy": lambda: _opt_state["status"] == "running",
                   "abort": None},
    "cfd":        {"run": _exec_cfd,
                   "busy": lambda: _cfd_state["status"] == "running",
                   "abort": _jobs_abort_cfd},
})


@app.after_request
def cors(r):
    r.headers["Access-Control-Allow-Origin"] = "*"
    r.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return r


if __name__ == "__main__":
    print("=" * 50)
    print("E-Maschinen Analyse-Server")
    print("→  http://localhost:5000")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
