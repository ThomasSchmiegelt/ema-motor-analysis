"""Experimentelle **Spritzöl-Kühlung am Wickelkopf** (Blender/Mantaflow-FLIP).

Eigenständiger On-Demand-Pfad **neben** dem physikalischen Analyse-/3D-Feld-Chain. Er
untersucht **qualitativ** die Fluidkühlung eines Wickelkopf-**Ausschnitts** mit Spritzöl:
Tröpfchenbildung, Benetzung, Abtropfen. Der FLIP-Löser von Blender (Mantaflow) ist ein
**visuell-plausibler**, NICHT validierter Löser — er liefert **kein Temperaturfeld und
keinen Wärmeübergangskoeffizienten**. Die abgeleiteten „Kennwerte" sind rein **geometrische
Benetzungs-Proxys** (benetzte Fläche %, Abdeckung je Fläche, Tropfen-/Fragmentzahl über die
Zeit) — Indikatoren für Kühl-Hotspots, keine kalibrierte Kühlleistung.

Ablauf (`run_oilspray`):
  1. Wickelkopf-**Ausschnitt** als STL exportieren (`ema_freecad.build_winding_head_stl_script`
     → FreeCAD-Subprozess), Geometrie identisch zu den real generierten Hairpin-Wickelköpfen.
  2. Blender-Setup-Skript generieren (`_blender_script`) — importiert die STL als Effector,
     baut Domain (LIQUID/FLIP) + Öl-Strahl (Inflow), setzt Öl-Stoffwerte + Secondary-Particles,
     bäckt, rendert Frames, misst Benetzung/Tropfen je Frame (KDTree) → `OIL_METRICS`.
  3. Über `blender_runner.run_blender_script` headless ausführen (Fortschritt gestreamt).
  4. Frames → `anim.mp4` (ffmpeg), Kennwert-Charts (matplotlib), Persistenz nach
     `results["oilspray"]`.

Architektur analog `ema_em3d` (externes Tool, projektgebundene Persistenz, Video + Bilder).
"""

import base64
import io
import json
import os
import time

import ema_freecad
import freecad_runner
import blender_runner

DEBUG_LOG_NAME = "oilspray_debug.log"


def _dbg_path(work_dir):
    return os.path.join(work_dir, DEBUG_LOG_NAME)


def _dbg_write(work_dir, sections):
    """Schreibt/überschreibt eine Klartext-Logdatei mit den aufgelösten Einstellungen + dem
    Verlauf des Laufs (STL-Export, Blender-Stdout, Fehler) — auf Nutzerwunsch, damit ein
    fehlgeschlagener oder unerwartet aussehender Lauf 1:1 zurückgemeldet werden kann, inkl.
    aller Parameter (nicht nur der Fehlermeldung). ``sections`` = Liste von (Titel, Inhalt)."""
    try:
        os.makedirs(work_dir, exist_ok=True)
        lines = ["Spritzöl-Debug-Log — %s" % time.strftime("%Y-%m-%d %H:%M:%S")]
        for title, body in sections:
            lines.append("\n" + "=" * 10 + " " + title + " " + "=" * 10)
            if isinstance(body, str):
                lines.append(body)
            else:
                try:
                    lines.append(json.dumps(body, indent=2, default=str, ensure_ascii=False))
                except (TypeError, ValueError):
                    lines.append(str(body))
        with open(_dbg_path(work_dir), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
    except OSError:
        pass


# ── Grenzen / Defaults ───────────────────────────────────────────────────────
RES_RANGE      = (24, 512)      # Domain-Auflösung (Kostentreiber; >200 = sehr lange CPU-Bakes)
FRAMES_RANGE   = (10, 240)      # Anzahl Simulationsframes
SECTION_RANGE  = (1, 12)        # Wickelkopf-Ausschnitt (Nutenzahl)
DEFAULT_RES    = 72
DEFAULT_FRAMES = 80
DEFAULT_SECTION = 3
FRAMES_SUBDIR  = "frames_oil"

# ── Beleuchtungs-Voreinstellungen ────────────────────────────────────────────
# Ein 3-Punkt-Rig (Key-Sonne, seitlich versetztes Fülllicht, optionales Kantenlicht) statt des
# alten Ein-Fülllicht-Aufbaus. Kernfehler vorher: das Fülllicht saß GENAU an der Kameraposition
# ("Kamerablitz") — auf glänzendem Metall (Welle/Kupfer, Metallic 0.7–0.95) spiegelt eine Fläche,
# die zur Kamera zeigt, ein kameranahes Licht fast immer direkt in die Linse zurück → Stahl/Kupfer
# wirkten flach ausgebrannt weiß statt Kontur zu zeigen. Alle vier Presets versetzen das Fülllicht
# seitlich (fill_offset relativ zu cam_d/cam_tgt) und fügen ein Kantenlicht (rim) für Kontur hinzu.
LIGHT_PRESETS = {
    "studio": dict(
        label="Studio (neutral)",
        world_color=(0.05, 0.06, 0.08), world_strength=0.9,
        key_energy=2.4, key_euler=(0.6, 0.15, 0.3), key_color=(1.0, 1.0, 1.0),
        fill_energy_k=32.0, fill_energy_min=6.0, fill_size_k=1.5,
        fill_offset=(0.55, -0.85, 0.6), fill_color=(1.0, 1.0, 1.0),
        rim=True, rim_energy_k=55.0, rim_size_k=0.7,
        rim_offset=(-0.7, 0.55, 0.5), rim_color=(0.75, 0.82, 1.0),
    ),
    "werkstatt": dict(
        label="Werkstatt (warm, hart)",
        world_color=(0.07, 0.06, 0.05), world_strength=0.7,
        key_energy=3.2, key_euler=(0.75, 0.1, 0.35), key_color=(1.0, 0.93, 0.8),
        fill_energy_k=14.0, fill_energy_min=4.0, fill_size_k=1.1,
        fill_offset=(0.5, -0.7, 0.4), fill_color=(1.0, 0.95, 0.85),
        rim=False, rim_energy_k=0.0, rim_size_k=0.6,
        rim_offset=(-0.7, 0.55, 0.5), rim_color=(1.0, 0.9, 0.8),
    ),
    "weich": dict(
        label="Weich (gleichmäßig, wenig Glanzlicht)",
        world_color=(0.10, 0.11, 0.13), world_strength=1.1,
        key_energy=1.4, key_euler=(0.5, 0.15, 0.3), key_color=(1.0, 1.0, 1.0),
        fill_energy_k=45.0, fill_energy_min=10.0, fill_size_k=2.2,
        fill_offset=(0.6, -0.6, 0.75), fill_color=(1.0, 1.0, 1.0),
        rim=True, rim_energy_k=25.0, rim_size_k=0.9,
        rim_offset=(-0.65, 0.5, 0.45), rim_color=(0.9, 0.93, 1.0),
    ),
    "kontrast": dict(
        label="Kontrastreich (dramatisch)",
        world_color=(0.02, 0.02, 0.03), world_strength=0.4,
        key_energy=4.0, key_euler=(0.65, 0.2, 0.25), key_color=(1.0, 1.0, 1.0),
        fill_energy_k=10.0, fill_energy_min=3.0, fill_size_k=0.9,
        fill_offset=(0.55, -0.9, 0.5), fill_color=(0.9, 0.95, 1.0),
        rim=True, rim_energy_k=90.0, rim_size_k=0.5,
        rim_offset=(-0.75, 0.6, 0.55), rim_color=(0.8, 0.85, 1.0),
    ),
}
DEFAULT_LIGHT_PRESET = "studio"


def _resolve_light_preset(name):
    return LIGHT_PRESETS.get(str(name or DEFAULT_LIGHT_PRESET), LIGHT_PRESETS[DEFAULT_LIGHT_PRESET])


def _clamp(v, lo, hi, default):
    try:
        return max(lo, min(hi, int(round(float(v)))))
    except (TypeError, ValueError):
        return default


# ──────────────────────────────────────────────────────────────────────────────
# 1. Wickelkopf-Ausschnitt → STL
# ──────────────────────────────────────────────────────────────────────────────
def _export_winding_stl(geom, axial_len, workdir, section_slots, progress_cb=None,
                        include_core=True, components=None, cut=None, view_mode="section",
                        hidden_pins=None, winding_full=False):
    """Baut per FreeCAD den Motor(-Ausschnitt) und exportiert ihn als **je-Bauteil-STL**
    (shaft/rotor/stator/magnets/winding — statt EINER gemergten Datei), damit Blender jedem
    Bauteil sein echtes Material geben kann (s. ``build_winding_head_stl_script``).
    ``hidden_pins`` blendet einzelne Hairpins aus (Untermenü), ``winding_full`` baut den
    Wickelkopf als vollen 360°-Ring statt nur über den Ausschnitt.
    Returns (parts | None, log) — ``parts`` = ``{key: abs_path}``."""
    os.makedirs(workdir, exist_ok=True)
    stl_dir   = os.path.join(workdir, "stl_parts")
    fcstd     = os.path.join(workdir, "wh.FCStd")
    if progress_cb:
        progress_cb("🧩 Motor-Ausschnitt (Welle/Rotor/Stator/Wickelköpfe) in FreeCAD bauen …"
                    if include_core else "🧩 Wickelkopf-Ausschnitt in FreeCAD bauen …", 5)
    code = ema_freecad.build_winding_head_stl_script(
        geom, axial_len, fcstd, stl_dir, section_slots=section_slots,
        include_core=include_core, components=components, cut=cut, view_mode=view_mode,
        hidden_pins=hidden_pins, winding_full=winding_full)
    res = freecad_runner.run_freecad_script(code, timeout=900 if winding_full else 600)
    stl_parts = res.get("stl_parts")
    if not res.get("success") or not stl_parts:
        err = res.get("stl_error") or res.get("stderr") or "STL-Export fehlgeschlagen"
        return None, err
    out = {}
    for key, fname in stl_parts.items():
        p = os.path.join(stl_dir, fname)
        if os.path.exists(p):
            out[key] = p
    if not out:
        return None, "STL-Dateien nicht gefunden"
    return out, "ok"


# ──────────────────────────────────────────────────────────────────────────────
# 2. Blender-Setup-Skript (Mantaflow FLIP) — läuft IN Blender
# ──────────────────────────────────────────────────────────────────────────────
_BLENDER_SCRIPT = r'''
import bpy, sys, os, json, math

# --- Config aus JSON-Datei (Pfad als erstes Argument nach "--") ---------------
_argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
CFG = json.load(open(_argv[0]))

def log(msg): print("OIL_STAGE:" + str(msg), flush=True)

def _set(obj, name, val):
    """Attribut nur setzen, wenn es existiert (robust gegen Blender-Versionsdrift)."""
    try:
        if hasattr(obj, name):
            setattr(obj, name, val)
            return True
    except Exception as e:
        print("OIL_STAGE:warn set %s: %s" % (name, e), flush=True)
    return False

# stl_parts: {"shaft"|"rotor"|"stator"|"magnets"|"winding": <abs. Dateipfad>} — je Bauteil eine
# eigene STL-Datei (Rückwärtskompatibilität: altes stl_path wird als reines "winding" behandelt).
STL_PARTS = CFG.get("stl_parts") or ({"winding": CFG["stl_path"]} if CFG.get("stl_path") else {})
FRAMES_DIR = CFG["frames_dir"]
RES       = int(CFG["resolution"])
F0        = int(CFG.get("frame_start", 1))
F1        = int(CFG.get("frame_end", 80))
BAND      = float(CFG.get("wet_band_m", 0.004))     # Benetzungs-Nahband [m]
SCALE     = float(CFG.get("mesh_scale", 0.001))     # mm -> m
VISC      = float(CFG.get("viscosity", 0.06))       # kinematische Öl-Viskosität (unskaliert)
SURFT     = float(CFG.get("surface_tension", 0.03))
ENGINE    = CFG.get("engine", "BLENDER_EEVEE")
# Spritzöl-Kühlring: ein Rohr-Ring (Ø RING_TUBE_MM) im Abstand RING_GAP_MM um die
# Wickelköpfe, mit NOZZLES Bohrungen (Ø NOZZLE_D_MM), aus denen Öl mit PRESSURE_BAR
# radial nach innen auf die Leiter spritzt (Strahlgeschwindigkeit v = Cd·√(2Δp/ρ)).
PRESSURE_BAR = float(CFG.get("pressure_bar", 3.0))
NOZZLES      = int(CFG.get("nozzle_count", 6))
RING_GAP_MM  = float(CFG.get("ring_gap_mm", 3.0))
RING_TUBE_MM = float(CFG.get("ring_tube_mm", 6.0))
NOZZLE_D_MM  = float(CFG.get("nozzle_d_mm", 1.0))
RHO_OIL   = 850.0                                   # kg/m³ (Motoröl)
CD_NOZZLE = 0.8                                     # Ausflusskoeffizient der Bohrung
JET_V     = CD_NOZZLE * math.sqrt(2.0 * PRESSURE_BAR * 1e5 / RHO_OIL)   # m/s aus dem Druck
STACK_HALF = float(CFG.get("stack_half_mm", 60.0)) * SCALE  # halbe Blechpaketlänge [m]
INCLUDE_CORE = bool(CFG.get("include_core", True))  # Welle/Rotor/Magnete/Stator im Modell
# Ausrichtung der Maschine: "horizontal" (Achse waagerecht, Schwerkraft ⊥ Achse — reale
# Einbaulage) oder "vertical" (Achse senkrecht). CLOSEUP = Nahaufnahme EIN Strahl auf EINEN Leiter.
ORIENTATION = str(CFG.get("orientation", "horizontal"))
HORIZONTAL  = ORIENTATION != "vertical"
CLOSEUP     = bool(CFG.get("closeup", False))
# Zeitlupe: time_scale < 1 lässt die Simulation pro Frame weniger physikalische Zeit rechnen →
# das Video (feste fps) zeigt Ultra-Slow-Motion. 1.0 = Echtzeit, 0.002 = 500×-Zeitlupe.
TIME_SCALE  = max(0.001, min(1.0, float(CFG.get("time_scale", 1.0))))
# Schnelle Darstellung (grobe Vorschau): weniger Substeps, keine Sekundärpartikel, flaches Rendern.
FAST        = bool(CFG.get("fast", False))
# Strahlrichtung justierbar: axiale Neigung (+ = mehr zur Blechpaket-Stirnfläche/nach unten) und
# tangentialer Versatz (Gieren) gegen den rein radialen Grund-Strahl. Der Grundzielpunkt bleibt
# ein ECHTER Kronen-(Kupfer-)Punkt → der Strahl trifft den Wickelkopf trotz Justage.
JET_TILT   = math.radians(max(-60.0, min(60.0, float(CFG.get("jet_tilt_deg", 0.0)))))
JET_YAW    = math.radians(max(-60.0, min(60.0, float(CFG.get("jet_yaw_deg", 0.0)))))
SHOW_JET_LINE = bool(CFG.get("show_jet_line", False))   # sichtbare Strahl-Ziellinie zeichnen
# Düsen-VERSATZ um die Motorachse: die Düsen-ÖFFNUNG (Position im Ring) wird um diesen Winkel
# gedreht, das ZIEL bleibt der echte Kronenpunkt (tgt, unverändert) — der Strahl läuft dadurch
# schräg zum Nachbar-Wickelkopf statt frontal auf EINEN, sodass links UND rechts vom Strahl
# Wickelkopf-Kupfer liegt (Nutzer-Wunsch). Anders als JET_YAW (dreht nur die Strahl-RICHTUNG am
# selben Ort) verschiebt dies die Düse selbst entlang des Rings.
NOZZLE_OFFSET = math.radians(max(-45.0, min(45.0, float(CFG.get("nozzle_offset_deg", 15.0)))))
# Sprühfächer (Kegelöffnung): streut die Anfangsgeschwindigkeit der Mantaflow-Emitter zufällig um
# die Grundrichtung (Blender „velocity_random") — der Strahl läuft kelchförmig/konisch statt als
# scharfer Nadelstrahl und zerfällt beim Auftreffen sichtbarer in Tröpfchen (zusammen mit den
# ohnehin aktiven Spray/Foam/Bubble-Sekundärpartikeln).
JET_CONE   = math.radians(max(0.0, min(40.0, float(CFG.get("jet_cone_deg", 10.0)))))
# Vorschau (Zwischenansicht): NUR Geometrie + Düsen + Strahl-Ziellinien rendern, KEIN Fluid-Bake.
# Zeigt vorab, wohin die Strahlen zeigen, bevor der teure Mantaflow-Bake läuft.
PREVIEW    = bool(CFG.get("preview", False))
# Drehteller-Vorschau: >1 ⇒ rendert N Kamera-Winkel rund um die Motorachse, damit sich das
# gerenderte Standbild im Browser frei DREHEN lässt (Ziehen). 1 = ein einzelnes Standbild (alt).
PREVIEW_TURNS = max(1, min(72, int(CFG.get("preview_turns", 1))))
# Ansicht: welche Achse im Bild nach UNTEN zeigt (nur Kamera/Blickrichtung — die Schwerkraft/Physik
# steuert weiterhin ORIENTATION horizontal/vertikal). "auto" folgt der Einbaulage. Sonst ±x/±y/±z.
VIEW_DOWN  = str(CFG.get("view_down", "auto")).lower()
# Koordinatensystem (XYZ-Achsen) im Bild einblenden — v. a. für die Vorschau, um die Lage zu erkennen.
SHOW_AXES  = bool(CFG.get("show_axes", False))
# Glättung (Shade Smooth): Netzfacetten auf gekrümmten Flächen verschwinden (harte Kanten bleiben).
SMOOTH     = bool(CFG.get("smooth", True))
# Öl-Transparenz (0 = deckend … 1 = klar) für das gerenderte Öl-Material.
OIL_ALPHA  = max(0.0, min(1.0, float(CFG.get("oil_transparency", 0.45))))
# Beleuchtungs-Voreinstellung (Weltfarbe/-stärke + 3-Punkt-Licht-Rig), s. ema_oilspray.LIGHT_PRESETS.
LIGHT = CFG.get("light") or {}
if PREVIEW:
    SHOW_JET_LINE = True                                # in der Vorschau immer die Linien zeigen
    SHOW_AXES = True                                    # Vorschau: Koordinatensystem zur Orientierung
os.makedirs(FRAMES_DIR, exist_ok=True)
CACHE_DIR = os.path.join(os.path.dirname(FRAMES_DIR), "blendcache_oil")
os.makedirs(CACHE_DIR, exist_ok=True)

# --- leere Szene --------------------------------------------------------------
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# --- 1) Motor-Bauteile importieren (JE Bauteil eine eigene STL-Datei/Objekt) --
# Getrennte Objekte statt EINER gemergten Mesh, damit jedes Bauteil sein ECHTES Material
# bekommt (Magnete ≠ Rotoreisen, Hairpins ≠ Stator — eine Radius-/Achsheuristik auf einem
# gemergten Mesh konnte das nicht unterscheiden).
log("STL importieren (%d Bauteile)" % len(STL_PARTS))
_PART_NAMES = {"shaft": "Shaft", "rotor": "Rotor", "stator": "Stator",
              "magnets": "Magnets", "winding": "WindingHead"}
_parts_obj = {}
for _key, _path in STL_PARTS.items():
    try:
        bpy.ops.wm.stl_import(filepath=_path)            # Blender 4.x
    except Exception:
        bpy.ops.import_mesh.stl(filepath=_path)          # ältere API
    _po = bpy.context.selected_objects[0] if bpy.context.selected_objects else bpy.context.object
    _po.name = _PART_NAMES.get(_key, _key)
    _po.scale = (SCALE, SCALE, SCALE)
    _parts_obj[_key] = _po
bpy.context.view_layer.update()
# `wh` bleibt (wie im Rest des Skripts erwartet) der WICKELKOPF speziell — Überhang-Sampling
# (Düsenziele, Benetzungsmetrik, Domain-Fokus) bezieht sich NUR auf ihn, nicht auf Kern-Teile.
wh = _parts_obj.get("winding") or next(iter(_parts_obj.values()))
import mathutils

# Shade Smooth: glättet die Netzfacetten auf gekrümmten Flächen (z. B. Kronen/Rohr), während echte
# Kanten über den Winkel (auto-smooth) scharf bleiben. Fällt robust auf per-Polygon-Smooth zurück.
def _smooth(obj, angle_deg=35.0):
    if not SMOOTH or obj is None or getattr(obj, "type", None) != 'MESH':
        return
    try:
        for _o in list(bpy.context.selected_objects): _o.select_set(False)
        obj.select_set(True); bpy.context.view_layer.objects.active = obj
        bpy.ops.object.shade_smooth()
        try:
            bpy.ops.object.shade_auto_smooth(angle=math.radians(angle_deg))   # Blender 4.2-Operator
        except Exception:
            try: obj.data.use_auto_smooth = True; obj.data.auto_smooth_angle = math.radians(angle_deg)
            except Exception: pass
    except Exception:
        try:
            for _p in obj.data.polygons: _p.use_smooth = True
        except Exception:
            pass

# Kamera-„oben"-Achse aus der gewünschten Unten-Richtung (VIEW_DOWN). to_track_quat erwartet einen
# Achsen-String ('X'/'-X'/'Y'/…). "auto" folgt der Einbaulage (horizontal → +Y oben, vertikal → +Z).
_DOWN2UP = {"-y": 'Y', "+y": '-Y', "-z": 'Z', "+z": '-Z', "-x": 'X', "+x": '-X'}
_UP2VEC  = {'X': (1, 0, 0), '-X': (-1, 0, 0), 'Y': (0, 1, 0), '-Y': (0, -1, 0),
            'Z': (0, 0, 1), '-Z': (0, 0, -1)}
def _up_axis_str():
    return _DOWN2UP.get(VIEW_DOWN, ('Y' if HORIZONTAL else 'Z'))
_TRACK_AXIS_VEC = {'X': mathutils.Vector((1, 0, 0)), '-X': mathutils.Vector((-1, 0, 0)),
                   'Y': mathutils.Vector((0, 1, 0)), '-Y': mathutils.Vector((0, -1, 0)),
                   'Z': mathutils.Vector((0, 0, 1)), '-Z': mathutils.Vector((0, 0, -1))}
def _track_quat(vec, track, up):
    # Blenders Vector.to_track_quat() akzeptiert für die Up-Achse NUR 'X'/'Y'/'Z' ohne Vorzeichen
    # (sonst ValueError "only X, Y or Z for up axis") — _DOWN2UP liefert aber z.B. '-Y'. Ein
    # zusätzlicher 180°-Roll um die (unveränderte) Track-Achse liefert exakt dieselbe Ausrichtung,
    # die ein vorzeichenbehaftetes Up ergäbe.
    if up.startswith('-'):
        q = vec.to_track_quat(track, up[1:])
        return q @ mathutils.Quaternion(_TRACK_AXIS_VEC[track], math.pi)
    return vec.to_track_quat(track, up)
# Für die HORIZONTALE Darstellung den Wickelkopf-Sektor um die Achse (z) nach OBEN (+y) drehen,
# damit die Schwerkraft (−y) das Öl sauber nach unten von den Wickelköpfen ablaufen lässt. Die
# Rotation MUSS auf ALLE importierten Bauteile (Welle/Rotor/Stator/Magnete/Wickelkopf) angewendet
# werden, nicht nur auf `wh` — jedes Bauteil ist seit dem Je-Bauteil-STL-Export ein EIGENES Objekt
# mit eigenem unrotierten Ursprung; wurde früher (EIN gemergtes Objekt) implizit mitgedreht. Nur
# `wh` zu drehen ließ Statornuten (fix) und Hairpins (gedreht) angular auseinanderlaufen — die Nuten
# passten optisch nicht mehr zu den Leitern (Nutzer-Beanstandung).
_pv = [wh.matrix_world @ v.co for v in wh.data.vertices]
_pa = [math.atan2(p.y, p.x) for p in _pv if p.z > STACK_HALF] or [math.atan2(p.y, p.x) for p in _pv]
if (max(_pa) - min(_pa)) > math.pi:
    _pa = [a + 2*math.pi if a < 0 else a for a in _pa]
_sec_c = 0.5 * (min(_pa) + max(_pa))
if HORIZONTAL:
    _rot_z = (math.pi / 2.0) - _sec_c                    # Sektor → +y (oben)
    for _po in _parts_obj.values():
        _po.rotation_euler = (0.0, 0.0, _rot_z)
    bpy.context.view_layer.update()
_smooth(wh)                                          # Facetten der Kronen/Leiter glätten
# Weltraum-BBox des skalierten (ggf. gedrehten) Modells
bb = [wh.matrix_world @ mathutils.Vector(c) for c in wh.bound_box]
xs = [p.x for p in bb]; ys = [p.y for p in bb]; zs = [p.z for p in bb]
xmin, xmax = min(xs), max(xs); ymin, ymax = min(ys), max(ys); zmin, zmax = min(zs), max(zs)
cx, cy = (xmin+xmax)/2, (ymin+ymax)/2
ext = max(xmax-xmin, ymax-ymin, 1e-3)

# Motorachse = z (das FreeCAD-Modell ist um die z-Achse bei x=y=0 gebaut). Der Kühlring sitzt
# am **+z-ENDE der Wickelköpfe** und spritzt Richtung Drehachse. Wir betrachten daher nur den
# Wickelkopf-Überhang bei +z (Vertices oberhalb der Blechpaket-Stirnfläche z=STACK_HALF).
_vw = [wh.matrix_world @ v.co for v in wh.data.vertices]
z_stack_end = STACK_HALF                             # Stirnfläche des Blechpakets (+z)
_ov = [p for p in _vw if p.z > z_stack_end] or _vw   # Wickelkopf-Überhang (+z)
r_crown = max(math.hypot(p.x, p.y) for p in _ov)     # Außenradius der Kronen am Ende
z_tip   = max(p.z for p in _ov)                      # axiales ENDE der Wickelköpfe
_angs = [math.atan2(p.y, p.x) for p in _ov]
if (max(_angs) - min(_angs)) > math.pi:              # Winkel-Wrap um ±π entfalten
    _angs = [a + 2*math.pi if a < 0 else a for a in _angs]
th_min, th_max = min(_angs), max(_angs)
# Ring am ENDE: Höhe = z_tip, Radius = Kronen-Außenradius + Spalt + Rohr-Radius.
gap_m   = RING_GAP_MM  * SCALE
tube_r  = 0.5 * RING_TUBE_MM * SCALE
r_noz   = r_crown + gap_m                             # Bohrungen an der Rohr-Innenseite
r_ring  = r_crown + gap_m + tube_r                   # Rohr-Mittenradius
ring_z  = z_tip                                      # AM ENDE der Wickelköpfe
# xy-Ausdehnung des Rings (um die ORIGIN-Achse). Der Strahl ZIELT Richtung Achse, trifft aber
# die Wickelköpfe (direkt innerhalb des Rings) — die Domain wird daher NICHT bis zur Achse
# aufgezogen (sonst wird sie riesig/grob), sondern hält den Wickelkopf-Endbereich eng + fein.
_ro = r_ring + tube_r
_ts = [th_min + (th_max - th_min) * i / 24.0 for i in range(25)]
_rx = [_ro * math.cos(t) for t in _ts] + [r_noz * math.cos(t) for t in _ts]
_ry = [_ro * math.sin(t) for t in _ts] + [r_noz * math.sin(t) for t in _ts]
ring_xmin, ring_xmax = min(_rx), max(_rx)
ring_ymin, ring_ymax = min(_ry), max(_ry)
# xy-Ausdehnung des Wickelkopf-Endbereichs (für die Domain)
wx = [p.x for p in _ov]; wy = [p.y for p in _ov]
wh_xmin, wh_xmax = min(wx), max(wx); wh_ymin, wh_ymax = min(wy), max(wy)
ext_end = max(ring_xmax - ring_xmin, ring_ymax - ring_ymin, z_tip - z_stack_end, 1e-3)

# Strahl-Geometrie VORAB (wird von Düsen UND Kamera gebraucht): Sektor-Mitte + Auftreffband.
_overh = max(1e-3, z_tip - z_stack_end)
_thc = 0.5 * (th_min + th_max)                       # Sektor-Mitte (θ)
_ct0, _st0 = math.cos(_thc), math.sin(_thc)
z_aim = z_stack_end + 0.35 * _overh                  # Zielhöhe (Fallback): radial nach innen/unten

# Zielpunkte an ECHTEN Wickelkopf-Leitern (Kupfer): jede Düse wird auf eine reale Kronen-
# Oberfläche „abgestimmt", damit der Strahl SICHTBAR auf einen Hairpin-Leiter trifft (statt in
# eine Lücke ZWISCHEN den Leitern zu spritzen — Nutzer: „die Ölöffnung muss in allen Positionen
# auf die Hairpins abgestimmt sein"). _ovinfo = (θ, r, z, Punkt) je Wickelkopf-Überhang-Vertex.
_ovinfo = [(_angs[i], math.hypot(_ov[i].x, _ov[i].y), _ov[i].z, _ov[i])
           for i in range(len(_ov))]
def _crown_target(th_want, win):
    """Realer Kronen-(Kupfer-)Punkt nahe Winkel th_want: die zum Ring zeigende Außenfläche
    (größter Radius), aber KNAPP UNTER der Kronenspitze (z ≈ ring_z − 1,2·Rohrradius) — so liegt
    der Punkt RADIAL innerhalb der Düse (Strahl quert den Ringspalt, läuft nicht axial vorbei),
    und der Strahl trifft die FLANKE des Wickelkopfs statt die Spitze zu streifen (an der Spitze
    fliegt der halbe Sprühkegel über die Krone hinweg — „trifft nicht"). Returns (θ_snap, Vektor)."""
    cand = [t for t in _ovinfo if abs(t[0] - th_want) <= win] or _ovinfo
    rmax = max(t[1] for t in cand)
    near = [t for t in cand if t[1] >= rmax - 0.003]     # äußerstes Kronenband (3 mm)
    z_hit = ring_z - 1.2 * tube_r                        # Zielhöhe: knapp unter der Spitze
    near.sort(key=lambda t: abs(t[2] - z_hit))
    t = near[0]
    return t[0], mathutils.Vector((t[3].x, t[3].y, t[3].z))
# In der Nahaufnahme EINEN zentralen Leiter wählen; Düse UND Kamera nutzen EXAKT diesen Punkt
# (so ist der Treffer im Bild, statt Düse-Winkel ≠ Kamera-Winkel wie in einem früheren Versuch).
if CLOSEUP:
    close_th, close_tgt = _crown_target(_thc, 0.33 * (th_max - th_min))
else:
    close_th, close_tgt = _thc, mathutils.Vector((r_crown * _ct0, r_crown * _st0, z_aim))

# Effector-Modifier auf JEDEM importierten Bauteil (nicht nur dem Wickelkopf) — das GANZE
# angezeigte Tortenstück ist Kollision + optischer Kontext (Öl läuft z. B. auch über Rotor/
# Stator ab, wenn die mit angezeigt sind); der Fluid-Löser wertet nur den Teil INNERHALB der
# Domain aus, der Rest bleibt sichtbar.
for _po in _parts_obj.values():
    bpy.context.view_layer.objects.active = _po
    bpy.ops.object.modifier_add(type='FLUID')
    _mpo = _po.modifiers[-1]; _mpo.fluid_type = 'EFFECTOR'
    _set(_mpo.effector_settings, "effector_type", "COLLISION")
    _set(_mpo.effector_settings, "surface_distance", 0.5)
    _set(_mpo.effector_settings, "use_effector", True)

# --- 2) Domain: fokussiert auf das +z-ENDE (Wickelkopf-Überhang + Ring), MIT Ablaufraum in
#     SCHWERKRAFT-Richtung, damit das Öl sichtbar über die Wickelköpfe ABLÄUFT (statt am
#     Aufprall sofort zu zerstäuben und die offene Domain zu verlassen). Horizontal: Schwerkraft
#     −y (Sektor oben) → Ablauf nach −y; vertikal: Schwerkraft −z → Ablauf nach −z.
log("Domain aufsetzen (Auflösung %d)" % RES)
splash = 0.22 * ext_end
if HORIZONTAL:
    dz_lo = z_stack_end - 0.25 * _overh              # axial (z): Endbereich
    dz_hi = z_tip + gap_m + 0.15 * ext_end
    Dxmin = min(wh_xmin, ring_xmin) - splash; Dxmax = max(wh_xmax, ring_xmax) + splash
    Dymax = max(wh_ymax, ring_ymax) + splash
    Dymin = min(wh_ymin, ring_ymin) - 1.0 * _overh - splash   # Ablauf nach unten (−y)
else:
    dz_lo = z_stack_end - 1.0 * _overh              # Ablauf nach unten (−z)
    dz_hi = ring_z + gap_m + 0.15 * ext_end
    Dxmin = min(wh_xmin, ring_xmin) - splash; Dxmax = max(wh_xmax, ring_xmax) + splash
    Dymin = min(wh_ymin, ring_ymin) - splash; Dymax = max(wh_ymax, ring_ymax) + splash
dcx, dcy, dcz = (Dxmin + Dxmax) / 2, (Dymin + Dymax) / 2, (dz_lo + dz_hi) / 2
sx = (Dxmax - Dxmin) / 2 + 0.005
sy = (Dymax - Dymin) / 2 + 0.005
sz = (dz_hi - dz_lo) / 2
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
# Sekundärpartikel (Spray/Foam/Bubble) machen die Tröpfchen sichtbar, kosten aber Bake-Zeit —
# in der schnellen Vorschau abschalten.
_set(ds, "use_spray_particles", not FAST)
_set(ds, "use_foam_particles", not FAST)
_set(ds, "use_bubble_particles", not FAST)
# Viskositätslöser NUR bei spürbar zähem Öl einschalten — dünnes Motoröl bei 3 bar verhält
# sich auf dieser Skala nahezu reibungsarm; ein aktiver Viskositätslöser macht selbst kleine
# Werte gelartig und dämpft den Strahl zum langsamen Klumpen (Nutzer: „zu dickflüssig").
if VISC > 0.02:
    _set(ds, "use_viscosity", True)
    if not _set(ds, "viscosity_value", VISC):
        _set(ds, "viscosity_base", VISC)
else:
    _set(ds, "use_viscosity", False)
_set(ds, "use_diffusion", True)
# Niedrige Oberflächenspannung → der austretende Strahl perlt NICHT sofort zur kompakten Kugel
# zusammen (bildet einen zusammenhängenden Strahl), zerfällt am Aufprall aber noch in Tropfen.
_set(ds, "surface_tension", SURFT)
_set(ds, "cache_type", "ALL")
_set(ds, "cache_directory", CACHE_DIR)
_set(ds, "cache_frame_start", F0)
_set(ds, "cache_frame_end", F1)
# OFFENE Ränder: Spritzöl, das den Domain-Rand erreicht, verlässt die Domain (statt an den
# unsichtbaren Wänden „Öl-Bleche" zu bilden). Der Boden wird über das Outflow-Objekt geleert.
for _b in ("use_collision_border_front", "use_collision_border_back",
           "use_collision_border_right", "use_collision_border_left",
           "use_collision_border_top", "use_collision_border_bottom"):
    _set(ds, _b, False)
# Schneller Strahl (3 bar ≈ 20 m/s) über feine Zellen → mehr Substeps, sonst „tunnelt" das
# Öl durch die Leiter (CFL). Höheres timesteps_max hält die Simulation stabil.
_set(ds, "timesteps_max", int(CFG.get("substeps_max", 4 if FAST else 8)))
_set(ds, "timesteps_min", 1)
_set(ds, "cfl_condition", 3.0)
_set(ds, "use_adaptive_timesteps", True)
# Zeitlupe (Ultra-Slow-Motion): weniger Sim-Zeit pro Frame — der 21-m/s-Strahl + die
# Tropfenbildung am Aufprall werden über viele Frames sichtbar statt in 1–2 Frames.
_set(ds, "time_scale", TIME_SCALE)

# --- 3) Spritzöl-Kühlring AM ENDE der Wickelköpfe, Strahl Richtung Drehachse ---
log("Spritzring am Wickelkopf-Ende + %d Düsen (%.1f bar → %.1f m/s, Richtung Achse)"
    % (NOZZLES, PRESSURE_BAR, JET_V))
voxel = (2.0 * max(sx, sy, sz)) / max(1, RES)        # ~Zellgröße der Domain
noz_r = 0.5 * NOZZLE_D_MM * SCALE
emit_s = max(noz_r, 1.2 * voxel)                     # sub-voxel-Bohrung emittiert sonst nicht
                                                     # (etwas größer → mehr sichtbares Ölvolumen)

# (a) Ring-Manifold als sichtbares Rohr (Bogen am +z-Ende) — Kontext, kein Fluid-Objekt.
# In der Nahaufnahme zeigt der Ring nur einen kurzen Bogen um die Mittel-Düse; sonst den vollen Bogen.
if CLOSEUP:
    ring_rad = r_ring
    _aw = min(0.14, max(0.06, 0.10 * (th_max - th_min)))   # schmaler Rohrstutzen (~±8°), kein Hook
    # Bogen um den gewählten Leiter zentriert, plus Puffer für den Düsen-Versatz (sonst sitzt der
    # Düsenstutzen bei größerem NOZZLE_OFFSET optisch außerhalb des gezeichneten Rohrbogens).
    arc_lo, arc_hi = close_th - _aw - abs(NOZZLE_OFFSET), close_th + _aw + abs(NOZZLE_OFFSET)
else:
    ring_rad = r_ring
    arc_lo, arc_hi = th_min - abs(NOZZLE_OFFSET), th_max + abs(NOZZLE_OFFSET)
_np = max(10, NOZZLES * 5)
_arc = []
for i in range(_np + 1):
    th = arc_lo + (arc_hi - arc_lo) * i / _np
    _arc.append((ring_rad * math.cos(th), ring_rad * math.sin(th), ring_z, 1.0))
_crv = bpy.data.curves.new("RingCurve", type='CURVE'); _crv.dimensions = '3D'
_spl = _crv.splines.new('POLY'); _spl.points.add(len(_arc) - 1)
for i, co in enumerate(_arc): _spl.points[i].co = co
_crv.bevel_depth = tube_r; _crv.bevel_resolution = 6
ring_obj = bpy.data.objects.new("SprayRing", _crv)
scene.collection.objects.link(ring_obj)
_steel = bpy.data.materials.new("Steel"); _steel.use_nodes = True
_bs = _steel.node_tree.nodes.get("Principled BSDF")
if _bs:
    _bs.inputs["Base Color"].default_value = (0.55, 0.57, 0.60, 1.0)
    if "Metallic" in _bs.inputs:  _bs.inputs["Metallic"].default_value = 1.0
    if "Roughness" in _bs.inputs: _bs.inputs["Roughness"].default_value = 0.45
ring_obj.data.materials.append(_steel)
_smooth(ring_obj)                                    # Rohr-Ring glätten

# (b) Düsen an der Rohr-Innenseite (am Ende). Jeder Strahl tritt aus einem SICHTBAREN Düsen-
#     STUTZEN am Ring aus (so „kommt" das Öl erkennbar aus einer Bohrung) und zielt radial nach
#     innen auf die Leiter (leicht nach unten, z_aim), wo er den Spalt quert, auftrifft und
#     zerstäubt. z_aim ist vorab gesetzt.
stub_len = min(0.45 * gap_m, 0.0012)                 # sichtbarer Düsenstutzen (max ~1.2 mm)
r_noz_use = r_noz
r_emit = r_noz_use - stub_len                        # Emitter an der Stutzen-Mündung → freier
                                                     # Strahl über den Rest des Spalts zum Leiter
# Leuchtendes Material für die (optionale) Strahl-Ziellinie.
_jetmat = bpy.data.materials.new("JetLine"); _jetmat.use_nodes = True
_jbs = _jetmat.node_tree.nodes.get("Principled BSDF")
if _jbs:
    _jbs.inputs["Base Color"].default_value = (1.0, 0.15, 0.05, 1.0)
    for _en in ("Emission Color", "Emission"):
        if _en in _jbs.inputs:
            try: _jbs.inputs[_en].default_value = (1.0, 0.2, 0.05, 1.0)
            except Exception: pass
    if "Emission Strength" in _jbs.inputs:
        _jbs.inputs["Emission Strength"].default_value = 4.0
oil_jets = []
for k in range(max(1, NOZZLES)):
    # Düsen-Winkel auf einen ECHTEN Leiter „abstimmen": in der Nahaufnahme der gewählte
    # zentrale Leiter, sonst je Düse den nächstliegenden Kronen-(Kupfer-)Punkt.
    if NOZZLES == 1:
        th, tgt = close_th, close_tgt
    else:
        _thw = th_min + (th_max - th_min) * k / (NOZZLES - 1)
        th, tgt = _crown_target(_thw, max(0.04, 0.5 * (th_max - th_min) / NOZZLES))
    # Düsen-ÖFFNUNG (Position im Ring) um NOZZLE_OFFSET versetzt — das ZIEL (tgt) bleibt der echte
    # Kronenpunkt bei th. Der Strahl läuft dadurch schräg zum Nachbar-Wickelkopf statt frontal auf
    # EINEN, sodass links UND rechts vom Strahlweg Wickelkopf-Kupfer liegt.
    th_noz = th + NOZZLE_OFFSET
    _c, _s = math.cos(th_noz), math.sin(th_noz)
    # sichtbarer Düsenstutzen: kleiner Zylinder von der Ring-Innenseite radial nach innen
    bpy.ops.mesh.primitive_cylinder_add(
        radius=max(1.2 * noz_r, 0.0008), depth=stub_len,
        location=((r_noz_use - 0.5 * stub_len) * _c, (r_noz_use - 0.5 * stub_len) * _s, ring_z))
    stub = bpy.context.object; stub.name = "Nozzle_%02d" % k
    stub.rotation_euler = mathutils.Vector((-_c, -_s, 0.0)).to_track_quat('Z', 'Y').to_euler()
    stub.data.materials.append(_steel)
    _smooth(stub)
    # Emitter (INFLOW) an der Stutzen-Mündung
    px, py = r_emit * _c, r_emit * _s
    bpy.ops.mesh.primitive_cube_add(location=(px, py, ring_z))
    jt = bpy.context.object; jt.name = "OilNozzle_%02d" % k
    jt.scale = (emit_s, emit_s, emit_s)
    bpy.context.view_layer.objects.active = jt
    bpy.ops.object.modifier_add(type='FLUID')
    mj = jt.modifiers[-1]; mj.fluid_type = 'FLOW'
    fs = mj.flow_settings
    _set(fs, "flow_type", "LIQUID")
    _set(fs, "flow_behavior", "INFLOW")
    _set(fs, "use_initial_velocity", True)
    # Strahl radial nach INNEN durch den Kronen-Auftreffpunkt (tgt liegt auf Düsenhöhe, 3 mm
    # innerhalb) → der Strahl quert den Ringspalt und TRIFFT sichtbar die Kupferkrone. Zielpunkt
    # etwas hinter der Krone (0.6·r), damit die Geschwindigkeit klar radial ist (kein axiales
    # Vorbeilaufen), der Leiter im Weg wird getroffen.
    _d0 = mathutils.Vector((0.6 * tgt.x - px, 0.6 * tgt.y - py, tgt.z - ring_z))
    if _d0.length < 1e-9:
        _d0 = mathutils.Vector((-_c, -_s, 0.0))
    _d0.normalize()
    # Justage: Gieren um die Wellenachse (z) = tangentialer Versatz; Neigung um die lokale
    # Tangente = axiale Neigung (Strahl mehr Richtung Stirnfläche/nach unten). Grundziel bleibt
    # der Kronenpunkt → der Strahl trifft die Wickelköpfe auch mit Justage.
    _tang = mathutils.Vector((-_s, _c, 0.0))
    if abs(JET_YAW) > 1e-6:
        _d0 = mathutils.Matrix.Rotation(JET_YAW, 4, 'Z') @ _d0
    if abs(JET_TILT) > 1e-6:
        _d0 = mathutils.Matrix.Rotation(JET_TILT, 4, _tang) @ _d0
    _d0.normalize()
    _set(fs, "velocity_coord", [JET_V * _d0.x, JET_V * _d0.y, JET_V * _d0.z])
    # Sprühfächer: zufällige Streuung um die Grundrichtung (kelchförmiger Strahl statt Nadelstrahl)
    # — die Stärke skaliert mit der Strahlgeschwindigkeit, damit der Fächerwinkel unabhängig vom
    # Druck ungefähr JET_CONE entspricht.
    _set(fs, "velocity_random", JET_V * math.sin(JET_CONE))
    _set(fs, "use_inflow", True)
    _set(fs, "subframes", 3)                          # feiner emittieren (schneller Strahl)
    jt.hide_render = True                             # Emitter-Würfel nicht rendern (Stutzen bleibt)
    oil_jets.append(jt)
    # Sichtbare Strahl-Ziellinie (Nutzer: „mit einer Linie darstellen, wohin er trifft").
    if SHOW_JET_LINE:
        _p0 = mathutils.Vector((px, py, ring_z))
        _Ll = gap_m + 0.7 * _overh
        _mid = _p0 + _d0 * (0.5 * _Ll)
        bpy.ops.mesh.primitive_cylinder_add(radius=max(0.35 * noz_r, 0.0004),
                                            depth=_Ll, location=_mid)
        _ln = bpy.context.object; _ln.name = "JetLine_%02d" % k
        _ln.rotation_euler = _d0.to_track_quat('Z', 'Y').to_euler()
        _ln.data.materials.append(_jetmat)
        try: _ln.color = (1.0, 0.15, 0.05, 1.0)       # Workbench-Objektfarbe
        except Exception: pass

# --- 3b) Abfluss (Outflow) am Domain-Boden (in Schwerkraft-Richtung) — kein Aufstauen ---
if HORIZONTAL:      # Boden = −y-Fläche
    _dl = (dcx, Dymin + 0.04 * (Dymax - Dymin), dcz)
    _ds = (sx * 0.98, 0.03 * (Dymax - Dymin) + 0.002, sz * 0.98)
else:               # Boden = −z-Fläche
    _dl = (dcx, dcy, dz_lo + 0.04 * (dz_hi - dz_lo))
    _ds = (sx * 0.98, sy * 0.98, 0.03 * (dz_hi - dz_lo) + 0.002)
bpy.ops.mesh.primitive_cube_add(location=_dl)
drain = bpy.context.object; drain.name = "OilDrain"
drain.scale = _ds
bpy.context.view_layer.objects.active = drain
bpy.ops.object.modifier_add(type='FLUID')
mo = drain.modifiers[-1]; mo.fluid_type = 'FLOW'
fo = mo.flow_settings
_set(fo, "flow_type", "LIQUID")
_set(fo, "flow_behavior", "OUTFLOW")
_set(fo, "use_inflow", False)
drain.hide_render = True                              # Drain-Platte nicht rendern (nur Sim)

# --- 4) Bake ------------------------------------------------------------------
scene.frame_start = F0; scene.frame_end = F1
# Horizontale Einbaulage: Schwerkraft senkrecht zur Achse (−y). Senkrecht: −z (entlang Achse).
scene.gravity = (0.0, -9.81, 0.0) if HORIZONTAL else (0.0, 0.0, -9.81)
bpy.context.view_layer.objects.active = dom
for o in bpy.context.selected_objects: o.select_set(False)
dom.select_set(True)
if not PREVIEW:
    log("Bake läuft (kann dauern; CPU-gebunden)")
    try:
        with bpy.context.temp_override(active_object=dom, object=dom,
                                       selected_objects=[dom]):
            bpy.ops.fluid.bake_all()
    except Exception as e:
        print("OIL_STAGE:bake_all override fehlgeschlagen (%s), direkt" % e, flush=True)
        bpy.ops.fluid.bake_all()
    log("Bake fertig")
else:
    log("Vorschau: KEIN Bake — nur Geometrie + Düsen + Strahllinien")

# --- 5) Render-Setup ----------------------------------------------------------
# Blender 4.2 hat EEVEE in BLENDER_EEVEE_NEXT umbenannt → gegen die echte Enum auflösen.
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
if ENGINE == 'CYCLES':
    try:
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'CUDA'
        prefs.get_devices()
        for d in prefs.devices: d.use = True
        scene.cycles.device = 'GPU'
        scene.cycles.samples = 24
    except Exception as e:
        print("OIL_STAGE:GPU aus (%s) -> EEVEE" % e, flush=True)
        ENGINE = _pick_engine('BLENDER_EEVEE_NEXT')
        scene.render.engine = ENGINE
scene.render.resolution_x = 960
scene.render.resolution_y = 720
scene.render.image_settings.file_format = 'PNG'
# Filmisches View-Transform (AgX/Filmic) staucht die Lichter → keine ausgebrannten reinweißen
# Flächen mehr, der Keil-Ausschnitt (Stator-OD/Kern/Kupfer) behält Kontur (Nutzer-Wunsch).
try:
    _vt = [i.identifier for i in scene.view_settings.bl_rna.properties['view_transform'].enum_items]
    for _cand in ('AgX', 'Filmic', 'Standard'):
        if _cand in _vt:
            scene.view_settings.view_transform = _cand
            break
except Exception as _e:
    print("OIL_STAGE:view_transform: %s" % _e, flush=True)

# Welt-Hintergrund (Ambient) — sonst ist die Szene fast schwarz. Farbe/Stärke aus der
# gewählten Beleuchtungs-Voreinstellung (LIGHT_PRESETS).
world = bpy.data.worlds.new("OilWorld"); scene.world = world
world.use_nodes = True
_bg = world.node_tree.nodes.get("Background")
if _bg:
    _wc = LIGHT.get("world_color", (0.05, 0.06, 0.08))
    _bg.inputs[0].default_value = (float(_wc[0]), float(_wc[1]), float(_wc[2]), 1.0)
    _bg.inputs[1].default_value = float(LIGHT.get("world_strength", 0.9))

# Kamera — Bezug ist die vorab bestimmte Sektor-Mitte (_thc) am Kronenradius (r_crown).
if HORIZONTAL:
    # Achse (z) waagerecht, Schwerkraft (−y) nach unten (to_track_quat 'Y' = Welt-Y oben).
    if CLOSEUP:
        # NAHAUFNAHME: seitlich-tangential auf die Auftreffstelle EINES Strahls auf EINEN Leiter.
        # Blickrichtung TANGENTIAL (⊥ zur radial-axialen Strahlebene) → der Strahl-Bogen Düse→
        # Leiter ist im Profil sichtbar; leicht radial-nach-außen versetzt, damit Ring (oben) UND
        # Leiter (unten) samt Spalt ins Bild kommen. Distanz an die axiale Wickelkopf-Überhang-
        # länge gekoppelt → der Leiterbereich füllt das Bild (kein toter Raum wie in der Übersicht).
        # Kamera auf den EXAKTEN Auftreffpunkt am Leiter (close_tgt) — derselbe Punkt, auf den
        # die Düse spritzt → der Treffer ist garantiert im Bild. Etwas Rückzug + radial-nach-innen-
        # Versatz, damit der KEIL-AUSSCHNITT (Kupferleiter + Kern) deutlich mit im Bild ist.
        # Blick von schräg AUSSEN-OBEN auf den Auftreffpunkt (Apex, wo der Strahl die Kupferkrone
        # trifft). Kamera radial nach außen + deutlich nach OBEN versetzt → sie schaut nach unten-
        # innen, sodass sich Düse → Öl­strahl → Kupferkrone → Keil-Ausschnitt (Kern) im Bild
        # ÜBEREINANDER staffeln (nozzle/jet/impact liegen dicht beisammen, der Kern liegt darunter).
        _ct, _st = math.cos(close_th), math.sin(close_th)
        _tang = mathutils.Vector((-_st, _ct, 0.0))          # Tangente
        _rad  = mathutils.Vector((_ct, _st, 0.0))           # radial nach außen
        cam_tgt = close_tgt.copy()                          # Apex = Öl-Auftreffpunkt am Leiter
        _span = max(z_tip - z_stack_end, 3.0 * gap_m, 0.02)
        cam_d = 2.2 * _span
        cam_loc = cam_tgt + _rad * (1.1 * cam_d) + _tang * (0.4 * cam_d) \
                  + mathutils.Vector((0.0, 0.0, 0.9 * cam_d))
        _lens = 40.0
    else:
        cam_tgt = mathutils.Vector((cx, 0.6 * Dymax + 0.4 * dcy, 0.5 * (z_stack_end + z_tip)))
        cam_d = 2.2 * max(ext, zmax - zmin)
        cam_loc = (cx + cam_d, cam_tgt.y + 0.25 * cam_d, cam_tgt.z + 0.35 * cam_d)
        _lens = 40.0
else:
    cam_tgt = mathutils.Vector((cx, cy, 0.45 * zmin + 0.55 * zmax))
    cam_d = 2.4 * max(ext, zmax - zmin)
    cam_loc = (cx + cam_d, cy - cam_d, cam_tgt.z + 0.55 * cam_d)
    _lens = 40.0
# Kamera-Fixwinkel (Drehteller→Video): im Vorschau-Drehteller gewählte Position wird 1:1 im
# echten Bake-Render wiederverwendet, statt die Standard-3/4-Ansicht neu zu berechnen — dieselbe
# Rotationsformel wie der Drehteller unten (Orbit um cam_tgt um die Kamera-Oben-Achse).
_CAM_LOCK_DEG = CFG.get("camera_angle_deg")
if _CAM_LOCK_DEG is not None:
    _lock_up_axis = _up_axis_str()
    _lock_up = mathutils.Vector(_UP2VEC.get(_lock_up_axis, (0, 1, 0) if HORIZONTAL else (0, 0, 1)))
    _lock_rot = mathutils.Matrix.Rotation(math.radians(float(_CAM_LOCK_DEG)), 4, _lock_up)
    cam_loc = cam_tgt + _lock_rot @ (mathutils.Vector(cam_loc) - cam_tgt)
bpy.ops.object.camera_add(location=cam_loc)
cam = bpy.context.object
# Kamera-Oben an die Einbaulage koppeln, damit „unten" (Schwerkraft) auch im Bild unten ist:
# horizontal → Welt-+Y oben (Achse liegt waagerecht), vertikal → Welt-+Z oben (Motorachse steht
# senkrecht, das Öl läuft sichtbar der Achse entlang nach unten). So wirkt die Einbaulage sichtbar.
_cam_up = _up_axis_str()
cam.rotation_euler = _track_quat(cam_tgt - cam.location, '-Z', _cam_up).to_euler()
if cam.data:
    cam.data.lens = _lens
scene.camera = cam
# Beleuchtung — 3-Punkt-Rig (Key-Sonne + seitlich versetztes Fülllicht + Kantenlicht), Werte aus
# der gewählten Voreinstellung (LIGHT_PRESETS). WICHTIG: das Fülllicht sitzt NICHT mehr an der
# Kameraposition — ein Licht direkt an der Kamera erzeugt einen Kamerablitz-Effekt: auf glänzendem
# Metall (Welle/Kupfer, hohe Metallic-Werte) spiegelt eine zur Kamera zeigende Fläche ein kamera-
# nahes Licht fast immer direkt in die Linse zurück → Stahl/Kupfer wirkten flach ausgebrannt WEISS
# statt Kontur zu zeigen (Nutzer-Beanstandung). Seitlicher Versatz (fill_offset relativ zu cam_d/
# cam_tgt) bricht diese Spiegel-Rückkopplung; das Kantenlicht gibt zusätzlich Kontur/Tiefe.
_key_energy = float(LIGHT.get("key_energy", 2.2))
_key_euler  = tuple(LIGHT.get("key_euler", (0.6, 0.15, 0.3)))
_key_color  = tuple(LIGHT.get("key_color", (1.0, 1.0, 1.0)))
_fill_k     = float(LIGHT.get("fill_energy_k", 32.0))
_fill_min   = float(LIGHT.get("fill_energy_min", 6.0))
_fill_size_k = float(LIGHT.get("fill_size_k", 1.5))
_fill_offset = tuple(LIGHT.get("fill_offset", (0.55, -0.85, 0.6)))
_fill_color = tuple(LIGHT.get("fill_color", (1.0, 1.0, 1.0)))
_rim_on     = bool(LIGHT.get("rim", True))
_rim_k      = float(LIGHT.get("rim_energy_k", 55.0))
_rim_size_k = float(LIGHT.get("rim_size_k", 0.7))
_rim_offset = tuple(LIGHT.get("rim_offset", (-0.7, 0.55, 0.5)))
_rim_color  = tuple(LIGHT.get("rim_color", (0.75, 0.82, 1.0)))

_lz = zmax + 3 * ext
bpy.ops.object.light_add(type='SUN', location=(cx + ext, cy + ext, _lz))
_sun = bpy.context.object; _sun.data.energy = _key_energy
_sun.data.color = _key_color
_sun.rotation_euler = _key_euler

_fill_loc = cam_tgt + mathutils.Vector((cam_d * _fill_offset[0], cam_d * _fill_offset[1],
                                        cam_d * _fill_offset[2]))
bpy.ops.object.light_add(type='AREA', location=_fill_loc)
_fill = bpy.context.object
# Fülllicht-Fläche an die Kameradistanz koppeln + Leistung ~ Distanz² (nah = weniger Watt),
# damit die Nahaufnahme nicht ausbrennt.
_fill.data.size = max(0.06, _fill_size_k * cam_d)
_fill.data.energy = max(_fill_min, _fill_k * cam_d * cam_d)
_fill.data.color = _fill_color
_fill.rotation_euler = (cam_tgt - _fill.location).to_track_quat('-Z', 'Y').to_euler()

if _rim_on:
    _rim_loc = cam_tgt + mathutils.Vector((cam_d * _rim_offset[0], cam_d * _rim_offset[1],
                                           cam_d * _rim_offset[2]))
    bpy.ops.object.light_add(type='AREA', location=_rim_loc)
    _rim = bpy.context.object
    _rim.data.size = max(0.04, _rim_size_k * cam_d)
    _rim.data.energy = max(4.0, _rim_k * cam_d * cam_d)
    _rim.data.color = _rim_color
    _rim.rotation_euler = (cam_tgt - _rim.location).to_track_quat('-Z', 'Y').to_euler()

# Öl-Material (transluzent, bernsteinfarben) auf die Liquid-Mesh (= Domain-Objekt). Die
# Transparenz ist über OIL_ALPHA einstellbar (0 = deckend … 1 = klar).
oil = bpy.data.materials.new("Oil"); oil.use_nodes = True
bsdf = oil.node_tree.nodes.get("Principled BSDF")
if bsdf:
    bsdf.inputs["Base Color"].default_value = (0.55, 0.35, 0.08, 1.0)
    if "Roughness" in bsdf.inputs: bsdf.inputs["Roughness"].default_value = 0.12
    if "IOR" in bsdf.inputs: bsdf.inputs["IOR"].default_value = 1.47
    for tname in ("Transmission", "Transmission Weight"):
        if tname in bsdf.inputs:
            bsdf.inputs[tname].default_value = OIL_ALPHA
    # Alpha-Blend als Rückfall (Workbench/EEVEE ohne Refraktion) — sonst wirkt das Öl deckend.
    if "Alpha" in bsdf.inputs:
        bsdf.inputs["Alpha"].default_value = max(0.35, 1.0 - 0.55 * OIL_ALPHA)
# EEVEE braucht für echte Transparenz Screen-Space-Refraktion + BLEND/HASHED-Blendmodus.
try:
    oil.use_screen_refraction = True
    for _bm in ("blend_method",):
        if hasattr(oil, _bm): setattr(oil, _bm, 'BLEND')
    if hasattr(oil, "show_transparent_back"): oil.show_transparent_back = False
    ee = getattr(scene, "eevee", None)
    if ee is not None:
        for _f in ("use_ssr", "use_ssr_refraction", "use_raytracing"):
            if hasattr(ee, _f): setattr(ee, _f, True)
except Exception as _e:
    print("OIL_STAGE:Öl-Transparenz: %s" % _e, flush=True)
dom.data.materials.append(oil)
# Bauteil-Materialien: JEDES importierte Bauteil ist eine EIGENE STL-Datei/Objekt (echte
# Objekt-Identität aus FreeCAD, s. build_winding_head_stl_script) und bekommt sein fachlich
# korrektes Material — ersetzt die alte Radius-/Achs-Heuristik auf einem gemergten Mesh, die
# z. B. Magnete nicht vom Rotoreisen und Hairpin-Beine in den Nuten nicht vom Stator unter-
# scheiden konnte (beide lagen im selben Radius-/Achsband).
def _mk_mat(name, rgb, metal, rough, spec=0.5):
    m = bpy.data.materials.new(name); m.use_nodes = True
    b = m.node_tree.nodes.get("Principled BSDF")
    if b:
        b.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
        if "Metallic" in b.inputs:  b.inputs["Metallic"].default_value = metal
        if "Roughness" in b.inputs: b.inputs["Roughness"].default_value = rough
        # Dielektrischer Fresnel-Speziallichtanteil (bleibt auch bei Metallic<1 aktiv) —
        # bei Default 0.5 legt sich über raue, mittelhelle Flächen (Elektroblech) unter
        # kräftiger Beleuchtung ein weißlicher Glanzschleier, der die Grundfarbe übertönt.
        for _sn in ("Specular IOR Level", "Specular"):
            if _sn in b.inputs: b.inputs[_sn].default_value = spec
    return m
_mat_shaft  = _mk_mat("Edelstahl-Welle", (0.66, 0.67, 0.70), 0.95, 0.22)  # bearbeiteter Edelstahl: hell, glatt
# Elektroblech (Rotor+Stator): dunkler, matter, weniger Fresnel-Glanz als vorher — die alte
# Kombi (hellgrau, Metallic 0.55, Speziallicht-Default 0.5) wusch unter kräftiger Beleuchtung
# fast weiß aus (Nutzer-Beanstandung); jetzt deutlich als GRAUES lackiertes Blech erkennbar.
_mat_lam    = _mk_mat("Elektroblech", (0.22, 0.23, 0.27), 0.35, 0.75, spec=0.22)
_mat_magnet = _mk_mat("Magnet-Stahl", (0.045, 0.045, 0.05), 0.5, 0.42)   # sehr dunkler Stahl
_mat_copper = _mk_mat("Kupfer", (0.74, 0.35, 0.12), 1.0, 0.34)           # Spulen/Hairpins
_PART_MATS = {"shaft": _mat_shaft, "rotor": _mat_lam, "stator": _mat_lam,
             "magnets": _mat_magnet, "winding": _mat_copper}
for _key, _po in _parts_obj.items():
    _po.data.materials.clear()
    _po.data.materials.append(_PART_MATS.get(_key, _mat_copper))
    _smooth(_po)

# --- 5a) Koordinatensystem (XYZ-Achsen) am Modell-Eck einblenden (Orientierungshilfe) --------
# 3 farbige, leuchtende Pfeile X(rot)/Y(grün)/Z(blau) mit Beschriftung an einer Modell-Ecke, damit
# man in der (drehbaren) Vorschau die Lage erkennt. Emissiv → sichtbar in EEVEE UND (per Objektfarbe)
# im Workbench-Render.
if SHOW_AXES:
    _gl = 0.32 * ext                                   # Achsenlänge
    _gr = max(0.02 * _gl, 0.0007)                      # Schaftradius
    _gpos = mathutils.Vector((xmin - 0.30 * ext, ymin - 0.30 * ext, zmin))
    def _axmat(name, rgb):
        m = bpy.data.materials.new(name); m.use_nodes = True
        b = m.node_tree.nodes.get("Principled BSDF")
        if b:
            b.inputs["Base Color"].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
            for _en in ("Emission Color", "Emission"):
                if _en in b.inputs:
                    try: b.inputs[_en].default_value = (rgb[0], rgb[1], rgb[2], 1.0)
                    except Exception: pass
            if "Emission Strength" in b.inputs: b.inputs["Emission Strength"].default_value = 2.5
        return m
    def _axis(vec, rgb, label):
        _m = _axmat("Axis_" + label, rgb)
        _d = mathutils.Vector(vec).normalized()
        bpy.ops.mesh.primitive_cylinder_add(radius=_gr, depth=_gl, location=_gpos + _d * (0.5 * _gl))
        _sh = bpy.context.object; _sh.name = "Axis_%s" % label
        _sh.rotation_euler = _d.to_track_quat('Z', 'Y').to_euler()
        _sh.data.materials.append(_m)
        try: _sh.color = (rgb[0], rgb[1], rgb[2], 1.0)
        except Exception: pass
        bpy.ops.mesh.primitive_cone_add(radius1=2.4 * _gr, radius2=0.0, depth=3.4 * _gr,
                                        location=_gpos + _d * (_gl + 1.7 * _gr))
        _cn = bpy.context.object; _cn.name = "AxisTip_%s" % label
        _cn.rotation_euler = _d.to_track_quat('Z', 'Y').to_euler()
        _cn.data.materials.append(_m)
        try: _cn.color = (rgb[0], rgb[1], rgb[2], 1.0)
        except Exception: pass
        try:                                            # Achsen-Beschriftung (X/Y/Z)
            _tc = bpy.data.curves.new("axtxt_" + label, type='FONT'); _tc.body = label
            _to = bpy.data.objects.new("AxisLbl_" + label, _tc); scene.collection.objects.link(_to)
            _to.location = _gpos + _d * (_gl + 6.0 * _gr); _sc = 5.0 * _gr
            _to.scale = (_sc, _sc, _sc); _to.data.materials.append(_m)
            try: _to.color = (rgb[0], rgb[1], rgb[2], 1.0)
            except Exception: pass
        except Exception:
            pass
    _axis((1, 0, 0), (0.92, 0.16, 0.16), "X")
    _axis((0, 1, 0), (0.18, 0.82, 0.24), "Y")
    _axis((0, 0, 1), (0.28, 0.46, 1.0), "Z")

# --- 5b) VORSCHAU: EIN Standbild (Geometrie + Düsen + Strahllinien), OHNE Bake/Metrik ---
if PREVIEW:
    dom.hide_render = True                             # leere Domain (kein Fluid) nicht rendern
    scene.frame_set(F0)
    _pv_dir = CFG.get("preview_dir") or FRAMES_DIR
    # Drehteller: die Kamera um cam_tgt um die KAMERA-OBEN-ACHSE orbiten (folgt VIEW_DOWN). So dreht
    # sich der gerenderte Motor-Ausschnitt und lässt sich im Browser durch die Winkel ziehen.
    _pv_up  = mathutils.Vector(_UP2VEC.get(_cam_up, (0, 1, 0) if HORIZONTAL else (0, 0, 1)))
    _pv_ct  = cam_tgt.copy() if hasattr(cam_tgt, "copy") else mathutils.Vector(cam_tgt)
    _pv_rel0 = cam.location.copy() - _pv_ct
    _fill_rel0 = _fill.location.copy() - _pv_ct        # Fülllicht mit der Kamera mitdrehen
    _pv_n = PREVIEW_TURNS
    _pv_done = []
    for _k in range(_pv_n):
        if _pv_n > 1:
            _ang = 2.0 * math.pi * _k / _pv_n
            _rot = mathutils.Matrix.Rotation(_ang, 4, _pv_up)
            cam.location = _pv_ct + _rot @ _pv_rel0
            cam.rotation_euler = _track_quat(_pv_ct - cam.location, '-Z', _cam_up).to_euler()
            _fill.location = _pv_ct + _rot @ _fill_rel0     # Licht folgt → jede Seite beleuchtet
            _fill.rotation_euler = _track_quat(_pv_ct - _fill.location, '-Z', _cam_up).to_euler()
            _pv_png = os.path.join(_pv_dir, "preview_%03d.png" % _k)
        else:
            _pv_png = CFG.get("preview_png") or os.path.join(_pv_dir, "preview.png")
        scene.render.filepath = _pv_png
        try:
            bpy.ops.render.render(write_still=True)
            print("OIL_PREVIEW:" + _pv_png, flush=True)
            _pv_done.append(_pv_png)
        except Exception as e:
            print("OIL_STAGE:Vorschau-Render fehlgeschlagen: %s" % e, flush=True)
    print("OIL_PREVIEW_N:%d" % len(_pv_done), flush=True)
    print("OIL_DONE", flush=True)
    sys.exit(0)

# --- 6) Benetzungs-Metrik: KDTree Effector-Vertices vs Liquid-Vertices --------
from mathutils.kdtree import KDTree
depsgraph = bpy.context.evaluated_depsgraph_get()
wh_eval = wh.evaluated_get(depsgraph)
wh_mesh = wh_eval.to_mesh()
# Benetzung NUR gegen die Wickelkopf-Überhänge messen (|z|>Stirnfläche) — sonst verwässern die
# tausenden Kern-Vertices (Welle/Rotor/Stator) den Prozentwert, obwohl das Öl nur die Leiter trifft.
wh_world = [wh.matrix_world @ v.co for v in wh_mesh.vertices
            if abs((wh.matrix_world @ v.co).z) > (z_stack_end - 0.002)]
if not wh_world:                                     # Fallback: alle Vertices
    wh_world = [wh.matrix_world @ v.co for v in wh_mesh.vertices]
nwh = len(wh_world)
kd = KDTree(nwh)
for i, co in enumerate(wh_world): kd.insert(co, i)
kd.balance()
wh_eval.to_mesh_clear()
hit_count = [0] * nwh          # je Wickelkopf-Vertex: in wievielen Frames benetzt
total_wh = max(1, nwh)

def liquid_world_verts(fr):
    dg = bpy.context.evaluated_depsgraph_get()
    de = dom.evaluated_get(dg)
    me = de.to_mesh()
    vs = [dom.matrix_world @ v.co for v in me.vertices]
    # Inseln (Fragmente) zählen als Tropfen-Proxy via bmesh
    import bmesh
    bm = bmesh.new(); bm.from_mesh(me)
    seen = set(); islands = 0
    verts = bm.verts; verts.ensure_lookup_table()
    for sv in verts:
        if sv.index in seen: continue
        islands += 1; stack = [sv]; seen.add(sv.index)
        while stack:
            v = stack.pop()
            for e in v.link_edges:
                o = e.other_vert(v)
                if o.index not in seen:
                    seen.add(o.index); stack.append(o)
    bm.free()
    de.to_mesh_clear()
    return vs, islands

series = []      # {frame, wetted_pct, n_islands, n_liquid_verts}
log("Frames rendern + Benetzung messen")
for fr in range(F0, F1 + 1):
    scene.frame_set(fr)
    scene.render.filepath = os.path.join(FRAMES_DIR, "frame_%04d.png" % (fr - F0 + 1))
    try:
        bpy.ops.render.render(write_still=True)
    except Exception as e:
        print("OIL_STAGE:render frame %d fehlgeschlagen: %s" % (fr, e), flush=True)
    # Benetzung
    try:
        vs, islands = liquid_world_verts(fr)
    except Exception as e:
        vs, islands = [], 0
        print("OIL_STAGE:liquid frame %d: %s" % (fr, e), flush=True)
    frame_hit = set()
    for co in vs:
        _pos, idx, dist = kd.find(co)      # KDTree.find -> (position, index, distance)
        if idx is not None and dist is not None and dist <= BAND:
            frame_hit.add(idx)
    for idx in frame_hit: hit_count[idx] += 1
    wetted_pct = 100.0 * len(frame_hit) / total_wh
    series.append({"frame": fr, "wetted_pct": round(wetted_pct, 2),
                   "n_islands": int(islands), "n_liquid_verts": len(vs)})
    print("OIL_FRAMES:%d/%d" % (fr - F0 + 1, F1 - F0 + 1), flush=True)

# --- 7) Abdeckungs-Heatmap: Effector nach kumulierter Benetzung eingefärbt ----
cov_png = CFG.get("coverage_png")
if cov_png:
    try:
        log("Abdeckungs-Heatmap rendern")
        me = wh.data
        # Vertex-Color-Attribut (Corner-Domain) aus hit_count
        maxhit = max(1, max(hit_count))
        attr = me.color_attributes.new(name="Coverage", type='FLOAT_COLOR', domain='POINT')
        for i in range(len(me.vertices)):
            f = hit_count[i] / maxhit if i < len(hit_count) else 0.0
            # blau (0) -> rot (1)
            attr.data[i].color = (f, 0.15 * (1 - abs(2*f-1)), 1.0 - f, 1.0)
        covmat = bpy.data.materials.new("Cov"); covmat.use_nodes = True
        nt = covmat.node_tree
        for nnode in list(nt.nodes): nt.nodes.remove(nnode)
        out = nt.nodes.new("ShaderNodeOutputMaterial")
        emi = nt.nodes.new("ShaderNodeEmission")
        vc  = nt.nodes.new("ShaderNodeVertexColor"); vc.layer_name = "Coverage"
        emi.inputs["Strength"].default_value = 1.5
        nt.links.new(vc.outputs["Color"], emi.inputs["Color"])
        nt.links.new(emi.outputs["Emission"], out.inputs["Surface"])
        wh.data.materials.clear(); wh.data.materials.append(covmat)
        dom.hide_render = True
        scene.frame_set(F1)
        scene.render.filepath = cov_png
        bpy.ops.render.render(write_still=True)
        dom.hide_render = False
    except Exception as e:
        print("OIL_STAGE:coverage heatmap fehlgeschlagen: %s" % e, flush=True)

# --- 8) Kennwerte ausgeben ----------------------------------------------------
peak = max((s["wetted_pct"] for s in series), default=0.0)
mean = round(sum(s["wetted_pct"] for s in series) / max(1, len(series)), 2)
peak_drops = max((s["n_islands"] for s in series), default=0)
out = {"series": series,
       "wetted_pct_peak": round(peak, 2),
       "wetted_pct_mean": mean,
       "droplets_peak": int(peak_drops),
       "n_frames": len(series),
       "n_effector_verts": nwh,
       "wet_band_mm": round(BAND * 1000, 2)}
print("OIL_METRICS:" + json.dumps(out), flush=True)
print("OIL_DONE", flush=True)
'''


def _blender_script():
    return _BLENDER_SCRIPT


# ──────────────────────────────────────────────────────────────────────────────
# 3. Charts (matplotlib, aus den Metriken)
# ──────────────────────────────────────────────────────────────────────────────
def _b64_png(fig):
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _metric_charts(metrics, charts_dir):
    """Benetzungs-% und Tropfenzahl über die Frames → base64 + Dateien."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    os.makedirs(charts_dir, exist_ok=True)
    series = metrics.get("series") or []
    if not series:
        return {}
    fr = [s["frame"] for s in series]
    wet = [s["wetted_pct"] for s in series]
    drp = [s["n_islands"] for s in series]
    imgs = {}

    fig, ax = plt.subplots(figsize=(6.2, 3.2))
    ax.plot(fr, wet, color="#c0392b", lw=2)
    ax.fill_between(fr, wet, color="#c0392b", alpha=0.15)
    ax.set_xlabel("Frame"); ax.set_ylabel("benetzte Wickelkopf-Fläche [%]")
    ax.set_title("Benetzung über die Zeit (geometrischer Proxy)")
    ax.grid(alpha=0.3)
    imgs["oil_wetting"] = _b64_png(fig)

    fig2, ax2 = plt.subplots(figsize=(6.2, 3.2))
    ax2.plot(fr, drp, color="#2471a3", lw=2)
    ax2.set_xlabel("Frame"); ax2.set_ylabel("Öl-Fragmente (Tropfen-Proxy)")
    ax2.set_title("Tröpfchenbildung/Fragmentierung über die Zeit")
    ax2.grid(alpha=0.3)
    imgs["oil_droplets"] = _b64_png(fig2)

    # zusätzlich als Datei (für PDF-Report / Galerie)
    for key, b64 in imgs.items():
        try:
            with open(os.path.join(charts_dir, key + ".png"), "wb") as f:
                f.write(base64.b64decode(b64))
        except OSError:
            pass
    return imgs


# ──────────────────────────────────────────────────────────────────────────────
# 4. Orchestrator
# ──────────────────────────────────────────────────────────────────────────────
def run_oilspray(payload, project_dir, progress_cb=None, cancel_cb=None):
    """Führt die experimentelle Spritzöl-Simulation aus und persistiert das Ergebnis.

    ``payload``      — normaler Analyse-Payload (geom + axial_len) + Öl-Optionen unter
                       ``oil`` ({resolution, frames, section_slots, viscosity,
                       surface_tension, jet_speed, engine}).
    Rückgabe: ``results["oilspray"]``-Dict (Config + Kennwerte + Bild-Keys + video-Flag).
    """
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    geom = payload.get("geom") or {}
    axial_len = float(payload.get("axial_len", geom.get("axialLen", 100.0)) or 100.0)
    oil = payload.get("oil") or {}

    res     = _clamp(oil.get("resolution", DEFAULT_RES), *RES_RANGE, DEFAULT_RES)
    frames  = _clamp(oil.get("frames", DEFAULT_FRAMES), *FRAMES_RANGE, DEFAULT_FRAMES)
    section = _clamp(oil.get("section_slots", DEFAULT_SECTION), *SECTION_RANGE, DEFAULT_SECTION)
    # Standardmäßig DÜNNFLÜSSIG + niedrige Oberflächenspannung → das Öl spritzt/streamt statt zu
    # verklumpen (0 ist gültig: kein Viskositätslöser / keine Oberflächenspannung).
    _visc   = oil.get("viscosity", 0.004)
    visc    = float(0.004 if _visc is None else _visc)
    _surft  = oil.get("surface_tension", 0.01)
    surft   = float(0.01 if _surft is None else _surft)
    engine  = str(oil.get("engine", "BLENDER_EEVEE") or "BLENDER_EEVEE")
    # Spritzöl-Kühlring
    pressure = max(0.2, min(20.0, float(oil.get("pressure_bar", 3.0) or 3.0)))
    nozzles  = max(1, min(40, int(oil.get("nozzle_count", 6) or 6)))
    ring_gap = max(0.5, min(30.0, float(oil.get("ring_gap_mm", 3.0) or 3.0)))
    ring_tube = max(1.0, min(30.0, float(oil.get("ring_tube_mm", 6.0) or 6.0)))
    nozzle_d = max(0.3, min(6.0, float(oil.get("nozzle_d_mm", 1.0) or 1.0)))
    include_core = bool(oil.get("include_core", True))
    orientation = "vertical" if str(oil.get("orientation", "horizontal")) == "vertical" else "horizontal"
    closeup  = bool(oil.get("closeup", False))
    # Zeitlupe: 1 = Echtzeit … 500 = Ultra-Slow-Motion (Sim-Zeit pro Frame = 1/slowmo)
    slowmo   = max(1.0, min(500.0, float(oil.get("slowmo", 1.0) or 1.0)))
    fast     = bool(oil.get("fast", False))          # schnelle, grobe Vorschau
    # Bauteil-Häkchenlisten (Anzeigen / Schneiden) + Voll-/Ausschnitt-Ansicht.
    show_map = oil.get("show") if isinstance(oil.get("show"), dict) else None
    cut_map  = oil.get("cut") if isinstance(oil.get("cut"), dict) else None
    view_mode = "full" if str(oil.get("view_mode", "section")) == "full" else "section"
    # Strahlrichtung + Ziellinie
    jet_tilt = max(-60.0, min(60.0, float(oil.get("jet_tilt_deg", 0.0) or 0.0)))
    jet_yaw  = max(-60.0, min(60.0, float(oil.get("jet_yaw_deg", 0.0) or 0.0)))
    nozzle_offset = max(-45.0, min(45.0, float(oil.get("nozzle_offset_deg", 15.0) or 0.0)))
    jet_cone = max(0.0, min(40.0, float(oil.get("jet_cone_deg", 10.0) or 0.0)))
    show_jet_line = bool(oil.get("show_jet_line", False))
    # Ansicht/Darstellung: Unten-Achse (Blickrichtung), Glättung, Öl-Transparenz, Koordinatensystem.
    view_down = str(oil.get("view_down", "auto")).lower()
    smooth    = bool(oil.get("smooth", True))
    oil_tp    = max(0.0, min(1.0, float(oil.get("oil_transparency", 0.45) or 0.45)))
    show_axes = bool(oil.get("show_axes", False))
    # Wickelkopf komplett (alle Nuten, wie die anderen Bauteile) statt nur der Ausschnitt.
    winding_full = bool(oil.get("winding_full", False))
    # Untermenü: einzelne Hairpins (Pin-Index) ausblenden.
    hidden_pins = oil.get("hidden_pins") or []
    try:
        hidden_pins = [int(i) for i in hidden_pins]
    except (TypeError, ValueError):
        hidden_pins = []
    # Kamera-Fixwinkel aus der Vorschau-Drehteller-Auswahl (None = Standard-3/4-Ansicht).
    camera_angle = oil.get("camera_angle_deg")
    camera_angle = float(camera_angle) if camera_angle is not None else None
    # Beleuchtungs-Voreinstellung (s. LIGHT_PRESETS) — unbekannter Name fällt auf "studio" zurück.
    light_preset = str(oil.get("light_preset", DEFAULT_LIGHT_PRESET) or DEFAULT_LIGHT_PRESET)
    if light_preset not in LIGHT_PRESETS:
        light_preset = DEFAULT_LIGHT_PRESET
    if fast:
        engine = "BLENDER_WORKBENCH"                  # flaches, schnelles Rendern
    if closeup:
        nozzles = 1                                  # Nahaufnahme: EIN Strahl auf EINEN Leiter
    jet_v   = round(0.8 * (2.0 * pressure * 1e5 / 850.0) ** 0.5, 2)   # Info: v aus Druck

    work = os.path.join(project_dir, "oilspray_work")
    frames_dir = os.path.join(project_dir, FRAMES_SUBDIR)
    charts_dir = os.path.join(project_dir, "charts")
    os.makedirs(work, exist_ok=True)
    os.makedirs(frames_dir, exist_ok=True)
    # alte Frames aufräumen, damit ffmpeg keine Reste einer früheren Länge mischt
    for fn in os.listdir(frames_dir):
        if fn.startswith("frame_") or fn == "anim.mp4":
            try: os.remove(os.path.join(frames_dir, fn))
            except OSError: pass
    # alten Mantaflow-Cache verwerfen — sonst kann ein neuer Lauf mit geänderten Einstellungen
    # (z. B. Zeitlupe) stale Bake-Daten des vorigen Laufs wiederverwenden
    import shutil
    shutil.rmtree(os.path.join(project_dir, "blendcache_oil"), ignore_errors=True)

    # Debug-Log (Nutzerwunsch): alle aufgelösten Einstellungen + Verlauf, damit ein auffälliger
    # oder fehlgeschlagener Lauf 1:1 zurückgemeldet werden kann statt nur der Fehlermeldung.
    _dbg = [("Einstellungen (aufgelöst)", {
        "resolution": res, "frames": frames, "section_slots": section,
        "viscosity": visc, "surface_tension": surft, "engine": engine, "fast": fast,
        "pressure_bar": pressure, "nozzle_count": nozzles, "ring_gap_mm": ring_gap,
        "ring_tube_mm": ring_tube, "nozzle_d_mm": nozzle_d, "include_core": include_core,
        "orientation": orientation, "closeup": closeup, "slowmo": slowmo,
        "view_mode": view_mode, "show": show_map, "cut": cut_map,
        "jet_tilt_deg": jet_tilt, "jet_yaw_deg": jet_yaw, "nozzle_offset_deg": nozzle_offset,
        "jet_cone_deg": jet_cone, "show_jet_line": show_jet_line, "view_down": view_down,
        "smooth": smooth, "oil_transparency": oil_tp, "show_axes": show_axes,
        "winding_full": winding_full, "hidden_pins": hidden_pins,
        "camera_angle_deg": camera_angle, "light_preset": light_preset,
        "axial_len": axial_len, "geom": geom,
    })]
    _dbg_write(work, _dbg)

    # 1) STL exportieren (je Bauteil eine Datei; Keilausschnitt inkl. Kern)
    parts, stl_log = _export_winding_stl(geom, axial_len, work, section, _log,
                                         include_core=include_core,
                                         components=show_map, cut=cut_map,
                                         view_mode=view_mode,
                                         hidden_pins=hidden_pins, winding_full=winding_full)
    _dbg.append(("STL-Export", {"ok": bool(parts), "parts": sorted(parts) if parts else None,
                                "log": stl_log}))
    _dbg_write(work, _dbg)
    if not parts:
        raise RuntimeError("Motor-Ausschnitt-STL-Export fehlgeschlagen: %s\n(Log mit allen "
                           "Einstellungen: %s)" % (stl_log, _dbg_path(work)))
    _log("✓ Motor-Ausschnitt exportiert (%s Nuten%s)"
         % ("alle" if winding_full else section, ", mit Kern" if include_core else ""), 12)

    # 2) Blender-Config
    cov_png = os.path.join(charts_dir, "oil_coverage.png")
    os.makedirs(charts_dir, exist_ok=True)
    cfg = {"stl_parts": parts, "frames_dir": frames_dir, "resolution": res,
           "frame_start": 1, "frame_end": frames, "viscosity": visc,
           "surface_tension": surft, "engine": engine, "coverage_png": cov_png,
           "mesh_scale": 0.001, "wet_band_m": 0.004,
           "pressure_bar": pressure, "nozzle_count": nozzles, "ring_gap_mm": ring_gap,
           "ring_tube_mm": ring_tube, "nozzle_d_mm": nozzle_d,
           "stack_half_mm": axial_len / 2.0, "include_core": include_core,
           "camera_angle_deg": camera_angle,
           "shaft_d_mm": float(geom.get("shaftD", 60.0) or 60.0),
           "rotor_od_mm": float(geom.get("rotorOD", 188.0) or 188.0),
           "stator_id_mm": float(geom.get("statorID", 190.0) or 190.0),
           "time_scale": 1.0 / slowmo,
           "orientation": orientation, "closeup": closeup, "fast": fast,
           "jet_tilt_deg": jet_tilt, "jet_yaw_deg": jet_yaw,
           "nozzle_offset_deg": nozzle_offset, "jet_cone_deg": jet_cone,
           "show_jet_line": show_jet_line, "view_down": view_down,
           "smooth": smooth, "oil_transparency": oil_tp, "show_axes": show_axes,
           "light": _resolve_light_preset(light_preset)}
    cfg_path = os.path.join(work, "oil_cfg.json")
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)

    if cancel_cb and cancel_cb():
        raise RuntimeError("abgebrochen")

    # 3) Blender headless
    _log("💧 Spritzring: %d Düsen (Ø%.1f mm) im Abstand %.1f mm, %.1f bar → Strahl %.1f m/s"
         % (nozzles, nozzle_d, ring_gap, pressure, jet_v), 15)
    _log("💧 Blender/Mantaflow-Bake (Auflösung %d, %d Frames%s) …"
         % (res, frames, ", %.0f×-Zeitlupe" % slowmo if slowmo > 1 else ""), 16)
    _log("ℹ Der FLIP-Bake läuft auf der CPU — die GPU beschleunigt nur das Rendern. "
         "Feine 1-mm-Düsen brauchen hohe Auflösung.", None)
    br = blender_runner.run_blender_script(
        _blender_script(), argv=[cfg_path], cwd=work, timeout=7200, progress_cb=_log)

    _dbg.append(("Blender-Lauf", {"ok": br.get("ok"), "aborted": br.get("aborted"),
                                  "error": br.get("error"),
                                  "engine_gewählt": engine, "material_light": light_preset,
                                  "stdout_tail": (br.get("stdout") or "")[-6000:]}))
    _dbg_write(work, _dbg)
    if br.get("aborted"):
        raise RuntimeError("abgebrochen")
    metrics = br.get("metrics") or {}
    if not br.get("ok") and not metrics:
        tail = (br.get("stdout") or "")[-800:]
        raise RuntimeError("Blender-Simulation fehlgeschlagen: %s\n%s\n(Log mit allen "
                           "Einstellungen: %s)" % (br.get("error"), tail, _dbg_path(work)))

    # 4) Video + Charts
    _log("🎬 Video kodieren (ffmpeg) …", 92)
    import ema_em3d
    video = ema_em3d._encode_video(frames_dir, fps=int(oil.get("fps", 24) or 24))
    charts = _metric_charts(metrics, charts_dir)

    images = {}
    images.update(charts)
    if os.path.exists(cov_png):
        with open(cov_png, "rb") as f:
            images["oil_coverage"] = base64.b64encode(f.read()).decode()

    result = {
        "source": "blender_mantaflow",
        "config": {"resolution": res, "frames": frames, "section_slots": section,
                   "viscosity": visc, "surface_tension": surft, "engine": engine,
                   "pressure_bar": pressure, "nozzle_count": nozzles,
                   "ring_gap_mm": ring_gap, "ring_tube_mm": ring_tube,
                   "nozzle_d_mm": nozzle_d, "jet_speed_mps": jet_v,
                   "orientation": orientation, "closeup": closeup, "slowmo": slowmo,
                   "fast": fast, "view_mode": view_mode,
                   "jet_tilt_deg": jet_tilt, "jet_yaw_deg": jet_yaw,
                   "nozzle_offset_deg": nozzle_offset, "jet_cone_deg": jet_cone,
                   "show_jet_line": show_jet_line, "view_down": view_down,
                   "smooth": smooth, "oil_transparency": oil_tp,
                   "winding_full": winding_full, "hidden_pins": hidden_pins,
                   "camera_angle_deg": camera_angle, "light_preset": light_preset},
        "metrics": {k: v for k, v in metrics.items() if k != "series"},
        "series": metrics.get("series", []),
        "images": images,
        "video": bool(video),
        "note": ("Qualitative Blender/Mantaflow-Studie (FLIP). KEIN Temperaturfeld / "
                 "Wärmeübergang — die Kennwerte sind geometrische Benetzungs-Proxys."),
        "debug_log": _dbg_path(work),
    }
    _dbg.append(("Ergebnis", {"metrics": result["metrics"], "video": bool(video)}))
    _dbg_write(work, _dbg)
    _persist(project_dir, result)
    # Jeden fertigen Lauf AUTOMATISCH als eigene Variante ablegen (Nutzer: „bei den Videos
    # sollen immer alle Varianten automatisch gespeichert werden") — Video + Charts wandern in
    # einen eigenen Store-Ordner, sodass ein neuer Lauf die vorherigen NICHT überschreibt.
    try:
        rid = _autosave_variant(project_dir, result, frames_dir)
        if rid:
            result["saved_id"] = rid
            _log("💾 Variante automatisch gespeichert (%s)." % rid, None)
    except Exception as _e:
        _log("⚠ Auto-Speichern der Variante fehlgeschlagen: %s" % _e, None)
    _log("✓ Spritzöl-Simulation fertig.", 100)
    return result


def preview_oilspray(payload, project_dir, progress_cb=None, cancel_cb=None):
    """Schnelle **Zwischenansicht** VOR dem teuren Bake: rendert nur Geometrie + Düsen + die
    Strahl-**Ziellinien** als EIN Standbild (kein Mantaflow-Bake). Zeigt vorab, wohin die Strahlen
    zeigen. Teilt sich die Optionen mit ``run_oilspray`` (Ausschnitt/Anzeigen/Schneiden/Richtung),
    berührt aber weder ``frames_oil`` noch den Bake-Cache noch ``results.json``.
    ``oil["preview_turns"]`` > 1 ⇒ **Drehteller**: N Kamera-Winkel rund um die Motorachse, sodass
    sich das gerenderte Bild im Browser drehen (ziehen) lässt.
    Rückgabe: ``{"image": <base64 png>, "images": [<base64 png>, …], "turns": N, "config": {...}}``."""
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    geom = payload.get("geom") or {}
    axial_len = float(payload.get("axial_len", geom.get("axialLen", 100.0)) or 100.0)
    oil = payload.get("oil") or {}

    section = _clamp(oil.get("section_slots", DEFAULT_SECTION), *SECTION_RANGE, DEFAULT_SECTION)
    show_map = oil.get("show") if isinstance(oil.get("show"), dict) else None
    cut_map  = oil.get("cut") if isinstance(oil.get("cut"), dict) else None
    view_mode = "full" if str(oil.get("view_mode", "section")) == "full" else "section"
    pressure = max(0.2, min(20.0, float(oil.get("pressure_bar", 3.0) or 3.0)))
    nozzles  = max(1, min(40, int(oil.get("nozzle_count", 6) or 6)))
    ring_gap = max(0.5, min(30.0, float(oil.get("ring_gap_mm", 3.0) or 3.0)))
    ring_tube = max(1.0, min(30.0, float(oil.get("ring_tube_mm", 6.0) or 6.0)))
    nozzle_d = max(0.3, min(6.0, float(oil.get("nozzle_d_mm", 1.0) or 1.0)))
    include_core = bool(oil.get("include_core", True))
    orientation = "vertical" if str(oil.get("orientation", "horizontal")) == "vertical" else "horizontal"
    closeup  = bool(oil.get("closeup", False))
    jet_tilt = max(-60.0, min(60.0, float(oil.get("jet_tilt_deg", 0.0) or 0.0)))
    jet_yaw  = max(-60.0, min(60.0, float(oil.get("jet_yaw_deg", 0.0) or 0.0)))
    nozzle_offset = max(-45.0, min(45.0, float(oil.get("nozzle_offset_deg", 15.0) or 0.0)))
    jet_cone = max(0.0, min(40.0, float(oil.get("jet_cone_deg", 10.0) or 0.0)))
    winding_full = bool(oil.get("winding_full", False))
    hidden_pins = oil.get("hidden_pins") or []
    try:
        hidden_pins = [int(i) for i in hidden_pins]
    except (TypeError, ValueError):
        hidden_pins = []
    # Drehteller-Vorschau: N Kamera-Winkel → das gerenderte Bild lässt sich im Browser drehen.
    # 1 = ein Standbild (alt). Geklemmt 1..72.
    preview_turns = max(1, min(72, int(oil.get("preview_turns", 1) or 1)))
    view_down = str(oil.get("view_down", "auto")).lower()   # welche Achse zeigt nach unten
    material  = bool(oil.get("material", True))             # mit Materialien (EEVEE) statt flach
                                                              # Standard AN — Workbench zeigte sonst
                                                              # flaches Grau/Weiß und wirkte wie ein
                                                              # Beleuchtungs-/Materialfehler.
    smooth    = bool(oil.get("smooth", True))               # Netzfacetten glätten
    oil_tp    = max(0.0, min(1.0, float(oil.get("oil_transparency", 0.45) or 0.45)))
    light_preset = str(oil.get("light_preset", DEFAULT_LIGHT_PRESET) or DEFAULT_LIGHT_PRESET)
    if light_preset not in LIGHT_PRESETS:
        light_preset = DEFAULT_LIGHT_PRESET
    if closeup:
        nozzles = 1

    work = os.path.join(project_dir, "oilspray_preview")
    pv_frames = os.path.join(work, "pv_frames")           # isoliert von frames_oil/blendcache
    os.makedirs(pv_frames, exist_ok=True)
    # Alte Drehteller-Bilder wegräumen, sonst mischt ein früherer Lauf mit mehr Winkeln hinein.
    for _old in os.listdir(pv_frames):
        if _old.startswith("preview_") and _old.endswith(".png"):
            try: os.remove(os.path.join(pv_frames, _old))
            except OSError: pass
    preview_png = os.path.join(work, "preview.png")

    _dbg = [("Einstellungen (aufgelöst)", {
        "section_slots": section, "show": show_map, "cut": cut_map, "view_mode": view_mode,
        "pressure_bar": pressure, "nozzle_count": nozzles, "ring_gap_mm": ring_gap,
        "ring_tube_mm": ring_tube, "nozzle_d_mm": nozzle_d, "include_core": include_core,
        "orientation": orientation, "closeup": closeup,
        "jet_tilt_deg": jet_tilt, "jet_yaw_deg": jet_yaw, "nozzle_offset_deg": nozzle_offset,
        "jet_cone_deg": jet_cone, "winding_full": winding_full, "hidden_pins": hidden_pins,
        "preview_turns": preview_turns, "view_down": view_down, "material": material,
        "smooth": smooth, "oil_transparency": oil_tp, "light_preset": light_preset,
        "axial_len": axial_len, "geom": geom,
    })]
    _dbg_write(work, _dbg)

    # 1) STL (Ausschnitt inkl. Anzeige-/Schnittlisten) — schnell (nur Ausschnitts-Nuten)
    parts, stl_log = _export_winding_stl(geom, axial_len, work, section, _log,
                                         include_core=include_core,
                                         components=show_map, cut=cut_map,
                                         view_mode=view_mode,
                                         hidden_pins=hidden_pins, winding_full=winding_full)
    _dbg.append(("STL-Export", {"ok": bool(parts), "parts": sorted(parts) if parts else None,
                                "log": stl_log}))
    _dbg_write(work, _dbg)
    if not parts:
        raise RuntimeError("Motor-Ausschnitt-STL-Export fehlgeschlagen: %s\n(Log mit allen "
                           "Einstellungen: %s)" % (stl_log, _dbg_path(work)))
    _log("✓ Ausschnitt exportiert — Vorschau rendern (ohne Bake) …", 40)

    if cancel_cb and cancel_cb():
        raise RuntimeError("abgebrochen")

    cfg = {"stl_parts": parts, "frames_dir": pv_frames, "resolution": 48,
           "frame_start": 1, "frame_end": 1, "mesh_scale": 0.001,
           "pressure_bar": pressure, "nozzle_count": nozzles, "ring_gap_mm": ring_gap,
           "ring_tube_mm": ring_tube, "nozzle_d_mm": nozzle_d,
           "stack_half_mm": axial_len / 2.0, "include_core": include_core,
           "shaft_d_mm": float(geom.get("shaftD", 60.0) or 60.0),
           "rotor_od_mm": float(geom.get("rotorOD", 188.0) or 188.0),
           "stator_id_mm": float(geom.get("statorID", 190.0) or 190.0),
           "orientation": orientation, "closeup": closeup,
           "jet_tilt_deg": jet_tilt, "jet_yaw_deg": jet_yaw,
           "nozzle_offset_deg": nozzle_offset, "jet_cone_deg": jet_cone,
           "show_jet_line": True, "preview": True, "preview_png": preview_png,
           "preview_dir": pv_frames, "preview_turns": preview_turns,
           "view_down": view_down, "show_axes": True, "smooth": smooth,
           "oil_transparency": oil_tp, "light": _resolve_light_preset(light_preset),
           # Mit Materialien → EEVEE (Kupfer/Stahl/Öl); sonst flaches, schnelles Workbench-Rendern.
           "engine": ("BLENDER_EEVEE" if material else "BLENDER_WORKBENCH"), "fast": True}
    cfg_path = os.path.join(work, "oil_preview_cfg.json")
    with open(cfg_path, "w") as f:
        json.dump(cfg, f)

    _log("🔍 Blender-Vorschau (nur Geometrie + Düsen + Strahllinien) …", 55)
    br = blender_runner.run_blender_script(
        _blender_script(), argv=[cfg_path], cwd=work, timeout=1200, progress_cb=_log)
    _dbg.append(("Blender-Lauf", {"ok": br.get("ok"), "aborted": br.get("aborted"),
                                  "error": br.get("error"),
                                  "engine_gewählt": cfg["engine"], "material": material,
                                  "light_preset": light_preset,
                                  "stdout_tail": (br.get("stdout") or "")[-6000:]}))
    _dbg_write(work, _dbg)
    if br.get("aborted"):
        raise RuntimeError("abgebrochen")

    # Drehteller-Bilder einsammeln (preview_000.png … in Winkelreihenfolge); Einzel-Standbild als
    # Rückfall. Fehlt jede Datei ⇒ Render fehlgeschlagen.
    if preview_turns > 1:
        pngs = sorted(os.path.join(pv_frames, f) for f in os.listdir(pv_frames)
                      if f.startswith("preview_") and f.endswith(".png"))
    else:
        pngs = [preview_png] if os.path.exists(preview_png) else []
    if not pngs:
        tail = (br.get("stdout") or "")[-800:]
        raise RuntimeError("Vorschau-Render fehlgeschlagen: %s\n%s\n(Log mit allen "
                           "Einstellungen: %s)" % (br.get("error"), tail, _dbg_path(work)))

    images = []
    for p in pngs:
        with open(p, "rb") as f:
            images.append(base64.b64encode(f.read()).decode())
    _log("✓ Vorschau fertig.", 100)
    return {"image": images[0], "images": images, "turns": len(images),
            "config": {"section_slots": section, "view_mode": view_mode,
                       "orientation": orientation, "closeup": closeup,
                       "nozzle_count": nozzles, "jet_tilt_deg": jet_tilt,
                       "jet_yaw_deg": jet_yaw, "nozzle_offset_deg": nozzle_offset,
                       "jet_cone_deg": jet_cone, "winding_full": winding_full,
                       "hidden_pins": hidden_pins, "turns": len(images),
                       "view_down": view_down, "material": material, "smooth": smooth,
                       "light_preset": light_preset},
            "debug_log": _dbg_path(work)}


def _persist(project_dir, result):
    """Schlanke Zusammenfassung (ohne base64-Bilder, Bild-Dateien liegen in charts/) in die
    ``results.json`` des Projekts mergen. Fehlt die Datei (Lauf ohne vorherige Analyse), wird
    sie ANGELEGT — sonst wäre der Öl-Lauf nach dem Neuladen weg („Speicherfunktion fehlt")."""
    rj = os.path.join(project_dir, "results.json")
    try:
        data = {}
        if os.path.exists(rj):
            with open(rj) as f:
                data = json.load(f)
        lean = {k: v for k, v in result.items() if k != "images"}
        lean["image_files"] = {k: "charts/%s.png" % k for k in result.get("images", {})}
        data["oilspray"] = lean
        tmp = rj + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, rj)
    except (OSError, ValueError):
        pass


def load_saved(project_dir):
    """Gespeicherten Öl-Lauf eines Projekts laden: ``results.json["oilspray"]`` + die als
    Dateien persistierten Charts (image_files) wieder als base64 einlesen → Dict im selben
    Format wie ``run_oilspray`` (für ``_renderOil`` im Frontend). None wenn keiner existiert."""
    rj = os.path.join(project_dir, "results.json")
    if not os.path.exists(rj):
        return None
    try:
        with open(rj) as f:
            saved = json.load(f).get("oilspray")
    except (OSError, ValueError):
        return None
    if not saved:
        return None
    images = {}
    for key, rel in (saved.get("image_files") or {}).items():
        p = os.path.join(project_dir, rel)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    images[key] = base64.b64encode(f.read()).decode()
            except OSError:
                pass
    out = dict(saved)
    out["images"] = images
    # Video nur melden, wenn die Datei wirklich noch da ist
    out["video"] = os.path.exists(os.path.join(project_dir, FRAMES_SUBDIR, "anim.mp4"))
    return out


# ──────────────────────────────────────────────────────────────────────────────
# 5. Varianten-Store (jeder Lauf wird automatisch als eigene Variante abgelegt)
# ──────────────────────────────────────────────────────────────────────────────
RUNS_SUBDIR = "oilspray_runs"


def _runs_root(project_dir):
    return os.path.join(project_dir, RUNS_SUBDIR)


def _autosave_variant(project_dir, result, frames_dir):
    """Legt den fertigen Lauf als eigene Variante unter ``<projekt>/oilspray_runs/<id>/`` ab:
    Video (anim.mp4) + Chart-PNGs kopiert, ``run.json`` (Config/Kennwerte/Serie, ohne base64).
    So überschreibt ein neuer Lauf die vorherigen NICHT. Returns die Varianten-ID (Zeitstempel)."""
    import time as _t, shutil as _sh
    rid = _t.strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(_runs_root(project_dir), rid)
    os.makedirs(dest, exist_ok=True)
    # Video kopieren
    src_mp4 = os.path.join(frames_dir, "anim.mp4")
    has_video = os.path.exists(src_mp4)
    if has_video:
        try: _sh.copy(src_mp4, os.path.join(dest, "anim.mp4"))
        except OSError: has_video = False
    # Chart-PNGs kopieren (aus charts/) → in den Store, damit sie stabil bleiben
    charts_dir = os.path.join(project_dir, "charts")
    image_files = {}
    for key in (result.get("images") or {}):
        src = os.path.join(charts_dir, key + ".png")
        if os.path.exists(src):
            try:
                _sh.copy(src, os.path.join(dest, key + ".png"))
                image_files[key] = key + ".png"
            except OSError:
                pass
    run = {k: v for k, v in result.items() if k != "images"}
    run["image_files"] = image_files
    run["video"] = has_video
    run["id"] = rid
    run["timestamp"] = _t.strftime("%Y-%m-%d %H:%M")
    try:
        with open(os.path.join(dest, "run.json"), "w") as f:
            json.dump(run, f, ensure_ascii=False)
    except OSError:
        pass
    return rid


def list_saved_runs(project_dir):
    """Liste aller Öl-Varianten eines Projekts (id, Zeit, Kurz-Kennwerte), neueste zuerst."""
    root = _runs_root(project_dir)
    out = []
    if not os.path.isdir(root):
        return out
    for rid in sorted(os.listdir(root), reverse=True):
        d = os.path.join(root, rid)
        rp = os.path.join(d, "run.json")
        if not os.path.isdir(d) or not os.path.exists(rp):
            continue
        try:
            with open(rp) as f:
                run = json.load(f)
        except (OSError, ValueError):
            continue
        cfg = run.get("config") or {}
        met = run.get("metrics") or {}
        out.append({
            "id": rid,
            "timestamp": run.get("timestamp", rid),
            "video": bool(run.get("video")) and os.path.exists(os.path.join(d, "anim.mp4")),
            "resolution": cfg.get("resolution"),
            "frames": cfg.get("frames"),
            "slowmo": cfg.get("slowmo"),
            "closeup": cfg.get("closeup"),
            "orientation": cfg.get("orientation"),
            "view_mode": cfg.get("view_mode"),
            "wetted_pct_mean": met.get("wetted_pct_mean"),
            "wetted_pct_peak": met.get("wetted_pct_peak"),
        })
    return out


def load_saved_run(project_dir, rid):
    """Eine gespeicherte Öl-Variante laden → Dict im ``run_oilspray``-Format (images als base64
    aus den Store-PNGs, ``video_src`` zeigt auf die Variante). None wenn nicht vorhanden."""
    d = os.path.join(_runs_root(project_dir), rid)
    rp = os.path.join(d, "run.json")
    if not os.path.exists(rp):
        return None
    try:
        with open(rp) as f:
            run = json.load(f)
    except (OSError, ValueError):
        return None
    images = {}
    for key, rel in (run.get("image_files") or {}).items():
        p = os.path.join(d, rel)
        if os.path.exists(p):
            try:
                with open(p, "rb") as f:
                    images[key] = base64.b64encode(f.read()).decode()
            except OSError:
                pass
    out = dict(run)
    out["images"] = images
    out["video"] = bool(run.get("video")) and os.path.exists(os.path.join(d, "anim.mp4"))
    return out


def saved_run_video(project_dir, rid):
    """Absoluter Pfad zur MP4 einer gespeicherten Variante (oder None)."""
    p = os.path.join(_runs_root(project_dir), rid, "anim.mp4")
    return p if os.path.exists(p) else None


def delete_saved_run(project_dir, rid):
    import shutil as _sh
    d = os.path.join(_runs_root(project_dir), rid)
    if os.path.isdir(d):
        _sh.rmtree(d, ignore_errors=True)
        return True
    return False
