// Zielwertoptimierung und Parameterstudie (Reiter ④ Berechnung).
//
// Beide schicken nur einen Spec an den Server und zeigen, was zurueckkommt;
// gerechnet wird in `ema_optimize` bzw. `ema_paramstudy`.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Zielwertoptimierung ──────────────────────────────────────────────────────
let _optMeta = null;
const OPT_APPLY = {   // free-param key → form input + value transform
  magWidth:{id:'mag_width',to:v=>v}, magThick:{id:'mag_thick',to:v=>v},
  magAngle:{id:'mag_angle',to:v=>v}, magAsym:{id:'mag_asym',to:v=>v}, magDist:{id:'mag_dist',to:v=>v},
  magDepthRel:{id:'mag_depth',to:v=>Math.round(v*100)}, slotDepth:{id:'slot_depth',to:v=>v},
  p:{id:'p_pairs',to:v=>Math.round(v)}, axial:{id:'dim_axial',to:v=>v},
};
function _optMetricOpts() {
  return Object.entries(_optMeta.metrics).map(([k, m]) => `<option value="${k}">${escHtml(m.label)}</option>`).join('');
}
async function openOptimizer() {
  document.getElementById('opt-modal').style.display = 'block';
  if (!_optMeta) _optMeta = await fetch('/optimize/meta').then(r => r.json());
  document.getElementById('opt-obj-metric').innerHTML = _optMetricOpts();
  // Kt und nicht T_maxwell: das Maxwell-Moment kommt aus dem geloesten Feld und
  // ist ohne aufgeloesten Luftspalt None — als Vorgabe einer Zielwertsuche also
  // eine Groesse, an der sich nichts messen laesst (s. ema_analysis).
  document.getElementById('opt-obj-metric').value = 'Kt';
  document.getElementById('opt-free').innerHTML = Object.entries(_optMeta.free_params).map(([k, f]) => `
    <div style="display:flex;gap:6px;align-items:center;margin-bottom:4px;font-size:.76rem">
      <label style="flex:1;display:flex;gap:5px;align-items:center;cursor:pointer">
        <input type="checkbox" class="opt-free-cb" data-k="${k}" ${['magWidth','magThick','magAngle'].includes(k)?'checked':''}/> ${escHtml(f.label)}</label>
      <input type="number" class="opt-free-lo" data-k="${k}" value="${f.lo}" style="width:60px;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:3px;border-radius:3px"/>
      <span style="color:#666">–</span>
      <input type="number" class="opt-free-hi" data-k="${k}" value="${f.hi}" style="width:60px;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:3px;border-radius:3px"/>
    </div>`).join('');
  if (!document.querySelector('.opt-constraint-row')) { addOptConstraint(); }
}
function closeOptimizer() { document.getElementById('opt-modal').style.display = 'none'; }
function addOptConstraint() {
  const div = document.createElement('div');
  div.className = 'opt-constraint-row';
  div.style.cssText = 'display:flex;gap:6px;align-items:center;margin-bottom:4px';
  div.innerHTML = `<select class="opt-c-metric" style="flex:1">${_optMetricOpts()}</select>
    <select class="opt-c-op" style="width:54px"><option value="<=">≤</option><option value=">=">≥</option></select>
    <input type="number" class="opt-c-val" placeholder="Wert" style="width:80px;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:5px;border-radius:3px"/>
    <button onclick="this.parentElement.remove()" style="background:#7a3030;width:auto;padding:4px 8px;font-size:.72rem">✕</button>`;
  document.getElementById('opt-constraints').appendChild(div);
}
// Baut den Optimierungs-Spec aus dem Modal (null bei Validierungsfehler → Alert). Von
// „▶ Optimierung starten" UND „➕ Warteschlange" gemeinsam genutzt.
async function _optBuildSpec() {
  const free = [...document.querySelectorAll('.opt-free-cb:checked')].map(cb => {
    const k = cb.dataset.k;
    const lo = +document.querySelector(`.opt-free-lo[data-k="${k}"]`).value;
    const hi = +document.querySelector(`.opt-free-hi[data-k="${k}"]`).value;
    return { param: k, min: Math.min(lo, hi), max: Math.max(lo, hi) };
  });
  if (!free.length) { alert('Mindestens einen freien Parameter wählen'); return null; }
  const cons = [...document.querySelectorAll('.opt-constraint-row')].map(r => ({
    metric: r.querySelector('.opt-c-metric').value, op: r.querySelector('.opt-c-op').value,
    value: parseFloat(r.querySelector('.opt-c-val').value),
  })).filter(c => !isNaN(c.value));
  const goal = document.getElementById('opt-obj-goal').value;
  const objective = { metric: document.getElementById('opt-obj-metric').value, goal };
  if (goal === 'target') objective.target = +document.getElementById('opt-obj-target').value;
  const base = await buildPayload();
  return { base_payload: base, objective, constraints: cons, free,
           iterations: +document.getElementById('opt-budget').value, batch: 6 };
}

async function runOptimize() {
  const spec = await _optBuildSpec();
  if (!spec) return;
  document.getElementById('opt-run').disabled = true;
  document.getElementById('opt-result').innerHTML = '';
  document.getElementById('opt-log').innerHTML = 'Starte…';
  const r = await fetch('/optimize', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                       body: JSON.stringify(spec) }).then(x => x.json());
  if (r.error) { alert(r.error); document.getElementById('opt-run').disabled = false; return; }
  _pollOptimize();
}
async function queueOptimize() {
  const spec = await _optBuildSpec();
  if (!spec) return;
  const title = 'Optimierung: ' + (document.getElementById('opt-obj-metric').value || '') +
                ' ' + (document.getElementById('opt-obj-goal').value || '');
  await enqueueJobs([{ type: 'optimize', title, payload: spec }],
                    document.getElementById('opt_queue_msg'));
}
// Ergebnis eines Optimierungs-Jobs ansehen (Modal öffnen + zuletzt gerechnetes Ergebnis).
async function openJobOptimize() {
  if (typeof openOptimizer === 'function') await openOptimizer();
  try {
    const s = await fetch('/optimize/status').then(x => x.json());
    const lg = document.getElementById('opt-log');
    if (lg) { lg.innerHTML = (s.log || []).map(escHtml).join('<br>'); lg.scrollTop = 1e9; }
    if (s.result) renderOptResult(s.result);
  } catch (e) {}
}
async function _pollOptimize() {
  const s = await fetch('/optimize/status').then(x => x.json());
  document.getElementById('opt-bar').style.width = (s.progress || 0) + '%';
  const lg = document.getElementById('opt-log');
  lg.innerHTML = (s.log || []).map(escHtml).join('<br>'); lg.scrollTop = 1e9;
  if (s.status === 'running') { setTimeout(_pollOptimize, 800); return; }
  document.getElementById('opt-run').disabled = false;
  if (s.status === 'error') { document.getElementById('opt-result').innerHTML = '<span style="color:#e57">Fehler: ' + escHtml(s.error || '') + '</span>'; return; }
  if (s.result) renderOptResult(s.result);
}
function renderOptResult(res) {
  const bm = res.best_metrics || {}, bp = res.best_params || {};
  const pj = Object.entries(bp).map(([k, v]) => `${k}=${(+v).toFixed(2)}`).join(', ');
  const mrows = Object.entries(bm).filter(([k]) => k !== 'error')
    .map(([k, v]) => `<tr><td style="color:#888;padding:2px 0">${escHtml(k)}</td><td style="color:#fff;text-align:right">${escHtml(String(v))}</td></tr>`).join('');
  document.getElementById('opt-result').innerHTML = `
    <div class="section-h">Beste${res.best_feasible ? ' (zulässige)' : ' — ⚠ keine zulässige gefunden'} Lösung</div>
    <div style="font-size:.76rem;color:#cde;margin-bottom:6px">${escHtml(pj)}</div>
    <table style="width:100%;font-size:.76rem;border-collapse:collapse">${mrows}</table>
    <div style="font-size:.7rem;color:#666;margin:6px 0">${res.n_evaluated} Auswertungen</div>
    <div style="display:flex;gap:6px">
      <button onclick='applyOptBest(${JSON.stringify(bp)},false)' style="flex:1;background:#2c5d8a;padding:8px;font-size:.76rem">Parameter übernehmen</button>
      <button onclick='applyOptBest(${JSON.stringify(bp)},true)' style="flex:1;background:#27ae60;padding:8px;font-size:.76rem">Übernehmen &amp; Voll-Analyse</button>
    </div>`;
}
function applyOptBest(params, andRun) {
  for (const [k, v] of Object.entries(params || {})) {
    const a = OPT_APPLY[k]; if (!a) continue;
    const el = document.getElementById(a.id); if (!el) continue;
    el.value = a.to(v);
    el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change'));
  }
  closeOptimizer(); switchTab('geo');
  if (andRun) document.getElementById('btn_analyse').click();
}

// ── Parameterstudie (ein Parameter über fester Drehzahl) ─────────────────────
// Geometrie-Parameter, die auch bei frei gezeichneten (custom) Designs wirken — die
// Magnet-Form-Parameter (magWidth/magAngle/…) verändern nur parametrische Topologien.
const _CUSTOM_STUDY_PARAMS = ['axial', 'airgap', 'slotDepth', 'p', 'magGap', 'shaftD', 'shaftBore'];
let _studyDesignPayload = null;     // non-null ⇒ Studie läuft auf dem Designer-Entwurf

function _populateStudyParams() {
  const sel = document.getElementById('study_param');
  if (!sel || !_optMeta) return;
  const entries = Object.entries(_optMeta.free_params)
    .filter(([k]) => !_studyDesignPayload || _CUSTOM_STUDY_PARAMS.includes(k));
  sel.innerHTML = entries.map(([k, f]) => `<option value="${k}">${escHtml(f.label)}</option>`).join('');
  _studyParamChanged();
}

async function initParamStudy() {
  const sel = document.getElementById('study_param');
  if (!sel || sel.options.length) return;            // already populated
  if (!_optMeta) _optMeta = await fetch('/optimize/meta').then(r => r.json());
  _populateStudyParams();
  sel.onchange = _studyParamChanged;
  _studyParamChanged();
  const fc = document.getElementById('study_field');
  if (fc) { const sync = () => { const v = fc.checked ? '' : 'none';
      document.getElementById('study_field_wrap').style.display = v;
      document.getElementById('study_field_res_wrap').style.display = v; };
    fc.onchange = sync; sync(); }
}
function _studyParamChanged() {
  // prefill x/y from the parameter's default range
  const sel = document.getElementById('study_param');
  const f = _optMeta && _optMeta.free_params[sel.value];
  if (!f) return;
  document.getElementById('study_lo').value = f.lo;
  document.getElementById('study_hi').value = f.hi;
  const lbl = (f.label.match(/\[([^\]]+)\]/) || [,'-'])[1];
  document.getElementById('study_unit1').textContent = lbl;
  document.getElementById('study_unit2').textContent = lbl;
}
// Baut den Parameterstudie-Body aus dem Formular (null bei Validierungsfehler → Alert).
// Von „📈 Parameterstudie starten" UND „➕ Warteschlange" gemeinsam genutzt.
async function _studyBuildBody() {
  const param = document.getElementById('study_param').value;
  const lo = +document.getElementById('study_lo').value;
  const hi = +document.getElementById('study_hi').value;
  const steps = +document.getElementById('study_steps').value;
  const rpm = +document.getElementById('study_rpm').value;
  const wantField = document.getElementById('study_field').checked;
  const field_frames = wantField ? +document.getElementById('study_field_n').value : 0;
  const field_N = +document.getElementById('study_field_res').value;
  if (lo === hi) { alert('Bereich x..y darf nicht leer sein (x ≠ y)'); return null; }
  // Studie auf dem Designer-/KI-Entwurf (custom-Geometrie) ODER der Formular-Auslegung
  const payload = _studyDesignPayload || await buildPayload();
  return { payload, param, lo, hi, steps, rpm, field_frames, field_N };
}

async function runParamStudy() {
  const body = await _studyBuildBody();
  if (!body) return;
  document.getElementById('btn_study').disabled = true;
  document.getElementById('study_result').innerHTML = '';
  document.getElementById('study_progress').style.display = 'block';
  const r = await fetch('/param_study', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  }).then(x => x.json());
  if (r.error) { alert(r.error); document.getElementById('btn_study').disabled = false; return; }
  _pollParamStudy();
}

async function queueParamStudy() {
  const body = await _studyBuildBody();
  if (!body) return;
  const title = 'Parameterstudie: ' + body.param + ' ' + body.lo + '…' + body.hi;
  await enqueueJobs([{ type: 'param_study', title, payload: body }],
                    document.getElementById('study_queue_msg'));
}
// Ergebnis eines Parameterstudie-Jobs ansehen (Tab ④ öffnen + zuletzt gerechnetes Ergebnis).
async function openJobStudy() {
  switchTab('calc');
  if (typeof initParamStudy === 'function') await initParamStudy();
  try {
    const s = await fetch('/param_study/status').then(x => x.json());
    document.getElementById('study_progress').style.display = 'block';
    document.getElementById('study_bar').style.width = (s.progress || 0) + '%';
    if (s.status === 'running') { _pollParamStudy(); return; }
    _studyRenderDone(s);
  } catch (e) {}
}
async function _pollParamStudy() {
  const s = await fetch('/param_study/status').then(x => x.json());
  document.getElementById('study_bar').style.width = (s.progress || 0) + '%';
  const log = (s.log || []);
  document.getElementById('study_msg').textContent = log[log.length - 1] || '…';
  if (s.status === 'running') { setTimeout(_pollParamStudy, 700); return; }
  _studyRenderDone(s);
}
// Fertiges Studienergebnis rendern (aus dem Poll ODER beim Öffnen eines Job-Ergebnisses).
function _studyRenderDone(s) {
  const btn = document.getElementById('btn_study'); if (btn) btn.disabled = false;
  if (s.status === 'error') {
    document.getElementById('study_result').innerHTML =
      '<span style="color:#e57">Fehler: ' + escHtml(s.error || '') + '</span>';
    return;
  }
  if (s.result) {
    const res = s.result;
    let html =
      `<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">`
      + `<span style="font-size:.72rem;color:#888">${res.n_ok} ausgewertet`
      + (res.n_fail ? `, ${res.n_fail} fehlgeschlagen` : '') + `</span>`
      + (res.kennung ? `<span style="font-size:.7rem;color:#6a8" title="${escHtml(res.ordner||'')}">🗂 ${escHtml(res.kennung)}</span>` : '')
      + `<a href="${res.gespeichert && res.kennung ? '/param_study/gespeichert/'+encodeURIComponent(res.kennung)+'/csv' : '/param_study/csv'}?t=${Date.now()}" style="margin-left:auto;background:#3a5a6a;color:#fff;text-decoration:none;border-radius:4px;padding:6px 12px;font-size:.74rem">⬇ Schritt-Werte (CSV)</a>`
      + `<button id="btn_study_report" onclick="makeStudyReport()" style="background:#7a5a3a;width:auto;padding:6px 12px;font-size:.74rem">📄 Studienbericht (PDF)</button>`
      + `</div>`
      + `<div id="study_report_msg" style="font-size:.74rem;color:#9aa;margin-bottom:6px"></div>`
      + `<img src="data:image/png;base64,${res.chart_b64}" style="width:100%;border-radius:4px;cursor:zoom-in" `
      + `onclick="window.open(this.src)"/>`;
    const imgs = res.field_images || [];
    if (imgs.length) {
      html += `<div class="section-h" style="margin-top:12px">Feldlinien über ${escHtml(res.label)}</div>`;
      if (res.field_video) {
        const vsrc = (res.gespeichert && res.kennung)
          ? '/param_study/gespeichert/' + encodeURIComponent(res.kennung) + '/video'
          : '/param_study/video';
        html += `<video src="${vsrc}?t=${Date.now()}" controls loop autoplay muted `
              + `style="width:100%;border-radius:4px;margin-bottom:8px;background:#000"></video>`;
      }
      html += `<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:6px">`
        + imgs.map(im =>
            `<figure style="margin:0">`
            + `<img src="data:image/png;base64,${im.b64}" style="width:100%;border-radius:3px;cursor:zoom-in" onclick="window.open(this.src)"/>`
            + `<figcaption style="font-size:.68rem;color:#9aa;text-align:center">${escHtml(res.label)}=${(+im.value).toFixed(2)}</figcaption>`
            + `</figure>`).join('')
        + `</div>`;
    }
    document.getElementById('study_result').innerHTML = html;
    if (typeof studyRefreshSaved === 'function') studyRefreshSaved();
  }
}

// ── 🗂 Studien-Store: je Studie EIN Ordner ───────────────────────────────────
// Vorher schrieben alle Studien in denselben Ordner und das Ergebnis lag nur im
// Serverspeicher — die zweite Studie loeschte die Bilder der ersten, und nach
// einem Neustart war alles weg. Geladen wird durch DIESELBE Zeichenfunktion wie
// ein frischer Lauf (`_studyRenderDone`), damit die beiden nicht auseinanderlaufen.
async function studyRefreshSaved() {
  const box = document.getElementById('study_saved_list');
  if (!box) return;
  let list = [];
  try { list = await fetch('/param_study/gespeichert').then(r => r.json()); } catch (e) {}
  if (!Array.isArray(list) || !list.length) {
    box.innerHTML = '<span style="font-size:.72rem;color:#789">Noch keine Studie abgelegt.</span>';
    return;
  }
  box.innerHTML = list.map(e => {
    const sp = (e.x_von != null && e.x_bis != null)
      ? (+e.x_von).toPrecision(3) + '…' + (+e.x_bis).toPrecision(3) : '';
    const warn = e.n_unerreichbar
      ? ` <span style="color:#e9a" title="Schritte ohne erreichbaren Betriebspunkt">⚠${e.n_unerreichbar}</span>` : '';
    const q = '?projekt=' + encodeURIComponent(e.wurzel || 'current');
    return `<div style="display:flex;align-items:center;gap:7px;background:#141821;border:1px solid #222a33;border-radius:5px;padding:6px 9px">
      <input type="checkbox" class="study-pick" value="${escHtml(e.kennung)}" data-wurzel="${escHtml(e.wurzel||'current')}"
             style="width:auto;margin:0" title="für den Reihenbericht auswählen"/>
      <div style="flex:1;min-width:0">
        <div style="font-size:.76rem;color:#cde;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
          ${escHtml(e.label || e.param || '?')} · ${escHtml(sp)} · ${e.steps} Schritte${warn}</div>
        <div style="font-size:.68rem;color:#789">${escHtml(e.zeitpunkt || e.kennung)} · ${e.rpm ? Math.round(e.rpm)+' U/min' : ''}${e.video ? ' · 🎬' : ''}${e.wurzel === 'global' ? ' · global' : ''}</div>
      </div>
      <button onclick="studyLoadSaved('${escHtml(e.kennung)}','${escHtml(e.wurzel||'current')}')" style="background:#456;width:auto;padding:4px 9px;font-size:.7rem" title="Studie ansehen">📂</button>
      <button onclick="studyBerichtEinzeln('${escHtml(e.kennung)}','${escHtml(e.wurzel||'current')}')" style="background:#7a5a3a;width:auto;padding:4px 9px;font-size:.7rem" title="PDF-Bericht über diese Studie erzeugen (wird in ihrem Ordner abgelegt)">📄</button>
      ${e.bericht ? `<a href="/param_study/gespeichert/${encodeURIComponent(e.kennung)}/bericht/download${q}" target="_blank" style="background:#3a5a6a;color:#fff;text-decoration:none;border-radius:4px;padding:4px 9px;font-size:.7rem" title="abgelegten Bericht öffnen">📕</a>` : ''}
      <a href="/param_study/gespeichert/${encodeURIComponent(e.kennung)}/csv${q}" style="background:#3a5a6a;color:#fff;text-decoration:none;border-radius:4px;padding:4px 9px;font-size:.7rem">⬇</a>
      <button onclick="studyDeleteSaved('${escHtml(e.kennung)}','${escHtml(e.wurzel||'current')}')" style="background:#633;width:auto;padding:4px 9px;font-size:.7rem">🗑</button>
    </div>`;
  }).join('');
}

async function studyLoadSaved(kennung, wurzel) {
  try {
    const st = await fetch('/param_study/gespeichert/' + encodeURIComponent(kennung)
                           + '?projekt=' + encodeURIComponent(wurzel || 'current')).then(r => r.json());
    if (st && !st.error) _studyRenderDone({ status: 'done', result: st });
  } catch (e) {}
}

// ── 📄 Berichte ueber ABGELEGTE Studien ─────────────────────────────────────
// Der vorhandene Knopf am Ergebnis berichtet nur ueber die ZULETZT gerechnete
// Studie (sie liegt im Serverspeicher und ist nach einem Neustart weg). Diese
// beiden gehen ueber den Store: einzeln, oder als Reihe ueber mehrere — letzteres
// beantwortet die Frage, die vor der Auslegung steht, naemlich welcher Parameter
// ueberhaupt zuerst anzufassen ist.
function _studyPicks() {
  return Array.from(document.querySelectorAll('.study-pick:checked'))
              .map(el => ({ kennung: el.value, wurzel: el.dataset.wurzel }));
}

async function _studyBerichtPoll(msgEl, fertigHtml) {
  let s;
  try { s = await fetch('/param_study/report/status').then(x => x.json()); }
  catch (e) { setTimeout(() => _studyBerichtPoll(msgEl, fertigHtml), 1500); return; }
  if (msgEl) msgEl.textContent = (s.log || []).slice(-1)[0] || '…';
  if (s.status === 'running') { setTimeout(() => _studyBerichtPoll(msgEl, fertigHtml), 900); return; }
  document.querySelectorAll('#btn_study_reihe').forEach(b => b.disabled = false);
  if (!msgEl) return;
  if (s.status === 'error') { msgEl.style.color = '#e57'; msgEl.textContent = '⚠ ' + (s.error || 'Fehler'); return; }
  msgEl.style.color = '#9c9';
  msgEl.innerHTML = fertigHtml;
  studyRefreshSaved();
}

async function studyBerichtEinzeln(kennung, wurzel) {
  const msg = document.getElementById('study_reihe_msg');
  if (msg) { msg.style.color = '#9aa'; msg.textContent = '⏳ Bericht über ' + kennung + ' …'; }
  const r = await fetch('/param_study/gespeichert/' + encodeURIComponent(kennung) + '/bericht',
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ projekt: wurzel || 'current' }) }).then(x => x.json());
  if (r.error) { if (msg) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; } return; }
  _studyBerichtPoll(msg, '✓ Bericht fertig — <a href="/param_study/gespeichert/'
    + encodeURIComponent(kennung) + '/bericht/download?projekt=' + encodeURIComponent(wurzel || 'current')
    + '" target="_blank" style="color:#6cf">PDF öffnen</a>');
}

async function studyBerichtReihe() {
  const msg = document.getElementById('study_reihe_msg');
  const picks = _studyPicks();
  const btn = document.getElementById('btn_study_reihe');
  if (btn) btn.disabled = true;
  const wurzel = picks.length ? picks[0].wurzel : 'current';
  if (msg) {
    msg.style.color = '#9aa';
    msg.textContent = '⏳ Reihenbericht über ' + (picks.length || 'alle') + ' Studien …';
  }
  const r = await fetch('/param_study/reihe/bericht', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ kennungen: picks.map(p => p.kennung), projekt: wurzel })
  }).then(x => x.json());
  if (r.error) {
    if (btn) btn.disabled = false;
    if (msg) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; }
    return;
  }
  _studyBerichtPoll(msg, '✓ Reihenbericht fertig — <a href="/param_study/reihe/bericht/download?projekt='
    + encodeURIComponent(wurzel) + '" target="_blank" style="color:#6cf">studienreihe.pdf öffnen</a>');
}

async function studyDeleteSaved(kennung, wurzel) {
  if (!confirm('Studie ' + kennung + ' loeschen? Der ganze Ordner geht weg.')) return;
  try {
    await fetch('/param_study/gespeichert/' + encodeURIComponent(kennung) + '/delete?projekt='
                + encodeURIComponent(wurzel || 'current'), { method: 'POST' });
  } catch (e) {}
  studyRefreshSaved();
}

async function makeStudyReport() {
  const btn = document.getElementById('btn_study_report');
  const msg = document.getElementById('study_report_msg');
  if (btn) btn.disabled = true;
  if (msg) { msg.style.color = '#9aa'; msg.textContent = '⏳ Bericht wird erstellt (LLM)…'; }
  const r = await fetch('/param_study/report', { method: 'POST',
    headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({}) }).then(x => x.json());
  if (r.error) { if (msg) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; }
    if (btn) btn.disabled = false; return; }
  _pollStudyReport();
}
async function _pollStudyReport() {
  const s = await fetch('/param_study/report/status').then(x => x.json());
  const msg = document.getElementById('study_report_msg');
  if (msg) msg.textContent = (s.log || []).slice(-1)[0] || '…';
  if (s.status === 'running') { setTimeout(_pollStudyReport, 900); return; }
  const btn = document.getElementById('btn_study_report');
  if (btn) btn.disabled = false;
  if (s.status === 'error') { if (msg) { msg.style.color = '#e57'; msg.textContent = 'Fehler: ' + (s.error || ''); } return; }
  if (s.has_pdf && msg) {
    msg.style.color = '#9c9';
    msg.innerHTML = '✓ Bericht fertig — <a href="/param_study/report/download" target="_blank" style="color:#6cf">parameterstudie.pdf öffnen</a>';
  }
}
