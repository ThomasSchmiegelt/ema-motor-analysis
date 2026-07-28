"""Tests für ema_step_import — FreeCAD-frei (synthetische Solid-Metadaten).

Deckt ab: Klassifikation (Welle/Rotor/Stator/Magnete), Polzahl-Schätzung,
Maßableitung und Magnet-OBB-Fit + einen Round-trip (Canvas-Halbpol → globale
Magnet-Rechtecke → detect_magnets rekonstruiert den Halbpol).

Lauf: ``python test_step_import.py`` (oder via pytest).
"""

import math

import ema_step_import as SI
import ema_design_optimize as DOPT


# ── Synthetische Geometrie-Bausteine ────────────────────────────────────────────

def _ring(idx, r_in, r_out, vol, z0=0.0, z1=120.0):
    """Annulus-Metadaten (com im Zentrum, r_min/r_max = Innen-/Außenradius)."""
    return {"id": idx, "vol": vol, "com": [0.0, 0.0, (z0 + z1) / 2],
            "r_min": r_in, "r_max": r_out, "z0": z0, "z1": z1,
            "nfaces": 4, "xy": [[r_out, 0], [0, r_out], [-r_out, 0], [0, -r_out]]}


def _rect_solid(idx, cx, cy, ang_deg, length, thick, vol, z0=0.0, z1=120.0):
    """Rechteck-Solid (Magnet): Footprint = 4 Ecken (zentriert um den Ursprung)."""
    a = math.radians(ang_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    corners = []
    for su in (-0.5, 0.5):
        for sv in (-0.5, 0.5):
            corners.append([round(cx + su * length * ux + sv * thick * vx, 3),
                            round(cy + su * length * uy + sv * thick * vy, 3)])
    rs = [math.hypot(x, y) for x, y in corners]
    return {"id": idx, "vol": vol, "com": [cx, cy, (z0 + z1) / 2],
            "r_min": round(min(rs), 3), "r_max": round(max(rs), 3),
            "z0": z0, "z1": z1, "nfaces": 6, "xy": corners}


def _build_motor(poles=8, radial_bar=True):
    """Synthetischer Motor: Welle + Rotor + Stator + `poles` Magnete + 48 Coils."""
    solids = []
    nid = 0
    solids.append(_ring(nid, 0.0, 30.0, vol=2.7e5)); nid += 1            # Welle (Vollzyl. r_min=0)
    rotor_id = nid
    solids.append(_ring(nid, 30.0, 94.0, vol=2.5e6)); nid += 1          # Rotorblech
    stator_id = nid
    solids.append(_ring(nid, 95.0, 140.0, vol=5.0e6)); nid += 1         # Statorblech (max r_max)
    # Magnete: radiale Stäbe, Zentrum bei r=75, Länge 30 (radial), Dicke 6 (tangential)
    sector = 2 * math.pi / poles
    for k in range(poles):
        th = k * sector
        cx, cy = 75 * math.cos(th), 75 * math.sin(th)
        ang = math.degrees(th) if radial_bar else math.degrees(th) + 90
        solids.append(_rect_solid(nid, cx, cy, ang, 30.0, 6.0, vol=1.8e4)); nid += 1
    # Coils im Statorbereich (r≈118), 48 Nuten
    for k in range(48):
        th = k * 2 * math.pi / 48
        cx, cy = 118 * math.cos(th), 118 * math.sin(th)
        solids.append(_rect_solid(nid, cx, cy, math.degrees(th), 20.0, 8.0, vol=9.0e3)); nid += 1
    return solids


# ── Tests ───────────────────────────────────────────────────────────────────────

def test_classify():
    solids = _build_motor(poles=8)
    roles = SI.classify_solids(solids)
    assert roles["shaft"] is not None and roles["shaft"]["id"] == 0, "Welle falsch"
    assert roles["rotor_iron"]["id"] == 1, "Rotorblech falsch"
    assert roles["stator_iron"]["id"] == 2, "Statorblech falsch"
    assert len(roles["magnets"]) == 8, f"Magnete: {len(roles['magnets'])} ≠ 8"
    assert len(roles["coils"]) == 48, f"Coils: {len(roles['coils'])} ≠ 48"
    print("✓ classify: Welle/Rotor/Stator/8 Magnete/48 Coils")


def test_estimate_poles():
    for P in (4, 6, 8, 12):
        angles = [k * 2 * math.pi / P for k in range(P)]
        got = SI._estimate_poles(angles)
        assert got == P, f"Polzahl {got} ≠ {P}"
    print("✓ estimate_poles: 4/6/8/12 erkannt")


def test_derive_geom():
    roles = SI.classify_solids(_build_motor(poles=8))
    params, warns = SI.derive_geom(roles)
    assert abs(params["rotorOD"] - 188.0) < 1, params["rotorOD"]
    assert abs(params["statorOD"] - 280.0) < 1, params["statorOD"]
    assert abs(params["statorID"] - 190.0) < 1, params["statorID"]
    assert abs(params["shaftD"] - 60.0) < 1, params["shaftD"]
    assert params["p"] == 4, f"p={params['p']} ≠ 4"
    assert params["slots"] == 48, f"slots={params['slots']} ≠ 48"
    assert params["airgap"] > 0
    assert params["magShape"] == "custom"
    print(f"✓ derive_geom: rotorOD={params['rotorOD']} statorOD={params['statorOD']} "
          f"p={params['p']} slots={params['slots']} gap={params['airgap']}")


def test_detect_magnets():
    roles = SI.classify_solids(_build_motor(poles=8, radial_bar=True))
    params, _ = SI.derive_geom(roles)
    mags = SI.detect_magnets(roles, params)
    assert len(mags) >= 1, "kein Magnet rekonstruiert"
    m = mags[0]
    # radialer Stab: Start innen (~60), Länge ~30, Dicke ~6, ~axial (ang≈0)
    assert 50 <= m["r"] <= 70, f"r_pos={m['r']}"
    assert 24 <= m["len"] <= 36, f"len={m['len']}"
    assert 3 <= m["thick"] <= 9, f"thick={m['thick']}"
    assert abs(m["off"]) < 5, f"off={m['off']}"
    print(f"✓ detect_magnets: r={m['r']} off={m['off']} ang={m['ang']} "
          f"len={m['len']} thick={m['thick']}")


def test_roundtrip_canvas():
    """Canvas-Halbpol → globale Magnet-Rechtecke (mit Spiegel + über alle Pole) →
    detect_magnets rekonstruiert annähernd denselben Halbpol."""
    poles = 8
    master = [{"r": 55.0, "off": 6.0, "ang": 20.0, "len": 28.0, "thick": 6.0, "pol": 1}]
    legs = DOPT._mirror_legs(master)            # Master + d-Achsen-Spiegel (voller Pol)

    solids = [_ring(0, 0.0, 30.0, 2.7e5),
              _ring(1, 30.0, 94.0, 2.5e6),
              _ring(2, 95.0, 140.0, 5.0e6)]
    nid = 3
    sector = 2 * math.pi / poles
    for p in range(poles):
        phi = p * sector
        c, s = math.cos(phi), math.sin(phi)
        for lg in legs:
            r0, off0, ang0 = lg["r_pos"], lg["offset"], math.radians(lg["tilt_deg"])
            L, T = lg["length"], lg["thickness"]
            # Magnet-Zentrum im pol-lokalen Frame (Start + halbe Länge entlang Achse)
            cxl = r0 + math.cos(ang0) * L / 2
            cyl = off0 + math.sin(ang0) * L / 2
            # nach global rotieren
            gx = cxl * c - cyl * s
            gy = cxl * s + cyl * c
            gang = math.degrees(ang0) + math.degrees(phi)
            solids.append(_rect_solid(nid, gx, gy, gang, L, T, vol=1.7e4)); nid += 1

    roles = SI.classify_solids(solids)
    params, _ = SI.derive_geom(roles)
    assert params["p"] == poles // 2, f"p={params['p']}"
    mags = SI.detect_magnets(roles, params)
    assert 1 <= len(mags) <= 2, f"Halbpol-Magnete: {len(mags)}"
    m = mags[0]
    assert 45 <= m["r"] <= 65, f"r={m['r']}"
    assert 22 <= m["len"] <= 34, f"len={m['len']}"
    assert m["off"] >= 0, f"off={m['off']} (Halbpol verletzt)"
    print(f"✓ roundtrip: {len(mags)} Halbpol-Magnet(e), r={m['r']} off={m['off']} "
          f"ang={m['ang']} len={m['len']}")


def main():
    test_classify()
    test_estimate_poles()
    test_derive_geom()
    test_detect_magnets()
    test_roundtrip_canvas()
    print("\nALLE STEP-IMPORT-TESTS BESTANDEN ✅")


if __name__ == "__main__":
    main()
