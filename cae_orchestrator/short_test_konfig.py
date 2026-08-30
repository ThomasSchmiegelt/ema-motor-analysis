"""Kurz-Test: Magnetkonfigurationen vergleichen (ohne CAD, ohne Server).

IPM-Magnetformen auf derselben Stator-/Rotor-Basis, ausgewertet mit dem
Fast-Evaluator-Kern der Pipeline (ema_analysis.run_em_analysis — derselbe,
den /param_study und /optimize serverseitig nutzen). Zusätzliche Größe:
Flussdichte in der Rotoreisen-Scheibe (Wellenbohrung..Rotorrand), belastet mit
Normal- (150 Nm) und Spitzlast (300 Nm, kurzfristig), Sättigungspassage aktiv
(B_H-Knie 2.0 T).
"""
import json, sys
import numpy as np

import ema_analysis as ea
import ema_optimize as O

# ── Basispayload (Verifikations-Projekt 20260813_140556) ────────────────────
raw = open(sys.argv[1]).read()
payload = json.loads(raw[raw.index("{"):])
base_geom = dict(payload["geom"])
base_axial = float(payload.get("axial_len", 120))
mats = O._materials(payload)

# Betrieb am Anhänger-Alpenpass (2500 kg, ~15 %): F ≈ 3980 N → Rad ~1273 Nm
# → Motor ~133 Nm; Repräsentativ: 150 Nm Normal, 300 Nm kurzfristig, ~3000 U/min.
RPM, LOAD, PEAK = 3000.0, 150.0, 300.0
SHAPES = ["v", "vasym", "u", "delta", "vv", "bar", "pmasynrm", "spm", "halbach"]

def evaluate(shape, load_nm):
    geom = dict(base_geom)
    geom["magShape"] = shape
    iq, id_ = ea.estimate_dq_currents(geom, RPM, load_nm, b_gap_t=0.8,
                                      rpm_base=float(payload.get("rpm_from", 1000)))
    em = ea.run_em_analysis(geom, N=200, rotor_angle=0.0, iq=iq, id_=id_,
                            axial_mm=base_axial, saturate=True)
    perf = em["performance"]
    # Rotoreisen-Scheibe: px → mm mit sc (px/mm), Gitter zentriert bei N/2
    B = np.asarray(em["B_mag"])
    N = 200; sc = em["scale"]
    i = np.arange(N, dtype=float) - N / 2
    X, Y = np.meshgrid(i, i)
    r_mm = np.hypot(X, Y) / sc
    m = (r_mm > geom.get("shaftD", 60) / 2 * 1.02) & (r_mm < (geom["rotorOD"] / 2) * 0.98)
    b = B[m]
    return {
        "shape": shape, "load": load_nm,
        "iq_A": round(float(iq), 1),
        "Kt": round(float(perf.get("Kt_Nm_per_A", 0)), 4),
        "B_gap": round(float(perf.get("B_gap_T", 0)), 3),
        "B_eisen_max": round(float(np.max(b)), 3),
        "B_eisen_p95": round(float(np.percentile(b, 95)), 3),
        "B_eisen_p50": round(float(np.percentile(b, 50)), 3),
    }

print(f"{'Konfig':10s} {'Last':>5s} {'Iq':>7s} {'Kt':>8s} {'B_gap':>7s} "
      f"{'B_Eisen max':>12s} {'p95':>7s} {'p50':>7s}")
print("Anforderung: Normal 1.0–1.6 T · kurzfristig ≤ 2 T (max, p95 als Maß)")
for s in SHAPES:
    out = []
    for load in (LOAD, PEAK):
        try:
            r = evaluate(s, load)
            out.append(f"{s:10s} {r['load']:5.0f} {r['iq_A']:7.1f} {r['Kt']:8.4f} "
                       f"{r['B_gap']:7.3f} {r['B_eisen_max']:12.3f} "
                       f"{r['B_eisen_p95']:7.3f} {r['B_eisen_p50']:7.3f}")
        except Exception as e:
            out.append(f"{s:10s} {load:5.0f}   FEHLER: {e}")
    print("\n".join(out))

print("\nAnmerkung: VORTEST (Fast-Evaluator, linearer Kern + Sättigungspassage),")
print("Ströme geschätzt (MTPA), B aus dem Feldbild. Endwerte: Analyse-Lauf.")
print("Eisen-B = |B| in Scheibe Wellenbohrung..Rotorrand (gesättigt, Knie 2.0 T).")
