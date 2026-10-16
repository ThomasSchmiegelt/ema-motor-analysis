// Reiter 📝 Bericht: der selbst geschriebene Bericht aus Bloecken.
//
// Der Zustand liegt in `_brDoc`; gespeichert wird auf Knopfdruck. Die
// Vorschau baut der SERVER mit `als_html` -- derselben Funktion, die auch
// die ausgelieferte HTML-Fassung schreibt.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── 📝 Berichtsreiter: selbst geschrieben, mit Bildern und Videos ───────────
// Der Bericht ist eine Liste BLOECKE. Der Zustand liegt in `_brDoc`; jede
// Aenderung schreibt dorthin, gespeichert wird auf Knopfdruck — ein Autosave
// bei jedem Tastendruck schriebe hunderte Fassungen, und der Server prueft die
// Pfade ohnehin bei jedem Speichern.
let _brDoc = null, _brKennung = null, _brBestand = { bilder: [], videos: [] };

function _brPid() {
  return (window._activeProject && window._activeProject.id) || 'current';
}

async function brAktivieren() {
  await brRefreshBestand();
  await brLadeBausteine();
  brRefreshListe();
  brRefreshAlle();
}

// Die Bausteine kommen vom Server — eine zweite Liste im Browser liefe beim
// nächsten neuen Baustein auseinander.
async function brLadeBausteine() {
  const sel = document.getElementById('br_baustein_sel');
  if (!sel) return;
  try {
    const l = await fetch('/project/' + _brPid() + '/berichte/bausteine').then(r => r.json());
    sel.innerHTML = (l || []).map(b => `<option value="${escHtml(b.quelle)}">${escHtml(b.label)}</option>`).join('');
  } catch (e) {}
}

// ── 📂 Alle Berichte des Projekts, egal welche Stufe sie erzeugt hat ───────
async function brRefreshAlle() {
  const box = document.getElementById('br_alle');
  if (!box) return;
  const pid = _brPid();
  let l = [];
  try { l = await fetch('/project/' + pid + '/berichte/alle').then(r => r.json()); } catch (e) {}
  if (!Array.isArray(l) || !l.length) {
    box.innerHTML = '<span style="font-size:.76rem;color:#789">Noch kein Bericht in diesem Projekt.</span>';
    return;
  }
  box.innerHTML = l.map(e => `
    <div style="display:flex;align-items:center;gap:8px;font-size:.78rem;background:#141821;border:1px solid #222a33;border-radius:5px;padding:5px 9px">
      <a href="/project/${pid}/datei/${e.pfad}" target="_blank" style="color:#6cf;text-decoration:none;flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
        ${escHtml(e.art)}${e.woher ? ' · ' + escHtml(e.woher) : ''}</a>
      <span style="font-size:.7rem;color:#789;white-space:nowrap">${e.mb} MB · ${escHtml(e.zeit)}</span>
    </div>`).join('');
}

// ── 👁 Vorschau ────────────────────────────────────────────────────────────
// Gebaut wird sie serverseitig mit `als_html` — derselben Funktion, die auch
// die ausgelieferte HTML-Fassung schreibt. Eine zweite Darstellung im Browser
// wäre genau die Stelle, an der Vorschau und Ergebnis auseinanderlaufen.
let _brVorschauTimer = null;
function brVorschau(sofort) {
  if (!document.getElementById('br_vorschau_an')?.checked) return;
  clearTimeout(_brVorschauTimer);
  _brVorschauTimer = setTimeout(async () => {
    if (!_brDoc) return;
    const rahmen = document.getElementById('br_vorschau');
    if (!rahmen) return;
    const doc = { titel: document.getElementById('br_titel')?.value || _brDoc.titel,
                  untertitel: document.getElementById('br_untertitel')?.value || '',
                  bloecke: _brDoc.bloecke || [] };
    try {
      const r = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung) + '/vorschau',
        { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc) });
      rahmen.srcdoc = r.ok ? await r.text()
        : '<p style="color:#e57;font:14px sans-serif">Vorschau fehlgeschlagen</p>';
    } catch (e) {
      rahmen.srcdoc = '<p style="color:#e57;font:14px sans-serif">' + escHtml(e.message) + '</p>';
    }
  }, sofort === true ? 0 : 700);
}

function brVorschauUm() {
  const an = document.getElementById('br_vorschau_an')?.checked;
  const pane = document.getElementById('br_vorschau_pane');
  if (pane) pane.style.display = an ? '' : 'none';
  if (an) brVorschau(true);
}

// ── 🕐 Fassungen und ⑂ Varianten ───────────────────────────────────────────
async function brRefreshFassungen() {
  const box = document.getElementById('br_fassungen');
  if (!box || !_brKennung) return;
  let l = [];
  try { l = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung) + '/fassungen')
                  .then(r => r.json()); } catch (e) {}
  if (!Array.isArray(l) || !l.length) {
    box.innerHTML = '<span style="font-size:.74rem;color:#789">Noch keine Fassung.</span>';
    return;
  }
  box.innerHTML = l.map((f, i) => `
    <div style="display:flex;align-items:center;gap:7px;font-size:.76rem;background:#141821;border:1px solid #222a33;border-radius:5px;padding:4px 9px">
      <span style="flex:1;min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">
        ${i === 0 ? '<b>jetzt</b> · ' : ''}${escHtml(f.zeit)} · ${escHtml(f.titel || '')} · ${f.n_bloecke} Blöcke
        <span style="color:#789">${escHtml(f.anlass || '')}</span></span>
      ${i === 0 ? '' : `<button onclick="brZurueck('${escHtml(f.marke)}')" style="background:#5a6a3a;width:auto;padding:3px 9px;font-size:.7rem" title="auf diese Fassung zurück">↩</button>`}
      <button onclick="brAbzweigen('${escHtml(f.marke)}')" style="background:#5a4a6a;width:auto;padding:3px 9px;font-size:.7rem" title="Variante ab dieser Fassung">⑂</button>
    </div>`).join('');
}

async function brZurueck(marke) {
  if (!confirm('Auf die Fassung von ' + marke + ' zurück? Der jetzige Stand wird vorher als Fassung gesichert.')) return;
  const r = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung) + '/zurueck',
    { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ marke }) })
    .then(x => x.json());
  if (r.error) { alert(r.error); return; }
  brOeffnen(_brKennung);
}

async function brAbzweigen(marke) {
  const t = prompt('Titel der Variante:', (_brDoc?.titel || 'Bericht') + ' (Variante)');
  if (t === null) return;
  const r = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung) + '/abzweigen',
    { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ marke: (typeof marke === 'string' ? marke : null), titel: t }) })
    .then(x => x.json());
  if (r.error) { alert(r.error); return; }
  await brRefreshListe();
  brOeffnen(r.kennung);
}


async function brRefreshBestand() {
  try { _brBestand = await fetch('/project/' + _brPid() + '/berichte/bestand').then(r => r.json()); }
  catch (e) { _brBestand = { bilder: [], videos: [] }; }
  if (_brDoc) brZeichne();
}

async function brRefreshListe() {
  const box = document.getElementById('br_liste');
  if (!box) return;
  let l = [];
  try { l = await fetch('/project/' + _brPid() + '/berichte/baum').then(r => r.json()); } catch (e) {}
  if (!Array.isArray(l) || !l.length) {
    box.innerHTML = '<span style="font-size:.76rem;color:#789">Noch kein Bericht — oben einen anlegen.</span>';
    return;
  }
  const pid = _brPid();
  box.innerHTML = l.map(e => {
    const arten = Object.entries(e.arten || {}).map(([k, v]) => v + '× ' + k).join(', ');
    const ein = (e.tiefe || 0) * 18;
    return `<div style="display:flex;align-items:center;gap:7px;background:#141821;border:1px solid #222a33;border-radius:5px;padding:6px 9px;margin-left:${ein}px">
      <div style="flex:1;min-width:0">
        <div style="font-size:.82rem;color:#cde;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${e.tiefe ? '⑂ ' : ''}${escHtml(e.titel)}</div>
        <div style="font-size:.68rem;color:#789">${escHtml(e.geaendert)} · ${e.n_bloecke} Blöcke${arten ? ' (' + escHtml(arten) + ')' : ''}${e.n_fassungen ? ' · ' + e.n_fassungen + ' Fassungen' : ''}</div>
      </div>
      <button onclick="brOeffnen('${escHtml(e.kennung)}')" style="background:#456;width:auto;padding:4px 9px;font-size:.7rem" title="bearbeiten">✎</button>
      ${e.pdf ? `<a href="/project/${pid}/berichte/${encodeURIComponent(e.kennung)}/pdf" target="_blank" style="background:#3a5a6a;color:#fff;text-decoration:none;border-radius:4px;padding:4px 9px;font-size:.7rem" title="PDF">📕</a>` : ''}
      ${e.html ? `<a href="/project/${pid}/berichte/${encodeURIComponent(e.kennung)}/html" target="_blank" style="background:#3a6a5a;color:#fff;text-decoration:none;border-radius:4px;padding:4px 9px;font-size:.7rem" title="HTML-Fassung — hier laufen die Videos">▶ HTML</a>` : ''}
      <button onclick="brLoeschen('${escHtml(e.kennung)}')" style="background:#633;width:auto;padding:4px 9px;font-size:.7rem">🗑</button>
    </div>`;
  }).join('');
}

async function brNeu() {
  const t = (document.getElementById('br_neu_titel')?.value || '').trim();
  const r = await fetch('/project/' + _brPid() + '/berichte/neu', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ titel: t }) }).then(x => x.json());
  if (r.error) { alert(r.error); return; }
  const el = document.getElementById('br_neu_titel'); if (el) el.value = '';
  await brRefreshListe();
  brOeffnen(r.kennung);
}

async function brOeffnen(kennung) {
  const doc = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(kennung))
                    .then(r => r.json());
  if (doc.error) { alert(doc.error); return; }
  _brDoc = doc; _brKennung = kennung;
  document.getElementById('br_editor').style.display = '';
  document.getElementById('br_titel').value = doc.titel || '';
  document.getElementById('br_untertitel').value = doc.untertitel || '';
  brZeichne();
  brRefreshFassungen();
  brVorschauUm();
}

async function brLoeschen(kennung) {
  if (!confirm('Bericht löschen? Der ganze Ordner geht weg (die Bilder und Videos bleiben, sie liegen woanders).')) return;
  await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(kennung) + '/delete', { method: 'POST' });
  if (_brKennung === kennung) { _brDoc = null; _brKennung = null;
    document.getElementById('br_editor').style.display = 'none'; }
  brRefreshListe();
}

function brAdd(art) {
  if (!_brDoc) return;
  const b = { art };
  if (art === 'text') b.text = '## Überschrift\n\nText …';
  if (art === 'tabelle') b.text = '| Größe | Wert |\n|---|---|\n| … | … |';
  if (art === 'bild') { b.pfad = (_brBestand.bilder[0] || {}).pfad || ''; b.beschriftung = ''; b.breite = 100; }
  if (art === 'video') { b.pfad = (_brBestand.videos[0] || {}).pfad || ''; b.beschriftung = ''; }
  if (art === 'baustein') {
    const sel = document.getElementById('br_baustein_sel');
    b.quelle = sel?.value || 'steckbrief';
    b.ueberschrift = sel?.options[sel.selectedIndex]?.text || '';
  }
  _brDoc.bloecke = _brDoc.bloecke || [];
  _brDoc.bloecke.push(b);
  brZeichne();
}

function brMove(i, d) {
  const b = _brDoc.bloecke, j = i + d;
  if (j < 0 || j >= b.length) return;
  [b[i], b[j]] = [b[j], b[i]];
  brZeichne();
}

function brDel(i) { _brDoc.bloecke.splice(i, 1); brZeichne(); }
function brSet(i, feld, wert) { _brDoc.bloecke[i][feld] = wert; }

function _brAuswahl(liste, aktuell, i) {
  // nach Gruppen sortiert — ein Projekt hat schnell fünfzig Bilder
  const gruppen = {};
  liste.forEach(x => { (gruppen[x.gruppe] = gruppen[x.gruppe] || []).push(x); });
  return Object.entries(gruppen).map(([g, xs]) =>
    `<optgroup label="${escHtml(g)}">` + xs.map(x =>
      `<option value="${escHtml(x.pfad)}"${x.pfad === aktuell ? ' selected' : ''}>${escHtml(x.name)}</option>`
    ).join('') + '</optgroup>').join('');
}

function brZeichne() {
  const box = document.getElementById('br_bloecke');
  if (!box || !_brDoc) return;
  const pid = _brPid();
  const bl = _brDoc.bloecke || [];
  if (!bl.length) {
    box.innerHTML = '<span style="font-size:.78rem;color:#789">Noch kein Block — oben einen anhängen.</span>';
    return;
  }
  box.innerHTML = bl.map((b, i) => {
    const kopf = `<div style="display:flex;gap:5px;align-items:center;margin-bottom:5px">
        <span style="font-size:.72rem;color:#789;flex:1">${i + 1}. ${escHtml(b.art)}</span>
        <button onclick="brMove(${i},-1)" style="background:#3a4150;width:auto;padding:2px 7px;font-size:.7rem">↑</button>
        <button onclick="brMove(${i},1)"  style="background:#3a4150;width:auto;padding:2px 7px;font-size:.7rem">↓</button>
        <button onclick="brDel(${i})"     style="background:#633;width:auto;padding:2px 7px;font-size:.7rem">🗑</button>
      </div>`;
    let rumpf = '';
    if (b.art === 'text' || b.art === 'tabelle') {
      rumpf = `<textarea oninput="brSet(${i},'text',this.value);brVorschau()" rows="${b.art === 'tabelle' ? 5 : 7}"
        style="width:100%;font-family:ui-monospace,monospace;font-size:.78rem;line-height:1.5"
        placeholder="Markdown">${escHtml(b.text || '')}</textarea>`;
    } else if (b.art === 'bild') {
      rumpf = `<div style="display:flex;gap:9px;align-items:flex-start;flex-wrap:wrap">
        <img src="/project/${pid}/datei/${b.pfad}" style="width:150px;border-radius:4px;background:#0d1014" onerror="this.style.opacity=.25"/>
        <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:5px">
          <select onchange="brSet(${i},'pfad',this.value);brZeichne()" style="width:100%">${_brAuswahl(_brBestand.bilder, b.pfad, i)}</select>
          <input type="text" value="${escHtml(b.beschriftung || '')}" oninput="brSet(${i},'beschriftung',this.value);brVorschau()" placeholder="Bildunterschrift"/>
          <label style="font-size:.72rem;color:#9aa">Breite ${b.breite || 100} %
            <input type="range" min="20" max="100" step="5" value="${b.breite || 100}"
                   oninput="brSet(${i},'breite',+this.value);this.previousSibling.textContent=' Breite '+this.value+' % '" style="width:100%"/></label>
        </div></div>`;
    } else if (b.art === 'video') {
      rumpf = `<div style="display:flex;gap:9px;align-items:flex-start;flex-wrap:wrap">
        <video src="/project/${pid}/datei/${b.pfad}" muted loop controls style="width:190px;border-radius:4px;background:#000"></video>
        <div style="flex:1;min-width:200px;display:flex;flex-direction:column;gap:5px">
          <select onchange="brSet(${i},'pfad',this.value);brZeichne()" style="width:100%">${_brAuswahl(_brBestand.videos, b.pfad, i)}</select>
          <input type="text" value="${escHtml(b.beschriftung || '')}" oninput="brSet(${i},'beschriftung',this.value);brVorschau()" placeholder="Bildunterschrift"/>
          <span style="font-size:.72rem;color:#9aa">Im PDF erscheint ein Standbild aus der Mitte, in der HTML-Fassung läuft es.</span>
        </div></div>`;
    } else if (b.art === 'baustein') {
      rumpf = `<div style="font-size:.78rem;color:#b9a">🧩 <b>${escHtml(b.ueberschrift || b.quelle)}</b>
        <div style="font-size:.72rem;color:#789;margin-top:3px;line-height:1.45">
          Wird beim Rendern FRISCH aus dem Projekt geholt — eine eingefrorene Zahl,
          die von der Ablage abweicht, sieht richtig aus und ist es nicht.</div>
        <input type="text" value="${escHtml(b.ueberschrift || '')}" oninput="brSet(${i},'ueberschrift',this.value);brVorschau()"
               placeholder="Überschrift" style="width:100%;margin-top:5px"/></div>`;
    } else {
      rumpf = '<div style="font-size:.76rem;color:#789;border-top:1px dashed #3a4150;padding-top:6px">— Seitenumbruch —</div>';
    }
    return `<div style="background:#141821;border:1px solid #222a33;border-radius:6px;padding:8px 10px">${kopf}${rumpf}</div>`;
  }).join('');
  brVorschau();
}

async function brSpeichern() {
  if (!_brDoc) return;
  _brDoc.titel = document.getElementById('br_titel').value;
  _brDoc.untertitel = document.getElementById('br_untertitel').value;
  const msg = document.getElementById('br_msg');
  const r = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung), {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(_brDoc) }).then(x => x.json());
  const mel = document.getElementById('br_meldungen');
  if (mel) mel.innerHTML = (r.meldungen || []).map(m => '⚠ ' + escHtml(m)).join('<br>');
  if (r.bloecke) { _brDoc.bloecke = r.bloecke; brZeichne(); }
  if (msg) { msg.style.color = '#9c9'; msg.textContent = '✓ gespeichert'
                + (r.fassung ? ' (Fassung ' + r.fassung + ')' : ' — unverändert, keine neue Fassung'); }
  brRefreshListe(); brRefreshFassungen();
}

async function brRendern() {
  if (!_brDoc) return;
  await brSpeichern();
  const btn = document.getElementById('btn_br_render');
  const msg = document.getElementById('br_msg');
  if (btn) btn.disabled = true;
  if (msg) { msg.style.color = '#9aa'; msg.textContent = '⏳ rendere …'; }
  const r = await fetch('/project/' + _brPid() + '/berichte/' + encodeURIComponent(_brKennung) + '/rendern',
                        { method: 'POST' }).then(x => x.json());
  if (r.error) {
    if (btn) btn.disabled = false;
    if (msg) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + r.error; }
    return;
  }
  _brPoll();
}

async function _brPoll() {
  let s;
  try { s = await fetch('/berichte/status').then(x => x.json()); }
  catch (e) { setTimeout(_brPoll, 1500); return; }
  const msg = document.getElementById('br_msg');
  if (msg) msg.textContent = (s.log || []).slice(-1)[0] || '…';
  if (s.status === 'running') { setTimeout(_brPoll, 900); return; }
  const btn = document.getElementById('btn_br_render');
  if (btn) btn.disabled = false;
  if (!msg) return;
  if (s.status === 'error') { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (s.error || 'Fehler'); return; }
  const pid = _brPid(), k = encodeURIComponent(_brKennung);
  msg.style.color = '#9c9';
  msg.innerHTML = '✓ fertig — <a href="/project/' + pid + '/berichte/' + k + '/pdf" target="_blank" style="color:#6cf">PDF</a>'
                + ' · <a href="/project/' + pid + '/berichte/' + k + '/html" target="_blank" style="color:#6cf">HTML (mit laufendem Video)</a>';
  brRefreshListe();
}
