"""**Berichtsreiter** — ein Bericht, den der Mensch selbst schreibt.

Alle uebrigen Berichte hier sind erzeugt: die Kette baut das Geruest, das Modell
schreibt die Prosa, die Bilder kommen aus den Erzeugern. Das ist richtig fuer
einen Lauf, aber es gibt nichts, worin man **selbst** etwas festhaelt — eine
Einordnung, eine Entscheidung, ein Vergleich zweier Laeufe, ein Video aus dem
Spritzoelpfad neben einem Feldbild.

Ein Bericht ist hier eine Liste **Bloecke** in der Reihenfolge, in der sie
stehen sollen:

* ``text``   — Markdown, wie der Mensch ihn tippt (Ueberschriften, Listen, Formeln)
* ``bild``   — eine Datei AUS DEM PROJEKT (Diagramm, CAD-Bild, festgehaltene Ansicht)
* ``video``  — eine MP4 aus dem Projekt
* ``tabelle``— eine Markdown-Tabelle von Hand
* ``umbruch``— Seitenumbruch

**Verwiesen, nicht kopiert.** Ein Block nennt den projektrelativen Pfad; die
Datei bleibt, wo sie entstanden ist. Ein Bericht, der Bilder kopiert, zeigt beim
naechsten Lauf den alten Stand, ohne dass jemand es merkt — dasselbe Argument,
aus dem `ema_agent.sichern` Bilder verweist statt sie mitzunehmen.

**Video im PDF gibt es nicht**, und das wird nicht verschwiegen: ein PDF kann
kein Video abspielen. Ein Videoblock wird deshalb ZWEIMAL ausgegeben — im PDF
als Standbild (mit ffmpeg gezogen) samt Dateiname, in einer **HTML-Fassung**
daneben als echtes ``<video>``. Beide entstehen aus derselben Blockliste; die
HTML-Fassung ist kein zweiter Bericht, sondern dieselbe mit funktionierendem
Video.
"""

import json
import os
import re
import subprocess
import time

ORDNER = "berichte"
ARTEN = ("text", "bild", "video", "tabelle", "umbruch")
MAX_BLOECKE = 200
MAX_TEXT = 40000


def wurzel(project_dir):
    return os.path.join(project_dir, ORDNER)


def _sicher(name, ersatz="bericht"):
    s = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in str(name or ""))
    return s.strip().replace(" ", "_").strip("._")[:48] or ersatz


def _rel_ok(project_dir, rel):
    """Ein Blockpfad zeigt IMMER ins Projekt. Geprueft wird am aufgeloesten
    Pfad, nicht an der Zeichenkette — `..` laesst sich sonst verstecken."""
    if not rel or os.path.isabs(str(rel)):
        return None
    p = os.path.realpath(os.path.join(project_dir, str(rel)))
    if not p.startswith(os.path.realpath(project_dir) + os.sep):
        return None
    return p if os.path.exists(p) else None


# ── Bestand: was sich einfuegen laesst ───────────────────────────────────────
_BILD_ORTE = (("charts", "Diagramme und Feldbilder"),
              ("cad_images", "CAD-Ansichten"),
              ("ansichten", "festgehaltene Ansichten (3-D-Betrachter)"))
_VIDEO_ORTE = (("frames", "Feldanimation (Rotation)"),
               ("frames_react", "Feldanimation (Ankerrueckwirkung)"),
               ("frames_load", "Feldanimation (Last-Rampe)"),
               ("frames_struct", "Verformung"),
               ("frames_em3d", "3-D-Lastprofil"),
               ("frames_oil", "Spritzoel (Mantaflow)"),
               ("frames_cfd", "Spritzoel (OpenFOAM)"),
               ("frames_fx3d", "Spritzoel (FluidX3D)"))


def bestand(project_dir):
    """Was in diesem Projekt zum Einfuegen bereitliegt — Bilder und Videos, je
    mit projektrelativem Pfad. Die Parameterstudien kommen mit, weil ihre
    Diagramme in eigenen Ordnern liegen und sonst unauffindbar waeren."""
    bilder, videos = [], []
    for ordner, gruppe in _BILD_ORTE:
        d = os.path.join(project_dir, ordner)
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            if f.lower().endswith((".png", ".jpg", ".jpeg")):
                bilder.append({"pfad": "%s/%s" % (ordner, f), "name": f,
                               "gruppe": gruppe})
    st_wurzel = os.path.join(project_dir, "parameterstudien")
    if os.path.isdir(st_wurzel):
        for k in sorted(os.listdir(st_wurzel), reverse=True):
            d = os.path.join(st_wurzel, k)
            if not os.path.isdir(d):
                continue
            for f in sorted(os.listdir(d)):
                if f.endswith(".png") and not f.startswith("frame_"):
                    bilder.append({"pfad": "parameterstudien/%s/%s" % (k, f),
                                   "name": "%s · %s" % (k, f),
                                   "gruppe": "Parameterstudien"})
            if os.path.exists(os.path.join(d, "anim.mp4")):
                videos.append({"pfad": "parameterstudien/%s/anim.mp4" % k,
                               "name": "%s · anim.mp4" % k,
                               "gruppe": "Parameterstudien"})
    for ordner, gruppe in _VIDEO_ORTE:
        p = os.path.join(project_dir, ordner, "anim.mp4")
        if os.path.exists(p):
            videos.append({"pfad": "%s/anim.mp4" % ordner, "name": gruppe,
                           "gruppe": "Laeufe"})
    for ordner in ("oilspray_runs", "fluidx3d_runs", "em3d_runs"):
        d = os.path.join(project_dir, ordner)
        if not os.path.isdir(d):
            continue
        for k in sorted(os.listdir(d), reverse=True):
            p = os.path.join(d, k, "anim.mp4")
            if os.path.exists(p):
                videos.append({"pfad": "%s/%s/anim.mp4" % (ordner, k),
                               "name": "%s · %s" % (ordner, k),
                               "gruppe": "gespeicherte Varianten"})
    return {"bilder": bilder, "videos": videos}


# ── Ablage ───────────────────────────────────────────────────────────────────
def anlegen(project_dir, titel=""):
    d = wurzel(project_dir)
    os.makedirs(d, exist_ok=True)
    basis = "%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), _sicher(titel))
    kennung, n = basis, 1
    while os.path.exists(os.path.join(d, kennung)):
        n += 1
        kennung = "%s-%d" % (basis, n)
    pfad = os.path.join(d, kennung)
    os.makedirs(pfad, exist_ok=True)
    speichern(project_dir, kennung, {"titel": titel or "Bericht", "bloecke": []})
    return kennung


def _pruefe(project_dir, doc):
    """Bringt ein Dokument in Form und meldet, was daran nicht geht. Rein."""
    bloecke, meldungen = [], []
    for i, b in enumerate((doc or {}).get("bloecke") or []):
        if len(bloecke) >= MAX_BLOECKE:
            meldungen.append("mehr als %d Bloecke — der Rest wurde verworfen" % MAX_BLOECKE)
            break
        art = str((b or {}).get("art") or "text")
        if art not in ARTEN:
            meldungen.append("Block %d: unbekannte Art '%s'" % (i + 1, art))
            continue
        neu = {"art": art}
        if art in ("text", "tabelle"):
            neu["text"] = str(b.get("text") or "")[:MAX_TEXT]
        elif art in ("bild", "video"):
            rel = str(b.get("pfad") or "")
            if not _rel_ok(project_dir, rel):
                meldungen.append("Block %d: '%s' liegt nicht im Projekt oder fehlt"
                                 % (i + 1, rel[:60]))
                continue
            neu["pfad"] = rel
            neu["beschriftung"] = str(b.get("beschriftung") or "")[:300]
            if art == "bild":
                try:
                    neu["breite"] = max(20, min(100, int(b.get("breite", 100))))
                except (TypeError, ValueError):
                    neu["breite"] = 100
        bloecke.append(neu)
    return bloecke, meldungen


def speichern(project_dir, kennung, doc):
    d = os.path.join(wurzel(project_dir), _sicher(kennung))
    os.makedirs(d, exist_ok=True)
    bloecke, meldungen = _pruefe(project_dir, doc)
    raus = {"kennung": os.path.basename(d),
            "titel": str((doc or {}).get("titel") or "Bericht")[:200],
            "untertitel": str((doc or {}).get("untertitel") or "")[:300],
            "bloecke": bloecke, "geaendert": time.strftime("%Y-%m-%d %H:%M")}
    tmp = os.path.join(d, "bericht.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(raus, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "bericht.json"))
    raus["meldungen"] = meldungen
    return raus


def laden(project_dir, kennung):
    p = os.path.join(wurzel(project_dir), _sicher(kennung), "bericht.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def liste(project_dir):
    d = wurzel(project_dir)
    if not os.path.isdir(d):
        return []
    out = []
    for k in sorted(os.listdir(d), reverse=True):
        doc = laden(project_dir, k)
        if not doc:
            continue
        arten = {}
        for b in doc.get("bloecke") or []:
            arten[b["art"]] = arten.get(b["art"], 0) + 1
        out.append({"kennung": k, "titel": doc.get("titel", k),
                    "geaendert": doc.get("geaendert", ""),
                    "n_bloecke": len(doc.get("bloecke") or []), "arten": arten,
                    "pdf": os.path.exists(os.path.join(d, k, "bericht.pdf")),
                    "html": os.path.exists(os.path.join(d, k, "bericht.html"))})
    return out


def loeschen(project_dir, kennung):
    import shutil
    d = os.path.join(wurzel(project_dir), _sicher(kennung))
    if os.path.isdir(d) and os.path.exists(os.path.join(d, "bericht.json")):
        shutil.rmtree(d, ignore_errors=True)
        return True
    return False


# ── Standbild aus einem Video (fuer das PDF) ─────────────────────────────────
def standbild(video_pfad, ziel_png, sekunde=None):
    """Ein Einzelbild aus dem Video ziehen. ``sekunde=None`` nimmt die MITTE —
    der erste Frame eines Simulationsvideos ist meistens der Zustand VOR dem
    Ereignis (ein leeres Fenster, ein noch nicht geflogener Strahl) und damit
    das am wenigsten aussagekraeftige Bild des ganzen Films."""
    if not os.path.exists(video_pfad):
        return None
    ss = sekunde
    if ss is None:
        try:
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", video_pfad],
                capture_output=True, text=True, timeout=30)
            ss = max(0.0, float((r.stdout or "0").strip()) / 2.0)
        except (OSError, ValueError, subprocess.SubprocessError):
            ss = 0.0
    os.makedirs(os.path.dirname(ziel_png) or ".", exist_ok=True)
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", "%.3f" % ss,
                        "-i", video_pfad, "-frames:v", "1", ziel_png],
                       capture_output=True, timeout=120)
    except (OSError, subprocess.SubprocessError):
        return None
    return ziel_png if os.path.exists(ziel_png) else None


# ── Ausgabe ──────────────────────────────────────────────────────────────────
def als_markdown(project_dir, doc, standbilder=True):
    """Die Blockliste als Markdown fuer pandoc. Videos werden zu Standbildern;
    der Dateiname steht darunter, damit der Leser weiss, dass es bewegt gibt."""
    teile = ["# " + str(doc.get("titel") or "Bericht"), ""]
    if doc.get("untertitel"):
        teile += ["*%s*" % doc["untertitel"], ""]
    d = os.path.join(wurzel(project_dir), _sicher(doc.get("kennung", "x")))
    for i, b in enumerate(doc.get("bloecke") or []):
        art = b.get("art")
        if art in ("text", "tabelle"):
            teile += [b.get("text") or "", ""]
        elif art == "bild":
            cap = b.get("beschriftung") or ""
            teile += ["![%s](%s)" % (cap.replace("]", ")"), b["pfad"]), ""]
        elif art == "video":
            cap = b.get("beschriftung") or os.path.basename(b["pfad"])
            png = None
            if standbilder:
                png = standbild(os.path.join(project_dir, b["pfad"]),
                                os.path.join(d, "standbild_%02d.png" % i))
            if png:
                rel = os.path.relpath(png, project_dir)
                teile += ["![%s (Standbild aus dem Video)](%s)"
                          % (cap.replace("]", ")"), rel), ""]
            teile += ["_Video: `%s` — ein PDF kann es nicht abspielen; in der "
                      "HTML-Fassung dieses Berichts laeuft es._" % b["pfad"], ""]
        elif art == "umbruch":
            teile += ["\\newpage", ""]
    return "\n".join(teile)


# `base href` zeigt auf das PROJEKT: die Blockpfade sind projektrelativ
# (`charts/…`, `parameterstudien/…/anim.mp4`), die HTML-Datei liegt aber zwei
# Ebenen tiefer in `berichte/<kennung>/`. Ohne diese Zeile zeigen alle Bilder
# und Videos ins Leere, sobald man die Datei direkt oeffnet — und genau das tut
# man mit ihr, sie ist ja die Fassung MIT laufendem Video.
_HTML_KOPF = """<!doctype html><meta charset="utf-8"><base href="../../"><title>%(titel)s</title>
<style>
 body{background:#12151a;color:#dde;font:15px/1.6 system-ui,sans-serif;
      max-width:52rem;margin:0 auto;padding:2rem 1.2rem}
 h1,h2,h3{color:#fff;line-height:1.25} h1{border-bottom:1px solid #2a3340;padding-bottom:.3rem}
 img,video{max-width:100%%;border-radius:6px;display:block;margin:1rem 0}
 figcaption{color:#9aa;font-size:.82rem;margin:-.6rem 0 1.2rem}
 table{border-collapse:collapse;width:100%%;font-size:.88rem;margin:1rem 0}
 th,td{border:1px solid #2a3340;padding:.35rem .6rem;text-align:left}
 code{background:#1b2028;padding:.1rem .3rem;border-radius:3px}
 hr{border:0;border-top:1px solid #2a3340;margin:2rem 0}
 .quelle{color:#789;font-size:.78rem}
</style>
<h1>%(titel)s</h1>
"""


def als_html(project_dir, doc):
    """Dieselbe Blockliste als HTML — hier laeuft das Video wirklich. Der
    Markdown-Text wird ueber pandoc gesetzt, wenn es da ist; sonst steht er als
    Absatz da (lieber unformatiert als gar nicht)."""
    import html as _h
    teile = [_HTML_KOPF % {"titel": _h.escape(str(doc.get("titel") or "Bericht"))}]
    if doc.get("untertitel"):
        teile.append("<p class='quelle'>%s</p>" % _h.escape(doc["untertitel"]))
    for b in doc.get("bloecke") or []:
        art = b.get("art")
        if art in ("text", "tabelle"):
            teile.append(_md_zu_html(b.get("text") or ""))
        elif art == "bild":
            br = b.get("breite", 100)
            teile.append("<figure><img src='%s' style='width:%d%%'>%s</figure>" % (
                _h.escape(b["pfad"]), br,
                ("<figcaption>%s</figcaption>" % _h.escape(b.get("beschriftung") or ""))
                if b.get("beschriftung") else ""))
        elif art == "video":
            teile.append("<figure><video src='%s' controls loop muted playsinline></video>%s</figure>"
                         % (_h.escape(b["pfad"]),
                            ("<figcaption>%s</figcaption>" % _h.escape(b.get("beschriftung") or ""))
                            if b.get("beschriftung") else ""))
        elif art == "umbruch":
            teile.append("<hr>")
    return "\n".join(teile)


def _md_zu_html(text):
    """Markdown → HTML ueber pandoc; ohne pandoc der Text als Absaetze."""
    import html as _h
    if not text.strip():
        return ""
    try:
        r = subprocess.run(["pandoc", "-f", "markdown", "-t", "html"],
                           input=text, capture_output=True, text=True, timeout=60)
        if r.returncode == 0 and (r.stdout or "").strip():
            return r.stdout
    except (OSError, subprocess.SubprocessError):
        pass
    return "".join("<p>%s</p>" % _h.escape(a.strip()).replace("\n", "<br>")
                   for a in re.split(r"\n\s*\n", text) if a.strip())


def rendern(project_dir, kennung, progress_cb=None):
    """PDF und HTML aus der Blockliste. Returns ``{pdf, html, md}``."""
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    doc = laden(project_dir, kennung)
    if not doc:
        raise ValueError("Bericht '%s' gibt es nicht" % kennung)
    d = os.path.join(wurzel(project_dir), _sicher(kennung))
    n_video = sum(1 for b in doc.get("bloecke") or [] if b.get("art") == "video")
    _log("Setze %d Bloecke%s…" % (len(doc.get("bloecke") or []),
                                  (", %d Standbilder aus Videos" % n_video) if n_video else ""), 15)
    md = als_markdown(project_dir, doc)
    md_p = os.path.join(d, "bericht.md")
    with open(md_p, "w", encoding="utf-8") as f:
        f.write(md)
    _log("Schreibe HTML (mit laufenden Videos)…", 45)
    html_p = os.path.join(d, "bericht.html")
    with open(html_p, "w", encoding="utf-8") as f:
        f.write(als_html(project_dir, doc))
    _log("Rendere PDF (pandoc + xelatex)…", 60)
    import ema_report
    # Die Bildpfade im Markdown sind PROJEKTrelativ, pandoc muss also vom
    # Projekt aus arbeiten — das PDF landet trotzdem beim Bericht.
    pdf_tmp = ema_report.render_pdf(md, project_dir, out_filename="_bericht_tmp.pdf",
                                    md_filename="_bericht_tmp.md")
    pdf_p = os.path.join(d, "bericht.pdf")
    if pdf_tmp and os.path.exists(pdf_tmp):
        os.replace(pdf_tmp, pdf_p)
    for rest in ("_bericht_tmp.md",):
        try:
            os.remove(os.path.join(project_dir, rest))
        except OSError:
            pass
    _log("✓ fertig.", 100)
    return {"pdf": pdf_p if os.path.exists(pdf_p) else None,
            "html": html_p, "md": md_p}
