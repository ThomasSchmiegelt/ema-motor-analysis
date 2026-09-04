# Agent-Anbindung (PI + lokales Modell)

Die CAE-Toolchain lässt sich vollständig von einem Agenten bedienen — mit einem
**lokalen** Modell über Ollama, ohne dass irgendetwas das Gerät verlässt.

## Einrichtung (einmalig)

```bash
# 1) PI installieren. Ohne sudo: npm-Präfix ins Benutzerverzeichnis legen.
npm config set prefix ~/.npm-global
npm install -g @earendil-works/pi-coding-agent
export PATH="$HOME/.npm-global/bin:$PATH"      # in ~/.bashrc aufnehmen

# 2) Modelle eintragen — liegt bereits unter ~/.pi/agent/models.json
#    (Ollama als OpenAI-kompatibler Anbieter, qwen-gross + qwen3.5:9b)

# 3) Modelle eintragen — liegt bereits unter ~/.pi/agent/models.json
```

## Benutzen

Ein Skript startet die ganze Kette:

```bash
cd ~/ai-workspace
./start_agent.sh                                  # Server (falls nötig) + PI, interaktiv
./start_agent.sh -p "Wie hoch ist B_gap im neuesten Projekt?"   # eine Frage
./start_agent.sh --kein-browser                   # ohne Browserfenster
./start_agent.sh --nur-server                     # nur den Orchestrator
./start_agent.sh --weiter                         # letzte Sitzung fortsetzen
./start_agent.sh --sitzungen                      # Sitzungen auflisten
./start_agent.sh --sitzung 01a01998               # bestimmte Sitzung (Teil-UUID reicht)
./start_agent.sh 01a01998                         # dasselbe, nackte Kennung genuegt
```

Es prüft Ollama, **nagelt das Modell auf seine ID fest** (`qwen-gross:latest` /
`ca8ec377441f` — ein `ollama pull` unter gleichem Namen tauscht sonst still die
Gewichte), startet den Orchestrator nur, wenn `:5000` nicht antwortet, räumt einen
belegten Port über `fuser` frei und wartet auf die Erreichbarkeit, bevor PI
losläuft. Alle weiteren Argumente gehen unverändert an `pi`.

Von Hand geht es genauso — nur aus `~/ai-workspace` heraus, sonst findet PI weder
`AGENTS.md` noch `.agents/skills/`:

```bash
export PATH="$HOME/.npm-global/bin:$PATH"
pi --provider ollama --model qwen-gross:latest
```

Im Sitzungsbetrieb wechselt `/model` (oder `Strg-L`) das Modell — `qwen3.5:9b` ist
die schnelle Variante für einfache Abfragen.

## Sitzungen fortsetzen

PI legt jede Sitzung als JSONL unter `~/.pi/agent/sessions/<kodiertes cwd>/` ab und
sortiert sie **nach Arbeitsverzeichnis** — deshalb startet `start_agent.sh` PI immer aus
`~/ai-workspace`, sonst zeigte `--continue` auf die Sitzungen eines anderen Ordners.

```bash
./start_agent.sh --sitzungen        # id, Zeitpunkt, erste Frage — neueste zuerst
./start_agent.sh --weiter           # die neueste fortsetzen  (pi --continue)
./start_agent.sh --sitzung 01a01998 # eine bestimmte          (pi --session)
./start_agent.sh 01a01998           # dasselbe, ohne Flagge
./start_agent.sh -- 01a01998        # dasselbe; `--` wird geschluckt, nicht durchgereicht
```

Die nackte Kennung wird **nicht** über ein Muster erkannt, sondern durch Abgleich mit den
wirklich vorhandenen Sitzungen — was keine ist, geht unverändert an `pi`. PIs eigene
Flaggen (`--session`, `--continue`, `-c`, `--resume`, `--fork`, `--no-session`) bleiben
dabei unangetastet: dann entscheidet PI, und das Skript sagt und ändert nichts.

Der Grund für die Bequemlichkeit: PI schreibt beim Beenden selbst
`To resume this session: pi --session <uuid>`. Der Griff danach landet leicht bei
`./start_agent.sh -- <uuid>` — und `--` kennt `pi` nicht, es brach mit
`Unknown option: --` ab, nachdem Server und Modellprüfung schon gelaufen waren.

Wie PI das Arbeitsverzeichnis in den Ordnernamen kodiert, ist nirgends zugesagt; das
Skript rät es deshalb **nicht**, sondern liest die erste Zeile jeder Sitzungsdatei — die
trägt `cwd` im Klartext — und filtert danach.

**Ohne Flag wird nicht fortgesetzt**, sondern nur die letzte Sitzung als Hinweis
angezeigt. Ein frischer Start bleibt der Normalfall: sonst schleppte jede neue Frage den
Verlauf der vorigen mit, und bei 64 k Kontext fällt das erst auf, wenn vorne etwas
herausfällt.

## Was der Agent sieht

| Datei | Rolle |
|---|---|
| `AGENTS.md` (Wurzel) | Projektkontext + harte Grenzen, immer im Kontext |
| `AGENTS.projekt.md` | der **Stand dieses Laufs**: gebundenes Projekt, Steckbrief, Arbeitsweise — wird bei jedem Start neu geschrieben |
| `.agents/skills/cae-orchestrator/SKILL.md` | Bedienanleitung, wird bei Bedarf geladen |
| `.agents/skills/cae-orchestrator/references/routes.md` | alle 135 Routen, nach Bereichen |
| `cae_orchestrator/cae_cli.py` | das eigentliche Werkzeug |

**Der Skill wird als Dateipfad genannt, nicht nur als Name.** `AGENTS.md`, die erzeugte
`AGENTS.projekt.md` und beide Startskripte schreiben `.agents/skills/cae-orchestrator/SKILL.md`
ausdrücklich hin. Grund ist ein gemessener Fehler in Hermes (siehe unten): dort schlägt
`skill_view("cae-orchestrator")` fehl, obwohl `hermes skills list` den Skill zeigt. Ein
Agent, der den Skill für abwesend hält, rechnet ohne Verben, Laufzeiten, Exit-Codes und
Fallen los — eine Datei zu lesen geht immer, auch wenn die Skill-Auflösung klemmt.

**Warum ein CLI und nicht MCP:** PI bindet Werkzeuge bewusst als „CLI mit README"
ein. Das passt hier auch inhaltlich — ein lokales Modell kann 135 Routen nicht als
135 Werkzeugschemata halten, wohl aber `cae_cli.py run em3d --wait` aufrufen und die
Antwort lesen. Der Alltagspfad hat zehn Verben, `raw` deckt den Rest ab.

## Was der Agent rechnet — und was davon bleibt

`cae_cli.py` hat **fünfundzwanzig** Verben: neun über HTTP auf `:5000`
(`status/health/geom/run/wait/results/projects/raw/routes`) und sechzehn, die **lokal**
rechnen — ohne Server, ohne FreeCAD, in Sekunden. Die vier, die im Alltag am meisten
tragen:

| Verb | Wofür |
|---|---|
| `steckbrief` | *Was ist dieses Projekt, und was ist daran schon gerechnet?* |
| `paarvergleich` | dreizehn Gestaltungsachsen, jede Option gegen jede — die Stufe VOR der Geometrie |
| `welle` | Vollwelle oder Hohlwelle, **am Feld gemessen** |
| `feldbild` | Feldlinienbilder ins Projekt, aus EINEM Löserlauf statt einem Pipelinelauf |

### `steckbrief` — der Einstieg in ein fremdes Projekt

Der Anlass war messbar: auf „erstelle kurz einen Steckbrief über das Projekt" beschrieb
der Agent am 04.09. das **Monorepo**, weil ihm über die Maschine nichts vorlag. Jetzt
liest `steckbrief` zusammen, was auf der Platte steht — Identität und Herkunft,
Maschinenart, Pole/Nuten, Bauraum, Luftspalt, Werkstoffe, Betriebspunkt, welche Stufen
gelaufen sind, die Kennwerte, der Sicherheitsbefund, der Bestand an Bildern/CAD/3-D-Netzen,
und mit `--laeufe` auch die früheren Agentenläufe und abgelegten Rechnungen.

**Er rechnet nichts.** Was fehlt, steht als fehlend da — nicht als 0 und nicht als
Näherung. Und **jeder Kennwert trägt seine Herkunft** (`analytisch`, `fdm2d`, `fem3d`,
`lptn`, `zyklus`, `geometrisch`, `abgeleitet`) aus einer Quelle: `B_gap_T [analytisch]`
und `T_maxwell_Nm [fdm2d]` stehen im selben `summary` und sähen sonst gleichwertig aus.

Dieselben Fakten gehen als Stichpunkte in `AGENTS.projekt.md`, stehen also schon vor dem
ersten Prompt im Kontext.

### Was der Agent rechnet, bleibt jetzt liegen

Von den örtlichen Verben schrieb nur `feldbild` etwas auf die Platte. `paarvergleich`,
`screen`, `rotor-check` und `sicherheit` — die Verben, mit denen ein Agent eine Auslegung
tatsächlich *entscheidet* — gaben ihr Ergebnis auf `stdout` aus: es stand in der rechten
Spalte, rollte nach oben aus dem Bild und war beim nächsten Start weg. Die Begründung
hinter einer Auslegung überlebte die Auslegung nicht.

Sobald ein Projekt gebunden ist (`--from-project`/`--projekt`), landet das Ergebnis in
`<projekt>/rechnungen/<zeit>_<verb>.txt` (der auslösende Aufruf steht im Kopf, strukturierte
Daten daneben als `.json`) plus **eine Zeile in `project.json`s `evolution`**. `--ohne-ablage`
schaltet es ab. Bewusst **nicht** in `results.json`: die gehört dem Pipelinelauf und würde
beim nächsten `run analyse` überschrieben.

### Erst schnell entscheiden, dann genau rechnen (`--guete`)

Die Knöpfe für Rechenqualität (FDM-Auflösung, Netzweite, Framezahl) standen in **keinem**
Schema — `--set fdm_resolution=300` wurde abgewiesen, ein Agent konnte sie also gar nicht
wählen und rechnete jeden Versuch in voller Schärfe: Stunden statt Minuten.

```bash
python3 cae_cli.py run analyse --from-project last --guete entwurf --wait   # ~9 min
python3 cae_cli.py run analyse --from-project last --guete detail  --wait   # ~2,7 h
```

Der Entwurf ist ehrlich, weil er gemessen ist: `B_gap` und `Kt` kommen aus der analytischen
Formel und hängen **nicht** an der Auflösung — ein Entwurfslauf verliert keine Kennzahl,
nur Bildschärfe. Keine Stufe geht unter N=300, weil dort die gemessene Luftspaltwelle
anfängt, um die Hälfte danebenzuliegen. Die Tabelle steht einmal in Python
(`ema_text2ema.GUETE`); die JS-Kopie in der Oberfläche ist per Test dagegen festgenagelt.

Wie viele Entwurfsschleifen gefahren werden, gibt der Mensch in der Startmaske vor und es
erreicht den Agenten als stehende Anweisung. Ohne diese Zahl fielen Agenten in eines von
zwei Extremen: ein einziger mehrstündiger Detaillauf, der nichts entscheidet — oder
endloses Herumprobieren.

### `welle` — Vollwelle oder Hohlwelle, gemessen

Eine Bohrung spart Masse und Trägheit und nimmt Kühlmittel auf; falsch ist sie erst, wenn
**durch die Welle Fluss läuft**. Das ist messbar: EIN FDM-Lauf, das radiale |B|-Profil im
Rotor, und von innen nach außen der erste Ring über 0,05 T. Alles darunter ist der
flussfreie Kern und darf heraus.

Entschieden wird **am Kern, nicht am Mittelwert über die ganze Welle**. Der Unterschied ist
keiner auf dem Papier: bei einer 120-mm-Welle führt gemessen der äußere Ring Fluss, während
der Kern bis r = 54 mm frei bleibt — über den Mittelwert entschieden stünden „Vollwelle
nötig" und „Bohrung bis 104 mm unbedenklich" im selben Befund. Der Befund ist **magnetisch**
und sagt das auch; ob die Welle Moment und Fliehkraft trägt, sagt `struktur`/`sicherheit`.

## Modell

`qwen-gross:latest` ist Qwen3.5 27B (Q4_K_M, 17 GB) mit Werkzeugaufruf-Fähigkeit —
dieselben Gewichte wie `qwen3.8:latest`, aber mit `num_ctx 65536` im Modelfile.
Das ist der ganze Unterschied, und er ist hier entscheidend: PI schickt über die
OpenAI-kompatible Schnittstelle **kein** `num_ctx` mit, der Server entscheidet also
allein. Gemessen (`ollama ps` nach einem Aufruf über `/v1/chat/completions`):
`qwen3.8` 32768, `qwen-gross` 65536 — trotz der 262144, die in `models.json` standen.
Die Angabe dort ist deshalb auf 65536 korrigiert; ein größerer Wert ließe PI mehr
Kontext packen, als der Server behält, und der Überhang fiele still weg.
Der große Kontext ist hier nützlich, weil `results.json` auch nach dem Filtern noch
umfangreich ist.

## Zweiter Agentenkopf: Hermes

Neben PI läuft **Hermes Agent** (Nous Research) auf demselben Modell und demselben
Skill. Zweck ist der Vergleich der *Agenten*, nicht zweier Werkzeugbindungen —
deshalb bekommt Hermes **kein MCP**, sondern dieselbe CLI wie PI.

```bash
./start_hermes.sh                    # interaktiv
./start_hermes.sh -z "Wie hoch ist B_gap im neuesten Projekt?"
./start_hermes.sh --nur-pruefen      # nur der Netznachweis, startet nichts
```

**Ein Skill, zwei Köpfe — ohne Kopie.** `hermes skills trust <repo>` lädt die
repo-eigenen Skills aus `./.agents/skills/`, also **genau dem Verzeichnis, das PI
schon benutzt**. Es wird nichts symlinkt und nichts kopiert; beide lesen dieselbe
Datei, und sie können nicht auseinanderlaufen.

Einmalig:

```bash
curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- \
     --skip-browser --skip-computer-use --skip-setup --non-interactive
hermes config set model.provider   ollama
hermes config set model.base_url   http://localhost:11434/v1
hermes config set model.default    qwen-gross:latest
hermes config set model.context_length 65536
hermes skills trust ~/ai-workspace
```

Installiert wird nach `~/.hermes` (2,0 GB) und `~/.local/bin/hermes` — **ohne sudo**.
`--skip-browser` spart Playwright/Chromium (das einzige, was root bräuchte),
`--skip-computer-use` den Fremdtreiber aus einem dritten Repo.

### Warum `start_hermes.sh` den Netzzugang misst statt ihn zu behaupten

Hermes' **mitgelieferte Vorgabe** ist `provider: auto` mit
`base_url: https://openrouter.ai/api/v1`. Dazu kommen zwei offene Fehler im Projekt
(NousResearch/hermes-agent #57255 und #14676): `provider: ollama` fällt bei einer
`base_url` mit `/v1` still auf `custom` durch, und ein blankes `custom` ohne
aufgelöste `base_url` zeigt auf OpenRouter. Auf einer Maschine, deren Prinzip
„nichts über das Heimnetz hinaus" ist, wäre das ein stiller Abfluss.

Die Konfigurationsdatei ist deshalb kein ausreichender Beleg. Vor jedem Start prüft
das Skript drei Dinge:

1. `provider`, `base_url` und `default` in `~/.hermes/config.yaml`;
2. dass in `~/.hermes/.env` **kein** OpenRouter-/OpenAI-/Anthropic-/Nous-Schlüssel steht;
3. **gemessen**: ein echter Aufruf, dabei werden die Verbindungen des
   `hermes`-Prozesses mit `ss -tnp` mitgeschrieben. Alles außer `127.0.0.1:11434`
   bricht ab — und **keine** beobachtete Verbindung bricht ebenfalls ab, denn eine
   leere Messung belegt nichts.

Gemessen am 24.08.2026: 12 Beobachtungen, alle auf `127.0.0.1:11434`, keine
Gegenstelle außerhalb.

### Hermes im Browser (Reiter 🪽 neben 🤖 PI)

Beide Köpfe hängen auch in der Oberfläche auf `:5000` — links der Denk-/Antwortstrom,
rechts Werkzeugausgaben und Bilder, darüber Stoppuhr und Bildschirmaufnahme. Es ist
**eine** Seite (`cae_orchestrator/ema_agent.html`) und **eine** Routenmenge
(`/agent/…`), unterschieden allein durch `?kopf=pi|hermes`; ein zweites HTML wäre die
Kopie, die beim ersten Fehlerbericht auseinanderläuft — dasselbe Argument, aus dem
beide Köpfe eine `SKILL.md` lesen.

Angesprochen wird **`hermes acp`** (Agent Client Protocol, zeilengetrenntes JSON-RPC
2.0 auf stdout, Protokoll auf stderr), nicht `hermes serve`: dessen eigene Oberfläche
auf `:9119` wäre ein Fremdkörper ohne Stoppuhr, ohne gemeinsames Protokoll, ohne die
Bilder aus dem Projektordner und ohne Aufnahme.

Zwei Unterschiede zu PI stehen direkt in der Startmaske:

* **Kein `--append-system-prompt`.** Der stehende Stand geht über `AGENTS.projekt.md`
  hinein, das der Kopf bei jedem Start schreibt.
* **Das Gedächtnis hängt am Projekt.** `HERMES_HOME` zeigt auf
  `<projekt>/_agent/hermes` (geteiltes `config.yaml`/`.env`/`skills` verlinkt, nicht
  kopiert), deshalb ist die Projektwahl im Browser **Pflicht** — genau wie die
  Projektmatrix, die `start_hermes.sh` am Terminal zuerst zeigt. Im falschen Projekt
  serviert Hermes das an einer anderen Auslegung Gelernte als Tatsache.

Das Modell ist im Browser nicht wählbar: `hermes acp` nimmt keinen Modellschalter an,
es gilt `~/.hermes/config.yaml`.

### Zwei gemessene Fehler stromaufwärts in Hermes ACP

Beide sind mit einem **eigenen** ACP-Klienten nachgestellt, also nicht von diesem Repo
verursacht — und beide sind hier umgangen, nicht geflickt (v0.20.5):

1. **Parallele Werkzeugaufrufe liefern keine Ergebnisse.** Ruft das Modell in EINEM Zug
   mehrere Werkzeuge auf, schickt `hermes acp` je ein `tool_call`, aber **kein einziges**
   `tool_call_update` (1 Werkzeug → Aufruf + Ergebnis; 3 Werkzeuge → 3 Aufrufe, 0
   Ergebnisse). Der Lauf vom 04.09. zeigt es: 1.562 Ereignisse, 3 Werkzeugaufrufe, 0
   Ergebnisse, rechte Spalte leer. Verloren sind sie aber nicht — Hermes schreibt jedes
   Werkzeugergebnis in seine `state.db`, das Modell bekommt sie ja auch. Sie werden dort
   am Zugende **nur lesend** nachgeschlagen (die Datei gehört dem laufenden Hermes) und
   füllen die stummen Kacheln mit dem echten Text; nur wo auch die Ablage nichts hergibt,
   bleibt ein ehrlicher Platzhalter statt einer Erfindung.

2. **`skill_view("cae-orchestrator")` meldet „not found"** — obwohl `hermes skills list`
   den Skill zeigt (Quelle `local`, Repopfad in `skills.trusted_project_dirs`) und
   derselbe Aufruf in einem gewöhnlichen Python-Prozess mit demselben `HERMES_HOME` und
   demselben Arbeitsverzeichnis gelingt. Die Ursache liegt in Hermes' Projekt-Skill-Auflösung
   (`agent.skill_utils.get_project_skills_dirs` → `find_project_root` über
   `TERMINAL_CWD`/`Path.cwd()`, während die ACP-Sitzung ihren cwd in einer eigenen
   Contextvar hält, `agent/runtime_cwd.py`). Gegenmittel ist der oben genannte
   Dateipfad in jeder Startunterlage: eine Datei lesen statt suchen.

Ein dritter Unterschied ist kein Fehler, sondern Absicht: **`sitzungen()` bleibt bei Hermes
leer.** Seine Sitzungen liegen in der `state.db`, ACP kann sie erst NACH dem Start auflisten
— ein nachgebautes fremdes SQL-Schema wäre die nächste stille Kopie.

### Beide Köpfe, dieselbe Frage

```
Frage:  „Wie hoch ist B_gap im neuesten Projekt?"
PI      → B_gap = 0.806 T, mit Hinweis auf die analytische Herkunft
Hermes  → B_gap = 0,806 T, mit demselben Hinweis
Kontrolle aus results.json: 0.806
```

Beide greifen selbstständig zum Skill und geben den Herkunftshinweis mit — die
Ehrlichkeitsregel steht an einer Stelle und wirkt in beiden. (Hermes hat dabei ein
falsches Projektverzeichnis benannt und die richtige Zahl genannt; eine
Zuordnungsungenauigkeit des lokalen Modells, kein Werkzeugfehler.)

## Beide Köpfe im Browser: Arbeitsleiste, Archiv, Aufnahme

Die Reiter 🤖 PI und 🪽 Hermes auf `:5000` sind eine Seite mit einer Routenmenge (Details
weiter unten). Vier Dinge daran sind keine Kosmetik, sondern Antworten auf gemessene
Fehlbedienungen:

**Die Arbeitsleiste** unter der Ergebnisspalte (`/agent/arbeit`, Sekundentakt, ein Abruf
kostet 5 ms). Ein Agentenlauf sieht von außen minutenlang gleich aus: links läuft Text,
rechts steht nichts Neues — ob eine Recherche hängt, der Löser rechnet oder schlicht nichts
passiert, war nicht zu unterscheiden. Sechs Leuchten: **Rechnung** (die vierzehn
`*_state`-Dicts des Servers mit Namen und Fortschritt) · **Recherche** (von
`ema_recherche` selbst gesetzt, als Datei — die Recherche läuft im CLI-Unterprozess des
Agenten und käme sonst gar nicht im Serverprozess an) · **Löser** (ccx/Elmer/Z88/Gmsh/
FreeCAD/OpenFOAM/Blender über `/proc/<pid>/comm`, gegen den Prozess*namen*, sonst schaltete
ein `grep ccx` die Lampe an) · **GPU** (Schwelle 50 %; diese Karte zeigt im Leerlauf 18–24 %) ·
**Modell** · **Agent** (arbeitet / still seit …). Was bewusst fehlt, ist eine Lampe „das
Modell denkt": Ollama meldet nur, welches Modell im Speicher *liegt*, nicht ob es rechnet.

**Ein Zug, der nie endet, ist sichtbar und lösbar.** Gemessen am 04.09.: Hermes schickte auf
`session/prompt` keine Antwort mehr — kein Text, kein Werkzeug, kein Fehler. Die Eingabe
blieb mit „Der Agent arbeitet noch" gesperrt, der einzige Ausweg war, den Lauf zu beenden
und die Sitzung zu verlieren. Jetzt wird mitgeführt, wann zuletzt *irgendetwas* kam — ohne
diese Marke ist ein hängender Zug von einem langen nicht zu unterscheiden — die Leiste zeigt
„still seit 8:13", und ab 450 s gibt es eine Freigabe. Die Schwellen liegen bewusst über der
Dauer eines langen Werkzeugaufrufs. Die Freigabe **beendet den Agenten nicht**: eine später
doch noch eintreffende Antwort erscheint im Strom, und das steht auch im Verlauf — ein
stiller Neustart des Zuges wäre schlimmer, dann liefen zwei nebeneinander.

**Frühere Läufe sind wieder aufrufbar.** Nach jedem Zug wurden ein Protokoll und eine
Ereignis-Mitschrift geschrieben — gelesen hat das nie jemand, es gab keine Route, kein Verb,
keinen Knopf. Für den, der davorsitzt, ist „geschrieben, aber unerreichbar" dasselbe wie
„nicht gespeichert", und genau so wurde es gemeldet. `GET /agent/laeufe` listet jetzt jeden
Lauf (projektgebunden **und** die ungebundenen, beide Köpfe zusammen, neueste zuerst, je mit
den gegebenen Aufträgen), `GET /agent/lauf` gibt einen zurück. Die Übersicht liest eine
Mitschrift dabei **nie ganz ein**: eine gemessene Mitschrift ist 9,4 MB mit 140.872
Ereignissen, das Auflisten aller Läufe kostet trotzdem 0,12 s. Abgespielt wird über
**dieselben** Zeichenfunktionen wie der lebende Lauf — ein zweiter Satz liefe beim ersten
Fehlerbericht auseinander.

**Die Bildschirmaufnahme folgt der Ergebnisspalte.** Die alte Regel („Server rechnet →
Pause", begründet damit, am Bild ändere sich dann ohnehin nichts) ist gemessen falsch: im
Lauf vom 04.09. kamen **mitten im Rechenlauf fünf Bilder** in die rechte Spalte —
angehalten wurde also genau während der einzigen Momente, die aufzuheben sich lohnt. Jetzt
setzt jede Kachel, jedes Bild, jeder Auftrag und jedes Scrollen dort die Uhr zurück.
Wichtiger noch: **es wird mitgeschrieben, wann was geschah.** Neben dem Video entstehen eine
`.marken.tsv` und ein ausführbares `.schnitt.sh` — benachbarte Marken werden zu einem Stück
verschmolzen, jedes Stück geschnitten und alle aneinandergehängt. Bewusst **neu kodiert
statt `-c copy`**: kopierend schnitte ffmpeg an Schlüsselbildern und träfe den Moment um
Sekunden daneben. Damit ist die Pause nur noch Platzersparnis und kein Zwang mehr.

## Nachgewiesen

Beide Abfragen liefen gegen den laufenden Server, das Modell hat selbstständig zum
Skill und zum CLI gegriffen:

* „Wie viele Projekte liegen im CAE-Orchestrator, und läuft der Server?"
  → „Server läuft (Pipeline idle), 18 Projekte" — deckt sich mit `cae_cli.py health`.
* „Nimm das neueste Projekt und nenne B_gap und Kt."
  → richtiges Projekt, 0,766 T / 0,05 Nm/A, **samt Herkunftshinweis** auf die
  analytische Formel — die Ehrlichkeitsregel aus dem Skill greift.
