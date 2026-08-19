"""Tests für den 🧪 Spray-Test-Prüfstand (`ema_spraytest`) — laufen OHNE Blender.

Abgedeckt: Parameter-Sampling (Runde-1-Streuung + Anker, Mutation um Eltern, σ-Schrumpf,
Bereichs-Klemmung, Dedup), Blender-Skript-Generierung (Marker, Bernoulli, Viskositäts-
Schwelle, horizontale Strahlrichtung + Schwerkraft) und die Runden-Persistenz
(round.json-Roundtrip, Markierungen, Eltern-Video-Referenz auf die Altrunde).

Ausführen: ``python test_spraytest.py`` oder ``pytest test_spraytest.py``.
"""

import json
import os
import random
import shutil
import tempfile

import ema_spraytest as st


# ── Sampling ─────────────────────────────────────────────────────────────────
def test_round1_covers_ranges_and_anchors_default():
    rng = random.Random(42)
    kids = st.sample_round([], 10, 1, rng=rng)
    assert len(kids) == 10
    assert kids[0] == st.DEFAULT_PARAMS                      # Anker-Variante
    for k, p in st.SPRAY_PARAMS.items():
        vals = [c[k] for c in kids]
        assert all(p["lo"] - 1e-9 <= v <= p["hi"] + 1e-9 for v in vals)
        # breite Streuung: obere und untere Bereichshälfte beide besetzt
        mid = st._denorm(k, 0.5)
        assert any(v < mid for v in vals) and any(v > mid for v in vals), k


def test_mutation_stays_near_parents_and_in_range():
    rng = random.Random(7)
    parents = [dict(st.DEFAULT_PARAMS)]
    kids = st.sample_round(parents, 8, 2, rng=rng)
    assert len(kids) == 8
    for c in kids:
        for k, p in st.SPRAY_PARAMS.items():
            assert p["lo"] - 1e-9 <= c[k] <= p["hi"] + 1e-9
        # Runde 2, σ=0.25: Kinder liegen in der Nähe des Elters (normiert < ~3σ·√d)
        assert st._pdist(c, parents[0]) < 0.25 * 3 * (len(st.PARAM_ORDER) ** 0.5)


def test_sigma_shrinks_with_rounds():
    parents = [dict(st.DEFAULT_PARAMS)]
    d2, d9 = [], []
    for seed in range(12):
        d2 += [st._pdist(c, parents[0])
               for c in st.sample_round(parents, 6, 2, rng=random.Random(seed))]
        d9 += [st._pdist(c, parents[0])
               for c in st.sample_round(parents, 6, 9, rng=random.Random(seed))]
    # Runde 9 hat σ = 0.25·0.7⁷ ≈ 0.02 → deutlich engere Kinder als Runde 2
    assert sum(d9) / len(d9) < 0.5 * (sum(d2) / len(d2))


def test_dedup_and_log_params_positive():
    rng = random.Random(3)
    parents = [dict(st.DEFAULT_PARAMS), dict(st.DEFAULT_PARAMS)]  # identische Eltern
    kids = st.sample_round(parents, 6, 5, rng=rng)
    allv = parents + kids
    for i in range(len(allv)):
        for j in range(i + 1, len(allv)):
            if i >= len(parents) or j >= len(parents):           # Duplikat-Eltern erlaubt
                assert st._pdist(allv[i], allv[j]) >= st.DEDUP_DIST * 0.5
    for c in kids:
        assert c["surface_tension"] > 0 and c["viscosity"] > 0   # log-Raum bleibt positiv


def test_clean_params_clamps_and_fills():
    p = st._clean_params({"pressure_bar": 99, "viscosity": -5, "unbekannt": 1})
    assert p["pressure_bar"] == st.SPRAY_PARAMS["pressure_bar"]["hi"]
    assert p["viscosity"] == st.SPRAY_PARAMS["viscosity"]["lo"]
    assert p["jet_cone_deg"] == st.DEFAULT_PARAMS["jet_cone_deg"]
    assert "unbekannt" not in p


# ── Blender-Skript ───────────────────────────────────────────────────────────
def test_bench_script_content():
    code = st._bench_script()
    # Marker, die blender_runner parst
    for marker in ("OIL_STAGE:", "OIL_FRAMES:", "OIL_METRICS:", "OIL_DONE"):
        assert marker in code, marker
    # Bernoulli-Strahlgeschwindigkeit aus dem Druck (wie im Motor-Skript)
    assert "math.sqrt(2.0 * PRESSURE_BAR * 1e5 / RHO_OIL)" in code
    # Viskositätslöser nur über der Schwelle
    assert "if VISC > 0.02:" in code
    # HORIZONTAL sprühen: Strahl entlang +x, Schwerkraft −z
    assert '"velocity_coord", [JET_V, 0.0, 0.0]' in code
    assert "scene.gravity = (0.0, 0.0, -9.81)" in code
    # Sekundärpartikel BEWUSST AUS — in diesem Blender-4.2-Build kaputt (ohne
    # resumable Cache 0 Partikel, mit resumable domänenfüllender Positions-Müll;
    # beides real verifiziert). Tropfen kommen aus dem feinen Upres-Mesh.
    for flag in ("use_spray_particles", "use_foam_particles", "use_bubble_particles"):
        assert '"%s", False' % flag in code, flag
    # Realismus-Paket: feineres Flüssigkeitsmesh (Upres + kleinerer Partikelradius)
    # + glatte Stab-Kollision — das liefert die sichtbaren Einzeltropfen.
    assert '"mesh_particle_radius", 1.4' in code
    # Upres nur bei grober Domain — bei hoher Auflösung OOM-Gefahr (1024³-Mesh ⇒
    # >28 GB RSS, real vom Kernel gekillt); ab 192 rechnet das Mesh auf Sim-Auflösung
    assert '"mesh_scale", 2 if RES < 192 else 1' in code
    assert '"use_fractions", True' in code
    # Render-Auflösung aus der cfg (Beauty rendert größer)
    assert "RENDER_PX" in code
    # Frames im _encode_video-Namensschema
    assert 'frame_%04d.png' in code
    # "Nur das Spray": Stäbe optional (Default aus), Kamera-Nahaufnahme ohne Stäbe
    assert 'CFG.get("show_rods", False)' in code
    assert "if SHOW_RODS else []" in code
    assert "if SHOW_RODS:" in code                     # Kamera-Zweig (Übersicht vs. nah)
    # Leer-Bake-Wächter: leerer Fluid-Frame blendet die Domain aus (sonst „großer Quader statt Spray")
    assert "dom.hide_render = (n_verts == 0)" in code, "Leer-Domain-Wächter je Frame fehlt"
    assert "_liquid_total == 0" in code and "KEIN Öl erzeugt" in code, "Leer-Bake-Warnung fehlt"
    assert "_jet_cells" in code and "Strahl unter-aufgelöst" in code, "Unter-Auflösungs-Wächter fehlt"
    assert '"jet_underres"' in code, "jet_underres-Kennwert fehlt"


def test_spray_param_physical_limits():
    """Anlagen-Grenzen (Nutzer-Vorgabe): Druck 0,1–3 bar, Düsen-Ø 0,5–3,0 mm —
    Sampling, Mutation und Klemmung dürfen sie nie verlassen."""
    assert st.SPRAY_PARAMS["pressure_bar"]["lo"] == 0.1
    assert st.SPRAY_PARAMS["pressure_bar"]["hi"] == 3.0
    assert st.SPRAY_PARAMS["nozzle_d_mm"]["lo"] == 0.5
    assert st.SPRAY_PARAMS["nozzle_d_mm"]["hi"] == 3.0
    p = st._clean_params({"pressure_bar": 8.0, "nozzle_d_mm": 5.0})
    assert p["pressure_bar"] == 3.0 and p["nozzle_d_mm"] == 3.0


# ── Runden-Persistenz ────────────────────────────────────────────────────────
def _tmp_root():
    d = tempfile.mkdtemp(prefix="spraytest_")
    old = st.SPRAYTEST_ROOT
    st.SPRAYTEST_ROOT = d
    return d, old


def test_round_store_roundtrip():
    d, old = _tmp_root()
    try:
        data = {"rid": "r001_20260714_120000", "round_no": 1, "ts": "2026-07-14 12:00:00",
                "quality": "normal", "n": 2, "aborted": False, "marked": [],
                "variants": [{"id": "v0", "params": dict(st.DEFAULT_PARAMS),
                              "source": "child", "ok": True}]}
        st._write_round(data["rid"], data)
        assert st.load_round(data["rid"])["round_no"] == 1
        lst = st.list_rounds()
        assert len(lst) == 1 and lst[0]["rid"] == data["rid"]
        # Markierungen: nur bekannte IDs werden übernommen
        upd = st.set_marked(data["rid"], ["v0", "vX"])
        assert upd["marked"] == ["v0"]
        assert st.load_round(data["rid"])["marked"] == ["v0"]
        assert st.delete_round(data["rid"]) is True
        assert st.load_round(data["rid"]) is None
    finally:
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_list_rounds_sorts_by_timestamp_not_rid():
    """Eine NEUE Runde 1 nach einer alten Runde 2 muss oben stehen (UI lädt rounds[0])."""
    d, old = _tmp_root()
    try:
        st._write_round("r002_20260714_111724", {"rid": "r002_20260714_111724",
                        "round_no": 2, "ts": "2026-07-14 11:39:26", "variants": [], "marked": []})
        st._write_round("r001_20260714_122626", {"rid": "r001_20260714_122626",
                        "round_no": 1, "ts": "2026-07-14 12:30:11", "variants": [], "marked": []})
        lst = st.list_rounds()
        assert [r["rid"] for r in lst] == ["r001_20260714_122626", "r002_20260714_111724"]
    finally:
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_parent_video_resolves_to_old_round():
    d, old = _tmp_root()
    try:
        # Altrunde mit echtem (leerem) Video-File
        old_rid = "r001_20260714_120000"
        vdir = os.path.join(st._rounds_dir(), old_rid, "v2", "frames")
        os.makedirs(vdir)
        mp4 = os.path.join(vdir, "anim.mp4")
        open(mp4, "wb").close()
        st._write_round(old_rid, {"rid": old_rid, "round_no": 1, "variants": [
            {"id": "v2", "params": dict(st.DEFAULT_PARAMS), "source": "child", "ok": True}],
            "marked": []})
        # Neue Runde referenziert v2 als Elter
        new_rid = "r002_20260714_130000"
        st._write_round(new_rid, {"rid": new_rid, "round_no": 2, "variants": [
            {"id": "p0", "params": dict(st.DEFAULT_PARAMS), "source": "parent",
             "src_round": old_rid, "src_vid": "v2", "ok": True}], "marked": []})
        assert st.video_path(new_rid, "p0") == mp4          # Referenz aufgelöst
        assert st.video_path(old_rid, "v2") == mp4
        assert st.video_path(new_rid, "gibtsnicht") is None
    finally:
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_favorites_store_roundtrip():
    """💾 Spray-Favoriten: speichern (Params geklemmt, Name gekürzt), listen, löschen."""
    d, old = _tmp_root()
    try:
        fav = st.save_favorite({"name": "  Mein Strahl  ", "params": {"pressure_bar": 99},
                                "sim": {"resolution": 9999, "frames": 3, "slowmo": 500},
                                "src": {"rid": "r001_x", "vid": "v2"}})
        assert fav["name"] == "Mein Strahl"
        assert fav["params"]["pressure_bar"] == st.SPRAY_PARAMS["pressure_bar"]["hi"]
        assert fav["params"]["viscosity"] == st.DEFAULT_PARAMS["viscosity"]  # aufgefüllt
        assert fav["sim"] == {"resolution": 512, "frames": 24, "slowmo": 50.0}
        assert fav["src"] == {"rid": "r001_x", "vid": "v2"}
        fav2 = st.save_favorite({"name": "", "params": dict(st.DEFAULT_PARAMS)})
        assert fav2["name"] == "Spray"                       # Default-Name
        favs = st.list_favorites()
        assert [f["id"] for f in favs] == [fav2["id"], fav["id"]]  # neueste zuerst
        assert st.delete_favorite(fav["id"]) is True
        assert st.delete_favorite(fav["id"]) is False
        assert [f["id"] for f in st.list_favorites()] == [fav2["id"]]
    finally:
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_run_round_with_fake_bake():
    """Kompletter run_round-Durchlauf mit gefälschtem Blender (kein echter Bake):
    Kinder + Eltern landen in round.json, Abbruch nach der 2. Variante behält die Teilrunde."""
    d, old = _tmp_root()
    orig = st._bake_variant
    calls = {"n": 0, "overrides": None}

    def fake_bake(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10,
                  overrides=None):
        calls["n"] += 1
        calls["overrides"] = overrides
        os.makedirs(os.path.join(vdir, "frames"), exist_ok=True)
        open(os.path.join(vdir, "frames", "anim.mp4"), "wb").close()
        return {"ok": True, "aborted": False, "error": None,
                "metrics": {"droplets_peak": 5,
                            "series": [{"frame": 1, "n_islands": 2, "n_snd": 3}]}}

    st._bake_variant = fake_bake
    try:
        spec = {"round_no": 2, "n": 4, "quality": "schnell",
                "parents": [{"params": dict(st.DEFAULT_PARAMS),
                             "src_round": "r001_x", "src_vid": "v1"}]}
        data = st.run_round(spec)
        assert calls["n"] == 4
        assert data["round_no"] == 2 and data["quality"] == "schnell"
        assert data["resolution"] == st.QUALITY_RES["schnell"]     # kein freies res ⇒ Preset
        vs = data["variants"]
        assert [v["source"] for v in vs] == ["parent"] + ["child"] * 4
        assert vs[0]["src_round"] == "r001_x" and vs[0]["src_vid"] == "v1"
        assert all(v["ok"] for v in vs)
        saved = st.load_round(data["rid"])
        assert saved["variants"][1]["droplets_peak"] == 5
        assert saved["variants"][1]["series"][0]["n_snd"] == 3     # 📊 Serie persistiert

        # Abbruch: cancel nach 2 Bakes → Teilrunde mit 2 Kindern, aborted=True
        calls["n"] = 0
        data2 = st.run_round({"round_no": 1, "n": 6, "quality": "normal"},
                             cancel_cb=lambda: calls["n"] >= 2)
        kids = [v for v in data2["variants"] if v["source"] == "child"]
        assert data2["aborted"] is True and len(kids) == 2
    finally:
        st._bake_variant = orig
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_run_round_clamps_resolution_frames_slowmo():
    """Freie Auflösung/Frames/Zeitlupe werden geklemmt und an den Bake durchgereicht."""
    d, old = _tmp_root()
    orig = st._bake_variant
    seen = {}

    def fake_bake(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10,
                  overrides=None):
        seen.update(overrides or {})
        os.makedirs(os.path.join(vdir, "frames"), exist_ok=True)
        open(os.path.join(vdir, "frames", "anim.mp4"), "wb").close()
        return {"ok": True, "aborted": False, "error": None, "metrics": {}}

    st._bake_variant = fake_bake
    try:
        data = st.run_round({"round_no": 1, "n": 4, "quality": "schnell",
                             "resolution": 9999, "frames": 3, "slowmo": 500})
        assert data["resolution"] == st.RES_RANGE[1] == 512        # geklemmt
        assert data["frames"] == st.FRAMES_RANGE[0] == 24
        assert data["slowmo"] == st.SLOWMO_RANGE[1] == 50
        assert seen["resolution"] == 512 and seen["frames"] == 24
        assert abs(seen["time_scale"] - 1.0 / 50) < 1e-9
        assert data["show_rods"] is False and seen["show_rods"] is False  # Default: nur Spray
        data2 = st.run_round({"round_no": 1, "n": 1, "show_rods": True})
        assert data2["show_rods"] is True and seen["show_rods"] is True
    finally:
        st._bake_variant = orig
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_run_round_single_exact():
    """🎯 Einzel-Strahl: n=1 + exact_params bäckt genau EINE Variante mit exakt
    diesen (geklemmten) Werten; n=1 ohne exact_params = der Default-Anker."""
    d, old = _tmp_root()
    orig = st._bake_variant

    def fake_bake(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10,
                  overrides=None):
        os.makedirs(os.path.join(vdir, "frames"), exist_ok=True)
        open(os.path.join(vdir, "frames", "anim.mp4"), "wb").close()
        return {"ok": True, "aborted": False, "error": None, "metrics": {}}

    st._bake_variant = fake_bake
    try:
        data = st.run_round({"round_no": 1, "n": 1,
                             "exact_params": {"pressure_bar": 2.5, "jet_cone_deg": 99}})
        kids = [v for v in data["variants"] if v["source"] == "child"]
        assert len(kids) == 1
        assert kids[0]["params"]["pressure_bar"] == 2.5
        assert kids[0]["params"]["jet_cone_deg"] == st.SPRAY_PARAMS["jet_cone_deg"]["hi"]
        assert kids[0]["params"]["viscosity"] == st.DEFAULT_PARAMS["viscosity"]
        data2 = st.run_round({"round_no": 1, "n": 1})
        kids2 = [v for v in data2["variants"] if v["source"] == "child"]
        assert len(kids2) == 1 and kids2[0]["params"] == st.DEFAULT_PARAMS
    finally:
        st._bake_variant = orig
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


def test_beauty_video_path_and_run_beauty():
    """✨: video_path(beauty=True) findet das Beauty-Video (lokal + über Eltern-Referenz);
    run_beauty bäckt mit Overrides und markiert die Variante in round.json."""
    d, old = _tmp_root()
    orig = st._bake_variant
    seen = {}

    def fake_bake(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10,
                  overrides=None):
        seen["vdir"] = vdir
        seen.update(overrides or {})
        os.makedirs(os.path.join(vdir, "frames"), exist_ok=True)
        open(os.path.join(vdir, "frames", "anim.mp4"), "wb").close()
        return {"ok": True, "aborted": False, "error": None, "metrics": {}}

    st._bake_variant = fake_bake
    try:
        rid = "r001_20260714_120000"
        st._write_round(rid, {"rid": rid, "round_no": 1, "quality": "schnell",
                              "slowmo": 3.0, "marked": [], "variants": [
                              {"id": "v0", "params": dict(st.DEFAULT_PARAMS),
                               "source": "child", "ok": True}]})
        assert st.video_path(rid, "v0", beauty=True) is None       # noch kein Beauty
        out = st.run_beauty(rid, "v0", {"resolution": 9999, "frames": 60})
        assert out["ok"] and out["beauty"] and out["resolution"] == 512
        assert seen["vdir"].endswith(os.path.join(rid, "v0", "beauty"))
        assert seen["render_px"] == st.BEAUTY_RENDER_PX
        bp = st.video_path(rid, "v0", beauty=True)
        assert bp and bp.endswith(os.path.join("v0", "beauty", "frames", "anim.mp4"))
        assert st.load_round(rid)["variants"][0]["beauty"] is True
        # Eltern-Referenz: neue Runde zeigt mit beauty=True auf das Beauty der Altrunde
        rid2 = "r002_20260714_130000"
        st._write_round(rid2, {"rid": rid2, "round_no": 2, "marked": [], "variants": [
            {"id": "p0", "params": dict(st.DEFAULT_PARAMS), "source": "parent",
             "src_round": rid, "src_vid": "v0", "ok": True}]})
        assert st.video_path(rid2, "p0", beauty=True) == bp
        # Unbekannte Runde/Variante
        assert st.run_beauty("gibtsnicht", "v0")["ok"] is False
        assert st.run_beauty(rid, "vX")["ok"] is False
    finally:
        st._bake_variant = orig
        st.SPRAYTEST_ROOT = old
        shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    import sys
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("✔ %s" % name)
            except AssertionError as e:
                fails += 1
                print("✘ %s: %s" % (name, e))
    print("—" * 40)
    print("OK" if not fails else "%d FEHLER" % fails)
    sys.exit(1 if fails else 0)
