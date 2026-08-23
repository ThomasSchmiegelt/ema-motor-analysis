"""Prototyp: jedes negative Merkmal im Rotor ist eine KAPSEL (Strecke + Radius).

  Magnettasche  Rechteck L x t mit halbrunden Endkappen  -> Strecke P0->P1, r = t/2
  Wuchtbohrung  Kreis                                    -> Strecke P->P,   r = d/2
  Flussbarriere radialer Schlitz der Breite w            -> Strecke r_in->r_out, r = w/2

Damit ist ALLES eine Abstandsfrage, und der Abstand ist die Stegdicke in mm.
"""
import math, numpy as np, ema_topology as T


def _kapseln(g):
    """[(P0, P1, r, name)] aller negativen Merkmale, global, in mm."""
    r_rot = float(g["rotorOD"]) / 2
    r_sh  = float(g["shaftD"]) / 2
    poles = int(g["p"]) * 2
    out = []
    legs, _ = T.magnet_legs(g)
    for pi in range(poles):
        pa = pi * 2 * math.pi / poles
        cp, sp = math.cos(pa), math.sin(pa)
        for li, lg in enumerate(legs):
            if lg.placement == "surface":
                continue                       # sitzt AUF dem Rotor, schneidet nichts
            x0 = lg.r_pos * cp - lg.offset * sp
            y0 = lg.r_pos * sp + lg.offset * cp
            la = pa + lg.tilt
            x1 = x0 + lg.length * math.cos(la)
            y1 = y0 + lg.length * math.sin(la)
            out.append((np.array([x0, y0]), np.array([x1, y1]),
                        lg.thickness / 2, f"Tasche P{pi}L{li}"))
    if bool(g.get("genBalanceBolts", False)):
        thr = {"M4":4.,"M5":5.,"M6":6.,"M8":8.,"M10":10.,"M12":12.,"M16":16.,"M20":20.}
        d = thr.get(str(g.get("balanceBoltThread","M6")).upper(), 6.0)
        bcd = float(g.get("balanceBoltCircleD", 0) or 0)
        pcr = bcd/2 if bcd > 0 else r_sh + (r_rot - r_sh) * 0.5
        off = math.radians(float(g.get("balanceBoltOffsetDeg", 0)))
        for i in range(max(2, poles)):
            a = off + i * 2*math.pi/max(2, poles)
            P = np.array([pcr*math.cos(a), pcr*math.sin(a)])
            out.append((P, P, (d + 0.4)/2, f"Bohrung {i}"))
    if g.get("genFluxBarrierQ") or g.get("genFluxBarrierD"):
        w  = max(0.5, min(40.0, float(g.get("fluxBarrierWidth", 3.0))))
        dp = max(1.0, min(120.0, float(g.get("fluxBarrierDepth", 10.0))))
        ro = r_rot - 2.0
        ri = max(r_sh + 1.0, ro - dp)
        angs = []
        if g.get("genFluxBarrierD"): angs += [i*2*math.pi/poles for i in range(poles)]
        if g.get("genFluxBarrierQ"): angs += [(i+.5)*2*math.pi/poles for i in range(poles)]
        for k, a in enumerate(angs):
            u = np.array([math.cos(a), math.sin(a)])
            out.append((ri*u, ro*u, w/2, f"Barriere {k}"))
    return out, r_rot, r_sh


def _seg_seg(p1, q1, p2, q2):
    """kuerzester Abstand zweier Strecken (2D)."""
    d1, d2 = q1-p1, q2-p2
    r = p1-p2
    a, e, f = d1@d1, d2@d2, d2@r
    if a < 1e-12 and e < 1e-12: return float(np.linalg.norm(r))
    if a < 1e-12: s, t = 0.0, min(max(f/e, 0), 1)
    else:
        c = d1@r
        if e < 1e-12: t, s = 0.0, min(max(-c/a, 0), 1)
        else:
            b = d1@d2; den = a*e - b*b
            s = min(max((b*f - c*e)/den, 0), 1) if den > 1e-12 else 0.0
            t = (b*s + f)/e
            if t < 0: t, s = 0.0, min(max(-c/a, 0), 1)
            elif t > 1: t, s = 1.0, min(max((b - c)/a, 0), 1)
    return float(np.linalg.norm((p1+s*d1) - (p2+t*d2)))


def _punkt_strecke(p, q):
    """kleinster Abstand des Ursprungs zur Strecke p->q."""
    d = q-p; L = d@d
    t = 0.0 if L < 1e-12 else min(max(-(p@d)/L, 0), 1)
    return float(np.linalg.norm(p + t*d))


def pruefe(g, bruecke=T.BRIDGE_MM):
    kap, r_rot, r_sh = _kapseln(g)
    befunde = []
    for P0, P1, r, name in kap:
        aussen = max(np.linalg.norm(P0), np.linalg.norm(P1)) + r      # weiteste Ausdehnung
        innen  = _punkt_strecke(P0, P1) - r                            # naechster Punkt
        befunde.append((r_rot - aussen, f"{name} -> Rotorrand"))
        befunde.append((innen - r_sh,   f"{name} -> Welle"))
    for i in range(len(kap)):
        for j in range(i+1, len(kap)):
            P0,P1,ri,ni = kap[i]; Q0,Q1,rj,nj = kap[j]
            befunde.append((_seg_seg(P0,P1,Q0,Q1) - ri - rj, f"{ni} <-> {nj}"))
    befunde.sort()
    return befunde, len(kap)
