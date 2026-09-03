"""Tests der persistenten Job-Warteschlange (ema_jobs) — schnell, ohne Flask/Solver.

Fake-Executors (ms-schnell) prüfen: Reihenfolge der Abarbeitung, Persistenz +
Server-Neustart-Verhalten (läuft → abgebrochen), Abbrechen wartender Jobs, Pause,
clear_finished, Busy-Warten und unbekannte Typen.

    venv/bin/python test_jobs.py    (oder pytest)
"""

import json
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ema_jobs  # noqa: E402


def _fresh(executors):
    """ema_jobs auf ein frisches Temp-Verzeichnis umbiegen + neu initialisieren."""
    d = tempfile.mkdtemp(prefix="ema_jobs_test_")
    ema_jobs.JOBS_DIR = d
    ema_jobs.QUEUE_FILE = os.path.join(d, "queue.json")
    ema_jobs.init(executors)
    return d


def _wait_all_finished(timeout=10.0):
    t0 = time.time()
    while time.time() - t0 < timeout:
        jobs = ema_jobs.list_jobs()["jobs"]
        if jobs and all(j["status"] in ("fertig", "fehler", "abgebrochen") for j in jobs):
            return jobs
        time.sleep(0.02)
    raise AssertionError("Jobs nicht rechtzeitig fertig: %s"
                         % [(j["title"], j["status"]) for j in ema_jobs.list_jobs()["jobs"]])


def test_sequential_order_and_outcome():
    ran = []
    def run(p):
        ran.append(p["n"])
        if p.get("fail"):
            return {"status": "fehler", "error": "kaputt"}
        return {"status": "fertig", "project_id": "proj_%d" % p["n"]}
    _fresh({"fake": {"run": run, "busy": lambda: False, "abort": None}})
    ids = ema_jobs.add_jobs([{"type": "fake", "title": "a", "payload": {"n": 1}},
                             {"type": "fake", "title": "b", "payload": {"n": 2, "fail": True}},
                             {"type": "fake", "title": "c", "payload": {"n": 3}}])
    assert len(ids) == 3
    jobs = _wait_all_finished()
    assert ran == [1, 2, 3], ran                       # Reihenfolge
    by_title = {j["title"]: j for j in jobs}
    assert by_title["a"]["status"] == "fertig" and by_title["a"]["project_id"] == "proj_1"
    assert by_title["b"]["status"] == "fehler" and by_title["b"]["error"] == "kaputt"
    assert by_title["c"]["status"] == "fertig"
    assert "payload" not in jobs[0]                    # list_jobs liefert Payloads nicht mit
    print("  ✓ sequenzielle Abarbeitung + Outcome")


def test_persistence_and_restart():
    _fresh({"fake": {"run": lambda p: {"status": "fertig"},
                     "busy": lambda: False, "abort": None}})
    # Absturz simulieren: Store mit einem 'läuft'- und einem 'wartet'-Job hinschreiben …
    crashed = {"config": {"paused": True},
               "jobs": [{"id": "aa", "type": "fake", "title": "alt", "payload": {},
                         "status": "läuft", "created": 1.0, "started": 2.0,
                         "finished": None, "project_id": None, "error": None},
                        {"id": "bb", "type": "fake", "title": "neu", "payload": {},
                         "status": "wartet", "created": 3.0, "started": None,
                         "finished": None, "project_id": None, "error": None}]}
    with open(ema_jobs.QUEUE_FILE, "w") as f:
        json.dump(crashed, f)
    # … und neu initialisieren (Server-Neustart): läuft → abgebrochen, wartet bleibt.
    ema_jobs.init({"fake": {"run": lambda p: {"status": "fertig"},
                            "busy": lambda: False, "abort": None}})
    out = ema_jobs.list_jobs()
    assert out["paused"] is True
    by_id = {j["id"]: j for j in out["jobs"]}
    assert by_id["aa"]["status"] == "abgebrochen"
    assert "Neustart" in (by_id["aa"]["error"] or "")
    assert by_id["bb"]["status"] == "wartet"           # läuft NICHT von selbst an
    # Der Neustart HÄLT die Schlange an, statt den nächsten Auftrag zu starten:
    # ein abgebrochener Lauf hat keinen Zwischenstand, er finge von vorn an — und
    # ein Neustart hat meistens einen Grund, der gegen genau diese Reihenfolge
    # spricht. Beobachtet als „der Server startet alte Läufe immer wieder neu".
    assert out["halt"] is True
    assert "alt" in out["halt_grund"] and "neu" in out["halt_grund"]
    # Persistenz auf Platte:
    with open(ema_jobs.QUEUE_FILE) as f:
        disk = json.load(f)
    assert disk["jobs"][0]["status"] == "abgebrochen"
    assert disk["config"]["halt"] is True
    # Erst die Entscheidung setzt die Schlange wieder in Gang (Pause zusätzlich lösen).
    ema_jobs.set_paused(False)
    ema_jobs.entscheiden("weiter")
    jobs = _wait_all_finished()
    assert {j["id"]: j["status"] for j in jobs}["bb"] == "fertig"
    print("  ✓ Persistenz + Server-Neustart (läuft→abgebrochen, Schlange hält an, "
          "läuft erst auf Zuruf weiter)")


def test_cancel_waiting_and_pause():
    gate = {"open": False}
    def slow(p):
        while not gate["open"]:
            time.sleep(0.01)
        return {"status": "fertig"}
    _fresh({"fake": {"run": slow, "busy": lambda: False, "abort": None}})
    ema_jobs.set_paused(True)
    ids = ema_jobs.add_jobs([{"type": "fake", "title": "x", "payload": {}},
                             {"type": "fake", "title": "y", "payload": {}}])
    time.sleep(0.15)
    assert all(j["status"] == "wartet" for j in ema_jobs.list_jobs()["jobs"])  # Pause hält
    assert ema_jobs.cancel(ids[1]) == "abgebrochen"    # wartenden abbrechen
    try:
        ema_jobs.cancel("gibtsnicht")
        raise AssertionError("KeyError erwartet")
    except KeyError:
        pass
    gate["open"] = True
    ema_jobs.set_paused(False)
    jobs = _wait_all_finished()
    st = {j["title"]: j["status"] for j in jobs}
    assert st == {"x": "fertig", "y": "abgebrochen"}, st
    # abgeschlossene nicht mehr abbrechbar:
    try:
        ema_jobs.cancel(ids[0])
        raise AssertionError("ValueError erwartet")
    except ValueError:
        pass
    assert ema_jobs.clear_finished() == 2
    assert ema_jobs.list_jobs()["jobs"] == []
    print("  ✓ Pause + Abbrechen wartender Jobs + clear_finished")


def test_busy_wait_and_unknown_type():
    busy = {"v": True}
    ran = []
    _fresh({"fake": {"run": lambda p: ran.append(1) or {"status": "fertig"},
                     "busy": lambda: busy["v"], "abort": None}})
    ema_jobs.add_jobs([{"type": "fake", "title": "w", "payload": {}}])
    time.sleep(0.3)
    assert ran == []                                   # Executor belegt ⇒ Job wartet
    busy["v"] = False
    old_poll = ema_jobs._BUSY_POLL_S
    _wait_all_finished(timeout=2 * old_poll + 5)
    assert ran == [1]
    try:
        ema_jobs.add_jobs([{"type": "gibtsnicht", "title": "?", "payload": {}}])
        raise AssertionError("ValueError erwartet")
    except ValueError:
        pass
    print("  ✓ Busy-Warten + unbekannter Typ")


if __name__ == "__main__":
    ema_jobs._BUSY_POLL_S = 0.05                       # Tests nicht ausbremsen
    test_sequential_order_and_outcome()
    test_persistence_and_restart()
    test_cancel_waiting_and_pause()
    test_busy_wait_and_unknown_type()
    print("ALLE JOB-QUEUE-TESTS BESTANDEN ✅")
