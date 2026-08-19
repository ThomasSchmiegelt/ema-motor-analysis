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
#    (Ollama als OpenAI-kompatibler Anbieter, qwen3.8 + qwen3.5:9b)

# 3) Orchestrator starten
cd ~/ai-workspace/cae_orchestrator && ./start.sh
```

## Benutzen

```bash
cd ~/ai-workspace
pi --provider ollama --model qwen3.8:latest                      # interaktiv
pi --provider ollama --model qwen3.8:latest -p "<Frage>"          # einmalig
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

`qwen3.8:latest` ist Qwen3.5 27B (Q4_K_M, 17,7 GB) mit 262 k Kontext und
Werkzeugaufruf-Fähigkeit. Die Modelldatei ist auf `contextWindow` 262144 gesetzt;
der große Kontext ist hier nützlich, weil `results.json` auch nach dem Filtern noch
umfangreich ist.

## Nachgewiesen

Beide Abfragen liefen gegen den laufenden Server, das Modell hat selbstständig zum
Skill und zum CLI gegriffen:

* „Wie viele Projekte liegen im CAE-Orchestrator, und läuft der Server?"
  → „Server läuft (Pipeline idle), 18 Projekte" — deckt sich mit `cae_cli.py health`.
* „Nimm das neueste Projekt und nenne B_gap und Kt."
  → richtiges Projekt, 0,766 T / 0,05 Nm/A, **samt Herkunftshinweis** auf die
  analytische Formel — die Ehrlichkeitsregel aus dem Skill greift.
