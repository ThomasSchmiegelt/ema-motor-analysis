// Reiter ⚙ Getriebe und 📥 STEP-Import.
//
// Zwei Masken, die beide eine fertige Kette im Server anstossen
// (`ema_getriebe.lauf`, `ema_step_import.run_import`) und ihr Ergebnis in
// den Designer bzw. in `vehicle.getriebe` zurueckgeben.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── STEP-Import: erkennt Magnetlage, lädt sie in den Designer ───────────────────
let _importedActive = false;       // true ⇒ _dsnBuildPayload markiert imported (Geometrie nicht neu bauen)
let _importedProjectId = null;     // Projekt mit der importierten motor.FCStd (Rotor)

// ──────────────── Getriebe-Reiter (⚙) ────────────────
// Die Kette selbst liegt im Server (``ema_getriebe.lauf``) und ist dieselbe, die
// ``cae_cli.py getriebe`` fuehrt. Hier steht nur die Maske.
function _gtSync() {
  const art = document.getElementById('gt_art').value;
  const einbau = document.getElementById('gt_einbau').value;
  const zeig = (id, an) => { const e = document.getElementById(id);
                             if (e) e.style.display = an ? '' : 'none'; };
  // Stufen gibt es bei Stirnrad UND Planetensatz. Zwei Planetenstufen liegen
  // koaxial hintereinander — auch in der Hohlwelle.
  zeig('gt_stufen_wrap',   art === 'stirnrad' || art === 'planeten');
  zeig('gt_planeten_wrap', art === 'planeten');
  zeig('gt_axial_wrap',    einbau === 'in_welle');
  zeig('gt_feld_wrap',     einbau === 'in_welle');
  // Der Einbauort ist ein TOR, keine Beschriftung: nur der Planetensatz passt
  // in die Hohlwelle. Das steht hier, statt es der Server abweisen zu lassen —
  // abgewiesen wird es dort trotzdem.
  const opt = document.querySelector('#gt_einbau option[value="in_welle"]');
  if (opt) {
    opt.disabled = (art !== 'planeten');
    if (opt.disabled && einbau === 'in_welle') {
      document.getElementById('gt_einbau').value = 'achsparallel';
      _gtSync();
    }
  }
}

async function startGetriebe() {
  const msg = document.getElementById('gt_msg');
  const logEl = document.getElementById('gt_log');
  const btn = document.getElementById('gt_btn');
  const num = id => { const v = (document.getElementById(id).value || '').trim();
                      return v === '' ? null : parseFloat(v); };
  const body = {
    art:  document.getElementById('gt_art').value,
    einbau: document.getElementById('gt_einbau').value,
    stufen: num('gt_stufen') || 1,
    planeten: num('gt_planeten') || 3,
    i: num('gt_i'), n_ab: num('gt_nab'),
    moment: num('gt_moment'), drehzahl: num('gt_drehzahl'),
    werkstoff: document.getElementById('gt_werkstoff').value,
    verzahnung: document.getElementById('gt_verzahnung').value,
    schraegung: num('gt_schraegung') || 0,
    bauraum_axial: num('gt_axial') || 0,
    ohne_feld: !document.getElementById('gt_feld').checked,
    cad: document.getElementById('gt_cad').checked,
    uebernehmen: document.getElementById('gt_uebernehmen').checked,
  };
  if (body.n_ab) body.i = null;          // Abtriebsdrehzahl schlaegt i
  if (window._activeProject && window._activeProject.id)
    body.project_id = window._activeProject.id;
  btn.disabled = true; msg.style.color = '#9c9'; msg.textContent = '⏳ Rechne…';
  logEl.style.display = 'block'; logEl.textContent = '';
  try {
    const antw = await fetch('/getriebe', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(body)});
    const r = await _gtJson(antw);
    if (r.error) { msg.style.color = '#e57'; msg.innerHTML = '⚠ ' + escHtml(r.error);
                   btn.disabled = false; return; }
    _pollGetriebe();
  } catch (e) {
    msg.style.color = '#e57'; msg.innerHTML = escHtml('Fehler: ' + e.message);
    btn.disabled = false;
  }
}

// Eine Antwort lesen, die vielleicht gar kein JSON ist.
//
// Der Grund ist gemessen und keine Vorsicht: `ema.html` wird bei JEDEM Aufruf
// frisch von der Platte gelesen, die Routen dagegen stehen fest, sobald der
// Server gestartet ist. Nach einer Änderung zeigt der Browser also den neuen
// Reiter, während der laufende Server die neue Route noch gar nicht kennt — er
// antwortet mit seiner HTML-404-Seite, und `.json()` scheitert daran mit
// „JSON.parse: unexpected character at line 1 column 1". Diese Meldung sagt
// über die Ursache nichts und schickt einen in den Code statt an den Server.
async function _gtJson(antw) {
  const typ = antw.headers.get('content-type') || '';
  if (typ.includes('application/json')) return await antw.json();
  if (antw.status === 404)
    throw new Error('Diese Route kennt der laufende Server nicht (404). Er ' +
      'läuft vermutlich noch mit dem Code von vor der Änderung — die Seite ' +
      'wird bei jedem Aufruf neu von der Platte gelesen, die Routen nicht. ' +
      'Server neu starten: ./start.sh');
  throw new Error('Der Server hat kein JSON geschickt (HTTP ' + antw.status +
                  ', ' + (typ || 'ohne Typangabe') + ').');
}

async function _pollGetriebe() {
  const msg = document.getElementById('gt_msg');
  const logEl = document.getElementById('gt_log');
  const btn = document.getElementById('gt_btn');
  try {
    const s = await _gtJson(await fetch('/getriebe/status'));
    if (Array.isArray(s.log)) { logEl.textContent = s.log.join('\n');
                                logEl.scrollTop = logEl.scrollHeight; }
    if (s.status === 'done') { _renderGetriebe(s.result); btn.disabled = false; return; }
    if (s.status === 'error') { msg.style.color = '#e57';
                                msg.textContent = '⚠ ' + (s.error || 'fehlgeschlagen');
                                btn.disabled = false; return; }
  } catch (e) {
    // Ein 404 geht nicht weg, indem man ihn wiederholt — der Server kennt die
    // Route schlicht nicht. Alles andere (ein Aussetzer im Netz) darf weiter.
    if (String(e.message).includes('404')) {
      msg.style.color = '#e57'; msg.innerHTML = escHtml('⚠ ' + e.message);
      btn.disabled = false; return;
    }
  }
  setTimeout(_pollGetriebe, 800);
}

// Die ausgelegte Verzahnung, solange die Seite offen ist. Sie gehoert in den
// Payload, hat aber kein Formularfeld: eine Verzahnung ist kein Zahlenfeld.
let _vehGetriebe = null;

function _vehGetriebeAnzeigen() {
  const el = document.getElementById('veh_getriebe_note');
  if (!el) return;
  if (_vehGetriebe) {
    const g = _vehGetriebe;
    el.innerHTML = '<span style="color:#6c6">⚙ ausgelegte Verzahnung aktiv</span> — ' +
      'η(T,&nbsp;n) statt fester 0,95' +
      (g.art ? ' · ' + escHtml(String(g.art)) : '') +
      (g.n_stufen ? ' · ' + escHtml(String(g.n_stufen)) + ' Stufen' : '') +
      (g.i_ist ? ' · i = ' + escHtml(Number(g.i_ist).toFixed(2)) : '');
  } else {
    el.innerHTML = 'skalare Übersetzung, festes η — im Reiter <b>⚙ Getriebe</b> ' +
      'auslegen und übernehmen, dann rechnet der Zyklus mit η(T,&nbsp;n).';
  }
}

function _renderGetriebe(res) {
  const msg = document.getElementById('gt_msg');
  const wrap = document.getElementById('gt_ergebnis_wrap');
  const urteil = document.getElementById('gt_urteil');
  const bild = document.getElementById('gt_bild');
  if (!res) { msg.style.color = '#e57'; msg.textContent = '⚠ kein Ergebnis'; return; }
  wrap.hidden = false;
  document.getElementById('gt_text').textContent = res.text || '';
  if (!res.ok) {
    msg.style.color = '#e57'; msg.textContent = '⚠ ' + (res.grund || 'nicht auslegbar');
    urteil.innerHTML = '';
    bild.style.display = 'none';
    return;
  }
  msg.style.color = '#6c6'; msg.textContent = '✓ gerechnet und im Projekt abgelegt.';
  // „Traegt nicht" und „passt nicht" sind ZWEIERLEI und stehen deshalb getrennt:
  // eine Verzahnung, die traegt und nur nicht in die Bohrung geht, braucht mehr
  // PLATZ, nicht mehr Modul.
  const zeilen = [];
  if (res.haelt === false)
    zeilen.push('<span style="color:#e57">⚠ Die VERZAHNUNG trägt nicht</span> — ' +
                'mehr Modul, mehr Breite oder ein besserer Werkstoff.');
  else if (res.haelt === null || res.haelt === undefined)
    zeilen.push('<span style="color:#ca8">Für diese Bauart wird keine ' +
                'Zahnfußtragfähigkeit gerechnet.</span>');
  else
    zeilen.push('<span style="color:#6c6">✓ Die Verzahnung trägt.</span>');
  if (res.in_welle) {
    const iw = res.in_welle;
    zeilen.push(iw.passt
      ? '<span style="color:#6c6">✓ Der Satz passt in die Welle.</span>'
      : '<span style="color:#e57">⚠ Der Satz PASST NICHT an den Einbauort</span> — ' +
        'was fehlt, ist Platz: größere Bohrung, kleinere Übersetzung oder ein ' +
        'anderer Einbau.');
    if (!iw.magnetisch_geprueft)
      zeilen.push('<span style="color:#ca8">Die magnetisch zulässige Bohrung ' +
                  'wurde NICHT geprüft</span> — „passt in die gezeichnete ' +
                  'Bohrung" ist nicht „zulässig".');
  }
  if (res.werkstoff_beleg === 'annahme')
    zeilen.push('<span style="color:#ca8">Die Festigkeitskennwerte sind eine ' +
                'ANNAHME</span> (Größenordnung der Werkstoffklasse), keine ' +
                'zitierte Messung — jede Sicherheit oben ist eine Größenordnung.');
  if (res.uebernommen === 'ja') {
    // Genau das, was cae_cli._getriebe_uebernehmen nach meta.json schreibt: das
    // Ergebnis selbst, ohne die drei reinen Anzeigeschluessel.
    const g = Object.assign({}, res);
    delete g.text; delete g.bestanden; delete g.uebernommen;
    _vehGetriebe = g;
    if (res.i_ist) _setField('veh_gear', Math.round(res.i_ist * 1e4) / 1e4);
    _vehGetriebeAnzeigen();
  }
  if (res.uebernommen)
    zeilen.push(res.uebernommen === 'ja'
      ? '<span style="color:#6c6">✓ Übernommen</span> — der nächste Analyselauf ' +
        'dieses Projekts rechnet mit dieser Übersetzung und mit η(T,&nbsp;n).'
      : '<span style="color:#ca8">Nicht übernommen</span> — ' +
        escHtml(res.uebernommen.replace(/^nein:\s*/, '')));
  const cad = res.cad || {};
  if (cad.zeichner === 'ersatz')
    zeilen.push('<span style="color:#ca8">Die Zeichnung zeigt ERSATZKÖRPER ohne ' +
                'Zähne</span> (FCGear fehlte) — sie belegt Lage und Platzbedarf, ' +
                'nicht die Zahnform.');
  urteil.innerHTML = zeilen.map(z => '<div>' + z + '</div>').join('');
  // Das Bild liegt im Projekt und wird ueber den vorhandenen Diagrammweg geholt
  // (``/chart/<name>`` loest gegen das aktive Projekt auf) -- mit Zeitstempel,
  // sonst zeigt der Browser das Bild der vorigen Auslegung.
  if (res.bild) {
    bild.src = '/chart/getriebe.png?t=' + Date.now();
    bild.style.display = '';
  } else {
    bild.style.display = 'none';
  }
}

async function startStepImport() {
  const fileEl = document.getElementById('import-file');
  const msg = document.getElementById('import-msg');
  const logEl = document.getElementById('import-log');
  const btn = document.getElementById('import-btn');
  if (!fileEl.files.length) { msg.style.color = '#e57'; msg.textContent = '⚠ Bitte eine STEP-Datei wählen.'; return; }
  btn.disabled = true; msg.style.color = '#9c9'; msg.textContent = '⏳ Lade hoch & erkenne Magnetlage…';
  logEl.style.display = 'block'; logEl.textContent = '';
  try {
    const fd = new FormData();
    fd.append('file', fileEl.files[0]);
    const r = await fetch('/import_step', { method: 'POST', body: fd }).then(x => x.json());
    if (r.error) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; btn.disabled = false; return; }
    _importedProjectId = r.project_id || null;
    _pollImport();
  } catch (e) {
    msg.style.color = '#e57'; msg.textContent = 'Fehler: ' + e.message; btn.disabled = false;
  }
}

async function _pollImport() {
  const msg = document.getElementById('import-msg');
  const logEl = document.getElementById('import-log');
  const btn = document.getElementById('import-btn');
  try {
    const s = await fetch('/import_step/status').then(x => x.json());
    if (Array.isArray(s.log)) logEl.textContent = s.log.join('\n');
    logEl.scrollTop = logEl.scrollHeight;
    if (s.status === 'done') { _onImportDone(s); btn.disabled = false; return; }
    if (s.status === 'error') { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (s.error || 'Import fehlgeschlagen'); btn.disabled = false; return; }
  } catch (e) { /* weiter pollen */ }
  setTimeout(_pollImport, 1000);
}

function _onImportDone(s) {
  const res = s.result;
  const msg = document.getElementById('import-msg');
  if (!res) { msg.style.color = '#e57'; msg.textContent = '⚠ Kein Ergebnis vom Import.'; return; }
  _importedActive = true;
  _importedProjectId = res.project_id || _importedProjectId;
  // erkannte Geometrie + Magnete in den Designer laden (params-Form von applyDesignToCanvas)
  applyDesignToCanvas({ params: res.params || {}, magnets: res.magnets || [],
                        barriers: res.barriers || [], begruendung: res.begruendung || '' });
  const warns = (res.warnings || []).map(w => '⚠ ' + w).join('\n');
  msg.style.color = '#6c6';
  msg.innerHTML = `✓ Import erkannt: ${res.n_magnet_bodies || 0} Magnetkörper · ${res.poles || '?'} Pole. `
    + `Jetzt im <b>Designer</b> prüfen/korrigieren und „⚙ CAD + Berechnung erzeugen" starten.`
    + (warns ? `<pre style="color:#e9a;margin-top:6px;white-space:pre-wrap;font-size:.72rem">${warns}</pre>` : '');
  switchTab('designer');
}
