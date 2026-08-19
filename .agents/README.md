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
Antwort lesen. Der Alltagspfad hat neun Verben, `raw` deckt den Rest ab.

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
