"""Prüfung Variante (a): vasym +15°, magDepthRel 0.6, magWidth 32 mm.
1) Rotor-Layout (Taschen-Kollision, min Web-Weite)
2) Kt / Eisen-B-Percentiles / Demag am Pass-Betriebspunkt
"""
import json, sys
import numpy as np
import ema_analysis as ea
from ema_rotorcheck import rotor_layout_check

raw = open(sys.argv[1]).read()
payload = json.loads(raw[raw.index("{"):])
g = dict(payload["geom"]); g.update(dict(
    magShape="vasym", magAngle=120, magAsym=15,
    magDepthRel=0.6, magThick=6, magWidth=32))
axial  = float(payload.get("axial_len", 120)); CEIL = 2.1

print("=== Rotor-Layout-Check ===")
lc = rotor_layout_check(g)
print(json.dumps(lc, indent=1, ensure_ascii=False)[:1500])
ok_layout = not lc.get("collision", False) and lc.get("min_web_mm", 0) >= 2.0

print("\n=== EM am Betriebspunkt ===")
def iron_b(em, geom):
    B  = np.asarray(em["B_mag"]); N = B.shape[0]; sc = em["scale"]
    i  = np.arange(N) - N/2; X,Y = np.meshgrid(i,i); r = np.hypot(X,Y)/sc
    m  = (r > geom["shaftD"]/2*1.02) & (r < geom["rotorOD"]/2*0.98)
    b  = np.minimum(B[m], CEIL)
    return tuple(round(float(np.percentile(b,q)),3) for q in (99,95,50))

for tag, rpm, nm in (("normal", 3000, 150), ("normal", 1500, 150), ("spitze", 3000, 300)):
    iq, id_ = ea.estimate_dq_currents(g, rpm, nm, b_gap_t=0.5, rpm_base=1000)
    em  = ea.run_em_analysis(g, N=200, iq=iq, id_=id_, axial_mm=axial, saturate=True)
    p99,p95,p50 = iron_b(em, g)
    print(f"{tag:6s} {rpm:5.0f} {nm:5.0f} Nm | Iq={iq:6.1f} Id={id_:6.1f} A | "
          f"Kt={em['performance']['Kt_Nm_per_A']:.4f} Bg={em['performance']['B_gap_T']:.3f} T | "
          f"Eisen p99/p95/p50={p99}/{p95}/{p50} T")

print("\n=== Demag (Spitze 300 Nm) ===")
em0 = ea.run_em_analysis(g, N=200, iq=0.0, axial_mm=axial)
adv = ea.compute_advanced_em(g, em0["performance"], axial, 1000, 4000, 300, magnet_temp_C=120)
dm  = adv["demag"]
print(f"xi={adv.get('xi')} Br120={dm['B_operating_T'] and dm['Br_T']} T B_op={dm['B_operating_T']} "
      f"B_arm={dm['B_armature_T']} margin={dm['margin_T']} T risk={dm['risk']}")

print("\nERGEBNIS:", "LAYOUT OK → cad+analyse bereit" if ok_layout else "LAYOUT PROBLEM → erst lösen")
