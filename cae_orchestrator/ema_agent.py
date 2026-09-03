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

# Ringpuffer: damit ein spaet geoeffneter oder neu geladener Browser den Verlauf
# nachbekommt, statt mitten im Satz einzusteigen.
RINGGROESSE = 4000

# Wie viel Text ein einzelnes Werkzeugergebnis in die rechte Spalte traegt. Ein
# ungekuerztes `results`-JSON ist sechsstellig lang und macht die Spalte unlesbar.
MAX_AUSGABE = 4000
MAX_BILDER_JE_ZUG = 12

BILD_ENDUNGEN = (".png", ".jpg", ".jpeg", ".svg", ".webp")


def pi_gefunden() -> str | None:
    """Pfad zu ``pi`` -- oder ``None``, dann sagt die Route es ehrlich."""
    umgebung = os.environ.get("PATH", "")
    for p in PI_PFADE:
        if os.path.isdir(p):
            umgebung = p + os.pathsep + umgebung
    return shutil.which("pi", path=umgebung)


def _umgebung() -> dict:
    env = dict(os.environ)
    zusatz = [p for p in PI_PFADE if os.path.isdir(p)]
    env["PATH"] = os.pathsep.join(zusatz + [env.get("PATH", "")])
    return env


class Lauf:
    """Ein laufender PI-Prozess samt Ereignisstrom.

    Bewusst EIN Lauf je Server (wie die uebrigen Zustands-Dicts in ``server.py``):
    zwei gleichzeitige Agenten wuerden sich um dasselbe Projektverzeichnis und
    denselben Ollama-Speicher streiten, und im Video will man ohnehin einen.
    """

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

    def _bilder_melden(self, alle: bool = False) -> None:
        neue = self._neue_bilder(alle=alle)
        self._bild_marke = max([b["mtime"] for b in neue] + [self._bild_marke])
        for b in neue:
            self._sende("bild", projekt=b["projekt"], unter=b["unter"],
                        datei=b["datei"])

    # ── Der Lesefaden ───────────────────────────────────────────────────────
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
        elif typ == "turn_start":
            self._sende("zug_start")
        elif typ == "agent_settled":
            # DAS ist das Zugende -- nicht turn_end, nicht agent_end.
            self.beschaeftigt = False
            self._bilder_melden(alle=True)      # Zugende: nichts zurueckhalten
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

    # ── Steuerung ───────────────────────────────────────────────────────────
    def starten(self, modell: str, projekt: str = "", sitzung: str = "",
                system_zusatz: str = "") -> dict:
        if self.laeuft:
            return {"ok": False, "grund": "Es laeuft bereits ein Agent."}
        pi = pi_gefunden()
        if not pi:
            return {"ok": False,
                    "grund": "pi nicht gefunden (erwartet in ~/.npm-global/bin) — "
                             "Einrichtung steht in .agents/README.md"}
        befehl = [pi, "--provider", "ollama", "--model", modell, "--mode", "rpc"]
        if sitzung == "weiter":
            befehl.append("--continue")
        elif sitzung:
            befehl += ["--session", sitzung]
        if system_zusatz:
            befehl += ["--append-system-prompt", system_zusatz]

        self.ring = []
        self._gesehen = set()
        self._bild_marke = time.time()
        self.fehler = ""
        self.projekt = projekt
        self.modell = modell
        self.start_ts = time.time()
        try:
            self.proc = subprocess.Popen(
                befehl, cwd=WURZEL, env=_umgebung(),
                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT, text=True, bufsize=1)
        except OSError as e:
            self.fehler = f"{type(e).__name__}: {e}"
            return {"ok": False, "grund": self.fehler}
        self.laeuft = True
        # Neuer Lauf, neuer Ordner -- und alles zu diesem Lauf kommt hinein:
        # Mitschrift, Protokoll und eine schon laufende Aufnahme.
        self.ordner = ""
        self._ordner_fuer = None
        self._nr = 0
        ordner = self.zielordner()
        self._mitschrift_schliessen()
        self._mitschrift_oeffnen()
        akte = self.projektakte_schreiben()
        threading.Thread(target=self._lesen, daemon=True).start()
        self._sende("start", modell=modell, projekt=projekt,
                    befehl=" ".join(befehl), ordner=ordner, akte=akte)
        return {"ok": True, "modell": modell, "projekt": projekt,
                "ordner": ordner}

    def fragen(self, text: str) -> dict:
        if not self.laeuft or not self.proc or not self.proc.stdin:
            return {"ok": False, "grund": "Es laeuft kein Agent."}
        if self.beschaeftigt:
            return {"ok": False, "grund": "Der Agent arbeitet noch."}
        self.beschaeftigt = True
        self._sende("frage", text=text)
        try:
            self.proc.stdin.write(
                json.dumps({"type": "prompt", "message": text},
                           ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
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
    def projektakte_schreiben(self) -> str:
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
                f"- Agentenkopf: PI im Browser (`/agent`)"]
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
            kopf += [f"- Kennung: `{self.projekt}`",
                     f"- Verzeichnis: `{ordner}`",
                     "",
                     "Das gebundene Projekt ist der ABLAGEORT dieses Laufs, **keine**",
                     "Vorlage: Polzahl, Nutzahl, Magnetanordnung, Kuehlung und",
                     "Werkstoffe werden nicht daraus uebernommen.",
                     ""]
            erg = os.path.join(ordner, "results.json")
            if os.path.exists(erg):
                kopf.append("Bereits gerechnet (aus results.json):")
                stand = os.path.join(WURZEL, ".agents", "projektstand.py")
                try:
                    aus = subprocess.run([sys.executable, stand, erg],
                                         capture_output=True, text=True, timeout=20)
                    kopf.append(aus.stdout.rstrip()
                                or "- (results.json nicht lesbar)")
                except Exception:                          # noqa: BLE001
                    kopf.append("- (results.json nicht lesbar)")
            else:
                kopf.append("Noch nichts gerechnet — es gibt keine results.json.")
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
                "pi": bool(pi_gefunden())}


LAUF = Lauf()


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
