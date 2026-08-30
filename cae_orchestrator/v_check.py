"""Zielgerichtete EM-Prüfung einer IPM-V an Pass-Betriebspunkten (Fast-Evaluator).
Eisen-B physikalisch auf ~2.1 T gedeckt (wie die Pipeline-Anzeigefelder), Kt/
B_gap/Demag aus der kalibrierten Kette.
"""
import json, sys
import numpy as np
import ema_analysis as ea

raw = open(sys.argv[1]).read()
payload = json.loads(raw[raw.index("{"):])
geom0 = dict(payload["geom"])
axial = float(payload.get("axial_len", 120))
CEIL  = 2.1  # IRON_B_SAT_DISPLAY

def iron_b(em, geom):
    B  = np.asarray(em["B_mag"]); N = B.shape[0]; sc = em["scale"]
    i  = np.arange(N, dtype=float) - N/2
    X,Y= np.meshgrid(i,i); r_mm = np.hypot(X,Y)/sc
    m  = (r_mm > geom.get("shaftD",60)/2*1.02) & (r_mm < geom["rotorOD"]/2*0.98)
    b  = np.minimum(B[m], CEIL)
    return tuple(round(float(np.percentile(b,q)),3) for q in (99,95,50))

def run(geom, label, rpm, Nm):
    iq,id_ = ea.estimate_dq_currents(geom, rpm, Nm, b_gap_t=0.5, rpm_base=1000)
    em   = ea.run_em_analysis(geom, N=200, rotor_angle=0.0, iq=iq, id_=id_,
                               axial_mm=axial, saturate=True)
    perf = em["performance"]
    p99,p95,p50 = iron_b(em, geom)
    print(f"{label:8s} {rpm:5.0f} {Nm:5.0f} Nm | Iq={iq:6.1f} Id={id_:6.1f} A | "
          f"Kt={perf.get('Kt_Nm_per_A'):.4f} B_gap={perf.get('B_gap_T'):.3f} T | "
          f"Eisen p99/p95/p50 = {p99}/{p95}/{p50} T")

# Demag-Margen (vereinfachte Kette, heiß 120 °C / kalt 20 °C, Spitzenlast)
def demag(geom, Nm, Tmag):
    em   = ea.run_em_analysis(geom, N=200, iq=0.0, axial_mm=axial)
    adv  = ea.compute_advanced_em(geom, em["performance"], axial, 1000, 4000, Nm,
                                   magnet_temp_C=Tmag)
    dm = adv["demag"]
    print(f"  Demag@{Nm}Nm/{Tmag}°C: xi={adv.get('xi')} Br={dm['Br_T']} T, "
          f"B_op={dm['B_operating_T']} B_arm={dm['B_armature_T']} margin={dm['margin_T']} T "
          f"risk={dm['risk']} Isc={adv.get('Isc_A')} A")

geom = dict(geom0); geom.update(magShape="v", magAngle=120, magDepthRel=0.5,
                                  magThick=6, magWidth=37)
print(f"V-IPM  magDepthRel=0.5 magAngle=120 magThick=6 magWidth=37  "
      f"(Rotor r={geom['rotorOD']/2:.1f}mm, Bohrung r={geom['shaftD']/2:.1f}mm)")
print("--- Eisen-B / Kt am Betriebspunkt (gedeckt 2.1 T) ---")
run(geom,"normal",3000,150)
run(geom,"normal",1500,150)
run(geom,"spitze",3000,300)
run(geom,"spitze",1000,300)
print("--- Demagnetisierung (Spitzenlast) ---")
demag(geom,300,120); demag(geom,300,20)
