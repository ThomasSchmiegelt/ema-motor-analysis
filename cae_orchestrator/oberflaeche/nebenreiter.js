// Zwei Reiter, die nur ZUSEHEN: 🧠 KI-Training und ⏳ Jobs.
//
// Beide rechnen nichts und schreiben nichts an der Auslegung -- der eine
// liest die Trainingsverlaeufe des Surrogats (GET /ki_training/*), der
// andere den Stand der Server-Warteschlange. Zusammen, weil sie dasselbe
// Muster haben (pollen, anzeigen, sonst nichts).
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── 🧠 KI-Training-Tab: Trainingsverläufe des Physik-Surrogats ────────────────
// Reiner Betrachter (GET /ki_training/*). Ausgewählte Läufe werden serverseitig zu
// EINEM Vergleichs-Chart gerendert (matplotlib, wie überall sonst im Programm) —
// deshalb hält der Client nur die Auswahl.
let _kiRuns = [], _kiSel = new Set();

// ── 📚 Lernprogramm (Erfahrungsdatenbank) ── Start, Fortschritt, Berichte ──
let _lpTimer = null;

async function lpStart() {
  const msg = document.getElementById('lp_msg');
  const body = {minuten: +document.getElementById('lp_minuten').value,
                auswertung: +document.getElementById('lp_auswertung').value,
                kombinieren: document.getElementById('lp_kombi').checked,
                qwen: document.getElementById('lp_qwen').checked};
  const r = await fetch('/lernprogramm', {method: 'POST', headers: {'Content-Type': 'application/json'},
                                          body: JSON.stringify(body)});
  const d = await r.json().catch(() => ({}));
  if (!r.ok) { msg.textContent = d.error || ('Fehler ' + r.status); return; }
  msg.textContent = 'läuft …';
  lpPoll();
}

async function lpAbbrechen() {
  await fetch('/lernprogramm/abbrechen', {method: 'POST'});
  document.getElementById('lp_msg').textContent = 'Abbruch angefordert — der Bericht wird trotzdem geschrieben.';
}

async function lpPoll() {
  clearTimeout(_lpTimer);
  let d;
  try { d = await fetch('/lernprogramm/status').then(r => r.json()); } catch (e) { return; }
  const log = document.getElementById('lp_log'), msg = document.getElementById('lp_msg');
  if (d.log && d.log.length) { log.style.display = ''; log.textContent = d.log.join('\n'); log.scrollTop = log.scrollHeight; }
  document.getElementById('lp_start').disabled = d.status === 'running';
  if (d.status === 'running') {
    const f = d.fortschritt || {};
    msg.textContent = `läuft · ${f.gueltig || 0} Entwürfe, ${f.mit_symptom || 0} mit Symptom · ${Math.round(d.sekunden || 0)} s`;
    _lpTimer = setTimeout(lpPoll, 3000);
  } else if (d.status === 'done' && d.ergebnis) {
    const e = d.ergebnis;
    msg.textContent = `fertig (${e.ende}) · ${e.gueltig} Entwürfe` +
      (e.deutungszeit_min != null ? ` · Deutungszeit ${e.deutungszeit_min} min` : '') +
      (e.deutung ? ' · qwen hat gedeutet' : '');
    await lpLaeufe(e.marke);
  } else if (d.status === 'error') {
    msg.textContent = 'Fehler: ' + (d.fehler || '');
  }
}

async function lpLaeufe(waehle) {
  const sel = document.getElementById('lp_laeufe');
  const d = await fetch('/lernprogramm/laeufe').then(r => r.json()).catch(() => ({laeufe: []}));
  sel.innerHTML = (d.laeufe || []).map(l =>
    `<option value="${escHtml(l.marke)}">${escHtml(l.marke)} · ${l.gueltig} Entwürfe · ${escHtml(l.ende)}</option>`).join('');
  if (waehle) sel.value = waehle;
  if (sel.value) lpBericht();
}

async function lpBericht() {
  const m = document.getElementById('lp_laeufe').value, box = document.getElementById('lp_bericht');
  if (!m) return;
  const d = await fetch('/lernprogramm/bericht/' + encodeURIComponent(m)).then(r => r.json()).catch(() => ({}));
  box.style.display = '';
  box.textContent = d.text || d.error || '';
}

async function kiActivate() {
  lpLaeufe(); lpPoll();
  const box = document.getElementById('ki-runs');
  try {
    const d = await fetch('/ki_training/runs').then(r => r.json());
    kiRenderService(d.service, d.available, d.dir);
    if (!d.available) {
      box.innerHTML = `<div style="color:#c88;font-size:.8rem">Kein Trainings-Unterprojekt gefunden
        (<code>${escHtml(d.dir || '')}</code>). Der Tab bleibt leer — das ist kein Fehler.</div>`;
      document.getElementById('ki-chart').style.display = 'none';
      return;
    }
    _kiRuns = d.runs || [];
    // Vorauswahl: die vier zuletzt angefassten Läufe (mehr wird im Chart unleserlich)
    if (!_kiSel.size) _kiRuns.slice(0, 4).forEach(r => _kiSel.add(r.name));
    kiRenderRuns();
    const sel = document.getElementById('ki_log_run');
    const cur = sel.value;
    sel.innerHTML = _kiRuns.map(r => `<option value="${escHtml(r.name)}">${escHtml(r.name)}</option>`).join('');
    if (cur && _kiRuns.some(r => r.name === cur)) sel.value = cur;
    kiLoadLog();
    kiRefreshChart();
  } catch (e) {
    box.innerHTML = `<div style="color:#c88;font-size:.8rem">Server nicht erreichbar: ${escHtml(e.message)}</div>`;
  }
}

function kiRenderService(svc, available, dir) {
  const el = document.getElementById('ki-service');
  if (!el) return;
  const up  = svc && svc.up;
  const h   = (svc && svc.health) || {};
  const col = up ? '#27ae60' : '#e67e22';
  // Der zweite Satz beantwortet die eigentliche Frage: ist die KI im Programm nutzbar?
  const note = up
    ? 'Der Dienst läuft. Ein Modell wird ausgeliefert, sobald ein Lauf die Abnahme besteht.'
    : 'Der Dienst läuft nicht — das Programm rechnet dann wie immer mit dem exakten '
      + 'FDM-Löser. Start: <code>cd physics_surrogate &amp;&amp; ./start.sh</code>';
  el.innerHTML = `<div class="fem-box" style="border-left:3px solid ${col}">
    <div class="row"><span class="k">Surrogat-Dienst (:5300)</span>
      <span class="v" style="color:${col}">${up ? 'erreichbar' : 'aus'}</span></div>
    ${up ? `<div class="row"><span class="k">Gerät</span><span class="v">${escHtml(String(h.device || '–'))}</span></div>
            <div class="row"><span class="k">Modell Stufe 1 (2D-FDM)</span><span class="v">${
              ((h.models || {}).fdm || {}).available
                ? escHtml(String(h.models.fdm.checkpoint)) : 'kein Checkpoint'}</span></div>` : ''}
    <div style="font-size:.75rem;color:#9ab;margin-top:6px;line-height:1.5">${note}</div>
  </div>`;
}

function kiRenderRuns() {
  const box = document.getElementById('ki-runs');
  if (!_kiRuns.length) { box.innerHTML = '<div style="color:#777;font-size:.8rem">Noch keine Trainingsläufe.</div>'; return; }
  const num = (v, d) => (v == null ? '–' : (+v).toFixed(d));
  box.innerHTML = `<table class="data-table" style="width:100%">
    <thead><tr>
      <th style="width:34px"></th><th>Lauf</th><th>Zustand</th><th>Epochen</th>
      <th>rel. L2 (A)</th><th>RMSE Br/Peak</th><th>bestes Tor</th><th>Tiefe</th><th>Std.</th><th>zuletzt</th>
    </tr></thead><tbody>
    ${_kiRuns.map(r => {
      const st = r.active ? '<span style="color:#2980b9">läuft</span>'
               : r.paused ? '<span style="color:#e67e22">pausiert</span>'
               : '<span style="color:#7f8c8d">gestoppt</span>';
      const gate = r.best_gate
        ? `<span style="color:${r.gate_passed ? '#27ae60' : '#e0a060'}">${num(r.best_gate.value, 4)}</span>`
          + `<span style="color:#666"> (E${r.best_gate.epoch})</span>`
        : '–';
      return `<tr>
        <td><input type="checkbox" ${_kiSel.has(r.name) ? 'checked' : ''}
             onchange="kiToggle('${escHtml(r.name)}', this.checked)"/></td>
        <td><b>${escHtml(r.name)}</b></td>
        <td>${st}</td>
        <td>${r.epochs}</td>
        <td>${num(r.last.val_rel_l2_A, 4)}</td>
        <td>${num(r.last.val_rmse_Br_rel_peak, 4)}</td>
        <td>${gate}</td>
        <td>${r.model.model_depth || '–'}</td>
        <td>${num(r.hours, 1)}</td>
        <td style="color:#777">${escHtml(r.modified)}</td>
      </tr>`;
    }).join('')}
    </tbody></table>
    <div style="font-size:.74rem;color:#666;margin-top:6px">
      Abnahme-Tor ist <b>RMSE Br/Peak &lt; 0,03</b> — der Fehler auf der Luftspaltkurve,
      aus der das Moment kommt. <code>rel. L2 (A)</code> ist die schwächere Größe
      (98 % der Feldenergie von A liegen im Rotor).
    </div>`;
}

function kiToggle(name, on) {
  if (on) _kiSel.add(name); else _kiSel.delete(name);
  kiRefreshChart();
}

async function kiRefreshChart() {
  const img = document.getElementById('ki-chart');
  const msg = document.getElementById('ki_chart_msg');
  if (!_kiSel.size) { img.style.display = 'none'; msg.textContent = 'kein Lauf ausgewählt'; return; }
  msg.textContent = 'zeichne …';
  const q = new URLSearchParams({ runs: [..._kiSel].join(','),
                                  x: document.getElementById('ki_xaxis').value });
  try {
    const d = await fetch('/ki_training/chart?' + q).then(r => r.json());
    if (d.error) { msg.textContent = '❌ ' + d.error; return; }
    img.src = 'data:image/png;base64,' + d.chart_b64;
    img.style.display = '';
    msg.textContent = '';
  } catch (e) { msg.textContent = '❌ ' + e.message; }
}

async function kiLoadLog() {
  const name = document.getElementById('ki_log_run').value;
  const pre  = document.getElementById('ki-log');
  if (!name) { pre.textContent = ''; return; }
  try {
    const d = await fetch('/ki_training/log/' + encodeURIComponent(name)).then(r => r.json());
    pre.textContent = d.log || '(kein train.log)';
  } catch (e) { pre.textContent = '❌ ' + e.message; }
}

// ── ⏳ Jobs-Tab: Server-Warteschlange (persistent, browser-unabhängig) ──────────
// Jobs werden über POST /jobs/add eingereiht und vom Server sequenziell abgearbeitet;
// dieser Tab zeigt/steuert nur den Server-Stand (Poll alle 3 s solange offen).
let _jobsTimer = null, _jobsPaused = false;
const _JOB_ICON = { analyse: '⚙', em3d: '🧲', em3d_sweep: '🌡', oilspray: '💧',
                    param_study: '📈', optimize: '🎯', cfd: '🌊' };
const _JOB_CHIP = { 'wartet': '#7f8c8d', 'läuft': '#2980b9', 'fertig': '#27ae60',
                    'fehler': '#c0392b', 'abgebrochen': '#e67e22' };

function jobsActivate() {
  jobsRefresh();
  if (_jobsTimer) clearInterval(_jobsTimer);
  _jobsTimer = setInterval(() => {
    if (window._activeTab === 'jobs') jobsRefresh();
    else { clearInterval(_jobsTimer); _jobsTimer = null; }
  }, 3000);
}

function _jobsBadge(n) {
  const b = document.getElementById('jobs-badge');
  if (!b) return;
  if (n > 0) { b.textContent = n; b.style.display = 'inline-block'; }
  else b.style.display = 'none';
}

function _jobsFmtT(t) {
  if (!t) return '';
  const d = new Date(t * 1000);
  return d.toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' }) + ' ' +
         d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit' });
}

async function jobsRefresh() {
  let j;
  try { j = await fetch('/jobs').then(r => r.json()); } catch (e) { return; }
  _jobsPaused = !!j.paused;
  const halt = document.getElementById('jobs_halt');
  if (halt) {
    halt.style.display = j.halt ? 'block' : 'none';
    const g = document.getElementById('jobs_halt_grund');
    if (g) g.textContent = j.halt_grund || '';
  }
  const pb = document.getElementById('jobs_pause_btn');
  if (pb) {
    pb.textContent = _jobsPaused ? '▶ Fortsetzen' : '⏸ Pausieren';
    pb.style.background = _jobsPaused ? '#27ae60' : '#555';
  }
  const jobs = j.jobs || [];
  const open = jobs.filter(x => x.status === 'wartet' || x.status === 'läuft');
  _jobsBadge(open.length);
  const hint = document.getElementById('jobs_hint');
  if (hint) hint.textContent = _jobsPaused
    ? '⏸ pausiert — der laufende Job läuft zu Ende, danach wartet die Schlange'
    : (open.length ? `${open.length} offen` : '');
  const list = document.getElementById('jobs_list');
  if (!list) return;
  if (!jobs.length) {
    list.innerHTML = '<div style="color:#777;padding:14px 0">Keine Jobs in der Warteschlange. ' +
      'Mit den „➕ Warteschlange"-Knöpfen in den Berechnungs-Tabs einreihen.</div>';
    return;
  }
  list.innerHTML = jobs.map(x => {
    const chip = `<span style="background:${_JOB_CHIP[x.status] || '#555'};color:#fff;border-radius:3px;` +
                 `padding:1px 7px;font-size:.7rem;white-space:nowrap">${escHtml(x.status)}</span>`;
    const prog = (x.status === 'läuft')
      ? `<div style="margin-top:4px"><div style="background:#222;border-radius:3px;height:7px;overflow:hidden">` +
        `<div style="background:#2980b9;height:100%;width:${x.progress || 0}%"></div></div>` +
        `<div style="font-size:.68rem;color:#89a;margin-top:2px">${escHtml((x.log_line || '').slice(0, 140))}</div></div>`
      : '';
    const err = x.error ? `<div style="font-size:.7rem;color:#e57;margin-top:3px">⚠ ${escHtml(String(x.error).slice(0, 200))}</div>` : '';
    // „Ergebnis öffnen"-Knopf je Job-Typ: em3d → 3D-Feld-Tab (lädt den gespeicherten Lauf),
    // oilspray → 💧-Tab, sonst die Analyse-Projektansicht. em3d-Jobs werden serverseitig
    // automatisch gespeichert (auch bei Teilabbruch), daher auch bei „abgebrochen" anbieten.
    const isE3 = (x.type === 'em3d' || x.type === 'em3d_sweep');
    const bs = 'background:#345;width:auto;padding:3px 9px;font-size:.7rem';
    let proj = '';
    // Param-Studie/Optimierung sind nicht projektgebunden → Ergebnis liegt im Server-State,
    // der „Ansehen"-Knopf öffnet den passenden Tab und rendert den letzten Lauf.
    if (x.status === 'fertig' && x.type === 'param_study')
      proj = `<button onclick="openJobStudy()" style="${bs}">📈 Ansehen</button>`;
    else if (x.status === 'fertig' && x.type === 'optimize')
      proj = `<button onclick="openJobOptimize()" style="${bs}">🎯 Ansehen</button>`;
    else if (x.status === 'fertig' && x.type === 'cfd')
      proj = `<button onclick="openJobCfd('${escHtml(x.project_id || '')}')" style="${bs}">🌊 Ansehen</button>`;
    else if (x.project_id && (x.status === 'fertig' || (isE3 && x.status === 'abgebrochen'))) {
      if (isE3)
        proj = `<button onclick="openJobEm3d('${escHtml(x.project_id)}')" style="${bs}">🧲 3D-Feld</button>`;
      else if (x.type === 'oilspray')
        proj = `<button onclick="openJobOil('${escHtml(x.project_id)}')" style="${bs}">💧 Spritzöl</button>`;
      else
        proj = `<button onclick="loadProjectById('${escHtml(x.project_id)}')" style="${bs}">📂 Ergebnis</button>`;
    }
    const cancel = (x.status === 'wartet' || x.status === 'läuft')
      ? `<button onclick="jobsCancel('${x.id}')" title="abbrechen" ` +
        `style="background:#733;width:auto;padding:3px 9px;font-size:.7rem">✖</button>` : '';
    // Umsortieren ist die dritte Antwort neben „weiter" und „weg": erst das hier.
    const vor = (x.status === 'wartet')
      ? `<button onclick="jobsVorziehen('${x.id}')" title="an den Anfang der Warteschlange" ` +
        `style="background:#456;width:auto;padding:3px 9px;font-size:.7rem">⬆ Zuerst</button>` : '';
    // Ein vom Neustart unterbrochener Lauf hat KEINEN Zwischenstand — er finge von
    // vorn an. Darum nur auf Zuruf, nie von selbst.
    const wdh = (x.status === 'abgebrochen')
      ? `<button onclick="jobsWiederholen('${x.id}')" title="erneut einreihen (faengt von vorn an)" ` +
        `style="background:#456;width:auto;padding:3px 9px;font-size:.7rem">↻ Nochmal</button>` : '';
    return `<div style="display:flex;gap:10px;align-items:flex-start;border:1px solid #2a2f38;` +
           `border-radius:6px;padding:8px 10px;margin-bottom:6px;background:#161a20">` +
           `<div style="font-size:1.1rem">${_JOB_ICON[x.type] || '⚙'}</div>` +
           `<div style="flex:1;min-width:0"><div style="color:#dde;font-size:.82rem">${escHtml(x.title || x.type)}` +
           ` <span style="color:#667;font-size:.68rem;margin-left:6px">${escHtml(x.type)} · ${_jobsFmtT(x.created)}</span></div>` +
           prog + err + `</div>${chip}${proj}${vor}${wdh}${cancel}</div>`;
  }).join('');
}

async function jobsEntscheiden(was) {
  if (was === 'verwerfen' &&
      !confirm('Alle WARTENDEN Aufträge verwerfen? Laufende und fertige bleiben.')) return;
  try {
    await fetch('/jobs/entscheiden', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ was }) });
  } catch (e) {}
  jobsRefresh();
}

async function jobsVorziehen(id) {
  try { await fetch('/jobs/' + id + '/vorziehen', { method: 'POST' }); } catch (e) {}
  jobsRefresh();
}

async function jobsWiederholen(id) {
  try { await fetch('/jobs/' + id + '/wiederholen', { method: 'POST' }); } catch (e) {}
  jobsRefresh();
}

async function jobsTogglePause() {
  try {
    await fetch('/jobs/config', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                  body: JSON.stringify({ paused: !_jobsPaused }) });
  } catch (e) {}
  jobsRefresh();
}

async function jobsClearDone() {
  try { await fetch('/jobs/clear_done', { method: 'POST' }); } catch (e) {}
  jobsRefresh();
}

async function jobsCancel(jid) {
  try {
    const r = await fetch('/jobs/' + encodeURIComponent(jid) + '/cancel', { method: 'POST' });
    if (!r.ok) { const e = await r.json().catch(() => ({})); alert('⚠ ' + (e.error || 'Abbruch nicht möglich')); }
  } catch (e) {}
  jobsRefresh();
}

// Ergebnis eines als Job gelaufenen 3D-Feld-Laufs öffnen: aktives Projekt setzen (die
// gespeicherten 3D-Läufe sind projektgebunden), in den 3D-Feld-Tab wechseln und den zuletzt
// gespeicherten Lauf (= dieser Job, Auto-Speichern serverseitig) laden.
async function openJobEm3d(pid) {
  try {
    if (pid) {
      await fetch('/project/' + encodeURIComponent(pid) + '/activate', { method: 'POST' }).catch(() => {});
      window._activeProject = { id: pid, name: (window._activeProject && _activeProject.id === pid && _activeProject.name) || pid };
    }
    switchTab('em3d');
    if (typeof _e3RefreshSavedCards === 'function') await _e3RefreshSavedCards();
    if (typeof _e3RefreshSavedList === 'function') _e3RefreshSavedList();
    // Neuesten gespeicherten Lauf (= dieser Job, Auto-Speichern) direkt in den Viewer laden.
    const list = await fetch('/em3d/saved').then(x => x.json());
    if (Array.isArray(list) && list.length)
      await _e3LoadRunById(list[0].id, document.getElementById('e3_msg'), true);
    else alert('Kein gespeicherter 3D-Lauf für dieses Projekt gefunden.');
  } catch (e) { alert('⚠ ' + e.message); }
}

// Ergebnis eines CFD-Jobs öffnen: 🌊-Tab + zuletzt gerechnetes Ergebnis (liegt im Server-State).
async function openJobCfd(pid) {
  try {
    if (pid) {
      await fetch('/project/' + encodeURIComponent(pid) + '/activate', { method: 'POST' }).catch(() => {});
      window._activeProject = { id: pid, name: (window._activeProject && _activeProject.id === pid && _activeProject.name) || pid };
    }
    switchTab('cfd');
    const s = await fetch('/cfd/status').then(x => x.json());
    if (s.result) _renderCfd(s.result);
  } catch (e) { alert('⚠ ' + e.message); }
}

// Ergebnis eines Spritzöl-Jobs öffnen: aktives Projekt setzen + 💧-Tab (lädt automatisch den
// zuletzt gespeicherten Lauf beim Öffnen).
async function openJobOil(pid) {
  try {
    if (pid) {
      await fetch('/project/' + encodeURIComponent(pid) + '/activate', { method: 'POST' }).catch(() => {});
      window._activeProject = { id: pid, name: (window._activeProject && _activeProject.id === pid && _activeProject.name) || pid };
    }
    switchTab('oil');
  } catch (e) { alert('⚠ ' + e.message); }
}

// Gemeinsamer Einreih-Helfer für alle „➕ Warteschlange"-Knöpfe.
async function enqueueJobs(items, feedbackEl) {
  if (!items || !items.length) { alert('Nichts zum Einreihen.'); return false; }
  try {
    const r = await fetch('/jobs/add', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                         body: JSON.stringify({ jobs: items }) });
    const j = await r.json();
    if (!r.ok) { alert('⚠ ' + (j.error || 'Einreihen fehlgeschlagen')); return false; }
    const msg = `✔ ${j.n} Job${j.n === 1 ? '' : 's'} eingereiht → Tab ⏳ Jobs`;
    if (feedbackEl) { feedbackEl.textContent = msg; setTimeout(() => { feedbackEl.textContent = ''; }, 5000); }
    try { const q = await fetch('/jobs').then(x => x.json());
          _jobsBadge((q.jobs || []).filter(x => x.status === 'wartet' || x.status === 'läuft').length); } catch (e) {}
    return true;
  } catch (e) { alert('⚠ ' + e.message); return false; }
}

// Reattach beim Laden: laufende Server-Jobs wieder anzeigen (Browser war zu) + Jobs-Badge.
async function _reattachJobs() {
  try {
    const s = await fetch('/status').then(r => r.json());
    if (s.status === 'running') {
      const rb = document.getElementById('tbtn-results'); if (rb) rb.disabled = false;
      const btn = document.getElementById('btn_analyse');
      if (btn) { btn.disabled = true; btn.textContent = '⏳ Analyse läuft…'; }
      const ap = document.getElementById('analysis-progress'); if (ap) ap.classList.add('show');
      const rc = document.getElementById('results-content'); if (rc) rc.style.display = 'none';
      if (!_pollTimer) _pollTimer = setInterval(pollStatus, 1200);
    }
  } catch (e) {}
  try {
    const s = await fetch('/em3d/status').then(r => r.json());
    if (s.status === 'running' && typeof _pollEm3d === 'function') _pollEm3d();
  } catch (e) {}
  try {
    const s = await fetch('/oilspray/status').then(r => r.json());
    if (s.status === 'running' && typeof _pollOil === 'function') {
      const ob = document.getElementById('oil_btn'); if (ob) ob.disabled = true;
      const pw = document.getElementById('oil_progress_wrap'); if (pw) pw.style.display = 'block';
      const ab = document.getElementById('oil_abort_btn'); if (ab) ab.style.display = '';
      _pollOil();
    }
  } catch (e) {}
  try {
    const s = await fetch('/cfd/status').then(r => r.json());
    if (s.status === 'running' && typeof _pollCfd === 'function') {
      const b = document.getElementById('cfd_btn'); if (b) b.disabled = true;
      const pw = document.getElementById('cfd_progress_wrap'); if (pw) pw.style.display = 'block';
      const ab = document.getElementById('cfd_abort_btn'); if (ab) ab.style.display = '';
      _pollCfd();
    }
  } catch (e) {}
  try {
    const j = await fetch('/jobs').then(r => r.json());
    _jobsBadge((j.jobs || []).filter(x => x.status === 'wartet' || x.status === 'läuft').length);
  } catch (e) {}
  // Badge leichtgewichtig aktuell halten (der Jobs-Tab selbst pollt schneller).
  setInterval(async () => {
    try {
      const j = await fetch('/jobs').then(r => r.json());
      _jobsBadge((j.jobs || []).filter(x => x.status === 'wartet' || x.status === 'läuft').length);
    } catch (e) {}
  }, 10000);
}
window.addEventListener('load', _reattachJobs);
