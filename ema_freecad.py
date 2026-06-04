"""FreeCAD script builders for IPM rotor geometry and structural FEM."""

import math
import json


def _max_magnet_width(rPos: float, magDist_half: float, halfAngle: float,
                      R_rot: float, bridge: float = 2.0) -> float:
    """Compute max magW so the outer magnet corner stays inside R_rot - bridge.

    Solves: (rPos + magW*cos)^2 + (magDist + magW*sin)^2 = (R_rot - bridge)^2
    """
    a = math.cos(halfAngle)
    b = math.sin(halfAngle)
    c = rPos
    d = magDist_half
    R = R_rot - bridge
    # quadratic: magW^2 + 2*(a*c + b*d)*magW + (c^2 + d^2 - R^2) = 0
    p = a * c + b * d
    q = c * c + d * d - R * R
    disc = p * p - q
    if disc < 0:
        return 5.0
    return max(-p + math.sqrt(disc), 5.0)


def build_em_rotor_script(geom: dict, axial_len: float, save_path: str) -> str:
    """Return FreeCAD Python code that creates IPM rotor with magnet pockets."""
    R_rot = geom["rotorOD"] / 2
    R_shaft = geom["shaftD"] / 2
    poles = int(geom["p"]) * 2
    magH = float(geom["magThick"])
    magDist_half = float(geom["magDist"]) / 2
    magDepthRel = float(geom["magDepthRel"])
    halfAngle = math.radians(float(geom["magAngle"]) / 2)
    mag_shape = geom.get("magShape", "v")

    rPos = R_shaft + (R_rot - R_shaft) * magDepthRel

    if mag_shape == "v":
        magW = min(float(geom["magWidth"]),
                   _max_magnet_width(rPos, magDist_half, halfAngle, R_rot))
        # (start_x_local, start_y_local, hAngle_sign)
        mag_configs = [
            (rPos, magDist_half, halfAngle),
            (rPos, -magDist_half, -halfAngle),
        ]
    else:
        magW = float(geom["magWidth"])
        mag_configs = [(rPos, 0.0, math.pi / 2)]

    # Centres in pole-local frame
    centres = []
    angles = []
    for (sx, sy, h) in mag_configs:
        cx = sx + (magW / 2) * math.cos(h)
        cy = sy + (magW / 2) * math.sin(h)
        centres.append((cx, cy))
        angles.append(h)

    centres_json = json.dumps(centres)
    angles_json = json.dumps(angles)

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
magW     = {magW}
magH     = {magH}
tol      = {tol}
centres  = {centres_json}  # [(cx_local, cy_local), ...]
h_angles = {angles_json}   # rotation of long axis in pole frame

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

    for (cx_l, cy_l), h_ang in zip(centres, h_angles):
        # Centre in global frame
        cx = cx_l * cos_p - cy_l * sin_p
        cy = cx_l * sin_p + cy_l * cos_p

        # Box centred at origin, long axis along X
        pkt = Part.makeBox(magW + tol, magH + tol, axial + 4,
                           App.Vector(-(magW + tol) / 2, -(magH + tol) / 2, -axial / 2 - 2))

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


def build_full_motor_script(geom: dict, axial_len: float, save_path: str) -> str:
    """Return FreeCAD Python code that creates a full IPM motor assembly:
    Shaft · Rotor iron · Magnets (N/S) · Stator iron · Hairpin conductors (3-phase).
    All parts are separate named objects with distinct colours.
    """
    R_so      = geom["statorOD"] / 2
    R_si      = geom["statorID"] / 2
    R_rot     = geom["rotorOD"]  / 2
    R_shaft   = geom["shaftD"]   / 2
    poles     = int(geom["p"]) * 2
    n_slots   = int(geom["slots"])
    slot_dep  = float(geom["slotDepth"])
    sw_ratio  = float(geom.get("slotWidthRatio", 0.5))
    magH      = float(geom["magThick"])
    magDist_h = float(geom["magDist"]) / 2
    depthRel  = float(geom["magDepthRel"])
    halfAngle = math.radians(float(geom["magAngle"]) / 2)
    mag_shape = geom.get("magShape", "v")
    axial     = axial_len

    import math as _m
    dtheta  = 2 * _m.pi / n_slots
    slot_w  = max(3.0, R_si * dtheta * sw_ratio)

    rPos = R_shaft + (R_rot - R_shaft) * depthRel
    if mag_shape == "v":
        magW = min(float(geom["magWidth"]),
                   _max_magnet_width(rPos, magDist_h, halfAngle, R_rot))
        mag_configs = [
            (rPos,  magDist_h,  halfAngle),
            (rPos, -magDist_h, -halfAngle),
        ]
    else:
        magW = float(geom["magWidth"])
        mag_configs = [(rPos, 0.0, _m.pi / 2)]

    centres = []
    h_angles_list = []
    for (sx, sy, h) in mag_configs:
        cx = sx + (magW / 2) * _m.cos(h)
        cy = sy + (magW / 2) * _m.sin(h)
        centres.append((cx, cy))
        h_angles_list.append(h)

    centres_json = json.dumps(centres)
    angles_json  = json.dumps(h_angles_list)

    n_layers  = 2
    ins       = 0.8
    cond_w    = max(1.5, slot_w - 2 * ins)
    layer_h   = max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)

    return f"""\
import FreeCAD as App
import Part
import math
import json as _json

doc = App.newDocument("Motor")

R_so      = {R_so};   R_si    = {R_si}
R_rot     = {R_rot};  R_shaft = {R_shaft}
axial     = {axial}
poles     = {poles};  n_slots = {n_slots}
slot_dep  = {slot_dep}; slot_w = {slot_w:.4f}
magW      = {magW:.4f}; magH  = {magH}
centres   = {centres_json}
h_angles  = {angles_json}
n_layers  = {n_layers}; ins   = {ins}; cond_w = {cond_w:.4f}; layer_h = {layer_h:.4f}
dtheta    = 2 * math.pi / n_slots

def _try_color(obj, rgb):
    try: obj.ViewObject.ShapeColor = rgb
    except Exception: pass

def _add(name, shape, rgb):
    o = doc.addObject("Part::Feature", name)
    o.Shape = shape
    _try_color(o, rgb)
    return o

# ── 1. SHAFT ──────────────────────────────────────────────────────────────
shaft_len = axial + 60
shaft = Part.makeCylinder(R_shaft, shaft_len, App.Vector(0, 0, -shaft_len / 2))
_add("Shaft", shaft, (0.75, 0.75, 0.75))

# ── 2. ROTOR IRON (with magnet pockets) ──────────────────────────────────
rotor_ring  = Part.makeCylinder(R_rot,   axial,     App.Vector(0, 0, -axial / 2))
bore_cut    = Part.makeCylinder(R_shaft, axial + 4, App.Vector(0, 0, -axial / 2 - 2))
rotor_solid = rotor_ring.cut(bore_cut)

pocket_shapes = []
for i in range(poles):
    pole_ang = i * (2 * math.pi / poles)
    cos_p = math.cos(pole_ang); sin_p = math.sin(pole_ang)
    for (cx_l, cy_l), h_ang in zip(centres, h_angles):
        cx = cx_l * cos_p - cy_l * sin_p
        cy = cx_l * sin_p + cy_l * cos_p
        pkt = Part.makeBox(magW + 0.4, magH + 0.4, axial + 4,
                           App.Vector(-(magW + 0.4) / 2, -(magH + 0.4) / 2, -axial / 2 - 2))
        m = App.Matrix(); m.rotateZ(pole_ang + h_ang)
        pkt = pkt.transformGeometry(m)
        pkt.translate(App.Vector(cx, cy, 0))
        pocket_shapes.append(pkt)

rotor_solid = rotor_solid.cut(Part.makeCompound(pocket_shapes))
if not rotor_solid.isValid():
    raise RuntimeError("Rotor iron invalid after pocket cuts")
_add("Rotor", rotor_solid, (0.40, 0.40, 0.46))

# ── 3. MAGNETS (N=red, S=blue) ───────────────────────────────────────────
mag_shapes = [[], []]
for i in range(poles):
    pole_ang = i * (2 * math.pi / poles)
    cos_p = math.cos(pole_ang); sin_p = math.sin(pole_ang)
    pol = i % 2
    for (cx_l, cy_l), h_ang in zip(centres, h_angles):
        cx = cx_l * cos_p - cy_l * sin_p
        cy = cx_l * sin_p + cy_l * cos_p
        mag = Part.makeBox(magW - 0.2, magH - 0.2, axial,
                           App.Vector(-(magW - 0.2) / 2, -(magH - 0.2) / 2, -axial / 2))
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

# ── 5. HAIRPIN CONDUCTORS (2 layers, 3-phase A/B/C) ──────────────────────
et_h      = 18        # end-turn extension beyond stack [mm]
full_h    = axial + 2 * et_h
ph_shapes = [[], [], []]
for s in range(n_slots):
    ang = s * dtheta
    ph  = s % 3
    for layer in range(n_layers):
        r_in = R_si + ins + layer * (layer_h + ins)
        cond = Part.makeBox(layer_h, cond_w, full_h,
                            App.Vector(r_in, -cond_w / 2, -full_h / 2))
        m = App.Matrix(); m.rotateZ(ang)
        ph_shapes[ph].append(cond.transformGeometry(m))

for (shapes, rgb, name) in zip(
        ph_shapes,
        [(0.90, 0.45, 0.05), (0.05, 0.75, 0.20), (0.10, 0.30, 0.90)],
        ["Coils_A", "Coils_B", "Coils_C"]):
    if shapes:
        compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
        _add(name, compound, rgb)

# ── SAVE ─────────────────────────────────────────────────────────────────
doc.recompute()

_rotor_shape = doc.getObject("Rotor").Shape
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
                            material_props: dict, save_dir: str) -> str:
    """Return FreeCAD Python code for centrifugal structural FEM of the rotor."""
    mat_json = json.dumps(material_props)
    # Density in t/mm³ for CalculiX (mm/N/MPa unit system)
    density_str = material_props.get("Density", "7700 kg/m^3")
    density_kg_m3 = float(str(density_str).split()[0])
    density_t_mm3 = density_kg_m3 / 1e12  # 1 kg/m³ = 1e-12 t/mm³

    return f"""\
import FreeCAD as App
import ObjectsFem
import json, os, sys, traceback

doc = App.openDocument(r"{fcstd_path}")
# Find rotor: prefer object named "Rotor", fall back to first Part::Feature
part = doc.getObject("Rotor")
if not part:
    part = next((o for o in doc.Objects if o.TypeId == "Part::Feature"), None)
if not part:
    print("ERROR: no Part::Feature")
    sys.exit(1)

analysis = ObjectsFem.makeAnalysis(doc, "Analysis")

mat = ObjectsFem.makeMaterialSolid(doc, "Material")
mat.Material = {mat_json}
analysis.addObject(mat)

# Find shaft bore face (smallest cylindrical face by radius)
shaft_face_ref = "Face1"
min_r = float("inf")
for i, face in enumerate(part.Shape.Faces):
    surf = face.Surface
    if surf.__class__.__name__ == "Cylinder" and surf.Radius < min_r:
        min_r = surf.Radius
        shaft_face_ref = f"Face{{i+1}}"

fixed = ObjectsFem.makeConstraintFixed(doc, "Fixed")
fixed.References = [(part, shaft_face_ref)]
analysis.addObject(fixed)

# Mesh
mesh = ObjectsFem.makeMeshGmsh(doc, "Mesh")
mesh.Shape = part
mesh.CharacteristicLengthMax = 4.0
analysis.addObject(mesh)
doc.recompute()

try:
    from femmesh.gmshtools import GmshTools
    err = GmshTools(mesh).create_mesh()
    if err:
        print(f"MESH_WARN: {{err}}")
    print(f"MESH_OK: {{mesh.FemMesh.NodeCount}} nodes")
except Exception as e:
    print(f"MESH_ERROR: {{e}}")
    traceback.print_exc()
    sys.exit(1)

doc.recompute()

solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
analysis.addObject(solver)
doc.recompute()

try:
    import math as _m
    from femtools.ccxtools import FemToolsCcx
    work = os.path.join(r"{save_dir}", "ccx_rotor")
    os.makedirs(work, exist_ok=True)
    fea = FemToolsCcx(analysis, solver)
    fea.update_objects()
    fea.setup_working_dir(work)
    fea.ccx_binary = "ccx"
    fea.ccx_binary_present = True
    fea.setup_ccx()

    # Write inp file, then patch:
    #  1. Insert *DENSITY after *ELASTIC block (FreeCAD 1.x omits it)
    #  2. Insert *DLOAD CENTRIF before *END STEP
    fea.write_inp_file()
    _omega  = {rpm} * 2 * _m.pi / 60     # rad/s
    _omega2 = _omega ** 2                  # rad²/s² (CalculiX CENTRIF unit)
    _rho    = {density_t_mm3:.6e}          # t/mm³  (CalculiX density unit)
    _inp = fea.inp_file_name
    if _inp and os.path.exists(_inp):
        with open(_inp) as _f:
            _lines = _f.readlines()
        _patched = []
        _after_elastic = False
        for _ln in _lines:
            if _ln.strip().upper() == '*END STEP':
                _patched.append('*DLOAD\\n')
                _patched.append(f'Evolumes, CENTRIF, {{_omega2:.3f}}, 0., 0., 0., 0., 0., 1.\\n')
            _patched.append(_ln)
            if _after_elastic:
                _patched.append(f'*DENSITY\\n')
                _patched.append(f'{{_rho}},\\n')
                _after_elastic = False
            if _ln.strip().upper().startswith('*ELASTIC'):
                _after_elastic = True  # next line is elastic data → insert density after it
        with open(_inp, 'w') as _f:
            _f.writelines(_patched)
        print(f"INP_PATCHED: rho={{_rho}} t/mm³, omega={{_omega:.2f}} rad/s")
    else:
        print(f"CENTRIF_INP_MISSING: {{_inp}}")

    fea.ccx_run()
    # FreeCAD 1.2 does not import .frd results back into the document.
    # Print the .frd path so the pipeline can parse it directly.
    _frd = os.path.splitext(_inp)[0] + ".frd" if _inp else ""
    if _frd and os.path.exists(_frd):
        print(f"FRD_FILE:{{_frd}}")
    else:
        print("FRD_FILE:MISSING")
    print("FEM_RESULT:" + json.dumps({{"solver_status": "FRD_READY"}}))
except Exception as e:
    print(f"FEA_ERROR: {{e}}")
    traceback.print_exc()
    print("FEM_RESULT:" + json.dumps({{"solver_status": "FAILED", "error": str(e)}}))
"""
