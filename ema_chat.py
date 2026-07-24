"""LLM chat over analysis results / variant comparisons.

Thin wrapper around Ollama's /api/chat (model ministral-3:14b, same as the report
generator). The relevant numeric/text result fields are packed into a compact JSON
system prompt — base64 images, animation frames and long numeric arrays are stripped
so the context stays small. There is no LLM in the analysis pipeline; this is purely
a post-hoc Q&A assistant over already-computed results.
"""

import json
import re
import urllib.request

from ema_report import OLLAMA_URL, DEFAULT_MODEL

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)
_MAX_CTX_CHARS = 12000


def _compact(obj, depth: int = 0):
    """Recursively drop base64/image/frame keys and collapse long arrays, so the
    result JSON shrinks from ~1 MB to a few KB of actual numbers/labels."""
    if depth > 6:
        return "…"
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            kl = str(k).lower()
            if any(t in kl for t in ("b64", "png", "image", "frames", "thumb", "_img")):
                continue
            cv = _compact(v, depth + 1)
            if cv is not None and cv != {} and cv != []:
                out[k] = cv
        return out
    if isinstance(obj, str):
        return obj if len(obj) <= 400 else obj[:400] + "…"
    if isinstance(obj, list):
        if len(obj) > 30:
            return f"[{len(obj)} Werte ausgelassen]"
        return [_compact(x, depth + 1) for x in obj]
    return obj


def _clip(s: str) -> str:
    return s if len(s) <= _MAX_CTX_CHARS else s[:_MAX_CTX_CHARS] + "\n…(gekürzt)"


def _ollama_chat(messages, model: str = DEFAULT_MODEL, timeout: int = 300) -> str:
    body = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"temperature": 0.3, "num_ctx": 14336, "num_predict": 2048},
    }).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    raw = (resp.get("message", {}) or {}).get("content", "").strip()
    return _THINK_RE.sub("", raw).strip()


def _conversation(system: str, history, message: str):
    msgs = [{"role": "system", "content": system}]
    for h in (history or [])[-8:]:
        role = h.get("role")
        content = (h.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            msgs.append({"role": role, "content": content})
    msgs.append({"role": "user", "content": message})
    return msgs


def _machine_datasheet(meta: dict) -> str:
    """Per-project 'datasheet': the e-machine's design parameters as a readable spec,
    built deterministically from meta.json (payload geom + materials + run settings).
    Prepended to the chat system prompt so each project's assistant is grounded on its
    OWN machine — the results JSON alone carries outputs, not the input parameters."""
    import ema_report as R
    meta    = meta or {}
    payload = meta.get("payload") or {}
    geom    = payload.get("geom") or meta.get("geom") or {}
    if not geom:
        return ""
    mats = meta.get("materials") or {}
    g    = geom.get
    def _v(x, u=""):
        if x is None:
            return "?"
        if isinstance(x, float):              # tidy float noise (0.7000…028 → 0.7)
            x = round(x, 3)
            if x == int(x):
                x = int(x)
        return f"{x}{u}"
    poles = int(g("p", 0)) * 2 if g("p") is not None else "?"
    topo  = R.TOPOLOGY_LABELS.get(g("magShape", "v"), g("magShape"))
    axial = payload.get("axial_len") or meta.get("axial_len") or g("axialLen")
    notes = str(meta.get("notes") or "").strip()
    notes_line = [f"- Projektnotizen: {notes}"] if notes else []
    return "\n".join(notes_line + [
        "MASCHINEN-DATENBLATT (Auslegungsparameter GENAU DIESES Projekts — als verbindliche Spezifikation behandeln):",
        f"- Bezeichnung: {meta.get('label', '?')}",
        f"- Topologie: {topo} (magShape={g('magShape')})  |  Pole: {poles} (p={g('p')})  |  Nutzahl: {g('slots')}",
        f"- Hauptmaße [mm]: Stator-Außen-Ø={_v(g('statorOD'))}, Stator-Innen-Ø={_v(g('statorID'))}, "
        f"Rotor-Ø={_v(g('rotorOD'))}, Wellen-Ø={_v(g('shaftD'))}, Wellenbohrung={_v(g('shaftBoreD'))}, "
        f"Luftspalt={_v(g('airGap'))}, Blechpaketlänge={_v(axial)}",
        f"- Stator/Wicklung: Nuttiefe={_v(g('slotDepth'))} mm, Leiter/Nut={g('conductorsPerSlot')}, "
        f"Spulenweite={g('coilPitch')} (0=auto), Wickelkopf-Aufweitung={_v(g('windingHeadFlare'))} mm, "
        f"Wickelkopf-Spreizung je Lage={_v(g('windingHeadSpread'))} ° (0=aus)",
        f"- Magnete: Form={g('magShape')}, Maße B/T/Abstand [mm]={_v(g('magWidth'))}/{_v(g('magThick'))}/{_v(g('magDist'))}, "
        f"Lagen={g('magLayers')}, Orientierung={g('magOrient')}, Segmentierung n_ax×n_circ={g('nAx')}×{g('nCirc')}",
        f"- Welle-Nabe-Verbindung: {g('shaftConnection')}",
        f"- Materialien: Rotor-Blech={mats.get('rotor', '?')}, Stator-Blech={mats.get('stator', '?')}, "
        f"Wicklung={mats.get('hairpin', '?')}, Magnet={mats.get('magnet', '?')}",
        f"- Betriebspunkt: Drehzahlbereich {meta.get('rpm_range', '?')}, Lastmoment={_v(payload.get('load_nm'))} Nm, "
        f"Kühlung={meta.get('cooling') or payload.get('cooling', '?')}, "
        f"Umgebungstemperatur={_v(meta.get('T_ambient') if meta.get('T_ambient') is not None else payload.get('T_ambient'))} °C",
    ])


def _rag_doku(message: str, project_dir: str | None = None) -> str:
    """Retrieved documentation snippets for the question, or ''. When ``project_dir`` is
    given, the project's OWN store is queried first then merged with the global base.
    Best effort — works without the knowledge base / Ollama embeddings."""
    try:
        import ema_rag
        if project_dir:
            ctx = ema_rag.context_for_project(message, project_dir, k=4, max_chars=3000)
        else:
            ctx = ema_rag.context_for(message, category=None, k=4, max_chars=3000)
    except Exception:
        return ""
    if not ctx:
        return ""
    return ("TECHNISCHE DOKUMENTATION (aus der Wissensbasis — nutze sie, wenn relevant, "
            "und nenne die Quelle):\n\n" + ctx + "\n\n")


def chat_results(message: str, history, results: dict, meta: dict | None = None,
                 project_dir: str | None = None) -> str:
    """Q&A about a single loaded project's results, grounded on its parameter datasheet.
    ``project_dir`` enables per-project RAG retrieval (own store + global base)."""
    meta = meta or {}
    datasheet = _machine_datasheet(meta)
    geom = (meta.get("payload") or {}).get("geom") or meta.get("geom") \
        or results.get("geom") or {}
    ctx = {
        "summary":      results.get("summary", {}),
        "em_advanced":  results.get("em_advanced", {}),
        "thermal":      _compact(results.get("thermal", {})),
        "struktur_fem": _compact(results.get("structural_fem", {})),
        "drivecycle":   _compact(results.get("drivecycle", {})),
        "geom":         geom,
    }
    ctx = _clip(json.dumps(_compact(ctx), ensure_ascii=False))
    system = (
        "Du bist ein erfahrener Auslegungsingenieur für IPM-Synchronmaschinen und "
        "beantwortest Fragen zu EINEM analysierten Motor.\n\n"
        + (datasheet + "\n\n" if datasheet else "")
        + _rag_doku(message, project_dir)
        + "BERECHNUNGSERGEBNISSE dieses Motors als JSON:\n\n"
        f"{ctx}\n\n"
        "Antworte präzise auf Deutsch und stütze jede Aussage auf konkrete Zahlen aus dem "
        "Datenblatt bzw. den Ergebnissen (mit Einheit). Steht etwas nicht in den Daten, sage "
        "das offen — erfinde keine Werte. Fasse dich kurz und technisch."
    )
    return _ollama_chat(_conversation(system, history, message))


def chat_compare(message: str, history, variants: list) -> str:
    """Q&A about a multi-variant comparison."""
    import ema_report as R
    rows = []
    for v in variants:
        s = v["results"].get("summary", {}) or {}
        g = v["meta"].get("geom", {}) or {}
        rows.append({
            "name": v["meta"].get("label", v["id"]),
            "topologie": R.TOPOLOGY_LABELS.get(g.get("magShape", "v"), g.get("magShape")),
            "B_gap_T": s.get("B_gap_T"), "Kt_Nm_per_A": s.get("Kt_Nm_per_A"),
            "T_maxwell_Nm": s.get("T_maxwell_Nm"), "max_safe_rpm": s.get("max_safe_rpm"),
            "mass_g": s.get("mass_g"), "T_winding_C": s.get("T_winding_C"),
            "T_magnet_C": s.get("T_magnet_C"), "P_total_W": s.get("P_total_W"),
            "verbrauch_kWh100km": s.get("cycle_kWh100km"),
        })
    diff = [r["label"] for r in R._input_param_rows(variants) if r["differ"]]
    ctx = _clip(json.dumps({"varianten": rows, "unterschiedliche_parameter": diff},
                           ensure_ascii=False))
    system = (
        "Du bist ein erfahrener Auslegungsingenieur für IPM-Synchronmaschinen und "
        "vergleichst mehrere Motor-Varianten.\n\n"
        + _rag_doku(message)
        + "Hier die Kennwerte je Variante als JSON (Variante 0 ist die Basis):\n\n"
        f"{ctx}\n\n"
        "Antworte präzise auf Deutsch mit konkreten Zahlen. Erkläre auf Nachfrage kausal, "
        "welche Parameter-Unterschiede welche Kennwert-Unterschiede bewirken. Erfinde keine "
        "Werte; was nicht in den Daten steht, benennst du als unbekannt."
    )
    return _ollama_chat(_conversation(system, history, message))
