// Die Feldanimation des Ergebnisreiters, der Laufzeitschaetzer und die
// Voreinstellungen Entwurf/Detail.
//
// `_FRAMEKOSTEN_S` ist gemessen (ema_pipeline._field_frame, je drei Frames,
// ein Lauf allein auf der Maschine) und `CALC_PRESETS` ist der Spiegel von
// `ema_text2ema.GUETE` -- `test_steckbrief.py` nagelt beide gegeneinander
// fest. Beides gehoert zusammen: die Voreinstellung setzt die Zahlen, aus
// denen der Schaetzer seine Stunden rechnet.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Field animation ────────────────────────────────────────────────────────────
let _animInterval = null;
let _totalFrames  = 36;
let _frameAngles  = [];
let _rpmList      = [];
let _rpmStats     = {};  // {rpm: {iq, id, B_gap, ...}}
let _currentRpm   = 0;
let _framesPerRpm = 36;
let _fieldMode    = 'rotate';     // bucket: rotate | react | load
let _modeMeta     = {};           // bucket → meta {mode,label,sweep_label,sweep_values,...}

const _MODE_BUCKET = { rotate: 'rotate', current_angle: 'react', load_ramp: 'load' };
// Rückfall-Beschriftung für Altprojekte, deren results.json noch keine
// `field_modes`-Metadaten trägt (nur `videos`).
const _MODE_LABEL  = { rotate: 'Rotor-Rotation', react: 'Stromwinkel (Ankerrückwirkung)',
                       load: 'Last-Rampe' };

function _frameFlatIndex(rpm, frameIdx) {
  const ri = _rpmList.indexOf(rpm);
  if (ri < 0) return frameIdx;
  return ri * _framesPerRpm + frameIdx;
}

function _modeFrameCount() {
  const m = _modeMeta[_fieldMode] || {};
  return _fieldMode === 'rotate' ? _framesPerRpm
                                 : (m.sweep_values ? m.sweep_values.length : (m.frames || 0));
}

function showFrame(n) {
  const img = document.getElementById('field-img');
  const lbl = document.getElementById('anim-angle-lbl');
  const sld = document.getElementById('anim-slider');
  const m   = _modeMeta[_fieldMode] || {};
  // Gibt es keine Rahmen, wird auch keiner angefordert. `loadProjectById` und
  // `loadResults` rufen `showFrame(0)` am Ende unbedingt — bei einem Axiallauf
  // (keine Animation, s. `renderField`) stand dann `GET /field/0` mit 404 in
  // der Konsole, und zwar bei JEDEM Laden. Ein Bild, das es nicht gibt,
  // anzufordern ist kein Fehler des Servers.
  if (!_totalFrames) { if (sld) { sld.value = 0; sld.disabled = true; } return; }
  if (_fieldMode === 'rotate') {
    img.src = '/field/' + _frameFlatIndex(_currentRpm, n) + '?t=' + Date.now();
    lbl.textContent = (_frameAngles[n] !== undefined ? _frameAngles[n].toFixed(1) : n) + '°';
  } else {
    img.src = '/field/' + _fieldMode + '/' + n + '?t=' + Date.now();
    const sv = (m.sweep_values || [])[n];
    lbl.textContent = (sv !== undefined ? sv : n) + (m.sweep_label ? ' ' + m.sweep_label.replace(/\[|\]/g, '').replace(/.*\s/, '') : '');
  }
  sld.value = n;
}

const _MODE_HINT = {
  rotate: 'Rotor dreht sich über eine Polteilung',
  react:  'Rotor steht, Stromwinkel β läuft 0…90°',
  load:   'Rotor steht, Last läuft 0…Volllast',
};

function selectFieldMode(bucket) {
  _fieldMode = bucket;
  const hint = document.getElementById('field-mode-hint');
  if (hint) hint.textContent = _MODE_HINT[bucket] || '';
  document.getElementById('rpm-row').style.display = (bucket === 'rotate') ? '' : 'none';
  const sld = document.getElementById('anim-slider');
  sld.max = Math.max(0, _modeFrameCount() - 1);
  sld.value = 0;
  showFrame(0);
}

function selectRpm(rpm) {
  _currentRpm = rpm;
  const stats = _rpmStats[rpm] || {};
  const lbl = document.getElementById('rpm-stats-lbl');
  if (lbl) {
    lbl.textContent = `i_q=${(stats.iq||0).toFixed(0)} A · i_d=${(stats.id||0).toFixed(0)} A · f=${(stats.freq||0).toFixed(0)} Hz`;
  }
  const curFrame = +document.getElementById('anim-slider').value;
  showFrame(Math.min(curFrame, _framesPerRpm - 1));
}

function toggleAnim() {
  const btn = document.getElementById('anim-play-btn');
  if (_animInterval) {
    clearInterval(_animInterval);
    _animInterval = null;
    btn.textContent = '▶ Play';
  } else {
    let frame = +document.getElementById('anim-slider').value;
    const cnt = Math.max(1, _modeFrameCount());
    _animInterval = setInterval(() => {
      frame = (frame + 1) % cnt;
      showFrame(frame);
    }, 120);
    btn.textContent = '⏸ Pause';
  }
}

// ── Laufzeitschätzung ──────────────────────────────────────────────────────────
//
// Gemessene Kosten EINES Animations-Frames (ema_pipeline._field_frame mit
// saturate=True, Projekt 20260827_170019_Alpenpass), Mittel aus drei Frames:
//
//   N          120    180    240    300    400    600
//   Sekunden   0.74   2.86   4.64   8.61   18.72  59.64
//
// Der alte Schätzer lag um mehr als eine Größenordnung zu niedrig, aus zwei
// Gründen — beide waren einmal richtig und sind es seit einer Änderung nicht mehr:
//
//  1. Er rechnete mit EINER Faktorisierung je Rotorwinkel (0,41 s bei N=300) und
//     einer billigen Rück-Substitution je Drehzahl. Seit die Frames mit
//     saturate=True laufen, trägt das nicht mehr: der Sättigungsdurchgang rechnet
//     je Frame ein neues feldabhängiges µ, das per Konstruktion nie wieder
//     vorkommt und deshalb bewusst NICHT gecacht wird. Gemessen kostet der zweite
//     Frame am GLEICHEN Winkel 8,97 s gegen 8,99 s beim ersten — der Cache spart
//     0,2 %, nicht 97 %.
//  2. Er zählte nur die Rotation. Ankerrückwirkung und Last-Rampe rendern je
//     n_frames weitere Frames desselben Preises.
//
// Alle sechs Werte der Auswahlliste sind direkt gemessen (je drei Frames, ein Lauf
// allein auf der Maschine) — es wird hier nichts fortgeschrieben. Der Exponent
// dient nur, falls jemand der Auswahlliste einen Wert hinzufügt.
const _FRAMEKOSTEN_S = { 120: 0.74, 180: 2.86, 240: 4.64, 300: 8.61, 400: 18.72, 600: 59.64 };
const _FRAMEKOSTEN_EXP = 2.51;

function _frameSekunden(N) {
  if (_FRAMEKOSTEN_S[N] !== undefined) return { s: _FRAMEKOSTEN_S[N], gemessen: true };
  const stuetz = Object.keys(_FRAMEKOSTEN_S).map(Number).sort((a, b) => a - b);
  const gross  = stuetz[stuetz.length - 1];
  if (N > gross) {
    return { s: _FRAMEKOSTEN_S[gross] * Math.pow(N / gross, _FRAMEKOSTEN_EXP), gemessen: false };
  }
  const klein = stuetz[0];
  if (N < klein) {
    return { s: _FRAMEKOSTEN_S[klein] * Math.pow(N / klein, _FRAMEKOSTEN_EXP), gemessen: false };
  }
  let lo = klein;
  for (const w of stuetz) if (w <= N) lo = w;
  const hi = stuetz.find(w => w >= N);
  const f  = (Math.log(N) - Math.log(lo)) / (Math.log(hi) - Math.log(lo));
  return { s: Math.exp(Math.log(_FRAMEKOSTEN_S[lo])
                       + f * (Math.log(_FRAMEKOSTEN_S[hi]) - Math.log(_FRAMEKOSTEN_S[lo]))),
           gemessen: false };
}

function _updateRuntimeEstimate() {
  const rFrom = +(document.getElementById('rpm_from')?.value || 5000);
  const rTo   = +(document.getElementById('rpm_to')?.value   || 20000);
  const rStep = +(document.getElementById('rpm_step')?.value || 1000);
  const nf    = +(document.getElementById('n_frames')?.value || 36);
  const fres  = +(document.getElementById('frame_resolution')?.value || 120);
  const nRpms = Math.max(1, Math.floor((rTo - rFrom) / Math.max(1, rStep)) + 1);
  // Rotation: n_rpms × n_frames.  Ankerrückwirkung und Last-Rampe: je n_frames
  // (ema_pipeline, Schleife über field_modes).
  const extra = (document.getElementById('fm_current_angle')?.checked ? nf : 0)
              + (document.getElementById('fm_load_ramp')?.checked ? nf : 0);
  const nFrames = nRpms * nf + extra;
  const k = _frameSekunden(fres);
  const total = nFrames * k.s;
  const el = document.getElementById('runtime_estimate');
  if (!el) return;
  const zeit = total < 90 ? `${total.toFixed(0)} Sek.`
             : total < 5400 ? `${(total / 60).toFixed(1)} Min.`
             : `${(total / 3600).toFixed(1)} Std.`;
  el.innerHTML =
    `${nRpms} Drehzahlen × ${nf} Frames` + (extra ? ` + ${extra} (Zusatz-Darstellungen)` : '')
    + ` = <b>${nFrames} Frames</b> × ${k.gemessen ? '' : '~'}${k.s.toFixed(2)} s `
    + `= <b>${zeit}</b>`
    + `<br/><span style="color:#888">Nur die Feld-Animation — Geometrie/CAD, Festigkeits-FEM `
    + `und Thermik kommen obendrauf (Netz-Auflösung unten nennt ihre Minuten).</span>`;
}
['rpm_from','rpm_to','rpm_step','n_frames','frame_resolution','fm_current_angle','fm_load_ramp'].forEach(id => {
  const el = document.getElementById(id);
  if (el) { el.addEventListener('input', _updateRuntimeEstimate); el.addEventListener('change', _updateRuntimeEstimate); }
});
window.addEventListener('load', _updateRuntimeEstimate);

// ── Voreinstellungen: Entwurf / Detail ─────────────────────────────────────────
//
// Gemessen am Projekt 20260827_170019_Alpenpass (vasym, p=3, 36 Nuten, Sättigung an),
// run_em_analysis über die Auflösung:
//
//   N            120     150     200     240     300     400     600
//   Sekunden     0.54    1.13    3.53    4.79    9.18    20.9    68.75
//   B_gap [T]    0.477   0.477   0.477   0.477   0.477   0.477   0.477
//   Kt           0.031   0.031   0.031   0.031   0.031   0.031   0.031
//   Br-Grundwelle -92.0%  -83.7%  -72.1%  -52.5%  -2.8%   +8.2%   0
//
// Zwei Befunde tragen die Voreinstellungen:
//   1. B_gap und Kt hängen NICHT an N — sie kommen aus _analytical_Bgap. Ein
//      Entwurfslauf verliert also keinen Kennwert, nur Bildschärfe.
//   2. Die FORM der Luftspaltwelle knickt bei N=300 ein; darunter liegt sie um die
//      Hälfte daneben. Deshalb geht KEINE Voreinstellung unter 300 — auch der
//      Entwurf nicht: seine frame_resolution 180 wird für die Berichtsbilder
//      ohnehin verdoppelt (ema_pipeline: _emf_N = min(600, max(300, 2·frame_res))
//      = 360), und das statische Feld läuft immer bei ≥ AIRGAP_PROFILE_N = 700.
//
// Bewusst NICHT in den Voreinstellungen: die Feld-Darstellungsarten
// (Ankerrückwirkung, Last-Rampe). Die sind eine Anzeigewahl, keine Genauigkeitsfrage
// — ein Knopf, der sie stillschweigend abwählt, nähme dem Nutzer etwas weg.
const CALC_PRESETS = {
  entwurf: {
    label: '📐 Entwurf',
    felder: { n_frames: 12, frame_resolution: 180, fdm_resolution: 300,
              axial_schnitte: 5, rpm_step: 1000,
              struct_solver: 'ccx', struct_mesh_mm: 4, struct_img_px: 1500,
              struct_video: false, struct_frames: 20 },
  },
  detail: {
    label: '🔬 Detail',
    felder: { n_frames: 36, frame_resolution: 300, fdm_resolution: 800,
              axial_schnitte: 9, rpm_step: 500,
              struct_solver: 'freecad', struct_mesh_mm: 2.5, struct_img_px: 3000,
              struct_video: true, struct_frames: 48 },
  },
};

function applyCalcPreset(name) {
  const p = CALC_PRESETS[name];
  if (!p) return;
  for (const [id, v] of Object.entries(p.felder)) _setField(id, v);
  _syncCalcPresetBadge();
  if (typeof _toast === 'function') _toast(`Voreinstellung ${p.label} übernommen`);
}

// Die Marke wird aus den FELDERN abgeleitet, nicht gemerkt. Damit stimmt sie auch
// nach „Projekt als Vorlage" oder einer wiederhergestellten Sitzung — und ein
// einzeln geänderter Wert fällt sofort auf „eigene Einstellung" zurück, statt eine
// Voreinstellung zu behaupten, die nicht mehr gilt.
function _calcPresetName() {
  for (const [name, p] of Object.entries(CALC_PRESETS)) {
    const passt = Object.entries(p.felder).every(([id, v]) => {
      const el = document.getElementById(id);
      if (!el) return false;
      return (el.type === 'checkbox') ? el.checked === !!v : String(el.value) === String(v);
    });
    if (passt) return name;
  }
  return null;
}

function _syncCalcPresetBadge() {
  const el = document.getElementById('preset_badge');
  if (!el) return;
  const name = _calcPresetName();
  el.textContent = name ? CALC_PRESETS[name].label : 'eigene Einstellung';
  el.style.color = name ? (name === 'detail' ? '#8fbe6a' : '#7db9e8') : '#aaa';
}

['n_frames','frame_resolution','fdm_resolution','rpm_step','struct_solver',
 'struct_mesh_mm','struct_img_px','struct_video','struct_frames'].forEach(id => {
  const el = document.getElementById(id);
  if (el) { el.addEventListener('input', _syncCalcPresetBadge);
            el.addEventListener('change', _syncCalcPresetBadge); }
});
window.addEventListener('load', _syncCalcPresetBadge);
