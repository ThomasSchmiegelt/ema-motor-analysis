# E-Maschinen Analyse

Browser-basiertes Werkzeug zur Auslegung und Analyse von Innenläufer-Permanentmagnetmotoren (IPM). Der Nutzer konfiguriert die Motor-Geometrie im Browser, dann läuft eine automatisierte Kette: FreeCAD-Geometrieerzeugung → 2D-FDM-Elektromagnetfeldberechnung → CalculiX-Strukturmechanik (Fliehkraft) → thermisches Netzwerk → Fahrzyklus-Verlustintegration. Optional kann ein PDF-Bericht über ein lokales LLM (Ollama) erzeugt werden.

> **Bedienung Schritt für Schritt:** siehe [NUTZUNGSANLEITUNG.md](NUTZUNGSANLEITUNG.md).
> **Berechnungsmethodik:** siehe [EM_BERECHNUNG.md](EM_BERECHNUNG.md).

## Bedienoberfläche

Die Oberfläche (`ema.html`) ist ein **Workflow mit Tabs**: ① Geometrie · ② Betrieb & Material · ③ Berechnung · ▶ Live-Simulation · 📊 FEM-Ergebnisse · 📄 Bericht · ⚖ Vergleich. Rechts läuft eine **persistente Live-Vorschau** (Motorquerschnitt + Magnetfeld, mit Pause-Knopf), die Trennlinien zwischen Eingaben/Vorschau und über dem Footer sind **ziehbar**, und ein globaler **Analyse-starten-Footer** zeigt den Fortschritt. Weitere Komfortfunktionen:

- **🧠 Text → Auslegung** – Anwendung in Worten beschreiben, das LLM leitet einen vollständigen, validierten Parametersatz ab (`ema_text2ema.py`).
- **🎯 Zielwertoptimierung** – Randbedingungen + freie Parameter mit Bereichen vorgeben; ein LLM steuert eine Suche über einen schnellen Analytik-Evaluator (ohne FreeCAD/FEM), bester zulässiger Treffer → optional Voll-Lauf (`ema_optimize.py`).
- **📂 Projekt-Browser** – Galerie aller Projekte mit Vorschau + Kennwerten, zum Ansehen/Laden.
- **💬 Ergebnis-Chat** – Fragen zum geladenen Projekt oder zum Variantenvergleich (`ema_chat.py`).
- **🖼 Einzelbild-Vorschau** – ein Feldbild ohne Volllauf, bis 5000 px (Multigrid-Solver).

---

## Was das Tool macht

### 1. Geometrie-Konfiguration (Browser)

Die Benutzeroberfläche (`ema.html`) erlaubt die vollständige parametrische Beschreibung des Motors:

- **Stator:** Außen-/Innendurchmesser, Nutzahl, Nuttiefe, Blechpaketlänge
- **Rotor:** Außendurchmesser, Wellendurchmesser, Polpaarzahl
- **Magnettaschen:** Topologien V, Doppel-V, U, Delta, PMa-SynRM, SPM, Halbach, Speiche, Balken (Breite, Dicke, Öffnungswinkel, Position) — automatisch auf die geometrisch maximale Länge beschnitten. Für die V-Form wahlweise auch **per Durchmesser** (Außen-Ø / Innen-Ø der Tasche + Winkel) definierbar.
- **Magnet-Orientierung:** Polung wahlweise über die lange Magnetseite (quer magnetisiert, Standard) oder um 90° gedreht über die kurze Seite — identisch in Live-Vorschau und FDM-Feldsimulation.
- **Wicklung:** Wicklungsart (Hairpin / Rundleiter), **Leiter pro Nut** (geradzahlig 2…12) und **Spulenweite** (Nutschritte, gesehnt möglich). Die Hairpin-Wickelköpfe werden als kollisionsfreie U-Pins (radial gestaffelte Kronen) im CAD-Modell erzeugt; die Leiterzahl je Nut geht auch in Kupfervolumen/Phasenwiderstand des Thermomodells ein.
- **Kühlung:** Natürliche Konvektion / Zwangsluft / Wassermantel / Öl-Spray
- **Nennpunkt:** Drehzahl, Drehmoment, Phasenstrom (d/q-Komponenten)
- **Projektname** für Archivierung

### 2. FEM-Geometrieerzeugung (FreeCAD)

`ema_freecad.py` generiert und führt FreeCAD-Python-Skripte headless aus:
- Stator-Ring, Rotorkern, V-förmige Magnettaschen via booleschen Operationen
- Speicherung als `.FCStd` und STEP-Export
- Renderings (isometrisch, Draufsicht) als PNG für den Bericht

### 3. Elektromagnetische Feldberechnung (`ema_analysis.py`)

Eigener 2D-FDM-Feldsolver (numpy + scipy), Auflösung im UI wählbar (100–800 px, Einzelbild bis 5000 px):

- Löst `∇(ν∇A) = −J` mit einer **direkten Sparse-Faktorisierung** (`scipy splu`, exakt bei jeder Auflösung, pro Geometrie gecacht); für sehr hohe Auflösung (> 2500 px) ein **CG-beschleunigter AMG-Solver** (`pyamg`). Fällt ohne scipy auf iterative SOR zurück.
- Materialien: Eisen µ_r = 500, NdFeB µ_r = 1.05, Statorwicklung als Volumenstrom
- Permanentmagnete als äquivalente Oberflächenströme modelliert
- Skalierung des FDM-Ergebnisses auf physikalische Tesla-Werte via analytischer Luftspaltfeld-Formel
- Berechnet: B_gap, Flussverkettung, Gegen-EMK, Drehmoment (Ld/Lq-Salienz), Ummagnetisierungsverluste, Stromwärmeverluste, Wirkungsgrad

### 4. Thermisches Modell (`ema_thermal.py`)

Stationäres Lumped-Parameter-Wärmenetzwerk (LPTN) mit 6 Knoten:

| Knoten | Bedeutung |
|---|---|
| W | Wicklung (Hairpin Cu) |
| Si | Statoreisen (Joch + Zähne) |
| Ri | Rotoreisen |
| M | Magnete |
| Sh | Welle |
| H | Gehäuse |

Kühltypen mit kalibrierten h_eff-Werten: Natürliche Konvektion, Zwangsluft, Wassermantel (h=800 W/m²K), Öl-Spray (h=2500 W/m²K). Der Luftspalt koppelt die Magnete über Konvektion **und** Strahlung an die Statorbohrung; ein Teil davon koppelt direkt an die Wicklung, sodass die Rotormagnete den Wärmeeintrag aus dem heißen Kupfer erhalten.

### 5. Fahrzyklus-Verlustintegration (`ema_drivecycle.py`)

- Eingebettetes WLTP Klasse 3b-Profil, Autobahn-Vollgas und **Anhänger-Alpenpass**
- Anhänger ist einstellbar: **Anhängermasse (inkl. Nutzlast), Achszahl und maximale Steigung [%]** (Standard 15 %)
- Upload eigener Zyklen als `t[s], v[km/h]`-CSV
- Verlustintegration mit transienter und stationärer Thermik je Zyklus

### 6. Strukturmechanische FEM (CalculiX)

`ema_freecad.py` + `freecad_runner.py` führen eine Fliehkraftanalyse des Rotors durch:
- FreeCAD erzeugt Gmsh-Vernetzung der Rotorgeometrie; die **Netz-Auflösung ist
  einstellbar** (`struct_mesh_mm`, 4/3/2,5/2 mm – kleiner = feiner, löst die
  Spannungsspitzen an den Magnettaschen-Stegen besser auf)
- CalculiX (ccx) löst die statische Spannungsanalyse **einmalig** bei Maximaldrehzahl
- Da Verschiebung und Spannung linear mit der Fliehkraft (∝ Drehzahl²) skalieren,
  werden daraus ohne weitere Solver-Läufe abgeleitet:
  - **hochauflösende Verformungsbilder** (bis 5000 px) bei **Nennlast**,
    **Maximaldrehzahl** und **Berstdrehzahl** (SF→1)
  - ein **Verformungs-Video** (Drehzahl-Rampe 0→max, feste Überhöhung)
- Ausgabe: Von-Mises-Spannungen, Verformungen, Sicherheitsfaktor, Berstdrehzahl, Knotenzahl

### 7. Projektverwaltung

- Jede Analyse wird als eigenes Projekt unter `~/cae_projekte/<timestamp>/` gespeichert
- Bis zu 10 Designvarianten können nebeneinander verglichen werden (Überlagerungsdiagramme, Vergleichstabelle, Vergleichsbericht mit Parameter-/Einfluss-Tabellen)
- Projekt-Browser (Galerie) und Laden abgeschlossener Projekte ohne Neuberechnung

### 8. PDF-Berichtsgenerierung (`ema_report.py`)

- LLM (Ollama) generiert deutschen technischen Bericht aus `results.json`
- Markdown-Ausgabe mit `[BILD:<key>]`-Platzhaltern → automatisch durch erzeugte Charts ersetzt
- Konvertierung: `pandoc` + `pdflatex` → `bericht.pdf`
- Agentischer Modus: mehrere Experten-LLM-Agenten schreiben Teilkapitel parallel (`ema_experts.py`)

---

## Voraussetzungen

### Pflicht

| Werkzeug | Version | Hinweis |
|---|---|---|
| Python | 3.10+ | Systeminstallation |
| FreeCAD | 1.1.x | aus Quellcode gebaut (siehe unten) |
| CalculiX (ccx) | 2.21+ | im FreeCAD-Pixi-Environment enthalten |
| [pixi](https://pixi.sh) | beliebig | zum Aufruf von FreeCAD mit korrekter Umgebung |

### Optional (nur für PDF-Berichte)

| Werkzeug | Hinweis |
|---|---|
| [Ollama](https://ollama.com) | lokal laufend auf `localhost:11434` |
| `ministral-3:14b` | `ollama pull ministral-3:14b` |
| pandoc | `sudo apt install pandoc` |
| pdflatex | `sudo apt install texlive-latex-base texlive-fonts-recommended` |

Die gesamte Analyse-Pipeline (FDM-Feldsolver, Thermik, Fahrzyklus, FEM) läuft vollständig ohne LLM. Ollama wird nur für die komfortbasierten Zusatzfunktionen aufgerufen — Bericht (`ema_report.py`, `ema_experts.py`), Ergebnis-Chat (`ema_chat.py`), Text→Auslegung (`ema_text2ema.py`) und die Steuerung der Zielwertoptimierung (`ema_optimize.py`) — immer mit dem Modell `ministral-3:14b`, das im Code fest eingestellt ist. Ohne Ollama bleiben alle physikalischen Berechnungen voll nutzbar.

---

## FreeCAD 1.1.x aus Quellcode

Das Tool benötigt FreeCAD 1.1.x aus dem Quellcode-Build via pixi. Fertig kompilierte FreeCAD-1.2-Pakete (z.B. unter `/opt/freecad-1.1/`) haben einen bekannten Visualisierungsfehler und werden **nicht** unterstützt.

```bash
# FreeCAD-Quellcode holen und bauen
git clone https://github.com/FreeCAD/FreeCAD ~/freecad_1.1_quellcode
cd ~/freecad_1.1_quellcode
# Auf den 1.1.x-Branch wechseln (empfohlen: 0.22 oder 1.1-release)
git checkout 0.22
pixi run install-release
```

Erwartete Pfade nach dem Build:
```
~/freecad_1.1_quellcode/build/release/bin/FreeCADCmd   ← FreeCAD-Binary
~/freecad_1.1_quellcode/.pixi/envs/default/bin/ccx     ← CalculiX
```

---

## Pfade anpassen

Alle hardcodierten Pfade befinden sich an **zwei Stellen**:

### `start.sh` (Zeilen 5–7)
```bash
FREECAD_ROOT="$HOME/freecad_1.1_quellcode"
FREECAD_CMD="$FREECAD_ROOT/build/release/bin/FreeCADCmd"
CCX_CMD="$FREECAD_ROOT/.pixi/envs/default/bin/ccx"
```

### `freecad_runner.py` (Zeilen 14–18)
```python
FREECAD_ROOT  = os.path.expanduser("~/freecad_1.1_quellcode")
FREECAD_BIN   = os.path.join(FREECAD_ROOT, "build/release/bin/FreeCAD")
FREECADCMD_BIN = os.path.join(FREECAD_ROOT, "build/release/bin/FreeCADCmd")
CCX_CMD = os.path.join(FREECAD_ROOT, ".pixi/envs/default/bin/ccx")
```

`server.py` liest `FREECAD_ROOT` ebenfalls aus (Zeile 147) — mit demselben `~/freecad_1.1_quellcode`-Standardwert.

Projektausgaben landen unter `~/cae_projekte/` (konfigurierbar in `server.py`, Zeile 9: `PROJECTS_ROOT`).

---

## Installation

```bash
git clone <repo-url> cae_orchestrator
cd cae_orchestrator
./install.sh
```

`install.sh` prüft alle Abhängigkeiten, legt die virtuelle Python-Umgebung an und gibt eine Zusammenfassung aus, was ggf. noch fehlt.

Nach erfolgreicher Installation:

```bash
./start.sh
```

Der Server startet auf **http://localhost:5000** und öffnet den Browser automatisch.

---

## Projektstruktur

```
server.py          Flask-Backend — REST-API + statisches Datei-Serving
ema.html           Browser-UI (Vanilla JS, kein Build-Schritt nötig)
ema_pipeline.py    Pipeline-Orchestrierung (Geometrie → EM → Thermik → FEM)
ema_freecad.py     FreeCAD-Skriptgenerierung (Rotor, Stator, FEM)
ema_analysis.py    2D-FDM-Elektromagnet-Feldsolver (numpy)
ema_thermal.py     Stationäres LPTN-Wärmemodell (6 Knoten)
ema_topology.py    Magnet-Platzierung (einzige Quelle, gespiegelt im JS von ema.html)
ema_drivecycle.py  Fahrzyklen (WLTP-3b, Vollgas, Anhänger einstellbar, CSV)
ema_compare.py     Variantenvergleich (bis zu 10 Projekte, Overlay-Charts)
ema_report.py      LLM → Markdown → pandoc → PDF-Bericht (+ Vergleichsbericht)
ema_experts.py     Agentischer Modus: mehrere LLM-Experten-Agenten
ema_chat.py        Ergebnis-/Vergleichs-Chat (Ollama)
ema_optimize.py    Zielwertoptimierung (LLM-gesteuert, schneller Analytik-Evaluator)
ema_text2ema.py    Text → validierter Parametersatz (Ollama)
freecad_runner.py  FreeCAD-Subprocess-Wrapper (headless, Output-Parsing)
start.sh           Startskript mit Prerequisite-Prüfung
install.sh         Einmalige Installation und Konfigurationsprüfung
requirements.txt   Python-Abhängigkeiten
```

---

## Python-Bibliotheken

| Paket | Zweck |
|---|---|
| `flask` | HTTP-Server, REST-API, statisches Datei-Serving |
| `numpy` | FDM-Feldsolver, Thermisches Netzwerk, Fahrzyklus-Verlustintegration |
| `scipy` | direkte Sparse-Faktorisierung des FDM-Feldlösers (sonst iterative SOR) |
| `pyamg` | iterativer AMG-Solver für sehr hohe Feldauflösung (> 2500 px); optional |
| `matplotlib` | Charts, Feldanimation (Agg-Backend, kein Display nötig) |

Alle Versionen: `requirements.txt`. Die Ollama-REST-API wird direkt über `urllib.request` aus der Python-Standardbibliothek aufgerufen. Externe Solver (FreeCAD, CalculiX, pandoc, pdflatex) werden als Subprozesse aufgerufen — keine Python-Bindings.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
# ema-motor-analysis
