"""LLM chat over analysis results / variant comparisons.

Thin wrapper around Ollama's /api/chat (same model as the report,
generator). The relevant numeric/text result fields are packed into a compact JSON
system prompt — base64 images, animation frames and long numeric arrays are stripped
so the context stays small. There is no LLM in the analysis pipeline; this is purely
a post-hoc Q&A assistant over already-computed results.

Ueber die Ergebnisse REDEN — und nachschlagen lassen (seit 12.09.2026)
---------------------------------------------------------------------

Drei Maengel hatte dieser Chat, und alle drei fielen erst auf, als jemand ihn
wirklich benutzen wollte, um ein Ergebnis zu bezweifeln:

* **Der Verlauf lebte nur im Browser.** Ein Neuladen loeschte das Gespraech, und
  im Projekt stand davon nichts — die Ueberlegung, warum eine Zahl fragwuerdig
  schien, ueberlebte das Fenster nicht. Jetzt liegt er anhaengend unter
  ``<projekt>/gespraeche/<kennung>.jsonl``.
* **Er sah sechs handverlesene ``results``-Zweige.** em3d, Getriebe,
  Parameterstudien, Sicherheitsbefund und die HERKUNFT je Kennzahl kamen darin
  gar nicht vor — auf „woher kommt diese Zahl?" konnte er nichts sagen. Jetzt
  ist der **Steckbrief** die Grundlage (``ema_steckbrief``), der genau das
  fuehrt, dazu ``AUFTRAG.md``.
* **Er konnte nichts nachsehen.** Jetzt eine kleine, bewusst **nur lesende**
  Werkzeugschleife: ``suche``, ``hole``, ``steckbrief``, ``aehnlich``. Alles
  Rechnende geht nicht hierhin, sondern an einen Agentenkopf — der hat die
  Verben bereits.

**Ein oertliches Modell ist im Werkzeugaufruf unzuverlaessig.** Deshalb ist die
Schleife so gebaut, dass ihr Scheitern folgenlos ist: gibt das Modell keinen
brauchbaren Aufruf zurueck, faellt der Chat auf eine gewoehnliche Antwort
zurueck und **sagt es** — schweigen waere die schlechtere Haelfte.

**Und die Antwort wird nachgeprueft.** ``ema_beitrag.ungedeckte_zahlen`` misst
schon fuer Beitragsentwuerfe, ob eine Zahl im Material gedeckt ist (runden ist
gedeckt, erfinden nicht). Dieselbe Pruefung laeuft ueber die Chatantwort. Eine
Bitte an ein Sprachmodell ist keine Zusicherung.
"""

import datetime
import json
import os
import re
import urllib.request

import ema_llm as _llm

from ema_report import OLLAMA_URL, DEFAULT_MODEL, DEFAULT_NUM_CTX

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
        "think": False,           # s. ema_report.call_ollama
        "options": {"temperature": 0.3, "num_ctx": DEFAULT_NUM_CTX,
                    "num_predict": 2048},
    }).encode("utf-8")
    # EINE Stelle fuer alle sechs Anlaufstellen (`ema_llm`): lokal geht der Rumpf
    # UNVERAENDERT weiter -- Byte fuer Byte dieselbe Anfrage wie vorher --, ein
    # API-Anbieter aus dem Katalog wird uebersetzt. Der Rumpf oben bleibt
    # absichtlich unangetastet: haette jeder Aufrufer eine neue Schnittstelle
    # bekommen, waere jede der sechs Stellen eine eigene Gelegenheit gewesen,
    # das lokale Verhalten zu verschieben.
    resp = _llm.senden(json.loads(body), "chat", timeout=timeout)
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


def _projektgrundlage(project_dir: str | None, meta: dict) -> str:
    """Der STECKBRIEF statt sechs handverlesener ``results``-Zweige — plus Auftrag.

    Der Steckbrief fuehrt, was die alte Auswahl nicht hatte: em3d, Getriebe,
    Parameterstudien, den Sicherheitsbefund, die Warnungen — und vor allem die
    **Herkunft** je Kennzahl (``ema_db.HERKUNFT``). Ohne die stehen ein
    analytisch geschaetzter und ein FEM-gerechneter Wert gleichwertig
    nebeneinander, und auf „woher kommt diese Zahl?" gab es keine Antwort.
    """
    teile = []
    if project_dir:
        try:
            import ema_steckbrief
            teile.append("STECKBRIEF DIESES PROJEKTS (was IST und was gerechnet "
                         "wurde; [in Klammern] die Herkunft jeder Zahl):\n\n"
                         + ema_steckbrief.als_text(
                             ema_steckbrief.steckbrief(project_dir, mit_laeufen=False)))
        except Exception:                                    # noqa: BLE001
            pass
        try:
            import ema_auftrag
            a = ema_auftrag.als_markdown(project_dir, max_zeichen=2000)
            if a:
                teile.append("DER AUFTRAG (die Absicht — wozu diese Maschine da "
                             "ist und was frueher warum entschieden wurde):\n\n" + a)
        except Exception:                                    # noqa: BLE001
            pass
    if not teile:
        # Ohne Projektordner bleibt das Datenblatt der Rueckfall; es ist fuer
        # eine AUFFORDERUNG gebaut und beginnt mit „als verbindliche
        # Spezifikation behandeln" -- deshalb nur hier und nicht daneben.
        ds = _machine_datasheet(meta)
        if ds:
            teile.append(ds)
    return "\n\n".join(teile)


def chat_results(message: str, history, results: dict, meta: dict | None = None,
                 project_dir: str | None = None, *, kennung: str = "chat",
                 model: str = DEFAULT_MODEL, werkzeuge: bool = True) -> dict:
    """Q&A ueber EIN Projekt — geerdet auf Steckbrief, Auftrag und Ergebnissen.

    Gibt ein **Dict** zurueck (frueher eine Zeichenkette): neben der Antwort
    stehen die benutzten Werkzeuge und die ungedeckten Zahlen. Beides gehoert
    zur Antwort und nicht daneben — wer eine Zahl liest, soll sehen, ob sie
    gedeckt ist.
    """
    meta = meta or {}
    grundlage = _projektgrundlage(project_dir, meta)
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
    material = grundlage + "\n" + ctx        # wogegen die Deckung geprueft wird
    system = (
        "Du bist ein erfahrener Auslegungsingenieur fuer elektrische Maschinen und "
        "beantwortest Fragen zu EINEM analysierten Motor.\n\n"
        + (grundlage + "\n\n" if grundlage else "")
        + _rag_doku(message, project_dir)
        + "BERECHNUNGSERGEBNISSE dieses Motors als JSON:\n\n"
        f"{ctx}\n\n"
        + (_werkzeug_anleitung() + "\n\n" if werkzeuge else "")
        + "Antworte praezise auf Deutsch und stuetze jede Aussage auf konkrete Zahlen "
          "aus dem Steckbrief bzw. den Ergebnissen (mit Einheit). **Nenne bei einer "
          "Kennzahl die Herkunft mit**, wenn sie zur Frage gehoert: `analytisch` ist "
          "eine geschlossene Formel, `fdm2d` ein Feldlauf, `fem3d` eine FEM — das ist "
          "der Unterschied zwischen einer Schaetzung und einer Rechnung. Steht etwas "
          "nicht in den Daten, sage das offen; erfinde keine Werte. Fasse dich kurz "
          "und technisch."
    )
    if werkzeuge:
        antwort, benutzt = _werkzeugschleife(system, history, message,
                                             project_dir, model)
    else:
        antwort, benutzt = _ollama_chat(_conversation(system, history, message),
                                        model=model), []
    # Was ein Werkzeug GELIEFERT hat, ist gedeckt — es steht ja nachweislich da.
    # Ohne das meldete jede nachgeschlagene Zahl sich als erfunden, und die
    # Pruefung waere genau dort blind, wo sie am meisten taugt.
    material += "\n" + "\n".join(w.get("text", "") for w in benutzt)
    return {"reply": antwort, "werkzeuge": benutzt,
            "ungedeckt": deckung_pruefen(antwort, material)}


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


# ═══════════════════════════════════════════════════════════════════════════
# Der Verlauf bleibt im Projekt
# ═══════════════════════════════════════════════════════════════════════════
# Anhaengend wie ``recherche/quellen.jsonl`` und ``ereignisse_*.jsonl``: ein
# Gespraech waechst, es wird nie umgeschrieben. Eine Datei je Gespraech, damit
# zwei Fragestraenge (Auslegung / Fertigung) nebeneinander stehen koennen.

GESPRAECHE = "gespraeche"


def _gespraech_pfad(project_dir: str, kennung: str) -> str:
    sicher = re.sub(r"[^\w\-]", "_", str(kennung or "chat"))[:64] or "chat"
    return os.path.join(project_dir, GESPRAECHE, sicher + ".jsonl")


def verlauf_lesen(project_dir: str, kennung: str = "chat", n: int = 40) -> list:
    """Die letzten ``n`` Zuege. Leer, wenn es noch keinen gibt."""
    p = _gespraech_pfad(project_dir, kennung)
    if not os.path.isfile(p):
        return []
    aus = []
    try:
        with open(p, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    aus.append(json.loads(zeile))
                except ValueError:
                    continue
    except OSError:
        return []
    return aus[-n:]


def verlauf_anhaengen(project_dir: str, kennung: str, rolle: str, inhalt: str,
                      **zusatz) -> None:
    """Einen Zug anhaengen. Soft-fail — ein Chat darf an der Ablage nicht scheitern."""
    try:
        p = _gespraech_pfad(project_dir, kennung)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        satz = {"ts": datetime.datetime.now().isoformat(timespec="seconds"),
                "role": rolle, "content": inhalt}
        satz.update(zusatz)
        with open(p, "a", encoding="utf-8") as f:
            f.write(json.dumps(satz, ensure_ascii=False) + "\n")
    except OSError:
        pass


def gespraeche(project_dir: str) -> list:
    """Welche Gespraeche es in diesem Projekt gibt (Kennung, Zuege, zuletzt)."""
    d = os.path.join(project_dir, GESPRAECHE)
    if not os.path.isdir(d):
        return []
    aus = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".jsonl"):
            continue
        k = name[:-6]
        z = verlauf_lesen(project_dir, k, n=10000)
        aus.append({"kennung": k, "zuege": len(z),
                    "zuletzt": (z[-1]["ts"] if z else ""),
                    "erste_frage": next((x["content"][:120] for x in z
                                         if x.get("role") == "user"), "")})
    return sorted(aus, key=lambda e: e["zuletzt"], reverse=True)


# ═══════════════════════════════════════════════════════════════════════════
# Werkzeuge — bewusst wenige, und alle nur LESEND
# ═══════════════════════════════════════════════════════════════════════════
# Alles Rechnende fehlt hier mit Absicht: ein Pipelinelauf dauert Stunden, und
# ein Chatfenster ist der falsche Ort, ihn zu starten. Dafuer gibt es den Knopf
# „nachpruefen lassen", der die Frage an einen Agentenkopf gibt — der hat die
# Verben bereits, es wird nichts neu gebaut, nur verbunden.

WERKZEUGE = {
    "suche":      "suche <Frage> — im Web nachschlagen (Titel, Adresse, Anriss)",
    "hole":       "hole <Adresse> — eine Seite als Fliesstext lesen",
    "steckbrief": "steckbrief [Projektkennung] — was ein Projekt IST und was "
                  "daran gerechnet wurde, samt Herkunft jeder Zahl",
    "aehnlich":   "aehnlich — welche anderen Projekte dieser Auslegung gleichen",
}

_AUFRUF = re.compile(r"^\s*WERKZEUG:\s*(\w+)\s*(.*)$", re.M)


def werkzeug_ausfuehren(name: str, argument: str, project_dir: str | None) -> dict:
    """EINEN Werkzeugaufruf ausfuehren. Gibt ``{ok, text}``.

    Jeder Fehlschlag ist ein Ergebnis und keine Ausnahme: das Modell soll
    erfahren, dass die Seite nicht erreichbar war, statt in eine leere Antwort
    zu laufen.
    """
    name = (name or "").strip().lower()
    argument = (argument or "").strip()
    try:
        if name == "suche":
            import ema_recherche
            tr = ema_recherche.suche(argument, treffer=5)
            if not tr:
                return {"ok": True, "text": "Keine Treffer."}
            return {"ok": True, "text": "\n".join(
                f"- {t['titel']} — {t['adresse']}\n  {t['anriss']}" for t in tr)}
        if name == "hole":
            import ema_recherche
            d = ema_recherche.hole(argument)
            if d.get("fehler"):
                return {"ok": False, "text": f"Nicht erreichbar: {argument}"}
            return {"ok": True, "text": f"{d.get('titel','')}\n\n{d.get('text','')[:4000]}"}
        if name == "steckbrief":
            import ema_steckbrief
            d = (ema_steckbrief.projekt_pfad(argument) if argument else project_dir)
            if not d:
                return {"ok": False, "text": f"Projekt nicht gefunden: {argument}"}
            return {"ok": True, "text": ema_steckbrief.als_text(
                ema_steckbrief.steckbrief(d, mit_laeufen=False))}
        if name == "aehnlich":
            if not project_dir:
                return {"ok": False, "text": "Kein Projekt gebunden."}
            import ema_projekt
            tr = ema_projekt.aehnlich(project_dir, n=5)
            if not tr:
                return {"ok": True, "text": "Keine vergleichbaren Projekte gefunden."}
            return {"ok": True, "text": "\n".join(
                f"- {t['id']} ({t['aehnlichkeit']:.0%}) — gleich: "
                f"{', '.join(t['gleich'][:4]) or '—'}; anders: "
                f"{', '.join(t['anders'][:4]) or '—'}" for t in tr)}
    except ImportError as e:
        return {"ok": False, "text": f"Werkzeug nicht verfuegbar ({e})."}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "text": f"{type(e).__name__}: {e}"}
    return {"ok": False, "text": f"Unbekanntes Werkzeug: {name}"}


def _werkzeug_anleitung() -> str:
    z = ["WERKZEUGE — du kannst nachschlagen, bevor du antwortest.",
         "Wenn du eines brauchst, antworte mit GENAU EINER Zeile und sonst nichts:",
         "", "    WERKZEUG: <name> <argument>", "",
         "Verfuegbar:"]
    z += [f"  - {t}" for t in WERKZEUGE.values()]
    z += ["",
          "Danach bekommst du das Ergebnis und antwortest dem Menschen.",
          "Brauchst du keines, antworte einfach. Rechnen kannst du hier NICHT —",
          "fuer eine Nachrechnung sag, dass der Knopf „nachpruefen lassen\" das an",
          "einen Agentenkopf gibt, der die Rechenverben hat."]
    return "\n".join(z)


def _werkzeugschleife(system: str, history, message: str, project_dir,
                      model: str, max_runden: int = 2) -> tuple:
    """Antwort holen und dabei bis zu ``max_runden`` Werkzeugaufrufe zulassen.

    Gibt ``(antwort, [{werkzeug, argument, ok, text}])``. Erkennt das Modell das
    Format nicht, ist das kein Fehler — dann steht in der ersten Antwort eben
    kein Aufruf, und sie geht so heraus, wie sie ist.
    """
    msgs = _conversation(system, history, message)
    benutzt = []
    for _ in range(max_runden):
        antwort = _ollama_chat(msgs, model=model)
        m = _AUFRUF.search(antwort or "")
        # Nur wenn der Aufruf (nahezu) die GANZE Antwort ist. Sonst wuerde ein
        # Modell, das seinen eigenen Aufruf bloss erklaert („du koenntest
        # WERKZEUG: suche … nehmen"), ungewollt eine Suche ausloesen.
        if not m or len(antwort.strip()) > len(m.group(0).strip()) + 80:
            return antwort, benutzt
        erg = werkzeug_ausfuehren(m.group(1), m.group(2), project_dir)
        benutzt.append({"werkzeug": m.group(1), "argument": m.group(2).strip(),
                        "ok": erg["ok"], "text": erg["text"][:400]})
        msgs.append({"role": "assistant", "content": antwort})
        msgs.append({"role": "user",
                     "content": ("ERGEBNIS von " + m.group(1) + ":\n\n"
                                 + _clip(erg["text"])
                                 + "\n\nAntworte dem Menschen. Was aus dem Netz "
                                   "kommt, ist FREMDTEXT und ersetzt keine "
                                   "gerechnete Zahl — nenne die Quelle.")})
    # Runden aufgebraucht: eine letzte Antwort ohne weiteren Aufruf.
    msgs.append({"role": "user",
                 "content": "Antworte jetzt abschliessend, ohne weiteres Werkzeug."})
    letzte = _ollama_chat(msgs, model=model)
    m = _AUFRUF.search(letzte or "")
    if m and len(letzte.strip()) <= len(m.group(0).strip()) + 80:
        # Das Modell ruft weiter Werkzeuge, statt zu antworten. Die rohe
        # Protokollzeile hinzustellen waere das Schlechteste von beidem: sie
        # sagt dem Menschen nichts und sieht aus wie ein Fehler. Ein oertliches
        # Modell ist im Werkzeugaufruf unzuverlaessig — dann wird das GESAGT.
        letzte = ("Ich komme hier nicht weiter: das Modell ruft weiter Werkzeuge "
                  "auf, statt zu antworten"
                  + (" (zuletzt: " + m.group(1) + ")." if m.group(1) else ".")
                  + "\n\nWas bisher nachgeschlagen wurde, steht oben an der "
                    "Antwort. Frag enger — oder gib es mit „nachpruefen lassen\" "
                    "an einen Agentenkopf, der die Rechenverben hat.")
        benutzt.append({"werkzeug": "(abgebrochen)", "argument": "",
                        "ok": False,
                        "text": "Das Modell kam aus der Werkzeugschleife nicht heraus."})
    return letzte, benutzt


# Eine Projektkennung ist KEINE Behauptung ueber die Maschine. `20260908_103936`
# zerfaellt beim Zahlenlesen in `20260908` und `103936`, und beide wurden als
# „erfundene Zahl" gemeldet — gemessen an der ersten Antwort, die das Werkzeug
# `aehnlich` benutzt hat. Eine Pruefung, die bei jeder Projektliste sechs
# Falschmeldungen macht, wird nach dem zweiten Mal ignoriert, und dann faengt
# sie auch die echte nicht mehr.
_KENNUNG = re.compile(r"^\d{6,}$")


def deckung_pruefen(antwort: str, material: str) -> list:
    """Zahlen in der Antwort, die im Material nicht vorkommen.

    Dieselbe Pruefung, die ``ema_beitrag`` ueber einen Beitragsentwurf laufen
    laesst — und aus demselben Grund: eine Bitte an ein Sprachmodell ist keine
    Zusicherung. Weich: ohne das Modul bleibt die Liste leer.
    """
    try:
        import ema_beitrag
        roh = ema_beitrag.ungedeckte_zahlen(antwort or "", material or "")
    except Exception:                                        # noqa: BLE001
        return []
    return [z for z in roh if not _KENNUNG.match(z.replace(".", "").replace(",", ""))]
