"""Der Werkzeug-Fingerabdruck — ohne Server, ohne Loeser.

Anlass steht im Kopf von ``ema_werkzeugstand``: die Agentenkoepfe haben
Schreibrecht im Repo, und der kuerzeste Weg zu einem Zielwert waere, die Grenze
im Modell zu verschieben. Verhindern laesst sich das unter demselben Benutzer
nicht — verbergen aber schon, und genau das halten diese Pruefungen fest.

Aufruf: ``venv/bin/python test_werkzeugstand.py``
"""

import os
import shutil
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_agent
import ema_arbeit
import ema_werkzeugstand as W

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


print("1. Der Stand ist eine Zahl, und er ist stabil")
s1 = W.stand()
s2 = W.stand()
pruefe(s1["hash"] == s2["hash"] and len(s1["hash"]) == 12,
       f"zweimal gelesen, derselbe Fingerabdruck ({s1['hash']})")
pruefe(not s1["fehlt"],
       "jedes Modul aus PHYSIK liegt wirklich da — eine Liste, die ins Leere "
       "zeigt, waere ein Fingerabdruck ueber Nichts")
pruefe(len(s1["dateien"]) == len(W.PHYSIK),
       f"{len(W.PHYSIK)} Physikmodule gehen ein")
pruefe(W.abweichung(s1, s2) == [],
       "kein Unterschied zu sich selbst")


print("\n2. Eine geaenderte Physikdatei bewegt ihn — eine andere Datei nicht")
# Gemessen wird an einer KOPIE des Verzeichnisses: die echten Module hier
# anzufassen hiesse, waehrend des Laufs genau das zu tun, wogegen dieses Modul
# gebaut ist.
tmp = tempfile.mkdtemp(prefix="werkzeugstand_")
try:
    hier = os.path.dirname(os.path.abspath(__file__))
    for name in W.PHYSIK:
        shutil.copy(os.path.join(hier, name), os.path.join(tmp, name))
    open(os.path.join(tmp, "ema_egal.py"), "w").write("# nicht in PHYSIK\n")

    alt_hier, W._HIER = W._HIER, tmp
    W._datei_cache.clear()
    try:
        a = W.stand()
        # eine Physikdatei
        ziel = os.path.join(tmp, "ema_asm.py")
        with open(ziel, "a") as f:
            f.write("\n# eine Zeile mehr\n")
        W._datei_cache.clear()
        b = W.stand()
        pruefe(a["hash"] != b["hash"],
               "ein Byte in ema_asm.py aendert den Fingerabdruck")
        pruefe(W.abweichung(a, b) == ["ema_asm.py"],
               "und die Abweichung NENNT die Datei — 'irgendetwas ist anders' "
               "waere unbrauchbar, wenn jemand nachsehen soll")

        # eine Datei ausserhalb der Liste
        with open(os.path.join(tmp, "ema_egal.py"), "a") as f:
            f.write("# noch eine\n")
        W._datei_cache.clear()
        c = W.stand()
        pruefe(c["hash"] == b["hash"],
               "eine Datei ausserhalb von PHYSIK bewegt ihn NICHT — sonst waere "
               "der Stand binnen einer Woche Rauschen, das niemand mehr liest")

        # ein fehlendes Modul verschwindet nicht still
        os.remove(ziel)
        W._datei_cache.clear()
        d = W.stand()
        pruefe(d["fehlt"] == ["ema_asm.py"] and "fehlt" in W.kurz(d),
               "ein fehlendes Physikmodul steht als fehlend da")
    finally:
        W._HIER = alt_hier
        W._datei_cache.clear()
finally:
    shutil.rmtree(tmp, ignore_errors=True)


print("\n3. Der Kopf vergleicht gegen den Stand SEINES Starts")
kopf = ema_agent.Kopf.__new__(ema_agent.Kopf)
gesendet = []
kopf._sende = lambda art, **kw: gesendet.append({"art": art, **kw})

# Ohne Startstand darf nichts knallen -- die Pruefungen bauen Koepfe mit
# __new__, und ein AttributeError waere der teuerste Weg, "kein Lauf" zu sagen.
kopf._werkzeug_pruefen()
pruefe(gesendet == [], "ohne laufenden Lauf wird nichts gemeldet")
w = kopf.werkzeug()
pruefe(w["hash"] == W.stand()["hash"] and "grund" in w,
       "und der Zustand ist trotzdem abrufbar (Vergleich gegen git HEAD)")

# Mit einem kuenstlich alten Startstand: die Meldung kommt, und zwar EINMAL.
alt = W.stand()
kopf._werkzeug0 = {**alt, "dateien": {**alt["dateien"], "ema_asm.py": "0" * 12}}
kopf._werkzeug_gemeldet = []
kopf._werkzeug_pruefen()
hin = [e for e in gesendet if e["art"] == "hinweis"]
pruefe(len(hin) == 1 and "ema_asm.py" in hin[0]["text"],
       "eine Aenderung waehrend des Laufs geht als Hinweis IN DEN STROM — "
       "damit steht sie auch im protokoll_*.md des Laufs")
kopf._werkzeug_pruefen()
pruefe(len([e for e in gesendet if e["art"] == "hinweis"]) == 1,
       "und genau einmal je Datei, nicht bei jedem Zugende neu")
pruefe(kopf.werkzeug()["abweichend"] and
       kopf.werkzeug()["geaendert"] == ["ema_asm.py"],
       "die Arbeitsanzeige bekommt dasselbe (Lampe 🔧)")


print("\n4. Der Stand reist mit den Zahlen mit")
import ema_steckbrief
import ema_projekt
pruefe(ema_steckbrief._werkzeugstand().startswith(s1["hash"]),
       "jede abgelegte Rechnung traegt ihn im Kopf (ema_steckbrief.ablegen)")
pruefe(ema_projekt._werkzeugstand() == ema_steckbrief._werkzeugstand(),
       "und jede Evolutionsstufe denselben — zwei Quellen waeren zwei Staende")

quelle = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "server.py"), encoding="utf-8").read()
pruefe('stand["werkzeug"] = k.werkzeug()' in quelle,
       "/agent/arbeit traegt ihn, ohne dass eine Route dafuer erfunden wurde")

for datei, was in (("ema_agent.html", "Schreibtisch"), ("ema_studio.html", "Studio")):
    h = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), datei),
             encoding="utf-8").read()
    pruefe("d.werkzeug" in h and "🔧" in h,
           f"die {was}seite hat die Werkzeuglampe")


print("\n5. Die Regel steht dort, wo der Agent sie liest")
wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for pfad, name in (
        (os.path.join(wurzel, "AGENTS.md"), "AGENTS.md"),
        (os.path.join(wurzel, ".agents", "skills", "cae-orchestrator", "SKILL.md"),
         "SKILL.md")):
    t = open(pfad, encoding="utf-8").read()
    pruefe("BEFUNDE.md" in t and "nicht erreichbar" in t,
           f"{name}: nicht das Werkzeug aendern — und ein begruendetes Nein ist "
           f"eine Antwort")

for kopfname, k in ema_agent.KOEPFE.items():
    t = k.systemzusatz("", {}, 3)
    pruefe("WERKZEUG:" in t and "BEFUNDE.md" in t,
           f"der stehende Auftrag von '{kopfname}' traegt sie")

pruefe(os.path.isfile(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "BEFUNDE.md")),
    "und die Befunddatei, auf die sie verweist, gibt es wirklich")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
