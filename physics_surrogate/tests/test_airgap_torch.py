"""Die Torch-Spiegelung von ``B_r(θ)`` gegen die echte Numpy-Fassung.

Braucht Torch, läuft also nur im Surrogat-venv:

    physics_surrogate/.venv/bin/python physics_surrogate/tests/test_airgap_torch.py

Das ist der Test, der den Verlustterm ehrlich hält: driftet die Spiegelung von
`ema_analysis._sample_airgap` ab, optimiert das Training eine Größe, die niemand misst —
und die Abnahme in `evaluate.py` (die die Numpy-Fassung benutzt) würde es erst Stunden
später merken.
"""

import os
import sys

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "data")))
sys.path.insert(0, os.path.normpath(os.path.join(_HERE, "..", "train")))

import encode2d            # noqa: E402
import ema_analysis as ea  # noqa: E402
from airgap_torch import AirgapBr, circ_smooth, smoothing_window  # noqa: E402

GEOM = {
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
    "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3,
    "magShape": "v", "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6,
    "magDist": 2, "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "nAx": 1, "nCirc": 1, "magTangLen": 0, "magAngle2": 90, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
}
N = 256


def test_circ_smooth_matches_numpy():
    rng = np.random.default_rng(0)
    sig = rng.normal(size=720)
    for win in (1, 3, 5, 9):
        ref = ea._circ_smooth(sig.copy(), win)
        got = circ_smooth(torch.from_numpy(sig)[None], win)[0].numpy()
        assert np.allclose(got, ref, atol=1e-12), f"win={win}: max {np.abs(got-ref).max():.2e}"
    assert smoothing_window() == 3
    print("✓ circ_smooth deckt sich mit _circ_smooth (win = 1/3/5/9)")


def test_br_matches_sample_airgap():
    """Der eigentliche Vertrag — auf echten Feldern, nicht auf Rauschen."""
    worst = 0.0
    for shape, statorID in (("v", 190.0), ("spm", 191.6), ("pmasynrm", 194.6)):
        geom = dict(GEOM, magShape=shape, statorID=statorID)
        mu, j, sc, ctr = ea._rasterise(geom, N)
        try:
            a = ea._solve_fdm(mu, j)
        finally:
            ea.clear_lu_cache()
        br_ref, _bt, _th, _bx, _by = ea._sample_airgap(a, geom, sc, ctr, N)

        r_ev = encode2d.ring_radius_px(geom, N)
        assert abs(r_ev - ((geom["statorID"] / 2) * sc - 1.0)) < 1e-9, \
            "ring_radius_px weicht von der sc/ctr-Rechnung in _rasterise ab"

        sampler = AirgapBr(N).double()
        got = sampler(torch.from_numpy(a)[None, None],
                      torch.tensor([r_ev], dtype=torch.float64))[0].numpy()
        err = np.max(np.abs(got - br_ref)) / max(np.max(np.abs(br_ref)), 1e-30)
        worst = max(worst, err)
        assert err < 1e-9, f"{shape}: rel. Abweichung {err:.2e} zu _sample_airgap"
    print(f"✓ B_r-Spiegelung deckt sich mit _sample_airgap (3 Topologien, "
          f"schlechtester rel. Fehler {worst:.1e})")


def test_gradient_flows_and_batches():
    """Differenzierbar und batchfähig mit unterschiedlichen Ringradien."""
    a = torch.zeros(3, 1, 64, 64, requires_grad=True)
    r = torch.tensor([20.0, 24.0, 28.0])
    br = AirgapBr(64)(a, r)
    assert br.shape == (3, 720)
    br.pow(2).mean().backward()
    assert a.grad is not None and torch.isfinite(a.grad).all()

    # Verschiedene Radien müssen verschiedene Kurven ergeben (kein stiller Broadcast).
    a2 = torch.randn(1, 1, 64, 64)
    curves = [AirgapBr(64)(a2, torch.tensor([rr])) for rr in (18.0, 26.0)]
    assert not torch.allclose(curves[0], curves[1])
    print("✓ differenzierbar, batchfähig, Ringradius wirkt je Sample")


def test_scale_invariance_of_relative_error():
    """α kürzt sich: normiertes A ergibt dieselbe *relative* Kurve wie rohes A."""
    a = torch.randn(1, 1, 128, 128)
    r = torch.tensor([50.0])
    s = AirgapBr(128)
    b1, b2 = s(a, r), s(a * 7.3, r)
    # Normvergleich statt allclose: B_r wechselt das Vorzeichen, einzelne Einträge
    # liegen bei ~0 und würden an atol scheitern, ohne dass etwas falsch wäre.
    err = (b2 - 7.3 * b1).norm() / (7.3 * b1).norm()
    assert err < 1e-5, f"rel. Abweichung {err:.2e}"
    print("✓ B_r ist linear in A — der Verlustterm sieht α nicht")


if __name__ == "__main__":
    print("Luftspalt-Spiegelung (Stufe 1)\n" + "=" * 50)
    test_circ_smooth_matches_numpy()
    test_br_matches_sample_airgap()
    test_gradient_flows_and_batches()
    test_scale_invariance_of_relative_error()
    print("\nALLE LUFTSPALT-TESTS BESTANDEN ✅")
