"""FreeCAD headless execution and FEM script builder.

Uses FreeCAD 1.1.1 from ~/freecad_1.1_quellcode (built with pixi). The binary
at /opt/freecad-1.1/... is actually 1.2 with a visualisation bug, so we
explicitly route through `pixi run` to pick up the working 1.1.1 build and
its conda env (CCX is bundled inside the same env).
"""

import subprocess
import tempfile
import os
import json
import re

FREECAD_ROOT  = os.path.expanduser("~/freecad_1.1_quellcode")
FREECAD_BIN   = os.path.join(FREECAD_ROOT, "build/release/bin/FreeCAD")
FREECADCMD_BIN = os.path.join(FREECAD_ROOT, "build/release/bin/FreeCADCmd")
CCX_CMD = os.path.join(FREECAD_ROOT, ".pixi/envs/default/bin/ccx")
CCX_DIR = os.path.dirname(CCX_CMD)
PIXI    = "pixi"


def _pixi_cmd(*args: str) -> list[str]:
    """Build a `pixi run --manifest-path … -- <cmd…>` invocation that runs
    inside the FreeCAD pixi env. Working dir must be FREECAD_ROOT."""
    return [PIXI, "run", "--manifest-path",
            os.path.join(FREECAD_ROOT, "pixi.toml"), "--", *args]


def run_freecad_script(code: str, timeout: int = 120) -> dict:
    """Execute a FreeCAD Python script headlessly. Returns parsed output dict."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(code)
        script_path = f.name

    env = os.environ.copy()
    env["PATH"] = CCX_DIR + os.pathsep + env.get("PATH", "")

    try:
        proc = subprocess.run(
            _pixi_cmd("build/release/bin/FreeCADCmd", script_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
            cwd=FREECAD_ROOT,
        )
        stdout = proc.stdout or ""
        stderr = proc.stderr or ""

        parsed: dict = {}
        for line in stdout.splitlines():
            line = line.strip()
            if line.startswith("CAD_FACES:"):
                try:
                    # FreeCAD sometimes appends its version banner to the same
                    # stdout line (no newline), so json.loads would see "Extra
                    # data". raw_decode parses the leading JSON and ignores the rest.
                    parsed["faces"], _ = json.JSONDecoder().raw_decode(line[10:])
                except json.JSONDecodeError:
                    pass
            elif line.startswith("CAD_VOLUME:"):
                try:
                    parsed["volume"] = float(line[11:])
                except ValueError:
                    pass
            elif line.startswith("CAD_SUCCESS"):
                parsed["cad_success"] = True
            elif line.startswith("SAVED:"):
                parsed["saved_path"] = line[6:]
            elif line.startswith("STEP_SAVED:"):
                parsed["step_path"] = line[11:]
            elif line.startswith("STEP_FAIL:"):
                parsed["step_error"] = line[10:]
            elif line.startswith("FRD_FILE:"):
                parsed["frd_file"] = line[9:]
            elif line.startswith("FEM_RESULT:"):
                try:
                    parsed["fem_result"], _ = json.JSONDecoder().raw_decode(line[11:])
                except json.JSONDecodeError:
                    pass

        # Robust fallback: a fine 2nd-order Gmsh mesh dumps a huge comma-separated
        # nonpositive-Jacobian node list to stdout WITHOUT a trailing newline, so the
        # Python marker prints get concatenated onto / scrambled with that dump and the
        # line-based parse above misses them. Search the whole blob by regex too.
        if "frd_file" not in parsed:
            m = re.search(r"FRD_FILE:(\S+)", stdout)
            if m:
                parsed["frd_file"] = m.group(1)
        if "fem_result" not in parsed:
            m = re.search(r'FEM_RESULT:(\{.*?\})', stdout)
            if m:
                try:
                    parsed["fem_result"] = json.loads(m.group(1))
                except json.JSONDecodeError:
                    pass

        success = parsed.get("cad_success", False) or "fem_result" in parsed
        return {
            "success": success,
            "stdout": stdout,
            "stderr": stderr,
            "returncode": proc.returncode,
            **parsed,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "stdout": "", "stderr": "Timeout überschritten", "returncode": -1}
    except Exception as exc:
        return {"success": False, "stdout": "", "stderr": str(exc), "returncode": -1}
    finally:
        try:
            os.unlink(script_path)
        except OSError:
            pass


def build_fem_script(freecad_file: str, params: dict, save_dir: str, material_props: dict) -> str:
    """Build a complete FEM analysis script from LLM-determined parameters.

    FreeCAD force unit: internal unit is mm*kg/s² = mN.
    To get N, multiply by 1000. We use App.Units.Quantity for correct conversion.

    Force direction is determined by the chosen face normal + Reversed flag.
    The LLM must choose a face whose normal (possibly reversed) matches the load direction:
      face normal +Z, Reversed=True  → force in -Z (downward) ✓
      face normal -X, Reversed=False → force in -X (leftward) ✓
    """
    mesh_size = params.get("mesh_size_mm", 5.0)
    fixed_ref = params.get("fixed_face_ref", "Face1")
    force_ref = params.get("force_face_ref", "Face6")
    force_n = params.get("force_magnitude_N", 1000.0)
    reversed_ = params.get("force_reversed", True)
    mat_json = json.dumps(material_props)

    return f"""\
import FreeCAD as App
import ObjectsFem
import json, os, sys, traceback

FREECAD_FILE = r"{freecad_file}"
SAVE_DIR = r"{save_dir}"
MESH_SIZE = {mesh_size}

doc = App.openDocument(FREECAD_FILE)
part_obj = next((o for o in doc.Objects if o.TypeId == "Part::Feature"), None)
if not part_obj:
    print("ERROR: Kein Part::Feature in Dokument")
    sys.exit(1)

analysis = ObjectsFem.makeAnalysis(doc, "Analysis")

mat = ObjectsFem.makeMaterialSolid(doc, "Material")
mat.Material = {mat_json}
analysis.addObject(mat)

# Fixed support
fixed = ObjectsFem.makeConstraintFixed(doc, "FixedConstraint")
fixed.References = [(part_obj, "{fixed_ref}")]
analysis.addObject(fixed)

# Force constraint
# IMPORTANT: Force direction = face normal direction (modified by Reversed).
# Force unit: App.Units.Quantity("... N") converts correctly to FreeCAD internal units.
force_c = ObjectsFem.makeConstraintForce(doc, "ForceConstraint")
force_c.References = [(part_obj, "{force_ref}")]
force_c.Force = App.Units.Quantity("{force_n} N")
force_c.Reversed = {reversed_}
analysis.addObject(force_c)

# Mesh
mesh = ObjectsFem.makeMeshGmsh(doc, "FEMMesh")
mesh.Shape = part_obj
mesh.CharacteristicLengthMax = MESH_SIZE
analysis.addObject(mesh)
doc.recompute()

try:
    from femmesh.gmshtools import GmshTools
    gt = GmshTools(mesh)
    err = gt.create_mesh()
    if err:
        print(f"MESH_WARNING: {{err}}")
    print(f"MESH_OK: {{mesh.FemMesh.NodeCount}} nodes")
except Exception as e:
    print(f"MESH_ERROR: {{e}}")
    traceback.print_exc()
    sys.exit(1)

doc.recompute()

# Solver – CCX binary found via PATH (set by runner)
solver = ObjectsFem.makeSolverCalculiXCcxTools(doc, "CalculiX")
analysis.addObject(solver)
doc.recompute()

try:
    from femtools.ccxtools import FemToolsCcx
    work_dir = os.path.join(SAVE_DIR, "ccx_work")
    os.makedirs(work_dir, exist_ok=True)
    fea = FemToolsCcx(analysis, solver)
    fea.update_objects()
    fea.setup_working_dir(work_dir)
    fea.ccx_binary = "ccx"   # resolved via PATH
    fea.ccx_binary_present = True
    fea.setup_ccx()
    solve_err = fea.run()
    print(f"SOLVER_DONE: {{solve_err}}")
except Exception as e:
    print(f"FEA_ERROR: {{e}}")
    traceback.print_exc()
    sys.exit(1)

res_obj = next(
    (o for o in doc.Objects if hasattr(o, "vonMises") and o.vonMises),
    None
)

if res_obj:
    vm = list(res_obj.vonMises)
    disp = list(res_obj.DisplacementLengths) if res_obj.DisplacementLengths else [0.0]
    out = {{
        "solver_status": "OK",
        "max_von_mises_MPa": round(max(vm), 2),
        "min_von_mises_MPa": round(min(vm), 2),
        "mean_von_mises_MPa": round(sum(vm) / len(vm), 2),
        "max_displacement_mm": round(max(disp), 4),
        "node_count": len(vm),
    }}
else:
    out = {{"solver_status": "NO_RESULTS", "solve_error": str(solve_err)}}

print("FEM_RESULT:" + json.dumps(out))
"""
