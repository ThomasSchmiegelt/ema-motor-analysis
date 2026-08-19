# E-Maschinen Designer – Vollständige Bedienungsanleitung

Browser-Werkzeug zur Auslegung und Analyse von Innenläufer-Permanentmagnet­motoren
(IPM). Du konfigurierst die Motor-Geometrie im Browser, eine vollautomatische Kette
rechnet dann **FreeCAD-Geometrie → 2D-FDM-Magnetfeld → CalculiX-Festigkeit
(Fliehkraft) → Thermik → Fahrzyklus**. Optional erzeugt ein lokales LLM (Ollama)
einen PDF-Bericht. Es ist **kein LLM in der Analyse** — das ist reine Physik/Numerik;
das LLM hilft nur bei Bericht, Chat, Text→Auslegung und der Optimierungs­steuerung.

Zusätzlich kannst du **fertige Motoren aus einer STEP-Datei importieren** (automatische
Magnet-Erkennung → Tab „📥 STEP-Import") und eine **echte 3D-Magnetfeldberechnung** mit
Elmer FEM durchführen (Endeffekte, Schrägung, 3D-Visualisierung → Tab „🧲 3D-Feld").

> Technische Details zu Installation/Voraussetzungen: siehe **README.md**.
> Berechnungsmethodik: siehe **EM_BERECHNUNG.md**.
> Methodenvergleich (vs. Abaqus / Ansys Motor-CAD): siehe **BERECHNUNGSMETHODEN_VERGLEICH.md**.

---

## 1. Starten

```bash
cd ~/ai-workspace/cae_orchestrator
./start.sh
```

Der Server läuft danach unter **http://localhost:5000** und der Browser öffnet sich
automatisch. `start.sh` prüft FreeCAD, CalculiX und (optional) Ollama **und Elmer**
(für das 3D-Feld) und richtet die Python-Umgebung beim ersten Mal ein. Fehlende
optionale Programme werden nur als Hinweis gemeldet — der Server startet trotzdem.

Alternativer Handstart (nach einmaliger Installation):
```bash
source venv/bin/activate
python server.py
```

---

## 2. Die Oberfläche im Überblick

Oben eine **Tab-Leiste** (Arbeitsschritte), darunter links der Eingabe-/Ergebnis­bereich
und rechts eine **persistente Live-Vorschau** (Motorquerschnitt + Magnetfeld). Ganz
unten ein **Footer** mit drei Workflow-Buttons und der Fortschrittsanzeige.

### Elemente

| Element | Funktion |
|---|---|
| **Tabs** | ① Projekt · ② Geometrie · ③ Betrieb & Material · ④ Berechnung · ▶ Live-Simulation · 🎨 Designer · 📥 STEP-Import · 🧲 3D-Feld · 💧 Spritzöl-Kühlung · 📊 FEM-Ergebnisse · ⚖ Vergleich |
| **Vorschau-Spalte** (rechts) | dreht den Motor live und zeigt das Feld; sichtbar auf den Eingabe-Tabs, ausgeblendet bei Projekt/Ergebnissen/Vergleich |
| **⏸ Pause** (in der Vorschau) | stoppt/startet die Rotor-Drehung — von jedem Eingabe-Tab aus erreichbar |
| **Vertikaler Splitter** | Trennlinie zwischen Eingaben und Vorschau ziehen → Vorschaubreite ändern (Canvas skaliert live mit) |
| **Horizontaler Splitter** | Trennlinie über dem Footer hochziehen → Footer vergrößern, zeigt das vollständige Analyse-Log |
| **Footer** | **🧊 CAD ansehen** (nur FreeCAD-Geometrie, schnell) · **🧪 Smoke-Test** (Backend-Selbsttest) · **⚙ Echte Berechnung** (volle Pipeline) |
| **💬 Chat** (unten rechts) | Fragen zu den Ergebnissen bzw. zum Vergleich stellen |
| **💾 Speichern…** (oben rechts) | Öffnet ein Vorschau-/Auswahlfenster mit allem, was gerade speicherbar ist (Projektdaten, Bewertung, 3D-Lauf, Varianten) — ein Klick statt mehrerer Einzelknöpfe |

Es gibt **keinen eigenen „Bericht"-Tab** mehr — der PDF-Bericht wird im Tab
**① Projekt** erzeugt (dort, wo auch alle anderen projektbezogenen Angaben liegen).

Tabs sind auch per URL-Anker direkt erreichbar, z. B. `…:5000/#compare`,
`#optimize`, `#projects`, `#text2ema`, `#rag`, `#designer`, `#import`, `#em3d`.

### Automatisches Speichern (Autosave)

Die Eingaben werden beim Tippen automatisch gespeichert — sowohl im **Browser-
Speicher** (localStorage) als auch auf dem **Server**. Wenn du den Browser aus
Versehen schließt, sind beim nächsten Öffnen alle Werte wieder da. Der Server-Stand
gewinnt, falls er neuer ist. Beim Start einer neuen Analyse wird der Zustand
zurückgesetzt.

---

## 3. Schritt-für-Schritt-Workflow

### Tab ① Projekt

Der **zentrale Einstiegspunkt** — hier startet jede Auslegung, und hier laufen alle
projektbezogenen Angaben zusammen. Alle folgenden Berechnungen (Geometrie, FEM,
3D-Feld, Bericht) schreiben in das **aktive Projekt**.

| Bereich | Inhalt |
|---|---|
| **➕ Neues Projekt anlegen** | Name, Tags (Komma-getrennt), Notizen/Ziel der Auslegung → legt sofort einen Projektordner an und aktiviert ihn |
| **📂 Bestehendes Projekt** | Liste + Suchfeld zum Aktivsetzen; **Galerie ⤢** öffnet die volle Kartenansicht (Vorschaubild, Kennwerte, „📋 Als Vorlage verwenden", „📁 Klonen", „⬇ Bundle exportieren", „📦 Import", „📄 Bericht öffnen", „🗑 Löschen") |
| **🗂 Organisation & Verlauf** | Status (neu/rechnet/gerechnet/bewertet/berichtet/verworfen), Tags, Notizen (fließen in Chat & Bericht) sowie der **Evolutionsverlauf** — jede Berechnung als Eintrag mit den geänderten Eingaben, inkl. Abstammung von Vorlagen/Klonen |
| **📎 Projekt-Dokumente** | Projektspezifische **Wissens-Dateien** (PDF/MD/CSV, werden eingebettet und von Chat & Bericht *dieses* Projekts durchsucht) und reine **Anhänge** (landen zusätzlich in der Projekt-Wissensbasis) |
| **📄 PDF-Bericht** | Standard- oder 6-Experten-Bericht für das aktive Projekt erzeugen (siehe unten); bindet — sofern vorhanden — die 3D-Feldberechnung mit ein |
| **🧲 Gespeicherte 3D-Läufe** | Im Tab 🧲 3D-Feld berechnete Elmer-Lösungen benannt ablegen und **ohne Neurechnen** wieder im Viewer öffnen (`<Projekt>/em3d_runs/`) |
| **🧰 Globale Werkzeuge & Daten** (eingeklappt) | **📚 Globale Wissensbasis** (projektübergreifende Referenzmaschinen + Dokumentation, speist Text→Auslegung/KI entwerfen/Chat) und **🎓 LLM-Trainingsdaten** (Kennzahlen + Download SFT-/VLM-JSONL) |

Ein Projekt muss **aktiv** sein, bevor auf den anderen Tabs sinnvoll gerechnet werden
kann — der aktive Name steht als Badge oben im Tab, und `loadProjectById`/„Als Vorlage
verwenden" setzen ihn automatisch. Die gleiche Organisations-/Verlaufs-/Verknüpfungs-
Ansicht ist zusätzlich als aufklappbares **🗂 Projektakte**-Panel im Ergebnis-Tab
verfügbar (kontextbezogen zum gerade geladenen Projekt).

#### PDF-Bericht

| Modus | Beschreibung |
|---|---|
| **Standard** | Ein LLM-Aufruf erzeugt den gesamten Bericht |
| **Agentisch (6-Experten)** | Sechs Experten-Agenten schreiben parallel Teilkapitel (EM, Thermik, Struktur, Fahrzyklus, Bewertung, Empfehlung) |

Benötigt Ollama + `pandoc` + `pdflatex`. **Formatierung:** keine Zahlenwerte im
Fließtext (das LLM ordnet Werte oft falsch zu) — stattdessen umfassende
**deterministische Tabellen** (nach Domäne gruppiert) direkt nach der Zusammenfassung
+ **qualitativer Fließtext** mit symbolischen Formeln; Feldbilder, Kennlinien und
Verformungsbilder werden als Abbildungen eingebettet; das Dokument ist linksbündig
(keine Blocksatz-Streckung um lange Formelausdrücke). Ist eine 3D-Feldberechnung
vorhanden, ergänzt der Bericht automatisch einen bebilderten Abschnitt „3D-
Magnetfeldvalidierung" mit der 2D-vs-3D-Kennwerttabelle.

---

### Tab ② Geometrie

Hier legst du die komplette parametrische Motor-Geometrie fest.

#### Hauptabmessungen

| Parameter | Einheit | Beschreibung |
|---|---|---|
| **Stator Außen-Ø** | mm | Außendurchmesser des Stator-Blechpakets |
| **Stator Innen-Ø** | mm | Innendurchmesser des Stators (= Bohrungsdurchmesser) |
| **Rotor-Ø** | mm | Außendurchmesser des Rotors (Stator-Innen-Ø minus 2× Luftspalt) |
| **Wellen-Ø** | mm | Wellendurchmesser |
| **Wellen-Bohrung** | mm | 0 = Vollwelle; > 0 → Hohlwelle (verringert Trägheit und Masse) |
| **Blechpaketlänge** | mm | Axiale Länge des aktiven Pakets |

Alle Abmessungen sind in einem weiten Bereich einstellbar (Stator-OD bis 3000 mm,
Welle ab 2 mm) — das Werkzeug taugt also sowohl für kleine Drohnenantriebe als auch
für große Traktionsmotoren.

#### Stator / Wicklung

| Parameter | Beschreibung |
|---|---|
| **Anzahl Nuten** | Nutenzahl des Stators (typ. 6 × Polpaarzahl für verteilte Wicklung) |
| **Nuttiefe** | Tiefe der Statornut in mm (2–200 mm) |
| **Leiter pro Nut (Hairpin)** | Geradzahlig 2–12; bestimmt das CAD-Modell der Wickelköpfe UND den Phasenwiderstand/Kupfervolumen im Thermomodell |
| **Spulenweite** | Nutschritte (0 = automatisch ≈ Nuten/Pole); kleinere Werte → gesehnte Wicklung |
| **Wickelkopf-Aufweitung** | Radiale Aufweitung der U-Bügelkronen in mm (0–25) |
| **Wickelkopf-Darstellung** | „Zugkörper" (glatter Loft-Sweep, Standard) oder „Box-Segmente" (Fallback bei Loft-Fehler). Nur im 3D-CAD/STEP sichtbar |

Die Hairpin-Wickelköpfe werden als kollisionsfreie U-Pins gebaut: das „Hin"-Bein auf
dem inneren Radius, das „Rück"-Bein auf dem äußeren, mit radialem Versatz am Scheitel —
so kreuzen sich die Arme nie auf derselben Höhe. Als „Zugkörper" ist die Krone ein
**durchgezogener, glatter Sweep** (kein Facetten-/Box-Look) mit **nahtlosem Übergang**
in die Nutstäbe. Auf der gegenüberliegenden Seite (Schweißseite) wird die reale
Hairpin-Fertigung nachgebildet: jedes Beinende verschränkt sich um eine halbe
Spulenweite (Twist) und läuft dann ein Stück **gerade parallel zur Motorachse** als
Schweißfahne aus — die zusammengehörigen Fahnenpaare konvergieren radial bis auf einen
sichtbaren Lichtspalt, ganz ohne Bauteil-Durchdringung.

#### Wellenverbindung (Blechpaket–Welle)

Drei Verbindungstypen mit jeweils eigenen Parametern:

| Typ | Parameter | Beschreibung |
|---|---|---|
| **Querpressverband** (Schrumpfsitz) | Übermaß (diametral, µm) | Klassische Presspassung; die analytische Bewertung berechnet Fugenpressung, übertragbares Moment und Lösedrehzahl (wo die Fliehkraft die Pressung aufhebt) |
| **Keilwelle** (Vielnut) | Zähne / Zahn-Tiefe (mm) | Vielnutprofil; Flankenpressung und Drehmomentkapazität |
| **Polygonprofil** (P3G) | Lappen / Exzentrizität (mm) | DIN-P3G-Profil; Flächenpressung und Drehmomentkapazität |

Das gewählte Profil wirkt sich auf die CAD-Geometrie (Welle + Rotorbohrung passen
zueinander) **und** auf die analytische Bewertung im Ergebnis-Tab aus. Die Fliehkraft-
FEM fixiert immer die innersten Rotorflächen, egal welches Profil.

#### Komponenten (Geometrie-Erzeugung)

Steuert, welche Bauteile beim 3D-/STEP-Aufbau erzeugt werden. Damit lässt sich das
Modell schrittweise aufbauen (z. B. erst Welle + Rotor + Magnete, dann Stator und
Wicklung dazu). **Steuert nur die CAD-Geometrie** — die EM-/Thermik-/Struktur-Rechnung
bleibt unverändert.

| Checkbox | Standard | Beschreibung |
|---|---|---|
| **Welle** | ✓ | Rotorwelle (mit gewähltem Verbindungsprofil) |
| **Rotor-Blechpaket** | ✓ | Rotor-Eisenring (mit Magnettaschen) |
| **Magnete** | ✓ | Magnete in den Taschen / auf der Oberfläche |
| **Stator-Blechpaket** | ✓ | Stator-Eisenring (mit Nuten) |
| **Hairpins (Nut-Stäbe)** | ✓ | Gerade Kupferstäbe in den Nuten |
| **Wickelköpfe (U-Bügel)** | ✓ | Gebogene Verbindungsstücke über dem Paket |
| **Lager A-Seite / B-Seite** | ☐ | Vereinfachte Lagerringe auf der Welle (Außen-Ø / Breite / Abstand einstellbar) |
| **Isolationspapier** | ☐ | Dünne Schale über den Wickelköpfen (Dicke einstellbar) |
| **Wuchtscheiben-Bolzen** | ☐ | Siehe nächster Abschnitt |
| **Flussbarriere q-Achse** | ☐ | Radiale Luftschlitze zwischen den Polen (reduziert Streufluss) |
| **Flussbarriere d-Achse** | ☐ | Radiale Luftschlitze in der Polmitte (trennt die Pol-Arme) |

##### Wuchtscheiben-Bolzen

Symmetrische Durchgangsbohrungen durch das **gesamte** Blechpaket für die Verschraubung
der Wuchtscheiben. Aktivierung über die Checkbox „Wuchtscheiben-Bolzen".

| Parameter | Beschreibung |
|---|---|
| **Gewinde** | M4 bis M20 (Bohrung = Nenn-Ø + 0,4 mm, z. B. M6 → 6,4 mm Bohrung) |
| **Lochkreis-Ø** | 0 = automatisch (Mitte zwischen Welle und Rotor-OD); sonst frei |
| **Versatzwinkel** | Drehung der Bohrungen in ° |

Eigenschaften:
- Die **Anzahl** ist an die Polzahl gekoppelt (Bolzen = Polzahl).
- Die Bohrungen werden in den **Rotor** geschnitten — die Fliehkraft-FEM sieht die
  Schwächung des Rotors durch die Löcher. Auch die 2D-Schnittbilder, die
  Live-Vorschau und die FDM-Feldsimulation zeigen die Bohrungen.
- Die Bolzen sind als separate Volumenkörper (`BalanceBolts`) im CAD-Modell enthalten.

##### Flussbarrieren

Radiale Luftschlitze im Rotorblech, ein Schlitz pro Pol, voll symmetrisch. Werden in
**vier Darstellungen** berücksichtigt: 3D-CAD, 2D-Schnittbild, Live-Vorschau und
FDM-Feldsimulation (sie rotieren mit dem Rotor). Die Bohrungen gehen auch in die
Fliehkraft-FEM ein.

| Parameter | Beschreibung |
|---|---|
| **Schlitz-Breite** | Tangentiale Breite in mm (0,5–40) |
| **Schlitz-Tiefe** | Radiale Tiefe in mm (1–120); Außenkante beginnt 2 mm unter der Rotor-OD (Eisenbrücke) |

- **q-Achse**: Schlitz liegt zwischen zwei Polen — reduziert den Streufluss zwischen
  benachbarten Polpaaren.
- **d-Achse**: Schlitz liegt in der Polmitte — trennt die beiden V-Arme eines Pols.

#### Magnet-Topologie

| Parameter | Beschreibung |
|---|---|
| **Polpaare (p)** | 1–40; bestimmt mit der Nutzahl die Wicklungsauslegung |
| **Magnet-Anordnung** | V-Form · asymmetrisches V · Doppel-V · U · Delta · PMa-SynRM · SPM · Halbach · Speiche · Balken |
| **Magnet-Orientierung (Polung)** | „Lange Seite N/S" (quer, Standard) oder „Kurze Seite N/S" (90° gedreht, längs). Wirkt identisch in Live-Vorschau und FDM |
| **Magnettasche (nur V-Form)** | Umschaltbar: „Position (Radius) + Länge" oder „Durchmesser (Außen-Ø / Innen-Ø) + Winkel" |
| **Öffnungswinkel** | Winkel zwischen den V-Armen (40–170°) |
| **Asymmetrie** | Nur bei „asymmetrisches V": Versatz des Arm-Winkels (−60° bis +60°) |
| **Position (Radius)** | Radiale Sitztiefe des Magneten (30–95 % des Radius) |
| **Magnet Länge** | Länge des einzelnen Magneten in mm (3–400 mm); wird ggf. automatisch auf die geometrisch maximale Länge gekürzt (der Hinweis erscheint orange) |
| **Magnet Dicke** | Dicke in mm (1–80 mm) |
| **Magnet-Luftspalt** | Spalt zwischen Magnet und Taschenwand in mm (0,05–0,3); wirkt auf die Taschengröße im CAD, der Magnet behält Nennmaß |
| **Magnet Abstand (Steg)** | Eisensteg zwischen Magnettasche und Rotor-OD |
| **Tangentialmagnet Länge** | Nur bei U und Delta: Länge des tangentialen Magnetarms (0 = auto) |
| **Lagen-Abstand / Lagen-Anzahl** | Nur bei Doppel-V und PMa-SynRM: radialer Abstand und Anzahl der Magnetlagen |
| **Polbedeckung** | Nur bei SPM und Halbach: wie viel des Umfangs vom Magneten bedeckt ist (50–98 %) |
| **Magnete / Pol (Halbach)** | Anzahl der geraden Magnetsegmente pro Pol im Halbach-Array (2–24) |
| **Segmente axial / umfang** | Magnetunterteilung (reduziert Wirbelstromverluste ∝ 1/n²) |

**Topologie-Übersicht:**

| Code | Magnetanordnung | Typischer Einsatz |
|---|---|---|
| **V** | Zwei Magnete pro Pol in V-Anordnung, eingebettet | Standard-IPM (BMW i3, Tesla Model 3) |
| **Asymm. V** | V mit unterschiedlichem Öffnungswinkel pro Arm | Geräusch-/Harmonische-Optimierung |
| **Doppel-V** | Zwei V-Lagen übereinander (4 Magnete/Pol) | Hohe Polpaarzahl, starker Reluctance-Anteil |
| **U** | Radial + tangentiale Magnete in U-Form | Gute Flusskonzentration |
| **Delta** | Drei Magnete in Deltaform | Hohe Remanenz-Nutzung |
| **PMa-SynRM** | Mehrere Magnetlagen in Flussbarrieren | Geringer Magnetverbrauch, breiter FW-Bereich |
| **SPM** | Magnete auf der Rotoroberfläche | Einfach, kein Reluctance-Moment |
| **Halbach** | Gerade Oberflächenmagnete mit rotierender Magnetisierung | Hoher Grundwellengehalt, sinus-förmig |
| **Speiche** | Magnete radial zwischen den Polen | Flusskonzentration (Ferrit-geeignet) |
| **Balken** | Einzelner flacher Magnet pro Pol | Einfachste IPM-Variante |

#### Buttons im Geometrie-Tab

| Button | Funktion |
|---|---|
| **↺ Vorschau aktualisieren** | Live-Querschnittsbild neu berechnen (bei manueller Parameteränderung) |
| **🧠 Aus Beschreibung ableiten** | Öffnet „Text → Auslegung" (siehe Abschnitt 4) |
| **📚 Wissensbasis** | Öffnet die RAG-Verwaltung (siehe Abschnitt 4) |

---

### Tab ③ Betrieb & Material

#### Werkstoffe

| Werkstoff | Auswahl |
|---|---|
| **Rotorblech** | M250-35A (Premium) · M270-35A (Standard) · M400-50A (günstig) · M800-65A (grob) · S235 (Vollmaterial) · 42CrMo4 (hochfest) |
| **Statorblech** | M250-35A · M270-35A · M400-50A · M800-65A (mit zugehörigen Ummagnetisierungsverlusten p in W/kg) |
| **Hairpin-Leiter** | Cu-ETP (Standard) · CuCrZr (hochfest) · CuAg0.1 (Silber) · Al 1350-H19 (leicht) |
| **Magnet-Typ** | NdFeB N35 (1,15 T) · N42 (1,28 T) · N50 (1,40 T) · Ferrit Y30 (0,40 T) |

Die Materialauswahl fließt in die FEM (E-Modul, Streckgrenze), die Verlustberechnung
(spez. Eisenverluste, Kupferleitwert), die Thermik (Wärmeleitwerte) und das Magnetfeld
(Remanenz Br, µr).

#### Thermisches Modell

| Parameter | Beschreibung |
|---|---|
| **Kühlungsart** | Natürliche Konvektion (h≈8) · Zwangsluft (h≈35) · Wassermantel (h≈800) · Ölkühlung (h≈2500 W/m²K) |
| **Umgebungstemperatur** | −40 bis 80 °C |

Das Modell rechnet ein 6-Knoten-LPTN (Wicklung, Statoreisen, Rotoreisen, Magnete,
Welle, Gehäuse) im stationären Zustand und transient über 30 Minuten.

#### Fahrzyklus

| Zyklus | Beschreibung |
|---|---|
| **WLTP Class 3b** | Genormtes Stadt-/Überlandprofil (approximiert) |
| **Autobahn-Vollgas** | 220 km/h Dauerlauf (Worst-Case für thermische Belastung) |
| **Anhänger-Alpenpass** | Bergauffahrt mit Anhänger, steilste Steigung einstellbar |
| **Alle drei** | Alle Zyklen nacheinander berechnet |
| **Eigene CSV** | `t[s], v[km/h]` — komma- oder semikolon-getrennt |
| **Ausschalten** | Keine Zyklusberechnung |

**Fahrzeugparameter:**

| Parameter | Einheit | Standard |
|---|---|---|
| Fahrzeugmasse | kg | 1600 |
| c_w · A | m² | 0,65 |
| Rollwiderstand c_r | — | 0,012 |
| Raddurchmesser | m | 0,32 |
| Getriebeübersetzung | — | 9,5 |
| Drivetrain η | — | 0,95 |
| Regen-Anteil | — | 0,55 |

**Anhänger-Einstellungen** (wirken nur auf den Anhänger-Zyklus):

| Parameter | Einheit | Standard |
|---|---|---|
| Anhänger-Masse (inkl. Nutzlast) | kg | 1800 |
| Anhänger-Achsen | — | 2 |
| max. Steigung (Bergauffahrt) | % | 15 |

Im Anhänger-Modus wird die Anhängermasse zum PKW addiert, c_wA steigt um 0,85 m²,
der Rollwiderstand steigt auf ≥ 0,018, v ist auf 100 km/h begrenzt und Rekuperation
sinkt auf 30 %. WLTP und Autobahn fahren immer ohne Anhänger.

#### Weitere Funktionen (im selben Tab)

| Element | Funktion |
|---|---|
| **🖼 Nur ein Frame rechnen** | Einzelnes hochauflösendes Feldbild (400–5000 px) ohne Volllauf; ab 3000 px Multigrid-Solver |
| **＋ Geometrie merken** | Aktuelle Konfiguration als Variante für den Vergleich ablegen (bis 10 Varianten) |
| **🔧 FreeCAD / 📦 STEP** | Nach einem Lauf: FreeCAD-GUI öffnen / STEP herunterladen |

Projekt anlegen/öffnen, Projekt-Browser (Galerie) und der PDF-Bericht liegen zentral im
Tab **① Projekt** — siehe oben.

---

### Tab ④ Berechnung

#### Analyse-Einstellungen

| Parameter | Beschreibung |
|---|---|
| **RPM von / bis / Schrittweite** | Drehzahlbereich für EM- und Strukturkennlinie. Die Fliehkraft-FEM läuft automatisch bei „RPM bis" (Worst-Case) |
| **Frames pro Drehzahl** | 4 (schnell) bis 72 (Cine) — Anzahl Rotorwinkel pro Drehzahl in der Feldanimation |
| **Feld-Darstellungsmodi** | Rotor-Rotation (immer aktiv); zusätzlich optional Ankerrückwirkung (Stromwinkel-Sweep) und/oder Last-Rampe (0→Volllast) |
| **FDM-Auflösung** | 100–800 px für das statische Feld; höher = schärferer Luftspalt, aber länger. Direkter Sparse-Solver (exakt bei jeder Auflösung) |
| **Frame-Auflösung** | 120–600 px für die Animationsframes; pro Rotorwinkel eine Faktorisierung, pro Drehzahl nur Rücksubstitution |
| **Flussdichte-Skala** | Maximum der |B|-Farbskala in Tesla (0 = automatisch ≈ 2,1 T). Für hochgesättigte Motoren höher setzen |

#### Strukturanalyse (Festigkeit)

| Parameter | Beschreibung |
|---|---|
| **Netz-Auflösung** | Gmsh-Elementgröße: 4/3/2,5/2 mm — kleiner = feiner, löst Spannungsspitzen an den Magnettaschen-Stegen besser auf |
| **Einzelbild-Auflösung** | Verformungsbilder bis 5000 px |
| **Verformungs-Video** | Checkbox + Frame-Zahl (20–72). Zeigt eine Drehzahl-Rampe 0→max mit wachsender Verformung |

CalculiX rechnet **einmalig** bei Maximaldrehzahl. Spannung und Verschiebung bei
anderen Drehzahlen werden über die **rpm²-Skalierung** abgeleitet (Fliehkraft ∝ ω²,
lineare FEM → linearer Zusammenhang). Daraus ergeben sich die Bilder bei Nennlast,
Maximaldrehzahl und Berstdrehzahl (dort SF → 1) ohne weitere Solver-Läufe.

#### Zielwertoptimierung

Button **🎯 Zielwertoptimierung öffnen** — siehe Abschnitt 4.

#### Parameterstudie (bei fester Drehzahl)

Variiert **einen** Parameter von x bis y in N Schritten bei fester Drehzahl und zeigt
den Einfluss auf **alle** Kennwerte als Small-Multiples-Diagramm.

| Parameter | Beschreibung |
|---|---|
| **Parameter** | Dropdown mit allen variierbaren Größen (Öffnungswinkel, Magnetlänge/-dicke, Steg, Nuttiefe, Polpaare, Blechlänge, Luftspalt, Magnet-Luftspalt, Asymmetrie …) |
| **von x / bis y** | Untere und obere Grenze des Sweeps |
| **Schritte** | Anzahl der gleichmäßigen Schritte (2–500, Standard 100) |
| **Drehzahl (fest)** | Die Drehzahl, bei der alle Schritte ausgewertet werden |
| **Feldlinien-Bilder + Video** | Checkbox: für jeden Schritt ein FDM-Feldbild rechnen → Video (Parametervariation sichtbar als Bildfolge) |
| **Feld-Frames / Feld-Auflösung** | Anzahl und Auflösung der Feldbilder (2–500 Frames, 200–600 px) |

Jeder Kandidat wird mit dem **schnellen Analytik-Evaluator** (~0,5 s, kein FreeCAD/
FEM) bewertet — die Geometrie wird bei jedem Schritt angepasst. 100 Punkte kosten
ca. 50 Sekunden. Ergebnis: Kennwert-Diagramme + optionale Bild-Galerie/Video + CSV-
Download aller Schritt-Werte. Ein **📄 Parameterstudie-Bericht (PDF)** kann ebenfalls
erzeugt werden (LLM-Analyse der Studien-Daten).

---

### Tab ▶ Live-Simulation

Echtzeit-Darstellung und Steuerung der Motor-Live-Vorschau.

| Steuerung | Funktion |
|---|---|
| **Play / Stop** | Animation starten/stoppen |
| **Reset** | Rotorwinkel auf 0 zurücksetzen |
| **Ultra Slow** | ~1/3000× Geschwindigkeit mit maximaler Feldpräzision (300 px). Ideal für schnelle Rotoren (z. B. 20.000 U/min) |
| **Lastmoment** | S1-Auslegungspunkt (0–450 Nm). Nur für Feldanimation & stationäre Thermik — die Fahrzyklus-Thermik nutzt dies **nicht** |
| **Feldschwächung** | d-Strom für Feldschwächungsbetrieb (0–800 A) |
| **Geschwindigkeit** | Zeitfaktor der Animation (0,05× bis 2×) |
| **Feld-Auflösung** | Niedrig/Mittel/Hoch für die Live-Vorschau |
| **Feldlinien-Dichte** | Anzahl der Äquipotentiallinien (5–30) |

Die Live-Vorschau zeigt den Motor-Querschnitt mit farbkodierter Flussdichte (magma-
Farbskala, schwarz→violett→rosa→weiß), Feldlinien (cyan), Geometrie-Umrisse (Stator/
Rotor/Welle) und Magnet-Umrisse (rot = Nordpol, blau = Südpol). Dient der **schnellen
visuellen Kontrolle** der Geometrie — ersetzt nicht die Vollberechnung.

---

### Tab 🎨 Designer (Canvas)

Freier Rotor-Entwurf: du zeichnest **eine Halbpol-Geometrie** auf einem Canvas, die
automatisch über die d-Achse gespiegelt und über alle Pole vervielfältigt wird
(alternierende Polarität). Die Analyse nutzt den vollen Pipeline-Pfad
(FreeCAD/FDM/FEM/Thermik).

#### Abmessungen

Eigene Eingabefelder für Stator-OD, Rotor-OD, Wellen-Ø, Luftspalt (→ Stator-ID wird
berechnet), Blechpaketlänge, Polzahl, Nutzahl, Leiter/Nut — unabhängig vom
Geometrie-Tab.

#### Werkzeuge

| Werkzeug | Bedienung |
|---|---|
| **▭ Auswahl** | Magnet oder Barriere anklicken → verschieben, Parameter ändern |
| **🧲 Magnet** | Auf den Rotor klicken und ziehen → gerader Magnet. Position/Länge/Neigung durch Mausbewegung; Dicke und Polarität (N/S) über die Felder neben dem Werkzeug |
| **〰 Barriere** | Klicks setzen Polylinien-Punkte; Doppelklick beendet. Breite über das Feld einstellbar |

**Magnete** sind immer gerade (keine Bogenformen). Position, Länge und Neigung werden
per Maus gesetzt und sind in der Seitenleiste als synchonisierte Liste sichtbar
(anklickbar). Magnet-Dicke und N/S-Polarität können im Werkzeug-Bereich geändert
werden. Der **Magnet-Luftspalt** (Tasche/Seite) ist ebenfalls als Feld vorhanden.

**Barrieren** sind Polylinien mit einstellbarer Breite — sie werden als „Kapsel"-
Geometrie (Zylinder um jeden Linienabschnitt) in FreeCAD, FDM und 2D-Schnitt als
Luftschlitze in den Rotor geschnitten.

#### Build-Prozess

1. Du zeichnest den **Halbpol** (obere Hälfte, d-Achse = vertikale Symmetrieachse).
2. Button **⚙ CAD + Berechnung erzeugen** kompiliert:
   - Spiegelt die Magnete an der d-Achse → vollständiger Pol.
   - Verteilt den Pol mit alternierender Polarität über alle Pole.
   - Erzeugt ein Payload mit `magShape:"custom"` + `customLegs` + `customBarriers`.
   - Startet die volle Pipeline (identisch mit „⚙ Echte Berechnung").

Die Magnete und Barrieren der Seitenleiste können einzeln gelöscht oder bearbeitet
werden.

> **Hinweis:** Ein Designer-/KI-Entwurf bringt seine Rotor-Luftschlitze ausschließlich
> über die **gezeichneten Barrieren** mit. Die parametrischen **Flussbarrieren (q/d)** und
> die **Wuchtbolzen-Bohrungen** aus dem Geometrie-Tab werden für einen Designer-Lauf
> bewusst **ignoriert**, damit keine doppelten/fremden Schlitze in den Rotor geraten.
> Übrige Geometrie-Tab-Einstellungen (Material, Kühlung, Welle-Verbindung, Lager) gelten
> weiterhin.

#### 🤖 KI entwerfen (im Designer)

Statt selbst zu zeichnen, lässt du die KI **komplette Maschinen** entwerfen — Hauptmaße,
Polzahl, Material, Betriebspunkt **und** die Magnete + Flussbarrieren direkt auf dem
Canvas. Du gibst die Hauptmaße als **Bereiche (von–bis)** vor; pro Variante wird daraus
zufällig gezogen. So geht's:

1. **Beschreibung (optional):** beschreibe die Anwendung (z. B. *„Traktionsmotor,
   hohe Effizienz, wassergekühlt"*) — wird der KI als Zusatzkontext mitgegeben.
2. **Bereiche (von–bis)** eintragen: **Stator-Außendurchmesser**, **Länge**,
   **Wellen-Durchmesser** und **Luftspalt**. Der Luftspalt ist auf den zulässigen Bereich
   **0,5–3 mm** begrenzt (Werte außerhalb werden hineingeklammert).
3. **Anzahl Varianten** (1–99, Standard 3) wählen und **✨ KI entwerfen** klicken.
4. Pro Variante werden die vier Maße (inkl. Luftspalt) **zufällig gezogen und fest
   gesetzt**; die KI (lokales Modell `qwen-gross:latest`, mit Referenzmaschinen aus der
   Wissensbasis geerdet) ergänzt Polzahl, Nutzahl und Material und **zeichnet Magnete +
   Flussbarrieren** passend dazu. Stator-Innen- und Rotor-Außendurchmesser ergeben sich aus
   dem gezogenen Luftspalt.
5. **Variante 1** wird sofort auf den Canvas + ins Formular geladen; alle Varianten
   erscheinen als Buttons — ein Klick lädt eine andere. Jeder Button trägt ein
   **gut/schlecht-Symbol** (👍/👎) aus der schnellen Vorab-Bewertung. **Du kannst das
   Urteil korrigieren:** neben jeder Variante gibt es 👍/👎-Knöpfe — ein Klick überschreibt
   die automatische Einschätzung (ein „✎" markiert die Korrektur, nochmal klicken setzt sie
   auf „automatisch" zurück). Dein korrigiertes Urteil wird beim Rechnen als **manuelle
   Bewertung** ins Trainingsfile übernommen.
6. Du kannst den Entwurf **prüfen und von Hand nachbessern** (Magnete verschieben,
   Barrieren ändern) und dann **⚙ CAD + Berechnung erzeugen** für eine einzelne Variante.
7. Oder **▶ Alle rechnen & vergleichen**: rechnet alle Varianten nacheinander durch die
   volle Pipeline und legt sie automatisch in den **Vergleich** (vorausgewählt).
   Varianten, die du mit **👎** bewertet hast, werden dabei **nicht gerechnet**, aber
   trotzdem **als „schlecht" ins LLM-Trainingsfile** geschrieben (mit den schnellen
   Vorab-Kennwerten) — so sammelst du Negativbeispiele, ohne Rechenzeit zu verbrauchen.

> **Feste Rechen-Drehzahlen:** Es wird ausschließlich an den Drehzahlen
> **1000 / 5000 / 15000 / 20000 1/min** gerechnet (statt eines von–bis-Sweeps). Die
> Struktur-FEM löst wie immer bei der höchsten Drehzahl (20000) als Worst Case.

> **Automatische Qualitäts-Vorsortierung:** Jeder erzeugte Entwurf wird sofort
> FreeCAD/FEM-frei bewertet (Luftspaltflussdichte, Temperaturen, sichere Drehzahl).
> Fällt ein Entwurf **schlecht** aus, generiert die KI mit gezieltem Mängel-Feedback
> **automatisch einen neuen** (bis zu 2 Nachversuche je Variante) und behält den besten.

> Robust: Liefert das Modell keine brauchbare Freihand-Geometrie, wird automatisch ein
> gültiger Halbpol aus der passenden Standard-Topologie erzeugt — es kommt **immer** ein
> zeichenbarer Entwurf heraus. Jeder gerechnete KI-Entwurf wird (inkl. der
> Aufgabenbeschreibung) im **LLM-Trainingsdatensatz** gespeichert.

> **Nur halber Pol & saubere Barrieren:** Es wird **immer nur die obere Pol-Hälfte**
> gezeichnet (Magnete mit Versatz ≥ 0, Barrieren mit y ≥ 0) — die andere Hälfte entsteht
> automatisch durch Spiegelung an der d-Achse. Das gilt auch beim Zeichnen von Hand (unter
> der d-Achse lässt sich nichts setzen). Eine Flussbarriere, die in einen Magneten
> hineinliefe, wird automatisch **verworfen** (geprüft gegen jeden Magneten und seine
> Spiegelung) — übrig bleiben nur Barrieren neben/zwischen den Magneten.

#### 🎯 Magnete fein-optimieren

Optimiert die **gezeichneten Magnet-Koordinaten** (Radius, Versatz, Neigung, Länge,
Dicke) auf ein Ziel hin — schnell und FEM-frei, LLM-gesteuert:

1. Wähle die **Zielgröße** (z. B. Maxwell-Moment, B_gap) und **maximieren / minimieren /
   Zielwert**.
2. Optional eine **Randbedingung** (z. B. *T_Wicklung ≤ 180 °C*) und die Iterationszahl.
3. **🎯 Magnete optimieren** — das **beste Layout** wird zurück auf den Canvas gezeichnet;
   der Statustext zeigt die Verbesserung (Ausgang → Bestwert). Anschließend normal rechnen.

> Im Unterschied zur **🎯 Zielwertoptimierung** (Berechnung-Tab), die globale
> parametrische Felder variiert, perturbiert dieser Zweig die einzeln gezeichneten
> Magnete. Die Pol-Symmetrie bleibt erhalten (nur der Halbpol wird verändert + gespiegelt).

#### 📈 Parameterstudie für diesen Entwurf

Schickt die gezeichnete Geometrie in die **Parameterstudie** (Berechnung-Tab): Der Button
**„📈 Parameterstudie für diesen Entwurf"** wechselt auf den Berechnung-Tab, beschränkt die
Parameter-Auswahl auf die **geometriewirksamen** Größen (Blechpaketlänge, Luftspalt,
Nuttiefe, Polzahl, Magnet-Luftspalt — die Magnet-Form-Parameter wirken nicht auf frei
gezeichnete Magnete) und zeigt einen grünen Hinweis. Mit **✕ zurücksetzen** läuft die
Studie wieder auf der Formular-Auslegung.

---

### Tab 📥 STEP-Import

Importiere die **STEP-Datei eines fertigen E-Motors** (Stator + Rotor + Wicklung). Das
Werkzeug erkennt automatisch die **Magnetlage**, leitet die Hauptmaße ab und bereitet
eine **Festigkeits-** und **elektromagnetische Analyse** der realen Geometrie vor.

So geht's:

1. **STEP-Datei wählen** (`.step`/`.stp`) und **📥 STEP importieren & analysieren** klicken.
2. Im Hintergrund liest FreeCAD alle Volumenkörper aus; eine Heuristik klassifiziert sie
   (über radiale Bänder, Volumen-Cluster und Rotationssymmetrie) in **Welle / Rotor-Blech /
   Magnete / Stator-Blech / Wicklung**, leitet **Polzahl, Nutzahl, Durchmesser, Luftspalt
   und Länge** ab und schätzt je Magnet eine orientierte Bounding-Box → **Halbpol-Magnete**.
3. Eine `motor.FCStd` mit benanntem **„Rotor"** wird geschrieben — damit rechnet die
   **bestehende Fliehkraft-FEM direkt auf der importierten Geometrie**.
4. Das Ergebnis wird in den **Designer** geladen (Maße + Magnete auf dem Canvas).
   **Prüfe und korrigiere** die erkannte Magnetlage/Polung dort.
5. Mit **⚙ CAD + Berechnung erzeugen** (Designer) startet die volle Analyse: die EM-Rechnung
   nutzt die erkannten Magnete (`customLegs`), die Festigkeits-FEM das echte importierte
   Rotor-Solid.

> **Grenzen (bewusst):** Die Erkennung ist **heuristisch** — daher der Pflicht-
> Bestätigungsschritt im Designer. Die Motorachse wird als **Z** angenommen.
> Flussbarrieren (Luftschlitze im Rotor) werden in dieser Version **nicht** automatisch
> erkannt. **Werkstoffe, Magnet-Br, Wicklung und Betriebspunkt** stehen nicht in der
> Geometrie und müssen in den Tabs „Geometrie"/„Betrieb & Material" gesetzt werden.

> **Makro:** Dieselbe Erkennung gibt es als eigenständiges FreeCAD-Makro
> `step_import.FCMacro` (direkt in der FreeCAD-GUI ausführbar, unabhängig vom Server).

---

### Tab 🧲 3D-Feld (Elmer)

Eine **echte 3D-Magnetfeldberechnung** mit dem externen FEM-Löser **Elmer** — als
Ergänzung zum (unendlich-lang angenommenen) 2D-Feldlöser. Sie zeigt, was 2D
prinzipbedingt nicht kann: **Endeffekte/finite Länge**, **Schrägung (Skew)**, eine echte
räumliche Feldlösung und einen **direkten Vergleich gegen 2D**. Eigenständiger
On-Demand-Job (der 2D-Pfad bleibt unverändert).

**Geometrie übernehmen:** Oben im Tab wählst du die **Geometriequelle** und klickst
**📥 Geometrie übernehmen** — die übernommene Geometrie wird als Zusammenfassung
(Stator-Ø, Rotor-Ø, Pole, Nuten, Magnet-Typ, Länge) angezeigt, damit du sie vor dem
(teuren) 3D-Lauf kontrollieren kannst. Quellen:

- **Geometrie-Tab (parametrisch)** — die normal konfigurierte Maschine.
- **Designer / importierte STEP** — die gezeichneten bzw. aus STEP erkannten Magnete
  (`customLegs`). Beim Öffnen des Tabs wird automatisch die passende Quelle übernommen
  (Designer, falls dort Magnete liegen, sonst der Geometrie-Tab).

**Einstellungen:**

| Parameter | Beschreibung |
|---|---|
| **Schrägung (Skew)** | Rotorschrägung in ° über die Paketlänge (0 = gerade) — reduziert Rastmoment/Oberwellen |
| **🧱 Hexaeder-Netz (strukturiert)** | Opt-in: baut ein strukturiertes Hexaeder-/Prismen-Netz (2D-Querschnitt + axiale Extrusion) statt Tetraedern. Löst den Luftspalt mit weniger Freiheitsgraden auf → weniger RAM, oft schärferes Feld. Gerader **und** gestaffelter Fall, inkl. Magnet-Langlöcher mit Klebespalt (wie im Tet-Netz). **Grenze (v1):** kein eingeprägtes Lastfeld → bei aktivem Lastfeld automatischer Rückfall auf Tetraeder. Ideal für die Leerlauf-/Feldvisualisierung. Nutzt Elmers Piola-Transformation + iterativen Löser (kann bei feinen Netzen etwas länger dauern) |
| **Mesh-Grobgröße** | Gmsh-Elementgröße außen in mm (größer = schneller, gröber) |
| **Luftspalt-Mesh** | Feinere Elementgröße im Luftspalt in mm (dort wird das Feld/Moment ausgewertet) |
| **Luftbox-Faktor** | Größe der umgebenden Luftbox (× Stator-OD) für die Außenrandbedingung |

**Zwei Buttons:**

- **🧊 3D-Modell ansehen (ohne Elmer)** — baut nur das 3D-Mesh und rendert das
  **3D-Schnittmodell** (Magnete rot = N / blau = S, Rotor-/Stator-Eisen) + die
  Stirnseiten-Ansicht der Polanordnung. Braucht **kein Elmer**, nur Gmsh/vtk.
- **🧲 3D-Feld berechnen (Elmer)** — voller Lauf: Gmsh-Mesh → Elmer-Magnetostatik →
  Auswertung. Ergebnis: **3D-|B|-Sättigungs-Schnittbild** (aufgeschnitten, in
  Sättigungsfarben eingefärbt — Skala ans Sättigungsknie ≈2 T gekoppelt, grüne
  Sättigungsgrenze, so ist direkt sichtbar wo das Eisen sättigen würde), die
  **Endeffekt-Kurve** (Luftspalt-|B_r| über der axialen Position — Maximum in der
  Mitte, Abfall zu den Stirnseiten), der **2D-vs-3D-Vergleich** des Luftspaltfelds und
  eine Kennwert-Tabelle.

Für die **volle interaktive 3D-Ansicht** (drehen, zoomen) gibt es drei Wege:

- **🧊 Im Browser ansehen (3D)** — ein **eingebetteter 3D-Viewer direkt in der Seite**
  (vtk.js, lokal mitgeliefert — keine Internetverbindung nötig). Zeigt die
  Festkörper-Oberfläche nach **|B| eingefärbt** mit Farbskala; mit der Maus drehen/zoomen.
  Braucht **kein** ParaView.
- **📊 In ParaView öffnen** — startet die installierte **ParaView**-GUI direkt mit der
  geladenen Ergebnisdatei (analog zu „🔧 FreeCAD"). Dann einmal **Apply** klicken und nach
  **„magnetic flux density"** einfärben. Benötigt ParaView (`sudo apt install paraview`).
  Volle Funktionen (Schnitte, Isoflächen, Stromlinien).
- **⬇ VTU herunterladen** — die `.vtu`-Datei für ParaView auf einem anderen Rechner.

> **Voraussetzung:** Elmer (`ElmerSolver`/`ElmerGrid`) muss installiert sein. Fehlt es,
> meldet der Server einen Installationshinweis (der „3D-Feld"-Button bleibt wirkungslos,
> die „3D-Modell"-Vorschau funktioniert weiter). Installation:
> ```bash
> sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa
> sudo apt-get update && sudo apt-get install -y elmerfem-csc
> ```

> **v1-Umfang:** lineare Materialien (Eisen µr = 500), **Open-Circuit** (nur Magnete,
> keine Statorströme). Daher ist das **Netto-Moment im Leerlauf ≈ 0** (der angezeigte
> Arkkio-Wert ist am groben Netz verrauscht). Der **Lastfall** (Spulenströme → echtes
> Moment) und die **nichtlineare BH-Kurve** sind als nächste Ausbaustufen vorgesehen.
> Ein grober Testlauf dauert Sekunden, ein feines Netz Minuten.

---

### ⚙ Analyse starten (Footer)

Der Footer enthält drei Workflow-Buttons:

| Button | Funktion |
|---|---|
| **🧊 CAD ansehen** | Nur die FreeCAD-Geometrie erzeugen (FCStd + STEP + 2D-Bilder). Schnell (~10–40 s), keine Analyse. Danach „🔧 FreeCAD" und „📦 STEP" verfügbar |
| **🧪 Smoke-Test** | Backend-Selbsttest (~17 Tests, ~15 s): prüft Importe, Topologie, FDM, Strom, Verformung, Skripterzeugung, Training und den KI-Auslegungs-Pfad. Kein FreeCAD nötig |
| **⚙ Echte Berechnung** | Volle Pipeline: FreeCAD-Geometrie → EM-Feld → Feldanimation → EM-Kennlinie → Fliehkraft-FEM → Verformung → Strukturkennlinie → Wellenverbindung → Thermik → Fahrzyklus |

Der Fortschritt (Balken + Log) wird im Footer angezeigt. Footer hochziehen (am
horizontalen Splitter) für das vollständige Log. Nach Abschluss springt die Ansicht
automatisch auf **FEM-Ergebnisse**.

---

### Tab 💧 Spritzöl-Kühlung (experimentell, Blender/Mantaflow)

Untersucht **qualitativ** die Fluidkühlung eines **Motor-Ausschnitts** mit Spritzöl.
Modelliert ist ein **Kühlring mit Düsen am Ende der Wickelköpfe**: aus seinen Bohrungen
spritzt Öl unter **Druck** **Richtung Drehachse** auf die Leiter, wo es **zerstäubt,
benetzt und abtropft**. Optional wird ein **Cutaway des Motors** (Welle · Rotor mit
Magneten · Stator) unter den Wickelköpfen mitgezeigt — gerechnet mit Blenders
Mantaflow-FLIP-Löser auf der echten generierten Geometrie.

> **⚠ Ehrliche Einordnung:** Das ist eine **visuelle/qualitative** Studie, **keine**
> validierte Kühlrechnung. Es entsteht **kein Temperaturfeld und kein Wärmeübergangs­
> koeffizient**. Die Kennwerte (benetzte Fläche %, Abdeckungs-Heatmap, Tropfenzahl) sind
> **geometrische Benetzungs-Proxys** — Indikatoren, wo das Öl hintrifft und wo es abtropft,
> nicht *wie stark* es kühlt. Für echte Kühlleistung bräuchte es Mehrphasen-CFD (OpenFOAM).

**Bedienung:** Geometrie & Ansicht (Anzahl Nuten; **Ansicht** *Ausschnitt* = schmaler Keil oder
*Gesamt* = voller 360°-Kern; **👁 Anzeigen** = welche Bauteile gebaut werden — Wickelkopf/Rotor/
Stator/Welle/Magnete; **✂ Schneiden** = welche davon aufgeschnitten werden, der Rest bleibt ganz);
**Darstellung & Einbaulage** (**Einbaulage** horizontal/vertikal, **Nahaufnahme** an/aus,
**🐢 Zeitlupe** bis **500×**); Kühlring (**Öldruck** in bar, Anzahl Düsen, Bohrungs-Ø, Abstand
Ring→Wickelkopf, Ring-Rohr-Ø); **🎯 Strahlrichtung** (**axiale Neigung** + **tangentialer Schwenk**
in Grad, **🔴 Ziellinie einzeichnen**); Öl-Stoffwerte (Viskosität/Oberflächenspannung);
Domain-Auflösung + Framezahl + Render-Engine + **⚡ Schnelle Darstellung** (grobe Vorschau) →
**💧 Spritzöl-Simulation starten**.
Über **👁 Anzeigen** blendet man Bauteile ganz aus (z. B. nur Wickelkopf + Stator), über
**✂ Schneiden** legt man fest, welche davon aufgeschnitten werden: im *Ausschnitt*-Modus wird ein
geschnittenes Bauteil auf das schmale Tortenstück reduziert, im *Gesamt*-Modus wird aus dem vollen
Ring ein Tortenstück **herausgeschnitten** (klassischer Cutaway); nicht geschnittene, nur angezeigte
Bauteile bleiben als voller Ring stehen. (Der Wickelkopf wird aus Rechenzeitgründen immer nur über
den Ausschnitt gebaut.)
Die **🎯 Strahlrichtung** neigt/schwenkt den Strahl gegenüber der automatischen (immer auf einen
echten Leiter gerichteten) Grundrichtung; die **🔴 Ziellinie** zeichnet je Düse eine leuchtende Linie
ins Video, sodass sofort sichtbar ist, wohin der Strahl zeigt und ob er die Wickelköpfe trifft.
Mit **🔍 Vorschau (Strahllinien, ohne Bake)** lässt sich das **vorab in einer Zwischenansicht** prüfen:
es wird in wenigen Sekunden **ein Standbild** aus Geometrie, Düsen und den 🔴 Strahllinien gerendert —
**ohne** die aufwändige Fluidberechnung. Passt die Richtung, startet man darunter den vollen Lauf.
Über das Feld **🔄 Drehteller** (1 / 12 / 24 / 36 Winkel) neben dem Knopf wird die Vorschau aus
mehreren Kamerawinkeln rund um die Motorachse gerendert; das Bild lässt sich dann per **Ziehen mit der
Maus** (oder dem Schieberegler) **frei drehen** — so kann man das gerenderte Ergebnis von allen Seiten
betrachten. (Mehr Winkel = etwas längere Render-Zeit. Das fertige Fluid-Video bleibt bei fester Kamera.)

In der Karte **🎨 Ansicht & Darstellung** stellt man ein, **welche Achse nach unten zeigt** (Blickrichtung —
die Schwerkraft/Physik steuert weiterhin die Einbaulage), ob das **🧭 Koordinatensystem** (X rot · Y grün ·
Z blau, Z = Motorachse; in der Vorschau immer eingeblendet) auch im Video erscheint, ob die **Vorschau mit
Materialien** (Kupfer-Leiter, Stahl-Ring, transluzentes Öl) statt flach gerendert wird, ob die **Kanten
geglättet** werden (Shade Smooth — die Facetten der Netzdarstellung verschwinden) und wie **transparent das
Öl** dargestellt wird. Materialien + Koordinatensystem machen die Drehteller-Rotation deutlich besser erkennbar.
Die **Einbaulage** bestimmt die Schwerkraftrichtung **und die Ansicht**: **horizontal** (Motorachse
waagerecht, übliche Einbaulage) lässt das Öl **seitlich** über die Wickelköpfe ablaufen; **vertikal**
stellt die Motorachse aufrecht — das Öl läuft **entlang der Achse** nach unten ab (deutlich sichtbar
anders).
Mit **Nahaufnahme** wird **ein** Strahl aus **einer** Düse im Detail gezeigt, wie er **auf einen
Leiter** trifft und zerstäubt (statt der Übersicht mit allen Düsen); jede Düse wird dabei automatisch
**auf einen echten Wickelkopf-Leiter ausgerichtet** (Ziel knapp unter der Kronenspitze), sodass der
Strahl sichtbar auf dem Kupfer landet.
Die **🐢 Zeitlupe** (5×–500×) streckt die Simulationszeit pro Frame — wie eine Hochgeschwindigkeits­
kamera zeigt das Video dann Strahlflug, Aufprall und Tröpfchenbildung im Detail (in Echtzeit quert
der ~21-m/s-Strahl den Spalt in 1–2 Frames). Bei starker Zeitlupe ggf. mehr Frames wählen, sonst ist
der gezeigte reale Zeitausschnitt sehr kurz.
Die **⚡ Schnelle Darstellung** schaltet auf ein flaches, schnelles Rendern (weniger Substeps, keine
Sekundärpartikel) — ideal, um Richtung/Auflösung/Ausschnitt auszuprobieren, bevor man einen feinen
Lauf startet (gröber, weniger Tröpfchen-Detail).
Die **Strahlgeschwindigkeit folgt aus dem Druck** (3 bar ≈ 21 m/s). Nach dem Lauf erscheinen ein
**Video** (Öl spritzt aus dem Ring auf die Leiter und zerstäubt), eine **Benetzungs-Heatmap** und
Zeitverläufe von Benetzung und Tropfenzahl. Der Lauf lässt sich **abbrechen**.
**Speichern & Wiederladen:** Jeder fertige Lauf wird **automatisch als eigene Variante im aktiven
Projekt gespeichert** (Video, Kennwerte, Charts) — ein neuer Lauf **überschreibt die vorherigen nicht**.
Unter **„🎞 Gespeicherte Läufe (Varianten)"** sind alle Läufe gelistet und lassen sich ohne Neurechnen
**ansehen** (📼) oder **löschen** (🗑). **„📼 Gespeicherten Lauf laden"** holt den zuletzt gespeicherten
Lauf zurück; beim Öffnen des Tabs wird er automatisch angezeigt.
**Zoomen im Video:** Mausrad über dem Video zoomt (bis 8×), gezoomtes Bild mit der Maus verschieben,
Doppelklick oder ⟲ setzt zurück (🔍±-Knöpfe unter dem Video). Bei 100 % funktionieren die normalen
Video-Bedienelemente (Play/Pause/Spulen) wie gewohnt.

> **Auflösung & feine Düsen:** Eine 1-mm-Bohrung ist bei grober Auflösung kleiner als eine
> Netz-Zelle. Für einen sauber aufgelösten Strahl die Domain-Auflösung hoch genug wählen
> (72–128; für einen wirklich scharfen Strahl **192–512**) — die Kosten wachsen aber
> ~kubisch mit der Auflösung. Hohe Auflösungen am besten mit wenigen Frames (10–30) und
> Zeitlupe kombinieren.

**Rechenaufwand:** Der FLIP-**Bake läuft auf der CPU** (die GPU beschleunigt nur das
Rendern) — Auflösung × Frames ist der Haupt-Kostentreiber; ein Ausschnitt hält es im
Minuten-Bereich. **Voraussetzung:** ein **portabler blender.org-Build** (der Ubuntu-`apt`-
Build stürzt bei der Fluidsimulation headless ab — siehe README/Voraussetzungen); fehlt er,
meldet der Server einen Installationshinweis.

---

### Tab 📊 FEM-Ergebnisse

Erst nach einem Lauf verfügbar (vorher ausgegraut). Unter-Reiter:

| Reiter | Inhalt |
|---|---|
| **EM-Feld** | Feldanimation mit Drehzahl-/Modus-Auswahl (Rotation / Ankerrückwirkung / Last-Rampe). Farbskala in Tesla + Legende. Videos pro Modus abrufbar |
| **CAD-Modell** | 2D-Schnittbilder (isometrisch, Draufsicht, Seite) mit Geometrie-Umrissen, Magnet-Konturen, Bolzenlöchern, Flussbarrieren |
| **Luftspalt** | B_r und B_t über dem Umfang (B_r = robust/exakt, B_t = Näherung, gestrichelt) |
| **EM-Kennlinie** | Drehmoment, Leistung, EMK, Wirkungsgrad über der Drehzahl. MTPA-Strom (salient: i_d < 0 für Reluctance-Moment) |
| **Festigkeit** | Von-Mises-Spannung, Sicherheitsfaktor, Knotenanzahl. FEM-deratierte max. sichere Drehzahl |
| **Verformung** | Hochauflösende Verformungsbilder bei Nennlast / Maximaldrehzahl / Berstdrehzahl + Verformungsvideo (rpm-Rampe). Bei FEM-Fehler: analytische Lamé-Verformung (rotationssymmetrisch, als glatter Annulus dargestellt) |
| **Wellenverbindung** | Analytische Bewertung der gewählten Verbindung: Fugenpressung / Flankenpressung, übertragbares Moment, Lösedrehzahl (Pressverband) bzw. Drehmomentkapazität (Keilwelle/P3G) |
| **Temperatur** | Stationäre Temperaturen + transientes Aufheizen über 30 min; Verluste (Kupfer, Eisen, Magnet-Wirbelstrom, mechanisch); Zeitkonstanten |
| **Fahrzyklen** | Je gewähltem Zyklus: Geschwindigkeits-/Drehzahl-/Momentprofil, Energiebilanz, thermische Bewertung (Spitzentemperaturen pro Zyklus) |

Buttons im Ergebnis-Tab:
- **🔧 FreeCAD** — öffnet das gespeicherte `motor.FCStd` im GUI-FreeCAD.
- **📦 STEP** — STEP-Datei herunterladen.

#### Stufen nachrechnen

Im Ergebnis-Tab gibt es einen aufklappbaren Bereich **🔁 Stufen nachrechnen**. Damit
kannst du einzelne Pipeline-Stufen selektiv nachholen, ohne die gesamte Analyse neu zu
starten — z. B. nur die Thermik oder nur den Fahrzyklus nachrechnen, wenn du die
Kühlung oder den Zyklus geändert hast. Wählbare Stufen: Magnetfeld / Strukturanalyse /
Thermik / Fahrzyklus. Die bestehende Geometrie (`motor.FCStd`) wird wiederverwendet.

#### Ergebnis-Bewertung

Unter den Ergebnissen: **Bewertung gut/schlecht** — Daumen hoch/runter + optionaler
Kommentar. Die Bewertung fließt in ein fortlaufendes **LLM-Trainingsfile**
(`~/cae_projekte/_training/dataset_sft.jsonl`), das automatisch bei jedem
Analyselauf aktualisiert wird. Es gibt auch einen automatischen Label-Vorschlag
(Heuristik auf Basis der Kennwerte).

**Vorsortierung der KI-Entwürfe:** Von der KI erzeugte Maschinen (Tab Designer →
🤖 KI entwerfen) werden direkt **automatisch mit gut/schlecht vorsortiert** (anhand
derselben Heuristik) und so im Trainingsfile abgelegt — der Status zeigt dann
„vorsortiert (Heuristik): …". Eine manuelle Bewertung überschreibt die Vorsortierung
und bleibt auch beim Nachrechnen erhalten. Jede Zeile des Trainingsfiles hat dasselbe
einheitliche Schema (u.a. `label`, `label_source` = `user`/`auto`, `auto_label`,
`design_source` = `hand`/`ki`); die Übersicht im Vergleich-Tab zählt manuell vs.
KI-vorsortiert getrennt.

---

### Tab ⚖ Vergleich

#### Varianten

- **Varianten zusammenstellen** über „＋ Geometrie merken" (Geometrie-Tab) oder
  manuell über „Aktuelle Konfig hinzufügen".
- **Export/Import** als `*.emavars.json`-Datei (Schemata-Format mit bis zu 10
  Varianten).
- **Auf dem Server speichern/laden/löschen** (persistiert unter
  `~/cae_projekte/_variants/`).
- **„Alle ausführen"** — rechnet alle Varianten sequentiell als Batch und erstellt
  Ergebnisse für jede.

#### Projektvergleich

1. Bis zu **10 Projekte** aus der Liste anwählen.
2. **Vergleich starten** → überlagerte Kennlinien (EM, Thermik, Energie),
   gruppierte Balkendiagramme, Vergleichstabelle.

#### Parameter-Tabelle (Spalten-Variation)

Tabellarischer Editor: Spalte 1 = Baseline aus dem aktuellen Formular, bis zu 10
weitere Spalten mit geänderten Parametern. **„Alle Spalten rechnen"** → sequentielle
Berechnung, Ergebnisse werden automatisch in den Vergleich übernommen.

Standardmäßig stehen die **26 Hauptparameter** in der Tabelle. Das Kästchen
**„Feinparameter zeigen"** blendet 22 weitere ein: Leiter je Nut, Nutbreitenverhältnis,
Magnetlagen und -abstand, Polbedeckung, Magnete je Pol, zweiter V-Winkel, Asymmetrie,
Tangentiallänge, Klebespalt, Magnetisierungsrichtung, Taschendefinition, Flusssperren
und Wuchtbohrungen. Sie sind bewusst zugeklappt, weil die meisten davon **nur für
bestimmte Topologien** wirken — welche, steht jeweils in der Zeilenbeschriftung
(z. B. „Polbedeckung … (nur spm, halbach)").

#### Vergleichsbericht (PDF)

| Modus | Beschreibung |
|---|---|
| **Standard** | LLM schreibt Prosa um deterministische Tabellen (Parameter-Tabelle mit ●-Markierung für abweichende Werte, Kennwert-Tabelle, Einfluss-Analyse Δ%) |
| **Agentisch (6-Experten-Recherche)** | Deterministisches Skelett (Methodik, alle Tabellen, Overlay-Charts, Bild-Galerien pro Variante) + 6 Experten vergleichen alle Varianten mit Vor-/Nachteilen. Deterministische Sicherheitsbewertung (FEM SF ≥ 1,5, Magnet ≤ 150 °C, Wicklung ≤ 180 °C) |

Der **LLM-Modell** für den Bericht ist im Vergleich-Tab wählbar (qwen-gross:latest /
qwen3.8:latest / gemma4:26b / andere installierte Ollama-Modelle).

Die **LLM-Trainingsdaten** (Übersicht, Download als SFT-/VLM-JSONL) liegen zentral im
Tab **① Projekt** unter „🧰 Globale Werkzeuge & Daten".

---

## 4. Spezialfunktionen

### 🧠 Text → Auslegung (Tab Geometrie)

Beschreibe die Anwendung in eigenen Worten (z. B. Leistung, Drehzahl, Drehmoment,
Bauraum, Kühlung, Effizienz/Kosten). Das LLM leitet einen vollständigen,
validierten Parametersatz ab:

1. Werte werden serverseitig auf gültige Bereiche geklemmt.
2. Radiale Konsistenz erzwungen (statorOD > statorID > rotorOD > Welle, ~0,7 mm
   Luftspalt, Nuten ≈ 6·p).
3. Falls Referenzmaschinen in der RAG-Wissensbasis liegen, werden sie als Kontext
   herangezogen (`rag_used` im Ergebnis sichtbar).
4. Begründung + Parameter angezeigt → **„In Formular übernehmen"**.

Danach kannst du alles feinjustieren und rechnen.

### 🎯 Zielwertoptimierung (Tab Berechnung)

LLM-gesteuerte Suche nach einem guten Design:

1. **Ziel** wählen (Kennwert maximieren / minimieren / Zielwert), z. B. „Maxwell-Moment
   maximieren" oder „Masse minimieren".
2. **Randbedingungen** festlegen (z. B. `T_Magnet ≤ 130 °C`,
   `max. sichere Drehzahl ≥ 18000`).
3. **Freie Parameter** ankreuzen und **Bereiche (von–bis)** angeben (Magnetlänge,
   -dicke, -winkel, Position, Steg, Nuttiefe, Polpaare, Blechlänge, Luftspalt,
   Magnet-Luftspalt, Asymmetrie …).
4. **Budget** (Anzahl Auswertungen) setzen, **starten**.

Jeder Kandidat wird mit dem **schnellen Analytik-Evaluator ohne FreeCAD/FEM** (~0,5 s)
bewertet; das LLM schlägt anhand der Historie neue Kandidaten vor, Zulässigkeit und
Bewertung rechnet das Programm deterministisch. Am Ende: bester **zulässiger** Treffer →
**„Parameter übernehmen"** (ins Formular) oder **„Übernehmen & Voll-Analyse"** (sofort
kompletter Lauf inkl. FEM auf dem Gewinner).

### 🤖 KI-gestützte Auslegung (Tab Designer)

Der **parallele KI-Pfad** im Designer-Tab — eine durchgängige, KI-gestützte
E-Maschinen-Auslegung: **Bereiche/Beschreibung → KI zeichnet komplette Varianten →
vergleichen → Magnete fein-optimieren → Parameterstudie**, alles auf der frei gezeichneten
Geometrie. Ausführlich beschrieben unter *Tab ✏ Designer (Canvas)* → **🤖 KI entwerfen**,
**🎯 Magnete fein-optimieren** und **📈 Parameterstudie für diesen Entwurf**. Im
Unterschied zu **🧠 Text → Auslegung** (füllt nur das Formular mit einer parametrischen
Standard-Topologie) entwirft der KI-Pfad auch die **frei platzierten Magnete und
Flussbarrieren** und speichert jeden Lauf als Trainingsdatensatz.

### 📂 Projekt-Browser (Tab ① Projekt → „Galerie ⤢")

Galerie aller Projekte unter `~/cae_projekte/` mit:

- **Querschnitts-Vorschau** (Thumbnail + hochauflösendes EM-Feldbild zum Anklicken)
- **Topologie, Abmessungen und Kennwerte** (Kt, Moment, max. Drehzahl, T_Magnet,
  Verluste, Verbrauch)
- **Status-/Abstammungs-/Verknüpfungs-Badges** (aus der Projektakte)
- **Suchfeld** + Filter „nur mit Ergebnissen"

Aktionen pro Karte:

| Button | Funktion |
|---|---|
| **Ergebnisse ansehen** | Projekt laden (ohne Neuberechnung) → Ergebnis-Tab |
| **📋 Als Vorlage verwenden** | Alle Eingabeparameter ins Formular übernehmen (Geometrie, Material, Drehzahlen, Fahrzeug, Anhänger, Struktur-/Feldeinstellungen) → Geometrie-Tab; dort anpassen und neu rechnen |
| **📁 Klonen** | Ganzes Projekt (Eingaben + Notizen + Projekt-Wissensbasis) duplizieren, mit vermerkter Abstammung — ohne die schweren Ergebnisse |
| **⬇ Bundle exportieren** | Projekt als `.emaproj`-Zip herunterladen; **📦 Import** (im Projekt-Tab) lädt ein solches Bundle wieder als neues Projekt hoch |
| **📄 Bericht öffnen** | PDF-Bericht anzeigen (nur wenn vorhanden) |
| **🗑 Löschen** | Projekt entfernen |

Ältere Projekte ohne gespeicherten Eingabesatz: Geometrie + Kernparameter werden aus
den Metadaten rekonstruiert.

### 📚 Wissensbasis / RAG

Eine lokale Wissensbasis (Retrieval-Augmented Generation), Embeddings über Ollama
(`nomic-embed-text`). Es gibt **zwei Ebenen**:

- **Globale Wissensbasis** (`~/cae_projekte/_rag/index.json`, Tab ① Projekt →
  „🧰 Globale Werkzeuge & Daten" → **📚 Wissensbasis öffnen**) — projektübergreifende
  Referenzmaschinen und Dokumentation. Speist **Text → Auslegung**, **🤖 KI entwerfen**
  (Designer-Tab) und den **Ergebnis-Chat**.
- **Projekt-Wissensbasis** (`<Projekt>/rag/index.json`, Tab ① Projekt → aktives Projekt
  → „📎 Projekt-Dokumente") — projektspezifische Quellen, die zusätzlich zur globalen
  Basis in Chat & Bericht *dieses* Projekts einfließen.

Beide funktionieren **best-effort** — ohne Ollama/Embeddings läuft alles weiter, nur
ohne Kontext-Anreicherung.

#### Dokumente verwalten (globale Basis)

| Aktion | Beschreibung |
|---|---|
| **Text hinzufügen** | Freitext einfügen (z. B. Datenblatt-Auszüge, Geometrie/Kennwerte guter Maschinen, technische Notizen). Optionaler Titel und Tag |
| **Datei(en) hochladen** | txt, md, csv, PDF — Mehrfachauswahl möglich. PDFs werden automatisch mit `pypdf` extrahiert |
| **Löschen** | Mehrfachauswahl (Checkboxen) → „Ausgewählte löschen" |
| **Suchen** | Volltextsuche über alle Dokumente (Cosine-Ähnlichkeit auf Embeddings via `nomic-embed-text`) |

**Tag** (optional): freier Text (z. B. „Maschine", „Doku"). Dient der Organisation,
hat aber keinen Einfluss auf die Suche.

### 💬 Ergebnis-Chat (Button unten rechts)

Stellt Fragen zum **aktuell geladenen Projekt** oder — wenn der Vergleich-Tab aktiv ist
und ≥ 2 Projekte angehakt sind — zum **Vergleich**. Antworten stützen sich auf:

- Die echten Ergebniszahlen des Projekts.
- Einen automatisch erstellten „Maschinen-Datenblatt" (Topologie, Abmessungen,
  Wicklung, Magnete, Materialien, Betriebspunkt — aus `meta.json`).
- RAG-Kontext aus der Wissensbasis (best-effort).

Benötigt Ollama.

### Bedienung ohne Browser: Kommandozeile und Agent

Alles, was die Oberfläche kann, hängt an HTTP-Routen auf `:5000`. `cae_cli.py` macht sie
von der Kommandozeile aus bedienbar — gedacht für Skripte **und** für ein lokales
Sprachmodell, das die Toolkette selbst bedient.

```bash
cd ~/ai-workspace/cae_orchestrator
python3 cae_cli.py health                      # laeuft der Server?
python3 cae_cli.py projects                    # Projekte auflisten
python3 cae_cli.py results --project last --sections    # welche Abschnitte gibt es?
python3 cae_cli.py results summary --project last      # Kennwerte des juengsten Projekts
python3 cae_cli.py run analyse --from-project last --wait
```

**Varianten rechnen, ohne den Payload zu schreiben.** Ein Lauf braucht rund 90 Schlüssel;
statt sie zusammenzusetzen, erbt man eine gerechnete Auslegung und ändert einzelne Werte:

```bash
python3 cae_cli.py run cad --from-project last --dry-run \
        --set slotDepth=30 --set p=8 --set magShape=v          # erst zeigen …
python3 cae_cli.py run analyse --from-project last --wait \
        --set slotDepth=30 --set project_name=Variante_A       #  … dann rechnen
```

`--set` prüft gegen dieselbe Parameterliste, die auch die Parameter-Tabelle speist
(`/param_schema`): 26 Hauptparameter + 22 Feinparameter, jeweils mit Typ, Grenzen und
Auswahlliste. **Grenzverletzungen werden abgewiesen, nicht geklemmt** — ein geklemmter
Wert sähe wie ein angenommener aus, und der Bericht rechnete dann eine andere Maschine
als die bestellte. Unbekannte Namen fallen mit Tippfehler-Vorschlag durch:

```
FEHLER: poleArkFrac steht weder im Schema noch im Grundpayload — gemeint war poleArcFrac?
FEHLER: magLayers: 5 liegt ueber der Obergrenze 4
```

`python3 cae_cli.py raw GET /param_schema` zeigt alle Parameter samt Beschreibung. Bei
den Feinparametern steht dort auch die **Topologiebindung** (`poleArcFrac` wirkt nur bei
`spm`/`halbach`, `magLayers` nur bei `pmasynrm`, `magAsym` nur bei `vasym` …) — auf einer
anderen Topologie wird der Wert angenommen und tut nichts.

**Mit Sprachmodell:** ein Skript in der Repo-Wurzel startet Server und Agent zusammen.

```bash
cd ~/ai-workspace
./start_agent.sh                              # interaktive Sitzung
./start_agent.sh -p "Wie hoch ist B_gap im neuesten Projekt?"
./start_agent.sh --weiter                     # letzte Sitzung fortsetzen
./start_agent.sh --sitzungen                  # Sitzungen auflisten
./start_agent.sh --sitzung 01a01998           # eine bestimmte fortsetzen
```

Ohne Flagge wird **nicht** fortgesetzt, sondern frisch gestartet — nur ein Hinweis auf
die letzte Sitzung erscheint. Das ist Absicht: sonst schleppt jede neue Frage den Verlauf
der vorigen mit. Einrichtung und Hintergrund in `.agents/README.md`.

---

## 5. Berechnungsmethoden (Kurzfassung)

| Domäne | Methode | Details |
|---|---|---|
| **Elektromagnetik (2D)** | 2D-FDM (Finite-Differenzen, skalares Vektorpotential `∇·(ν∇A)=−J`) | Direkter Sparse-Solver (`scipy splu`), Cache pro Geometrie; AMG-Solver (`pyamg`) für > 2500 px. Magnete = Äquivalent-Randströme; Eisen µr=500; nichtlineare Sättigung als Display-Nachbearbeitung. Split-Kalibrierung (Magnet + Stator getrennt skaliert) |
| **Elektromagnetik (3D, optional)** | 3D-FEM (Elmer, Gmsh-Netz, Kantenelemente) | Magnetostatik (`WhitneyAVSolver`, MUMPS-Direktlöser); Magnete via Magnetisierung Br/µ0; echte finite Länge → Endeffekte + Skew + 2D-Vergleich. v1: linear, Open-Circuit. Eigener On-Demand-Job (Tab „🧲 3D-Feld") |
| **Leistung** | Analytisch (dq-Modell, MTPA, Feldschwächung) | Drehmoment, EMK, Verluste, Wirkungsgrad über der Drehzahl |
| **Strukturmechanik** | 3D-FEM (CalculiX, Gmsh-Netz) | Einmalig bei Maximaldrehzahl; Verformung/Spannung bei anderen Drehzahlen via rpm²-Skalierung (Fliehkraft ∝ ω²). Berstdrehzahl = rpm bei SF→1. Nur der Rotor wird vernetzt |
| **Thermik** | 0D-LPTN (6-Knoten-Netzwerk) | Stationär + transient 30 min; kühlungsabhängige h-Werte |
| **Fahrzyklus** | Analytisch (Antriebsstrangmodell) | Geschwindigkeit → Fahrwiderstände → Motorbetriebspunkt → Verluste/Temperatur pro Zeitschritt |
| **Wellenverbindung** | Analytisch (Lamé, Flankenpressung) | Kein FEM; Press/Keilwelle/P3G jeweils nach Norm |
| **Geometrie** | FreeCAD (headless, Subprocess) | 3D-CAD + STEP; Marker-Protokoll |

> Ausführliche Methodik: siehe **EM_BERECHNUNG.md** und **BERECHNUNGSMETHODEN_VERGLEICH.md**.

---

## 6. Typische Laufzeiten

| Schritt | Größenordnung |
|---|---|
| Geometrie (FreeCAD) + STEP | ~10–40 s |
| EM-Feld + Animation (300 px, 36 Frames × 16 RPMs) | ~30 s – 2 min |
| Festigkeits-FEM (CalculiX, 3 mm Netz) | ~30–120 s |
| Verformungsbilder + Video | ~10–30 s |
| Thermik + Fahrzyklen | wenige Sekunden |
| Einzelbild 5000 px (Multigrid) | mehrere Minuten |
| Zielwertoptimierung (Budget 24) | ~1–2 Minuten |
| Parameterstudie (100 Schritte, ohne Feld) | ~50 s |
| Parameterstudie (100 Schritte, mit Feld 300 px) | ~5–10 min |
| PDF-Bericht (LLM) | ~30 s – 2 min |
| Vergleichsbericht agentisch (6 Experten, 4 Varianten) | ~5–10 min |
| Nur CAD ansehen (🧊) | ~10–40 s |
| Smoke-Test (🧪) | ~15 s |
| STEP-Import (Erkennung + motor.FCStd) | ~10–30 s |
| 3D-Modell-Vorschau (🧊, ohne Elmer) | ~5–15 s |
| 3D-Feld grob (Elmer, kleines Modell) | ~5–20 s |
| 3D-Feld fein (Elmer, feines Netz/große Maschine) | mehrere Minuten |

---

## 7. Tastaturbedienung und URL-Anker

| Anker | Tab / Funktion |
|---|---|
| `#projekt` | Projekt (Anlegen/Öffnen, Bericht, 3D-Läufe) |
| `#geo` | Geometrie |
| `#betrieb` | Betrieb & Material |
| `#calc` | Berechnung |
| `#live` | Live-Simulation |
| `#designer` | Canvas-Designer |
| `#import` | STEP-Import |
| `#em3d` | 3D-Feld (Elmer) |
| `#results` | FEM-Ergebnisse |
| `#compare` | Vergleich |
| `#projects` | Projekt-Browser (Galerie) |
| `#optimize` | Zielwertoptimierung |
| `#text2ema` | Text → Auslegung |
| `#rag` | Wissensbasis (RAG) |

Es gibt keinen `#report`-Anker mehr — der Bericht liegt auf `#projekt`.

---

## 8. Wo liegen meine Ergebnisse?

| Pfad | Inhalt |
|---|---|
| `~/cae_projekte/<Zeitstempel[_Name]>/` | Einzelprojekt: `motor.FCStd`, `motor.step`, `results.json`, `meta.json`, `cad_images/`, `charts/`, `frames/`, `frames_react/`, `frames_load/`, `frames_struct/` |
| `~/cae_projekte/<…>/import.step` | Beim STEP-Import: die hochgeladene Original-STEP |
| `~/cae_projekte/<…>/em3d/` | 3D-Feld (Elmer): Gmsh-Mesh, Elmer-Mesh, `case.sif`, `results/case_t0001.vtu` (ParaView) |
| `~/cae_projekte/_comparisons/` | Vergleichsberichte |
| `~/cae_projekte/_variants/` | Gespeicherte Variantensätze (JSON) |
| `~/cae_projekte/_rag/index.json` | RAG-Wissensbasis (Dokumente + Embeddings) |
| `~/cae_projekte/_training/dataset_sft.jsonl` | LLM-Trainingsfile (automatisch aktualisiert) |
| `~/cae_projekte/_training/dataset_vlm.jsonl` | VLM-Trainingsfile (Bilder + Text, für Vision-Finetuning) |
| `~/cae_projekte/_paramstudy/` | Parameterstudie-Ergebnisse (Bilder, Video, CSV) |

---

## 9. Fehlersuche

| Problem | Lösung |
|---|---|
| **„FreeCADCmd nicht gefunden"** | Pfade in `start.sh`, `freecad_runner.py` und `server.py` prüfen (siehe README, „Pfade anpassen"). Es muss der **1.1.x-Quellcode-Build** sein, nicht `/opt/freecad-1.1` |
| **Bericht / Chat / Text→Auslegung / Optimierung reagiert nicht** | Ollama läuft nicht: `ollama serve` starten; Modell prüfen: `ollama list` (benötigt `qwen-gross:latest`; ein anderes lässt sich ohne Codeänderung über `CAE_LLM_MODEL` setzen, die Kontextlänge über `CAE_LLM_NUM_CTX`). Für Wissensbasis/RAG-Embeddings: `nomic-embed-text` (`ollama pull nomic-embed-text`) |
| **PDF-Bericht schlägt fehl** | `pandoc` und `pdflatex` installieren: `sudo apt install pandoc texlive-latex-base texlive-fonts-recommended texlive-latex-extra` |
| **Magnete „fehlen" im Querschnitt** | Bei Oberflächen-Topologien (SPM/Halbach) gibt es keine Taschen — das ist korrekt (Magnete sitzen auf der Oberfläche) |
| **Magnete laufen sehr heiß / sehr kalt** | Kühlung, Last und Drehzahl prüfen. Die Magnete sind thermisch an die Statorbohrung gekoppelt (Wärmeeintrag aus dem Kupfer) |
| **Einzelbild 5000 px abgelehnt** | `pyamg` fehlt → ohne es ist die Vorschau auf 2500 px gedeckelt. `pip install pyamg` (im venv) |
| **5000-px-Bild dauert / braucht RAM** | Normal: Multigrid-Solver, mehrere Minuten, ~15 GB Spitzen-RAM |
| **FEM „Rotor nicht gefunden"** | Wenn „Rotor-Blechpaket" in den Komponenten abgewählt ist, gibt es keinen Rotor zum Vernetzen → Strukturanalyse wird übersprungen |
| **Verformung zeigt „analytisch"** | Bei aggressiven Multi-Layer-Topologien mit dünnen Eisenbrücken schlägt die FEM-Vernetzung gelegentlich fehl → automatischer Fallback auf die analytische Lamé-Lösung (axisymmetrisch, ohne Magnettaschen) |
| **Bohrungen/Flussbarrieren fehlen im Feldbild** | Prüfen, ob die Checkboxen in „Komponenten" aktiviert sind. Die Löcher werden sowohl im 3D-CAD, 2D-Schnitt, Live-Vorschau als auch in der FDM-Simulation (Magnetfeld) berücksichtigt |
| **Smoke-Test schlägt fehl** | `python3 smoke_test.py` im Terminal ausführen und die Fehlermeldung lesen. Häufig: fehlende Abhängigkeit (`pip install -r requirements.txt`) oder falscher FreeCAD-Pfad |
| **„3D-Feld berechnen" meldet Installationshinweis** | Elmer fehlt: `sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa && sudo apt install -y elmerfem-csc`. Die „🧊 3D-Modell ansehen"-Vorschau funktioniert auch ohne Elmer |
| **3D-Feld: Magnete/Pole stimmen nicht** | Skew/Maße prüfen. Bei sehr großen Magneten können sich die Rechteck-Pockets an Polgrenzen leicht schneiden (grobe v1-Geometrie) — gröberes/feineres Netz oder kleinere Magnete probieren |
| **3D-Moment ist nicht 0 im Leerlauf** | Erwartet: v1 ist Open-Circuit, das Netto-Moment ist physikalisch ≈ 0; der Arkkio-Wert ist am groben Netz verrauscht und nur informativ |
| **STEP-Import erkennt Magnete falsch** | Heuristik — im Designer korrigieren (Magnete verschieben/löschen, Polung setzen). Voller Motor (mit Stator/Wicklung) wird unterstützt; Achse = Z angenommen |
| **Autosave stellt alte Werte wieder her** | Manuell zurücksetzen: Browser-Console → `localStorage.removeItem('ema_form_state')` oder neuer Analyselauf (löscht den Session-Stand) |

---

## 10. Zusammenfassung der Pipeline-Stufen

```
┌─────────────────────────────────────────────────────────────────┐
│ ① GEOMETRIE                                                     │
│    FreeCAD: Stator + Rotor + Magnettaschen + Hairpins +         │
│    Wickelköpfe + Welle + opt. Lager/Isolation/Bolzen/Barrieren  │
│    → motor.FCStd + motor.step + CAD-Bilder                      │
├─────────────────────────────────────────────────────────────────┤
│ ② EM-FELD (statisch)                                            │
│    2D-FDM bei Rotorwinkel 0° (open-circuit + Lastpunkt)         │
│    → Luftspaltprofil Br(θ), Kalibrierungsfaktor sf_ref          │
├─────────────────────────────────────────────────────────────────┤
│ ③ FELD-ANIMATION                                                │
│    Pro RPM × N Frames: FDM mit Statorströmen (MTPA/FW)          │
│    + opt. Ankerrückwirkung + Last-Rampe                          │
│    → Frames (base64 + Disk) + Videos (mp4)                      │
├─────────────────────────────────────────────────────────────────┤
│ ④ EM-KENNLINIE                                                  │
│    Analytisch über den Drehzahlbereich:                          │
│    Drehmoment, Leistung, EMK, Verluste, Wirkungsgrad            │
├─────────────────────────────────────────────────────────────────┤
│ ⑤ FLIEHKRAFT-FEM                                                │
│    CalculiX: einmalig bei RPM_to (Gmsh-Netz, nur Rotor)         │
│    → σ_vM, Verschiebung, SF, Berstdrehzahl                      │
│    FEM-Derating der analytischen max. sicheren Drehzahl          │
├─────────────────────────────────────────────────────────────────┤
│ ⑥ VERFORMUNG                                                    │
│    rpm²-Skalierung → Bilder bei Nennlast/RPM_to/Berst           │
│    + Verformungsvideo (0→max)                                    │
├─────────────────────────────────────────────────────────────────┤
│ ⑦ STRUKTURKENNLINIE                                             │
│    Analytisch (Lamé-Sweep), FEM-deratiert                        │
│    → max. sichere Drehzahl (SF ≥ 1,5)                            │
├─────────────────────────────────────────────────────────────────┤
│ ⑧ WELLENVERBINDUNG                                              │
│    Analytisch (Press/Keilwelle/P3G)                              │
│    → Fugenpressung, Moment, Lösedrehzahl                         │
├─────────────────────────────────────────────────────────────────┤
│ ⑨ THERMIK                                                       │
│    6-Knoten-LPTN: stationär + transient 30 min                   │
│    → T_Wicklung, T_Magnet, T_Rotor, T_Stator, T_Welle           │
├─────────────────────────────────────────────────────────────────┤
│ ⑩ FAHRZYKLUS                                                    │
│    WLTP / Autobahn / Anhänger / CSV                              │
│    → Energiebilanz + thermische Bewertung pro Zyklus             │
└─────────────────────────────────────────────────────────────────┘
```

Jede Stufe ist fehlertolerant: ein Fehler in einer Stufe wird geloggt, die restlichen
laufen weiter. Über **🔁 Stufen nachrechnen** können einzelne Stufen selektiv
nachgeholt werden, ohne die ganze Pipeline neu zu starten.
