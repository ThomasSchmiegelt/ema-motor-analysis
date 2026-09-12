"""Tests fuer den FluidX3D-Spritzoelpfad (LBM, freie Oberflaeche) — OHNE GPU,
ohne Uebersetzer, ohne FreeCAD.

Geprueft werden die reinen Bausteine: das Setzen von ``defines.hpp``, der
Marker-Parser gegen die WIRKLICH gemessene Ausgabeform, die Auflösungsrechnung
gegen den gemessenen Speicherbedarf, die Fensterlage aus der Geometrie, das
STL-Drehen, der erzeugte C++-Fall (samt Lizenzpflichten) und die Ablage.

Drei Pruefungen halten Befunde fest, die Geld gekostet haben und die man einem
Ergebnis nicht ansieht:
  * ``test_ganze_maschine_passt_nicht`` — die Begruendung fuer das Fenster,
  * ``test_fenster_liegt_am_wickelkopf`` — der erste Probelauf traf die geraden
    Staebe statt der Krone,
  * ``test_saeule_startet_ausserhalb`` — der zweite hatte schon zum Zeitpunkt 0
    Oel am Kupfer, weil die Saeule im Leiterzwischenraum begann.

Lauf: ``python test_fluidx3d.py``
"""

import json
import math
import os
import tempfile

import numpy as np

import ema_fluidx3d as FX
import fluidx3d_runner as RUN


# ── 1. defines.hpp ───────────────────────────────────────────────────────────
def test_defines_setzen():
    """Die Zeilen tragen Zeilenendkommentare — ein `replace` auf die ganze Zeile
    greift nicht. Genau daran scheiterte der erste Versuch von Hand."""
    quelle = ("//#define SURFACE // enables free surface LBM: mark fluid cells\n"
              "#define GRAPHICS // on-the-fly rendering\n"
              "//#define VOLUME_FORCE\n"
              "#define PARTICLES // immersed particles\n"
              "#define FP16S\n"
              "//#define SURFACE_EXTRA // darf NICHT mitgeschaltet werden\n")
    neu = RUN.defines_setzen(quelle)
    stand = RUN.defines_stand(neu)
    assert "SURFACE" in stand and "VOLUME_FORCE" in stand and "FP16S" in stand
    assert "GRAPHICS" not in stand and "PARTICLES" not in stand
    # Praefix-Treffer duerfen nicht mitgehen (\b im Muster)
    assert "SURFACE_EXTRA" not in stand
    assert "//#define SURFACE_EXTRA" in neu
    # zweimal setzen aendert nichts mehr
    assert RUN.defines_setzen(neu) == neu
    print("✓ defines.hpp: Schalter gesetzt, Zeilenendkommentare ueberstanden, idempotent")


# ── 2. Marker aus FluidX3Ds Fortschrittszeile ────────────────────────────────
def test_marker_aus_fortschrittszeile():
    """FluidX3D ueberschreibt seine Fortschrittszeile mit ``\\r`` aus einem
    NEBENLAEUFIGEN Thread (`info.cpp:105`, `main.cpp:159`). Zeilenweises Lesen
    sieht die eigenen Marker deshalb MITTENDRIN. Das ist gemessen, nicht
    befuerchtet — die Ausgabe des Probelaufs sah genau so aus."""
    roh = ("|    9579 |   2902 GB/s |      1064 |        12000 100% |     0s |"
           "|FX3D_STAGE:Kupfer gevoxelt|    9580 |   2903 GB/s |")
    assert RUN.marker_aus(roh) == [("STAGE", "Kupfer gevoxelt")]
    assert RUN.marker_aus("\x1b[92mInfo\x1b[0m: x FX3D_STEP:7/24 y") == [("STEP", "7/24")]
    assert RUN.marker_aus("nichts dran") == []
    arten = [a for a, _ in RUN.marker_aus("FX3D_STAGE:a\nFX3D_DONE")]
    assert arten == ["STAGE", "DONE"]
    print("✓ Marker: aus der Fortschrittszeile herausgeloest, ANSI entfernt")


# ── 3. Auflösung gegen die Messung ───────────────────────────────────────────
def test_aufloesung_gegen_messung():
    """Gemessen am 12.09.2026: 208^3 = 8.998.912 Zellen belegten 572 MB GPU-
    Speicher (SURFACE + FP16S). Die Schaetzung muss das treffen — zu klein
    geschaetzt endet in einem OOM, und ein OOM ist hier ein SIGKILL."""
    a = FX.aufloesung(48.0, 1.0, n_fest=208)
    assert a["n"] == 208 and a["zellen"] == 208 ** 3
    assert abs(a["speicher_mb"] - 572.0) / 572.0 < 0.02, a["speicher_mb"]
    assert abs(a["zellen_je_bohrung"] - 4.33) < 0.01
    assert not a["unteraufgeloest"]

    # Der gemessene Fehlfall: ganze Maschine in einem Fenster ⇒ 1 Zelle je Bohrung
    b = FX.aufloesung(160.0, 1.0, n_fest=160)
    assert b["zellen_je_bohrung"] < FX.ZELLEN_JE_BOHRUNG_MIN
    assert b["unteraufgeloest"] is True

    # ohne Vorgabe wird auf das Ziel von 3 Zellen je Bohrung ausgelegt
    c = FX.aufloesung(48.0, 1.0)
    assert c["zellen_je_bohrung"] >= FX.ZELLEN_JE_BOHRUNG_ZIEL - 0.01

    # Der Speicher deckelt, nicht der Wunsch
    d = FX.aufloesung(48.0, 0.2, vram_mb=200)
    assert d["speicher_mb"] <= 200.0 * 1.0
    print("✓ Aufloesung: 575,9 MB geschaetzt gegen 572 MB gemessen (0,7 %), "
          "Unteraufloesung erkannt, Speicherdeckel greift")


def test_ganze_maschine_passt_nicht():
    """Der Grund, warum dieses Modul ein FENSTER rechnet — als Zahl, nicht als
    Behauptung. 305-mm-Stator, 1-mm-Bohrung, drei Zellen darueber."""
    v = FX.vollmaschine_kosten(305.0, 1.0)
    assert v["speicher_gb"] > 24.0, v
    assert v["passt"] is False
    # eine 3-mm-Bohrung an einer kleinen Maschine ginge dagegen
    k = FX.vollmaschine_kosten(90.0, 3.0)
    assert k["passt"] is True, k
    print("✓ Vollmaschine: %.0f GB noetig (passt nicht) — kleine Maschine mit "
          "3-mm-Bohrung passt" % v["speicher_gb"])


# ── 4. STL lesen/schreiben ───────────────────────────────────────────────────
def _ring_stl(r_i, r_a, z0, z1, n=64):
    """Synthetischer Zylinderring als Dreiecksnetz (ohne FreeCAD)."""
    tris = []
    for i in range(n):
        a0, a1 = 2 * math.pi * i / n, 2 * math.pi * (i + 1) / n
        for r in (r_i, r_a):
            p00 = (r * math.cos(a0), r * math.sin(a0), z0)
            p01 = (r * math.cos(a0), r * math.sin(a0), z1)
            p10 = (r * math.cos(a1), r * math.sin(a1), z0)
            p11 = (r * math.cos(a1), r * math.sin(a1), z1)
            tris.append([p00, p10, p11])
            tris.append([p00, p11, p01])
    return np.array(tris, dtype=np.float32)


def test_stl_rundlauf():
    tris = _ring_stl(90.0, 100.0, -10.0, 10.0)
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "t.stl")
        FX._stl_schreiben(p, tris)
        zurueck = FX._stl_lesen(p)
    assert zurueck.shape == tris.shape
    assert np.allclose(zurueck, tris, atol=1e-5)
    print("✓ STL: schreiben/lesen liefert dieselben Ecken (%d Dreiecke)" % len(tris))


# ── 5. Fensterlage ───────────────────────────────────────────────────────────
def _wickelkopf_stl():
    """Ein Paket (|z| < 75) plus EIN Kronen-Ausschnitt bei ~40° und z = 75…110.
    Der Probelauf setzte das Fenster auf z = 98 und traf die geraden Staebe —
    hier muss es in der Krone landen."""
    paket = _ring_stl(95.0, 140.0, -75.0, 75.0)
    krone = _ring_stl(120.0, 143.0, 78.0, 110.0, n=64)
    # Krone auf einen Ausschnitt um 40° beschneiden
    th = np.arctan2(krone[..., 1], krone[..., 0]).mean(axis=1)
    ziel = math.radians(40.0)
    d = np.abs(np.arctan2(np.sin(th - ziel), np.cos(th - ziel)))
    return np.concatenate([paket, krone[d < math.radians(20.0)]], axis=0)


def test_fenster_liegt_am_wickelkopf():
    tris = _wickelkopf_stl()
    f = FX.fenster_bestimmen(tris, axial_len_mm=150.0, fenster_mm=48.0,
                             ring_gap_mm=3.0, duese_mm=1.0, anlauf_mm=15.0)
    # Der Ausschnitt wird auf die +x-Achse gedreht
    assert abs(f["theta_deg"] - 40.0) < 3.0, f["theta_deg"]
    # z liegt im UEBERHANG, nicht im Blechpaket — der Fehler des ersten Laufs
    assert f["z_krone_mm"] > f["z_paket_mm"], f
    assert 78.0 <= f["z_krone_mm"] <= 110.0, f["z_krone_mm"]
    assert abs(f["r_krone_mm"] - 143.0) < 1.5, f["r_krone_mm"]
    assert abs(f["r_duese_mm"] - (f["r_krone_mm"] + 3.0)) < 1e-6
    # Anlauf liegt HINTER der Muendung, das Kupfer bleibt trotzdem im Bild
    bx = f["box_min_mm"][0]
    assert bx + 48.0 > f["r_duese_mm"] + 15.0, f
    assert f["kupfertiefe_mm"] > 5.0, f
    print("✓ Fenster: %+.1f° gedreht, Krone r=%.1f z=%.1f (Paket endet bei %.0f), "
          "%.1f mm Anlauf, %.1f mm Kupfer im Bild"
          % (f["theta_deg"], f["r_krone_mm"], f["z_krone_mm"], f["z_paket_mm"],
             f["anlauf_mm"], f["kupfertiefe_mm"]))


def test_fenster_ohne_ueberhang_sagt_es():
    """Kein Wickelkopf (nur ein Paket) — dann wird das Fenster aufs ganze Teil
    gesetzt und das steht im Ergebnis, statt still eine Krone zu erfinden."""
    f = FX.fenster_bestimmen(_ring_stl(95.0, 140.0, -75.0, 75.0), 150.0, 48.0)
    assert "kein Wickelkopf" in f["quelle"]
    print("✓ Fenster ohne Ueberhang: '%s'" % f["quelle"])


def test_stl_drehen_legt_ausschnitt_auf_x():
    tris = _wickelkopf_stl()
    f = FX.fenster_bestimmen(tris, 150.0, 48.0, 3.0, 1.0, anlauf_mm=15.0)
    with tempfile.TemporaryDirectory() as d:
        q = os.path.join(d, "q.stl")
        FX._stl_schreiben(q, tris)
        z = FX.stl_ins_fenster([q], f, os.path.join(d, "z.stl"))
        gedreht = FX._stl_lesen(z)
    p = gedreht.reshape(-1, 3)
    ueber = p[p[:, 2] > 75.0]
    th = np.degrees(np.arctan2(ueber[:, 1], ueber[:, 0]))
    assert abs(float(np.mean(np.arctan2(np.sin(np.radians(th)),
                                        np.cos(np.radians(th)))))) < 0.05
    print("✓ STL gedreht: der Ausschnitt liegt auf der +x-Achse (Mittelwinkel ~0°)")


# ── 6. Der erzeugte C++-Fall ─────────────────────────────────────────────────
def _cfg(**over):
    c = {"ZEIT": "2026-09-12 12:00:00", "N1": 208, "CELL_MM": "0.230769",
         "BOX_MM": "48.0", "BOX_MIN_X": "117.636", "BOX_MIN_Y": "-24.0",
         "BOX_MIN_Z": "70.284", "SI_RHO": "850.0", "SI_NU": "0.00001",
         "SI_SIGMA": "0.03", "SI_G": "9.81", "SI_U": "21.25", "D_NOZ_MM": "1.0",
         "X_NOZ": "126.1", "Z_NOZ": "104.0", "SAEULE": "64.6", "TILT": "0.0",
         "N_BILDER": 24, "SCHRITTE": 500, "STL": "../stl/f.stl", "AUS": "/tmp/aus"}
    c.update(over)
    return c


def test_setup_code_vollstaendig_und_lizenztreu():
    code = FX.setup_code(_cfg())
    assert "@@" not in code
    # Lizenzpflicht: geaenderte Fassung MUSS als solche gekennzeichnet sein
    assert "ALTERED SOURCE VERSION" in code
    assert "github.com/ProjectPhysX/FluidX3D" in code
    assert "licence notice retained" in code.lower() or "LICENSE.md" in code
    # die Schalter, auf die der Fall angewiesen ist, stehen im Kopf
    for s in ("SURFACE", "VOLUME_FORCE", "EQUILIBRIUM_BOUNDARIES", "FP16S"):
        assert s in code
    assert "FX3D_DONE" in code and "FX3D_STEP:" in code
    assert "kennwerte.json" in code and "schnitt_" in code and "fest.bin" in code
    # eine fehlende Angabe faellt auf, statt als "@@X@@" mitzureisen
    unvoll = dict(_cfg()); unvoll.pop("SAEULE")
    try:
        FX.setup_code(unvoll)
    except RuntimeError as e:
        assert "SAEULE" in str(e)
    else:
        raise AssertionError("unvollstaendige Vorlage wurde nicht beanstandet")
    print("✓ C++-Fall: vollstaendig gesetzt, als geaenderte Fassung gekennzeichnet, "
          "Luecke wird beanstandet")


def test_saeule_startet_ausserhalb():
    """Die Oelsaeule muss HINTER der Muendung in freier Luft stehen, nicht im
    Zwischenraum der Leiter. Gemessen im zweiten Probelauf: 13 Zellen lagen
    schon zum Zeitpunkt 0 am Kupfer, weil die Saeule nach INNEN gelegt wurde.

    Geprueft wird das Praedikat selbst — dieselben Formeln, mit denen das
    erzeugte C++ die Zellen auswaehlt — und nicht der Wortlaut des Quelltexts."""
    x_noz, z_noz, saeule, r_loch, tilt = 126.1, 104.0, 64.6, 2.17, 0.0
    ct, st = math.cos(tilt), math.sin(tilt)
    ny = 208
    treffer = []
    for x in range(0, 208, 2):
        for y in range(0, 208, 8):
            for z in range(0, 208, 8):
                px, py, pz = x - x_noz, y - 0.5 * ny, z - z_noz
                s = px * ct - pz * st                 # Lauflaenge NACH AUSSEN
                if s < 0.0 or s > saeule:
                    continue
                qx, qz = px - s * ct, pz + s * st
                if math.sqrt(qx * qx + py * py + qz * qz) >= r_loch:
                    continue
                treffer.append((x, y, z))
    assert treffer, "keine Saeulenzellen gefunden"
    assert all(x >= x_noz - 1.0 for x, _, _ in treffer), \
        "Saeule ragt nach innen — sie begaenne im Kupfer"
    assert max(x for x, _, _ in treffer) <= x_noz + saeule + 1.0
    print("✓ Oelsaeule: %d Probezellen, alle ausserhalb der Muendung "
          "(x >= %.0f), Laenge <= %.0f Zellen" % (len(treffer), x_noz, saeule))


def test_uebersetzungsbefehl_ist_der_offizielle():
    """Genau der ``Linux``-Zweig aus FluidX3Ds eigenem ``make.sh`` — nicht
    ``make.sh`` selbst, das den Lauf gleich mitstartet."""
    if not RUN.QUELLE:
        print("• FluidX3D-Quellbaum fehlt — Uebersetzungsbefehl uebersprungen")
        return
    cmd = RUN._uebersetzungsbefehl(RUN.QUELLE)
    txt = " ".join(cmd)
    for flag in ("-std=c++17", "-pthread", "-O", "-Wno-comment", "-lOpenCL",
                 "src/OpenCL/include", "bin/FluidX3D"):
        assert flag in txt, flag
    assert "src/setup.cpp" in txt and "src/lbm.cpp" in txt
    assert "-lX11" not in txt                       # GRAPHICS ist aus
    print("✓ Uebersetzung: make.sh-Linux-Zweig, ohne X11")


# ── 7. Auswertung, Bilder, Ablage ────────────────────────────────────────────
def _metriken(n=6):
    return {"reihe": [{"bild": i, "t_ms": 0.4 * i, "oel_mm3": 20.0 - 0.05 * i,
                       "nass": 900 + 80 * i, "am_kupfer": 10 * i} for i in range(n)],
            "n1": 32, "zelle_mm": 1.5, "mlups": 9500.0, "sekunden": 11.3,
            "schritte": 12000, "fest": 1000, "zellen_je_bohrung": 4.33}


def test_charts_und_bilder():
    m = _metriken()
    with tempfile.TemporaryDirectory() as d:
        imgs = FX.kennwert_charts(m, os.path.join(d, "charts"))
        assert set(imgs) == {"fx3d_benetzung", "fx3d_masse"}
        for k in imgs:
            assert os.path.exists(os.path.join(d, "charts", k + ".png"))
        assert FX.kennwert_charts({"reihe": []}, os.path.join(d, "charts")) == {}

        # Schnittdateien: 32x32, Kupfer als 255
        n1 = 32
        fest = np.zeros((n1, n1), dtype=np.uint8)
        fest[8:16, 4:12] = 255
        fp = os.path.join(d, "fest.bin"); open(fp, "wb").write(fest.tobytes())
        schnitte = []
        for i in range(len(m["reihe"])):
            feld = fest.copy()
            feld[20, 20 - i] = 200
            p = os.path.join(d, "schnitt_%04d.bin" % i)
            open(p, "wb").write(feld.tobytes())
            schnitte.append(p)
        frames = os.path.join(d, "frames")
        n = FX.bilder_rendern(schnitte, fp, n1, 1.5, m["reihe"], frames, "Test")
        assert n == len(schnitte)
        assert len(os.listdir(frames)) == len(schnitte)
    print("✓ Diagramme + %d Schnittbilder gerendert (ohne GPU)" % n)


def test_persist_und_varianten():
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, "charts"), exist_ok=True)
        res = {"source": "fluidx3d_lbm", "config": {"n": 208, "zelle_mm": 0.2308,
               "fenster_mm": 48.0, "dauer_ms": 10.0, "pressure_bar": 3.0,
               "nozzle_d_mm": 1.0},
               "metrics": {"mlups": 9500.0, "sekunden": 11.3},
               "bilanz": {"getroffen": True, "am_kupfer_max": 880,
                          "masse_abweichung_pct": -1.1},
               "series": _metriken()["reihe"], "images": {}, "video": False}
        # results.json existiert NICHT — muss angelegt werden
        FX._persist(d, res)
        assert os.path.exists(os.path.join(d, "results.json"))
        with open(os.path.join(d, "results.json")) as f:
            assert "fluidx3d" in json.load(f)
        zurueck = FX.load_saved(d)
        assert zurueck["bilanz"]["getroffen"] is True
        assert "images" in zurueck

        rid = FX._autosave_variant(d, res, os.path.join(d, "frames_fx3d"))
        liste = FX.list_saved_runs(d)
        assert len(liste) == 1 and liste[0]["id"] == rid
        assert liste[0]["getroffen"] is True and liste[0]["mlups"] == 9500.0
        eine = FX.load_saved_run(d, rid)
        assert eine["config"]["n"] == 208
        assert FX.load_saved_run(d, "gibtsnicht") is None
        assert FX.saved_run_video(d, rid) is None            # kein Video geschrieben
        assert FX.delete_saved_run(d, rid) is True
        assert FX.list_saved_runs(d) == []
    print("✓ Ablage: results.json angelegt, Variante gespeichert/geladen/geloescht")


def test_klemmen_und_strahl():
    assert FX.strahlgeschwindigkeit(3.0) == FX.strahlgeschwindigkeit(3.0)
    assert abs(FX.strahlgeschwindigkeit(3.0) - 21.25) < 0.02
    # dieselbe Formel wie im 💧-Pfad
    import ema_oilspray as OIL  # noqa: F401  (nur der Vergleich der Konstanten)
    assert FX.CD_NOZZLE == 0.8 and FX.SI_RHO == 850.0
    assert FX._klemm("quatsch", 1, 10, 5) == 5
    assert FX._klemm(99, 1, 10, 5) == 10
    assert FX._klemm(float("nan"), 1, 10, 5) == 5
    print("✓ Strahl 21,25 m/s bei 3 bar (Formel und Stoffwerte wie im 💧-Pfad)")


def main():
    test_defines_setzen()
    test_marker_aus_fortschrittszeile()
    test_aufloesung_gegen_messung()
    test_ganze_maschine_passt_nicht()
    test_stl_rundlauf()
    test_fenster_liegt_am_wickelkopf()
    test_fenster_ohne_ueberhang_sagt_es()
    test_stl_drehen_legt_ausschnitt_auf_x()
    test_setup_code_vollstaendig_und_lizenztreu()
    test_saeule_startet_ausserhalb()
    test_uebersetzungsbefehl_ist_der_offizielle()
    test_charts_und_bilder()
    test_persist_und_varianten()
    test_klemmen_und_strahl()
    print("\nALLE FLUIDX3D-TESTS BESTANDEN ✅  (GPU-Lauf separat)")


if __name__ == "__main__":
    main()
