// Reiter ⚖ Vergleich: Projektauswahl, Variantensaetze, Parametertabelle.
//
// Die drei Wege, auf denen MEHRERE Rechnungen entstehen oder nebeneinander
// gestellt werden. `buildPayload` (formular.js) ist dabei die eine Quelle
// des Payloads -- hier wird er nur vervielfaeltigt.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Compare tab ────────────────────────────────────────────────────────────────

const VARIANT_COLORS = ["#00d4ff", "#ff6b35", "#27ae60", "#e74c3c"];

async function refreshComparePicker() {
  try {
    const j = await fetch('/projects').then(r => r.json());
    const list = document.getElementById('cmp-project-list');
    const projs = (j.projects || []).filter(p => p.has_results);
    if (projs.length === 0) {
      list.innerHTML = '<div style="color:#888;font-size:.8rem">Noch keine Projekte mit results.json vorhanden.</div>';
      return;
    }
    list.innerHTML = projs.map(p =>
      `<label style="display:flex;gap:8px;align-items:center;cursor:pointer;padding:4px;border-radius:3px"
              onmouseover="this.style.background='#222'" onmouseout="this.style.background=''">
        <input type="checkbox" value="${p.id}" class="cmp-checkbox" onchange="updateCompareCount()"/>
        <span style="font-size:.82rem;color:#ddd">${escHtml(p.label)}</span>
        <span style="font-size:.7rem;color:#666">${escHtml(p.rpm_range || '')}</span>
        <span style="font-size:.68rem;color:#555;margin-left:auto">${p.id}</span>
      </label>`
    ).join('');
    updateCompareCount();
  } catch (e) { /* ignore */ }
}

function updateCompareCount() {
  const sel = document.querySelectorAll('.cmp-checkbox:checked');
  const cnt = document.getElementById('cmp-count');
  if (sel.length === 0) { cnt.textContent = ''; return; }
  cnt.textContent = `${sel.length}/10 ausgewählt`;
  // Limit to 10: disable other unchecked
  if (sel.length >= 10) {
    document.querySelectorAll('.cmp-checkbox:not(:checked)').forEach(cb => cb.disabled = true);
  } else {
    document.querySelectorAll('.cmp-checkbox').forEach(cb => cb.disabled = false);
  }
}

document.getElementById('btn_compare').addEventListener('click', runCompare);

async function runCompare() {
  const ids = [...document.querySelectorAll('.cmp-checkbox:checked')].map(cb => cb.value);
  if (ids.length < 1) { alert('Mindestens ein Projekt auswählen'); return; }
  if (ids.length > 10) { alert('Maximal 10 Projekte'); return; }
  const btn = document.getElementById('btn_compare');
  btn.disabled = true; btn.textContent = '⏳ lädt…';
  try {
    const r = await fetch('/compare?ids=' + ids.join(',')).then(x => x.json());
    if (r.error) { alert('Vergleich fehlgeschlagen: ' + r.error); return; }
    renderCompareResults(r);
  } catch (e) {
    alert('Fehler: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = '⚖ Vergleich starten';
  }
}

function renderCompareResults(r) {
  document.getElementById('cmp-results').style.display = 'block';
  document.getElementById('cmp-empty').style.display   = 'none';

  document.getElementById('cmp-kennlinien-img').src = 'data:image/png;base64,' + r.kennlinien_b64;
  document.getElementById('cmp-thermal-img').src    = 'data:image/png;base64,' + r.thermal_b64;

  // Build table: header with V1..Vn (color dots) + label/unit columns
  const variants = r.table.variants || [];
  const thead = document.getElementById('cmp-thead');
  const tbody = document.getElementById('cmp-tbody');
  thead.innerHTML = '<tr><th style="text-align:left">Kennwert</th>' +
    variants.map((v, i) =>
      `<th><span style="display:inline-block;width:10px;height:10px;background:${v.color};border-radius:50%;margin-right:5px"></span>` +
      `V${i+1} <span style="font-weight:normal;color:#888;font-size:.78rem">${escHtml(v.label)}</span></th>`
    ).join('') + '<th>Einheit</th></tr>';

  tbody.innerHTML = r.table.rows.map(row => {
    return `<tr><td style="font-weight:600;color:#ccc">${escHtml(row.label)}</td>` +
      row.values.map(v => `<td>${escHtml(String(v))}</td>`).join('') +
      `<td style="color:#666;font-size:.78rem">${escHtml(row.unit || '')}</td></tr>`;
  }).join('');
}

async function makeComparisonReport(agentic = false) {
  const ids = [...document.querySelectorAll('.cmp-checkbox:checked')].map(cb => cb.value);
  if (ids.length < 2) { alert('Mindestens 2 Projekte für einen Vergleichsbericht wählen'); return; }
  const btn = document.getElementById(agentic ? 'btn_cmp_report_ag' : 'btn_cmp_report');
  const st  = document.getElementById('cmp-report-status');
  btn.disabled = true;
  st.textContent = agentic ? '⏳ 6 Experten analysieren die Varianten…' : '⏳ Bericht wird erzeugt…';
  try {
    const model = (document.getElementById('cmp_model') || {}).value || 'qwen-gross:latest';
    const r = await fetch('/compare/report', { method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ ids, agentic, model }) }).then(x => x.json());
    if (r.error) { st.textContent = '❌ ' + r.error; btn.disabled = false; return; }
    const poll = setInterval(async () => {
      const s = await fetch('/report/status').then(x => x.json());
      st.textContent = `⏳ ${s.progress}% — ${(s.log[s.log.length-1] || '').slice(0, 60)}`;
      if (s.status === 'done') {
        clearInterval(poll); btn.disabled = false;
        st.innerHTML = '✓ fertig — <a href="/compare/report/download" style="color:#0cf">herunterladen</a>';
      } else if (s.status === 'error') {
        clearInterval(poll); btn.disabled = false; st.textContent = '❌ Fehler bei der Berichterzeugung';
      }
    }, 1500);
  } catch (e) { st.textContent = '❌ ' + e.message; btn.disabled = false; }
}

// Poll the report status until done/error; resolve with the final status string.
function _pollReportDone() {
  return new Promise(resolve => {
    const st = document.getElementById('cmp-report-status');
    const t = setInterval(async () => {
      try {
        const s = await fetch('/report/status').then(x => x.json());
        st.textContent = `⏳ ${s.progress}% — ${(s.log[s.log.length-1] || '').slice(0, 70)}`;
        if (s.status === 'done' || s.status === 'error') { clearInterval(t); resolve(s.status); }
      } catch (e) { /* keep polling */ }
    }, 1500);
  });
}

// Run the agentic comparison report sequentially with three models so they can be
// compared side by side. Each finished PDF is captured (blob) before the next run
// overwrites the server-side report state, and offered as a labelled download link.
async function makeComparisonReportTriple() {
  const ids = [...document.querySelectorAll('.cmp-checkbox:checked')].map(cb => cb.value);
  if (ids.length < 2) { alert('Mindestens 2 Projekte wählen'); return; }
  const models = ['qwen-gross:latest', 'ministral-3:14b', 'gemma4:26b'];
  const btn = document.getElementById('btn_cmp_report_triple');
  const st  = document.getElementById('cmp-report-status');
  const box = document.getElementById('cmp-triple-links');
  btn.disabled = true; box.innerHTML = '';
  const stamp = new Date().toISOString().slice(0, 16).replace(/[:T]/g, '');
  for (let i = 0; i < models.length; i++) {
    const m = models[i];
    st.textContent = `⏳ (${i + 1}/3) ${m} startet…`;
    try {
      const r = await fetch('/compare/report', { method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ ids, agentic: true, model: m }) }).then(x => x.json());
      if (r.error) {
        box.insertAdjacentHTML('beforeend', `<span style="color:#e57;font-size:.78rem">❌ ${m}: ${r.error}</span>`);
        continue;
      }
      const status = await _pollReportDone();
      if (status !== 'done') {
        box.insertAdjacentHTML('beforeend', `<span style="color:#e57;font-size:.78rem">❌ ${m}: Fehler bei der Erzeugung</span>`);
        continue;
      }
      // Grab the freshly rendered PDF before the next model overwrites it
      const blob = await fetch('/compare/report/download').then(x => x.blob());
      const url  = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.textContent = `📄 Vergleichsbericht — ${m}`;
      a.download = `vergleich_${m.replace(/[:.]/g, '-')}_${stamp}.pdf`;
      a.style.cssText = 'color:#0cf;font-size:.82rem;text-decoration:none';
      box.appendChild(a);
    } catch (e) {
      box.insertAdjacentHTML('beforeend', `<span style="color:#e57;font-size:.78rem">❌ ${m}: ${e.message}</span>`);
    }
  }
  st.textContent = '✓ alle Modelle fertig — Berichte unten herunterladen';
  btn.disabled = false;
}

// ── Variant manager ─────────────────────────────────────────────────────────
let variants = [];

function _updateVarBadge() {
  const el = document.getElementById('var-badge');
  if (el) el.textContent = variants.length;
}

// Save the current canvas geometry as a variant (callable from the config panel).
async function rememberGeometry() {
  if (variants.length >= 10) { alert('Maximal 10 Geometrien — im Tab „Vergleich" verwalten/ausführen.'); return; }
  const nm = (document.getElementById('project_name').value || '').trim()
             || `Geometrie ${variants.length + 1}`;
  const payload = await buildPayload();
  payload.project_name = nm;
  variants.push({ name: nm, payload });
  _updateVarBadge();
  renderVariantList();
  const b = document.getElementById('btn_remember_geo');
  const prev = b.textContent;
  b.textContent = `✓ „${nm}" gemerkt (${variants.length}/10)`;
  setTimeout(() => { b.innerHTML = `＋ Geometrie merken (Variante <span id="var-badge">${variants.length}</span>/10) → Vergleich`; }, 1100);
}

function renderVariantList() {
  const el = document.getElementById('var-list');
  _updateVarBadge();
  if (!el) return;
  if (!variants.length) {
    el.innerHTML = '<div style="color:#666;font-size:.78rem">Noch keine Varianten — „＋ Geometrie merken" (Konfig-Panel) oder „+ Aktuelle Konfig" fügt die aktuellen Parameter hinzu.</div>';
    return;
  }
  el.innerHTML = variants.map((v, i) =>
    `<div style="display:flex;gap:6px;align-items:center;background:#0f0f1a;border:1px solid #333;border-radius:4px;padding:4px 6px">
       <span style="color:#888;font-size:.75rem;width:22px">#${i+1}</span>
       <input value="${escHtml(v.name)}" onchange="variants[${i}].name=this.value" style="flex:1;background:transparent;border:none;color:#eee;font-size:.8rem"/>
       <span style="color:#666;font-size:.72rem">${escHtml(v.payload.geom.magShape)} · p${v.payload.geom.p}</span>
       <button onclick="deleteVariant(${i})" style="background:#822;padding:2px 8px;font-size:.72rem">✕</button>
     </div>`).join('');
}

async function addVariant() {
  if (variants.length >= 10) { alert('Maximal 10 Varianten'); return; }
  const nm = (document.getElementById('var-name').value || '').trim()
             || `Variante ${variants.length + 1}`;
  const payload = await buildPayload();
  payload.project_name = nm;
  variants.push({ name: nm, payload });
  document.getElementById('var-name').value = '';
  renderVariantList();
}

function deleteVariant(i) { variants.splice(i, 1); renderVariantList(); }

function exportVariants() {
  if (!variants.length) { alert('Keine Varianten zum Exportieren'); return; }
  const set = { schema_version: 1, kind: 'ema_variant_set',
                name: document.getElementById('var-set-name').value || 'varianten',
                created: new Date().toISOString(), variants };
  const blob = new Blob([JSON.stringify(set, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = (set.name || 'varianten') + '.emavars.json';
  a.click(); URL.revokeObjectURL(a.href);
}

function importVariants(ev) {
  const f = ev.target.files[0]; if (!f) return;
  const rd = new FileReader();
  rd.onload = () => {
    try {
      const set = JSON.parse(rd.result);
      if (set.kind !== 'ema_variant_set' || !Array.isArray(set.variants))
        throw new Error('Kein gültiges Varianten-Set');
      variants = set.variants.slice(0, 10);
      if (set.name) document.getElementById('var-set-name').value = set.name;
      renderVariantList();
      document.getElementById('var-status').textContent = `${variants.length} Varianten importiert`;
    } catch (e) { alert('Import fehlgeschlagen: ' + e.message); }
  };
  rd.readAsText(f);
  ev.target.value = '';
}

function _pollUntilDone() {
  return new Promise((resolve) => {
    const t = setInterval(async () => {
      try {
        const s = await fetch('/status').then(r => r.json());
        document.getElementById('progress-fill').style.width = s.progress + '%';
        if (s.log && s.log.length) {
          const logEl = document.getElementById('progress-log');
          logEl.innerHTML = s.log.map(l => `<p>${escHtml(l)}</p>`).join('');
          logEl.scrollTop = logEl.scrollHeight;
        }
        if (s.status === 'done' || s.status === 'error') { clearInterval(t); resolve(s.status); }
      } catch (e) { /* keep polling */ }
    }, 1200);
  });
}

async function runAllVariants() {
  if (!variants.length) { alert('Keine Varianten'); return; }
  const btn = document.getElementById('btn_run_all');
  btn.disabled = true;
  document.getElementById('tbtn-results').disabled = false;
  switchTab('results');
  document.getElementById('analysis-progress').classList.add('show');
  document.getElementById('results-content').style.display   = 'none';
  const ranIds = [];
  for (let i = 0; i < variants.length; i++) {
    const v = variants[i];
    document.getElementById('progress-title').textContent =
      `⚙ Variante ${i+1}/${variants.length}: ${v.name}`;
    document.getElementById('var-status').textContent = `läuft: ${i+1}/${variants.length}`;
    try {
      const resp = await fetch('/analyse', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(v.payload) });
      if (!resp.ok) { addLog('❌ Variante ' + v.name + ' Start fehlgeschlagen'); continue; }
      const st = await _pollUntilDone();
      const cur = await fetch('/status').then(r => r.json());
      if (cur.project_id) ranIds.push(cur.project_id);
      if (st === 'error') addLog('❌ Variante ' + v.name + ' fehlgeschlagen');
    } catch (e) { addLog('❌ ' + v.name + ': ' + e.message); }
  }
  btn.disabled = false;
  document.getElementById('var-status').textContent = `fertig: ${ranIds.length} Projekte`;
  // Jump back to compare and preselect the freshly-run projects
  switchTab('compare');
  await refreshComparePicker();
  ranIds.forEach(id => {
    const cb = document.querySelector(`.cmp-checkbox[value="${id}"]`);
    if (cb) cb.checked = true;
  });
  updateCompareCount();
}

// ➕ Alle Varianten als SERVER-Jobs einreihen (statt der Client-Schleife oben) —
// die Reihe läuft dann auch bei geschlossenem Browser weiter (Tab ⏳ Jobs).
async function queueAllVariants() {
  if (!variants.length) { alert('Keine Varianten'); return; }
  const ok = await enqueueJobs(
    variants.map(v => ({ type: 'analyse', title: v.name, payload: v.payload })),
    document.getElementById('var-status'));
  if (ok) document.getElementById('var-status').textContent =
    `✔ ${variants.length} Varianten eingereiht → Tab ⏳ Jobs`;
}

async function saveVariantSet() {
  const name = (document.getElementById('var-set-name').value || '').trim();
  if (!name) { alert('Set-Name angeben'); return; }
  if (!variants.length) { alert('Keine Varianten'); return; }
  const r = await fetch('/variants/save', { method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({ name, created: new Date().toISOString(), variants }) }).then(x => x.json());
  if (r.error) { alert(r.error); return; }
  document.getElementById('var-status').textContent = `Set „${name}" gespeichert`;
  refreshVariantSets();
}

async function loadVariantSet(name) {
  if (!name) return;
  const set = await fetch('/variants/load/' + encodeURIComponent(name)).then(x => x.json());
  if (set.error) { alert(set.error); return; }
  variants = (set.variants || []).slice(0, 10);
  document.getElementById('var-set-name').value = set.name || name;
  renderVariantList();
  document.getElementById('var-status').textContent = `Set „${name}" geladen (${variants.length})`;
}

async function refreshVariantSets() {
  try {
    const r = await fetch('/variants/list').then(x => x.json());
    const sel = document.getElementById('var-set-list');
    sel.innerHTML = '<option value="">— Server-Set laden —</option>' +
      (r.sets || []).map(s => `<option value="${escHtml(s.name)}">${escHtml(s.label)} (${s.n_variants})</option>`).join('');
  } catch (e) { /* ignore */ }
}

// ── Parameter table (column variation) ───────────────────────────────────────
// Spalte 1 = Ausgangswerte; jede weitere Spalte ist eine editierbare Variante.
let _ptabSchema = null;            // [{key,desc,kind,in_geom,adv,lo,hi,int,options,def}]
let _ptabRows   = [];             // die gerade sichtbaren Zeilen (Feinparameter zuschaltbar)
let _ptabCols   = [];             // [{name, values:{key:val}}]  (col 0 = Basis)

// Map a schema key into the full /analyse payload (geom vs. top-level vs. axial_len)
function _ptabApply(payload, key, val, spec) {
  if (val === undefined || val === null || val === '') return;
  if (spec.kind === 'num') val = spec.int ? parseInt(val) : parseFloat(val);
  if (spec.in_geom)        payload.geom[key] = val;
  else if (key === 'axialLen') payload.axial_len = val;
  else                     payload[key] = val;
}
// Read a schema key's value out of a built payload (for the baseline column)
function _ptabRead(payload, spec) {
  const key = spec.key;
  if (spec.in_geom)        return payload.geom ? payload.geom[key] : undefined;
  if (key === 'axialLen')  return payload.axial_len;
  return payload[key];
}

async function buildParamTable() {
  const st = document.getElementById('ptab-status');
  try {
    if (!_ptabSchema) {
      const r = await fetch('/param_schema').then(x => x.json());
      _ptabSchema = r.params || [];
    }
    const base = await buildPayload();
    const vals = {};
    _ptabSchema.forEach(spec => {
      let v = _ptabRead(base, spec);
      if (v === undefined || v === null) v = spec.def;
      vals[spec.key] = v;
    });
    _ptabCols = [{ name: 'Ausgangswerte', values: vals }];
    renderParamTable();
    const nAdv = _ptabSchema.filter(sp => sp.adv).length;
    st.textContent = `${_ptabSchema.length - nAdv} Parameter geladen (+ ${nAdv} Feinparameter)`;
  } catch (e) { st.textContent = '❌ ' + e.message; }
}

function addParamColumn() {
  if (!_ptabCols.length) { buildParamTable(); return; }
  if (_ptabCols.length >= 10) { alert('Maximal 10 Spalten'); return; }
  const last = _ptabCols[_ptabCols.length - 1];
  _ptabCols.push({ name: `Variante ${_ptabCols.length}`, values: { ...last.values } });
  renderParamTable();
}

function removeParamColumn() {
  if (_ptabCols.length <= 1) { alert('Die Ausgangsspalte bleibt erhalten'); return; }
  _ptabCols.pop();
  renderParamTable();
}

function _ptabCell(spec, ci, val) {
  // Column 0 (baseline) is read-only; the rest are editable.
  const ro = ci === 0;
  const id = `ptab_${spec.key}_${ci}`;
  if (spec.kind === 'enum') {
    const opts = (spec.options || []).map(o =>
      `<option value="${escHtml(o.value)}" ${o.value == val ? 'selected' : ''}>${escHtml(o.label)}</option>`).join('');
    return `<select ${ro ? 'disabled' : ''} onchange="_ptabSet('${spec.key}',${ci},this.value)"
              style="width:100%;background:${ro ? '#15151f' : '#0f0f1a'};border:1px solid #333;color:#ddd;padding:3px;border-radius:3px;font-size:.74rem">${opts}</select>`;
  }
  if (spec.kind === 'bool') {
    // .checked, nicht .value — ein Kontrollkaestchen liefert sonst immer "on".
    return `<input type="checkbox" ${val === true || val === 'true' ? 'checked' : ''} ${ro ? 'disabled' : ''}
              onchange="_ptabSet('${spec.key}',${ci},this.checked)" style="width:16px;height:16px"/>`;
  }
  const step = spec.int ? '1' : 'any';
  return `<input type="number" step="${step}" value="${val ?? ''}" ${ro ? 'readonly' : ''}
            min="${spec.lo ?? ''}" max="${spec.hi ?? ''}"
            onchange="_ptabSet('${spec.key}',${ci},this.value)"
            style="width:88px;background:${ro ? '#15151f' : '#0f0f1a'};border:1px solid #333;color:#ddd;padding:3px 4px;border-radius:3px;font-size:.74rem"/>`;
}

function _ptabSet(key, ci, val) {
  if (_ptabCols[ci]) _ptabCols[ci].values[key] = val;
}

function renderParamTable() {
  const wrap = document.getElementById('ptab-wrap');
  if (!_ptabCols.length) {
    wrap.innerHTML = '<div style="color:#666;font-size:.82rem;padding:14px">Noch keine Tabelle.</div>';
    return;
  }
  let head = '<tr><th style="text-align:left;min-width:210px">Parameter</th>';
  _ptabCols.forEach((c, ci) => {
    head += `<th style="min-width:100px">${ci === 0
      ? escHtml(c.name)
      : `<input value="${escHtml(c.name)}" onchange="_ptabCols[${ci}].name=this.value"
           style="width:96px;background:transparent;border:none;border-bottom:1px solid #444;color:#7db9e8;font-size:.78rem;text-align:center"/>`}</th>`;
  });
  head += '</tr>';
  let body = '';
  const adv = (document.getElementById('ptab_adv') || {}).checked;
  _ptabRows = _ptabSchema.filter(sp => adv || !sp.adv);
  _ptabRows.forEach(spec => {
    body += `<tr><td style="font-size:.76rem;color:#bbb">${escHtml(spec.desc)}</td>`;
    _ptabCols.forEach((c, ci) => {
      body += `<td style="text-align:center">${_ptabCell(spec, ci, c.values[spec.key])}</td>`;
    });
    body += '</tr>';
  });
  wrap.innerHTML = `<table class="data-table" style="font-size:.76rem">
    <thead>${head}</thead><tbody>${body}</tbody></table>`;
}

// Build a full /analyse payload for one table column (baseline form + overrides)
async function _ptabColPayload(col) {
  const p = await buildPayload();
  _ptabSchema.forEach(spec => _ptabApply(p, spec.key, col.values[spec.key], spec));
  p.project_name = col.name || 'Variante';
  return p;
}

function paramTableToVariants() {
  if (_ptabCols.length < 1) { alert('Keine Tabelle'); return; }
  Promise.all(_ptabCols.map(async c => ({ name: c.name, payload: await _ptabColPayload(c) })))
    .then(vs => { variants = vs.slice(0, 10); renderVariantList(); _updateVarBadge();
      document.getElementById('ptab-status').textContent = `${variants.length} Spalten als Varianten übernommen`; });
}

async function runParamTable() {
  if (_ptabCols.length < 1) { alert('Erst eine Tabelle erzeugen'); return; }
  const st = document.getElementById('ptab-status');
  document.getElementById('tbtn-results').disabled = false;
  switchTab('results');
  document.getElementById('analysis-progress').classList.add('show');
  document.getElementById('results-content').style.display = 'none';
  const ranIds = [];
  for (let i = 0; i < _ptabCols.length; i++) {
    const col = _ptabCols[i];
    document.getElementById('progress-title').textContent =
      `⚙ Spalte ${i+1}/${_ptabCols.length}: ${col.name}`;
    try {
      const payload = await _ptabColPayload(col);
      const resp = await fetch('/analyse', { method: 'POST',
        headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload) });
      if (!resp.ok) { addLog('❌ Spalte ' + col.name + ' Start fehlgeschlagen'); continue; }
      const s = await _pollUntilDone();
      const cur = await fetch('/status').then(r => r.json());
      if (cur.project_id) ranIds.push(cur.project_id);
      if (s === 'error') addLog('❌ Spalte ' + col.name + ' fehlgeschlagen');
    } catch (e) { addLog('❌ ' + col.name + ': ' + e.message); }
  }
  switchTab('compare');
  await refreshComparePicker();
  ranIds.forEach(id => {
    const cb = document.querySelector(`.cmp-checkbox[value="${id}"]`);
    if (cb) cb.checked = true;
  });
  updateCompareCount();
  refreshTrainingStats();
  if (st) st.textContent = `fertig: ${ranIds.length} Spalten gerechnet`;
}

// ➕ Alle Tabellen-Spalten als SERVER-Jobs einreihen (läuft auch bei geschlossenem Browser).
async function queueParamTable() {
  if (_ptabCols.length < 1) { alert('Erst eine Tabelle erzeugen'); return; }
  const items = [];
  for (const col of _ptabCols)
    items.push({ type: 'analyse', title: col.name || 'Spalte',
                 payload: await _ptabColPayload(col) });
  await enqueueJobs(items, document.getElementById('ptab-status'));
}

async function refreshTrainingStats() {
  try {
    const s = await fetch('/training/stats').then(x => x.json());
    const el = document.getElementById('training-stats');
    if (el) el.textContent = `— ${s.n_total} Datensätze (👍 ${s.n_gut} · 👎 ${s.n_schlecht} · offen ${s.n_unbewertet}) · bewertet: ${s.n_user_rated || 0} manuell / ${s.n_auto_rated || 0} KI-vorsortiert · ${s.n_images || 0} Bilder → ${s.n_vlm || 0} VLM-Einträge`;
    const dl = document.getElementById('training-dl');
    if (dl) dl.style.opacity = s.exists ? '1' : '0.4';
    const dlv = document.getElementById('training-dl-vlm');
    if (dlv) dlv.style.opacity = s.vlm_exists ? '1' : '0.4';
  } catch (e) { /* ignore */ }
}
function showRtab(name) {
  document.querySelectorAll('.rtab-content').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.rtab-btn').forEach(btn => btn.classList.remove('active'));
  const content = document.getElementById('rtab-' + name);
  if (content) content.classList.add('active');
  event.target.classList.add('active');
}
