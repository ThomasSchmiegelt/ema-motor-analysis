"""Moment-Hebel-Studie (2) + Gewichtskost (3).

Fragt: welche Maschinen-Grösse liefert T_peak >= 368 Nm am 800-A-Gegent,
und was kostet das in Masse? Alles lokal, schneller Wert (Kt/psi aus
kalibriertem FDM, Ueberschaetzung der Satti-Induktaanz wie im Pipeline-Hinweis:
unsaturated Ld/Lq -> reale Spitze tiefer).
"""
import math
import numpy as np
import ema_analysis as ea
import json

BASE = json.load(open('/home/cae/cae_projekte/20260827_124316_Alpenpass_2500kg_V-IPM/meta.json'))
gm = (BASE.get('payload') or BASE)['geom']
BASE_G = {k: gm[k] for k in gm}
SCALE_KEYS = ['statorOD', 'statorID', 'rotorOD', 'shaftD', 'slotDepth',
              'magDist', 'magWidth', 'magThick', 'magLayerGap',
              'pocketOuterD', 'pocketInnerD', 'shaftBoreD',
              'balanceBoltCircleD', 'bearingGapMm']
AIRGAP = 0.7          # mm, wie im Base
RHO_ST, RHO_MAG, RHO_CU = 7.85e-6, 7.50e-6, 8.90e-6   # kg per mm^3

def build(f: float, L: float, mag_w: float = None):
    g = dict(BASE_G)
    for k in SCALE_KEYS:
        g[k] = BASE_G[k] * f
    # Luftspalt konstant halten
    g['rotorOD'] = g['statorID'] - 2 * AIRGAP
    g['axialLen'] = g.get('axialLen')
    g['axialLen'] = L
    g['magShape'] = 'v'
    g['magAngle'] = 120
    g['magDepthRel'] = 0.5
    if mag_w:  # absolute Magnetenbreite ueberschreiben
        g['magWidth'] = mag_w
    return g

def masses(g):
    """Grobe Massenbalance (kg): Roteisen, Magneten, Statorisen, Kupfer."""
    L = g['axialLen']
    rotor_iron = math.pi / 4 * (g['rotorOD']**2 - g['shaftD']**2) * L * RHO_ST
    n_pole = g['slots'] / 3       # 12
    magnet = 2 * n_pole * g['magWidth'] * g['magThick'] * L * RHO_MAG
    stator_iron = math.pi / 4 * (g['statorOD']**2 - g['statorID']**2) * L * RHO_ST
    pitch = math.pi * g['statorID'] / g['slots']
    slotw = pitch * g['slotWidthRatio']
    copper = g['slots'] * slotw * g['slotDepth'] * L * 0.40 * RHO_CU  # Fuellung ~40%
    return rotor_iron, magnet, stator_iron, copper

def evaluate(label, g):
    print(f"--- {label}  (OD {g['statorOD']:.0f}, ID {g['statorID']:.0f}, L {g['axialLen']:.0f}, "
          f"w {g['magWidth']:.0f} th {g['magThick']:.0f}) ---")
    em = ea.run_em_analysis(g, N=160, rotor_angle=0.0, iq=0.0, id_=0.0,
                            axial_mm=g['axialLen'], saturate=True)
    perf = em['performance']
    adv = ea.compute_advanced_em(g, perf, g['axialLen'], 1000, 4000, 150, magnet_temp_C=20.0)
    env = ea.power_envelope(g, adv, rpm_max=4000, T_rated_Nm=0.0)
    ri, mg, si, cu = masses(g)
    m_tot = ri + mg + si + cu + 4.0   # + Welle/Wellenkupplung/Lager ~4 kg
    dm = adv.get('demag', {})
    print(f"  Kt={perf.get('Kt_Nm_per_A'):.4f} Nm/A  B_gap={perf.get('B_gap_T'):.3f} T  "
          f"psi={adv.get('psi_pm_Wb'):.4f} Wb")
    print(f"  T_peak={env.get('T_peak_max_Nm')} Nm  P_max={env.get('P_max_kW')} kW "
          f"@ {env.get('P_max_rpm')} rpm")
    print(f"  Demag(150Nm,20C): margin={dm.get('margin_T')} T risk={dm.get('risk')}")
    r, mg2, s, c = masses(g)
    print(f"  Masse: Roteisen {ri:.0f} kg | Magnet {mg:.0f} kg | Stator {si:.0f} kg | "
          f"Kupfer {cu:.0f} kg | Gesamtsch {m_tot:.0f} kg")
    return env.get('T_peak_max_Nm'), m_tot

print("Ziel: T_peak >= 368 Nm (AlpPass-Demand @ ~500 rpm) | i_max = 800 A | v_dc = 800 V")
print("Basis-Geometrie: OD280 ID190 L120, 36 Slots, p=3, V-IPM d0.5 w30 th6\n")
evaluate("S0 Basis (280/120)", build(1.0, 120))
evaluate("S1 f=1.10 L140",    build(1.10, 140))
evaluate("S2 f=1.20 L140",    build(1.20, 140))
evaluate("S3 f=1.30 L150",    build(1.30, 150))
