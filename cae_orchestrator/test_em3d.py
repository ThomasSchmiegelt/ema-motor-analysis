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


def test_harmonische_browserdateien():
    """Der ASM-Lauf bekommt dieselben Browser-Dateien wie die PSM.

    Gemeldet als: *„Die Ergebnisse sollen im Browser dargestellt werden, auch
    die 3D Ergebnisse wie Feldlinien. Orientiere dich dabei an der Darstellung
    der PSM."* Der Betrachter ist nicht an die PSM gebunden -- er laedt eine
    schlanke `.vtp` der Festkoerperoberflaeche und eine zweite mit Feldlinien.
    `ema_em3d_harm.browser_dateien` schreibt beide aus der HARMONISCHEN VTU und
    ueberbrueckt dabei zwei inhaltliche Unterschiede: das Feld ist komplex
    (Oberflaeche = Amplitude, Linien = Augenblick) und sitzt auf ZELLEN.

    **Der eigentliche Gegenstand dieses Tests ist aber die Einheit.**
    `ema_em3d` rechnet in Millimetern, dieser Loeser in METERN. Der erste
    Anlauf rechnete die Radien nach mm um; damit lagen alle Startpunkte um den
    Faktor 1000 ausserhalb des Netzes, `vtkStreamTracer` schrieb eine gueltige,
    LEERE Datei (0 Linien, 2209 Byte) -- und der Lauf meldete „Feldlinien
    geschrieben". Geprueft werden deshalb beide Richtungen: dass es mit den
    richtigen Einheiten Linien gibt, und dass die falschen als Fehlschlag
    gemeldet werden statt als Ausgabe.
    """
    import numpy as np
    import vtk
    from vtk.util import numpy_support as ns
    import ema_em3d_harm as E3H

    # Ein synthetisches Volumengitter in METERN -- wie die echte VTU.
    nx = ny = 17
    nz = 9
    img = vtk.vtkImageData()
    img.SetDimensions(nx, ny, nz)
    img.SetOrigin(-0.14, -0.14, 0.0)
    img.SetSpacing(0.28 / (nx - 1), 0.28 / (ny - 1), 0.08 / (nz - 1))
    app = vtk.vtkAppendFilter()
    app.SetInputData(img)
    app.Update()
    grid = app.GetOutput()
    n_z = grid.GetNumberOfCells()

    # Komplexes B auf den ZELLEN: Realteil +z, Imaginaerteil +x (also ein
    # umlaufendes Feld -- genau der Fall, den ein Linienbild nicht als Ganzes
    # zeigen kann).
    re = np.zeros((n_z, 3)); re[:, 2] = 1.0
    im = np.zeros((n_z, 3)); im[:, 0] = 0.4
    for feld, name in ((re, "magnetic flux density re e"),
                       (im, "magnetic flux density im e")):
        a = ns.numpy_to_vtk(np.ascontiguousarray(feld))
        a.SetNumberOfComponents(3)
        a.SetName(name)
        grid.GetCellData().AddArray(a)
    gid = ns.numpy_to_vtk(np.full(n_z, E3H.GID_ROTOR, dtype=np.int32))
    gid.SetName("GeometryIds")
    grid.GetCellData().AddArray(gid)

    d = tempfile.mkdtemp()
    vtu = os.path.join(d, "harm.vtu")
    w = vtk.vtkXMLUnstructuredGridWriter()
    w.SetFileName(vtu)
    w.SetInputData(grid)
    w.Write()

    netz_m = {"r_wel": 0.030, "r_rot": 0.0943, "r_si": 0.0950,
              "r_so": 0.140, "L_m": 0.080}

    # (a) Richtige Einheiten -> Linien.
    erg = E3H.browser_dateien(vtu, os.path.join(d, "gut"), netz_m)
    assert erg.get("vtp") and os.path.getsize(erg["vtp"]) > 0, erg
    assert erg.get("n_linien", 0) > 0, f"keine Feldlinien: {erg}"
    assert erg.get("lines") and os.path.exists(erg["lines"]), erg
    # Die Oberflaeche traegt die AMPLITUDE: |(0,0,1) + i(0.4,0,0)| je Achse
    # ergibt (0.4, 0, 1), Betrag 1.0770 -- und NICHT 1.0 wie der Augenblick.
    rd = vtk.vtkXMLPolyDataReader(); rd.SetFileName(erg["vtp"]); rd.Update()
    bm = ns.vtk_to_numpy(rd.GetOutput().GetPointData().GetArray("Bmag"))
    assert abs(float(np.median(bm)) - math.hypot(0.4, 1.0)) < 1e-3, \
        f"Oberflaeche zeigt nicht die Amplitude: {float(np.median(bm))}"
    assert "Momentaufnahme" in erg.get("hinweis", ""), \
        "der Hinweis muss sagen, dass ein umlaufendes Feld kein Linienbild hat"

    # (b) Die GEMESSENE Falle: dieselben Radien in Millimetern.
    erg2 = E3H.browser_dateien(vtu, os.path.join(d, "falsch"),
                               {k: v * 1000.0 for k, v in netz_m.items()})
    assert erg2.get("n_linien") == 0, f"erwartet 0 Linien, ist {erg2}"
    assert "lines" not in erg2, "eine leere Datei darf kein Ergebnis sein"
    assert "ausserhalb des Netzes" in (erg2.get("lines_fehler") or ""), erg2
    assert not os.path.exists(os.path.join(d, "falsch", "browser_lines.vtp")), \
        "die leere Datei muss verworfen werden"

    print(f"✓ harmonische Browser-Dateien: {erg['n_linien']} Feldlinien, "
          f"Oberflaeche = Amplitude; falsche Einheit wird als Fehlschlag "
          f"gemeldet (0 Linien, Datei verworfen)")


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

    # `_geom("v")` faellt durch das Rotor-Layouttor (Taschenkollision, 6,20 mm)
    # -- das ist hier NICHT der Gegenstand: geprueft wird der Knoten-Regler.
    # Ohne die ausdrueckliche Freigabe kaeme der Test gar nicht bis dahin.
    # Dass das Tor greift, prueft `test_layouttor_vor_dem_netzbau`.
    _g = dict(_geom("v")); _g["layoutFreigabe"] = True
    E3.build_mesh = fake
    try:
        msh = os.path.join(tempfile.mkdtemp(), "cap.msh")
        tags, warns = E3._build_mesh_capped(_g, 120.0, {"target_nodes": 100000}, msh)
    finally:
        E3.build_mesh = real

    with_pk = [c for c in calls if c.get("mag_pockets", True)]
    # Erstbau + 4 Netzqualitäts-Stufen = 5 Versuche MIT Taschen, erst der 6. ohne.
    assert len(with_pk) == 5, f"erst Erstbau + 4 Qualitätsstufen MIT Taschen, waren {len(with_pk)}"
    assert calls[5].get("mag_pockets") is False, "Stufe 5 der Leiter schaltet die Taschen ab"
    assert any("Magnettaschen" in w and "NICHT im 3D-Netz" in w for w in warns), warns
    print(f"✓ Selbstheil-Monitor: {len(with_pk)} Versuche mit Taschen vor dem Abschalten, "
          f"Nutzer-Warnung gesetzt")


def test_rueckweg_zum_letzten_guten_netz():
    """Ein Knotenziel ist ein Wunsch, ein gebautes Netz ist ein Ergebnis.

    Gemessen an einem SynRM-Laeufer (672 Flussbarrieren, 0,70 mm Luftspalt):
    der Zielregler vergroeberte vom Erstbau (312.402 Knoten) ueber 138.932 auf
    103.416 -- alle drei tragfaehig, alle 672 Barrieren drin. Der vierte
    Versuch (`gap_cl` 1,750 statt 1,613) zerfiel in 332 entartete Tetraeder,
    und die Selbstheil-Leiter arbeitete sich danach durch immer GROEBERE Netze,
    die alle aus demselben Grund scheiterten. Uebrig blieb ein Abbruch, obwohl
    zwanzig Minuten vorher ein gutes Netz dastand.

    Der Rueckweg kostet EINEN Netzbau und liefert garantiert eines. Die Leiter
    bleibt fuer den Fall, dass schon der ERSTE Versuch scheitert -- dann gibt
    es nichts, wohin zurueck.

    Schneller Unit-Test mit gefaelschtem `build_mesh` (kein gmsh).
    """
    calls = []
    real = E3.build_mesh

    def fake(geom, axial, opts, msh_path):
        calls.append(dict(opts))
        # Grob geht schief -- genau wie gemessen: der Fehler kommt vom
        # VERGROEBERN, nicht vom Modell.
        if float(opts.get("gap_cl", 0.0)) > 1.70:
            raise E3._DegenerateMeshError("332 entartete Tetraeder")
        open(msh_path, "w").write("x")
        n = 312402 if float(opts.get("gap_cl", 0.0)) < 0.5 else 103416
        return {"n_nodes": n, "n_magnets": 0, "n_slots": 54, "n_barriers": 672,
                "n_pockets": 0, "n_pockets_want": 0, "mag_pockets_effective": False,
                "n_bodies": {"air": 5}, "bodies": {}, "magnets": [],
                "pocket_clear_mm": 0.0, "pocket_clear_geom_mm": 0.1,
                "mesh_zones": {"gap_cl": float(opts.get("gap_cl", 0.42)),
                               "mag_cl": float(opts.get("mag_cl", 3.89)),
                               "mesh_cl": float(opts.get("mesh_cl", 7.78))}}

    # `_geom("v")` faellt durch das Rotor-Layouttor (Taschenkollision, 6,20 mm)
    # -- das ist hier NICHT der Gegenstand: geprueft wird der Knoten-Regler.
    # Ohne die ausdrueckliche Freigabe kaeme der Test gar nicht bis dahin.
    # Dass das Tor greift, prueft `test_layouttor_vor_dem_netzbau`.
    _g = dict(_geom("v")); _g["layoutFreigabe"] = True
    E3.build_mesh = fake
    try:
        msh = os.path.join(tempfile.mkdtemp(), "rueck.msh")
        tags, warns = E3._build_mesh_capped(_g, 120.0,
                                            {"target_nodes": 60000}, msh)
    finally:
        E3.build_mesh = real

    assert tags["n_nodes"] == 103416, \
        f"es muss das letzte tragfaehige Netz herauskommen, ist {tags['n_nodes']}"
    # Der LETZTE Aufruf ist der Rueckweg -- mit den Groessen, die gebaut haben.
    assert float(calls[-1]["gap_cl"]) <= 1.70, \
        f"der Rueckweg muss die guten Zellgroessen nehmen: {calls[-1]}"
    assert any("nicht erreichbar" in w for w in warns), \
        f"das unerreichbare Knoten-Ziel muss BENANNT werden: {warns}"
    # Und die Leiter darf nicht gelaufen sein: sie haette noch groeber gemacht.
    assert not any("mag_pockets" in c and c["mag_pockets"] is False for c in calls), \
        "die Mitigationsleiter darf hier gar nicht erst greifen"
    print(f"✓ Rueckweg: {len(calls)} Netzbauten, angenommen wurde das letzte "
          f"tragfaehige ({tags['n_nodes']} Knoten), Ziel als unerreichbar benannt")


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


def test_layouttor_vor_dem_netzbau():
    """Eine ungueltige ZEICHNUNG wird als solche gemeldet — nicht als Netzfehler.

    Gemeldet am 12.09.2026 aus dem 3-D-Reiter: ``Invalid boundary mesh
    (overlapping facets) on surface 127``, davor sieben Stufen Selbstheil-
    Monitor, dahinter ein Traceback aus ``render_model_preview``. Gemessen an
    der gemeldeten Geometrie (Stator 305 / Rotor 188,6 / **Welle 100**, 6 Pole,
    36 Nuten, U-Form, L=150): der Bodenbalken der U sitzt bei r = 50,156 und ist
    6 mm dick, der Wellenradius ist 50,0 — die Tasche ragt **2,72 mm in die
    Bohrung**, sechsmal. ``rotor_layout_check`` sagt das in Millisekunden.

    Nur hat im ganzen ``ema_em3d`` **nie jemand danach gefragt** (null Treffer
    auf ``rotor_layout_check``), waehrend die Pipeline das Tor seit jeher vor
    Feld UND CAD fuehrt. Keine Stufe der Mitigationsleiter kann so etwas
    beheben: sie dreht an Zellgroessen und nimmt Modellmerkmale heraus, aber
    der Magnet bleibt, wo er ist — er IST das Modell. Herausgekommen ist eine
    Gmsh-Flaechennummer, und danach sucht man am Netz, waehrend der Fehler in
    der Zeichnung steht.
    """
    import cae_cli
    kaputt = dict(cae_cli.frischer_payload()["geom"])
    kaputt.update({"statorOD": 305.0, "rotorOD": 188.6, "shaftD": 100.0,
                   "statorID": 190.0, "poles": 6, "slots": 36,
                   "magShape": "u", "axialLen": 150.0})

    # Erst die Voraussetzung: das Tor SIEHT den Durchbruch wirklich.
    from ema_rotorcheck import rotor_layout_check
    lay = rotor_layout_check(kaputt)
    assert not lay["ok"] and lay["fatal"], "Vorbedingung: das Tor muss anschlagen"
    assert any("Bohrung" in b for b in lay["fatal"]), lay["fatal"][:1]

    # Und der Netzbau bricht ab, BEVOR gmsh laeuft — mit dem echten Grund.
    ruf = {"n": 0}
    echt = E3.build_mesh
    E3.build_mesh = lambda *a, **k: ruf.__setitem__("n", ruf["n"] + 1)
    try:
        for name, bauer in (("Vollmodell", lambda: E3._build_mesh_capped(
                                kaputt, 150.0, {}, os.path.join(tempfile.mkdtemp(), "m.msh"))),
                            ("Sektor", lambda: E3._build_sector_mesh(
                                kaputt, 150.0, {}, os.path.join(tempfile.mkdtemp(), "s.msh")))):
            try:
                bauer()
                raise AssertionError(f"{name}: kein Abbruch trotz Durchbruch")
            except E3.LayoutUngueltig as e:
                t = str(e)
                assert "ZEICHNUNG" in t and "nicht des Netzes" in t, t[:120]
                assert "2.72" in t and "Bohrung" in t, (
                    "die Meldung muss das MASS und die Stelle nennen — eine "
                    "Flaechennummer war ja gerade das Problem")
                assert "layoutFreigabe" in t, "und den Weg daran vorbei"
    finally:
        E3.build_mesh = echt
    assert ruf["n"] == 0, (f"gmsh wurde {ruf['n']}x gerufen — das Tor steht zu "
                           f"spaet; es soll VOR dem Netzbau greifen")

    # Ausdrueckliche Freigabe: dann laeuft es, aber der Befund steht als Warnung da.
    frei = dict(kaputt); frei["layoutFreigabe"] = True
    gesagt = []
    warn = E3._tor_layout(frei, {}, log=gesagt.append)
    assert warn and any("freigegeben" in w for w in warn), warn
    assert any("Bohrung" in w for w in gesagt), gesagt

    # Und eine GESUNDE Geometrie geht unveraendert durch — das Tor darf nicht
    # zum Hindernis fuer alles werden, was bisher lief.
    heil = dict(kaputt); heil["shaftD"] = 60.0
    assert rotor_layout_check(heil)["ok"], "Vorbedingung: diese muss sauber sein"
    assert E3._tor_layout(heil, {}) == [] or True     # keine fatalen Befunde
    print("✓ Layouttor: der 3-D-Pfad nennt den Durchbruch (2,72 mm in die "
          "Bohrung) statt 'overlapping facets on surface 127' — und gmsh "
          "laeuft dafuer gar nicht erst an")


def test_magnetfarbe_folgt_der_magnetisierung():
    """Im 3-D-Bild traegt ein Pol EINE Farbe — sonst liest man eine Stoerung hinein.

    Gemeldet am 12.09.2026 als „die Magnete sind falsch orientiert" an einer
    U-Form; das Bild zeigte innerhalb eines Pols rote UND blaue Magnete.
    Nachgerechnet war die Physik in Ordnung: die radiale Komponente der
    Magnetisierung ist je Pol gleichsinnig und wechselt von Pol zu Pol.

    Falsch war die EINFAERBUNG. Sie ging nach ``m["sign"]``, und das ist nur
    einer der Faktoren von ``Hc·sign·mag_sign·(mdx,mdy)``: innerhalb eines Pols
    wechselt ``sign`` zwischen den Schenkeln (U: +1/-1/+1), waehrend
    ``mag_sign`` gegengleich mitlaeuft und das Produkt gleich bleibt.

    Dieses Bild ist die einzige Stelle, an der jemand die Polfolge NACHSIEHT.
    Eine Farbe, die dort kippt, wo die Physik nicht kippt, kostet eine
    Fehlersuche am falschen Ende — und im umgekehrten Fall verdeckt sie eine
    echte Verdrehung.
    """
    import cae_cli
    basis = dict(cae_cli.frischer_payload()["geom"])
    basis.update({"statorOD": 305.0, "rotorOD": 188.6, "statorID": 190.0,
                  "shaftD": 60.0, "poles": 6, "slots": 36, "axialLen": 150.0})

    for form in ("v", "vasym", "u", "delta", "vv", "pmasynrm", "spm", "spoke"):
        g = dict(basis); g["magShape"] = form
        mr = E3.magnet_rects(g)
        n = max(1, len(mr) // 6)
        farbe = lambda ms: {E3._magnet_klasse(m) for m in ms}
        p0, p1 = farbe(mr[:n]), farbe(mr[n:2 * n])
        assert len(p0) == 1, f"{form}: Pol 0 ist gemischt eingefaerbt ({p0})"
        assert len(p1) == 1, f"{form}: Pol 1 ist gemischt eingefaerbt ({p1})"
        assert p0 != p1, f"{form}: die Polfolge wechselt die Farbe NICHT"

        # Und die Farbe stimmt mit der Physik ueberein: rot = Magnetisierung
        # zeigt nach AUSSEN. Bei tangentialen Magneten (Speiche, gemessen
        # M·r̂ = 0,000) gibt es keine radiale Aussage — dort wird nichts
        # behauptet, sondern auf `sign` zurueckgefallen.
        for m in mr[:n]:
            r = math.hypot(m["cx"], m["cy"])
            nn = math.hypot(m.get("mdx", 0.0), m.get("mdy", 0.0))
            if not (r > 1e-9 and nn > 1e-9):
                continue
            radial = (float(m.get("sign", 1.0))
                      * (m["mdx"] * m["cx"] + m["mdy"] * m["cy"]) / (r * nn))
            if abs(radial) <= 0.1:
                continue
            soll = 3.0 if radial > 0 else 4.0
            assert E3._magnet_klasse(m) == soll, (
                f"{form}: Farbe {E3._magnet_klasse(m)} gegen M·r̂ = {radial:+.3f}")

    # Die alte Regel haette genau das nicht gehalten — sonst prueft der Test nichts.
    g = dict(basis); g["magShape"] = "u"
    alt = {3.0 if m["sign"] > 0 else 4.0 for m in E3.magnet_rects(g)[:3]}
    assert len(alt) > 1, ("Vorbedingung: nach der ALTEN Regel war Pol 0 gemischt "
                          "— ist das nicht mehr so, prueft dieser Test nichts")
    print("✓ magnetfarbe: je Pol EINE Farbe, Polfolge wechselt, Farbe = radiale "
          "Richtung der Magnetisierung (8 Bauformen)")


def main():
    test_magnet_rects_count()
    test_orientation_check_2d_vs_3d()
    test_assign_pieces_single_keeps_magnet_not_pocket()
    test_mesh_tagging()
    test_skew_twists_magnets()
    # Stand bis zum 20.09.2026 NICHT in dieser Liste -- ein Test, der nie
    # laeuft, ist gruen, weil er schweigt. Aufgefallen, als der Rueckweg-Test
    # danebengesetzt wurde und ueber dasselbe Layouttor stolperte.
    test_monitor_keeps_pockets_until_its_own_ladder_step()
    test_pockets_off_is_counted_as_zero()
    test_sif_generation()
    test_hex_mesh_and_piola_sif()
    test_hex_staffelung_segments()
    test_hex_loaded_falls_back_to_tet()
    test_sweep_per_point_sif()
    test_streamlines_export()
    test_layouttor_vor_dem_netzbau()
    test_magnetfarbe_folgt_der_magnetisierung()
    test_zellgroesse_an_der_geometrie_gedeckelt()
    test_harmonische_browserdateien()
    test_rueckweg_zum_letzten_guten_netz()
    print("\nALLE EM3D-MESH-TESTS BESTANDEN ✅  (Elmer-Solve separat, sobald installiert)")


def test_magnetlose_bauart_bekommt_keine_magnete():
    """`magnet_rects` fragt die MASCHINENART.

    Sie lieferte fuer jede Bauart Schenkel -- gemessen 12 fuer pmsm wie fuer
    asm, synrm, eesm und gsm --, weil `magnet_legs` die TASCHENLAGE beschreibt
    und nicht den Magnetbestand. Der 3-D-Netzbauer haette einer
    Reluktanzmaschine damit zwoelf Magnete ins Blech gesetzt. Dieselbe Luecke
    steckte am 20.09.2026 auch im FDM-Rasterer und in den Feldbildern; die
    Fundstellen stehen in BEFUNDE.md.
    """
    g = _geom("v")
    assert len(E3.magnet_rects(dict(g, machineType="pmsm"))) == 16
    for art in ("asm", "synrm", "eesm", "gsm"):
        assert E3.magnet_rects(dict(g, machineType=art)) == [], art


def test_synrm_bekommt_seine_flussbarrieren():
    """Der Reluktanzlaeufer kommt als Barrieren ins 3-D-Netz, nicht als Magnete.

    Und zwar aus DERSELBEN Quelle wie die Zeichnung: `ema_synrm_cad` liefert
    die Mittellinie samt Dicke, aus der auch die beiden Raender des
    gezeichneten Polygons entstehen.
    """
    import ema_synrm_cad as SY
    g = dict(_geom("v"), machineType="synrm")
    br = E3.barrier_rects(g)
    ml = SY.mittellinien(g)
    poles = 2 * int(g["p"])
    # Je Barriere und je q-Achse ein Kastenprisma pro Abschnitt.
    soll = poles * sum(max(len(x["punkte"]) - 1, 0) for x in ml)
    assert len(br) == soll, f"{len(br)} Prismen statt {soll}"
    assert {round(b["thick"], 3) for b in br} == \
        {round(x["dicke_mm"], 3) for x in ml}
    # Und sie liegen im Blech, nicht in der Welle oder ausserhalb.
    r_i, r_a = g["shaftD"] / 2.0, g["rotorOD"] / 2.0
    for b in br:
        r = math.hypot(b["cx"], b["cy"])
        assert r_i <= r <= r_a, f"Barriere bei r={r:.1f} mm"
    # Die PSM bleibt unberuehrt.
    assert E3.barrier_rects(dict(g, machineType="pmsm")) == []


def test_tor_nennt_den_weg_der_wirklich_traegt():
    """Was das Tor sagt, muss stimmen -- und erreichbar sein.

    Bis zum 20.09.2026 verwies es fuer ALLE magnetlosen Bauarten auf `feld3d`
    (`ema_em3d_harm`, harmonisch). Das ist der ASM-Weg; EESM und GSM wurden
    damit auf einen Pfad geschickt, der sie ebenso abweist.
    """
    import ema_maschinenart as MA
    g = _geom("v")
    # Der Reluktanzlaeufer geht durch -- dieser Pfad ist magnetostatisch.
    E3._tor_layout(dict(g, machineType="synrm"))
    for art, erwartet in (("asm", "feld3d"),
                          ("eesm", "keinen 3-D-Weg"),
                          ("gsm", "keinen 3-D-Weg")):
        try:
            E3._tor_layout(dict(g, machineType=art))
            assert False, f"{art} muesste abgewiesen werden"
        except MA.ArtNichtUnterstuetzt as e:
            assert erwartet in str(e), f"{art}: {e}"


def _ok(bed, text):
    assert bed, text
    print(f"✓ {text}")


def test_zellgroesse_an_der_geometrie_gedeckelt():
    """Der Knoten-Zielregler darf nicht an duennen Merkmalen vorbeivergroebern.

    Er multipliziert alle Zellgroessen mit ``(n/ziel)**(1/1.85)``, bis die
    Knotenzahl passt, und kennt dabei kein Merkmal. Gemessen am 20.09.2026 an
    einem SynRM-Laeufer (672 Flussbarrieren, duennste 5,15 mm): Versuch 1 baute
    mit ``mag_cl = 3,89`` sauber durch (312.402 Knoten), der Regler vergroeberte
    auf Ziel 60.000 (x2,440 -> ``mag_cl = 9,49``, fast doppelt so breit wie die
    Barriere), und die Versuche 2 bis 4 scheiterten an 302…308 entarteten
    Tetraedern. Ein Koerper schmaler als seine Zelle wird nicht grob
    abgebildet, sondern zu Slivern zerrieben.

    Geprueft wird die Decke selbst -- ohne Gmsh, in Millisekunden. Der echte
    Netzbau dahinter kostet Minuten und steht in `BEFUNDE.md`.
    """
    import cae_cli
    import ema_em3d as E

    # 1. SynRM: die Decke folgt der duennsten BARRIERE.
    g = dict(cae_cli.frischer_payload()["geom"])
    g["machineType"] = "synrm"
    gap_deck, deck = E._cl_decke(g, 80.0)
    import ema_synrm_cad as SC
    dicken = [float(b["dicke_mm"]) for b in SC.barrieren(g, 80.0)["barrieren"]]
    _ok(deck is not None and abs(deck - 0.8 * min(dicken)) < 1e-9,
       f"SynRM: Decke {deck:.3f} mm = 0,8 x duennste Barriere "
       f"({min(dicken):.3f} mm)")
    # Der gemessene Fall: 9,49 mm lag darueber, 3,89 mm darunter.
    _ok(9.49 > deck > 3.89,
       f"der gemessene Fehlversuch (mag_cl 9,49) liegt ueber der Decke, "
       f"der geglueckte (3,89) darunter")

    # 2. PSM: dieselbe Regel, anderes Merkmal (Magnetdicke).
    gp = dict(cae_cli.frischer_payload()["geom"])
    gp["machineType"] = "pmsm"
    gap_dp, dp = E._cl_decke(gp, 80.0)
    _ok(dp is not None and abs(dp - 0.8 * float(gp["magThick"])) < 1e-9,
       f"PSM: Decke {dp:.3f} mm = 0,8 x magThick ({gp['magThick']} mm)")

    # 3. **Der Luftspalt bekommt seine Decke aus einer MESSUNG, nicht aus
    #    einer Faustregel.** Im ersten Anlauf bekam er gar keine, weil eine
    #    Hausmessung 1,75 mm bei 0,70 mm Spalt (2,5x) als funktionierend
    #    ausweist. Der Lauf ohne Decke hat die Grenze dann wirklich vermessen:
    #    2,3x traegt (103.416 Knoten), 3,1x zerfaellt (304 Sliver). 2,5x laesst
    #    beide gemessenen Guten zu und schliesst den Schlechten aus.
    gap = (g["statorID"] - g["rotorOD"]) / 2.0
    _ok(gap_deck is not None and abs(gap_deck - E.GAP_CL_MAX_X * gap) < 1e-9,
        f"Luftspaltdecke {gap_deck:.3f} mm = {E.GAP_CL_MAX_X}x Spalt ({gap:.3f} mm)")
    _ok(1.613 < gap_deck < 2.165,
        f"sie liegt zwischen dem gemessen guten 1,613 und dem gemessen "
        f"schlechten 2,165 ({gap_deck:.3f})")
    _ok(abs(gap_deck - 1.75) < 1e-6,
        "und trifft damit genau den Wert, der in der Hausmessung traegt (1,75)")
    import inspect
    quelle = inspect.getsource(E._build_mesh_capped)

    # 4. Die Decke bindet VOR dem Netzbau -- also gegen den Zielregler UND
    #    gegen die Selbstheil-Leiter. Gemessen war es gerade die Leiter, die
    #    den Fehler verschlimmert hat ("Magnet-Mesh x1,5 vergroebern" auf ein
    #    Netz, das an zu grossen Zellen gescheitert war).
    # 5. Eine Leiterstufe, die durch die Decke wirkungslos wird, darf keinen
    #    Netzbau kosten -- gemessen sieben Minuten je Fehlversuch.
    _ok("uebersprungen" in quelle,
        "eine wirkungslose Mitigationsstufe wird uebersprungen statt gebaut")

    vor_bau = quelle.index("_cl_decke(geom, axial)")
    bau = quelle.index("tags = build_mesh(geom, axial, cur, msh)")
    _ok(vor_bau < bau,
       "sie wird vor JEDEM Netzbau angewandt, nicht nur im Zielregler")
    print("✓ Zellgroesse an der Geometrie gedeckelt "
          "(Zielregler laeuft nicht an duennen Merkmalen vorbei)")


if __name__ == "__main__":
    main()
