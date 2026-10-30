"""Abschnitt „Wie es zu dieser Auslegung kam“ -- aus dem, was das Projekt selbst abgelegt hat.

Der Bericht nannte Eingaben und Ergebnis, nicht den Weg. Der Weg liegt aber vor: die
Projektakte (``project.json``: ``evolution`` mit Aufruf, geaenderten Eingaben und Kennzahlen je
Schritt), die abgelegten Rechnungen (``rechnungen/<zeit>_<verb>.json|txt`` -- Tore, Magnetschluss,
Screening, Entscheidung) und der Auftrag (``AUFTRAG.md``: Ziel, Randbedingungen, Entscheidungen
**mit Gruenden**, offene Punkte). Hier wird das nur zusammengestellt -- ohne Sprachmodell, nichts
erfunden, und was fehlt, steht als fehlend da (aeltere Projekte haben keine Rechnungsablage).
"""
from __future__ import annotations

import json
import os
import re

_PLATZHALTER = "_noch nicht festgehalten_", "_noch keine_"


def _json(pfad: str):
    try:
        with open(pfad, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _abschnitte(pfad: str) -> dict[str, list[str]]:
    """``AUFTRAG.md`` -> {Ueberschrift: Zeilen ohne Platzhalter}."""
    try:
        with open(pfad, encoding="utf-8") as f:
            zeilen = f.read().splitlines()
    except OSError:
        return {}
    aus: dict[str, list[str]] = {}
    kopf = None
    for z in zeilen:
        if z.startswith("## "):
            kopf = z[3:].strip()
            aus[kopf] = []
        elif kopf and z.strip() and z.strip() not in _PLATZHALTER and not z.startswith(">"):
            aus[kopf].append(z.rstrip())
    return {k: v for k, v in aus.items() if v}


def _kopf_ausgang(txt: str) -> str:
    m = re.search(r"^# Ausgang: (.+)$", txt, re.M)
    return m.group(1).strip() if m else ""


def _befund(projekt: str, ref: str) -> tuple[str, list[str]]:
    """(Kurzbefund, Beanstandungen) zu einer abgelegten Rechnung."""
    if not ref:
        return "", []
    basis = os.path.join(projekt, ref)
    stamm, _ = os.path.splitext(basis)
    d = _json(stamm + ".json")
    try:
        with open(stamm + ".txt", encoding="utf-8") as f:
            ausgang = _kopf_ausgang(f.read(4000))
    except OSError:
        ausgang = ""
    verb = os.path.basename(stamm).split("_", 2)[-1]
    probleme: list[str] = []
    if isinstance(d, dict) and "kriterien" in d:
        offen = [k for k in d["kriterien"] if not k.get("ok")]
        hart = [k for k in offen if k.get("schwere") != "hinweis" and k.get("schwere") != "warnung"]
        for k in offen:
            probleme.append(f"{k.get('name')}: {str(k.get('text', ''))[:140]}")
        namen = ", ".join(k["name"] for k in offen)
        if not offen:
            return "alle Kriterien bestanden", []
        return (f"{len(offen)} offen ({namen})" + (f" — {ausgang}" if ausgang else "")), probleme
    if isinstance(d, dict) and "streuanteil" in d:
        return (f"Streuung {d['streuanteil'] * 100:.0f} % — {d.get('stufe')}"
                + (f" ({d.get('grund')})" if d.get("stufe") not in ("ok", None) and d.get("grund") else "")), []
    return ausgang or ("abgelegt" if d is not None else ""), []


def _aenderung(eintrag: dict, erster: bool) -> str:
    ch = eintrag.get("changed_inputs") or {}
    if erster and ch:
        return f"Ausgangsstand ({len(ch)} Eingaben)"
    if not ch:
        return "—"
    teile = [f"{k.replace('geom.', '')}={v}" for k, v in list(ch.items())[:5]]
    mehr = f" (+{len(ch) - 5} weitere)" if len(ch) > 5 else ""
    return ", ".join(teile) + mehr


def entstehung_md(project_dir: str) -> str:
    """Markdown-Abschnitt; leer, wenn das Projekt gar keine Akte hat."""
    akte = _json(os.path.join(project_dir, "project.json"))
    if not isinstance(akte, dict):
        return ""
    z: list[str] = ["## Wie es zu dieser Auslegung kam", ""]

    auftrag = _abschnitte(os.path.join(project_dir, "AUFTRAG.md"))
    design = akte.get("design") or {}
    brief = design.get("brief") or akte.get("notes")
    if brief:
        z += [f"**Aufgabe:** {str(brief).strip()[:600]}", ""]
    for name in ("Ziel", "Randbedingungen", "Entscheidungen", "Offene Punkte"):
        if auftrag.get(name):
            z += [f"**{name}**", ""] + [l if l.lstrip().startswith(("-", "*")) else f"- {l}" for l in auftrag[name]] + [""]
    if not any(auftrag.get(n) for n in ("Ziel", "Randbedingungen", "Entscheidungen")):
        z += ["_Im Auftrag sind weder Ziel noch Entscheidungen festgehalten; die Gründe einzelner "
              "Schritte sind deshalb nicht überliefert._", ""]

    lin = akte.get("lineage") or {}
    if lin.get("parent"):
        z += [f"**Herkunft:** abgeleitet aus Projekt `{lin['parent']}` ({lin.get('origin', '')}).", ""]

    evo = akte.get("evolution") or []
    if evo:
        z += ["**Verlauf** (jeder Schritt mit seinem Befund)", "",
              "| Nr | Zeit | Schritt | Änderung | Befund |", "|---:|---|---|---|---|"]
        probleme: list[str] = []
        for i, e in enumerate(evo, 1):
            ts = str(e.get("ts", ""))[5:16].replace("T", " ")
            schritt = str(e.get("action", "")).replace("cli:", "")
            if e.get("note") and not str(e.get("action", "")).startswith("cli:"):
                schritt += f" — {str(e['note'])[:60]}"
            elif e.get("note"):
                schritt = f"`{str(e['note'])[:70]}`"
            bef, pr = _befund(project_dir, e.get("ref", ""))
            probleme += pr
            km = e.get("key_metrics") or {}
            if km and not bef:
                bef = ", ".join(f"{k}={v}" for k, v in list(km.items())[:3])
            z.append(f"| {i} | {ts} | {schritt.replace('|', '/')} | {_aenderung(e, i == 1).replace('|', '/')} "
                     f"| {bef.replace('|', '/') or '—'} |")
        z.append("")
        if probleme:
            z += ["**Was die Prüfungen beanstandet haben** (und damit die Entscheidung mitbestimmt hat)", ""]
            z += [f"- {p}" for p in dict.fromkeys(probleme)][:12]
            z.append("")
        staende = {str(e.get("werkzeug", "")).split(" ")[0] for e in evo if e.get("werkzeug")}
        if len(staende) > 1:
            z += ["_Achtung: die Schritte stammen aus verschiedenen Werkzeugständen "
                  f"({', '.join(sorted(staende))}); ihre Zahlen sind nicht ohne Weiteres vergleichbar._", ""]
    else:
        z += ["_Für dieses Projekt sind keine Zwischenschritte abgelegt._", ""]

    agent = os.path.join(project_dir, "agent")
    if os.path.isdir(agent):
        laeufe = sorted(f for f in os.listdir(agent) if f.startswith("protokoll_") and f.endswith(".md"))
        if laeufe:
            z += [f"**Agentenläufe:** {len(laeufe)} Protokoll(e) im Projekt (`agent/{laeufe[-1]}` zuletzt) "
                  "— dort steht jeder Werkzeugaufruf mit seinem Ergebnis.", ""]
    return "\n".join(z).rstrip() + "\n"
