// Reiterleiste, Flussweg-Umschaltung und die Vorschau der Scheibe.
//
// Was hier steht, gilt fuer die GANZE Seite: welcher Reiter sichtbar ist,
// ob radial oder axial gerechnet wird, und welches Bild die Leinwand zeigt.
// Deshalb die erste Datei -- alles Weitere haengt an `switchTab`.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Tab switching ──────────────────────────────────────────────────────────────
const TABS = ['projekt','geo','betrieb','calc','live','designer','import','axial','getriebe','em3d','oil','cfd','fx3d','doku','spraytest','ki','jobs','results','compare','agent','agenth','studio'];
// tabs that keep the live preview pane (field canvas) visible on the right
const PREVIEW_TABS = new Set(['geo','betrieb','calc','live']);
const PANEL_OF = {
  projekt:'panel-projekt',
  geo:'panel-geo', betrieb:'panel-betrieb', calc:'panel-calc', live:'panel-live',
  designer:'panel-designer', import:'panel-import', axial:'panel-axial',
  getriebe:'panel-getriebe',
  em3d:'panel-em3d', oil:'panel-oil',
  cfd:'panel-cfd', fx3d:'panel-fx3d', doku:'panel-doku', spraytest:'panel-spraytest', ki:'panel-ki', jobs:'panel-jobs',
  results:'tab-results', compare:'tab-compare', agent:'panel-agent',
  agenth:'panel-agent-hermes', studio:'panel-agent-studio'
};

// Der Agent-Rahmen wird ERST beim ersten Öffnen geladen: sonst haengt schon beim
// Seitenstart ein offener NDJSON-Strom (/agent/strom) an einem Server-Arbeiter.
// EINE Seite (/agent), zwei Rahmen — unterschieden allein durch ?kopf=.
// Die beiden Laeufe sind im Server getrennt (`ema_agent.KOEPFE`), also darf
// jeder Reiter seinen eigenen Rahmen behalten.
// Der Studio-Kopf hat eine EIGENE Seite (einspaltig, handytauglich) statt eines
// dritten Layouts in ema_agent.html -- dieselben Routen, dasselbe agent_gemein.js.
const AG_RAHMEN = {pi: 'agent-rahmen', hermes: 'agent-rahmen-hermes',
                   studio: 'agent-rahmen-studio'};
const _agSrc = k => k === 'hermes' ? '/agent?kopf=hermes'
                  : k === 'studio' ? '/studio?kopf=studio' : '/agent';
/* Der Axialfluss-Rahmen wird wie die Agentenrahmen ERST beim ersten Oeffnen
 * geladen, und er bekommt das aktive Projekt in der Adresse mit. Wechselt das
 * Projekt, wird die Quelle neu gesetzt -- sonst zeigte der Reiter weiter die
 * Scheibe eines anderen Projekts, und das saehe richtig aus. */
function _axSrc() {
  const pid = (window._activeProject || {}).id;
  return "/axialfluss/" + (pid ? "?projekt=" + encodeURIComponent(pid) : "");
}
function axActivate() {
  const f = document.getElementById('axial-rahmen');
  if (!f) return;
  const soll = _axSrc();
  if (!f.src || !f.src.endsWith(soll)) f.src = soll;
}
function axNeu() {
  const f = document.getElementById('axial-rahmen');
  if (f) f.src = _axSrc();
}

function agActivate(kopf) {
  const k = kopf || 'pi';
  const f = document.getElementById(AG_RAHMEN[k]);
  if (f && !f.src) f.src = _agSrc(k);
}
function agNeu(kopf) {
  const k = kopf || 'pi';
  const f = document.getElementById(AG_RAHMEN[k]);
  if (f) f.src = _agSrc(k);   // laedt neu; der Lauf im Server bleibt bestehen
}

/* Der Flussweg bestimmt, welche Stufen ueberhaupt laufen -- das muss am Knopf
 * stehen, nicht erst im Protokoll, wenn Stufe 0 abweist. */
/* Die Fussleiste schreibt in das EINE Feld und laesst es sein `change` werfen --
 * damit laufen Knopfbeschriftung, Hinweistext, Maschinenart-Sichtbarkeit und
 * Payload ueber genau denselben Weg wie bei einer Auswahl im Reiter. */
function footFlussSetzen(w) {
  const el = document.getElementById('flux_path');
  if (!el) return;
  el.value = w;
  el.dispatchEvent(new Event('change'));
}

function _flussZeigen() {
  const w = document.getElementById('flux_path')?.value || 'radial';
  const axial = (w === 'axial');
  // Gegenrichtung: die Fussleiste nachziehen, egal wer umgestellt hat.
  const fs = document.getElementById('foot_flux');
  if (fs && fs.value !== w) fs.value = w;
  // **Die Scheibe hat ihren eigenen CAD-Erzeuger** (`ema_axial_cad`, seit dem
  // 07.10.2026) -- hier stand bis zum 09.10.2026 das Gegenteil, und zwar an
  // drei Stellen: ein abgeschaltetes Auswahlfeld, ein Hinweis
  // „fuer die Scheibe gibt es keinen CAD-Aufbau“ und die Zeile
  // „CAD und Struktur-FEM tragen ihn nicht“. Gemeldet als
  // „Smoketest bei Axialfluss ist ohne CAD, ich moechte mit CAD“.
  // Die Auswahl Vollmotor/Laeufer bleibt abgeschaltet, aber mit dem RICHTIGEN
  // Grund: es gibt genau EIN Scheibenmodell, keine zwei.
  const cs = document.getElementById('foot_cad');
  if (cs) {
    cs.disabled = axial;
    cs.title = axial
      ? 'Die Scheibe wird von ema_axial_cad gebaut (radiale Nuten, Sektor'
        + 'magnete) — ein Modell, keine Auswahl. „🧊 CAD ansehen“ '
        + 'und der Lauf bauen sie; ema_freecad (Zylinder mit Nuten im Mantel) '
        + 'ist hier der falsche Erzeuger und wird nicht gerufen.'
      : 'Welches CAD-Modell „🧊 CAD ansehen“ baut.';
  }
  const hint = document.getElementById('flux_hint');
  const btn = document.getElementById('btn_analyse');
  if (hint) hint.innerHTML = axial
    ? 'Ringfläche, Fluss parallel zur Drehachse. Getragen: <b>analytisch</b>, '
    + '<b>Feld</b> (abgewickelter Mehrschnitt, läuft hier mit den '
    + 'Einstellungen aus ④ Berechnung), <b>3D-Feld</b> (anti-periodischer '
    + 'Ringsektor, Reiter 🧲), <b>CAD</b> (die Scheibe selbst, '
    + '<code>ema_axial_cad</code>), <b>Thermik</b> und <b>Fahrzyklus</b>. '
    + 'Nur die <b>Struktur-FEM trägt ihn nicht</b> — sie rechnet die '
    + 'Ringspannung eines rotierenden Rings, und die Scheibe trägt zwei '
    + 'andere Lasten (axialer Anzug, Fliehkraft IN der Scheibenebene; '
    + '<code>ema_axial.ruecken</code>/<code>bandage</code>). '
    + '<b>Die Maße kommen aus dem Reiter ⊙ Axialfluss</b>, nicht von '
    + 'hier: dieser Reiter hat kein axiales Feld.'
    : 'Zylindrischer Luftspalt — alle Stufen.';
  if (btn) btn.textContent = axial ? '⚙ Echte Berechnung (axial)' : '⚙ Echte Berechnung';
  if (window._updateArtVis) window._updateArtVis();
  _flussReiter(axial);
}

/* **Ein Flussweg, eine Geometrieseite.** ② Geometrie ist die Maske der
 * Radialflussmaschine — Statorbohrung, Nuttiefe, Magnettasche — und
 * ⊙ Axialfluss die der Scheibe. Beide gleichzeitig anzubieten hiess, dass
 * man an Feldern dreht, die der gewaehlte Flussweg nicht liest; gemeldet als
 * „wenn ich unten im Fluss radial oder axial waehle, soll nur das
 * entsprechende Tab aktiv sein, das andere ausgeblendet“.
 *
 * Ausgeblendet wird der REITERKNOPF, nicht die Felder: `buildPayload` liest
 * sie weiter aus dem DOM (Welle, Baulaenge, Umrichter), und ein halb
 * abgeraeumtes Formular waere ein zweiter Zustand. Steht man auf dem Reiter,
 * der verschwindet, wird auf sein Gegenstueck umgeschaltet — ein aktiver
 * Reiter ohne Knopf waere eine Seite, von der es keinen Weg zurueck gibt.
 */
function _flussReiter(axial) {
  const geo = document.getElementById('tbtn-geo');
  const ax  = document.getElementById('tbtn-axial');
  if (geo) geo.style.display = axial ? 'none' : '';
  if (ax)  ax.style.display  = axial ? '' : 'none';
  if (axial && typeof axActivate === 'function') axActivate();
  const auf = window._activeTab;
  if (axial && auf === 'geo')        switchTab('axial');
  else if (!axial && auf === 'axial') switchTab('geo');
  // Der Smoke-Test baut beim Axialfluss die Scheibe mit: ohne CAD prueft er
  // dort genau die Stufen, die ohnehin nie strittig waren. Beim Zurueckstellen
  // auf radial faellt der Haken wieder weg — sonst daechte der naechste
  // 15-Sekunden-Test minutenlang nach, ohne dass jemand das verlangt hat.
  // Von Hand umgestellt bleibt er, wie er ist (`handgesetzt`).
  const sc = document.getElementById('foot_smoke_cad');
  if (sc && !sc.dataset.handgesetzt) sc.checked = axial;
  // ⊙ Die Schnittzahl des Mehrschnitts gibt es nur axial.
  const ac = document.getElementById('axial_calc_wrap');
  if (ac) ac.style.display = axial ? '' : 'none';
  // ⊙ Was die drei Feld-Darstellungsarten axial bedeuten (und was das
  // Drehzahlband dort NICHT bewegt) — am Haekchen, nicht nur im Protokoll.
  const fh = document.getElementById('fm_axial_hinweis');
  if (fh) fh.style.display = axial ? '' : 'none';
  // ⊙ Ebenso die beiden Grenzwerte der Magnethaltung (③ Betrieb).
  const ah = document.getElementById('ax_halt_wrap');
  if (ah) ah.style.display = axial ? '' : 'none';
  if (typeof _axVorschauAnstossen === 'function') _axVorschauAnstossen();
}
document.addEventListener('DOMContentLoaded', () => {
  const el = document.getElementById('flux_path');
  if (el) el.addEventListener('change', _flussZeigen);
  _flussZeigen();
});

/* ⊙ **Die Scheibe in der Vorschau — ohne eine zweite Zeichnung.**
 *
 * Die Leinwand `#simCanvas` steht auf ② Geometrie, ③ Betrieb,
 * ④ Berechnung und ▶ Live-Simulation und zeichnet den radialen
 * Querschnitt samt FDM-Feld. Bei `fluxPath = axial` ist das die falsche
 * Maschine: ein Scheibenlaeufer ist in dieser Ebene ein Ring ohne Merkmal.
 * Gemeldet als „das heisst auch, dass in den drei Tabs Betrieb /
 * Berechnung / Live-Simulation die Axialflussmaschine erscheint“.
 *
 * Gezeichnet wird deshalb NICHT hier. Der Reiter ⊙ Axialfluss ist ein
 * <iframe> gleichen Ursprungs; seine Leinwaende `c_front` (Draufsicht) und
 * `c_schnitt` (Halbschnitt r–z) werden mit `drawImage` hereinübernommen.
 * Eine zweite Zeichenfassung im Hauptfenster waere die naechste
 * `magnetLegs`-Drift — und sie waere es an der Stelle, an der man es am
 * wenigsten merkt, weil beide Bilder „richtig aussehen“.
 *
 * Angestossen, nicht gepollt: `loop()` gibt die Leinwand frei, und neu
 * abgebildet wird nur, wenn sich am Rahmen etwas getan haben kann (Reiter-
 * wechsel, Flusswechsel, und waehrend eine Vorschauseite offen ist einmal pro
 * Sekunde — die Zeichnung dort haengt an Reglern, die der Mensch bewegt).
 */
let _axVorschauZeit = 0, _axVorschauTimer = null;
// ⊙ Der Laeuferwinkel der Vorschau und die Vorgaben fuer ihre Bewegung.
// `_AX_UPS_SICHTBAR` ist die Zahl der Umdrehungen je Sekunde, die man
// WIRKLICH sieht — die Zeitlupe folgt daraus und wird angezeigt.
let _axTheta = 0, _axLetzte = 0;
const _AX_RPM_VORGABE = 3000, _AX_UPS_SICHTBAR = 0.35;

function _axVorschauAnstossen() {
  _axVorschauZeit = 0;                       // naechster Rahmen zeichnet neu
  const axial = (document.getElementById('flux_path')?.value || 'radial') === 'axial';
  const zeigt = axial && PREVIEW_TABS.has(window._activeTab || '');
  // Die Echtzeitdaten dieser Leinwand gelten der radialen Maschine.
  const ov = document.querySelector('#preview-pane .overlay');
  if (ov) ov.classList.toggle('ax-unten', zeigt);
  if (ov) for (const k of ov.children) {
    if (k.id === 'ov_axial') k.style.display = zeigt ? '' : 'none';
    else if (k.id === 'ov_laeufer') { if (zeigt) k.style.display = 'none'; }
    else k.style.display = zeigt ? 'none' : '';
  }
  // Die Vorschau treibt sich seit dem 11.10.2026 selbst (sie LAEUFT), der
  // frueher noetige Sekundentakt gegen ein eingefrorenes Standbild entfaellt.
  if (_axVorschauTimer) { clearInterval(_axVorschauTimer); _axVorschauTimer = null; }
  if (zeigt) _axLetzte = 0;
}

/* Der Haken in `loop()`. Rueckgabe `true` heisst: die Leinwand ist bedient,
 * das radiale Raster-/Loeser-/Zeichen-Dreigespann bleibt aus. */
window._axialVorschau = function (canvas, ctx, cw, ch) {
  if ((document.getElementById('flux_path')?.value || 'radial') !== 'axial')
    return false;
  let f = document.getElementById('axial-rahmen'), w = null;
  try { w = f && f.contentWindow; } catch (e) { w = null; }
  const bereit = w && typeof w.liveRahmen === 'function'
                 && w.document && w.document.getElementById('c_front');
  if (!bereit) {
    if (typeof axActivate === 'function') axActivate();
    ctx.fillStyle = '#111'; ctx.fillRect(0, 0, cw, ch);
    ctx.fillStyle = '#9bd'; ctx.font = '13px system-ui,sans-serif';
    ctx.fillText('⊙ Axialfluss — die Zeichnung wird geladen…', 16, 30);
    ctx.fillStyle = '#889'; ctx.font = '11px system-ui,sans-serif';
    ctx.fillText('Sie entsteht im Reiter ⊙ Axialfluss; hier läuft ihr Abbild.', 16, 50);
    return true;
  }

  // ── Der Laeuferwinkel ─────────────────────────────────────────────────────
  // **Die Drehzahl kommt vom Menschen, nicht aus einem Momentenmodell.** Das
  // dq-Modell dieser Leinwand ist das der RADIALEN Maschine (psi, Ld, Lq aus
  // `livePhysikLaden`); es auf eine Scheibe anzuwenden hiesse, Zahlen unter
  // fremdem Namen zu zeigen. Gedreht wird deshalb mit dem Drehzahl-Sollwert
  // bzw. der Vorgabe, und die Anzeige sagt beides.
  const zz = (typeof window._simZustand === 'function') ? window._simZustand() : null;
  const jetzt = performance.now();
  const dt = Math.min(0.12, (_axLetzte ? (jetzt - _axLetzte) : 16) / 1000);
  _axLetzte = jetzt;
  const rpm = (zz && zz.rpmSoll > 0) ? zz.rpmSoll : _AX_RPM_VORGABE;
  // Eine echte Scheibe bei 3000 1/min dreht 50-mal je Sekunde — unsichtbar.
  // Die Zeitlupe ist deshalb NICHT Geschmack, sondern Bedingung dafuer, dass
  // man ueberhaupt etwas sieht; ihr Faktor steht in der Anzeige, sonst waere
  // das Bild eine Aussage ueber eine Drehzahl, die es nicht zeigt.
  const sichtbarUps = _AX_UPS_SICHTBAR * ((zz && zz.tempo) || 1)
                      * ((zz && zz.ultraSlow) ? 0.1 : 1);
  const zeitlupe = Math.max(1, (rpm / 60) / Math.max(sichtbarUps, 1e-6));
  if (!zz || zz.laeuft) _axTheta += 2 * Math.PI * sichtbarUps * dt;
  _axTheta %= 2 * Math.PI;

  // ── Die Bilder von der Zeichenseite holen ────────────────────────────────
  let bilder = null, stand = null;
  try { bilder = w.liveRahmen(_axTheta); stand = w.liveStand && w.liveStand(); }
  catch (e) {
    ctx.fillStyle = '#111'; ctx.fillRect(0, 0, cw, ch);
    ctx.fillStyle = '#e57'; ctx.font = '12px monospace';
    ctx.fillText('⊙ Zeichnung nicht lesbar: ' + e.message, 12, 28);
    return true;
  }
  ctx.fillStyle = '#111'; ctx.fillRect(0, 0, cw, ch);
  if (!bilder) {
    ctx.fillStyle = '#9bd'; ctx.font = '13px system-ui,sans-serif';
    ctx.fillText(stand && stand.fehler ? '⊙ ' + stand.fehler
                                       : '⊙ rechnet die Läuferstellungen …', 16, 30);
    ctx.fillStyle = '#889'; ctx.font = '11px system-ui,sans-serif';
    ctx.fillText('Einmal je Geometrie — danach ist Drehen nur noch Ablesen.', 16, 50);
    if (stand && stand.periode_grad)
      ctx.fillText('Periode ' + stand.periode_grad.toFixed(1) + '° (Läufer UND Ständer)', 16, 68);
    return true;
  }

  // Untereinander: die Vorschau ist hochkant, und die Scheibe ist rund —
  // nebeneinander bliebe von beidem die Haelfte.
  // Der Hinweiskasten sitzt beim Axialfluss unten; was er belegt, wird hier
  // ABGEZOGEN statt ueberzeichnet — gemessen am Element selbst, nicht geraten.
  const _ovEl = document.querySelector('#preview-pane .overlay.ax-unten');
  const chN = Math.max(120, ch - (_ovEl ? _ovEl.offsetHeight + 18 : 0));
  // Die Abwicklung traegt seit dem 11.10.2026 die FELDLINIEN und nicht mehr
  // nur ein Schema — sie bekommt deshalb Platz. Die Scheibe bleibt das groesste
  // Bild: sie ist das einzige, an dem man die Maschine wiedererkennt.
  const anteil = [0.44, 0.34, 0.22];
  let y = 6, bi = 0;
  for (const [txt, cv] of bilder) {
    if (!cv || !cv.width) continue;
    const sk = Math.min((cw - 12) / cv.width,
                        (chN * (anteil[bi++] || 0.2) - 18) / cv.height);
    const bw = cv.width * sk, bh = cv.height * sk;
    try { ctx.drawImage(cv, (cw - bw) / 2, y, bw, bh); } catch (e) { /* neu geladen */ }
    y += bh + 4;
    ctx.fillStyle = '#8ab'; ctx.font = '10px system-ui,sans-serif';
    ctx.textAlign = 'center'; ctx.fillText(txt, cw / 2, y + 8); ctx.textAlign = 'left';
    y += 16;
    if (y > chN - 12) break;
  }

  const t = document.getElementById('ov_axial_t');
  if (t) {
    try {
      const pp = w.P();
      t.innerHTML = `Scheibe Ø ${(2 * pp.ro).toFixed(0)} mm · λ ${pp.lam.toFixed(3)}<br>`
        + `2p ${pp.poles} · Q ${pp.q} · ${pp.nSpalte} Luftspalt`
        + `${pp.nSpalte > 1 ? 'e' : ''} · ${pp.spalt} mm<br>`
        + `Bauform ${pp.topo.toUpperCase()} · Läufer ${pp.laeufer}<br>`
        + `<b>θ ${(_axTheta * 180 / Math.PI).toFixed(0)}°</b> bei `
        + `<b>${Math.round(rpm).toLocaleString('de-DE')} 1/min</b>`
        + `${(zz && !zz.laeuft) ? ' — angehalten' : ''}<br>`
        + `Zeitlupe 1 : ${Math.round(zeitlupe).toLocaleString('de-DE')}`;
    } catch (e) { t.textContent = '—'; }
  }
  return true;
};

function switchTab(name) {
  window._activeTab = name;
  // Beim Verlassen des 3D-Feld-Tabs den Animations-Timer stoppen (kein Rendern im Hintergrund).
  if (name !== 'em3d' && typeof _e3PlayStopTimer === 'function') _e3PlayStopTimer();
  TABS.forEach(t => {
    const panel = document.getElementById(PANEL_OF[t]);
    if (panel) panel.classList.toggle('active', t === name);
    const btn = document.getElementById('tbtn-' + t);
    if (btn) btn.classList.toggle('active', t === name);
  });
  const showPreview = PREVIEW_TABS.has(name);
  const pane = document.getElementById('preview-pane');
  if (pane) pane.classList.toggle('hidden', !showPreview);
  const vsp = document.getElementById('vsplit');
  if (vsp) vsp.classList.toggle('hidden', !showPreview);
  // Two RAFs: first applies the layout change, second measures the canvas
  if (PREVIEW_TABS.has(name)) requestAnimationFrame(() => requestAnimationFrame(() => {
    if (typeof resize === 'function') resize();
  }));
  // ⊙ Wer auf eine Vorschauseite wechselt, soll die Maschine sehen, die
  // gerechnet wird — beim Axialfluss also die Scheibe und nicht den
  // radialen Querschnitt.
  if (typeof _axVorschauAnstossen === 'function') _axVorschauAnstossen();
  // Die Bruecke laeuft nur, solange der Geometrie-Reiter offen ist: sie fragt im
  // Sekundentakt, und im Hintergrund gaebe es dafuer keinen Grund.
  if (typeof brueckeStart === 'function') {
    if (name === 'geo') brueckeStart(); else brueckeStopp();
  }
  if (name === 'getriebe' && typeof _gtSync === 'function') _gtSync();
  if (name === 'ki' && typeof kiActivate === 'function') kiActivate();
  if (name === 'projekt' && typeof pjActivate === 'function') pjActivate();
  if (name === 'calc' && typeof initParamStudy === 'function') initParamStudy();
  if (name === 'designer' && typeof dsnActivate === 'function')
    requestAnimationFrame(() => requestAnimationFrame(dsnActivate));
  if (name === 'compare') { refreshComparePicker(); renderVariantList(); refreshVariantSets(); }
  if (name === 'oil') {
    // Gespeicherten Öl-Lauf des aktiven Projekts still anzeigen (wenn nichts läuft/angezeigt wird)
    const ob = document.getElementById('oil_results');
    const runningOil = document.getElementById('oil_btn')?.disabled;
    if (ob && ob.style.display === 'none' && !runningOil && typeof loadOilSaved === 'function')
      loadOilSaved(false);
    if (typeof refreshOilVariants === 'function') refreshOilVariants();
    if (typeof stRefreshFavs === 'function') stRefreshFavs();   // 💾 Spray-Favoriten-Dropdown
    if (typeof _oilBuildPinList === 'function') _oilBuildPinList();
    if (typeof _oilDrawAngleFig === 'function') _oilDrawAngleFig();  // Winkel-Skizzen aktualisieren
    if (typeof oilRefreshPresets === 'function') oilRefreshPresets();  // gespeicherte Darstellungen
  }
  if (name === 'calc' && typeof studyRefreshSaved === 'function') studyRefreshSaved();
  if (name === 'em3d' && typeof e3RefreshAnsichten === 'function') e3RefreshAnsichten();
  if (name === 'doku' && typeof brAktivieren === 'function') brAktivieren();
  if (name === 'cfd' && typeof _cfdSyncInherited === 'function') _cfdSyncInherited();
  if (name === 'fx3d' && typeof _fx3dSyncInherited === 'function') { _fx3dSyncInherited(); _fx3dKosten(); fx3dRefreshSaved(); }
  if (name === 'spraytest' && typeof stRefresh === 'function') stRefresh();
  if (name === 'jobs' && typeof jobsActivate === 'function') jobsActivate();
  if (name === 'axial' && typeof axActivate === 'function') axActivate();
  if (name === 'agent' && typeof agActivate === 'function') agActivate('pi');
  if (name === 'agenth' && typeof agActivate === 'function') agActivate('hermes');
  if (name === 'studio' && typeof agActivate === 'function') agActivate('studio');
  if (name === 'em3d' && typeof adoptEm3dGeom === 'function') {
    // Beim Öffnen die aktuelle Geometrie der gewählten Quelle übernehmen + Zusammenfassung zeigen.
    const src = document.getElementById('e3_geomsrc');
    if (src && (window._activeTab === 'em3d')) {
      // WICHTIG: die Quelle NICHT automatisch auf „Designer" umschalten, nur weil im
      // Designer-Tab (evtl. aus einer früheren Aktion) noch gezeichnete Magnete liegen.
      // Das hat den Geometrie-Tab dauerhaft ausgeblendet („Geometrie ändert sich gar
      // nicht"). Standard bleibt der Geometrie-Tab; auf „Designer" stellt der Nutzer
      // bewusst per Dropdown um (_e3SrcUserSet merkt sich diese explizite Wahl).
      if (!_e3SrcUserSet) src.value = 'geo';
      adoptEm3dGeom();
    }
    if (typeof _e3RenderSweepTable === 'function') _e3RenderSweepTable();
    if (typeof _e3TargetSync === 'function') _e3TargetSync();
  }
  if (history.replaceState) history.replaceState(null, '', '#' + name);
}

// Deep-link: open a tab directly via URL hash (e.g. …/#compare). Disabled tabs are ignored.
window.addEventListener('load', () => {
  const h = location.hash.slice(1);
  if (TABS.includes(h)) {
    const btn = document.getElementById('tbtn-' + h);
    if (btn && !btn.disabled) switchTab(h);
    else switchTab('projekt');
  } else if (h === 'projects') {
    openProjectGallery();
  } else if (h === 'optimize') {
    openOptimizer();
  } else if (h === 'text2ema') {
    openText2Ema();
  } else if (h === 'rag') {
    openRag();
  } else {
    switchTab('projekt');   // Standard-Einstieg: Projekt-Tab
  }
});
