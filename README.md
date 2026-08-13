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
