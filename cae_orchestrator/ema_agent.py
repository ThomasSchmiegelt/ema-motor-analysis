"""PI im Browser: links der Agent, rechts was dabei herauskommt.

Wozu
----

``start_agent.sh`` startet PI im Terminal. Das ist zum Arbeiten richtig, taugt aber
nicht zum Zeigen: Bilder kann ein Terminal hier nicht darstellen (weder ``chafa``
noch ``timg`` noch ein Sixel-/Kitty-faehiges TERM sind auf dieser Maschine, und ohne
sudo laesst sich das nicht nachruesten), und einen geteilten Bildschirm gaebe es nur
mit einem Multiplexer -- ``tmux``, ``screen``, ``zellij`` und ``dtach`` fehlen
ebenfalls alle. Der Browser kann beides von Haus aus, und der Server laeuft ohnehin.

Wie PI angesprochen wird
------------------------

``pi --mode rpc``. Das ist ein **zweiseitiges** Protokoll und darum einer Kette von
``pi -p``-Aufrufen vorzuziehen: EIN Prozess haelt die Sitzung, jeder weitere Prompt
ist eine Zeile auf stdin, und das Modell bleibt geladen.

Gemessen und nicht geraten (die Form stand nirgends):

* **hinein** ``{"type":"prompt","message":"..."}``, eine Zeile je Zug.
  ``prompt``/``content``/``text`` als Feldname scheitern mit
  „Cannot read properties of undefined (reading 'startsWith')".
* **heraus** NDJSON. Fuer die linke Spalte zaehlen
  ``assistantMessageEvent.type`` = ``thinking_delta`` / ``text_delta`` /
  ``toolcall_start``; fuer die rechte ``tool_execution_start`` und
  ``tool_execution_end`` (``result.content[].text``, ``isError``).
* **Zugende** ist ``agent_settled`` -- nicht ``turn_end`` und nicht ``agent_end``,
  die kommen davor. Erst danach darf die Eingabe wieder frei sein.

Was hier NICHT passiert
-----------------------

Der Aufseher **fasst den Strom zusammen, er deutet ihn nicht**. Zwei Woerter Antwort
erzeugen 75 ``message_update``-Ereignisse; die roh in den Browser zu schieben waere
verschwenderisch und im Video unleserlich. Umgekehrt wird nichts weggelassen, was
eine Aussage traegt: Werkzeugaufrufe stehen mit ihrem vollen Befehl da, Fehler als
Fehler, und die Ausgabe wird nur laengenbegrenzt, nie stillschweigend geglaettet.

Und: **hier wird nichts gerechnet.** Der Agent ruft ``cae_cli.py`` wie im Terminal;
diese Datei sieht nur zu und reicht durch.
"""

from __future__ import annotations

import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

# PI sortiert Sitzungen nach dem Arbeitsverzeichnis -- derselbe Grund, aus dem
# ``start_agent.sh`` immer aus der Repo-Wurzel startet. Von woanders faende PI
# weder ``AGENTS.md`` noch ``.agents/skills/``, und ``--continue`` griffe in die
# Sitzungen eines fremden Verzeichnisses.
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJEKTE = os.path.expanduser("~/cae_projekte")
# Laeufe ohne Projektbindung: ein eigener Ordner, dessen Name NICHT mit "2"
# beginnt -- sonst taucht er in jeder Projektliste als Projekt auf.
FREIE_LAEUFE = os.path.join(PROJEKTE, "_agent_laeufe")

# Wo npm ohne sudo installiert. ``pi`` liegt hier, nicht in ~/.local/bin.
PI_PFADE = (os.path.expanduser("~/.npm-global/bin"),
            os.path.expanduser("~/.local/bin"))
# Der Nous-Installer legt ``hermes`` nach ~/.local/bin (kein root).
HERMES_PFADE = (os.path.expanduser("~/.local/bin"),
                os.path.expanduser("~/.npm-global/bin"))

# Ringpuffer: damit ein spaet geoeffneter oder neu geladener Browser den Verlauf
# nachbekommt, statt mitten im Satz einzusteigen.
RINGGROESSE = 4000

# Wie viel Text ein einzelnes Werkzeugergebnis in die rechte Spalte traegt. Ein
# ungekuerztes `results`-JSON ist sechsstellig lang und macht die Spalte unlesbar.
MAX_AUSGABE = 4000
MAX_BILDER_JE_ZUG = 12

BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".svg", ".webp")


def _suchen(name: str, pfade) -> str | None:
    umgebung = os.environ.get("PATH", "")
    for p in pfade:
        if os.path.isdir(p):
            umgebung = p + os.pathsep + umgebung
    return shutil.which(name, path=umgebung)


def pi_gefunden() -> str | None:
    """Pfad zu ``pi`` -- oder ``None``, dann sagt die Route es ehrlich."""
    return _suchen("pi", PI_PFADE)


def hermes_gefunden() -> str | None:
    """Pfad zu ``hermes`` -- oder ``None``."""
    return _suchen("hermes", HERMES_PFADE)


# ── Frueheren Laeufen nachgehen ──────────────────────────────────────────────
#
# ``Kopf.sichern()`` schreibt nach JEDEM Zug ein ``protokoll_*.md`` und die
# ``ereignisse_*.jsonl`` -- und bis hierher hat das nie jemand wieder gelesen. Es
# gab keine Route, kein Verb und keinen Knopf, der zurueck in einen alten Lauf
# fuehrt. Fuer den, der davorsitzt, ist "geschrieben, aber unerreichbar" dasselbe
# wie "nicht gespeichert"; genau so wurde es auch berichtet.
#
# Gelesen wird die **JSONL**, nicht die Markdown-Datei: die Markdown ist fuer
# Menschen gesetzt (Ueberschriften, Codebloecke), waehrend die JSONL Ereignis fuer
# Ereignis genau das enthaelt, was der Browser beim ersten Mal verarbeitet hat.
# Aus ihr laesst sich die rechte Spalte Kachel fuer Kachel wieder aufbauen, ohne
# ein zweites Anzeigeverfahren zu schreiben, das mit dem ersten auseinanderlaeuft.

_LAUF_DATEI = re.compile(r"^ereignisse_(\d{8}_\d{6}(?:-\d+)?)\.jsonl$")


def _lauf_lesen_datei(pfad: str) -> list:
    aus = []
    try:
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    aus.append(json.loads(zeile))
                except ValueError:
                    continue          # halbe letzte Zeile nach einem Absturz
    except OSError:
        return []
    return aus


def _lauf_kopfdaten(ereignisse: list) -> dict:
    """Modell, Kopf, Sitzung, Dauer und Umfang -- aus dem Ereignisstrom selbst.

    Nicht aus der Markdown geparst: die ist die abgeleitete Darstellung. Wer die
    Uebersicht aus ihr zoege, muesste ihr Format fuer immer festhalten.
    """
    if not ereignisse:
        return {}
    t0 = ereignisse[0].get("t") or 0.0
    t1 = ereignisse[-1].get("t") or t0
    kopf = {"ereignisse": len(ereignisse),
            "sekunden": round(max(0.0, float(t1) - float(t0)), 1),
            "kacheln": sum(1 for e in ereignisse
                           if e.get("art") in ("ergebnis", "bild")),
            "bilder": sum(1 for e in ereignisse if e.get("art") == "bild"),
            "auftraege": [str(e.get("text", ""))[:160] for e in ereignisse
                          if e.get("art") == "frage"]}
    for e in ereignisse:
        if e.get("art") == "start":
            kopf["kopf"] = e.get("kopf") or ""
            kopf["modell"] = e.get("modell") or ""
            kopf["projekt"] = e.get("projekt") or ""
        elif e.get("art") == "sitzung" and not kopf.get("sitzung"):
            kopf["sitzung"] = e.get("id") or ""
    return kopf


def _lauf_ueberblick(pfad: str) -> dict:
    """Dieselben Kopfdaten, aber OHNE die Datei ganz einzulesen.

    Der Grund ist gemessen: die Mitschrift eines einzigen Laufs vom 04.09. ist
    **9,4 MB mit 140.872 Ereignissen**. Eine Uebersicht, die jeden Lauf jedes
    Projekts vollstaendig durch ``json.loads`` schickt, laedt beim Oeffnen der
    Liste hunderte Megabyte -- fuer eine Tabelle mit fuenf Spalten.

    Darum ein Durchgang Zeile fuer Zeile, und entpackt wird nur, was die Zeile
    ueber ihren Wortlaut schon als interessant ausweist. Der Rest wird gezaehlt.
    """
    daten = {"ereignisse": 0, "kacheln": 0, "bilder": 0, "auftraege": [],
             "kopf": "", "modell": "", "sitzung": "", "sekunden": 0.0}
    erste_t = letzte_t = None
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            for zeile in f:
                if not zeile.strip():
                    continue
                daten["ereignisse"] += 1
                if '"art": "ergebnis"' in zeile:
                    daten["kacheln"] += 1
                elif '"art": "bild"' in zeile:
                    daten["kacheln"] += 1
                    daten["bilder"] += 1
                elif ('"art": "frage"' in zeile or '"art": "start"' in zeile
                        or '"art": "sitzung"' in zeile):
                    try:
                        e = json.loads(zeile)
                    except ValueError:
                        continue
                    art = e.get("art")
                    if art == "frage":
                        daten["auftraege"].append(str(e.get("text", ""))[:160])
                    elif art == "start":
                        daten["kopf"] = e.get("kopf") or ""
                        daten["modell"] = e.get("modell") or ""
                        daten["projekt"] = e.get("projekt") or ""
                    elif art == "sitzung" and not daten["sitzung"]:
                        daten["sitzung"] = e.get("id") or ""
                # Die Zeitmarke ohne Entpacken: sie steht als ``"t": …`` in jeder
                # Zeile, und der Schnitt darauf ist ein Vielfaches billiger als
                # das Auspacken des ganzen Satzes.
                k = zeile.find('"t":')
                if k >= 0:
                    try:
                        letzte_t = float(zeile[k + 4:].split(",")[0].strip("} \n"))
                        if erste_t is None:
                            erste_t = letzte_t
                    except ValueError:
                        pass
    except OSError:
        return daten
    if erste_t is not None and letzte_t is not None:
        daten["sekunden"] = round(max(0.0, letzte_t - erste_t), 1)
    return daten


def laeufe_im_ordner(ordner: str, projekt: str = "") -> list:
    """Die Laeufe eines ``agent/``-Ordners, neueste zuerst."""
    if not os.path.isdir(ordner):
        return []
    aus = []
    for name in sorted(os.listdir(ordner), reverse=True):
        m = _LAUF_DATEI.match(name)
        if not m:
            continue
        marke = m.group(1)
        pfad = os.path.join(ordner, name)
        eintrag = {"marke": marke, "projekt": projekt, "ordner": ordner,
                   "jsonl": pfad, "bytes": os.path.getsize(pfad),
                   "protokoll": os.path.join(ordner, f"protokoll_{marke}.md")
                   if os.path.isfile(os.path.join(ordner, f"protokoll_{marke}.md"))
                   else "",
                   "kopf": "", "modell": "", "sitzung": ""}
        eintrag.update(_lauf_ueberblick(pfad))
        eintrag["projekt"] = projekt or eintrag.get("projekt") or ""
        aus.append(eintrag)
    return aus


def laeufe_liste(max_n: int = 60) -> list:
    """Alle Agentenlaeufe -- die projektgebundenen UND die freien.

    Die freien tragen ``projekt: ""``. Sie gehen sonst verloren: wer ohne
    Bindung startet, um etwas Neues zu entwerfen, macht dabei oft gerade die
    Rechnung, auf die er spaeter zurueckkommen will.
    """
    aus = []
    try:
        eintraege = os.listdir(PROJEKTE)
    except OSError:
        return []
    for name in eintraege:
        if name.startswith("_"):
            continue
        aus += laeufe_im_ordner(os.path.join(PROJEKTE, name, "agent"), name)
    if os.path.isdir(FREIE_LAEUFE):
        for name in os.listdir(FREIE_LAEUFE):
            aus += laeufe_im_ordner(os.path.join(FREIE_LAEUFE, name), "")
    aus.sort(key=lambda e: e["marke"], reverse=True)
    return aus[:max_n]


def lauf_lesen(projekt: str, marke: str,
               max_ereignisse: int = RINGGROESSE) -> dict:
    """Einen einzelnen Lauf zurueckholen -- Kopfdaten und Ereignisse.

    ``projekt`` und ``marke`` werden gegen die Formen geprueft, die sie haben
    duerfen, und der fertige Pfad muss unter ``PROJEKTE`` liegen. Sonst waere
    dies eine Route, die jede Datei des Rechners ausliefert: die Kennungen kommen
    aus einer URL.
    """
    if not re.fullmatch(r"\d{8}_\d{6}(?:-\d+)?", str(marke or "")):
        return {"ok": False, "grund": "unzulaessige Laufkennung"}
    if projekt and not re.fullmatch(r"[A-Za-z0-9_.-]{1,120}", str(projekt)):
        return {"ok": False, "grund": "unzulaessige Projektkennung"}
    ordner = (os.path.join(PROJEKTE, projekt, "agent") if projekt
              else os.path.join(FREIE_LAEUFE, marke))
    ordner = os.path.realpath(ordner)
    if not ordner.startswith(os.path.realpath(PROJEKTE) + os.sep):
        return {"ok": False, "grund": "Pfad ausserhalb der Projektablage"}
    pfad = os.path.join(ordner, f"ereignisse_{marke}.jsonl")
    if not os.path.isfile(pfad):
        return {"ok": False, "grund": f"Kein Lauf {marke} in {ordner}"}
    ereignisse = _lauf_lesen_datei(pfad)
    md = os.path.join(ordner, f"protokoll_{marke}.md")
    # Gedeckelt wie der laufende Strom. Ein Lauf mit 140.872 Ereignissen -- so
    # einer liegt hier -- waere als eine JSON-Antwort 9 MB, und der Browser baute
    # daraus 140.872 Knoten, waehrend er denselben Verlauf im laufenden Betrieb
    # auf RINGGROESSE beschneidet. Beschnitten wird VORNE: das Ende eines Laufs
    # ist das, worauf man zurueckkommt.
    voll = len(ereignisse)
    if max_ereignisse and voll > max_ereignisse:
        ereignisse = ereignisse[-max_ereignisse:]
    return {"ok": True, "marke": marke, "projekt": projekt, "ordner": ordner,
            "protokoll": md if os.path.isfile(md) else "",
            **_lauf_kopfdaten(ereignisse),
            "ereignisse": voll, "gekuerzt": voll > len(ereignisse),
            "ereignisse_liste": ereignisse}


def _umgebung(pfade=PI_PFADE) -> dict:
    env = dict(os.environ)
    zusatz = [p for p in pfade if os.path.isdir(p)]
    env["PATH"] = os.pathsep.join(zusatz + [env.get("PATH", "")])
    return env


class Kopf:
    """Ein laufender Agentenprozess samt Ereignisstrom -- ohne sein Protokoll.

    Hier steht alles, was BEIDE Agentenkoepfe gleich machen: Ringpuffer und
    anhaengende Mitschrift, neue Bilder aus dem Projektordner, Protokoll,
    Zielordner, Zwischenrufe, Projektakte, Zustand. Was sich unterscheidet --
    Aufrufform, Drahtprotokoll, Sitzungsliste -- steht in den beiden
    Unterklassen ``PiKopf`` und ``HermesKopf``, jede an EINER Stelle.

    Der Grund fuer diese Aufteilung ist derselbe wie beim Skill: PI und Hermes
    lesen EINE ``SKILL.md``, keine Kopie. Eine zweite ``ema_agent.py`` fuer
    Hermes waere anfangs identisch und nach dem dritten Fehlerbericht nicht mehr
    -- und dann verhalten sich zwei Reiter unterschiedlich, ohne dass jemand
    sagen koennte, warum.

    Bewusst EIN Lauf je Kopf (wie die uebrigen Zustands-Dicts in ``server.py``):
    zwei gleichzeitige Agenten desselben Kopfes wuerden sich um dasselbe
    Projektverzeichnis und denselben Ollama-Speicher streiten, und im Video will
    man ohnehin einen.
    """

    NAME = "?"                 # Kennung in Routen und Oberflaeche
    LABEL = "?"                # Klartext fuer den Menschen
    PFADE = PI_PFADE           # wo das Programm gesucht wird
    KANN_SYSTEMZUSATZ = True   # eigener Systemzusatz beim Aufruf moeglich?

    # ── Was die Unterklassen ausfuellen ─────────────────────────────────────
    def programm(self) -> str | None:
        raise NotImplementedError

    def _fehlt_text(self) -> str:
        raise NotImplementedError

    def _befehl(self, prog: str, modell: str, sitzung: str,
                system_zusatz: str) -> list:
        raise NotImplementedError

    def _stderr_ziel(self):
        """PI mischt seine Klartextzeilen in stdout; Hermes schreibt dorthin
        reines JSON-RPC und seine Protokollzeilen nach stderr. Wer das
        zusammenlegt, zerschiesst bei Hermes den Strom."""
        return subprocess.STDOUT

    def _nach_start(self, modell: str, sitzung: str, system_zusatz: str) -> dict:
        """Nach dem Aufruf, vor der ersten Frage. PI ist sofort bereit; ACP
        braucht erst ``initialize`` und ``session/new``."""
        return {"ok": True}

    def _lesen(self) -> None:
        raise NotImplementedError

    def _prompt_senden(self, text: str) -> None:
        raise NotImplementedError

    def sitzungen(self, n: int = 8) -> list:
        return []

    def _umfeld(self) -> dict:
        return _umgebung(self.PFADE)

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.ring: list = []
        self.hoerer: list = []            # offene Browser-Stroeme
        self.sperre = threading.Lock()
        self.laeuft = False
        self.beschaeftigt = False         # zwischen Prompt und agent_settled
        self.projekt = ""
        self.modell = ""
        self.sitzung = ""
        self.start_ts = 0.0
        self._bild_marke = 0.0
        self._gesehen: set = set()
        self._offen: list = []            # vom Deckel zurueckgehaltene Bilder
        self.hinweise: list = []          # Zwischenrufe, die auf ihren Zug warten
        self.fehler = ""
        self._nr = 0                      # fortlaufend, UNABHAENGIG vom Ring
        self.ordner = ""                  # steht mit dem Start fest
        self._ordner_fuer = None          # fuer welches Projekt er gilt
        self._mit = None                  # offene Mitschrift (ereignisse.jsonl)

    # ── Ereignisse verteilen ────────────────────────────────────────────────
    def _sende(self, art: str, **felder) -> None:
        with self.sperre:
            # Die Nummer zaehlt DURCH und ist nicht die Stelle im Ring: sobald der
            # Ring das erste Mal ueberlaeuft, waere die Stelle nicht mehr eindeutig,
            # und ein wieder anknuepfender Browser bekaeme mit ``?ab=`` entweder
            # dasselbe zweimal oder ein Loch.
            self._nr += 1
            satz = {"i": self._nr, "art": art, "t": round(time.time(), 3), **felder}
            self.ring.append(satz)
            if len(self.ring) > RINGGROESSE:
                del self.ring[:len(self.ring) - RINGGROESSE]
            self._mitschreiben(satz)
            tot = []
            for q in self.hoerer:
                try:
                    q.put_nowait(satz)
                except queue.Full:
                    tot.append(q)
            for q in tot:
                self.hoerer.remove(q)

    def anmelden(self, ab: int = 0) -> queue.Queue:
        q: queue.Queue = queue.Queue(maxsize=8000)
        with self.sperre:
            for satz in (x for x in self.ring if x["i"] > ab):
                try:
                    q.put_nowait(satz)
                except queue.Full:
                    break
            self.hoerer.append(q)
        return q

    def abmelden(self, q: queue.Queue) -> None:
        with self.sperre:
            if q in self.hoerer:
                self.hoerer.remove(q)

    # ── Neue Bilder finden ──────────────────────────────────────────────────
    def _neue_bilder(self, alle: bool = False) -> list:
        """Bilder, die seit der letzten Schau entstanden oder sich geaendert haben.

        Ueber die Datei-Aenderungszeit und nicht ueber den Werkzeugausgabetext:
        welche Bilder ein Lauf erzeugt, steht dort naemlich gar nicht drin -- die
        Pipeline schreibt sie nebenbei nach ``charts/`` und ``cad_images/``. Wer
        sie aus dem Text klauben wollte, muesste jede Stufe einzeln kennen.
        """
        aus = []
        try:
            for pid in os.listdir(PROJEKTE):
                pdir = os.path.join(PROJEKTE, pid)
                if not os.path.isdir(pdir) or pid.startswith("_"):
                    continue
                for unter in ("charts", "cad_images"):
                    d = os.path.join(pdir, unter)
                    if not os.path.isdir(d):
                        continue
                    for name in os.listdir(d):
                        if not name.lower().endswith(BILD_ENDUNGEN):
                            continue
                        voll = os.path.join(d, name)
                        try:
                            mt = os.path.getmtime(voll)
                        except OSError:
                            continue
                        if mt <= self._bild_marke:
                            continue
                        schluessel = (voll, round(mt, 2))
                        if schluessel in self._gesehen:
                            continue
                        self._gesehen.add(schluessel)
                        aus.append({"projekt": pid, "unter": unter,
                                    "datei": name, "mtime": mt})
        except OSError:
            aus = []
        # Der Deckel begrenzt, wie viele Bilder AUF EINMAL nach rechts gehen --
        # er darf sie nicht verschlucken. Vorher wurden die aeltesten
        # weggeschnitten und waren damit endgueltig weg: die Marke ruecke ueber
        # sie hinweg, und ``_gesehen`` haelt sie ohnehin fuer erledigt. Eine
        # fertige Pipeline schreibt ihre Diagramme in wenigen Sekunden -- genau
        # der Fall, in dem der Deckel greift.
        aus = self._offen + aus
        aus.sort(key=lambda b: b["mtime"])
        if alle or len(aus) <= MAX_BILDER_JE_ZUG:
            self._offen = []
            return aus
        self._offen = aus[MAX_BILDER_JE_ZUG:]
        return aus[:MAX_BILDER_JE_ZUG]

    def _neue_rechnungen(self) -> list:
        """Abgelegte Verbergebnisse, die seit der letzten Schau entstanden sind.

        Der zweite Weg in die rechte Spalte -- und der belastbarere.

        Der erste Weg fuehrt ueber den Agentenkopf: er meldet sein
        Werkzeugergebnis, wir zeigen es. Bei Hermes ist dieser Weg **gemessen
        unterbrochen**: ruft er in einem Zug MEHRERE Werkzeuge auf, schickt
        ``hermes acp`` zwar je ein ``tool_call``, aber **kein einziges**
        ``tool_call_update`` -- die Ergebnisse kommen beim Klienten nie an.
        Nachgestellt am 04.09. mit ``hermes acp`` v0.20.5: ein Werkzeug im Zug ->
        ``tool_call`` UND ``tool_call_update {status: completed}``; drei
        Werkzeuge im Zug -> drei ``tool_call``, null Updates. Der Lauf vom
        selben Tag zeigt genau das: 1.562 Ereignisse, 3 Werkzeugaufrufe, 0
        Ergebnisse, rechte Spalte leer.

        Der zweite Weg geht nicht ueber den Kopf, sondern ueber die **Platte**:
        was ``cae_cli.py`` in ``<projekt>/rechnungen/`` ablegt, wird hier
        gefunden -- genau wie die Bilder in ``charts/``. Damit haengt das, was
        der Betrachter sieht, nicht mehr daran, ob ein Agentenprogramm sein
        Ergebnis korrekt meldet. Es haengt daran, ob gerechnet wurde.
        """
        aus = []
        try:
            for pid in os.listdir(PROJEKTE):
                d = os.path.join(PROJEKTE, pid, "rechnungen")
                if pid.startswith("_") or not os.path.isdir(d):
                    continue
                for name in os.listdir(d):
                    if not name.endswith(".txt"):
                        continue
                    voll = os.path.join(d, name)
                    try:
                        mt = os.path.getmtime(voll)
                    except OSError:
                        continue
                    if mt <= self._bild_marke:
                        continue
                    schluessel = (voll, round(mt, 2))
                    if schluessel in self._gesehen:
                        continue
                    self._gesehen.add(schluessel)
                    aus.append({"projekt": pid, "datei": name, "pfad": voll,
                                "mtime": mt})
        except OSError:
            return []
        aus.sort(key=lambda r: r["mtime"])
        return aus

    def _rechnungen_melden(self) -> None:
        for r in self._neue_rechnungen():
            try:
                with open(r["pfad"], encoding="utf-8") as f:
                    roh = f.read()
            except OSError:
                continue
            # Der Kopf der Datei (``# verb — Zeitpunkt``) steht schon in der
            # Kachelzeile; im Rumpf waere er nur doppelt.
            text = "\n".join(z for z in roh.splitlines()
                              if not z.startswith("#")).strip()
            verb = r["datei"].split("_", 2)[-1][:-4]
            self._sende("ergebnis", name=verb, fehler="ABGELEHNT" in roh
                        or "verletzt" in roh.split("\n\n")[0],
                        text=text[:MAX_AUSGABE],
                        gekuerzt=len(text) > MAX_AUSGABE, voll=len(text),
                        ablage=os.path.join(r["projekt"], "rechnungen",
                                            r["datei"]))
            self._bild_marke = max(self._bild_marke, r["mtime"])

    def _bilder_melden(self, alle: bool = False) -> None:
        neue = self._neue_bilder(alle=alle)
        self._bild_marke = max([b["mtime"] for b in neue] + [self._bild_marke])
        for b in neue:
            self._sende("bild", projekt=b["projekt"], unter=b["unter"],
                        datei=b["datei"])

    # ── Der Lesefaden ───────────────────────────────────────────────────────
    # ── Steuerung ───────────────────────────────────────────────────────────
    def starten(self, modell: str, projekt: str = "", sitzung: str = "",
                system_zusatz: str = "") -> dict:
        if self.laeuft:
            return {"ok": False, "grund": f"Es laeuft bereits ein {self.LABEL}."}
        prog = self.programm()
        if not prog:
            return {"ok": False, "grund": self._fehlt_text()}

        self.ring = []
        self._gesehen = set()
        self._bild_marke = time.time()
        self.fehler = ""
        self.projekt = projekt
        self.modell = modell
        self.sitzung = "" if sitzung in ("", "weiter") else sitzung
        self.start_ts = time.time()
        # Der Ordner steht mit dem Start fest, und die Projektakte wird VOR dem
        # Aufruf geschrieben: Hermes liest sie beim Hochfahren aus dem
        # Arbeitsverzeichnis, und was danach entstuende, saehe er nicht mehr.
        self.ordner = ""
        self._ordner_fuer = None
        self._nr = 0
        ordner = self.zielordner()
        self._mitschrift_schliessen()
        self._mitschrift_oeffnen()
        akte = self.projektakte_schreiben(system_zusatz)

        befehl = self._befehl(prog, modell, sitzung, system_zusatz)
        try:
            self.proc = subprocess.Popen(
                befehl, cwd=WURZEL, env=self._umfeld(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=self._stderr_ziel(), text=True, bufsize=1)
        except OSError as e:
            self.fehler = f"{type(e).__name__}: {e}"
            return {"ok": False, "grund": self.fehler}
        self.laeuft = True
        threading.Thread(target=self._lesen, daemon=True).start()
        self._sende("start", modell=modell, projekt=projekt, kopf=self.NAME,
                    befehl=" ".join(befehl), ordner=ordner, akte=akte)
        bereit = self._nach_start(modell, sitzung, system_zusatz)
        if not bereit.get("ok"):
            self.fehler = str(bereit.get("grund", ""))
            self._sende("fehler", text=self.fehler[:400])
            self.stoppen()
            return bereit
        return {"ok": True, "modell": modell, "projekt": projekt,
                "kopf": self.NAME, "ordner": ordner}

    def fragen(self, text: str) -> dict:
        if not self.laeuft or not self.proc or not self.proc.stdin:
            return {"ok": False, "grund": "Es laeuft kein Agent."}
        if self.beschaeftigt:
            return {"ok": False, "grund": "Der Agent arbeitet noch."}
        self.beschaeftigt = True
        self._sende("frage", text=text)
        try:
            self._prompt_senden(text)
        except (BrokenPipeError, OSError) as e:
            self.beschaeftigt = False
            return {"ok": False, "grund": f"{type(e).__name__}: {e}"}
        return {"ok": True}

    def stoppen(self) -> dict:
        if not self.proc:
            return {"ok": True}
        try:
            self.proc.terminate()
            self.proc.wait(timeout=5)
        except Exception:                                    # noqa: BLE001
            try:
                self.proc.kill()
            except Exception:                                # noqa: BLE001
                pass
        self.laeuft = False
        self.beschaeftigt = False
        self._sichern_still()
        self._mitschrift_schliessen()
        return {"ok": True}

    # ── Zwischenrufe waehrend eines Zuges ───────────────────────────────────
    #
    # PI nimmt waehrend eines laufenden Zuges keinen zweiten Prompt an -- ``fragen``
    # weist das ab, und das ist richtig so. Wer aber zusieht, wie der Agent zwanzig
    # Minuten in eine Richtung laeuft, die er nicht will, soll das SAGEN koennen,
    # ohne den Lauf abzubrechen und ohne den Moment abzupassen, in dem der Zug
    # endet. Der Zwischenruf wird deshalb gemerkt und am naechsten Zugende von
    # selbst uebergeben. Gesammelt, nicht einzeln: drei Rufe waehrend eines Zuges
    # sind ein Gedanke, keine drei Auftraege.
    def merken(self, text: str) -> dict:
        text = str(text).strip()
        if not text:
            return {"ok": False, "grund": "leerer Hinweis"}
        if not self.laeuft:
            return {"ok": False, "grund": "Es laeuft kein Agent."}
        if not self.beschaeftigt:
            return self.fragen(text)      # der Agent wartet ohnehin -- direkt hin
        with self.sperre:
            self.hinweise.append(text)
            wieviele = len(self.hinweise)
        self._sende("gemerkt", text=text, offen=wieviele)
        return {"ok": True, "gemerkt": True, "offen": wieviele}

    def _hinweise_uebergeben(self) -> None:
        with self.sperre:
            offen, self.hinweise = self.hinweise, []
        if not offen:
            return
        text = ("Zwischenruf waehrend des letzten Zuges (vom Menschen, hoeher "
                "gewichtet als der urspruengliche Auftrag):\n"
                + "\n".join(f"- {t}" for t in offen))
        self.fragen(text)

    # ── Den Lauf auf die Platte ─────────────────────────────────────────────
    def projektakte_schreiben(self, system_zusatz: str = "") -> str:
        """``AGENTS.projekt.md`` in der Repo-Wurzel neu schreiben.

        Warum das hier stehen MUSS -- gemessener Befund
        ------------------------------------------------

        PI liest beim Start ``AGENTS.md`` UND ``AGENTS.projekt.md`` aus dem
        Arbeitsverzeichnis. Geschrieben hat die zweite Datei bisher **nur**
        ``start_agent.sh``, und auch das nur, **wenn ein Projekt gebunden war**.
        Daraus folgten zwei Wege, auf denen ein Agent an einem alten Entwurf
        haengen blieb, ohne dass irgendetwas widersprach:

        * **Der Browser-Agent schrieb sie nie.** Jeder Lauf ueber ``/agent``
          las, was der Terminalkopf zuletzt hinterlassen hatte -- gemessen am
          03.09. ein Flugzeugantrieb vom 02.09., ueberschrieben mit
          „Aktuelles Projekt".
        * **Ohne Bindung blieb die alte Datei liegen.** Wer ausdruecklich OHNE
          Projekt startete, um etwas Neues zu entwerfen, bekam die alte Akte als
          seine eigene serviert.

        Eine Datei, die „Aktuelles Projekt" ueberschrieben ist und ein zwei Tage
        altes Fremdprojekt beschreibt, ist schlimmer als gar keine: das Modell
        hat keinen Anlass, an ihr zu zweifeln. Deshalb wird sie bei JEDEM Start
        geschrieben -- auch, und gerade, wenn es kein Projekt gibt.
        """
        pfad = os.path.join(WURZEL, "AGENTS.projekt.md")
        kopf = ["# Aktuelles Projekt — ERZEUGT beim Agentenstart, nicht von Hand aendern",
                "",
                "Diese Datei wird bei JEDEM Agentenstart neu geschrieben — auch wenn",
                "kein Projekt gebunden ist. Die Regeln stehen in AGENTS.md; hier stehen",
                "nur die Fakten des Laufs, der gerade beginnt.",
                "",
                f"- Stand: {time.strftime('%d.%m.%Y %H:%M')}",
                f"- Agentenkopf: {self.LABEL} im Browser (`/agent?kopf={self.NAME}`)",
]
        if not self.projekt:
            kopf += [
                "- Projekt: **keines gebunden**",
                "",
                "**Es gibt kein aktuelles Projekt.** Was in frueheren Laeufen entworfen",
                "wurde, ist fuer diese Aufgabe keine Vorgabe und keine Vorlage. Eine neue",
                "Auslegung beginnt mit",
                "`python3 cae_orchestrator/cae_cli.py aufgabe \"<Aufgabe>\"` und danach",
                "`paarvergleich --frisch` — NICHT mit `--from-project last`.",
            ]
        else:
            ordner = os.path.join(PROJEKTE, self.projekt)
            # Ablageort ODER Vorgabe -- der Unterschied entscheidet, ob die
            # Geometrie zu uebernehmen oder zu ignorieren ist, und beides
            # falschherum zu sagen ist gleich teuer. Die Marke steht in
            # ``project.json`` (``design.vorgabe``) und wird gesetzt, wenn
            # jemand im Designer vorzeichnet und ausdruecklich uebergibt.
            vorgabe = False
            try:
                with open(os.path.join(ordner, "project.json"),
                          encoding="utf-8") as f:
                    vorgabe = bool((json.load(f).get("design") or {}).get("vorgabe"))
            except (OSError, ValueError):
                pass
            kopf += [f"- Kennung: `{self.projekt}`",
                     f"- Verzeichnis: `{ordner}`",
                     ""]
            kopf += ([
                "In diesem Projekt liegt eine **von Hand vorgezeichnete Geometrie**,",
                "die ausdruecklich als STARTPUNKT uebergeben wurde. Fang damit an.",
                "Aendern darfst du sie -- sag dann aber, WAS du geaendert hast und",
                "warum. Dies ist NICHT der Fall, gegen den `--frisch` gebaut wurde.",
                ""] if vorgabe else [
                "Das gebundene Projekt ist der ABLAGEORT dieses Laufs, **keine**",
                "Vorlage: Polzahl, Nutzahl, Magnetanordnung, Kuehlung und",
                "Werkstoffe werden nicht daraus uebernommen.",
                ""])
            # Der Steckbrief statt nur der Kennwerte aus ``results.json``.
            #
            # Gemessener Anlass: auf „erstelle kurz einen Steckbrief ueber das
            # Projekt" beschrieb der Agent am 04.09. das **Monorepo** -- Ports,
            # Teilprojekte, Git-Zweig. Das war keine Halluzination, sondern die
            # einzige Beschreibung, die er hatte: hier standen nur Kennung,
            # Verzeichnis und „noch nichts gerechnet", und was sonst nach
            # „Projekt" aussah, stand in ``CLAUDE.md``. Jetzt steht die Maschine
            # selbst hier -- Art, Pole, Nuten, Bauraum, Werkstoffe, Betriebspunkt
            # -- und dazu, was daran schon gerechnet ist und was nicht.
            kopf.append("## Steckbrief dieses Projekts")
            kopf.append("")
            try:
                sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
                import ema_steckbrief
                kopf.append(ema_steckbrief.als_markdown(
                    ema_steckbrief.steckbrief(ordner)))
            except Exception as e:                         # noqa: BLE001
                kopf.append(f"- (Steckbrief nicht lesbar: {type(e).__name__})")
            kopf += ["",
                     "Den ausfuehrlichen Steckbrief samt Herkunft jeder Zahl gibt",
                     f"`python3 cae_orchestrator/cae_cli.py steckbrief {self.projekt}`;",
                     "`--laeufe` zeigt zusaetzlich, was frueher schon an diesem",
                     "Projekt gerechnet wurde."]
        kopf += ["",
                 # Der Skill liegt da, aber `skill_view` findet ihn in
                 # `hermes acp` v0.20.5 nicht (gemessen 04.09.2026, mit eigenem
                 # ACP-Klienten nachgestellt: "Skill 'cae-orchestrator' not
                 # found", waehrend `hermes skills list` ihn zeigt und derselbe
                 # Aufruf in einem gewoehnlichen Prozess gelingt). Ohne diesen
                 # Hinweis sucht der Kopf minutenlang -- oder rechnet ohne den
                 # Skill los, und dann fehlen ihm Verben, Laufzeiten,
                 # Exit-Codes und die Fallen.
                 "## Der Skill",
                 "",
                 "Der Skill `cae-orchestrator` liegt als Datei unter",
                 "`.agents/skills/cae-orchestrator/SKILL.md`. **Lies ihn dort.**",
                 "Findet `skill_view` ihn nicht (bei Hermes gemessen der Fall),",
                 "ist das kein Grund zu suchen und keiner, ohne ihn zu arbeiten",
                 "— eine Datei lesen, weiterarbeiten."]

        # Der stehende Auftrag -- fuer die Koepfe, die keinen Systemzusatz kennen.
        #
        # PI bekommt ihn ueber ``--append-system-prompt``: ein Systemzusatz
        # ueberlebt einen langen Zug, ein Prompt nicht. **Hermes ACP hat diese
        # Flagge nicht** (gemessen an ``hermes acp --help``). Ihn statt dessen an
        # den ersten Prompt zu haengen waere genau der Fehler, gegen den der
        # Systemzusatz gebaut wurde -- ein Prompt kann vergessen werden.
        #
        # Hermes liest aber ``AGENTS.md`` und ``AGENTS.projekt.md`` aus dem
        # Arbeitsverzeichnis, und diese Datei wird bei JEDEM Start neu
        # geschrieben. Derselbe Inhalt, zugestellt ueber den Weg, den dieser Kopf
        # hat. Deshalb steht der Aufruf VOR dem Popen: was danach entstuende,
        # saehe der Prozess nicht mehr.
        if system_zusatz and not self.KANN_SYSTEMZUSATZ:
            kopf += ["", "## Stehender Auftrag fuer diesen Lauf", "",
                     "Das Folgende gilt fuer den ganzen Lauf, nicht nur fuer die",
                     "erste Frage:", "", str(system_zusatz).strip()]
        try:
            with open(pfad, "w", encoding="utf-8") as f:
                f.write("\n".join(kopf) + "\n")
        except OSError:
            return ""
        return pfad

    def marke(self) -> str:
        """Kennung dieses Laufs. Ein PROJEKTordner nimmt mehrere Laeufe auf --
        ohne diese Kennung haenge der zweite Lauf seine Mitschrift an die des
        ersten an, und das Protokoll waere eine Vermischung zweier Sitzungen."""
        return time.strftime("%Y%m%d_%H%M%S",
                             time.localtime(self.start_ts or time.time()))

    def zielordner(self) -> str:
        """Wohin alles zu diesem Lauf geht -- Protokoll UND Aufnahme.

        Einmal bestimmt, dann festgehalten. Vorher wurde der Name bei jedem
        Aufruf aus der aktuellen Uhrzeit gebildet: wer die Aufnahme vor dem
        Agenten startete, bekam zwei Ordner, die eine Minute auseinanderlagen --
        Video hier, Protokoll dort.
        """
        if self.ordner and self._ordner_fuer == self.projekt:
            return self.ordner
        if self.projekt:
            self.ordner = os.path.join(PROJEKTE, self.projekt, "agent")
        else:
            marke = time.strftime("%Y%m%d_%H%M%S",
                                  time.localtime(self.start_ts or time.time()))
            self.ordner = os.path.join(FREIE_LAEUFE, marke)
        self._ordner_fuer = self.projekt
        return self.ordner

    # ── Mitschrift ──────────────────────────────────────────────────────────
    #
    # Der Ring haelt nur die letzten RINGGROESSE Ereignisse -- er ist fuer den
    # Browser da, nicht fuer das Archiv. Ein langer Lauf laeuft ueber, und dann
    # verloere ein aus dem Ring geschriebenes Protokoll seinen ANFANG. Darum
    # laeuft neben dem Ring eine anhaengende Mitschrift; aus ihr entsteht
    # ``protokoll.md``.
    def _mitschrift_oeffnen(self) -> None:
        try:
            ordner = self.zielordner()
            os.makedirs(ordner, exist_ok=True)
            self._mit = open(
                os.path.join(ordner, f"ereignisse_{self.marke()}.jsonl"),
                "a", encoding="utf-8")
        except OSError:
            self._mit = None

    def _mitschreiben(self, satz: dict) -> None:
        """Ein Ereignis anhaengen. Unter der Sperre, darum knapp gehalten."""
        if not self._mit:
            return
        try:
            self._mit.write(json.dumps(satz, ensure_ascii=False) + "\n")
            self._mit.flush()
        except (OSError, ValueError):
            self._mit = None          # einmal schiefgegangen, nicht weiter stoeren

    def _mitschrift_schliessen(self) -> None:
        f, self._mit = self._mit, None
        if f:
            try:
                f.close()
            except OSError:
                pass

    def _mitschrift_lesen(self) -> list:
        pfad = os.path.join(self.zielordner(), f"ereignisse_{self.marke()}.jsonl")
        if not os.path.isfile(pfad):
            return []
        aus = []
        with open(pfad, encoding="utf-8") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile:
                    continue
                try:
                    aus.append(json.loads(zeile))
                except ValueError:
                    continue          # halbe letzte Zeile nach einem Absturz
        return aus

    def _sichern_still(self) -> None:
        """Sichern, ohne dass ein Fehler dabei den Ereignisstrom reisst."""
        try:
            a = self.sichern()
            if a.get("ok"):
                self._sende("gesichert", pfad=a["pfad"], kacheln=a["kacheln"])
        except Exception as e:                               # noqa: BLE001
            self._sende("fehler", text=f"Protokoll nicht schreibbar: {e}")

    def sichern(self) -> dict:
        """Was rechts steht, als Markdown neben das Projekt legen.

        Aus dem **Ringpuffer**, nicht aus dem Browser: der Puffer ist die Quelle,
        aus der sich die Seite ohnehin speist, und er ueberlebt ein geschlossenes
        Fenster. Bilder werden **verwiesen, nicht kopiert** -- sie liegen schon im
        Projekt, und ein langer Lauf soll die Platte nicht zweimal fuellen.
        """
        ring = self._mitschrift_lesen()
        if not ring:
            with self.sperre:
                ring = list(self.ring)
        if not ring:
            return {"ok": False, "grund": "Noch nichts aufgezeichnet."}

        ordner = self.zielordner()
        os.makedirs(ordner, exist_ok=True)
        t0 = self.start_ts or ring[0].get("t", time.time())

        def uhr(t):
            s = max(0, int(round(float(t) - t0)))
            return f"{s // 3600:d}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 \
                   else f"{s // 60:02d}:{s % 60:02d}"

        z = [f"# Agentenlauf {time.strftime('%d.%m.%Y %H:%M', time.localtime(t0))}",
             "",
             f"* Kopf: {self.LABEL} (`{self.NAME}`)",
             f"* Modell: `{self.modell}`",
             f"* Projekt: {self.projekt or '— keine Bindung —'}",
             f"* Sitzung: `{self.sitzung or '—'}`",
             f"* Dauer: {uhr(ring[-1].get('t', t0))}",
             f"* Ereignisse: {len(ring)}",
             # Das Video liegt NICHT hier daneben (s. VIDEO_ORDNER). Ohne diese
             # Zeile waere es nach einer Woche nicht mehr diesem Lauf zuzuordnen.
             *([f"* Aufnahme: `{VIDEO.pfad}`"] if VIDEO.pfad else []),
             "",
             "> Geschrieben aus dem Ereignisstrom des Agenten. Bilder sind",
             "> **verwiesen**, nicht kopiert -- sie liegen im Projekt.",
             ""]
        kacheln = 0
        antwort: list = []

        def antwort_leeren():
            if antwort:
                z.append("".join(antwort).strip())
                z.append("")
                antwort.clear()

        for e in ring:
            art = e.get("art")
            if art == "frage":
                antwort_leeren()
                z += [f"## [{uhr(e.get('t', t0))}] Auftrag", "",
                      "> " + str(e.get("text", "")).replace("\n", "\n> "), ""]
            elif art == "text":
                antwort.append(str(e.get("text", "")))
            elif art == "werkzeug":
                antwort_leeren()
                z += [f"### [{uhr(e.get('t', t0))}] `$ {e.get('befehl', '')}`", ""]
            elif art == "ergebnis":
                antwort_leeren()
                if not str(e.get("text", "")).strip():
                    continue
                kacheln += 1
                kopf = "FEHLER" if e.get("fehler") else "Ergebnis"
                z += [f"**{kopf}** ({e.get('name', '')})", "", "```text",
                      str(e.get("text", "")), "```"]
                if e.get("gekuerzt"):
                    z.append(f"*gekuerzt — {e.get('voll')} Zeichen insgesamt*")
                z.append("")
            elif art == "bild":
                antwort_leeren()
                kacheln += 1
                pfad = os.path.join(PROJEKTE, e.get("projekt", ""),
                                    e.get("unter", ""), e.get("datei", ""))
                # Relativ, solange das Bild im gebundenen Projekt liegt: dann
                # laesst sich das Protokoll mitsamt Projekt verschieben.
                verweis = (os.path.join("..", e.get("unter", ""), e.get("datei", ""))
                           if self.projekt and e.get("projekt") == self.projekt
                           else pfad)
                z += [f"![{e.get('datei', '')}]({verweis})", ""]
            elif art == "fehler":
                antwort_leeren()
                z += [f"**⚠ {e.get('text', '')}**", ""]
        antwort_leeren()

        md = os.path.join(ordner, f"protokoll_{self.marke()}.md")
        with open(md, "w", encoding="utf-8") as f:
            f.write("\n".join(z))
        # Die JSONL-Mitschrift IST schon die vollstaendige Ereignisliste; ein
        # zweites json daneben waere nur eine Kopie, die beim naechsten Zug
        # wieder neu geschrieben wird.
        if not self._mit and not os.path.isfile(
                os.path.join(ordner, f"ereignisse_{self.marke()}.jsonl")):
            with open(os.path.join(ordner, f"ereignisse_{self.marke()}.json"),
                      "w", encoding="utf-8") as f:
                json.dump(ring, f, ensure_ascii=False, indent=1)
        return {"ok": True, "pfad": md, "ordner": ordner,
                "kacheln": kacheln, "ereignisse": len(ring)}

    def zustand(self) -> dict:
        return {"laeuft": self.laeuft, "beschaeftigt": self.beschaeftigt,
                "start_ts": round(self.start_ts, 3), "ordner": self.ordner,
                "projekt": self.projekt, "modell": self.modell,
                "sitzung": self.sitzung, "fehler": self.fehler,
                "ereignisse": len(self.ring),
                "sekunden": round(time.time() - self.start_ts, 1)
                if self.start_ts else 0.0,
                "kopf": self.NAME, "kopf_label": self.LABEL,
                "programm": bool(self.programm()),
                # ``pi`` bleibt als Name stehen, damit eine aeltere Seite nicht
                # ploetzlich "nicht installiert" meldet; ``programm`` ist das
                # kopfrichtige Feld.
                "pi": bool(self.programm())}


class PiKopf(Kopf):
    """PI ueber ``pi --mode rpc``.

    Die Form ist gemessen, nicht dokumentiert: hinein ``{"type":"prompt",
    "message":…}`` (mit ``prompt``/``content``/``text`` als Feldname scheitert es
    mit "Cannot read properties of undefined"), heraus NDJSON. **Zugende ist
    ``agent_settled``**, nicht ``turn_end`` und nicht ``agent_end`` -- die kommen
    davor.
    """

    NAME = "pi"
    LABEL = "PI"
    PFADE = PI_PFADE
    KANN_SYSTEMZUSATZ = True

    def programm(self) -> str | None:
        return pi_gefunden()

    def _fehlt_text(self) -> str:
        return ("pi nicht gefunden (erwartet in ~/.npm-global/bin) — "
                "Einrichtung steht in .agents/README.md")

    def _befehl(self, prog, modell, sitzung, system_zusatz) -> list:
        befehl = [prog, "--provider", "ollama", "--model", modell,
                  "--mode", "rpc"]
        if sitzung == "weiter":
            befehl.append("--continue")
        elif sitzung:
            befehl += ["--session", sitzung]
        if system_zusatz:
            befehl += ["--append-system-prompt", system_zusatz]
        return befehl

    def _prompt_senden(self, text: str) -> None:
        self.proc.stdin.write(
            json.dumps({"type": "prompt", "message": text},
                       ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def sitzungen(self, n: int = 8) -> list:
        return sitzungen(n)

    def _lesen(self) -> None:
        assert self.proc and self.proc.stdout
        for zeile in self.proc.stdout:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                d = json.loads(zeile)
            except ValueError:
                # Kein JSON: PI schreibt gelegentlich Klartext dazwischen. Nicht
                # verwerfen -- genau solche Zeilen tragen die Startfehler.
                self._sende("roh", text=zeile[:400])
                continue
            self._verarbeiten(d)
        self.laeuft = False
        self.beschaeftigt = False
        code = self.proc.wait() if self.proc else -1
        self._sende("ende", code=code)
        self._sichern_still()
        self._mitschrift_schliessen()

    def _verarbeiten(self, d: dict) -> None:
        typ = d.get("type")
        ev = d.get("assistantMessageEvent") or {}
        evt = ev.get("type")

        if evt == "thinking_delta":
            self._sende("denken", text=ev.get("delta", ""))
        elif evt == "text_delta":
            self._sende("text", text=ev.get("delta", ""))
        elif evt == "toolcall_start":
            self._sende("werkzeug_start", name=ev.get("toolName", ""))
        elif typ == "tool_execution_start":
            args = d.get("args") or {}
            self._sende("werkzeug", name=d.get("toolName", ""),
                        befehl=str(args.get("command") or
                                   json.dumps(args, ensure_ascii=False))[:600])
        elif typ == "tool_execution_end":
            res = d.get("result") or {}
            stuecke = [c.get("text", "") for c in (res.get("content") or [])
                       if c.get("type") == "text"]
            text = "\n".join(stuecke)
            self._sende("ergebnis", name=d.get("toolName", ""),
                        fehler=bool(d.get("isError")),
                        text=text[:MAX_AUSGABE],
                        gekuerzt=len(text) > MAX_AUSGABE, voll=len(text))
            self._bilder_melden()
            self._rechnungen_melden()
        elif typ == "turn_start":
            self._sende("zug_start")
        elif typ == "agent_settled":
            # DAS ist das Zugende -- nicht turn_end, nicht agent_end.
            self.beschaeftigt = False
            self._bilder_melden(alle=True)      # Zugende: nichts zurueckhalten
            self._rechnungen_melden()
            self._sende("bereit")
            self._sichern_still()
            self._hinweise_uebergeben()
        elif typ == "response" and d.get("command") == "prompt":
            if not d.get("success"):
                self.beschaeftigt = False
                self._sende("fehler", text=str(d.get("error", ""))[:400])
        elif typ == "session":
            self.sitzung = str(d.get("id", ""))
            self._sende("sitzung", id=self.sitzung, cwd=d.get("cwd", ""))


class HermesKopf(Kopf):
    """Hermes ueber ``hermes acp`` -- Agent Client Protocol, JSON-RPC 2.0.

    Warum ACP und nicht ``hermes serve``
    ------------------------------------

    ``hermes serve`` bringt eine EIGENE Weboberflaeche auf :9119 mit eigener
    Anmeldung. Sie in einen Rahmen zu haengen waere kein zweiter Agentenreiter,
    sondern ein Fremdkoerper: keine Stoppuhr, kein gemeinsames Protokoll, keine
    Bilder aus dem Projektordner, keine Aufnahme. ``hermes acp`` ist das
    Gegenstueck zu ``pi --mode rpc`` -- ein Prozess, ein Strom, und dieselbe
    Seite kann beide bedienen.

    Die Form ist gemessen (nicht dokumentiert geglaubt):

    * **Zeilengetrenntes JSON-RPC 2.0 auf stdout, Protokollzeilen auf stderr.**
      Sauberer als bei PI -- deshalb darf stderr hier NICHT hineingemischt
      werden, sonst zerfaellt der Strom an der ersten Logzeile.
    * ``initialize`` -> ``session/new {cwd, mcpServers}`` -> ``result.sessionId``.
      Erst danach ist der Kopf ansprechbar, deshalb ``_nach_start``.
    * ``session/prompt`` -- und **die Antwort auf diese Anfrage IST das
      Zugende** (``stopReason``). Das ist der eine Punkt, an dem ACP deutlich
      besser ist als PIs ``agent_settled``: es muss nichts erraten werden.
    * Waehrend des Zuges ``session/update`` mit ``update.sessionUpdate`` aus
      ``agent_thought_chunk`` (Denken), ``agent_message_chunk`` (Antwort),
      ``tool_call`` / ``tool_call_update`` (Werkzeug und sein Ergebnis),
      ``usage_update`` (Kontextfuellung) und ``session_info_update``.
    * **Keine Freigabe-Rueckfragen gemessen** (0 bei einem Shell-Aufruf). Kaeme
      doch eine (``session/request_permission``), wuerde der Zug ohne Antwort
      still stehen -- deshalb wird sie beantwortet und im Strom sichtbar
      gemacht, statt sie zu verschweigen.

    Was Hermes anders macht als PI, und warum das hier steht
    -------------------------------------------------------

    **Sein Gedaechtnis haengt am Projekt.** ``HERMES_HOME`` verschiebt die ganze
    Hermes-Ablage; ``start_hermes.sh`` macht das seit jeher, und es ist gemessen,
    dass ``hermes acp`` die Variable befolgt (``state.db`` landet dort). Ohne das
    bekaeme eine neue Auslegung das an einer anderen Auslegung Gelernte als
    Tatsache serviert -- genau der Grund, warum das Terminal beim Hermes-Start
    zuerst nach dem Projekt fragt und bei PI nicht.
    """

    NAME = "hermes"
    LABEL = "Hermes"
    PFADE = HERMES_PFADE
    KANN_SYSTEMZUSATZ = False        # kein --append-system-prompt (gemessen)

    def __init__(self):
        super().__init__()
        self._offene_wz: dict = {}   # toolCallId -> Titel, s. u.
        self._id = 0                  # laufende JSON-RPC-Nummer
        self._sid = ""                # ACP-Sitzung
        self._zug_id = 0              # Anfrage, deren Antwort das Zugende ist
        self._warten: dict = {}       # id -> Antwort
        self._rpc_sperre = threading.Lock()

    # ── Aufruf ──────────────────────────────────────────────────────────────
    def programm(self) -> str | None:
        return hermes_gefunden()

    def _fehlt_text(self) -> str:
        return ("hermes nicht gefunden (erwartet in ~/.local/bin) — "
                "Einrichtung steht in .agents/README.md")

    def _befehl(self, prog, modell, sitzung, system_zusatz) -> list:
        # Modell und Sitzung gehen NICHT ueber die Kommandozeile: `hermes acp`
        # nimmt beides nicht an (gemessen an --help). Das Modell steht in
        # ~/.hermes/config.yaml, die Sitzung wird ueber session/new bzw.
        # session/load gewaehlt.
        return [prog, "acp"]

    def _stderr_ziel(self):
        # NICHT nach stdout: dort laeuft reines JSON-RPC.
        return subprocess.PIPE

    def _umfeld(self) -> dict:
        env = _umgebung(self.PFADE)
        heim = self._hermes_heim()
        if heim:
            env["HERMES_HOME"] = heim
        return env

    def _hermes_heim(self) -> str:
        """Projekteigene Hermes-Ablage -- dieselbe wie in ``start_hermes.sh``.

        Geteiltes wird VERLINKT, nicht kopiert (``config.yaml``, ``.env``,
        ``skills``): eine Kopie liefe auseinander, und dann arbeiteten Terminal-
        und Browserkopf nach zwei Konfigurationen, die beide plausibel aussehen.
        Ohne Projektbindung bleibt die gemeinsame Ablage -- dann gibt es nichts
        zu trennen.
        """
        if not self.projekt:
            return ""
        heim = os.path.join(PROJEKTE, self.projekt, "_agent", "hermes")
        try:
            os.makedirs(os.path.join(heim, "memories"), exist_ok=True)
            os.makedirs(os.path.join(heim, "sessions"), exist_ok=True)
            for teil in ("config.yaml", ".env", "skills"):
                quelle = os.path.expanduser(f"~/.hermes/{teil}")
                ziel = os.path.join(heim, teil)
                if not os.path.exists(quelle):
                    continue
                if os.path.islink(ziel) and os.readlink(ziel) == quelle:
                    continue
                if os.path.lexists(ziel):
                    if os.path.isdir(ziel) and not os.path.islink(ziel):
                        continue          # echtes Verzeichnis: nicht anfassen
                    os.remove(ziel)
                os.symlink(quelle, ziel)
        except OSError:
            return ""
        return heim

    # ── JSON-RPC ────────────────────────────────────────────────────────────
    def _rpc(self, methode: str, params: dict, sek: float = 120.0) -> dict:
        with self._rpc_sperre:
            self._id += 1
            nr = self._id
        self._warten[nr] = None
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": nr, "method": methode, "params": params},
            ensure_ascii=False) + "\n")
        self.proc.stdin.flush()
        t0 = time.time()
        while self._warten.get(nr) is None and time.time() - t0 < sek:
            if not self.laeuft:
                break
            time.sleep(0.05)
        return self._warten.pop(nr, None) or {
            "error": {"message": f"keine Antwort auf {methode} in {sek:.0f}s"}}

    def _antworten(self, nr, ergebnis: dict) -> None:
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": nr, "result": ergebnis},
            ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    def _nach_start(self, modell: str, sitzung: str, system_zusatz: str) -> dict:
        a = self._rpc("initialize",
                      {"protocolVersion": 1,
                       "clientCapabilities": {"fs": {"readTextFile": False,
                                                     "writeTextFile": False}}},
                      sek=120)
        if "error" in a:
            return {"ok": False, "grund": f"initialize: {a['error'].get('message')}"}

        if sitzung and sitzung != "weiter":
            b = self._rpc("session/load",
                          {"sessionId": sitzung, "cwd": WURZEL, "mcpServers": []},
                          sek=180)
            if "error" not in b:
                self._sid = sitzung
        if not self._sid:
            b = self._rpc("session/new", {"cwd": WURZEL, "mcpServers": []}, sek=240)
            if "error" in b:
                return {"ok": False,
                        "grund": f"session/new: {b['error'].get('message')}"}
            self._sid = str((b.get("result") or {}).get("sessionId", ""))
        if not self._sid:
            return {"ok": False, "grund": "ACP lieferte keine sessionId"}
        self.sitzung = self._sid
        self._sende("sitzung", id=self._sid, cwd=WURZEL, heim=self._hermes_heim())
        return {"ok": True}

    def _prompt_senden(self, text: str) -> None:
        with self._rpc_sperre:
            self._id += 1
            nr = self._id
        self._zug_id = nr
        self.proc.stdin.write(json.dumps(
            {"jsonrpc": "2.0", "id": nr, "method": "session/prompt",
             "params": {"sessionId": self._sid,
                        "prompt": [{"type": "text", "text": text}]}},
            ensure_ascii=False) + "\n")
        self.proc.stdin.flush()

    # ── Strom ───────────────────────────────────────────────────────────────
    def _lesen(self) -> None:
        assert self.proc and self.proc.stdout
        threading.Thread(target=self._stderr_lesen, daemon=True).start()
        for zeile in self.proc.stdout:
            zeile = zeile.strip()
            if not zeile:
                continue
            try:
                d = json.loads(zeile)
            except ValueError:
                self._sende("roh", text=zeile[:400])
                continue
            self._verarbeiten(d)
        self.laeuft = False
        self.beschaeftigt = False
        code = self.proc.wait() if self.proc else -1
        self._sende("ende", code=code)
        self._sichern_still()
        self._mitschrift_schliessen()

    def _stderr_lesen(self) -> None:
        """Hermes' Protokollzeilen -- nur die, die etwas bedeuten.

        Alles durchzureichen fuellte die linke Spalte mit 55 Zeilen
        Plugin-Registrierung je Start. Weggeworfen werden darf es aber auch
        nicht: die Startfehler stehen genau dort.
        """
        if not self.proc or not self.proc.stderr:
            return
        for zeile in self.proc.stderr:
            zeile = zeile.rstrip()
            if not zeile:
                continue
            if "[ERROR]" in zeile or "[CRITICAL]" in zeile or "Traceback" in zeile:
                self._sende("roh", text=zeile[:400])

    def _verarbeiten(self, d: dict) -> None:
        # Antwort auf eine unserer Anfragen?
        if "id" in d and ("result" in d or "error" in d):
            nr = d.get("id")
            if nr == self._zug_id:
                # DAS ist das Zugende -- die Antwort auf session/prompt selbst.
                self._zug_id = 0
                self.beschaeftigt = False
                if "error" in d:
                    self._sende("fehler",
                                text=str(d["error"].get("message", ""))[:400])
                self._bilder_melden(alle=True)
                self._rechnungen_melden()
                self._offene_werkzeuge_abschliessen()
                erg = d.get("result") or {}
                self._sende("bereit", grund=str(erg.get("stopReason", "")),
                            marken=(erg.get("usage") or {}).get("totalTokens"))
                self._sichern_still()
                self._hinweise_uebergeben()
            else:
                self._warten[nr] = d
            return

        # Anfrage AN uns (z. B. Freigabe). Unbeantwortet stuende der Zug still.
        if "id" in d and "method" in d:
            self._freigabe(d)
            return

        if d.get("method") != "session/update":
            return
        upd = (d.get("params") or {}).get("update") or {}
        art = upd.get("sessionUpdate")
        inhalt = upd.get("content")

        def _text(x) -> str:
            if isinstance(x, dict):
                return str(x.get("text", ""))
            if isinstance(x, list):
                return "\n".join(_text(e.get("content", e)) if isinstance(e, dict)
                                 else str(e) for e in x)
            return str(x or "")

        if art == "agent_thought_chunk":
            self._sende("denken", text=_text(inhalt))
        elif art == "agent_message_chunk":
            self._sende("text", text=_text(inhalt))
        elif art == "tool_call":
            # Gemerkt, um am Zugende zu WISSEN, welcher Aufruf nie ein Ergebnis
            # bekommen hat -- siehe _offene_werkzeuge_abschliessen.
            if upd.get("toolCallId"):
                self._offene_wz[str(upd["toolCallId"])] = str(upd.get("title") or
                                                              upd.get("kind") or "")
            self._sende("werkzeug", name=str(upd.get("kind") or "werkzeug"),
                        befehl=(str(upd.get("title") or "")
                                + ("\n" + _text(inhalt) if inhalt else ""))[:600])
        elif art == "tool_call_update":
            if str(upd.get("status")) not in ("completed", "failed"):
                return                       # Zwischenstand, nicht das Ergebnis
            self._offene_wz.pop(str(upd.get("toolCallId") or ""), None)
            text = _text(inhalt)
            self._sende("ergebnis", name=str(upd.get("kind") or "werkzeug"),
                        fehler=str(upd.get("status")) == "failed",
                        text=text[:MAX_AUSGABE],
                        gekuerzt=len(text) > MAX_AUSGABE, voll=len(text))
            self._bilder_melden()
            self._rechnungen_melden()
        elif art == "usage_update":
            self._sende("kontext", genutzt=upd.get("used"), gross=upd.get("size"))

    def _offene_werkzeuge_abschliessen(self) -> None:
        """Werkzeugaufrufe benennen, zu denen ACP nie ein Ergebnis geschickt hat.

        Gemessener Fehler stromaufwaerts, ``hermes acp`` v0.20.5 (04.09.2026):
        ruft das Modell in EINEM Zug mehrere Werkzeuge auf, kommt je Aufruf ein
        ``tool_call``, aber **kein** ``tool_call_update`` -- bei einem einzelnen
        Werkzeug kommt es zuverlaessig. Nachgestellt mit einem eigenen
        ACP-Klienten: 1 Werkzeug -> 1 Aufruf + 1 Update; 3 Werkzeuge -> 3
        Aufrufe + 0 Updates. Das Modell selbst BEKOMMT seine Ergebnisse (es
        zitiert sie in der Antwort) -- nur der Klient sieht sie nicht.

        Erfinden laesst sich hier nichts: das Ergebnis ist an dieser Stelle
        wirklich nicht bekannt. Also steht genau das da, statt dass die rechte
        Spalte schweigt und der Betrachter denkt, es sei nichts gerechnet
        worden. Was das Verb auf die PLATTE geschrieben hat, kommt ohnehin
        ueber ``_rechnungen_melden`` an -- unabhaengig von diesem Fehler.
        """
        offen, self._offene_wz = dict(self._offene_wz), {}
        for titel in offen.values():
            self._sende("ergebnis", name="ohne Rueckmeldung", fehler=False,
                        text=(f"{titel}\n\n"
                              "Hermes hat zu diesem Werkzeugaufruf KEIN Ergebnis "
                              "gemeldet (ACP schickt bei mehreren Werkzeugen in "
                              "einem Zug kein tool_call_update — gemessen mit "
                              "hermes acp v0.20.5). Der Agent selbst hat es "
                              "bekommen; hier ist es nicht bekannt. Was ein "
                              "cae_cli-Verb ablegt, erscheint trotzdem — es "
                              "kommt ueber den Projektordner, nicht ueber ACP."),
                        gekuerzt=False, voll=0)

    def _freigabe(self, d: dict) -> None:
        """Eine Rueckfrage beantworten -- und sie sichtbar machen.

        Gemessen kommt hier nichts (0 Rueckfragen bei einem Shell-Aufruf, weil
        der Kopf ohne Terminal-Freigaben laeuft). Kaeme doch eine und niemand
        antwortete, stuende der Zug still und die Seite zeigte nur eine Uhr, die
        weiterlaeuft. Deshalb wird zugestimmt UND in den Strom geschrieben --
        stillschweigend zuzustimmen waere schlimmer als die Rueckfrage.
        """
        params = d.get("params") or {}
        optionen = params.get("options") or []
        wahl = ""
        for o in optionen:
            kennung = str(o.get("optionId", ""))
            if "allow" in kennung.lower() or "allow" in str(o.get("kind", "")).lower():
                wahl = kennung
                break
        if not wahl and optionen:
            wahl = str(optionen[0].get("optionId", ""))
        self._sende("freigabe", methode=str(d.get("method", "")),
                    text=json.dumps(params, ensure_ascii=False)[:400],
                    gewaehlt=wahl)
        try:
            self._antworten(d.get("id"),
                            {"outcome": {"outcome": "selected", "optionId": wahl}})
        except (BrokenPipeError, OSError):
            pass

    # ── Sitzungen ───────────────────────────────────────────────────────────
    def sitzungen(self, n: int = 8) -> list:
        """Hermes-Sitzungen liegen in seiner state.db, nicht als Dateien.

        Sie ueber ein eigenes SQL-Schema zu lesen hiesse, eine fremde
        Tabellenform nachzubauen, die sich mit jeder Fassung aendern darf. ACP
        kann es selbst (``sessionCapabilities.list``), aber erst NACH dem Start
        -- und die Startmaske fragt vorher. Bis das gebraucht wird, bleibt die
        Liste leer: eine leere Liste heisst hier "neue Sitzung", und das ist bei
        Hermes ohnehin der Normalfall, weil sein Gedaechtnis am Projekt haengt.
        """
        return []


LAUF = PiKopf()
HERMES = HermesKopf()

# Beide Koepfe unter ihrem Namen -- die Routen schlagen hier nach, statt je Kopf
# eine eigene Route zu tragen. Ein dritter Kopf braucht dann eine Zeile, keine
# fuenfzehn Routen.
KOEPFE = {LAUF.NAME: LAUF, HERMES.NAME: HERMES}


def kopf(name: str = "") -> Kopf:
    """Den gemeinten Kopf holen. Unbekannt -> PI (der gewachsene Weg)."""
    return KOEPFE.get(str(name or "").strip().lower(), LAUF)


# ── Bildschirmaufnahme ───────────────────────────────────────────────────────
#
# Der Browser nimmt auf (``getDisplayMedia`` + ``MediaRecorder``), aber er
# BEHAELT nichts: jedes Stueck geht sofort hierher und wird angehaengt. Sonst
# lieferte ein langer Lauf am Ende ein Blob von hunderten Megabyte im
# Arbeitsspeicher der Seite -- und waere beim Absturz des Fensters ganz weg.
# Mit dem Anhaengen ist der Speicherbedarf flach und die Datei nach jedem
# Stueck vollstaendig genug, um sie abzuspielen.
VIDEO_MAX_MB = 800        # harte Grenze; danach wird sauber beendet

# Wohin die Aufnahmen gehen. **Ein fester Ort**, nicht der Projektordner: ein
# Bildschirmvideo ist kein Rechenergebnis. Es gehoert dorthin, wo der Mensch
# Videos sucht und wo ein Abspieler sie findet -- und es soll nicht in ein
# Projektverzeichnis wandern, das spaeter kopiert, gepackt oder geloescht wird.
# Der Bezug zum Lauf steckt statt dessen im DATEINAMEN (Zeitmarke + Projekt),
# und das Protokoll nennt den Pfad. Ueber ``CAE_VIDEO_ORDNER`` umstellbar.
VIDEO_ORDNER = os.path.expanduser(
    os.environ.get("CAE_VIDEO_ORDNER") or "~/Videos")


class Aufnahme:
    def __init__(self):
        self.sperre = threading.Lock()
        self.f = None
        self.pfad = ""
        self.bytes = 0
        self.start_ts = 0.0
        # Waehrend der Server rechnet, steht das Bild still. Die Aufnahme wird
        # dann angehalten (der Browser haelt den MediaRecorder an, hier wird nur
        # BUCHGEFUEHRT, wie lange) -- sonst besteht ein vierstuendiger Lauf zu
        # neun Zehnteln aus einem unveraenderten Fortschrittsbalken und die
        # 800-MB-Grenze ist erreicht, bevor etwas Sehenswertes passiert ist.
        self.pause_s = 0.0
        self.pause_seit = 0.0

    def starten(self, projekt: str = "", ordner: str = "") -> dict:
        with self.sperre:
            if self.f:
                return {"ok": False, "grund": "Es laeuft bereits eine Aufnahme."}
            ordner = ordner or VIDEO_ORDNER
            os.makedirs(ordner, exist_ok=True)
            marke = time.strftime("%Y%m%d_%H%M%S")
            teil = "".join(c for c in str(projekt) if c.isalnum() or c in "._-")[:60]
            name = f"agent_{marke}" + (f"_{teil}" if teil else "") + ".webm"
            self.pfad = os.path.join(ordner, name)
            self.f = open(self.pfad, "wb")
            self.bytes = 0
            self.start_ts = time.time()
            self.pause_s = 0.0
            self.pause_seit = 0.0
            return {"ok": True, "pfad": self.pfad, "max_mb": VIDEO_MAX_MB}

    def anhaengen(self, rohdaten: bytes) -> dict:
        with self.sperre:
            if not self.f:
                return {"ok": False, "grund": "Es laeuft keine Aufnahme."}
            self.f.write(rohdaten)
            self.f.flush()
            self.bytes += len(rohdaten)
            voll = self.bytes >= VIDEO_MAX_MB * 1024 * 1024
        if voll:
            a = self.beenden()
            a["grenze"] = True
            return a
        return {"ok": True, "bytes": self.bytes, "grenze": False}

    def beenden(self) -> dict:
        with self.sperre:
            if not self.f:
                return {"ok": False, "grund": "Es laeuft keine Aufnahme."}
            try:
                self.f.close()
            finally:
                self.f = None
            pause = self._pause_gesamt()
            gesamt = time.time() - self.start_ts
            return {"ok": True, "pfad": self.pfad, "bytes": self.bytes,
                    "sekunden": round(gesamt - pause, 1),
                    "pause_s": round(pause, 1),
                    "verstrichen_s": round(gesamt, 1)}

    def pausieren(self, an: bool) -> dict:
        """Nur die Buchfuehrung -- angehalten wird im Browser.

        Der Datenstrom kommt aus dem ``MediaRecorder`` der Seite; nur sie kann
        ihn anhalten. Hier wird gezaehlt, wie lange, damit die Dauer im Protokoll
        die AUFGEZEICHNETE Zeit ist und nicht die verstrichene.
        """
        with self.sperre:
            if not self.f:
                return {"ok": False, "grund": "Es laeuft keine Aufnahme."}
            jetzt = time.time()
            if an and not self.pause_seit:
                self.pause_seit = jetzt
            elif not an and self.pause_seit:
                self.pause_s += jetzt - self.pause_seit
                self.pause_seit = 0.0
            return {"ok": True, "pausiert": bool(self.pause_seit),
                    "pause_s": round(self._pause_gesamt(jetzt), 1)}

    def _pause_gesamt(self, jetzt: float | None = None) -> float:
        jetzt = jetzt or time.time()
        return self.pause_s + (jetzt - self.pause_seit if self.pause_seit else 0.0)

    def zustand(self) -> dict:
        return {"laeuft": bool(self.f), "pfad": self.pfad, "bytes": self.bytes,
                "max_mb": VIDEO_MAX_MB, "ordner": VIDEO_ORDNER,
                "pausiert": bool(self.pause_seit),
                "pause_s": round(self._pause_gesamt(), 1)}


VIDEO = Aufnahme()


# ── Auswahl fuer die Startseite ──────────────────────────────────────────────

def projekte(n: int = 12) -> list:
    """Die juengsten Projekte -- Name, Stand, Zeit. Wie das Hermes-Startmenue."""
    aus = []
    try:
        namen = sorted((x for x in os.listdir(PROJEKTE)
                        if x[:1] == "2" and os.path.isdir(os.path.join(PROJEKTE, x))),
                       reverse=True)[:n]
    except OSError:
        return []
    for pid in namen:
        p = os.path.join(PROJEKTE, pid)
        aus.append({"id": pid,
                    "gerechnet": os.path.isfile(os.path.join(p, "results.json")),
                    "zeit": os.path.getmtime(p)})
    return aus


def sitzungen(n: int = 8) -> list:
    """PI-Sitzungen DIESES Arbeitsverzeichnisses.

    Dieselbe Regel wie in ``start_agent.sh`` (dort als eingebettetes Python), und
    aus demselben Grund: PI legt Sitzungen unter
    ``~/.pi/agent/sessions/<kodiertes cwd>/`` ab, **wie** das cwd kodiert wird ist
    aber nirgends zugesagt. Die erste Zeile jeder Datei traegt es im Klartext --
    danach wird gefiltert, statt den Verzeichnisnamen aus dem Pfad zu raten.
    """
    import glob

    basis = os.path.expanduser("~/.pi/agent/sessions")
    treffer = []
    for f in glob.glob(os.path.join(basis, "*", "*.jsonl")):
        try:
            with open(f, encoding="utf-8") as fh:
                kopf = json.loads(fh.readline())
                if kopf.get("type") != "session" or kopf.get("cwd") != WURZEL:
                    continue
                titel = ""
                for zeile in fh:
                    try:
                        d = json.loads(zeile)
                    except ValueError:
                        continue
                    m = d.get("message")
                    if (d.get("type") == "message" and isinstance(m, dict)
                            and m.get("role") == "user"):
                        for c in m.get("content") or []:
                            if isinstance(c, dict) and c.get("type") == "text":
                                titel = " ".join(str(c.get("text", "")).split())[:70]
                                break
                    if titel:
                        break
        except (OSError, ValueError, KeyError):
            continue
        treffer.append({"id": kopf["id"], "datei": f, "titel": titel,
                        "zeit": os.path.getmtime(f),
                        "stand": str(kopf.get("timestamp", ""))[:16].replace("T", " ")})
    treffer.sort(key=lambda s: -s["zeit"])
    return treffer[:n]
