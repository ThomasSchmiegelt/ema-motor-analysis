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
`6b9d840acbf5` — ein `ollama pull` unter gleichem Namen tauscht sonst still die
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
| `.agents/skills/cae-orchestrator/SKILL.md` | Bedienanleitung, wird bei Bedarf geladen |
| `.agents/skills/cae-orchestrator/references/routes.md` | alle 135 Routen, nach Bereichen |
| `cae_orchestrator/cae_cli.py` | das eigentliche Werkzeug |

**Warum ein CLI und nicht MCP:** PI bindet Werkzeuge bewusst als „CLI mit README"
ein. Das passt hier auch inhaltlich — ein lokales Modell kann 135 Routen nicht als
135 Werkzeugschemata halten, wohl aber `cae_cli.py run em3d --wait` aufrufen und die
Antwort lesen. Der Alltagspfad hat zehn Verben, `raw` deckt den Rest ab.

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

## Nachgewiesen

Beide Abfragen liefen gegen den laufenden Server, das Modell hat selbstständig zum
Skill und zum CLI gegriffen:

* „Wie viele Projekte liegen im CAE-Orchestrator, und läuft der Server?"
  → „Server läuft (Pipeline idle), 18 Projekte" — deckt sich mit `cae_cli.py health`.
* „Nimm das neueste Projekt und nenne B_gap und Kt."
  → richtiges Projekt, 0,766 T / 0,05 Nm/A, **samt Herkunftshinweis** auf die
  analytische Formel — die Ehrlichkeitsregel aus dem Skill greift.
