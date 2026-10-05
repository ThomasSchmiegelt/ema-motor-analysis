#!/usr/bin/env python3
"""Probe, KEIN Test: traegt der Haus-FDM eine abgewickelte Axialfluss-Scheibe?

Warum diese Datei existiert
---------------------------
``AXIALFLUSS.md`` (Stufe 2) behauptet, die Feldstufe einer Axialflussmaschine
sei die BILLIGSTE im ganzen Werkzeug, weil der Loeserkern schon da ist. Diese
Behauptung entscheidet die Reihenfolge des ganzen Plans -- also darf sie keine
Behauptung bleiben. Hier wird sie gemessen.

Geprueft wird genau eins: ``_build_fv_matrix`` / ``_solve_fdm`` /
``_material_labels`` / ``_curl_a`` nehmen nur Material- und Stromfelder auf
einem gleichmaessigen kartesischen Gitter -- sie kennen keinen Radius.
Radiusgebunden sind allein ``_rasterise`` und ``_sample_airgap``. Nichts in
``ema_analysis`` wird dafuer angefasst.

Kein Test, und zwar mit Absicht
-------------------------------
``test_*.py`` laeuft in der Suite und nagelt damit Verhalten fest, das es noch
nicht gibt: Stufe 0 (das Tor) weist eine Axialflussmaschine heute ueberall ab,
und das ist richtig. Ein gruener Test dafuer waere die Aussage „wird getragen".
Das Geruest fuer ``ema_axial_fdm.rastere_scheibe`` steht hier, bis es ein Modul
gibt -- dann zieht es dorthin und bekommt seinen Test.

Aufruf
------
    PYTHONPATH=. venv/bin/python axialfluss_scheibenprobe.py

Der eine Trick, ohne den es nicht geht
--------------------------------------
Fenster = GENAU ganzzahlige Polteilungen, Polgrenze bei x = 0. Dann ist das
hauseigene Dirichlet A = 0 am Seitenrand die RICHTIGE Bedingung (A ~ sin(pi*x/tau)
hat dort Nullen) und nicht nur eine weit genug entfernte. Deshalb braucht es
kein periodisches Verfahren und keinen zweiten Loeser.

Gemessen am 05.10.2026 (die Zahlen in AXIALFLUSS.md Stufe 2 und in BEFUNDE.md):
    B_an 0,9573 T | Spitze 0,9573 T | Grundwelle 1,2098 T = 1,264 x Spitze
    (4/pi = 1,273 -> nahezu rechteckig, wie es fuer Oberflaechenmagnete an
    glattem Eisen sein muss) | Bt 40,1 % | Klirranteil 42,6 %
    Linearitaetsprobe J -> 2J: 2,000000
    <B_n^2>/2mu0 = 345,8 kPa -> 12,23 kN Anzug je Spalt, 8,6 : 1 zum Schub

Was diese Probe NICHT sagt
--------------------------
Der Staender ist massives Eisen OHNE Nuten -- das ist die nutlose Variante. Die
40 % Tangentialanteil sind Streuung an den Polkanten, keine Nutungswirkung. Und
die Eichung auf die analytische Permeanz ist hier von Hand gesetzt; im Werkzeug
braucht ``zielfeld_luftspalt`` dafuer einen axialen Zweig (s. AXIALFLUSS.md §8.2).
"""

from __future__ import annotations

import math

import numpy as np

import ema_analysis as EA

MU0 = 4.0e-7 * math.pi

# Auslegung der Probescheibe. Ro/lambda aus AXIALFLUSS.md §1.3.
R_MITTE_MM = 102.5          # mittlerer Radius (lambda = 0,577 bei Ro = 130 mm)
POLE = 16
N = 400
HM, SPALT, H_RUECKEN = 6.0, 1.0, 20.0
KC = 1.15                   # Carterfaktor, wie _analytical_Bgap
RO, RI = 0.130, 0.0751      # fuer die Ringflaeche der Kraftrechnung [m]


def schichtung(seite_mm: float) -> list:
    """Die axiale Schichtung einer YASA/TORUS-NS-Scheibe, von unten nach oben.

    Der Staender fuellt, was nach zwei Rueckenblechen, zwei Magneten und zwei
    Spalten uebrig ist -- jochlos, der Fluss geht axial durch den Zahn durch.
    """
    h_st = seite_mm - (2 * H_RUECKEN + 2 * HM + 2 * SPALT)
    if h_st <= 0:
        raise ValueError(f"Fenster {seite_mm:.2f} mm zu klein fuer die Schichtung")
    y, lagen = 0.0, []
    for name, d in (("ruecken_u", H_RUECKEN), ("magnet_u", HM), ("spalt_u", SPALT),
                    ("stator", h_st), ("spalt_o", SPALT), ("magnet_o", HM),
                    ("ruecken_o", H_RUECKEN)):
        lagen.append((name, y, y + d))
        y += d
    return lagen


def rastere_scheibe(r_mitte_mm: float, pole: int, n: int):
    """``(mu, J, lagen, sc)`` einer abgewickelten Scheibe -- x = Umfang, y = axial.

    Das Gegenstueck zu ``ema_analysis._rasterise``, nur ohne Radien: dort
    ``R = hypot(X, Y)``-Ringe, hier waagerechte Baender. Dieselbe
    Magnetisierungslogik (``J = curl M``), damit der Vergleich zuordenbar ist.
    """
    tau_p = 2.0 * math.pi * r_mitte_mm / pole
    seite = 2.0 * tau_p                       # genau 2 Polteilungen -> s. Modulkopf
    sc = n / seite
    lagen = schichtung(seite)

    Y, X = np.meshgrid(np.arange(n) / sc, np.arange(n) / sc, indexing="ij")

    def band(name):
        a, b = [(p, q) for nm, p, q in lagen if nm == name][0]
        return (Y >= a) & (Y < b)

    mu = np.ones((n, n))
    mu[band("ruecken_u") | band("ruecken_o") | band("stator")] = EA.MU_R_IRON
    mu[band("magnet_u") | band("magnet_o")] = EA.MU_R_MAG

    # Axiale Magnetisierung, Vorzeichen je Polteilung. Beide Scheiben
    # GLEICHsinnig in +y: der Fluss tritt unten ein und oben aus, laeuft also
    # axial durch den Staender. Das ist der NS-Typ -- er braucht kein
    # Staenderjoch, daher "yokeless".
    pol = np.floor(X / tau_p).astype(int) % 2
    amp = EA.Br_NdFeB / (MU0 * EA.MU_R_MAG)
    My = np.zeros((n, n))
    for lage in ("magnet_u", "magnet_o"):
        My[band(lage) & (pol == 0)] = amp
        My[band(lage) & (pol == 1)] = -amp

    J = np.zeros((n, n))
    J[:, 1:-1] = (My[:, 2:] - My[:, :-2]) / 2.0      # J = curl M = dMy/dx
    return mu, J, lagen, sc


def main() -> int:
    mu, J, lagen, sc = rastere_scheibe(R_MITTE_MM, POLE, N)
    tau_p = 2.0 * math.pi * R_MITTE_MM / POLE
    print(f"Konstanten AUS ema_analysis: Br={EA.Br_NdFeB} T  "
          f"mu_r,Mag={EA.MU_R_MAG}  mu_r,Fe={EA.MU_R_IRON}")
    print(f"Scheibe r={R_MITTE_MM} mm, 2p={POLE} -> Polteilung {tau_p:.3f} mm")
    print(f"Fenster {2 * tau_p:.2f} mm = 2 Polteilungen, N={N} -> "
          f"{1 / sc:.3f} mm/px, Luftspalt {SPALT} mm = {SPALT * sc:.1f} px")
    for nm, a, b in lagen:
        print(f"  {nm:10s} y = {a:6.2f} .. {b:6.2f} mm")

    print("\n--- Hausloeser, unveraendert ---")
    A = EA._solve_fdm(mu, J, cache=False)
    Bx, By = EA._curl_a(A, EA._material_labels(mu))
    print(f"  _solve_fdm({N}x{N}) ok, A in [{A.min():.3g}, {A.max():.3g}]")

    a, b = [(p, q) for nm, p, q in lagen if nm == "spalt_u"][0]
    jy = int(round((a + b) / 2 * sc))
    bn, bt = By[jy, :], Bx[jy, :]               # normal = axial, tangential = Umfang

    perm = HM / (HM + EA.MU_R_MAG * KC * SPALT)
    b_an = EA.Br_NdFeB * perm
    sf = b_an / max(abs(bn).max(), 1e-12)       # Eichung wie _saturate_field
    bn_t, bt_t = bn * sf, bt * sf
    k = np.fft.rfft(bn_t) / N
    klirr = math.sqrt(sum(abs(k[h]) ** 2 for h in range(2, 40))) / abs(k[1])

    print(f"\n  Permeanz hm/(hm+mu_r*kc*g) = {perm:.4f} -> B_an = {b_an:.4f} T")
    print(f"  B_axial Spitze      {abs(bn_t).max():.4f} T")
    print(f"  B_axial Grundwelle  {2 * abs(k[1]):.4f} T = "
          f"{2 * abs(k[1]) / abs(bn_t).max():.3f} x Spitze   (4/pi = {4 / math.pi:.3f})")
    print(f"  B_tangential        {abs(bt_t).max():.4f} T "
          f"({abs(bt_t).max() / abs(bn_t).max() * 100:.1f} % der Normalkomponente)")
    print(f"  Klirranteil         {klirr * 100:.1f} %")

    A2 = EA._solve_fdm(mu, 2.0 * J, cache=False)
    print(f"  Linearitaetsprobe J -> 2J: {abs(A2).max() / abs(A).max():.6f} x A "
          f"(soll 2,000000)")

    print("\n=== Die Last, die es radial nicht gibt ===")
    sig_n = (bn_t ** 2).mean() / (2 * MU0)
    aring = math.pi * (RO ** 2 - RI ** 2)
    print(f"  <B_n^2>/2mu0 = {sig_n / 1e3:.1f} kPa auf {aring * 1e4:.1f} cm^2 "
          f"-> {sig_n * aring / 1e3:.2f} kN Anzug je Spalt")
    print(f"  Momentbildender Schub (water, ema_thermal.COOLING_RATING): 40 kPa "
          f"-> Verhaeltnis {sig_n / 40e3:.1f} : 1")
    print("  Zwei Spalte heben sich auf -- nur bei MITTIGEM Staender:")
    for d in (0.02, 0.05, 0.10, 0.20):
        f = sig_n * ((SPALT / (SPALT - d)) ** 2 - (SPALT / (SPALT + d)) ** 2)
        print(f"   Versatz {d:.2f} mm ({d / SPALT * 100:4.1f} % des Spalts) -> "
              f"{f * aring / 1e3:6.2f} kN = {f / sig_n * 100:5.1f} % einer Spaltkraft, "
              f"IN Richtung des Versatzes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
