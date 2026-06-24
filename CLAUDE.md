# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Project Does

Browser-based design/analysis tool for interior-permanent-magnet (IPM) motors. The
user configures motor geometry in a web UI; a Flask backend then runs a fully
automated, non-interactive analysis chain: **FreeCAD geometry → 2D-FDM
electromagnetic field → CalculiX structural FEM (centrifugal) → lumped-parameter
thermal → drive-cycle loss integration**. An optional step generates a German PDF
report via a local LLM (Ollama). UI language and most domain output is German.

There is **no LLM in the analysis pipeline itself** — it is pure numerical/physics
code (numpy + external solvers). Ollama is only invoked for report prose, always
with the model `ministral-3:14b` (hardcoded in `ema_report.py` / `ema_experts.py`).

> Note: the old `app.py`/`agents.py` Streamlit text-to-CAD pipeline described in
> earlier docs no longer exists. The entry point is `server.py`.

## Running

```bash
./install.sh        # one-time: checks deps, builds venv, reports what's missing
./start.sh          # checks prerequisites, sets up venv, runs server on :5000
```

`start.sh` auto-opens the browser at **http://localhost:5000**. To run manually:
`source venv/bin/activate && python server.py`. Python deps are minimal:
`flask`, `numpy`, `matplotlib` (Agg backend, no display needed) — see
`requirements.txt`. There is no build step for the frontend (`ema.html` is vanilla JS).

No linters or CI. Two test scripts: `python smoke_test.py` — fast (~15 s, no
FreeCAD) sanity check of the main pure-Python paths (imports, topology, dq/MTPA,
FDM + saturation, connection assessment, deformation, script generation incl. a
rotor-only-FEM assertion); add `--cad` to also run one real FreeCAD build + rotor
FEM (minutes). `python test_topology.py` gates magnet geometry + the JS↔Python
`magnetLegs` mirror. Run `smoke_test.py` after any backend change.

**Prerequisites:**
- **FreeCAD 1.1.x built from source** under `~/freecad_1.1_quellcode` (via pixi).
  The `/opt/freecad-1.1` binary is actually 1.2 with a visualisation bug — **do not
  use it**. Everything routes through `pixi run --manifest-path ~/freecad_1.1_quellcode/pixi.toml -- build/release/bin/FreeCAD[Cmd] …` so the working 1.1.x build + its conda env are picked up.
- **CalculiX** (`ccx`) bundled in that same pixi env at `~/freecad_1.1_quellcode/.pixi/envs/default/bin/ccx`.
- **pixi** on PATH.
- *Optional (PDF reports only):* Ollama at `localhost:11434` with `ministral-3:14b`, plus `pandoc` and `pdflatex`.

### Hardcoded paths live in three places (keep them in sync)
- `start.sh:5-9` — `FREECAD_ROOT`, `FREECAD_CMD`, `CCX_CMD`, `PORT`
- `freecad_runner.py:14-19` — `FREECAD_ROOT`, `FREECAD_BIN`, `FREECADCMD_BIN`, `CCX_CMD`
- `server.py:9,147` — `PROJECTS_ROOT` (`~/cae_projekte`), `FREECAD_ROOT`

## Architecture

### Request / state flow

`server.py` is a Flask app serving `ema.html` and a REST API. It holds **two
module-level state dicts** that the frontend polls (there is no per-session state —
the server tracks a single active job):

- `_state` — analysis pipeline (`status`/`progress`/`log`/`results`/`project_dir`),
  plus `_frames` (list of base64 field-animation PNGs).
- `_report_state` — separate state for LLM report generation.

`POST /analyse` spawns a daemon thread running `ema_pipeline.run_pipeline(...)`,
returns `202`, and the UI polls `GET /status` and finally `GET /results`. Same
pattern for `POST /project/<id>/report` → poll `GET /report/status`. Long-running
work never blocks the request.

Key endpoints: `/analyse`, `/status`, `/results`, `/field/<n>` (animation frame),
`/cad_image/<name>`, `/chart/<name>`, `/open_freecad` (launches GUI FreeCAD on the
saved doc), `/export_step` + `/download_step`, `/projects`, `/project/<id>/load`,
`/cad_preview` (+ `/cad_preview/status`) — **staged-workflow** geometry-only build
(`ema_pipeline.build_cad_preview`: FreeCAD geometry + STEP + 2D images, NO analysis;
sets `_state["project_dir"]` so `/open_freecad`/`/download_step` work; own `_cad_state`
thread), `/smoke_test` (+ `/smoke_test/status`) — runs `smoke_test.py` in a subprocess
(`sys.executable`, ANSI-stripped streamed log, own `_smoke_state`),
`/project/<id>/recompute` — **selective stage re-run** ("vergessene Berechnung
nachziehen"): POST `{stages:[…], …current form payload}` runs only the chosen stages
(⊆ `{field, structural, thermal, drivecycle}`) via `run_pipeline(…, stages=…)`, merges
into the project's saved `results.json`, and reuses `_state`/`/status`/`/results` like
`/analyse` (preloads existing frames first via `_reload_frames_from_disk`),
`/project/<id>/template` (input payload for "Projekt aus Vorlage erstellen"),
`/project/<id>/report`, `/compare?ids=A,B,C,D`, `/project/<id>/delete`,
`/design_ai` (+ `/design_ai/status`, `_design_state`) — KI entwirft komplette Designs,
and `/design_optimize` (+ `/design_optimize/status`, `_design_opt_state`) — per-magnet
optimisation of a drawn design (see `ema_design_ai.py` / `ema_design_optimize.py`),
plus the value-free RAG-markdown report routes `/project/<id>/report/rag_md` (download)
and `/project/<id>/report/rag_md/add` (POST → knowledge base). All
file-serving routes guard against path traversal via `_safe_name()`.

### The pipeline (`ema_pipeline.run_pipeline`)

This single ~470-line function (`ema_pipeline.py:800`) is the heart of the system.
It writes progress into `state["log"]` via `_log(state, msg, pct)` and runs these
stages in order, each tolerant of failure (a failed stage logs a warning and the
rest continue where possible).

**Selective re-run** (`run_pipeline(…, stages=<set>)`): when `stages` is a subset of
`{"geometry","field","structural","thermal","drivecycle"}` the saved `results.json` is
loaded first and only the chosen (slow/optional) stages are recomputed + merged back —
gated by the local `_do(name)` helper (`stages is None` ⇒ full run, original behaviour).
The cheap foundational stages **always** run (EM static field + speed sweep, structural
sweep, shaft connection, advanced EM, materials/summary) because everything downstream
needs the EM operating point `perf` and they cost <1 s; geometry (FreeCAD) is never
rebuilt in partial mode (existing `motor.FCStd` reused). `results["em"]` is built with
`.update` (not replace) so a partial run preserves saved field-animation metadata when
"field" is skipped. Driven by `POST /project/<id>/recompute` + the **"🔁 Stufen
nachrechnen"** panel in the results tab (uses the current form payload, so the forgotten
calc can be (re)configured first; `loadProjectById` now also repopulates the form via
`/template` so the form matches the viewed project).

1. **Geometry** — `build_full_motor_script()` → `run_freecad_script()` saves
   `motor.FCStd` and exports STEP in the same subprocess.
2. **CAD images** — `_save_cad_images()` renders PNGs for the report.
3. **EM field (static)** — `ema_analysis.run_em_analysis()` at rotor angle 0;
   caches an open-circuit calibration factor `sf_ref` reused for all loaded frames.
4. **Field animation** — for each RPM in the sweep × N frames, re-solve the FDM
   with stator currents (`estimate_dq_currents`); frames go to `_frames` (base64)
   **and** disk (`frames/frame_XXXX.png`).
5. **EM speed sweep** — analytical `compute_performance()` across the RPM range.
6. **Structural FEM** — `build_rotor_fem_script(..., mesh_mm=struct_mesh_mm)` →
   CalculiX **once** at max RPM (worst-case centrifugal). Meshes **only** the `"Rotor"`
   solid (rotor iron) — the stator, magnets and **hairpin winding heads are excluded**
   from the strength calc by construction (separate `Coils_A/B/C` / `Stator` objects);
   the part selection requires `"Rotor"` and never falls back to another body. Mesh
   fineness is settable (`struct_mesh_mm`, Gmsh `CharacteristicLengthMax`). **Do NOT set
   `mesh.ElementOrder` explicitly** — it makes CalculiX emit a results-less `.frd`
   (FreeCAD's default order works). **Robustness ladder** (`build_rotor_fem_script`):
   thin iron bridges in aggressive multi-layer pockets make a single mesh+solve flaky
   (degenerate tets → results-less `.frd`). Mitigations: mesh-quality flags
   `OptimizeStd=True` + `MeshSizeFromCurvature=14` + `CharacteristicLengthMin` (NOT
   `OptimizeNetgen` — yields a 0-node mesh in this Gmsh build), and a **retry over mesh
   sizes** `[mesh_mm, ×0.65, ×1.4]` that re-meshes + re-solves until the `.frd` actually
   contains a ` -4  DISP` block (`_frd_has_disp`) — only then is an attempt a success;
   otherwise the FAILED `fem_result` carries an `attempts` list (surfaced in the pipeline
   log) before the analytical fallback. Result read from the `.frd` via `_parse_frd_full`
   (`run_freecad_script` also has a regex fallback for the markers, since a fine mesh's
   nonpositive-Jacobian dump can scramble the stdout lines).
6b. **Deformation post-processing (rpm² linearity)** — a centrifugal load is a body
   force ∝ ω² and linear-elastic FEM is linear in the load, so **both** displacement
   and von-Mises stress scale exactly with `(rpm/rpm_solve)²`. From the single solve
   `_deform_extract` + `_render_deform_single` produce high-res single images
   (`struct_img_px`, up to 5000 px) at **Nennlast** (`rpm_from`), **Maximaldrehzahl**
   (`rpm_to`) and **Berstdrehzahl** (`_burst_rpm` = `rpm_solve·√(Sy/σ_solve)`, where
   SF→1), all at one fixed exaggeration so the growth is comparable. `_deformation_video`
   renders an rpm 0→max ramp (fixed exaggeration, displacement growing with rpm²) to
   `frames_struct/` → `anim.mp4` (served via `/project/<id>/video/struct`).
   `results["deformation"]` = `{chart_b64, stats, images:[{tag,label,file,stats}],
   video:bool, burst_rpm, source:"fem"|"analytical"}`; the max-speed image is also copied
   to `charts/deformation.png` for the PDF report. **Fallback:** when CalculiX produces no
   valid result (thin/disconnected iron bridges in aggressive multi-layer topologies make
   the solve flaky), `_analytical_deform_arrays` supplies a rotating-disc (Lamé, plane-
   stress) deformation field instead, so the Verformung tab always shows the radial growth
   (`source:"analytical"`, image titled "Verformung (analytisch)"). The analytical case is
   axisymmetric, so it is **rendered smooth** by `_render_deform_analytical` — a filled
   annulus coloured by |u(r)| with undeformed + exaggerated-deformed OD/bore outlines —
   NOT the FEM per-node scatter `_render_deform_single` (which looked like a confusing
   point cloud and got mistaken for a mesh; the analytical model has no mesh and no magnet
   pockets — those exist only in the real FEM, which meshes the pocketed "Rotor" solid).
   `_deformation_video` takes `smooth_mat=mat` to use the same smooth renderer per frame.
   Magnetic settings have
   their structural mirror in the UI (mesh/img-px/video/frames), via
   `struct_mesh_mm/struct_img_px/struct_video/struct_frames`.
7. **Structural sweep** — analytical Lamé sweep; finds max safe RPM (SF ≥ 1.5).
   **FEM derating (important):** the analytical disc model misses the stress
   concentration at the thin iron bridges over the magnet pockets, so `max_safe_rpm`
   is additionally derated by the CalculiX result — since stress ∝ rpm² and the solve
   is linear, the FEM-safe speed is `rpm_solve·√(SF_fem/1.5)` and the **more
   conservative** of analytical/FEM is reported. Without this the summary showed
   `max_safe_rpm = rpm_to` even when the FEM safety factor was 0.21 (rotor yields).
   `results["summary"]` now also carries `structural_ok`, `safety_factor_fem`,
   `fem_rpm`, `fem_sigma_vm_MPa`.
7b. **Shaft–core connection** — `connection_assessment` (analytical, no FEM) →
   `results["connection"]` + `charts/connection.png`.
8. **Thermal LPTN** — `ema_thermal.run_thermal_analysis()` (steady + transient over 30 min).
9. **Drive cycles** — optional WLTP-3b / full-load / trailer / CSV, each with per-cycle thermal.

Output is assembled into a `results` dict and persisted to
`<project_dir>/results.json` + `meta.json`. Charts are stored both inline (base64
in `results`) and as files under `charts/`.

### Canvas Designer (`ema.html` tab `designer`)

Free-form rotor designer: a standalone tab where the user enters the main dimensions
(statorOD, rotorOD, shaftD, air gap → statorID, stack length, poles, slots,
conductors/slot) and **draws ONE half-pole** on a dedicated `#designCanvas` — straight
magnets (drag a line = position+length+tilt, thickness from a field, N/S polarity
toggle, mouse + synced list) and free-form **flux barriers** (click a polyline, width
field). The half-pole is **mirrored across the d-axis** and the pipeline patterns it
over all poles with **alternating polarity**. `dsnBuild()` compiles the master into a
**full pole** of `customLegs` (master + d-axis mirror) + `customBarriers`, spreads them
over the current `GEOM`/form payload as `magShape:"custom"`, and runs the normal
analysis via the shared `_runAnalysisPayload(payload)`. JS lives in the
`// Designer-Tab` block (all `dsn*` functions top-level); `switchTab('designer')` calls
`dsnActivate()`. No JS↔Python topology mirror needed — the canvas emits the legs
directly. **Pole-local frame**: x=radial out, y=tangential, master d-axis = +x.
`dsnBuild()`'s payload builder is factored into **`_dsnBuildPayload()`** (also tags
`design_brief`/`design_rationale`/`design_source` when an AI design is active) and the
mirror loop now **dedups** coincident legs. **It force-disables the parametric
`genFluxBarrierQ/D` flux barriers AND `genBalanceBolts`** from the Geometrie tab — a
custom/Designer geometry draws its own rotor air slots as `customBarriers`, so the
Geometrie-tab toggles must not bleed in and add a second, unrelated set of slots/holes.
Other Geometrie-tab settings (material, cooling, shaft connection, bearings) are still
inherited.

**KI-gestützte Auslegung (paralleler Pfad, im Designer-Tab).** ONE generator
("🤖 KI entwerfen", `dsnAiGenerate` → `POST /design_ai_ranged`) plus per-magnet
optimisation + a per-design parameter study. All build on the same canvas/`dsnBuild`
plumbing — see `ema_design_ai.py` / `ema_design_optimize.py` in the file map:
- **🤖 KI entwerfen** (`dsnAiGenerate` → `POST /design_ai_ranged`): the single design
  generator. The user gives an **optional brief** + **von–bis ranges** for **statorOD /
  Länge / Welle-Ø / air gap** (air gap clamped to **0.5–3 mm** via `AIRGAP_RANGE`) +
  variant count `#dsn_ai_n` (1–99). Per variant those four dims are randomly sampled and
  **hard-forced** (`_apply_ranged_dims`: statorID/rotorOD derived from the chosen gap,
  **bore capped at `STATOR_SPLIT`·OD ≈0.68 so a real stator wall remains for slots + winding
  copper — not a bare sleeve — with `slotDepth` derived from that wall**, magnets re-clamped);
  the LLM fills material/poles/slots + draws a **half-pole**
  magnets/barriers layout, the brief (if any) is prepended to each variant's design task.
  Calculation runs at the **fixed speeds 1000/5000/15000/20000 1/min** —
  `design_variants_ranged` returns `rpm_list`, the UI stashes it in `_dsnRangedRpm`, and
  `_dsnBuildPayload` forwards it as `payload.rpm_list` (run_pipeline honours an explicit
  `rpm_list` over the from/to/step sweep). `applyDesignToCanvas` loads a variant onto the
  designer form + `DESIGN`; `dsnRunAllVariants` runs them sequentially through `/analyse`
  and pre-selects them in the compare picker. (`design_variants(brief,…)` / `POST /design_ai`
  still exist as the brief-only path but the UI now always uses the ranged generator.)
  Each variant carries a fast **`quality`** verdict (gut/schlecht, `_quick_eval`); the list
  shows 👍/👎 badges + **per-variant 👍/👎 correction buttons** (`dsnSetVariantVerdict` →
  `v.userVerdict`, toggle back to auto). `_dsnVerdict` = user override else auto. The active
  variant is tracked in `_dsnActiveVariant`; `_dsnBuildPayload` attaches the corrected verdict
  as **`payload.design_label`** → `run_pipeline` → `ema_training.upsert(label=…)` (manual
  `label_source="user"`, overrides the pre-sort). **👎 variants are NOT computed:** in
  `dsnRunAllVariants` any variant whose effective verdict (`_dsnVerdict`) is `schlecht` is
  **skipped** from the `/analyse` runs and instead posted to **`POST /training/design_rejected`**
  ({payload, quick-eval metrics}) → `ema_training.upsert(label="schlecht")` with a synthetic
  `ki_abgelehnt_*` id (no pipeline run), so a thumbs-down design still lands in the training set
  as schlecht without burning a full solve.
- **🎯 Magnete fein-optimieren** (`dsnOptimize` → `POST /design_optimize`): per-magnet
  optimisation of the drawn coordinates; the best layout is drawn back onto the canvas.
  Metric/goal/constraint dropdowns come from `/optimize/meta` (`dsnLoadOptMeta`).
- **📈 Parameterstudie für diesen Entwurf** (`dsnParamStudy`): runs `ema_paramstudy` on
  the drawn geometry (`_studyDesignPayload` override + `_CUSTOM_STUDY_PARAMS` filter).

Every AI run lands in the training dataset (`design_source:"ki"`, brief in the
instruction). The LLM emits a **half-pole** (y≥0); the d-axis mirror stays in
`dsnBuild`/`_mirror_legs`, never in the model output. **Half-pole is enforced everywhere:**
hand-drawing clamps `_evMM` to y≥0 (can't draw below the d-axis), and `_validate_layout`
forces magnet offsets ≥0 AND clamps every barrier point to y≥0 — so master geometry always
stays in the upper half and the mirror produces the full pole cleanly.

### Magnet topology system (`ema_topology.py`)

The rotor magnet arrangement is a **single source of truth**: `magnet_legs(geom)`
returns `(list[Leg], MotorTopoMeta)`. A `Leg` is a magnet placement in the
pole-local frame (x=radial out, y=tangential): `r_pos, offset, tilt, length,
thickness, mag_mode ("perp"|"tangential"|"radial"), mag_sign, mag_rot,
placement ("interior"|"surface"), layer`. Supported `magShape` codes: `v, vasym
(asymmetric V — per-arm opening via `magAsym`°, 0 ⇒ symmetric `v`), vv, u,
delta, pmasynrm, spm, halbach, spoke, bar, custom` (`custom` = legs supplied
explicitly via `geom["customLegs"]` from the Canvas Designer; free-form barriers via
`geom["customBarriers"]` carved in FreeCAD + the FDM raster + the 2D section).
`MotorTopoMeta` carries analytical
hints (`n_legs_per_pole, eta_hint, flux_focusing, reluctance_dominated,
is_surface, salient_xi_hint`) so `ema_analysis._analytical_Bgap` /
`estimate_saliency` branch on the topology without string checks.

Both consumers build geometry from these legs: `ema_freecad.build_full_motor_script`
(interior → pocket box cut + magnet solids; surface → annular arc-shell sector on
the rotor OD, no cut; **`surface_flat`** → flat rectangular tile, no pocket/caps —
used by the **Halbach** array, which is `segPerPole` (default 6) STRAIGHT flat magnets
per pole tangent to the OD with rotating magnetisation) and `ema_analysis._rasterise`
(interior box mask + air caps / surface annular-wedge / `surface_flat` bare box,
magnetisation by `mag_mode`). **`ema.html` has a hand-mirrored
`magnetLegs(GEOM)`** (+ `_maxMagnetWidth`) — change both together. The **V-form**
pocket can be parametrised two ways (`geom["pocketMode"]`): `"position"` (default —
`magDepthRel` radial seat + `magWidth` length) or `"diameter"` (`pocketOuterD` /
`pocketInnerD` + `magAngle`: inner corner at `pocketInnerD/2` → `r_pos =
√(r_inner²−d_half²)`, length so the outer corner reaches `pocketOuterD/2`). Both
modes are mirrored in `_build_v`/JS `magnetLegs` and gated by `test_js_mirror_diameter_mode`. Magnet
segmentation (`nAx`, `nCirc`) scales magnet-eddy loss ~1/n² with a skin-depth
check in `ema_thermal.compute_losses`; advanced EM metrics (Ld/Lq, MTPA, Isc,
demag) are in `ema_analysis.compute_advanced_em` → `results["em_advanced"]`.

**Magnetisation orientation** (`geom["magOrient"]`, default `"transverse"`): the
**Magnet-Orientierung (Polung)** dropdown, transverse/longitudinal — a 90° swap of the
per-leg magnetisation. `"transverse"` = long magnet side carries the N/S poles (M ⊥
long axis, historical); `"longitudinal"` = short side carries the poles (M ∥ long axis).
(It does NOT control Halbach — that is its own `magShape`.) The 90° swap is applied
AFTER the per-`mag_mode` direction in **both**
`ema_analysis._rasterise` and the hand-mirrored magnetisation block in
`ema.html`'s `stepPhysics` (the `if … === "longitudinal": (mdx,mdy)=(-mdy,mdx)`
swap MUST stay identical in both, so the live preview and the FDM frames match).
It is not part of `magnetLegs`, so the topology mirror test does not cover it —
edit both spots together by hand.

Crucially, the FDM field is **calibrated** to the orientation-blind analytical
`B_gap` (`run_em_analysis`: `sf = B_analytical / pk_fdm`), which would otherwise
renormalise the rotation back out (the displayed amplitude would look unchanged —
only the live raw-SOR preview would react). So `ema_analysis._orient_factor(geom)`
scales `_analytical_Bgap` by the ratio of the radial magnetisation projection
mean|M·r̂|_chosen / mean|M·r̂|_transverse (perp: |sin tilt|→|cos tilt|; a flat
`bar` or surface `spm` rotated 90° → ~0 radial flux → B_gap floor). This makes the
FDM amplitude (and the analytical Kt/EMK that share `B_gap`) react to the toggle.
The **same factor is mirrored as `_magOrientFactor(GEOM)` in `ema.html`** and
multiplied into the live magnet amplitude `Jm_amp`, so the live preview scales in
the SAME direction as the FDM (verified equal py↔js for every topology).

### Echte 3D-Magnetfeldberechnung (Elmer FEM) — `ema_em3d.py` / `elmer_runner.py`

Eigenständiger On-Demand-Pfad **neben** dem 2D-FDM (der 2D-Löser bleibt unangetastet und
dient als Vergleichsanker). Liefert, was 2D nicht kann: **Endeffekte/finite Länge**,
**Schrägung (Skew)**, eine echte 3D-Feldlösung (VTU) und einen **2D-vs-3D-Vergleich**.

Ablauf (`ema_em3d.run_em3d`): `build_mesh` (Gmsh-OCC: konzentrische Zylinder je Radius +
Magnete als `addThruSections`-Loft aus `magnet_rects(geom)` — gespiegelt zur 2D-Rasterung
`ema_analysis._rasterise` — mit Skew = um `skew_deg` gedrehtem oberen Querschnitt; +
Luftspalt-Ring + axiale Luftkappen + Luftbox → `occ.fragment` → **Physical-Volumes per
Schwerpunkt/Radius/z getaggt**, Magnet-Match über exakten `getCenterOfMass` + Massengate,
weil konzentrische Ringe ihren Volumenschwerpunkt AUF der Achse haben; Luftspalt per
MathEval-Hintergrundfeld verfeinert) → `ElmerGrid 14 2` (MSH→Elmer-Mesh, `elmer_runner`)
→ `write_sif` (Magnetostatik: `WhitneyAVSolver` + `MagnetoDynamicsCalcFields` + VTU +
SaveScalars; Eisen μr=500 linear, Magnet μr=1.05 + per-Magnet `Body Force Magnetization`
= Br/μ0·Richtung, BC außen A×n=0) → `ElmerSolver` → `parse_results` (VTU via **vtk**:
Luftspalt-Br(θ) bei mehreren z → Endeffekt-Kurve, |B|-Schnitt z=L/2, Arkkio-Moment; +
`run_em_analysis`-2D-Vergleich). Server: `/em3d` (503 wenn `elmer_runner.ELMER_OK` falsch),
`/em3d/status`, `/em3d/vtu`, `/em3d/preview` (3D-Modell-Render OHNE Elmer, nur Gmsh+vtk),
`/em3d/paraview` (startet die ParaView-GUI auf der VTU via `paraview --data=`, wie
`/open_freecad`), `/em3d/vtp` (schlanke .vtp = Festkörper-Oberfläche + |B| via
`export_browser_vtp`) + `/vendor/<name>` (lokal eingebettete Libs). UI: Tab **🧲 3D-Feld**
mit **eingebettetem vtk.js-Browser-Viewer** (`openBrowser3d`, lädt `/vendor/vtk.js` lazy,
rendert die .vtp nach |B| eingefärbt — offline, kein ParaView nötig) + ParaView-Knopf.
**Geometriequelle wählbar** (`#e3_geomsrc` + `adoptEm3dGeom`/`_em3dGeom`): Geometrie-Tab
(`buildPayload`, parametrisch) ODER Designer/importierte STEP (`_dsnBuildPayload`,
`magShape:"custom"`+`customLegs` — `build_mesh`/`magnet_rects` über `magnet_legs` honoriert
custom). „📥 Geometrie übernehmen" snapshottet + zeigt eine Zusammenfassung; beim Tab-Öffnen
auto-übernommen. **Parametrische Reinheit (Bugfix):** `buildPayload` erzwingt `magShape`
aus dem Dropdown und **löscht `customLegs`/`customBarriers`** — sonst sickern aus einer
früheren Designer-Sitzung via localStorage in `GEOM` zurückgebliebene custom-Magnete in
die parametrische 3D-Übernahme („nur Durchmesser übernommen, Magnete ignoriert"). **Gestaffelte
Schrägung / Step-Skew** (`skew_segments` K + `skew_step_deg`, opts → `_magnet_pieces`): jeder
Magnet wird in K axiale Prismen geschnitten, Segment k um `k·step` um die Wellenachse gedreht
(Position, Achse UND Magnetisierung); das Rotoreisen bleibt rotationssymmetrischer Vollzylinder.
Kontinuierlicher `skew_deg`-Twist bleibt der Fall K<2. Das Magnet-Tagging matcht jetzt über
(gx,gy,**gz**) + Segmenthöhen-Massengate. **Flussbarrieren im 3D-Mesh** (`barrier_rects` —
parametrisch `genFluxBarrierQ/D` radiale Schlitze + Designer `customBarriers` Polylinien,
gespiegelt zur 2D-`_rasterise`-Logik): als **Luft-Prismen** (μr=1) mit derselben Staffelung
gebaut, in den Rotor gefragmentet und als `air` getaggt (COM+Massengate, 2-Pass: Magnete zuerst,
Barrieren aus dem Rest). **Statornuten im 3D-Mesh** (`slot_rects`, default an via
`opts.stator_slots`): `slots` **gerade** (nicht mit-rotierende) Luft-Prismen über die volle
Länge (`_extrude_straight`), zentriert auf `s·2π/slots`, halbe Winkelbreite `(2π/slots)/4`, Band
`[r_si, r_si+slotDepth]` — gespiegelt zur 2D-`_rasterise`-Nutung; in den Statorring gefragmentet →
echte Zähne, als `air` getaggt (3-Pass: Magnete→Barrieren→Nuten). Der Fluss bündelt sich dadurch in
den Zähnen (im 3D-Feld/Schnittbild sichtbar). **Zonale Netz-Verfeinerung (einstellbar):** ① Luftspalt+Umgebung *sehr
fein* (`gap_cl`, MathEval-Gauß-Band), ② Magnete+Barrieren+Umgebung *fein* (`mag_cl`, Distance→
Threshold auf ihren Oberflächen, Saumbreite `mag_grow`), ③ Rest *grob* (`mesh_cl`) — per gmsh
`Min`-Feld kombiniert; `_magnet_pieces` wird für Barrieren wiederverwendet (mdx/mdy/sign via
`.get`). UI: Felder „Magnet-/Barrieren-Mesh", „Übergangszone" + Zonen-Übersicht-Karte. **3D-Feld-Tab UI**: breiteneinheitliche `.e3-card`-
Stapelung (wie FEM-Ergebnisse), **FEM-Einstellungen mit `<details>`-Erklärungen** (fachlich +
laienverständlich + Wirkung auf Genauigkeit/Rechenzeit), Staffelungs-Felder. **Browser-Viewer
Schnittebene** (`_e3SetClip`/`_e3FlipClip`, vtk.js `vtkPlane` + `mapper.addClippingPlane` +
**`mapper.modified()`** — ohne das rendert vtk.js die Clip-Änderung NICHT neu, der Schnitt schien
„kaputt") — Achse X/Y/Z + Positions-Slider + Seitenwechsel, „in den Motor schauen". **Feldfarbe
im Browser-Viewer** (`_e3ApplyColor`): robuster Bereich übers 2./98.-Perzentil (`_e3Percentiles`)
statt min/max + **log-Toggle** + **|B|max-Slider** — sonst klebt das moderate Statorfeld (~0,3–0,8 T
Leerlauf) ganz unten in der Skala; das matplotlib-Schnittbild `_slice_image` nutzt analog
`PowerNorm(γ=0.5)` (Wurzelskala). **Netz sichtbar machen:** statisches **Netz-Querschnittsbild**
(`_mesh_slice_image` — schneidet die gmsh-.vtk MIT Luft bei z=L/2, `tripcolor` nach √Fläche
hell=fein → zonale Auflösung sichtbar, Bildschlüssel `em3d_mesh_slice`) + interaktiver **🕸 Netz**-
Toggle im Browser-Viewer (`_e3ToggleMesh`, `actor.setEdgeVisibility` — Oberflächen-Netz der
Festkörper; das Luftspalt-Volumennetz nur im Querschnittsbild, da die .vtp keine Luft enthält). **Geometriequelle NICHT klebrig:** beim Öffnen des 3D-Tabs wird
NICHT automatisch auf „Designer" umgeschaltet (das blendete den Geometrie-Tab dauerhaft aus →
„Geometrie ändert sich nicht"); Standard ist der Geometrie-Tab, `_e3SrcUserSet` merkt die bewusste
Dropdown-Wahl. `/em3d/vtp`-Fetch ist cache-gebustet. **Bericht-Integration:**
`run_em3d` mergt eine schlanke 3D-Zusammenfassung (`_persist_em3d_summary`) in `results.json`
(`results["em3d"]`, Bilder liegen in `charts/em3d_*.png`); `ema_report.build_context` zieht
`em3d`+Bilder, `_single_md_tables` baut die 2D-vs-3D-Tabelle (B_gap, Endeffekt Rand/Mitte,
Staffelung), `_prompt_for` ergänzt §8 (qualitativ) und `_ensure_em3d_section` garantiert den
bebilderten 3D-Abschnitt auch ohne LLM-Mithilfe — Standard- + agentischer Einzelbericht. **v1-Scope:**
lineare Materialien, Open-Circuit (Magnete); Lastfall/Spulen + BH-Kurve sind Folgeschritte. **Prerequisite:**
Elmer (`sudo apt install elmerfem-csc` via PPA `elmer-csc-ubuntu/elmer-csc-ppa`) + die
Python-Pakete `gmsh`/`vtk` (in `requirements.txt`). Mesh/sif sind ohne Elmer test- und
baubar (`test_em3d.py`). **Gotchas (alle gelöst, beim Ändern beachten):** `gmsh.initialize(
interruptible=False)` — sonst „signal only works in main thread" im Flask-Worker; Elmer-
Body-IDs **konsekutiv ab 1** (sonst „Body 1 missing"); Solver 1 = **Direct/MUMPS** (Iterativ
stagniert); Elmer-Ausgabepfade **relativ** zum cwd; gmsh-VTK `CellEntityIds` = **Physical-
IDs** (nicht Entity-Tags) für die 3D-Render-Klassifikation.

**Stator hairpin end-windings** (`ema_freecad.build_full_motor_script`, block "5.
HAIRPIN CONDUCTORS"): `conductorsPerSlot` (clamped even 2..12) radial conductor
lanes per slot, wired as U-pins from slot *s* to slot *s+coilPitch* (`coilPitch`
in slot steps, 0=auto=`round(slots/poles)`, chordable). Collision-freedom rests on
the crown's **radial split**: the "go" arm rises on the inner lane radius, the
"return" arm descends on the outer lane radius with a radial step at the apex, so
crossing arms are never at the same radius+z. The **winding head (crown)** is built
by `_crown_swept` as ONE smooth lofted solid ("Zugkörper", `Part.makeLoft(sections,
solid=True, ruled=True)`) through oriented rect sections (the `_bar` frame keeps the
cross-section flat), flaring **radially outward** by `windingHeadFlare` mm — much
better than the old box-chevron `_crown` (kept as fallback). **Use `ruled=True`**: a
smooth (`ruled=False`) loft balloons between sections and collides with neighbours
(OVERLAP went 0→270); ruled hugs the box envelope → collision-free. `windingHeadStyle:
"box"` forces the old chevron; any loft failure also falls back to it.
`build_full_motor_script(..., winding_debug=True)` emits each physical pin as its own
`Pin_NNN` object for the identity-aware pairwise-`common().Volume` collision check
(must stay OVERLAP=0). `conductorsPerSlot` also drives
`ema_thermal._conductors_per_slot` (copper volume + `R_phase`).

**Shaft–laminated-core connection** (`geom["shaftConnection"]`: `press` (default,
Querpressverband) | `spline` (Keilwelle) | `polygon` (P3G)): `_bore_cutter(r,z0,h)`
returns one profile solid used for BOTH the rotor bore-cut and the shaft body so they
mate (press → plain cylinder; spline → cylinder + `splineTeeth` radial teeth of
`splineToothDepthMm`; polygon → `polygonLobes`-lobe `r=r+polygonEccMm·cos(lobes·φ)`
extrusion). The connection is **assessed analytically, no FEM** (`ema_pipeline.
connection_assessment` → `results["connection"]` + `_connection_chart`): press →
Lamé shrink-fit joint pressure, transmittable torque and **loosening speed** (where
centrifugal bore growth cancels the interference); spline/polygon → flank/surface
pressure & torque capacity vs the cooling-based `ema_thermal.rated_torque`. Because a
non-cylindrical bore has no single Cylinder face, `build_rotor_fem_script` fixes the
**innermost faces** (smallest max-vertex-radius band) instead of "smallest Cylinder.
Radius" — keeps the centrifugal FEM valid for every profile. The 2D `_save_cad_images`
section also outlines the bore profile.

**Stepwise geometry — per-component build toggles** (`build_full_motor_script`, CAD
only; the EM/thermal/structural solvers compute from parameters and are **unaffected**):
boolean `geom` flags gate each named solid so the model can be built up incrementally
(e.g. first Welle + Rotorblech + Magnete + Hairpins, then add the rest). Core flags
default **on** — `genShaft`, `genRotorIron`, `genMagnets`, `genStatorIron`, `genHairpins`
(straight slot bars + weld tabs), `genWindingHeads` (the U-crowns, gated *inside* the pin
loop so legs can be built without the over-hang). Two **new optional extras** default
**off**: `genBearingA`/`genBearingB` (simplified ring on the shaft, outboard of the stack
at ∓z — `bearingODmm` 0=auto=`R_shaft+14`, `bearingWidthMm`, `bearingGapMm`) and
`genInsulation` (winding-head insulation paper — thin shell hugging the crown OD on +z,
`insulationThkMm`; needs hairpins + winding heads). The STEP export picks up whatever
solids exist; the **SAVE block guards a missing `Rotor`** (prints `CAD_VOLUME:0.00`) so a
rotor-less partial build still completes — but the structural FEM then has no `Rotor` to
mesh and that stage warns. UI: the **Komponenten (Geometrie-Erzeugung)** section in the
Geometrie tab (checkboxes + bearing/insulation params, `_updateComponentVis`); flags
round-trip through `buildPayload`/`applyPayload` like any other geom key. Smoke-tested in
`smoke_test.py` (script-gen + named-object presence per toggle).

**Balance-disc bolts** (`genBalanceBolts`, default off): symmetric through-holes + bolt
solids (`BalanceBolts` object) for the screws fastening the balancing discs through the
WHOLE stack. Count is **coupled to the pole number** (`n_bolts = poles`), placed on a
pitch circle (`balanceBoltCircleD` 0=auto=midway shaft↔rotor, `balanceBoltOffsetDeg`
angular versatz). Thread ≥ M4 via `balanceBoltThread` (`_THREAD_D` map) → clearance hole
= nominal Ø + 0.4 mm (M6 → 6.4 mm). Unlike the other CAD-only extras the **holes are cut
into the `Rotor` solid**, so the centrifugal FEM (which meshes the saved `Rotor`) sees the
holes too — the bore-fix face picker only grabs the innermost faces, so the hole faces
(at the larger pitch radius) are never fixed. The 2D `_save_cad_images` outlines the bolt
circle, and the **live `drawRotor()` canvas** draws the holes too (they rotate with the
rotor) — same hole logic mirrored in three places (FreeCAD / 2D / canvas). UI: checkbox +
thread/Ø/offset in the **Komponenten** section.

**Flux barriers** (`genFluxBarrierQ` / `genFluxBarrierD`, both default off): optional radial
AIR slots in the rotor iron, one per pole each, fully symmetric — **q-axis** (between poles,
angle `(i+0.5)·2π/poles`, cuts inter-pole leakage) and **d-axis** (pole centre, `i·2π/poles`,
between a pole's two V-arms), independently toggleable, shared `fluxBarrierWidth` (tangential
mm) + `fluxBarrierDepth` (radial mm). Outer edge a 2 mm bridge below the OD, depth inward.
Mirrored in **four** places: FreeCAD (`_flux_barrier_slots` → cut into the `Rotor` solid, so
the centrifugal FEM sees them), the FDM rasteriser (`ema_analysis._rasterise` carves air slots
that **rotate with `rotor_angle`** → the magnetic simulation reflects them), the 2D
`_save_cad_images` section, and the live `drawRotor()` canvas. UI: two checkboxes +
width/depth sliders in the **Komponenten** section (`grp_fluxbarrier`), round-trips via
`buildPayload`/`applyPayload`.

**Flux-density display scale** (`field_bmax`, default 0 = auto): UI number field (Live
tab) → payload → `ema_pipeline._field_frame(..., b_ceiling=field_bmax)` overrides BOTH the
physical |B| clip and the colour-scale ceiling (else `IRON_B_SAT_DISPLAY=2.1`). Honoured by
the animation frames, the report field maps and the live `render_preview_frame`; `vmax_ref`
takes the user value when set.

### Variants, comparison report, field modes, video

- **Variant sets**: `server.py` `/variants/{save,list,load,delete}` persist a JSON set
  (`schema_version`, `kind:"ema_variant_set"`, `variants:[{name,payload}]`, ≤10) under
  `~/cae_projekte/_variants/`. The browser (`ema.html`) also exports/imports the same
  schema as `*.emavars.json` and drives a sequential "Alle ausführen" batch via the
  existing `/analyse`+`/status`. `buildPayload()` is the single payload builder reused by
  both single-run and variants.
- **Comparison**: `/compare?ids=` (up to **10**) → `ema_compare.run_compare`. The
  comparison **report** is `ema_report.generate_comparison_report` (reuses ema_compare
  charts + an LLM ranking prompt → pandoc PDF) via `POST /compare/report` (status on
  `/report/status`, PDF on `/compare/report/download`). The report's **tables are
  built deterministically** (`_input_param_rows` → input-parameter table with differing
  rows flagged `●`; `_md_metric_table`; `_md_influence` → changed-inputs-vs-baseline +
  Δ%-per-metric), injected via `[TABELLE:parameter|kennwerte|einfluss]` placeholders
  (`insert_tables`, fallback-appended if the LLM omits them). The LLM writes only prose
  around them — `_strip_md_tables` removes any pipe-tables the local model writes itself
  (they break pandoc), so tables come ONLY from the injector.
- **Parameter-Tabelle (Spalten-Variation)**: a spreadsheet-style editor in the Vergleich
  tab (`ema.html`: `buildParamTable`/`renderParamTable`/`runParamTable`). `GET /param_schema`
  returns the curated param set from `ema_text2ema.SCHEMA` enriched with enum labels
  (material/topology/cooling). Column 1 = baseline from `buildPayload()`; up to 10 editable
  columns. `_ptabApply`/`_ptabRead` map each schema key into the full `/analyse` payload
  (`in_geom`→`payload.geom[k]`, `axialLen`→`payload.axial_len`, else top-level — the SAME
  names: `rotor_lam/stator_lam/hairpin_mat/magnet/cooling/rpm_from/rpm_to/load_nm/T_ambient`).
  "Alle Spalten rechnen" runs each column sequentially via `/analyse`+`/status` (like
  `runAllVariants`) and preselects the results in the compare picker.
- **Agentic comparison report (6 experts over variants)**: `POST /compare/report` with
  `{agentic:true}` (or `mode:"agentic"`) → `ema_report.generate_comparison_report_agentic`.
  **Deterministic skeleton** (the local model is unreliable at structure → it caused
  centered two-word lines, malformed tables, missing images): WE assemble the methodology
  (static LaTeX formulas — FDM `∇·(ν∇A)=−J`, MTPA torque, von-Mises/burst, LPTN, Lamé),
  ALL tables (`_md_param_table`/`_md_metric_table`/`_md_influence` + new
  `_md_magnet_thermal_table`/`_md_energy_table`/`_md_connection_table`), the overlay charts,
  and **per-variant image galleries** (`_copy_variant_images` copies each project's
  em_field/em_field_load/airgap/em_curve/deformation/connection/thermal PNGs into the report
  as `charts/vN_<key>.png`, `_gallery_md` lays them out). The LLM writes ONLY cleaned prose
  per section (`_section_prose` → `_clean_prose`: strips think/tables/headings, normalises
  paragraphs) plus the 6 comparative experts (`run_expert_agents_compare`, Vor-/Nachteile je
  Variante, `assemble_expert_section_compare` h2/h3). UI: "🧠 6-Experten-Recherche (PDF)"
  button (`makeComparisonReport(true)`). **Rendering workflow:** the report is split into
  CHAPTERS, each rendered to its own PDF (`_render_chapters_pdf`, `render_pdf(page_numbers=
  False)`) and merged with `pdfunite` (gs fallback) — a failing chapter falls back to a
  text-only render instead of killing the whole report. **Formatting hardening** (the local
  model caused "one syllable per line" on later pages): `_strip_md_tables` now also drops
  thematic-break lines (`---`/`***`/`___`) — in context pandoc misreads them as a 1-column
  ~5.6%-wide table — and table delimiter rows without a leading pipe; `_escape_pipes` escapes
  stray `|` in prose so a "Vorteil … | Nachteil …" line never becomes a narrow table.
  **Safety hardening of the prose** (the local model misread losses as output power, ignored
  mechanical failure, invented mass comparisons, and recommended a rotor that yields): a
  **deterministic verdict** (`_variant_verdict` → `_md_verdict_table`/`_md_warnings_block`,
  chapter "Bewertung & Eignung") is computed in code (FEM SF ≥ 1.5, magnet ≤ 150 °C, winding
  ≤ 180 °C) and is authoritative over the LLM text; the LLM gets `_PROSE_GUARDRAILS` (losses
  ≠ power, don't invent numbers, never recommend a variant flagged NICHT einsetzbar) plus the
  verdict in its ranking context, and the loss key is relabelled `verlustleistung_abwaerme_W`.
  Model is selectable from the Vergleich tab (`#cmp_model`: ministral-3:14b / gemma4:26b / …),
  passed as `model` to `/compare/report`.
- **Bewertung gut/schlecht + Trainingsfile**: every finished analysis appends a JSONL line
  to `ema_training` (see file map). The Ergebnis-Tab shows a rating block (`renderRating`/
  `setRating` → `POST /project/<id>/rating {label,comment}`; `GET` returns the stored label +
  an `auto_label` heuristic suggestion). The Vergleich tab has a `📚 LLM-Trainingsdaten`
  panel (`GET /training/stats`, `GET /training/download`). Rating is rendered from both
  `loadResults` (fresh run) and `loadProjectById` (loaded project).
- **Field-visualisation modes** (`field_modes` in the `/analyse` payload, default
  `["rotate"]`): `rotate` (rotor turns), `current_angle` (rotor fixed, stator current
  vector β sweeps → armature reaction), `load_ramp` (rotor fixed, load 0→full). Each is
  rendered to its own subdir (`FIELD_SUBDIRS` = frames/frames_react/frames_load, kept in
  sync between `ema_pipeline` and `server`). `server._frames` is a **dict of buckets**;
  `/field/<n>` is a legacy alias for `/field/rotate/<n>`. Each frame set is encoded to
  `anim.mp4` via `ema_pipeline._make_video` (ffmpeg) → `/project/<id>/video/<mode>`.
- **Hollow shaft**: `shaftBoreD` (0=solid) hollows the *display* shaft in
  `build_full_motor_script` and reduces shaft mass in `ema_thermal`; the FEM shaft in
  `build_rotor_fem_script` stays solid so the bore-face fixed constraint is unchanged.
- **Tests**: `test_topology.py` (run `python test_topology.py` or pytest) gates geometry —
  SAT no-overlap, within-bounds, and an automatic JS↔Python `magnetLegs` mirror check
  (extracts the `// <<MIRROR-START/END>>` block from `ema.html`, needs `node`).

### Projects

Every run creates `~/cae_projekte/<timestamp[_name]>/` (`create_project_dir`) holding
`motor.FCStd`, `motor.step`, `results.json`, `meta.json`, and `cad_images/`,
`charts/`, `frames/` subdirs. `meta.json` also stores the **full input payload**
(`meta["payload"]`, minus the one-shot `cycle_csv`) so a project can be used as a
template. `load_project` restores a finished project (incl. re-reading frames from
disk into `_frames`) without recomputing. `ema_compare.py`
overlays up to 4 projects' curves. The **project gallery** (`ema.html`
`openProjectGallery` → `📂 Projekt-Browser`, also `#projects` deep-link) is a modal
grid of cards (cross-section thumbnail via `/project/<id>/thumb`, the high-res EM
field map via `/project/<id>/em_field` — `charts/em_field.png`, click-to-open at full
res — topology, dims, headline metrics, plus a **“📄 Bericht öffnen”** button +
badge when a report PDF exists) fed by `GET /projects?detail=1`. Card flags
`has_em_field` / `has_report` / `report_file` come from the project dir; the report
link hits `GET /project/<id>/report/download?mode=latest` (`_latest_report` = newest
of `bericht.pdf` / `bericht_agentisch.pdf` by mtime). Report generation keeps **only
the latest** report — `make_report`'s thread deletes the other-mode PDF after a
successful render. The `detail` flag also adds topology
+ metrics read from `results.json` (mtime-cached in `_SUMMARY_CACHE`; the bare
`/projects` call stays light for the dropdown/compare picker). A card's “Ergebnisse
ansehen” calls `loadProjectById` (shared with the dropdown's `onProjectSelect`); a
card's **“📋 Als Vorlage verwenden”** calls `useAsTemplate` → `GET
/project/<id>/template` → `applyPayload` (the inverse of `buildPayload`: repopulates
the whole form from the saved payload, then `switchTab('geo')`). Legacy projects
without `meta["payload"]` are served a `_reconstruct_payload` (geom + run settings,
material keys recovered from labels; `reconstructed:true`).

### FreeCAD subprocess protocol

`freecad_runner.run_freecad_script(code, timeout)` writes `code` to a temp `.py`,
runs it via `_pixi_cmd("build/release/bin/FreeCADCmd", path)` (cwd must be
`FREECAD_ROOT`; `ccx` dir prepended to PATH), and parses stdout for marker lines:

- `CAD_SUCCESS`, `CAD_FACES:<json>`, `CAD_VOLUME:<float>`, `SAVED:<path>`
- `STEP_SAVED:<path>` / `STEP_FAIL:<msg>`
- `FRD_FILE:<path>`, `FEM_RESULT:<json>`

Generated FreeCAD scripts must print these markers themselves. The FEM script
(`freecad_runner.build_fem_script` and the rotor FEM in `ema_freecad.py`) builds an
Analysis with material + fixed + force/centrifugal constraints, meshes with Gmsh,
runs `FemToolsCcx`, and emits the `.frd`. **Force/load magnitude uses
`App.Units.Quantity("<n> N")`** — FreeCAD's internal unit is mN, so this conversion
is required.

### FDM field solver (`ema_analysis.py`)

Solves `∇·(ν∇A) = −J` on a 2D grid (UI: 100–800 px). `_solve_fdm` builds a
finite-volume 5-point operator (harmonic-mean face ν, Dirichlet A=0 on the 10 %
air margin) and solves it with a **direct sparse factorisation** (`scipy splu`),
so it is exact at any resolution — no iteration tuning, and the air gap/teeth
resolve cleanly at high N. The operator depends only on `mu` (geometry + rotor
angle), **not** on the stator/magnet currents (those are the RHS `J`), so the
factorisation is **cached by `(N, hash(mu))`** in `_LU_CACHE` and reused across
every RPM / current-angle / load step at the same rotor position; the rotate
sweep re-uses ~`n_frames` angles across all RPMs (N=600 ≈ 3 s to factor, <0.1 s
per subsequent solve). `run_pipeline` calls `clear_lu_cache()` in its `finally`.
Above N≈2500 (`_DIRECT_N_MAX`) the direct factorisation needs too much RAM, so
`_solve_fdm` dispatches to `_solve_fdm_amg` — CG-accelerated `pyamg`
smoothed-aggregation AMG (Ruge-Stüben fallback for hard µ-jumps), with the
multigrid hierarchy cached by `(N, hash(mu))` in `_AMG_CACHE` exactly like the LU
cache. pyamg is optional (guarded import); without it the single-frame preview is
capped at 2500 px. This branch only serves the high-res single-frame preview
(`render_preview_frame`, up to 5000 px), not the animation sweep.
The legacy iterative `_solve_fdm_sor` remains as a SciPy-absent fallback.
Permanent magnets are modelled as equivalent surface (boundary) currents; iron
µr = 500, magnet µr = 1.05. The raw result is scaled to physical Tesla via
`_analytical_Bgap()`. **Split calibration under load:** the FV operator depends
only on `mu`, so the field is *linear* in the source `J` and `A = A_magnet +
A_stator`. The magnet equivalent currents (dipolar curl-of-M) and the stator slot
currents (net current per slot) have very different field-transfer gains, so
`run_em_analysis` solves the two parts **separately** (the 2nd `_solve_fdm` re-uses
the SAME cached factorisation — just a back-substitution) and scales each to its
own analytical air-gap target: magnets → `_analytical_Bgap`, armature →
`_analytical_Barm(geom, i_pk)` (peak fundamental MMF across the Carter q-axis gap).
A single shared factor (the old behaviour) made the loaded stator field blow up to
>100 T and bury the magnets — or, self-calibrated from the combined peak, scaled
the magnets down to ~0 (the "magnets ignored under load" bug). `sf_ref` is now the
open-circuit *magnet* calibration only; the armature part self-calibrates per frame
(its scale is geometry-only since both `B_arm` and `pk_stat` are linear in current).
Magnet `Br`/`mu_r` are injected by monkey-patching module
globals `ema_analysis.Br_NdFeB` / `MU_R_MAG` at the top of `run_pipeline` and
**restored in its `finally` block** — be careful editing that pattern.

**Nonlinear B-H saturation (display):** the base solve is linear (`MU_R_IRON=500`,
no saturation), so iron shows unphysical >2 T at tooth corners. `run_em_analysis(...,
saturate=True)` runs a fixed-point µ-pass (`_saturate_field`): lower µ where the
physically-scaled |B| exceeds the steel knee `B_SAT_IRON` (≈2 T), re-solve (~4 iters,
under-relaxed) → flux redistributes and |B| caps near saturation. It replaces ONLY
the displayed field (`Bx/By/B_mag/A`), anchored to the same air-gap peak; the
quantitative `Br_gap/Bt_gap` (torque) keep the rigorous linear split. Used for the
single high-res `render_preview_frame` (animation frames stay linear for speed).
Independently, `_field_frame`/`_field_vmax` clip the heatmap + colour-bar to
`IRON_B_SAT_DISPLAY` (2.1 T) so even linear frames never show an unphysical scale.
**Air domain:** the rasteriser pads `AIR_DOMAIN_FACTOR=1.25`× the stator OD (was
1.1) so the outer Dirichlet `A=0` boundary is clear of the iron (less squared-off
external/leakage field lines); costs ~14 %/N machine resolution — raise N for a
sharp air gap. **Outside-stator masking (`_field_frame`):** the padded air ring
carries a smooth `A` gradient down to the artificial `A=0` boundary, so its
percentile-spaced contour lines looked like flux "escaping" the stator even though
`|B|` there is ~0. The plot now masks both `B` (heatmap) and `A` (field-line
contours, via `nanpercentile`) for `r > 1.02·statorOD/2`, so field lines stay inside
the machine — physically the back-iron yoke (µr≈500 ≫ air) confines the flux.

**Air-gap Br/Bt profile (`_sample_airgap`, `_rasterise` carve).** A real 0.5–1 mm
gap is sub-pixel at usable N (0.7 mm vs ~1.2 mm/px at N=300), so the rotor & stator
iron rings touch and the gap is unresolved — sampling the curl-of-A there reads the
*iron* field, where the radial component is suppressed and the staircased round rim
injects a huge SPURIOUS tangential one (the old chart showed B_t wrongly dominating
B_r — physically impossible). Fix is two-part: (1) `_rasterise` opens a clean air
band of `max(gap, AIRGAP_MIN_MM=2.5 mm)` just BELOW the stator bore by removing
rotor-rim IRON only (magnets/slot air kept; the stator iron at `r_si` stays so its
BC keeps B_r dominant) — physical width ⇒ a no-op at low/animation N, resolved once
N is high. (2) `_sample_airgap` reads the profile just inside the bore: **B_r =
(1/r)·∂A/∂θ** (a derivative ALONG the gap circle ⇒ immune to the radial staircase,
robust at any N), and **B_t = −∂A/∂r** via an angular-harmonic two-circle fit in the
resolved band (spike-free; falls back to ~0 when the band is sub-pixel). The static
air-gap chart (`ema_pipeline` `em0`) is solved at `N≥AIRGAP_PROFILE_N=700` regardless
of `fdm_resolution` (sf_ref captured there is unused; frames self-calibrate). B_r is
robust+correct for all topologies; **B_t is only an approximation** on this Cartesian
grid (some geometries still give B_t≈B_r), so `_airgap_chart` plots B_r primary and
B_t secondary (dashed, "Näherung"), clipped to `|B_t|≤peak|B_r|`. Surface/spoke/delta
topologies legitimately carry more tangential flux.

**MTPA operating point (`estimate_dq_currents`):** below base speed a salient IPM
(ξ=Lq/Ld>1) now follows MTPA — a negative d-axis current adds reluctance torque
T_rel=1.5·p·(Ld−Lq)·i_d·i_q, so the displayed/loss currents reflect the efficient
point (i_d<0), not pure i_q (i_d=0). Non-salient rotors (ξ≈1) keep i_d=0. Above base
speed field-weakening adds a demagnetising d-current on top (continuous at rpm_base).
This feeds all consumers (field frames, thermal, drive cycle).

### Magnet-geometry clamping (`ema_freecad._max_magnet_width`)

V-shaped magnet pockets are auto-shortened to the longest length that still fits the
rotor: solves a quadratic so the outer pocket corner stays ≤ `R_rotor − bridge` (2 mm).

### Materials

All material tables are dicts at the top of `ema_pipeline.py:50-78`: `LAMINATES`
(rotor/stator electrical steel, with E/nu/yield for FEM), `HAIRPIN_MATS` (winding
conductors), `MAGNETS` (Br, µr, T_op_max, T_curie). `MATERIALS` is a backward-compat
alias of `LAMINATES`. `_mat_fc()` converts a laminate dict into the FreeCAD material
dict passed to the FEM script.

## File Map

| File | Role |
|---|---|
| `server.py` | Flask backend: serves `ema.html`, REST API, threaded job state, FreeCAD GUI/STEP launching |
| `ema.html` | Single-file vanilla-JS browser UI (no build). Workflow-tab layout: a top tab bar (`switchTab`, tabs `geo/betrieb/calc/live/results/report/compare`, `#hash` deep-linkable) over `#workspace` = `#panel-area` (active panel) + draggable `#vsplit` + persistent `#preview-pane` (live `#simCanvas`, hidden on results/report/compare) + draggable `#hsplit` + `#footer` (staged-workflow buttons `#btn_cad_preview` (🧊 CAD ansehen → `startCadPreview`) · `#btn_smoke` (🧪 Smoke-Test → `startSmokeTest`) · `#btn_analyse` (⚙ Echte Berechnung), all sharing the `_wfModal`/`_pollWf` overlay helpers for the first two, plus `#analysis-progress`; drag `#hsplit` taller to reveal the full `#progress-log`). Inputs grouped into `.tab-panel`s; `results`/`report` tabs gated `disabled` until an analysis finishes. `#vsplit`/`#hsplit` (`initSplitters`) resize preview width / footer height and call the canvas `resize()` live. The preview overlay has a pause button (`#ov_play` → global `toggleSim`/`_syncSimUI`, mirrors the Live-tab `#btn_play_pause`) so rotation can be stopped from any input tab |
| `ema_pipeline.py` | Pipeline orchestrator (`run_pipeline`) + material tables + all chart builders |
| `ema_topology.py` | Single source of truth for rotor magnet placement (`magnet_legs`, `Leg`, topology labels) — consumed by `ema_freecad` + `ema_analysis`; mirrored by JS `magnetLegs` in `ema.html` |
| `ema_freecad.py` | FreeCAD script generators (rotor, full motor, rotor FEM); interior pockets + surface arc magnets from `magnet_legs`; parametric hairpin end-windings (`conductorsPerSlot`/`coilPitch`, collision-free radial-split crowns) |
| `freecad_runner.py` | FreeCAD subprocess wrapper + marker parsing + generic FEM script builder |
| `ema_analysis.py` | 2D-FDM EM field solver + analytical performance (torque, EMF, saliency, d/q currents) |
| `ema_thermal.py` | 6-node lumped-parameter thermal network (steady + transient + per-cycle) |
| `ema_drivecycle.py` | Drive cycles (WLTP-3b, full-load, trailer, CSV) + drivetrain + energy integration. Trailer is user-parametric: `trailer_mountain_cycle(max_grade_pct)` (steepest uphill = that grade %, slope arrays stored in **degrees**) + `trailer_vehicle(base, trailer_mass_kg, n_axles)`; the `/analyse` payload carries `trailer:{mass_kg,n_axles,grade_pct}` |
| `ema_compare.py` | Multi-project comparison overlays |
| `ema_report.py` | LLM → Markdown → pandoc → pdflatex PDF report (standard + agentic modes). Embeds project images via `[BILD:key]` placeholders → `insert_images` (`build_context` `pairs`); the EM section features the FDM field maps `em_field` (Leerlauf) + `em_field_load` (Last) rendered by the pipeline's field stage to `charts/em_field*.png`, plus `airgap`/`em_curve`. Unknown keys (legacy projects without an image) are stripped cleanly; for an old project, re-run the **field** stage (Stufen nachrechnen) to generate them. **Formatting:** the prompt asks for LaTeX math (`$…$` inline, single-line `$$…$$` display — `_normalize_paragraphs` treats `$$` lines as structural so they aren't merged); `render_pdf` injects `_report_header.tex` (`ragged2e` document-wide → left-aligned, fixes the "1–2 words per line" justified-stretch around long unit/formula tokens; `float`+`[H]` to pin figures); `_strip_md_tables` is applied to standard + agentic output too (local models emit malformed centered pipe-tables). **NO numeric values in the prose** (the local model routinely mis-assigns them → nonsense): the standard + agentic single-project reports inject a comprehensive deterministic `[TABELLE:kennwerte]` (`_single_md_tables`, grouped by domain) right after the summary, the prompt demands QUALITATIVE prose + symbolic-only formulas, and `_strip_value_numbers` removes any straggler number+unit token (keeps the unit, inserts `…`; material codes like `M270-35A`/`N52` are protected). `_strip_value_numbers` also runs inside `_clean_prose` so the comparison/agentic comparative prose is value-free too |
| `ema_chat.py` | Ollama Q&A over results/comparison (`chat_results`/`chat_compare`); compacts results JSON (strips base64/frames). Each project-scope chat is grounded on a per-project **`_machine_datasheet(meta)`** (topology/dims/winding/magnets/materials/operating point, built from `meta.json` — `results.json` holds only outputs, so the server loads `meta.json` from `project_dir` and passes it to `chat_results`). Served by `POST /chat` (`scope:"project"\|"compare"`); UI is the floating `💬 Chat` widget in `ema.html`. **RAG:** `_rag_doku(message)` injects retrieved `doku`-category snippets from `ema_rag` into both system prompts (best-effort) |
| `ema_optimize.py` | LLM-steered target-value optimisation. `evaluate_fast` scores a candidate WITHOUT FreeCAD/FEM (EM at low N + analytical Kt/torque + steady LPTN thermal + analytical struct sweep + analytical mass, ~0.5 s). Its inner geom→metrics core is factored into **`_eval_geom(geom, axial, mats, op, …)`** (works for ANY `magShape` incl. `"custom"`); `evaluate_fast` = `_apply_params` (parametric `FREE_PARAMS`) then `_eval_geom`. The per-magnet optimiser (`ema_design_optimize`) reuses `_eval_geom`/`_fitness`/`_violation`/`_ollama_chat`/`_extract_array`. `optimize(spec)` seeds + lets `ministral-3` propose batches over `FREE_PARAMS`, deterministic clamp + feasibility/fitness pick the best feasible design. Served by `POST /optimize` (threaded, `_opt_state`) + `GET /optimize/status` + `GET /optimize/meta`; UI is the `🎯 Zielwertoptimierung` modal (Berechnung tab / `#optimize`). "Übernehmen" applies the best params to the form for a final full pipeline run |
| `ema_paramstudy.py` | **Parameterstudie bei fester Drehzahl**: `run_study(payload, param, lo, hi, steps=100, rpm)` sweeps ONE `ema_optimize.FREE_PARAMS` parameter x→y in N steps at a fixed speed and plots EVERY result metric over the parameter (small-multiples grid). Reuses `ema_optimize.evaluate_fast` (FreeCAD/FEM-free, geometry varied per step), so 100 points cost ~50 s. Served by `POST /param_study` (threaded, `_study_state`) + `GET /param_study/status`; UI is the **„📈 Parameterstudie"** panel (Berechnung tab) — parameter dropdown filled from `/optimize/meta`. **Custom (Designer/KI) designs:** `run_study` honours `geom.customLegs` (they ride through `evaluate_fast` unchanged), so the Designer-Tab button **„📈 Parameterstudie für diesen Entwurf"** (`dsnParamStudy`) runs the same study on the drawn geometry; the UI then restricts the dropdown to the geometry-effective params (`_CUSTOM_STUDY_PARAMS` = axial/airgap/slotDepth/p/magGap — magnet-shape params are no-ops on freehand magnets) and shows a banner (`_studyDesignPayload`, reset via `dsnClearStudyDesign`) |
| `ema_design_ai.py` (KI-Auslegung) | **KI entwirft komplette Maschinen aus einer Beschreibung** (Designer-Pfad). `design_variants(brief, n=3, model)` → list of full designs: parametric scalars (via `ema_text2ema.SCHEMA`+`_validate`) **plus** a freehand HALF-pole `magnets`/`barriers` layout in canvas format (`{r,off,ang,len,thick,pol}` / `{pts,width}`, pol-local mm) **plus** `begruendung`. RAG-grounded on `maschinen` references (`ema_rag.context_for`). **Robustness:** the local LLM call uses Ollama **`format:"json"`** (otherwise the combined schema's JSON is frequently broken — decimal commas, comments) + a lenient `_extract_obj` (strips `//`/`/* */` comments + trailing commas). `_validate_layout` clamps every magnet inside the rotor (true fit-length via the quadratic, NO 5 mm floor — magnets that cannot fit are dropped), **keeps everything in the half pole** (magnet offset ≥0, barrier points clamped to y≥0), **drops magnets that overlap an already-kept magnet** (`_obb_overlap` SAT on the rotated rectangles, `_MAG_MAG_CLEAR` gap — any count is fine, 1 pole-sized or many small, just no intersection; the d-axis mirror is deliberately NOT checked so a V/U arm may sit next to its own reflection) and **drops flux barriers that overlap a magnet** (`_polyline_hits_magnet` samples each slot polyline against every magnet AND its d-axis mirror, clearance `BARRIER_MAGNET_CLEARANCE_MM` + half the slot width — a barrier carved through a PM is nonsense geometry; the LLM prompt also forbids it); if the freehand layout is empty/unusable, `_legs_to_canvas(_params_to_geom(params))` synthesises a valid half-pole from the parametric topology (`magnet_legs`) so a drawable design ALWAYS results (`fallback:true`). **Qualitäts-Vorsortierung + Regenerierung:** jeder Entwurf wird sofort FreeCAD/FEM-frei bewertet (`_quick_eval` → `ema_optimize._eval_geom` auf der gespiegelten Custom-Geometrie + dieselbe Heuristik wie `ema_training.auto_label` → `verdict` gut/schlecht); fällt er **„schlecht"** aus, generiert `design_variants` mit gezieltem Mängel-Feedback einen neuen (bis `max_regen`=2 Nachversuche je Slot, `_gen_one` mit Parametrik-Fallback), nimmt den besten Versuch (`_quality_score`: gut>unbekannt>schlecht, dann B_gap) in `variants` (mit `quality`-Urteil) und sammelt die verworfenen in `rejected`. Return: `{variants, rejected, regenerated, rag_used, model}`. The per-slot generate→presort→regenerate loop is factored into **`_gen_slot(... post_fn=None)`**. **Bereichs-/Zufalls-Entwurf (the UI's only generator now):** `design_variants_ranged(ranges, n, …, brief="")` samples statorOD/axialLen/shaftD **and the air gap** from the user's von–bis ranges per variant (air gap clamped to `AIRGAP_RANGE`=0.5–3 mm), prepends the optional `brief` to each variant's task, **hard-forces** the dims via `_apply_ranged_dims` (statorID/rotorOD derived from the gap, **bore capped at `STATOR_SPLIT`·OD so the stator keeps a real wall for slots+back-iron instead of becoming a sleeve**, `slotDepth` set from that wall, magnets re-clamped) while the LLM fills the rest + draws magnets/barriers, and pins the eval to the fixed speeds `RANGED_RPM_LIST=[1000,5000,15000,20000]` (returned as `rpm_list`). Served by `POST /design_ai` (Body `{brief,n,model?,max_regen?}`) + `POST /design_ai_ranged` (Body `{ranges,n,model?,max_regen?}`), both threaded on `_design_state` + `GET /design_ai/status` |
| `ema_design_optimize.py` (Per-Magnet-Optimierung) | **Fine-optimises the DRAWN magnet coordinates** of a custom design (vs `ema_optimize` which varies global parametric fields). Vector = per master-leg `{r,off,ang,len,thick}` + barrier widths, bounds from rotor geometry. `_apply_vec` rebuilds master magnets → `ema_design_ai._validate_layout` (re-clamps) → `_mirror_legs`/`_mirror_barriers` (d-axis mirror, identical to `dsnBuild`, with **dedup** of coincident legs) → `magShape:"custom"` geom → `ema_optimize._eval_geom`. Pole symmetry preserved (only the master half-pole is perturbed, mirror regenerated per candidate). `optimize_custom(spec)` reuses the `ema_optimize` loop/fitness/LLM-propose. Served by `POST /design_optimize` (threaded, `_design_opt_state`) + `GET /design_optimize/status`; result's `best_magnets` drawn back onto the canvas |
| `ema_rag.py` | **Lokale Wissensbasis (RAG)** unter `~/cae_projekte/_rag/index.json`. EINE Basis, pro Dokument eine **Kategorie** `maschinen` (Referenzmaschinen → `ema_text2ema.derive`) oder `doku` (Doku → `ema_chat`). Embeddings über Ollama `/api/embeddings` (`nomic-embed-text`), Chunking ~900 Zeichen/150 Überlappung, Retrieval = Cosine (numpy). `add_text`/`add_file` (txt/md/csv direkt, **PDF via `pypdf`**), `search(query, category, k)`, `context_for(query, category)` (Prompt-Injektion), `list_documents`/`delete_document`/`stats`. Beide Konsumenten injizieren **best-effort** (ohne Ollama/Embeddings läuft alles weiter ohne Kontext). Server: `/rag/list`, `/rag/add`, `/rag/upload`, `/rag/delete/<id>`, `/rag/search`; UI: **„📚 Wissensbasis"**-Modal (Geometrie-Tab / `#rag`) |
| `ema_text2ema.py` | Text → parameter set. `derive(description)` asks `ministral-3` to fill the `SCHEMA` fields, then `_validate` clamps every value to its range/enum and enforces radial ordering (statorOD>statorID>rotorOD>shaftD>shaftBoreD, ~0.7 mm air gap, slots≈6·p) so the result always loads. Served by `POST /text2ema`; UI is the `🧠 Text → Auslegung` modal (Geometrie tab / `#text2ema`) → "In Formular übernehmen". **RAG:** retrieves `maschinen`-category reference machines from `ema_rag` and injects them into the prompt (returns `rag_used`); no web yet |
| `ema_experts.py` | Agentic report mode: parallel per-section LLM expert agents. `run_expert_agents` (6 experts on ONE project) + `run_expert_agents_compare`/`assemble_expert_section_compare` (the SAME 6 experts judge ALL variants **comparatively** with Vor-/Nachteile je Variante — used by the agentic comparison report) |
| `ema_training.py` | Fortlaufendes **LLM-Trainingsfile** (`~/cae_projekte/_training/dataset_sft.jsonl`, instruction/input/output JSONL). `run_pipeline` ruft nach dem Speichern `ema_training.upsert(project_id, meta, results)` auf (label=null) — **upsert per project_id** (kein Duplikat beim Nachrechnen). `instruction` = `ema_chat._machine_datasheet(meta)` (Geometrie+Material); für **KI-Entwürfe** stellt `build_instruction` die natürliche-Sprache-Aufgabe (`meta["design_brief"]`, durchgereicht aus dem `/analyse`-Payload) voran → echte „Beschreibung→Entwurf→Kennwerte"-SFT-Paare; jede Zeile trägt `design_source` ("ki"/"hand"). `output` = Kennwert-Text aus `results["summary"]`. **Einheitliches Schema:** jede Zeile trägt exakt `RECORD_KEYS` (project_id/timestamp/design_source/instruction/input/output/label/label_source/auto_label/auto_reasons/comment/rated_at/metrics/images); `_write_all` zieht beim Schreiben **jede** Zeile über `_normalize` auf dieses Schema (Altzeilen werden so beim nächsten Schreibvorgang migriert). **Vorsortierung:** `auto_label`/`auto_reasons` (Heuristik) werden **immer** mitgeschrieben; **KI-Entwürfe** (`design_source=="ki"`) werden direkt mit dem Heuristik-Label vorsortiert (`label_source="auto"`), Hand-Entwürfe bleiben `label=null`. `set_label(pid, "gut"/"schlecht", comment)` setzt das Label manuell (`label_source="user"`, vom Ergebnis-Tab) und bleibt beim Nachrechnen erhalten (überschreibt die Auto-Vorsortierung). `stats()` zählt zusätzlich `n_user_rated`/`n_auto_rated`/`n_ki`. **Bilder:** jede SFT-Zeile führt `images:[{key,title,path}]` mit (projekt-relative Pfade in `~/cae_projekte`, NICHT base64 — `IMAGE_PAIRS` spiegelt `ema_report.build_context` pairs, nur deterministische Charts, keine Animations-Frames). `export_vlm()` erzeugt zusätzlich `dataset_vlm.jsonl` (EIN Eintrag je Bild im messages/content-Format mit absolutem Bildpfad, fürs Vision-Finetuning) — wird nach jedem `upsert`/`set_label` mitgeführt. Endpoints `POST /training/vlm/export`, `GET /training/vlm/download` |
| `ema_step_import.py` | **STEP-Import eines fertigen Motors**: liest per FreeCAD alle Solids (`extract_solids_script`), klassifiziert FreeCAD-frei (`classify_solids` über radiale Bänder + Volumen-Cluster + Rotationssymmetrie), leitet Maße/Polzahl ab (`derive_geom`, `_gap_cluster_count` für Pole/Nuten) + erkennt Magnete via OBB-Fit (`detect_magnets`, pol-lokale Halbpol-Magnete im Canvas-Format) und schreibt `motor.FCStd` mit benanntem `"Rotor"` (`assemble_fcstd_script`) → die bestehende Struktur-FEM rechnet darauf, EM auf den `customLegs`. `run_import` → applyDesignToCanvas-Form. Server: `/import_step`+`/import_step/status`; UI-Tab **📥 STEP-Import** → lädt in den Designer (Bestätigung), dann `/analyse` mit `imported:true` (run_pipeline überspringt den Geometrie-Build). Makro `step_import.FCMacro`. Tests: `test_step_import.py` |
| `ema_em3d.py` / `elmer_runner.py` | **Echte 3D-Magnetfeldberechnung (Elmer FEM)** — s. Architektur-Abschnitt. `build_mesh` (Gmsh-OCC), `write_sif` (Elmer-Magnetostatik), `parse_results` (vtk-VTU + 2D-Vergleich), `run_em3d` (Orchestrator). `elmer_runner` = Subprozess-Wrapper (`ElmerGrid`/`ElmerSolver`, `ELMER_OK`). Server `/em3d`(+`/status`,`/vtu`), UI-Tab **🧲 3D-Feld**. Tests `test_em3d.py` (Mesh/sif ohne Elmer) |

## Reference docs (read these for domain detail before changing physics)

- `README.md` — full feature/prerequisite walkthrough (German).
- `EM_BERECHNUNG.md` — electromagnetic calculation methodology.
- `NUTZUNGSANLEITUNG.md` — end-user usage guide.
- `BERECHNUNGSMETHODEN_VERGLEICH.md` — methods used (FDM/FEM/LPTN) and an honest comparison vs Abaqus & Ansys Motor-CAD; scope/limits and recommended tool chain.

## Gotchas

- FreeCAD scripts run in a separate process with **no shared Python state** — pass
  everything via the generated script string and read results back through stdout markers.
- Opening a headlessly-saved `.FCStd` in GUI FreeCAD leaves ViewProviders detached;
  `server.py:/open_freecad` re-applies visibility on a `QTimer` (see comment there).
- Report model is fixed to `ministral-3:14b`; Ollama is reached directly via
  `urllib.request` (no SDK). The analysis pipeline runs fully without Ollama.
