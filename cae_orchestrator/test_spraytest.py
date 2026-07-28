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
    # Sekundärpartikel (Tröpfchen) immer an
    for flag in ("use_spray_particles", "use_foam_particles", "use_bubble_particles"):
        assert '"%s", True' % flag in code, flag
    # Frames im _encode_video-Namensschema
    assert 'frame_%04d.png' in code


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


def test_run_round_with_fake_bake():
    """Kompletter run_round-Durchlauf mit gefälschtem Blender (kein echter Bake):
    Kinder + Eltern landen in round.json, Abbruch nach der 2. Variante behält die Teilrunde."""
    d, old = _tmp_root()
    orig = st._bake_variant
    calls = {"n": 0}

    def fake_bake(params, vdir, quality, progress_cb=None, base_pct=0, span_pct=10):
        calls["n"] += 1
        os.makedirs(os.path.join(vdir, "frames"), exist_ok=True)
        open(os.path.join(vdir, "frames", "anim.mp4"), "wb").close()
        return {"ok": True, "aborted": False, "error": None,
                "metrics": {"droplets_peak": 5}}

    st._bake_variant = fake_bake
    try:
        spec = {"round_no": 2, "n": 4, "quality": "schnell",
                "parents": [{"params": dict(st.DEFAULT_PARAMS),
                             "src_round": "r001_x", "src_vid": "v1"}]}
        data = st.run_round(spec)
        assert calls["n"] == 4
        assert data["round_no"] == 2 and data["quality"] == "schnell"
        vs = data["variants"]
        assert [v["source"] for v in vs] == ["parent"] + ["child"] * 4
        assert vs[0]["src_round"] == "r001_x" and vs[0]["src_vid"] == "v1"
        assert all(v["ok"] for v in vs)
        assert st.load_round(data["rid"])["variants"][1]["droplets_peak"] == 5

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
