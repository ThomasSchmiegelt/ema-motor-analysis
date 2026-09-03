"""Nach einem Serverstart laeuft die Warteschlange NICHT von selbst weiter.

Der Anlass ist eine Beobachtung am laufenden System: „der Server startet ab und zu
alte Laeufe, die nicht abgeschlossen sind, immer wieder neu". Das stimmte —
``init`` markierte den unterbrochenen Auftrag als abgebrochen und liess den Worker
sofort den naechsten wartenden nehmen. Beim unterbrochenen selbst gibt es keinen
Zwischenstand, ein Wiederholen faengt also von vorn an; und ein Neustart hat
meistens einen Grund, der gegen genau diese Reihenfolge spricht.
"""

import io
import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_jobs

_ok = _bad = 0


def pruefe(b, t):
    global _ok, _bad
    if b:
        _ok += 1; print(f"  ✓ {t}")
    else:
        _bad += 1; print(f"  ✗ {t}")


_tmp = tempfile.mkdtemp(prefix="jobs_halt_")
ema_jobs.JOBS_DIR = _tmp
ema_jobs.QUEUE_FILE = os.path.join(_tmp, "queue.json")
_gelaufen = []


def _executor(payload):
    _gelaufen.append(payload.get("marke"))
    return {"status": "fertig"}


def _schreibe(jobs, config=None):
    with open(ema_jobs.QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump({"config": config or {}, "jobs": jobs}, f)


def _job(jid, status, titel, marke=None):
    return {"id": jid, "type": "analyse", "title": titel,
            "payload": {"marke": marke or jid}, "status": status,
            "created": time.time(), "started": None, "finished": None,
            "project_id": None, "error": None}


print("1. Ein Neustart mit offenen Auftraegen haelt an, statt weiterzulaufen")
_schreibe([_job("a", "läuft", "Variante A"), _job("b", "wartet", "Variante B")])
ema_jobs.init({"analyse": {"run": _executor, "busy": lambda: False, "abort": lambda: None}})
time.sleep(0.6)
z = ema_jobs.list_jobs()
pruefe(z["halt"], "die Warteschlange steht auf Halt")
pruefe("Variante A" in z["halt_grund"] and "Variante B" in z["halt_grund"],
       f"und sagt, worum es geht: {z['halt_grund'][:90]}…")
pruefe(not _gelaufen, f"NICHTS ist von selbst angelaufen ({_gelaufen})")
pruefe([j["status"] for j in z["jobs"]] == ["abgebrochen", "wartet"],
       "der unterbrochene ist abgebrochen, der wartende wartet weiter")

print("\n2. Entscheiden: fortsetzen")
ema_jobs.entscheiden("weiter")
time.sleep(0.8)
pruefe(_gelaufen == ["b"], f"erst auf Zuruf laeuft der wartende an ({_gelaufen})")
pruefe(not ema_jobs.list_jobs()["halt"], "der Halt ist aufgeloest")

print("\n3. Entscheiden: verwerfen")
_gelaufen.clear()
_schreibe([_job("c", "wartet", "C"), _job("d", "wartet", "D")])
ema_jobs._store = ema_jobs._load()
ema_jobs.init({"analyse": {"run": _executor, "busy": lambda: False, "abort": lambda: None}})
time.sleep(0.5)
a = ema_jobs.entscheiden("verwerfen")
time.sleep(0.5)
pruefe(a["verworfen"] == 2 and not _gelaufen,
       f"beide wartenden sind weg, keiner ist gelaufen ({_gelaufen})")
pruefe(all(j["status"] == "abgebrochen" for j in ema_jobs.list_jobs()["jobs"]),
       "und stehen als abgebrochen mit Begruendung da")

print("\n4. Umsortieren: erst das hier")
_gelaufen.clear()
_schreibe([_job("e", "wartet", "E"), _job("f", "wartet", "F")],
          {"halt": True, "halt_grund": "Test"})
ema_jobs._store = ema_jobs._load()
r = ema_jobs.vorziehen("f")
pruefe(r["ok"] and [j["id"] for j in ema_jobs.list_jobs()["jobs"]] == ["f", "e"],
       "der vorgezogene steht vorn")
pruefe(not ema_jobs.vorziehen("gibtsnicht")["ok"], "ein unbekannter Auftrag wird abgewiesen")
ema_jobs.entscheiden("weiter")
time.sleep(1.2)
pruefe(_gelaufen[:1] == ["f"], f"und laeuft zuerst ({_gelaufen})")

print("\n5. Wiederholen nur auf Zuruf")
_gelaufen.clear()
_schreibe([_job("g", "abgebrochen", "G")], {"halt": False})
ema_jobs._store = ema_jobs._load()
time.sleep(0.4)
pruefe(not _gelaufen, "ein abgebrochener Auftrag laeuft NICHT von selbst wieder an")
r = ema_jobs.wiederholen("g")
time.sleep(0.9)
pruefe(r["ok"] and r["id"] != "g", "erst 'wiederholen' reiht ihn als NEUEN Auftrag ein")
pruefe(_gelaufen == ["g"], f"der dann von vorn laeuft ({_gelaufen})")

print("\n6. Ohne offene Auftraege aendert sich nichts")
_schreibe([_job("h", "fertig", "H")])
ema_jobs._store = ema_jobs._load()
ema_jobs.init({"analyse": {"run": _executor, "busy": lambda: False, "abort": lambda: None}})
pruefe(not ema_jobs.list_jobs()["halt"],
       "eine leere oder abgearbeitete Schlange haelt nicht an")

shutil.rmtree(_tmp, ignore_errors=True)
print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
