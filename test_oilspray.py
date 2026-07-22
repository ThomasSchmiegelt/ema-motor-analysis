"""Tests für die experimentelle Spritzöl-Kühlung (Blender/Mantaflow) — OHNE Blender/FreeCAD.

Prüft die reinen-Python-Bausteine: den FreeCAD-STL-Skript-Generator (Wickelkopf-Ausschnitt,
nur Hairpins/Wickelköpfe, Slot-Limit), den generierten Blender-Setup-String (enthält die
nötigen Mantaflow-/Marker-Aufrufe), die Marker-Parser des Runners, das Clamping und die
Kennwert-Charts aus synthetischen Metriken.

Lauf: ``python test_oilspray.py`` (Blender/FreeCAD werden NICHT benötigt).
"""

import os
import tempfile

import ema_freecad
import ema_oilspray as OIL
import blender_runner
import freecad_runner

_GEOM = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
         "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3, "magShape": "v",
         "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6, "magDist": 2,
         "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
         "conductorsPerSlot": 4, "coilPitch": 0, "windingHeadFlare": 6,
         "windingHeadStyle": "sweep", "shaftConnection": "press"}


def test_stl_script_wedge_section():
    """include_core=True: Keilausschnitt MIT Welle/Rotor/Magnete/Stator + Wickelköpfe, per
    Sektor geschnitten; include_core=False: nur die Wickelköpfe. Slot-Limit + MeshPart-Export.
    Je-Bauteil-STL (STL_PARTS-Marker) statt EINER gemergten Datei."""
    stl_dir = "/tmp/wh_stl"
    core = ema_freecad.build_winding_head_stl_script(_GEOM, 120.0, "/tmp/wh.FCStd", stl_dir,
                                                     section_slots=3, include_core=True)
    assert "GEN_SHAFT = True" in core and "GEN_ROTOR = True" in core
    assert "GEN_STATOR = True" in core and "GEN_MAGNETS = True" in core
    assert "GEN_HAIRPIN = True" in core and "GEN_WHEAD = True" in core
    assert "WH_SLOT_LIMIT = 3" in core                       # nur Ausschnitts-Nuten
    assert "makeCylinder" in core and "common" in core       # Sektor-Cutaway
    assert "WIND_DEBUG = True" in core                        # Winkel aus Pins
    assert "MeshPart" in core and "LinearDeflection" in core
    assert "STL_PARTS:" in core and stl_dir in core
    assert '_kept_by_key.setdefault(_cp, []).append' in core  # je Bauteil eine eigene Compound

    wonly = ema_freecad.build_winding_head_stl_script(_GEOM, 120.0, "/tmp/wh.FCStd", stl_dir,
                                                      section_slots=3, include_core=False)
    assert "GEN_SHAFT = False" in wonly and "GEN_STATOR = False" in wonly
    assert "GEN_HAIRPIN = True" in wonly
    print("✓ STL-Skript: Keil-Cutaway mit Kern (core=True) bzw. nur Wickelköpfe (core=False), je-Bauteil-STL")


def test_stl_export_survives_degenerate_shape():
    """Automatismus gegen entartete BSpline-Flaechen ("Spline curve: Knots interval values too
    close" -- eine seltene degenerierte Wickelkopf-Krone/-Lasche): frueher liess EIN kaputtes
    Teil-Shape (z. B. ein Pin_XXX-Kompound) den GESAMTEN je-Bauteil-STL-Export scheitern (eine
    Exception irgendwo im Schreib-Loop brach direkt zum aeusseren STL_FAIL durch). Jetzt: Kompound-
    Mesh -> exportStl-Fallback -> Teil-Shapes EINZELN vernetzen (nur die defekten ueberspringen)
    -> nur bei komplett kaputtem Bauteil dieses eine Bauteil ueberspringen, alle anderen Bauteile
    bleiben unangetastet (kein Abbruch der ganzen Schleife)."""
    core = ema_freecad.build_winding_head_stl_script(_GEOM, 120.0, "/tmp/wh.FCStd", "/tmp/wh_stl",
                                                      section_slots=3, include_core=True)
    # Der ganze Bauteil-Loop steht jetzt unter einem eigenen try/except (weiter zum naechsten Key).
    assert "for _key, _shapes in _kept_by_key.items():\n        try:" in core
    assert "except Exception as _ke:" in core and "Bauteil %s uebersprungen" in core
    # exportStl-Fallback ist selbst abgesichert + fuehrt zur Teil-Shape-Einzelpruefung.
    assert "except Exception as _ee:" in core
    assert "Teil-Shapes einzeln pruefen" in core
    assert "for _si, _sh in enumerate(_shapes):" in core
    assert "kein Teil-Shape vernetzbar" in core
    print("✓ STL-Export: entartete Einzel-Shapes (Spline-Fehler) reissen nicht mehr den ganzen Export mit")


def test_stl_script_hidden_pins_and_winding_full():
    """hidden_pins blendet einzelne Hairpins aus dem Wickelkopf-Kompound aus; winding_full baut
    den Wickelkopf (wie die anderen Bauteile) als vollen 360°-Ring (alle Nuten, kein Ausschnitt-
    Trimmen mehr)."""
    stl_dir = "/tmp/wh_stl"
    hp = ema_freecad.build_winding_head_stl_script(_GEOM, 120.0, "/tmp/wh.FCStd", stl_dir,
                                                   section_slots=3, hidden_pins=[0, 2, 5])
    assert "_HIDDEN_PINS = set([0, 2, 5])" in hp
    assert "_pi in _HIDDEN_PINS" in hp

    full = ema_freecad.build_winding_head_stl_script(_GEOM, 120.0, "/tmp/wh.FCStd", stl_dir,
                                                     section_slots=3, winding_full=True)
    assert "WH_SLOT_LIMIT = 54" in full, "winding_full muss alle Nuten bauen (nicht section_slots)"
    print("✓ hidden_pins blendet Pins aus + winding_full baut alle Nuten")


def test_slot_limit_in_full_script():
    """hairpin_slot_limit begrenzt die Nuten-Schleife; 0 (Default) = volle Nutenzahl."""
    full = ema_freecad.build_full_motor_script(_GEOM, 120.0, "/tmp/m.FCStd")
    assert "WH_SLOT_LIMIT = 54" in full, "Default: alle Nuten"
    lim = ema_freecad.build_full_motor_script(_GEOM, 120.0, "/tmp/m.FCStd",
                                              hairpin_slot_limit=2)
    assert "WH_SLOT_LIMIT = 2" in lim
    assert "for s in range(min(n_slots, WH_SLOT_LIMIT))" in lim
    print("✓ Slot-Limit: Default 54, gesetzt 2, Schleife begrenzt")


def test_blender_script_markers():
    """Der Blender-Setup-String enthält die Mantaflow-/Marker-Aufrufe, die der Runner/das
    Ergebnis braucht (Domain LIQUID, Inflow, Bake, Secondary-Particles, OIL_*-Marker)."""
    s = OIL._blender_script()
    for tok in ("fluid.bake_all", "DOMAIN", "domain_type", "LIQUID", "FLOW",
                "INFLOW", "EFFECTOR", "use_spray_particles", "surface_tension",
                "KDTree", "OIL_METRICS:", "OIL_FRAMES:", "OIL_DONE", "OIL_STAGE:"):
        assert tok in s, f"Blender-Skript ohne {tok!r}"
    # EEVEE-Umbenennung (4.2) robust aufgelöst
    assert "BLENDER_EEVEE_NEXT" in s and "_pick_engine" in s
    print("✓ Blender-Skript: Domain/Inflow/Effector/Bake/Particles + OIL_*-Marker + Engine-Auflösung")


def test_orientation_closeup_branches():
    """Einbaulage (horizontal/vertikal) + Nahaufnahme sind im Blender-Skript verzweigt und
    die Schwerkraft folgt der Lage."""
    s = OIL._blender_script()
    for tok in ("ORIENTATION", "HORIZONTAL", "CLOSEUP",
                "scene.gravity = (0.0, -9.81, 0.0) if HORIZONTAL else (0.0, 0.0, -9.81)"):
        assert tok in s, f"Blender-Skript ohne {tok!r}"
    print("✓ Einbaulage/Nahaufnahme: HORIZONTAL/CLOSEUP-Zweige + lageabhängige Schwerkraft")


def test_jet_focus_and_thin_oil():
    """Dünnflüssiges, spritzfähiges Öl: (1) Viskositätslöser nur bei zähem Öl, (2) sichtbarer
    Düsenstutzen am Ring, aus dem das Öl austritt, (3) dünnflüssige Defaults."""
    s = OIL._blender_script()
    # (1) Viskositätslöser gated (dünnes Öl spritzt statt zu verklumpen)
    assert "if VISC > 0.02:" in s and 'use_viscosity", False' in s, "Viskositätslöser nicht gated"
    # (2) sichtbarer Düsenstutzen, aus dem das Öl austritt
    assert "stub_len" in s and "primitive_cylinder_add" in s, "kein sichtbarer Düsenstutzen"
    # (3) dünnflüssige Defaults in run_oilspray
    src = open(os.path.join(os.path.dirname(__file__), "ema_oilspray.py")).read()
    assert '"viscosity", 0.004' in src and '"surface_tension", 0.01' in src, "Defaults nicht dünn"
    print("✓ Dünnes Öl: gated Viskosität + sichtbarer Düsenstutzen + dünnflüssige Defaults")


def test_nozzle_aligned_to_hairpin():
    """Die Düsenöffnung wird auf einen ECHTEN Kronen-(Kupfer-)Punkt abgestimmt: das Skript
    baut die _crown_target-Zuordnung, der Strahl zielt auf diesen Punkt (tgt), und Düse UND
    Nahaufnahme-Kamera teilen sich denselben Auftreffpunkt (close_tgt)."""
    s = OIL._blender_script()
    assert "_crown_target" in s and "_ovinfo" in s, "keine Krone-zu-Düse-Zuordnung"
    # Strahl zielt radial durch den realen Kronenpunkt (0.6·tgt), NICHT mehr blind auf die Achse
    assert "0.6 * tgt.x - px" in s and "(0.0 - px)" not in s, "Strahl nicht auf echten Leiter gerichtet"
    # Zielhöhe knapp UNTER der Kronenspitze (Flanke) — an der Spitze fliegt der halbe Kegel drüber
    assert "z_hit = ring_z - 1.2 * tube_r" in s, "Strahl zielt nicht in die Kronen-Flanke"
    # Düse (1 Düse) und Kamera nutzen denselben gewählten Leiter
    assert "th, tgt = close_th, close_tgt" in s, "Düse nicht auf gewählten Leiter gesetzt"
    assert "cam_tgt = close_tgt.copy()" in s, "Kamera nicht auf den Auftreffpunkt gerichtet"
    print("✓ Düse auf echten Hairpin abgestimmt: _crown_target (Flanke), Strahl→tgt, Kamera=Auftreffpunkt")


def test_slowmo_time_scale():
    """Zeitlupe: der oil.slowmo-Faktor wird als Mantaflow time_scale=1/slowmo verdrahtet."""
    s = OIL._blender_script()
    assert 'CFG.get("time_scale", 1.0)' in s and '"time_scale", TIME_SCALE' in s, \
        "time_scale nicht im Blender-Skript gesetzt"
    src = open(os.path.join(os.path.dirname(__file__), "ema_oilspray.py")).read()
    assert '"time_scale": 1.0 / slowmo' in src, "slowmo nicht in die cfg übersetzt"
    assert '"slowmo", 1.0' in src, "slowmo-Default fehlt in run_oilspray"
    print("✓ Zeitlupe: oil.slowmo → cfg time_scale=1/slowmo → Domain time_scale")


def test_persist_creates_and_load_saved_roundtrip():
    """Speicherfunktion: _persist legt results.json AN (Lauf ohne vorherige Analyse) und
    load_saved liefert den Lauf mit base64-Bildern + korrektem video-Flag zurück."""
    import json
    d = tempfile.mkdtemp()
    charts = os.path.join(d, "charts"); os.makedirs(charts)
    # Mini-PNG-Datei als „Chart"
    with open(os.path.join(charts, "oil_wetting.png"), "wb") as f:
        f.write(b"\x89PNG_fake")
    result = {"source": "blender_mantaflow", "config": {"resolution": 72, "slowmo": 10},
              "metrics": {"wetted_pct_peak": 5.0}, "series": [],
              "images": {"oil_wetting": "AAAA"}, "video": True, "note": "qual"}
    OIL._persist(d, result)                      # KEINE results.json vorhanden → wird angelegt
    assert os.path.exists(os.path.join(d, "results.json")), "_persist legt results.json nicht an"
    back = OIL.load_saved(d)
    assert back and back["config"]["slowmo"] == 10
    assert "oil_wetting" in back["images"], "Chart-Datei nicht als base64 zurückgeladen"
    assert back["video"] is False, "video-Flag muss der Datei-Existenz folgen (keine anim.mp4)"
    os.makedirs(os.path.join(d, OIL.FRAMES_SUBDIR))
    with open(os.path.join(d, OIL.FRAMES_SUBDIR, "anim.mp4"), "wb") as f:
        f.write(b"mp4")
    assert OIL.load_saved(d)["video"] is True
    assert OIL.load_saved(tempfile.mkdtemp()) is None, "leeres Projekt muss None geben"
    print("✓ Speicherfunktion: _persist legt results.json an, load_saved Roundtrip + video-Flag")


def test_component_lists_and_view_mode():
    """Anzeigen-/Schneiden-Häkchenlisten + Gesamt/Ausschnitt steuern gen-Flags und die
    Schnitt-Logik im STL-Skript (common = Keil behalten, cut = Cutaway herausschneiden)."""
    stl = "/tmp/wh.stl"
    # Nur Wickelkopf + Stator anzeigen; Stator NICHT schneiden → voller Ring als Kontext.
    s = ema_freecad.build_winding_head_stl_script(
        _GEOM, 120.0, "/tmp/wh.FCStd", stl, section_slots=3,
        components={"shaft": False, "rotor": False, "stator": True,
                    "magnets": False, "winding": True},
        cut={"stator": False, "winding": True}, view_mode="section")
    assert "GEN_SHAFT = False" in s and "GEN_ROTOR = False" in s
    assert "GEN_STATOR = True" in s and "GEN_MAGNETS = False" in s
    assert "GEN_HAIRPIN = True" in s and "GEN_WHEAD = True" in s
    assert "_VIEW   = 'section'" in s
    assert "'winding'" in s and "'stator'" not in s.split("_CUTSET")[1].split("]")[0], \
        "Stator sollte NICHT in der Schnittmenge sein"
    assert "common(_wedge)" in s                      # Keil behalten
    # Voll-Modus: geschnittene Bauteile werden HERAUSgeschnitten (Cutaway).
    full = ema_freecad.build_winding_head_stl_script(
        _GEOM, 120.0, "/tmp/wh.FCStd", stl, section_slots=3,
        cut={"rotor": True, "stator": True}, view_mode="full")
    assert "_VIEW   = 'full'" in full
    assert ".cut(_wedge)" in full, "Voll-Modus muss ein Tortenstück herausschneiden"
    print("✓ Anzeigen/Schneiden + Gesamt/Ausschnitt: gen-Flags + common/cut-Logik im Skript")


def test_slowmo_500_and_fast_and_jet():
    """Zeitlupe bis 500×, schnelle Darstellung + justierbare Strahlrichtung/Ziellinie sind
    im Skript und in run_oilspray verdrahtet."""
    s = OIL._blender_script()
    # 500× → time_scale 0.002; die untere Klemme muss das zulassen (nicht 0.005)
    assert "max(0.001, min(1.0, float(CFG.get(\"time_scale\", 1.0)))" in s
    assert "FAST" in s and 'CFG.get("fast"' in s
    assert "use_spray_particles\", not FAST" in s, "Fast-Modus muss Sekundärpartikel abschalten"
    assert "JET_TILT" in s and "JET_YAW" in s and "SHOW_JET_LINE" in s
    assert "JetLine_%02d" in s, "Ziellinie wird nicht gezeichnet"
    src = open(os.path.join(os.path.dirname(__file__), "ema_oilspray.py")).read()
    assert "min(500.0, float(oil.get(\"slowmo\", 1.0)" in src, "slowmo geht nicht bis 500"
    assert '"fast": fast' in src and '"jet_tilt_deg": jet_tilt' in src
    assert '"show_jet_line": show_jet_line' in src
    assert 'engine = "BLENDER_WORKBENCH"' in src, "Fast-Modus soll flach/schnell rendern"
    print("✓ Zeitlupe 500× + schnelle Darstellung + Strahlrichtung/Ziellinie verdrahtet")


def test_housing_transparent_and_drain():
    """Transparentes Voll-Ring-Gehäuse (Innen-Ø = Stator-Ø, Wand, Ringkanal-Ausbuchtung, Ablauf
    unten): geschlossene Schale + optionale KOLLISIONSWAND (housing_collide, Standard an — Öl
    wird am Glas gefangen, Domain bis zur Innenwand, Outflow an der Gehäuse-tiefsten Stelle);
    run_oilspray/preview reichen stator_od_mm + housing + housing_collide + wall durch."""
    import json as _json
    s = OIL._blender_script()
    # CFG-Konstanten + Bau-Block
    assert 'CFG.get("housing"' in s and 'CFG.get("housing_wall_mm"' in s
    assert 'CFG.get("housing_collide"' in s, "housing_collide-CFG fehlt"
    assert 'CFG.get("stator_od_mm"' in s and "STATOR_OD" in s
    assert "if HOUSING:" in s
    assert 'MotorHousing' in s and "SOLIDIFY" in s, "Gehäuseschale fehlt/ist kein Solidify"
    assert "end_fill_type='NGON'" in s, "Gehäuse-Deckel fehlen (offenes Rohr statt Dose)"
    assert 'HousingBulge' in s, "Ringkanal-Ausbuchtung fehlt"
    assert 'HousingDrain' in s, "sichtbarer Ablauf-Stutzen fehlt"
    # Kollisionswand: Domain-Erweiterung + Effector am Gehäuse + Drain an der tiefsten Stelle
    assert "_haus_col = HOUSING and HOUSING_COLLIDE" in s
    assert "R_hous_in" in s, "Domain-Erweiterung bis zur Gehäuse-Innenwand fehlt"
    assert "if _haus_col:" in s and "if _haus_col and HORIZONTAL:" in s, \
        "Kollisions-Effector/Drain-Verlagerung fehlt"

    # cfg-Passthrough über preview_oilspray (fake STL + Blender)
    d = tempfile.mkdtemp(); seen = {}

    def _fake_stl(geom, axial, workdir, section, cb=None, include_core=True,
                  components=None, cut=None, view_mode="section",
                  hidden_pins=None, winding_full=False):
        p = os.path.join(workdir, "winding_head.stl")
        os.makedirs(workdir, exist_ok=True); open(p, "w").write("solid\nendsolid\n")
        return {"winding": p}, "ok"

    def _fake_blender(code, argv=None, cwd=None, timeout=None, progress_cb=None):
        seen["cfg"] = _json.load(open(argv[0]))
        with open(seen["cfg"]["preview_png"], "wb") as f: f.write(b"\x89PNG")
        return {"ok": True, "aborted": False, "stdout": "", "returncode": 0}

    orig_stl, orig_bl = OIL._export_winding_stl, OIL.blender_runner.run_blender_script
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out = OIL.preview_oilspray(
            {"geom": dict(_GEOM, statorOD=300.0), "axial_len": 120.0,
             "oil": {"housing": True, "housing_wall_mm": 4.0, "housing_collide": False}}, d)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl
    c = seen["cfg"]
    assert abs(c["stator_od_mm"] - 300.0) < 1e-9, "Stator-Außen-Ø nicht durchgereicht"
    assert c["housing"] is True and abs(c["housing_wall_mm"] - 4.0) < 1e-9
    assert c["housing_collide"] is False, "housing_collide=False nicht durchgereicht"
    assert out["config"]["housing_collide"] is False
    print("✓ Transparentes Gehäuse + Ablauf: Skript-Block + cfg-Passthrough (inkl. Kollisionswand)")


def test_ring_full_360():
    """Voller 360°-Spritzring: geschlossener Ring-Kreis + gleichverteilte Düsen + volle
    Domain-Umfangsabdeckung sind im Skript verdrahtet; run/preview reichen ring_full durch."""
    import json as _json
    s = OIL._blender_script()
    # CFG-Konstante + geschlossener Ring (cyclic-Spline, kein Doppelpunkt) + Domain über 360°
    assert 'CFG.get("ring_full"' in s and "RING_FULL" in s
    assert "use_cyclic_u = True" in s, "Voll-Ring ist keine geschlossene Kurvenschleife"
    assert "_ring_closed = RING_FULL" in s, \
        "Voll-Ring muss auch in der Nahaufnahme geschlossen bleiben (kein Stutzen-Fallback)"
    assert "2.0 * math.pi * k / NOZZLES" in s, "Düsen nicht gleichmäßig über 360° verteilt"
    # wrap-fester Zielpunkt-Helfer mit synthetischem Radial-Fallback (Keil + voller Ring)
    assert "_crown_target_full" in s and "def _ang_d(" in s
    assert s.count("r_crown * math.cos(th_want)") >= 1, "synthetisches Radialziel fehlt"

    # cfg-Passthrough über preview_oilspray (fake STL + Blender)
    d = tempfile.mkdtemp(); seen = {}

    def _fake_stl(geom, axial, workdir, section, cb=None, include_core=True,
                  components=None, cut=None, view_mode="section",
                  hidden_pins=None, winding_full=False):
        p = os.path.join(workdir, "winding_head.stl")
        os.makedirs(workdir, exist_ok=True); open(p, "w").write("solid\nendsolid\n")
        return {"winding": p}, "ok"

    def _fake_blender(code, argv=None, cwd=None, timeout=None, progress_cb=None):
        seen["cfg"] = _json.load(open(argv[0]))
        with open(seen["cfg"]["preview_png"], "wb") as f: f.write(b"\x89PNG")
        return {"ok": True, "aborted": False, "stdout": "", "returncode": 0}

    orig_stl, orig_bl = OIL._export_winding_stl, OIL.blender_runner.run_blender_script
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out = OIL.preview_oilspray(
            {"geom": dict(_GEOM), "axial_len": 120.0,
             "oil": {"ring_full": True, "nozzle_count": 12}}, d)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl
    c = seen["cfg"]
    assert c["ring_full"] is True, "ring_full nicht in die Blender-cfg durchgereicht"
    assert c["nozzle_count"] == 12
    assert c["housing_collide"] is True, "Kollisionswand muss Standard AN sein"
    assert out["config"]["ring_full"] is True, "ring_full fehlt in der result-config"
    print("✓ Voller 360°-Spritzring: geschlossener Ring + 360°-Düsen + cfg-Passthrough")


def test_view_down_axes_smooth_material():
    """Unten-Achse (Blickrichtung), Koordinatensystem, Shade-Smooth und Öl-Transparenz sind
    im Skript verdrahtet, und preview_oilspray reicht Materialien/View durch."""
    s = OIL._blender_script()
    # Unten-Achse → Kamera-Oben-Achse; Drehteller orbitet um diese Achse
    assert "VIEW_DOWN" in s and "_up_axis_str()" in s and "_DOWN2UP" in s
    assert "_cam_up = _up_axis_str()" in s, "Kamera-Oben folgt nicht der Unten-Achse"
    assert "_UP2VEC.get(_cam_up" in s, "Drehteller-Orbit nicht an die Unten-Achse gekoppelt"
    # Koordinatensystem-Gizmo (XYZ-Pfeile)
    assert "SHOW_AXES" in s and 'Axis_%s' in s and "primitive_cone_add" in s
    # Shade Smooth
    assert "def _smooth(" in s and "shade_smooth" in s and "shade_auto_smooth" in s
    assert "_smooth(wh)" in s and "_smooth(ring_obj)" in s
    # Öl-Transparenz
    assert "OIL_ALPHA" in s and "use_screen_refraction" in s

    # preview_oilspray: Material → EEVEE, sonst Workbench; view_down/smooth durchgereicht
    import json as _json
    d = tempfile.mkdtemp(); seen = {}

    def _fake_stl(geom, axial, workdir, section, cb=None, include_core=True,
                  components=None, cut=None, view_mode="section",
                  hidden_pins=None, winding_full=False):
        p = os.path.join(workdir, "winding_head.stl")
        os.makedirs(workdir, exist_ok=True); open(p, "w").write("solid\nendsolid\n")
        return {"winding": p}, "ok"

    def _fake_blender(code, argv=None, cwd=None, timeout=None, progress_cb=None):
        seen["cfg"] = _json.load(open(argv[0]))
        with open(seen["cfg"]["preview_png"], "wb") as f: f.write(b"\x89PNG")
        return {"ok": True, "aborted": False, "stdout": "", "returncode": 0}

    orig_stl, orig_bl = OIL._export_winding_stl, OIL.blender_runner.run_blender_script
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out = OIL.preview_oilspray(
            {"geom": _GEOM, "axial_len": 120.0,
             "oil": {"view_down": "-z", "material": True, "smooth": False,
                     "oil_transparency": 0.7}}, d)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl
    c = seen["cfg"]
    assert c["view_down"] == "-z" and c["smooth"] is False
    assert c["engine"] == "BLENDER_EEVEE", "Material-Vorschau muss EEVEE nutzen"
    assert c["show_axes"] is True and abs(c["oil_transparency"] - 0.7) < 1e-9
    assert out["config"]["view_down"] == "-z" and out["config"]["material"] is True
    print("✓ Unten-Achse + Koordinatensystem + Shade-Smooth + Öl-Transparenz/Material verdrahtet")


def test_variant_autosave_and_store_roundtrip():
    """Jeder Lauf wird automatisch als eigene Variante abgelegt; list/load/delete arbeiten
    darauf (kein Überschreiben eines vorherigen Laufs)."""
    d = tempfile.mkdtemp()
    charts = os.path.join(d, "charts"); os.makedirs(charts)
    with open(os.path.join(charts, "oil_wetting.png"), "wb") as f:
        f.write(b"\x89PNG_fake")
    frames = os.path.join(d, OIL.FRAMES_SUBDIR); os.makedirs(frames)
    with open(os.path.join(frames, "anim.mp4"), "wb") as f:
        f.write(b"mp4data")
    result = {"source": "blender_mantaflow",
              "config": {"resolution": 96, "frames": 40, "slowmo": 25,
                         "view_mode": "full", "orientation": "vertical", "closeup": False},
              "metrics": {"wetted_pct_mean": 1.5, "wetted_pct_peak": 3.2},
              "series": [], "images": {"oil_wetting": "AAAA"}, "video": True}
    rid = OIL._autosave_variant(d, result, frames)
    assert rid, "keine Varianten-ID"
    assert os.path.exists(os.path.join(d, OIL.RUNS_SUBDIR, rid, "anim.mp4"))
    lst = OIL.list_saved_runs(d)
    assert len(lst) == 1 and lst[0]["id"] == rid
    assert lst[0]["view_mode"] == "full" and lst[0]["video"] is True
    back = OIL.load_saved_run(d, rid)
    assert back and back["config"]["slowmo"] == 25 and "oil_wetting" in back["images"]
    assert OIL.saved_run_video(d, rid) is not None
    assert OIL.delete_saved_run(d, rid) is True
    assert OIL.list_saved_runs(d) == []
    print("✓ Varianten-Store: Auto-Speichern + list/load/video/delete Roundtrip")


def test_preview_branch_and_orchestrator():
    """Zwischenansicht: das Blender-Skript hat einen PREVIEW-Zweig (kein Bake, EIN Standbild,
    OIL_PREVIEW-Marker), und preview_oilspray baut die richtige cfg (preview + Linien erzwungen)
    ohne frames_oil/Cache/results.json zu berühren."""
    s = OIL._blender_script()
    assert 'PREVIEW    = bool(CFG.get("preview"' in s
    assert "if PREVIEW:" in s and "OIL_PREVIEW:" in s
    assert "SHOW_JET_LINE = True" in s, "Vorschau muss die Ziellinien erzwingen"
    # Drehteller: das Skript orbitet die Kamera über PREVIEW_TURNS Winkel
    assert "PREVIEW_TURNS" in s and "Matrix.Rotation" in s, "Drehteller-Orbit fehlt"

    # preview_oilspray mit gefälschtem STL-Export + gefälschtem Blender-Lauf
    import json as _json
    d = tempfile.mkdtemp()
    seen = {}

    def _fake_stl(geom, axial, workdir, section, cb=None, include_core=True,
                  components=None, cut=None, view_mode="section",
                  hidden_pins=None, winding_full=False):
        seen["view_mode"] = view_mode
        seen["hidden_pins"] = hidden_pins
        seen["winding_full"] = winding_full
        p = os.path.join(workdir, "winding_head.stl")
        os.makedirs(workdir, exist_ok=True); open(p, "w").write("solid\nendsolid\n")
        return {"winding": p}, "ok"

    def _fake_blender(code, argv=None, cwd=None, timeout=None, progress_cb=None):
        cfg = _json.load(open(argv[0]))
        seen["cfg"] = cfg
        _n = int(cfg.get("preview_turns", 1))
        if _n > 1:
            # „Render" die Drehteller-Winkel, die preview_oilspray aus preview_dir einsammelt
            for _k in range(_n):
                with open(os.path.join(cfg["preview_dir"], "preview_%03d.png" % _k), "wb") as f:
                    f.write(b"\x89PNG_turn")
        else:
            with open(cfg["preview_png"], "wb") as f:
                f.write(b"\x89PNG_preview")
        return {"ok": True, "aborted": False, "stdout": "", "returncode": 0}

    orig_stl, orig_bl = OIL._export_winding_stl, OIL.blender_runner.run_blender_script
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out = OIL.preview_oilspray(
            {"geom": _GEOM, "axial_len": 120.0,
             "oil": {"view_mode": "full", "closeup": True, "jet_tilt_deg": 15,
                     "show": {"stator": True}, "cut": {"stator": True}}},
            d)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl

    assert out["image"], "kein Vorschaubild"
    assert seen["cfg"]["preview"] is True and seen["cfg"]["show_jet_line"] is True
    assert seen["cfg"]["closeup"] is True and seen["view_mode"] == "full"
    # Vorschau darf den echten Lauf NICHT anfassen
    assert not os.path.exists(os.path.join(d, "results.json"))
    assert not os.path.exists(os.path.join(d, OIL.FRAMES_SUBDIR))

    # Drehteller: preview_turns>1 → mehrere base64-Bilder + Winkel-cfg
    d2 = tempfile.mkdtemp()
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out2 = OIL.preview_oilspray(
            {"geom": _GEOM, "axial_len": 120.0, "oil": {"preview_turns": 12}}, d2)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl
    assert seen["cfg"]["preview_turns"] == 12
    assert len(out2["images"]) == 12 and out2["turns"] == 12, "Drehteller lieferte nicht 12 Winkel"
    assert out2["image"] == out2["images"][0]
    print("✓ Vorschau: PREVIEW-Zweig (kein Bake) + Drehteller (N Winkel) + cfg, ohne echten Lauf zu berühren")


def test_frames_marker_regex():
    """Der Fortschritts-Marker OIL_FRAMES:i/n wird korrekt geparst."""
    m = blender_runner._FRAMES_RE.search("OIL_FRAMES:7/80")
    assert m and int(m.group(1)) == 7 and int(m.group(2)) == 80
    assert blender_runner._FRAMES_RE.search("kein marker") is None
    print("✓ OIL_FRAMES-Regex: 7/80 geparst")


def test_clamp():
    assert OIL._clamp(900, *OIL.RES_RANGE, OIL.DEFAULT_RES) == OIL.RES_RANGE[1]
    assert OIL.RES_RANGE[1] >= 512, "Domain-Auflösung soll bis mind. 512 gehen (Nutzerwunsch)"
    assert OIL._clamp(1, *OIL.RES_RANGE, OIL.DEFAULT_RES) == OIL.RES_RANGE[0]
    assert OIL._clamp("abc", *OIL.RES_RANGE, OIL.DEFAULT_RES) == OIL.DEFAULT_RES
    assert OIL._clamp(72, *OIL.RES_RANGE, OIL.DEFAULT_RES) == 72
    print("✓ _clamp: Bereichsgrenzen + Default bei Unfug")


def test_metric_charts_and_persist():
    """Aus synthetischen Metriken entstehen die Benetzungs-/Tropfen-Charts; _persist mergt
    eine schlanke (base64-freie) Zusammenfassung in eine vorhandene results.json."""
    metrics = {"series": [{"frame": i, "wetted_pct": min(100, i * 12),
                           "n_islands": 1 + (i % 3), "n_liquid_verts": 100 * i}
                          for i in range(1, 9)],
               "wetted_pct_peak": 96.0, "wetted_pct_mean": 54.0, "droplets_peak": 3}
    d = tempfile.mkdtemp()
    charts = os.path.join(d, "charts")
    imgs = OIL._metric_charts(metrics, charts)
    assert "oil_wetting" in imgs and "oil_droplets" in imgs
    assert os.path.exists(os.path.join(charts, "oil_wetting.png"))
    assert os.path.exists(os.path.join(charts, "oil_droplets.png"))

    # _persist in eine bestehende results.json
    import json
    rj = os.path.join(d, "results.json")
    with open(rj, "w") as f:
        json.dump({"summary": {"x": 1}}, f)
    result = {"source": "blender_mantaflow", "config": {"resolution": 72},
              "metrics": {"wetted_pct_peak": 96.0}, "series": metrics["series"],
              "images": {"oil_wetting": "AAAA", "oil_coverage": "BBBB"}, "video": True,
              "note": "qual"}
    OIL._persist(d, result)
    with open(rj) as f:
        back = json.load(f)
    assert "oilspray" in back and "images" not in back["oilspray"], "base64 nicht persistiert"
    assert back["oilspray"]["image_files"]["oil_wetting"] == "charts/oil_wetting.png"
    assert back["summary"]["x"] == 1, "bestehende Daten erhalten"
    print("✓ Charts erzeugt + _persist mergt schlank (keine base64) in results.json")


def test_blender_multi_part_materials_and_effectors():
    """Jedes Bauteil (shaft/rotor/stator/magnets/winding) kommt als EIGENE STL-Datei/Objekt rein
    und bekommt sein fachlich korrektes Material (Kupfer/Elektroblech/dunkler Magnet-Stahl/heller
    Edelstahl) statt der alten Radius-/Achs-Heuristik auf einem gemergten Mesh; ALLE importierten
    Bauteile werden zu Fluid-Effektoren (nicht nur der Wickelkopf)."""
    s = OIL._blender_script()
    assert "STL_PARTS = CFG.get(\"stl_parts\")" in s
    assert "_parts_obj" in s and "_PART_NAMES" in s
    assert 'wh = _parts_obj.get("winding") or next(iter(_parts_obj.values()))' in s
    for mat in ("Edelstahl-Welle", "Elektroblech", "Magnet-Stahl", "Kupfer"):
        assert mat in s, f"Material {mat!r} fehlt"
    assert "_PART_MATS = {" in s
    assert "for _po in _parts_obj.values():" in s and "'EFFECTOR'" in s.replace('"EFFECTOR"', "'EFFECTOR'")
    # Sektor-Ausrichtungs-Rotation (horizontale Einbaulage) muss auf ALLE Bauteil-Objekte wirken,
    # nicht nur auf `wh` — sonst laufen Statornuten (fix) und Hairpins (gedreht) angular auseinander.
    assert "for _po in _parts_obj.values():" in s and "_po.rotation_euler = (0.0, 0.0, _rot_z)" in s
    assert "wh.rotation_euler = (0.0, 0.0," not in s, "nur wh drehen ist der alte Bug"
    print("✓ Je-Bauteil-Import + echte Materialien (Kupfer/Elektroblech/Magnet-Stahl/Edelstahl) + Alle-Effektoren")


def test_camera_lock_from_preview():
    """Kamera-Fixwinkel (Drehteller→Video): CFG['camera_angle_deg'] dreht die Standard-Kamera-
    position um dieselbe Achse/Formel wie der Drehteller, bevor sie erzeugt wird."""
    s = OIL._blender_script()
    assert '_CAM_LOCK_DEG = CFG.get("camera_angle_deg")' in s
    assert "_lock_rot = mathutils.Matrix.Rotation" in s
    src = open(os.path.join(os.path.dirname(__file__), "ema_oilspray.py")).read()
    assert '"camera_angle_deg": camera_angle' in src
    assert 'oil.get("camera_angle_deg")' in src
    print("✓ Kamera-Fixwinkel aus der Vorschau wird in cfg/Skript durchgereicht")


def test_light_presets_wired():
    """Beleuchtungs-Voreinstellungen (Nutzer-Beanstandung: Stahl wirkte weiß/ausgebrannt, weil das
    alte Fülllicht AN der Kameraposition saß -> Kamerablitz-Effekt auf glänzendem Metall). Das
    3-Punkt-Rig (Key/seitlich versetztes Fülllicht/Kantenlicht) muss im Skript verdrahtet sein und
    run_oilspray/preview_oilspray müssen den gewählten Preset in cfg["light"] auflösen."""
    assert set(OIL.LIGHT_PRESETS) == {"studio", "werkstatt", "weich", "kontrast"}
    assert OIL._resolve_light_preset("unbekannt")["label"] == OIL.LIGHT_PRESETS["studio"]["label"]
    assert OIL._resolve_light_preset(None) is OIL.LIGHT_PRESETS[OIL.DEFAULT_LIGHT_PRESET]

    s = OIL._blender_script()
    assert 'LIGHT = CFG.get("light") or {}' in s
    assert "_fill_offset" in s and "_rim_on" in s and "_rim_offset" in s
    # Fülllicht darf NICHT mehr direkt an der Kameraposition erzeugt werden (der alte Bug).
    assert 'bpy.ops.object.light_add(type=\'AREA\', location=cam_loc)' not in s
    assert "_fill_loc = cam_tgt + mathutils.Vector" in s

    import json as _json
    d = tempfile.mkdtemp(); seen = {}

    def _fake_stl(geom, axial, workdir, section, cb=None, include_core=True,
                  components=None, cut=None, view_mode="section",
                  hidden_pins=None, winding_full=False):
        p = os.path.join(workdir, "winding_head.stl")
        os.makedirs(workdir, exist_ok=True); open(p, "w").write("solid\nendsolid\n")
        return {"winding": p}, "ok"

    def _fake_blender(code, argv=None, cwd=None, timeout=None, progress_cb=None):
        seen["cfg"] = _json.load(open(argv[0]))
        with open(seen["cfg"]["preview_png"], "wb") as f: f.write(b"\x89PNG")
        return {"ok": True, "aborted": False, "stdout": "", "returncode": 0}

    orig_stl, orig_bl = OIL._export_winding_stl, OIL.blender_runner.run_blender_script
    try:
        OIL._export_winding_stl = _fake_stl
        OIL.blender_runner.run_blender_script = _fake_blender
        out = OIL.preview_oilspray(
            {"geom": _GEOM, "axial_len": 120.0, "oil": {"light_preset": "kontrast"}}, d)
    finally:
        OIL._export_winding_stl, OIL.blender_runner.run_blender_script = orig_stl, orig_bl
    assert seen["cfg"]["light"] == _json.loads(_json.dumps(OIL.LIGHT_PRESETS["kontrast"]))
    assert out["config"]["light_preset"] == "kontrast"
    print("✓ Beleuchtungs-Voreinstellungen: 3-Punkt-Rig verdrahtet, Preset-Auflösung + Roundtrip")


def test_export_winding_stl_returns_parts_dict():
    """_export_winding_stl liefert ein {key: pfad}-Dict (je-Bauteil-STL), nicht mehr einen
    einzelnen Pfad — und reicht hidden_pins/winding_full an den Skript-Generator durch."""
    d = tempfile.mkdtemp()
    seen = {}

    def _fake_run(code, timeout=600):
        seen["code"] = code
        stl_dir = os.path.join(d, "stl_parts")
        os.makedirs(stl_dir, exist_ok=True)
        open(os.path.join(stl_dir, "winding.stl"), "w").write("solid\nendsolid\n")
        open(os.path.join(stl_dir, "rotor.stl"), "w").write("solid\nendsolid\n")
        return {"success": True, "stl_parts": {"winding": "winding.stl", "rotor": "rotor.stl"}}

    orig = freecad_runner.run_freecad_script
    try:
        freecad_runner.run_freecad_script = _fake_run
        parts, log = OIL._export_winding_stl(_GEOM, 120.0, d, 3, hidden_pins=[1, 2],
                                             winding_full=True)
    finally:
        freecad_runner.run_freecad_script = orig
    assert log == "ok" and isinstance(parts, dict)
    assert set(parts) == {"winding", "rotor"}
    assert all(os.path.exists(p) for p in parts.values())
    assert "_HIDDEN_PINS = set([1, 2])" in seen["code"]
    print("✓ _export_winding_stl liefert {key:pfad}-Dict + reicht hidden_pins/winding_full durch")


def main():
    test_stl_script_wedge_section()
    test_stl_export_survives_degenerate_shape()
    test_stl_script_hidden_pins_and_winding_full()
    test_slot_limit_in_full_script()
    test_blender_script_markers()
    test_blender_multi_part_materials_and_effectors()
    test_camera_lock_from_preview()
    test_light_presets_wired()
    test_export_winding_stl_returns_parts_dict()
    test_orientation_closeup_branches()
    test_jet_focus_and_thin_oil()
    test_nozzle_aligned_to_hairpin()
    test_slowmo_time_scale()
    test_component_lists_and_view_mode()
    test_slowmo_500_and_fast_and_jet()
    test_housing_transparent_and_drain()
    test_ring_full_360()
    test_view_down_axes_smooth_material()
    test_variant_autosave_and_store_roundtrip()
    test_preview_branch_and_orchestrator()
    test_persist_creates_and_load_saved_roundtrip()
    test_frames_marker_regex()
    test_clamp()
    test_metric_charts_and_persist()
    print("\nALLE SPRITZÖL-TESTS BESTANDEN ✅  (Blender-Bake separat, End-to-End über die UI)")


if __name__ == "__main__":
    main()
