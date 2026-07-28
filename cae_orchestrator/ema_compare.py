"""Variant comparison: load 2–4 project results.json and produce overlay charts."""

from __future__ import annotations
import os, json, io, base64
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.cm as cm
import matplotlib.colors as mcolors

MAX_VARIANTS = 10

# Up to 10 distinct, consistent variant colours across all comparison charts.
_CMAP = cm.get_cmap("tab10")


def _vcolor(i: int):
    return _CMAP(i % 10)


def _vhex(i: int) -> str:
    return mcolors.to_hex(_vcolor(i))


def _legend_ncol(n: int) -> int:
    return 1 if n <= 4 else (2 if n <= 8 else 3)


def _fig_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight",
                 facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def load_projects(projects_root: str, ids: list[str]) -> list[dict]:
    """Load results.json + meta.json for each id. Skip missing."""
    out = []
    for pid in ids[:MAX_VARIANTS]:
        path = os.path.join(projects_root, pid)
        rfile = os.path.join(path, "results.json")
        mfile = os.path.join(path, "meta.json")
        if not os.path.exists(rfile):
            continue
        try:
            with open(rfile) as f: results = json.load(f)
            meta = {}
            if os.path.exists(mfile):
                with open(mfile) as f: meta = json.load(f)
            out.append({"id": pid, "results": results, "meta": meta})
        except Exception:
            continue
    return out


# ── Chart 1: EM + structural sweep overlays ──────────────────────────────────

def chart_kennlinien(variants: list[dict]) -> str:
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), facecolor="#111")
    for ax in axes.flat:
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#aaa", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")
        ax.grid(color="#333", lw=0.4)

    ax_emf, ax_kt, ax_sig, ax_eta = axes.flat

    n = len(variants)
    for i, v in enumerate(variants):
        col   = _vcolor(i)
        lbl   = v["meta"].get("label", v["id"])[:24]
        em    = v["results"].get("em", {}) or {}
        sweep = em.get("speed_sweep", []) or []
        struct = v["results"].get("structural_sweep", []) or []
        cyc   = v["results"].get("drivecycle", {}) or {}

        if sweep:
            rpms = [s["rpm"]         for s in sweep]
            emf  = [s["emf_rms_V"]   for s in sweep]
            kt   = [s["Kt_Nm_per_A"] for s in sweep]
            ax_emf.plot(rpms, emf, color=col, lw=2, marker="o", markersize=4, label=lbl)
            ax_kt .plot(rpms, kt,  color=col, lw=2, marker="o", markersize=4, label=lbl)
        if struct:
            rpms = [s["rpm"]           for s in struct]
            sig  = [s["sigma_max_MPa"] for s in struct]
            ax_sig.plot(rpms, sig, color=col, lw=2, marker="o", markersize=4, label=lbl)

        if cyc and not cyc.get("error"):
            ax_eta.bar(i, cyc.get("E_per_100km_kWh", 0), color=col, edgecolor="#222",
                       label=lbl)

    ax_emf.set_title("Strangspannung EMK (eff.)", color="white", fontsize=10)
    ax_emf.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=9)
    ax_emf.set_ylabel("U_rms [V]",        color="#aaa", fontsize=9)
    ax_emf.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.85,
                  ncol=_legend_ncol(n), loc="best")

    ax_kt.set_title("Drehmomentkonstante Kt", color="white", fontsize=10)
    ax_kt.set_xlabel("Drehzahl [U/min]",      color="#aaa", fontsize=9)
    ax_kt.set_ylabel("Kt [Nm/A_pk]",          color="#aaa", fontsize=9)

    # Yield-grenze auf σ-Plot der ersten Variante (Material kann variieren)
    if variants:
        fem = variants[0]["results"].get("structural_fem", {}) or {}
        if fem.get("yield_mpa"):
            ax_sig.axhline(fem["yield_mpa"], color="#e74c3c", lw=1, ls="--",
                            label=f"Re = {fem['yield_mpa']} MPa (Var. 1)")
    ax_sig.set_title("Spannung σ_v,max", color="white", fontsize=10)
    ax_sig.set_xlabel("Drehzahl [U/min]", color="#aaa", fontsize=9)
    ax_sig.set_ylabel("σ [MPa]",          color="#aaa", fontsize=9)
    ax_sig.legend(facecolor="#222", labelcolor="white", fontsize=6, framealpha=0.85,
                  ncol=_legend_ncol(n), loc="best")

    ax_eta.set_title("Verbrauch WLTP / Custom", color="white", fontsize=10)
    ax_eta.set_xticks(range(len(variants)))
    ax_eta.set_xticklabels([f"V{i+1}" for i in range(len(variants))], color="#aaa")
    ax_eta.set_ylabel("kWh/100 km", color="#aaa", fontsize=9)
    for i, v in enumerate(variants):
        cyc = v["results"].get("drivecycle", {}) or {}
        val = cyc.get("E_per_100km_kWh", 0)
        ax_eta.text(i, val + 0.3, f"{val:.1f}" if val else "—",
                    ha="center", color="white", fontsize=8)

    fig.suptitle("Variantenvergleich · EM & Strukturkennlinien",
                 color="white", fontsize=12, y=0.995)
    fig.tight_layout()
    return _fig_b64(fig)


# ── Chart 2: Thermal + loss breakdown ────────────────────────────────────────

def chart_thermal_energy(variants: list[dict]) -> str:
    fig, (ax_T, ax_E) = plt.subplots(1, 2, figsize=(13, 4.5), facecolor="#111")
    for ax in (ax_T, ax_E):
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#aaa", labelsize=8)
        for sp in ax.spines.values(): sp.set_color("#444")

    n = len(variants)
    x = np.arange(n)
    w = 0.22

    # Grouped bars: T_winding, T_magnet, T_housing
    Tw = [(v["results"].get("thermal", {}) or {}).get("steady", {}).get("T_winding", 0) for v in variants]
    Tm = [(v["results"].get("thermal", {}) or {}).get("steady", {}).get("T_magnet",  0) for v in variants]
    Th = [(v["results"].get("thermal", {}) or {}).get("steady", {}).get("T_housing", 0) for v in variants]
    ax_T.bar(x - w,  Tw, w, color="#ff6b35", label="Wicklung")
    ax_T.bar(x,      Tm, w, color="#e74c3c", label="Magnet")
    ax_T.bar(x + w,  Th, w, color="#1abc9c", label="Gehäuse")
    ax_T.axhline(150, color="#f39c12", lw=0.8, ls=":", label="Magnet-Limit 150°C")
    ax_T.axhline(180, color="#e74c3c", lw=0.8, ls=":", label="Klasse-H 180°C")
    ax_T.set_xticks(x)
    ax_T.set_xticklabels([f"V{i+1}\n{(variants[i]['meta'].get('label') or '')[:14]}"
                          for i in range(n)], color="#aaa", fontsize=8)
    ax_T.set_ylabel("T [°C]", color="#aaa", fontsize=9)
    ax_T.set_title("Endtemperaturen (steady state)", color="white", fontsize=10)
    ax_T.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.85, ncol=2)

    # Stacked energy bars
    labels = ["Cu", "Fe", "Magnet", "Lager"]
    colors_e = ["#ff6b35", "#3498db", "#e74c3c", "#95a5a6"]
    bottom = np.zeros(n)
    for lbl, col, key in zip(labels, colors_e,
                              ["E_Cu_Wh","E_Fe_Wh","E_Mag_Wh","E_Bear_Wh"]):
        vals = [(v["results"].get("drivecycle", {}) or {}).get("losses", {}).get(key, 0)
                for v in variants]
        ax_E.bar(x, vals, 0.55, bottom=bottom, color=col, label=lbl,
                  edgecolor="#222", lw=0.8)
        bottom += np.array(vals)
    # Mech-Energie als helle Säule oben drüber zum Vergleich
    mech = [(v["results"].get("drivecycle", {}) or {}).get("E_mech_drv_Wh", 0)
            for v in variants]
    ax_E.bar(x, mech, 0.55, bottom=bottom, color="#0d4a6e", alpha=0.7,
              label="Nutzenergie", edgecolor="#222", lw=0.8)

    ax_E.set_xticks(x)
    ax_E.set_xticklabels([f"V{i+1}" for i in range(n)], color="#aaa")
    ax_E.set_ylabel("Energie [Wh]", color="#aaa", fontsize=9)
    ax_E.set_title("Energie-Aufteilung im Fahrzyklus", color="white", fontsize=10)
    ax_E.legend(facecolor="#222", labelcolor="white", fontsize=7, framealpha=0.85, ncol=2)

    fig.suptitle("Variantenvergleich · Thermisch + Energie",
                 color="white", fontsize=12, y=0.995)
    fig.tight_layout()
    return _fig_b64(fig)


# ── Side-by-side summary table ───────────────────────────────────────────────

def summary_table(variants: list[dict]) -> dict:
    """Build a list of row dicts: {label, values[v1,v2,...], unit}."""
    rows: list[dict] = []

    def row(label, key, unit="", fmt=lambda v: v, src="summary"):
        vals = []
        for v in variants:
            d = v["results"].get(src, {}) or {}
            x = d.get(key) if not isinstance(key, list) else None
            if isinstance(key, list):
                # nested lookup
                cur = v["results"]
                for k in key:
                    cur = (cur or {}).get(k) if isinstance(cur, dict) else None
                x = cur
            try:
                vals.append(fmt(x) if x is not None else "—")
            except Exception:
                vals.append(str(x) if x is not None else "—")
        rows.append({"label": label, "values": vals, "unit": unit})

    # Project / meta
    rows.append({"label": "Projekt",      "unit": "",
                 "values": [v["meta"].get("label", v["id"])[:30] for v in variants]})
    rows.append({"label": "Erstellt",     "unit": "",
                 "values": [v["meta"].get("created", "")[:19] for v in variants]})

    # EM
    row("B_gap (Peak)",     "B_gap_T",        "T",     lambda v: f"{v:.3f}")
    row("Kt",               "Kt_Nm_per_A",    "Nm/A",  lambda v: f"{v:.3f}")
    row("Maxwell-Moment",   "T_maxwell_Nm",   "Nm",    lambda v: f"{v:.1f}")
    row("LCM Nuten/Pole",   "lcm_slots_poles","")

    # Mass & Material
    row("Rotor-Masse",      "mass_g",         "g",     lambda v: f"{v:.0f}")
    row("Rotorblech",       "rotor_lam",      "")
    row("Statorblech",      "stator_lam",     "")
    row("Hairpin-Leiter",   "hairpin",        "")
    row("Magnet",           "magnet",         "")

    # Structural
    row("Max. sichere RPM", "max_safe_rpm",   "U/min", lambda v: f"{v:,.0f}")

    # Thermal
    row("T_Wicklung",       "T_winding_C",    "°C",    lambda v: f"{v:.1f}")
    row("T_Magnet",         "T_magnet_C",     "°C",    lambda v: f"{v:.1f}")
    row("T_Gehäuse",        "T_housing_C",    "°C",    lambda v: f"{v:.1f}")
    row("P_Verluste",       "P_total_W",      "W",     lambda v: f"{v:.0f}")
    row("Kühlung",          "cooling",        "")

    # Drive cycle
    row("Zyklus",           "cycle_name",     "")
    row("Verbrauch",        "cycle_kWh100km", "kWh/100km", lambda v: f"{v:.2f}")
    row("η_drive",          "cycle_eta",      "%",     lambda v: f"{v*100:.1f}")

    return {"rows": rows,
            "variants": [{"id": v["id"],
                          "label": v["meta"].get("label", v["id"])[:30],
                          "color": _vhex(i)}
                         for i, v in enumerate(variants)]}


def run_compare(projects_root: str, ids: list[str]) -> dict:
    variants = load_projects(projects_root, ids)
    if len(variants) < 1:
        return {"error": "Keine gültigen Projekte gefunden"}
    return {
        "n_variants":   len(variants),
        "ids":          [v["id"] for v in variants],
        "table":        summary_table(variants),
        "kennlinien_b64": chart_kennlinien(variants),
        "thermal_b64":    chart_thermal_energy(variants),
    }
