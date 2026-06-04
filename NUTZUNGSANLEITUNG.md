# CAE Orchestrator – Nutzungsanleitung

Automatische CAD-FEM-Pipeline mit KI-Agenten und menschlicher Freigabe an jedem Schritt.

---

## Voraussetzungen

| Komponente | Pfad / URL |
|---|---|
| FreeCAD 1.2 (headless) | `/opt/freecad-1.1/build/release/bin/FreeCADCmd` |
| CalculiX FEM-Solver | `/opt/freecad-1.1/.pixi/envs/default/bin/ccx` |
| Ollama | `http://localhost:11434` |
| Modell (Reasoning) | `qwen3.6-16k:latest` |
| Modell (Code) | `qwen2.5-coder:14b` |

Ollama muss laufen, bevor die App gestartet wird:
```bash
ollama serve
```

---

## Start

```bash
cd ~/ai-project/cae_orchestrator
./start.sh
```

Die App ist dann unter **http://localhost:8502** erreichbar.

Das Skript prüft automatisch, ob FreeCAD, CalculiX und Ollama verfügbar sind, und richtet die Python-Umgebung beim ersten Start ein.

---

## Bedienung

### 1. Eingaben (linke Sidebar)

| Feld | Beschreibung | Beispiel |
|---|---|---|
| **Bauteilbeschreibung** | Was soll gebaut werden? | `Kragarm 200mm lang, 20mm breit, 10mm hoch` |
| **Belastung** | Wie und wo wirkt die Kraft? | `1000 N nach unten am freien Ende` |
| **Lagerung** | Wo ist das Bauteil eingespannt? | `Linkes Ende fest eingespannt` |
| **Material** | Werkstoff aus der Liste wählen | `Stahl S235` |

Dann auf **"Analyse starten"** klicken.

### 2. Pipeline-Schritte (jeder Schritt benötigt Freigabe)

```
[1] Konstruktionsplan    →  [Freigeben]
        ↓
[2] CAD-Geometrie        →  [Freigeben]  oder  [Neu generieren]
        ↓
[3] FEM-Analyse          →  [Freigeben]
        ↓
[4] Ergebnisse           →  Fertig
```

**Schritt 1 – Konstruktionsplan:**  
Der Planungs-Agent erstellt einen nummerierten Konstruktionsplan aus der Beschreibung. Prüfen und mit "Freigeben" bestätigen.

**Schritt 2 – CAD-Geometrie:**  
Der Code-Agent generiert FreeCAD Python-Code und führt ihn headless aus. Bei Erfolg werden Flächenanzahl und Volumen angezeigt. Falls die Geometrie nicht stimmt, "Neu generieren" klicken (neuer LLM-Versuch).

**Schritt 3 – FEM-Analyse:**  
Der FEM-Agent bestimmt Randbedingungen (Einspannung, Kraftfläche, Vernetzung) und startet CalculiX. Zeigt Knotenanzahl und Löserstatus an.

**Schritt 4 – Ergebnisse:**  
Post-Processing-Agent bewertet die Ergebnisse. Angezeigt werden:
- Maximale von-Mises-Spannung [MPa]
- Maximale Verschiebung [mm]
- Sicherheitsfaktor (Streckgrenze / σ_max)
- Bewertung: **OK** / **WARNUNG** / **KRITISCH**

---

## Beispielanfragen

**Kragarm (klassisch):**
- Bauteil: `Rechteckiger Kragarm, 200mm lang, 20mm breit, 10mm hoch`
- Belastung: `1000 N vertikal nach unten am freien Ende`
- Lagerung: `Linkes Ende vollständig eingespannt`
- Material: `Stahl S235`

**Halterung:**
- Bauteil: `L-förmige Halterung, horizontaler Arm 150mm, vertikaler Flansch 80mm, Querschnitt 15x15mm`
- Belastung: `500 N nach unten auf dem horizontalen Arm`
- Lagerung: `Vertikaler Flansch an der Wand verschraubt`
- Material: `Aluminium 6061-T6`

**Zugprobe:**
- Bauteil: `Zugstab, 100mm lang, 10mm Durchmesser, zylindrisch`
- Belastung: `5000 N Zugkraft in axialer Richtung`
- Lagerung: `Ein Ende fest eingespannt`
- Material: `Stahl S235`

---

## Bekannte Einschränkungen

**Kraftaufbringung:**  
Die Kraft wirkt verteilt über die gewählte Fläche (kein Punktlast). Der KI-Agent wählt eine Fläche, deren Normale zur gewünschten Kraftrichtung passt. Das ist eine Vereinfachung.

**Netzqualität:**  
Das FEM-Netz ist 1. Ordnung mit 5 mm Elementgröße (grob). Spannungsspitzen werden typischerweise um ~50 % unterschätzt gegenüber analytischen Werten. Für Designentscheidungen ausreichend, nicht für Zertifizierungen.

**Geometriekomplexität:**  
Der Code-Agent kommt gut mit Grundkörpern (Quader, Zylinder, Bohrungen, L-Profile) zurecht. Komplexe Freiformflächen, Gewinde oder Baugruppen sind nicht zuverlässig.

**Laufzeit:**  
- Planungsschritt: ~10–20 Sekunden
- CAD-Generierung: ~30–90 Sekunden (Modellgröße abhängig)
- FEM-Vernetzung + Lösung: ~30–120 Sekunden (Bauteilgröße abhängig)

---

## Dateistruktur

```
cae_orchestrator/
├── app.py                  # Streamlit-Hauptanwendung
├── agents.py               # KI-Agenten (Plan, CAD, FEM, Post-Processing)
├── freecad_runner.py       # FreeCAD headless Ausführung + FEM-Skript-Builder
├── requirements.txt        # Python-Abhängigkeiten
├── start.sh                # Startskript mit Voraussetzungsprüfung
└── workspace/              # Generierte Dateien (FreeCAD-Dokumente, CCX-Ergebnisse)
```

---

## Fehlersuche

**"Ollama antwortet nicht"**  
→ `ollama serve` in einem Terminal starten. Prüfen ob Modelle geladen sind: `ollama list`

**"FreeCADCmd nicht gefunden"**  
→ Pfad in `freecad_runner.py` und `start.sh` anpassen (Konstante `FREECAD_CMD`)

**CAD schlägt fehl / "shape ungültig"**  
→ "Neu generieren" klicken. Bei wiederholtem Fehler: Beschreibung präziser formulieren und einfachere Geometrie beschreiben.

**FEM-Fehler "MESH_ERROR"**  
→ Die Geometrie hat möglicherweise sehr kleine Flächen oder degenerierte Kanten. Mesh-Größe in `agents.py` (Standardwert im FEM-Agent-Prompt) erhöhen oder Geometrie vereinfachen.

**Ergebnisse physikalisch unrealistisch**  
→ Prüfen ob Belastungsrichtung und Einspannung korrekt beschrieben sind. Hinweis: Kräfte werden als verteilte Last auf einer Fläche aufgebracht, nicht als Punktlast.
