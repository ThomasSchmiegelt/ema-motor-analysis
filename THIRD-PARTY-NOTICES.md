# Hinweise zu Fremdkomponenten

Dieses Repository steht unter der MIT-Lizenz (s. `LICENSE`). Der MIT-Vermerk an
der Wurzel gilt für **den hier entwickelten Code**, nicht für die unten
aufgeführten Fremdkomponenten — die behalten ihre eigenen Lizenzen.

Die Liste trennt bewusst zwei Fälle, weil daran unterschiedliche Pflichten
hängen:

* **Mitverbreitet** — die Datei liegt im Repository und geht bei jedem Klon mit.
  Hier verlangen die Lizenzen, dass Copyright-Vermerk und Lizenztext mitreisen.
* **Vorausgesetzt** — wird lokal installiert oder gebaut und ist **nicht** Teil
  dieses Repositories. Genannt zur Nachvollziehbarkeit, nicht als Auflage.

## Mitverbreitet

| Komponente | Pfad im Repo | Lizenz | Copyright |
|---|---|---|---|
| VTK.js | `cae_orchestrator/vendor/vtk.js` (Lizenz: `vtk.js.LICENSE.txt` daneben) | BSD-3-Clause | (c) 2016 Kitware, Inc. |
| c-blosc | `pikogk/local-install/lib/libblosc.{a,so.1.21.7}` | BSD-3-Clause | 2009–2018 Francesc Alted; 2019–heute Blosc Development Team |
| oneTBB | `pikogk/SkillSandbox/host-libs/libtbb.so.12` | Apache-2.0 | Intel Corporation |
| Boost.Iostreams | `pikogk/SkillSandbox/host-libs/libboost_iostreams.so.1.83.0` | BSL-1.0 | Boost-Mitwirkende |

Anmerkungen:

* Das VTK.js-Bündel verweist im Kopf auf `vtk.js.LICENSE.txt`; diese Datei liegt
  jetzt daneben und enthält den BSD-3-Vermerk von Kitware (wörtlich aus dem
  npm-Paket).
  **Offen:** das vendorierte Bündel ist 2.010.725 Bytes groß und stimmt mit
  keinem npm-Release der Serien 17.x bis 36.x überein (alle ≥ 2,39 MB; per
  Größen- und SHA-256-Abgleich geprüft). Seine Herkunft ist damit nicht belegt,
  und die von webpack extrahierten Banner der mitgebündelten Fremdabhängigkeiten
  ließen sich nicht versionsgenau beilegen. Beim nächsten Anfassen des
  3D-Viewers sollte das Bündel gegen ein angeheftetes npm-Release getauscht
  werden — das schließt beides zugleich.
* c-blosc bündelt seinerseits FastLZ, LZ4, Snappy, Zlib und Bitshuffle; die
  jeweiligen Texte liegen im c-blosc-Quellbaum unter `LICENSES/` (BSD-/MIT-artig).
* oneTBB steht unter Apache-2.0: Bei Weitergabe der Binärdatei gehören
  Lizenztext **und** eine etwaige `NOTICE` dazu.

## Vorausgesetzt, aber nicht mitverbreitet

Diese Werkzeuge werden über `localhost` angesprochen oder aus dem Quellcode
gebaut. Sie sind **nicht** Teil dieses Repositories — ein frischer Klon holt und
baut sie selbst (s. `pikogk/EXPERIENCE_REPORT.md` und die `install.sh`-Skripte).

| Komponente | Rolle | Lizenz |
|---|---|---|
| PicoGK / PicoGKRuntime — [LEAP 71](https://leap71.com/) | Geometriekernel des `pikogk`-Subprojekts | Apache-2.0 |
| PicoGK Examples | Beispielcode | CC0-1.0 |
| FreeCAD | CAD-Geometrie, Vernetzung | LGPL-2.1-or-later |
| CalculiX (`ccx`) | Struktur-FEM | GPL-2.0-or-later |
| Elmer FEM | 3D-Magnetostatik | LGPL-2.1 (Solver: GPL) |
| OpenFOAM (ESI, v2406) | VOF-Zweiphasenströmung | GPL-3.0 |
| Blender | Mantaflow-FLIP-Fluidsimulation | GPL-3.0 |
| Ollama + verwendete Modelle | lokale LLM-Dienste | Ollama MIT; Modelle mit je eigenen Bedingungen (das Standardmodell `qwen-gross`/`qwen3.8` = Qwen3.5 27B weist in seinen GGUF-Metadaten `general.license = apache-2.0` aus) |
| PI — [`@earendil-works/pi-coding-agent`](https://github.com/earendil-works/pi) | Agenten-Harness für die Bedienung per lokalem Modell (`start_agent.sh`) | MIT |
| .NET 9 Runtime/SDK | Laufzeit des `pikogk`-Dienstes | MIT |

**Zu PicoGK im Besonderen:** Die Unterverzeichnisse `pikogk/PicoGK/`,
`PicoGKRuntime/`, `PicoGKWebApi/`, `PicoGK_Examples/` und `c-blosc/` sind eigene
Git-Repositories und über die Wurzel-`.gitignore` von der Versionierung
ausgenommen. Dieses Repository enthält also **keinen PicoGK-Quellcode**;
mitverbreitet wird lediglich das oben genannte, aus c-blosc gebaute Binärartefakt.
Sollte PicoGK künftig doch mit ausgeliefert werden (Quellcode oder `picogk.so`),
greift Apache-2.0 §4 vollständig: Lizenz beilegen, `NOTICE` weiterreichen und
Änderungen kennzeichnen.

### Z88Aurora V5 (Universität Bayreuth)

**Vorausgesetzt, nicht mitverbreitet.** Liegt lokal unter `/opt/z88aurora` (2,8 GB)
und wird ausschließlich als **externes Programm** aufgerufen (`z88r` im Stapelbetrieb).
Dieses Repo enthält keinen Z88-Quellcode und keine Z88-Binärdatei; `ema_z88.py` schreibt
nur Eingabedateien im offenen Z88-Format und liest die Ausgabedateien.

Z88Aurora ist Freeware der Universität Bayreuth (Lehrstuhl für Konstruktionslehre und
CAD, Prof. Frank Rieg); der darunterliegende Kern **Z88OS** steht unter der GNU GPL.
Wer die Toolchain nachbaut, lädt Z88Aurora selbst von <https://z88.de/> — die dortigen
Nutzungsbedingungen gelten. Enthaltene Fremdkomponenten von Z88 (u. a. Intel MKL,
PARDISO, TetGen, Netgen, OpenCASCADE) reisen mit **jener** Installation, nicht mit
diesem Repo.

**Z88Arion** (Topologieoptimierung) wird **nicht** benutzt — es gibt keinen Linux-Bau.

### Gmsh

**Vorausgesetzt, nicht mitverbreitet.** Benutzt wird das Python-Modul `gmsh` (4.15.2)
im venv des Orchestrators, installiert ueber `requirements.txt`; `/usr/bin/gmsh` (4.12.1)
liegt daneben und wird nicht gebraucht. Gmsh steht unter der GNU GPL v2+
mit Ausnahmen; siehe <https://gmsh.info/>.

## Subprojekt `lego/`

Die Quellen dieses Subprojekts sind in `lego/README.md` unter „Quellen und
Lizenzen" aufgeführt; keine davon wird hier mitverbreitet:

* **BrickNet** — Kulits & Schmid, CVPR 2026, MIT. Bibliothek, Kollisionsnetze
  und die vortrainierten Qwen3-Adapter sind frei; die Datensätze sind gated.
* **ORCA Hand** — ETH Zurich Soft Robotics Lab / ORCA Dexterity, Inc.
  `orcahand_description` MIT, `orcahand_hardware` CC BY 4.0. Die Lizenz verlangt
  die Namensnennung: **„ORCA Hand by ORCA Dexterity, Inc. — CC BY 4.0"**.
  Der Lizenztext liegt unter `lego/reference/orca/LICENSE.orcahand_description`.
* **LDraw** — Teilebibliothek, CCAL 2.0.
* **Studio 2.0** — BrickLink, proprietär, kostenlos; nur als Betrachter genutzt,
  keine Datenquelle.

## Pflege

Wer eine Fremdkomponente **in** das Repository legt (Binärdatei, gebündeltes
Skript, kopierter Quellcode), trägt sie oben unter „Mitverbreitet" ein und legt
den zugehörigen Lizenztext daneben. Für die reine Benutzung eines lokal
installierten Werkzeugs genügt der Eintrag unter „Vorausgesetzt".
