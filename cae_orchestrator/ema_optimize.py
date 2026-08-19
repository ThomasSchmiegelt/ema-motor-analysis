"""Target-value optimisation: LLM-steered search over a fast analytical evaluator.

The user fixes hard CONSTRAINTS (must hold), FREE parameters with ranges (may be
changed), and an OBJECTIVE metric (maximise / minimise / hit a target). Each
candidate design is scored by a FreeCAD/FEM-FREE fast evaluator (~0.5 s): EM field
at low resolution → analytical Kt / torque, steady-state LPTN thermal, analytical
structural sweep, analytical mass. A local LLM (see ema_report.DEFAULT_MODEL) reads the
(params→metrics) history and proposes the next batch of candidates; deterministic
clamping + feasibility filtering keep it safe. The best feasible design is returned
so the caller can run the FULL pipeline once on the winner.

There is no LLM in the analysis itself — the LLM only steers the search.
"""

import json
import math
import random
import re
import urllib.request

import ema_analysis
import ema_thermal
from ema_report import OLLAMA_URL, DEFAULT_MODEL

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# ── Free parameters the optimiser may vary ───────────────────────────────────
# key → geom field (or special), label, default range, numeric type
FREE_PARAMS = {
    "magWidth":    {"geom": "magWidth",    "label": "Magnet-Länge [mm]",      "lo": 3,   "hi": 300, "type": float},
    "magThick":    {"geom": "magThick",    "label": "Magnet-Dicke [mm]",      "lo": 1,   "hi": 60,  "type": float},
    "magAngle":    {"geom": "magAngle",    "label": "Öffnungswinkel [°]",     "lo": 40,  "hi": 170, "type": float},
    "magAsym":     {"geom": "magAsym",     "label": "Asymmetrie V [°]",       "lo": -60, "hi": 60,  "type": float},
    "magDist":     {"geom": "magDist",     "label": "Steg-Abstand [mm]",      "lo": 0,   "hi": 80,  "type": float},
    "magDepthRel": {"geom": "magDepthRel", "label": "Position (Radius) [0–1]","lo": 0.3, "hi": 0.95,"type": float},
    "slotDepth":   {"geom": "slotDepth",   "label": "Nuttiefe [mm]",          "lo": 2,   "hi": 150, "type": float},
    "p":           {"geom": "p",           "label": "Polpaare",               "lo": 1,   "hi": 40,  "type": int},
    "axial":       {"special": "axial",    "label": "Blechpaketlänge [mm]",   "lo": 5,   "hi": 600, "type": float},
    "airgap":      {"special": "airgap",   "label": "Luftspalt Stator-Rotor [mm]", "lo": 0.1, "hi": 3.0, "type": float},
    "magGap":      {"geom": "magGapMm",    "label": "Magnet-Luftspalt [mm]",  "lo": 0.05,"hi": 0.3, "type": float},
}

# Metrics the evaluator produces (objective / constraints pick from these)
METRICS = {
    "Kt":           {"label": "Kt [Nm/A]",            "unit": "Nm/A"},
    "T_maxwell":    {"label": "Maxwell-Moment [Nm]",  "unit": "Nm"},
    "B_gap":        {"label": "B_gap [T]",            "unit": "T"},
    "max_safe_rpm": {"label": "max. sichere Drehzahl","unit": "U/min"},
    "mass_g":       {"label": "Rotor+Magnet-Masse",   "unit": "g"},
    "T_magnet":     {"label": "T_Magnet",             "unit": "°C"},
    "T_winding":    {"label": "T_Wicklung",           "unit": "°C"},
    "P_total":      {"label": "Verluste P_ges",       "unit": "W"},
}


def _materials(payload):
    import ema_pipeline as P
    mat    = P.LAMINATES.get(payload.get("rotor_lam", "m270_35a"),  P.LAMINATES["m270_35a"])
    st_mat = P.LAMINATES.get(payload.get("stator_lam", "m270_35a"), P.LAMINATES["m270_35a"])
    hp_mat = P.HAIRPIN_MATS.get(payload.get("hairpin_mat", "cu_etp"), P.HAIRPIN_MATS["cu_etp"])
    mag    = P.MAGNETS.get(payload.get("magnet", "ndfeb_n35"),       P.MAGNETS["ndfeb_n35"])
    return mat, st_mat, hp_mat, mag


def _clamp(params):
    out = {}
    for k, v in params.items():
        spec = FREE_PARAMS.get(k)
        if spec is None or v is None:
            continue
        try:
            v = spec["type"](v)
        except (TypeError, ValueError):
            continue
        out[k] = max(spec["lo"], min(spec["hi"], v))
    return out


def _apply_params(base_geom, base_axial, params):
    geom = dict(base_geom)
    axial = float(base_axial)
    for k, v in params.items():
        spec = FREE_PARAMS.get(k)
        if not spec:
            continue
        if spec.get("special") == "axial":
            axial = float(v)
        elif spec.get("special") == "airgap":
            # stator-rotor air gap drives the stator bore: statorID = rotorOD + 2·gap
            geom["statorID"] = float(geom["rotorOD"]) + 2.0 * float(v)
        else:
            geom[spec["geom"]] = spec["type"](v)
    return geom, axial


def _eval_geom(geom, axial, mats, op, cooling, T_amb, sweep_rpms, N=140):
    """FreeCAD/FEM-free metric evaluation for an ALREADY-built geometry dict.

    This is the shared evaluation core: EM field at low resolution → analytical
    Kt/torque, steady-state LPTN thermal, analytical mass + structural sweep.
    ``evaluate_fast`` (parametric search) and the per-magnet layout optimiser
    (``ema_design_optimize``) both call this so the metrics stay identical. Works
    for any ``magShape`` incl. ``"custom"`` (the custom legs/barriers in ``geom``
    are honoured by ``run_em_analysis`` unchanged)."""
    mat, st_mat, hp_mat, mag = mats
    _Br, _mu = ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG
    ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = mag["Br"], mag["mu_r"]
    try:
        em   = ema_analysis.run_em_analysis(geom, N=N, rotor_angle=0.0)
        perf = em["performance"]
        rpm_t   = op["rpm_thermal"]
        iq, id_ = ema_analysis.estimate_dq_currents(
            geom, rpm_t, op["load_nm"], b_gap_t=perf["B_gap_T"], rpm_base=op["rpm_base"])
        losses = ema_thermal.compute_losses(geom, axial, rpm_t, iq, id_, perf,
                                            mat, st_mat, hp_mat, mag)
        G  = ema_thermal.conductances(geom, axial, cooling, rpm_t)
        Tn = ema_thermal.solve_steady(G, losses, T_amb)
        caps = ema_thermal.compute_capacities(geom, axial, mat, st_mat, hp_mat, mag)
        masses = caps["_masses_g"]
        mass = float(masses.get("rotor", 0) + masses.get("magnet", 0))
        import ema_pipeline as P
        ss = P._struct_sweep(geom, mat, sweep_rpms)
        max_safe = next((s["rpm"] for s in reversed(ss) if s["safety_factor"] >= 1.5),
                        ss[0]["rpm"])
        return {
            "Kt":           round(perf["Kt_Nm_per_A"], 4),
            "T_maxwell":    round(perf.get("T_maxwell_Nm", 0.0), 2),
            "B_gap":        round(perf["B_gap_T"], 4),
            "max_safe_rpm": round(float(max_safe), 0),
            "mass_g":       round(mass, 0),
            "T_magnet":     round(Tn["T_magnet"], 1),
            "T_winding":    round(Tn["T_winding"], 1),
            "P_total":      round(losses["P_total"], 1),
        }
    except Exception as e:
        return {"error": str(e)[:160]}
    finally:
        ema_analysis.Br_NdFeB, ema_analysis.MU_R_MAG = _Br, _mu


def evaluate_fast(base_geom, base_axial, params, mats, op,
                  cooling, T_amb, sweep_rpms, N=140):
    """FreeCAD/FEM-free metric evaluation for one candidate parameter set."""
    geom, axial = _apply_params(base_geom, base_axial, params)
    return _eval_geom(geom, axial, mats, op, cooling, T_amb, sweep_rpms, N=N)


# ── feasibility + fitness ────────────────────────────────────────────────────

def _violation(metrics, constraints):
    """0 if all constraints hold, else a positive normalised total violation."""
    if "error" in metrics:
        return 1e9
    tot = 0.0
    for c in constraints:
        val = metrics.get(c["metric"])
        if val is None:
            continue
        v, lim = float(val), float(c["value"])
        scale = abs(lim) if abs(lim) > 1e-6 else 1.0
        if c["op"] == ">=" and v < lim:
            tot += (lim - v) / scale
        elif c["op"] == "<=" and v > lim:
            tot += (v - lim) / scale
    return tot


def _fitness(metrics, objective, constraints):
    """Higher = better. Infeasible designs rank below every feasible one."""
    viol = _violation(metrics, constraints)
    if "error" in metrics:
        return -1e12
    if viol > 1e-9:
        return -1e9 - viol
    val = metrics.get(objective["metric"])
    if val is None:
        return -1e9
    val = float(val)
    goal = objective.get("goal", "max")
    if goal == "min":
        return -val
    if goal == "target":
        return -abs(val - float(objective.get("target", val)))
    return val


# ── LLM proposal ─────────────────────────────────────────────────────────────

def _ollama_chat(messages, timeout=120):
    body = json.dumps({"model": DEFAULT_MODEL, "messages": messages, "stream": False,
                       "think": False,          # s. ema_report.call_ollama
                       "options": {"temperature": 0.6, "num_ctx": 12288, "num_predict": 900}}).encode()
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    return _THINK_RE.sub("", (resp.get("message", {}) or {}).get("content", "")).strip()


def _extract_array(txt):
    m = re.search(r"\[.*\]", txt, re.DOTALL)
    if not m:
        return []
    try:
        arr = json.loads(m.group(0))
        return [a for a in arr if isinstance(a, dict)]
    except Exception:
        return []


def _random_params(free):
    return {f["param"]: round(random.uniform(f["min"], f["max"]), 4) for f in free}


def _llm_propose(objective, constraints, free, history, k):
    ranges = {f["param"]: [f["min"], f["max"]] for f in free}
    # compact history: only params + objective metric + feasibility
    hist = [{"params": h["params"],
             "metrics": {mk: h["metrics"].get(mk) for mk in
                         ({objective["metric"]} | {c["metric"] for c in constraints})
                         if mk in h["metrics"]},
             "feasible": h["feasible"]}
            for h in history[-18:]]
    sys = (
        "Du bist ein Optimierungs-Assistent für E-Maschinen-Auslegung. Du schlägst "
        "neue Parameter-Kandidaten vor, um ein Ziel zu erreichen.\n"
        f"FREIE PARAMETER mit erlaubten Bereichen [min,max]: {json.dumps(ranges)}\n"
        f"ZIEL: {objective['goal']} von '{objective['metric']}'"
        + (f" → Zielwert {objective.get('target')}" if objective.get('goal') == 'target' else "") + "\n"
        f"HARTE RANDBEDINGUNGEN (müssen gelten): {json.dumps(constraints)}\n"
        f"BISHERIGE VERSUCHE (params→metrics, feasible): {json.dumps(hist, ensure_ascii=False)}\n\n"
        f"Schlage GENAU {k} neue, vielversprechende Parameter-Kombinationen vor "
        "(nutze die Trends; erkunde auch unerprobte Bereiche). Halte jeden Wert "
        "strikt im erlaubten Bereich. Antworte NUR mit einem JSON-Array aus "
        "Objekten, jedes mit genau den freien Parametern als Schlüssel. Kein Text."
    )
    try:
        arr = _extract_array(_ollama_chat([{"role": "system", "content": sys},
                                           {"role": "user", "content": "Nächste Kandidaten als JSON-Array:"}]))
    except Exception:
        arr = []
    out = [_clamp(a) for a in arr if a]
    out = [a for a in out if a]
    while len(out) < k:                     # pad with random if the LLM under-delivered
        out.append(_clamp(_random_params(free)))
    return out[:k]


# ── main loop ────────────────────────────────────────────────────────────────

def optimize(spec, progress_cb=None):
    """spec = {base_payload, objective:{metric,goal,target?}, constraints:[{metric,op,value}],
    free:[{param,min,max}], iterations, batch}. Returns result dict."""
    def log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    payload    = spec["base_payload"]
    objective  = spec["objective"]
    constraints = spec.get("constraints", [])
    free       = [f for f in spec.get("free", []) if f.get("param") in FREE_PARAMS]
    if not free:
        raise ValueError("Keine freien Parameter gewählt")
    budget = int(spec.get("iterations", 24))
    k      = max(2, int(spec.get("batch", 6)))

    base_geom  = payload["geom"]
    base_axial = float(payload.get("axial_len", base_geom.get("axialLen", 80)))
    mats       = _materials(payload)
    cooling    = payload.get("cooling", "water")
    T_amb      = float(payload.get("T_ambient", 25))
    op = {"rpm_thermal": float(payload.get("rpm_to", 20000)),
          "rpm_base":    float(payload.get("rpm_from", 5000)),
          "load_nm":     float(payload.get("load_nm", 5))}
    rpm_hi     = float(payload.get("rpm_to", 20000))
    sweep_rpms = [round(rpm_hi * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]

    history = []
    best = {"fitness": -1e18, "params": None, "metrics": None}

    def consider(params):
        m = evaluate_fast(base_geom, base_axial, params, mats, op,
                          cooling, T_amb, sweep_rpms)
        fit = _fitness(m, objective, constraints)
        feasible = ("error" not in m) and _violation(m, constraints) <= 1e-9
        history.append({"params": params, "metrics": m, "feasible": feasible, "fitness": fit})
        nonlocal best
        if fit > best["fitness"]:
            best = {"fitness": fit, "params": params, "metrics": m, "feasible": feasible}
        return m, feasible

    # Round 0: base design + random seeds
    base_params = {}
    for f in free:
        spc = FREE_PARAMS[f["param"]]
        cur = base_axial if spc.get("special") == "axial" else base_geom.get(spc["geom"])
        if cur is not None:
            base_params[f["param"]] = spc["type"](cur)
    seeds = [_clamp(base_params)] + [_clamp(_random_params(free)) for _ in range(k - 1)]
    log(f"Starte Optimierung: {len(free)} freie Parameter, {len(constraints)} Randbedingungen, Budget {budget}", 5)
    for i, p in enumerate(seeds):
        consider(p)
        log(f"Seed {i+1}/{len(seeds)} bewertet", 5 + int(10 * (i + 1) / len(seeds)))

    # LLM-steered rounds
    done = len(history)
    while done < budget:
        n = min(k, budget - done)
        log(f"LLM schlägt {n} neue Kandidaten vor… ({done}/{budget})",
            15 + int(80 * done / budget))
        cands = _llm_propose(objective, constraints, free, history, n)
        for p in cands:
            m, feas = consider(p)
            done += 1
            tag = "✓" if feas else "✗"
            ov = m.get(objective["metric"], "—") if "error" not in m else "FEHLER"
            log(f"  {tag} {objective['metric']}={ov}  [{done}/{budget}]",
                15 + int(80 * done / budget))

    # Best result
    bm = best["metrics"] or {}
    log(f"Fertig. Beste {'zulässige ' if best['feasible'] else ''}Lösung: "
        f"{objective['metric']}={bm.get(objective['metric'],'—')} "
        f"(feasible={best['feasible']})", 100)
    history_sorted = sorted(history, key=lambda h: h["fitness"], reverse=True)
    return {
        "best_params":   best["params"],
        "best_metrics":  best["metrics"],
        "best_feasible": best["feasible"],
        "objective":     objective,
        "constraints":   constraints,
        "n_evaluated":   len(history),
        "top":           history_sorted[:10],
    }
