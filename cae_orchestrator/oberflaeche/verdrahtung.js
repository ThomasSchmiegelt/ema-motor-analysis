// Die Knoepfe an ihre Funktionen haengen -- und sonst nichts.
//
// **Diese Datei muss ZULETZT geladen werden** (nach allen anderen ausser
// `sim.js`). In EINEM grossen <script> durfte eine Zeile ganz oben eine
// Funktion ansprechen, die tausend Zeilen weiter unten steht -- Funktions-
// deklarationen werden innerhalb eines Skripts hochgezogen. Ueber mehrere
// Dateien verteilt gilt das nicht mehr: `startAnalysis` steht in
// `formular.js`, `openFreeCAD` in `ergebnis.js`, `onProjectSelect` in
// `projekt.js`. Deshalb stehen die Zuweisungen hier und nicht dort.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

document.getElementById('btn_analyse').addEventListener('click', startAnalysis);
document.getElementById('btn_queue').addEventListener('click', async () => {
  // Aktuelle Formular-Berechnung als Server-Job einreihen (statt sofort zu rechnen).
  const p = await buildPayload();
  const title = p.project_name || ('Analyse ' + ((p.geom && p.geom.magShape) || ''));
  await enqueueJobs([{ type: 'analyse', title, payload: p }]);
});
document.getElementById('btn_cad_preview').addEventListener('click', startCadPreview);
document.getElementById('btn_smoke').addEventListener('click', startSmokeTest);
document.getElementById('btn_freecad').addEventListener('click', openFreeCAD);
document.getElementById('btn_step').addEventListener('click', downloadStep);
// (Bericht-Knöpfe haben inline onclick="generateReport(...)" auf Tab ① Projekt)
document.getElementById('project_load').addEventListener('change', onProjectSelect);
document.getElementById('sel_cycle').addEventListener('change', e => {
  const v = e.target.value;
  document.getElementById('csv_upload_wrap').style.display  = (v === 'csv')      ? 'block' : 'none';
  document.getElementById('anhaenger_hint').style.display   = (v === 'anhaenger' || v === 'both') ? 'block' : 'none';
  // The vehicle fields always describe the base car (PKW). Trailer mass, extra
  // drag and axle friction are added server-side and apply ONLY to the
  // Anhänger-Alpenpass cycle — WLTP and Autobahn always run with the base car.
});

// ── Draggable splitters (preview width + footer height; canvas resizes live) ──
(function initSplitters() {
  const ws     = document.getElementById('workspace');
  const pane   = document.getElementById('preview-pane');
  const footer = document.getElementById('footer');
  const vs     = document.getElementById('vsplit');
  const hs     = document.getElementById('hsplit');
  const live   = () => { if (typeof resize === 'function') resize(); };
  let mode = null;

  function onMove(e) {
    if (mode === 'v') {
      const r = ws.getBoundingClientRect();
      let w = r.right - e.clientX;                       // preview width from the right edge
      w = Math.max(260, Math.min(r.width - 320, w));
      pane.style.width = w + 'px';
      live();
    } else if (mode === 'h') {
      let h = window.innerHeight - e.clientY;            // footer height from the bottom
      h = Math.max(40, Math.min(window.innerHeight * 0.6, h));
      footer.style.height = h + 'px';
      live();
    }
  }
  function stop() {
    if (!mode) return;
    (mode === 'v' ? vs : hs).classList.remove('dragging');
    document.body.style.userSelect = '';
    mode = null;
    live();
  }
  function start(m, el) {
    return (e) => { mode = m; el.classList.add('dragging');
                    document.body.style.userSelect = 'none'; e.preventDefault(); };
  }
  vs.addEventListener('mousedown', start('v', vs));
  hs.addEventListener('mousedown', start('h', hs));
  window.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', stop);
})();
