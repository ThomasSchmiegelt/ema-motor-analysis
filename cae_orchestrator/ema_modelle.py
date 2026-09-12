"""Der Modellkatalog — EINE Datei, gepflegt statt von Hand geführt.

Warum es dieses Modul gibt
--------------------------

``pi`` liest seinen Katalog aus ``~/.pi/agent/models.json``, und **er entdeckt
nichts von selbst**. Gemessen am 11.09.2026 mit ``pi --list-models``: zwei
Einträge. In Ollama lagen zur selben Zeit **zwanzig** Modelle. Der Katalog war
also nicht nur unvollständig — er war auch falsch: ``qwen3.5:9b`` stand darin
und war gar nicht installiert. Die Startmaske bot damit ein Modell an, das beim
Start nicht existiert, und verschwieg neunzehn, die es gibt.

Von Hand gepflegte Listen neben einer Wirklichkeit, die sich ändert, laufen
auseinander — das ist in diesem Repo schon mehrfach gemessen worden (die zweite
Geom-Tabelle in ``server.py``, die zweite Nutgeometrie, die abgeschriebene
``magnetLegs``). Also wird der Katalog **abgeglichen**, nicht gepflegt:

* was in Ollama liegt, kommt hinein (``sync_ollama``),
* was darin steht und nicht mehr liegt, wird **benannt und nicht gelöscht** —
  ein fremder Eintrag kann zu einem Ollama gehören, das gerade aus ist, und
  stillschweigend die Datei eines anderen Werkzeugs zu beschneiden wäre
  übergriffig,
* ein API-Anbieter wird ausdrücklich eingetragen (``anbieter_setzen``).

Drei Dinge, die hier nicht beliebig sind
----------------------------------------

**Der Schlüssel verlässt dieses Modul nie.** ``katalog()`` gibt zu jedem
Anbieter nur ``schluessel: True/False`` heraus. Ein Schlüssel gehört nicht in
eine Antwort, die durch einen Browser geht, und erst recht nicht in eine
Protokollzeile.

**Geschrieben wird atomar und mit 0600.** Es ist PIs Datei, nicht unsere: sie
wird gelesen, ergänzt und zurückgeschrieben, ohne je etwas anzufassen, das wir
nicht selbst hineingelegt haben. Vor der ersten Änderung entsteht ein
``.bak`` — wer einen Katalog von Hand gebaut hat, soll ihn zurückholen können.

**„lokal" wird an der ADRESSE gemessen, nicht am Namen.** Ein Anbieter darf
heissen, wie er will; ob Eingaben die Maschine verlassen, entscheidet der Host.
"""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import urllib.error
import urllib.parse
import urllib.request

PI_MODELLE = os.path.expanduser("~/.pi/agent/models.json")
OLLAMA_URL = "http://localhost:11434"

# Anbieter, die sich ohne Handarbeit eintragen lassen. Der Schluessel kommt vom
# Menschen; alles andere steht hier, damit niemand eine Basisadresse raten muss.
# ``api`` ist PIs eigenes Vokabular (dieselbe Datei, dieselben Werte).
BEKANNT: dict[str, dict] = {
    "openrouter": {
        "label": "OpenRouter",
        "baseUrl": "https://openrouter.ai/api/v1",
        "api": "openai-completions",
        "modelle_url": "https://openrouter.ai/api/v1/models",
        "schluessel_ab": "https://openrouter.ai/keys",
    },
    "openai": {
        "label": "OpenAI",
        "baseUrl": "https://api.openai.com/v1",
        "api": "openai-completions",
        "modelle_url": "https://api.openai.com/v1/models",
        "schluessel_ab": "https://platform.openai.com/api-keys",
    },
    "anthropic": {
        "label": "Anthropic",
        "baseUrl": "https://api.anthropic.com/v1",
        "api": "anthropic",
        "modelle_url": "https://api.anthropic.com/v1/models",
        "schluessel_ab": "https://console.anthropic.com/settings/keys",
    },
}


def ist_lokal(base_url: str) -> bool:
    """Bleibt dieser Anbieter auf der Maschine? An der Adresse gemessen."""
    try:
        wirt = (urllib.parse.urlsplit(str(base_url or "")).hostname or "").lower()
    except ValueError:
        return False
    return wirt in ("localhost", "127.0.0.1", "::1", "0.0.0.0")


# ── Was Ollama WIRKLICH hat ──────────────────────────────────────────────────

def installiert(url: str = OLLAMA_URL, timeout: float = 4.0) -> tuple[list, str]:
    """Die Modelle, die in Ollama liegen — ``(liste, grund)``.

    Weich: ist Ollama aus, kommt ``([], grund)`` zurueck und der Katalog bleibt
    stehen. Ein leerer Abgleich darf nie dazu fuehren, dass Eintraege
    verschwinden.
    """
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
        return [], f"Ollama nicht erreichbar ({type(e).__name__})"
    aus = []
    for m in d.get("models") or []:
        name = m.get("name") or m.get("model")
        if not name:
            continue
        einz = (m.get("details") or {})
        aus.append({"id": name,
                    "groesse_gb": round((m.get("size") or 0) / 1e9, 1),
                    "digest": (m.get("digest") or "")[:12],
                    "parameter": einz.get("parameter_size") or "",
                    "quant": einz.get("quantization_level") or ""})
    aus.sort(key=lambda m: m["id"])
    return aus, ""


# ── Die Datei ────────────────────────────────────────────────────────────────

def _lies(pfad: str) -> tuple[dict, str]:
    try:
        with open(pfad, encoding="utf-8") as f:
            return (json.load(f) or {}), ""
    except FileNotFoundError:
        return {}, ""                      # noch keine Datei ist kein Fehler
    except (OSError, ValueError) as e:
        return {}, f"{os.path.basename(pfad)} nicht lesbar: {type(e).__name__}"


def _schreibe(pfad: str, d: dict) -> str:
    """Atomar, 0600, mit einmaliger Sicherung. Gibt einen Grund oder ''."""
    try:
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        if os.path.isfile(pfad) and not os.path.isfile(pfad + ".bak"):
            shutil.copy2(pfad, pfad + ".bak")
            os.chmod(pfad + ".bak", stat.S_IRUSR | stat.S_IWUSR)
        griff, tmp = tempfile.mkstemp(dir=os.path.dirname(pfad) or ".",
                                      prefix=".models.", suffix=".json")
        with os.fdopen(griff, "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2, ensure_ascii=False)
            f.write("\n")
        os.chmod(tmp, stat.S_IRUSR | stat.S_IWUSR)      # 0600: da steht ein Schluessel drin
        os.replace(tmp, pfad)
        return ""
    except OSError as e:
        return f"nicht schreibbar: {type(e).__name__}: {e}"


# ── Abgleich und Eintrag ─────────────────────────────────────────────────────

def sync_ollama(pfad: str = "", url: str = OLLAMA_URL,
                trocken: bool = False) -> dict:
    """Was in Ollama liegt, in den Katalog — und was fehlt, benennen.

    ``trocken=True`` schreibt nicht und sagt nur, was geschehen wuerde.
    """
    pfad = pfad or PI_MODELLE
    da, grund = installiert(url)
    if grund:
        return {"ok": False, "grund": grund, "neu": [], "verwaist": []}
    d, grund = _lies(pfad)
    if grund:
        return {"ok": False, "grund": grund, "neu": [], "verwaist": []}

    prov = d.setdefault("providers", {}).setdefault("ollama", {
        "baseUrl": f"{url}/v1", "api": "openai-completions",
        "apiKey": "ollama", "models": []})
    bekannt = {m.get("id") for m in (prov.get("models") or [])}
    vorhanden = {m["id"] for m in da}

    neu = []
    for m in da:
        if m["id"] in bekannt:
            continue
        prov.setdefault("models", []).append({
            "id": m["id"],
            "name": _ollama_name(m),
            "reasoning": True,
            "input": ["text"],
            # Das Kontextfenster steht in /api/tags NICHT. Eine erfundene Zahl
            # waere schlimmer als eine vorsichtige: PI schneidet daran ab.
            "contextWindow": 32768,
            "maxTokens": 8192,
            "cost": {"input": 0, "output": 0, "cacheRead": 0, "cacheWrite": 0},
        })
        neu.append(m["id"])

    verwaist = sorted(bekannt - vorhanden)
    if neu and not trocken:
        s = _schreibe(pfad, d)
        if s:
            return {"ok": False, "grund": s, "neu": [], "verwaist": verwaist}
    return {"ok": True, "grund": "", "neu": sorted(neu), "verwaist": verwaist,
            "gesamt": len(prov.get("models") or [])}


def _ollama_name(m: dict) -> str:
    teile = [t for t in (m.get("parameter"), m.get("quant")) if t]
    zusatz = f" {', '.join(teile)}" if teile else ""
    return f"{m['id']}{zusatz} — lokal, {m.get('groesse_gb', 0)} GB"


def anbieter_setzen(name: str, schluessel: str, modelle: list,
                    pfad: str = "", base_url: str = "", api: str = "") -> dict:
    """Einen API-Anbieter eintragen. Der Schluessel kommt NUR hier herein.

    ``modelle`` ist eine Liste von Modellkennungen oder von
    ``{"id", "name", "contextWindow"}``-Saetzen. Ein leerer Schluessel laesst
    einen vorhandenen stehen (Modelle nachtragen, ohne ihn neu tippen zu
    muessen).
    """
    pfad = pfad or PI_MODELLE
    name = (name or "").strip().lower()
    if not name:
        return {"ok": False, "grund": "kein Anbietername"}
    vor = BEKANNT.get(name, {})
    base_url = base_url or vor.get("baseUrl", "")
    api = api or vor.get("api", "openai-completions")
    if not base_url:
        return {"ok": False, "grund": f"'{name}' ist unbekannt — dann braucht "
                                      f"es eine Basisadresse"}
    if not modelle:
        return {"ok": False, "grund": "kein Modell angegeben — ein Anbieter "
                                      "ohne Modell steht in keiner Auswahl"}

    d, grund = _lies(pfad)
    if grund:
        return {"ok": False, "grund": grund}
    prov = d.setdefault("providers", {}).setdefault(name, {})
    alt_key = prov.get("apiKey", "")
    prov.update({"baseUrl": base_url, "api": api,
                 "apiKey": (schluessel or "").strip() or alt_key})
    if not prov["apiKey"] and not ist_lokal(base_url):
        return {"ok": False, "grund": "ohne Schluessel laesst sich dieser "
                                      "Anbieter nicht ansprechen"}

    haben = {m.get("id"): m for m in (prov.get("models") or [])}
    for m in modelle:
        m = {"id": m} if isinstance(m, str) else dict(m)
        if not m.get("id"):
            continue
        haben[m["id"]] = {
            "id": m["id"],
            "name": m.get("name") or m["id"],
            "reasoning": bool(m.get("reasoning", True)),
            "input": m.get("input") or ["text"],
            "contextWindow": int(m.get("contextWindow") or 128000),
            "maxTokens": int(m.get("maxTokens") or 16000),
            "cost": m.get("cost") or {"input": 1, "output": 1,
                                      "cacheRead": 0, "cacheWrite": 0},
        }
    prov["models"] = [haben[k] for k in sorted(haben)]

    s = _schreibe(pfad, d)
    if s:
        return {"ok": False, "grund": s}
    return {"ok": True, "grund": "", "anbieter": name,
            "modelle": [m["id"] for m in prov["models"]],
            "lokal": ist_lokal(base_url)}


def anbieter_entfernen(name: str, pfad: str = "") -> dict:
    """Einen Anbieter samt Schluessel aus dem Katalog nehmen."""
    pfad = pfad or PI_MODELLE
    d, grund = _lies(pfad)
    if grund:
        return {"ok": False, "grund": grund}
    if (name or "").lower() not in (d.get("providers") or {}):
        return {"ok": False, "grund": f"'{name}' steht nicht im Katalog"}
    d["providers"].pop(name.lower())
    s = _schreibe(pfad, d)
    return {"ok": not s, "grund": s}


# ── Was die Maske anbietet ───────────────────────────────────────────────────

def katalog(pfad: str = "", url: str = OLLAMA_URL,
            pruefe_ollama: bool = True) -> dict:
    """Alle waehlbaren Modelle — mit der Wahrheit daneben.

    Jeder Eintrag traegt ``anbieter``, ``modell``, ``name``, ``lokal``,
    ``schluessel`` (nur ja/nein), ``kostet`` und ``da``: ob das Modell
    tatsaechlich verfuegbar ist. Ein Ollama-Eintrag ohne installiertes Modell
    bekommt ``da=False`` — er wird GEZEIGT und als fehlend benannt, statt
    entweder zu verschwinden oder sich als waehlbar auszugeben.
    """
    pfad = pfad or PI_MODELLE
    d, grund = _lies(pfad)
    if grund:
        return {"ok": False, "modelle": [], "grund": grund, "anbieter": []}

    vorhanden, ollama_grund = (set(), "")
    if pruefe_ollama:
        da, ollama_grund = installiert(url)
        vorhanden = {m["id"] for m in da}

    aus, anbieter = [], []
    for name, p in (d.get("providers") or {}).items():
        lokal = ist_lokal(p.get("baseUrl"))
        anbieter.append({"name": name, "lokal": lokal,
                         "basis": p.get("baseUrl", ""),
                         "api": p.get("api", ""),
                         "schluessel": bool(p.get("apiKey")),
                         "n_modelle": len(p.get("models") or [])})
        for m in (p.get("models") or []):
            kosten = m.get("cost") or {}
            # „da" laesst sich nur fuer das lokale Ollama pruefen; bei einer API
            # hiesse das eine Anfrage samt Schluessel je Maskenaufruf.
            if lokal and name == "ollama" and pruefe_ollama and not ollama_grund:
                da_ = m.get("id") in vorhanden
            else:
                da_ = True
            aus.append({
                "anbieter": name,
                "modell": m.get("id", ""),
                "name": m.get("name") or m.get("id", ""),
                "lokal": lokal,
                "basis": p.get("baseUrl", ""),
                "schluessel": bool(p.get("apiKey")),
                "kostet": bool(kosten.get("input") or kosten.get("output")),
                "kontext": m.get("contextWindow"),
                "da": da_,
            })
    if not aus:
        return {"ok": False, "modelle": [], "anbieter": anbieter,
                "grund": f"in {os.path.basename(pfad)} steht kein Modell"}
    # Erst die lokalen, und Fehlendes ganz nach unten: wer ein API-Modell will,
    # soll es ausdruecklich waehlen statt es versehentlich zu treffen.
    aus.sort(key=lambda m: (not m["da"], not m["lokal"], m["anbieter"],
                            m["modell"]))
    return {"ok": True, "modelle": aus, "anbieter": anbieter,
            "grund": "", "ollama_grund": ollama_grund}


def anbieter_fuer(modell: str, pfad: str = "") -> str:
    """Zu welchem Anbieter gehoert dieses Modell? Vorgabe ``ollama``."""
    for m in katalog(pfad, pruefe_ollama=False).get("modelle") or []:
        if m["modell"] == modell:
            return m["anbieter"]
    return "ollama"


def fremde_modelle(anbieter: str, schluessel: str = "",
                   suche: str = "", timeout: float = 10.0,
                   grenze: int = 60, basis: str = "", api: str = "") -> dict:
    """Die Modellliste eines API-Anbieters holen — zum Auswaehlen, nicht zum Eintragen.

    OpenRouter fuehrt mehrere hundert; alle einzutragen machte den Katalog und
    die Maske unbrauchbar. Deshalb wird gesucht und gedeckelt, und eingetragen
    wird nur, was der Mensch anklickt.
    """
    anbieter = (anbieter or "").strip().lower()
    vor = dict(BEKANNT.get(anbieter) or {})
    if basis:
        # EIGENER Anbieter: die Basisadresse kommt aus der Maske. `/models` ist
        # der OpenAI-Standardpfad, und fast jeder kompatible Dienst bedient ihn
        # -- probiert wird es also, aber es ist ausdruecklich ein Versuch: wer
        # ihn nicht hat, traegt seine Modellkennungen von Hand ein, und dafuer
        # gibt es das Feld daneben.
        vor.setdefault("label", anbieter or "eigener Anbieter")
        vor["api"] = api or vor.get("api") or "openai-completions"
        vor["baseUrl"] = basis
        vor["modelle_url"] = basis.rstrip("/") + "/models"
    if not vor or not vor.get("modelle_url"):
        return {"ok": False, "grund": f"fuer '{anbieter}' ist keine Modell-"
                                      f"Auskunft hinterlegt — die Kennungen "
                                      f"lassen sich von Hand eintragen",
                "modelle": []}
    kopf = {"User-Agent": "cae-orchestrator"}
    if schluessel:
        if vor["api"] == "anthropic":
            kopf["x-api-key"] = schluessel
            kopf["anthropic-version"] = "2023-06-01"
        else:
            kopf["Authorization"] = f"Bearer {schluessel}"
    try:
        req = urllib.request.Request(vor["modelle_url"], headers=kopf)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            d = json.loads(r.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError, TimeoutError) as e:
        return {"ok": False, "modelle": [],
                "grund": f"{vor['label']} antwortet nicht ({type(e).__name__})"}

    roh = d.get("data") if isinstance(d, dict) else d
    aus = []
    for m in roh or []:
        kid = m.get("id") or m.get("name")
        if not kid:
            continue
        preis = m.get("pricing") or {}
        aus.append({
            "id": kid,
            "name": m.get("name") or kid,
            "contextWindow": int(m.get("context_length")
                                 or m.get("max_input_tokens") or 128000),
            "maxTokens": int(((m.get("top_provider") or {}).get("max_completion_tokens"))
                             or m.get("max_tokens") or 16000),
            # OpenRouter rechnet in Dollar je TOKEN; der Katalog fuehrt je
            # Million. Umgerechnet statt uebernommen — sonst stuende in der
            # Maske „kostet nichts" an einem Modell, das Geld kostet.
            "cost": {"input": round(float(preis.get("prompt") or 0) * 1e6, 4),
                     "output": round(float(preis.get("completion") or 0) * 1e6, 4),
                     "cacheRead": 0, "cacheWrite": 0},
        })
    if suche:
        s = suche.lower()
        aus = [m for m in aus if s in m["id"].lower() or s in m["name"].lower()]
    aus.sort(key=lambda m: m["id"])
    return {"ok": True, "grund": "", "anbieter": anbieter,
            "n_gesamt": len(roh or []), "modelle": aus[:grenze]}
