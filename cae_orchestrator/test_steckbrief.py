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

print(f"\n{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
