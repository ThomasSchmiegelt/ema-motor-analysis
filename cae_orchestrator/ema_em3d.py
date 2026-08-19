"""Echte 3D-Magnetfeldberechnung der IPM-Maschine mit Elmer FEM.

Der 2D-FDM-Löser (`ema_analysis`) nimmt unendliche axiale Länge an. Dieses Modul baut
ein **echtes 3D-Modell** (Gmsh-Mesh → Elmer-Magnetostatik) und liefert damit, was 2D
prinzipbedingt nicht kann: **Endeffekte/finite Länge**, **Schrägung (Skew)**, eine echte
3D-Feldlösung + Visualisierung und einen **Vergleich gegen 2D**.

Pipeline (jeweils eigene Funktion):
  build_mesh(geom, axial, opts) → Gmsh-OCC-Geometrie (3D-Primitive + fragment +
      Physical-Tagging per Schwerpunkt/Radius, analog `ema_step_import`), Magnete als
      tordierbare Extrusion (Skew). Liefert (msh_path, tags).
  write_sif(geom, opts, tags, work_dir) → Elmer-Solver-Input (WhitneyAVSolver-
      Magnetostatik + MagnetoDynamicsCalcFields + SaveScalars/SaveLine + VTU).
  parse_results(...) → Moment, Luftspalt-B(θ,z), Schnittbilder, 2D-Vergleich.
  run_em3d(payload, state, project_dir, cb) → Orchestrator (mesh→ElmerGrid→sif→
      ElmerSolver→parse), Fortschritt via progress_cb.

Wiederverwendung: `ema_topology.magnet_legs` (Magnetlage/-richtung, gleiche Quelle wie
2D/CAD), `ema_analysis` (estimate_dq_currents, run_em_analysis, compute_performance —
für Anregung + 2D-Vergleich), `ema_pipeline.MAGNETS/LAMINATES` (Br/μr).

Der 2D-Pfad bleibt unangetastet; dies ist ein eigenständiger On-Demand-Job.
"""

import hashlib
import math
import os
import json

import numpy as np

import ema_topology as TOPO

MU0 = 1.2566370614e-6           # Vakuumpermeabilität [H/m]
MU_R_IRON = 500.0               # lineares Eisen (wie 2D), BH-Kurve = Folgeschritt
MU_R_MAG = 1.05
# Skala der eingeprägten Nut-/Ring-Stromdichte (experimenteller 3D-Lastfall). Nut und Ring
# nutzen DENSELBEN C0, damit sich der Strom schließt; dieser Faktor regelt nur die absolute
# Höhe. Empirisch so kalibriert, dass das 3D-Luftspalt-Ankerfeld dem analytischen 2D-Wert
# `_analytical_Barm` entspricht (dominiert vom geometrieunabhängigen mm↔m-Einheitenfaktor;
# für andere Maschinen daher näherungsweise gültig — Lastfeld bleibt experimentell).
COIL_J_SCALE = 199.0
# Standard-Obergrenze der 3D-Netzknoten (Auto-Pfad ohne ausdrückliches Ziel). Das kantenbasierte
# curl-curl-System (MUMPS direkt) skaliert im RAM ~linear mit den Knoten, aber der MUMPS-Fill-in
# lässt den Bedarf leicht superlinear wachsen. Gemessen auf dieser Workstation (31 GiB RAM,
# `em3d_perf_check.py`, 8-polig/48-Nut V-Motor, Leerlauf):
#     Knoten     Solve      Peak-RAM     kB/Knoten
#      38.8k       24 s      2.3 GiB        59
#      64.1k       44 s      4.3 GiB        67
#     124.6k       91 s      9.7 GiB        78
#     162.9k      145 s     13.0 GiB        80
#     209.2k      195 s     17.9 GiB        90
#     277.3k      259 s     25.2 GiB        95   ← RAM-Stop bei 80 % (extrapoliert Deckel ~345k)
# → 55000 Knoten sind bewusst KONSERVATIV (≈3,5 GiB, ≈35 s) — schnell + immer stabil, NICHT
#   RAM-limitiert. Wer feiner will, gibt über den UI-Regler ein `target_nodes` bis EM3D_NODE_CEILING
#   vor. Wird das Netz feiner als das Ziel/den Cap, vergröbert `_build_mesh_capped` die Zellgrößen
#   automatisch (Segfault-/OOM-Schutz) und protokolliert das in `mesh_build.log`.
EM3D_MAX_NODES = 55000
# Harte Obergrenze für die vom Nutzer wählbare Ziel-Knotenzahl (UI-Regler 10k–300k). Oberhalb ~345k
# reicht der RAM dieser Maschine für den MUMPS-Direktlöser nicht mehr (OOM) — 300k lässt Sicherheit.
EM3D_NODE_CEILING = 300000

# In-Process-Cache des fertig gebauten 3D-Netzes je em3d-Arbeitsverzeichnis. Das Mesh hängt
# NUR an Geometrie + netzrelevanten Optionen (NICHT an rpm/load_nm) — ändert der Nutzer beim
# nächsten Einzellauf nur den Betriebspunkt, wird das Netz nicht neu gebaut, sondern
# wiederverwendet (nur der Löser läuft neu). Schlüssel = Arbeitsverzeichnis → {key, tags}.
# Prozess-lokal (Neustart ⇒ erster Lauf baut neu) und gegen fehlende Mesh-Dateien abgesichert.
_MESH_CACHE = {}


# ── Magnetplatzierung (1:1 zur 2D-Rasterung `ema_analysis._rasterise`) ───────────

def magnet_rects(geom: dict) -> list:
    """Alle Magnete der Maschine im globalen mm-Frame (z=Querschnitt).

    Spiegelt die Platzierung aus `ema_analysis._rasterise` (Zeilen ~205–267): je Pol
    `pole_ang = p_i·2π/poles`, alternierendes Vorzeichen, Startpunkt rotiert, Länge
    entlang `pole_ang+tilt`. Returns Liste von Dicts mit Mittelpunkt, Winkel, Maßen,
    Magnetisierungs-Einheitsvektor und Polindex/-vorzeichen."""
    poles = int(geom["p"]) * 2
    legs, _meta = TOPO.magnet_legs(geom)
    out = []
    long_swap = geom.get("magOrient") == "longitudinal"
    r_ro = geom["rotorOD"] / 2.0
    for p_i in range(poles):
        pole_ang = p_i * (2 * math.pi / poles)
        sign = 1 if p_i % 2 == 0 else -1
        cp, sp = math.cos(pole_ang), math.sin(pole_ang)
        for lg in legs:
            long_ang = pole_ang + lg.tilt
            lx, ly = math.cos(long_ang), math.sin(long_ang)
            if lg.mag_mode == "tangential":
                mdx, mdy = -sp, cp
            elif lg.mag_mode == "radial":
                base = pole_ang + lg.mag_rot
                mdx, mdy = math.cos(base), math.sin(base)
            else:                                          # "perp"
                mdx, mdy = -ly, lx
            if long_swap:
                mdx, mdy = -mdy, mdx

            if lg.placement == "surface":
                # Oberflächenmagnet: als Rechteck am OD genähert (v1).
                center_ang = pole_ang + lg.offset / r_ro
                rc = r_ro - lg.thickness / 2.0
                cx = rc * math.cos(center_ang); cy = rc * math.sin(center_ang)
                ang = center_ang + math.pi / 2.0          # Länge tangential
                length, thick = lg.length, lg.thickness
            else:
                sx = lg.r_pos * cp - lg.offset * sp        # Startpunkt global (mm)
                sy = lg.r_pos * sp + lg.offset * cp
                cx = sx + lx * lg.length / 2.0
                cy = sy + ly * lg.length / 2.0
                ang = long_ang
                length, thick = lg.length, lg.thickness

            m_amp = float(sign * lg.mag_sign)
            out.append({"cx": cx, "cy": cy, "ang": ang, "length": length,
                        "thick": max(0.8, thick), "pole": p_i, "sign": m_amp,
                        "mdx": mdx, "mdy": mdy, "placement": lg.placement})
    return out


def barrier_rects(geom: dict) -> list:
    """Flussbarrieren der Maschine als Luft-Rechtecke im globalen mm-Frame.

    Spiegelt die Barrieren-Logik aus `ema_analysis._rasterise`:
    - **parametrisch** (`genFluxBarrierQ`/`genFluxBarrierD`): je Pol ein radialer Schlitz
      (q = zwischen den Polen `(i+0.5)·2π/poles`, d = Polmitte `i·2π/poles`), radiales
      Band `[r_in, r_out=r_ro−2mm]`, tangential `fluxBarrierWidth`.
    - **custom** (`customBarriers`, Designer): Polylinien im Pol-lokalen Frame
      (x=radial, y=tangential), pro Pol repliziert, jedes Segment ein Box-Prisma.
    Returns Liste {cx,cy,ang,length,thick} (Länge entlang `ang`) — gleiches Format wie
    `magnet_rects`, aber ohne Magnetisierung (Luft). Leere Liste, wenn keine Barrieren.
    """
    poles = int(geom["p"]) * 2
    r_ro = geom["rotorOD"] / 2.0
    r_sh = geom["shaftD"] / 2.0
    out = []

    has_q = bool(geom.get("genFluxBarrierQ", False))
    has_d = bool(geom.get("genFluxBarrierD", False))
    if has_q or has_d:
        fbw = max(0.5, min(40.0, float(geom.get("fluxBarrierWidth", 3.0))))
        fbd = max(1.0, min(120.0, float(geom.get("fluxBarrierDepth", 10.0))))
        r_out = r_ro - 2.0
        r_in = max(r_sh + 1.0, r_out - fbd)
        rc = (r_in + r_out) / 2.0
        length = max(0.8, r_out - r_in)
        angs = []
        if has_d:
            angs += [i * 2 * math.pi / poles for i in range(poles)]
        if has_q:
            angs += [(i + 0.5) * 2 * math.pi / poles for i in range(poles)]
        for a in angs:
            out.append({"cx": rc * math.cos(a), "cy": rc * math.sin(a),
                        "ang": a, "length": length, "thick": fbw})

    cbars = geom.get("customBarriers") or []
    for p_i in range(poles):
        pa = p_i * 2 * math.pi / poles
        cp, sp = math.cos(pa), math.sin(pa)
        for bar in cbars:
            pts = bar.get("pts") or []
            w = max(0.5, float(bar.get("width", 3.0)))
            gp = [(px * cp - py * sp, px * sp + py * cp) for px, py in pts]
            for i in range(len(gp) - 1):
                ax, ay = gp[i]; bx, by = gp[i + 1]
                dx, dy = bx - ax, by - ay
                ll = math.hypot(dx, dy)
                if ll < 1e-6:
                    continue
                out.append({"cx": (ax + bx) / 2.0, "cy": (ay + by) / 2.0,
                            "ang": math.atan2(dy, dx), "length": ll, "thick": w})
    return out


def slot_rects(geom: dict) -> list:
    """Statornuten als Luft-Rechtecke im globalen mm-Frame (z=Querschnitt).

    Spiegelt die Nut-Rasterung aus `ema_analysis._rasterise` (Zeilen ~173–192): ``slots``
    radiale Nuten, je zentriert auf ``s·2π/slots``, halbe Winkelbreite ``(2π/slots)/4``
    (Nut belegt die halbe Nutteilung, Zahn die andere Hälfte), radiales Band
    ``[r_si, r_si+slotDepth]``. Als gerade (NICHT geschrägte) Vollprismen über die ganze
    Länge gebaut und in den Statorring gefragmentet → der Stator bekommt echte Zähne, der
    Fluss bündelt sich in den Zähnen (im 3D-Feld sichtbar). Returns {cx,cy,ang,length,thick}
    wie `magnet_rects`, aber Luft. Leere Liste, wenn keine Nuten."""
    n_slots = int(geom.get("slots", 0) or 0)
    slot_d = float(geom.get("slotDepth", 0.0) or 0.0)
    if n_slots <= 0 or slot_d <= 0.5:
        return []
    r_si = geom["statorID"] / 2.0
    r_so = geom["statorOD"] / 2.0
    slot_d = min(slot_d, max(1.0, (r_so - r_si) - 1.0))   # 1 mm Rückenjoch stehen lassen
    dth = 2 * math.pi / n_slots
    sw = dth * 0.5 / 2.0                                   # halbe Winkelbreite (= 2D `sw`)
    rc = r_si + slot_d / 2.0
    width = max(0.6, 2.0 * rc * math.sin(sw))             # tangentiale Sehnenbreite
    out = []
    for s in range(n_slots):
        a = s * dth
        out.append({"cx": rc * math.cos(a), "cy": rc * math.sin(a),
                    "ang": a, "length": slot_d, "thick": width})
    return out


def _assign_pieces(target_pieces, avail, dist_frac=0.5, mlo=0.3, mhi=2.6, single=False):
    """Fragment-Volumina den erwarteten Bauteilen zuordnen (COM-Distanz + Massengate).

    Die kleinen Taschen-Kappen brauchen lockerere Toleranzen (dist_frac/mlo/mhi), weil sie
    beim Fragmentieren am Magnet/Rotorrand beschnitten werden. Erwartetes Volumen: für die
    dünnen Taschen-Luftschalen die explizite Schalenmasse (``vol_pred`` ≈ Tasche − Magnet),
    sonst die volle Box — sonst überschätzt die Box die 0,1–0,3-mm-Schale massiv und das
    Massengate würde die Tasche verwerfen.

    ``single=True`` (für die MAGNETE): pro Stück wird nur das EINE Volumen behalten, dessen
    Masse der Vorhersage am nächsten kommt. Grund: Magnet-Prisma UND seine obround-Luft-
    Tasche haben denselben Schwerpunkt, und bei KURZEN Magneten (z. B. PMa-SynRM-Außenlage,
    5×3 mm) passiert die Taschen-Schale (~0,6·Magnetmasse) das lockere Massengate — dann
    wurde die LUFT-Schale mit-magnetisiert und die Tasche nie als Luft getaggt (Feldlinien
    liefen an den Magneten vorbei). Das freigegebene Schalen-Volumen fängt danach die
    Kappen-Zuordnung (``cap_pieces``/``vol_pred``) als Luft auf."""
    assign = {i: [] for i in range(len(target_pieces))}
    pred = [p.get("vol_pred", p["length"] * p["thick"] * (p["z1"] - p["z0"]))
            for p in target_pieces]
    cand = {i: [] for i in range(len(target_pieces))}
    for (v, gx, gy, gz, vmass) in avail:
        best, bd = None, 1e18
        for i, p in enumerate(target_pieces):
            zc = 0.5 * (p["z0"] + p["z1"])
            d = math.hypot(gx - p["cx"], gy - p["cy"]) + abs(gz - zc)
            if d < bd:
                bd, best = d, i
        if (best is not None
                and bd < dist_frac * max(target_pieces[best]["length"], target_pieces[best]["thick"])
                and mlo * pred[best] < vmass < mhi * pred[best]):
            cand[best].append((v, vmass))
    taken = set()
    for i, lst in cand.items():
        if single and len(lst) > 1:
            lst = [min(lst, key=lambda t: abs(t[1] - pred[i]))]
        for v, _m in lst:
            assign[i].append(v); taken.add(v)
    return assign, taken


def _magnet_pieces(rects: list, L: float, opts: dict):
    """Zerlegt jeden Magneten in die zu bauenden 3D-Stücke.

    **Gestaffelte Schrägung (Staffelung).** Echte Blechpakete sind oft in K gleich lange
    axiale Abschnitte unterteilt, die jeweils um einen festen Winkel gegeneinander um die
    Wellenachse verdreht sind (z. B. 200 mm → 5 Abschnitte je 5°). Die Magnete drehen sich
    mit ihrem Abschnitt mit. Hier wird jeder Magnet in ``skew_segments`` Prismen geschnitten;
    Segment k ist um ``k·skew_step_deg`` um die Achse (z) gedreht — Position, Längsachse UND
    Magnetisierungsrichtung. Das Rotoreisen selbst ist rotationssymmetrisch und bleibt ein
    durchgehender Zylinder (die Pockets der versetzten Magnete schneiden die Staffelung hinein).

    Fällt ``skew_segments < 2`` aus, wird je Magnet EIN Stück über die volle Länge gebaut
    (der kontinuierliche ``skew_deg``-Twist wird dann in ``build_mesh`` angewandt).

    Returns ``(pieces, n_seg, step_rad)`` mit pieces = Liste von Dicts
    {cx,cy,ang,length,thick,mdx,mdy,sign,pole,z0,z1,mag_idx}.
    """
    segs = max(1, int(opts.get("skew_segments", 1) or 1))
    step = math.radians(float(opts.get("skew_step_deg", 0.0) or 0.0))
    pieces = []
    if segs >= 2 and abs(step) > 1e-9:
        for mi, m in enumerate(rects):
            mdx, mdy = m.get("mdx", 0.0), m.get("mdy", 0.0)
            for k in range(segs):
                phi = k * step
                c, s = math.cos(phi), math.sin(phi)
                pieces.append({
                    "cx": m["cx"] * c - m["cy"] * s,
                    "cy": m["cx"] * s + m["cy"] * c,
                    "ang": m["ang"] + phi,
                    "length": m["length"], "thick": m["thick"],
                    "mdx": mdx * c - mdy * s,
                    "mdy": mdx * s + mdy * c,
                    "sign": m.get("sign", 0.0), "pole": m.get("pole", 0),
                    "z0": k * L / segs, "z1": (k + 1) * L / segs, "mag_idx": mi})
    else:
        for mi, m in enumerate(rects):
            pieces.append({"cx": m["cx"], "cy": m["cy"], "ang": m["ang"],
                           "length": m["length"], "thick": m["thick"],
                           "mdx": m.get("mdx", 0.0), "mdy": m.get("mdy", 0.0),
                           "sign": m.get("sign", 0.0), "pole": m.get("pole", 0),
                           "z0": 0.0, "z1": L, "mag_idx": mi})
    return pieces, segs, step


# ── 3D-Mesh (Gmsh OCC) ──────────────────────────────────────────────────────────

class _DegenerateMeshError(RuntimeError):
    """Das Netz wurde gebaut, enthält aber entartete Tetraeder (Sliver), auf denen der Elmer-
    Löser still scheitern würde. Getrennter Typ, damit ``build_mesh`` NICHT die (hier hilfreichen)
    Luft-Taschen abschaltet, sondern direkt an den Selbstheil-Monitor (Netzqualität/-dichte) übergibt."""


class _Em3dAborted(RuntimeError):
    """Der laufende ElmerSolver wurde vom Nutzer abgebrochen (``elmer_runner.abort_current``).
    Eigener Typ, damit der Sweep-Loop den Abbruch von einem echten Löser-Fehler unterscheidet
    und das bis dahin gerechnete Teilergebnis behält."""


def build_mesh(geom: dict, axial: float, opts: dict, msh_path: str) -> dict:
    """Robuster Wrapper um ``_build_mesh_once``: die Magnettaschen können bei groben
    Netzen/manchen Topologien ungültige Facetten erzeugen → dann EINMAL ohne Taschen neu bauen.
    So heilt sich jeder Aufrufer selbst (auch die Tests, die build_mesh direkt rufen).

    **Hexaeder-Modus (opt-in, ``opts["hex_mesh"]``):** strukturiertes Hex-/Prismen-Netz
    über ``_build_hex_mesh_once`` (2D-Querschnitt + axiale Extrusion) — für den geraden
    UND den gestaffelten Fall. Da der Hex-Pfad (v1) kein eingeprägtes Lastfeld
    (Stirnring-Leiter) kann, wird bei aktiver Spulenstrom-Einprägung automatisch auf das
    Tet-Netz zurückgefallen (Leerlauf-/Feldvisualisierung bleibt Hex). Schlägt der
    Hex-Bau fehl, ebenfalls Tet-Fallback."""
    if opts.get("hex_mesh"):
        want_load = (str(opts.get("excitation", "open_circuit")) == "loaded"
                     and bool(opts.get("coil_currents", True)))
        if want_load:
            tags = _build_mesh_once(geom, axial, opts, msh_path)   # Lastfeld ⇒ Tet
            tags["hex_fallback"] = "loaded_field_needs_tet"
            return tags
        try:
            return _build_hex_mesh_once(geom, axial, opts, msh_path)
        except Exception as e:
            tags = _build_mesh_once(geom, axial, opts, msh_path)   # Hex-Bau fehlgeschlagen ⇒ Tet
            tags["hex_fallback"] = f"hex_build_failed: {type(e).__name__}"
            return tags
    try:
        return _build_mesh_once(geom, axial, opts, msh_path)
    except _DegenerateMeshError:
        raise                                          # Taschen helfen → nicht abschalten, ab an die Leiter
    except Exception:
        # Sofort-Fallback „ohne Taschen" NUR für Direktaufrufer (Tests, Skripte). Der
        # Selbstheil-Monitor (`_build_mesh_capped`) schaltet ihn per `pocket_fallback=False`
        # ab: sonst fällt hier schon beim ERSTEN Fehlversuch das Modellfeature weg, bevor die
        # Leiter überhaupt an der Netzqualität drehen konnte — genau die Reihenfolge, die
        # `_mesh_mitigations` ausdrücklich umdreht (Netz zuerst, Modell zuletzt). Gemessen im
        # Projekt 20260812_073601: alle 5 Logzeilen meldeten `pockets=True`, das behaltene
        # Netz hatte 0 Taschen (`pocket_clear=0.0`, nur 8 Luftkörper, keine Luft im Rotor
        # zwischen r=48 mm und r=94 mm).
        if opts.get("mag_pockets", True) and opts.get("pocket_fallback", True):
            tags = _build_mesh_once(geom, axial, dict(opts, mag_pockets=False), msh_path)
            tags["caps_dropped"] = True
            return tags
        raise


def _build_mesh_once(geom: dict, axial: float, opts: dict, msh_path: str) -> dict:
    """Baut das 3D-Mesh und schreibt ``msh_path`` (MSH 2.2 für ElmerGrid).

    3D-Primitive (Zylinder je Radius + Magnet-Extrusionen + Luft-Box) → ``occ.fragment``
    (konform) → Physical-Volumes per Schwerpunkt/Radius/z getaggt. Skew via tordierter
    Magnet-Extrusion. Returns ``tags`` = {bodies, magnets, coils, boundary, L, dims}.
    """
    import gmsh

    L = float(axial)
    r_shaft = geom["shaftD"] / 2.0
    r_bore = max(float(geom.get("shaftBoreD", 0.0) or 0.0) / 2.0, 0.0)   # Hohlwelle (0=voll)
    if r_bore >= r_shaft - 0.5:                                          # zu groß ⇒ ignorieren
        r_bore = 0.0
    r_rot = geom["rotorOD"] / 2.0
    r_si = geom["statorID"] / 2.0
    r_so = geom["statorOD"] / 2.0
    poles = int(geom["p"]) * 2
    skew = math.radians(float(opts.get("skew_deg", 0.0)))
    box_f = float(opts.get("airbox_factor", 1.4))
    R_box = box_f * r_so
    cap = float(opts.get("cap_frac", 0.35)) * L          # axiale Luft je Seite
    mesh_cl = float(opts.get("mesh_cl", 0.0)) or max(2.0, r_so / 18.0)

    # interruptible=False: sonst ruft gmsh signal.signal() auf, was außerhalb des
    # Haupt-Threads (Flask-Worker) mit „signal only works in main thread" scheitert.
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("motor3d")
        occ = gmsh.model.occ

        # Zylinder z=0..L je Radius (Vollzylinder; fragment trennt die Ringe).
        shaft = occ.addCylinder(0, 0, 0, 0, 0, L, r_shaft)
        rotor = occ.addCylinder(0, 0, 0, 0, 0, L, r_rot)
        statI = occ.addCylinder(0, 0, 0, 0, 0, L, r_si)
        statO = occ.addCylinder(0, 0, 0, 0, 0, L, r_so)
        box = occ.addCylinder(0, 0, -cap, 0, 0, L + 2 * cap, R_box)
        # Hohlwelle: Bohrzylinder mit in die Welle fragmentieren → Innenraum wird LUFT
        # (per Radius klassifiziert). r_bore=0 ⇒ Vollwelle (kein Zusatzzylinder).
        bore = occ.addCylinder(0, 0, 0, 0, 0, L, r_bore) if r_bore > 0 else None

        # Magnete als Loft zwischen unterem und (um den Skew-Winkel gedrehtem) oberem
        # Querschnitt-Rechteck. OCC kennt kein twist → addThruSections; Skew=0 ⇒ Prisma.
        def _rect_loop(cx, cy, z, ang, Lm, Tm):
            cs, sn = math.cos(ang), math.sin(ang)
            pts = []
            for ux, uy in ((-Lm / 2, -Tm / 2), (Lm / 2, -Tm / 2),
                           (Lm / 2, Tm / 2), (-Lm / 2, Tm / 2)):
                px = cx + ux * cs - uy * sn
                py = cy + ux * sn + uy * cs
                pts.append(occ.addPoint(px, py, z))
            ls = [occ.addLine(pts[k], pts[(k + 1) % 4]) for k in range(4)]
            return occ.addCurveLoop(ls)

        # Prisma-Builder (für Magnete UND Flussbarrieren): Loft zwischen unterem und
        # oberem Querschnitt; n_seg≥2 = gerades, gestaffelt verdrehtes Segment, sonst
        # kontinuierlicher skew-Twist.
        def _extrude(pc):
            if n_seg >= 2:
                w0 = _rect_loop(pc["cx"], pc["cy"], pc["z0"], pc["ang"], pc["length"], pc["thick"])
                w1 = _rect_loop(pc["cx"], pc["cy"], pc["z1"], pc["ang"], pc["length"], pc["thick"])
            else:
                w0 = _rect_loop(pc["cx"], pc["cy"], 0.0, pc["ang"], pc["length"], pc["thick"])
                w1 = _rect_loop(pc["cx"], pc["cy"], L, pc["ang"] + skew, pc["length"], pc["thick"])
            sec = occ.addThruSections([w0, w1], -1, True, True)   # makeSolid, ruled
            vol = [d for d in sec if d[0] == 3]
            return vol[0][1] if vol else None

        # Obround/Langloch-Querschnitt (Rechteck Lm×Tm + zwei Halbkreis-Enden, Radius Tm/2+clr,
        # Flanken um clr aufgeweitet) als geschlossene Kurvenschleife auf Höhe z, um `ang` gedreht
        # und nach (cx,cy) verschoben — für die Magnet-Luft-Tasche (Klebespalt clr rundum). Zwei
        # solche Loops → Loft (addThruSections) ergibt die Tasche; kein Bool'scher Schnitt (PLC-robust).
        def _obround_loop(cx, cy, z, ang, Lm, Tm, clr, narc=7):
            cs, sn = math.cos(ang), math.sin(ang)
            rc = Tm / 2.0 + clr                                   # Halbkreis-Radius (Endkappe)
            hl = Lm / 2.0                                         # halbe Gerade (Kappenzentren ±hl)

            def _P(u, v):                                         # lokal (u längs, v quer) → global
                return occ.addPoint(cx + u * cs - v * sn, cy + u * sn + v * cs, z)
            pts = []
            for k in range(narc + 1):                            # rechte Kappe: Zentrum (+hl,0), −90°..+90°
                th = -math.pi / 2 + math.pi * k / narc
                pts.append(_P(hl + rc * math.cos(th), rc * math.sin(th)))
            for k in range(narc + 1):                            # linke Kappe: Zentrum (−hl,0), +90°..+270°
                th = math.pi / 2 + math.pi * k / narc
                pts.append(_P(-hl + rc * math.cos(th), rc * math.sin(th)))
            ls = [occ.addLine(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))]
            return occ.addCurveLoop(ls)

        def _obround_pocket(loops):
            sec = occ.addThruSections(loops, -1, True, True)      # makeSolid, ruled
            return [t for (d, t) in sec if d == 3]

        # Gerades Vollprisma 0..L (für Statornuten: die rotieren NICHT mit dem Rotor mit).
        def _extrude_straight(pc):
            w0 = _rect_loop(pc["cx"], pc["cy"], 0.0, pc["ang"], pc["length"], pc["thick"])
            w1 = _rect_loop(pc["cx"], pc["cy"], L, pc["ang"], pc["length"], pc["thick"])
            sec = occ.addThruSections([w0, w1], -1, True, True)
            vol = [d for d in sec if d[0] == 3]
            return vol[0][1] if vol else None

        rects = magnet_rects(geom)
        # KONTINUIERLICHER SKEW → FEINE STAFFELUNG, sobald Magnettaschen aktiv sind. Ein um den
        # EIGENEN Schwerpunkt tordiertes Magnet+Tasche-Paar ist nicht robust netzbar (die tordierte
        # dünne Schale bringt mesh.generate zum Scheitern; getestet). Als K gerade, um die WELLENACHSE
        # verdrehte Segmente (echte Staffelung) sind je für sich netzbar UND physikalisch korrekter
        # (reale Schrägung dreht den Querschnitt um die Wellenachse, nicht um den Magnetschwerpunkt).
        # K so fein, dass die Stufe ≤ 2° bleibt. Ohne Taschen bleibt der kontinuierliche Twist.
        _opts_eff = opts
        if (opts.get("mag_pockets", True) and int(opts.get("skew_segments", 1) or 1) < 2
                and abs(math.degrees(skew)) > 1e-6):
            _K = max(3, min(12, int(math.ceil(abs(math.degrees(skew)) / 3.0))))
            _opts_eff = dict(opts, skew_segments=_K, skew_step_deg=math.degrees(skew) / _K,
                             skew_deg=0.0)
            skew = 0.0                                     # Magnet-Extrude nutzt jetzt die Segmentebenen
        # Gestaffelte Schrägung: jeden Magneten in K verdrehte axiale Prismen schneiden.
        pieces, n_seg, _seg_step = _magnet_pieces(rects, L, _opts_eff)
        mag_vol_tags = [_extrude(pc) for pc in pieces]

        # Flussbarrieren (parametrisch q/d + custom) als LUFT-Prismen, mit der gleichen
        # Staffelung (rotieren mit dem Blechpaket). Werden in den Rotor gefragmentet.
        brects = barrier_rects(geom)
        bpieces, _bn, _bs = _magnet_pieces(brects, L, _opts_eff)
        bar_vol_tags = [_extrude(pc) for pc in bpieces]

        # Magnettaschen: EIN einheitliches Luft-LANGLOCH (obround: Rechteck + zwei Halbkreis-Enden)
        # um jeden vergrabenen Magneten, mit dem ECHTEN Geometrie-Tab-Klebespalt `clr` (magGapMm,
        # 0,1–0,3 mm) rundum — in ALLEN Fällen (gerade, Staffelung, Skew). Zwei Baufälle:
        #   • GERADE: EIN obround-Prisma über 0..L (Langloch mit Spalt rundum).
        #   • STAFFELUNG (n_seg≥2 — echte Staffel ODER der aus kontinuierlichem Skew übersetzte Fall):
        #     K GESTUFTE obround-Prismen, eins je Segment k, über die Länge versetzt (Winkel ang+k·step,
        #     Zentrum um die Wellenachse gedreht) — und dann PER MAGNET zu EINEM zusammenhängenden
        #     Luftkanal `occ.fuse`t. Magnetsegment + Tasche teilen exakt den Stufenwinkel → perfekter
        #     Sitz mit echtem Spalt.
        # **Warum fusen (wichtig, nicht rückgängig machen):** K SEPARATE gestufte Taschen lassen
        # zwischen den verdreht gestapelten Prismen dünne EISEN-Slivers stehen → entartete Tets →
        # `mesh.generate` scheitert / explodiert (>400 k Knoten). Deshalb wurde der Spalt früher
        # netzbarkeitshalber auf ~0,55·Twist-Versatz ANGEHOBEN (der Magnet füllte dann optisch das
        # Langloch, kein sichtbarer Luftspalt — genau die Nutzer-Beanstandung). Der Fuse zu EINEM
        # Kanal je Magnet beseitigt die Eisen-Slivers → der ECHTE 0,1–0,3-mm-Spalt ist netzbar
        # (verifiziert: 16 Kanäle, 5 Segmente, minSICN ~7e-3, ~76 k Knoten). Das Netz löst den dünnen
        # Spalt über `Mesh.MeshSizeMin ≈ 0,8·clr` auf (s. u.); der Knoten-Cap vergröbert nur das Fernfeld.
        # Nur vergrabene (interior) Magnete; Oberflächen-/Halbach-Magnete haben keine Tasche.
        # (Alt-Variablennamen cap_* bleiben → Luft-/Feinzonen-/Zuordnungslogik greift unverändert.)
        cap_vol_tags = []
        cap_pieces = []
        _pocket_clr = 0.0
        _pocket_clr_geom = 0.0
        _staffel = n_seg >= 2 and abs(_seg_step) > 1e-9   # echte Staffel ODER aus Skew übersetzt
        if opts.get("mag_pockets", True):
            clr = min(0.3, max(0.1, float(geom.get("magGapMm", 0.1) or 0.1)))   # Geometrie-Tab-Klebespalt
            if float(opts.get("mag_clear_mm", 0.0) or 0.0) > 0:
                clr = float(opts["mag_clear_mm"])                                # optionaler Override
            _pocket_clr_geom = clr
            _pocket_clr = clr                                                    # KEIN Anheben mehr

            def _shell_pred(Lm, Tm, dz):                 # erwartete Luft-Schalenmasse (Tasche − Magnet)
                rc = Tm / 2.0 + clr
                pocket = Lm * (Tm + 2 * clr) + math.pi * rc * rc                 # Stadion-Querschnitt
                return max(0.0, pocket - Lm * Tm) * dz

            def _pocket_prism(cx, cy, ang, z0, z1, Lm, Tm):
                l0 = _obround_loop(cx, cy, z0, ang, Lm, Tm, clr)
                l1 = _obround_loop(cx, cy, z1, ang, Lm, Tm, clr)
                return [(3, _t) for _t in _obround_pocket([l0, l1])]

            for _r in rects:
                if _r.get("placement", "interior") != "interior":
                    continue
                _Lm, _Tm, _a0 = _r["length"], _r["thick"], _r["ang"]
                try:
                    if _staffel:                          # gestufte obround-Prismen je Segment, dann fusen
                        # (kontinuierlicher Skew wurde oben in eine feine Staffelung übersetzt.)
                        segs, cxs, cys = [], [], []
                        _dz = L / n_seg
                        _eps = _dz * 0.02                 # winzige z-Überlappung → benachbarte Segmente fusen sauber
                        for k in range(n_seg):
                            phi = k * _seg_step
                            _c, _s = math.cos(phi), math.sin(phi)
                            gx = _r["cx"] * _c - _r["cy"] * _s
                            gy = _r["cx"] * _s + _r["cy"] * _c
                            segs += _pocket_prism(gx, gy, _a0 + phi, max(0.0, k * _dz - _eps),
                                                  min(L, (k + 1) * _dz + _eps), _Lm, _Tm)
                            cxs.append(gx); cys.append(gy)
                        if not segs:
                            continue
                        if len(segs) > 1:                 # zu EINEM Luftkanal je Magnet vereinen (keine Eisen-Slivers)
                            fused, _ = occ.fuse([segs[0]], segs[1:])
                            chan = [t for (d, t) in fused if d == 3]
                        else:
                            chan = [t for (d, t) in segs]
                        cap_vol_tags += chan
                        cap_pieces.append({"cx": sum(cxs) / len(cxs), "cy": sum(cys) / len(cys),
                                           "length": _Lm + 2 * clr, "thick": _Tm + 2 * clr,
                                           "z0": 0.0, "z1": L,
                                           "vol_pred": _shell_pred(_Lm, _Tm, L)})
                    else:                                  # gerade: EIN obround-Prisma
                        prism = _pocket_prism(_r["cx"], _r["cy"], _a0, 0.0, L, _Lm, _Tm)
                        cap_vol_tags += [t for (d, t) in prism]
                        cap_pieces.append({"cx": _r["cx"], "cy": _r["cy"],
                                           "length": _Lm + 2 * clr, "thick": _Tm + 2 * clr,
                                           "z0": 0.0, "z1": L,
                                           "vol_pred": _shell_pred(_Lm, _Tm, L)})
                except Exception:
                    pass

        # Verschraubungs-/Wuchtbolzen: Durchgangslöcher (Luft) durch den Rotor an der
        # Teilkreis-Position (Anzahl = Polzahl), wie FreeCAD. Nur wenn `genBalanceBolts`.
        bolt_tags = []
        bolt_pieces = []
        if bool(geom.get("genBalanceBolts", False)):
            _TH = {"M4": 4., "M5": 5., "M6": 6., "M8": 8., "M10": 10., "M12": 12.,
                   "M16": 16., "M20": 20.}
            _bhr = (_TH.get(str(geom.get("balanceBoltThread", "M6")), 6.0) + 0.4) / 2.0
            _nb = max(2, poles)
            _bcd = float(geom.get("balanceBoltCircleD", 0) or 0)
            _bpcr = _bcd / 2.0 if _bcd > 0 else r_shaft + (r_rot - r_shaft) * 0.5
            _boff = math.radians(float(geom.get("balanceBoltOffsetDeg", 0) or 0))
            for _k in range(_nb):
                _a = _boff + _k * 2 * math.pi / _nb
                _bx, _by = _bpcr * math.cos(_a), _bpcr * math.sin(_a)
                bolt_tags.append(occ.addCylinder(_bx, _by, 0, 0, 0, L, _bhr))
                bolt_pieces.append({"cx": _bx, "cy": _by, "length": 2 * _bhr,
                                    "thick": 2 * _bhr, "z0": 0.0, "z1": L})

        # Statornuten als LUFT-Prismen (gerade, volle Länge) in den Statorring fragmentieren
        # → echte Zähne. Standardmäßig an (kann per opts `stator_slots=False` aus).
        srects = slot_rects(geom) if opts.get("stator_slots", True) else []
        slot_pieces = [{**r, "z0": 0.0, "z1": L} for r in srects]
        slot_vol_tags = [_extrude_straight(pc) for pc in slot_pieces]

        # Stirnring-Leiter (Wickelkopf, vereinfacht): zwei Luft-Ringe AM Nut-Radiusband direkt
        # an den Stirnseiten (z∈[−t,0] und [L,L+t]). Sie verbinden die Nutstäbe → der
        # eingeprägte Nutstrom kann sich azimutal schließen (Σ axial = 0). Nur im Lastfall mit
        # Stromeinprägung gebaut. „Einfach": nur EIN Stromweg muss durch.
        want_rings = (bool(opts.get("coil_currents", True))
                      and str(opts.get("excitation", "open_circuit")) == "loaded"
                      and bool(srects))
        ring_tags = []
        _ring_t = 0.0
        if want_rings:
            slot_d = float(srects[0]["length"])
            t_ring = max(2.0, min(0.30 * cap, 0.6 * slot_d, 12.0))
            _ring_t = t_ring
            r_in_ring, r_out_ring = r_si, r_si + slot_d
            for z0r in (-t_ring, L):                       # unten + oben
                ro = occ.addCylinder(0, 0, z0r, 0, 0, t_ring, r_out_ring)
                ri = occ.addCylinder(0, 0, z0r, 0, 0, t_ring, r_in_ring)
                cutres, _ = occ.cut([(3, ro)], [(3, ri)])
                for (d, t) in cutres:
                    if d == 3:
                        ring_tags.append(t)

        occ.synchronize()
        all_in = [(3, shaft), (3, rotor), (3, statI), (3, statO), (3, box)] \
            + ([(3, bore)] if bore is not None else []) \
            + [(3, t) for t in mag_vol_tags if t is not None] \
            + [(3, t) for t in bar_vol_tags if t is not None] \
            + [(3, t) for t in cap_vol_tags if t is not None] \
            + [(3, t) for t in bolt_tags if t is not None] \
            + [(3, t) for t in slot_vol_tags if t is not None] \
            + [(3, t) for t in ring_tags]
        occ.fragment(all_in, [])
        occ.synchronize()

        # ── Magnete + Barrieren PER GEOMETRIE identifizieren (vor dem Vernetzen, für
        #    die zonale Verfeinerung brauchen wir ihre Oberflächen). Match über exakten
        #    Volumenschwerpunkt + Massengate (Eisen-Bulk viel größer, Slivers kleiner).
        _assign = _assign_pieces                            # (Modul-Ebene, unit-testbar)

        vinfo = []
        for (_d, v) in gmsh.model.getEntities(3):
            try:
                gx, gy, gz = gmsh.model.occ.getCenterOfMass(3, v)
                vmass = gmsh.model.occ.getMass(3, v)
            except Exception:
                gx = gy = gz = 1e9; vmass = 1e18
            vinfo.append((v, gx, gy, gz, vmass))

        mag_assign, mag_taken = _assign(pieces, vinfo, single=True)
        bar_avail = [t for t in vinfo if t[0] not in mag_taken]
        bar_assign, bar_taken = _assign(bpieces, bar_avail)
        cap_avail = [t for t in vinfo if t[0] not in mag_taken and t[0] not in bar_taken]
        cap_assign, cap_taken = _assign(cap_pieces, cap_avail, dist_frac=1.0, mlo=0.1, mhi=4.0)
        bolt_avail = [t for t in vinfo if t[0] not in (mag_taken | bar_taken | cap_taken)]
        bolt_assign, bolt_taken = _assign(bolt_pieces, bolt_avail, dist_frac=1.0, mlo=0.1, mhi=4.0)
        _used = mag_taken | bar_taken | cap_taken | bolt_taken
        slot_avail = [t for t in vinfo if t[0] not in _used]
        slot_assign, slot_taken = _assign(slot_pieces, slot_avail)

        def _surfs_of(vols):
            s = set()
            for v in vols:
                try:
                    for (d, t) in gmsh.model.getBoundary([(3, v)], oriented=False, recursive=False):
                        if d == 2:
                            s.add(abs(int(t)))
                except Exception:
                    pass
            return s
        mag_vols = [v for vs in mag_assign.values() for v in vs]
        bar_vols = [v for vs in bar_assign.values() for v in vs]
        cap_vols = [v for vs in cap_assign.values() for v in vs]
        bolt_vols = [v for vs in bolt_assign.values() for v in vs]
        slot_vols = [v for vs in slot_assign.values() for v in vs]
        # Flussbarrieren, Bolzenlöcher, Statornuten in die Feinzone (mag_cl). Magnete + Magnet-
        # Taschen NUR wenn KEINE Taschen aktiv: bei aktiven Taschen grenzen Magnet- und Taschen-
        # Oberfläche an den dünnen 0,1–0,3-mm-Klebespalt — ein mm-Ziel (mag_cl) dort ist geometrie-
        # widersprüchlich („Could not recover boundary mesh"); der Spalt wird stattdessen über
        # `Mesh.MeshSizeMin ≈ 0,8·clr` + den natürlichen Größengradienten aufgelöst (verifiziert:
        # so meshen die gefusten Kanäle sauber; ein festes Feinband auf ALLEN Magnetflächen sprengt
        # dagegen die Knotenzahl / hängt).
        fine_surfs = (_surfs_of(bar_vols) | _surfs_of(bolt_vols) | _surfs_of(slot_vols))
        if not (opts.get("mag_pockets", True) and _pocket_clr > 0):
            fine_surfs |= _surfs_of(mag_vols)

        # ── Zonale Netz-Verfeinerung (einstellbar): Luftspalt+Umgebung SEHR fein
        #    (gap_cl), Magnete/Barrieren+Umgebung FEIN (mag_cl, über mag_grow auf grob
        #    auslaufend), Rest GROB (mesh_cl). Felder per Min kombiniert.
        gap = max(0.3, (r_si - r_rot))
        gap_cl = float(opts.get("gap_cl", 0.0)) or max(0.35, gap * 0.6)
        mag_cl = float(opts.get("mag_cl", 0.0)) or max(gap_cl, mesh_cl * 0.5)
        mag_grow = float(opts.get("mag_grow", 0.0)) or max(2.0, 3.0 * gap)
        fld = gmsh.model.mesh.field
        fields = []
        # Luftspalt: MathEval-Gauß-Band um r_mid.
        rmid = (r_rot + r_si) / 2.0
        wgap = max(1.0, gap * 1.5)
        u = f"((sqrt(x*x+y*y)-{rmid})/{wgap})"            # MathEval: kein ^, nur *
        f_gap = fld.add("MathEval")
        fld.setString(f_gap, "F",
                      f"{gap_cl}+{max(0.0, mesh_cl-gap_cl)}*(1-exp(-{u}*{u}))")
        fields.append(f_gap)
        # Magnete + Barrieren + Statornuten: Distance→Threshold (fein nah, grob ab mag_grow).
        if fine_surfs:
            f_dist = fld.add("Distance")
            fld.setNumbers(f_dist, "SurfacesList", [float(s) for s in fine_surfs])
            f_thr = fld.add("Threshold")
            fld.setNumber(f_thr, "InField", f_dist)
            fld.setNumber(f_thr, "SizeMin", mag_cl)
            fld.setNumber(f_thr, "SizeMax", mesh_cl)
            fld.setNumber(f_thr, "DistMin", 0.0)
            fld.setNumber(f_thr, "DistMax", mag_grow)
            fields.append(f_thr)
        # Verfeinerungsgebiet (ROI): lokale Box im VOLLmodell feiner vernetzen, danach der
        # NORMALE volle Re-Solve (kein Submodell, keine BC-Übertragung) → physikalisch exakt.
        # gmsh-Box-Feld: VIn fein im Quader, VOut grob außen, weicher Saum (Thickness). roi_cl
        # leitet sich aus gap_cl/mag_cl ab → skaliert beim Knoten-Cap-Vergröbern automatisch mit.
        roi = opts.get("roi_box")
        roi_rf = float(opts.get("roi_refine", 0.0) or 0.0)
        roi_cl = 0.0
        if roi and roi_rf > 1.0:
            base_fine = min(gap_cl, mag_cl)
            roi_cl = max(0.12, base_fine / roi_rf)
            f_box = fld.add("Box")
            fld.setNumber(f_box, "VIn", roi_cl)
            fld.setNumber(f_box, "VOut", mesh_cl)
            fld.setNumber(f_box, "XMin", float(roi["xmin"])); fld.setNumber(f_box, "XMax", float(roi["xmax"]))
            fld.setNumber(f_box, "YMin", float(roi["ymin"])); fld.setNumber(f_box, "YMax", float(roi["ymax"]))
            fld.setNumber(f_box, "ZMin", float(roi["zmin"])); fld.setNumber(f_box, "ZMax", float(roi["zmax"]))
            fld.setNumber(f_box, "Thickness", max(1.0, base_fine * 3.0))
            fields.append(f_box)
        if len(fields) > 1:
            f_min = fld.add("Min")
            fld.setNumbers(f_min, "FieldsList", [float(f) for f in fields])
            fld.setAsBackgroundMesh(f_min)
        else:
            fld.setAsBackgroundMesh(fields[0])
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        # MeshSizeMin muss den dünnen Magnet-Klebespalt (clr, 0,1–0,3 mm) auflösen dürfen — sonst
        # überbrücken zu grobe Zellen den Spalt (Slivers/Fehlschlag). Als Boden ~0,8·clr, damit der
        # ECHTE Spalt in allen Fällen (auch Staffel/Skew, jetzt gefuste Kanäle) ≥1 Zelle quer bekommt.
        _msmin = min(gap_cl, mag_cl, roi_cl) if roi_cl else min(gap_cl, mag_cl)
        if _pocket_clr > 0:
            _msmin = min(_msmin, 0.8 * _pocket_clr)
        gmsh.option.setNumber("Mesh.MeshSizeMin", _msmin)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_cl)

        # Netzqualität (erste Stufe des Selbstheil-Monitors, mesh_robust=True): robusteres 2D-
        # Verfahren (Frontal-Delaunay) + kräftigere Tetraeder-Optimierung. Ändert das Modell
        # NICHT (keine Feature entfernt), nur wie gmsh vernetzt/glättet — hilft gegen schlecht
        # geformte/überlappende Facetten an engen Stellen (Magnetkanten/Nut/Luftspalt).
        if opts.get("mesh_robust"):
            gmsh.option.setNumber("Mesh.Algorithm", 6)          # Frontal-Delaunay (robust)
            gmsh.option.setNumber("Mesh.Optimize", 1)
            gmsh.option.setNumber("Mesh.OptimizeThreshold", 0.4)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)

        # Entartete Tetraeder (Sliver, ~0 Volumen / invertiert) killen den Elmer-Löser STILL:
        # der Netzbau läuft durch, aber CalcFields wirft „LUDecomp: Matrix is singular" bzw. der
        # Jfix-Hilfslöser divergiert. Daher hier die Netzqualität prüfen und einen zu schlechten
        # Wert wie einen BAU-Fehler behandeln → der Selbstheil-Monitor (_build_mesh_capped)
        # greift und probiert Mitigationen (robustere Vernetzung → feiner → … → Staffelung aus).
        # Schwelle bewusst niedrig (nur wirklich entartete Elemente), damit gesunde Staffel-Netze
        # (min. minSICN ~1e-3) NICHT fälschlich die Leiter auslösen und Skew wegoptimiert wird.
        if not opts.get("allow_degenerate"):
            try:
                _q_thresh = float(opts.get("degenerate_sicn", 2.0e-4))
                _e3d, _etg, _ = gmsh.model.mesh.getElements(3)
                _at = [int(t) for arr in _etg for t in arr]
                if _at:
                    _qs = gmsh.model.mesh.getElementQualities(_at, "minSICN")
                    _nbad = sum(1 for q in _qs if q <= _q_thresh)
                    # Toleranz: einzelne Ausreißer sind unkritisch; erst eine RELEVANTE Zahl
                    # entarteter Tets (bzw. echt invertierte) macht den Löser singulär.
                    _ninv = sum(1 for q in _qs if q <= 0.0)
                    if _ninv > 0 or _nbad > max(20, 0.0005 * len(_at)):
                        raise _DegenerateMeshError(
                            f"{_nbad} entartete Tetraeder (minSICN≤{_q_thresh:g}, davon {_ninv} "
                            f"invertiert) — Sliver, Elmer würde still scheitern")
            except _DegenerateMeshError:
                raise
            except Exception:
                pass                                     # Qualitätsabfrage best-effort

        # Klassifikation per Element-Schwerpunkt (echter Innenpunkt): konzentrische
        # Ringe haben ihren Volumen-Schwerpunkt AUF der Achse → Radius dort untauglich.
        def _probe(v):
            try:
                _t, etags, enodes = gmsh.model.mesh.getElements(3, v)
                if not etags or len(etags[0]) == 0:
                    return None
                nn = enodes[0][:4]
                cs = [gmsh.model.mesh.getNode(int(n))[0] for n in nn]
                cx = sum(c[0] for c in cs) / len(cs)
                cy = sum(c[1] for c in cs) / len(cs)
                cz = sum(c[2] for c in cs) / len(cs)
                return cx, cy, cz
            except Exception:
                return None

        groups = {"shaft": [], "rotor": [], "stator": [], "air": [], "ring": []}
        ring_band = (r_si, r_si + float(srects[0]["length"])) if (want_rings and srects) else None
        ring_z = {}                                          # ring-Volumen → +1 (oben) / −1 (unten)
        # Barrieren + Magnettaschen-Kappen sind LUFT-Taschen im Rotor. Die Statornuten werden
        # NICHT pauschal als „air" gebündelt, sondern unten EINZELN getaggt (Lastfall-Strom).
        for v in bar_vols:
            groups["air"].append(v)
        for v in cap_vols:
            groups["air"].append(v)
        for v in bolt_vols:
            groups["air"].append(v)                         # Bolzen-Durchgangslöcher (Luft)
        for (v, gx, gy, gz, vmass) in vinfo:
            if v in (mag_taken | bar_taken | cap_taken | bolt_taken | slot_taken):
                continue                                    # Magnet/Barriere/Kappe/Bolzen/Nut schon zugeordnet
            # Ringe über einen ECHTEN Innenpunkt (Element-Schwerpunkt): konzentrische
            # Ringe haben ihren Volumenschwerpunkt auf der Achse → dort Radius untauglich.
            pr = _probe(v)
            if pr is None:
                groups["air"].append(v); continue
            cx, cy, cz = pr
            rc = math.hypot(cx, cy)
            if cz < -1e-6 or cz > L + 1e-6:
                # Stirnring-Leiter? (Nut-Radiusband außerhalb des Pakets) — sonst Luft-Kappe.
                if ring_band and ring_band[0] - 0.5 <= rc <= ring_band[1] + 0.5:
                    groups["ring"].append(v); ring_z[v] = 1 if cz > L else -1
                else:
                    groups["air"].append(v)                 # axiale Luft-Kappen
            elif r_bore > 0 and rc < r_bore:
                groups["air"].append(v)                     # Hohlwellen-Bohrung (Luft)
            elif rc <= r_shaft:
                groups["shaft"].append(v)
            elif rc < r_rot:
                groups["rotor"].append(v)                   # Rotor-Eisen (inkl. Slivers)
            elif rc < r_si:
                groups["air"].append(v)                     # Luftspalt
            elif rc < r_so:
                groups["stator"].append(v)
            else:
                groups["air"].append(v)                     # radiale Luft

        tags = {"bodies": {}, "magnets": [], "coils": [], "L": L,
                "dims": {"r_shaft": r_shaft, "r_bore": r_bore, "r_rot": r_rot, "r_si": r_si,
                         "r_so": r_so, "R_box": R_box, "cap": cap}}
        # Elmer erwartet Körper-IDs konsekutiv ab 1 (sonst „Body 1 missing"); die
        # Bauteile zuerst (Volumen-Body-IDs 1..N), die Außenrand-Surface danach.
        pid = [1]

        def _phys(dim, ents, name):
            g = gmsh.model.addPhysicalGroup(dim, ents, pid[0]); pid[0] += 1
            gmsh.model.setPhysicalName(dim, g, name)
            return g

        # Entity→Bauteil-Klasse (für die 3D-Visualisierung über CellEntityIds).
        vol_class, mag_pol = {}, {}
        for name in ("shaft", "rotor", "stator", "air"):
            if groups[name]:
                tags["bodies"][name] = _phys(3, groups[name], name)
            for v in groups[name]:
                vol_class[v] = name
        for i, m in enumerate(pieces):
            if not mag_assign[i]:
                continue
            nm = f"magnet_{i}"
            phys = _phys(3, mag_assign[i], nm)
            tags["magnets"].append({"name": nm, "phys": phys, "mdx": m["mdx"],
                                    "mdy": m["mdy"], "sign": m["sign"], "pole": m["pole"]})
            for v in mag_assign[i]:
                vol_class[v] = "magnet"
                mag_pol[v] = 1 if m["sign"] > 0 else -1
        # Statornuten als EINZELNE Körper (Material Luft; im Lastfall Träger der
        # Stromdichte). Slot-Stück i ⇒ Nut-Index s=i (slot_rects baut s in Reihenfolge).
        for i, sp in enumerate(slot_pieces):
            if not slot_assign[i]:
                continue
            nm = f"slot_{i}"
            phys = _phys(3, slot_assign[i], nm)
            tags["coils"].append({"name": nm, "phys": phys, "s": i,
                                  "cx": sp["cx"], "cy": sp["cy"],
                                  "length": sp["length"], "thick": sp["thick"]})
            for v in slot_assign[i]:
                vol_class[v] = "coil"
        # Stirnring-Leiter (oben/unten) je als eigener Körper (Material Luft; im Lastfall
        # azimutale Rückführ-Stromdichte). z_sign = +1 oben (z>L) / −1 unten (z<0).
        tags["coil_rings"] = []
        for zs, label in ((1, "ringtop"), (-1, "ringbot")):
            rv = [v for v in groups["ring"] if ring_z.get(v) == zs]
            if rv:
                phys = _phys(3, rv, label)
                tags["coil_rings"].append({"name": label, "phys": phys, "z_sign": zs})
                for v in rv:
                    vol_class[v] = "coil"
        tags["vol_class"] = vol_class
        tags["mag_pol"] = mag_pol
        tags["ring_t"] = _ring_t

        # Außenrand (Box-Mantel + axiale Stirnflächen) als Physical-Surface für die BC.
        bxf = []
        for (_d, f) in gmsh.model.getEntities(2):
            cx, cy, cz = gmsh.model.occ.getCenterOfMass(2, f)
            if math.hypot(cx, cy) > R_box - 1e-3 or cz < -cap + 1e-3 or cz > L + cap - 1e-3:
                bxf.append(f)
        if bxf:
            tags["boundary"] = _phys(2, bxf, "outer")

        gmsh.write(msh_path)
        # Zusätzlich als VTK für die 3D-Visualisierung (trägt CellEntityIds).
        vtk_path = msh_path.rsplit(".", 1)[0] + ".vtk"
        try:
            gmsh.write(vtk_path)
            tags["vtk_mesh"] = vtk_path
        except Exception:
            pass
        tags["n_nodes"] = len(gmsh.model.mesh.getNodes()[0])
        tags["n_magnets"] = len(tags["magnets"])
        tags["n_barriers"] = len(bar_vols)
        tags["n_slots"] = len(slot_vols)
        # Magnettaschen ZÄHLEN, nicht nur anfordern. `mag_pockets=True` sagt nur, dass sie
        # GEBAUT werden sollten — ob die Luft-Schalen die Schwerpunkt-/Massenzuordnung
        # (`_assign_pieces`) überlebt haben, steht erst hier fest. Ohne diesen Zähler ist
        # „waren die Taschen überhaupt im Netz?" aus dem Logfile nicht beantwortbar (genau
        # diese Frage kam aus dem Betrieb): das Log meldete `pockets=True`, während die
        # Taschen längst über den Fallback in `build_mesh` abgeschaltet waren.
        tags["n_pockets"] = len(cap_vols)
        tags["n_pockets_want"] = len(cap_pieces)
        tags["mag_pockets_effective"] = bool(cap_vols)
        tags["n_bodies"] = {k: len(v) for k, v in groups.items()}
        tags["skew_segments"] = n_seg
        tags["skew_step_deg"] = math.degrees(_seg_step)
        tags["mesh_zones"] = {"gap_cl": gap_cl, "mag_cl": mag_cl,
                              "mesh_cl": mesh_cl, "mag_grow": mag_grow,
                              "pocket_clear": round(_pocket_clr, 2)}
        tags["pocket_clear_mm"] = round(_pocket_clr, 2)
        tags["pocket_clear_geom_mm"] = round(_pocket_clr_geom, 2)
        # Der Klebespalt entspricht jetzt in ALLEN Fällen dem Geometrie-Tab (gefuste Kanäle statt
        # angehobener Spalt) → nie mehr angehoben. Feld bleibt fürs UI/Log erhalten (immer False).
        tags["pocket_clear_raised"] = bool(_pocket_clr > _pocket_clr_geom + 1e-3)
        if roi_cl:
            tags["mesh_zones"]["roi_cl"] = roi_cl
            tags["roi_box"] = roi
        return tags
    finally:
        gmsh.finalize()


def _build_hex_mesh_once(geom: dict, axial: float, opts: dict, msh_path: str) -> dict:
    """Baut ein **Hexaeder-/Prismen-Netz** (opt-in) statt der Tetraeder von
    ``_build_mesh_once`` — strukturiert über **2D-Querschnitt + axiale Extrusion**.

    Ansatz: der Motor-Querschnitt (konzentrische Ringe + Magnete + Statornuten +
    Flussbarrieren) wird EINMAL als 2D-OCC-Fragment gebaut, zu Vierecken rekombiniert
    und axial in Schichten extrudiert (``recombine=True`` ⇒ Hexaeder/Prismen). Der
    Luftspalt wird so über wenige radial ausgerichtete Schichten mit einem Bruchteil
    der Freiheitsgrade eines Tet-Netzes aufgelöst — der eigentliche Speicher-/
    Genauigkeitsgewinn.

    - **Gerade** (kein Skew/Staffelung): EINE Extrusion 0..L, Magnete exakt in den
      Querschnitt geschnitten.
    - **Staffelung** (``skew_segments`` K≥2, bzw. kontinuierlicher ``skew_deg`` →
      feine Staffelung): K axiale Slabs, ALLE Rotationen der Magnete/Barrieren in den
      gemeinsamen 2D-Querschnitt geschnitten ⇒ jede Schicht teilt DASSELBE Basis-Netz
      (voll konform), und pro Slab wird das jeweils aktive Magnet-/Barrieren-Segment
      geometrisch (Schwerpunkt, um −φ_k rückgedreht) klassifiziert.

    **Magnet-Luft-Taschen (Langloch/obround):** wie im Tet-Pfad sitzt jeder vergrabene
    Magnet in einer obround-Luft-Tasche mit dem echten Geometrie-Tab-Klebespalt
    ``magGapMm`` (0,1–0,3 mm) rundum — im 2D-Querschnitt werden Tasche (magnet+clr) UND
    Magnet exakt geschnitten, der Ring dazwischen wird als Luft klassifiziert
    (``_use_pockets``, gated über ``mag_pockets``). ``Mesh.MeshSizeMin ≈ 0,8·clr`` löst
    den dünnen Ring auf. **v1-Scope-Grenze (bewusst, ggü. dem Tet-Pfad):** KEINE
    Stirnring-Leiter/Spulenstrom-Einprägung (Lastfeld) — Hex ist der Leerlauf-/
    Feldvisualisierungs-Pfad. Der Aufrufer (``build_mesh``) fällt bei Lastfeld-Bedarf
    auf Tet zurück. Elmer braucht auf Hex/Prisma die Piola-Transformation (``write_sif``
    setzt sie via ``tags["mesh_kind"]=="hex"``).

    Returns dieselbe ``tags``-Struktur wie ``_build_mesh_once`` (+ ``mesh_kind``).
    """
    import gmsh

    L = float(axial)
    r_shaft = geom["shaftD"] / 2.0
    r_bore = max(float(geom.get("shaftBoreD", 0.0) or 0.0) / 2.0, 0.0)
    if r_bore >= r_shaft - 0.5:
        r_bore = 0.0
    r_rot = geom["rotorOD"] / 2.0
    r_si = geom["statorID"] / 2.0
    r_so = geom["statorOD"] / 2.0
    box_f = float(opts.get("airbox_factor", 1.4))
    R_box = box_f * r_so
    cap = float(opts.get("cap_frac", 0.35)) * L
    mesh_cl = float(opts.get("mesh_cl", 0.0)) or max(2.0, r_so / 18.0)
    gap = max(0.3, (r_si - r_rot))
    gap_cl = float(opts.get("gap_cl", 0.0)) or max(0.35, gap * 0.6)
    mag_cl = float(opts.get("mag_cl", 0.0)) or max(gap_cl, mesh_cl * 0.5)

    # Skew/Staffelung → K Slabs. Kontinuierlicher Skew wird (wie im Tet-Pfad) in eine
    # feine Staffelung um die Wellenachse übersetzt (Extrusion ist je Slab gerade).
    skew = math.radians(float(opts.get("skew_deg", 0.0)))
    K = max(1, int(opts.get("skew_segments", 1) or 1))
    step = math.radians(float(opts.get("skew_step_deg", 0.0) or 0.0))
    if K < 2 and abs(math.degrees(skew)) > 1e-6:
        K = max(3, min(12, int(math.ceil(abs(math.degrees(skew)) / 3.0))))
        step = skew / K
    if K < 2:
        step = 0.0

    rects = magnet_rects(geom)
    brects = barrier_rects(geom)
    srects = slot_rects(geom)

    # Magnet-Luft-Tasche (Langloch/obround mit Klebespalt clr rundum) auch im Hex-Netz —
    # wie im Tet-Pfad der echte Geometrie-Tab-Spalt magGapMm (0,1–0,3 mm). Nur vergrabene
    # (interior) Magnete; Oberflächenmagnete (SPM/Halbach) haben keinen Klebespalt.
    _pockets = bool(opts.get("mag_pockets", True))
    clr = min(0.3, max(0.1, float(geom.get("magGapMm", 0.1) or 0.1)))
    if opts.get("mag_clear_mm"):
        clr = float(opts["mag_clear_mm"])
    _interior = [m for m in rects if m.get("placement") != "surface"]

    def _in_rect(px, py, m, eps=1e-6):
        c, s = math.cos(m["ang"]), math.sin(m["ang"])
        ux = (px - m["cx"]) * c + (py - m["cy"]) * s
        uy = -(px - m["cx"]) * s + (py - m["cy"]) * c
        return abs(ux) <= m["length"] / 2.0 + eps and abs(uy) <= m["thick"] / 2.0 + eps

    def _in_obround(px, py, m, extra):
        # Stadion-Enthaltung: Abstand des Punkts zur Mittellinie (Länge Lm entlang ang)
        # ≤ Tm/2 + extra ⇒ innerhalb des Langlochs (Rechteck + zwei Halbkreis-Enden).
        c, s = math.cos(m["ang"]), math.sin(m["ang"])
        ux = (px - m["cx"]) * c + (py - m["cy"]) * s
        uy = -(px - m["cx"]) * s + (py - m["cy"]) * c
        ux = max(-m["length"] / 2.0, min(m["length"] / 2.0, ux))   # auf die Mittellinie klemmen
        return math.hypot((px - m["cx"]) * c + (py - m["cy"]) * s - ux,
                          uy) <= m["thick"] / 2.0 + extra + 1e-6

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("motor3d_hex")
        occ = gmsh.model.occ

        # ── 2D-Querschnitt (z=0): konzentrische Scheiben + Magnete (alle K Rotationen) +
        #    Barrieren (alle K Rotationen) + Nuten (ohne Rotation) → ein Fragment.
        disks = []
        for R in (R_box, r_so, r_si, r_rot, r_shaft) + ((r_bore,) if r_bore > 0 else ()):
            disks.append((2, occ.addDisk(0, 0, 0, R, R)))

        def _rect2d(cx, cy, ang, Lm, Tm):
            c, s = math.cos(ang), math.sin(ang)
            pts = []
            for ux, uy in ((-Lm / 2, -Tm / 2), (Lm / 2, -Tm / 2),
                           (Lm / 2, Tm / 2), (-Lm / 2, Tm / 2)):
                pts.append(occ.addPoint(cx + ux * c - uy * s, cy + ux * s + uy * c, 0))
            ls = [occ.addLine(pts[k], pts[(k + 1) % 4]) for k in range(4)]
            return (2, occ.addPlaneSurface([occ.addCurveLoop(ls)]))

        def _obround2d(cx, cy, ang, Lm, Tm, extra, narc=6):
            # Langloch-Fläche (Stadion): Rechteck Lm×Tm + zwei Halbkreis-Enden, Radius Tm/2+extra,
            # Flanken um extra aufgeweitet — die Luft-Tasche um den Magneten (Klebespalt rundum).
            c, s = math.cos(ang), math.sin(ang)
            rc = Tm / 2.0 + extra
            hl = Lm / 2.0
            pts = []

            def _P(u, v):
                return occ.addPoint(cx + u * c - v * s, cy + u * s + v * c, 0)
            for k in range(narc + 1):                        # rechte Kappe (+hl), −90°..+90°
                th = -math.pi / 2 + math.pi * k / narc
                pts.append(_P(hl + rc * math.cos(th), rc * math.sin(th)))
            for k in range(narc + 1):                        # linke Kappe (−hl), +90°..+270°
                th = math.pi / 2 + math.pi * k / narc
                pts.append(_P(-hl + rc * math.cos(th), rc * math.sin(th)))
            ls = [occ.addLine(pts[k], pts[(k + 1) % len(pts)]) for k in range(len(pts))]
            return (2, occ.addPlaneSurface([occ.addCurveLoop(ls)]))

        cut_surfs = []
        rots = [k * step for k in range(K)] if K >= 2 else [0.0]
        _use_pockets = _pockets and clr > 0 and bool(_interior)
        for phi in rots:
            c, s = math.cos(phi), math.sin(phi)
            for m in rects:
                # Erst die Luft-Tasche (obround, magnet+clr), dann der Magnet exakt — beide ins
                # Fragment; der Ring dazwischen wird als Luft klassifiziert (sichtbarer Spalt).
                if _use_pockets and m.get("placement") != "surface":
                    cut_surfs.append(_obround2d(m["cx"] * c - m["cy"] * s,
                                                m["cx"] * s + m["cy"] * c,
                                                m["ang"] + phi, m["length"], m["thick"], clr))
                cut_surfs.append(_rect2d(m["cx"] * c - m["cy"] * s,
                                         m["cx"] * s + m["cy"] * c,
                                         m["ang"] + phi, m["length"], m["thick"]))
            for b in brects:
                cut_surfs.append(_rect2d(b["cx"] * c - b["cy"] * s,
                                         b["cx"] * s + b["cy"] * c,
                                         b["ang"] + phi, b["length"], b["thick"]))
        for sl in srects:                                    # Nuten drehen NICHT mit
            cut_surfs.append(_rect2d(sl["cx"], sl["cy"], sl["ang"], sl["length"], sl["thick"]))

        alls = disks + cut_surfs
        occ.fragment([alls[0]], alls[1:])
        occ.synchronize()
        base = [(2, t) for (d, t) in gmsh.model.getEntities(2)]

        # Zu Vierecken rekombinieren (⇒ Hexaeder bei der Extrusion; sonst Prismen).
        gmsh.option.setNumber("Mesh.RecombineAll", 1)
        gmsh.option.setNumber("Mesh.Algorithm", 8)           # Frontal-Delaunay for Quads

        # ── Axiale Extrusion: Cap unten (Luft) · K Motor-Slabs · Cap oben (Luft).
        seg_h = L / K
        nz_seg = max(1, int(round(seg_h / max(mesh_cl, 0.5))))
        nz_cap = max(2, int(round(cap / max(mesh_cl * 1.3, 0.5))))

        def _extrude_up(base_dt, dz, nz):
            occ.extrude(base_dt, 0, 0, dz, numElements=[max(1, nz)], recombine=True)
            occ.synchronize()

        def _tops_at(z):
            out = []
            for (d, t) in gmsh.model.getEntities(2):
                _cx, _cy, _cz = occ.getCenterOfMass(2, t)
                if abs(_cz - z) < 1e-4:
                    out.append((2, t))
            return out

        cur = base
        for k in range(K):
            _extrude_up(cur, seg_h, nz_seg)
            cur = _tops_at((k + 1) * seg_h)
        _extrude_up(cur, cap, nz_cap)                        # Cap oben
        _extrude_up(base, -cap, nz_cap)                      # Cap unten
        occ.synchronize()

        # Zonale 2D-Verfeinerung (Luftspalt sehr fein, Magnete/Nuten fein).
        fld = gmsh.model.mesh.field
        rmid = (r_rot + r_si) / 2.0
        wgap = max(1.0, gap * 1.5)
        u = f"((sqrt(x*x+y*y)-{rmid})/{wgap})"
        f_gap = fld.add("MathEval")
        fld.setString(f_gap, "F", f"{gap_cl}+{max(0.0, mesh_cl-gap_cl)}*(1-exp(-{u}*{u}))")
        fld.setAsBackgroundMesh(f_gap)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        # MeshSizeMin muss den dünnen Klebespalt (clr) auflösen dürfen (≥1 Zelle quer) — Boden
        # ~0,8·clr, wie im Tet-Pfad; sonst überbrücken zu grobe Quads den Luftring.
        _msmin = min(gap_cl, mag_cl)
        if _use_pockets:
            _msmin = min(_msmin, 0.8 * clr)
        gmsh.option.setNumber("Mesh.MeshSizeMin", _msmin)
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_cl)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)

        # ── Klassifikation je Volumen über den Element-Schwerpunkt (radius + z + Slab-Rotation).
        def _probe(v):
            _t, etags, enodes = gmsh.model.mesh.getElements(3, v)
            if not etags or len(etags[0]) == 0:
                return None
            nn = enodes[0][:8]                               # Hex: 8 Knoten (Prisma: 6, reicht auch)
            cs = [gmsh.model.mesh.getNode(int(n))[0] for n in nn]
            return (sum(c[0] for c in cs) / len(cs),
                    sum(c[1] for c in cs) / len(cs),
                    sum(c[2] for c in cs) / len(cs))

        groups = {"shaft": [], "rotor": [], "stator": [], "air": []}
        mag_groups = {}                                      # (mi,k) → {vols, mdx, mdy, sign, pole}
        for (_d, v) in gmsh.model.getEntities(3):
            pr = _probe(v)
            if pr is None:
                continue
            cx, cy, cz = pr
            rc = math.hypot(cx, cy)
            if cz < -1e-6 or cz > L + 1e-6:
                groups["air"].append(v); continue            # axiale Luft-Kappen
            k = min(K - 1, max(0, int(cz / seg_h))) if K >= 2 else 0
            phi = k * step
            cph, sph = math.cos(phi), math.sin(phi)
            ux = cx * cph + cy * sph                         # (cx,cy) um −φ zurückdrehen
            uy = -cx * sph + cy * cph
            if r_bore > 0 and rc < r_bore:
                groups["air"].append(v)
            elif rc <= r_shaft:
                groups["shaft"].append(v)
            elif rc < r_rot:
                # Reihenfolge: Magnet exakt (innen) → sonst Luft-Tasche (obround-Ring, sichtbarer
                # Klebespalt) → sonst Flussbarriere → sonst Rotoreisen.
                mi = next((i for i, m in enumerate(rects) if _in_rect(ux, uy, m)), None)
                if mi is not None:
                    m = rects[mi]
                    g = mag_groups.setdefault((mi, k), {
                        "vols": [], "mdx": m["mdx"] * cph - m["mdy"] * sph,
                        "mdy": m["mdx"] * sph + m["mdy"] * cph,
                        "sign": m.get("sign", 0.0), "pole": m.get("pole", 0)})
                    g["vols"].append(v)
                elif _use_pockets and any(_in_obround(ux, uy, m, clr) for m in _interior):
                    groups["air"].append(v)                  # Luft-Tasche (Klebespalt um den Magneten)
                elif any(_in_rect(ux, uy, b) for b in brects):
                    groups["air"].append(v)                  # Flussbarriere (Luft)
                else:
                    groups["rotor"].append(v)
            elif rc < r_si:
                groups["air"].append(v)                      # Luftspalt
            elif rc < r_so:
                if any(_in_rect(cx, cy, sl) for sl in srects):
                    groups["air"].append(v)                  # Statornut (Luft) — dreht nicht mit
                else:
                    groups["stator"].append(v)
            else:
                groups["air"].append(v)                      # radiale Luft

        tags = {"bodies": {}, "magnets": [], "coils": [], "coil_rings": [], "L": L,
                "mesh_kind": "hex",
                "dims": {"r_shaft": r_shaft, "r_bore": r_bore, "r_rot": r_rot, "r_si": r_si,
                         "r_so": r_so, "R_box": R_box, "cap": cap}}
        pid = [1]

        def _phys(dim, ents, name):
            g = gmsh.model.addPhysicalGroup(dim, ents, pid[0]); pid[0] += 1
            gmsh.model.setPhysicalName(dim, g, name)
            return g

        vol_class, mag_pol = {}, {}
        for name in ("shaft", "rotor", "stator", "air"):
            if groups[name]:
                tags["bodies"][name] = _phys(3, groups[name], name)
            for v in groups[name]:
                vol_class[v] = name
        for (mi, k), g in sorted(mag_groups.items()):
            if not g["vols"]:
                continue
            nm = f"magnet_{mi}_{k}"
            phys = _phys(3, g["vols"], nm)
            tags["magnets"].append({"name": nm, "phys": phys, "mdx": g["mdx"],
                                    "mdy": g["mdy"], "sign": g["sign"], "pole": g["pole"]})
            for v in g["vols"]:
                vol_class[v] = "magnet"
                mag_pol[v] = 1 if g["sign"] > 0 else -1
        tags["vol_class"] = vol_class
        tags["mag_pol"] = mag_pol
        tags["ring_t"] = 0.0

        # Außenrand (Box-Mantel + Stirnflächen) als Physical-Surface für die BC.
        bxf = []
        for (_d, f) in gmsh.model.getEntities(2):
            fx, fy, fz = occ.getCenterOfMass(2, f)
            if math.hypot(fx, fy) > R_box - 1e-3 or fz < -cap + 1e-3 or fz > L + cap - 1e-3:
                bxf.append(f)
        if bxf:
            tags["boundary"] = _phys(2, bxf, "outer")

        gmsh.write(msh_path)
        vtk_path = msh_path.rsplit(".", 1)[0] + ".vtk"
        try:
            gmsh.write(vtk_path)
            tags["vtk_mesh"] = vtk_path
        except Exception:
            pass
        # Anteil echter Hexaeder (Typ 5) / Prismen (Typ 6) fürs Log/UI.
        etypes, etags2, _ = gmsh.model.mesh.getElements(3)
        n_hex = sum(len(etags2[i]) for i, t in enumerate(etypes) if t == 5)
        n_pri = sum(len(etags2[i]) for i, t in enumerate(etypes) if t == 6)
        n_tet = sum(len(etags2[i]) for i, t in enumerate(etypes) if t == 4)
        tags["n_nodes"] = len(gmsh.model.mesh.getNodes()[0])
        tags["n_magnets"] = len(tags["magnets"])
        tags["n_barriers"] = len(brects)
        tags["n_slots"] = len(srects)
        tags["n_bodies"] = {k: len(v) for k, v in groups.items()}
        tags["skew_segments"] = K
        tags["skew_step_deg"] = math.degrees(step)
        tags["hex_counts"] = {"hex": n_hex, "prism": n_pri, "tet": n_tet}
        tags["mesh_zones"] = {"gap_cl": gap_cl, "mag_cl": mag_cl, "mesh_cl": mesh_cl,
                              "mag_grow": float(opts.get("mag_grow", 0.0) or 0.0)}
        tags["pocket_clear_mm"] = round(clr, 2) if _use_pockets else 0.0
        # Im Hex-Pfad sind die Taschen Teil des 2D-Querschnitts (kein separates Volumen) —
        # gezählt wird deshalb die Zahl der vergrabenen Magnete, für die sie gebaut wurden.
        tags["n_pockets"] = len(_interior) * K if _use_pockets else 0
        tags["n_pockets_want"] = len(_interior) * K
        tags["mag_pockets_effective"] = bool(_use_pockets)
        return tags
    finally:
        gmsh.finalize()


# ── Elmer-Solver-Input (.sif) ────────────────────────────────────────────────────

def write_sif(geom: dict, opts: dict, tags: dict, work_dir: str,
              mesh_name: str = "mesh") -> str:
    """Schreibt ``case.sif`` (3D-Magnetostatik) und gibt den Pfad zurück.

    WhitneyAVSolver (Kanten-A) + MagnetoDynamicsCalcFields (B/H/Energie) +
    ResultOutputSolver (VTU). Magnete als Permanentmagnet-Magnetisierung (Br aus der
    MAGNETS-Tabelle, Richtung aus `magnet_rects`); Eisen linear μr=500; Luft μr=1.
    BC außen: A×n=0. v1 = Open-Circuit (keine Spulenströme)."""
    from ema_pipeline import MAGNETS
    mag = MAGNETS.get(geom.get("magnet", "ndfeb_n35"), MAGNETS["ndfeb_n35"])
    Hc = float(mag["Br"]) / MU0                       # Magnetisierung |M| = Br/μ0 [A/m]

    bodies = tags["bodies"]
    L = tags["L"]
    # Elmer-Ausgabepfade RELATIV zum Lauf-Verzeichnis (cwd) lassen — absolute Pfade
    # werden von Elmer mit "./" verkettet → kaputter, geschachtelter Pfad.
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)

    # ── Betriebspunkt + Lastfall mit Statorströmen (Ankerrückwirkung) ───────────────
    # `excitation=loaded` berechnet den Betriebspunkt (dq-Ströme aus rpm+Last, wie 2D) und
    # prägt — sofern `coil_currents` (Standard AN) — je Nut eine axiale Stromdichte ein
    # (i_slot = i_d·cos(elAng) − i_q·sin(elAng), J_z = C0·i_slot). Damit sich der Strom in der
    # endlichen Länge SCHLIESST, tragen zwei Stirnring-Leiter (oben/unten, `tags["coil_rings"]`)
    # den azimutalen Rückführstrom — sonst explodiert das Vektorpotential (B~10⁴ T). Nut und
    # Ring leiten aus DEMSELBEN C0 ab (Mesh-Einheiten) → ∇·J≈0; `COIL_J_SCALE` kalibriert die
    # absolute Höhe aufs analytische 2D-Ankerfeld. Vereinfacht (Grundwelle, lineares Eisen).
    coils = tags.get("coils", [])
    op_loaded = str(opts.get("excitation", "open_circuit")) == "loaded"
    inject = op_loaded and bool(coils) and bool(opts.get("coil_currents", True))
    slot_J, iq, id_, ring_info = {}, 0.0, 0.0, None
    if op_loaded:
        import ema_analysis
        rpm = float(opts.get("rpm", 0.0) or 0.0)
        load_nm = float(opts.get("load_nm", 0.0) or 0.0)
        try:
            iq, id_ = ema_analysis.estimate_dq_currents(geom, rpm, load_nm)
        except Exception:
            iq, id_ = 0.0, 0.0
        if inject:
            n_slots = max(int(geom.get("slots", len(coils)) or len(coils)), 1)
            p_pairs = int(geom.get("p", 1))
            n_cond = max(int(geom.get("conductorsPerSlot", 2) or 2), 1)
            # Nut UND Ring in KONSISTENTEN Mesh-Einheiten (mm) aus EINEM C0 ableiten → der
            # axiale Nutstrom schließt sich exakt über den azimutalen Ringstrom (∇·J≈0).
            A_slot = max(float(coils[0]["thick"]) * float(coils[0]["length"]), 1e-6)  # mm²
            C0 = COIL_J_SCALE * n_cond / A_slot
            for c in coils:
                th = c["s"] * (2 * math.pi / n_slots) * p_pairs
                slot_J[c["phys"]] = C0 * (id_ * math.cos(th) - iq * math.sin(th))    # axial
            if slot_J:                                   # Σ exakt 0 erzwingen (Jfix-fähig)
                mean = sum(slot_J.values()) / len(slot_J)
                for k in slot_J:
                    slot_J[k] -= mean
            t_ring = max(float(tags.get("ring_t", 0.0)), 1e-6)
            ring_info = {"K": C0 / (t_ring * max(p_pairs, 1)), "p": p_pairs,
                         "id": id_, "iq": iq}
    loaded = inject and bool(slot_J)
    tags["operating_point"] = {"excitation": "loaded" if op_loaded else "open_circuit",
                               "field_loaded": loaded,
                               "rpm": float(opts.get("rpm", 0.0) or 0.0),
                               "load_nm": float(opts.get("load_nm", 0.0) or 0.0),
                               "iq_A": round(iq, 1), "id_A": round(id_, 1),
                               "is_peak_A": round(math.hypot(iq, id_), 1)}

    S = []
    S.append(f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n')
    S.append("Simulation\n"
             "  Max Output Level = 4\n"
             "  Coordinate System = Cartesian\n"
             "  Simulation Type = Steady State\n"
             "  Steady State Max Iterations = 1\n"
             "  Output Intervals = 1\nEnd\n")
    S.append(f"Constants\n  Permeability of Vacuum = {MU0}\nEnd\n")

    # Solver 1: Vektorpotential (Kantenelemente), magnetostatisch.
    # Direkter Löser (MUMPS) für das curl-curl-Kantenelement-System: für kleine/mittlere
    # 3D-Modelle robust (das iterative BiCGStabL stagniert ohne aufwändige Vorkonditionierung).
    # AUSNAHME Hex/Prisma (Piola): der Direkt-Löser (mit Tree-Gauge) geht in Elmer NUR mit der
    # niedrigst-ordnigen Kantenbasis auf Simplizes — die Piola-Basis auf Hex/Prisma zählt nicht
    # dazu („Direct solver … only possible with the lowest order edge basis"). Daher im Hex-Modus
    # zwingend den ITERATIVEN Löser (BiCGStabL+ILU) nehmen.
    is_hex = tags.get("mesh_kind") == "hex"
    direct = bool(opts.get("direct", True)) and not is_hex
    if is_hex:
        # Hex/Piola OHNE Tree-Gauge: das curl-curl-Kantensystem ist symmetrisch
        # positiv-SEMI-definit (Gradienten-Nullraum) mit KONSISTENTER rechter Seite
        # (Magnetquelle = curl der Magnetisierung ⇒ im Bildraum). BiCGStabL bricht daran
        # ab (NaN „Breakdown"); CG bleibt bei x0=0 im zur Nullraum orthogonalen Krylov-
        # Unterraum und konvergiert gegen die minimum-norm-Lösung. Daher CG + ILU0.
        lin1 = ('  Linear System Solver = Iterative\n'
                '  Linear System Iterative Method = CG\n'
                '  Linear System Preconditioning = ILU0\n'
                '  Linear System Max Iterations = 8000\n'
                '  Linear System Convergence Tolerance = 1.0e-7\n'
                '  Linear System Residual Output = 100\n'
                '  Linear System Abort Not Converged = False\n')
    elif direct:
        lin1 = ('  Linear System Solver = Direct\n'
                '  Linear System Direct Method = MUMPS\n')
    else:
        lin1 = ('  Linear System Solver = Iterative\n'
                '  Linear System Iterative Method = BiCGStabL\n'
                '  BiCGStabL Polynomial Degree = 4\n'
                '  Linear System Preconditioning = ILU1\n'
                '  Linear System Max Iterations = 8000\n'
                '  Linear System Convergence Tolerance = 1.0e-7\n'
                '  Linear System Residual Output = 100\n')
    # Jfix (Stromdichte-Bereinigung, nur Lastfall): reines (ΣJ=0-)Neumann-Poisson für ∇·J. Auf
    # GESUNDEN Netzen ist es konsistent und der iterative BiCGStabL konvergiert (~219 Iter, ILU1,
    # Nicht-Abbruch). Die vom Nutzer beobachtete DIVERGENZ („System diverged over maximum
    # tolerance") entstand NICHT hier, sondern am kaputten Staffel-Netz (Eisen-Slivers → ∇·J
    # diskret inkonsistent) — das fängt jetzt der Netz-Entartungs-Wächter oben ab, BEVOR gelöst
    # wird. Daher bewusst KEIN Direkt-Löser (MUMPS scheitert am singulären Neumann-System) und
    # KEIN `Jfix=0`-BC-Pin (in diesem Elmer ein unlistetes/wirkungsloses Keyword, s. Projekt-
    # historie) — der bewährte iterative Weg bleibt.
    jfix_cfg = ('  Jfix: Linear System Iterative Method = BiCGStabL\n'
                '  Jfix: Linear System Max Iterations = 10000\n'
                '  Jfix: Linear System Convergence Tolerance = 1.0e-6\n'
                '  Jfix: Linear System Preconditioning = ILU1\n'
                '  Jfix: Linear System Abort Not Converged = False\n') if loaded else ''
    # Piola-Transformation: curl-konforme Kantenelemente niedrigster Ordnung brauchen sie
    # auf NICHT-simpliziellen Elementen (Hexaeder/Prismen), sonst wird das Feld falsch. Auf
    # reinen Tetraeder-Netzen ist sie nicht nötig (daher nur im Hex-Modus gesetzt). WICHTIG:
    # Elmers WhitneyAVSolver verträgt „Use Tree Gauge" NICHT zusammen mit der Piola-Transform
    # („Tree Gauge cannot be used in conjunction with Piola transformation") → im Hex-Modus
    # das Tree-Gauge weglassen (die Piola-Kantenbasis bringt ihre eigene Eichung mit).
    gauge = '' if is_hex else '  Use Tree Gauge = Logical True\n'
    piola = '  Use Piola Transform = Logical True\n' if is_hex else ''
    S.append('Solver 1\n'
             '  Equation = "MgDyn"\n'
             '  Procedure = "MagnetoDynamics" "WhitneyAVSolver"\n'
             '  Variable = "AV"\n'
             '  Fix Input Current Density = ' + ('True' if loaded else 'False') + '\n'
             + gauge
             + piola
             + jfix_cfg
             + lin1 +
             '  Nonlinear System Max Iterations = 1\nEnd\n')
    # Solver 2: Felder B/H/Energie aus A.
    S.append('Solver 2\n'
             '  Equation = "MgDynCalc"\n'
             '  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"\n'
             '  Potential Variable = "AV"\n'
             '  Calculate Magnetic Field Strength = True\n'
             '  Calculate Magnetic Flux Density = True\n'
             '  Calculate Nodal Forces = True\n'
             '  Calculate Maxwell Stress = True\n'
             '  Calculate JxB = Logical True\n'
             '  Linear System Solver = Iterative\n'
             '  Linear System Iterative Method = CG\n'
             '  Linear System Preconditioning = ILU0\n'
             '  Linear System Max Iterations = 5000\n'
             '  Linear System Convergence Tolerance = 1.0e-8\nEnd\n')
    # Solver 3: VTU-Ausgabe (für vtk-Auswertung + ParaView).
    S.append('Solver 3\n'
             '  Equation = "ResultOutput"\n'
             '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
             '  Output File Name = "case"\n'
             '  Output Directory = "results"\n'
             '  Vtu Format = Logical True\n'
             '  Save Geometry Ids = Logical True\n'
             '  Discontinuous Bodies = Logical True\nEnd\n')
    # Solver 4: skalare Gesamtenergie.
    S.append('Solver 4\n'
             '  Equation = "SaveScalars"\n'
             '  Procedure = "SaveData" "SaveScalars"\n'
             '  Filename = "scalars.dat"\n'
             '  Show Norm Index = 1\nEnd\n')

    S.append("Equation 1\n  Active Solvers(2) = 1 2\nEnd\n")

    # Materialien.
    S.append(f"Material 1\n  Name = \"iron\"\n  Relative Permeability = {MU_R_IRON}\nEnd\n")
    S.append("Material 2\n  Name = \"air\"\n  Relative Permeability = 1.0\nEnd\n")
    S.append(f"Material 3\n  Name = \"magnet\"\n  Relative Permeability = {MU_R_MAG}\nEnd\n")

    # Körper: Eisen (shaft/rotor/stator), Luft, Magnete (Material 3 + Body Force).
    for name in ("shaft", "rotor", "stator"):
        if name in bodies:
            S.append(f'Body {bodies[name]}\n  Name = "{name}"\n  Equation = 1\n  Material = 1\nEnd\n')
    if "air" in bodies:
        S.append(f'Body {bodies["air"]}\n  Name = "air"\n  Equation = 1\n  Material = 2\nEnd\n')

    bf = 1
    for m in tags["magnets"]:
        mx = Hc * m["sign"] * m["mdx"]
        my = Hc * m["sign"] * m["mdy"]
        S.append(f'Body {m["phys"]}\n  Name = "{m["name"]}"\n  Equation = 1\n'
                 f'  Material = 3\n  Body Force = {bf}\nEnd\n')
        S.append(f'Body Force {bf}\n'
                 f'  Magnetization 1 = Real {mx:.6e}\n'
                 f'  Magnetization 2 = Real {my:.6e}\n'
                 f'  Magnetization 3 = Real 0.0\nEnd\n')
        bf += 1

    # Statornuten: Material Luft; im Lastfall axiale Stromdichte (Ankerrückwirkung).
    for c in coils:
        if loaded and c["phys"] in slot_J:
            S.append(f'Body {c["phys"]}\n  Name = "{c["name"]}"\n  Equation = 1\n'
                     f'  Material = 2\n  Body Force = {bf}\nEnd\n')
            S.append(f'Body Force {bf}\n  Current Density 3 = Real {slot_J[c["phys"]]:.6e}\nEnd\n')
            bf += 1
        else:
            S.append(f'Body {c["phys"]}\n  Name = "{c["name"]}"\n  Equation = 1\n  Material = 2\nEnd\n')

    # Stirnring-Leiter: azimutale Rückführ-Stromdichte (schließt den Nutstrom).
    # J_θ = z_sign·K·(i_d·sin(pθ)+i_q·cos(pθ)), θ=atan2(y,x); CD1=−y·J_θ, CD2=+x·J_θ.
    for r in tags.get("coil_rings", []):
        if loaded and ring_info:
            arg = f'{ring_info["p"]}*atan2(tx(1),tx(0))'
            amp = (f'{r["z_sign"] * ring_info["K"]:.8e}*'
                   f'({ring_info["id"]:.6e}*sin({arg})+{ring_info["iq"]:.6e}*cos({arg}))')
            S.append(f'Body {r["phys"]}\n  Name = "{r["name"]}"\n  Equation = 1\n'
                     f'  Material = 2\n  Body Force = {bf}\nEnd\n')
            S.append(f'Body Force {bf}\n'
                     f'  Current Density 1 = Variable Coordinate\n    Real MATC "-tx(1)*{amp}"\n'
                     f'  Current Density 2 = Variable Coordinate\n    Real MATC "tx(0)*{amp}"\nEnd\n')
            bf += 1
        else:
            S.append(f'Body {r["phys"]}\n  Name = "{r["name"]}"\n  Equation = 1\n  Material = 2\nEnd\n')

    # Außenrand: A×n = 0 (Fluss parallel zur weit entfernten Box). Der Jfix-Pegel wird NICHT
    # gepinnt (`Jfix=0` ist in diesem Elmer ein unlistetes Keyword) — das konsistente ΣJ=0-
    # Neumann-System löst iterativ auch ohne Pinning, solange das Netz gesund ist (Wächter oben).
    if "boundary" in tags:
        S.append(f'Boundary Condition 1\n  Target Boundaries(1) = {tags["boundary"]}\n'
                 '  AV {e} = Real 0\n  AV = Real 0\nEnd\n')

    sif_path = os.path.join(work_dir, "case.sif")
    with open(sif_path, "w") as f:
        f.write("\n".join(S))
    return sif_path


# ── Ergebnis-Auswertung (VTU via vtk + 2D-Vergleich + Charts) ────────────────────

def _find_vtu(work_dir: str) -> str | None:
    rdir = os.path.join(work_dir, "results")
    cands = []
    for base in (rdir, work_dir):
        if os.path.isdir(base):
            cands += [os.path.join(base, f) for f in os.listdir(base) if f.endswith(".vtu")]
    return max(cands, key=os.path.getmtime) if cands else None


def _read_grid(vtu_path: str):
    import vtk
    rd = vtk.vtkXMLUnstructuredGridReader()
    rd.SetFileName(vtu_path)
    rd.Update()
    return rd.GetOutput()


def _b_array_name(grid) -> str:
    pd = grid.GetPointData()
    for i in range(pd.GetNumberOfArrays()):
        nm = pd.GetArrayName(i)
        if nm and "flux density" in nm.lower():
            return nm
    # Fallback: erstes 3-komponentiges Array
    for i in range(pd.GetNumberOfArrays()):
        if pd.GetArray(i).GetNumberOfComponents() == 3:
            return pd.GetArrayName(i)
    return ""


def _probe(grid, pts, array_name):
    """B-Vektoren an den Weltkoordinaten ``pts`` (Nx3) interpolieren → (N,3) array."""
    import vtk
    from vtk.util import numpy_support as ns
    vpts = vtk.vtkPoints()
    for p in pts:
        vpts.InsertNextPoint(float(p[0]), float(p[1]), float(p[2]))
    poly = vtk.vtkPolyData(); poly.SetPoints(vpts)
    pf = vtk.vtkProbeFilter()
    pf.SetInputData(poly); pf.SetSourceData(grid); pf.Update()
    out = pf.GetOutput().GetPointData()
    arr = out.GetArray(array_name)
    if arr is None:
        return np.zeros((len(pts), 3))
    return ns.vtk_to_numpy(arr).reshape(-1, 3)


def _gap_field_metrics(grid, bname, tags) -> dict:
    """Tastet das Luftspaltfeld B(θ,z) ab → B_gap(Mitte), Endeffekt-Kurve über z und
    Arkkio-Moment. Gibt die Skalar-Kennwerte zurück PLUS (mit ``_``-Präfix) die Profil-
    Arrays ``_th``/``_br_mid``/``_z_levels_arr``, die ``parse_results`` für die Charts
    weiterverwendet. Geteilt zwischen dem vollen Einzellauf und dem schlanken Sweep-Pfad."""
    dims = tags["dims"]; L = tags["L"]
    r_mid = 0.5 * (dims["r_rot"] + dims["r_si"])
    n_th = 240
    th = np.linspace(0, 2 * np.pi, n_th, endpoint=False)
    # z-Ebenen für die Endeffekt-Kurve (0 = Stirnseite, L/2 = Mitte).
    z_levels = np.linspace(0.0, L, 11)
    br_by_z, bt_by_z = [], []
    for z in z_levels:
        pts = np.c_[r_mid * np.cos(th), r_mid * np.sin(th), np.full(n_th, z)]
        B = _probe(grid, pts, bname)
        br = B[:, 0] * np.cos(th) + B[:, 1] * np.sin(th)        # radial
        bt = -B[:, 0] * np.sin(th) + B[:, 1] * np.cos(th)       # tangential
        br_by_z.append(br); bt_by_z.append(bt)
    br_by_z = np.array(br_by_z); bt_by_z = np.array(bt_by_z)
    mid = len(z_levels) // 2
    br_mid = br_by_z[mid]
    # Moment (Arkkio-Näherung): T = (L·r²/μ0) · mean_z ∮ Br·Bθ dθ. v1 ist OPEN-CIRCUIT
    # (nur Magnete) → das Netto-Moment ist physikalisch ~0; der Wert ist am groben Netz
    # verrauscht und nur informativ. Das echte Lastmoment kommt mit den Spulenströmen.
    _trap = getattr(np, "trapezoid", None) or np.trapz   # NumPy 2.x: trapz → trapezoid
    arkkio = float(np.mean([_trap(br_by_z[i] * bt_by_z[i], th) for i in range(len(z_levels))]))
    return {
        "b_gap_mid_peak": round(float(np.max(np.abs(br_mid))), 3),
        # Plausibilitätsmarke für die Aufrufer: Eisen sättigt bei ~2 T, im Luftspalt sind
        # >3 T physikalisch ausgeschlossen. Im Lastfall dominieren die vereinfachten
        # Stirnring-Leiter das Feld nahe den Stirnseiten (gemessen an 20260812_073601:
        # 20,2 T am Rand gegen 2,4 T in der Mitte) — die „Endeffekt"-Kurve zeigt dann den
        # Ringstrom, keinen Endeffekt. Ohne diese Marke stand das kommentarlos im Diagramm.
        "b_gap_max_abs": round(float(np.max(np.abs(br_by_z))), 3),
        "b_gap_axial": [round(float(np.max(np.abs(b))), 3) for b in br_by_z],
        "z_levels": [round(float(z), 1) for z in z_levels],
        "torque_Nm": round((L * 1e-3) * (r_mid * 1e-3) ** 2 / MU0 * arkkio, 2),
        "torque_note": "Leerlauf (nur Magnete) ⇒ Netto-Moment ≈ 0; Lastfall folgt",
        "_th": th, "_br_mid": br_mid, "_z_levels_arr": z_levels,
    }


def _orientation_check(th2d, br2d, th3d, br3d, geom, tags, res) -> dict:
    """Prüft, ob die Magnetorientierung von 3D-Elmer und 2D-FDM ÜBEREINSTIMMT.

    Beide Löser leiten die Magnetisierung aus derselben Quelle ab (`ema_topology.magnet_legs`
    → `_rasterise` bzw. `magnet_rects`), aber an zwei Stellen können sie auseinanderlaufen:
    * **Rotorwinkel** — die 2D-Rasterung dreht die Pole mit ``rotor_angle``, der 3D-Pfad
      kennt keinen Rotorwinkel (das Netz sitzt immer bei 0). Der Vergleich läuft deshalb
      bei ``rotor_angle=0``; wer das 3D-Bild gegen einen ANIMATIONSFRAME hält, sieht
      zwangsläufig eine Verdrehung.
    * **Staffelung/Skew** — nur 3D. Die Mittelebene sitzt im mittleren Segment und ist
      damit um bis zu ``(K−1)·skew_step`` gegen die 2D-Lösung verdreht.

    Gemessen wird die Phase der p-ten Umfangsharmonischen von ``B_r(θ)`` in beiden
    Lösungen; die Differenz ist die mechanische Verdrehung der Polfolge. Alles darüber
    hinaus ist ein echter Vorzeichen-/Zuordnungsfehler und wird als Warnung gemeldet.
    """
    p = max(int(geom.get("p", 1) or 1), 1)
    _trap = getattr(np, "trapezoid", None) or np.trapz

    def _phase(th, br):
        th = np.asarray(th, float); br = np.asarray(br, float)
        c = _trap(br * np.exp(-1j * p * th), th) / math.pi
        return float(abs(c)), float(np.degrees(np.angle(c)))

    a2, ph2 = _phase(th2d, br2d)
    a3, ph3 = _phase(th3d, br3d)
    d_el = (ph3 - ph2 + 180.0) % 360.0 - 180.0
    # Vorzeichen so, dass die Zahl die GEOMETRISCHE Verdrehung ist: sitzt das 3D-Polmuster
    # um +δ weiter im Umlaufsinn (B_r ~ cos(p(θ−δ))), ist die Phase −p·δ ⇒ negieren.
    d_mech = -d_el / p
    # Erlaubte Verdrehung: die Staffelung selbst + Abtast-/Netzrauschen.
    skew_span = abs(float(tags.get("skew_step_deg", 0.0))) * max(int(tags.get("skew_segments", 1)) - 1, 0)
    tol = skew_span + 3.0
    out = {"phase_2D_deg": round(ph2, 2), "phase_3D_deg": round(ph3, 2),
           "phase_shift_mech_deg": round(d_mech, 2),
           "phase_tol_mech_deg": round(tol, 2),
           "orientation_ok": bool(abs(d_mech) <= tol),
           "fundamental_2D": round(a2, 4), "fundamental_3D": round(a3, 4)}
    if not out["orientation_ok"]:
        res.setdefault("warnings", []).append(
            f"Magnetorientierung 3D gegen 2D-FDM um {d_mech:+.1f}° mechanisch verdreht "
            f"(zulässig ±{tol:.1f}° aus der Staffelung). Beide Lösungen stehen bei "
            f"rotor_angle=0 — eine größere Verdrehung ist ein Modellfehler, kein Animationsversatz.")
    elif abs(d_mech) > 0.5:
        res.setdefault("warnings", []).append(
            f"Magnetorientierung 3D/2D stimmt überein (Versatz {d_mech:+.1f}° mechanisch, "
            f"erklärt durch die Staffelung {tags.get('skew_segments', 1)}×"
            f"{tags.get('skew_step_deg', 0.0):.1f}°, die es nur im 3D-Modell gibt).")
    return out


def _gap_metrics_only(work_dir: str, geom: dict, opts: dict, tags: dict) -> dict:
    """Schlanke Kennwerte (B_gap, Endeffekt, Moment) aus der VTU — OHNE Charts/VTU/VTP-
    Export. Für die Sweep-Betriebspunkte, die NICHT der Detailpunkt sind."""
    res = {"warnings": []}
    vtu = _find_vtu(work_dir)
    if not vtu:
        res["warnings"].append("Keine VTU-Ausgabe von Elmer gefunden.")
        return res
    grid = _read_grid(vtu)
    bname = _b_array_name(grid)
    if not bname:
        res["warnings"].append("Kein B-Feld in der VTU.")
        return res
    m = _gap_field_metrics(grid, bname, tags)
    for k in ("_th", "_br_mid", "_z_levels_arr"):
        m.pop(k, None)
    res.update(m)
    _b_gap_plausibility(res, tags)
    return res


def _b_gap_plausibility(res: dict, tags: dict) -> None:
    """Warnt, wenn das ausgewertete Luftspaltfeld physikalisch unmöglich ist.

    Eisen sättigt bei ~2 T; alles über ~3 T im Luftspalt kann nur aus dem Modell kommen,
    nicht aus der Maschine. Im Lastfall sind das die vereinfachten Stirnring-Leiter
    (`COIL_J_SCALE`, an EINER Maschine kalibriert): sie sitzen als Luft-Ringe direkt an den
    Stirnseiten und überstrahlen dort das Maschinenfeld. Gemessen am Lauf 20260812_073601:
    20,2 T an der Stirnseite gegen 2,4 T in der Mitte, mit 180°-Phasensprung zwischen den
    Hälften (die beiden Ringe führen gegensinnigen Umfangsstrom) — die „Endeffekt"-Kurve
    zeigt dann den Ringstrom, keinen Endeffekt. Das stand bisher kommentarlos im Diagramm."""
    b_max = float(res.get("b_gap_max_abs") or res.get("b_gap_mid_peak") or 0.0)
    if b_max <= 3.0:
        return
    op = tags.get("operating_point") or {}
    mid = float(res.get("b_gap_mid_peak") or 0.0)
    txt = (f"Luftspaltfeld unphysikalisch hoch: {b_max:.1f} T (Eisen sättigt bei ~2 T). ")
    if op.get("field_loaded"):
        txt += ("Ursache ist der vereinfachte Stirnring-Leiter des Lastfalls, der nahe den "
                f"Stirnseiten dominiert (Mitte {mid:.1f} T). Die Endeffekt-Kurve zeigt dort "
                "den Ringstrom, nicht den Endeffekt — für Vergleiche nur die Mittelebene "
                "verwenden, oder im Leerlauf rechnen.")
    else:
        txt += "Prüfen: Magnetisierung, Netz und Materialzuordnung."
    res.setdefault("warnings", []).append(txt)


def parse_results(work_dir: str, geom: dict, opts: dict, tags: dict,
                  project_dir: str) -> dict:
    """VTU → Luftspalt-B(θ,z), Endeffekt-Kurve, Schnittbild, Moment (Arkkio) +
    2D-Vergleich. Schreibt Charts nach ``project_dir/charts`` (base64 + Datei)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64, io

    dims = tags["dims"]; L = tags["L"]
    res = {"skew_deg": float(opts.get("skew_deg", 0.0)), "warnings": []}

    vtu = _find_vtu(work_dir)
    if not vtu:
        res["warnings"].append("Keine VTU-Ausgabe von Elmer gefunden.")
        return res
    res["vtu_path"] = vtu
    grid = _read_grid(vtu)
    bname = _b_array_name(grid)
    if not bname:
        res["warnings"].append("Kein B-Feld in der VTU.")
        return res

    # Luftspalt-B(θ,z) → B_gap(Mitte), Endeffekt-Kurve, Arkkio-Moment (geteilt mit dem
    # schlanken Sweep-Pfad; gibt zusätzlich die Profil-Arrays für die Charts zurück).
    m = _gap_field_metrics(grid, bname, tags)
    th = m.pop("_th"); br_mid = m.pop("_br_mid"); z_levels = m.pop("_z_levels_arr")
    res.update(m)
    _b_gap_plausibility(res, tags)

    charts = os.path.join(project_dir, "charts")
    os.makedirs(charts, exist_ok=True)

    def _save(fig, name):
        buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                                        facecolor="#0d0d0d")
        plt.close(fig)
        return _save_bytes(buf.getvalue(), name)

    def _save_bytes(data, name):
        with open(os.path.join(charts, name), "wb") as f:
            f.write(data)
        return "data:image/png;base64," + base64.b64encode(data).decode()

    images = []

    # Echte 3D-Ansichten (vtk offscreen): Modell + aufgeschnittenes Feld.
    try:
        images.extend(render_geometry_3d(tags, _save_bytes))
        images.append(render_field_3d(grid, bname, tags, _save_bytes))
    except Exception as e:
        res["warnings"].append(f"3D-Rendering fehlgeschlagen: {e}")

    # 2D-Vergleich: Luftspalt-Br 2D (FDM) vs 3D (Mitte).
    import ema_analysis
    cmp2d = {}
    try:
        # GLEICHER BETRIEBSPUNKT wie der 3D-Lauf. Vorher lief der Vergleich immer im
        # LEERLAUF gegen ein 3D-Lastfeld — B_gap_2D=0,629 T gegen B_gap_3D=2,401 T sind so
        # gar nicht vergleichbar, und die beiden Kurven landeten trotzdem in einem Bild.
        # Im Lastfall braucht `run_em_analysis` den Leerlauf-`sf_ref`, sonst kalibriert es
        # sich auf den eigenen Spitzenwert und wirft die Ankerrückwirkung wieder heraus.
        _n2d = int(opts.get("n2d", 360))
        _op = tags.get("operating_point") or {}
        _ld = bool(_op.get("field_loaded"))
        _oc = ema_analysis.run_em_analysis(geom, N=_n2d, rotor_angle=0.0)
        if _ld:
            em2d = ema_analysis.run_em_analysis(
                geom, N=_n2d, rotor_angle=0.0, iq=float(_op.get("iq_A") or 0.0),
                id_=float(_op.get("id_A") or 0.0), sf_ref=_oc.get("sf_ref"))
            _lbl2d = (f"2D-FDM (∞ lang, i_q={_op.get('iq_A')} A, i_d={_op.get('id_A')} A)")
        else:
            em2d, _lbl2d = _oc, "2D-FDM (∞ lang, Leerlauf)"
        br2d = np.asarray(em2d["Br_gap"]); th2d = np.linspace(0, 2 * np.pi, len(br2d), endpoint=False)
        perf = em2d.get("performance", {})
        cmp2d = {"B_gap_2D": round(float(np.max(np.abs(br2d))), 3),
                 "B_gap_3D_mid": res["b_gap_mid_peak"],
                 "Kt_2D": perf.get("Kt_Nm_per_A"),
                 "excitation": "loaded" if _ld else "open_circuit"}
        cmp2d.update(_orientation_check(th2d, br2d, th, br_mid, geom, tags, res))
        fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
        ax.plot(np.degrees(th2d), br2d, label=_lbl2d, color="#4fc3f7", lw=1.4)
        ax.plot(np.degrees(th), br_mid, label="3D Elmer (z=L/2)", color="#ff7043", lw=1.4)
        ax.set_xlabel("Umfangswinkel θ [°]"); ax.set_ylabel("B_r Luftspalt [T]")
        ax.set_title("Luftspalt-Radialfeld: 2D vs 3D", color="#ddd")
        ax.legend(fontsize=8); ax.grid(alpha=.2)
        _style_dark(ax)
        images.append({"key": "em3d_airgap_2d3d", "title": "Luftspalt 2D vs 3D",
                       "b64": _save(fig, "em3d_airgap_2d3d.png")})
    except Exception as e:
        res["warnings"].append(f"2D-Vergleich fehlgeschlagen: {e}")
    res["compare_2d"] = cmp2d

    # Endeffekt: axiales Peak-Br über z.
    fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
    ax.plot(z_levels, res["b_gap_axial"], "o-", color="#81c784", lw=1.4)
    ax.set_xlabel("axiale Position z [mm]"); ax.set_ylabel("Peak |B_r| [T]")
    ax.set_title("Endeffekt: Luftspaltfeld über der Paketlänge", color="#ddd")
    ax.grid(alpha=.2); _style_dark(ax)
    images.append({"key": "em3d_endeffect", "title": "Endeffekt B(z)",
                   "b64": _save(fig, "em3d_endeffect.png")})

    # |B|-Schnittbild bei z=L/2.
    try:
        images.append({"key": "em3d_slice_mid", "title": "|B| Schnitt z=L/2",
                       "b64": _slice_image(grid, bname, L / 2.0, dims, _save)})
    except Exception as e:
        res["warnings"].append(f"Schnittbild fehlgeschlagen: {e}")

    # Netz-Querschnitt (zonale Auflösung sichtbar machen).
    try:
        mb = _mesh_slice_image(tags, L / 2.0, _save_bytes)
        if mb:
            images.append({"key": "em3d_mesh_slice",
                           "title": "Netz-Querschnitt z=L/2 (zonale Auflösung)", "b64": mb})
    except Exception as e:
        res["warnings"].append(f"Netz-Schnittbild fehlgeschlagen: {e}")

    # .vtp für den eingebetteten vtk.js-Browser-Viewer (Festkörper-Oberfläche, |B|).
    try:
        vtp = os.path.join(os.path.dirname(vtu), "browser.vtp")
        export_browser_vtp(grid, bname, tags, vtp)
        res["vtp_path"] = vtp
    except Exception as e:
        res["warnings"].append(f"Browser-Viewer-Export fehlgeschlagen: {e}")

    # Feldlinien (.vtp Polylinien) für den Browser-Viewer.
    try:
        lines = os.path.join(os.path.dirname(vtu), "browser_lines.vtp")
        export_browser_streamlines(grid, bname, tags, lines)
        res["lines_path"] = lines
    except Exception as e:
        res["warnings"].append(f"Feldlinien-Export fehlgeschlagen: {e}")

    res["images"] = images
    return res


def _style_dark(ax):
    ax.set_facecolor("#0d0d0d")
    for s in ax.spines.values():
        s.set_color("#555")
    ax.tick_params(colors="#bbb"); ax.xaxis.label.set_color("#ccc"); ax.yaxis.label.set_color("#ccc")


def _slice_image(grid, bname, z0, dims, save_fn, b_sat=None):
    """Sättigungs-Schnitt auf der Ebene z=z0 (vtkCutter → matplotlib tricontourf).

    Färbt |B| in **Sättigungsfarben**: die Skala ist ans Sättigungsknie ``b_sat``
    (Standard ``B_SAT_DISPLAY_3D``≈2 T) gekoppelt statt an ein reines |B|-Perzentil,
    eine grüne Kontur markiert die Sättigungsgrenze, und die Farbtabelle (turbo)
    liest sich thermisch: blau=niedrig → grün≈Knie → rot=gesättigt. So zeigt der
    Schnitt direkt, WO das (linear gerechnete) Eisen in die Sättigung ginge — genau
    wie das Lastprofil-Video, nur als statisches Ergebnisbild. Qualitativ (lineares
    3D-Eisen, kein echtes BH-Limit)."""
    import vtk
    from vtk.util import numpy_support as ns
    import matplotlib.pyplot as plt
    plane = vtk.vtkPlane(); plane.SetOrigin(0, 0, z0); plane.SetNormal(0, 0, 1)
    cut = vtk.vtkCutter(); cut.SetCutFunction(plane); cut.SetInputData(grid); cut.Update()
    poly = cut.GetOutput()
    pts = ns.vtk_to_numpy(poly.GetPoints().GetData())
    B = ns.vtk_to_numpy(poly.GetPointData().GetArray(bname)).reshape(-1, 3)
    bmag = np.linalg.norm(B, axis=1)
    bs = float(b_sat if b_sat is not None else B_SAT_DISPLAY_3D)
    # Skala ans Sättigungsknie koppeln: vmax = 1,25·b_sat → das Knie liegt bei ~0,8
    # der turbo-Skala (gelb-grün), alles darüber schlägt nach rot um = gesättigt.
    vmax = 1.25 * bs
    fig, ax = plt.subplots(figsize=(5.4, 5.0), facecolor="#0d0d0d")
    tpc = ax.tricontourf(pts[:, 0], pts[:, 1], np.clip(bmag, 0, vmax),
                         levels=40, cmap="turbo", vmin=0.0, vmax=vmax)
    # Sättigungsgrenze als grüne Kontur (identisch zum Lastprofil-Video).
    try:
        ax.tricontour(pts[:, 0], pts[:, 1], bmag, levels=[bs],
                      colors="#39ff14", linewidths=1.1)
    except Exception:
        pass
    ax.set_aspect("equal")
    ax.set_title("|B| [T] — Sättigungs-Schnitt z=L/2\ngrün = Sättigungsgrenze %.1f T (qualitativ)"
                 % bs, color="#ddd", fontsize=10)
    rings = [dims["r_rot"], dims["r_si"], dims["r_so"]]
    if dims.get("r_bore", 0) > 0:
        rings.append(dims["r_bore"])                        # Hohlwellen-Bohrung
    for r in rings:
        ax.add_patch(plt.Circle((0, 0), r, fill=False, color="#ccc", lw=0.6))
    ax.set_xlim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    ax.set_ylim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    cb = fig.colorbar(tpc, ax=ax, shrink=0.8)
    cb.set_label("|B| [T]", color="#ccc")
    try:
        cb.ax.axhline(bs / vmax, color="#39ff14", lw=1.4)   # Knie-Marke in der Farbleiste
    except Exception:
        pass
    _style_dark(ax)
    return save_fn(fig, "em3d_slice_mid.png")


# Sättigungsknie fürs Video (lineares 3D-Eisen ⇒ qualitativ: markiert, WO das Eisen in die
# Sättigung ginge, und wie diese Zone mit der Last wächst — kein echtes BH-Limit).
B_SAT_DISPLAY_3D = 2.0


def _video_frame(grid, bname, dims, meta, out_png):
    """EIN Video-Frame für das dynamische Lastprofil: |B|-Sättigungs-Querschnitt (z=L/2) +
    Feldlinien in der Ebene + Kennwert-Panel (rpm/Last/i_q/i_d/|I|/B_gap/Moment + Phase) +
    normierte Zeitleiste mit Marker am aktuellen Betriebspunkt. Zeigt in EINEM Bild die
    Dynamik von Statorströmen, Sättigung und Feldlinien über den Lastzyklus."""
    import vtk
    from vtk.util import numpy_support as ns
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.colors as mcolors
    import matplotlib.tri as mtri

    z0 = meta["L"] / 2.0
    plane = vtk.vtkPlane(); plane.SetOrigin(0, 0, z0); plane.SetNormal(0, 0, 1)
    cut = vtk.vtkCutter(); cut.SetCutFunction(plane); cut.SetInputData(grid); cut.Update()
    poly = cut.GetOutput()
    pts = ns.vtk_to_numpy(poly.GetPoints().GetData())
    B = ns.vtk_to_numpy(poly.GetPointData().GetArray(bname)).reshape(-1, 3)
    x, y = pts[:, 0], pts[:, 1]
    bmag = np.linalg.norm(B, axis=1)
    r_so = dims["r_so"]; b_sat = meta.get("b_sat", B_SAT_DISPLAY_3D)

    fig = plt.figure(figsize=(9.2, 6.3), facecolor="#0d0d0d")
    gs = fig.add_gridspec(2, 2, width_ratios=[3.0, 1.15], height_ratios=[3.0, 1.05],
                          hspace=0.30, wspace=0.10)
    ax = fig.add_subplot(gs[0, 0]); axp = fig.add_subplot(gs[0, 1]); axt = fig.add_subplot(gs[1, :])

    # |B|-Heatmap (Wurzelskala) + Sättigungskontur (grün) + Feldlinien in der Ebene.
    vmax = max(b_sat, min(float(np.nanpercentile(bmag, 99)) if bmag.size else b_sat, 2.4))
    norm = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=vmax)
    ax.tricontourf(x, y, np.clip(bmag, 0, vmax), levels=40, cmap="magma", norm=norm)
    try:
        ax.tricontour(x, y, bmag, levels=[b_sat], colors="#39ff14", linewidths=1.0)
    except Exception:
        pass
    try:
        tri = mtri.Triangulation(x, y)
        gi = np.linspace(-r_so, r_so, 60)
        GX, GY = np.meshgrid(gi, gi)
        fx = mtri.LinearTriInterpolator(tri, B[:, 0]); fy = mtri.LinearTriInterpolator(tri, B[:, 1])
        U = np.asarray(fx(GX, GY)); V = np.asarray(fy(GX, GY))
        m = (GX ** 2 + GY ** 2) > (0.995 * r_so) ** 2
        U = np.ma.array(U, mask=m); V = np.ma.array(V, mask=m)
        ax.streamplot(gi, gi, U, V, color="#cfe3ff", density=1.1, linewidth=0.5, arrowsize=0.6)
    except Exception:
        pass
    for r in [dims["r_rot"], dims["r_si"], dims["r_so"]] + ([dims["r_bore"]] if dims.get("r_bore", 0) > 0 else []):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, color="#888", lw=0.6))
    ax.set_xlim(-r_so * 1.05, r_so * 1.05); ax.set_ylim(-r_so * 1.05, r_so * 1.05)
    ax.set_aspect("equal"); ax.set_xticks([]); ax.set_yticks([])
    ax.set_title("|B| Schnitt z=L/2 · Feldlinien · grün = Sättigungsgrenze (qualitativ)",
                 color="#ddd", fontsize=9)

    # Kennwert-Panel.
    axp.axis("off")
    def _fmt(v, f):
        return (f % v) if v is not None else "—"
    rows = [
        (f"Punkt {meta['idx'] + 1}/{meta['n']}", "#9ecbff", 12),
        (meta.get("phase") or "", "#ffd479", 11),
        ("", None, 5),
        (f"Drehzahl  {meta['rpm']:.0f} 1/min", "#dddddd", 10),
        (f"Last      {meta['load']:.0f} Nm", "#dddddd", 10),
        ("", None, 3),
        (f"i_q  {_fmt(meta.get('iq'), '%.0f')} A", "#7fd1b9", 10),
        (f"i_d  {_fmt(meta.get('id'), '%.0f')} A", "#f2a1a1", 10),
        (f"|I|  {_fmt(meta.get('is_peak'), '%.0f')} A", "#dddddd", 10),
        ("", None, 3),
        (f"B_gap  {_fmt(meta.get('b_gap'), '%.2f')} T", "#ffd479", 10),
        (f"Moment {_fmt(meta.get('torque'), '%.0f')} Nm", "#dddddd", 10),
    ]
    yy = 0.98
    for txt, col, sz in rows:
        if txt:
            axp.text(0.02, yy, txt, color=col, fontsize=sz, weight="bold", va="top",
                     family="monospace", transform=axp.transAxes)
        yy -= 0.058 + sz / 240.0

    # Normierte Zeitleiste (rpm/Last/i_q/i_d) mit Marker am aktuellen Punkt.
    idx = np.arange(meta["n"])
    def _norm(a):
        a = np.array(a, float); s = max(np.nanmax(np.abs(a)), 1.0); return a / s * 100.0
    axt.plot(idx, _norm(meta["prof_rpm"]), "-", color="#4fc3f7", lw=1.3, label="Drehzahl")
    axt.plot(idx, _norm(meta["prof_load"]), "-", color="#ffd479", lw=1.3, label="Last")
    axt.plot(idx, _norm(meta["prof_iq"]), "-", color="#7fd1b9", lw=1.1, label="i_q")
    axt.plot(idx, _norm(meta["prof_id"]), "-", color="#f2a1a1", lw=1.1, label="i_d")
    axt.axvline(meta["idx"], color="#ffffff", lw=1.4, alpha=0.85)
    axt.set_xlim(0, max(meta["n"] - 1, 1)); axt.set_ylim(-108, 108)
    axt.set_ylabel("% v. Max", fontsize=8)
    axt.set_title("Lastprofil (normiert) — Marker = aktueller Punkt", color="#bbb", fontsize=9)
    axt.legend(loc="upper right", fontsize=7, ncol=4, facecolor="#151515",
               labelcolor="#ccc", framealpha=0.5)
    _style_dark(ax); _style_dark(axt)
    fig.savefig(out_png, dpi=110, facecolor="#0d0d0d"); plt.close(fig)
    return out_png


def _video_frame_fail(meta, out_png):
    """Platzhalter-Frame für einen fehlgeschlagenen Betriebspunkt — hält die Framefolge
    lückenlos (ffmpeg braucht fortlaufende frame_%04d.png)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots(figsize=(9.2, 6.3), facecolor="#0d0d0d")
    ax.axis("off")
    ax.text(0.5, 0.5, f"Punkt {meta['idx'] + 1}/{meta['n']}\n{meta['rpm']:.0f} 1/min · "
            f"{meta['load']:.0f} Nm\n(fehlgeschlagen)", color="#e57", ha="center", va="center",
            fontsize=14, family="monospace")
    fig.savefig(out_png, dpi=110, facecolor="#0d0d0d"); plt.close(fig)
    return out_png


def _encode_video(frames_dir, fps=6):
    """frame_%04d.png in frames_dir → anim.mp4 via ffmpeg (wie ema_pipeline._make_video)."""
    import subprocess
    out = os.path.join(frames_dir, "anim.mp4")
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-framerate", str(fps),
             "-i", os.path.join(frames_dir, "frame_%04d.png"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p",
             "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", out],
            capture_output=True, text=True, timeout=240)
        return out if (r.returncode == 0 and os.path.exists(out)) else None
    except Exception:
        return None


def _mesh_slice_image(tags, z0, save_bytes):
    """Querschnitt des **Volumen-Netzes** bei z=z0 als Drahtgitter, eingefärbt nach
    Elementgröße — zeigt direkt die zonale Auflösung (Luftspalt sehr fein, Magnete/
    Barrieren fein, Rest grob). Nimmt die gmsh-.vtk (enthält ALLE Körper inkl. Luft, im
    Gegensatz zur Festkörper-.vtp). Returns data-URL oder None."""
    import vtk
    from vtk.util import numpy_support as ns
    import matplotlib.pyplot as plt
    import matplotlib.tri as mtri
    import io
    if not tags.get("vtk_mesh") or not os.path.exists(tags["vtk_mesh"]):
        return None
    rd = vtk.vtkUnstructuredGridReader(); rd.SetFileName(tags["vtk_mesh"]); rd.Update()
    g = rd.GetOutput()
    plane = vtk.vtkPlane(); plane.SetOrigin(0, 0, z0); plane.SetNormal(0, 0, 1)
    cut = vtk.vtkCutter(); cut.SetCutFunction(plane); cut.SetInputData(g); cut.Update()
    tri = vtk.vtkTriangleFilter(); tri.SetInputConnection(cut.GetOutputPort()); tri.Update()
    poly = tri.GetOutput()
    if poly.GetNumberOfPoints() == 0 or poly.GetNumberOfPolys() == 0:
        return None
    pts = ns.vtk_to_numpy(poly.GetPoints().GetData())
    conn = ns.vtk_to_numpy(poly.GetPolys().GetData()).reshape(-1, 4)
    tris = conn[:, 1:]
    x, y = pts[:, 0], pts[:, 1]
    triang = mtri.Triangulation(x, y, tris)
    # Elementgröße ~ √Fläche je Dreieck (klein = fein).
    a = tris[:, 0]; bb = tris[:, 1]; c = tris[:, 2]
    area = 0.5 * np.abs((x[bb] - x[a]) * (y[c] - y[a]) - (x[c] - x[a]) * (y[bb] - y[a]))
    csize = np.sqrt(np.maximum(area, 1e-9))
    fig, ax = plt.subplots(figsize=(5.4, 5.0), facecolor="#0d0d0d")
    tpc = ax.tripcolor(triang, csize, cmap="viridis_r", shading="flat",
                       vmin=float(np.percentile(csize, 2)), vmax=float(np.percentile(csize, 98)))
    ax.triplot(triang, color="#0c0c0c", lw=0.12, alpha=0.55)
    ax.set_aspect("equal"); ax.set_title("Netz-Querschnitt z=L/2 (hell = fein)", color="#ddd")
    dims = tags["dims"]
    rings = [dims["r_rot"], dims["r_si"], dims["r_so"]]
    if dims.get("r_bore", 0) > 0:
        rings.append(dims["r_bore"])
    for r in rings:
        ax.add_patch(plt.Circle((0, 0), r, fill=False, color="#bbb", lw=0.5, alpha=0.5))
    ax.set_xlim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    ax.set_ylim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    fig.colorbar(tpc, ax=ax, shrink=0.8, label="Elementgröße [mm]")
    _style_dark(ax)
    buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=110, bbox_inches="tight",
                                    facecolor="#0d0d0d")
    plt.close(fig)
    return save_bytes(buf.getvalue(), "em3d_mesh_slice.png")


# ── Echte 3D-Visualisierung (vtk offscreen) ─────────────────────────────────────

_CLS = {"shaft": 0, "rotor": 1, "stator": 2}     # Magnet N=3, S=4, Luft=-1


def _classified_grid(tags):
    """Liest das Mesh-VTK, fügt eine Zell-Skalar „cls" (Bauteilklasse) hinzu.

    Gmsh schreibt die **Physical-Group-IDs** als ``CellEntityIds`` (NICHT die
    elementaren Entity-Tags) → über die Physical-IDs aus ``tags`` abbilden."""
    import vtk
    from vtk.util import numpy_support as ns
    rd = vtk.vtkUnstructuredGridReader()
    rd.SetFileName(tags["vtk_mesh"]); rd.ReadAllScalarsOn(); rd.Update()
    g = rd.GetOutput()
    ent = ns.vtk_to_numpy(g.GetCellData().GetArray("CellEntityIds"))
    # Physical-ID → Klassencode.
    p2c = {}
    for name, pid in tags["bodies"].items():
        if name in _CLS:
            p2c[pid] = _CLS[name]                      # shaft/rotor/stator; air → fehlt ⇒ -1
    for m in tags["magnets"]:
        p2c[m["phys"]] = 3.0 if m["sign"] > 0 else 4.0
    cls = np.array([p2c.get(int(e), -1.0) for e in ent], dtype=float)
    arr = ns.numpy_to_vtk(cls); arr.SetName("cls")
    g.GetCellData().AddArray(arr); g.GetCellData().SetActiveScalars("cls")
    return g


def _class_actor(grid, code, color, opacity=1.0):
    import vtk
    th = vtk.vtkThreshold(); th.SetInputData(grid)
    th.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS, "cls")
    th.SetLowerThreshold(code - 0.5); th.SetUpperThreshold(code + 0.5)
    th.Update()
    sf = vtk.vtkDataSetSurfaceFilter(); sf.SetInputConnection(th.GetOutputPort()); sf.Update()
    if sf.GetOutput().GetNumberOfCells() == 0:
        return None
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(sf.GetOutputPort()); m.ScalarVisibilityOff()
    a = vtk.vtkActor(); a.SetMapper(m)
    a.GetProperty().SetColor(*color); a.GetProperty().SetOpacity(opacity)
    a.GetProperty().SetAmbient(0.25); a.GetProperty().SetDiffuse(0.8)
    return a


def _clip_z(grid, z0, keep_below=True):
    """Schneidet das Gitter bei z=z0 (Cutaway, um ins Innere zu sehen)."""
    import vtk
    clip = vtk.vtkClipDataSet(); clip.SetInputData(grid)
    pl = vtk.vtkPlane(); pl.SetOrigin(0, 0, z0)
    pl.SetNormal(0, 0, -1 if keep_below else 1)
    clip.SetClipFunction(pl); clip.Update()
    return clip.GetOutput()


_GEO_COLORS = {0: (0.26, 0.26, 0.30), 1: (0.62, 0.63, 0.66),
               2: (0.40, 0.45, 0.55), 3: (0.92, 0.18, 0.18), 4: (0.20, 0.45, 0.95)}


def _render_window(actors, size=(940, 820), bg=(0.05, 0.05, 0.08), extra=None):
    import vtk
    ren = vtk.vtkRenderer(); ren.SetBackground(*bg)
    for a in actors:
        if a is not None:
            ren.AddActor(a)
    if extra:
        ren.AddActor2D(extra)
    rw = vtk.vtkRenderWindow(); rw.SetOffScreenRendering(1); rw.AddRenderer(ren)
    rw.SetSize(*size)
    return ren, rw


def _grab(rw, save_fn, name):
    import vtk
    rw.Render()
    w2i = vtk.vtkWindowToImageFilter(); w2i.SetInput(rw); w2i.Update()
    import base64, io
    wr = vtk.vtkPNGWriter(); wr.SetWriteToMemory(1)
    wr.SetInputConnection(w2i.GetOutputPort()); wr.Write()
    data = bytes(memoryview(wr.GetResult()))
    return save_fn(data, name)


def _classify_grid_gids(grid, tags):
    """Wie ``_classified_grid``, aber aus den **GeometryIds** einer Elmer-VTU (Body-Physical-IDs)
    statt der gmsh-.vtk-CellEntityIds — für den zum vollen Motor gespiegelten Sektor (der die
    Mesh-.vtk nicht patternt, aber die VTU mit GeometryIds trägt). Fügt das Zell-Skalar „cls" an."""
    import vtk
    from vtk.util import numpy_support as ns
    gid = grid.GetCellData().GetArray("GeometryIds")
    if gid is None:
        return None
    ent = ns.vtk_to_numpy(gid)
    p2c = {}
    for name, pid in tags["bodies"].items():
        if name in _CLS:
            p2c[pid] = _CLS[name]
    for m in tags["magnets"]:
        p2c[m["phys"]] = 3.0 if m["sign"] > 0 else 4.0
    cls = np.array([p2c.get(int(e), -1.0) for e in ent], dtype=float)
    arr = ns.numpy_to_vtk(cls); arr.SetName("cls")
    grid.GetCellData().AddArray(arr); grid.GetCellData().SetActiveScalars("cls")
    return grid


def render_geometry_3d(tags, save_fn):
    """Echte 3D-Ansicht des Modells: Eisen halbtransparent, Magnete opak (N rot / S blau).
    Liefert eine Liste {key,title,b64}. Braucht ``tags['vtk_mesh']``."""
    if not tags.get("vtk_mesh") or not os.path.exists(tags["vtk_mesh"]):
        return []
    return _render_geometry_views(_classified_grid(tags), tags["L"], tags["dims"]["r_so"], save_fn)


def _render_geometry_views(full, L, R, save_fn):
    """Die eigentlichen Geometrie-Ansichten (Cutaway-Iso + Stirnseite) aus einem schon nach „cls"
    klassifizierten Gitter — geteilt von ``render_geometry_3d`` (Vollmodell, gmsh-.vtk) und dem
    Sektor (gespiegeltes VTU, GeometryIds)."""
    out = []

    # 1) Cutaway-Iso: oben aufgeschnitten, opake Bauteile → Pollage klar im 3D-Schnitt.
    cut = _clip_z(full, L * 0.55, keep_below=True)
    actors = [_class_actor(cut, c, _GEO_COLORS[c]) for c in (0, 1, 2, 3, 4)]
    ren, rw = _render_window(actors)
    ren.GetActiveCamera().SetViewUp(0, 0, 1)
    ren.ResetCamera()
    cam = ren.GetActiveCamera()
    cam.Azimuth(35); cam.Elevation(-60); cam.Zoom(1.25)
    ren.ResetCameraClippingRange()
    out.append({"key": "em3d_model_iso",
                "title": "3D-Schnittmodell (Magnete rot=N / blau=S, Rotor/Stator-Eisen)",
                "b64": _grab(rw, save_fn, "em3d_model_iso.png")})

    # 2) Stirnseite (Blick entlang der Achse) — reine Pol-/Magnetanordnung.
    ren2, rw2 = _render_window([_class_actor(full, 1, _GEO_COLORS[1]),
                                _class_actor(full, 3, _GEO_COLORS[3]),
                                _class_actor(full, 4, _GEO_COLORS[4])])
    ren2.GetActiveCamera().SetViewUp(0, 1, 0)
    ren2.ResetCamera()
    ren2.GetActiveCamera().Zoom(1.4)
    ren2.ResetCameraClippingRange()
    out.append({"key": "em3d_model_axial", "title": "Magnet-/Polanordnung (Blick entlang der Achse)",
                "b64": _grab(rw2, save_fn, "em3d_model_axial.png")})
    return out


def render_field_3d(grid, bname, tags, save_fn):
    """3D-Feldansicht: Geometrie-Oberflächen nach |B| eingefärbt, mit Schnitt zum
    Hineinschauen + Farbskala. Braucht die Elmer-VTU (Feld ``bname``)."""
    import vtk
    from vtk.util import numpy_support as ns
    B = ns.vtk_to_numpy(grid.GetPointData().GetArray(bname)).reshape(-1, 3)
    bmag = np.linalg.norm(B, axis=1)
    arr = ns.numpy_to_vtk(bmag); arr.SetName("Bmag")
    grid.GetPointData().AddArray(arr); grid.GetPointData().SetActiveScalars("Bmag")
    L = tags["L"]; R = tags["dims"]["r_so"]
    vmax = float(np.nanpercentile(bmag, 99))
    vmax = max(0.2, min(vmax, 2.2))

    lut = vtk.vtkLookupTable(); lut.SetHueRange(0.66, 0.0); lut.SetTableRange(0, vmax); lut.Build()
    # Schnitt bei z>L/2 wegnehmen, damit man ins Innere sieht.
    clip = vtk.vtkClipDataSet(); clip.SetInputData(grid)
    pl = vtk.vtkPlane(); pl.SetOrigin(0, 0, L * 0.55); pl.SetNormal(0, 0, -1)
    clip.SetClipFunction(pl); clip.Update()
    sf = vtk.vtkDataSetSurfaceFilter(); sf.SetInputConnection(clip.GetOutputPort()); sf.Update()
    m = vtk.vtkPolyDataMapper(); m.SetInputConnection(sf.GetOutputPort())
    m.SetLookupTable(lut); m.SetScalarRange(0, vmax); m.SetScalarModeToUsePointData()
    a = vtk.vtkActor(); a.SetMapper(m)
    sb = vtk.vtkScalarBarActor(); sb.SetLookupTable(lut); sb.SetTitle("|B| [T]")
    sb.SetNumberOfLabels(5)
    ren, rw = _render_window([a], extra=sb)
    cam = ren.GetActiveCamera()
    cam.SetPosition(R * 2.4, -R * 2.4, L * 1.9); cam.SetFocalPoint(0, 0, L / 2)
    cam.SetViewUp(0, 0, 1); ren.ResetCameraClippingRange()
    return {"key": "em3d_field3d", "title": "3D-Feld |B| (aufgeschnitten)",
            "b64": _grab(rw, save_fn, "em3d_field3d.png")}


def export_browser_vtp(grid, bname, tags, out_path):
    """Schreibt eine schlanke .vtp (Oberfläche NUR der Festkörper, eingefärbt nach |B|)
    für den eingebetteten vtk.js-Browser-Viewer. Luft wird über die `GeometryIds`
    (Body-Ids aus `tags`) entfernt; nur das skalare ``Bmag`` bleibt erhalten (klein)."""
    import vtk
    from vtk.util import numpy_support as ns

    solid_ids = set()
    for name in ("shaft", "rotor", "stator"):
        if name in tags["bodies"]:
            solid_ids.add(int(tags["bodies"][name]))
    for m in tags["magnets"]:
        solid_ids.add(int(m["phys"]))

    gid_arr = grid.GetCellData().GetArray("GeometryIds")
    if gid_arr is not None and solid_ids:
        gid = ns.vtk_to_numpy(gid_arr)
        mask = np.isin(gid, list(solid_ids)).astype(np.uint8)
        marr = ns.numpy_to_vtk(mask); marr.SetName("solidmask")
        grid.GetCellData().AddArray(marr)
        th = vtk.vtkThreshold(); th.SetInputData(grid)
        th.SetInputArrayToProcess(0, 0, 0, vtk.vtkDataObject.FIELD_ASSOCIATION_CELLS, "solidmask")
        th.SetLowerThreshold(0.5); th.SetUpperThreshold(1.5); th.Update()
        surf = vtk.vtkGeometryFilter(); surf.SetInputConnection(th.GetOutputPort())
    else:
        surf = vtk.vtkGeometryFilter(); surf.SetInputData(grid)
    surf.Update()
    poly = surf.GetOutput()

    B = ns.vtk_to_numpy(poly.GetPointData().GetArray(bname)).reshape(-1, 3)
    bmag = np.linalg.norm(B, axis=1).astype(np.float32)
    # Alle (großen) Punkt-Arrays entfernen, nur Bmag behalten → kleine Datei.
    pdp = poly.GetPointData()
    for nm in [pdp.GetArrayName(i) for i in range(pdp.GetNumberOfArrays())]:
        pdp.RemoveArray(nm)
    ba = ns.numpy_to_vtk(bmag); ba.SetName("Bmag")
    pdp.AddArray(ba); pdp.SetActiveScalars("Bmag")
    poly.GetCellData().Initialize()

    _write_vtp(poly, out_path)
    return out_path


def _write_vtp(poly, out_path):
    """Schreibt ein vtkPolyData im exakt vom vtk.js-XMLPolyDataReader lesbaren Format:
    Punkte als float32, Binär (base64-inline), UNkomprimiert, **32-Bit-Header**.
    (ASCII parst der Reader nicht; 64-Bit-Header + Kompression brechen ihn; 8-Byte-
    Doubles verrechnet er an der Ausrichtung: „Float64Array offset multiple of 8".)"""
    import vtk
    from vtk.util import numpy_support as ns
    pts32 = ns.vtk_to_numpy(poly.GetPoints().GetData()).astype(np.float32)
    vp = vtk.vtkPoints(); vp.SetData(ns.numpy_to_vtk(pts32)); poly.SetPoints(vp)
    w = vtk.vtkXMLPolyDataWriter(); w.SetFileName(out_path); w.SetInputData(poly)
    w.SetDataModeToBinary()
    try:
        w.SetHeaderTypeToUInt32()
    except Exception:
        try:
            w.SetHeaderType(vtk.vtkXMLWriter.UInt32)
        except Exception:
            pass
    try:
        w.SetCompressorTypeToNone()
    except Exception:
        pass
    w.Write()
    return out_path


def _clip_streamlines(poly, r_lim, z_lo, z_hi):
    """Schneidet Feldlinien am Verlassen des Motor-Bereichs ab (Radius > ``r_lim`` oder z
    außerhalb ``[z_lo, z_hi]``). Jede Polylinie wird in ihre zusammenhängenden IN-Bereichs-
    Abschnitte (≥2 Punkte) zerlegt → Ausreißer in den weiten Luftraum verschwinden, die
    guten Teile bleiben. Punktdaten (u. a. der B-Vektor) werden mitgenommen."""
    import vtk
    from vtk.util import numpy_support as ns
    if poly.GetNumberOfPoints() == 0:
        return poly
    pts = ns.vtk_to_numpy(poly.GetPoints().GetData())
    inb = ((np.hypot(pts[:, 0], pts[:, 1]) <= r_lim)
           & (pts[:, 2] >= z_lo) & (pts[:, 2] <= z_hi))
    opd = poly.GetPointData()
    arrays = [(opd.GetArrayName(i), ns.vtk_to_numpy(opd.GetArray(i)))
              for i in range(opd.GetNumberOfArrays())]
    newpts = vtk.vtkPoints(); cells = vtk.vtkCellArray(); keep = []

    def _flush(run):
        if len(run) >= 2:
            cells.InsertNextCell(len(run))
            for oid in run:
                cells.InsertCellPoint(newpts.GetNumberOfPoints())
                newpts.InsertNextPoint(pts[oid]); keep.append(oid)

    lines = poly.GetLines(); lines.InitTraversal(); idl = vtk.vtkIdList()
    while lines.GetNextCell(idl):
        run = []
        for i in range(idl.GetNumberOfIds()):
            oid = idl.GetId(i)
            if inb[oid]:
                run.append(oid)
            else:
                _flush(run); run = []
        _flush(run)
    out = vtk.vtkPolyData(); out.SetPoints(newpts); out.SetLines(cells)
    keep = np.array(keep, dtype=int)
    for name, arr in arrays:
        sub = np.ascontiguousarray(arr[keep]) if keep.size else arr[:0]
        va = ns.numpy_to_vtk(sub); va.SetName(name)
        out.GetPointData().AddArray(va)
    return out


def export_browser_streamlines(grid, bname, tags, out_path):
    """Tracet Magnetfeldlinien (B-Vektor) durch das Volumennetz und schreibt sie als
    schlanke Polylinien-.vtp (eingefärbt nach |B|) für den vtk.js-Browser-Viewer.

    Seeds: ein Punkteraster im Band Welle→Stator-OD, verteilt über MEHRERE axiale Ebenen
    (nicht nur z=L/2), sodass die Flusspfade den 3D-Körper füllen und Endeffekte/Skew
    sichtbar werden. Streamlines werden serverseitig getraced (das große Volumennetz bleibt
    auf dem Server), nur die dünnen Linien gehen in den Browser."""
    import vtk
    from vtk.util import numpy_support as ns

    # B-Vektorfeld als aktive Vektoren setzen (StreamTracer integriert das aktive Feld).
    grid.GetPointData().SetActiveVectors(bname)

    # Referenz-Feldstärke für die Abbruch-Schwelle: das flussführende Gebiet liegt bei ~0,1–2 T,
    # der Luftraum weit draußen bei ~0. Ohne Abbruch folgt der Tracer im (nahezu feldfreien,
    # bei groben Hex-Zellen zusätzlich „blockigen") Luftraum winzigen Rausch-Komponenten hunderte
    # mm weit → wilde Ausreißer. Wir setzen `TerminalSpeed` auf einen kleinen Bruchteil des
    # typischen Feldniveaus, damit Linien im schwachen Feld sauber ENDEN statt zu mäandern.
    try:
        _barr = grid.GetPointData().GetArray(bname)
        _bm = np.linalg.norm(ns.vtk_to_numpy(_barr).reshape(-1, 3), axis=1)
        _bref = float(np.nanpercentile(_bm, 80)) if _bm.size else 0.3
    except Exception:
        _bref = 0.3
    _term = max(1e-6, 0.04 * _bref)

    dims = tags["dims"]; L = float(tags["L"])
    r_so = float(dims["r_so"]); r_sh = float(dims.get("r_shaft", 0.0) or 0.0)
    r_in = max(r_sh + 0.1 * r_so, 0.15 * r_so)   # innen knapp über der Welle starten
    r_out = 0.98 * r_so                           # außen knapp im Statoreisen enden

    # Seed-Raster: konzentrische Ringe × Winkel × MEHRERE axiale Ebenen — geometrieunabhängig
    # über die Radien skaliert. Über mehrere z-Ebenen (im aktiven Stack, ohne die Luftkappen),
    # damit die Feldlinien den 3D-Körper füllen statt in einer Ebene zu kleben. Bewusst eher
    # DICHT exportiert (kleine Datei, Linien sind schlank), weil der Browser-Slider die Linien
    # nur clientseitig AUSDÜNNT — die hier erzeugte Anzahl ist die Obergrenze („viele").
    n_rings, n_ang, n_z = 7, 36, 12
    z_lo, z_hi = 0.03 * L, 0.97 * L               # über die (nahezu) volle Stapellänge verteilt
    seeds = vtk.vtkPoints()
    for iz in range(n_z):
        z = z_lo + (z_hi - z_lo) * iz / max(n_z - 1, 1) if n_z > 1 else L / 2.0
        for ir in range(n_rings):
            r = r_in + (r_out - r_in) * ir / max(n_rings - 1, 1)
            for ia in range(n_ang):
                a = 2.0 * np.pi * ia / n_ang
                seeds.InsertNextPoint(r * np.cos(a), r * np.sin(a), z)
    seed_pd = vtk.vtkPolyData(); seed_pd.SetPoints(seeds)

    tracer = vtk.vtkStreamTracer()
    tracer.SetInputData(grid)
    tracer.SetSourceData(seed_pd)
    tracer.SetIntegrationDirectionToBoth()
    tracer.SetIntegratorTypeToRungeKutta4()              # nicht-adaptiv: robust, auch bei homogenen Feldern
    # Schrittweite in LÄNGE (mm), an die Maschinengröße gekoppelt — der adaptive RK45 in
    # CELL_LENGTH-Einheiten brach hier sofort ab (0 Linien trotz vorhandenem Feld).
    tracer.SetIntegrationStepUnit(vtk.vtkStreamTracer.LENGTH_UNIT)
    tracer.SetInitialIntegrationStep(0.03 * r_so)
    tracer.SetMinimumIntegrationStep(0.01 * r_so)
    tracer.SetMaximumIntegrationStep(0.08 * r_so)
    # Nur ~2 Außendurchmesser weit verfolgen (eine Flusslinie schließt sich über das Joch in
    # dieser Distanz) — 6·r_so ließ Ausreißer hunderte mm in den Luftraum schießen.
    tracer.SetMaximumPropagation(2.2 * r_so)
    tracer.SetMaximumNumberOfSteps(1200)
    tracer.SetTerminalSpeed(_term)                       # im schwachen Feld enden (kein Mäandern)
    tracer.SetComputeVorticity(False)
    tracer.Update()
    poly = tracer.GetOutput()

    # Nachfilter: Linien, die trotzdem weit aus dem Motor herauslaufen (Radius ≫ Stator-OD oder
    # axial weit außerhalb des Pakets), abschneiden — hält die Darstellung im interessanten Bereich.
    r_lim = 1.25 * r_so
    z_lo_lim, z_hi_lim = -0.25 * L, 1.25 * L
    poly = _clip_streamlines(poly, r_lim, z_lo_lim, z_hi_lim)

    # |B| je Linienpunkt als einziges Skalar behalten, Rest verwerfen → kleine Datei.
    pdp = poly.GetPointData()
    barr = pdp.GetArray(bname)
    if barr is not None:
        B = ns.vtk_to_numpy(barr).reshape(-1, 3)
        bmag = np.linalg.norm(B, axis=1).astype(np.float32)
    else:
        bmag = np.zeros(poly.GetNumberOfPoints(), dtype=np.float32)
    for nm in [pdp.GetArrayName(i) for i in range(pdp.GetNumberOfArrays())]:
        pdp.RemoveArray(nm)
    ba = ns.numpy_to_vtk(bmag); ba.SetName("Bmag")
    pdp.AddArray(ba); pdp.SetActiveScalars("Bmag")
    poly.GetCellData().Initialize()

    _write_vtp(poly, out_path)
    return out_path


def _charts_saver(project_dir):
    """bytes+name → schreibt nach project_dir/charts, gibt data-URL zurück."""
    import base64
    charts = os.path.join(project_dir, "charts")
    os.makedirs(charts, exist_ok=True)

    def _save(data, name):
        with open(os.path.join(charts, name), "wb") as f:
            f.write(data)
        return "data:image/png;base64," + base64.b64encode(data).decode()
    return _save


def render_model_preview(payload: dict, project_dir: str, progress_cb=None) -> dict:
    """Baut NUR das 3D-Mesh und rendert die 3D-Modellansichten (Schnitt + Stirnseite) —
    OHNE Elmer. Schnelle räumliche Vorschau der parametrischen Geometrie."""
    def _log(m, p=None):
        if progress_cb:
            progress_cb(m, p)
    geom = payload.get("geom", payload)
    axial = float(payload.get("axial_len") or geom.get("axialLen") or 120.0)
    opts = {k: payload[k] for k in ("skew_deg", "skew_segments", "skew_step_deg",
                                    "mesh_cl", "gap_cl", "mag_cl", "mag_grow",
                                    "airbox_factor", "hex_mesh")
            if k in payload}
    work = os.path.join(project_dir, "em3d"); os.makedirs(work, exist_ok=True)
    _log("🔧 Baue 3D-Mesh (Gmsh)…", 15)
    tags, _ = _build_mesh_capped(geom, axial, opts, os.path.join(work, "motor3d.msh"), log=_log)
    _log(f"✓ Mesh: {tags['n_nodes']} Knoten, {tags['n_magnets']} Magnete", 70)
    _log("🎨 Rendere 3D-Modellansichten…", 80)
    saver = _charts_saver(project_dir)
    images = render_geometry_3d(tags, saver)
    try:
        mb = _mesh_slice_image(tags, axial / 2.0, saver)
        if mb:
            images.append({"key": "em3d_mesh_slice",
                           "title": "Netz-Querschnitt z=L/2 (zonale Auflösung)", "b64": mb})
    except Exception:
        pass
    _log("✓ 3D-Modell fertig", 100)
    return {"images": images, "preview": True, "axial_mm": axial,
            "mesh": {"n_nodes": tags["n_nodes"], "n_magnets": tags["n_magnets"],
                     "bodies": tags["n_bodies"]},
            "warnings": ["Nur 3D-Geometrie (ohne Feld). Für das berechnete |B|-Feld "
                         "Elmer installieren und '3D-Feld berechnen' nutzen."]}


def _seed_cl(geom, opts):
    """Explizite Zellgrößen (gap/mag/mesh/grow, mm) — nutzt gesetzte (>0) Werte, füllt den Rest
    mit denselben Auto-Regeln wie ``_build_mesh_once``. So sind die cl-Werte für das Skalieren
    (Ziel-/Fehler-Mitigation) IMMER konkret, auch beim allerersten Versuch (0 = auto)."""
    r_so = geom["statorOD"] / 2.0
    gap = max(0.1, (geom["statorID"] - geom["rotorOD"]) / 2.0)
    mesh_cl = float(opts.get("mesh_cl", 0.0)) or max(2.0, r_so / 18.0)
    gap_cl = float(opts.get("gap_cl", 0.0)) or max(0.35, gap * 0.6)
    mag_cl = float(opts.get("mag_cl", 0.0)) or max(gap_cl, mesh_cl * 0.5)
    mag_grow = float(opts.get("mag_grow", 0.0)) or max(2.0, 3.0 * gap)
    return gap_cl, mag_cl, mesh_cl, mag_grow


def _mesh_logger(msh, log=None):
    """Öffnet ein Mesh-Build-Logfile neben ``msh`` (``mesh_build.log``) und gibt eine Schreib-
    Funktion zurück, die JEDE Zeile mit Zeitstempel ins File schreibt UND (best-effort) an den
    optionalen UI-``log``-Callback spiegelt. Das File ist der Nachweis des Selbstheil-Monitors."""
    import datetime
    try:
        path = os.path.join(os.path.dirname(os.path.abspath(msh)) or ".", "mesh_build.log")
        fh = open(path, "a", encoding="utf-8")
    except Exception:
        fh, path = None, None

    def w(msg, ui=False, pct=None):
        line = f"[{datetime.datetime.now().strftime('%H:%M:%S')}] {msg}"
        if fh:
            try:
                fh.write(line + "\n"); fh.flush()
            except Exception:
                pass
        if ui and log:
            log(msg, pct)
    return w, path


# Selbstheil-Monitor: geordnete Mitigationsleiter für einen fehlgeschlagenen Netzbau (überlappende
# Facetten / ungültige Tetraeder). Jede Stufe bekommt (opts, seed_cl) und liefert (label, neue_opts).
# Reihenfolge nach Nutzer-Wunsch: ZUERST an der NETZQUALITÄT drehen (Vernetzungsverfahren,
# Zellgrößen feiner/gröber, Zonen-Verhältnisse) — das ändert das Modell NICHT — und erst als
# LETZTES Modell-Features (Magnettaschen, Skew, Nuten) entfernen. So bleibt maximale Modelltreue.
def _mesh_mitigations():
    def m_quality(o, cl):
        return ("Netzqualität erhöhen (robustes Verfahren + Tetraeder-Optimierung)",
                dict(o, mesh_robust=True))

    def m_coarsen_fine(o, cl):
        g, m, me, gr = cl
        return ("Luftspalt-/Magnet-Mesh ×1.5 vergröbern",
                dict(o, gap_cl=g * 1.5, mag_cl=m * 1.5, mesh_cl=me, mag_grow=gr))

    def m_ratio(o, cl):
        g, m, me, gr = cl
        # Zonen-VERHÄLTNISSE angleichen: den Größensprung zwischen Luftspalt/Magnet und grobem
        # Netz sanfter machen (mag_cl näher an gap_cl, breitere Übergangszone) — weniger
        # Konflikte durch steile Zellgrößen-Gradienten, ohne pauschal zu vergröbern.
        return ("Zonen-Verhältnisse angleichen (sanfterer Größenübergang)",
                dict(o, gap_cl=g, mag_cl=max(g, (g + m) * 0.5), mesh_cl=me, mag_grow=gr * 1.6))

    def m_coarsen_all(o, cl):
        g, m, me, gr = cl
        return ("Gesamtnetz ×1.8 vergröbern",
                dict(o, gap_cl=g * 1.8, mag_cl=m * 1.8, mesh_cl=me * 1.8, mag_grow=gr))

    def m_no_pockets(o, cl):
        return "Magnettaschen-Endkappen deaktivieren", dict(o, mag_pockets=False)

    def m_no_skew(o, cl):
        return ("Staffelung/Skew ausschalten (Prismen-Verdrehung als Konfliktquelle)",
                dict(o, skew_deg=0.0, skew_segments=1, skew_step_deg=0.0))

    def m_no_slots(o, cl):
        return "Statornuten aus dem Mesh nehmen", dict(o, stator_slots=False)

    # Netzqualität/-dichte/-verhältnisse zuerst, Modell-Features zuletzt.
    return [m_quality, m_coarsen_fine, m_ratio, m_coarsen_all, m_no_pockets, m_no_skew, m_no_slots]


def _build_mesh_capped(geom, axial, opts, msh, log=None):
    """Selbstheilender, ziel-gesteuerter 3D-Netzbau mit Logfile (``mesh_build.log`` neben ``msh``).

    Zwei verschränkte Aufgaben, protokolliert Schritt für Schritt:

    * **Ziel-Knotenzahl / Cap** — ist ``opts['target_nodes']`` gesetzt (UI-Regler, geklemmt auf
      10k…``EM3D_NODE_CEILING``), wird die Knotenzahl BEIDSEITIG angesteuert: zu grob ⇒ Zellgrößen
      verfeinern, zu fein ⇒ vergröbern (Skalierung ~Knoten∝h^-1.85, Toleranzband ±18 %). Ohne Ziel
      gilt der klassische Cap ``max_nodes``/``EM3D_MAX_NODES`` (nur vergröbern — Segfault-/OOM-Schutz).
    * **Selbstheil-Monitor** — schlägt ``build_mesh`` fehl (überlappende Facetten / ungültige Tets),
      spielt der Monitor selbständig eine Mitigationsleiter durch (Taschen aus → feine Zonen gröber →
      Skew aus → Nuten aus → alles gröber) und baut mit neuen Parametern neu, bis es klappt oder die
      Leiter erschöpft ist. Jeder Versuch (Parameter + Ergebnis/Fehler) landet im Logfile.

    Gibt ``(tags, warnings)`` zurück."""
    wl, logpath = _mesh_logger(msh, log)
    warns = []

    tn = opts.get("target_nodes")
    if tn:
        target = int(max(10000, min(EM3D_NODE_CEILING, float(tn))))
        cap = int(target * 1.18)
    else:
        target = None
        cap = int(opts.get("max_nodes", EM3D_MAX_NODES) or EM3D_MAX_NODES)

    # cl explizit machen (nie 0/auto) → Skalierung immer definiert.
    g0, m0, me0, gr0 = _seed_cl(geom, opts)
    # `pocket_fallback=False`: über die Taschen entscheidet AUSSCHLIESSLICH die Leiter
    # (Stufe 5), nicht der stille Sofort-Fallback in `build_mesh` — sonst wäre die
    # ausdrückliche Reihenfolge „Netzqualität zuerst, Modell-Features zuletzt" wirkungslos.
    cur = dict(opts, gap_cl=g0, mag_cl=m0, mesh_cl=me0, mag_grow=gr0,
               pocket_fallback=False)

    wl(f"=== Netzbau: Topologie={geom.get('magShape','?')} p={geom.get('p','?')} "
       f"slots={geom.get('slots','?')} L={axial:.0f}mm | "
       f"Ziel-Knoten={target if target else '—'} Cap={cap} | "
       f"cl start gap={g0:.3f} mag={m0:.2f} grob={me0:.2f} saum={gr0:.1f}")

    mitigations = _mesh_mitigations()
    mit_i = 0                      # nächster Mitigationsschritt bei Fehler
    scale_passes = 0               # Ziel-/Cap-Nachführungen
    pocket_ok_nodes = []           # Knotenzahlen der Versuche, die die Taschen getragen haben
    # 7 Mitigationsstufen + bis zu 4 Ziel-/Cap-Nachführungen; seit die Taschen nicht mehr
    # vorab still abgeschaltet werden, kann die Leiter tatsächlich bis ans Ende laufen.
    max_attempts = 13

    tags = None
    for attempt in range(1, max_attempts + 1):
        try:
            wl(f"Versuch {attempt}: gap={cur.get('gap_cl',0):.3f} mag={cur.get('mag_cl',0):.2f} "
               f"grob={cur.get('mesh_cl',0):.2f} pockets={cur.get('mag_pockets',True)} "
               f"slots={cur.get('stator_slots',True)} skew={cur.get('skew_deg',0)}°")
            tags = build_mesh(geom, axial, cur, msh)
        except Exception as e:
            wl(f"  ✗ FEHLER: {type(e).__name__}: {str(e)[:180]}")
            if mit_i >= len(mitigations):
                wl("  ⚠ Mitigationsleiter erschöpft — Netzbau bleibt fehlgeschlagen.")
                if logpath:
                    warns.append(f"Netzbau trotz Selbstheilung fehlgeschlagen — Details: {logpath}")
                raise
            label, cur = mitigations[mit_i](cur, _seed_cl(geom, cur))
            mit_i += 1
            wl(f"  → Selbstheil-Monitor greift ein: {label}", ui=True)
            warns.append(f"Netzbau geheilt: {label} (überlappende Facetten).")
            continue

        n = tags["n_nodes"]
        # Taschen IST-Stand, nicht Soll-Stand: `cur['mag_pockets']` sagt nur, was angefordert
        # war. Gezählt wird, was wirklich als Luft im Netz steht.
        n_pk, n_pk_want = tags.get("n_pockets", 0), tags.get("n_pockets_want", 0)
        if n_pk:
            pk_txt = f"{n_pk} Magnettaschen (Spalt {tags.get('pocket_clear_mm', 0):.2f} mm)"
        elif cur.get("mag_pockets", True):
            pk_txt = "KEINE Magnettaschen (angefordert, aber nicht im Netz)"
        else:
            pk_txt = "KEINE Magnettaschen (abgeschaltet)"
        wl(f"  ✓ {n} Knoten, {tags.get('n_magnets','?')} Magnete, "
           f"{tags.get('n_slots',0)} Nuten, {tags.get('n_barriers',0)} Barrieren, {pk_txt}")
        if n_pk:
            pocket_ok_nodes.append(n)      # dieser Netzbau trug die Taschen (für den Hinweis unten)
        if tags.get("caps_dropped") or (cur.get("mag_pockets", True) is False
                                        and opts.get("mag_pockets", True)):
            # Konkret werden statt „feiner wählen": gemessen an der Delta-Maschine aus
            # 20260812_073601 gelang der Bau MIT Taschen sowohl sehr fein (245 k Knoten) als
            # auch sehr grob (30 k) und scheiterte nur im mittleren Band — es ist ein Problem
            # des Größen-GRADIENTEN, nicht der absoluten Feinheit. Deshalb bekommt der Nutzer
            # die Knotenzahlen genannt, bei denen es in DIESEM Lauf funktioniert hat.
            hint = (f" In diesem Lauf gelang der Netzbau mit Taschen bei "
                    f"{', '.join(str(x) for x in sorted(set(pocket_ok_nodes)))} Knoten — "
                    f"Knoten-Ziel dorthin setzen." if pocket_ok_nodes else
                    " Abhilfe: Knoten-Ziel deutlich erhöhen oder Luftspalt-/Magnet-Mesh von Hand setzen.")
            warns.append(
                "Magnettaschen (Luftkappen um die Magnete) sind NICHT im 3D-Netz — sie waren bei "
                f"Knoten-Ziel {target if target else cap} nicht konfliktfrei vernetzbar "
                f"(Klebespalt {tags.get('pocket_clear_geom_mm', 0.1)} mm). Das 3D-Feld zeigt die "
                "Magnete deshalb in massivem Eisen, die 2D-FDM-Lösung dagegen mit Luftkappen." + hint)
        elif cur.get("mag_pockets", True) and not n_pk:
            # Taschen waren an, wurden gebaut — aber keine einzige Luft-Schale hat die
            # Zuordnung überlebt. Das blieb bisher völlig unbemerkt: das 3D-Feld zeigt dann
            # Magnete in massivem Eisen, während die 2D-FDM-Lösung Luftkappen hat.
            wl(f"  ⚠ {n_pk_want} Magnettaschen gebaut, aber 0 als Luft zugeordnet "
               f"— 3D-Rotor ohne Flussbarrieren (weicht von der 2D-FDM-Lösung ab).", ui=True)
            warns.append(f"Magnettaschen im 3D-Netz nicht angekommen ({n_pk_want} gebaut, 0 zugeordnet) "
                         "— das 3D-Feld zeigt die Magnete in massivem Eisen, die 2D-FDM-Lösung "
                         "dagegen mit Luftkappen. Magnet-/Luftspalt-Mesh feiner wählen.")

        # --- Ziel-/Cap-Nachführung ---
        too_fine = n > cap
        too_coarse = bool(target) and n < 0.82 * target
        if (too_fine or too_coarse) and scale_passes < 4:
            scale_passes += 1
            ref = target if target else cap
            f = (n / ref) ** (1.0 / 1.85)
            if too_fine and not target:
                f *= 1.06                                # Cap-Fall: sicher drunter landen
            mz = tags.get("mesh_zones", {})
            cur = dict(cur,
                       gap_cl=float(mz.get("gap_cl", cur["gap_cl"])) * f,
                       mag_cl=float(mz.get("mag_cl", cur["mag_cl"])) * f,
                       mesh_cl=float(mz.get("mesh_cl", cur["mesh_cl"])) * f,
                       mag_grow=float(mz.get("mag_grow", cur["mag_grow"])))
            verb = "vergröbere" if f > 1 else "verfeinere"
            wl(f"  → {verb} ×{f:.3f} (Ist {n} → Ziel {ref})",
               ui=True)
            continue

        break                                            # akzeptiert

    if scale_passes and target:
        warns.append(f"Netz auf {tags['n_nodes']} Knoten angesteuert (Ziel {target}).")
    elif scale_passes:
        warns.append(f"Netz auf {tags['n_nodes']} Knoten vergröbert (3D-Löser-Limit {cap}; "
                     "für feinere Auflösung Ziel-Knoten erhöhen oder Modell verkleinern).")
    wl(f"=== fertig: {tags['n_nodes']} Knoten nach {attempt} Versuch(en) ===")
    if logpath:
        tags["mesh_log"] = logpath
    return tags, warns


# ── Orchestrator ─────────────────────────────────────────────────────────────────

# Payload-Schlüssel, die als 3D-Optionen an Mesh + sif weitergereicht werden.
_EM3D_OPT_KEYS = ("skew_deg", "skew_segments", "skew_step_deg",
                  "mesh_cl", "gap_cl", "mag_cl", "mag_grow", "mag_clear_mm",
                  "airbox_factor", "n2d", "rpm", "load_nm",
                  "excitation", "coil_currents", "target_nodes", "hex_mesh")


def _em3d_opts(payload: dict) -> dict:
    return {k: payload[k] for k in _EM3D_OPT_KEYS if k in payload}


def _mesh_key(geom, axial, opts):
    """Hash über alles, was die NETZform bestimmt: Geometrie + Baulänge + netzrelevante Optionen.
    ``rpm``/``load_nm`` sind bewusst AUSGENOMMEN (sie ändern nur die .sif/dq-Ströme, nicht das
    Netz) — ``excitation``/``coil_currents`` bleiben drin, weil sie die Stirnring-Luftannuli im
    Netz schalten. Gleicher Hash ⇒ identisches Netz ⇒ Wiederverwendung."""
    mesh_opts = {k: v for k, v in opts.items() if k not in ("rpm", "load_nm")}
    blob = json.dumps({"geom": geom, "axial": axial, "opts": mesh_opts},
                      sort_keys=True, default=str)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()


def _prep_mesh(geom, axial, opts, work, log):
    """Baut das 3D-Mesh (rein geometrieabhängig, liest NIE rpm/load) und führt ElmerGrid aus.
    **Mesh-Cache:** ist im selben Arbeitsverzeichnis schon ein Netz mit identischem
    ``_mesh_key`` gebaut (und liegen die Dateien noch), wird es WIEDERVERWENDET — beim Ändern
    von nur Drehzahl/Last läuft dann nur der Löser neu. Über mehrere Betriebspunkte hinweg
    ohnehin einmal gebaut. Returns (tags, warns)."""
    import elmer_runner as ER
    msh = os.path.join(work, "motor3d.msh")
    key = _mesh_key(geom, axial, opts)
    cached = _MESH_CACHE.get(work)
    if (cached and cached.get("key") == key
            and os.path.isdir(os.path.join(work, "mesh")) and os.path.exists(msh)):
        t = cached["tags"]
        log(f"♻ Mesh wiederverwendet (Geometrie unverändert) — {t['n_nodes']} Knoten, "
            "nur der Löser läuft neu.", 28)
        return t, []
    log("🔧 Baue 3D-Mesh (Gmsh)…", 8)
    tags, mesh_warns = _build_mesh_capped(geom, axial, opts, msh, log=log)
    mz = tags.get("mesh_zones", {})
    log(f"✓ Mesh: {tags['n_nodes']} Knoten, {tags['n_magnets']} Magnete, "
        f"{tags.get('n_barriers', 0)} Flussbarrieren, {tags.get('n_slots', 0)} Statornuten, "
        f"Körper {tags['n_bodies']}", 28)
    if mz:
        log(f"   Zonen: Luftspalt {mz['gap_cl']:.2f} / Magnet+Barriere+Nut {mz['mag_cl']:.2f} "
            f"(Saum {mz.get('mag_grow', 0.0):.1f}) / grob {mz['mesh_cl']:.1f} mm", 30)
    if tags.get("mesh_kind") == "hex":
        hc = tags.get("hex_counts", {})
        log(f"   🧱 Hexaeder-Netz: {hc.get('hex', 0)} Hexaeder + {hc.get('prism', 0)} Prismen "
            f"(Piola-Transform aktiv)", 32)
    elif tags.get("hex_fallback"):
        log(f"   ⚠ Hexaeder-Modus nicht möglich ({tags['hex_fallback']}) → Tetraeder-Netz", 32)
    log("🔁 ElmerGrid: MSH → Elmer-Mesh…", 38)
    rg = ER.run_elmergrid(msh, os.path.join(work, "mesh"))
    if not rg["ok"]:
        raise RuntimeError("ElmerGrid fehlgeschlagen: " + (rg.get("stderr") or rg.get("error", ""))[:300])
    _MESH_CACHE[work] = {"key": key, "tags": tags}       # für den nächsten Lauf mit gleicher Geometrie
    return tags, mesh_warns


def _export_browser_point(work_dir, tags, stub, res):
    """Schreibt für EINEN Sweep-Punkt eine schlanke Browser-.vtp (`<stub>.vtp`) + die
    Feldlinien (`<stub>_lines.vtp`) aus der gerade gelösten VTU und hängt die Pfade an
    ``res``. Eindeutiger Dateiname je Punkt, weil alle Punkte dieselbe ``case.vtu``
    überschreiben."""
    vtu = _find_vtu(work_dir)
    if not vtu:
        return
    grid = _read_grid(vtu)
    bname = _b_array_name(grid)
    if not bname:
        return
    vtp = stub + ".vtp"
    export_browser_vtp(grid, bname, tags, vtp)
    res["vtp_path"] = vtp
    lines = stub + "_lines.vtp"
    export_browser_streamlines(grid, bname, tags, lines)
    res["lines_path"] = lines


def _solve_point(geom, opts, tags, work, project_dir, log, full, pct=None, browser_stub=None):
    """Löst GENAU einen Betriebspunkt auf dem schon vorhandenen Mesh: schreibt die .sif für
    ``opts`` (rpm/load/excitation → dq-Ströme), ruft ElmerSolver, wertet aus.
    ``full=True`` → volle Auswertung (``parse_results``: Charts + VTU + VTP), sonst nur
    schlanke Kennwerte (``_gap_metrics_only``). ``browser_stub`` (Sweep) → zusätzlich eine
    schlanke Browser-.vtp + Feldlinien je Punkt unter eindeutigem Namen. Returns (res, op)."""
    import elmer_runner as ER
    log("📝 Schreibe Elmer-Solverdatei (.sif)…", pct)
    write_sif(geom, opts, tags, work, mesh_name="mesh")
    op = dict(tags.get("operating_point", {}))
    if op.get("excitation") == "loaded":
        log(f"   Betriebspunkt: {op['rpm']:.0f} 1/min, {op['load_nm']:.0f} Nm → "
            f"i_q={op['iq_A']} A, i_d={op['id_A']} A (Spitze {op['is_peak_A']} A)", None)
        log("   3D-Feld: " + ("Lastfeld mit Statorströmen + Stirnring-Schließung (vereinfacht)"
                              if op.get("field_loaded") else "Magnetfeld (Leerlauf)"), None)
    else:
        log("   Anregung: Leerlauf (nur Magnete)", None)
    log("🧲 ElmerSolver: 3D-Magnetostatik…", None)
    rs = ER.run_elmersolver(os.path.join(work, "case.sif"), work)
    if rs.get("aborted"):
        raise _Em3dAborted("ElmerSolver abgebrochen")
    if not rs["ok"]:
        raise RuntimeError("ElmerSolver fehlgeschlagen: " + (rs.get("stderr") or rs.get("error", ""))[:300]
                           + "\n" + (rs.get("stdout", "")[-400:]))
    res = parse_results(work, geom, opts, tags, project_dir) if full \
        else _gap_metrics_only(work, geom, opts, tags)
    if browser_stub:
        try:
            _export_browser_point(work, tags, browser_stub, res)
        except Exception as e:
            res.setdefault("warnings", []).append(f"Browser-Export Punkt fehlgeschlagen: {e}")
    return res, op


def _decorate_res(res, tags, opts, axial, op, mesh_warns):
    """Hängt Mesh-/Geometrie-/Betriebspunkt-Metadaten + Last-Momentnotiz an ein Einzelpunkt-
    Ergebnis (geteilt von ``run_em3d`` und dem Sweep-Detailpunkt)."""
    res["mesh"] = {"n_nodes": tags["n_nodes"], "n_magnets": tags["n_magnets"],
                   "n_barriers": tags.get("n_barriers", 0), "bodies": tags["n_bodies"],
                   "n_pockets": tags.get("n_pockets", 0),
                   "pocket_clear_mm": tags.get("pocket_clear_mm", 0.0)}
    if opts.get("target_nodes"):
        res["mesh"]["target_nodes"] = int(opts["target_nodes"])
    if tags.get("mesh_log"):
        res["mesh"]["log"] = tags["mesh_log"]
    res["mesh_zones"] = tags.get("mesh_zones", {})
    res["axial_mm"] = axial
    res["skew_deg"] = float(opts.get("skew_deg", 0.0) or 0.0)
    res["skew_segments"] = int(tags.get("skew_segments", 1))
    res["skew_step_deg"] = float(tags.get("skew_step_deg", 0.0))
    res["operating_point"] = op
    if mesh_warns:
        res.setdefault("warnings", []).extend(mesh_warns)
    if op.get("excitation") == "loaded" and op.get("field_loaded"):
        res["torque_note"] = (f"Lastfall {op['rpm']:.0f} 1/min / {op['load_nm']:.0f} Nm "
                              f"(i_q={op['iq_A']} A, i_d={op['id_A']} A) — Statorströme mit "
                              "Stirnring-Schließung; Feld vereinfacht (Grundwelle, lin. Eisen)")
    elif op.get("excitation") == "loaded":
        res["torque_note"] = (f"Betriebspunkt {op['rpm']:.0f} 1/min / {op['load_nm']:.0f} Nm: "
                              f"i_q={op['iq_A']} A, i_d={op['id_A']} A. 3D-Feld = Leerlauf (Magnete)")
    return res


def run_em3d(payload: dict, project_dir: str, progress_cb=None) -> dict:
    """Voller 3D-Lauf: Mesh → ElmerGrid → sif → ElmerSolver → Auswertung.

    ``payload`` = der normale Analyse-Payload (geom + axial) + 3D-Optionen
    (skew_deg, mesh_cl, gap_cl, airbox_factor). Returns das Ergebnis-Dict."""
    import elmer_runner as ER

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    if not ER.ELMER_OK:
        raise RuntimeError(ER.INSTALL_HINT)

    geom = payload.get("geom", payload)
    axial = float(payload.get("axial_len") or payload.get("axialLen")
                  or geom.get("axialLen") or 120.0)
    opts = _em3d_opts(payload)

    work = os.path.join(project_dir, "em3d")
    os.makedirs(work, exist_ok=True)

    tags, mesh_warns = _prep_mesh(geom, axial, opts, work, _log)
    res, op = _solve_point(geom, opts, tags, work, project_dir, _log, full=True, pct=45)
    _log("📊 Werte Felder aus + vergleiche mit 2D…", 85)
    _decorate_res(res, tags, opts, axial, op, mesh_warns)

    # 3D-Ergebnis in results.json des Projekts mergen, damit der Gesamtbericht den
    # 3D-Teil mit aufnehmen kann (Bilder liegen bereits unter charts/). base64 wird
    # NICHT mitgespeichert (die Charts existieren als Dateien) — results.json schlank halten.
    try:
        _persist_em3d_summary(project_dir, res)
    except Exception as e:
        res.setdefault("warnings", []).append(f"results.json-Merge fehlgeschlagen: {e}")

    _log("✓ 3D-Feldberechnung fertig", 100)
    return res


def run_em3d_sweep(payload: dict, project_dir: str, progress_cb=None, cancel_cb=None) -> dict:
    """Betriebspunkt-Sweep (Drehzahlband mit wechselnden Lasten): baut das Mesh EINMAL und
    löst dieselbe 3D-Magnetostatik für jeden Punkt aus ``payload["sweep"]`` (Liste
    ``{rpm, load_nm, excitation}``). Liefert schlanke Kennwerte je Punkt + Verlaufskurven über
    die Drehzahl; das volle 3D-Feld (Charts/VTU/VTP/Viewer) nur für den ``detail_index``-Punkt.

    ``cancel_cb`` (optional): wird zwischen den Punkten abgefragt; liefert es True, bricht der
    Sweep ab und behält das bis dahin gerechnete **Teilergebnis** (Zeilen + Verlaufskurven +
    ggf. Detailfeld), markiert es ``aborted`` und persistiert es normal — der Nutzer kann es
    speichern/ansehen und sauber neu starten.

    Stufe 1: KEINE echte Transiente — jeder Punkt ist eine eigene statische Lösung (lineare
    Materialien, Lastfeld als Grundwelle wie im Einzellauf)."""
    import elmer_runner as ER

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    def _cancelled():
        return bool(cancel_cb and cancel_cb())

    if not ER.ELMER_OK:
        raise RuntimeError(ER.INSTALL_HINT)

    geom = payload.get("geom", payload)
    axial = float(payload.get("axial_len") or payload.get("axialLen")
                  or geom.get("axialLen") or 120.0)
    base_opts = _em3d_opts(payload)

    points = payload.get("sweep") or []
    if not points:
        raise RuntimeError("Kein Betriebspunkt im Sweep (payload['sweep'] ist leer).")
    n = len(points)
    detail_index = int(payload.get("detail_index", n - 1))
    detail_index = max(0, min(detail_index, n - 1))

    work = os.path.join(project_dir, "em3d")
    os.makedirs(work, exist_ok=True)

    tags, mesh_warns = _prep_mesh(geom, axial, base_opts, work, _log)
    _log(f"🌡 Drehzahlband: {n} Betriebspunkte (Mesh nur einmal gebaut), "
         f"Detailpunkt #{detail_index + 1} mit vollem 3D-Feld", 40)

    # Dynamisches Lastprofil-Video: je Betriebspunkt ein Querschnitts-Frame (|B|-Sättigung +
    # Feldlinien + Kennwert-Panel + Zeitleiste) → anim.mp4. Die Zeitleiste braucht die GEPLANTEN
    # Profil-Verläufe (rpm/Last fix aus den Punkten; i_q/i_d analytisch vorab, deterministisch
    # wie im Löser) — der aktuelle B_gap/Moment kommt je Frame aus der Lösung.
    make_video = bool(payload.get("make_video"))
    frames_dir = os.path.join(project_dir, "frames_em3d")
    prof = None
    if make_video:
        import ema_analysis
        if os.path.isdir(frames_dir):
            for f in os.listdir(frames_dir):
                if f.endswith((".png", ".mp4")):
                    try: os.remove(os.path.join(frames_dir, f))
                    except Exception: pass
        os.makedirs(frames_dir, exist_ok=True)
        p_rpm, p_load, p_iq, p_id = [], [], [], []
        for pt in points:
            pt = pt or {}
            r_ = float(pt.get("rpm", 0.0) or 0.0); l_ = float(pt.get("load_nm", 0.0) or 0.0)
            p_rpm.append(r_); p_load.append(l_)
            try:
                iqv, idv = ema_analysis.estimate_dq_currents(geom, r_, l_) if l_ != 0 else (0.0, 0.0)
            except Exception:
                iqv, idv = 0.0, 0.0
            p_iq.append(iqv); p_id.append(idv)
        prof = {"prof_rpm": p_rpm, "prof_load": p_load, "prof_iq": p_iq, "prof_id": p_id,
                "phases": [(pt or {}).get("phase", "") for pt in points]}

    def _emit_frame(i, rows_i, ok):
        """Rendert frame_{i:04d}.png aus der aktuell in work/ liegenden VTU (vor dem nächsten Solve)."""
        if not make_video:
            return
        out_png = os.path.join(frames_dir, f"frame_{i:04d}.png")
        meta = {"idx": i, "n": n, "L": float(tags["L"]),
                "rpm": prof["prof_rpm"][i], "load": prof["prof_load"][i],
                "iq": prof["prof_iq"][i], "id": prof["prof_id"][i],
                "is_peak": (rows_i or {}).get("is_peak_A"),
                "b_gap": (rows_i or {}).get("b_gap_mid_peak"),
                "torque": (rows_i or {}).get("torque_Nm"),
                "phase": prof["phases"][i], "b_sat": B_SAT_DISPLAY_3D,
                "prof_rpm": prof["prof_rpm"], "prof_load": prof["prof_load"],
                "prof_iq": prof["prof_iq"], "prof_id": prof["prof_id"]}
        try:
            vtu = _find_vtu(work) if ok else None
            if vtu:
                grid = _read_grid(vtu); bname = _b_array_name(grid)
                if bname:
                    _video_frame(grid, bname, tags["dims"], meta, out_png); return
            _video_frame_fail(meta, out_png)
        except Exception as e:
            try: _video_frame_fail(meta, out_png)
            except Exception: pass
            _log(f"⚠ Video-Frame {i + 1} fehlgeschlagen: {e}", None)

    # Reihenfolge: alle Nicht-Detailpunkte zuerst, der Detailpunkt ZULETZT — so gehören die
    # im work/ verbleibenden VTU/Charts/VTP zum Detailpunkt (die /em3d/vtu|vtp|paraview-Routen
    # servieren genau diese Dateipfade).
    order = [i for i in range(n) if i != detail_index] + [detail_index]

    rows = [None] * n
    warnings = list(mesh_warns)
    detail_res = None
    aborted = False
    for k, i in enumerate(order):
        if _cancelled():                         # Abbruch VOR dem nächsten Solve
            aborted = True
            _log("⛔ Abbruch — beende mit dem bis hier gerechneten Teilergebnis.", None)
            break
        pt = points[i] or {}
        rpm = float(pt.get("rpm", 0.0) or 0.0)
        load_nm = float(pt.get("load_nm", 0.0) or 0.0)
        exc = pt.get("excitation") or ("loaded" if load_nm > 0 else "open_circuit")
        opts = dict(base_opts, rpm=rpm, load_nm=load_nm, excitation=exc)
        is_detail = (i == detail_index)
        pct = 40 + int(55.0 * k / max(n, 1))
        _log(f"▶ Punkt {k + 1}/{n}: {rpm:.0f} 1/min, {load_nm:.0f} Nm ({exc})"
             + (" — Detailpunkt (volles Feld)" if is_detail else ""), pct)
        try:
            res, op = _solve_point(geom, opts, tags, work, project_dir, _log,
                                   full=is_detail, pct=None,
                                   browser_stub=os.path.join(work, f"browser_{i}"))
        except _Em3dAborted:                     # Solve mitten im Punkt gekillt → Teilergebnis
            aborted = True
            _log("⛔ Punkt abgebrochen — beende mit dem Teilergebnis.", None)
            break
        except Exception as e:
            if _cancelled():                     # Abbruch löste den Fehler aus → kein „Fehlpunkt"
                aborted = True
                _log("⛔ Abgebrochen — beende mit dem Teilergebnis.", None)
                break
            warnings.append(f"Punkt {k + 1}/{n} ({rpm:.0f} 1/min, {load_nm:.0f} Nm) "
                            f"fehlgeschlagen: {e}")
            _log(f"⚠ Punkt {k + 1}/{n} fehlgeschlagen: {e}", None)
            rows[i] = {"rpm": rpm, "load_nm": load_nm, "excitation": exc,
                       "iq_A": None, "id_A": None, "is_peak_A": None,
                       "b_gap_mid_peak": None, "torque_Nm": None, "ok": False}
            _emit_frame(i, rows[i], ok=False)
            continue
        rows[i] = {"rpm": rpm, "load_nm": load_nm, "excitation": exc,
                   "iq_A": op.get("iq_A"), "id_A": op.get("id_A"),
                   "is_peak_A": op.get("is_peak_A"),
                   "b_gap_mid_peak": res.get("b_gap_mid_peak"),
                   "torque_Nm": res.get("torque_Nm"), "ok": True,
                   "vtp_path": res.get("vtp_path"), "lines_path": res.get("lines_path")}
        warnings.extend(res.get("warnings", []) or [])
        # Frame JETZT rendern — die case.vtu dieses Punkts wird beim nächsten Solve überschrieben.
        _emit_frame(i, rows[i], ok=True)
        if is_detail:
            _decorate_res(res, tags, opts, axial, op, mesh_warns)
            detail_res = res

    n_done = sum(1 for r in rows if r and r.get("ok"))
    if aborted:
        warnings.append(f"⛔ Abgebrochen — Teilergebnis mit {n_done} gerechneten Punkt(en) "
                        f"(von {n}). Verlaufskurven aus den fertigen Punkten; volles 3D-Feld nur, "
                        f"falls der Detailpunkt schon dran war.")
    _log("📈 Erzeuge Verlaufskurven über die Drehzahl…", 96)
    sweep_images = _sweep_charts(rows, project_dir)

    video_ok = False
    if make_video and not aborted:               # unvollständige Frames → kein Video beim Abbruch
        _log("🎬 Kodiere Lastprofil-Video (ffmpeg)…", 98)
        vid = _encode_video(frames_dir, fps=int(payload.get("video_fps", 6) or 6))
        video_ok = bool(vid)
        if not video_ok:
            warnings.append("Lastprofil-Video: ffmpeg fehlt oder Kodierung fehlgeschlagen "
                            "(Einzel-Frames liegen in frames_em3d/).")

    out = {
        "sweep": rows,
        "sweep_images": sweep_images,
        "sweep_vtp": [(rows[i] or {}).get("vtp_path") for i in range(n)],
        "sweep_lines": [(rows[i] or {}).get("lines_path") for i in range(n)],
        "detail": detail_res,
        "detail_index": detail_index,
        "axial_mm": axial,
        "video": video_ok,
        "mesh": {"n_nodes": tags["n_nodes"], "n_magnets": tags["n_magnets"],
                 "n_barriers": tags.get("n_barriers", 0), "bodies": tags["n_bodies"]},
        "mesh_zones": tags.get("mesh_zones", {}),
        "warnings": warnings,
        "aborted": aborted,
        "n_done": n_done,
    }
    # results.json: Sweep-Zeilen + (über den Detailpunkt) die normale em3d-Zusammenfassung.
    try:
        _persist_em3d_sweep(project_dir, out)
        if detail_res:
            _persist_em3d_summary(project_dir, detail_res)
    except Exception as e:
        out["warnings"].append(f"results.json-Merge fehlgeschlagen: {e}")

    _log("✓ Drehzahlband-Berechnung fertig", 100)
    return out


# ── ROI-Verfeinerung: Bereich besonderen Interesses höher auflösen ───────────────
# Der Nutzer markiert nach einem Grob-Lauf einen Quader (ROI). Statt eines echten
# Submodells mit BC-Übertragung (in diesem Elmer-Build nicht robust: ein auf der
# geschlossenen Box vorgegebenes, abgetastetes Motor-B-Feld erzeugt an den 12 Box-
# kanten widersprüchliche Kanten-A-Randwerte → Lösung explodiert, s. memory
# project_em3d_submodel_bc) wird das VOLLE Modell mit einer lokal feineren Box neu
# vernetzt und KOMPLETT neu gelöst (normaler Außenrand A×n=0). Das ist physikalisch
# exakt — im ROI sogar genauer als ein Submodell, weil es gar keinen BC-Transferfehler
# gibt — und kostet nur einen weiteren vollen Solve. Reuse von _prep_mesh/_solve_point/
# _decorate_res; das ROI-Box-Feld sitzt im Gmsh-Mesh-Builder (_build_mesh_once).


def run_em3d_refine(payload: dict, project_dir: str, progress_cb=None) -> dict:
    """ROI-Verfeinerung: volles Modell mit lokal feinerem Quader neu rechnen. ``payload`` =
    normaler 3D-Payload (geom + axial + Opts) + ``roi_box`` (xmin..zmax mm) + ``refine_factor``.
    KEINE BC-Übertragung — voller Re-Solve mit dem normalen Außenrand. Returns das übliche
    Ergebnis-Dict (gleicher Viewer-/Render-Pfad wie ``run_em3d``)."""
    import elmer_runner as ER

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    if not ER.ELMER_OK:
        raise RuntimeError(ER.INSTALL_HINT)

    geom = payload.get("geom", payload)
    axial = float(payload.get("axial_len") or payload.get("axialLen")
                  or geom.get("axialLen") or 120.0)
    roi = payload.get("roi_box") or payload.get("roi")
    if not roi:
        raise ValueError("Kein Verfeinerungsgebiet (roi_box) angegeben")
    rf = float(payload.get("refine_factor", 3.0) or 3.0)

    opts = _em3d_opts(payload)
    opts["roi_box"] = {k: float(roi[k]) for k in ("xmin", "xmax", "ymin", "ymax", "zmin", "zmax")}
    opts["roi_refine"] = rf

    work = os.path.join(project_dir, "em3d")          # gleicher Pfad → /em3d/vtu|vtp|paraview
    os.makedirs(work, exist_ok=True)

    _log(f"🔍 Verfeinerungsgebiet: lokale Box ×{rf:.1f}, volles Modell wird neu vernetzt…", 6)
    tags, mesh_warns = _prep_mesh(geom, axial, opts, work, _log)
    res, op = _solve_point(geom, opts, tags, work, project_dir, _log, full=True, pct=45)
    _log("📊 Werte Felder aus + vergleiche mit 2D…", 85)
    _decorate_res(res, tags, opts, axial, op, mesh_warns)
    res["source"] = "refine"
    res["roi"] = opts["roi_box"]
    res["refine_factor"] = rf

    try:
        _persist_em3d_summary(project_dir, res)
    except Exception as e:
        res.setdefault("warnings", []).append(f"results.json-Merge fehlgeschlagen: {e}")

    _log("✓ Verfeinerte 3D-Berechnung fertig", 100)
    return res


def _sweep_charts(rows, project_dir):
    """Verlaufsdiagramme über die Drehzahl (B_gap, Moment, i_q/i_d) für die berechneten
    Sweep-Punkte. Schreibt PNGs nach ``charts/em3d_sweep_*.png`` (Datei + base64)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64, io

    ok = [r for r in rows if r and r.get("ok")]
    if not ok:
        return []
    ok = sorted(ok, key=lambda r: r["rpm"])
    rpm = [r["rpm"] for r in ok]

    charts = os.path.join(project_dir, "charts")
    os.makedirs(charts, exist_ok=True)

    def _save(fig, name):
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="#0d0d0d")
        plt.close(fig)
        data = buf.getvalue()
        with open(os.path.join(charts, name), "wb") as f:
            f.write(data)
        return "data:image/png;base64," + base64.b64encode(data).decode()

    images = []

    def _vals(key):
        return [(r.get(key) if r.get(key) is not None else float("nan")) for r in ok]

    # B_gap (Mitte) über Drehzahl.
    fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
    ax.plot(rpm, _vals("b_gap_mid_peak"), "o-", color="#4fc3f7", lw=1.4)
    ax.set_xlabel("Drehzahl [1/min]"); ax.set_ylabel("B_gap (Mitte) [T]")
    ax.set_title("Luftspaltfeld über dem Drehzahlband", color="#ddd")
    ax.grid(alpha=.2); _style_dark(ax)
    images.append({"key": "em3d_sweep_bgap", "title": "B_gap über Drehzahl",
                   "b64": _save(fig, "em3d_sweep_bgap.png")})

    # Moment (Arkkio) über Drehzahl.
    fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
    ax.plot(rpm, _vals("torque_Nm"), "o-", color="#ff7043", lw=1.4)
    ax.set_xlabel("Drehzahl [1/min]"); ax.set_ylabel("Moment (Arkkio) [Nm]")
    ax.set_title("Moment über dem Drehzahlband", color="#ddd")
    ax.grid(alpha=.2); _style_dark(ax)
    images.append({"key": "em3d_sweep_torque", "title": "Moment über Drehzahl",
                   "b64": _save(fig, "em3d_sweep_torque.png")})

    # Statorströme i_q / i_d über Drehzahl (nur sinnvoll, wenn Lastpunkte dabei sind).
    if any(r.get("iq_A") is not None for r in ok):
        fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
        ax.plot(rpm, _vals("iq_A"), "o-", color="#81c784", lw=1.4, label="i_q")
        ax.plot(rpm, _vals("id_A"), "s-", color="#ba68c8", lw=1.4, label="i_d")
        ax.set_xlabel("Drehzahl [1/min]"); ax.set_ylabel("Strom [A]")
        ax.set_title("Statorströme über dem Drehzahlband", color="#ddd")
        ax.legend(fontsize=8); ax.grid(alpha=.2); _style_dark(ax)
        images.append({"key": "em3d_sweep_currents", "title": "i_q/i_d über Drehzahl",
                       "b64": _save(fig, "em3d_sweep_currents.png")})
    return images


def _persist_em3d_sweep(project_dir: str, out: dict):
    """Speichert die Sweep-Zeilen + Bild-Keys in ``results.json`` (Schlüssel ``em3d_sweep``),
    ohne base64 (die Charts liegen als Dateien in charts/)."""
    rj = os.path.join(project_dir, "results.json")
    data = {}
    if os.path.isfile(rj):
        try:
            with open(rj) as f:
                data = json.load(f)
        except Exception:
            data = {}
    # Transiente work/-VTP-Pfade NICHT in results.json schreiben (nur zur Laufzeit im
    # Server-State relevant) → results.json schlank halten.
    rows = [{k: v for k, v in (r or {}).items() if k not in ("vtp_path", "lines_path")}
            for r in out.get("sweep", [])]
    data["em3d_sweep"] = {
        "rows": rows,
        "detail_index": out.get("detail_index"),
        "axial_mm": out.get("axial_mm"),
        "mesh": out.get("mesh"),
        "mesh_zones": out.get("mesh_zones"),
        "warnings": out.get("warnings", []),
        "images": [{"key": im.get("key"), "title": im.get("title")}
                   for im in (out.get("sweep_images") or []) if im.get("key")],
    }
    with open(rj, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _persist_em3d_summary(project_dir: str, res: dict):
    """Speichert eine schlanke 3D-Zusammenfassung in ``results.json`` (Schlüssel ``em3d``),
    damit ``ema_report`` den 3D-Abschnitt deterministisch aufbauen kann."""
    rj = os.path.join(project_dir, "results.json")
    data = {}
    if os.path.isfile(rj):
        try:
            with open(rj) as f:
                data = json.load(f)
        except Exception:
            data = {}
    summary = {k: res.get(k) for k in (
        "b_gap_mid_peak", "b_gap_axial", "z_axial", "torque_arkkio_Nm",
        "torque_Nm", "torque_note", "operating_point",
        "compare_2d", "mesh", "mesh_zones", "axial_mm", "skew_deg",
        "skew_segments", "skew_step_deg", "warnings")}
    # Bild-Schlüssel+Titel (Dateien liegen in charts/) für den Bericht.
    summary["images"] = [{"key": im.get("key"), "title": im.get("title")}
                         for im in (res.get("images") or []) if im.get("key")]
    data["em3d"] = summary
    with open(rj, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ── Ein-Pol-Sektor (Symmetrie-Submodell) ─────────────────────────────────────────
# „Zweite Stufe": EINE Pol-Teilung wird als eigenständiges, FEINERES Modell gerechnet und
# über die Maschinensymmetrie zum vollen Motor gespiegelt. Die beiden Winkel-Schnittflächen
# sind ANTI-PERIODISCH gekoppelt (PMSM: Feld kehrt je Pol-Teilung das Vorzeichen um) — das ist
# durch die Symmetrie EXAKT, KEIN Feldtransfer nötig (im Gegensatz zum gescheiterten Box-
# Submodell). Empirisch validiert (Spike): Elmers generische `Periodic BC` + `Rotate` +
# `Scale=-1` + `Use Lagrange Coefficient` bindet die WhitneyAV-Kanten-DOF korrekt
# (Anti-Periodizität ~9 % im Eisen, kein Aufblasen). Außenränder = echtes `A×n=0` wie das
# Vollmodell. Weil die Domäne nur 1/(2p) groß ist, lässt sie sich bei gleicher Rechenzeit viel
# feiner vernetzen → „höher aufgelöst". Enthält Welle/Hohlwelle, Magnete (+ Taschen), Statornuten
# UND Flussbarrieren (Features als volle Prismen, per occ.intersect an den Keil geschnitten →
# q-Achsen-Features dürfen die Periodikfläche kreuzen). Das gespiegelte Voll-Feld bekommt dieselben
# 3D-Ansichten wie `run_em3d` (Bauteile + aufgeschnittenes |B|, über GeometryIds klassifiziert).
# v1-Scope: Leerlauf (nur Magnete), KEIN Skew/Spulenströme (das bleibt dem Vollmodell `run_em3d`).


def _build_sector_mesh(geom: dict, axial: float, opts: dict, msh_path: str) -> dict:
    """Baut das Mesh EINER Pol-Teilung (Welle + Rotoreisen + 1 Pol Magnete + Luftspalt +
    Statoreisen mit Nuten + **Flussbarrieren** + Luft), Pol mittig, anti-periodische
    Winkelflächen (Tags 901/902) + echter Außenrand `A×n=0` (Tag 900).

    Magnete/Nuten/Barrieren werden als VOLLE Prismen gebaut und per ``occ.intersect`` an die
    Keil-Domäne (``c_box``) geschnitten — so dürfen q-Achsen-Barrieren/Nuten die Periodikfläche
    KREUZEN (halbe Features an den Rändern, von der Periodizität ergänzt). Klassifikation über die
    Fragment-Map (welches Output-Volumen kam aus welchem Feature). **Gestufte Verfeinerung**:
    Luftspalt sehr fein (gap_cl), Magnete+Barrieren+Nuten fein mit Distanz-Auslauf (mag_cl→mesh_cl
    über mag_grow), Rest grob (mesh_cl) — per gmsh ``Min``-Feld. Returns ``tags`` analog
    ``_build_mesh_once`` + ``master_pid``/``slave_pid``/``outer_pid``/``alpha``/``PC``/``poles``."""
    import gmsh

    L = float(axial)
    r_shaft = geom["shaftD"] / 2.0
    r_bore = max(float(geom.get("shaftBoreD", 0.0) or 0.0) / 2.0, 0.0)   # Hohlwelle (0=voll)
    if r_bore >= r_shaft - 0.5:
        r_bore = 0.0
    r_rot = geom["rotorOD"] / 2.0
    r_si = geom["statorID"] / 2.0
    r_so = geom["statorOD"] / 2.0
    poles = int(geom["p"]) * 2
    alpha = 2 * math.pi / poles
    PC = alpha / 2.0                                     # Pol mittig
    box_f = float(opts.get("airbox_factor", 1.4)); R_box = box_f * r_so
    cap = float(opts.get("cap_frac", 0.35)) * L
    mesh_cl = float(opts.get("mesh_cl", 0.0)) or max(1.0, r_so / 26.0)
    gap = max(0.3, r_si - r_rot)
    gap_cl = float(opts.get("gap_cl", 0.0)) or max(0.25, gap * 0.5)
    mag_cl = float(opts.get("mag_cl", 0.0)) or max(gap_cl, mesh_cl * 0.5)
    mag_grow = float(opts.get("mag_grow", 0.0)) or max(2.0, 3.0 * gap)

    cosP, sinP = math.cos(PC), math.sin(PC)

    def _rot(cx, cy):
        return cx * cosP - cy * sinP, cx * sinP + cy * cosP

    def _keep(cx, cy, margin):
        a = math.atan2(cy, cx)
        return -margin <= a <= alpha + margin

    # Magnete EINER Pol-Teilung (Pol 0), in die Sektor-Mitte PC gedreht.
    mags = []
    for m in magnet_rects(geom):
        if m.get("pole", 0) != 0:
            continue
        cx, cy = _rot(m["cx"], m["cy"]); mdx, mdy = _rot(m["mdx"], m["mdy"])
        mags.append({"cx": cx, "cy": cy, "ang": m["ang"] + PC, "length": m["length"],
                     "thick": max(0.8, m["thick"]), "sign": m["sign"], "mdx": mdx, "mdy": mdy})
    # Nuten + Barrieren um die Sektor-Mitte (inkl. Rand-Straddler — Clipping schneidet sie sauber).
    n_slots = int(geom.get("slots", 0) or 0)
    dth = (2 * math.pi / n_slots) if n_slots > 0 else alpha
    slots = []
    for s in slot_rects(geom):
        cx, cy = _rot(s["cx"], s["cy"])
        if _keep(cx, cy, 0.5 * dth):
            slots.append({"cx": cx, "cy": cy, "ang": s["ang"] + PC,
                          "length": s["length"], "thick": s["thick"]})
    bars = []
    for bd in barrier_rects(geom):
        cx, cy = _rot(bd["cx"], bd["cy"])
        if _keep(cx, cy, 0.5 * alpha):
            bars.append({"cx": cx, "cy": cy, "ang": bd["ang"] + PC,
                         "length": bd["length"], "thick": bd["thick"]})

    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        gmsh.model.add("sector3d")
        occ = gmsh.model.occ

        c_shaft = occ.addCylinder(0, 0, 0, 0, 0, L, r_shaft, angle=alpha)
        c_rot = occ.addCylinder(0, 0, 0, 0, 0, L, r_rot, angle=alpha)
        c_si = occ.addCylinder(0, 0, 0, 0, 0, L, r_si, angle=alpha)
        c_so = occ.addCylinder(0, 0, 0, 0, 0, L, r_so, angle=alpha)
        c_box = occ.addCylinder(0, 0, -cap, 0, 0, L + 2 * cap, R_box, angle=alpha)
        c_bore = occ.addCylinder(0, 0, 0, 0, 0, L, r_bore, angle=alpha) if r_bore > 0 else None

        def _prism(cx, cy, ang, length, thick):
            hl, ht = length / 2.0, thick / 2.0
            ca, sa = math.cos(ang), math.sin(ang)
            pts = []
            for ex, ey in ((-hl, -ht), (hl, -ht), (hl, ht), (-hl, ht)):
                pts.append(occ.addPoint(cx + ex * ca - ey * sa, cy + ex * sa + ey * ca, 0))
            ls = [occ.addLine(pts[i], pts[(i + 1) % 4]) for i in range(4)]
            sf = occ.addPlaneSurface([occ.addCurveLoop(ls)])
            return [e[1] for e in occ.extrude([(2, sf)], 0, 0, L) if e[0] == 3][0]

        # Features bauen + an die Keil-Domäne c_box schneiden (Tool behalten → c_box bleibt).
        feat = []                                        # (tag, kind, meta)
        for spec, kind in ([(m, "magnet") for m in mags]
                           + [(s, "air") for s in slots] + [(b, "air") for b in bars]):
            t = _prism(spec["cx"], spec["cy"], spec["ang"], spec["length"], spec["thick"])
            out, _ = occ.intersect([(3, t)], [(3, c_box)], removeObject=True, removeTool=False)
            for d, tt in out:
                if d == 3:
                    feat.append((tt, kind, spec))
        occ.synchronize()

        objs = [(3, c_shaft)]
        fixed = [(3, c_rot), (3, c_si), (3, c_so), (3, c_box)]
        if c_bore is not None:
            fixed.append((3, c_bore))                    # Hohlwellen-Bohrung mitfragmenten
        tools = fixed + [(3, t) for t, _, _ in feat]
        _ov, ovv = occ.fragment(objs, tools)
        occ.synchronize()
        nfix = 1 + len(fixed)                            # objs(1) + feste Zylinder; Features ab hier
        feat_vols = {}                                   # vol-tag → (kind, meta, feat_index)
        for j, (_t, kind, meta) in enumerate(feat):
            for (d, tt) in ovv[nfix + j]:
                if d == 3:
                    feat_vols[tt] = (kind, meta, j)
        vols = [t for d, t in gmsh.model.getEntities(3)]

        def _com(v):
            x, y, z = occ.getCenterOfMass(3, v); return x, y, z, math.hypot(x, y)

        groups = {"shaft": [], "rotor": [], "stator": [], "air": []}
        mag_groups = {}                                  # feat_index → [vols] (ein Magnetkörper)
        for v in vols:
            if v in feat_vols:
                kind, meta, j = feat_vols[v]
                if kind == "magnet":
                    mag_groups.setdefault(j, {"vols": [], "meta": meta})["vols"].append(v)
                else:
                    groups["air"].append(v)
                continue
            x, y, z, r = _com(v)
            if z < -1e-6 or z > L + 1e-6 or r > r_so + 0.5:
                groups["air"].append(v)
            elif r_bore > 0 and r < r_bore:
                groups["air"].append(v)                  # Hohlwellen-Bohrung (Luft)
            elif r < r_shaft:
                groups["shaft"].append(v)
            elif r < r_rot:
                groups["rotor"].append(v)
            elif r < r_si:
                groups["air"].append(v)                  # Luftspalt
            else:
                groups["stator"].append(v)

        tags = {"bodies": {}, "magnets": [], "coils": [], "L": L,
                "dims": {"r_shaft": r_shaft, "r_bore": r_bore, "r_rot": r_rot, "r_si": r_si,
                         "r_so": r_so, "R_box": R_box, "cap": cap}}
        bid = 1
        for name in ("shaft", "rotor", "stator", "air"):
            if groups[name]:
                gmsh.model.addPhysicalGroup(3, groups[name], bid); tags["bodies"][name] = bid; bid += 1
        for j, g in mag_groups.items():
            m = g["meta"]
            gmsh.model.addPhysicalGroup(3, g["vols"], bid)
            tags["magnets"].append({"name": f"magnet_{j}", "phys": bid, "mdx": m["mdx"],
                                    "mdy": m["mdy"], "sign": m["sign"], "pole": 0})
            bid += 1

        # Feinflächen (Magnete + Barrieren + Nuten) für die gestufte Verfeinerung.
        fine_surfs = set()
        for v in feat_vols:
            for d, s in gmsh.model.getBoundary([(3, v)], oriented=False):
                if d == 2:
                    fine_surfs.add(abs(s))

        # Randflächen: Winkelflächen θ=0 (Master) / θ=α (Slave) + Außenrand. Mehrere Flächen je
        # Seite (von Features zerschnitten) → Master↔Slave nach (r,z) des Schwerpunkts paaren.
        # SELEKTION über die SENKRECHTE ABSTAND zur jeweiligen Halbebene (NICHT über den Winkel —
        # ein Winkel-Toleranzfenster fängt schräge Feature-Seitenflächen mit ⇒ unpaarige Ränder).
        nsx, nsy = -math.sin(alpha), math.cos(alpha)     # Normale der Slave-Halbebene (θ=α) in xy
        master, slave, outer = [], [], []
        TOL = 0.4
        for d, sfc in gmsh.model.getEntities(2):
            x, y, z = occ.getCenterOfMass(2, sfc)
            rr = math.hypot(x, y)
            if abs(y) < TOL and x > TOL:                 # θ=0-Halbebene (y=0, x>0)
                master.append(sfc)
            elif abs(nsx * x + nsy * y) < TOL and (x * math.cos(alpha) + y * math.sin(alpha)) > TOL:
                slave.append(sfc)                        # θ=α-Halbebene (Senkrechtabstand ≈ 0)
            elif rr > R_box - 1.0 or z < -cap + 0.5 or z > L + cap - 0.5:
                outer.append(sfc)

        def _skey(sfc):
            x, y, z = occ.getCenterOfMass(2, sfc); return (round(math.hypot(x, y), 2), round(z, 2))
        master_s = sorted(master, key=_skey); slave_s = sorted(slave, key=_skey)
        ca, sa = math.cos(alpha), math.sin(alpha)
        aff = [ca, -sa, 0, 0,  sa, ca, 0, 0,  0, 0, 1, 0,  0, 0, 0, 1]
        if master_s and len(master_s) == len(slave_s):
            try:
                gmsh.model.mesh.setPeriodic(2, slave_s, master_s, aff)
            except Exception as e:
                tags.setdefault("warnings", []).append(f"setPeriodic: {e}")
        else:
            tags.setdefault("warnings", []).append(
                f"Periodikflächen unpaarig (Master {len(master_s)} / Slave {len(slave_s)})")
        gmsh.model.addPhysicalGroup(2, outer, 900); tags["outer_pid"] = 900
        gmsh.model.addPhysicalGroup(2, master, 901); tags["master_pid"] = 901
        gmsh.model.addPhysicalGroup(2, slave, 902); tags["slave_pid"] = 902

        # Gestufte Verfeinerung: ① Luftspalt SEHR fein (Gauß-Band gap_cl), ② Magnete/Barrieren/
        # Nuten FEIN mit Distanz-Auslauf (mag_cl→mesh_cl über mag_grow), ③ Rest grob (mesh_cl).
        fld = gmsh.model.mesh.field
        fields = []
        rmid = (r_rot + r_si) / 2.0; wgap = max(1.0, gap * 1.5)
        u = f"((sqrt(x*x+y*y)-{rmid})/{wgap})"
        fg = fld.add("MathEval")
        fld.setString(fg, "F", f"{gap_cl}+{max(0.0, mesh_cl-gap_cl)}*(1-exp(-{u}*{u}))")
        fields.append(fg)
        if fine_surfs:
            fdist = fld.add("Distance")
            fld.setNumbers(fdist, "SurfacesList", [float(s) for s in fine_surfs])
            fthr = fld.add("Threshold")
            fld.setNumber(fthr, "InField", fdist)
            fld.setNumber(fthr, "SizeMin", mag_cl)
            fld.setNumber(fthr, "SizeMax", mesh_cl)
            fld.setNumber(fthr, "DistMin", 0.0)
            fld.setNumber(fthr, "DistMax", mag_grow)
            fields.append(fthr)
        if len(fields) > 1:
            fmin = fld.add("Min")
            fld.setNumbers(fmin, "FieldsList", [float(f) for f in fields])
            fld.setAsBackgroundMesh(fmin)
        else:
            fld.setAsBackgroundMesh(fields[0])
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(gap_cl, mag_cl))
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_cl)
        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)
        gmsh.write(msh_path)

        tags["n_nodes"] = len(gmsh.model.mesh.getNodes()[0])
        tags["n_magnets"] = len(tags["magnets"])
        tags["n_slots"] = len(slots)
        tags["n_barriers"] = len(bars)
        tags["n_bodies"] = {k: len(v) for k, v in groups.items()}
        tags["alpha"] = alpha; tags["PC"] = PC; tags["poles"] = poles
        tags["mesh_zones"] = {"gap_cl": gap_cl, "mag_cl": mag_cl, "mesh_cl": mesh_cl,
                              "mag_grow": mag_grow}
        return tags
    finally:
        gmsh.finalize()


def write_sector_sif(geom: dict, tags: dict, work_dir: str, opts: dict, mesh_name: str = "mesh") -> str:
    """``case.sif`` für den Ein-Pol-Sektor: Magnete als Innenquellen, anti-periodische
    Winkelflächen (`Periodic BC` + `Rotate` + `Scale=-1` + Lagrange), Außenrand `A×n=0`.
    KEINE Coordinate Scaling (mm wie das Vollmodell; Magnetostatik ist skaleninvariant)."""
    from ema_pipeline import MAGNETS
    mag = MAGNETS.get(geom.get("magnet", "ndfeb_n35"), MAGNETS["ndfeb_n35"])
    Hc = float(mag["Br"]) / MU0
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)
    surf_pids = sorted([tags["outer_pid"], tags["master_pid"], tags["slave_pid"]])
    o_id = surf_pids.index(tags["outer_pid"]) + 1
    m_id = surf_pids.index(tags["master_pid"]) + 1
    s_id = surf_pids.index(tags["slave_pid"]) + 1
    alpha_deg = math.degrees(tags["alpha"])
    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n  Max Output Level = 4\n  Coordinate System = Cartesian\n"
         "  Simulation Type = Steady State\n  Steady State Max Iterations = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0}\nEnd\n",
         'Solver 1\n  Equation = "MgDyn"\n  Procedure = "MagnetoDynamics" "WhitneyAVSolver"\n'
         '  Variable = "AV"\n  Use Tree Gauge = Logical True\n'
         '  Linear System Solver = Direct\n  Linear System Direct Method = MUMPS\n'
         '  Nonlinear System Max Iterations = 1\nEnd\n',
         'Solver 2\n  Equation = "MgDynCalc"\n  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"\n'
         '  Potential Variable = "AV"\n  Calculate Magnetic Flux Density = True\n'
         '  Linear System Solver = Iterative\n  Linear System Iterative Method = CG\n'
         '  Linear System Preconditioning = ILU0\n  Linear System Max Iterations = 5000\n'
         '  Linear System Convergence Tolerance = 1.0e-8\nEnd\n',
         'Solver 3\n  Equation = "ResultOutput"\n  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
         '  Output File Name = "case"\n  Output Directory = "results"\n  Vtu Format = Logical True\n'
         '  Save Geometry Ids = Logical True\nEnd\n',
         "Equation 1\n  Active Solvers(2) = 1 2\nEnd\n",
         f'Material 1\n  Name = "iron"\n  Relative Permeability = {MU_R_IRON}\nEnd\n',
         'Material 2\n  Name = "air"\n  Relative Permeability = 1.0\nEnd\n',
         f'Material 3\n  Name = "magnet"\n  Relative Permeability = {MU_R_MAG}\nEnd\n']
    b = tags["bodies"]
    for name in ("shaft", "rotor", "stator"):
        if name in b:
            S.append(f'Body {b[name]}\n  Name = "{name}"\n  Equation = 1\n  Material = 1\nEnd\n')
    if "air" in b:
        S.append(f'Body {b["air"]}\n  Name = "air"\n  Equation = 1\n  Material = 2\nEnd\n')
    bf = 1
    for m in tags["magnets"]:
        mx = Hc * m["sign"] * m["mdx"]; my = Hc * m["sign"] * m["mdy"]
        S.append(f'Body {m["phys"]}\n  Name = "{m["name"]}"\n  Equation = 1\n'
                 f'  Material = 3\n  Body Force = {bf}\nEnd\n')
        S.append(f'Body Force {bf}\n  Magnetization 1 = Real {mx:.6e}\n'
                 f'  Magnetization 2 = Real {my:.6e}\n  Magnetization 3 = Real 0.0\nEnd\n')
        bf += 1
    # Außenrand: A×n=0 (Kanten + nodal), wie das Vollmodell.
    S.append(f'Boundary Condition {o_id}\n  Target Boundaries(1) = {o_id}\n'
             '  AV {e} = Real 0\n  AV = Real 0\nEnd\n')
    # Anti-periodische Winkelflächen: Slave = −(Master um α gedreht).
    S.append(f'Boundary Condition {s_id}\n  Target Boundaries(1) = {s_id}\n'
             f'  Periodic BC = {m_id}\n  Periodic BC Rotate(3) = 0 0 {alpha_deg:.10f}\n'
             '  Periodic BC Scale = Real -1.0\n  Periodic BC Use Lagrange Coefficient = Logical True\nEnd\n')
    sif = os.path.join(work_dir, "case.sif")
    open(sif, "w").write("\n".join(S))
    return sif


def _pattern_full_motor(sgrid, tags):
    """Spiegelt das Ein-Pol-Feld über die Symmetrie zum VOLLEN Motor: 2p Kopien, je um k·α um
    die Achse gedreht, B-Vektor mitgedreht und anti-periodisch mit (−1)^k vorzeichengewendet.
    GeometryIds (Body-Ids) bleiben je Kopie erhalten → der Browser-Export maskiert weiter sauber.
    Sektor-VTU ist in mm (keine Coordinate Scaling) → keine Skalierung nötig."""
    import vtk
    from vtk.util import numpy_support as ns
    bname = _b_array_name(sgrid)
    B0 = ns.vtk_to_numpy(sgrid.GetPointData().GetArray(bname)).reshape(-1, 3)
    alpha = tags["alpha"]; poles = tags["poles"]
    app = vtk.vtkAppendFilter(); app.MergePointsOff()
    keep = []
    for k in range(poles):
        ang = k * alpha; c, s = math.cos(ang), math.sin(ang)
        tf = vtk.vtkTransform(); tf.RotateZ(math.degrees(ang))
        tfil = vtk.vtkTransformFilter(); tfil.SetTransform(tf); tfil.SetInputData(sgrid); tfil.Update()
        g = vtk.vtkUnstructuredGrid(); g.DeepCopy(tfil.GetOutput())
        Br = np.empty_like(B0)
        Br[:, 0] = c * B0[:, 0] - s * B0[:, 1]
        Br[:, 1] = s * B0[:, 0] + c * B0[:, 1]
        Br[:, 2] = B0[:, 2]
        if k % 2:
            Br = -Br
        g.GetPointData().RemoveArray(bname)
        arr = ns.numpy_to_vtk(np.ascontiguousarray(Br)); arr.SetName(bname)
        g.GetPointData().AddArray(arr); g.GetPointData().SetActiveVectors(bname)
        keep.append(g); app.AddInputData(g)
    app.Update()
    return app.GetOutput()


def _sector_results(work, geom, tags, project_dir, opts):
    """Wertet den Sektor-Solve aus: spiegelt zum vollen Motor, Luftspalt-Kennwerte + Endeffekt +
    Schnittbild + Browser-VTP/Feldlinien (alles am vollen Motor), 2D-Vergleich, |B|-Statistik."""
    import base64, vtk
    from vtk.util import numpy_support as ns
    res = {"source": "sector", "warnings": [], "axial_mm": tags["L"], "poles": tags["poles"],
           "mesh": {"n_nodes": tags["n_nodes"], "n_magnets": tags["n_magnets"],
                    "n_barriers": tags.get("n_barriers", 0), "n_slots": tags.get("n_slots", 0),
                    "bodies": tags["n_bodies"]},
           "mesh_zones": tags.get("mesh_zones", {}), "images": []}
    vtu = _find_vtu(work)
    if not vtu:
        res["warnings"].append("Sektor: keine VTU-Ausgabe von Elmer."); return res
    sgrid = _read_grid(vtu); bname = _b_array_name(sgrid)
    if not bname:
        res["warnings"].append("Sektor: kein B-Feld in der VTU."); return res

    # Validierung: Anti-Periodizität (Master θ=0 ↔ Slave θ=α, erwartet B_slave=−R_α·B_master).
    # Gemessen im STATORJOCH (glattes, starkes Eisen ÜBER den Nuten) über mehrere Radien × z —
    # NICHT im Luftspalt/Nutband/Magnetbereich (dort verrauscht die grobe Abtastung den Wert auf
    # >100 %, obwohl die BC im starken Eisen ~5–7 % trifft). MEDIAN = robust gegen Ausreißer.
    try:
        d = tags["dims"]; al = tags["alpha"]; L = tags["L"]
        ca, sa = math.cos(al), math.sin(al)
        sd = min(float(geom.get("slotDepth", 0) or 0), max(1.0, (d["r_so"] - d["r_si"]) - 1.0))
        slot_out = d["r_si"] + sd
        rlo, rhi = slot_out + 1.5, d["r_so"] - 1.5
        if rhi - rlo < 2.0:                                   # dünnes Joch → Rotoreisen-Außenband
            rlo, rhi = 0.6 * d["r_rot"], 0.85 * d["r_rot"]
        errs = []
        for r in np.linspace(rlo, rhi, 5):
            for z in (0.35 * L, 0.5 * L, 0.65 * L):
                Bm = _probe(sgrid, np.array([[r, 0.0, z]]), bname)[0]
                Bs = _probe(sgrid, np.array([[r * ca, r * sa, z]]), bname)[0]
                Rm = np.array([ca * Bm[0] - sa * Bm[1], sa * Bm[0] + ca * Bm[1], Bm[2]])
                if np.linalg.norm(Bm) > 0.05:
                    errs.append(np.linalg.norm(Bs + Rm) / np.linalg.norm(Rm))
        if errs:
            res["antiperiodic_err"] = round(float(np.median(errs)), 3)
    except Exception as e:
        res["warnings"].append(f"Anti-Periodizitäts-Check: {e}")

    # Zum vollen Motor spiegeln; ab hier alles am vollen Feld.
    full = _pattern_full_motor(sgrid, tags)
    fvtu = os.path.join(work, "results", "sector_full.vtu")
    w = vtk.vtkXMLUnstructuredGridWriter(); w.SetFileName(fvtu); w.SetInputData(full)
    w.SetDataModeToBinary(); w.Write()
    res["vtu_path"] = fvtu

    try:
        Bv = ns.vtk_to_numpy(full.GetPointData().GetArray(bname)).reshape(-1, 3)
        mg = np.linalg.norm(Bv, axis=1)
        res["b_stats"] = {"min": round(float(mg.min()), 4), "max": round(float(mg.max()), 4),
                          "mean": round(float(mg.mean()), 4)}
    except Exception as e:
        res["warnings"].append(f"Statistik: {e}")

    m = _gap_field_metrics(full, bname, tags)
    th = m.pop("_th"); br_mid = m.pop("_br_mid"); z_levels = m.pop("_z_levels_arr")
    res.update(m)

    charts = os.path.join(project_dir, "charts"); os.makedirs(charts, exist_ok=True)
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt, io

    def _savefig(fig, name):
        buf = io.BytesIO(); fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", facecolor="#0d0d0d")
        plt.close(fig)
        with open(os.path.join(charts, name), "wb") as f:
            f.write(buf.getvalue())
        return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()

    def _savebytes(data, name):
        with open(os.path.join(charts, name), "wb") as f:
            f.write(data)
        return "data:image/png;base64," + base64.b64encode(data).decode()

    # 2D-Vergleich (FDM) — wie parse_results.
    try:
        import ema_analysis
        em2d = ema_analysis.run_em_analysis(geom, N=int(opts.get("n2d", 360)), rotor_angle=0.0)
        br2d = np.asarray(em2d["Br_gap"]); th2d = np.linspace(0, 2 * np.pi, len(br2d), endpoint=False)
        res["compare_2d"] = {"B_gap_2D": round(float(np.max(np.abs(br2d))), 3),
                             "B_gap_3D_mid": res.get("b_gap_mid_peak")}
        fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
        ax.plot(np.degrees(th2d), br2d, label="2D-FDM (∞ lang)", color="#4fc3f7", lw=1.4)
        ax.plot(np.degrees(th), br_mid, label="3D Sektor (z=L/2)", color="#ff7043", lw=1.4)
        ax.set_xlabel("Umfangswinkel θ [°]"); ax.set_ylabel("B_r Luftspalt [T]")
        ax.set_title("Luftspalt-Radialfeld: 2D vs 3D-Sektor", color="#ddd")
        ax.legend(fontsize=8); ax.grid(alpha=.2); _style_dark(ax)
        res["images"].append({"key": "em3d_airgap_2d3d", "title": "Luftspalt 2D vs 3D",
                              "b64": _savefig(fig, "em3d_airgap_2d3d.png")})
    except Exception as e:
        res["warnings"].append(f"2D-Vergleich: {e}")

    # Endeffekt + |B|-Schnitt + Browser-Export (alles am vollen Motor).
    try:
        fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
        ax.plot(z_levels, res["b_gap_axial"], "o-", color="#81c784", lw=1.4)
        ax.set_xlabel("axiale Position z [mm]"); ax.set_ylabel("Peak |B_r| [T]")
        ax.set_title("Endeffekt: Luftspaltfeld über der Paketlänge", color="#ddd")
        ax.grid(alpha=.2); _style_dark(ax)
        res["images"].append({"key": "em3d_endeffect", "title": "Endeffekt B(z)",
                              "b64": _savefig(fig, "em3d_endeffect.png")})
    except Exception as e:
        res["warnings"].append(f"Endeffekt-Chart: {e}")
    try:
        res["images"].append({"key": "em3d_slice_mid", "title": "|B| Schnitt z=L/2",
                              "b64": _slice_image(full, bname, tags["L"] / 2.0, tags["dims"], _savefig)})
    except Exception as e:
        res["warnings"].append(f"Schnittbild: {e}")
    # Echte 3D-Ansichten des VOLLEN (gespiegelten) Motors — wie das Vollmodell, damit Welle,
    # Magnete, Nuten/Zähne, Magnettaschen und Luftspalt sichtbar werden (über die GeometryIds
    # klassifiziert; das Sektor-VTU trägt sie, ein Mesh-.vtk wird nicht gepatternt).
    try:
        cls_full = _classify_grid_gids(full, tags)
        if cls_full is not None:
            res["images"] = (_render_geometry_views(cls_full, tags["L"], tags["dims"]["r_so"],
                                                    _savebytes) + res["images"])
    except Exception as e:
        res["warnings"].append(f"3D-Geometrie-Ansicht: {e}")
    try:
        res["images"].append(render_field_3d(full, bname, tags, _savebytes))
    except Exception as e:
        res["warnings"].append(f"3D-Feld-Ansicht: {e}")
    try:
        vtp = os.path.join(work, "sector_browser.vtp")
        export_browser_vtp(full, bname, tags, vtp); res["vtp_path"] = vtp
        lines = os.path.join(work, "sector_browser_lines.vtp")
        export_browser_streamlines(full, bname, tags, lines); res["lines_path"] = lines
    except Exception as e:
        res["warnings"].append(f"Browser-Export: {e}")
    return res


def run_em3d_sector(payload: dict, project_dir: str, progress_cb=None) -> dict:
    """Ein-Pol-Sektor mit Anti-Periodizität, zum vollen Motor gespiegelt. ``payload`` = normaler
    3D-Payload (geom + axial + Opts). Robustes, schnelles, FEINES Symmetrie-Submodell (Leerlauf).
    Returns das übliche Ergebnis-Dict (gleicher Viewer-/Render-Pfad wie ``run_em3d``)."""
    import elmer_runner as ER

    def _log(msg, pct=None):
        if progress_cb:
            progress_cb(msg, pct)

    if not ER.ELMER_OK:
        raise RuntimeError(ER.INSTALL_HINT)
    geom = payload.get("geom", payload)
    axial = float(payload.get("axial_len") or payload.get("axialLen") or geom.get("axialLen") or 120.0)
    opts = _em3d_opts(payload)
    work = os.path.join(project_dir, "em3d"); os.makedirs(work, exist_ok=True)

    _log("🔁 Baue Ein-Pol-Sektor (Symmetrie, fein)…", 8)
    msh = os.path.join(work, "sector.msh")
    # Knoten-KONTINGENT (einstellbar): das Tortenstück ist nur 1/(2p) des Modells → so fein wie
    # gewünscht. ``node_budget_pct`` (10–100 %, 100 % = EM3D_MAX_NODES) skaliert das Ziel; die
    # Zielsuche verfeinert/vergröbert (n ~ h^-1.85 → Skalenfaktor (n/Ziel)^(1/1.85) auf alle
    # Zonengrößen gap/mag/mesh, damit die Abstufungen Luftspalt < Magnet/Barriere < grob bleiben).
    pct = float(payload.get("node_budget_pct") or opts.get("node_budget_pct") or 100.0)
    pct = min(100.0, max(10.0, pct))
    cap = int(EM3D_MAX_NODES * pct / 100.0)
    res_budget_pct = pct
    target = int(cap * 0.9)                               # etwas Luft unter dem Kontingent
    _log(f"   Knoten-Kontingent {pct:.0f} % → Ziel ~{target} Knoten (Tortenstück)", None)
    o = dict(opts); tags = None
    for attempt in range(4):
        tags = _build_sector_mesh(geom, axial, o, msh)
        n = tags["n_nodes"]
        if 0.6 * cap <= n <= cap:                         # im Zielband → fertig
            break
        if n > cap or (n < 0.6 * cap and attempt < 3):    # zu fein ODER unausgereizt → nachregeln
            f = (n / target) ** (1.0 / 1.85)
            f = min(2.2, max(0.55, f))                    # pro Schritt begrenzen
            mz = tags["mesh_zones"]
            o = dict(o, mesh_cl=mz["mesh_cl"] * f, gap_cl=mz["gap_cl"] * f,
                     mag_cl=mz["mag_cl"] * f, mag_grow=mz["mag_grow"])
            _log(f"   Sektor-Netz {n} Knoten → Zielband ~{target} (Zonengrößen ×{f:.2f})…", None)
            if n > cap:
                continue
            # unter dem Ziel: einmal verfeinern, dann das Ergebnis nehmen (nicht überschießen).
            tags = _build_sector_mesh(geom, axial, o, msh)
            if tags["n_nodes"] > cap:                     # überschossen → zurück auf groberes Netz
                tags = _build_sector_mesh(geom, axial, dict(o, mesh_cl=o["mesh_cl"] / f * 1.15,
                                                            gap_cl=o["gap_cl"] / f * 1.15,
                                                            mag_cl=o["mag_cl"] / f * 1.15), msh)
            break
    mz = tags["mesh_zones"]
    _log(f"✓ Sektor (Tortenstück): {tags['n_nodes']} Knoten, {tags['n_magnets']} Magnete, "
         f"{tags['n_slots']} Nuten, {tags['n_barriers']} Barrieren (1 von {tags['poles']} Polen); "
         f"Zonen Luftspalt {mz['gap_cl']:.2f} / Magnet+Barriere+Nut {mz['mag_cl']:.2f} / grob "
         f"{mz['mesh_cl']:.2f} mm", 32)
    rg = ER.run_elmergrid(msh, os.path.join(work, "mesh"))
    if not rg["ok"]:
        raise RuntimeError("ElmerGrid (Sektor): " + (rg.get("stderr") or rg.get("error", ""))[:300])
    write_sector_sif(geom, tags, work, opts, mesh_name="mesh")
    _log("🧲 ElmerSolver: feine Pol-Magnetostatik (anti-periodisch)…", 50)
    rs = ER.run_elmersolver(os.path.join(work, "case.sif"), work)
    if not rs["ok"]:
        raise RuntimeError("ElmerSolver (Sektor): " + (rs.get("stderr") or rs.get("error", ""))[:300]
                           + "\n" + (rs.get("stdout", "")[-400:]))
    _log("🪞 Spiegele Pol → voller Motor + werte aus…", 84)
    res = _sector_results(work, geom, tags, project_dir, opts)
    res["axial_mm"] = axial
    res["node_budget_pct"] = round(res_budget_pct, 0)
    res["node_budget_max"] = EM3D_MAX_NODES
    if res.get("antiperiodic_err") is not None:
        _log(f"   Anti-Periodizität im Eisen: {res['antiperiodic_err']*100:.1f}% "
             "(0 = exakt; Rest = Netzgröße)", None)
    try:
        _persist_em3d_summary(project_dir, res)
    except Exception as e:
        res.setdefault("warnings", []).append(f"results.json-Merge: {e}")
    _log("✓ Sektor-Berechnung fertig (voller Motor gespiegelt)", 100)
    return res
