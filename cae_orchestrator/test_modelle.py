"""Der Modellkatalog — gepflegt statt von Hand geführt, und ohne den Schlüssel auszuplaudern.

Was hier still falsch sein könnte und deshalb geprüft wird:

* **Eine Handliste neben einer Wirklichkeit, die sich ändert, läuft auseinander.**
  Gemessen am 11.09.2026: ``pi --list-models`` zeigte **zwei** Modelle, in Ollama
  lagen **zwanzig**, und eines der zwei (``qwen3.5:9b``) war gar nicht
  installiert — die Startmaske bot also ein Modell an, an dem der Start
  scheitert, und verschwieg neunzehn, die es gibt.
* **Ein Abgleich darf nie etwas wegnehmen.** Ist Ollama gerade aus, sieht der
  Abgleich null Modelle. Würde er daraus „dann weg damit" schließen, wäre ein
  ausgeschaltetes Ollama gleichbedeutend mit einem gelöschten Katalog — und der
  Katalog gehört ``pi``, nicht uns.
* **Der Schlüssel gehört in keine Antwort.** Er wird eingetragen und danach nur
  noch als ja/nein gemeldet.
* **Preise stehen bei OpenRouter je TOKEN, im Katalog je MILLION.** Ungerechnet
  übernommen stünde an einem Modell für 10 $/Mio die Angabe „kostet nichts".

Aufruf: ``venv/bin/python test_modelle.py``
"""

import json
import os
import stat
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_modelle as M

_ok = _bad = 0


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


GESTELLT = {"providers": {"ollama": {
    "baseUrl": "http://localhost:11434/v1", "api": "openai-completions",
    "apiKey": "ollama",
    "models": [{"id": "qwen-gross:latest", "name": "Qwen lokal"},
               {"id": "gibtsnichtmehr:latest", "name": "Karteileiche"}]}}}

# Ein gestelltes Ollama: der Test darf nicht davon abhaengen, was gerade
# installiert ist -- sonst prueft er die Maschine statt den Code.
DA = [{"id": "qwen-gross:latest", "groesse_gb": 17.7, "digest": "1bb3a46c5021",
       "parameter": "27B", "quant": "Q4_K_M"},
      {"id": "ministral-3:14b", "groesse_gb": 9.1, "digest": "4760c35aeb9d",
       "parameter": "14B", "quant": "Q4_K_M"}]


def _mit_gestelltem_ollama(liste, grund=""):
    M.installiert = lambda url=M.OLLAMA_URL, timeout=4.0: (liste, grund)


_echt_installiert = M.installiert


def _neue_datei(tmp, inhalt=GESTELLT):
    p = os.path.join(tmp, "models.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(inhalt, f)
    return p


print("1. Der Abgleich traegt ein, was WIRKLICH da ist")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    _mit_gestelltem_ollama(DA)
    r = M.sync_ollama(p)
    pruefe(r["ok"], "Abgleich laeuft")
    pruefe(r["neu"] == ["ministral-3:14b"],
           f"genau das fehlende Modell kommt hinzu ({r['neu']})")
    pruefe(r["verwaist"] == ["gibtsnichtmehr:latest"],
           "und der Eintrag ohne Modell wird BENANNT")
    d = json.load(open(p))
    ids = [m["id"] for m in d["providers"]["ollama"]["models"]]
    pruefe("gibtsnichtmehr:latest" in ids,
           "er wird aber NICHT geloescht — er kann zu einem Ollama gehoeren, "
           "das gerade aus ist, und die Datei gehoert pi, nicht uns")
    pruefe(len(ids) == 3, f"drei Eintraege, keine Dubletten ({ids})")

    zweimal = M.sync_ollama(p)
    pruefe(zweimal["neu"] == [],
           "ein zweiter Abgleich traegt nichts nach — er ist idempotent")

print("\n2. Ist Ollama aus, wird NICHTS angetastet")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    vorher = open(p, encoding="utf-8").read()
    _mit_gestelltem_ollama([], "Ollama nicht erreichbar (URLError)")
    r = M.sync_ollama(p)
    pruefe(not r["ok"] and "erreichbar" in r["grund"],
           f"der Abgleich sagt warum: {r['grund']!r}")
    pruefe(open(p, encoding="utf-8").read() == vorher,
           "und die Datei ist Byte fuer Byte unveraendert — ein ausgeschaltetes "
           "Ollama darf keinen Katalog leeren")
    k = M.katalog(p, pruefe_ollama=True)
    pruefe(all(m["da"] for m in k["modelle"]),
           "und im Katalog gilt dann NICHTS als fehlend: ohne Auskunft laesst "
           "sich das nicht behaupten")

print("\n3. Was der Katalog herausgibt — und was nicht")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    _mit_gestelltem_ollama(DA)
    M.anbieter_setzen("openrouter", "sk-or-v1-GEHEIM-NICHT-AUSGEBEN",
                      [{"id": "anthropic/claude-opus-5", "contextWindow": 1000000,
                        "cost": {"input": 5.0, "output": 25.0}}], pfad=p)
    k = M.katalog(p)
    roh = json.dumps(k, ensure_ascii=False)
    pruefe("GEHEIM" not in roh,
           "der Schluessel steht in KEINER Antwort — er ginge sonst durch den Browser")
    nach = {m["modell"]: m for m in k["modelle"]}
    pruefe(nach["anthropic/claude-opus-5"]["schluessel"] is True
           and nach["anthropic/claude-opus-5"]["lokal"] is False,
           "nur die Auskunft, OB einer da ist — und dass es nicht lokal ist")
    pruefe(nach["gibtsnichtmehr:latest"]["da"] is False
           and nach["qwen-gross:latest"]["da"] is True,
           "'da' trennt den Karteileichen-Eintrag vom wirklich installierten")
    pruefe(k["modelle"][-1]["da"] is False,
           "und Fehlendes steht ganz unten, nicht mittendrin")
    pruefe(nach["anthropic/claude-opus-5"]["kostet"] is True
           and nach["qwen-gross:latest"]["kostet"] is False,
           "kostenpflichtig und kostenlos werden auseinandergehalten")

print("\n4. Eintragen: ohne Schluessel kein API-Anbieter")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    r = M.anbieter_setzen("openrouter", "", [{"id": "a/b"}], pfad=p)
    pruefe(not r["ok"] and "Schluessel" in r["grund"],
           f"abgewiesen statt halb eingetragen: {r['grund']!r}")
    r = M.anbieter_setzen("openrouter", "sk-1", [], pfad=p)
    pruefe(not r["ok"] and "Modell" in r["grund"],
           "und ein Anbieter ohne Modell steht in keiner Auswahl")
    r = M.anbieter_setzen("gibtsnicht", "sk-1", [{"id": "a/b"}], pfad=p)
    pruefe(not r["ok"] and "unbekannt" in r["grund"],
           "ein unbekannter Anbieter braucht eine Basisadresse — geraten wird keine")

    M.anbieter_setzen("openrouter", "sk-erster", [{"id": "a/b"}], pfad=p)
    M.anbieter_setzen("openrouter", "", [{"id": "c/d"}], pfad=p)
    d = json.load(open(p))
    pruefe(d["providers"]["openrouter"]["apiKey"] == "sk-erster",
           "ein LEERER Schluessel laesst den vorhandenen stehen — Modelle "
           "nachtragen, ohne ihn neu tippen zu muessen")
    pruefe([m["id"] for m in d["providers"]["openrouter"]["models"]] == ["a/b", "c/d"],
           "und die Modelle kommen dazu statt sich zu ersetzen")

print("\n5. Die Datei: 0600, atomar, mit Sicherung")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    M.anbieter_setzen("openrouter", "sk-1", [{"id": "a/b"}], pfad=p)
    m = stat.S_IMODE(os.stat(p).st_mode)
    pruefe(m == 0o600, f"Rechte 0600 (ist {oct(m)}) — da steht ein Schluessel drin")
    pruefe(os.path.isfile(p + ".bak"), "eine Sicherung liegt daneben")
    pruefe(json.load(open(p + ".bak")) == GESTELLT,
           "und sie traegt den Stand VOR der ersten Aenderung")
    M.anbieter_setzen("openrouter", "sk-2", [{"id": "e/f"}], pfad=p)
    pruefe(json.load(open(p + ".bak")) == GESTELLT,
           "eine zweite Aenderung ueberschreibt die Sicherung NICHT — sonst "
           "waere sie nach zwei Fehlgriffen wertlos")
    pruefe(not [f for f in os.listdir(tmp) if f.startswith(".models.")],
           "keine Reste der temporaeren Datei")

print("\n6. Preise: je TOKEN herein, je MILLION hinein")
roh = {"data": [{"id": "anthropic/claude-opus-5", "name": "Opus 5",
                 "context_length": 1000000,
                 "pricing": {"prompt": "0.000005", "completion": "0.000025"}},
                {"id": "frei/modell", "context_length": 8192,
                 "pricing": {"prompt": "0", "completion": "0"}}]}
import urllib.request
class _Antwort:
    def read(self): return json.dumps(roh).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
_echt_urlopen = urllib.request.urlopen
urllib.request.urlopen = lambda *a, **k: _Antwort()
try:
    r = M.fremde_modelle("openrouter", "sk-1")
    nach = {m["id"]: m for m in r["modelle"]}
    pruefe(nach["anthropic/claude-opus-5"]["cost"]["input"] == 5.0
           and nach["anthropic/claude-opus-5"]["cost"]["output"] == 25.0,
           "0,000005 $/Token wird zu 5,00 $/Mio — ungerechnet uebernommen "
           "stuende an einem Modell fuer 5 $/Mio die Angabe 'kostet nichts'")
    pruefe(nach["frei/modell"]["cost"]["input"] == 0,
           "und ein kostenloses bleibt kostenlos")
    pruefe(nach["anthropic/claude-opus-5"]["contextWindow"] == 1000000,
           "das Kontextfenster kommt vom Anbieter, nicht aus einer Annahme")
finally:
    urllib.request.urlopen = _echt_urlopen

print("\n7. Ein EIGENER Anbieter — Adresse und API-Form aus der Maske")
with tempfile.TemporaryDirectory() as tmp:
    p = _neue_datei(tmp)
    r = M.anbieter_setzen("groq", "sk-GEHEIM3",
                          [{"id": "llama-3.3-70b"}, {"id": "mixtral-8x7b"}],
                          pfad=p, base_url="https://api.groq.com/openai/v1",
                          api="openai-completions")
    pruefe(r["ok"] and r["anbieter"] == "groq" and len(r["modelle"]) == 2,
           "ein Anbieter, der in BEKANNT gar nicht steht, laesst sich eintragen "
           "— sonst waere die Auswahl auf drei Dienste festgenagelt")
    pruefe(r["lokal"] is False,
           "und gilt als nicht lokal — an der ADRESSE gemessen, nicht am Namen")
    d = json.load(open(p))["providers"]["groq"]
    pruefe(d["baseUrl"] == "https://api.groq.com/openai/v1"
           and d["api"] == "openai-completions",
           "Basisadresse und API-Form stehen so im Katalog, wie sie getippt wurden")
    k = M.katalog(p, pruefe_ollama=False)
    pruefe("GEHEIM3" not in json.dumps(k, ensure_ascii=False),
           "und auch hier verlaesst der Schluessel das Modul nicht")

    # Ohne Basisadresse ist ein unbekannter Anbieter nicht eintragbar — geraten
    # wird keine. (Der Server weist es ab, die Maske sagt es vorher.)
    r2 = M.anbieter_setzen("garnicht", "sk-1", [{"id": "x"}], pfad=p)
    pruefe(not r2["ok"] and "unbekannt" in r2["grund"],
           f"ohne Adresse abgewiesen: {r2['grund']!r}")

print("\n8. Die Modellliste eines eigenen Anbieters: /models wird VERSUCHT")
_gerufen = {}
class _A2:
    def read(self): return json.dumps({"data": [{"id": "llama-3.3-70b"}]}).encode()
    def __enter__(self): return self
    def __exit__(self, *a): return False
def _spion(req, timeout=None):
    _gerufen["url"] = req.full_url
    return _A2()
_echt2 = urllib.request.urlopen
urllib.request.urlopen = _spion
try:
    r = M.fremde_modelle("groq", "sk-1", basis="https://api.groq.com/openai/v1")
    pruefe(r["ok"] and _gerufen["url"] == "https://api.groq.com/openai/v1/models",
           f"gefragt wird {_gerufen.get('url')} — der OpenAI-Standardpfad")
    pruefe([m["id"] for m in r["modelle"]] == ["llama-3.3-70b"],
           "und die Kennungen kommen zurueck")
finally:
    urllib.request.urlopen = _echt2

r = M.fremde_modelle("garnichtbekannt", "sk-1")
pruefe(not r["ok"] and "Hand" in r["grund"],
       "ohne Basis und ohne Hinterlegung sagt es, dass man die Kennungen von "
       "Hand eintragen kann — statt nur 'geht nicht'")

print("\n9. Die Maske fuehrt die Felder und reicht sie durch")
_h = open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "ema_agent.html"), encoding="utf-8").read()
for feld in ("kat_name", "kat_basis", "kat_api", "kat_ids"):
    pruefe(f'id="{feld}"' in _h, f"Feld {feld} vorhanden")
pruefe('value="__eigen__"' in _h,
       "und ein Eintrag 'eigener Anbieter' in der Auswahl")
pruefe(_h.count("katAnbieterFelder()") >= 2,
       "Suchen UND Eintragen holen die Angaben aus DERSELBEN Stelle — zwei "
       "Abschriften liefen beim ersten Feld auseinander")
pruefe("kat_ids" in _h.split("function katEintragen")[1][:1200],
       "von Hand getippte Kennungen werden mit eingetragen — ohne sie waere ein "
       "Anbieter ohne /models gar nicht eintragbar")

print("\n10. Und die Sperre sitzt im Server, nicht in der Maske")
try:
    import server
    c = server.app.test_client()
    fremd = {"REMOTE_ADDR": "192.168.1.50"}
    for pfad in ("/agent/anbieter", "/agent/anbieter/sync", "/agent/anbieter/liste"):
        r = c.post(pfad, json={"anbieter": "openrouter"}, environ_base=fremd)
        pruefe(r.status_code == 403,
               f"POST {pfad} aus dem Heimnetz -> {r.status_code}")
    r = c.get("/agent/anbieter", environ_base=fremd)
    pruefe(r.status_code == 200 and r.get_json()["lokal"] is False,
           "LESEN bleibt offen, sagt aber 'nicht lokal' — die Maske sperrt "
           "ihre Felder daraufhin selbst, und der Server verlaesst sich nicht darauf")
    roh = json.dumps(r.get_json())
    pruefe("apiKey" not in roh and "sk-" not in roh,
           "und auch diese Antwort traegt keinen Schluessel")
except Exception as e:                       # ohne Flask laeuft der Rest trotzdem
    print(f"  — Serverteil uebersprungen ({type(e).__name__}: {e})")

M.installiert = _echt_installiert
print("\n" + "=" * 66)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
