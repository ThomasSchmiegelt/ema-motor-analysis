"""🧪 Spray-Test-Prüfstand: iteratives Spray-Tuning (Mensch wählt, Evolution mutiert).

Eigenständiger On-Demand-Pfad neben der Spritzöl-Kühlung (`ema_oilspray`). Statt des
teuren Motor-Ausschnitts (FreeCAD-STL + große Domain) simuliert ein **einfacher
Prüfstand** nur das Spray selbst: EINE Düse sprüht **horizontal** (Strahl entlang +x,
Schwerkraft −z) als Freistrahl — standardmäßig ist NUR das Spray zu sehen (Kamera
nah am Strahl); die drei vertikalen Kupferstäbe (Hairpin-Stellvertreter) sind per
``show_rods`` optional zuschaltbar. Pro Runde
werden ~10 Parameter-Varianten gebacken und als kurze Loop-Videos gezeigt; der Nutzer
markiert die besten, die nächste Runde sampelt Kinder **um die markierten Eltern**
(Kreuzung + Gauß-Mutation, Streuung schrumpft je Runde) — bis das Spray passt und die
Sieger-Parameter in den echten 💧-Tab übernommen werden.

Variiert wird NUR die Spray-Physik (`SPRAY_PARAMS`): Druck, Sprühkegel,
Oberflächenspannung, Viskosität, Düsen-Ø. Auflösung (frei bis 512), Frames und
Zeitlupe sind je RUNDE einstellbar und gelten für alle Kacheln (Vergleichbarkeit);
`run_beauty` rendert eine einzelne Variante hochauflösend nach (✨).

Persistenz global unter ``~/cae_projekte/_spraytest/rounds/<rid>/`` (projektunabhängig,
analog `_variants`/`_training`): je Runde ein Ordner mit ``round.json`` + je Kind-
Variante ``v<i>/`` (eigenes ``frames/``+``anim.mp4``) — Eltern werden NICHT neu
gebacken, ihr Video wird aus der Altrunde referenziert.
"""

import json
import math
import os
import random
import shutil
import time
import uuid

import blender_runner

SPRAYTEST_ROOT = os.path.expanduser("~/cae_projekte/_spraytest")
ROUNDS_SUBDIR = "rounds"

# ── Parameter-Raum ───────────────────────────────────────────────────────────
# Die 5 Haupthebel für Tropfenbildung/Strahlform (s. Diskussion der Einflussgrößen).
# log=True ⇒ Sampling/Mutation im log-Raum (Größenordnungs-Parameter). Viskositäts-
# Bereich kreuzt bewusst die 0.02-Schwelle, ab der der Mantaflow-Viskositätslöser
# aktiv wird (darunter reibungsarm-dünnflüssig, darüber zunehmend zäh/gelartig).
# Druck 0,1–3 bar und Düsen-Ø 0,5–1,5 mm sind die physikalischen Grenzen der realen
# Öl-Anlage (Nutzer-Vorgabe) — Sampling/Mutation/Klemmung bleiben immer darin.
SPRAY_PARAMS = {
    "pressure_bar":    {"lo": 0.1,   "hi": 3.0,  "log": False, "label": "Druck",              "unit": "bar", "fmt": "%.1f"},
    "jet_cone_deg":    {"lo": 0.0,   "hi": 30.0, "log": False, "label": "Sprühkegel",         "unit": "°",   "fmt": "%.0f"},
    "surface_tension": {"lo": 0.002, "hi": 0.05, "log": True,  "label": "Oberflächenspannung","unit": "",    "fmt": "%.4f"},
    "viscosity":       {"lo": 0.001, "hi": 0.08, "log": True,  "label": "Viskosität",         "unit": "",    "fmt": "%.4f"},
    "nozzle_d_mm":     {"lo": 0.5,   "hi": 1.5,  "log": False, "label": "Düsen-Ø",            "unit": "mm",  "fmt": "%.1f"},
}
PARAM_ORDER = list(SPRAY_PARAMS)

# Anker-Variante = die aktuellen Defaults des echten Öl-Laufs (ema_oilspray).
DEFAULT_PARAMS = {"pressure_bar": 3.0, "jet_cone_deg": 10.0,
                  "surface_tension": 0.01, "viscosity": 0.004, "nozzle_d_mm": 1.0}

# Feste Sim-/Render-Einstellungen (Vergleichbarkeit der Kacheln). `quality` skaliert
# nur die Domain-Auflösung und gilt für die GANZE Runde; eine freie Auflösung
# (`spec["resolution"]` > 0) überschreibt das Preset (Kosten ~kubisch!).
QUALITY_RES = {"schnell": 48, "normal": 64, "fein": 96}
DEFAULT_QUALITY = "normal"
RES_RANGE = (32, 512)            # freie Domain-Auflösung (wie der 💧-Tab)
FRAMES_RANGE = (24, 120)
BENCH_FRAMES = 44
BENCH_FPS = 24
SLOWMO_RANGE = (1.0, 50.0)       # Zeitlupe je Runde: time_scale = 1/slowmo
DEFAULT_SLOWMO = 3.0             # ≈ das alte feste time_scale 0.35
N_RANGE = (1, 12)                # n=1 ⇒ Einzel-Strahl (eine Kachel)
DEFAULT_N = 10
# ✨ Schönheits-Render (eine Variante einzeln, hochauflösend, größeres Bild)
BEAUTY_RES = 256
BEAUTY_FRAMES = 60
BEAUTY_RENDER_PX = [1280, 960]

# Dedup-Schwelle im normierten Parameterraum (euklidisch): zu ähnliche Kinder werden
# neu gewürfelt (sonst verschenkt eine Kachel Rechenzeit für ein Quasi-Duplikat).
DEDUP_DIST = 0.02
MUT_SIGMA0 = 0.25                # Mutations-σ in Runde 2, schrumpft ×0.7 je Runde


def _rounds_dir():
    return os.path.join(SPRAYTEST_ROOT, ROUNDS_SUBDIR)


# ── Normierung / Sampling ────────────────────────────────────────────────────
def _norm(key, val):
    """Parameterwert → [0..1] (log-Params im log-Raum)."""
    p = SPRAY_PARAMS[key]
    lo, hi = p["lo"], p["hi"]
    v = max(lo, min(hi, float(val)))
    if p["log"]:
        return (math.log(v) - math.log(lo)) / (math.log(hi) - math.log(lo))
    return (v - lo) / (hi - lo)


def _denorm(key, x):
    p = SPRAY_PARAMS[key]
    lo, hi = p["lo"], p["hi"]
    x = max(0.0, min(1.0, float(x)))
    if p["log"]:
        return math.exp(math.log(lo) + x * (math.log(hi) - math.log(lo)))
    return lo + x * (hi - lo)


def _clean_params(params):
    """Nur bekannte Keys, auf die Bereiche geklemmt; fehlende mit Default aufgefüllt."""
    out = {}
    for k in PARAM_ORDER:
        try:
            v = float((params or {}).get(k, DEFAULT_PARAMS[k]))
        except (TypeError, ValueError):
            v = DEFAULT_PARAMS[k]
        out[k] = max(SPRAY_PARAMS[k]["lo"], min(SPRAY_PARAMS[k]["hi"], v))
    return out


def _pdist(a, b):
    """Euklidischer Abstand zweier Parametersätze im normierten Raum."""
    return math.sqrt(sum((_norm(k, a[k]) - _norm(k, b[k])) ** 2 for k in PARAM_ORDER))


def sample_round(parents, n, round_no, rng=None):
    """Erzeugt die n KIND-Parametersätze einer Runde (Eltern werden nicht neu gebacken).

    Runde 1 (keine Eltern): Kind 0 = ``DEFAULT_PARAMS`` als Anker, der Rest quasi-
    gleichmäßig über die Bereiche gestreut (stratifiziert je Parameter + unabhängige
    Permutation = Latin-Hypercube-artig). Runde ≥2: je Kind zwei zufällige Eltern →
    Parameter-weise Kreuzung → Gauß-Mutation im normierten Raum, σ schrumpft je Runde;
    Kinder, die einem Elter/Geschwister zu ähnlich sind, werden neu gewürfelt."""
    rng = rng or random.Random()
    n = max(1, int(n))
    parents = [_clean_params(p) for p in (parents or [])]
    kids = []

    if not parents:
        kids.append(dict(DEFAULT_PARAMS))
        m = n - 1
        if m > 0:
            cols = {}
            for k in PARAM_ORDER:
                vals = [(i + rng.random()) / m for i in range(m)]
                rng.shuffle(vals)                      # je Parameter eigene Permutation
                cols[k] = vals
            for i in range(m):
                kids.append({k: _denorm(k, cols[k][i]) for k in PARAM_ORDER})
        return kids[:n]

    sigma = MUT_SIGMA0 * (0.7 ** max(0, int(round_no) - 2))
    taken = list(parents)
    for _ in range(n):
        child = None
        for _try in range(40):
            pa = rng.choice(parents)
            pb = rng.choice(parents)                   # darf == pa sein (dann reine Mutation)
            cand = {}
            for k in PARAM_ORDER:
                base = _norm(k, pa[k] if rng.random() < 0.5 else pb[k])
                cand[k] = _denorm(k, base + rng.gauss(0.0, sigma))
            if all(_pdist(cand, t) >= DEDUP_DIST for t in taken):
                child = cand
                break
        if child is None:
            child = cand                               # nach 40 Versuchen akzeptieren
        taken.append(child)
        kids.append(child)
    return kids


def format_params(params):
    """Kompakte Anzeige-Zeile für eine Kachel, z. B. '3.0 bar · 10° · σ 0.0100 · ν 0.0040 · Ø 1.0 mm'."""
    p = _clean_params(params)
    return " · ".join([
        ("%.1f bar" % p["pressure_bar"]),
        ("%.0f°" % p["jet_cone_deg"]),
        ("σ %.4f" % p["surface_tension"]),
        ("ν %.4f" % p["viscosity"]),
        ("Ø %.1f mm" % p["nozzle_d_mm"]),
    ])


# ──────────────────────────────────────────────────────────────────────────────
# Blender-Prüfstand-Skript (läuft IN Blender) — bewusst ein EIGENES, kleines
# Template statt des Motor-Skripts aus ema_oilspray: keine STL, feste Kamera/Licht,
# nur Düse + 3 Kupferstäbe. Bewährte Bausteine (Engine-Auflösung, Viskositäts-
# Schwelle, offene Ränder, Öl-Material, Marker) sind von dort übernommen.
# ──────────────────────────────────────────────────────────────────────────────
_BENCH_SCRIPT = r'''
import bpy, sys, os, json, math, mathutils

_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CFG = json.load(open(_argv[0]))

def log(msg): print("OIL_STAGE:" + str(msg), flush=True)

def _set(obj, name, val):
    try:
        if hasattr(obj, name):
            setattr(obj, name, val)
            return True
    except Exception as e:
        print("OIL_STAGE:warn set %s: %s" % (name, e), flush=True)
    return False

FRAMES_DIR = CFG["frames_dir"]
RES     = int(CFG.get("resolution", 64))
F0, F1  = 1, int(CFG.get("frames", 44))
VISC    = float(CFG.get("viscosity", 0.004))
SURFT   = float(CFG.get("surface_tension", 0.01))
PRESSURE_BAR = float(CFG.get("pressure_bar", 3.0))
CONE    = math.radians(max(0.0, min(40.0, float(CFG.get("jet_cone_deg", 10.0)))))
NOZ_D   = float(CFG.get("nozzle_d_mm", 1.0)) * 0.001      # [m]
TIME_SCALE = max(0.001, min(1.0, float(CFG.get("time_scale", 0.35))))
SHOW_RODS = bool(CFG.get("show_rods", False))
RENDER_PX = CFG.get("render_px") or [640, 480]
ENGINE  = CFG.get("engine", "BLENDER_EEVEE")
RHO_OIL = 850.0
JET_V   = 0.8 * math.sqrt(2.0 * PRESSURE_BAR * 1e5 / RHO_OIL)   # Bernoulli wie im Motor-Skript
os.makedirs(FRAMES_DIR, exist_ok=True)
CACHE_DIR = os.path.join(os.path.dirname(FRAMES_DIR), "blendcache_bench")
os.makedirs(CACHE_DIR, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- Prüfstand-Geometrie (Meter): Düse bei x=0, Strahl HORIZONTAL → +x, Schwerkraft −z.
# Standard: FREISTRAHL ohne Ziele — "nur das Spray sehen". Optional (SHOW_RODS):
# 3 vertikale Kupferstäbe Ø 6 mm bei x=25 mm (Hairpin-Stellvertreter) als Aufprallziele.
ROD_X   = 0.025
ROD_D   = 0.006
ROD_H   = 0.05

def _mk_mat(name, rgb, metal, rough, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        if "Metallic" in b.inputs:  b.inputs["Metallic"].default_value = metal
        if "Roughness" in b.inputs: b.inputs["Roughness"].default_value = rough
        for _sn in ("Specular IOR Level", "Specular"):
            if _sn in b.inputs: b.inputs[_sn].default_value = spec
    return m

_mat_copper = _mk_mat("Kupfer", (0.74, 0.35, 0.12), 1.0, 0.34)
_mat_steel  = _mk_mat("Stahl", (0.55, 0.57, 0.60), 0.95, 0.35)

# Kupferstäbe (Effector = Kollision) — nur wenn gewünscht; ohne sie fliegt der
# Freistrahl ungestört durch die offene Domain (reine Strahl-/Tropfen-Beurteilung).
rods = []
for i, ry in (enumerate((-0.008, 0.0, 0.008)) if SHOW_RODS else []):
    bpy.ops.mesh.primitive_cylinder_add(radius=0.5 * ROD_D, depth=ROD_H,
                                        location=(ROD_X, ry, -0.010))
    rod = bpy.context.object; rod.name = "Rod_%d" % i
    rod.data.materials.append(_mat_copper)
    bpy.ops.object.shade_smooth()
    bpy.context.view_layer.objects.active = rod
    bpy.ops.object.modifier_add(type='FLUID')
    mr = rod.modifiers[-1]; mr.fluid_type = 'EFFECTOR'
    _set(mr.effector_settings, "effector_type", "COLLISION")
    _set(mr.effector_settings, "use_effector", True)
    rods.append(rod)

# Düsenstutzen (sichtbar, Stahl) — Zylinder entlang x, Mündung bei x=0.
stub_len = 0.008
bpy.ops.mesh.primitive_cylinder_add(radius=max(0.0012, 1.2 * 0.5 * NOZ_D),
                                    depth=stub_len, location=(-0.5 * stub_len, 0.0, 0.0))
stub = bpy.context.object; stub.name = "Nozzle"
stub.rotation_euler = (0.0, math.pi / 2.0, 0.0)
stub.data.materials.append(_mat_steel)
bpy.ops.object.shade_smooth()

# --- Domain (LIQUID/FLIP), offene Ränder, Boden-Outflow ------------------------
log("Domain aufsetzen (Auflösung %d)" % RES)
Dxmin, Dxmax = -0.012, 0.075
Dymin, Dymax = -0.035, 0.035
Dzmin, Dzmax = -0.055, 0.022
dcx, dcy, dcz = (Dxmin+Dxmax)/2, (Dymin+Dymax)/2, (Dzmin+Dzmax)/2
sx, sy, sz = (Dxmax-Dxmin)/2, (Dymax-Dymin)/2, (Dzmax-Dzmin)/2
voxel = (2.0 * max(sx, sy, sz)) / max(1, RES)
bpy.ops.mesh.primitive_cube_add(location=(dcx, dcy, dcz))
dom = bpy.context.object; dom.name = "Domain"
dom.scale = (sx, sy, sz)
bpy.context.view_layer.objects.active = dom
bpy.ops.object.modifier_add(type='FLUID')
md = dom.modifiers[-1]; md.fluid_type = 'DOMAIN'
ds = md.domain_settings
_set(ds, "domain_type", "LIQUID")
_set(ds, "resolution_max", RES)
_set(ds, "simulation_method", "FLIP")
_set(ds, "use_mesh", True)
_set(ds, "use_flip_particles", True)
# Sekundärpartikel (Spray/Foam/Bubble) BEWUSST AUS — in diesem Blender-4.2-Build
# kaputt (ausgiebig verifiziert): ohne resumable Cache werden schlicht NULL Partikel
# erzeugt (leere particles-Cache-Dateien), MIT resumable Cache laden sie als
# domänenfüllender Staub (Positionen über den ganzen Quader statt an der
# Flüssigkeit). Die sichtbaren Tröpfchen kommen stattdessen aus dem FEINEN
# Upres-Flüssigkeitsmesh (mesh_scale=2 + mesh_particle_radius 1.4, s. u.) —
# verifiziert: einzelne fliegende Tropfen statt Klumpen.
_set(ds, "use_spray_particles", False)
_set(ds, "use_foam_particles", False)
_set(ds, "use_bubble_particles", False)
# Viskositätslöser nur bei zähem Öl (>0.02) — wie im Motor-Skript: ein aktiver Löser
# macht selbst kleine Werte gelartig (dünnes Öl soll reibungsarm spritzen).
if VISC > 0.02:
    _set(ds, "use_viscosity", True)
    if not _set(ds, "viscosity_value", VISC):
        _set(ds, "viscosity_base", VISC)
else:
    _set(ds, "use_viscosity", False)
_set(ds, "use_diffusion", True)
_set(ds, "surface_tension", SURFT)
_set(ds, "cache_type", "ALL")
_set(ds, "cache_directory", CACHE_DIR)
_set(ds, "cache_frame_start", F0)
_set(ds, "cache_frame_end", F1)
for _b in ("use_collision_border_front", "use_collision_border_back",
           "use_collision_border_right", "use_collision_border_left",
           "use_collision_border_top", "use_collision_border_bottom"):
    _set(ds, _b, False)
# Substeps skalieren mit der Auflösung (Anti-Tunneling des schnellen Strahls bei
# hoher Auflösung; CFL bleibt adaptiv, grobe Läufe bleiben so schnell wie bisher).
_set(ds, "timesteps_max", int(CFG.get("substeps_max") or max(8, RES // 24)))
_set(ds, "timesteps_min", 1)
_set(ds, "cfl_condition", 3.0)
_set(ds, "use_adaptive_timesteps", True)
_set(ds, "time_scale", TIME_SCALE)

# --- Realismus: feines Flüssigkeits-Mesh + saubere Kollision ---------------------
# Default mesh_particle_radius=2.0 machte dicke Blobs; mesh_scale=2 (Upres) erzeugt
# das SICHTBARE Mesh auf 2× Sim-Auflösung — großer optischer Gewinn bei GROBEN Domains.
# Bei hoher Auflösung MUSS der Upres aus: 512er-Domain + Upres ⇒ 1024³-Mesh-Gitter ⇒
# >28 GB RSS ⇒ der Kernel OOM-killt Blender (real passiert auf dieser 31-GiB-Maschine);
# ab ~192 ist die Sim selbst fein genug, das Mesh braucht keine Verdopplung mehr.
_set(ds, "mesh_particle_radius", 1.4)
_set(ds, "mesh_scale", 2 if RES < 192 else 1)
_set(ds, "mesh_generator", 'IMPROVED')
_set(ds, "mesh_smoothen_pos", 1)
_set(ds, "use_fractions", True)          # glatte statt voxel-treppige Stab-Kollision
_set(ds, "fractions_distance", voxel)

# --- Düse (INFLOW): Emitter an der Stutzen-Mündung, Strahl horizontal +x ------
# 1.6·voxel statt 1.2: bei Prüfstand-Auflösung 48–96 ist der 1-mm-Strahl sonst sub-voxel
# und der FREISTRAHL zwischen Düse und Stab bleibt als Flüssigkeitsmesh unsichtbar
# (nur der Aufprall-Splash war zu sehen — verifiziert im ersten Testlauf).
emit_s = max(0.5 * NOZ_D, 1.6 * voxel)

# --- Unter-Auflösungs-Wächter (analog zum Leer-Bake-Wächter) -------------------
# Ist die Bohrung < ~2 Zellen breit, bleibt der Freistrahl als Flüssigkeitsmesh unsichtbar
# (nur der Aufprall-Splash war zu sehen). Früh + laut warnen; Kennwerte tragen die Zahlen mit.
_jet_cells = NOZ_D / max(1e-9, voxel)                    # Bohrungs-Ø / Zellgröße
_voxel_mm  = voxel * 1000.0
_jet_underres = _jet_cells < 2.0
if _jet_underres:
    print("OIL_STAGE:⚠ Strahl unter-aufgelöst — die %.2f-mm-Bohrung ist bei Auflösung %d nur "
          "~%.1f Zellen breit (Voxel %.2f mm). Der Freistrahl wird kaum sichtbar (nur der "
          "Aufprall-Splash). Abhilfe: Auflösung erhöhen." % (NOZ_D * 1000.0, RES, _jet_cells,
          _voxel_mm), flush=True)

bpy.ops.mesh.primitive_cube_add(location=(0.5 * emit_s, 0.0, 0.0))
jt = bpy.context.object; jt.name = "OilNozzle"
jt.scale = (emit_s, emit_s, emit_s)
bpy.context.view_layer.objects.active = jt
bpy.ops.object.modifier_add(type='FLUID')
mj = jt.modifiers[-1]; mj.fluid_type = 'FLOW'
fs = mj.flow_settings
_set(fs, "flow_type", "LIQUID")
_set(fs, "flow_behavior", "INFLOW")
_set(fs, "use_initial_velocity", True)
_set(fs, "velocity_coord", [JET_V, 0.0, 0.0])
_set(fs, "velocity_random", JET_V * math.sin(CONE))  # Sprühfächer (Kegelöffnung)
_set(fs, "use_inflow", True)
_set(fs, "subframes", 3)
jt.hide_render = True

# Boden-Outflow (−z): Öl wird unten abgeführt, staut sich nicht auf.
bpy.ops.mesh.primitive_cube_add(location=(dcx, dcy, Dzmin + 0.04 * (Dzmax - Dzmin)))
drain = bpy.context.object; drain.name = "OilDrain"
drain.scale = (sx * 0.98, sy * 0.98, 0.03 * (Dzmax - Dzmin) + 0.002)
bpy.context.view_layer.objects.active = drain
bpy.ops.object.modifier_add(type='FLUID')
mo = drain.modifiers[-1]; mo.fluid_type = 'FLOW'
fo = mo.flow_settings
_set(fo, "flow_type", "LIQUID")
_set(fo, "flow_behavior", "OUTFLOW")
_set(fo, "use_inflow", False)
drain.hide_render = True

# --- Bake ----------------------------------------------------------------------
scene.frame_start = F0; scene.frame_end = F1
scene.gravity = (0.0, 0.0, -9.81)                    # horizontal sprühen, Schwerkraft nach unten
bpy.context.view_layer.objects.active = dom
for o in bpy.context.selected_objects: o.select_set(False)
dom.select_set(True)
log("Bake läuft (Prüfstand)")
try:
    with bpy.context.temp_override(active_object=dom, object=dom, selected_objects=[dom]):
        bpy.ops.fluid.bake_all()
except Exception as e:
    print("OIL_STAGE:bake_all override fehlgeschlagen (%s), direkt" % e, flush=True)
    bpy.ops.fluid.bake_all()
log("Bake fertig")

# --- Render-Setup ----------------------------------------------------------------
_eng_items = [i.identifier for i in scene.render.bl_rna.properties['engine'].enum_items]
def _pick_engine(req):
    if req in _eng_items:
        return req
    for cand in ('BLENDER_EEVEE_NEXT', 'BLENDER_EEVEE', 'CYCLES', 'BLENDER_WORKBENCH'):
        if cand in _eng_items:
            return cand
    return _eng_items[0]
ENGINE = _pick_engine(ENGINE)
log("Render vorbereiten (%s)" % ENGINE)
scene.render.engine = ENGINE
scene.render.resolution_x = int(RENDER_PX[0])
scene.render.resolution_y = int(RENDER_PX[1])
scene.render.image_settings.file_format = 'PNG'
try:
    _vt = [i.identifier for i in scene.view_settings.bl_rna.properties['view_transform'].enum_items]
    for _cand in ('AgX', 'Filmic', 'Standard'):
        if _cand in _vt:
            scene.view_settings.view_transform = _cand
            break
except Exception:
    pass

world = bpy.data.worlds.new("BenchWorld"); scene.world = world
world.use_nodes = True
_bg = world.node_tree.nodes.get("Background")
if _bg:
    _bg.inputs[0].default_value = (0.05, 0.06, 0.08, 1.0)
    _bg.inputs[1].default_value = 0.9

# Kamera: 3/4-Ansicht (seitlich + leicht diagonal), Strahl läuft im Bild nach rechts,
# Tropfen fallen nach unten. Mit Stäben die weitere Übersicht (NICHT exakt entlang −y —
# die 3 Stäbe stehen in y-Reihe und verdeckten sich sonst gegenseitig); OHNE Stäbe
# ("nur das Spray") eine NAHAUFNAHME auf Düsenmündung + Freistrahl.
if SHOW_RODS:
    cam_tgt = mathutils.Vector((0.022, 0.0, -0.014))
    cam_loc = (cam_tgt.x + 0.05, 0.105, cam_tgt.z + 0.04)
    cam_lens = 45.0
else:
    cam_tgt = mathutils.Vector((0.019, 0.0, -0.006))
    cam_loc = (cam_tgt.x + 0.030, 0.062, cam_tgt.z + 0.020)
    cam_lens = 50.0
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.object
cam.rotation_euler = (cam_tgt - cam.location).to_track_quat('-Z', 'Z').to_euler()
if cam.data:
    cam.data.lens = cam_lens
    # Near-Clip! Blender-Default 0.1 m — die Nahaufnahme steht nur ~0.07 m vom Ziel,
    # damit läge die GANZE Szene vor der Clip-Ebene und das Bild bliebe leer.
    cam.data.clip_start = 0.001
    cam.data.clip_end = 10.0
scene.camera = cam

bpy.ops.object.light_add(type='SUN', location=(0.05, 0.08, 0.15))
_sun = bpy.context.object; _sun.data.energy = 2.4
_sun.rotation_euler = (0.6, 0.15, 0.3)
bpy.ops.object.light_add(type='AREA', location=(cam_tgt.x + 0.05, 0.09, 0.06))
_fill = bpy.context.object
_fill.data.size = 0.12; _fill.data.energy = 18.0
_fill.rotation_euler = (cam_tgt - _fill.location).to_track_quat('-Z', 'Z').to_euler()

# Öl-Material (transluzent bernsteinfarben) auf die Liquid-Mesh (Domain-Objekt).
oil = bpy.data.materials.new("Oil"); oil.use_nodes = True
bsdf = oil.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.55, 0.35, 0.08, 1.0)
    if "Roughness" in bsdf.inputs: bsdf.inputs["Roughness"].default_value = 0.12
    if "IOR" in bsdf.inputs: bsdf.inputs["IOR"].default_value = 1.47
    for tname in ("Transmission", "Transmission Weight"):
        if tname in bsdf.inputs:
            bsdf.inputs[tname].default_value = 0.45
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = 0.75
try:
    oil.use_screen_refraction = True
    if hasattr(oil, "blend_method"): oil.blend_method = 'BLEND'
    ee = getattr(scene, "eevee", None)
    if ee is not None:
        for _f in ("use_ssr", "use_ssr_refraction", "use_raytracing"):
            if hasattr(ee, _f): setattr(ee, _f, True)
except Exception:
    pass
dom.data.materials.append(oil)

# --- Frames rendern + Fragment-Zählung (Tropfen-Proxy) --------------------------
def _islands():
    dg = bpy.context.evaluated_depsgraph_get()
    de = dom.evaluated_get(dg)
    me = de.to_mesh()
    import bmesh
    bm = bmesh.new(); bm.from_mesh(me)
    seen = set(); n = 0
    bm.verts.ensure_lookup_table()
    for sv in bm.verts:
        if sv.index in seen: continue
        n += 1; stack = [sv]; seen.add(sv.index)
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in seen:
                    seen.add(o.index); stack.append(o)
    nv = len(me.vertices)
    bm.free(); de.to_mesh_clear()
    return n, nv

series = []
log("Frames rendern")
_liquid_total = 0
for fr in range(F0, F1 + 1):
    scene.frame_set(fr)
    # Fluid-Mesh ZUERST auswerten: leerer Bake-Frame → Domain ausblenden, sonst rendert Blender
    # die nackte Domain-Würfel-Mesh (Öl-Material) = „großer Quader statt Spray".
    try:
        n_isl, n_verts = _islands()
    except Exception:
        n_isl, n_verts = 0, 0
    dom.hide_render = (n_verts == 0)
    _liquid_total += n_verts
    scene.render.filepath = os.path.join(FRAMES_DIR, "frame_%04d.png" % (fr - F0 + 1))
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        print("OIL_STAGE:render frame %d fehlgeschlagen: %s" % (fr, e), flush=True)
    series.append({"frame": fr, "n_islands": int(n_isl), "n_liquid_verts": int(n_verts)})
    print("OIL_FRAMES:%d/%d" % (fr - F0 + 1, F1 - F0 + 1), flush=True)
dom.hide_render = False
if _liquid_total == 0:
    print("OIL_STAGE:⚠ Bake hat KEIN Öl erzeugt (0 Fluid-Vertices in allen Frames) — "
          "Domain ausgeblendet. Prüfe Auflösung und ob der Bake durchlief.", flush=True)

out = {"series": series,
       "droplets_peak": max((s["n_islands"] for s in series), default=0),
       "n_frames": len(series),
       "jet_cells": round(_jet_cells, 2),
       "voxel_mm": round(_voxel_mm, 3),
       "jet_underres": bool(_jet_underres)}
print("OIL_METRICS:" + json.dumps(out), flush=True)
print("OIL_DONE", flush=True)
'''


def _bench_script():
    return _BENCH_SCRIPT


# ──────────────────────────────────────────────────────────────────────────────
# Runden-Lauf + Persistenz
# ──────────────────────────────────────────────────────────────────────────────
def _clampf(v, lo, hi, default):
    """float-Klemmung mit Default (None/0/Unfug ⇒ default)."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return default
    if v <= 0:
        return default
    return max(lo, min(hi, v))


def _bake_variant(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10,
                  overrides=None):
    """Bäckt EINE Kind-Variante in ihr eigenes Verzeichnis (work/frames/anim.mp4).
    ``overrides`` (resolution/frames/time_scale/render_px …) überschreibt die
    Qualitäts-Defaults — genutzt von run_round (freie Auflösung, Frames, Zeitlupe)
    und run_beauty (✨ hochauflösender Einzel-Render)."""
    frames_dir = os.path.join(vdir, "frames")
    work = os.path.join(vdir, "work")
    os.makedirs(frames_dir, exist_ok=True)
    os.makedirs(work, exist_ok=True)
    cfg = dict(_clean_params(params))
    cfg.update({
        "frames_dir": frames_dir,
        "resolution": QUALITY_RES.get(quality, QUALITY_RES[DEFAULT_QUALITY]),
        "frames": BENCH_FRAMES,
        "time_scale": 1.0 / DEFAULT_SLOWMO,
        "show_rods": False,          # Standard: nur das Spray (Freistrahl, Kamera nah)
        "engine": "BLENDER_EEVEE",
    })
    cfg.update(overrides or {})
    cfg_path = os.path.join(work, "bench_cfg.json")
    with open(cfg_path, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)
    with open(os.path.join(vdir, "params.json"), "w", encoding="utf-8") as f:
        json.dump(_clean_params(params), f, indent=2)

    def _log(msg, pct):
        if progress_cb:
            progress_cb(msg, base_pct + (span_pct // 2 if pct is None else 0))

    # Timeout skaliert mit der Auflösung (Kosten ~kubisch in RES; quadratisch angesetzt
    # reicht als Budget, weil das Rendern nicht mitwächst): 96 ⇒ 30 min, 512 ⇒ Deckel 3 h.
    res_n = int(cfg.get("resolution") or 64)
    timeout = int(min(10800, max(1800, 1800 * (res_n / 96.0) ** 2)))
    res = blender_runner.run_blender_script(_bench_script(), argv=[cfg_path],
                                            cwd=work, timeout=timeout, progress_cb=_log)
    if not res.get("ok"):
        return {"ok": False, "aborted": bool(res.get("aborted")),
                "error": res.get("error") or "Blender-Fehler", "metrics": res.get("metrics")}
    import ema_em3d
    video = ema_em3d._encode_video(frames_dir, fps=BENCH_FPS)
    return {"ok": bool(video), "aborted": False,
            "error": None if video else "Video-Kodierung fehlgeschlagen",
            "metrics": res.get("metrics")}


def run_round(spec, progress_cb=None, cancel_cb=None):
    """Rechnet EINE Runde: sampelt n Kinder (um die Eltern, falls vorhanden), bäckt sie
    sequenziell (blender_runner kann nur einen Prozess), schreibt ``round.json``.
    Eltern werden NICHT gebacken — ihr Video referenziert die Altrunde. Abbruch zwischen
    Varianten (``cancel_cb``) behält die Teilrunde."""
    spec = spec or {}
    round_no = max(1, int(spec.get("round_no") or 1))
    n = max(N_RANGE[0], min(N_RANGE[1], int(spec.get("n") or DEFAULT_N)))
    quality = str(spec.get("quality") or DEFAULT_QUALITY)
    if quality not in QUALITY_RES:
        quality = DEFAULT_QUALITY
    # Freie Auflösung (>0) überschreibt das Qualitäts-Preset; Frames + Zeitlupe je Runde
    # einstellbar — alle drei gelten für die GANZE Runde (Vergleichbarkeit der Kacheln).
    res_eff = int(_clampf(spec.get("resolution"), *RES_RANGE,
                          default=QUALITY_RES[quality]))
    frames = int(_clampf(spec.get("frames"), *FRAMES_RANGE, default=BENCH_FRAMES))
    slowmo = _clampf(spec.get("slowmo"), *SLOWMO_RANGE, default=DEFAULT_SLOWMO)
    show_rods = bool(spec.get("show_rods"))
    overrides = {"resolution": res_eff, "frames": frames, "time_scale": 1.0 / slowmo,
                 "show_rods": show_rods}
    parents_in = spec.get("parents") or []

    rid = "r%03d_%s" % (round_no, time.strftime("%Y%m%d_%H%M%S"))
    rdir = os.path.join(_rounds_dir(), rid)
    os.makedirs(rdir, exist_ok=True)

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    # Eltern übernehmen (nur Referenz auf ihr existierendes Video in der Altrunde).
    variants = []
    for i, p in enumerate(parents_in):
        variants.append({
            "id": "p%d" % i,
            "params": _clean_params(p.get("params") if isinstance(p, dict) and "params" in p else p),
            "source": "parent",
            "src_round": (p.get("src_round") if isinstance(p, dict) else None),
            "src_vid": (p.get("src_vid") if isinstance(p, dict) else None),
            "ok": True,
        })

    parent_params = [v["params"] for v in variants]
    # 🎯 Einzel-Strahl: exakt DIESE Parameter einmal backen (keine Streuung/Mutation) —
    # das Ergebnis ist eine normale Runde mit einer Kachel (markierbar/✨/💾 wie immer).
    exact = spec.get("exact_params")
    if exact:
        kids = [_clean_params(exact)]
    else:
        kids = sample_round(parent_params, n, round_no)
    _log("🧪 Runde %d: %d %s backen (Auflösung %d, %d Frames, Zeitlupe %.0f×)"
         % (round_no, len(kids), "Einzel-Strahl" if exact else "Kinder",
            res_eff, frames, slowmo), 2)

    aborted = False
    for i, params in enumerate(kids):
        if cancel_cb and cancel_cb():
            aborted = True
            _log("⛔ Abbruch — %d/%d Varianten fertig (Teilrunde bleibt)" % (i, len(kids)), None)
            break
        vid = "v%d" % i
        vdir = os.path.join(rdir, vid)
        base_pct = 2 + int(96.0 * i / max(1, len(kids)))
        _log("💧 Variante %d/%d: %s" % (i + 1, len(kids), format_params(params)), base_pct)
        r = _bake_variant(params, vdir, quality, progress_cb=progress_cb,
                          base_pct=base_pct, span_pct=int(96.0 / max(1, len(kids))),
                          overrides=overrides)
        met = r.get("metrics") or {}
        variants.append({"id": vid, "params": _clean_params(params), "source": "child",
                         "ok": bool(r.get("ok")), "error": r.get("error"),
                         "droplets_peak": met.get("droplets_peak"),
                         "series": met.get("series")})
        if r.get("aborted"):
            aborted = True
            _log("⛔ Abbruch während Variante %d — Teilrunde bleibt" % (i + 1), None)
            break

    round_data = {"rid": rid, "round_no": round_no, "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
                  "quality": quality, "resolution": res_eff, "frames": frames,
                  "slowmo": slowmo, "show_rods": show_rods, "n": n, "aborted": aborted,
                  "variants": variants, "marked": []}
    _write_round(rid, round_data)
    _log("✅ Runde %d gespeichert (%s)" % (round_no, rid), 100)
    return round_data


def run_beauty(rid, vid, opts=None, progress_cb=None, cancel_cb=None):
    """✨ Schönheits-Render: EINE Variante einer Runde einzeln neu backen — höhere
    Domain-Auflösung + größeres Renderbild — nach ``<rid>/<vid>/beauty/``. Die
    Runden-Kacheln bleiben unangetastet; ``round.json`` markiert die Variante mit
    ``beauty: true`` (die UI schaltet die Kachel dann auf das Beauty-Video um)."""
    opts = opts or {}
    data = load_round(rid)
    if not data:
        return {"ok": False, "error": "Runde nicht gefunden"}
    var = next((v for v in (data.get("variants") or []) if v.get("id") == vid), None)
    if var is None:
        return {"ok": False, "error": "Variante nicht gefunden"}
    if cancel_cb and cancel_cb():
        return {"ok": False, "aborted": True, "error": None}
    res_n = int(_clampf(opts.get("resolution"), *RES_RANGE, default=BEAUTY_RES))
    frames = int(_clampf(opts.get("frames"), *FRAMES_RANGE, default=BEAUTY_FRAMES))
    slowmo = _clampf(opts.get("slowmo"), *SLOWMO_RANGE,
                     default=float(data.get("slowmo") or DEFAULT_SLOWMO))
    if progress_cb:
        progress_cb("✨ Schönheits-Render %s: Auflösung %d, %d Frames, Zeitlupe %.0f× — %s"
                    % (vid, res_n, frames, slowmo, format_params(var.get("params"))), 2)
    vdir = os.path.join(_rounds_dir(), rid, vid, "beauty")
    r = _bake_variant(var.get("params"), vdir, data.get("quality") or DEFAULT_QUALITY,
                      progress_cb=progress_cb, base_pct=2, span_pct=96,
                      overrides={"resolution": res_n, "frames": frames,
                                 "time_scale": 1.0 / slowmo,
                                 # Stäbe wie in der Original-Runde (Vergleichbarkeit ✨↔Kachel)
                                 "show_rods": bool(opts.get("show_rods",
                                                            data.get("show_rods"))),
                                 "render_px": list(BEAUTY_RENDER_PX)})
    if r.get("ok"):
        data = load_round(rid) or data     # frisch laden (Markierungen etc. erhalten)
        for v in data.get("variants") or []:
            if v.get("id") == vid:
                v["beauty"] = True
                v["beauty_res"] = res_n
        _write_round(rid, data)
    return dict(r, rid=rid, vid=vid, beauty=bool(r.get("ok")), resolution=res_n)


# ── Runden-Store ─────────────────────────────────────────────────────────────
def _round_json(rid):
    return os.path.join(_rounds_dir(), rid, "round.json")


def _write_round(rid, data):
    path = _round_json(rid)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    os.replace(tmp, path)


def list_rounds():
    """Alle Runden, neueste zuerst: [{rid, round_no, ts, n_variants, marked}]."""
    root = _rounds_dir()
    if not os.path.isdir(root):
        return []
    out = []
    for rid in os.listdir(root):
        data = load_round(rid)
        if data:
            out.append({"rid": rid, "round_no": data.get("round_no"),
                        "ts": data.get("ts"), "quality": data.get("quality"),
                        "aborted": bool(data.get("aborted")),
                        "n_variants": len(data.get("variants") or []),
                        "marked": data.get("marked") or []})
    # Nach Zeitstempel sortieren, NICHT nach rid: die rid beginnt mit der Rundennummer,
    # eine frisch gestartete Runde 1 wäre sonst hinter einer alten Runde 2 einsortiert
    # (die UI lädt beim Öffnen rounds[0] — das muss die zuletzt gerechnete Runde sein).
    out.sort(key=lambda r: (r.get("ts") or "", r["rid"]), reverse=True)
    return out


def load_round(rid):
    try:
        with open(_round_json(rid), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def set_marked(rid, ids):
    data = load_round(rid)
    if data is None:
        return None
    known = {v["id"] for v in data.get("variants") or []}
    data["marked"] = [i for i in (ids or []) if i in known]
    _write_round(rid, data)
    return data


def delete_round(rid):
    rdir = os.path.join(_rounds_dir(), rid)
    if os.path.isdir(rdir):
        shutil.rmtree(rdir, ignore_errors=True)
        return True
    return False


# ── 💾 Spray-Favoriten (benannte Parametersätze für die echte 💧-Berechnung) ──
# Ein guter Strahl wird MIT seinen Einstellungen benannt abgespeichert und später
# im 💧-Tab in die Felder der echten Motor-Berechnung übernommen. Store global
# unter SPRAYTEST_ROOT/favorites.json (wie die Runden projektunabhängig).
def _favorites_path():
    return os.path.join(SPRAYTEST_ROOT, "favorites.json")


def list_favorites():
    try:
        with open(_favorites_path(), encoding="utf-8") as f:
            favs = json.load(f)
        return favs if isinstance(favs, list) else []
    except (OSError, ValueError):
        return []


def _write_favorites(favs):
    os.makedirs(SPRAYTEST_ROOT, exist_ok=True)
    tmp = _favorites_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(favs, f, indent=2, ensure_ascii=False)
    os.replace(tmp, _favorites_path())


def save_favorite(data):
    """Speichert einen Spray-Favoriten: {name, params, sim:{resolution,frames,slowmo},
    src:{rid,vid}}. Params werden geklemmt; Rückgabe = gespeicherter Eintrag."""
    data = data or {}
    sim = data.get("sim") or {}
    fav = {
        "id": "fav_%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), uuid.uuid4().hex[:6]),
        "name": (str(data.get("name") or "").strip() or "Spray")[:60],
        "ts": time.strftime("%Y-%m-%d %H:%M:%S"),
        "params": _clean_params(data.get("params")),
        "sim": {"resolution": int(_clampf(sim.get("resolution"), *RES_RANGE, default=QUALITY_RES[DEFAULT_QUALITY])),
                "frames": int(_clampf(sim.get("frames"), *FRAMES_RANGE, default=BENCH_FRAMES)),
                "slowmo": _clampf(sim.get("slowmo"), *SLOWMO_RANGE, default=DEFAULT_SLOWMO)},
        "src": {"rid": (data.get("src") or {}).get("rid"),
                "vid": (data.get("src") or {}).get("vid")},
    }
    favs = list_favorites()
    favs.insert(0, fav)
    _write_favorites(favs)
    return fav


def delete_favorite(fid):
    favs = list_favorites()
    keep = [f for f in favs if f.get("id") != fid]
    if len(keep) == len(favs):
        return False
    _write_favorites(keep)
    return True


def video_path(rid, vid, beauty=False):
    """Absoluter Pfad der anim.mp4 einer Variante — löst bei Eltern die Referenz auf
    die Altrunde auf (src_round/src_vid). ``beauty=True`` liefert das ✨-Video
    (``<vid>/beauty/frames/anim.mp4``; lokal zuerst, sonst Eltern-Referenz).
    None wenn nicht vorhanden."""
    data = load_round(rid)
    if not data:
        return None
    for v in data.get("variants") or []:
        if v.get("id") == vid:
            if beauty:
                p = os.path.join(_rounds_dir(), rid, vid, "beauty", "frames", "anim.mp4")
                if os.path.exists(p):
                    return p
                if v.get("source") == "parent" and v.get("src_round") and v.get("src_vid"):
                    return video_path(v["src_round"], v["src_vid"], beauty=True)
                return None
            if v.get("source") == "parent" and v.get("src_round") and v.get("src_vid"):
                return video_path(v["src_round"], v["src_vid"])
            p = os.path.join(_rounds_dir(), rid, vid, "frames", "anim.mp4")
            return p if os.path.exists(p) else None
    return None
