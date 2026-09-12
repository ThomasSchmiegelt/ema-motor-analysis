"""Die EINE Stelle zum Sprachmodell — lokal unveraendert, API uebersetzt.

Was hier still falsch sein koennte und deshalb geprueft wird:

* **Lokal muss BYTE FUER BYTE dieselbe Anfrage herausgehen wie vorher.** Das
  ganze Werkzeug haengt am lokalen Weg; eine Umleitung, die dort auch nur
  ``num_ctx`` verliert, klemmt das Modell still auf den Modelfile-Wert zurueck
  (``ema_report`` beschreibt genau das).
* **``num_ctx`` und ``think`` gibt es in keiner fremden API.** Sie fallen weg —
  aber sie muessen GENANNT werden, sonst verschiebt sich das Verhalten
  unbemerkt.
* **Anthropic will die Systemrolle NEBEN den Nachrichten und ``max_tokens``
  zwingend.** Ohne beides kommt ein 400 zurueck.
* **Einbettungen bleiben lokal, immer.** Kein Anbieter im Katalog hat einen
  Embeddings-Endpunkt, und eine woanders erzeugte Einbettung waere mit den
  vorhandenen unvergleichbar — der Index ist ein Vektorraum, kein Textspeicher.
* **Der Schluessel gehoert in keine Auskunft.**

Aufruf: ``venv/bin/python test_llm.py``  (ohne Netz, ohne Ollama)
"""

import json
import os
import sys
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_llm as L
import ema_modelle as M

_ok = _bad = 0


def pruefe(b, t):
    global _ok, _bad
    if b:
        _ok += 1; print(f"  ✓ {t}")
    else:
        _bad += 1; print(f"  ✗ {t}")


GESTELLT = {"providers": {
    "ollama": {"baseUrl": "http://localhost:11434/v1", "api": "openai-completions",
               "apiKey": "ollama", "models": [{"id": "qwen-gross:latest"}]},
    "einanbieter": {"baseUrl": "https://api.beispiel.test/v1",
                    "api": "openai-completions",
                    "apiKey": "sk-GEHEIM-NICHT-AUSGEBEN",
                    "models": [{"id": "fremd/modell"}]},
    "anthropic": {"baseUrl": "https://api.anthropic.com/v1", "api": "anthropic",
                  "apiKey": "sk-ant-GEHEIM2", "models": [{"id": "claude-opus-5"}]},
    "ohne_schluessel": {"baseUrl": "https://api.leer.test/v1",
                        "api": "openai-completions",
                        "models": [{"id": "leer/modell"}]},
}}

# Was wirklich hinausging — die Anfrage wird abgefangen, nicht gesendet.
GESENDET = {}


class _Antwort:
    def __init__(self, d): self._d = json.dumps(d).encode()
    def read(self): return self._d
    def __enter__(self): return self
    def __exit__(self, *a): return False


def _stub(req, timeout=None):
    GESENDET.clear()
    GESENDET.update({"url": req.full_url,
                     "kopf": {k.lower(): v for k, v in req.headers.items()},
                     "rumpf": json.loads(req.data.decode())})
    if "anthropic" in req.full_url:
        return _Antwort({"content": [{"type": "text", "text": "ANTWORT-A"}]})
    if "/api/" in req.full_url:                      # lokaler Ollama-Weg
        return _Antwort({"message": {"content": "ANTWORT-L"},
                         "response": "ANTWORT-L"})
    return _Antwort({"choices": [{"message": {"content": "ANTWORT-O"}}]})


ANFRAGE = {"model": "", "messages": [
               {"role": "system", "content": "Du bist knapp."},
               {"role": "user", "content": "Hallo"}],
           "stream": False, "think": False, "format": "json",
           "options": {"temperature": 0.3, "num_ctx": 65536, "num_predict": 999}}

_echt = urllib.request.urlopen
tmp = tempfile.mkdtemp()
pfad = os.path.join(tmp, "models.json")
with open(pfad, "w", encoding="utf-8") as f:
    json.dump(GESTELLT, f)
M.PI_MODELLE = pfad
urllib.request.urlopen = _stub

try:
    print("1. Lokal: der Rumpf geht UNVERAENDERT hinaus")
    a = dict(ANFRAGE, model="qwen-gross:latest")
    r = L.senden(dict(a), "chat", timeout=5)
    pruefe(GESENDET["rumpf"] == a,
           "Byte fuer Byte dieselbe Anfrage — auch num_ctx, think und format")
    pruefe(GESENDET["url"].endswith("/api/chat"),
           f"an Ollamas eigenen Pfad ({GESENDET['url']})")
    pruefe("/v1/api" not in GESENDET["url"],
           "das '/v1' aus dem Katalog wird dabei abgeschnitten — sonst stuende "
           "'/v1/api/chat' da und nichts antwortete")
    pruefe(r["message"]["content"] == "ANTWORT-L", "Antwort kommt durch")
    pruefe(L.letzte_info["lokal"] is True and L.letzte_info["verloren"] == [],
           "und es geht nichts verloren")

    print("\n2. OpenAI-kompatibel: uebersetzt, und was fehlt, wird gesagt")
    r = L.senden(dict(ANFRAGE, model="fremd/modell"), "chat", timeout=5)
    b = GESENDET["rumpf"]
    pruefe(GESENDET["url"] == "https://api.beispiel.test/v1/chat/completions",
           GESENDET["url"])
    pruefe(GESENDET["kopf"].get("authorization", "").startswith("Bearer "),
           "Schluessel als Bearer-Kopf")
    pruefe(b.get("temperature") == 0.3 and b.get("max_tokens") == 999,
           "Temperatur und num_predict→max_tokens kommen mit")
    pruefe(b.get("response_format") == {"type": "json_object"},
           "format='json' wird zu response_format — sonst kaeme Prosa zurueck, "
           "wo der Aufrufer JSON erwartet")
    pruefe("num_ctx" not in json.dumps(b) and "think" not in b,
           "num_ctx und think gehen NICHT mit (gibt es dort nicht)")
    pruefe(set(L.letzte_info["verloren"]) == {"num_ctx", "think"},
           f"und genau das wird gemeldet: {L.letzte_info['verloren']}")
    pruefe(r["message"]["content"] == "ANTWORT-O",
           "die Antwort kommt in Ollama-Form zurueck — die Aufrufer merken nichts")

    print("\n3. Anthropic: Systemrolle daneben, max_tokens zwingend")
    r = L.senden(dict(ANFRAGE, model="claude-opus-5"), "chat", timeout=5)
    b = GESENDET["rumpf"]
    pruefe(GESENDET["url"].endswith("/messages"), GESENDET["url"])
    pruefe(GESENDET["kopf"].get("x-api-key") and
           GESENDET["kopf"].get("anthropic-version") == "2023-06-01",
           "x-api-key und anthropic-version im Kopf (nicht Bearer)")
    pruefe(b.get("system") == "Du bist knapp.",
           "die Systemrolle steht NEBEN den Nachrichten")
    pruefe(all(m["role"] != "system" for m in b["messages"]),
           "und nicht mehr in ihnen")
    pruefe(isinstance(b.get("max_tokens"), int) and b["max_tokens"] > 0,
           f"max_tokens ist gesetzt ({b.get('max_tokens')}) — ohne gibt es 400")
    pruefe(r["message"]["content"] == "ANTWORT-A", "Antwort zurueckuebersetzt")

    print("\n4. /api/generate: ein Prompt wird zu einer Nachricht")
    L.senden({"model": "fremd/modell", "prompt": "Sag Hallo",
              "stream": False, "options": {}}, "generate", timeout=5)
    b = GESENDET["rumpf"]
    pruefe(b["messages"] == [{"role": "user", "content": "Sag Hallo"}],
           "der Prompt wird zur Nutzernachricht — /chat/completions kennt "
           "keinen blossen Prompt")

    print("\n5. Einbettungen bleiben LOKAL, auch bei einem API-Modell")
    L.senden({"model": "fremd/modell", "prompt": "x"}, "embeddings", timeout=5)
    pruefe("/api/embeddings" in GESENDET["url"]
           and "beispiel.test" not in GESENDET["url"],
           f"gegangen an {GESENDET['url']} — kein Anbieter im Katalog hat einen "
           f"Embeddings-Endpunkt, und eine woanders erzeugte Einbettung waere "
           f"mit den vorhandenen unvergleichbar")

    print("\n6. Ohne Schluessel: klares Nein, und nie ein Schluessel in der Auskunft")
    try:
        L.senden(dict(ANFRAGE, model="leer/modell"), "chat", timeout=5)
        pruefe(False, "haette scheitern muessen")
    except L.LlmFehler as e:
        pruefe("Schluessel" in str(e), f"abgewiesen: {str(e)[:60]}…")
    L.senden(dict(ANFRAGE, model="fremd/modell"), "chat", timeout=5)
    pruefe("GEHEIM" not in json.dumps(L.letzte_info),
           "letzte_info traegt den Schluessel NICHT")

    print("\n7. Alle sechs Aufrufer gehen wirklich durch diese Stelle")
    hier = os.path.dirname(os.path.abspath(__file__))
    for f in ("ema_report.py", "ema_chat.py", "ema_text2ema.py",
              "ema_optimize.py", "ema_design_ai.py", "ema_experts.py"):
        q = open(os.path.join(hier, f), encoding="utf-8").read()
        pruefe("_llm.senden(" in q and "urllib.request.urlopen" not in q,
               f"{f}: ueber _llm.senden, kein eigener urlopen mehr")
finally:
    urllib.request.urlopen = _echt

print("\n" + "=" * 64)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
