# E-Maschinen Analyse

Browser-basiertes Werkzeug zur Auslegung und Analyse von Innenläufer-Permanentmagnetmotoren (IPM). Der Nutzer konfiguriert die Motor-Geometrie im Browser, dann läuft eine automatisierte Kette: FreeCAD-Geometrieerzeugung → 2D-FDM-Elektromagnetfeldberechnung → CalculiX-Strukturmechanik (Fliehkraft). Optional kann ein PDF-Bericht über ein lokales LLM (Ollama) erzeugt werden.

---

## Was das Tool macht

### 1. Geometrie-Konfiguration (Browser)

Die Benutzeroberfläche (`ema.html`) erlaubt die vollständige parametrische Beschreibung des Motors:

- **Stator:** Außen-/Innendurchmesser, Nutzahl, Nuttiefe, Blechpaketlänge
- **Rotor:** Außendurchmesser, Wellendurchmesser, Polpaarzahl
- **Magnettaschen:** V-förmige Magnet-Einbettung (Breite, Dicke, Öffnungswinkel) — automatisch auf die geometrisch maximale Länge beschnitten
- **Wicklung:** Wicklungsart (Hairpin / Rundleiter), Drähte pro Nut, Füllfaktor, Windungszahl
- **Kühlung:** Natürliche Konvektion / Zwangsluft / Wassermantel / Öl-Spray
- **Nennpunkt:** Drehzahl, Drehmoment, Phasenstrom (d/q-Komponenten)
- **Projektname** für Archivierung

### 2. FEM-Geometrieerzeugung (FreeCAD)

`ema_freecad.py` generiert und führt FreeCAD-Python-Skripte headless aus:
- Stator-Ring, Rotorkern, V-förmige Magnettaschen via booleschen Operationen
- Speicherung als `.FCStd` und STEP-Export
- Renderings (isometrisch, Draufsicht) als PNG für den Bericht

### 3. Elektromagnetische Feldberechnung (`ema_analysis.py`)

Eigener 2D-FDM-Feldsolver auf Basis von numpy (150 × 150 Gitter):

- Löst `∇(ν∇A) = −J` mit SOR-Iteration auf dem Querschnitt des Motors
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

Kühltypen mit kalibrierten h_eff-Werten: Natürliche Konvektion, Zwangsluft, Wassermantel (h=800 W/m²K), Öl-Spray (h=2500 W/m²K).

### 5. Fahrzyklus-Verlustintegration (`ema_drivecycle.py`)

- Eingebettetes WLTP Klasse 3b-Profil (1800 s, approximiertes Geschwindigkeitsprofil mit korrekten Phasendauern, Peak- und Durchschnittsgeschwindigkeiten)
- Upload eigener Zyklen als `t[s], v[km/h]`-CSV
- Gewichtete Verlustintegration über den Betriebspunktraum

### 6. Strukturmechanische FEM (CalculiX)

`ema_freecad.py` + `freecad_runner.py` führen eine Fliehkraftanalyse des Rotors durch:
- FreeCAD erzeugt Gmsh-Vernetzung der Rotorgeometrie
- CalculiX (ccx) löst die statische Spannungsanalyse
- Ausgabe: Von-Mises-Spannungen, Verformungen, Knotenzahl

### 7. Projektverwaltung

- Jede Analyse wird als eigenes Projekt unter `~/cae_projekte/<timestamp>/` gespeichert
- Bis zu 4 Designvarianten können nebeneinander verglichen werden (Überlagerungsdiagramme)
- Laden abgeschlossener Projekte ohne Neuberechnung

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

Die gesamte Analyse-Pipeline (FDM-Feldsolver, Thermik, Fahrzyklus, FEM) läuft vollständig ohne LLM. Ollama wird ausschließlich zur Berichtsgenerierung (`ema_report.py`, `ema_experts.py`) aufgerufen — immer mit dem Modell `ministral-3:14b`, das im Code fest eingestellt ist.

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
ema_drivecycle.py  Fahrzyklus-Verlustintegration (WLTP-3b + CSV)
ema_compare.py     Variantenvergleich (bis zu 4 Projekte, Overlay-Charts)
ema_report.py      LLM → Markdown → pandoc → PDF-Bericht
ema_experts.py     Agentischer Modus: mehrere LLM-Experten-Agenten
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
| `matplotlib` | Charts, Feldanimation (Agg-Backend, kein Display nötig) |

Alle Versionen: `requirements.txt`. Die Ollama-REST-API wird direkt über `urllib.request` aus der Python-Standardbibliothek aufgerufen. Externe Solver (FreeCAD, CalculiX, pandoc, pdflatex) werden als Subprozesse aufgerufen — keine Python-Bindings.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
# ema-motor-analysis
