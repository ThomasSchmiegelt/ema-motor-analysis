"""E-Maschinen Analyse-Server: serves ema.html + full analysis pipeline."""

import json, os, threading
from flask import Flask, request, jsonify, send_from_directory, send_file, Response

app = Flask(__name__, static_folder=os.path.dirname(__file__))

WORKSPACE = os.path.join(os.path.dirname(__file__), "workspace")
PROJECTS_ROOT = os.path.expanduser("~/cae_projekte")
os.makedirs(WORKSPACE, exist_ok=True)
os.makedirs(PROJECTS_ROOT, exist_ok=True)

_state  = {"status": "idle", "progress": 0, "log": [],
           "results": None, "project_dir": None, "project_id": None}
_frames = []   # field animation frames (base64 PNG strings)

# Report generation state (separate from analysis pipeline)
_report_state = {"status": "idle", "progress": 0, "log": [],
                 "pdf_path": None, "project_id": None}


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
    _frames.clear()

    t = threading.Thread(target=_run, args=(data,), daemon=True)
    t.start()
    return jsonify({"status": "started"}), 202


def _run(data):
    from ema_pipeline import run_pipeline, create_project_dir
    try:
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


@app.route("/field/<int:n>")
def field_frame(n: int):
    import base64
    if n >= len(_frames):
        return "", 404
    img = base64.b64decode(_frames[n])
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

@app.route("/projects")
def list_projects():
    """List all saved projects."""
    if not os.path.isdir(PROJECTS_ROOT):
        return jsonify({"projects": []})
    projs = []
    for name in sorted(os.listdir(PROJECTS_ROOT), reverse=True):
        path = os.path.join(PROJECTS_ROOT, name)
        if not os.path.isdir(path):
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
        projs.append({
            "id":          name,
            "label":       meta.get("label", name),
            "created":     meta.get("created", ""),
            "rpm_range":   meta.get("rpm_range", ""),
            "has_results": has_results,
            "has_fcstd":   has_fcstd,
            "has_step":    has_step,
        })
    return jsonify({"projects": projs, "current": _state.get("project_id")})


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

    # Load frames index
    frames_dir = os.path.join(path, "frames")
    n_frames = 0
    if os.path.isdir(frames_dir):
        n_frames = len([f for f in os.listdir(frames_dir) if f.endswith(".png")])
    if n_frames > 0:
        # Re-populate _frames from disk as base64
        import base64 as _b64
        _frames.clear()
        for i in range(n_frames):
            fp = os.path.join(frames_dir, f"frame_{i:04d}.png")
            if os.path.exists(fp):
                with open(fp, "rb") as f:
                    _frames.append(_b64.b64encode(f.read()).decode())

    _state["results"]     = results
    _state["project_dir"] = path
    _state["project_id"]  = pid
    _state["status"]      = "done"
    return jsonify({"status": "loaded", "id": pid,
                    "n_frames": len(_frames),
                    "summary": results.get("summary", {})})


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
            _report_state["status"]   = "done"
            _report_state["progress"] = 100
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
    })


@app.route("/project/<pid>/report/download")
def download_report(pid: str):
    if not _safe_name(pid):
        return "", 403
    mode = request.args.get("mode", "standard")
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


@app.route("/compare")
def compare():
    """Compare up to 4 projects. ?ids=A,B,C,D"""
    ids_raw = request.args.get("ids", "")
    ids = [i.strip() for i in ids_raw.split(",") if i.strip() and _safe_name(i.strip())]
    if not ids:
        return jsonify({"error": "Keine Projekt-IDs angegeben"}), 400
    if len(ids) > 4:
        ids = ids[:4]
    from ema_compare import run_compare
    try:
        result = run_compare(PROJECTS_ROOT, ids)
    except Exception as e:
        import traceback
        return jsonify({"error": str(e), "trace": traceback.format_exc()[:600]}), 500
    return jsonify(result)


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
