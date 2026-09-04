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

## Pairwise comparison: what is actually being decided

The screening section below answers "which variant do I take?". One step earlier a
different question stands: **what does the machine actually depend on?**
`ema_paarvergleich` puts eight axes — magnet arrangement, conductors per slot, magnet
/ lamination / conductor material, cooling, diameter, length — option against option,
all eight in **0.4 s**.

```bash
python3 cae_orchestrator/cae_cli.py paarvergleich --from-project last
```

Two outputs, and the second is the more useful one. First the **pairs**: which metric
speaks for which side, and which does not move between them at all. Second **"what
moves what"** — the spread of each metric across the options of ONE axis. The order in
which the decisions have to be made falls out of that instead of being guessed
(measured on a 260 mm machine):

| Metric | strongest axis | spread | then |
|---|---|---:|---|
| Kt | magnet arrangement | 230 % | diameter 59 %, slot count 0 % |
| continuous torque (S1) | cooling | 550 % | diameter 125 %, length 86 % |
| safety factor at n_max | lamination | 282 % | diameter 125 % |
| mass, cost | diameter | 126 % | length 85 % |

**Deliberately no overall score and no winner.** Weighting Kt against cost and mass is
a goal decision, not a calculation — `screen --ziel` already does it in the open. The
pairwise comparison puts things side by side; the choice stays with the human.

**One defect the build turned up.** The first draft computed losses with
`compute_losses(iq, id_)` and thereby claimed **28×** the loss between 2 and 12
conductors per slot. The reason: the analytical torque relation normalises to **one**
turn per slot, while phase resistance grows quadratically with conductor count — at
constant ampere-turns the two cancel. The axis now runs through
`ema_thermal.design_point_losses`, whose copper anchor is current density × copper
volume and therefore turn-count independent; what remains is the fill factor, whose
measured optimum is at 8 conductors per slot.

A second find came with it: `_passt` in the screener rejected **every purely
surface-mounted arrangement**, because rim-mounted magnets have no interior pocket and
the radial containment test therefore ran on "infinity". SPM was thus unreachable for
`screen`, although the layout gate accepts it. Fixed and pinned in the test — together
with its counterpart: Halbach is still rejected, but for a real reason (its tiles
overlap by 5.95 mm), and gate and fit agree on that.

All analytical: no field run, no FEM, no thermal simulation. Cooling acts only through
a table of shear stresses per cooling type, not through a computed heat transfer.

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

## Draft or detail: how much compute for what

The calculation tab now carries two presets, **📐 Entwurf** (draft) and **🔬 Detail**.
They set frame count, resolution, speed step and the structural settings; the label
above them says whether the current state still matches a preset or has become a
custom one.

What makes a preset defensible here is a measurement (project *Alpenpass*, vasym,
p=3, 36 slots, saturation on):

| N | seconds | B_gap [T] | Kt | Br fundamental, dev. from N=600 |
|---:|---:|---:|---:|---:|
| 120 | 0.54 | 0.477 | 0.031 | −92.0 % |
| 240 | 4.79 | 0.477 | 0.031 | −52.5 % |
| **300** | 9.18 | 0.477 | 0.031 | **−2.8 %** |
| 600 | 68.75 | 0.477 | 0.031 | 0 % |

**B_gap and Kt do not move at all across the range** — they come from the analytical
anchor, not from the grid, while runtime rises by a factor of 127. What does depend on
resolution is the **shape** of the air-gap wave, and that has its knee at N=300. A
draft run therefore loses no metric, only image sharpness — and still no preset sits
below 300: the report field images render at twice the frame resolution, so the
draft's 180 px lands at 360.

**The agent could not choose any of this.** The knobs live in *no* schema — they
describe how precisely to compute, not what the machine is — so `--set
fdm_resolution=300` was rejected as unknown and every trial an agent ran went at
full detail: hours where minutes would do. The table now lives in
`ema_text2ema.GUETE` as the single source, `cae_cli.py run --guete
entwurf|detail` applies it, and a test nails the browser's copy against the
Python one the way the topology test does for the JS mirror.

And the **number of draft loops is the human's to set**, not the agent's: a field
in the agent start mask that reaches both heads as a standing instruction — *that
many fast rounds, `sicherheit` after each, and only when a state holds does one
run go to detail.* Without it agents fell into one of two extremes, both observed
here: a single multi-hour detail run that decides nothing, or fiddling without
end.

**The runtime estimate was more than an order of magnitude too low.** It assumed one
factorisation per rotor angle and a cheap back-substitution per speed. That was right
while the frames ran linearly; since they run saturated it no longer holds — the
saturation pass builds a new field-dependent µ per frame that by construction never
recurs and is therefore deliberately not cached. Measured, the second frame at the
**same** angle costs 8.97 s against 8.99 s for the first: the cache saves 0.2 %, not
97 %. The estimate also counted only the rotation, not the two extra visualisations.
It now uses directly measured seconds per frame (0.74 / 2.86 / 4.64 / 8.61 / 18.72 /
59.64 s for N = 120…600) and states the number that falls out: **9 minutes for the
draft, 2.7 hours for detail.**

## Solid shaft or hollow — measured, not assumed

A shaft bore (`shaftBoreD`, 0 = solid) saves mass and inertia and takes coolant or
a spline. It is wrong only when **flux runs through the shaft**. That is
measurable, so it is measured: `cae_cli.py welle` solves one field, takes the
radial |B| profile in the rotor (mean and p95 over the full circumference per
ring) and, from the inside out, finds the first ring above 0.05 T. Everything
below that is the **flux-free core** and may come out; the finding hands you the
change ready-made (`--set shaftBoreD=58.0`) or says a solid shaft is needed.

The decision is on the **core**, not on the mean over the whole shaft, and the
difference is not academic: on a 120 mm shaft the outer ring measurably carries
flux while the core stays free to r = 54 mm. Decided on the mean, one finding
would read "solid shaft required" and "bore up to 104 mm harmless" at the same
time — both cannot be true. The bore is capped at `shaftD-2`, which is exactly
where the schema otherwise silently resets it to 0.

The finding is **magnetic** and says so: whether the shaft carries torque and
centrifugal load is `struktur`/`sicherheit`. A magnetically harmless bore can be
mechanically inadmissible.

## From the designer straight to the agent

Geometry roughed out in the canvas designer goes to PI or Hermes as a **starting
point** without a pipeline run — two buttons in the designer tab. The payload is
topped up from the schema defaults (otherwise the agent inherits half a payload
and silently gets defaults where it assumes a decision) and written as
`meta.json`: exactly where `--from-project` and the project profile already look,
so no new tool is needed.

The point it turns on: a bound project is normally **expressly not a template** —
that is the mistake `--frisch` was built against. A deliberate hand-over is the
opposite, so it is marked as such and **inverts** the standing instruction: *start
here, change what you must, and say what you changed and why.* The description
typed when a project is created now also reaches the agent, so the same task is
not typed twice; a designer hand-over appends to it rather than replacing it.

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

**Which project?** Hermes now asks that first at a terminal — a list of the eight newest
projects with their calculation state and the date of their Hermes store, plus "shared
store" as a way out. PI still simply takes the newest, and that is not an oversight: PI's
memory is not bound to a project, Hermes's is. Landing in the wrong project with Hermes
serves you another design's lessons as fact, and you do not notice. It only asks without
`--projekt`/`--kein-projekt` and only at a terminal; the default is the newest project,
i.e. the previous behaviour.

**New or previous session?** Both heads can resume, but neither used to ask — and what
is not asked is not used: every question started from zero while the session with the
whole history sat next to it. Both now show a short menu at a terminal, **defaulting to
new**. And when there is nothing to resume, it now says so: with a per-project store a
fresh project is always empty, so the menu never appeared — indistinguishable from a
broken one. Resuming automatically would be wrong (a carried-over history only becomes visible
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

## What survives an agent run

An agent that computes and leaves nothing behind is a demo, not a tool. Three
things used to disappear.

**The results of the local verbs stood nowhere.** Of the sixteen local verbs
exactly one wrote to disk. `paarvergleich`, `screen`, `rotor-check`,
`sicherheit`, `welle` — the verbs with which a design is actually *decided* —
printed to stdout: it showed in the results column, scrolled off the top, and was
gone at the next start. The reasoning behind a design did not outlive the design.
They now write `<project>/rechnungen/<time>_<verb>.txt` with the invoking command
in the header, plus one line in `project.json`'s evolution log. Not into
`results.json`: that belongs to the pipeline run and would be rewritten by the
next `run analyse`.

**The runs were written but unreachable.** A `protokoll_*.md` and an
`ereignisse_*.jsonl` were saved after *every* turn — and nothing ever read them
back: no route, no verb, no button. From the seat in front of it, "written but
unreachable" is the same as "not saved", and that is how it was reported. There
is now **🗂 Frühere Läufe**: every run of both heads, newest first, each with the
prompts that were given — you recognise a run by what was asked, not by its clock
time. One click replays it through *the same* render functions as the live stream;
a second set would drift from the first. The overview never fully parses a
transcript — one measured here is **9.4 MB with 140,872 events** — and a single
run comes back capped at the ring-buffer size, cut from the front, because the end
is what you come back to.

**What is this project?** Asked for "a short profile of the project", an agent
described the *monorepo* — ports, subprojects, git branch. Not a hallucination:
about the machine it had nothing but a 1.7 MB `results.json`. `cae_cli.py
steckbrief [--laeufe]` and the same text at the top of the generated
`AGENTS.projekt.md` now carry machine type, poles/slots, envelope, air gap,
materials, operating point, which stages ran, and the key figures — **each with
its provenance** from the same register the computation database uses, because
`B_gap_T [analytisch]` and `T_maxwell_Nm [fdm2d]` sit side by side in one summary
and would otherwise look equivalent. It computes nothing: what is missing on disk
is printed as missing, not as 0.

### The work strip

An agent run looks the same from outside for minutes on end: text on the left,
nothing new on the right. Whether a web search is hanging, the solver is
computing, or simply nothing is happening was indistinguishable — and whoever
cannot see that either aborts too early or waits for something that is not
running. A strip under the results column, exactly as tall as the two input boxes
opposite, carries five lamps plus the agent itself: **computation** (the server's
fourteen state dicts, with progress), **research** (a pulse set by the code that
actually opens the connection, not guessed from the agent's tool text),
**solver** (`ccx`/Elmer/Z88/Gmsh/FreeCAD/OpenFOAM/Blender via `/proc/<pid>/comm`,
matched on the process *name* so a `grep ccx` in some shell does not light it),
**GPU**, and the **model** loaded.

Two things are deliberately absent or measured rather than assumed. There is no
"the model is thinking" lamp: Ollama reports over `/api/ps` only what is *resident*,
not what is computing, and a lamp labelled that way would be worse than none. And
the GPU threshold is 50 %, not 12 %, because this card measures 18–24 % at idle
with only the desktop on it — a lamp at 12 % would be permanently lit. A poll
costs 5 ms; nothing is polled while the tab is hidden.

The **rate** is exact where it can be: Hermes keeps `output_tokens` per session,
so two samples give measured tokens per second. PI keeps none — there the page
counts characters and writes "Z/s" on it, because characters can be counted and
tokens cannot, and a figure extrapolated from characters would look like a
measurement.

### When a turn never ends

Reported as *"it says the agent is working, but it isn't"* — while the strip next
to it correctly said nothing was running. Measured cause: Hermes sent no answer to
`session/prompt` at all — no text, no tool, no error. The busy flag stayed set,
every further input was refused with "the agent is still working", and the only
way out was to end the whole run and lose the session. A hanging turn was
indistinguishable from a long one because nothing recorded *when something last
arrived*. It does now, the strip shows "still seit 8:13" in amber, the pill at the
top is corrected, and past 450 s of silence a **🔓 Sperre lösen** button appears.
It does not stop the agent — the process runs on, and a late answer still shows up
in the stream. That is said out loud rather than restarting the turn quietly,
which would leave two turns running side by side with nobody knowing.

### Two measured upstream defects in Hermes ACP

Both found by reproducing them with an own ACP client, so neither is caused by
this repo. Both are documented rather than papered over — and worked around where
a workaround is honest.

**Parallel tool calls lose their results.** With one tool per turn, `hermes acp`
v0.20.5 sends `tool_call` *and* `tool_call_update`. With three, it sends three
`tool_call` and **zero** updates: the results never reach the client, and the
results column stayed empty for the whole run (measured: 1,562 events, 3 tool
calls, 0 results). They are not lost, though — Hermes writes every tool result
into its own `state.db`, because the model receives them too. They are read back
from there at the end of the turn (read-only, with a timeout — the file belongs to
the running Hermes) and fill the silent tiles with the *real* text. Matched in
*order*, not by id: ACP hands out `tc-…`, the store `call_…`, two numbering
schemes. Only where the store has nothing does the honest placeholder remain.

**`skill_view` does not find a skill that is demonstrably there.** It answers
*Skill 'cae-orchestrator' not found* although `hermes skills list` shows it
(source `local`, trust `local`), the repo is in `trusted_project_dirs`, the
process cwd is the repo, and the identical call succeeds in an ordinary Python
process with the same `HERMES_HOME` and cwd. Not patched here. Instead every start
document names the file path outright — `AGENTS.md`, the generated
`AGENTS.projekt.md`, both start scripts: *read it as a file.* An agent that thinks
the skill is absent starts computing without verbs, runtimes, exit codes and
traps.

### Screen recording follows the results column

The recording used to pause while the server computed, on the argument that
nothing changes on screen but a progress bar. Measured, that is false: in one run
**five images arrived in the results column mid-computation** — cross-section,
side view, air gap, field, field under load. It paused during precisely the
moments worth keeping. Now every tile, every image, every prompt and any scrolling
in the results column resets the clock, and the recording resumes the instant
something appears rather than at the next watchdog tick.

Better still, it writes down **when** things happened. Each event is stamped with
its **video second** — elapsed time *minus* pauses, since a list against the wall
clock drifts further with every pause — and on stop two files land next to the
recording: a `.marken.tsv` and an executable `.schnitt.sh` that merges neighbouring
marks into segments, cuts each with lead-in and lead-out, and concatenates them.
Deliberately re-encoding rather than `-c copy`: copying cuts at key frames and
misses the moment by seconds. With that list the pause is only a size saving and
no longer a constraint — a checkbox turns it off, and you cut afterwards.

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
