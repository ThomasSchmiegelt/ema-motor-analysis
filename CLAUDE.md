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

No linters or CI. Two core test scripts: `python smoke_test.py` — fast (~15 s, no
FreeCAD) sanity check of the main pure-Python paths (imports, topology, dq/MTPA,
FDM + saturation, connection assessment, deformation, script generation incl. a
rotor-only-FEM assertion); add `--cad` to also run one real FreeCAD build + rotor
FEM (minutes). `python test_topology.py` gates magnet geometry + the JS↔Python
`magnetLegs` mirror. Run `smoke_test.py` after any backend change.

The on-demand sub-systems each have their own standalone test file, runnable via
`python test_X.py` or pytest, all fast and dependency-free unless noted:
`test_em3d.py` (mesh/sif generation for the Elmer 3D field, no Elmer needed),
`test_em3d_submodel.py` (ROI refine + sector symmetry, needs Elmer for the
physical-result half), `test_step_import.py` (STEP→FreeCAD classification),
`test_oilspray.py` (Blender script generation/markers, no Blender needed),
`test_spraytest.py` (Spray-Test bench: sampling/mutation, bench script, round store —
no Blender needed), `test_jobs.py` (persistent server job queue: ordering, restart
recovery, pause/cancel — fake executors, no Flask/solvers), `test_cfd.py`
(OpenFOAM-VOF cooling: case-dict generation + jet/HTC correlation + wetted fraction +
thermal HTC-coupling — no OpenFOAM needed).

**Prerequisites:**
- **FreeCAD 1.1.x built from source** under `~/freecad_1.1_quellcode` (via pixi).
  The `/opt/freecad-1.1` binary is actually 1.2 with a visualisation bug — **do not
  use it**. Everything routes through `pixi run --manifest-path ~/freecad_1.1_quellcode/pixi.toml -- build/release/bin/FreeCAD[Cmd] …` so the working 1.1.x build + its conda env are picked up.
- **CalculiX** (`ccx`) bundled in that same pixi env at `~/freecad_1.1_quellcode/.pixi/envs/default/bin/ccx`.
- **pixi** on PATH.
- *Optional (PDF reports only):* Ollama at `localhost:11434` with `ministral-3:14b`, plus `pandoc` and `pdflatex`.
- *Optional (🌊 quantitative Spritzöl-Kühlung):* **OpenFOAM v2406** (ESI) unter `/usr/lib/openfoam/openfoam2406`
  (`interFoam`/`blockMesh`/`snappyHexMesh`/`surfaceFeatureExtract`/`foamToVTK`), via `etc/bashrc`
  gesourct (`$OPENFOAM_BASHRC` überschreibt). Ohne OpenFOAM 503t `/cfd`; Mesh/HTC/Thermik-Kopplung
  sind ohne OpenFOAM test-/baubar (`test_cfd.py`).

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

**Persistent job queue (`ema_jobs.py`, Tab ⏳ Jobs):** jobs survive a closed browser AND
a server restart. `POST /jobs/add {jobs:[{type,title,payload}]}` enqueues (types
`analyse`/`em3d`/`em3d_sweep`/`oilspray`/**`param_study`**/**`optimize`**/**`cfd`**); ONE worker thread runs them
sequentially by calling the **synchronous executor bodies** factored out of the routes (`_exec_analyse`
→ `_run`; `_em3d_setup`+`_em3d_body`/`_em3d_sweep_body`; `_oil_setup`+`_oil_body`;
`_exec_param_study`→`_param_study_body`; `_exec_optimize`→`_optimize_body` — the direct routes now spawn
these same bodies in a thread, behaviour unchanged). Executors write into the SAME module state dicts
(`_state`/`_em3d_state`/`_oil_state`/`_study_state`/`_opt_state`), so the per-tab UIs show live progress
and the routes' 409-guards apply; the worker `busy()`-waits when the user starts something directly.
`ema_jobs` injects the job **title** into the payload as `_job_title` (so executors can name a saved
artefact — e.g. the em3d auto-save). **em3d/em3d_sweep jobs AUTO-SAVE** their result into the active
project's `em3d_runs/` store on finish (`_em3d_job_outcome`→`_em3d_store_run`, also on a partial abort),
so a job-run 3D calculation is later openable in the 🧲 3D-Feld tab (direct runs still save manually);
the jobs list's result button is per-type (em3d→`openJobEm3d` loads the newest saved run into the
3D-Feld tab; oilspray→`openJobOil`; `param_study`→`openJobStudy`; `optimize`→`openJobOptimize` render
the server-state result in Tab ④; analyse→`loadProjectById`). Store `~/cae_projekte/_jobs/queue.json` (atomic);
on `init` stale `läuft` jobs → `abgebrochen (Server-Neustart)`, waiting jobs resume.
`GET /jobs` (running job enriched with progress + last log line via `_JOB_STATES`),
`POST /jobs/<jid>/cancel` (waiting → abgebrochen; running → executor abort hook, analyse
not abortable → 409), `POST /jobs/clear_done`, `POST /jobs/config {paused}`. UI: tab
**⏳ Jobs** (`panel-jobs`, `jobsActivate`/`jobsRefresh` poll 3 s, badge `#jobs-badge`
every 10 s) + „➕ Warteschlange" buttons next to every heavy start button (footer analyse,
Varianten `queueAllVariants`, Param-Tabelle `queueParamTable`, Designer
`dsnQueueAllVariants` — 👎-variants still go to `/training/design_rejected` instead of the
queue — em3d `queueEm3d`/`queueEm3dSweep`, oil `queueOilspray`, **Tab ④ Berechnung**
Parameterstudie `queueParamStudy` + Zielwertoptimierung `queueOptimize`; all share `enqueueJobs`).
**Reattach on page load** (`_reattachJobs` on `window.load`): if `/status` (or
`/em3d/status`, `/oilspray/status`) reports running, the matching poll loop/UI is restarted
so a reopened browser shows the running job again. Job statuses (German): `wartet/läuft/
fertig/fehler/abgebrochen`.

Key endpoints: `/analyse`, `/status`, `/results`, `/field/<n>` (animation frame),
`/cad_image/<name>`, `/chart/<name>`, `/open_freecad` (launches GUI FreeCAD on the
saved doc), `/export_step` + `/download_step`, `/projects`, `/project/<id>/load`,
`/project/<id>/activate` — **lightweight active-project select** (sets `_state["project_dir"]`/
`project_id` WITHOUT loading results/frames; returns `has_results`; Tab ①'s `pjSetActive` POSTs it
so report + em3d target the active project),
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
Schwerpunkt/Radius/z getaggt**, Magnet-Match über exakten `getCenterOfMass` + Massengate
(`_assign_pieces`, Modul-Ebene/unit-testbar), weil konzentrische Ringe ihren Volumenschwerpunkt
AUF der Achse haben. **Magnete matchen mit `single=True`** — pro Magnet-Stück nur das EINE
massen-nächste Volumen: Magnet-Prisma und obround-Tasche teilen denselben COM, und bei KURZEN
Magneten (PMa-SynRM-Außenlage 5×3 mm) passierte die Taschen-Schale (~0,6·Magnetmasse) das lockere
Gate → die LUFT-Schale wurde mit-magnetisiert + die Tasche nie als Luft getaggt („Feldlinien gehen
nicht durch die Magnete", Joch zeigte Nut- statt Polmuster). Verifiziert: 16/16 Magnete cos(B,M)=+1,
sauberes 4-Pol-Schnittbild (Regressionstest `test_assign_pieces_single_keeps_magnet_not_pocket`);
Luftspalt per
MathEval-Hintergrundfeld verfeinert) → `ElmerGrid 14 2` (MSH→Elmer-Mesh, `elmer_runner`)
→ `write_sif` (Magnetostatik: `WhitneyAVSolver` + `MagnetoDynamicsCalcFields` + VTU +
SaveScalars; Eisen μr=500 linear, Magnet μr=1.05 + per-Magnet `Body Force Magnetization`
= Br/μ0·Richtung, BC außen A×n=0) → `ElmerSolver` → `parse_results` (VTU via **vtk**:
Luftspalt-Br(θ) bei mehreren z → Endeffekt-Kurve, |B|-Schnitt z=L/2, Arkkio-Moment; +
`run_em_analysis`-2D-Vergleich).

**Hexaeder-Netz (opt-in, `opts["hex_mesh"]` / UI `e3_hex_mesh`, `_build_hex_mesh_once`):**
strukturiertes **Hex-/Prismen**-Netz statt der Tetraeder — 2D-Querschnitt-OCC-Fragment
(konzentrische Scheiben + Magnete + Statornuten + Flussbarrieren), zu Vierecken
rekombiniert (`Mesh.RecombineAll`) + axial extrudiert (`occ.extrude(...,recombine=True)`).
**Gerade** = eine Extrusion 0..L; **Staffelung** (`skew_segments` K≥2, kontinuierlicher
`skew_deg` wird in eine feine Staffelung übersetzt) = ALLE K Rotationen der Magnete/
Barrieren in den GEMEINSAMEN 2D-Querschnitt geschnitten + in K konformen Slabs extrudiert
(jede Schicht teilt dasselbe Basis-Netz → voll konform), pro Slab wird das aktive Magnet-
Segment geometrisch klassifiziert (Schwerpunkt, um −φ_k rückgedreht) und mit der um φ_k
gedrehten Magnetisierung getaggt. Der Luftspalt wird über wenige radial ausgerichtete
Schichten mit einem Bruchteil der Tet-Freiheitsgrade aufgelöst (Speicher-/Genauigkeits-
gewinn). **Magnet-Luft-Taschen (Langloch):** wie im Tet-Pfad sitzt jeder vergrabene Magnet
in einer obround-Tasche mit echtem `magGapMm`-Klebespalt (0,1–0,3 mm) — Tasche (magnet+clr)
UND Magnet werden in den 2D-Querschnitt geschnitten, der Ring dazwischen als Luft
klassifiziert (`_in_obround`/`_use_pockets`, `MeshSizeMin≈0,8·clr` löst den Ring auf).
**Elmer braucht auf Hex/Prisma zwingend die Piola-Transformation** der Kantenbasis
(`write_sif` setzt `Use Piola Transform` NUR bei `tags["mesh_kind"]=="hex"`) — und dann
KEIN Tree-Gauge (unverträglich) und KEIN Direkt-/MUMPS-Löser (nur „lowest order edge basis"
auf Simplizes). Das ungeeichte curl-curl-System ist symmetrisch **positiv-semidefinit** mit
konsistenter RHS (Magnetquelle = curl von M) → **CG + ILU0** (BiCGStabL bricht mit NaN ab;
verifiziert: korrektes 4-Pol-IPM-Feld). **v1-Scope-Grenze:** KEIN eingeprägtes Lastfeld
(Stirnring-Leiter) — die Obround-Magnettaschen (Klebespalt) sind seit 2026-07-06b auch im
Hex-Netz drin. `build_mesh` fällt bei Lastfeld-Einprägung (`excitation=loaded`+`coil_currents`) automatisch
auf Tet zurück (`tags["hex_fallback"]`), ebenso bei Hex-Bau-Fehler. Der Selbstheil-/Knoten-
Cap-Monitor (`_build_mesh_capped`) greift auch im Hex-Modus (die Zellgrößen-Skalierung wirkt
gleich). Test: `test_em3d.py` `test_hex_mesh_and_piola_sif`/`test_hex_staffelung_segments`/
`test_hex_loaded_falls_back_to_tet` (ohne Elmer). Server: `/em3d` (503 wenn `elmer_runner.ELMER_OK` falsch),
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
(gx,gy,**gz**) + Segmenthöhen-Massengate. **Magnet-Luft-Tasche (Langloch/obround, `mag_pockets`,
Standard an):** jeder vergrabene Magnet sitzt in einem **obround-Luft-Langloch** (Rechteck + zwei
Halbkreis-Enden, `_obround_loop`+`_obround_pocket`), das den Magnet mit `clr` Spalt rundum umschließt
(Querschnitt folgt exakt der Magnet-Geometrie, nur um `clr` größer). Zwei Baufälle: ① **GERADE**
→ EIN obround-Prisma über 0..L, Spalt = echter Geometrie-Tab-Klebespalt `magGapMm` (0,1–0,3 mm); die
Schale ist ein sauberes Prisma und selbst bei 0,1 mm netzbar (verifiziert). ② **STAFFELUNG** (`n_seg≥2`)
→ **K gestufte** obround-Prismen, eins je Segment, über die Länge versetzt (Winkel `ang+k·step`, Zentrum
um die Wellenachse gedreht) — und dann **PER MAGNET zu EINEM zusammenhängenden Luftkanal `occ.fuse`t**
(winzige z-Überlappung der Segmente). Magnetsegment + Tasche teilen exakt den Stufenwinkel → perfekter Sitz.
**Der kontinuierliche Skew (`skew_deg`) wird bei aktiven Taschen in eine feine Staffelung um die Wellenachse
ÜBERSETZT** (`_opts_eff`, K=⌈skew°/3⌉ Segmente) — ein um den EIGENEN Schwerpunkt tordiertes Magnet+Tasche-
Paar ist NICHT robust netzbar (die tordierte dünne Schale bringt `mesh.generate` zum Scheitern/Hänger;
ausgiebig getestet), gerade Segmente um die Wellenachse dagegen schon UND das ist physikalisch korrekter.
Damit ① **echter, sichtbarer Klebespalt `magGapMm` (0,1–0,3 mm) in ALLEN Fällen** (Flanke berührt nie
Eisen — der Magnet ist ein Rechteck, das satt im Langloch sitzt), ② Tasche schrägt/staffelt mit, ③ die
Eisen-Slivers zwischen den Segmenten liegen in Luft → löserstabil. **Warum der Fuse (wichtig — nicht rück-
gängig machen):** K SEPARATE gestufte Taschen lassen zwischen den verdreht gestapelten Prismen dünne
EISEN-Slivers stehen → entartete Tets → `mesh.generate` scheitert/explodiert (>400 k Knoten). Früher wurde
der Spalt deshalb netzbarkeitshalber auf ~0,55·Twist-Versatz ANGEHOBEN (der Magnet füllte dann optisch das
Langloch, **kein sichtbarer Luftspalt** — genau die Nutzer-Beanstandung). Der Fuse zu EINEM Kanal je Magnet
beseitigt die Eisen-Slivers → der ECHTE Spalt ist netzbar (verifiziert: 16 Kanäle, 5 Segmente, minSICN ~7e-3,
~60 k Knoten, kein Anheben). **Netzauflösung des dünnen Spalts (kritisch):** (a) die Magnet-/Taschen-
Oberflächen gehören bei aktiven Taschen NICHT ins grobe `mag_cl`-Feld (ein mm-Ziel im 0,2-mm-Spalt ist
geometriewidersprüchlich → „Could not recover boundary mesh"); (b) ein FESTES feines Saumband auf ALLEN
Magnetflächen sprengt die Knotenzahl/hängt. Stattdessen löst **`Mesh.MeshSizeMin ≈ 0,8·clr`** (Boden) plus
der natürliche Größengradient den Spalt auf — der Knoten-Cap vergröbert nur das Fernfeld, der Boden hält
den Spalt bei ≥1 Zelle. `tags["pocket_clear_mm"]` = `["pocket_clear_geom_mm"]` (immer der Geometrie-Tab-
Spalt), `["pocket_clear_raised"]` jetzt **immer False**. Die dünne Luftschale passiert das Massengate über
eine **explizite Schalenmasse** (`cap_pieces["vol_pred"]` ≈ Tasche−Magnet). **Netz-
Entartungs-Wächter (`_DegenerateMeshError`):** nach `mesh.generate(3)` prüft `_build_mesh_once` die
Tet-Qualität (`getElementQualities` minSICN) und wirft bei entarteten Slivers (minSICN≤`degenerate_sicn`
= 2e-4 über Toleranz, oder invertiert) — der Elmer-Löser scheitert daran sonst STILL. `build_mesh`
reicht diesen Typ direkt an den Selbstheil-Monitor weiter (Taschen NICHT abschalten, die helfen ja),
der Netzqualität/-dichte hochzieht (…→ Skew aus als letztes). `allow_degenerate`/`degenerate_sicn`
justierbar. **Flussbarrieren im 3D-Mesh** (`barrier_rects` —
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
`.get`). UI: Felder „Magnet-/Barrieren-Mesh", „Übergangszone" + Zonen-Übersicht-Karte. **Ziel-Knoten-Regler
(`target_nodes`, UI `e3_target_on`/`e3_target_nodes` 10k–300k):** überschreibt den konservativen Auto-Cap;
`_build_mesh_capped` steuert die Knotenzahl BEIDSEITIG an (zu grob ⇒ Zellgrößen ×f<1 verfeinern, zu fein ⇒
×f>1 vergröbern, f=(n/ziel)^(1/1.85), Toleranzband ±18 %, ≤4 Skalier-Pässe), Zonen-Verhältnisse bleiben.
Geklemmt 10000…`EM3D_NODE_CEILING`=300000 (= gemessener RAM-Deckel dieser 31-GiB-Maschine, `em3d_perf_check.py`:
Peak-RAM ~linear+Fill-in, 55k≈3,5 GiB, 277k≈25 GiB → OOM ~345k; der 55k-Auto-Cap ist bewusst konservativ, NIE
RAM-limitiert). **Selbstheilender Netzbau-Monitor (`_build_mesh_capped` + `_mesh_mitigations`):** schlägt
`build_mesh` fehl (überlappende Facetten / ungültige Tets), spielt der Monitor selbständig eine Mitigationsleiter
durch. **Reihenfolge: ZUERST Netzqualität/-dichte/-verhältnisse (ändert das Modell NICHT), erst als LETZTES
Modell-Features entfernen** — Netzqualität erhöhen (`mesh_robust`: gmsh Frontal-Delaunay + Tetraeder-Optimierung
`Mesh.Optimize`/`OptimizeThreshold`) → Luftspalt-/Magnet-Mesh ×1,5 vergröbern → Zonen-Verhältnisse angleichen
(`mag_cl`→`gap_cl`-nah, Saumzone `mag_grow` ×1,6, sanfterer Größengradient) → Gesamtnetz ×1,8 → Magnettaschen-Kappen
aus → Skew/Staffelung aus → Statornuten aus — und baut mit neuen Parametern neu, bis es klappt oder die Leiter
erschöpft ist. **Logfile `mesh_build.log`** (`_mesh_logger`,
im `em3d/`-Ordner des Projekts) protokolliert JEDEN Versuch (Parameter + Knoten/Fehler + Monitor-Entscheidung) mit
Zeitstempel; Pfad in `res["mesh"]["log"]`. `_seed_cl` macht die cl-Werte vor dem ersten Bau explizit (nie 0/auto)
→ Skalierung immer definiert. Test: schneller Unit-Test via gefälschtem `build_mesh` (Targeting/Heilung/Logfile
in ms). **3D-Feld-Tab UI**: breiteneinheitliche `.e3-card`-
Stapelung (wie FEM-Ergebnisse), **FEM-Einstellungen mit `<details>`-Erklärungen** (fachlich +
laienverständlich + Wirkung auf Genauigkeit/Rechenzeit), Staffelungs-Felder. **Browser-Viewer
Schnittebene** (`_e3SetClip`/`_e3FlipClip`, vtk.js `vtkPlane` + `mapper.addClippingPlane` +
**`mapper.modified()`** — ohne das rendert vtk.js die Clip-Änderung NICHT neu, der Schnitt schien
„kaputt") — Achse X/Y/Z + Positions-Slider + Seitenwechsel, „in den Motor schauen". **Standard-Ansichten
im Browser-Viewer** (`_e3SetView('xy'|'xz'|'yz'|'iso')`, Knopfgruppe „Ansicht" in der Viewer-Bedienleiste):
setzt Blickrichtung + View-Up der Kamera (Z = Motorachse; XY = Stirnseite/Querschnitt, XZ/YZ = Längsschnitt,
Iso = Standardperspektive) und ruft `resetCamera()` für die Abstands-/Zoom-Anpassung — gilt für Feld UND
Flusslinien. **Feldfarbe
im Browser-Viewer** (`_e3ApplyColor`): robuster Bereich übers 2./98.-Perzentil (`_e3Percentiles`)
statt min/max + **log-Toggle** + **|B|max-Slider** — sonst klebt das moderate Statorfeld (~0,3–0,8 T
Leerlauf) ganz unten in der Skala; das matplotlib-Schnittbild `_slice_image`
(Ergebnisbild `em3d_slice_mid`) zeigt den z=L/2-Schnitt jetzt in **Sättigungsfarben**:
Skala ans Sättigungsknie `B_SAT_DISPLAY_3D`≈2 T gekoppelt (`vmax=1,25·b_sat`, turbo-
Colormap blau→grün≈Knie→rot=gesättigt) + **grüne Sättigungskontur** bei `b_sat` +
Knie-Marke in der Farbleiste — identisch zur Logik des Lastprofil-Videos, so zeigt der
statische Schnitt direkt, WO das (linear gerechnete) Eisen sättigen würde (qualitativ).
**Netz sichtbar machen:** statisches **Netz-Querschnittsbild**
(`_mesh_slice_image` — schneidet die gmsh-.vtk MIT Luft bei z=L/2, `tripcolor` nach √Fläche
hell=fein → zonale Auflösung sichtbar, Bildschlüssel `em3d_mesh_slice`) + interaktiver **🕸 Netz**-
Toggle im Browser-Viewer (`_e3ToggleMesh`, `actor.setEdgeVisibility` — Oberflächen-Netz der
Festkörper; das Luftspalt-Volumennetz nur im Querschnittsbild, da die .vtp keine Luft enthält).
**Magnetfeldlinien im Browser-Viewer** (`🧵 Feldlinien`-Toggle, `_e3ToggleLines`): serverseitig
aus dem vollen Volumennetz (B-Vektor) getracet (`export_browser_streamlines` — `vtkStreamTracer`
RK4 + `LENGTH_UNIT`-Schritt skaliert an `dims["r_so"]`, Seed-Raster Welle→Stator-OD verteilt über
**viele axiale Ebenen über die volle Länge** (`n_z=12`, z∈[0,03·L … 0,97·L] im Eisenstapel, NICHT nur
z=L/2 bzw. 3 Ebenen → die Linien füllen den ganzen 3D-Körper über die Bauteillänge statt in wenigen
Ebenen zu kleben, Endeffekt/Skew sichtbar); der adaptive RK45 in
CELL_LENGTH-Einheiten lieferte 0 Linien. **Zahmheit gegen „wilde" Linien (v. a. beim Hex-Netz, dessen
B-Feld im schwachen Luftraum blockiger ist):** `TerminalSpeed` **adaptiv** = 4 % des 80.-|B|-Perzentils
→ Linien ENDEN im schwachen Feld statt Rausch-Komponenten hunderte mm weit zu folgen; `MaximumPropagation`
2,2·r_so (statt 6·); und `_clip_streamlines` schneidet Linien am Verlassen des Motorbereichs ab
(r>1,25·r_so oder z∉[−0,25·L…1,25·L], je Polylinie in In-Bereichs-Abschnitte zerlegt, Punktdaten erhalten)
— ohne das schossen einzelne Linien bis z≈±450 mm in die Luftbox. Ergebnis als schlanke
Polylinien-.vtp (nur `Bmag`, float32/UInt32 wie `export_browser_vtp` — beide nutzen `_write_vtp`)
über `/em3d/streamlines` geladen; im Viewer mit DERSELBEN `ctf`/`scalarRange` wie die Oberfläche
eingefärbt (folgt log/|B|max). **Liniendichte einstellbar** (`Dichte`-Slider `e3_line_density` /
`_e3ApplyLineDensity`): serverseitig wird bewusst DICHT exportiert (`n_rings,n_ang=9,48`, die
Obergrenze „viele"), der Slider dünnt clientseitig jede k-te Polylinie aus (`getLines().getData()`
→ Teilmenge, Punkte+Bmag unverändert) — sofort, ohne Server-Round-Trip, für Einzellauf UND jeden
Sweep-Punkt. Sind die Feldlinien an, wird die |B|-Oberfläche **transparent**
(`_e3SurfaceOpacity` → `setOpacity(0.18)`, Renderer mit Depth-Peeling), damit die Linien im Inneren
sichtbar sind. **Einzelne Lastfälle/Drehzahlen im Browser-Viewer (Sweep):** `run_em3d_sweep`
exportiert pro Betriebspunkt eine eigene schlanke .vtp + Feldlinien (`_solve_point(browser_stub=…)`
→ `_export_browser_point`, eindeutige `browser_<i>.vtp`, da alle Punkte dieselbe `case.vtu`
überschreiben); `out["sweep_vtp"]`/`sweep_lines` (Index→Pfad). `/em3d/vtp` + `/em3d/streamlines`
nehmen `?i=<index>` (`_em3d_point_path`, sonst Detail-/Einzelpfad); ein **Lastfall-`<select>` direkt
in der Viewer-Bedienleiste** (`e3_speed_wrap`/`_e3PopulateSpeedSelect`, gespeist aus `_e3SweepPoints`)
schaltet zwischen allen Betriebspunkten um (`openBrowser3d(idx)` setzt `_e3ViewIdx`, lädt Oberfläche
+ Feldlinien des Punkts neu). **Dynamische Darstellung über Drehzahl/Last (Player im Browser-Viewer):**
die Sweep-Punkte lassen sich flüssig **abspielen** statt nur per Dropdown durchzuklicken —
`_e3PopulateSpeedSelect` baut in `e3_speed_wrap` neben dem Dropdown eine **Player-Leiste** (▶/⏸
`_e3PlayToggle`, Scrub-Slider `_e3Scrub`, Tempo 0.5/1/2× `_e3PlaySetTempo`, Loop, „Skala fixieren",
Live-Readout `#e3_play_lbl`). Der Timer (`_e3PlayTick`) tauscht pro Frame nur die Punkt-Daten
(`_e3ShowPointData` → `mapper.setInputData` **ohne** Kamera-Reset), gespeist aus dem **VTP-Cache**
`_e3PdCache`/`_e3LinesCache` (`_e3GetPointPd`/`_e3GetLinesPd`, beim ersten Viewer-Öffnen per
`_e3PreloadSweep` vorgeladen) — daher ist der Punktwechsel sofort/ruckelfrei statt Render-Fenster-
Neuaufbau. Feldlinien animieren mit (`_e3SetLinesForIdx`), „Skala fixieren" (default an) hält die
Farbskala fest, damit das Feldwachstum über Last/Drehzahl vergleichbar bleibt. `openBrowser3d(idx,
swap=true)` ist der Schnellpfad (`_e3ViewerLive`), ohne `swap` der volle Erstaufbau. Die Punktliste
befüllt man gezielt als **Drehzahl-Rampe** (`_e3RampSpeed`, feste Last) oder **Last-Rampe**
(`_e3RampLoad`, feste Drehzahl, 0→Last-bis) in der Sweep-Karte → getrennt „über Drehzahl" bzw.
„über Last" abspielbar. `_e3PlayStop` (bei neuem Lauf / neuem Render / Tab-Wechsel) stoppt den Timer
+ leert die Caches; Einzelläufe (`_e3SweepPoints=null`) zeigen keinen Player. **Reines Frontend**
(alle Punkt-VTPs + `/em3d/vtp?i=`/`/em3d/streamlines?i=` existieren schon).
Transiente `work/`-Pfade werden NICHT in `results.json` geschrieben. **Geometriequelle NICHT klebrig:** beim Öffnen des 3D-Tabs wird
NICHT automatisch auf „Designer" umgeschaltet (das blendete den Geometrie-Tab dauerhaft aus →
„Geometrie ändert sich nicht"); Standard ist der Geometrie-Tab, `_e3SrcUserSet` merkt die bewusste
Dropdown-Wahl. `/em3d/vtp`-Fetch ist cache-gebustet. **Bericht-Integration:**
`run_em3d` mergt eine schlanke 3D-Zusammenfassung (`_persist_em3d_summary`) in `results.json`
(`results["em3d"]`, Bilder liegen in `charts/em3d_*.png`); `ema_report.build_context` zieht
`em3d`+Bilder, `_single_md_tables` baut die 2D-vs-3D-Tabelle (B_gap, Endeffekt Rand/Mitte,
Staffelung), `_prompt_for` ergänzt §8 (qualitativ) und `_ensure_em3d_section` garantiert den
bebilderten 3D-Abschnitt auch ohne LLM-Mithilfe — Standard- + agentischer Einzelbericht. **Betriebspunkt (Drehzahl + Last):** UI-Karte „⚡ Betriebspunkt" (rpm + Last + Anregung +
Lastprofile Leerlauf/Teillast/Nennlast/Volllast/Feldschwächung). `write_sif` berechnet bei
`excitation=loaded` IMMER den Betriebspunkt (dq-Ströme via `estimate_dq_currents`,
`tags["operating_point"]`) und zeigt i_q/i_d an. **3D-Lastfeld (Ankerrückwirkung)** ist umgesetzt
(`coil_currents`, Standard AN): je Nut eine axiale Stromdichte (CD3) + zwei **Stirnring-Leiter**
(`tags["coil_rings"]`, Luft-Annuli am Nut-Radiusband an z∈[−t,0]/[L,L+t]) mit azimutalem
Rückführstrom (CD1/CD2 via Elmer-MATC), Nut+Ring aus DEMSELBEN `C0` → ∇·J≈0 → der Strom schließt
sich in der endlichen Länge (sonst explodiert das Feld auf B~10⁴ T). `Fix Input Current Density=
True` reinigt die Restdivergenz über den **iterativen Jfix-Hilfslöser** (BiCGStabL+ILU1, kein
Direkt-Löser, KEIN `Jfix=0`-Pin — beides scheitert am singulären Neumann-System bzw. ist ein
unlistetes Keyword). Das konsistente ΣJ=0-System konvergiert iterativ, SOLANGE das Netz gesund ist.
Die vom Nutzer beobachtete **Jfix-Divergenz** („System diverged") kam vom kaputten **Staffel-Netz**
(Eisen-Slivers → ∇·J diskret inkonsistent), NICHT vom Löser — das fängt jetzt der Netz-Entartungs-
Wächter (s. o.) + die Luft-Tasche ab, bevor gelöst wird. **`COIL_J_SCALE≈199`** kalibriert die Höhe aufs
analytische `_analytical_Barm` (mm↔m-Einheitenfaktor, ~geometrieunabhängig). Verifiziert: B_gap
skaliert mit Last (0.18 T Leerlauf → 1.9 T@50 Nm → 3.5 T@150 Nm). Abschaltbar (dann Leerlauffeld +
Betriebspunkt). **v1-Scope:** lineare Materialien, Lastfeld vereinfacht (Grundwelle, lin. Eisen);
BH-Kurve + verteilte echte Wicklung sind Folgeschritte. **Drehzahlband / Betriebspunkt-Sweep
(`run_em3d_sweep`, Stufe 1 — KEINE echte Transiente):** mehrere Betriebspunkte
(`payload["sweep"]` = Liste `{rpm, load_nm, excitation}`) als je eigene statische 3D-Magnetostatik.
Schlüssel-Hebel: `build_mesh`/`_build_mesh_capped` lesen NIE rpm/load → das Mesh wird **einmal**
gebaut (`_prep_mesh`: Gmsh + ElmerGrid), pro Punkt läuft nur `write_sif` (neue dq-Ströme) +
`ElmerSolver` (`_solve_point`). **Mesh-Cache für Einzelläufe (`_MESH_CACHE`/`_mesh_key`):** dasselbe
Prinzip greift auch requestübergreifend — `_prep_mesh` merkt sich je em3d-Arbeitsverzeichnis das
gebaute Netz unter einem Hash aus **Geometrie + Baulänge + netzrelevanten Optionen** (`_mesh_key`,
**ohne** rpm/load_nm, ABER **mit** excitation/coil_currents, weil die die Stirnring-Luftannuli im
Netz schalten). Ändert der Nutzer beim nächsten Einzellauf nur Drehzahl/Last, wird das Netz
**wiederverwendet** (nur der Löser läuft neu, Log „♻ Mesh wiederverwendet"); Geometrieänderung oder
fehlende Mesh-Dateien ⇒ Neubau. Prozess-lokal (Neustart ⇒ erster Lauf baut neu). Gilt für
`run_em3d`/`run_em3d_sweep`/`run_em3d_refine` (die ROI-`Box` ist Teil des Keys → korrekt Neubau);
der Sektor-Pfad baut über `_build_sector_mesh` und ist nicht betroffen. `run_em3d` ist dafür in `_prep_mesh`/`_solve_point`/`_decorate_res`
zerlegt (Einzellauf unverändert); die Luftspalt-Metriken stecken im geteilten `_gap_field_metrics`
(volle Auswertung `parse_results` ↔ schlank `_gap_metrics_only`). Pro Punkt nur schlanke Kennwerte
(B_gap, Moment, i_q/i_d) + Verlaufskurven über die Drehzahl (`_sweep_charts` → `charts/em3d_sweep_*`);
das **volle 3D-Feld** (VTU/VTP/Viewer/Bilder) nur für den **Detailpunkt** (`detail_index`, default
letzter Punkt — wird ZULETZT gelöst, damit die im `work/` verbleibenden Dateien zu ihm gehören).
Persistenz `results["em3d_sweep"]` (`_persist_em3d_sweep`) + der Detailpunkt zusätzlich über
`_persist_em3d_summary` nach `results["em3d"]`. Server: **`POST /em3d_sweep`** (Klon von `/em3d`,
teilt `_em3d_state` + `/em3d/status|vtu|vtp|paraview`; VTU/VTP zeigen auf den Detailpunkt). UI:
Karte **„🌡 Drehzahlband / Lastsweep"** im 3D-Feld-Tab (editierbare Punkt-Tabelle `_e3Sweep` +
Detail-Radio, „aus Profilen füllen" via `_e3ApplyPreset`/`_e3RatedTorque`, „rpm-Band anhängen";
`startEm3dSweep` → `_pollEm3d` verzweigt bei `result.sweep` auf `_renderEm3dSweep`, das die
Sweep-Tabelle+Kurven in `#e3_sweep_results` rendert und den Detailpunkt über das vorhandene
`_renderEm3d` zeigt). Test: `test_sweep_per_point_sif` (Mesh einmal, zwei `write_sif` → verschiedene
dq-Ströme, ohne Elmer). **Dynamisches Lastprofil-Video (`payload["make_video"]`):** eine synthetische
Fahrzyklus-Punktliste (JS `_e3LoadProfile`, 20–50 Punkte: Anfahren→Beschleunigung→Nennbetrieb→
Feldschwächung→Boost→Auslauf; erzwingt Anregung „loaded"+Spulenströme, damit das Netz die
Stirnringe hat) wird als Sweep gerechnet und pro Betriebspunkt zu EINEM Querschnitts-Frame gerendert:
`_video_frame` (|B|-Sättigungs-Schnitt z=L/2 via `vtkCutter`+`tricontourf` PowerNorm, **grüne
Sättigungskontur** bei `B_SAT_DISPLAY_3D`=2 T — lineares Eisen ⇒ qualitativ, „wo es sättigen würde",
Zone wächst mit Last, + **Feldlinien in der Ebene** via `LinearTriInterpolator`→`streamplot` +
Kennwert-Panel rpm/Last/i_q/i_d/|I|/B_gap/Moment/Phase + **normierte Zeitleiste** mit Marker am
aktuellen Punkt). Frame JETZT (vor dem nächsten Solve, der `case.vtu` überschreibt) über den
`_emit_frame`-Helfer aus der aktuellen VTU; Frames heißen `frame_{i:04d}.png` in PROFIL-Reihenfolge
(fehlgeschlagene Punkte → `_video_frame_fail`-Platzhalter, damit ffmpeg lückenlos bleibt) →
`_encode_video` (ffmpeg, `frames_em3d/anim.mp4`). Zeitleiste nutzt die GEPLANTEN Verläufe (rpm/Last
aus den Punkten, i_q/i_d analytisch vorab via `estimate_dq_currents` — deterministisch wie der Löser).
`out["video"]` (bool) → `_renderEm3dSweep` zeigt einen `<video>`-Player + Download; Server serviert die
MP4 über `GET /project/<id>/video/em3d` (Modus `em3d`→`frames_em3d` in `video_subdirs`, neben
`struct`/den Feld-Modi). UI: Karte-Zeile **„🎬 Lastprofil-Video erzeugen"** (+ Punkte-Feld 20–50) in
der Drehzahlband-Karte; `_e3MakeVideo` schaltet nur der Profil-Knopf ein (alle anderen Bauer setzen
ihn zurück). Test: Frame-Renderer + `_encode_video` laufen ohne Elmer auf einem synthetischen Gitter. **3D-Lauf speichern/laden (PROJEKT-gebundener Store):** ein fertiger 3D-Lauf
(Config + Kennwerte + VTU/VTP-Feld) wird unter `<aktives Projekt>/em3d_runs/<id>/` abgelegt
(`config.json`/`result.json` + kopierte Feld-Dateien, Pfade auf den Store gemappt) und ohne
Neurechnen im Viewer wieder geöffnet — `_em3d_runs_root()` liefert die Store-Wurzel des aktiven
Projekts (`None` ⇒ die Routen verweigern/liefern leer, „erst Projekt wählen"; den globalen
`_em3d_runs`-Store gibt es nicht mehr). Generell binden ALLE em3d-Handler den Lauf via
`_em3d_project_dir(data)` (ehrt `project_id` wie `/analyse`s reuse_id, sonst aktives `_state`-Projekt,
sonst frisches `…_em3d`) ans Projekt → VTU/VTP landen in `<projekt>/em3d/`. Server: `POST /em3d/save`
(liest `_em3d_state["result"]`, `_em3d_copy_run_files` kopiert VTU/VTP/Feldlinien + Sweep-Punkte),
`GET /em3d/saved` (Liste), `GET /em3d/saved/<id>` (setzt `_em3d_state["result"]` → die bestehenden
`/em3d/vtp|vtu|streamlines|paraview` bedienen den Lauf), `POST /em3d/saved/<id>/delete`; alle
`_safe_name`-geschützt. UI: die **Speichern-Karte** (Name + `_e3SaveRun`) + Tab-①-Dropdown
(`_e3BuildConfig`/`_e3ApplyConfig`/`_e3SaveRun`/`_e3RefreshSavedList`, von `pjSetActive` mit
aufgefrischt) liegen auf **Tab ① Projekt**; ZUSÄTZLICH gibt es eine **Karten-Liste
„🧲 Gespeicherte 3D-Läufe" IM 3D-Feld-Tab** (`#e3_saved_cards`/`_e3RefreshSavedCards`, Muster wie
die 💧-Öl-Varianten) — je Lauf „📂 Laden"/„🗑", `_e3LoadRunById(id, msgEl, openInTab)` ist der
gemeinsame Lade-Pfad (Dropdown, Karten, `openJobEm3d`); mit `openInTab` wird in den 3D-Feld-Tab
gewechselt und Feld + Browser-Viewer inline gezeigt. Der Kartenrefresh hängt an der Tab-Aktivierung
(`adoptEm3dGeom`) + an Speichern/Löschen.
**ROI-Verfeinerung (Bereich höher auflösen)** — `run_em3d_refine` (`POST /em3d/submodel`, teilt
`_em3d_state`): nach einem Lauf markiert der Nutzer interaktiv im vtk.js-Viewer einen Quader
(`_e3Roi`, gelbe `vtkCubeSource`-Drahtbox + 6 Zahlenfelder als Quelle der Wahrheit); das **volle
Modell** wird mit einem lokal feineren Gmsh-**`Box`-Feld** im Quader (`opts["roi_box"]`/`roi_refine`
in `_build_mesh_once`, `roi_cl=min(gap_cl,mag_cl)/refine_factor`, via `Min` kombiniert) **komplett
neu** gelöst (normaler Außenrand A×n=0) — reuse `_prep_mesh`/`_solve_point`/`_decorate_res`,
`res["source"]="refine"`. **KEIN echtes Submodell mit BC-Übertragung:** ein auf der geschlossenen
ROI-Box vorgegebenes, abgetastetes Motor-B-Feld (`Magnetic Flux Density i` → Elmers `DirichletAfromB`)
erzeugt an den 12 Boxkanten widersprüchliche Kanten-A-Randwerte und explodiert (≈1100 T) — nur auf
glatten Feldern (homogen/Dipol) validierbar, nicht auf einem realen Motorrand mit Nuten/Zähnen/
Magnetkanten (s. memory `project_em3d_submodel_bc`). Der volle Re-Solve ist im ROI sogar genauer
(kein BC-Transferfehler), kostet aber einen weiteren Solve. Test: `test_em3d_submodel.py`
(`test_roi_box_refines_mesh` ohne Elmer: Box-Feld → mehr Knoten + `mesh_zones["roi_cl"]`;
`test_refine_full_resolve` mit Elmer: |B| physikalisch + stimmt im ROI mit dem Grob-Lauf überein).
**Ein-Pol-Sektor (Symmetrie-Submodell, „2. Stufe")** — `run_em3d_sector` (`POST /em3d/sector`,
teilt `_em3d_state`, UI-Knopf **„🔁 Schnelle Pol-Berechnung (Symmetrie)"**): rechnet EINE
Pol-Teilung (`_build_sector_mesh`: Sektor-Zylinder via `addCylinder(angle=α)`, **Magnete + Nuten +
Flussbarrieren** aus `magnet_rects`/`slot_rects`/`barrier_rects` in die Sektor-Mitte gedreht, als VOLLE
Prismen gebaut und per `occ.intersect` an die Keil-Domäne geschnitten — so dürfen q-Achsen-
Barrieren/Nuten die Periodikfläche kreuzen, Klassifikation über die **Fragment-Map**;
Periodikflächen-Selektion über **Senkrechtabstand** zur Halbebene, Master↔Slave nach (r,z) gepaart;
**gestufte Verfeinerung** Luftspalt(`gap_cl`)→Magnet/Barriere/Nut(`mag_cl`, Distanz-Auslauf
`mag_grow`)→grob(`mesh_cl`) via `Min`-Feld; das Tortenstück wird in `run_em3d_sector` per Zielsuche
bis ~`EM3D_MAX_NODES` **ausgereizt**) und spiegelt sie über die
Maschinensymmetrie zum vollen Motor (`_pattern_full_motor`: 2p Kopien, je um k·α gedreht, B-Vektor
mitgedreht + anti-periodisch `(−1)^k`, GeometryIds erhalten). Die beiden Winkel-Schnittflächen sind
**anti-periodisch** gekoppelt (Elmer `Periodic BC` + `Rotate` + `Scale=-1` + `Use Lagrange
Coefficient` — bindet die WhitneyAV-**Kanten-DOF** korrekt, validiert ~10 % Anti-Periodizität im
glatten Joch, KEIN Aufblasen), Außenrand `A×n=0` wie das Vollmodell — **kein Feldtransfer** nötig
(im Gegensatz zum gescheiterten Box-Submodell). Weil die Domäne nur 1/(2p) groß ist, wird sie
**feiner** vernetzt → „höher aufgelöst" bei kürzerer Rechenzeit. `write_sector_sif` schreibt **OHNE
Coordinate Scaling** (mm wie das Vollmodell; Magnetostatik ist skaleninvariant). `_sector_results`
spiegelt → volle-Motor-VTU/VTP/Feldlinien + Luftspalt-Kennwerte (`_gap_field_metrics`) + Endeffekt +
2D-Vergleich + Anti-Periodizitäts-Kennwert (`antiperiodic_err`, **Median im Statorjoch** — im
Luftspalt/Nutband geben die Proben >100 % Rauschen trotz korrekter BC) + die **vollen 3D-Ansichten**
des gespiegelten Motors (`render_geometry_3d`-Logik via `_render_geometry_views` + `render_field_3d`,
Klassifikation über die VTU-**GeometryIds** mit `_classify_grid_gids` statt der gmsh-.vtk — Welle,
Magnete, Nuten/Zähne, Magnettaschen, Luftspalt sichtbar). **Einstellbares Knoten-Kontingent**
(`node_budget_pct` 10–100 %, 100 % = `EM3D_MAX_NODES`) regelt per Zielsuche, wie fein das Tortenstück
wird. **v1-Scope:** Leerlauf (nur Magnete) + Magnete (+ Taschen) + Statornuten + **Flussbarrieren** +
**Hohlwelle**; KEIN Skew/Spulenströme (das bleibt `run_em3d`). Erfordert `slots % poles == 0` (sonst
nur näherungsweise). Test:
`test_sector_mesh_and_sif` (ohne Elmer: Periodik+Außenrand-BC, Nuten/Pol) + `test_sector_full_resolve`
(mit Elmer: physikalisch, Anti-Periodizität < 15 %, voller Motor gespiegelt).
**Prerequisite:**
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
by `_crown_swept` as a smooth SOLID sweep ("Zugkörper") through oriented rect
sections (`_crown_frame`/`_crown_rect` keep the cross-section flat), flaring
**radially outward** by `windingHeadFlare` mm. **Stufenweise Spreizung je LAGE**
(`windingHeadSpread`, ° je Lage, 0 = aus/historisch, UI-Slider „Spreizung je Lage"):
JEDE Lage k bekommt ihren EIGENEN Biegewinkel `(k+1)·spread` — Lage 0 → 1×, Lage 1 → 2×,
Lage 2 → 3× … → die Lagen fächern radial auf (mehr Kronen-Abstand, realer Hairpin). **Früher
paarweise** (Lanes 2j/2j+1 teilten einen Winkel → Lage 1&2 bzw. 3&4 blieben parallel — genau
die Nutzer-Beanstandung); jetzt **per Lane**. Umsetzung `_lane_flare(k)` im erzeugten Skript
(`(k+1)·spread`): auf dem Kronen-Arm ist `dr/dz = f/H_eff`, also `f = wh_flare + H_eff·tan(α)`
(`WH_EBEND`/`WH_WAPEX`/`WH_HEFF` aus `_crown_swept` auf Modul-Ebene gehoben). In `_crown_swept`
bekommt der **Hin-Arm f0=`_lane_flare(k0)`, der Rück-Arm f1=`_lane_flare(k1)`**, per `b`
geblendet (`f = f0 + b·(f1−f0)`). **Kollisionsfrei:** f0<f1 → der radiale Kreuzungsabstand
wächst `(r1−r0)+(f1−f0)·g ≥ r1−r0` (Bänder divergieren nur zusätzlich, nie enger). **Auch auf
der SCHWEISSSEITE** (`_tab`, `f_weld = H_w·tan(a_w)`, wächst glatt mit der Rampe): die Lagen-
PAARE fächern auf, wobei beide Beine EINES Schweißpaares (Lage 2j/2j+1) dieselbe Aufweitung
teilen → der Schweißpunkt trifft weiterhin zusammen (per-Lage würde die zu verschweißenden
Enden auseinanderziehen). Nur `sweep`, nicht die Box-Darstellung; die Isolierhülse nutzt
`wh_flare_max` (äußerste Lage). Gate: `smoke_test.py` `[Wickelkopf-Spreizung]` führt die
emittierte Mathematik ohne FreeCAD aus (per-Lage-Monotonie + Winkel (k+1)·spread + Schweißseite). The path is **C¹-smooth by design**:
a **vertical slot exit at BOTH ends** (θ-easing with s′=0 at the path ends + flare
blended to slope 0 below the bend, start/end sections embedded 1.2 mm into the own
leg → seamless leg↔crown junction), straight chevron arms (constant slope keeps the
2H/pitch z-gap of tangential neighbours), a parabolic apex cap, and the r0→r1 radial
hand-over as a smoothstep inside the apex window `w_apex = min(0.18,0.28/pitch)·(1−e_bend)`
— the (1−e) factor matters: θ-easing compresses the mid region, so an unscaled
t-window maps to a WIDER θ-window and collided with the innermost arm crossing at
θ-fraction `0.5 − 1/(2·pitch)`. On the arms the flare is LINEAR in the height
profile h (pure function of h → identical on both arms at equal z → the r1−r0
crossing gap is preserved; a steeper h² flare measurably worsened the crossing
grazes). **The sweep is 5 SEPARATE smooth lofts** (bend|arm|apex|arm|bend, split at
the C² breaks, shared boundary sections → tangent-continuous invisible seams): ONE
global smooth loft RINGS — the B-spline interpolates all sections globally and the
end-bend curvature made the surface oscillate ±0.2–0.4 mm along the whole arm,
eating the 0.8 mm lane gaps (overlap 14→300 mm³). Per-segment analytic volume gates
(path length × cross-section, 0.6–1.6×) catch ballooning; fallback: one ruled loft →
box chevron `_crown`. The **weld side** (`_tab`) models the real hairpin twist: every
leg end leaves the slot vertically (embedded), bends into a sloped tangential ramp
twisting it by **half a coil pitch** (ALL lanes the same direction; ramp height
`H_w = crown_H` ⇒ ramp slope = crown-arm slope ⇒ same 2H/pitch z-gap between slot
neighbours; parallel ramps in a lane never cross), then runs **straight parallel to
the motor axis** as the weld tip. After the y/2 twist the go leg of pin(s) (lane 2j)
and the return leg of pin(s−pitch) (lane 2j+1) — both slot s — end side by side at
θ = s+y/2; over the last ramp quarter the pair converges radially (even lane out,
odd lane in, smoothstep) to a 0.12 mm light gap, so the welded pair visibly meets
without boolean overlap (verified: overlap totals unchanged vs crowns-only). Same
segmented smooth-loft build (bend|ramp|bend|tip), fallbacks ruled loft → `_tab_box`
(the old angled box). `windingHeadStyle:"box"` forces box crown + box tabs. `build_full_motor_script(..., winding_debug=True)` emits each physical pin
as its own `Pin_NNN` object for the identity-aware pairwise-`common().Volume`
collision check. NOTE the sweep style grazes neighbours by tiny slivers — measured
totals (all pins): s48/c4 11.6 mm³ (old ruled baseline 14.0), s36/c2 0.0, chorded
pitch5 63.3 (baseline 88.1); treat that as the baseline, not zero — the box style is
the strictly collision-free reference. `conductorsPerSlot` also drives
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

**Defensiver Rotor-Bau (`build_full_motor_script`, „Rotor wird nicht erzeugt"-Fix):** ein
ungültiger Solid nach den Taschen-/Barrieren-Schnitten (aggressive Multi-Lagen-Taschen → dünne
entartete Eisenstege) darf NICHT mehr das ganze Skript per `raise` abbrechen (das verlor Rotor
UND Welle/Magnete/Stator/Hairpins — es wurde gar nichts gespeichert). Stattdessen: batch-Schnitt
ungültig → `removeSplitter()` → sonst jede Tasche **einzeln** von der gültigen Basisscheibe
(`rotor_base` = Ring − Bohrung) schneiden; ganz am Ende, falls immer noch ungültig, Fallback auf
die **ungeschnittene Rotorscheibe** + Log-Warnung. So entsteht IMMER ein gültiges „Rotor"-Objekt
→ das Modell speichert, die Struktur-FEM hat einen Körper. Gate: `smoke_test.py --cad` (echter
FreeCAD-Build + Rotor-FEM).

### Experimentelle Spritzöl-Kühlung am Wickelkopf (Blender/Mantaflow) — `ema_oilspray.py` / `blender_runner.py`

Eigenständiger On-Demand-Pfad **neben** dem Analyse-Chain (wie em3d): untersucht **qualitativ**
die Fluidkühlung eines Wickelkopf-**Ausschnitts** mit Spritzöl — **Tröpfchenbildung, Benetzung,
Abtropfen** — mit Blenders **Mantaflow-FLIP**-Löser. **Ehrliche Scope-Grenze (steht im UI):**
visuell-plausibel, NICHT validiert, **kein Temperaturfeld / kein Wärmeübergangskoeffizient**; die
„Kennwerte" sind rein **geometrische Benetzungs-Proxys** (benetzte Fläche %, Abdeckung je Fläche,
Tropfen-/Fragmentzahl über die Zeit). Für echte Kühlrechnung bliebe OpenFOAM VOF ein Folgeschritt.

Ablauf (`ema_oilspray.run_oilspray`): (1) **Motor-Keilausschnitt → STL** via
`ema_freecad.build_winding_head_stl_script(..., include_core=True)` (reuse `build_full_motor_script`
mit Welle/Rotor/Magnete/Stator+Hairpins/Wickelköpfen, `winding_debug=True`, **`hairpin_slot_limit`**
begrenzt die Nuten-Schleife auf den Ausschnitt → Sekunden statt Minuten; Epilog schneidet alles per
**Sektor-Zylinder** (`Part.makeCylinder(angle)` + `common`) zu einem **Tortenstück-Cutaway** über den
Winkelbereich der Wickelköpfe; Export per **`MeshPart.meshFromShape`** grob 0,6 mm — NICHT `exportStl`
default, das produziert Hunderte MB / Mio. Dreiecke; Marker `STL_SAVED:`). `include_core=False` → nur
die Wickelköpfe (alt). (2)
**Blender-Setup-Skript** (`_BLENDER_SCRIPT`, headless) — importiert die STL als **Effector**
(COLLISION), baut **Domain** (LIQUID/FLIP, `resolution_max`), einen **Spritzöl-Kühlring** und
misst Benetzung/Tropfen. **Kühlring-Modell** (statt eines simplen Fallstrahls): ein Rohr-Ring
(Ø `ring_tube_mm`) **am +z-ENDE der Wickelköpfe** (`ring_z = z_tip`, nur der Überhang mit
z>Blechpaket-Stirnfläche `stack_half_mm` wird betrachtet), Radius = Kronen-Außenradius am Ende +
`ring_gap_mm` + Rohr-Radius, als sichtbarer Rohr-Bogen (Kurve+Bevel, Stahl); darauf `nozzle_count`
**Düsen** (INFLOW), die Öl **Richtung Drehachse** spritzen — jeder Strahl **zielt auf die z-Achse auf
Höhe des Wickelkopf-Körpers** (`z_aim`), also radial-nach-innen UND leicht nach unten, damit er die
Leiter trifft statt horizontal über die Kronen zu fliegen. Strahlgeschwindigkeit aus dem **Druck**
`pressure_bar` via Bernoulli `v = Cd·√(2·Δp/ρ)` (ρ=850, Cd=0,8; 3 bar ≈ 21 m/s).
**Voller 360°-Spritzring (`oil.ring_full`, UI `#oil_ring_full` „⭕ Voller Spritzring"):** Ring als
GESCHLOSSENER Kreis (`use_cyclic_u`-Poly-Spline, kein Doppelpunkt bei 0=2π) + Düsen gleichverteilt
über 360° (`k/N` statt `k/(N−1)`); Ziel je Düse wrap-fest über `_crown_target_full` (`_ang_d`
modulo 2π) — liegt beim Keil-Ausschnitt KEIN Kupfer in der Nähe, zielt die Düse synthetisch radial
nach innen auf den Kronenradius (sonst schösse der Strahl quer durch die Maschine auf den fernen
Keil). Die Domain deckt dann den vollen Umfang ab (`_ts` über 2π ⇒ Auflösung verteilt sich auf viel
mehr Raum — UI-Hinweis: Auflösung + Düsenzahl erhöhen); sinnvoll v. a. mit `winding_full`.
**Der Voll-Ring gewinnt auch über die Nahaufnahme** (`_ring_closed = RING_FULL` — sonst zeigte
⭕+Nahaufnahme nur einen Rohrstutzen, „Ring nicht geschlossen"); die Nahaufnahme behält 1 Düse/Kamera.
**Live-Winkel-Skizzen (`_oilDrawAngleFig`, `#oil_angle_fig` in der 🎯 Strahlrichtung-Karte):** DREI
client-seitige SVG-Panels — ① Stirnansicht (Düsen-Versatz/tangentialer Schwenk/Sprühkegel; zeichnet
zusätzlich ALLE Düsen-Öffnungen aus „Anzahl Düsen" verteilt über Bogen bzw. 360° mit je einem kurzen
Radialstrahl-Pfeil), ② Seitenschnitt (axiale Neigung), ③ **Einbaulage/„wo ist unten?"** (Schwerkraft-
Pfeil g, Gehäuse-Umriss, Ablauf, Öl-Weg — folgt `oil_orientation` horizontal/vertikal +
`oil_housing`/`oil_housing_collide`), die per `oninput`/`onchange` der vier Winkelfelder +
`oil_nozzles` + `ring_full`/`winding_full`/`housing*`-Checkboxen + `oil_orientation` live
mitzeichnen (gleiche Vorzeichen-Konvention wie das Blender-Skript: Versatz/Schwenk math. positiv um
die Achse, Neigung + = zur Stirnfläche); aufgerufen auch beim Öffnen des 💧-Tabs (`switchTab`).
**Skizze-↔-Simulation gleiche Basis (Bugfix):** in ② Seitenschnitt liegt der Ring jetzt DIREKT über
der Kronenflanke (gleiches x wie das Ziel) → der Grundstrahl ist bei Neigung 0° **pur radial** (im
Bild senkrecht) — genau die Basis, ab der auch Blender die Neigung rechnet (dort ist der Grundstrahl
nahezu radial). Früher lehnte die Skizzen-Basis ~27° zur Stirnfläche → Skizze und Blender „rechneten
von unterschiedlichen Basen". **x/y/z-Achsen-Triaden** (`axesTriad`, z blau = Motorachse, x rot,
y/r grün; eine Achse ⊙ aus der Ebene) in allen drei Panels: Stirnansicht `front` (z⊙, x→, y↑),
Seitenschnitt `side` (z→, r↑, x⊙), Einbaulage `install_h`/`install_v`. Öl-Stoffwerte
(`use_viscosity`/`viscosity_value`, `surface_tension`) + **Secondary-Particles** (spray/foam/bubble →
Tröpfchen). **Cutaway-Einfärbung:** eine STL-Mesh, Faces nach axialer Position (|z|>Stirnfläche =
Wickelkopf-Überhang → Kupfer, sonst Kern → Stahlgrau). **Domain fokussiert auf das +z-Ende**
(Wickelkopf-Überhang + Ring, NICHT bis zur Achse — sonst zu groß/grob) MIT **Ablaufraum nach unten**
(`dz_lo = z_stack_end − 1·Überhang`), damit das Öl sichtbar über die Wickelköpfe runterläuft statt am
Aufprall sofort zu zerstäuben und die offene Domain zu verlassen; **offene Ränder**
(`use_collision_border_*=False`, Splash verlässt die Domain statt „Öl-Bleche" an den Wänden zu bilden)
+ Boden-**Outflow**-Drain; **Drain/Düsen-Objekte `hide_render=True`** (Sim-Hilfsobjekte).
**Transparentes Motorgehäuse (`oil.housing`/UI `#oil_housing`, Default an, `housing_wall_mm`
Default 4):** ein durchsichtiges, **beidseitig geschlossenes** Voll-Ring-Gehäuse („Dose",
`end_fill_type='NGON'`-Deckel + Solidify) rund um Rotor/Stator, Wand `HOUSING_WALL` (Solidify
nach außen), axial von `min(zmin,−STACK_HALF)` bis `z_tip+gap` (die Wickelköpfe liegen darin) +
ein **sichtbarer Ablauf-Stutzen** an der schwerkraft-tiefsten Seite (−y horizontal / −z vertikal).
**GENAU EINE Hülle** (Bugfix „mehrere kollidierende Gehäuse"): der Innenradius `R_hous_in =
max(0,5·Stator-Ø, r_ring+3·tube_r)` umschließt Stator UND Spritzring — die frühere **zweite,
weitere „Bulge"-Schale** über dem Ringkanal (`R_bulge`, wenn der Ring über den Stator-Ø ragte)
wirkte als ineinander steckender zweiter Zylinder wie mehrere kollidierende Gehäuse und ist
ENTFERNT. `R_hous_in` bleibt der Innenradius, an dem Kollisionswand/Domain enden. Glas-Material
`_glass` mit **Alpha 0,14** (0,045 war im Video unsichtbar → „Gehäuse scheint nicht geschlossen").
**Kollisionswand (`oil.housing_collide`/UI `#oil_housing_collide`, Default AN):** das Gehäuse bekommt einen
Fluid-EFFECTOR (COLLISION) — das Öl wird am Glas **gefangen**, läuft innen herunter und wird an der
**Gehäuse-tiefsten Stelle** entfernt: die Domain wird dazu bis zur Gehäuse-Innenwand in Schwerkraft-Richtung
aufgezogen (`_haus_col`/`R_hous_in`: horizontal `Dymin ≤ −(R+Wand)` + x-Breite; vertikal `dz_lo` bis zum
Boden-Deckel + radial bis zur Wand — größere Domain ⇒ UI-Hinweis Auflösung erhöhen) und der **OilDrain-Outflow
an die Gehäuse-tiefste Stelle verlagert** (horizontal: schmale Lachen-Box innen am Glas-Boden `y=−R_hous_in`
entlang z; vertikal: flache Box auf dem Boden-Deckel). In der Nahaufnahme (`CLOSEUP`) bleibt die fokussierte
Domain (kein `_haus_col`). **OHNE Collide = alte Sichtwand:** keine Kollisions-/Bake-Kosten, fokussierte Domain,
das Öl „verschwindet" sichtbar an der Domain-Grenze mitten im Gehäuse. In `PREVIEW` mitgezeichnet. Benetzung
wird NUR gegen die Wickelkopf-Überhang-Vertices gemessen (sonst verwässern die Kern-Vertices den
%-Wert). Emitter ≥`1,2·voxel` (1-mm-Bohrung ist sub-voxel). Schneller Strahl braucht mehr Substeps
(`timesteps_max`, adaptiv/CFL) sonst tunnelt das Öl.
**Einbaulage + Nahaufnahme** (`orientation` `horizontal`(Standard)/`vertical`, `closeup`): bei
**horizontal** (Motorachse waagerecht = übliche Einbaulage) wird der Wickelkopf-Sektor um die z-Achse
nach **+y (oben)** gedreht (`wh.rotation_euler`), die **Schwerkraft** ist `(0,−9,81,0)` (quer zur
Achse) und Domain-Ablaufraum + Boden-Outflow liegen an der **−y-Fläche** → das Öl läuft seitlich über
die Wickelköpfe ab; bei **vertical** bleibt die alte Geometrie (Schwerkraft −z, Ablauf −z entlang der
Achse). `closeup` erzwingt **1 Düse** und eine **Kamera-Nahaufnahme** (schräg außen-oben) auf den
Auftreffpunkt; ohne `closeup` die 3/4-Übersicht mit allen Düsen.
UI: Karte „🎥 Darstellung & Einbaulage" (`oil_orientation`/`oil_closeup`).
**Schnittdarstellung durch eine Düse (`oil.section_cut` + `oil.section_cut_noz` 1-basiert, UI
`#oil_section_cut`/`#oil_section_noz`):** Schnittebene durch die **Motorachse (z) UND den
Austrittspunkt der gewählten Spritzbohrung** (Azimut θ0 aus `noz_angles`, in der Düsen-Schleife
gesammelt); ein Halbraum-`SectionCutter`-Quader (um ε=0,1 mm aus der exakten Achsen-Ebene versetzt —
koplanare NGON-/Solidify-Flächen erzeugen sonst Boolean-Splitter) wird per Boolean-DIFFERENCE von
**allen** Anzeige-Festkörpern abgezogen: **jedem `_parts_obj`-Bauteil** (die STL kommt als getrennte
Teile winding/rotor/stator/shaft/magnets — nur `wh` zu schneiden ließ den Kern ganz), dem Ring
(Kurve → `convert(target='MESH')` vorher), Gehäuse-Schalen und `Nozzle_*`/`JetLine_*` (der gewählte
Stutzen liegt IN der Ebene → Bohrung längs halbiert sichtbar). Kamera senkrecht auf die Ebene
(Ziel = Motorachse Mitte, explizite Basis X_cam=+z/Y_cam=radial/Z_cam=n — `_cam_up` wäre bei Düse
„oben" degeneriert). **Schnitt + Nahaufnahme (`closeup`)** = „rechtes oberes Viertel": Bild unten
von der z-Achse begrenzt, radial bis über den Spritzring, axial etwas Blechpaket (Rotor/Stator) +
Wickelkopf/Ring-Ende — die normale tangentiale Closeup-Kamera stünde in der weggeschnittenen
Hälfte und passt nicht zum Halbraum-Schnitt; Basisdistanz **1.6** (dichter auf die Wickelköpfe,
Nutzerwunsch) statt 2.2. **Schnitt-Zoom (`oil.section_zoom`, UI `#oil_section_zoom` 0,5–4×):**
`cam_d /= SECTION_ZOOM` in Voll- UND Nahansicht des Schnitts (>1 = dichter). **Zoom-Anker ist der
WICKELKOPF, nicht die Motorachse** (`_sec_tgt`): das Kameraziel liegt bei 1× weiter auf der Achse
(Übersicht unverändert), rutscht aber mit steigendem Zoom auf die Wickelkopf-/Ring-Mitte in der
Schnittebene zu — `room = 0,34·cam_d − 0,55·_wh_sz` ist der erlaubte Abstand des Ziels von der
Wickelkopf-Mitte, `_wh_c`/`_wh_sz` = radiales Band (Kronen-Innenradius … über den Spritzring) ×
axiales Band (Blechpaket-Ende … über Kronen-/Ring-Ende) aus den STL-Überhang-Vertices. Ohne das
zoomte man auf die Welle und der für die Spraybildung interessante Wickelkopf lief aus dem Bild
(Nutzer-Beanstandung). **Boolean-Robustheit (kritisch):** die STL-Teile
(v. a. die Hairpins, Beinahe-Berührungen/Doppel-Dreiecke) sind NICHT mannigfaltig — EXACT braucht
`use_self` + `use_hole_tolerant`, sonst „explodiert" der Schnitt (WindingHead-BBox ~4 m, kupfer-
farbener Nebel füllte das ganze Bild); zusätzlich ein **BBox-Wächter** in `_cut` (Halbraum-
DIFFERENCE kann nur verkleinern ⇒ BBox-Wachstum >1,5× = gescheitert → FAST probieren → sonst
Bauteil ungeschnitten lassen). Kamera-/Objekt-BBoxen werden als `OIL_STAGE:cam/obj`-Zeilen
geloggt (Debughilfe für „Bild zeigt nichts"). Die **Fluid-Domain wird NICHT geschnitten** (Öl/Strahl voll sichtbar) und die
**Benetzungs-Metrik nimmt bei aktivem Schnitt das BASIS-Mesh** (`wh.data` statt der evaluierten,
halbierten Mesh) → Kennwerte bleiben mit ungeschnittenen Läufen vergleichbar. Wirkt auch in der
🔍 Vorschau (verifiziert: echter Längsschnitt mit halbierter Welle + Ringrohr-Querschnitt).
**Düse auf echten Hairpin abgestimmt + sichtbarer Kupfertreffer** (`_crown_target`): jede Düse (die eine
in der Nahaufnahme, sonst je Düse) wird auf einen **realen Kronen-(Kupfer-)Punkt** aus den STL-Überhang-
Vertices (`_ovinfo`) gesetzt — größter Radius, Zielhöhe **knapp UNTER der Kronenspitze** (`z_hit = ring_z
− 1,2·tube_r`, Kronen-**FLANKE**); der Strahl zielt **radial nach innen durch** den Punkt (`0.6·tgt`) und
**landet AUF dem Leiter** (verifiziert: Öl legt sich über die Kronen, `wetted_mean` 0,64→1,53 %). Zwei
frühere Fehlschläge: median-z-Ziel ⇒ Richtung ≈ −z axial vorbei (`wetted 0 %`); Apex GENAU auf Düsenhöhe
⇒ halber Sprühkegel fliegt über die Spitze. Nahaufnahme: Düse UND Kamera teilen `close_th`/`close_tgt`
(kein Winkel-Mismatch), Kamera `cam_d=2.2·span` von außen-oben (nicht enger — sonst OD-Zähne). Der
**Keil-Ausschnitt** wird nach **radialem Band** eingefärbt (Welle/Rotoreisen/Stator, Radien via cfg) +
Kupfer am Überhang. **Zeitlupe** (`oil.slowmo` 1–50, UI `#oil_slowmo` bis 50× Ultra): cfg
`time_scale = 1/slowmo` → Mantaflow `ds.time_scale` — weniger Sim-Zeit pro Frame, das Video (feste fps)
zeigt Strahlflug/Aufprall/Tröpfchen als Slow-Motion; Rechenzeit/Frame gleich, realer Zeitausschnitt
kürzer. **Speicherfunktion:** `_persist` legt `results.json` **an** wenn sie fehlt (Öl-Lauf ohne
vorherige Analyse ging sonst verloren); `load_saved(project_dir)` lädt den Lauf zurück (Chart-Dateien →
base64, `video`-Flag = Existenz von `frames_oil/anim.mp4`) → `GET /project/<id>/oilspray`; UI-Knopf
**„📼 Gespeicherten Lauf laden"** + stilles Auto-Laden beim Öffnen des 💧-Tabs (`switchTab('oil')`,
nur wenn nichts läuft/angezeigt). Alter **Mantaflow-Cache** (`blendcache_oil`) wird je Lauf gelöscht
(sonst stale Bake bei geänderten Einstellungen). **Video-Zoom** (`_oilInitZoom`, reine Frontend-Lupe):
Mausrad zoomt (bis 8×, CSS-Transform), Ziehen verschiebt NUR wenn gezoomt (bei 100 % bleiben die
Video-Controls bedienbar), Doppelklick/⟲ reset; 🔍±-Knöpfe unter dem Video. **Domain-Auflösung bis
1000** (`RES_RANGE=(24,1000)`, UI `#oil_res` max 1000 — Kosten ~kubisch, >512 **RAM-kritisch** (OOM →
leerer Bake → schwarzes Video), Warnhinweis im Hilfetext; nur mit fokussierter Domain + wenigen Frames sinnvoll).
**Bauteil-Häkchenlisten + Ansicht (`oil.show`/`oil.cut`/`oil.view_mode`, `build_winding_head_stl_script(
components=,cut=,view_mode=)`):** zwei Listen — **👁 Anzeigen** (welche Bauteile gebaut werden →
gen*-Flags: Wickelkopf/Rotor/Stator/Welle/Magnete) und **✂ Schneiden** (welche davon aufgeschnitten
werden). Ansicht **Ausschnitt** (Keil, `common(_wedge)` — geschnittene Bauteile auf das Tortenstück
reduziert, Rest voller Ring) vs **Gesamt** (voller 360°-Kern, geschnittene Bauteile mit `cut(_wedge)`
= herausgeschnittener Cutaway). Der **Wickelkopf wird IMMER nur über den Ausschnitt** gebaut
(`hairpin_slot_limit`, Rechenzeit); der Kern ist ohnehin ein voller Ring und wird getrimmt.
`_classify` ordnet FreeCAD-Objekte (Shaft/Rotor/Stator/Magnet*/Pin_*·Coils) den Keys zu.
**Zeitlupe bis 500×** (`slowmo` 1–500 → `time_scale=1/slowmo`, untere Klemme jetzt `0.001`).
**⚡ Schnelle Darstellung** (`oil.fast`): Workbench-Engine + weniger Substeps + KEINE
Sekundärpartikel → grobe, schnelle Vorschau. **Strahlrichtung justierbar** (`jet_tilt_deg` axial,
`jet_yaw_deg` tangential, um den echten `_crown_target`-Grundstrahl gedreht → trifft die
Wickelköpfe weiterhin) + **🔴 Ziellinie** (`show_jet_line` → leuchtende `JetLine_*`-Zylinder je Düse
zeigen im Video, wohin der Strahl trifft). **Neigungs-Vorzeichen (Gotcha, 2026-07-23 gefixt):**
Konvention wie die UI-Skizze — POSITIVE Neigung = zur Blechpaket-Stirnfläche (−z); die positive
Drehung um die lokale Tangente kippt den radial-einwärts-Strahl aber nach +z (k×v=+z), daher dreht
das Blender-Skript mit **`Rotation(-JET_TILT, …)`** (vorher +JET_TILT ⇒ Skizze und Modell zeigten
entgegengesetzt). **Feste Kamera-Ansichten (`oil.cam_view`, UI `#oil_cam_view`
auto/wh_hero/top/front/section):** **„schräg oben auf die Wickelköpfe" (`wh_hero`)** — 3/4-Blick
von außen-oben näher an den Wickelkopf-Überhang (Ziel = Mitte Blechpaket-Ende…Kronen-/Ring-Ende,
horizontal: Kamera hoch +y zum +z-Ende, Bild-Oben=Motorachse `_cam_up_ovr='Z'`); „von oben"
(entgegen der Schwerkraft; horizontal ⇒ Kamera +y, Bild-Oben = Motorachse via `_cam_up_ovr='Z'`)
und „von vorne" (Stirnansicht, Kamera am +z-Ende, Blick −z, `_cam_up_ovr='Y'`; vertikal fällt
„oben" mit „vorne" zusammen) — überschreibt NUR die Kamera (Nahaufnahme/Schnittkörper bleiben
wie eingestellt, die Schnitt-Kameramatrix wird bei aktiver wh_hero/top/front-Ansicht übersprungen),
Drehteller orbitet um die Override-Oben-Achse. **Gotcha (2026-07-28 gefixt, „schwarzes Video"):**
`wh_hero` ist eine SCHRÄGE 3/4-Ansicht (Kamera oben-seitlich versetzt) und MUSS ihr Ziel per
`_track_quat(cam_tgt−cam.location,'-Z',_cam_up)` anpeilen. `wh_hero` setzt zwar `_cam_up_ovr='Z'`,
darf aber NICHT in die achsparallele „von oben"-Explizit-Rotationsmatrix (Blick strikt −y) fallen —
sonst schaut die schräg-hoch stehende Kamera waagerecht ÜBER die Geometrie hinweg → **leeres/
schwarzes Bild** (verifiziert: Frames RGB≈15–23). Die Explizit-Matrix gilt nur für `top`/`front`;
`wh_hero` behält die `_track_quat`-Rotation (der `_cam_up_ovr`-Block überspringt weiterhin die
Schnitt-Kameramatrix). Reproduzierbar über `preview_oilspray` (gleiche Kamera, ohne Bake).
**„section" = Schnitt-Orientierung OHNE Schnitt** (`_SECTION_CAM = SECTION_CUT or CAM_VIEW=="section"`):
dieselbe Section-Kamera (senkrecht auf die Ebene Motorachse↔`SECTION_NOZ`-Düse, `SECTION_ZOOM`- und
`CLOSEUP`-abhängig wie beim echten Schnitt) UND dieselbe explizite `_radc`/`_nrmc`-Bild-Oben-Basis
(`elif _SECTION_CAM:`), aber der Boolean-Cut-Block (`if SECTION_CUT:`) läuft NICHT → Wickelkopf-Ansicht
in Schnitt-Blickrichtung, Motor ungeschnitten (Nutzerwunsch). **🔍 Zwischenansicht/Vorschau (`preview_oilspray`,
`POST /oilspray/preview`, `cfg["preview"]`):** rendert VOR dem teuren Bake EIN Standbild — nur
Geometrie + Düsen + Strahl-Ziellinien (Blender-Skript `if PREVIEW:` überspringt `bake_all` + Metrik/
Frame-Loop, blendet die leere Domain aus, `sys.exit(0)` nach `OIL_PREVIEW:`; `SHOW_JET_LINE` erzwungen,
Workbench+fast). Eigene isolierte `oilspray_preview/`-Arbeitsdateien (berührt weder `frames_oil` noch
Bake-Cache noch `results.json`); teilt `_oil_state` mit dem Voll-Lauf. UI: Knopf „🔍 Vorschau
(Strahllinien, ohne Bake)" (`startOilPreview` → `_pollOil` verzweigt bei `result.preview` auf
`_renderOilPreview`); `_oilBuildPayload` ist der geteilte Payload-Builder für Voll-Lauf + Vorschau.
**Drehteller-Vorschau (`preview_turns`, UI `#oil_pv_turns` 1/12/24/36):** >1 ⇒ das Blender-Skript
orbitet in der PREVIEW-Schleife die Kamera um `cam_tgt` um die Motorachse (Kamera-Oben-Achse `_pv_up`
= Welt-Y horizontal / Welt-Z vertikal, `Matrix.Rotation`) und rendert N Winkel `preview_%03d.png` in
`preview_dir` (Marker `OIL_PREVIEW:` je Bild + `OIL_PREVIEW_N:`); `preview_oilspray` sammelt sie zu
`out["images"]` (base64-Liste, `image`=erstes, `turns`=N). Der Browser lässt das gerenderte Standbild
**drehen** (`_oilInitTurntable`: Ziehen/Touch + Slider blättert clientseitig durch die vorab
gerenderten Winkel — reines Frontend, kein Bake). 1 = einzelnes Standbild (alt).
**Blickrichtung „Unten" + Koordinatensystem + Materialien/Glättung (`view_down`/`show_axes`/`material`/
`smooth`/`oil_transparency`):** die **Unten-Achse** (`view_down` auto/±x/±y/±z, UI `#oil_view_down`) dreht die
**Kamera** — sie setzt die Kamera-Oben-Achse (`_up_axis_str`→`_cam_up`, `_DOWN2UP`) UND die Drehteller-Orbit-
Achse (`_UP2VEC[_cam_up]`); rein Blickrichtung, die Schwerkraft/Physik steuert weiter `orientation`. Ein
**Koordinatensystem** (`SHOW_AXES`, in der Vorschau immer an, sonst `#oil_show_axes`) blendet emissive XYZ-Pfeile
mit Beschriftung an der Modell-Ecke ein (X rot/Y grün/Z blau, Z=Motorachse) → Orientierung im drehbaren Bild.
**Materialien in der Vorschau** (`material`, `#oil_material`): rendert die Vorschau mit EEVEE (Kupfer/Stahl/
transluzentes Öl) statt flachem Workbench; **Shade Smooth** (`smooth`, Default an, `_smooth()` = `shade_smooth`
+ `shade_auto_smooth`-Winkel, Fallback per-Polygon) lässt die Netzfacetten auf Kronen/Rohr verschwinden;
**Öl-Transparenz** (`oil_transparency` 0..1 → `OIL_ALPHA`, EEVEE `use_screen_refraction`+SSR). Im Drehteller
folgt das Fülllicht der Kamera (jede Seite beleuchtet). **Einbaulage sichtbar** (`_cam_up` folgt `view_down`,
auto = 'Y' horizontal / 'Z' vertikal → die Motorachse steht im vertikalen Fall aufrecht, das Öl läuft der Achse entlang ab).
**Darstellungs-Presets + Rechen-Pakete (`ema_oilspray.save_preset`/`list_presets`/`delete_preset`,
Store `~/cae_projekte/_oilspray/presets.json`):** eine benannte 💧-Darstellung = der KOMPLETTE
oilspray-Payload (`_oilBuildPayload`, also Ausschnitt/Öl/Kamera/Auflösung …). Server `GET|POST
/oilspray/presets` + `POST /oilspray/presets/<id>/delete`. UI-Karte **„💾 Darstellungen & Rechen-
Pakete"** (`oilSavePreset`/`oilRefreshPresets`/`oilDeletePreset` + Häkchenliste): mehrere ausgewählte
Presets gehen als **Paket** über `enqueueJobs` (Typ `oilspray`) in die Server-Job-Warteschlange
(`ema_jobs`) und laufen nacheinander durch (auch bei geschlossenem Browser → Tab ⏳ Jobs) — „Berechne
Darstellung 1, 5, 6". Gate: `test_oilspray.py` `test_presets_store_roundtrip`.

**Auto-Varianten-Store (`oilspray_runs/<id>/`):** jeder fertige Lauf wird AUTOMATISCH als eigene
Variante (Video + Charts + `run.json`) abgelegt (`_autosave_variant`), sodass ein neuer Lauf die
vorherigen NICHT überschreibt; `list_saved_runs`/`load_saved_run`/`saved_run_video`/`delete_saved_run`
+ Server `/project/<id>/oilspray/saved(/<rid>(/video|/delete))`, UI-Karte „🎞 Gespeicherte Läufe"
(`refreshOilVariants`/`loadOilVariant`/`deleteOilVariant`, Variante lädt mit eigenem `video_src`).
**Damit das Öl DÜNNFLÜSSIG spritzt + Tröpfchen bildet (statt als Gel-Klumpen zu hängen — Nutzer-
Beanstandung), drei Hebel:** ① **dünnflüssiges Öl per Default** (`viscosity≈0,004`) — der **Mantaflow-
Viskositätslöser läuft NUR bei zähem Öl `VISC>0,02`** (ein aktiver Löser macht selbst kleine Werte
gelartig → Klumpen). ② **Moderate Oberflächenspannung** (`surface_tension≈0,01`): hoch genug für
Tröpfchenbildung beim Auftreffen, niedrig genug dass sich der Strahl nicht sofort zur einen Kugel
zusammenzieht (0,03 ballte ihn zu, 0,003 verschmierte ihn film-/rope-artig ohne Tropfen). ③
**Sichtbarer Düsenstutzen:** je Düse ein kleiner Stahl-Zylinder radial nach innen am Ring, der Emitter
sitzt an der **Stutzen-Mündung** (`r_emit=r_noz−stub_len`) → das Öl tritt sichtbar aus einer Bohrung aus
(Emitter-Würfel selbst `hide_render`). **Scope-Ehrlichkeit (bewusst NICHT weiter getrieben):** bei
1-mm-Düse + 3-mm-Ringspalt ist der freie Strahl sub-pixelig/kurz; ein „gestochener" Laser-Strahl bräuchte
sehr hohe RES (rechenintensiv, Nutzer ist rechenleistungsbegrenzt). Ein Versuch mit *fokussierter*
Nahaufnahme-Domain (eng um den Strahlweg für feine Zellen) wurde **verworfen** — die offenen Ränder ließen
den schnellen Strahl sofort aus der kleinen Domain austreten (Öl erreichte den Leiter nicht mehr); die
weite Domain lässt die Tropfen dagegen fliegen + auf den Leitern landen.
**Bäckt** (`fluid.bake_all`), rendert je Frame und misst **Benetzung** (KDTree Effector-Vertices ↔
Liquid-Vertices im Nahband) + **Tropfenzahl** (Mesh-Inseln via bmesh) → `OIL_METRICS:<json>`, plus
eine **Abdeckungs-Heatmap** (Effector nach kumulierter Benetzung emissiv eingefärbt). **Leer-Bake-
Wächter (Gotcha „großer Quader statt Spray"):** die Domain trägt das (amberne) Öl-Material; produziert
der FLIP-Bake für einen Frame KEIN Fluid (Bake fehlgeschlagen — z. B. Domain durch Kollisions-Gehäuse/
vollen Ring + hohe Auflösung zu groß → OOM/Timeout —, Auflösung zu grob für die Düse, oder Lauf während
des Bakes abgebrochen), rendert Blender die **nackte Domain-Würfel-Mesh** = ein großer amberner Quader
statt Spray. Deshalb wertet der Frame-Loop (BEIDE Skripte, oilspray + `ema_spraytest`) das Fluid-Mesh
**vor** dem Render aus und setzt `dom.hide_render = (len(vs)==0)`; ist der Bake über ALLE Frames leer
(`_liquid_total==0`), meldet er das laut (`OIL_STAGE:⚠ Bake hat KEIN Öl erzeugt …`) statt still den
Würfel zu zeigen. **Unter-Auflösungs-Wächter (Gotcha „Ölstrahl nicht sichtbar"):** der Freistrahl
braucht ≥~2 Zellen über der Bohrung, sonst bildet der FLIP-Löser kein zusammenhängendes Öl-Mesh und der
Strahl „verschwindet" (häufigste Falle: die **Kollisionswand 🧱** zieht die Domain bis zur Gehäuse-
Innenwand auf → grobe Voxel bei gleicher Auflösung; verifiziert: 260-mm-Stator, 🧱 an, RES 260, 1-mm-Bohrung
⇒ Voxel ≈ 0,98 mm ⇒ Strahl ~1 Zelle; 🧱 aus ⇒ fokussierte Domain, Voxel ≈ 0,23 mm ⇒ ~4 Zellen). BEIDE Skripte
(oilspray + `ema_spraytest`) berechnen beim Domain-/Düsen-Setup `_jet_cells = Bohrungs-Ø / voxel` und melden
bei `<2` **früh** (vor dem Bake) laut `OIL_STAGE:⚠ Strahl unter-aufgelöst …` mit konkreter Abhilfe (🧱 aus /
Nahaufnahme / Auflösung erhöhen — im oilspray-Skript kontextabhängig aus `_haus_col`/`CLOSEUP`); die Kennwerte
`jet_cells`/`voxel_mm`/`jet_underres` wandern zusätzlich ins Ergebnis (`OIL_METRICS`), und `_renderOil`
zeigt bei `jet_underres` ein Warn-Banner oben im Ergebnis. Gate: `test_oilspray.py`/`test_spraytest.py`
(`Strahl unter-aufgelöst` + `jet_underres`). **Live-Auflösungs-Empfehlung (`_oilRecommendRes`, Hint
`#oil_res_hint`):** aus Bohrungs-Ø + Stator-Ø + 🧱/Nahaufnahme rechnet der 💧-Tab clientseitig
`Voxel ≈ 2·halbe-Domain-Spanne/RES` (Spanne ≈ ½·Stator-Ø mit 🧱, sonst ~0,13·Stator-Ø fokussiert)
und empfiehlt `RES ≥ 2·Spanne·3/Bohrung` für ~3 Zellen; ist das mit 🧱 selbst bei 512 unmöglich, rät
der Hint zu **🧱 aus / Nahaufnahme** (der wirksamere Hebel). Ausgelöst per `oninput` von
`oil_nozzle_d`/`oil_res` + `onchange` von `oil_housing`/`oil_housing_collide`/`oil_closeup` und aus
`_oilDrawAngleFig`. (3) `blender_runner.run_blender_script` führt es
gestreamt aus (Marker `OIL_STAGE/OIL_FRAMES/OIL_METRICS/OIL_DONE`, Abbruch via `abort_current`).
(4) Frames → `frames_oil/anim.mp4` (ffmpeg, reuse `ema_em3d._encode_video`), Kennwert-Charts
(matplotlib), `results["oilspray"]` schlank in `results.json` gemergt (`_persist`, ohne base64).

**Gotcha — Blender-Build (kritisch):** Das Ubuntu-**`apt`-Blender** linkt gegen System-libpython →
Mantaflow stürzt headless mit `PyImport_AppendInittab() may not be called after Py_Initialize()`
ab (Fluid-Sim unbrauchbar). `blender_runner._find_blender()` bevorzugt daher einen **portablen
blender.org-Build** (`~/blender_portable/blender-*/blender`, bringt eigenes Python mit; bäckt
korrekt) vor `/usr/bin/blender`; `$EMA_BLENDER` überschreibt. `BLENDER_OK` ist **False beim reinen
apt-Build** → Server `/oilspray` 503t mit Install-Hinweis. Getestet: 4.2.9 LTS. **Weitere Gotchas:**
Blender 4.2 hat EEVEE in **`BLENDER_EEVEE_NEXT`** umbenannt → das Skript löst die Engine gegen die
echte Enum auf (`_pick_engine`); `KDTree.find` liefert **`(position, index, distance)`** (nicht
index zuerst); **Bake ist CPU-gebunden** (GPU nur beim Rendern). Server: `/oilspray` (503 wenn kein
taugliches Blender), `/oilspray/status`, `/oilspray/abort`; Video über `project_video`
(`video_subdirs["oil"]="frames_oil"`). UI: Tab **💧 Spritzöl-Kühlung** (`panel-oil`, `startOilspray`/
`_pollOil`/`_renderOil`) mit Ausschnitt-/Öl-/Auflösungs-Feldern + Scope-Grenze-Hinweis. Test:
`test_oilspray.py` (Skript-Generierung/Marker/Charts/Persist ohne Blender/FreeCAD).

### Quantitative Spritzöl-Kühlung (OpenFOAM VOF / interFoam) — `ema_cfd.py` / `openfoam_runner.py`

Eigenständiger On-Demand-Pfad **neben** dem qualitativen Mantaflow-💧 (Details in der File-Map-
Zeile `ema_cfd.py`). Auf DEMSELBEN Wickelkopf-Ausschnitt läuft eine echte VOF-Zweiphasenströmung
(Öl/Luft, `interFoam`) → benetzte Fläche %, Filmverteilung und ein daraus abgeleiteter **effektiver
Wärmeübergangskoeffizient (HTC)**. Bei gewählter Ölkühlung speist der HTC über `ema_pipeline` das
LPTN-Thermikmodell (`ema_thermal`, direkter Wicklung→Kühlmittel-Pfad `G_w_cool`, opt-in) — die
Motortemperaturen folgen dann dem gerechneten Spray statt dem pauschalen Preset-`h_eff`. Spiegelt
exakt die Elmer-3D-Architektur (Subprozess-Wrapper `openfoam_runner` wie `elmer_runner`, threaded
Server-State `_cfd_state`, `/cfd`-Routen, Job-Typ `cfd`, Tab **🌊 OpenFOAM (quant.)**). **Scope-
Ehrlichkeit (steht im UI + Bericht):** `interFoam` ist ISOTHERM — die Strömung/Benetzung ist
gerechnet, der HTC ist ein **korrelationsbasierter Kennwert** (Prallstrahl-Nusselt, Stufe 1), KEIN
aufgelöstes Temperaturfeld; ein voll konjugierter HTC (CHT, `chtMultiRegionFoam`) wäre die Folgestufe
im gleichen Gerüst. Verifiziert: End-to-End auf einem synthetischen STL (blockMesh→snappyHexMesh→
interFoam→foamToVTK→Benetzung/HTC) läuft mit OpenFOAM v2406.

**3D-Öloberfläche im Browser (gerechnetes VOF-Video + vtk.js-Viewer, wie 🧲 3D-Feld):** interFoam
schreibt je Schreibzeitpunkt das Volumen (`VTK/cfd_case_<N>/internal.vtu`, `alpha.oil`+`U` als
Punkt-/Zelldaten). Daraus wird — physikalisch gerechnet, im Gegensatz zum qualitativen Mantaflow-💧
— die **Öl/Luft-Grenzfläche als Isofläche `alpha.oil=0.5`** getract (`_oil_isosurface` via
`vtkContourFilter`, Punkt-Skalar `Umag`=|U|) und: ① je Zeitschritt offscreen mit **fester Kamera**
(aus den Wickelkopf-Bounds) + **fester |U|-Skala 0…jet_v** gerendert (`_cfd_video`) → `frames_cfd/
anim.mp4` (Strahlflug/Aufprall/Filmablauf; reuse `ema_em3d._encode_video`), ② der letzte Zeitschritt
als **schlanke float32-.vtp** exportiert (`export_browser_cfd` → `<projekt>/cfd/cfd_oil.vtp` +
`cfd_solid.vtp` = Wickelkopf-Wand mit Benetzung; `_lean_scalar_poly` behält EIN Skalar, `ema_em3d.
_write_vtp` schreibt vtk.js-lesbar). `run_cfd` legt beide + `video:bool` ins Ergebnis (NICHT
persistiert — transiente Case-Pfade, `_persist_cfd_summary` strippt `oil/solid_vtp_path`; nur das
`video`-Flag bleibt). Server: **`GET /cfd/vtp?part=oil|solid`** (aus `_cfd_state["result"]`, wie
`/em3d/vtp`) + `GET /project/<id>/video/cfd` (`video_subdirs["cfd"]="frames_cfd"`). UI (`_renderCfd`):
inline **`<video>`-Player** (autoplay/loop/muted) + Knopf **„🧊 Im Browser ansehen (3D)"** →
**`_cfdViewer`** (selbst-enthalten, teilt nur `_loadVtkJs`/`_e3Percentiles` mit dem em3d-Viewer):
Öl-Isofläche nach |U| eingefärbt (Blau→Bernstein→Rot) + halbtransparent über der opaken Kupfer-
Wickelkopf-Oberfläche (Depth-Peeling), Öl-Transparenz-Slider `_cfdOilOpacity`. Der Viewer lebt aus
dem In-Memory-`_cfd_state` (wie em3d-Nicht-gespeicherte-Läufe); das Video liegt persistent als Datei.
Payload-Flag `cfd.make_video` (Default an). Test: `test_cfd.py::test_isosurface_and_browser_vtp`
(synthetisches foamToVTK → Isofläche + 2 float32-VTPs, vtk-gated, ohne OpenFOAM).

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
| `ema_jobs.py` | **Persistente Server-Job-Warteschlange** (`~/cae_projekte/_jobs/queue.json`): EIN Worker-Thread arbeitet eingereihte Jobs (analyse/em3d/em3d_sweep/oilspray) sequenziell ab — Jobs überleben geschlossenen Browser + Server-Neustart (stale `läuft`→`abgebrochen`, Wartende laufen wieder an). Executors werden von `server.py` via `init({type:{run,busy,abort}})` registriert und schreiben in dieselben State-Dicts wie die Direkt-Routen (Live-Fortschritt in den Tab-UIs). Server-Routen `/jobs` + `/jobs/add|<jid>/cancel|clear_done|config`; UI-Tab **⏳ Jobs** + „➕ Warteschlange"-Knöpfe + `_reattachJobs` (Reattach beim Seiten-Laden). Test: `test_jobs.py` |
| `ema.html` | Single-file vanilla-JS browser UI (no build). Workflow-tab layout: a top tab bar (`switchTab`, tabs `projekt/geo/betrieb/calc/live/designer/import/em3d/oil/spraytest/jobs/results/compare` (`oil` = 💧 Spritzöl-Kühlung, Blender/Mantaflow; `jobs` = ⏳ Server-Job-Warteschlange, s. `ema_jobs.py`), `#hash` deep-linkable; **there is no `report` tab — the Bericht moved into Tab ①**). The **entry tab is `① Projekt`** (`panel-projekt`, the default landing tab) — **the central project hub** for everything project-scoped. Top row: create a project (`pjCreate` → `POST /project/new`, lays down the dir + `project.json` immediately, `status:"neu"`, `origin:"manual"`) · open existing ones (`pjRefreshList` from `/projects?detail=1`, **Galerie ⤢** = `openProjectGallery`). When a project is active (`#pj-active-wrap` shown), the cards are grouped under `.pj-group-h` headers: **📋 Projektdaten & Notizen** (Organisation/status/tags/notes → `/project/<id>/meta` + evolution/lineage; Projekt-Dokumente = per-project RAG via `/project/<id>/rag/add` + attachments via `/project/<id>/attachments`) · **📄 Auswertung & Bericht** (the **PDF-Bericht card** `#pj-report-card` with `#btn_report`/`#btn_report_agentic` → `generateReport(mode)` + `#report_status`/`#report_rag`; the **gespeicherte 3D-Läufe** card `#e3_save_name`/`#e3_saved_list` → `_e3SaveRun`/`_e3LoadRun`/`_e3DeleteSaved`, project-scoped under `<projekt>/em3d_runs/`) · collapsed `<details>` **🧰 Globale Werkzeuge & Daten** (global Wissensbasis `openRag` + LLM-Trainingsdaten `refreshTrainingStats`/`#training-stats`). **Active-project plumbing:** `window._activeProject` is the client truth; **`pjSetActive` also POSTs `/project/<id>/activate`** (lightweight — sets server `_state["project_dir"]`/`project_id` WITHOUT loading results) so report + em3d (which read `_state`) target the chosen project, then refreshes the report card (`pjUpdateReportCard`), the saved-3D list, and the training stats. `buildPayload()`/`_dsnBuildPayload()` attach `payload.project_id = _activeProject.id`, and `/analyse`'s `_run` (+ all em3d handlers via `_em3d_project_dir`) reuse that dir (generalised `reuse_id`) so every calculation/3D-run writes **into** the active project. `loadProjectById` calls `pjSetActive` too. `generateReport` prefers `_activeProject.id` (falls back to `/status`). The Tab-3 (Betrieb) project-management block was removed; `#project_name`/`#project_load` survive as hidden elements only to keep variant/param-table/applyPayload JS wired. The results-tab `🗂 Projektakte` `<details>` panel (`renderAkte`) still mirrors the same project contextually. The rest of the layout sits over `#workspace` = `#panel-area` (active panel) + draggable `#vsplit` + persistent `#preview-pane` (live `#simCanvas`, hidden on results/compare) + draggable `#hsplit` + `#footer` (staged-workflow buttons `#btn_cad_preview` (🧊 CAD ansehen → `startCadPreview`) · `#btn_smoke` (🧪 Smoke-Test → `startSmokeTest`) · `#btn_analyse` (⚙ Echte Berechnung), all sharing the `_wfModal`/`_pollWf` overlay helpers for the first two, plus `#analysis-progress`; drag `#hsplit` taller to reveal the full `#progress-log`). Inputs grouped into `.tab-panel`s; the `results` tab is gated `disabled` until an analysis finishes. `#vsplit`/`#hsplit` (`initSplitters`) resize preview width / footer height and call the canvas `resize()` live. The preview overlay has a pause button (`#ov_play` → global `toggleSim`/`_syncSimUI`, mirrors the Live-tab `#btn_play_pause`) so rotation can be stopped from any input tab. **Globales Speichern** (`#btn-global-save` in der Topbar + `#save-modal`): EIN Speicherknopf öffnet ein Vorschau-/Auswahl-Fenster (`openSaveModal`/`saveModalCommit`/`_buildSaveItems`), das **kontextabhängig** alles Speicherbare als abwählbare Positionen listet — **Projektdaten & Notizen** (`/project/<id>/meta`, liest `pj_*` bzw. bei passendem `akte-body.pid` die `akte_*`-Felder und schreibt beim Speichern in BEIDE zurück), **Bewertung** (`/project/<id>/rating`, gut/schlecht-Select), **3D-Feld-Lauf** (`/em3d/save`, sichtbar via `window._e3HasResult`, gesetzt in `_renderEm3d`/`_renderEm3dSweep`), **Varianten-Set** (`/variants/save`, wenn `variants.length`). Jede Zeile zeigt eine Vorschau + Häkchen (+ optional Name/Bewertung), Commit speichert alle angehakten nacheinander mit ✓/❌ je Zeile. Die alten Einzel-Speicherknöpfe (Projektdaten/Akte/3D-Lauf/Varianten) zeigen jetzt alle auf `openSaveModal()`; `pjSaveMeta`/`saveAkteMeta`/`_e3SaveRun`/`saveVariantSet` bleiben als Funktionen bestehen, die Buttons rufen aber das Modal |
| `ema_pipeline.py` | Pipeline orchestrator (`run_pipeline`) + material tables + all chart builders |
| `ema_topology.py` | Single source of truth for rotor magnet placement (`magnet_legs`, `Leg`, topology labels) — consumed by `ema_freecad` + `ema_analysis`; mirrored by JS `magnetLegs` in `ema.html` |
| `ema_freecad.py` | FreeCAD script generators (rotor, full motor, rotor FEM); interior pockets + surface arc magnets from `magnet_legs`; parametric hairpin end-windings (`conductorsPerSlot`/`coilPitch`, collision-free radial-split crowns) |
| `freecad_runner.py` | FreeCAD subprocess wrapper + marker parsing + generic FEM script builder |
| `ema_analysis.py` | 2D-FDM EM field solver + analytical performance (torque, EMF, saliency, d/q currents) |
| `ema_thermal.py` | 6-node lumped-parameter thermal network (steady + transient + per-cycle). **CFD-Kopplung (opt-in):** `conductances`/`run_thermal_analysis`/`solve_transient_series` nehmen `htc_oil`/`wetted_area_m2` (aus `ema_cfd`) → direkter Wicklung→Kühlmittel-Pfad `G_w_cool` in `build_GA` + RHS an Knoten W; Default 0 ⇒ unverändertes Preset-Modell (`COOLING_PRESETS["oil"]["h_eff"]=2500`) |
| `ema_drivecycle.py` | Drive cycles (WLTP-3b, full-load, trailer, CSV) + drivetrain + energy integration. Trailer is user-parametric: `trailer_mountain_cycle(max_grade_pct)` (steepest uphill = that grade %, slope arrays stored in **degrees**) + `trailer_vehicle(base, trailer_mass_kg, n_axles)`; the `/analyse` payload carries `trailer:{mass_kg,n_axles,grade_pct}` |
| `ema_compare.py` | Multi-project comparison overlays |
| `ema_report.py` | LLM → Markdown → pandoc → pdflatex PDF report (standard + agentic modes). Embeds project images via `[BILD:key]` placeholders → `insert_images` (`build_context` `pairs`); the EM section features the FDM field maps `em_field` (Leerlauf) + `em_field_load` (Last) rendered by the pipeline's field stage to `charts/em_field*.png`, plus `airgap`/`em_curve`. Unknown keys (legacy projects without an image) are stripped cleanly; for an old project, re-run the **field** stage (Stufen nachrechnen) to generate them. **Formatting:** the prompt asks for LaTeX math (`$…$` inline, single-line `$$…$$` display — `_normalize_paragraphs` treats `$$` lines as structural so they aren't merged); `render_pdf` injects `_report_header.tex` (`ragged2e` document-wide → left-aligned, fixes the "1–2 words per line" justified-stretch around long unit/formula tokens; `float`+`[H]` to pin figures); `_strip_md_tables` is applied to standard + agentic output too (local models emit malformed centered pipe-tables). **NO numeric values in the prose** (the local model routinely mis-assigns them → nonsense): the standard + agentic single-project reports inject a comprehensive deterministic `[TABELLE:kennwerte]` (`_single_md_tables`, grouped by domain) right after the summary, the prompt demands QUALITATIVE prose + symbolic-only formulas, and `_strip_value_numbers` removes any straggler number+unit token (keeps the unit, inserts `…`; material codes like `M270-35A`/`N52` are protected). `_strip_value_numbers` also runs inside `_clean_prose` so the comparison/agentic comparative prose is value-free too. **3D-Feld in BEIDEN Einzelberichten:** when `results["em3d"]` exists, both `generate_report` and `generate_report_agentic` call `_ensure_em3d_section` (own bebilderter „3D-Magnetfeldvalidierung (Elmer FEM)"-Abschnitt + `em3d_*` images) and `_single_md_tables` adds the 2D-vs-3D table — so a 3D run on the active project always surfaces in the PDF (the old `…_em3d`-subproject split that hid it is gone now that em3d is project-bound). **Spritzöl-Kühlung im Bericht (analog):** when `results["oilspray"]` exists, `build_context` zieht `ctx["oilspray"]` (Benetzungs-Proxys + `oil_coverage`/`oil_wetting`/`oil_droplets` charts), both generators call `_ensure_kuehlung_section` (own qualitativer, scope-ehrlicher „Spritzöl-Wickelkopfkühlung"-Abschnitt + Bilder) and `_single_md_tables` adds a cooling-proxy table — so a 💧-Lauf auf dem aktiven Projekt landet ebenfalls im PDF |
| `ema_chat.py` | Ollama Q&A over results/comparison (`chat_results`/`chat_compare`); compacts results JSON (strips base64/frames). Each project-scope chat is grounded on a per-project **`_machine_datasheet(meta)`** (topology/dims/winding/magnets/materials/operating point, built from `meta.json` — `results.json` holds only outputs, so the server loads `meta.json` from `project_dir` and passes it to `chat_results`). Served by `POST /chat` (`scope:"project"\|"compare"`); UI is the floating `💬 Chat` widget in `ema.html`. **RAG:** `_rag_doku(message)` injects retrieved `doku`-category snippets from `ema_rag` into both system prompts (best-effort) |
| `ema_optimize.py` | LLM-steered target-value optimisation. `evaluate_fast` scores a candidate WITHOUT FreeCAD/FEM (EM at low N + analytical Kt/torque + steady LPTN thermal + analytical struct sweep + analytical mass, ~0.5 s). Its inner geom→metrics core is factored into **`_eval_geom(geom, axial, mats, op, …)`** (works for ANY `magShape` incl. `"custom"`); `evaluate_fast` = `_apply_params` (parametric `FREE_PARAMS`) then `_eval_geom`. The per-magnet optimiser (`ema_design_optimize`) reuses `_eval_geom`/`_fitness`/`_violation`/`_ollama_chat`/`_extract_array`. `optimize(spec)` seeds + lets `ministral-3` propose batches over `FREE_PARAMS`, deterministic clamp + feasibility/fitness pick the best feasible design. Served by `POST /optimize` (threaded, `_opt_state`, body factored into `_optimize_body`) + `GET /optimize/status` + `GET /optimize/meta`; UI is the `🎯 Zielwertoptimierung` modal (Berechnung tab / `#optimize`). "Übernehmen" applies the best params to the form for a final full pipeline run. **Als Job:** „➕ Warteschlange" (`queueOptimize`, Job-Typ `optimize` → `_exec_optimize`) reiht die Optimierung server-seitig ein (läuft bei geschlossenem Browser); das Ergebnis liegt in `_opt_state`, der Jobs-Knopf „🎯 Ansehen" (`openJobOptimize`) öffnet das Modal + rendert es |
| `ema_paramstudy.py` | **Parameterstudie bei fester Drehzahl**: `run_study(payload, param, lo, hi, steps=100, rpm)` sweeps ONE `ema_optimize.FREE_PARAMS` parameter x→y in N steps at a fixed speed and plots EVERY result metric over the parameter (small-multiples grid). Reuses `ema_optimize.evaluate_fast` (FreeCAD/FEM-free, geometry varied per step), so 100 points cost ~50 s. Served by `POST /param_study` (threaded, `_study_state`, body factored into `_param_study_body`) + `GET /param_study/status`; UI is the **„📈 Parameterstudie"** panel (Berechnung tab) — parameter dropdown filled from `/optimize/meta`. **Als Job:** „➕ Warteschlange" (`queueParamStudy`, Job-Typ `param_study` → `_exec_param_study`) reiht die Studie server-seitig ein; das Ergebnis liegt in `_study_state`, der Jobs-Knopf „📈 Ansehen" (`openJobStudy`) öffnet Tab ④ + rendert es (`_studyRenderDone`). **Custom (Designer/KI) designs:** `run_study` honours `geom.customLegs` (they ride through `evaluate_fast` unchanged), so the Designer-Tab button **„📈 Parameterstudie für diesen Entwurf"** (`dsnParamStudy`) runs the same study on the drawn geometry; the UI then restricts the dropdown to the geometry-effective params (`_CUSTOM_STUDY_PARAMS` = axial/airgap/slotDepth/p/magGap — magnet-shape params are no-ops on freehand magnets) and shows a banner (`_studyDesignPayload`, reset via `dsnClearStudyDesign`) |
| `ema_design_ai.py` (KI-Auslegung) | **KI entwirft komplette Maschinen aus einer Beschreibung** (Designer-Pfad). `design_variants(brief, n=3, model)` → list of full designs: parametric scalars (via `ema_text2ema.SCHEMA`+`_validate`) **plus** a freehand HALF-pole `magnets`/`barriers` layout in canvas format (`{r,off,ang,len,thick,pol}` / `{pts,width}`, pol-local mm) **plus** `begruendung`. RAG-grounded on `maschinen` references (`ema_rag.context_for`). **Robustness:** the local LLM call uses Ollama **`format:"json"`** (otherwise the combined schema's JSON is frequently broken — decimal commas, comments) + a lenient `_extract_obj` (strips `//`/`/* */` comments + trailing commas). `_validate_layout` clamps every magnet inside the rotor (true fit-length via the quadratic, NO 5 mm floor — magnets that cannot fit are dropped), **keeps everything in the half pole** (magnet offset ≥0, barrier points clamped to y≥0), **drops magnets that overlap an already-kept magnet** (`_obb_overlap` SAT on the rotated rectangles, `_MAG_MAG_CLEAR` gap — any count is fine, 1 pole-sized or many small, just no intersection; the d-axis mirror is deliberately NOT checked so a V/U arm may sit next to its own reflection) and **drops flux barriers that overlap a magnet** (`_polyline_hits_magnet` samples each slot polyline against every magnet AND its d-axis mirror, clearance `BARRIER_MAGNET_CLEARANCE_MM` + half the slot width — a barrier carved through a PM is nonsense geometry; the LLM prompt also forbids it); if the freehand layout is empty/unusable, `_legs_to_canvas(_params_to_geom(params))` synthesises a valid half-pole from the parametric topology (`magnet_legs`) so a drawable design ALWAYS results (`fallback:true`). **Qualitäts-Vorsortierung + Regenerierung:** jeder Entwurf wird sofort FreeCAD/FEM-frei bewertet (`_quick_eval` → `ema_optimize._eval_geom` auf der gespiegelten Custom-Geometrie + dieselbe Heuristik wie `ema_training.auto_label` → `verdict` gut/schlecht); fällt er **„schlecht"** aus, generiert `design_variants` mit gezieltem Mängel-Feedback einen neuen (bis `max_regen`=2 Nachversuche je Slot, `_gen_one` mit Parametrik-Fallback), nimmt den besten Versuch (`_quality_score`: gut>unbekannt>schlecht, dann B_gap) in `variants` (mit `quality`-Urteil) und sammelt die verworfenen in `rejected`. Return: `{variants, rejected, regenerated, rag_used, model}`. The per-slot generate→presort→regenerate loop is factored into **`_gen_slot(... post_fn=None)`**. **Bereichs-/Zufalls-Entwurf (the UI's only generator now):** `design_variants_ranged(ranges, n, …, brief="")` samples statorOD/axialLen/shaftD **and the air gap** from the user's von–bis ranges per variant (air gap clamped to `AIRGAP_RANGE`=0.5–3 mm), prepends the optional `brief` to each variant's task, **hard-forces** the dims via `_apply_ranged_dims` (statorID/rotorOD derived from the gap, **bore capped at `STATOR_SPLIT`·OD so the stator keeps a real wall for slots+back-iron instead of becoming a sleeve**, `slotDepth` set from that wall, magnets re-clamped) while the LLM fills the rest + draws magnets/barriers, and pins the eval to the fixed speeds `RANGED_RPM_LIST=[1000,5000,15000,20000]` (returned as `rpm_list`). Served by `POST /design_ai` (Body `{brief,n,model?,max_regen?}`) + `POST /design_ai_ranged` (Body `{ranges,n,model?,max_regen?}`), both threaded on `_design_state` + `GET /design_ai/status` |
| `ema_design_optimize.py` (Per-Magnet-Optimierung) | **Fine-optimises the DRAWN magnet coordinates** of a custom design (vs `ema_optimize` which varies global parametric fields). Vector = per master-leg `{r,off,ang,len,thick}` + barrier widths, bounds from rotor geometry. `_apply_vec` rebuilds master magnets → `ema_design_ai._validate_layout` (re-clamps) → `_mirror_legs`/`_mirror_barriers` (d-axis mirror, identical to `dsnBuild`, with **dedup** of coincident legs) → `magShape:"custom"` geom → `ema_optimize._eval_geom`. Pole symmetry preserved (only the master half-pole is perturbed, mirror regenerated per candidate). `optimize_custom(spec)` reuses the `ema_optimize` loop/fitness/LLM-propose. Served by `POST /design_optimize` (threaded, `_design_opt_state`) + `GET /design_optimize/status`; result's `best_magnets` drawn back onto the canvas |
| `ema_rag.py` | **Lokale Wissensbasis (RAG)** unter `~/cae_projekte/_rag/index.json`. EINE Basis, pro Dokument eine **Kategorie** `maschinen` (Referenzmaschinen → `ema_text2ema.derive`) oder `doku` (Doku → `ema_chat`). Embeddings über Ollama `/api/embeddings` (`nomic-embed-text`), Chunking ~900 Zeichen/150 Überlappung, Retrieval = Cosine (numpy). `add_text`/`add_file` (txt/md/csv direkt, **PDF via `pypdf`**), `search(query, category, k)`, `context_for(query, category)` (Prompt-Injektion), `list_documents`/`delete_document`/`stats`. Beide Konsumenten injizieren **best-effort** (ohne Ollama/Embeddings läuft alles weiter ohne Kontext). **Pro-Projekt-Store:** alle Funktionen nehmen ein optionales `store_dir` (None = globale Basis, sonst `<dir>/index.json`) → die Projektakte legt unter `<projekt>/rag/` einen eigenen Store an; `context_for_project(query, project_dir)` fragt Projekt-Store zuerst + globale Basis gemerged ab (genutzt von `ema_chat` mit `project_dir`). Server: `/rag/list`, `/rag/add`, `/rag/upload`, `/rag/delete/<id>`, `/rag/search` (global) + `/project/<id>/rag*` (pro Projekt, s. `ema_projekt`); UI: **„📚 Wissensbasis"**-Modal (Geometrie-Tab / `#rag`) + Projektakte-Panel |
| `ema_text2ema.py` | Text → parameter set. `derive(description)` asks `ministral-3` to fill the `SCHEMA` fields, then `_validate` clamps every value to its range/enum and enforces radial ordering (statorOD>statorID>rotorOD>shaftD>shaftBoreD, ~0.7 mm air gap, slots≈6·p) so the result always loads. Served by `POST /text2ema`; UI is the `🧠 Text → Auslegung` modal (Geometrie tab / `#text2ema`) → "In Formular übernehmen". **RAG:** retrieves `maschinen`-category reference machines from `ema_rag` and injects them into the prompt (returns `rag_used`); no web yet |
| `ema_experts.py` | Agentic report mode: parallel per-section LLM expert agents. `run_expert_agents` (experts on ONE project) + `run_expert_agents_compare`/`assemble_expert_section_compare` (the SAME experts judge ALL variants **comparatively** with Vor-/Nachteile je Variante — used by the agentic comparison report). **8 experts registered, 2 conditional:** the 6 always-on (em_feld/kennlinien/luftspalt/festigkeit/temperatur/fahrzyklus) plus a dedicated **3D-Magnetfeld expert** (`em3d`, selector `_em3d_data`, `condition` = `results["em3d"]`) and a **Kühlungs expert** (`kuehlung`, selector `_kuehlung_data`, `condition` = `results["oilspray"]` — Spritzöl-Benetzungs-Proxys im LPTN-Kontext, scope-ehrlich: kein Wärmeübergang). Each expert may carry a `condition(results, meta)`; `run_expert_agents` runs only the experts whose condition holds (compare: if ANY variant satisfies it), so the em3d/kuehlung sections appear only when the run exists. The EM-Feld expert is now purely 2D-FDM (its 3D slice moved to the em3d expert). `_EXPERT_IMAGES` maps each expert→charts (em_feld: airgap/em_field/em_field_load; em3d: em3d_airgap_2d3d/em3d_endeffect/em3d_field3d/em3d_slice_mid/em3d_model_iso; kuehlung: oil_coverage/oil_wetting/oil_droplets — only rendered when the chart files exist) |
| `ema_training.py` | Fortlaufendes **LLM-Trainingsfile** (`~/cae_projekte/_training/dataset_sft.jsonl`, instruction/input/output JSONL). `run_pipeline` ruft nach dem Speichern `ema_training.upsert(project_id, meta, results)` auf (label=null) — **upsert per project_id** (kein Duplikat beim Nachrechnen). `instruction` = `ema_chat._machine_datasheet(meta)` (Geometrie+Material); für **KI-Entwürfe** stellt `build_instruction` die natürliche-Sprache-Aufgabe (`meta["design_brief"]`, durchgereicht aus dem `/analyse`-Payload) voran → echte „Beschreibung→Entwurf→Kennwerte"-SFT-Paare; jede Zeile trägt `design_source` ("ki"/"hand"). `output` = Kennwert-Text aus `results["summary"]`. **Einheitliches Schema:** jede Zeile trägt exakt `RECORD_KEYS` (project_id/timestamp/design_source/instruction/input/output/label/label_source/auto_label/auto_reasons/comment/rated_at/metrics/images); `_write_all` zieht beim Schreiben **jede** Zeile über `_normalize` auf dieses Schema (Altzeilen werden so beim nächsten Schreibvorgang migriert). **Vorsortierung:** `auto_label`/`auto_reasons` (Heuristik) werden **immer** mitgeschrieben; **KI-Entwürfe** (`design_source=="ki"`) werden direkt mit dem Heuristik-Label vorsortiert (`label_source="auto"`), Hand-Entwürfe bleiben `label=null`. `set_label(pid, "gut"/"schlecht", comment)` setzt das Label manuell (`label_source="user"`, vom Ergebnis-Tab) und bleibt beim Nachrechnen erhalten (überschreibt die Auto-Vorsortierung). `stats()` zählt zusätzlich `n_user_rated`/`n_auto_rated`/`n_ki`. **Bilder:** jede SFT-Zeile führt `images:[{key,title,path}]` mit (projekt-relative Pfade in `~/cae_projekte`, NICHT base64 — `IMAGE_PAIRS` spiegelt `ema_report.build_context` pairs, nur deterministische Charts, keine Animations-Frames). `export_vlm()` erzeugt zusätzlich `dataset_vlm.jsonl` (EIN Eintrag je Bild im messages/content-Format mit absolutem Bildpfad, fürs Vision-Finetuning) — wird nach jedem `upsert`/`set_label` mitgeführt. Endpoints `POST /training/vlm/export`, `GET /training/vlm/download` |
| `ema_projekt.py` (Projektakte) | **Eine KI-lesbare Quelle der Wahrheit pro Projekt** (`<projekt>/project.json`, `schema_version:1`). Wird in `create_project_dir` **zuerst** angelegt (`init`, neue kwargs `origin`/`parent`) und **laufend** fortgeschrieben: `run_pipeline` setzt zu Beginn `status="rechnet"` und ruft am Save-Block (`ema_pipeline.py:~2275`, direkt nach `ema_training.upsert`) `record_run(...)` → hängt eine **Evolutionsstufe** an (`{ts,action,changed_inputs,key_metrics,note,ref}`, Eingabe-Diff via flachem geom.*-Vergleich, Kennzahlen via `ema_training.build_metrics`) und aktualisiert `datasheet`/`metrics`/`assets`/`design`/`inputs.payload`/`status`. Action = `analyse`/`recompute:<stages>`/`design_ai`. Weitere Schreibpunkte: Rating (`status=bewertet`+Stufe), Report (`status=berichtet`+`assets.report`). **Referenzen statt base64** (Charts als rel. Pfade, gespiegelt aus `ema_training.IMAGE_PAIRS`). **Backward-Compat:** `load_or_synthesize(dir)` rekonstruiert die Akte für Altprojekte aus `meta.json`+`results.json` (kein Pflicht-Migrationslauf), optional Lazy-Write-Back. Jeder Schreibvorgang **soft-fail** (atomar `os.replace`), `load` nutzt `setdefault` je Schlüssel. Felder: `status`(neu/rechnet/gerechnet/bewertet/berichtet/verworfen)·`tags`·`notes`(Entscheidungs-Log)·`lineage{parent,origin}`·`design`·`datasheet`·`inputs.payload`·`metrics`·`assets`·`evolution[]`·`links[]`(persistente Vergleichs-Verknüpfungen, einweg+selbstheilend via `resolved_links`)·`rag.docs[]`·`attachments[]`. Konsumenten lesen dieselbe Quelle: `ema_report.build_context` zieht `evolution`/`links`/`notes` (deterministischer Abschnitt **„Projektverlauf & Verknüpfungen"** via `_evolution_links_md`, nach der Prosa angehängt), `ema_chat` erdet auf `notes` + (bei Altprojekten) das synthetisierte Payload. Server: `/project/<id>/manifest`·`/meta`(Status/Tags/Notizen)·`/links`(GET/POST)·`/links/remove`·`/clone`(ganzes Verzeichnis klonen, `lineage.parent`, RAG mitkopieren — KEINE schweren Ergebnisse)·`/bundle`(Export `.emaproj`-Zip)·`/import_bundle`(Zip-slip-sicher → neues Projekt, `origin=import`)·`/rag`+`/rag/add`+`/rag/<doc>/delete`(**Pro-Projekt-RAG** unter `<projekt>/rag/index.json`)·`/attachments`(Anhänge → automatisch in die Projekt-RAG). UI: Galerie-Badges (Status/Abstammung/⚖Links/⟳Stufen) + **📁 Klonen**/**⬇ Bundle**/**📦 Import**, Ergebnis-Tab-Panel **🗂 Projektakte** (Status/Tags/Notizen + Evolutions-Timeline + Verknüpfungen + Projekt-RAG/Anhänge). Test: `smoke_test.py` `[projektakte]`-Block (init/record/diff/links/synthesize/lineage + `ema_rag.store_dir`-Isolation, ohne Ollama/FreeCAD) |
| `ema_step_import.py` | **STEP-Import eines fertigen Motors**: liest per FreeCAD alle Solids (`extract_solids_script`), klassifiziert FreeCAD-frei (`classify_solids` über radiale Bänder + Volumen-Cluster + Rotationssymmetrie), leitet Maße/Polzahl ab (`derive_geom`, `_gap_cluster_count` für Pole/Nuten) + erkennt Magnete via OBB-Fit (`detect_magnets`, pol-lokale Halbpol-Magnete im Canvas-Format) und schreibt `motor.FCStd` mit benanntem `"Rotor"` (`assemble_fcstd_script`) → die bestehende Struktur-FEM rechnet darauf, EM auf den `customLegs`. `run_import` → applyDesignToCanvas-Form. Server: `/import_step`+`/import_step/status`; UI-Tab **📥 STEP-Import** → lädt in den Designer (Bestätigung), dann `/analyse` mit `imported:true` (run_pipeline überspringt den Geometrie-Build). Makro `step_import.FCMacro`. Tests: `test_step_import.py` |
| `ema_em3d.py` / `elmer_runner.py` | **Echte 3D-Magnetfeldberechnung (Elmer FEM)** — s. Architektur-Abschnitt. `build_mesh` (Gmsh-OCC), `write_sif` (Elmer-Magnetostatik), `parse_results` (vtk-VTU + 2D-Vergleich), `run_em3d` (Orchestrator, zerlegt in `_prep_mesh`/`_solve_point`/`_decorate_res`), `run_em3d_sweep` (Drehzahlband: Mesh einmal, Punkt-Raster), `run_em3d_refine` (ROI lokal feiner + voller Re-Solve, ROI-`Box`-Feld in `_build_mesh_once`), `run_em3d_sector` (Ein-Pol-Sektor, anti-periodisch, zum vollen Motor gespiegelt — `_build_sector_mesh`/`write_sector_sif`/`_pattern_full_motor`/`_sector_results`). `elmer_runner` = Subprozess-Wrapper (`ElmerGrid`/`ElmerSolver`, `ELMER_OK`). Server `/em3d`(+`/status`,`/vtu`,`/vtp`,`/streamlines`,`/paraview`) + `/em3d_sweep` + `/em3d/submodel` (Verfeinerung) + `/em3d/sector` (Ein-Pol-Symmetrie) + **`/em3d/abort`** + `/em3d/save\|saved\|saved/<id>\|saved/<id>/delete` (PROJEKT-gebundener Store `<projekt>/em3d_runs/` via `_em3d_runs_root`; alle Handler binden den Lauf über `_em3d_project_dir`), UI-Tab **🧲 3D-Feld** (gespeicherte Läufe + Bericht liegen auf Tab ① Projekt). **Lauf abbrechen (`/em3d/abort`, UI-Knopf „⛔ Abbrechen"):** setzt ein Abbruch-Flag (`server._em3d_abort`) UND killt den laufenden ElmerSolver (`elmer_runner.abort_current` → Popen `terminate`, `run_elmersolver` meldet `aborted`) → sofortiger Stopp statt bis zum `timeout`. Beim **Sweep** (`run_em3d_sweep(..., cancel_cb=)`) wird zwischen den Punkten geprüft und das **Teilergebnis behalten** (`out["aborted"]/["n_done"]`, Kurven aus den fertigen Punkten, persistiert; Detailfeld nur, wenn der Detailpunkt — zuletzt in der Reihenfolge — schon dran war). Status wird `aborted` (UI gibt den Start wieder frei, rendert das Teilergebnis, speicherbar). **Gespeicherten Lauf laden zeigte „kein Feld":** `_e3LoadRun` leert jetzt die Viewer-Caches (`_e3PlayStop` → `_e3PdCache`/`_e3LinesCache`, per Punkt-Index gecacht) + neutralisiert `_e3ViewIdx`/`_e3SweepPoints` VOR dem Rendern und öffnet den Viewer frisch — sonst zeigte `_e3GetPointPd` die (stale) VTP des vorherigen Laufs bzw. nichts. Tests `test_em3d.py` (Mesh/sif + Sweep + Feldlinien-Export ohne Elmer) + `test_em3d_submodel.py` (ROI-Verfeinerung) |
| `ema_oilspray.py` / `blender_runner.py` | **Experimentelle Spritzöl-Kühlung am Wickelkopf** (Blender/Mantaflow-FLIP) — s. Architektur-Abschnitt. `run_oilspray` (STL-Ausschnitt → Mantaflow-Bake → Benetzungs-/Tropfen-Kennwerte → Video/Charts, `_persist` nach results.json); `blender_runner` = Subprozess-Wrapper (bevorzugt portablen blender.org-Build; `BLENDER_OK`, `abort_current`). Server `/oilspray`(+`/status`,`/abort`), UI-Tab **💧 Spritzöl-Kühlung**. **Qualitativ — kein Wärmeübergang.** Braucht `blender` (portabel, Mantaflow-tauglich) + FreeCAD (STL). Test: `test_oilspray.py` (ohne Blender). Wickelkopf-STL via `ema_freecad.build_winding_head_stl_script` (`hairpin_slot_limit`) |
| `ema_cfd.py` / `openfoam_runner.py` | **Quantitative Spritzöl-Wickelkopfkühlung (OpenFOAM VOF / interFoam)** — On-Demand-Pfad NEBEN dem qualitativen Mantaflow-💧 (teilt den Wickelkopf-STL-Export `ema_oilspray._export_winding_stl`, `include_core=False`). `run_cfd` = `_prep_case` (STL → auf Meter skalieren via vtk → Domäne → `build_case_dicts` schreiben → blockMesh → surfaceFeatureExtract → snappyHexMesh) → `_solve` (interFoam) → `_parse` (foamToVTK → windinghead-Rand-VTP je Zeitschritt → **flächengewichtete Benetzung** `wetted_fraction` + **effektiver HTC** `htc_model`) → `_persist_cfd_summary` (schlank nach results.json["cfd"]). **`build_case_dicts(cfg)`** ist REIN (alle OpenFOAM-Dicts als Text) → ohne OpenFOAM testbar; **`meshQualityControls` inline** (kein `#includeEtc` — das zog den etc-FoamFile-Header in den Sub-Dict und brach snappy). Öl kommt als Curtain vom +Y-Rand (Ring-Seite, −Y-Geschwindigkeit aus `jet_velocity`=Cd·√(2Δp/ρ)), Schwerkraft −Y, Wickelkopf = no-slip-Wand (STL via snappy), Atmosphäre = Ablauf. **HTC-Modell (Stufe 1, dokumentiert):** interFoam ist ISOTHERM → `htc_model` = Prallstrahl-Nusselt `Nu=0.585·Re^0.5·Pr^0.4`, `h=Nu·k/L_char`, flächengemittelt mit der gerechneten Benetzung, geklemmt 100…8000 W/m²·K. **3D-Öloberfläche (Browser):** `_oil_isosurface` tract die VOF-Grenzfläche `alpha.oil=0.5` (aus `internal.vtu`, Skalar `Umag`), `_cfd_video` rendert sie je Zeitschritt offscreen (feste Kamera/|U|-Skala) → `frames_cfd/anim.mp4`, `export_browser_cfd` schreibt Öl-Isofläche + Wickelkopf als schlanke float32-.vtp (`_write_vtp`) → Route `/cfd/vtp?part=oil|solid`; UI `_renderCfd` zeigt `<video>` + vtk.js-Viewer `_cfdViewer`. `openfoam_runner` = Subprozess-Wrapper (sourct `etc/bashrc`; `OPENFOAM_OK`, `run_blockmesh/surface_features/snappy/solver/foamtovtk`, `abort_current` via SIGTERM wie `elmer_runner`). Server `/cfd`(+`/status`,`/abort`,`/vtp`), Job-Typ `cfd`, `/project/<id>/video/cfd`, UI-Tab **🌊 OpenFOAM (quant.)** (`_cfdBuildPayload`/`startCfd`/`_pollCfd`/`_renderCfd`/`_cfdViewer`/`queueCfd`, HTC prominent + Scope-Banner). **`_cfdBuildPayload` baut auf `_oilBuildPayload()` auf** → der 🌊-Tab **erbt die GESAMTEN 💧-Einstellungen** (Geometrie + Öl + Ring/Düsen/Ausschnitt/Druck); `payload.cfd` übernimmt daraus `pressure_bar`/`nozzle_d_mm`/`section_slots` und ergänzt NUR die OpenFOAM-spezifischen Felder (`end_time`/`n_cells`/`refine`/`viscosity`/`make_video`). Der Tab zeigt nur diese OpenFOAM-Parameter + eine Live-Zusammenfassung der übernommenen 💧-Werte (`_cfdSyncInherited`, an `switchTab('cfd')`) + Knopf „💧 Spritzöl-Einstellungen öffnen". Jobs (`queueCfd`→⏳ Jobs, Ergebnis-Knopf `openJobCfd`) und Ergebnisse (`_renderCfd`) laufen im Tab. **HTC-Kopplung:** `ema_pipeline` liest bei `cooling=="oil"` results.json["cfd"]["htc_eff"] + wetted_area und gibt sie an `ema_thermal.run_thermal_analysis(htc_oil=…, wetted_area_m2=…)` → `conductances` ergänzt einen direkten Wicklung→Kühlmittel-Pfad `G_w_cool=htc·A_wh` (opt-in; htc_oil=0 ⇒ bit-identisch zum Preset); `results["summary"]["htc_source"]`="cfd"/"preset". Bericht: `_ensure_kuehlung_section` + `_single_md_tables` + Kühlungs-Experte ziehen `results["cfd"]`. **v1-Scope:** VOF/isotherm; CHT (`chtMultiRegionFoam`, konjugierter HTC) wäre die Folgestufe. Test: `test_cfd.py` (Case-Dicts + jet/HTC + Benetzung + Thermik-Kopplung, ohne OpenFOAM) |
| `ema_spraytest.py` | **🧪 Spray-Test-Prüfstand** — iteratives Spray-Tuning (Mensch wählt, Evolution mutiert). Vereinfachter Blender/Mantaflow-Prüfstand OHNE FreeCAD/Motor: EINE Düse sprüht **horizontal** (+x, Schwerkraft −z) als **Freistrahl — Standard zeigt NUR das Spray** (Kamera-Nahaufnahme auf Mündung+Strahl); die 3 Kupferstäbe (Aufprallziele, weitere Übersichts-Kamera) sind per `spec["show_rods"]`/UI-Häkchen `#st_rods` zuschaltbar (in round.json persistiert, `run_beauty` erbt es aus der Runde). Pro Runde n (Default 10) Varianten der 5 Spray-Physik-Parameter (`SPRAY_PARAMS`: pressure_bar/jet_cone_deg/surface_tension(log)/viscosity(log)/nozzle_d_mm) als kurze Loop-Videos. **Anlagen-Grenzen (Nutzer-Vorgabe: Druck 0,1–3 bar; Düsen-Ø 0,5–3,0 mm ab 2026-07-28)** — in `SPRAY_PARAMS`, den UI-min/max (🧪 `st_e_p`/`st_e_noz` + 💧 `oil_pressure`/`oil_nozzle_d`) UND den `ema_oilspray`-Klemmen; `stAdopt` klemmt übernommene Alt-Werte auf die Feldgrenzen. `sample_round`: Runde 1 = Latin-Hypercube-Streuung + Default-Anker; Runde ≥2 = Kreuzung zweier markierter Eltern + Gauß-Mutation im normierten Raum (σ=0.25·0.7^(r−2), Dedup). Eltern werden NICHT neu gebacken (Video-Referenz auf die Altrunde, `video_path` löst rekursiv auf). `run_round` bäckt Kinder **sequenziell** (blender_runner kann nur einen Prozess) in je eigene Verzeichnisse, Abbruch zwischen Varianten behält die Teilrunde. Store global `~/cae_projekte/_spraytest/rounds/<rid>/` (projektunabhängig; `list_rounds` sortiert nach **Zeitstempel**, nicht rid — sonst läge eine neue Runde 1 hinter einer alten Runde 2). Sim-Settings je Runde: **EIN Auflösungsfeld** `spec["resolution"]` 32–512 (`RES_RANGE`, UI `#st_res` + Preset-Knöpfe 48/64/96/160/320/500; das alte `quality`-Preset bleibt als Fallback für Alt-Runden; Bake-Timeout skaliert quadratisch mit), **Frames** (24–120) + **Zeitlupe** (`slowmo` 1–50 ⇒ time_scale=1/slowmo) je Runde einstellbar. **💾 Spray-Favoriten** (`favorites.json` im Store, `save_favorite`/`list_favorites`/`delete_favorite`, Server `GET/POST /spraytest/favorites` + `/spraytest/favorites/<fid>/delete`): guter Strahl wird benannt gespeichert ({name, params, sim, src}) — Karte „💾 Gespeicherte Sprays" im 🧪-Tab + **Dropdown `#oil_fav_sel` im 💧-Tab** (`stApplyFavorite`/`oilApplyFavorite` schreibt Druck/Kegel/σ/ν/Düsen-Ø in die Öl-Felder). **Realismus-Paket im Bench-Skript** (gegen „unrealistische Tropfen"): die Einzeltropfen kommen aus dem **feinen Upres-Flüssigkeitsmesh** — `mesh_particle_radius` 1.4 (Default 2.0 = dicke Blobs), **Upres `mesh_scale=2` NUR bei RES<192** (bei hoher Auflösung ⇒ 1024³-Mesh-Gitter ⇒ ~29 GB RSS ⇒ Kernel-OOM-Kill, real passiert bei 512; ohne Upres braucht 512 nur ~3 GB), Generator IMPROVED, `use_fractions` (glatte Stab-Kollision), Substeps skalieren mit RES. `blender_runner` meldet einen Signal-Kill (OOM ⇒ SIGKILL) jetzt als RAM-Fehler statt fälschlich als „abgebrochen" (nur `_ABORTED` zählt als Nutzer-Abbruch); ein OOM-Ausfall bricht damit auch die Runde nicht mehr ab, sondern nur die eine Variante. **`n=1` + `spec["exact_params"]`** = 🎯 Einzel-Strahl (exakt diese 5 Parameter, eine Kachel; UI-Karte „🎯 Einzelnen Strahl backen" mit „↙ Werte aus 💧-Tab holen", `stStartSingle`/`stSingleFromOil`). **Gotcha (ausgiebig verifiziert, NICHT wieder aktivieren):** die Mantaflow-**Sekundärpartikel** (Spray/Foam/Bubble) sind in diesem Blender-4.2-Build **kaputt** — ohne `cache_resumable` werden NULL Partikel erzeugt (leere particles-Cache-Dateien), MIT resumable laden sie als **domänenfüllender Positions-Müll** (Staub über den ganzen Quader statt an der Flüssigkeit); die `use_*_particles`-Flags stehen deshalb bewusst auf False. `run_beauty(rid,vid,opts)` = **✨ Schönheits-Render** EINER Variante (Default 256er-Domain, 60 Frames, 1280×960) nach `<rid>/<vid>/beauty/`; `video_path(rid,vid,beauty=True)` löst auch Eltern-Referenzen rekursiv auf. Server `_spraytest_state` + `POST /spraytest`, `POST /spraytest/beauty`, `/spraytest/status\|abort\|rounds\|round/<rid>(/marked\|/delete)\|video/<rid>/<vid>(?beauty=1)` (teilt sich die Blender-Sequenzialität mit `/oilspray` → 409 wenn einer läuft). UI-Tab **🧪 Spray-Test** (`panel-spraytest`, `st*`-JS): Kachel-Raster mit ⭐-Markierung (persistiert), Tropfen-**Sparkline** je Kachel (`_stSparkline`, Serie `n_islands` aus round.json), **Klick aufs Video = Großansicht-Modal** (`stOpenBig`: ⭐/✔/✨ + Original↔Beauty-Umschalter), „✨ Schön rendern" je Kachel (`stBeauty`), „➡ Nächste Runde aus Markierten", „✔ Übernehmen" schreibt die Parameter in die 💧-Öl-Felder (`oil_pressure/oil_jet_cone/oil_surft/oil_visc/oil_nozzle_d`). Test: `test_spraytest.py` (ohne Blender) |
| `em3d_perf_check.py` | **Performance-Check der 3D-Elmer-Berechnung** (Standalone-CLI): fährt die Netzfeinheit stufenweise hoch (Zellgrößen-Skalierung) und misst je Stufe **Knotenzahl, Zeit (Mesh/ElmerGrid/Solve) + Peak-RAM** (via `/usr/bin/time -v`), schreibt `em3d_perf.csv`/`.json` inkrementell. `--calibrate` (nur meshen), `--max-nodes`/`--timeout`/`--ram-stop`/`--factors`. Datengrundlage für `EM3D_NODE_CEILING` + die RAM/Zeit-Schätzung des Ziel-Knoten-Reglers |

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
