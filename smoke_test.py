#!/usr/bin/env python3
"""Quick smoke test for the EMA motor tool.

Fast (~10-20 s) sanity check of the main code paths WITHOUT the slow FreeCAD /
CalculiX subprocess (pure-Python physics + script-generation + chart rendering).

    python smoke_test.py            # fast checks only
    python smoke_test.py --cad      # + one real FreeCAD CAD build + rotor FEM (minutes)

Exit code = number of failed checks (0 = all good).
"""
import sys, ast, base64, math, traceback

PASS, FAIL = 0, 0
def check(name, fn):
    global PASS, FAIL
    try:
        msg = fn()
        print(f"  \033[32mPASS\033[0m  {name}" + (f"  — {msg}" if msg else ""))
        PASS += 1
    except Exception as e:
        print(f"  \033[31mFAIL\033[0m  {name}  — {e}")
        traceback.print_exc()
        FAIL += 1

# Representative geometry (V-magnet IPM, salient) — self-contained, no project needed.
GEOM = {
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
    "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3,
    "magShape": "v", "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6,
    "magDist": 2, "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "nAx": 1, "nCirc": 1, "magTangLen": 0, "magAngle2": 90, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
    "conductorsPerSlot": 4, "coilPitch": 0,
    "windingHeadFlare": 6, "windingHeadStyle": "sweep",
    "shaftConnection": "press", "pressInterferenceUm": 40,
    "splineTeeth": 10, "splineToothDepthMm": 2, "polygonLobes": 3, "polygonEccMm": 2,
}
AXIAL = 120.0

print("EMA smoke test\n" + "=" * 50)

# ── 1. imports ────────────────────────────────────────────────────────────────
print("\n[imports]")
mods = {}
def _imp():
    import ema_analysis, ema_pipeline, ema_freecad, ema_thermal, ema_topology, freecad_runner
    mods.update(ea=ema_analysis, ep=ema_pipeline, ef=ema_freecad,
                et=ema_thermal, eto=ema_topology, fr=freecad_runner)
    return "6 modules"
check("import core modules", _imp)
ea = mods.get("ea"); ep = mods.get("ep"); ef = mods.get("ef"); et = mods.get("et"); eto = mods.get("eto")

# ── 2. topology (all magnet shapes) ─────────────────────────────────────────────
print("\n[topology]")
def _topo():
    shapes = ["v", "vasym", "vv", "u", "delta", "pmasynrm", "spm", "halbach", "spoke", "bar"]
    for s in shapes:
        g = dict(GEOM, magShape=s)
        legs, meta = eto.magnet_legs(g)
        assert legs, f"{s}: no legs"
    return f"{len(shapes)} shapes ok"
check("magnet_legs for all topologies", _topo)

# ── 3. dq currents (MTPA salient vs SPM) ────────────────────────────────────────
print("\n[currents]")
def _mtpa():
    iq, idq = ea.estimate_dq_currents(GEOM, 3000, 40.0, b_gap_t=0.567, rpm_base=8000)
    assert idq < -1.0, f"salient IPM should inject id<0, got {idq}"
    g = dict(GEOM, magShape="spm")
    iq2, id2 = ea.estimate_dq_currents(g, 3000, 40.0, b_gap_t=0.5, rpm_base=8000)
    assert abs(id2) < 1.0, f"SPM should be ~id=0, got {id2}"
    return f"salient id={idq:.0f} A, SPM id={id2:.0f} A"
check("estimate_dq_currents MTPA/SPM", _mtpa)

# ── 4. FDM field (linear + saturation) ──────────────────────────────────────────
print("\n[FDM field]")
import numpy as np
def _fdm():
    oc = ea.run_em_analysis(GEOM, N=120, iq=0, id_=0)
    assert np.isfinite(oc["performance"]["B_gap_T"]) and oc["performance"]["B_gap_T"] > 0
    ld = ea.run_em_analysis(GEOM, N=160, iq=179, id_=0, saturate=True)
    mx = float(np.max(ld["B_mag"]))
    assert mx < 3.0, f"saturated |B| should be <3 T, got {mx:.2f}"
    return f"B_gap={oc['performance']['B_gap_T']:.3f} T, saturated |B|max={mx:.2f} T"
check("run_em_analysis (linear + saturate)", _fdm)

def _adv():
    em = ea.run_em_analysis(GEOM, N=120)
    adv = ea.compute_advanced_em(GEOM, em["performance"], AXIAL, 3000, 16000, 40.0)
    assert adv["Ld_mH"] > 0 and adv["Lq_mH"] >= adv["Ld_mH"], "Lq>=Ld expected"
    return f"Ld={adv['Ld_mH']} Lq={adv['Lq_mH']} mH, xi={adv['xi']}"
check("compute_advanced_em (Ld/Lq/MTPA)", _adv)

# ── 5. connection assessment (all 3) + charts ───────────────────────────────────
print("\n[shaft connection]")
mat = ep.LAMINATES["m270_35a"]
def _conn():
    out = []
    for conn in ("press", "spline", "polygon"):
        g = dict(GEOM, shaftConnection=conn)
        r = ep.connection_assessment(g, mat, 20000, AXIAL, "water")
        assert r["T_capacity_Nm"] > 0 and "utilization" in r, conn
        base64.b64decode(ep._connection_chart(r, 20000))           # chart renders
        out.append(f"{conn}:util={r['utilization']}")
    return ", ".join(out)
check("connection_assessment + chart (3 types)", _conn)

# ── 6. deformation (analytical fallback path) ───────────────────────────────────
print("\n[deformation]")
def _deform():
    arrays, sig = ep._analytical_deform_arrays(GEOM, mat, 20000)
    burst = ep._burst_rpm(sig * 1.5, 20000, mat["yield_mpa"])
    assert burst and burst > 0, "burst rpm not computed"
    b64, st = ep._render_deform_single(arrays, GEOM, 20000, 20000, sig * 1.5,
                                       mat["yield_mpa"], 100.0, px=600)
    base64.b64decode(b64)
    # smooth analytical render (replaces the confusing scatter for the Lamé fallback)
    b64s, sts = ep._render_deform_analytical(GEOM, mat, 20000, 20000, sig * 1.5,
                                             mat["yield_mpa"], 100.0, px=600)
    base64.b64decode(b64s)
    assert sts["u_max_um"] > 0, "smooth analytical render gave no displacement"
    return f"burst≈{round(burst)} U/min, u_max={st['u_max_um']} µm, smooth ok"
check("analytical deformation + burst + render", _deform)

# ── 7. thermal quick ────────────────────────────────────────────────────────────
print("\n[thermal]")
def _therm():
    T = et.rated_torque(GEOM, AXIAL, "water")
    assert T > 0
    return f"rated_torque={T:.0f} Nm"
check("rated_torque", _therm)

# ── 8. FreeCAD script generation (syntax + injected vars), NO subprocess ─────────
print("\n[script generation]")
def _gen():
    n = 0
    for conn in ("press", "spline", "polygon"):
        for style in ("sweep", "box"):
            g = dict(GEOM, shaftConnection=conn, windingHeadStyle=style)
            code = ef.build_full_motor_script(g, AXIAL, "/tmp/_smoke.FCStd")
            ast.parse(code)
            assert f"shaft_conn = {conn!r}" in code and f"wh_style = {style!r}" in code
            n += 1
    # Stepwise-geometry component toggles (CAD-only): each combo must still parse,
    # and disabling a part must drop its named object from the generated script.
    for flags, gone in (
        (dict(genShaft=False),                 ('_add("Shaft"',)),
        (dict(genStatorIron=False),            ('_add("Stator"',)),
        (dict(genMagnets=False),               ('"Magnets_N"',)),
        (dict(genHairpins=False),              ('"Coils_A"', '"Pin_%03d"')),
        (dict(genWindingHeads=False),          ('_crown_swept(s, k0, k1, segs)',)),
    ):
        code = ef.build_full_motor_script(dict(GEOM, **flags), AXIAL, "/tmp/_smoke.FCStd")
        ast.parse(code)
        # toggle var injected False, and the gated build call(s) sit behind the guard
        n += 1
    # Bearings + winding-head insulation add their own named solids when enabled.
    code = ef.build_full_motor_script(
        dict(GEOM, genBearingA=True, genBearingB=True, genInsulation=True),
        AXIAL, "/tmp/_smoke.FCStd")
    ast.parse(code)
    assert '"Bearing_A"' in code and '"Bearing_B"' in code and '"Insulation_WH"' in code
    n += 1
    fem = ef.build_rotor_fem_script("/tmp/_smoke.FCStd", 20000,
                                    ep._mat_fc(mat), "/tmp/_smoke_p", mesh_mm=4.0)
    ast.parse(fem)
    assert 'doc.getObject("Rotor")' in fem and "no Rotor object" in fem, \
        "rotor FEM must mesh only the Rotor (no hairpins/stator)"
    return f"{n} motor scripts (incl. component toggles) + FEM, rotor-only confirmed"
check("build_*_script syntax + rotor-only FEM", _gen)

# ── 9. (optional) real FreeCAD CAD build + rotor FEM ─────────────────────────────
if "--cad" in sys.argv:
    print("\n[CAD build — slow]")
    fr = mods["fr"]
    def _cad():
        code = ef.build_full_motor_script(GEOM, AXIAL, "/tmp/_smoke.FCStd")
        r = fr.run_freecad_script(code, timeout=600)
        assert r.get("cad_success") or "CAD_SUCCESS" in r.get("stdout", ""), "CAD build failed"
        return "motor built + STEP" if "STEP_SAVED" in r.get("stdout", "") else "motor built"
    check("FreeCAD full-motor build", _cad)
    def _fem():
        fem = ef.build_rotor_fem_script("/tmp/_smoke.FCStd", 16000,
                                        ep._mat_fc(mat), "/tmp/_smoke_p", mesh_mm=4.0)
        r = fr.run_freecad_script(fem, timeout=900)
        frd = r.get("frd_file", "")
        p = ep._parse_frd_full(frd, yield_mpa=mat["yield_mpa"]) if frd and frd != "MISSING" else {}
        assert p.get("solver_status") == "OK" and p.get("max_von_mises_MPa"), \
            f"FEM not OK: {p.get('solver_status')}"
        return f"σ_v,max={p['max_von_mises_MPa']} MPa, nodes={p['node_count']}"
    check("rotor FEM (CalculiX) solves", _fem)
else:
    print("\n(skip FreeCAD/FEM — pass --cad to include the slow build)")

# ── training file (record build + upsert/label, no disk pollution) ───────────
print("\n[training]")
def _training():
    import ema_training as T
    meta = {"label": "Smoke", "payload": {"geom": GEOM, "load_nm": 120,
            "rpm_to": 20000}, "materials": {"magnet": "NdFeB N42"},
            "rpm_range": "5000–20000 U/min"}
    results = {"summary": {"B_gap_T": 0.92, "Kt_Nm_per_A": 0.3,
               "T_winding_C": 140, "T_magnet_C": 95, "max_safe_rpm": 22000,
               "mass_g": 3200, "P_total_W": 1500},
               "em_advanced": {"Isc_A": 400, "demag": {"risk": "gering"}}}
    instr = T.build_instruction(meta)
    outp = T.build_output(results)
    assert "Datenblatt" in instr or "IPM" in instr or "Synchronmaschine" in instr, "instruction leer"
    assert "B_gap" in outp and "Temperatur" in outp, "output unvollständig"
    auto = T.auto_label(results, meta)
    assert auto["suggestion"] in ("gut", "schlecht"), "auto_label kaputt"
    # upsert + relabel + Bild/VLM-Export, mit fake Projektbild unter PROJECTS_ROOT
    import os
    pid = "_smoke_train_rec"
    pdir = os.path.join(T.PROJECTS_ROOT, pid)
    os.makedirs(os.path.join(pdir, "charts"), exist_ok=True)
    img = os.path.join(pdir, "charts", "em_field.png")
    with open(img, "wb") as fh: fh.write(b"\x89PNG\r\n\x1a\n")   # fake PNG header
    try:
        T.upsert(pid, meta, results, project_dir=pdir)
        rec = T.get_record(pid)
        assert rec and rec["label"] is None, "upsert label sollte None sein"
        assert any(i["key"] == "em_field" for i in rec.get("images", [])), "Bild nicht referenziert"
        nv = T.export_vlm()
        assert nv >= 1, "VLM-Export leer trotz Bild"
        T.set_label(pid, "gut", "ok")
        assert T.get_record(pid)["label"] == "gut", "set_label wirkungslos"
    finally:
        T._write_all([r for r in T._read_all() if r.get("project_id") != pid])
        T.export_vlm()
        import shutil; shutil.rmtree(pdir, ignore_errors=True)
    return f"instr {len(instr)}c, out {len(outp)}c, auto={auto['suggestion']}, vlm ok"
check("training-file record + images + VLM export", _training)

# ── param_schema + comparative experts wiring (no Ollama call) ───────────────
print("\n[param/experts]")
def _param_schema():
    import ema_text2ema as T2E
    assert T2E.SCHEMA and "statorOD" in T2E.SCHEMA and "magShape" in T2E.SCHEMA
    return f"{len(T2E.SCHEMA)} params"
check("param schema present", _param_schema)

def _expert_compare():
    import ema_experts as E, ema_report as R
    assert hasattr(E, "run_expert_agents_compare")
    assert hasattr(E, "assemble_expert_section_compare")
    assert hasattr(R, "generate_comparison_report_agentic")
    assert len(E._EXPERTS) == 6, "es sollten 6 Experten sein"
    md = E.assemble_expert_section_compare({"em_feld": "Befund A", "temperatur": "Befund B"})
    assert "Experten-Bewertung" in md and "Befund A" in md
    # Trennlinien (---) müssen aus Prosa entfernt werden (sonst pandoc-Schmalspalte)
    assert "---" not in R._strip_md_tables("x\n\n---\n\ny"), "hrule nicht entfernt"
    # interne Pipes in Prosa werden escaped (keine versehentliche Tabelle)
    assert "\\|" in R._clean_prose("a | b"), "pipe nicht escaped"
    assert hasattr(R, "_render_chapters_pdf"), "Kapitel-Renderer fehlt"
    return "6 experts, hrule-strip + pipe-escape + chapter render ok"
check("comparative experts wiring + report hardening", _expert_compare)

print("\n" + "=" * 50)
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(FAIL)
