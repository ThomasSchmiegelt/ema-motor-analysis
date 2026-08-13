"""Die Augmentierung muss eine EXAKTE Symmetrie sein, sonst trainiert sie auf Fehler.

Der Test rechnet deshalb gegen den echten Löser nach — nicht gegen eine zweite
Torch-Formulierung derselben Annahme. Zusätzlich wird die Stelle geprüft, an der es
still kaputtging: der Luftspaltring bei ``n/2`` gegen die D4-Achse bei ``(n−1)/2``.

    physics_surrogate/.venv/bin/python physics_surrogate/tests/test_augment.py
"""

import os
import sys

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
for _p in (os.path.join(_ROOT, "data"), os.path.join(_ROOT, "train")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import augment as A          # noqa: E402
from airgap_torch import AirgapBr   # noqa: E402
from domain import _add_orchestrator_to_path  # noqa: E402,F401  (setzt sys.path)

ELEMENTS = [(k, m) for m in (False, True) for k in range(4)]


def _name(k: int, mirror: bool) -> str:
    return f"rot{90 * k}{' gespiegelt' if mirror else ''}"


def _machine(n: int = 128, seed: int = 0):
    """Ein auf ``n/2`` zentriertes Spielzeug-„Rotor+Stator" mit Quelle.

    Die Luftpolsterung entspricht der des echten Encoders (`AIR_DOMAIN_FACTOR = 1.25`,
    Material bei N=512 auf 52…460): daran hängt, wie weit `A` bis zum Dirichlet-Rand
    abgeklungen ist — und damit der Restfehler des 1-px-Rückschubs.
    """
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:n, 0:n].astype(np.float64)
    r = np.hypot(yy - n / 2, xx - n / 2)
    th = np.arctan2(yy - n / 2, xx - n / 2)
    mu = np.ones((n, n), np.float64)
    mu[r < 0.21 * n] = 500.0                            # Rotoreisen
    mu[(r > 0.28 * n) & (r < 0.40 * n)] = 500.0         # Statoreisen
    j = np.zeros((n, n), np.float64)
    band = (r > 0.29 * n) & (r < 0.38 * n)
    j[band] = np.cos(4 * th[band]) * rng.uniform(0.5, 1.5)
    return mu, j.astype(np.float32)


def _np_d4(a: np.ndarray, k: int, mirror: bool) -> np.ndarray:
    """Numpy-Gegenstück zu `augment.d4` — bewusst getrennt formuliert."""
    out = a
    if mirror:
        out = np.roll(out[:, ::-1], 1, axis=-1)
    if k:
        out = np.rot90(out, k)
        sh = A._ROLL_AFTER_ROT[k]
        out = np.roll(np.roll(out, sh[0], -2), sh[1], -1)
    return np.ascontiguousarray(out)


def test_d4_ist_loesersymmetrie():
    """``_solve_fdm(g·µ, g·J)`` muss ``g·_solve_fdm(µ, J)`` sein.

    Gemessen wird im **relativen L2** — das ist die Größe, die der Verlust benutzt, und
    der Rückschub lässt am Rand bewusst eine Zeile umlaufen (s. `augment`-Docstring).
    Die Transposition (`mrot90`) kommt ohne Rückschub aus und muss deshalb auf
    Maschinengenauigkeit stimmen; sie trennt „Gruppenwirkung richtig" von „Rückschub
    näherungsweise".
    """
    import ema_analysis as ea

    mu, j = _machine()
    try:
        a = ea._solve_fdm(mu, j)
        norm = np.linalg.norm(a)
        for k, mirror in ELEMENTS:
            got = ea._solve_fdm(_np_d4(mu, k, mirror), _np_d4(j, k, mirror))
            err = np.linalg.norm(got - _np_d4(a, k, mirror)) / norm
            limit = 1e-12 if (k, mirror) in ((0, False), (1, True)) else 3e-3
            assert err < limit, f"{_name(k, mirror)}: {err:.2e} (Grenze {limit:.0e})"
    finally:
        ea.clear_lu_cache()
    print("✓ alle 8 D4-Elemente sind Symmetrien des FDM-Operators "
          "(Transposition exakt, Rest < 3e-3 rel. L2)")


def test_torch_und_numpy_dieselbe_abbildung():
    a = np.arange(64 * 64, dtype=np.float32).reshape(64, 64)
    for k, mirror in ELEMENTS:
        got = A.d4(torch.from_numpy(a)[None, None], k, mirror)[0, 0].numpy()
        assert np.array_equal(got, _np_d4(a, k, mirror)), _name(k, mirror)
    print("✓ Torch- und Numpy-Fassung von D4 sind bitgleich")


def test_luftspaltring_bleibt_unberuehrt():
    """Ohne den 1-px-Rückschub geriete der Ring in die Eisenkante (gemessen bis 20×)."""
    import ema_analysis as ea

    n = 128
    mu, j = _machine(n)
    try:
        a = ea._solve_fdm(mu, j)
    finally:
        ea.clear_lu_cache()
    t = torch.from_numpy(a.astype(np.float32))[None, None]
    ag = AirgapBr(n)
    r_ev = torch.tensor([0.26 * n], dtype=torch.float32)
    b0 = float(ag(t, r_ev).abs().max())
    for k, mirror in ELEMENTS:
        b1 = float(ag(A.d4(t, k, mirror), r_ev).abs().max())
        assert abs(b1 / b0 - 1.0) < 1e-5, \
            f"{_name(k, mirror)}: max|Br| um Faktor {b1 / b0:.3f} verschoben"
    print("✓ der Luftspaltring bei n/2 überlebt alle 8 Abbildungen")


def test_vorzeichen_nur_auf_quellkanaelen():
    """Material-One-Hots dürfen nie negativ werden, Quelle und Ziel gemeinsam kippen."""
    x = torch.rand(8, 4, 32, 32)
    y = torch.rand(8, 1, 32, 32)
    gen = torch.Generator().manual_seed(3)
    flipped = total = 0
    for _ in range(40):
        xa, ya = A.augment(x, y, gen)
        assert (xa[:, :A.FIRST_SIGNED_CHANNEL] >= 0).all()
        # je Sample: Quellkanal und Ziel tragen dasselbe Vorzeichen
        s_src = torch.sign(xa[:, 3].flatten(1).sum(1))
        s_tgt = torch.sign(ya.flatten(1).sum(1))
        assert torch.equal(s_src, s_tgt)
        flipped += int((s_tgt < 0).sum())
        total += s_tgt.numel()
    # je Sample gezogen, also grob die Hälfte — nie und immer wären beide ein Fehler
    assert 0.35 < flipped / total < 0.65, f"{flipped}/{total} getauscht"
    print(f"✓ Vorzeichentausch trifft nur Quelle und Ziel "
          f"({flipped}/{total} Samples, je Sample gezogen)")


def test_modus_sign_laesst_geometrie_exakt_unberuehrt():
    """``mode="sign"`` darf NUR das Vorzeichen kippen — kein Drehen, kein Rückschub.

    Sonst wäre der abgeschwächte Modus still eine dritte Variante statt der Hälfte des
    vollen. Geprüft wird auf Bitgleichheit, nicht auf eine Toleranz.
    """
    c = A.FIRST_SIGNED_CHANNEL
    x = torch.rand(6, 4, 32, 32)
    y = torch.rand(6, 1, 32, 32)
    gen = torch.Generator().manual_seed(7)
    seen = set()
    for _ in range(20):
        xa, ya = A.augment(x, y, gen, mode="sign")
        # Material-One-Hots: unverändert, nicht nur „nahe dran"
        assert torch.equal(xa[:, :c], x[:, :c]), "Materialkanäle verändert"
        for b in range(x.shape[0]):
            s = 1.0 if torch.equal(xa[b, c:], x[b, c:]) else -1.0
            if s < 0:
                assert torch.equal(xa[b, c:], -x[b, c:]), "weder +x noch −x ⇒ gedreht"
            assert torch.equal(ya[b], s * y[b]), "Ziel folgt der Quelle nicht"
            seen.add(s)
    assert seen == {1.0, -1.0}, f"nur Vorzeichen {seen} gezogen"
    print("✓ mode='sign' lässt die Geometrie bitgleich, kippt nur das Vorzeichen")


def test_unbekannter_modus_faellt_auf():
    try:
        A.augment(torch.rand(1, 4, 8, 8), torch.rand(1, 1, 8, 8), mode="d4")
    except ValueError as e:
        assert "d4_sign" in str(e)
        print("✓ unbekannter Modus wird abgewiesen statt still ignoriert")
        return
    raise AssertionError("unbekannter Modus wurde stillschweigend akzeptiert")


def test_kanalzahl_bleibt_und_eingang_unveraendert():
    """`augment` darf den Batch des Ladeprogramms nicht in-place verändern."""
    x = torch.rand(2, 5, 32, 32)      # 5 Kanäle = mit free_space
    y = torch.rand(2, 1, 32, 32)
    x0, y0 = x.clone(), y.clone()
    xa, ya = A.augment(x, y, torch.Generator().manual_seed(1))
    assert xa.shape == x.shape and ya.shape == y.shape
    assert torch.equal(x, x0) and torch.equal(y, y0)
    print("✓ Formen bleiben, der Eingangsbatch wird nicht verändert")


if __name__ == "__main__":
    print("Augmentierung Stufe 1 (D4 × Vorzeichen)\n" + "=" * 50)
    test_d4_ist_loesersymmetrie()
    test_torch_und_numpy_dieselbe_abbildung()
    test_luftspaltring_bleibt_unberuehrt()
    test_vorzeichen_nur_auf_quellkanaelen()
    test_modus_sign_laesst_geometrie_exakt_unberuehrt()
    test_unbekannter_modus_faellt_auf()
    test_kanalzahl_bleibt_und_eingang_unveraendert()
    print("\nALLE AUGMENTIERUNGS-TESTS BESTANDEN ✅")
