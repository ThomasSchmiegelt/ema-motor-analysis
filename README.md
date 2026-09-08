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
`ema_paarvergleich` puts **twenty axes** — machine type, magnet arrangement, inner/outer
rotor, winding type, conductors per slot, magnet / lamination / conductor material,
cooling, shaft joint, bolting, flux barriers, pocket opening, **skew**, **DC-link
voltage**, **current limit**, V opening angle, shaft diameter, diameter, length —
option against option, in seconds.

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

### The magnet pocket now comes from its WALLS

A V-pocket used to be built from three numbers, none of which is a wall:
`magDepthRel` (relative radial seat, 0…1), `magWidth` (length in mm) and `magDist`
(web spacing in mm). None follows from the others, and whether they fit together is
something only the layout gate can say. In a measured agent run on 2026-09-07 that
cost **four stage-0 aborts in a row**:

| | rotor radius | finding |
|---|---:|---|
| 1 | 25.8 mm | pocket sticks out **2.45 mm** |
| 2 | 25.2 mm | pocket sticks out **0.15 mm** |
| 3 | 25.5 mm | pocket sticks out **1.96 mm** |
| 4 | 25.5 mm | collision with the neighbouring pole, **0.77 mm** |

The gate was right every time. What was wrong is that there was nothing to derive the
pocket *from* — so guessing was the only option left.

But a pocket has walls, and those are the real design quantity. "Pocket" here always
means the pocket **including its end caps and the glue gap**, not the magnet body —
that is what actually gets cut:

| Wall | mm | against | what it holds |
|---|---:|---|---|
| rim | 1.3 | rotor OD | pole shoe against centrifugal load; also short-circuits the magnet |
| d-axis | 1.5 | pole symmetry axis | carries the two V arms against each other |
| q-axis | 2.0 | the neighbouring pole's pocket | carries the reluctance path, caps the arm length |
| spoke | 1.5 / 2.0 | rotor OD / shaft OD | |

The d-axis wall was **nowhere expressed** before — on the baseline design it fell out
of `magDist = 8` by accident, at **0.81 mm**.

Seat and web spacing follow from the walls in closed form; only the **length** is
searched, and against the real layout gate rather than a second distance formula
sitting beside it. On the baseline rotor (Ø 188.6, 6 poles, 120°, 6 mm thick):

| | magnet length | web spacing | seat | d-axis wall |
|---|---:|---:|---:|---:|
| before (guessed) | 24.72 mm | 8.00 mm | 0.681 | 0.81 mm |
| from the walls | **42.24 mm** | 9.37 mm | 0.446 | **1.50 mm** |

**One number in that derivation was wrong, and it looked right.** The seat `r_pos` is
the magnet's *inner end*, not the pocket centre — from the inner end to the outer cap
centre is `L + gap`, not `L/2 + gap`. Computed with the wrong distance, the pocket of
an 84 mm design sat **36.2 mm outside** the rotor. It only showed up on a
cross-check: a first measurement had hidden it, because the old position mode clamps
the length as well and therefore cut the over-long pocket back down again.

**Where it applies: new designs only** (`--frisch`). Existing projects carry their
mode in their stored payload and do not move by a single digit — verified bit-identical
across all topologies over 2430 cases.

**Failing honestly is part of it.** Ten poles on a 51 mm rotor with 3 mm thick magnets
leave 1.38 mm of arm between the walls. A magnet shorter than it is thick does not get
built; instead of the number you get a refusal naming the four levers (fewer poles,
bigger rotor, thinner magnet, shallower angle). Returning 1.38 as "ok" would be worse,
because a whole chain then computes on it.

**Side finding on the spoke type:** both its walls measured **1.20 mm** although the
code intended 1.3 — the glue gap enters twice (the end cap sits one gap *outside* the
magnet end **and** carries the radius `thickness/2 + gap` itself). Now 1.5 mm at the
rim and 2.0 mm to the shaft, and unconditionally: no degree of freedom is taken away
here, a wall is corrected that the tool meant to hold anyway.

### One letter, twenty-five minutes

In the same run the agent set `--set windingType=runddraht` — the correct German
spelling — and got:

```
FEHLER: windingType: 'runddraht' unbekannt. Zulaessig: hairpin, rundraht
```

The accepted value is `rundraht` with **one** "d". The tool writes both spellings
itself: `ARTEN = ("hairpin", "rundraht")` sits next to
`ART_LABEL["rundraht"] = "Runddraht (…)"`. After that the agent could no longer see
the difference: some thirty calls recomputing the same thing over and over
(`printf 'runddraht' 'rundraht'`, `cand.count('d')`, `[c for c in g]`, four
`curl /param_schema` invocations with hand-written search functions), a formal
retraction in between ("my typo, not a tool bug") — and two lines later the same
mistake again. Net result: **no insight, ~25 minutes, ~60 calls.**

Two lines of tool, not two lines of prompt: known German spellings are now rewritten
rather than refused (and the rewrite is printed), and an unknown **value** gets the
same typo suggestion an unknown **key** has had all along — `Meinten Sie 'hairpin'?`.
The enum value itself was deliberately not renamed: it appears in the generated
FreeCAD script, in four test files and in every stored project file.

### Cogging torque — the quantity behind "very precise"

One brief asked for a robot-arm drive, "very precise, including rotational accuracy".
The tool did not know that quantity. There was one line:

```python
T_cogging_est = Br_NdFeB * R_gap * L_ax * 0.05 / lcm * 1000   # before
```

The remanence of the **material** instead of the air-gap field, a coefficient 0.05
with no provenance — and above all: **the slot opening does not appear in it.** It is
the single strongest lever. Two designs with the same pole and slot count got the same
number, no matter how wide the slot opened towards the air gap.

**It is not measured, and that is stated.** The obvious route — rotate the rotor
through one cogging period in the FDM — does not work here, measured on a 24-slot /
10-pole machine (cogging period 3.0°). After a full period the *same* value must
appear:

| Resolution | T(0°) | T(3°) | Difference |
|---|---:|---:|---:|
| N=500 | 8.70 Nm | 0.30 Nm | **−8.40** |
| N=700 | 0.90 Nm | 4.10 Nm | **+3.20** |
| N=900 | 5.50 Nm | 3.70 Nm | **−1.80** |

It does not converge. The cause is staircasing: the rotor sits on a fixed Cartesian
grid, and rotating it flips pixels between iron, magnet and air, producing a spurious
torque many times larger than the one sought. Cogging needs a body-fitted mesh.

`ema_rastmoment` therefore computes it analytically after Zhu/Howe, and separates
cleanly what is **exact** from what stays an **estimate**:

- **Exact**, pure counting: `n_c = LCM(slots, poles)` (cogging periods per
  revolution), the cogging factor `2p·Q/n_c` after Gieras, and the skew factor.
  Skewing by exactly **one slot pitch** cancels the fundamental **exactly** — that is
  an integral over a full period, not an approximation.
- **Estimated**, factor ~2: the amplitude itself. Sound for *comparing* two designs
  (both carry the same error), not as an absolute promise. Every output says so.

**The important side finding:** this tool draws **open slots**. There is no slot
closure, no bridge — `nut_breite` at the bore *is* the opening, measured 4.03 mm over
a 0.70 mm gap. That is the worst arrangement for cogging, and the assessment says so
on every design.

In the pairwise comparison cogging runs as a **permanent column** but does **not**
count in the balance: how much rotational smoothness matters is decided by the
application, not by the tool.

### Inverter: voltage and current are settable

`--set inverterVdc=24 --set inverterImax=200 --set umrichterBezug=wicklung`

Previously 800 V / 800 A were module globals nobody could change. It is more than
passing two numbers through: the electrical model computes with **one turn per slot**
(`conductorsPerSlot` does not enter K_t, ψ, L_d/L_q or the envelope at all), so the
800 V belonged to an imagined single-turn winding. At fixed geometry and torque the
**ampere-turns** are fixed, and the turns count trades current against voltage
(K_t ∝ N, i ∝ 1/N, u ∝ N): 24 V at 200 A and 800 V at 6 A are the **same machine**
with two different windings.

`umrichterBezug` states which is meant — it is not inferred from the value. The first
attempt did infer it, and that broke visibly: in the current axis 800 A produced less
torque than 400 A, because the default value alone fell back to the other reference.

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

## A third head, and a chat that leaves the desk (`/studio`)

The two-column agent page is built for a desk: agent on the left, results on the right,
a drag handle between them that only listens to mouse events. On a phone it is
unusable — the same finding that produced the `/m` path, and the same answer: **don't
share the layout, share everything underneath it.**

The **📱 Studio** tab shows the same agent run in **one column** — question, thinking,
tool call, result, image, all under one another in the order they happened. Two columns
are two timelines, and a reader inevitably takes one as the continuation of the other;
here a result tile sits exactly where it was produced.

Behind it runs a **third agent** next to 🤖 PI and 🪽 Hermes: its own process, its own
session, its own memory. It stands explicitly *beside* a computing PI rather than in its
place, and so it gets a different standing order from the other two — **it writes about
what was computed, it does not compute on its own.** The design brief the others carry
(draft loops, drive-cycle choice, 3D counter-check) would be actively harmful here: it
would send the agent into an hours-long run while somebody waits on a phone for one
sentence.

Two things only became visible through that side-by-side, and both are now fixed rather
than described: `AGENTS.projekt.md` was rewritten on **every** agent start — so the
second head fed the first a foreign project the next time it read the file; and screen
recording exists **once per server**, not once per head, which the page now says
honestly instead of faking a second recorder.

**From a phone** it is the same conversation: "📱 Handy" shows the address and a QR code,
the phone joins mid-conversation and keeps typing. It is the only agent page deliberately
reachable over the LAN, so it — and only it — carries the same token as `/m`; one QR
covers both ways. Open from the machine itself (where it is a tab), token required from
anywhere else. PI and Hermes are untouched.

### Portrait, at a fixed resolution

A Reel and a Short are **1080×1920**. Record a landscape window and you get a 16:9 video
whose portrait crop is decided *afterwards, while cutting* — which means what ends up in
frame is decided then, too. So the Studio tab puts the conversation in a **stage of exactly
that pixel size** (9:16 by default, plus 4:5, 1:1 and "free"), scaled as a whole to fit the
window: the layout no longer depends on the window size, the dashed edge is the cut line,
and the crop is settled *before* recording. The stage is scaled, not its font sizes — it
carries its own type scale, about twice the size of a UI, because a Reel is read on a
phone. On a phone the whole thing is skipped: the screen is already portrait.

Next to it sits what is **actually** captured. The stage is 1080×1920 but sits scaled down
on screen, and it is the screen's pixels that get recorded — a 1000 px tall window measures
527×937, which the crop then scales up to 1920. That number is on screen with a warning
colour, rather than leaving someone to wonder later why the Reel looks soft; the remedy is
a taller window or a higher-density display.

The crop itself is not guessed: when recording starts the page writes a mark carrying the
stage rectangle, the window size and the capture size, and `crop=…,scale=1080:1920` follows
from it — **only** for a tab or window capture. If the whole screen was recorded the window
sits somewhere inside it, which cannot be known, so there is no crop line, just the sentence
saying why.

### Typeset, not raw — and the field analysis keeps its columns

The model answers in Markdown. Raw, that puts asterisks, hashes and pipes on screen; the
Studio tab typesets it instead: headings, bold, italics, code, lists, quotes — and
**tables**. The table is the actual point: a field analysis *is* a table, and
`| B_gap | 0.799 T |` as raw text is not one. The renderer is a short block of its own (no
library), it only ever sees the text the model wrote, and `test_studio.py` checks it with
`node` against fixed examples — the same method as the topology JS mirror.

Two details separate "typeset" from "tidy": a soft line break from the model becomes a
**space**, not a break — otherwise the right edge frays exactly where the model wrapped at
eighty characters; and italics only apply at word boundaries, or `em_field_load.png` takes
itself apart.

**Tool output** goes the other way: it keeps its columns and the *font* is fitted instead.
Wrapping destroys a table of key figures, scrolling hides it, and a height cap cut straight
through one — the Steckbrief ended after `safety_factor_fem`. The font size now follows the
**aligned** lines, recognised by their column gap; prose may wrap. That took three attempts,
each driven by a measurement: a percentile over all lines fell for the 228 characters of
prose in the `welle` output; a plain "contains a pipe" mistook the same sentence for a table
because `(|B| p95 …)` sits inside it; and without one character of slack a 94-character
table wrapped because 93 fitted after rounding. When a table genuinely does not fit — the
pair comparison measures 418 characters wide — the tile says so instead of wrapping in
silence.

### The bottom bar: two rows, and you can see who is doing what

On the phone it sat right; at the desk it did not. Four stacked rows, one of them just
for the storage path — truncated with ellipses, permanently in the way for something you
need once a day. The path now lives on the save button (hover is enough) and appears in
the transcript on a **manual** save, where it belongs chronologically. The "show
thinking" checkbox moved to the right end of the work row; that removes the fourth row
and gives the input its full width back for the icons.

Where the truncated line used to be there is now the same **lamp row** as on the desk
page: the agent itself (always, while it runs — "working · 0:42", "waiting for you",
amber "silent for 8:13" with the release button), plus computation with progress,
research, solver, GPU, loaded model, rate, and the tool lamp. The desk page shows every
lamp all the time; here only the active ones — the stage is 1080 pixels wide, and on the
phone they stay one swipeable row (wrapping, they measured six).

What still does not exist is a "model is thinking" lamp: Ollama only reports which model
is *loaded*, not whether it is computing.

### Images at full width — and the finished recording

Two things were missing from the transcript, and the first was a bug with a very
concrete cause: **the images were nothing but lines.** The transcript is a column
flexbox, and its children shrink by themselves once the content grows taller than
the stage — instead of scrolling, the browser squashes. An image with automatic
height has nothing to stop that; it is compressed first and hardest, and what
remains is a white stripe. Now nothing in the transcript shrinks; it scrolls,
which is what the overflow is for. (The desk page was never affected: its
transcript is an ordinary block. That is the counter-check on the cause.)

The size itself now follows one rule: **the card sets the width, the height
follows the aspect ratio.** Both halves are needed — setting only the width left
a 700-pixel chart small and lost on the 1080-pixel stage; leaving only the height
automatic distorted it as soon as the stage's height cap kicked in. An image that
does not arrive now says so: before, it was indistinguishable from a squashed
one — both a white stripe — and you go looking for the fault in the wrong place.

**The finished recording sits in the transcript, not just its path.** It used to
end with two lines naming where the file went — the same situation as the agent
runs before there was a way back: written but unreachable is the same as not
there, and on a phone all the more so, since there is no file system to go
looking in. Both agent pages now append a card with a player at the same place in
the transcript where every other result appears; the server hands out the file
from the video folder, limited to the two extensions the recorder ever writes,
and it answers range requests — so you can seek without loading eighty megabytes
first.

### The recording captures the stage, not the tab

The screen recorder captured the whole browser tab. What came out was a
window-shaped picture with the portrait stage sitting somewhere inside it — the
reel's crop only came into being later, at cutting time, and until then nobody
knew exactly what would end up in frame. That is precisely the failure the fixed
stage was built against.

The browser can do this itself: **Region Capture** crops a self-capture down to
one element. Two conditions come with it, and both are now met — the capture has
to be the page's own tab (so the page asks differently), and the crop has to be
in place **before** the first frame is recorded; the shared recording logic now
waits for the page, between building the recorder and starting it. After that the
file *is* the stage — nothing left to crop.

What this does **not** change is resolution: the crop happens in the pixels the
tab actually has. A stage scaled down to 527×937 yields 527×937, and the pill at
the top still says so. Anyone who wants true 1080×1920 makes the window tall
enough.

And the cut list now distinguishes **three** cases instead of two: already
cropped, computable afterwards, or position unknown (a full-screen capture). The
first two both yield no `ffmpeg` line — conflating them would mean writing "no
crop" under a perfectly cropped reel. If a browser cannot do region capture, the
page says so and falls back to the computed crop.

## The tool is the yardstick, not the object

Target-value optimisation raises an uncomfortable question: what stops the agent from
editing the source until the number comes out right? The heads are coding agents with
write access to this directory, and the browser path asks for no permission. The honest
answer is that it **cannot be prevented.** The agent runs as the same user, without a
sandbox; whoever owns a file may write it, and a `chmod` back costs one line. A lock you
can open from the inside is not a lock, it is a claim.

Hiding it, however, can be prevented, and that is what this comes down to. A fingerprint
over the twelve modules whose change moves a figure travels with every stored
calculation, every line of the project log, and the Steckbrief — and when several states
show up there, the Steckbrief says outright that those figures are not readily
comparable. If one of those files changes **while** an agent is running, it appears
immediately as an amber 🔧 lamp in the work row and as a line in that run's transcript,
which is to say exactly when somebody is already watching.

Next to it, the rule in plain words — in `AGENTS.md`, in `SKILL.md`, and in every one of
the three heads' standing orders: a goal is reached through geometry, material and
operating point, never through a limit moved in the source. If you believe the tool
itself is wrong, you write a **finding** into `cae_orchestrator/BEFUNDE.md` (what was
observed, where it was measured, which line) instead of repairing it silently —
otherwise the figures before and after the repair come from two different tools, and
nothing about them says so.

The **target-value search itself** needs none of this: there the model only proposes
parameter vectors, they are clamped to their ranges, and every infeasible solution ranks
below every feasible one. The source is out of its reach. What is exposed is the route an
agent takes by hand.

## A no is also a good answer

The occasion was a 230 V fan drive. It could not be computed — and instead of saying so,
the model produced numbers: 0.0 Nm of torque and, next to it, a loss of **2.8·10²⁰ W**.
Anyone reading that goes looking for an arithmetic error. The finding was "different
machine class" all along; there was simply no place for it to be stated.

The cause is a chain of three stages, each unremarkable on its own, and it is written up
with every measurement and line reference in `cae_orchestrator/BEFUNDE.md`. The core: to
magnetise at all this machine needs 1686 A against an inverter limit of 800 A, so no
torque-producing current is left — and the loss term divided by that current with a floor
of 10⁻⁹. A division by almost nothing is not a result; it is the point at which the
calculation should have stopped.

Now the operating point first decides whether it **exists**. Below a thousandth of the
current limit no number comes back, but `reachable: no` with a reason naming both
currents and the adjustable knob; torque, slip and losses are then explicitly **empty and
not 0.0** — a zero reads like a computed result, and that is exactly how it was read. The
cage no longer falls back silently to its manufacturing floor, and the 2-D field stage
refuses to mesh a rotor from it rather than spending half an hour on a machine that does
not exist.

### Should answers be weighted?

Yes — but not with a confidence number. That would be one more invented quantity. What
makes a figure weighable are two statements, and both were already half there: its
**provenance** (which method produced it — that has been on every figure in the
Steckbrief from the start) and its **domain of validity** (does this case sit in the
class this chain is calibrated for).

The domain is explicitly **not a gate**: outside does not mean wrong, it means "this
chain is not calibrated for that, and none of the computed designs sits there". Three
statements, each measured rather than asserted: whether an inverter was set at all or the
traction default of 800 V / 800 A applies (in which case every current statement is a
statement about that ceiling); whether the machine needs more magnetisation than this
class provides — **direct mains operation without a converter is not modelled**, and that
now stands there verbatim; and whether the power falls inside the band actually computed
here (read out of the database: 0.2 to 419 kW from 57 runs).

The Steckbrief, `sicherheit` and `beitrag` all carry it. Which makes "not representable,
because the model has no mains operation" a complete answer — not a failure.

## Instagram and X posts — out of what was actually computed

The Studio tab's second job, and a verb so the agent can use the same tool:

```bash
python3 cae_orchestrator/cae_cli.py beitrag x --from-project last
python3 cae_orchestrator/cae_cli.py beitrag instagram --from-project last --ton begeistert
```

The material comes from the project's **Steckbrief**, not from the conversation. That
difference is the whole point: the Steckbrief knows which stage produced which figure and
what is missing, whereas a post written from the chat log inherits every number the agent
estimated along the way — and **publishes it**.

For the same reason "no figure without cover in the material" is not left to the prompt:
every number in the draft is **measured back** against the material afterwards and
reported as a warning when it isn't there. Rounding is covered (0.7994 → 0.80); inventing
is not. Asking a language model nicely is not a guarantee.

What a draft carries: text in the channel's shape (X 280 characters per post, thread of up
to three — and **too long means wrapping, not truncating**; in the first real run part 1
ended at 274 of 280 characters with "Achtung: Sicherheitskriterien…", so the one caveat
worth reading fell off the end), hashtags, an image selection with alt texts, a
**provenance footer** saying which figure came from which stage — and, if a screen
recording was running, cut suggestions from its marks with a ready `ffmpeg` line. It shows
the line; it does not run it.

**Nothing is published.** There is no path out, no credentials and no button for it. The
draft is filed under `<project>/beitraege/` and in the project's stored calculations;
copying and posting is done by hand.

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
