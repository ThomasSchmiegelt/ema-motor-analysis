// Der Payload und alles, was ihn startet: `buildPayload`/`applyPayload`,
// Auto-Speichern, Abzweige, die Bruecke zu den Agentenkoepfen, Umrichter,
// Axialmasse, Analyse/CAD-Vorschau/Smoke-Test und die Torvorschlaege.
//
// `buildPayload()` ist die EINE Stelle, an der aus dem Formular eine
// Anfrage wird -- Einzellauf, Varianten, Parametertabelle und Designer
// gehen alle hier hindurch.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// Der Zeitgeber des Statuspolls. Er stand frueher im Block „Analysis API“
// von ema.html; gelesen wird er hier (`pollStatus`) und in `nebenreiter.js`
// (`_reattachJobs`, laeuft beim `load`-Ereignis, also nach allen Skripten).
let _pollTimer = null;

// Assemble the exact /analyse request body from the current form + GEOM.
// Reused by startAnalysis() and by the variant manager ("save current config").
// ── Auto-Speichern der Eingaben (localStorage) ───────────────────────────────
// Schützt vor versehentlichem Schließen/Neuladen des Browsers: die komplette
// Formular-Konfiguration wird bei jeder Änderung (entprellt) lokal gesichert und
// beim nächsten Öffnen automatisch wiederhergestellt. Fertige Analysen liegen
// ohnehin als Projekt unter ~/cae_projekte und sind über den Projekt-Browser
// erreichbar — hier geht es nur um die noch nicht gerechnete Eingabe-Maske.
const _FORM_KEY = 'ema_form_v1';
let _saveTimer = null;
function saveFormState() {
  buildPayload().then(p => {
    delete p.cycle_csv;            // einmalig (File), kann nicht restauriert werden
    const rec = { t: Date.now(), payload: p };
    try { localStorage.setItem(_FORM_KEY, JSON.stringify(rec)); }     // lokal (sofort)
    catch (e) { /* Quota/Privatmodus — still ignorieren */ }
    try {                                                             // serverseitig (geräteübergreifend)
      fetch('/session/save', { method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(rec), keepalive: true }).catch(() => {});
    } catch (e) {}
  }).catch(() => {});
}
function _scheduleSave() { clearTimeout(_saveTimer); _saveTimer = setTimeout(saveFormState, 600); }
async function restoreFormState() {
  let local = null;
  try { const raw = localStorage.getItem(_FORM_KEY); if (raw) local = JSON.parse(raw); } catch (e) {}
  let server = null;
  try { const r = await fetch('/session/load').then(x => x.json()); if (r && r.payload) server = r; }
  catch (e) {}
  // Neuere der beiden Sitzungen gewinnt (lokal vs. Server).
  let best = (local && local.payload) ? local : null;
  if (server && (!best || (server.t || 0) > (best.t || 0))) best = server;
  if (best && best.payload) { applyPayload(best.payload); return true; }
  return false;
}
function clearFormState() {
  try { localStorage.removeItem(_FORM_KEY); } catch (e) {}
  try { fetch('/session/clear', { method: 'POST' }).catch(() => {}); } catch (e) {}
}
async function setupAutosave() {
  document.addEventListener('input',  _scheduleSave, true);
  document.addEventListener('change', _scheduleSave, true);
  window.addEventListener('beforeunload', saveFormState);   // best effort beim Schließen
  if ((await restoreFormState()) && typeof _toast === 'function') _toast('Eingaben wiederhergestellt');
}

// ══════════ Abzweige und der Weg zurueck ══════════
//
// Die Evolution der Projektakte war eine Einbahnstrasse: jede Stufe haelt nur
// die GEAENDERTEN Werte (gedeckelt), den vollen Payload gibt es einmal — den
// letzten. Wer einem Abzweig folgte und feststellte, dass er nicht traegt,
// hatte keinen Weg zurueck ausser von Hand. ``ema_projekt`` legt deshalb je
// Knoten einen Schnappschuss ab; hier sind die zwei Knoepfe dazu.
//
// Zurueckgehen LOESCHT die Stufen dazwischen NICHT: dass ein Zweig probiert
// wurde und sich nicht bewaehrt hat, ist selbst eine Auskunft.
async function knotenSetzen() {
  const pid = window._activeProject && window._activeProject.id;
  const txt = document.getElementById('brk-text');
  if (!pid) { if (txt) txt.textContent = '⚠ Erst ein Projekt wählen (Tab ① Projekt).'; return; }
  const label = prompt('Wofür steht dieser Abzweig?\n' +
                       '(z. B. „vor dem Versuch mit 8 Polen")', '');
  if (label === null) return;
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/knoten',
      {method: 'POST', headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({label})}).then(x => x.json());
    if (txt) txt.innerHTML = r && r.ok
      ? '⑂ <b>Abzweig gesetzt</b> — von hier kommst du mit „↩ Zurück zu …" ' +
        'wieder her.'
      : '⚠ ' + escHtml((r && r.grund) || 'nicht gesetzt');
    if (r && r.ok) knotenListe();
  } catch (e) { if (txt) txt.textContent = 'Fehler: ' + e.message; }
}

async function knotenListe() {
  const pid = window._activeProject && window._activeProject.id;
  const box = document.getElementById('brk-knoten');
  if (!box) return;
  if (!box.hidden) { box.hidden = true; return; }        // zweiter Klick schliesst
  if (!pid) return;
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/knoten')
                      .then(x => x.json());
    const kn = (r && r.knoten) || [];
    if (!kn.length) {
      box.innerHTML = '<span style="color:#9aa">Noch keine Rückkehrpunkte. ' +
        'Jeder gerechnete Lauf legt einen an; „⑂ Abzweig" setzt einen von Hand.</span>';
    } else {
      box.innerHTML = '<div style="font-size:.78rem;color:#9aa;margin-bottom:6px">' +
        'Zurück zu einem Stand — die Stufen dazwischen bleiben stehen:</div>' +
        kn.map(k => {
          const wann = (k.ts || '').slice(0, 16).replace('T', ' ');
          const wie = k.automatisch ? '' :
            ' <span style="color:#b18aff">⑂ von Hand</span>';
          return '<div style="display:flex;gap:9px;align-items:center;' +
            'padding:3px 0;border-top:1px solid #26262e">' +
            '<button class="brk-btn" style="background:#455" onclick="knotenZurueck(\'' +
            escHtml(k.marke) + '\')">↩</button>' +
            '<span style="flex:1;min-width:0"><b>' +
            escHtml(k.label || k.action || 'Stand') + '</b>' + wie +
            ' <span style="color:#889">· ' + escHtml(wann) + '</span>' +
            (k.note ? '<br><span style="color:#889;font-size:.75rem">' +
                      escHtml(k.note) + '</span>' : '') + '</span></div>';
        }).join('');
    }
    box.hidden = false;
  } catch (e) { /* stumm */ }
}

async function knotenZurueck(marke) {
  const pid = window._activeProject && window._activeProject.id;
  const txt = document.getElementById('brk-text');
  if (!pid || !marke) return;
  if (!confirm('Zu diesem Stand zurückgehen?\n\n' +
               'Der aktuelle Stand wird vorher automatisch als Rückkehrpunkt ' +
               'gesichert, und die Stufen dazwischen bleiben in der Projektakte ' +
               'stehen — gelöscht wird nichts.')) return;
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/zurueck',
      {method: 'POST', headers: {'Content-Type': 'application/json'},
       body: JSON.stringify({marke})}).then(x => x.json());
    if (!r || !r.ok) {
      if (txt) txt.innerHTML = '⚠ ' + escHtml((r && r.grund) || 'nicht möglich');
      return;
    }
    // Der Payload des Projekts ist ein anderer — das Formular zieht nach.
    _brkBeruehrt = false;
    await brueckeHolen(true);
    if (txt) txt.innerHTML = '↩ <b>Zurück auf „' +
      escHtml(r.label || r.marke) + '"</b> — ' + escHtml(r.hinweis || '');
    const box = document.getElementById('brk-knoten');
    if (box) box.hidden = true;
  } catch (e) { if (txt) txt.textContent = 'Fehler: ' + e.message; }
}

// ══════════ Bruecke: Agentenkoepfe <-> Geometrie-Reiter ══════════
//
// Beide Seiten arbeiten laengst am selben Projekt -- der Agent ueber
// ``cae_cli.py --from-project``, das Formular ueber ``/project/<id>/template``.
// Was fehlte, ist dass die eine Seite merkt, wenn die andere etwas geaendert
// hat: der Agent schreibt ``meta.json``, und der Reiter erfuhr davon erst, wenn
// jemand von Hand „Als Vorlage verwenden" drueckte. Zwei Leute an einem Werkstueck,
// von denen einer nicht hinsieht.
//
// Erkannt wird die Aenderung an der PAYLOAD-MARKE und nicht an der Dateizeit:
// ``meta.json`` wird auch neu geschrieben, wenn nur eine Notiz dazukam, und dann
// wuerde die Bruecke ein Formular ueberschreiben, in dem sich nichts geaendert hat.
//
// ``automatisch folgen`` gilt nur, solange das Formular UNBERUEHRT ist. Wer
// gerade selbst tippt, bekommt keinen fremden Wert unter der Hand -- dann wird
// gefragt. Das ist der einzige Punkt, an dem „automatisch" gefaehrlich waere.
let _brkMarke = null;        // zuletzt gesehene Marke des aktiven Projekts
let _brkBeruehrt = false;    // hat der Mensch seit dem letzten Abgleich getippt?
let _brkTimer = null;
let _brkOffen = null;        // Marke, die zur Uebernahme ansteht

function _brkAutoUm() { _brkZeichnen(_brkLetzterStand); }

function brueckeBeruehrt() {
  // Nur EINE Meldung je Abgleich -- der Zaehler haengt an jedem Tastendruck.
  if (!_brkBeruehrt) { _brkBeruehrt = true; _brkZeichnen(_brkLetzterStand); }
}

let _brkLetzterStand = null;

async function _brkAbfragen() {
  const pid = window._activeProject && window._activeProject.id;
  const bar = document.getElementById('brk-bar');
  if (!bar) return;
  if (!pid) { bar.hidden = true; return; }
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/stand');
    if (!r.ok) { bar.hidden = true; return; }
    const st = await r.json();
    if (!st.ok) { bar.hidden = true; return; }
    bar.hidden = false;
    _brkLetzterStand = st;
    if (_brkMarke === null) { _brkMarke = st.payload_marke; }   // erster Blick
    else if (st.payload_marke !== _brkMarke) {
      _brkOffen = st.payload_marke;
      const auto = document.getElementById('brk-auto');
      if (auto && auto.checked && !_brkBeruehrt) { await brueckeHolen(true); return; }
    }
    _brkZeichnen(st);
  } catch (e) { /* Netzaussetzer: beim naechsten Mal wieder */ }
}

function _brkZeichnen(st) {
  if (!st) return;
  const lampe = document.getElementById('brk-lampe');
  const txt = document.getElementById('brk-text');
  const hol = document.getElementById('brk-hol');
  const bar = document.getElementById('brk-bar');
  const koepfe = st.koepfe || [];
  const neu = !!_brkOffen;
  bar.classList.toggle('neu', neu);
  lampe.className = 'brk-punkt' + (neu ? ' neu' : (koepfe.length ? ' an' : ''));
  hol.hidden = !neu;
  const wer = koepfe.length
    ? koepfe.map(k => k.kopf.toUpperCase() + (k.beschaeftigt ? ' (arbeitet)' : ''))
            .join(', ')
    : null;
  let m;
  if (neu) {
    const l = st.letzte || {};
    const feld = (l.geaendert || []).slice(0, 4).join(', ');
    m = '<b>Die Auslegung dieses Projekts hat sich geändert</b>'
      + (l.action ? ' — ' + escHtml(l.action) : '')
      + (feld ? ' (' + escHtml(feld) + (l.n_geaendert > 4 ? ' …' : '') + ')' : '')
      + (_brkBeruehrt
          ? ' · <span style="color:#e6a23c">dein Formular ist geändert, es wird '
            + 'nichts überschrieben</span>'
          : '');
  } else if (wer) {
    m = 'Verbunden mit ' + escHtml(wer) + ' auf <code>' + escHtml(st.id) + '</code>'
      + ' · Änderungen des Agenten kommen hier an.';
  } else {
    m = 'Projekt <code>' + escHtml(st.id) + '</code> · kein Agentenkopf daran. '
      + 'Änderungen aus dem Terminal (<code>cae_cli.py</code>) kommen trotzdem an.';
  }
  txt.innerHTML = m;
}

async function brueckeHolen(still) {
  const pid = window._activeProject && window._activeProject.id;
  if (!pid) return;
  try {
    const tpl = await fetch('/project/' + encodeURIComponent(pid) + '/template')
                        .then(x => x.json());
    if (tpl && tpl.payload) {
      applyPayload(tpl.payload);
      _brkMarke = _brkOffen || _brkMarke;
      _brkOffen = null;
      _brkBeruehrt = false;
      const txt = document.getElementById('brk-text');
      if (txt) txt.innerHTML = (still ? '⤓ <b>Automatisch übernommen</b>'
                                      : '⤓ <b>Übernommen</b>')
        + ' — das Formular zeigt jetzt den Stand des Projekts.';
      const bar = document.getElementById('brk-bar');
      if (bar) bar.classList.remove('neu');
      const hol = document.getElementById('brk-hol');
      if (hol) hol.hidden = true;
      const lampe = document.getElementById('brk-lampe');
      if (lampe) lampe.className = 'brk-punkt an';
    }
  } catch (e) { /* stumm: beim naechsten Abgleich wieder */ }
}

async function brueckeGeben() {
  // Die andere Richtung. ``/agent/vorgabe`` gab es schon — aber nur als Knopf
  // im Designer. Was im Geometrie-Reiter steht, kam beim Agenten nur an, wenn
  // jemand vorher rechnete; eine Uebergabe darf Sekunden dauern und keine
  // Stunden.
  const pid = window._activeProject && window._activeProject.id;
  const txt = document.getElementById('brk-text');
  if (!pid) { if (txt) txt.textContent = '⚠ Erst ein Projekt wählen (Tab ① Projekt).'; return; }
  try {
    const payload = await buildPayload();
    const r = await fetch('/agent/vorgabe', {method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({payload, projekt: pid})}).then(x => x.json());
    if (txt) txt.innerHTML = r && r.ok
      ? '⤒ <b>An den Agenten gegeben</b> — steht als Vorgabe in <code>'
        + escHtml(pid) + '</code>. Ein laufender Kopf sieht sie beim nächsten '
        + 'Steckbrief; ein neuer bekommt sie im stehenden Auftrag.'
      : '⚠ ' + escHtml((r && r.grund) || 'Übergabe fehlgeschlagen');
    // Der eigene Stand ist damit der Stand des Projekts.
    const st = await fetch('/project/' + encodeURIComponent(pid) + '/stand')
                       .then(x => x.json()).catch(() => null);
    if (st && st.ok) { _brkMarke = st.payload_marke; _brkOffen = null; _brkBeruehrt = false; }
  } catch (e) {
    if (txt) txt.textContent = 'Fehler: ' + e.message;
  }
}

function brueckeStart() {
  if (_brkTimer) return;
  const panel = document.getElementById('panel-geo');
  if (panel && !panel.dataset.brkGebunden) {
    panel.addEventListener('input', brueckeBeruehrt);
    panel.addEventListener('change', brueckeBeruehrt);
    panel.dataset.brkGebunden = '1';
  }
  _brkAbfragen();
  _brkTimer = setInterval(_brkAbfragen, 4000);
}
function brueckeStopp() {
  if (_brkTimer) { clearInterval(_brkTimer); _brkTimer = null; }
}
// Ein Projektwechsel setzt die Bruecke zurueck -- die Marke des alten Projekts
// haette am neuen keine Bedeutung und meldete sofort eine „Aenderung".
function brueckeNeuesProjekt() {
  _brkMarke = null; _brkOffen = null; _brkBeruehrt = false; _brkLetzterStand = null;
  if (_brkTimer) _brkAbfragen();
}

// Die Leistungselektronik pruefen. Gerechnet wird auf dem SERVER
// (`ema_umrichter`), nicht hier: die Teilbarkeitsregel (slots % 3k, ganze
// Polzahl je Sektor, q >= k fuer den Versatz) haengt an der Wicklung, und eine
// zweite Fassung davon in JavaScript waere genau die Abschrift, die beim ersten
// geaenderten Nenner auseinanderlaeuft — derselbe Grund, aus dem `magnetLegs`
// per Test gegen die Python-Fassung genagelt wird.
async function pruefeUmrichter() {
  const out = document.getElementById('umrichter_out');
  const btn = document.getElementById('btn_umrichter');
  if (!out) return;
  out.innerHTML = '<span style="color:#888">… rechnet</span>';
  if (btn) btn.disabled = true;
  try {
    const payload = await buildPayload();
    const r = await fetch('/umrichter', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({payload, ausfall: true})
    });
    const d = await r.json();
    if (!r.ok || d.error) { out.innerHTML = '<span style="color:#e57373">' + escHtml(d.error || ('HTTP ' + r.status)) + '</span>'; return; }
    const w = d.wickelbar || {};
    let h = '<div style="color:#ddd;line-height:1.55">';
    h += '<b>' + d.k + ' Modul' + (d.k !== 1 ? 'e' : '') + '</b> — ' + escHtml(d.topologie_text) + '<br>';
    h += 'je Modul ' + d.v_modul_V.toFixed(0) + ' V · ' + d.i_modul_A.toFixed(0) + ' A = ' + d.S_modul_kVA.toFixed(1) + ' kVA';
    h += ' &nbsp;|&nbsp; zusammen ' + d.S_gesamt_kVA.toFixed(1) + ' kVA<br>';
    h += 'die Maschine sieht <b>' + d.v_maschine_V.toFixed(0) + ' V · ' + d.i_maschine_A.toFixed(0) + ' A</b>';
    h += ' <span style="color:#888">(k Module wirken wie EIN Umrichter mit k·V bei gleichem Strom)</span><br>';
    h += '<span style="color:#888">' + w.slots + ' Nuten, ' + w.pole + ' Pole, q = ' + (w.q != null ? w.q.toFixed(2) : '?') + '</span>';
    h += '</div>';
    for (const b of (w.befunde || [])) {
      const hart = !!b.hart;
      h += '<div style="margin-top:6px;color:' + (hart ? '#e57373' : '#ffb74d') + '">'
         + (hart ? '✗ ' : '⚠ ') + escHtml(b.text) + '</div>';
    }
    if (w.ok && !(w.befunde || []).length && d.k > 1)
      h += '<div style="margin-top:6px;color:#81c784">✓ teilbar</div>';
    if (d.warnung) h += '<div style="margin-top:6px;color:#ffb74d">⚠ ' + escHtml(d.warnung) + '</div>';
    const a = d.ausfall || {};
    if (a.moeglich) {
      h += '<div style="margin-top:8px;color:#ddd">Ausfall eines Moduls (' + a.rest_module + ' von ' + a.k
         + '): <b>' + a.P_voll_kW.toFixed(0) + ' kW → ' + a.P_rest_kW.toFixed(0) + ' kW</b>'
         + (a.P_anteil != null ? ' (' + (a.P_anteil * 100).toFixed(0) + ' %)' : '') + '</div>';
    } else if (a.grund) {
      h += '<div style="margin-top:8px;color:#888">Ausfall: ' + escHtml(a.grund) + '</div>';
    }
    if ((d.bilder || []).length)
      h += '<div style="margin-top:6px;color:#888">Bilder in charts/: ' + d.bilder.map(esc).join(', ') + '</div>';
    out.innerHTML = h;
  } catch (e) {
    out.innerHTML = '<span style="color:#e57373">' + escHtml(String(e)) + '</span>';
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* ⊙ Die gezeichnete Scheibe aus dem Reiter ⊙ Axialfluss holen.
 *
 * Der Reiter ist ein <iframe> auf `/axialfluss/` — gleicher Ursprung, also ist
 * `werteLesen()` dort unmittelbar aufrufbar. Gelesen wird das FORMULAR der
 * Seite und nicht ihr gerechnetes `P()`: `P()` halbiert Radien und rechnet
 * Winkel in Bogenmaß um, und zwei Umrechnungen für dieselbe Größe sind eine zu
 * viel (derselbe Grund steht dort über `werteLesen`).
 *
 * Ist der Reiter noch nicht geladen, wird er hier angestoßen und es gibt
 * `null` zurück — dann gelten die Maße, die im Projekt stehen, und was dort
 * fehlt, ergänzt der Server benannt (`ema_fluss.axial_ergaenzen`). Nichts wird
 * hier gerechnet oder geraten.
 */
/* ⊙ Elementkennung ↔ Schemaschlüssel der beiden Haltungs-Grenzwerte.
 * EINE Tabelle für Payload UND `applyPayload` — dasselbe Muster wie
 * `_ART_FELDER`, und aus demselben Grund: eine zweite Aufzählung war schon
 * einmal die Stelle, an der ein Feld gesetzt, aber nie wiederhergestellt
 * wurde (`struct_solver`). */
const _AX_HALT_FELDER = {ax_klebe_zul: 'axialKlebeZulMpa',
                         ax_bandage_zul: 'axialBandageZulMpa'};
let _axQuelle = null;          // woher die letzten axialen Maße kamen
async function _axialGeomHolen() {
  const f = document.getElementById('axial-rahmen');
  let werte = null;
  try {
    const w = f && f.contentWindow;
    if (w && typeof w.werteLesen === 'function') {
      const v = w.werteLesen();
      if (v && Object.keys(v).length) werte = v;
    }
  } catch (e) { werte = null; }      // Rahmen noch leer
  if (!werte) {
    if (typeof axActivate === 'function') axActivate();   // laden, fürs nächste Mal
    _axQuelle = 'projekt';
    return null;
  }
  try {
    const r = await fetch('/axialfluss/geom', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ werte }) });
    if (!r.ok) { _axQuelle = 'projekt'; return null; }
    const d = await r.json();
    if (!d.ok) { _axQuelle = 'projekt'; return null; }
    _axQuelle = 'reiter';
    return d;
  } catch (e) { _axQuelle = 'projekt'; return null; }
}

async function buildPayload() {
  const payload = {
    // Die Leistungselektronik gehoert in `geom`, weil `ema_analysis.umrichter`
    // -- die EINE Quelle der Grenzen -- nur `geom` bekommt. Ein zweiter Ort
    // waere die Stelle, an der Formular und Rechnung auseinanderlaufen.
    geom:             { ...GEOM,
                        inverterVdc:       +(document.getElementById('inv_vdc')?.value || 800),
                        inverterImax:      +(document.getElementById('inv_imax')?.value || 800),
                        inverterAnzahl:    +(document.getElementById('inv_anzahl')?.value || 1),
                        inverterTopologie: document.getElementById('inv_topologie')?.value || 'verschachtelt',
                        umrichterBezug:    document.getElementById('inv_bezug')?.value || 'einwindung',
                        // Ohne diese Zeile rechnete der Browser IMMER eine PSM:
                        // `machineType` stand nur im Schema und kam nie mit.
                        machineType:       document.getElementById('machine_art')?.value
                                           || GEOM.machineType || 'pmsm',
                        // Derselbe Grund wie bei `machineType` eine Zeile
                        // darueber: aus GEOM allein kaeme er auch aus einer
                        // frueheren Sitzung ueber localStorage zurueck, und
                        // dann rechnete der Knopf eine Scheibe, die niemand
                        // gewaehlt hat -- oder umgekehrt.
                        fluxPath:          document.getElementById('flux_path')?.value
                                           || GEOM.fluxPath || 'radial' },
    project_name:     document.getElementById('project_name').value || '',
    rotor_lam:        document.getElementById('sel_rotor_lam').value,
    stator_lam:       document.getElementById('sel_stator_lam').value,
    hairpin_mat:      document.getElementById('sel_hairpin').value,
    magnet:           document.getElementById('sel_magnet').value,
    axial_len:        +document.getElementById('dim_axial').value,
    n_frames:         +document.getElementById('n_frames').value,
    fdm_resolution:   +document.getElementById('fdm_resolution').value,
    // ⊙ Nur beim Axialfluss gelesen (`ema_axial_fdm.felder`,
    // `ema_em3d._run_em3d_axial`); radial ignoriert ihn.
    axial_schnitte:   +(document.getElementById('axial_schnitte')?.value || 5),
    frame_resolution: +document.getElementById('frame_resolution').value,
    field_bmax:       +(document.getElementById('field_bmax')?.value || 0),
    struct_mesh_mm:   +document.getElementById('struct_mesh_mm').value,
    struct_solver:    document.getElementById('struct_solver')?.value || 'freecad',
    struct_img_px:    +document.getElementById('struct_img_px').value,
    struct_video:     document.getElementById('struct_video').checked,
    struct_frames:    +document.getElementById('struct_frames').value,
    rpm_from:         +document.getElementById('rpm_from').value,
    rpm_to:           +document.getElementById('rpm_to').value,
    rpm_step:         +document.getElementById('rpm_step').value,
    load_nm:          +document.getElementById('sim_load').value,
    cooling:          document.getElementById('sel_cooling').value,
    T_ambient:        +document.getElementById('T_ambient').value,
    cycle:            document.getElementById('sel_cycle').value === 'both' ? 'both' : document.getElementById('sel_cycle').value,
    cycle_anhaenger:  document.getElementById('sel_cycle').value === 'anhaenger' || document.getElementById('sel_cycle').value === 'both',
    vehicle: {
      mass_kg:    +document.getElementById('veh_mass').value,
      cwA_m2:     +document.getElementById('veh_cwA').value,
      cr:         +document.getElementById('veh_cr').value,
      r_wheel_m:  +document.getElementById('veh_rwheel').value,
      gear_ratio: +document.getElementById('veh_gear').value,
      eta_drive:  +document.getElementById('veh_eta').value,
      regen_frac: +document.getElementById('veh_regen').value,
      // Nur wenn eine ausgelegte Verzahnung uebernommen wurde; ohne sie rechnet
      // compute_drivetrain mit gear_ratio + eta_drive wie bisher.
      ...(_vehGetriebe ? { getriebe: _vehGetriebe } : {}),
    },
    trailer: {
      mass_kg:   +document.getElementById('trailer_mass').value,
      n_axles:   +document.getElementById('trailer_axles').value,
      grade_pct: +document.getElementById('trailer_grade').value,
    },
  };
  if (payload.cycle === 'csv') {
    const f = document.getElementById('cycle_csv_file').files[0];
    if (f) payload.cycle_csv = await f.text();
    else   payload.cycle = 'wltp3';
  }
  const fmodes = ['rotate'];
  if (document.getElementById('fm_current_angle')?.checked) fmodes.push('current_angle');
  if (document.getElementById('fm_load_ramp')?.checked)     fmodes.push('load_ramp');
  payload.field_modes = fmodes;
  payload.geom.axialLen = payload.axial_len;
  // Parametrische Reinheit: der Geometrie-Tab ist IMMER parametrisch. magShape kommt
  // ausschließlich aus dem Dropdown, und etwaige aus einer früheren Designer-/KI-/STEP-
  // Sitzung in GEOM zurückgebliebene custom-Magnete (über die localStorage-Wiederher-
  // stellung) dürfen NICHT in eine parametrische Berechnung durchsickern — sonst würde
  // z. B. die 3D-Übernahme stale gezeichnete Magnete statt der eingestellten Topologie
  // verwenden. Der Designer-Pfad (_dsnBuildPayload) setzt magShape/customLegs danach
  // bewusst wieder.
  const _msEl = document.getElementById('mag_shape');
  if (_msEl) payload.geom.magShape = _msEl.value;
  delete payload.geom.customLegs;
  delete payload.geom.customBarriers;
  // ⊙ **Beim Axialfluss kommen die Maße aus dem Reiter ⊙ Axialfluss.** Dieser
  // Reiter hat kein einziges `axial*`-Feld — die Scheibe wird dort gezeichnet,
  // und das ist bewusst so (`axialfluss/LIESMICH.md`: 643 kB Maske, drei
  // Viertel ihrer geom-Felder bedeuten axial nichts). Nur schickte
  // `buildPayload` deshalb `fluxPath="axial"` MIT dem radialen Vokabular und
  // OHNE eine einzige axiale Zahl, und der Lauf starb an der ersten:
  // „❌ FEHLER: 'axialAktivOD' fehlt" mit vollem Traceback (09.10.2026).
  // Umgerechnet wird auf dem Server (`POST /axialfluss/geom`, aus
  // `ema_fluss.aus_seite`) — eine zweite Zuordnungstabelle in JavaScript wäre
  // dieselbe Falle wie die handgespiegelte `magnetLegs`.
  if ((payload.geom.fluxPath || 'radial') === 'axial') {
    const ax = await _axialGeomHolen();
    if (ax) Object.assign(payload.geom, ax.geom);
    // ⊙ Die zwei zulässigen Spannungen der Magnethaltung kommen aus
    // ③ Betrieb und NICHT aus der Zeichenseite — sie sind Werkstoffangaben,
    // keine Geometrie; deshalb werden sie NACH dem Zusammenführen gesetzt.
    for (const [id, k] of Object.entries(_AX_HALT_FELDER)) {
      const v = +(document.getElementById(id)?.value || 0);
      if (v > 0) payload.geom[k] = v;
    }
  }
  // In das aktive Projekt (Projekt-Tab) hineinrechnen statt jedes Mal ein neues anzulegen.
  if (window._activeProject && _activeProject.id) payload.project_id = _activeProject.id;
  return payload;
}

// Set a form field's value (or checkbox) and fire input+change so all bound
// callbacks run (GEOM update, displays, topology visibility, solver reset).
function _setField(id, val) {
  const el = document.getElementById(id);
  if (!el || val === undefined || val === null) return;
  if (el.type === 'checkbox') el.checked = !!val;
  else el.value = val;
  el.dispatchEvent(new Event('input'));
  el.dispatchEvent(new Event('change'));
}

// Inverse of buildPayload: repopulate the WHOLE form from a saved payload
// (used by "Projekt aus Vorlage erstellen"). Geometry selects are set first so
// the topology-dependent fields are visible; numeric % fields are scaled back to
// their displayed value. Geom keys without a form input (e.g. slotWidthRatio) are
// written straight onto GEOM.
function applyPayload(payload) {
  if (!payload) return;
  const G = payload.geom || {};
  for (const [k, v] of Object.entries(G)) GEOM[k] = v;   // incl. input-less keys

  // geometry selects first (drive topology/pocket/connection visibility via handlers)
  // Die Maschinenart zuerst: sie blendet die Magnet-Topologie ein oder aus.
  _setField('flux_path', G.fluxPath);
  if (typeof _flussZeigen === 'function') _flussZeigen();
  _setField('machine_art', G.machineType);
  _setField('t_leiter', G.tLeiterC);
  // Alle art-spezifischen Felder aus EINER Tabelle zurueckschreiben -- dieselbe,
  // aus der sie gefuellt und gebunden werden. Eine zweite Aufzaehlung hier war
  // schon einmal die Stelle, an der ein neues Feld zwar gesetzt, aber nie
  // wiederhergestellt wurde: „Projekt als Vorlage" holte dann stillschweigend
  // den Wert des zuletzt angesehenen Formulars (derselbe Befund wie frueher
  // bei `struct_solver`).
  if (window._ART_FELDER) {
    for (const id in window._ART_FELDER) _setField(id, G[window._ART_FELDER[id]]);
  }
  for (const id in _AX_HALT_FELDER) _setField(id, G[_AX_HALT_FELDER[id]]);
  if (window._updateArtVis) window._updateArtVis();
  _setField('mag_shape',   G.magShape);
  _setField('pocket_mode', G.pocketMode);
  _setField('mag_orient',  G.magOrient);
  _setField('wh_style',    G.windingHeadStyle);
  _setField('shaft_connection', G.shaftConnection);
  // Leistungselektronik zurueck ins Formular -- ohne das holt sich „Projekt als
  // Vorlage" stillschweigend die Umrichterwerte des zuletzt angesehenen
  // Formulars statt die des Projekts (derselbe Befund wie frueher bei
  // `struct_solver`).
  _setField('inv_vdc',       G.inverterVdc);
  _setField('inv_imax',      G.inverterImax);
  _setField('inv_anzahl',    G.inverterAnzahl);
  _setField('inv_topologie', G.inverterTopologie);
  _setField('inv_bezug',     G.umrichterBezug);

  const pct = v => (v != null ? Math.round(v * 100) : undefined);
  const geoMap = {
    dim_stator_out: G.statorOD, dim_stator_in: G.statorID, dim_rotor_out: G.rotorOD,
    dim_shaft: G.shaftD, dim_shaft_bore: G.shaftBoreD,
    stator_slots: G.slots, p_pairs: G.p,
    pocket_outer_d: G.pocketOuterD, pocket_inner_d: G.pocketInnerD,
    mag_angle: G.magAngle, mag_angle2: G.magAngle2, mag_asym: G.magAsym, mag_tang_len: G.magTangLen,
    mag_depth: pct(G.magDepthRel), mag_width: G.magWidth, mag_thick: G.magThick,
    mag_gap: G.magGapMm,
    mag_dist: G.magDist, mag_layer_gap: G.magLayerGap, mag_layers: G.magLayers,
    pole_arc: pct(G.poleArcFrac), seg_per_pole: G.segPerPole, n_ax: G.nAx, n_circ: G.nCirc,
    slot_depth: G.slotDepth, cond_per_slot: G.conductorsPerSlot, coil_pitch: G.coilPitch,
    wh_flare: G.windingHeadFlare, wh_spread: G.windingHeadSpread,
    press_interf: G.pressInterferenceUm,
    spline_teeth: G.splineTeeth, spline_depth: G.splineToothDepthMm,
    poly_lobes: G.polygonLobes, poly_ecc: G.polygonEccMm,
  };
  for (const [id, v] of Object.entries(geoMap)) _setField(id, v);

  // run settings + materials
  _setField('project_name', payload.project_name);
  _setField('dim_axial',    payload.axial_len);
  _setField('sel_rotor_lam',  payload.rotor_lam);
  _setField('sel_stator_lam', payload.stator_lam);
  _setField('sel_hairpin',    payload.hairpin_mat);
  _setField('sel_magnet',     payload.magnet);
  // struct_solver stand hier nicht: buildPayload schickt ihn, applyPayload stellte ihn
  // nicht wieder her — „Projekt als Vorlage" holte also stillschweigend den Löser des
  // zuletzt angesehenen Formulars statt den des Projekts.
  ['n_frames','fdm_resolution','frame_resolution','field_bmax','struct_mesh_mm','struct_solver',
   'struct_img_px','struct_frames','rpm_from','rpm_to','rpm_step','T_ambient'].forEach(k => _setField(k, payload[k]));
  _setField('struct_video', payload.struct_video);
  _setField('sim_load',     payload.load_nm);
  _setField('sel_cooling',  payload.cooling);
  if (payload.cycle) _setField('sel_cycle', payload.cycle);

  const veh = payload.vehicle || {};
  // Die AUSGELEGTE Verzahnung (aus Tab ⚙ Getriebe, `--uebernehmen`). Sie steht
  // in keinem Formularfeld, und `buildPayload` baute `vehicle` bis zum
  // 15.09.2026 ausschliesslich aus den sieben Feldern — der naechste Lauf aus
  // dem Browser warf sie also still weg und fiel auf die skalare Uebersetzung
  // samt festem eta = 0,95 zurueck, genau die beiden Konstanten, gegen die
  // ema_getriebe gebaut wurde. Siehe BEFUNDE.md, 15.09.2026.
  _vehGetriebe = veh.getriebe || null;
  _vehGetriebeAnzeigen();
  _setField('veh_mass', veh.mass_kg);   _setField('veh_cwA', veh.cwA_m2);  _setField('veh_cr', veh.cr);
  _setField('veh_rwheel', veh.r_wheel_m); _setField('veh_gear', veh.gear_ratio);
  _setField('veh_eta', veh.eta_drive);  _setField('veh_regen', veh.regen_frac);
  const tr = payload.trailer || {};
  _setField('trailer_mass', tr.mass_kg); _setField('trailer_axles', tr.n_axles); _setField('trailer_grade', tr.grade_pct);

  const fm = payload.field_modes || [];
  _setField('fm_current_angle', fm.includes('current_angle'));
  _setField('fm_load_ramp',     fm.includes('load_ramp'));

  // stepwise-geometry component toggles (default to the full build if absent)
  const dflt = (v, d) => (v === undefined ? d : v);
  _setField('gen_shaft',    dflt(G.genShaft,        true));
  _setField('gen_rotor',    dflt(G.genRotorIron,    true));
  _setField('gen_magnets',  dflt(G.genMagnets,      true));
  _setField('gen_stator',   dflt(G.genStatorIron,   true));
  _setField('gen_hairpins', dflt(G.genHairpins,     true));
  _setField('gen_whead',    dflt(G.genWindingHeads, true));
  _setField('gen_bear_a',   dflt(G.genBearingA,     false));
  _setField('gen_bear_b',   dflt(G.genBearingB,     false));
  _setField('gen_insul',    dflt(G.genInsulation,   false));
  _setField('bearing_od',   dflt(G.bearingODmm,     0));
  _setField('bearing_w',    dflt(G.bearingWidthMm,  14));
  _setField('bearing_gap',  dflt(G.bearingGapMm,    5));
  _setField('insul_thk',    dflt(G.insulationThkMm, 0.4));
  _setField('gen_balance',  dflt(G.genBalanceBolts,    false));
  _setField('bal_thread',   dflt(G.balanceBoltThread,  'M6'));
  _setField('bal_circle_d', dflt(G.balanceBoltCircleD, 0));
  _setField('bal_offset',   dflt(G.balanceBoltOffsetDeg, 0));
  _setField('gen_fb_q',     dflt(G.genFluxBarrierQ, false));
  _setField('gen_fb_d',     dflt(G.genFluxBarrierD, false));
  _setField('fb_width',     dflt(G.fluxBarrierWidth, 3));
  _setField('fb_depth',     dflt(G.fluxBarrierDepth, 10));
  if (typeof _updateComponentVis === 'function') _updateComponentVis();
}

// Lightweight transient toast (no dependency).
function _toast(msg) {
  let t = document.getElementById('_toast');
  if (!t) {
    t = document.createElement('div'); t.id = '_toast';
    t.style.cssText = 'position:fixed;bottom:22px;left:50%;transform:translateX(-50%);' +
      'background:#27ae60;color:#fff;padding:10px 18px;border-radius:6px;z-index:500;' +
      'font-size:.85rem;box-shadow:0 4px 16px rgba(0,0,0,.4);transition:opacity .3s;max-width:80vw';
    document.body.appendChild(t);
  }
  t.textContent = msg; t.style.opacity = '1';
  clearTimeout(t._tid); t._tid = setTimeout(() => { t.style.opacity = '0'; }, 4000);
}

// "Projekt aus Vorlage erstellen": load a project's inputs into the form for a new run.
async function useAsTemplate(pid) {
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/template').then(x => x.json());
    if (r.error) { alert('Vorlage laden fehlgeschlagen: ' + r.error); return; }
    applyPayload(r.payload);
    closeProjectGallery();
    switchTab('geo');
    const note = r.reconstructed ? ' — aus Metadaten rekonstruiert, einige Einstellungen auf Standard' : '';
    _toast('📋 Vorlage übernommen: „' + (r.label || pid) + '"' + note + '. Parameter anpassen und Analyse starten.');
  } catch (e) { alert('Fehler: ' + e.message); }
}

// Ganzes Projekt klonen (Eingaben + Notizen + Projekt-RAG, mit Abstammung).
async function cloneProject(pid) {
  const name = prompt('Name des neuen (geklonten) Projekts:', '');
  if (name === null) return;
  try {
    const r = await fetch('/project/' + encodeURIComponent(pid) + '/clone',
      { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }) }).then(x => x.json());
    if (r.error) { alert('Klonen fehlgeschlagen: ' + r.error); return; }
    if (r.payload) applyPayload(r.payload);
    closeProjectGallery();
    switchTab('geo');
    await refreshProjectList();
    _toast('📁 Klon „' + (r.label || r.id) + '" angelegt (Abstammung vermerkt). Eingaben übernommen — Analyse starten.');
  } catch (e) { alert('Fehler: ' + e.message); }
}

// Bundle importieren (.emaproj) → neues Projekt
async function importBundle(input) {
  const f = input.files && input.files[0];
  if (!f) return;
  const fd = new FormData(); fd.append('file', f);
  try {
    const r = await fetch('/import_bundle', { method: 'POST', body: fd }).then(x => x.json());
    if (r.error) { alert('Import fehlgeschlagen: ' + r.error); return; }
    await openProjectGallery();
    _toast('📦 Bundle importiert: „' + (r.label || r.id) + '"');
  } catch (e) { alert('Fehler: ' + e.message); }
  finally { input.value = ''; }
}

async function startAnalysis() {
  const payload = await buildPayload();
  return _runAnalysisPayload(payload);
}

async function _runAnalysisPayload(payload) {
  const btn = document.getElementById('btn_analyse');
  btn.disabled = true;
  btn.textContent = '⏳ Analyse läuft…';

  // Switch to results tab and show progress
  document.getElementById('tbtn-results').disabled = false;
  switchTab('results');
  document.getElementById('analysis-progress').classList.add('show');
  document.getElementById('results-content').style.display   = 'none';
  document.getElementById('progress-log').innerHTML = '';
  document.getElementById('progress-fill').style.width = '0%';

  try {
    const resp = await fetch('/analyse', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    if (!resp.ok) {
      const err = await resp.json();
      addLog('❌ ' + (err.error || 'Fehler beim Starten'));
      btn.disabled = false; btn.textContent = '⚙ Analyse starten';
      return;
    }
    _pollTimer = setInterval(pollStatus, 1200);
  } catch(e) {
    addLog('❌ Server nicht erreichbar: ' + e.message);
    btn.disabled = false; btn.textContent = '⚙ Analyse starten';
  }
}

// ── Selectively re-run forgotten pipeline stages on the loaded project ──────────
async function recomputeStages() {
  const map = {rc_field: 'field', rc_structural: 'structural',
               rc_thermal: 'thermal', rc_drivecycle: 'drivecycle'};
  const stages = Object.entries(map)
    .filter(([id]) => document.getElementById(id)?.checked).map(([, v]) => v);
  if (!stages.length) { alert('Bitte mindestens eine Stufe wählen.'); return; }

  // Active project id from server state (set by a run or by loading a project)
  let pid = null;
  try { pid = (await fetch('/status').then(r => r.json())).project_id; } catch (e) {}
  if (!pid) { alert('Kein Projekt geladen — erst ein Projekt laden oder eine Analyse ausführen.'); return; }

  const btn = document.getElementById('btn_recompute');
  btn.disabled = true; const old = btn.textContent; btn.textContent = '⏳ Rechne…';
  switchTab('results');
  document.getElementById('analysis-progress').classList.add('show');
  document.getElementById('progress-title').textContent = 'Nachrechnen läuft…';
  document.getElementById('progress-log').innerHTML = '';
  document.getElementById('progress-fill').style.width = '0%';
  try {
    const payload = await buildPayload();
    payload.stages = stages;
    const resp = await fetch('/project/' + encodeURIComponent(pid) + '/recompute', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload) });
    const j = await resp.json();
    if (!resp.ok) { addLog('❌ ' + (j.error || 'Nachrechnen fehlgeschlagen')); return; }
    addLog('↻ Nachrechnen gestartet: ' + (j.stages || stages).join(', '));
    _pollTimer = setInterval(pollStatus, 1200);
  } catch (e) {
    addLog('❌ Server nicht erreichbar: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = old;
  }
}

// ── Staged workflow: CAD-only preview + smoke test ──────────────────────────────
// A reusable progress/result overlay (live log + body region + actions footer).
function _wfModal(title) {
  let ov = document.getElementById('wf-overlay');
  if (ov) ov.remove();
  ov = document.createElement('div');
  ov.id = 'wf-overlay';
  ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:9999;'
    + 'display:flex;align-items:center;justify-content:center;padding:24px';
  ov.onclick = e => { if (e.target === ov) ov.remove(); };
  ov.innerHTML = `
    <div style="background:#26262b;border:1px solid #444;border-radius:8px;max-width:880px;
                width:100%;max-height:88vh;display:flex;flex-direction:column;overflow:hidden">
      <div style="padding:12px 16px;border-bottom:1px solid #3a3a3a;display:flex;
                  justify-content:space-between;align-items:center">
        <strong id="wf-title" style="font-size:.95rem">${escHtml(title)}</strong>
        <button onclick="document.getElementById('wf-overlay').remove()"
                style="background:#444;padding:5px 12px;font-size:.78rem">Schließen</button>
      </div>
      <div id="wf-body" style="padding:14px 16px;overflow:auto"></div>
      <pre id="wf-log" style="margin:0;padding:10px 16px;background:#1b1b1f;color:#bcd;
           font-size:.72rem;line-height:1.45;max-height:240px;overflow:auto;
           border-top:1px solid #333;white-space:pre-wrap"></pre>
      <div id="wf-actions" style="padding:10px 16px;border-top:1px solid #3a3a3a;
           display:flex;gap:8px;flex-wrap:wrap"></div>
    </div>`;
  document.body.appendChild(ov);
  return ov;
}
function _wfLog(lines) {
  const el = document.getElementById('wf-log');
  if (!el || !lines) return;
  el.textContent = lines.join('\n');
  el.scrollTop = el.scrollHeight;
}

async function startCadPreview() {
  const btn = document.getElementById('btn_cad_preview');
  btn.disabled = true; const old = btn.textContent; btn.textContent = '⏳ Baue CAD…';
  _wfModal('🧊 CAD-Geometrie wird erzeugt…');
  document.getElementById('wf-body').innerHTML =
    '<div style="color:#9ab">Erzeuge nur die Geometrie (Welle · Rotor · Magnete · '
    + 'Stator · Hairpins · aktivierte Extras) in FreeCAD — ohne Berechnung. '
    + 'Das kann je nach Topologie ~10–90 s dauern.</div>';
  try {
    // Im Designer-Tab die GEZEICHNETE Geometrie bauen (custom legs/barriers),
    // nicht die Form aus dem Geometrie-Tab.
    const useDesign = (window._activeTab === 'designer') && DESIGN.magnets.length;
    const payload = useDesign ? await _dsnBuildPayload() : await buildPayload();
    // Welches Modell gebaut wird (Fussleiste). Der Vorgabewert ist der
    // Vollmotor, also bleibt jeder bisherige Aufruf derselbe.
    payload.cad_modell =
      document.getElementById('foot_cad')?.value || 'vollmotor';
    const resp = await fetch('/cad_preview', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload) });
    if (!resp.ok) { const e = await resp.json();
      document.getElementById('wf-body').innerHTML =
        '<div style="color:#e88">❌ ' + escHtml(e.error || 'Start fehlgeschlagen') + '</div>';
      return;
    }
    _pollWf('/cad_preview/status', _onCadDone);
  } catch (e) {
    document.getElementById('wf-body').innerHTML =
      '<div style="color:#e88">❌ Server nicht erreichbar: ' + escHtml(e.message) + '</div>';
  } finally { btn.disabled = false; btn.textContent = old; }
}

function _onCadDone(s) {
  const ok = s.status === 'done';
  document.getElementById('wf-title').textContent =
    ok ? '🧊 CAD-Geometrie bereit' : '🧊 CAD-Vorschau fehlgeschlagen';
  const r = s.result || {};
  const ts = '?t=' + Date.now();
  if (ok) {
    const imgs = r.cad_images || {};
    document.getElementById('wf-body').innerHTML = `
      <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;font-size:.8rem;color:#cde">
        <span>📐 ${(r.n_faces||0)} Flächen</span>
        <span>· Volumen ≈ ${Math.round(r.volume_mm3||0).toLocaleString()} mm³</span>
        <span>· STEP: ${r.step ? '✓' : '—'}</span>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px">
        <figure style="margin:0"><img src="/cad_image/motor_cross_section.png${ts}"
           style="width:100%;border:1px solid #444;border-radius:5px;background:#fff"
           onerror="this.style.opacity=.3;this.alt='Querschnitt n/a'"/>
           <figcaption style="font-size:.72rem;color:#9ab;text-align:center">Querschnitt</figcaption></figure>
        <figure style="margin:0"><img src="/cad_image/motor_side_view.png${ts}"
           style="width:100%;border:1px solid #444;border-radius:5px;background:#fff"
           onerror="this.style.opacity=.3;this.alt='Axialschnitt n/a'"/>
           <figcaption style="font-size:.72rem;color:#9ab;text-align:center">Axialschnitt</figcaption></figure>
      </div>
      <div style="font-size:.72rem;color:#778;margin-top:8px">
        2D-Schnitte sind schematisch (zeigen nicht alle Komponenten-Schalter). Für die
        echte 3D-Geometrie inkl. Lager/Isolation „In FreeCAD öffnen".</div>`;
    document.getElementById('wf-actions').innerHTML = `
      <button onclick="openFreeCAD()" style="background:#2b6cb0;padding:8px 16px;font-size:.8rem">🔧 In FreeCAD öffnen (3D)</button>
      <button onclick="downloadStep()" style="background:#445;padding:8px 16px;font-size:.8rem">⬇ STEP herunterladen</button>
      <button onclick="document.getElementById('btn_analyse').click();document.getElementById('wf-overlay').remove();"
              style="background:#1f7a5a;padding:8px 16px;font-size:.8rem">⚙ Echte Berechnung starten</button>`;
  } else {
    document.getElementById('wf-body').innerHTML =
      '<div style="color:#e88">❌ ' + escHtml(s.error || 'Geometrie fehlgeschlagen') + '</div>';
  }
}

async function startSmokeTest() {
  const btn = document.getElementById('btn_smoke');
  btn.disabled = true; const old = btn.textContent; btn.textContent = '⏳ Test läuft…';
  const mitCad = !!document.getElementById('foot_smoke_cad')?.checked;
  _wfModal('🧪 Smoke-Test läuft…');
  document.getElementById('wf-body').innerHTML =
    '<div style="color:#9ab">Schneller Selbsttest der Rechenkette (Topologie, dq/MTPA, '
    + 'FDM-Feld, Verbindung, Verformung, Skript-Erzeugung, ⊙ Axialfluss)'
    + (mitCad
       ? ' — <b>mit FreeCAD</b>: Vollmotor + Läufer-FEM und die Scheibe '
         + '(<code>ema_axial_cad</code>) werden wirklich gebaut. Das dauert Minuten.'
       : ' — ohne FreeCAD, ~15 s. Für den echten Scheibenbau den Haken '
         + '„mit CAD“ setzen.')
    + '</div>';
  try {
    const resp = await fetch('/smoke_test', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({ cad: mitCad }) });
    if (!resp.ok) { const e = await resp.json();
      document.getElementById('wf-body').innerHTML =
        '<div style="color:#e88">❌ ' + escHtml(e.error || 'Start fehlgeschlagen') + '</div>';
      return;
    }
    _pollWf('/smoke_test/status', _onSmokeDone);
  } catch (e) {
    document.getElementById('wf-body').innerHTML =
      '<div style="color:#e88">❌ Server nicht erreichbar: ' + escHtml(e.message) + '</div>';
  } finally { btn.disabled = false; btn.textContent = old; }
}

function _onSmokeDone(s) {
  const ok = s.status === 'done' && s.result && s.result.ok;
  document.getElementById('wf-title').textContent = ok ? '🧪 Smoke-Test bestanden' : '🧪 Smoke-Test fehlgeschlagen';
  const sum = (s.result && s.result.summary) || (ok ? 'OK' : 'Fehler');
  // Womit geprueft wurde, gehoert zum Ergebnis: „28 bestanden" sagt nicht, ob
  // FreeCAD dabei war -- und genau das ist beim Axialfluss die Frage.
  const wie = s.cad
    ? '<b>mit FreeCAD</b> — Vollmotor, Läufer-FEM und die Scheibe '
      + '(<code>ema_axial_cad</code>) wurden wirklich gebaut'
    : 'ohne FreeCAD — reine Rechenkette samt ⊙ Axialfluss; der echte '
      + 'Scheibenbau braucht den Haken „mit CAD“';
  document.getElementById('wf-body').innerHTML =
    `<div style="font-size:.9rem;color:${ok ? '#7ec98f' : '#e88'}">${ok ? '✓' : '❌'} ${escHtml(sum)}</div>`
    + `<div style="margin-top:6px;font-size:.76rem;color:#9ab">${wie}</div>`;
}

// Generic poller for a {status,progress,log,result,error} endpoint until done/error.
function _pollWf(url, onDone) {
  const tick = async () => {
    try {
      const s = await fetch(url).then(r => r.json());
      _wfLog(s.log);
      if (s.status === 'done' || s.status === 'error') {
        if (document.getElementById('wf-overlay')) onDone(s);
        return;
      }
    } catch (e) { /* keep polling */ }
    if (document.getElementById('wf-overlay')) setTimeout(tick, 1000);
  };
  tick();
}

// Render a single field frame (no FreeCAD/FEM/animation) and show it in an overlay.
async function previewFrame() {
  const btn = document.getElementById('btn_preview');
  const old = btn.textContent;
  const res = +(document.getElementById('preview_res')?.value || 800);
  btn.disabled = true;
  btn.textContent = res >= 3000 ? '⏳ Multigrid… (mehrere Minuten)'
                  : res >= 1600 ? '⏳ Rechne (kann dauern)…'
                  : '⏳ Rechne Frame…';
  try {
    const payload = await buildPayload();
    payload.frame_resolution = res;   // preview drives both grid size and image px
    const resp = await fetch('/preview_field', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload),
    });
    const data = await resp.json();
    if (!resp.ok) { alert('Vorschau fehlgeschlagen: ' + (data.error || resp.status)); return; }
    _showPreviewModal(data);
  } catch(e) {
    alert('Server nicht erreichbar: ' + e.message);
  } finally {
    btn.disabled = false; btn.textContent = old;
  }
}

function _showPreviewModal(data) {
  let ov = document.getElementById('preview-overlay');
  if (!ov) {
    ov = document.createElement('div');
    ov.id = 'preview-overlay';
    ov.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.82);z-index:9999;'
      + 'display:flex;align-items:center;justify-content:center;flex-direction:column;gap:10px';
    ov.onclick = e => { if (e.target === ov) ov.remove(); };
    document.body.appendChild(ov);
  }
  ov.innerHTML = `
    <img src="data:image/png;base64,${data.png_b64}"
         style="max-width:90vw;max-height:80vh;border:1px solid #444;border-radius:6px"/>
    <div style="color:#cde;font-family:monospace;font-size:.8rem">
      ${data.flussweg === 'axial'
        ? `⊙ abgewickelter Schnitt bei r=${data.radius_mm} mm · ${escHtml(data.bauform||'')}`
          + ` · ${data.polteilungen} Polteilungen · Gitter ${data.N}²`
          + ` · ${Math.round(data.rpm).toLocaleString()} U/min · i_q=${data.iq} A`
          + ` · B_gap=${data.B_gap_T} T`
        : `Gitter ${data.N}² → Bild ${data.out_px || data.N} px · ${Math.round(data.rpm).toLocaleString()} U/min`
          + ` · i_q=${data.iq} A · i_d=${data.id} A · B_gap=${data.B_gap_T} T · θ=${data.rotor_angle_deg}°`}
    </div>
    ${data.hinweis ? `<div style="color:#8ab;font-size:.74rem;max-width:70ch;text-align:center">${escHtml(data.hinweis)}</div>` : ''}
    <button onclick="document.getElementById('preview-overlay').remove()"
            style="background:#444;padding:8px 18px;font-size:.8rem">Schließen</button>`;
}

async function pollStatus() {
  try {
    const s = await fetch('/status').then(r => r.json());
    document.getElementById('progress-fill').style.width = s.progress + '%';
    if (s.log && s.log.length) {
      const logEl = document.getElementById('progress-log');
      logEl.innerHTML = s.log.map(l => `<p>${escHtml(l)}</p>`).join('');
      logEl.scrollTop = logEl.scrollHeight;
    }
    if (s.status === 'done') {
      clearInterval(_pollTimer);
      loadResults();
    } else if (s.status === 'error') {
      clearInterval(_pollTimer);
      const _d = s.diagnose || {};
      // „Analyse fehlgeschlagen" allein sagt nicht, WAS gehalten hat. Der
      // Server rechnet den Befund (`ema_diagnose`), hier steht sein Titel.
      document.getElementById('progress-title').textContent =
        '❌ ' + (_d.titel || 'Analyse fehlgeschlagen');
      document.getElementById('btn_analyse').disabled = false;
      document.getElementById('btn_analyse').textContent = '⚙ Analyse starten';
      _zeigeVorschlaege(s);
      // Die Fussleiste ist 52 px hoch und `overflow:hidden` -- der Kasten wird
      // hinter das Protokoll gehaengt und war damit zwar im DOM, aber
      // unsichtbar. Von aussen sah das aus wie „es kommt kein Vorschlag",
      // und genau so wurde es mehrfach gemeldet. Ein gerissenes Tor zieht die
      // Leiste deshalb selbst auf -- so weit, dass Befund und Wege im Bild
      // sind, und nicht weiter. Wer sie wieder zuzieht, behaelt das: gesetzt
      // wird nur beim Fehlschlag.
      try {
        const f = document.getElementById('footer');
        const b2 = document.getElementById('gate_vorschlaege');
        if (f && b2) {
          const soll = Math.min(Math.round(window.innerHeight * 0.62),
                                b2.scrollHeight + 150);
          if (f.offsetHeight < soll) {
            f.style.height = soll + 'px';
            if (typeof _splitRefresh === 'function') _splitRefresh();
            window.dispatchEvent(new Event('resize'));
          }
          b2.scrollIntoView({ block: 'nearest' });
        }
      } catch (e) {}
    }
  } catch(e) { /* server busy */ }
}

// ── Ein Tor ist gerissen — und das Werkzeug weiss, was helfen wuerde ────────
// „Analyse fehlgeschlagen" allein ist bei der Fliehkraft eine besonders arme
// Auskunft: die Ringspannung ist eine geschlossene Formel, jeder Hebel darin
// laesst sich nach dem zulaessigen Wert aufloesen. Der Server rechnet die Wege
// aus (`ema_rotorcheck.entlastung`, jeder gegen dasselbe Tor nachgeprueft) und
// schickt sie in `/status`; hier werden Knoepfe daraus.
//
// VORGESCHLAGEN IST NICHT GEWAEHLT: jeder Knopf traegt seinen Preis, und
// uebernommen wird erst auf Klick — und auch dann wird nur das Formular
// gesetzt, nicht neu gestartet. Was gebaut wird, entscheidet der Mensch.
// Ist die Seite, die hier laeuft, noch die, die auf der Platte liegt? Ein
// offener Reiter laedt sich nicht von selbst neu -- und dann sucht man Fehler
// in einer Maske, die der Server laengst ersetzt hat. Dieselbe Pruefung
// fuehren die Agentenseiten seit jeher (`seiteVeraltet`).
let _uiStand = null;
async function _uiStandPruefen() {
  try {
    const r = await fetch('/oberflaeche', { cache: 'no-store' }).then(x => x.json());
    if (!r || !r.hash) return;
    if (_uiStand === null) { _uiStand = r.hash; return; }
    if (r.hash === _uiStand || document.getElementById('ui_veraltet')) return;
    const b = document.createElement('div');
    b.id = 'ui_veraltet';
    b.style.cssText = 'position:fixed;left:0;right:0;top:0;z-index:9999;padding:7px 12px;'
      + 'background:#6a4a1e;color:#ffe9c0;font-size:.82rem;text-align:center;'
      + 'border-bottom:1px solid #a8822e';
    b.innerHTML = 'Die Oberfläche auf dem Server hat sich geändert — diese Seite ist veraltet. '
      + '<button onclick="location.reload(true)" style="width:auto;display:inline-block;'
      + 'padding:2px 10px;margin-left:8px;background:#2a3a4a;color:#cfe;border:1px solid #4a6a8a;'
      + 'border-radius:3px;cursor:pointer">neu laden</button>';
    document.body.appendChild(b);
  } catch (e) { /* Server aus — nicht der Moment fuer eine Warnung */ }
}
_uiStandPruefen();
setInterval(_uiStandPruefen, 20000);

function _zeigeVorschlaege(s) {
  const alt = document.getElementById('gate_vorschlaege');
  if (alt) alt.remove();
  const wege = s.vorschlaege || [];
  const diag = s.diagnose || {};
  const hinweise = diag.hinweise || [];
  // Auch OHNE gerechnete Wege gibt es fast immer etwas zu sagen: welche Stufe
  // gehalten hat, warum die Vorschau trotzdem rechnet, und die Frage, mit der
  // sich der Chat darauf ansetzen laesst. Frueher hing dieser ganze Kasten an
  // `wege.length` — also an dem einen Tor, das Wege mitbringt.
  if (!wege.length && !hinweise.length && !diag.chat) return;
  const box = document.createElement('div');
  box.id = 'gate_vorschlaege';
  box.style.cssText = 'margin-top:10px;background:#2a2620;border:1px solid #6a5a2e;'
                    + 'border-radius:6px;padding:10px 12px;font-size:.82rem;color:#e8dcc0';
  // ZUERST, was gefunden wurde -- und zwar ALLES, nicht nur das Tor, das
  // angehalten hat. Gemeldet als „wieder steht nirgends, was das Problem ist":
  // der Laeufer zerfiel in Einzelarme, waehrend der Lauf am Daempferkaefig
  // stand, und die Nabe kam nur als Nebensatz in einem Hinweis vor.
  const befunde = (s.befunde && s.befunde.length) ? s.befunde
                  : (s.befund ? [s.befund] : []);
  box.innerHTML =
    `<div style="font-weight:600;margin-bottom:5px">${escHtml(
        diag.titel || 'Was passiert ist')}</div>`
    + (befunde.length
         ? `<div style="margin-bottom:9px">
              <div style="font-size:.76rem;color:#e8b;letter-spacing:.04em;margin-bottom:3px">GEFUNDEN</div>`
           + befunde.map((b, n) => `<div style="font-size:.78rem;color:#f0d2d2;line-height:1.5;
                margin-bottom:3px;padding-left:16px;text-indent:-16px">`
                + (n === 0 ? '\u26D4 ' : '\u26A0 ') + escHtml(b) + `</div>`).join('')
           + (befunde.length > 1
                ? `<div style="font-size:.72rem;color:#b5a980;margin-top:3px">
                     \u26D4 hält den Lauf an \u00b7 \u26A0 bleibt offen, auch wenn der erste behoben ist</div>`
                : '')
           + `</div>`
         : '')
    + (wege.length ? `<div style="font-size:.76rem;color:#9cb;letter-spacing:.04em;margin-bottom:2px">DAS HILFT</div>` : '')
    + wege.map((w, i) => `
        <div style="display:flex;gap:9px;align-items:flex-start;padding:6px 0;border-top:1px solid #4a412a">
          <div style="flex:1;min-width:0">
            <div>${escHtml(w.text)}</div>
            <div style="font-size:.74rem;color:#b5a980;line-height:1.45;margin-top:2px">${escHtml(w.preis || '')}</div>
          </div>
          ${(w.schluessel || w.aenderungen) ? `<div style="display:flex;gap:5px;flex-wrap:wrap">
            <button onclick="_gateUebernehmen(${i})" style="background:#5a6a3a;width:auto;padding:5px 11px;font-size:.75rem;white-space:nowrap">übernehmen</button>
            <button onclick="_gateUebernehmen(${i},true)" style="background:#3a5a6a;width:auto;padding:5px 11px;font-size:.75rem;white-space:nowrap">übernehmen &amp; rechnen</button>
          </div>` : ''}
        </div>`).join('')
    + (wege.length ? `<div style="font-size:.74rem;color:#b5a980;margin-top:8px;border-top:1px solid #4a412a;padding-top:6px">
         „Übernehmen" setzt nur das Formular, „übernehmen &amp; rechnen" startet den
         Lauf gleich mit. Beides erst auf Klick: welcher Weg gegangen wird,
         bleibt eine Auslegungsentscheidung.</div>` : '')
    // Die Hinweise tragen den Zusammenhang, nicht die Abhilfe — allen voran
    // den, der die gemeldete Unstimmigkeit aufloest („ich kann doch einen
    // Frame rechnen": der Vorschaupfad führt kein Tor).
    + hinweise.map(h => `<div style="font-size:.76rem;color:#b5a980;line-height:1.5;
         margin-top:7px;border-top:1px solid #4a412a;padding-top:6px">ℹ ${escHtml(h)}</div>`).join('')
    + (diag.chat ? `<div style="margin-top:9px;border-top:1px solid #4a412a;padding-top:8px">
         <button onclick="_gateZumChat()" style="background:#3a5a6a;width:auto;padding:6px 12px;font-size:.78rem">
           💬 Im Chat besprechen</button>
         <span style="font-size:.74rem;color:#b5a980;margin-left:8px">
           übernimmt Befund und Maße in die Frage — nichts wird gerechnet</span></div>` : '');
  window._gateChat = diag.chat || '';
  window._gateWege = wege;
  const ziel = document.getElementById('progress-log');
  if (ziel && ziel.parentNode) ziel.parentNode.insertBefore(box, ziel.nextSibling);
}

// Welches Eingabefeld gehoert zu diesem Schluessel? Drei Wege in dieser
// Reihenfolge: gleicher Name (die Hauptfelder heissen wie ihr Schluessel),
// dann die art-abhaengigen Felder aus `_ART_FELDER` — DIESELBE Tabelle, aus
// der auch `applyPayload` liest, damit keine zweite danebensteht und beim
// naechsten neuen Feld auseinanderlaeuft. Findet sich nichts, wird das gesagt.
// Rueckfall, falls `window._ART_FELDER` beim Klick noch nicht steht: es wird
// in einem spaeteren Script-Block gesetzt, und ein Knopf, der davon abhaengt,
// ist genau dann tot, wenn man ihn braucht. Die Tabelle ist klein und aendert
// sich selten; `window._ART_FELDER` hat weiterhin Vorrang.
const _ART_FELDER_FALLBACK = {
  pol_schuh_anteil:"polSchuhAnteil", pol_bedeckung:"polbedeckung",
  pol_b_schuh:"polSchuhBreiteMm",    pol_b_kern:"polKernBreiteMm",
  pol_d_spule:"erregerSpuleDickeMm", pol_h_spule:"erregerSpuleHoeheMm",
  pol_kegel:"polKegelWinkelGrad",    spule_form:"erregerSpuleForm",
  spule_fuellung:"erregerSpuleFuellung",
  pol_befestigung:"polBefestigung",  pol_bolzen:"polBolzen",
  pol_gewinde:"polBolzenGewinde",    daempfer:"daempferkaefig",
  daempfer_staebe:"daempferStaebeJePol", daempfer_mat:"daempferMat",
  rotor_type:"rotorType", rotor_bars:"rotorBars", rotor_skew:"rotorSkewSlots",
  b_ziel:"bZielT", anker_wicklung:"armatureWinding"
};
function _gateFeld(schluessel) {
  let el = document.getElementById(schluessel);
  if (el) return el;
  const t = Object.assign({}, _ART_FELDER_FALLBACK, window._ART_FELDER || {});
  for (const id in t) {
    if (t[id] !== schluessel) continue;
    el = document.getElementById(id);
    if (el) return el;
  }
  return null;
}

// Einen Vorschlag ins Formular schreiben. `ebene` sagt, wohin er gehört — der
// Server weiß das, der Browser müsste es sonst raten.
function _gateAnwenden(w) {
  // Ein Weg kann MEHRERE Werte tragen (`aenderungen`) -- gerade die, die nur
  // gemeinsam wirken. Einzeln angeboten waeren sie Knoepfe, die nichts
  // bewirken; deshalb setzt dieser eine Klick alle.
  const paare = w.aenderungen
    ? Object.entries(w.aenderungen).map(([k, v]) => [k, v])
    : (w.schluessel ? [[w.schluessel, w.wert]] : []);
  let gesetzt = 0; const fehlt = [];
  for (const [schl, wert] of paare) {
    const el = _gateFeld(schl);
    if (el) {
      if (el.type === "checkbox") el.checked = (wert === true || +wert === 1);
      else el.value = wert;
      el.dispatchEvent(new Event("input",  { bubbles: true }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
      gesetzt++;
    } else fehlt.push(schl + " = " + wert);
    if ((w.ebene || "geom") === "geom" && typeof GEOM === "object") GEOM[schl] = wert;
    // Der Rotoraussendurchmesser zieht die Statorbohrung mit:
    // statorID = rotorOD + 2*Luftspalt. Ohne das reisst beim naechsten Anlauf
    // das Luftspalt-Tor statt der Fliehkraft, und es saehe aus, als haette der
    // Vorschlag nichts genuetzt.
    if (schl === "rotorOD" && typeof GEOM === "object") {
      const spalt = Math.max(0.1, ((+GEOM.statorID || 0)
                    - (+document.getElementById("rotorOD")?.defaultValue || 0)) / 2) || 0.7;
      const neuID = +(wert + 2 * spalt).toFixed(2);
      GEOM.statorID = neuID;
      const sid = document.getElementById("statorID");
      if (sid) { sid.value = neuID; sid.dispatchEvent(new Event("change", { bubbles: true })); }
    }
  }
  if (typeof drawRotor === "function") { try { drawRotor(); } catch (e) {} }
  return { gesetzt, fehlt };
}

// Einen Vorschlag ins Formular schreiben. `ebene` sagt, wohin er gehoert — der
// Server weiss das, der Browser muesste es sonst raten.
function _gateUebernehmen(i, auchRechnen) {
  const w = (window._gateWege || [])[i];
  if (!w) return;
  const r = _gateAnwenden(w);
  const box = document.getElementById('gate_vorschlaege');
  if (box) {
    // GANZ NACH OBEN. Unten angehaengt verschwand sie am Ende eines langen
    // Kastens, und von aussen sah ein geglueckter Klick aus wie gar keiner.
    const hin = document.createElement('div');
    hin.style.cssText = 'margin:-4px -6px 8px;padding:5px 8px;border-radius:4px;'
      + 'font-size:.80rem;font-weight:600;'
      + (r.fehlt.length ? 'background:#5a2a2a;color:#fcc' : 'background:#2a4a2a;color:#cfc');
    hin.textContent = r.fehlt.length
      ? '\u26A0 Feld nicht gefunden — bitte von Hand setzen: ' + r.fehlt.join(', ')
      : (auchRechnen
           ? '\u2713 ' + w.text + ' — übernommen, Analyse wird gestartet…'
           : '\u2713 ' + w.text + ' — ins Formular übernommen (Tab \u2461 Geometrie / \u2462 Betrieb prüfen, dann neu starten).');
    box.insertBefore(hin, box.firstChild);
    box.scrollIntoView({ block: 'nearest' });
  }
  // Ausfuehren ist ein eigener Klick, nie eine Folge des Uebernehmens: welcher
  // Weg gegangen wird, bleibt eine Auslegungsentscheidung. Angeboten wird er
  // aber, statt den Menschen den Startknopf suchen zu lassen.
  if (auchRechnen && !r.fehlt.length && typeof startAnalysis === 'function') {
    setTimeout(() => { try { startAnalysis(); } catch (e) {} }, 60);
  }
}
