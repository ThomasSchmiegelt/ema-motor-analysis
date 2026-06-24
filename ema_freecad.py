"""FreeCAD script builders for IPM rotor geometry and structural FEM."""

import math
import json

from ema_topology import magnet_legs, leg_records


def build_em_rotor_script(geom: dict, axial_len: float, save_path: str) -> str:
    """Return FreeCAD Python code that creates IPM rotor with magnet pockets."""
    R_rot = geom["rotorOD"] / 2
    R_shaft = geom["shaftD"] / 2
    poles = int(geom["p"]) * 2

    # Magnet placement from the single source of truth (ema_topology).
    legs, _meta = magnet_legs(geom)
    recs_json = json.dumps(leg_records(legs))

    tol = 0.4   # pocket oversize for clean cut

    return f"""\
import FreeCAD as App
import Part
import math
import json as _json

doc = App.newDocument("Rotor")

R_rot    = {R_rot}
R_shaft  = {R_shaft}
axial    = {axial_len}
poles    = {poles}
tol      = {tol}
legs     = {recs_json}   # pole-local magnet placement records (ema_topology)

# Main rotor disc
rotor = Part.makeCylinder(R_rot, axial, App.Vector(0, 0, -axial / 2))
shaft = Part.makeCylinder(R_shaft, axial + 4, App.Vector(0, 0, -axial / 2 - 2))
rotor = rotor.cut(shaft)
if not rotor.isValid():
    raise RuntimeError("Rotor base invalid")

for i in range(poles):
    pole_ang = i * (2 * math.pi / poles)
    cos_p = math.cos(pole_ang)
    sin_p = math.sin(pole_ang)

    for rec in [lg for lg in legs if lg["placement"] == "interior"]:
        cx_l = rec["cx"]; cy_l = rec["cy"]; h_ang = rec["rot"]
        L = rec["length"]; T = rec["thick"]
        # Centre in global frame
        cx = cx_l * cos_p - cy_l * sin_p
        cy = cx_l * sin_p + cy_l * cos_p

        # Box centred at origin, long axis along X
        pkt = Part.makeBox(L + tol, T + tol, axial + 4,
                           App.Vector(-(L + tol) / 2, -(T + tol) / 2, -axial / 2 - 2))

        # Rotate by (pole_ang + h_ang)
        m = App.Matrix()
        m.rotateZ(pole_ang + h_ang)
        pkt = pkt.transformGeometry(m)

        # Translate to magnet centre
        pkt.translate(App.Vector(cx, cy, 0))

        rotor = rotor.cut(pkt)
        if not rotor.isValid():
            raise RuntimeError(f"Rotor invalid after pocket pole={{i}}")

result = rotor
obj = doc.addObject("Part::Feature", "Rotor")
obj.Shape = result
doc.recompute()

_faces = []
for _i, _f in enumerate(result.Faces):
    try:
        _n = _f.normalAt(0, 0)
        _c = _f.CenterOfMass
        _faces.append({{
            "index": _i,
            "area_mm2": round(_f.Area, 2),
            "centroid": {{"x": round(_c.x,2), "y": round(_c.y,2), "z": round(_c.z,2)}},
            "normal":   {{"x": round(_n.x,3), "y": round(_n.y,3), "z": round(_n.z,3)}},
        }})
    except Exception:
        pass

print("CAD_FACES:" + _json.dumps(_faces))
print(f"CAD_VOLUME:{{result.Volume:.2f}}")
doc.saveAs(r"{save_path}")
print("SAVED:{save_path}")
print("CAD_SUCCESS")
"""


def build_full_motor_script(geom: dict, axial_len: float, save_path: str,
                            winding_debug: bool = False) -> str:
    """Return FreeCAD Python code that creates a full IPM motor assembly:
    Shaft · Rotor iron · Magnets (N/S) · Stator iron · Hairpin conductors (3-phase).
    All parts are separate named objects with distinct colours.

    ``winding_debug=True`` emits each physical U-pin as its own ``Pin_NNN`` object
    (instead of three phase compounds) so a collision test can treat each pin as one
    conductor and check only *inter*-pin overlaps.
    """
    R_so      = geom["statorOD"] / 2
    R_si      = geom["statorID"] / 2
    R_rot     = geom["rotorOD"]  / 2
    R_shaft   = geom["shaftD"]   / 2
    poles     = int(geom["p"]) * 2
    n_slots   = int(geom["slots"])
    slot_dep  = float(geom["slotDepth"])
    sw_ratio  = float(geom.get("slotWidthRatio", 0.5))
    axial     = axial_len

    import math as _m
    dtheta  = 2 * _m.pi / n_slots
    slot_w  = max(3.0, R_si * dtheta * sw_ratio)

    # Magnet placement comes from the single source of truth (ema_topology).
    legs, _meta = magnet_legs(geom)
    recs_json = json.dumps(leg_records(legs))
    R_bore = float(geom.get("shaftBoreD", 0)) / 2   # hollow shaft (0 = solid)

    # Hairpin winding: C conductors/slot (even), coil pitch y in slot steps
    # (0/auto → full pitch = slots/poles, i.e. round(n_slots/poles)).
    n_layers  = int(geom.get("conductorsPerSlot", 2))
    n_layers  = max(2, min(12, n_layers + (n_layers % 2)))   # clamp to even 2..12
    coil_pitch = int(geom.get("coilPitch", 0) or 0)
    if coil_pitch <= 0:
        coil_pitch = max(1, round(n_slots / max(1, poles)))
    coil_pitch = max(1, min(n_slots - 1, coil_pitch))
    ins       = 0.8
    cond_w    = max(1.5, slot_w - 2 * ins)
    layer_h   = max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)

    # Winding-head (Wickelkopf) shape: smooth loft "Zugkörper" flaring radially out.
    wh_flare  = max(0.0, min(25.0, float(geom.get("windingHeadFlare", 6.0))))
    wh_style  = str(geom.get("windingHeadStyle", "sweep"))
    if wh_style not in ("sweep", "box"):
        wh_style = "sweep"

    # Shaft–laminated-core connection: press fit / spline / polygon (P3G).
    shaft_conn = str(geom.get("shaftConnection", "press"))
    if shaft_conn not in ("press", "spline", "polygon"):
        shaft_conn = "press"
    spline_teeth = max(3, min(40, int(geom.get("splineTeeth", 10))))
    spline_depth = max(0.5, min(8.0, float(geom.get("splineToothDepthMm", 2.0))))
    poly_lobes   = max(3, min(5, int(geom.get("polygonLobes", 3))))
    poly_ecc     = max(0.3, min(8.0, float(geom.get("polygonEccMm", 2.0))))

    # Stepwise geometry — per-component build toggles (CAD only; the EM/thermal/
    # structural solvers compute from parameters and are unaffected). Absent keys
    # default to the historical FULL build: all core parts on, with bearings and
    # winding-head insulation as new optional extras (off by default).
    gen_shaft   = bool(geom.get("genShaft",        True))
    gen_rotor   = bool(geom.get("genRotorIron",    True))
    gen_magnets = bool(geom.get("genMagnets",      True))
    gen_stator  = bool(geom.get("genStatorIron",   True))
    gen_hairpin = bool(geom.get("genHairpins",     True))   # straight slot bars + tabs
    gen_whead   = bool(geom.get("genWindingHeads", True))   # U-crowns (need hairpins)
    gen_bear_a  = bool(geom.get("genBearingA",     False))  # A-side bearing (−z)
    gen_bear_b  = bool(geom.get("genBearingB",     False))  # B-side bearing (+z)
    gen_insul   = bool(geom.get("genInsulation",   False))  # winding-head paper
    bearing_od  = max(0.0,  float(geom.get("bearingODmm",     0)))      # 0 = auto
    bearing_w   = max(2.0,  min(80.0,  float(geom.get("bearingWidthMm", 14))))
    bearing_gap = max(0.0,  min(120.0, float(geom.get("bearingGapMm",    5))))
    insul_thk   = max(0.1,  min(3.0,   float(geom.get("insulationThkMm", 0.4))))

    # Balance-disc bolts: optional through-holes (+ bolt solids) for the screws that
    # fasten the balancing discs through the WHOLE lamination stack. Count is coupled
    # to the pole count, fully symmetric on a pitch circle (adjustable diameter +
    # angular offset). Thread M4 and up → clearance hole = nominal Ø + 0.4 mm
    # (e.g. M6 → 6.4 mm). CAD-only (like the bearing/insulation extras), but the cut
    # lands in the "Rotor" solid so the centrifugal FEM sees the holes too.
    gen_balance  = bool(geom.get("genBalanceBolts", False))
    bal_thread   = str(geom.get("balanceBoltThread", "M6")).upper()
    bal_circle_d = max(0.0, float(geom.get("balanceBoltCircleD", 0)))    # 0 = auto
    bal_offset   = float(geom.get("balanceBoltOffsetDeg", 0))

    # Flux barriers: optional radial AIR slots cut into the rotor iron, independently
    # toggleable for the q-axis (between poles → cuts inter-pole leakage) and the
    # d-axis (pole centre, between a pole's two V-arms). One slot per pole each, fully
    # symmetric. Cut into the "Rotor" solid → the centrifugal FEM sees them too; the
    # FDM rasteriser carves the same slots so the magnetic simulation reflects them.
    gen_fb_q   = bool(geom.get("genFluxBarrierQ", False))
    gen_fb_d   = bool(geom.get("genFluxBarrierD", False))
    fb_width   = max(0.5, min(40.0, float(geom.get("fluxBarrierWidth", 3.0))))
    fb_depth   = max(1.0, min(120.0, float(geom.get("fluxBarrierDepth", 10.0))))

    # Custom (designer) free-form barriers: list of {pts:[[x,y],…] (pole-local mm),
    # width}. Replicated per pole, cut as air capsules into the rotor iron.
    custom_barriers = geom.get("customBarriers") or []
    custom_barriers_json = json.dumps(custom_barriers)

    # Magnet-to-pocket clearance per side [mm] (the visible air gap around magnets).
    mag_gap = max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))

    return f"""\
import FreeCAD as App
import Part
import math
import json as _json

doc = App.newDocument("Motor")

R_so      = {R_so};   R_si    = {R_si}
R_rot     = {R_rot};  R_shaft = {R_shaft}
R_bore    = {R_bore}
axial     = {axial}
poles     = {poles};  n_slots = {n_slots}
slot_dep  = {slot_dep}; slot_w = {slot_w:.4f}
legs      = {recs_json}   # pole-local magnet placement records (ema_topology)
n_layers  = {n_layers}; ins   = {ins}; cond_w = {cond_w:.4f}; layer_h = {layer_h:.4f}
coil_pitch = {coil_pitch}
WIND_DEBUG = {winding_debug!r}
wh_flare  = {wh_flare}; wh_style = {wh_style!r}
shaft_conn = {shaft_conn!r}
spline_teeth = {spline_teeth}; spline_depth = {spline_depth}
poly_lobes = {poly_lobes}; poly_ecc = {poly_ecc}
GEN_SHAFT = {gen_shaft!r}; GEN_ROTOR = {gen_rotor!r}; GEN_MAGNETS = {gen_magnets!r}
GEN_STATOR = {gen_stator!r}; GEN_HAIRPIN = {gen_hairpin!r}; GEN_WHEAD = {gen_whead!r}
GEN_BEAR_A = {gen_bear_a!r}; GEN_BEAR_B = {gen_bear_b!r}; GEN_INSUL = {gen_insul!r}
bearing_od = {bearing_od}; bearing_w = {bearing_w}; bearing_gap = {bearing_gap}
insul_thk  = {insul_thk}
GEN_BALANCE = {gen_balance!r}; BAL_THREAD = {bal_thread!r}
BAL_CIRCLE_D = {bal_circle_d}; BAL_OFFSET = {bal_offset}
GEN_FB_Q = {gen_fb_q!r}; GEN_FB_D = {gen_fb_d!r}
FB_WIDTH = {fb_width}; FB_DEPTH = {fb_depth}
CUSTOM_BARRIERS = {custom_barriers_json}
MAG_GAP = {mag_gap}
dtheta    = 2 * math.pi / n_slots

# Custom designer barriers: thick polyline (capsule) per pole, cut as air.
def _custom_barrier_solids():
    shapes = []
    for p_i in range(poles):
        pa = p_i * 2 * math.pi / poles
        ca, sa = math.cos(pa), math.sin(pa)
        for bar in CUSTOM_BARRIERS:
            pts = bar.get("pts") or []
            w = max(0.5, float(bar.get("width", 3.0)))
            gp = [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]
            for i in range(len(gp) - 1):
                ax, ay = gp[i]; bx, by = gp[i + 1]
                dx, dy = bx - ax, by - ay
                seg = math.hypot(dx, dy)
                if seg < 1e-6:
                    continue
                ang = math.atan2(dy, dx)
                box = Part.makeBox(seg, w, axial + 4, App.Vector(0, -w / 2, -axial / 2 - 2))
                m = App.Matrix(); m.rotateZ(ang)
                box = box.transformGeometry(m); box.translate(App.Vector(ax, ay, 0))
                shapes.append(box)
                # rounded joint at the inner vertex
                cyl = Part.makeCylinder(w / 2, axial + 4, App.Vector(ax, ay, -axial / 2 - 2))
                shapes.append(cyl)
            if gp:
                ex, ey = gp[-1]
                shapes.append(Part.makeCylinder(w / 2, axial + 4, App.Vector(ex, ey, -axial / 2 - 2)))
    return shapes

# Flux-barrier radial slots (air). q-axis = between poles (i+0.5)·pitch, d-axis =
# pole centre i·pitch. Outer edge a bridge below the OD, depth inward. One per pole.
def _flux_barrier_slots():
    shapes = []
    bridge = 2.0
    r_out  = R_rot - bridge
    r_in   = max(R_shaft + 1.0, r_out - FB_DEPTH)
    depth  = max(0.5, r_out - r_in)
    angs = []
    if GEN_FB_D:
        angs += [i * 2 * math.pi / poles for i in range(poles)]
    if GEN_FB_Q:
        angs += [(i + 0.5) * 2 * math.pi / poles for i in range(poles)]
    for a in angs:
        box = Part.makeBox(depth, FB_WIDTH, axial + 4,
                           App.Vector(r_in, -FB_WIDTH / 2.0, -axial / 2 - 2))
        m = App.Matrix(); m.rotateZ(a)
        shapes.append(box.transformGeometry(m))
    return shapes

# Balance-bolt geometry (clearance hole + bolt circle). Count = poles, symmetric.
_THREAD_D = {{"M4": 4.0, "M5": 5.0, "M6": 6.0, "M8": 8.0, "M10": 10.0,
             "M12": 12.0, "M16": 16.0, "M20": 20.0}}
bal_nom    = _THREAD_D.get(BAL_THREAD, 6.0)
bal_hole_r = (bal_nom + 0.4) / 2.0          # clearance hole (M6 → 6.4 mm)
n_bolts    = max(2, poles)                  # one bolt per pole, fully symmetric
if BAL_CIRCLE_D > 0:
    bal_pcr = BAL_CIRCLE_D / 2.0
else:                                       # auto: midway between shaft and rotor OD
    bal_pcr = R_shaft + (R_rot - R_shaft) * 0.5

def _balance_positions():
    out = []
    for i in range(n_bolts):
        a = math.radians(BAL_OFFSET) + i * 2 * math.pi / n_bolts
        out.append((bal_pcr * math.cos(a), bal_pcr * math.sin(a)))
    return out

def _try_color(obj, rgb):
    try: obj.ViewObject.ShapeColor = rgb
    except Exception: pass

def _add(name, shape, rgb):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    _try_color(o, rgb)
    return o

def _bore_cutter(r, z0, h):
    # Shaft–core connection profile, used BOTH as the shaft outer body and as the
    # rotor bore-cut so the two always mate. press → plain cylinder; spline → cyl +
    # radial teeth (Keilwelle); polygon → P3G lobed profile r(φ)=r+ecc·cos(lobes·φ).
    if shaft_conn == "polygon":
        pts = []
        M = 240
        for i in range(M):
            phi = 2 * math.pi * i / M
            rr = r + poly_ecc * math.cos(poly_lobes * phi)
            pts.append(App.Vector(rr * math.cos(phi), rr * math.sin(phi), z0))
        pts.append(pts[0])
        face = Part.Face(Part.makePolygon(pts))
        return face.extrude(App.Vector(0, 0, h))
    if shaft_conn == "spline":
        body = Part.makeCylinder(r, h, App.Vector(0, 0, z0))
        tw = max(1.5, 2 * math.pi * r / spline_teeth * 0.5)      # tooth tangential width
        teeth = []
        for i in range(spline_teeth):
            a = 2 * math.pi * i / spline_teeth
            bx = Part.makeBox(spline_depth + 1.0, tw, h, App.Vector(r - 1.0, -tw / 2.0, z0))
            mm = App.Matrix(); mm.rotateZ(a)
            teeth.append(bx.transformGeometry(mm))
        return body.fuse(teeth) if teeth else body
    return Part.makeCylinder(r, h, App.Vector(0, 0, z0))          # press → plain cylinder

# ── 1. SHAFT (hollow if R_bore > 0; outer profile = connection type) ──────
if GEN_SHAFT:
    shaft_len = axial + 60
    shaft = _bore_cutter(R_shaft, -shaft_len / 2, shaft_len)
    if R_bore > 0:
        shaft = shaft.cut(Part.makeCylinder(R_bore, shaft_len + 4, App.Vector(0, 0, -shaft_len / 2 - 2)))
    _add("Shaft", shaft, (0.75, 0.75, 0.75))

# ── 2. ROTOR IRON (with magnet pockets; bore = connection type) ───────────
if GEN_ROTOR:
    rotor_ring  = Part.makeCylinder(R_rot,   axial,     App.Vector(0, 0, -axial / 2))
    bore_cut    = _bore_cutter(R_shaft, -axial / 2 - 2, axial + 4)
    rotor_solid = rotor_ring.cut(bore_cut)

    pocket_shapes = []
    for i in range(poles):
        pole_ang = i * (2 * math.pi / poles)
        cos_p = math.cos(pole_ang); sin_p = math.sin(pole_ang)
        for rec in [lg for lg in legs if lg["placement"] == "interior"]:
            cx_l = rec["cx"]; cy_l = rec["cy"]; h_ang = rec["rot"]
            L = rec["length"]; T = rec["thick"]
            cx = cx_l * cos_p - cy_l * sin_p
            cy = cx_l * sin_p + cy_l * cos_p
            m = App.Matrix(); m.rotateZ(pole_ang + h_ang)
            # obround pocket (Langloch): straight box + semicircular end caps (air
            # flux barriers). Straight length = magnet length, caps add air at ends.
            _pw = L + 2 * MAG_GAP; _pt = T + 2 * MAG_GAP    # pocket = magnet + gap/side
            pkt = Part.makeBox(_pw, _pt, axial + 4,
                               App.Vector(-_pw / 2, -_pt / 2, -axial / 2 - 2))
            pkt = pkt.transformGeometry(m); pkt.translate(App.Vector(cx, cy, 0))
            pocket_shapes.append(pkt)
            cap_r = _pt / 2
            for ex in (-L / 2, L / 2):
                cap = Part.makeCylinder(cap_r, axial + 4, App.Vector(ex, 0, -axial / 2 - 2))
                cap = cap.transformGeometry(m); cap.translate(App.Vector(cx, cy, 0))
                pocket_shapes.append(cap)

    if pocket_shapes:
        rotor_solid = rotor_solid.cut(Part.makeCompound(pocket_shapes))
    # Balance-disc bolt holes through the whole stack (symmetric, count = poles).
    if GEN_BALANCE and bal_hole_r > 0:
        hole_shapes = []
        for (hx, hy) in _balance_positions():
            h = Part.makeCylinder(bal_hole_r, axial + 4, App.Vector(hx, hy, -axial / 2 - 2))
            hole_shapes.append(h)
        if hole_shapes:
            rotor_cut = rotor_solid.cut(Part.makeCompound(hole_shapes))
            if rotor_cut.isValid():
                rotor_solid = rotor_cut
            else:
                print("WARN: balance-bolt holes produced an invalid rotor — skipped")
    # Flux-barrier radial air slots (q-/d-axis), cut into the rotor iron.
    if GEN_FB_Q or GEN_FB_D:
        fb_shapes = _flux_barrier_slots()
        if fb_shapes:
            rotor_cut = rotor_solid.cut(Part.makeCompound(fb_shapes))
            if rotor_cut.isValid():
                rotor_solid = rotor_cut
            else:
                print("WARN: flux-barrier slots produced an invalid rotor — skipped")
    # Custom designer barriers (free-form polylines), cut as air capsules.
    if CUSTOM_BARRIERS:
        cb_shapes = _custom_barrier_solids()
        if cb_shapes:
            rotor_cut = rotor_solid.cut(Part.makeCompound(cb_shapes))
            if rotor_cut.isValid():
                rotor_solid = rotor_cut
            else:
                print("WARN: custom barriers produced an invalid rotor — skipped")
    if not rotor_solid.isValid():
        raise RuntimeError("Rotor iron invalid after pocket cuts")
    _add("Rotor", rotor_solid, (0.40, 0.40, 0.46))

# ── 2b. BALANCE-DISC BOLTS (optional; through the whole stack) ─────────────
if GEN_BALANCE and bal_nom > 0:
    bolt_shapes = []
    head_h = max(2.5, 0.6 * bal_nom)        # head / nut height
    head_r = 0.9 * bal_nom                  # ≈ across-corners of a hex head
    z0 = -axial / 2 - head_h
    bolt_len = axial + 2 * head_h
    for (hx, hy) in _balance_positions():
        shank = Part.makeCylinder(bal_nom / 2.0, bolt_len, App.Vector(hx, hy, z0))
        head  = Part.makeCylinder(head_r, head_h, App.Vector(hx, hy, z0))
        nut   = Part.makeCylinder(head_r, head_h, App.Vector(hx, hy, -axial / 2 + axial))
        bolt_shapes += [shank, head, nut]
    if bolt_shapes:
        _add("BalanceBolts", Part.makeCompound(bolt_shapes), (0.30, 0.30, 0.33))

# ── 3. MAGNETS (N=red, S=blue) ───────────────────────────────────────────
if GEN_MAGNETS:
    mag_shapes = [[], []]
    for i in range(poles):
        pole_ang = i * (2 * math.pi / poles)
        cos_p = math.cos(pole_ang); sin_p = math.sin(pole_ang)
        pol = i % 2
        for rec in legs:
            cx_l = rec["cx"]; cy_l = rec["cy"]; h_ang = rec["rot"]
            L = rec["length"]; T = rec["thick"]
            cx = cx_l * cos_p - cy_l * sin_p
            cy = cx_l * sin_p + cy_l * cos_p
            if rec["placement"] == "surface":
                # Surface magnet: annular arc-shell sector on the rotor OD (no pocket).
                # L = arc length [mm]; rec["offset"] = tangential arc-length shift of
                # the segment centre from the pole centre (Halbach sub-segments).
                arc_rad = L / R_rot
                arc_deg = math.degrees(arc_rad)
                center_ang = pole_ang + rec["offset"] / R_rot
                # outer band INSIDE the rotor OD: [R_rot - T, R_rot]
                sector = Part.makeCylinder(R_rot, axial, App.Vector(0, 0, -axial / 2),
                                           App.Vector(0, 0, 1), arc_deg)
                bore = Part.makeCylinder(R_rot - T, axial + 2, App.Vector(0, 0, -axial / 2 - 1))
                mag = sector.cut(bore)
                mm = App.Matrix(); mm.rotateZ(center_ang - arc_rad / 2)
                mag = mag.transformGeometry(mm)
            else:
                mag = Part.makeBox(L, T, axial,
                                   App.Vector(-L / 2, -T / 2, -axial / 2))
                m = App.Matrix(); m.rotateZ(pole_ang + h_ang)
                mag = mag.transformGeometry(m)
                mag.translate(App.Vector(cx, cy, 0))
            mag_shapes[pol].append(mag)

    for (shapes, rgb, name) in zip(
            mag_shapes,
            [(0.90, 0.15, 0.15), (0.15, 0.30, 0.90)],
            ["Magnets_N", "Magnets_S"]):
        if shapes:
            compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
            _add(name, compound, rgb)

# ── 4. STATOR IRON (with slots) ──────────────────────────────────────────
if GEN_STATOR:
    stator_ring  = Part.makeCylinder(R_so, axial,     App.Vector(0, 0, -axial / 2))
    stator_bore  = Part.makeCylinder(R_si, axial + 4, App.Vector(0, 0, -axial / 2 - 2))
    stator_solid = stator_ring.cut(stator_bore)

    slot_shapes = []
    for s in range(n_slots):
        ang      = s * dtheta
        slot_box = Part.makeBox(slot_dep + 1, slot_w, axial + 4,
                                App.Vector(R_si - 0.5, -slot_w / 2, -axial / 2 - 2))
        m = App.Matrix(); m.rotateZ(ang)
        slot_shapes.append(slot_box.transformGeometry(m))

    stator_solid = stator_solid.cut(Part.makeCompound(slot_shapes))
    if not stator_solid.isValid():
        raise RuntimeError("Stator invalid after slot cuts")
    _add("Stator", stator_solid, (0.35, 0.35, 0.40))

# ── 5. HAIRPIN CONDUCTORS (C lanes/slot, U-crowns + weld tabs, 3-phase) ───
# Each slot holds n_layers radial conductor lanes. At the +z (crown) face a
# U-bridge connects (slot s, lane 2j) → (slot s+coil_pitch, lane 2j+1); at the
# -z face short weld tabs are added. Collision-free by construction:
#   • different lane-pairs occupy separate radial bands (radius increases per lane)
#   • within a band a triangular "chevron" rise guarantees a constant z-gap
#     2H/coil_pitch between tangential neighbours → set H so that exceeds the bar.
z_face  = axial / 2.0
thick   = max(layer_h, cond_w)
clr     = 0.6
# Chevron peak so neighbouring crowns in a lane clear: gap 2H/pitch >= bar + clr.
crown_H = max(10.0, 0.5 * coil_pitch * (thick + clr) * 1.6)
M_seg   = 6
_COL    = [(0.90, 0.45, 0.05), (0.05, 0.75, 0.20), (0.10, 0.30, 0.90)]

def _r_lane(k):
    return R_si + ins + k * (layer_h + ins) + layer_h / 2.0

def _pt(r, th, z):
    return App.Vector(r * math.cos(th), r * math.sin(th), z)

def _bar(p0, p1, w, h):
    # Oriented bar: length along p1-p0, height h along the (perpendicular) radial
    # direction, width w along the binormal — fixed cross-section orientation
    # (no free roll), so bars never wander across lane / axial clearances.
    d = p1.sub(p0); L = d.Length
    if L < 1e-6:
        return None
    ex = App.Vector(d); ex.normalize()
    rad = App.Vector((p0.x + p1.x) / 2.0, (p0.y + p1.y) / 2.0, 0.0)
    if rad.Length < 1e-9:
        rad = App.Vector(1, 0, 0)
    rad.normalize()
    ez = rad.sub(ex * ex.dot(rad))                 # radial part ⟂ length → height axis
    if ez.Length < 1e-9:
        ez = App.Vector(0, 0, 1)
    ez.normalize()
    ey = ez.cross(ex)                              # binormal → width axis
    box = Part.makeBox(L, w, h, App.Vector(0, -w / 2.0, -h / 2.0))
    box.Placement = App.Placement(App.Matrix(
        ex.x, ey.x, ez.x, p0.x,
        ex.y, ey.y, ez.y, p0.y,
        ex.z, ey.z, ez.z, p0.z,
        0, 0, 0, 1))
    return box

def _leg(s, k, out):
    r_in = R_si + ins + k * (layer_h + ins)
    cond = Part.makeBox(layer_h, cond_w, axial,
                        App.Vector(r_in, -cond_w / 2.0, -axial / 2.0))
    m = App.Matrix(); m.rotateZ(s * dtheta)
    out.append(cond.transformGeometry(m))

def _crown(s, k0, k1, out):
    # Hairpin crown: "go" arm rises on the inner lane radius r0, "return" arm
    # descends on the outer lane radius r1, with a short radial step at the apex.
    # Crossing arms of overlapping crowns are therefore always at different radii
    # (r0 vs r1) → no collision; parallel same-arm neighbours keep the z-gap
    # 2H/pitch. (A symmetric single-radius chevron would let go/return arms cross.)
    th0 = s * dtheta; th1 = (s + coil_pitch) * dtheta
    r0 = _r_lane(k0); r1 = _r_lane(k1)
    th_mid = th0 + 0.5 * (th1 - th0)
    half = max(2, M_seg // 2)
    pts = []
    for mseg in range(0, half + 1):                 # ascending arm @ r0
        t = 0.5 * mseg / half
        pts.append(_pt(r0, th0 + t * (th1 - th0), z_face + crown_H * 2.0 * t))
    pts.append(_pt(r1, th_mid, z_face + crown_H))    # radial step at the apex
    for mseg in range(1, half + 1):                 # descending arm @ r1
        t = 0.5 + 0.5 * mseg / half
        pts.append(_pt(r1, th0 + t * (th1 - th0), z_face + crown_H * 2.0 * (1.0 - t)))
    for a in range(len(pts) - 1):
        seg = _bar(pts[a], pts[a + 1], cond_w, layer_h)
        if seg is not None:
            out.append(seg)

def _crown_frame(p_from, p_to, at):
    # Orthonormal frame at a path point: ex=tangent, ez=radial⟂tangent (height),
    # ey=binormal (width) — keeps the conductor cross-section flat (no roll).
    ex = p_to.sub(p_from)
    ex = App.Vector(ex)
    if ex.Length < 1e-9:
        ex = App.Vector(0, 0, 1)
    ex.normalize()
    rad = App.Vector(at.x, at.y, 0.0)
    if rad.Length < 1e-9:
        rad = App.Vector(1, 0, 0)
    rad.normalize()
    ez = rad.sub(ex * ex.dot(rad))
    if ez.Length < 1e-9:
        ez = App.Vector(0, 0, 1)
    ez.normalize()
    return ex, ez.cross(ex), ez

def _crown_rect(at, ey, ez):
    cw2 = cond_w / 2.0; lh2 = layer_h / 2.0
    cs = [App.Vector(at.x + ey.x * cw2 + ez.x * lh2, at.y + ey.y * cw2 + ez.y * lh2, at.z + ey.z * cw2 + ez.z * lh2),
          App.Vector(at.x - ey.x * cw2 + ez.x * lh2, at.y - ey.y * cw2 + ez.y * lh2, at.z - ey.z * cw2 + ez.z * lh2),
          App.Vector(at.x - ey.x * cw2 - ez.x * lh2, at.y - ey.y * cw2 - ez.y * lh2, at.z - ey.z * cw2 - ez.z * lh2),
          App.Vector(at.x + ey.x * cw2 - ez.x * lh2, at.y + ey.y * cw2 - ez.y * lh2, at.z + ey.z * cw2 - ez.z * lh2)]
    return Part.makePolygon(cs + [cs[0]])

def _crown_swept(s, k0, k1, out):
    # Winding head as ONE continuous solid (Zugkörper): a FINELY-sampled ruled loft
    # through the crown path swept with the rectangular conductor cross-section.
    # Ruled (piecewise-linear) is used on purpose — a smooth B-spline sweep overshoots
    # at the sharp r0→r1 apex step and the go/return arms touch (tiny overlaps); the
    # many small linear segments here look smooth yet hug the path envelope, so the
    # collision-free radial split (ascending @ r0, descending @ r1) is preserved.
    # Uniform outward flare (wh_flare). Fallback: box chevron _crown.
    if wh_style == "box":
        _crown(s, k0, k1, out); return
    th0 = s * dtheta; th1 = (s + coil_pitch) * dtheta
    r0 = _r_lane(k0); r1 = _r_lane(k1); f = wh_flare
    th_mid = th0 + 0.5 * (th1 - th0)
    half = 16                                         # many segments → visually smooth
    pts = []
    for mseg in range(0, half + 1):                  # ascending @ r0, flaring out
        t = 0.5 * mseg / half
        pts.append(_pt(r0 + f * 2.0 * t, th0 + t * (th1 - th0), z_face + crown_H * 2.0 * t))
    pts.append(_pt(r1 + f, th_mid, z_face + crown_H))            # apex (radial step, flared)
    for mseg in range(1, half + 1):                  # descending @ r1, flaring back in
        t = 0.5 + 0.5 * mseg / half
        pts.append(_pt(r1 + f * 2.0 * (1.0 - t), th0 + t * (th1 - th0),
                       z_face + crown_H * 2.0 * (1.0 - t)))
    try:
        n = len(pts); secs = []
        for i in range(n):
            pf = pts[i - 1] if i > 0 else pts[i]
            pt = pts[i + 1] if i < n - 1 else pts[i]
            _ex, ey, ez = _crown_frame(pf, pt, pts[i])
            secs.append(_crown_rect(pts[i], ey, ez))
        solid = Part.makeLoft(secs, True, True)       # solid=True, ruled=True
        if solid and solid.isValid() and solid.Volume > 1e-6:
            out.append(solid); return
    except Exception:
        pass
    _crown(s, k0, k1, out)                            # fallback: box chevron

def _tab(s, k, out):
    th0 = s * dtheta; r = _r_lane(k)
    direction = 1.0 if (k % 2 == 0) else -1.0
    p0 = _pt(r, th0, -z_face)
    p1 = _pt(r, th0 + direction * 0.30 * dtheta, -z_face - (6.0 + k * 1.5))
    seg = _bar(p0, p1, cond_w, layer_h)
    if seg is not None:
        out.append(seg)

# Build physical U-pins (each = one continuous conductor): leg(s,2j) + crown +
# leg(s+pitch,2j+1) + weld tabs. Pins partition all legs uniquely. The U-crown
# (winding head) is only added when GEN_WHEAD — otherwise the slot bars + weld
# tabs are emitted without the over-hang loop (straight conductors only).
if GEN_HAIRPIN:
    pins = []
    for s in range(n_slots):
        for j in range(n_layers // 2):
            segs = []
            k0 = 2 * j; k1 = 2 * j + 1
            s2 = (s + coil_pitch) % n_slots
            _leg(s, k0, segs); _tab(s, k0, segs)
            if GEN_WHEAD:
                _crown_swept(s, k0, k1, segs)
            _leg(s2, k1, segs); _tab(s2, k1, segs)
            pins.append((s % 3, segs))

    if WIND_DEBUG:
        for _pi, (_ph, _segs) in enumerate(pins):
            if _segs:
                _add("Pin_%03d" % _pi, Part.makeCompound(_segs), _COL[_ph])
    else:
        ph_shapes = [[], [], []]
        for _ph, _segs in pins:
            ph_shapes[_ph].extend(_segs)
        for (shapes, rgb, name) in zip(ph_shapes, _COL,
                                       ["Coils_A", "Coils_B", "Coils_C"]):
            if shapes:
                compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
                _add(name, compound, rgb)

# ── 6. BEARINGS (A=−z / B=+z) — simplified ring on the shaft, outboard of stack ──
if GEN_BEAR_A or GEN_BEAR_B:
    b_or = (bearing_od / 2.0) if bearing_od > 0 else (R_shaft + 14.0)
    b_or = max(b_or, R_shaft + 4.0)
    for _sd, _flag, _nm in ((-1.0, GEN_BEAR_A, "Bearing_A"), (1.0, GEN_BEAR_B, "Bearing_B")):
        if not _flag:
            continue
        z0 = -(axial / 2.0 + bearing_gap + bearing_w) if _sd < 0 else (axial / 2.0 + bearing_gap)
        ring = Part.makeCylinder(b_or, bearing_w, App.Vector(0, 0, z0))
        ring = ring.cut(Part.makeCylinder(R_shaft, bearing_w + 2, App.Vector(0, 0, z0 - 1)))
        _add(_nm, ring, (0.55, 0.56, 0.60))

# ── 7. WINDING-HEAD INSULATION PAPER — thin shell hugging the crown OD (+z) ──
if GEN_INSUL and GEN_HAIRPIN and GEN_WHEAD:
    r_env = R_si + slot_dep + 2.0 * wh_flare + 1.5
    z_lo  = z_face - insul_thk
    z_hi  = z_face + crown_H + insul_thk
    sleeve = Part.makeCylinder(r_env + insul_thk, z_hi - z_lo, App.Vector(0, 0, z_lo))
    sleeve = sleeve.cut(Part.makeCylinder(r_env, z_hi - z_lo + 2, App.Vector(0, 0, z_lo - 1)))
    _add("Insulation_WH", sleeve, (0.93, 0.86, 0.55))

# ── SAVE ─────────────────────────────────────────────────────────────────
doc.recompute()

_rotor_obj = doc.getObject("Rotor")   # may be absent (rotor iron toggled off)
if _rotor_obj is not None:
    _rotor_shape = _rotor_obj.Shape
    _faces = []
    for _i, _f in enumerate(_rotor_shape.Faces):
        try:
            _n = _f.normalAt(0, 0); _c = _f.CenterOfMass
            _faces.append({{"index": _i, "area_mm2": round(_f.Area, 2),
                            "centroid": {{"x": round(_c.x,2),"y": round(_c.y,2),"z": round(_c.z,2)}},
                            "normal":   {{"x": round(_n.x,3),"y": round(_n.y,3),"z": round(_n.z,3)}}}})
        except Exception:
            pass
    print("CAD_FACES:" + _json.dumps(_faces))
    print(f"CAD_VOLUME:{{_rotor_shape.Volume:.2f}}")
else:
    print("CAD_FACES:[]")
    print("CAD_VOLUME:0.00")
doc.saveAs(r"{save_path}")
print("SAVED:{save_path}")

# ── STEP export (alongside .FCStd) ───────────────────────────────────────
try:
    _step_path = r"{save_path}".rsplit(".", 1)[0] + ".step"
    _shapes = [o.Shape for o in doc.Objects
               if hasattr(o, "Shape") and o.Shape and not o.Shape.isNull()]
    if _shapes:
        Part.makeCompound(_shapes).exportStep(_step_path)
        print("STEP_SAVED:" + _step_path)
except Exception as _se:
    print("STEP_FAIL:" + str(_se))

print("CAD_SUCCESS")
"""


def build_rotor_fem_script(fcstd_path: str, rpm: float,
                            material_props: dict, save_dir: str,
                            mesh_mm: float = 4.0) -> str:
    """Return FreeCAD Python code for centrifugal structural FEM of the rotor.

    mesh_mm : Gmsh CharacteristicLengthMax [mm] — smaller = finer mesh = higher
              spatial resolution (esp. at the magnet-pocket bridges where the peak
              stress concentrates). Default 4.0. The element ORDER is left at
              FreeCAD's default (2nd-order tets); setting it explicitly was found to
              make CalculiX emit a results-less .frd.
    """
    mat_json = json.dumps(material_props)
    mesh_mm  = max(0.8, min(8.0, float(mesh_mm)))   # clamp to a sane build range
    # Density in t/mm³ for CalculiX (mm/N/MPa unit system)
    density_str = material_props.get("Density", "7700 kg/m^3")
    density_kg_m3 = float(str(density_str).split()[0])
    density_t_mm3 = density_kg_m3 / 1e12  # 1 kg/m³ = 1e-12 t/mm³

    return f"""\
import FreeCAD as App
import ObjectsFem
import json, os, sys, traceback

doc = App.openDocument(r"{fcstd_path}")
# Rotor strength only: mesh EXCLUSIVELY the rotor iron ("Rotor"). The winding
# heads (stator hairpin conductors), stator iron and magnets must NOT be part of
# the centrifugal FEM, so never fall back to another Part::Feature (Stator / Pin_*
# / Shaft) — if "Rotor" is missing, fail cleanly instead of meshing the wrong body.
part = doc.getObject("Rotor")
if not part:
    print("ERROR: no Rotor object for structural FEM")
    print("FEM_RESULT:" + json.dumps({{"solver_status": "FAILED", "error": "no Rotor part"}}))
    sys.exit(1)

analysis = ObjectsFem.makeAnalysis(doc, "Analysis")

mat = ObjectsFem.makeMaterialSolid(doc, "Material")
mat.Material = {mat_json}
analysis.addObject(mat)

# Fix the bore (shaft seat). Works for ANY connection profile (cylinder / spline /
# polygon): the bore faces are the innermost ones — pick every face whose largest
# vertex radius is within 1.5× of the smallest such radius. (A non-cylindrical bore
# has no single Cylinder face, so the old "smallest Cylinder.Radius" search fails.)
def _face_max_r(f):
    try:
        return max((v.Point.x ** 2 + v.Point.y ** 2) ** 0.5 for v in f.Vertexes)
    except Exception:
        return 1e9
_fr = [(_face_max_r(f), i) for i, f in enumerate(part.Shape.Faces)]
_rmin = min((r for r, _ in _fr), default=0.0)
fixed_refs = [(part, f"Face{{i+1}}") for r, i in _fr if r <= _rmin * 1.5 + 0.5]
if not fixed_refs:
    fixed_refs = [(part, "Face1")]
print(f"BORE_FIX_FACES: {{len(fixed_refs)}} (rmin={{_rmin:.2f}} mm)")

fixed = ObjectsFem.makeConstraintFixed(doc, "Fixed")
fixed.References = fixed_refs
analysis.addObject(fixed)

# Mesh + solve with a ROBUSTNESS LADDER. Thin iron bridges between aggressive
# multi-layer magnet pockets make a single Gmsh+CalculiX attempt flaky (degenerate
# tets → CalculiX writes a results-less .frd). Mitigations: (a) turn ON Gmsh's
# Netgen + standard mesh optimisers, a curvature-based size and a minimum element
# length so the thin bridges get well-shaped elements; (b) RETRY with finer/coarser
# mesh sizes until the .frd actually contains a DISP result block. Element ORDER is
# left at FreeCAD's default (setting it explicitly produced a results-less .frd).
import math as _m
from femmesh.gmshtools import GmshTools
from femtools.ccxtools import FemToolsCcx

mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
mesh.Shape = part
analysis.addObject(mesh)
solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
analysis.addObject(solver)
doc.recompute()

_omega  = {rpm} * 2 * _m.pi / 60     # rad/s
_omega2 = _omega ** 2                  # rad²/s² (CalculiX CENTRIF unit)
_rho    = {density_t_mm3:.6e}          # t/mm³  (CalculiX density unit)
_work   = os.path.join(r"{save_dir}", "ccx_rotor")
os.makedirs(_work, exist_ok=True)

def _set_opts(_cl):
    # Quality flags help Gmsh build solvable tets on the thin pocket bridges:
    #   OptimizeStd           – Gmsh's own tet-quality optimiser (fewer nonpositive
    #                           Jacobians, the usual cause of a results-less .frd);
    #   MeshSizeFromCurvature – more elements on the curved pocket caps;
    #   CharacteristicLengthMin – floor so thin bridges keep a few elements across.
    # (OptimizeNetgen is intentionally NOT set — in this Gmsh build it yields a mesh
    # with 0 nodes.)
    mesh.CharacteristicLengthMax = _cl
    for _a, _v in (("CharacteristicLengthMin", max(0.0, _cl * 0.15)),
                   ("OptimizeStd", True),
                   ("MeshSizeFromCurvature", 14)):
        try: setattr(mesh, _a, _v)
        except Exception: pass

def _patch_inp(_inp):
    # FreeCAD 1.x omits *DENSITY and the centrifugal *DLOAD — inject both.
    if not (_inp and os.path.exists(_inp)):
        print("CENTRIF_INP_MISSING:", _inp); return
    with open(_inp) as _f: _lines = _f.readlines()
    _out = []; _ae = False
    for _ln in _lines:
        if _ln.strip().upper() == '*END STEP':
            _out.append('*DLOAD\\n')
            _out.append(f'Evolumes, CENTRIF, {{_omega2:.3f}}, 0., 0., 0., 0., 0., 1.\\n')
        _out.append(_ln)
        if _ae:
            _out.append('*DENSITY\\n'); _out.append(f'{{_rho}},\\n'); _ae = False
        if _ln.strip().upper().startswith('*ELASTIC'):
            _ae = True
    with open(_inp, 'w') as _f: _f.writelines(_out)

def _frd_has_disp(_frd):
    # A real result .frd contains a " -4  DISP" displacement dataset; a results-less
    # one (degenerate mesh) does not — this is how we know an attempt truly succeeded.
    try:
        with open(_frd, 'r', errors='ignore') as _f:
            return ' -4  DISP' in _f.read()
    except Exception:
        return False

_clamp  = lambda x: max(0.4, min(8.0, x))
_ladder = [{mesh_mm}, {mesh_mm} * 0.65, {mesh_mm} * 1.4]   # base → finer → coarser
_attempts = []; _frd = ""; _ok = False; _nodes = 0
for _ai, _cl0 in enumerate(_ladder):
    _cl = _clamp(_cl0)
    try:
        _set_opts(_cl); doc.recompute()
        _warn = GmshTools(mesh).create_mesh()
        _nodes = mesh.FemMesh.NodeCount if mesh.FemMesh else 0
        print(f"MESH_TRY[{{_ai}}] clmax={{_cl:.2f}} -> {{_nodes}} Knoten" + (f" warn={{_warn}}" if _warn else ""))
        if _nodes < 50:
            _attempts.append(f"clmax={{_cl:.2f}}: nur {{_nodes}} Knoten"); continue
        doc.recompute()
        fea = FemToolsCcx(analysis, solver)
        fea.update_objects(); fea.setup_working_dir(_work)
        fea.ccx_binary = "ccx"; fea.ccx_binary_present = True; fea.setup_ccx()
        fea.write_inp_file()
        _inp = fea.inp_file_name
        _patch_inp(_inp)
        _frd = (os.path.splitext(_inp)[0] + ".frd") if _inp else ""
        try:
            if _frd and os.path.exists(_frd): os.remove(_frd)   # avoid stale FRD from a prior try
        except Exception: pass
        fea.ccx_run(); sys.stdout.flush()
        if _frd_has_disp(_frd):
            _ok = True; print(f"SOLVE_OK[{{_ai}}] clmax={{_cl:.2f}}, {{_nodes}} Knoten"); break
        _attempts.append(f"clmax={{_cl:.2f}}, {{_nodes}} Knoten: FRD ohne DISP-Ergebnis")
        print(f"SOLVE_NORESULT[{{_ai}}] clmax={{_cl:.2f}}")
    except Exception as _e:
        _attempts.append(f"clmax={{_cl:.2f}}: {{_e}}")
        print(f"ATTEMPT_FAIL[{{_ai}}]: {{_e}}"); traceback.print_exc()

sys.stdout.flush()
if _ok and _frd and os.path.exists(_frd):
    print(f"\\nFRD_FILE:{{_frd}}")
    print("FEM_RESULT:" + json.dumps({{"solver_status": "FRD_READY", "nodes": _nodes}}) + "\\n")
else:
    print("\\nFRD_FILE:MISSING")
    print("FEM_RESULT:" + json.dumps({{"solver_status": "FAILED", "attempts": _attempts[:8]}}) + "\\n")
sys.stdout.flush()
"""
