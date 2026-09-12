"""AUFTRAG.md — die ABSICHT eines Projekts, fortschreibbar.

Drei Dokumente mit drei Lebensdauern, und keines ersetzt ein anderes:

===========================  ================================  =========================
Datei                        Inhalt                            Lebensdauer
===========================  ================================  =========================
``AGENTS.md`` (Repo)         die **Regeln**                    eine Quelle, nie kopiert
``AGENTS.projekt.md``        die **Fakten** des Laufs          bei jedem Agentenstart neu
``<projekt>/AUFTRAG.md``     die **Absicht**                   waechst, nie ueberschrieben
===========================  ================================  =========================

Die Absicht fehlte. ``design.brief`` ist ein FELD — ein Satz aus der Maske, der im
Steckbrief und im stehenden Auftrag landet; was dagegen NICHT festgehalten wurde, ist
die Begruendung einer Entscheidung („Ferrit statt NdFeB, weil der Preis bindet"), eine
Randbedingung, die der Auftraggeber genannt hat, und was noch offen ist. Genau das
braucht ein Agent beim naechsten Start am meisten, und genau das steht heute allein im
Gespraech — also nirgends.

Entwurfsentscheidungen, jede gegen einen konkreten Fehlerfall:

* **Idempotent wie ``ema_projekt.init``.** ``anlegen`` fasst eine vorhandene Datei
  NICHT an. Sie kann von Hand geschrieben sein, und eine Vorlage darueber waere der
  eine Schreibvorgang, der Text vernichtet, statt welchen hinzuzufuegen.
* **Es gibt kein ``ersetzen``.** ``ergaenzen`` haengt einen datierten Eintrag unter
  seinen Abschnitt. Eine ueberholte Entscheidung wird als ueberholt vermerkt, nicht
  getilgt — warum etwas verworfen wurde, ist selbst eine Auskunft (dieselbe Haltung
  wie ``ema_projekt.zurueck``, das die Geschichte ausdruecklich nicht umschreibt).
* **Abschnitte werden erkannt, nicht gezaehlt.** Wer die Datei von Hand umsortiert
  oder einen eigenen Abschnitt einfuegt, darf das; ``ergaenzen`` sucht die
  Ueberschrift und haengt vor der naechsten an. Ist der Abschnitt nicht da, wird er
  am Ende angelegt statt der Eintrag verworfen.
* **Soft-fail wie ueberall hier**: ein fehlgeschlagener Schreibvorgang darf keinen
  Lauf abbrechen.
"""

from __future__ import annotations

import datetime
import os
import re

DATEI = "AUFTRAG.md"

# Die fuenf Abschnitte. Reihenfolge ist die Lesereihenfolge: erst wohin, dann
# was im Weg steht, dann was entschieden wurde, dann was offen ist.
ABSCHNITTE = [
    ("ziel",            "Ziel"),
    ("randbedingungen", "Randbedingungen"),
    ("entscheidungen",  "Entscheidungen"),
    ("offen",           "Offene Punkte"),
    ("verweise",        "Verweise"),
]
_SCHLUESSEL = {k for k, _ in ABSCHNITTE}
_TITEL = dict(ABSCHNITTE)

# `\s*$` waere hier falsch: mit re.M frisst es die Leerzeilen NACH der
# Ueberschrift mit, und dann steht bei jedem Anhaengen eine Leerzeile mehr da.
_KOPF = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.M)


def pfad(project_dir: str) -> str:
    return os.path.join(project_dir, DATEI)


def _heute() -> str:
    return datetime.datetime.now().strftime("%Y-%m-%d")


def _norm(s: str) -> str:
    """Abschnittsnamen vergleichbar machen (Schluessel ODER Ueberschrift)."""
    return re.sub(r"[^a-z]", "", (s or "").lower()
                  .replace("ä", "a").replace("ö", "o").replace("ü", "u").replace("ß", "ss"))


def _vorlage(titel: str, brief: str, tags) -> str:
    tagz = ", ".join(str(t) for t in (tags or []) if str(t).strip())
    z = [
        f"# Auftrag — {titel}".rstrip(),
        "",
        "> Was dieses Projekt erreichen soll und warum. Dieses Dokument wird",
        "> **ergaenzt, nicht ueberschrieben** — auch von den Agentenkoepfen.",
        "> Die Fakten des Laufs stehen in `project.json`, die Regeln in `AGENTS.md`.",
        "",
        "## Ziel",
        "",
        (brief.strip() if (brief or "").strip() else "_noch nicht festgehalten_"),
        "",
        "## Randbedingungen",
        "",
        (f"Schlagworte: {tagz}" if tagz else "_noch nicht festgehalten_"),
        "",
        "## Entscheidungen",
        "",
        "_noch keine_",
        "",
        "## Offene Punkte",
        "",
        "_noch keine_",
        "",
        "## Verweise",
        "",
        "_noch keine_",
        "",
    ]
    return "\n".join(z)


def anlegen(project_dir: str, titel: str = "", brief: str = "",
            tags=None) -> bool:
    """Die Vorlage schreiben — aber NUR, wenn noch keine Datei da ist.

    Rueckgabe: True, wenn eine Datei entstanden ist; False, wenn schon eine da war
    oder das Schreiben fehlschlug. Soft-fail.
    """
    try:
        p = pfad(project_dir)
        if os.path.exists(p):
            return False
        os.makedirs(project_dir, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(_vorlage(titel or os.path.basename(project_dir.rstrip("/")),
                             brief or "", tags))
        return True
    except Exception:                                        # noqa: BLE001
        return False


def lesen(project_dir: str) -> str:
    """Den ganzen Auftrag als Text. Leer, wenn es keinen gibt."""
    try:
        with open(pfad(project_dir), encoding="utf-8") as f:
            return f.read()
    except Exception:                                        # noqa: BLE001
        return ""


def abschnitte(project_dir: str) -> dict:
    """Die Abschnitte als ``{ueberschrift: rumpf}`` — in Dateireihenfolge.

    Gelesen wird, was DASTEHT, nicht was dastehen sollte: ein von Hand
    eingefuegter Abschnitt erscheint mit.
    """
    txt = lesen(project_dir)
    if not txt:
        return {}
    aus, stellen = {}, list(_KOPF.finditer(txt))
    for i, m in enumerate(stellen):
        ende = stellen[i + 1].start() if i + 1 < len(stellen) else len(txt)
        aus[m.group(1)] = txt[m.end():ende].strip("\n")
    return aus


def ergaenzen(project_dir: str, abschnitt: str, text: str,
              quelle: str = "") -> dict:
    """Einen datierten Eintrag UNTER einen Abschnitt haengen.

    ``abschnitt`` darf der Schluessel (``entscheidungen``) oder die Ueberschrift
    (``Entscheidungen``) sein. Gibt es ihn nicht, wird er am Ende angelegt — ein
    verworfener Eintrag waere schlechter als ein Abschnitt zu viel.
    """
    text = (text or "").strip()
    if not text:
        return {"ok": False, "grund": "kein Text"}
    try:
        p = pfad(project_dir)
        if not os.path.exists(p):
            anlegen(project_dir)
        with open(p, encoding="utf-8") as f:
            txt = f.read()

        # Erst den TITEL bestimmen, dann danach suchen. Ueber den Schluessel
        # gesucht liefe `offen` an der Ueberschrift „Offene Punkte" vorbei und
        # legte einen zweiten, gleichnamigen Abschnitt an (gemessen).
        titel = _TITEL.get(_norm(abschnitt), abschnitt.strip() or "Sonstiges")
        ziel = _norm(titel)

        herkunft = f" ({quelle})" if (quelle or "").strip() else ""
        eintrag = f"- **{_heute()}**{herkunft} — {text}\n"

        stellen = list(_KOPF.finditer(txt))
        treffer = next((i for i, m in enumerate(stellen)
                        if _norm(m.group(1)) == ziel), None)
        if treffer is None:
            # Abschnitt fehlt — hinten anlegen.
            neu = txt.rstrip("\n") + f"\n\n## {titel}\n\n" + eintrag
        else:
            m = stellen[treffer]
            ende = (stellen[treffer + 1].start()
                    if treffer + 1 < len(stellen) else len(txt))
            rumpf = txt[m.end():ende]
            # Platzhalter der Vorlage weicht dem ersten echten Eintrag; alles
            # andere bleibt Zeichen fuer Zeichen stehen.
            gestutzt = re.sub(r"^\s*_noch (?:keine|nicht festgehalten)_\s*$", "",
                              rumpf, flags=re.M)
            gestutzt = gestutzt.strip("\n")
            neuer_rumpf = ("\n\n" + gestutzt + "\n" + eintrag + "\n"
                           if gestutzt else "\n\n" + eintrag + "\n")
            neu = txt[:m.end()] + neuer_rumpf + txt[ende:]

        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(neu)
        os.replace(tmp, p)
        _verlauf(project_dir, titel, text)
        return {"ok": True, "abschnitt": titel}
    except Exception as e:                                   # noqa: BLE001
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}


def _verlauf(project_dir: str, titel: str, text: str) -> None:
    """Eine Zeile in die EINE Zeitleiste (``project.json``s ``evolution``)."""
    try:
        import ema_projekt
        ema_projekt.append_evolution(project_dir, {
            "action": "auftrag",
            "note": f"{titel}: {text[:160]}",
        })
    except Exception:                                        # noqa: BLE001
        pass


def als_markdown(project_dir: str, max_zeichen: int = 4000) -> str:
    """Der Auftrag fuer eine Aufforderung/einen Bericht — gedeckelt.

    Der Deckel ist kein Schoenheitsmass: der Auftrag reist in
    ``AGENTS.projekt.md`` und in Chat-Aufforderungen mit, und ein ueber Monate
    gewachsenes Dokument wuerde dort den Platz fuer die Fakten fressen. Gekuerzt
    wird HINTEN und es wird gesagt.
    """
    txt = lesen(project_dir).strip()
    if not txt:
        return ""
    if len(txt) <= max_zeichen:
        return txt
    return txt[:max_zeichen].rstrip() + "\n\n… (gekuerzt, vollstaendig in AUFTRAG.md)"
