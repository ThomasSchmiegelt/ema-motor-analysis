# E-Maschinen-Berechnung — Technische Dokumentation

Dieses Dokument beschreibt vollständig, wie die E-Maschinen-Analysepipeline im
`cae_orchestrator`-Projekt funktioniert. Es richtet sich an Entwickler, die den
Code verstehen, erweitern oder debuggen wollen.

---

## Inhaltsverzeichnis

1. [Systemübersicht](#1-systemübersicht)
2. [Datenfluss von Ende zu Ende](#2-datenfluss-von-ende-zu-ende)
3. [Geometrie-Eingabe (`ema.html` + `bridge.py`)](#3-geometrie-eingabe)
4. [CAD-Erzeugung (`ema_freecad.py`)](#4-cad-erzeugung)
5. [Elektromagnetischer Feldsolver (`ema_analysis.py`)](#5-elektromagnetischer-feldsolver)
6. [Thermische Analyse (`ema_thermal.py`)](#6-thermische-analyse)
7. [Fahrzyklus-Analyse (`ema_drivecycle.py`)](#7-fahrzyklus-analyse)
8. [Strukturelle FEM – Fliehkraft (`ema_freecad.py`)](#8-strukturelle-fem)
9. [Vollständige Pipeline (`ema_pipeline.py`)](#9-vollständige-pipeline)
10. [Berichtgenerierung (`ema_report.py`)](#10-berichtgenerierung)
11. [Schlüsselkonstanten und Materialien](#11-schlüsselkonstanten-und-materialien)
12. [Bekannte Einschränkungen und Näherungen](#12-bekannte-einschränkungen)
13. [Echte 3D-Feldberechnung — Elmer FEM (`ema_em3d.py`)](#13-echte-3d-feldberechnung)

---

## 1. Systemübersicht

Die E-Maschinen-Pipeline ist eine vollständig lokale CAE-Kette für
**Interior-Permanent-Magnet-(IPM)-Motoren**. Es gibt **eine** Flask-Anwendung
(`server.py`) mit **einer** Single-Page-Browser-UI (`ema.html`, Vanilla JS, kein
Build-Schritt). Es gibt **keine** separaten Streamlit-Apps und kein `bridge.py`
mehr (frühere Architekturvarianten) — der Einstiegspunkt ist ausschließlich
`server.py`, gestartet über `./start.sh`.

`server.py` hält den Analysezustand in modul-globalen Zustandsdicts (`_state` für
die Hauptpipeline, plus eigene States für 3D-Feld, Design-KI, Optimierung,
CAD-Vorschau, Smoke-Test) — es gibt **keine** Session-/Nutzerverwaltung, der Server
verfolgt jeweils **einen** aktiven Job. `POST /analyse` startet
`ema_pipeline.run_pipeline(...)` in einem Daemon-Thread und antwortet sofort mit
`202`; das Browser-UI pollt `GET /status` und holt am Ende `GET /results` — dasselbe
Poll-Muster gilt für die 3D-Feldberechnung (`/em3d`+`/em3d/status`), die
KI-Auslegung (`/design_ai_ranged`+`/design_ai/status`) und weitere Hintergrund-Jobs.
Kein Cloud-Dienst ist beteiligt. Alle LLM-Aufrufe (Bericht, Chat, Text→Auslegung,
KI-Auslegung, Optimierung, RAG-Embeddings) gehen an Ollama (`localhost:11434`).
FEM läuft über FreeCAD + CalculiX; die optionale echte 3D-Feldberechnung über
Elmer FEM (Gmsh-Vernetzung + `ElmerSolver`, Abschnitt 13).

---

## 2. Datenfluss von Ende zu Ende

```
Browser (ema.html)
    │  Nutzer stellt Motor-Geometrie/Betrieb/Material ein (oder zeichnet im
    │  Designer-Tab), klickt „⚙ Echte Berechnung"
    │  POST /analyse  (JSON-Payload: geom + Betriebspunkt + Material + …)
    ▼
server.py  (Flask, Port 5000)
    │  spawnt Daemon-Thread → ema_pipeline.run_pipeline(payload, state)
    │  Antwort: 202 Accepted; Browser pollt GET /status, danach GET /results
    ▼
ema_pipeline.run_pipeline()
    │
    ├─ GEOMETRIE
    │    ema_freecad.build_full_motor_script()  → FreeCAD-Python-Code (String)
    │    freecad_runner.run_freecad_script()    → Subprocess, parst stdout-Marker
    │    Ergebnis: motor.FCStd, motor.step, CAD-Bilder
    │
    ├─ EM-FELD (statisch + Animation)
    │    ema_analysis.run_em_analysis()         → FDM-Solver (scipy splu, Gitter 100–800 px)
    │    pro RPM × Frame: neu skalierte Ströme (MTPA/Feldschwächung)
    │    Ergebnis: A, Bx, By, Br_gap, Bt_gap, Frames (base64 + Disk), Performance-Sweep
    │
    ├─ STRUKTURELLE FEM (Fliehkraft, einmalig bei rpm_to)
    │    ema_freecad.build_rotor_fem_script()   → FreeCAD-Python-Code (String)
    │    freecad_runner.run_freecad_script()    → FreeCAD + CalculiX, Robustheits-Retry
    │    Ergebnis: σ_v,max, u_max, SF, Berstdrehzahl, Knotenanzahl (+ rpm²-Ableitungen)
    │
    ├─ WELLENVERBINDUNG (analytisch, kein FEM)
    │    ema_pipeline.connection_assessment()   → Fugenpressung/Flankenpressung, Moment
    │
    ├─ THERMIK
    │    ema_thermal.run_thermal_analysis()     → LPTN (6 Knoten), stationär + transient
    │
    ├─ FAHRZYKLUS (optional, je gewähltem Profil)
    │    ema_drivecycle.compute_drivetrain()    → RPM/Drehmoment-Zeitreihe
    │    ema_drivecycle.cycle_energy()          → Verbrauch, Wirkungsgrad, thermische Bewertung
    │
    └─ SPEICHERN
         results.json, meta.json, project.json (Projektakte, ema_projekt.py),
         ema_training.upsert() → LLM-Trainingsfile
```

Der Bericht (`ema_report.py`, lokales LLM via Ollama → Markdown → `pandoc` →
`pdflatex` → `bericht.pdf`) und die echte 3D-Feldberechnung (`ema_em3d.py`, Elmer
FEM) sind **eigene, separat angestoßene** Hintergrund-Jobs (`POST
/project/<id>/report`, `POST /em3d`) — keine Pipeline-Stufen von `run_pipeline`.
`run_pipeline(..., stages=<Teilmenge>)` erlaubt außerdem einen **selektiven
Nachlauf** einzelner (teurer/optionaler) Stufen ⊆ `{field, structural, thermal,
drivecycle}` auf einem bereits existierenden Projekt (`POST
/project/<id>/recompute`), ohne die Geometrie neu zu bauen.

---

## 3. Geometrie-Eingabe

### `ema.html` (Browser-UI)

Eine eigenständige HTML-Seite mit JavaScript, die ein interaktives
Geometrie-Formular bereitstellt. Der Nutzer stellt alle Motor-Parameter ein und
klickt „CAD Export (Python)". Die Seite sendet ein JSON-Objekt per `fetch` an
`http://localhost:5000/geom`.

**Geometrie-Parameter (Schlüssel im JSON):**

| Parameter | Typ | Bedeutung |
|---|---|---|
| `statorOD` | float [mm] | Stator-Außendurchmesser |
| `statorID` | float [mm] | Stator-Innendurchmesser (= Luftspaltgrenze) |
| `rotorOD` | float [mm] | Rotor-Außendurchmesser |
| `shaftD` | float [mm] | Wellen-Durchmesser |
| `p` | int | Polpaar-Anzahl |
| `slots` | int | Nutanzahl Stator |
| `slotDepth` | float [mm] | Nuttiefe |
| `slotWidthRatio` | float [0–1] | Nutenbreite relativ zur Nutteilung |
| `magShape` | string | Magnet-Topologie: `v`, `vasym`, `vv`, `u`, `delta`, `pmasynrm`, `spm`, `halbach`, `spoke`, `bar` oder `custom` (frei gezeichnet im Designer) |
| `magWidth` | float [mm] | Magnetlänge (entlang der langen Achse) |
| `magThick` | float [mm] | Magnetdicke |
| `magAngle` | float [°] | Öffnungswinkel der V-Anordnung (gesamt) |
| `magDist` | float [mm] | Abstand der beiden V-Magnete zur Polteilungsachse |
| `magDepthRel` | float [0–1] | Radiale Position der Magnete (0 = Welle, 1 = Außenrand) |

Dies ist nur ein Ausschnitt der Kern-Geometrieparameter. Die vollständige,
einzige-Quelle-der-Wahrheit-Ableitung der Magnetplatzierung je Topologie steht in
`ema_topology.py` (`magnet_legs(geom)`); die aktuelle, vollständige Parameterliste
(inkl. Wicklung, Wellenverbindung, Komponenten-Toggles, Flussbarrieren,
Wuchtscheiben-Bolzen, Skew/Staffelung fürs 3D-Feld) ist in `CLAUDE.md` gepflegt.

### `server.py` (Flask-Backend)

`POST /analyse` nimmt das JSON entgegen und startet `ema_pipeline.run_pipeline`
in einem Daemon-Thread; das Browser-UI (`ema.html`) pollt `GET /status` und holt
am Ende `GET /results`. Es gibt keine separate Streamlit- oder `bridge.py`-Variante
mehr — Einstiegspunkt ist ausschließlich `server.py` (siehe Abschnitt 1).

---

## 4. CAD-Erzeugung

**Datei:** `ema_freecad.py`

### Rotor-Geometrie (`build_em_rotor_script`)

Erzeugt einen FreeCAD-Python-Skript-String, der headless ausgeführt wird und
eine Rotorscheibe mit Magnettaschen erstellt.

**Ablauf im erzeugten Skript:**

1. **Rotorring**: `Part.makeCylinder(R_rot, axial)` abzüglich Wellenbohrung
2. **Magnettaschen** (Schleife über alle Pole):
   - Pro Pol: 2 Taschen (V-Form) oder 1 Tasche (flat)
   - Jede Tasche ist eine Box (`Part.makeBox`) mit Übermaß (`tol = 0.4 mm`)
   - Die Box wird um `(pole_ang + h_ang)` gedreht und dann verschoben
   - `rotor.cut(pkt)` entfernt die Tasche — nach jedem Schnitt Validierung
3. Ausgabe: `CAD_FACES:<json>`, `CAD_VOLUME:<float>`, `SAVED:<path>`, `CAD_SUCCESS`

**Magnet-Clamping (`_max_magnet_width`):**

Verhindert, dass Magnettaschen aus dem Rotor herausragen. Löst die quadratische
Gleichung:

```
(rPos + magW·cos α)² + (magDist + magW·sin α)² = (R_rot − 2 mm)²
```

Der äußerste Eckpunkt der Tasche muss mindestens 2 mm Brücke zum Außenrand
einhalten. Falls die Diskriminante negativ ist, wird `magW = 5 mm` gesetzt.

### Vollmotor-Geometrie (`build_full_motor_script`)

Erstellt zusätzlich Statorring mit Nuten, Permanentmagnete (N rot / S blau),
Welle und Hairpin-Leiter (3-phasig, 2-lagig) als separate FreeCAD-Objekte mit
Farben. Exportiert auch eine STEP-Datei parallel zur FCStd-Datei.

---

## 5. Elektromagnetischer Feldsolver

**Datei:** `ema_analysis.py`

Der Feldsolver arbeitet vollständig in Python mit NumPy — kein externes
FEM-Programm für den EM-Teil.

### 5.1 Geometrie-Rasterisierung (`_rasterise`)

Das 2D-Motorquerschnitt wird auf ein `N×N`-Pixel-Grid (Standard: N=150)
abgebildet.

**Grid-Aufbau:**

```python
maxD = statorOD * 1.1          # Rand-Abstand
sc   = N / maxD                # Skalierung px/mm
ctr  = N / 2                   # Mittelpunkt
```

**Materialverteilung:**
- `mu[R >= r_si & R <= r_so] = 500` → Statorjoch (Elektrostahl)
- `mu[R >= r_sh & R <= r_ro] = 500` → Rotoreisen
- Statornuten (innerhalb `r_si` bis `r_si + slotDepth`): `mu = 1` (Luft)
- Magnete: `mu = 1.05` (NdFeB N35)

**Statorstrom-Einspeisung (dq-Transformation):**

Für eine gegebene Rotorlage `rotor_angle` und Ströme `iq`, `id_` wird pro Nut
ein Strombelag `J` aufgeprägt:

```python
elAng = ang * p_pairs
cur   = (id_ * cos(elAng - rotor_angle * p) - iq * sin(elAng - rotor_angle * p)) / IQ_REF
J[mask] += cur * J_slot_scale
```

`IQ_REF = 2.0` normiert die Skala so, dass bei `iq = 2 A` ca. 50 % des
Magnet-J erreicht wird (kalibriert am konvergierten float64-Solver).

**Permanentmagnet-Modellierung:**

Statt Punktquellen wird der Curl der Magnetisierung M verwendet (Standard-FEM-Ansatz):

```
J_z = curl(M) = ∂My/∂x − ∂Mx/∂y
```

Die Magnetisierung `M = amp · t̂` ist uniform innerhalb jedes Magnets
(t̂ = Einheitsvektor senkrecht zur langen Magnetachse, Vorzeichen wechselt mit
Nord-/Südpol). Die Finite-Differenz-Gradienten an der Magnetgrenze erzeugen
automatisch den korrekten Oberflächenstrom ohne Punktquell-Artefakte.

### 5.2 FDM-Löser (`_solve_fdm`)

Löst die 2D-magnetostatische Gleichung:

```
∇(ν · ∇A) = −J
```

mit der Skalarvariable `A` (z-Komponente des magnetischen Vektorpotentials).

**Methode:** Ein Finite-Volumen-5-Punkt-Operator mit harmonisch gemittelten
Flächen-ν (`_build_fv_matrix`) wird **direkt sparse faktorisiert** (`scipy splu`)
und für die rechte Seite `J` rücksubstituiert. Das ist bei jeder Auflösung exakt
(kein Iterations-Tuning), sodass Luftspalt und Zähne auch bei hoher Auflösung
sauber aufgelöst werden. Der Operator hängt nur von der Permeabilitätskarte µ
(Geometrie + Rotorwinkel) ab, **nicht** von den Strömen (die in `J` stecken) — die
Faktorisierung wird daher per `(N, hash(µ))` gecacht und über alle Drehzahl-/
Stromwinkel-/Lastschritte beim gleichen Rotorwinkel wiederverwendet.

| Parameter | Wert | Bedeutung |
|---|---|---|
| Operator | FV-5-Punkt, harm. Mittel ν | symmetrisch positiv definit (interne Knoten) |
| Faktorisierung | `scipy.sparse.linalg.splu` | exakt, einmal pro µ gecacht |
| Hochauflösung | `pyamg` AMG (CG-beschl.) | ab N > 2500 (Speicher), Hierarchie ebenfalls gecacht |
| Fallback | iterative Red-Black-SOR | nur falls scipy fehlt (`_solve_fdm_sor`) |
| Datentyp | float64 | – |
| Randbedingung | A = 0 am Rand | Dirichlet (10 % Luftrand, kein Fluss durch den Rand) |

> Hinweis: Frühere Versionen nutzten Red-Black-SOR als primären Löser; diese
> iterative Variante ist nur noch der scipy-lose Fallback.

### 5.3 Luftspaltabtastung (`_sample_airgap`)

Aus dem gelösten Potenzial `A` werden die Flussdichtekomponenten über den
negativen Gradienten berechnet:

```python
Bx =  dA/dy    # (B = curl A in 2D)
By = -dA/dx
```

Entlang 720 gleichmäßig verteilter Punkte auf dem mittleren Luftspaltradius
werden Bx und By bilinear interpoliert und in Radial- und Tangentialkomponenten
transformiert:

```
Br =  Bx·cos(θ) + By·sin(θ)
Bt = -Bx·sin(θ) + By·cos(θ)
```

### 5.4 Analytische Kalibrierung (`_analytical_Bgap`)

Der FDM-Solver liefert `A` in relativen Einheiten. Zur Umrechnung in physikalische
Tesla wird der Peak der radialen Flussdichte auf den analytisch berechneten Wert
skaliert:

```
B_analytical = Br_NdFeB · (hm_eff / (hm_eff + μ_r,mag · kc · g)) · α_i
```

mit:
- `hm_eff = magThick · sin(magAngle/2)` — effektive Magnetdicke für V-Magnete
- `kc = 1.15` — Carter-Faktor (vereinfacht, berücksichtigt Nutöffnungen)
- `g = (statorID − rotorOD) / 2` — mechanischer Luftspalt [mm]
- `α_i = min(magSpan / polePitch, 0.92)` — Polbedeckungsfaktor

Der Skalierungsfaktor:
```python
sf = B_analytical / max(fdm_peak, 1e-6)
```

wird auf alle FDM-Felder angewendet.

### 5.5 Maxwell-Drehmoment

Das elektromagnetische Drehmoment wird aus dem radialen und tangentialen
Flussdichteanteil entlang des Luftspalts berechnet:

```
T_maxwell = (2π R_gap L_ax / μ₀) · mean(Br · Bt)
```

mit `R_gap = (r_rot/2 + r_si/2) / 1000` [m] und `L_ax = 80 mm` (Axiallänge).

### 5.6 Leistungsgrößen (`compute_performance`)

| Kenngröße | Formel | Einheit |
|---|---|---|
| Flussverkettung | `ψ_pm = p · (2/π) · B_gap · R_gap · L_ax` | Wb |
| EMK (Spitze) | `ê = ψ_pm · ω_el`, `ω_el = n · 2π/60 · p` | V |
| EMK (RMS) | `E_rms = ê / √2` | V |
| Drehmomentkonstante | `Kt = 1.5 · p · ψ_pm` | Nm/A_pk |
| Zahnmoment (geschätzt) | `T_cog ≈ Br · R_gap · L_ax · 0.05 / lcm` | Nm |
| LCM Nuten/Pole | `lcm(poles, slots)` | — |

### 5.7 Feldlinien-Sweeps (in `ema_pipeline.py`)

Für einen Drehzahl-/Last-Sweep wird `run_em_analysis` für mehrere Rotorwinkel
und dq-Stromkombinationen wiederholt aufgerufen. `estimate_dq_currents` berechnet
dabei das nötige `iq` (Last) und `id_` (Feldschwächung):

- **Unterhalb der Basisgeschwindigkeit:** `id_ = 0`, `iq = T_load / Kt`
- **Oberhalb der Basisgeschwindigkeit:** Lineare FW-Rampe bis `id_ = −iq · 1.5`,
  `iq` leicht reduziert (MTPA-Näherung)

---

## 6. Thermische Analyse

**Datei:** `ema_thermal.py`

### 6.1 LPTN-Topologie

Das Thermische Netz hat 6 Knoten:

```
[W] Wicklung (Hairpin-Cu)
 │ G_w_si
[Si] Statoreisen
 │ G_si_h              G_si_m
[H] Gehäuse        [M] Magnete
 │ G_h_amb              │ G_m_ri
[Amb] Umgebung      [Ri] Rotoreisen
                         │ G_ri_sh
                        [Sh] Welle
                         │ G_sh_h
                        [H] Gehäuse
```

Alle Leitwerte in W/K:

| Pfad | Berechnung | Typischer Wert |
|---|---|---|
| W ↔ Si | `K_ins · A_slot / t_ins`, cap 100 W/K | ~100 W/K |
| Si ↔ H | `1500 W/m²K · 2π·R_so·L` | ~300 W/K |
| Si ↔ M | `(6 + 0.02·rpm) · 2π·R_si·L` | 10–200 W/K |
| M ↔ Ri | 80 W/K (Klebung, fest) | 80 W/K |
| Ri ↔ Sh | `800 · 2π·R_sh·L` | ~30 W/K |
| Sh ↔ H | 5 W/K (Lager, schlechter Pfad) | 5 W/K |
| H → Amb | `h_eff · A_gehäuse` (kühlungsabhängig) | s. u. |

**Kühlungs-Presets:**

| Kühlung | h_eff [W/m²K] | ΔT_Kühlmittel |
|---|---|---|
| Natürliche Konvektion | 8 | 0 K |
| Zwangsluft | 35 | 5 K |
| Wassermantel | 800 | 15 K |
| Ölkühlung (Spray) | 2500 | 20 K |

### 6.2 Verlustrechnung (`compute_losses`)

**Kupferverluste:**

```
R_phase = ρ_el · L_cond · n_slots · n_layers / (3 · A_leiter)
P_Cu    = 3 · (iq² + id²) / 2 · R_phase
```

Hairpin-Leiterquerschnitt aus Geometrie: `A = cond_w · layer_h`.
Leiterlänge inkl. 18 mm Wickelkopf-Überhang: `L_cond = L_axial + 2 · 18 mm`.

**Eisenverluste (Bertotti-Referenz):**

```
P_Fe = specific_loss [W/kg] · (f_el/50) · B_gap² · m_Stator
```

Aufteilung: 75 % Stator, 25 % Rotor.

**Magnetverluste (Wirbelstrom, empirisch):**

```
P_Mag = 0.005 · P_Cu + 0.02 · P_Fe · (f_el / 200)²
```

**Lager/Windungsverluste:**

```
P_Bear = 0.005 · P_mech + 5 W  (5 W Basiszug)
```

### 6.3 Stationäre Lösung

```
A · T = P    →    T = inv(−A) · (P + G_h_amb · T_amb · e_H)
```

Die Matrix A wird aus den Leitwerten assembliert (Knotenmatrix mit negativen
Diagonaleinträgen = Summe ausgehender Leitwerte).

### 6.4 Transiente Lösung (Implicit Euler)

```
(C/dt − A) · T^{n+1} = C/dt · T^n + P + G_h_amb · T_amb · e_H
```

Standard: `t_max = 1800 s`, `dt = 5 s`. Die Wärmekapazitäten werden aus
Geometrie und Materialeigenschaften berechnet.

### 6.5 Warnungsgrenzen

| Knoten | Warnschwelle | Grenzwert |
|---|---|---|
| Wicklung | 155 °C | Klasse F |
| Wicklung | 180 °C | Klasse H (Abschaltschwelle) |
| Magnet | 150 °C | NdFeB N35 Entmagnetisierungsrisiko |
| Gehäuse | 80 °C | Berührungsschutz erforderlich |

---

## 7. Fahrzyklus-Analyse

**Datei:** `ema_drivecycle.py`

### 7.1 WLTP-3b-Profil

Das WLTP-Klasse-3b-Profil ist eine **deterministische Approximation** mit korrekten
Phasengrenzen, Spitzen- und Durchschnittsgeschwindigkeiten:

| Phase | Dauer [s] | v_max [km/h] | v_avg [km/h] | Strecke [m] |
|---|---|---|---|---|
| Low | 589 | 56.5 | 18.9 | 3095 |
| Medium | 1022 | 76.6 | 39.5 | 4756 |
| High | 1477 | 97.4 | 56.7 | 7158 |
| Extra-High | 1800 | 131.3 | 92.0 | 8254 |
| **Gesamt** | **1800** | — | — | **23 260** |

Das Profil wird durch stochastische Beschleunigungs-/Brems-/Konstantfahrt-Segmente
aufgebaut (RNG-Seed: 20260522 → reproduzierbar). Pro Phase wird die Zeitreihe auf
die Ziel-Durchschnittsgeschwindigkeit skaliert und auf v_max geclippt.

### 7.2 Antriebsstrang-Dynamik (`compute_drivetrain`)

Fahrwiderstände:

```
F_Trägheit  = m · a
F_Luft      = 0.5 · ρ · cwA · v²
F_Roll      = m · g · cr   (wenn v > 0.1 m/s)
F_Hang      = m · g · sin(α)
F_Rad       = F_Trägheit + F_Luft + F_Roll + F_Hang
```

Motordrehmoment (Einzel-Untersetzung `i_gear`):
- Antrieb: `T_motor = (F_Rad · r_Rad) / (i_gear · η_drive)`
- Bremsen: `T_motor = (F_Rad · r_Rad) · η_drive / i_gear`

**Standard-Fahrzeugparameter:**

| Parameter | Wert |
|---|---|
| Masse | 1600 kg |
| cwA | 0.65 m² |
| Rollwiderstand | 0.012 |
| Radradius | 0.32 m |
| Getriebeübersetzung | 9.5 |
| Antriebswirkungsgrad | 0.95 |
| Rekuperationsanteil | 55 % |

### 7.3 Energiebilanz (`cycle_energy`)

Skalierung der Verluste über den Zyklus:
- **Kupfer:** `P_Cu(t) ∝ |T(t)|²` (da `i_q ∝ T / Kt`)
- **Eisen:** `P_Fe(t) ∝ |rpm(t)|²` (Bertotti-Hauptterm)
- **Magnete:** `P_Mag(t) ∝ |rpm(t)|²`
- **Lager:** Konstant wenn `rpm > 50 U/min`

Elektrische Eingangsleistung:
- Motormode: `P_elec = P_mech + P_loss`
- Bremsmode: `P_elec = −|P_mech| · regen_frac + P_loss`

Ausgegeben werden: Verbrauch [kWh/100 km], Gesamtwirkungsgrad, Rekuperationsanteil,
Verlustaufteilung nach Verlustmechanismus.

---

## 8. Strukturelle FEM

**Datei:** `ema_freecad.py` → `build_rotor_fem_script`

### 8.1 Ablauf

Der erzeugte FreeCAD-Python-Code:

1. Öffnet `rotor.FCStd`
2. Sucht das Rotor-Objekt (Name „Rotor" oder erstes `Part::Feature`)
3. Erstellt FEM-Analyse-Objekt und Materialdefinition
4. Sucht die Wellenbohrungsfläche automatisch:
   ```python
   kleinster Zylinder-Radius → shaft_face_ref = f"Face{i+1}"
   ```
5. Setzt Festeinspannung (`Fixed`) an der Wellenbohrung
6. Vernetzt mit Gmsh (Elementgröße: `CharacteristicLengthMax = 4 mm`)
7. Schreibt CalculiX-.inp-Datei und **patcht** sie manuell:

### 8.2 INP-Datei-Patching

FreeCAD 1.x schreibt keine `*DENSITY`- und keine `*DLOAD CENTRIF`-Blöcke.
Das Skript öffnet die erzeugte `.inp`-Datei und fügt ein:

**Dichte** (nach dem `*ELASTIC`-Datenblock):
```
*DENSITY
7.9e-9,              ← t/mm³  (= 7900 kg/m³ / 1e12)
```

**Fliehkraft** (vor `*END STEP`):
```
*DLOAD
Evolumes, CENTRIF, ω², 0., 0., 0., 0., 0., 1.
           ──────────────────────────────────────
           ω² [rad²/s²], Rotationsachse Z
```

`ω = rpm · 2π / 60` — CalculiX verlangt `ω²` als Skalierungsfaktor.

### 8.3 Einheitensystem

CalculiX in der FreeCAD-Integration nutzt das System **mm / N / MPa / t**:
- Kraft: N
- Länge: mm
- Spannung: MPa = N/mm²
- Dichte: t/mm³ (= kg/m³ · 10⁻¹²)

Falsche Einheiten für die Dichte sind der häufigste Fehler bei Fliehkraftanalysen.

### 8.4 Ergebnisauswertung

FreeCAD 1.x importiert `.frd`-Ergebnisse nicht automatisch zurück. Das Skript
druckt den FRD-Dateipfad:

```
FRD_FILE:/path/to/ccx_rotor/Analysis.frd
```

`freecad_runner.py` parst diese Ausgabe und liest die `.frd`-Datei direkt aus,
um `max_von_mises_MPa`, `max_displacement_mm` und `node_count` zu extrahieren.

**Bewertung:**

```
Sicherheitsfaktor = Re / σ_v,max
```

Grenzwerte für Stahl S235 (`Re = 235 MPa`):
- SF ≥ 2.0 → Grün (ausreichend)
- SF ≥ 1.0 → Gelb (grenzwertig)
- SF < 1.0 → Rot (Versagen)

---

## 9. Vollständige Pipeline

**Datei:** `ema_pipeline.py`

Die vollständige Pipeline führt alle Schritte sequenziell durch, speichert alle
Zwischenergebnisse strukturiert und erzeugt Charts:

```
cae_projekte/<timestamp>_<name>/
├── rotor.FCStd
├── motor.FCStd        (Vollmotor inkl. Stator, Leiter)
├── motor.step
├── results.json       (alle Kennwerte)
├── meta.json          (Geometrie + Achslänge)
├── bericht.md
├── bericht.pdf
├── cad_images/
│   ├── motor_cross_section.png
│   └── motor_side_view.png
└── charts/
    ├── airgap.png
    ├── em_curve.png
    ├── structural_sweep.png
    ├── deformation.png
    ├── thermal.png
    └── drivecycle.png
```

Diese Liste ist illustrativ, nicht vollständig — je nach genutzten Funktionen kommen
weitere Verzeichnisse hinzu: `project.json` (Projektakte, `ema_projekt.py`),
`frames_react/`/`frames_load/`/`frames_struct/`/`frames_em3d/` (weitere
Feld-/Verformungs-/3D-Animationsmodi), `em3d/` (Elmer-Mesh/SIF/VTU bei einer 3D-
Feldberechnung), `em3d_runs/<id>/` (gespeicherte 3D-Läufe) und `rag/index.json`
(projektspezifische Wissensbasis).

**Materialdatenbanken** (in `ema_pipeline.py`):

- `LAMINATES`: Elektrostahl-Blechsorten (M250-35A bis M800-65A, S235, 42CrMo4)
  mit Verlustzahl [W/kg @ 1 T/50 Hz], Sättigungsflussdichte, Dichte, E-Modul
- `HAIRPIN_MATERIALS`: Kupfer und Aluminium mit ρ_el, Dichte, cp
- `MAGNET_GRADES`: NdFeB N35/N42/N48, SmCo28 mit Br, Hc, T_max, Dichte
- `ROTOR_MATERIALS`: Stahl-Sorten für Rotoreisen (FEM-relevant: E, ν, Re, ρ)

---

## 10. Berichtgenerierung

**Datei:** `ema_report.py`

### 10.1 Modell

```python
DEFAULT_MODEL = os.environ.get("CAE_LLM_MODEL", "qwen3.8:latest")
```

Ministral ist das einzige LLM in dieser Kette. Es wird ausschließlich für
die Textgenerierung des Berichts verwendet — alle Berechnungen davor sind
rein numerisch.

### 10.2 Kontext-Aufbereitung (`build_context`)

Liest `results.json` und `meta.json` aus dem Projektverzeichnis und baut ein
kompaktes JSON-Dict mit nur den für den Bericht relevanten Kenngrößen:
Geometrie, EM-Kennwerte, Festigkeit, Thermik, Fahrzyklus. Große Zeitreihen-Arrays
werden nicht übergeben.

Zusätzlich wird eine Map der vorhandenen Bild-Dateien gebaut (Pfad + Titel pro Key).

### 10.3 Prompt-Struktur

Der Prompt weist Ministral an:
- Sprache: Deutsch, sachlich, ohne Floskeln
- Struktur: 7 fest vorgegebene Abschnitte (Zusammenfassung, Geometrie, EM,
  Festigkeit, Thermik, Fahrzyklus, Empfehlungen)
- Bilder: `[BILD:key]`-Platzhalter an passenden Stellen setzen

### 10.4 Nachbearbeitung

```python
_BILD_RE = re.compile(r"`?\s*\[BILD\s*:\s*([a-z_]+)\s*\]\s*`?", re.IGNORECASE)
```

Ersetzt alle `[BILD:key]`-Platzhalter durch `![title](path)`-Markdown-Referenzen.
Nicht referenzierte Bilder werden am Ende als eigener Abschnitt angehängt.
`<think>...</think>`-Blöcke (falls das Modell diese erzeugt) werden entfernt.

### 10.5 PDF-Rendering

```
pandoc bericht.md
    --from markdown-yaml_metadata_block
    --pdf-engine=xelatex
    -V geometry:margin=18mm
    -V mainfont="DejaVu Serif"
    → bericht.pdf
```

`-from markdown-yaml_metadata_block` verhindert, dass `---`-Trennlinien
als YAML-Header fehlinterpretiert werden. Fallback auf pdflatex, falls xelatex
fehlt.

---

## 11. Schlüsselkonstanten und Materialien

### EM-Materialkonstanten (`ema_analysis.py`)

```python
Br_NdFeB   = 1.15   # T   — NdFeB N35 Remanenz
MU_R_MAG   = 1.05   # —   — NdFeB rel. Permeabilität
MU_R_IRON  = 500.0  # —   — Elektrostahl
MU0        = 4π·10⁻⁷ H/m
```

### FDM-Skalierungsparameter

```python
J_amp        = 6000.0 / N   # Magnetisierungsamplitude (skaliert mit Grid)
J_slot_scale = 5.0 / N      # Statorstrom-Skalierung
IQ_REF       = 2.0          # Normierungsstrom für dq-Einspeisung
```

### Axiallänge

```python
AXIAL_LEN = 80.0  # mm  — Standard-Blechpaketlänge in ema_app.py
L_ax      = 0.080 # m   — in ema_analysis.py
```

### FEM-Timeout

```python
timeout = 600  # Sekunden (CalculiX)
```

---

## 12. Bekannte Einschränkungen

### EM-Feldsolver

- **2D-Näherung:** Der FDM-Solver ist rein 2D (kein Axialschnitt). Randeffekte,
  Wickelkopf-Streuung und Sättigungsverläufe axial sind nicht erfasst. Wer diese
  Effekte quantitativ braucht (Endeffekte, Schrägung/Skew), kann optional die echte
  3D-Feldberechnung (Elmer FEM, Abschnitt 13) danebenrechnen — der 2D-Solver bleibt
  dabei unverändert der schnelle Standardpfad für Kennlinien/Sweeps.
- **Gitterauflösung:** Bei N=150 entspricht ein Pixel ca. 1–2 mm. Sehr schmale
  Magnete (<3 mm) oder enge Luftspalte (<0.5 mm) werden ungenau dargestellt.
- **Iterationszahl:** 120 SOR-Iterationen ohne Residuumsprüfung. Bei extremen
  Geometrien (sehr hohe μ_r-Sprünge) kann der Löser nicht vollständig konvergieren.
- **Kalibrierung:** Die physikalische Einheit wird über `_analytical_Bgap` (Carter-
  Gleichung) eingestellt. Diese Gleichung gilt streng nur für den Leerlauffall
  und flache Magnete. Für V-Magnete wird `hm_eff = hm·sin(α/2)` verwendet.
- **Drehmoment:** Das Maxwell-Drehmoment wird über den Mittelwert `mean(Br·Bt)`
  berechnet — korrekt für symmetrische Verteilungen, kann bei asymmetrischen
  Rastzuständen ungenau sein.

### Thermische Analyse

- **Stationärer Betriebspunkt:** Die Verlustrechnung gilt für einen festen
  Arbeitspunkt (rpm, iq, id). Kein thermisches Betriebsartenmodell (S1–S9).
- **1D-Wärmepfad:** Keine 2D-FEM-Thermik; die LPTN-Leitwerte sind empirische
  Schätzwerte.
- **Eisenverluste:** Skalierung über `(f/50)·B²` (vereinfachtes Bertotti-Modell),
  kein separater Hysterese- und Wirbelstromterm.

### Strukturelle FEM

- **Netzgröße:** 4 mm Elementgröße ist für Spannungsspitzen (Kerbwirkung an
  Magnettaschen-Ecken) grob. Ergebnisse können σ_v um 30–50 % unterschätzen.
- **Randbedingung:** Die Wellenbohrung ist vollständig eingespannt (keine
  Pressverbandmodellierung). Bei kleinen Wellen-/Rotor-Verhältnissen konservativ.
- **Keine Magnetkräfte:** Die elektromagnetischen Kräfte auf den Rotor
  (Maxwell-Kräfte im Luftspalt) werden in der Strukturanalyse nicht berücksichtigt
  — nur Fliehkraft.

### Fahrzyklus

- **WLTP-Approximation:** Das Profil ist eine stochastische Rekonstruktion
  (Seed: 20260522), keine offizielle WLTP-Tabelle. Gesamtstrecke ±2 %.
- **Eingang Verlustskaling:** Die Verluste werden von einem Referenzpunkt auf
  den gesamten Zyklus skaliert (quadratisch in T und rpm). Ein echtes Verlust-
  kennfeld (Torque-Map) wäre genauer.
- **Einstufiges Getriebe:** Kein Gangwechsel, keine Schlupfmodellierung.

---

## 13. Echte 3D-Feldberechnung

**Dateien:** `ema_em3d.py` (Orchestrierung, Mesh, SIF, Auswertung), `elmer_runner.py`
(Subprozess-Wrapper für `ElmerGrid`/`ElmerSolver`).

Ein eigenständiger, **on-demand** angestoßener Pfad neben dem 2D-FDM-Solver (der 2D-
Löser bleibt unverändert der schnelle Standardpfad und dient zugleich als
Vergleichsanker). Löst, was 2D grundsätzlich nicht kann: **finite Baulänge**
(Endeffekte), **Schrägung/Staffelung**, eine echte volumetrische 3D-Feldlösung und
einen quantitativen 2D-vs-3D-Vergleich.

### 13.1 Vernetzung (`build_mesh`)

Gmsh-OCC baut die volle 3D-Geometrie: konzentrische Zylinder je Radius (Welle,
Rotoreisen, Luftspalt, Statoreisen, Luftbox), Magnete als `addThruSections`-Lofts aus
`magnet_rects(geom)` (gespiegelt zur 2D-Rasterisierung `ema_analysis._rasterise`),
optional um `skew_deg` verdreht (kontinuierlich) oder in `skew_segments` diskrete,
um die Wellenachse gedrehte Stufen zerlegt (Staffelung). Alle Teile werden per
`occ.fragment` verschnitten und über Schwerpunkt/Radius/z-Position als **Physical
Volumes** getaggt (Magnet-Zuordnung über ein Massengate, da konzentrische Ringe ihren
Volumenschwerpunkt auf der Achse haben). Optionale Zusatzgeometrie: Flussbarrieren
(radiale Luft-Prismen), Statornuten (gerade Luft-Prismen über die volle Länge) und
**Magnettaschen als echte Langlöcher** — jeder vergrabene Magnet sitzt in einer
obround-Luftschale mit `magGapMm` (0,1–0,3 mm) Spalt rundum; bei Staffelung werden die
gestuften Einzeltaschen pro Magnet zu **einem** zusammenhängenden Luftkanal fusioniert
(sonst blieben zwischen den verdreht gestapelten Prismen dünne Eisen-Slivers stehen,
die das Netz entarten lassen). Ein **Netz-Entartungs-Wächter** prüft nach jedem
Vernetzungsversuch die Tetraeder-Qualität; schlägt sie fehl, durchläuft ein
**selbstheilender Monitor** eine Mitigationsleiter (Netzqualität/-dichte hoch →
Zonenverhältnisse angleichen → Gesamtnetz gröber → Zusatzgeometrie sukzessive
abschalten), bis der Bau gelingt oder die Leiter erschöpft ist. Zonale Verfeinerung
(Luftspalt sehr fein, Magnete/Barrieren/Nuten fein, Rest grob) hält die Knotenzahl
innerhalb eines einstellbaren Budgets.

### 13.2 Löser (`write_sif` → `ElmerSolver`)

Magnetostatik über `WhitneyAVSolver` (Kantenelemente, Vektorpotential A) +
`MagnetoDynamicsCalcFields` + `SaveScalars`, gelöst mit dem **direkten
MUMPS-Löser** (ein iterativer Löser stagniert an diesem Gleichungssystem). Eisen
linear µr≈500, Magnete µr≈1,05 mit `Body Force Magnetization = Br/µ0 · Richtung` pro
Magnet; Außenrand `A×n=0`. Optional wird der **Betriebspunkt** (Drehzahl + Last)
berücksichtigt: dq-Ströme aus `estimate_dq_currents` treiben Nutstromdichten +
Stirnring-Rückleiter (damit ∇·J≈0 über die endliche Baulänge schließt), eine
iterative Divergenzbereinigung (`Fix Input Current Density`) hält das System
konsistent. v1-Scope: **lineare** Materialien, keine verteilte Wicklungsgeometrie.

### 13.3 Auswertung (`parse_results`)

Liest die VTU-Ergebnisse (Paket `vtk`): Luftspalt-B_r(θ) bei mehreren Axialpositionen
→ **Endeffekt-Kurve** (Feldabfall zum Rand hin), |B|-Schnittbild bei z=L/2, Arkkio-
Drehmoment sowie ein **2D-vs-3D-Vergleich** gegen `ema_analysis.run_em_analysis`.
Ergebnisse fließen als kompakte Zusammenfassung in `results.json` (`results["em3d"]`)
und damit automatisch in den PDF-Bericht ein.

### 13.4 Erweiterte Modi

- **Drehzahl-/Lastsweep** (`run_em3d_sweep`): das Netz hängt nicht von Drehzahl/Last
  ab und wird deshalb **einmal** gebaut; pro Betriebspunkt läuft nur `write_sif` +
  `ElmerSolver` neu. Ein Detailpunkt bekommt das volle 3D-Feld, alle anderen nur
  schlanke Kennwerte — inklusive eines optionalen Lastprofil-Videos.
- **ROI-Verfeinerung** (`run_em3d_refine`): lokal feineres Netz in einem markierten
  Quader + vollständiger Re-Solve (kein Submodell mit Randwert-Transfer — das
  scheitert an einem realen, nicht glatten Motor-Randfeld; ein voller Re-Solve ist
  im ROI sogar genauer, kostet aber einen weiteren Solve).
- **Ein-Pol-Symmetrie-Schnellmodus** (`run_em3d_sector`): löst nur eine
  Polteilung mit anti-periodischer Randbedingung (Elmer `Periodic BC` +
  `Scale=-1`) und spiegelt das Ergebnis zum vollen Motor — bei gleichem
  Knotenbudget deutlich feiner aufgelöst, da die Domäne nur 1/(2p) so groß ist.
  Erfordert `slots % poles == 0`; v1-Scope: Leerlauf + Magnete (+ Taschen) +
  Statornuten + Flussbarrieren + Hohlwelle, kein Skew/keine Spulenströme.

### 13.5 Voraussetzungen und Grenzen

Benötigt Elmer (`elmerfem-csc`) sowie die Python-Pakete `gmsh`/`vtk` — rein optional,
Mesh und SIF-Datei sind auch ohne installiertes Elmer test- und baubar
(`test_em3d.py`). **v1-Scope-Einschränkungen:** lineare Materialien (keine
BH-Kurve), vereinfachtes Lastfeld (Grundwelle statt verteilter realer Wicklung),
keine Bewegungssimulation/Transiente (der Drehzahlsweep ist eine Folge statischer
Arbeitspunkte, keine echte Zeitintegration). Ausführliche Architekturdetails
(Gotchas, Tagging-Feinheiten, UI-Bedienung) stehen in `CLAUDE.md` und
`NUTZUNGSANLEITUNG.md` (Tab „🧲 3D-Feld").
