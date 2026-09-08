# ai-workspace

*[English version →](README.md)*

Monorepo für die E-Maschinen-CAE-Toolkette (IPM-Traktionsmotoren): Geometrie →
EM-Feld → Struktur-FEM → Thermik → Fahrzyklus → PDF-Bericht. Betrieben unter einem
eingeschränkten User (kein sudo), bedienbar im Browser, über die Kommandozeile oder
von einem **lokalen** Sprachmodell.

**Gerechnet wird ausschließlich lokal.** Nach außen geht nur zweierlei: die
Agenten-Recherche (siehe unten) und — technisch bedingt — der Server selbst, der auf
allen Schnittstellen lauscht (siehe „Netzsichtbarkeit").

**Ehrlich vorweg, damit die Tabelle nicht mehr verspricht als sie hält:** getragen
wird die Kette von `cae_orchestrator`. Die übrigen Ordner sind eigenständige
Teilprojekte in unterschiedlichem Reifegrad, die *heute* nicht miteinander
verdrahtet sind — siehe die Spalte „Verbindung".

**Stichworte:** E-Maschine · IPM · PMSM · Traktionsmotor · Motorauslegung · CAE · FEM ·
CalculiX · Z88Aurora · FreeCAD · Gmsh · Elmer · OpenFOAM · Elektromagnetik ·
2D-FDM-Feldlöser · Topologieoptimierung (SKO/SIMP) · Fliehkraft-Rotorfestigkeit ·
Wärmenetzwerk · Fahrzyklus (WLTP) · lokales Sprachmodell · Ollama · Agenten-Skill ·
PI · Hermes Agent · Herkunftsnachweis · SQLite

## Teilprojekte

| Ordner | Was | Stack | Start |
|---|---|---|---|
| `cae_orchestrator/` | Browser-CAE für IPM-Motoren (Geometrie → EM-Feld → FEM → Thermik → Fahrzyklus, PDF-Bericht) | Python/Flask + FreeCAD/Elmer/OpenFOAM/Blender | `cd cae_orchestrator && ./start.sh` → http://localhost:5000 |
| `connection_detection/` | FreeCAD-Workbench: Verbindungserkennung in STEP-Baugruppen (Basis für Multi-Body-CalculiX) | Python-FreeCAD-Addon (`rtree`) | via `FreeCADCmd cli.py -- input.step -o out.json` |
| `pikogk/` | PicoGK-Geometriekernel mit HTTP-API (Voxel-/Implicit-Geometrie, „Engine-Head"-Skills für Zylinderköpfe) | .NET 9 + native `picogk.so` | `cd pikogk && ./start.sh` → http://localhost:5266 |
| `physics_surrogate/` | ML-Surrogat für die 2D-FDM-Feldstufe (PhysicsNeMo/Torch) | Python + Torch/CUDA | `cd physics_surrogate && ./start.sh` → http://localhost:5300 |
| `lego/` | LEGO-Technic-Mechaniken per LLM, bewertet an ORCA-Handkinematik | Python + BrickNet | — (CLI) |

## Zusammenspiel — was wirklich verdrahtet ist

| Verbindung | Stand |
|---|---|
| `cae_orchestrator` → **Ollama** `:11434` | **vorhanden** — Bericht, Chat, KI-Auslegung, Zielwertoptimierung, RAG-Embeddings |
| `cae_orchestrator` → **physics_surrogate** `:5300` | **nur lesend** — der Tab 🧠 KI-Training zeigt Trainingsläufe und pollt `/health` (`ema_ki_training.py`). Einen Inferenzpfad gibt es nicht: `/predict/*` antwortet fest mit 503, ein `ema_surrogate.py` existiert nicht. Umgekehrt benutzt der Datensatzgenerator die **echte** Rasterisierung des Orchestrators über `PYTHONPATH` |
| `cae_orchestrator` ↔ **pikogk** `:5266` | **nicht vorhanden.** Im Orchestrator steht kein einziger Verweis auf `:5266` oder `pikogk`. `pikogk/INTEGRATION.md` beschreibt den HTTP-Vertrag *für den Fall*, dass die Kopplung einmal gebaut wird — sie ist es nicht. Auch fachlich disjunkt: Zylinderköpfe gegen IPM-E-Maschinen |
| `cae_orchestrator` ↔ **connection_detection** | **nicht vorhanden.** Der JSON-Export trägt `tie`/`contact`-Marken für Multi-Body-CalculiX, aber der Verbraucher ist nirgends geschrieben — der Export endet heute in der Datei. Geteilt wird nur die FreeCAD-Toolchain |
| `lego/` | eigenständig, kein Dienst, keine Abhängigkeit zu den übrigen |

## Agentenbedienung (lokales Modell, kein Cloud-Zugang)

Die Toolkette lässt sich außer im Browser auch von einem **lokalen** Sprachmodell
bedienen — wahlweise über [PI](https://pi.dev) (`@earendil-works/pi-coding-agent`)
oder über **Hermes Agent** (Nous Research). Beide laufen auf demselben Ollama-Modell
und lesen **denselben** Skill aus `.agents/skills/` — es wird nichts kopiert und
nichts verlinkt, also können sie nicht auseinanderlaufen. Je eine Zeile startet die
ganze Kette:

```bash
./start_agent.sh                          # Orchestrator (falls nötig) + PI, interaktiv
./start_agent.sh -p "Wie hoch ist B_gap im neuesten Projekt?"
./start_agent.sh --weiter                 # letzte Sitzung fortsetzen
./start_agent.sh --sitzungen              # Sitzungen dieses Ordners auflisten

./start_hermes.sh                         # dasselbe mit Hermes
./start_hermes.sh -z "Wie hoch ist B_gap im neuesten Projekt?"
./start_hermes.sh --projekt Alpenpass     # Hermes an ein CAE-Projekt binden
./start_hermes.sh --nur-pruefen           # nur der Nachweis, dass nichts nach draußen geht
```

**Welches Projekt?** Hermes fragt das am Terminal jetzt zuerst — eine Liste der acht
jüngsten Projekte mit Rechenstand und dem Datum ihres Hermes-Speichers, dazu
„gemeinsamer Speicher" als Ausweg. PI nimmt weiterhin einfach das jüngste, und das ist
kein Versehen: PIs Gedächtnis hängt nicht am Projekt, Hermes' schon. Wer bei Hermes im
falschen Projekt landet, bekommt das Gelernte einer anderen Auslegung als Tatsache
serviert und merkt es nicht. Gefragt wird nur ohne `--projekt`/`--kein-projekt` und nur
am Terminal; Vorgabe ist das jüngste Projekt, also das bisherige Verhalten.

**Neue oder alte Sitzung?** Beide Köpfe können fortsetzen, gefragt hat es aber keiner —
und was nicht gefragt wird, wird nicht benutzt: jede Frage fing bei null an, obwohl
nebenan die Sitzung mit dem ganzen Verlauf lag. Beide zeigen jetzt am Terminal ein kurzes
Menü, **Vorgabe neu**. Und wenn es nichts fortzusetzen gibt, steht das jetzt auch da:
bei projekteigenem Speicher ist ein frisches Projekt immer leer, das Menü erschien also
nie — was von einem kaputten Menü nicht zu unterscheiden war. Automatisch fortsetzen wäre falsch — ein mitgeschleppter Verlauf
fällt bei 65 k Kontext erst auf, wenn vorne etwas herausfällt; fragen ist der Mittelweg.
Nicht gefragt wird ohne Terminal, bei einer Einmalfrage (`-p`/`-z`) und wenn der Aufrufer
die Sitzungsflaggen selbst gesetzt hat — ein Skriptaufruf darf nicht blockieren.

**Hermes führt Erinnerungen und Sitzungen je Projekt.** Sein eingebauter Speicher ist
sonst *eine* Datei für die ganze Maschine (`~/.hermes/memories/MEMORY.md`, 2200 Zeichen),
und die Konfiguration bietet keinen Weg, ihn zu trennen — der Agent läse bei der nächsten
Auslegung als Tatsache wieder, was er bei der vorigen gelernt hat. Der Hebel ist
`HERMES_HOME`, es verschiebt aber die *ganze* Ablage, und eine je Projekt kopierte
`config.yaml` wäre genau die Drift, die dieses Repo beim Skill vermeidet. Also aufgeteilt:
`config.yaml`, `.env` und `skills` werden **verlinkt** (eine Quelle), projekteigen sind nur
`memories/` und `sessions/` unter `<projekt>/_agent/hermes/`. **PI bekommt das nicht**,
und das ist kein Versäumnis: PI sortiert Sitzungen nach Arbeitsverzeichnis, und das muss
die Repo-Wurzel bleiben, sonst findet PI weder `AGENTS.md` noch die Skills.

**Der Projektkontext wird erzeugt, nicht kopiert.** `AGENTS.md` bleibt die eine,
unveränderte Regelquelle und wird nie in ein Projektverzeichnis kopiert — eine Kopie läuft
still auseinander, und dann arbeiten zwei Agentenköpfe nach zwei Regelwerken, die beide
plausibel aussehen. Stattdessen entsteht bei jedem Start frisch `AGENTS.projekt.md` (nicht
versioniert) mit den Fakten des aktuellen Projekts: Kennung, Verzeichnis, vorhandene
Kennwerte — und vor allem, **welche Stufen noch nicht gerechnet sind**. Sie sagt
ausdrücklich, wenn eine Festigkeitszahl analytisch statt aus der FEM stammt; das sieht in
der Ausgabe gleich aus und ist in diesem Repo schon dreimal unbemerkt durchgerutscht.

Beide beantworten dieselbe Frage mit derselben Zahl (gemessen: **0,806 T**, beide
samt Herkunftshinweis auf die analytische Luftspaltformel). `start_hermes.sh`
**misst** vor jedem Start, dass Hermes ausschließlich `127.0.0.1:11434` anspricht —
dessen mitgelieferte Vorgabe zeigt auf OpenRouter, und zwei offene Fehler im Projekt
lassen `provider: ollama` still dorthin durchfallen. Einzelheiten in
`.agents/README.md`.

Das Skript prüft Ollama, **nagelt das Modell auf seine ID fest** (ein `ollama pull` unter
gleichem Namen tauscht sonst still die Gewichte), startet den Server nur, wenn `:5000`
nicht antwortet, und wartet auf dessen Erreichbarkeit, bevor PI läuft.

| Teil | Wo | Was |
|---|---|---|
| `start_agent.sh` | Wurzel | Startkette + Sitzungsverwaltung (mit Sitzungsmenü) |
| `.agents/projektstand.py` | Wurzel | erzeugt den Projektblock für `AGENTS.projekt.md` — beide Köpfe benutzen denselben Erzeuger, sehen also denselben Stand |
| `.agents/` | Wurzel | Skill-Definition für PI (`skills/cae-orchestrator/SKILL.md`) und Einrichtung |
| `cae_orchestrator/cae_cli.py` | Teilprojekt | die Kommandozeile, die beide Agenten benutzen — **achtzehn Verben**: neun über HTTP auf `:5000` (`status/health/geom/run/wait/results/projects/raw/routes`), neun lokal (`paarvergleich`, `rotor-check`, `screen`, `bilddaten`, `struktur`, `topopt`, `db`, `lernen`, `recherche`) |
| `start_hermes.sh` | Wurzel | zweiter Agentenkopf: **Hermes Agent**, gleiches Modell, gleicher Skill, mit gemessenem Netznachweis; Projektbindung über `HERMES_HOME` |

**Warum eine CLI und kein MCP-Server:** ein lokales Modell kann die ~135 HTTP-Routen des
Orchestrators nicht als 135 Werkzeugschemata im Kontext halten. PI bindet Werkzeuge
deshalb als *Skill = CLI + README*; `cae_cli.py` filtert Base64-Nutzlasten heraus, kappt
die Ausgabe und trägt den Zustand im Exit-Code. Details in `.agents/README.md`.

**Modell:** `qwen-gross:latest` (Qwen3.5 27B Q4_K_M, 64 k Kontext) — dasselbe Modell, das
auch Bericht, Chat und KI-Auslegung im Orchestrator benutzen. Eine Quelle dafür:
`ema_report.DEFAULT_MODEL` / `DEFAULT_NUM_CTX`, umstellbar über `CAE_LLM_MODEL` bzw.
`CAE_LLM_NUM_CTX` ohne Codeänderung.

## Was hier anders ist: jede Zahl sagt, woher sie kommt

Dieselbe Größe lässt sich auf mehreren Stufen gewinnen, und die Wahl ist eine Abwägung
zwischen Zeit und Aussagekraft. **Welche Stufe eine Zahl geliefert hat, wird je Wert
festgehalten** — nicht hinterher geraten:

| Größe | schnell | genauer | am schärfsten |
|---|---|---|---|
| Luftspaltfeld, Moment | analytische Formel (ms) | 2D-FDM (Sekunden) | 3D-Elmer (Minuten) |
| Rotorfestigkeit | Ringformel × Kt (ms) | eigener Rechensatz, Polsektor (~1 s) | FreeCAD + CalculiX, Vollrotor (Minuten) |
| Löserprüfung | — | — | CalculiX **und** Z88Aurora auf einem Netz |
| Blechschnitt | Parameterstudie | Topologieoptimierung (~20 s) | — |

Zwei Werte, die im selben Kennwertsatz nebeneinanderstehen und **nicht** gleichwertig sind:

* `B_gap_T` kommt aus der **analytischen** Luftspaltformel — nicht aus dem Feldbild.
* `T_maxwell_Nm` kommt aus dem **gelösten 2D-FDM-Feld** (Maxwell-Spannungstensor).

Ohne diese Unterscheidung behauptete ein Bericht eine Feldrechnung, die es nicht gab.
Die Regel zieht sich durch das ganze Werkzeug: der Berichtsprosa werden die Zahlen
entzogen (`_strip_value_numbers`), und die Werte stehen nur in deterministischen
Tabellen — jeder mit seiner Herkunft.

## Rechnungsdatenbank

Jeder Lauf schreibt in **eine** SQLite-Datei (`~/cae_projekte/_db/rechnungen.db`):
Eingabeparameter, Kennwerte **mit dem Verfahren, das jeden erzeugt hat**, Bilder, Tore.
Sie **ersetzt `results.json` nicht** — sie ist der fragbare Index darüber und lässt sich
jederzeit aus dem Dateibestand neu aufbauen.

Am echten Bestand gemessen: 35 Läufe, davon 14 vollständig und **21 abgebrochen**. Die
gesamte Zahlenhistorie passt in **208 kB** gegen 20 GB Projektdaten — denn eine
`results.json` ist 1,7 MB, davon 884 kB Bilder als Base64, während der eigentliche
Kennwertsatz 0,9 kB misst.

```bash
cd cae_orchestrator
python3 cae_cli.py db import                       # ~/cae_projekte einlesen
python3 cae_cli.py db liste
python3 cae_cli.py db guete --lauf last            # was gerechnet wurde, und wie scharf
python3 cae_cli.py db vergleich                    # eine Zeile je Lauf, Herkunft je Spalte
```

Abgebrochene Läufe bleiben sichtbar, statt stillschweigend übersprungen zu werden —
sonst sähe die Datenbank vollständiger aus als der Bestand.

## Was die Toolchain aus ihren eigenen Läufen weiß

```bash
python3 cae_cli.py lernen zeige
```

Zwei Quellen, streng getrennt:

* **Gemessen** — bei jedem Aufruf neu aus der Datenbank hergeleitet. Niemand schreibt
  es, niemand kann es färben. Es fand sofort einen echten Mangel: von 11 Läufen mit
  `struct_mesh_mm = 2` hat genau **einer** einen Struktur-FEM-Wert geliefert, die
  übrigen liefen unbemerkt in die Zeitüberschreitung.
* **Erfahrungen** — abgelegte Notizen, **nur mit Beleg** angenommen (Lauf-Kennung,
  gemessene Zahl, Befehlsausgabe). Ohne Beleg werden sie abgewiesen. Ein Speicher, der
  ungeprüfte Eindrücke annimmt, füllt sich mit Folklore, und die liest das nächste
  Modell als Tatsache.

Es wird **kein Modell trainiert**. „Gelernt" heißt: aus dem eigenen Bestand hergeleitet
und beim nächsten Mal da.

## Was von einem Agentenlauf bleibt

Ein Agent, der rechnet und nichts hinterlässt, ist eine Vorführung, kein Werkzeug.
Drei Dinge verschwanden bisher.

**Die Ergebnisse der örtlichen Verben standen nirgends.** Von sechzehn örtlichen
Verben schrieb genau eines auf die Platte. `paarvergleich`, `screen`,
`rotor-check`, `sicherheit`, `welle` — also gerade die Verben, mit denen eine
Auslegung *entschieden* wird — gaben ihr Ergebnis auf `stdout` aus: es stand in
der rechten Spalte, wanderte nach oben aus dem Bild und war beim nächsten Start
weg. Die Begründung eines Entwurfs überlebte den Entwurf nicht. Sie schreiben ihr
Ergebnis jetzt nach `<projekt>/rechnungen/<zeit>_<verb>.txt` — mit dem Aufruf im
Kopf, sonst ist eine Zahl später nicht zuzuordnen — und hängen eine Zeile an das
Projekttagebuch in `project.json`. **Nicht** in `results.json`: die gehört dem
Pipelinelauf und würde beim nächsten `run analyse` neu geschrieben.

**Die Läufe waren geschrieben, aber unerreichbar.** Nach *jedem* Zug entstanden
ein `protokoll_*.md` und eine `ereignisse_*.jsonl` — gelesen hat das nie jemand:
keine Route, kein Verb, kein Knopf. Für den, der davorsitzt, ist „geschrieben,
aber unerreichbar" dasselbe wie „nicht gespeichert". Es gibt jetzt **🗂 Frühere
Läufe**: alle Läufe beider Köpfe, neueste zuerst, jeder **mit dem gestellten
Auftrag** daran — an einer Uhrzeit erkennt man keinen Lauf wieder, an der Frage
schon. Ein Klick spielt ihn über *dieselben* Zeichenfunktionen ab wie den
laufenden Strom; ein zweiter Satz liefe mit dem ersten auseinander. Die Übersicht
liest dabei keine Mitschrift ganz ein — eine hier gemessene ist **9,4 MB mit
140.872 Ereignissen** — und ein einzelner Lauf kommt auf die Ringgröße gedeckelt
zurück, **vorne** abgeschnitten, weil das Ende das ist, worauf man zurückkommt.

**Was ist dieses Projekt?** Auf „erstelle kurz einen Steckbrief über das Projekt"
beschrieb ein Agent das **Monorepo** — Ports, Teilprojekte, Git-Zweig. Keine
Halluzination: über die Maschine lag ihm nichts vor außer einer 1,7 MB großen
`results.json`. `cae_cli.py steckbrief [--laeufe]` und derselbe Text am Anfang der
erzeugten `AGENTS.projekt.md` tragen jetzt Maschinenart, Pole/Nuten, Bauraum,
Luftspalt, Werkstoffe, Betriebspunkt, gelaufene Stufen und die Kennwerte — **jeden
mit seiner Herkunft** aus demselben Register, aus dem sich die Rechnungsdatenbank
speist. `B_gap_T [analytisch]` und `T_maxwell_Nm [fdm2d]` stehen im selben
`summary` nebeneinander und sähen ohne die Angabe gleichwertig aus. Gerechnet wird
nichts: was auf der Platte fehlt, steht als fehlend da, nicht als 0.

### Die Arbeitsleiste

Ein Agentenlauf sieht von außen minutenlang gleich aus: links läuft Text, rechts
steht nichts Neues. Ob dabei eine Recherche hängt, der Löser rechnet oder schlicht
nichts passiert, war nicht zu unterscheiden — und wer das nicht sieht, bricht zu
früh ab oder wartet auf etwas, das gar nicht läuft. Eine Leiste unter der
Ergebnisspalte, genau so hoch wie die beiden Eingabefelder gegenüber, trägt fünf
Leuchten und den Agenten selbst: **Rechnung** (die vierzehn Zustände des Servers,
mit Fortschritt), **Recherche** (ein Puls, den die Stelle setzt, die *wirklich*
ins Netz greift — nicht aus dem Werkzeugtext geraten), **Löser**
(`ccx`/Elmer/Z88/Gmsh/FreeCAD/OpenFOAM/Blender über `/proc/<pid>/comm`, gegen den
Prozess*namen*, damit ein `grep ccx` in irgendeiner Shell die Leuchte nicht
anschaltet), **GPU** und das geladene **Modell**.

Zwei Dinge fehlen bewusst oder sind gemessen statt angenommen. Es gibt keine
Leuchte „das Modell denkt": Ollama meldet über `/api/ps` nur, was im Speicher
*liegt*, nicht was rechnet — eine so beschriftete Leuchte wäre schlechter als
keine. Und die GPU-Schwelle liegt bei 50 %, nicht bei 12 %, weil diese Karte im
Leerlauf mit nichts als dem Schreibtisch **18–24 %** zeigt; eine Lampe bei 12 %
wäre dauernd an. Ein Abruf kostet 5 ms, und im verdeckten Reiter wird gar nicht
gefragt.

Das **Tempo** ist exakt, wo es exakt sein kann: Hermes führt `output_tokens` je
Sitzung mit, zwei Abfragen ergeben also gemessene Token je Sekunde. PI führt keine
— dort zählt die Seite Zeichen und schreibt „Z/s" daran, weil sich Zeichen zählen
lassen und Token nicht, und eine aus Zeichen hochgerechnete Zahl wie eine Messung
aussähe.

### Wenn ein Zug nie endet

Gemeldet als *„er sagt, dass der Agent arbeitet, tut er aber nicht"* — während die
Leiste daneben korrekt „nichts läuft" zeigte. Gemessene Ursache: Hermes schickte
auf `session/prompt` überhaupt keine Antwort — kein Text, kein Werkzeug, kein
Fehler. Die Sperre blieb stehen, jede weitere Eingabe wurde mit „Der Agent
arbeitet noch" abgewiesen, und der einzige Ausweg war, den ganzen Lauf zu beenden
und die Sitzung zu verlieren. Ein hängender Zug war von einem langen nicht zu
unterscheiden, weil nirgends stand, *wann zuletzt etwas kam*. Jetzt schon: die
Leiste zeigt bernsteinfarben „still seit 8:13", die Pille oben wird korrigiert,
und ab 450 s Stille erscheint **🔓 Sperre lösen**. Das beendet den Agenten
**nicht** — der Prozess läuft weiter, und eine später doch noch eintreffende
Antwort erscheint im Verlauf. Das wird ausdrücklich gesagt, statt den Zug still
neu zu starten: dann liefen zwei nebeneinander, ohne dass es jemand weiß.

### Zwei gemessene Fehler stromaufwärts in Hermes ACP

Beide mit einem eigenen ACP-Klienten nachgestellt, also nicht von diesem Repo
verursacht. Beide dokumentiert statt überspielt — und umgangen, wo eine Umgehung
ehrlich ist.

**Parallele Werkzeugaufrufe verlieren ihr Ergebnis.** Bei *einem* Werkzeug je Zug
schickt `hermes acp` v0.20.5 `tool_call` **und** `tool_call_update`. Bei drei
schickt es drei `tool_call` und **null** Updates: die Ergebnisse erreichen den
Klienten nie, und die Ergebnisspalte blieb einen ganzen Lauf lang leer (gemessen:
1.562 Ereignisse, 3 Werkzeugaufrufe, 0 Ergebnisse). Verloren sind sie aber nicht —
Hermes schreibt jedes Werkzeugergebnis in seine eigene `state.db`, denn das Modell
bekommt sie ja auch. Von dort werden sie am Zugende nachgelesen (nur lesend, mit
Zeitgrenze — die Datei gehört dem laufenden Hermes) und füllen die stummen
Kacheln mit dem *echten* Text. Zugeordnet wird der **Reihe** nach, nicht über die
Kennung: ACP vergibt `tc-…`, die Ablage `call_…`, zwei Nummernkreise. Nur wo auch
die Ablage nichts hergibt, bleibt der ehrliche Platzhalter.

**`skill_view` findet einen Skill nicht, der nachweislich da ist.** Es antwortet
*Skill 'cae-orchestrator' not found*, obwohl `hermes skills list` ihn zeigt
(Quelle `local`, Trust `local`), das Repo in `trusted_project_dirs` steht, der
Prozess-cwd das Repo ist und derselbe Aufruf in einem gewöhnlichen Python-Prozess
mit demselben `HERMES_HOME` und demselben Arbeitsverzeichnis gelingt. Hier wird
nichts geflickt. Statt dessen nennt **jede** Startunterlage den Dateipfad
ausdrücklich — `AGENTS.md`, die erzeugte `AGENTS.projekt.md`, beide Startskripte:
*lies ihn als Datei.* Ein Agent, der den Skill für abwesend hält, rechnet ohne
Verben, Laufzeiten, Exit-Codes und Fallen los.

### Die Bildschirmaufnahme folgt der Ergebnisspalte

Angehalten wurde bisher, während der Server rechnete, mit der Begründung, am Bild
ändere sich dann nichts außer einem Fortschrittsbalken. Gemessen ist das falsch:
in einem Lauf kamen **mitten im Rechenlauf fünf Bilder** in die rechte Spalte —
Querschnitt, Seitenansicht, Luftspalt, Feldbild, Feld unter Last. Angehalten wurde
also genau während der Momente, die aufzuheben sich lohnt. Jetzt setzen jede
Kachel, jedes Bild, jeder Auftrag und Scrollen in der Ergebnisspalte die Uhr
zurück, und beim Erscheinen wird sofort fortgesetzt statt erst beim nächsten
Wächterlauf.

Vor allem aber wird **mitgeschrieben, wann was geschah**. Jedes Ereignis bekommt
seine **Videosekunde** — verstrichene Zeit *minus* Pausen, weil eine Liste nach
der Wanduhr mit jeder Pause weiter danebenläge — und beim Beenden liegen neben der
Aufnahme eine `.marken.tsv` und ein ausführbares `.schnitt.sh`, das benachbarte
Marken zu Stücken verschmilzt, jedes mit Vor- und Nachlauf schneidet und alle
aneinanderhängt. Bewusst **neu kodiert statt `-c copy`**: kopierend schneidet
ffmpeg an Schlüsselbildern und trifft den Moment um Sekunden daneben. Mit dieser
Liste ist die Pause nur noch Platzersparnis und kein Zwang — ein Kästchen schaltet
sie ab, und geschnitten wird hinterher.

## Recherche — und ihre Grenze

Die Agenten dürfen im Internet nachschlagen (`cae_cli.py recherche suche|hole`). Was
zurückkommt, ist als **Fremdtext** markiert: er kann falsch sein, veraltet oder eine
Anweisung an ein Sprachmodell enthalten. Er darf **nie** eine gerechnete Zahl ersetzen.

Wesentliches lässt sich unter dem Projekt ablegen — Text, Bilder und entnommene Werte:

```bash
python3 cae_cli.py recherche merke --projekt last --adresse https://… \
  --wert "stegbreite_mm=1.8 mm :: die zitierte Stelle, aus der der Wert stammt"
```

Werte landen in einer **eigenen** Tabelle `referenzwerte`, nie bei den gerechneten
`kennwerte`. Ein recherchierter Wert kann richtig sein, ist aber nicht nachgerechnet.
Quelle und wörtliches Zitat sind Pflicht; Zahlen werden **nie** automatisch aus
Fließtext geklaubt.

**Gerechnet wird weiterhin ausschließlich lokal.** Es wird nichts hochgeladen und keine
Rechenaufgabe ausgelagert.

## Paarvergleich: worüber überhaupt entschieden wird

Die Vorauswahl unten beantwortet „welche Variante nehme ich?". Eine Stufe früher
steht eine andere Frage: **woran hängt die Maschine überhaupt?** `ema_paarvergleich`
stellt **zwanzig Achsen** — Maschinenart, Magnetanordnung, Bauform, Wicklungsart,
Leiter je Nut, Magnet-, Blech- und Leiterwerkstoff, Kühlung, Wellenverbindung,
Verschraubung, Flussbarrieren, Taschenöffnung, **Schrägung**, **Zwischenkreis-
spannung**, **Stromgrenze**, V-Öffnungswinkel, Wellendurchmesser, Durchmesser,
Länge — Option gegen Option, in Sekunden.

```bash
python3 cae_orchestrator/cae_cli.py paarvergleich --from-project last
```

Zwei Ausgaben, und die zweite ist die wichtigere. Erstens die **Paare**: welche
Kennzahl spricht für welche Seite, und welche bewegt sich zwischen beiden gar nicht.
Zweitens **„was bewegt was"** — die Spannweite jeder Kennzahl über die Optionen
EINER Achse. Daraus fällt die Reihenfolge der Entscheidungen heraus, statt geraten
zu werden (gemessen an einer 260-mm-Maschine):

| Kennzahl | stärkste Achse | Spanne | danach |
|---|---|---:|---|
| Kt | Magnetanordnung | 230 % | Durchmesser 59 %, Nutzahl 0 % |
| Dauermoment (S1) | Kühlung | 550 % | Durchmesser 125 %, Länge 86 % |
| Sicherheit bei n_max | Elektroblech | 282 % | Durchmesser 125 % |
| Masse, Kosten | Durchmesser | 126 % | Länge 85 % |

**Bewusst keine Gesamtnote und kein Sieger.** Eine Gewichtung über Kt, Kosten und
Masse ist eine Zielentscheidung, keine Rechnung — `screen --ziel` macht sie bereits
offen. Der Paarvergleich stellt gegenüber; die Wahl bleibt beim Menschen.

**Ein Fehler, den das Bauen zutage gefördert hat.** Der erste Entwurf rechnete die
Verluste mit `compute_losses(iq, id_)` und behauptete damit zwischen 2 und 12 Leitern
je Nut das **28-Fache** an Verlustleistung. Der Grund: die analytische Momentformel
normiert auf **eine** Windung je Nut, während der Phasenwiderstand quadratisch mit
der Leiterzahl wächst — bei gleichen Amperewindungen kürzt sich das heraus. Jetzt
läuft die Achse über `ema_thermal.design_point_losses`, dessen Kupferanker
Stromdichte × Kupfervolumen ist und damit windungszahlunabhängig; übrig bleibt der
Füllfaktor, und der hat sein Optimum gemessen bei 8 Leitern je Nut.

Ein zweiter Fund fiel dabei ab: `_passt` in der Vorauswahl wies **jede reine
Oberflächen-Bauform** ab, weil aussen aufgesetzte Magnete keine eingelassene Tasche
haben und die radiale Einschlussprüfung damit auf „unendlich" lief. SPM war für
`screen` also nie erreichbar, obwohl das Layouttor es annimmt. Behoben und im Test
festgehalten — zusammen mit dem Gegenstück: Halbach wird weiterhin abgelehnt, aber
aus einem echten Grund (die Kacheln überlappen sich um 5,95 mm), und Tor und
Einpassung sind sich darin einig.

Alles analytisch: kein Feldlauf, keine FEM, keine Thermiksimulation. Die Kühlung
wirkt nur über eine Tabelle von Schubspannungen je Kühlart, nicht über einen
gerechneten Wärmeübergang.

### Die Magnettasche kommt aus ihren Wänden

Die V-Tasche entstand aus drei Zahlen, von denen keine eine Wand ist: `magDepthRel`
(relative radiale Lage 0…1), `magWidth` (Länge in mm) und `magDist` (Stegabstand in
mm). Keine folgt aus den anderen, und ob sie zusammen passen, sagt erst das
Layouttor. In einem gemessenen Agentenlauf vom 07.09.2026 kostete das **vier
Abbrüche an Stufe 0 hintereinander**:

| | Rotorradius | Befund |
|---|---:|---|
| 1 | 25,8 mm | Tasche ragt **2,45 mm** heraus |
| 2 | 25,2 mm | Tasche ragt **0,15 mm** heraus |
| 3 | 25,5 mm | Tasche ragt **1,96 mm** heraus |
| 4 | 25,5 mm | Kollision mit dem Nachbarpol, **0,77 mm** |

Das Tor hatte jedes Mal recht. Falsch war, dass es nichts gab, woraus sich die Tasche
ableiten ließ — also blieb nur Probieren.

Eine Tasche hat aber Wände, und die sind die eigentliche Entwurfsgröße. Gemeint ist
dabei immer die **Tasche** einschließlich Endkappen und Klebespalt, nicht der
Magnetkörper — das ist es ja, was geschnitten wird:

| Wand | mm | wogegen | was sie hält |
|---|---:|---|---|
| Rand | 1,3 | Rotoraußenrand | Polschuh gegen Fliehkraft; kurzschließt den Magneten zugleich |
| d-Achse | 1,5 | Polsymmetrieachse | trägt die beiden V-Schenkel gegeneinander |
| q-Achse | 2,0 | Tasche des Nachbarpols | führt den Reluktanzpfad, begrenzt die Schenkellänge |
| Speiche | 1,5 / 2,0 | Rotorrand / Wellenaußenrand | |

Die Wand zur d-Achse war vorher **nirgends ausgedrückt** — am Ausgangsentwurf fiel
sie aus `magDist = 8` zufällig mit **0,81 mm** ab.

Daraus folgen Sitz und Stegabstand in geschlossener Form, gesucht wird nur noch die
**Länge** — und zwar gegen das echte Layouttor, nicht gegen ein zweites Abstandsmaß
daneben. Am Ausgangsentwurf (Läufer-Ø 188,6, 6 Pole, 120°, 6 mm dick):

| | Magnetlänge | Stegabstand | Position | Wand zur d-Achse |
|---|---:|---:|---:|---:|
| bisher (geraten) | 24,72 mm | 8,00 mm | 0,681 | 0,81 mm |
| aus den Wänden | **42,24 mm** | 9,37 mm | 0,446 | **1,50 mm** |

**Eine Zahl war dabei falsch, und sie sah richtig aus.** Der Sitz `r_pos` ist das
*innere Ende* des Magneten, nicht die Taschenmitte — vom inneren Ende bis zum äußeren
Kappenmittelpunkt sind es `L + Spalt` und nicht `L/2 + Spalt`. Mit dem falschen
Abstand gerechnet stand die Tasche einer 84-mm-Auslegung **36,2 mm außerhalb** des
Rotors. Aufgefallen ist das erst beim Gegenrechnen: eine erste Messung hatte den
Fehler nicht gezeigt, weil der alte Positionsmodus die Länge zusätzlich klemmt und
damit genau die zu lange Tasche wieder wegschnitt.

**Wo es gilt: nur bei neuen Auslegungen** (`--frisch`). Bestehende Projekte tragen
ihren Modus im gespeicherten Payload und ändern sich um keine Ziffer — über alle
Bauformen mit 2430 Fällen bitgleich nachgerechnet.

**Ehrlich scheitern gehört dazu.** Zehn Pole auf einem 51-mm-Läufer mit 3 mm dicken
Magneten lassen zwischen den Wänden 1,38 mm Schenkel übrig. Ein Magnet, der kürzer
ist als er dick ist, wird nicht gebaut; statt der Zahl kommt eine Absage mit den vier
Hebeln (weniger Pole, größerer Rotor, dünnerer Magnet, flacherer Winkel). Eine 1,38
als „ok" zurückzugeben wäre schlimmer, weil danach eine ganze Kette darauf rechnet.

**Nebenbefund bei der Speiche:** dort standen beide Wände gemessen bei **1,20 mm**,
obwohl der Code 1,3 meinte — der Klebespalt geht zweimal ein (die Endkappe sitzt um
einen Spalt außerhalb des Magnetendes **und** trägt selbst den Radius
`Dicke/2 + Spalt`). Jetzt 1,5 mm außen und 2,0 mm zur Welle, und zwar unbedingt: hier
wird kein Freiheitsgrad genommen, sondern eine Wand berichtigt, die das Werkzeug
ohnehin einhalten wollte.

### Ein Buchstabe, fünfundzwanzig Minuten

Im selben Lauf setzte der Agent `--set windingType=runddraht` — die richtige deutsche
Schreibweise — und bekam:

```
FEHLER: windingType: 'runddraht' unbekannt. Zulaessig: hairpin, rundraht
```

Der zulässige Wert heißt `rundraht` mit **einem** „d". Das Werkzeug schreibt beide
Schreibweisen selbst: `ARTEN = ("hairpin", "rundraht")` steht neben
`ART_LABEL["rundraht"] = "Runddraht (…)"`. Danach konnte der Agent den Unterschied
nicht mehr sehen: rund dreißig Aufrufe, die dieselbe Sache immer wieder nachrechnen
(`printf 'runddraht' 'rundraht'`, `cand.count('d')`, `[c for c in g]`, viermal
`curl /param_schema` mit selbstgebauten Suchfunktionen), zwischendurch eine förmliche
Zurücknahme („mein Tippfehler, kein Tool-Fehler") — und zwei Zeilen später derselbe
Fehler noch einmal. Netto: **null Erkenntnis, ~25 Minuten, ~60 Aufrufe.**

Zwei Zeilen Werkzeug, nicht zwei Zeilen Prompt: bekannte deutsche Schreibweisen
werden umgeschrieben statt abgewiesen (und die Umschreibung steht in der Ausgabe),
und ein unbekannter **Wert** bekommt jetzt denselben Tippfehler-Vorschlag, den ein
unbekannter **Name** längst bekam — `Meinten Sie 'hairpin'?`. Umbenannt wurde der
Wert bewusst nicht: er steht im erzeugten FreeCAD-Skript, in vier Testdateien und in
jeder gespeicherten Projektdatei.

### Rastmoment — die Größe hinter „sehr präzise"

Ein Auftrag lautete: Roboterarm-Antrieb, „sehr präzise auch von der
Drehgenauigkeit". Genau diese Größe kannte das Werkzeug nicht. Es gab eine Zeile:

```python
T_cogging_est = Br_NdFeB * R_gap * L_ax * 0.05 / lcm * 1000   # vorher
```

Die Remanenz des **Werkstoffs** statt des Luftspaltfelds, ein Beiwert 0,05 ohne
Herkunft — und vor allem: **die Nutöffnung kommt darin nicht vor.** Sie ist der
stärkste Hebel überhaupt. Zwei Auslegungen mit gleicher Pol- und Nutzahl bekamen
dieselbe Zahl, egal wie weit die Nut zum Luftspalt hin aufging.

**Gemessen wird es nicht — und das steht dabei.** Der naheliegende Weg wäre, den
Läufer im FDM über eine Rastperiode zu drehen. Das geht hier nicht, nachgemessen an
einer 24N/10P-Maschine (Rastperiode 3,0°); nach einer vollen Periode *muss*
derselbe Wert stehen:

| Auflösung | T(0°) | T(3°) | Differenz |
|---|---:|---:|---:|
| N=500 | 8,70 Nm | 0,30 Nm | **−8,40** |
| N=700 | 0,90 Nm | 4,10 Nm | **+3,20** |
| N=900 | 5,50 Nm | 3,70 Nm | **−1,80** |

Es konvergiert nicht. Ursache ist die Treppung: der Läufer liegt auf einem festen
kartesischen Raster, beim Drehen springen Bildpunkte zwischen Eisen, Magnet und
Luft, und das erzeugt ein Scheinmoment, das um ein Vielfaches größer ist als das
gesuchte. Ein Rastmoment braucht ein körperangepasstes Netz.

`ema_rastmoment` rechnet es deshalb analytisch nach Zhu/Howe — und trennt sauber,
was **exakt** ist von dem, was **geschätzt** bleibt:

- **Exakt**, reine Zählerei: `n_c = kgV(Nutzahl, Polzahl)` (Rastperioden je
  Umdrehung), der Rastfaktor `2p·Q/n_c` nach Gieras, und der Schrägungsfaktor. Eine
  Schrägung um genau **eine Nutteilung** löscht die Grundwelle **exakt** aus — das
  ist ein Integral über eine volle Periode, keine Näherung.
- **Geschätzt**, Faktor ~2: die Amplitude selbst. Für den *Vergleich* zweier
  Auslegungen tragfähig (beide Seiten tragen denselben Fehler), als absolute Zusage
  nicht. So steht es in jeder Ausgabe.

Was die neue Rechnung kann und die alte Zeile nicht (an einem 75-mm-Antrieb, 6 Nm):

| Änderung | Rastmoment |
|---|---:|
| Ausgang, offene Nut 4,03 mm | 0,136 Nm (2,3 %) |
| Nutschlitz gedacht auf 1,0 mm | 0,045 Nm |
| Nutschlitz gedacht auf 0,5 mm | 0,015 Nm |
| Schrägung um eine halbe Nutteilung | 0,017 Nm |
| Schrägung um eine ganze Nutteilung | **0,000 Nm** |
| 27 Nuten statt 24 (kgV 270 statt 120) | 0,002 Nm |
| 30 Nuten zu 10 Polen (kgV 30) | unbrauchbar |

**Der wichtigste Befund nebenbei:** dieses Werkzeug zeichnet **offene Nuten**. Es
gibt keinen Nutverschluss, keinen Schlitzsteg — `nut_breite` am Bohrungsrand *ist*
die Öffnung, gemessen 4,03 mm über 0,70 mm Luftspalt. Das ist die ungünstigste
Anordnung für das Rastmoment, und die Bewertung sagt es bei jeder Auslegung dazu.

Im Paarvergleich läuft das Rastmoment als **stehende Spalte** mit, zählt aber
**nicht** in der Bilanz: wie wichtig Drehgenauigkeit ist, entscheidet der Einsatz
und nicht das Werkzeug — an einer Roboterachse ist es die wichtigste Zahl der
Tabelle, an einer Pumpe belanglos. Es wegzulassen wäre trotzdem falsch gewesen:
unter der Schrägungsachse stünde sonst „bewegt NICHT: alles", obwohl sie genau das
bewegt, wofür sie da ist.

### Umrichter: Spannung und Strom sind einstellbar

`--set inverterVdc=24 --set inverterImax=200 --set umrichterBezug=wicklung`

Vorher waren 800 V / 800 A Modulglobale, die niemand ändern konnte. Es ist mehr als
zwei Zahlen durchzureichen: das elektrische Modell rechnet mit **einer Windung je
Nut** (`conductorsPerSlot` geht in K_t, ψ, L_d/L_q und das Kennfeld gar nicht ein),
also gehörten die 800 V zu einer gedachten Einwindungswicklung. Bei fester Geometrie
und festem Moment liegen die **Amperewindungen** fest, und die Windungszahl tauscht
Strom gegen Spannung (K_t ∝ N, i ∝ 1/N, u ∝ N): 24 V mit 200 A und 800 V mit 6 A
sind **dieselbe Maschine** mit zwei Wicklungen.

`umrichterBezug` sagt, was gemeint ist — es wird nicht aus dem Zahlenwert erraten.
Der erste Entwurf tat genau das, und es brach sichtbar auf: in der Stromachse
lieferten 800 A weniger Moment als 400 A, weil ausgerechnet der Vorgabewert auf den
anderen Bezug zurückfiel. `sicherheit` prüft außerdem, ob die Wicklung zum Umrichter
passt, und nennt die Windungszahl, die passen würde — gewählt wird sie nicht: welche
Wicklung gebaut wird, entscheidet nicht das Rechenwerkzeug.

## Vorauswahl: erst die Bauform durchspielen, dann eine rechnen

Ein voller Lauf dauert 30 min bis 4 h. In der Praxis begann deshalb jede Rechnung beim
letzten Stand und änderte daran einen Wert. Polzahl, Nutzahl und Magnetanordnung des
*ersten* Entwurfs blieben damit stehen — und gerade sie prägen die Maschine.

`ema_screen` sieht sie sich zuerst an, analytisch: **384 Konfigurationen in 20 s**,
rangiert, und jede Ablehnung im Wortlaut.

```bash
python3 cae_cli.py screen --from-project last \
        --auftrag "günstiger Stadtantrieb, magnetarm"
```

Das Ziel wird aus dem Auslegungsauftrag gelesen — **mit den Wörtern, die es getragen
haben** (`günstig` ← *günstig*, *magnetarm*), damit die Erkennung keine Blackbox ist. Ein
kostenorientierter und ein leistungsorientierter Auftrag gewichten dieselben Varianten
verschieden; die Gewichte stehen offen im Code, damit man ihnen widersprechen kann.

Sie **sortiert aus und rangiert — sie entscheidet nichts.** Kein Feldlauf, keine FEM,
keine Thermik: die Kennwerte tragen folgerichtig die Herkunft `analytisch`, und was oben
steht, muss danach richtig gerechnet werden.

**Beim Bauen kamen drei Fehler heraus, die nicht in der Vorauswahl lagen.** Sie ließ
zunächst nur 69 von 384 Varianten durch — damit wäre sie ein Filter gewesen, keine
Vorauswahl:

| Befund | Wirkung |
|---|---|
| `_obb_rect_distance` nahm unter den trennenden Achsen die **loseste** Schranke (`min`) statt der straffsten | Für zwei lange, schräg gekreuzte Taschen meldete das Layouttor **0,51 mm Steg, wo 17,11 mm frei sind** — Faktor 33. Das Tor hat damit über die gesamte Laufzeit dieses Werkzeugs einwandfreie Entwürfe verworfen, nicht nur in der Vorauswahl. `max` ist weiterhin eine untere Schranke, meldet also nie einen zu dicken Steg: das Tor bleibt auf der sicheren Seite |
| `_build_spoke` setzte den Magneten 1,0 mm über die Bohrung, ohne die Taschenkappe von `magThick/2 + Spalt` | Ab 1,8 mm Dicke schnitt die Tasche **in die Wellenbohrung**. Der Speichentyp war bei keiner Einstellung baubar |
| `_build_u` reservierte den Steg zwischen Magnet**körpern** statt zwischen **Taschen** | 1,70–1,73 mm gegen 2,00 mm Mindestdicke, unverändert über jeden Parameter. Die U-Form war ebenfalls nie baubar |

Nach den Fixes: **312 von 384 brauchbar, alle acht Magnetanordnungen bei allen vier
Polzahlen erreichbar.** Die verbleibenden 72 scheitern am Kriterium für eine symmetrische
Drehstromwicklung — das ist Arithmetik, nicht Geometrie.

Die Einpassung hat **zwei** Stellschrauben, weil eine nicht reichen kann: den
Magnetkörper zu verkleinern macht *jeden* Steg dicker, die Anordnung enger zu ziehen macht
die Stege *zwischen* den Polen dicker und die *innerhalb* eines Pols dünner. Mehrlagige
Anordnungen verlangen das Gegenteil — `pmasynrm` ist bei 16 mm Lagenabstand mit 2,71 mm
Steg zulässig und scheitert bei 8 mm an 0,01 mm. Jede Verkleinerung steht im Protokoll:
eine Vorauswahl, die stillschweigend Magnete schrumpft und danach nach Momentkonstante
rangiert, würde sich selbst betrügen.

Bei den Fahrzyklen steht neben WLTP, Volllast und Autobahn jetzt **Stadt/Land**: 1300 s,
18,76 km, Spitze 94,9 km/h, 12 % Standanteil (gemessen).

## Bilddatensatz: was das Auge sieht und keine Kennzahl misst

Manches am Blechschnitt beurteilt ein Mensch besser als jede Formel — ob die Stege
gleichmaessig sind, ob der Magnet zur Polteilung passt. `ema_bilddaten` bereitet genau
diese Frage vor: zufaellige Rotorquerschnitte zeichnen, von Hand bewerten lassen, und
aus den Urteilen eine **nachrechenbare Schranke** ziehen.

```bash
python3 cae_orchestrator/cae_cli.py bilddaten erzeugen --anzahl 500
python3 cae_orchestrator/cae_cli.py bilddaten seite     # bewerten.html im Browser
python3 cae_orchestrator/cae_cli.py bilddaten einlesen --datei ~/Downloads/urteile.json
python3 cae_orchestrator/cae_cli.py bilddaten regel --merken
```

Der Anlass war ein Plan ueber **10.000 Zufallsmaschinen** fuer ein Bildmodell. Die Idee
stimmt, die Zahl nicht — drei Messungen haben sie auf ~500 gebracht:

| Gemessen | Folge |
|---|---|
| Von zufaellig gezogenen Geometrien bestehen **27 %** das Layouttor (107 von 400) | Die uebrigen drei Viertel sind Taschen, die sich schneiden oder aus dem Rotor ragen. Das entscheidet `rotor_layout_check` in Millisekunden und exakt — niemand muss sie ansehen |
| Von den Ueberlebenden nennt die vorhandene Heuristik bereits **79,3 %** „schlecht" | Ein menschliches Urteil traegt dort nichts bei, wo eine Regel schon entscheidet |
| Bleiben ~**5 %** der Ziehungen, in denen das Auge wirklich gebraucht wird | Bei 10.000 waeren das 500 lohnende Bilder und 9.500 verlorene. Also werden gleich die 500 gezogen |

Gezeichnet wird mit **demselben** Code wie das Bild im Projektbericht
(`ema_pipeline.render_cross_section`, aus `_save_cad_images` herausgeloest und im Test
bitgleich gegengeprueft) — ein eigener Zeichner haette Maschinen gezeigt, die so nie
gerechnet wurden. Nur kleiner und ohne Beschriftung: 384 px, 0,138 s und 33 kB je Bild
gegen 0,245 s und 172 kB in Berichtsgroesse.

Zwei Dinge, die bewusst **nicht** passieren:

* **Keine Heuristik-Vorbelegung.** Die Bewertungsseite zeigt das Bild und sonst nichts —
  keine Masse, keine Kennzahlen, keinen Vorschlag. Wer eine Vermutung vorschlaegt,
  bekommt sie bestaetigt zurueck, und das unabhaengige Urteil ist weg.
* **Kein neuronales Netz.** Die Geometrie liegt exakt vor; sie aus Pixeln
  zurueckzuschaetzen waere ein Rueckschritt. Am Ende steht eine Schranke ueber
  gemessenen Groessen (Stegbreite, Polbedeckung, Nabenanteil …), die man am Blech
  nachmessen und bestreiten kann.

`regel` prueft die gefundene Schranke auf einem **zurueckgehaltenen Drittel** (feste
Zuteilung ueber die Variantenkennung, in jedem Lauf dieselbe) und legt sie nur dann als
belegte Erfahrung ab. Haelt sie dort nicht, sagt sie das und schreibt nichts — eine
Schranke, die nur den Lernteil trifft, ist eine Eigenschaft des Datensatzes und keine
des Rotors. Der Test legt beide Faelle fest: eine kuenstlich in die Urteile gelegte
Schranke muss wiedergefunden werden (Pruefteil 1,00), und bei Muenzwurf-Urteilen darf
keine Regel durchkommen (Lernteil 0,63, Pruefteil 0,48 — abgewiesen).

## Entwurf oder Detail: wie viel Rechenleistung wofür

Im Berechnungs-Reiter stehen jetzt zwei Voreinstellungen, **📐 Entwurf** und
**🔬 Detail**. Sie setzen Frame-Zahl, Auflösung, Drehzahlschritt und die
Struktur-Einstellungen; die Anzeige darüber sagt, ob der aktuelle Stand noch einer
Voreinstellung entspricht oder schon eine eigene ist.

Der Grund, warum das überhaupt eine Voreinstellung sein darf, ist eine Messung
(Projekt *Alpenpass*, vasym, p=3, 36 Nuten, Sättigung an):

| N | Sekunden | B_gap [T] | Kt | Br-Grundwelle, Abw. zu N=600 |
|---:|---:|---:|---:|---:|
| 120 | 0,54 | 0,477 | 0,031 | −92,0 % |
| 240 | 4,79 | 0,477 | 0,031 | −52,5 % |
| **300** | 9,18 | 0,477 | 0,031 | **−2,8 %** |
| 600 | 68,75 | 0,477 | 0,031 | 0 % |

**B_gap und Kt bewegen sich über den ganzen Bereich nicht** — sie kommen aus der
analytischen Verankerung, nicht aus dem Gitter, während die Rechenzeit um den Faktor
127 steigt. An der Auflösung hängt allein die **Form** der Luftspaltwelle, und die
knickt bei N=300 ein. Ein Entwurfslauf verliert also keinen Kennwert, nur
Bildschärfe — und darum liegt trotzdem keine Voreinstellung unter 300: die
Berichtsbilder rendern mit der doppelten Frame-Auflösung, der Entwurf mit 180 px also
bei 360.

**Der Agent konnte davon nichts wählen.** Die Regler stehen in *keinem* Schema —
sie beschreiben nicht die Maschine, sondern wie genau gerechnet wird — also wurde
`--set fdm_resolution=300` als unbekannt abgewiesen, und jeder Versuch eines
Agenten lief in Detailgenauigkeit: Stunden, wo Minuten genügen. Die Tabelle steht
jetzt als `ema_text2ema.GUETE` an einer Stelle, `cae_cli.py run --guete
entwurf|detail` wendet sie an, und ein Test nagelt die Kopie in der Oberfläche
gegen die Python-Tabelle fest — so wie der Topologietest es für den JS-Spiegel tut.

Und die **Zahl der Entwurfsschleifen gibt der Mensch vor**, nicht der Agent: ein
Feld in der Startmaske, das beide Köpfe als stehenden Auftrag erreicht — *so viele
schnelle Runden, nach jeder `sicherheit`, und erst wenn ein Stand hält, geht EIN
Lauf auf Detail.* Ohne diese Zahl fielen Agenten in eines von zwei Extremen, beide
hier beobachtet: ein Detaillauf von Stunden, an dem sich nichts entscheiden lässt,
oder Herumprobieren ohne Ende.

**Der Laufzeitschätzer war dabei um mehr als eine Größenordnung zu niedrig.** Er
rechnete mit einer Faktorisierung je Rotorwinkel und einer billigen Rück-Substitution
je Drehzahl. Das war richtig, solange die Frames linear liefen; seit sie mit
Sättigung rechnen, trägt es nicht mehr — der Sättigungsdurchgang erzeugt je Frame ein
neues feldabhängiges µ, das per Konstruktion nie wieder vorkommt und deshalb bewusst
nicht zwischengespeichert wird. Gemessen kostet der zweite Frame am **gleichen**
Winkel 8,97 s gegen 8,99 s beim ersten: der Zwischenspeicher spart 0,2 %, nicht 97 %.
Außerdem zählte der Schätzer nur die Rotation, nicht die beiden Zusatzdarstellungen.
Er rechnet jetzt mit direkt gemessenen Sekunden je Frame (0,74 / 2,86 / 4,64 / 8,61 /
18,72 / 59,64 s bei N = 120…600) und nennt die Zahl, die dabei herauskommt: **9 Minuten
für den Entwurf, 2,7 Stunden für Detail.**

## Vollwelle oder Hohlwelle — gemessen, nicht angenommen

Eine Wellenbohrung (`shaftBoreD`, 0 = Vollwelle) spart Masse und Trägheit und
nimmt Kühlmittel oder eine Steckverzahnung auf. Falsch ist sie erst, wenn **durch
die Welle Fluss läuft**. Das ist messbar, also wird es gemessen: `cae_cli.py
welle` rechnet ein Feld, nimmt das radiale |B|-Profil im Rotor (je Ring
Mittelwert und p95 über den vollen Umfang) und sucht von innen nach außen den
ersten Ring über 0,05 T. Alles darunter ist der **flussfreie Kern** und darf
heraus; der Befund reicht die Änderung fertig hin (`--set shaftBoreD=58.0`) oder
sagt, dass die Vollwelle nötig ist.

Entschieden wird am **Kern**, nicht am Mittelwert über die ganze Welle, und der
Unterschied ist keiner auf dem Papier: bei einer 120-mm-Welle führt der äußere
Ring gemessen Fluss, während der Kern bis r = 54 mm frei bleibt. Über den
Mittelwert entschieden stünden „Vollwelle nötig" und „Bohrung bis 104 mm
unbedenklich" im selben Befund — beides zugleich kann nicht stimmen. Gedeckelt
wird bei `shaftD-2`: genau dort setzt das Schema die Bohrung sonst
stillschweigend auf 0 zurück.

Der Befund ist **magnetisch** und sagt das auch: ob die Welle Moment und
Fliehkraft trägt, sagt `struktur`/`sicherheit`. Eine magnetisch unbedenkliche
Bohrung kann mechanisch unzulässig sein.

## Vom Designer direkt an den Agenten

Im Canvas-Designer grob vorgezeichnete Geometrie geht als **Startpunkt** an PI
oder Hermes — ohne Pipelinelauf, zwei Knöpfe im Designer-Reiter. Der Payload wird
aus den Schemavorgaben aufgefüllt (sonst liefe der Agent in einen halben Payload
und bekäme still Vorgabewerte an Stellen, an denen er eine Entscheidung vermutet)
und als `meta.json` abgelegt: genau dort, wo `--from-project` und der Steckbrief
ohnehin nachsehen. Kein neues Werkzeug nötig.

Der Punkt, an dem es hängt: ein gebundenes Projekt ist sonst **ausdrücklich keine
Vorlage** — das ist der Fehler, gegen den `--frisch` gebaut wurde. Eine bewusste
Übergabe ist das Gegenteil, wird als solche markiert und **dreht** den stehenden
Auftrag um: *fang hier an, ändere was nötig ist, und sag, was du geändert hast
und warum.* Auch die Beschreibung, die beim Anlegen eines Projekts eingegeben
wird, erreicht den Agenten jetzt — dieselbe Aufgabe muss nicht zweimal getippt
werden; eine Designer-Übergabe hängt daran an, statt sie zu ersetzen.

## Festigkeit ohne FreeCAD, zweiter Löser, Topologieoptimierung

Neben dem gewachsenen Weg (FreeCAD baut das Netz, CalculiX löst) gibt es einen
**eigenen Rechensatz**: Gmsh vernetzt aus derselben Magnetgeometrie, aus der auch das
2D-Feld kommt, und der CalculiX-Satz wird selbst geschrieben. Zwei Gründe:

1. Eine **Topologieoptimierung** braucht je Element einen eigenen E-Modul. FreeCADs
   `.inp`-Schreiber kann das nicht.
2. Ein **Polsektor** statt des ganzen Rotors — und kein FreeCAD-Start in der Schleife.

Gemessen an derselben Maschine (Delta-IPM, 3 Polpaare):

| | Elemente | Zeit |
|---|---:|---:|
| FreeCAD + CalculiX, Vollrotor | 797.275 | Minuten, davor ~40 s FreeCAD-Start |
| eigener Satz, Polsektor | 13.669 | 0,4 s vernetzt, 0,35 s gelöst |
| eigener Satz, Vollrotor | 37.066 | 1,2 s vernetzt, 1,5 s (ccx) / 2,1 s (Z88) |

**Z88Aurora V5** (`/opt/z88aurora`) rechnet als zweiter, unabhängiger Löser dasselbe
Netz. Auf gleicher Last und gleichem Netz:

| Größe | CalculiX | Z88 | Abw. |
|---|---:|---:|---:|
| σ_v Mittel | 57,15 MPa | 57,15 MPa | 0,00 % |
| σ_v P99 (Torwert) | 128,89 MPa | 128,90 MPa | 0,01 % |
| Ringspannung Bohrung | 161,57 MPa | 161,62 MPa | 0,03 % |
| größte Verschiebung | 40,59 µm | 40,60 µm | — |

Das prüft **Löser und Rechensatz**, nicht das Netz und nicht das Modell.

```bash
cd cae_orchestrator
python3 cae_cli.py struktur --from-project last --solver beide --voll
python3 cae_cli.py topopt   --from-project last --iterationen 25
```

Im Browser stehen beide unter *Strukturanalyse* („Rechensatz & Löser"), in der
Pipeline über `struct_solver` (`freecad` bleibt die Vorgabe). **Nur der
FreeCAD-Rechensatz speist die Verformungsbilder und das Rampenvideo** — die brauchen
Knotenkoordinaten aus der `.frd`.

Die **Topologieoptimierung** (SKO, wahlweise SIMP/OC) läuft auf dem Polsektor,
~0,8 s je Iteration, Konvergenz nach ~20 Iterationen. Sie liefert ein **Dichtefeld,
kein Bauteil**: ein Blechschnitt hat Fertigungs-, Fluss- und Steifigkeits­bedingungen,
die kein Dichtefeld kennt. Was herauskommt, ist der Radialbereich, in dem das Eisen
mechanisch wenig trägt — ein Hinweis, wo eine Flussbarriere vertretbar *wäre*, nach
einer EM-Rechnung und nicht davor. **Z88Arion** wäre das naheliegende Werkzeug dafür,
gibt es aber nicht für Linux (nur Windows, und dort ohne Stapelbetrieb).

## Bedienung am Handy (`/m`)

Ein schmaler zweiter Bedienweg für unterwegs: **Maße eingeben → Halbpol zeichnen →
vier Betriebspunkte mit dem 2D-FDM-Löser rechnen**. Gerechnet wird immer auf dem
Rechner (der Löser ist Python/NumPy); das Handy ist Eingabe- und Anzeigegerät.

Beim Serverstart steht die Einstiegsadresse samt **QR-Code** im Terminal:

```
http://192.168.178.49:5000/m?t=<Token>
```

Handy ins **gleiche** WLAN (nicht ins Gast-WLAN der Fritz!Box — das ist gegen das
Heimnetz abgeschottet), QR scannen, „Zum Startbildschirm hinzufügen" → App-Symbol.
Die Seite läuft danach auch ohne Verbindung an, hält den Entwurf lokal und rechnet,
sobald der Rechner wieder erreichbar ist.

Gemessen an der Beispielmaschine: **vier Punkte in ~9 s, 1,7 MB** (N=180, 640 px).
Als einzige Routengruppe verlangt `/m…` ein Token; die übrigen Routen bleiben offen
wie bisher. Grenzen des Pfads: nur 2D-Feld — kein CAD, keine Festigkeit, keine
Thermik, kein Fahrzyklus, kein Bericht.

## Der dritte Kopf: ein Chat, der mitkommt (`/studio`)

Die Agentenseite mit den zwei Spalten ist für den Schreibtisch gebaut — links der
Agent, rechts die Ergebnisse, dazwischen ein Ziehgriff, der auf Mausereignisse hört.
Auf einem Handy ist sie unbedienbar. Genau derselbe Befund hatte schon den Handy-Pfad
`/m` hervorgebracht, und die Antwort ist dieselbe: **nicht das Layout teilen, sondern
alles darunter.**

Der Reiter **📱 Studio** zeigt denselben Agentenlauf **einspaltig** — Frage, Denken,
Werkzeugaufruf, Ergebnis, Bild, alles untereinander in der Reihenfolge, in der es
geschieht. Zwei Spalten sind zwei Zeitachsen; man liest unwillkürlich die eine als
Fortsetzung der anderen. Eine Ergebniskachel steht hier an der Stelle, an der sie
entstanden ist.

Dahinter läuft ein **eigener, dritter Agent** neben 🤖 PI und 🪽 Hermes — eigener
Prozess, eigene Sitzung, eigenes Gedächtnis. Er steht ausdrücklich *neben* einem
rechnenden PI, nicht an dessen Stelle, und bekommt deshalb einen anderen stehenden
Auftrag als die beiden: **er schreibt über das, was gerechnet wurde, und rechnet nicht
von sich aus.** Die Auslegungsanweisung der anderen Köpfe (Entwurfsschleifen,
Fahrzykluswahl, 3D-Gegenprobe) wäre hier schädlich — sie schickte ihn in einen
Stundenlauf, während jemand am Handy auf einen Satz wartet.

Zwei Dinge fielen erst durch dieses Nebeneinander auf, und beide sind jetzt behoben
statt beschrieben: `AGENTS.projekt.md` wurde bei **jedem** Agentenstart überschrieben —
der zweite Kopf täuschte dem ersten damit beim nächsten Lesen ein fremdes Projekt vor;
und die Bildschirmaufnahme gibt es **einmal je Server**, nicht je Kopf, was die Seite
jetzt ehrlich sagt, statt einen zweiten Rekorder vorzutäuschen.

**Vom Handy aus** ist es derselbe Chat: „📱 Handy" zeigt Adresse und QR-Code, das
Telefon steigt mitten im Gespräch ein und schreibt weiter. Als einzige Agentenseite
steht sie absichtlich im Heimnetz und trägt deshalb dasselbe Token wie `/m` — ein QR
deckt beide Wege. Vom Rechner selbst ist sie offen (dort ist sie ein Reiter), von außen
nur mit Token; PI und Hermes bleiben unberührt.

### Hochkant, mit fester Auflösung

Ein Reel und ein Short sind **1080×1920**. Nimmt man ein Fenster in Fensterform auf,
entsteht ein 16:9-Video, aus dem der Hochkantausschnitt erst hinterher geschnitten wird —
und dann entscheidet sich *beim Schneiden*, was im Bild ist. Deshalb steht der Verlauf im
Studio-Reiter in einer **Bühne mit genau dieser Pixelgröße** (9:16 als Vorgabe, dazu 4:5,
1:1 und „frei"), die als Ganzes ins Fenster skaliert wird: die Anordnung ist unabhängig
von der Fenstergröße, der gestrichelte Rand ist die Schnittkante, und der Zuschnitt steht
**vor** der Aufnahme fest. Skaliert wird die Bühne, nicht ihre Schriftgrößen — die feste
Bühne hat einen eigenen, etwa doppelt so großen Schriftsatz, weil ein Reel auf einem
Telefon gelesen wird. Am Handy entfällt das Ganze: dort *ist* der Schirm schon hochkant.

Daneben steht, was **wirklich** aufgenommen wird. Die Bühne ist 1080×1920 groß, sitzt
aber verkleinert auf dem Schirm, und aufgenommen werden dessen Bildpunkte — ein 1000 px
hohes Fenster liefert gemessen 527×937, die der Zuschnitt auf 1920 hochrechnet. Das steht
mit Zahl und Warnfarbe da, statt dass hinterher jemand rätselt, warum das Reel weich
aussieht; Abhilfe ist ein höheres Fenster oder ein Bildschirm mit doppelter Punktdichte.

Der Zuschnitt selbst wird nicht geraten: beim Aufnahmestart schreibt die Seite eine Marke
mit Bühnenrechteck, Fenster- und Aufnahmegröße, und daraus entsteht die fertige
`crop=…,scale=1080:1920`-Zeile — **nur** bei einer Reiter- oder Fensteraufnahme. Wurde der
ganze Bildschirm aufgenommen, sitzt das Fenster irgendwo darin; das lässt sich nicht
wissen, also steht dort keine Zeile, sondern der Satz, warum nicht.

### Gesetzt statt roh — und die Feldanalyse behält ihre Spalten

Das Modell antwortet in Markdown. Roh gesetzt stehen im Bild Sternchen, Rauten und
Rohrzeichen; im Studio-Reiter wird stattdessen gesetzt: Überschriften, Fett, Kursiv,
Code, Listen, Zitate — und **Tabellen**. Die Tabelle ist der eigentliche Grund: eine
Feldanalyse *ist* eine Tabelle, und `| B_gap | 0,799 T |` als Rohtext ist keine. Der
Renderer ist ein knapper eigener Block (keine Bibliothek), er sieht nur den Text, den das
Modell geschrieben hat, und `test_studio.py` prüft ihn mit `node` gegen feste Beispiele —
dasselbe Verfahren wie beim JS-Spiegel der Topologie.

Zwei Feinheiten, die den Unterschied zwischen „gesetzt" und „ordentlich" ausmachen: ein
weicher Zeilenumbruch des Modells wird zum **Leerzeichen** statt zu einem Umbruch — sonst
franst die rechte Kante genau dort aus, wo das Modell bei achtzig Zeichen umbrach; und
Kursivschrift gilt nur an Wortgrenzen, sonst zerlegt `em_field_load.png` sich selbst.

Die **Werkzeugausgabe** geht den umgekehrten Weg: sie behält ihre Spalten, und angepasst
wird die *Schrift*. Umbrechen zerstört eine Kennwertetabelle, Scrollen versteckt sie, und
ein Höhendeckel schnitt mitten hinein — der Steckbrief war nach `safety_factor_fem` zu
Ende. Der Schriftgrad folgt jetzt den **ausgerichteten** Zeilen, erkannt an der
Spaltenlücke; Prosa darf umbrechen. Drei Anläufe hat das gebraucht, jeder wegen einer
Messung: ein Hundertstelwert über alle Zeilen fiel auf die 228 Zeichen Prosa der
`welle`-Ausgabe herein; ein bloßes „enthält ein Rohrzeichen" hielt denselben Satz für eine
Tabelle, weil `(|B| p95 …)` darin steht; und ohne ein Zeichen Luft brach eine 94 Zeichen
breite Tabelle um, weil nach dem Abrunden 93 passten. Passt eine Tabelle wirklich nicht —
der Paarvergleich ist gemessen 418 Zeichen breit —, steht das an der Kachel, statt still
umzubrechen.

### Die Fußleiste: zwei Zeilen, und man sieht, wer gerade was macht

Am Handy saß sie richtig, am Schreibtisch nicht. Vier Zeilen übereinander, davon eine
allein für den Ablagepfad — abgeschnitten mit Auslassungspunkten, dauerhaft im Weg für
eine Angabe, die man einmal am Tag braucht. Der Pfad sitzt jetzt am Sicherungsknopf
(anfassen genügt) und erscheint bei einer Sicherung **von Hand** als Zeile im Verlauf,
wo er chronologisch hingehört. Das Häkchen „Denken zeigen" zog an das rechte Ende der
Arbeitszeile; damit fällt die vierte Zeile weg, und die Eingabe bekommt die volle Breite
für ihre Symbole.

An der Stelle der abgeschnittenen Zeile steht jetzt dieselbe **Lampenzeile** wie am
Schreibtisch: der Agent (immer, solange er läuft — „arbeitet · 0:42", „wartet auf dich",
bernstein „still seit 8:13" samt Freigabe), dazu Rechnung mit Fortschritt, Recherche,
Löser, Grafikkarte, geladenes Modell, Tempo und die Werkzeuglampe. Am Schreibtisch
stehen alle Lampen immer, hier nur die tätigen — die Bühne ist 1080 Punkte breit; am
Handy bleiben sie eine wischbare Zeile, umbrechend nahmen sie dort gemessen sechs.

Was es weiterhin **nicht** gibt, ist eine Lampe „Modell denkt": Ollama meldet nur,
welches Modell im Speicher *liegt*, nicht ob es rechnet.

### Bilder in voller Breite — und die fertige Aufnahme

Zwei Dinge fehlten im Verlauf, und das erste war ein Fehler mit einer sehr
konkreten Ursache: **die Bilder waren nur noch Striche.** Der Verlauf ist eine
Spalten-Flexbox, und deren Kinder schrumpfen von sich aus, sobald der Inhalt
länger wird als die Bühne — statt zu scrollen, staucht der Browser. Ein Bild mit
automatischer Höhe hat nichts, was das aufhält; es wird zuerst und am stärksten
zusammengedrückt, übrig bleibt ein weißer Strich. Jetzt schrumpft nichts im
Verlauf, gescrollt wird — dafür ist der Überlauf da. (Die Schreibtischseite war
nie betroffen: ihr Verlauf ist ein gewöhnlicher Block. Das ist zugleich die
Gegenprobe.)

Die Größe selbst folgt jetzt einer Regel: **die Kachel gibt die Breite vor, die
Höhe folgt dem Seitenverhältnis.** Beides ist nötig — nur die Breite zu setzen
ließ ein 700 Punkte breites Diagramm auf der 1080er Bühne klein und verloren
stehen; nur die Höhe automatisch zu lassen verzerrte es, sobald der Höhendeckel
der Bühne greift. Ein Bild, das gar nicht kommt, sagt das jetzt: vorher war es
von einem gestauchten nicht zu unterscheiden, beides ein weißer Strich, und man
sucht den Fehler an der falschen Stelle.

**Die fertige Aufnahme liegt im Verlauf, nicht nur ihr Pfad.** Sie endete
bisher mit zwei Zeilen, die den Ablageort nannten — dieselbe Lage wie bei den
Agentenläufen, bevor es einen Weg zurück gab: geschrieben, aber unerreichbar ist
dasselbe wie nicht vorhanden, und am Handy erst recht, dort gibt es kein
Dateisystem zum Nachsehen. Beide Agentenseiten hängen jetzt eine Kachel mit
einem Abspieler an derselben Stelle in den Verlauf, an der auch jedes andere
Ergebnis steht; der Server liefert die Datei aus dem Videoordner, beschränkt auf
die zwei Endungen, die der Recorder überhaupt schreibt, und beantwortet
Bereichsanfragen — man kann also springen, ohne achtzig Megabyte vorher zu
laden.

### Aufgenommen wird die Bühne, nicht der Reiter

Der Bildschirmrecorder nahm den ganzen Browser-Reiter auf. Heraus kam ein Bild in
Fensterform, in dem die hochkante Bühne irgendwo saß — der Ausschnitt fürs Reel
entstand erst hinterher beim Schneiden, und bis dahin wusste niemand genau, was
im Bild landet. Das ist genau der Fehler, gegen den die feste Bühne überhaupt
gebaut wurde.

Der Browser kann das selbst: **Region Capture** schneidet eine Selbstaufnahme auf
ein Element zu. Zwei Bedingungen hängen daran, und beide sind erfüllt — die
Aufnahme muss der eigene Reiter sein (die Seite fragt deshalb anders an), und der
Zuschnitt muss stehen, **bevor** das erste Bild aufgezeichnet wird; die
gemeinsame Aufnahmelogik wartet dafür jetzt auf die Seite, zwischen dem Bau des
Recorders und seinem Start. Danach ist die Datei die Bühne — kein Nachschneiden
mehr.

Was das **nicht** ändert, ist die Auflösung: geschnitten wird in den Bildpunkten,
die der Reiter wirklich hat. Eine auf 527×937 verkleinerte Bühne liefert 527×937,
und die Pille oben sagt das weiterhin. Wer echte 1080×1920 will, macht das
Fenster hoch genug.

Und die Schnittliste unterscheidet jetzt **drei** Fälle statt zwei: schon
zugeschnitten, hinterher berechenbar, oder Lage unbekannt (Bildschirmaufnahme).
Die ersten beiden ergeben beide keine `ffmpeg`-Zeile — sie zusammenzuwerfen
hieße, unter einem perfekt zugeschnittenen Reel „ohne Zuschnitt" zu schreiben.
Kann ein Browser die Bereichsaufnahme nicht, sagt die Seite es und fällt auf den
gerechneten Zuschnitt zurück. Versucht werden **zwei** Verfahren, in dieser
Reihenfolge: *Element Capture* nimmt nur den Teilbaum auf — was darüber liegt,
eine Schublade, ein Fenster des Betriebssystems, ist nicht im Bild; *Region
Capture* schneidet das Reiterbild auf das Rechteck zu und lässt Verdeckendes
drin. Also erst das schärfere.

### Und die Seite merkt, wenn sie veraltet ist

Ein Agentenlauf dauert Stunden, und die Seite bleibt so lange offen. Wird in der
Zwischenzeit an ihr gearbeitet, bedient man weiter die alte Oberfläche — und
nichts weist darauf hin. Genau so ist es passiert: die Bereichsaufnahme lag um
10:19 auf der Platte, der Mitschnitt um 10:27 nahm trotzdem den ganzen Reiter
auf, weil der Reiter seit 09:44 offen war. Die Suche ging in den Code statt auf
„Strg+R".

Der Server meldet den Stand der Seitendateien jetzt in der Arbeitsanzeige mit
(eine eigene Liste neben den Physikmodulen — ein Knopfumbau darf nicht aussehen
wie eine Modelländerung). Die Seite merkt sich den Stand beim Öffnen und sagt
**einmal** Bescheid, wenn er sich ändert. Neu geladen wird nicht von selbst:
mitten in einem Lauf ist das eine Entscheidung des Menschen, nicht der Seite.

## Der Schnellbewerter sah die Zeichnung nicht

Vor dem Bau einer freien Magnetsuche wurde erst die Grundlage nachgemessen — und
die trug nicht. Der Schnellbewerter, der hinter KI-Entwurf, Magnetfeinschliff,
Parameterstudie und Zielwertoptimierung steht, bekam sechs **gezeichnete**
Anordnungen vorgesetzt, die sich nur in einer Sache unterschieden:

| gezeichnet | Kt | B_gap |
|---|---:|---:|
| 2 Magnete, 24 mm lang, 6 mm dick | 0,0270 | 0,413 T |
| 2 Magnete, **6 mm** lang | 0,0270 | 0,413 T |
| 2 Magnete, **60 mm** lang | 0,0270 | 0,413 T |
| 2 Magnete, **2 mm** dick | 0,0270 | 0,413 T |
| 2 Magnete, **35° geschrägt** | 0,0270 | 0,413 T |
| **4** Magnete, 24 mm | 0,0540 | 0,827 T |

Länge, Dicke und Neigung bewegten **nichts**, allein die Anzahl bewegte alles —
und die genau linear. Die Formel für das Luftspaltfeld las bei einer gezeichneten
Geometrie die *parametrischen* Felder „Magnetbreite" und „Magnetdicke", die mit
der Zeichnung nichts zu tun haben.

Am schwersten wiegt die Folge: der Magnetfeinschliff („🎯 Magnete
fein-optimieren") verschiebt Magnetkoordinaten und bewertet mit genau diesem
Bewerter — seine Zielgröße änderte sich also nie, er optimierte nichts. Dasselbe
traf die Vorsortierung der KI-Entwürfe und deren Label im Trainingsdatensatz. Der
Defekt hat sich versteckt, weil das Werkzeug, das ihn aufgedeckt hätte, selbst
blind war.

Jetzt wird **je Magnet** gerechnet: Permeanz aus seiner Dicke, Beitrag aus seiner
Länge, und die Neigung als radiale Projektion der Magnetisierung. Für lauter
gleiche Magnete ist das exakt die alte Formel — die parametrischen Bauformen
ändern sich um keine Stelle, und eine gezeichnete V-, VAsym- oder U-Anordnung
trifft ihren parametrischen Zwilling jetzt auf sechs Nachkommastellen. Länge,
Dicke und Neigung bewegen die Zahl; vier kurze Magnete sind so gut wie zwei lange
gleicher Gesamtlänge, statt doppelt so gut.

**Und eine Null, die wie eine Messung aussah:** das Maxwell-Moment aus dem
gelösten Feld stand in jedem Projekt auf 0,0 Nm, mit der Herkunft „FDM" daneben.
Ursache ist der Luftspalt im Raster — die Tangentialkomponente wird auf zwei
Kreisen im aufgelösten Luftband gefittet, und das Band ist bei einer 280er
Maschine mit 0,7 mm Spalt selbst bei 800 Punkten nur 0,6 Bildpunkte breit;
gebraucht werden mehr als 2,5. Es stand also nie eine Messung da. Jetzt steht dort
nichts — und daneben, warum.

## Rechenläufe für den Agenten: `studie` und `zielwert`

Parameterstudie und Zielwertoptimierung gab es nur als Knopf im Browser. Für einen
Agenten existiert ein Knopf, den nur die Oberfläche hat, nicht — er bedient die
Kette über das CLI. Beide sind jetzt Verben, und damit gilt: **ein Verb genügt für
alle drei Köpfe**, sie lesen dieselbe Anleitung.

```bash
python3 cae_orchestrator/cae_cli.py studie --from-project last \
        --param magAngle --von 60 --bis 160 --punkte 60
python3 cae_orchestrator/cae_cli.py zielwert --from-project last \
        --ziel Kt --max --grenze T_magnet:le:150
```

`studie` gibt eine Tabelle aus und darüber die Antwort auf die eigentliche Frage:
welcher Kennwert sich über den Bereich am stärksten bewegt und welcher gar nicht.
Hundert Zeilen Zahlen sind für ein Sprachmodell kein Ergebnis.

`zielwert` ist zugleich die saubere Antwort auf „erreiche diesen Wert": dort
schlägt das Modell nur **Parametervektoren** vor, die geklemmt und rangiert
werden — statt von Hand zu suchen und dabei in Versuchung zu geraten, eine Grenze
im Modell zu verschieben. Findet die Suche keinen zulässigen Entwurf, sagt sie das
**samt der Randbedingung, die bindet** und wie weit sie verletzt ist. Der
am-wenigsten-schlechte Entwurf als Sieger wäre die gefährlichere Antwort.

## Das Werkzeug ist der Maßstab, nicht der Gegenstand

Bei einer Zielwertoptimierung stellt sich eine unangenehme Frage: was hindert den
Agenten daran, den Quellcode zu ändern, bis die Zahl stimmt? Die Köpfe sind
Codieragenten mit Schreibrecht in diesem Verzeichnis, und im Browser wird keine Freigabe
erfragt. Die ehrliche Antwort ist: **verhindern lässt es sich nicht.** Der Agent läuft
als derselbe Benutzer, ohne Sandkasten; wem eine Datei gehört, der darf sie schreiben,
und ein `chmod` zurück kostet eine Zeile. Ein Schloss, das man von innen aufschließen
kann, ist kein Schloss, sondern eine Behauptung.

**Verbergen** lässt es sich sehr wohl verhindern, und darauf läuft es hier hinaus. Ein
Fingerabdruck über die zwölf Module, deren Änderung eine Kennzahl bewegt, reist mit
jeder abgelegten Rechnung, jeder Zeile im Projekttagebuch und dem Steckbrief mit — und
stehen dort mehrere Stände, sagt der Steckbrief ausdrücklich, dass diese Zahlen nicht
ohne Weiteres vergleichbar sind. Ändert sich eine dieser Dateien **während** ein Agent
läuft, erscheint es sofort als bernsteinfarbene Lampe 🔧 in der Arbeitszeile und als
Zeile im Protokoll des Laufs, also genau dann, wenn ohnehin jemand hinsieht.

Daneben steht die Regel im Klartext — in `AGENTS.md`, in der `SKILL.md` und im stehenden
Auftrag jedes der drei Köpfe: ein Ziel wird über Geometrie, Werkstoff und Betriebspunkt
erreicht, nie durch eine verschobene Grenze im Quelltext. Hält man das Werkzeug für
falsch, schreibt man einen **Befund** nach `cae_orchestrator/BEFUNDE.md` (was beobachtet,
wo gemessen, welche Fundstelle) statt still zu reparieren — sonst stammen die Zahlen vor
und nach der Reparatur aus zwei verschiedenen Werkzeugen, und man sieht ihnen das nicht
an.

Die **Zielwertsuche selbst** braucht davon nichts: dort schlägt das Modell nur
Parametervektoren vor, sie werden auf ihre Bereiche geklemmt, und jede unzulässige
Lösung rangiert unter jeder zulässigen. Der Quelltext ist für sie unerreichbar.
Gefährdet ist der Weg, den ein Agent von Hand geht.

## Ein Nein ist auch eine gute Antwort

Der Anlass war ein 230-V-Ventilatorantrieb. Er ließ sich nicht rechnen — und statt das zu
sagen, lieferte das Modell Zahlen: 0,0 Nm Moment und daneben eine Verlustleistung von
**2,8·10²⁰ W**. Wer das liest, sucht den Rechenfehler. Der Befund war die ganze Zeit
„andere Maschinenklasse"; es gab nur keinen Ort, an dem er hätte stehen können.

Die Ursache ist eine Kette aus drei Stufen, jede für sich unauffällig, und sie steht mit
allen Messwerten und Fundstellen in `cae_orchestrator/BEFUNDE.md`. Der Kern: allein zum
Magnetisieren braucht diese Maschine 1686 A gegen eine Umrichtergrenze von 800 A, es
bleibt kein momentbildender Strom — und das Verlustglied teilte durch diesen Strom mit
einem Boden von 10⁻⁹. Eine Division durch fast Null ist kein Ergebnis, sondern die
Stelle, an der die Rechnung hätte aufhören müssen.

Jetzt entscheidet der Betriebspunkt zuerst, ob es ihn **gibt**. Unter einem Tausendstel
der Stromgrenze kommt kein Zahlenwert zurück, sondern `erreichbar: nein` mit einer
Begründung, die die beiden Ströme und die Stellschraube nennt; Moment, Schlupf und
Verluste sind dann ausdrücklich **leer und nicht 0,0** — eine Null liest sich wie ein
gerechnetes Ergebnis, und genau so wurde sie gelesen. Der Käfig fällt nicht mehr still
auf seine Fertigungsuntergrenze zurück, und die 2-D-Feldstufe weigert sich, daraus einen
Rotor zu vernetzen, statt eine halbe Stunde an eine Maschine zu hängen, die es nicht
gibt.

### Müssen Antworten gewichtet werden?

Ja — aber nicht mit einer Vertrauenszahl. Die wäre selbst wieder eine erfundene Größe.
Was eine Zahl wägbar macht, sind zwei Angaben, und beide waren schon halb da: ihre
**Herkunft** (welches Verfahren sie geliefert hat — das steht seit jeher an jedem
Kennwert im Steckbrief) und ihr **Geltungsbereich** (liegt der Fall in der Klasse, auf
die diese Kette geeicht ist).

Der Geltungsbereich ist ausdrücklich **kein Tor**: außerhalb heißt nicht falsch, sondern
„dafür ist diese Kette nicht geeicht, und keine der gerechneten Auslegungen liegt dort".
Drei Angaben, jede gemessen statt behauptet: ob überhaupt ein Umrichter gesetzt ist oder
die Traktionsvorgabe 800 V / 800 A gilt (dann ist jede Stromaussage eine Aussage über
diesen Deckel); ob die Maschine mehr Magnetisierung braucht, als diese Klasse hergibt —
**der unmittelbare Netzbetrieb ohne Stromrichter ist nicht modelliert**, und das steht
jetzt wortwörtlich da; und ob die Leistung in dem Band liegt, in dem hier tatsächlich
schon gerechnet wurde (aus der Datenbank ausgelesen: 0,2 bis 419 kW aus 57 Läufen).

Steckbrief, `sicherheit` und `beitrag` tragen das mit. Damit ist „nicht darstellbar, weil
das Modell keinen Netzbetrieb kennt" eine vollständige Antwort — kein Fehlschlag.

## Beiträge für Instagram und X — aus dem, was gerechnet wurde

Die zweite Aufgabe des Studio-Reiters, und als Verb auch dem Agenten zugänglich:

```bash
python3 cae_orchestrator/cae_cli.py beitrag x --from-project last
python3 cae_orchestrator/cae_cli.py beitrag instagram --from-project last --ton begeistert
```

Das Material kommt aus dem **Steckbrief** des Projekts, nicht aus dem Gesprächsverlauf.
Der Unterschied ist der ganze Punkt: der Steckbrief weiß, welche Stufe eine Kennzahl
geliefert hat und was fehlt — ein Beitrag aus dem Chat übernähme jede Zahl, die der
Agent unterwegs einmal geschätzt hat, und **veröffentlicht sie**.

Aus demselben Grund steht die Regel „keine Zahl ohne Deckung im Material" nicht nur im
Prompt: jede Zahl des Entwurfs wird hinterher **nachgemessen** und als Hinweis gemeldet,
wenn sie im Material nicht vorkommt. Runden ist gedeckt (0,7994 → 0,80), Erfinden nicht.
Eine Bitte an ein Sprachmodell ist keine Zusicherung.

Was der Entwurf mitbringt: Text in der Form des Kanals (X 280 Zeichen je Beitrag, Faden
bis drei — **zu lang heißt umbrechen, nicht abschneiden**; im ersten echten Lauf endete
Teil 1 bei 274 von 280 Zeichen mit „Achtung: Sicherheitskriterien…", es fiel also
ausgerechnet die Einschränkung weg, wegen der man den Beitrag lesen sollte), Hashtags,
eine Bildauswahl mit Alternativtexten, eine **Herkunftsfußzeile** (welche Kennzahl aus
welcher Stufe) — und, wenn eine Bildschirmaufnahme mitlief, Schnittvorschläge aus deren
Marken samt fertiger `ffmpeg`-Zeile. Geschnitten wird sie nicht; gezeigt schon.

**Veröffentlicht wird nichts.** Es gibt keinen Netzweg nach draußen, keine Zugangsdaten
und keinen Knopf dafür. Der Entwurf landet unter `<projekt>/beitraege/` und in den
abgelegten Rechnungen des Projekts; kopiert und gepostet wird von Hand.

## Geteilte Toolchain (systemweit / /opt, nicht in diesem Repo)

- FreeCAD-1.1-Quellbuild + CalculiX → `/opt/cae-tools/freecad_1.1_quellcode` (Symlink `~/freecad_1.1_quellcode`). `ccx` 2.23 wird von dort auch **ohne** FreeCAD aufgerufen
- **Z88Aurora®** V5 → `/opt/z88aurora` (2,8 GB, nur die Stapel-Löser werden benutzt) — Freeware des Lehrstuhls für Konstruktionslehre und CAD (LCAD), Universität Bayreuth, von Prof. Dr.-Ing. Frank Rieg; Lizenz und ein Hinweis zur Herleitung der Dateiformate in `THIRD-PARTY-NOTICES.md`. `z88r` findet sein eigenes MKL nicht — `LD_LIBRARY_PATH` auf `/opt/z88aurora/bin/ubuntu64` ist der ganze Trick. **Z88Arion gibt es nicht für Linux**
- Gmsh — das benutzte ist das **Python-Modul im venv** (4.15.2, aus `requirements.txt`); `/usr/bin/gmsh` (4.12.1) liegt daneben und wird nicht gebraucht
- Portables Blender → `/opt/cae-tools/blender_portable` (Symlink `~/blender_portable`)
- OpenFOAM v2406 (`/usr/lib/openfoam`), Elmer, CUDA, pandoc/pdflatex — systemweit
- Ollama-Dienst auf `localhost:11434`

## Laufzeitdaten (NICHT versioniert)

- `cae_orchestrator` schreibt Projekte nach `~/cae_projekte` (`~ = /home/cae`).
- `pikogk` schreibt generierte Geometrie nach `pikogk/PicoGKWebApi/data/` (gitignored).

## Hinweis native Teile

Dieses Repo versioniert **im Wesentlichen Quellcode**. Die gebaute native `pikogk.so`
liegt auf der Platte (gitignored) und wird vom laufenden Dienst genutzt. Ein Clone auf
einem anderen Rechner müsste sie neu bauen (siehe `pikogk/EXPERIENCE_REPORT.md`).

Ausnahme, weil daran Lizenzpflichten hängen: einige **gebaute Fremd-Binärdateien** sind
versioniert und gehen bei jedem Klon mit (`libblosc` aus c-blosc, `libtbb`,
`libboost_iostreams`, das gebündelte `vtk.js`). Sie sind in `THIRD-PARTY-NOTICES.md`
aufgeführt — wer weitere hinzufügt, trägt sie dort nach.

## Hinweis zur Netzsichtbarkeit

Der Server bindet auf `0.0.0.0` und setzt `Access-Control-Allow-Origin: *` — er ist aus
demselben WLAN erreichbar, **ohne Auth und ohne TLS**. Das ist für den lokalen
Machbarkeitsnachweis bewusst so; nur der Handy-Pfad `/m…` verlangt ein Token. Nicht in
ein fremdes Netz stellen.

## Lizenz

Der hier entwickelte Code steht unter der **MIT-Lizenz** (`LICENSE`).

Fremdkomponenten behalten ihre eigenen Lizenzen. `THIRD-PARTY-NOTICES.md` trennt dabei,
was **mitverbreitet** wird (im Repo enthalten — Lizenztext und Copyright-Vermerk müssen
mitreisen) und was lediglich **vorausgesetzt** wird (lokal installiert oder selbst gebaut,
nicht Teil dieses Repos). Dazu zählt insbesondere **PicoGK** von LEAP 71 (Apache-2.0):
das `pikogk`-Subprojekt bindet es ein, enthält aber keinen PicoGK-Quellcode.
