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

**Topics:** electric motor · IPM · PMSM · traction motor · motor design · CAE · FEA ·
finite element analysis · CalculiX · Z88Aurora · FreeCAD · Gmsh · Elmer · OpenFOAM ·
electromagnetics · 2D FDM field solver · topology optimisation (SKO/SIMP) · centrifugal
rotor stress · lumped-parameter thermal network · drive cycle (WLTP) · design space
exploration · pole/slot combination · magnet arrangement · local LLM ·
Ollama · agent skill · PI · Hermes Agent · provenance tracking · SQLite

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

## Screening the configuration before computing one

A full run takes 30 min to 4 h, so in practice every calculation started from the last
one and changed a value or two. Pole count, slot count and magnet arrangement of the
*first* draft therefore stayed put — and those are exactly what shapes a machine.

`ema_screen` looks at them first, analytically: **384 configurations in 20 s**, ranked,
with every rejection stated in words.

```bash
python3 cae_cli.py screen --from-project last \
        --auftrag "affordable city drive, low on magnets"
```

The goal is read from the design brief **with the words that carried it**, so it is never
a black box (`guenstig` ← *affordable*, *low on magnets*). Cost-oriented and
performance-oriented briefs weight the same variants differently; the weights are open in
the code so they can be argued with.

It **sorts out and ranks — it decides nothing.** No field run, no FEM, no thermal: the
metrics it produces carry the provenance `analytisch`, and whatever it puts on top still
has to be computed properly.

**Building it turned up three defects that were not in the screener.** It first passed
only 69 of 384 variants, which would have made it a filter, not a screen:

| Found | Effect |
|---|---|
| `_obb_rect_distance` took the **loosest** separating axis (`min`) instead of the tightest | For two long pockets crossed at a steep angle the layout gate reported **0.51 mm of web where 17.11 mm are free** — a factor of 33. The gate had been rejecting sound designs for as long as the tool has existed, not just inside the screener. `max` is still a lower bound, so it never over-reports a web: the gate stays on the safe side |
| `_build_spoke` seated the magnet 1.0 mm above the bore, ignoring the pocket's end cap of `magThick/2 + gap` | From 1.8 mm thickness the pocket cut **into the shaft bore**. The spoke type was not buildable at any setting |
| `_build_u` reserved the web between magnet **bodies** instead of between **pockets** | 1.70–1.73 mm against a 2.00 mm minimum, unchanged across every parameter. The U-cup was never buildable either |

After the fixes: **312 of 384 usable, all eight magnet arrangements reachable at all four
pole counts.** The remaining 72 fail the symmetric three-phase winding criterion — that is
arithmetic, not geometry.

The fit has **two** knobs, because one cannot work: shrinking the magnet body thickens
*every* web, while pulling the arrangement tighter thickens the webs *between* poles and
thins the ones *inside* a pole. Layered arrangements need the opposite — `pmasynrm` is
legal at 16 mm layer spacing with a 2.71 mm web and fails at 8 mm with 0.01 mm. Every
reduction is recorded: a screen that quietly shrinks magnets and then ranks by torque
constant would be deceiving itself.

Drive cycles now include **city/rural** alongside WLTP, full load and motorway: 1300 s,
18.76 km, 94.9 km/h peak, 12 % standstill (measured).

## Image dataset: what the eye sees and no metric measures

Some things about a lamination cross-section a human judges better than any formula —
whether the webs are even, whether the magnet suits the pole pitch. `ema_bilddaten`
prepares exactly that question: draw random rotor cross-sections, have them rated by
hand, and mine the ratings for a **checkable threshold**.

```bash
python3 cae_orchestrator/cae_cli.py bilddaten erzeugen --anzahl 500
python3 cae_orchestrator/cae_cli.py bilddaten seite     # open bewerten.html
python3 cae_orchestrator/cae_cli.py bilddaten einlesen --datei ~/Downloads/urteile.json
python3 cae_orchestrator/cae_cli.py bilddaten regel --merken
```

The occasion was a plan for **10,000 random machines** to train a vision model. The idea
holds, the number did not — three measurements brought it down to ~500:

| Measured | Consequence |
|---|---|
| Of randomly drawn geometries, **27 %** pass the layout gate (107 of 400) | The other three quarters are pockets that intersect or stick out of the rotor. `rotor_layout_check` decides those in milliseconds and exactly — nobody needs to look at them |
| Of the survivors, the existing heuristic already calls **79.3 %** "bad" | A human judgment adds nothing where a rule already decides |
| That leaves ~**5 %** of the draws where the eye is genuinely needed | At 10,000 that would be 500 worthwhile images and 9,500 wasted. So the 500 are drawn directly |

Drawing goes through the **same** code as the project report's image
(`ema_pipeline.render_cross_section`, extracted from `_save_cad_images` and verified
bit-identical in the test) — a renderer of its own would have shown machines that were
never computed that way. Only smaller and unlabelled: 384 px, 0.138 s and 33 kB per
image against 0.245 s and 172 kB at report size.

Two things that deliberately do **not** happen:

* **No heuristic pre-fill.** The rating page shows the image and nothing else — no
  dimensions, no metrics, no suggestion. Suggest a guess and you get it confirmed back,
  and the independent judgment you were after is gone.
* **No neural net.** The geometry is known exactly; estimating it back out of pixels
  would be a step backwards. What comes out is a threshold over measured quantities
  (web width, pole coverage, hub fraction …) that can be measured on the lamination and
  argued with.

`regel` checks the threshold it finds on a **held-out third** (fixed assignment by
variant id, the same in every run) and only then files it as evidenced experience. If it
does not hold there, it says so and writes nothing — a threshold that only fits the
training part is a property of the dataset, not of the rotor. The test pins both cases:
a threshold planted in the ratings must be recovered (held-out 1.00), and coin-flip
ratings must let nothing through (training 0.63, held-out 0.48 — refused).

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
./start_hermes.sh --projekt Alpenpass     # bind Hermes to one CAE project
./start_hermes.sh --nur-pruefen           # prove it only talks to local Ollama
```

**New or previous session?** Both heads can resume, but neither used to ask — and what
is not asked is not used: every question started from zero while the session with the
whole history sat next to it. Both now show a short menu at a terminal, **defaulting to
new**. Resuming automatically would be wrong (a carried-over history only becomes visible
at 65 k context once something falls off the front); asking is the middle ground. Nothing
is asked without a terminal, on a one-shot `-p`/`-z`, or when the caller set the session
flags themselves — a scripted call must not block.

**Hermes keeps memories and sessions per project.** Its built-in store is otherwise *one*
file for the whole machine (`~/.hermes/memories/MEMORY.md`, 2200 characters) with no
config option to separate them — the agent would read what it learned about one design as
fact while working on the next. The lever is `HERMES_HOME`, but it moves the *entire*
store, and a per-project `config.yaml` would be exactly the drift this repo avoids with
the skill. So it is split: `config.yaml`, `.env` and `skills` are **symlinked** (one
source), only `memories/` and `sessions/` live under `<project>/_agent/hermes/`. **PI does
not get this**, and that is not an oversight: PI sorts sessions by working directory, and
that has to stay the repo root or PI finds neither `AGENTS.md` nor the skills.

**The project context is generated, not copied.** `AGENTS.md` stays the one unchanged
source of rules and is never copied into a project folder — a copy drifts silently, and
then two agent heads work from two rulebooks that both look plausible. Instead, every
start freshly writes `AGENTS.projekt.md` (not versioned) with the facts of the current
project: identifier, directory, the metrics that exist — and above all **which stages have
not been computed**. It states explicitly when a strength figure is analytic rather than
FEM; that looks identical in the output and has slipped through unnoticed three times in
this repo.

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
- **Z88Aurora®** V5 — freeware of the Chair for Engineering Design and CAD (LCAD), University of Bayreuth, by Prof. Dr.-Ing. Frank Rieg; batch solvers only. `z88r` needs `LD_LIBRARY_PATH` set to its own MKL and **two** runs — `-t` writes `Z88R.DYN`, which `-c` then reads. **Z88Arion has no Linux build**
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
