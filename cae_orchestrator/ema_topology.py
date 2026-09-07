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
#
# 1,3 mm ist der Wert der **Erstauslegung** und ausdruecklich zum Optimieren
# gedacht -- er ist nicht aus einer Festigkeitsrechnung hergeleitet, sondern eine
# Vorgabe. Was er bewirkt, ist gemessen (V-Form, p=3, Rotor-Aussen-Ø 188,6 mm):
#
#   BRIDGE_MM   Wand Tasche→Rand   Magnetlaenge   B_gap
#     2,0 mm         2,00 mm         23,56 mm     0,351 T
#     1,3 mm         1,30 mm         24,72 mm     0,369 T
#
# Der Steg sitzt also naeher am Rand, der Magnet wird laenger und liegt weiter
# aussen -- genau das war die Absicht. **Der Preis steht daneben und wird nicht
# verschwiegen:** ein duennerer Steg traegt die Fliehkraft schlechter. Geprueft
# wird das nicht hier, sondern in ``ema_rotorcheck.rotor_stress_check`` (Kerbfaktor
# ``KT_POCKET``) und in der Struktur-FEM; wer die Drehzahl hochzieht, sieht es dort.
#
# Die Groesse hat zwei Rollen, die zusammengehoeren: sie klemmt die Magnetlaenge
# gegen den Rotorrand (``_max_magnet_width``) UND sie ist die Vorgabe fuer den
# Mindeststeg des Layouttors (``ema_rotorcheck``). Der JS-Spiegel in ``ema.html``
# (``BRIDGE`` in ``magnetLegs``) fuehrt denselben Wert -- ``test_topology.py``
# nagelt beide gegeneinander fest.
BRIDGE_MM = 1.3

# ── Die Waende der Magnettasche ───────────────────────────────────────────────
#
# Bis hierher entstand eine V-Tasche aus DREI geratenen Zahlen: ``magDepthRel``
# (relative radiale Lage 0…1), ``magWidth`` (Laenge in mm) und ``magDist``
# (Stegabstand in mm). Keine davon ist eine Wand, keine folgt aus den anderen, und
# ob sie zusammen passen, sagt erst das Layouttor. Gemessen am Agentenlauf
# 20260907_074942: VIER Abbrueche an Stufe 0 hintereinander, die Tasche ragte
# 2,45 / 0,15 / 1,96 mm ueber den Rotorrand bzw. kollidierte um 0,77 mm mit dem
# Nachbarpol -- jedes Mal ein neuer Rateversuch.
#
# Eine Tasche hat aber Waende, und die sind die eigentliche Entwurfsgroesse:
#
#   Rand    zwischen Tasche und Rotoraussenrand -- haelt den Polschuh gegen die
#           Fliehkraft UND kurzschliesst den Magneten (s. ``stegbreite_mm``)
#   Achse   zwischen Tasche und Polsymmetrieachse (d-Achse). Der Steg dort traegt
#           die beiden V-Schenkel gegeneinander. Er war NIRGENDS ausgedrueckt --
#           am frischen Payload fiel er aus ``magDist=8`` zufaellig mit 0,81 mm ab.
#   q-Achse zwischen den Taschen ZWEIER BENACHBARTER Pole. Er fuehrt den
#           Reluktanzpfad und begrenzt, wie lang ein V-Schenkel werden darf.
#
# Gemeint ist immer die TASCHE (Rechteck + Endkappen + Klebespalt ``magGapMm``),
# nicht der Magnetkoerper -- dieselbe Groesse, die ``ema_rotorcheck.Pocket`` prueft.
# Der JS-Spiegel in ``ema.html`` (``magnetLegs``) fuehrt dieselben Werte;
# ``test_topology.py`` nagelt beide gegeneinander fest.
WAND_RAND_MM      = BRIDGE_MM   # 1,3 -- Tasche → Rotoraussenrand (V-artig)
WAND_ACHSE_MM     = 1.5         # Tasche → Polsymmetrieachse (d-Achse)
WAND_QACHSE_MM    = 2.0         # Tasche → Tasche des Nachbarpols (q-Achse)
WAND_SPEICHE_A_MM = 1.5         # Speiche: Tasche → Rotoraussenrand
WAND_SPEICHE_I_MM = 2.0         # Speiche: Tasche → Wellenaussenrand


def _spalt(geom: dict) -> float:
    """Klebespalt Magnet↔Tasche [mm] -- dieselbe Klemme wie in ``ema_freecad``."""
    return max(0.05, min(0.3, float((geom or {}).get("magGapMm", 0.1))))


def pocket_mode(geom: dict) -> str:
    """Wie die V-Tasche parametriert ist: ``position`` (Vorgabe) | ``diameter`` | ``wand``."""
    m = str((geom or {}).get("pocketMode", "position") or "position").strip().lower()
    return m if m in ("position", "diameter", "wand") else "position"


def sitz_aus_waenden(r_rot: float, halb_winkel: float, mag_h: float,
                     gap: float, laenge: float,
                     wand_rand: float = None, wand_achse: float = None):
    """``(d_half, r_pos)`` so, dass die Tasche BEIDE Waende genau beruehrt.

    Geschlossene Form, keine Iteration, kein Tor -- ``ema_rotorcheck`` importiert
    dieses Modul, ein Import zurueck waere ein Zirkel. Die Groesse der Tasche
    (``laenge``) kommt von aussen; wer sie erst suchen muss, tut das in
    ``ema_screen.einpassen`` mit dem echten Layouttor als Pruefstein.

    ``d_half`` folgt aus der Achswand: die INNERE Kappe ist die dichteste Stelle an
    der d-Achse (der Rechteckrand liegt bei ``ht*cos t <= ht`` weiter weg), ihr
    Mittelpunkt sitzt bei ``d_half - gap*sin t``, ihr Radius ist ``ht``.

    ``r_pos`` folgt daraus, dass die AEUSSERE Kappe die Randwand genau beruehrt --
    das ist „so weit aussen wie moeglich" bei gegebener Laenge: ihr Mittelpunkt
    laeuft auf dem Kreis ``R = r_rot - wand_rand - ht``.

    **``r_pos`` ist das INNERE ENDE des Magneten, nicht die Taschenmitte** (so liest
    es ``leg_center``). Vom inneren Ende bis zum aeusseren Kappenmittelpunkt sind es
    darum ``L/2 + hl = L + gap`` und nicht ``hl``. Der Unterschied ist keiner auf
    dem Papier: mit ``hl`` gerechnet stand die Tasche einer 84-mm-Auslegung
    **36,2 mm** ausserhalb des Rotors, und weil der Positionsmodus die Laenge
    zusaetzlich klemmt, fiel das in einer Vergleichsmessung nicht auf.
    """
    wand_rand = WAND_RAND_MM if wand_rand is None else wand_rand
    wand_achse = WAND_ACHSE_MM if wand_achse is None else wand_achse
    ht = mag_h / 2.0 + gap                       # halbe Taschendicke = Kappenradius
    d = max(laenge, 0.0) + gap                   # inneres Ende → aeusserer Kappenmittelpunkt
    d_half = wand_achse + ht + gap * math.sin(halb_winkel)
    R = r_rot - wand_rand - ht
    y = d_half + d * math.sin(halb_winkel)
    if R <= 0 or y >= R:
        # Der Slot passt bei dieser Laenge/Dicke gar nicht mehr zwischen die Waende.
        # Kein Ersatzwert, der wie ein Entwurf aussieht: der Sitz faellt auf den
        # innersten moeglichen zurueck und das Layouttor sagt es dann deutlich.
        return d_half, max(r_rot * 0.05, 1.0)
    r_pos = math.sqrt(R * R - y * y) - d * math.cos(halb_winkel)
    return d_half, r_pos


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


def slot_laenge_max(r_rot: float, r_shaft: float, half_ang: float, mag_h: float,
                    gap: float, wand_rand: float = None, wand_achse: float = None) -> float:
    """Laengster Magnet, der zwischen Achswand, Randwand und Welle in den Slot geht.

    Dieselbe Quadratik wie ``_max_magnet_width``, nur nach der LAENGE aufgeloest
    statt nach dem Sitz: gesucht ist ``d = L + gap`` (inneres Ende → aeusserer
    Kappenmittelpunkt, s. ``sitz_aus_waenden``) mit
    ``sqrt(R^2 - (d_half + d*sin t)^2) - d*cos t = r_min``.

    Der Nachbarpol steht hier NICHT drin -- den kennt erst das Layouttor, und
    ``ema_screen.einpassen`` zieht die Laenge daran nach unten. Dieses Modul liefert
    die obere Schranke aus der eigenen Polgeometrie, damit ``magnet_legs`` auch bei
    ``magWidth = 0`` („Slot fuellen") eine vollstaendige Geometrie zurueckgibt statt
    einer mit Magneten der Laenge null.
    """
    wand_rand = WAND_RAND_MM if wand_rand is None else wand_rand
    wand_achse = WAND_ACHSE_MM if wand_achse is None else wand_achse
    ht = mag_h / 2.0 + gap
    d_half = wand_achse + ht + gap * math.sin(half_ang)
    R = r_rot - wand_rand - ht
    r_min = r_shaft + wand_achse + mag_h / 2.0 + 2.0 * gap
    a, b = math.sin(half_ang), math.cos(half_ang)
    P = d_half * a + r_min * b
    Q = r_min * r_min + d_half * d_half - R * R
    disc = P * P - Q
    if disc <= 0:
        return 0.0
    return max(-P + math.sqrt(disc) - gap, 0.0)


def _v_sitz(geom: dict, half_ang: float, mag_h: float, mag_w: float,
            wand_rand: float = None):
    """``(r_pos, d_half, laenge)`` fuer die V-artigen Bauformen, je nach ``pocketMode``.

    ``position``/``diameter`` (bisher, Vorgabe fuer bestehende Projekte): der Sitz
    kommt aus ``magDepthRel``/``magDist``, die Laenge wird gegen die Randwand
    geklemmt. ``wand`` (s. ``sitz_aus_waenden``): die Laenge ist die Vorgabe, der
    Sitz folgt aus den Waenden -- ``magDist`` und ``magDepthRel`` sind dann
    ABGELEITET und werden von ``ema_screen.einpassen`` zurueckgeschrieben, damit im
    Payload die Maschine steht, die wirklich gebaut wird.
    """
    r_rot, r_shaft, r_pos = _common(geom)
    d_half = float(geom["magDist"]) / 2
    if pocket_mode(geom) == "wand":
        gap = _spalt(geom)
        if mag_w <= 0:                      # „Slot fuellen" -- s. slot_laenge_max
            mag_w = slot_laenge_max(r_rot, r_shaft, half_ang, mag_h, gap,
                                    wand_rand=wand_rand)
        d_half, r_pos = sitz_aus_waenden(r_rot, half_ang, mag_h, gap,
                                         mag_w, wand_rand=wand_rand)
        return r_pos, d_half, mag_w
    eb = (WAND_RAND_MM if wand_rand is None else wand_rand) + mag_h / 2
    return r_pos, d_half, min(mag_w, _max_magnet_width(r_pos, d_half, half_ang,
                                                       r_rot, eb))


def _build_v(geom: dict):
    r_rot, _r_shaft, r_pos = _common(geom)
    mag_h = float(geom["magThick"])
    d_half = float(geom["magDist"]) / 2
    half_ang = math.radians(float(geom["magAngle"]) / 2)
    # Diameter mode: the pocket is defined by inner-Ø, outer-Ø and the V angle.
    # The inner magnet corner (at tangential offset d_half) sits at radius
    # pocketInnerD/2 → r_pos = sqrt(r_inner² − d_half²); the length follows from
    # the outer corner reaching pocketOuterD/2 (same quadratic as the OD clamp).
    if pocket_mode(geom) == "diameter":
        r_pos = math.sqrt(max(25.0, (float(geom["pocketInnerD"]) / 2) ** 2 - d_half ** 2))
        mag_w = _max_magnet_width(r_pos, d_half, half_ang, float(geom["pocketOuterD"]) / 2, 0.0)
        # Thickness-aware clamp: keep the magnet CORNER (not just its centreline)
        # inside r_rot - BRIDGE by reserving half the thickness.
        mag_w = min(mag_w, _max_magnet_width(r_pos, d_half, half_ang, r_rot,
                                             WAND_RAND_MM + mag_h / 2))
    else:
        r_pos, d_half, mag_w = _v_sitz(geom, half_ang, mag_h, float(geom["magWidth"]))
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
    # Per-arm opening angle (clamped to a sane V range so corners stay inside).
    ha_top = min(max(half_ang + asym, math.radians(5)), math.radians(85))
    ha_bot = min(max(half_ang - asym, math.radians(5)), math.radians(85))
    # Jeder Arm sitzt an SEINEN Waenden -- bei verschiedenen Oeffnungswinkeln sind
    # das verschiedene Sitze, und genau das ist der Sinn der asymmetrischen Form.
    r_top, d_top, w_top = _v_sitz(geom, ha_top, mag_h, float(geom["magWidth"]))
    r_bot, d_bot, w_bot = _v_sitz(geom, ha_bot, mag_h, float(geom["magWidth"]))
    legs = [
        Leg(r_top,  d_top,  ha_top, w_top, mag_h, "perp", +1),
        Leg(r_bot, -d_bot, -ha_bot, w_bot, mag_h, "perp", -1),
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
    r_pos, d_half, mag_w = _v_sitz(geom, half_ang, mag_h, float(geom["magWidth"]))
    # Bottom bar BELOW the arm feet (r_pos) → radial gap, disjoint from the arms
    # regardless of its tangential length.  The clearance has to be reserved between
    # POCKETS, not between magnet bodies: each pocket is one CAD gap wider than its
    # magnet on every side, and the arm foot carries a round end cap of the same
    # radius.  Reserving only ``mag_h + BRIDGE_MM`` left a **1.75 mm** web against
    # (measured back when BRIDGE_MM was 2.0; the 1.15 factor scales with it)
    # the 2.00 mm minimum of ``rotor_layout_check`` — measured, and independent of
    # magThick, magAngle and magWidth, i.e. the U-cup never passed the layout gate
    # at any parameter setting.  The 15 % on the bridge covers the difference
    # between the cap-to-cap and the box-to-box measure (~0.05 mm).
    gap = _spalt(geom)
    # Im Wandmodus gilt fuer JEDEN Steg im Blech ``WAND_QACHSE_MM`` (s.
    # ``ema_screen._einpassen_wand``); der Bodenbalken muss diesen Abstand zu den
    # Armfuessen halten, sonst faellt die U-Form dort durch, wo sie frueher gerade
    # eben durchkam.
    _steg = WAND_QACHSE_MM if pocket_mode(geom) == "wand" else BRIDGE_MM
    bar_r = max(r_pos - mag_h - 2 * gap - _steg * 1.15,
                r_bore + mag_h / 2 + 1.0)
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
    if pocket_mode(geom) == "wand":
        # Die AEUSSERE Lage sitzt an der Randwand; die innere haengt um
        # ``magLayerGap`` darunter. Dass sich die beiden dabei nicht beruehren, ist
        # der Punkt, an dem das Doppel-V kippt -- geprueft wird es mit
        # ``ema_rotorcheck.pocket_distance`` in ``ema_screen.einpassen``, das
        # ``magLayerGap`` noetigenfalls anhebt und die Anhebung MELDET. Hier steht
        # nur die Bauvorschrift, kein Tor: dieses Modul kennt das Tor nicht
        # (Importzirkel), und ein zweites Abstandsmass daneben waere die naechste
        # stille Abschrift.
        gap = _spalt(geom)
        r1, d1, w1 = _v_sitz(geom, half_ang2, mag_h, float(geom["magWidth"]))
        w0 = float(geom["magWidth"])
        if w0 <= 0:                          # „Slot fuellen" auch fuer die innere Lage
            w0 = slot_laenge_max(r_rot, _r_shaft, half_ang, mag_h, gap,
                                 wand_rand=WAND_RAND_MM + d_layer)
        d_half, r_pos = sitz_aus_waenden(r_rot, half_ang, mag_h, gap, w0,
                                         wand_rand=WAND_RAND_MM + d_layer)
    else:
        eb = WAND_RAND_MM + mag_h / 2
        d1 = d_half
        w0 = min(float(geom["magWidth"]),
                 _max_magnet_width(r_pos, d_half, half_ang, r_rot, eb))
        r1 = r_pos + d_layer
        w1 = min(float(geom["magWidth"]) * 1.05,
                 _max_magnet_width(r1, d_half, half_ang2, r_rot, eb))
    legs = [
        Leg(r_pos,  d_half,  half_ang, w0, mag_h, "perp", +1, layer=0),
        Leg(r_pos, -d_half, -half_ang, w0, mag_h, "perp", -1, layer=0),
        Leg(r1,  d1,  half_ang2, w1, mag_h, "perp", +1, layer=1),
        Leg(r1, -d1, -half_ang2, w1, mag_h, "perp", -1, layer=1),
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
    # Im Wandmodus ist das eine groessere RANDWAND fuer die Arme -- das Deck steht
    # dann an der eigentlichen Randwand, die Arme eine Deckhoehe darunter.
    _steg = WAND_QACHSE_MM if pocket_mode(geom) == "wand" else WAND_RAND_MM
    arm_bridge = WAND_RAND_MM + _steg + 1.5 * mag_h
    r_pos, d_half, mag_w = _v_sitz(geom, half_ang, mag_h, float(geom["magWidth"]),
                                   wand_rand=arm_bridge - mag_h / 2)
    r_tip = r_pos + mag_w * math.cos(half_ang)
    y_tip = d_half + mag_w * math.sin(half_ang)
    deck_r = min(r_tip + mag_h + _steg, r_rot - mag_h / 2 - WAND_RAND_MM)
    tang = float(geom.get("magTangLen", 0))
    deck_len = tang if tang > 0 else 1.6 * y_tip
    # keep the deck corner inside r_rot - BRIDGE
    max_half = math.sqrt(max((r_rot - WAND_RAND_MM) ** 2 - (deck_r + mag_h / 2) ** 2, 0.0))
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
                 _max_magnet_width(rk, d_half, hak, r_rot, WAND_RAND_MM + mag_h / 2))
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


# ── Offene Magnettasche ───────────────────────────────────────────────────────
#
# Der Steg zwischen Tasche und Rotorrand haelt den Polschuh mechanisch UND
# kurzschliesst den Magneten magnetisch -- er ist beides zugleich, und darum ist
# seine Breite die eigentliche Entwurfsentscheidung des Speichenlaeufers. Wird er
# weggelassen, ist die Tasche zum Luftspalt hin OFFEN:
#
#   magnetisch  der Streupfad ueber den Steg entfaellt; genau er steckt in
#               ``ema_analysis._analytical_Bgap`` als ``k_leak``
#   mechanisch  der Rotorrand ist unterbrochen. Den Polschuh haelt dann nichts
#               mehr ausser einer Bandage, einer Schwalbenschwanzfuehrung oder
#               Endscheiben — das ist kein Detail, sondern eine andere Bauart.
#
# Deshalb ist es ein eigener Schalter und keine stille Folge von BRIDGE_MM = 0:
# wer ihn setzt, hat die mechanische Seite zu beantworten, und `rotor_layout_check`
# sagt es ihm.
TASCHE_OFFEN = ("nein", "aussen", "innen", "beide")
TASCHE_OFFEN_LABEL = {
    "nein":   "geschlossen (Steg am Rand)",
    "aussen": "zum Luftspalt offen",
    "innen":  "zur Welle offen",
    "beide":  "beidseitig offen",
}


def taschenoeffnung(geom: dict) -> str:
    """Wie die Magnettasche geoeffnet ist -- ``nein`` (Vorgabe) heisst: Steg steht."""
    w = str((geom or {}).get("magTascheOffen", "nein") or "nein").strip().lower()
    return w if w in TASCHE_OFFEN else "nein"


def stegbreite_mm(geom: dict) -> tuple:
    """Der WIRKLICHE Steg aussen und innen [mm] -- 0, wo die Tasche offen ist.

    Eine Quelle fuer alle, die den Steg brauchen: die Zeichnung, das Layouttor,
    die Fliehkraftpruefung und die Streuung im analytischen Luftspaltfeld.
    """
    offen = taschenoeffnung(geom)
    aussen = 0.0 if offen in ("aussen", "beide") else BRIDGE_MM
    innen = 0.0 if offen in ("innen", "beide") else BRIDGE_MM
    return aussen, innen


def _build_spoke(geom: dict):
    """Spoke-type: one radial slab per pole, tangentially magnetised (flux focus)."""
    r_rot = geom["rotorOD"] / 2
    r_shaft = geom["shaftD"] / 2
    mag_h = float(geom["magThick"])
    # Die Tasche endet nicht am Magneten: sie traegt an beiden Enden eine runde
    # Kappe vom Radius ``mag_h/2 + Spalt``.  Mit ``r_start = r_shaft + 1.0`` schnitt
    # diese Kappe fuer jede Dicke ab 1,8 mm in die Wellenbohrung — bei den ueblichen
    # 6 mm um 2,1 mm.  Der Saum reserviert Steg UND Kappe an beiden Enden.
    gap = _spalt(geom)
    # Der Saum reserviert Steg UND Kappe -- je Ende einzeln, denn die Tasche kann
    # aussen offen und innen geschlossen sein (s. ``taschenoeffnung``). Ist ein
    # Ende offen, laeuft der Magnet bis an die Grenze: aussen bis an den
    # Luftspalt, innen bis an die Welle. Die runde Kappe ragt dann darueber
    # hinaus und wird vom Rotorblech abgeschnitten — genau das IST die Oeffnung.
    #
    # Die Waende der Speichentasche stehen jetzt ausdruecklich (WAND_SPEICHE_*) und
    # gelten fuer die TASCHE, nicht fuer den Magneten. Nachgemessen lieferte der
    # frueherer Saum ``steg + mag_h/2 + gap`` an beiden Enden **1,20 mm**, obwohl
    # ``BRIDGE_MM`` 1,3 sagt: die Endkappe sitzt um ``gap`` AUSSERHALB des
    # Magnetendes (halbe Taschenlaenge ist ``L/2 + gap``) und traegt selbst den
    # Radius ``mag_h/2 + gap`` -- der Klebespalt geht also ZWEIMAL ein. Der Saum
    # rechnet ihn jetzt zweimal, und dann steht die Wand, die dransteht.
    steg_a, steg_i = stegbreite_mm(geom)
    wand_a = WAND_SPEICHE_A_MM if steg_a > 0 else 0.0
    wand_i = WAND_SPEICHE_I_MM if steg_i > 0 else 0.0
    saum_a = (wand_a + mag_h / 2 + 2 * gap) if steg_a > 0 else 0.0
    saum_i = (wand_i + mag_h / 2 + 2 * gap) if steg_i > 0 else 0.0
    r_start = r_shaft + saum_i
    length = max(r_rot - saum_a - r_start, 5.0)
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


# ── Zusatzteile im Rotorblech: Flussbarrieren und Wuchtverschraubung ──────────
#
# Beide schneiden Material aus demselben Blech, in dem die Magnettaschen sitzen,
# und beide standen bisher an DREI Stellen einzeln ausgeschrieben: im
# FreeCAD-Erzeuger (``ema_freecad.build_full_motor_script``), im 2-D-Schnittbild
# (``ema_pipeline._save_cad_images``) und in der Leinwand-Vorschau (``ema.html``,
# ``drawRotor``). Drei Abschriften derselben Formel sind drei Gelegenheiten
# auseinanderzulaufen -- und das Layouttor kannte sie ueberhaupt nicht, obwohl es
# genau die Frage beantwortet, ob im Blech noch Platz ist.
#
# Hier stehen sie einmal, als reine Zahlen ohne Zeichen- oder CAD-Bezug. Der
# FreeCAD-Erzeuger schreibt seinen Code weiterhin selbst (er laeuft in einem
# fremden Prozess und kann nichts importieren); die Formeln sind aus ihm
# uebernommen und in ``test_rotorcheck`` gegen ihn festgenagelt.

# Gewindenenndurchmesser [mm]. Spiegelt ``_THREAD_D`` im FreeCAD-Erzeuger.
THREAD_D = {"M4": 4.0, "M5": 5.0, "M6": 6.0, "M8": 8.0,
            "M10": 10.0, "M12": 12.0, "M16": 16.0, "M20": 20.0}

# Steg zwischen Barrierenende und Rotoraussenrand, wie im Erzeuger fest gesetzt.
FB_RANDSTEG_MM = 2.0


def flux_barrier_slots(geom: dict) -> list:
    """Die radialen Luftschlitze im Rotorblech -- je Schlitz ein Datensatz.

    ``family`` ist ``"d"`` (Polmitte) oder ``"q"`` (zwischen den Polen). Die Winkel,
    der Aussensteg von 2 mm und die Klemmung nach innen auf ``r_shaft + 1`` sind
    zeichengetreu aus ``ema_freecad._flux_barrier_slots`` uebernommen.
    """
    if not (bool(geom.get("genFluxBarrierQ", False))
            or bool(geom.get("genFluxBarrierD", False))):
        return []
    poles = max(2, 2 * max(1, int(geom.get("p", 3))))
    r_rot = float(geom["rotorOD"]) / 2.0
    r_sh  = float(geom["shaftD"]) / 2.0
    breite = max(0.5, min(40.0, float(geom.get("fluxBarrierWidth", 3.0))))
    tiefe  = max(1.0, min(120.0, float(geom.get("fluxBarrierDepth", 10.0))))
    r_out = r_rot - FB_RANDSTEG_MM
    r_in  = max(r_sh + 1.0, r_out - tiefe)
    aus = []
    if bool(geom.get("genFluxBarrierD", False)):
        aus += [(i * 2.0 * math.pi / poles, "d") for i in range(poles)]
    if bool(geom.get("genFluxBarrierQ", False)):
        aus += [((i + 0.5) * 2.0 * math.pi / poles, "q") for i in range(poles)]
    return [{"angle": a, "family": f, "r_in": r_in, "r_out": r_out,
             "width": breite, "depth": max(0.5, r_out - r_in)} for a, f in aus]


def balance_bolt_holes(geom: dict) -> list:
    """Die Durchgangsloecher der Wuchtscheiben-Verschraubung.

    Anzahl = Polzahl (mindestens 2), damit der Rotor symmetrisch bleibt; der
    Lochdurchmesser ist Gewindenennmass + 0,4 mm Spiel. Ohne Angabe eines
    Lochkreises sitzt er auf halber Strecke zwischen Welle und Rotoraussen.
    Zeichengetreu aus ``ema_freecad`` (``bal_hole_r``, ``bal_pcr``,
    ``_balance_positions``).
    """
    if not bool(geom.get("genBalanceBolts", False)):
        return []
    poles = max(2, 2 * max(1, int(geom.get("p", 3))))
    r_rot = float(geom["rotorOD"]) / 2.0
    r_sh  = float(geom["shaftD"]) / 2.0
    gewinde = str(geom.get("balanceBoltThread", "M6")).upper()
    nenn = THREAD_D.get(gewinde, 6.0)
    r_loch = (nenn + 0.4) / 2.0
    kreis_d = max(0.0, float(geom.get("balanceBoltCircleD", 0) or 0))
    r_kreis = kreis_d / 2.0 if kreis_d > 0 else r_sh + (r_rot - r_sh) * 0.5
    versatz = math.radians(float(geom.get("balanceBoltOffsetDeg", 0)))
    n = max(2, poles)
    aus = []
    for i in range(n):
        a = versatz + i * 2.0 * math.pi / n
        aus.append({"angle": a, "x": r_kreis * math.cos(a), "y": r_kreis * math.sin(a),
                    "r": r_loch, "thread": gewinde, "pitch_r": r_kreis})
    return aus
