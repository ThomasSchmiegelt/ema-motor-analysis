"""Fortlaufendes LLM-Trainingsfile für E-Maschinen-Auslegungen.

Jede abgeschlossene Berechnung wird als EINE JSONL-Zeile (instruction/input/output
Format für SFT-Finetuning) angehängt:

    {"project_id", "timestamp",
     "instruction": <Geometrie + Material als lesbares Datenblatt>,
     "input": "",
     "output":      <berechnete Kennwerte: Leistung, Flussdichte, Temperatur …>,
     "label": "gut"|"schlecht"|null,   # vom Nutzer im Ergebnis-Tab gesetzt
     "comment": "",
     "metrics": { … flache Kennzahlen für spätere Auswertung … }}

Die Datei wird **per Projekt-ID upsertet** (kein Duplikat bei Nachrechnung oder
nachträglicher Bewertung — die Zeile mit gleicher project_id wird ersetzt).

Die Beschreibung (instruction) wird aus dem Maschinen-Datenblatt von
``ema_chat._machine_datasheet`` gebaut, die Ergebnis-Beschreibung (output) aus
``results["summary"]`` — beides ist die einzige Wahrheitsquelle der Auslegung.
"""

from __future__ import annotations

import json
import os
import datetime

PROJECTS_ROOT = os.path.expanduser("~/cae_projekte")
TRAINING_ROOT = os.path.join(PROJECTS_ROOT, "_training")
SFT_FILE = os.path.join(TRAINING_ROOT, "dataset_sft.jsonl")
VLM_FILE = os.path.join(TRAINING_ROOT, "dataset_vlm.jsonl")

# Kanonische Bild-Schlüssel je Projekt (key, projekt-relativer Pfad, Titel).
# Spiegelt die `pairs`-Liste in ema_report.build_context — nur die deterministischen
# Auswertungsbilder, NICHT die Animations-Frames (zu viele, redundant).
IMAGE_PAIRS = [
    ("cross_section", "cad_images/motor_cross_section.png", "Querschnitt (XY-Ebene)"),
    ("side_view",     "cad_images/motor_side_view.png",     "Axialschnitt (XZ-Ebene)"),
    ("em_field",      "charts/em_field.png",                 "FDM-Magnetfeld im Leerlauf (Flussdichte |B|)"),
    ("em_field_load", "charts/em_field_load.png",            "FDM-Magnetfeld unter Last (Ankerrückwirkung)"),
    ("airgap",        "charts/airgap.png",                   "Luftspaltflussdichte über dem Umfang"),
    ("em_curve",      "charts/em_curve.png",                 "EM-Kennlinie über Drehzahl"),
    ("structural",    "charts/structural_sweep.png",         "Strukturkennlinie (Spannung über Drehzahl)"),
    ("deformation",   "charts/deformation.png",              "FEM-Verformung des Rotors"),
    ("thermal",       "charts/thermal.png",                  "Thermische Analyse (LPTN)"),
    ("drivecycle",    "charts/drivecycle.png",               "Fahrzyklus-Auswertung"),
    ("drivecycle_vollast",   "charts/drivecycle_vollast.png",   "Autobahn-Vollgas 220 km/h"),
    ("drivecycle_anhaenger", "charts/drivecycle_anhaenger.png", "Anhänger-Alpenpass"),
]


def collect_images(project_id: str, project_dir: str | None = None) -> list[dict]:
    """Vorhandene Auswertungsbilder eines Projekts als Pfad-Referenzen.

    ``path`` ist relativ zu ``~/cae_projekte`` (``<project_id>/charts/…``) — portabel,
    nicht inline (Base64 würde das Text-Dataset sprengen). Es werden nur Bilder
    aufgenommen, die tatsächlich auf der Platte liegen.
    """
    project_dir = project_dir or os.path.join(PROJECTS_ROOT, project_id)
    out = []
    for key, rel, title in IMAGE_PAIRS:
        if os.path.exists(os.path.join(project_dir, rel)):
            out.append({"key": key, "title": title,
                        "path": f"{project_id}/{rel}"})
    return out


# ── Text builders ────────────────────────────────────────────────────────────

def build_instruction(meta: dict) -> str:
    """Geometrie + Material als verbindliche Auslegungs-Spezifikation (Text)."""
    try:
        from ema_chat import _machine_datasheet
        sheet = _machine_datasheet(meta or {})
    except Exception:
        sheet = ""
    head = ("Beschreibe und bewerte die folgende Auslegung einer permanenterregten "
            "Synchronmaschine (IPM). Gib die zu erwartenden Kennwerte "
            "(Leistung/Drehmoment, Luftspaltflussdichte, Temperaturen, Festigkeit, "
            "Verbrauch) an und beurteile, ob die Auslegung sinnvoll ist.")
    return f"{head}\n\n{sheet}".strip() if sheet else head


def _g(x, unit="", nd=2):
    if x is None or x == "":
        return None
    if isinstance(x, float):
        x = round(x, nd)
        if x == int(x):
            x = int(x)
    return f"{x}{(' ' + unit) if unit else ''}"


def build_output(results: dict) -> str:
    """Berechnete Kennwerte als lesbarer deutscher Ergebnis-Text."""
    s = (results or {}).get("summary", {}) or {}
    adv = (results or {}).get("em_advanced", {}) or {}
    lines = ["BERECHNETE KENNWERTE:"]

    def add(label, val):
        if val is not None:
            lines.append(f"- {label}: {val}")

    add("Luftspalt-Flussdichte B_gap (Peak)", _g(s.get("B_gap_T"), "T", 3))
    add("Drehmomentkonstante Kt", _g(s.get("Kt_Nm_per_A"), "Nm/A", 3))
    add("Maxwell-Moment", _g(s.get("T_maxwell_Nm"), "Nm", 1))
    add("Max. sichere Drehzahl", _g(s.get("max_safe_rpm"), "U/min", 0))
    add("Rotor-Masse", _g(s.get("mass_g"), "g", 0))
    add("Eisenverluste (Schätzung)", _g(s.get("P_fe_W_est"), "W", 1))
    add("Gesamtverluste P_ges", _g(s.get("P_total_W"), "W", 0))
    add("Temperatur Wicklung", _g(s.get("T_winding_C"), "°C", 1))
    add("Temperatur Magnet", _g(s.get("T_magnet_C"), "°C", 1))
    add("Temperatur Gehäuse", _g(s.get("T_housing_C"), "°C", 1))
    add("Kühlung", s.get("cooling") or None)
    if adv:
        add("Kurzschlussstrom Isc", _g(adv.get("Isc_A"), "A", 0))
        add("Ld", _g(adv.get("Ld_mH"), "mH", 3))
        add("Lq", _g(adv.get("Lq_mH"), "mH", 3))
        add("Saliency ξ=Lq/Ld", _g(adv.get("saliency"), "", 2))
        demag = (adv.get("demag") or {}).get("risk")
        add("Demagnetisierungs-Risiko", demag)
    # Drive-cycle (any of the available cycles)
    add("Verbrauch (Zyklus)", _g(s.get("cycle_kWh100km"), "kWh/100km", 2))
    add("Wirkungsgrad Antrieb (Zyklus)", _g(s.get("cycle_eta"), "", 3))
    add("Verbrauch Vollast", _g(s.get("vollast_kWh100km"), "kWh/100km", 2))
    add("Verbrauch Anhänger", _g(s.get("anhaenger_kWh100km"), "kWh/100km", 2))
    return "\n".join(lines)


def build_metrics(results: dict) -> dict:
    """Flache numerische Kennzahlen (für spätere Tabellen-/Statistik-Auswertung)."""
    s = (results or {}).get("summary", {}) or {}
    adv = (results or {}).get("em_advanced", {}) or {}
    out = {
        "B_gap_T":          s.get("B_gap_T"),
        "Kt_Nm_per_A":      s.get("Kt_Nm_per_A"),
        "T_maxwell_Nm":     s.get("T_maxwell_Nm"),
        "max_safe_rpm":     s.get("max_safe_rpm"),
        "mass_g":           s.get("mass_g"),
        "P_total_W":        s.get("P_total_W"),
        "T_winding_C":      s.get("T_winding_C"),
        "T_magnet_C":       s.get("T_magnet_C"),
        "cycle_kWh100km":   s.get("cycle_kWh100km"),
        "Isc_A":            adv.get("Isc_A"),
        "demag_risiko":     (adv.get("demag") or {}).get("risk"),
    }
    return {k: v for k, v in out.items() if v is not None}


# ── Heuristic auto-label (nur Vorschlag, der Nutzer bestätigt/überschreibt) ──

def auto_label(results: dict, meta: dict | None = None) -> dict:
    """Grobe Heuristik 'gut/schlecht' aus den Kennwerten — als VORSCHLAG.

    Gibt {"suggestion": "gut"|"schlecht"|None, "reasons": [...]} zurück.
    """
    s = (results or {}).get("summary", {}) or {}
    reasons = []
    bad = 0
    t_w = s.get("T_winding_C")
    t_m = s.get("T_magnet_C")
    if t_w is not None and t_w > 180:
        reasons.append(f"Wicklungstemperatur hoch ({t_w:.0f} °C)"); bad += 1
    if t_m is not None and t_m > 150:
        reasons.append(f"Magnettemperatur kritisch ({t_m:.0f} °C)"); bad += 1
    rpm = s.get("max_safe_rpm")
    payload = (meta or {}).get("payload") or {}
    rpm_to = payload.get("rpm_to")
    if rpm is not None and rpm_to and rpm < rpm_to:
        reasons.append(f"max. sichere Drehzahl ({rpm:.0f}) < Maximaldrehzahl ({rpm_to:.0f})"); bad += 1
    bgap = s.get("B_gap_T")
    if bgap is not None and bgap < 0.6:
        reasons.append(f"niedrige Luftspaltflussdichte ({bgap:.2f} T)"); bad += 1
    if not reasons:
        reasons.append("keine Grenzwertverletzung erkannt")
    return {"suggestion": ("schlecht" if bad else "gut"), "reasons": reasons}


# ── JSONL store (upsert by project_id) ───────────────────────────────────────

def _read_all() -> list[dict]:
    if not os.path.exists(SFT_FILE):
        return []
    recs = []
    with open(SFT_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                recs.append(json.loads(line))
            except Exception:
                continue
    return recs


def _write_all(recs: list[dict]) -> None:
    os.makedirs(TRAINING_ROOT, exist_ok=True)
    tmp = SFT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for r in recs:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    os.replace(tmp, SFT_FILE)


def upsert(project_id: str, meta: dict, results: dict,
           label=None, comment: str = "", project_dir: str | None = None) -> dict:
    """Schreibt/aktualisiert die Trainingszeile für project_id.

    Eine bestehende Bewertung (label/comment) bleibt erhalten, wenn die Funktion
    beim Nachrechnen ohne neues Label aufgerufen wird. Bild-Pfade werden mitgeführt
    und das VLM-Manifest danach neu erzeugt.
    """
    recs = _read_all()
    existing = next((r for r in recs if r.get("project_id") == project_id), None)
    rec = {
        "project_id":  project_id,
        "timestamp":   datetime.datetime.now().isoformat(timespec="seconds"),
        "instruction": build_instruction(meta),
        "input":       "",
        "output":      build_output(results),
        "label":       label if label is not None else (existing or {}).get("label"),
        "comment":     comment or (existing or {}).get("comment", ""),
        "metrics":     build_metrics(results),
        "images":      collect_images(project_id, project_dir),
    }
    if existing is not None:
        recs = [rec if r.get("project_id") == project_id else r for r in recs]
    else:
        recs.append(rec)
    _write_all(recs)
    export_vlm(recs)
    return rec


def set_label(project_id: str, label, comment: str = "") -> dict | None:
    """Setzt nur Label/Kommentar einer bestehenden Zeile (vom Ergebnis-Tab)."""
    recs = _read_all()
    found = None
    for r in recs:
        if r.get("project_id") == project_id:
            r["label"] = label
            r["comment"] = comment
            r["rated_at"] = datetime.datetime.now().isoformat(timespec="seconds")
            found = r
            break
    if found is None:
        return None
    _write_all(recs)
    export_vlm(recs)
    return found


# ── VLM-Manifest (ein Eintrag JE BILD, multimodales SFT-Format) ──────────────

def _vlm_prompt(rec: dict, img: dict) -> str:
    """Bild-spezifischer Prompt: Bildkontext + Auslegungs-Datenblatt."""
    return (f"Das folgende Bild zeigt: {img.get('title', img.get('key'))} "
            f"einer permanenterregten Synchronmaschine (IPM).\n\n"
            f"{rec.get('instruction', '')}\n\n"
            f"Beschreibe, was in diesem Bild zu sehen ist, und beurteile die "
            f"Auslegung aus dieser Sicht.")


def _vlm_answer(rec: dict) -> str:
    ans = rec.get("output", "")
    label = rec.get("label")
    if label:
        cmt = rec.get("comment", "")
        ans += f"\n\nGesamtbewertung dieser Auslegung: {label}."
        if cmt:
            ans += f" ({cmt})"
    return ans


def export_vlm(recs: list[dict] | None = None) -> int:
    """Erzeugt ``dataset_vlm.jsonl`` aus den SFT-Records — EIN Eintrag je Bild im
    messages/content-Format (Bildpfad absolut, fürs Vision-Finetuning). Nur Bilder,
    die tatsächlich auf der Platte liegen. Gibt die Anzahl Einträge zurück."""
    if recs is None:
        recs = _read_all()
    os.makedirs(TRAINING_ROOT, exist_ok=True)
    n = 0
    tmp = VLM_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        for rec in recs:
            for img in rec.get("images", []) or []:
                abs_path = os.path.join(PROJECTS_ROOT, img.get("path", ""))
                if not os.path.exists(abs_path):
                    continue
                prompt = _vlm_prompt(rec, img)
                answer = _vlm_answer(rec)
                entry = {
                    "project_id": rec.get("project_id"),
                    "image_key":  img.get("key"),
                    "image":      abs_path,
                    "label":      rec.get("label"),
                    "messages": [
                        {"role": "user", "content": [
                            {"type": "image", "image": abs_path},
                            {"type": "text",  "text": prompt}]},
                        {"role": "assistant", "content": [
                            {"type": "text", "text": answer}]},
                    ],
                }
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                n += 1
    os.replace(tmp, VLM_FILE)
    return n


def get_record(project_id: str) -> dict | None:
    for r in _read_all():
        if r.get("project_id") == project_id:
            return r
    return None


def stats() -> dict:
    recs = _read_all()
    n = len(recs)
    gut = sum(1 for r in recs if r.get("label") == "gut")
    schlecht = sum(1 for r in recs if r.get("label") == "schlecht")
    n_images = sum(len(r.get("images", []) or []) for r in recs)
    n_vlm = 0
    if os.path.exists(VLM_FILE):
        with open(VLM_FILE, encoding="utf-8") as f:
            n_vlm = sum(1 for line in f if line.strip())
    return {
        "n_total":     n,
        "n_gut":       gut,
        "n_schlecht":  schlecht,
        "n_unbewertet": n - gut - schlecht,
        "n_images":    n_images,
        "n_vlm":       n_vlm,
        "file":        SFT_FILE,
        "vlm_file":    VLM_FILE,
        "exists":      os.path.exists(SFT_FILE),
        "vlm_exists":  os.path.exists(VLM_FILE),
    }
