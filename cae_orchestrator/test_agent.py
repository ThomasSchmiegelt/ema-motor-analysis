"""Tests fuer den Agenten im Browser (`ema_agent`) — ohne PI, ohne Server.

Was hier festgenagelt wird, und warum gerade das
------------------------------------------------

Fast alles an diesem Modul haengt an einer **gemessenen** Zusage eines fremden
Programms, die nirgends dokumentiert ist. Genau solche Stellen brechen still:
PI wird aktualisiert, das Feld heisst anders, und die Seite zeigt dann nicht
etwa einen Fehler, sondern **nichts** — ein leeres Fenster, in dem der Agent
scheinbar nicht antwortet.

1. **Die Prompt-Form.** ``{"type":"prompt","message":…}``. Mit ``prompt``,
   ``content`` oder ``text`` als Feldname antwortet PI
   „Cannot read properties of undefined (reading 'startsWith')" — gemessen.
2. **Das Zugende ist ``agent_settled``**, nicht ``turn_end`` und nicht
   ``agent_end``. Beide kommen davor; wer auf sie hoert, gibt die Eingabe zu
   frueh frei und schickt den naechsten Prompt in einen laufenden Zug.
3. **Der Strom wird zusammengefasst.** Zwei Woerter Antwort erzeugen 75
   ``message_update``-Ereignisse. Der Aufseher darf sie buendeln, aber keinen
   Werkzeugaufruf und keinen Fehler verschlucken.
4. **Bilder kommen ueber die Aenderungszeit**, nicht aus dem Werkzeugtext.
5. **Das Arbeitsverzeichnis ist die Repo-Wurzel** — PI sortiert Sitzungen nach
   cwd, und von woanders faende es weder ``AGENTS.md`` noch ``.agents/skills/``.
6. **Die Bildroute laesst nur ``charts``/``cad_images`` durch.**
"""

import io
import json
import os
import queue
import shutil
import subprocess
import sys
import time

import ema_agent as A

_n_ok = _n_bad = 0


def pruefe(bedingung, text):
    global _n_ok, _n_bad
    if bedingung:
        _n_ok += 1
        print(f"  ✓ {text}")
    else:
        _n_bad += 1
        print(f"  ✗ {text}")


def _frischer_lauf() -> A.PiKopf:
    """Ein Aufseher ohne Prozess — genug, um den Ereignispfad zu pruefen."""
    lauf = A.PiKopf()
    lauf.laeuft = True
    lauf._bild_marke = time.time() + 3600      # keine echten Bilder einstreuen
    return lauf


def _ereignisse(lauf) -> list:
    return list(lauf.ring)


print("1. Die gemessene PI-Schnittstelle")

# Die Prompt-Form: nachgestellter Prozess, der nur mitschreibt, was hineingeht.
class _Rohr:
    def __init__(self): self.zeilen = []
    def write(self, s): self.zeilen.append(s)
    def flush(self): pass


class _Prozess:
    def __init__(self): self.stdin = _Rohr()


lauf = _frischer_lauf()
lauf.proc = _Prozess()
lauf.fragen("Hallo Welt")
geschrieben = json.loads(lauf.proc.stdin.zeilen[0])
pruefe(geschrieben == {"type": "prompt", "message": "Hallo Welt"},
       f"stdin traegt genau {{type:prompt, message:…}} ({geschrieben})")
pruefe("message" in geschrieben and "prompt" not in geschrieben
       and "content" not in geschrieben and "text" not in geschrieben,
       "und keinen der drei Feldnamen, mit denen PI scheitert")
pruefe(lauf.beschaeftigt, "nach dem Absenden gilt der Agent als beschaeftigt")
pruefe(not lauf.fragen("noch was")["ok"],
       "ein zweiter Prompt waehrend eines laufenden Zuges wird abgewiesen")


print("\n2. agent_settled ist das Zugende — turn_end und agent_end sind es nicht")
lauf = _frischer_lauf()
lauf.beschaeftigt = True
for typ in ("turn_end", "agent_end"):
    lauf._verarbeiten({"type": typ})
    pruefe(lauf.beschaeftigt, f"'{typ}' gibt die Eingabe NICHT frei")
lauf._verarbeiten({"type": "agent_settled"})
pruefe(not lauf.beschaeftigt, "'agent_settled' gibt sie frei")
pruefe(any(e["art"] == "bereit" for e in _ereignisse(lauf)),
       "und meldet 'bereit' an die Seite")


print("\n3. Der Strom wird zusammengefasst, aber nichts verschluckt")
lauf = _frischer_lauf()
roh = [
    {"type": "message_update", "assistantMessageEvent":
        {"type": "thinking_delta", "delta": "denk"}},
    {"type": "message_update", "assistantMessageEvent":
        {"type": "text_delta", "delta": "Ant"}},
    {"type": "message_update", "assistantMessageEvent":
        {"type": "text_delta", "delta": "wort"}},
    {"type": "message_update", "assistantMessageEvent":
        {"type": "toolcall_start", "toolName": "bash"}},
    {"type": "tool_execution_start", "toolName": "bash",
     "args": {"command": "python3 cae_cli.py health"}},
    {"type": "tool_execution_end", "toolName": "bash", "isError": False,
     "result": {"content": [{"type": "text", "text": "alles erreichbar"}]}},
    {"type": "agent_settled"},
]
for d in roh:
    lauf._verarbeiten(d)
arten = [e["art"] for e in _ereignisse(lauf)]
pruefe(arten == ["denken", "text", "text", "werkzeug_start", "werkzeug",
                 "ergebnis", "bereit", "gesichert"],
       f"jede Rohform findet ihre Entsprechung ({arten})")
pruefe(arten[-1] == "gesichert" and arten[-2] == "bereit",
       "am Zugende wird von selbst gesichert — ein langer Lauf haengt nicht daran, "
       "dass der Browser bis zum Schluss offen bleibt")
wz = next(e for e in _ereignisse(lauf) if e["art"] == "werkzeug")
pruefe(wz["befehl"] == "python3 cae_cli.py health",
       "der Werkzeugaufruf steht im Klartext da, nicht als JSON-Klumpen")
erg = next(e for e in _ereignisse(lauf) if e["art"] == "ergebnis")
pruefe(erg["text"] == "alles erreichbar" and not erg["fehler"],
       "die Werkzeugausgabe geht vollstaendig in die rechte Spalte")

# Fehler duerfen NICHT wie Erfolge aussehen.
lauf = _frischer_lauf()
lauf._verarbeiten({"type": "tool_execution_end", "toolName": "bash", "isError": True,
                   "result": {"content": [{"type": "text", "text": "Exit 2"}]}})
pruefe(_ereignisse(lauf)[0]["fehler"] is True,
       "ein fehlgeschlagenes Werkzeug ist als Fehler markiert")

# Lange Ausgaben werden gekuerzt — aber sichtbar, nicht heimlich.
lauf = _frischer_lauf()
lang = "x" * (A.MAX_AUSGABE + 500)
lauf._verarbeiten({"type": "tool_execution_end", "toolName": "bash", "isError": False,
                   "result": {"content": [{"type": "text", "text": lang}]}})
e = _ereignisse(lauf)[0]
pruefe(len(e["text"]) == A.MAX_AUSGABE and e["gekuerzt"]
       and e["voll"] == len(lang),
       f"lange Ausgabe gekuerzt UND als gekuerzt ausgewiesen ({e['voll']} Zeichen)")

# Nicht-JSON darf nicht verschwinden: dort stehen die Startfehler.
lauf = _frischer_lauf()
lauf._sende("roh", text="Error: model not found")
pruefe(_ereignisse(lauf)[0]["art"] == "roh",
       "Klartextzeilen von PI werden durchgereicht, nicht verworfen")

# Ein abgewiesener Prompt gibt die Eingabe wieder frei.
lauf = _frischer_lauf()
lauf.beschaeftigt = True
lauf._verarbeiten({"type": "response", "command": "prompt", "success": False,
                   "error": "kaputt"})
pruefe(not lauf.beschaeftigt and _ereignisse(lauf)[0]["art"] == "fehler",
       "ein abgewiesener Prompt meldet den Fehler und gibt die Eingabe frei")


print("\n4. Bilder kommen ueber die Aenderungszeit")
import tempfile

with tempfile.TemporaryDirectory() as tmp:
    alt_wurzel = A.PROJEKTE
    A.PROJEKTE = tmp
    try:
        pdir = os.path.join(tmp, "20260902_120000_Probe", "charts")
        os.makedirs(pdir)
        lauf = _frischer_lauf()
        lauf._bild_marke = time.time()
        time.sleep(0.02)
        alt = os.path.join(pdir, "vorher.png")
        open(alt, "wb").write(b"\x89PNG")
        neu = lauf._neue_bilder()
        pruefe([b["datei"] for b in neu] == ["vorher.png"],
               "ein neu geschriebenes Diagramm wird gefunden")
        pruefe(lauf._neue_bilder() == [],
               "dasselbe Bild kein zweites Mal — sonst fuellt es die Spalte zu")
        time.sleep(0.02)
        os.utime(alt, None)                 # neu gerechnet, gleicher Name
        lauf._bild_marke = 0.0
        pruefe([b["datei"] for b in lauf._neue_bilder()] == ["vorher.png"],
               "ein NEU gerechnetes Bild gleichen Namens kommt wieder durch")
        open(os.path.join(pdir, "notiz.txt"), "w").write("kein Bild")
        lauf._bild_marke = 0.0
        pruefe(all(b["datei"].endswith(A.BILD_ENDUNGEN)
                   for b in lauf._neue_bilder()),
               "Nicht-Bilder bleiben draussen")
        os.makedirs(os.path.join(tmp, "_intern", "charts"))
        open(os.path.join(tmp, "_intern", "charts", "x.png"), "wb").write(b"\x89PNG")
        lauf._bild_marke = 0.0
        pruefe(all(b["projekt"][:1] != "_" for b in lauf._neue_bilder()),
               "interne Ordner (_db, _jobs, _training …) zaehlen nicht als Projekt")
    finally:
        A.PROJEKTE = alt_wurzel


print("\n5. Ringpuffer: ein neu geladener Browser steigt dort ein, wo er war")
lauf = _frischer_lauf()
for i in range(5):
    lauf._sende("text", text=f"t{i}")
q_alles = lauf.anmelden(0)
q_ab3 = lauf.anmelden(3)
pruefe(q_alles.qsize() == 5, f"wer bei 0 anmeldet, bekommt den ganzen Verlauf ({q_alles.qsize()})")
pruefe(q_ab3.qsize() == 2, f"wer bei 3 anmeldet, nur den Rest ({q_ab3.qsize()})")
lauf._sende("text", text="neu")
pruefe(q_ab3.get_nowait()["text"] == "t3",
       "der Nachzuegler beginnt bei t3, nicht bei t0")


def _letzter(q):
    letzt = None
    while not q.empty():
        letzt = q.get_nowait()
    return letzt


pruefe(_letzter(q_alles)["text"] == "neu" and _letzter(q_ab3)["text"] == "neu",
       "und beide enden beim selben neuen Ereignis")
lauf.abmelden(q_ab3)
pruefe(q_ab3 not in lauf.hoerer, "abgemeldete Hoerer werden nicht weiter bedient")

lauf = _frischer_lauf()
for i in range(A.RINGGROESSE + 50):
    lauf._sende("text", text=str(i))
pruefe(len(lauf.ring) == A.RINGGROESSE,
       f"der Ring ist gedeckelt ({len(lauf.ring)}) — ein langer Lauf frisst den Speicher nicht")


print("\n6. Wo PI laeuft, und womit")
pruefe(os.path.isfile(os.path.join(A.WURZEL, "AGENTS.md"))
       or os.path.isdir(os.path.join(A.WURZEL, ".agents")),
       f"das Arbeitsverzeichnis ist die Repo-Wurzel ({A.WURZEL})")
pruefe(os.path.isdir(os.path.join(A.WURZEL, "cae_orchestrator")),
       "und enthaelt den Orchestrator")
umg = A._umgebung()
pruefe(any(p in umg["PATH"].split(os.pathsep) for p in A.PI_PFADE if os.path.isdir(p)),
       "npm-global liegt im PATH des Unterprozesses — dort liegt pi")

lauf = A.PiKopf()
lauf.laeuft = True
pruefe(not lauf.starten("egal")["ok"],
       "ein zweiter Agent wird abgewiesen, solange einer laeuft")


print("\n7. Die Bildroute laesst nur die zwei Bildordner durch")
try:
    import server
    server.app.config["TESTING"] = True
    c = server.app.test_client()
    pruefe(c.get("/agent").status_code == 200, "die Seite wird ausgeliefert")
    pruefe(c.get("/agent/auswahl").status_code == 200, "die Startauswahl antwortet")
    pruefe(c.get("/agent/status").status_code == 200, "der Zustand ist abfragbar")
    pruefe(c.get("/agent/bild/../charts/x.png").status_code in (403, 404),
           "ein Projektname mit .. wird abgewiesen")
    pruefe(c.get("/agent/bild/gueltig/rag/x.png").status_code == 403,
           "ein anderer Unterordner als charts/cad_images wird abgewiesen")
    pruefe(c.get("/agent/bild/gueltig/charts/gibtsnicht.png").status_code == 404,
           "ein fehlendes Bild ist ein 404, kein Serverfehler")
    leer = c.post("/agent/frage", json={"text": "  "})
    pruefe(leer.status_code == 400, "ein leerer Auftrag wird abgewiesen")
except ImportError as e:
    print(f"  (server nicht importierbar: {e} — Routentests uebersprungen)")


print("\n8. Der Agent haengt als eigener Reiter in der Hauptoberflaeche")
_hier = os.path.dirname(os.path.abspath(__file__))
_ema = io.open(os.path.join(_hier, "ema.html"), encoding="utf-8").read()
pruefe("switchTab('agent')" in _ema and "id=\"tbtn-agent\"" in _ema,
       "die Reiterleiste hat einen Knopf 🤖 PI")
pruefe("switchTab('agenth')" in _ema and "id=\"tbtn-agenth\"" in _ema,
       "und daneben einen zweiten Knopf 🪽 Hermes")
pruefe("'compare','agent','agenth']" in _ema.replace(" ", "")
       and "agent:'panel-agent'" in _ema
       and "agenth:'panel-agent-hermes'" in _ema,
       "beide Reiter sind in TABS und PANEL_OF angemeldet — sonst schaltet switchTab sie nie sichtbar")
pruefe('id="agent-rahmen"' in _ema and 'id="agent-rahmen-hermes"' in _ema
       and 'src="/agent"' not in _ema,
       "je Kopf ein eigener Rahmen, beide erst nach dem ersten Oeffnen geladen (kein Strom beim Seitenstart)")
pruefe("_agSrc = k => k === 'hermes' ? '/agent?kopf=hermes' : '/agent'" in _ema,
       "agActivate() setzt die Quelle nach — EINE Seite, unterschieden durch ?kopf=")

_ag = io.open(os.path.join(_hier, "ema_agent.html"), encoding="utf-8").read()
pruefe("anknuepfen" in _ag and "'/agent/status'" in _ag,
       "die Seite fragt beim Laden erst, ob schon ein Lauf haengt")
pruefe("if (!await anknuepfen()) auswahlLaden()" in _ag,
       "und zeigt die Startmaske nur, wenn keiner laeuft — sonst zeichnet der Ringpuffer den Verlauf nach")


print("\n9. Das Protokoll: was rechts steht, liegt hinterher auf der Platte")
_lauf = _frischer_lauf()
_lauf.modell = "qwen-gross:latest"
_lauf.start_ts = time.time() - 125
_lauf.projekt = ""
_lauf._sende("start", modell="m", projekt="", befehl="pi --mode rpc")
_lauf._sende("frage", text="Rechne den Paarvergleich.")
_lauf._sende("text", text="Ich starte ")
_lauf._sende("text", text="mit dem Paarvergleich.")
_lauf._sende("werkzeug", name="bash", befehl="python3 cae_cli.py paarvergleich --frisch")
_lauf._sende("ergebnis", name="bash", fehler=False, text="Achse kuehlung: 3 Optionen",
             gekuerzt=False, voll=24)
_lauf._sende("bild", projekt="20260901_x", unter="charts", datei="em_field.png")
_a = _lauf.sichern()
pruefe(_a["ok"] and os.path.isfile(_a["pfad"]), f"das Protokoll wird geschrieben ({_a.get('pfad')})")
_md = io.open(_a["pfad"], encoding="utf-8").read()
pruefe("Rechne den Paarvergleich." in _md, "der Auftrag steht drin")
pruefe("Achse kuehlung: 3 Optionen" in _md, "und die Werkzeugausgabe — das ist die rechte Spalte")
pruefe("Ich starte mit dem Paarvergleich." in _md,
       "die Antwort steht als EIN Absatz da, nicht als 75 Bruchstuecke")
pruefe("![em_field.png](" in _md and "/home/" in _md,
       "Bilder werden verwiesen, nicht kopiert — ein langer Lauf fuellt die Platte nicht zweimal")
pruefe("02:05" in _md, "die Dauer steht im Kopf")
pruefe(_a["kacheln"] == 2, f"gezaehlt werden die Kacheln der rechten Spalte ({_a['kacheln']})")
pruefe(not _lauf.projekt and A.FREIE_LAEUFE in _a["ordner"]
       and not os.path.basename(A.FREIE_LAEUFE).startswith("2"),
       "ohne Projektbindung liegt es unter _agent_laeufe — kein Name, der als Projekt durchgeht")
_lauf.projekt = "20260901_x"
pruefe(_lauf.zielordner() == os.path.join(A.PROJEKTE, "20260901_x", "agent"),
       "mit Bindung liegt es im Projekt")
shutil.rmtree(A.FREIE_LAEUFE, ignore_errors=True)

_leer = A.PiKopf()
pruefe(not _leer.sichern()["ok"], "ein leerer Lauf schreibt keine leere Datei")


print("\n10. Die Aufnahme haengt an, statt im Browser zu sammeln")
_v = A.Aufnahme()
_ord = tempfile.mkdtemp(prefix="aufnahme_")
_s = _v.starten(_ord)
pruefe(_s["ok"] and _s["pfad"].endswith(".webm"), "die Aufnahme legt eine Datei an")
pruefe(not _v.starten(_ord)["ok"], "eine zweite Aufnahme wird abgewiesen")
_v.anhaengen(b"AAAA"); _v.anhaengen(b"BB")
pruefe(_v.zustand()["bytes"] == 6, "jedes Stueck wird angehaengt")
pruefe(io.open(_s["pfad"], "rb").read() == b"AAAABB",
       "und steht schon WAEHREND des Laufs vollstaendig auf der Platte")
_e = _v.beenden()
pruefe(_e["ok"] and _e["bytes"] == 6, "das Ende meldet Groesse und Dauer")
pruefe(not _v.anhaengen(b"X")["ok"], "nach dem Ende nimmt sie nichts mehr an")

_v2 = A.Aufnahme()
_alt_max = A.VIDEO_MAX_MB
try:
    A.VIDEO_MAX_MB = 1 / 1024 / 1024        # 1 Byte
    _v2.starten(_ord)
    _r = _v2.anhaengen(b"XY")
    pruefe(_r.get("grenze") and not _v2.zustand()["laeuft"],
           "an der Groessengrenze endet sie von selbst — ein langer Lauf laeuft die Platte nicht voll")
finally:
    A.VIDEO_MAX_MB = _alt_max
shutil.rmtree(_ord, ignore_errors=True)


print("\n11. Mitlaufen, Stoppuhr und Sichern in der Seite")
pruefe("const FOLGT" in _ag and "chip_links" in _ag and "chip_rechts" in _ag,
       "jede Spalte merkt sich, ob sie folgt — statt es bei jedem Anhaengen neu zu schaetzen")
pruefe("bild.addEventListener('load'" in _ag,
       "nach dem Laden eines Bildes wird nachgezogen — vorher steht seine Hoehe nicht fest")
pruefe("uhrTick" in _ag and "ZUG0" in _ag and "start_ts" in _ag,
       "die Stoppuhr zeigt Laufzeit UND laufenden Zug und ueberlebt ein Neuladen")
pruefe("uhrStempel(e.t)" in _ag, "jede Kachel traegt ihre Zeit — im Video ablesbar")
pruefe("/agent/video/stueck" in _ag and "REK_KETTE" in _ag,
       "die Aufnahme schickt Stuecke der Reihe nach an den Server, statt sie zu sammeln")
pruefe('allow="display-capture"' in _ema,
       "der Reiter erlaubt dem Rahmen die Bildschirmaufnahme — sonst ginge sie nur auf der eigenen Seite")

try:
    pruefe(c.post("/agent/sichern").status_code in (200, 400),
           "die Sicherungsroute antwortet")
    pruefe(c.get("/agent/video/status").status_code == 200,
           "der Aufnahmezustand ist abfragbar")
except NameError:
    print("  (Routentests uebersprungen)")


print("\n12. Ein LANGER Lauf verliert weder seinen Anfang noch seinen Ordner")
_tmp = tempfile.mkdtemp(prefix="langer_lauf_")
_l = A.PiKopf()
_l.start_ts = time.time()
_l.ordner = _tmp; _l._ordner_fuer = _l.projekt
_l._mitschrift_oeffnen()
_l._sende("frage", text="DER ERSTE AUFTRAG")
for i in range(A.RINGGROESSE + 200):
    _l._sende("ergebnis", name="bash", fehler=False, text=f"Zwischenergebnis {i}",
              gekuerzt=False, voll=9)
pruefe(len(_l.ring) == A.RINGGROESSE and _l._nr == A.RINGGROESSE + 201,
       f"der Ring ist gedeckelt ({len(_l.ring)}), die Zaehlung laeuft weiter ({_l._nr})")
_nummern = [x["i"] for x in _l.ring]
pruefe(_nummern == sorted(set(_nummern)) and _nummern[-1] == _l._nr,
       "die Nummern zaehlen durch — nach dem Ueberlauf ist ?ab= sonst mehrdeutig")
_q = _l.anmelden(_l._nr - 3)
pruefe(_q.qsize() == 3, f"?ab= liefert genau das Neue ({_q.qsize()})")
_a = _l.sichern()
_md = io.open(_a["pfad"], encoding="utf-8").read()
pruefe("DER ERSTE AUFTRAG" in _md,
       "der Anfang steht im Protokoll — aus der Mitschrift, nicht aus dem uebergelaufenen Ring")
pruefe("Zwischenergebnis 0" in _md and f"Zwischenergebnis {A.RINGGROESSE + 199}" in _md,
       "und alles dazwischen ebenso")
_l._mitschrift_schliessen()
pruefe(_l.marke() in os.path.basename(_a["pfad"]),
       "Protokoll und Mitschrift tragen die Kennung des Laufs — ein Projektordner "
       "vermischt zwei Sitzungen sonst")
shutil.rmtree(_tmp, ignore_errors=True)

# Die Aufnahme liegt an EINEM festen Ort, nicht beim Projekt: ein
# Bildschirmvideo ist kein Rechenergebnis, und der Bezug zum Lauf steckt im
# Dateinamen. Frueher zog eine laufende Aufnahme in den Projektordner um --
# das entfaellt, weil es nichts mehr umzuziehen gibt.
_tmp2 = tempfile.mkdtemp(prefix="video_")
_v3 = A.Aufnahme()
_s3 = _v3.starten(projekt="20260903_Testlauf", ordner=_tmp2)
pruefe(os.path.dirname(_s3["pfad"]) == _tmp2,
       "die Aufnahme landet im vorgegebenen Videoordner")
pruefe("20260903_Testlauf" in os.path.basename(_s3["pfad"])
       and os.path.basename(_s3["pfad"]).startswith("agent_"),
       f"der Dateiname traegt Zeitmarke und Projekt ({os.path.basename(_s3['pfad'])})")
pruefe(A.VIDEO_ORDNER == os.path.expanduser(
           os.environ.get("CAE_VIDEO_ORDNER") or "~/Videos"),
       f"ohne Vorgabe ist der Ordner ~/Videos ({A.VIDEO_ORDNER})")
_v3.anhaengen(b"AAA")
pruefe(_v3.pausieren(True)["pausiert"] is True, "die Aufnahme laesst sich anhalten")
pruefe(_v3.zustand()["pausiert"] is True, "und meldet das im Zustand")
_v3.anhaengen(b"BBB")                     # der Browser haelt an, nicht der Server
pruefe(_v3.pausieren(False)["pausiert"] is False, "und wieder fortsetzen")
_e3 = _v3.beenden()
pruefe(_e3["verstrichen_s"] >= _e3["sekunden"] >= 0.0 and _e3["pause_s"] >= 0.0,
       "die gemeldete Dauer ist die AUFGEZEICHNETE, die Pause steht daneben")
pruefe(io.open(_s3["pfad"], "rb").read() == b"AAABBB",
       "die Stuecke stehen der Reihe nach in EINER Datei")
_x3 = A.Aufnahme()
pruefe(_x3.pausieren(True)["ok"] is False,
       "ohne laufende Aufnahme ist Anhalten ein Bedienfehler, kein stiller Erfolg")
shutil.rmtree(_tmp2, ignore_errors=True)


print("\n12b. Die Projektakte wird bei JEDEM Start neu geschrieben")
_akte = os.path.join(A.WURZEL, "AGENTS.projekt.md")
_sicherung = io.open(_akte, encoding="utf-8").read() if os.path.exists(_akte) else None
try:
    _alt_p = A.LAUF.projekt
    A.LAUF.projekt = ""
    _p = A.LAUF.projektakte_schreiben()
    _t = io.open(_p, encoding="utf-8").read()
    pruefe("keines gebunden" in _t and "keine Vorlage" in _t,
           "ohne Bindung steht ausdruecklich drin, dass es KEIN aktuelles Projekt gibt")
    pruefe("--from-project last" in _t and "NICHT" in _t,
           "und dass eine neue Auslegung nicht mit --from-project last beginnt")
    A.LAUF.projekt = "20260101_Nichtvorhanden"
    _t2 = io.open(A.LAUF.projektakte_schreiben(), encoding="utf-8").read()
    pruefe("20260101_Nichtvorhanden" in _t2 and "keines gebunden" not in _t2,
           "mit Bindung traegt sie die Kennung — die alte Akte bleibt NICHT stehen")
    pruefe("ABLAGEORT" in _t2 and "Vorlage" in _t2,
           "und sagt auch dann, dass das Projekt Ablageort ist und nicht Vorlage")
finally:
    A.LAUF.projekt = _alt_p
    if _sicherung is not None:
        io.open(_akte, "w", encoding="utf-8").write(_sicherung)
    elif os.path.exists(_akte):
        os.remove(_akte)

_agents_md = io.open(os.path.join(A.WURZEL, "AGENTS.md"), encoding="utf-8").read()
pruefe("--frisch" in _agents_md and "python3 cae_cli.py aufgabe" in _agents_md,
       "AGENTS.md — die erste Datei, die PI liest — zeigt den frischen Start als Beispiel")
pruefe("maschinenart" in _agents_md and "zyklus liste" in _agents_md,
       "und nennt Maschinenart und Lastfall als Entscheidungen VOR dem Lauf")


print("\n13. Der Bilder-Deckel haelt zurueck, statt zu verschlucken")
_pt = tempfile.mkdtemp(prefix="bilder_")
_alt_proj = A.PROJEKTE
try:
    A.PROJEKTE = _pt
    _ch = os.path.join(_pt, "20260903_test", "charts")
    os.makedirs(_ch)
    _n = A.MAX_BILDER_JE_ZUG + 5
    for i in range(_n):                       # eine fertige Pipeline schreibt sie
        with open(os.path.join(_ch, f"bild_{i:02d}.png"), "wb") as f:
            f.write(b"x")                     # in wenigen Sekunden auf einmal
    _b = A.PiKopf()
    _b._bild_marke = 0.0
    _erste = _b._neue_bilder()
    pruefe(len(_erste) == A.MAX_BILDER_JE_ZUG,
           f"auf einmal gehen hoechstens {A.MAX_BILDER_JE_ZUG} nach rechts")
    pruefe(len(_b._offen) == 5, "der Rest wird zurueckgehalten, nicht weggeworfen")
    _zweite = _b._neue_bilder(alle=True)
    _namen = sorted(x["datei"] for x in _erste + _zweite)
    pruefe(len(_namen) == _n and len(set(_namen)) == _n,
           f"am Zugende sind ALLE {_n} da, jedes genau einmal ({len(_namen)})")
    pruefe(_namen[0] == "bild_00.png",
           "auch das aelteste — vorher schnitt der Deckel genau die weg")
finally:
    A.PROJEKTE = _alt_proj
    shutil.rmtree(_pt, ignore_errors=True)


print("\n14. Der 3D-Lauf steht im Auftrag, nicht nur im Skill")
try:
    import server as _srv
    _gefangen = {}

    def _fang(modell, projekt="", sitzung="", system_zusatz=""):
        _gefangen["zusatz"] = system_zusatz
        return {"ok": False, "grund": "Test"}

    _echt = A.LAUF.starten
    A.LAUF.starten = _fang
    try:
        _srv.app.config["TESTING"] = True
        _srv.app.test_client().post("/agent/start", json={"projekt": "", "modell": "m"})
    finally:
        A.LAUF.starten = _echt
    _z = _gefangen.get("zusatz", "")
    pruefe("run em3d" in _z and "--wait" in _z,
           "der Systemzusatz verlangt die 3D-Gegenprobe nach jeder Analyse")
    pruefe("report" in _z and "503" in _z,
           "und den Bericht DANACH — samt Hinweis, dass 503 fehlendes Elmer meldet")
    _skill = io.open(os.path.join(A.WURZEL, ".agents", "skills",
                                  "cae-orchestrator", "SKILL.md"), encoding="utf-8").read()
    pruefe("run em3d --from-project" in _skill,
           "und dasselbe steht im Skill, den beide Agentenkoepfe lesen")
except ImportError as e:
    print(f"  (server nicht importierbar: {e})")


print("\n15. Zwischenruf: mitreden, ohne den Lauf zu unterbrechen")
_z = _frischer_lauf()
_z.laeuft = True
_z.beschaeftigt = True
_a = _z.merken("Das ist ein Fahrrad, kein Auto — nimm keinen Pkw-Zyklus.")
pruefe(_a["ok"] and _a.get("gemerkt") and _z.hinweise,
       "waehrend eines Zuges wird der Hinweis GEMERKT statt abgewiesen")
pruefe([e["art"] for e in _ereignisse(_z)][-1] == "gemerkt",
       "und sofort quittiert — der Mensch sieht, dass er angekommen ist")
_z.merken("Und rechne den Zyklus mit gear_ratio 1.")
pruefe(len(_z.hinweise) == 2, "mehrere Rufe sammeln sich")

_gesendet = []
_z.fragen = lambda t: _gesendet.append(t) or {"ok": True}
_z._hinweise_uebergeben()
pruefe(len(_gesendet) == 1 and not _z.hinweise,
       "am Zugende gehen sie als EIN Auftrag hinaus, nicht als drei")
pruefe("Fahrrad" in _gesendet[0] and "gear_ratio" in _gesendet[0]
       and "Zwischenruf" in _gesendet[0],
       "beide Rufe stehen darin, als Zwischenruf gekennzeichnet")
pruefe(not _z.merken("  ")["ok"], "ein leerer Zwischenruf wird abgewiesen")

_w = A.PiKopf()
_w.laeuft = True
_w.beschaeftigt = False
_w.fragen = lambda t: {"ok": True, "direkt": True}
pruefe(_w.merken("jetzt")["ok"] and not _w.hinweise,
       "wartet der Agent ohnehin, geht der Hinweis sofort durch")

_html = io.open(os.path.join(_hier, "ema_agent.html"), encoding="utf-8").read()
pruefe("b_hinweis" in _html and "/agent/hinweis" in _html,
       "die Seite hat ein eigenes Zwischenruf-Feld")
pruefe("$('b_hinweis').disabled = !LAEUFT" in _html,
       "das WAEHREND der Arbeit bedienbar bleibt — sonst haette es keinen Zweck")


print("\n15b. Die Ergebnisspalte GLEITET ans Ende, sie springt nicht")
# Fuer die Bildschirmaufnahme ist das der ganze Unterschied: sprang die Spalte,
# war die neue Kachel schon unten, bevor man sah, DASS eine kam.
_runter = _html.split("function runter(el){")[1].split("}")[0]
pruefe("scrollHeight" not in _runter,
       "kein Sprung mehr beim Anhaengen — runter() weist scrollTop nicht mehr zu")
pruefe("gleitStart(el.id)" in _html and "requestAnimationFrame(schritt)" in _html,
       "runter() startet ein Gleiten je Bild statt einer Zuweisung")
pruefe("GLEIT_MIN_PX_S" in _html and "rest / GLEIT_TAU_S" in _html,
       "das Tempo ist Rueckstand/Zeitkonstante, nach unten auf Lesegeschwindigkeit begrenzt")
pruefe("if(g && Math.abs(el.scrollTop - g.erwartet) < 2) return;" in _html,
       "die eigene Bewegung gilt nicht als Bedienung — sonst schaltete das Mitlaufen sich selbst ab")
pruefe("if(!unten) gleitStopp(id);" in _html,
       "wer von Hand hochscrollt, bricht das Gleiten sofort ab")
pruefe("gleitStopp(id);\n  FOLGT[id] = true" in _html,
       "„⤓ Neues\" springt weiterhin sofort ans Ende")


print("\n16. Zweiter Kopf: Hermes, genauso eingebaut wie PI")

_h = A.HermesKopf()
pruefe(_h.NAME == "hermes" and _h.LABEL == "Hermes",
       "der Kopf traegt Name und Beschriftung, an denen die Routen ihn finden")
pruefe(A.kopf("hermes") is A.HERMES and A.kopf("") is A.LAUF
       and A.kopf("gibtsnicht") is A.LAUF,
       "kopf() waehlt aus, faellt aber auf PI zurueck — eine aeltere Seite laeuft unveraendert weiter")
pruefe(A.LAUF is not A.HERMES and A.LAUF.ring is not A.HERMES.ring,
       "beide Koepfe haben EIGENEN Zustand: ein laufender PI blockiert Hermes nicht")

pruefe(_h._befehl("/pfad/hermes", "qwen-gross:latest", "abc", "zusatz")
       == ["/pfad/hermes", "acp"],
       "Modell und Sitzung stehen NICHT auf der Kommandozeile — `hermes acp` nimmt beides nicht an")
pruefe(_h._stderr_ziel() is subprocess.PIPE,
       "stderr wird NICHT nach stdout gemischt — dort laeuft reines JSON-RPC")
pruefe(A.PiKopf()._stderr_ziel() is subprocess.STDOUT,
       "bei PI dagegen schon — dort ist stdout ohnehin NDJSON plus Text")
pruefe(_h.KANN_SYSTEMZUSATZ is False and A.PiKopf().KANN_SYSTEMZUSATZ is True,
       "Hermes kennt kein --append-system-prompt; der Stand geht ueber AGENTS.projekt.md hinein")

# ── HERMES_HOME: das Gedaechtnis haengt am Projekt ──────────────
_h.projekt = ""
pruefe("HERMES_HOME" not in _h._umfeld(),
       "ohne Projektbindung bleibt die gemeinsame Ablage — da gibt es nichts zu trennen")
_tmp = tempfile.mkdtemp(prefix="agent_hermes_")
_alt_proj = A.PROJEKTE
try:
    A.PROJEKTE = _tmp
    _h.projekt = "20260904_120000_probe"
    _heim = _h._umfeld().get("HERMES_HOME", "")
    pruefe(_heim.endswith(os.path.join("20260904_120000_probe", "_agent", "hermes"))
           and os.path.isdir(os.path.join(_heim, "memories")),
           "mit Projekt zeigt HERMES_HOME in den Projektordner — sonst servierte er das an einer anderen Auslegung Gelernte")
finally:
    A.PROJEKTE = _alt_proj
    shutil.rmtree(_tmp, ignore_errors=True)

# ── Der Strom: die gemessenen session/update-Arten ──────────────
_h2 = A.HermesKopf()
_h2.laeuft = True
_h2._bild_marke = time.time() + 3600
_h2.proc = _Prozess()
_h2._sid = "sitz-1"

def _upd(art, **rest):
    _h2._verarbeiten({"jsonrpc": "2.0", "method": "session/update",
                      "params": {"sessionId": "sitz-1",
                                 "update": {"sessionUpdate": art, **rest}}})

_upd("agent_thought_chunk", content={"type": "text", "text": "Ich ueberlege."})
_upd("agent_message_chunk", content={"type": "text", "text": "Ich rechne."})
_upd("tool_call", kind="execute", title="python3 cae_cli.py paarvergleich")
_upd("tool_call_update", kind="execute", status="pending", content={"text": "laeuft"})
_upd("tool_call_update", kind="execute", status="completed",
     content={"text": "Achse kuehlung: 3 Optionen"})
_upd("usage_update", used=12000, size=65536)
_arten = [e["art"] for e in _ereignisse(_h2)]
pruefe(_arten == ["denken", "text", "werkzeug", "ergebnis", "kontext"],
       f"denken/text/werkzeug/ergebnis/kontext kommen an, der Zwischenstand nicht ({_arten})")

# ── Das Zugende ist die ANTWORT auf session/prompt ──────────────
_h2.beschaeftigt = True
_h2._zug_id = 7
_h2._verarbeiten({"jsonrpc": "2.0", "id": 7,
                  "result": {"stopReason": "end_turn"}})
pruefe(not _h2.beschaeftigt and "bereit" in [e["art"] for e in _ereignisse(_h2)],
       "die Antwort auf session/prompt IST das Zugende — nichts muss erraten werden")

# Eine Antwort auf eine ANDERE Anfrage ist kein Zugende, sondern ein Ergebnis.
_vorher = len(_ereignisse(_h2))
_h2._verarbeiten({"jsonrpc": "2.0", "id": 3, "result": {"sessionId": "x"}})
pruefe(_h2._warten.get(3, {}).get("result", {}).get("sessionId") == "x"
       and len(_ereignisse(_h2)) == _vorher,
       "eine Antwort auf initialize/session/new wird abgelegt, nicht als Zugende gedeutet")

# ── Freigabe: beantworten UND sichtbar machen ───────────────────
_h2.proc.stdin.zeilen = []
_h2._verarbeiten({"jsonrpc": "2.0", "id": 9, "method": "session/request_permission",
                  "params": {"options": [{"optionId": "reject_once"},
                                         {"optionId": "allow_always"}]}})
_antw = json.loads(_h2.proc.stdin.zeilen[-1])
pruefe(_antw["id"] == 9
       and _antw["result"]["outcome"]["optionId"] == "allow_always",
       "eine Rueckfrage wird beantwortet — unbeantwortet stuende der Zug still")
pruefe(_ereignisse(_h2)[-1]["art"] == "freigabe",
       "und sie steht im Strom: stillschweigend zuzustimmen waere schlimmer als die Rueckfrage")

# ── Der Prompt geht als session/prompt hinaus ───────────────────
_h3 = A.HermesKopf()
_h3.laeuft = True
_h3._bild_marke = time.time() + 3600
_h3.proc = _Prozess()
_h3._sid = "sitz-2"
_h3.fragen("Lege eine ASM aus.")
_raus = json.loads(_h3.proc.stdin.zeilen[0])
pruefe(_raus["method"] == "session/prompt"
       and _raus["params"]["sessionId"] == "sitz-2"
       and _raus["params"]["prompt"] == [{"type": "text", "text": "Lege eine ASM aus."}],
       "hinein geht ACP-Form: sessionId + prompt-Bloecke")
pruefe(_h3._zug_id == _raus["id"],
       "und die Nummer wird gemerkt — an ihr erkennt der Strom das Zugende")

# ── Die Seite bedient BEIDE Koepfe ──────────────────────────────
pruefe("const KOPF = (new URLSearchParams(location.search).get('kopf') || 'pi')" in _html,
       "die Seite liest ?kopf= (Vorgabe pi) statt ein zweites HTML zu sein")
pruefe(_html.count("fetch('/agent") == 0 and _html.count("fetch(K('/agent") >= 10,
       "und schickt JEDE Adresse durch K() — eine vergessene traefe sonst still PI")
pruefe("PROJEKTPFLICHT && !$('f_projekt').value" in _html,
       "bei Hermes ist die Projektwahl Pflicht: sein Gedaechtnis haengt daran")

try:
    import server as _srv
    _srv.app.config["TESTING"] = True
    _c = _srv.app.test_client()
    _a = _c.get("/agent/auswahl?kopf=hermes").get_json()
    _b = _c.get("/agent/auswahl").get_json()
    pruefe(_a["kopf"] == "hermes" and _a["kopf_label"] == "Hermes"
           and _a["projektpflicht"] is True,
           "/agent/auswahl?kopf=hermes antwortet fuer Hermes — mit Projektpflicht")
    pruefe(_b["kopf"] == "pi" and _b["projektpflicht"] is False,
           "ohne Angabe bleibt es PI, ohne Projektpflicht")
    pruefe({x["name"] for x in _a["koepfe"]} == {"pi", "hermes"},
           "die Maske erfaehrt, welche Koepfe es gibt")
    pruefe(_c.get("/agent/status?kopf=hermes").get_json()["kopf"] == "hermes",
           "auch der Zustand ist je Kopf abfragbar — sonst zeigte der Hermes-Reiter PIs Uhr")
except ImportError as e:
    print(f"  (server nicht importierbar: {e} — Kopfroutentests uebersprungen)")


print("\n" + "=" * 60)
print(f"{_n_ok} bestanden, {_n_bad} fehlgeschlagen")
sys.exit(1 if _n_bad else 0)
