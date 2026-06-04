"""Agentic multi-expert evaluation for E-machine analysis results.

Each expert receives a focused slice of results.json and returns a German
technical assessment as markdown text. Experts run sequentially (same Ollama
instance) and their outputs are later assembled into the full report.
"""

from __future__ import annotations
import json, math, re, urllib.request
from typing import Callable


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
    "em_feld":    ["airgap"],
    "kennlinien": ["em_curve"],
    "luftspalt":  ["airgap"],
    "festigkeit": ["structural", "deformation"],
    "temperatur": ["thermal"],
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
    return {
        "performance":    perf,
        "B_gap_T":        perf.get("B_gap_T"),
        "Kt_Nm_per_A":    perf.get("Kt_Nm_per_A"),
        "T_maxwell_Nm":   perf.get("T_maxwell_Nm"),
        "lcm_slots_poles":perf.get("lcm_slots_poles"),
        "poles":          int(geom.get("p", 0)) * 2,
        "slots":          geom.get("slots"),
        "magnet":         meta.get("materials", {}).get("magnet", ""),
        "airgap_mm":      geom.get("statorID", 0) - geom.get("rotorOD", 0) if geom else 0,
        "Br_T_samples":   [round(br[i], 4) for i in range(0, len(br), step)][:60],
        "Bt_T_samples":   [round(bt[i], 4) for i in range(0, len(bt), step)][:60],
        "theta_deg_samples": [round(th[i], 1) for i in range(0, len(th), step)][:60],
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
            "Bewerte die Feldqualität im Luftspalt und im Rotor. "
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
    n = len(_EXPERTS)

    for idx, exp in enumerate(_EXPERTS):
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
