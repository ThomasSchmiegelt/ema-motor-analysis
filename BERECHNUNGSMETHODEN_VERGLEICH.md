# Berechnungsmethoden — Erklärung und Vergleich mit Abaqus & Ansys Motor-CAD

Dieses Dokument erklärt, **welche Berechnungsverfahren** dieses Werkzeug für die
Auslegung von IPM-Maschinen einsetzt, und ordnet sie **ehrlich** gegenüber den
Industrie-Standardwerkzeugen **Abaqus** (allgemeine FEA) und **Ansys Motor-CAD**
(dedizierte E-Maschinen-Auslegung) ein.

> Kurzfassung: Dieses Tool ist ein **schnelles Vorauslegungs- und Lehrwerkzeug**.
> Es benutzt teils dieselben Methodenklassen wie die kommerziellen Tools (echtes
> FEM für die Festigkeit, ein Lumped-Parameter-Thermonetzwerk wie Motor-CAD), aber
> in **vereinfachter, weitgehend linearer** Form mit teilweise empirisch verankerten
> Verlustmodellen. Es ersetzt **keine** validierte Auslegung in Motor-CAD/Abaqus,
> sondern dient dem schnellen Durchrechnen vieler Varianten *vor* dem Detail-Tool.

---

## 1. Überblick: Methode je Domäne

| Domäne | Dieses Tool | Abaqus | Ansys Motor-CAD |
|---|---|---|---|
| **Elektromagnetik** | 2D-**Finite-Differenzen** (FDM), magnetostatisch, linear + optionale B-H-Sättigung; analytische Drehmoment-/EMK-Kennwerte | (kein nativer Nieder­frequenz-EM-Solver; gekoppelt mit Maxwell/Opera) | 2D-**FEA** (magnetostatisch + transient) + Analytik, der Branchen­standard |
| **Festigkeit (Rotor)** | 3D-**FEM** linear-elastisch (CalculiX), Fliehkraft, ein Lastfall, lineare Tets; analytischer Lamé-Fallback | 3D-**FEM** voll nichtlinear (Plastizität, Kontakt, Ermüdung, Modal/NVH) | Analytik + **FEA**-Rotorspannung |
| **Thermik** | 6-Knoten-**LPTN** (stationär + transient) | 3D-**FE-Wärmeleitung**/CHT | detailliertes **LPTN** (Branchenstandard) + CFD-kalibrierte Korrelationen |
| **Welle-Nabe-Verbindung** | **analytisch** (Lamé-Schrumpfsitz / Keilwelle / Polygon) | 3D-FEM mit Kontakt + Vorspannung | analytisch + FEA |
| **System / Fahrzyklus** | quasistatische Antriebsstrang- + Energie­integration (WLTP-3b u.a.) | — (kein Fahrzeug-System) | **Lab**/Duty-Cycle, Wirkungsgradkennfelder |
| **Bericht** | lokales LLM (Text), keine Rechenmethode | — | integrierte Reports |

---

## 2. Die Verfahren im Detail (dieses Tool)

### 2.1 Elektromagnetik — 2D-Finite-Differenzen-Methode (`ema_analysis.py`)

- **Modellgleichung:** magnetostatisches Vektorpotenzial $A_z$ in 2D,
  $$\nabla\cdot(\nu\,\nabla A) = -J$$
  mit Reluktivität $\nu = 1/\mu$ und Stromdichte $J$ (Quelle).
- **Diskretisierung:** Finite-Volumen-5-Punkt-Operator auf einem **kartesischen
  Gitter** (UI: 100–800 px), **harmonisches Mittel** der Flächen-$\nu$ an
  Material­grenzen, **Dirichlet** $A=0$ am 10-%-Luftrand.
- **Löser:** **direkte dünnbesetzte LU-Faktorisierung** (`scipy splu`), nach
  `(N, hash(µ))` zwischengespeichert und über alle Drehzahlen/Stromwinkel
  wiederverwendet; oberhalb ~2500 px **algebraisches Mehrgitter** (`pyamg`, CG).
- **Magnete:** als **äquivalente Oberflächen-(Rand-)Ströme** modelliert
  (Curl der Magnetisierung). Eisen $\mu_r=500$ **linear**; optionaler
  **B-H-Sättigungs-Pass** (Fixpunkt-$\mu$-Iteration) nur für die Darstellung.
- **Kalibrierung:** das FDM-Feld wird auf die **analytische
  Luftspaltflussdichte** $B_{gap}$ skaliert; unter Last getrennte Kalibrierung
  von Magnet- und Ankerfeld.
- **Kennwerte (analytisch, aus $B_{gap}$):** Drehmoment (Maxwell-Spannungstensor /
  $BLv$), EMK, Drehmomentkonstante $K_t$, Rastmoment über das kgV von Nut-/Polzahl,
  Salienz $\xi=L_q/L_d$, MTPA-Stromwinkel, Feldschwächung, Kurzschlussstrom $I_{sc}$,
  Entmagnetisierungs­reserve.

**Charakter:** physikalisch fundiert, aber **2D** (keine Wickelkopf-/Stirnstreuung
in 3D), **linear** im Lastpfad (Sättigung nur als Display-Korrektur), Drehmoment
**analytisch verankert** statt direkt aus dem Feld integriert.

### 2.2 Festigkeit — 3D-FEM mit CalculiX (`ema_freecad.py`, `freecad_runner.py`)

- **Methode:** echte **3D-Finite-Elemente-Methode**, linear-elastisch, gelöst mit
  **CalculiX (ccx)**; Vernetzung mit **Gmsh** (Tetraeder, FreeCAD-Standard-Ordnung).
- **Last:** **Fliehkraft** als Volumenkraft $\propto \rho\,\omega^2 r$ (CalculiX
  `*DLOAD, CENTRIF`). Ein Solve bei Maximaldrehzahl; weil linear-elastisch, skalieren
  Verschiebung und von-Mises-Spannung **exakt mit $(\text{rpm}/\text{rpm}_{solve})^2$**
  → Nennlast/Maximal/Berstdrehzahl ohne Neu-Solve.
- **Vernetzt wird nur das Rotor-Blechpaket** (mit ausgeschnittenen Magnettaschen);
  Bohrung fixiert. **Stabilisierung:** `OptimizeStd` + Krümmungs­verfeinerung +
  Mindest-Elementgröße + **Retry-Leiter** über Netzfeinheiten, bis das `.frd`
  echte Verschiebungs­ergebnisse enthält.
- **Fallback:** schlägt CalculiX an aggressiven Topologien (dünne Eisenstege) doch
  fehl, liefert ein **analytisches rotierendes-Scheiben-Modell (Lamé,
  ebener Spannungszustand)** die radiale Aufweitung.

**Charakter:** gleiche **Methodenklasse** wie Abaqus/Motor-CAD-Mechanik, aber
**ein** Lastfall (nur Fliehkraft — **kein** Schrumpfsitz-Vorspannung, **keine**
Thermo­dehnung), **linear-elastisch** (keine Plastizität/Ermüdung), lineare Elemente,
Rotor-Eisen isoliert.

### 2.3 Thermik — 6-Knoten-Lumped-Parameter-Netzwerk (`ema_thermal.py`)

- **Methode:** **LPTN** (thermisches Ersatzschaltbild) mit 6 Knoten — Wicklung,
  Statoreisen, Rotoreisen, Magnete, Welle, Gehäuse (+ Umgebung als Rand).
- **Aufbau:** Wärme­leitwerte $G$ [W/K] (Nut­isolation, Kontakt/Schrumpfsitz,
  Luftspalt-Konvektion+Strahlung, Lager) und Wärme­kapazitäten $C$ [J/K]
  (Masse × spez. Wärme).
- **Lösung:** stationär = lineares Gleichungssystem $A\,T = P+b$
  (`np.linalg.solve`); transient = **impliziter Euler** ($\Delta t=5\,$s) über 30 min.
- **Verlustquellen:** Kupfer $I^2R$ (DC-Widerstand), Eisen (Bertotti-artig
  $\propto \text{rpm}\cdot B^2$), Magnet-Wirbelstrom ($\propto f^2$, mit
  Segmentierungs-$1/n^2$), Lager.

**Charakter:** **dieselbe Methode wie das Motor-CAD-Thermomodul** — aber deutlich
**grobkörniger** (6 statt vieler Dutzend Knoten) und teils **empirisch verankert**
(z.B. Magnet­wirbelstrom als Anteil der Kupferverluste). DC-Kupfer (**keine**
AC-/Proximity-Verluste).

### 2.4 System / Fahrzyklus (`ema_drivecycle.py`)

- **Quasistatische** Rückwärtsrechnung: aus dem Geschwindigkeitsprofil
  (WLTP-3b, Volllast, Anhänger-Bergfahrt, CSV) → Rad-/Motormoment & -drehzahl →
  Verlust- und Energie­integration, je Zyklus eigene transiente Thermik.

---

## 3. Vergleich mit **Abaqus**

Abaqus ist eine **allgemeine, hochgradig nichtlineare FEA-Suite** (Struktur, Thermik,
gekoppelt) — der De-facto-Standard für Festigkeits-/Lebensdauer-Nachweise.

| Aspekt | Dieses Tool | Abaqus |
|---|---|---|
| Struktur-Methode | 3D-FEM linear-elastisch (CalculiX) | 3D-FEM, **nichtlinear** |
| Material | linear, isotrop, temperatur­unabhängig | Plastizität, Anisotropie (Blechpaket!), temperaturabhängig |
| Lastfälle | nur Fliehkraft, ein Solve | Fliehkraft **+ Schrumpfsitz-Vorspannung + Thermodehnung + Kontakt**, Mehrlastfälle |
| Kontakt/Klebung | keiner (Rotor-Eisen allein) | Magnet-Klebung, Wellen-Presssitz als Kontakt |
| Elemente | lineare Tets, Auto-Netz | lineare/quadratische, anisotrope Vernetzung, Konvergenzstudien |
| Weitere Analysen | — | **Ermüdung, Modal/NVH, Bruch, Crash, Kriechen** |
| Elektromagnetik | 2D-FDM (im Tool) | **nicht** nativ (Kopplung mit Maxwell/JMAG nötig) |
| Validierung | Plausibilitäts­niveau | extensiv validiert, zertifizierungs­tauglich |
| Aufwand/Kosten | Sekunden–Minuten, frei | teure Lizenz, Experten, lange Aufsetz-/Rechenzeiten |

**Einordnung:** Für die Rotor-Fliehkraft liefert dieses Tool eine **brauchbare
Erst-Abschätzung** von Spannung, Verschiebung und Berstdrehzahl — mit demselben
Verfahren (FEM), aber ohne die für einen **Nachweis** entscheidenden Effekte
(Schrumpfsitz-Vorspannung, Thermodehnung, Plastizität, Stege-Ermüdung, anisotropes
Blechpaket). Diese gehören zu Abaqus.

---

## 4. Vergleich mit **Ansys Motor-CAD**

Motor-CAD ist das **dedizierte E-Maschinen-Auslegungswerkzeug** — methodisch dem
hier Gebauten am ähnlichsten (EMag + Thermik-LPTN + Mechanik + Duty-Cycle), nur
deutlich detaillierter und messtechnisch validiert.

| Aspekt | Dieses Tool | Motor-CAD |
|---|---|---|
| EMag-Methode | **2D-FDM**, analytisch verankertes Moment | **2D-FEA** (magnetostatisch + transient) + Analytik |
| Sättigung | linear + Display-B-H-Pass | nichtlineare B-H im Solve |
| Drehmoment/Rastmoment | analytisch (Maxwell, kgV) | aus FEA-Feld integriert (inkl. Oberwellen) |
| Verluste | Bertotti-/empirisch, DC-Kupfer | Eisen (Modell), **AC-Kupfer + Proximity**, Magnet-Wirbelstrom per FEA |
| Entmagnetisierung | analytische Reserve | FEA-Entmagnetisierungs­karte |
| Thermik | **6-Knoten-LPTN** (gleiche Klasse!) | **detailliertes LPTN**, kalibrierte Konvektions­korrelationen, Kühl-/Gehäuse­detail |
| Mechanik | analytisch + einfache FEM | analytisch + FEA-Rotorspannung |
| System | WLTP/Volllast/Anhänger | **Lab**: Wirkungsgradkennfelder, Duty-Cycles, Inverter-Kopplung |
| NVH/Akustik | — | ja |
| Validierung | Plausibilitäts­niveau | branchenweit gegen Messungen validiert |

**Einordnung:** Konzeptionell macht dieses Tool **dasselbe** wie Motor-CAD und nutzt
beim Thermik-LPTN **dieselbe Methode**. Die Unterschiede sind **Tiefe und
Validierung**: Motor-CAD rechnet das Feld per FEA (statt FDM), integriert das
Drehmoment direkt, modelliert AC-Verluste/Proximity, hat ein feineres,
korrelations­kalibriertes Thermomodell und erzeugt Wirkungsgradkennfelder. Dieses
Tool ist die **schnelle, freie Vorstufe** dazu.

---

## 5. Genauigkeit, Gültigkeit, Grenzen

**Wo dieses Tool gut ist**
- **Schnelles Variantenrechnen** und Parameterstudien (Sekunden–Minuten je Lauf).
- **Trends und Größenordnungen**: Luftspaltfeld, $K_t$, Salienz, grobe Temperaturen,
  Fliehkraft-Spannung/Berstdrehzahl, Reichweite/Verbrauch.
- **Lehre/Verständnis**: die Feldbilder, das LPTN und die FEM sind transparent.

**Wo die Grenzen liegen (bewusst)**
- EM **2D** + **linear** im Solve → keine 3D-Stirnstreuung, Sättigung nur als
  Anzeige; Drehmoment analytisch verankert (nicht feldintegriert).
- Verluste teils **empirisch**; **keine** AC-Kupfer-/Proximity-Verluste.
- Festigkeit **linear-elastisch, ein Lastfall** (keine Press-Vorspannung,
  Thermodehnung, Plastizität, Ermüdung).
- Thermik **6 Knoten**, Konvektion vereinfacht.
- **Keine** NVH/Akustik, **kein** Inverter-/Regelungs-Coupling, **keine**
  Wirkungsgradkennfelder.

**Empfohlener Einsatz (Werkzeugkette)**
1. **Dieses Tool** — Konzept finden, Topologien/Parameter sichten, Kandidaten filtern.
2. **Motor-CAD** — EMag-/Thermik-/Duty-Cycle-Detailauslegung, Wirkungsgradkennfeld.
3. **Abaqus** (+ Maxwell/JMAG) — Festigkeits-/Lebensdauer-/NVH-Nachweis,
   nichtlineare und gekoppelte Effekte, Zertifizierung.

---

## 6. Fazit

| | Dieses Tool | Motor-CAD | Abaqus |
|---|---|---|---|
| Rolle | Vorauslegung/Lehre | E-Maschinen-Detailtool | Struktur/Multiphysik-Nachweis |
| EMag | 2D-FDM + Analytik | 2D-FEA + Analytik | — (Kopplung) |
| Festigkeit | FEM linear, 1 Lastfall | analytisch + FEA | FEM nichtlinear, voll |
| Thermik | LPTN (6 Knoten) | LPTN (detailliert) | FE-Wärmeleitung |
| Validierung | Plausibilität | messvalidiert | zertifizierungs­tauglich |
| Geschwindigkeit/Kosten | sehr schnell, frei | schnell, kommerziell | langsam, teuer |

Die verwendeten Verfahren sind **methodisch korrekt gewählt** (FDM/FEM/LPTN sind
anerkannte Ansätze) und für die **Vorauslegung angemessen**. Für belastbare,
nachweisfähige Ergebnisse — insbesondere AC-Verluste, nichtlineare Sättigung,
Schrumpfsitz-/Thermo-gekoppelte Festigkeit und Lebensdauer — sind **Motor-CAD**
(elektromagnetisch/thermisch) und **Abaqus** (mechanisch/multiphysikalisch) das
Mittel der Wahl.

> Hinweis: Genannte Produktnamen (Abaqus = Dassault Systèmes, Motor-CAD/Maxwell =
> Ansys, JMAG = JSOL, Opera = Dassault) sind Marken der jeweiligen Inhaber. Die
> Aussagen hier beschreiben typische Methoden/Leistungsumfänge zum Vergleich, keine
> herstellerseitige Spezifikation.
