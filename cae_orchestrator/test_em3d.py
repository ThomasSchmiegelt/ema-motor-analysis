"""Tests für ema_em3d — Mesh-Erzeugung + Tagging (braucht gmsh, NICHT Elmer).

Prüft, dass das 3D-Mesh die Bauteile korrekt als Physical-Volumes taggt
(shaft/rotor/stator/air + Magnete), die Magnetzahl zur Topologie passt, der
Skew die Magnete über die Länge verdreht und die .sif sauber generiert.

Lauf: ``python test_em3d.py``.
"""

import math
import os
import tempfile

import ema_em3d as E3

_GEOM = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "p": 4,
         "slots": 48, "slotDepth": 25, "magThick": 6, "magWidth": 40, "magAngle": 130,
         "magDepthRel": 0.5, "magDist": 3, "poleArcFrac": 0.83, "magOrient": "transverse",
         "magnet": "ndfeb_n42"}


def _geom(shape):
    g = dict(_GEOM); g["magShape"] = shape; return g


def test_magnet_rects_count():
    # bar/spoke: 1 Magnet je Pol = 8; V: 2 Arme je Pol = 16.
    assert len(E3.magnet_rects(_geom("bar"))) == 8
    assert len(E3.magnet_rects(_geom("v"))) == 16
    # Magnetisierungs-Vektor ist ein Einheitsvektor, Vorzeichen alterniert über die Pole.
    rects = E3.magnet_rects(_geom("bar"))
    for m in rects:
        assert abs(math.hypot(m["mdx"], m["mdy"]) - 1.0) < 1e-6
    assert {m["sign"] for m in rects} == {1.0, -1.0}
    print("✓ magnet_rects: bar=8, v=16, Einheits-M, alternierende Polung")


def test_mesh_tagging():
    msh = os.path.join(tempfile.mkdtemp(), "m.msh")
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 0, "mesh_cl": 13.0, "gap_cl": 1.6}, msh)
    assert os.path.exists(msh) and os.path.getsize(msh) > 100000
    for name in ("shaft", "rotor", "stator", "air"):
        assert name in tags["bodies"], f"Körper {name} fehlt"
    assert tags["n_magnets"] == 16, f"Magnete {tags['n_magnets']} ≠ 16"
    assert tags["n_nodes"] > 5000
    assert "boundary" in tags
    print(f"✓ mesh_tagging: Körper {list(tags['bodies'])}, {tags['n_magnets']} Magnete, "
          f"{tags['n_nodes']} Knoten")


def test_skew_twists_magnets():
    # Skew über die Länge. MIT Magnettaschen (Standard) wird der kontinuierliche Skew netzbarkeits-
    # halber als feine STAFFELUNG um die Wellenachse umgesetzt (ein um den eigenen Schwerpunkt
    # tordiertes Magnet+Tasche-Paar ist nicht robust netzbar) → jeder der 16 Magnete wird in K
    # Segmente geschnitten; die K gestuften obround-Taschen werden PER MAGNET zu EINEM Luftkanal
    # gefuset (keine Eisen-Slivers) → der ECHTE Geometrie-Tab-Klebespalt (magGapMm) bleibt erhalten,
    # NICHT mehr angehoben. Wir prüfen: Mesh baubar, Segmentzahl = Vielfaches von 16, Taschen aktiv,
    # Spalt = Geometrie-Spalt.
    g = _geom("v"); g["magGapMm"] = 0.2
    msh = os.path.join(tempfile.mkdtemp(), "s.msh")
    tags = E3.build_mesh(g, 120.0, {"skew_deg": 12, "mesh_cl": 13.0, "gap_cl": 1.6}, msh)
    assert tags["n_magnets"] % 16 == 0 and tags["n_magnets"] >= 16, tags["n_magnets"]
    assert tags["skew_segments"] >= 2, "Skew als Staffelung umgesetzt"
    assert not tags.get("caps_dropped"), "Magnettaschen sollten netzbar sein"
    assert not tags.get("pocket_clear_raised"), "Spalt NICHT mehr anheben (gefuste Kanäle)"
    assert abs(tags["pocket_clear_mm"] - 0.2) < 1e-6, tags["pocket_clear_mm"]
    # Die Taschen müssen GEZÄHLT im Netz ankommen, nicht nur angefordert sein: `mag_pockets`
    # sagte bisher nur, dass sie gebaut werden SOLLTEN. Im Betrieb lief ein Lauf mit
    # „pockets=True" im Log und 0 Taschen im Netz.
    assert tags["n_pockets"] > 0, "Taschen angefordert, aber keine im Netz gelandet"
    assert tags["n_pockets_want"] > 0 and tags["mag_pockets_effective"]
    assert os.path.exists(msh)
    print(f"✓ skew=12°→Staffelung: {tags['skew_segments']} Segmente, "
          f"{tags['n_magnets']} Magnetstücke, ECHTER Spalt {tags['pocket_clear_mm']}mm "
          f"(geom {tags['pocket_clear_geom_mm']}mm), Taschen gefuset")


def test_sif_generation():
    msh = os.path.join(tempfile.mkdtemp(), "m.msh")
    work = os.path.dirname(msh)
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 0, "mesh_cl": 14.0, "gap_cl": 1.8}, msh)
    sif = E3.write_sif(_geom("v"), {}, tags, work, "mesh")
    txt = open(sif).read()
    assert "WhitneyAVSolver" in txt
    assert "MagnetoDynamicsCalcFields" in txt
    assert txt.count("Magnetization 1 =") == tags["n_magnets"]
    assert "Boundary Condition 1" in txt
    assert "Relative Permeability = 500" in txt
    print(f"✓ sif: WhitneyAVSolver + CalcFields + {tags['n_magnets']} Magnetisierungen + BC")


def test_hex_mesh_and_piola_sif():
    # Opt-in-Hexaeder-Netz (strukturiert, 2D-Querschnitt + axiale Extrusion): das Netz muss
    # überwiegend aus Hexaedern/Prismen (nicht Tetraedern) bestehen, die Magnete korrekt
    # taggen, und die .sif MUSS die Piola-Transformation setzen + Tree-Gauge/Direkt-Löser
    # weglassen (Elmer verträgt beides nicht mit Piola). Gerader Fall.
    msh = os.path.join(tempfile.mkdtemp(), "hx.msh")
    work = os.path.dirname(msh)
    g = _geom("v")
    tags = E3.build_mesh(g, 120.0, {"hex_mesh": True, "mesh_cl": 10.0, "gap_cl": 1.6}, msh)
    assert tags.get("mesh_kind") == "hex", "kein Hex-Netz gebaut"
    hc = tags.get("hex_counts", {})
    assert hc.get("hex", 0) + hc.get("prism", 0) > 5 * hc.get("tet", 0), f"zu viele Tets: {hc}"
    assert tags["n_magnets"] == 16, f"Magnete {tags['n_magnets']} ≠ 16"
    for name in ("shaft", "rotor", "stator", "air"):
        assert name in tags["bodies"], f"Körper {name} fehlt"
    # Magnet-Langloch-Taschen (Klebespalt) sind auch im Hex-Netz drin (Standard an).
    assert tags.get("pocket_clear_mm", 0) > 0, "Magnet-Luft-Taschen fehlen im Hex-Netz"
    sif = E3.write_sif(g, {"hex_mesh": True}, tags, work, "mesh")
    txt = open(sif).read()
    assert "Use Piola Transform = Logical True" in txt, "Piola-Transform fehlt im Hex-.sif"
    assert "Use Tree Gauge" not in txt, "Tree-Gauge darf mit Piola NICHT gesetzt sein"
    assert "Linear System Solver = Iterative" in txt, "Hex/Piola braucht den iterativen Löser"
    assert txt.count("Magnetization 1 =") == tags["n_magnets"]
    print(f"✓ hex: {hc.get('hex',0)} Hexaeder + {hc.get('prism',0)} Prismen, "
          f"{tags['n_magnets']} Magnete, Piola-.sif iterativ")


def test_hex_staffelung_segments():
    # Hexaeder + Staffelung: der gemeinsame 2D-Querschnitt wird mit ALLEN K Rotationen der
    # Magnete geschnitten und in K konformen Slabs extrudiert → die Magnetstücke sind ein
    # Vielfaches der Basis-Magnete (je Segment eigene, gedrehte Magnetisierung).
    msh = os.path.join(tempfile.mkdtemp(), "hxs.msh")
    g = _geom("v")
    tags = E3.build_mesh(g, 120.0, {"hex_mesh": True, "mesh_cl": 10.0,
                                    "skew_segments": 3, "skew_step_deg": 5.0}, msh)
    assert tags.get("mesh_kind") == "hex"
    assert tags["skew_segments"] == 3
    assert tags["n_magnets"] == 16 * 3, f"erwartet 48 Magnetstücke, ist {tags['n_magnets']}"
    print(f"✓ hex-staffelung: {tags['skew_segments']} Segmente, {tags['n_magnets']} Magnetstücke")


def test_hex_loaded_falls_back_to_tet():
    # Der Hex-Pfad (v1) kann kein eingeprägtes Lastfeld (Stirnring-Leiter) → bei aktivem
    # Lastfeld MUSS build_mesh automatisch auf das Tetraeder-Netz zurückfallen.
    msh = os.path.join(tempfile.mkdtemp(), "hxl.msh")
    g = _geom("v")
    tags = E3.build_mesh(g, 120.0, {"hex_mesh": True, "mesh_cl": 13.0,
                                    "excitation": "loaded", "coil_currents": True,
                                    "rpm": 3000, "load_nm": 80}, msh)
    assert tags.get("mesh_kind") != "hex", "Lastfeld hätte auf Tet zurückfallen müssen"
    assert tags.get("hex_fallback") == "loaded_field_needs_tet"
    print("✓ hex-fallback: Lastfeld → Tetraeder-Netz (wie erwartet)")


def test_sweep_per_point_sif():
    # Sweep-Kern (run_em3d_sweep): das Mesh wird EINMAL gebaut, dann je Betriebspunkt nur
    # write_sif neu — verschiedene rpm/Last ⇒ verschiedene dq-Ströme/operating_point auf
    # DEMSELBEN Mesh. Genau das macht der Drehzahlband-Lauf (ohne Elmer prüfbar).
    msh = os.path.join(tempfile.mkdtemp(), "m.msh")
    work = os.path.dirname(msh)
    tags = E3.build_mesh(_geom("v"), 120.0, {"skew_deg": 0, "mesh_cl": 14.0, "gap_cl": 1.8}, msh)
    n_nodes0 = tags["n_nodes"]
    ops = []
    for rpm, load in ((1000, 150), (15000, 40)):
        E3.write_sif(_geom("v"), {"rpm": rpm, "load_nm": load, "excitation": "loaded"},
                     tags, work, "mesh")
        ops.append(dict(tags["operating_point"]))
    # Mesh unverändert (kein Neuaufbau pro Punkt).
    assert tags["n_nodes"] == n_nodes0
    assert ops[0]["load_nm"] == 150 and ops[1]["load_nm"] == 40
    assert ops[0]["rpm"] == 1000 and ops[1]["rpm"] == 15000
    # Verschiedene Betriebspunkte ⇒ verschiedene Statorströme.
    assert (ops[0]["iq_A"], ops[0]["id_A"]) != (ops[1]["iq_A"], ops[1]["id_A"])
    print(f"✓ sweep: 1 Mesh ({n_nodes0} Knoten), 2 Punkte → "
          f"i_q {ops[0]['iq_A']}→{ops[1]['iq_A']} A, i_d {ops[0]['id_A']}→{ops[1]['id_A']} A")


def test_streamlines_export():
    # Feldlinien-Export für den Browser-Viewer: aus einem (synthetischen) Volumengitter mit
    # B-Vektorfeld eine schlanke Polylinien-.vtp tracen — OHNE Elmer. Prüft, dass Linien
    # entstehen, nur ``Bmag`` als Skalar übrig bleibt und das vtk.js-lesbare Format
    # (UInt32-Header, float32-Punkte) geschrieben wird.
    import numpy as np
    import vtk
    from vtk.util import numpy_support as ns

    nx = ny = 21; nz = 13
    img = vtk.vtkImageData()
    img.SetDimensions(nx, ny, nz)
    img.SetOrigin(-100.0, -100.0, 0.0)
    img.SetSpacing(200.0 / (nx - 1), 200.0 / (ny - 1), 120.0 / (nz - 1))
    B = np.zeros((nx * ny * nz, 3), dtype=float); B[:, 2] = 1.0   # homogenes +z-Feld
    arr = ns.numpy_to_vtk(B); arr.SetName("B")
    img.GetPointData().AddArray(arr)

    tags = {"dims": {"r_so": 90.0, "r_shaft": 20.0}, "L": 120.0}
    out = os.path.join(tempfile.mkdtemp(), "lines.vtp")
    E3.export_browser_streamlines(img, "B", tags, out)

    assert os.path.exists(out) and os.path.getsize(out) > 0
    head = open(out, "rb").read(400).decode("latin-1")
    assert 'header_type="UInt32"' in head, "vtk.js braucht UInt32-Header"
    assert 'type="Float32"' in head, "Punkte müssen float32 sein"

    rd = vtk.vtkXMLPolyDataReader(); rd.SetFileName(out); rd.Update()
    poly = rd.GetOutput()
    assert poly.GetNumberOfLines() > 0, "keine Feldlinien getraced"
    pdp = poly.GetPointData()
    names = {pdp.GetArrayName(i) for i in range(pdp.GetNumberOfArrays())}
    assert names == {"Bmag"}, f"nur Bmag erwartet, ist {names}"
    print(f"✓ streamlines: {poly.GetNumberOfLines()} Feldlinien, nur Bmag, UInt32/float32")


def test_assign_pieces_single_keeps_magnet_not_pocket():
    """PMa-SynRM-Regression: Magnet-Prisma und seine obround-Luft-Tasche haben denselben
    Schwerpunkt; bei KURZEN Magneten (5×3 mm Außenlage) passiert die Taschen-Schale das
    Massengate. single=True muss das EINE massen-nächste Volumen (den echten Magneten)
    behalten und die Schale freigeben (→ wird danach als Luft-Kappe getaggt)."""
    import ema_em3d as E
    L = 40.0
    piece = {"cx": 30.7, "cy": 4.0, "z0": 0.0, "z1": L, "length": 5.0, "thick": 3.0}
    pred = 5.0 * 3.0 * L                                   # 600 mm³
    ring_mass = 361.0                                      # obround − Magnet (~0.6·pred → im Gate!)
    avail = [(101, 30.7, 4.0, L / 2, ring_mass),           # Taschen-Schale (gleicher COM)
             (102, 30.7, 4.0, L / 2, pred)]                # echter Magnet
    # Alte Logik (single=False): BEIDE landen im Magnet → die Luft-Schale wird magnetisiert
    a0, _t0 = E._assign_pieces([piece], avail)
    assert len(a0[0]) == 2, "Doku des alten Fehlers: beide Volumina passieren das Gate"
    # Fix: single=True behält nur den massen-nächsten Kandidaten (den echten Magneten)
    a1, t1 = E._assign_pieces([piece], avail, single=True)
    assert a1[0] == [102], f"erwartet [102] (echter Magnet), ist {a1[0]}"
    assert t1 == {102}, "die Schale muss frei bleiben (für die Kappen-Zuordnung als Luft)"
    print("✓ _assign_pieces(single=True): kurzer Magnet behalten, Taschen-Schale freigegeben")


def test_monitor_keeps_pockets_until_its_own_ladder_step():
    """Der Selbstheil-Monitor darf die Magnettaschen NICHT vor seiner eigenen Leiterstufe
    aufgeben. Genau das passierte im Betrieb: `build_mesh` fing jeden Fehler ab und baute
    sofort ohne Taschen neu, während `mesh_build.log` weiter `pockets=True` meldete.

    Schneller Unit-Test mit gefälschtem `build_mesh` (kein gmsh, Millisekunden): Bau
    gelingt nur OHNE Taschen. Erwartet: die Leiter probiert erst alle Netzqualitäts-Stufen
    MIT Taschen, schaltet sie erst auf ihrer Stufe ab, und die Warnung sagt es dem Nutzer.
    """
    calls = []
    real = E3.build_mesh

    def fake(geom, axial, opts, msh_path):
        calls.append(dict(opts))
        assert opts.get("pocket_fallback") is False, \
            "Monitor muss den stillen Sofort-Fallback abschalten"
        if opts.get("mag_pockets", True):
            raise RuntimeError("Invalid boundary mesh (overlapping facets) on surface 1")
        open(msh_path, "w").write("x")
        return {"n_nodes": 100000, "n_magnets": 16, "n_slots": 48, "n_barriers": 0,
                "n_pockets": 0, "n_pockets_want": 0, "mag_pockets_effective": False,
                "n_bodies": {"air": 4}, "bodies": {}, "magnets": [],
                "pocket_clear_mm": 0.0, "pocket_clear_geom_mm": 0.1,
                "mesh_zones": {"gap_cl": 1.0, "mag_cl": 4.0, "mesh_cl": 10.0}}

    E3.build_mesh = fake
    try:
        msh = os.path.join(tempfile.mkdtemp(), "cap.msh")
        tags, warns = E3._build_mesh_capped(_geom("v"), 120.0, {"target_nodes": 100000}, msh)
    finally:
        E3.build_mesh = real

    with_pk = [c for c in calls if c.get("mag_pockets", True)]
    # Erstbau + 4 Netzqualitäts-Stufen = 5 Versuche MIT Taschen, erst der 6. ohne.
    assert len(with_pk) == 5, f"erst Erstbau + 4 Qualitätsstufen MIT Taschen, waren {len(with_pk)}"
    assert calls[5].get("mag_pockets") is False, "Stufe 5 der Leiter schaltet die Taschen ab"
    assert any("Magnettaschen" in w and "NICHT im 3D-Netz" in w for w in warns), warns
    print(f"✓ Selbstheil-Monitor: {len(with_pk)} Versuche mit Taschen vor dem Abschalten, "
          f"Nutzer-Warnung gesetzt")


def test_pockets_off_is_counted_as_zero():
    """Taschen aus ⇒ n_pockets == 0. Zusammen mit dem Gegenstück in
    ``test_skew_twists_magnets`` heißt das: der Zähler unterscheidet die beiden Fälle
    wirklich und ist nicht bloß ein durchgereichtes Flag."""
    msh = os.path.join(tempfile.mkdtemp(), "np.msh")
    tags = E3.build_mesh(_geom("v"), 120.0,
                         {"skew_deg": 0, "mesh_cl": 13.0, "gap_cl": 1.6,
                          "mag_pockets": False}, msh)
    assert tags["n_pockets"] == 0 and not tags["mag_pockets_effective"]
    assert tags["n_magnets"] == 16
    print("✓ mag_pockets=False ⇒ n_pockets=0 (Zähler misst den IST-Stand)")


def test_orientation_check_2d_vs_3d():
    """``_orientation_check`` misst die Verdrehung der Polfolge zwischen 2D-FDM und
    3D-Elmer. Reine Zahlenprüfung (kein Netz, kein Elmer): synthetische Br(θ) mit
    BEKANNTEM Versatz hinein, gemessener Versatz heraus."""
    import numpy as np
    g = {"p": 3}
    th = np.linspace(0, 2 * np.pi, 720, endpoint=False)
    br2 = np.cos(3 * th)

    # (a) identisch ⇒ 0° Versatz, in Ordnung
    res = {"warnings": []}
    out = E3._orientation_check(th, br2, th, br2.copy(), g, {}, res)
    assert abs(out["phase_shift_mech_deg"]) < 1e-6, out
    assert out["orientation_ok"] and not res["warnings"]

    # (b) 4° mechanisch verdreht, Staffelung 3×3° ⇒ Toleranz 6+3 = 9° ⇒ in Ordnung
    sh = math.radians(4.0)
    res = {"warnings": []}
    out = E3._orientation_check(th, br2, th, np.cos(3 * (th - sh)), g,
                                {"skew_segments": 3, "skew_step_deg": 3.0}, res)
    assert abs(out["phase_shift_mech_deg"] - 4.0) < 0.05, out
    assert out["orientation_ok"] and len(res["warnings"]) == 1   # erklärender Hinweis

    # (c) 20° mechanisch verdreht, keine Staffelung ⇒ Toleranz 3° ⇒ Warnung
    sh = math.radians(20.0)
    res = {"warnings": []}
    out = E3._orientation_check(th, br2, th, np.cos(3 * (th - sh)), g, {}, res)
    assert abs(out["phase_shift_mech_deg"] - 20.0) < 0.05, out
    assert not out["orientation_ok"] and "verdreht" in res["warnings"][0]
    print("✓ _orientation_check: 0°/4°(tol 9°)/20°(tol 3°) korrekt bewertet")


def main():
    test_magnet_rects_count()
    test_orientation_check_2d_vs_3d()
    test_assign_pieces_single_keeps_magnet_not_pocket()
    test_mesh_tagging()
    test_skew_twists_magnets()
    test_pockets_off_is_counted_as_zero()
    test_sif_generation()
    test_hex_mesh_and_piola_sif()
    test_hex_staffelung_segments()
    test_hex_loaded_falls_back_to_tet()
    test_sweep_per_point_sif()
    test_streamlines_export()
    print("\nALLE EM3D-MESH-TESTS BESTANDEN ✅  (Elmer-Solve separat, sobald installiert)")


if __name__ == "__main__":
    main()
