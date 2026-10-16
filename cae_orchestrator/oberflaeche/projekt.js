// Reiter ① Projekt: anlegen, oeffnen, Projektakte, Auftrag, Papierkorb,
// Galerie, Wissensbasis und das globale Speichern-Fenster.
//
// Alles, was AM PROJEKT haengt und nicht an einer einzelnen Rechnung.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

async function refreshProjectList() {
  try {
    const j = await fetch('/projects').then(r => r.json());
    const sel = document.getElementById('project_load');
    const cur = sel.value;
    sel.innerHTML = '<option value="">— neues Projekt —</option>';
    (j.projects || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      const tag = [p.has_step ? 'STEP' : '', p.has_fcstd ? 'FCStd' : ''].filter(Boolean).join('+');
      opt.textContent = `${p.label}${p.rpm_range ? '  ['+p.rpm_range+']' : ''}${tag ? '  ('+tag+')' : ''}`;
      sel.appendChild(opt);
    });
    if (cur) sel.value = cur;
  } catch(e) { /* ignore */ }
}

async function onProjectSelect(e) {
  if (e.target.value) loadProjectById(e.target.value);
}

async function loadProjectById(pid) {
  if (!pid) return;
  document.getElementById('tbtn-results').disabled = false;
  switchTab('results');
  document.getElementById('analysis-progress').classList.remove('show');
  document.getElementById('results-content').style.display   = 'block';
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/load').then(x => x.json());
    if (r.error) { alert('Laden fehlgeschlagen: ' + r.error); return; }
    const data = await fetch('/results').then(x => x.json());
    const sel = document.getElementById('project_load'); if (sel) sel.value = pid;
    // Geladenes Projekt = aktives Projekt (Nachrechnungen/Berichte landen hier).
    pjSetActive(pid, (r.meta && (r.meta.name || r.meta.label)) || pid);
    // Sync the form to the project's saved inputs so "Stufen nachrechnen" (which uses
    // the current form) matches this project. Best-effort; ignore on legacy projects.
    try {
      const tpl = await fetch('/project/' + encodeURIComponent(pid) + '/template').then(x => x.json());
      if (tpl && tpl.payload) applyPayload(tpl.payload);
    } catch (e) { /* keep current form */ }
    renderSummary(data.summary);
    renderField(data.em);
    renderCadImages(data.cad_images);
    renderAirgap(data.em);
    renderEmCurve(data.em);
    renderPower(data.power);
    renderStress(data.structural_fem, data.structural_sweep, data.structural_sweep_chart_b64);
    renderAxialStruktur(data.axial_struktur, data.axial_struktur_chart_b64);
    renderConnection(data.connection);
    renderDeformation(data.deformation, data.structural_fem);
    renderThermal(data.thermal);
    renderDriveCycle(data.drivecycle);
    renderDriveCycleExtra(data.drivecycle_vollast,   'cycle-autobahn',  'cycle-autobahn-energy',  'cycle-autobahn-stats',  'rtab-btn-cycle-autobahn',  'cycle-autobahn-thermal',  'cycle-autobahn-therm-avg',  'cycle-autobahn-therm-peak',  'cycle-autobahn-therm-warn');
    renderDriveCycleExtra(data.drivecycle_anhaenger, 'cycle-anhaenger', 'cycle-anhaenger-energy', 'cycle-anhaenger-stats', 'rtab-btn-cycle-anhaenger', 'cycle-anhaenger-thermal', 'cycle-anhaenger-therm-avg', 'cycle-anhaenger-therm-peak', 'cycle-anhaenger-therm-warn');
    renderManual(data.manual);
    document.getElementById('btn_freecad').style.display  = 'block';
    document.getElementById('btn_step').style.display     = 'block';
    pjUpdateReportCard(pid, true);   // Bericht-Karte auf Tab ① freischalten
    renderRating(pid);
    showFrame(0);
  } catch(err) { alert('Fehler beim Laden: ' + err.message); }
}

refreshProjectList();

// ── Projekt-Tab (Einstieg: Anlage · Organisation · Wissensbasis) ─────────────
// Das "aktive Projekt": alle Berechnungen (buildPayload) schreiben hier hinein.
window._activeProject = null;

function pjActivate() {
  pjRefreshList();
  if (_activeProject && _activeProject.id) pjSetActive(_activeProject.id, _activeProject.name);
}

async function pjRefreshList() {
  const box = document.getElementById('pj-list');
  if (!box) return;
  try {
    const j = await fetch('/projects?detail=1').then(r => r.json());
    const ps = j.projects || [];
    if (!ps.length) { box.innerHTML = '<div style="color:#778;padding:10px">Noch keine Projekte.</div>'; return; }
    box.innerHTML = ps.map(p => {
      const act = (_activeProject && _activeProject.id === p.id);
      const st  = p.status ? `<span style="color:#9bd;font-size:.7rem">${escHtml(p.status)}</span>` : '';
      return `<div style="display:flex;align-items:center;gap:8px;padding:6px 4px;border-bottom:1px solid #2a2f38;${act?'background:#1b2a22':''}">
        <div style="flex:1;min-width:0">
          <div style="color:#cde;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${act?'✓ ':''}${escHtml(p.label || p.id)}</div>
          <div style="color:#778;font-size:.7rem">${escHtml((p.id||'').slice(0,15))} ${st}</div>
        </div>
        <button onclick="pjSetActive('${p.id}', this.dataset.n)" data-n="${escHtml(p.label||p.id)}"
                title="aktiv setzen" style="background:#2e7d4f;width:auto;padding:4px 9px;font-size:.72rem">Aktiv</button>
        <button onclick="loadProjectById('${p.id}')" title="Ergebnisse ansehen"
                style="background:#3a4a6a;width:auto;padding:4px 9px;font-size:.72rem">📊</button>
        <button onclick="pjDelete('${p.id}', this.dataset.n)" data-n="${escHtml(p.label||p.id)}"
                title="löschen" style="background:#5a2a2a;width:auto;padding:4px 8px;font-size:.72rem">✕</button>
      </div>`;
    }).join('');
  } catch (e) {
    box.innerHTML = '<div style="color:#e57;padding:10px">Fehler beim Laden.</div>';
  }
}

async function pjCreate() {
  const name  = document.getElementById('pj_new_name').value.trim();
  const tags  = document.getElementById('pj_new_tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const notes = document.getElementById('pj_new_notes').value;
  const msg   = document.getElementById('pj_new_msg');
  msg.textContent = '⏳ lege an…';
  try {
    const r = await fetch('/project/new', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      // `brief` ist dieselbe Eingabe wie `notes`, geht aber nach `design.brief` und
      // damit in den Steckbrief — also in das, was der Agent beim Start liest.
      // Vorher stand die Beschreibung nur in `notes` und war für ihn unsichtbar;
      // wer ihn danach beauftragte, tippte dieselbe Aufgabe ein zweites Mal.
      body: JSON.stringify({ name, tags, notes, brief: notes }) }).then(x => x.json());
    if (r.error) { msg.textContent = '❌ ' + r.error; return; }
    msg.textContent = '✓ angelegt: ' + (r.name || r.id);
    document.getElementById('pj_new_name').value = '';
    document.getElementById('pj_new_tags').value = '';
    document.getElementById('pj_new_notes').value = '';
    await pjRefreshList();
    pjSetActive(r.id, r.name || r.id);
  } catch (e) { msg.textContent = '❌ ' + e.message; }
}

function pjSetActive(pid, name) {
  if (!pid) return;
  window._activeProject = { id: pid, name: name || pid };
  const badge = document.getElementById('pj-active-badge');
  if (badge) badge.innerHTML = '✓ Aktives Projekt: <b style="color:#cfe">' + escHtml(name || pid) + '</b>';
  const wrap = document.getElementById('pj-active-wrap');
  if (wrap) wrap.style.display = 'block';
  // Server-side aktives Projekt setzen, damit Bericht + 3D-Feld (lesen _state) das
  // gewählte Projekt treffen (best-effort).
  fetch('/project/' + encodeURIComponent(pid) + '/activate', { method: 'POST' })
    .then(r => r.json())
    .then(j => { if (typeof pjUpdateReportCard === 'function') pjUpdateReportCard(pid, !!j.has_results); })
    .catch(() => {});
  pjRenderOrg(pid);
  pjRenderDocs(pid);
  pjRenderAuftrag(pid);
  pjRenderKorb(pid);
  pjRenderAehnlich(pid);
  pjRefreshList();
  // projektgebundene Panels (auf Tab 1) auffrischen
  if (typeof _e3RefreshSavedList === 'function') _e3RefreshSavedList();
  if (typeof refreshTrainingStats === 'function') refreshTrainingStats();
  // Die Bruecke merkt sich die Marke des Projekts, an dem sie haengt — nach
  // einem Wechsel haette die alte am neuen keine Bedeutung und meldete sofort
  // eine „Aenderung", die keine ist.
  if (typeof brueckeNeuesProjekt === 'function') brueckeNeuesProjekt();
}

// ── AUFTRAG.md: die Absicht des Projekts, fortschreibbar ────────────────────
// Gerendert wird der Text des SERVERS (ema_auftrag), nicht eine zweite Fassung
// hier — sonst zeigt die Maske etwas anderes als die Datei, die der Agent liest.
async function pjRenderAuftrag(pid) {
  const box = document.getElementById('pj_auftrag');
  const sel = document.getElementById('pj_auftrag_abschnitt');
  if (!box) return;
  box.innerHTML = '<span style="color:#778">…</span>';
  try {
    const j = await (await fetch('/project/' + encodeURIComponent(pid) + '/auftrag')).json();
    if (sel && !sel.options.length) {
      sel.innerHTML = (j.moeglich || []).map(a =>
        '<option value="' + escHtml(a.schluessel) + '">' + escHtml(a.titel) + '</option>').join('');
    }
    // Eine LISTE in Dateireihenfolge (das Dict hätte Flask alphabetisch sortiert).
    const ab = j.abschnitte || [];
    if (!ab.length || ab.every(a => a.leer)) {
      box.innerHTML = '<span style="color:#889">Noch nichts festgehalten. Halte hier fest, '
                    + '<b>wozu</b> dieses Projekt da ist und warum du entschieden hast, wie du '
                    + 'entschieden hast — die Agentenköpfe lesen es beim Start.</span>';
      return;
    }
    box.innerHTML = ab.map(a => {
      // Ein Platzhalter der Vorlage ist KEIN Inhalt — sonst liest man
      // „_noch keine_" als Aussage. Der Abschnitt bleibt sichtbar (dass er
      // offen ist, ist selbst eine Auskunft), aber gedämpft.
      const rumpf = a.leer
        ? '<span style="color:#667;font-style:italic">— offen —</span>'
        : escHtml(a.text)
            .replace(/^- \*\*(.+?)\*\*/gm, '<b style="color:#8ab">$1</b>')
            .replace(/\*\*(.+?)\*\*/g, '<b>$1</b>');
      return '<div style="margin-bottom:10px"><div style="color:#9cf;font-weight:600">'
           + escHtml(a.titel) + '</div><div style="white-space:pre-wrap">'
           + rumpf + '</div></div>';
    }).join('');
  } catch (e) { box.innerHTML = '<span style="color:#c88">nicht lesbar: ' + escHtml(e.message) + '</span>'; }
}

async function pjAuftragErgaenzen() {
  const pid = _activeProject && _activeProject.id;
  const msg = document.getElementById('pj_auftrag_msg');
  const inp = document.getElementById('pj_auftrag_text');
  const sel = document.getElementById('pj_auftrag_abschnitt');
  if (!pid || !inp || !sel) return;
  const text = (inp.value || '').trim();
  if (!text) { if (msg) msg.textContent = 'Kein Text.'; return; }
  if (msg) msg.textContent = '…';
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/auftrag', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ abschnitt: sel.value, text: text, quelle: 'Mensch' })
    });
    const j = await r.json();
    if (!r.ok) { if (msg) msg.textContent = '❌ ' + (j.error || r.status); return; }
    inp.value = '';
    if (msg) msg.textContent = '✓ ergänzt unter „' + j.abschnitt + '"';
    pjRenderAuftrag(pid);
    pjRenderOrg(pid);          // die Ergänzung steht auch in der Zeitleiste
  } catch (e) { if (msg) msg.textContent = '❌ ' + e.message; }
}

// ── Ähnliche Projekte ───────────────────────────────────────────────────────
// Verknüpfen ging schon immer, aber die Kennung musste man WISSEN — bei 75
// abgelegten Projekten verknüpft man dann, woran man sich erinnert, und das ist
// selten das Ähnlichste.
async function pjRenderAehnlich(pid) {
  const box = document.getElementById('pj_aehnlich');
  if (!box) return;
  box.innerHTML = '<span style="color:#778">…</span>';
  try {
    const j = await (await fetch('/project/' + encodeURIComponent(pid)
                                 + '/aehnlich?n=5')).json();
    const t = j.treffer || [];
    if (!t.length) {
      box.innerHTML = '<span style="color:#889">Keine vergleichbaren Projekte '
                    + '(hat dieses schon einen Payload?).</span>';
      return;
    }
    box.innerHTML = t.map(e =>
      '<div style="padding:5px 0;border-bottom:1px solid #2c313a">'
      + '<div style="display:flex;gap:8px;align-items:center">'
      + '<b style="color:#cfe">' + escHtml(e.label || e.id) + '</b>'
      + '<span style="color:#9cf">' + Math.round(e.aehnlichkeit * 100) + ' %</span>'
      + (e.dublette ? '<span style="color:#d9a441;font-size:.72rem">gleicher Payload</span>' : '')
      + '<button onclick="pjSetActive(\'' + escHtml(e.id) + '\',\'' + escHtml(e.label || e.id) + '\')" '
      + 'style="margin-left:auto;background:#2c5d8a;padding:3px 9px;font-size:.72rem">öffnen</button>'
      + '<button onclick="pjVerweisSetzen(\'' + escHtml(e.id) + '\')" title="Als Verweis festhalten" '
      + 'style="background:#3a3a3e;padding:3px 9px;font-size:.72rem">⚖ merken</button></div>'
      + '<div style="font-size:.72rem;color:#889;margin-top:2px">gleich: '
      + escHtml((e.gleich || []).join(', ') || '—') + '</div>'
      + ((e.anders || []).length ? '<div style="font-size:.72rem;color:#a87;margin-top:1px">anders: '
         + escHtml(e.anders.slice(0, 4).join(', ')) + '</div>' : '')
      + '</div>').join('');
  } catch (e) { box.innerHTML = '<span style="color:#c88">' + escHtml(e.message) + '</span>'; }
}

async function pjVerweisSetzen(otherId) {
  const pid = _activeProject && _activeProject.id;
  if (!pid) return;
  await fetch('/project/' + encodeURIComponent(pid) + '/links', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ id: otherId, relation: 'aehnlich',
                           note: 'über die Ähnlichkeitssuche gefunden' })
  });
  pjRenderOrg(pid);
}

// ── Papierkorb: hier landet alles, was entsorgt wird ────────────────────────
// Ohne diese Ansicht wäre der Korb aufgehoben und unerreichbar — und das ist
// von weg nicht zu unterscheiden.
async function pjRenderKorb(pid) {
  const box = document.getElementById('pj_korb');
  if (!box) return;
  try {
    const j = await (await fetch('/project/' + encodeURIComponent(pid) + '/papierkorb')).json();
    const e = (j.eintraege || []).filter(x => x.da);
    if (!e.length) { box.innerHTML = '<span style="color:#889">leer</span>'; return; }
    box.innerHTML = e.map(x =>
      '<div style="display:flex;gap:8px;align-items:center;padding:3px 0;border-bottom:1px solid #2c313a">'
      + '<span style="flex:1">' + escHtml(x.herkunft || x.name)
      + (x.grund ? ' <span style="color:#889">— ' + escHtml(x.grund) + '</span>' : '') + '</span>'
      + '<span style="color:#889;font-size:.72rem">' + escHtml(x.groesse) + '</span>'
      + '<button onclick="pjKorbZurueck(\'' + escHtml(x.marke) + '\')" '
      + 'style="background:#3a5d3a;padding:3px 9px;font-size:.72rem">↩ zurück</button></div>').join('');
  } catch (e) { box.innerHTML = '<span style="color:#c88">' + escHtml(e.message) + '</span>'; }
}

async function pjKorbZurueck(marke) {
  const pid = _activeProject && _activeProject.id;
  if (!pid) return;
  const r = await fetch('/project/' + encodeURIComponent(pid) + '/papierkorb', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ was: 'zurueck', marke: marke })
  });
  const j = await r.json();
  const msg = document.getElementById('pj_korb_msg');
  if (msg) msg.textContent = r.ok ? ('✓ zurückgeholt' + (j.hinweis ? ' — ' + j.hinweis : ''))
                                  : ('❌ ' + (j.error || r.status));
  pjRenderKorb(pid);
}

// Bericht-Karte (Tab ① Projekt): nur aktiv, wenn das aktive Projekt Ergebnisse hat.
function pjUpdateReportCard(pid, hasResults) {
  const btnStd = document.getElementById('btn_report');
  const btnAgt = document.getElementById('btn_report_agentic');
  const hint   = document.getElementById('pj_report_hint');
  if (!btnStd || !btnAgt) return;
  btnStd.disabled = btnAgt.disabled = !hasResults;
  // beim Projektwechsel die Knöpfe in den Ausgangszustand zurücksetzen (kein Download-Modus)
  btnStd.textContent = '📄 Bericht (Standard)';
  btnAgt.textContent = '🧠 6-Experten-Bericht';
  btnStd.style.background = '#2c5d8a';
  btnAgt.style.background = '#5a4a7a';
  btnStd.onclick = () => generateReport('standard');
  btnAgt.onclick = () => generateReport('agentic');
  const box = document.getElementById('report_status'); if (box) box.style.display = 'none';
  const rag = document.getElementById('report_rag');     if (rag) rag.style.display = 'none';
  if (hint) hint.textContent = hasResults
    ? 'PDF-Bericht für das aktive Projekt (lokales LLM für die Prosa, Kennwerte deterministisch).'
    : 'Erst verfügbar, wenn das aktive Projekt Ergebnisse hat — Geometrie + Analyse laufen lassen.';
}

async function pjRenderOrg(pid) {
  try {
    const m = await fetch('/project/' + encodeURIComponent(pid) + '/manifest').then(x => x.json());
    if (m.error) return;
    if (m.label) {
      if (_activeProject && _activeProject.id === pid) _activeProject.name = m.label;
      const badge = document.getElementById('pj-active-badge');
      if (badge) badge.innerHTML = '✓ Aktives Projekt: <b style="color:#cfe">' + escHtml(m.label) + '</b>';
    }
    const stEl = document.getElementById('pj_status'); if (stEl) stEl.value = m.status || 'neu';
    document.getElementById('pj_tags').value  = (m.tags || []).join(', ');
    document.getElementById('pj_notes').value = m.notes || '';
    const evo = (m.evolution || []);
    document.getElementById('pj_evolution').innerHTML = evo.length
      ? evo.map((e, i) => {
          const ch = Object.keys(e.changed_inputs || {});
          const note = e.note ? ` · <i style="color:#9ab">${escHtml(e.note)}</i>` : '';
          return `<div style="padding:3px 0;border-bottom:1px solid #2a2f38">
            <b>${i+1}.</b> ${escHtml((e.ts||'').slice(0,16).replace('T',' '))} — <span style="color:#9bd">${escHtml(typeof _akteAction==='function'?_akteAction(e.action):(e.action||''))}</span>
            <span style="color:#889;font-size:.72rem">${escHtml(ch.length?ch.join(', '):'—')}</span>${note}</div>`;
        }).join('')
      : '<span style="color:#778">noch keine Stufen — Berechnung anstoßen</span>';
    const lin = m.lineage || {};
    document.getElementById('pj_lineage').innerHTML =
      (lin.parent ? `Abstammung: <a href="#" onclick="pjSetActive('${lin.parent}');return false" style="color:#9bd">${escHtml(lin.parent)}</a> · ` : '')
      + 'Herkunft: ' + escHtml(lin.origin || '—');
    const btn = document.getElementById('pj_btn_results');
    if (btn) btn.style.display = (m.status && m.status !== 'neu') ? 'inline-block' : 'none';
  } catch (e) {}
}

async function pjSaveMeta() {
  const pid = _activeProject && _activeProject.id;
  if (!pid) return;
  const tags = document.getElementById('pj_tags').value.split(',').map(t => t.trim()).filter(Boolean);
  const msg = document.getElementById('pj_meta_msg'); msg.textContent = '⏳ …';
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/meta',
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: document.getElementById('pj_status').value,
          tags, notes: document.getElementById('pj_notes').value }) }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : '✓ gespeichert';
  } catch (e) { msg.textContent = '❌ ' + e.message; }
}

async function pjRenderDocs(pid) {
  try {
    const [rag, att] = await Promise.all([
      fetch('/project/' + encodeURIComponent(pid) + '/rag').then(x => x.json()),
      fetch('/project/' + encodeURIComponent(pid) + '/attachments').then(x => x.json()),
    ]);
    const docs = (rag.documents || []), atts = (att.attachments || []);
    const dHtml = docs.length
      ? docs.map(d => `<div style="display:flex;justify-content:space-between;padding:3px 0;border-bottom:1px solid #2a2f38">
          <span>📄 ${escHtml(d.title)} <span style="color:#778;font-size:.72rem">(${d.n_chunks} Abschnitte)</span></span>
          <button onclick="pjDelDoc('${d.id}')" style="background:#5a2a2a;width:auto;padding:2px 8px;font-size:.72rem">✕</button></div>`).join('')
      : '<span style="color:#778">keine Wissens-Dokumente</span>';
    const aHtml = atts.length
      ? '<div style="margin-top:7px;color:#9ab;font-size:.74rem">📎 Anhänge: ' + atts.map(a => escHtml(a.name)).join(', ') + '</div>'
      : '';
    document.getElementById('pj_docs').innerHTML = dHtml + aHtml;
  } catch (e) {}
}

async function pjDelDoc(docId) {
  const pid = _activeProject && _activeProject.id;
  if (!pid) return;
  await fetch('/project/' + encodeURIComponent(pid) + '/rag/' + encodeURIComponent(docId) + '/delete', { method: 'POST' });
  pjRenderDocs(pid);
}

async function pjUploadRag(input) {
  const pid = _activeProject && _activeProject.id;
  const f = input.files && input.files[0];
  if (!pid || !f) return;
  const msg = document.getElementById('pj_docs_msg'); msg.textContent = '⏳ einbetten…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/rag/add', { method: 'POST', body: fd }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : '✓ hinzugefügt';
    pjRenderDocs(pid);
  } catch (e) { msg.textContent = '❌ ' + e.message; }
  finally { input.value = ''; }
}

async function pjUploadAttachment(input) {
  const pid = _activeProject && _activeProject.id;
  const f = input.files && input.files[0];
  if (!pid || !f) return;
  const msg = document.getElementById('pj_docs_msg'); msg.textContent = '⏳ lade hoch…';
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/attachments', { method: 'POST', body: fd }).then(x => x.json());
    msg.textContent = r.error ? ('❌ ' + r.error) : ('✓ Anhang gespeichert' + (r.rag_added ? ' (+RAG)' : ''));
    pjRenderDocs(pid);
  } catch (e) { msg.textContent = '❌ ' + e.message; }
  finally { input.value = ''; }
}

// EIN Aufrufer fuer beide Loeschknoepfe (Projektliste und Galerie). Zwei
// Abschriften waeren die Stelle, an der die eine die Bestaetigung mitschickt
// und die andere nicht. Die Route entsorgt in den Papierkorb des Bestandes und
// weist ohne { bestaetigt: true } mit 409 ab -- die Rueckfrage sitzt im Server,
// nicht hier; dieser confirm ist die Hoeflichkeit davor, nicht die Sicherung.
async function _projektEntsorgen(pid, name) {
  const frage = 'Projekt „' + (name || pid) + '" in den Papierkorb legen?\n\n'
              + 'Es wird nach _papierkorb/ verschoben und ist von dort '
              + 'wiederherstellbar — nicht sofort vernichtet.';
  if (!confirm(frage)) return null;
  const r = await fetch('/project/' + encodeURIComponent(pid) + '/delete', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ bestaetigt: true, grund: 'ueber die Oberflaeche' })
  });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) { alert('Nicht entsorgt: ' + (j.error || r.status)); return null; }
  return j;
}

async function pjDelete(pid, name) {
  if (!await _projektEntsorgen(pid, name)) return;
  if (_activeProject && _activeProject.id === pid) {
    window._activeProject = null;
    const badge = document.getElementById('pj-active-badge');
    if (badge) badge.textContent = 'Kein aktives Projekt — lege eines an oder öffne ein bestehendes.';
    const wrap = document.getElementById('pj-active-wrap'); if (wrap) wrap.style.display = 'none';
  }
  pjRefreshList();
  if (typeof refreshProjectList === 'function') refreshProjectList();
}

function pjOpenResults() {
  if (_activeProject && _activeProject.id) loadProjectById(_activeProject.id);
}

// ── Project gallery (browse + open + delete) ─────────────────────────────────
let _galleryProjects = [];
async function openProjectGallery() {
  const ov = document.getElementById('project-gallery');
  ov.style.display = 'block';
  document.getElementById('gallery-grid').innerHTML =
    '<div style="color:#888;padding:20px">Lade Projekte…</div>';
  try {
    const j = await fetch('/projects?detail=1').then(r => r.json());
    _galleryProjects = j.projects || [];
  } catch (e) {
    document.getElementById('gallery-grid').innerHTML =
      '<div style="color:#e57;padding:20px">Fehler beim Laden der Projekte.</div>';
    return;
  }
  renderGallery();
}
function closeProjectGallery() { document.getElementById('project-gallery').style.display = 'none'; }

function _gNum(x, d = 0) {
  return (x === null || x === undefined) ? '—'
    : Number(x).toLocaleString('de-DE', { minimumFractionDigits: d, maximumFractionDigits: d });
}
function renderGallery() {
  const q = (document.getElementById('gallery-search').value || '').toLowerCase();
  const onlyRes = document.getElementById('gallery-only-results').checked;
  const list = _galleryProjects.filter(p =>
    (!onlyRes || p.has_results) &&
    (!q || (p.label + ' ' + (p.topology || '') + ' ' + p.id).toLowerCase().includes(q)));
  document.getElementById('gallery-count').textContent = list.length + ' Projekte';
  const grid = document.getElementById('gallery-grid');
  if (!list.length) { grid.innerHTML = '<div style="color:#888;padding:20px">Keine Projekte.</div>'; return; }
  grid.innerHTML = list.map(p => {
    const m = p.metrics || {};
    const pid = encodeURIComponent(p.id);
    const thumb = p.has_thumb
      ? `<img src="/project/${pid}/thumb" loading="lazy"
             style="width:100%;height:150px;object-fit:contain;background:#0d0d0d;border-radius:4px"/>`
      : `<div style="height:150px;background:#0d0d0d;border-radius:4px;display:flex;align-items:center;justify-content:center;color:#555;font-size:.8rem">kein Bild</div>`;
    // High-res EM-simulation field map (open circuit) — auto-saved by the pipeline.
    const emThumb = p.has_em_field
      ? `<a href="/project/${pid}/em_field" target="_blank" rel="noopener" title="EM-Feldsimulation in voller Auflösung öffnen">
           <img src="/project/${pid}/em_field" loading="lazy"
                style="width:100%;height:132px;object-fit:contain;background:#0d0d0d;border-radius:4px;margin-top:5px;cursor:zoom-in"/>
         </a>
         <div style="font-size:.64rem;color:#789;text-align:center;margin-top:1px">⚡ EM-Feld (Leerlauf) — klicken für volle Auflösung</div>`
      : '';
    const STAT = {neu:'#555', rechnet:'#b58900', gerechnet:'#2c5d8a',
                  bewertet:'#27632a', berichtet:'#6a4caf', verworfen:'#7a3030'};
    const akteBadges = [];
    if (p.status) akteBadges.push(`<span style="background:${STAT[p.status]||'#555'};color:#fff;border-radius:3px;padding:1px 6px;font-size:.66rem">${escHtml(p.status)}</span>`);
    if (p.parent) akteBadges.push(`<span title="aus ${escHtml(p.parent)}" style="background:#3a3a3e;color:#9bd;border-radius:3px;padding:1px 6px;font-size:.66rem">⤴ Vorlage</span>`);
    if (p.links_count) akteBadges.push(`<span title="verknüpfte Vergleichsprojekte" style="background:#3a3a3e;color:#9bd;border-radius:3px;padding:1px 6px;font-size:.66rem">⚖ ${p.links_count}</span>`);
    if (p.evolution_count) akteBadges.push(`<span title="Evolutionsstufen" style="background:#3a3a3e;color:#9bd;border-radius:3px;padding:1px 6px;font-size:.66rem">⟳ ${p.evolution_count}</span>`);
    const badges = [...akteBadges,
                    ...[p.has_results ? 'Ergebnisse' : '', p.has_step ? 'STEP' : '',
                    p.has_fcstd ? 'FCStd' : '', p.has_report ? '📄 Bericht' : '']
      .filter(Boolean).map(b => `<span style="background:#2c5d8a;color:#cde;border-radius:3px;padding:1px 6px;font-size:.66rem">${b}</span>`)].join(' ');
    const reportBtn = p.has_report
      ? `<a href="/project/${pid}/report/download?mode=latest" target="_blank" rel="noopener"
            title="Letzten erzeugten Bericht öffnen (${escHtml(p.report_file || 'PDF')})"
            style="display:block;text-align:center;margin-top:5px;background:#6a4caf;color:#fff;padding:7px;font-size:.74rem;border-radius:4px;text-decoration:none">📄 Bericht öffnen (PDF)</a>`
      : '';
    const metricsHtml = p.has_results ? `
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:2px 8px;font-size:.7rem;color:#bbb;margin-top:6px">
        <span>Kt: <b>${_gNum(m.Kt, 3)}</b></span><span>M: <b>${_gNum(m.T_maxwell, 1)}</b> Nm</span>
        <span>n_max: <b>${_gNum(m.max_safe_rpm)}</b></span><span>T_Mag: <b>${_gNum(m.T_magnet, 0)}</b> °C</span>
        <span>P: <b>${_gNum(m.P_total, 0)}</b> W</span><span>${m.verbrauch != null ? _gNum(m.verbrauch, 1) + ' kWh' : ''}</span>
      </div>` : '';
    return `<div style="background:#252528;border:1px solid #3a3a3e;border-radius:6px;padding:10px;display:flex;flex-direction:column">
      ${thumb}
      ${emThumb}
      <div style="font-weight:600;color:#fff;font-size:.86rem;margin-top:7px">${escHtml(p.label)}</div>
      <div style="font-size:.7rem;color:#888">${escHtml((p.created || '').slice(0, 16).replace('T', ' '))}</div>
      <div style="font-size:.72rem;color:#9bd;margin-top:2px">${escHtml(p.topology || '—')} · p${p.p ?? '?'} · Ø${p.stator_od ?? '?'} mm · ${p.axial ?? '?'} mm</div>
      ${metricsHtml}
      <div style="display:flex;gap:4px;margin-top:7px;flex-wrap:wrap">${badges}</div>
      <div style="display:flex;gap:5px;margin-top:8px">
        <button ${p.has_results ? '' : 'disabled'} onclick="galleryOpen('${p.id}')"
                style="flex:1;background:#27ae60;padding:7px;font-size:.74rem">Ergebnisse ansehen</button>
        <button onclick="galleryDelete('${p.id}')" title="Projekt löschen"
                style="background:#7a3030;width:auto;padding:7px 9px;font-size:.74rem">🗑</button>
      </div>
      <div style="display:flex;gap:5px;margin-top:5px">
        <button onclick="useAsTemplate('${p.id}')" title="Parameter dieses Projekts ins Formular laden"
                style="flex:1;background:#2c5d8a;padding:7px;font-size:.74rem">📋 Als Vorlage</button>
        <button onclick="cloneProject('${p.id}')" title="Ganzes Projekt klonen (Eingaben + Notizen + Projekt-RAG, mit Abstammung)"
                style="flex:1;background:#46607a;padding:7px;font-size:.74rem">📁 Klonen</button>
      </div>
      <a href="/project/${pid}/bundle" title="Projekt als .emaproj-Bundle exportieren"
         style="display:block;text-align:center;margin-top:5px;background:#3a3a3e;color:#cde;padding:6px;font-size:.72rem;border-radius:4px;text-decoration:none">⬇ Bundle exportieren</a>
      ${reportBtn}
    </div>`;
  }).join('');
}
// ── Text → EMA (Beschreibung → Parametersatz) ────────────────────────────────
const T2E_APPLY = {  // param key → {id, [to]} ; selects + sliders fire input/change
  statorOD:'dim_stator_out', statorID:'dim_stator_in', rotorOD:'dim_rotor_out',
  shaftD:'dim_shaft', shaftBoreD:'dim_shaft_bore', axialLen:'dim_axial',
  slots:'stator_slots', slotDepth:'slot_depth', p:'p_pairs', magShape:'mag_shape',
  machineType:'machine_art',
  magAngle:'mag_angle', magWidth:'mag_width', magThick:'mag_thick', magDist:'mag_dist',
  nAx:'n_ax', nCirc:'n_circ', rotor_lam:'sel_rotor_lam', stator_lam:'sel_stator_lam',
  hairpin_mat:'sel_hairpin', magnet:'sel_magnet', cooling:'sel_cooling',
  rpm_from:'rpm_from', rpm_to:'rpm_to', load_nm:'sim_load', T_ambient:'T_ambient',
  magDepthRel:{id:'mag_depth', to:v=>Math.round(v*100)},
};
function openText2Ema(){ document.getElementById('t2e-modal').style.display='block';
  document.getElementById('t2e-desc').focus(); }
function closeText2Ema(){ document.getElementById('t2e-modal').style.display='none'; }
async function runText2Ema(){
  const desc=document.getElementById('t2e-desc').value.trim();
  if(!desc){ alert('Bitte eine Beschreibung eingeben'); return; }
  const btn=document.getElementById('t2e-run'); btn.disabled=true;
  const out=document.getElementById('t2e-out');
  out.innerHTML='<span style="color:#888">⏳ LLM leitet Parameter ab…</span>';
  try{
    const r=await fetch('/text2ema',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({description:desc})}).then(x=>x.json());
    if(r.error){ out.innerHTML='<span style="color:#e57">⚠ '+escHtml(r.error)+'</span>'; return; }
    _t2eParams=r.params;
    const rows=Object.entries(r.params).map(([k,v])=>
      `<tr><td style="color:#888;padding:1px 8px 1px 0">${escHtml(k)}</td><td style="color:#fff">${escHtml(String(v))}</td></tr>`).join('');
    out.innerHTML=`
      ${r.rag_used?'<div style="font-size:.74rem;color:#9c9;margin-bottom:6px">📚 Mit Referenzmaschinen aus der Wissensbasis angereichert</div>':''}
      <div class="section-h">Begründung</div>
      <div style="font-size:.8rem;color:#cde;line-height:1.5;margin-bottom:8px">${escHtml(r.begruendung||'—')}</div>
      <div class="section-h">Abgeleitete Parameter</div>
      <table style="font-size:.76rem;border-collapse:collapse;columns:2">${rows}</table>
      <button onclick="applyText2Ema()" style="background:#27ae60;width:100%;padding:10px;font-size:.8rem;margin-top:10px">✓ In Formular übernehmen</button>`;
  }catch(e){ out.innerHTML='<span style="color:#e57">Fehler: '+escHtml(e.message)+'</span>'; }
  finally{ btn.disabled=false; }
}
let _t2eParams=null;
function applyText2Ema(){
  for(const [k,v] of Object.entries(_t2eParams||{})){
    const a=T2E_APPLY[k]; if(!a) continue;
    const id=typeof a==='string'?a:a.id;
    const el=document.getElementById(id); if(!el) continue;
    el.value=(typeof a==='object'&&a.to)?a.to(v):v;
    el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change'));
  }
  closeText2Ema(); switchTab('geo');
}

// ── Wissensbasis (RAG) ───────────────────────────────────────────────────────
function openRag(){ document.getElementById('rag-modal').style.display='block'; refreshRagList(); }
function closeRag(){ document.getElementById('rag-modal').style.display='none'; }

// ═══════════════════ GLOBALES SPEICHERN (Modal) ══════════════════════════════
// EIN Speicherknopf (Topbar) öffnet dieses Fenster: es zeigt alles, was gerade
// gespeichert werden kann, mit Vorschau + Auswahl (abwählbar). Ersetzt die
// verstreuten Einzel-Speicherknöpfe (Projektdaten / 3D-Lauf / Bewertung / Varianten).
function closeSaveModal(){ document.getElementById('save-modal').style.display='none'; }

function _saveEsc(s){ return (s==null?'':String(s)).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

// Baut die Liste der aktuell speicherbaren Positionen (kontextabhängig).
function _buildSaveItems(){
  const items = [];
  // 1) Projektdaten & Notizen (aktives Projekt)
  // Zwei spiegelnde Feldsätze: Tab ① (pj_*) und Projektakte-Panel (akte_*). Wenn die
  // Akte auf dasselbe Projekt zeigt, lieber deren (evtl. gerade editierte) Werte lesen —
  // und beim Speichern in BEIDE zurückschreiben, damit sie synchron bleiben.
  const pid = _activeProject && _activeProject.id;
  if (pid){
    const aktePid = (document.getElementById('akte-body')||{}).dataset ? document.getElementById('akte-body').dataset.pid : null;
    const useAkte = aktePid && aktePid === pid && document.getElementById('akte_status');
    const gv = (id)=> (document.getElementById(id)||{}).value || '';
    const status = useAkte ? gv('akte_status') : gv('pj_status');
    const tags   = useAkte ? gv('akte_tags')   : gv('pj_tags');
    const notes  = useAkte ? gv('akte_notes')  : gv('pj_notes');
    const notesShort = notes.length>70 ? notes.slice(0,70)+'…' : notes;
    items.push({ key:'projekt', label:'📋 Projektdaten & Notizen', checked:true,
      preview:`Projekt „${_saveEsc(_activeProject.name||pid)}" · Status: <b>${_saveEsc(status||'—')}</b>`
        + (tags?` · Tags: ${_saveEsc(tags)}`:'')
        + (notes?`<br><span style="color:#889">Notiz: ${_saveEsc(notesShort)}</span>`:''),
      commit: async ()=>{
        const t = tags.split(',').map(x=>x.trim()).filter(Boolean);
        const r = await fetch('/project/'+encodeURIComponent(pid)+'/meta',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({status, tags:t, notes})}).then(x=>x.json());
        if (r.error) throw new Error(r.error);
        // beide Feldsätze angleichen
        [['pj_status','akte_status',status],['pj_tags','akte_tags',tags],['pj_notes','akte_notes',notes]]
          .forEach(([a,b,v])=>{ const ea=document.getElementById(a); if(ea)ea.value=v;
                                 const eb=document.getElementById(b); if(eb)eb.value=v; });
        const m=document.getElementById('pj_meta_msg'); if(m) m.textContent='✓ gespeichert';
        const m2=document.getElementById('akte_status_msg'); if(m2) m2.textContent='✓ gespeichert';
      }});
  }
  // 2) Bewertung (Projekt mit Ergebnissen)
  if (_ratingPid){
    const g=document.getElementById('rate_gut'), b=document.getElementById('rate_schlecht');
    const cur = (g&&g.style.outline!=='none'&&g.style.outline)?'gut'
              : (b&&b.style.outline!=='none'&&b.style.outline)?'schlecht':'';
    items.push({ key:'rating', label:'⭐ Bewertung (gut/schlecht)', checked:!!cur,
      preview:`für das aktive Projekt`
        + `<div style="margin-top:5px"><select id="save_rating_sel" style="width:auto;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:5px;border-radius:3px;font-size:.8rem">`
        + `<option value="">— nicht ändern —</option>`
        + `<option value="gut"${cur==='gut'?' selected':''}>👍 gut</option>`
        + `<option value="schlecht"${cur==='schlecht'?' selected':''}>👎 schlecht</option>`
        + `</select></div>`,
      commit: async ()=>{
        const sel=document.getElementById('save_rating_sel');
        const label = sel ? sel.value : cur;
        if (!label) throw new Error('keine Bewertung gewählt');
        const comment=(document.getElementById('rate_comment')||{}).value||'';
        const r = await fetch('/project/'+encodeURIComponent(_ratingPid)+'/rating',{method:'POST',
          headers:{'Content-Type':'application/json'},
          body:JSON.stringify({label, comment:comment.trim()})}).then(x=>x.json());
        if (r.error) throw new Error(r.error);
        if (typeof _ratingHighlight==='function') _ratingHighlight(label);
        if (typeof refreshTrainingStats==='function') refreshTrainingStats();
      }});
  }
  // 3) 3D-Feld-Lauf (nur wenn ein Ergebnis im Viewer liegt)
  if (window._e3HasResult){
    const nm = (document.getElementById('e3_save_name')||{}).value || '';
    items.push({ key:'em3d', label:'🧲 3D-Feld-Lauf', checked:true,
      preview:`der aktuelle Elmer-Lauf (Feld + Kennwerte) im aktiven Projekt`
        + `<div style="margin-top:5px"><input id="save_e3_name" value="${_saveEsc(nm)}" placeholder="Name (optional)" style="width:70%;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:5px;border-radius:3px;font-size:.8rem"/></div>`,
      commit: async ()=>{
        const name=((document.getElementById('save_e3_name')||{}).value||'').trim();
        const src=document.getElementById('e3_save_name'); if(src) src.value=name;
        const r = await fetch('/em3d/save',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({name, config:_e3BuildConfig()})}).then(x=>x.json());
        if (r.error) throw new Error(r.error);
        if (typeof _e3RefreshSavedList==='function') await _e3RefreshSavedList();
      }});
  }
  // 4) Varianten-Set (nur wenn Varianten vorhanden)
  if (typeof variants!=='undefined' && variants && variants.length){
    const nm=(document.getElementById('var-set-name')||{}).value||'';
    items.push({ key:'variants', label:`🗂 Varianten-Set (${variants.length})`, checked:true,
      preview:`${variants.length} Variante(n) als Set auf dem Server`
        + `<div style="margin-top:5px"><input id="save_var_name" value="${_saveEsc(nm)}" placeholder="Set-Name (Pflicht)" style="width:70%;background:#2a2a2e;border:1px solid #444;color:#ddd;padding:5px;border-radius:3px;font-size:.8rem"/></div>`,
      commit: async ()=>{
        const name=((document.getElementById('save_var_name')||{}).value||'').trim();
        if (!name) throw new Error('Set-Name angeben');
        const src=document.getElementById('var-set-name'); if(src) src.value=name;
        const r = await fetch('/variants/save',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({name, created:new Date().toISOString(), variants})}).then(x=>x.json());
        if (r.error) throw new Error(r.error);
        if (typeof refreshVariantSets==='function') refreshVariantSets();
      }});
  }
  return items;
}

let _saveModalItems = [];
function openSaveModal(){
  _saveModalItems = _buildSaveItems();
  const box = document.getElementById('save-items');
  const msg = document.getElementById('save-modal-msg'); if (msg) msg.textContent='';
  if (!_saveModalItems.length){
    box.innerHTML = '<div style="color:#c96;padding:14px;text-align:center">'
      + 'Momentan gibt es nichts zu speichern.<br>'
      + '<span style="font-size:.78rem;color:#889">Lege ein Projekt an bzw. wähle es aus, führe eine Berechnung, einen 3D-Lauf oder Varianten aus.</span></div>';
  } else {
    box.innerHTML = _saveModalItems.map((it,i)=>
      `<label style="display:flex;gap:10px;align-items:flex-start;background:#242428;border:1px solid #35353a;border-radius:6px;padding:10px 12px;cursor:pointer">
         <input type="checkbox" id="save_chk_${i}" ${it.checked?'checked':''} style="margin-top:3px;width:16px;height:16px;flex:0 0 auto"/>
         <div style="flex:1">
           <div style="color:#eee;font-size:.86rem;font-weight:600">${it.label}</div>
           <div style="color:#aab;font-size:.78rem;margin-top:2px">${it.preview}</div>
         </div>
         <span id="save_row_${i}" style="font-size:.8rem;color:#889;flex:0 0 auto;margin-top:2px"></span>
       </label>`).join('');
  }
  document.getElementById('save-modal').style.display='block';
}

async function saveModalCommit(){
  const msg = document.getElementById('save-modal-msg');
  const btn = document.getElementById('save-commit-btn');
  if (!_saveModalItems.length){ closeSaveModal(); return; }
  btn.disabled = true; if (msg){ msg.style.color='#9c9'; msg.textContent='⏳ speichere…'; }
  let ok=0, fail=0, skip=0;
  for (let i=0;i<_saveModalItems.length;i++){
    const chk=document.getElementById('save_chk_'+i);
    const row=document.getElementById('save_row_'+i);
    if (!chk || !chk.checked){ if(row){row.style.color='#667';row.textContent='übersprungen';} skip++; continue; }
    if (row){ row.style.color='#889'; row.textContent='⏳'; }
    try { await _saveModalItems[i].commit(); if(row){row.style.color='#6c6';row.textContent='✓';} ok++; }
    catch(e){ if(row){row.style.color='#e77';row.textContent='❌ '+e.message;} fail++; }
  }
  btn.disabled = false;
  if (msg){
    msg.style.color = fail? '#e77' : '#6c6';
    msg.textContent = `${ok} gespeichert` + (fail?`, ${fail} fehlgeschlagen`:'') + (skip?`, ${skip} abgewählt`:'');
  }
}
async function refreshRagList(){
  const box=document.getElementById('rag-list');
  try{
    const r=await fetch('/rag/list').then(x=>x.json());
    const st=r.stats||{};
    document.getElementById('rag-stats').textContent =
      `${st.n_documents||0} Dokumente · ${st.n_chunks||0} Abschnitte · Modell ${st.embed_model||'?'}`;
    const docs=r.documents||[];
    if(!docs.length){ box.innerHTML='<span style="color:#777">Noch keine Dokumente hinterlegt.</span>'; return; }
    box.innerHTML=docs.map(d=>{
      const tag = d.category && d.category!=='allgemein' ? `🏷 ${escHtml(d.category)}` : '📄';
      return `<div style="display:flex;gap:8px;align-items:center;padding:5px 0;border-bottom:1px solid #2a2a2e">
        <input type="checkbox" class="rag-sel" value="${d.id}" onchange="ragUpdateSelUI()" style="flex:0 0 auto"/>
        <span style="flex:0 0 auto;font-size:.72rem;color:#9a9">${tag}</span>
        <span style="flex:1;color:#ddd">${escHtml(d.title)}</span>
        <span style="flex:0 0 auto;font-size:.72rem;color:#777">${d.n_chunks} Abschn. · ${d.created||''}</span>
        <button onclick="ragDelete('${d.id}')" style="flex:0 0 auto;background:#7a3030;width:auto;padding:3px 9px;font-size:.72rem">✕</button>
      </div>`;
    }).join('');
    ragUpdateSelUI();
  }catch(e){ box.innerHTML='<span style="color:#e57">Fehler: '+escHtml(e.message)+'</span>'; }
}
function _ragSelected(){ return [...document.querySelectorAll('.rag-sel:checked')].map(c=>c.value); }
function ragUpdateSelUI(){
  const n=_ragSelected().length, btn=document.getElementById('rag-del-sel');
  if(btn){ btn.disabled=!n; btn.style.opacity=n?'1':'.5';
    btn.textContent=n?`🗑 ${n} löschen`:'🗑 Ausgewählte löschen'; }
  const all=document.querySelectorAll('.rag-sel'), sa=document.getElementById('rag-sel-all');
  if(sa){ sa.checked=all.length>0 && n===all.length;
    sa.indeterminate = n>0 && n<all.length; }
}
function ragToggleAll(on){ document.querySelectorAll('.rag-sel').forEach(c=>c.checked=on); ragUpdateSelUI(); }
async function ragDeleteSelected(){
  const ids=_ragSelected();
  if(!ids.length) return;
  if(!confirm(`${ids.length} Dokument(e) löschen?`)) return;
  const r=await fetch('/rag/delete',{method:'POST',headers:{'Content-Type':'application/json'},
    body:JSON.stringify({ids})}).then(x=>x.json());
  const msg=document.getElementById('rag-msg');
  msg.style.color='#9c9'; msg.textContent=`✓ ${r.n_deleted||0} gelöscht`;
  document.getElementById('rag-sel-all').checked=false;
  refreshRagList();
}
async function ragAddText(){
  const text=document.getElementById('rag-text').value.trim();
  const msg=document.getElementById('rag-msg');
  if(!text){ alert('Bitte Text einfügen'); return; }
  const btn=document.getElementById('rag-add-btn'); btn.disabled=true;
  msg.style.color='#9c9'; msg.textContent='⏳ Wird eingebettet…';
  try{
    const r=await fetch('/rag/add',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({text, title:document.getElementById('rag-title').value,
        category:document.getElementById('rag-cat').value})}).then(x=>x.json());
    if(r.error){ msg.style.color='#e57'; msg.textContent='⚠ '+r.error; return; }
    msg.textContent='✓ hinzugefügt ('+r.n_chunks+' Abschnitte)';
    document.getElementById('rag-text').value=''; document.getElementById('rag-title').value='';
    refreshRagList();
  }catch(e){ msg.style.color='#e57'; msg.textContent='Fehler: '+e.message; }
  finally{ btn.disabled=false; }
}
async function ragUpload(){
  const files=document.getElementById('rag-file').files;
  const msg=document.getElementById('rag-msg');
  if(!files.length){ alert('Bitte Datei(en) wählen'); return; }
  const btn=document.getElementById('rag-up-btn'); btn.disabled=true;
  msg.style.color='#9c9'; msg.textContent=`⏳ Lese + bette ein (${files.length})…`;
  try{
    const fd=new FormData();
    for(const f of files) fd.append('file', f);
    fd.append('category', document.getElementById('rag-cat').value);
    fd.append('title', document.getElementById('rag-title').value);
    const r=await fetch('/rag/upload',{method:'POST',body:fd}).then(x=>x.json());
    if(r.error){ msg.style.color='#e57'; msg.textContent='⚠ '+r.error; return; }
    if(r.n_added!==undefined){
      msg.textContent=`✓ ${r.n_added} hinzugefügt`+((r.errors&&r.errors.length)?` · ${r.errors.length} Fehler`:'');
      if(r.errors&&r.errors.length){ msg.style.color='#e9a'; }
    } else {
      msg.textContent='✓ '+escHtml(r.title)+' ('+r.n_chunks+' Abschnitte)';
    }
    document.getElementById('rag-file').value='';
    refreshRagList();
  }catch(e){ msg.style.color='#e57'; msg.textContent='Fehler: '+e.message; }
  finally{ btn.disabled=false; }
}
async function ragDelete(id){
  if(!confirm('Dokument löschen?')) return;
  await fetch('/rag/delete/'+encodeURIComponent(id),{method:'POST'});
  refreshRagList();
}


function galleryOpen(pid) { closeProjectGallery(); loadProjectById(pid); }
async function galleryDelete(pid) {
  try {
    if (!await _projektEntsorgen(pid, pid)) return;
    _galleryProjects = _galleryProjects.filter(p => p.id !== pid);
    renderGallery(); refreshProjectList();
  } catch (e) { alert('Löschen fehlgeschlagen: ' + e.message); }
}
