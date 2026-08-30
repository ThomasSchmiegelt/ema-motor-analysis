# ai-workspace

*[Deutsche Fassung →](README.de.md)*

A connected CAE toolchain for electric machines (IPM traction motors): geometry →
electromagnetic field → structural FEM → thermal → drive cycle → PDF report. Runs
locally under a restricted user, driven from a browser, a command line, or a **local**
language model.

**Honest up front, so the table promises no more than it delivers:** the chain is
carried by `cae_orchestrator`. The other folders are independent subprojects at
different stages of maturity that are *not* wired to each other today — see the
"Wiring" column.

## Subprojects

| Folder | What | Stack | Start |
|---|---|---|---|
| `cae_orchestrator/` | Browser CAE for IPM motors (geometry → EM field → FEM → thermal → drive cycle, PDF report) | Python/Flask + FreeCAD/CalculiX/Z88/Elmer/OpenFOAM/Blender | `cd cae_orchestrator && ./start.sh` → http://localhost:5000 |
| `connection_detection/` | FreeCAD workbench: geometric connection detection in STEP assemblies | Python FreeCAD add-on (`rtree`) | `FreeCADCmd cli.py -- input.step -o out.json` |
| `pikogk/` | PicoGK geometry kernel with an HTTP API (voxel/implicit geometry, LLM-generated "skills") | .NET 9 + native `picogk.so` | `cd pikogk && ./start.sh` → http://localhost:5266 |
| `physics_surrogate/` | ML surrogate for the 2D-FDM field stage (PhysicsNeMo/Torch) | Python + Torch/CUDA | `cd physics_surrogate && ./start.sh` → http://localhost:5300 |
| `lego/` | LLM-generated LEGO Technic mechanisms, scored against ORCA hand kinematics | Python + BrickNet | — (CLI) |

## Wiring — what actually exists

| Connection | State |
|---|---|
| `cae_orchestrator` → **Ollama** `:11434` | **present** — report, chat, AI design, target-value optimiser, RAG embeddings |
| `cae_orchestrator` → **physics_surrogate** `:5300` | **read-only** — the 🧠 tab polls `/health` and plots `history.csv`. There is **no** inference path: `/predict/*` returns a hardcoded 503, and the `ema_surrogate.py` client its own README advertises does not exist |
| `cae_orchestrator` ↔ **pikogk** `:5266` | **absent.** Grepping the orchestrator for `5266`/`pikogk` returns nothing. `pikogk/INTEGRATION.md` documents the contract for a link that was never built |
| `cae_orchestrator` ↔ **connection_detection** | **absent.** The JSON export carries `tie`/`contact` labels for multi-body CalculiX, but no consumer is written anywhere in this repo |
| `lego/` | standalone — no service, no port, no dependency on a sibling |

## What makes this different: every number says where it came from

The same quantity can be obtained at several levels of sharpness, and the choice is a
trade between time and confidence. **Which level produced a number is recorded per
value**, not guessed afterwards:

| Quantity | fast | sharper | sharpest |
|---|---|---|---|
| Air-gap field, torque | analytic formula (ms) | 2D FDM (seconds) | 3D Elmer FEM (minutes) |
| Rotor strength | rotating-ring formula × Kt (ms) | own deck, pole sector (~1 s) | FreeCAD + CalculiX, full rotor (minutes) |
| Solver check | — | — | CalculiX **and** Z88Aurora on one mesh |
| Sheet cross-section | parameter study | topology optimisation (~20 s) | — |

Two values that sit side by side in the same result set and are **not** equivalent:

* `B_gap_T` comes from the **analytic** air-gap formula — not from the field picture.
* `T_maxwell_Nm` comes from the **solved 2D-FDM field** (Maxwell stress tensor).

Without that distinction a report would claim a field computation that never happened.
The rule runs through the whole tool: report prose is stripped of numbers
(`_strip_value_numbers`) and the figures appear only in deterministic tables — each
with its origin.

## Computation database

Every run writes into one SQLite file (`~/cae_projekte/_db/rechnungen.db`): input
parameters, key figures **with the method that produced each one**, images, gates. It
does **not** replace `results.json` — it is a queryable index over it and can be
rebuilt from disk at any time.

Measured on a real stock: 35 runs, of which 14 complete and **21 aborted**. The whole
numeric history fits in **208 kB**, against 20 GB of project data — because a
`results.json` is 1.7 MB, of which 884 kB are base64 images while the actual key-figure
set is 0.9 kB.

```bash
cd cae_orchestrator
python3 cae_cli.py db import                       # read ~/cae_projekte
python3 cae_cli.py db liste
python3 cae_cli.py db guete --lauf last            # what was computed, and how sharply
python3 cae_cli.py db vergleich                    # one row per run, origin per column
```

Aborted runs stay visible instead of being silently skipped — otherwise the database
would look more complete than the stock is.

## What the toolchain has learned from its own runs

```bash
python3 cae_cli.py lernen zeige
```

Two sources, kept strictly apart:

* **Measured** — derived from the database on every call. Nobody writes it, nobody can
  colour it. It found a real defect immediately: of 11 runs with `struct_mesh_mm = 2`,
  exactly **one** produced a structural-FEM value; the rest ran into the timeout
  unnoticed.
* **Experience** — notes deposited by an agent or a human, accepted **only with
  evidence** (a run id, a measured number, a command output). Without evidence they are
  refused. A store that accepts unverified impressions fills with folklore, and the next
  model reads it as fact.

No model is trained here. "Learned" means: derived from the tool's own stock and
available next time.

## Two solvers on one mesh

Besides the FreeCAD route there is an own deck: Gmsh meshes one pole sector — or the
full rotor — from the same magnet geometry the 2D field uses, and the CalculiX input
file is written directly. **Z88Aurora V5** solves the same mesh as an independent second
opinion.

| Quantity | CalculiX | Z88 | Δ |
|---|---:|---:|---:|
| von Mises, mean | 57.15 MPa | 57.15 MPa | 0.00 % |
| von Mises, P99 (the gated value) | 128.89 MPa | 128.90 MPa | 0.01 % |
| Bore hoop stress | 161.57 MPa | 161.62 MPa | 0.03 % |
| max displacement | 40.59 µm | 40.60 µm | — |

This checks **solver and deck** — not the mesh and not the model. A mesh both see wrongly,
both see wrongly. Speed: 797,275 elements plus a 40 s FreeCAD start become **13,669
elements meshed in 0.4 s**.

That deck also carries the **topology optimisation** (SKO, optionally SIMP/OC, ~0.8 s per
iteration): it needs a per-element Young's modulus, which FreeCAD's writer cannot emit.
The result is a **density field, not a part** — a sheet cross-section has manufacturing,
flux and stiffness constraints no density field knows.

## Two agent heads, one skill

The chain is drivable by a **local** model — via [PI](https://pi.dev) or **Hermes Agent**
(Nous Research). Both run on the same Ollama model and read the **same** skill from
`.agents/skills/`; nothing is copied or symlinked, so they cannot drift.

```bash
./start_agent.sh                          # PI
./start_hermes.sh                         # Hermes
./start_hermes.sh --nur-pruefen           # prove it only talks to local Ollama
```

Both answer the same question with the same number (measured: **0.806 T**, both with the
note that it comes from the analytic formula). `start_hermes.sh` **measures** before every
start that Hermes only contacts `127.0.0.1:11434` — its shipped default points at a cloud
endpoint, and two known upstream bugs make the local setting fall through to it silently.

**Why a CLI and not MCP:** a local model cannot hold ~135 HTTP routes as 135 tool schemas
in its context. Tools are bound as *skill = CLI + README*.

## Research — and its boundary

The agents may look things up on the internet (`cae_cli.py recherche suche|hole`). What
comes back is marked as **foreign text**: it may be wrong, outdated, or contain
instructions aimed at a language model. It may **never** replace a computed number.

What matters can be filed under the project — text, images, and extracted values:

```bash
python3 cae_cli.py recherche merke --projekt last --adresse https://… \
  --wert "web_mm=1.8 mm :: quoted passage the value comes from"
```

Values land in a **separate** table `referenzwerte`, never among the computed
`kennwerte`. A researched value may be correct, but it was not recomputed. Source and a
verbatim quotation are mandatory; numbers are never scraped from prose automatically.

**Computation stays local.** Nothing is uploaded, no calculation is outsourced.

## Phone (`/m`)

A deliberately narrow second path: enter dimensions → draw a half pole → compute four
operating points with the 2D-FDM solver, as an installable web app (PWA). Measured on the
example machine: **four points in ~9 s, 1.7 MB**. The entry URL with a QR code is printed
at server start.

## Shared toolchain (system-wide, not in this repo)

- FreeCAD 1.1 source build + CalculiX (`ccx` 2.23); `ccx` is also called directly, without FreeCAD
- **Z88Aurora V5** (batch solvers only). `z88r` needs `LD_LIBRARY_PATH` set to its own MKL and **two** runs — `-t` writes `Z88R.DYN`, which `-c` then reads. **Z88Arion has no Linux build**
- Gmsh (the Python module in the orchestrator venv), OpenFOAM v2406, Elmer, CUDA, pandoc/pdflatex
- Ollama at `localhost:11434`

## Runtime data (never versioned)

`cae_orchestrator` writes projects to `~/cae_projekte`, the database to
`~/cae_projekte/_db`. `pikogk` writes generated geometry to gitignored folders. The
built native `picogk.so` is a build artifact — a fresh clone must rebuild it (see
`pikogk/EXPERIENCE_REPORT.md`).

## Note on network exposure

The server binds `0.0.0.0` and sets `Access-Control-Allow-Origin: *` — it is reachable
from the same WLAN **without auth and without TLS**. That is deliberate for a local
proof of concept; only the phone path `/m…` requires a token. Do not expose this to an
untrusted network.

## Licence

Code developed here is **MIT** (`LICENSE`). Third-party components keep their own
licences; `THIRD-PARTY-NOTICES.md` separates what is **redistributed** from what is
merely **required** (locally installed or self-built) — including **PicoGK** by LEAP 71
(Apache-2.0) and **Z88Aurora** (University of Bayreuth).
