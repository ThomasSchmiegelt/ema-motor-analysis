# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Monorepo for a connected E-machine (electric motor) CAE toolchain: three independent
subprojects that talk to each other over local HTTP services (`localhost`), run under
a restricted user **`cae`** (no sudo). It was assembled from previously separate repos
(see root `README.md` — English; `README.de.md` — German — for the full picture) — each subproject still has its own
history, conventions, and often its own `CLAUDE.md` / docs. **Read the subproject's own
docs before working in it** — this file only covers cross-cutting/root context; it does
not restate subproject detail.

| Folder | What | Stack | Start |
|---|---|---|---|
| `cae_orchestrator/` | Browser CAE for IPM motors: geometry → EM field → structural FEM → thermal → drive-cycle, PDF report | Python/Flask + FreeCAD/CalculiX/Elmer/OpenFOAM/Blender | `cd cae_orchestrator && ./start.sh` → http://localhost:5000 |
| `connection_detection/` | FreeCAD workbench: geometric connection detection in STEP assemblies (basis for multi-body CalculiX) | Python FreeCAD addon (`rtree`) | `FreeCADCmd cli.py -- input.step -o out.json` |
| `pikogk/` | PicoGK geometry kernel + HTTP API (voxel/implicit geometry, LLM-driven "skill" generation; domain = combustion cylinder heads) | .NET 9 + native `picogk.so` | `cd pikogk && ./start.sh` → http://localhost:5266 |
| `physics_surrogate/` | ML surrogate for the 2D-FDM field stage (PhysicsNeMo/Torch). **Stalled mid-stage-1**: 17 GB dataset + 4 trained checkpoints, best `rmse_Br_rel_peak` 0.054 against a 0.03 gate; `/predict/*` returns a hardcoded 503 and there is no inference client | Python + Torch/CUDA | `cd physics_surrogate && ./start.sh` → http://localhost:5300 |
| `lego/` | LLM-generated functional LEGO Technic mechanisms, scored against ORCA hand kinematics | Python + BrickNet | — (CLI) |

Each subproject has **its own CLAUDE.md or docs** — read those before working there:
- `cae_orchestrator/CLAUDE.md` — extremely detailed (pipeline stages, endpoints, magnet
  topology system, 3D EM field solver, canvas designer, etc.). Consult it rather than
  re-deriving architecture from source.
- `pikogk/EXPERIENCE_REPORT.md` — how the Linux port was built (native build steps,
  workarounds for the officially-Windows/macOS-only PicoGK).
- `pikogk/INTEGRATION.md` — HTTP contract for calling the PicoGK web API from another
  program.

## Agent layer (root-level, spans the whole repo)

Besides the browser UI, the toolchain is drivable by a **local** LLM through
[PI](https://pi.dev) (`@earendil-works/pi-coding-agent`) + Ollama. This lives at the root
because it is not part of any one subproject:

| Path | What |
|---|---|
| `start_agent.sh` | one command: checks Ollama, pins the model **by ID** (a `ollama pull` under the same name silently swaps the weights), starts the orchestrator only if `:5000` is silent, waits for it, then `exec pi`. Session handling: `--weiter` / `--sitzung <id>` / `--sitzungen`; a bare known session id and a lone `--` are accepted too, PI's own session flags pass through untouched |
| `.agents/README.md` | setup + what the agent sees; PI binds tools as **Skill = CLI + README**, deliberately not MCP |
| `.agents/skills/cae-orchestrator/SKILL.md` | the skill the model reads — the authority on how `cae_cli.py` is meant to be used |
| `cae_orchestrator/cae_cli.py` | the CLI itself, thirty-one verbs: nine over HTTP on `:5000` (`status/health/geom/run/wait/results/projects/raw/routes`), twenty-two local (**`getriebe`** — gear design (`ema_getriebe.py`): ratio split, tooth counts, module, load capacity, load-dependent efficiency, mass and the inertia referred to the motor shaft. The gearbox used to be two constants (`gear_ratio: 9.5`, `eta_drive: 0.95`) — a bicycle hub motor and a traction drive got the same ones. Tooth-form and notch factors are computed from the geometry (30° tangent, ISO 6336-3), not looked up: a table holds only for x = 0, and the sizing picks a profile shift as soon as z drops below 17. It also decides **where** the gearbox sits, and `in_welle` — a planetary set inside the rotor's hollow shaft — is a gate, not a label: it puts the needed bore, the drawn bore and the **magnetically permissible** bore (from `ema_welle.pruefen`, a real field run) side by side and names the one that binds, **`studie`** — sweep ONE parameter x→y and record every metric (`ema_paramstudy.run_study`), and **`zielwert`** — the target-value optimisation (`ema_optimize.optimize`); both existed only as browser buttons, and a button the agent cannot see does not exist for it. One verb serves all three heads — they read the same `SKILL.md`. `zielwert` is also the clean answer to "reach this target": there the model only proposes **parameter vectors**, clamped and ranked deterministically, instead of hand-searching with `run --set`; and when no feasible design exists it says so **naming the binding constraint** rather than declaring the least-bad candidate a winner, **`feld2d`** — the induction machine's field stage, harmonic in Elmer 2-D (`ema_em2d_harm`), because the house FDM is real, linear and magnetostatic and a cage rotor is not representable in it at all; it saturates the rotor bridge by measurement, measures the Carter factor the *drawn* slot actually has (2,27 against the 1,15 `ema_asm` assumes) and samples the torque-slip curve, **`feld3d`** — the counter-calculation in Elmer 3-D (`ema_em3d_harm`) for the one quantity a cross-section cannot give at all, the **short-circuit ring**: the 3-D mesh is built as axial **slabs of one meshed cross-section**, so radial resolution costs triangles instead of tetrahedra — the 0,7 mm airgap now has two element layers at 59.796 nodes where the old free tet mesh had exactly one at 166.614 elements. The model is validated against `feld2d` at the two points where the ring plays no part (no cage current 0,3 %, ideally shorted cage 0,14 %); the ring figure itself is a **lower bound** (63–78 % of the bar loss depending on mesh, every refinement pushes it up, no convergence in reach on this machine), which still refutes the flat 20 % `ema_asm` assumed by at least a factor three. `ema_asm.kurzschlussring_zuschlag` derives the surcharge from geometry instead. Not for an absolute torque: the 0,7 mm airgap is not resolvable in an affordable 3-D mesh, and `--nur-netz` says what a run will cost before it is started, **`welle`** — solid or hollow shaft, *measured*: one FDM solve, the radial |B| profile in the rotor, and from it the largest radius with no flux anywhere, hence the largest permissible bore (a bore saves mass and inertia and is only wrong when it sits in the magnetic path; the finding is magnetic and says so — strength is `struktur`/`sicherheit`), **`steckbrief`** — what a project *is* and what has been computed on it (machine type, poles/slots, envelope, materials, which stages ran, the key figures **each carrying its provenance**, what is still open); it computes nothing and prints what is missing as missing, and `--laeufe` also lists that project's past agent runs and stored calculations, `paarvergleich`, `rotor-check`, `screen`, `bilddaten`, `struktur`, `topopt`, `db`, `lernen`, `recherche`, **`feldbild`** — magnetic field-line images into the project's `charts/` (see-through, cut-open, one pole, axial section) from ONE FDM solve, so "show me the field" costs seconds instead of a pipeline run, **`maschinenart`** — which machine types exist (PSM/ASM/SynRM/EESM) and how far each is actually carried, **`aufgabe`** — break a new task into what must be settled / what the local stock already answers / what is genuinely open (the step BEFORE researching), **`zyklus`** — pick/build/keep drive cycles, **`sicherheit`** — check a finished run against the safety limits, **`beitrag`** — Instagram/X post drafts built from what was *computed* (`ema_beitrag.py`): the facts come from the Steckbrief, every figure in the draft is checked back against that material, and nothing is ever published — the draft is filed under `<project>/beitraege/` and copied by hand). **The verbs that decide a design — `paarvergleich`, `screen`, `rotor-check`, `sicherheit`, `feldbild` — now persist their result** to `<projekt>/rechnungen/<time>_<verb>.txt` plus one line in `project.json`'s `evolution`, whenever a project is bound (`--from-project`/`--projekt`; `--ohne-ablage` opts out). Before, only `feldbild` wrote anything: the reasoning behind a design did not outlive the design |
| `start_hermes.sh` | **second agent head**: Hermes Agent (Nous Research), same Ollama model, same skill. `hermes skills trust <repo>` loads `./.agents/skills/` — the very directory PI uses, so nothing is copied or symlinked and the two cannot drift. At a TTY it opens a **project matrix** first — one of the eight newest projects, **`n` to create a fresh one**, or `g` for the shared store — and only then the session menu — PI just takes the newest project, because PI's memory is not per-project while Hermes's is: landing in the wrong project serves another design's lessons as fact. `n` calls the same `ema_pipeline.create_project_dir(origin="manual")` the server uses behind `POST /project/new`, so the Projektakte (`project.json`, status/lineage/evolution) exists from the start; a bare `mkdir` would leave exactly the agent-created projects without one. The matrix also appears when the store is **empty** (offering only `n`/`g`) — it used to bail out there, so on a first run there was neither a project to pick nor a way to make one. Its `--nur-pruefen` **measures** (via `ss -tnp`) that Hermes only talks to `127.0.0.1:11434`: the shipped default points at OpenRouter, and two open upstream bugs (#57255, #14676) make `provider: ollama` fall through to it silently |
| `cae_orchestrator/ema_agent.py` (routes `/agent…`) | **both heads in the browser**, as tabs 🤖 PI and 🪽 Hermes on `:5000` — one page and one set of routes, told apart only by `?kopf=`; PI speaks `pi --mode rpc`, Hermes speaks `hermes acp` (ACP/JSON-RPC). Hermes' `HERMES_HOME` hangs on the project there too, so the browser makes the project choice mandatory for it — the counterpart to `start_hermes.sh`'s project matrix. Detail in `cae_orchestrator/CLAUDE.md` |
| `cae_orchestrator/ema_studio.html` + `agent_gemein.js` (routes `/studio…`) | **a third head, and the one page that is meant to leave the desk.** Same agent routes, same event stream — but one column, everything under everything else in the order it happened, sized for a thumb. The two-column page is built for the desk and the screen recording; on a phone its drag handle and fixed panes are unusable, the same finding that produced `ema_mobil.py`. What the two pages share is **behaviour, not layout**: `agent_gemein.js` holds the stream, the clock, the follow-scrolling, the archive replay and the whole screen recorder, and calls back into each page for drawing. `StudioKopf` is its own `pi` process next to a computing PI (one line in `KOEPFE`), with its own standing order — *write about what was computed, do not compute* — because the design brief the other heads get would send it off to run drive cycles while somebody waits on a phone. It is also the only agent page deliberately reachable over the LAN, so it — and only it — carries the mobile path's token (`/studio`, `/agent/…?kopf=studio`; `pi` and `hermes` stay as open as the rest of the server). Its second job is `beitrag`: Instagram and X drafts out of the Steckbrief, with every figure checked back against the material and nothing ever published. Its bottom bar is two rows, not four: the storage path moved to the save button's `title` (and, on a manual save, into the transcript where it belongs chronologically), which freed the width for the icons, and the work display is now the desk page's **lamp row** — agent, computation, research, solver, GPU, model, rate, and 🔧 tool — so you can see who is doing what |
| draft first, exact later (`--guete`) | The knobs for computational quality (FDM resolution, mesh size, frame count) live in **no** schema, so `--set fdm_resolution=300` was rejected and an agent could not choose them at all — every trial ran at full detail, hours instead of minutes. The browser had the table (`CALC_PRESETS`) since forever; now `ema_text2ema.GUETE` is the single source, `run --guete entwurf|detail` applies it, and `test_steckbrief.py` nails the JS copy against the Python table the way `test_topology.py` does for topologies. Draft is honest because it is measured: `B_gap` and `Kt` come from the analytical formula and do **not** depend on resolution — a draft run loses no key figure, only image sharpness; and no preset goes below N=300, where the measured air-gap waveform starts to be off by half. The **number of draft loops** is set by the human in the start mask and reaches the agent as a standing instruction — without it agents fell into one of two extremes: a single multi-hour detail run that decides nothing, or endless fiddling |
| designer → agent, and the project brief | Geometry roughed out in the canvas designer can be handed to PI/Hermes as a **starting point** without a pipeline run (`POST /agent/vorgabe`, buttons in the designer tab): the payload — topped up from the `--frisch` schema defaults, so the agent does not inherit half a payload — is written as `meta.json`, which is exactly where `cae_cli.py --from-project` and the Steckbrief already look, so no new tool is needed. It is marked `design.vorgabe`, and that flag **inverts** the standing system prompt: a bound project is normally "expressly NOT a template" (the case `--frisch` was built against), but a deliberate hand-over is the opposite — *start here, change what you must, and say what you changed and why*. The description typed when a project is created now goes to `design.brief` as well as `notes`, so it reaches the agent through the Steckbrief and the system prompt instead of being typed a second time; a designer hand-over **appends** to it rather than replacing it. Binding an agent to a project that does not exist is now refused instead of silently creating a stray `<typo>/agent` folder |
| agent runs, kept and retrievable | `sichern()` wrote a `protokoll_*.md` + `ereignisse_*.jsonl` into `<projekt>/agent/` after **every** turn — and nothing ever read them back: no route, no verb, no button. From the seat in front of it, "written but unreachable" is the same as "not saved", and that is how it was reported. `GET /agent/laeufe` lists every run (project-bound **and** the unbound ones under `_agent_laeufe`, both heads together, newest first, each with the prompts that were given); `GET /agent/lauf?projekt=&marke=` returns one, capped at `RINGGROESSE` events — one measured transcript is 9,4 MB with 140.872 events, and the overview therefore never fully parses a transcript. The page replays it through **the same** render functions as the live stream (a second set would drift from the first) |

**The fast evaluator only recently learned to read a drawing**
(`ema_optimize._eval_geom` → `ema_analysis._analytical_Bgap`). For a *drawn*
geometry (`magShape:"custom"`) it used to compute the air-gap field from the
**parametric** `magWidth`/`magThick` — so magnet length, thickness and tilt moved
nothing and only the magnet *count* moved anything, linearly. Everything built on
it inherited that: the per-magnet fine optimiser had a constant objective, and the
AI-design pre-sort and its training labels rested on a number that did not know
its own drawing. It now sums per leg, `Σ perm(h_i)·(len_i/pole_pitch)·|sin(tilt_i)|`,
which reproduces the parametric formula exactly for identical legs. Measured
before/after and written up in `cae_orchestrator/BEFUNDE.md`; the same entry
records why `T_maxwell` was always 0.0 (the tangential air-gap fit falls back to
zero below a 2.5-pixel air band — true at every resolution this chain uses) and
now reports `None` with a reason instead.

**The tool is the yardstick, not the object** (`cae_orchestrator/ema_werkzeugstand.py`).
The heads are coding agents with write access to this repo, and the browser path asks for
no permission — so in a target-value search the shortest route to the number is to edit
`ema_asm.py`, and that is the one route that makes the number wrong without anyone
seeing it. Under the same user, without a sandbox, that cannot be *prevented*; it can be
made impossible to *hide*. A fingerprint over the twelve modules whose change moves a
figure rides along with every stored calculation, every `evolution` entry and the
Steckbrief (which says so out loud when the figures come from more than one state), and
a change **during** a run shows up in the work bar and in that run's `protokoll_*.md`
while somebody is watching. Alongside it, the rule in plain words in `AGENTS.md`,
`SKILL.md` and every head's standing order: a goal is reached through geometry and
operating point, never by moving a limit in the source; if it is not reachable, *"not
reachable, because …" is the right and complete answer* — a reasoned no is a result, not
a failure; and a tool you believe to be wrong gets a finding in
`cae_orchestrator/BEFUNDE.md`, not a silent repair mid-run. The target-value search
itself (`ema_optimize.py`) needs none of this: there the model only proposes parameter
vectors, clamped and ranked deterministically, and the source is out of its reach.

Two things that are easy to get wrong when touching this:

- **PI sorts sessions by cwd**, so `start_agent.sh` always `exec`s from the repo root —
  otherwise `--continue` would reach into another directory's sessions, and PI would find
  neither `AGENTS.md` nor `.agents/skills/`.
- **The model and its context length come from `ema_report`** (`DEFAULT_MODEL`,
  `DEFAULT_NUM_CTX`), not from `start_agent.sh`. The script only pins which model PI
  itself talks to; both default to `qwen-gross:latest` / 65536 and are overridable via
  `CAE_LLM_MODEL` / `CAE_LLM_NUM_CTX`.

## How the pieces interact

**Read this before believing any "toolchain" wording elsewhere.** End to end there is
**one** carrying product (`cae_orchestrator`) plus four independent satellites. Measured,
not assumed:

- **`cae_orchestrator` → Ollama (11434): real.** Report, chat, AI design, optimiser,
  RAG embeddings. Without it all physics still works; only the LLM routes 503.
- **`cae_orchestrator` → `physics_surrogate` (5300): read-only.** `ema_ki_training.py`
  polls `/health` and plots `history.csv` for the 🧠 tab. There is **no** inference path:
  `service/app.py` returns a hardcoded 503 on `/predict/*`, and the `ema_surrogate.py`
  client its own README advertises does not exist. The real coupling runs the other way —
  `gen_fdm_dataset.py` imports the orchestrator's genuine `_rasterise` via `PYTHONPATH`.
- **`cae_orchestrator` ↔ `pikogk` (5266): does not exist.** Grepping the orchestrator for
  `5266`/`pikogk` returns nothing. `pikogk/INTEGRATION.md` documents the HTTP contract in
  anticipation of a link that was never built; the domains are disjoint anyway.
- **`connection_detection`: standalone, and its output is currently a dead end.** It
  produces a `ConnectionGraph` JSON carrying `tie`/`contact` labels for multi-body
  CalculiX, but no `.inp` writer consumes it anywhere in this repo. It shares the FreeCAD
  toolchain with `cae_orchestrator` and nothing else.
- **`lego`: standalone.** No service, no port, no dependency on any sibling.
- Nothing in this repo talks to the network beyond `localhost` — no auth/TLS anywhere,
  intentionally (local PoC scope).

## Shared toolchain (system-wide, outside this repo — do not try to vendor/rebuild it)

- FreeCAD 1.1.x built from source under `~/freecad_1.1_quellcode` (via pixi) + CalculiX
  (`ccx` 2.23) in the same pixi env. **`/opt/freecad-1.1` is actually 1.2 with a
  visualisation bug — never use it.** `ccx` is also called directly, without FreeCAD.
- **Z88Aurora V5** under `/opt/z88aurora` (2,8 GB, owned by `thomas`, world-readable).
  Only the batch solvers are used (`z88r -c -parao|-siccg|…`). Two traps: `z88r` needs
  `LD_LIBRARY_PATH=/opt/z88aurora/bin/ubuntu64` because its own MKL is not in the
  RPATH, and it needs **two** runs — `-t` writes `Z88R.DYN`, which `-c` then reads.
  **Z88Arion has no Linux build** (Windows only, GUI only, no batch mode).
- Gmsh — the one actually used is the **Python module in the orchestrator venv** (4.15.2, from `requirements.txt`). `/usr/bin/gmsh` (4.12.1) sits alongside and is not needed.
- Portable Blender under `~/blender_portable`.
- OpenFOAM v2406 (`/usr/lib/openfoam`), Elmer, CUDA, pandoc/pdflatex — installed system-wide.
- Ollama at `localhost:11434`.

## Runtime data (never versioned)

- `cae_orchestrator` writes projects to `~/cae_projekte`.
- `pikogk` writes generated geometry to `pikogk/PicoGKWebApi/data/` and
  `pikogk/PicoGKWebApi/output/` (gitignored).
- `pikogk/PicoGKRuntime/Dist/picogk.so` (+ vendored `c-blosc`) is a native build
  artifact, gitignored — a fresh clone must rebuild it from source (see
  `pikogk/EXPERIENCE_REPORT.md`).
- `pikogk/PicoGK/`, `PicoGKRuntime/`, `PicoGKWebApi/`, `PicoGK_Examples/`, `c-blosc/`
  are **separate git repos** (upstream Leap71 code + a local fork), deliberately not
  embedded as submodules — they keep their own `.git` history on disk and are excluded
  via root `.gitignore`, not tracked as gitlinks.

## Subproject quick reference

### `cae_orchestrator/` (Python/Flask)
```bash
./install.sh   # one-time: checks deps, builds venv
./start.sh     # venv + prerequisite checks, runs server on :5000
python smoke_test.py         # fast (~15s) sanity check — run after any backend change
python smoke_test.py --cad   # + one real FreeCAD build + rotor FEM (minutes)
python test_topology.py      # magnet geometry + JS<->Python topology mirror
python test_X.py             # per-subsystem tests (test_em3d.py, test_step_import.py, ...)
```
No linters/CI configured. Full architecture (request/state flow, the ~470-line
pipeline in `ema_pipeline.py`, magnet topology system, 3D Elmer EM field, canvas
designer, AI design generation) is documented in `cae_orchestrator/CLAUDE.md` — that
file is the authority, not this one.

**Second structural path (`ema_deck.py` / `ema_z88.py` / `ema_topopt.py`).** Besides
the FreeCAD route there is an own deck: Gmsh (Python API) meshes one pole sector — or
the full rotor — from the same `ema_topology.magnet_legs` the 2-D FDM uses, and the
CalculiX input file is written here rather than by FreeCAD. It exists because
topology optimisation needs a **per-element Young's modulus**, which FreeCAD's writer
cannot emit, and because 13.669 elements meshed in 0,4 s beat 797.275 elements plus a
40 s FreeCAD start. **Z88Aurora V5** (`/opt/z88aurora`, batch solvers only) runs the
same mesh as an independent second opinion — measured agreement 0,00–0,05 %.
Selected via `struct_solver` (`freecad` | `ccx` | `z88` | `beide`); `freecad` remains
the default and is the only one that feeds the deformation images and ramp video.
Three things that are easy to get wrong there are documented in the module headers:
Z88 has **no centrifugal load** (its `OMEGA` is the SOR relaxation factor), its
material file is **space-separated** (a comma silently yields nu=0), and
`gmsh.initialize()` needs `interruptible=False` or it fails inside a Flask worker.

### `connection_detection/` (Python, FreeCAD addon)
Pure-geometry pipeline (`pipeline.py`): broad phase (bbox + `rtree`) → fine phase
(pairwise geometric evaluation) → `ConnectionGraph` export. Single entry point shared
by two front ends so they can't drift: `cli.py` (batch, via `FreeCADCmd`) and
`connection_detection_gui/` (interactive FreeCAD workbench command,
`InitGui.py`/`Init.py` register it). Needs FreeCAD's Python (`Import`/`Part` modules),
so run through `FreeCADCmd`, not plain `python3`:
```bash
FreeCADCmd cli.py -- input.step -o candidates.json
```
Tests that are pure geometry (no FreeCAD) run under plain Python/pytest:
```bash
python -m pytest tests/test_broad_phase.py
```
Layout: `detection/` (broad/fine phase, surface classification, penetration),
`model/` (`Part`, `ConnectionGraph`, candidate), `io/` (STEP reading), `graph_export/`
(JSON schema + FEM-mapping export).

### `pikogk/` (.NET 9, native C++ core)
```bash
cd pikogk && ./start.sh   # kills stale instances on :5266, starts, opens browser
```
`start.sh` requires `~/.dotnet` (.NET 9 SDK) and a built `PicoGKRuntime/Dist/picogk.so`
— see `EXPERIENCE_REPORT.md` if either is missing. PicoGK allows only **one** global
`Library` instance per process and always opens a native GLFW/OpenGL viewer window
internally (`DISPLAY` must be set, default `:1`), even when driven purely via HTTP.

**Architecture:** `Library.Go()` blocks its thread for the process lifetime, so it runs
on a dedicated background thread; actual geometry generation happens in a worker loop
that pulls jobs off a `BlockingCollection` — HTTP handlers in `PicoGKWebApi/` (`POST
/generate-shape`, `POST /interpret`) only enqueue and await a `TaskCompletionSource`,
never call into PicoGK directly. All requests are processed **serially** by the one
worker (a PicoGK/GLFW constraint, not a choice) — batch callers should plan for that.
See `INTEGRATION.md` for the full HTTP contract (endpoints, error codes, no
auth/TLS by design).

**Skill system** (`PicoGKWebApi/EngineHead/`, `SkillCreationOrchestrator.cs`): LLM
(Ollama)-driven generation of new parametric geometry "skills". Flow: generate C# code
→ `SkillCodeValidator` static check (rejects disallowed calls) → run in
`SkillSandbox/` (Docker container, Xvfb + software GL, compiles + executes untouched
from the host) via `SkillSandboxRunner`. Up to 3 attempts, feeding sandbox/validator
errors back to the LLM; never trusts anything from the sandbox beyond its report.
Domain-specific skills (cylinder-head components: `Kanal`, `Ventilstern`, `Brennraum`,
`Wasserkern`, etc.) live under `EngineHead/Skills/`; the top-level `pikogk/Skills` is a
symlink into that same directory.
