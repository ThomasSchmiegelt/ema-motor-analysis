"""Die aufgeteilte Oberflaeche — haelt sie zusammen? (ohne Server, ohne Loeser)

Am 16.10.2026 sind die beiden ``<script>``-Bloecke aus ``ema.html`` (zusammen
11.568 Zeilen) nach ``oberflaeche/*.js`` gewandert. Das war eine reine
Verschiebung, und genau deshalb braucht es diese Pruefungen: eine Verschiebung
hat zwei Arten, still falsch zu werden.

**Die erste ist die Reihenfolge.** In EINEM Skript darf oben stehen, was unten
definiert ist — Funktionsdeklarationen werden innerhalb eines Skripts
hochgezogen. Ueber mehrere Dateien gilt das nicht mehr. Gemessen als
Gegenprobe: ``verdrahtung.js`` an den Anfang gezogen ergibt im Browser
``Uncaught ReferenceError: startAnalysis is not defined @ verdrahtung.js:13``
— und zwar genau EINmal, beim Laden, wo es niemandem auffaellt, der danach
einen anderen Knopf drueckt.

**Die zweite ist das Lesen.** Elf Tests suchen in der Seite nach einer
Elementkennung oder einem Funktionsnamen. Laesen sie weiter nur ``ema.html``,
waeren sie nach der Aufteilung nicht rot, sondern **gruen und blind**: eine
Zeichenkette, die nicht mehr in der Datei steht, meldet keinen Fehler.
``ema_seite.quelltext()`` ist die eine Stelle, die beides zusammenfuehrt.

Aufruf: ``venv/bin/python test_oberflaeche.py``
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_seite
import ema_werkzeugstand as W

HIER = os.path.dirname(os.path.abspath(__file__))
ORDNER = os.path.join(HIER, "oberflaeche")

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


NAMEN = ema_seite.skriptnamen()
QUELLEN = {n: open(os.path.join(ORDNER, n), encoding="utf-8").read()
           for n in NAMEN if os.path.isfile(os.path.join(ORDNER, n))}


print("1. Die Seite und der Ordner meinen dieselben Dateien")
pruefe(len(NAMEN) >= 10, f"{len(NAMEN)} Skripte in ema.html eingebunden")
fehlend = [n for n in NAMEN if n not in QUELLEN]
pruefe(not fehlend, f"jede eingebundene Datei liegt auch da{'' if not fehlend else ': fehlt ' + ', '.join(fehlend)}")
auf_platte = {f for f in os.listdir(ORDNER) if f.endswith(".js")}
verwaist = sorted(auf_platte - set(NAMEN))
# Eine Datei, die da liegt und nicht eingebunden ist, wird nie geladen — und
# sieht beim Lesen trotzdem nach gueltigem Code aus. Das ist die schlimmere
# Haelfte: sie faellt erst auf, wenn jemand sie zu aendern versucht.
pruefe(not verwaist, f"und keine liegt ungenutzt daneben{'' if not verwaist else ': ' + ', '.join(verwaist)}")

# `ema.html` traegt NUR noch Einbindungen. Ein neuer Inline-Block waere der
# erste Schritt zurueck zu den 16.096 Zeilen.
html = open(ema_seite.SEITE, encoding="utf-8").read()
inline = [m for m in re.findall(r"<script(?![^>]*\ssrc=)[^>]*>(.*?)</script>",
                                html, re.S) if m.strip()]
pruefe(not inline,
       f"ema.html enthaelt kein Inline-JavaScript mehr "
       f"({len(html.splitlines())} Zeilen Markup und Stil)")


print("\n2. Reihenfolge: was Knoepfe verdrahtet, kommt zuletzt")
pruefe(NAMEN[-1] == "sim.js",
       "sim.js steht ganz hinten — es startet beim Laden seine Zeichenschleife")
pruefe(NAMEN[-2] == "verdrahtung.js",
       "verdrahtung.js steht davor")

# Der eigentliche Punkt: JEDE Funktion, die `verdrahtung.js` an einen Knopf
# haengt, muss in einer FRUEHER geladenen Datei deklariert sein. Gepruefte
# Gegenprobe im Modulkopf.
vor = "\n".join(QUELLEN[n] for n in NAMEN[:NAMEN.index("verdrahtung.js")])
# Nur die Zeilen auf oberster Ebene: innerhalb der Splitter-Kapsel haengen
# `onMove`/`stop` an Fenster-Ereignissen, und die sind dort lokal deklariert.
gerufen = set()
for zeile in QUELLEN["verdrahtung.js"].splitlines():
    if zeile[:1].isspace():
        continue
    gerufen.update(re.findall(
        r"addEventListener\(\s*'[a-z]+'\s*,\s*([A-Za-z_$][\w$]*)\s*\)", zeile))
pruefe(len(gerufen) >= 5, f"{len(gerufen)} Funktionen werden dort angehaengt")
for name in sorted(gerufen):
    pruefe(re.search(r"^(async\s+)?function\s+%s\s*\(" % re.escape(name),
                     vor, re.M) is not None,
           f"{name}() ist vorher deklariert")


print("\n3. Jede Datei fuer sich — und alle zusammen")
node = shutil.which("node") or shutil.which("nodejs")
if not node:
    print("  … node fehlt, Syntaxpruefung uebersprungen")
else:
    for n in NAMEN:
        r = subprocess.run([node, "--check", os.path.join(ORDNER, n)],
                           capture_output=True, text=True)
        pruefe(r.returncode == 0,
               f"{n}: syntaktisch vollstaendig" +
               ("" if r.returncode == 0 else " — " + r.stderr.strip()[:200]))
    # Zusammen gelesen faellt auf, was einzeln nicht auffaellt: derselbe Name
    # zweimal auf oberster Ebene mit `let`/`const` ist ein Fehler, den keine
    # Datei fuer sich zeigt (dasselbe Verfahren wie test_studio.py fuer
    # agent_gemein.js + Seite). `sim.js` bleibt draussen — es ist eine Kapsel
    # und darf Namen fuehren, die oben schon vergeben sind.
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as f:
        f.write("\n".join(QUELLEN[n] for n in NAMEN if n != "sim.js"))
        pfad = f.name
    try:
        r = subprocess.run([node, "--check", pfad], capture_output=True, text=True)
        pruefe(r.returncode == 0,
               "und alle zusammen — keine doppelte Deklaration" +
               ("" if r.returncode == 0 else " — " + r.stderr.strip()[:200]))
    finally:
        os.unlink(pfad)


print("\n4. Wer die Seite liest, liest auch das Skript")
q = ema_seite.quelltext()
pruefe('id="panel-geo"' in q, "quelltext() traegt das Markup")
pruefe("async function buildPayload()" in q, "… und die Masken-Logik")
pruefe("function magnetLegs(G)" in q, "… und die Kapsel der Live-Vorschau")
a, b = q.find("// <<MIRROR-START>>"), q.find("// <<MIRROR-END>>")
pruefe(0 < a < b, "der Spiegelblock von magnet_legs ist am Stueck auffindbar "
                  "(test_topology.py schneidet genau hier)")
pruefe(q.count("// <<MIRROR-START>>") == 1,
       "und die Startmarke kommt genau EINMAL vor — eine Erwaehnung im "
       "Dateikopf reichte, um den Schnitt ins Leere laufen zu lassen")

# Dass KEIN Test mehr an `ema.html` vorbei liest, ist der Teil, der still
# kaputtgehen kann: ein direktes open() findet die Datei weiterhin.
direkt = []
for f in sorted(os.listdir(HIER)):
    if not (f.startswith("test_") and f.endswith(".py")) or f == os.path.basename(__file__):
        continue
    t = open(os.path.join(HIER, f), encoding="utf-8").read()
    if re.search(r'open\([^)]*"ema\.html"', t):
        direkt.append(f)
pruefe(not direkt,
       "kein Test liest ema.html direkt" +
       ("" if not direkt else " — " + ", ".join(direkt)))


print("\n5. Der Fingerabdruck kennt die neuen Dateien")
stand = W.stand_oberflaeche()
pruefe(not stand["fehlt"], "keine Datei der Oberflaeche fehlt")
for n in NAMEN:
    pruefe("oberflaeche/" + n in stand["dateien"],
           f"oberflaeche/{n} geht in den Stand ein")
pruefe(all("oberflaeche/" + n in W._AUSGELIEFERT for n in NAMEN),
       "und sie gelten als AUSGELIEFERT — nach einer Aenderung genuegt ein "
       "Neuladen, kein Serverneustart")


print("\n" + "=" * 60)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
