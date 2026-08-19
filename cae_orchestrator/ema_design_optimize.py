"""Per-Magnet-Fein-Optimierung frei gezeichneter (Custom-)Designs.

Anders als `ema_optimize` (variiert globale parametrische Felder wie magWidth/magAngle)
perturbiert dieser Zweig die **gezeichneten Magnet-Koordinaten** eines Halbpols
(r/offset/tilt/length/thickness je Magnet) sowie die **Barrieren-Breiten** — LLM-
gesteuert, FreeCAD/FEM-frei bewertet. Pol-Symmetrie bleibt erhalten: optimiert wird der
**Master-Halbpol**, die d-Achsen-Spiegelung wird pro Kandidat neu erzeugt (exakt wie
`dsnBuild()` im Canvas), bevor `magShape:"custom"` ausgewertet wird.

Maximale Wiederverwendung von `ema_optimize`:
  _eval_geom (Bewertungskern), _fitness/_violation (Ranking), _ollama_chat/_extract_array
  (LLM-Vorschlag), _materials. Und `ema_design_ai._validate_layout` clampt jeden
  Kandidaten auf gültige Geometrie (äußere Ecke < rotorOD/2 − Brücke), sodass auch wilde
  LLM-Vorschläge nie eine kaputte Maschine erzeugen.
"""

import json
import math
import random

import ema_optimize as OPT
import ema_design_ai as DAI


# ── Master half-pole ↔ full pole (mirror, identisch zu dsnBuild) ──────────────

def _mirror_legs(magnets) -> list:
    """Canvas-Master-Magnete → volle customLegs (Master + d-Achsen-Spiegel).

    Dedup: ein Spiegel, der mit einem bereits vorhandenen Leg zusammenfällt (z.B. wenn
    das Modell beide V-Arme statt nur einer Hälfte liefert), wird übersprungen."""
    legs, seen = [], set()

    def _key(r, off, tilt, length):
        return (round(r, 1), round(off, 1), round(tilt, 1), round(length, 1))

    def _add(r, off, tilt, length, thick, sign):
        k = _key(r, off, tilt, length)
        if k in seen:
            return
        seen.add(k)
        legs.append({"r_pos": r, "offset": off, "tilt_deg": tilt,
                     "length": length, "thickness": thick, "mag_sign": sign})

    for m in magnets:
        on_axis = abs(m["off"]) < 0.5 and abs(m["ang"]) < 2.0
        _add(m["r"], m["off"], m["ang"], m["len"], m["thick"], m["pol"])
        if not on_axis:
            _add(m["r"], -m["off"], -m["ang"], m["len"], m["thick"], m["pol"])
    return legs


def _mirror_barriers(barriers) -> list:
    bars = []
    for b in barriers:
        bars.append({"pts": b["pts"], "width": b["width"]})
        bars.append({"pts": [[x, -y] for x, y in b["pts"]], "width": b["width"]})
    return bars


# ── Vektor-Raum über den Master-Magneten ─────────────────────────────────────

_COORDS = ("r", "off", "ang", "len", "thick")


def _bounds(magnets, params):
    """Erlaubte Bereiche je Vektor-Schlüssel (m{i}_{coord}, b{j}_width)."""
    r_rot = float(params.get("rotorOD", 188.6)) / 2.0
    r_shaft = float(params.get("shaftD", 60.0)) / 2.0
    thick_max = max(2.0, (r_rot - r_shaft) * 0.5)
    b = {}
    for i, _m in enumerate(magnets):
        b[f"m{i}_r"]     = [r_shaft + 5.0, r_rot - 3.0]
        b[f"m{i}_off"]   = [0.0, max(1.0, r_rot * 0.7)]
        b[f"m{i}_ang"]   = [-80.0, 80.0]
        b[f"m{i}_len"]   = [3.0, max(5.0, r_rot - r_shaft)]
        b[f"m{i}_thick"] = [1.0, thick_max]
    return b, thick_max


def _vec_of(magnets) -> dict:
    v = {}
    for i, m in enumerate(magnets):
        for c in _COORDS:
            v[f"m{i}_{c}"] = float(m[{"r": "r", "off": "off", "ang": "ang",
                                      "len": "len", "thick": "thick"}[c]])
    return v


def _apply_vec(magnets_tpl, barriers, vec, params):
    """Vektor → (validierte) Master-Magnete → volle customLegs/customBarriers.

    Re-uses `ema_design_ai._validate_layout` so every candidate is geometrically
    valid (length re-clamped to the live `_max_magnet_width`)."""
    mags = []
    for i, m in enumerate(magnets_tpl):
        mags.append({
            "r":     vec.get(f"m{i}_r",     m["r"]),
            "off":   vec.get(f"m{i}_off",   m["off"]),
            "ang":   vec.get(f"m{i}_ang",   m["ang"]),
            "len":   vec.get(f"m{i}_len",   m["len"]),
            "thick": vec.get(f"m{i}_thick", m["thick"]),
            "pol":   m["pol"],
        })
    mags, _bars = DAI._validate_layout(mags, [], params)
    legs = _mirror_legs(mags)
    bars = _mirror_barriers(barriers)
    return mags, legs, bars


def _clampv(vec, bounds):
    out = {}
    for k, val in vec.items():
        if k not in bounds:
            continue
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        lo, hi = bounds[k]
        out[k] = max(lo, min(hi, val))
    return out


def _random_vec(bounds):
    return {k: round(random.uniform(lo, hi), 3) for k, (lo, hi) in bounds.items()}


def _propose(objective, constraints, bounds, history, k, model):
    hist = [{"vec": h["vec"],
             "metrics": {mk: h["metrics"].get(mk) for mk in
                         ({objective["metric"]} | {c["metric"] for c in constraints})
                         if mk in h["metrics"]},
             "feasible": h["feasible"]}
            for h in history[-14:]]
    sys = (
        "Du optimierst die Magnet-Geometrie eines IPM-Rotors. Variiere die Koordinaten "
        "der Magnete eines halben Pols, um ein Ziel zu erreichen.\n"
        f"VEKTOR-SCHLÜSSEL mit Bereichen [min,max] (m{{i}}_r=Radius, _off=Tangentialversatz, "
        f"_ang=Neigung°, _len=Länge, _thick=Dicke, je in mm bzw. °): {json.dumps(bounds)}\n"
        f"ZIEL: {objective['goal']} von '{objective['metric']}'"
        + (f" → Zielwert {objective.get('target')}" if objective.get('goal') == 'target' else "") + "\n"
        f"HARTE RANDBEDINGUNGEN: {json.dumps(constraints)}\n"
        f"BISHERIGE VERSUCHE (vec→metrics, feasible): {json.dumps(hist, ensure_ascii=False)}\n\n"
        f"Schlage GENAU {k} neue Vektoren vor (nutze Trends, erkunde). Jeder Wert strikt "
        "im Bereich. Antworte NUR mit JSON-Array aus Objekten mit genau diesen Schlüsseln."
    )
    try:
        arr = OPT._extract_array(OPT._ollama_chat(
            [{"role": "system", "content": sys},
             {"role": "user", "content": "Nächste Vektoren als JSON-Array:"}]))
    except Exception:
        arr = []
    out = [_clampv(a, bounds) for a in arr if isinstance(a, dict)]
    out = [a for a in out if a]
    while len(out) < k:
        out.append(_clampv(_random_vec(bounds), bounds))
    return out[:k]


# ── main ───────────────────────────────────────────────────────────────────────

def optimize_custom(spec, progress_cb=None):
    """spec = {base_payload, magnets, barriers, objective, constraints, iterations,
    batch, model?}. `magnets`/`barriers` = der Master-Halbpol (Canvas-Format).
    Returns {best_magnets, best_barriers, best_metrics, best_feasible, base_metrics,
    objective, constraints, n_evaluated, top}."""
    def log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    payload    = spec["base_payload"]
    objective  = spec["objective"]
    constraints = spec.get("constraints", [])
    budget = int(spec.get("iterations", 20))
    k      = max(2, int(spec.get("batch", 5)))
    model  = spec.get("model") or OPT.DEFAULT_MODEL

    base_geom  = dict(payload["geom"])
    params     = {"rotorOD": base_geom.get("rotorOD"), "shaftD": base_geom.get("shaftD")}
    magnets_tpl, barriers = DAI._validate_layout(spec.get("magnets"),
                                                 spec.get("barriers"), {
                                                     "rotorOD": base_geom.get("rotorOD"),
                                                     "shaftD": base_geom.get("shaftD")})
    if not magnets_tpl:
        raise ValueError("Kein gültiger Magnet im Entwurf — nichts zu optimieren")

    base_axial = float(payload.get("axial_len", base_geom.get("axialLen", 80)))
    mats       = OPT._materials(payload)
    cooling    = payload.get("cooling", "water")
    T_amb      = float(payload.get("T_ambient", 25))
    op = {"rpm_thermal": float(payload.get("rpm_to", 20000)),
          "rpm_base":    float(payload.get("rpm_from", 5000)),
          "load_nm":     float(payload.get("load_nm", 5))}
    rpm_hi     = float(payload.get("rpm_to", 20000))
    sweep_rpms = [round(rpm_hi * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]

    bounds, _tmax = _bounds(magnets_tpl, base_geom)

    history = []
    best = {"fitness": -1e18, "vec": None, "magnets": None, "metrics": None,
            "feasible": False}

    def consider(vec):
        mags, legs, bars = _apply_vec(magnets_tpl, barriers, vec, base_geom)
        geom = dict(base_geom)
        geom["magShape"] = "custom"
        geom["customLegs"] = legs
        geom["customBarriers"] = bars
        m = OPT._eval_geom(geom, base_axial, mats, op, cooling, T_amb, sweep_rpms)
        fit = OPT._fitness(m, objective, constraints)
        feasible = ("error" not in m) and OPT._violation(m, constraints) <= 1e-9
        history.append({"vec": vec, "metrics": m, "feasible": feasible, "fitness": fit})
        nonlocal best
        if fit > best["fitness"]:
            best = {"fitness": fit, "vec": vec, "magnets": mags, "metrics": m,
                    "feasible": feasible}
        return m, feasible

    # Round 0: the drawn baseline + random seeds
    base_vec = _vec_of(magnets_tpl)
    base_metrics, _bf = consider(base_vec)
    log(f"Baseline bewertet: {objective['metric']}={base_metrics.get(objective['metric'], '—')}", 6)
    seeds = [_clampv(_random_vec(bounds), bounds) for _ in range(max(0, k - 1))]
    for i, s in enumerate(seeds):
        consider(s)
        log(f"Seed {i + 1}/{len(seeds)} bewertet", 6 + int(10 * (i + 1) / max(1, len(seeds))))

    done = len(history)
    while done < budget:
        n = min(k, budget - done)
        log(f"LLM schlägt {n} Magnet-Varianten vor… ({done}/{budget})",
            16 + int(80 * done / budget))
        for vec in _propose(objective, constraints, bounds, history, n, model):
            m, feas = consider(vec)
            done += 1
            tag = "✓" if feas else "✗"
            ov = m.get(objective["metric"], "—") if "error" not in m else "FEHLER"
            log(f"  {tag} {objective['metric']}={ov}  [{done}/{budget}]",
                16 + int(80 * done / budget))

    bm = best["metrics"] or {}
    log(f"Fertig. Beste {'zulässige ' if best['feasible'] else ''}Lösung: "
        f"{objective['metric']}={bm.get(objective['metric'], '—')}", 100)
    history_sorted = sorted(history, key=lambda h: h["fitness"], reverse=True)
    return {
        "best_magnets":  best["magnets"],
        "best_barriers": barriers,
        "best_metrics":  best["metrics"],
        "best_feasible": best["feasible"],
        "base_metrics":  base_metrics,
        "objective":     objective,
        "constraints":   constraints,
        "n_evaluated":   len(history),
        "top":           [{"metrics": h["metrics"], "feasible": h["feasible"]}
                          for h in history_sorted[:10]],
    }
