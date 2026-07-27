"""Agentic multi-expert evaluation for E-machine analysis results.

Each expert receives a focused slice of results.json and returns a German
technical assessment as markdown text. Experts run sequentially (same Ollama
instance) and their outputs are later assembled into the full report.
"""

from __future__ import annotations
import json, math, re, urllib.request
from typing import Callable

from ema_topology import TOPOLOGY_LABELS


OLLAMA_URL   = "http://localhost:11434"
EXPERT_MODEL = "ministral-3:14b"


# ── Paragraph normaliser (same logic as ema_report._normalize_paragraphs) ───

def _normalize_text(text: str) -> str:
    """Join lines the LLM broke mid-paragraph into proper prose paragraphs."""
    def _is_structural(line: str) -> bool:
        s = line.strip()
        return (s == ""
                or s.startswith("#")
                or bool(re.match(r"^\s*[-*+]|\s*\d+\.", line))
                or s.startswith("!["))

    def _one_pass(t: str) -> tuple[str, bool]:
        lines = t.split("\n")
        out: list[str] = []
        changed = False
        i = 0
        while i < len(lines):
            line = lines[i]
            if (not _is_structural(line)
                    and not line.rstrip().endswith((".", "!", "?", ":", ";"))
                    and i + 1 < len(lines)):
                nxt = lines[i + 1]
                if nxt.strip() and not _is_structural(nxt):
                    out.append(line.rstrip() + " " + nxt.lstrip())
                    changed = True
                    i += 2
                    continue
            out.append(line)
            i += 1
        return "\n".join(out), changed

    for _ in range(20):
        text, changed = _one_pass(text)
        if not changed:
            break
    return text


# ── Image mapping: expert key → ordered list of img_map keys ────────────────

_EXPERT_IMAGES: dict[str, list[str]] = {
    "em_feld":    ["airgap", "em_field", "em_field_load"],
    "kennlinien": ["em_curve"],
    "luftspalt":  ["airgap"],
    "em3d":       ["em3d_airgap_2d3d", "em3d_endeffect", "em3d_field3d",
                   "em3d_slice_mid", "em3d_model_iso"],
    "festigkeit": ["structural", "deformation"],
    "temperatur": ["thermal"],
    "kuehlung":   ["oil_coverage", "oil_wetting", "oil_droplets"],
    "fahrzyklus": ["drivecycle", "drivecycle_vollast", "drivecycle_anhaenger"],
}


# ── LLM call ────────────────────────────────────────────────────────────────

def _call(prompt: str, model: str = EXPERT_MODEL, timeout: int = 300) -> str:
    body = json.dumps({
        "model":  model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "num_predict": 4096,
            "num_ctx":     12288,
        },
    }).encode()
    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    raw = resp.get("response", "").strip() or resp.get("thinking", "").strip()
    # Strip <think> blocks (Qwen3 style)
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()
    # Strip inline thinking preambles that some model variants write without tags.
    # Detect the end of the thinking block: look for the first paragraph that
    # starts like an actual German technical sentence (starts with a capital letter
    # or a bullet) after a blank line that follows known thinking markers.
    preamble_markers = (
        "Here's a thinking process",
        "Here is a thinking process",
        "Let me analyze",
        "Let me think",
        "Okay, let me",
        "Alright, let",
        "**Analyze User Input",
        "**Analysis:**",
    )
    lower = raw.lower()
    for marker in preamble_markers:
        if marker.lower() in lower:
            # Find the last blank line before a paragraph that starts with a capital
            # German letter or a bullet — that is where the actual answer begins.
            paragraphs = re.split(r"\n{2,}", raw)
            # Drop leading paragraphs that look like English thinking
            answer_parts: list[str] = []
            in_answer = False
            for para in paragraphs:
                first = para.lstrip()
                is_german_start = (
                    bool(re.match(r"^[A-ZÄÖÜ]", first))
                    and not re.match(r"^(Here|Let|Okay|Alright|I'll|Sure|Of course|Now)", first)
                ) or first.startswith(("-", "*", "•"))
                if is_german_start:
                    in_answer = True
                if in_answer:
                    answer_parts.append(para)
            if answer_parts:
                raw = "\n\n".join(answer_parts)
            break
    return raw.strip()


# ── Data selectors ────────────────────────────────────────────────────────────

def _em3d_compact(results: dict) -> dict | None:
    """Kompakte 3D-Magnetfeld-Kennwerte (Elmer FEM) für die Experten — None, wenn für
    dieses Projekt kein 3D-Lauf vorliegt. Spiegelt ``ema_report.build_context['em3d']``."""
    e3 = results.get("em3d") or {}
    if not e3:
        return None
    cmp3 = e3.get("compare_2d") or {}
    bz   = e3.get("b_gap_axial") or []
    endeff = round(min(bz) / max(bz), 3) if (bz and max(bz) > 0) else None
    mesh = e3.get("mesh") or {}
    return {
        "B_gap_3D_Paketmitte_T": e3.get("b_gap_mid_peak"),
        "B_gap_2D_FDM_T":        cmp3.get("B_gap_2D"),
        "B_gap_3D_Vergleich_T":  cmp3.get("B_gap_3D_mid"),
        "endeffekt_rand_zu_mitte": endeff,   # <1 ⇒ Feldabfall zu den Stirnseiten
        "skew_deg":          e3.get("skew_deg"),
        "skew_segments":     e3.get("skew_segments"),
        "skew_step_deg":     e3.get("skew_step_deg"),
        "axial_mm":          e3.get("axial_mm"),
        "mesh_knoten":       mesh.get("n_nodes"),
        "n_flussbarrieren":  mesh.get("n_barriers"),
        "warnungen":         e3.get("warnings", []),
    }


def _em_field_data(results: dict, meta: dict) -> dict:
    em  = results.get("em", {}) or {}
    perf = em.get("performance", {}) or {}
    gap  = em.get("B_gap_data", {}) or {}
    geom = (meta.get("geom") or {})
    # Subsample gap data to keep prompt compact
    br  = gap.get("Br_T", [])
    bt  = gap.get("Bt_T", [])
    th  = gap.get("theta_deg", [])
    step = max(1, len(br) // 60)
    out = {
        "performance":    perf,
        "B_gap_T":        perf.get("B_gap_T"),
        "Kt_Nm_per_A":    perf.get("Kt_Nm_per_A"),
        "T_maxwell_Nm":   perf.get("T_maxwell_Nm"),
        "lcm_slots_poles":perf.get("lcm_slots_poles"),
        "poles":          int(geom.get("p", 0)) * 2,
        "slots":          geom.get("slots"),
        "magnet":         meta.get("materials", {}).get("magnet", ""),
        "magTopologie":   TOPOLOGY_LABELS.get(geom.get("magShape", "v"), geom.get("magShape")),
        "em_erweitert":   results.get("em_advanced") or {},
        "airgap_mm":      geom.get("statorID", 0) - geom.get("rotorOD", 0) if geom else 0,
        "Br_T_samples":   [round(br[i], 4) for i in range(0, len(br), step)][:60],
        "Bt_T_samples":   [round(bt[i], 4) for i in range(0, len(bt), step)][:60],
        "theta_deg_samples": [round(th[i], 1) for i in range(0, len(th), step)][:60],
    }
    # Hinweis: die echte 3D-Feldlösung (Elmer) hat einen EIGENEN 3D-Magnetfeld-Experten
    # (_em3d_data) — der EM-Feld-Experte bleibt beim 2D-FDM-Schnittmodell.
    return out


def _em3d_data(results: dict, meta: dict) -> dict:
    """Fachdaten für den 3D-Magnetfeld-Experten (Elmer FEM) — kompakte 3D-Kennwerte +
    2D-vs-3D-Vergleich + Endeffekt. Nur belegt, wenn ein 3D-Lauf vorliegt."""
    e3 = _em3d_compact(results) or {}
    geom = (meta.get("geom") or {})
    e3["poles"] = int(geom.get("p", 0)) * 2
    e3["slots"] = geom.get("slots")
    e3["magTopologie"] = TOPOLOGY_LABELS.get(geom.get("magShape", "v"), geom.get("magShape"))
    return e3


def _kuehlung_data(results: dict, meta: dict) -> dict:
    """Fachdaten für den Kühlungs-Experten: die experimentelle Spritzöl-Studie (Benetzungs-
    Proxys, QUALITATIV — kein Wärmeübergang) im Kontext des analytischen LPTN-Thermikmodells."""
    oil    = results.get("oilspray") or {}
    om     = oil.get("metrics") or {}
    oc     = oil.get("config") or {}
    therm  = results.get("thermal") or {}
    steady = therm.get("steady") or {}
    losses = therm.get("losses") or {}
    return {
        "spritzoel": {
            "benetzung_mittel_pct":   om.get("wetted_pct_mean"),
            "benetzung_spitze_pct":   om.get("wetted_pct_peak"),
            "tropfen_spitze":         om.get("droplets_peak"),
            "n_frames":               om.get("n_frames"),
            "strahl_zellen":          om.get("jet_cells"),
            "strahl_unteraufgeloest": om.get("jet_underres"),
            "voxel_mm":               om.get("voxel_mm"),
            "aufloesung":             oc.get("resolution"),
            "duesen":                 oc.get("nozzle_count"),
            "duesen_d_mm":            oc.get("nozzle_d_mm"),
            "druck_bar":              oc.get("pressure_bar"),
            "voller_ring":            oc.get("ring_full"),
            "einbaulage":             oc.get("orientation"),
            "hinweis_scope":          oil.get("note", ""),
        },
        "thermik_kontext": {
            "kuehlung":     therm.get("cooling_label", meta.get("cooling", "")),
            "T_winding_C":  steady.get("T_winding"),
            "T_magnet_C":   steady.get("T_magnet"),
            "T_housing_C":  steady.get("T_housing"),
            "verluste_W":   losses,
            "T_ambient":    meta.get("T_ambient", 25),
        },
    }


def _kennlinien_data(results: dict, meta: dict) -> dict:
    em    = results.get("em", {}) or {}
    sweep = em.get("speed_sweep", []) or []
    # Only pass key columns, not full objects
    compact = [
        {"rpm": s["rpm"], "emf_V": round(s.get("emf_rms_V", 0), 2),
         "Kt": round(s.get("Kt_Nm_per_A", 0), 4)}
        for s in sweep
    ]
    return {
        "speed_sweep": compact,
        "rpm_range":   meta.get("rpm_range", ""),
        "poles":       int((meta.get("geom") or {}).get("p", 0)) * 2,
        "slots":       (meta.get("geom") or {}).get("slots"),
        "Kt_ref":      (em.get("performance") or {}).get("Kt_Nm_per_A"),
        "B_gap_T":     (em.get("performance") or {}).get("B_gap_T"),
        "load_nm":     meta.get("load_nm"),
    }


def _luftspalt_data(results: dict, meta: dict) -> dict:
    em   = results.get("em", {}) or {}
    perf = em.get("performance", {}) or {}
    gap  = em.get("B_gap_data", {}) or {}
    geom = (meta.get("geom") or {})
    br   = gap.get("Br_T", [])
    bt   = gap.get("Bt_T", [])
    # Compute basic harmonic info (peak-to-peak, mean, std)
    import numpy as np
    br_arr = np.array(br) if br else np.array([0.0])
    bt_arr = np.array(bt) if bt else np.array([0.0])
    gap_mm = float(geom.get("statorID", 0) - geom.get("rotorOD", 0)) if geom else 0
    return {
        "B_gap_T":        perf.get("B_gap_T"),
        "lcm_slots_poles":perf.get("lcm_slots_poles"),
        "poles":          int(geom.get("p", 0)) * 2,
        "slots":          geom.get("slots"),
        "airgap_mm":      round(gap_mm, 2),
        "Br_peak_T":      round(float(br_arr.max()), 4),
        "Br_mean_T":      round(float(br_arr.mean()), 4),
        "Br_pp_T":        round(float(br_arr.max() - br_arr.min()), 4),
        "Bt_peak_T":      round(float(bt_arr.max()), 4),
        "T_maxwell_Nm":   perf.get("T_maxwell_Nm"),
        "magShape":       geom.get("magShape"),
        "magTopologie":   TOPOLOGY_LABELS.get(geom.get("magShape", "v"), geom.get("magShape")),
        "rotorOD_mm":     geom.get("rotorOD"),
        "statorID_mm":    geom.get("statorID"),
    }


def _festigkeit_data(results: dict, meta: dict) -> dict:
    fem   = results.get("structural_fem", {}) or {}
    sweep = results.get("structural_sweep", []) or []
    deform = (results.get("deformation") or {}).get("stats", {}) or {}
    mat   = (meta.get("materials") or {}).get("rotor", "")
    geom  = (meta.get("geom") or {})
    return {
        "fem":         {k: v for k, v in fem.items() if not k.startswith("_")},
        "deformation": deform,
        "material":    mat,
        "yield_mpa":   fem.get("yield_mpa"),
        "safety_factor": fem.get("safety_factor"),
        "max_von_mises_MPa": fem.get("max_von_mises_MPa"),
        "max_displacement_um": fem.get("max_displacement_um"),
        "rpm_fem":     fem.get("rpm"),
        "max_safe_rpm": results.get("summary", {}).get("max_safe_rpm"),
        "struct_sweep_sample": sweep[::max(1, len(sweep)//8)] if sweep else [],
        "rotorOD_mm":  geom.get("rotorOD"),
        "shaftD_mm":   geom.get("shaftD"),
    }


def _temperatur_data(results: dict, meta: dict) -> dict:
    therm  = results.get("thermal", {}) or {}
    steady = therm.get("steady", {}) or {}
    losses = therm.get("losses", {}) or {}
    trans  = therm.get("transient", {}) or {}
    segmentierung = results.get("segmentation") or {}
    em_adv = results.get("em_advanced") or {}
    demag  = (em_adv.get("demag") or {}) if not em_adv.get("error") else {}
    # Trim transient to ~10 time points
    t_raw  = trans.get("t", [])
    step   = max(1, len(t_raw) // 10)
    def _thin(key):
        arr = trans.get(key, [])
        return [round(arr[i], 1) for i in range(0, len(arr), step)]

    def _cycle_therm_summary(cyc_key: str) -> dict | None:
        cyc = results.get(cyc_key, {}) or {}
        ct  = cyc.get("thermal", {}) or {}
        if not ct or ct.get("error"):
            return None
        return {
            "T_rated_Nm":   ct.get("T_rated_Nm"),
            "J_rated_Apmm2": ct.get("J_rated_Apmm2"),
            "avg_T_Nm":  ct.get("avg_T_Nm"),
            "avg_rpm":   ct.get("avg_rpm"),
            "avg":       ct.get("avg", {}),
            "peak_T_Nm": ct.get("peak_T_Nm"),
            "peak_rpm":  ct.get("peak_rpm"),
            "peak":      ct.get("peak", {}),
            "warnings":  ct.get("warnings", []),
        }

    out = {
        "designpunkt": {
            "steady":    steady,
            "losses":    losses,
            "warnings":  therm.get("warnings", []),
            "cooling":   therm.get("cooling_label", meta.get("cooling", "")),
            "T_ambient": meta.get("T_ambient", 25),
            "rpm_thermal": meta.get("rpm_thermal"),
            "load_nm":   meta.get("load_nm"),
            "T_rated_Nm": therm.get("T_rated_Nm"),
            "J_Apmm2":   therm.get("J_Apmm2"),
        },
        "transient_t_s":     [round(t_raw[i], 0) for i in range(0, len(t_raw), step)],
        "transient_winding": _thin("T_winding"),
        "transient_magnet":  _thin("T_magnet"),
        "transient_housing": _thin("T_housing"),
        "segmentierung":     segmentierung,
        "demagnetisierung":  demag,
    }
    for cyc_key, label in [("drivecycle", "wltp"),
                            ("drivecycle_vollast", "autobahn_220"),
                            ("drivecycle_anhaenger", "anhaenger")]:
        s = _cycle_therm_summary(cyc_key)
        if s:
            out[f"zyklus_{label}"] = s
    return out


def _fahrzyklus_data(results: dict, meta: dict) -> dict:
    cyc      = results.get("drivecycle", {}) or {}
    vollast  = results.get("drivecycle_vollast", {}) or {}
    anhaenger= results.get("drivecycle_anhaenger", {}) or {}

    def _clean(d: dict) -> dict:
        return {k: v for k, v in d.items()
                if k not in ("chart_b64", "op_points", "vehicle", "thermal")}

    veh = cyc.get("vehicle", meta.get("vehicle", {})) or {}
    out = {
        "wltp":    _clean(cyc),
        "vehicle": {k: veh[k] for k in
                    ("mass_kg","cwA_m2","cr","r_wheel_m","gear_ratio","eta_drive","regen_frac")
                    if k in veh},
        "summary": {k: results.get("summary", {}).get(k)
                    for k in ("cycle_kWh100km","cycle_eta",
                              "vollast_kWh100km","vollast_eta",
                              "anhaenger_kWh100km","anhaenger_T_max_Nm")},
    }
    if vollast and not vollast.get("error"):
        out["autobahn_220"] = _clean(vollast)
    if anhaenger and not anhaenger.get("error"):
        out["anhaenger_alpenpass"] = _clean(anhaenger)
    return out


# ── Expert definitions ────────────────────────────────────────────────────────

_EXPERTS: list[dict] = [
    {
        "key":   "em_feld",
        "title": "EM-Feld-Analyse",
        "role":  "EM-Feld-Experte für Permanentmagnet-Synchronmaschinen",
        "task":  (
            "Bewerte die Feldqualität im Luftspalt und im Rotor (2D-FDM-Schnittmodell). "
            "Beurteile: Höhe der Luftspaltflussdichte (B_gap), Gleichmäßigkeit von Br und Bt über "
            "den Umfang, sichtbare Oberwellenanteile in den Abtastwerten, "
            "Sättigungsrisiko im Blech, Magnetschwächung (B_r-Wert). "
            "Gib 3–5 konkrete Empfehlungen."
        ),
        "selector": _em_field_data,
        "section":  "## EM-Feld-Analyse\n\n",
    },
    {
        "key":   "kennlinien",
        "title": "Kennlinien-Analyse",
        "role":  "Experte für Drehzahl-Drehmoment-Kennlinien von E-Maschinen",
        "task":  (
            "Bewerte den Drehzahlbereich der Maschine anhand des EMF- und Kt-Verlaufs. "
            "Beurteile: Feldschwächungsbedarf (EMK steigt linear → Basis-Drehzahl), "
            "Drehmomentkonstante im Nennbereich, Verfügbarkeit über den gesamten Drehzahlsweep, "
            "Verhältnis Spitzen- zu Nenndrehmoment. "
            "Gib 3–5 konkrete Empfehlungen."
        ),
        "selector": _kennlinien_data,
        "section":  "## Kennlinien-Analyse\n\n",
    },
    {
        "key":   "luftspalt",
        "title": "Luftspalt-Analyse",
        "role":  "Experte für Luftspaltauslegung und Rastmoment",
        "task":  (
            "Bewerte die Luftspaltgeometrie und ihre Auswirkungen. "
            "Beurteile: Luftspaltweite (mechanisch, magnetisch), "
            "LCM(Nuten, Polpaare) als Maß für das Rastmoment "
            "(hohes LCM = geringes Rastmoment), Peak-to-Peak-Variation von Br "
            "als Harmonischen-Indikator, Tangentialfeldanteil (Bt/Br-Verhältnis). "
            "Gib 3–5 konkrete Empfehlungen."
        ),
        "selector": _luftspalt_data,
        "section":  "## Luftspalt-Analyse\n\n",
    },
    {
        "key":   "em3d",
        "title": "3D-Magnetfeld-Validierung (Elmer FEM)",
        "role":  "Experte für 3D-Magnetfeld-FEM (Endeffekte, Schrägung, finite Paketlänge)",
        "task":  (
            "Bewerte die echte 3D-Magnetfeldberechnung (Elmer FEM) im Vergleich zum schnellen "
            "2D-FDM-Schnittmodell. Beurteile: die mittige Luftspaltinduktion 3D "
            "('B_gap_3D_Paketmitte_T') gegen die 2D-FDM-Referenz ('B_gap_2D_FDM_T') — ist die "
            "2D-Näherung belastbar? Den Endeffekt ('endeffekt_rand_zu_mitte' < 1 ⇒ Feldabfall "
            "zu den Stirnseiten durch dreidimensionalen Flussschluss), seine Bedeutung für "
            "Drehmoment/Streuung bei kurzem Blechpaket. Falls Schrägung/Staffelung "
            "('skew_deg'/'skew_segments'/'skew_step_deg') aktiv ist: Wirkung auf Rastmoment "
            "und Oberwellen. Beziehe die Netzgüte ('mesh_knoten') und etwaige Warnungen ein. "
            "Gib 3–5 konkrete Empfehlungen (z. B. wann eine 3D-Rechnung nötig ist, Skew, "
            "Paketlänge)."
        ),
        "selector": _em3d_data,
        "section":  "## 3D-Magnetfeld-Validierung (Elmer FEM)\n\n",
        "condition": lambda results, meta: bool(results.get("em3d")),
    },
    {
        "key":   "festigkeit",
        "title": "Festigkeit und Verformung",
        "role":  "FEM-Experte für Rotor-Strukturmechanik",
        "task":  (
            "Bewerte die strukturmechanische Auslegung des Rotors. "
            "Beurteile: Vergleichsspannung σ_v,max vs. Streckgrenze, Sicherheitsfaktor, "
            "maximale Verschiebung (Luftspaltverengung), kritische Drehzahl, "
            "Übereinstimmung CalculiX vs. analytische Abschätzung. "
            "Gib 3–5 konkrete Empfehlungen mit Grenzdrehzahlen oder Materialvorschlägen."
        ),
        "selector": _festigkeit_data,
        "section":  "## Festigkeit und Verformung\n\n",
    },
    {
        "key":   "temperatur",
        "title": "Thermische Analyse",
        "role":  "Thermik-Experte für elektrische Antriebe",
        "task":  (
            "Bewerte das thermische Verhalten der Maschine – sowohl am Auslegungspunkt "
            "als auch für jeden vorhandenen Fahrzyklus. "
            "Unter 'designpunkt': Endtemperaturen aller Knoten vs. Isolationsklasse H "
            "(180 °C) und Magnet-Dauergrenze (T_op_max des gewählten Grades, NdFeB-N "
            "≈ 80 °C, Curie ≈ 310 °C), Aufheizzeitkonstante, Verlustaufteilung "
            "(Cu/Fe/Magnet), Kühlungseffizienz, Stromdichte J und Dauer-Nennmoment T_Nenn. "
            "Für jeden Zyklus (zyklus_wltp, zyklus_autobahn_220, zyklus_anhaenger): "
            "'avg' = Dauerbetrieb (stationär bei Ø-Verlust), 'peak' = realer "
            "Transienten-Peak auf warmgelaufener Maschine. Beachte besonders die "
            "Magnet-Peaktemperatur (Entmagnetisierung) und ob T_rms das größenbasierte "
            "Dauer-Nennmoment T_rated_Nm übersteigt (thermische Dauerüberlast). "
            "Vergleiche die thermische Belastung zwischen den Zyklen. "
            "Gib 4–6 konkrete Empfehlungen inkl. zyklus-spezifischer Risiken."
        ),
        "selector": _temperatur_data,
        "section":  "## Thermische Analyse\n\n",
    },
    {
        "key":   "kuehlung",
        "title": "Kühlungs-Analyse (Spritzöl-Wickelkopfkühlung)",
        "role":  "Kühlungs-Experte für Spritzöl-/Fluidkühlung elektrischer Antriebe",
        "task":  (
            "Bewerte die experimentelle Spritzöl-Wickelkopfkühlung (FLIP-Fluidsimulation) "
            "im Zusammenhang mit dem thermischen Modell. WICHTIG — Scope ehrlich benennen: die "
            "Studie ist QUALITATIV (visuell-plausibel), liefert KEIN Temperaturfeld und KEINEN "
            "Wärmeübergangskoeffizienten; die Kennwerte ('spritzoel') sind geometrische "
            "Benetzungs-Proxys (benetzte Fläche %, Tropfen-/Fragmentzahl). Beurteile: wie gut "
            "das Öl die Wickelköpfe erreicht (Benetzung mittel/Spitze), Strahlbildung/"
            "Tröpfchen, ob der Strahl ausreichend aufgelöst ist ('strahl_zellen' ≥ ~2, sonst "
            "'strahl_unteraufgeloest'), und ob die Düsenauslegung (Anzahl, Ø, Druck, voller "
            "Ring) zur Benetzung passt. Setze das qualitativ in Bezug zum LPTN-Kühlungskontext "
            "('thermik_kontext': gewählte Kühlung, Wicklungstemperatur, Verluste) — bestätigt "
            "die Benetzung die Annahme einer wirksamen Ölkühlung? Betone, dass für eine echte "
            "Kühlrechnung eine konjugierte CFD-/VOF-Simulation nötig wäre. "
            "Gib 3–5 konkrete Empfehlungen (Düsenlage/-anzahl/-druck, Auflösung, nächste Stufe)."
        ),
        "selector": _kuehlung_data,
        "section":  "## Kühlungs-Analyse (Spritzöl-Wickelkopfkühlung)\n\n",
        "condition": lambda results, meta: bool(results.get("oilspray")),
    },
    {
        "key":   "fahrzyklus",
        "title": "Fahrzyklus-Analyse",
        "role":  "Antriebsstrang-Experte für EV-Verbrauchsanalyse",
        "task":  (
            "Bewerte das Verhalten der Maschine in allen verfügbaren Fahrzyklen. "
            "Beurteile: Verbrauch kWh/100 km, Systemwirkungsgrad und Rekuperationsanteil "
            "für jeden vorhandenen Zyklus (WLTP, Autobahn 220 km/h, Anhänger-Alpenpass). "
            "Erkläre warum Autobahn 220 km/h vor allem die Feldschwächung und hohe Drehzahl "
            "belastet, während der Anhänger-Alpenpass die thermische Auslegung durch "
            "hohes Dauerdrehmoment bei niedrigen Drehzahlen stresst. "
            "Gib 3–5 konkrete Empfehlungen."
        ),
        "selector": _fahrzyklus_data,
        "section":  "## Fahrzyklus-Analyse\n\n",
    },
]


# ── Main function ─────────────────────────────────────────────────────────────

def run_expert_agents(
    results: dict,
    meta: dict,
    model: str = EXPERT_MODEL,
    progress_cb: Callable[[str, int | None], None] | None = None,
) -> dict[str, str]:
    """Run all 6 expert agents and return {expert_key: markdown_text}.

    Each call is independent — failure of one expert does not abort the others.
    """
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    out: dict[str, str] = {}
    # Bedingte Experten (3D-Feld, Kühlung) nur ausführen, wenn die zugehörigen Daten
    # vorliegen — sonst würde der Abschnitt leer bzw. halluziniert werden.
    experts = [e for e in _EXPERTS
               if not e.get("condition") or e["condition"](results, meta)]
    n = len(experts)

    for idx, exp in enumerate(experts):
        _log(f"👤 Experte {idx+1}/{n}: {exp['title']}…", int(5 + idx * 90 / n))
        try:
            data = exp["selector"](results, meta)
            data_json = json.dumps(data, ensure_ascii=False, indent=2)

            prompt = (
                f"Du bist ein {exp['role']}. "
                f"Antworte auf Deutsch, sachlich und prägnant.\n\n"
                f"{exp['task']}\n\n"
                f"Analysedaten (JSON):\n```json\n{data_json}\n```\n\n"
                f"Schreibe deinen Befund als zusammenhängenden Fließtext mit 2–4 Absätzen, "
                f"gefolgt von einer Aufzählungsliste der Empfehlungen (3–5 Punkte).\n"
                f"FORMATIERUNGSREGELN – unbedingt einhalten:\n"
                f"- Jeder Absatz ist eine einzige zusammenhängende Textzeile oder mehrere "
                f"Sätze ohne harte Zeilenumbrüche mittendrin.\n"
                f"- Kein Zeilenumbruch nach einzelnen Wörtern, Zahlen oder Einheiten.\n"
                f"- Absätze werden durch genau eine Leerzeile getrennt.\n"
                f"- Keine Überschrift, keine Code-Blöcke, keine Einleitungsfloskeln.\n"
                f"Beginne direkt mit dem ersten Satz des Befunds."
            )
            text = _call(prompt, model=model)
            out[exp["key"]] = text
            _log(f"  ✓ {exp['title']}: {len(text)} Zeichen", None)
        except Exception as e:
            out[exp["key"]] = f"*Analyse nicht verfügbar: {e}*"
            _log(f"  ⚠ {exp['title']} fehlgeschlagen: {e}", None)

    _log(f"✓ Alle {n} Experten fertig", 98)
    return out


def assemble_expert_section(
    expert_outputs: dict[str, str],
    img_map: dict | None = None,
) -> str:
    """Combine expert outputs into a markdown section with images and normalized prose."""
    img_map = img_map or {}
    parts = ["# Expertenbewertung\n"]
    for exp in _EXPERTS:
        key  = exp["key"]
        text = expert_outputs.get(key, "")
        if not text:
            continue
        # Normalise prose (fix mid-sentence line breaks from the LLM)
        text = _normalize_text(text)
        # Section header
        section_md = exp["section"]
        # Insert relevant images immediately after the header
        img_md = ""
        for img_key in _EXPERT_IMAGES.get(key, []):
            entry = img_map.get(img_key)
            if entry:
                img_md += f"\n![{entry['title']}]({entry['path']})\n\n"
        parts.append(section_md + img_md + text + "\n\n")
    return "\n".join(parts)


# ── Comparative variant evaluation (6 experts judge ALL variants together) ──

def run_expert_agents_compare(
    variants: list[dict],
    model: str = EXPERT_MODEL,
    progress_cb: Callable[[str, int | None], None] | None = None,
) -> dict[str, str]:
    """Lasse die 6 Experten ALLE Varianten VERGLEICHEND bewerten.

    ``variants`` ist eine Liste ``[{"name", "results", "meta"}, …]`` (Variante 0 =
    Basis). Jeder Experte erhält seinen Fachdaten-Ausschnitt für jede Variante und
    schreibt einen vergleichenden Befund inkl. **Vor- und Nachteilen je Variante**.
    Rückgabe: ``{expert_key: markdown_text}``.
    """
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    out: dict[str, str] = {}
    names = [v.get("name") or f"Variante {i+1}" for i, v in enumerate(variants)]
    # Bedingte Experten (3D-Feld, Kühlung) mitnehmen, sobald IRGENDEINE Variante die Daten hat.
    def _any(cond):
        return any(cond(v.get("results", {}) or {}, v.get("meta", {}) or {}) for v in variants)
    experts = [e for e in _EXPERTS if not e.get("condition") or _any(e["condition"])]
    n = len(experts)

    for idx, exp in enumerate(experts):
        _log(f"👤 Experte {idx+1}/{n} (Vergleich): {exp['title']}…", int(5 + idx * 90 / n))
        try:
            per_variant = []
            for v, nm in zip(variants, names):
                try:
                    d = exp["selector"](v.get("results", {}) or {}, v.get("meta", {}) or {})
                except Exception as se:
                    d = {"fehler": str(se)}
                per_variant.append({"variante": nm, "daten": d})
            data_json = json.dumps(per_variant, ensure_ascii=False, indent=2)

            prompt = (
                f"Du bist ein {exp['role']}. Antworte auf Deutsch, sachlich und prägnant.\n\n"
                f"Es werden {len(variants)} Motor-Varianten VERGLICHEND bewertet "
                f"(Variante 0 = Basis): {', '.join(names)}.\n\n"
                f"Deine Fachaufgabe: {exp['task']}\n\n"
                f"Fachdaten je Variante (JSON):\n```json\n{data_json}\n```\n\n"
                f"Schreibe einen VERGLEICHENDEN Befund aus DEINER Fachsicht:\n"
                f"1. Ein bis zwei Absätze Fließtext, in denen du die Varianten anhand "
                f"konkreter Zahlen gegenüberstellst (was ist besser/schlechter und warum).\n"
                f"2. Danach für JEDE Variante eine kurze Zeile mit Vor- und Nachteilen im Format:\n"
                f"   - **<Variantenname>** — Vorteile: … — Nachteile: …\n"
                f"   (KEINE senkrechten Striche '|' verwenden)\n"
                f"3. Abschließend ein Satz, welche Variante aus deiner Fachsicht die beste ist.\n\n"
                f"FORMATIERUNGSREGELN – unbedingt einhalten:\n"
                f"- Absätze sind zusammenhängende Zeilen ohne harte Umbrüche mittendrin.\n"
                f"- Kein Zeilenumbruch nach einzelnen Wörtern, Zahlen oder Einheiten.\n"
                f"- Keine Überschrift, keine Code-Blöcke, keine Markdown-Tabellen, keine Floskeln.\n"
                f"Beginne direkt mit dem ersten Satz."
            )
            text = _call(prompt, model=model)
            out[exp["key"]] = text
            _log(f"  ✓ {exp['title']}: {len(text)} Zeichen", None)
        except Exception as e:
            out[exp["key"]] = f"*Vergleichsanalyse nicht verfügbar: {e}*"
            _log(f"  ⚠ {exp['title']} fehlgeschlagen: {e}", None)

    _log(f"✓ Alle {n} Experten (Vergleich) fertig", 98)
    return out


def assemble_expert_section_compare(expert_outputs: dict[str, str]) -> str:
    """Vergleichende Experten-Befunde zu einem Markdown-Abschnitt zusammenfügen
    (h2-Titel, h3 je Experte — passt in die nummerierte Berichtsstruktur)."""
    parts = ["## 10. Agentische Experten-Bewertung der Varianten (6 Experten)\n",
             "_Sechs Fachexperten beurteilen die Varianten vergleichend und nennen "
             "Vor- und Nachteile je Variante._\n"]
    for exp in _EXPERTS:
        text = expert_outputs.get(exp["key"], "")
        if not text:
            continue
        text = _normalize_text(text)
        # exp["section"] ist eine h2-Überschrift ("## …") → auf h3 absenken
        heading = "### " + exp["section"].lstrip("# ").strip()
        parts.append(heading + "\n\n" + text + "\n\n")
    return "\n".join(parts)
