// Reiter 🧲 3D-Feld: Lauf, Drehzahlband, Verfeinerung, Sektor -- und der
// eingebettete vtk.js-Betrachter samt Abspieler.
//
// Die drei Bloecke standen in ema.html an drei Stellen (Maske · Poll und
// Ergebnis · Betrachter), getrennt durch den Berichtsreiter. Keiner von
// ihnen hat eine Anweisung auf oberster Ebene, sie stehen hier deshalb
// zusammen.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── 3D-Feld (Elmer) ────────────────────────────────────────────────────────────
// Übernommene Geometrie (Snapshot) für den 3D-Lauf. Quelle: Geometrie-Tab (parametrisch)
// oder Designer/Import (gezeichnete/erkannte Magnete via customLegs).
let _em3dGeomPayload = null;
// Merkt sich, ob der Nutzer die 3D-Geometriequelle bewusst per Dropdown gewählt hat.
// Solange false, wird beim Öffnen des 3D-Tabs immer der Geometrie-Tab als Quelle genutzt
// (verhindert das stille, klebrige Umschalten auf „Designer").
let _e3SrcUserSet = false;

async function _em3dBuildGeomPayload() {
  const src = document.getElementById('e3_geomsrc')?.value || 'geo';
  if (src === 'designer') {
    if (!DESIGN.magnets || !DESIGN.magnets.length)
      throw new Error('Keine gezeichneten/importierten Magnete im Designer-Tab vorhanden.');
    return await _dsnBuildPayload();
  }
  return await buildPayload();
}

function _em3dGeomSummaryHtml(p) {
  const g = p.geom || {}, axial = p.axial_len || g.axialLen;
  const designer = (document.getElementById('e3_geomsrc')?.value === 'designer');
  const srcLbl = designer ? 'Designer / Import (custom)' : 'Geometrie-Tab (parametrisch)';
  // **Welcher 3-D-Löser läuft, hängt am Flussweg** — und das muss hier stehen,
  // nicht erst im Protokoll. Gemeldet als „wie bekomme ich die Axialfluss-
  // maschine nach Elmer? Geometrie Axialfluss gibt es dort nicht": der Reiter
  // zeigte nur die Quelle (Geometrie-Tab / Designer) und verschwieg, dass eine
  // Scheibe einen anderen Löser braucht als ein Zylinder.
  if ((g.fluxPath || 'radial') === 'axial') {
    return '<div style="color:#8bc34a;font-size:.8rem;line-height:1.5">'
      + '<b>⊙ Axialfluss</b> — gerechnet wird ein <b>anti-periodischer '
      + 'Ringsektor EINER Polteilung</b> (<code>ema_axial_em3d</code>), nicht '
      + 'der magnetostatische Vollmotor: der baut konzentrische Zylinder und '
      + 'wäre hier eine andere Maschine.<br>'
      + `Scheibe Ø ${(g.axialAktivOD ?? '—')} mm · λ ${(g.axialLambda ?? '—')}`
      + ` · 2p ${2 * (g.p || 0)} · Q ${(g.slots ?? '—')}`
      + ` · Spalt ${(g.axialSpaltMm ?? '—')} mm · Bauform ${(g.axialBauform || '—')}`
      // Woher diese Maße kommen, gehört dazu: sie stehen in KEINEM Feld
      // dieses Reiters, und „ich kann die Geometrie nicht übernehmen“
      // war genau diese fehlende Auskunft (09.10.2026).
      + `<br><span style="color:#9ab">Maße aus ${_axQuelle === 'reiter'
            ? '<b>Reiter ⊙ Axialfluss</b> (der gezeichneten Scheibe)'
            : 'dem <b>Projekt</b>; was dort fehlt, ergänzt der Lauf benannt '
              + '— den Reiter ⊙ Axialfluss einmal öffnen, dann gilt die Zeichnung'}`
      + '</span>'
      + '<br><span style="color:#9ab">Mitgerechnet wird der <b>Mehrschnitt</b> '
      + 'auf derselben Geometrie — die Abweichung über dem Radius IST das '
      + 'Ergebnis (der <code>∂/∂r</code>-Term, den der Mehrschnitt fallen '
      + 'lässt). Netzfeinheit aus den Feldern unten, Schnittzahl und N aus '
      + '④ Berechnung.</span></div>';
  }
  const magLbl = g.magShape === 'custom'
    ? `custom (${(g.customLegs || []).length} Legs/Pol)` : (g.magShape || '—');
  const nbar = (() => {
    let n = 0;
    if (g.genFluxBarrierQ) n += (g.p || 0) * 2;
    if (g.genFluxBarrierD) n += (g.p || 0) * 2;
    n += ((g.customBarriers || []).length) * (g.p || 0) * 2;
    return n;
  })();
  return `<div style="color:#6c6">✓ Übernommen — Quelle: <b>${srcLbl}</b></div>`
    + `<div style="margin-top:3px">Stator-Ø ${g.statorOD} · Rotor-Ø ${g.rotorOD} · Welle-Ø ${g.shaftD} · `
    + `Luftspalt ${(((g.statorID||0)-(g.rotorOD||0))/2).toFixed(2)} mm · ${(g.p||0)*2} Pole · `
    + `${g.slots} Nuten · Magnet: ${magLbl}${nbar ? ` · ${nbar} Flussbarrieren` : ''} · Länge ${axial} mm</div>`
    + `<div style="color:#6a8;margin-top:3px">Die aktuelle Geometrie wird bei JEDEM 3D-Lauf automatisch frisch übernommen.</div>`;
}

async function adoptEm3dGeom() {
  const sum = document.getElementById('e3_geomsummary');
  if (!sum) return;
  _e3RefreshSavedList();           // gespeicherte 3D-Läufe in die Tab-①-Auswahl laden
  if (typeof _e3RefreshSavedCards === 'function') _e3RefreshSavedCards();  // Karten im 3D-Feld-Tab
  try {
    _em3dGeomPayload = await _em3dBuildGeomPayload();
    sum.innerHTML = _em3dGeomSummaryHtml(_em3dGeomPayload);
  } catch (e) {
    _em3dGeomPayload = null;
    sum.innerHTML = '<span style="color:#e57">⚠ ' + escHtml(e.message) + '</span>';
  }
}

// Liefert die für den 3D-Lauf zu verwendende Geometrie. WICHTIG: IMMER frisch aus der
// aktuell gewählten Quelle (Geometrie-Tab/Designer) bauen — NICHT den eingefrorenen
// Snapshot wiederverwenden. Sonst würde nach dem ersten „übernehmen" jede spätere
// Magnet-/Geometrieänderung ignoriert („nur einmal übernommen"). Aktualisiert dabei
// auch die Zusammenfassung, damit Anzeige und Lauf garantiert übereinstimmen.
async function _em3dGeom() {
  await adoptEm3dGeom();                       // rebuild snapshot + refresh summary
  if (!_em3dGeomPayload)
    throw new Error('Keine gültige Geometrie übernommen (siehe Hinweis bei der Geometriequelle).');
  return JSON.parse(JSON.stringify(_em3dGeomPayload));
}

// Ziel-Knoten-Regler: Label, Grob-Schätzung (RAM/Zeit, gemessen) + Aktiv/Inaktiv der Zellgrößen.
function _e3TargetSync() {
  const on  = document.getElementById('e3_target_on');
  const sl  = document.getElementById('e3_target_nodes');
  const lbl = document.getElementById('e3_target_lbl');
  const est = document.getElementById('e3_target_est');
  if (!sl) return;
  const n = +sl.value;
  if (lbl) lbl.textContent = n.toLocaleString('de-DE');
  sl.disabled = !(on && on.checked);
  // gemessene Regression (31-GiB-Maschine, MUMPS): RAM ≈ n·(59…95)/1e6 GiB, Zeit ≈ ~Knoten^1.2.
  const ramGiB = (n * (58 + 40 * (n / 300000)) / 1e6);   // kB/Knoten steigt 58→~98 (Fill-in)
  const secs   = 24 * Math.pow(n / 38813, 1.35);
  const mins   = secs >= 90 ? (secs / 60).toFixed(1) + ' min' : Math.round(secs) + ' s';
  if (est) est.innerHTML = (on && on.checked)
    ? `≈ <b>${ramGiB.toFixed(1)} GiB</b> RAM, ≈ <b>${mins}</b> Solve (grobe Schätzung)`
      + (n > 300000 ? ' — <span style="color:#e88">über RAM-Deckel!</span>' : '')
    : 'Regler aus — es gelten die Zellgrößen unten + Auto-Cap (55 000).';
}

// FEM-Einstellungen (inkl. Schrägung + gestaffelte Staffelung) in den Payload schreiben.
function _em3dApplyOpts(payload) {
  const g = id => +document.getElementById(id).value;
  payload.skew_deg      = g('e3_skew');
  payload.skew_segments = Math.max(1, Math.round(g('e3_segs')));
  payload.skew_step_deg = g('e3_stepdeg');
  payload.mesh_cl       = g('e3_meshcl');
  payload.gap_cl        = g('e3_gapcl');
  payload.mag_cl        = g('e3_magcl');     // 0 = auto (≈ halbe Grobgröße)
  payload.mag_grow      = g('e3_maggrow');   // 0 = auto (≈ 3× Luftspalt)
  payload.airbox_factor = g('e3_box');
  // Ziel-Netzknoten (Regler): überschreibt den Auto-Cap, steuert die Knotenzahl beidseitig an.
  if (document.getElementById('e3_target_on')?.checked)
    payload.target_nodes = +document.getElementById('e3_target_nodes').value || 0;
  else
    delete payload.target_nodes;
  // Betriebspunkt: Anregung + Drehzahl + Last (+ experimentelle 3D-Stromeinprägung).
  payload.excitation   = document.getElementById('e3_excitation').value;
  payload.rpm          = g('e3_rpm');
  payload.load_nm      = g('e3_load');
  payload.coil_currents = !!document.getElementById('e3_coilcurr')?.checked;
  // Hexaeder-Netz (strukturiert) statt Tetraeder — opt-in, Leerlauf-/Feldvisualisierung.
  payload.hex_mesh = !!document.getElementById('e3_hex_mesh')?.checked;
}

// ── 3D-Lauf speichern / aufrufen ────────────────────────────────────────────────
// Felder, die eine 3D-Config ausmachen (round-trip Speichern↔Laden).
const _E3_CFG_FIELDS = ['e3_geomsrc','e3_preset','e3_excitation','e3_rpm','e3_load',
  'e3_skew','e3_segs','e3_stepdeg','e3_meshcl','e3_gapcl','e3_magcl','e3_maggrow','e3_box',
  'e3_target_on','e3_target_nodes'];
// Geometrie eines GELADENEN Laufs (damit eine Verfeinerung danach die passende Geometrie
// nutzt statt der aktuellen Formularwerte). Null = frischer Lauf (Formular ist maßgeblich).
let _e3LoadedGeom = null;

function _e3BuildConfig() {
  const cfg = { sweep: JSON.parse(JSON.stringify(_e3Sweep || [])), detail_index: _e3DetailIdx,
                coil_currents: !!document.getElementById('e3_coilcurr')?.checked,
                hex_mesh: !!document.getElementById('e3_hex_mesh')?.checked,
                geom_payload: _em3dGeomPayload };
  _E3_CFG_FIELDS.forEach(id => { const el = document.getElementById(id); if (el) cfg[id] = el.value; });
  const to = document.getElementById('e3_target_on'); if (to) cfg.e3_target_on = to.checked;
  return cfg;
}

function _e3ApplyConfig(cfg) {
  if (!cfg) return;
  _E3_CFG_FIELDS.forEach(id => {
    const el = document.getElementById(id);
    if (el && cfg[id] !== undefined && el.type !== 'checkbox') el.value = cfg[id];
  });
  const to = document.getElementById('e3_target_on');
  if (to && cfg.e3_target_on !== undefined) to.checked = !!cfg.e3_target_on;
  if (typeof _e3TargetSync === 'function') _e3TargetSync();
  const cc = document.getElementById('e3_coilcurr'); if (cc) cc.checked = !!cfg.coil_currents;
  const hx = document.getElementById('e3_hex_mesh'); if (hx) hx.checked = !!cfg.hex_mesh;
  if (Array.isArray(cfg.sweep)) { _e3Sweep = JSON.parse(JSON.stringify(cfg.sweep)); }
  if (cfg.detail_index != null) _e3DetailIdx = cfg.detail_index;
  if (typeof _e3RenderSweepTable === 'function') _e3RenderSweepTable();
  if (cfg.geom_payload) { _em3dGeomPayload = cfg.geom_payload; _e3LoadedGeom = cfg.geom_payload; }
  if (typeof _updateExcitationVis === 'function') _updateExcitationVis();
}

async function _e3SaveRun() {
  const m = document.getElementById('e3_save_msg');
  const name = (document.getElementById('e3_save_name').value || '').trim();
  try {
    const r = await fetch('/em3d/save', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ name, config: _e3BuildConfig() }) }).then(x => x.json());
    if (r.error) { m.style.color = '#e57'; m.textContent = '⚠ ' + r.error; return; }
    m.style.color = '#6c6'; m.textContent = '✓ Gespeichert: ' + (r.name || r.id);
    await _e3RefreshSavedList();
    if (typeof _e3RefreshSavedCards === 'function') _e3RefreshSavedCards();
  } catch (e) { m.style.color = '#e57'; m.textContent = '⚠ ' + e.message; }
}

async function _e3RefreshSavedList() {
  const sel = document.getElementById('e3_saved_list'); if (!sel) return;
  try {
    const list = await fetch('/em3d/saved').then(x => x.json());
    const cur = sel.value;
    sel.innerHTML = '<option value="">— gespeicherte Läufe —</option>' + (list || []).map(it => {
      const tag = it.is_submodel ? ' · 🔍Gebiet' : (it.is_sweep ? ' · Sweep' : '');
      const bg = it.b_gap != null ? ` · B_gap ${it.b_gap} T` : '';
      return `<option value="${escHtml(it.id)}">${escHtml(it.name)} (${escHtml(it.timestamp||'')})${bg}${tag}</option>`;
    }).join('');
    sel.value = cur;
  } catch (e) {}
}

// Vom Tab-①-Dropdown (`#e3_saved_list`): den gewählten Lauf per ID laden.
async function _e3LoadRun() {
  const m = document.getElementById('e3_save_msg');
  const id = document.getElementById('e3_saved_list').value;
  if (!id) { m.style.color = '#e57'; m.textContent = '⚠ Bitte einen Lauf wählen.'; return; }
  // Vom Tab ① aus NICHT automatisch in den 3D-Feld-Tab springen; die Meldung führt hin.
  const r = await _e3LoadRunById(id, m, false);
  if (r && !r.error) m.textContent += ' — im 3D-Feld-Tab „🧊 Im Browser ansehen".';
}

// Gespeicherten 3D-Lauf per ID laden — genutzt vom Tab-①-Dropdown UND der Karten-Liste
// „🧲 Gespeicherte 3D-Läufe" im 3D-Feld-Tab (und von openJobEm3d). openInTab=true wechselt
// vorher in den 3D-Feld-Tab, damit das Ergebnis + der Browser-Viewer sofort sichtbar sind.
async function _e3LoadRunById(id, msgEl, openInTab) {
  try {
    const r = await fetch('/em3d/saved/' + encodeURIComponent(id)).then(x => x.json());
    if (r.error) { if (msgEl) { msgEl.style.color = '#e57'; msgEl.textContent = '⚠ ' + r.error; } return r; }
    // WICHTIG: die Feld-/Feldlinien-Caches des VORHERIGEN Laufs leeren — _e3GetPointPd cached
    // die geparste VTP je Punkt-Index; ohne Leeren zeigt der Viewer nach dem Laden das ALTE
    // (oder gar kein) Feld. _e3PlayStop() leert _e3PdCache/_e3LinesCache + stoppt den Player.
    if (typeof _e3PlayStop === 'function') _e3PlayStop();
    _e3ViewIdx = null; _e3SweepPoints = null;
    _e3ApplyConfig(r.config);
    if (openInTab && window._activeTab !== 'em3d') switchTab('em3d');
    if (r.result && r.result.sweep) _renderEm3dSweep(r.result); else _renderEm3d(r.result);
    if (msgEl) { msgEl.style.color = '#6c6'; msgEl.textContent = '✓ Geladen: ' + (r.name || id); }
    return r;
  } catch (e) { if (msgEl) { msgEl.style.color = '#e57'; msgEl.textContent = '⚠ ' + e.message; } }
}

// Karten-Liste „🧲 Gespeicherte 3D-Läufe" im 3D-Feld-Tab (Muster wie die 💧-Öl-Varianten).
async function _e3RefreshSavedCards() {
  const el = document.getElementById('e3_saved_cards');
  if (!el) return;
  try {
    const list = await fetch('/em3d/saved').then(x => x.json());
    if (!Array.isArray(list) || !list.length) {
      el.innerHTML = '<span style="color:#889">— noch keine gespeicherten 3D-Läufe —</span>'; return; }
    let h = '<div style="display:flex;flex-direction:column;gap:6px">';
    for (const it of list) {
      const bits = [];
      if (it.is_submodel) bits.push('🔍 Gebiet/Sektor');
      else if (it.is_sweep) bits.push('Sweep');
      if (it.excitation) bits.push(it.excitation === 'loaded' ? 'mit Last' : 'Leerlauf');
      if (it.b_gap != null) bits.push('B_gap ' + it.b_gap + ' T');
      h += `<div style="display:flex;gap:8px;align-items:center;background:#1c2024;border:1px solid #333;`
         + `border-radius:5px;padding:6px 9px">`
         + `<span style="flex:1"><b>${escHtml(it.name || it.id)}</b>`
         + `<span style="color:#889;font-size:.9em"> — ${escHtml(it.timestamp || '')}`
         + `${bits.length ? ' · ' + escHtml(bits.join(' · ')) : ''}</span></span>`
         + `<button onclick="_e3LoadRunById('${escHtml(it.id)}', document.getElementById('e3_msg'), true)" `
         +   `style="width:auto;padding:3px 10px;background:#2e6a4a">📂 Laden</button>`
         + `<button onclick="_e3DeleteSavedRun('${escHtml(it.id)}')" `
         +   `style="width:auto;padding:3px 9px;background:#7a3030">🗑</button>`
         + `</div>`;
    }
    el.innerHTML = h + '</div>';
  } catch (e) {
    el.innerHTML = '<span style="color:#c66">⚠ Liste nicht ladbar.</span>';
  }
}

async function _e3DeleteSavedRun(id) {
  if (!confirm('Gespeicherten 3D-Lauf löschen?')) return;
  try { await fetch('/em3d/saved/' + encodeURIComponent(id) + '/delete', { method: 'POST' }); } catch (e) {}
  _e3RefreshSavedCards();
  if (typeof _e3RefreshSavedList === 'function') _e3RefreshSavedList();
}

async function _e3DeleteSaved() {
  const m = document.getElementById('e3_save_msg');
  const id = document.getElementById('e3_saved_list').value;
  if (!id) return;
  if (!confirm('Gespeicherten 3D-Lauf löschen?')) return;
  try {
    await fetch('/em3d/saved/' + encodeURIComponent(id) + '/delete', { method: 'POST' });
    m.style.color = '#6c6'; m.textContent = '✓ Gelöscht.';
    await _e3RefreshSavedList();
    if (typeof _e3RefreshSavedCards === 'function') _e3RefreshSavedCards();
  } catch (e) { m.style.color = '#e57'; m.textContent = '⚠ ' + e.message; }
}

// ── Verfeinerungsgebiet (Submodell) ─────────────────────────────────────────────
let _e3RoiActor = null;     // gelber Drahtgitter-Quader im Viewer

function _e3ShowRefineCard(show) {
  const c = document.getElementById('e3_refine_card');
  if (c) c.style.display = show ? 'block' : 'none';
}

// Vorbelegung des Quaders aus der Maschinengröße: Luftspalt-/Magnetbereich auf der +x-Seite.
function _e3RoiDefaults() {
  const g = (_em3dGeomPayload && _em3dGeomPayload.geom) || {};
  const rso = (+g.statorOD || 160) / 2;
  const L = (_em3dGeomPayload && (+_em3dGeomPayload.axial_len)) || (+g.axialLen) || 80;
  return { xmin: +(0.12 * rso).toFixed(1), xmax: +(0.78 * rso).toFixed(1),
           ymin: +(-0.32 * rso).toFixed(1), ymax: +(0.32 * rso).toFixed(1),
           zmin: +(0.30 * L).toFixed(1), zmax: +(0.70 * L).toFixed(1) };
}

function _e3RoiReset() {
  const d = _e3RoiDefaults();
  ['xmin','xmax','ymin','ymax','zmin','zmax'].forEach(k => {
    const el = document.getElementById('e3_roi_' + k); if (el) el.value = d[k];
  });
  _e3DrawRoiBox();
}

function _e3ReadRoi() {
  const v = k => +document.getElementById('e3_roi_' + k).value;
  const r = { xmin: v('xmin'), xmax: v('xmax'), ymin: v('ymin'),
              ymax: v('ymax'), zmin: v('zmin'), zmax: v('zmax') };
  if (r.xmax <= r.xmin || r.ymax <= r.ymin || r.zmax <= r.zmin) return null;
  return r;
}

function _e3RoiChanged() { _e3DrawRoiBox(); }

// Gelben Drahtgitter-Quader im 3D-Viewer zeichnen (live aus den Feldern). vtk.js-Box-Quelle;
// fehlt sie im Build, bleiben die Zahlenfelder die (interaktive) Quelle der Wahrheit.
function _e3DrawRoiBox() {
  if (!_e3rw || !window.vtk) return;
  const r = _e3ReadRoi(); if (!r) return;
  const ren = _e3rw.getRenderer();
  if (_e3RoiActor) { try { ren.removeActor(_e3RoiActor); } catch (e) {} _e3RoiActor = null; }
  try {
    const cube = vtk.Filters.Sources.vtkCubeSource.newInstance({
      xLength: r.xmax - r.xmin, yLength: r.ymax - r.ymin, zLength: r.zmax - r.zmin,
      center: [(r.xmin + r.xmax) / 2, (r.ymin + r.ymax) / 2, (r.zmin + r.zmax) / 2] });
    const mp = vtk.Rendering.Core.vtkMapper.newInstance();
    mp.setInputConnection(cube.getOutputPort());
    const a = vtk.Rendering.Core.vtkActor.newInstance(); a.setMapper(mp);
    a.getProperty().setRepresentation(1);      // Wireframe
    a.getProperty().setColor(1.0, 0.85, 0.1); a.getProperty().setLineWidth(2);
    ren.addActor(a); _e3RoiActor = a;
    _e3rw.getRenderWindow().render();
  } catch (e) {}
}

async function startEm3dSubmodel() {
  const m = document.getElementById('e3_roi_msg');
  const roi = _e3ReadRoi();
  if (!roi) { m.style.color = '#e57'; m.textContent = '⚠ Ungültiger Quader (bis-Werte müssen > von-Werten sein).'; return; }
  m.style.color = '#9aa'; m.textContent = '⏳ Verfeinerung wird gerechnet (volles Modell, lokal feiner)…';
  try {
    // Geometrie: bei geladenem Lauf die gespeicherte, sonst die aktuelle Form/Designer-Geometrie.
    const payload = _e3LoadedGeom ? JSON.parse(JSON.stringify(_e3LoadedGeom)) : await _em3dGeom();
    _em3dApplyOpts(payload);
    payload.roi_box = roi;
    payload.refine_factor = +document.getElementById('e3_roi_refine').value || 3;
    const btn = document.getElementById('e3_roi_btn'); if (btn) btn.disabled = true;
    ['e3_btn','e3_pbtn','e3_sbtn'].forEach(id => { const el=document.getElementById(id); if(el)el.disabled=true; });
    const r = await fetch('/em3d/submodel', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify(payload) }).then(x => x.json());
    if (r.error) { m.style.color = '#e57'; m.textContent = '⚠ ' + r.error;
      if (btn) btn.disabled = false; return; }
    document.getElementById('e3_log').style.display = 'block';
    _pollEm3d();
  } catch (e) { m.style.color = '#e57'; m.textContent = '⚠ ' + e.message; }
}

// Geschätztes Nenn-Drehmoment aus der Maschinengröße (Tangentialspannungs-Auslegung):
// T ≈ σ·(π/2)·D_rotor²·L_stack, σ ≈ 25 kPa typische Dauer-Tangentialspannung. Unabhängig
// vom (oft kleinen) load_nm-Formularfeld → liefert realistische Profil-Lasten je Maschine.
function _e3RatedTorque(g) {
  const geom = g.geom || {};
  const D = (+geom.rotorOD || 180) / 1000;                       // m
  const L = (+g.axial_len || +geom.axialLen || 80) / 1000;       // m
  const sigma = 25000;                                           // N/m²
  return Math.max(1, sigma * (Math.PI / 2) * D * D * L);         // Nm
}

// Lastprofile: füllen Anregung + Drehzahl + Last mit typischen Werten. Die Last leitet sich
// aus dem geschätzten Nennmoment der Maschine ab (nicht aus dem load_nm-Feld), die Drehzahl
// aus dem Drehzahlbereich (rpm_to).
function _e3ApplyPreset() {
  const pr = document.getElementById('e3_preset').value;
  if (pr === 'custom') return;
  const g = (_em3dGeomPayload) || {};
  const rpmTo = +g.rpm_to || 8000;
  const Tn = _e3RatedTorque(g);                                  // Nennmoment-Schätzung
  const set = (exc, rpm, load) => {
    document.getElementById('e3_excitation').value = exc;
    document.getElementById('e3_rpm').value = Math.round(rpm);
    document.getElementById('e3_load').value = Math.round(load);
  };
  if (pr === 'leerlauf')            set('open_circuit', rpmTo * 0.5, 0);
  else if (pr === 'teillast')       set('loaded', rpmTo * 0.5, Tn * 0.4);
  else if (pr === 'nennlast')       set('loaded', rpmTo * 0.6, Tn);
  else if (pr === 'volllast')       set('loaded', Math.max(300, rpmTo * 0.10), Tn * 1.8);
  else if (pr === 'feldschwaechung') set('loaded', rpmTo, Tn * 0.55);
  _updateExcitationVis();
}

// Manuelle Änderung → Profil auf „Benutzerdefiniert".
function _e3MarkCustom() {
  const sel = document.getElementById('e3_preset');
  if (sel && sel.value !== 'custom') sel.value = 'custom';
  _updateExcitationVis();
}

// Den experimentellen 3D-Strom-Schalter nur im Lastfall zeigen.
function _updateExcitationVis() {
  const loaded = document.getElementById('e3_excitation')?.value === 'loaded';
  const f = document.getElementById('e3_coilcurr_field');
  if (f) f.style.display = loaded ? '' : 'none';
}

// ── Drehzahlband / Lastsweep ──────────────────────────────────────────────────────
// Liste der Betriebspunkte (rpm/Last/Anregung) + Index des Detailpunkts (volles 3D-Feld).
let _e3Sweep = [
  { rpm: 1000, load_nm: 150, excitation: 'loaded' },
  { rpm: 8000, load_nm: 90,  excitation: 'loaded' },
  { rpm: 15000, load_nm: 55, excitation: 'loaded' },
];
let _e3DetailIdx = 2;

function _e3RenderSweepTable() {
  const t = document.getElementById('e3_sweep_table');
  if (!t) return;
  if (_e3DetailIdx >= _e3Sweep.length) _e3DetailIdx = Math.max(0, _e3Sweep.length - 1);
  let h = '<tr style="color:#9ab;text-align:left;border-bottom:1px solid #2a2a30">'
        + '<th style="padding:4px 6px">Detail&nbsp;⦿</th><th style="padding:4px 6px">Drehzahl [1/min]</th>'
        + '<th style="padding:4px 6px">Last [Nm]</th><th style="padding:4px 6px">Anregung</th><th></th></tr>';
  _e3Sweep.forEach((p, i) => {
    h += `<tr style="border-bottom:1px solid #1d1d24">`
      + `<td style="padding:3px 6px;text-align:center"><input type="radio" name="e3detail" ${i===_e3DetailIdx?'checked':''} onchange="_e3DetailIdx=${i}"></td>`
      + `<td style="padding:3px 6px"><input type="number" value="${p.rpm}" min="0" max="60000" step="100" style="width:96px" onchange="_e3SweepSet(${i},'rpm',this.value)"></td>`
      + `<td style="padding:3px 6px"><input type="number" value="${p.load_nm}" min="0" max="5000" step="10" style="width:84px" onchange="_e3SweepSet(${i},'load_nm',this.value)"></td>`
      + `<td style="padding:3px 6px"><select onchange="_e3SweepSet(${i},'excitation',this.value)" style="width:auto;padding:3px">`
      + `<option value="loaded" ${p.excitation==='loaded'?'selected':''}>Lastfall</option>`
      + `<option value="open_circuit" ${p.excitation==='open_circuit'?'selected':''}>Leerlauf</option></select></td>`
      + `<td style="padding:3px 6px;text-align:right"><button onclick="_e3SweepDel(${i})" style="background:#5a3a3a;width:auto;padding:2px 9px">✕</button></td></tr>`;
  });
  t.innerHTML = h;
}
function _e3SweepSet(i, k, v) {
  if (!_e3Sweep[i]) return;
  _e3Sweep[i][k] = (k === 'excitation') ? v : (+v || 0);
}
function _e3SweepDel(i) { _e3Sweep.splice(i, 1); if (!_e3Sweep.length) _e3SweepAddRow(); _e3RenderSweepTable(); }
function _e3SweepAddRow() {
  const last = _e3Sweep[_e3Sweep.length - 1] || { rpm: 3000, load_nm: 100, excitation: 'loaded' };
  _e3Sweep.push({ rpm: last.rpm, load_nm: last.load_nm, excitation: last.excitation });
  _e3RenderSweepTable();
}
function _e3SweepClear() { _e3Sweep = []; _e3DetailIdx = 0; _e3MakeVideo = false; _e3SweepAddRow(); }

// Aus den 5 Lastprofilen ein Drehzahlband bauen (gleiche Logik wie _e3ApplyPreset).
function _e3SweepFromProfiles() {
  const g = (_em3dGeomPayload) || {};
  const rpmTo = +g.rpm_to || 8000;
  const Tn = _e3RatedTorque(g);
  _e3Sweep = [
    { rpm: Math.round(Math.max(300, rpmTo * 0.10)), load_nm: Math.round(Tn * 1.8), excitation: 'loaded' },   // Volllast/Anfahren
    { rpm: Math.round(rpmTo * 0.5),  load_nm: Math.round(Tn * 0.4),  excitation: 'loaded' },                  // Teillast
    { rpm: Math.round(rpmTo * 0.6),  load_nm: Math.round(Tn),        excitation: 'loaded' },                  // Nennlast
    { rpm: Math.round(rpmTo),        load_nm: Math.round(Tn * 0.55), excitation: 'loaded' },                  // Feldschwächung
    { rpm: Math.round(rpmTo * 0.5),  load_nm: 0,                     excitation: 'open_circuit' },            // Leerlauf
  ];
  _e3DetailIdx = 2;
  _e3MakeVideo = false;
  _e3RenderSweepTable();
}
// rpm von–bis · N Punkte · feste Last → Zeilen anhängen.
function _e3SweepFromBand() {
  const lo = +document.getElementById('e3_sw_from').value || 0;
  const hi = +document.getElementById('e3_sw_to').value || 0;
  const n = Math.max(1, Math.round(+document.getElementById('e3_sw_n').value || 1));
  const load = +document.getElementById('e3_sw_load').value || 0;
  const exc = load > 0 ? 'loaded' : 'open_circuit';
  for (let i = 0; i < n; i++) {
    const rpm = n === 1 ? lo : Math.round(lo + (hi - lo) * i / (n - 1));
    _e3Sweep.push({ rpm, load_nm: load, excitation: exc });
  }
  _e3RenderSweepTable();
}
// Reine Drehzahl-Rampe (feste Last) → ERSETZT die Punktliste. Für die dynamische
// Darstellung „über Drehzahl" im 3D-Viewer (der Player läuft dann über die rpm-Achse).
function _e3RampSpeed() {
  const lo = +document.getElementById('e3_sw_from').value || 0;
  const hi = +document.getElementById('e3_sw_to').value || 0;
  const n = Math.max(2, Math.round(+document.getElementById('e3_sw_n').value || 2));
  const load = +document.getElementById('e3_sw_load').value || 0;
  const exc = load > 0 ? 'loaded' : 'open_circuit';
  _e3Sweep = [];
  for (let i = 0; i < n; i++) {
    const rpm = Math.round(lo + (hi - lo) * i / (n - 1));
    _e3Sweep.push({ rpm, load_nm: load, excitation: exc });
  }
  _e3DetailIdx = Math.floor((n - 1) / 2);          // Detailfeld in der Bandmitte
  _e3MakeVideo = false;
  _e3RenderSweepTable();
}
// Reine Last-Rampe (feste Drehzahl) → ERSETZT die Punktliste. Für die dynamische
// Darstellung „über Last" (0 → Last-bis); Punkt 0 = Leerlauf. Der Player läuft über die Last.
function _e3RampLoad() {
  const rpm = +document.getElementById('e3_sw_rpm_fixed').value || 0;
  const hiT = +document.getElementById('e3_sw_load_to').value || 0;
  const n = Math.max(2, Math.round(+document.getElementById('e3_sw_n').value || 2));
  _e3Sweep = [];
  for (let i = 0; i < n; i++) {
    const load = Math.round(hiT * i / (n - 1));
    _e3Sweep.push({ rpm, load_nm: load, excitation: load > 0 ? 'loaded' : 'open_circuit' });
  }
  _e3DetailIdx = n - 1;                             // Detailfeld bei Volllast
  _e3MakeVideo = false;
  _e3RenderSweepTable();
}

// Dynamisches Lastprofil (synthetischer Fahrzyklus) → Punktliste + Video-Flag. Ausgelegt, dass
// i_q/i_d, Sättigung und Feldlinien maximal sichtbar variieren: Anfahren (Volllast) →
// Beschleunigung → Nennbetrieb → Feldschwächung (i_d↓ über Basisdrehzahl) → Boost → Auslauf.
let _e3MakeVideo = false;
function _e3LoadProfile() {
  const g = (_em3dGeomPayload) || {};
  let N = Math.round(+document.getElementById('e3_prof_n').value || 30);
  N = Math.max(20, Math.min(50, N));
  const rpmTo = +g.rpm_to || 8000;
  const Tn = _e3RatedTorque(g);
  const rb = 0.55 * rpmTo;                           // Basisdrehzahl (darüber Feldschwächung)
  // [Anteil, Label, rpm(t 0..1), Last(t)]
  const segs = [
    [0.18, 'Anfahren (Volllast)',  t => (0.05 + 0.30 * t) * rpmTo, t => (0.5 + 1.1 * t) * Tn],
    [0.14, 'Beschleunigung',       t => (0.35 + 0.15 * t) * rpmTo, t => 1.6 * Tn],
    [0.12, 'Nennbetrieb',          t => (0.50 + 0.05 * t) * rpmTo, t => Tn],
    [0.26, 'Feldschwächung',       t => (0.55 + 0.45 * t) * rpmTo, t => Tn * rb / ((0.55 + 0.45 * t) * rpmTo)],
    [0.10, 'Boost / Überlast',     t => (0.88 + 0.04 * t) * rpmTo, t => 1.5 * Tn],
    [0.20, 'Lastabwurf / Auslauf', t => (0.90 - 0.85 * t) * rpmTo, t => 1.5 * Tn * (1 - t)],
  ];
  let counts = segs.map(s => Math.max(2, Math.round(s[0] * N)));
  let sum = counts.reduce((a, b) => a + b, 0);
  while (sum > N) { counts[counts.indexOf(Math.max(...counts))]--; sum--; }
  while (sum < N) { counts[counts.indexOf(Math.max(...counts))]++; sum++; }
  const pts = [];
  segs.forEach((s, si) => {
    const cnt = counts[si];
    for (let k = 0; k < cnt; k++) {
      const t = cnt === 1 ? 0.5 : k / (cnt - 1);
      const rpm = Math.max(0, Math.round(s[2](t)));
      const load = Math.max(0, Math.round(s[3](t)));
      pts.push({ rpm, load_nm: load, excitation: load > 0 ? 'loaded' : 'open_circuit', phase: s[1] });
    }
  });
  _e3Sweep = pts;
  let acc = 0; for (let si = 0; si < 4; si++) acc += counts[si];   // Detailfeld = Boost-Beginn (max Sättigung)
  _e3DetailIdx = Math.min(pts.length - 1, acc);
  _e3MakeVideo = true;
  // Das Mesh MUSS mit Stirnringen gebaut werden → Anregung „Lastfall" + Spulenströme erzwingen.
  const ex = document.getElementById('e3_excitation'); if (ex) ex.value = 'loaded';
  const cc = document.getElementById('e3_coilcurr'); if (cc) cc.checked = true;
  if (typeof _updateExcitationVis === 'function') _updateExcitationVis();
  _e3RenderSweepTable();
  _toast(`🎬 Lastprofil mit ${pts.length} Punkten — „Drehzahlband berechnen" rendert danach das Video.`);
}

async function startEm3dSweep() {
  const msg = document.getElementById('e3_msg');
  const logEl = document.getElementById('e3_log');
  const btn = document.getElementById('e3_sbtn');
  if (!_e3Sweep.length) { msg.style.color = '#e57'; msg.textContent = '⚠ Keine Betriebspunkte in der Tabelle.'; return; }
  btn.disabled = true; msg.style.color = '#9c9';
  msg.textContent = `⏳ Starte Drehzahlband (${_e3Sweep.length} Punkte, Mesh nur einmal)…`;
  logEl.style.display = 'block'; logEl.textContent = '';
  document.getElementById('e3_results').innerHTML = '';
  document.getElementById('e3_sweep_results').innerHTML = '';
  _e3PlayStop();               // laufenden Player stoppen + Caches leeren (neuer Lauf)
  _e3LoadedGeom = null; _e3ShowRefineCard(false);
  try {
    const payload = await _em3dGeom();
    _em3dApplyOpts(payload);
    payload.sweep = _e3Sweep.map(p => ({ rpm: +p.rpm || 0, load_nm: +p.load_nm || 0, excitation: p.excitation || 'loaded', phase: p.phase || '' }));
    payload.detail_index = Math.max(0, Math.min(_e3DetailIdx, _e3Sweep.length - 1));
    payload.make_video = !!_e3MakeVideo;
    const r = await fetch('/em3d_sweep', { method: 'POST', headers: {'Content-Type':'application/json'},
                                           body: JSON.stringify(payload) });
    if (r.status === 503) {
      const j = await r.json(); msg.style.color = '#e57';
      msg.innerHTML = '⚠ ' + escHtml(j.error || 'Elmer fehlt').replace(/\n/g,'<br>');
      btn.disabled = false; return;
    }
    if (!r.ok) { const j = await r.json().catch(()=>({})); msg.style.color='#e57';
      msg.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false; return; }
    _pollEm3d();
  } catch (e) { msg.style.color='#e57'; msg.textContent = 'Fehler: ' + e.message; btn.disabled = false; }
}

function _renderEm3dSweep(res) {
  window._e3HasResult = true;   // ein 3D-Lauf liegt zum Speichern vor
  const msg = document.getElementById('e3_msg');
  const sbox = document.getElementById('e3_sweep_results');
  const rows = res.sweep || [];
  const nOk = rows.filter(r => r && r.ok).length;
  msg.style.color = '#6c6';
  msg.innerHTML = `✓ Drehzahlband fertig · ${nOk}/${rows.length} Punkte`
    + (res.mesh ? ` · Mesh ${res.mesh.n_nodes} Knoten (einmal gebaut)` : '');
  let h = '<div class="e3-card"><div class="section-title">🌡 Drehzahlband — Kennwerte je Betriebspunkt</div>';
  h += '<table style="width:100%;font-size:.8rem;border-collapse:collapse">'
     + '<tr style="color:#9ab;text-align:left;border-bottom:1px solid #2a2a30">'
     + '<th style="padding:4px 6px">#</th><th style="padding:4px 6px">Drehzahl [1/min]</th>'
     + '<th style="padding:4px 6px">Last [Nm]</th><th style="padding:4px 6px">Anregung</th>'
     + '<th style="padding:4px 6px">B_gap(Mitte) [T]</th><th style="padding:4px 6px">Moment [Nm]</th>'
     + '<th style="padding:4px 6px">i_q [A]</th><th style="padding:4px 6px">i_d [A]</th></tr>';
  const fmt = v => (v == null ? '—' : v);
  rows.forEach((r, i) => {
    if (!r) return;
    const detail = (i === res.detail_index);
    h += `<tr style="border-bottom:1px solid #1d1d24;${detail?'background:#1c2a22':''}${r.ok?'':'color:#c77'}">`
      + `<td style="padding:3px 6px">${i+1}${detail?' ⦿':''}${r.ok?'':' ⚠'}</td>`
      + `<td style="padding:3px 6px">${fmt(r.rpm)}</td><td style="padding:3px 6px">${fmt(r.load_nm)}</td>`
      + `<td style="padding:3px 6px">${r.excitation==='loaded'?'Lastfall':'Leerlauf'}</td>`
      + `<td style="padding:3px 6px">${fmt(r.b_gap_mid_peak)}</td><td style="padding:3px 6px">${fmt(r.torque_Nm)}</td>`
      + `<td style="padding:3px 6px">${fmt(r.iq_A)}</td><td style="padding:3px 6px">${fmt(r.id_A)}</td></tr>`;
  });
  h += '</table>';
  (res.sweep_images || []).forEach(im => {
    h += `<div style="margin-top:10px"><div style="font-size:.8rem;color:#9aa;margin-bottom:4px">${escHtml(im.title||'')}</div>`
       + `<img src="${im.b64}" style="max-width:100%;border:1px solid #222;border-radius:4px"></div>`;
  });
  if (res.video) {
    const pid = (window._activeProject && _activeProject.id) || 'current';
    const vurl = `/project/${encodeURIComponent(pid)}/video/em3d?t=${Date.now()}`;
    h += `<div style="margin-top:12px"><div style="font-size:.82rem;color:#ffd479;margin-bottom:4px">🎬 Dynamisches Lastprofil — |B|-Sättigung · Feldlinien · Ströme (i_q/i_d) · Zeitleiste</div>`
       + `<video controls loop muted style="max-width:100%;border:1px solid #333;border-radius:6px;background:#000" src="${vurl}"></video>`
       + `<div style="margin-top:4px"><a href="${vurl}" download style="color:#7ad;font-size:.78rem">⬇ Video herunterladen (MP4)</a></div></div>`;
  }
  if ((res.warnings || []).length)
    h += `<div style="margin-top:8px;font-size:.76rem;color:#c96">⚠ ${res.warnings.map(escHtml).join('<br>⚠ ')}</div>`;
  // Drehzahl/Lastfall-Auswahl: jeder gerechnete Punkt hat eine eigene 3D-VTP (+ Feldlinien).
  // Der Umschalter sitzt in der Viewer-Bedienleiste (e3_clipbar) → direkt am 3D-Bild.
  const okIdx = rows.map((r, i) => (r && r.ok) ? i : -1).filter(i => i >= 0);
  const sweepPts = okIdx.map(i => ({ i, rpm: rows[i].rpm, load: rows[i].load_nm }));
  h += `<div style="margin-top:10px;font-size:.78rem;color:#9aa">Detailpunkt #${(res.detail_index??0)+1} — volles 3D-Feld unten`
     + (sweepPts.length > 1 ? ` · im Browser-Viewer zwischen allen Lastfällen umschaltbar (Auswahl „🧊 Lastfall")` : '')
     + `:</div></div>`;
  sbox.innerHTML = h;
  // Detailpunkt über die vorhandene Einzelpunkt-Anzeige (Viewer/ParaView/VTU/2D-vs-3D).
  if (res.detail) {
    _renderEm3d(res.detail);                       // setzt _e3ViewIdx=null, _e3SweepPoints=null
    // Browser-Viewer beim Sweep auf den Detailpunkt-Index vorbelegen + Lastfälle hinterlegen.
    _e3ViewIdx = (res.detail_index == null ? null : res.detail_index);
    _e3SweepPoints = sweepPts.length > 1 ? sweepPts : null;
  } else document.getElementById('e3_results').innerHTML = '';
}

async function startEm3d() {
  const msg = document.getElementById('e3_msg');
  const logEl = document.getElementById('e3_log');
  const btn = document.getElementById('e3_btn');
  btn.disabled = true; msg.style.color = '#9c9'; msg.textContent = '⏳ Starte 3D-Berechnung…';
  logEl.style.display = 'block'; logEl.textContent = '';
  document.getElementById('e3_results').innerHTML = '';
  document.getElementById('e3_sweep_results').innerHTML = '';
  _e3PlayStop();               // laufenden Player stoppen + Caches leeren (neuer Lauf)
  _e3LoadedGeom = null;        // frischer Lauf → Grob-Quelle ist dieser Lauf (Formular maßgeblich)
  _e3ShowRefineCard(false);
  try {
    const payload = await _em3dGeom();
    _em3dApplyOpts(payload);
    const r = await fetch('/em3d', { method: 'POST', headers: {'Content-Type':'application/json'},
                                     body: JSON.stringify(payload) });
    if (r.status === 503) {
      const j = await r.json(); msg.style.color = '#e57';
      msg.innerHTML = '⚠ ' + escHtml(j.error || 'Elmer fehlt').replace(/\n/g,'<br>');
      btn.disabled = false; return;
    }
    if (!r.ok) { const j = await r.json().catch(()=>({})); msg.style.color='#e57';
      msg.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false; return; }
    _pollEm3d();
  } catch (e) { msg.style.color='#e57'; msg.textContent = 'Fehler: ' + e.message; btn.disabled = false; }
}

// ➕ 3D-Berechnungen in die Server-Warteschlange einreihen (gleiche Payload-Builder wie
// startEm3d/startEm3dSweep, aber POST /jobs/add statt sofortigem Start).
async function queueEm3d() {
  const payload = await _em3dGeom();
  _em3dApplyOpts(payload);
  const t = '3D-Feld ' + ((payload.geom && payload.geom.magShape) || '');
  await enqueueJobs([{ type: 'em3d', title: t.trim(), payload }],
                    document.getElementById('e3_msg'));
}

async function queueEm3dSweep() {
  if (!_e3Sweep.length) { alert('Keine Betriebspunkte in der Tabelle.'); return; }
  const payload = await _em3dGeom();
  _em3dApplyOpts(payload);
  payload.sweep = _e3Sweep.map(p => ({ rpm: +p.rpm || 0, load_nm: +p.load_nm || 0,
                                       excitation: p.excitation || 'loaded', phase: p.phase || '' }));
  payload.detail_index = Math.max(0, Math.min(_e3DetailIdx, _e3Sweep.length - 1));
  payload.make_video = !!_e3MakeVideo;
  await enqueueJobs([{ type: 'em3d_sweep',
                       title: `3D-Drehzahlband (${_e3Sweep.length} Punkte)`, payload }],
                    document.getElementById('e3_msg'));
}

// Ein-Pol-Sektor (Symmetrie-Submodell): eine Pol-Teilung fein, anti-periodisch, zum vollen
// Motor gespiegelt. Teilt _em3d_state/Status/Viewer mit /em3d (über _pollEm3d).
async function startEm3dSector() {
  const msg = document.getElementById('e3_msg');
  const logEl = document.getElementById('e3_log');
  const btn = document.getElementById('e3_secbtn');
  btn.disabled = true; msg.style.color = '#9c9';
  msg.textContent = '⏳ Starte Pol-Berechnung (Symmetrie, feines Netz)…';
  logEl.style.display = 'block'; logEl.textContent = '';
  document.getElementById('e3_results').innerHTML = '';
  document.getElementById('e3_sweep_results').innerHTML = '';
  _e3PlayStop();               // laufenden Player stoppen + Caches leeren (neuer Lauf)
  _e3LoadedGeom = null; _e3ShowRefineCard(false);
  try {
    const payload = await _em3dGeom();
    _em3dApplyOpts(payload);
    payload.node_budget_pct = +(document.getElementById('e3_node_budget')||{}).value || 100;
    const r = await fetch('/em3d/sector', { method: 'POST', headers: {'Content-Type':'application/json'},
                                            body: JSON.stringify(payload) });
    if (r.status === 503) {
      const j = await r.json(); msg.style.color = '#e57';
      msg.innerHTML = '⚠ ' + escHtml(j.error || 'Elmer fehlt').replace(/\n/g,'<br>');
      btn.disabled = false; return;
    }
    if (!r.ok) { const j = await r.json().catch(()=>({})); msg.style.color='#e57';
      msg.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false; return; }
    _pollEm3d();
  } catch (e) { msg.style.color='#e57'; msg.textContent = 'Fehler: ' + e.message; btn.disabled = false; }
}

async function startEm3dPreview() {
  const msg = document.getElementById('e3_msg');
  const logEl = document.getElementById('e3_log');
  const btn = document.getElementById('e3_pbtn');
  btn.disabled = true; msg.style.color = '#9c9'; msg.textContent = '⏳ Baue 3D-Modell…';
  logEl.style.display = 'block'; logEl.textContent = '';
  document.getElementById('e3_results').innerHTML = '';
  document.getElementById('e3_sweep_results').innerHTML = '';
  _e3PlayStop();               // laufenden Player stoppen + Caches leeren (neuer Lauf)
  try {
    const payload = await _em3dGeom();
    _em3dApplyOpts(payload);
    const r = await fetch('/em3d/preview', { method: 'POST', headers: {'Content-Type':'application/json'},
                                             body: JSON.stringify(payload) });
    if (!r.ok) { const j = await r.json().catch(()=>({})); msg.style.color='#e57';
      msg.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false; return; }
    _pollEm3d(true);
  } catch (e) { msg.style.color='#e57'; msg.textContent = 'Fehler: ' + e.message; btn.disabled = false; }
}

function _e3ShowAbort(show) {
  const b = document.getElementById('e3_abort'); if (b) b.style.display = show ? '' : 'none';
}

// Laufende 3D-Berechnung abbrechen. Beim Drehzahlband/Sweep behält der Server das bis dahin
// gerechnete Teilergebnis (Status „aborted" → _pollEm3d rendert es); danach ist sofort ein
// neuer Lauf startbar.
async function abortEm3d() {
  const b = document.getElementById('e3_abort'); if (b) b.disabled = true;
  const msg = document.getElementById('e3_msg');
  if (msg) { msg.style.color = '#fb0'; msg.textContent = '⛔ Breche ab… (laufenden Löser stoppen)'; }
  try { await fetch('/em3d/abort', { method: 'POST' }); } catch (e) {}
  if (b) b.disabled = false;   // _pollEm3d blendet ihn aus, sobald der Lauf endet
}

async function _pollEm3d(isPreview) {
  const msg = document.getElementById('e3_msg');
  const logEl = document.getElementById('e3_log');
  const enable = () => { ['e3_btn','e3_pbtn','e3_sbtn','e3_secbtn'].forEach(id => {
                         const el=document.getElementById(id); if(el)el.disabled=false; });
                         _e3ShowAbort(false); };
  try {
    const s = await fetch('/em3d/status').then(x => x.json());
    if (Array.isArray(s.log)) { logEl.textContent = s.log.join('\n'); logEl.scrollTop = logEl.scrollHeight; }
    // Abbrechen-Knopf nur bei einem echten (abbrechbaren) Elmer-Lauf zeigen, nicht bei der Vorschau.
    _e3ShowAbort(s.status === 'running' && !isPreview);
    if (s.status === 'done' || s.status === 'aborted') {
      if (s.result && s.result.sweep) _renderEm3dSweep(s.result);
      else if (s.result) _renderEm3d(s.result);
      if (s.status === 'aborted') {
        msg.style.color = '#fb0';
        const nd = s.result && s.result.n_done;
        msg.textContent = '⛔ Abgebrochen'
          + (nd != null ? ` — ${nd} gerechnete(r) Punkt(e) behalten (speicherbar). ` : ' — ')
          + 'Neustart jederzeit möglich.';
      }
      enable(); return;
    }
    if (s.status === 'error') { msg.style.color='#e57'; msg.textContent = '⚠ ' + (s.error || 'Fehlgeschlagen'); enable(); return; }
  } catch (e) {}
  setTimeout(() => _pollEm3d(isPreview), 1500);
}

/* Die Bedienleiste + der Rahmen des eingebetteten 3-D-Betrachters -- EINMAL.
 *
 * **Warum das eine Funktion ist und kein zweiter Block:** `_renderEm3d` hat
 * zwei Zweige, und der Betrachter stand nur im einen. Der andere (`res.bericht`
 * -- Axialfluss und die harmonische Asynchronmaschine) zeichnete zwar den Knopf
 * „🧊 Im Browser ansehen", aber nicht den `#e3_viewer3d`, den `openBrowser3d()`
 * sucht; die Funktion kehrt dort in der zweiten Zeile zurueck (`if (!div)
 * return;`). Gemessen am 11.10.2026: der Knopf war da, klickbar, und tat
 * **nichts** -- kein Fehler in der Konsole, kein Bild, keine Feldlinien. Mit
 * ihm fehlten auch der Feldlinien-Schalter, der Dichteregler, die
 * Schnittebene und die Ansichtsknoepfe, also genau das, wofuer es den
 * Betrachter gibt. Zwei Abschriften waeren dieselbe Falle noch einmal.
 */
function _e3BetrachterHtml() {
  let h = '';
  h += `<div id="e3_view_fs">`;   // Wrapper für Bedienleiste + Viewer → gemeinsam ins Vollbild
  h += `<div id="e3_clipbar" style="margin-top:10px;display:none;align-items:center;gap:12px;flex-wrap:wrap;`
     + `background:#16161c;border:1px solid #2e2e36;border-radius:6px;padding:8px 11px;font-size:.78rem;color:#bcd">`
     + `<span id="e3_speed_wrap" style="display:none;gap:5px;align-items:center;border-right:1px solid #2e2e36;padding-right:12px"></span>`
     + `<span style="display:flex;gap:4px;align-items:center;border-right:1px solid #2e2e36;padding-right:12px">`
     +   `<span style="color:#89a">Ansicht</span>`
     +   `<button onclick="_e3SetView('xy')" title="Blick entlang Z-Achse (Querschnitt / Stirnseite)" style="width:auto;padding:3px 9px;background:#2e3a4a">XY</button>`
     +   `<button onclick="_e3SetView('xz')" title="Blick entlang Y-Achse (Längsschnitt)" style="width:auto;padding:3px 9px;background:#2e3a4a">XZ</button>`
     +   `<button onclick="_e3SetView('yz')" title="Blick entlang X-Achse (Längsschnitt)" style="width:auto;padding:3px 9px;background:#2e3a4a">YZ</button>`
     +   `<button onclick="_e3SetView('iso')" title="Iso-Perspektive (Standardansicht)" style="width:auto;padding:3px 9px;background:#3a4a3a">⬛ Iso</button>`
     +   `<button onclick="_e3Fullscreen()" id="e3_fs_btn" title="3D-Ansicht als Vollbild (Esc zum Verlassen)" style="width:auto;padding:3px 9px;background:#3a4a3a">⛶ Vollbild</button>`
     + `</span>`
     + `<label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="e3_clip_on" onchange="_e3SetClip()" style="width:auto"> ✂️ Schnittebene</label>`
     + `<label style="display:flex;gap:5px;align-items:center">Achse `
     + `<select id="e3_clip_axis" onchange="_e3SetClip()" style="width:auto;padding:3px"><option value="x">X</option><option value="y" selected>Y</option><option value="z">Z (axial)</option></select></label>`
     + `<label style="display:flex;gap:6px;align-items:center;flex:1;min-width:140px">Position `
     + `<input type="range" id="e3_clip_pos" min="0" max="1000" value="500" oninput="_e3SetClip()" style="flex:1"></label>`
     + `<button onclick="_e3FlipClip()" style="width:auto;padding:4px 10px;background:#3a4a6a">↔ Seite</button>`
     + `<label style="display:flex;gap:6px;align-items:center;cursor:pointer;border-left:1px solid #2e2e36;padding-left:12px"><input type="checkbox" id="e3_lines_on" onchange="_e3ToggleLines()" style="width:auto"> 🧵 Feldlinien</label>`
     + `<button onclick="_e3Festhalten()" title="Diese Ansicht festhalten — sie landet im Projekt und lässt sich in den Elmer-Bericht und in eigene Berichte einfügen" style="width:auto;padding:3px 9px;background:#5a3a6a;border-left:1px solid #2e2e36;margin-left:6px">📷 Festhalten</button>`
     + `<span id="e3_shot_msg" style="font-size:.7rem;color:#6c8"></span>`
     + `<label id="e3_line_dens_wrap" style="display:none;gap:5px;align-items:center" title="Dichte der Feldlinien (wenige ↔ viele)">Dichte `
     + `<input type="range" id="e3_line_density" min="8" max="100" value="45" oninput="_e3ApplyLineDensity()" style="width:90px"></label>`
     + `<label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="e3_mesh_on" onchange="_e3ToggleMesh()" style="width:auto"> 🕸 Netz</label>`
     + `<label style="display:flex;gap:6px;align-items:center;cursor:pointer"><input type="checkbox" id="e3_logscale" checked onchange="_e3ApplyColor()" style="width:auto"> 📈 log |B|</label>`
     + `<label style="display:flex;gap:5px;align-items:center;flex:1;min-width:130px" title="Obergrenze der Farbskala">|B|max `
     + `<input type="range" id="e3_vmax" min="5" max="100" value="100" oninput="_e3ApplyColor()" style="flex:1"></label>`
     + `</div>`;
  h += `<div id="e3_viewer3d" style="margin-top:8px;width:100%;height:480px;background:#0d0d12;`
     + `border:1px solid #333;border-radius:6px;display:none;position:relative"></div>`;
  h += `</div>`;   // /e3_view_fs
  return h;
}

function _renderEm3d(res) {
  const msg = document.getElementById('e3_msg');
  const box = document.getElementById('e3_results');
  if (!res) { msg.textContent = '⚠ Kein Ergebnis.'; return; }
  // **Die Asynchronmaschine liefert hier etwas ANDERES**, und das wird auch
  // so gezeigt: ihr 3-D-Weg ist harmonisch (`ema_em3d_harm`) und beantwortet
  // die Frage nach dem KURZSCHLUSSRING — zweimal dasselbe Netz, einmal mit
  // leitendem und einmal mit isolierendem Ring. Ein Feldbild und eine
  // 2D-gegen-3D-Tabelle gibt es dort nicht; sie zu erfinden waere schlimmer
  // als der Bericht, den der Loeser wirklich schreibt.
  if (res.bericht) {
    // **Welcher Löser den Bericht geschrieben hat, sagt `art`/`source` — nicht
    // die blosse Anwesenheit von `bericht`.** Den trägt der Axiallauf genauso,
    // und er landete dadurch unter der Überschrift „Asynchronmaschine" samt
    // einem Satz über den Käfig (gemessen 11.10.2026: `art="axial"`,
    // `source="axial_em3d"`, Überschrift trotzdem ASM). Die Zahlen darunter
    // waren die richtigen — eine Überschrift, die eine andere Maschine nennt,
    // ist trotzdem eine falsche Auskunft.
    const _ax = (res.art === 'axial') || (res.source === 'axial_em3d');
    window._e3HasResult = true;
    msg.style.color = '#6c6';
    msg.innerHTML = (_ax ? '✓ Axialfluss-Ringsektor · ' : '✓ 3-D harmonisch (Kurzschlussring) · ')
      + (res.mesh ? res.mesh.nodes + ' Knoten, ' + res.mesh.tets + ' Tetraeder' : '')
      + (_ax && res.mesh && res.mesh.sektor_grad
         ? ' · ein Pol (' + (+res.mesh.sektor_grad).toFixed(1) + '°)' : '');
    box.innerHTML =
      '<div class="e3-card"><h4>'
      + (_ax ? '⊙ 3-D-Ringsektor — Axialflussmaschine'
             : '🧲 3-D harmonisch — Asynchronmaschine') + '</h4>'
      + '<div class="hint" style="font-size:11px;color:#9aa;margin-bottom:6px">'
      + (_ax
         ? 'Gerechnet hat <code>ema_axial_em3d</code>: EINE Polteilung als '
           + '<b>anti-periodischer Ringsektor</b>, magnetostatisch, im Leerlauf. '
           + 'Danebengestellt ist der abgewickelte <b>Mehrschnitt</b> auf '
           + 'derselben Geometrie — die Abweichung über dem Radius IST das '
           + 'Ergebnis (der <code>∂/∂r</code>-Term, den der Mehrschnitt fallen lässt).'
         : 'Der Käfig braucht ein <b>zeitabhängiges</b> Feld; der magnetostatische '
           + '3-D-Pfad kann ihn nicht darstellen. Gerechnet hat deshalb '
           + '<code>ema_em3d_harm</code> — derselbe Knopf, der richtige Löser.')
      + '</div>'
      + '<pre style="white-space:pre;overflow-x:auto;font-size:11px;'
      + 'line-height:1.45;margin:0">'
      + String(res.bericht).replace(/[&<>]/g,
          c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) + '</pre>'
      // **Der Browser-Betrachter gilt auch hier.** Er ist nicht an die PSM
      // gebunden: er lädt eine schlanke .vtp der Festkörperoberfläche und eine
      // zweite mit Feldlinien, und `ema_em3d_harm.browser_dateien` schreibt
      // beide aus der harmonischen VTU. Was das Bild zeigt, steht dabei — eine
      // Amplitude ist phasenunabhängig, ein Linienbild ist es nicht.
      + (res.browser && res.browser.hinweis
         ? '<div class="hint" style="font-size:11px;color:#9aa;margin-top:8px">'
           + String(res.browser.hinweis).replace(/[&<>]/g,
               c => ({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])) + '</div>'
         : '')
      + '<div style="margin-top:8px">'
      + (res.vtp_path ? '<button onclick="openBrowser3d()" style="background:#2e6a4a;width:auto;padding:6px 12px">🧊 Im Browser ansehen (3D) — mit Feldlinien</button> ' : '')
      + '<button onclick="openParaview()">🧊 In ParaView öffnen</button> '
      + '<a href="/em3d/vtu" download>⬇ VTU laden</a></div>'
      // **Und der Betrachter selbst gehoert dazu.** Der Knopf stand hier
      // seit dem ASM-Umbau, der Rahmen, den er oeffnet, nicht — er wurde nur
      // im anderen Zweig gebaut, und `openBrowser3d()` kehrt ohne ihn
      // wortlos zurueck. Gemeinsame Quelle: `_e3BetrachterHtml`.
      + (res.vtp_path ? _e3BetrachterHtml() : '')
      + '</div>';
    _e3PlayStop();
    _e3ViewIdx = null; _e3SweepPoints = null;
    return;
  }
  window._e3HasResult = true;   // ein 3D-Lauf liegt zum Speichern vor
  _e3PlayStop();            // laufenden Player stoppen + Punkt-Caches leeren (neuer Lauf)
  _e3ViewIdx = null;        // Einzellauf: Routen liefern den Detail-/Einzelpfad (Sweep setzt danach um)
  _e3SweepPoints = null;    // Einzellauf: kein Lastfall-Umschalter (Sweep setzt danach)
  msg.style.color = '#6c6';
  const c = res.compare_2d || {};
  if (res.preview) {
    msg.innerHTML = `✓ 3D-Modell · ${res.mesh ? res.mesh.n_nodes+' Knoten, '+res.mesh.n_magnets+' Magnete' : ''}`;
  } else {
    msg.innerHTML = `✓ 3D-Feld fertig · ${res.mesh ? res.mesh.n_nodes+' Knoten' : ''} · `
      + (res.b_gap_mid_peak!=null ? `B_gap 3D(Mitte)=${res.b_gap_mid_peak} T` : '')
      + (c.B_gap_2D!=null ? ` vs 2D-FDM=${c.B_gap_2D} T` : '');
  }
  let h = '';
  const op = res.operating_point;
  if (op && op.excitation === 'loaded') {
    h += `<div style="background:#16161c;border:1px solid #2e2e36;border-radius:6px;padding:8px 11px;margin:6px 0;font-size:.8rem;color:#bcd">`
       + `<b>⚡ Betriebspunkt:</b> ${op.rpm} 1/min · ${op.load_nm} Nm → `
       + `i_q = ${op.iq_A} A · i_d = ${op.id_A} A · |I| = ${op.is_peak_A} A (Spitze)`
       + `<div style="color:#9a8;margin-top:3px">3D-Feld: `
       + (op.field_loaded ? 'Lastfeld mit Statorströmen + Stirnring-Schließung (vereinfacht: Grundwelle, lineares Eisen)'
                          : 'Magnetfeld (Leerlauf) — die Ströme oben sind der berechnete Betriebspunkt.')
       + `</div></div>`;
  }
  // Modelltreue des Netzes: die Magnettaschen (Luftkappen um jeden vergrabenen Magneten)
  // sind in der 2D-FDM-Lösung IMMER da; im 3D-Netz kann der Selbstheil-Monitor sie
  // abschalten. Ohne diese Zeile war „waren die Taschen überhaupt drin?" im UI nicht
  // beantwortbar — deshalb steht sie hier, auch wenn alles in Ordnung ist.
  if (res.mesh && res.mesh.n_magnets != null) {
    const npk = res.mesh.n_pockets;
    const okpk = npk > 0;
    h += `<div style="font-size:.78rem;color:#9aa;margin:6px 0">🧲 Netz: `
       + `${res.mesh.n_magnets} Magnete · `
       + (npk == null ? 'Magnettaschen: unbekannt (Netz vor dieser Version gebaut)'
                      : (okpk ? `<span style="color:#8c8">${npk} Magnettaschen</span>`
                                + (res.mesh.pocket_clear_mm ? ` (Spalt ${res.mesh.pocket_clear_mm} mm)` : '')
                              : `<span style="color:#e8a">keine Magnettaschen</span> — die Magnete sitzen `
                                + `im 3D-Modell in massivem Eisen, die 2D-FDM-Lösung hat Luftkappen. `
                                + `Das ist nicht nur optisch: die Kappen sind der Streupfad an den Magnetenden, `
                                + `ohne sie weicht das Luftspaltfeld deutlich ab (an dieser Maschine gemessen +75 % Grundwelle). `
                                + `Knoten-Ziel erhöhen und neu rechnen`))
       + (res.mesh.n_barriers ? ` · ${res.mesh.n_barriers} Flussbarrieren` : '')
       + `</div>`;
  }
  if (c.B_gap_2D != null) {
    const exc2 = c.excitation === 'loaded' ? 'Lastpunkt' : 'Leerlauf';
    h += `<table style="font-size:.8rem;border-collapse:collapse;margin:6px 0">
      <tr><th style="text-align:left;padding:3px 10px">Kennwert</th><th style="padding:3px 10px">2D-FDM</th><th style="padding:3px 10px">3D-Elmer</th></tr>
      <tr><td style="padding:3px 10px">B_gap [T] (${exc2})</td><td style="text-align:center">${c.B_gap_2D}</td><td style="text-align:center">${c.B_gap_3D_mid}</td></tr>`
      + (c.phase_shift_mech_deg != null
          ? `<tr><td style="padding:3px 10px">Polfolge θ [° mech]</td>`
            + `<td style="text-align:center" colspan="2">`
            + (c.orientation_ok ? `<span style="color:#8c8">✓ deckungsgleich</span>` : `<span style="color:#e88">✗ verdreht</span>`)
            + ` (Versatz ${c.phase_shift_mech_deg > 0 ? '+' : ''}${c.phase_shift_mech_deg}°, zulässig ±${c.phase_tol_mech_deg}°)</td></tr>`
          : '')
      + `</table>`
      + (c.phase_shift_mech_deg != null
          ? `<div style="font-size:.74rem;color:#889;margin:-2px 0 8px">Beide Lösungen stehen bei `
            + `Rotorwinkel 0°; die Toleranz ist die Staffelung, die es nur im 3D-Modell gibt. `
            + `Ein Vergleich gegen einen <i>Animationsframe</i> der EM-Feld-Ansicht zeigt dagegen `
            + `immer eine Verdrehung — der Frame steht bei einem anderen Rotorwinkel.</div>`
          : '');
  }
  (res.images || []).forEach(im => {
    // Das statische „3D-Feld |B| (aufgeschnitten)" ist doppelt zum interaktiven Browser-
    // Viewer (drehen/schneiden/Feldlinien/Sättigungsfarben) → im UI weglassen, sobald der
    // Viewer verfügbar ist (die .vtp existiert). Für den PDF-Bericht wird es weiter erzeugt.
    if (im.key === 'em3d_field3d' && res.vtp_path) return;
    h += `<div style="margin:8px 0"><div style="font-size:.76rem;color:#9aa">${escHtml(im.title)}</div>`
       + `<img src="${im.b64}" style="max-width:100%;border:1px solid #333;border-radius:4px"/></div>`;
  });
  if (res.vtu_path) {
    h += `<div style="margin-top:8px;display:flex;gap:14px;align-items:center;flex-wrap:wrap">`
       + (res.vtp_path ? `<button onclick="openBrowser3d()" style="background:#2e6a4a;width:auto;padding:6px 12px">🧊 Im Browser ansehen (3D)</button>` : '')
       + `<button onclick="openParaview()" style="background:#3a4a6a;width:auto;padding:6px 12px">📊 In ParaView öffnen</button>`
       + `<a href="/em3d/vtu" style="color:#7ad">⬇ VTU herunterladen</a></div>`;
    if (res.vtp_path) h += _e3BetrachterHtml();
  }
  (res.warnings || []).forEach(w => { h += `<div style="color:#e9a;font-size:.74rem">⚠ ${escHtml(w)}</div>`; });
  if (res.source === 'refine') {
    h = `<div style="background:#16161c;border:1px solid #2e6a4a;border-radius:6px;padding:8px 11px;margin:6px 0;font-size:.8rem;color:#bcd">`
      + `🔍 <b>Lokal verfeinerter Lauf</b> (volles Modell, Gebiet ${res.refine_factor||''}× feiner)`
      + `${res.mesh ? ' · '+res.mesh.n_nodes+' Knoten' : ''} — physikalisch exakt, kein Submodell.</div>` + h;
  }
  if (res.source === 'sector') {
    const ap = res.antiperiodic_err != null ? (res.antiperiodic_err*100).toFixed(1)+'%' : '—';
    h = `<div style="background:#16161c;border:1px solid #2e6a4a;border-radius:6px;padding:8px 11px;margin:6px 0;font-size:.8rem;color:#bcd">`
      + `🔁 <b>Pol-Sektor (Symmetrie)</b> — eine von ${res.poles||''} Pol-Teilungen fein gerechnet`
      + `${res.mesh ? ' ('+res.mesh.n_nodes+' Knoten/Pol'+(res.mesh.n_barriers?', '+res.mesh.n_barriers+' Barrieren':'')+')' : ''}`
      + `${res.node_budget_pct!=null ? ' · Kontingent '+res.node_budget_pct+' % von '+(res.node_budget_max||'')+' max' : ''}`
      + ` und zum vollen Motor gespiegelt. Gestufte Verfeinerung (Luftspalt/Magnete+Barrieren/grob).`
      + ` Anti-Periodizität im Eisen ${ap} (0 = exakt; Rest = Netzgröße).</div>` + h;
  }
  box.innerHTML = h;
  // Verfeinerungsgebiet-Karte nach einem echten 3D-Feldlauf (mit VTU) anbieten; bei reiner
  // Modell-Vorschau ausblenden. ROI-Felder einmalig aus der Maschinengröße vorbelegen.
  const realRun = !!res.vtu_path && !res.preview;
  _e3ShowRefineCard(realRun);
  if (realRun && !document.getElementById('e3_roi_xmin').value) _e3RoiReset();
}

// ── Eingebetteter 3D-Viewer (vtk.js, lokal eingebettet) ─────────────────────────
let _vtkLoading = null;
function _loadVtkJs() {
  if (window.vtk) return Promise.resolve();
  if (_vtkLoading) return _vtkLoading;
  _vtkLoading = new Promise((resolve, reject) => {
    const s = document.createElement('script');
    s.src = '/vendor/vtk.js';
    s.onload = () => resolve();
    s.onerror = () => reject(new Error('vtk.js konnte nicht geladen werden'));
    document.head.appendChild(s);
  });
  return _vtkLoading;
}

let _e3rw = null;
let _e3clip = null;
let _e3ViewIdx = null;       // beim Sweep: Index des angezeigten Drehzahl-Punkts (sonst null)
let _e3SweepPoints = null;   // beim Sweep: [{i,rpm,load}] für den Lastfall-Umschalter im Viewer
let _e3ViewerLive = false;   // Render-Fenster gebaut → Punktwechsel per Daten-Swap (flüssig)
let _e3PdCache = {};         // Punkt-Index → geparste vtkPolyData (Oberfläche + Bmag)
let _e3LinesCache = {};      // Punkt-Index → geparste vtkPolyData (Feldlinien)
// Punkt-VTP (Oberfläche) holen — aus dem Cache oder per Fetch+Parse (dann cachen).
async function _e3GetPointPd(idx) {
  const key = (idx == null ? 'single' : idx);
  if (_e3PdCache[key]) return _e3PdCache[key];
  const qs = (idx == null ? '' : '&i=' + idx);
  const buf = await fetch('/em3d/vtp?t=' + Date.now() + qs, { cache: 'no-store' })
    .then(r => { if (!r.ok) throw new Error('VTP nicht verfügbar'); return r.arrayBuffer(); });
  const reader = vtk.IO.XML.vtkXMLPolyDataReader.newInstance();
  reader.parseAsArrayBuffer(buf);
  const pd = reader.getOutputData(0);
  _e3PdCache[key] = pd;
  return pd;
}
// Feldlinien-VTP holen — aus dem Cache oder per Fetch+Parse (dann cachen).
async function _e3GetLinesPd(idx) {
  const key = (idx == null ? 'single' : idx);
  if (_e3LinesCache[key]) return _e3LinesCache[key];
  const qs = (idx == null ? '' : '&i=' + idx);
  const buf = await fetch('/em3d/streamlines?t=' + Date.now() + qs, { cache: 'no-store' })
    .then(r => { if (!r.ok) throw new Error('Feldlinien nicht verfügbar'); return r.arrayBuffer(); });
  const reader = vtk.IO.XML.vtkXMLPolyDataReader.newInstance();
  reader.parseAsArrayBuffer(buf);
  const pd = reader.getOutputData(0);
  _e3LinesCache[key] = pd;
  return pd;
}
// Alle Sweep-Punkte (und Feldlinien, falls aktiv) im Hintergrund vorladen → flüssiges Abspielen.
function _e3PreloadSweep() {
  if (!_e3SweepPoints) return;
  const linesOn = document.getElementById('e3_lines_on')?.checked;
  _e3SweepPoints.forEach(p => {
    if (!_e3PdCache[p.i]) _e3GetPointPd(p.i).catch(() => {});
    if (linesOn && !_e3LinesCache[p.i]) _e3GetLinesPd(p.i).catch(() => {});
  });
}
// Feld-Daten im BESTEHENDEN Viewer austauschen (kein Render-Fenster-Neuaufbau) → flüssig.
// fixScale=true hält die Farbskala fest (Feldwachstum über Last/Drehzahl bleibt vergleichbar).
function _e3ShowPointData(pd, fixScale) {
  if (!_e3rw || !_e3clip || !pd) return;
  _e3clip.mapper.setInputData(pd);
  _e3clip.bounds = pd.getBounds();
  if (!fixScale) {
    const arr = pd.getPointData().getArrayByName('Bmag');
    if (arr) _e3clip.dataRange = _e3Percentiles(arr.getData(), 0.02, 0.98);
  }
  try { _e3clip.mapper.modified(); } catch (e) {}
  _e3SetClip();      // Schnittebene an die (ggf. leicht anderen) Bounds anpassen
  _e3ApplyColor();   // Skala/Legende neu (bei fixScale unverändert)
  _e3rw.getRenderWindow().render();
}

// ── 📄 Elmer-Bericht ueber den 3-D-Lauf ─────────────────────────────────────
async function startEm3dBericht() {
  const btn = document.getElementById('btn_em3d_bericht');
  const msg = document.getElementById('e3_bericht_msg');
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  const mitAnsichten = document.getElementById('e3_bericht_ansichten')?.checked;
  if (btn) btn.disabled = true;
  if (msg) { msg.style.color = '#9aa'; msg.textContent = '⏳ Elmer-Bericht …'; }
  let auswahl = null;
  if (!mitAnsichten) auswahl = [];        // leere Liste = ausdruecklich keine
  const r = await fetch('/em3d/bericht', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ projekt: pid, ansichten: auswahl }) }).then(x => x.json());
  if (r.error) {
    if (btn) btn.disabled = false;
    if (msg) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; }
    return;
  }
  _pollEm3dBericht();
}

async function _pollEm3dBericht() {
  let s;
  try { s = await fetch('/em3d/bericht/status').then(x => x.json()); }
  catch (e) { setTimeout(_pollEm3dBericht, 1500); return; }
  const msg = document.getElementById('e3_bericht_msg');
  if (msg) msg.textContent = (s.log || []).slice(-1)[0] || '…';
  if (s.status === 'running') { setTimeout(_pollEm3dBericht, 1000); return; }
  const btn = document.getElementById('btn_em3d_bericht');
  if (btn) btn.disabled = false;
  if (!msg) return;
  if (s.status === 'error') { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (s.error || 'Fehler'); return; }
  msg.style.color = '#9c9';
  msg.innerHTML = '✓ fertig — <a href="/em3d/bericht/download" target="_blank" style="color:#6cf">bericht_elmer.pdf öffnen</a>';
}

// Die festgehaltenen Ansichten des Projekts als kleine Vorschau + Löschen.
async function e3RefreshAnsichten() {
  const box = document.getElementById('e3_ansichten_liste');
  if (!box) return;
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  let l = [];
  try { l = await fetch('/project/' + pid + '/ansichten').then(r => r.json()); } catch (e) {}
  if (!Array.isArray(l) || !l.length) {
    box.innerHTML = '<span style="font-size:.72rem;color:#789">Noch keine Ansicht festgehalten — im Browser-Betrachter auf 📷 drücken.</span>';
    return;
  }
  box.innerHTML = l.map(a => `<figure style="margin:0;width:110px">
      <img src="/project/${pid}/ansicht/${encodeURIComponent(a.datei)}" style="width:100%;border-radius:4px;cursor:zoom-in"
           onclick="window.open(this.src)" title="${escHtml((a.einstellungen&&a.einstellungen.skala)||'')}"/>
      <figcaption style="font-size:.62rem;color:#789;text-align:center;line-height:1.25">
        ${escHtml((a.zeit||'').slice(5))}
        <button onclick="e3DeleteAnsicht('${escHtml(a.datei)}')" style="background:#633;width:auto;padding:1px 5px;font-size:.6rem;margin-top:2px">🗑</button>
      </figcaption></figure>`).join('');
}

async function e3DeleteAnsicht(datei) {
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try { await fetch('/project/' + pid + '/ansicht/' + encodeURIComponent(datei) + '/delete', { method: 'POST' }); } catch (e) {}
  e3RefreshAnsichten();
}

// ── 📷 Die eingestellte Ansicht festhalten ──────────────────────────────────
// Was hier eingestellt ist — Blickrichtung, Schnittebene, Farbskala, Feldlinien,
// Lastfall — kommt aus KEINEM Erzeuger: die Berichtsbilder rendert matplotlib
// bzw. `render_field_3d` mit fester Kamera. Wer die gedrehte, aufgeschnittene
// Ansicht zeigen wollte, machte bisher ein Bildschirmfoto.
// vtk.js gibt das WebGL-Bild ueber `captureNextImage()` heraus: erst anmelden,
// dann rendern, dann faellt die data-URL an. Ein `canvas.toDataURL()` liefert
// ohne `preserveDrawingBuffer` ein leeres Bild.
async function _e3Festhalten() {
  const msg = document.getElementById('e3_shot_msg');
  const zeig = (t, f) => { if (msg) { msg.style.color = f || '#6c8'; msg.textContent = t; } };
  if (!_e3rw) { zeig('⚠ kein Betrachter offen', '#e9a'); return; }
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    const ogl = _e3rw.getOpenGLRenderWindow ? _e3rw.getOpenGLRenderWindow() : null;
    if (!ogl || !ogl.captureNextImage) { zeig('⚠ dieser vtk.js-Build kann nicht abgreifen', '#e9a'); return; }
    zeig('📷 …');
    const p = ogl.captureNextImage();
    _e3rw.getRenderWindow().render();
    const png = await p;
    // Die Einstellungen gehoeren zum Bild: ein |B|-Bild ohne seine Skala ist
    // kein Messwert, sondern ein Muster.
    const leg = document.getElementById('e3_legend');
    const sel = document.getElementById('e3_view_speed');
    const ein = {
      skala: leg ? leg.textContent.replace(/\s+/g, ' ').trim().slice(0, 60) : '',
      lastfall: (sel && sel.options.length) ? sel.options[sel.selectedIndex].text : '',
      schnitt: document.getElementById('e3_clip_on')?.checked
               ? ('Schnitt ' + (document.getElementById('e3_clip_axis')?.value || '')) : '',
      feldlinien: !!document.getElementById('e3_lines_on')?.checked,
    };
    const name = 'e3_' + (ein.lastfall || 'ansicht').replace(/[^A-Za-z0-9]+/g, '_').slice(0, 20);
    const r = await fetch('/project/' + pid + '/ansicht', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ png, name, beschriftung: '3-D-Feld |B| aus dem Betrachter',
                             einstellungen: ein }) }).then(x => x.json());
    if (r.error) { zeig('⚠ ' + r.error, '#e57'); return; }
    zeig('✓ festgehalten (' + Math.round((r.bytes || 0) / 1024) + ' kB)');
    e3RefreshAnsichten();
    if (typeof brRefreshBestand === 'function') brRefreshBestand();
  } catch (e) { zeig('⚠ ' + e.message, '#e57'); }
}

async function openBrowser3d(idx, swap) {
  if (idx !== undefined && idx !== null) _e3ViewIdx = idx;
  const div = document.getElementById('e3_viewer3d');
  if (!div) return;
  // Schnellpfad: Viewer läuft schon → nur die Punkt-Daten tauschen (flüssiges Abspielen/Scrubben).
  if (swap && _e3ViewerLive && _e3rw && _e3clip) {
    try {
      const pd = await _e3GetPointPd(_e3ViewIdx);
      _e3ShowPointData(pd, document.getElementById('e3_play_fixscale')?.checked);
      if (document.getElementById('e3_lines_on')?.checked) _e3SetLinesForIdx(_e3ViewIdx);
      _e3PlaySyncControls();
      return;
    } catch (e) { /* Fallback: voller Aufbau */ }
  }
  div.style.display = 'block';
  div.innerHTML = '<div style="padding:14px;color:#9aa;font-size:.82rem">⏳ Lade 3D-Viewer…</div>';
  try {
    await _loadVtkJs();
    const pd = await _e3GetPointPd(_e3ViewIdx);
    div.innerHTML = '';
    const arr = pd.getPointData().getArrayByName('Bmag');
    // Robuste Skala: das 2./98. Perzentil statt min/max — Eckenspitzen am Magneten
    // bestimmen sonst die Obergrenze, sodass das moderate Statorfeld kaum Farbe bekommt.
    const dataRange = arr ? _e3Percentiles(arr.getData(), 0.02, 0.98) : [0, 1];
    const ctf = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
    const mapper = vtk.Rendering.Core.vtkMapper.newInstance();
    mapper.setInputData(pd);
    mapper.setLookupTable(ctf);
    mapper.setScalarModeToUsePointFieldData();
    mapper.setColorByArrayName('Bmag');
    mapper.setInterpolateScalarsBeforeMapping(true);
    const actor = vtk.Rendering.Core.vtkActor.newInstance();
    actor.setMapper(mapper);
    // Schnittebene (Clipping) für „in den Motor schauen" — Bounds für den Positions-Slider.
    const plane = vtk.Common.DataModel.vtkPlane.newInstance();
    _e3clip = { mapper, plane, bounds: pd.getBounds(), flip: 1, ctf, dataRange, actor };
    _e3ApplyColor();   // baut ctf + Legende aus log-Toggle + vmax-Slider
    if (_e3rw) { try { _e3rw.delete(); } catch (e) {} }
    _e3rw = vtk.Rendering.Misc.vtkGenericRenderWindow.newInstance({ background: [0.05, 0.05, 0.07] });
    _e3rw.setContainer(div);
    _e3rw.getRenderer().addActor(actor);
    // Depth-Peeling für korrekte Transparenz (Oberfläche wird bei Feldlinien durchsichtig).
    try {
      const r = _e3rw.getRenderer();
      r.setUseDepthPeeling(true); r.setOcclusionRatio(0.1); r.setMaximumNumberOfPeels(4);
    } catch (e) {}
    _e3rw.getRenderer().resetCamera();
    // leichte Iso-Perspektive statt frontal
    try {
      const cam = _e3rw.getRenderer().getActiveCamera();
      cam.azimuth(35); cam.elevation(-25);
      _e3rw.getRenderer().resetCameraClippingRange();
    } catch (e) {}
    _e3rw.resize();
    _e3rw.getRenderWindow().render();
    // Hinweis + Farbskala als HTML-Overlay (vtkScalarBarActor ist im UMD-Build nicht enthalten)
    const tip = document.createElement('div');
    tip.style.cssText = 'position:absolute;top:6px;left:10px;font-size:.7rem;color:#789;pointer-events:none';
    tip.textContent = 'ziehen = drehen · Rad = zoomen';
    div.appendChild(tip);
    const leg = document.createElement('div');
    leg.id = 'e3_legend';
    leg.style.cssText = 'position:absolute;top:6px;right:10px;font-size:.66rem;color:#cdd;pointer-events:none;text-align:center';
    div.appendChild(leg);
    if (_e3clip) _e3clip.legEl = leg;
    // Schnittebenen-Bedienleiste einblenden + Slider neutralisieren.
    const bar = document.getElementById('e3_clipbar');
    if (bar) { bar.style.display = 'flex';
      const on = document.getElementById('e3_clip_on'); if (on) on.checked = false;
      const pos = document.getElementById('e3_clip_pos'); if (pos) pos.value = 500;
      if (_e3clip) _e3clip.flip = 1;
    }
    _e3PopulateSpeedSelect();   // Lastfall-Umschalter (nur Sweep) befüllen/zeigen
    _e3ApplyColor();   // Legende mit dem aktuellen Bereich füllen
    // Feldlinien neu laden, falls der Toggle aktiv ist (z. B. nach Drehzahl-Wechsel) —
    // setzt auch die Oberflächen-Transparenz.
    const linesOn = document.getElementById('e3_lines_on');
    if (linesOn && linesOn.checked) await _e3ToggleLines();
    else _e3SurfaceOpacity();
    // Verfeinerungs-Quader (gelbes Drahtgitter) zeichnen, wenn die ROI-Karte sichtbar ist.
    if (document.getElementById('e3_refine_card')?.style.display !== 'none') _e3DrawRoiBox();
    _e3ViewerLive = true;       // ab jetzt Punktwechsel per Daten-Swap (flüssig)
    _e3PreloadSweep();          // restliche Sweep-Punkte im Hintergrund vorladen
  } catch (e) {
    _e3ViewerLive = false;
    div.innerHTML = '<div style="padding:14px;color:#e57;font-size:.82rem">⚠ ' + escHtml(e.message)
      + '. Alternativ „📊 In ParaView öffnen" nutzen.</div>';
  }
}

// Robuste Perzentil-Grenzen einer (typisierten) Werteliste — ohne die ganze Kopie zu
// sortieren wäre genauer, aber die Oberflächen-Punktzahl ist klein genug.
function _e3Percentiles(data, pLo, pHi) {
  const a = Array.prototype.slice.call(data).filter(v => isFinite(v)).sort((x, y) => x - y);
  if (!a.length) return [0, 1];
  const q = f => a[Math.min(a.length - 1, Math.max(0, Math.round(f * (a.length - 1))))];
  let lo = q(pLo), hi = q(pHi);
  if (!(hi > lo)) hi = lo + 1e-6;
  return [lo, hi];
}

// Farbskala (Blau→Grün→Rot) neu aufbauen aus log-Toggle + |B|max-Slider und die
// HTML-Legende aktualisieren. Log spreizt die kleinen/mittleren Feldwerte (Statorjoch),
// die neben den Magnet-/Luftspaltspitzen sonst alle ganz unten in der Skala kleben.
function _e3ApplyColor() {
  if (!_e3clip || !_e3clip.ctf) return;
  const ctf = _e3clip.ctf;
  const [dlo, dhi] = _e3clip.dataRange || [0, 1];
  const log = document.getElementById('e3_logscale')?.checked;
  const vfrac = (+document.getElementById('e3_vmax')?.value || 100) / 100;
  const hi = Math.max(dlo + 1e-6, dlo + (dhi - dlo) * vfrac);
  const lo = Math.max(log ? Math.max(hi * 1e-3, 1e-4) : 0, dlo);
  ctf.removeAllPoints();
  const stops = [[0, 0, 0, 1], [0.5, 0, 1, 0], [1, 1, 0, 0]];   // blau→grün→rot
  for (const [f, r, g, bl] of stops) {
    const x = log ? lo * Math.pow(hi / lo, f) : lo + (hi - lo) * f;
    ctf.addRGBPoint(x, r, g, bl);
  }
  _e3clip.mapper.setScalarRange(lo, hi);
  try { _e3clip.mapper.modified(); } catch (e) {}
  if (_e3clip.linesMapper) {
    _e3clip.linesMapper.setScalarRange(lo, hi);
    try { _e3clip.linesMapper.modified(); } catch (e) {}
  }
  if (_e3rw) _e3rw.getRenderWindow().render();
  const leg = _e3clip.legEl;
  if (leg) {
    const mid = log ? Math.sqrt(lo * hi) : (lo + hi) / 2;
    leg.innerHTML = `<div>|B| [T]${log ? ' (log)' : ''}</div>`
      + `<div style="display:flex;gap:4px;justify-content:center;margin-top:3px">`
      + `<div style="display:flex;flex-direction:column;justify-content:space-between;height:120px">`
      + `<span>${hi.toFixed(2)}</span><span>${mid.toFixed(2)}</span><span>${lo.toFixed(2)}</span></div>`
      + `<div style="width:16px;height:120px;border:1px solid #555;background:linear-gradient(to top,#00f,#0f0,#f00)"></div></div>`;
  }
}

// Drahtgitter (Netz-Kanten) auf den Festkörper-Oberflächen ein-/ausblenden — zeigt die
// Oberflächen-Netzdichte (am Luftspalt/an den Magneten feiner). Das volumetrische Luftspalt-
// Feinnetz selbst sieht man am besten im „Netz-Querschnitt"-Bild (enthält die Luft).
function _e3ToggleMesh() {
  if (!_e3clip || !_e3clip.actor || !_e3rw) return;
  const on = document.getElementById('e3_mesh_on')?.checked;
  const prop = _e3clip.actor.getProperty();
  prop.setEdgeVisibility(!!on);
  prop.setEdgeColor(0.85, 0.88, 0.95);
  prop.setLineWidth(1);
  _e3rw.getRenderWindow().render();
}

// Lastfall-Umschalter (nur Sweep) in der Viewer-Bedienleiste befüllen — direkt am 3D-Bild
// zwischen allen gerechneten Betriebspunkten (Drehzahl/Last) des Drehzahlbands wechseln.
function _e3PopulateSpeedSelect() {
  const wrap = document.getElementById('e3_speed_wrap');
  if (!wrap) return;
  if (!_e3SweepPoints || _e3SweepPoints.length < 2) { wrap.style.display = 'none'; wrap.innerHTML = ''; return; }
  wrap.style.display = 'flex';
  wrap.style.alignItems = 'center';
  wrap.style.gap = '6px';
  wrap.style.flexWrap = 'wrap';
  const pos = _e3SweepPoints.findIndex(p => p.i === _e3ViewIdx);
  _e3PlayPos = pos >= 0 ? pos : 0;
  const playing = !!_e3PlayTimer;
  wrap.innerHTML =
      `<button id="e3_play_btn" onclick="_e3PlayToggle()" title="Betriebspunkte abspielen (über Drehzahl bzw. Last)" style="width:auto;padding:3px 9px;background:${playing ? '#6a3a3a' : '#2e6a4a'}">${playing ? '⏸' : '▶'}</button>`
    + `<input type="range" id="e3_play_slider" min="0" max="${_e3SweepPoints.length - 1}" step="1" value="${_e3PlayPos}" oninput="_e3Scrub(this.value)" style="width:120px" title="Betriebspunkt scrubben">`
    + `<select id="e3_play_tempo" onchange="_e3PlaySetTempo(this.value)" title="Abspieltempo" style="width:auto;padding:3px">`
    +   `<option value="0.5">0.5×</option><option value="1" selected>1×</option><option value="2">2×</option></select>`
    + `<label style="display:flex;gap:3px;align-items:center;cursor:pointer" title="am Ende von vorn"><input type="checkbox" id="e3_play_loop" checked style="width:auto"> ⟳</label>`
    + `<label style="display:flex;gap:3px;align-items:center;cursor:pointer" title="Farbskala beim Abspielen fixieren (Feldwachstum bleibt vergleichbar)"><input type="checkbox" id="e3_play_fixscale" checked style="width:auto"> Skala</label>`
    + `<span id="e3_play_lbl" style="min-width:150px;color:#bcd"></span>`
    + `<select id="e3_view_speed" onchange="_e3SelectPoint(+this.value)" title="direkt zu Betriebspunkt" style="width:auto;padding:3px">`
    +   _e3SweepPoints.map(p => `<option value="${p.i}"${p.i === _e3ViewIdx ? ' selected' : ''}>`
        + `#${p.i + 1} · ${p.rpm} 1/min · ${p.load} Nm</option>`).join('')
    + `</select>`;
  _e3PlayUpdateLabel();
}

// ── Player: die berechneten Betriebspunkte flüssig abspielen (dynamische Darstellung
// über Drehzahl bzw. über Last). Nutzt den Punkt-VTP-Cache → nur Daten-Swap, kein Neuaufbau.
let _e3PlayTimer = null, _e3PlayPos = 0, _e3PlaySpeed = 1;
function _e3PlayTempoMs() { return Math.round(700 / (_e3PlaySpeed || 1)); }
function _e3PlayStartTimer() { _e3PlayStopTimer(); _e3PlayTimer = setInterval(_e3PlayTick, _e3PlayTempoMs()); }
function _e3PlayStopTimer() { if (_e3PlayTimer) { clearInterval(_e3PlayTimer); _e3PlayTimer = null; } }
function _e3PlaySetTempo(v) { _e3PlaySpeed = +v || 1; if (_e3PlayTimer) _e3PlayStartTimer(); }
function _e3PlayToggle() {
  if (!_e3SweepPoints || _e3SweepPoints.length < 2) return;
  if (_e3PlayTimer) _e3PlayStopTimer(); else _e3PlayStartTimer();
  _e3PlaySyncControls();
}
function _e3PlayTick() {
  if (!_e3SweepPoints) { _e3PlayStopTimer(); return; }
  let next = _e3PlayPos + 1;
  if (next >= _e3SweepPoints.length) {
    if (document.getElementById('e3_play_loop')?.checked) next = 0;
    else { _e3PlayStopTimer(); _e3PlaySyncControls(); return; }
  }
  _e3Scrub(next);
}
// pos = Slider-Position 0…N-1 (nicht der Punkt-Index). Fährt den Punkt per Daten-Swap an.
function _e3Scrub(pos) {
  if (!_e3SweepPoints) return;
  pos = Math.max(0, Math.min(_e3SweepPoints.length - 1, +pos || 0));
  _e3PlayPos = pos;
  openBrowser3d(_e3SweepPoints[pos].i, true);   // swap → _e3PlaySyncControls() folgt
}
function _e3SelectPoint(pointIdx) {
  const pos = _e3SweepPoints ? _e3SweepPoints.findIndex(p => p.i === pointIdx) : -1;
  if (pos >= 0) _e3Scrub(pos);
}
function _e3PlaySyncControls() {
  const sl = document.getElementById('e3_play_slider'); if (sl) sl.value = _e3PlayPos;
  const pt = _e3SweepPoints && _e3SweepPoints[_e3PlayPos];
  const sel = document.getElementById('e3_view_speed'); if (sel && pt) sel.value = pt.i;
  const btn = document.getElementById('e3_play_btn');
  if (btn) { const on = !!_e3PlayTimer; btn.textContent = on ? '⏸' : '▶'; btn.style.background = on ? '#6a3a3a' : '#2e6a4a'; }
  _e3PlayUpdateLabel();
}
function _e3PlayUpdateLabel() {
  const lbl = document.getElementById('e3_play_lbl');
  const pt = _e3SweepPoints && _e3SweepPoints[_e3PlayPos];
  if (lbl && pt) lbl.textContent = `#${pt.i + 1} · ${pt.rpm} 1/min · ${pt.load} Nm`;
}
// Player stoppen + Caches leeren + Viewer-Status zurücksetzen (bei neuem Lauf / neuem Render).
function _e3PlayStop() {
  _e3PlayStopTimer();
  _e3PdCache = {}; _e3LinesCache = {};
  _e3ViewerLive = false;
}

// Oberflächen-Transparenz an den Feldlinien-Status koppeln: sind die Feldlinien an, wird die
// |B|-Oberfläche (Sättigungsdarstellung) durchsichtig, damit die Linien im Inneren sichtbar sind.
function _e3SurfaceOpacity() {
  if (!_e3clip || !_e3clip.actor) return;
  const linesOn = document.getElementById('e3_lines_on')?.checked;
  _e3clip.actor.getProperty().setOpacity(linesOn ? 0.18 : 1.0);
}

// Magnetfeldlinien (serverseitig getracete Polylinien) ein-/ausblenden. Werden lazy
// als schlanke .vtp geladen und mit DERSELBEN |B|-Farbskala (ctf) wie die Oberfläche
// eingefärbt, damit sie log/|B|max-Reglern folgen. Beim Sweep über `?i=` der Drehzahl-Punkt.
// Sind sie an, wird die |B|-Oberfläche transparent (Linien im Inneren sichtbar).
// Feldlinien-Polydata in den Viewer setzen (Actor neu aufbauen). Von _e3ToggleLines und
// vom Player (Punktwechsel) genutzt.
function _e3SetLines(pd) {
  if (!_e3clip || !_e3rw || !pd) return;
  if (_e3clip.linesActor) { _e3rw.getRenderer().removeActor(_e3clip.linesActor); }
  const lm = vtk.Rendering.Core.vtkMapper.newInstance();
  lm.setLookupTable(_e3clip.ctf);
  lm.setScalarModeToUsePointFieldData();
  lm.setColorByArrayName('Bmag');
  lm.setInterpolateScalarsBeforeMapping(true);
  const la = vtk.Rendering.Core.vtkActor.newInstance();
  la.setMapper(lm);
  la.getProperty().setLineWidth(2);
  _e3clip.linesMapper = lm;
  _e3clip.linesActor = la;
  _e3clip.linesFull = pd;              // volle (dichte) Feldlinien — der Slider dünnt sie aus
  _e3rw.getRenderer().addActor(la);
  _e3ApplyLineDensity();               // setzt den Mapper-Input auf die ausgedünnte Teilmenge
  _e3SurfaceOpacity();                 // |B|-Oberfläche transparent, damit die Linien sichtbar werden
  _e3ApplyColor();                     // Linien an die aktuelle Farbskala koppeln
  _e3rw.getRenderWindow().render();
}
// Feldlinien für einen Punkt (aus Cache oder Fetch) setzen — beim Abspielen; blockiert nicht.
function _e3SetLinesForIdx(idx) { _e3GetLinesPd(idx).then(pd => _e3SetLines(pd)).catch(() => {}); }

async function _e3ToggleLines() {
  if (!_e3clip || !_e3rw) return;
  const on = document.getElementById('e3_lines_on')?.checked;
  const densWrap = document.getElementById('e3_line_dens_wrap');
  if (!on) {
    if (_e3clip.linesActor) { _e3rw.getRenderer().removeActor(_e3clip.linesActor); }
    if (densWrap) densWrap.style.display = 'none';
    _e3SurfaceOpacity();   // Oberfläche wieder deckend
    _e3rw.getRenderWindow().render();
    return;
  }
  try {
    const pd = await _e3GetLinesPd(_e3ViewIdx);
    _e3SetLines(pd);
    if (densWrap) densWrap.style.display = 'flex';
  } catch (e) {
    _toast('⚠ Feldlinien: ' + e.message);
    const cb = document.getElementById('e3_lines_on'); if (cb) cb.checked = false;
    if (densWrap) densWrap.style.display = 'none';
    _e3SurfaceOpacity();   // Fehlschlag → Oberfläche deckend lassen
  }
}

// Feldlinien-Dichte (Slider): die voll exportierten Linien clientseitig ausdünnen — jede
// k-te Polylinie behalten (k aus dem Slider-Prozentwert). Schnell, ohne Server-Round-Trip,
// für Einzellauf UND jeden Sweep-Punkt. Die Punkte (+ Bmag) bleiben unverändert, nur die
// Linien-Zellen werden auf eine Teilmenge reduziert.
function _e3ApplyLineDensity() {
  if (!_e3clip || !_e3clip.linesMapper || !_e3clip.linesFull || !_e3rw) return;
  const full = _e3clip.linesFull;
  const frac = Math.max(0.01, (+document.getElementById('e3_line_density')?.value || 45) / 100);
  const step = Math.max(1, Math.round(1 / frac));   // jede step-te Linie behalten
  const data = full.getLines().getData();           // [n,i0,…,in-1, n,j0,…]
  const kept = [];
  let p = 0, ci = 0;
  while (p < data.length) {
    const n = data[p];
    if (ci % step === 0) { kept.push(n); for (let k = 1; k <= n; k++) kept.push(data[p + k]); }
    p += n + 1; ci++;
  }
  const sub = vtk.Common.DataModel.vtkPolyData.newInstance();
  sub.setPoints(full.getPoints());
  sub.getLines().setData(Uint32Array.from(kept));
  const bm = full.getPointData().getArrayByName('Bmag');
  if (bm) { sub.getPointData().addArray(bm); sub.getPointData().setActiveScalars('Bmag'); }
  _e3clip.linesMapper.setInputData(sub);
  try { _e3clip.linesMapper.modified(); } catch (e) {}
  _e3rw.getRenderWindow().render();
}

// Schnittebene aus der Bedienleiste auf den Mapper anwenden.
function _e3SetClip() {
  if (!_e3clip || !_e3rw) return;
  const on = document.getElementById('e3_clip_on')?.checked;
  const mapper = _e3clip.mapper, plane = _e3clip.plane, b = _e3clip.bounds;
  mapper.removeAllClippingPlanes();
  if (on) {
    const axis = document.getElementById('e3_clip_axis')?.value || 'y';
    const t = (+document.getElementById('e3_clip_pos')?.value || 500) / 1000;
    const idx = axis === 'x' ? 0 : axis === 'z' ? 2 : 1;
    const lo = b[idx * 2], hi = b[idx * 2 + 1];
    const o = [(b[0] + b[1]) / 2, (b[2] + b[3]) / 2, (b[4] + b[5]) / 2];
    o[idx] = lo + t * (hi - lo);
    const n = [0, 0, 0]; n[idx] = _e3clip.flip;
    plane.setOrigin(o[0], o[1], o[2]);
    plane.setNormal(n[0], n[1], n[2]);
    mapper.addClippingPlane(plane);
  }
  try { mapper.modified(); } catch (e) {}
  _e3rw.getRenderWindow().render();
}

function _e3FlipClip() {
  if (!_e3clip) return;
  _e3clip.flip = -_e3clip.flip;
  const on = document.getElementById('e3_clip_on');
  if (on && !on.checked) on.checked = true;
  _e3SetClip();
}

// Standard-Kameraorientierungen für den Browser-3D-Viewer (Feld + Flusslinien). Z ist die
// Motorachse (axial), X/Y die Querschnittsebene. Die Blickrichtung + View-Up werden gesetzt,
// resetCamera() passt anschließend Abstand/Zoom an die Bounds an.
function _e3SetView(view) {
  if (!_e3rw) return;
  const ren = _e3rw.getRenderer();
  const cam = ren.getActiveCamera();
  const b = (_e3clip && _e3clip.bounds) || ren.computeVisiblePropBounds();
  const cx = (b[0] + b[1]) / 2, cy = (b[2] + b[3]) / 2, cz = (b[4] + b[5]) / 2;
  const dx = (b[1] - b[0]) || 1, dy = (b[3] - b[2]) || 1, dz = (b[5] - b[4]) || 1;
  const d = Math.sqrt(dx * dx + dy * dy + dz * dz) || 1;   // nur Richtung zählt (resetCamera skaliert)
  cam.setFocalPoint(cx, cy, cz);
  if (view === 'xy')      { cam.setPosition(cx, cy, cz + d); cam.setViewUp(0, 1, 0); }  // Blick −Z
  else if (view === 'xz') { cam.setPosition(cx, cy - d, cz); cam.setViewUp(0, 0, 1); }  // Blick +Y
  else if (view === 'yz') { cam.setPosition(cx + d, cy, cz); cam.setViewUp(0, 0, 1); }  // Blick −X
  else { cam.setPosition(cx + d * 0.7, cy - d * 0.7, cz + d * 0.5); cam.setViewUp(0, 0, 1); } // Iso
  ren.resetCamera();                    // Abstand an Bounds anpassen (Blickrichtung bleibt)
  ren.resetCameraClippingRange();
  _e3rw.getRenderWindow().render();
}

// Vollbild-Umschaltung des eingebetteten 3D-Viewers: das Wrapper-Element #e3_view_fs (Bedienleiste
// + Viewer) geht per nativer Fullscreen-API ins Vollbild, sodass die Steuerung (Ansicht/Schnitt/
// Feldlinien/Farbe) auch im Vollbild erreichbar bleibt. Die vtk.js-GenericRenderWindow richtet sich
// nach der Container-Größe → beim Ein-/Austritt Wrapper auf Spalten-Flex (volle Höhe) stellen, den
// Viewer den Rest füllen lassen und resize()+render() aufrufen. Handler nur EINMAL registriert.
let _e3FsHooked = false;
function _e3Fullscreen() {
  const wrap = document.getElementById('e3_view_fs');
  const div = document.getElementById('e3_viewer3d');
  if (!wrap || !div) return;
  if (!_e3FsHooked) {
    _e3FsHooked = true;
    document.addEventListener('fullscreenchange', () => {
      const w = document.getElementById('e3_view_fs');
      const d = document.getElementById('e3_viewer3d');
      if (!w || !d) return;
      const fs = document.fullscreenElement === w;
      // Inline-Styles schlagen UA-:fullscreen → Layout explizit setzen bzw. zurücknehmen.
      if (fs) {
        w.style.cssText = 'display:flex;flex-direction:column;height:100%;width:100%;background:#0d0d12;box-sizing:border-box;padding:8px';
        d.style.flex = '1 1 auto';
        d.style.height = 'auto';
        d.style.marginTop = '8px';
      } else {
        w.style.cssText = '';
        d.style.flex = '';
        d.style.height = '480px';
      }
      const btn = document.getElementById('e3_fs_btn');
      if (btn) btn.textContent = fs ? '⛶ Vollbild verlassen' : '⛶ Vollbild';
      // vtk.js an die neue Größe anpassen (nach dem Layout-Reflow).
      setTimeout(() => { if (_e3rw) { try { _e3rw.resize(); _e3rw.getRenderWindow().render(); } catch (e) {} } }, 60);
    });
  }
  if (document.fullscreenElement === wrap) {
    document.exitFullscreen && document.exitFullscreen();
  } else if (wrap.requestFullscreen) {
    wrap.requestFullscreen().catch(() => _toast('Vollbild vom Browser abgelehnt'));
  } else {
    _toast('Vollbild wird vom Browser nicht unterstützt');
  }
}

async function openParaview() {
  try {
    const r = await fetch('/em3d/paraview').then(x => x.json());
    if (r.error) { alert((r.need_install ? '' : 'Fehler: ') + r.error); return; }
    _toast('📊 ParaView wird geöffnet…');
  } catch (e) { alert('ParaView konnte nicht gestartet werden: ' + e.message); }
}
