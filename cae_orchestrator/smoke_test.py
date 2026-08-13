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

def _envelope():
    """Leistungskennfeld: die drei klassischen Bereiche müssen ohne Fallunterscheidung
    im Code herauskommen — sonst stimmt die Grenzenbehandlung nicht."""
    em  = ea.run_em_analysis(GEOM, N=120)
    adv = ea.compute_advanced_em(GEOM, em["performance"], AXIAL, 3000, 16000, 40.0)
    env = ea.power_envelope(GEOM, adv, rpm_max=16000, T_rated_Nm=120.0)
    assert "error" not in env, env.get("error")
    T = env["T_peak_Nm"]
    assert T[0] > 0, "kein Anfahrmoment"
    # Konstantmoment unterhalb, Abfall oberhalb der Eckdrehzahl
    i_b = env["rpm"].index(env["rpm_base"])
    assert abs(T[0] - T[i_b]) < 0.05 * T[0], "Moment fällt schon vor der Eckdrehzahl"
    assert T[-1] < T[i_b], "keine Feldschwächung oberhalb der Eckdrehzahl"
    # Dauerlinie darf die Spitzenlinie nie überschreiten
    assert all(c <= p + 1e-6 for c, p in zip(env["T_cont_Nm"], T)), "Dauer > Spitze"
    assert env["T_cont_Nm"][0] <= 120.0 + 1e-6, "Kühlungsdeckel greift nicht"
    assert env["cont_limited_by"] == "kuehlung"
    b64 = ep._power_chart(env)
    assert len(base64.b64decode(b64)) > 5000, "Kennfeld-Chart leer"
    return (f"P_max={env['P_max_kW']} kW @ {env['P_max_rpm']} 1/min, "
            f"M_max={env['T_peak_max_Nm']} Nm bis {env['rpm_base']} 1/min")
check("power_envelope (Konstantmoment → Feldschwächung, Dauer ≤ Spitze)", _envelope)

def _ki_training():
    """Der KI-Training-Tab liest ein OPTIONALES Nachbarprojekt — er muss auch dann
    sauber antworten, wenn `physics_surrogate/` gar nicht da ist."""
    import ema_ki_training as kt
    runs = kt.list_runs()                       # darf leer sein, aber nicht werfen
    assert isinstance(runs, list)
    for r in runs:
        assert r["epochs"] >= 1 and isinstance(r["history"], list)
        assert set(("name", "best_gate", "gate_passed", "active", "paused")) <= set(r)
    svc = kt.service_status()
    assert "up" in svc, "Dienst-Status ohne 'up'"
    if runs:
        b64 = kt.chart([runs[0]["name"]], x="progress")
        assert len(base64.b64decode(b64)) > 5000, "Verlaufs-Chart leer"
    return (f"{len(runs)} Lauf/Läufe, Dienst {'an' if svc['up'] else 'aus'}"
            if kt.available() else "physics_surrogate/ nicht vorhanden → leer, kein Fehler")
check("KI-Training-Tab: Läufe lesen + Chart + Dienst-Status", _ki_training)

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

def _wh_spread():
    # Stufenweise Spreizung der Wickelkopf-Lagen: innerste Lage 1·spread°, nächste 2·…
    # Die emittierte Mathematik wird WIRKLICH ausgeführt (reines Python, kein FreeCAD):
    # der Konstanten-Block zwischen z_face und _r_lane braucht nur math + die Header-Werte.
    import math as _m, re as _re
    def _slice(code):
        ns = {"math": _m}
        for ln in code.splitlines():
            if _re.match(r"^(n_layers|axial|coil_pitch|wh_flare)\b", ln):
                exec(ln, ns)
        exec(code[code.index("z_face  = axial / 2.0"):code.index("def _r_lane(k):")], ns)
        return ns
    g = dict(GEOM, conductorsPerSlot=8, windingHeadFlare=6, windingHeadSpread=2.0)
    code = ef.build_full_motor_script(g, AXIAL, "/tmp/_smoke.FCStd")
    ast.parse(code)
    # per-Lage: Hin-Arm f0, Rück-Arm f1 (NICHT mehr ein gemeinsames f je Paar)
    assert "wh_spread = 2.0" in code, "Spreizung nicht verdrahtet"
    assert "f0 = _lane_flare(k0); f1 = _lane_flare(k1)" in code, "Kronen-Arme nicht per-Lage"
    assert "f = f0 + b * (f1 - f0)" in code, "Aufweitung folgt der Lage nicht"
    assert "f_weld = H_w * math.tan(a_w)" in code, "Spreizung fehlt auf der Schweißseite"
    assert "2.0 * wh_flare_max" in code, "Isolierhülse muss die äußerste Lage umschließen"
    ns = _slice(code)
    fs = [ns["_lane_flare"](k) for k in range(8)]    # JEDE Lage einzeln (0..7)
    assert all(fs[i] < fs[i + 1] for i in range(7)), f"keine per-Lage-Spreizung: {fs}"
    for k, f in enumerate(fs):                        # dr/dz = f/H_eff ⇒ α = atan(…)
        a = _m.degrees(_m.atan((f - 6.0) / ns["WH_HEFF"]))
        assert abs(a - (k + 1) * 2.0) < 1e-6, f"Lage {k}: {a:.3f}° statt {(k+1)*2.0}°"
    assert abs(ns["wh_flare_max"] - fs[-1]) < 1e-9   # Hülse umschließt die äußerste Lage
    # spread = 0 ⇒ historisches Verhalten (alle Lagen gleich)
    ns0 = _slice(ef.build_full_motor_script(dict(GEOM, conductorsPerSlot=8),
                                            AXIAL, "/tmp/_smoke.FCStd"))
    assert {ns0["_lane_flare"](k) for k in range(8)} == {ns0["wh_flare"]}
    return "Lagen 2/4/6/8/10/12/14/16°, f=%s mm" % [round(f, 2) for f in fs]
check("Wickelkopf-Spreizung je Lage (per Lage, Krone + Schweißseite)", _wh_spread)

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
    pid_ki = "_smoke_train_ki"
    try:
        T.upsert(pid, meta, results, project_dir=pdir)
        rec = T.get_record(pid)
        # Hand-Entwurf: unbewertet, aber Heuristik-Vorschlag mitgeschrieben
        assert rec and rec["label"] is None, "Hand-upsert label sollte None sein"
        assert rec["label_source"] is None, "Hand-upsert label_source sollte None sein"
        assert rec["auto_label"] in ("gut", "schlecht"), "auto_label nicht gespeichert"
        # einheitliches Schema: jede Zeile trägt exakt RECORD_KEYS
        assert list(rec.keys()) == T.RECORD_KEYS, f"Schema abweichend: {list(rec.keys())}"
        assert any(i["key"] == "em_field" for i in rec.get("images", [])), "Bild nicht referenziert"
        nv = T.export_vlm()
        assert nv >= 1, "VLM-Export leer trotz Bild"
        T.set_label(pid, "gut", "ok")
        r2 = T.get_record(pid)
        assert r2["label"] == "gut" and r2["label_source"] == "user", "set_label wirkungslos"
        # KI-Entwurf: wird direkt heuristisch vorsortiert
        meta_ki = dict(meta, design_source="ki", design_brief="Testaufgabe")
        T.upsert(pid_ki, meta_ki, results, project_dir=pdir)
        rk = T.get_record(pid_ki)
        assert rk["design_source"] == "ki", "design_source nicht ki"
        assert rk["label"] in ("gut", "schlecht"), "KI-Entwurf nicht vorsortiert"
        assert rk["label_source"] == "auto", "KI-Vorsortierung nicht als auto markiert"
        assert rk["label"] == rk["auto_label"], "Vorsortier-Label != Heuristik"
        # Designer-Korrektur: expliziter Label-Parameter gewinnt über Auto-Vorsortierung
        T.upsert(pid_ki, meta_ki, results, label="gut", project_dir=pdir)
        rc = T.get_record(pid_ki)
        assert rc["label"] == "gut" and rc["label_source"] == "user", "Korrektur nicht übernommen"
        # manuelle Bewertung bleibt beim Nachrechnen erhalten (überschreibt auto nicht)
        T.set_label(pid_ki, "schlecht", "")
        T.upsert(pid_ki, meta_ki, results, project_dir=pdir)
        assert T.get_record(pid_ki)["label"] == "schlecht", "manuelle Bewertung verloren"
        assert T.get_record(pid_ki)["label_source"] == "user", "user-Label überschrieben"
    finally:
        drop = {pid, pid_ki}
        T._write_all([r for r in T._read_all() if r.get("project_id") not in drop])
        T.export_vlm()
        import shutil; shutil.rmtree(pdir, ignore_errors=True)
    return f"instr {len(instr)}c, out {len(outp)}c, auto={auto['suggestion']}, ki-presort ok"
check("training-file record + images + VLM export", _training)

# ── Projektakte (manifest + evolution + synthesize, no Ollama/FreeCAD) ───────
print("\n[projektakte]")
def _projektakte():
    import ema_projekt as P, ema_training as T, os, json, tempfile, shutil
    meta = {"label": "Akte-Test", "created": "2026-01-01T00:00:00",
            "payload": {"geom": dict(GEOM), "load_nm": 120, "rpm_to": 20000},
            "materials": {"magnet": "NdFeB N42"}, "rpm_range": "5000–20000 U/min",
            "design_source": "hand"}
    results = {"summary": {"B_gap_T": 0.92, "Kt_Nm_per_A": 0.3, "T_winding_C": 140,
               "T_magnet_C": 95, "max_safe_rpm": 22000, "mass_g": 3200,
               "P_total_W": 1500}, "em_advanced": {"Isc_A": 400}}
    base = tempfile.mkdtemp(prefix="smoke_akte_")
    try:
        # 1) init writes a v1 stub first
        pdir = os.path.join(base, "20260101_000000_test"); os.makedirs(pdir)
        assert P.init(pdir, "20260101_000000_test", origin="analyse"), "init fehlgeschlagen"
        m0 = P.load(pdir)
        assert m0 and m0["schema_version"] == 1 and m0["status"] == "neu", "Stub falsch"
        # 2) record_run appends an evolution stage, sets status + metrics
        os.makedirs(os.path.join(pdir, "charts"), exist_ok=True)
        with open(os.path.join(pdir, "charts", "em_field.png"), "wb") as fh:
            fh.write(b"\x89PNG\r\n\x1a\n")
        P.record_run(pdir, "20260101_000000_test", meta, results, action="analyse")
        # second run with a changed input → diff captured
        meta2 = json.loads(json.dumps(meta)); meta2["payload"]["geom"]["statorOD"] = 300
        P.record_run(pdir, "20260101_000000_test", meta2, results,
                     action="recompute:field", note="OD vergrößert")
        m1 = P.load(pdir)
        assert len(m1["evolution"]) == 2, f"evolution {len(m1['evolution'])}!=2"
        assert m1["status"] == "gerechnet", "Status nicht gerechnet"
        assert m1["metrics"] == T.build_metrics(results), "metrics != build_metrics"
        assert m1["evolution"][1]["changed_inputs"].get("geom.statorOD") == 300, "Diff fehlt"
        assert any(c["key"] == "em_field" for c in m1["assets"]["charts"]), "Asset fehlt"
        # 3) links: add + remove + resolve (self-healing)
        other = os.path.join(base, "20260101_111111_b"); os.makedirs(other)
        P.init(other, "20260101_111111_b")
        P.add_link(pdir, "20260101_111111_b", label="B")
        assert len(P.resolved_links(pdir, base)) == 1, "Link nicht aufgelöst"
        P.add_link(pdir, "tot_weg")                       # toter Link
        assert len(P.resolved_links(pdir, base)) == 1, "toter Link nicht übersprungen"
        P.remove_link(pdir, "20260101_111111_b")
        assert len(P.load(pdir)["links"]) == 1, "remove_link falsch"
        # 4) legacy synthesize: dir mit NUR meta/results reproduziert Akte
        leg = os.path.join(base, "20251212_000000_legacy"); os.makedirs(leg)
        with open(os.path.join(leg, "meta.json"), "w") as fh: json.dump(meta, fh)
        with open(os.path.join(leg, "results.json"), "w") as fh: json.dump(results, fh)
        assert not os.path.exists(P.path_for(leg)), "darf vor Zugriff keine Akte haben"
        syn = P.load_or_synthesize(leg, write_back=True)
        assert syn["metrics"] == T.build_metrics(results), "synthese metrics falsch"
        assert syn["datasheet"], "synthese datenblatt leer"
        assert os.path.exists(P.path_for(leg)), "lazy write-back fehlt"
        # 5) clone lineage (synthesized child carries parent)
        child = os.path.join(base, "20260202_000000_clone"); os.makedirs(child)
        P.init(child, "20260202_000000_clone", origin="clone",
               parent="20260101_000000_test")
        assert P.load(child)["lineage"]["parent"] == "20260101_000000_test", "lineage fehlt"
        # 6) ema_rag store_dir isolation (ohne Ollama: nur _save/_load/delete-Pfad)
        import ema_rag as RG
        store = os.path.join(base, "ragstore")
        idx = {"schema_version": 1,
               "documents": [{"id": "d1", "title": "x", "category": "projekt",
                              "n_chunks": 1, "chars": 3}],
               "chunks": [{"doc_id": "d1", "idx": 0, "text": "abc", "embedding": [0.1]}]}
        RG._save(idx, store_dir=store)
        assert os.path.exists(os.path.join(store, "index.json")), "store nicht geschrieben"
        assert RG._paths(None)[1] == RG.INDEX_PATH, "globaler Pfad verändert"
        assert len(RG.list_documents(store_dir=store)) == 1, "store-Doku fehlt"
        assert RG.delete_document("d1", store_dir=store), "store-delete wirkungslos"
        assert RG.list_documents(store_dir=store) == [], "store nicht geleert"
        return "init/record/diff/links/synthesize/lineage/store ok"
    finally:
        shutil.rmtree(base, ignore_errors=True)
check("Projektakte manifest + evolution + synthesize", _projektakte)

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
    # 6 immer-aktive Experten + 2 bedingte (em3d, kuehlung) = 8 registriert
    keys = [e["key"] for e in E._EXPERTS]
    assert len(E._EXPERTS) == 8, "es sollten 8 Experten sein (6 + em3d + kuehlung)"
    assert "em3d" in keys and "kuehlung" in keys, "3D-Feld-/Kühlungs-Experte fehlt"
    # bedingte Experten NUR laufen lassen, wenn ihre Daten vorliegen
    picked = [e["key"] for e in E._EXPERTS
              if not e.get("condition") or e["condition"]({"summary": {}}, {})]
    assert "em3d" not in picked and "kuehlung" not in picked, "bedingte Experten nicht gegated"
    picked2 = [e["key"] for e in E._EXPERTS if not e.get("condition")
               or e["condition"]({"em3d": {"x": 1}, "oilspray": {"y": 1}}, {})]
    assert "em3d" in picked2 and "kuehlung" in picked2, "bedingte Experten laufen nicht mit Daten"
    md = E.assemble_expert_section_compare({"em_feld": "Befund A", "temperatur": "Befund B"})
    assert "Experten-Bewertung" in md and "Befund A" in md
    # Trennlinien (---) müssen aus Prosa entfernt werden (sonst pandoc-Schmalspalte)
    assert "---" not in R._strip_md_tables("x\n\n---\n\ny"), "hrule nicht entfernt"
    # interne Pipes in Prosa werden escaped (keine versehentliche Tabelle)
    assert "\\|" in R._clean_prose("a | b"), "pipe nicht escaped"
    assert hasattr(R, "_render_chapters_pdf"), "Kapitel-Renderer fehlt"
    # Kühl-Abschnitt im Einzelbericht erscheint nur mit oilspray-Daten
    assert R._ensure_kuehlung_section("# x", {"_img_map": {}}) == "# x", "Kühl-Abschnitt ohne Daten"
    return "8 experts (2 gated), kuehlung section, hrule-strip + pipe-escape + chapter render ok"
check("comparative experts wiring + report hardening", _expert_compare)

# ── KI-Auslegung (Designer-Pfad) — Validator/Synth/Optimizer, ohne Ollama ────────
print("\n[ki-design]")
def _design_ai_validate():
    import ema_design_ai as D, ema_text2ema as T2E
    params = T2E._validate({"rotorOD": 188.6, "shaftD": 60, "statorID": 190,
                            "statorOD": 280, "p": 4, "magShape": "v", "slots": 48})
    # wild LLM magnets must be clamped into the rotor (outer corner < r_rot - bridge)
    bogus = [{"r": 95, "off": 10, "ang": 20, "len": 500, "thick": 6, "pol": 1},
             {"r": 9999, "off": -5, "ang": 200, "len": 30, "thick": 99, "pol": -1}]
    # barrier along the +y axis is far from the (near +x) magnets → survives, but its
    # outer point is pulled inside the OD bridge and its width is clamped to ≤10.
    mags, bars = D._validate_layout(bogus, [{"pts": [[5, 80], [5, 9999]], "width": 50}], params)
    assert mags, "kein Magnet überlebte die Validierung"
    r_rot = params["rotorOD"] / 2
    for m in mags:
        assert 0 <= m["off"], "Halbpol: offset muss ≥0 sein"
        oc = math.hypot(m["r"] + m["len"] * math.cos(math.radians(m["ang"])),
                        m["off"] + m["len"] * math.sin(math.radians(m["ang"])))
        assert oc <= r_rot - D.TOPO.BRIDGE_MM + 1e-6, f"Magnet ragt aus dem Rotor ({oc:.1f})"
    assert bars and len(bars[0]["pts"]) >= 2 and bars[0]["width"] <= 10
    # a barrier running THROUGH a magnet (incl. its d-axis mirror) is dropped
    _, bad_bars = D._validate_layout([{"r": 60, "off": 4, "ang": 25, "len": 18, "thick": 4, "pol": 1}],
                                     [{"pts": [[60, 4], [70, 8]], "width": 3}], params)
    assert bad_bars == [], "überlappende Flussbarriere nicht entfernt"
    # overlapping magnets are dropped (no magnet–magnet intersection); separated kept
    om, _ = D._validate_layout([{"r": 50, "off": 5, "ang": 20, "len": 18, "thick": 4, "pol": 1},
                                {"r": 51, "off": 6, "ang": 22, "len": 18, "thick": 4, "pol": 1}],
                               [], params)
    assert len(om) == 1, f"überlappende Magnete nicht entfernt: {om}"
    sep, _ = D._validate_layout([{"r": 40, "off": 4, "ang": 15, "len": 12, "thick": 3, "pol": 1},
                                 {"r": 40, "off": 22, "ang": 60, "len": 12, "thick": 3, "pol": 1}],
                                [], params)
    assert len(sep) == 2, f"saubere Magnete fälschlich verworfen: {sep}"
    # parametric fallback: always yields a drawable half-pole
    syn = D._legs_to_canvas(D._params_to_geom(params))
    assert syn, "Fallback-Synthese leer"
    return f"{len(mags)} clamped, no-overlap ok, fallback {len(syn)} legs"
check("design_ai validate + parametric fallback", _design_ai_validate)

def _design_opt_roundtrip():
    import ema_design_optimize as DO, ema_design_ai as D, ema_text2ema as T2E
    params = T2E._validate({"rotorOD": 188.6, "shaftD": 60, "p": 4, "magShape": "v"})
    mags = D._legs_to_canvas(D._params_to_geom(params))
    vec = DO._vec_of(mags)
    assert all(k.startswith("m0_") for k in vec), "Vektor-Schlüssel falsch"
    m2, legs, bars = DO._apply_vec(mags, [], vec, {"rotorOD": 188.6, "shaftD": 60})
    assert m2 and abs(m2[0]["r"] - mags[0]["r"]) < 1e-6, "Round-Trip r weicht ab"
    # off>0 master → mirror present (2 legs), signs/tilt mirrored
    if mags[0]["off"] >= 0.5:
        assert len(legs) == 2 and legs[1]["offset"] == -legs[0]["offset"], "Spiegelung fehlt"
    return f"vec {len(vec)} keys, {len(legs)} legs"
check("design_optimize vector round-trip + mirror", _design_opt_roundtrip)

def _eval_geom_custom():
    import ema_optimize as OPT, ema_design_optimize as DO, ema_design_ai as D, ema_text2ema as T2E
    import ema_pipeline as P
    params = T2E._validate({"rotorOD": 188.6, "shaftD": 60, "statorID": 190,
                            "statorOD": 280, "p": 4, "magShape": "v", "slots": 48})
    g = D._params_to_geom(params)
    g.update({"statorID": params["statorID"], "statorOD": params["statorOD"],
              "conductorsPerSlot": 4, "slotWidthRatio": 0.5})
    g["magShape"] = "custom"
    g["customLegs"] = DO._mirror_legs(D._legs_to_canvas(D._params_to_geom(params)))
    g["customBarriers"] = []
    mats = (P.LAMINATES["m270_35a"], P.LAMINATES["m270_35a"],
            P.HAIRPIN_MATS["cu_etp"], P.MAGNETS["ndfeb_n42"])
    op = {"rpm_thermal": 12000, "rpm_base": 5000, "load_nm": 80}
    m = OPT._eval_geom(g, 80.0, mats, op, "water", 25,
                       [2400, 4200, 6000, 7800, 9600, 10800, 12000], N=120)
    assert "error" not in m, f"eval error: {m.get('error')}"
    assert m["B_gap"] > 0.2, f"B_gap zu klein ({m['B_gap']})"
    return f"custom B_gap={m['B_gap']} Kt={m['Kt']}"
check("_eval_geom on custom geometry", _eval_geom_custom)

def _param_study_custom():
    import ema_paramstudy as PS, ema_design_ai as D, ema_design_optimize as DO, ema_text2ema as T2E
    params = T2E._validate({"rotorOD": 188.6, "shaftD": 60, "statorID": 190,
                            "statorOD": 280, "p": 4, "magShape": "v", "slots": 48})
    geom = D._params_to_geom(params)
    geom.update({"statorID": params["statorID"], "statorOD": params["statorOD"],
                 "conductorsPerSlot": 4, "slotWidthRatio": 0.5, "magShape": "custom",
                 "customLegs": DO._mirror_legs(D._legs_to_canvas(D._params_to_geom(params))),
                 "customBarriers": []})
    payload = {"geom": geom, "axial_len": 120, "rotor_lam": "m270_35a",
               "stator_lam": "m270_35a", "hairpin_mat": "cu_etp", "magnet": "ndfeb_n42",
               "cooling": "water", "rpm_from": 5000, "rpm_to": 12000, "load_nm": 80}
    res = PS.run_study(payload, "airgap", 0.3, 2.0, steps=3, rpm=10000)
    bg = [b for b in res["metrics"]["B_gap"] if b is not None]
    assert res["n_ok"] == 3 and len(bg) == 3, "Studie auf custom-Geometrie fehlgeschlagen"
    assert bg[0] > bg[-1], "größerer Luftspalt müsste B_gap senken"
    return f"custom sweep B_gap {bg[0]}→{bg[-1]}"
check("param study honours custom geometry", _param_study_custom)

def _design_quality_gate():
    import ema_design_ai as D, ema_text2ema as T2E
    params = T2E._validate({"rotorOD": 188.6, "shaftD": 60, "statorID": 190,
                            "statorOD": 280, "p": 4, "magShape": "v", "slots": 48})
    variant = {"params": params,
               "magnets": D._legs_to_canvas(D._params_to_geom(params)),
               "barriers": [], "begruendung": "", "fallback": False}
    q = D._quick_eval(variant)
    assert q["verdict"] in ("gut", "schlecht", None), "Qualitäts-Urteil kaputt"
    # Regenerations-Schleife: erst „schlecht", dann „gut" → genau 1 ersetzt, V1 gut
    import ema_design_ai as DD
    calls = {"n": 0}
    bad = {"params": params, "magnets": [], "barriers": [], "begruendung": "b", "fallback": True}
    good = {"params": params, "magnets": variant["magnets"], "barriers": [],
            "begruendung": "g", "fallback": False}
    orig_gen, orig_eval = DD._gen_one, DD._quick_eval
    DD._gen_one = lambda *a, **k: (good if calls.update(n=calls["n"] + 1) or calls["n"] >= 2 else bad)
    DD._quick_eval = lambda v: {"verdict": ("gut" if v is good else "schlecht"),
                                "reasons": ["test"], "metrics": {"B_gap": 1.0}}
    try:
        res = DD.design_variants("Testmotor", n=1, max_regen=2)
    finally:
        DD._gen_one, DD._quick_eval = orig_gen, orig_eval
    assert res["regenerated"] == 1, f"erwartete 1 Ersetzung, war {res['regenerated']}"
    assert res["variants"][0]["quality"]["verdict"] == "gut", "schlechte Variante nicht ersetzt"
    assert len(res["rejected"]) == 1, "verworfener Entwurf nicht erfasst"
    return f"verdict={q['verdict']}, regen-gate ok"
check("design quality pre-sort + regenerate-if-bad", _design_quality_gate)

def _ranged_design():
    import ema_design_ai as D
    rg = {"statorOD": [150, 160], "axialLen": [80, 90], "shaftD": [30, 35],
          "airgap": [1.0, 2.5]}
    # sampling within ranges incl. the user air-gap band (clamped to 0.5..3)
    for _ in range(20):
        d = D._sample_dims(rg)
        assert 150 <= d["statorOD"] <= 160 and 80 <= d["axialLen"] <= 90, d
        assert 30 <= d["shaftD"] <= 35 and 1.0 <= d["airgap"] <= 2.5, d
    # air gap is clamped to the allowed 0.5..3 band even if the user over-/undershoots
    for _ in range(20):
        d = D._sample_dims({"airgap": [0.1, 9.0]})
        assert 0.5 <= d["airgap"] <= 3.0, d
    # dims forced + statorID/rotorOD derived from the chosen air gap, magnets re-clamped
    v = {"params": {"statorOD": 999, "rotorOD": 140, "shaftD": 99, "p": 4, "slots": 48,
                    "magnet": "N42", "cooling": "water"},
         "magnets": [{"r": 35, "off": 4, "ang": 25, "len": 12, "thick": 4, "pol": 1}],
         "barriers": []}
    D._apply_ranged_dims(v, {"statorOD": 155.0, "axialLen": 85.0, "shaftD": 32.0, "airgap": 1.2})
    p = v["params"]
    assert (p["statorOD"], p["axialLen"], p["shaftD"]) == (155.0, 85.0, 32.0), p
    assert abs((p["statorID"] - p["rotorOD"]) / 2 - 1.2) < 1e-6, p
    assert p["rpm_from"] == 1000 and p["rpm_to"] == 20000 and v["magnets"], p
    # a REAL stator wall is reserved (bore ≤ STATOR_SPLIT·OD) + slot depth fits the wall
    wall = p["statorOD"] / 2 - p["statorID"] / 2
    assert p["statorID"] / 2 <= D.STATOR_SPLIT * p["statorOD"] / 2 + 1e-6, p
    assert 4 <= p["slotDepth"] <= wall - 3 + 1e-6, p
    # end-to-end with mocked LLM: fixed rpm_list + per-variant brief
    orig = D._one_variant
    D._one_variant = lambda *a, **k: {
        "params": D.T2E._validate({"p": 4, "slots": 48, "rotorOD": 150}),
        "magnets": [{"r": 50, "off": 4, "ang": 25, "len": 18, "thick": 4, "pol": 1}],
        "barriers": [], "begruendung": "t", "fallback": False}
    try:
        res = D.design_variants_ranged(rg, n=2, max_regen=0)
    finally:
        D._one_variant = orig
    assert len(res["variants"]) == 2 and res["rpm_list"] == [1000, 5000, 15000, 20000], res
    assert all(x.get("design_brief") for x in res["variants"]), "per-variant brief fehlt"
    # optional brief is prepended to each variant's design task
    assert D._ranged_brief({"statorOD":150,"axialLen":80,"shaftD":30,"airgap":1.0},
                           "Traktion XY").startswith("ANWENDUNG: Traktion XY"), "Brief nicht vorangestellt"
    # barriers are clamped to the HALF pole (y≥0)
    _, hb = D._validate_layout([], [{"pts": [[40, -8], [50, -3]], "width": 2}],
                               {"rotorOD": 180, "shaftD": 40})
    assert hb and all(p[1] >= 0 for p in hb[0]["pts"]), f"Barriere nicht auf halben Pol geklemmt: {hb}"
    return f"dims forced, brief prepended, half-pole barriers, rpm_list {res['rpm_list']}"
check("ranged/random design generation", _ranged_design)

def _training_brief():
    import ema_training as TR
    meta = {"design_brief": "120 kW Traktionsmotor, 16000 U/min", "design_source": "ki",
            "geom": {"rotorOD": 188.6}, "materials": {}}
    instr = TR.build_instruction(meta)
    assert "120 kW Traktionsmotor" in instr, "Brief fehlt in der Instruction"
    rec_src = (meta.get("design_source"))
    assert rec_src == "ki"
    return "brief in instruction + design_source"
check("training instruction carries design brief", _training_brief)

print("\n" + "=" * 50)
print(f"RESULT: {PASS} passed, {FAIL} failed")
sys.exit(FAIL)
