// Der Leinwand-Designer und der KI-Entwurfspfad daneben.
//
// `DESIGN` haelt EINEN Halbpol in pol-lokalen Millimetern; beim Bauen wird
// er an der d-Achse gespiegelt und als `magShape="custom"` verschickt.
// Der KI-Teil (Varianten, Urteil, Fein-Optimierung, Studie auf dem Entwurf)
// stand frueher weiter unten in derselben Datei und ist hier angehaengt --
// er hat keine Anweisung auf oberster Ebene, die Reihenfolge ist also egal.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Designer-Tab (Canvas) ────────────────────────────────────────────────────
// DESIGN holds ONE half-pole master in pole-local mm (x=radial out, y=tangential).
// On build it is mirrored across the d-axis → full pole → magShape="custom" legs +
// custom barriers; the pipeline replicates per pole with alternating polarity.
const DESIGN = { magnets: [], barriers: [] };
let _dsnTool = 'select', _dsnPol = 1, _dsnCanvas = null, _dsnCtx = null;
let _dsnDrag = null, _dsnBar = null, _dsnSel = null, _dsnInit = false;
const _dsnView = { cx: 0, cy: 0, scale: 1 };

function dsnDims() {
  const g = id => +document.getElementById(id).value;
  const rotorOD = g('dsn_rotorOD'), airgap = g('dsn_airgap');
  return { statorOD: g('dsn_statorOD'), rotorOD, shaftD: g('dsn_shaftD'),
           statorID: rotorOD + 2 * airgap, airgap, axial: g('dsn_axial'),
           poles: Math.max(2, Math.round(g('dsn_poles') / 2) * 2),
           slots: g('dsn_slots'), cps: g('dsn_cps') };
}
function dsnSetTool(t) {
  _dsnTool = t; _dsnBar = null; _dsnDrag = null;
  for (const [k, id] of [['select','dsn_tool_sel'],['magnet','dsn_tool_mag'],
                        ['barrier','dsn_tool_bar'],['anlage','dsn_tool_anl']]) {
    const b = document.getElementById(id); if (b) b.style.background = (k === t) ? '#3a6' : '#444';
  }
  _dsnCanvas.style.cursor = t === 'select' ? 'default' : 'crosshair';
  dsnDraw();
}
function dsnTogglePol() {
  _dsnPol = -_dsnPol;
  const b = document.getElementById('dsn_pol');
  b.textContent = _dsnPol > 0 ? 'N (+)' : 'S (−)';
  b.style.background = _dsnPol > 0 ? '#c0392b' : '#2c5d8a';
}
function _mm2s(x, y) { return [_dsnView.cx + x * _dsnView.scale, _dsnView.cy - y * _dsnView.scale]; }
function _s2mm(sx, sy) { return [(sx - _dsnView.cx) / _dsnView.scale, -(sy - _dsnView.cy) / _dsnView.scale]; }
function _rot(pa, x, y) { const c = Math.cos(pa), s = Math.sin(pa); return [x * c - y * s, x * s + y * c]; }

function dsnActivate() {
  _dsnCanvas = document.getElementById('designCanvas');
  if (!_dsnCanvas) return;
  _dsnCtx = _dsnCanvas.getContext('2d');
  if (!_dsnInit) {
    _dsnInit = true;
    ['dsn_statorOD','dsn_rotorOD','dsn_shaftD','dsn_airgap','dsn_axial','dsn_poles','dsn_slots','dsn_cps']
      .forEach(i => document.getElementById(i).addEventListener('input', dsnResize));
    _dsnCanvas.addEventListener('mousedown', dsnMouseDown);
    _dsnCanvas.addEventListener('mousemove', dsnMouseMove);
    window.addEventListener('mouseup', dsnMouseUp);
    _dsnCanvas.addEventListener('dblclick', () => { if (_dsnBar) dsnFinishBar(); });
    window.addEventListener('keydown', e => {
      if (window._activeTab !== 'designer') return;
      if (e.key === 'Enter' && _dsnBar) dsnFinishBar();
      else if (e.key === 'Escape') { _dsnBar = null; _dsnDrag = null; dsnDraw(); }
      else if ((e.key === 'Delete' || e.key === 'Backspace') && _dsnSel != null) {
        DESIGN.magnets.splice(_dsnSel, 1); _dsnSel = null; dsnSync();
      }
    });
  }
  dsnResize(); dsnSync();
  dsnLoadOptMeta();
}
function dsnResize() {
  if (!_dsnCanvas) return;
  const r = _dsnCanvas.getBoundingClientRect();
  _dsnCanvas.width = Math.max(100, r.width); _dsnCanvas.height = Math.max(100, r.height);
  const d = dsnDims(), R = d.statorOD / 2 * 1.12;
  _dsnView.scale = Math.min(_dsnCanvas.width, _dsnCanvas.height) / (2 * R);
  _dsnView.cx = _dsnCanvas.width / 2; _dsnView.cy = _dsnCanvas.height / 2;
  dsnDraw();
}
// Event→mm; y wird auf ≥0 geklemmt, damit IMMER nur im halben Rotorpol (obere Hälfte,
// d-Achse = x-Achse) gezeichnet wird — die andere Hälfte entsteht durch Spiegelung.
function _evMM(e) { const r = _dsnCanvas.getBoundingClientRect(); const p = _s2mm(e.clientX - r.left, e.clientY - r.top); return [p[0], Math.max(0, p[1])]; }

function dsnMouseDown(e) {
  const [x, y] = _evMM(e);
  if (_dsnTool === 'magnet') { _dsnDrag = { x0: x, y0: y, x1: x, y1: y }; }
  else if (_dsnTool === 'anlage') { dsnAnlKlick(x, y); }
  else if (_dsnTool === 'barrier') {
    if (!_dsnBar) _dsnBar = { pts: [[x, y]], width: +document.getElementById('dsn_barwidth').value };
    else _dsnBar.pts.push([x, y]);
    dsnDraw();
  } else { // select: pick a master magnet
    _dsnSel = null;
    for (let i = DESIGN.magnets.length - 1; i >= 0; i--) {
      if (_dsnHitMag(DESIGN.magnets[i], x, y)) { _dsnSel = i; break; }
    }
    dsnSync();
  }
}
function dsnMouseMove(e) {
  if (_dsnTool === 'magnet' && _dsnDrag) { const [x, y] = _evMM(e); _dsnDrag.x1 = x; _dsnDrag.y1 = y; dsnDraw(); }
  else if (_dsnTool === 'barrier' && _dsnBar) { const [x, y] = _evMM(e); _dsnBar.hover = [x, y]; dsnDraw(); }
}
function dsnMouseUp() {
  if (_dsnTool === 'magnet' && _dsnDrag) {
    const dx = _dsnDrag.x1 - _dsnDrag.x0, dy = _dsnDrag.y1 - _dsnDrag.y0;
    const len = Math.hypot(dx, dy);
    if (len >= 2) {
      DESIGN.magnets.push({ r: _dsnDrag.x0, off: _dsnDrag.y0,
        ang: Math.atan2(dy, dx) * 180 / Math.PI, len,
        thick: +document.getElementById('dsn_magthick').value, pol: _dsnPol });
      _importedActive = false;   // hand-gezeichnet ⇒ nicht mehr die importierte Geometrie
      dsnSync();
    }
    _dsnDrag = null; dsnDraw();
  }
}
function dsnFinishBar() {
  if (_dsnBar && _dsnBar.pts.length >= 2) { delete _dsnBar.hover; DESIGN.barriers.push(_dsnBar); }
  _dsnBar = null; dsnSync();
}
function _dsnHitMag(m, x, y) {
  const a = m.ang * Math.PI / 180, c = Math.cos(a), s = Math.sin(a);
  const lx = (x - m.r) * c + (y - m.off) * s;      // along axis
  const tx = -(x - m.r) * s + (y - m.off) * c;      // perpendicular
  return lx >= -1 && lx <= m.len + 1 && Math.abs(tx) <= m.thick / 2 + 1;
}

function _dsnMagCorners(m, pa) {
  const a = (m.ang) * Math.PI / 180, c = Math.cos(a), s = Math.sin(a), h = m.thick / 2;
  const P = (l, t) => _rot(pa, m.r + l * c - t * s, m.off + l * s + t * c);
  return [P(0, -h), P(m.len, -h), P(m.len, h), P(0, h)];
}
// ── Anlageflächen ───────────────────────────────────────────────────────────
// Die Stellen, an denen der Magnet wirklich am Blech anliegt. Sie sind im
// Mehrkörperlauf (struct_solver="kontakt") die Last-Übertragungsflächen —
// gemessen tragen sie ~14 % der Taschenwand, und die maßgebende Blechspannung
// hängt daran um Faktor 1,9. Bis hierher waren sie für ALLE Magnete gleich
// (anlageBreiteMm/anlageProFlanke/anlageEndeMm); hier werden sie je Magnet
// zeichenbar.
//
// `u` wird von der Magnet-MITTE gemessen (−len/2 … +len/2), weil ema_kontakt
// es so liest. Der Designer rechnet sonst ab dem Magnet-ANFANG (`m.r`) — wer
// die beiden verwechselt, legt jede Anlage um eine halbe Magnetlänge daneben.
const ANL_FLAECHEN = ['flanke+', 'flanke-', 'kappe+', 'kappe-'];

// Pol-lokale Koordinaten eines Punktes IM Magnetsystem: l ab Magnetanfang, t quer.
function _dsnLokal(m, x, y) {
  const a = m.ang * Math.PI / 180, c = Math.cos(a), si = Math.sin(a);
  const dx = x - m.r, dy = y - m.off;
  return [dx * c + dy * si, -dx * si + dy * c];
}
// Die parametrische Vorgabe als Startpunkt — damit ein Magnet, den man zum
// ersten Mal anfasst, nicht mit EINER Anlage dasteht und im Löser schwimmt.
function _dsnAnlVorgabe(m) {
  const b = +(document.getElementById('dsn_anl_breite')?.value || 3);
  const n = Math.max(1, Math.min(6, +(document.getElementById('dsn_anl_je')?.value || 2)));
  const e = +(document.getElementById('dsn_anl_ende')?.value || 1.5);
  const out = [];
  for (const sg of ['+', '-']) {
    for (let k = 0; k < n; k++) {
      out.push({ f: 'flanke' + sg, u: +((k - (n - 1) / 2) * (m.len * 0.5)).toFixed(2),
                 b: Math.min(b, m.len / (2 * n)) });
    }
    if (e > 0) out.push({ f: 'kappe' + sg, u: 0, b: Math.min(e, m.thick * 0.9) });
  }
  return out;
}
function _dsnAnlListe(m) { return m.anlagen || _dsnAnlVorgabe(m); }
// Welche Anlagefläche trifft ein Klick? Gibt [magnetIndex, flaeche, u] oder null.
function _dsnAnlTreffer(x, y) {
  let best = null, bd = 1e9;
  for (let i = 0; i < DESIGN.magnets.length; i++) {
    const m = DESIGN.magnets[i], h = m.thick / 2;
    const [l, t] = _dsnLokal(m, x, y);
    if (l < -h * 2 || l > m.len + h * 2) continue;
    const dFl = Math.abs(Math.abs(t) - h);                 // Abstand zur Flanke
    const dKa = Math.min(Math.abs(l), Math.abs(l - m.len));// Abstand zum Ende
    if (dKa < dFl && dKa < h && Math.abs(t) < h) {
      if (dKa < bd) { bd = dKa; best = [i, 'kappe' + (l > m.len / 2 ? '+' : '-'), 0]; }
    } else if (dFl < h && l >= 0 && l <= m.len) {
      if (dFl < bd) { bd = dFl; best = [i, 'flanke' + (t > 0 ? '+' : '-'),
                                        +(l - m.len / 2).toFixed(2)]; }
    }
  }
  return bd < 4 ? best : null;
}
// Klick: vorhandene Anlage in der Nähe entfernen, sonst eine setzen.
function dsnAnlKlick(x, y) {
  const tr = _dsnAnlTreffer(x, y);
  if (!tr) return false;
  const [i, f, u] = tr, m = DESIGN.magnets[i];
  if (!m.anlagen) m.anlagen = _dsnAnlVorgabe(m);   // vom Vorgabestand aus weiter
  const nah = m.anlagen.findIndex(a => a.f === f &&
        (f.startsWith('kappe') || Math.abs(a.u - u) < Math.max(2, a.b)));
  if (nah >= 0) m.anlagen.splice(nah, 1);
  else {
    const br = f.startsWith('flanke')
      ? +(document.getElementById('dsn_anl_breite')?.value || 3)
      : +(document.getElementById('dsn_anl_ende')?.value || 1.5);
    m.anlagen.push({ f, u, b: br });
  }
  dsnSync();
  return true;
}
function dsnAnlZurueck(i) { delete DESIGN.magnets[i].anlagen; dsnSync(); }

function _dsnZeichneAnlagen(m, pa, hervor) {
  const a = m.ang * Math.PI / 180, c = Math.cos(a), si = Math.sin(a), h = m.thick / 2;
  const P = (l, t) => _rot(pa, m.r + l * c - t * si, m.off + l * si + t * c);
  const eigen = !!m.anlagen;
  _dsnCtx.lineCap = 'round';
  for (const al of _dsnAnlListe(m)) {
    const sg = al.f.endsWith('+') ? 1 : -1;
    let p0, p1;
    if (al.f.startsWith('flanke')) {
      const l0 = m.len / 2 + al.u - al.b / 2, l1 = m.len / 2 + al.u + al.b / 2;
      p0 = P(l0, sg * h); p1 = P(l1, sg * h);
    } else {
      const l = sg > 0 ? m.len : 0;
      p0 = P(l, -al.b / 2); p1 = P(l, al.b / 2);
    }
    const [x0, y0] = _mm2s(p0[0], p0[1]), [x1, y1] = _mm2s(p1[0], p1[1]);
    _dsnCtx.beginPath(); _dsnCtx.moveTo(x0, y0); _dsnCtx.lineTo(x1, y1);
    _dsnCtx.strokeStyle = eigen ? '#32d74b' : '#9aa5b1';
    _dsnCtx.lineWidth = hervor ? 5 : 3.5;
    _dsnCtx.stroke();
  }
  _dsnCtx.lineCap = 'butt';
}
function _dsnFillPoly(corners, fill, stroke, lw) {
  _dsnCtx.beginPath();
  corners.forEach(([x, y], i) => { const [sx, sy] = _mm2s(x, y); i ? _dsnCtx.lineTo(sx, sy) : _dsnCtx.moveTo(sx, sy); });
  _dsnCtx.closePath();
  if (fill) { _dsnCtx.fillStyle = fill; _dsnCtx.fill(); }
  if (stroke) { _dsnCtx.strokeStyle = stroke; _dsnCtx.lineWidth = lw || 1; _dsnCtx.stroke(); }
}
function _dsnDrawBar(pts, pa, col, w) {
  _dsnCtx.beginPath();
  pts.forEach(([x, y], i) => { const [rx, ry] = _rot(pa, x, y); const [sx, sy] = _mm2s(rx, ry); i ? _dsnCtx.lineTo(sx, sy) : _dsnCtx.moveTo(sx, sy); });
  _dsnCtx.strokeStyle = col; _dsnCtx.lineWidth = Math.max(2, w * _dsnView.scale);
  _dsnCtx.lineCap = 'round'; _dsnCtx.lineJoin = 'round'; _dsnCtx.stroke(); _dsnCtx.lineCap = 'butt';
}
function dsnDraw() {
  if (!_dsnCtx) return;
  const d = dsnDims(), W = _dsnCanvas.width, H = _dsnCanvas.height;
  _dsnCtx.clearRect(0, 0, W, H);
  const circle = (r, fill, stroke) => {
    _dsnCtx.beginPath(); const [cx, cy] = [_dsnView.cx, _dsnView.cy];
    _dsnCtx.arc(cx, cy, r * _dsnView.scale, 0, 2 * Math.PI);
    if (fill) { _dsnCtx.fillStyle = fill; _dsnCtx.fill(); }
    if (stroke) { _dsnCtx.strokeStyle = stroke; _dsnCtx.lineWidth = 1; _dsnCtx.stroke(); }
  };
  circle(d.statorOD / 2, '#15151f', '#2e5f8a');
  circle(d.statorID / 2, null, '#33415a');
  circle(d.rotorOD / 2, '#1b2330', '#4a5568');
  circle(d.shaftD / 2, '#0d0d14', '#555');
  // editing wedge (master half-pole: 0 → +π/poles)
  const half = Math.PI / d.poles;
  _dsnCtx.beginPath(); _dsnCtx.moveTo(_dsnView.cx, _dsnView.cy);
  _dsnCtx.arc(_dsnView.cx, _dsnView.cy, d.rotorOD / 2 * _dsnView.scale, 0, -half, true);
  _dsnCtx.closePath(); _dsnCtx.fillStyle = 'rgba(120,150,180,0.10)'; _dsnCtx.fill();
  // patterned preview: all poles, master + mirror, alternating polarity
  for (let p = 0; p < d.poles; p++) {
    const pa = p * 2 * Math.PI / d.poles, ps = (p % 2 === 0) ? 1 : -1;
    const master = (p === 0);
    for (let mi = 0; mi < DESIGN.magnets.length; mi++) {
      const m = DESIGN.magnets[mi];
      const disp = m.pol * ps;
      const col = disp > 0 ? '#e74c3c' : '#3498db';
      // master
      _dsnFillPoly(_dsnMagCorners(m, pa), master ? col : col + 'cc',
                   master && mi === _dsnSel ? '#ffd34d' : '#0008', master && mi === _dsnSel ? 2 : 0.5);
      // mirror across d-axis (skip if on axis)
      if (!(Math.abs(m.off) < 0.5 && Math.abs(m.ang) < 2)) {
        const mm = { r: m.r, off: -m.off, ang: -m.ang, len: m.len, thick: m.thick };
        _dsnFillPoly(_dsnMagCorners(mm, pa), col + 'cc', '#0008', 0.5);
      }
      // Anlageflächen. NICHT maßstäblich in der Dicke: sie ist der Klebespalt
      // (0,1 mm) und bei Läuferdurchmessern hier unter einem Bildpunkt. Länge
      // und Lage sind maßstäblich, die Strichstärke ist eine Marke.
      if (master) _dsnZeichneAnlagen(m, pa, mi === _dsnSel);
    }
    for (const b of DESIGN.barriers) {
      _dsnDrawBar(b.pts, pa, '#cbd5e1', b.width);
      _dsnDrawBar(b.pts.map(([x, y]) => [x, -y]), pa, '#cbd5e1', b.width);
    }
  }
  // in-progress drag/barrier
  if (_dsnDrag) {
    const [s0x, s0y] = _mm2s(_dsnDrag.x0, _dsnDrag.y0), [s1x, s1y] = _mm2s(_dsnDrag.x1, _dsnDrag.y1);
    _dsnCtx.beginPath(); _dsnCtx.moveTo(s0x, s0y); _dsnCtx.lineTo(s1x, s1y);
    _dsnCtx.strokeStyle = _dsnPol > 0 ? '#e74c3c' : '#3498db'; _dsnCtx.lineWidth = 2; _dsnCtx.stroke();
  }
  if (_dsnBar) {
    const pts = _dsnBar.hover ? _dsnBar.pts.concat([_dsnBar.hover]) : _dsnBar.pts;
    _dsnDrawBar(pts, 0, '#ffd34d', _dsnBar.width);
  }
}
function dsnSync() {
  const ml = document.getElementById('dsn_mag_list'), bl = document.getElementById('dsn_bar_list');
  document.getElementById('dsn_mag_count').textContent = `(${DESIGN.magnets.length})`;
  document.getElementById('dsn_bar_count').textContent = `(${DESIGN.barriers.length})`;
  ml.innerHTML = DESIGN.magnets.length ? DESIGN.magnets.map((m, i) =>
    `<div style="display:flex;gap:5px;align-items:center;padding:2px 0;${i === _dsnSel ? 'background:#2a2f3a;border-radius:3px' : ''}">
       <span style="color:${m.pol > 0 ? '#e74c3c' : '#3498db'}">${m.pol > 0 ? 'N' : 'S'}</span>
       <span style="flex:1">r=${m.r.toFixed(0)} off=${m.off.toFixed(0)} ${m.ang.toFixed(0)}° L=${m.len.toFixed(0)} t=${m.thick}</span>
       <span title="Anlageflächen — ⊥-Werkzeug setzt/entfernt sie" style="color:${m.anlagen ? '#32d74b' : '#8a93a0'};font-size:.7rem">⊥${_dsnAnlListe(m).length}${m.anlagen ? '' : '·V'}</span>
       ${m.anlagen ? `<button onclick="dsnAnlZurueck(${i})" title="Anlagen zurück auf die Vorgabe" style="background:#3a4a5a;width:auto;padding:1px 6px;font-size:.7rem">↺</button>` : ''}
       <button onclick="DESIGN.magnets.splice(${i},1);_dsnSel=null;dsnSync()" style="background:#7a3030;width:auto;padding:1px 7px;font-size:.7rem">✕</button>
     </div>`).join('') : '<span style="color:#777">Keine Magnete. Werkzeug „Magnet" wählen und im grauen Sektor aufziehen.</span>';
  bl.innerHTML = DESIGN.barriers.length ? DESIGN.barriers.map((b, i) =>
    `<div style="display:flex;gap:5px;align-items:center;padding:2px 0">
       <span style="flex:1">〰 ${b.pts.length} Punkte · ${b.width} mm</span>
       <button onclick="DESIGN.barriers.splice(${i},1);dsnSync()" style="background:#7a3030;width:auto;padding:1px 7px;font-size:.7rem">✕</button>
     </div>`).join('') : '<span style="color:#777">Keine Barrieren.</span>';
  dsnDraw();
}
function dsnClear() {
  if (!confirm('Designer leeren?')) return;
  DESIGN.magnets = []; DESIGN.barriers = []; _dsnSel = null; _dsnBar = null;
  // `anlagen` hängt an den Magneten und geht mit ihnen
  _importedActive = false;   // hand-geleerte Geometrie ist nicht mehr der STEP-Import
  dsnSync();
}
// Build the full /analyse payload from the current canvas design (no run).
// Shared by dsnBuild (manual run), the KI batch run and the magnet optimiser.
async function _dsnBuildPayload() {
  const d = dsnDims();
  // half-pole → full pole (master + mirror across d-axis); dedup coincident legs
  const legs = [], anl = [], onAxis = m => Math.abs(m.off) < 0.5 && Math.abs(m.ang) < 2;
  const _seen = new Set();
  const _addLeg = (r, off, ang, len, thick, sign, anlagen) => {
    const k = `${r.toFixed(1)}|${off.toFixed(1)}|${ang.toFixed(1)}|${len.toFixed(1)}`;
    if (_seen.has(k)) return; _seen.add(k);
    legs.push({ r_pos: r, offset: off, tilt_deg: ang, length: len, thickness: thick, mag_sign: sign });
    anl.push(anlagen || null);   // null = parametrische Vorgaben, NICHT "keine"
  };
  // Spiegelung an der d-Achse: (x,y)→(x,−y) und tilt→−tilt. Die Längsachse u
  // bleibt dabei erhalten, die Querachse v kippt — also tauschen flanke+ und
  // flanke−, während u und die Kappen stehen bleiben. Wer das verwechselt,
  // legt die Anlagen der gespiegelten Hälfte auf die falsche Flanke, und das
  // sieht man im Ergebnis nicht.
  const _spiegel = as => as && as.map(a => ({
    f: a.f.startsWith('flanke') ? (a.f.endsWith('+') ? 'flanke-' : 'flanke+') : a.f,
    u: a.u, b: a.b }));
  for (const m of DESIGN.magnets) {
    _addLeg(m.r, m.off, m.ang, m.len, m.thick, m.pol, m.anlagen || null);
    if (!onAxis(m)) _addLeg(m.r, -m.off, -m.ang, m.len, m.thick, m.pol,
                            _spiegel(m.anlagen));
  }
  const bars = [];
  for (const b of DESIGN.barriers) {
    bars.push({ pts: b.pts, width: b.width });
    bars.push({ pts: b.pts.map(([x, y]) => [x, -y]), width: b.width });
  }
  // reuse the form's run settings/materials, override geometry with the design
  const payload = await buildPayload();
  // Fit the slot depth into the actual stator wall so the stator gets real slots +
  // copper (not a bare sleeve): keep ≥3 mm back iron, otherwise shrink the depth.
  const _wall = Math.max(0, (d.statorOD - d.statorID) / 2);
  const _slotDepth = Math.max(4, Math.min(GEOM.slotDepth || 25, 0.6 * _wall, _wall - 3));
  payload.geom = { ...GEOM, statorOD: d.statorOD, statorID: d.statorID, rotorOD: d.rotorOD,
    shaftD: d.shaftD, p: d.poles / 2, slots: d.slots, conductorsPerSlot: d.cps,
    slotDepth: +_slotDepth.toFixed(1),
    magGapMm: +document.getElementById('dsn_maggap').value,
    // The designer draws its rotor air slots as customBarriers — the parametric
    // q/d flux-barrier toggles AND the balance-bolt holes from the Geometrie tab
    // must NOT bleed into a custom design (they'd add unrelated slots/holes on top
    // of the drawn geometry).
    genFluxBarrierQ: false, genFluxBarrierD: false, genBalanceBolts: false,
    magShape: 'custom', customLegs: legs, customBarriers: bars, axialLen: d.axial,
    // Nur mitschicken, wenn wirklich etwas gezeichnet wurde — ein Feld voller
    // `null` hiesse dasselbe wie keins und stuende nur im Payload herum.
    ...(anl.some(a => a) ? { customAnlagen: anl } : {}) };
  payload.axial_len = d.axial;
  payload.project_name = document.getElementById('project_name')?.value || 'Designer';
  // KI-Auslegung: Aufgabe/Begründung/Quelle ins Trainingsfile durchreichen.
  // Beim Bereichs-Entwurf trägt jede Variante ihren eigenen (gezogenen) Brief.
  const _av = _dsnAiVariants[_dsnActiveVariant];
  payload.design_brief     = (_av && _av.design_brief) || _dsnAiBrief || '';
  payload.design_rationale = _dsnAiRationale || '';
  payload.design_source    = payload.design_brief ? 'ki' : 'hand';
  // Bereichs-Entwurf: an festen Drehzahlen rechnen (überschreibt den von/bis-Sweep)
  if (Array.isArray(_dsnRangedRpm) && _dsnRangedRpm.length >= 2) {
    payload.rpm_list = _dsnRangedRpm;
    payload.rpm_from = _dsnRangedRpm[0];
    payload.rpm_to   = _dsnRangedRpm[_dsnRangedRpm.length - 1];
  }
  // vom Nutzer korrigiertes gut/schlecht-Urteil der aktiven KI-Variante
  // → wird als manuelles Label im Trainingsfile gespeichert (überschreibt die Auto-Sortierung)
  if (_av && _av.userVerdict) payload.design_label = _av.userVerdict;
  // STEP-Import: motor.FCStd existiert schon (mit benanntem Rotor) — run_pipeline soll
  // die Geometrie NICHT neu bauen, sondern die importierte für die Festigkeits-FEM nutzen.
  if (_importedActive) {
    payload.imported = true;
    payload.project_name = (window._activeProject && _activeProject.name) || 'STEP-Import';
    if (_importedProjectId) payload.project_id = _importedProjectId;
  }
  // Designer-/3D-Pfad ans aktive Projekt binden (Fallback, wenn kein Import läuft)
  if (!payload.project_id && window._activeProject && _activeProject.id)
    payload.project_id = _activeProject.id;
  return payload;
}

// Die gezeichnete Geometrie als STARTPUNKT an einen Agentenkopf übergeben —
// ohne Pipelinelauf. Der Payload landet als meta.json im Projekt, also genau
// dort, wo `cae_cli.py --from-project` und der Steckbrief ohnehin nachsehen:
// der Agent braucht dafür kein neues Werkzeug, er liest die Maschine in seiner
// Projektakte. Markiert wird sie als `design.vorgabe` — sonst bekäme er den
// üblichen Satz zu hören, das gebundene Projekt sei „ausdrücklich KEINE
// Vorlage", und würfe genau das weg, was hier eigens hingelegt wurde.
async function dsnAnAgent(kopf) {
  const msg = document.getElementById('dsn_agent_msg');
  if (!DESIGN.magnets.length) {
    msg.style.color = '#e57';
    msg.textContent = '⚠ Mindestens einen Magneten zeichnen — sonst gibt es keine Geometrie zu übergeben.';
    return;
  }
  msg.style.color = '#9c9'; msg.textContent = '⏳ übergebe…';
  try {
    const payload = await _dsnBuildPayload();
    const brief = (document.getElementById('dsn_agent_brief').value || '').trim();
    // In ein bestehendes aktives Projekt hinein, wenn es eines gibt — sonst legt
    // die Route ein neues an. Zwei Projekte für dieselbe Auslegung sind der
    // Anfang davon, dass später niemand mehr weiß, welches gilt.
    const pid = (window._activeProject && window._activeProject.id) || '';
    const r = await fetch('/agent/vorgabe', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ payload, brief, projekt: pid,
                             name: (document.getElementById('pj_new_name') || {}).value || '' })
    }).then(x => x.json());
    if (!r.ok) { msg.style.color = '#e57'; msg.textContent = '❌ ' + (r.grund || 'fehlgeschlagen'); return; }
    const url = '/agent?kopf=' + encodeURIComponent(kopf) + '&projekt=' + encodeURIComponent(r.id);
    msg.style.color = '#9c9';
    msg.innerHTML = '✓ übergeben an Projekt <b>' + escHtml(r.id) + '</b> — ' +
                    '<a href="' + url + '" target="_blank" style="color:#6cf">' +
                    (kopf === 'hermes' ? '🪽 Hermes' : '🤖 PI') + ' öffnen</a>';
    window.open(url, '_blank');
  } catch (e) {
    msg.style.color = '#e57'; msg.textContent = '❌ ' + e.message;
  }
}

async function dsnBuild() {
  const msg = document.getElementById('dsn_build_msg');
  if (!DESIGN.magnets.length) { msg.style.color = '#e57'; msg.textContent = '⚠ Mindestens einen Magnet zeichnen.'; return; }
  const payload = await _dsnBuildPayload();
  msg.style.color = '#9c9'; msg.textContent = '⏳ Starte Analyse…';
  _runAnalysisPayload(payload);
}

// ── KI-Entwurf (Designer-Pfad) ─────────────────────────────────────────────────
let _dsnAiVariants = [], _dsnAiBrief = '', _dsnAiRationale = '', _dsnActiveVariant = -1;
// Beim Bereichs-Entwurf gerechnete feste Drehzahlen (sonst null → normaler Sweep)
let _dsnRangedRpm = null;

// Map a design's params onto the designer form (dims) + main form (material/op),
// set the canvas half-pole, redraw. dsnBuild() then reads all of it.
function applyDesignToCanvas(design) {
  // Standardmäßig KEINE importierte Geometrie (AI-Variante/Vorlage). Der STEP-Import
  // setzt _importedActive in _onImportDone explizit NACH diesem Aufruf wieder true.
  _importedActive = false;
  const p = design.params || {};
  const set = (id, v) => { const e = document.getElementById(id); if (e && v != null) { e.value = v; e.dispatchEvent(new Event('input', {bubbles:true})); e.dispatchEvent(new Event('change', {bubbles:true})); } };
  // designer dimensions
  set('dsn_statorOD', p.statorOD); set('dsn_rotorOD', p.rotorOD); set('dsn_shaftD', p.shaftD);
  if (p.statorID != null && p.rotorOD != null) set('dsn_airgap', Math.max(0.1, Math.round((p.statorID - p.rotorOD) / 2 * 100) / 100));
  set('dsn_axial', p.axialLen);
  if (p.p != null) set('dsn_poles', p.p * 2);
  set('dsn_slots', p.slots);
  // material + operating point live in the main form; dsnBuild()/buildPayload() reads them
  set('sel_rotor_lam', p.rotor_lam); set('sel_stator_lam', p.stator_lam);
  set('sel_hairpin', p.hairpin_mat); set('sel_magnet', p.magnet); set('sel_cooling', p.cooling);
  set('sim_load', p.load_nm); set('rpm_from', p.rpm_from); set('rpm_to', p.rpm_to);
  // canvas geometry (half-pole master)
  DESIGN.magnets = (design.magnets || []).map(m => ({ r: m.r, off: m.off, ang: m.ang, len: m.len, thick: m.thick, pol: m.pol }));
  DESIGN.barriers = (design.barriers || []).map(b => ({ pts: b.pts.map(pt => [pt[0], pt[1]]), width: b.width }));
  _dsnAiRationale = design.begruendung || '';
  if (typeof dsnDraw === 'function') dsnDraw();
  if (typeof dsnSync === 'function') dsnSync();
}


// effektives Urteil einer Variante: Nutzer-Korrektur hat Vorrang vor der Auto-Heuristik
function _dsnVerdict(v) { return v.userVerdict || (v.quality || {}).verdict || null; }

function _dsnRenderVariants() {
  const box = document.getElementById('dsn_ai_variants');
  if (!_dsnAiVariants.length) { box.innerHTML = ''; return; }
  let h = '<div style="font-size:.74rem;color:#9aa;margin:4px 0">Varianten (Klick lädt auf Canvas · 👍/👎 = Urteil korrigieren):</div>';
  _dsnAiVariants.forEach((v, i) => {
    const p = v.params || {};
    const fb = v.fallback ? ' ⚙' : '';
    const verdict = _dsnVerdict(v);
    const mark = v.userVerdict ? '✎' : '';   // korrigiert?
    const badge = verdict === 'gut' ? ` <span style="color:#6c6">👍${mark}</span>`
                : verdict === 'schlecht' ? ` <span style="color:#e87">👎${mark}</span>` : '';
    const bg = (v.quality && v.quality.metrics && v.quality.metrics.B_gap) ? ` · B≈${v.quality.metrics.B_gap} T` : '';
    const act = (i === _dsnActiveVariant) ? 'outline:1px solid #6a4caf;' : '';
    const gB = (c) => `background:${verdict===c ? (c==='gut'?'#2e7d4f':'#a23b3b') : '#3a3f4a'};font-size:.72rem;padding:4px 7px;border:none;cursor:pointer`;
    h += `<div style="display:flex;gap:3px;margin-bottom:4px;align-items:stretch">`
       + `<button onclick="dsnLoadVariant(${i})" title="auf Canvas laden" style="flex:1;text-align:left;background:#2a2f3a;${act}font-size:.72rem;padding:6px 8px">`
       + `V${i+1}${fb}${badge}: ${p.magShape||'?'}, ⌀${p.rotorOD||'?'} mm, ${(p.p||0)*2} Pole, ${(v.magnets||[]).length} Magnete${bg}</button>`
       + `<button onclick="dsnSetVariantVerdict(${i},'gut')" title="als gut markieren" style="${gB('gut')}">👍</button>`
       + `<button onclick="dsnSetVariantVerdict(${i},'schlecht')" title="als schlecht markieren" style="${gB('schlecht')}">👎</button>`
       + `</div>`;
  });
  h += `<button onclick="dsnRunAllVariants()" style="width:100%;background:#2e7d32;font-size:.76rem;padding:8px;margin-top:2px">▶ Alle rechnen & vergleichen</button>`;
  h += `<button onclick="dsnQueueAllVariants()" title="Alle 👍-Varianten in die Server-Warteschlange (laufen auch bei geschlossenem Browser)" style="width:100%;background:#456;font-size:.76rem;padding:8px;margin-top:4px">➕ In Warteschlange (Tab ⏳ Jobs)</button>`;
  box.innerHTML = h;
}

// Nutzer korrigiert das gut/schlecht-Urteil einer Variante (Toggle: nochmal klicken = zurück auf Auto)
function dsnSetVariantVerdict(i, label) {
  const v = _dsnAiVariants[i]; if (!v) return;
  v.userVerdict = (v.userVerdict === label) ? null : label;
  _dsnRenderVariants();
}

function dsnLoadVariant(i) {
  const v = _dsnAiVariants[i]; if (!v) return;
  _dsnActiveVariant = i;
  applyDesignToCanvas(v);
  _dsnRenderVariants();
  const st = document.getElementById('dsn_ai_status');
  st.innerHTML = `✓ Variante ${i+1} geladen.` + (v.begruendung ? ` <span style="color:#789">${v.begruendung}</span>` : '');
}

// ✨ KI entwerfen: optionale Beschreibung + von–bis-Bereiche (inkl. Luftspalt 0,5–3 mm).
// Pro Variante werden Maße/Luftspalt zufällig gezogen + erzwungen, die KI füllt den Rest
// und zeichnet Magnete/Barrieren (nur halber Pol). Rechnung an festen Drehzahlen.
async function dsnAiGenerate() {
  const brief = document.getElementById('dsn_ai_brief').value.trim();
  const st  = document.getElementById('dsn_ai_status');
  const btn = document.getElementById('dsn_ai_btn');
  const num = id => +document.getElementById(id).value;
  const ranges = {
    statorOD: [num('dsn_rg_sod_lo'), num('dsn_rg_sod_hi')],
    axialLen: [num('dsn_rg_len_lo'), num('dsn_rg_len_hi')],
    shaftD:   [num('dsn_rg_shd_lo'), num('dsn_rg_shd_hi')],
    airgap:   [num('dsn_rg_gap_lo'), num('dsn_rg_gap_hi')],
  };
  for (const [k, r] of Object.entries(ranges)) {
    if (!(r[0] > 0) || !(r[1] > 0)) { st.style.color = '#e57'; st.textContent = `⚠ Bereich für ${k} unvollständig.`; return; }
  }
  const n = Math.max(1, Math.min(99, num('dsn_ai_n') || 3));
  btn.disabled = true; st.style.color = '#9aa'; st.textContent = '⏳ KI entwirft…';
  try {
    const r = await fetch('/design_ai_ranged', { method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ brief, ranges, n }) });
    if (!r.ok) { const e = await r.json(); st.style.color = '#e57'; st.textContent = '❌ ' + (e.error||'Start fehlgeschlagen'); btn.disabled = false; return; }
  } catch (e) { st.style.color = '#e57'; st.textContent = '❌ Server nicht erreichbar'; btn.disabled = false; return; }
  const poll = setInterval(async () => {
    let s; try { s = await fetch('/design_ai/status').then(x => x.json()); } catch (e) { return; }
    const last = (s.log||[]).slice(-1)[0] || '…';
    if (s.status === 'running') { st.textContent = '⏳ ' + last; return; }
    clearInterval(poll); btn.disabled = false;
    if (s.status === 'error') { st.style.color = '#e57'; st.textContent = '❌ ' + (s.error||'Fehler'); return; }
    const res = s.result || {};
    _dsnAiVariants = res.variants || [];
    _dsnActiveVariant = -1;
    _dsnAiBrief = brief;                  // Fallback; je-Variante-Brief steckt in design_brief
    _dsnRangedRpm = (Array.isArray(res.rpm_list) && res.rpm_list.length >= 2) ? res.rpm_list : [1000,5000,15000,20000];
    st.style.color = '#9c9';
    const regen = res.regenerated ? `, ${res.regenerated} schlechte ersetzt` : '';
    const spd = _dsnRangedRpm.join('/');
    st.textContent = `✓ ${_dsnAiVariants.length} Varianten` + (res.rag_used ? ' (mit Wissensbasis)' : '') + regen + ` — Rechnung @ ${spd} 1/min — V1 geladen.`;
    _dsnRenderVariants();
    if (_dsnAiVariants.length) dsnLoadVariant(0);
  }, 1200);
}

async function dsnRunAllVariants() {
  if (!_dsnAiVariants.length) return;
  document.getElementById('tbtn-results').disabled = false;
  switchTab('results');
  document.getElementById('analysis-progress').classList.add('show');
  document.getElementById('results-content').style.display = 'none';
  const ranIds = [];
  let skipped = 0;
  for (let i = 0; i < _dsnAiVariants.length; i++) {
    document.getElementById('progress-title').textContent = `⚙ KI-Variante ${i+1}/${_dsnAiVariants.length}`;
    try {
      _dsnActiveVariant = i;                       // damit das korrigierte Urteil mitgeht
      applyDesignToCanvas(_dsnAiVariants[i]);
      const payload = await _dsnBuildPayload();
      payload.project_name = `KI-V${i+1}`;
      // 👎: nicht rechnen, aber als „schlecht" ins Trainingsfile (mit Schnell-Kennwerten)
      if (_dsnVerdict(_dsnAiVariants[i]) === 'schlecht') {
        addLog(`👎 Variante ${i+1} übersprungen → als schlecht ins Trainingsfile`);
        try {
          await fetch('/training/design_rejected', { method:'POST', headers:{'Content-Type':'application/json'},
            body: JSON.stringify({ payload, metrics: (_dsnAiVariants[i].quality||{}).metrics || {},
                                   project_name: payload.project_name }) });
        } catch (e) { addLog('⚠ V'+(i+1)+' nicht gespeichert: '+e.message); }
        skipped++;
        continue;
      }
      const resp = await fetch('/analyse', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(payload) });
      if (!resp.ok) { addLog('❌ Variante ' + (i+1) + ' Start fehlgeschlagen'); continue; }
      const s = await _pollUntilDone();
      const cur = await fetch('/status').then(r => r.json());
      if (cur.project_id) ranIds.push(cur.project_id);
      if (s === 'error') addLog('❌ Variante ' + (i+1) + ' fehlgeschlagen');
    } catch (e) { addLog('❌ V' + (i+1) + ': ' + e.message); }
  }
  if (skipped) addLog(`ℹ ${skipped} mit 👎 bewertete Variante(n) nur als schlecht gespeichert, nicht gerechnet.`);
  switchTab('compare');
  await refreshComparePicker();
  ranIds.forEach(id => { const cb = document.querySelector(`.cmp-checkbox[value="${id}"]`); if (cb) cb.checked = true; });
  updateCompareCount();
  refreshTrainingStats();
}

// ➕ KI-Varianten als SERVER-Jobs einreihen (statt der Client-Schleife oben): identische
// Payload-Erzeugung (applyDesignToCanvas + _dsnBuildPayload); 👎-Varianten werden wie in
// dsnRunAllVariants NICHT gerechnet, sondern nur als „schlecht" ins Trainingsfile gemeldet.
async function dsnQueueAllVariants() {
  if (!_dsnAiVariants.length) return;
  const items = [];
  let skipped = 0;
  for (let i = 0; i < _dsnAiVariants.length; i++) {
    _dsnActiveVariant = i;
    applyDesignToCanvas(_dsnAiVariants[i]);
    const payload = await _dsnBuildPayload();
    payload.project_name = `KI-V${i+1}`;
    if (_dsnVerdict(_dsnAiVariants[i]) === 'schlecht') {
      try {
        await fetch('/training/design_rejected', { method:'POST', headers:{'Content-Type':'application/json'},
          body: JSON.stringify({ payload, metrics: (_dsnAiVariants[i].quality||{}).metrics || {},
                                 project_name: payload.project_name }) });
      } catch (e) {}
      skipped++;
      continue;
    }
    items.push({ type: 'analyse', title: payload.project_name, payload });
  }
  if (!items.length) { alert(skipped ? 'Alle Varianten sind mit 👎 bewertet — nichts eingereiht.' : 'Keine Varianten.'); return; }
  const ok = await enqueueJobs(items);
  if (ok && skipped) alert(`ℹ ${skipped} 👎-Variante(n) nur als schlecht gespeichert, nicht eingereiht.`);
}

// ── Per-Magnet-Fein-Optimierung ────────────────────────────────────────────────
let _dsnOptMetaLoaded = false;
async function dsnLoadOptMeta() {
  if (_dsnOptMetaLoaded) return;
  try {
    const meta = await fetch('/optimize/meta').then(x => x.json());
    const mSel = document.getElementById('dsn_opt_metric');
    const cSel = document.getElementById('dsn_opt_cmetric');
    let opts = '';
    for (const [k, v] of Object.entries(meta.metrics || {})) opts += `<option value="${k}">${v.label}</option>`;
    mSel.innerHTML = opts;
    cSel.innerHTML = '<option value="">—</option>' + opts;
    document.getElementById('dsn_opt_goal').addEventListener('change', e => {
      document.getElementById('dsn_opt_target').style.display = e.target.value === 'target' ? '' : 'none';
    });
    _dsnOptMetaLoaded = true;
  } catch (e) { /* offline */ }
}

async function dsnOptimize() {
  const st = document.getElementById('dsn_opt_status');
  const btn = document.getElementById('dsn_opt_btn');
  if (!DESIGN.magnets.length) { st.style.color = '#e57'; st.textContent = '⚠ Erst Magnete zeichnen/entwerfen.'; return; }
  const metric = document.getElementById('dsn_opt_metric').value;
  const goal   = document.getElementById('dsn_opt_goal').value;
  const objective = { metric, goal };
  if (goal === 'target') objective.target = +document.getElementById('dsn_opt_target').value;
  const constraints = [];
  const cm = document.getElementById('dsn_opt_cmetric').value;
  if (cm) constraints.push({ metric: cm, op: document.getElementById('dsn_opt_cop').value, value: +document.getElementById('dsn_opt_cval').value });
  const iterations = +document.getElementById('dsn_opt_iter').value || 20;
  const base_payload = await _dsnBuildPayload();
  const spec = { base_payload, magnets: DESIGN.magnets, barriers: DESIGN.barriers, objective, constraints, iterations };
  btn.disabled = true; st.style.color = '#9aa'; st.textContent = '⏳ Optimierung gestartet…';
  try {
    const r = await fetch('/design_optimize', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify(spec) });
    if (!r.ok) { const e = await r.json(); st.style.color = '#e57'; st.textContent = '❌ ' + (e.error||'Start fehlgeschlagen'); btn.disabled = false; return; }
  } catch (e) { st.style.color = '#e57'; st.textContent = '❌ Server nicht erreichbar'; btn.disabled = false; return; }
  const poll = setInterval(async () => {
    let s; try { s = await fetch('/design_optimize/status').then(x => x.json()); } catch (e) { return; }
    const last = (s.log||[]).slice(-1)[0] || '…';
    if (s.status === 'running') { st.textContent = '⏳ ' + last; return; }
    clearInterval(poll); btn.disabled = false;
    if (s.status === 'error') { st.style.color = '#e57'; st.textContent = '❌ ' + (s.error||'Fehler'); return; }
    const res = s.result || {};
    if (res.best_magnets && res.best_magnets.length) {
      DESIGN.magnets = res.best_magnets.map(m => ({ r:m.r, off:m.off, ang:m.ang, len:m.len, thick:m.thick, pol:m.pol }));
      if (typeof dsnDraw === 'function') dsnDraw();
      if (typeof dsnSync === 'function') dsnSync();
    }
    const bm = res.best_metrics || {}, base = res.base_metrics || {};
    const mv = bm[metric], bv = base[metric];
    st.style.color = '#9c9';
    st.innerHTML = `✓ Optimiert (${res.n_evaluated} Bewertungen). ${metric}: ${bv ?? '—'} → <b>${mv ?? '—'}</b>`
                 + (res.best_feasible ? '' : ' <span style="color:#e7a">(Randbed. verletzt)</span>')
                 + '. Bestes Layout auf den Canvas gezeichnet.';
  }, 1200);
}

// ── Parameterstudie für den Designer-/KI-Entwurf ────────────────────────────────
function _syncStudyDesignBanner() {
  const b = document.getElementById('study_design_banner');
  if (b) b.style.display = _studyDesignPayload ? 'block' : 'none';
}
async function dsnParamStudy() {
  const msg = document.getElementById('dsn_build_msg');
  if (!DESIGN.magnets.length) { msg.style.color = '#e57'; msg.textContent = '⚠ Erst Magnete zeichnen/entwerfen.'; return; }
  _studyDesignPayload = await _dsnBuildPayload();        // Snapshot der gezeichneten Geometrie
  switchTab('calc');                                     // ruft initParamStudy()
  if (!_optMeta) _optMeta = await fetch('/optimize/meta').then(r => r.json());
  _populateStudyParams();                               // auf custom-wirksame Parameter beschränken
  if (typeof _studyDesignPayload.rpm_to === 'number') document.getElementById('study_rpm').value = _studyDesignPayload.rpm_to;
  _syncStudyDesignBanner();
  const panel = document.getElementById('study_design_banner');
  if (panel && panel.scrollIntoView) panel.scrollIntoView({ behavior: 'smooth', block: 'center' });
}
function dsnClearStudyDesign() {
  _studyDesignPayload = null;
  _populateStudyParams();
  _syncStudyDesignBanner();
}
