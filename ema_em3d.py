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

import math
import os
import json

import numpy as np

import ema_topology as TOPO

MU0 = 1.2566370614e-6           # Vakuumpermeabilität [H/m]
MU_R_IRON = 500.0               # lineares Eisen (wie 2D), BH-Kurve = Folgeschritt
MU_R_MAG = 1.05


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
                        "mdx": mdx, "mdy": mdy})
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

def build_mesh(geom: dict, axial: float, opts: dict, msh_path: str) -> dict:
    """Baut das 3D-Mesh und schreibt ``msh_path`` (MSH 2.2 für ElmerGrid).

    3D-Primitive (Zylinder je Radius + Magnet-Extrusionen + Luft-Box) → ``occ.fragment``
    (konform) → Physical-Volumes per Schwerpunkt/Radius/z getaggt. Skew via tordierter
    Magnet-Extrusion. Returns ``tags`` = {bodies, magnets, coils, boundary, L, dims}.
    """
    import gmsh

    L = float(axial)
    r_shaft = geom["shaftD"] / 2.0
    r_rot = geom["rotorOD"] / 2.0
    r_si = geom["statorID"] / 2.0
    r_so = geom["statorOD"] / 2.0
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

        # Gerades Vollprisma 0..L (für Statornuten: die rotieren NICHT mit dem Rotor mit).
        def _extrude_straight(pc):
            w0 = _rect_loop(pc["cx"], pc["cy"], 0.0, pc["ang"], pc["length"], pc["thick"])
            w1 = _rect_loop(pc["cx"], pc["cy"], L, pc["ang"], pc["length"], pc["thick"])
            sec = occ.addThruSections([w0, w1], -1, True, True)
            vol = [d for d in sec if d[0] == 3]
            return vol[0][1] if vol else None

        rects = magnet_rects(geom)
        # Gestaffelte Schrägung: jeden Magneten in K verdrehte axiale Prismen schneiden.
        pieces, n_seg, _seg_step = _magnet_pieces(rects, L, opts)
        mag_vol_tags = [_extrude(pc) for pc in pieces]

        # Flussbarrieren (parametrisch q/d + custom) als LUFT-Prismen, mit der gleichen
        # Staffelung (rotieren mit dem Blechpaket). Werden in den Rotor gefragmentet.
        brects = barrier_rects(geom)
        bpieces, _bn, _bs = _magnet_pieces(brects, L, opts)
        bar_vol_tags = [_extrude(pc) for pc in bpieces]

        # Statornuten als LUFT-Prismen (gerade, volle Länge) in den Statorring fragmentieren
        # → echte Zähne. Standardmäßig an (kann per opts `stator_slots=False` aus).
        srects = slot_rects(geom) if opts.get("stator_slots", True) else []
        slot_pieces = [{**r, "z0": 0.0, "z1": L} for r in srects]
        slot_vol_tags = [_extrude_straight(pc) for pc in slot_pieces]

        occ.synchronize()
        all_in = [(3, shaft), (3, rotor), (3, statI), (3, statO), (3, box)] \
            + [(3, t) for t in mag_vol_tags if t is not None] \
            + [(3, t) for t in bar_vol_tags if t is not None] \
            + [(3, t) for t in slot_vol_tags if t is not None]
        occ.fragment(all_in, [])
        occ.synchronize()

        # ── Magnete + Barrieren PER GEOMETRIE identifizieren (vor dem Vernetzen, für
        #    die zonale Verfeinerung brauchen wir ihre Oberflächen). Match über exakten
        #    Volumenschwerpunkt + Massengate (Eisen-Bulk viel größer, Slivers kleiner).
        def _assign(target_pieces, avail):
            assign = {i: [] for i in range(len(target_pieces))}
            pred = [p["length"] * p["thick"] * (p["z1"] - p["z0"]) for p in target_pieces]
            taken = set()
            for (v, gx, gy, gz, vmass) in avail:
                best, bd = None, 1e18
                for i, p in enumerate(target_pieces):
                    zc = 0.5 * (p["z0"] + p["z1"])
                    d = math.hypot(gx - p["cx"], gy - p["cy"]) + abs(gz - zc)
                    if d < bd:
                        bd, best = d, i
                if (best is not None and bd < 0.5 * target_pieces[best]["length"]
                        and 0.3 * pred[best] < vmass < 2.6 * pred[best]):
                    assign[best].append(v); taken.add(v)
            return assign, taken

        vinfo = []
        for (_d, v) in gmsh.model.getEntities(3):
            try:
                gx, gy, gz = gmsh.model.occ.getCenterOfMass(3, v)
                vmass = gmsh.model.occ.getMass(3, v)
            except Exception:
                gx = gy = gz = 1e9; vmass = 1e18
            vinfo.append((v, gx, gy, gz, vmass))

        mag_assign, mag_taken = _assign(pieces, vinfo)
        bar_avail = [t for t in vinfo if t[0] not in mag_taken]
        bar_assign, bar_taken = _assign(bpieces, bar_avail)
        slot_avail = [t for t in vinfo if t[0] not in mag_taken and t[0] not in bar_taken]
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
        slot_vols = [v for vs in slot_assign.values() for v in vs]
        fine_surfs = _surfs_of(mag_vols) | _surfs_of(bar_vols)

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
        # Magnete + Barrieren: Distance→Threshold (fein nah, grob ab mag_grow).
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
        if len(fields) > 1:
            f_min = fld.add("Min")
            fld.setNumbers(f_min, "FieldsList", [float(f) for f in fields])
            fld.setAsBackgroundMesh(f_min)
        else:
            fld.setAsBackgroundMesh(fields[0])
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", min(gap_cl, mag_cl))
        gmsh.option.setNumber("Mesh.MeshSizeMax", mesh_cl)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.model.mesh.generate(3)

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

        groups = {"shaft": [], "rotor": [], "stator": [], "air": []}
        # Barrieren + Statornuten sind LUFT-Taschen (im Rotor bzw. im Statorring).
        for v in bar_vols:
            groups["air"].append(v)
        for v in slot_vols:
            groups["air"].append(v)
        for (v, gx, gy, gz, vmass) in vinfo:
            if v in mag_taken or v in bar_taken or v in slot_taken:
                continue                                    # Magnet/Barriere/Nut schon zugeordnet
            # Ringe über einen ECHTEN Innenpunkt (Element-Schwerpunkt): konzentrische
            # Ringe haben ihren Volumenschwerpunkt auf der Achse → dort Radius untauglich.
            pr = _probe(v)
            if pr is None:
                groups["air"].append(v); continue
            cx, cy, cz = pr
            rc = math.hypot(cx, cy)
            if cz < -1e-6 or cz > L + 1e-6:
                groups["air"].append(v)                     # axiale Luft-Kappen
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
                "dims": {"r_shaft": r_shaft, "r_rot": r_rot, "r_si": r_si,
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
        tags["vol_class"] = vol_class
        tags["mag_pol"] = mag_pol

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
        tags["n_bodies"] = {k: len(v) for k, v in groups.items()}
        tags["skew_segments"] = n_seg
        tags["skew_step_deg"] = math.degrees(_seg_step)
        tags["mesh_zones"] = {"gap_cl": gap_cl, "mag_cl": mag_cl,
                              "mesh_cl": mesh_cl, "mag_grow": mag_grow}
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
    direct = bool(opts.get("direct", True))
    if direct:
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
    S.append('Solver 1\n'
             '  Equation = "MgDyn"\n'
             '  Procedure = "MagnetoDynamics" "WhitneyAVSolver"\n'
             '  Variable = "AV"\n'
             '  Fix Input Current Density = False\n'
             '  Use Tree Gauge = Logical True\n'
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

    # Außenrand: A×n = 0 (Fluss parallel zur weit entfernten Box).
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


def parse_results(work_dir: str, geom: dict, opts: dict, tags: dict,
                  project_dir: str) -> dict:
    """VTU → Luftspalt-B(θ,z), Endeffekt-Kurve, Schnittbild, Moment (Arkkio) +
    2D-Vergleich. Schreibt Charts nach ``project_dir/charts`` (base64 + Datei)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import base64, io

    dims = tags["dims"]; L = tags["L"]
    r_mid = 0.5 * (dims["r_rot"] + dims["r_si"])
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
    br_mid, bt_mid = br_by_z[mid], bt_by_z[mid]
    res["b_gap_mid_peak"] = round(float(np.max(np.abs(br_mid))), 3)
    res["b_gap_axial"] = [round(float(np.max(np.abs(b))), 3) for b in br_by_z]
    res["z_levels"] = [round(float(z), 1) for z in z_levels]

    # Moment (Arkkio-Näherung): T = (L·r²/μ0) · mean_z ∮ Br·Bθ dθ. v1 ist OPEN-CIRCUIT
    # (nur Magnete) → das Netto-Moment ist physikalisch ~0; der Wert ist am groben Netz
    # verrauscht und nur informativ. Das echte Lastmoment kommt mit den Spulenströmen.
    _trap = getattr(np, "trapezoid", None) or np.trapz   # NumPy 2.x: trapz → trapezoid
    arkkio = float(np.mean([_trap(br_by_z[i] * bt_by_z[i], th) for i in range(len(z_levels))]))
    res["torque_Nm"] = round((L * 1e-3) * (r_mid * 1e-3) ** 2 / MU0 * arkkio, 2)
    res["torque_note"] = "Leerlauf (nur Magnete) ⇒ Netto-Moment ≈ 0; Lastfall folgt"

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
        em2d = ema_analysis.run_em_analysis(geom, N=int(opts.get("n2d", 360)), rotor_angle=0.0)
        br2d = np.asarray(em2d["Br_gap"]); th2d = np.linspace(0, 2 * np.pi, len(br2d), endpoint=False)
        perf = em2d.get("performance", {})
        cmp2d = {"B_gap_2D": round(float(np.max(np.abs(br2d))), 3),
                 "B_gap_3D_mid": res["b_gap_mid_peak"],
                 "Kt_2D": perf.get("Kt_Nm_per_A")}
        fig, ax = plt.subplots(figsize=(6.2, 3.4), facecolor="#0d0d0d")
        ax.plot(np.degrees(th2d), br2d, label="2D-FDM (∞ lang)", color="#4fc3f7", lw=1.4)
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

    res["images"] = images
    return res


def _style_dark(ax):
    ax.set_facecolor("#0d0d0d")
    for s in ax.spines.values():
        s.set_color("#555")
    ax.tick_params(colors="#bbb"); ax.xaxis.label.set_color("#ccc"); ax.yaxis.label.set_color("#ccc")


def _slice_image(grid, bname, z0, dims, save_fn):
    """|B|-Heatmap auf der Ebene z=z0 (vtkCutter → matplotlib tricontourf)."""
    import vtk
    from vtk.util import numpy_support as ns
    import matplotlib.pyplot as plt
    plane = vtk.vtkPlane(); plane.SetOrigin(0, 0, z0); plane.SetNormal(0, 0, 1)
    cut = vtk.vtkCutter(); cut.SetCutFunction(plane); cut.SetInputData(grid); cut.Update()
    poly = cut.GetOutput()
    pts = ns.vtk_to_numpy(poly.GetPoints().GetData())
    B = ns.vtk_to_numpy(poly.GetPointData().GetArray(bname)).reshape(-1, 3)
    bmag = np.linalg.norm(B, axis=1)
    import matplotlib.colors as mcolors
    # Perzeptiv-/Wurzelskala (PowerNorm γ=0.5 ≈ logartig, verträgt B=0): das moderate
    # Statorfeld (~0,3–0,8 T) ist sonst neben den starken Magnet-/Luftspaltspitzen kaum
    # sichtbar. vmax robust über das 99. Perzentil (Eckenspitzen nicht skalenbestimmend).
    vmax = float(np.nanpercentile(bmag, 99)) if bmag.size else 2.0
    vmax = max(0.3, min(vmax, 2.4))
    norm = mcolors.PowerNorm(gamma=0.5, vmin=0.0, vmax=vmax)
    fig, ax = plt.subplots(figsize=(5.4, 5.0), facecolor="#0d0d0d")
    tpc = ax.tricontourf(pts[:, 0], pts[:, 1], np.clip(bmag, 0, vmax),
                         levels=40, cmap="magma", norm=norm)
    ax.set_aspect("equal"); ax.set_title("|B| [T] — Schnitt z=L/2 (Wurzelskala)", color="#ddd")
    for r in (dims["r_rot"], dims["r_si"], dims["r_so"]):
        ax.add_patch(plt.Circle((0, 0), r, fill=False, color="#888", lw=0.6))
    ax.set_xlim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    ax.set_ylim(-dims["r_so"] * 1.05, dims["r_so"] * 1.05)
    fig.colorbar(tpc, ax=ax, shrink=0.8)
    _style_dark(ax)
    return save_fn(fig, "em3d_slice_mid.png")


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
    for r in (dims["r_rot"], dims["r_si"], dims["r_so"]):
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


def render_geometry_3d(tags, save_fn):
    """Echte 3D-Ansicht des Modells: Eisen halbtransparent, Magnete opak (N rot / S blau).
    Liefert eine Liste {key,title,b64}. Braucht ``tags['vtk_mesh']``."""
    if not tags.get("vtk_mesh") or not os.path.exists(tags["vtk_mesh"]):
        return []
    full = _classified_grid(tags)
    L = tags["L"]; R = tags["dims"]["r_so"]
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

    # Punkte als float32 (sonst schreibt VTK 8-Byte-Doubles → der vtk.js-Reader
    # verrechnet sich an der 8-Byte-Ausrichtung: „Float64Array offset multiple of 8").
    pts32 = ns.vtk_to_numpy(poly.GetPoints().GetData()).astype(np.float32)
    vp = vtk.vtkPoints(); vp.SetData(ns.numpy_to_vtk(pts32)); poly.SetPoints(vp)

    # Binär (base64-inline), UNkomprimiert, **32-Bit-Header** — genau das Format, das
    # der vtk.js-XMLPolyDataReader im Browser liest (ASCII parst er nicht; 64-Bit-Header
    # + Kompression brechen ihn).
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
                                    "airbox_factor")
            if k in payload}
    work = os.path.join(project_dir, "em3d"); os.makedirs(work, exist_ok=True)
    _log("🔧 Baue 3D-Mesh (Gmsh)…", 15)
    tags = build_mesh(geom, axial, opts, os.path.join(work, "motor3d.msh"))
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


# ── Orchestrator ─────────────────────────────────────────────────────────────────

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
    opts = {k: payload[k] for k in ("skew_deg", "skew_segments", "skew_step_deg",
                                    "mesh_cl", "gap_cl", "mag_cl", "mag_grow",
                                    "airbox_factor", "n2d")
            if k in payload}

    work = os.path.join(project_dir, "em3d")
    os.makedirs(work, exist_ok=True)
    msh = os.path.join(work, "motor3d.msh")

    _log("🔧 Baue 3D-Mesh (Gmsh)…", 8)
    tags = build_mesh(geom, axial, opts, msh)
    mz = tags.get("mesh_zones", {})
    _log(f"✓ Mesh: {tags['n_nodes']} Knoten, {tags['n_magnets']} Magnete, "
         f"{tags.get('n_barriers', 0)} Flussbarrieren, {tags.get('n_slots', 0)} Statornuten, "
         f"Körper {tags['n_bodies']}", 28)
    if mz:
        _log(f"   Zonen: Luftspalt {mz['gap_cl']:.2f} / Magnet+Barriere {mz['mag_cl']:.2f} "
             f"(Saum {mz['mag_grow']:.1f}) / grob {mz['mesh_cl']:.1f} mm", 30)

    _log("🔁 ElmerGrid: MSH → Elmer-Mesh…", 38)
    mesh_dir = os.path.join(work, "mesh")
    rg = ER.run_elmergrid(msh, mesh_dir)
    if not rg["ok"]:
        raise RuntimeError("ElmerGrid fehlgeschlagen: " + (rg.get("stderr") or rg.get("error", ""))[:300])

    _log("📝 Schreibe Elmer-Solverdatei (.sif)…", 45)
    write_sif(geom, opts, tags, work, mesh_name="mesh")

    _log("🧲 ElmerSolver: 3D-Magnetostatik…", 50)
    rs = ER.run_elmersolver(os.path.join(work, "case.sif"), work)
    if not rs["ok"]:
        raise RuntimeError("ElmerSolver fehlgeschlagen: " + (rs.get("stderr") or rs.get("error", ""))[:300]
                           + "\n" + (rs.get("stdout", "")[-400:]))

    _log("📊 Werte Felder aus + vergleiche mit 2D…", 85)
    res = parse_results(work, geom, opts, tags, project_dir)
    res["mesh"] = {"n_nodes": tags["n_nodes"], "n_magnets": tags["n_magnets"],
                   "n_barriers": tags.get("n_barriers", 0), "bodies": tags["n_bodies"]}
    res["mesh_zones"] = tags.get("mesh_zones", {})
    res["axial_mm"] = axial
    res["skew_deg"] = float(opts.get("skew_deg", 0.0) or 0.0)
    res["skew_segments"] = int(tags.get("skew_segments", 1))
    res["skew_step_deg"] = float(tags.get("skew_step_deg", 0.0))

    # 3D-Ergebnis in results.json des Projekts mergen, damit der Gesamtbericht den
    # 3D-Teil mit aufnehmen kann (Bilder liegen bereits unter charts/). base64 wird
    # NICHT mitgespeichert (die Charts existieren als Dateien) — results.json schlank halten.
    try:
        _persist_em3d_summary(project_dir, res)
    except Exception as e:
        res.setdefault("warnings", []).append(f"results.json-Merge fehlgeschlagen: {e}")

    _log("✓ 3D-Feldberechnung fertig", 100)
    return res


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
        "compare_2d", "mesh", "mesh_zones", "axial_mm", "skew_deg",
        "skew_segments", "skew_step_deg", "warnings")}
    # Bild-Schlüssel+Titel (Dateien liegen in charts/) für den Bericht.
    summary["images"] = [{"key": im.get("key"), "title": im.get("title")}
                         for im in (res.get("images") or []) if im.get("key")]
    data["em3d"] = summary
    with open(rj, "w") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
