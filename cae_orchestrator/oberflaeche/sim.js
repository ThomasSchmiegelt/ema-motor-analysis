// Die Live-Vorschau: Geometrie rastern, Feld loesen, Laeufer zeichnen.
//
// Eine Kapsel (IIFE) mit eigenem `GEOM`/`PHYS`; nach aussen gereicht wird
// nur, was die Maske braucht (`window.GEOM`, `window.resize`,
// `window.toggleSim`, `window._ART_FELDER`, …).
//
// Hier steht auch der HANDGESPIEGELTE `magnetLegs`, eingefasst in die beiden
// MIRROR-Marken weiter unten: `test_topology.py` schneidet den Block zwischen
// ihnen heraus und faehrt ihn mit `node` gegen `ema_topology.magnet_legs`.
// Wer dort etwas aendert, aendert BEIDE Seiten oder keine. (Die Marken werden
// hier bewusst nicht ausgeschrieben -- der Test sucht die ERSTE, und eine
// Erwaehnung im Kopf waere genau die, die er dann findet.)
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

(function () {
  const canvas = document.getElementById("simCanvas");
  const ctx    = canvas.getContext("2d");
  let cvsW, cvsH, CX, CY, SCALE;

  const GEOM = {
    machineType: "pmsm",
    statorOD: 280, statorID: 190, rotorOD: 188.6, shaftD: 60,
    slots: 54, slotDepth: 25, slotWidthRatio: 0.5,
    p: 3, magShape: "v", magAngle: 120, magDepthRel: 0.7,
    magWidth: 45, magThick: 6, magDist: 4, airGap: 0.7,
    magLayers: 3, magLayerGap: 8, poleArcFrac: 0.83, segPerPole: 6,
    nAx: 1, nCirc: 1, shaftBoreD: 0, magTangLen: 0, magAngle2: 90, magAsym: 0, magGapMm: 0.1,
    pocketMode: "position", pocketOuterD: 178, pocketInnerD: 150,
    magOrient: "transverse", conductorsPerSlot: 4, coilPitch: 0,
    windingHeadFlare: 6, windingHeadSpread: 0, windingHeadStyle: "sweep",
    shaftConnection: "press", pressInterferenceUm: 40,
    splineTeeth: 10, splineToothDepthMm: 2, polygonLobes: 3, polygonEccMm: 2,
    // Stepwise geometry: per-component build toggles (CAD only). Core parts on,
    // bearings + winding-head insulation optional extras off.
    genShaft: true, genRotorIron: true, genMagnets: true, genStatorIron: true,
    genHairpins: true, genWindingHeads: true,
    genBearingA: false, genBearingB: false, genInsulation: false,
    bearingODmm: 0, bearingWidthMm: 14, bearingGapMm: 5, insulationThkMm: 0.4,
    // Balance-disc bolts (optional): holes + bolts through the whole stack,
    // count = pole number, symmetric (pitch-circle Ø + angular offset, thread ≥ M4).
    genBalanceBolts: false, balanceBoltThread: "M6",
    balanceBoltCircleD: 0, balanceBoltOffsetDeg: 0,
    // Flux barriers (optional radial air slots): q-axis (between poles) + d-axis
    // (pole centre), independently toggleable, shared width/depth [mm].
    genFluxBarrierQ: false, genFluxBarrierD: false,
    fluxBarrierWidth: 3, fluxBarrierDepth: 10,
  };
  window.GEOM = GEOM; // expose for analysis payload

  const PHYS = {
    isRunning: true, ultraSlow: false,
    omega: 0, angle: 0, iq: 0, id: 0, torque: 0,
    load: 5, voltage: 800, id_manual: 0, timeScale: 1.0, rpmSet: 0,
    Rs: 0.02, Ld: 0.0003, Lq: 0.0008, Psi: 0.09, J: 0.1,
    // Der Winkel des DREHFELDS, getrennt vom Laeuferwinkel. Bei jeder
    // Synchronmaschine sind die beiden dasselbe -- bei der ASM nicht, und
    // genau darin besteht die Bauart: ohne Schlupf wird im Kaefig nichts
    // induziert, also traegt ein synchron mitlaufender Kaefig kein Moment.
    // Gemeldet als „bei der ASM hat man das Gefuehl, Feld und Welle laufen
    // synchron" -- sie liefen es, weil das Staenderfeld am LAEUFERwinkel hing.
    feldWinkel: 0, schlupf: 0,
    // ── Aus der WIRKLICHEN Maschine, sobald `livePhysikLaden()` lief ────────
    // Bis dahin gelten die Festwerte darueber. Sie sind ausdruecklich als
    // Startwerte stehengeblieben, damit die Vorschau ohne Serverantwort
    // weiterlaeuft — aber `echt` sagt, woran man gerade sieht.
    echt: false, iMax: 800, vDc: 800, rpmBase: 5000, xi: 2.67,
    kModule: 1, sysJeNut: null, ausfallSystem: -1,
  };

  let GRID_SIZE_STD = 100, GRID_SIZE = 100;
  let gridA = null, gridMu = null, gridJ = null, isSolverInit = false;
  let _frameCount = 0, _lastErr = "";

  function init() {
    // Multiple attempts to capture canvas dimensions after layout settles
    resize();
    requestAnimationFrame(resize);
    setTimeout(resize, 50);
    setTimeout(resize, 200);

    if (typeof ResizeObserver !== 'undefined') {
      new ResizeObserver(resize).observe(canvas.parentElement);
    }
    window.addEventListener("resize", resize);
    window.addEventListener("load", () => requestAnimationFrame(resize));

    const resetField = () => { isSolverInit = false; _laeuferAnfordern(); };
    bindInput("dim_stator_out", v => { GEOM.statorOD = v; resetField(); });
    bindInput("dim_stator_in",  v => { GEOM.statorID  = v; resetField(); });
    bindInput("dim_rotor_out",  v => { GEOM.rotorOD   = v; resetField(); });
    bindInput("dim_shaft",      v => { GEOM.shaftD     = v; resetField(); });
    bindInput("dim_shaft_bore", v => { GEOM.shaftBoreD = v; resetField(); });
    bindInput("stator_slots",   v => { GEOM.slots = parseInt(v); resetField(); });
    bindInput("p_pairs", v => {
      GEOM.p = v;
      document.getElementById("poles_display").innerText = v * 2;
      // Die Polzahl steht jetzt bei der Maschinenart und nicht mehr bei den
      // Magneten -- sie gehoert jeder Bauart. Die Anzeige daneben sagt, was
      // aus den Polpaaren folgt, weil in der Maschine 2p zaehlt.
      const dp = document.getElementById("disp_poles");
      if (dp) dp.textContent = (v * 2) + " Pole";
      resetField();
    });

    // Maschinenart -- die Entscheidung VOR der Topologie. Die Auswahl kommt aus
    // `/param_schema` (dort baut `_art_optionen` die Beschriftung aus
    // `ema_maschinenart` und nennt gleich, wie weit eine Art getragen ist); eine
    // zweite Liste im HTML waere die naechste Stelle, an der Formular und
    // Rechnung auseinanderlaufen. Bis sie geladen ist, steht genau ein Eintrag

    // da -- die Vorgabe, mit der bisher ohnehin gerechnet wurde.
    async function _artLaden() {
      const sel = document.getElementById("machine_art");
      if (!sel) return;
      try {
        if (!_ptabSchema) {
          const r = await fetch("/param_schema").then(x => x.json());
          _ptabSchema = r.params || [];
        }
        const spec = _ptabSchema.find(sp => sp.key === "machineType");
        if (!spec || !spec.options || !spec.options.length) return;
        const cur = GEOM.machineType || spec.def || "pmsm";
        sel.innerHTML = spec.options.map(o =>
          `<option value="${o.value}"${o.value === cur ? " selected" : ""}>` +
          `${o.label}</option>`).join("");
        sel.value = cur;
      } catch (e) { /* ohne Server bleibt die Vorgabe stehen */ }
      _updateArtVis();
    }

    // Was eine Bauart NICHT hat, wird ausgeblendet statt als wirkungsloses Feld
    // stehen zu lassen: eine Asynchronmaschine hat keine Magnetanordnung, und
    // ein Regler, der nichts bewegt, liest sich wie einer, der nicht wirkt.
    // Die vier Wicklungswerkstoffe + die Leitertemperatur. Dieselbe Quelle wie
    // die Maschinenart: /param_schema, nicht eine zweite Liste im HTML.
    // JEDES Feld, das nur EINE (oder wenige) Bauarten haben: Elementkennung
    // -> Schemaschluessel. Grenzen, Auswahllisten und Vorgaben kommen aus
    // /param_schema und stehen NICHT ein zweites Mal im HTML -- sonst ist ein
    // Wert waehlbar, den die Rechnung nicht kennt (derselbe Grund, aus dem die
    // Maschinenart-Liste von dort kommt).
    const _ART_FELDER = {mat_bar: "barMat", mat_rotorwire: "rotorWireMat",
                         mat_field: "fieldMat", mat_armature: "armatureMat",
                         spule_form: "erregerSpuleForm",
                         spule_fuellung: "erregerSpuleFuellung",
                         pol_b_schuh: "polSchuhBreiteMm",
                         pol_b_kern: "polKernBreiteMm",
                         pol_d_spule: "erregerSpuleDickeMm",
                         pol_h_spule: "erregerSpuleHoeheMm",
                         pol_kegel: "polKegelWinkelGrad",
                         b_ziel: "bZielT",
                         synrm_k: "synrmBarrieren",
                         synrm_kw: "synrmIsolationsgrad",
                         synrm_steg: "synrmStegMm",
                         synrm_beta: "synrmBetaGrad",
                         laeufer_nut_tiefe: "laeuferNutTiefeMm",
                         laeufer_nut_breite: "laeuferNutBreiteMm",
                         laeufer_steg: "laeuferStegMm",
                         rotor_type: "rotorType", rotor_bars: "rotorBars",
                         rotor_skew: "rotorSkewSlots",
                         rotor_turns: "rotorTurnsPerSlot",
                         pol_bedeckung: "polbedeckung",
                         pol_schuh_anteil: "polSchuhAnteil",
                         pol_befestigung: "polBefestigung",
                         pol_bolzen: "polBolzen",
                         pol_gewinde: "polBolzenGewinde",
                         daempfer: "daempferkaefig",
                         daempfer_staebe: "daempferStaebeJePol",
                         daempfer_mat: "daempferMat",
                         anker_wicklung: "armatureWinding"};
    const _MAT_FELDER = _ART_FELDER;          // alter Name, gleiche Tabelle

    async function _matLaden() {
      try {
        if (!_ptabSchema) {
          const r = await fetch("/param_schema").then(x => x.json());
          _ptabSchema = r.params || [];
        }
      } catch (e) { return; }
      for (const id in _ART_FELDER) {
        const el = document.getElementById(id);
        const key = _ART_FELDER[id];
        const spec = _ptabSchema.find(sp => sp.key === key);
        if (!el || !spec) continue;
        if (spec.options) {
          const cur = GEOM[key] || spec.def;
          el.innerHTML = spec.options.map(o =>
            `<option value="${o.value}"${o.value === cur ? " selected" : ""}>` +
            `${o.label}</option>`).join("");
          el.value = cur;
          GEOM[key] = el.value;
          el.onchange = e => { GEOM[key] = e.target.value; resetField(); };
        } else {
          // Zahlenfeld: Grenzen aus dem Schema, damit die Maske keinen Wert
          // annimmt, den `--set` und die Pipeline abweisen wuerden.
          if (spec.lo !== undefined && spec.lo !== null) el.min = spec.lo;
          if (spec.hi !== undefined && spec.hi !== null) el.max = spec.hi;
          if (spec.int) el.step = 1;
          const cur = (GEOM[key] === undefined || GEOM[key] === null)
                        ? spec.def : GEOM[key];
          el.value = cur;
          GEOM[key] = spec.int ? Math.round(+cur) : +cur;
          el.oninput = e => {
            let v = +e.target.value;
            if (!isFinite(v)) return;
            GEOM[key] = spec.int ? Math.round(v) : v;
            resetField();
          };
        }
      }
      const tl = document.getElementById("t_leiter");
      if (tl) tl.oninput = e => {
        GEOM.tLeiterC = +e.target.value || 0; resetField();
      };
      _updateArtVis();
    }
    window._matLaden = _matLaden;
    window._ART_FELDER = _ART_FELDER;

    function _updateArtVis() {
      const sel = document.getElementById("machine_art");
      const art = (sel && sel.value) || GEOM.machineType || "pmsm";
      const mitMagneten = (art === "pmsm");
      // **Der Reluktanzlaeufer haengt seit dem 20.09.2026 NICHT mehr an
      // `magShape`.** Seine Flussbarrieren kommen aus `ema_synrm_cad` nach
      // Auslegungsregeln (Nutteilung, Isolationsgrad, Feldlinienform) und
      // nicht mehr aus der Magnet-Anordnung. Die Topologiegruppe hier stehen
      // zu lassen -- und sei es unter dem Namen „Flussbarrieren (Anordnung)"
      // -- waere ein Regler, der nichts mehr bewegt. Er wird ausgeblendet,
      // und an seine Stelle tritt die eigene Gruppe „Flussbarrieren
      // (Reluktanzlaeufer)".
      const topo = document.getElementById("grp_magnet_topo");
      if (topo) topo.style.display = mitMagneten ? "" : "none";
      const topoTitel = topo && topo.querySelector(".grp-titel, h4, legend, .section-title");
      if (topoTitel) topoTitel.textContent = "Magnet-Topologie";
      // Nur die Wicklungen zeigen, die diese Bauart WIRKLICH hat. Ein
      // Ankerwerkstoff an einer Asynchronmaschine waere ein Feld ohne
      // Wirkung, und ein wirkungsloses Feld liest sich wie ein defektes.
      document.querySelectorAll(".wick-mat, .art-feld").forEach(el => {
        const arten = (el.getAttribute("data-arten") || "").split(/\s+/);
        el.style.display = arten.includes(art) ? "" : "none";
      });
      // Die Polzahl bleibt IMMER stehen -- sie gehoert jeder Maschine. Nur
      // die Beschriftung sagt, was daraus folgt.
      const dp = document.getElementById("disp_poles");
      if (dp) dp.textContent = (2 * (GEOM.p || 1)) + " Pole";
      const hin = document.getElementById("art_hinweis");
      if (hin) {
        const opt = sel && sel.selectedOptions && sel.selectedOptions[0];
        const lbl = (opt ? opt.textContent : art);
        hin.textContent = mitMagneten ? ""
          : (art === "synrm")
            ? (lbl + " — ohne Magnete. Die Flussbarrieren kommen aus den " +
               "Auslegungsregeln (Nutteilung, Isolationsgrad, Feldlinienform), " +
               "nicht mehr aus der Magnet-Anordnung; der Griff dafuer steht " +
               "unter 'Flussbarrieren (Reluktanzlaeufer)'. Die analytische " +
               "Rechnung kennt davon weiterhin nur die Barrierenhoehe.")
            : (lbl +
               " — ohne Magnete; die Magnet-Topologie entfaellt. Welche Stufen " +
               "diese Art traegt, steht in der Auswahl; der Lauf weist ab, was " +
               "sie nicht traegt.");
      }
    }
    window._updateArtVis = _updateArtVis;

    document.getElementById("machine_art").onchange = e => {
      GEOM.machineType = e.target.value; resetField(); _updateArtVis();
    };
    _artLaden();
    _matLaden();

    document.getElementById("mag_shape").onchange = e => {
      GEOM.magShape = e.target.value; resetField();
      _updateTopoVisibility(); _updatePocketMode(); _updateEffWidthDisplay();
    };
    document.getElementById("pocket_mode").onchange = e => {
      GEOM.pocketMode = e.target.value; resetField(); _updatePocketMode();
    };
    document.getElementById("mag_orient").onchange = e => {
      GEOM.magOrient = e.target.value; resetField();
    };
    bindInput("pocket_outer_d", v => { GEOM.pocketOuterD = v; resetField(); });
    bindInput("pocket_inner_d", v => { GEOM.pocketInnerD = v; resetField(); });
    bindSlider("mag_angle", v => { GEOM.magAngle    = v; resetField(); _updateEffWidthDisplay(); }, "°");
    bindSlider("mag_angle2", v => { GEOM.magAngle2  = v; resetField(); }, "°");
    bindSlider("mag_asym",  v => { GEOM.magAsym     = v; resetField(); }, "°");
    bindSlider("mag_tang_len", v => { GEOM.magTangLen = v; resetField(); }, " mm");
    bindSlider("mag_depth", v => { GEOM.magDepthRel = v / 100; resetField(); _updateEffWidthDisplay(); }, "%");
    bindSlider("mag_width", v => { GEOM.magWidth    = v; resetField(); _updateEffWidthDisplay(); }, " mm");
    bindSlider("mag_thick", v => { GEOM.magThick    = v; resetField(); _updateEffWidthDisplay(); }, " mm");
    bindSlider("mag_gap",   v => { GEOM.magGapMm    = v; }, " mm");
    bindSlider("mag_dist",  v => { GEOM.magDist     = v; resetField(); }, " mm");
    bindSlider("mag_layer_gap", v => { GEOM.magLayerGap = v; resetField(); }, " mm");
    bindSlider("mag_layers",    v => { GEOM.magLayers   = parseInt(v); resetField(); }, "");
    bindSlider("pole_arc",      v => { GEOM.poleArcFrac  = v / 100; resetField(); }, "%");
    bindSlider("seg_per_pole",  v => { GEOM.segPerPole   = parseInt(v); resetField(); }, "");
    bindSlider("n_ax",          v => { GEOM.nAx          = parseInt(v); }, "");
    bindSlider("n_circ",        v => { GEOM.nCirc        = parseInt(v); }, "");
    _updateTopoVisibility(); _updatePocketMode();
    bindSlider("slot_depth",v => { GEOM.slotDepth   = v; resetField(); }, " mm");
    bindSlider("cond_per_slot", v => { GEOM.conductorsPerSlot = parseInt(v); }, "");
    bindSlider("coil_pitch",    v => { GEOM.coilPitch         = parseInt(v); }, "");
    bindSlider("wh_flare",      v => { GEOM.windingHeadFlare   = v; }, " mm");
    bindSlider("wh_spread",     v => { GEOM.windingHeadSpread  = v; }, " °");
    document.getElementById("wh_style").onchange = e => { GEOM.windingHeadStyle = e.target.value; };
    // Wellenverbindung (Blechpaket–Welle)
    bindSlider("press_interf",  v => { GEOM.pressInterferenceUm = v; }, " µm");
    bindSlider("spline_teeth",  v => { GEOM.splineTeeth         = parseInt(v); }, "");
    bindSlider("spline_depth",  v => { GEOM.splineToothDepthMm  = v; }, " mm");
    bindSlider("poly_lobes",    v => { GEOM.polygonLobes        = parseInt(v); }, "");
    bindSlider("poly_ecc",      v => { GEOM.polygonEccMm        = v; }, " mm");
    document.getElementById("shaft_connection").onchange = e => {
      GEOM.shaftConnection = e.target.value; _updateShaftConn();
    };
    _updateShaftConn();

    // Stepwise geometry — component build toggles (CAD only, no solver reset).
    const _chk = (id, key) => {
      document.getElementById(id).onchange = e => {
        GEOM[key] = e.target.checked; _updateComponentVis();
      };
    };
    _chk("gen_shaft",   "genShaft");    _chk("gen_rotor",   "genRotorIron");
    _chk("gen_magnets", "genMagnets");  _chk("gen_stator",  "genStatorIron");
    _chk("gen_hairpins","genHairpins"); _chk("gen_whead",   "genWindingHeads");
    _chk("gen_bear_a",  "genBearingA"); _chk("gen_bear_b",  "genBearingB");
    _chk("gen_insul",   "genInsulation");
    _chk("gen_balance", "genBalanceBolts");
    bindSlider("bearing_od",  v => { GEOM.bearingODmm    = v; }, " mm");
    bindSlider("bearing_w",   v => { GEOM.bearingWidthMm = v; }, " mm");
    bindSlider("bearing_gap", v => { GEOM.bearingGapMm   = v; }, " mm");
    bindSlider("insul_thk",   v => { GEOM.insulationThkMm = v; }, " mm");
    document.getElementById("bal_thread").onchange =
      e => { GEOM.balanceBoltThread = e.target.value; };
    // bal_circle_d / bal_offset accept 0 and negative values (auto / versatz),
    // so they can't use bindInput (which ignores ≤ 0).
    const _balNum = (id, key) => {
      const el = document.getElementById(id); if (!el) return;
      const h = () => { const v = parseFloat(el.value); if (!isNaN(v)) GEOM[key] = v; };
      el.oninput = h; el.onchange = h;
    };
    _balNum("bal_circle_d", "balanceBoltCircleD");
    _balNum("bal_offset",   "balanceBoltOffsetDeg");
    const _fbChk = (id, key) => {
      const el = document.getElementById(id); if (!el) return;
      el.onchange = e => { GEOM[key] = e.target.checked; resetField(); _updateComponentVis(); };
    };
    _fbChk("gen_fb_q", "genFluxBarrierQ");
    _fbChk("gen_fb_d", "genFluxBarrierD");
    bindSlider("fb_width", v => { GEOM.fluxBarrierWidth = v; resetField(); }, " mm");
    bindSlider("fb_depth", v => { GEOM.fluxBarrierDepth = v; resetField(); }, " mm");
    _updateComponentVis();

    bindSlider("sim_load",      v => PHYS.load      = v, " Nm");
    bindSlider("sim_id_weak",   v => PHYS.id_manual = v, " A");
    bindSlider("sim_timescale", v => PHYS.timeScale  = v, "x");
    const _rpmSetEl = document.getElementById("sim_rpm_set");
    if (_rpmSetEl) _rpmSetEl.oninput = () => {
      const v = parseFloat(_rpmSetEl.value) || 0;
      PHYS.rpmSet = v;
      const d = document.getElementById("disp_rpm_set");
      if (d) d.innerText = v > 0 ? v.toLocaleString("de-DE") + " U/min" : "frei";
    };

    document.getElementById("grid_res").onchange = e => {
      GRID_SIZE_STD = parseInt(e.target.value);
      updateGridMode();
    };
    document.getElementById("chk_ultra_slow").onchange = e => {
      PHYS.ultraSlow = e.target.checked;
      updateGridMode();
    };

    const btnPlay = document.getElementById("btn_play_pause");
    // Keep all play/pause controls (Live-tab button + preview-overlay button +
    // status text) in sync. Exposed globally so the overlay button — reachable
    // from the Geometrie/Betrieb/Berechnung tabs — toggles the same state.
    window._syncSimUI = () => {
      const r = PHYS.isRunning;
      if (btnPlay) { btnPlay.innerText = r ? "Stop" : "Start"; btnPlay.className = r ? "stop" : "start"; }
      const ov = document.getElementById("ov_play");
      if (ov) { ov.textContent = r ? "⏸ Pause" : "▶ Start"; ov.style.background = r ? "var(--err)" : "var(--ok)"; }
      const vs = document.getElementById("val_status");
      if (vs) { vs.innerText = r ? "LÄUFT" : "PAUSE"; vs.style.color = r ? "var(--ok)" : "var(--warn)"; }
    };
    window.toggleSim = () => { PHYS.isRunning = !PHYS.isRunning; window._syncSimUI(); };
    // ⊙ Der Axialzweig der Vorschau steht AUSSERHALB dieser Kapsel und braucht
    // trotzdem den Lauf-Zustand. Herausgereicht wird er, statt ihn dort ein
    // zweites Mal zu fuehren — zwei Zustaende fuer denselben Knopf laufen beim
    // ersten Sonderfall auseinander.
    window._simZustand = () => ({ laeuft: PHYS.isRunning, omega: PHYS.omega,
                                  rpmSoll: PHYS.rpmSet, tempo: PHYS.timeScale,
                                  ultraSlow: PHYS.ultraSlow });
    btnPlay.onclick = window.toggleSim;
    document.getElementById("btn_reset").onclick = () => {
      PHYS.omega = PHYS.angle = PHYS.id = PHYS.iq = 0;
    };

    // Apply button: the preview pane is already visible on the input tabs, so just
    // force a canvas resize + reset the solver (no tab switch needed).
    document.getElementById("btn_apply").onclick = () => {
      requestAnimationFrame(() => requestAnimationFrame(() => {
        resize();
        isSolverInit = false;
      }));
    };

    initSolverArrays();
    requestAnimationFrame(loop);

    // Eingaben automatisch sichern + (falls vorhanden) letzte Sitzung wiederherstellen.
    if (typeof setupAutosave === 'function') setupAutosave();
  }

  function updateGridMode() {
    GRID_SIZE = PHYS.ultraSlow ? 300 : GRID_SIZE_STD;
    isSolverInit = false;
  }

  function bindInput(id, cb) {
    const el = document.getElementById(id);
    if (!el) return;
    const handle = () => { const v = parseFloat(el.value); if (!isNaN(v) && v > 0) cb(v); };
    el.oninput  = handle;
    el.onchange = handle;  // also fires on paste / spin-button
  }

  function bindSlider(id, cb, unit) {
    const el = document.getElementById(id);
    if (!el) return;
    el.oninput = () => {
      const v = parseFloat(el.value);
      cb(v);
      const dispId = "disp_" + id.replace("sim_", "").replace("in_", "");
      const dispEl = document.getElementById(dispId);
      if (dispEl) dispEl.innerText = v + unit;
    };
  }

  function resize() {
    const p = canvas.parentElement;
    if (!p) return;
    let w = p.clientWidth  || p.offsetWidth  || 0;
    let h = p.clientHeight || p.offsetHeight || 0;
    // Fallback to window dimensions if flex layout hasn't computed yet
    if (w < 10) w = Math.max(300, window.innerWidth  - 370);
    if (h < 10) h = Math.max(300, window.innerHeight - 48);
    if (w === cvsW && h === cvsH) return;
    cvsW = w; cvsH = h;
    canvas.width = cvsW; canvas.height = cvsH;
    CX = cvsW / 2; CY = cvsH / 2;
    isSolverInit = false;
  }
  window.resize = resize;

  function initSolverArrays() {
    const total = GRID_SIZE * GRID_SIZE;
    gridA  = new Float32Array(total).fill(0);
    gridMu = new Float32Array(total).fill(1);
    gridJ  = new Float32Array(total).fill(0);
    isSolverInit = true;
  }

  // Show/hide topology-specific parameter rows based on the selected magShape.
  function _updateTopoVisibility() {
    const shape = GEOM.magShape || "v";
    document.querySelectorAll(".topo-param").forEach(el => {
      const topos = (el.getAttribute("data-topos") || "").split(/\s+/);
      el.style.display = topos.includes(shape) ? "" : "none";
    });
  }

  // Pocket-by-diameter mode (V-form only): swap Position/Länge sliders for the
  // Außen-Ø/Innen-Ø inputs. The opening angle slider stays in both modes.
  function _updatePocketMode() {
    const isV = (GEOM.magShape || "v") === "v";
    const mode = GEOM.pocketMode || "position";
    const dia = isV && mode === "diameter";
    const wand = mode === "wand";
    document.querySelectorAll(".pocket-dia").forEach(el => el.style.display = dia ? "" : "none");
    document.querySelectorAll(".pocket-pos").forEach(el => el.style.display = (dia || wand) ? "none" : "");
    // Im Wandmodus sind Sitz UND Stegabstand abgeleitet — sie als Schieberegler
    // stehen zu lassen hiesse, eine Eingabe anzubieten, die nichts bewirkt.
    const dist = document.getElementById("mag_dist");
    if (dist && dist.closest(".slider-group"))
      dist.closest(".slider-group").style.display = wand ? "none" : "";
    const note = document.getElementById("pocket_wand_note");
    if (!note) return;
    note.style.display = wand ? "" : "none";
    if (!wand) return;
    try {
      const legs = magnetLegs(GEOM).filter(l => l.placement === "interior" && l.length > 0);
      const Rrot = GEOM.rotorOD/2, Rsh = GEOM.shaftD/2;
      const l0 = legs[0];
      const dep = ((l0.rPos - Rsh) / Math.max(Rrot - Rsh, 1e-6) * 100).toFixed(1);
      const len = Math.max.apply(null, legs.map(l => l.length)).toFixed(2);
      note.innerHTML = "Abgeleitet: Stegabstand <b>" + (2*Math.abs(l0.offset)).toFixed(2) +
        " mm</b> · Position <b>" + dep + "&nbsp;%</b> · Magnetlänge <b>" + len + " mm</b>" +
        "<br>Magnetlänge 0 = Slot füllen. Der Steg zum Nachbarpol (2,0 mm) wird beim " +
        "Rechnen geprüft, nicht hier.";
    } catch (e) { note.textContent = "Abgeleitet aus den Wänden."; }
  }

  // Show only the parameter sliders relevant to the chosen shaft connection.
  function _updateShaftConn() {
    const c = GEOM.shaftConnection || "press";
    const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? "" : "none"; };
    show("grp_press", c === "press");
    show("grp_spline_teeth", c === "spline");
    show("grp_spline_depth", c === "spline");
    show("grp_poly_lobes", c === "polygon");
    show("grp_poly_ecc", c === "polygon");
  }

  // Component toggles: reveal bearing/insulation params when enabled, and gate the
  // winding-head + insulation options on hairpins being built (no bars → no heads).
  function _updateComponentVis() {
    const show = (id, on) => { const e = document.getElementById(id); if (e) e.style.display = on ? "" : "none"; };
    show("grp_bearing", !!(GEOM.genBearingA || GEOM.genBearingB));
    show("grp_insul",   !!GEOM.genInsulation);
    show("grp_balance", !!GEOM.genBalanceBolts);
    show("grp_fluxbarrier", !!(GEOM.genFluxBarrierQ || GEOM.genFluxBarrierD));
    const hp = GEOM.genHairpins !== false;
    const wh = document.getElementById("gen_whead");
    const ins = document.getElementById("gen_insul");
    if (wh)  { wh.disabled  = !hp; wh.parentElement.style.opacity  = hp ? "1" : ".45"; }
    if (ins) { ins.disabled = !(hp && GEOM.genWindingHeads !== false);
               ins.parentElement.style.opacity = ins.disabled ? ".45" : "1"; }
  }

  function _updateEffWidthDisplay() {
    // effective magnet length for V-family (thickness-aware clamp)
    const wel = document.getElementById("disp_mag_width_eff");
    if (wel) {
      const vFam = ["v","vasym","u","vv","delta","pmasynrm"].includes(GEOM.magShape);
      if (!vFam) { wel.innerText = ""; }
      else {
        const rPos = GEOM.shaftD/2 + (GEOM.rotorOD/2 - GEOM.shaftD/2) * GEOM.magDepthRel;
        const hA   = (GEOM.magAngle * Math.PI / 180) / 2;
        const maxW = _maxMagnetWidth(rPos, GEOM.magDist/2, hA, GEOM.rotorOD/2, 2 + GEOM.magThick/2);
        const eff  = Math.min(GEOM.magWidth, maxW);
        wel.innerText = (eff < GEOM.magWidth - 0.5) ? `→ ${eff.toFixed(1)} mm eff.` : "";
      }
    }
    // surface-magnet thickness clamp warning (spm/halbach)
    const tel = document.getElementById("disp_mag_thick");
    if (tel) {
      const isSurf = ["spm","halbach"].includes(GEOM.magShape);
      const note = tel.parentElement.querySelector(".thick-eff");
      if (note) note.remove();
      if (isSurf) {
        const eff = _surfaceThickness(GEOM);
        if (eff < GEOM.magThick - 0.05) {
          const s = document.createElement("span");
          s.className = "thick-eff";
          s.style.cssText = "color:#f90;font-size:.8em;margin-left:4px";
          s.innerText = `→ ${eff.toFixed(1)} mm (Luftspalt)`;
          tel.parentElement.appendChild(s);
        }
      }
    }
  }

  // <<MIRROR-START>> (test_topology.py extracts this block to compare against ema_topology.py)
  // mirrors ema_topology._max_magnet_width(): clamps arm length so the outer
  // corner stays inside R_rot - BRIDGE (same iron bridge as FreeCAD/ema_topology)
  function _maxMagnetWidth(rPos_mm, mDistHalf_mm, halfAngle, rRot_mm, bridge) {
    if (bridge == null) bridge = 1.3;
    const a = Math.cos(halfAngle), b = Math.sin(halfAngle);
    const R = rRot_mm - bridge;
    const p = a * rPos_mm + b * mDistHalf_mm;
    const q = rPos_mm*rPos_mm + mDistHalf_mm*mDistHalf_mm - R*R;
    const disc = p*p - q;
    return disc < 0 ? 5 : Math.max(-p + Math.sqrt(disc), 5);
  }

  // Spiegel von ema_topology.WAND_* -- EINE Stelle, damit test_topology.py sie
  // gegen die Python-Konstanten festnageln kann.
  const WAND_RAND = 1.3, WAND_ACHSE = 1.5, WAND_QACHSE = 2.0;
  const WAND_SP_A = 1.5, WAND_SP_I = 2.0;

  // Spiegel von ema_topology.sitz_aus_waenden()/slot_laenge_max()/_v_sitz():
  // im Wandmodus folgen Sitz (magDist, magDepthRel) und noetigenfalls die Laenge
  // aus den WAENDEN der Tasche statt aus geratenen Zahlen. rPos ist das INNERE
  // ENDE des Magneten -- vom inneren Ende bis zum aeusseren Kappenmittelpunkt sind
  // es L + gap, nicht L/2 + gap.
  function _sitzAusWaenden(rRot, halfAngle, magH, gap, laenge, wandRand) {
    if (wandRand == null) wandRand = WAND_RAND;
    const ht = magH/2 + gap, d = Math.max(laenge, 0) + gap;
    const dHalf = WAND_ACHSE + ht + gap*Math.sin(halfAngle);
    const R = rRot - wandRand - ht, y = dHalf + d*Math.sin(halfAngle);
    if (R <= 0 || y >= R) return [dHalf, Math.max(rRot*0.05, 1.0)];
    return [dHalf, Math.sqrt(R*R - y*y) - d*Math.cos(halfAngle)];
  }
  function _slotLaengeMax(rRot, rShaft, halfAngle, magH, gap, wandRand) {
    if (wandRand == null) wandRand = WAND_RAND;
    const ht = magH/2 + gap;
    const dHalf = WAND_ACHSE + ht + gap*Math.sin(halfAngle);
    const R = rRot - wandRand - ht, rMin = rShaft + WAND_ACHSE + magH/2 + 2*gap;
    const a = Math.sin(halfAngle), b = Math.cos(halfAngle);
    const P = dHalf*a + rMin*b, Q = rMin*rMin + dHalf*dHalf - R*R;
    const disc = P*P - Q;
    return disc <= 0 ? 0 : Math.max(-P + Math.sqrt(disc) - gap, 0);
  }
  // Spiegel von ema_topology._v_sitz(): [rPos, dHalf, laenge] je nach pocketMode.
  function _vSitz(G, halfAngle, magH, magW, wandRand) {
    const Rrot = G.rotorOD/2, Rshaft = G.shaftD/2;
    const rPos = Rshaft + (Rrot - Rshaft) * G.magDepthRel;
    let dHalf = G.magDist/2;
    if (_pocketMode(G) === "wand") {
      const gap = Math.max(0.05, Math.min(0.3, G.magGapMm != null ? G.magGapMm : 0.1));
      if (magW <= 0) magW = _slotLaengeMax(Rrot, Rshaft, halfAngle, magH, gap, wandRand);
      const sz = _sitzAusWaenden(Rrot, halfAngle, magH, gap, magW, wandRand);
      return [sz[1], sz[0], magW];
    }
    const eb = (wandRand == null ? WAND_RAND : wandRand) + magH/2;
    return [rPos, dHalf, Math.min(magW, _maxMagnetWidth(rPos, dHalf, halfAngle, Rrot, eb))];
  }
  function _pocketMode(G) {
    const m = String(G.pocketMode || "position").trim().toLowerCase();
    return (m === "position" || m === "diameter" || m === "wand") ? m : "position";
  }

  // mirrors ema_topology._surface_thickness(): surface magnets occupy the outer
  // rotor band [r_rot - t, r_rot] (inside the OD); clamp to leave an iron core.
  function _surfaceThickness(G) {
    const maxT = (G.rotorOD/2 - G.shaftD/2) - 2.0, req = G.magThick;
    if (maxT <= 0.5) return Math.max(maxT, 0.5);
    return req > maxT ? maxT : req;
  }

  // ⚠ MIRROR of ema_topology.magnet_legs() — keep both in sync.
  // Returns pole-local magnet placement legs. Frame: x = radial outward,
  // y = tangential. A leg starts at (rPos, offset) and extends `length` along
  // (cos tilt, sin tilt); `thickness` is perpendicular. magMode ∈
  // "perp"|"tangential"|"radial"; magSign flips polarity; placement ∈
  // "interior"|"surface".
  function magnetLegs(G) {
    const BRIDGE = 1.3;   // Spiegel von ema_topology.BRIDGE_MM (test_topology.py)
    const WAND = _pocketMode(G) === "wand";
    const Rrot = G.rotorOD/2, Rshaft = G.shaftD/2;
    const Rbore = (G.shaftBoreD != null ? G.shaftBoreD : 0)/2;
    const rPos = Rshaft + (Rrot - Rshaft) * G.magDepthRel;
    const magH = G.magThick;
    const shape = G.magShape || "v";
    const dH = G.magDist/2, hA = (G.magAngle*Math.PI/180)/2;
    const hA2 = ((G.magAngle2 != null ? G.magAngle2 : G.magAngle)*Math.PI/180)/2;
    const dL = (G.magLayerGap != null ? G.magLayerGap : 8);
    const tang = (G.magTangLen != null ? G.magTangLen : 0);
    const eb = BRIDGE + magH/2;                      // thickness-aware bridge
    const leg = (o) => Object.assign(
      {rPos, offset:0, tilt:0, length:G.magWidth, thickness:magH,
       magMode:"perp", magSign:1, magRot:0, placement:"interior", layer:0}, o);
    if (shape === "v") {
      // Diameter mode: pocket defined by inner-Ø, outer-Ø and the V angle.
      let rPosV = rPos, dHV = dH, w;
      if (_pocketMode(G) === "diameter") {
        rPosV = Math.sqrt(Math.max(25.0, Math.pow(G.pocketInnerD/2, 2) - dH*dH));
        w = _maxMagnetWidth(rPosV, dH, hA, G.pocketOuterD/2, 0.0);
        w = Math.min(w, _maxMagnetWidth(rPosV, dH, hA, Rrot, eb));
      } else {
        const sz = _vSitz(G, hA, magH, G.magWidth);
        rPosV = sz[0]; dHV = sz[1]; w = sz[2];
      }
      return [ leg({rPos:rPosV, offset:+dHV, tilt:+hA, length:w, magSign:+1}),
               leg({rPos:rPosV, offset:-dHV, tilt:-hA, length:w, magSign:-1}) ];
    }
    if (shape === "vasym") {
      // asymmetric V: the two arms open at different angles about the d-axis
      const asym = (G.magAsym != null ? G.magAsym : 0)*Math.PI/180;
      const haTop = Math.min(Math.max(hA + asym, 5*Math.PI/180), 85*Math.PI/180);
      const haBot = Math.min(Math.max(hA - asym, 5*Math.PI/180), 85*Math.PI/180);
      const st = _vSitz(G, haTop, magH, G.magWidth);
      const sb = _vSitz(G, haBot, magH, G.magWidth);
      return [ leg({rPos:st[0], offset:+st[1], tilt:+haTop, length:st[2], magSign:+1}),
               leg({rPos:sb[0], offset:-sb[1], tilt:-haBot, length:sb[2], magSign:-1}) ];
    }
    if (shape === "u") {
      const szU = _vSitz(G, hA, magH, G.magWidth);
      const rPosU = szU[0], dHU = szU[1], w = szU[2];
      // Der Steg wird zwischen TASCHEN gemessen, nicht zwischen Magnetkoerpern:
      // jede Tasche ist rundum einen Klebespalt groesser und der Armfuss traegt eine
      // runde Endkappe. Mit nur BRIDGE blieben 1,75 mm gegen 2,00 mm Mindestdicke
      // (gemessen, als BRIDGE noch 2,0 war; der Faktor 1,15 geht mit).
      // Spiegel zu ema_topology._build_u -- beide zusammen aendern.
      const gapU = Math.max(0.05, Math.min(0.3, G.magGapMm != null ? G.magGapMm : 0.1));
      const stegU = WAND ? WAND_QACHSE : BRIDGE;
      const barR = Math.max(rPosU - magH - 2*gapU - stegU*1.15, Rbore + magH/2 + 1.0);
      let barLen = tang > 0 ? tang : 2*dHU;
      barLen = Math.min(barLen, 2*(dHU + w*Math.sin(hA)*0.5));
      return [ leg({rPos:rPosU, offset:+dHU, tilt:+hA, length:w, magSign:+1}),
               leg({rPos:rPosU, offset:-dHU, tilt:-hA, length:w, magSign:-1}),
               leg({rPos:barR, offset:-barLen/2, tilt:Math.PI/2, length:barLen, magSign:+1}) ];
    }
    if (shape === "vv") {
      let r0v = rPos, d0v = dH, w0, r1, d1v = dH, w1;
      if (WAND) {
        const s1 = _vSitz(G, hA2, magH, G.magWidth);
        r1 = s1[0]; d1v = s1[1]; w1 = s1[2];
        const gapV = Math.max(0.05, Math.min(0.3, G.magGapMm != null ? G.magGapMm : 0.1));
        w0 = G.magWidth <= 0 ? _slotLaengeMax(Rrot, Rshaft, hA, magH, gapV, WAND_RAND + dL)
                             : G.magWidth;
        const s0 = _sitzAusWaenden(Rrot, hA, magH, gapV, w0, WAND_RAND + dL);
        d0v = s0[0]; r0v = s0[1];
      } else {
        w0 = Math.min(G.magWidth, _maxMagnetWidth(rPos, dH, hA, Rrot, eb));
        r1 = rPos + dL;
        w1 = Math.min(G.magWidth*1.05, _maxMagnetWidth(r1, dH, hA2, Rrot, eb));
      }
      return [ leg({rPos:r0v, offset:+d0v, tilt:+hA, length:w0, magSign:+1, layer:0}),
               leg({rPos:r0v, offset:-d0v, tilt:-hA, length:w0, magSign:-1, layer:0}),
               leg({rPos:r1, offset:+d1v, tilt:+hA2, length:w1, magSign:+1, layer:1}),
               leg({rPos:r1, offset:-d1v, tilt:-hA2, length:w1, magSign:-1, layer:1}) ];
    }
    if (shape === "delta") {
      const stegD = WAND ? WAND_QACHSE : WAND_RAND;
      const armBridge = WAND_RAND + stegD + 1.5*magH;
      const szD = _vSitz(G, hA, magH, G.magWidth, armBridge - magH/2);
      const rPosD = szD[0], dHD = szD[1], w = szD[2];
      const rTip = rPosD + w*Math.cos(hA), yTip = dHD + w*Math.sin(hA);
      const deckR = Math.min(rTip + magH + stegD, Rrot - magH/2 - WAND_RAND);
      let deckLen = tang > 0 ? tang : 1.6*yTip;
      const maxHalf = Math.sqrt(Math.max((Rrot-WAND_RAND)**2 - (deckR+magH/2)**2, 0));
      deckLen = Math.min(deckLen, 2*maxHalf);
      return [ leg({rPos:rPosD, offset:+dHD, tilt:+hA, length:w, magSign:+1}),
               leg({rPos:rPosD, offset:-dHD, tilt:-hA, length:w, magSign:-1}),
               leg({rPos:deckR, offset:-deckLen/2, tilt:Math.PI/2, length:deckLen, magSign:+1}) ];
    }
    if (shape === "pmasynrm") {
      const nL = Math.max(2, parseInt(G.magLayers || 3));
      const mh = magH*0.5, ebp = BRIDGE + mh/2, out = [];
      for (let k=0;k<nL;k++) {
        let rk = rPos + (k - (nL-1)/2)*dL;
        rk = Math.max(rk, Rshaft + mh + 2);
        const hak = Math.max(hA - k*(8*Math.PI/180), 20*Math.PI/180);
        const wk = Math.min(G.magWidth*(0.8+0.15*k), _maxMagnetWidth(rk, dH, hak, Rrot, ebp));
        out.push(leg({rPos:rk, offset:+dH, tilt:+hak, length:wk, thickness:mh, magSign:+1, layer:k}));
        out.push(leg({rPos:rk, offset:-dH, tilt:-hak, length:wk, thickness:mh, magSign:-1, layer:k}));
      }
      return out;
    }
    if (shape === "spm") {
      const poles = G.p*2, pitch = Math.PI*G.rotorOD/poles;
      const arc = (G.poleArcFrac != null ? G.poleArcFrac : 0.83) * pitch;
      return [leg({rPos:Rrot, tilt:Math.PI/2, length:arc, thickness:_surfaceThickness(G), magMode:"radial", placement:"surface"})];
    }
    if (shape === "halbach") {
      // seg straight flat magnets/pole (tiles tangent to OD), rotating magnetisation
      const poles = G.p*2, pitch = Math.PI*G.rotorOD/poles;
      const arcTotal = (G.poleArcFrac != null ? G.poleArcFrac : 0.95) * pitch;
      const seg = Math.max(2, parseInt(G.segPerPole || 6));
      const segAng = (arcTotal/seg)/Rrot;
      const mh = _surfaceThickness(G);
      const length = 2*Rrot*Math.sin(segAng/2)*0.95;
      const rOut = Rrot - BRIDGE;
      const dOut = Math.sqrt(Math.max(rOut*rOut - (length/2)*(length/2), 1.0));
      const rC = dOut - mh/2, out=[];
      for (let s=0;s<seg;s++) {
        const ang = (s-(seg-1)/2)*segAng, tilt = ang + Math.PI/2;
        const cx = rC*Math.cos(ang), cy = rC*Math.sin(ang);
        const rPos2 = cx - (length/2)*Math.cos(tilt), off = cy - (length/2)*Math.sin(tilt);
        const mrot = (s-(seg-1)/2)*(Math.PI/seg)*2;
        out.push(leg({rPos:rPos2, offset:off, tilt:tilt, length:length,
                      thickness:mh, magMode:"radial", magRot:mrot, placement:"surface_flat"}));
      }
      return out;
    }
    if (shape === "spoke") {
      // Die Tasche endet nicht am Magneten: an beiden Enden sitzt eine Kappe vom
      // Radius magThick/2 + Spalt. Mit Rshaft + 1.0 schnitt sie ab 1,8 mm Dicke in
      // die Bohrung. Spiegel zu ema_topology._build_spoke.
      // Die Waende stehen jetzt ausdruecklich: aussen WAND_SPEICHE_A, innen
      // WAND_SPEICHE_I -- und sie gelten fuer die TASCHE. Der Klebespalt geht
      // ZWEIMAL ein (die Kappe sitzt um gap ausserhalb des Magnetendes und traegt
      // selbst den Radius magH/2 + gap); mit nur einem stand die Wand bei 1,20 mm,
      // obwohl 1,3 gemeint war. Spiegel zu ema_topology._build_spoke.
      const gapS = Math.max(0.05, Math.min(0.3, G.magGapMm != null ? G.magGapMm : 0.1));
      const offS = String(G.magTascheOffen || "nein").trim().toLowerCase();
      const offA = (offS === "aussen" || offS === "beide");
      const offI = (offS === "innen"  || offS === "beide");
      const saumA = offA ? 0 : WAND_SP_A + magH/2 + 2*gapS;
      const saumI = offI ? 0 : WAND_SP_I + magH/2 + 2*gapS;
      const rStart = Rshaft + saumI;
      const length = Math.max(Rrot - saumA - rStart, 5.0);
      return [leg({rPos:rStart, tilt:0, length:length, magMode:"tangential", magSign:+1})];
    }
    // bar / fallback: single tangential flat magnet
    return [leg({tilt:Math.PI/2})];
  }
  // <<MIRROR-END>>

  // Mirror of ema_analysis._orient_factor: air-gap flux scaling when the magnet
  // magnetisation is rotated 90° (magOrient="longitudinal"). Keeps the live field
  // amplitude responding to the orientation toggle in the SAME direction as the FDM.
  function _magOrientFactor(G) {
    if (G.magOrient !== "longitudinal") return 1.0;
    const legs = magnetLegs(G);
    const cp = 1.0, sp = 0.0;
    let num = 0, den = 0;
    for (const lg of legs) {
      const lx = Math.cos(lg.tilt), ly = Math.sin(lg.tilt);
      let mdx, mdy;
      if (lg.magMode === "tangential") { mdx = -sp; mdy = cp; }
      else if (lg.magMode === "radial") { mdx = Math.cos(lg.magRot); mdy = Math.sin(lg.magRot); }
      else { mdx = -ly; mdy = lx; }
      den += Math.abs(mdx*cp + mdy*sp);
      num += Math.abs((-mdy)*cp + mdx*sp);
    }
    return den < 1e-6 ? 1.0 : num/den;
  }

  function smoothMu(dist) {
    const edge = Math.max(0, Math.min(1, dist + 0.5));
    return 500.0 * (1.0 - edge) + 1.0 * edge;
  }

  function rasterizeGeometry() {
    if (!isSolverInit) initSolverArrays();
    const N = GRID_SIZE;
    const maxD = GEOM.statorOD * 1.1;
    const gs = N / maxD, center = N / 2;
    const rSO = (GEOM.statorOD / 2) * gs, rSI = (GEOM.statorID / 2) * gs;
    const rRO = (GEOM.rotorOD  / 2) * gs, rSh = (GEOM.shaftD    / 2) * gs;
    const slotD = GEOM.slotDepth * gs;
    gridJ.fill(0);
    for (let y = 0; y < N; y++) {
      for (let x = 0; x < N; x++) {
        const dx = x - center, dy = y - center;
        const r  = Math.sqrt(dx*dx + dy*dy);
        const dSt = Math.max(rSI - r, r - rSO);
        const rBore = (GEOM.shaftBoreD > 0 ? (GEOM.shaftBoreD/2)*gs : 0);
        const dRo = Math.max(rBore - r, r - rRO);   // iron band [bore, rotorOD] (steel shaft)
        gridMu[y*N+x] = smoothMu(Math.min(dSt, dRo));
      }
    }
    // Low-permeability AIR carved into the rotor iron so the variable-µ solver lets
    // the flux refract AROUND it (µr≈1 vs. µr=500). Mirror of ema_analysis._rasterise:
    // balance-bolt holes, flux-barrier slots (q/d) and custom (designer) barriers —
    // all rotate WITH the rotor (PHYS.angle). The hollow-shaft bore is already air
    // (handled in the iron-ring loop above via rBore); the surroundings are air by
    // default (gridMu initialised to 1).
    {
      const P2 = GEOM.p*2, a0 = PHYS.angle;
      // Die Laeuferteile der magnetlosen Bauarten: Nuten, Wickelfenster und
      // die Luft zwischen den Schenkelpolen sind magnetisch Luft und gehoeren
      // ins Raster -- sonst zeigte die Leinwand Pole und die Feldlinien eine
      // Vollscheibe. Der Strom darin ist NICHT eingepraegt (magnetostatisch);
      // das sagt `feld_darstellbar` und die Zeile unter der Leinwand.
      const _ltR = (typeof _laeuferTeileAktiv === "function")
                     ? _laeuferTeileAktiv() : null;
      const _stR = (typeof _staenderTeileAktiv === "function")
                     ? _staenderTeileAktiv() : null;
      // Womit eine eingepraegte GLEICHdurchflutung gewichtet wird.
      //
      // Die Staendernut unten schreibt je Zelle den NUTstrom; die Durchflutung
      // einer Nut ist also `I * Zellen_je_Nut`. Damit eine Erregerspule mit F
      // Amperewindungen im selben Bild dasselbe Gewicht hat wie eine Nut mit
      // I Ampere, bekommt `rastere` diesen Umrechner -- dann steht das
      // Verhaeltnis Spule:Nut genau auf F:I. Geraten wird daran nichts.
      const _zellenJeNut = Math.max(1, Math.ceil(slotD))
        * Math.max(1, Math.ceil(rSI * (2*Math.PI/Math.max(GEOM.slots,1))
                                * GEOM.slotWidthRatio));
      const _jNut = _zellenJeNut * (5 / N);
      if (typeof LAEUFER !== "undefined") {
        // Der Laeufer dreht mit (`a0`), der Staender steht.
        if (_ltR) LAEUFER.rastere(gridMu, N, center, gs, _ltR, a0, gridJ, _jNut);
        if (_stR) LAEUFER.rastere(gridMu, N, center, gs, _stR, 0, gridJ, _jNut);
      }
      if (GEOM.genBalanceBolts) {
        const TH={M4:4,M5:5,M6:6,M8:8,M10:10,M12:12,M16:16,M20:20};
        const nom=TH[GEOM.balanceBoltThread||'M6']||6, hr=((nom+0.4)/2)*gs;
        const pcr=(GEOM.balanceBoltCircleD>0?GEOM.balanceBoltCircleD/2
                  :GEOM.shaftD/2+(GEOM.rotorOD/2-GEOM.shaftD/2)*0.5)*gs;
        const off=(GEOM.balanceBoltOffsetDeg||0)*Math.PI/180, nb=Math.max(2,P2), ri=Math.ceil(hr);
        for(let bi=0;bi<nb;bi++){
          const a=off+a0+bi*2*Math.PI/nb, hx=center+pcr*Math.cos(a), hy=center+pcr*Math.sin(a);
          for(let yy=-ri;yy<=ri;yy++)for(let xx=-ri;xx<=ri;xx++){
            if(xx*xx+yy*yy<=hr*hr){const ix=Math.floor(hx+xx),iy=Math.floor(hy+yy);
              if(ix>=0&&ix<N&&iy>=0&&iy<N)gridMu[iy*N+ix]=1;}
          }
        }
      }
      if (GEOM.genFluxBarrierQ || GEOM.genFluxBarrierD) {
        const fbw=Math.max(0.5,Math.min(40,GEOM.fluxBarrierWidth||3))*gs;
        const fbd=Math.max(1,Math.min(120,GEOM.fluxBarrierDepth||10))*gs;
        const rout=rRO-2*gs, rin=Math.max(rSh+1*gs, rout-fbd), angs=[];
        if(GEOM.genFluxBarrierD)for(let i=0;i<P2;i++)angs.push(a0+i*2*Math.PI/P2);
        if(GEOM.genFluxBarrierQ)for(let i=0;i<P2;i++)angs.push(a0+(i+0.5)*2*Math.PI/P2);
        for(const a of angs){
          const ca=Math.cos(a),sa=Math.sin(a);
          for(let rr=rin;rr<=rout;rr+=0.5)for(let w=-fbw/2;w<=fbw/2;w+=0.5){
            const ix=Math.floor(center+rr*ca - w*sa), iy=Math.floor(center+rr*sa + w*ca);
            if(ix>=0&&ix<N&&iy>=0&&iy<N)gridMu[iy*N+ix]=1;
          }
        }
      }
      const cbars=GEOM.customBarriers||[];
      for(let p=0;p<(cbars.length?P2:0);p++){
        const pa=p*2*Math.PI/P2+a0, cpa=Math.cos(pa), spa=Math.sin(pa);
        for(const bar of cbars){
          const pts=bar.pts||[], hw=Math.max(0.5,(bar.width||3))/2*gs;
          const gp=pts.map(q=>[(q[0]*cpa-q[1]*spa)*gs,(q[0]*spa+q[1]*cpa)*gs]);
          for(let s=0;s<gp.length-1;s++){
            const ax=gp[s][0],ay=gp[s][1],dx=gp[s+1][0]-ax,dy=gp[s+1][1]-ay,ll=dx*dx+dy*dy;
            if(ll<1e-6)continue;
            const mnx=Math.floor(center+Math.min(ax,ax+dx)-hw),mxx=Math.ceil(center+Math.max(ax,ax+dx)+hw);
            const mny=Math.floor(center+Math.min(ay,ay+dy)-hw),mxy=Math.ceil(center+Math.max(ay,ay+dy)+hw);
            for(let iy=Math.max(0,mny);iy<=Math.min(N-1,mxy);iy++)for(let ix=Math.max(0,mnx);ix<=Math.min(N-1,mxx);ix++){
              const Xc=ix-center,Yc=iy-center;
              let t=((Xc-ax)*dx+(Yc-ay)*dy)/ll; t=t<0?0:(t>1?1:t);
              const cx=ax+t*dx,cy=ay+t*dy;
              if((Xc-cx)*(Xc-cx)+(Yc-cy)*(Yc-cy)<=hw*hw)gridMu[iy*N+ix]=1;
            }
          }
        }
      }
    }
    const slots = GEOM.slots, step = 2*Math.PI/slots, sw = step * GEOM.slotWidthRatio;
    // Eine Bauart mit EIGENEM Staender bekommt keine Drehstromnuten.
    //
    // Die Gleichstrommaschine traegt Schenkelpole mit Gleicherregung; das
    // dreiphasige Nutfeld darueberzulegen ergab ein Drehfeld auf einer
    // Maschine, die keines hat -- gemeldet als „die Magnetfelder in der
    // fremderregten Gleichstrommaschine sind auch falsch". Ihre Erregung steht
    // schon im Raster (oben, ueber `durchflutung_A`).
    const _dreiphasig = _staenderfeldAktiv();
    for (let s = 0; _dreiphasig && s < slots; s++) {
      const ang = s*step, elAng = ang*GEOM.p;
      // FELDwinkel, nicht Laeuferwinkel: bei der ASM laeuft das Drehfeld dem
      // Kaefig um den Schlupf voraus, und das ist das Sichtbare an der Bauart.
      // Bei jeder Synchronmaschine ist `feldWinkel === angle` (s. stepPhysics).
      const _fw = PHYS.feldWinkel * GEOM.p;
      let cur = PHYS.id*Math.cos(elAng - _fw) - PHYS.iq*Math.sin(elAng - _fw);
      // Das ausgefallene System fuehrt KEINEN Strom. Damit zeigt das Feldbild
      // den Fehlerfall selbst: bei `sektoriert` fehlt ein ganzer
      // Umfangsabschnitt, und die Unsymmetrie ist zu sehen statt nur benannt.
      if (PHYS.ausfallSystem >= 0 && PHYS.sysJeNut
          && PHYS.sysJeNut[s] === PHYS.ausfallSystem) cur = 0;
      const ca = Math.cos(ang), sa = Math.sin(ang);
      for (let r2 = 0; r2 < Math.ceil(slotD); r2++) {
        const rr = rSI + r2, w = rr*step*GEOM.slotWidthRatio, ws = Math.ceil(w);
        for (let ww = -ws/2; ww <= ws/2; ww++) {
          const px = center + rr*ca - ww*sa, py = center + rr*sa + ww*ca;
          const ix = Math.floor(px), iy = Math.floor(py);
          if (ix>=0 && ix<N && iy>=0 && iy<N) {
            const idx = iy*N+ix; gridMu[idx] = 1; gridJ[idx] = cur*(5/N);
          }
        }
      }
    }
    // Magnets – numerical curl(M) approach; placement from magnetLegs()
    // (mirror of ema_topology / ema_analysis._rasterise).
    const Mx_acc = new Float32Array(N*N);
    const My_acc = new Float32Array(N*N);
    const poles  = GEOM.p*2;
    // Eine Bauart OHNE Magnete bekommt auch keine magnetisierten Zellen. Die
    // Zeichnung liess die Magnete schon weg, das RASTER nicht -- gemeldet als
    // „bei der Simulation der ASM sieht es so aus, als waeren die Magnete der
    // PSM noch enthalten", und genau so war es: das Feldbild einer
    // Asynchronmaschine war ein PM-Feld. Dieselbe Frage wie in `drawRotor`,
    // damit Bild und Feld nicht auseinanderfallen.
    const legs   = _hatMagnete() ? magnetLegs(GEOM) : [];
    // ×4 restores the amplitude lost when the magnet rasterisation switched from
    // sub-pixel accumulation (the old l+=0.5/t+=0.5 loops hit each pixel ~2×2 times)
    // to a clean one-contribution-per-pixel mask — without it the magnet flux is ~4×
    // too weak vs. the stator and field lines no longer cross the magnets perpendicular.
    const Jm_amp = (8000 / N) * 4 * _magOrientFactor(GEOM);   // 90°-rotation flux scaling
    const rRO_mm = GEOM.rotorOD/2;

    for (let p2 = 0; p2 < poles; p2++) {
      const pA   = p2*(2*Math.PI/poles) + PHYS.angle;
      const mSign = p2%2===0 ? 1 : -1;
      const cpA = Math.cos(pA), spA = Math.sin(pA);
      for (const lg of legs) {
        const lx = Math.cos(pA+lg.tilt), ly = Math.sin(pA+lg.tilt);
        let mdx, mdy;
        if (lg.magMode === "tangential") { mdx = -spA; mdy = cpA; }
        else if (lg.magMode === "radial") { const b = pA+lg.magRot; mdx = Math.cos(b); mdy = Math.sin(b); }
        else { mdx = -ly; mdy = lx; }            // "perp"
        // 90° re-orientation (short side N/S) — mirror of ema_analysis._rasterise
        if (GEOM.magOrient === "longitudinal") { const _t = mdx; mdx = -mdy; mdy = _t; }
        const Jm = Jm_amp * mSign * lg.magSign;
        const mH = lg.thickness * gs;
        // Clean per-pixel top-hat (mirror of ema_analysis._rasterise's boolean
        // mask): visit each pixel of the magnet's bounding box ONCE and test the
        // inside predicate, so Mx/My accumulate exactly one contribution per pixel.
        // The old sub-pixel stepping (l+=0.5,t+=0.5) hit interior pixels ~4× and
        // ragged edge pixels fewer times — that sampling-density bumpiness, run
        // through curl(M), injected spurious equivalent currents that showed up as
        // tight, strange flux loops around every magnet.
        if (lg.placement === "surface") {
          const centerAng = pA + lg.offset / rRO_mm;
          const halfArc = (lg.length/2) / rRO_mm;
          const r1 = rRO, r0 = r1 - mH;   // outer rotor band (rRO already in grid units)
          const ri = Math.ceil(r1);
          const yA=Math.max(0,Math.floor(center-ri)), yB=Math.min(N-1,Math.ceil(center+ri));
          const xA=Math.max(0,Math.floor(center-ri)), xB=Math.min(N-1,Math.ceil(center+ri));
          for(let iy=yA;iy<=yB;iy++)for(let ix=xA;ix<=xB;ix++){
            const ddx=ix-center, ddy=iy-center, rr=Math.sqrt(ddx*ddx+ddy*ddy);
            if(rr<r0||rr>r1)continue;
            let d=Math.atan2(ddy,ddx)-centerAng+Math.PI;
            d-=2*Math.PI*Math.floor(d/(2*Math.PI));
            if(Math.abs(d-Math.PI)<=halfArc){ const idx=iy*N+ix; gridMu[idx]=1.5; Mx_acc[idx]+=Jm*mdx; My_acc[idx]+=Jm*mdy; }
          }
        } else {
          const sX = center + lg.rPos*gs*cpA - lg.offset*gs*spA;
          const sY = center + lg.rPos*gs*spA + lg.offset*gs*cpA;
          const tx = -ly, ty = lx;
          const w = lg.length*gs, h = mH;
          let minX=1e9,maxX=-1e9,minY=1e9,maxY=-1e9;   // rotated-rect bounding box
          for(const lv of [0,w])for(const tv of [-h/2,h/2]){
            const cx=sX+lv*lx+tv*tx, cy=sY+lv*ly+tv*ty;
            if(cx<minX)minX=cx; if(cx>maxX)maxX=cx; if(cy<minY)minY=cy; if(cy>maxY)maxY=cy;
          }
          const xA=Math.max(0,Math.floor(minX)-1), xB=Math.min(N-1,Math.ceil(maxX)+1);
          const yA=Math.max(0,Math.floor(minY)-1), yB=Math.min(N-1,Math.ceil(maxY)+1);
          for(let iy=yA;iy<=yB;iy++)for(let ix=xA;ix<=xB;ix++){
            const ddx=ix-sX, ddy=iy-sY;
            const lc=ddx*lx+ddy*ly, tc=ddx*tx+ddy*ty;
            if(lc>=0 && lc<=w && Math.abs(tc)<=h/2){ const idx=iy*N+ix; gridMu[idx]=1.5; Mx_acc[idx]+=Jm*mdx; My_acc[idx]+=Jm*mdy; }
          }
        }
      }
    }
    // J_z += curl(M) = ∂My/∂x − ∂Mx/∂y  (central differences)
    for (let y = 1; y < N-1; y++) {
      for (let x = 1; x < N-1; x++) {
        const dMy_dx = (My_acc[y*N+(x+1)] - My_acc[y*N+(x-1)]) * 0.5;
        const dMx_dy = (Mx_acc[(y+1)*N+x] - Mx_acc[(y-1)*N+x]) * 0.5;
        gridJ[y*N+x] += dMy_dx - dMx_dy;
      }
    }
  }

  function solveField() {
    // Variable-permeability operator ∇·(ν∇A) = −J with harmonic-mean face ν (ν=1/µ),
    // mirroring the Python FDM (ema_analysis._build_fv_matrix). THIS is what makes the
    // field REFRACT around low-permeability AIR — the flux barriers, the hollow-shaft
    // bore, the magnet pockets and the surrounding air all carry µr≈1 vs. µr=500 iron,
    // so flux avoids them and concentrates in the iron. The old constant Laplacian only
    // scaled the source by µ and ignored the air's reluctance entirely. In a uniform
    // region the amplitude is preserved: Σf = 4/µ ⇒ J/Σf = µ·J/4 (= the old µ·J·0.25).
    const N = GRID_SIZE, iter = PHYS.ultraSlow ? 100 : 40;
    for (let k=0;k<iter;k++) {
      for (let y=1;y<N-1;y++) for (let x=1;x<N-1;x++) {
        const i = y*N+x;
        const nuC = 1.0/gridMu[i];
        const nuE = 1.0/gridMu[i+1], nuW = 1.0/gridMu[i-1];
        const nuN = 1.0/gridMu[i+N], nuS = 1.0/gridMu[i-N];
        const fE = 2*nuC*nuE/(nuC+nuE), fW = 2*nuC*nuW/(nuC+nuW);
        const fN = 2*nuC*nuN/(nuC+nuN), fS = 2*nuC*nuS/(nuC+nuS);
        const sumF = fE+fW+fN+fS;
        const tgt = (fE*gridA[i+1]+fW*gridA[i-1]+fN*gridA[i+N]+fS*gridA[i-N] + gridJ[i]) / sumF;
        gridA[i] += 1.4*(tgt - gridA[i]);
      }
    }
  }

  const dt_base = 0.0005;
  // Spiegel von ema_analysis.estimate_dq_currents -- per node geprueft.
  // Der Marker steht ALLEIN auf seiner Zeile: die Extraktion schneidet
  // direkt dahinter, und ein Kommentartext dahinter landete als nackter
  // Ausdruck im erzeugten JS (gemessen: SyntaxError beim ersten Versuch).
  // <<MTPA-START>>
  // Der d-Strom im Momentmaximum je Ampere. Diese eine Formel steht zweimal --
  // hier und in Python --, weil die Vorschau sechzig Mal je Sekunde rechnet und
  // nicht fragen kann. `test_livesim.py` fuehrt BEIDE aus und vergleicht sie;
  // laufen sie auseinander, zeigt die Vorschau ein anderes Moment als der Lauf.
  function _mtpaId(psi, Ld, Lq, iq) {
    const dL = Lq - Ld;
    if (!(dL > 1e-12) || !(psi > 0)) return 0;          // nicht salient -> reines q
    return (psi - Math.sqrt(psi*psi + 8*dL*dL*iq*iq)) / (4*dL);
  }
  // <<MTPA-END>>

  // Die Elektrik der gezeichneten Maschine holen. Gerechnet wird auf dem
  // SERVER (compute_advanced_em + umrichter) -- psi, Ld und Lq hier noch einmal
  // herzuleiten waere die naechste Abschrift, die auseinanderlaeuft.
  async function livePhysikLaden() {
    const info = document.getElementById('live_phys_info');
    if (info) info.innerHTML = '<span style="color:#888">… rechnet</span>';
    try {
      const payload = await buildPayload();
      const r = await fetch('/umrichter', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body: JSON.stringify({payload, maschine:true})});
      const d = await r.json();
      const m = d.maschine || {};
      if (!r.ok || d.error || m.fehler) {
        if (info) info.innerHTML = '<span style="color:#e57373">' +
          escHtml(d.error || m.fehler || ('HTTP '+r.status)) + '</span>';
        return;
      }
      PHYS.Psi = m.psi_pm_Wb;  PHYS.Ld = m.Ld_H;  PHYS.Lq = m.Lq_H;
      PHYS.xi = m.xi || 1;     PHYS.rpmBase = m.rpm_base || 5000;
      PHYS.schlupf = Math.max(0, Math.min(0.9, m.schlupf || 0));
      PHYS.iMax = m.i_max_A;   PHYS.vDc = m.v_dc_V;
      PHYS.kModule = m.n_module || 1;
      PHYS.sysJeNut = (d.system_je_nut && d.system_je_nut.length) ? d.system_je_nut : null;
      PHYS.echt = true;
      const dm = document.getElementById('disp_module');
      if (dm) dm.innerText = PHYS.kModule + (PHYS.kModule === 1 ? ' Modul' : ' Module');
      if (info) info.innerHTML =
        'ψ ' + (PHYS.Psi*1000).toFixed(1) + ' mWb · L<sub>d</sub> ' +
        (PHYS.Ld*1e6).toFixed(1) + ' µH · L<sub>q</sub> ' + (PHYS.Lq*1e6).toFixed(1) +
        ' µH · ξ ' + PHYS.xi.toFixed(2) + '<br>Eckdrehzahl ' +
        Math.round(PHYS.rpmBase).toLocaleString() + ' 1/min · Grenzen ' +
        Math.round(PHYS.vDc) + ' V / ' + Math.round(PHYS.iMax) + ' A' +
        (PHYS.kModule > 1 ? ' (auf 1 Wdg/Nut, ' + PHYS.kModule + ' Module)' : '') +
        // Woher die Zahlen kommen, und was in ihnen NICHT steckt. Eine
        // Vorschau, die fuer jede Bauart gleich aussieht, laedt dazu ein,
        // sie fuer jede Bauart gleich zu lesen.
        (PHYS.schlupf > 0
          ? '<br>Schlupf ' + (PHYS.schlupf*100).toFixed(2) +
            ' % — das Drehfeld laeuft dem Laeufer voraus'
          : '') +
        (m.ohne_salienz
          ? '<br><span style="color:#c9a227">ohne Salienz: diese Bauart ' +
            'rechnet hier kein L<sub>d</sub>/L<sub>q</sub></span>'
          : '') +
        '<br><span style="color:#81c784">' +
        (m.modell ? m.modell + ' — ' + (m.quelle || '') : 'aus der Geometrie') +
        '</span>';
      livePhysikAusfall();
    } catch (e) {
      if (info) info.innerHTML = '<span style="color:#e57373">' + escHtml(String(e)) + '</span>';
    }
  }

  function livePhysikAusfall() {
    const an = document.getElementById('chk_modul_aus');
    // Ohne mehrere Module gibt es keinen n-1-Fall -- dann ist ein Ausfall der
    // Totalausfall, und den als "ein Modul weniger" zu zeigen waere gelogen.
    PHYS.ausfallSystem = (an && an.checked && PHYS.kModule > 1) ? 0 : -1;
  }

  function stepPhysics() {
    const dt = PHYS.ultraSlow ? 0.000005 : dt_base*PHYS.timeScale;
    if (isNaN(PHYS.omega)) PHYS.omega = 0;
    GEOM.airGap = Math.max(0.1, (GEOM.statorID - GEOM.rotorOD)/2);
    // Direct speed setpoint: pin the rotor to the chosen rpm BEFORE the current
    // update so field weakening (i_d) reflects it — instead of the torque-driven
    // run-up. Same 9.55 (≈30/π) factor as the rpm display so the value matches.
    if (PHYS.rpmSet > 0) PHYS.omega = PHYS.rpmSet / 9.55;
    // Stromgrenze, Eckdrehzahl und d/q kommen aus der Maschine, sobald sie
    // geholt wurde. Vorher die alten Festwerte -- damit die Vorschau auch ohne
    // Serverantwort laeuft, aber `PHYS.echt` sagt, woran man sieht.
    //
    // Bei n-1 traegt nur noch (k-1)/k der Wicklung: das deckelt sowohl den
    // Strom als auch das erreichbare Moment, genau wie `ema_umrichter.ausfall`.
    const _rest = (PHYS.ausfallSystem >= 0 && PHYS.kModule > 1)
                    ? (PHYS.kModule - 1) / PHYS.kModule : 1.0;
    const _iLim = PHYS.iMax * _rest;
    const tiq = Math.min((PHYS.load+20)*1.5, _iLim);
    // MTPA statt des festen -0,4: bei einem salienten Laeufer bringt der
    // negative d-Strom Reluktanzmoment, und wieviel, haengt an psi, Ld und Lq.
    let tid = _mtpaId(PHYS.Psi, PHYS.Ld, PHYS.Lq, tiq);
    const _rpmNow = Math.abs(PHYS.omega*9.55), _rpmB = Math.max(PHYS.rpmBase, 1);
    if (_rpmNow > _rpmB) {
      // Feldschwaechung wie in estimate_dq_currents: proportional zur Last,
      // umgekehrt zur Salienz, gedeckelt bei 1,5.
      const fw = Math.min((_rpmNow - _rpmB) / _rpmB, 1.5);
      tid -= tiq * fw / Math.max(PHYS.xi, 1e-6);
    }
    tid -= PHYS.id_manual;
    PHYS.iq += (tiq - PHYS.iq)*0.1;
    PHYS.id += (tid - PHYS.id)*0.1;
    PHYS.torque = 1.5*GEOM.p*(PHYS.Psi*PHYS.iq + (PHYS.Ld-PHYS.Lq)*PHYS.id*PHYS.iq);
    if (PHYS.rpmSet <= 0) {   // free run-up only when no setpoint is given
      const T_net = PHYS.torque - Math.sign(PHYS.omega)*PHYS.load - (0.01+Math.abs(PHYS.omega)*0.00001)*PHYS.omega;
      PHYS.omega += (T_net/PHYS.J)*dt;
      const mxW = 30000/9.55;
      PHYS.omega = Math.max(-mxW, Math.min(mxW, PHYS.omega));
    }
    PHYS.angle += PHYS.omega*dt;
    // n_syn = n / (1 - s): der Laeufer laeuft dem Feld um den Schlupf nach.
    // Bei s = 0 wird der Feldwinkel GLEICHGESETZT statt mit derselben Zahl
    // fortgeschrieben -- so bleibt jede Synchronrechnung Ziffer fuer Ziffer
    // dieselbe und kann nicht ueber die Laufzeit auseinanderdriften.
    if (PHYS.schlupf > 0) {
      PHYS.feldWinkel += (PHYS.omega / (1 - PHYS.schlupf)) * dt;
    } else {
      PHYS.feldWinkel = PHYS.angle;
    }
  }

  function draw() {
    const maxD = GEOM.statorOD*1.1;
    SCALE = Math.min(cvsW, cvsH)/maxD;
    ctx.fillStyle = "#111"; ctx.fillRect(0,0,cvsW,cvsH);
    ctx.save(); ctx.translate(CX, CY);
    drawStator();
    ctx.save(); ctx.rotate(PHYS.angle); drawRotor(); ctx.restore();
    drawFluxLines(maxD);
    ctx.restore();

    // Debug bar – always visible, proves canvas is alive
    _frameCount++;
    const rpm = Math.round(PHYS.omega * 9.55);
    ctx.fillStyle = "rgba(0,0,0,0.55)";
    ctx.fillRect(0, cvsH - 22, cvsW, 22);
    ctx.fillStyle = _frameCount % 60 < 30 ? "#0f0" : "#0a0";
    ctx.font = "11px monospace";
    ctx.fillText(
      "▶ frame:" + _frameCount + "  " +
      cvsW + "×" + cvsH + "  " +
      "rpm:" + rpm + "  " +
      "D_a:" + GEOM.statorOD + "mm  " +
      "slots:" + GEOM.slots + "  " +
      "p=" + GEOM.p +
      (_lastErr ? "  ERR:" + _lastErr : ""),
      6, cvsH - 6
    );

    updateUI();
  }

  // ── Laeufer ohne Magnete: die Teile kommen aus Python ───────────────────
  //
  // ASM (Kaefig/Schleifring), EESM (Schenkelpole), GSM (Anker + Staenderpole)
  // und SynRM (Flussbarrieren) werden NICHT hier gerechnet. `POST /laeuferbild`
  // liefert fertige Zeichenteile aus genau den Funktionen, die die Maschine
  // rechnen -- eine zweite Geometriefassung im Browser waere die naechste
  // `magnetLegs`-Drift, und die ist in CLAUDE.md als gefaehrlichste Stelle des
  // Werkzeugs vermerkt. Die PSM bleibt unberuehrt auf ihrem alten Weg.
  let _laeuferBild = null;      // Antwort von /laeuferbild
  let _laeuferMarke = "";       // wofuer sie gilt
  let _laeuferTimer = null;

  // Die Marke entscheidet, WANN neu geholt wird. Sie traegt nur, was die
  // Laeufergeometrie wirklich bewegt -- eine Marke ueber das ganze GEOM liesse
  // bei jedem Tastendruck am Fahrzeuggewicht einen Serveraufruf los.
  function _laeuferMarkeBauen() {
    const g = GEOM;
    return [g.machineType || "pmsm", g.rotorType || "", g.p, g.slots,
            g.rotorOD, g.statorID, g.statorOD, g.shaftD, g.shaftBoreD,
            g.axialLen, g.magShape, g.magWidth, g.magThick, g.magDist,
            g.magDepthRel, g.magAngle, g.magLayers, g.conductorsPerSlot,
            // Alles, was den LAEUFER der magnetlosen Bauarten bewegt. Ohne
            // diese Felder aenderte sich die Zeichnung nicht, obwohl der
            // Server eine andere liefern wuerde -- und eine Marke, die eine
            // Aenderung nicht bemerkt, ist schlimmer als keine: sie friert
            // die alte Maschine ein und sieht dabei richtig aus.
            g.erregerSpuleForm, g.erregerSpuleFuellung,
            g.polSchuhBreiteMm, g.polKernBreiteMm, g.erregerSpuleDickeMm,
            g.erregerSpuleHoeheMm, g.polKegelWinkelGrad,
            g.daempferkaefig, g.daempferStaebeJePol,
            g.daempferMat, g.bZielT, g.poleArcFrac, g.slotWidthRatio,
            g.slotDepth, g.rotorBars, g.armatureWinding,
            // Der Reluktanzlaeufer und die Kaefignut in Millimetern.
            g.synrmBarrieren, g.synrmIsolationsgrad, g.synrmStegMm,
            g.synrmBetaGrad, g.laeuferNutTiefeMm, g.laeuferNutBreiteMm,
            g.laeuferStegMm, g.rotorSkewSlots, g.rotorTurnsPerSlot
           ].join("|");
  }

  function _laeuferArt() { return (GEOM.machineType || "pmsm"); }

  // Zeichnet DIESE Bauart Magnete aus `magnetLegs`?
  //
  // Die Frage haing frueher daran, ob TEILE angekommen sind -- und das ist
  // etwas anderes: eine leere Teileliste heisst „nichts zu zeichnen", nicht
  // „zeichne Magnete". Blieb sie leer (nicht auslegbarer Kaefig, Abruf noch
  // unterwegs, Serverfehler), bekam eine Asynchronmaschine die Magnete einer
  // PSM ins Bild UND ins Raster. Genau so gemeldet. Die Antwort kommt aus
  // `ema_maschinenart` ueber `/laeuferbild`; solange sie fehlt, gilt die eine
  // Bauart, die ihre Magnete selbst zeichnet.
  function _hatMagnete() {
    const b = _laeuferBild;
    if (b && _laeuferMarke === _laeuferMarkeBauen()
        && typeof b.hat_magnete === "boolean") return b.hat_magnete;
    return _laeuferArt() === "pmsm";
  }

  // Bedeutet der dreiphasige Nutstrom der Vorschau fuer diese Bauart etwas?
  // Bei der Gleichstrommaschine nicht: ihr Staender traegt Schenkelpole mit
  // Gleicherregung, kein Drehfeld.
  function _staenderfeldAktiv() {
    const b = _laeuferBild;
    if (b && _laeuferMarke === _laeuferMarkeBauen()
        && typeof b.staenderfeld === "boolean") return b.staenderfeld;
    return true;
  }

  // Die Teile, die JETZT gelten -- oder null. Die Marke wird mitgeprueft:
  // waehrend der Abruf laeuft, gehoeren die alten Teile zu einer anderen
  // Maschine, und die zu zeichnen waere schlimmer als sie wegzulassen.
  function _laeuferTeileAktiv() {
    if (!_laeuferBild || _laeuferMarke !== _laeuferMarkeBauen()) return null;
    const t = _laeuferBild.teile;
    return (t && t.length) ? t : null;
  }
  function _staenderTeileAktiv() {
    if (!_laeuferBild || _laeuferMarke !== _laeuferMarkeBauen()) return null;
    const t = _laeuferBild.staender;
    return (t && t.length) ? t : null;
  }

  // Wieviel vom Hinweis STEHT, bevor man klickt. Zwei Zeilen im schmalen
  // Vorschaufenster; alles darueber waechst dem Kasten davon.
  const _HINWEIS_KURZ = 85;

  function _hinweisMalen(el) {
    const v = el.dataset.voll || "";
    // Ein ⚠ ist der Grund, warum der Hinweis ueberhaupt dasteht -- also faengt
    // die Kurzfassung DORT an und nicht bei der Beschreibung der Bauart.
    const i = v.indexOf("\u26A0");
    const kern = i >= 0 ? v.slice(i) : v;
    if (el.dataset.offen === "1") {
      el.textContent = v + "   \u2303 weniger";
      el.style.maxHeight = "11em";
      el.style.overflowY = "auto";
      return;
    }
    // Zugeklappt wird NICHT gescrollt: ein Rollbalken in einem 250 px breiten
    // Kasten verdeckt gerade das „mehr", auf das er hinweist.
    el.style.maxHeight = "none";
    el.style.overflowY = "hidden";
    el.textContent = kern.length > _HINWEIS_KURZ
      ? kern.slice(0, _HINWEIS_KURZ).replace(/\s+\S*$/, "") + " \u2026  \u2304 mehr"
      : kern;
  }

  // Was die Bauart ABGELEITET hat -- und ein Knopf, der es in die Felder
  // schreibt. Gemeldet als „auch waeren vorgaben hilfreich": die
  // Millimeterfelder tragen `0 = ableiten`, und eine 0 sagt nicht, WAS
  // abgeleitet wurde. Gerechnet wird hier nichts; die Zahlen kommen aus
  // `/laeuferbild` (`masse`), also aus derselben Quelle wie die Zeichnung.
  // Eine zweite Ableitung im JavaScript waere die naechste stille Drift.
  function _masseVorgabeZeigen() {
    const b = _laeuferBild;
    const gilt = b && _laeuferMarke === _laeuferMarkeBauen();
    const liste = (gilt && Array.isArray(b.masse)) ? b.masse : [];
    const befund = (gilt && Array.isArray(b.masse_befund)) ? b.masse_befund : [];
    // Ein Befund ohne Weg ist eine Sackgasse — gemeldet als „ich kann damit
    // nichts anfangen". Der Server rechnet die Wege (`ema_eesm_cad.entlastung`,
    // jeder gegen dasselbe Tor nachgeprueft) und schickt sie mit dem Laeuferbild.
    const vors  = (gilt && Array.isArray(b.vorschlaege)) ? b.vorschlaege : [];
    const vhin  = (gilt && Array.isArray(b.vorschlag_hinweise)) ? b.vorschlag_hinweise : [];
    window._laeuferVorschlaege = vors;
    // Nur EINMAL zeigen: die Vorschlaege gelten dem Laeufer, nicht der Gruppe,
    // in der die Meldung zufaellig steht.
    let vorsGezeigt = false;
    document.querySelectorAll(".masse-vorgabe").forEach(el => {
      // Nur in der Gruppe zeigen, die zu dieser Bauart sichtbar ist.
      const grp = el.closest(".art-feld, .input-group");
      const sichtbar = grp && grp.offsetParent !== null;
      if (!liste.length || !sichtbar) { el.style.display = "none"; return; }
      const txt = liste.map(m =>
        `${_esc(m.label)} <b>${(+m.wert).toFixed(2)}${_esc(m.einheit)}</b>` +
        (m.gesetzt ? " (gesetzt)" : "")).join(" · ");
      const knopf = liste.some(m => m.schluessel && !m.gesetzt)
        ? ' <button type="button" onclick="_masseUebernehmen()" style="width:auto;' +
          'display:inline-block;padding:1px 7px;margin-left:6px;font-size:10px;' +
          'line-height:1.5;background:#22303f;color:#8fb;border:1px solid #3a4a5e;' +
          'border-radius:3px;cursor:pointer">\u21A5 in die Felder</button>' : "";
      const zeigeVors = (vors.length || vhin.length) && !vorsGezeigt;
      if (zeigeVors) vorsGezeigt = true;
      el.innerHTML = "Abgeleitet: " + txt + knopf
        + (befund.length
             ? '<div style="color:#f4a; margin-top:3px">\u26A0 '
               + befund.map(_esc).join("<br>\u26A0 ") + "</div>"
             : "")
        + (zeigeVors
             ? '<div style="margin-top:5px;border-top:1px solid #33404f;padding-top:4px">'
               + (vors.length ? '<div style="color:#9cb;margin-bottom:2px">Das hilft:</div>' : "")
               + vors.map((w, i) =>
                   '<div style="margin-top:2px">\u2192 ' + _esc(w.text)
                   + ((w.schluessel || w.aenderungen)
                        ? ' <button type="button" onclick="_masseVorschlag(' + i + ')" '
                          + 'style="width:auto;display:inline-block;padding:1px 7px;margin-left:6px;'
                          + 'font-size:10px;line-height:1.5;background:#22303f;color:#8fb;'
                          + 'border:1px solid #3a4a5e;border-radius:3px;cursor:pointer">'
                          + '\u2713 \u00fcbernehmen</button>'
                          + ' <button type="button" onclick="_masseVorschlag(' + i + ',true)" '
                          + 'style="width:auto;display:inline-block;padding:1px 7px;margin-left:3px;'
                          + 'font-size:10px;line-height:1.5;background:#1f2f3a;color:#9cf;'
                          + 'border:1px solid #3a4a5e;border-radius:3px;cursor:pointer">'
                          + '\u00fcbernehmen &amp; rechnen</button>' : "")
                   + (w.preis ? '<div style="color:#8a94a0;font-size:10px;margin-left:12px">'
                                + _esc(w.preis) + '</div>' : "")
                   + '</div>').join("")
               + vhin.map(h => '<div style="color:#8a94a0;margin-top:3px">\u2139 '
                               + _esc(h) + '</div>').join("")
               + '</div>'
             : "");
      el.style.display = "";
    });
  }

  // Die abgeleiteten Werte in die Felder schreiben -- ausdruecklich auf
  // Zuruf. Von selbst einzutragen hiesse, aus „ableiten" ein „festhalten" zu
  // machen, ohne dass jemand es entschieden hat.
  function _masseUebernehmen() {
    const b = _laeuferBild;
    if (!b || !Array.isArray(b.masse)) return;
    let n = 0;
    for (const m of b.masse) {
      if (!m.schluessel) continue;
      // EINE Feldsuche fuer beide Uebernahmen (`_gateFeld`) -- hier stand
      // dieselbe Umkehrtabelle ein zweites Mal.
      const el = _gateFeld(m.schluessel);
      if (!el) continue;
      el.value = (+m.wert).toFixed(2);
      // Die EIGENEN Ereignisse der Maske ausloesen statt GEOM selbst zu
      // setzen: dann laufen dieselben Handler wie beim Tippen (GEOM, Neuzeichnen,
      // Autospeichern), und es gibt keinen zweiten Weg, der davon abweichen kann.
      el.dispatchEvent(new Event("input", { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      n++;
    }
    if (n) _masseVorgabeZeigen();
  }
  // Einen gerechneten Vorschlag ins Feld schreiben -- ueber DIESELBE Feldsuche
  // wie die Tor-Vorschlaege (`_gateFeld`) und ueber die EIGENEN Ereignisse der
  // Maske, damit dieselben Handler laufen wie beim Tippen.
  function _masseVorschlag(i, auchRechnen) {
    const w = (window._laeuferVorschlaege || [])[i];
    if (!w) return;
    // Dieselbe Anwendung wie bei den Tor-Vorschlaegen (`_gateAnwenden`) --
    // mehrteilige Wege eingeschlossen. Eine zweite Fassung waere die naechste
    // Stelle, an der die beiden auseinanderlaufen.
    _gateAnwenden(w);
    if (auchRechnen && typeof startAnalysis === "function") {
      setTimeout(() => { try { startAnalysis(); } catch (e) {} }, 60);
    }
  }
  window._masseVorschlag = _masseVorschlag;
  window._masseUebernehmen = _masseUebernehmen;

  function _esc(t) {
    return String(t == null ? "" : t).replace(/[&<>"]/g,
      c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  }

  // Ein Balken ganz oben, wenn der Serverprozess aelter ist als seine Dateien.
// Bewusst NICHT wegklickbar und bewusst nicht im Läufer-Hinweis versteckt: er
// sagt, dass ALLES, was die Seite zeigt, aus einer alten Fassung kommt.
function _serverVeraltetZeigen(text) {
  let el = document.getElementById("server_veraltet");
  if (!text) { if (el) el.remove(); return; }
  if (!el) {
    el = document.createElement("div");
    el.id = "server_veraltet";
    el.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:9999;"
      + "background:#7a2f2f;color:#ffe8e8;padding:7px 14px;font-size:.82rem;"
      + "line-height:1.45;border-bottom:1px solid #a04040";
    document.body.appendChild(el);
  }
  el.textContent = "\u26a0 " + text;
}

function _laeuferHinweisZeigen() {
    _masseVorgabeZeigen();
    // Die volle Beschreibung gehoert in den Reiter, wo sie umbrechen darf.
    const bes = document.getElementById("laeufer_beschreibung");
    if (bes) {
      const g = _laeuferBild && _laeuferMarke === _laeuferMarkeBauen()
                && _laeuferArt() !== "pmsm";
      let t = g ? (_laeuferBild.fehler
                       ? "\u26a0 Laeufer nicht zeichenbar: " + _laeuferBild.fehler
                       : (_laeuferBild.hinweis || "")) : "";
      bes.textContent = t;
      bes.style.display = t ? "" : "none";
      // **Der Server kann aelter sein als sein Code.** Python laedt ein Modul
      // EINMAL; wer waehrend eines laufenden Servers eine Zeichendatei aendert,
      // sieht im Browser weiter die alte Fassung — und Neuladen der SEITE hilft
      // nicht. Zweimal am 20.09.2026 gemeldet (ein Polkern schien im CAD zu
      // fehlen; die Reluktanzmaschine kam „wieder als PSM ohne Magnete").
      // Der Server sagt es jetzt selbst; hier steht es, wo man hinsieht.
      _serverVeraltetZeigen(_laeuferBild && _laeuferBild.server_veraltet);
    }
    const el = document.getElementById("ov_laeufer");
    if (!el) return;
    const b = _laeuferBild;
    if (!b || _laeuferMarke !== _laeuferMarkeBauen() || _laeuferArt() === "pmsm") {
      el.style.display = "none"; el.textContent = ""; return;
    }
    // Am BILD steht nur, was gezeichnet ist -- und was daran nicht stimmt.
    let txt = b.kurz || b.zaehlung || b.hinweis || "";
    if (b.fehler) txt = "Laeufer nicht zeichenbar: " + b.fehler;
    el.dataset.voll = txt;
    el.dataset.offen = "0";
    el.title = txt;
    el.onclick = () => {
      el.dataset.offen = el.dataset.offen === "1" ? "0" : "1";
      _hinweisMalen(el);
    };
    _hinweisMalen(el);
    el.style.display = txt ? "" : "none";
  }

  // Entprellt: `resetField` feuert bei JEDEM Tastendruck im Geometrie-Reiter.
  function _laeuferAnfordern() {
    const marke = _laeuferMarkeBauen();
    if (marke === _laeuferMarke) return;
    if (_laeuferArt() === "pmsm") {          // die Seite kann es selbst
      _laeuferBild = null; _laeuferMarke = marke; _laeuferHinweisZeigen(); return;
    }
    if (_laeuferTimer) clearTimeout(_laeuferTimer);
    _laeuferTimer = setTimeout(async () => {
      try {
        const r = await fetch("/laeuferbild", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ geom: GEOM, axial_len: GEOM.axialLen || 80 })
        });
        _laeuferBild = await r.json();
        _laeuferMarke = marke;
      } catch (e) {
        // Ohne Antwort bleibt der nackte Laeufer stehen -- besser als eine
        // Zeichnung, die zu einer anderen Geometrie gehoert.
        _laeuferBild = null; _laeuferMarke = marke;
      }
      _laeuferHinweisZeigen();
      isSolverInit = false;                  // das Raster muss neu entstehen
    }, 250);
  }

  function drawStator() {
    // Die GSM ist die einzige Bauart mit einem ANDEREN Staender: Schenkelpole
    // nach innen, keine Nuten. Ihre Teile kommen aus derselben Quelle.
    const _st = _staenderTeileAktiv();
    if (_st) { LAEUFER.zeichne(ctx, _st, SCALE); return; }
    const rO=(GEOM.statorOD/2)*SCALE, rI=(GEOM.statorID/2)*SCALE;
    ctx.beginPath(); ctx.arc(0,0,rO,0,2*Math.PI); ctx.arc(0,0,rI,0,2*Math.PI,true);
    ctx.fillStyle="#3a3a3c"; ctx.fill();
    ctx.strokeStyle="#555"; ctx.lineWidth=1; ctx.stroke();
    const slots=GEOM.slots, dpx=GEOM.slotDepth*SCALE;
    const circ=2*Math.PI*rI, pitch=circ/slots, sw=pitch*GEOM.slotWidthRatio;
    for (let i=0;i<slots;i++) {
      ctx.save();
      ctx.rotate(i*(2*Math.PI/slots));
      if (dpx < rO-rI) {
        ctx.fillStyle="#222"; ctx.fillRect(rI,-sw/2,dpx,sw);
        const ins=1*SCALE, cw=sw-2*ins, layers=4, ch=(dpx-(layers+1)*ins)/layers;
        if (cw>0&&ch>0) {
          ctx.fillStyle="#b87333";
          for (let l=0;l<layers;l++) ctx.fillRect(rI+ins+l*(ch+ins),-cw/2,ch,cw);
        }
      }
      ctx.restore();
    }
  }

  function drawRotor() {
    const rO=(GEOM.rotorOD/2)*SCALE, rSh=(GEOM.shaftD/2)*SCALE;
    ctx.beginPath(); ctx.arc(0,0,rO,0,2*Math.PI); ctx.arc(0,0,rSh,0,2*Math.PI,true);
    // **Der Grund ist EISEN — und muss auch so aussehen.** Der Läufergrund war
    // immer `#7f8c8d`, `ema_laeufer.js` malt Eisen dagegen `#2d3748`. Solange
    // nur Magnete daraufkamen, war das eine Farbe für ein Material. Seit eine
    // Bauart ihren ganzen Läufer aus `teile()` zeichnet, ist jede Stelle, die
    // kein Teil abdeckt, ein HELLGRAUER Fleck neben dunklem Eisen — und liest
    // sich als drittes Material. Gemeldet als „innerhalb des Polschuhs gibt es
    // links und rechts einen hellgrauen Bereich … es scheint, als wäre das
    // auch ein Metall". Wo `teile()` den Läufer beschreibt, bekommt der Grund
    // deshalb die Eisenfarbe des Zeichners; der PSM-Pfad behält seine.
    const _eig = !!_laeuferTeileAktiv();
    ctx.fillStyle = _eig ? "#2d3748" : "#7f8c8d";
    ctx.fill(); ctx.strokeStyle = _eig ? "#4a5568" : "#95a5a6"; ctx.stroke();
    ctx.beginPath(); ctx.arc(0,0,rSh,0,2*Math.PI);
    ctx.fillStyle="#222"; ctx.fill(); ctx.strokeStyle="#444"; ctx.stroke();
    // hollow-shaft bore
    if (GEOM.shaftBoreD > 0) {
      const rBore=(GEOM.shaftBoreD/2)*SCALE;
      ctx.beginPath(); ctx.arc(0,0,rBore,0,2*Math.PI);
      ctx.fillStyle="#0d0d14"; ctx.fill(); ctx.strokeStyle="#555"; ctx.stroke();
    }
    const poles=GEOM.p*2, step=2*Math.PI/poles;
    // Eine Bauart ohne Magnete zeichnet ihre eigenen Teile -- und dann bleibt
    // `legs` leer, damit die Polschleife darunter nichts malt. Sie laeuft
    // weiter durch (2p leere Durchgaenge): den Magnetblock auszuklammern
    // haette denselben Code zweimal eingerueckt, und das ist die Sorte
    // Umbau, bei der der PSM-Pfad still kaputtgeht.
    const _lt = _laeuferTeileAktiv();
    if (_lt) LAEUFER.zeichne(ctx, _lt, SCALE);
    const legs = _hatMagnete() ? magnetLegs(GEOM) : [];
    const rRO = (GEOM.rotorOD/2)*SCALE;
    for (let i=0;i<poles;i++) {
      ctx.save(); ctx.rotate(i*step);
      // Colour by the pole's PHYSICAL polarity (red = N = net magnetisation pointing
      // radially OUT). IDENTICAL net-radial rule to ema_pipeline._draw_magnet_outlines,
      // so red means the same physical pole here AND in the FEM field plot. Pure i%2
      // parity is ambiguous (red=S for a V-pole, red=N for SPM). Index fallback only
      // when the net radial component vanishes (spoke = tangential magnetisation).
      const _sgn = i%2===0 ? 1 : -1, _cpA = Math.cos(i*step), _spA = Math.sin(i*step);
      let _net = 0;
      for (const lg of legs) {
        const _la = i*step + lg.tilt, _lx = Math.cos(_la), _ly = Math.sin(_la);
        let _mdx, _mdy;
        if (lg.magMode === "tangential") { _mdx=-_spA; _mdy=_cpA; }
        else if (lg.magMode === "radial") { const _b=i*step+lg.magRot; _mdx=Math.cos(_b); _mdy=Math.sin(_b); }
        else { _mdx=-_ly; _mdy=_lx; }
        if (GEOM.magOrient === "longitudinal") { const _t=_mdx; _mdx=-_mdy; _mdy=_t; }
        const _amp = _sgn * lg.magSign;
        let _pax, _pay;
        if (lg.placement === "surface") { const _ca=i*step+lg.offset/(GEOM.rotorOD/2); _pax=Math.cos(_ca); _pay=Math.sin(_ca); }
        else {
          const _sx=lg.rPos*_cpA - lg.offset*_spA, _sy=lg.rPos*_spA + lg.offset*_cpA;
          const _mx=_sx+0.5*lg.length*_lx, _my=_sy+0.5*lg.length*_ly, _rr=Math.hypot(_mx,_my)||1;
          _pax=_mx/_rr; _pay=_my/_rr;
        }
        _net += _amp*(_mdx*_pax + _mdy*_pay);
      }
      const _isN = Math.abs(_net) > 1e-6 ? _net > 0 : (i%2===0);
      const magColor = _isN ? "#e74c3c" : "#3498db";
      ctx.fillStyle = magColor;
      for (const lg of legs) {
        const mH = lg.thickness*SCALE;
        if (lg.placement === "surface") {
          const halfArc = (lg.length/2)/(GEOM.rotorOD/2);
          const ca = lg.offset/(GEOM.rotorOD/2);
          ctx.fillStyle = magColor;
          ctx.beginPath();
          ctx.arc(0,0, rRO - mH,   ca-halfArc, ca+halfArc, false);
          ctx.arc(0,0, rRO,        ca+halfArc, ca-halfArc, true);
          ctx.closePath(); ctx.fill();
        } else {
          ctx.save();
          ctx.translate(lg.rPos*SCALE, lg.offset*SCALE);
          ctx.rotate(lg.tilt);
          const L = lg.length*SCALE, r = mH/2;
          if (lg.placement === "interior") {
            // obround pocket = magnet straight section + air end caps (flux barriers)
            ctx.fillStyle = "#11131c";
            ctx.fillRect(0, -r, L, mH);
            ctx.beginPath(); ctx.arc(0, 0, r, 0, 2*Math.PI); ctx.fill();
            ctx.beginPath(); ctx.arc(L, 0, r, 0, 2*Math.PI); ctx.fill();
          }
          // magnet (rectangle); surface_flat (Halbach tile) has no pocket/caps
          ctx.fillStyle = magColor;
          ctx.fillRect(0, -r, L, mH);
          ctx.restore();
        }
      }
      ctx.restore();
    }
    // Balance-disc bolt holes (optional): symmetric, count = poles, on a pitch
    // circle (Ø/offset adjustable). Mirrors the FreeCAD + 2D-section geometry.
    if (GEOM.genBalanceBolts) {
      const TH = {M4:4,M5:5,M6:6,M8:8,M10:10,M12:12,M16:16,M20:20};
      const nom = TH[(GEOM.balanceBoltThread||'M6')] || 6;
      const hr  = ((nom+0.4)/2)*SCALE;
      const pcr = (GEOM.balanceBoltCircleD>0 ? GEOM.balanceBoltCircleD/2
                  : GEOM.shaftD/2 + (GEOM.rotorOD/2 - GEOM.shaftD/2)*0.5)*SCALE;
      const off = (GEOM.balanceBoltOffsetDeg||0)*Math.PI/180;
      const nb  = Math.max(2, poles);
      for (let i=0;i<nb;i++){
        const a = off + i*2*Math.PI/nb;
        ctx.beginPath();
        ctx.arc(pcr*Math.cos(a), pcr*Math.sin(a), hr, 0, 2*Math.PI);
        ctx.fillStyle="#0d0d14"; ctx.fill();
        ctx.strokeStyle="#aab"; ctx.lineWidth=1; ctx.stroke();
      }
    }
    // Flux-barrier radial slots (optional): q-axis between poles, d-axis pole centre.
    if (GEOM.genFluxBarrierQ || GEOM.genFluxBarrierD) {
      const fbw = (GEOM.fluxBarrierWidth||3)*SCALE, fbd = (GEOM.fluxBarrierDepth||10)*SCALE;
      const rout = (GEOM.rotorOD/2 - 2)*SCALE, rin = Math.max((GEOM.shaftD/2 + 1)*SCALE, rout - fbd);
      const angs = [];
      if (GEOM.genFluxBarrierD) for (let i=0;i<poles;i++) angs.push(i*2*Math.PI/poles);
      if (GEOM.genFluxBarrierQ) for (let i=0;i<poles;i++) angs.push((i+0.5)*2*Math.PI/poles);
      ctx.fillStyle="#0d0d14"; ctx.strokeStyle="#aab"; ctx.lineWidth=1;
      for (const a of angs){
        ctx.save(); ctx.rotate(a);
        ctx.beginPath(); ctx.rect(rin, -fbw/2, rout-rin, fbw); ctx.fill(); ctx.stroke();
        ctx.restore();
      }
    }
  }

  function drawFluxLines(maxD) {
    const N=GRID_SIZE, gs=maxD*SCALE, cs=gs/N;
    const nL=parseInt(document.getElementById("flux_density").value);
    if (!nL) return;
    let minA=Infinity, maxA=-Infinity;
    for (let i=0;i<gridA.length;i+=10) {
      if(gridA[i]<minA) minA=gridA[i]; if(gridA[i]>maxA) maxA=gridA[i];
    }
    if (!isFinite(minA)) { minA=-100; maxA=100; }
    const range=maxA-minA;
    ctx.lineWidth = PHYS.ultraSlow?1:1.5; ctx.strokeStyle="#50c878"; ctx.globalAlpha=0.7;
    ctx.beginPath();
    const g2c = v => (v-N/2)*cs;
    for (let l=0;l<nL;l++) {
      const level = minA+(l+0.5)*(range/nL);
      for (let y=0;y<N-1;y++) for (let x=0;x<N-1;x++) {
        const v0=gridA[y*N+x], v1=gridA[y*N+x+1], v2=gridA[(y+1)*N+x+1], v3=gridA[(y+1)*N+x];
        let mask=0;
        if(v0>level)mask|=1; if(v1>level)mask|=2; if(v2>level)mask|=4; if(v3>level)mask|=8;
        if(mask===0||mask===15) continue;
        const p=[];
        if((mask&1)||(mask&8)) p[3]={x,y:y+(level-v0)/(v3-v0)};
        if((mask&1)||(mask&2)) p[0]={x:x+(level-v0)/(v1-v0),y};
        if((mask&2)||(mask&4)) p[1]={x:x+1,y:y+(level-v1)/(v2-v1)};
        if((mask&4)||(mask&8)) p[2]={x:x+(level-v3)/(v2-v3),y:y+1};
        const segments={1:[0,3],2:[1,0],4:[2,1],8:[3,2],3:[1,3],6:[2,0],9:[0,2],12:[3,1],
          14:[0,3],13:[1,0],11:[2,1],7:[3,2]};
        const seg=segments[mask];
        if(seg) { ctx.moveTo(g2c(p[seg[0]].x),g2c(p[seg[0]].y)); ctx.lineTo(g2c(p[seg[1]].x),g2c(p[seg[1]].y)); }
        else if(mask===5) { ctx.moveTo(g2c(p[0].x),g2c(p[0].y)); ctx.lineTo(g2c(p[3].x),g2c(p[3].y)); ctx.moveTo(g2c(p[2].x),g2c(p[2].y)); ctx.lineTo(g2c(p[1].x),g2c(p[1].y)); }
        else if(mask===10) { ctx.moveTo(g2c(p[1].x),g2c(p[1].y)); ctx.lineTo(g2c(p[0].x),g2c(p[0].y)); ctx.moveTo(g2c(p[3].x),g2c(p[3].y)); ctx.lineTo(g2c(p[2].x),g2c(p[2].y)); }
      }
    }
    ctx.stroke(); ctx.globalAlpha=1;
  }

  function updateUI() {
    const rpm=Math.round(PHYS.omega*9.55);
    document.getElementById("val_rpm").innerText    = rpm+" U/min";
    document.getElementById("val_torque").innerText = PHYS.torque.toFixed(0)+" Nm";
    document.getElementById("val_iq").innerText     = PHYS.iq.toFixed(0)+" A";
    document.getElementById("val_id").innerText     = PHYS.id.toFixed(0)+" A";
    document.getElementById("val_power").innerText  = (Math.abs(PHYS.torque*PHYS.omega)/1000).toFixed(1)+" kW";
    // Bei mehreren Modulen ist der Strang-Strom nicht der Modul-Strom. Die
    // Zahl, die jemand beim Einkauf braucht, ist die je Modul.
    const _im = document.getElementById("val_modulstrom");
    if (_im) {
      // |I_s| ist der auf EINE Windung bezogene Strom -- und der ist zugleich
      // der Strom JE MODUL, solange alle Module tragen: k Systeme zu je N/k
      // Windungen mit demselben Strom ergeben dieselbe Durchflutung wie eines
      // mit N (s. ema_umrichter). "k × I" waere also falsch gewesen.
      //
      // Faellt eines aus, muessen die uebrigen k-1 den Strom um k/(k-1)
      // erhoehen, um dieselbe Durchflutung zu halten. DAS ist die Tendenz, die
      // man bei Teillast sieht -- das Moment bleibt, der Modulstrom steigt.
      // Erst wenn er die Modulgrenze reisst, faellt auch das Moment.
      const _is = Math.hypot(PHYS.iq, PHYS.id);
      const _aus = (PHYS.ausfallSystem >= 0 && PHYS.kModule > 1);
      const _proModul = _aus ? _is * PHYS.kModule / (PHYS.kModule - 1) : _is;
      let _t = _proModul.toFixed(0) + " A";
      if (PHYS.kModule > 1) {
        _t += _aus
          ? "  (" + (PHYS.kModule - 1) + " von " + PHYS.kModule + " tragen, +"
            + (100 / (PHYS.kModule - 1)).toFixed(0) + " %)"
          : "  (je Modul, " + PHYS.kModule + " Stück)";
      }
      _im.innerText = _t;
      const _ueber = _proModul > PHYS.iMax * 1.001;
      _im.style.color = _ueber ? "#e57373" : (PHYS.echt ? "" : "#c9a227");
      _im.title = _ueber
        ? "über der Modulgrenze von " + Math.round(PHYS.iMax) + " A — das Moment fällt"
        : (PHYS.echt ? "aus der Geometrie gerechnet"
                     : "FESTWERTE — „Elektrik aus der Geometrie holen“ drücken");
    }
    document.getElementById("val_grid").innerText   = GRID_SIZE + "px  #" + _frameCount;
  }

  function loop() {
    if (!cvsW || !cvsH) resize();
    // ⊙ Beim Axialfluss bedient `_axialVorschau` die Leinwand (Abbild der
    // Zeichnung aus dem Reiter ⊙ Axialfluss). Das radiale Dreigespann
    // Rastern/Lösen/Zeichnen bleibt dann aus — es rästert einen
    // Zylinderquerschnitt, und darin ist eine Scheibe ein Ring ohne Merkmal.
    if (cvsW > 0 && cvsH > 0 && window._axialVorschau
        && window._axialVorschau(canvas, ctx, cvsW, cvsH)) {
      requestAnimationFrame(loop);
      return;
    }
    if (cvsW > 0 && cvsH > 0) {
      try {
        if (PHYS.isRunning) {
          const steps = PHYS.ultraSlow ? 1 : 5;
          for (let i = 0; i < steps; i++) stepPhysics();
        }
        rasterizeGeometry(); solveField(); draw();
      } catch(e) {
        _lastErr = e.message + " @ " + (e.stack||"").split("\n")[1];
        console.error("[EMA canvas]", e);
        ctx.fillStyle = "#111"; ctx.fillRect(0, 0, cvsW, cvsH);
        ctx.fillStyle = "#f44"; ctx.font = "13px monospace";
        ctx.fillText("LOOP ERROR: " + e.message, 10, 30);
        ctx.fillText((e.stack||"").split("\n")[1] || "", 10, 50);
      }
    }
    requestAnimationFrame(loop);
  }

  init();
})();
