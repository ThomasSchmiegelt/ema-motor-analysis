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

# Welche Kennzahlen gezeigt werden, in Plot-Reihenfolge — die BESCHRIFTUNG kommt
# aus `ema_optimize.METRICS`, derselben Quelle, aus der auch die Zahlen stammen.
#
# Hier stand bis zum 12.09.2026 eine zweite, handgefuehrte Tabelle, und sie war
# auseinandergelaufen: `mass_g` hiess hier **„Aktivteil-Masse"**, waehrend die
# Zahl in `ema_optimize._eval_geom` als `rotor + magnet` gerechnet wird — ohne
# Statoreisen und ohne Kupfer (dort korrekt „Rotor+Magnet-Masse" beschriftet).
# Aufgefallen ist es an einer Luftspalt-Studie: der Luftspalt aendert ueber
# `statorID` NUR den Stator, also stand die Spalte ueber 0,1…2,0 mm bei exakt
# 23008 g still — was wie ein Rechenfehler aussieht und keiner war. Eine falsche
# Beschriftung ist hier teurer als eine fehlende: sie laesst eine richtige Zahl
# falsch erscheinen.
_STUDY_KEYS = ["Kt", "T_maxwell", "B_gap", "max_safe_rpm",
               "mass_g", "T_magnet", "T_winding", "P_total"]


def _ohne_einheit(label: str) -> str:
    """Eine nachgestellte ``[Einheit]`` aus dem Label nehmen.

    ``O.METRICS`` fuehrt sie uneinheitlich mit (``"Kt [Nm/A]"``, aber
    ``"T_Magnet"``), und Kopfzeile wie Achsenbeschriftung haengen die Einheit
    ohnehin aus dem eigenen Feld an — sonst stuende ``Kt [Nm/A] [Nm/A]`` in der
    CSV. Die Einheit bleibt also EIN Feld, und das Label bleibt EINE Quelle.
    """
    lab = label.strip()
    if lab.endswith("]") and " [" in lab:
        lab = lab[:lab.rindex(" [")].strip()
    return lab


_STUDY_METRICS = [(k, _ohne_einheit(O.METRICS[k]["label"]), O.METRICS[k]["unit"])
                  for k in _STUDY_KEYS if k in O.METRICS]


def _fig_b64(fig, dpi=120):
    import base64
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, bbox_inches="tight",
                facecolor=fig.get_facecolor())
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def wirkungslos_grund(payload, param, lo, hi):
    """Bewegt dieser Parameter in DIESER Auslegung ueberhaupt etwas — und wenn
    nicht, warum? Gibt einen Satz zurueck oder ``""``.

    Anlass: eine Testreihe ueber alle elf Parameter, 15 Schritte je Studie.
    **Vier** davon lieferten eine vollkommen flache Kurve, und an der Kurve war
    nicht zu erkennen, ob die Auslegung unempfindlich ist oder das Werkzeug
    nichts tut. Gemessen war es dreimal das Zweite und einmal das Erste:

    * ``magDist`` und ``magDepthRel`` sind im **Wandmodus** (`pocketMode="wand"`,
      die Vorgabe von ``--frisch``) ABGELEITETE Groessen — sie werden aus den
      Wandstaerken gerechnet und zurueckgeschrieben. Als Eingabe tun sie nichts;
      im Positionsmodus bewegen dieselben Werte die Taschen sofort (nachgeprueft
      an ``ema_topology.magnet_legs``).
    * ``magAsym`` gilt nur fuer ``magShape="vasym"``. An einer symmetrischen
      V-Form ist er wirkungslos — an der asymmetrischen kippt er die Schenkel
      (gemessen 1,047/−1,047 rad → 1,484/−0,524).
    * ``magGap`` bewegt die Tasche sehr wohl, aber nicht die Kennzahlen: der
      Klebespalt aendert die Tasche, nicht den Magneten, und ``_analytical_Bgap``
      rechnet aus Magnetlaenge und -dicke. Das ist richtig so und im 3-D-Pfad
      anders — hier ist es eine Aussage ueber das Modell, kein Fehler.

    Eine flache Kurve ohne Begruendung ist die teuerste Art von Ergebnis: sie
    sieht nach einem Rechenfehler aus und ist keiner (derselbe Grund, aus dem
    ``ema_paarvergleich`` „bewegt NICHT: alles" ausdruecklich hinschreibt).
    """
    geom = payload.get("geom") or {}
    if param in ("magDist", "magDepthRel") and str(geom.get("pocketMode")) == "wand":
        return ("%s ist im Wandmodus (`pocketMode=\"wand\"`) eine ABGELEITETE "
                "Groesse — sie folgt aus den Wandstaerken und wird zurueck-"
                "geschrieben. Als Eingabe bewegt sie nichts. Fuer eine Studie "
                "darueber `pocketMode=\"position\"` setzen." % param)
    if param == "magAsym" and str(geom.get("magShape")) != "vasym":
        return ("magAsym gilt nur fuer die asymmetrische V-Form "
                "(`magShape=\"vasym\"`); diese Auslegung ist `%s`."
                % geom.get("magShape"))
    # Allgemeiner Fall: erreicht der Parameter die Geometrie ueberhaupt?
    base_geom = geom
    base_axial = float(payload.get("axial_len", geom.get("axialLen", 80)))
    try:
        g_lo, a_lo = O._apply_params(base_geom, base_axial, {param: lo})
        g_hi, a_hi = O._apply_params(base_geom, base_axial, {param: hi})
    except Exception:                                           # noqa: BLE001
        return ""
    if g_lo == g_hi and a_lo == a_hi:
        return ("%s erreicht die Geometrie dieser Auslegung nicht — zwischen "
                "%g und %g aendert sich kein einziger Zeichnungswert." % (param, lo, hi))
    return ""


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
    n_ok = n_fail = n_unerreichbar = 0
    unerreichbar_grund = ""
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
            if m.get("erreichbar") is False:
                # Der Punkt existiert nicht: Verluste und Temperaturen sind
                # `None`. Ohne diesen Zaehler steht spaeter eine leere Spalte da,
                # und eine leere Spalte sieht wie ein Rechenfehler aus — genau
                # so wurde sie auch gemeldet.
                n_unerreichbar += 1
                if not unerreichbar_grund:
                    unerreichbar_grund = m.get("grund", "")
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

    hinweis = ""
    # Wandern die Magnete mit? Bei den Wellenparametern wird ihre absolute Lage
    # gehalten (`ema_optimize.magnete_halten`); wo das geometrisch nicht geht —
    # Speiche und Bar spannen den Ringraum zwischen Welle und Rand aus —, sagt
    # es der Hinweis, statt eine Kurve zu zeigen, in der zwei Aenderungen
    # stecken.
    if spec.get("haelt_magnete"):
        _hin = ""
        for _v in (lo, hi):
            _g, _ = O._apply_params(base_geom, base_axial, {param: cast(_v)})
            _hin = _g.get("_magnetlage_hinweis") or _hin
        if _hin:
            hinweis = _hin
            log("⚠ " + _hin, 99)
    # Bewegt sich ueberhaupt etwas — und wenn nicht, warum nicht?
    flach = [k for k, _, _ in _STUDY_METRICS
             if len({v for v in metric_series[k] if v is not None}) <= 1]
    grund = wirkungslos_grund(payload, param, lo, hi)
    if grund:
        hinweis = ((hinweis + " ") if hinweis else "") + grund
        log("⚠ " + grund, 99)
    elif len(flach) == len(_STUDY_METRICS):
        hinweis = ("%s bewegt die Zeichnung, aber KEINE der gerechneten "
                   "Kennzahlen — der schnelle Bewerter rechnet analytisch und "
                   "sieht diese Groesse nicht." % label)
        log("⚠ " + hinweis, 99)
    if n_unerreichbar:
        hinweis = ((hinweis + " ") if hinweis else "") + (
            f"{n_unerreichbar} von {steps} Schritten erreichen den geforderten "
            f"Betriebspunkt NICHT — dort sind Verluste und Temperaturen leer "
            f"(und nicht 0). {unerreichbar_grund}")
        log("⚠ " + hinweis, 99)
    log(f"✓ Fertig: {n_ok} ausgewertet, {n_fail} fehlgeschlagen"
        + (f", {n_unerreichbar} ohne erreichbaren Betriebspunkt" if n_unerreichbar else ""),
        100)
    return {
        "n_unerreichbar": n_unerreichbar,
        "hinweis":        hinweis,
        "flache_kennzahlen": flach,
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
                # `_ax` wurde bis zum 12.09.2026 verworfen — eine Laengenstudie
                # rechnete ihre Feldbilder deshalb auf festen 80 mm.
                em0   = ema_analysis.run_em_analysis(geom, N=min(field_N, 160),
                                                     rotor_angle=0.0, axial_mm=_ax)
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
                    # Die Datei wird MITGEFUEHRT, damit der Studien-Store die
                    # Galerie spaeter aus denselben Bildern wiederherstellen
                    # kann, statt eine zweite Kopie danebenzulegen.
                    images.append({"value": val, "b64": b64,
                                   "datei": (f"frame_{n_disk-1:04d}.png" if out_dir else None)})
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


# ─────────────────────────────────────────────────────────────────────────────
# Studien-Store — jede Studie in ihren EIGENEN Ordner
# ─────────────────────────────────────────────────────────────────────────────
# Bis zum 12.09.2026 schrieben ALLE Studien in EINEN Ordner
# (`server.STUDY_FIELD_DIR` = `~/cae_projekte/_paramstudy`), und
# `_render_field_series` raeumte ihn zu Beginn jedes Laufs leer — die zweite
# Studie ueberschrieb also die Bilder und das Video der ersten. Schlimmer: das
# Ergebnis selbst (Zahlen, Diagramm, CSV) lag ueberhaupt nur im Serverspeicher
# (`_study_state["result"]`), war nach einem Neustart weg und liess sich nie
# wieder ansehen. Aus der Sicht dessen, der davorsitzt, ist „gerechnet, aber
# nicht auffindbar" dasselbe wie „nicht gerechnet" — derselbe Befund wie bei
# den Agentenlaeufen vor `/agent/laeufe` und bei den Verbergebnissen vor
# `ema_steckbrief.ablegen`.
#
# Jetzt: ein Ordner je Studie, benannt nach Zeit UND Parameter (`20260912_
# 121500_magAngle`), mit allem darin — Zahlen, Diagramm, CSV, Feldbilder,
# Video und dem Payload, aus dem sie gerechnet wurde. Er liegt beim PROJEKT,
# wenn eines gebunden ist (`<projekt>/parameterstudien/`), sonst unter
# `~/cae_projekte/_paramstudy/`; dasselbe Verhaeltnis wie bei den
# em3d-/Oel-/FluidX3D-Varianten.

import json
import os
import time

STUDIEN_UNTERORDNER = "parameterstudien"
GLOBALE_WURZEL = os.path.expanduser("~/cae_projekte/_paramstudy")


def studien_wurzel(project_dir=None):
    """Wo die Studien dieses Laufs hingehoeren: ans Projekt, sonst global."""
    if project_dir and os.path.isdir(project_dir):
        return os.path.join(project_dir, STUDIEN_UNTERORDNER)
    return GLOBALE_WURZEL


def studie_anlegen(wurzel, param):
    """Legt den Ordner fuer EINE Studie an und gibt (kennung, pfad) zurueck.

    Wird VOR dem Lauf gerufen, weil die Feldbilder waehrend des Laufs
    hineingeschrieben werden. Zwei Studien in derselben Sekunde bekommen ein
    ``-2`` angehaengt (dasselbe wie `ema_steckbrief.ablegen` — ein Agentenzug
    kann zwei Studien in Millisekunden starten)."""
    os.makedirs(wurzel, exist_ok=True)
    basis = "%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), _dateiname(param))
    kennung, n = basis, 1
    while os.path.exists(os.path.join(wurzel, kennung)):
        n += 1
        kennung = "%s-%d" % (basis, n)
    pfad = os.path.join(wurzel, kennung)
    os.makedirs(pfad, exist_ok=True)
    return kennung, pfad


def _dateiname(text):
    """Parametername als Ordnerbestandteil — nur das, was sicher ist."""
    return "".join(c if (c.isalnum() or c in "._-") else "_" for c in str(text))[:40] or "studie"


def csv_text(result):
    """Die Studie als CSV — **eine** Quelle fuer den Download und die abgelegte
    Datei. Sie stand vorher nur in `server.param_study_csv`; eine zweite
    Fassung fuer den Store waere genau die Art Abschrift, die auseinanderlaeuft
    (der Spaltenkopf der Metriken kommt ohnehin schon aus `ema_optimize`)."""
    xs = result.get("x") or []
    mets = result.get("metrics") or {}
    meta = result.get("metric_meta") or []
    keys = [m["key"] for m in meta]
    kopf = [result.get("label", result.get("param", "param"))] + \
           [("%s [%s]" % (m["label"], m["unit"])) if m.get("unit") else m["label"]
            for m in meta]
    zeilen = [";".join(kopf)]
    for i, x in enumerate(xs):
        reihe = ["%g" % x]
        for k in keys:
            v = (mets.get(k) or [None] * len(xs))[i]
            reihe.append("" if v is None else "%g" % v)
        zeilen.append(";".join(reihe))
    return "\n".join(zeilen)


def ablegen(result, pfad, payload=None, notiz=""):
    """Schreibt die fertige Studie in ihren Ordner: ``studie.json`` (schlank,
    ohne base64), ``studie.csv``, ``verlauf.png`` und — wenn vorhanden — die
    Feldbilder/das Video, die waehrend des Laufs schon dort gelandet sind.

    ``payload`` kommt mit, damit die Studie **nachvollziehbar** ist: ohne die
    Geometrie, an der sie gerechnet wurde, ist eine Kurve eine Behauptung."""
    import base64
    os.makedirs(pfad, exist_ok=True)
    schlank = {k: v for k, v in result.items()
               if k not in ("chart_b64", "field_images")}
    schlank["field_images"] = [{"value": b.get("value"), "datei": b.get("datei")}
                               for b in (result.get("field_images") or [])
                               if b.get("datei")]
    schlank["kennung"] = os.path.basename(pfad)
    schlank["zeitpunkt"] = time.strftime("%Y-%m-%d %H:%M")
    schlank["notiz"] = notiz or ""
    if payload is not None:
        schlank["payload"] = payload
    try:
        if result.get("chart_b64"):
            with open(os.path.join(pfad, "verlauf.png"), "wb") as f:
                f.write(base64.b64decode(result["chart_b64"]))
        with open(os.path.join(pfad, "studie.csv"), "w", encoding="utf-8") as f:
            f.write(csv_text(result) + "\n")
        tmp = os.path.join(pfad, "studie.json.tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(schlank, f, ensure_ascii=False)
        os.replace(tmp, os.path.join(pfad, "studie.json"))
    except (OSError, ValueError) as e:                     # noqa: BLE001
        return {"ok": False, "error": str(e)}
    return {"ok": True, "kennung": schlank["kennung"], "pfad": pfad}


def _kurz(studie, pfad):
    """Eine Zeile fuer die Uebersicht — ohne die Zahlenreihen einzulesen."""
    mets = studie.get("metrics") or {}
    def spanne(k):
        werte = [v for v in (mets.get(k) or []) if v is not None]
        return (min(werte), max(werte)) if werte else None
    return {
        "kennung": studie.get("kennung", os.path.basename(pfad)),
        "zeitpunkt": studie.get("zeitpunkt", ""),
        "param": studie.get("param"), "label": studie.get("label"),
        "x_von": (studie.get("x") or [None])[0],
        "x_bis": (studie.get("x") or [None])[-1],
        "steps": studie.get("steps"), "rpm": studie.get("rpm"),
        "n_ok": studie.get("n_ok"), "n_fail": studie.get("n_fail"),
        "n_unerreichbar": studie.get("n_unerreichbar"),
        "video": os.path.exists(os.path.join(pfad, "anim.mp4")),
        "bericht": os.path.exists(os.path.join(pfad, "parameterstudie.pdf")),
        "n_feldbilder": len(studie.get("field_images") or []),
        "Kt_spanne": spanne("Kt"), "notiz": studie.get("notiz", ""),
    }


def liste(wurzel):
    """Alle abgelegten Studien, neueste zuerst."""
    out = []
    if not os.path.isdir(wurzel):
        return out
    for kennung in sorted(os.listdir(wurzel), reverse=True):
        pfad = os.path.join(wurzel, kennung)
        datei = os.path.join(pfad, "studie.json")
        if not os.path.isdir(pfad) or not os.path.exists(datei):
            continue
        try:
            with open(datei, encoding="utf-8") as f:
                out.append(_kurz(json.load(f), pfad))
        except (OSError, ValueError):
            continue
    return out


def laden(wurzel, kennung):
    """Eine abgelegte Studie im Format von ``run_study`` zurueckgeben —
    Diagramm und Feldbilder wieder als base64, damit das Frontend sie durch
    DIESELBE Zeichenfunktion schickt wie einen frischen Lauf (eine zweite
    waere die naechste Stelle, an der zwei Darstellungen auseinanderlaufen)."""
    import base64
    pfad = os.path.join(wurzel, kennung)
    datei = os.path.join(pfad, "studie.json")
    if not os.path.exists(datei):
        return None
    try:
        with open(datei, encoding="utf-8") as f:
            studie = json.load(f)
    except (OSError, ValueError):
        return None
    chart = os.path.join(pfad, "verlauf.png")
    if os.path.exists(chart):
        with open(chart, "rb") as f:
            studie["chart_b64"] = base64.b64encode(f.read()).decode()
    bilder = []
    for b in studie.get("field_images") or []:
        bp = os.path.join(pfad, b.get("datei") or "")
        if b.get("datei") and os.path.exists(bp):
            with open(bp, "rb") as f:
                bilder.append({"value": b.get("value"),
                               "b64": base64.b64encode(f.read()).decode()})
    studie["field_images"] = bilder
    studie["field_video"] = os.path.exists(os.path.join(pfad, "anim.mp4"))
    studie["gespeichert"] = True
    return studie


def video_pfad(wurzel, kennung):
    p = os.path.join(wurzel, kennung, "anim.mp4")
    return p if os.path.exists(p) else None


def bericht_pfad(wurzel, kennung, name="parameterstudie.pdf"):
    """Pfad des abgelegten Studienberichts (oder None). Der Bericht liegt IM
    Studienordner, neben den Zahlen, aus denen er entstanden ist — ein Bericht
    an einem anderen Ort ist beim naechsten Lauf nicht mehr zuzuordnen."""
    p = os.path.join(wurzel, kennung, name)
    return p if os.path.exists(p) else None


def reihe_bericht_pfad(wurzel, name="studienreihe.pdf"):
    """Der Reihenbericht liegt eine Ebene ueber den Studien — er gehoert keiner
    einzelnen."""
    p = os.path.join(os.path.dirname(wurzel.rstrip("/")), name)
    return p if os.path.exists(p) else None


def csv_pfad(wurzel, kennung):
    p = os.path.join(wurzel, kennung, "studie.csv")
    return p if os.path.exists(p) else None


def loeschen(wurzel, kennung):
    import shutil
    p = os.path.join(wurzel, kennung)
    if os.path.isdir(p) and os.path.exists(os.path.join(p, "studie.json")):
        shutil.rmtree(p, ignore_errors=True)
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# Reihenauswertung — mehrere Studien nebeneinander
# ─────────────────────────────────────────────────────────────────────────────
# Eine einzelne Studie sagt, WIE ein Parameter wirkt. Eine Reihe sagt, WELCHER
# ueberhaupt zuerst anzufassen ist — und das ist die Frage, die vor der
# Auslegung steht (dasselbe Argument, aus dem `ema_paarvergleich` neben den
# Paaren die Spannweite je Achse ausgibt).
#
# **Der Vergleich gilt nur, wenn alle Studien vom SELBEN Entwurf ausgehen.**
# Spannweiten zweier Studien gegeneinander zu stellen, die an verschiedenen
# Maschinen gerechnet wurden, ist keine Rangliste, sondern eine Verwechslung —
# und man sieht es den Zahlen nicht an. `reihe_auswerten` prueft das ueber die
# Payload-Marke (`ema_projekt.payload_marke`, dieselbe Quelle, an der auch die
# Bruecke zwischen Agent und Formular haengt) und sagt es, statt zu rechnen.

def _spanne(werte):
    w = [v for v in werte if v is not None]
    if len(w) < 2:
        return None
    lo, hi = min(w), max(w)
    bezug = max(abs(lo), abs(hi), 1e-12)
    # Die relative Spanne ist IMMER definiert, saettigt aber gegen 100 %: ein
    # Faktor 3 und ein Faktor 143 sehen darin beide nach "fast alles" aus. Der
    # FAKTOR trennt sie und ist bei einer multiplikativ wirkenden Groesse das
    # richtige Mass — er gibt es nur dort, wo nichts null oder negativ wird.
    faktor = (hi / lo) if lo > 1e-12 else None
    return {"min": lo, "max": hi, "spanne": hi - lo,
            "spanne_pct": 100.0 * (hi - lo) / bezug, "faktor": faktor}


def reihe_auswerten(studien, schluessel="Kt"):
    """Mehrere Studien nebeneinander: was bewegt welcher Parameter, und welcher
    zuerst. ``studien`` = Liste von ``run_study``/``laden``-Ergebnissen.

    Returns ``{basis_gleich, marken, zeilen, rangliste, kennzahlen, warnungen}``.
    Rein — keine Datei, kein Netz, kein Loeser.
    """
    try:
        import ema_projekt as _PJ
        marke = _PJ.payload_marke
    except Exception:                                        # noqa: BLE001
        marke = lambda p: ""                                 # noqa: E731
    marken, zeilen, warnungen = {}, [], []
    kennzahlen = []
    for st in studien:
        for m in st.get("metric_meta") or []:
            if m["key"] not in kennzahlen:
                kennzahlen.append(m["key"])
    for st in studien:
        p = st.get("payload")
        mk = marke(p) if isinstance(p, dict) and p else None
        if mk:
            marken.setdefault(mk, []).append(st.get("param"))
        xs = st.get("x") or []
        spannen = {k: _spanne((st.get("metrics") or {}).get(k) or []) for k in kennzahlen}
        flach = [k for k, s in spannen.items()
                 if s is not None and abs(s["spanne_pct"]) < 0.05]
        zeilen.append({
            "param": st.get("param"), "label": st.get("label", st.get("param")),
            "kennung": st.get("kennung"),
            "von": xs[0] if xs else None, "bis": xs[-1] if xs else None,
            "steps": st.get("steps"), "rpm": st.get("rpm"),
            "spannen": spannen, "flach": flach,
            "alles_flach": len(flach) == len([k for k in kennzahlen if spannen.get(k)]),
            "hinweis": (st.get("hinweis") or "").strip(),
            "n_unerreichbar": st.get("n_unerreichbar") or 0,
            "n_feldbilder": len(st.get("field_images") or []),
        })
    basis_gleich = len(marken) <= 1
    if not basis_gleich:
        warnungen.append(
            "Die Studien gehen NICHT vom selben Entwurf aus (%d verschiedene "
            "Payloads: %s). Eine Rangliste ueber ihre Spannweiten waere ein "
            "Vergleich verschiedener Maschinen — sie steht deshalb unter "
            "Vorbehalt." % (len(marken),
                            "; ".join(", ".join(v) for v in marken.values())))
    ohne = [z["param"] for z in zeilen if not z["hinweis"] and z["alles_flach"]]
    if ohne:
        warnungen.append(
            "Ohne Wirkung und ohne Begruendung: %s. Eine flache Kurve, zu der "
            "nichts dasteht, ist ungeklaert — nicht bestaetigt."
            % ", ".join(ohne))
    unerr = [(z["param"], z["n_unerreichbar"]) for z in zeilen if z["n_unerreichbar"]]
    if unerr:
        warnungen.append(
            "Schritte ohne erreichbaren Betriebspunkt: %s. Dort sind Verluste "
            "und Temperaturen leer und NICHT null."
            % ", ".join("%s (%d)" % t for t in unerr))
    rangliste = {}
    for k in kennzahlen:
        mit = [(z["param"], z["label"], z["spannen"][k]["spanne_pct"])
               for z in zeilen if z["spannen"].get(k)]
        rangliste[k] = sorted(mit, key=lambda t: -abs(t[2]))
    return {"basis_gleich": basis_gleich, "marken": sorted(marken),
            "zeilen": zeilen, "rangliste": rangliste,
            "kennzahlen": kennzahlen, "warnungen": warnungen,
            "leit": schluessel}


def reihe_chart(auswertung, schluessel=("Kt", "P_total", "B_gap", "mass_g")):
    """Balken je Parameter: wie weit bewegt er die Kennzahl (in %). Waagerecht
    und nach Wirkung sortiert — eine Rangliste liest man an der Laenge ab, nicht
    an einer Zahlenkolonne."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    rang = auswertung.get("rangliste") or {}
    hat = [k for k in schluessel if rang.get(k)]
    if not hat:
        return ""
    fig, axes = plt.subplots(1, len(hat), figsize=(4.2 * len(hat), 4.4), squeeze=False)
    farben = {"Kt": "#2d7d5a", "P_total": "#b5563a", "B_gap": "#2471a3",
              "mass_g": "#7a5a3a"}
    for ax, k in zip(axes[0], hat):
        eintraege = rang[k][::-1]
        namen = [e[1] for e in eintraege]
        werte = [abs(e[2]) for e in eintraege]
        ax.barh(range(len(werte)), werte, color=farben.get(k, "#555"))
        ax.set_yticks(range(len(namen)))
        ax.set_yticklabels(namen, fontsize=7)
        ax.set_xlabel("Spannweite [%]", fontsize=8)
        ax.set_title(k, fontsize=9)
        ax.grid(axis="x", alpha=0.3)
        # Am Balken steht der FAKTOR, nicht noch einmal der Prozentwert: die
        # Balkenlaenge sagt schon, wie viel des Wertebereichs der Parameter
        # ueberstreicht — was sie NICHT sagt, ist ob das ein Drittel mehr oder
        # das Hundertfache ist.
        fak = {z["param"]: (z["spannen"].get(k) or {}).get("faktor")
               for z in auswertung.get("zeilen") or []}
        for i, (e, v) in enumerate(zip(eintraege, werte)):
            if v <= 0:
                continue
            f = fak.get(e[0])
            ax.text(v, i, ("  ×%.1f" % f) if f and f >= 1.05 else "  %.0f %%" % v,
                    va="center", fontsize=6.5)
    fig.suptitle("Was bewegt welcher Parameter (Spannweite ueber den Studienbereich)",
                 fontsize=10)
    fig.tight_layout()
    return _fig_b64(fig, dpi=120)
