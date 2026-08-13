# physics_surrogate — PhysicsNeMo-Surrogate für die CAE-Löser

Trainierte Ersatzmodelle (NVIDIA PhysicsNeMo) für die Löser-Stufen des
`cae_orchestrator`. Sie liefern eine Vorhersage in Millisekunden; der echte Löser
(FDM/Elmer/Blender) bleibt der Bestätigungslauf. Eigener HTTP-Dienst auf **:5300**,
angesprochen vom Orchestrator über `cae_orchestrator/ema_surrogate.py`.

**Eine Vorhersage ist keine Lösung.** Ergebnisse des Dienstes tragen in der UI ein
dauerhaftes Banner und fließen **nicht** in `results.json`, den PDF-Bericht oder den
Trainingsdatensatz ein — dieselbe Scope-Ehrlichkeit wie beim isothermen HTC in
`ema_cfd.py`.

## Start

```bash
./install.sh        # einmalig: venv + PhysicsNeMo/Torch (~5–6 GB), Rauchtest
./start.sh          # Dienst auf :5300
curl -s localhost:5300/health | python3 -m json.tool
```

Das venv ist **bewusst getrennt** vom Flask-venv des Orchestrators: dort ist kein
Torch, und das soll so bleiben.

## Stufen

| Stufe | Ziel-Löser | Zustand | Abnahmekriterium |
|---|---|---|---|
| 1 | 2D-FDM (`ema_analysis`) | **in Arbeit** (AP1.0–1.2 erledigt) | rel. L2 auf `A` < 3 %, RMSE `Br_gap(θ)` < 3 % des Peaks, RMSE `Bt_gap(θ)` < 8 % des `Br`-Peaks, Inferenz < 100 ms |
| 2 | 3D-Elmer (`ema_em3d`) | offen | Momentfehler < 5 %, rel. L2 auf \|B\| < 8 % |
| 3 | kombiniert (2D-Feld als Eingang von Stufe 2) | offen | bei 50 % der Elmer-Daten ≥ so gut wie Stufe 2 bei 100 % |
| 4 | Kühlung (Blender/Mantaflow) | Skizze | offen (erst Laufzeit messen) |

Reihenfolge ist Absicht: die billige 2D-Stufe fährt Encoder, Datensatz-Pipeline,
Trainingsloop, Dienst und UI-Muster ein, die 3D-Stufe erbt sie.

## Der Encoder ist geteilt, nicht nachgebaut

`ema_analysis` / `ema_em3d` / `ema_topology` importieren auf Modulebene nur
`math`/`numpy`/`ema_topology` — gmsh und vtk werden lazy in den Funktionen geladen.
Deshalb sind sie **ohne FreeCAD/Elmer/Gmsh importierbar**, und der Encoder verwendet
die *echte* Rasterisierung des Orchestrators (`_rasterise(..., maps=True)`) statt einer
zweiten Implementierung, die auseinanderdriften könnte. `start.sh` setzt dafür
`PYTHONPATH` auf `../cae_orchestrator`.

Aus demselben Grund werden die Kennwerte mit den *vorhandenen* Funktionen gerechnet:
`_sample_airgap` (Luftspaltkurve), `compute_performance` (Kt/EMK),
`gap_metrics_from_profiles` (3D-Moment/Endeffekt, Arkkio).

## Was Stufe 1 vorhersagt — und was nicht

**Das Muster von `A`, nicht seine Amplitude.** `run_em_analysis:1050-1061` skaliert jede
Quelle ohnehin auf ihren *analytischen* Luftspalt-Spitzenwert
(`sf_mag = _analytical_Bgap/max|Br_magnet|`, `sf_arm = _analytical_Barm/max|Br_stator|`)
und verwirft dabei die Amplitude des Lösers — `_build_fv_matrix` sagt dasselbe in seinem
Docstring. Das Trainingsziel ist deshalb `A/RMS(A)`.

Das ist keine Vereinfachung, sondern die Bedingung dafür, dass überhaupt etwas lernbar
ist: die amplitudenbehaftete Form spannt über den Datensatz einen Faktor **1514**
(Magnetquelle = ±-Dipolschicht mit weitgehender Auslöschung, Statorquelle = kohärent
gefüllte Nuten, dazu die Polzahl p = 1…22). Bei sample-relativem Verlust ist der Gradient
∝ `1/‖t‖`; gemessen blieb das Netz damit bei `rel. L2 ≈ 0,95` stehen und lernte nicht
einmal 50 Beispiele auswendig.

Ein Lastfall braucht daher weiterhin **zwei** Auswertungen (Magnet-, Statorquelle), die
der Orchestrator wie heute mit seinen beiden analytischen Formeln zusammensetzt.

## Datensatz und Training (Stufe 1)

```bash
cd ../cae_orchestrator
python gen_fdm_dataset.py --dry-run                 # Selbsttests des Encoders
python gen_fdm_dataset.py --n 5000 --grid 512 --workers 4     # ~1 h, ~17 GB

cd ../physics_surrogate
.venv/bin/python data/dataset.py --check            # CRC aller NPZ (ZIP-Integrität)
.venv/bin/python data/dataset.py --verify 5         # Ziele gegen den echten Löser
.venv/bin/python train/train_fdm.py                 # Konfiguration: train/conf/fdm.yaml
.venv/bin/python train/evaluate.py                  # Abnahme auf dem Halteset
```

`--check` und `--verify` sind kein Zierrat: `--verify` hat die float16-Ablage der Quelle
als Fehlerquelle entlarvt, `--check` eine beschädigte NPZ unter 5199, die den
Trainingsloop erst nach Stunden zufällig getroffen hätte.

## Layout

```
data/     encode2d.py dataset.py domain.py         # Geometrie → Tensor, Laden, Gültigkeit
models/   unet2d.py                                # 2D-UNet (physicsnemo.Module)
train/    train_fdm.py evaluate.py common.py airgap_torch.py conf/*.yaml
service/  app.py predict.py                        # Flask :5300
tests/                                             # laufen ohne GPU
checkpoints/  datasets/                            # nicht versioniert
```

Das 2D-Netz ist selbst geschrieben, weil `physicsnemo.models.unet.UNet` **3D-only** ist
(`MaxPool3d`, „Expected 5D input tensor (B,C,D,H,W)" — verifiziert mit 2.1.1). Es leitet
aber von `physicsnemo.Module` ab, sodass der Checkpoint die Konstruktorargumente mitführt
und der Dienst ihn ohne Architekturwissen laden kann. Stufe 2 benutzt das Original.

## Nicht im Scope

- **Hoch-N-Superauflösung** (N=800–5000): der Sinn hoher Auflösung ist gerade das
  Auflösen des sub-pixeligen Luftspalts — das kann ein bei N=512 trainiertes Netz nicht
  erfinden. Der exakte splu-/AMG-Pfad bleibt daneben stehen.
- **Optimierer-Beschleunigung**: bei `N=140` beeinflusst die FDM-Lösung keine der 8
  Metriken in `ema_optimize._eval_geom` (`Kt`/`B_gap` sind analytisch, `T_maxwell` ist
  dort identisch 0, weil `Bt_gap` unterhalb N≈300 nicht auflöst). Erst ein Surrogat, das
  `Kt`/`B_gap` selbst lernt, würde dort etwas bringen.
- **Designer-/STEP-Geometrien** (`magShape:"custom"`): v1 nur parametrisch.
- **Gerechnete Kühlung**: der 💧-Mantaflow-Pfad liefert geometrische Benetzungs-Proxys,
  kein Temperaturfeld und keinen HTC. Ein Surrogat darauf erbt diese Grenze und darf
  nicht in `ema_thermal` einfließen.
