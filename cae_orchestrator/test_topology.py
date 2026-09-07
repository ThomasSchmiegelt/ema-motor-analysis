"""Consistency / plausibility tests for the rotor magnet topologies.

Runnable headless two ways:
  * `python test_topology.py`     → prints a per-topology PASS/FAIL table, exit≠0 on failure
  * `pytest test_topology.py`     → standard test discovery (slow tests opt-in via -m slow)

Fast tests (no FreeCAD / no solver):
  - no interior-leg overlap (separating-axis test)
  - all legs stay within [shaft bore, rotor OD-bridge]; surface magnets fit the air gap
  - the JS mirror `magnetLegs` in ema.html matches Python `magnet_legs` (needs `node`)

Slow tests (`-m slow`): CAD-script compiles, FDM field is sane, ffmpeg present.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

try:
    import pytest
except ModuleNotFoundError:                      # allow `python test_topology.py` without pytest
    class _Skip(Exception):
        pass

    class _Mark:
        slow = staticmethod(lambda f: f)
        @staticmethod
        def parametrize(_names, _vals):
            return lambda f: f

    class _PytestShim:
        mark = _Mark()
        @staticmethod
        def skip(msg=""):
            raise _Skip(msg)

    pytest = _PytestShim()

import ema_topology as T
from ema_screen import WAND_BAUFORMEN as T_WAND_BAUFORMEN

HERE = os.path.dirname(os.path.abspath(__file__))
EMA_HTML = os.path.join(HERE, "ema.html")
TOL = 0.1   # mm geometric tolerance

# Base geometry: rotor small enough that surface magnets fit (statorID/2=95).
BASE = dict(
    statorOD=280, statorID=190, rotorOD=170, shaftD=60, shaftBoreD=0,
    slots=54, slotDepth=25, slotWidthRatio=0.5, p=4,
    magAngle=120, magAngle2=90, magDepthRel=0.6, magWidth=35, magThick=6,
    magDist=8, magTangLen=0, airGap=0.7,
    magLayers=3, magLayerGap=9, poleArcFrac=0.83, segPerPole=6,
)

TOPOS = list(T._BUILDERS.keys())
INTERIOR_TOPOS = [s for s in TOPOS
                  if not T.magnet_legs(dict(BASE, magShape=s))[1].is_surface]
SURFACE_TOPOS = [s for s in TOPOS
                 if T.magnet_legs(dict(BASE, magShape=s))[1].is_surface]


# ── geometry helpers ────────────────────────────────────────────────────────

def _rect_corners(leg):
    """Four corners of a leg's magnet body in the pole-local frame."""
    cx, cy = T.leg_center(leg)
    ux, uy = math.cos(leg.tilt), math.sin(leg.tilt)          # long axis
    px, py = -uy, ux                                          # thickness axis
    hl, ht = leg.length / 2, leg.thickness / 2
    return [(cx + sl * hl * ux + st * ht * px,
             cy + sl * hl * uy + st * ht * py)
            for sl in (-1, 1) for st in (-1, 1)]


def _project(corners, ax, ay):
    ds = [cx * ax + cy * ay for cx, cy in corners]
    return min(ds), max(ds)


def _rects_overlap(a, b, tol=TOL):
    """Separating-axis test for two convex quads. True ⇒ they overlap."""
    for r in (a, b):
        for i in range(len(r)):
            ex = r[(i + 1) % len(r)][0] - r[i][0]
            ey = r[(i + 1) % len(r)][1] - r[i][1]
            ax, ay = -ey, ex                                  # edge normal
            n = math.hypot(ax, ay)
            if n < 1e-9:
                continue
            ax, ay = ax / n, ay / n
            amin, amax = _project(a, ax, ay)
            bmin, bmax = _project(b, ax, ay)
            if amin > bmax - tol or bmin > amax - tol:
                return False                                  # separating axis found
    return True


def _overlapping_pairs(geom):
    legs, _ = T.magnet_legs(geom)
    interior = [lg for lg in legs if lg.placement == "interior"]
    rects = [_rect_corners(lg) for lg in interior]
    bad = []
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            if _rects_overlap(rects[i], rects[j]):
                bad.append((i, j))
    return bad


def _bounds_violations(geom):
    legs, meta = T.magnet_legs(geom)
    r_rot = geom["rotorOD"] / 2
    r_bore = geom.get("shaftBoreD", 0) / 2
    msgs = []
    r_shaft = geom["shaftD"] / 2
    for k, lg in enumerate(legs):
        if lg.placement == "surface":
            # inward band [r_rot - t, r_rot]: must fit the rotor radius and not
            # grow past the OD into the stator
            if lg.thickness > (r_rot - r_shaft) + TOL:
                msgs.append(f"surface leg {k} thickness {lg.thickness:.1f} exceeds rotor radial space")
            continue
        for cx, cy in _rect_corners(lg):
            rad = math.hypot(cx, cy)
            if rad > r_rot - T.BRIDGE_MM + TOL:
                msgs.append(f"leg {k} corner r={rad:.1f} > rotorOD/2-bridge={r_rot - T.BRIDGE_MM:.1f}")
            if rad < r_bore - TOL:
                msgs.append(f"leg {k} corner r={rad:.1f} < bore={r_bore:.1f}")
    return msgs


# ── fast tests ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("shape", TOPOS)
def test_no_interior_overlap(shape):
    geom = dict(BASE, magShape=shape)
    bad = _overlapping_pairs(geom)
    assert not bad, f"{shape}: interior magnet legs overlap: pairs {bad}"


@pytest.mark.parametrize("shape", TOPOS)
def test_within_bounds(shape):
    geom = dict(BASE, magShape=shape)
    msgs = _bounds_violations(geom)
    assert not msgs, f"{shape}: " + "; ".join(msgs)


def test_within_bounds_thick_surface():
    """Surface magnets must be clamped so a thick magnet still fits the air gap."""
    for shape in SURFACE_TOPOS:
        geom = dict(BASE, magShape=shape, magThick=15)        # 15 mm would overrun
        msgs = _bounds_violations(geom)
        assert not msgs, f"{shape} (thick): " + "; ".join(msgs)


def test_hollow_shaft_keeps_rotor_bore():
    """A hollow shaft must not move the rotor bore (r_pos reference)."""
    solid = T.magnet_legs(dict(BASE, magShape="v", shaftBoreD=0))[0]
    hollow = T.magnet_legs(dict(BASE, magShape="v", shaftBoreD=30))[0]
    assert [round(l.r_pos, 6) for l in solid] == [round(l.r_pos, 6) for l in hollow]


# ── JS ↔ Python mirror ──────────────────────────────────────────────────────

def _extract_js_mirror():
    src = open(EMA_HTML, encoding="utf-8").read()
    a = src.find("// <<MIRROR-START>>")
    b = src.find("// <<MIRROR-END>>")
    if a < 0 or b < 0:
        return None
    return src[a:b]


def _js_legs(geom):
    block = _extract_js_mirror()
    if block is None:
        pytest.skip("MIRROR sentinels not found in ema.html")
    if not shutil.which("node"):
        pytest.skip("node not available")
    driver = block + (
        "\nconst _g = JSON.parse(require('fs').readFileSync(0,'utf8'));"
        "\nprocess.stdout.write(JSON.stringify(magnetLegs(_g)));\n"
    )
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
        f.write(driver)
        path = f.name
    try:
        out = subprocess.run(["node", path], input=json.dumps(geom),
                             capture_output=True, text=True, timeout=20)
        if out.returncode != 0:
            raise AssertionError("node error: " + out.stderr[:400])
        return json.loads(out.stdout)
    finally:
        os.unlink(path)


_FIELDS = ["r_pos", "offset", "tilt", "length", "thickness",
           "mag_mode", "mag_sign", "mag_rot", "placement", "layer"]
_JS_KEY = {"r_pos": "rPos", "mag_mode": "magMode", "mag_sign": "magSign",
           "mag_rot": "magRot"}


@pytest.mark.parametrize("shape", TOPOS)
def test_js_mirror_matches(shape):
    geom = dict(BASE, magShape=shape)
    py_legs, _ = T.magnet_legs(geom)
    js_legs = _js_legs(geom)
    assert len(js_legs) == len(py_legs), f"{shape}: leg count {len(js_legs)} vs {len(py_legs)}"
    for i, (pl, jl) in enumerate(zip(py_legs, js_legs)):
        for fld in _FIELDS:
            pv = getattr(pl, fld)
            jv = jl.get(_JS_KEY.get(fld, fld))
            if isinstance(pv, (int, float)) and not isinstance(pv, bool):
                assert abs(float(pv) - float(jv)) < 1e-6, \
                    f"{shape} leg{i}.{fld}: py={pv} js={jv}"
            else:
                assert str(pv) == str(jv), f"{shape} leg{i}.{fld}: py={pv} js={jv}"


def test_js_mirror_diameter_mode():
    """V-form pocket-by-diameter mode (outer-Ø / inner-Ø / angle) must also match
    between Python `magnet_legs` and the JS `magnetLegs` mirror."""
    geom = dict(BASE, magShape="v", pocketMode="diameter",
                pocketOuterD=160, pocketInnerD=120)
    py_legs, _ = T.magnet_legs(geom)
    js_legs = _js_legs(geom)
    assert len(js_legs) == len(py_legs)
    for i, (pl, jl) in enumerate(zip(py_legs, js_legs)):
        for fld in _FIELDS:
            pv = getattr(pl, fld)
            jv = jl.get(_JS_KEY.get(fld, fld))
            if isinstance(pv, (int, float)) and not isinstance(pv, bool):
                assert abs(float(pv) - float(jv)) < 1e-6, f"diameter leg{i}.{fld}: py={pv} js={jv}"
            else:
                assert str(pv) == str(jv), f"diameter leg{i}.{fld}: py={pv} js={jv}"


def _vergleiche(geom, marke):
    py_legs, _ = T.magnet_legs(geom)
    js_legs = _js_legs(geom)
    assert len(js_legs) == len(py_legs), \
        f"{marke}: leg count {len(js_legs)} vs {len(py_legs)}"
    for i, (pl, jl) in enumerate(zip(py_legs, js_legs)):
        for fld in _FIELDS:
            pv = getattr(pl, fld)
            jv = jl.get(_JS_KEY.get(fld, fld))
            if isinstance(pv, (int, float)) and not isinstance(pv, bool):
                assert abs(float(pv) - float(jv)) < 1e-6, \
                    f"{marke} leg{i}.{fld}: py={pv} js={jv}"
            else:
                assert str(pv) == str(jv), f"{marke} leg{i}.{fld}: py={pv} js={jv}"


@pytest.mark.parametrize("shape", list(T_WAND_BAUFORMEN))
@pytest.mark.parametrize("magw", [0, 30])
def test_js_mirror_wandmodus(shape, magw):
    """Der Wandmodus muss im Browser dieselbe Maschine zeichnen wie im Rechenwerk.

    Beide ``magWidth``-Faelle: 0 heisst „Slot fuellen" (die Laenge kommt dann aus
    ``slot_laenge_max``), ein gesetzter Wert heisst „so lang bauen und so weit
    aussen setzen, wie die Randwand zulaesst". Liefen die beiden Fassungen
    auseinander, zeigte die Leinwand eine andere Tasche als die, die gerechnet und
    gebaut wird -- und beide saehen plausibel aus.
    """
    _vergleiche(dict(BASE, magShape=shape, pocketMode="wand", magWidth=magw),
                f"wand/{shape}/W{magw}")


@pytest.mark.parametrize("offen", ["nein", "aussen", "innen", "beide"])
def test_js_mirror_speiche_oeffnung(offen):
    """Die Speichentasche und ihre ausdrueckliche Oeffnung, py gegen js."""
    _vergleiche(dict(BASE, magShape="spoke", magTascheOffen=offen), f"spoke/{offen}")


def test_waende_py_gegen_js():
    """Die fuenf Wandmasse stehen in BEIDEN Fassungen -- und mit denselben Zahlen.

    Sie sind der Kern des Wandmodus; eine stille Abweichung waere eine andere
    Maschine bei gleichem Payload. Gelesen wird der JS-Block, nicht nachgetippt.
    """
    block = _extract_js_mirror()
    if block is None:
        pytest.skip("MIRROR sentinels not found in ema.html")
    for name, wert in (("WAND_RAND", T.WAND_RAND_MM), ("WAND_ACHSE", T.WAND_ACHSE_MM),
                       ("WAND_QACHSE", T.WAND_QACHSE_MM),
                       ("WAND_SP_A", T.WAND_SPEICHE_A_MM),
                       ("WAND_SP_I", T.WAND_SPEICHE_I_MM)):
        assert f"{name} = {wert}" in block, \
            f"{name} = {wert} steht nicht im JS-Spiegel (ema_topology sagt {wert})"
    # Und sie stehen NUR dort: kein Wandmass darf als nacktes Literal in einer
    # Formel wiederauftauchen, sonst laeuft eine Aenderung nur halb durch.
    formeln = block.split("magnetLegs")[0]
    for wert in (T.WAND_ACHSE_MM, T.WAND_QACHSE_MM):
        assert f"= {wert} +" not in formeln and f" {wert} + ht" not in formeln, \
            f"{wert} steht als Literal in einer JS-Formel statt als WAND_*-Konstante"


def test_wandmodus_haelt_seine_waende():
    """Was der Wandmodus baut, haelt Rand-, d-Achsen- und q-Achsenwand ein.

    Gemessen wird an der TASCHE (``ema_rotorcheck.Pocket``, also einschliesslich
    Klebespalt und Endkappen) -- nicht am Magnetkoerper, denn geschnitten wird die
    Tasche. Das ist genau die Stelle, an der die alte Klemme danebenlag: sie hielt
    die Magnetmittellinie, das Tor mass die Taschenecken.
    """
    import ema_rotorcheck as RC
    from ema_screen import einpassen
    for shape in T_WAND_BAUFORMEN:
        g = einpassen(dict(BASE, magShape=shape, pocketMode="wand", magWidth=0))
        assert g["ok"], f"{shape}: {g['grund']}"
        geom = g["geom"]
        r_rot = geom["rotorOD"] / 2.0
        taschen, _ = RC._magnettaschen(geom)
        for base, pk in taschen:
            _rmin, rmax = pk.radius_bounds()
            assert rmax <= r_rot - T.WAND_RAND_MM + 1e-6, \
                f"{shape}: Tasche steht {r_rot - rmax:.3f} mm vom Rand statt {T.WAND_RAND_MM}"
        chk = RC.rotor_layout_check(geom, min_web_mm=T.WAND_QACHSE_MM)
        assert chk["ok"], f"{shape}: {chk['fatal'][:1]}"
        assert chk["layout"]["min_web_found_mm"] >= T.WAND_QACHSE_MM - 1e-6


def test_speiche_haelt_ihre_waende():
    """Speiche: aussen 1,5 mm, innen 2,0 mm — an der Tasche gemessen.

    Vorher standen dort BEIDE bei 1,20 mm, obwohl der Code 1,3 meinte: der
    Klebespalt geht zweimal ein (die Kappe sitzt um ``gap`` ausserhalb des
    Magnetendes UND traegt selbst den Radius ``magThick/2 + gap``).
    """
    import ema_rotorcheck as RC
    for th in (3.0, 6.0, 10.0):
        geom = dict(BASE, magShape="spoke", magThick=th)
        r_rot, r_sh = geom["rotorOD"] / 2.0, geom["shaftD"] / 2.0
        taschen, _ = RC._magnettaschen(geom)
        rmin, rmax = taschen[0][1].radius_bounds()
        assert abs((r_rot - rmax) - T.WAND_SPEICHE_A_MM) < 1e-6, \
            f"magThick={th}: Wand aussen {r_rot - rmax:.3f} statt {T.WAND_SPEICHE_A_MM}"
        assert abs((rmin - r_sh) - T.WAND_SPEICHE_I_MM) < 1e-6, \
            f"magThick={th}: Wand innen {rmin - r_sh:.3f} statt {T.WAND_SPEICHE_I_MM}"


# ── slow tests (opt-in: pytest -m slow) ─────────────────────────────────────

@pytest.mark.slow
@pytest.mark.parametrize("shape", TOPOS)
def test_cad_compiles(shape):
    import ema_freecad
    geom = dict(BASE, magShape=shape)
    code = ema_freecad.build_full_motor_script(geom, 80.0, "/tmp/_t.FCStd")
    compile(code, "<cad>", "exec")


@pytest.mark.slow
@pytest.mark.parametrize("shape", TOPOS)
def test_field_sane(shape):
    import ema_analysis
    geom = dict(BASE, magShape=shape)
    bg = ema_analysis._analytical_Bgap(geom)
    assert 0.05 <= bg <= 2.3, f"{shape}: B_gap {bg} out of band"


@pytest.mark.slow
def test_field_monotonic_sanity():
    import ema_analysis
    v = ema_analysis._analytical_Bgap(dict(BASE, magShape="v"))
    vv = ema_analysis._analytical_Bgap(dict(BASE, magShape="vv"))
    assert vv >= v - 0.05, f"vv ({vv}) should be >= v ({v})"
    lo = ema_analysis._analytical_Bgap(dict(BASE, magShape="spoke", p=2))
    hi = ema_analysis._analytical_Bgap(dict(BASE, magShape="spoke", p=8))
    assert hi > lo, f"spoke flux-focusing should rise with pole count ({lo}->{hi})"


@pytest.mark.slow
def test_ffmpeg_present():
    assert shutil.which("ffmpeg"), "ffmpeg not on PATH"


# ── direct-run summary ──────────────────────────────────────────────────────

def _main():
    print(f"Topologies: {TOPOS}")
    print(f"  interior: {INTERIOR_TOPOS}")
    print(f"  surface : {SURFACE_TOPOS}\n")
    rows, failures = [], 0
    try:
        js_ok = _extract_js_mirror() is not None and bool(shutil.which("node"))
    except Exception:
        js_ok = False
    for shape in TOPOS:
        geom = dict(BASE, magShape=shape)
        bad = _overlapping_pairs(geom)
        bnd = _bounds_violations(geom)
        mir = "skip"
        if js_ok:
            try:
                jl = _js_legs(geom)
                pl, _ = T.magnet_legs(geom)
                mir = "OK" if len(jl) == len(pl) else f"len {len(jl)}!={len(pl)}"
            except Exception as e:
                mir = f"ERR {e}"[:30]
        ov = "OK" if not bad else f"OVERLAP {bad}"
        bd = "OK" if not bnd else f"OOB({len(bnd)})"
        if bad or bnd:
            failures += 1
        rows.append((shape, ov, bd, mir))
    w = max(len(r[0]) for r in rows)
    print(f"{'topo':<{w}}  {'overlap':<16} {'bounds':<10} mirror")
    for s, ov, bd, mir in rows:
        print(f"{s:<{w}}  {ov:<16} {bd:<10} {mir}")
    print(f"\n{failures} topolog{'y' if failures==1 else 'ies'} with geometry violations")

    # ── Wandmodus ────────────────────────────────────────────────────────────
    print("\nWandmodus (Rand %.1f / d-Achse %.1f / q-Achse %.1f mm)"
          % (T.WAND_RAND_MM, T.WAND_ACHSE_MM, T.WAND_QACHSE_MM))
    pruefungen = [("Waende py<->js", test_waende_py_gegen_js),
                  ("Waende gehalten", test_wandmodus_haelt_seine_waende),
                  ("Speichenwaende", test_speiche_haelt_ihre_waende)]
    if js_ok:
        for shape in T_WAND_BAUFORMEN:
            for magw in (0, 30):
                pruefungen.append((f"Spiegel wand/{shape}/W{magw}",
                                   lambda sh=shape, w=magw: test_js_mirror_wandmodus(sh, w)))
        for offen in ("nein", "aussen", "innen", "beide"):
            pruefungen.append((f"Spiegel spoke/{offen}",
                               lambda o=offen: test_js_mirror_speiche_oeffnung(o)))
    for name, fn in pruefungen:
        try:
            fn()
            print(f"  OK   {name}")
        except Exception as e:                                   # noqa: BLE001
            failures += 1
            print(f"  FEHL {name}: {str(e)[:140]}")

    # Was der frische Payload wirklich baut -- die Zahl, an der der Agent haengt.
    try:
        from ema_screen import einpassen
        g = einpassen(dict(BASE, magShape="v", pocketMode="wand", magWidth=0))["geom"]
        print(f"\n  frischer V-Laeufer: magWidth {g['magWidth']} mm - "
              f"magDist {g['magDist']} mm - magDepthRel {g['magDepthRel']}")
    except Exception as e:                                       # noqa: BLE001
        print(f"  (Einpassung nicht lesbar: {e})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(_main())
