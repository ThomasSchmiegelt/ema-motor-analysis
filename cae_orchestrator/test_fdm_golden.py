"""Numerischer Regressionstest („Golden Test") für das 2D-FDM-Feld — OHNE FreeCAD.

`smoke_test.py` prüft am FDM nur `isfinite`, `B_gap > 0` und `|B|max < 3 T`. Ein Feld,
das glatt, endlich, unter 3 T und trotzdem **falsch** ist, fällt dort nicht auf. Dieser
Test friert deshalb den Ist-Zustand der splu-Referenzlösung ein: pro Fall einen
Fingerabdruck aus der Luftspalt-Kurve `Br_gap(θ)`, |B|-Statistik, `A`-Norm und den
Kennwerten, verglichen mit `rtol=1e-6`.

Gedacht als Gate für Änderungen an `_rasterise` / `_solve_fdm` / der Kalibrierung —
insbesondere für rein additive Erweiterungen, die das Verhalten NICHT ändern dürfen.

    python test_fdm_golden.py              # prüfen
    python test_fdm_golden.py --update     # Baseline neu erzeugen (bewusste Änderung!)
    python -m pytest test_fdm_golden.py    # oder per pytest

Baseline: `test_fdm_golden.json` (versioniert, menschenlesbar).
"""

import json
import math
import os
import sys

import numpy as np

import ema_analysis as ea

BASELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "test_fdm_golden.json")

RTOL = 1e-6

# Repräsentative V-IPM-Geometrie (identisch zu smoke_test.GEOM, damit beide Tests
# über dieselbe Maschine reden).
GEOM = {
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
    "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3,
    "magShape": "v", "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6,
    "magDist": 2, "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "nAx": 1, "nCirc": 1, "magTangLen": 0, "magAngle2": 90, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
}
AXIAL = 120.0

# (Fall-Name, magShape, N, iq, id_) — Topologien mit unterschiedlicher Flussführung:
# `v` (vergrabene V-Anordnung), `spm` (Oberflächenmagnete), `pmasynrm` (reluktanz-
# dominiert). Der Lastfall deckt zusätzlich den Split-Kalibrierungspfad ab
# (getrennte Magnet-/Anker-Lösung + `_analytical_Barm`), der historisch der fragilste
# Teil ist.
CASES_FAST = [
    ("v_oc_180",        "v",        180,   0.0, 0.0),
    ("v_load_180",      "v",        180, 179.0, 0.0),
    ("spm_oc_180",      "spm",      180,   0.0, 0.0),
    ("pmasynrm_oc_180", "pmasynrm", 180,   0.0, 0.0),
]
# N=512 ist das Zielgitter des Surrogats (dort löst der Luftspalt-Carve auf) und
# kostet ~2 s pro Lösung.
#
# ACHTUNG beim Lesen der Baseline (kein Fehler, sondern dokumentiertes Verhalten):
# `bt_norm`/`bt_peak`/`T_maxwell` sind bei N ≤ 256 **exakt 0**. `_sample_airgap`
# gewinnt B_t aus einem Zwei-Kreis-Harmonischen-Fit im aufgelösten Luftspaltband und
# fällt auf 0 zurück, solange das Band sub-pixelig ist (`AIRGAP_MIN_MM = 2.5` mm gegen
# ~1,5 mm/px bei N=180). Erst ab N≈360 wird B_t ungleich 0 — und dann nicht monoton
# (gemessen max|B_t| = 0.67 / 1.01 / 0.22 T bei N = 360 / 512 / 700). `T_maxwell` ist
# daher KEINE auflösungsstabile Größe; als Regressionsanker taugt es nur pro festem N.
CASES_SLOW = [
    ("v_oc_512",        "v",        512,   0.0, 0.0),
    ("spm_oc_512",      "spm",      512,   0.0, 0.0),
    ("pmasynrm_oc_512", "pmasynrm", 512,   0.0, 0.0),
]
# Der NICHTLINEARE Anzeigepfad (`saturate=True`). Seit 13.08.2026 rendern ALLE
# Feldbilder — auch die Animations-Frames — darüber; vorher war er nur an den beiden
# Berichtsbildern aktiv und damit praktisch ungetestet. Die Fixpunkt-Iteration in
# `_saturate_field` (4 Durchgänge, jeweils neue µ ⇒ neue Faktorisierung) ist der
# fragilste Teil des Anzeigepfads: sie hängt an `B_SAT_IRON`, am Fröhlich-Exponenten
# und am Relaxationsfaktor. N=256 hält die Laufzeit bei ~5 s je Fall.
CASES_SAT = [
    ("v_oc_256_sat",    "v",        256,   0.0,   0.0, True),
    ("v_load_256_sat",  "v",        256, 179.0,   0.0, True),
]


def _iron_bulk_p98(bmag, mu):
    """p98 von |B| im Eisen OHNE die Randschicht (3 Zellen von jeder Materialgrenze).

    Der Rand trägt die Eckensingularitäten und ist auflösungsabhängig; das Volumen
    konvergiert (gemessen 0,46 → 0,66 → 0,83 → 0,94 T bei N = 256/362/512/724). Ein
    Regressionsanker gehört auf die konvergente Größe.
    """
    iron = mu >= ea.MU_R_IRON - 1e-3
    core = iron
    for _ in range(3):                       # 4-Nachbarschafts-Erosion, ohne scipy
        core = (core
                & np.roll(core,  1, 0) & np.roll(core, -1, 0)
                & np.roll(core,  1, 1) & np.roll(core, -1, 1))
    return float(np.percentile(bmag[core], 98)) if core.any() else 0.0


def _fingerprint(name, shape, N, iq, id_, sat=False):
    """Ein Fall rechnen und auf einen vergleichbaren Fingerabdruck reduzieren."""
    geom = dict(GEOM, magShape=shape)
    try:
        em = ea.run_em_analysis(geom, N=N, rotor_angle=0.0, iq=iq, id_=id_,
                               axial_mm=AXIAL, saturate=sat)
    finally:
        # Faktorisierungen nicht über die Fälle mitschleppen (N=512 ist speicherhungrig).
        ea.clear_lu_cache()

    br, bt = np.asarray(em["Br_gap"]), np.asarray(em["Bt_gap"])
    bmag, A = np.asarray(em["B_mag"]), np.asarray(em["A"])
    perf = em["performance"]

    assert np.all(np.isfinite(br)) and np.all(np.isfinite(bmag)), f"{name}: NaN/Inf im Feld"

    return {
        # Luftspaltkurve: dezimierte Stützstellen + integrale Maße. Die Maße fangen
        # auch Abweichungen in den nicht abgetasteten Punkten.
        "br_samples": [float(v) for v in br[::10]],
        "br_norm":    float(np.linalg.norm(br)),
        "br_peak":    float(np.max(np.abs(br))),
        "bt_norm":    float(np.linalg.norm(bt)),
        "bt_peak":    float(np.max(np.abs(bt))),
        # Feldbild. ACHTUNG bei `b_max`: das ist eine SINGULÄRE Zelle an einer
        # Magnetecke (dort läuft das Feld einer scharfen Ecke im Kontinuum gegen
        # unendlich), also keine physikalische Größe, sondern eine Stichprobe der
        # Singularität — gemessen 12,9 / 12,8 / 13,5 / 14,1 T bei N = 256/362/512/724,
        # während der Anteil solcher Zellen von 2,9 % auf 1,2 % fällt. Als Anker taugt
        # `b_iron_bulk_p98`: Eisen ohne die Randschicht, dort konvergiert das Feld.
        "b_max":      float(np.max(bmag)),
        "b_mean":     float(np.mean(bmag)),
        "b_p98":      float(np.percentile(bmag, 98)),
        "b_iron_bulk_p98": _iron_bulk_p98(bmag, np.asarray(em["mu"])),
        "a_norm":     float(np.linalg.norm(A)),
        # Kalibrierung + Kennwerte
        "sf_ref":     float(em["sf_ref"]),
        "B_gap_T":    float(perf["B_gap_T"]),
        "Kt":         float(perf["Kt_Nm_per_A"]),
        "psi_pm_Wb":  float(perf["psi_pm_Wb"]),
        "T_maxwell":  float(perf["T_maxwell_Nm"]),
    }


def _cmp(case, key, got, exp, errs):
    if isinstance(exp, list):
        g = np.asarray(got, dtype=float)
        e = np.asarray(exp, dtype=float)
        if g.shape != e.shape:
            errs.append(f"{case}.{key}: Länge {g.shape} statt {e.shape}")
            return
        # atol relativ zum Kurvenmaximum: Nulldurchgänge sonst unvergleichbar
        atol = RTOL * max(float(np.max(np.abs(e))), 1e-30)
        if not np.allclose(g, e, rtol=RTOL, atol=atol):
            i = int(np.argmax(np.abs(g - e)))
            errs.append(f"{case}.{key}[{i}]: {g[i]:.12g} statt {e[i]:.12g} "
                        f"(max Δ {np.max(np.abs(g - e)):.3g})")
    else:
        if not math.isclose(float(got), float(exp), rel_tol=RTOL,
                            abs_tol=RTOL * max(abs(float(exp)), 1e-30)):
            errs.append(f"{case}.{key}: {float(got):.12g} statt {float(exp):.12g}")


def _load_baseline():
    if not os.path.exists(BASELINE):
        raise AssertionError(
            f"Baseline {os.path.basename(BASELINE)} fehlt — einmalig mit "
            "`python test_fdm_golden.py --update` erzeugen.")
    with open(BASELINE) as f:
        return json.load(f)


def _check(cases):
    base = _load_baseline()
    errs = []
    for name, shape, N, iq, id_, *rest in cases:
        if name not in base:
            errs.append(f"{name}: nicht in der Baseline — `--update` nötig?")
            continue
        fp = _fingerprint(name, shape, N, iq, id_, *rest)
        exp = base[name]
        for key in sorted(exp):
            _cmp(name, key, fp.get(key), exp[key], errs)
        print(f"  ✓ {name:<16} Br_peak={fp['br_peak']:.6f} T  |B|max={fp['b_max']:.4f} T  "
              f"T_maxwell={fp['T_maxwell']:.4g} Nm")
    assert not errs, ("FDM-Feld hat sich geändert (rtol=%g):\n  " % RTOL
                      + "\n  ".join(errs)
                      + "\n\nWar die Änderung beabsichtigt? Dann `python "
                        "test_fdm_golden.py --update` und den Diff prüfen.")


def test_golden_n180():
    """Schnelle Fälle (Animationsauflösung) + Lastfall/Split-Kalibrierung."""
    print("\n[FDM-Golden N=180]")
    _check(CASES_FAST)


def test_golden_n512():
    """Zielgitter des Surrogats — ~2 s pro Lösung."""
    print("\n[FDM-Golden N=512]")
    _check(CASES_SLOW)


def test_golden_saturated():
    """Nichtlinearer Anzeigepfad — der, aus dem seit 13.08. jedes Feldbild kommt."""
    print("\n[FDM-Golden nichtlinear (saturate=True)]")
    _check(CASES_SAT)


def test_rasterise_maps():
    """Vertrag von `_rasterise(..., maps=True)` (Grundlage des Surrogat-Encoders).

    Prüft: die 4-Tupel-Rückgabe bleibt bitgleich, die Masken partitionieren das Gitter
    lückenlos, sie stimmen mit den µ-Werten überein, und die Magnetisierung liegt
    (bis auf die dokumentierte Endkappen-Überlappung) in den Magneten.
    """
    print("\n[_rasterise maps=True]")
    for shape in ("v", "spm", "pmasynrm"):
        geom = dict(GEOM, magShape=shape)
        N = 256
        mu, J, sc, ctr = ea._rasterise(geom, N)
        mu2, J2, sc2, ctr2, m = ea._rasterise(geom, N, maps=True)

        assert np.array_equal(mu, mu2) and np.array_equal(J, J2), \
            f"{shape}: maps=True verändert die regulären Rückgabewerte"
        assert (sc, ctr) == (sc2, ctr2)

        iron, mag, air = m["iron"], m["magnet"], m["air"]
        assert int(iron.sum() + mag.sum() + air.sum()) == N * N, \
            f"{shape}: Masken partitionieren das Gitter nicht"
        assert not (iron & mag).any() and not (iron & air).any() and not (mag & air).any()
        # Masken ↔ µ-Werte
        assert np.all(mu[iron] >= ea.MU_R_IRON - 1e-3), f"{shape}: iron-Maske falsch"
        assert np.allclose(mu[mag], ea.MU_R_MAG), f"{shape}: magnet-Maske falsch"
        assert np.allclose(mu[air], 1.0), f"{shape}: air-Maske falsch"
        assert mag.sum() > 0 and iron.sum() > 0

        # Magnetisierung: vorhanden, richtungsbehaftet (Polwechsel ⇒ beide Vorzeichen),
        # und nahezu vollständig innerhalb der Magnete (s. Docstring-Quirk).
        M = np.hypot(m["Mx"], m["My"])
        assert M[mag].mean() > 0, f"{shape}: keine Magnetisierung in den Magneten"
        assert m["Mx"].min() < 0 < m["Mx"].max(), f"{shape}: kein Polaritätswechsel in Mx"
        stray = float((M > 0).sum() and ((M > 0) & ~mag).sum() / (M > 0).sum())
        assert stray < 0.05, f"{shape}: {stray:.1%} der Magnetisierung außerhalb der Magnete"
        assert abs(M[mag].mean() / m["j_amp"] - 1.0) < 0.35, \
            f"{shape}: |M|/j_amp = {M[mag].mean() / m['j_amp']:.3f}, erwartet ~1"

        print(f"  ✓ {shape:<9} Eisen={int(iron.sum())} Magnet={int(mag.sum())} "
              f"Luft={int(air.sum())}  Streu-M={stray:.2%}")


def test_curl_a_material_interface():
    """`_curl_a` darf den Stencil nicht über eine Materialgrenze legen.

    Analytisch bekannter Fall: `A` ist stückweise linear in y mit Steigung s1 im
    Eisen und s2 im Magneten. Dann ist `Bx = ∂A/∂y` exakt s1 bzw. s2 — auch in der
    Grenzzelle, denn die Tangentialkomponente von B SPRINGT dort (nur die Normal-
    komponente ist stetig). Die zentrale Differenz liefert in den beiden Grenzzeilen
    stattdessen den Mittelwert (s1+s2)/2, der zu keinem der beiden Materialien gehört.
    """
    print("\n[_curl_a Materialgrenze]")
    N, k, s1, s2 = 32, 16, 1.0, 7.0
    y = np.arange(N, dtype=float)
    prof = np.where(y < k, s1 * y, s1 * k + s2 * (y - k))
    A = np.repeat(prof[:, None], N, axis=1)            # nur y-abhängig
    mu = np.where(y[:, None] < k, ea.MU_R_IRON, ea.MU_R_MAG) * np.ones((N, N))
    lbl = ea._material_labels(mu)
    assert set(np.unique(lbl)) == {1, 2}, "Testaufbau: zwei Materialien erwartet"

    exact = np.where(y[:, None] < k, s1, s2) * np.ones((N, N))
    bx_m, _ = ea._curl_a(A, lbl)
    bx_c, _ = ea._curl_a(A, None)

    # Materialbewusst: exakt, inklusive der Grenzzeilen k-1 und k.
    err_m = float(np.max(np.abs(bx_m - exact)))
    assert err_m < 1e-12, f"materialbewusster Stencil: Fehler {err_m:.3g}, erwartet 0"
    # Zentrale Differenz: in der Grenzzeile k der Mittelwert statt s2.
    assert math.isclose(float(bx_c[k, N // 2]), 0.5 * (s1 + s2), rel_tol=1e-12)
    assert math.isclose(float(bx_c[k - 1, N // 2]), s1, rel_tol=1e-12)
    err_c = float(np.max(np.abs(bx_c - exact)))

    # Ohne Materialwechsel muss er bitgleich zu np.gradient bleiben (keine Regression
    # im Volumen, wo die zentrale Differenz die genauere zweite Ordnung ist).
    rng = np.random.default_rng(0)
    F = rng.standard_normal((24, 24))
    one = np.zeros((24, 24), dtype=np.int8)
    gx, gy = ea._curl_a(F, one)
    # Rundungsgleich, nicht bitgleich: 0.5*(fwd+bwd) und (F[i+1]-F[i-1])/2 sind
    # dieselbe Formel in anderer Klammerung.
    assert np.allclose(gx, np.gradient(F, axis=0), rtol=1e-14, atol=1e-15), \
        "uniformes Material ≠ np.gradient"
    assert np.allclose(gy, -np.gradient(F, axis=1), rtol=1e-14, atol=1e-15), \
        "uniformes Material ≠ np.gradient"

    print(f"  ✓ Sprung {s1}→{s2}: materialbewusst Fehler {err_m:.2g}, "
          f"zentrale Differenz {err_c:.3g} (= (s1+s2)/2 in den Grenzzeilen)")
    print(f"  ✓ uniformes Material: rundungsgleich zu np.gradient")


def test_lu_cache_bounded():
    """Der LU-Cache muss nach SPEICHER gedeckelt sein, nicht nach Eintragszahl.

    Zwei Eigenschaften, die zusammen einen realen Aufhänger verhindert haben
    (13.08.2026, 72 Frames × 14 Drehzahlen bei N=600 blieben um Frame 469 stehen):

    * Der Sättigungs-Fixpunkt rechnet je Iteration ein neues ``mu``, das per
      Konstruktion nie wieder vorkommt. Landete es im Cache, wuchsen die
      Einträge um 5 je Frame und verdrängten die wiederverwendbaren.
    * Ein Eintrag kostet bei N=240 ~0,12 GB, bei N=600 ~1,0 GB — eine feste
      Eintragszahl reserviert dort zweistellige GB und die Maschine lagert aus.
    """
    print("\n[LU-Cache Deckel]")
    geom = dict(GEOM, magShape="v")
    angles = [0.0, 0.03, 0.06, 0.09, 0.12]

    def _run(ang, iq, id_):
        ea.run_em_analysis(geom, N=240, rotor_angle=ang, iq=iq, id_=id_,
                           axial_mm=AXIAL, saturate=True)

    def _used_gb():
        return sum(ea._lu_bytes(lu) for lu, _iv in ea._LU_CACHE.values()) / 1e9

    budget_orig = ea._LU_CACHE_GB
    try:
        ea._LU_CACHE_GB = 0.25                    # bei N=240 Platz für zwei Einträge
        ea.clear_lu_cache()
        for ang in angles:
            _run(ang, 120.0, -60.0)
            assert _used_gb() <= ea._LU_CACHE_GB, (
                f"Cache {_used_gb():.3f} GB über Budget {ea._LU_CACHE_GB} GB")
        n = len(ea._LU_CACHE)
        assert n <= 2, f"{n} Einträge trotz 0,25-GB-Budget — Eviction greift nicht"
        print(f"  ✓ Budget gehalten: {n} Einträge / {_used_gb():.3f} GB "
              f"nach {len(angles)} Frames")

        # Ohne den cache=False-Pfad stünden hier 5 Einträge je Frame.
        ea._LU_CACHE_GB = 100.0
        ea.clear_lu_cache()
        for ang in angles:
            _run(ang, 120.0, -60.0)
        n = len(ea._LU_CACHE)
        assert n == len(angles), (
            f"{n} Einträge für {len(angles)} Rotorwinkel — die Sättigungs-Iterate "
            f"werden mitgecacht")
        print(f"  ✓ ein Eintrag je Rotorwinkel: {n} bei {len(angles)} Frames")

        # Zweiter Betriebspunkt über dieselben Winkel: der Operator hängt nur an mu,
        # es darf kein einziger Eintrag dazukommen.
        for ang in angles:
            _run(ang, 110.0, -70.0)
        assert len(ea._LU_CACHE) == len(angles), (
            f"{len(ea._LU_CACHE)} statt {n} Einträge — Wiederverwendung kaputt")
        print(f"  ✓ Wiederverwendung über Betriebspunkte: weiterhin {n} Einträge")
    finally:
        ea._LU_CACHE_GB = budget_orig
        ea.clear_lu_cache()


def _update():
    out = {}
    for name, shape, N, iq, id_, *rest in CASES_FAST + CASES_SLOW + CASES_SAT:
        fp = _fingerprint(name, shape, N, iq, id_, *rest)
        out[name] = fp
        print(f"  + {name:<16} Br_peak={fp['br_peak']:.6f} T  |B|max={fp['b_max']:.4f} T")
    with open(BASELINE, "w") as f:
        json.dump(out, f, indent=1, sort_keys=True)
        f.write("\n")
    print(f"\nBaseline geschrieben: {BASELINE} ({len(out)} Fälle)")


if __name__ == "__main__":
    if "--update" in sys.argv:
        print("FDM-Golden-Baseline erzeugen\n" + "=" * 50)
        _update()
        sys.exit(0)
    print("FDM-Golden-Test\n" + "=" * 50)
    test_curl_a_material_interface()
    test_golden_n180()
    test_golden_n512()
    test_golden_saturated()
    test_rasterise_maps()
    test_lu_cache_bounded()
    print("\nALLE FDM-GOLDEN-TESTS BESTANDEN ✅")
