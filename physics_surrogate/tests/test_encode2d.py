"""Tests für Domäne + Encoder der Stufe 1 — OHNE GPU, ohne Torch, ohne Datensatz.

Läuft in BEIDEN venvs (Orchestrator wie Surrogat), weil nur numpy/scipy und der
Orchestrator-Import gebraucht werden:

    cae_orchestrator/venv/bin/python physics_surrogate/tests/test_encode2d.py
    physics_surrogate/.venv/bin/python physics_surrogate/tests/test_encode2d.py

Der wichtigste Punkt hier ist der **Vertrag zwischen Erzeuger und Dienst**: beide
encodieren mit demselben Code und prüfen gegen dieselbe Gültigkeitsgrenze. Driftet das
auseinander, sagt das Modell im Betrieb etwas anderes voraus als im Training gelernt —
und niemand merkt es.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "data")))

import domain            # noqa: E402
import encode2d          # noqa: E402
import ema_analysis as ea  # noqa: E402

# Basismaschine des Datensatzes (identisch zu gen_fdm_dataset.BASE_GEOM).
GEOM = {
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
    "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3,
    "magShape": "v", "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6,
    "magDist": 2, "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "nAx": 1, "nCirc": 1, "magTangLen": 0, "magAngle2": 90, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
}
AXIAL = 120.0
N = 128          # klein — hier geht es um Verträge, nicht um Feldgenauigkeit


def test_masks_encode_mu_exactly():
    """Die drei Materialmasken codieren µ vollständig — verlustfrei umkehrbar."""
    for shape in ("v", "spm", "spoke"):
        geom = dict(GEOM, magShape=shape)
        mat, j_mag, j_stat, _maps = encode2d.rasterise(geom, N)
        mu_ref, _j, _sc, _ctr = ea._rasterise(geom, N)
        assert np.array_equal(encode2d.mu_from_mat(mat), mu_ref), \
            f"{shape}: mu_from_mat(mat) weicht von _rasterise ab"
    print("✓ Materialmasken codieren µ exakt (3 Topologien)")


def test_source_split_is_exact():
    """J_magnet + J_stator == J — dieselbe Aufspaltung wie run_em_analysis:997-1004."""
    geom = dict(GEOM)
    iq, id_ = 150.0, -60.0
    mat, j_mag, j_stat, _m = encode2d.rasterise(geom, N, iq=iq, id_=id_)
    _mu, j_full, _sc, _c = ea._rasterise(geom, N, iq=iq, id_=id_)
    assert np.allclose(j_mag + j_stat, j_full, atol=1e-5)
    # Im Leerlauf gibt es keine Statorquelle.
    _m2, jm0, js0, _m3 = encode2d.rasterise(geom, N)
    assert np.max(np.abs(js0)) == 0.0 and np.max(np.abs(jm0)) > 0
    print("✓ Quellenaufspaltung exakt, Leerlauf ohne Statorquelle")


def test_channels_are_normalised_and_onehot():
    geom = dict(GEOM)
    mat, j_mag, _js, _m = encode2d.rasterise(geom, N)
    x, alpha = encode2d.encode(mat, j_mag)
    assert x.shape == (encode2d.N_CHANNELS, N, N) and x.dtype == np.float32
    assert np.array_equal(x[0] + x[1] + x[2], np.ones((N, N), np.float32)), \
        "Masken sind kein One-Hot"
    assert abs(float(np.max(np.abs(x[3]))) - 1.0) < 1e-6, "Quellkanal nicht auf 1 normiert"
    assert alpha > 0
    print(f"✓ Kanäle {encode2d.CHANNEL_NAMES}: One-Hot + Quelle auf 1 normiert")


def test_scale_equivariance():
    """Der Kern des Ansatzes: skaliert man die Quelle, skaliert das Feld exakt mit.

    Genau deshalb dürfen Ein- und Ausgang mit demselben α normiert werden — die
    Amplitudenstreuung zwischen Samples fällt exakt heraus, nicht näherungsweise.
    """
    geom = dict(GEOM)
    mu, j, _sc, _c = ea._rasterise(geom, N)
    try:
        a1 = ea._solve_fdm(mu, j)
        a2 = ea._solve_fdm(mu, j * 3.7)
    finally:
        ea.clear_lu_cache()
    assert np.allclose(a2, a1 * 3.7, rtol=1e-6), "Löser ist nicht linear in J"

    x1, al1 = encode2d.encode(np.zeros_like(mu, np.uint8), j)
    x2, al2 = encode2d.encode(np.zeros_like(mu, np.uint8), j * 3.7)
    assert np.allclose(x1[3], x2[3], atol=1e-6), "normierter Quellkanal hängt von der Amplitude ab"
    assert np.allclose(encode2d.encode_target(a1, al1),
                       encode2d.encode_target(a2, al2), rtol=1e-5), \
        "normierte Zielgröße hängt von der Amplitude ab"
    print("✓ Skalen-Äquivarianz: J→3,7·J ⇒ A→3,7·A, normierte Größen unverändert")


def test_encode_decode_roundtrip():
    geom = dict(GEOM)
    mu, j, _sc, _c = ea._rasterise(geom, N)
    try:
        a = ea._solve_fdm(mu, j)
    finally:
        ea.clear_lu_cache()
    _x, alpha = encode2d.encode(np.zeros_like(mu, np.uint8), j)
    back = encode2d.decode_target(encode2d.encode_target(a, alpha), alpha)
    assert np.allclose(back, a, rtol=1e-5)
    print("✓ encode_target/decode_target ist ein Rundlauf")


def test_pattern_target_is_amplitude_free():
    """Das Trainingsziel trägt keine Amplitude — und braucht sie auch nicht.

    Der zweite Teil ist der eigentliche Beweis: die auf ihren Spitzenwert bezogene
    Luftspaltkurve ist gegen die Normierung invariant. Genau diese Kurve benutzt
    `run_em_analysis:1053` (`sf = B_analytisch/max|Br|`), also liefert das Muster allein
    dasselbe Feld in Tesla wie die volle Lösung.
    """
    mu, j, sc, ctr = ea._rasterise(GEOM, N)
    try:
        a = ea._solve_fdm(mu, j)
    finally:
        ea.clear_lu_cache()
    p1, p2 = encode2d.pattern(a), encode2d.pattern(a * 42.0)
    assert np.allclose(p1, p2, rtol=1e-5), "pattern() hängt noch an der Amplitude"
    assert abs(float(p1.std()) - 1.0) < 1e-5

    br_a, _bt, _th, _bx, _by = ea._sample_airgap(a, GEOM, sc, ctr, N)
    br_p, _bt, _th, _bx, _by = ea._sample_airgap(
        np.asarray(p1, np.float64), GEOM, sc, ctr, N)
    assert np.allclose(br_a / np.max(np.abs(br_a)), br_p / np.max(np.abs(br_p)),
                       atol=1e-6), "spitzenwertbezogene Br-Kurve überlebt die Normierung nicht"
    print("✓ pattern(): amplitudenfrei, spitzenwertbezogenes Br unverändert")


def test_effective_bounds_are_tighter_than_free_params():
    """Die Sampling-Box muss auf das Baubare geschnitten sein (sonst ~4 % Annahme)."""
    box = domain.effective_bounds(GEOM, exclude=domain.STAGE1_INERT)
    for key in domain.STAGE1_INERT:
        assert key not in box, f"{key} wirkt nicht aufs 2D-Feld, gehört nicht in die Box"
    wall = (GEOM["statorOD"] - GEOM["statorID"]) / 2
    assert box["slotDepth"][1] < wall, "slotDepth-Obergrenze lässt kein Rückenjoch übrig"
    assert box["slotDepth"][1] < domain.FREE_PARAMS["slotDepth"]["hi"]
    assert box["p"][1] * 2 * domain.MIN_SLOTS_PER_POLE <= GEOM["slots"]
    assert box["magThick"][1] < domain.FREE_PARAMS["magThick"]["hi"]
    for key, (lo, hi) in box.items():
        assert lo < hi, f"{key}: leeres Intervall [{lo}, {hi}]"
    print(f"✓ effektive Box geschnitten: slotDepth≤{box['slotDepth'][1]:.1f} mm, "
          f"p≤{box['p'][1]:.0f}, magThick≤{box['magThick'][1]:.1f} mm")


def test_feasibility_rejects_impossible_geometry():
    assert not domain.feasibility_problems(GEOM, AXIAL), \
        "die Basismaschine muss baubar sein"
    cases = {
        "Nut durch das Joch": dict(GEOM, slotDepth=140),
        "mehr Pole als Nuten": dict(GEOM, p=35),
        "Magnete dicker als der Rotor": dict(GEOM, magThick=55),
        "Rotor größer als die Bohrung": dict(GEOM, rotorOD=195),
        "keine Drehstromwicklung": dict(GEOM, slots=55),
    }
    for name, geom in cases.items():
        assert domain.feasibility_problems(geom, AXIAL), f"'{name}' wurde nicht erkannt"
    print(f"✓ Machbarkeitsfilter erkennt {len(cases)} unmögliche Geometrien")


def test_bounds_violations_flag_out_of_domain():
    box = domain.effective_bounds(GEOM, exclude=domain.STAGE1_INERT)
    assert not domain.bounds_violations(GEOM, AXIAL, GEOM, box), \
        "die Basismaschine liegt im trainierten Bereich"
    # Luftspalt weit außerhalb → muss auffallen (sonst extrapoliert der Dienst still)
    far = dict(GEOM, statorID=GEOM["rotorOD"] + 2 * 12.0)
    assert domain.bounds_violations(far, AXIAL, GEOM, box)
    # Andere Basismaschine → nicht mittrainiert
    other = dict(GEOM, statorOD=400)
    assert domain.bounds_violations(other, AXIAL, GEOM, box)
    # Designer-Geometrie ist in v1 nicht abgedeckt
    assert domain.bounds_violations(dict(GEOM, magShape="custom"), AXIAL, GEOM, box)
    print("✓ Bereichsprüfung meldet Luftspalt, fremde Basismaschine und custom-Geometrie")


def test_raster_problems_catch_vanishing_magnets():
    _mat, _jm, _js, maps = encode2d.rasterise(GEOM, N)
    assert not domain.raster_problems(maps, N), "Basismaschine rastert sauber"
    empty = {"magnet": np.zeros((N, N), bool), "iron": maps["iron"],
             "Mx": np.zeros((N, N), np.float32), "My": np.zeros((N, N), np.float32)}
    assert domain.raster_problems(empty, N), "verschwundene Magnete nicht erkannt"
    print("✓ Rasterprüfung erkennt verschwundene Magnete")


if __name__ == "__main__":
    print("Encoder-/Domänen-Tests (Stufe 1)\n" + "=" * 50)
    test_masks_encode_mu_exactly()
    test_source_split_is_exact()
    test_channels_are_normalised_and_onehot()
    test_scale_equivariance()
    test_encode_decode_roundtrip()
    test_pattern_target_is_amplitude_free()
    test_effective_bounds_are_tighter_than_free_params()
    test_feasibility_rejects_impossible_geometry()
    test_bounds_violations_flag_out_of_domain()
    test_raster_problems_catch_vanishing_magnets()
    print("\nALLE ENCODER-TESTS BESTANDEN ✅")
