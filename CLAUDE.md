# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this repo is

Monorepo for a connected E-machine (electric motor) CAE toolchain: three independent
subprojects that talk to each other over local HTTP services (`localhost`), run under
a restricted user **`cae`** (no sudo). It was assembled from previously separate repos
(see root `README.md` for the full picture) — each subproject still has its own
history, conventions, and often its own `CLAUDE.md` / docs. **Read the subproject's own
docs before working in it** — this file only covers cross-cutting/root context; it does
not restate subproject detail.

| Folder | What | Stack | Start |
|---|---|---|---|
| `cae_orchestrator/` | Browser CAE for IPM motors: geometry → EM field → structural FEM → thermal → drive-cycle, PDF report | Python/Flask + FreeCAD/CalculiX/Elmer/OpenFOAM/Blender | `cd cae_orchestrator && ./start.sh` → http://localhost:5000 |
| `connection_detection/` | FreeCAD workbench: geometric connection detection in STEP assemblies (basis for multi-body CalculiX) | Python FreeCAD addon (`rtree`) | `FreeCADCmd cli.py -- input.step -o out.json` |
| `pikogk/` | PicoGK geometry kernel + HTTP API (voxel/implicit geometry, LLM-driven "skill" generation) | .NET 9 + native `picogk.so` | `cd pikogk && ./start.sh` → http://localhost:5266 |

Each subproject has **its own CLAUDE.md or docs** — read those before working there:
- `cae_orchestrator/CLAUDE.md` — extremely detailed (pipeline stages, endpoints, magnet
  topology system, 3D EM field solver, canvas designer, etc.). Consult it rather than
  re-deriving architecture from source.
- `pikogk/EXPERIENCE_REPORT.md` — how the Linux port was built (native build steps,
  workarounds for the officially-Windows/macOS-only PicoGK).
- `pikogk/INTEGRATION.md` — HTTP contract for calling the PicoGK web API from another
  program.

## How the pieces interact

- `pikogk` (port 5266) and Ollama (port 11434) run as standalone local HTTP services;
  `cae_orchestrator` and other scripts call them via `localhost` regardless of the
  caller's own working directory.
- `connection_detection` shares the FreeCAD toolchain with `cae_orchestrator` but is
  otherwise independent (no HTTP link between them).
- Nothing in this repo talks to the network beyond `localhost` — no auth/TLS anywhere,
  intentionally (local PoC scope).

## Shared toolchain (system-wide, outside this repo — do not try to vendor/rebuild it)

- FreeCAD 1.1.x built from source under `~/freecad_1.1_quellcode` (via pixi) + CalculiX
  (`ccx`) in the same pixi env. **`/opt/freecad-1.1` is actually 1.2 with a
  visualisation bug — never use it.**
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
