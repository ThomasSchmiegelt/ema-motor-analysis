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
* ``baustein``— ein GERECHNETER Abschnitt (Steckbrief, Getriebe, Elmer,
  Studienreihe, Sicherheit), der beim Rendern aus dem Projekt geholt wird

Der letzte macht diesen Bericht zum **Gesamtbericht ueber die ganze Maschine**:
das Getriebe, das 3-D-Feld und die Parameterstudien rechnen ihre eigenen
Abschnitte, hier stehen sie NEBEN dem selbst geschriebenen Text — und sie werden
beim Rendern frisch geholt, nicht eingefroren. Eine Zahl im Bericht, die von der
Ablage abweicht, waere die schlimmste Sorte Fehler: sie sieht richtig aus.

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
ARTEN = ("text", "bild", "video", "tabelle", "umbruch", "baustein")
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
        elif art == "baustein":
            q = str(b.get("quelle") or "")
            if q not in BAUSTEINE:
                meldungen.append("Block %d: unbekannter Baustein '%s'" % (i + 1, q[:30]))
                continue
            neu["quelle"] = q
            neu["ueberschrift"] = str(b.get("ueberschrift") or BAUSTEINE[q])[:200]
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


def speichern(project_dir, kennung, doc, anlass="gespeichert"):
    d = os.path.join(wurzel(project_dir), _sicher(kennung))
    os.makedirs(d, exist_ok=True)
    bloecke, meldungen = _pruefe(project_dir, doc)
    eltern = (doc or {}).get("eltern")
    if not isinstance(eltern, dict):
        # Die Herkunft ueberlebt ein Speichern, auch wenn die Oberflaeche sie
        # nicht mitschickt — sonst waere der Baum nach der ersten Aenderung flach.
        eltern = ((laden(project_dir, kennung) or {}).get("eltern")
                  if os.path.exists(os.path.join(d, "bericht.json")) else None)
    raus = {"kennung": os.path.basename(d),
            "titel": str((doc or {}).get("titel") or "Bericht")[:200],
            "untertitel": str((doc or {}).get("untertitel") or "")[:300],
            "eltern": eltern if isinstance(eltern, dict) else None,
            "bloecke": bloecke, "geaendert": time.strftime("%Y-%m-%d %H:%M")}
    tmp = os.path.join(d, "bericht.json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(raus, f, ensure_ascii=False, indent=1)
    os.replace(tmp, os.path.join(d, "bericht.json"))
    try:
        raus["fassung"] = fassung_ablegen(project_dir, raus["kennung"], raus, anlass)
    except Exception:                                        # noqa: BLE001
        raus["fassung"] = None
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


def loeschen(project_dir, kennung, *, bestaetigt=True):
    """Einen Bericht entsorgen — ueber den Papierkorb.

    Hier steckt die Arbeit eines Menschen: Text, den er geschrieben, und
    Bilder, die er ausgewaehlt hat, dazu alle Fassungen. Ein
    ``rmtree(ignore_errors=True)`` warf das weg, ohne auch nur zu melden, ob es
    geklappt hat.
    """
    d = os.path.join(wurzel(project_dir), _sicher(kennung))
    if not (os.path.isdir(d) and os.path.exists(os.path.join(d, "bericht.json"))):
        return False
    import ema_ablage
    r = ema_ablage.entsorgen(d, "Bericht verworfen", bestaetigt=bestaetigt,
                             project_dir=project_dir)
    return bool(r.get("ok"))


# ── Bausteine: gerechnete Abschnitte, beim Rendern frisch geholt ────────────
BAUSTEINE = {
    "steckbrief": "Steckbrief — was dieses Projekt ist und was gerechnet wurde",
    "getriebe":   "Getriebeauslegung",
    "elmer":      "3-D-Magnetfeld (Elmer)",
    "studien":    "Parameterstudien (Uebersicht)",
    "sicherheit": "Sicherheitskriterien",
}


def baustein_md(project_dir, quelle):
    """Einen gerechneten Abschnitt als Markdown. Immer FRISCH aus der Ablage —
    eine eingefrorene Zahl im Bericht, die von der Ablage abweicht, ist die
    schlimmste Sorte Fehler: sie sieht richtig aus.

    Was es nicht gibt, sagt das auch. Ein Bericht, in dem ein leerer Abschnitt
    steht, ist besser als einer, in dem er fehlt: das Fehlen ist die Auskunft."""
    try:
        if quelle == "steckbrief":
            import ema_steckbrief
            sb = ema_steckbrief.steckbrief(project_dir, mit_laeufen=False)
            return ema_steckbrief.als_markdown(sb)
        if quelle == "getriebe":
            import ema_steckbrief
            g = ema_steckbrief.getriebe(project_dir)
            if not g:
                return "_Fuer dieses Projekt ist keine Getriebeauslegung abgelegt._"
            return _getriebe_md(g)
        if quelle == "elmer":
            return _elmer_md(project_dir)
        if quelle == "studien":
            return _studien_md(project_dir)
        if quelle == "sicherheit":
            return _sicherheit_md(project_dir)
    except Exception as e:                                   # noqa: BLE001
        return "_Der Abschnitt konnte nicht geholt werden: %s_" % e
    return "_Unbekannter Baustein: %s_" % quelle


def _tab(zeilen, kopf=("Groesse", "Wert")):
    aus = ["| " + " | ".join(kopf) + " |", "|" + "---|" * len(kopf)]
    for z in zeilen:
        aus.append("| " + " | ".join("—" if v is None else str(v) for v in z) + " |")
    return "\n".join(aus)


def _getriebe_md(g):
    e = g.get("ergebnis") if isinstance(g.get("ergebnis"), dict) else g
    zeilen = []
    for name, schl, eh in (("Bauart", "art", ""), ("Einbauort", "einbau", ""),
                           ("Uebersetzung (soll)", "i_soll", ""),
                           ("Uebersetzung (ist)", "i_ist", ""),
                           ("Stufen", "stufen", ""),
                           ("Wirkungsgrad", "eta", ""),
                           ("Masse", "masse_kg", "kg"),
                           ("Traegheit (auf die Motorwelle)", "J_red_kgm2", "kg m^2")):
        v = e.get(schl)
        if v is not None:
            zeilen.append((name, ("%s %s" % (v, eh)).strip()))
    for i, st in enumerate(e.get("stufen_detail") or e.get("stufen_liste") or [], 1):
        if not isinstance(st, dict):
            continue
        zeilen.append(("Stufe %d" % i,
                       "z %s/%s, m %s mm, b %s mm, a %s mm, S_F %s, S_H %s"
                       % (st.get("z1"), st.get("z2"), st.get("m"), st.get("b"),
                          st.get("a"), st.get("S_F"), st.get("S_H"))))
    txt = _tab(zeilen) if zeilen else "_Die Getriebeablage enthaelt keine auswertbaren Felder._"
    hin = e.get("hinweis") or e.get("vorbehalt")
    if hin:
        txt += "\n\n> " + str(hin)
    return txt


def _elmer_md(project_dir):
    rj = os.path.join(project_dir, "results.json")
    if not os.path.exists(rj):
        return "_Kein `results.json` — es lief noch keine Rechnung in diesem Projekt._"
    try:
        with open(rj, encoding="utf-8") as f:
            e3 = (json.load(f) or {}).get("em3d")
    except (OSError, ValueError):
        e3 = None
    if not e3:
        return "_Fuer dieses Projekt ist kein 3-D-Lauf (Elmer) abgelegt._"
    import ema_report
    teile = [ema_report._em3d_md_netz(e3), "", ema_report._em3d_md_ergebnis(e3)]
    sif = os.path.join(project_dir, "em3d", "case.sif")
    if os.path.exists(sif):
        try:
            with open(sif, encoding="utf-8", errors="replace") as f:
                teile = [ema_report._em3d_md_loeser(ema_report.sif_loeser(f.read())), ""] + teile
        except OSError:
            pass
    warn = [str(w) for w in (e3.get("warnings") or [])]
    if warn:
        teile += ["", "**Warnungen des Laufs:**", ""] + ["- " + w for w in warn]
    return "\n".join(teile)


def _studien_md(project_dir):
    import ema_paramstudy
    w = ema_paramstudy.studien_wurzel(project_dir)
    eintraege = ema_paramstudy.liste(w)
    if not eintraege:
        return "_In diesem Projekt ist keine Parameterstudie abgelegt._"
    studien = [ema_paramstudy.laden(w, e["kennung"]) for e in eintraege]
    studien = [x for x in studien if x]
    ausw = ema_paramstudy.reihe_auswerten(studien)
    import ema_report
    teile = [ema_report._reihe_md_rangliste(ausw)]
    if ausw.get("warnungen"):
        teile += ["", "**Vorbehalte:**", ""] + ["- " + x for x in ausw["warnungen"]]
    return "\n".join(teile)


def _sicherheit_md(project_dir):
    rj = os.path.join(project_dir, "results.json")
    mj = os.path.join(project_dir, "meta.json")
    if not os.path.exists(rj):
        return "_Kein `results.json` — es lief noch keine Rechnung in diesem Projekt._"
    try:
        import ema_sicherheit
        with open(rj, encoding="utf-8") as f:
            res = json.load(f) or {}
        meta = {}
        if os.path.exists(mj):
            with open(mj, encoding="utf-8") as f:
                meta = json.load(f) or {}
        erg = ema_sicherheit.pruefen(res, meta)
    except Exception as e:                                   # noqa: BLE001
        return "_Die Sicherheitspruefung lief nicht: %s_" % e
    zeilen = [(k.get("name"), ("bestanden" if k.get("ok") else "VERLETZT"),
               (k.get("text") or "")[:160]) for k in (erg.get("kriterien") or [])]
    if not zeilen:
        return "_Keine Kriterien auswertbar._"
    return _tab(zeilen, kopf=("Kriterium", "Befund", "Bemerkung"))


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
        elif art == "baustein":
            teile += ["## " + (b.get("ueberschrift") or BAUSTEINE.get(b["quelle"], "")), "",
                      baustein_md(project_dir, b["quelle"]), ""]
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
        elif art == "baustein":
            teile.append("<h2>%s</h2>" % _h.escape(
                b.get("ueberschrift") or BAUSTEINE.get(b["quelle"], "")))
            teile.append(_md_zu_html(baustein_md(project_dir, b["quelle"])))
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


# ─────────────────────────────────────────────────────────────────────────────
# Fassungen und Abzweige — zurueck zu einer Aenderung, weiter als Variante
# ─────────────────────────────────────────────────────────────────────────────
# Gewuenscht als „eine Art Baumstruktur, dass ich zu Aenderungen und Varianten
# zurueckgehen kann". Zwei verschiedene Dinge, und sie brauchen zwei Mechanismen:
#
#   * **Fassung** — derselbe Bericht zu einem frueheren Zeitpunkt. Jedes
#     Speichern legt eine ab; `zurueck` holt sie zurueck.
#   * **Abzweig** — ein NEUER Bericht, der von einer Fassung ausgeht. Er traegt
#     seine Herkunft (`eltern`), und daraus wird der Baum.
#
# **Die Geschichte wird nicht umgeschrieben.** `zurueck` sichert vorher den
# verlassenen Stand als eigene Fassung und haengt die Rueckkehr als neue an —
# dieselbe Haltung wie `ema_projekt.zurueck`: dass ein Zweig probiert wurde und
# sich nicht bewaehrt hat, ist selbst eine Auskunft.

FASSUNGEN = "fassungen"
MAX_FASSUNGEN = 60


def _fassungen_dir(project_dir, kennung):
    return os.path.join(wurzel(project_dir), _sicher(kennung), FASSUNGEN)


def _inhalt_marke(doc):
    """Fingerabdruck ueber das, was den Bericht ausmacht — Titel und Bloecke.
    Ohne ihn legte jedes Speichern eine Fassung an, auch wenn sich nichts
    geaendert hat, und die Liste waere binnen eines Nachmittags unlesbar."""
    import hashlib
    kern = {"titel": doc.get("titel"), "untertitel": doc.get("untertitel"),
            "bloecke": doc.get("bloecke") or []}
    roh = json.dumps(kern, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha1(roh.encode("utf-8")).hexdigest()[:12]


def fassung_ablegen(project_dir, kennung, doc, anlass="gespeichert"):
    """Den aktuellen Stand als Fassung sichern. Gibt die Marke zurueck — oder
    None, wenn sich gegenueber der letzten Fassung nichts geaendert hat."""
    d = _fassungen_dir(project_dir, kennung)
    os.makedirs(d, exist_ok=True)
    marke_inhalt = _inhalt_marke(doc)
    vorhanden = fassungen(project_dir, kennung)
    if vorhanden and vorhanden[0].get("inhalt") == marke_inhalt:
        return None
    basis = time.strftime("%Y%m%d_%H%M%S")
    marke, n = basis, 1
    while os.path.exists(os.path.join(d, marke + ".json")):
        n += 1
        marke = "%s-%d" % (basis, n)
    satz = dict(doc)
    satz.update({"marke": marke, "inhalt": marke_inhalt, "anlass": anlass,
                 "zeit": time.strftime("%Y-%m-%d %H:%M:%S")})
    with open(os.path.join(d, marke + ".json"), "w", encoding="utf-8") as f:
        json.dump(satz, f, ensure_ascii=False)
    # Ueberzaehlige Fassungen kappen. Eine Fassung ist ein Stand, den jemand
    # geschrieben hat — sie wandert deshalb in den Papierkorb und wird nicht
    # weggeworfen. (Der Deckel selbst bleibt: sonst waechst der Ordner mit
    # jedem Speichern, und die Fassungsliste wird unlesbar.)
    alt = sorted((f for f in os.listdir(d) if f.endswith(".json")),
                 key=lambda f: _marke_key(f[:-5]))
    ueberzaehlig = alt[:-MAX_FASSUNGEN] if MAX_FASSUNGEN > 0 else []
    if ueberzaehlig:
        try:
            import ema_ablage
            for f in ueberzaehlig:
                ema_ablage.entsorgen(
                    os.path.join(d, f),
                    f"aelteste Fassung, ueber {MAX_FASSUNGEN} hinaus",
                    bestaetigt=True, project_dir=project_dir)
        except Exception:                                    # noqa: BLE001
            pass
    return marke


def _marke_key(marke):
    """Sortierschluessel einer Marke: (Zeitstempel, laufende Nummer).

    NICHT die Zeichenkette. Zwei Fassungen derselben Sekunde heissen
    ``…165038`` und ``…165038-2``; im Dateinamen sortiert der Bindestrich (0x2D)
    UNTER den Punkt (0x2E), also stuende ``…165038.json`` vor ``…165038-2.json``
    und die aeltere gaelte als die juengere. Genau dieser Fehler steht schon in
    `ema_getriebe.rechnungen()` — hier waere er beim Doppel-Speichern
    aufgefallen: die Dubletten-Erkennung verglich gegen den falschen Stand."""
    m = str(marke or "")
    basis, _, rest = m.partition("-")
    try:
        n = int(rest) if rest else 1
    except ValueError:
        n = 1
    return (basis, n)


def fassungen(project_dir, kennung):
    """Alle Fassungen eines Berichts, neueste zuerst — ohne die Bloecke zu
    laden (die Uebersicht steht in der Oberflaeche, nicht im Speicher)."""
    d = _fassungen_dir(project_dir, kennung)
    if not os.path.isdir(d):
        return []
    out = []
    dateien = sorted((f for f in os.listdir(d) if f.endswith(".json")),
                     key=lambda f: _marke_key(f[:-5]), reverse=True)
    for f in dateien:
        try:
            with open(os.path.join(d, f), encoding="utf-8") as fh:
                s = json.load(fh) or {}
        except (OSError, ValueError):
            continue
        out.append({"marke": s.get("marke", f[:-5]), "zeit": s.get("zeit", ""),
                    "anlass": s.get("anlass", ""), "inhalt": s.get("inhalt", ""),
                    "titel": s.get("titel", ""),
                    "n_bloecke": len(s.get("bloecke") or [])})
    return out


def fassung_holen(project_dir, kennung, marke):
    p = os.path.join(_fassungen_dir(project_dir, kennung), _sicher(marke) + ".json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def zurueck(project_dir, kennung, marke):
    """Zu einer Fassung zurueck. Der VERLASSENE Stand wird vorher gesichert —
    sonst waere der Rueckweg der einzige Schritt, den man nicht rueckgaengig
    machen kann."""
    alt = fassung_holen(project_dir, kennung, marke)
    if not alt:
        return {"ok": False, "grund": "Fassung '%s' gibt es nicht" % marke}
    jetzt = laden(project_dir, kennung)
    if jetzt:
        fassung_ablegen(project_dir, kennung, jetzt, anlass="vor der Rueckkehr")
    doc = {"titel": alt.get("titel"), "untertitel": alt.get("untertitel"),
           "bloecke": alt.get("bloecke") or [], "eltern": (jetzt or {}).get("eltern")}
    r = speichern(project_dir, kennung, doc, anlass="zurueck auf %s" % marke)
    return {"ok": True, "marke": marke, "bericht": r}


def abzweigen(project_dir, kennung, marke=None, titel=""):
    """Von einem Bericht (oder einer seiner Fassungen) eine **Variante** —
    ein neuer Bericht, der seine Herkunft mitfuehrt. Daraus entsteht der Baum."""
    quelle = (fassung_holen(project_dir, kennung, marke) if marke
              else laden(project_dir, kennung))
    if not quelle:
        return {"ok": False, "grund": "Vorlage nicht gefunden"}
    neu = anlegen(project_dir, titel or ((quelle.get("titel") or "Bericht") + " Variante"))
    speichern(project_dir, neu, {
        "titel": titel or ((quelle.get("titel") or "Bericht") + " (Variante)"),
        "untertitel": quelle.get("untertitel", ""),
        "bloecke": quelle.get("bloecke") or [],
        "eltern": {"kennung": kennung, "marke": marke or ""}},
        anlass="abgezweigt von %s%s" % (kennung, ("@" + marke) if marke else ""))
    return {"ok": True, "kennung": neu}


def baum(project_dir):
    """Die Berichte als Baum: Wurzeln sind die ohne Eltern, Kinder haengen
    darunter. Flach zurueckgegeben (mit ``tiefe``), weil die Oberflaeche eine
    Liste zeichnet und keine Rekursion braucht."""
    alle = {e["kennung"]: e for e in liste(project_dir)}
    for k, e in alle.items():
        doc = laden(project_dir, k) or {}
        e["eltern"] = (doc.get("eltern") or {}).get("kennung") or None
        e["eltern_marke"] = (doc.get("eltern") or {}).get("marke") or ""
        e["n_fassungen"] = len(fassungen(project_dir, k))
    kinder = {}
    for k, e in alle.items():
        kinder.setdefault(e["eltern"] if e["eltern"] in alle else None, []).append(k)
    aus = []

    def _rein(k, tiefe):
        e = dict(alle[k]); e["tiefe"] = tiefe
        aus.append(e)
        for kind in sorted(kinder.get(k, [])):
            _rein(kind, tiefe + 1)

    for k in sorted(kinder.get(None, []), reverse=True):
        _rein(k, 0)
    return aus


# ─────────────────────────────────────────────────────────────────────────────
# Alle Berichte EINES Projekts — auch die, die woanders entstanden sind
# ─────────────────────────────────────────────────────────────────────────────
# Gewuenscht als „ich moechte die Berichte auch im Projektordner haben". Sie
# LIEGEN dort, jeder einzelne — nur an fuenf verschiedenen Stellen, weil jede
# Stufe ihren Bericht dort ablegt, wo ihre Zahlen liegen: der Studienbericht
# beim Studienordner, der Reihenbericht eine Ebene darueber, der Elmer-Bericht
# und der Projektbericht in der Projektwurzel. Das ist richtig so — ein Bericht
# neben seinen Zahlen ist zuzuordnen, ein Bericht in einem Sammelordner nicht.
# Was fehlte, ist die EINE Liste, die sie alle nennt.

_BERICHT_ORTE = (
    ("bericht.pdf",           "Projektbericht (LLM)"),
    ("bericht_agentisch.pdf", "Projektbericht (6 Experten)"),
    ("bericht_elmer.pdf",     "Elmer-Auswertung (3-D-Feld)"),
    ("studienreihe.pdf",      "Parameterstudien — Reihenauswertung"),
    ("parameterstudie.pdf",   "Parameterstudie"),
)


def alle_berichte(project_dir):
    """Jedes PDF/HTML dieses Projekts, egal welche Stufe es erzeugt hat —
    mit projektrelativem Pfad, Groesse und Zeit. Neueste zuerst."""
    aus = []

    def _nimm(rel, art, woher=""):
        p = os.path.join(project_dir, rel)
        if not os.path.exists(p):
            return
        try:
            gr, ts = os.path.getsize(p), os.path.getmtime(p)
        except OSError:
            return
        aus.append({"pfad": rel.replace(os.sep, "/"), "art": art, "woher": woher,
                    "bytes": gr, "mb": round(gr / 1e6, 2),
                    "zeit": time.strftime("%Y-%m-%d %H:%M", time.localtime(ts)),
                    "_ts": ts})

    for datei, art in _BERICHT_ORTE:
        _nimm(datei, art, "Projektwurzel")
    st = os.path.join(project_dir, "parameterstudien")
    if os.path.isdir(st):
        for k in sorted(os.listdir(st)):
            _nimm(os.path.join("parameterstudien", k, "parameterstudie.pdf"),
                  "Parameterstudie", k)
    for k in sorted((os.listdir(wurzel(project_dir))
                     if os.path.isdir(wurzel(project_dir)) else [])):
        doc = laden(project_dir, k)
        titel = (doc or {}).get("titel") or k
        for was, art in (("pdf", "eigener Bericht (PDF)"),
                         ("html", "eigener Bericht (HTML, mit Video)")):
            _nimm(os.path.join(ORDNER, k, "bericht." + was), art, titel)
    aus.sort(key=lambda e: -e["_ts"])
    for e in aus:
        e.pop("_ts", None)
    return aus
