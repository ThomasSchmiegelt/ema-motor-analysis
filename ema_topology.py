"""Single source of truth for rotor magnet placement across the toolchain.

Both `ema_freecad.py` (CAD geometry / pockets + magnet solids) and
`ema_analysis.py` (2-D FDM field) build their magnet geometry from the `Leg`
list returned by `magnet_legs(geom)`.  The structural FEM inherits the geometry
from the saved CAD document, so it needs no separate magnet logic.

⚠  MIRROR: the JavaScript function `magnetLegs(GEOM)` in `ema.html` is a
hand-maintained transliteration of `magnet_legs()` below.  Any change to the leg
recipes here MUST be mirrored there (and vice versa).  Each implementation is
isolated in a single named function so drift is easy to spot.

Frame convention (pole-local): x = radially outward, y = tangential.
A leg's magnet body starts at ``(r_pos, offset)`` and extends a distance
``length`` along the direction ``(cos tilt, sin tilt)``; its ``thickness`` is
measured perpendicular to that long axis.  Consumers rotate the whole pole by
``pole_ang`` and (for the FDM) flip magnetisation by ``mag_sign`` and alternate
pole polarity per pole index.

Magnetisation modes (resolved by the FDM consumer, dormant geometry-wise):
  "perp"        – M perpendicular to the long axis  (V / U / Delta / Doppel-V / flat)
  "tangential"  – M along the tangential direction   (Spoke, flux concentration)
  "radial"      – M along the radial direction       (SPM / Halbach)
"""

import math
from dataclasses import dataclass

# Iron bridge kept between the outer magnet corner and the rotor OD [mm].
BRIDGE_MM = 2.0


@dataclass(frozen=True)
class Leg:
    r_pos: float                 # radial start position (inner end) [mm]
    offset: float                # tangential offset of the start [mm]
    tilt: float                  # rotation of long axis in pole-local frame [rad]
    length: float                # magnet length along the long axis [mm]
    thickness: float             # magnet thickness (magnetisation extent) [mm]
    mag_mode: str = "perp"       # "perp" | "tangential" | "radial"
    mag_sign: int = 1            # +1/-1 polarity within the pole
    mag_rot: float = 0.0         # extra magnetisation rotation [rad] (Halbach only)
    placement: str = "interior"  # "interior" (pocket cut) | "surface" (added solid)
    layer: int = 0               # multi-layer index (Doppel-V / PMa-SynRM)


@dataclass(frozen=True)
class MotorTopoMeta:
    code: str
    label: str
    n_legs_per_pole: int
    flux_focusing: bool = False
    reluctance_dominated: bool = False
    is_surface: bool = False
    eta_hint: float = 1.0           # opening efficiency for analytical B_gap
    salient_xi_hint: float = 0.0    # 0 => use default saliency model
    warn: str = ""                  # non-empty => a geometry warning to surface


# Human-readable labels — also reused by the report (ema_report / ema_experts).
TOPOLOGY_LABELS = {
    "v":        "V-Form (IPM)",
    "vasym":    "Asymmetrisches V (IPM)",
    "bar":      "Balken / Flach (IPM)",
    "u":        "U-Form (IPM)",
    "vv":       "Doppel-V (mehrlagig)",
    "delta":    "Delta-Form (IPM)",
    "pmasynrm": "PMa-SynRM (Flussbarrieren)",
    "spm":      "SPM radial (Oberfläche)",
    "halbach":  "Halbach-Array (Oberfläche)",
    "spoke":    "Speichen-Typ (Flusskonzentration)",
    "custom":   "Designer (frei gezeichnet)",
}


def _max_magnet_width(r_pos: float, mag_dist_half: float, half_angle: float,
                      r_rot: float, bridge: float = BRIDGE_MM) -> float:
    """Max magnet length so the outer magnet corner stays inside ``r_rot - bridge``.

    Solves: (r_pos + L*cos)^2 + (mag_dist_half + L*sin)^2 = (r_rot - bridge)^2
    (Canonical clamp — moved here from ema_freecad; the JS ``_maxMagnetWidth``
    mirrors it.)
    """
    a = math.cos(half_angle)
    b = math.sin(half_angle)
    c = r_pos
    d = mag_dist_half
    R = r_rot - bridge
    p = a * c + b * d
    q = c * c + d * d - R * R
    disc = p * p - q
    if disc < 0:
        return 5.0
    return max(-p + math.sqrt(disc), 5.0)


# ── per-topology leg builders ──────────────────────────────────────────────────

def _common(geom: dict):
    """Shared radial reference: rotor/shaft radii and the magnet seat radius."""
    r_rot = geom["rotorOD"] / 2
    r_shaft = geom["shaftD"] / 2
    depth_rel = float(geom["magDepthRel"])
    r_pos = r_shaft + (r_rot - r_shaft) * depth_rel
    return r_rot, r_shaft, r_pos


def _build_v(geom: dict):
    r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    # Diameter mode: the pocket is defined by inner-Ø, outer-Ø and the V angle.
    # The inner magnet corner (at tangential offset d_half) sits at radius
    # pocketInnerD/2 → r_pos = sqrt(r_inner² − d_half²); the length follows from
    # the outer corner reaching pocketOuterD/2 (same quadratic as the OD clamp).
    if geom.get("pocketMode") == "diameter":
        r_pos = math.sqrt(max(25.0, (float(geom["pocketInnerD"]) / 2) ** 2 - d_half ** 2))
        mag_w = _max_magnet_width(r_pos, d_half, half_ang, float(geom["pocketOuterD"]) / 2, 0.0)
    else:
        mag_w = float(geom["magWidth"])
    # Thickness-aware clamp: keep the magnet CORNER (not just its centreline)
    # inside r_rot - BRIDGE by reserving half the thickness.
    mag_w = min(mag_w,
                _max_magnet_width(r_pos, d_half, half_ang, r_rot, BRIDGE_MM + mag_h / 2))
    legs = [
        Leg(r_pos,  d_half,  half_ang, mag_w, mag_h, "perp", +1),
        Leg(r_pos, -d_half, -half_ang, mag_w, mag_h, "perp", -1),
    ]
    meta = MotorTopoMeta("v", TOPOLOGY_LABELS["v"], n_legs_per_pole=2,
                         eta_hint=math.sin(half_ang))
    return legs, meta


def _build_vasym(geom: dict):
    """Asymmetric V: the two arms open at DIFFERENT angles about the d-axis.

    ``magAngle`` sets the (symmetric) base opening; ``magAsym`` (deg) tilts the
    two arms apart — the +offset arm gets ``half_ang + asym``, the −offset arm
    ``half_ang − asym``.  ``magAsym = 0`` reduces exactly to the symmetric ``v``.
    Breaking the pole symmetry shifts the back-EMF harmonics and is a common
    cogging-/torque-ripple-reduction measure.
    """
    r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    asym = math.radians(float(geom.get("magAsym", 0.0)))
    eb = BRIDGE_MM + mag_h / 2
    # Per-arm opening angle (clamped to a sane V range so corners stay inside).
    ha_top = min(max(half_ang + asym, math.radians(5)), math.radians(85))
    ha_bot = min(max(half_ang - asym, math.radians(5)), math.radians(85))
    w_top = min(float(geom["magWidth"]), _max_magnet_width(r_pos, d_half, ha_top, r_rot, eb))
    w_bot = min(float(geom["magWidth"]), _max_magnet_width(r_pos, d_half, ha_bot, r_rot, eb))
    legs = [
        Leg(r_pos,  d_half,  ha_top, w_top, mag_h, "perp", +1),
        Leg(r_pos, -d_half, -ha_bot, w_bot, mag_h, "perp", -1),
    ]
    meta = MotorTopoMeta("vasym", TOPOLOGY_LABELS["vasym"], n_legs_per_pole=2,
                         eta_hint=math.sin((ha_top + ha_bot) / 2))
    return legs, meta


def _build_bar(geom: dict):
    _r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    mag_w = float(geom["magWidth"])
    legs = [Leg(r_pos, 0.0, math.pi / 2, mag_w, mag_h, "perp", +1)]
    meta = MotorTopoMeta("bar", TOPOLOGY_LABELS["bar"], n_legs_per_pole=1,
                         eta_hint=1.0)
    return legs, meta


def _build_u(geom: dict):
    """V-pair plus a tangential bottom bar BELOW the arm feet (U cup, no overlap)."""
    r_rot, _r_shaft, r_pos = _common(geom)
    r_bore = float(geom.get("shaftBoreD", 0)) / 2
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    mag_w = min(float(geom["magWidth"]),
                _max_magnet_width(r_pos, d_half, half_ang, r_rot, BRIDGE_MM + mag_h / 2))
    # Bottom bar one thickness + bridge BELOW the arm feet (r_pos) → radial gap,
    # provably disjoint from the arms regardless of its tangential length.
    bar_r = max(r_pos - mag_h - BRIDGE_MM, r_bore + mag_h / 2 + 1.0)
    tang = float(geom.get("magTangLen", 0))
    bar_len = tang if tang > 0 else 2 * d_half
    bar_len = min(bar_len, 2 * (d_half + mag_w * math.sin(half_ang) * 0.5))
    legs = [
        Leg(r_pos,  d_half,  half_ang, mag_w, mag_h, "perp", +1),
        Leg(r_pos, -d_half, -half_ang, mag_w, mag_h, "perp", -1),
        Leg(bar_r, -bar_len / 2, math.pi / 2, bar_len, mag_h, "perp", +1),
    ]
    meta = MotorTopoMeta("u", TOPOLOGY_LABELS["u"], n_legs_per_pole=2,
                         eta_hint=math.sin(half_ang))
    return legs, meta


def _build_vv(geom: dict):
    """Double-V: inner + outer V layer, each with its OWN opening angle."""
    r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)            # inner
    half_ang2 = math.radians(float(geom.get("magAngle2", float(geom["magAngle"])))) / 2  # outer
    d_layer = float(geom.get("magLayerGap", 8.0))
    eb = BRIDGE_MM + mag_h / 2
    w0 = min(float(geom["magWidth"]),
             _max_magnet_width(r_pos, d_half, half_ang, r_rot, eb))
    r1 = r_pos + d_layer
    w1 = min(float(geom["magWidth"]) * 1.05,
             _max_magnet_width(r1, d_half, half_ang2, r_rot, eb))
    legs = [
        Leg(r_pos,  d_half,  half_ang, w0, mag_h, "perp", +1, layer=0),
        Leg(r_pos, -d_half, -half_ang, w0, mag_h, "perp", -1, layer=0),
        Leg(r1,  d_half,  half_ang2, w1, mag_h, "perp", +1, layer=1),
        Leg(r1, -d_half, -half_ang2, w1, mag_h, "perp", -1, layer=1),
    ]
    meta = MotorTopoMeta("vv", TOPOLOGY_LABELS["vv"], n_legs_per_pole=4,
                         eta_hint=math.sin(half_ang))
    return legs, meta


def _build_delta(geom: dict):
    """V-pair plus a tangential top deck ABOVE the arm tips (triangle, no overlap)."""
    r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    # Reserve radial room above the arms for the deck (one thickness + 2 bridges).
    arm_bridge = 2 * BRIDGE_MM + 1.5 * mag_h
    mag_w = min(float(geom["magWidth"]),
                _max_magnet_width(r_pos, d_half, half_ang, r_rot, arm_bridge))
    r_tip = r_pos + mag_w * math.cos(half_ang)
    y_tip = d_half + mag_w * math.sin(half_ang)
    deck_r = min(r_tip + mag_h + BRIDGE_MM, r_rot - mag_h / 2 - BRIDGE_MM)
    tang = float(geom.get("magTangLen", 0))
    deck_len = tang if tang > 0 else 1.6 * y_tip
    # keep the deck corner inside r_rot - BRIDGE
    max_half = math.sqrt(max((r_rot - BRIDGE_MM) ** 2 - (deck_r + mag_h / 2) ** 2, 0.0))
    deck_len = min(deck_len, 2 * max_half)
    legs = [
        Leg(r_pos,  d_half,  half_ang, mag_w, mag_h, "perp", +1),
        Leg(r_pos, -d_half, -half_ang, mag_w, mag_h, "perp", -1),
        Leg(deck_r, -deck_len / 2, math.pi / 2, deck_len, mag_h, "perp", +1),
    ]
    meta = MotorTopoMeta("delta", TOPOLOGY_LABELS["delta"], n_legs_per_pole=3,
                         eta_hint=math.sin(half_ang) * 0.9)
    return legs, meta


def _build_pmasynrm(geom: dict):
    """Multi-layer shallow-V flux barriers with thin magnets (reluctance-dominated)."""
    r_rot, r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"]) * 0.5
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    n_layers = max(2, int(geom.get("magLayers", 3)))
    d_layer = float(geom.get("magLayerGap", 8.0))
    legs = []
    for k in range(n_layers):
        rk = r_pos + (k - (n_layers - 1) / 2.0) * d_layer
        rk = max(rk, r_shaft + mag_h + 2.0)
        hak = max(half_ang - k * math.radians(8), math.radians(20))
        wk = min(float(geom["magWidth"]) * (0.8 + 0.15 * k),
                 _max_magnet_width(rk, d_half, hak, r_rot, BRIDGE_MM + mag_h / 2))
        legs.append(Leg(rk,  d_half,  hak, wk, mag_h, "perp", +1, layer=k))
        legs.append(Leg(rk, -d_half, -hak, wk, mag_h, "perp", -1, layer=k))
    meta = MotorTopoMeta("pmasynrm", TOPOLOGY_LABELS["pmasynrm"],
                         n_legs_per_pole=2 * n_layers, reluctance_dominated=True,
                         eta_hint=0.2, salient_xi_hint=4.0)
    return legs, meta


def _surface_thickness(geom: dict):
    """Surface magnets occupy the OUTER band of the rotor ([r_rot - t, r_rot]),
    i.e. inside the rotor OD envelope — they never grow into the stator and the
    air gap stays statorID/2 - rotorOD/2. Thickness is clamped to leave an iron
    core (≥2 mm) inside."""
    r_rot = geom["rotorOD"] / 2
    r_shaft = geom["shaftD"] / 2
    max_t = (r_rot - r_shaft) - 2.0
    req = float(geom["magThick"])
    if max_t <= 0.5:
        return max(max_t, 0.5), "Rotor zu dünn für Oberflächenmagnete — Rotor-Ø vergrößern"
    if req > max_t:
        return max_t, f"Magnetdicke auf {max_t:.1f} mm begrenzt (Rotordicke)"
    return req, ""


def _build_spm(geom: dict):
    """Surface radial PM: one magnetised arc segment per pole on the rotor OD."""
    r_rot = geom["rotorOD"] / 2
    poles = int(geom["p"]) * 2
    pole_pitch = math.pi * geom["rotorOD"] / poles            # [mm] arc per pole
    arc = float(geom.get("poleArcFrac", 0.83)) * pole_pitch
    mag_h, warn = _surface_thickness(geom)
    legs = [Leg(r_rot, 0.0, math.pi / 2, arc, mag_h,
                "radial", +1, placement="surface")]
    meta = MotorTopoMeta("spm", TOPOLOGY_LABELS["spm"], n_legs_per_pole=1,
                         is_surface=True, eta_hint=float(geom.get("poleArcFrac", 0.83)),
                         warn=warn)
    return legs, meta


def _build_halbach(geom: dict):
    """Surface Halbach array: ``seg`` STRAIGHT flat magnets per pole (default 6),
    arranged as flat tiles tangent to the rotor OD with rotating magnetisation
    (placement ``surface_flat`` → flat box, no pocket/caps, like surface-mounted but
    not curved). Each tile's magnetisation advances across the array (Halbach)."""
    r_rot = geom["rotorOD"] / 2
    poles = int(geom["p"]) * 2
    pole_pitch = math.pi * geom["rotorOD"] / poles
    arc_total = float(geom.get("poleArcFrac", 0.95)) * pole_pitch
    seg = max(2, int(geom.get("segPerPole", 6)))          # 6 flat magnets/pole default
    seg_ang = (arc_total / seg) / r_rot                    # angular span per tile [rad]
    mag_h, warn = _surface_thickness(geom)
    length = 2.0 * r_rot * math.sin(seg_ang / 2.0) * 0.95  # flat chord (small gap)
    # Inscribe the flat tile so its OUTER CORNERS sit at the rim (r_rot − bridge);
    # a flat chord at the surface would otherwise poke its corners past the OD.
    r_out = r_rot - BRIDGE_MM
    d_out = math.sqrt(max(r_out ** 2 - (length / 2.0) ** 2, 1.0))   # outer-face centre dist
    r_c = d_out - mag_h / 2.0                               # tile centre radius
    legs = []
    for s in range(seg):
        ang = (s - (seg - 1) / 2.0) * seg_ang              # tile centre angle (pole-local)
        tilt = ang + math.pi / 2.0                          # long axis tangential
        cx = r_c * math.cos(ang); cy = r_c * math.sin(ang)  # tile centre (pole-local)
        r_pos = cx - (length / 2.0) * math.cos(tilt)        # start end (leg_center → centre)
        offset = cy - (length / 2.0) * math.sin(tilt)
        mag_rot = (s - (seg - 1) / 2.0) * (math.pi / seg) * 2.0   # Halbach rotation
        legs.append(Leg(r_pos, offset, tilt, length, mag_h,
                        "radial", +1, mag_rot=mag_rot, placement="surface_flat"))
    meta = MotorTopoMeta("halbach", TOPOLOGY_LABELS["halbach"], n_legs_per_pole=seg,
                         is_surface=True, eta_hint=float(geom.get("poleArcFrac", 0.95)) * 1.1,
                         warn=warn)
    return legs, meta


def _build_spoke(geom: dict):
    """Spoke-type: one radial slab per pole, tangentially magnetised (flux focus)."""
    r_rot = geom["rotorOD"] / 2
    r_shaft = geom["shaftD"] / 2
    mag_h = float(geom["magThick"])
    r_start = r_shaft + 1.0
    length = max(r_rot - r_shaft - 2 * BRIDGE_MM, 5.0)
    legs = [Leg(r_start, 0.0, 0.0, length, mag_h, "tangential", +1)]
    meta = MotorTopoMeta("spoke", TOPOLOGY_LABELS["spoke"], n_legs_per_pole=1,
                         flux_focusing=True, eta_hint=1.0, salient_xi_hint=1.6)
    return legs, meta


# Registry. Unknown codes fall back to the flat bar (matches the historical
# `else` branch in the consumers).
def _build_custom(geom: dict):
    """Free-form designer topology: the magnets are supplied explicitly as
    ``geom["customLegs"]`` — a list of ONE pole's straight magnets in the pole-local
    frame (x=radial out, y=tangential), already mirrored across the d-axis by the
    canvas designer. Each item: {r_pos, offset, tilt_deg, length, thickness,
    mag_sign, mag_mode?}. The per-pole replication + polarity alternation is done by
    the consumers (FreeCAD / FDM), exactly as for the parametric topologies."""
    legs = []
    for it in (geom.get("customLegs") or []):
        try:
            legs.append(Leg(
                r_pos=float(it["r_pos"]),
                offset=float(it.get("offset", 0.0)),
                tilt=math.radians(float(it.get("tilt_deg", 0.0))),
                length=float(it["length"]),
                thickness=float(it["thickness"]),
                mag_mode=str(it.get("mag_mode", "perp")),
                mag_sign=int(it.get("mag_sign", 1)),
                placement="interior",
                layer=int(it.get("layer", 0)),
            ))
        except (KeyError, TypeError, ValueError):
            continue
    meta = MotorTopoMeta(
        code="custom", label=TOPOLOGY_LABELS.get("custom", "Designer (frei)"),
        n_legs_per_pole=max(1, len(legs)), is_surface=False, eta_hint=1.0)
    return legs, meta


_BUILDERS = {
    "v":        _build_v,
    "vasym":    _build_vasym,
    "bar":      _build_bar,
    "u":        _build_u,
    "vv":       _build_vv,
    "delta":    _build_delta,
    "pmasynrm": _build_pmasynrm,
    "spm":      _build_spm,
    "halbach":  _build_halbach,
    "spoke":    _build_spoke,
    "custom":   _build_custom,
}


def magnet_legs(geom: dict):
    """Return ``(list[Leg], MotorTopoMeta)`` for the configured topology.

    """
    shape = geom.get("magShape", "v")
    builder = _BUILDERS.get(shape, _build_bar)
    return builder(geom)


# ── consumer helpers ────────────────────────────────────────────────────────────

def leg_center(leg: Leg):
    """Pole-local centre of the magnet body (start + half-length along axis)."""
    cx = leg.r_pos + (leg.length / 2) * math.cos(leg.tilt)
    cy = leg.offset + (leg.length / 2) * math.sin(leg.tilt)
    return cx, cy


def leg_records(legs):
    """Serialisable pole-local placement records for the CAD/raster consumers.

    For interior legs the CAD uses (cx, cy, rot) to place a box.  For surface
    legs it uses (r_pos, offset, length) — offset is a tangential arc-length
    shift of the segment centre from the pole centre (Halbach sub-segments).
    """
    recs = []
    for lg in legs:
        cx, cy = leg_center(lg)
        recs.append({
            "cx": cx, "cy": cy, "rot": lg.tilt,
            "length": lg.length, "thick": lg.thickness,
            "placement": lg.placement,
            "r_pos": lg.r_pos, "offset": lg.offset, "mag_rot": lg.mag_rot,
        })
    return recs
