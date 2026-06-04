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
        ("airgap",        "charts/airgap.png",                   "Luftspaltflussdichte"),
        ("em_curve",      "charts/em_curve.png",                 "EM-Kennlinie über Drehzahl"),
        ("structural",    "charts/structural_sweep.png",         "Strukturkennlinie"),
        ("deformation",   "charts/deformation.png",              "FEM-Verformung"),
        ("thermal",       "charts/thermal.png",                  "Thermische Analyse (LPTN)"),
        ("drivecycle",    "charts/drivecycle.png",               "Fahrzyklus-Auswertung"),
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

    return f"""Du bist ein erfahrener E-Maschinen-Auslegungsingenieur und schreibst einen technischen Auslegungsbericht auf Deutsch.

Hier sind die Analyse-Ergebnisse als JSON:

```json
{payload_json}
```

Schreibe einen strukturierten, sachlichen Bericht in Markdown mit genau diesen Abschnitten:

1. **Zusammenfassung** — 3–5 Sätze zu den wichtigsten Kennwerten und der Gesamtbewertung
2. **Geometrie und Konstruktion** — Abmessungen, Polzahl/Nutzahl, gewähltes Magnetlayout, Masse
3. **Elektromagnetische Auslegung** — B_gap, Kt, Drehmoment, Aussage zum Rastmoment (LCM)
4. **Festigkeit** — σ_v,max, Sicherheitsfaktor, Verschiebung, max. sichere Drehzahl
5. **Thermisches Verhalten** — Kühlung, Endtemperaturen, Gesamtverluste, ggf. Warnungen
{fahrzyklus_section}
7. **Empfehlungen** — 3–5 konkrete Verbesserungsvorschläge basierend auf den Zahlen

BEBILDERUNG: Füge Platzhalter `[BILD:KEY]` an sinnvollen Stellen im Fließtext ein.
Verfügbare Bild-KEYs: {available}

Zuordnung (strikt einhalten — kein Bild in Abschnitt 1 Zusammenfassung):
- Abschnitt 2 Geometrie:              [BILD:cross_section] oder [BILD:side_view]
- Abschnitt 3 Elektromagnetik:        [BILD:airgap]  und  [BILD:em_curve]
- Abschnitt 4 Festigkeit:             [BILD:structural]  und ggf. [BILD:deformation]
- Abschnitt 5 Thermik:                [BILD:thermal]
- Abschnitt 6 Fahrzyklus:             [BILD:drivecycle]{(f"  und  {vollast_img}") if vollast_img else ""}{(f"  und  {anhaenger_img}") if anhaenger_img else ""}

FORMATIERUNGSREGELN (unbedingt einhalten):
- Schreibe echten Fließtext in Absätzen. Kein Zeilenumbruch mitten im Satz.
- Pro Abschnitt 1–3 Absätze, danach ggf. eine Aufzählung. Keine abgebrochenen Listen.
- Masse in kg ausgeben (mass_g-Feld durch 1000 teilen und als kg angeben).
- Alle Größen mit SI-Einheit: MPa, Nm, kWh, °C, U/min, kg usw.
- Keine Codeblöcke, keine Einleitungsfloskeln, keine einzelnen Stichworte als eigene Zeile.

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
            or "[BILD:" in line
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


def render_pdf(md: str, project_dir: str, out_filename: str = "bericht.pdf") -> str:
    """Write `bericht.md` + `bericht.pdf` into project_dir. Returns PDF path."""
    md_path  = os.path.join(project_dir, "bericht.md")
    pdf_path = os.path.join(project_dir, out_filename)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)

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
        "--resource-path", project_dir,
        "-o", pdf_path,
    ]
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
    md_final = insert_images(md_raw, ctx["_img_map"])

    _log("Rendere PDF (pandoc + xelatex)…", 85)
    pdf_path = render_pdf(md_final, project_dir)
    _log(f"✓ Bericht: {os.path.basename(pdf_path)}", 100)

    return {
        "pdf":     pdf_path,
        "md":      os.path.join(project_dir, "bericht.md"),
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
    md_main = insert_images(md_main, ctx["_img_map"])

    # Append expert section (with images + paragraph normalisation)
    expert_md = assemble_expert_section(expert_out, img_map=ctx["_img_map"])
    md_final  = md_main.rstrip() + "\n\n---\n\n" + expert_md

    _log("Rendere PDF (pandoc + xelatex)…", 85)
    pdf_path = render_pdf(md_final, project_dir, out_filename="bericht_agentisch.pdf")
    _log(f"✓ Agentischer Bericht: {os.path.basename(pdf_path)}", 100)

    return {
        "pdf":            pdf_path,
        "md":             os.path.join(project_dir, "bericht.md"),
        "model":          model,
        "expert_model":   emodel,
        "n_chars":        len(md_final),
        "expert_outputs": expert_out,
    }
