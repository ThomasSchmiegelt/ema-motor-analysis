"""Full E-machine analysis pipeline: Geometry → EM → Structural FEM → Post-processing."""

import math, io, base64, os, json, re, datetime, subprocess
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

from freecad_runner import run_freecad_script
from ema_freecad   import build_full_motor_script, build_rotor_fem_script
import ema_analysis
import ema_thermal
import ema_drivecycle


# ── Project directory ─────────────────────────────────────────────────────────

def create_project_dir(root: str, name: str = "") -> tuple[str, str]:
    """Create a fresh ~/cae_projekte/<timestamp>[_<name>]/ directory.
    Returns (full_path, project_id)."""
    ts   = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = re.sub(r'[^\w\-]+', '_', (name or "").strip())[:48].strip("_")
    pid  = f"{ts}_{safe}" if safe else ts
    full = os.path.join(root, pid)
    os.makedirs(full, exist_ok=True)
    for sub in ("cad_images", "charts", "frames"):
        os.makedirs(os.path.join(full, sub), exist_ok=True)
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
MAGNETS = {
    "ndfeb_n35": {"label": "NdFeB N35", "Br": 1.15, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310},
    "ndfeb_n42": {"label": "NdFeB N42", "Br": 1.28, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310},
    "ndfeb_n50": {"label": "NdFeB N50", "Br": 1.40, "mu_r": 1.05, "T_op_max": 80,  "T_curie": 310},
    "ferrite":   {"label": "Ferrit Y30","Br": 0.40, "mu_r": 1.07, "T_op_max": 250, "T_curie": 450},
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
    sf = round(yield_mpa / max_vm, 2) if yield_mpa > 0 and max_vm > 0 else None

    return {
        "solver_status":       "OK",
        "max_von_mises_MPa":   round(max_vm, 2),
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


def _fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=90, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode()


# ── Field frame (single rotor angle) ─────────────────────────────────────────

def _field_frame(geom: dict, rotor_angle: float, N: int = 120,
                 iq: float = 0.0, id_: float = 0.0,
                 rpm: float = 0.0, vmax_clip: float | None = None,
                 sf_ref: float | None = None) -> str:
    em = ema_analysis.run_em_analysis(geom, N=N, rotor_angle=rotor_angle,
                                       iq=iq, id_=id_, fdm_iters=120,
                                       sf_ref=sf_ref)
    sc, ctr = em["scale"], em["center"]
    B, A    = em["B_mag"], em["A"]

    fig, ax = plt.subplots(figsize=(5.2, 5.2), facecolor="#0d0d0d")
    ax.set_facecolor("#0d0d0d")

    if vmax_clip is not None and vmax_clip > 0:
        vmax = vmax_clip
    else:
        vmax = float(np.percentile(B[B > 1e-4], 98)) if B.max() > 1e-4 else 0.5
    ax.imshow(B, origin="lower", cmap="inferno", vmin=0, vmax=vmax)

    # Field lines — percentile-spaced so equal flux tubes are shown, not equal A increments.
    # This concentrates more lines in the magnetically active regions (air gap, magnet pockets).
    A_flat = A.ravel()
    pcts   = np.linspace(3, 97, 50)
    lvls   = np.unique(np.percentile(A_flat, pcts))
    ax.contour(A, levels=lvls, colors="#00e5ff", linewidths=0.55, alpha=0.80)

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

    title_parts = [f"θ = {math.degrees(rotor_angle):.1f}°"]
    if rpm > 0:
        title_parts.append(f"{rpm:,.0f} U/min".replace(",", "."))
        title_parts.append(f"i_q={iq:.0f} i_d={id_:.0f} A")
    ax.set_title("  |  ".join(title_parts), color="#bbb", fontsize=8, pad=3)
    ax.axis("off")
    fig.tight_layout(pad=0.1)
    return _fig_b64(fig)


# ── Matplotlib charts ─────────────────────────────────────────────────────────

def _airgap_chart(em: dict) -> str:
    fig, ax = plt.subplots(figsize=(7, 2.8), facecolor="#111")
    ax.set_facecolor("#1a1a2e")
    th = np.degrees(em["theta"])
    ax.plot(th, em["Br_gap"], color="#00d4ff", lw=1.8, label="B_r (radial)")
    ax.plot(th, em["Bt_gap"], color="#ff7043", lw=1.2, alpha=0.8, label="B_t (tangential)")
    ax.axhline(0, color="#555", lw=0.5)
    ax.set_xlabel("Winkel [°]", color="#aaa", fontsize=9)
    ax.set_ylabel("B [T]",      color="#aaa", fontsize=9)
    ax.set_title("Luftspaltflussdichte (offen, Rotorwinkel 0°)", color="white", fontsize=9)
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

def _save_cad_images(geom: dict, axial: float, out_root: str) -> dict:
    """Render motor cross-section + side view to <out_root>/cad_images/*.png."""
    import math as _m
    import numpy as np
    from matplotlib.patches import Wedge, Circle
    from matplotlib.patches import Polygon as MplPoly, Patch
    from ema_freecad import _max_magnet_width

    out_dir = os.path.join(out_root, "cad_images")
    os.makedirs(out_dir, exist_ok=True)

    R_rot   = geom["rotorOD"] / 2;  R_shaft = geom["shaftD"] / 2
    R_si    = geom["statorID"] / 2; R_so    = geom["statorOD"] / 2
    n_poles = int(geom["p"]) * 2;   n_slots = int(geom["slots"])
    slot_dep = float(geom["slotDepth"])
    mag_thick = float(geom["magThick"])
    mag_dist_half = float(geom["magDist"]) / 2
    half_angle    = _m.radians(float(geom["magAngle"]) / 2)
    mag_shape     = geom.get("magShape", "v")
    sw_ratio      = float(geom.get("slotWidthRatio", 0.5))
    rPos          = R_shaft + (R_rot - R_shaft) * float(geom["magDepthRel"])
    dtheta_s      = 2 * _m.pi / n_slots
    slot_w        = max(3.0, R_si * dtheta_s * sw_ratio)
    ins, n_layers = 0.8, 2
    cond_w   = max(1.5, slot_w - 2 * ins)
    layer_h  = max(2.0, (slot_dep - 2 - (n_layers + 1) * ins) / n_layers)
    if mag_shape == "v":
        mag_w = min(float(geom.get("magWidth", 35)),
                    _max_magnet_width(rPos, mag_dist_half, half_angle, R_rot))
    else:
        mag_w = float(geom.get("magWidth", 35))

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
    fig, ax = plt.subplots(figsize=(10, 10))
    fig.patch.set_facecolor('#0d1117'); ax.set_facecolor('#0d1117')
    ax.set_aspect('equal'); ax.axis('off')
    lim = R_so * 1.15; ax.set_xlim(-lim, lim); ax.set_ylim(-lim, lim)

    annulus(ax, 0, R_shaft,  '#555555', ec='#888888', lw=1.2)
    annulus(ax, R_shaft, R_rot, '#2d3748', ec='#4a5568', lw=0.8)
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
        cfgs = ([(rPos, +mag_dist_half, +half_angle), (rPos, -mag_dist_half, -half_angle)]
                if mag_shape == "v" else [(rPos, 0.0, _m.pi/2)])
        for sx, sy, ha in cfgs:
            # Arm centre in pole-local frame (start at (sx,sy), extend in direction ha)
            c_h, s_h = _m.cos(ha), _m.sin(ha)
            cx_l = sx + (mag_w / 2) * c_h
            cy_l = sy + (mag_w / 2) * s_h
            hw, hh = mag_w / 2, mag_thick / 2
            local = [(-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh)]
            pole_corners = [(c_h*lx - s_h*ly + cx_l, s_h*lx + c_h*ly + cy_l)
                            for lx, ly in local]
            corners = rot2d(pole_corners, pa)
            fc = '#c0392b' if is_n else '#2980b9'
            ec = '#ff6b6b' if is_n else '#74b9ff'
            mag_patch = MplPoly(corners, closed=True, fc=fc, ec=ec, lw=0.8, alpha=0.9)
            ax.add_patch(mag_patch)
            mag_patch.set_clip_path(_rotor_clip)

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
        C     = rho * omega**2 / 8
        # Max tangential stress at inner bore (Lamé solution)
        sigma_t = C * ((3 + nu) * R**2 + (1 + nu) * r**2) / 1e6  # MPa
        sigma   = sigma_t * Kt
        sf      = Sy / sigma if sigma > 1e-3 else 9999
        out.append({"rpm": rpm,
                    "sigma_max_MPa": round(sigma, 2),
                    "safety_factor": round(sf, 2)})
    return out


# ── Main pipeline ─────────────────────────────────────────────────────────────

_THERMAL_TIME_S = 1800  # 30 min — long enough for housing to approach steady


def run_pipeline(data: dict, state: dict, frames: list,
                  workspace: str, project_dir: str | None = None):
    # When no project_dir is given, fall back to workspace (legacy behaviour)
    proj = project_dir or workspace
    os.makedirs(proj, exist_ok=True)
    for sub in ("cad_images", "charts", "frames"):
        os.makedirs(os.path.join(proj, sub), exist_ok=True)

    geom        = data["geom"]
    rotor_key   = data.get("rotor_lam",  data.get("material", "m270_35a"))
    stator_key  = data.get("stator_lam", rotor_key)
    hp_key      = data.get("hairpin_mat","cu_etp")
    mag_key     = data.get("magnet",     "ndfeb_n35")
    axial       = float(data.get("axial_len",    80.0))
    n_frames    = int(data.get("n_frames",        36))
    fdm_res     = int(data.get("fdm_resolution", 150))
    frame_res   = int(data.get("frame_resolution", 120))
    load_nm     = float(data.get("load_nm",        5.0))
    rpm_from    = float(data.get("rpm_from",    5000.0))
    rpm_to      = float(data.get("rpm_to",     20000.0))
    rpm_step    = float(data.get("rpm_step",    1000.0))
    sweep_rpms  = _rpm_sweep_from_range(rpm_from, rpm_to, rpm_step)
    rpm_fem     = rpm_to   # FEM at maximum speed (worst case)

    # Thermal inputs
    cooling     = str(data.get("cooling",         "water"))
    T_ambient   = float(data.get("T_ambient",     25.0))
    rpm_thermal = float(data.get("rpm_thermal",   rpm_to))     # design point for steady-state

    # Drive-cycle inputs (optional)
    cycle_kind   = str(data.get("cycle",          "wltp3"))    # "wltp3" | "csv" | "off"
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
        # ── 1. FreeCAD geometry (full motor assembly) ─────────────────────────
        _log(state, "⚙ Erzeuge vollständige Motorgeometrie in FreeCAD...", 4)
        fcstd = os.path.join(proj, "motor.FCStd")
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

        # ── 2. EM field (FDM, static at angle 0) ─────────────────────────────
        _log(state, f"🔬 Berechne EM-Feld (FDM {fdm_res}×{fdm_res})...", 22)
        em0    = ema_analysis.run_em_analysis(geom, N=fdm_res, rotor_angle=0.0)
        sf_ref = em0["sf_ref"]   # OC calibration factor — reused for all loaded frames
        perf   = em0["performance"]
        airgap_b64 = _airgap_chart(em0)
        _save_png_b64(airgap_b64, os.path.join(proj, "charts", "airgap.png"))
        results["em"] = {
            "performance":      perf,
            "airgap_chart_b64": airgap_b64,
            "B_gap_data": {
                "theta_deg": np.degrees(em0["theta"]).tolist()[::4],
                "Br_T":      em0["Br_gap"].tolist()[::4],
                "Bt_T":      em0["Bt_gap"].tolist()[::4],
            },
        }
        _log(state,
             f"✓ EM: B_gap = {perf['B_gap_T']:.3f} T | "
             f"Kt = {perf['Kt_Nm_per_A']:.3f} Nm/A | "
             f"Maxwell-Moment ≈ {perf['T_maxwell_Nm']:.1f} Nm", 38)

        # ── 3. Per-RPM field animation (stator currents modelled) ─────────────
        n_rpms     = len(sweep_rpms)
        total_sol  = n_rpms * n_frames
        poles      = int(geom["p"]) * 2
        pole_pitch = 2 * math.pi / poles
        angles     = np.linspace(0, pole_pitch, n_frames, endpoint=False)
        angle_deg  = [round(math.degrees(a), 1) for a in angles]

        _log(state,
             f"🎞 Erzeuge Feldanimation: {n_rpms} Drehzahlen × {n_frames} Frames "
             f"= {total_sol} FDM-Solves (N={frame_res})...", 38)

        # Base speed = first RPM in sweep (field-weakening starts above this)
        rpm_base = float(sweep_rpms[0])

        # First pass at base RPM to determine a stable vmax for consistent colormap
        _iq0, _id0 = ema_analysis.estimate_dq_currents(
            geom, rpm_base, load_nm, b_gap_t=perf["B_gap_T"], rpm_base=rpm_base)
        _em_ref = ema_analysis.run_em_analysis(
            geom, N=frame_res, rotor_angle=0.0, iq=_iq0, id_=_id0)
        _B_ref  = _em_ref["B_mag"]
        vmax_ref = float(np.percentile(_B_ref[_B_ref > 1e-4], 98)) if _B_ref.max() > 1e-4 else 0.5

        rpm_list  = []
        rpm_stats = {}
        solved    = 0

        for rpm in sweep_rpms:
            iq, id_ = ema_analysis.estimate_dq_currents(
                geom, float(rpm), load_nm, b_gap_t=perf["B_gap_T"], rpm_base=rpm_base)
            f_el = float(rpm) * int(geom["p"]) / 60

            rpm_list.append(rpm)
            rpm_stats[rpm] = {
                "iq":   round(iq, 1),
                "id":   round(id_, 1),
                "freq": round(f_el, 1),
            }

            for i, ang in enumerate(angles):
                b64 = _field_frame(
                    geom, float(ang), N=frame_res,
                    iq=iq, id_=id_, rpm=float(rpm), vmax_clip=vmax_ref,
                    sf_ref=sf_ref)
                frames.append(b64)
                # Persist frame to disk: frames/frame_<flatIdx>.png
                _save_png_b64(b64, os.path.join(proj, "frames",
                                                f"frame_{len(frames)-1:04d}.png"))
                solved += 1
                pct = 38 + solved / total_sol * 37
                if solved % max(1, total_sol // 20) == 0 or solved == total_sol:
                    _log(state,
                         f"  RPM {rpm:6.0f} | i_q={iq:.0f} i_d={id_:.0f} A | "
                         f"Frame {i+1}/{n_frames}  [{solved}/{total_sol}]", pct)

        results["em"]["frames_per_rpm"]    = n_frames
        results["em"]["rpm_frame_count"]   = n_frames
        results["em"]["frame_angle_deg"]   = angle_deg
        results["em"]["rpm_list"]          = rpm_list
        results["em"]["rpm_stats"]         = rpm_stats
        results["em"]["n_frames"]          = len(frames)   # total flat count
        _log(state, f"✓ Animation: {len(frames)} Frames für {n_rpms} Drehzahlen", 75)

        # ── 4. EM speed sweep (analytical, for charts) ───────────────────────
        _log(state, "📈 EM-Kennlinie über Drehzahlbereich...", 75)
        from ema_analysis import compute_performance
        em_sweep = [compute_performance(geom, perf["B_gap_T"], float(r)) for r in sweep_rpms]
        results["em"]["speed_sweep"]        = em_sweep
        em_sweep_b64 = _em_sweep_chart(em_sweep)
        _save_png_b64(em_sweep_b64, os.path.join(proj, "charts", "em_curve.png"))
        results["em"]["em_sweep_chart_b64"] = em_sweep_b64
        _log(state, "✓ EM-Kennlinie fertig", 78)

        # ── 5. Structural FEM (CalculiX, single RPM = rpm_to) ────────────────
        _log(state, f"🏗 Strukturanalyse bei {rpm_fem:.0f} U/min (FreeCAD + CalculiX)...", 78)
        code_fem = build_rotor_fem_script(fcstd, rpm_fem, _mat_fc(mat), proj)
        res_fem  = run_freecad_script(code_fem, timeout=600)
        fem_r    = res_fem.get("fem_result", {})

        frd_path = res_fem.get("frd_file", "")
        frd_full = None
        if frd_path and frd_path != "MISSING" and fem_r.get("solver_status") == "FRD_READY":
            frd_full = _parse_frd_full(frd_path, yield_mpa=mat["yield_mpa"])
            fem_r = {k: v for k, v in frd_full.items() if not k.startswith("_")}

        if fem_r and fem_r.get("max_von_mises_MPa"):
            sig  = fem_r["max_von_mises_MPa"]
            sf_v = fem_r.get("safety_factor") or (mat["yield_mpa"] / sig if sig > 0 else None)
            fem_r.update({"safety_factor": round(sf_v, 2) if sf_v else None,
                          "yield_mpa": mat["yield_mpa"],
                          "material":  mat["label"],
                          "rpm":       rpm_fem})
            u_um = fem_r.get("max_displacement_um", "?")
            _log(state,
                 f"✓ FEM: σ_v,max = {sig:.1f} MPa | SF = {sf_v:.2f} | "
                 f"u_max = {u_um} µm", 88)
        else:
            fem_r = {"solver_status": "FAILED",
                     "log": res_fem.get("stdout", "")[:400],
                     "rpm": rpm_fem}
            frd_full = None
            _log(state,
                 "⚠ CalculiX fehlgeschlagen – analytische Näherung verfügbar", 88)
        results["structural_fem"] = fem_r

        # ── 5b. FEM deformation plot ──────────────────────────────────────────
        deform_result = {"chart_b64": "", "stats": {}}
        if frd_full and frd_full.get("_nodes"):
            try:
                chart_b64, deform_stats = _fem_deformation_plot(frd_full, geom, rpm_fem)
                _save_png_b64(chart_b64, os.path.join(proj, "charts", "deformation.png"))
                deform_result = {"chart_b64": chart_b64, "stats": deform_stats}
                _log(state,
                     f"✓ Verformungsplot: u_max={deform_stats.get('u_max_um','?')} µm, "
                     f"Skalierung ×{deform_stats.get('scale_factor','?')}", 91)
            except Exception as _de:
                _log(state, f"⚠ Verformungsplot fehlgeschlagen: {_de}", 91)
        results["deformation"] = deform_result

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
            (s["rpm"] for s in reversed(struct_sweep) if s["safety_factor"] >= 1.5),
            struct_sweep[0]["rpm"]
        )
        _log(state, f"✓ Strukturkennlinie: max. sichere Drehzahl ≈ {max_safe_rpm:.0f} U/min", 93)

        # ── 7. Thermal LPTN analysis ──────────────────────────────────────────
        _log(state, f"🌡 Thermisches Modell ({cooling}, {T_ambient}°C Umgebung)...", 93)
        try:
            therm = ema_thermal.run_thermal_analysis(
                geom, axial, rpm_thermal, load_nm, perf,
                mat, st_mat, hp_mat, mag,
                cooling=cooling, T_amb=T_ambient, t_max=_THERMAL_TIME_S)
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
        except Exception as _te:
            _log(state, f"⚠ Thermal-Analyse fehlgeschlagen: {_te}", 96)
            results["thermal"] = {"error": str(_te)}

        # ── 8. Drive-cycle analysis (optional) ────────────────────────────────
        if cycle_kind != "off":
            vehicle    = {**ema_drivecycle.DEFAULT_VEHICLE, **vehicle_in}

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
                elif cycle_kind == "anhaenger":
                    cyc_primary = ema_drivecycle.trailer_mountain_cycle()
                    veh_primary = ema_drivecycle.trailer_vehicle(vehicle)
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
                    cyc_ah = ema_drivecycle.trailer_mountain_cycle()
                    veh_ah = ema_drivecycle.trailer_vehicle(vehicle)
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
            "rotor_lam":       mat["label"],
            "stator_lam":      st_mat["label"],
            "hairpin":         hp_mat["label"],
            "magnet":          mag["label"],
            "mass_g":          results["geometry"]["mass_g"],
            "fill_factor":     fill_factor,
            "P_fe_W_est":      round(P_fe_W, 1),
            "T_winding_C":     ss.get("T_winding"),
            "T_magnet_C":      ss.get("T_magnet"),
            "T_housing_C":     ss.get("T_housing"),
            "P_total_W":       losses_summary.get("P_total"),
            "cooling":         therm_summary.get("cooling_label", ""),
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
            }
            with open(os.path.join(proj, "meta.json"), "w") as f:
                json.dump(meta, f, indent=2, ensure_ascii=False)
            with open(os.path.join(proj, "results.json"), "w") as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            _log(state, f"💾 Projekt gespeichert: {proj}", 99)
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
