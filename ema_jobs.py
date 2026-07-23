"""Persistente Server-Job-Warteschlange.

Berechnungsjobs (analyse / em3d / em3d_sweep / oilspray) werden server-seitig in eine
Warteschlange gestellt und von EINEM Worker-Thread sequenziell abgearbeitet — sie laufen
damit auch weiter, wenn der Browser geschlossen wird, und eine ganze Job-Reihe (Varianten,
Parameter-Tabelle, KI-Entwürfe) überlebt das Zumachen des Tabs. Der Stand liegt persistent
in ``~/cae_projekte/_jobs/queue.json`` (atomar via os.replace), sodass die UI nach dem
Wieder-Öffnen (und der Worker nach einem Server-Neustart) dort weitermachen kann.

Executors werden von ``server.py`` über :func:`init` registriert:
``{type: {"run": fn(payload)->outcome, "busy": fn()->bool, "abort": fn|None}}``.
``run`` läuft SYNCHRON im Worker-Thread und schreibt selbst in den jeweiligen
Modul-State-Dict des Servers (``_state``/``_em3d_state``/``_oil_state``) — die
bestehenden Tab-UIs zeigen dadurch unverändert Live-Fortschritt. Outcome =
``{"status": "fertig"|"fehler"|"abgebrochen", "project_id": str|None, "error": str|None}``.
"""

import json
import os
import threading
import time
import uuid

JOBS_DIR   = os.path.join(os.path.expanduser("~/cae_projekte"), "_jobs")
QUEUE_FILE = os.path.join(JOBS_DIR, "queue.json")

MAX_OPEN_JOBS = 50          # Cap offener (wartender) Jobs
_BUSY_POLL_S  = 2.0         # Wartetakt, wenn der Executor direkt (ohne Queue) belegt ist

# Job-Status (deutsch, wie die übrige UI)
ST_WAIT, ST_RUN, ST_DONE, ST_ERR, ST_ABORT = "wartet", "läuft", "fertig", "fehler", "abgebrochen"
_FINISHED = (ST_DONE, ST_ERR, ST_ABORT)

_lock = threading.RLock()
_store = None               # {"config": {"paused": bool}, "jobs": [job, ...]}
_executors = {}             # type -> {"run","busy","abort"}
_worker = None              # der eine Worker-Thread (oder None)
_wake = threading.Event()   # weckt den Worker (neuer Job / Pause aufgehoben)


def _load():
    try:
        with open(QUEUE_FILE) as f:
            d = json.load(f)
        d.setdefault("config", {}).setdefault("paused", False)
        d.setdefault("jobs", [])
        return d
    except Exception:
        return {"config": {"paused": False}, "jobs": []}


def _save():
    """Persistiert den Store atomar (Muster ema_projekt). Immer unter _lock aufrufen."""
    try:
        os.makedirs(JOBS_DIR, exist_ok=True)
        tmp = QUEUE_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(_store, f, ensure_ascii=False, indent=1)
        os.replace(tmp, QUEUE_FILE)
    except Exception:
        pass                                          # soft-fail wie ema_projekt


def init(executors):
    """Von server.py beim Import aufgerufen: Executors registrieren, Store laden,
    verwaiste 'läuft'-Jobs (Server-Neustart/-Absturz) als abgebrochen markieren und —
    falls wartende Jobs existieren und nicht pausiert ist — den Worker starten."""
    global _store, _executors
    with _lock:
        _executors = dict(executors or {})
        _store = _load()
        for j in _store["jobs"]:
            if j.get("status") == ST_RUN:
                j["status"] = ST_ABORT
                j["error"] = "Server-Neustart während der Ausführung"
                j["finished"] = time.time()
        _save()
    _ensure_worker()


def _ensure_worker():
    """Startet den Worker-Thread, wenn er nicht läuft (lazy, daemon)."""
    global _worker
    with _lock:
        if _worker is not None and _worker.is_alive():
            _wake.set()
            return
        _worker = threading.Thread(target=_worker_loop, daemon=True, name="ema-jobs")
        _worker.start()


def _next_waiting():
    with _lock:
        if _store["config"].get("paused"):
            return None
        for j in _store["jobs"]:
            if j.get("status") == ST_WAIT:
                return j
    return None


def _worker_loop():
    """Nimmt sequenziell den jeweils ersten wartenden Job. Ist der Executor gerade direkt
    (ohne Queue) belegt, wird gewartet statt parallel zu starten — die Rechenpfade
    (FreeCAD/CalculiX/Elmer/Blender) vertragen nur einen Lauf gleichzeitig."""
    while True:
        job = _next_waiting()
        if job is None:
            _wake.clear()
            _wake.wait(timeout=30.0)
            continue
        ex = _executors.get(job.get("type"))
        if ex is None:                                # unbekannter Typ (Altbestand)
            with _lock:
                job["status"], job["error"] = ST_ERR, "unbekannter Job-Typ"
                job["finished"] = time.time()
                _save()
            continue
        try:
            while ex["busy"]():
                time.sleep(_BUSY_POLL_S)
        except Exception:
            pass
        with _lock:
            if job.get("status") != ST_WAIT:          # zwischenzeitlich abgebrochen
                continue
            job["status"], job["started"] = ST_RUN, time.time()
            _save()
        try:
            out = ex["run"](job.get("payload") or {}) or {}
            status = out.get("status") or ST_DONE
        except Exception as e:                        # Executor selbst geworfen
            out, status = {"error": str(e)}, ST_ERR
        with _lock:
            job["status"] = status if status in _FINISHED else ST_DONE
            job["project_id"] = out.get("project_id") or job.get("project_id")
            job["error"] = out.get("error")
            job["finished"] = time.time()
            _save()


# ── öffentliche API (von den /jobs-Routen genutzt) ────────────────────────────

def add_jobs(items):
    """Reiht Jobs ein: items = [{type, title, payload}]. Liefert die neuen IDs.
    Wirft ValueError bei unbekanntem Typ oder vollem Queue-Cap."""
    with _lock:
        n_open = sum(1 for j in _store["jobs"] if j.get("status") in (ST_WAIT, ST_RUN))
        ids = []
        jobs = []
        for it in (items or []):
            t = (it.get("type") or "").strip()
            if t not in _executors:
                raise ValueError(f"unbekannter Job-Typ: {t!r}")
            if n_open + len(jobs) >= MAX_OPEN_JOBS:
                raise ValueError(f"Warteschlange voll (max {MAX_OPEN_JOBS} offene Jobs)")
            jid = uuid.uuid4().hex[:10]
            jobs.append({"id": jid, "type": t,
                         "title": (it.get("title") or t)[:120],
                         "payload": it.get("payload") or {},
                         "status": ST_WAIT, "created": time.time(),
                         "started": None, "finished": None,
                         "project_id": None, "error": None})
            ids.append(jid)
        _store["jobs"].extend(jobs)
        _save()
    if ids:
        _ensure_worker()
    return ids


def list_jobs():
    """Alle Jobs (ohne die Payloads — die können groß sein) + paused-Flag."""
    with _lock:
        jobs = [{k: v for k, v in j.items() if k != "payload"} for j in _store["jobs"]]
        return {"paused": bool(_store["config"].get("paused")), "jobs": jobs}


def get_job(jid):
    with _lock:
        for j in _store["jobs"]:
            if j.get("id") == jid:
                return j
    return None


def cancel(jid):
    """Wartenden Job abbrechen (→ abgebrochen). Laufenden Job: Executor-abort()
    falls vorhanden (der Worker markiert ihn dann über das run()-Outcome), sonst
    ValueError. Unbekannte ID → KeyError."""
    with _lock:
        job = next((j for j in _store["jobs"] if j.get("id") == jid), None)
        if job is None:
            raise KeyError(jid)
        if job["status"] == ST_WAIT:
            job["status"], job["finished"] = ST_ABORT, time.time()
            _save()
            return "abgebrochen"
        if job["status"] != ST_RUN:
            raise ValueError("Job ist bereits abgeschlossen")
        ab = (_executors.get(job["type"]) or {}).get("abort")
        if ab is None:
            raise ValueError("dieser Job-Typ ist nicht abbrechbar (läuft zu Ende)")
    ab()                                              # außerhalb des Locks (kann dauern)
    return "abbruch angefordert"


def clear_finished():
    with _lock:
        before = len(_store["jobs"])
        _store["jobs"] = [j for j in _store["jobs"] if j.get("status") not in _FINISHED]
        _save()
        return before - len(_store["jobs"])


def set_paused(paused):
    with _lock:
        _store["config"]["paused"] = bool(paused)
        _save()
    if not paused:
        _ensure_worker()
    return bool(paused)
