"""Ein Modell ueber eine API angeben -- ohne Server, ohne pi, ohne Netz.

Was hier still falsch sein koennte und deshalb geprueft wird:

* **„lokal" muss an der ADRESSE gemessen werden, nicht am Namen.** Ein Anbieter
  darf heissen, wie er will; ob Eingaben die Maschine verlassen, entscheidet der
  Host. Wer nach dem Namen geht, erklaert einen entfernten Dienst namens
  ``ollama`` zum Heimspiel.
* **Es darf keine zweite Modell-Liste geben.** Die Anbieter stehen in PIs eigener
  ``models.json``; eine hier gepflegte Kopie liefe auseinander, und dann boete
  die Maske ein Modell an, das ``pi`` nicht kennt.
* **Ein unbekanntes Modell darf NICHT zu einem geratenen Anbieter fuehren.**
  Dann bliebe es bei ``ollama``, und alles verhaelt sich wie vorher.
* **Kein Schluessel gehoert in eine Antwort, die durch den Browser geht** -- nur
  die Auskunft, ob einer da ist.

Aufruf: ``venv/bin/python test_modellwahl.py``
"""

import json
import os
import re
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_agent as A

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


# Eine erfundene models.json -- der lokale Fall allein wuerde genau das nicht
# pruefen, worum es hier geht.
GESTELLT = {
    "providers": {
        "ollama": {
            "baseUrl": "http://localhost:11434/v1", "api": "openai-completions",
            "apiKey": "ollama",
            "models": [{"id": "qwen-gross:latest", "name": "Qwen lokal",
                        "contextWindow": 65536,
                        "cost": {"input": 0, "output": 0}}]},
        "anthropic": {
            "baseUrl": "https://api.anthropic.com/v1", "api": "anthropic",
            "apiKey": "sk-ant-GEHEIM-NICHT-AUSGEBEN",
            "models": [{"id": "claude-opus-5", "name": "Opus 5",
                        "contextWindow": 200000,
                        "cost": {"input": 15, "output": 75}}]},
        # Ein Anbieter OHNE Schluessel: der Start muss daran scheitern, und die
        # Maske muss es vorher sagen.
        "ohne_schluessel": {
            "baseUrl": "https://api.example.com/v1", "api": "openai-completions",
            "models": [{"id": "irgendwas", "name": "Ohne Schluessel",
                        "cost": {"input": 1, "output": 1}}]},
        # Die Falle: heisst wie der lokale, liegt aber woanders.
        "ollama_fern": {
            "baseUrl": "https://ollama.example.com/v1",
            "api": "openai-completions", "apiKey": "x",
            "models": [{"id": "fern:latest", "name": "Ollama auf fremdem Wirt",
                        "cost": {"input": 0, "output": 0}}]},
    }
}


print("1. Lokal oder nicht — an der Adresse gemessen")
for url, soll in (("http://localhost:11434/v1", True),
                  ("http://127.0.0.1:11434/v1", True),
                  ("http://[::1]:8080", True),
                  ("https://api.anthropic.com/v1", False),
                  ("https://ollama.example.com/v1", False),
                  ("", False)):
    pruefe(A._ist_lokal(url) is soll,
           f"{url or '(leer)'} -> {'lokal' if soll else 'nicht lokal'}")

with tempfile.TemporaryDirectory() as tmp:
    pfad = os.path.join(tmp, "models.json")
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(GESTELLT, f)

    print("\n2. Die Liste kommt aus PIs Datei")
    r = A.modelle(pfad)
    pruefe(r["ok"] and len(r["modelle"]) == 4,
           f"vier Modelle aus vier Anbietern gelesen ({len(r['modelle'])})")
    nach = {m["modell"]: m for m in r["modelle"]}
    pruefe(nach["qwen-gross:latest"]["lokal"] is True
           and nach["claude-opus-5"]["lokal"] is False,
           "lokal und API werden auseinandergehalten")
    pruefe(nach["fern:latest"]["lokal"] is False,
           "ein Anbieter, der 'ollama_fern' heisst, aber auf einem fremden Wirt "
           "liegt, gilt NICHT als lokal — sonst entschiede die Beschriftung "
           "darueber, ob Daten das Haus verlassen")
    pruefe(r["modelle"][0]["lokal"] is True,
           "lokale Modelle stehen oben: wer ein API-Modell will, soll es "
           "ausdruecklich waehlen statt es versehentlich zu treffen")

    print("\n3. Was NICHT herausgegeben wird")
    roh = json.dumps(r, ensure_ascii=False)
    pruefe("sk-ant-GEHEIM" not in roh and "GEHEIM" not in roh,
           "der Schluessel steht in KEINER Antwort — er ginge sonst durch den "
           "Browser")
    pruefe(nach["claude-opus-5"]["schluessel"] is True
           and nach["irgendwas"]["schluessel"] is False,
           "nur die Auskunft, OB einer da ist — und die fehlt beim Anbieter "
           "ohne Schluessel")
    pruefe(nach["claude-opus-5"]["kostet"] is True
           and nach["qwen-gross:latest"]["kostet"] is False,
           "und ob der Lauf Geld kostet")

    print("\n4. Der Anbieter folgt aus dem Modell")
    pruefe(A.anbieter_fuer("claude-opus-5", pfad) == "anthropic",
           "ein API-Modell findet seinen Anbieter")
    pruefe(A.anbieter_fuer("qwen-gross:latest", pfad) == "ollama",
           "ein lokales auch")
    pruefe(A.anbieter_fuer("gibtsnicht", pfad) == "ollama",
           "ein UNBEKANNTES faellt auf ollama zurueck — geraten wird nichts, "
           "und alles verhaelt sich wie vorher")

    print("\n5. Fehlt die Datei, wird das gesagt")
    leer = A.modelle(os.path.join(tmp, "gibtsnicht.json"))
    pruefe(not leer["ok"] and leer["modelle"] == [] and leer["grund"],
           f"keine Datei -> keine Liste UND ein Grund: {leer['grund']!r}")
    kaputt = os.path.join(tmp, "kaputt.json")
    with open(kaputt, "w", encoding="utf-8") as f:
        f.write("{kein json")
    pruefe(not A.modelle(kaputt)["ok"],
           "und eine kaputte Datei reisst nichts mit")

print("\n6. Der Aufruf traegt den Anbieter — er war fest verdrahtet")
_hier = os.path.dirname(os.path.abspath(__file__))
_quelle = open(os.path.join(_hier, "ema_agent.py"), encoding="utf-8").read()
pruefe('"--provider", anbieter_fuer(modell)' in _quelle
       and '"--provider", "ollama"' not in _quelle,
       "PiKopf baut den Aufruf mit dem gefundenen Anbieter, nicht mit der "
       "Zeichenkette 'ollama'")
pruefe("self.anbieter" in _quelle and "self.lokal" in _quelle,
       "und fuehrt beides im Zustand mit — ein Lauf gegen ein API-Modell ist "
       "nicht derselbe Lauf wie einer gegen das lokale")
pruefe("verlassen" in _quelle.split("def sichern")[0].split("Modell:")[-1][:400]
       or "API" in _quelle.split("Modell:")[-1][:400],
       "das Protokoll sagt es ebenfalls")

print("\n7. Startskript und Startmaske")
_wurzel = os.path.dirname(_hier)
_sh = open(os.path.join(_wurzel, "start_agent.sh"), encoding="utf-8").read()
pruefe('--provider "$PROVIDER"' in _sh and "--provider ollama" not in _sh,
       "start_agent.sh reicht den Anbieter durch statt ihn festzuschreiben")
pruefe("--anbieter" in _sh and "--modell" in _sh,
       "und nimmt beide als Argument an")
pruefe('if [ "$PROVIDER" = "ollama" ]; then' in _sh,
       "der Ollama-Vorlauf laeuft nur noch, wenn der Agent auch dort rechnet — "
       "sonst pruefte er etwas, das mit dem Lauf nichts zu tun hat")
pruefe("verlaesst damit diese Maschine" in _sh,
       "und bei einem API-Modell steht im Terminal, was das bedeutet")
_syn = subprocess.run(["bash", "-n", os.path.join(_wurzel, "start_agent.sh")],
                      capture_output=True, text=True)
pruefe(_syn.returncode == 0, f"bash -n sauber ({_syn.stderr.strip()[:80] or 'ok'})")

for seite in ("ema_agent.html", "ema_studio.html"):
    _h = open(os.path.join(_hier, seite), encoding="utf-8").read()
    pruefe('<select id="f_modell"' in _h and "modellFuellen" in _h,
           f"{seite}: die Maske bietet eine Auswahl statt eines Textfelds")
    pruefe("verlässt" in _h and "modellHinweis" in _h,
           f"{seite}: und sagt bei einem API-Modell, dass die Eingaben die "
           f"Maschine verlassen")

_srv = open(os.path.join(_hier, "server.py"), encoding="utf-8").read()
pruefe('"modelle": mm.get("modelle")' in _srv,
       "/agent/auswahl liefert die Liste mit")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
