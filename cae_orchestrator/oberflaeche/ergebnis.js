// Der Ergebnisreiter: alles, was ein fertiges `results.json` zeichnet.
//
// Reine Darstellung -- gerechnet wird hier nichts, und keine Zahl entsteht
// hier, die nicht aus dem Lauf kommt.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

async function loadResults() {
  const data = await fetch('/results').then(r => r.json());
  document.getElementById('analysis-progress').classList.remove('show');
  document.getElementById('results-content').style.display   = 'block';

  renderSummary(data.summary);
  renderField(data.em);
  renderCadImages(data.cad_images);
  renderAirgap(data.em);
  renderEmCurve(data.em);
  renderPower(data.power);
  renderStress(data.structural_fem, data.structural_sweep, data.structural_sweep_chart_b64);
  renderAxialStruktur(data.axial_struktur, data.axial_struktur_chart_b64);
  renderConnection(data.connection);
  renderMehrkoerper(data.structural_fem);
  renderMagnetlast(data.magnetlast, data.structural_fem);
  renderDeformation(data.deformation, data.structural_fem);
  renderThermal(data.thermal);
  renderDriveCycle(data.drivecycle);
  renderDriveCycleExtra(data.drivecycle_vollast,   'cycle-autobahn',  'cycle-autobahn-energy',  'cycle-autobahn-stats',  'rtab-btn-cycle-autobahn',  'cycle-autobahn-thermal',  'cycle-autobahn-therm-avg',  'cycle-autobahn-therm-peak',  'cycle-autobahn-therm-warn');
  renderDriveCycleExtra(data.drivecycle_anhaenger, 'cycle-anhaenger', 'cycle-anhaenger-energy', 'cycle-anhaenger-stats', 'rtab-btn-cycle-anhaenger', 'cycle-anhaenger-thermal', 'cycle-anhaenger-therm-avg', 'cycle-anhaenger-therm-peak', 'cycle-anhaenger-therm-warn');
  renderManual(data.manual);

  document.getElementById('btn_analyse').disabled = false;
  document.getElementById('btn_analyse').textContent = '⚙ Erneut analysieren';
  document.getElementById('btn_freecad').style.display  = 'block';
  document.getElementById('btn_step').style.display     = 'block';
  refreshProjectList();

  try {
    const s = await fetch('/status').then(r => r.json());
    renderRating(s && s.project_id);
    pjUpdateReportCard(s && s.project_id, true);   // Bericht-Karte auf Tab ① freischalten
  } catch (e) { renderRating(null); }

  showFrame(0);
}

// ── Ergebnis-Bewertung (gut/schlecht) → LLM-Trainingsfile ───────────────────
let _ratingPid = null;

function _ratingHighlight(label) {
  const g = document.getElementById('rate_gut'), b = document.getElementById('rate_schlecht');
  if (!g || !b) return;
  g.style.outline = label === 'gut' ? '2px solid #6f6' : 'none';
  b.style.outline = label === 'schlecht' ? '2px solid #f88' : 'none';
}

async function renderRating(pid) {
  _ratingPid = pid || null;
  const stat = document.getElementById('rate_status');
  const auto = document.getElementById('rate_auto');
  const cmt  = document.getElementById('rate_comment');
  if (cmt) cmt.value = '';
  _ratingHighlight(null);
  if (auto) auto.textContent = '';
  if (stat) stat.textContent = '';
  if (!pid) { if (stat) stat.textContent = '(kein aktives Projekt)'; return; }
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/rating').then(x => x.json());
    if (r.label) {
      _ratingHighlight(r.label);
      if (stat) stat.textContent = (r.label_source === 'auto')
        ? `vorsortiert (Heuristik): ${r.label} — zum Bestätigen/Ändern klicken`
        : `bewertet: ${r.label}`;
    }
    else if (stat) stat.textContent = 'noch nicht bewertet';
    if (cmt && r.comment) cmt.value = r.comment;
    if (auto && r.auto) auto.textContent =
      `Heuristik-Vorschlag: ${r.auto.suggestion} — ${(r.auto.reasons || []).join('; ')}`;
  } catch (e) { if (stat) stat.textContent = ''; }
  renderAkte(pid);
}

// ── Projektakte-Panel (Verlauf · Notizen · Verknüpfungen · Projekt-RAG) ──────
const _AKTE_ACTIONS = { analyse:'Vollanalyse', design_ai:'KI-Entwurf', rating:'Bewertung',
  report:'Bericht', clone:'Geklont', import:'Importiert' };
function _akteAction(a){ if(!a) return ''; if(a.startsWith('recompute:')) return 'Nachgerechnet ('+a.slice(10)+')';
  return _AKTE_ACTIONS[a.split(':')[0]] || a; }

async function renderAkte(pid) {
  const body = document.getElementById('akte-body');
  if (!body) return;
  if (!pid) { body.style.opacity = .5; return; }
  body.style.opacity = 1;
  body.dataset.pid = pid;
  try {
    const m = await fetch('/project/' + encodeURIComponent(pid) + '/manifest').then(x => x.json());
    if (m.error) return;
    if (document.getElementById('akte_status')) document.getElementById('akte_status').value = m.status || 'gerechnet';
    document.getElementById('akte_tags').value = (m.tags || []).join(', ');
    document.getElementById('akte_notes').value = m.notes || '';
    // Evolution
    const evo = (m.evolution || []);
    document.getElementById('akte_evolution').innerHTML = evo.length
      ? evo.map((e, i) => {
          const ch = Object.keys(e.changed_inputs || {});
          const chs = ch.length ? ch.join(', ') : '—';
          const note = e.note ? ` · <i style="color:#9ab">${escHtml(e.note)}</i>` : '';
          return `<div style="padding:3px 0;border-bottom:1px solid #2a2f38">
            <b>${i+1}.</b> ${escHtml((e.ts||'').slice(0,16).replace('T',' '))} — <span style="color:#9bd">${escHtml(_akteAction(e.action))}</span>
            <span style="color:#889;font-size:.72rem">${escHtml(chs)}</span>${note}</div>`;
        }).join('')
      : '<span style="color:#778">noch keine Stufen</span>';
    // Links
    const links = (m.links || []);
    document.getElementById('akte_links').innerHTML = links.length
      ? links.map(l => `<div style="display:flex;justify-content:space-between;align-items:center;padding:2px 0">
          <span>⚖ <a href="#" onclick="loadProjectById('${l.id}');return false" style="color:#9bd">${escHtml(l.label||l.id)}</a></span>
          <button onclick="removeAkteLink('${l.id}')" title="Verknüpfung entfernen" style="background:#5a2a2a;width:auto;padding:2px 8px;font-size:.72rem">✕</button></div>`).join('')
      : '<span style="color:#778">keine Verknüpfungen</span>';
    // Link-Picker aus der Projektliste füllen
    try {
      const j = await fetch('/projects').then(x => x.json());
      const pick = document.getElementById('akte_link_pick');
      pick.innerHTML = (j.projects || []).filter(p => p.id !== pid)
        .map(p => `<option value="${p.id}">${escHtml(p.label || p.id)}</option>`).join('');
    } catch (e) {}
    renderAkteRag(pid);
  } catch (e) {}
}

async function renderAkteRag(pid) {
  try {
    const [rag, att] = await Promise.all([
      fetch('/project/' + encodeURIComponent(pid) + '/rag').then(x => x.json()),
      fetch('/project/' + encodeURIComponent(pid) + '/attachments').then(x => x.json()),
    ]);
    const docs = (rag.documents || []);
    const atts = (att.attachments || []);
    const dHtml = docs.length
      ? docs.map(d => `<div style="display:flex;justify-content:space-between;padding:2px 0">
          <span>📄 ${escHtml(d.title)} <span style="color:#778;font-size:.72rem">(${d.n_chunks} Abschnitte)</span></span>
          <button onclick="delAkteRag('${pid}','${d.id}')" style="background:#5a2a2a;width:auto;padding:2px 8px;font-size:.72rem">✕</button></div>`).join('')
      : '<span style="color:#778">keine Wissens-Dokumente</span>';
    const aHtml = atts.length
      ? '<div style="margin-top:5px;color:#9ab;font-size:.74rem">Anhänge: ' + atts.map(a => escHtml(a.name)).join(', ') + '</div>'
      : '';
    document.getElementById('akte_rag').innerHTML = dHtml + aHtml;
  } catch (e) {}
}

async function saveAkteMeta() {
  const pid = document.getElementById('akte-body').dataset.pid;
  if (!pid) return;
  const tags = document.getElementById('akte_tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const msg = document.getElementById('akte_status_msg');
  msg.textContent = '⏳ …';
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/meta',
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: document.getElementById('akte_status').value,
          tags, notes: document.getElementById('akte_notes').value }) }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : '✓ gespeichert';
  } catch (e) { msg.textContent = '❌ ' + e.message; }
}

async function addAkteLink() {
  const pid = document.getElementById('akte-body').dataset.pid;
  const other = document.getElementById('akte_link_pick').value;
  if (!pid || !other) return;
  await fetch('/project/' + encodeURIComponent(pid) + '/links',
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ other }) });
  renderAkte(pid);
}
async function removeAkteLink(other) {
  const pid = document.getElementById('akte-body').dataset.pid;
  if (!pid) return;
  await fetch('/project/' + encodeURIComponent(pid) + '/links/remove',
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ other }) });
  renderAkte(pid);
}
async function delAkteRag(pid, docId) {
  await fetch('/project/' + encodeURIComponent(pid) + '/rag/' + encodeURIComponent(docId) + '/delete',
    { method: 'POST' });
  renderAkteRag(pid);
}
async function uploadAkteRag(input) {
  const pid = document.getElementById('akte-body').dataset.pid;
  const f = input.files && input.files[0];
  if (!pid || !f) return;
  const msg = document.getElementById('akte_rag_msg'); msg.textContent = '⏳ einbetten…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/rag/add', { method: 'POST', body: fd }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : '✓ hinzugefügt';
    renderAkteRag(pid);
  } catch (e) { msg.textContent = '❌ ' + e.message; }
  finally { input.value = ''; }
}
async function uploadAkteAttachment(input) {
  const pid = document.getElementById('akte-body').dataset.pid;
  const f = input.files && input.files[0];
  if (!pid || !f) return;
  const msg = document.getElementById('akte_rag_msg'); msg.textContent = '⏳ lade hoch…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/attachments', { method: 'POST', body: fd }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : ('✓ Anhang gespeichert' + (r.rag_added ? ' (+RAG)' : ''));
    renderAkteRag(pid);
  } catch (e) { msg.textContent = '❌ ' + e.message; }
  finally { input.value = ''; }
}

async function setRating(label) {
  if (!_ratingPid) { alert('Kein aktives Projekt zum Bewerten'); return; }
  const comment = (document.getElementById('rate_comment').value || '').trim();
  const stat = document.getElementById('rate_status');
  stat.textContent = '⏳ speichere…';
  try {
    const r = await fetch('/project/' + encodeURIComponent(_ratingPid) + '/rating',
      { method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ label, comment }) }).then(x => x.json());
    if (r.error) { stat.textContent = '❌ ' + r.error; return; }
    _ratingHighlight(label);
    stat.textContent = `✓ gespeichert: ${label}`;
    refreshTrainingStats();
  } catch (e) { stat.textContent = '❌ ' + e.message; }
}

async function downloadStep() {
  // Browser download via direct hit
  window.location = '/download_step';
}

let _reportPoll = null;

async function generateReport(mode = 'standard') {
  let pid = (window._activeProject && _activeProject.id) || null;
  if (!pid) {
    const s = await fetch('/status').then(r => r.json()).catch(() => null);
    pid = s && s.project_id;
  }
  if (!pid) {
    alert('Kein aktives Projekt — erst Projekt wählen und Analyse abschließen');
    return;
  }

  const btnStd = document.getElementById('btn_report');
  const btnAgt = document.getElementById('btn_report_agentic');
  const btn    = mode === 'agentic' ? btnAgt : btnStd;
  const box    = document.getElementById('report_status');
  const msg    = document.getElementById('report_msg');
  const bar    = document.getElementById('report_bar');

  const isAgentic = (mode === 'agentic');
  const label     = isAgentic
    ? '⏳ 6 Experten laufen…'
    : '⏳ Bericht läuft…';

  btn.disabled = true;
  btn.textContent = label;
  box.style.display = 'block';
  msg.textContent = 'gestartet…';
  bar.style.width = '0%';
  const ragBox = document.getElementById('report_rag');
  if (ragBox) ragBox.style.display = 'none';

  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/report',
                          { method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({
                              // kein model/expert_model: der Server setzt seinen
                              // Standard (ema_report.DEFAULT_MODEL, per CAE_LLM_MODEL
                              // umstellbar) — sonst haette das Frontend eine zweite,
                              // still veraltende Quelle fuer dieselbe Entscheidung.
                              mode:         mode,
                            }) });
    if (!r.ok) {
      const e = await r.json();
      msg.textContent = '❌ ' + (e.error || 'Start fehlgeschlagen');
      btn.disabled = false; btn.textContent = isAgentic ? '🤖 Bericht Agentisch' : '📄 Bericht Standard';
      return;
    }
  } catch (e) {
    msg.textContent = '❌ Server nicht erreichbar';
    btn.disabled = false; btn.textContent = isAgentic ? '🤖 Bericht Agentisch' : '📄 Bericht Standard';
    return;
  }

  if (_reportPoll) clearInterval(_reportPoll);
  _reportPoll = setInterval(async () => {
    try {
      const st = await fetch('/report/status').then(x => x.json());
      bar.style.width = (st.progress || 0) + '%';
      const last = (st.log || []).slice(-1)[0] || '…';
      msg.textContent = last;
      if (st.status === 'done') {
        clearInterval(_reportPoll);
        btn.disabled = false;
        const dlLabel = isAgentic ? '🤖 Agentischen Bericht herunterladen' : '📄 Bericht herunterladen';
        btn.textContent = dlLabel;
        btn.style.background = '#27ae60';
        btn.onclick = () => {
          window.location = '/project/' + pid + '/report/download?mode=' + mode;
        };
        msg.innerHTML = `✓ Fertig — Klick auf den Button startet den Download.`;
        if (st.has_rag_md) showReportRag(pid);
      } else if (st.status === 'error') {
        clearInterval(_reportPoll);
        msg.textContent = '❌ Fehler — siehe Server-Log';
        btn.disabled = false;
        btn.textContent = isAgentic ? '🤖 Bericht Agentisch' : '📄 Bericht Standard';
        btn.style.background = '';
      }
    } catch (e) { /* server busy */ }
  }, 1500);
}

// Wertfreie RAG-Markdown-Aktionen (nach fertigem Bericht eingeblendet)
function showReportRag(pid) {
  const box = document.getElementById('report_rag');
  const msg = document.getElementById('report_rag_msg');
  const dl  = document.getElementById('btn_rag_dl');
  const add = document.getElementById('btn_rag_add');
  if (!box) return;
  box.style.display = 'block';
  msg.textContent = '';
  add.disabled = false; add.style.background = '#3a5a7a';
  add.textContent = '➕ In Wissensbasis aufnehmen';
  dl.onclick = () => {
    window.location = '/project/' + encodeURIComponent(pid) + '/report/rag_md';
  };
  add.onclick = async () => {
    add.disabled = true; add.textContent = '⏳ wird eingebettet…';
    msg.textContent = 'Einbettung über Ollama (nomic-embed-text)…';
    try {
      const r = await fetch('/project/' + encodeURIComponent(pid) + '/report/rag_md/add',
                            { method: 'POST' });
      const j = await r.json();
      if (r.ok) {
        add.textContent = '✓ aufgenommen';
        add.style.background = '#27ae60';
        msg.textContent = '✓ In Wissensbasis (Doku) aufgenommen' +
          (j.n_chunks ? ` — ${j.n_chunks} Abschnitte.` : '.');
      } else {
        add.disabled = false; add.textContent = '➕ In Wissensbasis aufnehmen';
        msg.textContent = '❌ ' + (j.error || 'Fehler');
      }
    } catch (e) {
      add.disabled = false; add.textContent = '➕ In Wissensbasis aufnehmen';
      msg.textContent = '❌ Server nicht erreichbar';
    }
  };
}

// ── Render helpers ─────────────────────────────────────────────────────────────

function renderSummary(s) {
  if (!s) return;
  // **`null` heisst NICHT GERECHNET und darf die Seite nicht anhalten.** Beides
  // war hier verletzt: `s.max_safe_rpm.toLocaleString()` und
  // `s.mass_g.toFixed(1)` griffen ungeprueft zu, und bei der SCHEIBE sind
  // beide per Konstruktion `null` (sie traegt weder Lame-Ring noch
  // Struktur-FEM, und ihre Masse kommt nicht aus dem Zylindermodell). Gemessen
  // am 09.10.2026: `loadProjectById` brach mit „Fehler beim Laden: Cannot read
  // properties of null (reading 'toLocaleString')" ab — ein fertig gerechneter
  // Axiallauf liess sich im Browser GAR NICHT ansehen. Eine 0 einzusetzen waere
  // der zweite Fehler: sie liest sich wie ein Messwert.
  const z = (v, nd, suf) => (v == null ? '–' : (+v).toFixed(nd) + (suf || ''));
  const n = (v, suf) => (v == null ? '–'
                         : (+v).toLocaleString('de-DE') + (suf || ''));
  const html = [
    metric('Luftspalt B_peak',   z(s.B_gap_T, 3, ' T'),                'analytisch'),
    metric('Kt',                 z(s.Kt_Nm_per_A, 3, ' Nm/A'),         '1 Wdg/Nut'),
    metric('Maxwell-Moment',     z(s.T_maxwell_Nm, 1, ' Nm'),
                                 s.T_maxwell_Nm != null ? 'FDM' : 'Luftspalt im Raster nicht aufgelöst'),
    metric('Maximalleistung',    z(s.P_max_kW, 0, ' kW'),
                                 s.P_max_rpm != null ? 'bei ' + n(s.P_max_rpm) + ' U/min' : 'Tab 🔄 EM-Kennlinie'),
    metric('Max. Drehmoment',    z(s.T_peak_max_Nm, 0, ' Nm'),
                                 'Umrichtergrenze, ungesättigt'),
    metric('Max. Drehzahl',      n(s.max_safe_rpm, ' U/min'),
                                 s.max_safe_rpm != null ? 'SF ≥ 1.5'
                                 : (s.structural_basis === 'scheibe'
                                    ? 'nicht gerechnet — ⊙ Scheibenfestigkeit'
                                    : 'nicht gerechnet')),
    metric('Masse Rotor',        z(s.mass_g, 1, ' g'),
                                 s.mass_g != null ? (s.rotor_lam || '')
                                 : 'nicht gerechnet'),
    metric('Füllgrad Hairpin',   ((s.fill_factor || 0) * 100).toFixed(1) + ' %', 'Leiter/Nutquerschnitt'),
    metric('P_Fe Schätzung',     (s.P_fe_W_est || 0).toFixed(0) + ' W','Stator, Leerlauf'),
    metric('LCM Nuten/Pole',     s.lcm_slots_poles,                     'Rastmoment-Güte'),
    // Die vierte Auslegungsgrenze. `renderSummary` ist eine ausdrueckliche
    // Kachelliste und zeigt `summary` NICHT generisch — ohne diese Zeile kaeme
    // die Saettigung hier nicht an, obwohl sie im summary steht.
    metric('Eisen ' + (s.saettigung_engstelle || ''),
           s.saettigung_pct != null ? s.saettigung_pct.toFixed(0) + ' %' : '–',
           s.B_eisen_T != null
             ? s.B_eisen_T.toFixed(2) + ' T — Flusserhaltung, kein Feldbild'
             : 'erst ab einem Lauf nach dem 13.09.2026'),
    metric('Rotorblech',         s.rotor_lam  || '–', ''),
    metric('Statorblech',        s.stator_lam || '–', ''),
    metric('Hairpin',            s.hairpin    || '–', ''),
    metric('Magnet',             s.magnet     || '–', ''),
  ].join('');
  document.getElementById('summary-grid').innerHTML = html;
  document.getElementById('summary-grid').style.gridTemplateColumns = 'repeat(4,1fr)';
}

function metric(label, value, sub) {
  return `<div class="metric-card"><div class="label">${escHtml(label)}</div>
    <div class="value">${escHtml(String(value))}</div>
    <div class="sub">${escHtml(String(sub))}</div></div>`;
}

function renderField(em) {
  if (!em) return;
  // **Die Scheibe zeigt ihre eigenen Bilder.** Der Frame-Player bleibt dabei
  // stehen und bedient — die Animation gibt es seit dem 12.10.2026 auch axial
  // (`ema_axial_fdm.frames`, abgewickelter Schnitt über dem Läuferwinkel);
  // was sich unterscheidet, ist WAS ein Bild zeigt, nicht ob es eines gibt.
  const _ax = (em.flussweg === 'axial') || !!em.axial;
  const _axw = document.getElementById('axial-field-wrap');
  if (_axw) {
    _axw.style.display = _ax ? 'flex' : 'none';
    if (_ax) {
      const si = document.getElementById('axial-schnitt-img');
      const bi = document.getElementById('axial-bgap-img');
      if (si) si.src = em.axial_schnitt_b64
        ? 'data:image/png;base64,' + em.axial_schnitt_b64 : '';
      if (bi) bi.src = em.axial_bgap_bild_b64
        ? 'data:image/png;base64,' + em.axial_bgap_bild_b64 : '';
      const n = document.getElementById('axial-field-note');
      if (n) n.innerHTML =
          'Mehrschnitt (<code>ema_axial_fdm</code>) — <b>keine 3-D-Lösung</b>: '
        + 'jeder Schnitt rechnet, als setze sich seine Geometrie radial '
        + 'unendlich fort. Die radiale Streuung an Ri und Ro misst der '
        + 'Ringsektor im Reiter 🧲 3-D-Feld nach.'
        + (em.axial_frames_r_mm
           ? '<br>Die Animation unten zeigt denselben Schnitt bei r = '
             + em.axial_frames_r_mm + ' mm über eine <b>elektrische Periode</b> '
             + '(zwei Polteilungen) — nicht über eine ganze Umdrehung, die wäre '
             + 'p-mal dasselbe Bild.'
           : '');
    }
  }
  const _rfw = document.getElementById('radial-field-wrap');
  if (_rfw) _rfw.style.display = (_ax && !(em.n_frames > 0)) ? 'none' : '';
  _framesPerRpm = em.frames_per_rpm || em.n_frames || 36;
  _frameAngles  = em.frame_angle_deg || [];
  _rpmList      = em.rpm_list || [];
  _rpmStats     = em.rpm_stats || {};
  _totalFrames  = (em.rpm_frame_count != null) ? em.rpm_frame_count : _framesPerRpm;

  // Populate RPM selector
  const sel = document.getElementById('rpm-select');
  if (sel) {
    sel.innerHTML = '';
    if (_rpmList.length === 0) {
      sel.innerHTML = '<option value="0">—</option>';
    } else {
      _rpmList.forEach(r => {
        const opt = document.createElement('option');
        opt.value = r;
        opt.textContent = r.toLocaleString() + ' U/min';
        sel.appendChild(opt);
      });
    }
    sel.onchange = () => selectRpm(+sel.value);
  }

  _currentRpm = _rpmList[0] || 0;
  if (sel && _rpmList.length) sel.value = _currentRpm;

  // Field-mode selector + video links (from em.field_modes / em.videos)
  _modeMeta = {};
  const fmSel = document.getElementById('field-mode-select');
  // **Eine LEERE Liste ist etwas anderes als eine fehlende.** `undefined` heisst
  // „Altprojekt ohne Metadaten" und bekommt den Rueckfall auf `rotate`; `[]`
  // heisst „es wurde ausdruecklich keine Animation gerechnet", und das ist beim
  // Axialfluss der Normalfall (die Rahmen rastern einen Zylinderschnitt, in dem
  // eine Scheibe ein Ring ohne Merkmal ist). Der Rueckfall griff auch dort und
  // liess den Spieler Rahmen 0 anfordern — `GET /field/0` mit 404 in der
  // Browserkonsole bei jedem Laden eines Axialprojekts (09.10.2026).
  const keineAnim = Array.isArray(em.field_modes) && em.field_modes.length === 0;
  const modes = keineAnim ? []
              : (em.field_modes || [{mode:'rotate', label:'Rotor-Rotation'}]);
  if (fmSel) {
    fmSel.innerHTML = '';
    modes.forEach(m => {
      const bucket = _MODE_BUCKET[m.mode] || 'rotate';
      _modeMeta[bucket] = m;
      const opt = document.createElement('option');
      opt.value = bucket; opt.textContent = m.label || m.mode;
      fmSel.appendChild(opt);
    });
  }
  renderFieldVideos(em.videos || {}, modes);
  _fieldMode = 'rotate';
  const hint = document.getElementById('field-mode-hint');
  if (keineAnim) {
    _totalFrames = 0;
    const sld = document.getElementById('anim-slider');
    if (sld) { sld.max = 0; sld.value = 0; sld.disabled = true; }
    if (hint) hint.innerHTML =
      '\u2299 <b>Keine Feld-Animation</b> \u2014 ihre Rahmen rastern einen '
      + 'Zylinderschnitt, und darin ist eine Scheibe ein Ring ohne Merkmal. '
      + 'Gezeichnet sind statt dessen der abgewickelte Schnitt und B_gap \u00fcber '
      + 'dem Radius (Reiter \ud83d\udcca Diagramme); bewegt sieht man die Scheibe '
      + 'im Reiter \u2299 Axialfluss.';
    const img = document.getElementById('field-img');
    if (img) img.removeAttribute('src');
  } else {
    const sld = document.getElementById('anim-slider');
    if (sld) sld.disabled = false;
    selectFieldMode('rotate');
  }
}

// Ein <video>-Player je gerechnetem Feld-Modus. Die Reihenfolge folgt
// `field_modes` (rotate → Stromwinkel → Last-Rampe), damit der Beschriftungstext
// derselbe ist wie im Modus-Auswahlfeld darüber.
function renderFieldVideos(vids, modes) {
  const wrap = document.getElementById('field-videos');
  const list = document.getElementById('field-videos-list');
  if (!wrap || !list) return;
  const stamp = window._resultsStamp || Date.now();
  const seen  = new Set();
  const items = [];
  (modes || []).forEach(m => {
    const b = _MODE_BUCKET[m.mode] || 'rotate';
    if (vids[b] && !seen.has(b)) { seen.add(b); items.push([b, m.label || m.mode]); }
  });
  // Videos ohne passenden field_modes-Eintrag (Altprojekt) trotzdem zeigen
  Object.keys(vids).forEach(b => {
    if (!seen.has(b)) { seen.add(b); items.push([b, _MODE_LABEL[b] || b]); }
  });

  if (!items.length) { wrap.style.display = 'none'; list.innerHTML = ''; return; }
  wrap.style.display = 'flex';
  list.innerHTML = items.map(([b, label]) => {
    const url = `/project/current/video/${b}?t=${stamp}`;
    return `<div>
      <div style="font-size:.8rem;color:#7db9e8;margin-bottom:4px">${escHtml(label)}</div>
      <video controls loop muted playsinline preload="metadata" src="${url}"
             style="width:100%;max-width:700px;background:#000;border-radius:6px;border:1px solid #333"></video>
      <div><a href="${url}" download="feld_${b}.mp4"
              style="color:#0cf;font-size:.75rem">⬇ ${escHtml(label)} als MP4</a></div>
    </div>`;
  }).join('');
}

function _deformImgUrl(file) {
  // cache-bust so a freshly computed project's image isn't served stale
  return '/chart/' + file + '?t=' + (window._resultsStamp || Date.now());
}

function _renderDeformStats(s) {
  const wrap = document.getElementById('deform-table-wrap');
  if (!wrap || !s) return;
  const sf = (s.safety_factor == null) ? '–' : s.safety_factor.toFixed(2);
  const sfWarn = (s.safety_factor != null && s.safety_factor < 1.0) ? ' style="color:#ff6b6b"' : '';
  wrap.innerHTML = `
    <div class="fem-box">
      <div class="row"><span class="k">Drehzahl</span><span class="v">${(s.rpm||0).toLocaleString()} U/min</span></div>
      <div class="row"><span class="k">u_max</span><span class="v">${(s.u_max_um||0).toFixed(2)} µm</span></div>
      <div class="row"><span class="k">σ_v,max</span><span class="v">${(s.sigma_max_MPa||0).toFixed(0)} MPa</span></div>
      <div class="row"><span class="k">Sicherheitsfaktor</span><span class="v"${sfWarn}>${sf}</span></div>
      <div class="row"><span class="k">Überhöhung</span><span class="v">×${s.scale_factor||1}</span></div>
    </div>`;
}

function renderDeformation(deform, fem) {
  const tabs = document.getElementById('deform-img-tabs');
  if (tabs) tabs.innerHTML = '';
  const imgEl0 = document.getElementById('deform-img');
  const hasImages = deform && ((deform.images && deform.images.length) || deform.chart_b64);
  if (!hasImages) {
    // FEM produced no result (e.g. CalculiX failed for this geometry) → no
    // deformation plot. Show a clear message instead of an empty/broken image.
    if (imgEl0) { imgEl0.removeAttribute('src'); imgEl0.alt = ''; }
    ['deform-burst-banner','deform-video-wrap','deform-source-note'].forEach(id => {
      const e = document.getElementById(id); if (e) e.style.display = 'none';
    });
    const reason = (fem && fem.solver_status && fem.solver_status !== 'OK')
      ? `CalculiX-Strukturlösung fehlgeschlagen (${fem.solver_status}).`
      : 'Keine FEM-Verformungsdaten vorhanden.';
    const wrap = document.getElementById('deform-table-wrap');
    if (wrap) wrap.innerHTML = `<div class="fem-box" style="border-left:3px solid #c0504d">
      <div style="color:#e0a0a0;font-size:.82rem;line-height:1.4">⚠ ${reason}<br/>
      Verformungsbilder und Video benötigen ein gültiges CalculiX-Ergebnis.
      Die analytische <b>Festigkeitskennlinie</b> (Tab „🏗 Festigkeit") ist davon unabhängig verfügbar.</div></div>`;
    return;
  }

  // Quelle des Bildes benennen. Der analytische Rückfall ist ein rotierender
  // Vollring (Lamé) — er hat KEINE Magnete und KEINE Magnettaschen, weil es in
  // diesem Modell gar keine gibt. Ohne diesen Hinweis sieht es aus, als würde die
  // FEM die Taschen übersehen; tatsächlich ist die FEM gar nicht gelaufen.
  const srcBox = document.getElementById('deform-source-note');
  if (srcBox) {
    if (deform.source === 'analytical') {
      const why = (fem && Array.isArray(fem.attempts) && fem.attempts.length)
        ? ' Versuche: ' + fem.attempts.map(escHtml).join(' · ') : '';
      srcBox.style.display = '';
      srcBox.innerHTML = `<div class="fem-box" style="border-left:3px solid #e0a060">
        <div style="color:#e0c090;font-size:.8rem;line-height:1.5">
        ⚠ <b>Analytischer Ersatz</b> — die CalculiX-FEM hat für diese Geometrie kein
        Ergebnis geliefert, deshalb zeigt das Bild das Modell der <b>rotierenden
        Vollscheibe</b> (Lamé). Das ist ein glatter Ring <b>ohne Magnete und ohne
        Magnettaschen</b>: die gibt es in diesem Modell nicht — es fehlt also nichts
        an der Darstellung, es fehlt das FEM-Ergebnis. Damit fehlt auch die
        Spannungsüberhöhung an den dünnen Eisenstegen über den Taschen.${why}<br/>
        Abhilfe: „🔁 Stufen nachrechnen" → <b>Festigkeit</b>, ggf. mit gröberem/feinerem
        Struktur-Netz.</div></div>`;
    } else {
      srcBox.style.display = 'none';
    }
  }

  // Burst-speed banner
  const banner = document.getElementById('deform-burst-banner');
  if (banner) {
    if (deform.burst_rpm) {
      banner.style.display = '';
      banner.innerHTML = `<div class="fem-box" style="border-left:3px solid #ff8c00">
        <div class="row"><span class="k">💥 Berstdrehzahl (SF→1)</span>
        <span class="v" style="color:#ff8c00;font-weight:bold">${(+deform.burst_rpm).toLocaleString()} U/min</span></div></div>`;
    } else { banner.style.display = 'none'; }
  }

  const imgEl = document.getElementById('deform-img');
  const images = deform.images || [];
  // Seit dem 22.10.2026 zwei Achsen: WAS (Spannung/Sicherheit/Verformung) und
  // BEI WELCHER Drehzahl. Altprojekte tragen kein `groesse` — dann gibt es nur
  // die Verformung, und die Größenreihe bleibt leer statt eine Wahl
  // vorzutäuschen, die es nicht gibt.
  const gTabs = document.getElementById('deform-groesse-tabs');
  const note  = document.getElementById('deform-darst-note');
  const gList = (deform.groessen && deform.groessen.length)
    ? deform.groessen
    : [...new Set(images.map(i => i.groesse || 'verformung'))]
        .map(k => ({ key: k, label: k.charAt(0).toUpperCase() + k.slice(1) }));
  let aktiveGroesse = gList.find(g => g.key === 'spannung') ? 'spannung'
                                                            : (gList[0] || {}).key;
  const DARST_TEXT = {
    schnitt: 'Echter Schnitt durch das Rechennetz bei halber Paketlänge — die Magnettaschen sind Löcher, weil dort keine Elemente sind. Eine FEM-Lösung bei Maximaldrehzahl, alle anderen Drehzahlen über rpm²-Skalierung (Fliehkraft ∝ ω², lineare Elastizität).',
    punktwolke: 'Projizierte Knotenwolke (keine Elementtabelle im .frd) — über die ganze Paketlänge übereinander, deshalb sind die Magnettaschen darin nicht als Löcher zu sehen.',
    analytisch: 'Analytische rotierende Vollscheibe (Lamé) — glatter Ring ohne Magnete und ohne Magnettaschen.'
  };
  if (note) {
    note.textContent = DARST_TEXT[deform.darstellung]
      || 'Eine FEM-Lösung bei Maximaldrehzahl, andere Drehzahlen über rpm²-Skalierung.';
  }

  const zeichneRpm = () => {
    if (!tabs) return;
    tabs.innerHTML = '';
    const pass = images.filter(i => (i.groesse || 'verformung') === aktiveGroesse);
    if (!pass.length) return;
    let active = pass.find(i => i.tag === 'max') || pass[0];
    const setActive = (im, btn) => {
      imgEl.src = _deformImgUrl(im.file);
      _renderDeformStats(im.stats);
      [...tabs.children].forEach(c => c.style.background = '#2a2a3e');
      btn.style.background = '#3a5a8c';
    };
    pass.forEach(im => {
      const btn = document.createElement('button');
      btn.className = 'rtab-btn'; btn.textContent = im.label;
      btn.style.cssText = 'padding:5px 10px;font-size:.74rem;background:#2a2a3e';
      btn.onclick = () => setActive(im, btn);
      tabs.appendChild(btn);
      if (im === active) setActive(im, btn);
    });
  };

  if (images.length && tabs) {
    if (gTabs) {
      gTabs.innerHTML = '';
      if (gList.length > 1) {
        gList.forEach(g => {
          const btn = document.createElement('button');
          btn.className = 'rtab-btn'; btn.textContent = g.label;
          btn.style.cssText = 'padding:5px 12px;font-size:.76rem;font-weight:600;background:#2a2a3e';
          btn.onclick = () => {
            aktiveGroesse = g.key;
            [...gTabs.children].forEach(c => c.style.background = '#2a2a3e');
            btn.style.background = '#2e6b4f';
            zeichneRpm();
          };
          gTabs.appendChild(btn);
          if (g.key === aktiveGroesse) btn.style.background = '#2e6b4f';
        });
      }
    }
    zeichneRpm();
  } else if (deform.chart_b64) {
    imgEl.src = 'data:image/png;base64,' + deform.chart_b64;
    _renderDeformStats(deform.stats);
  }

  // Deformation ramp video
  const vWrap = document.getElementById('deform-video-wrap');
  if (vWrap) {
    if (deform.video) {
      const url = '/project/current/video/struct';
      vWrap.style.display = '';
      document.getElementById('deform-video').src = url;
      document.getElementById('deform-video-dl').href = url;
    } else { vWrap.style.display = 'none'; }
  }
}

function _fillCycleTables(cyc, eBodyId, sBodyId) {
  const eBody = document.getElementById(eBodyId);
  const sBody = document.getElementById(sBodyId);
  if (!eBody || !sBody) return;
  const L = cyc.losses || {};
  eBody.innerHTML = [
    ['Batterie → Motor',     (cyc.E_elec_drv_Wh||0).toFixed(0) + ' Wh'],
    ['Motor → Räder',        (cyc.E_mech_drv_Wh||0).toFixed(0) + ' Wh'],
    ['Regen (Motor → Bat.)', (cyc.E_regen_Wh||0).toFixed(0) + ' Wh'],
    ['Batterie netto',       '<b>' + (cyc.E_elec_net_Wh||0).toFixed(0) + ' Wh</b>'],
    ['<b>Verbrauch</b>',     '<b>' + (cyc.E_per_100km_kWh||0).toFixed(2) + ' kWh/100 km</b>'],
    ['η_drive',              ((cyc.eta_drive||0)*100).toFixed(1) + ' %'],
    ['Σ Verluste',           (L.E_total_Wh||0).toFixed(0) + ' Wh'],
    ['  davon Cu',           (L.E_Cu_Wh||0).toFixed(0) + ' Wh'],
    ['  davon Fe',           (L.E_Fe_Wh||0).toFixed(0) + ' Wh'],
    ['  davon Magnet',       (L.E_Mag_Wh||0).toFixed(0) + ' Wh'],
    ['  davon Lager',        (L.E_Bear_Wh||0).toFixed(0) + ' Wh'],
  ].map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');

  sBody.innerHTML = [
    ['Zyklus',              cyc.cycle_name || '–'],
    ['Strecke',             (cyc.distance_km||0).toFixed(2) + ' km'],
    ['Dauer',               ((cyc.duration_s||0)/60).toFixed(1) + ' min'],
    ['v_max',               (cyc.v_max_kmh||0).toFixed(1) + ' km/h'],
    ['v_⌀',                 (cyc.v_avg_kmh||0).toFixed(1) + ' km/h'],
    ['rpm_max',             (cyc.rpm_max||0).toLocaleString()],
    ['rpm_RMS',             (cyc.rpm_rms||0).toLocaleString()],
    ['T_max (peak/brem.)',  (cyc.T_max||0).toFixed(1) + ' Nm'],
    ['T_RMS',               (cyc.T_rms||0).toFixed(1) + ' Nm'],
    ['Regen-Anteil',        ((cyc.regen_share||0)*100).toFixed(1) + ' %'],
  ].map(([k,v]) => `<tr><td>${k}</td><td>${v}</td></tr>`).join('');
}

function _fillCycleThermal(therm, panelId, avgBodyId, peakBodyId, warnId) {
  const panel = document.getElementById(panelId);
  if (!panel) return;
  if (!therm || therm.error) { panel.style.display = 'none'; return; }
  panel.style.display = 'block';

  function tempRow(label, T) {
    const color = T > 180 ? '#ff4444' : T > 155 ? '#e8a000' : T > 120 ? '#f0c040' : '#4fc';
    return `<tr><td>${label}</td><td style="color:${color}">${typeof T==='number' ? T.toFixed(0)+'°C' : '–'}</td></tr>`;
  }
  function fillNode(bodyId, node, T_nm, rpm_val) {
    if (!node) return;
    const body = document.getElementById(bodyId);
    if (!body) return;
    body.innerHTML =
      `<tr><td style="color:#888">T_Motor</td><td>${(T_nm||0).toFixed(0)} Nm @ ${(rpm_val||0).toFixed(0)} rpm</td></tr>` +
      tempRow('Wicklung', node.T_winding) +
      tempRow('Stator',   node.T_stator) +
      tempRow('Magnet',   node.T_magnet) +
      tempRow('Gehäuse',  node.T_housing);
  }
  fillNode(avgBodyId,  therm.avg,  therm.avg_T_Nm,  therm.avg_rpm);
  fillNode(peakBodyId, therm.peak, therm.peak_T_Nm, therm.peak_rpm);

  const warnEl = document.getElementById(warnId);
  if (warnEl) {
    const warns = (therm.warnings || []).filter(w => w);
    warnEl.innerHTML = warns.length ? warns.map(w => `<div>${w}</div>`).join('') : '';
    warnEl.style.display = warns.length ? 'block' : 'none';
  }
}

function renderDriveCycle(cyc) {
  const img = document.getElementById('cycle-img');
  if (!cyc || cyc.error) {
    img.alt = 'Fahrzyklus nicht verfügbar' + (cyc && cyc.error ? ' (' + cyc.error + ')' : '');
    document.getElementById('cycle-energy-tbody').innerHTML = '';
    document.getElementById('cycle-stats-tbody').innerHTML  = '';
    document.getElementById('cycle-wltp-thermal').style.display = 'none';
    return;
  }
  if (cyc.chart_b64) img.src = 'data:image/png;base64,' + cyc.chart_b64;
  _fillCycleTables(cyc, 'cycle-energy-tbody', 'cycle-stats-tbody');
  _fillCycleThermal(cyc.thermal, 'cycle-wltp-thermal',
    'cycle-wltp-therm-avg', 'cycle-wltp-therm-peak', 'cycle-wltp-therm-warn');
}

function renderDriveCycleExtra(cyc, imgId, eBodyId, sBodyId, tabBtnId, thermPanelId, thermAvgId, thermPeakId, thermWarnId) {
  const btn = document.getElementById(tabBtnId);
  if (!cyc || cyc.error) {
    if (btn) btn.style.display = 'none';
    return;
  }
  if (btn) btn.style.display = 'inline-block';
  const img = document.getElementById(imgId + '-img');
  if (img && cyc.chart_b64) img.src = 'data:image/png;base64,' + cyc.chart_b64;
  _fillCycleTables(cyc, eBodyId, sBodyId);
  _fillCycleThermal(cyc.thermal, thermPanelId, thermAvgId, thermPeakId, thermWarnId);
}

function renderThermal(th) {
  if (!th || th.error) {
    document.getElementById('thermal-img').alt =
      'Thermisches Modell nicht verfügbar' + (th && th.error ? ' (' + th.error + ')' : '');
    document.getElementById('losses-tbody').innerHTML = '';
    document.getElementById('tau-tbody').innerHTML    = '';
    return;
  }
  if (th.chart_b64) {
    document.getElementById('thermal-img').src = 'data:image/png;base64,' + th.chart_b64;
  }
  const L = th.losses || {};
  document.getElementById('losses-tbody').innerHTML = [
    ['P_Cu (Wicklung)',      L.P_Cu],
    ['P_Fe Stator',          L.P_Fe_stator],
    ['P_Fe Rotor',           L.P_Fe_rotor],
    ['P_Magnet (Eddy)',      L.P_Mag_eddy],
    ['P_Lager/Reibung',      L.P_Bearing],
    ['<b>P_Gesamt</b>',      '<b>' + (L.P_total||0).toFixed(0) + '</b>'],
  ].map(([k,v]) => `<tr><td>${k}</td><td>${typeof v==='number'?v.toFixed(1):v}</td></tr>`).join('');

  const tau = th.tau_s || {};
  document.getElementById('tau-tbody').innerHTML = [
    ['Wicklung', tau.winding],
    ['Stator',   tau.stator],
    ['Magnet',   tau.magnet],
    ['Gehäuse',  tau.housing],
  ].map(([k,v]) => `<tr><td>${k}</td><td>${v||'–'}</td></tr>`).join('');

  const wrap = document.getElementById('thermal-warnings');
  const warnings = th.warnings || [];
  if (warnings.length === 0) {
    wrap.innerHTML = '<div style="color:#4caf50">✓ Alle Temperaturen im unkritischen Bereich</div>';
  } else {
    wrap.innerHTML = warnings.map(w =>
      `<div style="color:${w.includes('Magnet')?'#e74c3c':'#f39c12'};padding:2px 0">${escHtml(w)}</div>`
    ).join('');
  }
}

function renderCadImages(imgs) {
  const crossEl = document.getElementById('cad-cross-img');
  const sideEl  = document.getElementById('cad-side-img');
  if (!imgs || (!imgs.cross_section && !imgs.side_view)) {
    crossEl.removeAttribute('src');
    sideEl.removeAttribute('src');
    crossEl.alt = 'Querschnitt nicht verfügbar';
    sideEl.alt  = 'Axialschnitt nicht verfügbar';
    return;
  }
  const ts = '?t=' + Date.now();
  if (imgs.cross_section) {
    crossEl.src = '/cad_image/motor_cross_section.png' + ts;
    crossEl.onerror = () => { crossEl.alt = '⚠ Querschnitt-Bild konnte nicht geladen werden'; };
  }
  if (imgs.side_view) {
    sideEl.src  = '/cad_image/motor_side_view.png' + ts;
    sideEl.onerror = () => { sideEl.alt = '⚠ Axialschnitt-Bild konnte nicht geladen werden'; };
  }
}

function renderAirgap(em) {
  if (!em || !em.airgap_chart_b64) return;
  document.getElementById('airgap-img').src = 'data:image/png;base64,' + em.airgap_chart_b64;
}

// Leistungskennfeld (results.power). Bewusst mit ausgeschriebenen Annahmen —
// die Kurve sieht genauer aus, als sie ist (ungesättigte Ld/Lq, feste
// Umrichtergrenzen, keine Verluste abgezogen).
function renderPower(pw) {
  const wrap = document.getElementById('power-wrap');
  if (!wrap) return;
  if (!pw || pw.error || !pw.chart_b64) {
    wrap.style.display = 'none';
    return;
  }
  wrap.style.display = '';
  document.getElementById('power-img').src = 'data:image/png;base64,' + pw.chart_b64;
  document.getElementById('power-metrics').innerHTML = [
    metric('Maximalleistung', pw.P_max_kW.toFixed(0) + ' kW',
           'bei ' + (+pw.P_max_rpm).toLocaleString() + ' U/min'),
    metric('Dauerleistung',   pw.P_cont_max_kW.toFixed(0) + ' kW',
           pw.cont_limited_by === 'kuehlung' ? 'kühlungsbegrenzt' : 'strombegrenzt (= Spitze)'),
    metric('Max. Drehmoment', pw.T_peak_max_Nm.toFixed(0) + ' Nm',
           'bis ' + (+pw.rpm_base).toLocaleString() + ' U/min (Eckdrehzahl)'),
    metric('Grenzdrehzahl',   (+pw.rpm_max).toLocaleString() + ' U/min', 'strukturell sicher, SF ≥ 1.5'),
  ].join('');
  const cont = (pw.cont_limited_by === 'kuehlung')
    ? `Die Dauerlinie ist durch die Kühlung begrenzt (M_dauer = ${pw.T_rated_Nm} Nm).`
    : `Dauer- und Spitzenlinie fallen zusammen: die Kühlung erlaubt mehr Moment `
      + `(${pw.T_rated_Nm} Nm) als der Umrichter bei ${pw.i_max_A} A liefert.`;
  document.getElementById('power-note').innerHTML =
    `Wellenleistung aus ψ_pm, L_d/L_q und den Umrichtergrenzen `
    + `<b>${pw.v_dc_V} V / ${pw.i_max_A} A</b> an den Klemmen`
    + ((pw.n_wdg && pw.n_wdg > 1)
       ? ` bei <b>${pw.n_wdg} Wdg/Nut</b> — gerechnet mit ${pw.v_dc_1t_V} V / ${pw.i_max_1t_A} A `
         + `auf 1 Wdg/Nut, der Bezugsgröße von K_t und ψ. `
       : ` (Ströme wie K_t auf <b>1 Wdg/Nut</b> bezogen). `)
    + cont + ` `
    + `<b>Grenzen der Aussage:</b> L_d/L_q sind ungesättigt (der FDM rechnet linear), `
    + `das echte Moment bei Volllast liegt darunter; Verluste sind nicht abgezogen `
    + `(Wellenleistung, nicht Umrichter-Eingang).`
    + (pw.limited_by_rpm
       ? ` ⚠ Die Leistung steigt bis zur Grenzdrehzahl weiter an — die <b>Festigkeit</b> begrenzt hier, nicht die Elektrik.`
       : '');
}

function renderEmCurve(em) {
  if (!em) return;
  if (em.em_sweep_chart_b64)
    document.getElementById('emcurve-img').src = 'data:image/png;base64,' + em.em_sweep_chart_b64;
  const tbody = document.getElementById('em-tbody');
  tbody.innerHTML = (em.speed_sweep || []).map(r =>
    `<tr><td>${r.rpm}</td><td>${r.emf_peak_V.toFixed(1)}</td>
         <td>${r.emf_rms_V.toFixed(1)}</td>
         <td>${r.Kt_Nm_per_A.toFixed(4)}</td>
         <td>${r.T_cogging_Nm.toFixed(3)} <span class="hint">gesch\u00e4tzt (Zhu/Howe) \u2014 Nutschlitz, Luftspalt, kgV und Schr\u00e4gung; nicht gemessen</span></td></tr>`
  ).join('');
}

function renderLoeservergleich(v) {
  // Zeigt CalculiX gegen Z88 auf DEMSELBEN Netz. Beschriftet ausdruecklich, was der
  // Vergleich prueft und was nicht — dieselbe Trennung wie ueberall sonst im Werkzeug:
  // eine Zahl bekommt gesagt, woher sie kommt.
  if (!v || !v.calculix || !v.z88) return '';
  const zeilen = [
    ['σ_v Spitze',            'stress_peak_MPa',      'MPa'],
    ['σ_v P99 (Torwert)',     'stress_p99_MPa',       'MPa'],
    ['Ringspannung Bohrung',  'bore_hoop_median_MPa', 'MPa'],
  ];
  let html = `<div style="margin-top:10px;border-top:1px solid #333;padding-top:8px">
    <div style="font-size:.8rem;color:#8ad;margin-bottom:6px">
      Zwei Löser, ein Netz</div>
    <table style="width:100%;font-size:.76rem;border-collapse:collapse">
    <tr style="color:#888"><th style="text-align:left">Größe</th>
      <th style="text-align:right">CalculiX</th><th style="text-align:right">Z88</th>
      <th style="text-align:right">Abw.</th></tr>`;
  for (const [name, schl, einheit] of zeilen) {
    const a = v.calculix[schl], b = v.z88[schl];
    if (a == null || b == null) continue;
    const abw = v['abweichung_' + schl + '_pct'];
    html += `<tr><td>${name}</td>
      <td style="text-align:right">${a.toFixed(2)} ${einheit}</td>
      <td style="text-align:right">${b.toFixed(2)} ${einheit}</td>
      <td style="text-align:right;color:${abw > 5 ? '#e74c3c' : '#7c7'}">
        ${abw != null ? abw.toFixed(2) + ' %' : '–'}</td></tr>`;
  }
  html += `</table><div style="font-size:.7rem;color:#666;margin-top:6px">
    ${v.hinweis || ''}</div></div>`;
  return html;
}

// ── 🧲 Mehrkörper (struct_solver = "kontakt") ──────────────────────────────
// Der einzige Weg, der etwas über den MAGNETEN sagt: dort ist er ein
// gerechneter Körper. Beurteilt wird er am ZUG und nicht an der
// Vergleichsspannung — ein gesinterter Magnet ist spröde.
function renderMehrkoerper(fem) {
  const wrap = document.getElementById('mk-wrap');
  if (!wrap) return;
  if (!fem || fem.rechensatz !== 'kontakt') { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  const img = document.getElementById('mk-img');
  if (img) { if (fem.bild) img.src = _deformImgUrl(fem.bild); else img.removeAttribute('src'); }

  const z = (k, v) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const a = fem.anlagen || {};
  const box = document.getElementById('mk-anlagen');
  if (box) {
    box.innerHTML =
      z('Rechensatz', `Mehrkörper ${fem.modell === 'eben' ? 'EBEN' : 'räumlich'}`
          + (fem.modell === 'eben'
             ? ` (${fem.ebener_zustand === 'spannung' ? 'ebene Spannung' : 'ebene Dehnung'}`
               + `${fem.elementgrad === 2 ? ', 2. Ordnung' : ''})`
             : '')
          + `, ${fem.n_magnetkoerper || 0} Magnetkörper`) +
      z('Kontaktpaare', `${fem.n_kontaktpaare || 0} über ${a.n_anlagen || 0} Anlageflächen`) +
      z('je Magnet', `${a.n_anlagen_je_magnet || 0} Anlagen, ${(+(a.flaeche_je_magnet_mm2 || 0)).toFixed(0)} mm²`) +
      `<div class="row"><span class="k"><b>tragender Anteil der Wand</b></span><span class="v"><b>${(+(a.anteil_an_der_wand_pct || 0)).toFixed(1)} %</b></span></div>` +
      z('Flankenanlagen', `${a.je_flanke || 0} je Flanke, ${(+(a.breite_mm || 0)).toFixed(1)} mm breit`) +
      z('Endanschlag', a.endanschlag
          ? `${(+(a.ende_mm || 0)).toFixed(1)} mm — nimmt ${(+(a.endanschlag_anteil_luftkappe_pct || 0)).toFixed(0)} % der Luftkappe ein`
          : 'keiner — in Längsrichtung hält nur Reibung') +
      z('Reibbeiwert', `${a.reibung} (Annahme)`) +
      z('Netz', `${(fem.netz_knoten || 0).toLocaleString('de-DE')} Knoten / `
          + `${(fem.netz_elemente || 0).toLocaleString('de-DE')} `
          + (fem.modell === 'eben' ? 'Dreiecke' : 'Tet4'));
  }

  const m = fem.magnet || {};
  const mb = document.getElementById('mk-magnet');
  if (mb) {
    if (!m.hauptzug_p99_MPa) { mb.innerHTML = '<div style="color:#9ab;font-size:.8rem">keine Magnetspannungen im Ergebnis</div>'; }
    else {
      const sf = m.sf_zug_p99;
      const warn = (sf != null && sf < 1.3) ? ' style="color:#ff6b6b"' : '';
      mb.innerHTML =
        z('Werkstoff', `${escHtml(m.werkstoff || '?')} (Beleg: ${escHtml(m.beleg || '?')})`) +
        z('größte Hauptzugspannung', `${(+m.hauptzug_max_MPa).toFixed(1)} MPa`) +
        `<div class="row"><span class="k"><b>P99 (maßgebend)</b></span><span class="v"${warn}><b>${(+m.hauptzug_p99_MPa).toFixed(1)} MPa</b></span></div>` +
        z('Zugfestigkeit', `${(+m.zug_grenze_MPa).toFixed(0)} MPa`) +
        `<div class="row"><span class="k">Sicherheit gegen Bruch</span><span class="v"${warn}>${sf == null ? '–' : (+sf).toFixed(2)}</span></div>` +
        z('von Mises (nachrichtlich)', `${(+m.von_mises_max_MPa).toFixed(1)} MPa`) +
        z('Druckfestigkeit', `${(+m.druck_grenze_MPa).toFixed(0)} MPa`) +
        `<div style="margin-top:7px;font-size:.72rem;color:#8a93a0;line-height:1.45">${escHtml(m.hinweis || '')}</div>`
        // Ein zu optimistischer Wert muss das AN SICH tragen, sonst liest er
        // sich wie ein Messwert (gemessen +53 % bei halbem Magnetnetz).
        + (m.aufloesung
           ? `<div style="margin-top:6px;font-size:.72rem;color:#e8b339;line-height:1.45">⚠ ${escHtml(m.aufloesung)}</div>`
           : '');
    }
  }

  const g = document.getElementById('mk-grenzen');
  if (g) {
    const liste = (fem.grenzen || []).map(t => `<li>${escHtml(t)}</li>`).join('');
    g.innerHTML = liste
      ? `<b>Was dieser Lauf nicht ist:</b><ul style="margin:5px 0 0 16px;padding:0">${liste}</ul>` : '';
  }
}

// ── 🧲 Magnetfliehkraft ────────────────────────────────────────────────────
// Die Last, die der Struktur-FEM gefehlt hat: vernetzt wird nur das
// Rotoreisen, die Magnettaschen sind darin Luft. Hier steht, was statt dessen
// aufgetragen wurde und was der Blechsteg davon sieht — samt dem, was die
// Rechnung NICHT ist (ema_magnetlast.grenzen).
function renderMagnetlast(ml, fem) {
  const wrap = document.getElementById('maglast-wrap');
  if (!wrap) return;
  if (!ml || !ml.n_magnete) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  // Im MEHRKÖRPER-Lauf wird diese Last NICHT aufgetragen — dort sind die
  // Magnete Körper und bringen ihre Fliehkraft selbst mit. Das Bild bleibt
  // richtig (es zeigt, wo die Kraft angreift), aber wer es ohne diesen Satz
  // liest, hält es für die Last, mit der gerechnet wurde.
  const mk = fem && fem.rechensatz === 'kontakt';
  const hin = document.getElementById('maglast-modus');
  if (hin) {
    hin.style.display = mk ? '' : 'none';
    if (mk) hin.innerHTML = `<div class="fem-box" style="border-left:3px solid #4fc3f7">
      <div style="color:#9ad;font-size:.8rem;line-height:1.5">ℹ Dieser Lauf rechnet
      <b>Mehrkörper</b>: die Magnete sind eigene Körper und bringen ihre Fliehkraft
      selbst mit. Die Kräfte unten zeigen also, <b>wo</b> sie angreift — aufgetragen
      als verschmierte Wandlast wurde sie <b>nicht</b> (das wäre die doppelte Last).
      Was das Blech davon sieht, steht oben unter 🧲 Mehrkörper.</div></div>`;
  }
  const img = document.getElementById('maglast-img');
  if (img && ml.bild) img.src = _deformImgUrl(ml.bild);

  const z = (k, v) => `<div class="row"><span class="k">${k}</span><span class="v">${v}</span></div>`;
  const box = document.getElementById('maglast-box');
  if (box) {
    box.innerHTML =
      z('Drehzahl', (+(ml.rpm || 0)).toLocaleString('de-DE') + ' U/min') +
      z('Magnete', `${ml.n_magnete} Stück, ${(+ml.magnet_kg).toFixed(3)} kg`) +
      z('Kraft je Magnet', (+ml.kraft_je_magnet_kN).toFixed(1) + ' kN') +
      z('Kraft je Pol', (+ml.kraft_je_pol_kN).toFixed(1) + ' kN') +
      z('Kraft gesamt', (+ml.kraft_gesamt_kN).toFixed(0) + ' kN') +
      z('Flächenlast max.', (+ml.druck_max_MPa).toFixed(1) + ' MPa') +
      z('belastete Wände', `${ml.n_waende} (${(ml.arten || []).join(' + ')})`);
  }

  const st = ml.steg || {};
  const sbox = document.getElementById('maglast-steg');
  if (sbox) {
    if (!st.steg_traegt) {
      sbox.innerHTML = `<div style="color:#9ab;font-size:.8rem;line-height:1.5">
        ${escHtml(st.grund || 'Der Blechsteg trägt die Magnete hier nicht.')}</div>`;
    } else if (st.sigma_steg_MPa == null) {
      sbox.innerHTML = `<div style="color:#e0c090;font-size:.8rem;line-height:1.5">
        ⚠ ${escHtml(st.grund || 'Stegspannung nicht bestimmbar.')}</div>`;
    } else {
      const sf = st.sf_ueberlagert;
      const warn = (sf != null && sf < (st.sf_ziel || 1.3)) ? ' style="color:#ff6b6b"' : '';
      sbox.innerHTML =
        `<div class="row"><span class="k"><b>Steg-Richtwert</b></span><span class="v"></span></div>` +
        z('Randsteg (gemessen)', (+st.s_rand_mm).toFixed(2) + ' mm') +
        z('tragender Querschnitt', `${st.n_stege_je_pol} × ${(+st.s_rand_mm).toFixed(2)} mm → ${(+st.flaeche_steg_mm2).toFixed(0)} mm²`) +
        z('σ aus Magnetlast', (+st.sigma_steg_MPa).toFixed(0) + ' MPa') +
        z('σ Ringspannung', (st.sigma_ring_MPa == null ? '–' : (+st.sigma_ring_MPa).toFixed(0) + ' MPa')) +
        `<div class="row"><span class="k"><b>σ überlagert</b></span><span class="v"${warn}><b>${st.sigma_ueberlagert_MPa == null ? '–' : (+st.sigma_ueberlagert_MPa).toFixed(0) + ' MPa'}</b></span></div>` +
        `<div class="row"><span class="k">Sicherheit (Ziel ≥ ${st.sf_ziel})</span><span class="v"${warn}>${sf == null ? '–' : (+sf).toFixed(2)}</span></div>` +
        `<div style="margin-top:7px;font-size:.72rem;color:#8a93a0;line-height:1.45">${escHtml(st.annahme || '')}</div>`;
    }
  }

  const g = document.getElementById('maglast-grenzen');
  if (g) {
    const liste = (ml.grenzen || []).map(t => `<li>${escHtml(t)}</li>`).join('');
    g.innerHTML = liste
      ? `<b>Was diese Last nicht ist:</b><ul style="margin:5px 0 0 16px;padding:0">${liste}</ul>`
      : '';
  }
}

function renderStress(fem, sweep, chartB64) {
  if (chartB64)
    document.getElementById('stress-img').src = 'data:image/png;base64,' + chartB64;

  // FEM single-RPM box
  const box = document.getElementById('fem-box');
  if (fem && fem.max_von_mises_MPa) {
    const sf   = fem.safety_factor;
    const cls  = sf >= 2 ? 'sf-ok' : sf >= 1 ? 'sf-warn' : 'sf-bad';
    box.innerHTML = [
      row('Status', fem.solver_status || 'OK'),
      row('Drehzahl', fem.rpm + ' U/min'),
      row('σ_v,max', fem.max_von_mises_MPa + ' MPa'),
      row('Sicherheitsfaktor', `<span class="${cls}">${sf}</span>`),
      row('u_max', fem.max_displacement_mm + ' mm'),
      row('Knoten', fem.node_count || '–'),
      row('Material', fem.material || '–'),
      row('Streckgrenze', fem.yield_mpa + ' MPa'),
    ].join('');
    if (fem.rechensatz === 'eigen')
      box.innerHTML += row('Rechensatz',
        `eigener Satz (${fem.solver_verwendet || '?'}, ` +
        `${fem.netz_sektor ? 'Polsektor' : 'Vollrotor'}, ` +
        `${(fem.netz_elemente || 0).toLocaleString('de-DE')} Tets)`);
    box.innerHTML += renderLoeservergleich(fem.loeservergleich);
  } else {
    box.innerHTML = `<div class="row"><span class="k">Status</span>
      <span class="v sf-warn">⚠ Nicht verfügbar</span></div>
      <div style="font-size:.78rem;color:#666;padding:6px 0">
      CalculiX fehlgeschlagen. Analytische Näherung in Kennlinie.</div>`;
  }

  // Analytical sweep table
  const tbody = document.getElementById('struct-tbody');
  tbody.innerHTML = (sweep || []).map(r => {
    const cls = r.safety_factor >= 2 ? 'sf-ok' : r.safety_factor >= 1 ? 'sf-warn' : 'sf-bad';
    return `<tr><td>${r.rpm}</td><td>${r.sigma_max_MPa}</td>
             <td class="${cls}">${r.safety_factor}</td></tr>`;
  }).join('');
}

/* ⊙ **Was die Scheibe traegt — und was daran nicht gerechnet ist.**
 *
 * Gezeigt wird, was `ema_axial.anzug`/`ruecken`/`bandage` geliefert haben.
 * Gerechnet wird hier NICHTS: jede Zahl kommt aus `results.axial_struktur`,
 * und die beiden Urteile (`t_reicht`, `klebung_haelt`) faellt die Python-Seite.
 * Ein zweites Urteil im Browser waere die Stelle, an der Oberflaeche und
 * Rechnung auseinanderlaufen — und zwar bei einer Festigkeitsaussage.
 *
 * Die offenen Punkte stehen MIT im Bild und nicht in einer Fussnote: dass
 * keine FEM lief, ist bei der Scheibe die Bauart und kein Mangel, dass die
 * Fliehkraftspannung des Blechs fehlt, aber sehr wohl eine Luecke.
 */
function renderAxialStruktur(st, chartB64) {
  const wrap = document.getElementById('axstr-wrap');
  const rad  = document.getElementById('radstr-wrap');
  if (!wrap) return;
  if (!st) { wrap.style.display = 'none'; if (rad) rad.style.display = ''; return; }
  wrap.style.display = '';
  if (rad) rad.style.display = 'none';      // seine Tabellen sind hier leer
  if (chartB64)
    document.getElementById('axstr-img').src = 'data:image/png;base64,' + chartB64;

  const rk = st.ruecken || {}, az = st.anzug || {}, bd = st.bandage || {};
  const mm = v => (v == null ? '–' : (v * 1000).toFixed(2) + ' mm');
  const um = v => (v == null ? '–' : (v * 1e6).toFixed(1) + ' µm');

  document.getElementById('axstr-note').innerHTML =
    '<b>Keine Struktur-FEM, und das ist die Bauart.</b> Sie vernetzt den '
    + 'Zylinder-Rotor und lädt ihn mit Fliehkraft; die Scheibe trägt zwei '
    + 'andere Lasten. Die <b>Hauptlast ist der axiale Anzug</b> — gemessen '
    + '8,6 : 1 zum momentbildenden Schub —, gerechnet als '
    + 'achssymmetrische <b>Kreisringplatte</b> (innen an der Nabe eingespannt, '
    + 'außen frei). Die zweite zieht die Magnete <b>in der Scheibenebene</b> '
    + 'nach außen, wo kein Blechsteg steht.';

  const ok = (b) => b ? '<span class="sf-ok">✓</span>'
                      : '<span class="sf-bad">⚠</span>';
  const zeilen = [
    row('Bindend', rk.bindet || '–'),
    row('magnetisch nötig', mm(rk.t_magnetisch_m)),
    row('aus der Durchbiegung', mm(rk.t_steifigkeit_m)),
    row('→ Soll', mm(rk.t_soll_m)),
  ];
  if (st.t_ist_m != null)
    zeilen.push(row('gezeichnet',
      mm(st.t_ist_m) + ' ' + ok(st.t_reicht)));
  zeilen.push(row('Durchbiegung w_max',
    um(st.w_bei_t_ist_m != null ? st.w_bei_t_ist_m : rk.w_bei_t_soll_m)));
  const anteil = st.w_anteil_spalt_ist != null ? st.w_anteil_spalt_ist
                                               : rk.w_anteil_spalt;
  if (anteil != null)
    zeilen.push(row('… als Anteil des Luftspalts',
      (anteil * 100).toFixed(1) + ' % ' + ok(anteil <= 0.10)
      + ' <span style="color:#777">(zulässig 10 %)</span>'));
  zeilen.push(row('Einspannung (Nabe)', mm(rk.nabe_r_m) + ' Radius'));
  zeilen.push(row('axialer Anzug',
    az.sigma_n_pa ? (az.sigma_n_pa / 1e3).toFixed(1) + ' kPa' : '–'));
  zeilen.push(row('… Kraft je Luftspalt',
    az.kraft_je_spalt_N ? (az.kraft_je_spalt_N / 1e3).toFixed(2) + ' kN' : '–'));
  if (az.hebt_sich_auf)
    zeilen.push(row('negative Steifigkeit',
      (az.negative_steifigkeit_N_per_m / 1e6).toFixed(1) + ' MN/m'
      + ' <span style="color:#777">(zwei Spalte heben sich nur bei mittigem '
      + 'Ständer auf)</span>'));
  document.getElementById('axstr-box').innerHTML = zeilen.join('');

  const mz = [
    row('Drehzahl', (st.rpm ?? '–') + ' 1/min'),
    row('Umfangsgeschwindigkeit',
      bd.u_aussen_m_s ? bd.u_aussen_m_s.toFixed(1) + ' m/s' : '–'),
    row('Magnetmasse je Scheibe',
      bd.magnetmasse_je_scheibe_kg != null
        ? bd.magnetmasse_je_scheibe_kg.toFixed(3) + ' kg' : '–'),
    row('Fliehkraft in der Ebene',
      bd.kraft_gesamt_N ? (bd.kraft_gesamt_N / 1e3).toFixed(1) + ' kN' : '–'),
    row('… je Pol',
      bd.kraft_je_pol_N ? (bd.kraft_je_pol_N / 1e3).toFixed(2) + ' kN' : '–'),
    row('Klebescherspannung',
      bd.klebescherspannung_pa
        ? (bd.klebescherspannung_pa / 1e6).toFixed(2) + ' MPa' : '–'),
  ];
  if (bd.klebung_haelt != null)
    mz.push(row('Klebung hält',
      ok(bd.klebung_haelt) + ' <span style="color:#777">(gegen '
      + bd.klebe_zul_mpa + ' MPa zulässig)</span>'));
  else
    mz.push(row('Klebung hält',
      '<span class="sf-warn">kein Urteil</span> <span style="color:#777">— '
      + 'zulässige Scherspannung in ③ Betrieb eintragen</span>'));
  if (bd.t_bandage_m != null)
    mz.push(row('Bandage nötig', mm(bd.t_bandage_m)
      + ' <span style="color:#777">(bei ' + bd.sigma_zul_mpa + ' MPa)</span>'));
  else
    mz.push(row('Bandage',
      '<span style="color:#777">keine Dicke genannt — kein '
      + 'Bandagenwerkstoff in den Tabellen</span>'));
  document.getElementById('axstr-mag').innerHTML = mz.join('');

  const offen = (st.ungeprueft || []).concat(
    st.max_safe_rpm_grund ? ['max. sichere Drehzahl: ' + st.max_safe_rpm_grund] : []);
  document.getElementById('axstr-offen').innerHTML = offen.length
    ? '<b>Nicht gerechnet:</b><ul style="margin:4px 0 0 16px;padding:0">'
      + offen.map(x => '<li>' + escHtml(x) + '</li>').join('') + '</ul>'
    : '';
}

function renderConnection(c) {
  const wrap = document.getElementById('conn-wrap');
  if (!wrap) return;
  if (!c) { wrap.style.display = 'none'; return; }
  wrap.style.display = '';
  if (c.chart_b64) document.getElementById('conn-img').src = 'data:image/png;base64,' + c.chart_b64;
  const ucls = (c.utilization != null && c.utilization <= 1) ? 'sf-ok' : 'sf-bad';
  const rows = [
    row('Typ', c.note || c.type),
    row('Nennmoment', (c.T_rated_Nm ?? '–') + ' Nm'),
    row('Drehmomentkapazität', (c.T_capacity_Nm ?? '–') + ' Nm'),
    row('Auslastung', `<span class="${ucls}">${c.utilization ?? '–'}</span>`),
  ];
  if (c.type === 'press') {
    rows.push(row('Übermaß', (c.interference_um ?? '–') + ' µm'));
    rows.push(row('Fugendruck', (c.p_MPa ?? '–') + ' MPa'));
    const lcls = (c.loosening_rpm && c.loosening_rpm >= (c._rpm_max || 0)) ? 'sf-ok' : 'sf-warn';
    rows.push(row('Lösedrehzahl', `<span class="${lcls}">${(c.loosening_rpm ?? '–')} U/min</span>`));
  } else {
    rows.push(row('Flächenpressung', (c.p_MPa ?? '–') + ' MPa'));
    rows.push(row('zul. Pressung', (c.p_allow_MPa ?? '–') + ' MPa'));
  }
  rows.push(row('Bewertung', c.ok ? '<span class="sf-ok">in Ordnung</span>'
                                  : '<span class="sf-bad">⚠ kritisch</span>'));
  document.getElementById('conn-box').innerHTML = rows.join('');
}

function renderManual(m) {
  if (!m) return;
  const panel = document.getElementById('manual-panel');
  panel.style.display = 'block';
  document.getElementById('manual-cmd').textContent = m.open_cmd || '';
}

function row(k, v) {
  return `<div class="row"><span class="k">${escHtml(k)}</span><span class="v">${v}</span></div>`;
}

async function openFreeCAD() {
  try {
    const r = await fetch('/open_freecad');
    const d = await r.json();
    if (d.error) alert(d.error);
  } catch(e) { alert('Verbindung zum Server fehlgeschlagen.'); }
}

function copyCmd() {
  const cmd = document.getElementById('manual-cmd').textContent;
  navigator.clipboard.writeText(cmd).catch(() => {});
}

function addLog(msg) {
  const el = document.getElementById('progress-log');
  el.innerHTML += `<p>${escHtml(msg)}</p>`;
  el.scrollTop = el.scrollHeight;
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}
