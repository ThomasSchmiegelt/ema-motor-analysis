# E-Maschinen Analyse

Browser-basiertes Werkzeug zur Auslegung und Analyse von Innenläufer-Permanentmagnetmotoren (IPM). Der Nutzer konfiguriert die Motor-Geometrie im Browser (parametrisch oder frei gezeichnet), dann läuft eine automatisierte Kette: FreeCAD-Geometrieerzeugung → 2D-FDM-Elektromagnetfeldberechnung → CalculiX-Strukturmechanik (Fliehkraft) → thermisches Netzwerk → Fahrzyklus-Verlustintegration. Optional ergänzen eine **echte 3D-Magnetfeldberechnung** (Elmer FEM) und ein PDF-Bericht über ein lokales LLM (Ollama) die Auslegung.

> **Bedienung Schritt für Schritt:** siehe [NUTZUNGSANLEITUNG.md](NUTZUNGSANLEITUNG.md).
> **Berechnungsmethodik:** siehe [EM_BERECHNUNG.md](EM_BERECHNUNG.md).
> **Methodenvergleich (vs. Abaqus / Ansys Motor-CAD):** siehe [BERECHNUNGSMETHODEN_VERGLEICH.md](BERECHNUNGSMETHODEN_VERGLEICH.md).

## Bedienoberfläche

Die Oberfläche (`ema.html`) ist ein **Workflow mit Tabs**: ① Projekt · ② Geometrie · ③ Betrieb & Material · ④ Berechnung · ▶ Live-Simulation · 🎨 Designer · 📥 STEP-Import · 🧲 3D-Feld · 💧 Spritzöl-Kühlung · 📊 FEM-Ergebnisse · ⚖ Vergleich. **Tab ① Projekt** ist der zentrale Einstiegspunkt: Projekt anlegen/öffnen, organisatorische Angaben + Notizen, projektspezifische Wissens-Dokumente, PDF-Bericht und gespeicherte 3D-Läufe laufen dort zusammen (es gibt keinen separaten „Bericht"-Tab mehr). Rechts läuft eine **persistente Live-Vorschau** (Motorquerschnitt + Magnetfeld, mit Pause-Knopf), die Trennlinien zwischen Eingaben/Vorschau und über dem Footer sind **ziehbar**, und ein globaler **Analyse-starten-Footer** zeigt den Fortschritt. Weitere Komfortfunktionen:

- **🧠 Text → Auslegung** – Anwendung in Worten beschreiben, das LLM leitet einen vollständigen, validierten Parametersatz ab (`ema_text2ema.py`), optional gestützt auf Referenzmaschinen aus der lokalen Wissensbasis (RAG).
- **🎨 Designer + 🤖 KI entwerfen** – freies Zeichnen einer Rotor-Halbpol-Geometrie (Magnete + Flussbarrieren) auf einer Canvas, oder ein LLM entwirft komplette Maschinen aus einer Beschreibung + Bereichsvorgaben (Statorbohrung, Länge, Welle, Luftspalt) samt automatischer Qualitäts-Vorsortierung und Regenerierung schlechter Entwürfe (`ema_design_ai.py`).
- **🎯 Zielwertoptimierung** – Randbedingungen + freie Parameter mit Bereichen vorgeben; ein LLM steuert eine Suche über einen schnellen Analytik-Evaluator (ohne FreeCAD/FEM), bester zulässiger Treffer → optional Voll-Lauf (`ema_optimize.py`). Für gezeichnete Designer-Entwürfe gibt es eine **Magnet-Feinoptimierung** der Einzelkoordinaten (`ema_design_optimize.py`).
- **📈 Parameterstudie** – variiert einen Parameter über N Schritte bei fester Drehzahl und plottet den Einfluss auf alle Kennwerte (`ema_paramstudy.py`); funktioniert auch auf frei gezeichneten Designer-Geometrien.
- **🧲 3D-Feld (Elmer FEM)** – echte 3D-Magnetfeldberechnung neben dem 2D-FDM-Solver: Endeffekte, Schrägung/Staffelung, Drehzahl-/Lastsweeps, Lastprofil-Video, ROI-Verfeinerung und ein symmetrie-basierter Ein-Pol-Schnellmodus, mit eingebettetem Browser-3D-Viewer (`ema_em3d.py`, siehe unten).
- **💧 Spritzöl-Kühlung (experimentell, Blender/Mantaflow)** – **qualitative** Fluidsimulation von Spritzöl auf einem Wickelkopf-Ausschnitt: Tröpfchenbildung, Benetzung, Abtropfen als Animation + geometrische Benetzungs-Kennwerte (`ema_oilspray.py`). **Wichtig:** kein Temperaturfeld/Wärmeübergang — eine visuelle Studie, keine kalibrierte Kühlrechnung. Braucht einen portablen blender.org-Build (der apt-Build stürzt headless ab).
- **📥 STEP-Import** – fertigen Motor aus einer STEP-Datei importieren; automatische Klassifikation der Bauteile und Magnet-Erkennung (`ema_step_import.py`).
- **📂 Projekt-Browser** – Galerie aller Projekte mit Vorschau + Kennwerten, inkl. Klonen, Bundle-Export/-Import und Status-/Verlaufs-Badges aus der Projektakte.
- **🗂 Projektakte** – jedes Projekt führt eine KI-lesbare Verlaufsakte (`project.json`): Status, Tags, Notizen, Evolutionsstufen mit Eingabe-Diffs, Verknüpfungen zu Vergleichsprojekten, projektspezifische Wissensbasis + Anhänge (`ema_projekt.py`).
- **🎓 LLM-Trainingsdatensatz** – jede Berechnung wird automatisch als SFT-Trainingsbeispiel (Text) + VLM-Manifest (Bilder) abgelegt, inkl. automatischer und manueller gut/schlecht-Bewertung (`ema_training.py`).
- **💬 Ergebnis-Chat** – Fragen zum geladenen Projekt oder zum Variantenvergleich, gestützt auf ein automatisches Maschinen-Datenblatt + RAG-Kontext (`ema_chat.py`).
- **🖼 Einzelbild-Vorschau** – ein Feldbild ohne Volllauf, bis 5000 px (Multigrid-Solver).
- **🤖 Agent / 🪽 Hermes** – zwei Agentenköpfe auf einem lokalen Modell bedienen dieselbe Toolkette im Browser: links Denk-/Antwortstrom, rechts Werkzeugausgaben und Bilder, darunter eine Arbeitsleiste (läuft eine Rechnung? welcher Löser? GPU? Tempo?), dazu Bildschirmaufnahme mit Schnittmarken und ein Archiv aller früheren Läufe (`ema_agent.py`, siehe unten).

---

## Was das Tool macht

### 1. Geometrie-Konfiguration (Browser)

Die Benutzeroberfläche (`ema.html`) erlaubt die vollständige parametrische Beschreibung des Motors — **oder** das freie Zeichnen im Designer-Tab:

- **Stator:** Außen-/Innendurchmesser, Nutzahl, Nuttiefe, Blechpaketlänge
- **Rotor:** Außendurchmesser, Wellendurchmesser, Polpaarzahl, optional Hohlwelle
- **Magnettaschen:** Topologien V, asymmetrisches V, Doppel-V, U, Delta, PMa-SynRM, SPM, Halbach, Speiche, Balken, **oder frei gezeichnet** (Custom/Designer-Pfad) (Breite, Dicke, Öffnungswinkel, Position) — automatisch auf die geometrisch maximale Länge beschnitten. Für die V-Form wahlweise auch **per Durchmesser** (Außen-Ø / Innen-Ø der Tasche + Winkel) definierbar.
- **Magnet-Orientierung:** Polung wahlweise über die lange Magnetseite (quer magnetisiert, Standard) oder um 90° gedreht über die kurze Seite — identisch in Live-Vorschau und FDM-Feldsimulation.
- **Wicklung:** Wicklungsart (Hairpin / Rundleiter), **Leiter pro Nut** (geradzahlig 2…12) und **Spulenweite** (Nutschritte, gesehnt möglich). Die Hairpin-Wickelköpfe werden als kollisionsfreie, **durchgezogen-glatte Zugkörper-Sweeps** im CAD-Modell erzeugt — nahtloser Übergang in die Nutstäbe, und auf der Schweißseite mit dem realen Halb-Spulenweiten-Twist + geradem, achsparallelem Fahnen-Ende; die Leiterzahl je Nut geht auch in Kupfervolumen/Phasenwiderstand des Thermomodells ein.
- **Wellenverbindung:** Presssitz (Querpressverband), Keilwelle oder Polygonprofil (P3G) — Welle und Rotorbohrung passen zueinander, analytisch bewertet (Fugenpressung/Flankenpressung, Drehmomentkapazität, Lösedrehzahl).
- **Bauteil-Stufenbau:** einzelne Komponenten (Welle, Rotor-/Statoreisen, Magnete, Hairpins, Wickelköpfe, Lager, Isolationspapier, Wuchtscheiben-Bolzen, Flussbarrieren q-/d-Achse) unabhängig ein-/ausschaltbar für einen schrittweisen CAD-Aufbau.
- **Kühlung:** Natürliche Konvektion / Zwangsluft / Wassermantel / Öl-Spray
- **Nennpunkt:** Drehzahl, Drehmoment, Phasenstrom (d/q-Komponenten)
- **Projektname, Tags, Notizen** für Archivierung und Nachvollziehbarkeit

### 2. FEM-Geometrieerzeugung (FreeCAD)

`ema_freecad.py` generiert und führt FreeCAD-Python-Skripte headless aus:
- Stator-Ring, Rotorkern, Magnettaschen aller Topologien via booleschen Operationen, Hairpin-Nutstäbe + glatte Wickelkopf-Sweeps, Welle mit gewähltem Verbindungsprofil
- Speicherung als `.FCStd` und STEP-Export
- Renderings (isometrisch, Draufsicht) als PNG für den Bericht

### 3. Elektromagnetische Feldberechnung — 2D (`ema_analysis.py`)

Eigener 2D-FDM-Feldsolver (numpy + scipy), Auflösung im UI wählbar (100–800 px, Einzelbild bis 5000 px):

- Löst `∇(ν∇A) = −J` mit einer **direkten Sparse-Faktorisierung** (`scipy splu`, exakt bei jeder Auflösung, pro Geometrie gecacht); für sehr hohe Auflösung (> 2500 px) ein **CG-beschleunigter AMG-Solver** (`pyamg`). Fällt ohne scipy auf iterative SOR zurück.
- Materialien: Eisen µ_r = 500, NdFeB µ_r = 1.05, Statorwicklung als Volumenstrom
- Permanentmagnete als äquivalente Oberflächenströme modelliert
- Skalierung des FDM-Ergebnisses auf physikalische Tesla-Werte via analytischer Luftspaltfeld-Formel
- Berechnet: B_gap, Flussverkettung, Gegen-EMK, Drehmoment (Ld/Lq-Salienz, MTPA), Ummagnetisierungsverluste, Stromwärmeverluste, Wirkungsgrad

### 4. Elektromagnetische Feldberechnung — echtes 3D-FEM (Elmer) (`ema_em3d.py` / `elmer_runner.py`)

Eigenständiger On-Demand-Pfad neben dem 2D-FDM-Solver (der 2D-Löser bleibt als Vergleichsanker unangetastet), für alles, was 2D nicht kann:

- **Gmsh-OCC-Vernetzung** der vollen 3D-Geometrie (konzentrische Zylinder, Magnete als Lofts, Luftspalt- und Luftkappen), zonale Netzverfeinerung (Luftspalt sehr fein, Magnete/Barrieren/Nuten fein, Rest grob), Ziel-Knoten-Regler und ein **selbstheilender Netzbau-Monitor**, der bei Mesh-Problemen automatisch eine Mitigationsleiter durchspielt
- **Elmer-Magnetostatik** (`WhitneyAVSolver` + Kantenelemente, MUMPS-Direktlöser); echte finite Baulänge → **Endeffekte** und **Schrägung/Staffelung** werden sichtbar; optionale Ankerrückwirkung (Spulenströme über Nut- + Stirnring-Leiter) beim Betriebspunkt
- **Magnettaschen als echte Langlöcher** (Obround) mit einstellbarem 0,1–0,3 mm Klebespalt rundum — auch bei Skew/Staffelung, über eine pro Magnet fusionierte, gestufte Luftkanal-Geometrie
- **Drehzahl-/Lastsweeps** (ein Netz, mehrere Betriebspunkte) inkl. Lastprofil-Video (Sättigungs-Schnittbild + Feldlinien über einen synthetischen Fahrzyklus)
- **ROI-Verfeinerung** (lokal feineres Netz + voller Re-Solve im markierten Bereich) und ein **symmetrie-basierter Ein-Pol-Schnellmodus** (anti-periodisches Submodell, zum vollen Motor gespiegelt) für höhere Auflösung bei kürzerer Rechenzeit
- **Eingebetteter Browser-3D-Viewer** (vtk.js, offline, ohne ParaView nötig): |B|-Oberfläche, Feldlinien, Schnittebene, Standardansichten, Netz-Anzeige, Vollbild — sowie ein Play-Controller für Drehzahl-/Lastrampen
- Ergebnisse (Kennwerte + 2D-vs-3D-Vergleich) fließen automatisch in den PDF-Bericht ein; 3D-Läufe lassen sich projektgebunden speichern und ohne Neurechnen wieder laden

Benötigt Elmer (`elmerfem-csc`) + die Python-Pakete `gmsh`/`vtk` — optional, die gesamte übrige Pipeline läuft ohne.

### 4b. Experimentelle Spritzöl-Kühlung am Wickelkopf (Blender/Mantaflow) (`ema_oilspray.py` / `blender_runner.py`)

Ein eigenständiger On-Demand-Pfad (Tab **💧 Spritzöl-Kühlung**), der **qualitativ** die Fluidkühlung eines Wickelkopf-**Ausschnitts** mit Spritzöl untersucht:

- Ein **Motor-Keilausschnitt** wird aus dem konfigurierten Motor als STL exportiert — optional als **Cutaway mit Welle · Rotor (mit Magneten) · Stator · Wickelköpfen** (Tortenstück über den Winkelbereich der Wickelköpfe) — und als Kollisionsgeometrie an Blenders **Mantaflow-FLIP**-Löser übergeben.
- Ein **Kühlring mit Düsen sitzt am Ende der Wickelköpfe** und spritzt Öl unter **Druck** (bar → Strahlgeschwindigkeit via Bernoulli, 3 bar ≈ 21 m/s) **Richtung Drehachse auf die Leiter**, wo es **zerstäubt und abläuft**; **Secondary-Particles** erzeugen die **Tröpfchenbildung**. Ergebnis: eine gerenderte **Animation** (Video) + eine **Abdeckungs-Heatmap** + Zeitverläufe von **benetzter Fläche** und **Tropfen-/Fragmentzahl**.
- **Ehrliche Einordnung:** Mantaflow ist visuell-plausibel, **nicht validiert** — es gibt **kein Temperaturfeld und keinen Wärmeübergangskoeffizienten**. Die Kennwerte sind rein **geometrische Benetzungs-Proxys** (Indikatoren für Kühl-Hotspots), keine kalibrierte Kühlleistung. Für echte Kühlrechnung wäre Mehrphasen-CFD (OpenFOAM VOF) der nächste Schritt.
- **Einbaulage + Nahaufnahme:** die **horizontale** Darstellung (Motorachse waagerecht = übliche Einbaulage) lässt das Öl seitlich über die Wickelköpfe ablaufen; „vertikal" behält die Ablaufrichtung entlang der Achse. Mit **Nahaufnahme** wird ein **einzelner Strahl** aus **einer** Düse seitlich im Detail gezeigt, wie er **auf einen Leiter** des Wickelkopfs trifft und zerstäubt.
- Der FLIP-**Bake läuft auf der CPU** (die GPU beschleunigt nur das Rendern); Auflösung × Framezahl ist der Kostentreiber, daher der Ausschnitt + moderate Defaults.

Benötigt einen **portablen blender.org-Build** (der `apt`-Build stürzt bei der Fluidsimulation headless ab, siehe Voraussetzungen) + FreeCAD (STL-Export) — optional, die übrige Pipeline läuft ohne.

### 5. Canvas-Designer & KI-gestützte Auslegung (`ema_design_ai.py` / `ema_design_optimize.py`)

Neben der parametrischen Geometrie gibt es einen freien Zeichenpfad:

- **Canvas-Designer:** ein Halbpol wird frei gezeichnet (Magnete per Drag, Flussbarrieren als Polylinien), automatisch d-Achsen-gespiegelt und über alle Pole mit alternierender Polung gemustert.
- **🤖 KI entwerfen:** ein LLM entwirft komplette Maschinen aus einer optionalen Beschreibung + Von-Bis-Bereichen für Statorbohrung, Länge, Wellendurchmesser und Luftspalt — inklusive Material/Polzahl/Nutzahl und einer frei gezeichneten Magnet-/Barrieren-Halbpol-Geometrie. Jeder Entwurf wird sofort FreeCAD-/FEM-frei bewertet (gut/schlecht) und bei Bedarf automatisch mit gezieltem Feedback neu generiert.
- **🎯 Magnete fein-optimieren:** Feinoptimierung der gezeichneten Magnet-Einzelkoordinaten (Position, Länge, Dicke, Winkel) gegen ein wählbares Ziel/Constraint.
- **📈 Parameterstudie für diesen Entwurf:** Parametervariation auf der gezeichneten Geometrie.

Jeder KI-Lauf landet automatisch im LLM-Trainingsdatensatz (Beschreibung → Entwurf → Kennwerte).

### 6. Thermisches Modell (`ema_thermal.py`)

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

### 7. Fahrzyklus-Verlustintegration (`ema_drivecycle.py`)

- Eingebettetes WLTP Klasse 3b-Profil, Autobahn-Vollgas und **Anhänger-Alpenpass**
- Anhänger ist einstellbar: **Anhängermasse (inkl. Nutzlast), Achszahl und maximale Steigung [%]** (Standard 15 %)
- Upload eigener Zyklen als `t[s], v[km/h]`-CSV
- Verlustintegration mit transienter und stationärer Thermik je Zyklus

### 8. Strukturmechanische FEM (CalculiX)

`ema_freecad.py` + `freecad_runner.py` führen eine Fliehkraftanalyse des Rotors durch:
- FreeCAD erzeugt Gmsh-Vernetzung der Rotorgeometrie; die **Netz-Auflösung ist
  einstellbar** (`struct_mesh_mm`, 4/3/2,5/2 mm – kleiner = feiner, löst die
  Spannungsspitzen an den Magnettaschen-Stegen besser auf)
- CalculiX (ccx) löst die statische Spannungsanalyse **einmalig** bei Maximaldrehzahl, mit einer **Robustheits-Leiter** (Mesh-Qualitätsflags + Größen-Retry), die auch bei dünnen Eisenstegen in aggressiven Multi-Layer-Topologien zuverlässig ein auswertbares Ergebnis liefert
- Da Verschiebung und Spannung linear mit der Fliehkraft (∝ Drehzahl²) skalieren,
  werden daraus ohne weitere Solver-Läufe abgeleitet:
  - **hochauflösende Verformungsbilder** (bis 5000 px) bei **Nennlast**,
    **Maximaldrehzahl** und **Berstdrehzahl** (SF→1)
  - ein **Verformungs-Video** (Drehzahl-Rampe 0→max, feste Überhöhung)
- Schlägt die FEM trotz der Robustheits-Leiter fehl, greift ein **analytischer Lamé-Fallback** (rotationssymmetrische Scheibe), damit die Verformung immer dargestellt wird
- Ausgabe: Von-Mises-Spannungen, Verformungen, Sicherheitsfaktor, Berstdrehzahl, Knotenzahl

### 9. Projektverwaltung & Projektakte

- Jede Analyse wird als eigenes Projekt unter `~/cae_projekte/<timestamp>/` gespeichert, mit einer **KI-lesbaren Projektakte** (`project.json`): Status, Tags, Notizen, Evolutionsverlauf mit Eingabe-Diffs, Verknüpfungen zu Vergleichsprojekten, Anhänge und projektspezifische Wissensbasis.
- Projekte lassen sich **klonen** (mit Abstammung) und als `.emaproj`-Bundle exportieren/importieren.
- Bis zu 10 Designvarianten können nebeneinander verglichen werden (Überlagerungsdiagramme, Vergleichstabelle, Vergleichsbericht mit Parameter-/Einfluss-Tabellen)
- Projekt-Browser (Galerie) und Laden abgeschlossener Projekte ohne Neuberechnung

### 10. Wissensbasis (RAG) & LLM-Trainingsdatensatz

- Eine lokale, embeddingbasierte Wissensbasis (Ollama `nomic-embed-text`) existiert **global** (Referenzmaschinen + Dokumentation, speist Text→Auslegung, KI entwerfen und den Chat) **und projektspezifisch** (`ema_rag.py`).
- Jede Berechnung wird automatisch als Trainingsbeispiel für ein SFT-Finetuning (Text) und ein VLM-Finetuning (Bilder) abgelegt, mit automatischer Heuristik-Vorsortierung und manueller gut/schlecht-Bewertung (`ema_training.py`).

### 11. PDF-Berichtsgenerierung (`ema_report.py`)

- LLM (Ollama) generiert deutschen technischen Bericht aus `results.json`
- Markdown-Ausgabe mit `[BILD:<key>]`-Platzhaltern → automatisch durch erzeugte Charts ersetzt
- Konvertierung: `pandoc` + `pdflatex` → `bericht.pdf`
- Agentischer Modus: mehrere Experten-LLM-Agenten schreiben Teilkapitel parallel (`ema_experts.py`)
- Bindet — sofern vorhanden — die 3D-Feldberechnung (Elmer) mit eigenem Abschnitt + 2D-vs-3D-Kennwerttabelle ein

### 12. Agentenbetrieb (`cae_cli.py` / `ema_agent.py`)

Die gesamte Toolkette ist auch **ohne Browser** bedienbar — von der Kommandozeile und von
einem **lokalen** Sprachmodell (Ollama), das über zwei Agentenköpfe (PI, Hermes) dieselbe
Kommandozeile aufruft. Einrichtung und Hintergrund stehen in `../.agents/README.md`.

- **`cae_cli.py`** hat fünfundzwanzig Verben: neun über HTTP auf `:5000`
  (`health/status/geom/projects/results/run/wait/raw/routes`) und sechzehn, die **lokal**
  rechnen — darunter `steckbrief` (was ist dieses Projekt, und was ist daran schon
  gerechnet — **mit Herkunftsangabe je Kennwert**; es rechnet nichts nach: was fehlt, steht
  als fehlend da, nicht als 0), `welle` (Vollwelle oder Hohlwelle, am gemessenen Feld
  entschieden), `paarvergleich`, `screen`, `rotor-check`, `sicherheit`, `feldbild`,
  `struktur`, `topopt`, `zyklus`, `maschinenart`, `aufgabe`, `bilddaten`, `db`, `lernen`,
  `recherche`.
- **`run … --guete entwurf|detail`** setzt Framezahl, Frame-/FDM-Auflösung, Drehzahlschritt
  und die Struktur-Einstellungen in einem Griff — dieselbe Tabelle wie die Knöpfe
  „📐 Entwurf" / „🔬 Detail" im Berechnungs-Tab, jetzt aus **einer** Quelle
  (`ema_text2ema.GUETE`; die JS-Kopie ist per Test dagegen festgenagelt). Vorher standen
  diese Werte in keinem Schema und waren für ein Modell unerreichbar: jeder Versuch lief
  in voller Schärfe, Stunden statt Minuten. Der Entwurf verliert dabei keine Kennzahl —
  `B_gap` und `Kt` kommen aus der analytischen Formel und hängen nicht an der Auflösung —,
  nur Bildschärfe; unter N=300 geht deshalb keine Stufe.
- **Was entschieden wird, bleibt liegen.** `paarvergleich`, `screen`, `rotor-check`,
  `sicherheit`, `welle` und `feldbild` legen ihr Ergebnis bei gebundenem Projekt in
  `<projekt>/rechnungen/<zeit>_<verb>.txt` ab (der auslösende Aufruf steht im Kopf,
  strukturierte Daten daneben als `.json`) und vermerken eine Zeile in `project.json`s
  `evolution`; `--ohne-ablage` schaltet es ab. Bewusst **nicht** in `results.json` — die
  gehört dem Pipelinelauf und würde beim nächsten `run analyse` überschrieben.
- **Im Browser** liegen beide Köpfe als Reiter 🤖 PI und 🪽 Hermes auf **einer** Seite mit
  **einer** Routenmenge (`/agent/…`, unterschieden nur durch `?kopf=`). Dazu gehören eine
  **Arbeitsleiste** (`/agent/arbeit`: laufende Rechnung mit Fortschritt, Recherche, Löser,
  GPU, Modell, Zustand des Agenten samt „still seit …"), ein **Archiv**
  (`/agent/laeufe`, `/agent/lauf` — frühere Läufe beider Köpfe, abgespielt über dieselben
  Zeichenfunktionen wie der lebende Lauf) und eine **Bildschirmaufnahme**, die sich nach
  der Ergebnisspalte richtet und neben dem Video eine `.marken.tsv` plus ein fertiges
  `.schnitt.sh` ablegt.
- **Vom Designer an den Agenten:** eine im Canvas-Designer grob entworfene Geometrie geht
  ohne Pipelinelauf als **Startpunkt** an PI/Hermes (`POST /agent/vorgabe`, Knöpfe im
  Designer-Tab); die Beschreibung aus „Projekt anlegen" erreicht den Agenten ebenfalls,
  statt ein zweites Mal getippt zu werden.

---

## Voraussetzungen

### Pflicht

| Werkzeug | Version | Hinweis |
|---|---|---|
| Python | 3.10+ | Systeminstallation |
| FreeCAD | 1.1.x | aus Quellcode gebaut (siehe unten) |
| CalculiX (ccx) | 2.21+ | im FreeCAD-Pixi-Environment enthalten |
| [pixi](https://pixi.sh) | beliebig | zum Aufruf von FreeCAD mit korrekter Umgebung |

### Optional (nur für PDF-Berichte, Chat, Text→Auslegung, KI-Auslegung, Optimierung)

| Werkzeug | Hinweis |
|---|---|
| [Ollama](https://ollama.com) | lokal laufend auf `localhost:11434` |
| `qwen-gross:latest` | Qwen3.5 27B mit 64 k Kontext im Modelfile — Standardmodell für Bericht/Chat/KI-Auslegung |
| `nomic-embed-text` | `ollama pull nomic-embed-text` — für die Wissensbasis (RAG) |
| pandoc | `sudo apt install pandoc` |
| pdflatex | `sudo apt install texlive-latex-base texlive-fonts-recommended` |

### Optional (nur für die echte 3D-Magnetfeldberechnung)

| Werkzeug | Hinweis |
|---|---|
| Elmer FEM | `sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa && sudo apt install -y elmerfem-csc` |
| `gmsh`, `vtk` | Python-Pakete, in `requirements.txt` enthalten |
| Blender (💧 Spritzöl-Kühlung) | **Portabler blender.org-Build** nötig — der `apt`-Build stürzt bei der Fluidsimulation headless ab. `mkdir -p ~/blender_portable && cd ~/blender_portable && curl -O https://download.blender.org/release/Blender4.2/blender-4.2.9-linux-x64.tar.xz && tar xf blender-4.2.9-linux-x64.tar.xz` (oder Pfad via `$EMA_BLENDER`) |

Die gesamte Analyse-Pipeline (FDM-Feldsolver, Thermik, Fahrzyklus, FEM) läuft vollständig ohne LLM, RAG oder Elmer. Ollama wird nur für die komfortbasierten Zusatzfunktionen aufgerufen — Bericht (`ema_report.py`, `ema_experts.py`), Ergebnis-Chat (`ema_chat.py`), Text→Auslegung (`ema_text2ema.py`), KI-Auslegung/Optimierung (`ema_design_ai.py`, `ema_design_optimize.py`, `ema_optimize.py`) und die Wissensbasis (`ema_rag.py`) — immer mit dem Modell aus `ema_report.DEFAULT_MODEL` (Vorgabe `qwen-gross:latest`, über die Umgebungsvariable `CAE_LLM_MODEL` umstellbar) und der Kontextlänge aus `ema_report.DEFAULT_NUM_CTX` (Vorgabe 65536, `CAE_LLM_NUM_CTX`). `nomic-embed-text` bleibt das Embedding-Modell für RAG. Ohne Ollama bleiben alle physikalischen Berechnungen voll nutzbar. Ohne Elmer läuft alles außer dem Tab „🧲 3D-Feld" normal (die 3D-Modell-Vorschau ohne Feldlösung funktioniert auch ohne Elmer).

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

Alle hardcodierten Pfade befinden sich an **drei Stellen**:

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

### `server.py` (Zeilen 9, 147)
```python
PROJECTS_ROOT = os.path.expanduser("~/cae_projekte")
FREECAD_ROOT  = os.path.expanduser("~/freecad_1.1_quellcode")
```

Projektausgaben landen unter `~/cae_projekte/` (`PROJECTS_ROOT`).

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

## Tests

```bash
python smoke_test.py      # ~15 s, kein FreeCAD nötig: Importe, Topologie, dq/MTPA,
                           # FDM + Sättigung, Verformung, Skripterzeugung, KI-Auslegungspfad
python smoke_test.py --cad  # zusätzlich ein echter FreeCAD-Build + Rotor-FEM (Minuten)
python test_topology.py   # Magnetgeometrie + JS↔Python-Spiegel (magnetLegs), braucht node
python test_em3d.py       # 3D-Elmer-Mesh/SIF/Feldlinien-Export ohne Elmer, End-to-End mit Elmer
python test_steckbrief.py # Steckbrief, Ablage, Laufarchiv, Arbeitsleiste, Wellenbefund
python test_agent.py      # Agentenköpfe: Strom-Zerlegung, Zustand, Aufnahme/Marken
python test_cae_cli.py    # --set gegen ein gestelltes Schema (+ Drift-Test gegen :5000)
```

`smoke_test.py` nach jeder Backend-Änderung ausführen.

---

## Projektstruktur

```
server.py               Flask-Backend — REST-API + statisches Datei-Serving
ema.html                Browser-UI (Vanilla JS, kein Build-Schritt nötig)
ema_pipeline.py         Pipeline-Orchestrierung (Geometrie → EM → Thermik → FEM)
ema_freecad.py          FreeCAD-Skriptgenerierung (Rotor, Stator, Hairpins, FEM)
ema_analysis.py         2D-FDM-Elektromagnet-Feldsolver (numpy)
ema_thermal.py          Stationäres LPTN-Wärmemodell (6 Knoten)
ema_topology.py         Magnet-Platzierung (einzige Quelle, gespiegelt im JS von ema.html)
ema_drivecycle.py       Fahrzyklen (WLTP-3b, Vollgas, Anhänger einstellbar, CSV)
ema_compare.py          Variantenvergleich (bis zu 10 Projekte, Overlay-Charts)
ema_report.py           LLM → Markdown → pandoc → PDF-Bericht (+ Vergleichsbericht)
ema_experts.py          Agentischer Modus: mehrere LLM-Experten-Agenten
ema_chat.py             Ergebnis-/Vergleichs-Chat (Ollama)
ema_optimize.py         Zielwertoptimierung (LLM-gesteuert, schneller Analytik-Evaluator)
ema_paramstudy.py       Parameterstudie bei fester Drehzahl (parametrisch + Designer-Entwürfe)
ema_text2ema.py         Text → validierter Parametersatz (Ollama, RAG-gestützt)
ema_design_ai.py        KI-gestützte Komplettauslegung (Designer-Pfad, RAG-gestützt)
ema_design_optimize.py  Per-Magnet-Feinoptimierung eines gezeichneten Entwurfs
ema_step_import.py      STEP-Import eines fertigen Motors (Klassifikation + Magnet-Erkennung)
ema_em3d.py             Echte 3D-Magnetfeldberechnung (Elmer FEM): Mesh, SIF, Sweeps, Sektor/ROI
elmer_runner.py         Elmer-Subprozess-Wrapper (ElmerGrid/ElmerSolver)
ema_projekt.py          Projektakte (project.json) — Status/Verlauf/Verknüpfungen/RAG/Anhänge
ema_rag.py              Lokale Wissensbasis (RAG), global + pro Projekt
ema_training.py         Fortlaufendes LLM-Trainingsfile (SFT + VLM)
freecad_runner.py       FreeCAD-Subprocess-Wrapper (headless, Output-Parsing)
em3d_perf_check.py      Performance-/RAM-Kalibrierung der 3D-Elmer-Vernetzung (Standalone-CLI)
cae_cli.py              Agent-/Skript-Kommandozeile (25 Verben, 16 davon lokal)
ema_agent.py            Beide Agentenköpfe im Browser (Routen /agent…), Aufnahme, Laufarchiv
ema_agent.html          Die Agentenseite (eine Seite für PI und Hermes, ?kopf=)
ema_steckbrief.py       Projekt-Steckbrief + Ablage der Verbergebnisse (rechnungen/)
ema_arbeit.py           Messwerte der Arbeitsleiste (Rechnung/Recherche/Löser/GPU/Modell)
ema_welle.py            Vollwelle oder Hohlwelle, am Feld entschieden
ema_feldbild.py         Feldlinienbilder (durchsichtig, Schnitt, ein Pol, Längsschnitt)
start.sh                Startskript mit Prerequisite-Prüfung
install.sh              Einmalige Installation und Konfigurationsprüfung
requirements.txt        Python-Abhängigkeiten
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
| `gmsh` | 3D-Vernetzung für die echte Elmer-Feldberechnung; optional |
| `vtk` | Lesen/Schreiben der 3D-Feldergebnisse (VTU/VTP), Browser-Viewer-Export; optional |
| `pypdf` | PDF-Extraktion für die Wissensbasis (RAG); optional |

Alle Versionen: `requirements.txt`. Die Ollama-REST-API wird direkt über `urllib.request` aus der Python-Standardbibliothek aufgerufen. Externe Solver (FreeCAD, CalculiX, Elmer, pandoc, pdflatex) werden als Subprozesse aufgerufen — keine Python-Bindings.

---

## Lizenz

MIT — siehe [LICENSE](LICENSE).
