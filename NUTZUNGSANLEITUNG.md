# E-Maschinen Designer – Bedienungsanleitung

Browser-Werkzeug zur Auslegung und Analyse von Innenläufer-Permanentmagnet­motoren
(IPM). Du konfigurierst die Motorgeometrie im Browser, eine vollautomatische Kette
rechnet dann **FreeCAD-Geometrie → 2D-FDM-Magnetfeld → CalculiX-Festigkeit
(Fliehkraft) → Thermik → Fahrzyklus**. Optional erzeugt ein lokales LLM (Ollama) einen
PDF-Bericht. Es ist **kein LLM in der Analyse** – das ist reine Physik/Numerik; das
LLM hilft nur bei Bericht, Chat, Text→Auslegung und der Optimierungs­steuerung.

> Technische Details zu Installation/Voraussetzungen: siehe **README.md**.
> Berechnungsmethodik: siehe **EM_BERECHNUNG.md**.

---

## 1. Starten

```bash
cd ~/ai-project/cae_orchestrator
./start.sh
```

Der Server läuft danach unter **http://localhost:5000** und der Browser öffnet sich
automatisch. `start.sh` prüft FreeCAD, CalculiX und (optional) Ollama und richtet die
Python-Umgebung beim ersten Mal ein.

---

## 2. Die Oberfläche im Überblick

Oben eine **Tab-Leiste** (Arbeitsschritte), darunter links der Eingabe-/Ergebnis­bereich
und rechts eine **persistente Live-Vorschau** (Motorquerschnitt + Magnetfeld). Ganz
unten ein **Footer** mit dem globalen Button **„⚙ Analyse starten"** und der
Fortschrittsanzeige.

| Element | Funktion |
|---|---|
| **Tabs** | ① Geometrie · ② Betrieb & Material · ③ Berechnung · ▶ Live-Simulation · 📊 FEM-Ergebnisse · 📄 Bericht · ⚖ Vergleich |
| **Vorschau-Spalte** (rechts) | dreht den Motor live und zeigt das Feld; sichtbar auf den Eingabe-Tabs, ausgeblendet bei Ergebnissen/Bericht/Vergleich |
| **⏸ Pause** (in der Vorschau) | stoppt/startet die Rotor-Drehung – von jedem Eingabe-Tab aus erreichbar |
| **Vertikaler Splitter** | Trennlinie zwischen Eingaben und Vorschau ziehen → Vorschaubreite ändern (Canvas skaliert live mit) |
| **Horizontaler Splitter** | Trennlinie über dem Footer hochziehen → Footer vergrößern, zeigt das vollständige Analyse-Log |
| **💬 Chat** (unten rechts) | Fragen zu den Ergebnissen bzw. zum Vergleich stellen |

Tabs sind auch per URL-Anker direkt erreichbar, z. B. `…:5000/#vergleich`,
`#optimize`, `#projects`, `#text2ema`.

---

## 3. Schritt-für-Schritt-Workflow

### Tab ① Geometrie

- **Hauptabmessungen:** Stator Außen-/Innen-Ø, Rotor-Ø, Wellen-Ø, Wellen-Bohrung
  (0 = Vollwelle), Blechpaketlänge.
- **Stator/Wicklung:** Nutzahl, Nuttiefe, **Leiter pro Nut** (Hairpin, geradzahlig
  2…12) und **Spulenweite** (in Nutschritten, 0 = automatisch ≈ Nuten/Pole, kleinere
  Werte = gesehnte Wicklung). Die Leiterzahl je Nut fließt in das CAD-Modell der
  Wickelköpfe **und** in das Kupfervolumen/den Phasenwiderstand des Thermomodells ein.
- **Magnet-Topologie:** Polpaare, Magnet­anordnung (V, Doppel-V, U, Delta, PMa-SynRM,
  SPM, Halbach, Speiche, Balken), Öffnungswinkel, Position, Magnet­länge/-dicke, Steg,
  axiale/umfängliche Segmentierung.
  - **Magnet-Orientierung (Polung):** „Lange Seite N/S" (quer magnetisiert, Standard)
    *oder* „Kurze Seite N/S" (um 90° gedreht, längs magnetisiert). Wirkt identisch in
    der Live-Vorschau und in der FDM-Feldsimulation.
  - **V-Form – Taschen­definition umschaltbar:** „Position (Radius) + Länge" *oder*
    **„Durchmesser (Außen-Ø / Innen-Ø) + Winkel"**. Im Durchmesser-Modus gibst du den
    Außen- und Innendurchmesser der Tasche an; die Magnetlänge ergibt sich daraus.
- **Werkstoffe:** Rotor-/Statorblech, Hairpin-Leiter, Magnettyp.
- **↺ Vorschau aktualisieren:** rechnet das Live-Querschnittsbild neu.
- **🧠 Aus Beschreibung ableiten (Text → Auslegung):** siehe Abschnitt 4.
- **＋ Geometrie merken:** legt die aktuelle Konfiguration als Variante (bis 10) für
  den Vergleich ab.

### Tab ② Betrieb & Material

- **Lastmoment (S1-Auslegungspunkt)** und **Feldschwächung** – beeinflussen die
  Feldanimation und die stationäre Einzel-Thermik (nicht die Fahrzyklus-Thermik – dort
  kommt die Last aus dem Zyklus).
- **Thermisches Modell:** Kühlungsart (natürlich / Zwangsluft / Wassermantel / Öl),
  Umgebungstemperatur.
- **Fahrzyklus:** WLTP-3b, Autobahn-Vollgas, **Anhänger-Alpenpass**, alle drei, eigene
  CSV oder aus.
  - **Anhänger-Einstellungen:** Anhänger-Masse (inkl. Nutzlast), Achszahl und
    **maximale Steigung [%]** der Bergauffahrt sind frei einstellbar (Standard 15 %).
  - **Fahrzeugparameter:** Masse, c_w·A, Rollwiderstand, Raddurchmesser, Übersetzung,
    Wirkungsgrad, Regen-Anteil.
- **Projekt-Name** (optional) und **Vorhandene Projekte laden** (Dropdown) +
  **📂 Projekt-Browser** (Galerie, siehe Abschnitt 4).

### Tab ③ Berechnung

- **Drehzahlbereich** (von / bis / Schrittweite) – die Festigkeits-FEM läuft bei
  „RPM bis" (Worst-Case-Fliehkraft).
- **Frames pro Drehzahl** und **Feld-Darstellungs­modi** (Rotor-Rotation immer aktiv;
  zusätzlich Ankerrückwirkung und/oder Last-Rampe).
- **FDM-Auflösung** (statisches Feld) und **Frame-Auflösung** (Animation). Höhere Werte
  lösen Luftspalt und Zähne feiner auf, brauchen aber länger.
- **Strukturanalyse (Festigkeit):** **Netz-Auflösung** (4/3/2,5/2 mm – kleiner = feiner,
  löst die Stegspannungen besser auf), **Einzelbild-Auflösung** (bis 5000 px) sowie
  **Verformungs-Video** (Drehzahl-Rampe 0→max) mit wählbarer Frame-Zahl. CalculiX rechnet
  einmalig bei Maximaldrehzahl; Verformung/Spannung bei anderen Drehzahlen werden über
  die Drehzahl²-Skalierung abgeleitet. Im Ergebnis-Tab **Verformung** gibt es Einzelbilder
  bei **Nennlast / Maximaldrehzahl / Berstdrehzahl** und das Video.
- **⏱ Geschätzte Laufzeit** wird live mitgerechnet.
- **🖼 Nur ein Frame rechnen:** Einzelbild ohne Volllauf, Auflösung bis **5000 px**
  (ab 3000 px Multigrid-Solver, mehrere Minuten).
- **🎯 Zielwertoptimierung öffnen:** siehe Abschnitt 4.

### ⚙ Analyse starten (Footer)

Der grüne Footer-Button startet die komplette Pipeline. Der Fortschritt läuft im
Footer (Balken + Log – Footer hochziehen für mehr Zeilen). Nach Abschluss springt die
Ansicht automatisch auf **FEM-Ergebnisse**.

### Tab ▶ Live-Simulation

Echtzeit-Daten (Drehzahl, Moment, Strom, Leistung) und Steuerung der Live-Animation
(Play/Pause, Reset, Ultra-Slow, Geschwindigkeit, Gitter, Feldlinien-Dichte). Dient der
schnellen visuellen Kontrolle der Geometrie – ersetzt nicht die Vollberechnung.

### Tab 📊 FEM-Ergebnisse

Nach einem Lauf hier verfügbar (vorher ausgegraut). Unter-Reiter: **EM-Feld** (Animation
mit Drehzahl-/Modus-Auswahl, Colorbar in Tesla + Legende), **CAD-Modell**, **Luftspalt**,
**EM-Kennlinie**, **Festigkeit**, **Verformung**, **Temperatur** (inkl. Verluste &
Zeitkonstanten) und die **Fahrzyklen** (WLTP / Autobahn / Anhänger, je mit Energiebilanz
und thermischer Bewertung). Buttons **🔧 FreeCAD** (Modell öffnen) und **📦 STEP**
(Export) erscheinen nach dem Lauf.

### Tab 📄 Bericht

Erzeugt einen deutschen PDF-Bericht aus dem aktuellen Projekt (lokales LLM
`ministral-3:14b`). **Standard** oder **Agentisch** (mehrere Experten-Teilkapitel). Erst
nach einer abgeschlossenen Analyse verfügbar. Benötigt Ollama + `pandoc` + `pdflatex`.

### Tab ⚖ Vergleich

- **Varianten** zusammenstellen (über „Geometrie merken" oder „Aktuelle Konfig"),
  als `*.emavars.json` exportieren/importieren, auf dem Server speichern und als Batch
  mit **„Alle ausführen"** rechnen.
- **Projekte** (bis 10) auswählen → **Vergleich starten**: überlagerte Kennlinien,
  gruppierte Thermik/Energie-Balken und eine **Vergleichstabelle**.
- **📄 Vergleichsbericht:** PDF mit echten **Parameter-Tabellen** (abweichende Werte
  markiert), **Kennwert-Tabelle** und einer **Einfluss-Analyse** (welche Parameter­
  änderung welche Kennwert­änderung in % bewirkt) plus LLM-Interpretation und Ranking.

---

## 4. Spezialfunktionen

### 🧠 Text → Auslegung (Tab Geometrie)

Beschreibe die Anwendung in eigenen Worten (Leistung, Drehzahl, Drehmoment, Bauraum,
Kühlung, Effizienz/Kosten). Das LLM leitet einen vollständigen, in sich stimmigen
Parametersatz ab; die Werte werden serverseitig auf gültige Bereiche geklemmt und die
radiale Konsistenz erzwungen (statorOD > statorID > rotorOD > Welle, ~0,7 mm Luftspalt,
Nuten ≈ 6·p). Es werden Begründung + Parameter angezeigt → **„In Formular übernehmen"**.
Danach kannst du alles feinjustieren und rechnen.

### 🎯 Zielwertoptimierung (Tab Berechnung)

LLM-gesteuerte Suche nach einem guten Design:
1. **Ziel** wählen (Kennwert maximieren / minimieren / Zielwert), z. B. „Maxwell-Moment
   maximieren" oder „Masse minimieren".
2. **Randbedingungen** festlegen, die gelten müssen (z. B. `T_Magnet ≤ 130`,
   `max. sichere Drehzahl ≥ 18000`).
3. **Freie Parameter** ankreuzen und ihren **Bereich (von–bis)** angeben (Magnetlänge,
   -dicke, -winkel, Position, Steg, Nuttiefe, Polpaare, Blechlänge).
4. **Budget** (Anzahl Auswertungen) setzen, **starten**.

Jeder Kandidat wird mit einem **schnellen Analytik-Evaluator ohne FreeCAD/FEM** (~0,5 s)
bewertet; das LLM schlägt anhand der Historie neue Kandidaten vor, Zulässigkeit und
Bewertung rechnet das Programm deterministisch. Am Ende: bester **zulässiger** Treffer →
**„Parameter übernehmen"** (ins Formular) oder **„Übernehmen & Voll-Analyse"** (sofort
kompletter Lauf inkl. FEM auf dem Gewinner).

### 📂 Projekt-Browser (Tab Betrieb & Material)

Galerie aller Projekte unter `~/cae_projekte/` mit Querschnitts-Vorschau, Topologie,
Abmessungen und Kennwerten (Kt, Moment, max. Drehzahl, T_Magnet, Verluste, Verbrauch).
Suchfeld + „nur mit Ergebnissen"-Filter. **„Ergebnisse ansehen"** lädt das Projekt
(ohne Neuberechnung) und springt auf den Ergebnis-Tab; Papierkorb löscht es.
**„📋 Als Vorlage verwenden"** übernimmt *alle* Eingabeparameter des Projekts ins
Formular (Geometrie, Materialien, Drehzahlen, Struktur-/Feld-Einstellungen, Fahrzeug/
Anhänger) und springt auf den Geometrie-Tab — dort anpassen und neu rechnen. Bei
älteren Projekten (ohne gespeicherten Eingabe-Satz) werden Geometrie + Kernparameter
aus den Metadaten rekonstruiert, der Rest bleibt auf den aktuellen Formularwerten.

### 💬 Ergebnis-Chat (Button unten rechts)

Stellt Fragen zum **aktuell geladenen Projekt** oder – wenn der Vergleich-Tab aktiv ist
und ≥ 2 Projekte angehakt sind – zum **Vergleich**. Antworten stützen sich auf die echten
Ergebniszahlen. Benötigt Ollama.

---

## 5. Typische Laufzeiten

| Schritt | Größenordnung |
|---|---|
| Geometrie (FreeCAD) + STEP | ~10–40 s |
| EM-Feld + Animation | je nach Auflösung/Frames ~10 s – einige Minuten |
| Festigkeits-FEM (CalculiX) | ~30–120 s |
| Thermik + Fahrzyklen | wenige Sekunden |
| Einzelbild 5000 px (Multigrid) | mehrere Minuten |
| Zielwertoptimierung (Budget 24) | ~1–2 Minuten |
| PDF-Bericht (LLM) | ~30 s – 2 Minuten |

---

## 6. Fehlersuche

| Problem | Lösung |
|---|---|
| **„FreeCADCmd nicht gefunden"** | Pfade in `start.sh`, `freecad_runner.py` und `server.py` prüfen (siehe README, Abschnitt „Pfade anpassen"). Es muss der **1.1.x-Quellcode-Build** sein, nicht `/opt/freecad-1.1`. |
| **Bericht / Chat / Text→Auslegung / Optimierung reagiert nicht** | Ollama läuft nicht. `ollama serve` starten; Modell prüfen: `ollama list` (benötigt `ministral-3:14b`). |
| **PDF-Bericht schlägt fehl** | `pandoc` und `pdflatex` installieren (siehe README). |
| **Magnete „fehlen" im Querschnitt** | Bei Oberflächen-Topologien (SPM/Halbach) gibt es keine Taschen – das ist korrekt. Bei Innenpol-Topologien sind die Magnete vorhanden (Feldstruktur an den Rändern). |
| **Magnete laufen sehr heiß / sehr kalt** | Kühlung, Last und Drehzahl prüfen. Die Magnete sind thermisch an die Statorbohrung gekoppelt (Wärmeeintrag aus den Wicklungen). |
| **Einzelbild 5000 px abgelehnt** | `pyamg` fehlt → ohne es ist die Vorschau auf 2500 px gedeckelt. `pip install -r requirements.txt` (im venv) nachziehen. |
| **5000-px-Bild dauert / braucht RAM** | Normal: Multigrid-Solver, mehrere Minuten, ~15 GB Spitzen-RAM. |

---

## 7. Wo liegen meine Ergebnisse?

Jeder Lauf erzeugt `~/cae_projekte/<Zeitstempel[_Name]>/` mit `motor.FCStd`,
`motor.step`, `results.json`, `meta.json` sowie den Unterordnern `cad_images/`,
`charts/` und `frames/`. Vergleichsberichte landen unter `~/cae_projekte/_comparisons/`,
gespeicherte Variantensätze unter `~/cae_projekte/_variants/`.
