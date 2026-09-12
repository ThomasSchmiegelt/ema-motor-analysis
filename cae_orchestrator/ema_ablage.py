"""Papierkorb — die EINE Loeschstelle.

Geloescht wurde an rund einem Dutzend Stellen, jede fuer sich, jede endgueltig:
``shutil.rmtree(path)`` fuer ein ganzes Projekt, ``os.remove`` fuer einen
Bericht, eine Ansicht, eine Studie, einen gespeicherten 3-D-Lauf. Gefragt hat
dabei **nur die Oberflaeche** — die Routen und die Modulfunktionen fuehrten
aus, was ihnen gesagt wurde. Wer `/project/<id>/delete` mit `curl` traf, einen
Agentenkopf danebenlaufen liess oder eine Kennung vertippte, hatte einen Ordner
mit Wochen an Rechenzeit ohne Rueckfrage und ohne Rueckweg verloren.

Zwei Regeln, und beide sitzen HIER statt in der Oberflaeche:

1. **Ohne ``bestaetigt=True`` passiert nichts.** Der Aufruf gibt dann zurueck,
   WAS entsorgt wuerde und wie gross es ist -- er ist damit zugleich die
   Rueckfrage. Eine Zusicherung in einer Maske ist keine, sobald es einen
   zweiten Weg zur Funktion gibt, und es gibt hier immer einen zweiten Weg
   (CLI, Route, Agentenkopf).
2. **Entsorgt heisst verschoben, nicht vernichtet.** Alles landet unter
   ``<projekt>/.papierkorb/<zeit>/`` (ein ganzes Projekt unter
   ``~/cae_projekte/_papierkorb/``) und laesst sich zurueckholen. Endgueltig
   wird es erst auf ausdruecklichen Zuruf -- und auch der braucht ``bestaetigt``.

Was bewusst NICHT hierher geht: Frame-Ordner, ``blendcache_oil``, das
Elmer-Netz, die Loeserdateien des eigenen Rechensatzes. Das sind
Zwischenstaende, die bei jedem Lauf neu entstehen; sie aufzuheben liesse den
Platz davonlaufen, ohne dass irgendjemand sie je zurueckholte. Still bleiben
sie trotzdem nicht: wo sie geraeumt werden, steht es im Protokoll.

Der Ordner heisst ``.papierkorb`` mit fuehrendem Punkt, damit er nicht als
Bestand mitgezaehlt wird -- dieselbe Ueberlegung wie beim fuehrenden ``_`` von
``~/cae_projekte/_agent_laeufe``, das sonst in jeder Projektliste auftauchte.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil

KORB = ".papierkorb"
PROJEKT_KORB = "_papierkorb"          # fuer ganze Projekte, unter der Wurzel
JOURNAL = "journal.jsonl"


class NichtBestaetigt(RuntimeError):
    """Es wurde nichts geloescht — und das ist der Normalfall, kein Fehler."""

    def __init__(self, bericht: dict):
        super().__init__(bericht.get("text", "nicht bestaetigt"))
        self.bericht = bericht


def _jetzt() -> str:
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]


def _freie_marke(korb: str) -> str:
    """Eine Marke, die es im Korb noch nicht gibt.

    Die Millisekunde reicht nicht: wer zwei Dinge hintereinander entsorgt --
    und das tut schon das Kappen der Berichtsfassungen in EINER Schleife --
    bekommt zweimal dieselbe. Die Ordner kollidieren dabei nicht (verschiedene
    Namen), aber die MARKE ist der Griff, mit dem ``wiederherstellen``
    zurueckholt: bei zwei gleichen erwischt es immer denselben, und das zweite
    liegt unerreichbar im Korb. Dieselbe Absicherung wie in
    ``ema_projekt.knoten_setzen``.
    """
    basis = _jetzt()
    marke, n = basis, 1
    while os.path.exists(os.path.join(korb, marke)):
        n += 1
        marke = "%s-%d" % (basis, n)
    return marke


def _marke_key(marke: str):
    """(Zeitstempel, laufende Nummer) — NICHT die Zeichenkette.

    ``…735_000-2`` sortiert als Text unter ``…735_000``, weil der Bindestrich
    unter dem Unterstrich liegt; dieselbe Falle wie in ``ema_getriebe`` und
    ``ema_bericht``.
    """
    basis, _, rest = str(marke).partition("-")
    try:
        n = int(rest) if rest else 1
    except ValueError:
        n = 1
    return (basis, n)


def _groesse(pfad: str) -> tuple[int, int]:
    """(Bytes, Dateien) — fuer die Rueckfrage. Ein Ordner mit 2 GB Feldnetzen
    ist eine andere Entscheidung als eine 4-kB-JSON."""
    if os.path.isfile(pfad):
        try:
            return os.path.getsize(pfad), 1
        except OSError:
            return 0, 1
    n = b = 0
    for wurzel, _d, dateien in os.walk(pfad):
        for f in dateien:
            n += 1
            try:
                b += os.path.getsize(os.path.join(wurzel, f))
            except OSError:
                pass
    return b, n


def _lesbar(b: int) -> str:
    for e, s in ((1 << 30, "GB"), (1 << 20, "MB"), (1 << 10, "kB")):
        if b >= e:
            return f"{b / e:.1f} {s}"
    return f"{b} B"


def korb_wurzel(project_dir: str) -> str:
    return os.path.join(project_dir, KORB)


def _innerhalb(pfad: str, wurzel: str) -> bool:
    """Liegt ``pfad`` wirklich unter ``wurzel``?

    Geprueft am AUFGELOESTEN Pfad (``realpath``), nicht an der Zeichenkette:
    ``..`` und ein Symlink lassen sich sonst verstecken -- derselbe Grund, aus
    dem ``ema_bericht._rel_ok`` es genauso macht.
    """
    try:
        p = os.path.realpath(pfad)
        w = os.path.realpath(wurzel)
        return p == w or p.startswith(w + os.sep)
    except OSError:
        return False


def _journal(korb: str, eintrag: dict) -> None:
    """Anhaengend — das Journal ist die Liste dessen, was im Korb liegt."""
    try:
        os.makedirs(korb, exist_ok=True)
        with open(os.path.join(korb, JOURNAL), "a", encoding="utf-8") as f:
            f.write(json.dumps(eintrag, ensure_ascii=False) + "\n")
    except OSError:
        pass


def _verlauf(project_dir: str, text: str, action: str = "entsorgt") -> None:
    """Eine Zeile in die EINE Zeitleiste. Soft-fail."""
    try:
        import ema_projekt
        ema_projekt.append_evolution(project_dir, {"action": action, "note": text})
    except Exception:                                        # noqa: BLE001
        pass


# ── entsorgen ─────────────────────────────────────────────────────────────────

def entsorgen(pfad: str, grund: str = "", *, bestaetigt: bool = False,
              project_dir: str | None = None, wurzel: str | None = None) -> dict:
    """Etwas in den Papierkorb legen — **nur mit ``bestaetigt=True``**.

    ``project_dir``  das Projekt, in dessen Korb es geht. Ohne Angabe wird es
                     aus dem Pfad erschlossen (der naechste Ordner mit einer
                     ``project.json`` oberhalb).
    ``wurzel``       Sicherheitsgrenze: ``pfad`` MUSS darunter liegen. Ohne
                     Angabe ist es ``project_dir``.

    Ohne Bestaetigung wird NICHTS angefasst und zurueckgegeben, was geschehen
    WUERDE -- der Aufruf ist damit die Rueckfrage.
    """
    pfad = os.path.abspath(pfad)
    if not os.path.exists(pfad):
        return {"ok": False, "grund": f"nicht vorhanden: {pfad}"}

    project_dir = project_dir or _projekt_ueber(pfad)
    grenze = wurzel or project_dir
    if not grenze:
        return {"ok": False, "grund": "kein Projekt und keine Wurzel angegeben — "
                                      "so wird hier nichts geloescht"}
    if not _innerhalb(pfad, grenze):
        return {"ok": False,
                "grund": f"{pfad} liegt nicht unter {grenze} — abgewiesen"}
    if os.path.realpath(pfad) == os.path.realpath(grenze) and project_dir:
        return {"ok": False, "grund": "das waere die Wurzel selbst — "
                                      "ein ganzes Projekt geht ueber projekt_entsorgen"}

    b, n = _groesse(pfad)
    name = os.path.basename(pfad.rstrip(os.sep))
    was = {"pfad": pfad, "name": name, "bytes": b, "dateien": n,
           "groesse": _lesbar(b), "grund": grund or ""}
    if not bestaetigt:
        return {"ok": False, "bestaetigung_noetig": True, "was": was,
                "text": (f"{name} ({_lesbar(b)}, {n} Datei(en)) wuerde in den "
                         f"Papierkorb gelegt. Nichts ist geschehen. Zum "
                         f"Ausfuehren: bestaetigt=True.")}

    korb = korb_wurzel(project_dir) if project_dir else os.path.join(
        os.path.dirname(grenze), PROJEKT_KORB)
    marke = _freie_marke(korb)
    ziel_ordner = os.path.join(korb, marke)
    try:
        os.makedirs(ziel_ordner, exist_ok=True)
        ziel = os.path.join(ziel_ordner, name)
        shutil.move(pfad, ziel)
    except (OSError, shutil.Error) as e:
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}

    rel = (os.path.relpath(pfad, project_dir) if project_dir else pfad)
    eintrag = {"marke": marke, "ts": datetime.datetime.now().isoformat(timespec="seconds"),
               "name": name, "herkunft": rel, "grund": grund or "",
               "bytes": b, "dateien": n}
    _journal(korb, eintrag)
    if project_dir:
        _verlauf(project_dir,
                 f"{rel} in den Papierkorb ({_lesbar(b)}, {n} Datei(en))"
                 + (f" — {grund}" if grund else ""))
    return {"ok": True, "marke": marke, "korb": ziel_ordner, "was": was}


def projekt_entsorgen(projekt_pfad: str, projekte_wurzel: str, grund: str = "",
                      *, bestaetigt: bool = False) -> dict:
    """Ein GANZES Projekt entsorgen — nach ``<wurzel>/_papierkorb/``.

    Eigene Funktion und nicht ``entsorgen`` mit anderer Wurzel: das ist die
    folgenreichste Loeschung im ganzen Werkzeug (Wochen an Rechenzeit), und sie
    soll nicht dieselbe Signatur tragen wie das Wegwerfen eines Diagramms.
    """
    projekt_pfad = os.path.abspath(projekt_pfad)
    if not os.path.isdir(projekt_pfad):
        return {"ok": False, "grund": f"kein Projektordner: {projekt_pfad}"}
    if not _innerhalb(projekt_pfad, projekte_wurzel):
        return {"ok": False, "grund": f"{projekt_pfad} liegt nicht unter "
                                      f"{projekte_wurzel} — abgewiesen"}
    if os.path.realpath(projekt_pfad) == os.path.realpath(projekte_wurzel):
        return {"ok": False, "grund": "das waere die Projektwurzel selbst"}

    b, n = _groesse(projekt_pfad)
    pid = os.path.basename(projekt_pfad.rstrip(os.sep))
    was = {"pfad": projekt_pfad, "name": pid, "bytes": b, "dateien": n,
           "groesse": _lesbar(b), "grund": grund or ""}
    if not bestaetigt:
        return {"ok": False, "bestaetigung_noetig": True, "was": was,
                "text": (f"Projekt {pid} ({_lesbar(b)}, {n} Datei(en)) wuerde in "
                         f"den Papierkorb gelegt. Nichts ist geschehen. Zum "
                         f"Ausfuehren: bestaetigt=True.")}

    korb = os.path.join(projekte_wurzel, PROJEKT_KORB)
    marke = _freie_marke(korb)
    ziel_ordner = os.path.join(korb, marke)
    try:
        os.makedirs(ziel_ordner, exist_ok=True)
        shutil.move(projekt_pfad, os.path.join(ziel_ordner, pid))
    except (OSError, shutil.Error) as e:
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}
    _journal(korb, {"marke": marke,
                    "ts": datetime.datetime.now().isoformat(timespec="seconds"),
                    "name": pid, "herkunft": projekt_pfad, "grund": grund or "",
                    "bytes": b, "dateien": n, "projekt": True})
    return {"ok": True, "marke": marke, "korb": ziel_ordner, "was": was}


def _projekt_ueber(pfad: str) -> str | None:
    """Der naechste Ordner oberhalb, der eine ``project.json`` traegt."""
    d = pfad if os.path.isdir(pfad) else os.path.dirname(pfad)
    for _ in range(8):
        if os.path.isfile(os.path.join(d, "project.json")):
            return d
        eltern = os.path.dirname(d)
        if eltern == d:
            break
        d = eltern
    return None


# ── nachsehen, zurueckholen, endgueltig ───────────────────────────────────────

def inhalt(project_dir: str) -> list[dict]:
    """Was im Korb liegt, neueste zuerst.

    Gelesen wird das JOURNAL und dann geprueft, ob es die Sache noch gibt —
    wer von Hand im Korb aufraeumt, soll keinen Eintrag sehen, der ins Leere
    zeigt.
    """
    korb = korb_wurzel(project_dir)
    p = os.path.join(korb, JOURNAL)
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
                    e = json.loads(zeile)
                except ValueError:
                    continue
                ziel = os.path.join(korb, e.get("marke", ""), e.get("name", ""))
                e["da"] = os.path.exists(ziel)
                e["im_korb"] = ziel
                e["groesse"] = _lesbar(int(e.get("bytes") or 0))
                aus.append(e)
    except OSError:
        return []
    return sorted(aus, key=lambda e: _marke_key(e.get("marke", "")), reverse=True)


def wiederherstellen(project_dir: str, marke: str) -> dict:
    """Etwas an seinen Herkunftsort zurueckholen.

    Steht dort inzwischen wieder etwas, wird NICHT ueberschrieben — der
    Rueckweg darf nicht selbst zur Loeschung werden. Dann landet es daneben,
    und das wird gesagt.
    """
    treffer = next((e for e in inhalt(project_dir)
                    if e.get("marke") == marke), None)
    if not treffer:
        return {"ok": False, "grund": f"kein Eintrag {marke} im Papierkorb"}
    if not treffer.get("da"):
        return {"ok": False, "grund": f"{treffer['name']} liegt nicht mehr im Korb"}
    quelle = treffer["im_korb"]
    ziel = os.path.join(project_dir, treffer.get("herkunft") or treffer["name"])
    umbenannt = False
    if os.path.exists(ziel):
        ziel = ziel + ".zurueckgeholt_" + marke
        umbenannt = True
    try:
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        shutil.move(quelle, ziel)
    except (OSError, shutil.Error) as e:
        return {"ok": False, "grund": f"{type(e).__name__}: {e}"}
    _verlauf(project_dir, f"{os.path.relpath(ziel, project_dir)} aus dem "
                          f"Papierkorb zurueckgeholt", action="zurueckgeholt")
    return {"ok": True, "pfad": ziel, "umbenannt": umbenannt,
            "hinweis": ("Am Herkunftsort stand schon etwas — zurueckgeholt "
                        "wurde daneben." if umbenannt else "")}


def endgueltig(project_dir: str, marke: str = "", *,
               bestaetigt: bool = False) -> dict:
    """Den Korb (oder einen Eintrag) endgueltig leeren — nur auf Zuruf.

    Auch hier ohne ``bestaetigt`` nichts: dies ist die einzige Stelle im
    ganzen Werkzeug, nach der etwas wirklich weg ist.
    """
    eintraege = [e for e in inhalt(project_dir)
                 if (not marke or e.get("marke") == marke) and e.get("da")]
    b = sum(int(e.get("bytes") or 0) for e in eintraege)
    if not bestaetigt:
        return {"ok": False, "bestaetigung_noetig": True,
                "eintraege": len(eintraege), "bytes": b,
                "text": (f"{len(eintraege)} Eintrag/Eintraege ({_lesbar(b)}) "
                         f"wuerden ENDGUELTIG geloescht. Nichts ist geschehen.")}
    weg = 0
    for e in eintraege:
        ziel = e["im_korb"]
        try:
            if os.path.isdir(ziel):
                shutil.rmtree(ziel)
            else:
                os.remove(ziel)
            weg += 1
        except OSError:
            pass
    _verlauf(project_dir, f"{weg} Eintrag/Eintraege endgueltig geloescht "
                          f"({_lesbar(b)})", action="geloescht")
    return {"ok": True, "geloescht": weg, "bytes": b}


# ── Zwischenstaende: nicht aufheben, aber auch nicht verschweigen ─────────────

def geraeumt(project_dir: str | None, was: str, n: int = 0) -> None:
    """Einen geraeumten ZWISCHENstand protokollieren.

    Frame-Ordner, Blender-Cache, Elmer-Netz: sie entstehen bei jedem Lauf neu
    und gehoeren nicht in den Korb (der Platz liefe davon). Dass sie geraeumt
    wurden, gehoert trotzdem in die Zeitleiste — still bleibt hier nichts.
    """
    if not project_dir:
        return
    _verlauf(project_dir, f"{was} geraeumt" + (f" ({n} Dateien)" if n else ""),
             action="geraeumt")
