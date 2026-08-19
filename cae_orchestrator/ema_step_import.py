"""STEP-Import eines fertigen E-Motors → Magnet-Erkennung + Einfädeln in die Pipeline.

Der Nutzer lädt eine STEP-Datei eines kompletten Motors (Stator + Rotor + Wicklung)
hoch. Dieses Modul

  1. liest mit FreeCAD alle Solids aus (Skript A, ``extract_solids_script``),
  2. klassifiziert sie **FreeCAD-frei** über radiale Bänder + Volumen-Cluster +
     Rotationssymmetrie (``classify_solids``) in Welle / Rotorblech / Magnete /
     Statorblech / Wicklung,
  3. leitet die Hauptmaße ab (``derive_geom``) und fittet je Magnet eine orientierte
     Bounding-Box (``detect_magnets``) → pol-lokale Magnete im **Canvas-Format**
     (Halbpol, ``{r,off,ang,len,thick,pol}`` — identisch zu ``DESIGN.magnets``),
  4. schreibt eine ``motor.FCStd`` (Skript B, ``assemble_fcstd_script``), in der das
     Rotorblech als Objekt ``"Rotor"`` benannt ist — so rechnet die **bestehende**
     Struktur-FEM (`ema_freecad.build_rotor_fem_script`) ohne Änderung darauf.

Die erkannten Magnete fahren als ``customLegs`` durch den **bestehenden** FDM-EM-Pfad
(`ema_analysis`, `magShape:"custom"`). Es wird kein neuer Solver gebaut.

Bewusste Grenzen (im UI als Warnung): die Erkennung ist heuristisch (daher der
Bestätigungsschritt im Designer-Tab), die Motorachse wird als **Z** angenommen,
Flussbarrieren (Luft-Voids im Rotor) werden in v1 nicht erkannt, und Material/Br/
Betriebspunkt liefert die Geometrie nicht — die setzt der Nutzer im Formular.

Wiederverwendung: ``ema_design_ai._validate_layout`` (clamp in gültigen Halbpol),
``ema_design_optimize._mirror_legs`` (d-Achsen-Spiegel, identisch zu ``dsnBuild``),
``ema_topology.magnet_legs`` (Round-trip-Test), ``freecad_runner.run_freecad_script``.
"""

import json
import math
import os

import numpy as np

import ema_design_ai as DAI
from freecad_runner import run_freecad_script


_VOL_CLUSTER_TOL = 0.40   # relative Volumentoleranz, damit Magnete als ein Cluster gelten


# ── FreeCAD-Skript A: Solid-Metadaten extrahieren ───────────────────────────────

def extract_solids_script(step_path: str) -> str:
    """FreeCAD-Code: STEP öffnen, jedes Solid vermessen, als ``SOLID_META:<json>``
    drucken. Die Achse ist Z; Radien beziehen sich auf den XY-Schwerpunkt der
    Gesamt-BoundBox (recentert, falls der Motor nicht im Ursprung liegt)."""
    return f"""\
import FreeCAD as App
import Part
import json as _json

# STEP direkt als Shape lesen (Part.read) — NICHT App.openDocument (das ist für .FCStd).
_top = Part.read(r"{step_path}")
_solids = list(_top.Solids) if hasattr(_top, "Solids") and _top.Solids else []
if not _solids and not _top.isNull():
    _solids = [_top]

# XY-Mittelpunkt der Gesamt-BoundBox = Motorachse (Z) durch diesen Punkt.
if _solids:
    _bb = _solids[0].BoundBox
    for _s in _solids[1:]:
        _bb.add(_s.BoundBox)
    _cx0, _cy0 = (_bb.XMin + _bb.XMax) / 2.0, (_bb.YMin + _bb.YMax) / 2.0
else:
    _cx0 = _cy0 = 0.0

print("STEP_NSOLIDS:%d" % len(_solids))
print("STEP_CENTER:%.4f,%.4f" % (_cx0, _cy0))

for _i, _s in enumerate(_solids):
    try:
        _vs = _s.Vertexes
        _xy = []
        _rmin = 1e18; _rmax = 0.0; _seen = set()
        for _v in _vs:
            _p = _v.Point
            _dx = _p.x - _cx0; _dy = _p.y - _cy0
            _r = (_dx * _dx + _dy * _dy) ** 0.5
            if _r < _rmin: _rmin = _r
            if _r > _rmax: _rmax = _r
            _k = (round(_dx, 1), round(_dy, 1))
            if _k not in _seen:
                _seen.add(_k); _xy.append([round(_dx, 3), round(_dy, 3)])
        if len(_xy) > 400:
            _step = len(_xy) // 400 + 1
            _xy = _xy[::_step]
        _com = _s.CenterOfMass
        _bbx = _s.BoundBox
        _meta = {{
            "id": _i,
            "vol": round(_s.Volume, 3),
            "com": [round(_com.x - _cx0, 3), round(_com.y - _cy0, 3), round(_com.z, 3)],
            "r_min": round(_rmin if _rmin < 1e17 else 0.0, 3),
            "r_max": round(_rmax, 3),
            "z0": round(_bbx.ZMin, 3), "z1": round(_bbx.ZMax, 3),
            "nfaces": len(_s.Faces),
            "xy": _xy,
        }}
        print("SOLID_META:" + _json.dumps(_meta))
    except Exception as _e:
        print("SOLID_SKIP:%d:%s" % (_i, _e))

print("CAD_SUCCESS")
"""


def _parse_solid_meta(stdout: str) -> tuple[list, tuple]:
    """Aus dem Skript-A-stdout die Solid-Metadaten + den XY-Mittelpunkt parsen."""
    solids, center = [], (0.0, 0.0)
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("SOLID_META:"):
            try:
                solids.append(json.loads(line[len("SOLID_META:"):]))
            except json.JSONDecodeError:
                pass
        elif line.startswith("STEP_CENTER:"):
            try:
                a, b = line[len("STEP_CENTER:"):].split(",")
                center = (float(a), float(b))
            except ValueError:
                pass
    return solids, center


# ── Klassifikation (FreeCAD-frei) ───────────────────────────────────────────────

def _com_r(s: dict) -> float:
    cx, cy = s["com"][0], s["com"][1]
    return math.hypot(cx, cy)


def _largest_volume_cluster(cands: list) -> list:
    """Größtes Cluster ähnlich-volumiger Solids (Magnete sind viele gleiche Körper)."""
    if not cands:
        return []
    order = sorted(cands, key=lambda s: s["vol"])
    best = []
    for i, seed in enumerate(order):
        v = seed["vol"]
        if v <= 0:
            continue
        group = [s for s in order if abs(s["vol"] - v) <= _VOL_CLUSTER_TOL * v]
        if len(group) > len(best):
            best = group
    if len(best) >= 4:
        return best
    # Fallback: kleine Stückzahl (z.B. 2-polig) trotzdem akzeptieren
    return best if len(best) >= 2 else []


def classify_solids(solids: list) -> dict:
    """Solids → Rollen über radiale Bänder, Volumen-Cluster und Lage.

    Returns dict mit ``shaft``/``rotor_iron``/``stator_iron`` (Solid-dict oder None),
    ``magnets``/``coils`` (Listen von Solid-dicts) und ``warnings`` (Liste)."""
    warns: list = []
    roles = {"shaft": None, "rotor_iron": None, "stator_iron": None,
             "magnets": [], "coils": [], "warnings": warns}
    if not solids:
        warns.append("Keine Solids in der STEP-Datei gefunden.")
        return roles

    rmax_all = max(s["r_max"] for s in solids)

    # Welle: Vollkörper (r_min ≈ 0), kleinster Außenradius.
    shaft_c = [s for s in solids if s["r_min"] <= max(2.0, 0.06 * rmax_all)]
    shaft = min(shaft_c, key=lambda s: s["r_max"]) if shaft_c else None

    others = [s for s in solids if s is not shaft]
    byvol = sorted(others, key=lambda s: s["vol"], reverse=True)
    big = [s for s in byvol if s["vol"] >= 0.15 * byvol[0]["vol"]] if byvol else []

    stator = rotor = None
    if big:
        # Statorblech = größtes-Volumen-Solid mit dem größten Außenradius.
        stator = max(big, key=lambda s: s["r_max"])
        # Rotorblech = großes Solid, dessen Außenradius INNERHALB der Statorbohrung liegt.
        rotor_c = [s for s in big if s is not stator and s["r_max"] < stator["r_min"] + 1.0]
        rotor = max(rotor_c, key=lambda s: s["vol"]) if rotor_c else None

    if rotor is None:
        # Rotor-only-STEP oder Stator nicht abgrenzbar: größtes Annulus = Rotor.
        rotor = max((s for s in others), key=lambda s: s["vol"], default=None)
        if stator is rotor:
            stator = None
            warns.append("Kein eindeutiges Statorblech gefunden — Stator-Maße bitte prüfen.")

    if rotor is None:
        warns.append("Kein Rotorblech erkennbar — Festigkeits-FEM nicht möglich.")
        return roles
    roles["rotor_iron"] = rotor
    roles["stator_iron"] = stator
    roles["shaft"] = shaft

    # Magnete: kleine, ähnlich-volumige Solids im Rotor-RING (nicht an der Achse:
    # ein Körper im Zentrum ist Welle/Bolzen, kein Magnet → untere Radius-Schranke).
    r_rot = rotor["r_max"]
    r_lo = max(rotor["r_min"], 0.2 * r_rot)
    fixed = {id(x) for x in (shaft, rotor, stator) if x is not None}
    mcand = [s for s in solids
             if id(s) not in fixed
             and s["vol"] < 0.5 * rotor["vol"]
             and r_lo < _com_r(s) < r_rot * 1.03]
    magnets = _largest_volume_cluster(mcand)
    roles["magnets"] = magnets
    if not magnets:
        warns.append("Keine Magnete erkannt — bitte im Designer von Hand ergänzen.")

    # Wicklung: Solids im Statorbereich (für Nutzahl-Schätzung).
    if stator is not None:
        used = fixed | {id(m) for m in magnets}
        roles["coils"] = [s for s in solids
                          if id(s) not in used and _com_r(s) > stator["r_min"] * 0.98]

    return roles


# ── Maße ableiten ───────────────────────────────────────────────────────────────

def _gap_cluster_count(angles: list) -> int:
    """Anzahl Winkel-Cluster über **Lücken-Clustering** auf dem Kreis.

    Eng beieinander liegende Winkel (z.B. die zwei Arme einer V-Form, oder die
    Leiter einer Nut) bilden ein Cluster; zwischen den Clustern klaffen große
    Lücken. Der Schnitt zwischen kleinen und großen Lücken wird am größten
    RELATIVEN Sprung der sortierten Lücken gesucht (robust, auch wenn die
    Innerhalb-Lücke > halbe Cluster-Teilung ist)."""
    if len(angles) < 2:
        return len(angles)
    a = sorted(x % (2 * math.pi) for x in angles)
    gaps = [a[i + 1] - a[i] for i in range(len(a) - 1)]
    gaps.append(a[0] + 2 * math.pi - a[-1])           # Lücke über den 0/2π-Sprung
    if max(gaps) <= 1e-6:
        return 1
    sg = sorted(gaps)
    best_ratio, split_val = 1.0, 0.0
    for i in range(len(sg) - 1):
        if sg[i] <= 1e-9:
            continue
        ratio = sg[i + 1] / sg[i]
        if ratio > best_ratio:
            best_ratio, split_val = ratio, (sg[i] + sg[i + 1]) / 2.0
    if best_ratio >= 1.3:                              # klar bimodal → große Lücken = Grenzen
        return sum(1 for g in gaps if g > split_val)
    return len(gaps)                                   # gleichmäßig → 1 Element/Cluster


def _estimate_poles(angles: list) -> int:
    """Polzahl aus den Magnet-Schwerpunkt-Winkeln — Cluster zählen, auf gerade runden."""
    poles = max(2, _gap_cluster_count(angles))
    if poles % 2:                                      # Pole sind immer gerade
        poles += 1
    return poles


def derive_geom(roles: dict) -> tuple[dict, list]:
    """Hauptmaße aus den klassifizierten Solids ableiten. Returns (params, warnings)."""
    warns = list(roles.get("warnings", []))
    rotor = roles["rotor_iron"]
    stator = roles["stator_iron"]
    shaft = roles["shaft"]
    magnets = roles["magnets"]

    rotorOD = round(2 * rotor["r_max"], 2)
    rotor_bore = 2 * rotor["r_min"]
    shaftD = round(2 * shaft["r_max"], 2) if shaft else round(rotor_bore, 2)
    axialLen = round(max(1.0, rotor["z1"] - rotor["z0"]), 2)

    if stator is not None:
        statorOD = round(2 * stator["r_max"], 2)
        statorID = round(2 * stator["r_min"], 2)
    else:
        statorOD = round(rotorOD + 0.10 * rotorOD + 40.0, 2)   # grobe Annahme
        statorID = round(rotorOD + 1.4, 2)                      # ~0,7 mm Luftspalt
        warns.append("Stator nicht erkannt — statorOD/statorID geschätzt, bitte korrigieren.")

    airgap = round((statorID - rotorOD) / 2.0, 3)
    if airgap <= 0:
        statorID = round(rotorOD + 1.4, 2)
        airgap = 0.7
        warns.append("Luftspalt ≤ 0 aus der Geometrie — auf 0,7 mm gesetzt.")

    # Polzahl aus Magnet-Symmetrie.
    angles = [math.atan2(m["com"][1], m["com"][0]) for m in magnets]
    poles = _estimate_poles(angles) if angles else 8
    p = max(1, poles // 2)

    # Nutzahl aus der Wicklung: die Coil-Solids winkelmäßig clustern (eine Nut enthält
    # bei Hairpins MEHRERE Leiter → reines Zählen überschätzt grob). Nur akzeptieren,
    # wenn das Ergebnis plausibel ist (Vielfaches von 3, im Band 1,5·p_pol … 4·p_pol);
    # sonst Standard 6·p — der Nutzer korrigiert die Nutzahl im Formular.
    coils = roles.get("coils", [])
    poles = 2 * p
    slots = 6 * p
    slot_warn = True
    if len(coils) >= 6:
        n_clusters = _gap_cluster_count([math.atan2(c["com"][1], c["com"][0]) for c in coils])
        if n_clusters % 3 == 0 and poles <= n_clusters <= 6 * poles:
            slots = n_clusters
            slot_warn = False
    if slot_warn:
        warns.append(f"Nutzahl nicht zuverlässig aus der Geometrie ableitbar "
                     f"(z.B. Hairpin-Wicklung) — auf {slots} (6·p) gesetzt, bitte prüfen.")

    params = {
        "statorOD": statorOD, "statorID": statorID, "rotorOD": rotorOD,
        "shaftD": shaftD, "axialLen": axialLen, "airgap": airgap,
        "p": p, "slots": int(slots), "magShape": "custom",
        "slotDepth": round(max(4.0, (statorOD - statorID) / 2.0 * 0.55), 2),
        # Material/Betriebspunkt liefert die Geometrie nicht → Defaults (Nutzer setzt sie).
        "rotor_lam": "m270_35a", "stator_lam": "m270_35a", "hairpin_mat": "cu_etp",
        "magnet": "ndfeb_n35", "cooling": "water",
        "rpm_from": 1000, "rpm_to": 12000, "load_nm": 100,
    }
    return params, warns


# ── Magnet-Erkennung (OBB-Fit → pol-lokale Canvas-Magnete) ───────────────────────

def _obb_fit(xy: list):
    """Orientierte Bounding-Box eines (rechteckigen) Footprints via PCA.

    Returns (cx, cy, length, thick, tilt_rad) — Zentrum, längere/kürzere Ausdehnung
    und Winkel der Hauptachse im globalen (recenterten) XY-Frame."""
    pts = np.asarray(xy, dtype=float)
    if pts.shape[0] < 3:
        # zu wenig Punkte: achsparallele Box
        mn, mx = pts.min(axis=0), pts.max(axis=0)
        c = (mn + mx) / 2.0
        return float(c[0]), float(c[1]), float(mx[0] - mn[0]), float(mx[1] - mn[1]), 0.0
    c = pts.mean(axis=0)
    d = pts - c
    cov = np.cov(d.T)
    evals, evecs = np.linalg.eigh(cov)
    # Hauptachse = größerer Eigenwert
    axis = evecs[:, int(np.argmax(evals))]
    perp = np.array([-axis[1], axis[0]])
    proj_a = d @ axis
    proj_p = d @ perp
    length = float(proj_a.max() - proj_a.min())
    thick = float(proj_p.max() - proj_p.min())
    # Zentrum auf den tatsächlichen Mittelpunkt der Projektionsspannen legen
    ca = (proj_a.max() + proj_a.min()) / 2.0
    cp = (proj_p.max() + proj_p.min()) / 2.0
    cc = c + ca * axis + cp * perp
    if thick > length:                       # Achse zeigt entlang der kurzen Seite → tauschen
        length, thick = thick, length
        axis, perp = perp, axis
    tilt = math.atan2(axis[1], axis[0])
    return float(cc[0]), float(cc[1]), length, thick, tilt


def detect_magnets(roles: dict, params: dict) -> list:
    """Magnet-Solids → pol-lokale Halbpol-Magnete im Canvas-Format ``{r,off,ang,len,
    thick,pol}``. Alle Pole werden in einen Pol gefaltet, auf die +offset-Hälfte
    reduziert und über ``ema_design_ai._validate_layout`` in einen gültigen Halbpol
    geclamped."""
    magnets = roles["magnets"]
    if not magnets:
        return []
    poles = max(2, 2 * int(params.get("p", 4)))
    sector = 2 * math.pi / poles

    folded = []
    for m in magnets:
        cx, cy, length, thick, tilt = _obb_fit(m["xy"])
        # In welchen Pol fällt der Magnet? Pol-Mittenwinkel = nächstes Vielfache von sector.
        ang_g = math.atan2(cy, cx)
        k = round(ang_g / sector)
        a = -k * sector                       # Rotation, die diesen Pol auf die +x-Achse legt
        ca, sa = math.cos(a), math.sin(a)
        lx = cx * ca - cy * sa                # pol-lokales Zentrum (x=radial, y=tangential)
        ly = cx * sa + cy * ca
        tl = tilt + a                          # pol-lokaler Längsachsenwinkel
        ux, uy = math.cos(tl), math.sin(tl)
        # Endpunkte; Start = das radial innere Ende (kleineres x)
        e1 = (lx - ux * length / 2.0, ly - uy * length / 2.0)
        e2 = (lx + ux * length / 2.0, ly + uy * length / 2.0)
        start, end = (e1, e2) if e1[0] <= e2[0] else (e2, e1)
        ang = math.degrees(math.atan2(end[1] - start[1], end[0] - start[0]))
        folded.append({"r": round(start[0], 2), "off": round(start[1], 2),
                       "ang": round(ang, 1), "len": round(length, 2),
                       "thick": round(max(1.0, thick), 2), "pol": 1})

    # Auf die +offset-Hälfte reduzieren (Master-Halbpol) und Duplikate (aus der
    # Pol-Faltung) verschmelzen.
    half, seen = [], set()
    for m in folded:
        if m["off"] < -0.6:                    # gehört zur gespiegelten Hälfte
            continue
        key = (round(m["r"], 0), round(abs(m["off"]), 0), round(m["len"], 0))
        if key in seen:
            continue
        seen.add(key)
        m["off"] = abs(m["off"])
        half.append(m)

    # In einen gültigen Halbpol clampen (Wiederverwendung der Designer-Robustheit).
    mags, _bars = DAI._validate_layout(half, [], params)
    return mags


# ── FreeCAD-Skript B: motor.FCStd mit benanntem "Rotor" schreiben ───────────────

def assemble_fcstd_script(step_path: str, roles: dict, fcstd_path: str) -> str:
    """FreeCAD-Code: dieselben Solids erneut einsammeln (gleiche Reihenfolge wie
    Skript A) und in ein neues Dokument mit benannten Objekten kopieren — das
    Rotorblech als ``"Rotor"`` (damit die bestehende Struktur-FEM greift). Speichert
    ``motor.FCStd`` + STEP-Reexport und druckt die üblichen CAD-Marker."""
    rotor_id = roles["rotor_iron"]["id"]
    stator_id = roles["stator_iron"]["id"] if roles.get("stator_iron") else -1
    shaft_id = roles["shaft"]["id"] if roles.get("shaft") else -1
    magnet_ids = [m["id"] for m in roles.get("magnets", [])]
    coil_ids = [c["id"] for c in roles.get("coils", [])]
    ids_json = json.dumps({"rotor": rotor_id, "stator": stator_id, "shaft": shaft_id,
                           "magnets": magnet_ids, "coils": coil_ids})

    return f"""\
import FreeCAD as App
import Part
import json as _json

# Dieselbe Solid-Reihenfolge wie Skript A (Part.read → .Solids), damit die IDs passen.
_top = Part.read(r"{step_path}")
_solids = list(_top.Solids) if hasattr(_top, "Solids") and _top.Solids else []
if not _solids and not _top.isNull():
    _solids = [_top]

_ids = {ids_json}

doc = App.newDocument("Motor")

def _add(name, shape, col):
    _ob = doc.addObject("Part::Feature", name)
    _ob.Shape = shape
    try:
        _ob.ViewObject.ShapeColor = col
    except Exception:
        pass
    return _ob

def _get(i):
    return _solids[i] if 0 <= i < len(_solids) else None

# Rotorblech MUSS "Rotor" heißen (Struktur-FEM sucht per Name).
_rot = _get(_ids["rotor"])
if _rot is not None:
    _add("Rotor", _rot, (0.55, 0.55, 0.60))
if _ids["shaft"] >= 0 and _get(_ids["shaft"]) is not None:
    _add("Shaft", _get(_ids["shaft"]), (0.30, 0.30, 0.33))
if _ids["stator"] >= 0 and _get(_ids["stator"]) is not None:
    _add("Stator", _get(_ids["stator"]), (0.45, 0.45, 0.50))
_mag_shapes = [_get(i) for i in _ids["magnets"] if _get(i) is not None]
if _mag_shapes:
    _add("Magnets", Part.makeCompound(_mag_shapes), (0.85, 0.20, 0.20))
_coil_shapes = [_get(i) for i in _ids["coils"] if _get(i) is not None]
if _coil_shapes:
    _add("Coils", Part.makeCompound(_coil_shapes), (0.80, 0.50, 0.20))

doc.recompute()

_rotor_obj = doc.getObject("Rotor")
if _rotor_obj is not None:
    _rs = _rotor_obj.Shape
    print("CAD_FACES:[]")
    print("CAD_VOLUME:%.2f" % _rs.Volume)
else:
    print("CAD_FACES:[]")
    print("CAD_VOLUME:0.00")

doc.saveAs(r"{fcstd_path}")
print("SAVED:{fcstd_path}")

try:
    _step_out = r"{fcstd_path}".rsplit(".", 1)[0] + ".step"
    _shapes = [o.Shape for o in doc.Objects
               if hasattr(o, "Shape") and o.Shape and not o.Shape.isNull()]
    if _shapes:
        Part.makeCompound(_shapes).exportStep(_step_out)
        print("STEP_SAVED:" + _step_out)
except Exception as _se:
    print("STEP_FAIL:" + str(_se))

print("CAD_SUCCESS")
"""


# ── Orchestrator ────────────────────────────────────────────────────────────────

def run_import(step_path: str, project_dir: str, progress_cb=None) -> dict:
    """Vollständiger Import: Skript A → klassifizieren → Maße/Magnete ableiten →
    Skript B (motor.FCStd mit "Rotor"). Returns ein ``applyDesignToCanvas``-förmiges
    Dict ``{params, magnets, barriers, warnings, begruendung, imported}``."""
    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    _log("🔍 Lese Solids aus der STEP-Datei …", 5)
    resA = run_freecad_script(extract_solids_script(step_path), timeout=300)
    solids, _center = _parse_solid_meta(resA.get("stdout", ""))
    if not solids:
        raise RuntimeError("Keine Solids in der STEP-Datei lesbar. "
                           + (resA.get("stderr", "")[:200]))
    _log(f"✓ {len(solids)} Solids gefunden", 25)

    _log("🧩 Klassifiziere Bauteile (Welle/Rotor/Magnete/Stator) …", 35)
    roles = classify_solids(solids)
    if roles["rotor_iron"] is None:
        raise RuntimeError("Kein Rotorblech in der STEP-Datei erkennbar.")

    params, warns = derive_geom(roles)
    magnets = detect_magnets(roles, params)
    _log(f"✓ Maße abgeleitet · {len(magnets)} Magnete (Halbpol) · {2*params['p']} Pole", 55)
    for w in warns:
        _log("⚠ " + w)

    _log("🧊 Schreibe motor.FCStd (Rotor benannt) …", 70)
    fcstd = os.path.join(project_dir, "motor.FCStd")
    resB = run_freecad_script(assemble_fcstd_script(step_path, roles, fcstd), timeout=300)
    if not resB.get("cad_success"):
        warns.append("motor.FCStd-Erzeugung meldete keinen Erfolg — "
                     "Festigkeits-FEM evtl. nicht möglich. " + resB.get("stderr", "")[:200])
        _log("⚠ motor.FCStd unsicher: " + resB.get("stderr", "")[:200])
    else:
        _log("✓ motor.FCStd geschrieben", 90)

    # customLegs für die Pipeline (Master-Halbpol → voller Pol, identisch zu dsnBuild).
    import ema_design_optimize as DOPT
    custom_legs = DOPT._mirror_legs(magnets) if magnets else []

    n_stator = "ja" if roles.get("stator_iron") else "geschätzt"
    begruendung = (
        f"Aus STEP importiert: {len(solids)} Solids → Rotor + "
        f"{len(roles['magnets'])} Magnet-Körper, Stator {n_stator}. "
        f"Abgeleitet: {2*params['p']} Pole, {params['slots']} Nuten, "
        f"Ø {params['rotorOD']} mm Rotor, Luftspalt {params['airgap']} mm. "
        "Bitte Magnetlage, Polung und Werkstoffe prüfen, dann rechnen."
    )

    # meta.json schreiben, damit das Projekt ladbar ist (Hauptpfad: Frontend schickt
    # den bestätigten Payload erneut über /analyse mit imported=true).
    payload = dict(params)
    payload["geom"] = {**{k: params[k] for k in (
        "statorOD", "statorID", "rotorOD", "shaftD", "slots", "slotDepth", "p")},
        "magShape": "custom", "customLegs": custom_legs, "customBarriers": []}
    payload["imported"] = True
    payload["axial_len"] = params["axialLen"]
    try:
        with open(os.path.join(project_dir, "meta.json"), "w") as f:
            json.dump({"payload": payload, "imported": True,
                       "warnings": warns, "source": "step_import"}, f, indent=1)
    except OSError:
        pass

    return {
        "params": params,
        "magnets": magnets,
        "barriers": [],
        "customLegs": custom_legs,
        "warnings": warns,
        "begruendung": begruendung,
        "imported": True,
        "source": "step_import",
        "n_solids": len(solids),
        "n_magnet_bodies": len(roles["magnets"]),
        "poles": 2 * params["p"],
    }
