"""**Festgehaltene Ansichten** — Bildschirmbilder aus den Browser-Betrachtern.

Der 3-D-Betrachter (`🧲 3D-Feld` → „🧊 Im Browser ansehen") zeichnet mit vtk.js
in ein WebGL-Bild. Was man dort einstellt — Blickrichtung, Schnittebene,
Farbskala, Feldlinien, Lastfall — ist oft **genau die Ansicht, die in den
Bericht gehoert**, und sie existierte bisher nur auf dem Schirm: die
Berichtsbilder kommen aus matplotlib und aus `render_field_3d`, nicht aus dem
Betrachter. Wer die gedrehte, aufgeschnittene Ansicht zeigen wollte, machte ein
Bildschirmfoto und legte es von Hand irgendwohin.

Dieses Modul ist die Ablage dafuer: `<projekt>/ansichten/<zeit>_<name>.png`,
daneben eine `.json` mit Beschriftung und den Einstellungen, unter denen das
Bild entstanden ist (Farbskala, Schnitt, Lastfall). **Die Einstellungen gehoeren
dazu** — ein |B|-Bild ohne seine Skala ist kein Messwert, sondern ein Muster,
und im Bericht steht es sonst ohne Massstab neben gerechneten Zahlen.

Bewusst getrennt von `charts/`: dort liegt, was das Werkzeug erzeugt hat und bei
einem neuen Lauf ueberschreibt. Eine festgehaltene Ansicht ist eine Entscheidung
des Menschen und wird von keinem Lauf angefasst.
"""

import base64
import json
import os
import re
import time

ORDNER = "ansichten"
MAX_BYTES = 12 * 1024 * 1024          # ein Bildschirmbild, nicht ein Datensatz
_ERLAUBT = re.compile(r"^[A-Za-z0-9_.-]{1,80}$")


def wurzel(project_dir):
    return os.path.join(project_dir, ORDNER)


def _sicher(name, ersatz="ansicht"):
    """Nur das, was als Dateiname sicher ist — kein Pfad, kein Punkt am Anfang."""
    s = "".join(c if (c.isalnum() or c in "._- ") else "_" for c in str(name or ""))
    s = s.strip().replace(" ", "_").strip("._")[:48]
    return s or ersatz


def _b64_von(png):
    """Nimmt entweder eine reine base64-Zeichenkette oder eine ``data:``-URL,
    wie sie `canvas.toDataURL()` und vtk.js' `captureNextImage()` liefern."""
    s = str(png or "")
    if s.startswith("data:"):
        if "," not in s:
            raise ValueError("unvollstaendige data-URL")
        kopf, _, s = s.partition(",")
        if "image/png" not in kopf:
            raise ValueError("nur PNG wird angenommen (%s)" % kopf[:40])
    return base64.b64decode(s, validate=True)


def sichern(project_dir, png, name="", beschriftung="", einstellungen=None):
    """Eine Ansicht ablegen. ``png`` = base64 oder ``data:image/png;base64,…``.

    Returns ``{ok, datei, pfad, bytes}`` oder ``{ok: False, grund}``."""
    try:
        roh = _b64_von(png)
    except (ValueError, TypeError) as e:
        return {"ok": False, "grund": "kein lesbares PNG: %s" % e}
    if not roh.startswith(b"\x89PNG\r\n\x1a\n"):
        return {"ok": False, "grund": "die Daten sind kein PNG"}
    if len(roh) > MAX_BYTES:
        return {"ok": False, "grund": "zu gross (%.1f MB, erlaubt sind %.0f MB)"
                                      % (len(roh) / 1e6, MAX_BYTES / 1e6)}
    d = wurzel(project_dir)
    os.makedirs(d, exist_ok=True)
    basis = "%s_%s" % (time.strftime("%Y%m%d_%H%M%S"), _sicher(name))
    datei, n = basis + ".png", 1
    while os.path.exists(os.path.join(d, datei)):
        n += 1
        datei = "%s-%d.png" % (basis, n)
    pfad = os.path.join(d, datei)
    with open(pfad, "wb") as f:
        f.write(roh)
    neben = {"datei": datei, "beschriftung": str(beschriftung or "")[:400],
             "einstellungen": einstellungen if isinstance(einstellungen, dict) else {},
             "zeit": time.strftime("%Y-%m-%d %H:%M"), "bytes": len(roh)}
    try:
        with open(pfad[:-4] + ".json", "w", encoding="utf-8") as f:
            json.dump(neben, f, ensure_ascii=False)
    except OSError:
        pass
    return {"ok": True, "datei": datei, "pfad": pfad, "bytes": len(roh)}


def liste(project_dir):
    """Alle festgehaltenen Ansichten, neueste zuerst."""
    d = wurzel(project_dir)
    if not os.path.isdir(d):
        return []
    out = []
    for datei in sorted((f for f in os.listdir(d) if f.endswith(".png")), reverse=True):
        eintrag = {"datei": datei, "beschriftung": "", "einstellungen": {},
                   "zeit": "", "bytes": 0}
        try:
            eintrag["bytes"] = os.path.getsize(os.path.join(d, datei))
        except OSError:
            pass
        neben = os.path.join(d, datei[:-4] + ".json")
        if os.path.exists(neben):
            try:
                with open(neben, encoding="utf-8") as f:
                    eintrag.update(json.load(f) or {})
            except (OSError, ValueError):
                pass
        eintrag["datei"] = datei                      # nie aus der Seitendatei
        out.append(eintrag)
    return out


def pfad(project_dir, datei):
    """Absoluter Pfad EINER Ansicht — oder None. Prueft den Namen, damit ueber
    die Route kein Pfad hereinkommt."""
    if not _ERLAUBT.fullmatch(str(datei or "")) or not str(datei).endswith(".png"):
        return None
    p = os.path.join(wurzel(project_dir), datei)
    return p if os.path.exists(p) else None


def loeschen(project_dir, datei):
    p = pfad(project_dir, datei)
    if not p:
        return False
    try:
        os.remove(p)
    except OSError:
        return False
    try:
        os.remove(p[:-4] + ".json")
    except OSError:
        pass
    return True


def als_bildpaare(project_dir, auswahl=None):
    """Die Ansichten als ``[(relativer_pfad, Beschriftung)]`` — die Form, in der
    `ema_report` Bilder in Markdown setzt. ``auswahl`` = Dateinamen oder None
    fuer alle."""
    out = []
    for e in liste(project_dir):
        if auswahl is not None and e["datei"] not in auswahl:
            continue
        cap = e.get("beschriftung") or "Festgehaltene Ansicht"
        ein = e.get("einstellungen") or {}
        zusatz = []
        if ein.get("skala"):
            zusatz.append(str(ein["skala"]))
        if ein.get("lastfall"):
            zusatz.append(str(ein["lastfall"]))
        if ein.get("schnitt"):
            zusatz.append(str(ein["schnitt"]))
        if zusatz:
            cap += " (" + ", ".join(zusatz) + ")"
        out.append((os.path.join(ORDNER, e["datei"]), cap))
    return out
