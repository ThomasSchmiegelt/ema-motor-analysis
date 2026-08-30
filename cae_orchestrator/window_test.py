import json, numpy as np, ema_analysis as ea
raw=open('/tmp/dryrun.txt').read(); payload=json.loads(raw[raw.index("{"):])
g0=dict(payload['geom']); axial=float(payload.get('axial_len',120)); CEIL=2.1
def iron_b(em,g):
    B=np.asarray(em['B_mag']); N=B.shape[0]; sc=em['scale']; i=np.arange(N)-N/2
    X,Y=np.meshgrid(i,i); r=np.hypot(X,Y)/sc
    m=(r>g['shaftD']/2*1.02)&(r<g['rotorOD']/2*0.98); b=np.minimum(B[m],CEIL)
    return tuple(round(float(np.percentile(b,q)),3) for q in (99,95,50))
def check(extra,label):
    g=dict(g0); g.update(dict(magShape='v',magAngle=120,magDepthRel=0.5,magThick=6,magWidth=37),**extra)
    iq,id_=ea.estimate_dq_currents(g,3000,150,b_gap_t=0.5,rpm_base=1000)
    iq2,id2=ea.estimate_dq_currents(g,3000,300,b_gap_t=0.5,rpm_base=1000)
    em=ea.run_em_analysis(g,N=160,iq=iq,id_=id_,axial_mm=axial,saturate=True)
    em2=ea.run_em_analysis(g,N=160,iq=iq2,id_=id2,axial_mm=axial,saturate=True)
    p1=iron_b(em,g); p2=iron_b(em2,g)
    adv=ea.compute_advanced_em(g,em['performance'],axial,1000,4000,300,magnet_temp_C=120)
    dm=adv['demag']
    ok1='OK ' if (1.0<=p1[1]<=1.6+0.05) else '   '
    ok2='OK ' if p2[1]<=2.05 else '   '
    print(f"{label:14s} Kt={em['performance']['Kt_Nm_per_A']:.4f} Bg={em['performance']['B_gap_T']:.3f} | "
          f"Norm(150Nm/3000) p99/p95/p50={p1[0]}/{p1[1]}/{p1[2]} {ok1} | "
          f"Spitze(300Nm) ={p2[0]}/{p2[1]}/{p2[2]} {ok2} | "
          f"Iq={iq:.0f}/{iq2:.0f} A | Br120={dm['Br_T']} margin={dm['margin_T']} xi={adv['xi']}")
check({}, 'Ref (th6 w37)')
check(dict(magThick=4), 'schmal  th4 w37')
check(dict(magWidth=30), 'kurz   th6 w30')
check(dict(magThick=4,magWidth=30), 'beide  th4 w30')
check(dict(magThick=5,magAngle=100), 'flacher th6 w37 a100')
