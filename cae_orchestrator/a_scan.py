"""Scan: welche Größe hält das B-Fenster (p95≤1.6 normal, p99≤2.0 Spitze)
und liefert welches Kt? vasym +15°, th6.
"""
import json, numpy as np, ema_analysis as ea
raw=open('/tmp/dryrun.txt').read(); payload=json.loads(raw[raw.index("{"):])
g0=dict(payload['geom']); axial=float(payload.get('axial_len',120)); CEIL=2.1

def iron_b(em,g):
    B=np.asarray(em['B_mag']); N=B.shape[0]; sc=em['scale']; i=np.arange(N)-N/2
    X,Y=np.meshgrid(i,i); r=np.hypot(X,Y)/sc
    m=(r>g['shaftD']/2*1.02)&(r<g['rotorOD']/2*0.98); b=np.minimum(B[m],CEIL)
    clamped=float(np.mean(B[m]>CEIL-1e-6))
    return tuple(round(float(np.percentile(b,q)),3) for q in (99,95,50)), round(clamped,4)

def check(d,w,label):
    g=dict(g0); g.update(dict(magShape='vasym',magAngle=120,magAsym=15,
                              magDepthRel=d,magThick=6,magWidth=w))
    iq,id_=ea.estimate_dq_currents(g,3000,150,b_gap_t=0.5,rpm_base=1000)
    iq2,id2=ea.estimate_dq_currents(g,3000,300,b_gap_t=0.5,rpm_base=1000)
    em=ea.run_em_analysis(g,N=160,iq=iq,id_=id_,axial_mm=axial,saturate=True)
    em2=ea.run_em_analysis(g,N=160,iq=iq2,id_=id2,axial_mm=axial,saturate=True)
    p1,cl1=iron_b(em,g); p2,cl2=iron_b(em2,g)
    w1=(1.0<=p1[1]<=1.6) and p1[0]<=2.0
    w2=p2[0]<=2.0
    print(f"{label:14s} Kt={em['performance']['Kt_Nm_per_A']:.4f} | "
          f"150Nm p99/p95/p50={p1[0]}/{p1[1]}/{p1[2]} (gesätt>2.1: {cl1:.1%}) {'OK ' if w1 else 'FEHLT'} | "
          f"300Nm={p2[0]}/{p2[1]}/{p2[2]} (gesätt {cl2:.1%}) {'OK ' if w2 else 'FEHLT'}")

check(0.5, 30, 'REF d0.5 w30')
check(0.5, 31, 'a     d0.5 w31')
check(0.6, 30, 'b     d0.6 w30')
check(0.55,31, 'c     d0.55 w31')
check(0.55,32, 'd     d0.55 w32')
check(0.6, 31, 'e     d0.6 w31')
check(0.6, 32, '(a)   d0.6 w32')
