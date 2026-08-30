"""Asymmetrisches V (magShape=vasym) mit den gewählten Magneten (th6 w30 a120 d0.5).
magAsym neigt die beiden Schenkel um ±[asym]° gegenüber dem symmetrischen V.
Vergleich bei 150 Nm/3000 rpm (norm.) und 300 Nm (Spitze), B-Fenster 1.0–1.6 / ≤2.0 T peak.
"""
import json, numpy as np, ema_analysis as ea
raw=open('/tmp/dryrun.txt').read(); payload=json.loads(raw[raw.index("{"):])
g0=dict(payload['geom']); axial=float(payload.get('axial_len',120)); CEIL=2.1

def iron_b(em,g):
    B=np.asarray(em['B_mag']); N=B.shape[0]; sc=em['scale']; i=np.arange(N)-N/2
    X,Y=np.meshgrid(i,i); r=np.hypot(X,Y)/sc
    m=(r>g['shaftD']/2*1.02)&(r<g['rotorOD']/2*0.98); b=np.minimum(B[m],CEIL)
    return tuple(round(float(np.percentile(b,q)),3) for q in (99,95,50))

def check(shape,asym,label):
    g=dict(g0); g.update(dict(magShape=shape,magAngle=120,magDepthRel=0.5,
                              magThick=6,magWidth=30,magAsym=asym))
    iq,id_=ea.estimate_dq_currents(g,3000,150,b_gap_t=0.5,rpm_base=1000)
    iq2,id2=ea.estimate_dq_currents(g,3000,300,b_gap_t=0.5,rpm_base=1000)
    em=ea.run_em_analysis(g,N=160,iq=iq,id_=id_,axial_mm=axial,saturate=True)
    em2=ea.run_em_analysis(g,N=160,iq=iq2,id_=id2,axial_mm=axial,saturate=True)
    p1=iron_b(em,g); p2=iron_b(em2,g)
    adv=ea.compute_advanced_em(g,em['performance'],axial,1000,4000,300,magnet_temp_C=120)
    dm=adv['demag']
    ok1='OK ' if (1.0<=p1[1]<=1.65) else '   '
    ok2='OK ' if p2[0]<=2.05 else '   '
    print(f"{label:16s} Kt={em['performance']['Kt_Nm_per_A']:.4f} Bg={em['performance']['B_gap_T']:.3f} | "
          f"150Nm p99/p95/p50={p1[0]}/{p1[1]}/{p1[2]} {ok1} | "
          f"300Nm ={p2[0]}/{p2[1]}/{p2[2]} {ok2} | "
          f"Iq={iq:.0f}/{iq2:.0f} A | margin={dm['margin_T']:.3f}T risk={dm.get('risk')}")

check('v',  0,  'REF sym. v')
check('vasym', 10, 'asym +10°')
check('vasym', 15, 'asym +15°')
check('vasym', 20, 'asym +20°')
check('vasym', 30, 'asym +30°')
check('vasym',-15, 'asym −15°')
