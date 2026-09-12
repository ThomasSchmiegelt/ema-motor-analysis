"""Die EINE Stelle, an der dieses Werkzeug ein Sprachmodell anspricht.

Warum es das gibt
-----------------

Das ema-Werkzeug hatte **sechs** eigene Anlaufstellen, jede mit eigenem
``urllib``-Aufruf und jede fest auf Ollamas eigenes Protokoll verdrahtet
(``/api/chat``, ``/api/generate``, ``/api/embeddings``)::

    ema_report.py    /api/generate     Bericht
    ema_chat.py      /api/chat         Chat
    ema_text2ema.py  /api/chat         Text → Auslegung
    ema_optimize.py  /api/chat         Zielwertsuche
    ema_design_ai.py /api/chat         KI-Entwurf
    ema_experts.py   /api/generate     Experten

Ein im Katalog eingetragener API-Anbieter wirkte damit nur fuer die
Agentenkoepfe; das Werkzeug selbst sprach weiter ausschliesslich mit Ollama.

Der Entwurf: **der Ollama-Rumpf bleibt die innere Sprache.**
----------------------------------------------------------

Die sechs Aufrufer bauen ihren Anfragerumpf weiter genauso wie bisher und
lesen die Antwort genauso wie bisher. ``senden`` schickt ihn bei einem
**lokalen** Anbieter unveraendert weiter -- Byte fuer Byte dieselbe Anfrage wie
vorher, also kann sich am lokalen Verhalten nichts aendern -- und uebersetzt ihn
nur fuer eine API. Die Antwort wird in dieselbe Form zurueckuebersetzt.

Das ist die risikoaermste Bauform: haette jeder Aufrufer stattdessen eine neue
Schnittstelle bekommen, waere jede der sechs Stellen eine eigene Gelegenheit
gewesen, das lokale Verhalten zu verschieben.

Was beim Uebersetzen VERLOREN geht -- und darum gesagt wird
-----------------------------------------------------------

* ``num_ctx`` gibt es in keiner OpenAI- oder Anthropic-API. Lokal ist es
  tragend (``ema_report.DEFAULT_NUM_CTX`` = 65536, und ein fehlender Wert
  klemmt das Modell auf den Modelfile-Wert zurueck); bei einer API bestimmt
  der Anbieter das Kontextfenster. Es wird fallengelassen, und ``letzte_info``
  sagt es.
* ``think: False`` ebenso. Es schaltet bei Ollama die Denkkette ab; die APIs
  haben eigene Mechanismen.
* **Einbettungen bleiben IMMER lokal.** Weder Anthropic noch OpenRouter bieten
  einen Embeddings-Endpunkt; ``ema_rag`` braucht ``nomic-embed-text``. Eine API
  ersetzt Ollama also NICHT vollstaendig, und das ist keine Uebergangsloesung,
  sondern die Lage.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

import ema_modelle as _kat

# Der lokale Weg, unveraendert. `ema_report.OLLAMA_URL` bleibt die Vorgabe fuer
# alle Aufrufer; hier steht nur der Rueckfall, falls jemand ohne Basis ruft.
OLLAMA_URL = _kat.OLLAMA_URL

# Was zuletzt geschah -- fuer die Arbeitsleiste und fuer Protokolle. KEIN
# Schluessel, nie.
letzte_info: dict = {}


class LlmFehler(RuntimeError):
    """Die Gegenstelle hat nicht geantwortet oder etwas Unlesbares geschickt."""


def _anbieter_von(modell: str) -> dict:
    """Anbietersatz zu einem Modell -- oder der lokale Ollama-Weg als Vorgabe."""
    try:
        k = _kat.katalog(pruefe_ollama=False)
        name = _kat.anbieter_fuer(modell)
        for a in (k.get("anbieter") or []):
            if a["name"] == name:
                roh = _kat._lies(_kat.PI_MODELLE)[0] or {}
                p = (roh.get("providers") or {}).get(name) or {}
                return {"name": name, "baseUrl": p.get("baseUrl", ""),
                        "api": p.get("api", "openai-completions"),
                        "apiKey": p.get("apiKey", ""),
                        "lokal": _kat.ist_lokal(p.get("baseUrl", ""))}
    except Exception:
        pass
    return {"name": "ollama", "baseUrl": OLLAMA_URL, "api": "ollama",
            "apiKey": "", "lokal": True}


def _hole(url: str, rumpf: bytes, kopf: dict, timeout: float) -> dict:
    req = urllib.request.Request(url, data=rumpf, headers=kopf)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        text = ""
        try:
            text = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise LlmFehler(f"HTTP {e.code} von {url}: {text}") from None
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
        raise LlmFehler(f"{type(e).__name__} an {url}") from None


# ── Uebersetzung: Ollama-Rumpf → fremde API ──────────────────────────────────

def _nach_openai(anfrage: dict, art: str) -> dict:
    """Ollama-Rumpf → OpenAI-``/chat/completions``."""
    opt = anfrage.get("options") or {}
    aus = {"model": anfrage.get("model"), "stream": False}
    if art == "generate":
        # /api/generate kennt nur einen Prompt; OpenAI will Nachrichten.
        aus["messages"] = [{"role": "user", "content": anfrage.get("prompt", "")}]
    else:
        aus["messages"] = anfrage.get("messages") or []
    if "temperature" in opt:
        aus["temperature"] = opt["temperature"]
    for k_o, k_n in (("top_p", "top_p"), ("num_predict", "max_tokens")):
        if k_o in opt:
            aus[k_n] = opt[k_o]
    if anfrage.get("format") == "json":
        aus["response_format"] = {"type": "json_object"}
    return aus


def _nach_anthropic(anfrage: dict, art: str) -> dict:
    """Ollama-Rumpf → Anthropic-``/messages``.

    Zwei Dinge sind dort anders und nicht optional: die Systemrolle steht
    **neben** den Nachrichten statt in ihnen, und ``max_tokens`` ist
    PFLICHT -- ohne kommt ein 400 zurueck.
    """
    opt = anfrage.get("options") or {}
    if art == "generate":
        nachr = [{"role": "user", "content": anfrage.get("prompt", "")}]
        system = ""
    else:
        roh = anfrage.get("messages") or []
        system = "\n\n".join(m.get("content", "") for m in roh
                             if m.get("role") == "system")
        nachr = [{"role": m.get("role"), "content": m.get("content", "")}
                 for m in roh if m.get("role") in ("user", "assistant")]
    aus = {"model": anfrage.get("model"),
           "messages": nachr or [{"role": "user", "content": ""}],
           "max_tokens": int(opt.get("num_predict") or 16000)}
    if system:
        aus["system"] = system
    if "temperature" in opt:
        aus["temperature"] = opt["temperature"]
    return aus


def _zurueck(d: dict, api: str, art: str) -> dict:
    """Fremde Antwort → Ollama-Form, damit die Aufrufer nichts merken."""
    if api == "anthropic":
        text = "".join(b.get("text", "") for b in (d.get("content") or [])
                       if b.get("type") == "text")
    else:
        wahl = (d.get("choices") or [{}])[0]
        text = ((wahl.get("message") or {}).get("content")
                or wahl.get("text") or "")
    return {"message": {"content": text}} if art == "chat" else {"response": text}


# ── Der eine Aufruf ──────────────────────────────────────────────────────────

def senden(anfrage: dict, art: str = "chat", base_url: str = "",
           timeout: float = 600.0) -> dict:
    """Eine Anfrage im Ollama-Format abschicken -- lokal oder ueber eine API.

    ``art``: ``"chat"`` · ``"generate"`` · ``"embeddings"``. Die Antwort kommt
    IMMER in Ollama-Form zurueck (``message.content`` bzw. ``response``), damit
    die sechs Aufrufer ihre Auswertung unveraendert behalten.
    """
    global letzte_info
    modell = str(anfrage.get("model") or "")
    a = _anbieter_von(modell)

    # Einbettungen: immer lokal. Es gibt in diesem Katalog keinen Anbieter mit
    # Embeddings-Endpunkt, und eine stillschweigend woanders erzeugte Einbettung
    # waere mit den vorhandenen unvergleichbar — der Index ist ein Vektorraum,
    # kein Textspeicher.
    if art == "embeddings" or a["lokal"] or a["api"] == "ollama":
        if art == "embeddings":
            # IMMER die lokale Adresse — auch wenn das Modell zu einem
            # API-Anbieter gehoert. Ein erster Entwurf nahm hier dessen
            # Basisadresse und haette den Text an einen fremden Dienst
            # geschickt, der dort gar keinen Embeddings-Endpunkt hat; der Test
            # hat es gefangen.
            basis = base_url or OLLAMA_URL
        else:
            basis = base_url or a["baseUrl"] or OLLAMA_URL
        if basis.endswith("/v1"):
            basis = basis[:-3]                     # /api/… liegt neben /v1
        pfad = {"chat": "/api/chat", "generate": "/api/generate",
                "embeddings": "/api/embeddings"}[art]
        letzte_info = {"anbieter": a["name"], "lokal": True, "api": "ollama",
                       "modell": modell, "verloren": []}
        return _hole(basis.rstrip("/") + pfad,
                     json.dumps(anfrage).encode("utf-8"),
                     {"Content-Type": "application/json"}, timeout)

    # ── Ab hier verlaesst die Anfrage die Maschine ──────────────────────────
    if not a["apiKey"]:
        raise LlmFehler(f"Anbieter '{a['name']}' hat keinen Schluessel im "
                        f"Katalog — Eintragen ueber die Startmaske "
                        f"(⚙ Modelle & API-Zugang, nur von diesem Rechner).")
    basis = (base_url or a["baseUrl"]).rstrip("/")
    verloren = [k for k in ("num_ctx",) if k in (anfrage.get("options") or {})]
    if anfrage.get("think") is not None:
        verloren.append("think")

    if a["api"] == "anthropic":
        url = basis + "/messages"
        kopf = {"Content-Type": "application/json", "x-api-key": a["apiKey"],
                "anthropic-version": "2023-06-01"}
        rumpf = _nach_anthropic(anfrage, art)
    else:                                          # openai-completions & Verwandte
        url = basis + "/chat/completions"
        kopf = {"Content-Type": "application/json",
                "Authorization": f"Bearer {a['apiKey']}"}
        rumpf = _nach_openai(anfrage, art)

    letzte_info = {"anbieter": a["name"], "lokal": False, "api": a["api"],
                   "modell": modell, "verloren": verloren}
    d = _hole(url, json.dumps(rumpf).encode("utf-8"), kopf, timeout)
    return _zurueck(d, a["api"], art)
