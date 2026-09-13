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
| **FluidX3D** — [ProjectPhysX](https://github.com/ProjectPhysX/FluidX3D) | Lattice-Boltzmann mit freier Oberfläche auf der GPU (`ema_fluidx3d.py`) | **eigene Lizenz — schränkt die NUTZUNG ein, s. eigenen Abschnitt unten** |
| **Code Aster 17.4.0** — [EDF](https://code-aster.org) | dritter Struktur-Löser (`cae_orchestrator/ema_aster.py`), aus einem entpackten Salome-Meca-Abbild unter `~/aster-build` | **GPL-3.0-or-later**, s. eigenen Abschnitt unten |
| PI — [`@earendil-works/pi-coding-agent`](https://github.com/earendil-works/pi) | Agenten-Harness für die Bedienung per lokalem Modell (`start_agent.sh`) | MIT |
| Hermes Agent 0.20.5 — [Nous Research](https://github.com/NousResearch/hermes-agent) | zweiter Agentenkopf (`start_hermes.sh`, `hermes acp`) | MIT (c) 2025 Nous Research |
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

**Z88Aurora®** ist Freeware des **Lehrstuhls für Konstruktionslehre und CAD (LCAD),
Universität Bayreuth, Universitätsstr. 30, 95447 Bayreuth**, verfasst und herausgegeben
von **Prof. Dr.-Ing. Frank Rieg**. „Z88" ist eine eingetragene Marke (Nr. 30 2009 064 238)
von Prof. Dr.-Ing. Frank Rieg. Der darunterliegende Kern **Z88OS** steht unter der GNU GPL.

Die Lizenzvereinbarung liegt der Software bei (Theorie-Handbuch, Abschnitt „License").
Die für dieses Repo maßgeblichen Punkte:

* **§1 Nutzungsrecht** — erlaubt die Nutzung „on any computer in multiple number of
  installations". Eine Einschränkung auf nichtkommerzielle Nutzung enthält die
  Vereinbarung **nicht**.
* **§2 Urheberrecht** — „There is no right to use trademarks, pictures, documentation
  … without naming LCAD." Daher die vollständige Nennung oben; wer Abbildungen oder
  Textstellen aus der Z88-Dokumentation übernimmt, nennt LCAD ebenfalls.
* **§3** — kein Vermieten, kein Verleasen, **kein Reverse Engineering, Dekompilieren
  oder Disassemblieren**. Ausdrücklich: „there is no warranty for accuracy of the
  given results."
* **§4/§5** — keine Gewährleistung, keine Haftung für Folgeschäden.
* **§7** — deutsches Recht.

> **Offenlegung zum Entstehen von `ema_z88.py`:** Drei Dateiformate (`Z88MAN.TXT`,
> die Materialdatei und der Aufrufvertrag von `z88r`) sind in der mitgelieferten
> Dokumentation **nicht beschrieben**. Sie wurden aus den Zeichenketten der Binärdateien
> (`strings`) und aus Fehlversuchen erschlossen — also durch Beobachten des Programms
> im Betrieb, nicht durch Dekompilieren oder Disassemblieren. Ob das unter §3 fällt, ist
> eine Rechtsfrage und keine technische; wer Z88 in einem geschäftlichen Zusammenhang
> einsetzt, sollte sie klären. In Deutschland erlaubt §69d Abs. 3 UrhG das Beobachten,
> Untersuchen und Testen eines Programms zum Ermitteln seiner Ideen und Grundsätze und
> ist vertraglich nicht abdingbar; §69e UrhG regelt die Dekompilierung zur
> Interoperabilität gesondert. Das ist ein Hinweis, keine Rechtsberatung.

Wer die Toolchain nachbaut, lädt Z88Aurora selbst von <https://z88.de/> — die dortigen
Nutzungsbedingungen gelten. Enthaltene Fremdkomponenten von Z88 (u. a. Intel MKL,
PARDISO, TetGen, Netgen, OpenCASCADE) reisen mit **jener** Installation, nicht mit
diesem Repo.

**Z88Arion** (Topologieoptimierung) wird **nicht** benutzt — es gibt keinen Linux-Bau.

### Code Aster 17.4.0 (EDF)

**Vorausgesetzt, nicht mitverbreitet.** Liegt lokal unter `~/aster-build` (aus
einem entpackten Salome-Meca-SIF-Abbild) und wird als **dritter Struktur-Löser**
neben CalculiX und Z88 benutzt. Dieses Repo enthält **keinen Aster-Quellcode**;
mitverbreitet sind allein `cae_orchestrator/ema_aster.py` und `test_aster.py`,
die Asters eigenes `.mail`-Format schreiben und die Ergebnisse zurücklesen.

Lizenz: **GPL-3.0-or-later**, gemessen an `~/aster-build/src/src/LICENSE` (GNU
GPL Version 3) und am Kopf jeder Quelldatei: *„Copyright (C) 1991 - 2026 - EDF -
www.code-aster.org … either version 3 of the License, or (at your option) any
later version."*

**Wie Aster gerufen wird, ist hier lizenzrelevant und deshalb ausgeschrieben:**
Aster 17 läuft als **Bibliothek** (`import code_aster`), aber **nicht in diesem
Prozess** — `ema_aster.loese` startet
`bash -lc 'source env_aster.sh; exec "$ASTER_PYTHON" rechnung.py'`, also einen
eigenen Prozess mit Asters eigenem Python. Der Orchestrator importiert
`code_aster` an keiner Stelle; ausgetauscht werden Dateien. Das ist derselbe
Abstand wie zu CalculiX, OpenFOAM, Blender und Z88 — und ein anderer als zu
**Gmsh**, das im selben Prozess importiert wird (s. nächster Abschnitt).

### Gmsh

**Vorausgesetzt, nicht mitverbreitet.** Benutzt wird das Python-Modul `gmsh` (4.15.2)
im venv des Orchestrators, installiert ueber `requirements.txt`; `/usr/bin/gmsh` (4.12.1)
liegt daneben und wird nicht gebraucht. Gmsh steht unter der GNU GPL v2+
mit Ausnahmen; siehe <https://gmsh.info/>. Gemessen am installierten Paket:
`gmsh-4.15.2.dist-info/METADATA` weist `License: GPLv2+` aus.

**Das ist die engste Kopplung dieser Liste** und der Grund, warum der Abschnitt
mehr als eine Zeile bekommt: Gmsh wird **im selben Python-Prozess importiert**
(`import gmsh` in `ema_deck.py`, `ema_em3d.py`, `ema_em2d_harm.py`,
`ema_em3d_harm.py`) — nicht als Unterprozess wie CalculiX, Aster, OpenFOAM,
Blender und Z88. Wer die Lizenz dieses Repositories ändern will, fängt hier an
zu prüfen: die GPL untersagt in **§6 (v2)** bzw. **§10 (v3)** ausdrücklich,
Empfängern *weitere* Beschränkungen aufzuerlegen. Solange dieses Repo unter MIT
steht, stellt sich die Frage nicht; eine Klausel „nicht kommerziell" oder „nicht
militärisch" über dem eigenen Code stellt sie sofort.

### FluidX3D (Dr. Moritz Lehmann / ProjectPhysX)

**Vorausgesetzt, nicht mitverbreitet** — und der **einzige** Eintrag dieser Liste,
dessen Lizenz nicht nur die Weitergabe, sondern die **Nutzung** einschränkt.
Deshalb ein eigener Abschnitt statt einer Tabellenzeile.

Der Quellbaum liegt unter `~/ai-workspace/FluidX3D` und ist über die
Wurzel-`.gitignore` (`/FluidX3D/`) von der Versionierung ausgenommen; dieses
Repository enthält **keinen FluidX3D-Quellcode**. Mitverbreitet sind allein die
eigenen Dateien `cae_orchestrator/ema_fluidx3d.py`, `fluidx3d_runner.py` und
`test_fluidx3d.py`.

Lizenz: `FluidX3D/LICENSE.md`, Copyright (c) 2022–2026 Dr. Moritz Lehmann.
Erlaubt sind **öffentliche Forschung, Lehre und private Nutzung**. Die vier
Punkte, die hier wirklich greifen:

1. **Keine kommerzielle Nutzung** (Klausel 2). Das schließt ausdrücklich ein,
   gegen Entgelt ein Produkt oder eine Dienstleistung anzubieten, deren Wert
   sich aus der Funktionalität dieser Software ergibt — Hosting und Support
   eingeschlossen. **Der MIT-Vermerk an der Wurzel gilt dafür nicht**: er
   erlaubt wörtlich das Verkaufen, für diesen Pfad ist das falsch.
2. **Keine militärische Nutzung** (Klausel 3).
3. **Kein KI-Training auf dem Quelltext** (Klausel 4) — auf dem Original, auf
   geänderten Fassungen und auf Teilen davon. Praktisch heißt das: den
   FluidX3D-Quelltext nicht in `ema_rag` legen, nicht in den Trainingssatz
   (`ema_training`) geben und nicht an ein Modell schicken. Das erzeugte
   `setup.cpp` ist eine geänderte Fassung und fällt mit darunter.
4. **Veröffentlichte Ergebnisse ziehen die Quelle nach** (Klausel 5): werden
   Binärdateien **oder Daten oder Ergebnisse** einer geänderten Fassung
   veröffentlicht, muss die geänderte Quelle mitveröffentlicht werden. Diese
   Pflicht ist hier erfüllt, solange `ema_fluidx3d.py` — der Erzeuger des
   `setup.cpp` — in diesem öffentlichen Repository liegt. Wer Bilder, Videos
   oder Kennwerte aus dem 🌀-Reiter veröffentlicht, sollte darauf verweisen.

**Was das Werkzeug von sich aus tut** (s. `cae_orchestrator/CLAUDE.md`): es
arbeitet in einer **Kopie** unter `$CAE_FLUIDX3D_HEIM` (Vorgabe `~/fluidx3d_cae`)
und rührt den Quellbaum nicht an; das erzeugte `setup.cpp` trägt im Kopf
`ALTERED SOURCE VERSION` samt Verweis auf das Original (Klauseln 1 und 7),
`vorbereiten` legt eine `HERKUNFT.txt` neben die Kopie, und
`test_fluidx3d.test_setup_code_vollstaendig_und_lizenztreu` prüft die
Kennzeichnung.

**Bei wissenschaftlichen Veröffentlichungen** sollen die unter
<https://github.com/ProjectPhysX/FluidX3D#references> genannten Arbeiten zitiert
werden (Klausel 6). Der Name „FluidX3D" steht unter deutschem Werktitelschutz
(§ 5 Abs. 3 MarkenG).

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

**Eine dritte Frage gehört dazu, und an ihr ist FluidX3D durchgerutscht:
schränkt die Lizenz die NUTZUNG ein?** Die beiden Fälle oben sortieren nach
*Weitergabe* — mitverbreitet oder nicht. Eine Lizenz kann aber auch dann binden,
wenn nichts weitergegeben wird: kein Verkauf, kein militärischer Einsatz, kein
KI-Training, oder eine Pflicht, die erst beim Veröffentlichen von Ergebnissen
entsteht. Das trifft **den Benutzer dieses Repositories**, nicht den Verteiler,
und der MIT-Vermerk an der Wurzel sagt dazu von sich aus nichts — er erlaubt
wörtlich das Verkaufen.

Solche Komponenten bekommen deshalb einen **eigenen Abschnitt** statt einer
Tabellenzeile, und der Verweis gehört zusätzlich in `LICENSE`,
`cae_orchestrator/LICENSE` und die Lizenzabschnitte beider READMEs — sonst steht
die Einschränkung an genau der Stelle nicht, an der jemand nach der Lizenz
sieht. (FluidX3D kam am 12.09.2026 dazu und fehlte hier bis zum 13.09.: die
Regel darüber fragte nur nach Weitergabe, und nach ihr war eine Tabellenzeile
ausreichend.)
