"""Steckbrief, Ablage und der Rueckweg in frueher gelaufene Zuege -- ohne Server.

Drei Beschwerden stehen hinter diesen Pruefungen, und jede hat hier ihre eigene
Reihe:

  1. **„Die Ergebnisse der agentischen Berechnungen werden nicht gespeichert."**
     Stimmte woertlich: von den oertlichen Verben schrieb nur ``feldbild`` etwas
     auf die Platte. Also wird hier festgenagelt, dass ``paarvergleich``,
     ``screen``, ``rotor-check`` und ``sicherheit`` ihr Ergebnis ins Projekt
     legen -- und dass die Ablage NICHT abhaengig davon ist, ob der Agentenkopf
     sein Werkzeugergebnis meldet.
  2. **„Ich kann sie nicht wieder aufrufen."** Die Protokolle wurden nach jedem
     Zug geschrieben und nie gelesen. Geprueft wird der ganze Rueckweg:
     Auflisten, Einlesen, Deckelung, und dass die Seite dafuer KEINEN zweiten
     Satz Zeichenfunktionen bekommt.
  3. **„Die Agenten sollen einen Steckbrief ueber das Projekt wiedergeben."**
     Der Steckbrief darf nichts rechnen und muss die Herkunft jeder Zahl
     mitfuehren -- sonst sieht die analytische Ringformel aus wie ein
     FEM-Ergebnis, und genau daran ist in diesem Repo schon dreimal etwas
     falsch gelesen worden.

Der teuerste Fehler, gegen den hier geprueft wird, ist aber der vierte: die
Uebersicht darf die Mitschriften **nicht vollstaendig einlesen**. Eine davon ist
gemessen 9,4 MB mit 140.872 Ereignissen.
"""

import json
import os
import re
import sys
import tempfile
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import cae_cli
import ema_agent
import ema_steckbrief as SB

_ok = _bad = 0
HIER = os.path.dirname(os.path.abspath(__file__))


def pruefe(bedingung, text):
    global _ok, _bad
    if bedingung:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def _projekt(tmp, pid="20260101_120000", **erg):
    """Ein Projektordner, wie ihn die Pipeline hinterlaesst."""
    d = os.path.join(tmp, pid)
    os.makedirs(os.path.join(d, "charts"), exist_ok=True)
    json.dump({"schema_version": 1, "id": pid, "label": pid, "status": "gerechnet",
               "created": "2026-01-01T12:00:00", "updated": "2026-01-01T12:30:00",
               "lineage": {"parent": None, "origin": "analyse"},
               "design": {"brief": "", "source": "hand"}, "evolution": [],
               "metrics": {}, "assets": {}, "inputs": {"payload": {}},
               "notes": "", "tags": [], "links": [], "rag": {"docs": []},
               "attachments": []},
              open(os.path.join(d, "project.json"), "w"))
    json.dump({"payload": {"geom": {"statorOD": 200, "statorID": 130, "rotorOD": 128.6,
                                    "axialLen": 90, "slots": 48, "p": 4,
                                    "machineType": "pmsm", "magShape": "v"},
                           "axial_len": 90, "cooling": "water", "magnet": "ndfeb_n35",
                           "rotor_lam": "m400_50a", "hairpin_mat": "cu_etp",
                           "rpm_from": 1000, "rpm_to": 12000, "load_nm": 180}},
              open(os.path.join(d, "meta.json"), "w"))
    if erg:
        json.dump(erg, open(os.path.join(d, "results.json"), "w"))
    return d


# ── 1) Die Ablage: ein Verbergebnis ueberlebt das Fenster ───────────────────
print("\n[1] Ablage — was gerechnet wurde, bleibt liegen")

with tempfile.TemporaryDirectory() as tmp:
    d = _projekt(tmp)
    a = SB.ablegen(d, "paarvergleich", "Achse kuehlung: 3 Optionen",
                   daten={"achsen": 1}, befehl="paarvergleich --achsen kuehlung")
    pruefe(a["ok"] and os.path.isfile(a["datei"]),
           "ein Verbergebnis landet als Datei im Projekt")
    roh = open(a["datei"], encoding="utf-8").read()
    pruefe("# Aufruf : paarvergleich --achsen kuehlung" in roh,
           "und traegt den AUFRUF mit — ohne ihn ist eine Zahl spaeter nicht "
           "zuzuordnen")
    pruefe("Achse kuehlung: 3 Optionen" in roh, "der Wortlaut steht drin")
    pruefe(os.path.isfile(a["datei"][:-4] + ".json"),
           "strukturierte Daten liegen als .json daneben")

    b = SB.ablegen(d, "paarvergleich", "zweiter Lauf in derselben Sekunde")
    pruefe(b["ok"] and b["datei"] != a["datei"],
           "zwei Rechnungen in DERSELBEN Sekunde ueberschreiben sich nicht "
           "(ein Agent ruft zwei Verben in einem Zug auf)")

    akte = json.load(open(os.path.join(d, "project.json")))
    pruefe(any(e.get("action") == "cli:paarvergleich" for e in akte["evolution"]),
           "die Ablage haengt eine Zeile ins Projekttagebuch — nicht in ein "
           "zweites Tagebuch daneben")
    pruefe(akte["evolution"][-1]["ref"].startswith("rechnungen/"),
           "und verweist relativ, damit das Projekt umziehen kann")

    pruefe(SB.ablegen(os.path.join(tmp, "gibtsnicht"), "screen", "x")["ok"] is False,
           "ohne Projektordner schlaegt die Ablage WEICH fehl — ein volles "
           "Dateisystem darf keine fertige Rechnung abbrechen")

    r = SB.rechnungen(d)
    pruefe(len(r) == 2 and r[0]["marke"] >= r[1]["marke"],
           "die Ablage laesst sich wieder auflisten, neueste zuerst")
    pruefe(r[0]["verb"] == "paarvergleich" and r[0]["ausgang"] == "bestanden",
           "mit Verb und Ausgang je Eintrag")


# ── 2) Der Steckbrief rechnet NICHTS ────────────────────────────────────────
print("\n[2] Steckbrief — meldet, wertet nicht")

with tempfile.TemporaryDirectory() as tmp:
    leer = _projekt(tmp, "20260101_000000")
    sb = SB.steckbrief(leer, mit_laeufen=False)
    pruefe(sb["ok"] and not sb["kennwerte"],
           "ohne results.json gibt es KEINE Kennwerte — auch keine genaeherten")
    pruefe(all(not s["da"] for s in sb["gerechnet"]),
           "und keine Stufe gilt als gerechnet")
    pruefe(any("Noch nicht gerechnet" in w for w in sb["warnungen"]),
           "was fehlt, steht als fehlend da")
    pruefe(sb["maschine"]["pole"] == 8 and sb["maschine"]["nuten"] == 48,
           "die Maschine selbst steht trotzdem da (p=4 -> 8 Pole, 48 Nuten)")
    pruefe(abs(sb["maschine"]["luftspalt_mm"] - 0.7) < 1e-6,
           "der Luftspalt wird aus statorID/rotorOD gebildet, nicht geraten")

    voll = _projekt(tmp, "20260101_120000",
                    em={"x": 1}, structural_fem={"x": 1},
                    summary={"B_gap_T": 0.82, "safety_factor_fem": 2.4,
                             "structural_basis": "fem", "T_maxwell_Nm": 41.0})
    sb = SB.steckbrief(voll, mit_laeufen=False)
    k = {x["schluessel"]: x for x in sb["kennwerte"]}
    pruefe(k["B_gap_T"]["methode"] == "analytisch",
           "B_gap_T traegt seine Herkunft: ANALYTISCH, nicht aus dem Feld")
    pruefe(k["T_maxwell_Nm"]["methode"] == "fdm2d",
           "T_maxwell_Nm dagegen kommt aus dem geloesten Feld — beide stehen "
           "im selben summary und saehen sonst gleichwertig aus")
    import ema_db
    pruefe(all(x["methode"] == (ema_db.HERKUNFT.get(x["schluessel"]) or {})
               .get("methode", "unbekannt") for x in sb["kennwerte"]),
           "die Herkunft kommt aus ema_db.HERKUNFT — keine zweite Liste daneben")

    analytisch = _projekt(tmp, "20260101_130000",
                          summary={"structural_basis": "analytisch"})
    sb = SB.steckbrief(analytisch, mit_laeufen=False)
    pruefe(any("ANALYTISCH" in w for w in sb["warnungen"]),
           "structural_basis=analytisch wird ausdruecklich gewarnt — die Zahl "
           "sieht aus wie ein FEM-Ergebnis, ist aber die Ringformel")
    pruefe(any("nicht 'sicher'" in w for w in sb["warnungen"]),
           "und ein fehlender safety_factor_fem heisst 'keine FEM', nicht 'sicher'")

    # Elmer legt seine VTU eine Ebene tiefer -- ein flaches listdir meldete 0.
    tief = os.path.join(voll, "em3d", "results")
    os.makedirs(tief)
    open(os.path.join(tief, "case_t0001.vtu"), "w").write("x")
    pruefe(SB.steckbrief(voll, mit_laeufen=False)["bestand"]["vtu"] == 1,
           "3D-Feldnetze werden auch in em3d/results/ gefunden")

    text = SB.als_text(SB.steckbrief(voll, mit_laeufen=False))
    pruefe("STECKBRIEF" in text and "Kennwerte (mit Herkunft)" in text,
           "als Text gibt es genau das, was ein Agent vorliest")
    md = SB.als_markdown(SB.steckbrief(voll, mit_laeufen=False))
    pruefe(md.startswith("- Maschinenart:") and "Herkunft:" in md,
           "und als Stichpunkte fuer AGENTS.projekt.md")


# ── 3) Der Rueckweg: frueher gelaufene Zuege ────────────────────────────────
print("\n[3] Frueher gelaufene Zuege wieder aufrufen")


def _lauf_schreiben(ordner, marke, n_text=50):
    os.makedirs(ordner, exist_ok=True)
    ev = [{"i": 1, "art": "start", "t": 1000.0, "kopf": "hermes",
           "modell": "qwen-gross:latest", "projekt": ""},
          {"i": 2, "art": "frage", "t": 1001.0, "text": "rechne mir das durch"}]
    for i in range(n_text):
        ev.append({"i": 3 + i, "art": "text", "t": 1002.0 + i, "text": "x"})
    ev += [{"i": 900, "art": "ergebnis", "t": 1200.0, "name": "execute",
            "text": "fertig", "fehler": False},
           {"i": 901, "art": "bild", "t": 1201.0, "projekt": "p",
            "unter": "charts", "datei": "feld_linien.png"},
           {"i": 902, "art": "bereit", "t": 1202.0, "grund": "end_turn"}]
    with open(os.path.join(ordner, f"ereignisse_{marke}.jsonl"), "w") as f:
        for e in ev:
            f.write(json.dumps(e) + "\n")
    open(os.path.join(ordner, f"protokoll_{marke}.md"), "w").write("# Lauf\n")
    return ev


with tempfile.TemporaryDirectory() as tmp:
    alt_p, alt_f = ema_agent.PROJEKTE, ema_agent.FREIE_LAEUFE
    ema_agent.PROJEKTE = tmp
    ema_agent.FREIE_LAEUFE = os.path.join(tmp, "_agent_laeufe")
    try:
        d = _projekt(tmp, "20260101_120000")
        ev = _lauf_schreiben(os.path.join(d, "agent"), "20260101_121500")
        _lauf_schreiben(os.path.join(ema_agent.FREIE_LAEUFE, "20260102_090000"),
                        "20260102_090000")

        laeufe = ema_agent.laeufe_liste()
        pruefe(len(laeufe) == 2, "projektgebundene UND freie Laeufe stehen in der Liste")
        pruefe(laeufe[0]["marke"] == "20260102_090000", "neueste zuerst")
        frei = [l for l in laeufe if not l["projekt"]]
        pruefe(len(frei) == 1,
               "der Lauf ohne Projektbindung geht nicht verloren — gerade in ihm "
               "entsteht oft der Entwurf, auf den man zurueckkommt")

        l = [x for x in laeufe if x["projekt"]][0]
        pruefe(l["auftraege"] == ["rechne mir das durch"],
               "der gestellte Auftrag steht an der Uebersicht — daran erkennt "
               "man einen Lauf wieder, nicht an seiner Uhrzeit")
        pruefe(l["kopf"] == "hermes", "und welcher Agentenkopf ihn gefahren hat")
        pruefe(l["kacheln"] == 2 and l["bilder"] == 1,
               "Ergebnisse und Bilder werden gezaehlt")
        pruefe(abs(l["sekunden"] - 202.0) < 1.0, "die Dauer kommt aus den Zeitmarken")

        # Der teure Fehler: die Uebersicht darf NICHT alles einlesen.
        voll = ema_agent._lauf_kopfdaten(ev)
        knapp = ema_agent._lauf_ueberblick(
            os.path.join(d, "agent", "ereignisse_20260101_121500.jsonl"))
        pruefe(all(voll[k] == knapp[k] for k in
                   ("ereignisse", "kacheln", "bilder", "auftraege", "kopf")),
               "der sparsame Ueberblick liefert DASSELBE wie das volle Einlesen")

        a = ema_agent.lauf_lesen("20260101_120000", "20260101_121500")
        pruefe(a["ok"] and len(a["ereignisse_liste"]) == len(ev),
               "ein Lauf laesst sich vollstaendig zurueckholen")
        a = ema_agent.lauf_lesen("20260101_120000", "20260101_121500",
                                 max_ereignisse=5)
        pruefe(len(a["ereignisse_liste"]) == 5 and a["gekuerzt"]
               and a["ereignisse"] == len(ev),
               "und gedeckelt, ohne die wahre Zahl zu verschweigen")
        pruefe(a["ereignisse_liste"][-1]["art"] == "bereit",
               "beschnitten wird VORNE — das Ende ist das, worauf man zurueckkommt")

        for projekt, marke, was in (("../../etc", "20260101_121500", "Projektpfad"),
                                    ("20260101_120000", "../../passwd", "Laufkennung"),
                                    ("x/y", "20260101_121500", "Schraegstrich")):
            pruefe(ema_agent.lauf_lesen(projekt, marke)["ok"] is False,
                   f"eine Kennung aus der URL kommt nicht durch ({was})")
    finally:
        ema_agent.PROJEKTE, ema_agent.FREIE_LAEUFE = alt_p, alt_f


# ── 4) Der zweite Weg in die rechte Spalte: ueber die Platte ────────────────
print("\n[4] Ergebnisse ueber den Projektordner, nicht ueber den Agentenkopf")

with tempfile.TemporaryDirectory() as tmp:
    alt_p = ema_agent.PROJEKTE
    ema_agent.PROJEKTE = tmp
    try:
        d = _projekt(tmp, "20260101_120000")
        kopf = ema_agent.Kopf.__new__(ema_agent.Kopf)
        kopf._bild_marke = 0.0
        kopf._gesehen = set()
        gesendet = []
        kopf._sende = lambda art, **kw: gesendet.append({"art": art, **kw})

        SB.ablegen(d, "rotor-check", "ABGELEHNT:\n  ✗ Tasche schneidet den Ring",
                   ok=False)
        kopf._rechnungen_melden()
        pruefe(len(gesendet) == 1 and gesendet[0]["art"] == "ergebnis",
               "was ein Verb ablegt, erscheint als Ergebnis in der rechten "
               "Spalte — ohne dass der Agentenkopf es melden muss")
        pruefe(gesendet[0]["name"] == "rotor-check",
               "unter dem Namen des Verbs")
        pruefe("Tasche schneidet den Ring" in gesendet[0]["text"]
               and not gesendet[0]["text"].startswith("#"),
               "mit dem Wortlaut, ohne den Dateikopf doppelt zu zeigen")
        pruefe(gesendet[0]["ablage"].endswith(".txt")
               and "rechnungen" in gesendet[0]["ablage"],
               "und mit dem Ort, an dem es dauerhaft liegt")

        kopf._rechnungen_melden()
        pruefe(len(gesendet) == 1, "dieselbe Datei kommt kein zweites Mal")
    finally:
        ema_agent.PROJEKTE = alt_p


# ── 5) Der gemessene ACP-Fehler wird benannt, nicht ueberspielt ─────────────
print("\n[5] Hermes: Werkzeugaufrufe ohne Ergebnis")

h = ema_agent.HermesKopf.__new__(ema_agent.HermesKopf)
h._offene_wz = {}
h._bild_marke = time.time() + 3600      # keine echten Bilder in diese Pruefung
h._gesehen = set()
h._offen = []
h._zug_ts = 0.0
h._hermes_heim = lambda: ""             # ohne Ablage: nur der Platzhalter
gesendet = []
h._sende = lambda art, **kw: gesendet.append({"art": art, **kw})
upd = {"sessionUpdate": "tool_call", "toolCallId": "tc-1", "kind": "execute",
       "title": "terminal: cae_cli.py paarvergleich"}
h._verarbeiten({"method": "session/update", "params": {"update": upd}})
h._verarbeiten({"method": "session/update", "params": {"update": dict(
    upd, toolCallId="tc-2", title="read: AGENTS.md", kind="read")}})
pruefe(len(h._offene_wz) == 2,
       "offene Werkzeugaufrufe werden gemerkt (gemessen: hermes acp v0.20.5 "
       "schickt bei MEHREREN Werkzeugen je Zug kein tool_call_update)")

h._verarbeiten({"method": "session/update", "params": {"update": {
    "sessionUpdate": "tool_call_update", "toolCallId": "tc-1", "kind": "execute",
    "status": "completed",
    "content": [{"type": "content", "content": {"type": "text", "text": "fertig"}}]}}})
pruefe(len(h._offene_wz) == 1 and any(g["art"] == "ergebnis" for g in gesendet),
       "ein beantworteter Aufruf wird ausgetragen und als Ergebnis gezeigt")

gesendet.clear()
h._offene_werkzeuge_abschliessen()
pruefe(len(gesendet) == 1 and gesendet[0]["art"] == "ergebnis",
       "der unbeantwortete bekommt am Zugende eine eigene Kachel")
pruefe("KEIN Ergebnis" in gesendet[0]["text"]
       and "read: AGENTS.md" in gesendet[0]["text"],
       "die sagt, dass das Ergebnis hier NICHT bekannt ist — statt zu schweigen "
       "oder etwas zu erfinden")
pruefe("hermes acp v0.20.5" in gesendet[0]["text"],
       "und nennt die gemessene Ursache, damit sie nicht bei uns gesucht wird")
pruefe(h._offene_wz == {}, "danach ist die Liste leer, nicht doppelt gemeldet")


# ── 6) Die CLI ─────────────────────────────────────────────────────────────
print("\n[6] Die CLI")

quelle = open(os.path.join(HIER, "cae_cli.py"), encoding="utf-8").read()
p = cae_cli.build_parser()
a = p.parse_args(["steckbrief", "20260101_120000", "--laeufe"])
pruefe(a.fn is cae_cli.cmd_steckbrief and a.laeufe,
       "`steckbrief` ist als Verb verdrahtet")

for verb in ("paarvergleich", "screen", "rotor-check", "sicherheit", "feldbild"):
    args = p.parse_args([verb, "--ohne-ablage"] +
                        ([] if verb == "sicherheit" else ["--frisch"]))
    pruefe(getattr(args, "ohne_ablage", False) is True,
           f"`{verb} --ohne-ablage` schaltet die Ablage ab (Vorgabe ist AN)")

for verb in ('"paarvergleich"', '"screen"', '"rotor-check"', '"sicherheit"',
             '"feldbild"'):
    pruefe(f"_ablegen(args, {verb}" in quelle,
           f"{verb} legt sein Ergebnis ins Projekt")

pruefe("import ema_steckbrief" in quelle and "def _projekt_pfad" in quelle
       and quelle.count("if kennung == \"last\"") == 0,
       "'last' wird an EINER Stelle aufgeloest (ema_steckbrief), nicht zweimal")

skill = open(os.path.join(os.path.dirname(HIER),
                          ".agents/skills/cae-orchestrator/SKILL.md"),
             encoding="utf-8").read()
pruefe("steckbrief" in skill,
       "das Verb steht in der EINEN SKILL.md, die beide Koepfe lesen")


# ── 7) Die Routen ──────────────────────────────────────────────────────────
print("\n[7] Routen")

srv = open(os.path.join(HIER, "server.py"), encoding="utf-8").read()
for route in ("/agent/laeufe", "/agent/lauf", "/agent/steckbrief"):
    pruefe(f'@app.route("{route}")' in srv, f"{route} gibt es")
pruefe("laeufe_liste" in srv and "lauf_lesen" in srv,
       "und sie greifen auf ema_agent zu, statt selbst im Dateisystem zu suchen")


# ── 8) Die Seite: EIN Satz Zeichenfunktionen ───────────────────────────────
print("\n[8] Agentenseite")

html = open(os.path.join(HIER, "ema_agent.html"), encoding="utf-8").read()
pruefe('id="archiv"' in html and 'id="a_liste"' in html,
       "es gibt eine Archivansicht")
pruefe("let SPALTEN" in html and "$(SPALTEN.l)" in html and "$(SPALTEN.r)" in html,
       "sie rendert ueber DIESELBEN Funktionen wie der laufende Strom — ein "
       "zweiter Satz liefe mit dem ersten auseinander")
pruefe("#archiv{position:fixed" in html,
       "und liegt ueber der ganzen Seite, nicht in der Buehne: gesucht wird sie "
       "gerade dann, wenn kein Agent laeuft")
pruefe(html.index('id="b_archiv_kopf"') < html.index('id="buehne"'),
       "der Knopf dazu steht in der Kopfzeile, also auch vor dem ersten Start")
pruefe("e.ablage ?" in html and "im Projekt:" in html,
       "eine Kachel aus der Ablage zeigt, WO das Ergebnis dauerhaft liegt")
pruefe("archivZeigen" in html and "verarbeitenStumm" in html,
       "ein alter Lauf faerbt die Anzeige des laufenden nicht um "
       "(eigene, stumme Verarbeitung)")

# ── 9) Der Skill muss auffindbar bleiben, auch ohne skill_view ─────────────
print("\n[9] Der Weg zum Skill")

# Gemessen am 04.09.2026: `skill_view("cae-orchestrator")` scheitert in
# `hermes acp` v0.20.5 mit "not found", obwohl `hermes skills list` den Skill
# zeigt und derselbe Aufruf in einem gewoehnlichen Python-Prozess mit demselben
# HERMES_HOME und demselben Arbeitsverzeichnis gelingt (mit eigenem ACP-Klienten
# nachgestellt, also nicht von diesem Repo verursacht). Der Agent muss den Skill
# trotzdem bekommen -- ueber den Dateipfad, der in JEDER Startunterlage steht.
WURZEL = os.path.dirname(HIER)
PFAD = ".agents/skills/cae-orchestrator/SKILL.md"
pruefe(os.path.isfile(os.path.join(WURZEL, PFAD)),
       "der Skill liegt an dem Pfad, auf den verwiesen wird")

agents = open(os.path.join(WURZEL, "AGENTS.md"), encoding="utf-8").read()
pruefe(PFAD in agents and "skill_view" in agents,
       "AGENTS.md nennt den Dateipfad UND den gemessenen Fehlgriff")

quelle_agent = open(os.path.join(HIER, "ema_agent.py"), encoding="utf-8").read()
pruefe(PFAD in quelle_agent and "## Der Skill" in quelle_agent,
       "die im Browser erzeugte Projektakte nennt ihn ebenfalls — sie ist die "
       "einzige Unterlage, die bei JEDEM Start neu entsteht")

for skript in ("start_agent.sh", "start_hermes.sh"):
    t = open(os.path.join(WURZEL, skript), encoding="utf-8").read()
    pruefe(PFAD in t, f"{skript} schreibt ihn in die Projektakte des Terminalkopfs")

# ── 10) Vorgabe aus dem Designer und die Projektbeschreibung ───────────────
print("\n[10] Vorgabe, Beschreibung — einmal eingeben, nicht zweimal")

with tempfile.TemporaryDirectory() as tmp:
    d = _projekt(tmp, "20260101_140000")
    akte = json.load(open(os.path.join(d, "project.json")))
    akte["design"] = {"brief": "80 kW Peak, 1200 kg, guenstig.\n\nGrob "
                               "vorgezeichnet: 8 Pole, V-Form.",
                      "source": "designer", "vorgabe": True}
    json.dump(akte, open(os.path.join(d, "project.json"), "w"))

    sb = SB.steckbrief(d, mit_laeufen=False)
    pruefe(sb["vorgabe"] is True,
           "eine im Designer uebergebene Geometrie ist als VORGABE markiert")
    pruefe("80 kW Peak" in sb["auftrag"] and "8 Pole" in sb["auftrag"],
           "Projektbeschreibung UND Designerzusatz stehen beide im Auftrag — "
           "der zweite darf den ersten nicht loeschen")

    md = SB.als_markdown(sb)
    pruefe("VORGABE, kein Altbestand" in md,
           "die Projektakte sagt ausdruecklich, dass die Geometrie GEWOLLT ist")
    pruefe("`--frisch` gebaut wurde" in md,
           "und grenzt sie gegen den Fall ab, gegen den --frisch gebaut wurde — "
           "eine ignorierte Vorgabe aergert mehr als eine geerbte Altgeometrie")
    kopf = [z for z in md.splitlines() if z.startswith("- **Auftrag")]
    pruefe(len(kopf) == 1 and not any(
        z and not z.startswith((" ", "-")) for z in md.splitlines()),
        "ein mehrzeiliger Auftrag zerreisst die Aufzaehlung nicht")

    ohne = _projekt(tmp, "20260101_150000")
    pruefe(SB.steckbrief(ohne, mit_laeufen=False)["vorgabe"] is False,
           "ein gewoehnliches Projekt bleibt ausdruecklich KEINE Vorlage")

quelle_srv = open(os.path.join(HIER, "server.py"), encoding="utf-8").read()
pruefe('@app.route("/agent/vorgabe"' in quelle_srv,
       "es gibt eine Route, die gezeichnete Geometrie uebergibt — ohne Lauf")
pruefe("body.get(\"brief\")" in quelle_srv,
       "/project/new nimmt die Beschreibung an und legt sie nach design.brief")
pruefe("gibt es nicht." in quelle_srv,
       "ein Agentenstart auf ein Projekt, das es nicht gibt, wird abgewiesen "
       "statt einen Scheinordner anzulegen")

ema = open(os.path.join(HIER, "ema.html"), encoding="utf-8").read()
pruefe("dsnAnAgent" in ema and "/agent/vorgabe" in ema,
       "der Designer hat den Uebergabeknopf")
pruefe("brief: notes" in ema,
       "die Beschreibung beim Anlegen geht als Auftrag mit — nicht nur als Notiz")


# ── 11) Die Arbeitsleiste ──────────────────────────────────────────────────
print("\n[11] Arbeitsleiste")

import ema_arbeit
st = ema_arbeit.stand({"Analyse": {"status": "idle"},
                       "3D-Feld": {"status": "running", "progress": 42}})
pruefe(st["rechnung"]["an"] is True
       and st["rechnung"]["was"][0]["name"] == "3D-Feld"
       and st["rechnung"]["was"][0]["fortschritt"] == 42,
       "eine laufende Rechnung wird mit Namen und Fortschritt gemeldet")
pruefe(all(s["name"] != "Analyse" for s in st["rechnung"]["was"]),
       "eine untaetige nicht")
for feld in ("recherche", "gpu", "modell", "loeser"):
    pruefe(feld in st, f"die Leiste meldet '{feld}'")
pruefe("denkt" not in json.dumps(st, ensure_ascii=False),
       "sie behauptet NICHT, das Modell denke — Ollama meldet nur, was GELADEN "
       "ist, nicht was rechnet")

alt_puls = ema_arbeit.PULS_DATEI
with tempfile.TemporaryDirectory() as tmp:
    ema_arbeit.PULS_DATEI = os.path.join(tmp, "recherche.puls")
    try:
        pruefe(ema_arbeit.recherche_laeuft()["an"] is False,
               "ohne Puls laeuft keine Recherche")
        ema_arbeit.puls()
        pruefe(ema_arbeit.recherche_laeuft()["an"] is True,
               "nach einem Puls schon — gesetzt von der Stelle, die WIRKLICH "
               "ins Netz greift, nicht aus dem Werkzeugtext geraten")
    finally:
        ema_arbeit.PULS_DATEI = alt_puls

quelle_rech = open(os.path.join(HIER, "ema_recherche.py"), encoding="utf-8").read()
pruefe(quelle_rech.count("_arbeit_puls()") >= 4,
       "suche, hole und hole_bild setzen den Puls (plus der Helfer selbst)")

t0 = time.time()
for _ in range(5):
    ema_arbeit.stand({})
dauer = (time.time() - t0) / 5 * 1000
pruefe(dauer < 60,
       f"ein Abruf kostet {dauer:.0f} ms — die Leiste wird im Sekundentakt "
       f"abgefragt, teuer darf sie nicht sein")

pruefe('@app.route("/agent/arbeit")' in quelle_srv, "die Route gibt es")
pruefe("ema_arbeit.stand({" in quelle_srv,
       "der Server reicht seine Zustandsdicts herein, statt dass das Messmodul "
       "ihn importiert (Importzirkel, und ohne Flask nicht pruefbar)")

pruefe('id="arbeit"' in html and "arbeitHoehe" in html,
       "die Seite hat die Leiste und gleicht ihre Hoehe an")
pruefe("block_eingabe" in html and "block_hinweis" in html
       and "offsetHeight" in html,
       "und zwar GEMESSEN an den beiden Eingabebloecken links, nicht geraten")
pruefe("document.hidden" in html,
       "im verdeckten Reiter wird nicht abgefragt — eine Anzeige ist kein "
       "Messgeraet")

# ── 12) Die stummen Werkzeuge nachlesen, statt sie zu beschriften ──────────
print("\n[12] Nachlese aus Hermes' Sitzungsablage")

# Der ACP-Fehler bleibt (er ist stromaufwaerts), aber die Ergebnisse SIND da:
# Hermes schreibt sie in state.db, denn das Modell bekommt sie ja auch. Also
# werden sie von dort geholt statt nur benannt.
zerlegen = ema_agent._zerlegen
pruefe(zerlegen('{"output": "hallo", "exit_code": 0}') == ["hallo"],
       "ein Terminalergebnis wird ausgepackt")
pruefe(zerlegen('{"content": "1|zeile", "total_lines": 1}') == ["1|zeile"],
       "ein Dateilesen ebenso (`content` statt `output`)")
pruefe(zerlegen('{"output": "a"}\n{"output": "b"}') == ["a", "b"],
       "MEHRERE hintereinander geschriebene Objekte werden alle gefunden — "
       "genau der Fall, um dessentwillen nachgelesen wird")
mit_rest = zerlegen('{"output": "a"}\n\n[Subdirectory context discovered: x]\nlang')
pruefe(len(mit_rest) == 1 and mit_rest[0].startswith("a")
       and "Kontext" in mit_rest[0],
       "angehaengter Modellkontext landet NICHT in der Ergebniskachel — wird "
       "aber gemeldet statt verschluckt")
pruefe("(Exit 3)" in zerlegen('{"output": "x", "exit_code": 3}')[0],
       "ein Exit-Code ungleich 0 steht dabei")
pruefe(zerlegen("kein json") == ["kein json"],
       "was sich nicht lesen laesst, wird roh durchgereicht")

with tempfile.TemporaryDirectory() as tmp:
    import sqlite3
    heim = os.path.join(tmp, "hermes")
    os.makedirs(heim)
    db = sqlite3.connect(os.path.join(heim, "state.db"))
    db.execute("create table messages (id integer primary key, session_id text, "
               "role text, content text, tool_name text, timestamp real)")
    db.execute("create table session_model_usage (session_id text, task text, "
               "input_tokens int, output_tokens int, api_call_count int)")
    db.executemany("insert into messages (session_id, role, content, tool_name, "
                   "timestamp) values (?,?,?,?,?)", [
        ("s1", "tool", '{"output": "ERGEBNIS EINS", "exit_code": 0}', "terminal", 100.0),
        ("s1", "tool", '{"content": "ERGEBNIS ZWEI"}', "read_file", 101.0),
        ("s1", "tool", '{"output": "ZU ALT"}', "terminal", 10.0),
    ])
    db.executemany("insert into session_model_usage values (?,?,?,?,?)", [
        ("s1", "", 1000, 500, 2), ("s1", "title_generation", 50, 10, 1)])
    db.commit(); db.close()

    h = ema_agent.HermesKopf.__new__(ema_agent.HermesKopf)
    h._hermes_heim = lambda: heim
    h._sid = "s1"
    h._tempo_probe = None

    erg = h._ergebnisse_nachlesen(99.0)
    pruefe([e["text"] for e in erg] == ["ERGEBNIS EINS", "ERGEBNIS ZWEI"],
           "die Ergebnisse dieses Zuges kommen zurueck, in der Reihenfolge")
    pruefe(all(e["text"] != "ZU ALT" for e in erg),
           "aeltere aus demselben Sitzungsverlauf nicht")
    pruefe(erg[1]["name"] == "read_file", "mit dem Werkzeugnamen")

    h._offene_wz = {"tc-1": "terminal: cae_cli.py health",
                    "tc-2": "read: SKILL.md"}
    h._zug_ts = 99.0
    gesendet = []
    h._sende = lambda art, **kw: gesendet.append({"art": art, **kw})
    h._offene_werkzeuge_abschliessen()
    pruefe(len(gesendet) == 2 and all(g["art"] == "ergebnis" for g in gesendet),
           "beide stummen Aufrufe bekommen eine Kachel")
    pruefe("ERGEBNIS EINS" in gesendet[0]["text"]
           and "ERGEBNIS ZWEI" in gesendet[1]["text"],
           "und darin steht das ECHTE Ergebnis, nicht mehr nur die Erklaerung, "
           "warum keines da ist")
    pruefe(all(g.get("nachgelesen") for g in gesendet),
           "als nachgelesen gekennzeichnet")

    h._offene_wz = {"tc-9": "terminal: irgendwas"}
    h._zug_ts = 10_000.0            # nichts in der Ablage aus diesem Zeitraum
    gesendet.clear()
    h._offene_werkzeuge_abschliessen()
    pruefe(len(gesendet) == 1 and "KEIN Ergebnis" in gesendet[0]["text"],
           "findet die Nachlese nichts, steht wieder der ehrliche Platzhalter da")

    t1 = h.tempo()
    pruefe(t1["da"] and t1["aus"] == 500 and t1["ein"] == 1000,
           "das Tempo kommt aus Hermes' eigener Buchfuehrung (exakte Token, "
           "nicht aus Zeichen hochgerechnet)")
    pruefe(t1["tok_s"] is None, "die erste Messung hat noch keine Rate")
    time.sleep(0.7)
    pruefe(h.tempo()["tok_s"] == 0.0,
           "die zweite schon — hier 0, weil nichts dazugekommen ist")

pruefe(ema_agent.Kopf.tempo(ema_agent.PiKopf())["da"] is False,
       "PI fuehrt keine Token mit, und es wird auch nichts geschaetzt")

pruefe("ZTEMPO" in html and "Z/s (Zeichen)" in html,
       "wo kein Tokentempo da ist, misst die Seite ZEICHEN und sagt das auch")
pruefe("Tok/s" in html, "wo eines da ist, steht es in Token")

# ── 13) Ein Zug, der nie endet ─────────────────────────────────────────────
print("\n[13] Haengender Zug — sichtbar und loesbar")

k = ema_agent.PiKopf()
k.laeuft = True
k.proc = None
pruefe(k.freigeben() == {"ok": True, "war_gesperrt": False},
       "ohne Sperre ist Freigeben ein Nichtstun")

k.beschaeftigt = True
k.zug_ab = time.time() - 900
k.letztes_ts = time.time() - 700
z = k.zustand()
pruefe(z["beschaeftigt"] and z["still_sek"] > 600,
       "der Zustand sagt, wie lange schon NICHTS mehr kam — vorher war ein "
       "haengender Zug von einem langen nicht zu unterscheiden")
pruefe(z["zug_sek"] > 800 and z["prozess_lebt"] is False,
       "dazu die Zugdauer und ob der Prozess ueberhaupt noch lebt")

a = k.freigeben()
pruefe(a["ok"] and a["war_gesperrt"] and a["still_sek"] > 600,
       "die Sperre laesst sich loesen, ohne den Agenten zu beenden")
pruefe(k.beschaeftigt is False, "danach nimmt er wieder Auftraege an")
arten = [e["art"] for e in k.ring]
pruefe(arten == ["fehler", "bereit"],
       "im Verlauf steht, DASS von Hand geloest wurde, und dann erst 'bereit'")
pruefe("laeuft weiter" in k.ring[0]["text"],
       "und dass der Agent WEITERLAEUFT — ein stiller Neustart des Zuges waere "
       "schlimmer, dann liefen zwei nebeneinander")
pruefe(k.freigeben()["war_gesperrt"] is False, "zweimal loesen tut nichts")

k.laeuft = False
pruefe(k.freigeben()["ok"] is False, "ohne laufenden Agenten gibt es nichts zu loesen")

pruefe('@app.route("/agent/freigeben"' in quelle_srv, "die Route gibt es")
pruefe('stand["kopf"] = {' in quelle_srv,
       "die Arbeitsleiste bekommt den Kopfzustand mitgeliefert")

pruefe("STILL_WARNUNG = 120" in html and "STILL_FREIGABE = 450" in html,
       "die Schwellen liegen UEBER der Dauer eines langen Werkzeugaufrufs "
       "(Hermes laesst eines bis 420 s laufen) — darunter waere die Warnung "
       "ein Fehlalarm")
pruefe("still seit" in html and "🔓 Sperre lösen" in html,
       "die Leiste zeigt die Stille und bietet erst dann das Loesen an")
pruefe("pille.textContent = 'still seit '" in html,
       "auch die Pille oben wird korrigiert — sie sagte unbeirrt 'arbeitet'")

# ── 14) Aufnahme: Marken statt Pausen ──────────────────────────────────────
print("\n[14] Bildschirmaufnahme — die Momente rechts")

# Die alte Regel war "Server rechnet -> Pause", begruendet damit, am Bild aendere
# sich dann nichts. Gemessen falsch: im Lauf vom 04.09. kamen MITTEN im
# Rechenlauf fuenf Bilder in die rechte Spalte. Angehalten wurde also genau
# waehrend der Momente, die aufzuheben sich lohnt.
pruefe("z.rechnet" not in html,
       "die Aufnahme richtet sich NICHT mehr danach, ob der Server rechnet")
pruefe("REK_NACHLAUF" in html and "rekTaetig(" in html,
       "sondern nach Taetigkeit in der Ergebnisspalte")
pruefe("k.dataset.markeArt = 'bild'" in html
       and "k.dataset.markeArt = e.fehler ? 'fehler' : 'ergebnis'" in html,
       "jede Kachel und jedes Bild setzt eine Marke")
pruefe("function rekVideoS" in html and "REK_PAUSE_S" in html,
       "die Marke traegt die VIDEOsekunde, nicht die Uhrzeit — nach einer Pause "
       "laegen die beiden auseinander")
pruefe('id="c_luecken"' in html and "luecken.checked" in html,
       "und die Pause laesst sich ganz abschalten: mit der Markenliste ist sie "
       "nur noch Platzersparnis, kein Zwang")

with tempfile.TemporaryDirectory() as tmp:
    v = ema_agent.Aufnahme()
    v.starten(projekt="probe", ordner=tmp)
    v.anhaengen(b"x" * 64)
    pruefe(v.marke("bild", "em_field.png", video_s=12.0)["ok"],
           "eine Marke laesst sich setzen")
    v.marke("ergebnis", "sicherheit: 2 Kriterien verletzt", video_s=20.0)
    v.marke("bild", "em_curve.png", video_s=400.0)
    e = v.beenden()
    pruefe(e["n_marken"] == 3 and os.path.isfile(e["marken"]),
           "beim Beenden entsteht die Markenliste neben der Aufnahme")
    tsv = open(e["marken"], encoding="utf-8").read()
    pruefe("12.00\t" in tsv and "em_curve.png" in tsv,
           "mit Videosekunde und Beschriftung je Marke")
    pruefe(e["stuecke"] == 2,
           "benachbarte Marken werden zu EINEM Stueck verschmolzen, entfernte "
           "nicht (12 s und 20 s zusammen, 400 s eigenes)")
    skript = open(e["schnitt"], encoding="utf-8").read()
    pruefe(skript.startswith("#!/usr/bin/env bash") and "ffmpeg" in skript,
           "und ein fertiges ffmpeg-Skript — eine Liste von Zeitpunkten ist "
           "noch keine Arbeit, die jemand gern von Hand macht")
    pruefe("-ss 6.00 -t 26.00" in skript,
           "geschnitten wird mit Vor- und Nachlauf um die Marke herum")
    pruefe("-c:v libvpx-vp9" in skript and "-ss 6.00 -t 26.00 -i " in skript,
           "neu kodiert statt kopiert: `-c copy` schnitte an Schluesselbildern "
           "und traefe den Moment um Sekunden daneben")
    pruefe(os.access(e["schnitt"], os.X_OK), "das Skript ist ausfuehrbar")
    import subprocess as _sp
    pruefe(_sp.run(["bash", "-n", e["schnitt"]]).returncode == 0,
           "und syntaktisch gueltig")

    leer = ema_agent.Aufnahme()
    leer.starten(projekt="leer", ordner=tmp)
    leer.anhaengen(b"x")
    e2 = leer.beenden()
    pruefe(e2["stuecke"] == 0 and "Keine Marken" in open(e2["schnitt"]).read(),
           "ohne Marken sagt das Skript das, statt ein leeres Video zu bauen")

pruefe('@app.route("/agent/video/marke"' in quelle_srv, "die Route gibt es")

print(f"\n{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
