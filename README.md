# ai-workspace

Monorepo für die E-Maschinen-CAE-Toolkette — betrieben unter dem eingeschränkten
User **`cae`** (kein sudo), alles auf `localhost`.

**Ehrlich vorweg, damit die Tabelle nicht mehr verspricht als sie hält:** getragen
wird die Kette von `cae_orchestrator`. Die übrigen Ordner sind eigenständige
Teilprojekte in unterschiedlichem Reifegrad, die *heute* nicht miteinander
verdrahtet sind — siehe die Spalte „Verbindung".

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
./start_hermes.sh --nur-pruefen           # nur der Nachweis, dass nichts nach draußen geht
```

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
| `start_agent.sh` | Wurzel | Startkette + Sitzungsverwaltung |
| `.agents/` | Wurzel | Skill-Definition für PI (`skills/cae-orchestrator/SKILL.md`) und Einrichtung |
| `cae_orchestrator/cae_cli.py` | Teilprojekt | die Kommandozeile, die beide Agenten benutzen — zwölf Verben über HTTP auf `:5000` (`rotor-check`, `struktur` und `topopt` rechnen lokal) |
| `start_hermes.sh` | Wurzel | zweiter Agentenkopf: **Hermes Agent**, gleiches Modell, gleicher Skill, mit gemessenem Netznachweis |

**Warum eine CLI und kein MCP-Server:** ein lokales Modell kann die ~135 HTTP-Routen des
Orchestrators nicht als 135 Werkzeugschemata im Kontext halten. PI bindet Werkzeuge
deshalb als *Skill = CLI + README*; `cae_cli.py` filtert Base64-Nutzlasten heraus, kappt
die Ausgabe und trägt den Zustand im Exit-Code. Details in `.agents/README.md`.

**Modell:** `qwen-gross:latest` (Qwen3.5 27B Q4_K_M, 64 k Kontext) — dasselbe Modell, das
auch Bericht, Chat und KI-Auslegung im Orchestrator benutzen. Eine Quelle dafür:
`ema_report.DEFAULT_MODEL` / `DEFAULT_NUM_CTX`, umstellbar über `CAE_LLM_MODEL` bzw.
`CAE_LLM_NUM_CTX` ohne Codeänderung.

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
- **Z88Aurora V5** → `/opt/z88aurora` (2,8 GB, nur die Stapel-Löser werden benutzt). `z88r` findet sein eigenes MKL nicht — `LD_LIBRARY_PATH` auf `/opt/z88aurora/bin/ubuntu64` ist der ganze Trick. **Z88Arion gibt es nicht für Linux**
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

## Lizenz

Der hier entwickelte Code steht unter der **MIT-Lizenz** (`LICENSE`).

Fremdkomponenten behalten ihre eigenen Lizenzen. `THIRD-PARTY-NOTICES.md` trennt dabei,
was **mitverbreitet** wird (im Repo enthalten — Lizenztext und Copyright-Vermerk müssen
mitreisen) und was lediglich **vorausgesetzt** wird (lokal installiert oder selbst gebaut,
nicht Teil dieses Repos). Dazu zählt insbesondere **PicoGK** von LEAP 71 (Apache-2.0):
das `pikogk`-Subprojekt bindet es ein, enthält aber keinen PicoGK-Quellcode.
