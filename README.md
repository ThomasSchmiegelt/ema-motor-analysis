# ai-workspace

Monorepo für die zusammengehörige E-Maschinen-CAE-Toolkette. Drei Teilprojekte, die
über lokale HTTP-Dienste (`localhost`) zusammenspielen — betrieben unter dem
eingeschränkten User **`cae`** (kein sudo).

## Teilprojekte

| Ordner | Was | Stack | Start |
|---|---|---|---|
| `cae_orchestrator/` | Browser-CAE für IPM-Motoren (Geometrie → EM-Feld → FEM → Thermik → Fahrzyklus, PDF-Bericht) | Python/Flask + FreeCAD/Elmer/OpenFOAM/Blender | `cd cae_orchestrator && ./start.sh` → http://localhost:5000 |
| `connection_detection/` | FreeCAD-Workbench: Verbindungserkennung in STEP-Baugruppen (Basis für Multi-Body-CalculiX) | Python-FreeCAD-Addon (`rtree`) | via `FreeCADCmd cli.py -- input.step -o out.json` |
| `pikogk/` | PicoGK-Geometriekernel mit HTTP-API (Voxel-/Implicit-Geometrie, „Engine-Head"-Skills) | .NET 9 + native `picogk.so` | `cd pikogk && ./start.sh` → http://localhost:5266 |

## Zusammenspiel

`pikogk` und Ollama laufen als **lokale HTTP-Dienste**; `cae_orchestrator` (und Skripte)
rufen sie über `localhost` (`:5266` bzw. `:11434`) — Aufrufort egal. `connection_detection`
teilt sich die FreeCAD-Toolchain mit `cae_orchestrator`.

## Agentenbedienung (lokales Modell, kein Cloud-Zugang)

Die Toolkette lässt sich außer im Browser auch von einem **lokalen** Sprachmodell
bedienen — über [PI](https://pi.dev) (`@earendil-works/pi-coding-agent`) und Ollama.
Eine Zeile startet beides:

```bash
./start_agent.sh                          # Orchestrator (falls nötig) + PI, interaktiv
./start_agent.sh -p "Wie hoch ist B_gap im neuesten Projekt?"
./start_agent.sh --weiter                 # letzte Sitzung fortsetzen
./start_agent.sh --sitzungen              # Sitzungen dieses Ordners auflisten
```

Das Skript prüft Ollama, **nagelt das Modell auf seine ID fest** (ein `ollama pull` unter
gleichem Namen tauscht sonst still die Gewichte), startet den Server nur, wenn `:5000`
nicht antwortet, und wartet auf dessen Erreichbarkeit, bevor PI läuft.

| Teil | Wo | Was |
|---|---|---|
| `start_agent.sh` | Wurzel | Startkette + Sitzungsverwaltung |
| `.agents/` | Wurzel | Skill-Definition für PI (`skills/cae-orchestrator/SKILL.md`) und Einrichtung |
| `cae_orchestrator/cae_cli.py` | Teilprojekt | die Kommandozeile, die der Agent benutzt — zehn Verben über HTTP auf `:5000` (`rotor-check` rechnet lokal) |

**Warum eine CLI und kein MCP-Server:** ein lokales Modell kann die ~135 HTTP-Routen des
Orchestrators nicht als 135 Werkzeugschemata im Kontext halten. PI bindet Werkzeuge
deshalb als *Skill = CLI + README*; `cae_cli.py` filtert Base64-Nutzlasten heraus, kappt
die Ausgabe und trägt den Zustand im Exit-Code. Details in `.agents/README.md`.

**Modell:** `qwen-gross:latest` (Qwen3.5 27B Q4_K_M, 64 k Kontext) — dasselbe Modell, das
auch Bericht, Chat und KI-Auslegung im Orchestrator benutzen. Eine Quelle dafür:
`ema_report.DEFAULT_MODEL` / `DEFAULT_NUM_CTX`, umstellbar über `CAE_LLM_MODEL` bzw.
`CAE_LLM_NUM_CTX` ohne Codeänderung.

## Geteilte Toolchain (systemweit / /opt, nicht in diesem Repo)

- FreeCAD-1.1-Quellbuild + CalculiX → `/opt/cae-tools/freecad_1.1_quellcode` (Symlink `~/freecad_1.1_quellcode`)
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

## Lizenz

Der hier entwickelte Code steht unter der **MIT-Lizenz** (`LICENSE`).

Fremdkomponenten behalten ihre eigenen Lizenzen. `THIRD-PARTY-NOTICES.md` trennt dabei,
was **mitverbreitet** wird (im Repo enthalten — Lizenztext und Copyright-Vermerk müssen
mitreisen) und was lediglich **vorausgesetzt** wird (lokal installiert oder selbst gebaut,
nicht Teil dieses Repos). Dazu zählt insbesondere **PicoGK** von LEAP 71 (Apache-2.0):
das `pikogk`-Subprojekt bindet es ein, enthält aber keinen PicoGK-Quellcode.
