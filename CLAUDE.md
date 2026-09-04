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
| `cae_orchestrator/cae_cli.py` | the CLI itself, twenty-three verbs: nine over HTTP on `:5000` (`status/health/geom/run/wait/results/projects/raw/routes`), fourteen local (`paarvergleich`, `rotor-check`, `screen`, `bilddaten`, `struktur`, `topopt`, `db`, `lernen`, `recherche`, **`feldbild`** — magnetic field-line images into the project's `charts/` (see-through, cut-open, one pole, axial section) from ONE FDM solve, so "show me the field" costs seconds instead of a pipeline run, **`maschinenart`** — which machine types exist (PSM/ASM/SynRM/EESM) and how far each is actually carried, **`aufgabe`** — break a new task into what must be settled / what the local stock already answers / what is genuinely open (the step BEFORE researching), **`zyklus`** — pick/build/keep drive cycles, **`sicherheit`** — check a finished run against the safety limits) |
| `start_hermes.sh` | **second agent head**: Hermes Agent (Nous Research), same Ollama model, same skill. `hermes skills trust <repo>` loads `./.agents/skills/` — the very directory PI uses, so nothing is copied or symlinked and the two cannot drift. At a TTY it opens a **project matrix** first — one of the eight newest projects, **`n` to create a fresh one**, or `g` for the shared store — and only then the session menu — PI just takes the newest project, because PI's memory is not per-project while Hermes's is: landing in the wrong project serves another design's lessons as fact. `n` calls the same `ema_pipeline.create_project_dir(origin="manual")` the server uses behind `POST /project/new`, so the Projektakte (`project.json`, status/lineage/evolution) exists from the start; a bare `mkdir` would leave exactly the agent-created projects without one. The matrix also appears when the store is **empty** (offering only `n`/`g`) — it used to bail out there, so on a first run there was neither a project to pick nor a way to make one. Its `--nur-pruefen` **measures** (via `ss -tnp`) that Hermes only talks to `127.0.0.1:11434`: the shipped default points at OpenRouter, and two open upstream bugs (#57255, #14676) make `provider: ollama` fall through to it silently |
| `cae_orchestrator/ema_agent.py` (routes `/agent…`) | **both heads in the browser**, as tabs 🤖 PI and 🪽 Hermes on `:5000` — one page and one set of routes, told apart only by `?kopf=`; PI speaks `pi --mode rpc`, Hermes speaks `hermes acp` (ACP/JSON-RPC). Hermes' `HERMES_HOME` hangs on the project there too, so the browser makes the project choice mandatory for it — the counterpart to `start_hermes.sh`'s project matrix. Detail in `cae_orchestrator/CLAUDE.md` |

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
