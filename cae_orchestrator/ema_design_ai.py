"""KI-gestützter Entwurf kompletter IPM-Maschinen für den Designer-Tab.

Der parallele „KI-Auslegungs"-Pfad: aus einer Anwendungs-Beschreibung entwirft das
lokale LLM (s. ema_report.DEFAULT_MODEL) eine ODER mehrere **komplette** Maschinen — Hauptmaße,
Polzahl, Material, Betriebspunkt **und** eine frei gezeichnete Halbpol-Geometrie
(Magnetpositionen + Flussbarrieren im Canvas-Format). Die Geometrie wird anschließend
auf den Designer-Canvas gezeichnet (`DESIGN.magnets`/`DESIGN.barriers`), kann editiert
und über das bestehende `dsnBuild()` → `/analyse` gerechnet werden.

Wiederverwendung:
  * `ema_text2ema.SCHEMA` + `_validate` für den parametrischen (Maß-)Teil — garantiert
    in sich stimmige, ladbare Hauptmaße (radiale Ordnung, ~0,7 mm Spalt, slots≈6p).
  * `ema_rag.context_for(brief, category="maschinen")` zur Erdung an Referenzmaschinen.
  * `ema_topology.magnet_legs` + `_max_magnet_width` für die geometrische Validierung
    der freien Magnete und für den **Fallback**: liefert das LLM keine brauchbare
    Freihand-Geometrie, wird aus der parametrischen Topologie ein gültiger Halbpol
    synthetisiert, sodass IMMER etwas Gezeichnetes herauskommt.

Magnet-Format (Canvas-Master, pol-lokal mm; x=radial außen, y=tangential):
  {r, off, ang, len, thick, pol}  — identisch zu `DESIGN.magnets` in ema.html.
Barrieren: {pts:[[x,y],…], width}.

Kein LLM in der Analyse selbst — das Modell erzeugt nur die Eingabe-Geometrie.
"""

import json
import math
import re
import urllib.request

import ema_text2ema as T2E
import ema_topology as TOPO
from ema_report import OLLAMA_URL, DEFAULT_MODEL

_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)

# Geometrie-Defaults, die magnet_legs/_build_* brauchen, aber NICHT im SCHEMA stehen.
# Die parametrischen SCHEMA-Felder werden darüber gelegt (für den Fallback-Synthesizer).
_GEOM_DEFAULTS = {
    "magLayers": 1, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "magAsym": 0.0, "magAngle2": 90, "magTangLen": 0, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
    "magGapMm": 0.1,
}


# ── Parsing helpers ───────────────────────────────────────────────────────────

_COMMENT_RE = re.compile(r"//[^\n\r]*|/\*.*?\*/", re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",\s*([}\]])")


def _extract_obj(txt: str) -> dict:
    """First top-level JSON object in the text, tolerant of local-model quirks
    (``` fences, // and /* */ comments, trailing commas)."""
    obj = T2E._extract_obj(txt)
    if isinstance(obj, dict) and obj:
        return obj
    m = re.search(r"\{.*\}", txt, re.DOTALL)
    if not m:
        return {}
    cleaned = _TRAILING_COMMA_RE.sub(r"\1", _COMMENT_RE.sub("", m.group(0)))
    try:
        out = json.loads(cleaned)
        return out if isinstance(out, dict) else {}
    except Exception:
        return {}


def _num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return float(default)


def _clamp(v, lo, hi):
    return max(lo, min(hi, v))


# ── Layout validation (the robustness core) ──────────────────────────────────

def _validate_layout(magnets, barriers, params) -> tuple[list, list]:
    """Clamp freehand magnets + barriers into a physically valid HALF-pole.

    Returns (magnets, barriers) in canvas format. Invalid entries are dropped;
    every kept magnet's outer corner stays inside ``r_rot − bridge`` (via the
    canonical `ema_topology._max_magnet_width`) and its inner end clears the shaft.
    Magnets are kept on the +offset half (the canvas master); `dsnBuild()` mirrors.
    """
    r_rot = _num(params.get("rotorOD"), 188.6) / 2.0
    r_shaft = _num(params.get("shaftD"), 60.0) / 2.0
    bridge = TOPO.BRIDGE_MM
    thick_max = max(2.0, (r_rot - r_shaft) * 0.5)

    def _fit_len(r, off, ang_rad, r_lim):
        """Max length so the magnet CENTERLINE outer corner stays ≤ r_lim (no floor)."""
        a, b = math.cos(ang_rad), math.sin(ang_rad)
        p = a * r + b * off
        q = r * r + off * off - r_lim * r_lim
        disc = p * p - q
        if disc < 0:
            return 0.0
        return max(0.0, -p + math.sqrt(disc))

    out_mag = []
    for m in (magnets or []):
        if not isinstance(m, dict):
            continue
        thick = _clamp(_num(m.get("thick"), 4.0), 1.0, thick_max)
        r_lim = r_rot - bridge - thick / 2          # centreline must clear OD bridge + half thickness
        r = _clamp(_num(m.get("r"), r_shaft + (r_rot - r_shaft) * 0.6),
                   r_shaft + thick / 2 + 1.0, max(r_shaft + thick / 2 + 1.0, r_lim - 1.0))
        off = _clamp(abs(_num(m.get("off"), 0.0)), 0.0, r_rot)   # half-pole: +y side
        ang = _clamp(_num(m.get("ang"), 0.0), -89.0, 89.0)
        lmax = _fit_len(r, off, math.radians(ang), r_lim)
        if lmax < 2.0:                               # cannot fit a real magnet here → drop
            continue
        length = _clamp(_num(m.get("len"), 20.0), 2.0, lmax)
        pol = -1 if _num(m.get("pol"), 1.0) < 0 else 1
        cand = {"r": round(r, 2), "off": round(off, 2), "ang": round(ang, 1),
                "len": round(length, 2), "thick": round(thick, 2), "pol": pol}
        # No magnet–magnet overlap among the placed (master) magnets — any count is
        # fine (1 pole-sized OR many small) as long as they don't intersect. The
        # d-axis mirror is NOT checked here: a V/U arm legitimately sits right next to
        # its own reflection near the pole centre (that proximity is the V, not a clash).
        if any(_obb_overlap(cand, ex, _MAG_MAG_CLEAR) for ex in out_mag):
            continue                                 # would overlap a kept magnet → drop
        out_mag.append(cand)

    out_bar = []
    for b in (barriers or []):
        if not isinstance(b, dict):
            continue
        pts = b.get("pts") or []
        cl = []
        for pt in pts:
            try:
                x, y = float(pt[0]), float(pt[1])
            except (TypeError, ValueError, IndexError):
                continue
            y = max(0.0, y)                               # HALF pole only (y≥0); mirror added later
            rad = math.hypot(x, y)
            if rad > r_rot - bridge:                      # pull inside the OD bridge
                s = (r_rot - bridge) / rad
                x, y = x * s, y * s
            cl.append([round(x, 2), round(y, 2)])
        if len(cl) < 2:
            continue
        width = _clamp(_num(b.get("width"), 2.0), 0.5, 10.0)
        # Keep barriers OUT of the magnets: a flux barrier carved through a magnet
        # makes nonsense geometry (air inside the PM). Drop the barrier if its
        # polyline runs into any magnet — checking BOTH the master (+offset) and its
        # d-axis mirror (−offset), with a clearance that includes half the slot width.
        clear = BARRIER_MAGNET_CLEARANCE_MM + width / 2.0
        if _polyline_hits_magnet(cl, out_mag, clear):
            continue
        out_bar.append({"pts": cl, "width": round(width, 2)})

    return out_mag, out_bar


BARRIER_MAGNET_CLEARANCE_MM = 1.0   # min. gap freehand barriers keep from magnets
_MAG_MAG_CLEAR = 0.5                 # min. gap between magnets (no overlap)


def _mag_mirror(m: dict) -> dict:
    """d-axis mirror of a canvas magnet (offset→−offset, tilt→−tilt)."""
    return {"r": m["r"], "off": -_num(m["off"]), "ang": -_num(m["ang"]),
            "len": m["len"], "thick": m["thick"]}


def _obb(m: dict):
    """Oriented bounding box of a magnet: (cx, cy, ux, uy, vx, vy, hL, hT) — centre,
    unit length axis (u), unit thickness axis (v), half-length, half-thickness."""
    a = math.radians(_num(m.get("ang")))
    c, s = math.cos(a), math.sin(a)
    L, t = _num(m.get("len")), _num(m.get("thick"), 4.0)
    cx = _num(m.get("r")) + c * L / 2.0
    cy = _num(m.get("off")) + s * L / 2.0
    return (cx, cy, c, s, -s, c, L / 2.0, t / 2.0)


def _obb_overlap(m1: dict, m2: dict, clear: float = 0.0) -> bool:
    """Do two magnet rectangles intersect (with ``clear`` mm gap)? Separating-axis
    test over the four box edge normals — exact for convex rectangles."""
    c1x, c1y, u1x, u1y, v1x, v1y, h1L, h1T = _obb(m1)
    c2x, c2y, u2x, u2y, v2x, v2y, h2L, h2T = _obb(m2)
    dx, dy = c2x - c1x, c2y - c1y
    for ax, ay in ((u1x, u1y), (v1x, v1y), (u2x, u2y), (v2x, v2y)):
        r1 = h1L * abs(u1x * ax + u1y * ay) + h1T * abs(v1x * ax + v1y * ay)
        r2 = h2L * abs(u2x * ax + u2y * ay) + h2T * abs(v2x * ax + v2y * ay)
        if abs(dx * ax + dy * ay) > r1 + r2 + clear:
            return False                            # separated on this axis ⇒ no overlap
    return True


def _pt_in_magnet(x: float, y: float, mag: dict, clear: float) -> bool:
    """Is point (x,y) inside the magnet rectangle (start=(r,off), axis=tilt, length×
    thickness) expanded by ``clear`` mm? Tested for the given mag orientation."""
    a = math.radians(_num(mag.get("ang")))
    c, s = math.cos(a), math.sin(a)
    dx, dy = x - _num(mag.get("r")), y - _num(mag.get("off"))
    u = dx * c + dy * s                     # along the long axis
    v = -dx * s + dy * c                    # across the thickness
    half_t = _num(mag.get("thick"), 4.0) / 2.0
    return (-clear <= u <= _num(mag.get("len")) + clear) and (abs(v) <= half_t + clear)


def _polyline_hits_magnet(pts: list, magnets: list, clear: float) -> bool:
    """True if any sampled point of the polyline lands inside any magnet OR its
    d-axis mirror (offset→−offset, tilt→−tilt). Segments are sampled so a slot that
    crosses a magnet between two outside vertices is still caught."""
    def mirror(m):
        return {"r": m.get("r"), "off": -_num(m.get("off")),
                "ang": -_num(m.get("ang")), "len": m.get("len"), "thick": m.get("thick")}
    mags = list(magnets) + [mirror(m) for m in magnets]
    for i in range(len(pts) - 1):
        (x0, y0), (x1, y1) = pts[i], pts[i + 1]
        for t in (0.0, 0.25, 0.5, 0.75, 1.0):
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if any(_pt_in_magnet(x, y, m, clear) for m in mags):
                return True
    return False


# ── Fallback: parametric topology → drawn half-pole ──────────────────────────

def _params_to_geom(params: dict) -> dict:
    """Build a full geom dict (for `magnet_legs`) from the validated SCHEMA params."""
    geom = dict(_GEOM_DEFAULTS)
    for k in ("statorOD", "statorID", "rotorOD", "shaftD", "shaftBoreD", "slots",
              "slotDepth", "p", "magShape", "magAngle", "magDepthRel", "magWidth",
              "magThick", "magDist", "nAx", "nCirc"):
        if params.get(k) is not None:
            geom[k] = params[k]
    return geom


def _legs_to_canvas(geom: dict) -> list:
    """Synthesise canvas-format HALF-pole magnets from a parametric topology.

    Uses the single-source-of-truth `magnet_legs`; keeps the +offset half (master).
    Surface placements are skipped (the freehand canvas models interior magnets)."""
    try:
        legs, _meta = TOPO.magnet_legs(geom)
    except Exception:
        return []
    out = []
    for lg in legs:
        if getattr(lg, "placement", "interior") != "interior":
            continue
        if lg.offset < -0.05:                 # keep the master half (mirror is added later)
            continue
        out.append({"r": round(lg.r_pos, 2), "off": round(max(0.0, lg.offset), 2),
                    "ang": round(math.degrees(lg.tilt), 1), "len": round(lg.length, 2),
                    "thick": round(lg.thickness, 2),
                    "pol": -1 if int(lg.mag_sign) < 0 else 1})
    return out


# ── LLM prompt ───────────────────────────────────────────────────────────────

def _layout_fields() -> str:
    return (
        "  params: ein Objekt mit GENAU diesen Feldern (Maße/Material/Betriebspunkt):\n"
        + "\n".join(
            f"    {k}: " + (f"einer von {s['opts']}" if s["kind"] == "enum"
                            else f"Zahl {s['lo']}–{s['hi']}") + f" — {s['desc']}"
            for k, s in T2E.SCHEMA.items())
        + "\n  magnets: Liste von Magneten EINES HALBEN Pols (pol-lokal, mm; x=radial "
          "nach außen, y=tangential). Gib NUR die Magnete auf der Seite y≥0 an — die "
          "andere Hälfte wird automatisch an der d-Achse (Pol-Mitte, y=0) gespiegelt, "
          "NICHT selbst spiegeln. Für eine V-Anordnung also EIN geneigter Magnet "
          "(off>0, ang>0); die Spiegelung ergänzt den zweiten Arm. Jeder Magnet: "
          "{r: radiale Startposition [mm], off: tangentialer Versatz [mm, ≥0], "
          "ang: Neigung der Längsachse [°], len: Länge [mm], thick: Dicke [mm], "
          "pol: +1 oder -1 (Polung innerhalb des Pols)}. Die äußere Magnetecke muss "
          "< (rotorOD/2 − 2 mm) bleiben. Die Magnete dürfen sich NICHT überlappen — "
          "entweder EIN im Verhältnis zum Pol großer Magnet, oder mehrere kleinere mit "
          "deutlichem Abstand zueinander (auch zur d-Achsen-Spiegelung).\n"
        + "  barriers: Liste von Flussbarrieren (Luftschlitze) EINES HALBEN Pols: "
          "{pts: [[x,y],…] Polygonzug in mm, width: Breite [mm]}. ALLE Punkte mit y≥0 "
          "(nur die obere Pol-Hälfte!), die Spiegelung an der d-Achse erfolgt automatisch. "
          "Leere Liste erlaubt.\n"
    )


def _prompt(brief: str, context: str, prior: list, variety: int,
            feedback: str = "") -> str:
    ref = ""
    if context:
        ref = ("REFERENZMASCHINEN (aus der Wissensbasis — als gut befundene Auslegungen; "
               "orientiere dich, übernimm nicht blind):\n" + context + "\n\n")
    div = ""
    if prior:
        summ = "; ".join(
            f"Variante {i+1}: {p['params'].get('magShape')}, "
            f"rotorOD≈{p['params'].get('rotorOD')} mm, p={p['params'].get('p')}, "
            f"{len(p['magnets'])} Magnete"
            for i, p in enumerate(prior))
        div = ("BEREITS ENTWORFENE VARIANTEN (deutlich anders machen — andere Topologie/"
               f"Polzahl/Magnetanordnung): {summ}\n\n")
    fb = ""
    if feedback:
        fb = ("DER VORIGE ENTWURF WAR UNGEEIGNET — behebe die folgenden Mängel gezielt "
              "(z.B. mehr Magnetmaterial/Querschnitt für höhere Luftspaltflussdichte, "
              "dünnere Magnete/bessere Kühlung gegen Übertemperatur, robusteres "
              f"Rotoreisen für die Drehzahl):\n{feedback}\n\n")
    hint = ("Erkunde mutig eine alternative Bauform." if variety else
            "Entwirf eine solide, ausgewogene erste Auslegung.")
    return (
        "Du bist ein erfahrener Auslegungsingenieur für Innenpol-PM-Synchronmaschinen "
        "(IPM). Entwirf eine KOMPLETTE Maschine zur folgenden Anwendung — inklusive der "
        "frei platzierten Magnete und Flussbarrieren im Rotor. " + hint + "\n\n"
        f"ANWENDUNG:\n{brief}\n\n" + ref + div + fb +
        "Liefere die folgende Struktur als JSON:\n" + _layout_fields() + "\n"
        "Regeln: statorOD > statorID > rotorOD > shaftD; Luftspalt ~0,7 mm "
        "(rotorOD ≈ statorID − 1,4); slots ≈ 6·p; die Magnete sitzen im Rotoreisen "
        "zwischen Welle (shaftD/2) und Rotorrand (rotorOD/2 − 2 mm Brücke); für eine "
        "V-Anordnung zwei geneigte Magnete pro halbem Pol; Flussbarrieren reduzieren "
        "Streuung/Rastmoment und liegen NEBEN/ZWISCHEN den Magneten — sie dürfen die "
        "Magnete NICHT überlappen (sonst würde Luft in den Magneten ausgeschnitten). "
        "Setze die Magnete passend zu params.p und params.rotorOD.\n\n"
        "Antworte NUR mit einem JSON-Objekt {\"params\":{…}, \"magnets\":[…], "
        "\"barriers\":[…], \"begruendung\":\"<2–4 Sätze>\"}. Kein weiterer Text."
    )


def _ollama(messages, model, timeout):
    # format="json" constrains the local model to syntactically valid JSON — essential
    # for the larger combined params+magnets+barriers schema (free-text JSON from a
    # local model is otherwise frequently broken: decimal commas, comments, math).
    body = json.dumps({"model": model, "messages": messages, "stream": False,
                       "think": False,          # s. ema_report.call_ollama
                       "format": "json",
                       "options": {"temperature": 0.35, "num_ctx": 8192,
                                   "num_predict": 1600}}).encode("utf-8")
    req = urllib.request.Request(f"{OLLAMA_URL}/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    return _THINK_RE.sub("", (resp.get("message", {}) or {}).get("content", "")).strip()


# ── one design ────────────────────────────────────────────────────────────────

def _one_variant(brief, context, prior, variety, model, timeout, feedback=""):
    txt = _ollama([{"role": "user",
                    "content": _prompt(brief, context, prior, variety, feedback)}],
                  model, timeout)
    obj = _extract_obj(txt)
    params = T2E._validate(obj.get("params", {}) if isinstance(obj.get("params"), dict) else {})
    magnets, barriers = _validate_layout(obj.get("magnets"), obj.get("barriers"), params)
    fallback = False
    if not magnets:                                   # LLM gave no usable geometry
        magnets = _legs_to_canvas(_params_to_geom(params))
        fallback = True
    why = obj.get("begruendung")
    if isinstance(why, (dict, list)):
        why = json.dumps(why, ensure_ascii=False)
    return {
        "params":      params,
        "magnets":     magnets,
        "barriers":    barriers,
        "begruendung": str(why or ""),
        "fallback":    fallback,
    }


# ── Schnelle Qualitäts-Vorsortierung (FreeCAD/FEM-frei) ──────────────────────

def _quick_eval(variant: dict) -> dict:
    """Bewertet einen Entwurf FreeCAD/FEM-frei und liefert ein gut/schlecht-Urteil.

    Nutzt dieselbe Heuristik wie das Trainings-Auto-Label (``ema_training.auto_label``)
    auf den schnell geschätzten Kennwerten (``ema_optimize._eval_geom``). „schlecht"
    heißt also: der Entwurf würde auch nach einer echten Rechnung als schlecht gelten.
    Best-effort — jeder Fehler ⇒ ``verdict=None`` (kein Aussortieren)."""
    try:
        import ema_optimize as OPT
        import ema_design_optimize as DOPT      # lazy: vermeidet Zirkelimport
        import ema_training
        params = variant.get("params") or {}
        mags, bars = _validate_layout(variant.get("magnets"), variant.get("barriers"),
                                      {"rotorOD": params.get("rotorOD"),
                                       "shaftD": params.get("shaftD")})
        if not mags:
            return {"verdict": None, "reasons": ["keine gültige Geometrie"], "metrics": {}}
        geom = _params_to_geom(params)
        geom["magShape"] = "custom"
        geom["customLegs"] = DOPT._mirror_legs(mags)
        geom["customBarriers"] = DOPT._mirror_barriers(bars)
        mats = OPT._materials(params)            # params tragen die Material-Schlüssel
        axial = float(params.get("axialLen", 80))
        rpm_hi = float(params.get("rpm_to", 20000))
        op = {"rpm_thermal": rpm_hi,
              "rpm_base":    float(params.get("rpm_from", 5000)),
              "load_nm":     float(params.get("load_nm", 5))}
        sweep = [round(rpm_hi * f) for f in (0.2, 0.35, 0.5, 0.65, 0.8, 0.9, 1.0)]
        m = OPT._eval_geom(geom, axial, mats, op, params.get("cooling", "water"),
                           float(params.get("T_ambient", 25)), sweep)
        if "error" in m:
            return {"verdict": None, "reasons": [m["error"]], "metrics": m}
        summary = {"T_winding_C": m.get("T_winding"), "T_magnet_C": m.get("T_magnet"),
                   "max_safe_rpm": m.get("max_safe_rpm"), "B_gap_T": m.get("B_gap")}
        auto = ema_training.auto_label({"summary": summary},
                                       {"payload": {"rpm_to": rpm_hi}})
        return {"verdict": auto.get("suggestion"),
                "reasons": auto.get("reasons", []), "metrics": m}
    except Exception as e:
        return {"verdict": None, "reasons": [str(e)[:160]], "metrics": {}}


_VERDICT_RANK = {"gut": 2, None: 1, "schlecht": 0}


def _quality_score(variant: dict):
    q = variant.get("quality") or {}
    rank = _VERDICT_RANK.get(q.get("verdict"), 1)
    bgap = (q.get("metrics") or {}).get("B_gap") or 0.0
    return (rank, bgap)


def _gen_one(brief, context, prior, variety, model, timeout, feedback=""):
    """Einen Entwurf erzeugen (mit parametrischem Fallback bei LLM-Fehler)."""
    try:
        return _one_variant(brief, context, prior, variety, model, timeout, feedback)
    except Exception as e:
        try:
            params = T2E.derive(brief, timeout=timeout)["params"]
        except Exception:
            params = T2E._validate({})
        return {"params": params, "magnets": _legs_to_canvas(_params_to_geom(params)),
                "barriers": [], "begruendung": f"(Fallback: {e})", "fallback": True}


def _gen_slot(brief, context, prior, i, n, model, timeout, max_regen,
              progress_cb=None, post_fn=None):
    """Einen Varianten-Slot erzeugen: generieren → (optional ``post_fn`` anwenden) →
    vorsortieren; bei „schlecht" mit gezieltem Feedback bis ``max_regen``-mal neu.
    Gibt ``(best, rejected)`` zurück (best = bester Versuch nach ``_quality_score``)."""
    attempts, feedback = [], ""
    for t in range(max_regen + 1):
        if progress_cb:
            tag = f"Variante {i + 1}/{n}" + (f" (Nachversuch {t})" if t else "")
            progress_cb(f"Entwerfe {tag}…", int(100 * i / n))
        v = _gen_one(brief, context, prior, i, model, timeout, feedback)
        if post_fn:
            post_fn(v)                              # z.B. Bereichs-Maße erzwingen
        v["quality"] = _quick_eval(v)
        attempts.append(v)
        if v["quality"].get("verdict") != "schlecht":
            break                                   # gut/unbekannt → akzeptieren
        feedback = "; ".join(v["quality"].get("reasons", [])) or "ungeeignete Kennwerte"
        if progress_cb:
            progress_cb(f"Variante {i + 1} schlecht ({feedback}) → neuer Entwurf",
                        int(100 * i / n))
    best = max(attempts, key=_quality_score)
    return best, [a for a in attempts if a is not best]


def design_variants(brief: str, n: int = 3, model: str = DEFAULT_MODEL,
                    timeout: int = 180, max_regen: int = 2, progress_cb=None) -> dict:
    """Return {variants:[…], rejected:[…], regenerated, rag_used, model}.

    Generates ``n`` distinct complete designs (each with a drawn half-pole). **Jeder
    Entwurf wird sofort FreeCAD/FEM-frei vorsortiert** (``_quick_eval``); fällt er
    „schlecht" aus, wird mit gezieltem Feedback ein neuer erzeugt (bis ``max_regen``
    Nachversuche je Variante). Der beste Versuch je Slot landet in ``variants`` (mit
    ``quality``-Urteil), die verworfenen schlechten in ``rejected``. Robust: ein
    leeres Freihand-Layout fällt auf die parametrische Topologie zurück, sodass jede
    Variante zeichenbar ist."""
    if not (brief or "").strip():
        raise ValueError("Leere Beschreibung")
    n = max(1, min(99, int(n)))
    max_regen = max(0, min(4, int(max_regen)))

    context = ""
    try:
        import ema_rag
        context = ema_rag.context_for(brief, category="maschinen", k=4)
    except Exception:
        context = ""

    variants, rejected = [], []
    for i in range(n):
        best, rej = _gen_slot(brief, context, variants, i, n, model,
                              timeout, max_regen, progress_cb)
        variants.append(best)
        rejected.extend(rej)

    if progress_cb:
        progress_cb(f"Fertig: {len(variants)} Varianten "
                    f"({len(rejected)} schlechte verworfen)", 100)
    return {"variants": variants, "rejected": rejected,
            "regenerated": len(rejected), "rag_used": bool(context), "model": model}


# ── Bereichs-/Zufalls-Entwurf ────────────────────────────────────────────────
# Der Nutzer gibt nur Bereiche für statorOD / Länge / Wellen-Ø an (von–bis); der
# Luftspalt ist fest 0,5–2 mm. Pro Variante werden diese vier Maße zufällig
# gezogen und HART erzwungen, das LLM zeichnet Magnete + Flussbarrieren dazu und
# füllt die übrigen Werte (Polzahl, Nutzahl, Material). Bewertet/gerechnet wird an
# den festen Drehzahlen 1000/5000/15000/20000 1/min.

RANGED_RPM_LIST = [1000, 5000, 15000, 20000]
AIRGAP_RANGE = (0.5, 3.0)            # zulässiger Luftspaltbereich [mm]
STATOR_SPLIT = 0.68                  # max. Bohrung/Außen-Verhältnis → echte Statorwand
                                     # (Nuten + Rückeisen), sonst wird der Stator zur Hülse


def _sample_dims(ranges: dict) -> dict:
    """Zieht statorOD/axialLen/shaftD UND den Luftspalt aus den Nutzer-Bereichen
    (Luftspalt hart auf ``AIRGAP_RANGE`` = 0,5–3 mm geklammert)."""
    import random

    def pick(key, dlo, dhi):
        r = ranges.get(key) or [dlo, dhi]
        lo, hi = float(min(r[0], r[1])), float(max(r[0], r[1]))
        return round(random.uniform(lo, hi), 1)

    gr = ranges.get("airgap") or list(AIRGAP_RANGE)
    glo = _clamp(float(min(gr[0], gr[1])), AIRGAP_RANGE[0], AIRGAP_RANGE[1])
    ghi = _clamp(float(max(gr[0], gr[1])), AIRGAP_RANGE[0], AIRGAP_RANGE[1])
    return {
        "statorOD": pick("statorOD", 120.0, 300.0),
        "axialLen": pick("axialLen", 40.0, 200.0),
        "shaftD":   pick("shaftD",   20.0, 80.0),
        "airgap":   round(random.uniform(glo, ghi), 2),
    }


def _apply_ranged_dims(variant: dict, dims: dict) -> None:
    """Erzwingt die gezogenen Maße + Luftspalt im Entwurf und re-clampt die Magnete.

    statorID/rotorOD werden aus dem gewählten Luftspalt abgeleitet (rotorOD =
    statorID − 2·Spalt), die übrige Auslegung (Polzahl/Material/Magnete) bleibt
    vom LLM. Feste Drehzahl-Eckpunkte (rpm_from/rpm_to) für die 4-Punkt-Rechnung."""
    p = dict(variant.get("params") or {})
    sod, axl, shd, gap = dims["statorOD"], dims["axialLen"], dims["shaftD"], dims["airgap"]
    p["statorOD"], p["axialLen"], p["shaftD"] = sod, axl, shd
    # Reserve a REAL stator wall (slots + back iron): cap the bore at STATOR_SPLIT·OD,
    # otherwise the rotor grows until the stator is a thin sleeve with no room for the
    # winding slots/copper.  rotorOD then follows from the chosen air gap.
    rod_cap = STATOR_SPLIT * sod - 2 * gap            # rotorOD at the max bore
    rod = _num(p.get("rotorOD"), rod_cap)
    rod = _clamp(rod, shd + 8.0, max(shd + 8.0, min(rod_cap, sod - 2 * gap - 6.0)))
    p["rotorOD"]  = round(rod, 1)
    p["statorID"] = round(rod + 2 * gap, 1)
    wall = sod / 2.0 - p["statorID"] / 2.0            # stator radial wall [mm]
    p["slotDepth"] = round(_clamp(0.55 * wall, 4.0, max(4.0, wall - 3.0)), 1)
    p["rpm_from"], p["rpm_to"] = RANGED_RPM_LIST[0], RANGED_RPM_LIST[-1]
    variant["params"] = p
    mags, bars = _validate_layout(variant.get("magnets"), variant.get("barriers"), p)
    if not mags:                                      # Layout passte nicht mehr → synthetisieren
        mags = _legs_to_canvas(_params_to_geom(p))
        variant["fallback"] = True
    variant["magnets"], variant["barriers"] = mags, bars


def _ranged_brief(dims: dict, brief: str = "") -> str:
    base = (
        f"Entwirf eine Innenpol-PM-Synchronmaschine (IPM) mit Statoraußendurchmesser "
        f"≈ {dims['statorOD']} mm, aktiver Länge ≈ {dims['axialLen']} mm, "
        f"Wellendurchmesser ≈ {dims['shaftD']} mm und Luftspalt ≈ {dims['airgap']} mm. "
        f"Wähle Polzahl, Nutzahl, Material und eine zu diesen Maßen passende Magnet- "
        f"und Flussbarrieren-Anordnung; ausgelegt für Drehzahlen bis "
        f"{RANGED_RPM_LIST[-1]} 1/min.")
    brief = (brief or "").strip()
    return f"ANWENDUNG: {brief}\n\n{base}" if brief else base


def design_variants_ranged(ranges: dict, n: int = 3, model: str = DEFAULT_MODEL,
                           timeout: int = 180, max_regen: int = 2,
                           progress_cb=None, brief: str = "") -> dict:
    """Wie :func:`design_variants`, aber maßgetrieben (optional zusätzlich brief-geführt).

    ``ranges`` = ``{"statorOD":[lo,hi], "axialLen":[lo,hi], "shaftD":[lo,hi],
    "airgap":[lo,hi]}`` (Luftspalt auf 0,5–3 mm geklammert). Pro Variante werden die
    Maße + Luftspalt zufällig gezogen und erzwungen; ``brief`` (optionale Anwendungs-
    beschreibung) wird der je-Variante-Aufgabe vorangestellt. Das LLM liefert Restwerte
    + gezeichnete Magnete/Barrieren. Rückgabe wie ``design_variants`` plus ``rpm_list``."""
    n = max(1, min(99, int(n)))
    max_regen = max(0, min(4, int(max_regen)))
    context = ""
    try:
        import ema_rag
        q = (brief or "").strip() or "IPM Hochdrehzahl Auslegung"
        context = ema_rag.context_for(q, category="maschinen", k=4)
    except Exception:
        context = ""

    variants, rejected = [], []
    for i in range(n):
        dims = _sample_dims(ranges)
        brief_v = _ranged_brief(dims, brief)
        best, rej = _gen_slot(brief_v, context, variants, i, n, model, timeout,
                              max_regen, progress_cb,
                              post_fn=lambda v, d=dims: _apply_ranged_dims(v, d))
        best["design_brief"] = brief_v                # fürs Trainingsfile (Aufgabe→Entwurf)
        variants.append(best)
        rejected.extend(rej)

    if progress_cb:
        progress_cb(f"Fertig: {len(variants)} Bereichs-Varianten "
                    f"({len(rejected)} schlechte verworfen)", 100)
    return {"variants": variants, "rejected": rejected, "regenerated": len(rejected),
            "rag_used": bool(context), "model": model, "rpm_list": list(RANGED_RPM_LIST)}
