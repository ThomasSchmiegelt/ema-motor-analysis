"""Full E-machine analysis pipeline: Geometry → EM → Structural FEM → Post-processing."""

import math, io, base64, os, json, re, datetime, subprocess, shutil
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec
from matplotlib.colors import PowerNorm
from matplotlib.lines import Line2D

from freecad_runner import run_freecad_script
from ema_freecad   import build_full_motor_script, build_rotor_fem_script
from ema_rotorcheck import rotor_layout_check, rotor_stress_check, _bore_hoop_mpa


def _gate_rotor_layout(data: dict, state: dict | None = None,
                       fatal: bool = True) -> None:
    """Hard pre-CAD gate: reject rotor layouts whose magnet pockets collide,
    breach the bore/rim or leave webs thinner than the manufacturing minimum.
    Runs pure 2-D math on ema_topology records (milliseconds) and covers all
    entry points that build geometry (cad_preview + full analyse).

    ``fatal=False`` downgrades the rejection to a logged warning.  Used when an
    EXISTING project is only partially recomputed: its geometry was built before
    this gate existed, is already on disk and is not rebuilt — refusing the run
    there would lock the user out of recomputing thermal/drivecycle on a project
    that is otherwise perfectly loadable."""
    geom = (data or {}).get("geom") or {}
    if not geom:
        return
    chk = rotor_layout_check(geom)
    if state is not None:
        lay = chk["layout"]
        verdict = "OK" if chk["ok"] else "ABGELEHNT"
        _log(state, f"\U0001F6E1 Rotorlayout-Check: {lay['label']}, "
                    f"{lay['pockets_total']} Taschen, "
                    f"minimaler Abstand {lay['min_web_found_mm']} mm "
                    f"(mind. {lay['min_web_req_mm']} mm) - {verdict}", 5)
    if not chk["ok"]:
        msg = "Rotorlayout-Check fehlgeschlagen: " + "; ".join(chk["fatal"])
        if fatal:
            raise RuntimeError(msg)
        _log(state, "\u26A0 " + msg + " (Nachrechnen laeuft trotzdem weiter — "
                    "die Geometrie auf der Platte wird nicht neu gebaut.)", 5)
    for w in chk.get("warnings", []):
        if state is not None:
            _log(state, "\u26A0 " + w, 5)


def _gate_rotor_stress(data: dict, state: dict | None = None,
                       fatal: bool = True) -> None:
    """Hard pre-CAD centrifugal gate.  Reports BOTH 2-D plane states and gates on the
    CONSERVATIVE (plane-strain) bore hoop stress at n_max.

    Physical note (kept on the log so the number is never misread): a real IPM rotor
    has finite axial length and magnet pockets, so it sits BETWEEN the thin-disc
    (plane stress, optimistic) and the continuous-cylinder (plane strain, conservative)
    bounds.  Both are exact for their respective 2-D problems; the definitive, binding
    safety factor needs the 3-D FEM on the real rotor (Stage C). Pure math (msec).

    ``fatal=False``: see ``_gate_rotor_layout`` — warn instead of refuse when an
    existing project is only partially recomputed."""
    geom = (data or {}).get("geom") or {}
    if not geom:
        return
    mat = LAMINATES.get(data.get("rotor_lam", "m270_35a"),
                        LAMINATES["m270_35a"])
    tgt  = data.get("target") or {}
    nmax = float(tgt.get("n_max", data.get("rpm_to", 20000.0)))
    st = rotor_stress_check(geom, mat, {"n_max": nmax})
    if state is not None:
        icon = {"PASS": "\u2705", "WARN": "\u26A0\uFE0F", "FAIL": "\u274C"}[st["level"]]
        mname = mat.get("label") or "rotor"
        _log(state,
             f"\U0001F6E1 Rotor-Festigkeit ({nmax:.0f} U/min, {mname}):  "
             f"Scheibe  \u03C3 {st['sigma_bore_plane_stress_MPa']:6.1f} MPa (SF {st['sf_plane_stress']:.2f}) | "
             f"Zylinder \u03C3 {st['sigma_bore_conservative_MPa']:6.1f} MPa (SF {st['safety_factor']:.2f}) | "
             f"Peak (Kt={st['kt_pocket']:.1f}) \u03C3 {st['sigma_peak_MPa']:.1f} MPa (SF {st['safety_factor_peak']:.2f}) | "
             f"Fliessgrenze {st['yield_mpa']:.0f} MPa {icon} {st['level']}", 5)
        _log(state, "   Tier-1 = Machbarkeits-Screen (hard-fail nur bei SF_peak < 1.0); "
                    "bindend ist Tier-2: 3D-FEM-P99 vs. Fliessgrenze (Stage 5).", 5)
    if st["safety_factor_peak"] < 1.0:
        _mkmsg = (
            f"Rotor-Festigkeitsgate nicht bestanden: Peak-Spannung (2D-Ring x Kt={st['kt_pocket']}) "
            f"{st['sigma_peak_MPa']:.1f} MPa an der Bohrung bei {nmax:.0f} U/min "
            f"gibt SF {st['safety_factor_peak']:.2f} < 1.0 - Rotor fliesst sicher. "
            f"(Fliess {st['yield_mpa']:.0f} MPa) Geometrie verkleinern (rotorOD/Aufnahme) "
            f"oder n_max senken, dann neu laufen lassen.")
        if fatal:
            raise RuntimeError(_mkmsg)
        _log(state, "\u26A0 " + _mkmsg + " (Nachrechnen laeuft trotzdem weiter.)", 5)
    elif state is not None and not st["ok"]:
        _log(state, f"   ⚠ Tier-1: SF_peak {st['safety_factor_peak']:.2f} unter Ziel "
                    f"{st['sf_target']:.1f}, aber machbar -> entscheidet Tier-2 (3D-FEM).", 5)

import ema_analysis
import ema_thermal
import ema_drivecycle


# ── Project directory ─────────────────────────────────────────────────────────

def create_project_dir(root: str, name: str = "", *,
                       origin: str = "analyse", parent=None) -> tuple[str, str]:
    """Create a fresh ~/cae_projekte/<timestamp>[_<name>]/ directory.
    Returns (full_path, project_id).

    Also lays down the Projektakte stub (``project.json``) *first*, so the manifest
    exists before any computation (``origin``/``parent`` record provenance/lineage)."""
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[^\w\-]+', '_', (name or "").strip())[:48].strip("_")
    pid  = f"{ts}_{safe}" if safe else ts
    full = os.path.join(root, pid)
    os.makedirs(full, exist_ok=True)
    for sub in ("cad_images", "charts", "frames"):
        os.makedirs(os.path.join(full, sub), exist_ok=True)
    try:
        import ema_projekt
        ema_projekt.init(full, pid, origin=origin, parent=parent, label=name or pid)
    except Exception:
        pass
    return full, pid


def _save_png_b64(b64: str, path: str) -> None:
    """Decode a base64 PNG string and write to disk."""
    if not b64:
        return
    try:
        with open(path, "wb") as f:
            f.write(base64.b64decode(b64))
    except Exception:
        pass


# Field-visualisation modes → (frames bucket key, on-disk subdir). Must stay in
# sync with server.py FIELD_SUBDIRS and the ema.html mode selector.
FIELD_SUBDIRS = {"rotate": "frames", "react": "frames_react", "load": "frames_load"}


def _make_video(frames_dir: str, fps: int = 15) -> str | None:
    """Encode frame_%04d.png in frames_dir into anim.mp4 via ffmpeg. Returns path or None."""
    out = os.path.join(frames_dir, "anim.mp4")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps),
             "-i", os.path.join(frames_dir, "frame_%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out],
            capture_output=True, text=True, timeout=180)
        return out if (r.returncode == 0 and os.path.exists(out)) else None
    except Exception:
        return None


# _export_step retained as fallback only — main path inlines STEP into the
# main FreeCAD subprocess via build_full_motor_script in ema_freecad.py.

# ── Material databases ────────────────────────────────────────────────────────

# Electrical steel laminations for rotor and stator
# specific_loss_Wkg: P [W/kg] at 1 T / 50 Hz (Bertotti reference)
LAMINATES = {
    "m250_35a":     {"label": "M250-35A (Premium, 0.35 mm)",   "specific_loss_Wkg": 2.5,  "B_sat_T": 1.65, "density": 7650, "E": 200000, "nu": 0.30, "yield_mpa": 350},
    "m270_35a":     {"label": "M270-35A (Standard, 0.35 mm)",  "specific_loss_Wkg": 2.7,  "B_sat_T": 1.70, "density": 7650, "E": 200000, "nu": 0.30, "yield_mpa": 340},
    "m400_50a":     {"label": "M400-50A (Günstig, 0.50 mm)",   "specific_loss_Wkg": 4.0,  "B_sat_T": 1.80, "density": 7700, "E": 200000, "nu": 0.30, "yield_mpa": 380},
    "m800_65a":     {"label": "M800-65A (Grob, 0.65 mm)",      "specific_loss_Wkg": 8.0,  "B_sat_T": 1.85, "density": 7800, "E": 210000, "nu": 0.30, "yield_mpa": 400},
    "steel_s235":   {"label": "Stahl S235 (Vollmaterial)",      "specific_loss_Wkg": 15.0, "B_sat_T": 2.00, "density": 7850, "E": 210000, "nu": 0.30, "yield_mpa": 235},
    "steel_42crmo4":{"label": "42CrMo4 vergütet (Vollmaterial)","specific_loss_Wkg": 12.0, "B_sat_T": 2.00, "density": 7850, "E": 210000, "nu": 0.30, "yield_mpa": 900},
}

# Copper / aluminium conductors for hairpin windings
# rho_el: electrical resistivity [Ω·m] at 20 °C
HAIRPIN_MATS = {
    "cu_etp":   {"label": "Cu-ETP (Reinst-Kupfer, 99.9 %)", "rho_el": 1.72e-8, "density": 8900, "E": 120000, "nu": 0.34},
    "cu_crZr":  {"label": "CuCrZr (Hochfest-Kupfer)",       "rho_el": 2.05e-8, "density": 8900, "E": 125000, "nu": 0.34},
    "cu_ag01":  {"label": "CuAg0.1 (Silber-Kupfer)",        "rho_el": 1.75e-8, "density": 8930, "E": 120000, "nu": 0.34},
    "al_1350":  {"label": "Al 1350-H19 (Aluminium)",        "rho_el": 2.83e-8, "density": 2700, "E":  68000, "nu": 0.33},
}

# T_op_max = max. continuous operating temp (irreversible-loss onset for the
# base "N" grade); T_curie = Curie temperature (magnet destroyed above).
# rho_el: electrical resistivity [Ω·m] (drives magnet-eddy skin depth);
# alpha_Br: remanence temperature coefficient [1/K] (Br(T) = Br·(1+alpha_Br·(T-20)))
MAGNETS = {
    "ndfeb_n35": {"label": "NdFeB N35", "Br": 1.15, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310, "rho_el": 1.4e-6, "alpha_Br": -0.0012},
    "ndfeb_n42": {"label": "NdFeB N42", "Br": 1.28, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310, "rho_el": 1.4e-6, "alpha_Br": -0.0012},
    "ndfeb_n50": {"label": "NdFeB N50", "Br": 1.40, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310, "rho_el": 1.4e-6, "alpha_Br": -0.0012},
    "ferrite":   {"label": "Ferrit Y30","Br": 0.40, "mu_r": 1.07, "T_op_max": 250, "T_curie": 450, "rho_el": 1.0e4,  "alpha_Br": -0.0020},
}

# Backward-compat alias for the structural FEM helper
MATERIALS = {k: {**v, "label": v["label"]} for k, v in LAMINATES.items()}

RPM_SWEEP = [500, 1000, 2000, 3000, 5000, 7000, 10000, 15000, 20000]


def _rpm_sweep_from_range(rpm_from: float, rpm_to: float, rpm_step: float) -> list[int]:
    """Build an RPM list from from/to/step, always including endpoints."""
    if rpm_step <= 0:
        rpm_step = 1000
    out = []
    r = rpm_from
    while r <= rpm_to + 1e-3:
        out.append(int(round(r)))
        r += rpm_step
    if not out or out[-1] < rpm_to:
        out.append(int(round(rpm_to)))
    return out


# ── Helpers ───────────────────────────────────────────────────────────────────

def _parse_frd(frd_path: str, yield_mpa: float = 0.0) -> dict:
    """Parse a CalculiX .frd file — scalars only (for summary dict)."""
    import math as _m
    disp: dict = {}
    stress_vm: dict = {}
    mode = None
    header_skip = 0

    try:
        with open(frd_path) as f:
            lines = f.readlines()
    except OSError:
        return {"solver_status": "FRD_NOT_FOUND", "frd_path": frd_path}

    for ln in lines:
        if " -4  DISP" in ln:
            mode = "disp"; header_skip = 4; continue
        if " -4  STRESS" in ln:
            mode = "stress"; header_skip = 6; continue
        if ln.startswith(" -4 ") and mode:
            mode = None; continue
        if header_skip > 0 and ln.startswith(" -5"):
            header_skip -= 1; continue

        if mode == "disp" and ln.startswith(" -1"):
            try:
                nid = int(ln[3:13])
                d1 = float(ln[13:25]); d2 = float(ln[25:37]); d3 = float(ln[37:49])
                mag = _m.sqrt(d1*d1 + d2*d2 + d3*d3)
                if mag < 1.0:
                    disp[nid] = mag
            except (ValueError, IndexError):
                pass
        elif mode == "stress" and ln.startswith(" -1"):
            try:
                nid = int(ln[3:13])
                sxx = float(ln[13:25]); syy = float(ln[25:37]); szz = float(ln[37:49])
                sxy = float(ln[49:61]); syz = float(ln[61:73]); szx = float(ln[73:85])
                vm = _m.sqrt(0.5 * ((sxx-syy)**2 + (syy-szz)**2 + (szz-sxx)**2
                                    + 6*(sxy*sxy + syz*syz + szx*szx)))
                stress_vm[nid] = vm
            except (ValueError, IndexError):
                pass

    valid_stress = {k: v for k, v in stress_vm.items() if k in disp}
    if not valid_stress:
        return {"solver_status": "NO_VALID_NODES", "frd_path": frd_path,
                "disp_nodes": len(disp), "stress_nodes": len(stress_vm)}

    max_vm = max(valid_stress.values())
    max_d  = max(disp.values()) if disp else 0.0
    sf = round(yield_mpa / max_vm, 2) if yield_mpa > 0 and max_vm > 0 else None

    return {
        "solver_status":       "OK",
        "max_von_mises_MPa":   round(max_vm, 2),
        "mean_von_mises_MPa":  round(sum(valid_stress.values()) / len(valid_stress), 2),
        "max_displacement_mm": round(max_d, 4),
        "max_displacement_um": round(max_d * 1e3, 3),
        "node_count":          len(valid_stress),
        "safety_factor":       sf,
    }


def _parse_frd_full(frd_path: str, yield_mpa: float = 0.0) -> dict:
    """Extended FRD parser — also returns per-node coords and displacements for plotting."""
    import math as _m

    nodes: dict[int, tuple[float,float,float]] = {}   # nid → (x, y, z) [mm]
    disp_vec: dict[int, tuple[float,float,float]] = {} # nid → (dx, dy, dz) [mm]
    disp_mag: dict[int, float] = {}
    stress_vm: dict[int, float] = {}
    mode = None
    header_skip = 0
    in_node_block = False

    try:
        with open(frd_path) as f:
            lines = f.readlines()
    except OSError:
        return {"solver_status": "FRD_NOT_FOUND"}

    for ln in lines:
        # Node-coordinate block starts with "    2C"
        if ln.startswith("    2C") or ln.startswith("  2C"):
            in_node_block = True; continue
        if in_node_block and ln.startswith(" -3"):
            in_node_block = False; continue
        if in_node_block and ln.startswith(" -1"):
            try:
                nid = int(ln[3:13])
                x = float(ln[13:25]); y = float(ln[25:37]); z = float(ln[37:49])
                nodes[nid] = (x, y, z)
            except (ValueError, IndexError):
                pass
            continue

        if " -4  DISP" in ln:
            mode = "disp"; header_skip = 4; continue
        if " -4  STRESS" in ln:
            mode = "stress"; header_skip = 6; continue
        if ln.startswith(" -4 ") and mode:
            mode = None; continue
        if header_skip > 0 and ln.startswith(" -5"):
            header_skip -= 1; continue

        if mode == "disp" and ln.startswith(" -1"):
            try:
                nid = int(ln[3:13])
                d1 = float(ln[13:25]); d2 = float(ln[25:37]); d3 = float(ln[37:49])
                mag = _m.sqrt(d1*d1 + d2*d2 + d3*d3)
                if mag < 1.0:
                    disp_vec[nid] = (d1, d2, d3)
                    disp_mag[nid] = mag
            except (ValueError, IndexError):
                pass
        elif mode == "stress" and ln.startswith(" -1"):
            try:
                nid = int(ln[3:13])
                sxx = float(ln[13:25]); syy = float(ln[25:37]); szz = float(ln[37:49])
                sxy = float(ln[49:61]); syz = float(ln[61:73]); szx = float(ln[73:85])
                vm = _m.sqrt(0.5 * ((sxx-syy)**2 + (syy-szz)**2 + (szz-sxx)**2
                                    + 6*(sxy*sxy + syz*syz + szx*szx)))
                stress_vm[nid] = vm
            except (ValueError, IndexError):
                pass

    valid = {k: v for k, v in stress_vm.items() if k in disp_mag}
    if not valid:
        return {"solver_status": "NO_VALID_NODES",
                "nodes": nodes, "disp_mag": disp_mag}

    max_vm = max(valid.values())
    max_d  = max(disp_mag.values()) if disp_mag else 0.0
    # P99 = notch-toleranter Gate-Wert: das Rohmaximum an scharfen
    # Taschenkanten ist eine Gitter-Singularitaet; P99 ist der vertretbare
    # "schlechteste reale" Wert (verifiziert c2: FEM-P99 392 MPa ~ Kt x Lame 398).
    _sv   = sorted(valid.values())
    _i    = min(len(_sv) - 1, len(_sv) - 1 - len(_sv) // 100)
    notch_peak = _sv[_i]
    sf = round(yield_mpa / max_vm, 2) if yield_mpa > 0 and max_vm > 0 else None

    return {
        "solver_status":       "OK",
        "max_von_mises_MPa":   round(max_vm, 2),
        "notch_peak_MPa":      round(notch_peak, 2),
        "mean_von_mises_MPa":  round(sum(valid.values()) / len(valid), 2),
        "max_displacement_mm": round(max_d, 4),
        "max_displacement_um": round(max_d * 1e3, 3),
        "node_count":          len(valid),
        "safety_factor":       sf,
        # Geometry data for plotting (not serialised to JSON)
        "_nodes":     nodes,
        "_disp_vec":  disp_vec,
        "_disp_mag":  disp_mag,
        "_stress_vm": valid,
    }


def _fem_deformation_plot(frd_full: dict, geom: dict, rpm: float) -> tuple[str, dict]:
    """Generate deformation plot from parsed FRD data. Returns (base64_png, stats_dict)."""
    nodes    = frd_full.get("_nodes",    {})
    disp_vec = frd_full.get("_disp_vec", {})
    disp_mag = frd_full.get("_disp_mag", {})

    if not nodes or not disp_mag:
        return "", {}

    # Collect nodes that have both coordinates and valid displacement
    common = [nid for nid in disp_mag if nid in nodes]
    if not common:
        return "", {}

    xs  = np.array([nodes[n][0] for n in common])
    ys  = np.array([nodes[n][1] for n in common])
    um  = np.array([disp_mag[n] * 1e3 for n in common])   # mm → µm
    dxs = np.array([disp_vec[n][0] for n in common])
    dys = np.array([disp_vec[n][1] for n in common])

    u_max_um    = float(np.max(um))
    u_radial    = np.sqrt(xs**2 + ys**2)
    u_rad_disp  = np.abs(xs * dxs + ys * dys) / (u_radial + 1e-9)  # radial component
    u_radial_um = float(np.max(u_rad_disp) * 1e3)

    # Scale factor: exaggerate so the max deformation spans ~5% of rotor radius
    R_rot = geom["rotorOD"] / 2
    max_d_mm = float(np.max([disp_mag[n] for n in common]))
    scale_factor = max(1, int(R_rot * 0.05 / (max_d_mm + 1e-9)))
    scale_factor = min(scale_factor, 5000)

    xs_def = xs + dxs * scale_factor
    ys_def = ys + dys * scale_factor

    fig, axes = plt.subplots(1, 2, figsize=(13, 6), facecolor="#0d0d0d")

    for ax, (px, py, title_suffix) in zip(
            axes,
            [(xs,     ys,     f"Unverformt  (×1)"),
             (xs_def, ys_def, f"Verformt  (×{scale_factor})")]):
        ax.set_facecolor("#0d0d0d")
        sc = ax.scatter(px, py, c=um, cmap="plasma", s=2, vmin=0, vmax=max(u_max_um, 0.01))

        # Geometry reference circles
        th = np.linspace(0, 2*math.pi, 360)
        for r_mm, col in [(R_rot, "#aaa"), (geom["shaftD"]/2, "#888"),
                          (geom["statorID"]/2, "#555"), (geom["statorOD"]/2, "#444")]:
            ax.plot(r_mm*np.cos(th), r_mm*np.sin(th), col, lw=0.6, alpha=0.6)

        ax.set_aspect("equal")
        ax.set_title(f"{title_suffix}", color="#bbb", fontsize=9)
        ax.tick_params(colors="#666", labelsize=7)
        for sp in ax.spines.values(): sp.set_color("#333")
        ax.set_xlabel("x [mm]", color="#888", fontsize=8)
        ax.set_ylabel("y [mm]", color="#888", fontsize=8)

    cb = fig.colorbar(sc, ax=axes, pad=0.01, fraction=0.015)
    cb.set_label("Verschiebung [µm]", color="#aaa", fontsize=8)
    cb.ax.yaxis.set_tick_params(color="#666", labelsize=7)
    plt.setp(cb.ax.yaxis.get_ticklabels(), color="#aaa")

    fig.suptitle(
        f"FEM-Verformung Rotor  |  {rpm:,.0f} U/min  |  "
        f"u_max = {u_max_um:.2f} µm  |  Skalierung ×{scale_factor}".replace(",", "."),
        color="white", fontsize=10, y=1.01)
    fig.tight_layout()

    stats = {
        "u_max_um":     round(u_max_um, 3),
        "u_radial_um":  round(u_radial_um, 3),
        "scale_factor": scale_factor,
        "node_count":   len(common),
        "rpm":          rpm,
    }
    return _fig_b64(fig), stats


# ── Scaled deformation (single FEM solve → any RPM via rpm² linearity) ─────────
#
# A centrifugal load is a body force ∝ ω², and linear-elastic FEM is linear in the
# load, so BOTH the displacement field and the von-Mises stress scale exactly with
# (rpm/rpm_solve)².  We therefore solve CalculiX once (at rpm_solve, the worst-case
# max speed) and reconstruct the result at any other speed by this scale factor —
# used for the burst-speed estimate, the high-res single images (rated / max /
# burst) and every deformation-video frame, all from one solve.

def _deform_extract(frd_full: dict):
    """Pull node coords + displacement vectors from a parsed FRD into arrays.

    Returns (xs, ys, dxs, dys, dmag_mm) in mm, or None if no usable data.
    """
    nodes    = frd_full.get("_nodes",    {})
    disp_vec = frd_full.get("_disp_vec", {})
    disp_mag = frd_full.get("_disp_mag", {})
    common = [nid for nid in disp_mag if nid in nodes]
    if not common:
        return None
    xs   = np.array([nodes[n][0]    for n in common])
    ys   = np.array([nodes[n][1]    for n in common])
    dxs  = np.array([disp_vec[n][0] for n in common])
    dys  = np.array([disp_vec[n][1] for n in common])
    dmag = np.array([disp_mag[n]    for n in common])   # mm
    return xs, ys, dxs, dys, dmag


def _burst_rpm(sigma_solve_mpa: float, rpm_solve: float, yield_mpa: float) -> float | None:
    """Speed where the peak von-Mises stress reaches the yield limit (SF→1).

    σ ∝ rpm², so rpm_burst = rpm_solve · √(σ_yield / σ(rpm_solve)).
    """
    if sigma_solve_mpa <= 0 or rpm_solve <= 0 or yield_mpa <= 0:
        return None
    return rpm_solve * math.sqrt(yield_mpa / sigma_solve_mpa)


def _deform_title(title_prefix, rpm_target, u_max_um, sigma_t, sf_t, exagg):
    sf_txt = f"SF = {sf_t:.2f}" if sf_t is not None else "SF = –"
    if sf_t is not None and sf_t < 1.0:
        sf_txt += "  ⚠ Streckgrenze überschritten"
    return (f"{title_prefix}  |  {rpm_target:,.0f} U/min  |  u_max = {u_max_um:.2f} µm  |  "
            f"σ_v,max = {sigma_t:.0f} MPa  |  {sf_txt}  |  Überhöhung ×{exagg:.0f}"
            ).replace(",", ".")


def _render_deform_analytical(geom: dict, mat: dict, rpm_target: float, rpm_solve: float,
                              sigma_solve_mpa: float, yield_mpa: float, exagg: float,
                              px: int = 3000, max_um_clip: float | None = None,
                              title_prefix: str = "Verformung (analytisch)"
                              ) -> tuple[str, dict]:
    """Smooth render of the axisymmetric rotating-disc (Lamé) deformation.

    The analytical solution depends only on radius, so instead of a confusing
    scattered point cloud it is drawn as a SMOOTH filled annulus coloured by the
    radial displacement |u(r)|, with the undeformed rotor OD/bore outlines and the
    exaggerated deformed outlines (dashed) overlaid — so the radial growth reads at
    a glance and nobody mistakes it for a meshed FEM result.
    """
    a = max(geom["shaftD"] / 2.0, 1.0)                 # bore radius [mm]
    b = max(geom["rotorOD"] / 2.0, a + 1.0)            # OD radius [mm]
    E = float(mat["E"]) * 1e6; nu = float(mat["nu"]); rho = float(mat["density"])
    omega = rpm_target * 2 * math.pi / 60.0
    C  = rho * omega ** 2
    am, bm = a / 1000.0, b / 1000.0

    def _u_mm(r_mm):                                    # radial displacement [mm] at r
        rm = np.asarray(r_mm) / 1000.0; r2 = rm * rm
        with np.errstate(divide="ignore", invalid="ignore"):
            sr = (3 + nu) / 8.0 * C * (am * am + bm * bm - am * am * bm * bm / r2 - r2)
            st = C / 8.0 * ((3 + nu) * (am * am + bm * bm + am * am * bm * bm / r2)
                            - (1 + 3 * nu) * r2)
            return (rm / E * (st - nu * sr)) * 1000.0

    N = 520; ext = b * 1.12
    g = np.linspace(-ext, ext, N); X, Y = np.meshgrid(g, g)
    Rmm = np.hypot(X, Y)
    um_field = np.abs(_u_mm(Rmm)) * 1000.0             # mm → µm
    um_field = np.where((Rmm >= a) & (Rmm <= b), um_field, np.nan)
    u_max_um = float(np.nanmax(um_field)) if np.isfinite(um_field).any() else 0.0

    s       = (rpm_target / rpm_solve) ** 2 if rpm_solve > 0 else 0.0
    sigma_t = sigma_solve_mpa * s
    sf_t    = (yield_mpa / sigma_t) if sigma_t > 1e-6 else None
    vmax    = max_um_clip if (max_um_clip and max_um_clip > 0) else max(u_max_um, 0.01)

    fig_in = max(5.0, px / 600.0)
    fig, ax = plt.subplots(figsize=(fig_in, fig_in), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    im = ax.imshow(um_field, extent=[-ext, ext, -ext, ext], origin="lower",
                   cmap="plasma", vmin=0, vmax=vmax, interpolation="bilinear")
    th = np.linspace(0, 2 * math.pi, 360); ct, st_ = np.cos(th), np.sin(th)
    for r_mm in (b, a):
        ax.plot(r_mm * ct, r_mm * st_, "#aaa", lw=0.8, alpha=0.6)        # undeformed
        rd = r_mm + float(_u_mm(r_mm)) * exagg
        ax.plot(rd * ct, rd * st_, "#00e5ff", lw=1.0, ls="--", alpha=0.9)  # deformed (×exagg)
    ax.set_aspect("equal"); ax.axis("off")

    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label("Radiale Verschiebung |u| [µm]", color="#ddd", fontsize=10)
    cb.ax.tick_params(color="#666", labelcolor="#bbb", labelsize=8)
    cb.outline.set_edgecolor("#444")
    handles = [Line2D([0], [0], color="#aaa", lw=1.2, label="unverformt (OD/Bohrung)"),
               Line2D([0], [0], color="#00e5ff", lw=1.2, ls="--",
                      label=f"verformt ×{exagg:.0f}")]
    ax.legend(handles=handles, loc="lower left", fontsize=8, framealpha=0.6,
              facecolor="#0d0d0d", edgecolor="#444", labelcolor="#ddd")
    fig.suptitle(_deform_title(title_prefix, rpm_target, u_max_um, sigma_t, sf_t, exagg),
                 color="white", fontsize=11, y=0.98)
    fig.tight_layout()
    stats = {"rpm": round(rpm_target), "u_max_um": round(u_max_um, 3),
             "sigma_max_MPa": round(sigma_t, 1),
             "safety_factor": round(sf_t, 2) if sf_t is not None else None,
             "scale_factor": round(exagg)}
    dpi = max(90, int(px / fig_in))
    return _fig_b64(fig, dpi=dpi), stats


def _render_deform_single(arrays, geom: dict, rpm_target: float, rpm_solve: float,
                          sigma_solve_mpa: float, yield_mpa: float, exagg: float,
                          px: int = 3000, max_um_clip: float | None = None,
                          subsample: int | None = None,
                          title_prefix: str = "FEM-Verformung") -> tuple[str, dict]:
    """Render ONE deformed-rotor view at ``rpm_target`` from the single solve.

    arrays      : output of _deform_extract (solved at rpm_solve).
    exagg       : fixed displacement exaggeration factor (shared across all images
                  / video frames so the growth with speed is visually comparable).
    max_um_clip : fixed colour-scale ceiling [µm] for a consistent colour map.
    subsample   : plot every Nth node (video frames use this for speed).
    """
    xs, ys, dxs, dys, dmag = arrays
    if subsample and subsample > 1:
        xs, ys, dxs, dys, dmag = (a[::subsample] for a in (xs, ys, dxs, dys, dmag))

    s          = (rpm_target / rpm_solve) ** 2 if rpm_solve > 0 else 0.0   # rpm² scaling
    um         = dmag * s * 1e3                                            # mm → µm
    u_max_um   = float(np.max(um)) if um.size else 0.0
    sigma_t    = sigma_solve_mpa * s
    sf_t       = (yield_mpa / sigma_t) if sigma_t > 1e-6 else None

    xs_def = xs + dxs * s * exagg
    ys_def = ys + dys * s * exagg

    R_rot = geom["rotorOD"] / 2
    vmax  = max_um_clip if (max_um_clip and max_um_clip > 0) else max(u_max_um, 0.01)

    fig_in = max(5.0, px / 600.0)
    fig, ax = plt.subplots(figsize=(fig_in, fig_in), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")
    sc = ax.scatter(xs_def, ys_def, c=um, cmap="plasma", s=3, vmin=0, vmax=vmax)
    th = np.linspace(0, 2 * math.pi, 360)
    for r_mm, col in [(R_rot, "#aaa"), (geom["shaftD"] / 2, "#888")]:
        ax.plot(r_mm * np.cos(th), r_mm * np.sin(th), col, lw=0.7, alpha=0.55)
    ax.set_aspect("equal"); ax.axis("off")

    cb = fig.colorbar(sc, ax=ax, fraction=0.046, pad=0.02)
    cb.set_label("Verschiebung [µm]", color="#ddd", fontsize=10)
    cb.ax.tick_params(color="#666", labelcolor="#bbb", labelsize=8)
    cb.outline.set_edgecolor("#444")

    fig.suptitle(_deform_title(title_prefix, rpm_target, u_max_um, sigma_t, sf_t, exagg),
                 color="white", fontsize=11, y=0.98)
    fig.tight_layout()

    stats = {
        "rpm":          round(rpm_target),
        "u_max_um":     round(u_max_um, 3),
        "sigma_max_MPa": round(sigma_t, 1),
        "safety_factor": round(sf_t, 2) if sf_t is not None else None,
        "scale_factor": round(exagg),
    }
    dpi = max(90, int(px / fig_in))
    return _fig_b64(fig, dpi=dpi), stats


def _deformation_video(arrays, geom: dict, rpm_max: float, rpm_solve: float,
                       sigma_solve_mpa: float, yield_mpa: float, exagg: float,
                       max_um_clip: float, frames_dir: str, n_frames: int = 30,
                       title_prefix: str = "FEM-Verformung",
                       smooth_mat: dict | None = None) -> str | None:
    """Render an rpm 0→rpm_max deformation ramp (fixed exaggeration) → anim.mp4.

    The displacement grows with rpm² at the fixed exaggeration, so the rotor is
    seen visibly bulging out as speed rises — a feel for where/how it deforms.
    ``smooth_mat`` set → use the smooth analytical (Lamé) renderer instead of the
    FEM point-scatter (so the analytical video is a clean filled annulus too).
    """
    os.makedirs(frames_dir, exist_ok=True)
    # subsample nodes for speed (video frames are small); keep >= ~6k points
    npts = len(arrays[0])
    sub  = max(1, npts // 6000)
    rpms = np.linspace(0.0, rpm_max, max(2, n_frames))
    for i, rpm in enumerate(rpms):
        if smooth_mat is not None:
            b64, _ = _render_deform_analytical(
                geom, smooth_mat, float(rpm), rpm_solve, sigma_solve_mpa, yield_mpa,
                exagg, px=700, max_um_clip=max_um_clip, title_prefix=title_prefix)
        else:
            b64, _ = _render_deform_single(
                arrays, geom, float(rpm), rpm_solve, sigma_solve_mpa, yield_mpa,
                exagg, px=700, max_um_clip=max_um_clip, subsample=sub,
                title_prefix=title_prefix)
        _save_png_b64(b64, os.path.join(frames_dir, f"frame_{i:04d}.png"))
    return _make_video(frames_dir, fps=12)


def _analytical_deform_arrays(geom: dict, mat: dict, rpm: float, n: int = 6000):
    """Rotating annular-disc (Lamé, plane stress) deformation — FEM-free fallback.

    Returns ((xs, ys, dxs, dys, dmag) in mm at ``rpm``, sigma_hoop_max_MPa).
    Used when CalculiX cannot solve the rotor (e.g. thin/disconnected iron bridges
    in aggressive multi-layer topologies) so the Verformung tab still shows the
    radial growth. Radial displacement u(r) = r/E·(σ_θ − ν·σ_r); the disc is the
    rotor annulus shaft→OD. Same arrays shape as _deform_extract, so the existing
    renderer/video (rpm² scaling) work unchanged.
    """
    a = max(geom["shaftD"] / 2.0, 1.0) / 1000.0     # inner radius [m]
    b = max(geom["rotorOD"] / 2.0, a * 1000 + 1) / 1000.0
    E   = float(mat["E"]) * 1e6                      # MPa → Pa
    nu  = float(mat["nu"]);  rho = float(mat["density"])
    omega = rpm * 2 * math.pi / 60.0
    C = rho * omega ** 2
    rng = np.random.default_rng(0)
    rr = np.sqrt(rng.uniform((a / b) ** 2, 1.0, n)) * b     # radius [m], area-uniform
    th = rng.uniform(0, 2 * math.pi, n)
    r2 = rr * rr
    sr = (3 + nu) / 8.0 * C * (a * a + b * b - a * a * b * b / r2 - r2)
    st = C / 8.0 * ((3 + nu) * (a * a + b * b + a * a * b * b / r2) - (1 + 3 * nu) * r2)
    u  = rr / E * (st - nu * sr)                            # radial displacement [m]
    rr_mm = rr * 1000.0;  ur_mm = u * 1000.0
    cx, cy = np.cos(th), np.sin(th)
    xs, ys = rr_mm * cx, rr_mm * cy
    dxs, dys = ur_mm * cx, ur_mm * cy
    dmag = np.abs(ur_mm)
    sigma_hoop_max = float(np.max(st)) / 1e6               # Pa → MPa (peak at bore)
    return (xs, ys, dxs, dys, dmag), sigma_hoop_max


def _log(state, msg, progress=None):
    state["log"].append(msg)
    if progress is not None:
        state["progress"] = int(progress)


def _mat_fc(m: dict) -> dict:
    return {
        "Name":          m["label"],
        "YoungsModulus": f"{m['E']} MPa",
        "PoissonRatio":  str(m["nu"]),
        "Density":       f"{m['density']} kg/m^3",
    }


def _fig_b64(fig, dpi: int = 90) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ── Field frame (single rotor angle) ─────────────────────────────────────────

# Physical display ceiling: electrical steel saturates ~2 T, so the colour scale
# and heatmap are capped here. The linear FDM can compute higher |B| at tooth
# corners (artefacts); the nonlinear saturation pass (run_em_analysis saturate=True)
# removes them physically, and this cap keeps even the linear frames honest.
IRON_B_SAT_DISPLAY = 2.1


def _field_vmax(B) -> float:
    """Display ceiling for the |B| heatmap.

    A plain percentile is dominated by the low-field air/gap pixels (vmax ends up
    ~0.7 T) so the iron — which runs 0.5–1.5 T — over-saturates to the top of the
    colour map.  Instead anchor vmax to the high field (99.9th percentile of the
    spike-clipped magnitude, ≈ the iron peak), floored to 1.6 T so weak-field
    designs stay legible — and capped at the physical saturation level so the
    scale never reads an unphysical >2 T.
    """
    Bc  = np.minimum(B, IRON_B_SAT_DISPLAY)
    pos = Bc[Bc > 1e-4]
    if pos.size == 0:
        return 1.6
    return min(IRON_B_SAT_DISPLAY, max(1.6, 1.4 * float(np.percentile(pos, 99.9))))


def _draw_magnet_outlines(ax, geom: dict, sc: float, ctr: float,
                          rotor_angle: float = 0.0) -> None:
    """Overlay each magnet's outline on a field frame, matching the rasteriser's
    placement (ema_analysis._rasterise). Interior/flat magnets are rectangles,
    surface magnets annular wedges; coloured red (N) / blue (S)."""
    from matplotlib.patches import Polygon as MplPoly
    from ema_topology import magnet_legs
    try:
        legs, _meta = magnet_legs(geom)
    except Exception:
        return
    poles = int(geom["p"]) * 2
    r_ro  = (geom["rotorOD"] / 2) * sc
    for p_i in range(poles):
        pole_ang = p_i * (2 * math.pi / poles) + rotor_angle
        sign     = 1 if p_i % 2 == 0 else -1
        cp, sp   = math.cos(pole_ang), math.sin(pole_ang)
        # Colour by the POLE's PHYSICAL polarity (red = N = net magnetisation pointing
        # radially OUT, blue = S = inward), summed over all legs of the pole. This is
        # the ONLY rule that means the same thing for every topology — pure pole-index
        # parity gives red=S for a V-pole but red=N for SPM (the V arms magnetise
        # inward), so red would mean different polarities in different motors. The
        # IDENTICAL net-radial rule runs in ema.html drawRotor(), so red = the same
        # physical pole in the canvas AND this FEM field plot. Falls back to index
        # parity only when the net radial component vanishes (e.g. spoke = tangential).
        net = 0.0
        for lg in legs:
            la = pole_ang + lg.tilt
            lx, ly = math.cos(la), math.sin(la)
            if lg.mag_mode == "tangential":
                mdx, mdy = -sp, cp
            elif lg.mag_mode == "radial":
                b = pole_ang + lg.mag_rot
                mdx, mdy = math.cos(b), math.sin(b)
            else:
                mdx, mdy = -ly, lx
            if geom.get("magOrient") == "longitudinal":
                mdx, mdy = -mdy, mdx
            amp = sign * lg.mag_sign
            if lg.placement == "surface":
                ca = pole_ang + lg.offset / (geom["rotorOD"] / 2)
                pax, pay = math.cos(ca), math.sin(ca)
            else:
                sx0 = lg.r_pos * cp - lg.offset * sp
                sy0 = lg.r_pos * sp + lg.offset * cp
                mx = sx0 + 0.5 * lg.length * lx
                my = sy0 + 0.5 * lg.length * ly
                rr = math.hypot(mx, my) or 1.0
                pax, pay = mx / rr, my / rr
            net += amp * (mdx * pax + mdy * pay)
        is_n = (net > 0) if abs(net) > 1e-6 else (sign >= 0)
        col  = "#ff5a5a" if is_n else "#4db8ff"
        for lg in legs:
            if lg.placement == "surface":
                magH = lg.thickness * sc
                cang = pole_ang + lg.offset / (geom["rotorOD"] / 2)
                harc = (lg.length / 2) / (geom["rotorOD"] / 2)
                a = np.linspace(cang - harc, cang + harc, 16)
                pts = [(ctr + r_ro * math.cos(t), ctr + r_ro * math.sin(t)) for t in a]
                pts += [(ctr + (r_ro - magH) * math.cos(t),
                         ctr + (r_ro - magH) * math.sin(t)) for t in a[::-1]]
            else:
                long_ang = pole_ang + lg.tilt
                lx, ly = math.cos(long_ang), math.sin(long_ang)
                sx = lg.r_pos * sc * cp - lg.offset * sc * sp
                sy = lg.r_pos * sc * sp + lg.offset * sc * cp
                w, h = lg.length * sc, lg.thickness * sc
                def P(l, t):
                    return (ctr + sx + l * lx + t * (-ly),
                            ctr + sy + l * ly + t * lx)
                pts = [P(0, -h / 2), P(w, -h / 2), P(w, h / 2), P(0, h / 2)]
            ax.add_patch(MplPoly(pts, closed=True, fill=False,
                                 edgecolor=col, lw=0.9, alpha=0.9, zorder=15))


def _field_frame(geom: dict, rotor_angle: float, N: int = 120,
                 iq: float = 0.0, id_: float = 0.0,
                 rpm: float = 0.0, vmax_clip: float | None = None,
                 sf_ref: float | None = None, out_px: int | None = None,
                 saturate: bool = False, b_ceiling: float | None = None,
                 magnet_outlines: bool = False) -> str:
    # b_ceiling overrides the physical display clip + colour-scale ceiling so the
    # user can widen/narrow the |B| scale (field_bmax). Falls back to the steel-
    # saturation default when not set.
    ceil = float(b_ceiling) if (b_ceiling and b_ceiling > 0) else IRON_B_SAT_DISPLAY
    em = ema_analysis.run_em_analysis(geom, N=N, rotor_angle=rotor_angle,
                                       iq=iq, id_=id_, fdm_iters=120,
                                       sf_ref=sf_ref, saturate=saturate)
    sc, ctr = em["scale"], em["center"]
    B, A    = em["B_mag"], em["A"]

    # out_px (preview) drives a larger, sharper output bitmap (fixed 5.2" figure,
    # higher dpi); the default animation frames keep the compact ~470 px size.
    fig, ax = plt.subplots(figsize=(5.2, 5.2), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    # Clip |B| to the physical iron-saturation ceiling: the linear FDM produces
    # unphysical spikes at the stair-stepped iron/air corners; real steel can't
    # exceed ~2 T (the nonlinear saturate pass enforces this in the solve, this
    # clip also keeps the linear animation frames honest).
    B = np.minimum(B, ceil)

    # Mask everything OUTSIDE the stator OD. The FDM domain is padded with an air
    # margin out to an artificial A=0 (Dirichlet) boundary, so the vector potential
    # A still varies across that outer air ring even though the flux density |B|
    # there is essentially zero — drawing A-contours (field lines) in it gives the
    # misleading impression of lots of flux escaping the stator. Physically the
    # back-iron yoke (µr≈500 ≫ air) confines the flux, so we blank the housing/air
    # region beyond the stator OD: field lines + heatmap are limited to the machine.
    _ny, _nx = B.shape
    _yy, _xx = np.mgrid[0:_ny, 0:_nx]
    _r_mm    = np.hypot(_xx - ctr, _yy - ctr) / sc
    _outside = _r_mm > (geom["statorOD"] / 2.0) * 1.02
    B = np.where(_outside, np.nan, B)
    A = np.where(_outside, np.nan, A)
    vmax = (vmax_clip if (vmax_clip is not None and vmax_clip > 0)
            else (ceil if (b_ceiling and b_ceiling > 0) else _field_vmax(B)))
    # magma (black→purple→pink→white) + a γ=0.5 power norm: the air gap stays dark,
    # the iron spreads across purple→magenta→pink so the individual field steps are
    # visible instead of the whole rotor over-saturating to the pale top of the map.
    im = ax.imshow(B, origin="lower", cmap="magma",
                   norm=PowerNorm(0.5, vmin=0.0, vmax=vmax))

    # Field lines — percentile-spaced so equal flux tubes are shown, not equal A increments.
    # This concentrates more lines in the magnetically active regions (air gap, magnet pockets).
    # 28 levels stays legible at high resolution (50 turned the iron into a cyan mesh).
    # Levels from the INSIDE-the-stator field only (A is NaN outside now); contour
    # treats NaN as masked, so no field lines are drawn in the housing/air ring.
    pcts   = np.linspace(3, 97, 28)
    lvls   = np.unique(np.nanpercentile(A, pcts))
    lvls   = lvls[np.isfinite(lvls)]
    if lvls.size:
        ax.contour(A, levels=lvls, colors="#00e5ff", linewidths=0.5, alpha=0.75)

    # Geometry outlines
    th = np.linspace(0, 2 * math.pi, 360)
    for r_mm, col, lw in [
        (geom["statorOD"] / 2, "white", 0.8),
        (geom["statorID"] / 2, "white", 0.8),
        (geom["rotorOD"]  / 2, "#ccc",  0.7),
        (geom["shaftD"]   / 2, "#888",  0.6),
    ]:
        r_px = r_mm * sc
        ax.plot(ctr + r_px * np.cos(th), ctr + r_px * np.sin(th), col, lw=lw)

    # Magnet outlines (so the magnets are visibly delineated, not just implied by the
    # field). Same placement math as ema_analysis._rasterise; N=red / S=blue.
    if magnet_outlines:
        _draw_magnet_outlines(ax, geom, sc, ctr, rotor_angle)

    # Larger fonts on the high-resolution single-frame previews so the colour-bar
    # label / ticks / legend stay readable; compact on the small animation frames.
    big   = bool(out_px and out_px >= 1200)
    fs_t  = 11 if big else 8       # title
    fs_cb = 10 if big else 7       # colour-bar label
    fs_tk = 9  if big else 6       # colour-bar ticks
    fs_lg = 9  if big else 6       # legend

    # Colour bar — the heatmap encodes the flux-density magnitude |B| in Tesla.
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.02)
    cbar.set_label("Flussdichte |B|  (T)", color="#ddd", fontsize=fs_cb)
    cbar.ax.tick_params(color="#666", labelcolor="#bbb", labelsize=fs_tk)
    cbar.outline.set_edgecolor("#444")
    # Explicit ticks (PowerNorm spaces them non-linearly) up to the display ceiling.
    cb_ticks = np.round(np.linspace(0.0, vmax, 6), 2)
    cbar.set_ticks(cb_ticks)

    # Legend — explains the overlays (what the lines mean), with units in the labels.
    handles = [Line2D([0], [0], color="#00e5ff", lw=0.9,
                      label="Feldlinien (Vektorpot. A)")]
    handles += [Line2D([0], [0], color=c, lw=1.0, label=l) for c, l in
                [("white", "Stator (OD/ID)"), ("#ccc", "Rotor (OD)"), ("#888", "Welle")]]
    leg = ax.legend(handles=handles, loc="lower left", fontsize=fs_lg,
                    framealpha=0.6, facecolor="#0d0d0d", edgecolor="#444",
                    labelcolor="#ddd", borderpad=0.5, handlelength=1.4)
    leg.set_zorder(20)

    title_parts = [f"Magnetfeld  |  θ = {math.degrees(rotor_angle):.1f}°"]
    if rpm > 0:
        title_parts.append(f"{rpm:,.0f} U/min".replace(",", "."))
        title_parts.append(f"i_q={iq:.0f} i_d={id_:.0f} A")
    ax.set_title("  |  ".join(title_parts), color="#bbb", fontsize=fs_t, pad=3)
    ax.axis("off")
    fig.tight_layout(pad=0.1)
    dpi = max(90, int(out_px / 5.2)) if out_px else 90
    return _fig_b64(fig, dpi=dpi)


PREVIEW_N_MAX_DIRECT = 2500   # direct splu ceiling on a ~32 GB host (~15 GB peak)
PREVIEW_N_MAX_AMG    = 6000   # pyamg AMG ceiling (~5–6 GB at 5000, ~8–9 GB at 6000)


def render_preview_frame(data: dict) -> dict:
    """Render exactly ONE field frame for a quick visual preview.

    No FreeCAD, no FEM, no animation — just the field setup of `run_pipeline`
    (magnet remanence/permeability override, open-circuit calibration, dq-current
    estimate) followed by a single FDM solve + render.  Useful to check geometry
    and the colour scale without a full multi-minute run.  Honours optional
    `rotor_angle_deg`, `rpm` and `load_nm` in `data`; resolution comes from
    `frame_resolution` (falls back to `fdm_resolution`).  Returns a dict with the
    base64 PNG plus the operating point used.

    Up to N≈2500 the exact direct factorisation is used (~M^1.1 memory: N=2000 ≈
    9 GB). Beyond that — if pyamg is installed — the CG-accelerated AMG branch
    takes over (~5–6 GB at 5000), so the grid is capped at `PREVIEW_N_MAX_AMG`;
    without pyamg the cap is `PREVIEW_N_MAX_DIRECT` to avoid OOM-ing the host.
    """
    geom    = data["geom"]
    mag     = MAGNETS.get(data.get("magnet", "ndfeb_n35"), MAGNETS["ndfeb_n35"])
    N       = int(data.get("frame_resolution", data.get("fdm_resolution", 200)))
    n_max   = PREVIEW_N_MAX_AMG if ema_analysis._HAVE_PYAMG else PREVIEW_N_MAX_DIRECT
    if N > n_max:
        if ema_analysis._HAVE_PYAMG:
            raise ValueError(
                f"Auflösung {N} px übersteigt das Limit ({n_max} px) des "
                f"Multigrid-Solvers auf dieser Maschine.")
        raise ValueError(
            f"Auflösung {N} px übersteigt das Limit des direkten Solvers "
            f"({n_max} px ≈ 15 GB RAM). Für höhere Auflösungen pyamg installieren "
            f"(pip install pyamg) — dann ist der Multigrid-Solver bis "
            f"{PREVIEW_N_MAX_AMG} px verfügbar.")
    rpm     = float(data.get("rpm", data.get("rpm_from", 5000.0)))
    load_nm = float(data.get("load_nm", 5.0))
    ang     = math.radians(float(data.get("rotor_angle_deg", 0.0)))

    _orig_Br, _orig_mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    ema_analysis.Br_NdFeB = mag["Br"]
    ema_analysis.MU_R_MAG = mag["mu_r"]
    try:
        # B_gap (for the dq-current estimate) only needs a coarse grid — keep the
        # expensive high-N factorisation for the single displayed frame.
        em0   = ema_analysis.run_em_analysis(geom, N=min(N, 250), rotor_angle=0.0)
        b_gap = em0["performance"]["B_gap_T"]
        iq, id_ = ema_analysis.estimate_dq_currents(
            geom, rpm, load_nm, b_gap_t=b_gap, rpm_base=rpm)
        # No sf_ref needed: run_em_analysis now calibrates the magnet and stator
        # fields separately (magnet → analytical B_gap, armature → analytical
        # B_arm), so both are physically scaled here and the magnets stay visible
        # under load. Output a large, sharp bitmap sized to the grid (1000–5000 px).
        out_px = int(min(5000, max(1000, N)))
        # Single high-res frame → run the nonlinear B-H saturation pass so the iron
        # shows physical (saturated, flux-redistributed) |B|, not linear >2 T spikes.
        b_ceiling = float(data.get("field_bmax", 0) or 0)
        png = _field_frame(geom, ang, N=N, iq=iq, id_=id_, rpm=rpm, out_px=out_px,
                           saturate=True, b_ceiling=b_ceiling, magnet_outlines=True)
        return {"png_b64": png, "B_gap_T": round(b_gap, 4),
                "iq": round(iq, 1), "id": round(id_, 1), "rpm": rpm, "N": N,
                "out_px": out_px, "rotor_angle_deg": round(math.degrees(ang), 1)}
    finally:
        ema_analysis.Br_NdFeB = _orig_Br
        ema_analysis.MU_R_MAG = _orig_mu
        ema_analysis.clear_lu_cache()


# ── Matplotlib charts ─────────────────────────────────────────────────────────

def _airgap_chart(em: dict) -> str:
    fig, ax = plt.subplots(figsize=(7, 2.8), facecolor="#111")
    ax.set_facecolor("#1a1a2e")
    th = np.degrees(em["theta"])
    Br = np.asarray(em["Br_gap"], dtype=float)
    Bt = np.asarray(em["Bt_gap"], dtype=float)
    # Br (radial) is the working air-gap flux density — robustly extracted via the
    # tangential derivative of A and calibrated to the analytical peak, so it is the
    # primary curve.  Bt (tangential) is a finite-difference across a gap that is at
    # best a few cells on the Cartesian grid; for some geometries it is only an
    # approximation, so it is shown secondary (dashed) and clipped to the physical
    # envelope |Bt| ≤ peak|Br| so a numerical spike can never spuriously dominate Br
    # (the air-gap tangential field cannot exceed the radial working flux there).
    pk = float(np.max(np.abs(Br))) if Br.size else 1.0
    Bt_disp = np.clip(Bt, -pk, pk)
    ax.plot(th, Br, color="#00d4ff", lw=2.0, label="B_r (radial)")
    ax.plot(th, Bt_disp, color="#ff7043", lw=1.0, ls="--", alpha=0.7,
            label="B_t (tangential, Näherung)")
    ax.axhline(0, color="#555", lw=0.5)
    ax.set_xlabel("Winkel [°]", color="#aaa", fontsize=9)
    ax.set_ylabel("B [T]",      color="#aaa", fontsize=9)
    ax.set_title("Luftspaltflussdichte B_r (offen, Rotorwinkel 0°)", color="white", fontsize=9)
    ax.tick_params(colors="#888", labelsize=8)
    for sp in ax.spines.values(): sp.set_color("#444")
    ax.legend(facecolor="#222", labelcolor="white", fontsize=8, framealpha=0.8)
    fig.tight_layout()
    return _fig_b64(fig)


def _em_sweep_chart(sweep: list) -> str:
    rpms = [s["rpm"]         for s in sweep]
    emfs = [s["emf_rms_V"]   for s in sweep]
    Kts  = [s["Kt_Nm_per_A"] for s in sweep]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3), facecolor="#111")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#888", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")
        ax.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=8)

    ax1.plot(rpms, emfs, color="#00d4ff", lw=2, marker="o", markersize=4)
    ax1.set_title("Strangspannung EMK (1 Wdg/Nut)", color="white", fontsize=9)
    ax1.set_ylabel("U_rms [V]", color="#aaa", fontsize=8)

    ax2.plot(rpms, Kts, color="#4caf50", lw=2, marker="o", markersize=4)
    ax2.set_title("Drehmomentkonstante Kt", color="white", fontsize=9)
    ax2.set_ylabel("Kt [Nm/A_pk]", color="#aaa", fontsize=8)

    fig.tight_layout()
    return _fig_b64(fig)


def _power_chart(env: dict) -> str:
    """Torque + power over speed (peak / continuous) — the capability envelope.

    Both curves share one x-axis with twin y-axes, because the two facts a reader
    wants are "how much torque up to which speed" and "where does the power peak",
    and separating them into two panels breaks the visual link at the base speed.
    """
    rpm  = np.asarray(env["rpm"], float)
    T_pk = np.asarray(env["T_peak_Nm"], float)
    T_co = np.asarray(env["T_cont_Nm"], float)
    P_pk = np.asarray(env["P_peak_kW"], float)
    P_co = np.asarray(env["P_cont_kW"], float)

    fig, ax = plt.subplots(figsize=(9, 3.6), facecolor="#111")
    ax.set_facecolor("#1a1a2e")
    ax.tick_params(colors="#888", labelsize=8)
    for sp in ax.spines.values(): sp.set_color("#444")
    ax.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=8)
    ax.set_ylabel("Drehmoment [Nm]", color="#ff9f43", fontsize=8)
    ax.plot(rpm, T_pk, color="#ff9f43", lw=2, label="M Spitze")
    if not np.allclose(T_co, T_pk):
        ax.plot(rpm, T_co, color="#ff9f43", lw=1.4, ls="--", label="M Dauer (Kühlung)")
    ax.tick_params(axis="y", colors="#ff9f43")

    ax2 = ax.twinx()
    ax2.set_facecolor("none")
    ax2.set_ylabel("Leistung [kW]", color="#00d4ff", fontsize=8)
    ax2.tick_params(axis="y", colors="#00d4ff", labelsize=8)
    for sp in ax2.spines.values(): sp.set_color("#444")
    ax2.plot(rpm, P_pk, color="#00d4ff", lw=2, label="P Spitze")
    if not np.allclose(P_co, P_pk):
        ax2.plot(rpm, P_co, color="#00d4ff", lw=1.4, ls="--", label="P Dauer")

    ax2.plot([env["P_max_rpm"]], [env["P_max_kW"]], "o", color="#00d4ff", ms=6)
    ax2.annotate(f"{env['P_max_kW']:.0f} kW @ {env['P_max_rpm']:.0f} 1/min",
                 (env["P_max_rpm"], env["P_max_kW"]), textcoords="offset points",
                 xytext=(6, 8), color="#00d4ff", fontsize=8)
    ax.axvline(env["rpm_base"], color="#666", ls=":", lw=1)
    ax.annotate(f"Eckdrehzahl {env['rpm_base']:.0f}", (env["rpm_base"], 0.06),
                xycoords=("data", "axes fraction"), textcoords="offset points",
                xytext=(4, 0), color="#888", fontsize=7)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    leg = ax.legend(h1 + h2, l1 + l2, loc="lower center", ncol=4, fontsize=7,
                    facecolor="#1a1a2e", edgecolor="#444")
    for t in leg.get_texts(): t.set_color("#ccc")
    ax.set_title(f"Drehmoment-/Leistungskennfeld  (Grenzen {env['v_dc_V']:.0f} V, "
                 f"{env['i_max_A']:.0f} A, 1 Wdg/Nut, ungesättigt)",
                 color="white", fontsize=9)
    fig.tight_layout()
    return _fig_b64(fig)


def _drivecycle_chart(cyc: dict, drv: dict, res: dict) -> str:
    """4-panel chart: v(t), motor operating points, cumulative energy, loss split."""
    import matplotlib.gridspec as gs
    t        = np.asarray(cyc["t"])
    v        = np.asarray(cyc["v_kmh"])
    rpm      = np.asarray(drv["rpm_motor"])
    T_arr    = np.asarray(drv["T_motor"])

    fig = plt.figure(figsize=(14, 8), facecolor="#111")
    g = gs.GridSpec(2, 2, figure=fig, hspace=0.32, wspace=0.22)
    ax_v   = fig.add_subplot(g[0, 0])
    ax_map = fig.add_subplot(g[0, 1])
    ax_E   = fig.add_subplot(g[1, 0])
    ax_L   = fig.add_subplot(g[1, 1])
    for ax in (ax_v, ax_map, ax_E, ax_L):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#aaa", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")

    # 1. Speed profile
    ax_v.plot(t / 60, v, color="#00d4ff", lw=1.0)
    # Phase markers
    cum = 0
    for ph in cyc.get("phases", []):
        ax_v.axvline(ph["t_end"] / 60, color="#555", lw=0.5, ls=":")
        ax_v.text(((cum + ph["t_end"]) / 2) / 60, v.max() * 0.95,
                  ph["name"], color="#888", fontsize=7, ha="center")
        cum = ph["t_end"]
    ax_v.set_xlabel("Zeit [min]", color="#aaa", fontsize=9)
    ax_v.set_ylabel("v [km/h]",   color="#aaa", fontsize=9)
    ax_v.set_title(f"{cyc['name']}  ·  v_max={res['v_max_kmh']:.0f}  v_⌀={res['v_avg_kmh']:.0f} km/h",
                   color="white", fontsize=10)
    ax_v.grid(color="#333", lw=0.4)

    # 2. Operating-point cloud (rpm × T)
    P_loss = np.asarray(res["op_points"]["P_loss"])
    rpm_sub = np.asarray(res["op_points"]["rpm"])
    T_sub   = np.asarray(res["op_points"]["T"])
    sc = ax_map.scatter(rpm_sub, T_sub, c=P_loss, cmap="plasma",
                        s=6, alpha=0.75,
                        vmin=0, vmax=max(1, float(np.percentile(P_loss, 95))))
    ax_map.axhline(0, color="#666", lw=0.6)
    ax_map.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=9)
    ax_map.set_ylabel("Drehmoment [Nm]",  color="#aaa", fontsize=9)
    ax_map.set_title("Betriebspunkte (Farbe = momentane Verluste)",
                     color="white", fontsize=10)
    cb = fig.colorbar(sc, ax=ax_map, pad=0.02, fraction=0.04)
    cb.set_label("P_loss [W]", color="#aaa", fontsize=8)
    cb.ax.tick_params(colors="#aaa", labelsize=7)

    # 3. Cumulative electric energy
    # P_elec = mech + losses (sign aware) — reconstruct quickly
    P_mech = T_arr * (rpm * 2 * math.pi / 60)
    # Recompute loss series at sub-sample resolution
    cum_elec = np.cumsum(np.where(P_mech > 0, P_mech, P_mech * 0.55)) * (t[1] - t[0]) / 3600
    cum_loss = np.linspace(0, res["losses"]["E_total_Wh"], len(t))
    ax_E.fill_between(t/60, 0, cum_elec, color="#00d4ff", alpha=0.5, label="Mech. Energie")
    ax_E.fill_between(t/60, cum_elec, cum_elec + cum_loss, color="#ff6b35",
                       alpha=0.7, label="Verluste")
    ax_E.set_xlabel("Zeit [min]", color="#aaa", fontsize=9)
    ax_E.set_ylabel("kumul. Energie [Wh]", color="#aaa", fontsize=9)
    ax_E.set_title(f"Energie-Aufbau  ·  {res['E_per_100km_kWh']:.1f} kWh/100 km",
                   color="white", fontsize=10)
    ax_E.legend(facecolor="#222", labelcolor="white", fontsize=8, framealpha=0.85, loc="upper left")
    ax_E.grid(color="#333", lw=0.4)

    # 4. Loss-budget pie
    L = res["losses"]
    sizes  = [L["E_Cu_Wh"], L["E_Fe_Wh"], L["E_Mag_Wh"], L["E_Bear_Wh"]]
    labels = ["Cu (i²R)", "Eisen", "Magnet Eddy", "Lager/Reibung"]
    colors = ["#ff6b35", "#3498db", "#e74c3c", "#95a5a6"]
    sizes_safe = [max(0.001, s) for s in sizes]
    ax_L.pie(sizes_safe, labels=labels, colors=colors, autopct="%1.0f%%",
              textprops={"color": "white", "fontsize": 9})
    ax_L.set_title(f"Verluste über Zyklus  ·  ⌀ η = {res['eta_drive']*100:.1f} %",
                   color="white", fontsize=10)

    fig.suptitle(f"Fahrzyklus-Analyse  ·  {res['distance_km']:.1f} km  ·  "
                 f"E_netto = {res['E_elec_net_Wh']:.0f} Wh  ·  Regen = {res['E_regen_Wh']:.0f} Wh",
                 color="white", fontsize=11, y=0.995)
    return _fig_b64(fig)


def _thermal_chart(therm: dict) -> str:
    """Two-panel chart: steady-state bar + transient heat-up curves."""
    steady = therm["steady"]
    trans  = therm["transient"]
    nodes  = ["Wicklung", "Stator-Fe", "Rotor-Fe", "Magnet", "Welle", "Gehäuse"]
    T_ss   = [steady["T_winding"], steady["T_stator"], steady["T_rotor"],
              steady["T_magnet"],  steady["T_shaft"],  steady["T_housing"]]
    colors = ["#ff6b35", "#3498db", "#9b59b6", "#e74c3c", "#95a5a6", "#1abc9c"]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 4.5), facecolor="#111",
                                    gridspec_kw={"width_ratios": [1, 1.6]})
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#aaa", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")

    # Steady-state bar
    bars = ax1.bar(nodes, T_ss, color=colors, edgecolor="#222", lw=0.8)
    ax1.axhline(steady["T_ambient"], color="#666", lw=0.8, ls="--",
                label=f"T_amb = {steady['T_ambient']}°C")
    ax1.axhline(150, color="#f39c12", lw=0.8, ls=":", label="Magnet-Limit 150°C")
    ax1.axhline(180, color="#e74c3c", lw=0.8, ls=":", label="Klasse-H 180°C")
    ax1.set_ylabel("T [°C]", color="#aaa", fontsize=9)
    ax1.set_title(f"Endtemperaturen ({steady['cooling']})",
                  color="white", fontsize=10)
    ax1.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.85, loc="upper left")
    for b, T in zip(bars, T_ss):
        ax1.text(b.get_x() + b.get_width()/2, T + 5, f"{T:.0f}",
                 ha="center", color="white", fontsize=8)
    ax1.set_ylim(0, max(220, max(T_ss) * 1.15))
    plt.setp(ax1.get_xticklabels(), rotation=35, ha="right")

    # Transient curves
    t_min = np.array(trans["t"]) / 60
    for key, lbl, col in zip(["T_winding","T_stator","T_rotor","T_magnet","T_shaft","T_housing"],
                              nodes, colors):
        ax2.plot(t_min, trans[key], color=col, lw=1.8, label=lbl)
    ax2.axhline(180, color="#e74c3c", lw=0.6, ls=":", alpha=0.6)
    ax2.axhline(150, color="#f39c12", lw=0.6, ls=":", alpha=0.6)
    ax2.set_xlabel("Zeit [min]", color="#aaa", fontsize=9)
    ax2.set_ylabel("T [°C]",    color="#aaa", fontsize=9)
    ax2.set_title("Aufheizverlauf (Stufenlast bis Endwert)",
                  color="white", fontsize=10)
    ax2.legend(facecolor="#222", labelcolor="white", fontsize=7,
               framealpha=0.85, ncol=2, loc="lower right")

    fig.tight_layout()
    return _fig_b64(fig)


def _struct_sweep_chart(sweep_fem: dict | None, sweep_analytical: list, yield_mpa: float) -> str:
    rpms = [s["rpm"]          for s in sweep_analytical]
    sigs = [s["sigma_max_MPa"] for s in sweep_analytical]
    sfs  = [s["safety_factor"] for s in sweep_analytical]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 3), facecolor="#111")
    for ax in (ax1, ax2):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#888", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")
        ax.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=8)

    ax1.plot(rpms, sigs, color="#ff7043", lw=2, marker="o", markersize=4, label="Analytisch")
    ax1.axhline(yield_mpa, color="#f44336", lw=1.2, ls="--", label=f"Re = {yield_mpa} MPa")
    if sweep_fem and sweep_fem.get("max_von_mises_MPa"):
        ax1.scatter([sweep_fem["rpm"]], [sweep_fem["max_von_mises_MPa"]],
                    color="#00d4ff", zorder=5, s=60, label="CalculiX FEM")
    ax1.set_title("Vergleichsspannung σ_v,max", color="white", fontsize=9)
    ax1.set_ylabel("σ [MPa]", color="#aaa", fontsize=8)
    ax1.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.8)

    ax2.plot(rpms, sfs, color="#4caf50", lw=2, marker="o", markersize=4)
    ax2.axhline(2.0, color="#4caf50", lw=1, ls="--", alpha=0.5, label="SF = 2.0")
    ax2.axhline(1.0, color="#f44336", lw=1, ls="--", alpha=0.7, label="SF = 1.0")
    ax2.set_title("Sicherheitsfaktor", color="white", fontsize=9)
    ax2.set_ylabel("SF [-]", color="#aaa", fontsize=8)
    ax2.set_ylim(0, min(max(sfs) * 1.1, 20))
    ax2.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.8)

    fig.tight_layout()
    return _fig_b64(fig)


# ── CAD cross-section images ──────────────────────────────────────────────────

def _schnittmasse(geom: dict) -> dict:
    """Abgeleitete Querschnittsmasse — eine Quelle fuer Quer- UND Axialschnitt.

    Beide Bilder rechneten dieselben zwoelf Groessen frueher jedes fuer sich aus. Seit
    ``render_cross_section`` eigenstaendig ist (der Bilddatensatz zeichnet damit ohne
    Beschriftung), waeren es drei Stellen gewesen, die auseinanderlaufen koennen.
    """
    R_si     = geom["statorID"] / 2
    n_slots  = int(geom["slots"])
    slot_dep = float(geom["slotDepth"])
    dtheta_s = 2 * math.pi / n_slots
    slot_w   = max(3.0, R_si * dtheta_s * float(geom.get("slotWidthRatio", 0.5)))
    ins, n_layers = 0.8, 2
    return {"R_rot": geom["rotorOD"] / 2, "R_shaft": geom["shaftD"] / 2,
            "R_bore": float(geom.get("shaftBoreD", 0)) / 2,   # hollow shaft (0 = solid)
            "R_si": R_si, "R_so": geom["statorOD"] / 2,
            "n_poles": int(geom["p"]) * 2, "n_slots": n_slots,
            "slot_dep": slot_dep, "dtheta_s": dtheta_s, "slot_w": slot_w,
            "ins": ins, "n_layers": n_layers,
            "cond_w": max(1.5, slot_w - 2 * ins),
            "layer_h": max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)}


def render_cross_section(geom: dict, ax, *, beschriftung: bool = True) -> None:
    """Den XY-Querschnitt auf eine **vorhandene** Achse zeichnen.

    Herausgeloest aus ``_save_cad_images``, weil der Bilddatensatz
    (``ema_bilddaten``) genau dieses Bild braucht — und zwar ohne Titel, Masszeile
    und Legende: ein Bewertungsbild, das die Hauptmasse danebenschreibt, laesst den
    Betrachter Zahlen ablesen statt Gestalt sehen.

    Zeichnet ausschliesslich — speichert nichts, schliesst keine Figur.
    """
    import math as _m
    import numpy as np
    from matplotlib.patches import Wedge, Circle
    from matplotlib.patches import Polygon as MplPoly, Patch
    from ema_topology import magnet_legs, leg_center

    m = _schnittmasse(geom)
    R_rot, R_shaft, R_bore = m["R_rot"], m["R_shaft"], m["R_bore"]
    R_si, R_so       = m["R_si"], m["R_so"]
    n_poles, n_slots = m["n_poles"], m["n_slots"]
    slot_dep, dtheta_s, slot_w = m["slot_dep"], m["dtheta_s"], m["slot_w"]
    ins, n_layers    = m["ins"], m["n_layers"]
    cond_w, layer_h  = m["cond_w"], m["layer_h"]
    legs, _meta = magnet_legs(geom)                          # single source of truth

    def rot2d(pts, a):
        c, s = _m.cos(a), _m.sin(a)
        return [(x*c - y*s, x*s + y*c) for x, y in pts]

    def annulus(ax_, r_in, r_out, fc, ec='none', lw=0.5, alpha=1.0, n=360):
        th = np.linspace(0, 2*_m.pi, n)
        ox, oy = r_out*np.cos(th), r_out*np.sin(th)
        ix, iy = r_in*np.cos(th[::-1]), r_in*np.sin(th[::-1])
        verts = np.column_stack([np.hstack([ox, ix]), np.hstack([oy, iy])])
        ax_.add_patch(MplPoly(verts, closed=True, fc=fc, ec=ec, lw=lw, alpha=alpha))

    # ── cross-section (XY) ────────────────────────────────────────────────────
    ax.figure.patch.set_facecolor('#0d1117'); ax.set_facecolor('#0d1117')
    ax.set_aspect('equal'); ax.axis('off')
    lim = R_so * 1.15; ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)

    annulus(ax, R_bore, R_shaft, '#555555', ec='#888888', lw=1.2)
    if R_bore > 0:                                  # hollow shaft bore (air)
        ax.add_patch(Circle((0, 0), R_bore, fc='#0d1117', ec='#888888', lw=0.9))
    annulus(ax, R_shaft, R_rot, '#2d3748', ec='#4a5568', lw=0.8)
    # Shaft–core connection profile outline (spline teeth / polygon lobes) so the
    # joint is visible in the 2D section too (plain circle for a press fit).
    _conn = str(geom.get("shaftConnection", "press"))
    if _conn == "spline":
        z = int(geom.get("splineTeeth", 10)); dep = float(geom.get("splineToothDepthMm", 2.0))
        tw = max(1.5, 2 * math.pi * R_shaft / z * 0.5)
        for i in range(z):
            a = 2 * math.pi * i / z
            local = [(R_shaft - 0.5, -tw / 2), (R_shaft + dep, -tw / 2),
                     (R_shaft + dep, tw / 2), (R_shaft - 0.5, tw / 2)]
            tooth = [(x * math.cos(a) - y * math.sin(a), x * math.sin(a) + y * math.cos(a))
                     for x, y in local]
            ax.add_patch(MplPoly(tooth, closed=True, fc='#555555', ec='#888888', lw=0.6))
    elif _conn == "polygon":
        lobes = int(geom.get("polygonLobes", 3)); ecc = float(geom.get("polygonEccMm", 2.0))
        th = np.linspace(0, 2 * math.pi, 240)
        rr = R_shaft + ecc * np.cos(lobes * th)
        ax.plot(rr * np.cos(th), rr * np.sin(th), color='#aab', lw=1.0)
    # Balance-disc bolt holes (optional): symmetric circle, count = pole number.
    if bool(geom.get("genBalanceBolts", False)):
        _thr_d = {"M4": 4.0, "M5": 5.0, "M6": 6.0, "M8": 8.0, "M10": 10.0,
                  "M12": 12.0, "M16": 16.0, "M20": 20.0}
        _bnom = _thr_d.get(str(geom.get("balanceBoltThread", "M6")).upper(), 6.0)
        _bhr  = (_bnom + 0.4) / 2.0
        _bcd  = float(geom.get("balanceBoltCircleD", 0) or 0)
        _bpcr = _bcd / 2.0 if _bcd > 0 else R_shaft + (R_rot - R_shaft) * 0.5
        _boff = _m.radians(float(geom.get("balanceBoltOffsetDeg", 0)))
        _nb   = max(2, n_poles)
        for i in range(_nb):
            a = _boff + i * 2 * _m.pi / _nb
            ax.add_patch(Circle((_bpcr * _m.cos(a), _bpcr * _m.sin(a)), _bhr,
                                fc='#0d1117', ec='#9aa', lw=0.7))

    # Flux-barrier radial slots (optional): q-axis between poles, d-axis pole centre.
    if bool(geom.get("genFluxBarrierQ", False)) or bool(geom.get("genFluxBarrierD", False)):
        _fbw  = max(0.5, min(40.0, float(geom.get("fluxBarrierWidth", 3.0))))
        _fbd  = max(1.0, min(120.0, float(geom.get("fluxBarrierDepth", 10.0))))
        _rout = R_rot - 2.0
        _rin  = max(R_shaft + 1.0, _rout - _fbd)
        _fangs = []
        if bool(geom.get("genFluxBarrierD", False)):
            _fangs += [i * 2 * _m.pi / n_poles for i in range(n_poles)]
        if bool(geom.get("genFluxBarrierQ", False)):
            _fangs += [(i + 0.5) * 2 * _m.pi / n_poles for i in range(n_poles)]
        for a in _fangs:
            loc = [(_rin, -_fbw / 2), (_rout, -_fbw / 2), (_rout, _fbw / 2), (_rin, _fbw / 2)]
            poly = [(x * _m.cos(a) - y * _m.sin(a), x * _m.sin(a) + y * _m.cos(a))
                    for x, y in loc]
            ax.add_patch(MplPoly(poly, closed=True, fc='#0d1117', ec='#9aa', lw=0.7))

    # Custom (designer) barriers: thick polylines per pole.
    _cbars = geom.get("customBarriers") or []
    if _cbars:
        for p_i in range(n_poles):
            pa = p_i * 2 * _m.pi / n_poles
            ca, sa = _m.cos(pa), _m.sin(pa)
            for bar in _cbars:
                pts = bar.get("pts") or []
                hw  = max(0.5, float(bar.get("width", 3.0))) / 2.0
                gp  = [(x * ca - y * sa, x * sa + y * ca) for x, y in pts]
                xs_ = [p[0] for p in gp]; ys_ = [p[1] for p in gp]
                ax.plot(xs_, ys_, color='#9aa', lw=1.5, solid_capstyle='round',
                        solid_joinstyle='round')

    annulus(ax, R_si, R_so,  '#1e3a5f', ec='#2e5f8a', lw=0.8)
    ax.add_patch(Circle((0, 0), R_si, fill=False, ec='#333', lw=0.4, ls='--'))

    ph_colors = ['#e67e22', '#27ae60', '#3498db']
    for s in range(n_slots):
        ang = s * dtheta_s
        ha  = _m.atan2(slot_w / 2, R_si)
        ax.add_patch(Wedge((0,0), R_si+slot_dep, _m.degrees(ang-ha), _m.degrees(ang+ha),
                           width=slot_dep, fc='#0d1117', ec='none'))
        hc = _m.atan2(cond_w / 2, R_si)
        c1, c2 = _m.degrees(ang-hc), _m.degrees(ang+hc)
        for layer in range(n_layers):
            r0 = R_si + ins + layer * (layer_h + ins)
            ax.add_patch(Wedge((0,0), r0+layer_h, c1, c2, width=layer_h,
                               fc=ph_colors[s % 3], ec='none', alpha=0.85))

    # Clip magnets to rotor OD — prevents geometry extending into air gap
    _rotor_clip = Circle((0, 0), R_rot, fc='none', ec='none', lw=0)
    ax.add_patch(_rotor_clip)

    for pole in range(n_poles):
        pa = pole * 2 * _m.pi / n_poles
        is_n = (pole % 2 == 0)
        fc = '#c0392b' if is_n else '#2980b9'
        ec = '#ff6b6b' if is_n else '#74b9ff'
        for lg in legs:
            if lg.placement == "surface":
                ca = pa + lg.offset / R_rot
                ha = (lg.length / 2) / R_rot
                # outer band inside the rotor OD: Wedge width goes inward from R_rot
                ax.add_patch(Wedge((0, 0), R_rot,
                                   _m.degrees(ca - ha), _m.degrees(ca + ha),
                                   width=lg.thickness, fc=fc, ec=ec, lw=0.6, alpha=0.95))
                continue
            # Interior: obround pocket (Langloch) = magnet rectangle + 2 air end caps.
            cx_l, cy_l = leg_center(lg)
            c_h, s_h = _m.cos(lg.tilt), _m.sin(lg.tilt)
            hw, hh = lg.length / 2, lg.thickness / 2
            local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            rect = rot2d([(c_h*lx - s_h*ly + cx_l, s_h*lx + c_h*ly + cy_l)
                          for lx, ly in local], pa)
            # air end caps (flux barriers) — interior obround pockets only, not the
            # flat surface-mounted Halbach tiles ("surface_flat").
            if lg.placement == "interior":
                (e0x, e0y) = rot2d([(cx_l - hw*c_h, cy_l - hw*s_h)], pa)[0]
                (e1x, e1y) = rot2d([(cx_l + hw*c_h, cy_l + hw*s_h)], pa)[0]
                for (ex, ey) in [(e0x, e0y), (e1x, e1y)]:
                    cap = Circle((ex, ey), hh, fc='#0d1117', ec='#4a5568', lw=0.6)
                    ax.add_patch(cap); cap.set_clip_path(_rotor_clip)
            # magnet rectangle (fills the straight section)
            mp = MplPoly(rect, closed=True, fc=fc, ec=ec, lw=0.8, alpha=0.95)
            ax.add_patch(mp); mp.set_clip_path(_rotor_clip)

    if beschriftung:
        ax.text(0, lim*0.95, "IPM-Motor — Querschnitt (XY)",
                color='white', fontsize=11, ha='center', va='top', fontweight='bold')
        ax.text(0, -lim*0.96,
                f"D_a={geom['statorOD']:.0f} mm  |  D_i={geom['statorID']:.0f} mm  |  "
                f"D_r={geom['rotorOD']:.0f} mm  |  d_w={geom['shaftD']:.0f} mm  |  "
                f"2p={n_poles}  |  Q={n_slots}",
                color='#888', fontsize=8, ha='center', va='top')
        ax.legend(handles=[
            Patch(fc='#555',    ec='#888',    label='Welle'),
            Patch(fc='#2d3748', ec='#4a5568', label='Rotorblech'),
            Patch(fc='#c0392b', ec='#ff6b6b', label='Magnet N'),
            Patch(fc='#2980b9', ec='#74b9ff', label='Magnet S'),
            Patch(fc='#1e3a5f', ec='#2e5f8a', label='Statorblech'),
            Patch(fc='#e67e22', label='Phase A'), Patch(fc='#27ae60', label='Phase B'),
            Patch(fc='#3498db', label='Phase C'),
        ], loc='upper right', facecolor='#1a1a2e', labelcolor='white',
           fontsize=7.5, framealpha=0.9, ncol=2)


def _save_cad_images(geom: dict, axial: float, out_root: str) -> dict:
    """Render motor cross-section + side view to <out_root>/cad_images/*.png."""
    out_dir = os.path.join(out_root, "cad_images")
    os.makedirs(out_dir, exist_ok=True)

    m = _schnittmasse(geom)
    R_rot, R_shaft, R_bore = m["R_rot"], m["R_shaft"], m["R_bore"]
    R_si, R_so = m["R_si"], m["R_so"]
    ins, n_layers, layer_h = m["ins"], m["n_layers"], m["layer_h"]

    fig, ax = plt.subplots(figsize=(10, 10))
    render_cross_section(geom, ax)
    cross_path = os.path.join(out_dir, "motor_cross_section.png")
    fig.savefig(cross_path, dpi=130, bbox_inches='tight', facecolor='#0d1117')
    plt.close(fig)

    # ── side view (XZ axial cut) ───────────────────────────────────────────────
    fig2, ax2 = plt.subplots(figsize=(13, 5))
    fig2.patch.set_facecolor('#0d1117'); ax2.set_facecolor('#0d1117')
    ax2.set_aspect('equal'); ax2.axis('off')

    end_turn = 18.0; half_ax = axial / 2; total_ax = half_ax + end_turn

    def add_rect(xr, x0, x1, y0, y1, fc, ec='none', lw=0.5, alpha=1.0):
        from matplotlib.patches import Rectangle
        xr.add_patch(Rectangle((min(x0,x1), min(y0,y1)), abs(x1-x0), abs(y1-y0),
                                fc=fc, ec=ec, lw=lw, alpha=alpha))

    add_rect(ax2, -total_ax*1.1, total_ax*1.1, -R_shaft, R_shaft, '#555', ec='#888', lw=0.8)
    if R_bore > 0:                                  # hollow-shaft bore (air channel)
        add_rect(ax2, -total_ax*1.1, total_ax*1.1, -R_bore, R_bore, '#0d1117', ec='#888', lw=0.6)
    for sy in [1, -1]:
        add_rect(ax2, -half_ax, half_ax, sy*R_shaft, sy*R_rot, '#2d3748', ec='#4a5568', lw=0.8)
        add_rect(ax2, -half_ax, half_ax, sy*R_rot, sy*R_si, '#0d1117')
        add_rect(ax2, -half_ax, half_ax, sy*R_si, sy*R_so, '#1e3a5f', ec='#2e5f8a', lw=0.8)
        for layer in range(n_layers):
            r0 = R_si + ins + layer*(layer_h+ins); r1 = r0 + layer_h
            for sign in [+1, -1]:
                add_rect(ax2, -total_ax, -half_ax, sign*r0, sign*r1, '#b87333', ec='#d4a84b', lw=0.5, alpha=0.8)
                add_rect(ax2, half_ax, total_ax,   sign*r0, sign*r1, '#b87333', ec='#d4a84b', lw=0.5, alpha=0.8)

    ax2.axhline(0, color='#444', lw=0.5, ls='--')
    ax2.annotate('', xy=(half_ax, R_so+8), xytext=(-half_ax, R_so+8),
                 arrowprops=dict(arrowstyle='<->', color='#aaa', lw=0.8))
    ax2.text(0, R_so+12, f"Blechpaket  l = {axial:.0f} mm",
             color='#aaa', fontsize=8, ha='center', va='bottom')
    ax2.annotate('', xy=(total_ax*1.12+8, R_so), xytext=(total_ax*1.12+8, 0),
                 arrowprops=dict(arrowstyle='<->', color='#aaa', lw=0.8))
    ax2.text(total_ax*1.12+14, R_so/2, f"D_a/2\n{R_so:.0f} mm",
             color='#aaa', fontsize=7.5, ha='left', va='center')
    ax2.text(0, -R_so*1.15,
             f"IPM-Motor — Axialschnitt  |  Blechpaket {axial:.0f} mm  |  Wicklungsüberhang ~{end_turn:.0f} mm",
             color='#888', fontsize=8, ha='center', va='top')
    ax2.set_xlim(-total_ax*1.35, total_ax*1.45); ax2.set_ylim(-R_so*1.3, R_so*1.35)

    side_path = os.path.join(out_dir, "motor_side_view.png")
    fig2.savefig(side_path, dpi=130, bbox_inches='tight', facecolor='#0d1117')
    plt.close(fig2)

    return {"cross_section": "cad_images/motor_cross_section.png",
            "side_view":     "cad_images/motor_side_view.png"}


# ── Analytical structural sweep ────────────────────────────────────────────────

def _struct_sweep(geom: dict, mat: dict, rpms: list | None = None) -> list:
    """Lamé rotating annular disc + stress concentration at magnet pockets."""
    R   = geom["rotorOD"] / 2 / 1000
    r   = geom["shaftD"]  / 2 / 1000
    rho = mat["density"]
    nu  = mat["nu"]
    Sy  = mat["yield_mpa"]
    Kt  = 1.5   # conservative factor at pocket bridges

    out = []
    for rpm in (rpms or RPM_SWEEP):
        omega = rpm * 2 * math.pi / 60
        # Exact rotating-annulus solution (Lamé) in the CONSERVATIVE plane-strain
        # state — single source of truth ema_rotorcheck._bore_hoop_mpa (verified
        # <0.2 % against independent FEM).  Old /8 + (3+nu)R²+(1+nu)r² form
        # under-estimated by ~2x — fixed.
        sig_bore = _bore_hoop_mpa(r, R, rho, omega, nu / (1.0 - nu))
        sigma    = sig_bore * Kt
        sf       = Sy / sigma if sigma > 1e-3 else 9999
        out.append({"rpm": rpm,
                    "sigma_max_MPa": round(sigma, 2),
                    "safety_factor": round(sf, 2)})
    return out


# ── Shaft–laminated-core connection (analytical, no FEM) ───────────────────────

_SHAFT_E = 210e9; _SHAFT_NU = 0.30; _SHAFT_RHO = 7850.0   # steel shaft defaults
_FIT_MU  = 0.15                                            # friction steel/laminate (press)


def connection_assessment(geom: dict, mat: dict, rpm_max: float,
                          axial: float, cooling: str) -> dict:
    """Assess the rotor-core↔shaft connection analytically (no FEM).

    press   : thick-cylinder shrink fit (Lamé) → joint pressure, transmittable
              torque, and the loosening speed where centrifugal bore expansion
              cancels the interference (p→0).
    spline  : flank pressure / torque capacity (DIN-5480-style, load share φ=0.75).
    polygon : P3G surface pressure / capacity (DIN-32711 form factor).
    Torque reference is the cooling-based rated torque (ema_thermal.rated_torque).
    """
    conn = str(geom.get("shaftConnection", "press"))
    d    = max(geom["shaftD"] / 1000.0, 1e-3)                       # shaft/bore dia [m]
    rf   = d / 2.0
    L    = max(axial / 1000.0, 1e-3)                               # engagement length [m]
    ra   = max(geom["rotorOD"] / 2.0 / 1000.0, rf * 1.2)          # hub outer radius [m]
    ri   = max(float(geom.get("shaftBoreD", 0)) / 2.0 / 1000.0, 0.0)  # shaft inner (hollow)
    Eh   = float(mat["E"]) * 1e6; nuh = float(mat["nu"]); rho_h = float(mat["density"])
    Es, nus, rho_s = _SHAFT_E, _SHAFT_NU, _SHAFT_RHO
    yld  = float(mat.get("yield_mpa", 300)) * 1e6
    T_rated = ema_thermal.rated_torque(geom, axial, cooling)
    res = {"type": conn, "T_rated_Nm": round(T_rated, 1)}

    if conn == "spline":
        z  = int(geom.get("splineTeeth", 10))
        h  = float(geom.get("splineToothDepthMm", 2.0)) / 1000.0
        phi = 0.75                                                 # tooth load share
        p_zul = 0.9 * yld
        T_cap = p_zul * z * h * L * (d / 2.0) * phi
        p_act = (2.0 * T_rated / (z * h * L * d * phi)) if (z * h * L * d * phi) > 0 else 0.0
        util  = p_act / p_zul if p_zul > 0 else 0.0
        res.update({"teeth": z, "p_MPa": round(p_act / 1e6, 1),
                    "p_allow_MPa": round(p_zul / 1e6, 0),
                    "T_capacity_Nm": round(T_cap, 1), "utilization": round(util, 2),
                    "ok": bool(util <= 1.0), "note": "Keilwelle – Flankenpressung"})
    elif conn == "polygon":
        e  = float(geom.get("polygonEccMm", 2.0)) / 1000.0
        p_zul = 0.9 * yld
        gfac  = 0.75 * math.pi * d * e + 0.05 * d ** 2             # DIN 32711 form factor
        T_cap = p_zul * L * gfac
        p_act = (T_rated / (L * gfac)) if (L * gfac) > 0 else 0.0
        util  = p_act / p_zul if p_zul > 0 else 0.0
        res.update({"lobes": int(geom.get("polygonLobes", 3)), "p_MPa": round(p_act / 1e6, 1),
                    "p_allow_MPa": round(p_zul / 1e6, 0),
                    "T_capacity_Nm": round(T_cap, 1), "utilization": round(util, 2),
                    "ok": bool(util <= 1.0), "note": "Polygonprofil P3G – Flächenpressung"})
    else:  # press / shrink fit
        delta = float(geom.get("pressInterferenceUm", 40)) * 1e-6  # diametral interference [m]
        Ch = ((ra ** 2 + rf ** 2) / (ra ** 2 - rf ** 2) + nuh) / Eh
        Cs = (((rf ** 2 + ri ** 2) / (rf ** 2 - ri ** 2) - nus) / Es
              if (rf ** 2 - ri ** 2) > 1e-12 else (1 - nus) / Es)
        p0   = delta / (d * (Ch + Cs)) if (Ch + Cs) > 0 else 0.0   # static joint pressure [Pa]
        T_fit = _FIT_MU * p0 * math.pi * d * L * (d / 2.0)         # transmittable torque [Nm]
        # centrifugal loosening: net bore-vs-shaft radial growth per ω² (rotating disc)
        kh = rf / Eh * (rho_h / 4.0) * ((1 - nuh) * rf ** 2 + (3 + nuh) * ra ** 2)
        ks = rf / Es * (rho_s / 4.0) * ((1 - nus) * rf ** 2)
        k  = max(kh - ks, 1e-30)
        w_loose = math.sqrt((delta / 2.0) / k)
        loosening_rpm = w_loose * 60.0 / (2.0 * math.pi)
        util = T_rated / T_fit if T_fit > 1e-9 else 9.99
        res.update({"interference_um": round(delta * 1e6, 0), "p_MPa": round(p0 / 1e6, 1),
                    "T_capacity_Nm": round(T_fit, 1), "utilization": round(util, 2),
                    "loosening_rpm": round(loosening_rpm),
                    "ok": bool(T_fit >= T_rated and loosening_rpm >= rpm_max),
                    "note": "Querpressverband – Schrumpfsitz"})
    return res


def _connection_chart(res: dict, rpm_max: float) -> str:
    fig, ax = plt.subplots(figsize=(7, 3.0), facecolor="#111")
    ax.set_facecolor("#1a1a2e")
    if res.get("type") == "press" and res.get("loosening_rpm"):
        p0 = res["p_MPa"]; loose = float(res["loosening_rpm"])
        rpm = np.linspace(0, max(rpm_max, loose) * 1.1, 200)
        p   = np.clip(p0 * (1 - (rpm / max(loose, 1)) ** 2), 0, None)
        ax.plot(rpm, p, color="#00d4ff", lw=2, label="Fugendruck p(n)")
        ax.axvline(loose, color="#ff5252", ls="--", lw=1.4, label=f"Lösedrehzahl {loose:,.0f}".replace(",", "."))
        ax.axvline(rpm_max, color="#ffd54f", ls=":", lw=1.4, label=f"max. Drehzahl {rpm_max:,.0f}".replace(",", "."))
        ax.set_xlabel("Drehzahl [U/min]", color="#aaa"); ax.set_ylabel("Fugendruck [MPa]", color="#aaa")
    else:
        T_r = res.get("T_rated_Nm", 0); T_c = res.get("T_capacity_Nm", 0)
        bars = ax.bar(["Nennmoment", "Kapazität"], [T_r, T_c], color=["#ffd54f", "#00d4ff"])
        ax.bar_label(bars, fmt="%.0f", color="#ddd")
        ax.set_ylabel("Drehmoment [Nm]", color="#aaa")
    ax.set_title(res.get("note", "Wellenverbindung"), color="#ddd", fontsize=10)
    ax.tick_params(colors="#888");
    for sp in ax.spines.values(): sp.set_color("#444")
    leg = ax.legend(fontsize=7, facecolor="#1a1a2e", edgecolor="#444", labelcolor="#ccc") if res.get("type") == "press" else None
    fig.tight_layout()
    return _fig_b64(fig)


# ── Geometry-only preview (no EM/FEM/thermal) ───────────────────────────────────

def build_cad_preview(data: dict, state: dict, project_dir: str) -> dict:
    """Build ONLY the FreeCAD geometry (full motor assembly) + STEP + 2D CAD images,
    skipping all numerical analysis. Used by the "CAD-Geometrie ansehen" button so the
    user can inspect / open the model (incl. the per-component build toggles) before
    committing to the full pipeline. Writes ``motor.FCStd`` + ``motor.step`` into
    ``project_dir`` so the existing ``/open_freecad`` and ``/download_step`` routes work.
    """
    os.makedirs(os.path.join(project_dir, "cad_images"), exist_ok=True)
    geom  = data["geom"]
    axial = float(data.get("axial_len", 80.0))

    _gate_rotor_layout(data, state)
    _gate_rotor_stress(data, state)
    _log(state, "⚙ Erzeuge Motorgeometrie in FreeCAD…", 10)
    fcstd = os.path.join(project_dir, "motor.FCStd")
    code  = build_full_motor_script(geom, axial, fcstd)
    res   = run_freecad_script(code, timeout=300)
    if not res.get("cad_success"):
        raise RuntimeError("Geometrie fehlgeschlagen: " + (res.get("stderr", "")[:300]))

    vol_mm3 = res.get("volume", 0)
    step_ok = bool(res.get("step_path") and os.path.exists(res.get("step_path", "")))
    out = {
        "volume_mm3": round(vol_mm3, 0),
        "n_faces":    len(res.get("faces", [])),
        "step":       step_ok,
        "fcstd":      os.path.basename(fcstd),
    }
    _log(state, f"✓ Geometrie: {out['n_faces']} Flächen, {vol_mm3:.0f} mm³"
                + (" · STEP exportiert" if step_ok else ""), 70)

    try:
        out["cad_images"] = _save_cad_images(geom, axial, project_dir)
        _log(state, "✓ CAD-Schnittbilder erzeugt", 95)
    except Exception as _e:
        out["cad_images"] = {}
        _log(state, f"⚠ CAD-Bilder fehlgeschlagen: {_e}", 95)
    _log(state, "✓ CAD-Vorschau fertig — Modell kann in FreeCAD geöffnet werden", 100)
    return out


# ── Main pipeline ─────────────────────────────────────────────────────────────

_THERMAL_TIME_S = 1800  # 30 min — long enough for housing to approach steady

# Bindender Struktur-Sicherheitsbeiwert (Tier-2-Gate). EINE Quelle: der Wert steht
# an zwei weit auseinanderliegenden Stellen im Lauf (FEM-Auswertung und
# Drehzahl-Derating) und wanderte als Literal auch in gespeicherte results.json —
# eine getrennt gepflegte Kopie wäre still auseinandergelaufen.
SF_TARGET = 1.3


def _struktur_eigener_satz(geom: dict, mat: dict, rpm: float, proj: str,
                           solver: str, mesh_mm: float, state: dict) -> dict:
    """Rotor-Festigkeit ueber ``ema_deck`` statt ueber FreeCAD — und wahlweise mit Z88.

    Gibt einen Ergebnisblock in DERSELBEN Form zurueck wie der FreeCAD-Pfad, damit das
    Tier-2-Tor darunter unveraendert weiterlaeuft:
    ``max_von_mises_MPa`` (Rohmaximum) und ``notch_peak_MPa`` (P99, der kerbtolerante
    Wert, auf den das Tor stellt).

    Der Polsektor bleibt CalculiX vorbehalten — Z88 kennt weder zyklische Symmetrie
    noch schiefe Symmetrieebenen. Bei ``z88`` und ``beide`` wird deshalb der volle
    Rotor vernetzt, und dann rechnen beide Loeser bitgleich dasselbe Netz.
    """
    import ema_deck as _deck

    sektor = (solver == "ccx")
    netz = _deck.baue(geom, mesh_mm=mesh_mm, ordnung=1, sektoren=1 if sektor else 0)
    _log(state, f"   Netz: {netz.n_knoten:,} Knoten / {netz.n_elemente:,} Tet4, "
                f"{'ein Polsektor' if sektor else 'voller Rotor'}", 79)

    arbeit = os.path.join(proj, "eigener_satz")
    os.makedirs(arbeit, exist_ok=True)
    aus: dict = {"solver_status": "OK", "rechensatz": "eigen", "rpm": rpm,
                 "netz_knoten": netz.n_knoten, "netz_elemente": netz.n_elemente,
                 "netz_sektor": bool(sektor), "struct_mesh_mm": mesh_mm}

    k_ccx = k_z88 = None
    if solver in ("ccx", "beide"):
        pfad = _deck.schreibe_inp(netz, mat, rpm, os.path.join(arbeit, "rotor.inp"))
        r = _deck.loese_ccx(pfad)
        if r["solver_status"] != "OK":
            return {"solver_status": "FAILED", "rechensatz": "eigen", "rpm": rpm,
                    "log": str(r.get("meldung", ""))[:1500]}
        k_ccx = _deck.kennzahlen(netz, _deck.lies_dat_spannungen(r["dat"]),
                                 mat["yield_mpa"])

    if solver in ("z88", "beide"):
        import ema_z88 as _z88
        ok, warum = _z88.verfuegbar()
        if not ok:
            _log(state, f"⚠ Z88 nicht einsatzbereit ({warum}) — nur CalculiX", 79)
        else:
            zp = os.path.join(arbeit, "z88")
            _z88.schreibe_satz(netz, mat, rpm, zp)
            rz = _z88.loese(zp, netz=netz)
            if rz["solver_status"] == "OK":
                k_z88 = _z88.kennzahlen_aus_lauf(netz, zp, mat["yield_mpa"])
                k_z88["solver"] = rz["solver"]
            else:
                _log(state, f"⚠ Z88 ohne Ergebnis: {rz.get('meldung', '')}", 79)

    fuehrend = k_ccx or k_z88
    if not fuehrend:
        return {"solver_status": "FAILED", "rechensatz": "eigen", "rpm": rpm,
                "log": "kein Loeser hat Spannungen geliefert"}

    aus.update({"max_von_mises_MPa": fuehrend["stress_peak_MPa"],
                "notch_peak_MPa": fuehrend["stress_p99_MPa"],
                "mean_von_mises_MPa": fuehrend["stress_mean_MPa"],
                "bore_hoop_median_MPa": fuehrend.get("bore_hoop_median_MPa"),
                "node_count": netz.n_knoten,
                "solver_verwendet": "CalculiX" if k_ccx else "Z88"})
    if fuehrend.get("max_displacement_um") is not None:
        aus["max_displacement_um"] = fuehrend["max_displacement_um"]
        aus["max_displacement_mm"] = fuehrend.get("max_displacement_mm")

    if k_ccx and k_z88:
        vergleich = {"calculix": k_ccx, "z88": k_z88}
        for schl in ("stress_peak_MPa", "stress_p99_MPa", "bore_hoop_median_MPa"):
            a, b = k_ccx.get(schl), k_z88.get(schl)
            if a and b:
                vergleich[f"abweichung_{schl}_pct"] = round(100 * abs(a - b) / abs(a), 3)
        vergleich["hinweis"] = ("Gleiches Netz, gleiche Last, zwei unabhaengige Loeser. "
                                "Das prueft Loeser und Rechensatz — NICHT das Netz und "
                                "nicht das Modell.")
        aus["loeservergleich"] = vergleich
        schlimmste = max((v for k, v in vergleich.items()
                          if k.startswith("abweichung_")), default=0.0)
        _log(state, f"✓ CalculiX gegen Z88 auf demselben Netz: hoechste Abweichung "
                    f"{schlimmste:.2f} %", 87)
    return aus


def run_pipeline(data: dict, state: dict, frames: list,
                  workspace: str, project_dir: str | None = None,
                  stages: set | None = None):
    """Run the full analysis pipeline, or — when ``stages`` is given — only a SUBSET
    of stages on an existing project (selective "nachrechnen" of forgotten calcs).

    ``stages`` is a set drawn from {"geometry", "field", "structural", "thermal",
    "drivecycle"}. When it is ``None`` every stage runs (original behaviour). In
    partial mode the existing ``results.json`` is loaded first and only the selected
    (slow/optional) stages are recomputed and merged back; the cheap foundational
    stages (EM static field + speed sweep, structural sweep, shaft connection,
    advanced EM, material/summary) always run because everything downstream needs the
    EM operating point and they cost <1 s. Geometry (FreeCAD) is never rebuilt in
    partial mode — the existing ``motor.FCStd`` is reused.
    """
    # When no project_dir is given, fall back to workspace (legacy behaviour)
    proj = project_dir or workspace
    os.makedirs(proj, exist_ok=True)
    for sub in ("cad_images", "charts", "frames"):
        os.makedirs(os.path.join(proj, sub), exist_ok=True)

    partial = stages is not None
    def _do(name: str) -> bool:
        return (stages is None) or (name in stages)

    # Rotor-Tore VOR allem anderen — sie kosten Millisekunden und sparen im
    # Fehlerfall den 40-s-FreeCAD-Lauf. ``state`` wird durchgereicht, damit die
    # Diagnosezeile im Fortschrittsprotokoll steht und der Nutzer nicht nur einen
    # nackten Traceback sieht. Im Teil-Nachrechnen wird nur gewarnt, nicht
    # abgewiesen: die Geometrie liegt dort fertig auf der Platte und wird gar nicht
    # neu gebaut — ein hartes Tor würde ein ladbares Altprojekt unrechenbar machen.
    _gate_rotor_layout(data, state, fatal=not partial)
    _gate_rotor_stress(data, state, fatal=not partial)

    # Projektakte: Lauf startet → Status laufend (billig, kein base64). Soft.
    try:
        import ema_projekt
        ema_projekt.update(proj, status="rechnet")
    except Exception:
        pass

    geom        = data["geom"]
    rotor_key   = data.get("rotor_lam",  data.get("material", "m270_35a"))
    stator_key  = data.get("stator_lam", rotor_key)
    hp_key      = data.get("hairpin_mat","cu_etp")
    mag_key     = data.get("magnet",     "ndfeb_n35")
    axial       = float(data.get("axial_len",    80.0))
    n_frames    = int(data.get("n_frames",        36))
    fdm_res     = int(data.get("fdm_resolution", 150))
    frame_res   = int(data.get("frame_resolution", 120))
    field_bmax  = float(data.get("field_bmax", 0) or 0)   # 0 = auto |B| colour scale
    load_nm     = float(data.get("load_nm",        5.0))
    rpm_from    = float(data.get("rpm_from",    5000.0))
    rpm_to      = float(data.get("rpm_to",     20000.0))
    rpm_step    = float(data.get("rpm_step",    1000.0))
    # Explicit fixed speed points (e.g. the ranged KI designer: 1000/5000/15000/20000);
    # falls back to the from/to/step sweep when not given. Endpoints set rpm_from/rpm_to
    # so the FEM worst case, deformation tags and thermal design point stay consistent.
    rpm_list    = data.get("rpm_list")
    if isinstance(rpm_list, (list, tuple)) and len(rpm_list) >= 2:
        sweep_rpms = sorted({int(round(float(r))) for r in rpm_list if float(r) > 0})
        rpm_from, rpm_to = float(sweep_rpms[0]), float(sweep_rpms[-1])
    else:
        sweep_rpms = _rpm_sweep_from_range(rpm_from, rpm_to, rpm_step)
    rpm_fem     = rpm_to   # FEM solved at maximum speed (worst case); other speeds scaled

    # Structural-analysis settings (mirrors the magnetic-analysis controls)
    struct_mesh_mm = float(data.get("struct_mesh_mm", 3.0))    # Gmsh char. length [mm]; smaller = finer
    # Welcher Rechensatz und welcher Loeser die Struktur-Stufe rechnet.
    #   "freecad" – der gewachsene Weg (FreeCAD baut das Netz, CalculiX loest). Vorgabe,
    #               und der EINZIGE, der die Verformungsbilder und das Rampenvideo
    #               speist (die brauchen Knotenkoordinaten aus der .frd).
    #   "ccx"     – eigener Rechensatz (ema_deck), Polsektor, CalculiX. Sekunden statt
    #               Minuten, aber ohne Verformungsbilder (5b faellt auf die
    #               analytische Naeherung zurueck — der Pfad existiert schon).
    #   "z88"     – eigener Rechensatz, voller Rotor, Z88Aurora.
    #   "beide"   – eigener Rechensatz, voller Rotor, BEIDE Loeser und die
    #               Gegenueberstellung in results["structural_fem"]["loeservergleich"].
    struct_solver  = str(data.get("struct_solver", "freecad")).lower()
    if struct_solver not in ("freecad", "ccx", "z88", "beide"):
        struct_solver = "freecad"
    struct_video   = bool(data.get("struct_video",   True))    # render deformation ramp video
    struct_frames  = int(data.get("struct_frames",   30))      # video frame count
    struct_img_px  = int(min(5000, max(800, data.get("struct_img_px", 3000))))  # single-image px

    # Thermal inputs
    cooling     = str(data.get("cooling",         "water"))
    T_ambient   = float(data.get("T_ambient",     25.0))
    rpm_thermal = float(data.get("rpm_thermal",   rpm_to))     # design point for steady-state

    # Drive-cycle inputs (optional)
    cycle_kind   = str(data.get("cycle",          "wltp3"))    # "wltp3" | "stadtland" | "vollast" | "anhaenger" | "csv" | "off"
    cycle_csv    = data.get("cycle_csv",          "")
    vehicle_in   = data.get("vehicle",            {}) or {}

    mat    = LAMINATES.get(rotor_key,  LAMINATES["m270_35a"])
    st_mat = LAMINATES.get(stator_key, LAMINATES["m270_35a"])
    hp_mat = HAIRPIN_MATS.get(hp_key,  HAIRPIN_MATS["cu_etp"])
    mag    = MAGNETS.get(mag_key,      MAGNETS["ndfeb_n35"])

    # Override magnet properties in ema_analysis module
    _orig_Br  = ema_analysis.Br_NdFeB
    _orig_mu  = ema_analysis.MU_R_MAG
    ema_analysis.Br_NdFeB = mag["Br"]
    ema_analysis.MU_R_MAG = mag["mu_r"]

    results = {}
    try:
        # motor.FCStd path — always defined (reused by structural FEM + manual);
        # only (re)built when the geometry stage actually runs.
        fcstd = os.path.join(proj, "motor.FCStd")
        if partial:
            # Selective re-run: start from the saved results, recompute only the
            # chosen stages, and merge back. Unselected stages keep their output.
            try:
                with open(os.path.join(proj, "results.json")) as _rf:
                    results = json.load(_rf)
            except Exception as _re:
                _log(state, f"⚠ results.json nicht ladbar ({_re}) — starte leer", 4)
            _log(state, "↻ Teil-Neuberechnung: " + ", ".join(sorted(stages))
                        + " (übrige Ergebnisse bleiben erhalten)", 4)

        # ── 1. FreeCAD geometry (full motor assembly) ─────────────────────────
        # Importierte Geometrie (STEP-Import) NIE neu bauen: motor.FCStd existiert
        # bereits (mit benanntem "Rotor"-Solid) — der else-Zweig nutzt sie für die
        # Struktur-FEM, während die EM-Analyse auf den erkannten customLegs rechnet.
        imported = bool(data.get("imported")) and os.path.exists(fcstd)
        if _do("geometry") and not imported:
            _log(state, "⚙ Erzeuge vollständige Motorgeometrie in FreeCAD...", 4)
            code  = build_full_motor_script(geom, axial, fcstd)
            res   = run_freecad_script(code, timeout=180)

            if not res.get("cad_success"):
                _log(state, "❌ Geometrie fehlgeschlagen:\n" + res.get("stderr", "")[:400])
                state["status"] = "error"
                return

            vol_mm3 = res.get("volume", 0)
            results["geometry"] = {
                "n_faces":   len(res.get("faces", [])),
                "volume_mm3": round(vol_mm3, 0),
                "mass_g":    round(vol_mm3 * mat["density"] * 1e-6, 1),
            }
            _log(state,
                 f"✓ Geometrie: {results['geometry']['n_faces']} Flächen, "
                 f"{vol_mm3:.0f} mm³, Masse ≈ {results['geometry']['mass_g']} g", 20)

            # Topology geometry warnings (e.g. surface-magnet thickness clamped to air gap)
            from ema_topology import magnet_legs as _mlegs
            _slg, _smeta = _mlegs(geom)
            if _smeta.warn:
                _log(state, f"⚠ {_smeta.warn}", 20)
            if _smeta.is_surface and not _smeta.warn:
                clr = geom["statorID"] / 2 - (geom["rotorOD"] / 2 + _slg[0].thickness)
                _log(state, f"✓ Oberflächenmagnet-Luftspalt: {clr:.1f} mm", 20)

            # ── 1a. STEP export (alongside FCStd, same FreeCAD subprocess) ──────
            step_path = res.get("step_path", "")
            if step_path and os.path.exists(step_path):
                results["step_path"] = step_path
                _log(state, f"✓ STEP exportiert: {os.path.basename(step_path)}", 20)
            else:
                err = res.get("step_error", "")
                _log(state, f"⚠ STEP-Export nicht verfügbar {('('+err+')') if err else ''}", 20)

            # ── 1b. CAD images ────────────────────────────────────────────────────
            try:
                cad_imgs = _save_cad_images(geom, axial, proj)
                results["cad_images"] = cad_imgs
                _log(state, "✓ CAD-Bilder gespeichert", 21)
            except Exception as _e:
                _log(state, f"⚠ CAD-Bilder fehlgeschlagen: {_e}", 21)
                results["cad_images"] = {}
        else:
            if not os.path.exists(fcstd):
                _log(state, "⚠ motor.FCStd fehlt — Struktur-FEM braucht die Geometrie; "
                            "bitte einmal die volle Berechnung ausführen", 20)
            if imported:
                _log(state, "📥 Importierte STEP-Geometrie: motor.FCStd (Rotor) wird "
                            "direkt für die Festigkeits-FEM verwendet", 21)
            else:
                _log(state, "↩ Geometrie/CAD übersprungen (bestehende motor.FCStd verwendet)", 21)

        # ── 2. EM field (FDM, static at angle 0) ─────────────────────────────
        # The air-gap Br/Bt profile (chart) needs the thin gap resolved, so solve at
        # ≥ AIRGAP_PROFILE_N regardless of the (often low) user fdm_resolution — a
        # sub-pixel gap makes the sampled tangential field spuriously dominate the
        # radial one.  perf is N-robust and the captured sf_ref is unused downstream
        # (frames self-calibrate), so raising N here is safe.
        em_n   = max(fdm_res, ema_analysis.AIRGAP_PROFILE_N)
        _log(state, f"🔬 Berechne EM-Feld (FDM {em_n}×{em_n})...", 22)
        em0    = ema_analysis.run_em_analysis(geom, N=em_n, rotor_angle=0.0)
        sf_ref = em0["sf_ref"]   # OC calibration factor — reused for all loaded frames
        perf   = em0["performance"]
        airgap_b64 = _airgap_chart(em0)
        _save_png_b64(airgap_b64, os.path.join(proj, "charts", "airgap.png"))
        # UPDATE (not replace) so a partial re-run keeps any saved field-animation
        # metadata (rpm_list / field_modes / videos) when the field stage is skipped.
        results.setdefault("em", {})
        results["em"].update({
            "performance":      perf,
            "airgap_chart_b64": airgap_b64,
            "B_gap_data": {
                "theta_deg": np.degrees(em0["theta"]).tolist()[::4],
                "Br_T":      em0["Br_gap"].tolist()[::4],
                "Bt_T":      em0["Bt_gap"].tolist()[::4],
            },
        })
        _log(state,
             f"✓ EM: B_gap = {perf['B_gap_T']:.3f} T | "
             f"Kt = {perf['Kt_Nm_per_A']:.3f} Nm/A | "
             f"Maxwell-Moment ≈ {perf['T_maxwell_Nm']:.1f} Nm", 38)

        # ── 3. Field animation(s) — one or more visualisation modes ──────────
        # rotate       : rotor turns (rotor_angle sweep), iq/id per RPM (existing)
        # current_angle: rotor fixed, stator current vector angle β sweeps (reaction)
        # load_ramp    : rotor fixed, load 0→full (iq/id scaled) at reference RPM
        n_rpms     = len(sweep_rpms)
        poles      = int(geom["p"]) * 2
        pole_pitch = 2 * math.pi / poles
        rpm_base   = float(sweep_rpms[0])
        # Always include rotate (the main viewer depends on its RPM machinery).
        # Field animation is a slow, selectively re-runnable stage: when not chosen
        # in a partial re-run, leave field_modes empty so every per-mode loop below
        # is skipped and the saved frames/metadata are kept untouched.
        field_modes = (list(dict.fromkeys(["rotate", *(data.get("field_modes") or [])]))
                       if _do("field") else [])

        angles    = np.linspace(0, pole_pitch, n_frames, endpoint=False)
        angle_deg = [round(math.degrees(a), 1) for a in angles]

        modes_meta = []
        videos = {}
        if field_modes:   # skip the extra reference solve entirely when no field work
            # vmax for a consistent colormap across all frames (from loaded base field)
            _iq0, _id0 = ema_analysis.estimate_dq_currents(
                geom, rpm_base, load_nm, b_gap_t=perf["B_gap_T"], rpm_base=rpm_base)
            # saturate=True like the frames themselves — sonst leitet der Farbdeckel
            # aus einem LINEAREN Feld ab, das im Rotor 3…18 T zeigt (µr=500 ohne
            # Sättigungsknie), und die Frames werden gegen eine Skala normiert, die
            # es in der gezeigten Lösung gar nicht gibt.
            _em_ref = ema_analysis.run_em_analysis(
                geom, N=frame_res, rotor_angle=0.0, iq=_iq0, id_=_id0, saturate=True)
            _B_ref  = _em_ref["B_mag"]
            # consistent display ceiling for all frames; user override wins
            vmax_ref = field_bmax if field_bmax > 0 else _field_vmax(_B_ref)

            # Reference operating point for the standstill modes (max speed, full load)
            rpm_ref = float(rpm_to)
            iq_full, id_full = ema_analysis.estimate_dq_currents(
                geom, rpm_ref, load_nm, b_gap_t=perf["B_gap_T"], rpm_base=rpm_base)
            Is_full = math.hypot(iq_full, id_full)

            # High-resolution FDM field maps for the PDF report (these colourful
            # |B| plots dress the report up far more than the line charts): one at
            # open circuit (magnet flux paths) and one at full load / max speed
            # (armature reaction). Saturated display so the iron caps at ~2 T.
            try:
                _emf_N = int(min(600, max(300, frame_res * 2)))
                _b_oc = _field_frame(geom, 0.0, N=_emf_N, iq=0.0, id_=0.0,
                                     out_px=1500, saturate=True, b_ceiling=field_bmax,
                                     magnet_outlines=True)
                _save_png_b64(_b_oc, os.path.join(proj, "charts", "em_field.png"))
                _b_ld = _field_frame(geom, 0.0, N=_emf_N, iq=iq_full, id_=id_full,
                                     rpm=rpm_ref, out_px=1500, saturate=True,
                                     b_ceiling=field_bmax, magnet_outlines=True)
                _save_png_b64(_b_ld, os.path.join(proj, "charts", "em_field_load.png"))
                _log(state, f"✓ EM-Feldbilder (Leerlauf + Last) für Bericht gerendert "
                            f"(FDM {_emf_N}²)", 74)
            except Exception as _fe:
                _log(state, f"⚠ EM-Feldbilder für Bericht fehlgeschlagen: {_fe}", 74)

        def _persist(bucket_key, subdir, b64):
            bucket = frames.setdefault(bucket_key, [])
            bucket.append(b64)
            _save_png_b64(b64, os.path.join(proj, subdir, f"frame_{len(bucket)-1:04d}.png"))

        for mode in field_modes:
            if mode == "rotate":
                sub = FIELD_SUBDIRS["rotate"]; os.makedirs(os.path.join(proj, sub), exist_ok=True)
                frames["rotate"] = []
                total = n_rpms * n_frames; solved = 0
                rpm_list, rpm_stats = [], {}
                _log(state, f"🎞 Rotor-Rotation: {n_rpms} U/min × {n_frames} Frames = {total}...", 40)
                for rpm in sweep_rpms:
                    iq, id_ = ema_analysis.estimate_dq_currents(
                        geom, float(rpm), load_nm, b_gap_t=perf["B_gap_T"], rpm_base=rpm_base)
                    rpm_list.append(rpm)
                    rpm_stats[rpm] = {"iq": round(iq, 1), "id": round(id_, 1),
                                      "freq": round(float(rpm) * int(geom["p"]) / 60, 1)}
                    for ang in angles:
                        b64 = _field_frame(geom, float(ang), N=frame_res, iq=iq, id_=id_,
                                           rpm=float(rpm), vmax_clip=vmax_ref,
                                           saturate=True,
                                           b_ceiling=field_bmax, magnet_outlines=True)
                        _persist("rotate", sub, b64)
                        solved += 1
                        if solved % max(1, total // 15) == 0 or solved == total:
                            _log(state, f"  Rotation [{solved}/{total}]", 40 + solved / total * 18)
                results["em"]["frames_per_rpm"]  = n_frames
                results["em"]["rpm_frame_count"] = n_frames
                results["em"]["frame_angle_deg"] = angle_deg
                results["em"]["rpm_list"]        = rpm_list
                results["em"]["rpm_stats"]       = rpm_stats
                results["em"]["n_frames"]        = len(frames["rotate"])
                modes_meta.append({"mode": "rotate", "label": "Rotor-Rotation",
                                   "frames_per_rpm": n_frames, "rpm_list": rpm_list,
                                   "sweep_label": "Winkel [°]", "sweep_values": angle_deg})
            elif mode == "current_angle":
                sub = FIELD_SUBDIRS["react"]; os.makedirs(os.path.join(proj, sub), exist_ok=True)
                frames["react"] = []
                betas = np.linspace(0, math.pi / 2, n_frames)
                _log(state, f"🧲 Ankerrückwirkung (Stromwinkel β): {n_frames} Frames @ {rpm_ref:.0f} U/min...", 60)
                for b in betas:
                    b64 = _field_frame(geom, 0.0, N=frame_res, iq=Is_full * math.cos(b),
                                       id_=-Is_full * math.sin(b), rpm=rpm_ref,
                                       vmax_clip=vmax_ref, b_ceiling=field_bmax,
                                       saturate=True, magnet_outlines=True)
                    _persist("react", sub, b64)
                modes_meta.append({"mode": "current_angle", "label": "Stromwinkel (Ankerrückwirkung)",
                                   "frames": n_frames, "sweep_label": "β [°]",
                                   "sweep_values": [round(math.degrees(b), 1) for b in betas]})
                _log(state, f"✓ Ankerrückwirkung: {n_frames} Frames", 66)
            elif mode == "load_ramp":
                sub = FIELD_SUBDIRS["load"]; os.makedirs(os.path.join(proj, sub), exist_ok=True)
                frames["load"] = []
                fracs = np.linspace(0, 1, n_frames)
                _log(state, f"🧲 Last-Rampe 0→Volllast: {n_frames} Frames @ {rpm_ref:.0f} U/min...", 66)
                for fr in fracs:
                    b64 = _field_frame(geom, 0.0, N=frame_res, iq=fr * iq_full,
                                       id_=fr * id_full, rpm=rpm_ref,
                                       vmax_clip=vmax_ref, b_ceiling=field_bmax,
                                       saturate=True, magnet_outlines=True)
                    _persist("load", sub, b64)
                modes_meta.append({"mode": "load_ramp", "label": "Last-Rampe",
                                   "frames": n_frames, "sweep_label": "Last [%]",
                                   "sweep_values": [round(fr * 100) for fr in fracs]})
                _log(state, f"✓ Last-Rampe: {n_frames} Frames", 72)

        # Encode each frame set to mp4 (ffmpeg) for download
        for mode in field_modes:
            key = "react" if mode == "current_angle" else ("load" if mode == "load_ramp" else "rotate")
            sub = FIELD_SUBDIRS[key]
            vid = _make_video(os.path.join(proj, sub))
            if vid:
                videos[key] = os.path.join(sub, "anim.mp4")
        if _do("field"):
            results["em"]["field_modes"] = modes_meta
            results["em"]["videos"]      = videos
            _log(state, f"✓ Feld-Animation fertig ({len(field_modes)} Modus/Modi, Videos: {len(videos)})", 75)
        else:
            _log(state, "↩ Feld-Animation übersprungen (bestehende Frames behalten)", 75)

        # ── 4. EM speed sweep (analytical, for charts) ───────────────────────
        _log(state, "📈 EM-Kennlinie über Drehzahlbereich...", 75)
        from ema_analysis import compute_performance
        em_sweep = [compute_performance(geom, perf["B_gap_T"], float(r)) for r in sweep_rpms]
        results["em"]["speed_sweep"]        = em_sweep
        em_sweep_b64 = _em_sweep_chart(em_sweep)
        _save_png_b64(em_sweep_b64, os.path.join(proj, "charts", "em_curve.png"))
        results["em"]["em_sweep_chart_b64"] = em_sweep_b64
        _log(state, "✓ EM-Kennlinie fertig", 78)

        # ── 5. Structural FEM (CalculiX, single solve @ rpm_to; other speeds scaled) ──
        # Slow, selectively re-runnable. When skipped (partial re-run), keep the saved
        # structural_fem result; frd_full is then unavailable so 5b uses the analytical
        # fallback (or, if a real FEM image already exists, 5b is skipped too).
        frd_full = None
        if _do("structural") and struct_solver != "freecad":
            _log(state, f"🏗 Strukturanalyse bei {rpm_fem:.0f} U/min "
                        f"(eigener Rechensatz, {struct_solver}, "
                        f"Netz {struct_mesh_mm:.1f} mm)...", 78)
            try:
                fem_r = _struktur_eigener_satz(geom, mat, rpm_fem, proj, struct_solver,
                                               struct_mesh_mm, state)
            except Exception as _e:
                fem_r = {"solver_status": "FAILED", "rechensatz": "eigen",
                         "rpm": rpm_fem, "log": f"{type(_e).__name__}: {_e}"}
                _log(state, f"⚠ eigener Rechensatz gescheitert: {_e}", 88)
            frd_full = None          # keine .frd -> 5b nimmt die analytische Naeherung
            if fem_r.get("max_von_mises_MPa"):
                _notch = fem_r.get("notch_peak_MPa")
                _st5   = rotor_stress_check(geom, mat, {"n_max": rpm_fem})
                _pk_an = float(_st5["sigma_peak_MPa"])
                _pk_fm = float(_notch) if _notch else 0.0
                peak   = max(_pk_fm, _pk_an)
                sf_v   = mat["yield_mpa"] / peak if peak > 0 else None
                fem_r.update({"safety_factor": round(sf_v, 3) if sf_v else None,
                              "yield_mpa": mat["yield_mpa"],
                              "material":  mat["label"],
                              "stress_peak_gate_MPa": round(peak, 1),
                              "stress_peak_fem_p99_MPa": round(_pk_fm, 1),
                              "stress_peak_analytic_MPa": round(_pk_an, 1),
                              "structural_sf_target": SF_TARGET})
                _log(state,
                     f"✓ FEM (Tier-2, eigener Satz): Peak = max(P99 {_pk_fm:.1f}, "
                     f"Ring×Kt {_pk_an:.1f}) = {peak:.1f} MPa → SF = {sf_v:.2f} "
                     f"(Ziel ≥ {SF_TARGET})", 88)
                _log(state, "   (keine Verformungsbilder — die brauchen den "
                            "FreeCAD-Rechensatz)", 88)
            results["structural_fem"] = fem_r
        elif _do("structural"):
            _log(state, f"🏗 Strukturanalyse bei {rpm_fem:.0f} U/min "
                        f"(FreeCAD + CalculiX, Netz {struct_mesh_mm:.1f} mm)...", 78)
            code_fem = build_rotor_fem_script(fcstd, rpm_fem, _mat_fc(mat), proj,
                                              mesh_mm=struct_mesh_mm)
            # Finer meshes (2nd-order) take longer to mesh + solve — allow up to 20 min.
            res_fem  = run_freecad_script(code_fem, timeout=1200)
            fem_r    = res_fem.get("fem_result", {})

            frd_path = res_fem.get("frd_file", "")
            if frd_path and frd_path != "MISSING" and fem_r.get("solver_status") == "FRD_READY":
                frd_full = _parse_frd_full(frd_path, yield_mpa=mat["yield_mpa"])
                fem_r = {k: v for k, v in frd_full.items() if not k.startswith("_")}
                # Gegenprobe: sind die Magnettaschen in dem, was der Loeser bekam?
                # Ueber die CAD-Bilder ginge das NICHT — die werden aus denselben
                # Parametern gezeichnet wie die Geometrie und koennten einen
                # misslungenen Booleschen Schnitt gar nicht zeigen. Das Volumen der
                # geloesten .inp kann es. Weich: nur ein Vermerk, kein Abbruch.
                try:
                    import ema_deck as _deck
                    _inp = os.path.splitext(frd_path)[0] + ".inp"
                    if os.path.isfile(_inp):
                        _tc = _deck.pruefe_taschen(dict(geom, axialLen=axial), _inp)
                        fem_r["taschen_check"] = _tc
                        if _tc["ok"]:
                            _log(state, f"✓ Magnettaschen im vernetzten Modell bestaetigt "
                                        f"(Netz {_tc['volumen_netz_mm3']:.0f} mm³ gegen "
                                        f"parametrisch {_tc['volumen_taschen_mm3']:.0f} mm³, "
                                        f"{_tc['abw_zu_taschen_pct']:.1f} %)", 87)
                        elif _tc["befund"] == "taschen_fehlen":
                            _log(state, "⚠ Das vernetzte Modell ist der VOLLE RING — die "
                                        "Magnettaschen fehlen in der FEM-Geometrie!", 87)
                        else:
                            _log(state, f"⚠ Taschenpruefung unklar: Netz weicht "
                                        f"{_tc['abw_zu_taschen_pct']:.1f} % von der Parametrik "
                                        f"und {_tc['abw_zu_ring_pct']:.1f} % vom vollen Ring ab", 87)
                except Exception as _tce:                # noqa: BLE001
                    _log(state, f"   (Taschenpruefung uebersprungen: {_tce})", 87)

            if fem_r and fem_r.get("max_von_mises_MPa"):
                # Tier-2-Gate (bindend): Peak = max(FEM-P99, 2D-Ring x Kt).
                # Rohmaximum (sichere Taschen-Ecke) wird NICHT als Gate verwendet.
                _notch = fem_r.get("notch_peak_MPa")
                _st5   = rotor_stress_check(geom, mat, {"n_max": rpm_fem})
                _pk_an = float(_st5["sigma_peak_MPa"])
                _pk_fm = float(_notch) if _notch else 0.0
                peak  = max(_pk_fm, _pk_an)
                sf_v  = mat["yield_mpa"] / peak if peak > 0 else None
                fem_r.update({"safety_factor": round(sf_v, 3) if sf_v else None,
                              "yield_mpa": mat["yield_mpa"],
                              "material":  mat["label"],
                              "rpm":       rpm_fem,
                              "stress_peak_gate_MPa": round(peak, 1),
                              "stress_peak_fem_p99_MPa": round(_pk_fm, 1),
                              "stress_peak_analytic_MPa": round(_pk_an, 1),
                              "structural_sf_target": SF_TARGET})
                u_um = fem_r.get("max_displacement_um", "?")
                _log(state,
                     f"✓ FEM (Tier-2): Peak = max(P99 {_pk_fm or 0:.1f}, Ring×Kt {_pk_an:.1f}) = "
                     f"{peak:.1f} MPa → SF = {sf_v:.2f} (Ziel ≥ {SF_TARGET}) | u_max = {u_um} µm", 88)
                if fem_r.get("max_von_mises_MPa"):
                    _log(state,
                         f"   (Rohmax {fem_r['max_von_mises_MPa']:.0f} MPa = Gitter-Singularitaet an "
                         f"scharfer Taschen-Ecke - kein Gate-Wert)", 88)
            else:
                _raw = res_fem.get("fem_result", {}) or {}
                _att = _raw.get("attempts") or []
                _err = (res_fem.get("stderr") or "").strip()
                # Den GRUND festhalten. Vorher wurde nur stdout gespeichert — und
                # genau der ist bei einer Zeitueberschreitung leer, waehrend der
                # Grund in stderr steht (freecad_runner.py:145). Gemessen an drei
                # Alpenpass-Laeufen vom 27.08.: attempts=[], log="", kein Hinweis,
                # obwohl schlicht der 1200-s-Deckel gerissen war.
                _grund = ("zeitueberschreitung" if "Timeout" in _err
                          else ("kein_rotor" if "no Rotor" in (res_fem.get("stdout") or "")
                                else ("solver" if _att else "unbekannt")))
                fem_r = {"solver_status": "FAILED",
                         "fehlgrund": _grund,
                         "attempts": _att,
                         "log": (res_fem.get("stdout", "") or "")[-1500:],
                         "fehlertext": _err[-500:],
                         "struct_mesh_mm": struct_mesh_mm,
                         "rpm": rpm_fem}
                frd_full = None
                if _grund == "zeitueberschreitung":
                    _log(state,
                         f"⚠ CalculiX ABGEBROCHEN: Zeitueberschreitung bei Netz "
                         f"{struct_mesh_mm} mm. Feinere Netze kosten ueberproportional "
                         f"Zeit (gemessen: 3 mm ≈ 7 min, 2 mm deutlich mehr als 20 min).", 88)
                    _log(state, "   Abhilfe: groeberes Netz — oder struct_solver='ccx', "
                                "der eigene Rechensatz rechnet denselben Fall in Sekunden.", 88)
                else:
                    _log(state,
                         f"⚠ CalculiX ohne Ergebnis ({_grund}"
                         + (f", {len(_att)} Netz-Versuche" if _att else ", kein Netz-Versuch")
                         + ")", 88)
                if _err:
                    _log(state, f"   Meldung: {_err[:200]}", 88)
                for _a in _att[:4]:
                    _log(state, f"   • {_a}", 88)
                _log(state, "   → Verformung und Spannung kommen aus der analytischen "
                            "Naeherung (Lamé), NICHT aus der FEM.", 88)
            results["structural_fem"] = fem_r
        else:
            fem_r = results.get("structural_fem", {}) or {}
            _log(state, "↩ Struktur-FEM übersprungen (bestehende Ergebnisse)", 88)

        # ── 5b. FEM deformation: burst speed + 3 high-res images + ramp video ──
        # One solve (above, at rpm_fem) is scaled by rpm² to every speed of interest.
        if _do("structural"):
            deform_result = {"chart_b64": "", "stats": {}, "images": [], "video": False,
                             "burst_rpm": None}
            try:
                yld = float(mat["yield_mpa"])
                # Primary: real CalculiX result. Fallback: analytical rotating-disc
                # (Lamé) deformation when ccx couldn't solve (thin/disconnected iron
                # bridges in aggressive topologies) — the Verformung tab always shows
                # the radial growth either way.
                fem_ok = bool(frd_full and frd_full.get("_nodes")
                              and fem_r.get("max_von_mises_MPa"))
                if fem_ok:
                    arrays      = _deform_extract(frd_full)
                    sigma_solve = float(fem_r.get("stress_peak_gate_MPa")
                                       or fem_r.get("max_von_mises_MPa") or 0.0)
                    title_pref  = "FEM-Verformung"
                    deform_result["source"] = "fem"
                else:
                    arrays, sig_hoop = _analytical_deform_arrays(geom, mat, rpm_fem)
                    sigma_solve = sig_hoop * 1.5          # Kt≈1.5, matches _struct_sweep
                    title_pref  = "Verformung (analytisch)"
                    deform_result["source"] = "analytical"
                    _log(state, "ℹ FEM ohne Ergebnis — analytische Verformung (Lamé) wird dargestellt", 88)
                burst       = _burst_rpm(sigma_solve, rpm_fem, yld)
                deform_result["burst_rpm"] = round(burst) if burst else None

                # Fixed exaggeration + colour ceiling from the WORST speed shown
                # (max(rpm_to, burst)) so all images/frames are directly comparable.
                R_rot     = geom["rotorOD"] / 2
                rpm_worst = max(rpm_fem, burst or 0.0)
                s_worst   = (rpm_worst / rpm_fem) ** 2 if rpm_fem > 0 else 1.0
                _, _, _, _, dmag = arrays
                d_worst_mm = float(np.max(dmag)) * s_worst
                exagg      = max(1.0, min(5000.0, R_rot * 0.08 / (d_worst_mm + 1e-9)))
                um_clip    = float(np.max(dmag)) * s_worst * 1e3   # µm ceiling at worst speed

                # Three operating points: rated (base) speed, max speed, burst speed
                pts = [("nennlast", "Nennlast (Grunddrehzahl)", rpm_from),
                       ("max",      "Maximaldrehzahl",          rpm_fem)]
                if burst:
                    pts.append(("burst", "Berstdrehzahl (SF→1)", burst))
                # Analytical (Lamé) is axisymmetric → smooth filled-annulus render;
                # FEM keeps the per-node scatter (irregular mesh nodes, real pockets).
                _smooth = mat if deform_result.get("source") == "analytical" else None
                for tag, label, rpm_t in pts:
                    if _smooth is not None:
                        b64, st = _render_deform_analytical(
                            geom, _smooth, float(rpm_t), rpm_fem, sigma_solve, yld,
                            exagg, px=struct_img_px, max_um_clip=um_clip,
                            title_prefix=title_pref)
                    else:
                        b64, st = _render_deform_single(
                            arrays, geom, float(rpm_t), rpm_fem, sigma_solve, yld,
                            exagg, px=struct_img_px, max_um_clip=um_clip,
                            title_prefix=title_pref)
                    fname = f"deformation_{tag}.png"
                    _save_png_b64(b64, os.path.join(proj, "charts", fname))
                    deform_result["images"].append(
                        {"tag": tag, "label": label, "file": fname, "stats": st})
                # Keep chart_b64 + charts/deformation.png as the max-speed image
                # for back-compat (PDF report [BILD:deformation], quick view).
                if deform_result["images"]:
                    mx = next((im for im in deform_result["images"] if im["tag"] == "max"),
                              deform_result["images"][0])
                    mx_path = os.path.join(proj, "charts", mx["file"])
                    deform_result["chart_b64"] = base64.b64encode(
                        open(mx_path, "rb").read()).decode()
                    deform_result["stats"] = mx["stats"]
                    shutil.copyfile(mx_path, os.path.join(proj, "charts", "deformation.png"))
                _log(state,
                     f"✓ Verformung: Berstdrehzahl ≈ {deform_result['burst_rpm'] or '?'} U/min, "
                     f"{len(deform_result['images'])} Einzelbilder ({struct_img_px} px)", 89)

                if struct_video:
                    _log(state, f"🎞 Verformungs-Video (0→{rpm_fem:.0f} U/min, "
                                f"{struct_frames} Frames)...", 90)
                    vdir = os.path.join(proj, "frames_struct")
                    vid = _deformation_video(arrays, geom, rpm_fem, rpm_fem, sigma_solve,
                                             yld, exagg, um_clip, vdir, n_frames=struct_frames,
                                             title_prefix=title_pref, smooth_mat=_smooth)
                    deform_result["video"] = bool(vid)
                    _log(state, f"✓ Verformungs-Video: {'erstellt' if vid else 'ffmpeg fehlt'}", 91)
            except Exception as _de:
                _log(state, f"⚠ Verformungsdarstellung fehlgeschlagen: {_de}", 91)
            results["deformation"] = deform_result
        else:
            _log(state, "↩ Verformung übersprungen (bestehende Ergebnisse)", 91)

        # ── 6. Structural speed sweep (analytical) ────────────────────────────
        _log(state, "📈 Strukturkennlinie über Drehzahlbereich...", 91)
        struct_sweep = _struct_sweep(geom, mat, sweep_rpms)
        results["structural_sweep"] = struct_sweep
        struct_chart_b64 = _struct_sweep_chart(
            fem_r if fem_r.get("max_von_mises_MPa") else None,
            struct_sweep, mat["yield_mpa"]
        )
        _save_png_b64(struct_chart_b64, os.path.join(proj, "charts", "structural_sweep.png"))
        results["structural_sweep_chart_b64"] = struct_chart_b64
        max_safe_rpm = next(
            (s["rpm"] for s in reversed(struct_sweep) if s["safety_factor"] >= SF_TARGET),
            struct_sweep[0]["rpm"]
        )
        # ── Derate by the FEM result ──────────────────────────────────────────
        # The analytical Lamé rotating-disc model does NOT capture the stress
        # concentration at the thin iron bridges over the magnet pockets — the
        # CalculiX FEM does (and the Kt-factor approximates it, now on the
        # CORRECT plane-strain annulus formula). Since stress ∝ rpm² and the
        # solve is linear, the FEM-anchored safe speed (SF = target) is
        # rpm_solve·√(SF_fem/target). Always report the MORE CONSERVATIVE of the
        # two so the table is honest. Binding target for SF is 1.3 (requirement),
        # so "max. sichere Drehzahl" = speed where SF just reaches 1.3.
        sf_fem  = fem_r.get("safety_factor")
        rpm_fem = fem_r.get("rpm")
        structural_ok = True
        if sf_fem and rpm_fem and sf_fem > 0:
            max_safe_rpm_fem = rpm_fem * math.sqrt(sf_fem / SF_TARGET)
            if max_safe_rpm_fem < max_safe_rpm:
                _log(state, f"⚠ FEM derated max. sichere Drehzahl: analytisch "
                            f"{max_safe_rpm:.0f} → FEM {max_safe_rpm_fem:.0f} U/min "
                            f"(SF_FEM={sf_fem:.2f} @ {rpm_fem:.0f})", 92)
            max_safe_rpm = min(max_safe_rpm, max_safe_rpm_fem)
            # structurally OK only if the notch-tolerant FEM safety factor at the
            # operating max speed already meets the SF >= 1.3 requirement
            structural_ok = bool(sf_fem >= SF_TARGET)
        results["structural_ok"]      = structural_ok
        results["max_safe_rpm_fem"]   = (round(rpm_fem * math.sqrt(sf_fem / SF_TARGET))
                                         if (sf_fem and rpm_fem and sf_fem > 0) else None)
        _log(state, f"✓ Strukturkennlinie: max. sichere Drehzahl ≈ {max_safe_rpm:.0f} U/min"
                    f"{'' if structural_ok else ' ⚠ FEM: Versagen im Betriebsbereich'}", 93)

        # ── 6b. Shaft–core connection assessment (analytical) ─────────────────
        try:
            conn_res = connection_assessment(geom, mat, rpm_to, axial, cooling)
            conn_chart = _connection_chart(conn_res, rpm_to)
            _save_png_b64(conn_chart, os.path.join(proj, "charts", "connection.png"))
            conn_res["chart_b64"] = conn_chart
            results["connection"] = conn_res
            _flag = "" if conn_res.get("ok") else " ⚠"
            _extra = (f", Lösedrehzahl≈{conn_res.get('loosening_rpm')}"
                      if conn_res.get("type") == "press" else "")
            _log(state, f"🔗 Wellenverbindung ({conn_res['note']}): "
                        f"Auslastung {conn_res.get('utilization')}{_extra}{_flag}", 93)
        except Exception as _ce:
            _log(state, f"⚠ Wellenverbindung-Bewertung fehlgeschlagen: {_ce}", 93)

        # ── 7. Thermal LPTN analysis ──────────────────────────────────────────
        # CFD-Kopplung (opt-in): liegt für dieses Projekt eine OpenFOAM-VOF-Spritzölrechnung
        # vor UND ist Ölkühlung gewählt, treibt der GERECHNETE HTC die Wicklungskühlung statt
        # des Preset-h_eff. Der CFD-Lauf ist separat (schreibt results.json["cfd"]) → auch von
        # der Platte lesen, falls nicht schon im in-memory results.
        _htc_oil, _wetted_area, _htc_source = 0.0, 0.0, "preset"
        if cooling == "oil":
            _cfd = results.get("cfd")
            if not _cfd:
                try:
                    with open(os.path.join(proj, "results.json")) as _cf:
                        _cfd = json.load(_cf).get("cfd")
                except Exception:
                    _cfd = None
            if _cfd and _cfd.get("htc_eff"):
                _htc_oil = float(_cfd["htc_eff"])
                _wetted_area = float(_cfd.get("wetted_area_m2") or 0.0)
                _htc_source = "cfd"
        if _do("thermal"):
            _log(state, f"🌡 Thermisches Modell ({cooling}, {T_ambient}°C Umgebung)...", 93)
            if _htc_source == "cfd":
                _log(state, f"  🌊 CFD-Spritzöl-HTC {_htc_oil:.0f} W/m²·K (benetzt "
                            f"{_wetted_area*1e4:.1f} cm²) treibt die Wicklungskühlung", 93)
            try:
                therm = ema_thermal.run_thermal_analysis(
                    geom, axial, rpm_thermal, load_nm, perf,
                    mat, st_mat, hp_mat, mag,
                    cooling=cooling, T_amb=T_ambient, t_max=_THERMAL_TIME_S,
                    htc_oil=_htc_oil, wetted_area_m2=_wetted_area)
                therm["htc_source"] = _htc_source
                therm["htc_oil_Wm2K"] = round(_htc_oil, 1)
                therm_chart_b64 = _thermal_chart(therm)
                _save_png_b64(therm_chart_b64, os.path.join(proj, "charts", "thermal.png"))
                therm["chart_b64"] = therm_chart_b64
                results["thermal"] = therm
                ss = therm["steady"]
                _log(state,
                     f"✓ Thermal: T_w={ss['T_winding']:.0f}°C  T_M={ss['T_magnet']:.0f}°C  "
                     f"T_H={ss['T_housing']:.0f}°C  | P_ges={therm['losses']['P_total']:.0f} W", 96)
                for w in therm.get("warnings", []):
                    _log(state, f"  {w}", 96)

                # Magnet segmentation summary (eddy-loss reduction + skin-depth check)
                _ls = therm.get("losses") or {}
                results["segmentation"] = {
                    "n_ax":          _ls.get("n_ax", 1),
                    "n_circ":        _ls.get("n_circ", 1),
                    "k_seg":         _ls.get("k_seg", 1.0),
                    "delta_skin_mm": _ls.get("delta_skin_mm"),
                    "P_Mag_eddy_W":  _ls.get("P_Mag_eddy"),
                    "P_Mag_unseg_W": _ls.get("P_Mag_unseg"),
                    "warning":       _ls.get("seg_warning", False),
                }
                if _ls.get("n_ax", 1) > 1 or _ls.get("n_circ", 1) > 1:
                    _log(state,
                         f"  🧲 Segmentierung n_ax={_ls.get('n_ax')} n_circ={_ls.get('n_circ')}: "
                         f"P_Mag {_ls.get('P_Mag_unseg')}→{_ls.get('P_Mag_eddy')} W "
                         f"(×{_ls.get('k_seg')}), δ={_ls.get('delta_skin_mm')} mm", 96)
                if _ls.get("seg_warning"):
                    _log(state, "  ⚠ Segmentbreite > Skintiefe — Segmentierung kaum wirksam", 96)
            except Exception as _te:
                _log(state, f"⚠ Thermal-Analyse fehlgeschlagen: {_te}", 96)
                results["thermal"] = {"error": str(_te)}
        else:
            _log(state, "↩ Thermik übersprungen (bestehende Ergebnisse)", 96)

        # ── 7b. Advanced EM metrics (Ld/Lq, MTPA, Isc, demagnetisation) ───────
        try:
            _tmag = ((results.get("thermal") or {}).get("steady") or {}).get("T_magnet", 20.0)
            adv = ema_analysis.compute_advanced_em(
                geom, perf, axial, rpm_base, rpm_to, load_nm,
                mag=mag, magnet_temp_C=_tmag)
            results["em_advanced"] = adv
            _log(state,
                 f"✓ EM-Advanced: Ld={adv['Ld_mH']} Lq={adv['Lq_mH']} mH | "
                 f"Isc={adv['Isc_A']} A | Demag-Reserve={adv['demag']['margin_T']} T"
                 + ("  ⚠ DEMAG-RISIKO" if adv['demag']['risk'] else ""), 96)
        except Exception as _ae:
            _log(state, f"⚠ EM-Advanced fehlgeschlagen: {_ae}", 96)
            results["em_advanced"] = {"error": str(_ae)}

        # ── 7c. Torque/power envelope — "was kann die Maschine maximal?" ──────
        # Deliberately placed HERE: it needs em_advanced (ψ/Ld/Lq), the cooling-based
        # rated torque and the structurally safe speed, i.e. all three domains. All
        # inputs are already computed, so this costs milliseconds.
        try:
            _T_rated = float((results.get("thermal") or {}).get("T_rated_Nm")
                             or (results.get("connection") or {}).get("T_rated_Nm") or 0.0)
            env = ema_analysis.power_envelope(
                geom, results.get("em_advanced") or {},
                rpm_max=max_safe_rpm, T_rated_Nm=_T_rated)
            results["power"] = env
            if "error" not in env:
                env_b64 = _power_chart(env)
                _save_png_b64(env_b64, os.path.join(proj, "charts", "power.png"))
                results["power"]["chart_b64"] = env_b64
                _log(state,
                     f"✓ Leistung: P_max ≈ {env['P_max_kW']:.0f} kW @ {env['P_max_rpm']:.0f} U/min | "
                     f"T_max ≈ {env['T_peak_max_Nm']:.0f} Nm bis {env['rpm_base']:.0f} U/min", 96)
            else:
                _log(state, f"⚠ Leistungskennlinie: {env['error']}", 96)
        except Exception as _pe:
            _log(state, f"⚠ Leistungskennlinie fehlgeschlagen: {_pe}", 96)
            results["power"] = {"error": str(_pe)}

        # ── 8. Drive-cycle analysis (optional; selectively re-runnable) ───────
        if _do("drivecycle") and cycle_kind != "off":
            vehicle    = {**ema_drivecycle.DEFAULT_VEHICLE, **vehicle_in}
            # User-settable trailer: total mass (incl. payload), axle count, max grade %
            trailer_in = data.get("trailer", {}) or {}
            tr_mass    = trailer_in.get("mass_kg")
            tr_axles   = trailer_in.get("n_axles")
            tr_grade   = float(trailer_in.get("grade_pct", ema_drivecycle.DEFAULT_TRAILER_GRADE_PCT))

            def _run_one_cycle(cyc_obj: dict, veh: dict, chart_key: str) -> dict:
                drv = ema_drivecycle.compute_drivetrain(cyc_obj, veh)
                series = ema_thermal.cycle_loss_series(
                    drv, geom, axial, perf, mat, st_mat, hp_mat, mag,
                    cooling=cooling, rpm_base=rpm_base)
                res = ema_drivecycle.cycle_energy(drv, series, veh)
                b64 = _drivecycle_chart(cyc_obj, drv, res)
                _save_png_b64(b64, os.path.join(proj, "charts", f"{chart_key}.png"))
                res["chart_b64"]  = b64
                res["cycle_name"] = cyc_obj["name"]
                res["vehicle"]    = veh
                # Per-cycle thermal analysis (transient peak + continuous steady)
                try:
                    cyc_therm = ema_thermal.thermal_for_cycle(
                        drv, res, series, geom, axial,
                        mat, st_mat, hp_mat, mag,
                        cooling=cooling, T_amb=T_ambient)
                    res["thermal"] = cyc_therm
                    avg, pk = cyc_therm["avg"], cyc_therm["peak"]
                    _log(state,
                         f"   🌡 Thermisch ({cyc_obj['name']}): "
                         f"Dauer T_W={avg['T_winding']:.0f}°C T_M={avg['T_magnet']:.0f}°C | "
                         f"Peak T_W={pk['T_winding']:.0f}°C T_M={pk['T_magnet']:.0f}°C "
                         f"(T_Nenn={cyc_therm.get('T_rated_Nm','?')} Nm)", 96)
                    for w in cyc_therm.get("warnings", []):
                        _log(state, f"     {w}", 96)
                except Exception as _cte:
                    _log(state, f"   ⚠ Zyklus-Thermik fehlgeschlagen: {_cte}", 96)
                    res["thermal"] = {"error": str(_cte)}
                return res

            # Primary cycle
            try:
                if cycle_kind == "csv" and cycle_csv:
                    cyc_primary = ema_drivecycle.load_csv_cycle(cycle_csv)
                    veh_primary = vehicle
                elif cycle_kind == "vollast":
                    cyc_primary = ema_drivecycle.fullload_cycle()
                    veh_primary = vehicle
                elif cycle_kind == "stadtland":
                    cyc_primary = ema_drivecycle.stadtland_cycle()
                    veh_primary = vehicle
                elif cycle_kind == "anhaenger":
                    cyc_primary = ema_drivecycle.trailer_mountain_cycle(tr_grade)
                    veh_primary = ema_drivecycle.trailer_vehicle(vehicle, tr_mass, tr_axles)
                else:
                    cyc_primary = ema_drivecycle.wltp_class3()
                    veh_primary = vehicle

                cyc_res = _run_one_cycle(cyc_primary, veh_primary, "drivecycle")
                results["drivecycle"] = cyc_res
                _log(state,
                     f"🚗 Zyklus ({cyc_primary['name']}): {cyc_res['distance_km']:.1f} km · "
                     f"{cyc_res['E_per_100km_kWh']:.2f} kWh/100 km · "
                     f"η={cyc_res['eta_drive']*100:.1f}%", 96)
            except Exception as _ce:
                _log(state, f"⚠ Primärer Drive-Cycle fehlgeschlagen: {_ce}", 96)
                results["drivecycle"] = {"error": str(_ce)}

            # Autobahn-Vollgas when cycle_kind includes it
            if cycle_kind in ("both", "wltp3"):
                try:
                    cyc_vl = ema_drivecycle.fullload_cycle()
                    vl_res = _run_one_cycle(cyc_vl, vehicle, "drivecycle_vollast")
                    results["drivecycle_vollast"] = vl_res
                    _log(state,
                         f"🏎 Autobahn 220: {vl_res['distance_km']:.1f} km · "
                         f"{vl_res['E_per_100km_kWh']:.2f} kWh/100 km · "
                         f"η={vl_res['eta_drive']*100:.1f}%", 97)
                except Exception as _ve:
                    _log(state, f"⚠ Vollast-Zyklus fehlgeschlagen: {_ve}", 97)
                    results["drivecycle_vollast"] = {"error": str(_ve)}

            # Anhänger-Alpenpass always when "both" or "anhaenger_extra" flag set
            if cycle_kind in ("both",) or data.get("cycle_anhaenger"):
                try:
                    cyc_ah = ema_drivecycle.trailer_mountain_cycle(tr_grade)
                    veh_ah = ema_drivecycle.trailer_vehicle(vehicle, tr_mass, tr_axles)
                    ah_res = _run_one_cycle(cyc_ah, veh_ah, "drivecycle_anhaenger")
                    results["drivecycle_anhaenger"] = ah_res
                    _log(state,
                         f"⛰ Anhänger-Alpenpass: {ah_res['distance_km']:.1f} km · "
                         f"{ah_res['E_per_100km_kWh']:.2f} kWh/100 km · "
                         f"T_max={ah_res['T_max']:.0f} Nm", 98)
                except Exception as _ae:
                    _log(state, f"⚠ Anhänger-Zyklus fehlgeschlagen: {_ae}", 98)
                    results["drivecycle_anhaenger"] = {"error": str(_ae)}

        # ── Material estimates ────────────────────────────────────────────────
        # Fill factor (hairpin conductors / slot area)
        n_layers  = 2
        ins       = 0.8
        import math as _m
        dtheta_s  = 2 * _m.pi / int(geom["slots"])
        slot_w    = max(3.0, (geom["statorID"] / 2) * dtheta_s *
                        float(geom.get("slotWidthRatio", 0.5)))
        slot_dep  = float(geom["slotDepth"])
        cond_w    = max(1.5, slot_w - 2 * ins)
        layer_h   = max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)
        fill_factor = round(cond_w * layer_h * n_layers / (slot_w * slot_dep), 3)

        # Iron-loss estimate (Bertotti simplified, open-circuit no-load)
        f_el      = rpm_fem * int(geom["p"]) / 60
        R_si_m    = (geom["statorID"] / 2) / 1000
        R_so_m    = (geom["statorOD"] / 2) / 1000
        slot_area = slot_dep * slot_w * 1e-6   # m²
        V_st_m3   = (_m.pi * (R_so_m**2 - R_si_m**2) * (axial / 1000) -
                     int(geom["slots"]) * slot_area * (axial / 1000))
        mass_st_kg = max(0.01, V_st_m3 * st_mat["density"])
        P_fe_W    = (st_mat["specific_loss_Wkg"] *
                     (f_el / 50) * (perf["B_gap_T"] ** 2) * mass_st_kg)

        results["materials"] = {
            "rotor_lam":       mat["label"],
            "stator_lam":      st_mat["label"],
            "hairpin":         hp_mat["label"],
            "magnet":          mag["label"],
            "fill_factor":     fill_factor,
            "P_fe_W_est":      round(P_fe_W, 1),
            "rho_hairpin_Ohm_m": hp_mat["rho_el"],
            "hairpin_density": hp_mat["density"],
            "stator_B_sat_T":  st_mat["B_sat_T"],
            "rotor_B_sat_T":   mat["B_sat_T"],
        }

        # ── Summary ───────────────────────────────────────────────────────────
        therm_summary = results.get("thermal", {}) or {}
        ss             = (therm_summary.get("steady") or {})
        losses_summary = (therm_summary.get("losses") or {})
        results["summary"] = {
            "B_gap_T":         perf["B_gap_T"],
            "Kt_Nm_per_A":     perf["Kt_Nm_per_A"],
            "T_maxwell_Nm":    perf.get("T_maxwell_Nm", 0),
            "lcm_slots_poles": perf["lcm_slots_poles"],
            "max_safe_rpm":    max_safe_rpm,
            "P_max_kW":        (results.get("power") or {}).get("P_max_kW"),
            "P_max_rpm":       (results.get("power") or {}).get("P_max_rpm"),
            "P_cont_max_kW":   (results.get("power") or {}).get("P_cont_max_kW"),
            "T_peak_max_Nm":   (results.get("power") or {}).get("T_peak_max_Nm"),
            "structural_ok":   structural_ok,
            # WORAUF die Festigkeitsaussage beruht. Ohne das steht ein gruenes
            # structural_ok auch dann da, wenn die FEM gar nicht gelaufen ist —
            # gemessen der Fall in allen drei Alpenpass-Laeufen vom 27.08.
            "structural_basis": ("fem" if fem_r.get("max_von_mises_MPa")
                                 else "analytisch"),
            "safety_factor_fem": fem_r.get("safety_factor"),
            "fem_rpm":         fem_r.get("rpm"),
            "fem_sigma_vm_MPa": fem_r.get("max_von_mises_MPa"),
            "rotor_lam":       mat["label"],
            "stator_lam":      st_mat["label"],
            "hairpin":         hp_mat["label"],
            "magnet":          mag["label"],
            "mass_g":          (results.get("geometry") or {}).get("mass_g"),
            "fill_factor":     fill_factor,
            "P_fe_W_est":      round(P_fe_W, 1),
            "T_winding_C":     ss.get("T_winding"),
            "T_magnet_C":      ss.get("T_magnet"),
            "T_housing_C":     ss.get("T_housing"),
            "P_total_W":       losses_summary.get("P_total"),
            "cooling":         therm_summary.get("cooling_label", ""),
            "htc_source":      (results.get("thermal") or {}).get("htc_source", "preset"),
            "htc_oil_Wm2K":    (results.get("thermal") or {}).get("htc_oil_Wm2K"),
            "cycle_kWh100km":  (results.get("drivecycle") or {}).get("E_per_100km_kWh"),
            "cycle_eta":       (results.get("drivecycle") or {}).get("eta_drive"),
            "cycle_name":      (results.get("drivecycle") or {}).get("cycle_name", ""),
            "vollast_kWh100km":(results.get("drivecycle_vollast") or {}).get("E_per_100km_kWh"),
            "vollast_eta":     (results.get("drivecycle_vollast") or {}).get("eta_drive"),
            "anhaenger_kWh100km":(results.get("drivecycle_anhaenger") or {}).get("E_per_100km_kWh"),
            "anhaenger_T_max_Nm":(results.get("drivecycle_anhaenger") or {}).get("T_max"),
        }
        results["manual"] = {
            "fcstd_path":  fcstd,
            "step_path":   results.get("step_path", ""),
            "open_cmd":    f"cd ~/freecad_1.1_quellcode && pixi run freecad-release \"{fcstd}\"",
        }
        results["project"] = {
            "id":         os.path.basename(proj),
            "dir":        proj,
            "n_frames":   len(frames),
        }

        # ── Persist project metadata + results to disk ───────────────────────
        try:
            meta = {
                "label":      data.get("project_name", "") or os.path.basename(proj),
                "created":    datetime.datetime.now().isoformat(timespec="seconds"),
                "rpm_range":  f"{int(rpm_from)}–{int(rpm_to)} U/min",
                "rpm_step":   int(rpm_step),
                "n_frames":   len(frames),
                "frames_per_rpm": n_frames,
                "materials":  {"rotor": mat["label"], "stator": st_mat["label"],
                               "hairpin": hp_mat["label"], "magnet": mag["label"]},
                "geom":       geom,
                "axial_len":  axial,
                "load_nm":    load_nm,
                "cooling":    cooling,
                "T_ambient":  T_ambient,
                "rpm_thermal": rpm_thermal,
                # KI-Auslegungs-Pfad: Aufgabe/Begründung/Quelle für das Trainingsfile
                # (fehlen bei Hand-Entwürfen → "hand").
                "design_brief":     data.get("design_brief", ""),
                "design_rationale": data.get("design_rationale", ""),
                "design_source":    data.get("design_source", "hand"),
                # Full input payload for "Projekt aus Vorlage erstellen" — lets the
                # form be repopulated exactly (minus the one-shot CSV upload).
                "payload":    {k: v for k, v in data.items() if k != "cycle_csv"},
            }
            with open(os.path.join(proj, "meta.json"), "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            with open(os.path.join(proj, "results.json"), "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            _log(state, f"💾 Projekt gespeichert: {proj}", 99)
            # Rechnungsdatenbank nachfuehren. Weich: sie ist ein INDEX ueber
            # results.json und laesst sich jederzeit neu aufbauen ('cae_cli.py db
            # import'), also darf ein Fehler hier den Lauf nie scheitern lassen —
            # die maßgeblichen Daten liegen zwei Zeilen darueber bereits auf der Platte.
            try:
                import ema_db as _db
                _conn = _db.oeffne()
                _db.importiere_projekt(_conn, proj)
                _conn.close()
                _log(state, "🗃 Rechnungsdatenbank nachgefuehrt", 99)
            except Exception as _dbe:                        # noqa: BLE001
                _log(state, f"⚠ Rechnungsdatenbank nicht nachgefuehrt ({_dbe})", 99)
            # Fortlaufendes LLM-Trainingsfile: eine JSONL-Zeile je Berechnung
            # (Geometrie/Material → Kennwerte). Label "gut/schlecht" wird später
            # im Ergebnis-Tab gesetzt. Upsert per Projekt-ID (kein Duplikat beim
            # Nachrechnen). Soft — ein Fehler darf die Analyse nie abbrechen.
            try:
                import ema_training
                # Vom Nutzer korrigiertes/bestätigtes gut-schlecht-Urteil aus dem
                # Designer (KI-Varianten-Liste) → als MANUELLES Label übernehmen
                # (label_source="user"), sonst None (KI-Entwürfe werden in upsert
                # heuristisch vorsortiert, Hand-Entwürfe bleiben unbewertet).
                _dl = data.get("design_label")
                _dl = _dl if _dl in ("gut", "schlecht") else None
                ema_training.upsert(os.path.basename(proj), meta, results,
                                    label=_dl, project_dir=proj)
                _log(state, "📚 Trainingsdatensatz aktualisiert", 99)
            except Exception as _te:
                _log(state, f"⚠ Trainingsfile nicht geschrieben: {_te}", 99)
            # Projektakte fortschreiben: Evolutionsstufe anhängen (Eingabe-Diff +
            # Kennzahlen) und Datenblatt/Assets/Status aktualisieren. Die Action
            # unterscheidet Voll-/Teil-Lauf bzw. KI-Entwurf. Soft — Akte darf den
            # Lauf nie abbrechen.
            try:
                import ema_projekt
                if partial:
                    _action = "recompute:" + ",".join(sorted(stages))
                elif meta.get("design_source") == "ki":
                    _action = "design_ai"
                else:
                    _action = "analyse"
                ema_projekt.record_run(proj, os.path.basename(proj), meta, results,
                                       action=_action,
                                       note=str(data.get("evolution_note", "") or ""))
            except Exception as _ae:
                _log(state, f"⚠ Projektakte nicht geschrieben: {_ae}", 99)
        except Exception as _pe:
            _log(state, f"⚠ Projekt-Speichern fehlgeschlagen: {_pe}", 99)

        state["results"] = results
        state["status"]  = "done"
        _log(state,
             f"✅ Analyse abgeschlossen — "
             f"B_gap={perf['B_gap_T']:.3f} T, "
             f"max. sicher: {max_safe_rpm:.0f} U/min", 100)

    except Exception as e:
        import traceback
        _log(state, f"❌ FEHLER: {e}\n{traceback.format_exc()[:600]}")
        state["status"] = "error"
    finally:
        ema_analysis.Br_NdFeB = _orig_Br
        ema_analysis.MU_R_MAG = _orig_mu
        ema_analysis.clear_lu_cache()   # free the LU factorisations for this run
