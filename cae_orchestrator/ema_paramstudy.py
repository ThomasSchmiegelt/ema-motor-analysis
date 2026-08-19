"""Parameter study at a FIXED speed.

The user picks ONE parameter and a range [x, y]; the study evaluates the design at
``steps`` (default 100) equally-spaced values of that parameter while everything else
(including the speed) is held fixed, and plots every result metric over the parameter.
This makes the influence of e.g. a magnet-angle change directly visible.

Because 100 evaluations would be far too slow with FreeCAD + FEM, the study reuses the
FreeCAD/FEM-FREE fast evaluator from ``ema_optimize`` (EM field at low resolution →
analytical torque/Kt, steady-state LPTN thermal, analytical structural sweep + mass,
~0.5 s each). Geometry IS varied — the chosen parameter changes the analytical model
exactly as it would the real geometry; only the expensive meshing/solve is skipped.
"""

import io
import math

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

import ema_optimize as O

# Metrics shown in the study, in plot order: (metric key, label, unit)
_STUDY_METRICS = [
    ("Kt",           "Kt",                 "Nm/A"),
    ("T_maxwell",    "Maxwell-Moment",     "Nm"),
    ("B_gap",        "B_gap (Peak)",       "T"),
    ("max_safe_rpm", "max. sichere Drehzahl", "U/min"),
    ("mass_g",       "Aktivteil-Masse",    "g"),
    ("T_magnet",     "T_Magnet",           "°C"),
    ("T_winding",    "T_Wicklung",         "°C"),
    ("P_total",      "Verluste P_ges",     "W"),
]


def _fig_b64(fig, dpi=120):
    import base64
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def run_study(payload, param, lo, hi, steps=100, rpm=None,
              field_frames=0, field_N=160, out_dir=None, progress_cb=None):
    """Sweep one parameter from ``lo`` to ``hi`` in ``steps`` points at a FIXED speed.

    If ``field_frames`` ≥ 2, the FDM magnetic field (with flux lines) is additionally
    rendered at that many parameter values sampled across [lo, hi] — returned as
    base64 images and, if ``out_dir`` is given + ffmpeg is available, assembled into a
    video (``<out_dir>/anim.mp4``).

    Returns a dict: {param, label, rpm, x:[…], metrics:{key:[…]}, chart_b64, n_ok,
    n_fail, field_images:[{value,b64}], field_video:bool}.
    """
    def log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    spec = O.FREE_PARAMS.get(param)
    if spec is None:
        raise ValueError(f"Unbekannter Parameter: {param}")
    lo, hi = float(lo), float(hi)
    steps = max(2, min(500, int(steps)))
    if hi == lo:
        raise ValueError("Bereich x..y darf nicht leer sein (x ≠ y)")

    base_geom  = payload["geom"]
    base_axial = float(payload.get("axial_len", base_geom.get("axialLen", 80)))
    mats       = O._materials(payload)
    cooling    = payload.get("cooling", "water")
    T_amb      = float(payload.get("T_ambient", 25))

    # Fixed operating speed: the study speed (falls back to rpm_to). The field-
    # weakening threshold (rpm_base) is kept from the payload so the dq-current
    # operating point is physical at the chosen speed.
    rpm_fix = float(rpm if rpm not in (None, "", 0) else payload.get("rpm_to", 20000))
    op = {"rpm_thermal": rpm_fix,
          "rpm_base":    float(payload.get("rpm_from", 5000)),
          "load_nm":     float(payload.get("load_nm", 5))}
    rpm_hi     = float(payload.get("rpm_to", 20000))
    sweep_rpms = [round(rpm_hi * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]

    cast = spec["type"]
    xs, metric_series = [], {k: [] for k, _, _ in _STUDY_METRICS}
    n_ok = n_fail = 0
    label = spec["label"]
    log(f"Parameterstudie: {label}  {lo:g} → {hi:g} in {steps} Schritten @ {rpm_fix:.0f} U/min", 2)

    for i in range(steps):
        val = lo + (hi - lo) * i / (steps - 1)
        val = cast(val)
        m = O.evaluate_fast(base_geom, base_axial, {param: val}, mats, op,
                            cooling, T_amb, sweep_rpms)
        xs.append(val)
        if "error" in m:
            n_fail += 1
            for k in metric_series:
                metric_series[k].append(None)
        else:
            n_ok += 1
            for k in metric_series:
                metric_series[k].append(m.get(k))
        if (i + 1) % max(1, steps // 20) == 0 or i + 1 == steps:
            log(f"  [{i+1}/{steps}]  {label}={val:g}", 2 + int(95 * (i + 1) / steps))

    chart_b64 = _build_chart(xs, metric_series, label, spec.get("type") is int, rpm_fix)

    field_images, field_video = [], False
    field_frames = int(field_frames or 0)
    if field_frames >= 2:
        field_images, field_video = _render_field_series(
            base_geom, base_axial, param, lo, hi, field_frames, cast,
            mats[3], op, rpm_fix, float(payload.get("field_bmax", 0) or 0),
            int(field_N), out_dir, label, log)

    log(f"✓ Fertig: {n_ok} ausgewertet, {n_fail} fehlgeschlagen", 100)
    return {
        "param":    param,
        "label":    label,
        "rpm":      rpm_fix,
        "x":        xs,
        "metrics":  metric_series,
        "metric_meta": [{"key": k, "label": l, "unit": u} for k, l, u in _STUDY_METRICS],
        "chart_b64": chart_b64,
        "n_ok":     n_ok,
        "n_fail":   n_fail,
        "steps":    steps,
        "field_images": field_images,
        "field_video":  field_video,
    }


# A smooth video may use hundreds of frames (like the main animations), but ALL of
# them as base64 in the polled JSON result would be huge — so the returned gallery is
# capped to an evenly-spaced sample; the VIDEO uses every rendered frame.
_GALLERY_MAX = 24


def _render_field_series(base_geom, base_axial, param, lo, hi, n_frames, cast,
                         mag, op, rpm_fix, field_bmax, field_N, out_dir, label, log):
    """Render the FDM field (with flux lines) at n_frames parameter values across
    [lo,hi]. ALL frames go to disk → mp4 (for a smooth video); only an evenly-spaced
    sample (≤ _GALLERY_MAX) is returned as base64 for the on-page gallery."""
    import os
    import ema_analysis
    import ema_pipeline as P

    if out_dir:
        # fresh frame dir so an old study's frames never leak into the video
        for fn in (os.listdir(out_dir) if os.path.isdir(out_dir) else []):
            if fn.startswith("frame_") or fn == "anim.mp4":
                try: os.remove(os.path.join(out_dir, fn))
                except OSError: pass
        os.makedirs(out_dir, exist_ok=True)

    # which frame indices are kept as base64 for the gallery (evenly spaced)
    if n_frames <= _GALLERY_MAX:
        gallery_idx = set(range(n_frames))
    else:
        gallery_idx = {round(i * (n_frames - 1) / (_GALLERY_MAX - 1))
                       for i in range(_GALLERY_MAX)}

    images, n_disk = [], 0
    # Magnet remanence/permeability for the FDM solve (same monkey-patch pattern as
    # run_pipeline / evaluate_fast), restored in the finally block.
    _Br, _mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = mag["Br"], mag["mu_r"]
    try:
        for j in range(n_frames):
            val = cast(lo + (hi - lo) * j / (n_frames - 1))
            geom, _ax = O._apply_params(base_geom, base_axial, {param: val})
            try:
                em0   = ema_analysis.run_em_analysis(geom, N=min(field_N, 160), rotor_angle=0.0)
                b_gap = em0["performance"]["B_gap_T"]
                iq, id_ = ema_analysis.estimate_dq_currents(
                    geom, rpm_fix, op["load_nm"], b_gap_t=b_gap, rpm_base=op["rpm_base"])
                b64 = P._field_frame(geom, 0.0, N=field_N, iq=iq, id_=id_, rpm=rpm_fix,
                                     out_px=1100, saturate=True, b_ceiling=field_bmax,
                                     magnet_outlines=True)
                if out_dir:                       # every frame → disk for the video
                    P._save_png_b64(b64, os.path.join(out_dir, f"frame_{n_disk:04d}.png"))
                    n_disk += 1
                if j in gallery_idx:              # only a sample → returned gallery
                    images.append({"value": val, "b64": b64})
            except Exception as e:
                log(f"  ⚠ Feldbild bei {label}={val:g} fehlgeschlagen: {e}")
            if (j + 1) % max(1, n_frames // 20) == 0 or j + 1 == n_frames:
                log(f"  Feldlinien [{j+1}/{n_frames}]  {label}={val:g}")
    finally:
        ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = _Br, _mu
        ema_analysis.clear_lu_cache()

    # fps scaled so the clip lasts ~a handful of seconds regardless of frame count
    fps = max(6, min(25, round(n_disk / 6))) if n_disk else 6
    video = bool(out_dir and n_disk >= 2 and P._make_video(out_dir, fps=fps))
    return images, video


def _build_chart(xs, series, xlabel, x_is_int, rpm_fix):
    """Small-multiples grid: one panel per metric, value over the parameter."""
    specs = [(k, l, u) for k, l, u in _STUDY_METRICS if any(v is not None for v in series[k])]
    if not specs:
        specs = _STUDY_METRICS
    n = len(specs)
    cols = 2
    rows = math.ceil(n / cols)
    fig, axes = plt.subplots(rows, cols, figsize=(11, 2.6 * rows), facecolor="#0d1117")
    axes = axes.flatten() if hasattr(axes, "flatten") else [axes]

    for ax, (key, label, unit) in zip(axes, specs):
        ys = series[key]
        px = [x for x, y in zip(xs, ys) if y is not None]
        py = [y for y in ys if y is not None]
        ax.set_facecolor("#161b22")
        if px:
            ax.plot(px, py, color="#58a6ff", lw=1.8, marker="o", ms=2.5, mfc="#58a6ff", mec="none")
        ax.set_title(f"{label}", color="#ddd", fontsize=9, pad=4)
        ax.set_xlabel(xlabel, color="#999", fontsize=7.5)
        ax.set_ylabel(unit, color="#999", fontsize=7.5)
        ax.tick_params(colors="#888", labelsize=7)
        for s in ax.spines.values():
            s.set_color("#30363d")
        ax.grid(True, color="#21262d", lw=0.6)

    for ax in axes[n:]:
        ax.axis("off")

    fig.suptitle(f"Parameterstudie über {xlabel}  @ {rpm_fix:,.0f} U/min".replace(",", "."),
                 color="#eee", fontsize=11, y=1.0)
    fig.tight_layout(rect=(0, 0, 1, 0.98))
    return _fig_b64(fig)
