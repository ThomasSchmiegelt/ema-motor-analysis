"""Text → EMA: derive an IPM-motor parameter set from a free-text application
description via the local LLM (ministral-3:14b), then validate/clamp it to a safe,
self-consistent geometry. First stage only — no RAG / no web research yet; this is
deliberately a deterministic schema fill so the result always loads into the UI.

The LLM proposes values for the fields in SCHEMA; everything is then clamped to the
allowed range / enum and the radial ordering (statorOD > statorID > rotorOD > shaftD
> shaftBoreD) is enforced, so a sloppy LLM answer can never produce broken geometry.
"""

import json
import re
import urllib.request

from ema_report import OLLAMA_URL, DEFAULT_MODEL

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Allowed enum codes (must match the pipeline tables + UI dropdowns)
_LAM   = ["m250_35a", "m270_35a", "m400_50a", "m800_65a", "steel_s235", "steel_42crmo4"]
_HAIR  = ["cu_etp", "cu_crZr", "cu_ag01", "al_1350"]
_MAG   = ["ndfeb_n35", "ndfeb_n42", "ndfeb_n50", "ferrite"]
_COOL  = ["natural", "forced", "water", "oil"]
_SHAPE = ["v", "vasym", "vv", "u", "delta", "pmasynrm", "spm", "halbach", "spoke", "bar"]

# field → spec. num: (lo, hi, default); enum: options + default.
SCHEMA = {
    "statorOD":   {"kind": "num", "lo": 80,  "hi": 600, "def": 280, "desc": "Stator-Außendurchmesser [mm]"},
    "statorID":   {"kind": "num", "lo": 50,  "hi": 500, "def": 190, "desc": "Stator-Innendurchmesser [mm]"},
    "rotorOD":    {"kind": "num", "lo": 40,  "hi": 498, "def": 188.6, "desc": "Rotor-Außendurchmesser [mm] (< statorID, Luftspalt ~0.7 mm)"},
    "shaftD":     {"kind": "num", "lo": 15,  "hi": 300, "def": 60,  "desc": "Wellendurchmesser [mm]"},
    "shaftBoreD": {"kind": "num", "lo": 0,   "hi": 250, "def": 0,   "desc": "Hohlwellen-Bohrung [mm] (0 = Vollwelle)"},
    "axialLen":   {"kind": "num", "lo": 30,  "hi": 300, "def": 80,  "desc": "Blechpaketlänge [mm]"},
    "slots":      {"kind": "num", "lo": 6,   "hi": 96,  "def": 54,  "desc": "Statornutzahl (Vielfaches von 3, typ. 6·p)", "int": True},
    "slotDepth":  {"kind": "num", "lo": 8,   "hi": 60,  "def": 25,  "desc": "Nuttiefe [mm]"},
    "p":          {"kind": "num", "lo": 1,   "hi": 12,  "def": 3,   "desc": "Polpaarzahl", "int": True},
    "magShape":   {"kind": "enum", "opts": _SHAPE, "def": "v", "desc": "Magnet-Topologie"},
    "magAngle":   {"kind": "num", "lo": 40,  "hi": 170, "def": 120, "desc": "V-Öffnungswinkel [°] (kleiner → mehr Flusskonzentration)"},
    "magDepthRel":{"kind": "num", "lo": 0.4, "hi": 0.92,"def": 0.7, "desc": "radiale Magnetposition (0=Welle … 1=Rotorrand)"},
    "magWidth":   {"kind": "num", "lo": 10,  "hi": 90,  "def": 45,  "desc": "Magnetlänge [mm]"},
    "magThick":   {"kind": "num", "lo": 2,   "hi": 15,  "def": 6,   "desc": "Magnetdicke [mm]"},
    "magDist":    {"kind": "num", "lo": 0,   "hi": 30,  "def": 2,   "desc": "Stegabstand zwischen den Magneten [mm]"},
    "nAx":        {"kind": "num", "lo": 1,   "hi": 12,  "def": 1,   "desc": "Magnet-Segmente axial (Wirbelstromreduktion)", "int": True},
    "nCirc":      {"kind": "num", "lo": 1,   "hi": 6,   "def": 1,   "desc": "Magnet-Segmente in Umfangsrichtung", "int": True},
    "rotor_lam":  {"kind": "enum", "opts": _LAM,  "def": "m270_35a", "desc": "Rotorblech"},
    "stator_lam": {"kind": "enum", "opts": _LAM,  "def": "m270_35a", "desc": "Statorblech"},
    "hairpin_mat":{"kind": "enum", "opts": _HAIR, "def": "cu_etp",   "desc": "Hairpin-Leitermaterial"},
    "magnet":     {"kind": "enum", "opts": _MAG,  "def": "ndfeb_n35","desc": "Magnetwerkstoff"},
    "cooling":    {"kind": "enum", "opts": _COOL, "def": "water",    "desc": "Kühlung"},
    "rpm_from":   {"kind": "num", "lo": 100, "hi": 25000, "def": 5000,  "desc": "Basisdrehzahl / Auslegungsdrehzahl [U/min]"},
    "rpm_to":     {"kind": "num", "lo": 500, "hi": 50000, "def": 20000, "desc": "Maximaldrehzahl [U/min]"},
    "load_nm":    {"kind": "num", "lo": 0,   "hi": 1000,  "def": 120,   "desc": "Auslegungs-Lastmoment [Nm]"},
    "T_ambient":  {"kind": "num", "lo": -40, "hi": 80,    "def": 25,    "desc": "Umgebungstemperatur [°C]"},
}


def _extract_obj(txt: str):
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except Exception:
        return {}


def _validate(raw: dict) -> dict:
    out = {}
    for key, spec in SCHEMA.items():
        v = raw.get(key)
        if spec["kind"] == "enum":
            out[key] = v if v in spec["opts"] else spec["def"]
        else:
            try:
                v = float(v)
            except (TypeError, ValueError):
                v = spec["def"]
            v = max(spec["lo"], min(spec["hi"], v))
            out[key] = int(round(v)) if spec.get("int") else round(v, 3)
    # slots → nearest multiple of 3 (>=6)
    out["slots"] = max(6, int(round(out["slots"] / 3)) * 3)
    # enforce radial ordering statorOD > statorID > rotorOD > shaftD > shaftBoreD
    if out["statorID"] >= out["statorOD"] - 10:
        out["statorID"] = round(out["statorOD"] - 40, 1)
    if out["rotorOD"] >= out["statorID"] - 0.4:
        out["rotorOD"] = round(out["statorID"] - 1.4, 1)        # ~0.7 mm air gap each side
    if out["shaftD"] >= out["rotorOD"] - 5:
        out["shaftD"] = round(out["rotorOD"] * 0.35, 1)
    if out["shaftBoreD"] >= out["shaftD"] - 2:
        out["shaftBoreD"] = 0
    if out["rpm_to"] <= out["rpm_from"]:
        out["rpm_to"] = out["rpm_from"] * 2
    return out


def _prompt(description: str, context: str = "") -> str:
    fields = "\n".join(
        f"  {k}: " + (f"einer von {s['opts']}" if s["kind"] == "enum"
                      else f"Zahl {s['lo']}–{s['hi']}") + f" — {s['desc']}"
        for k, s in SCHEMA.items())
    ref = ""
    if context:
        ref = ("REFERENZMASCHINEN (aus der Wissensbasis — als gut befundene Auslegungen; "
               "orientiere dich an plausiblen Werten, übernimm aber nicht blind):\n"
               f"{context}\n\n")
    return (
        "Du bist ein erfahrener Auslegungsingenieur für Innenpol-PM-Synchronmaschinen "
        "(IPM). Leite aus der folgenden Anwendungsbeschreibung einen sinnvollen, in sich "
        "stimmigen Parametersatz für eine erste Auslegung ab.\n\n"
        f"ANWENDUNG:\n{description}\n\n"
        + ref +
        "FELDER (Schlüssel: erlaubter Bereich/Auswahl — Bedeutung):\n" + fields + "\n\n"
        "Regeln: statorOD > statorID > rotorOD > shaftD; Luftspalt ~0,7 mm "
        "(rotorOD ≈ statorID − 1,4); slots ≈ 6·p; höhere Maximaldrehzahl → kleinerer "
        "Rotordurchmesser (Fliehkraft); hohes Drehmoment → größerer Durchmesser/Länge, "
        "stärkerer Magnet (n42/n50), kleinerer Öffnungswinkel; sparsam/günstig → Ferrit "
        "oder n35. Wähle die Kühlung passend zur Leistungsdichte.\n\n"
        "Antworte NUR mit einem JSON-Objekt: {\"params\": {<alle Felder>}, "
        "\"begruendung\": \"<2–4 Sätze, warum diese Wahl>\"}. Kein weiterer Text."
    )


def derive(description: str, timeout: int = 180) -> dict:
    """Return {params, begruendung, model}. params is always complete + valid."""
    if not (description or "").strip():
        raise ValueError("Leere Beschreibung")
    # RAG: ground the derivation on deposited reference machines (category "maschinen").
    # Best effort — if the knowledge base / Ollama embeddings are unavailable, derive
    # still works without context.
    context = ""
    try:
        import ema_rag
        context = ema_rag.context_for(description, category=None, k=4)
    except Exception:
        context = ""
    body = json.dumps({
        "model": DEFAULT_MODEL,
        "messages": [{"role": "user", "content": _prompt(description, context)}],
        "stream": False,
        "options": {"temperature": 0.4, "num_ctx": 8192, "num_predict": 1200},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    txt = _THINK_RE.sub("", (resp.get("message", {}) or {}).get("content", "")).strip()
    obj = _extract_obj(txt)
    raw = obj.get("params", obj) if isinstance(obj, dict) else {}
    why = obj.get("begruendung") if isinstance(obj, dict) else ""
    if isinstance(why, (dict, list)):
        why = json.dumps(why, ensure_ascii=False)
    return {
        "params":      _validate(raw if isinstance(raw, dict) else {}),
        "begruendung": str(why or ""),
        "model":       DEFAULT_MODEL,
        "rag_used":    bool(context),
    }
