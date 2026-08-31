"""2-D algebraic pre-CAD gate for rotor magnet-pocket layout.

Pure math on the pole-local `Leg` records from `ema_topology.magnet_legs(geom)`
(the single source of truth that FreeCAD `ema_freecad.py` and the FDM field both
consume).  No CAD, no FreeCAD — runs in milliseconds.

The pocket shape modelled here is the EXACT final-CAD pocket as cut by
``ema_freecad.build_full_motor_script``:

    stadium (Langloch) = centred rectangle (L + 2g) x (T + 2g)
                         + two semicircular end caps of radius (T + 2g)/2
                         at +/- (L + 2g)/2 - (T + 2g)/2 ...

i.e. half-length ``hl = (L + 2g)/2``, half-width ``ht = (T + 2g)/2``,
cap centres at +/- hl along the long axis, cap radius ``ht``.
(That is what decides whether iron webs survive in the real model.)

Checks, per pole then replicated on 2p poles:

  1. CONTAINMENT – every *interior* pocket has all extent inside the annulus
     [bore, rotor OD].  Breach inward = crack/through-hole to the shaft
     connection; outward = pocket sticking out of the rotor (air-gap gone,
     stator collision).
  2. MIN WEB     – minimum distance between ANY two distinct pockets (same or
     adjacent poles) >= ``min_web_mm`` (default ``ema_topology.BRIDGE_MM`` = 2mm).
     Overlap (negative distance) is fatal; a web under the minimum is a
     crack / flux-barrier / manufacturability defect.
  3. SANITY      – surface-placed magnets (SPM/Halbach) stay on the rim band.

Public API:

    from ema_rotorcheck import rotor_layout_check
    chk = rotor_layout_check(geom, min_web_mm=2.0)
    if not chk["ok"]:
        raise RuntimeError("; ".join(chk["fatal"]))
"""

from __future__ import annotations

import math

from ema_topology import (BRIDGE_MM, balance_bolt_holes, flux_barrier_slots,
                          leg_center, magnet_legs)


# ── 2-D helpers ────────────────────────────────────────────────────────────────

def _rot2(v, a: float):
    c, s = math.cos(a), math.sin(a)
    return (c * v[0] - s * v[1], s * v[0] + c * v[1])


def _corners(center, angle: float, ha: float, hb: float):
    return [
        (center[0] + _rot2((sx * ha, sy * hb), angle)[0],
         center[1] + _rot2((sx * ha, sy * hb), angle)[1])
        for sx, sy in ((1, 1), (1, -1), (-1, -1), (-1, 1))
    ]


def _proj(pts, axis):
    vals = [p[0] * axis[0] + p[1] * axis[1] for p in pts]
    return min(vals), max(vals)


def _obb_rect_distance(A, B):
    """Rect-rect signed distance via SAT. A/B: (center, angle, ha, hb)."""
    cA, thA, haA, hbA = A
    cB, thB, haB, hbB = B
    axes = []
    for th, ha, hb in ((thA, haA, hbA), (thB, haB, hbB)):
        c, s = math.cos(th), math.sin(th)
        axes.append((c, s))
        axes.append((-s, c))
    PA = _corners(cA, thA, haA, hbA)
    PB = _corners(cB, thB, haB, hbB)
    ovs = []
    for ax in axes:
        a0, a1 = _proj(PA, ax)
        b0, b1 = _proj(PB, ax)
        ovs.append(min(a1, b1) - max(a0, b0))   # >0 overlap, <0 separation
    if any(o < 0 for o in ovs):
        # Separated: every separating axis yields a LOWER bound on the true
        # distance, so take the TIGHTEST one.  This used to be ``min(...)``, the
        # loosest bound -- for two long, thin pockets crossed at a steep angle it
        # reported **0.51 mm** where the real clearance is **17.11 mm** (measured,
        # 33x too small).  The gate then killed layouts that were never tight, which
        # is why several rotor topologies could not be built at any parameter
        # setting.  ``max`` is still a lower bound (it never over-reports a web), so
        # the gate stays on the safe side -- it just stops rejecting sound designs.
        return max(-o for o in ovs if o < 0)
    return -min(ovs)                            # penetration (negative)


def _point_to_rect(p, obb):
    """Distance from a point to an OBB (0 if inside).  obb: (c, angle, ha, hb)."""
    c, th, ha, hb = obb
    dx, dy = p[0] - c[0], p[1] - c[1]
    ct, st = math.cos(-th), math.sin(-th)
    lx = ct * dx - st * dy
    ly = st * dx + ct * dy
    return math.hypot(max(abs(lx) - ha, 0.0), max(abs(ly) - hb, 0.0))


class Pocket:
    """Stadium (= obround) as cut by the final CAD: rectangle + end caps."""

    def __init__(self, center, angle, hl, ht):
        self.center, self.angle = center, angle
        self.hl, self.ht = hl, ht
        self.core = (center, angle, hl, ht)
        ux = math.cos(angle)
        uy = math.sin(angle)
        self.caps = ((center[0] + ux * hl, center[1] + uy * hl),
                     (center[0] - ux * hl, center[1] - uy * hl))
        self.cap_r = ht

    def radius_bounds(self):
        rmax = max(math.hypot(x, y) for x, y in _corners(self.center, self.angle,
                                                         self.hl, self.ht))
        rmin = min(math.hypot(x, y) for x, y in _corners(self.center, self.angle,
                                                         self.hl, self.ht))
        for cp in self.caps:
            d = math.hypot(cp[0], cp[1])
            rmax = max(rmax, d + self.cap_r)
            rmin = min(rmin, d - self.cap_r)
        return rmin, rmax


def pocket_distance(A: Pocket, B: Pocket):
    """Min signed distance between two pockets (negative = penetration)."""
    d = _obb_rect_distance(A.core, B.core)
    d = min(d, _point_to_rect(B.caps[0], A.core) - B.cap_r)
    d = min(d, _point_to_rect(B.caps[1], A.core) - B.cap_r)
    d = min(d, _point_to_rect(A.caps[0], B.core) - A.cap_r)
    d = min(d, _point_to_rect(A.caps[1], B.core) - A.cap_r)
    for ca in A.caps:
        for cb in B.caps:
            d = min(d, math.hypot(ca[0] - cb[0], ca[1] - cb[1])
                    - A.cap_r - B.cap_r)
    return d


# ── the check ─────────────────────────────────────────────────────────────────

def _magnettaschen(geom: dict):
    """Die Magnettaschen aller Pole als ``Pocket`` -- eine Quelle fuer beide Pruefungen.

    Stand frueher nur in ``rotor_layout_check``; seit ``zusatzteile_check`` dieselben
    Taschen braucht, waeren es zwei Abschriften derselben Spaltregel geworden.
    """
    legs, _meta = magnet_legs(geom)
    poles = max(2, int(geom.get("p", 3)) * 2)
    # identical pocket-gap rule as ema_freecad.build_full_motor_script
    gap = max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))
    pockets: list[tuple[dict, Pocket]] = []   # interior (must stay in annulus)
    surface: list[tuple[dict, Pocket]] = []   # rim-mounted (SPM/Halbach)
    for li, leg in enumerate(legs):
        if leg.length <= 0 or leg.thickness <= 0:
            continue
        hl = leg.length / 2.0 + gap
        ht = leg.thickness / 2.0 + gap
        for pole in range(poles):
            pole_ang = pole * 2.0 * math.pi / poles
            center = _rot2(leg_center(leg), pole_ang)
            ang = leg.tilt + pole_ang
            base = dict(pole=pole, leg=li, r_pos=leg.r_pos, offset=leg.offset,
                        length=leg.length, thickness=leg.thickness,
                        layer=leg.layer, placement=leg.placement)
            if leg.placement == "interior":
                pockets.append((base, Pocket(center, ang, hl, ht)))
            else:
                surface.append((base, Pocket(center, ang, hl, ht)))
    return pockets, surface


def zusatzteile_check(geom: dict, min_web_mm: float | None = None) -> dict:
    """Flussbarrieren und Wuchtverschraubung gegen die Magnettaschen pruefen.

    Diese Luecke stand ausdruecklich in der Doku: „a passing gate does not rule out
    a breakthrough from those". Beide schneiden Material aus demselben Blech wie die
    Taschen, und bisher hat das niemand nachgemessen -- ein Schlitz, der in eine
    Magnettasche laeuft, kam erst in FreeCAD heraus, nach 40 Sekunden Startzeit.

    Geprueft wird mit **denselben** Bausteinen wie das Taschenlayout: der Schlitz ist
    ein Rechteck (``Pocket`` mit radialer Laengsachse), das Bohrloch ein Kreis
    (``Pocket`` mit gleichen Halbachsen). Damit gibt es keine zweite Abstandsformel.

    **Die Befunde sind bewusst Warnungen, keine Ausschluesse.** Das Layouttor ist
    Stufe 0 der Pipeline und bricht einen Lauf ab; eine neue Ausschlussregel wuerde
    bestehende, laufende Auslegungen von einem Tag auf den anderen verweigern. Wer
    sie als Tor will, liest ``ok`` aus diesem Ergebnis.
    """
    if min_web_mm is None:
        min_web_mm = BRIDGE_MM
    schlitze = flux_barrier_slots(geom)
    loecher  = balance_bolt_holes(geom)
    if not schlitze and not loecher:
        return {"ok": True, "aktiv": False, "befunde": [],
                "n_barrieren": 0, "n_loecher": 0, "min_abstand_mm": None}

    r_rot = float(geom["rotorOD"]) / 2.0
    r_sh  = float(geom["shaftD"]) / 2.0
    pockets, surface = _magnettaschen(geom)

    teile: list[tuple[str, Pocket]] = []
    for i, sl in enumerate(schlitze):
        mitte_r = (sl["r_in"] + sl["r_out"]) / 2.0
        mitte = (mitte_r * math.cos(sl["angle"]), mitte_r * math.sin(sl["angle"]))
        teile.append((f"Flussbarriere {sl['family']}{i}",
                      Pocket(mitte, sl["angle"], sl["depth"] / 2.0, sl["width"] / 2.0)))
    for i, lo in enumerate(loecher):
        teile.append((f"Schraubloch {i} ({lo['thread']})",
                      Pocket((lo["x"], lo["y"]), 0.0, lo["r"], lo["r"])))

    # Befunde als (Art, Wert, Text) sammeln. Bei Drehsymmetrie meldet JEDER Pol
    # denselben Durchbruch -- sechs gleichlautende Zeilen sind keine sechs Befunde,
    # sondern einer, und sie verdecken in einer Agentenantwort alles Uebrige.
    roh: list[tuple[str, float, str]] = []
    min_abstand = math.inf

    # 1. Einschluss im Blechring.
    for sl in schlitze:
        if sl["r_out"] > r_rot + 1e-6:
            roh.append(("barriere_rand", sl["r_out"] - r_rot,
                        f"Flussbarriere ragt {sl['r_out'] - r_rot:.2f} mm ueber den "
                        f"Rotoraussenrand"))
    for lo in loecher:
        d_aussen = r_rot - lo["pitch_r"] - lo["r"]
        if d_aussen < min_web_mm - 1e-6:
            roh.append(("loch_rand", d_aussen,
                        f"Schraubloch ({lo['thread']}) laesst zum Rotoraussenrand nur "
                        f"{d_aussen:.2f} mm statt {min_web_mm:.1f} mm"))
        d_innen = lo["pitch_r"] - lo["r"] - r_sh
        if d_innen < min_web_mm - 1e-6:
            roh.append(("loch_welle", d_innen,
                        f"Schraubloch ({lo['thread']}) laesst zur Welle nur "
                        f"{d_innen:.2f} mm statt {min_web_mm:.1f} mm"))

    # 2. Zusatzteil gegen Magnettasche -- der eigentliche Grund fuer diese Pruefung.
    for name, pk in teile:
        art = "Flussbarriere" if name.startswith("Fluss") else "Schraubloch"
        for base, tasche in pockets + surface:
            d = pocket_distance(pk, tasche)
            min_abstand = min(min_abstand, d)
            if d < -1e-6:
                roh.append((f"{art}_schnitt", d,
                            f"{art} schneidet eine Magnettasche um {abs(d):.2f} mm "
                            f"(zuerst Pol {base['pole']}, Leg {base['leg']})"))
            elif d < min_web_mm - 1e-6:
                roh.append((f"{art}_steg", d,
                            f"{art} steht nur {d:.2f} mm von einer Magnettasche "
                            f"(zuerst Pol {base['pole']}, Leg {base['leg']}) -- "
                            f"Mindeststeg {min_web_mm:.1f} mm"))

    # 3. Zusatzteile untereinander.
    for i in range(len(teile)):
        for j in range(i + 1, len(teile)):
            d = pocket_distance(teile[i][1], teile[j][1])
            min_abstand = min(min_abstand, d)
            if d < min_web_mm - 1e-6:
                a_kurz = teile[i][0].split(" ")[0]
                b_kurz = teile[j][0].split(" ")[0]
                roh.append((f"unter_sich_{a_kurz}_{b_kurz}", d,
                            f"{a_kurz} und {b_kurz} stehen nur {d:.2f} mm auseinander "
                            f"-- Mindeststeg {min_web_mm:.1f} mm"))

    # Je Art nur der SCHLIMMSTE Fall, mit der Zahl der gleichartigen Stellen. Bei
    # Drehsymmetrie meldet sonst jeder Pol denselben Durchbruch noch einmal.
    nach_art: dict = {}
    for art, wert, text in roh:
        e = nach_art.setdefault(art, {"wert": wert, "text": text, "n": 0})
        e["n"] += 1
        if wert < e["wert"]:
            e["wert"], e["text"] = wert, text
    knapp = [(e["text"] + (f"  [{e['n']}× gleichartig]" if e["n"] > 1 else ""))
             for _art, e in sorted(nach_art.items(), key=lambda kv: kv[1]["wert"])]
    return {"ok": not knapp, "aktiv": True, "befunde": knapp,
            "n_barrieren": len(schlitze), "n_loecher": len(loecher),
            "min_abstand_mm": None if min_abstand == math.inf else round(min_abstand, 3),
            "min_web_req_mm": min_web_mm}


def rotor_layout_check(geom: dict, min_web_mm: float | None = None) -> dict:
    """Run the 2-D rotor layout gate.  JSON-serialisable report."""
    if min_web_mm is None:
        min_web_mm = BRIDGE_MM

    legs, meta = magnet_legs(geom)
    poles = max(2, int(geom.get("p", 3)) * 2)
    r_rot = float(geom["rotorOD"]) / 2.0
    r_shaft = float(geom["shaftD"]) / 2.0

    # identical pocket-gap rule as ema_freecad.build_full_motor_script
    gap = max(0.05, min(0.3, float(geom.get("magGapMm", 0.1))))

    fatal: list[str] = []
    warnings: list[str] = []

    pockets, surface = _magnettaschen(geom)

    # 1) containment -----------------------------------------------------------
    eps = 1e-6
    for base, pk in pockets:
        rmin, rmax = pk.radius_bounds()
        if rmax > r_rot + eps:
            fatal.append(
                f"Tasche (Pol {base['pole']}, Leg {base['leg']}) ragt "
                f"{rmax - r_rot:.2f} mm ausserhalb des Rotors "
                f"(Aussenradius = {r_rot:.1f} mm) - loest Luftspalt auf / "
                f"stosst gegen Stator")
        if rmin < r_shaft - eps:
            fatal.append(
                f"Tasche (Pol {base['pole']}, Leg {base['leg']}) ragt "
                f"{r_shaft - rmin:.2f} mm in die Bohrung "
                f"(Bohrradius = {r_shaft:.1f} mm) - Riss / Durchtritt zur Welle")

    # 2) min web over ALL pockets/tiles ----------------------------------------
    allpk = [(b, pk, "Tasche") for b, pk in pockets]
    allpk += [(b, pk, "Oberflaechenmagnet") for b, pk in surface]
    min_dist = math.inf
    worst = None
    for i in range(len(allpk)):
        bi, pi_, ki = allpk[i]
        for j in range(i + 1, len(allpk)):
            bj, pj, kj = allpk[j]
            if bi["pole"] == bj["pole"] and bi["leg"] == bj["leg"]:
                continue
            d = pocket_distance(pi_, pj)
            if d < min_dist:
                min_dist = d
                worst = (bi, bj, d, ki, kj)
    if worst is not None:
        bi, bj, d, ki, kj = worst
        label = (f"{ki} (Pol {bi['pole']}, Leg {bi['leg']}) <-> "
                 f"{kj} (Pol {bj['pole']}, Leg {bj['leg']})")
        if d < -eps:
            fatal.append(f"Kollision: {label} - Ueberlappung {abs(d):.2f} mm")
        elif d < min_web_mm - eps:
            fatal.append(
                f"Stege zu duenn: {label} - Abstand {d:.2f} mm < "
                f"Mindestdicke {min_web_mm:.2f} mm (Riss-/Flussbarriere-Risiko)")

    # 3) surface sanity ---------------------------------------------------------
    for base, pk in surface:
        _, rmax = pk.radius_bounds()
        if rmax > r_rot + 0.5:
            warnings.append(
                f"Oberflaechenmagnet (Pol {base['pole']}, Leg {base['leg']}) "
                f"ragt bis {rmax:.1f} mm > Rotor-Aussen {r_rot:.1f} mm")

    # 4) Zusatzteile: Flussbarrieren und Wuchtverschraubung gegen die Taschen.
    #    Als WARNUNG, nicht als Ausschluss -- s. zusatzteile_check. Bisher sah das
    #    Tor diese beiden Bauteile ueberhaupt nicht, obwohl sie in dasselbe Blech
    #    schneiden; ein Schlitz durch eine Magnettasche fiel erst in FreeCAD auf.
    zusatz = zusatzteile_check(geom, min_web_mm)
    warnings.extend(zusatz["befunde"])

    info = {
        "topology": meta.code,
        "label": meta.label,
        "poles": poles,
        "legs_per_pole": len(legs),
        "pockets_total": len(pockets),
        "surface_tiles_total": len(surface),
        "r_shaft_mm": round(r_shaft, 3),
        "r_rotor_mm": round(r_rot, 3),
        "pocket_gap_mm": gap,
        "min_web_req_mm": min_web_mm,
        "min_web_found_mm": None if min_dist == math.inf
                              else round(min_dist, 3),
        "worst_pair": None if worst is None else {
            "a": {"pole": worst[0]["pole"], "leg": worst[0]["leg"],
                  "layer": worst[0]["layer"],
                  "placement": worst[0]["placement"]},
            "b": {"pole": worst[1]["pole"], "leg": worst[1]["leg"],
                  "layer": worst[1]["layer"],
                  "placement": worst[1]["placement"]},
            "distance_mm": round(worst[2], 3),
        },
        "zusatzteile": zusatz,
    }

    return {"ok": not fatal, "fatal": fatal, "warnings": warnings,
            "layout": info}


# ── C) ROTATIONAL STRESS — conservative 2-D Lamé gate on the bore hoop stress ────
#
# A rotating annulus (shaft-OD a -> rotor-OD b) under centrifugal load carries
# its maximum hoop stress at the bore.  The rigorous 2-D axisymmetric solution
# (equilibrium + constitutive + kinematic, verified by SymPy residual = 0 AND an
# independent FEM to <0.2 %) is

#     sigma_theta(a) = rho*omega^2 / 4 * [ (1-L)*a^2 + (3+L)*b^2 ]

# with L = D12/D11, which is the *state of the plane*, not a material guess:
#
#     plane STRESS  (thin disc,      sigma_z = 0):  L = nu
#     plane STRAIN  (long cylinder,  epsilon_z = 0):  L = nu/(1-nu)
#
# Since L_strain > L_stress, plane strain is ALWAYS the higher -> conservative
# bound for a real continuous IPM rotor.  A real rotor sits BETWEEN these two
# (finite axial length); the definitive value needs the 3-D FEM (Stage C).

def _bore_hoop_mpa(a_m: float, b_m: float, rho: float, w: float, lam: float):
    """Exact rotating-annulus bore hoop stress [MPa].  a_m,b_m [m], rho [kg/m^3],
    w [rad/s], lam = D12/D11.  Clean SI (no mm/kg hybrids)."""
    return (rho * w * w / 4.0
            * ((1.0 - lam) * a_m * a_m + (3.0 + lam) * b_m * b_m) / 1e6)


# Engineering notch factor for the SHARP pocket corners (zero-radius stadium cut
# into the iron web).  Deliberate assumption (matches the pipeline's existing
# Kt≈1.5 deformation-stage convention), documented, NOT a computed value.  The
# binding gate value is
#     sigma_peak = max( FEM-P99 (notch-tolerant 3D result), KT_POCKET * hoop );
# the FEM P99 governs where available, Kt is the analytical screen.
KT_POCKET = 1.5


def rotor_stress_check(geom: dict, mat: dict, target: dict,
                       sf_target: float = 1.3) -> dict:
    """Centrifugal structural gate at n_max.  Reports BOTH plane states, gates
    on the CONSERVATIVE (plane-strain) value.  Pure math (millisecond).

    ``mat`` must carry ``density`` [kg/m^3], ``nu``, ``yield_mpa`` [MPa].
    ``target`` must carry ``n_max`` [rpm].  ``geom`` needs ``shaftD``/``rotorOD`` [mm].
    """
    nu     = float(mat.get("nu", 0.30))
    rho    = float(mat.get("density", 7650.0))
    sigy   = float(mat.get("yield_mpa", 340.0))
    a_m    = float(geom["shaftD"])  / 2.0e3   # mm -> m
    b_m    = float(geom["rotorOD"]) / 2.0e3
    nm     = float(target["n_max"])
    w      = 2.0 * math.pi * nm / 60.0

    sig_ps  = _bore_hoop_mpa(a_m, b_m, rho, w, nu)            # optimistisch
    sig_str = _bore_hoop_mpa(a_m, b_m, rho, w, nu / (1.0 - nu))  # konservativ
    gate    = max(sig_ps, sig_str)                             # = sig_str

    # Peak level = conservative ring stress + engineering notch factor (sharp pocket corner).
    sig_peak  = gate * KT_POCKET
    sf_gate   = sigy / gate if gate > 0 else float("inf")            # ohne Notch
    sf_peak   = sigy / sig_peak if sig_peak > 0 else float("inf")    # MIT Notch -> bindend
    sf_ps     = sigy / sig_ps if sig_ps > 0 else float("inf")
    level     = "PASS" if sf_peak >= sf_target else \
                ("WARN" if sf_peak >= 1.0 else "FAIL")
    return {
        "ok": sf_peak >= sf_target,
        "level": level,
        "sigma_bore_conservative_MPa": round(sig_str, 1),   # Ring, ohne Notch
        "sigma_bore_plane_stress_MPa": round(sig_ps, 1),    # optimistische 2D-Scheibe
        "sigma_bore_plane_strain_MPa": round(sig_str, 1),   # konservativer 3D-Zylinder
        "kt_pocket": KT_POCKET,                              # engineering Notch-Faktor
        "sigma_peak_MPa": round(sig_peak, 1),                # Ring x Kt -> analyt. Peak
        "safety_factor": round(sf_gate, 3),                  # am Ring-Wert (ohne Notch)
        "safety_factor_peak": round(sf_peak, 3),             # MIT Notch -> GATE
        "sf_plane_stress": round(sf_ps, 3),
        "yield_mpa": sigy, "nu": nu, "density_kg_m3": rho,
        "a_mm": round(a_m * 1e3, 3), "b_mm": round(b_m * 1e3, 3),
        "n_max_rpm": nm, "sf_target": sf_target,
        "note": ("2D-Lame-Losung rotierende Scheibe mit Bohrung, Spannungsmax. an der "
                 "Bohrung. Konservativ = Ebenenverformung (durchgehender Zylinder). "
                 "Peak = Ring x Kt (scharfe Taschenkante, Kt=1.5 Annahme); "
                 "3D-FEM-P99 ist hier bindender. "
                 "BINDEND: Tier-2-Gate = max(FEM-P99, Ring*Kt) vs. Fliessgrenze."),
    }


if __name__ == "__main__":
    import json, sys
    if len(sys.argv) > 1:
        doc = json.loads(open(sys.argv[1]).read())
        geom = doc.get("geom", doc) if isinstance(doc, dict) else None
        rep = rotor_layout_check(geom)
        print(json.dumps(rep, indent=2, ensure_ascii=False))
        sys.exit(0 if rep["ok"] else 1)
    print(__doc__)
