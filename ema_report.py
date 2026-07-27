"""LLM-generated, illustrated PDF report for an analysis project.

Pipeline:
  project_dir/results.json + meta.json  →  compact context dict
  context  →  prompt to ministral-3:14b (Ollama, OpenAI-compat REST)
  LLM markdown  →  post-process to insert ![…](…) image refs
  markdown  →  pandoc + pdflatex  →  project_dir/bericht.pdf

The prompt instructs the LLM to use `[BILD:<key>]` placeholders at natural
locations; the post-processor replaces them with the matching markdown image
references and copies all referenced PNGs into a local sub-dir so pandoc can
find them by relative path.
"""

from __future__ import annotations
import os, json, re, shutil, subprocess, urllib.request
from typing import Iterable

from ema_topology import TOPOLOGY_LABELS


OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "ministral-3:14b"


# ── Context extraction ──────────────────────────────────────────────────────

def build_context(project_dir: str) -> dict:
    """Compact dict of metrics + image map for the report."""
    meta, results = {}, {}
    mp = os.path.join(project_dir, "meta.json")
    rp = os.path.join(project_dir, "results.json")
    if os.path.exists(mp):
        with open(mp) as f: meta = json.load(f)
    if os.path.exists(rp):
        with open(rp) as f: results = json.load(f)

    # Image keys → relative paths from project_dir
    imgs = {}
    pairs = [
        ("cross_section", "cad_images/motor_cross_section.png", "Querschnitt (XY-Ebene)"),
        ("side_view",     "cad_images/motor_side_view.png",     "Axialschnitt (XZ-Ebene)"),
        ("em_field",      "charts/em_field.png",                 "FDM-Magnetfeld im Leerlauf (Flussdichte |B|)"),
        ("em_field_load", "charts/em_field_load.png",            "FDM-Magnetfeld unter Last (Ankerrückwirkung)"),
        ("airgap",        "charts/airgap.png",                   "Luftspaltflussdichte"),
        ("em_curve",      "charts/em_curve.png",                 "EM-Kennlinie über Drehzahl"),
        ("structural",    "charts/structural_sweep.png",         "Strukturkennlinie"),
        ("deformation",   "charts/deformation.png",              "FEM-Verformung"),
        ("thermal",       "charts/thermal.png",                  "Thermische Analyse (LPTN)"),
        ("drivecycle",    "charts/drivecycle.png",               "Fahrzyklus-Auswertung"),
        # Echte 3D-Magnetfeldberechnung (Elmer) — nur vorhanden, wenn ein 3D-Lauf lief.
        ("em3d_model_iso",   "charts/em3d_model_iso.png",   "3D-Modell (Isometrie, aufgeschnitten)"),
        ("em3d_model_axial", "charts/em3d_model_axial.png", "Magnet-/Polanordnung (Blick entlang der Achse)"),
        ("em3d_field3d",     "charts/em3d_field3d.png",     "3D-Feld |B| (aufgeschnitten)"),
        ("em3d_slice_mid",   "charts/em3d_slice_mid.png",   "|B|-Schnitt in der Paketmitte (z = L/2)"),
        ("em3d_endeffect",   "charts/em3d_endeffect.png",   "Endeffekt: axialer Verlauf der Luftspaltinduktion B(z)"),
        ("em3d_airgap_2d3d", "charts/em3d_airgap_2d3d.png", "Luftspaltinduktion: 2D-FDM vs. 3D-Elmer"),
        # Experimentelle Spritzöl-Kühlung (Blender/Mantaflow) — nur bei durchgeführtem 💧-Lauf.
        ("oil_coverage",  "charts/oil_coverage.png",  "Benetzungs-Heatmap am Wickelkopf (kumulierte Ölabdeckung)"),
        ("oil_wetting",   "charts/oil_wetting.png",   "Benetzte Wickelkopf-Fläche über die Zeit"),
        ("oil_droplets",  "charts/oil_droplets.png",  "Tröpfchenbildung / Fragmentierung über die Zeit"),
        # Quantitative OpenFOAM-VOF-Kühlung (interFoam) — nur bei durchgeführtem 🌊-Lauf.
        ("cfd_wetting",   "charts/cfd_wetting.png",   "VOF-Benetzung über die Zeit (OpenFOAM interFoam)"),
    ]
    for key, rel, title in pairs:
        full = os.path.join(project_dir, rel)
        if os.path.exists(full):
            imgs[key] = {"path": rel, "title": title}

    # Compact metric extraction (LLM doesn't need everything)
    summary = results.get("summary") or {}
    geom    = meta.get("geom") or {}
    therm   = results.get("thermal") or {}
    cyc     = results.get("drivecycle") or {}
    fem     = results.get("structural_fem") or {}

    vollast   = results.get("drivecycle_vollast") or {}
    anhaenger = results.get("drivecycle_anhaenger") or {}
    if os.path.exists(os.path.join(project_dir, "charts", "drivecycle_vollast.png")):
        imgs["drivecycle_vollast"] = {
            "path":  "charts/drivecycle_vollast.png",
            "title": "Autobahn-Vollgas 220 km/h",
        }
    if os.path.exists(os.path.join(project_dir, "charts", "drivecycle_anhaenger.png")):
        imgs["drivecycle_anhaenger"] = {
            "path":  "charts/drivecycle_anhaenger.png",
            "title": "Anhänger-Alpenpass",
        }

    ctx = {
        "label":     meta.get("label", os.path.basename(project_dir)),
        "created":   meta.get("created", ""),
        "geometry": {
            "rotorOD":  geom.get("rotorOD"),
            "statorOD": geom.get("statorOD"),
            "statorID": geom.get("statorID"),
            "shaftD":   geom.get("shaftD"),
            "poles":    int(geom.get("p", 0)) * 2,
            "slots":    geom.get("slots"),
            "magShape": geom.get("magShape"),
            "magTopologie": TOPOLOGY_LABELS.get(geom.get("magShape", "v"),
                                                geom.get("magShape")),
            "axial":    meta.get("axial_len"),
            "n_faces":  (results.get("geometry") or {}).get("n_faces"),
            "mass_kg":  round((results.get("geometry") or {}).get("mass_g", 0) / 1000, 2),
        },
        "materials": {
            "rotor":   summary.get("rotor_lam"),
            "stator":  summary.get("stator_lam"),
            "hairpin": summary.get("hairpin"),
            "magnet":  summary.get("magnet"),
        },
        "em": {
            "B_gap_T":      summary.get("B_gap_T"),
            "Kt_Nm_per_A":  summary.get("Kt_Nm_per_A"),
            "T_maxwell_Nm": summary.get("T_maxwell_Nm"),
            "lcm":          summary.get("lcm_slots_poles"),
        },
        "structural": {
            "rpm_fem":        fem.get("rpm"),
            "sigma_v_max_MPa":fem.get("max_von_mises_MPa"),
            "safety_factor":  fem.get("safety_factor"),
            "u_max_um":       fem.get("max_displacement_um"),
            "max_safe_rpm":   summary.get("max_safe_rpm"),
        },
        "thermal": {
            "cooling":    summary.get("cooling"),
            "T_winding":  summary.get("T_winding_C"),
            "T_magnet":   summary.get("T_magnet_C"),
            "T_housing":  summary.get("T_housing_C"),
            "P_total_W":  summary.get("P_total_W"),
            "warnings":   therm.get("warnings", []),
        },
        "drivecycle": {
            "name":          cyc.get("cycle_name"),
            "distance_km":   cyc.get("distance_km"),
            "kWh_per_100km": cyc.get("E_per_100km_kWh"),
            "eta_drive":     cyc.get("eta_drive"),
            "regen_share":   cyc.get("regen_share"),
            "v_max_kmh":     cyc.get("v_max_kmh"),
        },
        "vollast_zyklus": {
            "name":          vollast.get("cycle_name"),
            "distance_km":   vollast.get("distance_km"),
            "kWh_per_100km": vollast.get("E_per_100km_kWh"),
            "eta_drive":     vollast.get("eta_drive"),
            "regen_share":   vollast.get("regen_share"),
            "v_max_kmh":     vollast.get("v_max_kmh"),
            "T_max_Nm":      vollast.get("T_max"),
            "rpm_max":       vollast.get("rpm_max"),
            "thermal_avg":   (vollast.get("thermal") or {}).get("avg"),
            "thermal_peak":  (vollast.get("thermal") or {}).get("peak"),
        } if vollast and not vollast.get("error") else None,
        "anhaenger_alpenpass": {
            "name":          anhaenger.get("cycle_name"),
            "distance_km":   anhaenger.get("distance_km"),
            "kWh_per_100km": anhaenger.get("E_per_100km_kWh"),
            "eta_drive":     anhaenger.get("eta_drive"),
            "regen_share":   anhaenger.get("regen_share"),
            "T_max_Nm":      anhaenger.get("T_max"),
            "T_rms_Nm":      anhaenger.get("T_rms"),
            "v_avg_kmh":     anhaenger.get("v_avg_kmh"),
            "thermal_avg":   (anhaenger.get("thermal") or {}).get("avg"),
            "thermal_peak":  (anhaenger.get("thermal") or {}).get("peak"),
            "thermal_warnings": (anhaenger.get("thermal") or {}).get("warnings", []),
        } if anhaenger and not anhaenger.get("error") else None,
        "images": list(imgs.keys()),
        "_img_map": imgs,
    }

    seg = results.get("segmentation") or {}
    if seg:
        ctx["segmentierung"] = {
            "n_axial":         seg.get("n_ax"),
            "n_umfang":        seg.get("n_circ"),
            "verlustfaktor":   seg.get("k_seg"),
            "P_Mag_unsegm_W":  seg.get("P_Mag_unseg_W"),
            "P_Mag_segm_W":    seg.get("P_Mag_eddy_W"),
            "skintiefe_mm":    seg.get("delta_skin_mm"),
            "warnung_wirkungslos": seg.get("warning"),
        }

    adv = results.get("em_advanced") or {}
    if adv and not adv.get("error"):
        dm = adv.get("demag") or {}
        ctx["em_erweitert"] = {
            "Ld_mH":  adv.get("Ld_mH"),
            "Lq_mH":  adv.get("Lq_mH"),
            "salienz_xi": adv.get("xi"),
            "Isc_A":  adv.get("Isc_A"),
            "psi_pm_Wb": adv.get("psi_pm_Wb"),
            "mtpa":   adv.get("mtpa"),
            "demag": {
                "magnet_temp_C": dm.get("magnet_temp_C"),
                "Br_T":          dm.get("Br_T"),
                "reserve_T":     dm.get("margin_T"),
                "risiko":        dm.get("risk"),
            },
        }

    # Echte 3D-Magnetfeldberechnung (Elmer) — falls für dieses Projekt durchgeführt.
    e3 = results.get("em3d") or {}
    if e3:
        cmp3 = e3.get("compare_2d") or {}
        bz = e3.get("b_gap_axial") or []
        endeff = None
        if bz and max(bz) > 0:
            endeff = round(min(bz) / max(bz), 3)         # Stirnseite/Mitte
        mz = e3.get("mesh_zones") or {}
        ctx["em3d"] = {
            "B_gap_3D_mid_T":  e3.get("b_gap_mid_peak"),
            "B_gap_2D_FDM_T":  cmp3.get("B_gap_2D"),
            "B_gap_3D_cmp_T":  cmp3.get("B_gap_3D_mid"),
            "endeffekt_rand_zu_mitte": endeff,
            "skew_deg":        e3.get("skew_deg"),
            "skew_segments":   e3.get("skew_segments"),
            "skew_step_deg":   e3.get("skew_step_deg"),
            "mesh_knoten":     (e3.get("mesh") or {}).get("n_nodes"),
            "n_barrieren":     (e3.get("mesh") or {}).get("n_barriers"),
            "zone_luftspalt":  mz.get("gap_cl"),
            "zone_magnet":     mz.get("mag_cl"),
            "zone_grob":       mz.get("mesh_cl"),
            "axial_mm":        e3.get("axial_mm"),
            "warnungen":       e3.get("warnings", []),
        }

    # Experimentelle Spritzöl-Kühlung (Blender/Mantaflow) — falls ein 💧-Lauf im Projekt liegt.
    # QUALITATIV: geometrische Benetzungs-Proxys, KEIN Wärmeübergang/Temperaturfeld.
    oil = results.get("oilspray") or {}
    if oil:
        om = oil.get("metrics") or {}
        oc = oil.get("config") or {}
        ctx["oilspray"] = {
            "benetzung_mittel_pct": om.get("wetted_pct_mean"),
            "benetzung_spitze_pct": om.get("wetted_pct_peak"),
            "tropfen_spitze":       om.get("droplets_peak"),
            "n_frames":             om.get("n_frames"),
            "voxel_mm":             om.get("voxel_mm"),
            "strahl_zellen":        om.get("jet_cells"),
            "strahl_unteraufgeloest": om.get("jet_underres"),
            "aufloesung":           oc.get("resolution"),
            "duesen":               oc.get("nozzle_count"),
            "duesen_d_mm":          oc.get("nozzle_d_mm"),
            "druck_bar":            oc.get("pressure_bar"),
            "voller_ring":          oc.get("ring_full"),
            "einbaulage":           oc.get("orientation"),
            "video":                bool(oil.get("video")),
            "hinweis":              oil.get("note", ""),
        }

    # Quantitative OpenFOAM-VOF-Kühlung (interFoam) — echter HTC (Stufe-1-Korrelation),
    # falls ein 🌊-Lauf im Projekt liegt.
    cfd = results.get("cfd") or {}
    if cfd:
        hd = cfd.get("htc_detail") or {}
        cc = cfd.get("config") or {}
        ctx["cfd"] = {
            "htc_eff_Wm2K":         cfd.get("htc_eff"),
            "benetzung_mittel_pct": cfd.get("wetted_pct_mean"),
            "benetzung_spitze_pct": cfd.get("wetted_pct_peak"),
            "benetzte_flaeche_cm2": round((cfd.get("wetted_area_m2") or 0.0) * 1e4, 1),
            "strahl_v_mps":         cc.get("jet_v_mps"),
            "druck_bar":            cc.get("pressure_bar"),
            "Re_jet":               hd.get("Re_jet"),
            "Pr":                   hd.get("Pr"),
            "Nu":                   hd.get("Nu"),
            "L_char_mm":            hd.get("L_char_mm"),
            "netz_zellen":          cc.get("n_cells"),
            "verfeinerung":         cc.get("refine"),
            "hinweis":              cfd.get("scope_note", ""),
        }

    # Projektakte: Evolutionsverlauf + verknüpfte Vergleichsprojekte + Notizen aus
    # dem Manifest (load_or_synthesize → auch für Altprojekte verfügbar). Die Akte ist
    # die EINE Quelle; meta/results bleiben der Fallback, den der Synthesizer selbst nutzt.
    try:
        import ema_projekt
        man = ema_projekt.load_or_synthesize(project_dir, write_back=False)
        ctx["evolution"] = man.get("evolution", [])
        ctx["links"]     = man.get("links", [])
        ctx["notes"]     = man.get("notes", "")
        ctx["status"]    = man.get("status", "")
    except Exception:
        ctx.setdefault("evolution", []); ctx.setdefault("links", [])
    return ctx


# ── Prompt + LLM call ───────────────────────────────────────────────────────

def _prompt_for(ctx: dict) -> str:
    """Build a German technical-report prompt with [BILD:key] placeholders."""
    # Strip heavy keys for prompt
    payload = {k: v for k, v in ctx.items() if not k.startswith("_") and k != "images"}
    payload_json = json.dumps(payload, ensure_ascii=False, indent=2)
    available = ", ".join(ctx.get("images", []))

    has_vollast   = bool(ctx.get("vollast_zyklus"))
    has_anhaenger = bool(ctx.get("anhaenger_alpenpass"))
    extra_cycles  = []
    if has_vollast:   extra_cycles.append("Autobahn 220 km/h (hohes RPM, Feldschwächung)")
    if has_anhaenger: extra_cycles.append("Anhänger-Alpenpass (hohes Dauerdrehmoment, thermisch kritisch)")
    if extra_cycles:
        fahrzyklus_section = (
            "6. **Fahrzyklus-Bewertung** — WLTP-Verbrauch, Wirkungsgrad, Rekuperationsanteil; "
            "Vergleich mit: " + ", ".join(extra_cycles) + "; erkläre die jeweils dominante Belastungsart"
        )
    else:
        fahrzyklus_section = (
            "6. **Fahrzyklus-Bewertung** — Verbrauch in kWh/100 km, Wirkungsgrad, Rekuperationsanteil"
        )
    vollast_img   = "[BILD:drivecycle_vollast]"   if "drivecycle_vollast"   in available else ""
    anhaenger_img = "[BILD:drivecycle_anhaenger]" if "drivecycle_anhaenger" in available else ""

    has_3d = bool(ctx.get("em3d"))
    if has_3d:
        drei_d_section = (
            "8. **3D-Magnetfeldvalidierung (Elmer FEM)** — Vergleich der echten 3D-Feldlösung "
            "mit dem 2D-FDM-Schnittmodell: Bedeutung der finiten Paketlänge und der Endeffekte "
            "(axiale Feldabnahme zu den Stirnseiten), Plausibilität von B_gap 3D vs. 2D, und – "
            "falls vorhanden – die Wirkung der Schrägung bzw. der gestaffelten Staffelung "
            "(Step-Skew) auf Rastmoment/Oberwellen. Qualitativ, ohne Zahlen.")
        drei_d_img = ("- Abschnitt 8 3D-Validierung:        [BILD:em3d_field3d]  und  "
                      "[BILD:em3d_endeffect]  und  [BILD:em3d_airgap_2d3d]  und  [BILD:em3d_model_iso]\n")
    else:
        drei_d_section = ""
        drei_d_img = ""

    return f"""Du bist ein erfahrener E-Maschinen-Auslegungsingenieur und schreibst einen technischen Auslegungsbericht auf Deutsch.

Hier sind die Analyse-Ergebnisse als JSON:

```json
{payload_json}
```

WICHTIG — KEINE ZAHLEN IM FLIESSTEXT: Alle Zahlenwerte stehen ausschließlich in der
Kennwerttabelle, die automatisch eingefügt wird. Im Fließtext beschreibst du die
Ergebnisse NUR QUALITATIV (z. B. „hohe Luftspaltflussdichte", „ausreichende
Sicherheit", „thermisch unkritisch", „die Reluktanz dominiert das Drehmoment"),
ohne konkrete Zahlen, Einheiten oder Rechnungen. Begründung: falsch zugeordnete
Werte im Text machen den Bericht unbrauchbar — die Tabelle ist die einzige Quelle
der Zahlen.

Füge die Zeile `[TABELLE:kennwerte]` GENAU EINMAL direkt nach der Zusammenfassung
(Abschnitt 1) ein — dort wird die vollständige Parameter- und Kennwerttabelle
eingesetzt.

Schreibe einen strukturierten, sachlichen Bericht in Markdown mit genau diesen Abschnitten:

1. **Zusammenfassung** — 3–5 Sätze zur Gesamtbewertung (qualitativ, ohne Zahlen)
2. **Geometrie und Konstruktion** — Abmessungen, Polzahl/Nutzahl, gewählte Magnet-Topologie (`geometry.magTopologie`) und ihre Eignung, Masse
3. **Elektromagnetische Auslegung** — B_gap, Kt, Drehmoment, Rastmoment (LCM); falls `em_erweitert` vorhanden: Ld/Lq und Salienz ξ, Magnet- vs. Reluktanzmoment-Anteil (besonders bei PMa-SynRM/Spoke), MTPA-Stromwinkel, Kurzschlussstrom Isc; falls `segmentierung` vorhanden: Wirkung der Magnetsegmentierung auf die Wirbelstromverluste (Verlustfaktor, Skintiefe, ggf. Wirkungslos-Warnung)
4. **Festigkeit** — σ_v,max, Sicherheitsfaktor, Verschiebung, max. sichere Drehzahl
5. **Thermisches Verhalten** — Kühlung, Endtemperaturen, Gesamtverluste, ggf. Warnungen; falls `em_erweitert.demag` vorhanden: Demagnetisierungs-Reserve bei Magnettemperatur (Risiko ja/nein)
{fahrzyklus_section}
7. **Empfehlungen** — 3–5 konkrete Verbesserungsvorschläge basierend auf den Zahlen (inkl. Topologie-/Segmentierungs-Eignung)
{drei_d_section}

BEBILDERUNG: Füge Platzhalter `[BILD:KEY]` an sinnvollen Stellen im Fließtext ein.
Verfügbare Bild-KEYs: {available}

Zuordnung (strikt einhalten — kein Bild in Abschnitt 1 Zusammenfassung):
- Abschnitt 2 Geometrie:              [BILD:cross_section] oder [BILD:side_view]
- Abschnitt 3 Elektromagnetik:        [BILD:em_field]  und  [BILD:em_field_load]  und  [BILD:airgap]  und  [BILD:em_curve]
- Abschnitt 4 Festigkeit:             [BILD:structural]  und ggf. [BILD:deformation]
- Abschnitt 5 Thermik:                [BILD:thermal]
- Abschnitt 6 Fahrzyklus:             [BILD:drivecycle]{(f"  und  {vollast_img}") if vollast_img else ""}{(f"  und  {anhaenger_img}") if anhaenger_img else ""}
{drei_d_img}

FORMATIERUNGSREGELN (unbedingt einhalten):
- Schreibe echten Fließtext in Absätzen. Kein Zeilenumbruch mitten im Satz.
- Pro Abschnitt 1–3 Absätze, danach ggf. eine Aufzählung. Keine abgebrochenen Listen.
- KEINE Tabellen (kein Markdown mit `|`) selbst schreiben — die Tabelle kommt über
  `[TABELLE:kennwerte]`.
- KEINE Zahlenwerte und KEINE Einheiten im Fließtext (keine MPa/Nm/°C/U/min/kg/T/%
  mit Zahl). Beschreibe Größen relativ und qualitativ. Verweise bei Bedarf mit
  „siehe Kennwerttabelle".
- Keine Codeblöcke, keine Einleitungsfloskeln, keine einzelnen Stichworte als eigene Zeile.
- FORMELN nur SYMBOLISCH als LaTeX-Mathematik (wird im PDF gesetzt), OHNE eingesetzte
  Zahlen:
  - Im Satz eingebettet mit einfachen Dollarzeichen, z.B. $\\xi = L_q/L_d$,
    $T \\propto \\psi_{{PM}}\\,i_q$.
  - Abgesetzte Formeln auf EINER Zeile mit doppelten Dollarzeichen, z.B.
    $$T = \\tfrac{{3}}{{2}}\\,p\\,(\\psi_{{PM}}\\,i_q + (L_d - L_q)\\,i_d\\,i_q)$$
  - Echte LaTeX-Syntax verwenden: `\\frac`, `\\cdot`, `\\sqrt`, Indizes `_{{...}}`,
    Hochzahlen `^{{...}}`, griechische Buchstaben `\\sigma`, `\\omega`, `\\psi`.
    KEINE Unicode-Sonderzeichen in Formeln (kein σ, ², · — stattdessen \\sigma, ^2, \\cdot).

Beginne direkt mit `# Auslegungsbericht: {ctx.get('label', '')}` ohne weitere Vorrede."""


def call_ollama(prompt: str, model: str = DEFAULT_MODEL,
                 base_url: str = OLLAMA_URL, timeout: int = 600) -> str:
    """Single non-streaming call to Ollama's /api/generate."""
    # /no_think suppresses Qwen3 reasoning chain; ignored by other models.
    body = json.dumps({
        "model":   model,
        "prompt":  prompt,
        "stream":  False,
        "options": {
            "temperature": 0.4,
            "num_predict": 8192,
            "num_ctx":     14336,
        },
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{base_url}/api/generate", data=body,
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        resp = json.loads(r.read())
    raw = resp.get("response", "").strip() or resp.get("thinking", "").strip()
    return re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL).strip()


# ── Markdown post-processing + PDF render ───────────────────────────────────

# Match [BILD:key] optionally surrounded by backticks / whitespace /
# newlines that the LLM sometimes adds around code-like tokens.
_BILD_RE = re.compile(r"`?\s*\[BILD\s*:\s*([a-z_]+)\s*\]\s*`?", re.IGNORECASE)
_THINK_RE = re.compile(r"<think>.*?</think>", re.DOTALL)


def _normalize_paragraphs(md: str) -> str:
    """Join lines that the LLM broke mid-paragraph back into proper paragraphs.

    Runs repeatedly until stable so that multi-line broken paragraphs collapse
    fully. Preserves headings, list items, image refs, and blank lines.
    """
    import re as _re

    def _is_structural(line: str) -> bool:
        return (
            line.strip() == ""
            or line.lstrip().startswith("#")
            or bool(_re.match(r"^\s*[-*+]|\s*\d+\.", line))
            or line.strip().startswith("![")
            or line.lstrip().startswith("|")          # markdown table rows
            or "$$" in line                            # display-math line (keep alone)
            or "[BILD:" in line
            or "[TABELLE:" in line
        )

    def _one_pass(text: str) -> tuple[str, bool]:
        lines = text.split("\n")
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

    for _ in range(20):  # safety limit
        md, changed = _one_pass(md)
        if not changed:
            break
    return md


def _ensure_em_images(md: str, img_map: dict) -> str:
    """Guarantee the FDM field maps land IN the electromagnetic section. The local
    model often forgets the `[BILD:em_field]` placeholders, which would otherwise
    dump these (the report's visual highlight) into the appendix. Inject them right
    after the EM-section heading when present and not already referenced."""
    inject = [k for k in ("em_field", "em_field_load")
              if k in img_map and not re.search(rf"\[BILD\s*:\s*{k}\s*\]", md, re.I)]
    if not inject:
        return md
    block = "\n" + "\n".join(f"[BILD:{k}]" for k in inject)
    lines = md.split("\n")
    for i, ln in enumerate(lines):
        if ln.lstrip().startswith("#") and "elektromagnet" in ln.lower():
            lines.insert(i + 1, block)
            return "\n".join(lines)
    return md + "\n" + block        # fallback: appendix (old behaviour)


_EM3D_KEYS = ("em3d_field3d", "em3d_endeffect", "em3d_airgap_2d3d",
              "em3d_slice_mid", "em3d_model_iso", "em3d_model_axial")


def _ensure_em3d_section(md: str, ctx: dict) -> str:
    """Garantiert einen eigenen, bebilderten 3D-Abschnitt. Erkennt ein vom LLM bereits
    geschriebenes 3D-Kapitel (Überschrift mit „3D" / „Elmer") bzw. gesetzte em3d-Bild-
    Platzhalter; fehlt beides, wird ein deterministischer Abschnitt mit allen verfügbaren
    3D-Bildern angehängt (qualitativer Einleitungstext, Zahlen stehen in der Kennwerttabelle)."""
    if not ctx.get("em3d"):
        return md
    img_map = ctx.get("_img_map", {})
    avail = [k for k in _EM3D_KEYS if k in img_map]
    if not avail:
        return md
    has_heading = bool(re.search(r"(?im)^#{1,3}\s.*(3d|elmer)", md))
    has_ph = any(re.search(rf"\[BILD\s*:\s*{k}\s*\]", md, re.I) for k in _EM3D_KEYS)
    if has_heading or has_ph:
        return md
    e3 = ctx["em3d"]
    staffel = ((e3.get("skew_segments") or 1) >= 2 and (e3.get("skew_step_deg") or 0))
    skew = (e3.get("skew_deg") or 0) > 0
    extra = ""
    if staffel:
        extra = (" Die gestaffelte Staffelung (Step-Skew) des Blechpakets ist im 3D-Modell "
                 "berücksichtigt und glättet das Rastmoment und die Oberwellen der "
                 "Luftspaltinduktion.")
    elif skew:
        extra = (" Die kontinuierliche Schrägung ist im 3D-Modell berücksichtigt und "
                 "mindert Rastmoment und Oberwellen.")
    intro = (
        "Das 2D-FDM-Schnittmodell nimmt eine unendlich lange Maschine an. Die echte "
        "3D-Magnetostatik (Elmer FEM) erfasst dagegen die finite Paketlänge und die "
        "Endeffekte: zu den Stirnseiten hin nimmt die Luftspaltinduktion ab, weil sich "
        "der Fluss dort dreidimensional über die Stirnflächen schließt. Der Vergleich "
        "der mittigen Luftspaltinduktion zwischen 2D und 3D ordnet die Genauigkeit des "
        "schnellen 2D-Modells ein; die Abweichung bleibt qualitativ plausibel."
        + extra + " Die quantitativen Werte stehen in der Kennwerttabelle.")
    block = ["\n\n## 3D-Magnetfeldvalidierung (Elmer FEM)\n", intro]
    block += [f"[BILD:{k}]" for k in avail]
    return md.rstrip() + "\n" + "\n".join(block) + "\n"


_KUEHL_KEYS = ("oil_coverage", "oil_wetting", "oil_droplets", "cfd_wetting")


def _ensure_kuehlung_section(md: str, ctx: dict) -> str:
    """Garantiert einen eigenen, bebilderten Abschnitt zur Spritzöl-Wickelkopfkühlung, wenn ein
    qualitativer 💧-Lauf (Mantaflow) UND/ODER eine quantitative 🌊-Rechnung (OpenFOAM VOF)
    vorliegt (spiegelt ``_ensure_em3d_section``). Erkennt ein bereits geschriebenes Kühl-Kapitel
    bzw. gesetzte Bild-Platzhalter; fehlt beides, wird ein deterministischer, scope-ehrlicher
    Abschnitt angehängt."""
    has_oil = bool(ctx.get("oilspray"))
    has_cfd = bool(ctx.get("cfd"))
    if not (has_oil or has_cfd):
        return md
    img_map = ctx.get("_img_map", {})
    avail = [k for k in _KUEHL_KEYS if k in img_map]
    has_heading = bool(re.search(r"(?im)^#{1,3}\s.*(spritzöl|spritzoel|wickelkopfkühl|ölkühl)", md))
    has_ph = any(re.search(rf"\[BILD\s*:\s*{k}\s*\]", md, re.I) for k in _KUEHL_KEYS)
    if has_heading or has_ph:
        return md
    paras = []
    if has_cfd:
        paras.append(
            "Die Spritzöl-Kühlung am Wickelkopf wurde **quantitativ** mit einer OpenFOAM-"
            "VOF-Zweiphasensimulation (interFoam) gerechnet: Öl- und Luftphase, Strahl, "
            "Benetzung und Abtropfen werden strömungsmechanisch aufgelöst. Daraus wird ein "
            "**effektiver Wärmeübergangskoeffizient** abgeleitet, der bei gewählter Ölkühlung "
            "direkt das Thermikmodell speist (Wicklung → Kühlmittel). **Scope-Ehrlichkeit:** "
            "interFoam ist isotherm — die Strömung/Benetzung ist gerechnet, der HTC ist ein "
            "korrelationsbasierter Kennwert (Prallstrahl-Nusselt), kein aufgelöstes "
            "Temperaturfeld; ein voll konjugierter HTC (CHT) wäre die Folgestufe.")
    if has_oil:
        paras.append(
            "Ergänzend/zum Vergleich wurde derselbe Wickelkopf-Ausschnitt mit einem schnellen "
            "FLIP-Fluidlöser (Blender/Mantaflow) **qualitativ** betrachtet — Strahlbildung, "
            "Tröpfchen und Abtropfen. Diese Studie liefert bewusst nur geometrische "
            "Benetzungs-Proxys (kein Temperaturfeld/HTC). Die quantitativen Werte beider "
            "Pfade stehen in der Kennwerttabelle.")
    block = ["\n\n## Spritzöl-Wickelkopfkühlung\n"] + ["\n".join(paras)]
    block += [f"[BILD:{k}]" for k in avail]
    return md.rstrip() + "\n" + "\n".join(block) + "\n"


def insert_images(md: str, img_map: dict) -> str:
    """Replace [BILD:key] with ![title](path) for each known key.
    Also strips backticks the LLM tends to add around the placeholder, and
    appends any images the LLM forgot to reference."""
    md = _THINK_RE.sub("", md).strip()
    md = _normalize_paragraphs(md)
    used: set[str] = set()
    def _repl(m: re.Match) -> str:
        key = m.group(1).lower().strip()
        if key in img_map:
            used.add(key)
            entry = img_map[key]
            return f"\n\n![{entry['title']}]({entry['path']})\n\n"
        return ""
    md = _BILD_RE.sub(_repl, md)

    # Append unused images at the end so nothing is lost
    leftover = [k for k in img_map if k not in used]
    if leftover:
        md += "\n\n## Weitere Diagramme\n\n"
        for k in leftover:
            e = img_map[k]
            md += f"![{e['title']}]({e['path']})\n\n"
    return md


_LATEX_HEADER = r"""\usepackage[document]{ragged2e}
% Left-align (ragged-right) the whole document: with narrow margins + long
% non-breakable tokens (units, i_q=-155 A, formulas) full justification stretches
% the spaces and produces the "one or two words per line" look. Ragged-right plus a
% generous emergencystretch keeps lines naturally filled and left-aligned.
\setlength{\RaggedRightParindent}{0pt}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.55em}
\setlength{\emergencystretch}{3em}
\usepackage{float}
\let\origfigure\figure
\let\endorigfigure\endfigure
% Keep images near where they are referenced rather than floating to page ends.
\renewenvironment{figure}[1][]{\origfigure[H]}{\endorigfigure}
"""


def render_pdf(md: str, project_dir: str, out_filename: str = "bericht.pdf",
               md_filename: str = "bericht.md", page_numbers: bool = True) -> str:
    """Write the markdown + PDF into project_dir. Returns PDF path."""
    md_path  = os.path.join(project_dir, md_filename)
    pdf_path = os.path.join(project_dir, out_filename)
    hdr_path = os.path.join(project_dir, "_report_header.tex")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    with open(hdr_path, "w", encoding="utf-8") as f:
        f.write(_LATEX_HEADER)

    # Pandoc with xelatex for utf-8 + image embedding. Margins narrower than
    # default to fit the wide chart PNGs.
    # `markdown-yaml_metadata_block` disables YAML front-matter parsing — the
    # LLM tends to use `---` as horizontal rules between sections, which
    # pandoc would otherwise interpret as YAML delimiters and choke on.
    # `-V lang=de` enables German hyphenation via babel/polyglossia which
    # prevents the "two words per line" problem from over-wide justified text.
    cmd = [
        "pandoc", md_path,
        "--from", "markdown-yaml_metadata_block",
        "--pdf-engine=xelatex",
        "-V", "geometry:margin=20mm",
        "-V", "mainfont=DejaVu Serif",
        "-V", "monofont=DejaVu Sans Mono",
        "-V", "colorlinks=true",
        "-V", "lang=de",
        "-V", "linestretch=1.08",
        "--include-in-header", hdr_path,
        "--resource-path", project_dir,
        "-o", pdf_path,
    ]
    if not page_numbers:                 # per-chapter render → no restarting "1,1,1"
        cmd[1:1] = ["-V", "pagestyle=empty"]
    res = subprocess.run(cmd, cwd=project_dir, capture_output=True,
                          text=True, timeout=180)
    if res.returncode != 0 or not os.path.exists(pdf_path):
        cmd_fallback = [
            "pandoc", md_path,
            "--from", "markdown-yaml_metadata_block",
            "-V", "geometry:margin=20mm",
            "-V", "lang=de",
            "--resource-path", project_dir,
            "-o", pdf_path,
        ]
        res2 = subprocess.run(cmd_fallback, cwd=project_dir,
                               capture_output=True, text=True, timeout=180)
        if res2.returncode != 0:
            raise RuntimeError(f"pandoc failed:\n"
                                f"first attempt: {res.stderr[-400:]}\n"
                                f"fallback:      {res2.stderr[-400:]}")
    return pdf_path


# ── Top-level ────────────────────────────────────────────────────────────────

def _write_rag_markdown(project_dir: str, prose_vf: str, ctx: dict, _log=None) -> str | None:
    """Write the value-free RAG markdown (bericht_rag.md) next to the report.
    Best-effort — a failure here never breaks the PDF report."""
    try:
        rag_md = to_rag_markdown(prose_vf, ctx)
        path = os.path.join(project_dir, "bericht_rag.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(rag_md)
        if _log:
            _log("✓ RAG-Markdown (wertfrei) erzeugt: bericht_rag.md", None)
        return path
    except Exception as e:                                  # pragma: no cover
        if _log:
            _log(f"⚠ RAG-Markdown fehlgeschlagen: {e}", None)
        return None


def generate_report(project_dir: str, model: str = DEFAULT_MODEL,
                     progress_cb=None) -> dict:
    """Build context → call LLM → post-process → render PDF.
    Returns {"pdf": path, "md": path, "model": …, "n_chars": …}."""
    def _log(msg, pct=None):
        if progress_cb: progress_cb(msg, pct)

    _log("Lade Analyse-Daten…", 5)
    ctx = build_context(project_dir)
    if not ctx.get("images"):
        _log("⚠ Keine Bilder gefunden — Bericht wird textlastig", 10)

    _log(f"Frage {model}…", 15)
    prompt = _prompt_for(ctx)
    md_raw = call_ollama(prompt, model=model)
    _log(f"LLM-Antwort: {len(md_raw)} Zeichen", 70)

    _log("Bilder einfügen…", 75)
    md_raw   = _strip_md_tables(md_raw)   # local models emit malformed centered tables
    md_raw   = _strip_value_numbers(md_raw)   # Zahlen nur in der Tabelle, nicht im Fließtext
    _prose_vf = md_raw                     # value-free prose snapshot (for the RAG markdown)
    md_raw   = _ensure_em_images(md_raw, ctx["_img_map"])  # EM field maps into §3
    md_raw   = _ensure_em3d_section(md_raw, ctx)           # eigener 3D-Abschnitt + Bilder
    md_raw   = _ensure_kuehlung_section(md_raw, ctx)       # Spritzöl-Kühlung + Bilder
    md_final = insert_images(md_raw, ctx["_img_map"])
    md_final = insert_tables(md_final, {"kennwerte": _single_md_tables(ctx)})
    _evo = _evolution_links_md(ctx)
    if _evo:
        md_final = md_final.rstrip() + "\n\n" + _evo + "\n"

    _log("Rendere PDF (pandoc + xelatex)…", 85)
    pdf_path = render_pdf(md_final, project_dir)
    rag_md_path = _write_rag_markdown(project_dir, _prose_vf, ctx, _log)
    _log(f"✓ Bericht: {os.path.basename(pdf_path)}", 100)

    return {
        "pdf":     pdf_path,
        "md":      os.path.join(project_dir, "bericht.md"),
        "rag_md":  rag_md_path,
        "model":   model,
        "n_chars": len(md_final),
    }


def generate_report_agentic(
    project_dir: str,
    model: str = DEFAULT_MODEL,
    expert_model: str | None = None,
    progress_cb=None,
) -> dict:
    """Agentic variant: run 6 expert agents first, then produce the main report.

    The expert analyses are appended as a dedicated section after the
    standard 7-section report. Returns same dict as generate_report plus
    "expert_outputs" key.
    """
    from ema_experts import run_expert_agents, assemble_expert_section

    def _log(msg, pct=None):
        if progress_cb: progress_cb(msg, pct)

    _log("Lade Analyse-Daten…", 2)
    ctx = build_context(project_dir)

    # Load full results for expert agents
    results, meta = {}, {}
    rp = os.path.join(project_dir, "results.json")
    mp = os.path.join(project_dir, "meta.json")
    if os.path.exists(rp):
        with open(rp) as f: results = json.load(f)
    if os.path.exists(mp):
        with open(mp) as f: meta = json.load(f)

    # Expert agents (use expert_model or fall back to same model)
    _log("Starte Experten-Agenten…", 5)
    emodel = expert_model or model
    expert_out = run_expert_agents(
        results, meta, model=emodel,
        progress_cb=lambda msg, pct: _log(f"  {msg}", None),
    )

    # Main report body
    _log(f"Hauptbericht ({model})…", 55)
    prompt   = _prompt_for(ctx)
    md_main  = call_ollama(prompt, model=model)
    _log(f"Hauptbericht: {len(md_main)} Zeichen", 72)

    _log("Bilder einfügen…", 74)
    md_main = _strip_md_tables(md_main)   # drop malformed centered LLM tables
    md_main = _strip_value_numbers(md_main)   # Zahlen nur in der Tabelle, nicht im Fließtext
    _prose_vf = md_main                    # value-free prose snapshot (for the RAG markdown)
    md_main = _ensure_em_images(md_main, ctx["_img_map"])  # EM field maps into §3
    md_main = _ensure_em3d_section(md_main, ctx)           # eigener 3D-Abschnitt + Bilder
    md_main = _ensure_kuehlung_section(md_main, ctx)       # Spritzöl-Kühlung + Bilder
    md_main = insert_images(md_main, ctx["_img_map"])
    md_main = insert_tables(md_main, {"kennwerte": _single_md_tables(ctx)})

    # Append expert section (with images + paragraph normalisation)
    expert_md = assemble_expert_section(expert_out, img_map=ctx["_img_map"])
    md_final  = md_main.rstrip() + "\n\n---\n\n" + expert_md
    _evo = _evolution_links_md(ctx)
    if _evo:
        md_final = md_final.rstrip() + "\n\n" + _evo + "\n"

    _log("Rendere PDF (pandoc + xelatex)…", 85)
    pdf_path = render_pdf(md_final, project_dir, out_filename="bericht_agentisch.pdf")
    rag_md_path = _write_rag_markdown(project_dir, _prose_vf, ctx, _log)
    _log(f"✓ Agentischer Bericht: {os.path.basename(pdf_path)}", 100)

    return {
        "pdf":            pdf_path,
        "md":             os.path.join(project_dir, "bericht.md"),
        "rag_md":         rag_md_path,
        "model":          model,
        "expert_model":   emodel,
        "n_chars":        len(md_final),
        "expert_outputs": expert_out,
    }


# ── Comparison report (multiple variants) ────────────────────────────────────

_TAB_RE = re.compile(r"`?\s*\[TABELLE\s*:\s*([a-z_]+)\s*\]\s*`?", re.IGNORECASE)


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _mdesc(s):
    return str(s).replace("|", "\\|")


def _fmt_val(x, nd=None, unit=""):
    """Human-readable cell value; numbers get `nd` decimals + thin-space thousands."""
    if x is None or x == "":
        return "—"
    if isinstance(x, bool):
        s = "ja" if x else "nein"
    elif isinstance(x, (int, float)):
        s = f"{x:,.{nd}f}".replace(",", " ") if nd is not None else f"{x:g}"
    else:
        s = str(x)
    return f"{s} {unit}".strip() if unit else s


def _vals_differ(raw):
    seen = [x for x in raw if x not in (None, "", "—")]
    return len({str(x) for x in seen}) > 1


# Output metrics shown in the comparison: (label, results-summary key, unit, decimals, better)
_METRIC_SPECS = [
    ("B_gap (Peak)",            "B_gap_T",            "T",          3, None),
    ("Drehmomentkonstante Kt",  "Kt_Nm_per_A",        "Nm/A",       3, "up"),
    ("Maxwell-Moment",          "T_maxwell_Nm",       "Nm",         1, "up"),
    ("Max. sichere Drehzahl",   "max_safe_rpm",       "U/min",      0, "up"),
    ("Rotor-Masse",             "mass_g",             "g",          0, "down"),
    ("T_Wicklung",              "T_winding_C",        "°C",         1, "down"),
    ("T_Magnet",                "T_magnet_C",         "°C",         1, "down"),
    ("Verluste P_ges",          "P_total_W",          "W",          0, "down"),
    ("Verbrauch",               "verbrauch_kWh100km", "kWh/100km",  2, "down"),
    ("Kurzschlussstrom Isc",    "Isc_A",              "A",          0, None),
    ("Demag-Risiko",            "demag_risiko",       "",        None, None),
]


def _input_param_rows(variants):
    """Per-variant geometry + operating INPUT parameters (from meta), one row each,
    flagged when the value differs across variants."""
    G  = lambda v: (v["meta"].get("geom") or {})
    M  = lambda v: v["meta"]
    MT = lambda v: (v["meta"].get("materials") or {})

    def topo(v):
        gg = G(v)
        return TOPOLOGY_LABELS.get(gg.get("magShape", "v"), gg.get("magShape", "?"))

    specs = [
        ("Topologie",                 "",   topo,                                       None),
        ("Polpaare p",                "",   lambda v: G(v).get("p"),                    None),
        ("Nuten",                     "",   lambda v: G(v).get("slots"),                None),
        ("Stator-Außen-Ø",            "mm", lambda v: G(v).get("statorOD"),             1),
        ("Stator-Innen-Ø",            "mm", lambda v: G(v).get("statorID"),             1),
        ("Rotor-Ø",                   "mm", lambda v: G(v).get("rotorOD"),              1),
        ("Luftspalt",                 "mm", lambda v: G(v).get("airGap"),               2),
        ("Wellen-Ø",                  "mm", lambda v: G(v).get("shaftD"),               1),
        ("Wellen-Bohrung",            "mm", lambda v: G(v).get("shaftBoreD", 0),        1),
        ("Blechpaketlänge",           "mm", lambda v: M(v).get("axial_len") or G(v).get("axialLen"), 1),
        ("Nuttiefe",                  "mm", lambda v: G(v).get("slotDepth"),            1),
        ("Magnet-Länge",              "mm", lambda v: G(v).get("magWidth"),             1),
        ("Magnet-Dicke",              "mm", lambda v: G(v).get("magThick"),             1),
        ("Öffnungswinkel",            "°",  lambda v: G(v).get("magAngle"),             0),
        ("Magnet-Position (Radius)",  "%",  lambda v: (lambda x: x * 100 if x is not None else None)(G(v).get("magDepthRel")), 0),
        ("Steg-Abstand",              "mm", lambda v: G(v).get("magDist"),              1),
        ("Segmentierung n_ax×n_circ", "",   lambda v: f"{G(v).get('nAx',1)}×{G(v).get('nCirc',1)}", None),
        ("Rotorblech",                "",   lambda v: MT(v).get("rotor"),               None),
        ("Statorblech",               "",   lambda v: MT(v).get("stator"),              None),
        ("Hairpin-Leiter",            "",   lambda v: MT(v).get("hairpin"),             None),
        ("Magnet-Typ",                "",   lambda v: MT(v).get("magnet"),              None),
        ("Lastmoment (Auslegung)",    "Nm", lambda v: M(v).get("load_nm"),              1),
        ("Kühlung",                   "",   lambda v: M(v).get("cooling"),              None),
        ("Umgebungstemperatur",       "°C", lambda v: M(v).get("T_ambient"),            0),
        ("Drehzahlbereich",           "",   lambda v: M(v).get("rpm_range"),            None),
    ]
    rows = []
    for label, unit, fn, nd in specs:
        raw = []
        for v in variants:
            try:
                raw.append(fn(v))
            except Exception:
                raw.append(None)
        rows.append({"label": label,
                     "values": [_fmt_val(x, nd, unit) for x in raw],
                     "differ": _vals_differ(raw)})
    return rows


def _md_param_table(variants, param_rows):
    names = [v["meta"].get("label", v["id"])[:22] for v in variants]
    lines = ["| Parameter | " + " | ".join(_mdesc(n) for n in names) + " | Δ |",
             "|" + "---|" * (len(names) + 2)]
    for r in param_rows:
        mark  = "●" if r["differ"] else ""
        label = f"**{r['label']}**" if r["differ"] else r["label"]
        cells = " | ".join(_mdesc(x) for x in r["values"])
        lines.append(f"| {label} | {cells} | {mark} |")
    return "\n".join(lines)


def _md_metric_table(rows):
    names = [r["name"][:22] for r in rows]
    lines = ["| Kennwert | " + " | ".join(_mdesc(n) for n in names) + " | Einheit |",
             "|" + "---|" * (len(names) + 2)]
    for label, key, unit, nd, _better in _METRIC_SPECS:
        cells = [_fmt_val(r.get(key), nd) for r in rows]
        if all(c == "—" for c in cells):
            continue
        lines.append(f"| {label} | " + " | ".join(_mdesc(c) for c in cells) + f" | {unit} |")
    return "\n".join(lines)


def _md_influence(variants, param_rows, rows):
    """Baseline = variant 0. Show (a) which inputs each variant changed vs the
    baseline and (b) the resulting % change of each headline metric."""
    if len(rows) < 2:
        return "_Einfluss-Analyse benötigt mindestens zwei Varianten._"
    base = rows[0]["name"][:22]
    out = [f"_Basis-Variante: **{_mdesc(base)}**. Δ% bezieht sich auf diese Basis._\n"]

    diff_rows = [r for r in param_rows if r["differ"]]
    if diff_rows:
        out.append("**Geänderte Eingabe-Parameter gegenüber der Basis:**\n")
        lines = ["| Variante | " + " | ".join(_mdesc(r["label"]) for r in diff_rows) + " |",
                 "|" + "---|" * (len(diff_rows) + 1)]
        for i, v in enumerate(variants[1:], start=1):
            cells = []
            for r in diff_rows:
                cur = r["values"][i] if i < len(r["values"]) else "—"
                base_v = r["values"][0] if r["values"] else "—"
                cells.append(cur if cur != base_v else "=")
            lines.append(f"| {_mdesc(rows[i]['name'][:22])} | " + " | ".join(_mdesc(c) for c in cells) + " |")
        out.append("\n".join(lines))

    out.append("\n**Resultierende Kennwert-Änderungen (Δ% gegenüber Basis):**\n")
    metrics = [m for m in _METRIC_SPECS if m[4] in ("up", "down")]
    hdr_names = [rows[i]["name"][:18] for i in range(1, len(rows))]
    lines = ["| Kennwert | " + " | ".join(_mdesc(n) for n in hdr_names) + " | besser |",
             "|" + "---|" * (len(hdr_names) + 2)]
    for label, key, unit, nd, better in metrics:
        b0 = _num(rows[0].get(key))
        cells = []
        for i in range(1, len(rows)):
            xi = _num(rows[i].get(key))
            if b0 in (None, 0) or xi is None:
                cells.append("—")
            else:
                cells.append(f"{(xi - b0) / abs(b0) * 100:+.0f}%")
        if all(c == "—" for c in cells):
            continue
        lines.append(f"| {label} | " + " | ".join(cells) + f" | {'↑' if better=='up' else '↓'} |")
    out.append("\n".join(lines))
    return "\n".join(out)


def _strip_md_tables(md: str) -> str:
    """Remove any pipe-table blocks (and stray bold-only lines) the LLM wrote
    itself. Comparison tables come ONLY from the deterministic injector — local
    models tend to ignore the "no tables" instruction and emit malformed ones
    that break pandoc. The [TABELLE:…] placeholders are not pipe rows, so they
    survive and get filled by insert_tables()."""
    out = []
    for line in md.split("\n"):
        s = line.strip()
        if s.startswith("|"):                      # pipe-table row or separator
            continue
        # table delimiter row even WITHOUT a leading pipe (e.g. "---|---|---")
        if re.match(r"^:?-{2,}:?(\s*\|\s*:?-{2,}:?)+$", s):
            continue
        # thematic-break / horizontal-rule lines (--- *** ___): the local model
        # scatters them between paragraphs; in context pandoc misreads them as a
        # 1-column table → a 5.6%-wide column → "one syllable per line". Drop them.
        if re.match(r"^([-*_])\1{2,}$", s):
            continue
        if s and set(s) <= {"*"}:                  # stray "**" / "***" lines
            continue
        if re.search(r"\(\s*[Ww]ird durch .*?ersetzt\s*\)", s):  # placeholder echoes
            continue
        out.append(line)
    return "\n".join(out)


def _escape_pipes(text: str) -> str:
    """Escape unescaped `|` in prose so pandoc never turns a sentence with a pipe
    separator (e.g. 'Vorteile … | Nachteile …') into a narrow table — the cause of
    the 'two words per line' columns on the expert pages. Deterministic tables are
    assembled separately and never pass through here."""
    return re.sub(r"(?<!\\)\|", r"\\|", text)


# Numeric quantities (number + physical unit) are stripped from the running text so
# the prose can NEVER mis-assign a value — all numbers live in the tables only. The
# unit is kept and the number replaced by "…", which reads as "see table".
# Multi-character / unambiguous units may follow the number without a space.
_U_SAFE  = (r"°C|kWh/100\s?km|kWh|Nm/A|Nm|U/min|km/h|MPa|GPa|kW|µH|mH|Wb|Hz|"
            r"mm|cm|µm|km|kg|m²|%")
# Single-character / ambiguous units (T, A, V, W, °) REQUIRE a leading space so a
# material code like "M270-35A" or a magnet grade "N52" is never mangled.
_U_AMBIG = r"°|T|A|V|W"
_NUM     = r"[-+]?\d[\d.,]*(?:\s?(?:–|-|bis|\.\.\.|…)\s?\d[\d.,]*)?"
# Lookbehind also rejects a preceding hyphen/word char (inside an identifier/code).
_VAL_NUM_RE = re.compile(
    r"(?<![\w.,$\\-])" + _NUM +
    r"(?:\s?(" + _U_SAFE + r")|\s(" + _U_AMBIG + r"))(?![A-Za-zµ])"
)


def _strip_value_numbers(md: str) -> str:
    """Remove numeric VALUES (number + unit) from the running prose, keeping the
    unit and inserting `…`. The report's numbers belong in the tables; the local
    model routinely mis-assigns them in the flow text, which makes the report
    nonsensical. Headings, table rows, image/placeholder lines and fenced math are
    left untouched."""
    out, in_fence = [], False
    for line in md.split("\n"):
        s = line.lstrip()
        if s.startswith("```") or s.startswith("$$"):
            in_fence = not in_fence if s.startswith("```") else in_fence
            out.append(line)
            continue
        if in_fence:
            out.append(line)
            continue
        # skip structural lines: headings, table rows, image / placeholder lines
        if (not s) or s.startswith(("#", "|", "!", "[", ">")) or "[BILD:" in s \
                or "[TABELLE:" in s or s.startswith("---"):
            out.append(line)
            continue
        out.append(_VAL_NUM_RE.sub(
            lambda m: "… " + (m.group(1) or m.group(2)), line))
    return "\n".join(out)


_IMG_MD_RE = re.compile(r"!\[[^\]]*\]\([^)]*\)")
# A line that, after stripping, holds only punctuation / list bullets / ellipses —
# i.e. carries no information once the values were removed.
_EMPTY_INFO_RE = re.compile(r"^[\s.,;:–\-•*…()/]*$")
# The "… <unit>" remnants that _strip_value_numbers leaves behind — for the RAG text
# we drop the unit too so no value reference survives at all.
_RAG_VAL_RE = re.compile(r"…\s*(?:" + _U_SAFE + r"|" + _U_AMBIG + r")?")


def to_rag_markdown(prose_md: str, ctx: dict | None = None) -> str:
    """Distil a finished report's prose into a VALUE-FREE, table-/figure-free
    Markdown for a RAG knowledge base.

    Keeps the qualitative, transferable statements (structure, operating
    principles, design trade-offs) plus the heading outline; removes every concrete
    numeric value, all tables, all figures and the [BILD:]/[TABELLE:] placeholders.
    Material grades and topology names are categories (not numbers) and are kept on
    purpose — they make the text retrievable and generalisable. No LLM call: this is
    a pure transform of the already value-stripped report prose."""
    md = _strip_md_tables(prose_md)          # pipe tables + horizontal rules
    md = _IMG_MD_RE.sub("", md)              # raw ![alt](path) image refs
    # Replace the placeholders with a newline (NOT ""): the regexes eat the
    # surrounding blank lines, so "" would glue a heading onto the previous text.
    md = _BILD_RE.sub("\n", md)              # [BILD:key] placeholders
    md = _TAB_RE.sub("\n", md)              # [TABELLE:key] placeholders
    md = _strip_value_numbers(md)            # number+unit → "… <unit>" (safety net)
    md = _RAG_VAL_RE.sub("", md)             # drop the "… <unit>" remnants entirely

    _PREP = r"(?:von|bei|auf|um|mit|ca\.?|etwa|rund|circa)"
    cleaned = []
    for line in md.split("\n"):
        s = line.rstrip()
        is_head = s.lstrip().startswith("#")
        if s and not is_head and _EMPTY_INFO_RE.match(s):
            continue                         # drop "- …" / ": …" value-only remnants
        # collapse any leftover bare "…" mid-sentence, then tidy whitespace/punctuation
        s = re.sub(r"\s*…\s*", " ", s)
        # a removed value leaves a dangling preposition ("Drehmoment von bei …"):
        # drop a preposition immediately followed by another preposition…
        s = re.sub(r"\b" + _PREP + r"\s+(?=" + _PREP + r"\b)", "", s)
        # …or one left hanging right before punctuation / end of sentence.
        s = re.sub(r"\b" + _PREP + r"\s*([.,;:]|$)", r"\1", s)
        s = re.sub(r"\s{2,}", " ", s)
        s = re.sub(r"\s+([.,;:!?])", r"\1", s)
        # a bullet reduced to a bare label ("- Kennwert:") carries no info anymore
        if not is_head and re.match(r"^[\s>*+-]*\S.*:\s*$", s) and "—" not in s:
            continue
        # keep blank lines around a heading so Markdown renders it as a heading
        if is_head and cleaned and cleaned[-1] != "":
            cleaned.append("")
        cleaned.append(s.rstrip())
        if is_head:
            cleaned.append("")
    body = re.sub(r"\n{3,}", "\n\n", "\n".join(cleaned)).strip()

    title, descr = "Auslegungsbericht (allgemein)", []
    if ctx:
        g = ctx.get("geometry") or {}; th = ctx.get("thermal") or {}; mt = ctx.get("materials") or {}
        if g.get("magTopologie"): descr.append(str(g["magTopologie"]))
        if th.get("cooling"):     descr.append(f"Kühlung: {th['cooling']}")
        if mt.get("magnet"):      descr.append(f"Magnet: {mt['magnet']}")
        if descr:
            title = "Auslegungsbericht – " + ", ".join(descr)
    intro = ("> Wertfreie, allgemein gehaltene Fassung eines IPM-Motor-Auslegungsberichts "
             "für die Wissensbasis (RAG). Konkrete Zahlenwerte sind bewusst entfernt; der "
             "Text beschreibt qualitativ Aufbau, Wirkprinzipien und Auslegungs"
             "zusammenhänge dieser Maschinenkonfiguration.")
    return f"# {title}\n\n{intro}\n\n{body}\n"


def _single_md_tables(ctx: dict) -> str:
    """Comprehensive, deterministic parameter+result table for the single-project
    report. ALL numeric values of the report live here (the prose stays qualitative
    and value-free), grouped by domain."""
    g = ctx.get("geometry", {}) or {}
    mt = ctx.get("materials", {}) or {}
    em = ctx.get("em", {}) or {}
    st = ctx.get("structural", {}) or {}
    th = ctx.get("thermal", {}) or {}
    dc = ctx.get("drivecycle", {}) or {}
    adv = ctx.get("em_erweitert", {}) or {}
    seg = ctx.get("segmentierung", {}) or {}

    def _tbl(title, rows):
        rows = [(lbl, _fmt_val(val, nd, unit)) for lbl, val, unit, nd in rows
                if val not in (None, "", [])]
        if not rows:
            return ""
        out = [f"### {title}", "", "| Kennwert | Wert |", "|---|---|"]
        out += [f"| {_mdesc(l)} | {_mdesc(v)} |" for l, v in rows]
        return "\n".join(out) + "\n"

    blocks = []
    blocks.append(_tbl("Geometrie und Konstruktion", [
        ("Magnet-Topologie", g.get("magTopologie"), "", None),
        ("Polzahl",          g.get("poles"),        "", None),
        ("Nutzahl",          g.get("slots"),        "", None),
        ("Stator Außen-Ø",   g.get("statorOD"),     "mm", 1),
        ("Stator Innen-Ø",   g.get("statorID"),     "mm", 1),
        ("Rotor-Ø",          g.get("rotorOD"),      "mm", 1),
        ("Wellen-Ø",         g.get("shaftD"),       "mm", 1),
        ("Blechpaketlänge",  g.get("axial"),        "mm", 1),
        ("Aktivteil-Masse",  g.get("mass_kg"),      "kg", 2),
    ]))
    blocks.append(_tbl("Werkstoffe", [
        ("Rotorblech",  mt.get("rotor"),   "", None),
        ("Statorblech", mt.get("stator"),  "", None),
        ("Wicklung",    mt.get("hairpin"), "", None),
        ("Magnet",      mt.get("magnet"),  "", None),
    ]))
    em_rows = [
        ("Luftspaltflussdichte B_gap (Peak)", em.get("B_gap_T"),      "T",    3),
        ("Drehmomentkonstante Kt",            em.get("Kt_Nm_per_A"),  "Nm/A", 3),
        ("Maxwell-Moment",                    em.get("T_maxwell_Nm"), "Nm",   1),
        ("LCM (Nut/Pol)",                     em.get("lcm"),          "",     None),
    ]
    if adv:
        dm = adv.get("demag", {}) or {}
        em_rows += [
            ("Ld", adv.get("Ld_mH"), "mH", 3),
            ("Lq", adv.get("Lq_mH"), "mH", 3),
            ("Salienz ξ = Lq/Ld", adv.get("salienz_xi"), "", 2),
            ("Permanentmagnetfluss ψ_PM", adv.get("psi_pm_Wb"), "Wb", 4),
            ("Kurzschlussstrom Isc", adv.get("Isc_A"), "A", 0),
            ("Demag-Reserve @ T_Magnet", dm.get("reserve_T"), "T", 3),
            ("Demag-Risiko", ("ja" if dm.get("risiko") else "nein")
                if dm.get("risiko") is not None else None, "", None),
        ]
    blocks.append(_tbl("Elektromagnetische Auslegung", em_rows))
    if seg:
        blocks.append(_tbl("Magnet-Segmentierung", [
            ("Segmente axial",        seg.get("n_axial"),        "", None),
            ("Segmente Umfang",       seg.get("n_umfang"),       "", None),
            ("Verlustfaktor",         seg.get("verlustfaktor"),  "", 3),
            ("Wirbelstromverlust unsegm.", seg.get("P_Mag_unsegm_W"), "W", 1),
            ("Wirbelstromverlust segm.",   seg.get("P_Mag_segm_W"),   "W", 1),
            ("Skintiefe",             seg.get("skintiefe_mm"),   "mm", 2),
        ]))
    blocks.append(_tbl("Festigkeit (Fliehkraft-FEM)", [
        ("Vergleichsspannung σ_v,max", st.get("sigma_v_max_MPa"), "MPa", 1),
        ("Sicherheitsfaktor",          st.get("safety_factor"),   "",    2),
        ("Max. Verschiebung",          st.get("u_max_um"),        "µm",  1),
        ("FEM-Drehzahl",               st.get("rpm_fem"),         "U/min", 0),
        ("Max. sichere Drehzahl",      st.get("max_safe_rpm"),    "U/min", 0),
    ]))
    blocks.append(_tbl("Thermisches Verhalten", [
        ("Kühlung",        th.get("cooling"),    "", None),
        ("T_Wicklung",     th.get("T_winding"),  "°C", 1),
        ("T_Magnet",       th.get("T_magnet"),   "°C", 1),
        ("T_Gehäuse",      th.get("T_housing"),  "°C", 1),
        ("Gesamtverluste", th.get("P_total_W"),  "W", 0),
    ]))
    if dc:
        blocks.append(_tbl(f"Fahrzyklus ({dc.get('name') or '—'})", [
            ("Strecke",          dc.get("distance_km"),   "km", 1),
            ("Verbrauch",        dc.get("kWh_per_100km"), "kWh/100km", 2),
            ("Antriebswirkungsgrad", dc.get("eta_drive"), "", 3),
            ("Rekuperationsanteil",  dc.get("regen_share"), "", 3),
            ("v_max",            dc.get("v_max_kmh"),     "km/h", 0),
        ]))
    e3 = ctx.get("em3d", {}) or {}
    if e3:
        staffel = None
        if (e3.get("skew_segments") or 1) >= 2 and (e3.get("skew_step_deg") or 0):
            staffel = f"{e3.get('skew_segments')} Segmente à {e3.get('skew_step_deg')}°"
        zonen = None
        if e3.get("zone_luftspalt"):
            zonen = (f"{e3.get('zone_luftspalt'):.2f} / {e3.get('zone_magnet'):.2f} / "
                     f"{e3.get('zone_grob'):.1f} mm (Spalt/Magnet/grob)")
        blocks.append(_tbl("3D-Magnetfeldberechnung (Elmer FEM)", [
            ("B_gap 3D (Paketmitte)",      e3.get("B_gap_3D_mid_T"), "T", 3),
            ("B_gap 2D-FDM (Vergleich)",   e3.get("B_gap_2D_FDM_T"), "T", 3),
            ("Endeffekt B(Stirn)/B(Mitte)", e3.get("endeffekt_rand_zu_mitte"), "", 3),
            ("Schrägung (kontinuierlich)", e3.get("skew_deg"),     "°", 1),
            ("Gestaffelte Staffelung",     staffel,                "", None),
            ("Flussbarrieren (3D-Modell)", e3.get("n_barrieren"),  "", None),
            ("Netz-Zonen (fein→grob)",     zonen,                  "", None),
            ("Netzknoten (3D)",            e3.get("mesh_knoten"),  "", None),
        ]))
    cfd = ctx.get("cfd", {}) or {}
    if cfd:
        blocks.append(_tbl("Spritzöl-Kühlung — quantitativ (OpenFOAM VOF / interFoam)", [
            ("Effektiver HTC",             cfd.get("htc_eff_Wm2K"),         "W/m²·K", 0),
            ("Benetzte Fläche (Mittel)",   cfd.get("benetzung_mittel_pct"), "%", 1),
            ("Benetzte Fläche (Spitze)",   cfd.get("benetzung_spitze_pct"), "%", 1),
            ("Benetzte Fläche",            cfd.get("benetzte_flaeche_cm2"), "cm²", 1),
            ("Strahlgeschwindigkeit",      cfd.get("strahl_v_mps"),         "m/s", 1),
            ("Öldruck",                    cfd.get("druck_bar"),            "bar", 1),
            ("Re / Pr / Nu (Korrelation)",
             (f"{cfd.get('Re_jet')} / {cfd.get('Pr')} / {cfd.get('Nu')}"
              if cfd.get("Re_jet") is not None else None), "", None),
            ("Charakteristische Länge",    cfd.get("L_char_mm"),            "mm", 2),
            ("Netz-Grundauflösung",        cfd.get("netz_zellen"),          "Zellen", None),
        ]))
    oil = ctx.get("oilspray", {}) or {}
    if oil:
        blocks.append(_tbl("Spritzöl-Kühlung — qualitativ (Blender/Mantaflow, Benetzungs-Proxys)", [
            ("Benetzte Fläche (Mittel)",   oil.get("benetzung_mittel_pct"), "%", 1),
            ("Benetzte Fläche (Spitze)",   oil.get("benetzung_spitze_pct"), "%", 1),
            ("Tropfen/Fragmente (Spitze)", oil.get("tropfen_spitze"),       "", None),
            ("Düsen",                      oil.get("duesen"),               "", None),
            ("Düsen-Ø",                    oil.get("duesen_d_mm"),          "mm", 2),
            ("Öldruck",                    oil.get("druck_bar"),            "bar", 1),
            ("Domain-Auflösung",           oil.get("aufloesung"),           "px", None),
            ("Strahl-Zellen (Auflösung)",  oil.get("strahl_zellen"),        "", 1),
        ]))
    return "\n".join(b for b in blocks if b).strip()


def insert_tables(md: str, table_map: dict) -> str:
    """Replace [TABELLE:key] with the deterministic markdown table; append any the
    LLM forgot to place (so no table is ever lost). Run AFTER insert_images so the
    table markdown never passes through paragraph normalisation."""
    used: set[str] = set()

    def _repl(m: re.Match) -> str:
        key = m.group(1).lower().strip()
        if key in table_map:
            used.add(key)
            return f"\n\n{table_map[key]}\n\n"
        return ""
    md = _TAB_RE.sub(_repl, md)

    titles = {"parameter": "Parameter-Vergleich (Eingaben)",
              "kennwerte": "Ergebnis-Kennwerte",
              "einfluss":  "Einfluss der Parameteränderungen"}
    for k, tbl in table_map.items():
        if k not in used and tbl:
            md += f"\n\n## {titles.get(k, k)}\n\n{tbl}\n"
    return md


_EVO_ACTION_LABELS = {
    "analyse": "Vollanalyse", "design_ai": "KI-Entwurf",
    "rating": "Bewertung", "report": "Bericht", "clone": "Geklont",
}


def _evolution_links_md(ctx: dict) -> str:
    """Deterministic 'Evolutionsverlauf' + 'Verknüpfte Projekte' section from the
    Projektakte (appended AFTER the LLM prose, so it never passes through table
    stripping). Returns '' if there is nothing to show."""
    evo = ctx.get("evolution") or []
    links = ctx.get("links") or []
    if not evo and not links:
        return ""
    parts = ["## Projektverlauf & Verknüpfungen\n"]
    if evo:
        parts.append("### Evolutionsverlauf\n")
        parts.append("| # | Zeitpunkt | Aktion | Geänderte Eingaben |")
        parts.append("|---|-----------|--------|--------------------|")
        for i, e in enumerate(evo, 1):
            act = e.get("action", "")
            label = _EVO_ACTION_LABELS.get(act.split(":")[0], act) or act
            if act.startswith("recompute:"):
                label = "Nachgerechnet (" + act.split(":", 1)[1] + ")"
            ch = e.get("changed_inputs") or {}
            chs = ", ".join(sorted(ch.keys())) if ch else "—"
            if len(chs) > 80:
                chs = chs[:77] + "…"
            note = e.get("note") or ""
            cell = chs + (f" · _{note}_" if note else "")
            parts.append(f"| {i} | {e.get('ts','')} | {label} | {cell} |")
        parts.append("")
    if links:
        parts.append("### Verknüpfte Vergleichsprojekte\n")
        for l in links:
            note = f" — {l.get('note')}" if l.get("note") else ""
            parts.append(f"- **{l.get('label', l.get('id'))}** "
                        f"({l.get('relation', 'vergleich')}){note}")
        parts.append("")
    return "\n".join(parts).strip()


def _comparison_context(project_ids, projects_root):
    """Per-variant key metrics + topology label for the comparison prompt."""
    import ema_compare
    variants = ema_compare.load_projects(projects_root, project_ids)
    rows = []
    for v in variants:
        s = v["results"].get("summary", {}) or {}
        g = v["meta"].get("geom", {}) or {}
        adv = v["results"].get("em_advanced", {}) or {}
        seg = v["results"].get("segmentation", {}) or {}
        rows.append({
            "name":          v["meta"].get("label", v["id"]),
            "topologie":     TOPOLOGY_LABELS.get(g.get("magShape", "v"), g.get("magShape")),
            "B_gap_T":       s.get("B_gap_T"),
            "Kt_Nm_per_A":   s.get("Kt_Nm_per_A"),
            "T_maxwell_Nm":  s.get("T_maxwell_Nm"),
            "max_safe_rpm":  s.get("max_safe_rpm"),
            # FEM-Festigkeit (maßgeblich; analytischer Sweep ist zu optimistisch)
            "safety_factor_fem": s.get("safety_factor_fem"),
            "structural_ok": s.get("structural_ok"),
            "fem_rpm":       s.get("fem_rpm"),
            "mass_g":        s.get("mass_g"),
            "mass_kg":       (round(s.get("mass_g") / 1000.0, 2)
                              if s.get("mass_g") is not None else None),
            "T_winding_C":   s.get("T_winding_C"),
            "T_magnet_C":    s.get("T_magnet_C"),
            # WICHTIG: das ist VERLUSTLEISTUNG (Abwärme), NICHT Nutz-/Wellenleistung!
            # (klarer Label-Key für das LLM; P_total_W bleibt für _md_metric_table erhalten)
            "verlustleistung_abwaerme_W": s.get("P_total_W"),
            "P_total_W":     s.get("P_total_W"),
            "verbrauch_kWh100km": s.get("cycle_kWh100km"),
            "Isc_A":         adv.get("Isc_A"),
            "demag_risiko":  (adv.get("demag") or {}).get("risk"),
            "segmentierung": (f"n_ax={seg.get('n_ax')},n_circ={seg.get('n_circ')}"
                              if seg else None),
        })
    return variants, rows


# ── Deterministische Bewertung & Warnungen (NICHT vom LLM erzeugt) ───────────

def _variant_verdict(row: dict) -> dict:
    """Harte, regelbasierte Beurteilung einer Variante aus den Kennwerten.
    Diese Logik ist deterministisch und überschreibt jede LLM-Aussage — eine
    Variante, die strukturell oder thermisch versagt, darf NIE empfohlen werden."""
    warn, ok = [], True
    sf = row.get("safety_factor_fem")
    if sf is not None:
        if sf < 1.0:
            warn.append(f"MECHANISCHES VERSAGEN: FEM-Sicherheitsfaktor {sf:.2f} < 1 "
                        f"bei {_fmt_val(row.get('fem_rpm'),0)} U/min (Rotor fließt/berstet)")
            ok = False
        elif sf < 1.5:
            warn.append(f"Festigkeit unzureichend: FEM-Sicherheitsfaktor {sf:.2f} < 1,5")
            ok = False
    tm = row.get("T_magnet_C")
    if tm is not None and tm > 150:
        warn.append(f"Magnettemperatur {tm:.0f} °C > 150 °C (Entmagnetisierungsgefahr)")
        ok = False
    tw = row.get("T_winding_C")
    if tw is not None and tw > 180:
        warn.append(f"Wicklungstemperatur {tw:.0f} °C > 180 °C (Isolationsklasse H)")
        ok = False
    return {"empfohlen": ok, "warnungen": warn}


def _md_verdict_table(rows):
    """Deterministische Ampel-Tabelle: Eignung + Warnungen je Variante."""
    head = ["Variante", "FEM-SF", "sichere Drehzahl [U/min]", "T_Magnet [°C]",
            "Bewertung"]
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    for i, r in enumerate(rows):
        v = _variant_verdict(r)
        status = "✅ einsetzbar" if v["empfohlen"] else "❌ NICHT einsetzbar"
        out.append("| " + " | ".join(_mdesc(x) for x in [
            f"V{i+1} {r['name'][:18]}",
            _fmt_val(r.get("safety_factor_fem"), 2),
            _fmt_val(r.get("max_safe_rpm"), 0),
            _fmt_val(r.get("T_magnet_C"), 0),
            status,
        ]) + " |")
    return "\n".join(out)


def _md_warnings_block(rows):
    """Aufzählung der konkreten Warnungen je Variante (deterministisch)."""
    lines = []
    for i, r in enumerate(rows):
        v = _variant_verdict(r)
        if v["warnungen"]:
            lines.append(f"**V{i+1} – {_mdesc(r['name'])}:**\n")
            for w in v["warnungen"]:
                lines.append(f"- {_mdesc(w)}")
            lines.append("")
    if not lines:
        return "_Keine kritischen Grenzwertverletzungen festgestellt._"
    return "\n".join(lines)


def _comparison_prompt(rows, diff_labels):
    payload = json.dumps({"varianten": rows}, ensure_ascii=False, indent=2)
    diffs = ", ".join(diff_labels) if diff_labels else "(keine — Varianten sind identisch parametriert)"
    return f"""Du bist ein erfahrener E-Maschinen-Auslegungsingenieur und schreibst einen
**Vergleichsbericht** über {len(rows)} Motor-Varianten auf Deutsch.

Kennwerte je Variante als JSON (Variante 0 ist die Basis):

```json
{payload}
```

Zwischen den Varianten unterscheiden sich diese Eingabe-Parameter: {diffs}.

WICHTIG: Tabellen werden automatisch eingefügt — schreibe selbst KEINE Tabellen.
Setze stattdessen exakt diese Platzhalter (jeweils in einer eigenen Zeile) an den
passenden Stellen; sie werden durch fertige Tabellen/Diagramme ersetzt:
[TABELLE:parameter]  [TABELLE:kennwerte]  [TABELLE:einfluss]  [BILD:kennlinien]  [BILD:thermal]

Gliederung (genau diese Abschnitte, als Markdown-Überschriften):

1. **Überblick** — welche Varianten/Topologien verglichen werden und das Ziel
2. **Eingabe-Parameter** — kurze Einleitung, dann [TABELLE:parameter]; benenne in
   Worten, WO die Varianten sich unterscheiden (die mit ● markierten Zeilen)
3. **Ergebnis-Kennwerte** — [TABELLE:kennwerte], dann [BILD:kennlinien]; beschreibe
   die elektromagnetischen Unterschiede (B_gap, Kt, Maxwell-Moment, Isc)
4. **Einfluss der Änderungen** — [TABELLE:einfluss]; das ist der Kern: erkläre
   KAUSAL, welche Parameter-Änderung welche Kennwert-Änderung bewirkt
   (z.B. „größerer Öffnungswinkel → +x % Kt, aber höheres T_Magnet"). Stütze jede
   Aussage auf die Δ%-Zahlen der Tabelle.
5. **Festigkeit & Thermik** — max. sichere Drehzahl, Masse, Temperaturen,
   Verluste; [BILD:thermal]; weise auf Demagnetisierungs-Risiken hin
6. **Ranking & Empfehlung** — ordne die Varianten nach Eignung, nenne klar die
   beste und begründe mit Zahlen
7. **Fazit** — 2–3 Sätze

Beziehe dich durchgehend auf konkrete Zahlen. Erfinde keine Werte."""


def generate_comparison_report(project_ids, projects_root, out_dir,
                               model: str = DEFAULT_MODEL, progress_cb=None) -> dict:
    """Multi-variant comparison report: ema_compare charts + LLM narrative → PDF."""
    import base64 as _b64
    import ema_compare

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    os.makedirs(os.path.join(out_dir, "charts"), exist_ok=True)
    _log("Lade Varianten + erzeuge Vergleichs-Diagramme…", 10)
    variants, rows = _comparison_context(project_ids, projects_root)
    if len(variants) < 2:
        raise ValueError("Mindestens 2 gültige Projekte für einen Vergleich nötig")

    cmp = ema_compare.run_compare(projects_root, project_ids)
    img_map = {}
    for key, b64key, title in [("kennlinien", "kennlinien_b64", "Kennlinien-Vergleich"),
                               ("thermal", "thermal_b64", "Thermik & Energie")]:
        if cmp.get(b64key):
            rel = f"charts/cmp_{key}.png"
            with open(os.path.join(out_dir, rel), "wb") as f:
                f.write(_b64.b64decode(cmp[b64key]))
            img_map[key] = {"path": rel, "title": title}

    # Deterministic tables (formatting under our control, not the LLM's)
    param_rows  = _input_param_rows(variants)
    diff_labels = [r["label"] for r in param_rows if r["differ"]]
    table_map = {
        "parameter": _md_param_table(variants, param_rows),
        "kennwerte": _md_metric_table(rows),
        "einfluss":  _md_influence(variants, param_rows, rows),
    }

    _log(f"Frage {model} (Vergleichsanalyse)…", 35)
    md_raw = call_ollama(_comparison_prompt(rows, diff_labels), model=model)
    _log(f"LLM-Antwort: {len(md_raw)} Zeichen", 75)

    md_raw = _strip_md_tables(md_raw)          # tables come only from our injector
    md_final = insert_images(md_raw, img_map)
    md_final = insert_tables(md_final, table_map)
    _log("Rendere PDF…", 85)
    pdf_path = render_pdf(md_final, out_dir, out_filename="vergleichsbericht.pdf")
    _log(f"✓ Vergleichsbericht: {os.path.basename(pdf_path)}", 100)
    return {"pdf": pdf_path, "md": os.path.join(out_dir, "bericht.md"),
            "model": model, "n_variants": len(variants), "n_chars": len(md_final)}


# ── Comprehensive agentic comparison report — deterministic skeleton ─────────
# The local model is unreliable at structure (centered two-word lines, malformed
# tables, forgotten images). So the agentic comparison report is built
# DETERMINISTICALLY: methodology (with LaTeX formulas), all tables, all images and
# per-variant galleries are assembled by us; the LLM only writes cleaned prose
# blocks and the comparative expert findings.

# Per-variant source images copied into the report's charts/ dir.
_VARIANT_IMG_SRC = [
    ("cross_section", "cad_images/motor_cross_section.png", "Querschnitt"),
    ("em_field",      "charts/em_field.png",                "EM-Feld (Leerlauf)"),
    ("em_field_load", "charts/em_field_load.png",           "EM-Feld (Last)"),
    ("airgap",        "charts/airgap.png",                  "Luftspaltflussdichte"),
    ("em_curve",      "charts/em_curve.png",                "EM-Kennlinie"),
    ("deformation",   "charts/deformation.png",             "Verformung (FEM)"),
    ("connection",    "charts/connection.png",              "Welle-Nabe-Verbindung"),
    ("thermal",       "charts/thermal.png",                 "Thermik (LPTN)"),
]


def _variant_names(variants):
    return [v["meta"].get("label", v["id"]) or v["id"] for v in variants]


def _copy_variant_images(variants, projects_root, out_dir):
    """Copy each variant's existing PNGs into out_dir/charts as vN_<key>.png.
    Returns [{idx, name, images:{key: relpath}}] (only images that exist)."""
    import shutil
    os.makedirs(os.path.join(out_dir, "charts"), exist_ok=True)
    per = []
    for i, v in enumerate(variants, start=1):
        pdir = os.path.join(projects_root, v["id"])
        imgs = {}
        for key, rel, _title in _VARIANT_IMG_SRC:
            src = os.path.join(pdir, rel)
            if os.path.exists(src):
                dst_rel = f"charts/v{i}_{key}.png"
                try:
                    shutil.copyfile(src, os.path.join(out_dir, dst_rel))
                    imgs[key] = dst_rel
                except Exception:
                    pass
        per.append({"idx": i, "name": _variant_names(variants)[i-1], "images": imgs})
    return per


# Erklärung je Bildtyp ("auskommentieren") — was zeigt das Bild, worauf achten.
_GALLERY_DESC = {
    "em_field":      "Farbskala = Flussdichte |B|. Rote Zonen im Eisen zeigen Sättigung, "
                     "der Luftspaltring die nutzbare Felddichte; die Feldlinien (Höhenlinien "
                     "des Vektorpotentials A) verdeutlichen den Flussverlauf je Pol.",
    "em_field_load": "Magnetfeld unter Last (Statorstrom aktiv). Im Vergleich zum Leerlauf "
                     "zeigt sich die Ankerrückwirkung: das Statorfeld verzerrt das Magnetfeld "
                     "und verschiebt die Flussverteilung.",
    "airgap":        "Radiale (B_r) und tangentiale (B_t) Luftspaltflussdichte über dem "
                     "Polumfang. Die Grundwellen-Amplitude bestimmt das Drehmoment, der "
                     "Oberwellengehalt das Rastmoment und die Eisenverluste.",
    "em_curve":      "Induzierte Spannung (EMK) und Drehmomentkonstante Kt über der Drehzahl. "
                     "Der Knick markiert die Eckdrehzahl, ab der Feldschwächung einsetzt.",
    "deformation":   "Fliehkraftbedingte radiale Aufweitung des Rotors (überhöht dargestellt) "
                     "bei Maximaldrehzahl. Die Verformung skaliert quadratisch mit der Drehzahl.",
    "connection":    "Kennfeld der Welle-Nabe-Verbindung: Fugendruck und übertragbares Moment "
                     "bzw. Lösedrehzahl, bei der die Fliehkraft den Pressverband löst.",
    "thermal":       "Stationäre Knotentemperaturen (Wicklung, Eisen, Magnet, Gehäuse) und der "
                     "transiente Temperaturanstieg aus dem Lumped-Parameter-Netzwerk.",
}


def _gallery_md(per_variant, key, title):
    """Markdown-Bildgalerie: erklärender Text + je Variante eine eigene captioned Figure."""
    figs = [f"![{title} – Variante V{p['idx']} ({_mdesc(p['name'])})]({p['images'][key]})"
            for p in per_variant if key in p.get("images", {})]
    if not figs:
        return ""
    desc = _GALLERY_DESC.get(key)
    head = (f"*{desc}*\n\n" if desc else "")
    # leere Zeile zwischen den Bildern → jedes wird zu einer eigenen Abbildung mit Untertitel
    return "\n" + head + "\n\n".join(figs) + "\n"


def _md_simple_table(header, rows):
    """rows = [(label, [cell1, cell2, …]), …]; header = ['Kennwert', 'V1', …]."""
    out = ["| " + " | ".join(_mdesc(h) for h in header) + " |",
           "|" + "---|" * len(header)]
    for label, cells in rows:
        out.append(f"| {_mdesc(label)} | " + " | ".join(_mdesc(c) for c in cells) + " |")
    return "\n".join(out)


def _md_magnet_thermal_table(rows):
    names = [r["name"][:18] for r in rows]
    body = []
    specs = [("T_Magnet [°C]", "T_magnet_C", 1), ("T_Wicklung [°C]", "T_winding_C", 1),
             ("Verluste P_ges [W]", "P_total_W", 0)]
    for label, key, nd in specs:
        body.append((label, [_fmt_val(r.get(key), nd) for r in rows]))
    return _md_simple_table(["Kennwert"] + [f"V{i+1}" for i in range(len(rows))], body)


def _md_energy_table(rows):
    body = [
        ("Verbrauch WLTP [kWh/100km]", [_fmt_val(r.get("verbrauch_kWh100km"), 2) for r in rows]),
    ]
    return _md_simple_table(["Kennwert"] + [f"V{i+1}" for i in range(len(rows))], body)


def _md_connection_table(variants):
    names = [f"V{i+1}" for i in range(len(variants))]
    specs = [
        ("Typ",                      lambda c: c.get("note") or c.get("type")),
        ("Übertragb. Moment [Nm]",   lambda c: _fmt_val(c.get("T_capacity_Nm"), 0)),
        ("Auslegungsmoment [Nm]",    lambda c: _fmt_val(c.get("T_rated_Nm"), 0)),
        ("Ausnutzung",               lambda c: _fmt_val(c.get("utilization"), 2)),
        ("Fugendruck [MPa]",         lambda c: _fmt_val(c.get("p_MPa"), 1)),
        ("Lösedrehzahl [U/min]",     lambda c: _fmt_val(c.get("loosening_rpm"), 0)),
    ]
    body = []
    for label, fn in specs:
        cells = []
        for v in variants:
            c = (v["results"].get("connection") or {})
            try: cells.append(fn(c))
            except Exception: cells.append("—")
        body.append((label, cells))
    return _md_simple_table(["Kennwert"] + names, body)


def _methodology_md():
    """Static methodology section with LaTeX formulas (renders via xelatex)."""
    return r"""## 1. Berechnungsmethodik

Alle **Kennzahlen, Tabellen und Diagramme** dieses Berichts stammen aus einer rein
numerisch-physikalischen Rechenkette (FDM-Feld, CalculiX-FEM, LPTN-Thermik) — die
**Zahlen werden NICHT von einem Sprachmodell erzeugt**. Ein lokales Sprachmodell formuliert
lediglich die **erläuternden Fließtexte** und die vergleichende Experten-Einschätzung
(Kapitel 10); maßgeblich für die Eignung ist stets die regelbasierte Bewertungstabelle, nicht
der generierte Text.

### 1.1 Elektromagnetik – 2D-Finite-Differenzen-Feldlöser

Das Magnetfeld wird in der Querschnittsebene über das magnetische Vektorpotential
$A_z(x,y)$ aus der nichtlinearen Poisson-Gleichung berechnet:

$$\nabla \cdot \left( \nu \, \nabla A_z \right) = -J_z$$

mit der Reluktivität $\nu = 1/\mu$ (Eisen $\mu_r \approx 500$, Magnet $\mu_r \approx 1{,}05$)
und der Stromdichte $J_z$ aus Magnet-Ersatzströmen und Statorstrom. Das Gleichungssystem
wird mit einer direkten Sparse-Faktorisierung exakt gelöst. Die Flussdichte folgt aus
$\vec{B} = \nabla \times \vec{A}$, d.h. $B_x = \partial A_z/\partial y$ und
$B_y = -\partial A_z/\partial x$. Die radiale Luftspaltflussdichte wird entlang des
Spaltkreises über die winkelstabile Ableitung

$$B_r(\theta) = \frac{1}{r}\,\frac{\partial A_z}{\partial \theta}$$

abgetastet. Das Drehmoment setzt sich aus Permanentmagnet- und Reluktanzanteil zusammen:

$$T = \frac{3}{2}\,p\,\Big(\psi_{PM}\,i_q + (L_d - L_q)\,i_d\,i_q\Big)$$

Unterhalb der Eckdrehzahl folgt der Betriebspunkt der MTPA-Strategie (maximales Moment
pro Ampere, $i_d < 0$ bei Schenkeligkeit $\xi = L_q/L_d > 1$), darüber kommt
Feldschwächung hinzu.

### 1.2 Strukturmechanik – FEM (CalculiX)

Der Rotor wird unter Fliehkraft als Volumenkörper vernetzt und linear-elastisch gelöst.
Die volumenbezogene Fliehkraft ist $f = \rho\,\omega^2\,r$. Beurteilt wird die
Vergleichsspannung nach von Mises

$$\sigma_v = \sqrt{\tfrac{1}{2}\big[(\sigma_1-\sigma_2)^2+(\sigma_2-\sigma_3)^2+(\sigma_3-\sigma_1)^2\big]}$$

gegen die Streckgrenze $R_e$ über den Sicherheitsfaktor $\mathrm{SF} = R_e/\sigma_v$.
Da die Last $\propto \omega^2$ und das Problem linear ist, skalieren Verschiebung und
Spannung exakt mit $(\omega/\omega_0)^2$; daraus folgt die Berstdrehzahl

$$n_{berst} = n_{solve}\,\sqrt{R_e/\sigma_{solve}}.$$

### 1.3 Thermik – Lumped-Parameter-Netzwerk (LPTN)

Ein thermisches Knotennetzwerk (Wicklung, Eisen, Magnet, Gehäuse, …) wird stationär und
transient gelöst. Im stationären Fall gilt pro Knoten die Wärmebilanz

$$\sum_j \frac{T_j - T_i}{R_{ij}} + P_i = 0,$$

mit den Verlustquellen $P_i$ (Kupfer-, Eisen-, Magnetverluste) und thermischen Widerständen
$R_{ij}$ je nach Kühlung. Bewertet werden Magnet- (Entmagnetisierung) und
Wicklungstemperatur (Isolationsklasse).

### 1.4 Welle–Blechpaket-Verbindung

Analytisch bewertet: Querpressverband über die Lamé-Gleichungen (Fugendruck $p$,
übertragbares Moment $T \approx \mu\,p\,\pi\,d^2 l / 2$, Lösedrehzahl, bei der die
fliehkraftbedingte Bohrungsaufweitung das Übermaß aufhebt); Keil-/Polygonprofile über
Flanken- bzw. Flächenpressung.

### 1.5 Fahrzyklus & Energiebilanz

Über den Fahrzyklus (z.B. WLTP) werden Mechanik- und Verlustleistung zeitlich integriert,
$E = \int (P_{mech} + P_{verl})\,dt$, woraus Verbrauch (kWh/100 km), Wirkungsgrad und die
Energieaufteilung (Cu/Fe/Magnet/Lager vs. Nutzenergie) folgen.
"""


def _clean_prose(text: str) -> str:
    """LLM-Prosa säubern: Think-Blöcke + Tabellen raus, Absätze normalisieren,
    Überschriften entfernen (Struktur kommt von uns)."""
    text = _THINK_RE.sub("", text or "").strip()
    text = _strip_md_tables(text)
    text = _strip_value_numbers(text)   # Zahlen gehören in die Tabellen, nicht in die Prosa
    text = _normalize_paragraphs(text)
    # eigene Überschriften des Modells entfernen (wir setzen die Struktur)
    text = "\n".join(l for l in text.split("\n") if not l.lstrip().startswith("#"))
    return _escape_pipes(text.strip())


# Harte Leitplanken — gegen die beobachteten gefährlichen LLM-Fehlinterpretationen
# (Verluste als Nutzleistung gedeutet, mechanisches Versagen ignoriert, falsche
# Rechen-/Größenvergleiche, versagende Variante empfohlen).
_PROSE_GUARDRAILS = (
    "VERBINDLICHE REGELN (Verstoß = grober Fehler):\n"
    "1. Verwende AUSSCHLIESSLICH die Zahlen aus den Daten. ERFINDE KEINE Werte und "
    "rechne nichts Neues aus (keine eigenen Massen-/Leistungs-/Wirkungsgradrechnungen).\n"
    "2. 'verlustleistung_abwaerme_W' ist VERLUSTLEISTUNG = ABWÄRME, NICHT Nutz- oder "
    "Wellenleistung. Ein hoher Wert ist SCHLECHT (mehr Verluste), nicht 'leistungsstark'.\n"
    "3. Festigkeit: maßgeblich ist 'safety_factor_fem'. SF < 1,0 = der Rotor VERSAGT "
    "(fließt/berstet); SF < 1,5 = unzulässig. Eine solche Variante darf NIEMALS für hohe "
    "Drehzahlen oder als beste empfohlen werden — auch nicht relativierend.\n"
    "4. 'max_safe_rpm' ist bereits die FEM-deratete sichere Drehzahl; widersprich ihr nicht.\n"
    "5. Größen-/Reihenfolge-Aussagen (schwerer/leichter, höher/niedriger) müssen mit den "
    "Zahlen übereinstimmen. Wenn die Varianten identische Werte haben, sage das klar.\n"
    "6. Triff KEINE Sicherheits-/Eignungs-Endurteile, die der Bewertungstabelle "
    "widersprechen.\n"
)


def _section_prose(model, role, task, context):
    """Ein fokussierter LLM-Aufruf für EINEN Fließtext-Abschnitt (gesäubert)."""
    payload = json.dumps(context, ensure_ascii=False, indent=2)
    prompt = (
        f"Du bist {role} und schreibst einen Abschnitt eines technischen "
        f"Vergleichsberichts über Motor-Varianten auf Deutsch.\n\n"
        f"Aufgabe: {task}\n\n"
        f"{_PROSE_GUARDRAILS}\n"
        f"Daten (JSON):\n```json\n{payload}\n```\n\n"
        f"FORMAT: Nur zusammenhängender Fließtext (2–4 Absätze), beziehe dich auf konkrete "
        f"Zahlen aus den Daten. KEINE Überschrift, KEINE Tabellen, KEINE Aufzählungslisten, "
        f"KEINE Code-Blöcke, keine Einleitungsfloskeln. Kein Zeilenumbruch nach einzelnen "
        f"Wörtern/Zahlen/Einheiten; Absätze durch genau eine Leerzeile trennen."
    )
    try:
        return _clean_prose(call_ollama(prompt, model=model))
    except Exception as e:
        return f"_Abschnitt nicht verfügbar: {e}_"


def generate_comparison_report_agentic(project_ids, projects_root, out_dir,
                                       model: str = DEFAULT_MODEL,
                                       expert_model: str | None = None,
                                       progress_cb=None) -> dict:
    """Umfangreicher, professioneller agentischer Vergleichsbericht.

    Deterministisches Gerüst (Methodik mit LaTeX-Formeln, alle Tabellen, alle Bilder
    inkl. pro-Variante-Galerien für EM-Feld/Luftspalt/Verformung/Verbindung) + LLM nur
    für gesäuberte Fließtext-Abschnitte und die 6 vergleichenden Experten."""
    import base64 as _b64
    import ema_compare
    from ema_experts import run_expert_agents_compare, assemble_expert_section_compare

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    os.makedirs(os.path.join(out_dir, "charts"), exist_ok=True)
    _log("Lade Varianten + erzeuge Vergleichs-Diagramme…", 5)
    variants, rows = _comparison_context(project_ids, projects_root)
    if len(variants) < 2:
        raise ValueError("Mindestens 2 gültige Projekte für einen Vergleich nötig")
    names = _variant_names(variants)

    # Overlay-Diagramme (Kennlinien + Thermik/Energie)
    cmp = ema_compare.run_compare(projects_root, project_ids)
    overlay = {}
    for key, b64key, title in [("kennlinien", "kennlinien_b64", "Kennlinien-Vergleich"),
                               ("thermal", "thermal_b64", "Thermik & Energie (Magnettemperaturen + Energieaufteilung)")]:
        if cmp.get(b64key):
            rel = f"charts/cmp_{key}.png"
            with open(os.path.join(out_dir, rel), "wb") as f:
                f.write(_b64.b64decode(cmp[b64key]))
            overlay[key] = {"path": rel, "title": title}

    # Pro-Variante-Bilder kopieren
    _log("Kopiere Varianten-Bilder (EM-Feld, Luftspalt, Verformung, Verbindung)…", 12)
    per_var = _copy_variant_images(variants, projects_root, out_dir)

    # Deterministische Tabellen
    param_rows  = _input_param_rows(variants)
    diff_labels = [r["label"] for r in param_rows if r["differ"]]
    tbl_param   = _md_param_table(variants, param_rows)
    tbl_metric  = _md_metric_table(rows)
    tbl_infl    = _md_influence(variants, param_rows, rows)
    tbl_magtherm = _md_magnet_thermal_table(rows)
    tbl_energy  = _md_energy_table(rows)
    tbl_conn    = _md_connection_table(variants)

    # 6 vergleichende Experten
    _log("Starte 6 Experten-Agenten (vergleichend)…", 22)
    emodel = expert_model or model
    expert_vars = [{"name": names[i], "results": v["results"], "meta": v["meta"]}
                   for i, v in enumerate(variants)]
    expert_out = run_expert_agents_compare(
        expert_vars, model=emodel,
        progress_cb=lambda msg, pct: _log(f"  {msg}", None),
    )
    expert_md = _clean_prose_keep_headings(assemble_expert_section_compare(expert_out))

    # LLM-Fließtext je Abschnitt (gesäubert)
    legend = "; ".join(f"V{i+1} = {n}" for i, n in enumerate(names))
    _log(f"Verfasse Fließtext-Abschnitte ({model})…", 60)
    p_over = _section_prose(model, "ein erfahrener E-Maschinen-Auslegungsingenieur",
        "Gib einen Überblick: welche Topologien/Varianten werden verglichen und mit welchem Ziel. 1 Absatz.",
        {"varianten": rows})
    p_design = _section_prose(model, "ein Konstrukteur für E-Maschinen",
        "Beschreibe die Unterschiede in Gestaltung und Auslegung der Varianten (Geometrie, "
        "Magnete, Wicklung, Material, Verbindung). Welche Parameter unterscheiden sich (●)?",
        {"unterschiede": diff_labels, "varianten": rows})
    p_em = _section_prose(model, "ein EM-Feld-Experte",
        "Vergleiche die Elektromagnetik der Varianten (Luftspaltflussdichte B_gap, Kt, "
        "Maxwell-Moment, Kurzschlussstrom). Erkläre die Feldbilder und Kennlinien.",
        {"varianten": rows})
    p_therm = _section_prose(model, "ein Thermik-Experte",
        "Vergleiche besonders die MAGNETTEMPERATUREN der Varianten (Entmagnetisierungsrisiko) "
        "sowie Wicklungstemperatur und Verluste.",
        {"varianten": rows})
    p_energy = _section_prose(model, "ein Antriebsstrang-Experte",
        "Vergleiche die Energiebilanz: Verbrauch (kWh/100km), Wirkungsgrad und Energieaufteilung.",
        {"varianten": rows})
    # Deterministische Bewertung (regelbasiert, NICHT vom LLM) — Quelle der Wahrheit
    verdicts    = [_variant_verdict(r) for r in rows]
    tbl_verdict = _md_verdict_table(rows)
    warn_block  = _md_warnings_block(rows)
    einsetzbar  = [f"V{i+1} ({names[i]})" for i, v in enumerate(verdicts) if v["empfohlen"]]
    nicht_ok    = [f"V{i+1} ({names[i]})" for i, v in enumerate(verdicts) if not v["empfohlen"]]
    det_reco = ("**Deterministische Eignung:** "
                + ("einsetzbar: " + ", ".join(einsetzbar) + ". " if einsetzbar
                   else "KEINE Variante erfüllt alle Festigkeits-/Thermikgrenzen. ")
                + ("NICHT einsetzbar: " + ", ".join(nicht_ok) + "." if nicht_ok else ""))

    p_rank = _section_prose(model, "ein leitender Auslegungsingenieur",
        "Ranking und klare Empfehlung. WICHTIG: Die regelbasierte Eignung steht im Kontext "
        "('verdict' je Variante) und ist VERBINDLICH — eine als NICHT einsetzbar markierte "
        "Variante (z.B. FEM-Sicherheitsfaktor < 1,5) darf NICHT empfohlen werden, auch nicht "
        "für hohe Drehzahlen. Begründe das Ranking mit den Zahlen; bei mechanischem Versagen "
        "ist die Festigkeit das K.-o.-Kriterium.",
        {"varianten": [dict(r, verdict=verdicts[i]) for i, r in enumerate(rows)],
         "deterministische_eignung": {"einsetzbar": einsetzbar, "nicht_einsetzbar": nicht_ok}})

    # Bericht in EINZELNE KAPITEL zerlegen → jedes separat rendern → zusammenfügen.
    # So reißt ein einzelnes problematisches Kapitel nicht den ganzen Bericht.
    _log("Setze Kapitel zusammen…", 84)
    def _join(*parts):
        return "\n".join(p for p in parts if p)

    ov_kenn = (f"![{overlay['kennlinien']['title']}]({overlay['kennlinien']['path']})\n"
               if "kennlinien" in overlay else "")
    ov_therm = (f"![{overlay['thermal']['title']}]({overlay['thermal']['path']})\n"
                if "thermal" in overlay else "")

    chapters = [
        ("00_titel", _join(
            f"# Vergleichsbericht: {len(variants)} Varianten einer IPM-Synchronmaschine\n",
            f"_Verglichene Varianten: {legend}._\n", p_over)),
        ("00b_bewertung", _join(
            "## Bewertung & Eignung (regelbasiert)\n",
            "_Diese Ampel ist deterministisch aus den berechneten Kennwerten abgeleitet "
            "(FEM-Sicherheitsfaktor ≥ 1,5; Magnet ≤ 150 °C; Wicklung ≤ 180 °C) und ist "
            "gegenüber dem nachfolgenden, sprachlich generierten Text maßgeblich._\n",
            tbl_verdict, "",
            "**Konkrete Warnungen:**\n", warn_block, "",
            det_reco)),
        ("01_methodik", _methodology_md()),
        ("02_gestaltung", _join(
            "## 2. Gestaltung und Auslegung der Varianten\n", tbl_param, "", p_design)),
        ("03_em", _join(
            "## 3. Elektromagnetik\n", tbl_metric, "", ov_kenn,
            _gallery_md(per_var, "em_field", "EM-Feld (Leerlauf)"),
            _gallery_md(per_var, "em_field_load", "EM-Feld (Last)"),
            _gallery_md(per_var, "em_curve", "EM-Kennlinie"), "", p_em)),
        ("04_luftspalt", _join(
            "## 4. Luftspaltflussdichte\n",
            _gallery_md(per_var, "airgap", "Luftspaltflussdichte"))),
        ("05_festigkeit", _join(
            "## 5. Festigkeit und Verformung\n",
            _gallery_md(per_var, "deformation", "Verformung (FEM)"))),
        ("06_verbindung", _join(
            "## 6. Welle–Blechpaket-Verbindung\n", tbl_conn, "",
            _gallery_md(per_var, "connection", "Welle-Nabe-Verbindung"))),
        ("07_thermik", _join(
            "## 7. Thermik und Magnettemperaturen\n", tbl_magtherm, "", ov_therm,
            _gallery_md(per_var, "thermal", "Thermik (LPTN)"), "", p_therm)),
        ("08_energie", _join(
            "## 8. Energiebilanz\n", tbl_energy, "", p_energy)),
        ("09_einfluss", _join(
            "## 9. Einfluss der Auslegungsänderungen\n", tbl_infl)),
        ("10_experten", expert_md),
        ("11_ranking", _join("## 11. Ranking und Empfehlung\n",
                             det_reco, "", p_rank)),
    ]

    _log("Rendere Kapitel einzeln + füge zusammen (pandoc + xelatex)…", 90)
    pdf_path = _render_chapters_pdf(chapters, out_dir,
                                    out_filename="vergleichsbericht_agentisch.pdf",
                                    progress_cb=_log)
    # Gesamtes Markdown zur Referenz ablegen
    md_full = "\n\n".join(c[1] for c in chapters)
    with open(os.path.join(out_dir, "bericht.md"), "w", encoding="utf-8") as f:
        f.write(md_full)
    _log(f"✓ Agentischer Vergleichsbericht: {os.path.basename(pdf_path)}", 100)
    return {"pdf": pdf_path, "md": os.path.join(out_dir, "bericht.md"),
            "model": model, "expert_model": emodel,
            "n_variants": len(variants), "n_chars": len(md_full),
            "n_chapters": len(chapters), "expert_outputs": expert_out}


def _clean_prose_keep_headings(text: str) -> str:
    """Wie _clean_prose, aber Überschriften (Experten-Abschnitte) bleiben erhalten."""
    text = _THINK_RE.sub("", text or "").strip()
    text = _strip_md_tables(text)
    text = _strip_value_numbers(text)   # Zahlen gehören in die Tabellen, nicht in die Prosa
    return _escape_pipes(_normalize_paragraphs(text).strip())


def _render_chapters_pdf(chapters, out_dir, out_filename="bericht.pdf", progress_cb=None):
    """Rendere jedes Kapitel (id, markdown) zu einem eigenen PDF und füge sie mit
    pdfunite zu einem Gesamtbericht zusammen. Schlägt ein Kapitel im LaTeX fehl,
    wird es als reiner Text-Fallback gerendert, statt den ganzen Bericht zu kippen."""
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    parts = []
    n = len(chapters)
    for i, (cid, md) in enumerate(chapters):
        if not (md or "").strip():
            continue
        pdf_i = f"_kap_{i:02d}_{cid}.pdf"
        md_i  = f"_kap_{i:02d}_{cid}.md"
        _log(f"  Kapitel {i+1}/{n}: {cid}", None)
        try:
            p = render_pdf(md, out_dir, out_filename=pdf_i,
                           md_filename=md_i, page_numbers=False)
            parts.append(p)
        except Exception as e:
            _log(f"  ⚠ Kapitel {cid} fehlgeschlagen ({str(e)[:80]}) → Text-Fallback", None)
            # harte Bereinigung: nur Überschriften + Fließtext, keine Bilder/Tabellen/Math
            safe = "\n".join(
                l for l in md.split("\n")
                if not l.lstrip().startswith(("|", "![", "$$"))
            )
            safe = re.sub(r"\$[^$]*\$", "", safe)          # Inline-Math entfernen
            try:
                p = render_pdf(safe or f"## {cid}\n\n(Kapitel nicht darstellbar)",
                               out_dir, out_filename=pdf_i, md_filename=md_i,
                               page_numbers=False)
                parts.append(p)
            except Exception as e2:
                _log(f"  ⚠ Kapitel {cid} auch im Fallback fehlgeschlagen: {str(e2)[:80]}", None)

    final = os.path.join(out_dir, out_filename)
    if not parts:
        raise RuntimeError("Kein Kapitel konnte gerendert werden")
    if len(parts) == 1:
        os.replace(parts[0], final)
    else:
        res = subprocess.run(["pdfunite", *parts, final],
                             capture_output=True, text=True, timeout=120)
        if res.returncode != 0 or not os.path.exists(final):
            # Fallback-Merge via Ghostscript
            gs = subprocess.run(["gs", "-dBATCH", "-dNOPAUSE", "-q",
                                 "-sDEVICE=pdfwrite", f"-sOutputFile={final}", *parts],
                                capture_output=True, text=True, timeout=120)
            if gs.returncode != 0 or not os.path.exists(final):
                raise RuntimeError(f"PDF-Merge fehlgeschlagen: {res.stderr[-200:]}")
        # Kapitel-Einzel-PDFs aufräumen
        for p in parts:
            try: os.remove(p)
            except OSError: pass
    return final


# ── Parameterstudie-Bericht (LLM, Studiendaten als Prompt-Basis) ─────────────

def _study_metric_stats(study: dict):
    """Per-metric Start/Ende/Min/Max (+ Parameterwert bei Min/Max) + Tendenz."""
    xs   = study.get("x", [])
    mets = study.get("metrics", {})
    out  = []
    for m in study.get("metric_meta", []):
        key, label, unit = m["key"], m["label"], m["unit"]
        ys = mets.get(key, [])
        pairs = [(x, y) for x, y in zip(xs, ys) if y is not None]
        if not pairs:
            continue
        x0, y0 = pairs[0]
        x1, y1 = pairs[-1]
        ymin = min(pairs, key=lambda p: p[1])
        ymax = max(pairs, key=lambda p: p[1])
        rng  = abs(ymax[1] - ymin[1])
        ref  = max(abs(ymax[1]), abs(ymin[1]), 1e-9)
        eps = 1e-9 + 0.01 * abs(x1 - x0)
        max_interior = x0 + eps < ymax[0] < x1 - eps
        min_interior = x0 + eps < ymin[0] < x1 - eps
        if rng / ref < 0.02:
            trend = "nahezu konstant"
        elif max_interior:
            trend = "Maximum im Inneren (Optimum)"
        elif min_interior:
            trend = "Minimum im Inneren"
        elif y1 > y0:
            trend = "steigend"
        else:
            trend = "fallend"
        out.append({"key": key, "label": label, "unit": unit,
                    "start": y0, "ende": y1, "min": ymin[1], "argmin": ymin[0],
                    "max": ymax[1], "argmax": ymax[0], "trend": trend,
                    "max_interior": max_interior, "min_interior": min_interior})
    return out


def _study_downsample(study: dict, max_rows: int = 15):
    """Evenly-spaced subset of the step rows: [(x, {metric_key: val})]."""
    xs   = study.get("x", [])
    mets = study.get("metrics", {})
    keys = [m["key"] for m in study.get("metric_meta", [])]
    n = len(xs)
    if n == 0:
        return [], keys
    idx = (list(range(n)) if n <= max_rows
           else sorted({round(i * (n - 1) / (max_rows - 1)) for i in range(max_rows)}))
    rows = [(xs[i], {k: mets.get(k, [None] * n)[i] for k in keys}) for i in idx]
    return rows, keys


def _study_data_table(study: dict, plabel: str):
    """Deterministic per-step value table (downsampled) — the numeric basis of the
    evaluation, so every figure is traceable to a step."""
    rows, keys = _study_downsample(study)
    if not rows:
        return ""
    meta = {m["key"]: m for m in study.get("metric_meta", [])}
    hdr  = [plabel] + [f"{meta[k]['label']} [{meta[k]['unit']}]" if meta[k]['unit'] else meta[k]['label']
                       for k in keys]
    lines = ["| " + " | ".join(_mdesc(h) for h in hdr) + " |",
             "|" + "---|" * len(hdr)]
    for x, vals in rows:
        cells = [_fmt_val(x, 2)] + [_fmt_val(vals[k], 3) for k in keys]
        lines.append("| " + " | ".join(_mdesc(c) for c in cells) + " |")
    return "\n".join(lines)


def _study_md_table(stats, plabel):
    lines = [f"| Kennwert | Start | Ende | Min (bei {_mdesc(plabel)}) | Max (bei {_mdesc(plabel)}) | Tendenz |",
             "|" + "---|" * 6]
    for s in stats:
        u = s["unit"]
        lines.append(
            f"| {_mdesc(s['label'])} "
            f"| {_fmt_val(s['start'], 3, u)} | {_fmt_val(s['ende'], 3, u)} "
            f"| {_fmt_val(s['min'], 3, u)} ({_fmt_val(s['argmin'], 2)}) "
            f"| {_fmt_val(s['max'], 3, u)} ({_fmt_val(s['argmax'], 2)}) "
            f"| {s['trend']} |")
    return "\n".join(lines)


def _study_prompt(study, stats, machine):
    plabel = study.get("label", study.get("param", "?"))
    xs = study.get("x", [])
    rng = f"{xs[0]:g} … {xs[-1]:g}" if xs else "?"
    facts = "\n".join(
        f"- {s['label']}: Start {s['start']:.3g} {s['unit']}, Ende {s['ende']:.3g} {s['unit']}, "
        f"Min {s['min']:.3g} bei {s['argmin']:g}, Max {s['max']:.3g} bei {s['argmax']:g}, {s['trend']}"
        for s in stats)
    # downsampled per-step series so the evaluation reflects the WHOLE curve shape,
    # not just the endpoints/extrema (the output prose is value-free either way).
    rows, keys = _study_downsample(study, max_rows=10)
    kmeta = {m["key"]: m["label"] for m in study.get("metric_meta", [])}
    series_lines = []
    for x, vals in rows:
        cells = ", ".join(f"{kmeta.get(k,k)}={vals[k]:.3g}" for k in keys if vals.get(k) is not None)
        series_lines.append(f"  {plabel}={x:g}: {cells}")
    series = "\n".join(series_lines)
    return (
        "Du bist ein erfahrener Auslegungsingenieur für IPM-Synchronmaschinen und schreibst "
        "die ERLÄUTERUNG zu einer Parameterstudie auf Deutsch.\n\n"
        f"Variierter Parameter: {plabel}, Bereich {rng}, bei fester Drehzahl "
        f"{study.get('rpm', 0):.0f} U/min.\n\n"
        f"MASCHINE:\n{machine}\n\n"
        f"GEMESSENE ABHÄNGIGKEITEN (Datenbasis):\n{facts}\n\n"
        f"SCHRITT-WERTE (Auszug, zur Beurteilung des Verlaufs):\n{series}\n\n"
        f"{_PROSE_GUARDRAILS}\n"
        "Schreibe Markdown mit genau diesen Abschnitten (## Überschriften):\n"
        "1. Überblick — was die Studie zeigt (qualitativ)\n"
        "2. Einfluss je Kennwert — erkläre kausal-physikalisch, warum der Parameter den "
        "jeweiligen Kennwert so verändert (steigend/fallend/Optimum)\n"
        "3. Zielkonflikte — welche Kennwerte gegenläufig sind\n"
        "4. Empfehlung — welcher Parameterbereich für welches Ziel sinnvoll ist\n\n"
        "REGELN: KEINE Zahlenwerte/Einheiten im Fließtext (die stehen in der Tabelle) — "
        "beschreibe QUALITATIV (höher/niedriger, Optimum, gegenläufig). Keine eigenen "
        "Tabellen. Beginne direkt mit `## Überblick`."
    )


def generate_paramstudy_report(study: dict, payload: dict, out_dir: str,
                               model: str = DEFAULT_MODEL, progress_cb=None) -> dict:
    """LLM report for a parameter study. The study data (per-metric trends) is the
    basis of the prompt; numbers live in a deterministic table, the prose is
    qualitative. Embeds the small-multiples chart + a few field-line images.
    Returns {"pdf": path, "md": path, "model": …}."""
    import base64
    def _log(msg, pct=None):
        if progress_cb: progress_cb(msg, pct)

    os.makedirs(out_dir, exist_ok=True)
    cdir = os.path.join(out_dir, "charts")
    os.makedirs(cdir, exist_ok=True)

    plabel = study.get("label", study.get("param", "?"))
    stats  = _study_metric_stats(study)

    # machine datasheet for context (reuse ema_chat helper on a meta-like dict)
    try:
        import ema_chat
        machine = ema_chat._machine_datasheet({"payload": payload, **payload})
    except Exception:
        g = payload.get("geom", {}) or {}
        machine = (f"Topologie {TOPOLOGY_LABELS.get(g.get('magShape','v'), g.get('magShape'))}, "
                   f"{int(g.get('p',0))*2} Pole, {g.get('slots')} Nuten, "
                   f"Stator-Ø {g.get('statorOD')} mm.")

    _log(f"Analysiere Studiendaten ({len(stats)} Kennwerte)…", 15)

    # images: chart + a few sampled field frames
    md_imgs = []
    if study.get("chart_b64"):
        p = os.path.join(cdir, "study_chart.png")
        with open(p, "wb") as f: f.write(base64.b64decode(study["chart_b64"]))
        md_imgs.append(("charts/study_chart.png",
                        f"Kennwerte über {plabel}"))
    fimgs = study.get("field_images", []) or []
    if fimgs:
        pick = [fimgs[0], fimgs[len(fimgs)//2], fimgs[-1]] if len(fimgs) >= 3 else fimgs
        for k, im in enumerate(pick):
            p = os.path.join(cdir, f"study_field_{k}.png")
            with open(p, "wb") as f: f.write(base64.b64decode(im["b64"]))
            md_imgs.append((f"charts/study_field_{k}.png",
                            f"Magnetfeld bei {plabel} = {im['value']:g}"))

    _log(f"Frage {model} (qualitative Erläuterung)…", 35)
    try:
        prose = _clean_prose_keep_headings(call_ollama(_study_prompt(study, stats, machine), model=model))
    except Exception as e:
        _log(f"⚠ LLM nicht erreichbar ({e}) — Bericht ohne Fließtext", 50)
        prose = ("## Überblick\n\n_Die qualitative Erläuterung konnte nicht erzeugt werden "
                 "(LLM nicht erreichbar). Die Kennwert-Tabelle und Diagramme unten sind "
                 "vollständig._")

    xs = study.get("x", [])
    rng = f"{xs[0]:g} … {xs[-1]:g}" if xs else "?"
    parts = [
        f"# Parameterstudie: {plabel}",
        "",
        f"**Variierter Parameter:** {plabel}  ·  **Bereich:** {rng}  ·  "
        f"**Drehzahl (fest):** {study.get('rpm',0):.0f} U/min  ·  "
        f"**Stützstellen:** {study.get('steps','?')}",
        "",
        "## Kennwert-Abhängigkeiten",
        "",
        _study_md_table(stats, plabel),
        "",
    ]
    # chart first, then prose, then field gallery
    if md_imgs:
        rel, cap = md_imgs[0]
        parts += [f"![{cap}]({rel})", ""]
    parts += [prose, ""]
    for rel, cap in md_imgs[1:]:
        parts += [f"![{cap}]({rel})", ""]

    # per-step value table (downsampled) — the numeric basis of the evaluation
    data_tbl = _study_data_table(study, plabel)
    if data_tbl:
        parts += ["## Datentabelle (Schrittwerte, Auszug)", "",
                  f"_Auszug der berechneten Stützstellen ({study.get('steps','?')} insgesamt); "
                  f"die vollständigen Schrittwerte stehen als CSV-Export zur Verfügung._", "",
                  data_tbl, ""]

    md = "\n".join(parts)
    _log("Rendere PDF (pandoc + xelatex)…", 80)
    pdf_path = render_pdf(md, out_dir, out_filename="parameterstudie.pdf",
                          md_filename="parameterstudie.md")
    _log(f"✓ Bericht: {os.path.basename(pdf_path)}", 100)
    return {"pdf": pdf_path, "md": os.path.join(out_dir, "parameterstudie.md"), "model": model}
