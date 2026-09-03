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
    verwaiste 'läuft'-Jobs als abgebrochen markieren — und bei offenen Aufträgen
    die Warteschlange ANHALTEN statt sie weiterlaufen zu lassen.

    Warum angehalten wird
    ---------------------

    Vorher startete der Worker nach jedem Serverstart sofort den ersten wartenden
    Auftrag. Für den Absturz mitten in einer Zehnerreihe ist das richtig gedacht,
    aus der Sicht des Menschen aber falsch: Ein Neustart hat meistens einen Grund
    (etwas war kaputt, etwas wurde geändert, es sollte etwas anderes zuerst
    laufen), und die Warteschlange fing stattdessen unbemerkt wieder an — beim
    unterbrochenen Auftrag von vorn, weil ein abgebrochener Lauf keinen
    Zwischenstand hat. Von aussen sieht das aus, als starte der Server alte Läufe
    von selbst neu; genau das tat er auch.

    Jetzt gilt: gab es beim Start offene Aufträge, wird ``halt`` gesetzt und der
    Grund dazu. Es läuft nichts, bis jemand entscheidet — fortsetzen, umsortieren
    oder verwerfen. Ohne offene Aufträge ändert sich nichts.
    """
    global _store, _executors
    with _lock:
        _executors = dict(executors or {})
        _store = _load()
        unterbrochen = []
        for j in _store["jobs"]:
            if j.get("status") == ST_RUN:
                j["status"] = ST_ABORT
                j["error"] = "Server-Neustart während der Ausführung"
                j["finished"] = time.time()
                unterbrochen.append(j["title"])
        wartend = [j for j in _store["jobs"] if j.get("status") == ST_WAIT]
        if wartend or unterbrochen:
            teile = []
            if unterbrochen:
                teile.append(f"{len(unterbrochen)} Auftrag/Aufträge wurden vom Neustart "
                             f"unterbrochen ({', '.join(unterbrochen[:3])})")
            if wartend:
                teile.append(f"{len(wartend)} warten noch "
                             f"({', '.join(j['title'] for j in wartend[:3])})")
            _store["config"]["halt"] = True
            _store["config"]["halt_grund"] = (
                "Nach dem Serverstart angehalten: " + " · ".join(teile)
                + ". Nichts läuft, bis du entscheidest: fortsetzen, umsortieren "
                  "oder verwerfen.")
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
        if _store["config"].get("paused") or _store["config"].get("halt"):
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
            payload = job.get("payload") or {}
            # Job-Titel für die Executors mitgeben (z. B. als Speichername eines 3D-Laufs),
            # ohne die run(payload)-Signatur zu ändern.
            payload.setdefault("_job_title", job.get("title"))
            out = ex["run"](payload) or {}
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
        return {"paused": bool(_store["config"].get("paused")),
                "halt": bool(_store["config"].get("halt")),
                "halt_grund": _store["config"].get("halt_grund", ""),
                "jobs": jobs}


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


def entscheiden(was: str) -> dict:
    """Den Halt nach einem Serverstart aufloesen — bewusst, nicht nebenbei.

    ``weiter``    die wartenden Auftraege laufen in der abgelegten Reihenfolge.
    ``verwerfen`` alle wartenden werden abgebrochen; nichts laeuft an.
    """
    if was not in ("weiter", "verwerfen"):
        raise ValueError(f"unbekannte Entscheidung: {was!r}")
    with _lock:
        n = 0
        if was == "verwerfen":
            for j in _store["jobs"]:
                if j.get("status") == ST_WAIT:
                    j["status"], j["finished"] = ST_ABORT, time.time()
                    j["error"] = "nach Serverstart verworfen"
                    n += 1
        _store["config"]["halt"] = False
        _store["config"]["halt_grund"] = ""
        _save()
    _ensure_worker()
    return {"ok": True, "entscheidung": was, "verworfen": n}


def vorziehen(jid: str) -> dict:
    """Einen wartenden Auftrag an den Anfang der Warteschlange stellen.

    Die Reihenfolge IST die Liste — der Worker nimmt den ersten wartenden. Damit
    ist Umsortieren die dritte Antwort auf die Frage nach einem Neustart: nicht
    nur „weiter oder weg", sondern „erst das hier".
    """
    with _lock:
        job = next((j for j in _store["jobs"] if j.get("id") == jid), None)
        if not job:
            return {"ok": False, "grund": "unbekannter Auftrag"}
        if job.get("status") != ST_WAIT:
            return {"ok": False, "grund": f"nur wartende Auftraege ({job['status']})"}
        erste = next((i for i, j in enumerate(_store["jobs"])
                      if j.get("status") == ST_WAIT), None)
        _store["jobs"].remove(job)
        _store["jobs"].insert(erste if erste is not None else 0, job)
        _save()
    return {"ok": True, "id": jid}


def wiederholen(jid: str) -> dict:
    """Einen abgebrochenen Auftrag erneut einreihen (als Kopie am Ende).

    Ausdruecklich auf Zuruf: ein vom Neustart unterbrochener Lauf hat keinen
    Zwischenstand, er finge von vorn an — das soll ein Mensch entscheiden.
    """
    with _lock:
        job = next((j for j in _store["jobs"] if j.get("id") == jid), None)
        if not job:
            return {"ok": False, "grund": "unbekannter Auftrag"}
        if job.get("status") not in _FINISHED:
            return {"ok": False, "grund": "laeuft oder wartet bereits"}
        neu = dict(job, id=uuid.uuid4().hex[:10], status=ST_WAIT,
                   created=time.time(), started=None, finished=None,
                   error=None, project_id=None)
        _store["jobs"].append(neu)
        _save()
    _ensure_worker()
    return {"ok": True, "id": neu["id"]}


def set_paused(paused):
    with _lock:
        _store["config"]["paused"] = bool(paused)
        _save()
    if not paused:
        _ensure_worker()
    return bool(paused)
