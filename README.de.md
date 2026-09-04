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
stellt acht Achsen — Magnetanordnung, Leiter je Nut, Magnet-, Blech- und
Leiterwerkstoff, Kühlung, Durchmesser, Länge — Option gegen Option, alle acht in
**0,4 s**.

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
