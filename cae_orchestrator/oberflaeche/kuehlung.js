// Die vier Wege auf DEMSELBEN Spritzoelfall: 💧 Blender/Mantaflow
// (qualitativ), 🌊 OpenFOAM-VOF (quantitativ, liefert den HTC),
// 🌀 FluidX3D (LBM auf der GPU) und 🧪 der Spray-Pruefstand.
//
// Zusammen in EINER Datei, weil sie sich den Einstellungssatz teilen:
// `_cfdBuildPayload` und `_fx3dBuildPayload` bauen auf `_oilBuildPayload`
// auf. Ein zweiter Satz Spritzoelfelder waere die Stelle, an der die drei
// Loeser auseinanderlaufen, ohne dass es jemand merkt.
//
// Herausgeloest aus ema.html am 16.10.2026 -- unveraendert; siehe oberflaeche/LIESMICH.md.

// ── Spritzöl-Kühlung (Blender/Mantaflow) ────────────────────────────────────────
// Untermenü „einzelne Hairpins ein-/ausblenden": rein clientseitig aus GEOM.slots/
// conductorsPerSlot berechnet (Pin-Index = s*pinsProSlot + j, spiegelt die FreeCAD-Reihenfolge
// in build_full_motor_script) — kein Server-Roundtrip nötig, um die Liste zu befüllen.
function _oilBuildPinList() {
  const grid = document.getElementById('oil_pins_grid');
  if (!grid) return;
  const full = document.getElementById('oil_winding_full')?.checked;
  const secEl = document.getElementById('oil_section');
  const nSlots = full ? (GEOM.slots || 12) : Math.min(GEOM.slots || 12, +(secEl && secEl.value) || 3);
  const pinsPerSlot = Math.max(1, Math.floor((GEOM.conductorsPerSlot || 4) / 2));
  // Über einen Listen-Rebuild hinweg abgewählte Pins merken (z. B. nach „Wickelkopf komplett").
  const prevHidden = new Set(Array.from(grid.querySelectorAll('.oil-pin-ck'))
    .filter(c => !c.checked).map(c => +c.dataset.pin));
  let html = '';
  for (let s = 0; s < nSlots; s++) {
    html += '<div style="display:flex;flex-direction:column;gap:1px;padding:2px 5px;border-right:1px solid #3a3a44">';
    html += '<span style="opacity:.6">Nut ' + s + '</span>';
    for (let j = 0; j < pinsPerSlot; j++) {
      const pi = s * pinsPerSlot + j;
      const checked = prevHidden.has(pi) ? '' : 'checked';
      html += '<label style="white-space:nowrap"><input type="checkbox" class="oil-pin-ck" data-pin="' + pi + '" '
            + checked + ' style="width:auto;margin-right:3px">#' + pi + '</label>';
    }
    html += '</div>';
  }
  grid.innerHTML = html || '<i>keine Geometrie</i>';
}
function _oilHiddenPinList() {
  const grid = document.getElementById('oil_pins_grid');
  if (!grid) return [];
  return Array.from(grid.querySelectorAll('.oil-pin-ck')).filter(c => !c.checked).map(c => +c.dataset.pin);
}

// --- 🎯 Live-Skizzen der Winkeleinstellungen (Strahlrichtung) -------------------------------
// Zwei SVG-Panels, die den vier Winkelfeldern folgen: Stirnansicht (Düsen-Versatz + tangentialer
// Schwenk + Sprühkegel, Blick entlang der Motorachse) und Seitenschnitt (axiale Neigung).
// Reines Frontend — gleiche Vorzeichen-Konvention wie das Blender-Skript (positiver Versatz/
// Schwenk = mathematisch positiv um die Achse; positive Neigung = zur Blechpaket-Stirnfläche).
function _oilDrawAngleFig() {
  const box = document.getElementById('oil_angle_fig');
  if (!box) return;
  const val = id => { const el = document.getElementById(id); return el ? (+el.value || 0) : 0; };
  const offs = val('oil_nozzle_offset'), yaw = val('oil_jet_yaw');
  const tilt = val('oil_jet_tilt'),      cone = val('oil_jet_cone');
  const ringFull = !!document.getElementById('oil_ring_full')?.checked;
  const D2R = Math.PI / 180;
  // SVG-Punkt aus Polarkoordinaten (mathematisch: 90° = oben), y im Bild nach unten
  const P = (cx, cy, r, deg) => [cx + r * Math.cos(deg * D2R), cy - r * Math.sin(deg * D2R)];
  const fmt = n => n.toFixed(1);
  const line = (a, b, col, w, dash) =>
    `<line x1="${fmt(a[0])}" y1="${fmt(a[1])}" x2="${fmt(b[0])}" y2="${fmt(b[1])}" stroke="${col}"`
    + ` stroke-width="${w}"${dash ? ` stroke-dasharray="${dash}"` : ''} stroke-linecap="round"/>`;
  // Pfeil von a in Richtung dirDeg (math. Winkel), Länge L
  const arrow = (a, dirDeg, L, col, w) => {
    const b = P(a[0], a[1], L, dirDeg);
    const h1 = P(b[0], b[1], 7, dirDeg + 155), h2 = P(b[0], b[1], 7, dirDeg - 155);
    return line(a, b, col, w) + line(b, h1, col, w) + line(b, h2, col, w);
  };
  // Sprühkegel-Fläche um dirDeg (±cone), von a aus
  const coneWedge = (a, dirDeg, L, c) => {
    if (c <= 0) return '';
    const p1 = P(a[0], a[1], L, dirDeg + c), p2 = P(a[0], a[1], L, dirDeg - c);
    return `<path d="M ${fmt(a[0])} ${fmt(a[1])} L ${fmt(p1[0])} ${fmt(p1[1])} L ${fmt(p2[0])} ${fmt(p2[1])} Z"`
         + ` fill="rgba(255,60,30,.14)" stroke="rgba(255,60,30,.5)" stroke-width=".7"/>`;
  };
  const txt = (x, y, s, col, anchor) =>
    `<text x="${fmt(x)}" y="${fmt(y)}" fill="${col || '#aab'}" font-size="9.5"`
    + ` text-anchor="${anchor || 'middle'}" font-family="sans-serif">${s}</text>`;
  // Kleines Koordinatensystem (x rot, y/r grün, z blau; z = Motorachse). Eine Achse zeigt aus
  // der Bildebene → als Kreis mit Punkt (⊙). 'front' = Stirnansicht (Blick entlang der Achse):
  // z aus der Ebene, x→rechts, y↑. 'side' = Seitenschnitt: z→rechts (Achse), r↑, x aus der Ebene.
  const axesTriad = (x0, y0, mode) => {
    const C = { x: '#ef6a5a', y: '#67c777', z: '#7ab8f0', r: '#67c777' };
    const ax = (dx, dy, lbl) =>
      arrow([x0, y0], Math.atan2(dy, dx) / D2R, 19, C[lbl], 1.5) + txt(x0 + dx * 27, y0 - dy * 27 + 3, lbl, C[lbl]);
    const dot = lbl =>
      `<circle cx="${x0}" cy="${y0}" r="4.5" fill="none" stroke="${C[lbl]}" stroke-width="1.6"/>`
      + `<circle cx="${x0}" cy="${y0}" r="1.5" fill="${C[lbl]}"/>` + txt(x0 - 8, y0 - 8, lbl, C[lbl], 'end');
    if (mode === 'front')     return dot('z') + ax(1, 0, 'x') + ax(0, 1, 'y');   // Stirnansicht: z aus Ebene
    if (mode === 'install_h') return dot('x') + ax(1, 0, 'z') + ax(0, 1, 'y');   // horiz. Einbaulage: z waagerecht
    if (mode === 'install_v') return dot('x') + ax(0, 1, 'z') + ax(1, 0, 'y');   // vert. Einbaulage: z senkrecht
    return ax(1, 0, 'z') + ax(0, 1, 'r') + dot('x');                            // Seitenschnitt: z waagerecht, r↑
  };

  // ---------- Panel 1: Stirnansicht (Blick auf das Wickelkopf-Ende, Achse = Punkt) ----------
  const cx = 128, cy = 140, rCr = 50, rRing = 95, rNoz = rRing - 7;
  let s1 = '';
  s1 += `<circle cx="${cx}" cy="${cy}" r="3" fill="#8af"/>` + txt(cx, cy + 14, 'Motorachse', '#8af');
  // Wickelkopf-Kronen als Kupfer-Segmente (nur oben = Keil-Ausschnitt; voller Ring ⇒ rundum grau angedeutet)
  const wFull = !!document.getElementById('oil_winding_full')?.checked;
  const segSpan = ringFull ? 360 : 84, segN = ringFull ? 24 : 7, segA0 = 90 - segSpan / 2;
  for (let i = 0; i < segN; i++) {
    const a0 = segA0 + segSpan * (i + 0.12) / segN, a1 = segA0 + segSpan * (i + 0.88) / segN;
    const q0 = P(cx, cy, rCr, a0), q1 = P(cx, cy, rCr, a1);
    const q2 = P(cx, cy, rCr - 12, a1), q3 = P(cx, cy, rCr - 12, a0);
    // beim vollen Ring: nur der gebaute Keil = Kupfer, Rest blass — außer 🌀 Wickelkopf komplett
    const inWedge = wFull || !ringFull || (a0 > 48 && a1 < 132);
    s1 += `<path d="M ${fmt(q0[0])} ${fmt(q0[1])} A ${rCr} ${rCr} 0 0 0 ${fmt(q1[0])} ${fmt(q1[1])}`
        + ` L ${fmt(q2[0])} ${fmt(q2[1])} A ${rCr - 12} ${rCr - 12} 0 0 1 ${fmt(q3[0])} ${fmt(q3[1])} Z"`
        + ` fill="${inWedge ? '#b87333' : '#4a4a52'}" opacity="${inWedge ? '.9' : '.45'}"/>`;
  }
  s1 += txt(cx, cy - 16, 'Wickelköpfe', '#e0a060');
  // Spritzring: voller Kreis oder Bogen über dem Ausschnitt (Rest gestrichelt blass)
  if (ringFull) {
    s1 += `<circle cx="${cx}" cy="${cy}" r="${rRing}" fill="none" stroke="#99a" stroke-width="5"/>`;
  } else {
    const b0 = P(cx, cy, rRing, 34), b1 = P(cx, cy, rRing, 146);
    s1 += `<path d="M ${fmt(b1[0])} ${fmt(b1[1])} A ${rRing} ${rRing} 0 0 1 ${fmt(b0[0])} ${fmt(b0[1])}"`
        + ` fill="none" stroke="#99a" stroke-width="5"/>`
        + `<circle cx="${cx}" cy="${cy}" r="${rRing}" fill="none" stroke="#555" stroke-width="1.2" stroke-dasharray="3 5"/>`;
  }
  s1 += txt(...P(cx, cy, rRing + 17, 236), 'Spritzring', '#99a', 'start');
  // ALLE Düsen-Öffnungen (Anzahl aus „Anzahl Düsen") verteilt: voller Ring ⇒ gleichmäßig über
  // 360°, sonst über den Ringbogen — jede mit kurzem Strahlpfeil radial nach innen. Die
  // Haupt-Düse oben (90°+Versatz) zeigt zusätzlich Schwenk/Kegel im Detail.
  const nN = Math.max(1, Math.round(val('oil_nozzles') || 6));
  const thMain = 90 + offs;
  for (let k = 0; k < nN; k++) {
    const a = ringFull ? thMain + 360 * k / nN
                       : (nN === 1 ? thMain : 46 + 88 * k / (nN - 1) + offs);
    const dAng = ((a - thMain) % 360 + 360) % 360;
    if (dAng < 1 || dAng > 359) continue;               // Haupt-Düse: Detail-Zeichnung unten
    const Nk = P(cx, cy, rNoz, a);
    s1 += `<rect x="${fmt(Nk[0] - 3)}" y="${fmt(Nk[1] - 3)}" width="6" height="6" fill="#dde" `
        + `transform="rotate(${fmt(-(a - 90))} ${fmt(Nk[0])} ${fmt(Nk[1])})"/>`
        + arrow(Nk, a + 180, rNoz - rCr + 2, '#ff4a30', 1.3);
  }
  // Ziel (echter Kronenpunkt) oben bei 90°, Düse um den Versatz verschoben
  const thT = 90, thN = 90 + offs;
  const T = P(cx, cy, rCr - 2, thT), N = P(cx, cy, rNoz, thN);
  s1 += `<circle cx="${fmt(T[0])}" cy="${fmt(T[1])}" r="3" fill="#ffd54a"/>`
      + txt(T[0] + 9, T[1] + 3, 'Ziel', '#ffd54a', 'start');
  s1 += `<rect x="${fmt(N[0] - 3.5)}" y="${fmt(N[1] - 3.5)}" width="7" height="7" fill="#dde" `
      + `transform="rotate(${fmt(-(thN - 90))} ${fmt(N[0])} ${fmt(N[1])})"/>`
      + txt(...P(cx, cy, rRing + 12, thN + (offs >= 0 ? 12 : -12)), 'Düse', '#dde',
            offs >= 0 ? 'end' : 'start');
  // Versatz-Winkelbogen zwischen Ziel-Winkel und Düsen-Winkel
  if (Math.abs(offs) > 0.5) {
    const ra = rRing + 16, a0 = Math.min(thT, thN), a1 = Math.max(thT, thN);
    const p0 = P(cx, cy, ra, a0), p1 = P(cx, cy, ra, a1);
    s1 += `<path d="M ${fmt(p0[0])} ${fmt(p0[1])} A ${ra} ${ra} 0 0 0 ${fmt(p1[0])} ${fmt(p1[1])}"`
        + ` fill="none" stroke="#6cf" stroke-width="1.6"/>`
        + txt(...P(cx, cy, ra + 11, (a0 + a1) / 2), `Versatz ${offs}°`, '#6cf');
  }
  // Grundstrahl Düse→Ziel (gestrichelt), + Schwenk gedrehter Strahl (rot) + Kegel
  const dir0 = Math.atan2(-(T[1] - N[1]), T[0] - N[0]) / D2R;   // math. Winkel Düse→Ziel
  const dirJ = dir0 + yaw;                                       // Schwenk: math. positiv um z
  const Lj = Math.hypot(T[0] - N[0], T[1] - N[1]) * 1.25;
  if (Math.abs(yaw) > 0.5) s1 += line(N, P(N[0], N[1], Lj, dir0), '#888', 1.2, '4 4');
  s1 += coneWedge(N, dirJ, Lj, cone) + arrow(N, dirJ, Lj, '#ff4a30', 2.2);
  s1 += axesTriad(34, 64, 'front');                       // x/y/z-Achsen (z = Motorachse, aus der Ebene)
  // Live-Werte gesammelt unten (in der Grafik selbst wird es sonst zu eng)
  s1 += txt(cx, 246, `Schwenk ${yaw}°  ·  Sprühkegel ±${cone}°  ·  ${nN} Düsen`, '#ff8a70');
  const panel1 = `<div style="text-align:center"><svg width="256" height="252" viewBox="0 0 256 252">${s1}</svg>`
    + `<div style="font-size:.72rem;color:#889">Stirnansicht — Blick auf das Wickelkopf-Ende<br>`
    + `(alle Düsen aus „Anzahl Düsen"; gestrichelt = Strahl ohne Schwenk)</div></div>`;

  // ---------- Panel 2: Seitenschnitt (Motorachse waagerecht, r nach oben) ----------
  let s2 = '';
  const axY = 218;
  s2 += line([12, axY], [244, axY], '#8af', 1.2, '8 4 2 4') + txt(230, axY - 5, 'Achse (z)', '#8af', 'end');
  s2 += `<rect x="20" y="92" width="112" height="${axY - 92}" fill="#4a4a52"/>`
      + txt(76, 118, 'Blechpaket', '#aab');
  s2 += `<rect x="132" y="108" width="58" height="62" rx="7" fill="#b87333" opacity=".9"/>`
      + txt(161, 188, 'Wickelkopf', '#e0a060') + line([132, 92], [132, axY], '#666', 1, '3 3')
      + txt(128, 86, 'Stirnfläche', '#889', 'end');
  // Ring-Rohr im Schnitt: Kreis DIREKT über der Kronenflanke (gleiches x wie das Ziel), damit
  // der Grundstrahl PUR RADIAL nach innen (im Bild: senkrecht nach unten) verläuft — genau die
  // Basis, ab der auch Blender die Neigung rechnet (dort ist der Grundstrahl nahezu radial). So
  // rechnen Skizze und Simulation die axiale Neigung ab DERSELBEN Basis (0° = radial).
  const T2 = [168, 132];                                  // Kronenflanke knapp unter der Spitze
  const rx = T2[0], ry = 84;
  s2 += `<circle cx="${rx}" cy="${ry}" r="10" fill="none" stroke="#99a" stroke-width="4"/>`
      + txt(rx + 16, ry - 6, 'Ring', '#99a', 'start');
  // Düse an der Ring-Innenseite (unten), Grundstrahl radial nach innen auf die Kronen-FLANKE
  const N2 = [rx, ry + 12];
  const dir20 = Math.atan2(-(T2[1] - N2[1]), T2[0] - N2[0]) / D2R;   // = −90° (radial nach innen)
  // positive Neigung = mehr zur Stirnfläche (im Bild: nach LINKS, math. Winkel Richtung −180°)
  const dir2 = dir20 - tilt;
  const L2 = Math.hypot(T2[0] - N2[0], T2[1] - N2[1]) * 1.35;
  if (Math.abs(tilt) > 0.5) s2 += line(N2, P(N2[0], N2[1], L2, dir20), '#888', 1.2, '4 4');
  s2 += coneWedge(N2, dir2, L2, cone) + arrow(N2, dir2, L2, '#ff4a30', 2.2);
  s2 += txt(N2[0] + 14, N2[1] + 8, `Neigung ${tilt}°`, '#ff8a70', 'start');
  s2 += txt(16, 16, '+ = zur Stirnfläche', '#889', 'start')
      + txt(16, 28, '− = zur Wickelkopfspitze', '#889', 'start');
  s2 += axesTriad(30, axY - 18, 'side');                  // x/y/z-Achsen (z = Achse waagerecht, r↑)
  const panel2 = `<div style="text-align:center"><svg width="256" height="252" viewBox="0 0 256 252">${s2}</svg>`
    + `<div style="font-size:.72rem;color:#889">Seitenschnitt — Achse waagerecht<br>(axiale Neigung des Strahls)</div></div>`;

  // ---------- Panel 3: Einbaulage — wo ist UNTEN? (Schwerkraft, Gehäuse, Ablauf) ----------
  const orient = document.getElementById('oil_orientation')?.value || 'horizontal';
  const hOn  = !!document.getElementById('oil_housing')?.checked;
  const hCol = !!document.getElementById('oil_housing_collide')?.checked;
  const glass = 'rgba(120,180,240,.55)', glassFill = 'rgba(120,180,240,.07)', oilCol = '#49c0ff';
  let s3 = '';
  if (orient !== 'vertical') {
    // horizontal: Achse waagerecht — unten = Bildunterkante (quer zur Achse)
    s3 += line([16, 118], [244, 118], '#8af', 1.2, '8 4 2 4') + txt(212, 112, 'Achse (z)', '#8af', 'start');
    if (hOn) {
      s3 += `<rect x="30" y="52" width="180" height="132" rx="8" fill="${glassFill}" stroke="${glass}" stroke-width="2.5"/>`;
      s3 += `<rect x="112" y="184" width="16" height="16" fill="${glassFill}" stroke="${glass}" stroke-width="2"/>`
          + txt(134, 198, 'Ablauf', '#7ab8f0', 'start');
    }
    s3 += `<rect x="46" y="76" width="104" height="84" fill="#4a4a52"/>` + txt(98, 122, 'Blechpaket', '#aab');
    s3 += `<rect x="150" y="86" width="34" height="64" rx="6" fill="#b87333" opacity=".9"/>`
        + txt(167, 70, 'Wickelkopf', '#e0a060');
    s3 += `<circle cx="192" cy="62" r="6" fill="none" stroke="#99a" stroke-width="3"/>`
        + `<circle cx="192" cy="174" r="6" fill="none" stroke="#99a" stroke-width="3"/>`
        + txt(204, 58, 'Ring', '#99a', 'start');
    // Öl-Weg nach unten: mit Kollisionswand bis zum Glas-Boden + Ablauf, sonst „verschwindet"
    if (hOn && hCol) {
      s3 += line([192, 70], [192, 168], oilCol, 1.8, '2 4')
          + line([190, 181], [130, 183], oilCol, 1.8, '2 4')
          + arrow([130, 183], 180, 8, oilCol, 1.8)
          + txt(226, 160, 'Öl', oilCol, 'start');
    } else {
      s3 += line([192, 70], [192, 138], oilCol, 1.8, '2 4')
          + txt(198, 148, 'Öl verschwindet (Domain-Grenze)', '#889', 'end');
    }
    s3 += arrow([18, 58], -90, 46, '#ffd54a', 2) + txt(18, 48, 'g', '#ffd54a');
    s3 += axesTriad(228, 210, 'install_h');               // x/y/z-Achsen (z = Motorachse, waagerecht)
    s3 += txt(128, 236, '⬇ unten = quer zur Achse (−y)', '#ffd54a');
  } else {
    // vertikal: Achse senkrecht — Motor steht aufrecht, unten = −z entlang der Achse
    s3 += line([128, 16], [128, 222], '#8af', 1.2, '8 4 2 4') + txt(136, 26, 'Achse (z)', '#8af', 'start');
    if (hOn) {
      s3 += `<rect x="60" y="32" width="136" height="180" rx="8" fill="${glassFill}" stroke="${glass}" stroke-width="2.5"/>`;
      s3 += `<rect x="118" y="212" width="20" height="14" fill="${glassFill}" stroke="${glass}" stroke-width="2"/>`
          + txt(146, 226, 'Ablauf', '#7ab8f0', 'start');
    }
    s3 += `<rect x="80" y="88" width="96" height="112" fill="#4a4a52"/>` + txt(128, 148, 'Blechpaket', '#aab');
    s3 += `<rect x="90" y="54" width="76" height="34" rx="6" fill="#b87333" opacity=".9"/>`
        + txt(128, 48, 'Wickelkopf', '#e0a060');
    s3 += `<circle cx="72" cy="50" r="6" fill="none" stroke="#99a" stroke-width="3"/>`
        + `<circle cx="184" cy="50" r="6" fill="none" stroke="#99a" stroke-width="3"/>`
        + txt(196, 46, 'Ring', '#99a', 'start');
    if (hOn && hCol) {
      s3 += line([72, 58], [72, 206], oilCol, 1.8, '2 4')
          + line([74, 209], [116, 211], oilCol, 1.8, '2 4')
          + arrow([116, 211], 0, 8, oilCol, 1.8)
          + txt(60, 140, 'Öl', oilCol, 'end');
    } else {
      s3 += line([72, 58], [72, 150], oilCol, 1.8, '2 4')
          + txt(66, 164, 'Öl verschwindet (Domain-Grenze)', '#889', 'start');
    }
    s3 += arrow([28, 58], -90, 46, '#ffd54a', 2) + txt(28, 48, 'g', '#ffd54a');
    s3 += axesTriad(214, 210, 'install_v');               // x/y/z-Achsen (z = Motorachse, senkrecht)
    s3 += txt(128, 240, '⬇ unten = entlang der Achse (−z)', '#ffd54a');
  }
  const cap3 = (hOn && hCol) ? 'Kollisionswand: Öl wird am Glas gefangen → Ablauf'
             : hOn ? 'Sichtwand: Öl läuft aus dem berechneten Bereich'
                   : 'ohne Gehäuse';
  const panel3 = `<div style="text-align:center"><svg width="256" height="252" viewBox="0 0 256 252">${s3}</svg>`
    + `<div style="font-size:.72rem;color:#889">Einbaulage „${orient === 'vertical' ? 'vertikal' : 'horizontal'}" — wo ist unten?<br>(${cap3})</div></div>`;

  box.innerHTML = panel1 + panel2 + panel3;
  _oilRecommendRes();
}

// Auflösungs-Empfehlung aus dem Bohrungs-Ø: der Freistrahl braucht ≥~3 Zellen über die
// Bohrung, sonst bildet der FLIP-Löser kein zusammenhängendes Öl-Mesh (der Strahl
// „verschwindet"). Die Voxelgröße ≈ 2·halbe Domain-Spanne / Auflösung; die Domain-Spanne
// hängt stark davon ab, ob die Kollisionswand 🧱 aktiv ist (dann bis zur Gehäuse-Innenwand
// ≈ ½·Stator-Ø) oder die Domain auf den Wickelkopf fokussiert ist (viel kleiner). Näherung,
// deckt sich mit den gemessenen Fällen (Stator-Ø 260, 🧱 an, RES 260 ⇒ Voxel ≈ 0,98 mm).
function _oilRecommendRes() {
  const el = document.getElementById('oil_res_hint');
  if (!el) return;
  const num = (id, d) => { const e = document.getElementById(id); const v = e ? +e.value : NaN; return isFinite(v) && v > 0 ? v : d; };
  const ck  = id => { const e = document.getElementById(id); return e ? !!e.checked : false; };
  const statOD = num('statorOD', 200);
  const nozD   = num('oil_nozzle_d', 1);
  const curRes = num('oil_res', 72);
  const collide = ck('oil_housing') && ck('oil_housing_collide') && !ck('oil_closeup');
  // halbe Domain-Spanne [mm]: 🧱 an ⇒ ~½·Stator-Ø (+Wand); sonst fokussiert ⇒ ~0,13·Stator-Ø
  const halfSpan = collide ? 0.53 * statOD : 0.13 * statOD;
  const Nmin = 2, Ntgt = 3;                                  // <2 = unsichtbar, ≥3 = sauber
  const resFor = n => Math.ceil(2 * halfSpan * n / Math.max(0.1, nozD) / 4) * 4;
  const recRaw = resFor(Ntgt);
  const rec = Math.min(1000, Math.max(24, recRaw));
  const voxel = 2 * halfSpan / Math.max(1, curRes);
  const cells = nozD / voxel;
  const col = cells < Nmin ? '#f0a0a0' : cells < Ntgt ? '#f0c070' : '#8fce9b';
  let msg = `<span style="color:${col}">Aktuell ~<b>${cells.toFixed(1)}</b> Zellen über die `
          + `${nozD.toFixed(1)}-mm-Bohrung (Voxel ≈ ${voxel.toFixed(2)} mm).</span> `;
  if (collide && recRaw > 1000) {
    // Selbst 1000 reicht mit 🧱 nicht → auf fokussierte Domain hinweisen (der wirksamere Hebel).
    const halfF = 0.13 * statOD, recF = Math.min(1000, Math.max(24, Math.ceil(2 * halfF * Ntgt / Math.max(0.1, nozD) / 4) * 4));
    msg += `Mit <b>🧱 Kollisionswand</b> ist die Domain zu groß — selbst 1000 Zellen lösen die `
         + `Bohrung kaum auf. Empfehlung: <b>🧱 aus</b> oder <b>Nahaufnahme</b> (fokussierte Domain), `
         + `dann genügen ≈ <b>${recF}</b> Zellen.`;
  } else {
    msg += `Empfohlen: <b>≥ ${rec}</b> Zellen (für ~${Ntgt} Zellen über die Bohrung)`;
    if (rec > curRes) msg += ` — aktuell ${curRes} ist zu grob.`;
    else msg += `.`;
  }
  el.innerHTML = msg;
}

// Gemeinsamer Payload-Builder für Voll-Lauf UND Vorschau (identische Geometrie/Richtung).
async function _oilBuildPayload() {
  const g = id => document.getElementById(id);
  const ck = id => { const el = g(id); return el ? !!el.checked : false; };
  const payload = await buildPayload();
  const show = { winding: ck('oil_show_winding'), rotor: ck('oil_show_rotor'),
                 stator: ck('oil_show_stator'), shaft: ck('oil_show_shaft'),
                 magnets: ck('oil_show_magnets') };
  const cut  = { winding: ck('oil_cut_winding'), rotor: ck('oil_cut_rotor'),
                 stator: ck('oil_cut_stator'), shaft: ck('oil_cut_shaft'),
                 magnets: ck('oil_cut_magnets') };
  payload.oil = {
    resolution:     +g('oil_res').value || 72,
    frames:         +g('oil_frames').value || 80,
    section_slots:  +g('oil_section').value || 3,
    show, cut,
    view_mode:      g('oil_view_mode').value || 'section',
    include_core:   !!(show.rotor || show.stator || show.shaft || show.magnets),
    winding_full:   ck('oil_winding_full'),
    hidden_pins:    _oilHiddenPinList(),
    viscosity:      +g('oil_visc').value || 0.004,
    surface_tension:+g('oil_surft').value || 0.01,
    pressure_bar:   +g('oil_pressure').value || 3,
    nozzle_count:   +g('oil_nozzles').value || 6,
    nozzle_d_mm:    +g('oil_nozzle_d').value || 1,
    ring_full:      ck('oil_ring_full'),
    ring_gap_mm:    +g('oil_ring_gap').value || 3,
    ring_tube_mm:   +g('oil_ring_tube').value || 6,
    orientation:    g('oil_orientation').value || 'horizontal',
    closeup:        !!g('oil_closeup').checked,
    slowmo:         +g('oil_slowmo').value || 1,
    fast:           ck('oil_fast'),
    jet_tilt_deg:   +g('oil_jet_tilt').value || 0,
    jet_yaw_deg:    +g('oil_jet_yaw').value || 0,
    nozzle_offset_deg: +(g('oil_nozzle_offset') && g('oil_nozzle_offset').value) || 0,
    jet_cone_deg:   +(g('oil_jet_cone') && g('oil_jet_cone').value) || 0,
    show_jet_line:  ck('oil_jet_line'),
    preview_turns:  +(g('oil_pv_turns') && g('oil_pv_turns').value) || 1,
    view_down:      (g('oil_view_down') && g('oil_view_down').value) || 'auto',
    show_axes:      ck('oil_show_axes'),
    material:       ck('oil_material'),
    light_preset:   (g('oil_light_preset') && g('oil_light_preset').value) || 'studio',
    smooth:         g('oil_smooth') ? !!g('oil_smooth').checked : true,
    housing:        ck('oil_housing'),
    housing_collide:ck('oil_housing_collide'),   // 🧱 Gehäuse fängt das Öl (Kollisionswand)
    housing_wall_mm:+(g('oil_housing_wall') && g('oil_housing_wall').value) || 4,
    section_cut:    ck('oil_section_cut'),       // ✂ Schnitt durch Motorachse + Düsen-Austritt
    section_cut_noz:+(g('oil_section_noz') && g('oil_section_noz').value) || 1,
    section_zoom:   +(g('oil_section_zoom') && g('oil_section_zoom').value) || 1,
    cam_view:       (g('oil_cam_view') && g('oil_cam_view').value) || 'auto',
    oil_transparency: (g('oil_transparency') ? +g('oil_transparency').value : 0.45),
    engine:         g('oil_engine').value || 'BLENDER_EEVEE',
    camera_angle_deg: (window._oilCamLockDeg != null ? window._oilCamLockDeg : null),
  };
  if (window._activeProject && window._activeProject.id) payload.project_id = window._activeProject.id;
  return payload;
}

// ➕ Spritzöl-Lauf in die Server-Warteschlange (gleiches Payload wie startOilspray).
async function queueOilspray() {
  const payload = await _oilBuildPayload();
  await enqueueJobs([{ type: 'oilspray', title: '💧 Spritzöl-Simulation', payload }],
                    document.getElementById('oil_status'));
}

// ── 🌊 OpenFOAM-VOF-Kühlrechnung (quantitativ) ──────────────────────────────────
async function _cfdBuildPayload() {
  const g = id => document.getElementById(id);
  // Die GESAMTEN 💧-Einstellungen übernehmen (Geometrie + Öl + Ring/Düsen/Ausschnitt/Druck).
  // Der OpenFOAM-Tab stellt nur noch OpenFOAM-spezifische Dinge ein.
  const payload = await _oilBuildPayload();
  const oil = payload.oil || {};
  payload.cfd = {
    // ── aus dem 💧-Tab übernommen (strömungs-/geometrierelevant) ──
    pressure_bar:  +oil.pressure_bar || 3,
    nozzle_d_mm:   +oil.nozzle_d_mm  || 1,
    section_slots: +oil.section_slots || 3,
    // ── OpenFOAM-spezifisch (nur hier eingestellt) ──
    end_time:      +g('cfd_endtime').value || 0.05,
    n_cells:       +g('cfd_ncells').value || 44,
    refine:        +g('cfd_refine').value || 2,
    viscosity:     +g('cfd_visc').value || 4e-5,
    make_video:    g('cfd_make_video') ? !!g('cfd_make_video').checked : true,
  };
  return payload;
}

// Zeigt im 🌊-Tab, welche Werte gerade aus dem 💧-Tab übernommen werden.
function _cfdSyncInherited() {
  const el = document.getElementById('cfd_inherited');
  if (!el) return;
  const g = id => document.getElementById(id);
  const val = (id, d) => (g(id) ? (g(id).value || d) : d);
  const secStr = (val('oil_section', 3)) + ' Nuten';
  el.innerHTML =
    'Öldruck <b>' + val('oil_pressure', 3) + ' bar</b> · Düsen-Ø <b>' + val('oil_nozzle_d', 1) +
    ' mm</b> · Ausschnitt <b>' + secStr + '</b> · Düsen <b>' + val('oil_nozzles', 6) +
    '</b> · Ring-Spalt <b>' + val('oil_ring_gap', 3) + ' mm</b>';
}

async function startCfd() {
  const btn = document.getElementById('cfd_btn');
  const msg = document.getElementById('cfd_msg');
  document.getElementById('cfd_results').style.display = 'none';
  btn.disabled = true;
  document.getElementById('cfd_progress_wrap').style.display = 'block';
  document.getElementById('cfd_bar').style.width = '0%';
  document.getElementById('cfd_log').textContent = '';
  msg.style.color = '#9aa'; msg.textContent = '⏳ Starte OpenFOAM-VOF-Rechnung…';
  try {
    const payload = await _cfdBuildPayload();
    const r = await fetch('/cfd', { method: 'POST', headers: { 'Content-Type': 'application/json' },
                                    body: JSON.stringify(payload) });
    const j = await r.json();
    if (r.status === 503) {
      const ni = document.getElementById('cfd_need_install');
      if (ni) { ni.style.display = 'block'; ni.textContent = j.error || 'OpenFOAM nicht installiert.'; }
      msg.style.color = '#e88'; msg.textContent = '⚠ OpenFOAM nicht verfügbar.';
      btn.disabled = false; return;
    }
    if (!r.ok) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (j.error || 'Start fehlgeschlagen'); btn.disabled = false; return; }
    document.getElementById('cfd_abort_btn').style.display = '';
    _pollCfd();
  } catch (e) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + e.message; btn.disabled = false; }
}

async function abortCfd() {
  try { await fetch('/cfd/abort', { method: 'POST' }); } catch (e) {}
}

async function _pollCfd() {
  let s;
  try { s = await fetch('/cfd/status').then(x => x.json()); } catch (e) { setTimeout(_pollCfd, 2000); return; }
  document.getElementById('cfd_bar').style.width = (s.progress || 0) + '%';
  const logEl = document.getElementById('cfd_log');
  if (Array.isArray(s.log)) { logEl.textContent = s.log.join('\n'); logEl.scrollTop = logEl.scrollHeight; }
  if (s.status === 'running') { setTimeout(_pollCfd, 1500); return; }
  document.getElementById('cfd_btn').disabled = false;
  document.getElementById('cfd_abort_btn').style.display = 'none';
  const msg = document.getElementById('cfd_msg');
  if (s.status === 'error') { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (s.error || 'Fehler'); return; }
  if (s.status === 'aborted') { msg.style.color = '#c85'; msg.textContent = '⛔ Abgebrochen.'; return; }
  if (s.result) { _renderCfd(s.result); msg.style.color = '#6c6'; msg.textContent = '✓ Fertig.'; }
}

function _renderCfd(res) {
  const box = document.getElementById('cfd_results');
  if (!res) return;
  const hd = res.htc_detail || {};
  const cfg = res.config || {};
  const img = (res.images && res.images.cfd_wetting)
    ? `<img src="data:image/png;base64,${res.images.cfd_wetting}" style="width:100%;max-width:640px;border-radius:5px;cursor:zoom-in" onclick="window.open(this.src)"/>` : '';
  box.innerHTML = `
    <div class="e3-card">
      <div class="section-title">🌊 Ergebnis der VOF-Kühlrechnung</div>
      <div style="display:flex;gap:14px;flex-wrap:wrap;align-items:stretch;margin-bottom:10px">
        <div style="flex:1;min-width:180px;background:#16302a;border:1px solid #2e6a4a;border-radius:8px;padding:12px 14px">
          <div style="font-size:.74rem;color:#8ca">Effektiver Wärmeübergang (HTC)</div>
          <div style="font-size:1.6rem;color:#7fe0b0;font-weight:600">${escHtml(String(res.htc_eff))} <span style="font-size:.9rem;color:#8ca">W/m²·K</span></div>
          <div style="font-size:.72rem;color:#8ca;margin-top:3px">→ speist die Thermik (Wicklung → Kühlmittel)</div>
        </div>
        <div style="flex:1;min-width:180px;background:#1a2430;border:1px solid #2e4a6a;border-radius:8px;padding:12px 14px">
          <div style="font-size:.74rem;color:#9bd">Benetzte Wickelkopf-Fläche</div>
          <div style="font-size:1.6rem;color:#8cd0ff;font-weight:600">${escHtml(String(res.wetted_pct_mean))} <span style="font-size:.9rem;color:#9bd">%</span></div>
          <div style="font-size:.72rem;color:#9bd;margin-top:3px">Spitze ${escHtml(String(res.wetted_pct_peak))} % · ${(res.wetted_area_m2*1e4).toFixed(1)} cm²</div>
        </div>
      </div>
      <table style="width:100%;font-size:.78rem;border-collapse:collapse;margin-bottom:10px">
        <tr><td style="color:#889;padding:2px 0">Strahlgeschwindigkeit</td><td style="text-align:right;color:#cde">${escHtml(String(cfg.jet_v_mps))} m/s (${escHtml(String(cfg.pressure_bar))} bar)</td></tr>
        <tr><td style="color:#889;padding:2px 0">Re / Pr / Nu (Korrelation)</td><td style="text-align:right;color:#cde">${escHtml(String(hd.Re_jet))} / ${escHtml(String(hd.Pr))} / ${escHtml(String(hd.Nu))}</td></tr>
        <tr><td style="color:#889;padding:2px 0">Charakteristische Länge</td><td style="text-align:right;color:#cde">${escHtml(String(hd.L_char_mm))} mm</td></tr>
        <tr><td style="color:#889;padding:2px 0">Netz (Auflösung/Verfeinerung)</td><td style="text-align:right;color:#cde">${escHtml(String(cfg.n_cells))} / L${escHtml(String(cfg.refine))}</td></tr>
      </table>
      ${img}
      <div style="margin-top:8px;font-size:.74rem;color:#987;line-height:1.4">ℹ ${escHtml(res.scope_note || '')}</div>
    </div>`;

  // ── 3D-Öloberfläche: gerechnetes VOF-Video + interaktiver Browser-Viewer ──
  const pid = res.project_id || 'current';
  const vid = res.video
    ? `<video controls loop autoplay muted playsinline
         style="width:100%;max-width:720px;border-radius:6px;background:#000"
         src="/project/${encodeURIComponent(pid)}/video/cfd?t=${Date.now()}"></video>
       <div style="font-size:.72rem;color:#789;margin-top:4px">
         Gerechnete Öl/Luft-Grenzfläche (Isofläche α<sub>Öl</sub>=0.5) über die Zeit,
         nach Strömungsgeschwindigkeit |U| eingefärbt — Strahlflug, Aufprall, Filmablauf.</div>`
    : `<div style="font-size:.78rem;color:#987">Kein Video erzeugt (ffmpeg/Frames fehlen).</div>`;
  const vcard = document.createElement('div');
  vcard.className = 'e3-card';
  vcard.innerHTML = `
    <div class="section-title">🎥 3D-Öloberfläche (gerechnet) & Video</div>
    ${vid}
    <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin:10px 0 6px">
      <button onclick="_cfdViewer()" style="background:#2e6a8a;width:auto;padding:8px 14px;font-size:.82rem">🧊 Im Browser ansehen (3D, dreh-/zoombar)</button>
      <label style="font-size:.74rem;color:#9aa;display:flex;align-items:center;gap:5px">
        <input type="range" id="cfd_oil_op" min="10" max="100" value="72" style="width:110px"
          oninput="_cfdOilOpacity()"/> Öl-Transparenz</label>
    </div>
    <div id="cfd_viewer3d" style="display:none;position:relative;width:100%;height:520px;background:#0b0e12;border-radius:6px;overflow:hidden"></div>`;
  box.appendChild(vcard);
  box.style.display = 'block';
}

// ── Selbst-enthaltener vtk.js-Viewer der gerechneten Öl-Isofläche + Wickelkopf ──
let _cfdrw = null, _cfdOilActor = null;
async function _cfdViewer() {
  const div = document.getElementById('cfd_viewer3d');
  if (!div) return;
  div.style.display = 'block';
  div.innerHTML = '<div style="padding:14px;color:#9aa;font-size:.82rem">⏳ Lade 3D-Viewer…</div>';
  try {
    await _loadVtkJs();
    const rd = () => vtk.IO.XML.vtkXMLPolyDataReader.newInstance();
    const getPd = async (part) => {
      const buf = await fetch('/cfd/vtp?part=' + part + '&t=' + Date.now(), { cache: 'no-store' })
        .then(r => { if (!r.ok) throw new Error(part + '-VTP nicht verfügbar'); return r.arrayBuffer(); });
      const r = rd(); r.parseAsArrayBuffer(buf); return r.getOutputData(0);
    };
    const oilPd = await getPd('oil');
    let solidPd = null; try { solidPd = await getPd('solid'); } catch (e) {}
    div.innerHTML = '';
    if (_cfdrw) { try { _cfdrw.delete(); } catch (e) {} _cfdrw = null; }
    _cfdrw = vtk.Rendering.Misc.vtkGenericRenderWindow.newInstance({ background: [0.043, 0.055, 0.071] });
    _cfdrw.setContainer(div);
    const ren = _cfdrw.getRenderer();
    // Depth-Peeling → korrekte Transparenz der Öloberfläche über dem opaken Wickelkopf.
    try { ren.setUseDepthPeeling(true); ren.setOcclusionRatio(0.1); ren.setMaximumNumberOfPeels(4); } catch (e) {}

    // Wickelkopf-Oberfläche (Kupfer, opak) als Geometrie-Kontext.
    if (solidPd && solidPd.getNumberOfPoints() > 0) {
      const sm = vtk.Rendering.Core.vtkMapper.newInstance(); sm.setInputData(solidPd); sm.setScalarVisibility(false);
      const sa = vtk.Rendering.Core.vtkActor.newInstance(); sa.setMapper(sm);
      sa.getProperty().setColor(0.72, 0.45, 0.20);
      sa.getProperty().setAmbient(0.3); sa.getProperty().setDiffuse(0.85);
      ren.addActor(sa);
    }
    // Öl-Isofläche, nach |U| eingefärbt (Blau→Bernstein→Rot), halbtransparent.
    const arr = oilPd.getPointData().getArrayByName('Umag');
    const [lo, hi] = arr ? _e3Percentiles(arr.getData(), 0.02, 0.98) : [0, 1];
    const ctf = vtk.Rendering.Core.vtkColorTransferFunction.newInstance();
    ctf.addRGBPoint(lo, 0.10, 0.20, 0.55);
    ctf.addRGBPoint(lo + 0.35 * (hi - lo), 0.15, 0.65, 0.75);
    ctf.addRGBPoint(lo + 0.70 * (hi - lo), 0.95, 0.62, 0.12);
    ctf.addRGBPoint(hi, 0.95, 0.25, 0.15);
    const om = vtk.Rendering.Core.vtkMapper.newInstance();
    om.setInputData(oilPd); om.setLookupTable(ctf);
    om.setScalarModeToUsePointFieldData(); om.setColorByArrayName('Umag');
    om.setInterpolateScalarsBeforeMapping(true);
    _cfdOilActor = vtk.Rendering.Core.vtkActor.newInstance(); _cfdOilActor.setMapper(om);
    _cfdOilActor.getProperty().setOpacity((+document.getElementById('cfd_oil_op')?.value || 72) / 100);
    ren.addActor(_cfdOilActor);

    ren.resetCamera();
    try { const cam = ren.getActiveCamera(); cam.azimuth(35); cam.elevation(-22); ren.resetCameraClippingRange(); } catch (e) {}
    _cfdrw.resize(); _cfdrw.getRenderWindow().render();
    const tip = document.createElement('div');
    tip.style.cssText = 'position:absolute;top:6px;left:10px;font-size:.7rem;color:#789;pointer-events:none';
    tip.textContent = 'ziehen = drehen · Rad = zoomen · Farbe = |U| (Strömungsgeschwindigkeit)';
    div.appendChild(tip);
  } catch (e) {
    div.innerHTML = '<div style="padding:14px;color:#e57;font-size:.82rem">⚠ ' + escHtml(e.message) + '</div>';
  }
}
function _cfdOilOpacity() {
  if (!_cfdOilActor || !_cfdrw) return;
  _cfdOilActor.getProperty().setOpacity((+document.getElementById('cfd_oil_op').value || 72) / 100);
  _cfdrw.getRenderWindow().render();
}

// ── 🌀 FluidX3D (LBM, GPU) ───────────────────────────────────────────────────
// Erbt den GANZEN 💧-Satz (Geometrie, Druck, Düsen-Ø, Ringabstand, Ausschnitt) und
// ergänzt nur die LBM-eigenen Größen — dasselbe Verhältnis, das 🌊 zu 💧 hat. Ein
// zweiter Satz Spritzöl-Felder wäre die Stelle, an der die drei Löser auseinander-
// laufen, ohne dass es jemand merkt.
async function _fx3dBuildPayload() {
  const g = id => document.getElementById(id);
  const payload = await _oilBuildPayload();
  payload.fx3d = {
    fenster_mm: +g('fx3d_fenster').value || 48,
    n:          +g('fx3d_n').value || 208,
    dauer_ms:   +g('fx3d_dauer').value || 10,
    stoss_ms:   +g('fx3d_stoss').value || 0.7,
    bilder:     +g('fx3d_bilder').value || 24,
    fps:        +g('fx3d_fps').value || 12,
  };
  return payload;
}

function _fx3dSyncInherited() {
  const el = document.getElementById('fx3d_inherited');
  if (!el) return;
  const g = id => document.getElementById(id);
  const val = (id, d) => (g(id) ? (g(id).value || d) : d);
  el.innerHTML =
    'Öldruck <b>' + val('oil_pressure', 3) + ' bar</b> · Düsen-Ø <b>' + val('oil_nozzle_d', 1) +
    ' mm</b> · Ring-Spalt <b>' + val('oil_ring_gap', 3) + ' mm</b> · Ausschnitt <b>' +
    val('oil_section', 3) + ' Nuten</b>';
}

// Was der Fall kostet, BEVOR er läuft — gerechnet auf dem Server, nicht im Browser
// nachgebaut: die Zahl muss aus derselben Quelle kommen wie der Lauf.
let _fx3dKostenTimer = null;
function _fx3dKosten() {
  clearTimeout(_fx3dKostenTimer);
  _fx3dKostenTimer = setTimeout(async () => {
    const box = document.getElementById('fx3d_kosten');
    if (!box) return;
    const g = id => document.getElementById(id);
    try {
      const body = { geom: (typeof GEOM !== 'undefined' ? GEOM : {}),
                     oil: { nozzle_d_mm: +g('oil_nozzle_d')?.value || 1,
                            pressure_bar: +g('oil_pressure')?.value || 3 },
                     fx3d: { fenster_mm: +g('fx3d_fenster').value || 48,
                             n: +g('fx3d_n').value || 208 } };
      const r = await fetch('/fluidx3d/kosten', { method: 'POST',
        headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      const j = await r.json();
      const a = j.aufloesung || {}, v = j.vollmaschine || {};
      const warn = a.unteraufgeloest
        ? '<div style="color:#e9a;margin-top:5px">⚠ Strahl unter-aufgelöst (&lt; 2 Zellen je Bohrung) — Fenster verkleinern oder Zellzahl erhöhen.</div>' : '';
      box.innerHTML =
        '<b>' + a.n + '³</b> = ' + (a.zellen/1e6).toFixed(1) + ' Mio. Zellen · <b>' +
        (a.zelle_mm||0).toFixed(3) + ' mm</b> je Zelle · <b>' + a.zellen_je_bohrung +
        '</b> Zellen je Bohrung · ' + (a.speicher_mb||0).toFixed(0) + ' MB GPU · Strahl <b>' +
        j.strahl_mps + ' m/s</b>' + warn +
        '<div style="color:#789;margin-top:5px">Die ganze Maschine mit derselben Auflösung wären ' +
        v.n + '³ = ' + (v.zellen/1e6).toFixed(0) + ' Mio. Zellen ≈ <b>' + v.speicher_gb +
        ' GB</b> — ' + (v.passt ? 'ginge' : 'geht auf dieser Karte nicht') + '.</div>';
    } catch (e) { box.textContent = '—'; }
  }, 250);
}

async function startFluidx3d() {
  const btn = document.getElementById('fx3d_btn');
  const msg = document.getElementById('fx3d_msg');
  document.getElementById('fx3d_results').style.display = 'none';
  btn.disabled = true;
  document.getElementById('fx3d_progress_wrap').style.display = 'block';
  document.getElementById('fx3d_bar').style.width = '0%';
  document.getElementById('fx3d_log').textContent = '';
  msg.style.color = '#9aa'; msg.textContent = '⏳ Starte FluidX3D…';
  try {
    const payload = await _fx3dBuildPayload();
    const r = await fetch('/fluidx3d', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
    const j = await r.json();
    if (r.status === 503) {
      const ni = document.getElementById('fx3d_need_install');
      if (ni) { ni.style.display = 'block'; ni.textContent = j.error || 'FluidX3D nicht verfügbar.'; }
      msg.style.color = '#e88'; msg.textContent = '⚠ FluidX3D nicht verfügbar.';
      btn.disabled = false; return;
    }
    if (!r.ok) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (j.error || 'Start fehlgeschlagen'); btn.disabled = false; return; }
    document.getElementById('fx3d_abort_btn').style.display = '';
    _pollFx3d();
  } catch (e) { msg.style.color = '#e57'; msg.textContent = '⚠ ' + e.message; btn.disabled = false; }
}

async function abortFluidx3d() {
  try { await fetch('/fluidx3d/abort', { method: 'POST' }); } catch (e) {}
}

async function _pollFx3d() {
  let s;
  try { s = await fetch('/fluidx3d/status').then(x => x.json()); } catch (e) { setTimeout(_pollFx3d, 2000); return; }
  document.getElementById('fx3d_bar').style.width = (s.progress || 0) + '%';
  const logEl = document.getElementById('fx3d_log');
  if (Array.isArray(s.log)) { logEl.textContent = s.log.join('\n'); logEl.scrollTop = logEl.scrollHeight; }
  if (s.status === 'running') { setTimeout(_pollFx3d, 1500); return; }
  document.getElementById('fx3d_btn').disabled = false;
  document.getElementById('fx3d_abort_btn').style.display = 'none';
  const msg = document.getElementById('fx3d_msg');
  if (s.status === 'error') { msg.style.color = '#e57'; msg.textContent = '⚠ ' + (s.error || 'Fehler'); return; }
  if (s.status === 'aborted') { msg.style.color = '#c85'; msg.textContent = '⛔ Abgebrochen.'; return; }
  if (s.result) { _renderFx3d(s.result); fx3dRefreshSaved();
                  msg.style.color = '#6c6'; msg.textContent = '✓ Fertig.'; }
}

function _renderFx3d(res, videoSrc) {
  const box = document.getElementById('fx3d_results');
  if (!res) return;
  const cfg = res.config || {}, met = res.metrics || {}, bil = res.bilanz || {},
        auf = res.aufloesung || {}, fen = res.fenster || {}, voll = res.vollmaschine || {};
  const pid = res.project_id || (window._activeProject && window._activeProject.id) || 'current';
  const vsrc = videoSrc || ('/project/' + pid + '/video/fx3d');
  const bild = k => (res.images && res.images[k])
    ? `<img src="data:image/png;base64,${res.images[k]}" style="width:100%;max-width:560px;border-radius:5px;cursor:zoom-in" onclick="window.open(this.src)"/>` : '';
  const treffer = bil.getroffen
    ? `<span style="color:#7fe0b0">✓ der Strahl trifft</span>`
    : `<span style="color:#e9a">✗ KEIN Treffer — Düsenlage/Ölstoß prüfen</span>`;
  box.style.display = '';
  box.innerHTML = `
    <div class="e3-card">
      <div class="section-title">🌀 Ergebnis des LBM-Laufs</div>
      <div style="display:flex;gap:14px;flex-wrap:wrap;margin-bottom:10px">
        <div style="flex:1;min-width:170px;background:#231a30;border:1px solid #5a3a8a;border-radius:8px;padding:12px 14px">
          <div style="font-size:.74rem;color:#b9a">Benetzung am Kupfer</div>
          <div style="font-size:1.6rem;color:#c9a8ff;font-weight:600">${escHtml(String(bil.am_kupfer_max ?? '—'))} <span style="font-size:.9rem;color:#b9a">Zellen</span></div>
          <div style="font-size:.72rem;color:#b9a;margin-top:3px">${treffer}</div>
        </div>
        <div style="flex:1;min-width:170px;background:#1a2430;border:1px solid #2e4a6a;border-radius:8px;padding:12px 14px">
          <div style="font-size:.74rem;color:#9bd">Rechenleistung</div>
          <div style="font-size:1.6rem;color:#8cd0ff;font-weight:600">${escHtml(String(Math.round(met.mlups||0)))} <span style="font-size:.9rem;color:#9bd">MLUPS</span></div>
          <div style="font-size:.72rem;color:#9bd;margin-top:3px">${(met.sekunden||0).toFixed(1)} s für ${escHtml(String(met.t_ende_ms ? met.t_ende_ms.toFixed(2) : '—'))} ms Realzeit</div>
        </div>
        <div style="flex:1;min-width:170px;background:#16302a;border:1px solid #2e6a4a;border-radius:8px;padding:12px 14px">
          <div style="font-size:.74rem;color:#8ca">Massenerhaltung</div>
          <div style="font-size:1.6rem;color:#7fe0b0;font-weight:600">${escHtml(String(bil.masse_abweichung_pct ?? '—'))} <span style="font-size:.9rem;color:#8ca">%</span></div>
          <div style="font-size:.72rem;color:#8ca;margin-top:3px">${escHtml(String(bil.oel_start_mm3))} → ${escHtml(String(bil.oel_ende_mm3))} mm³ im Fenster</div>
        </div>
      </div>
      <table style="width:100%;font-size:.78rem;border-collapse:collapse;margin-bottom:10px">
        <tr><td style="padding:3px 6px;color:#89a">Gitter</td><td style="padding:3px 6px"><b>${auf.n}³</b> = ${((auf.zellen||0)/1e6).toFixed(1)} Mio. Zellen, ${(cfg.zelle_mm||0).toFixed(4)} mm je Zelle</td></tr>
        <tr><td style="padding:3px 6px;color:#89a">Düse</td><td style="padding:3px 6px">${cfg.nozzle_d_mm} mm Bohrung = <b>${auf.zellen_je_bohrung}</b> Zellen · ${cfg.pressure_bar} bar → ${cfg.jet_speed_mps} m/s</td></tr>
        <tr><td style="padding:3px 6px;color:#89a">Fenster</td><td style="padding:3px 6px">${cfg.fenster_mm} mm um die Krone bei r=${fen.r_krone_mm} mm, z=${fen.z_krone_mm} mm (${fen.quelle||''}) · ${fen.anlauf_mm} mm Anlauf, ${fen.kupfertiefe_mm} mm Kupfer im Bild</td></tr>
        <tr><td style="padding:3px 6px;color:#89a">Ölstoß</td><td style="padding:3px 6px">${cfg.stoss_ms} ms${cfg.stoss_gekuerzt ? ' <span style="color:#e9a">(gekürzt, sonst hätte der Wickelkopf nicht mehr ins Fenster gepasst)</span>' : ''} · simuliert ${cfg.dauer_ms} ms</td></tr>
        <tr><td style="padding:3px 6px;color:#89a">Ganze Maschine</td><td style="padding:3px 6px;color:#89a">bräuchte ${voll.n}³ ≈ ${voll.speicher_gb} GB — ${voll.passt ? 'ginge' : 'geht auf dieser Karte nicht'}</td></tr>
      </table>
      ${res.warnung ? `<div style="background:#2a2620;border:1px solid #6a5a2e;border-radius:5px;padding:8px 11px;font-size:.78rem;color:#d8c89a;margin-bottom:10px">⚠ ${escHtml(res.warnung)}</div>` : ''}
      ${res.video ? `<video src="${vsrc}" controls autoplay loop muted style="width:100%;max-width:640px;border-radius:6px"></video>` : '<div style="font-size:.78rem;color:#9aa">Kein Video erzeugt.</div>'}
      <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:10px">${bild('fx3d_benetzung')}${bild('fx3d_masse')}</div>
      <div style="margin-top:10px;font-size:.75rem;color:#9aa;line-height:1.5">${escHtml(res.note || '')}</div>
      <div style="margin-top:5px;font-size:.72rem;color:#789">${escHtml(res.lizenz || '')}</div>
    </div>`;
}

async function queueFluidx3d() {
  const payload = await _fx3dBuildPayload();
  await enqueueJobs([{ type: 'fluidx3d', title: '🌀 FluidX3D-Spritzöl (LBM)', payload }],
                    document.getElementById('fx3d_queue_msg'));
}

// ── gespeicherte Varianten (Muster: 🎞 Öl-Varianten) ─────────────────────────
async function fx3dRefreshSaved() {
  const box = document.getElementById('fx3d_saved_cards');
  if (!box) return;
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  let list = [];
  try { list = await fetch('/project/' + pid + '/fluidx3d/saved').then(r => r.json()); } catch (e) {}
  if (!Array.isArray(list) || !list.length) { box.innerHTML = '<span style="font-size:.78rem;color:#789">Noch kein Lauf gespeichert.</span>'; return; }
  box.innerHTML = list.map(v => `
    <div style="background:#141821;border:1px solid #2a3340;border-radius:6px;padding:9px 11px;min-width:220px">
      <div style="font-size:.8rem;color:#cde">${escHtml(v.timestamp || v.id)}</div>
      <div style="font-size:.72rem;color:#89a;margin:3px 0 6px">
        ${v.n}³ · ${v.zelle_mm} mm · ${v.fenster_mm} mm Fenster · ${v.pressure_bar} bar<br>
        ${Math.round(v.mlups||0)} MLUPS · ${v.getroffen ? '✓ Treffer' : '✗ kein Treffer'} (${v.am_kupfer_max||0} Zellen)
      </div>
      <button onclick="fx3dLoadSaved('${escHtml(v.id)}')" style="background:#456;width:auto;padding:5px 10px;font-size:.74rem">📂 Laden</button>
      <button onclick="fx3dDeleteSaved('${escHtml(v.id)}')" style="background:#633;width:auto;padding:5px 10px;font-size:.74rem">🗑</button>
    </div>`).join('');
}

async function fx3dLoadSaved(rid) {
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    const run = await fetch('/project/' + pid + '/fluidx3d/saved/' + rid).then(r => r.json());
    if (run && !run.error) _renderFx3d(run, run.video_src);
  } catch (e) {}
}

async function fx3dDeleteSaved(rid) {
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try { await fetch('/project/' + pid + '/fluidx3d/saved/' + rid + '/delete', { method: 'POST' }); } catch (e) {}
  fx3dRefreshSaved();
}

async function queueCfd() {
  const payload = await _cfdBuildPayload();
  await enqueueJobs([{ type: 'cfd', title: '🌊 OpenFOAM-VOF-Kühlung', payload }],
                    document.getElementById('cfd_queue_msg'));
}

// ── 💾 Darstellungs-Presets + Rechen-Pakete ─────────────────────────────────────────
window._oilPresets = [];
async function oilSavePreset() {
  const st = document.getElementById('oil_preset_status');
  const nameEl = document.getElementById('oil_preset_name');
  const name = (nameEl?.value || '').trim();
  if (!name) { if (st) st.textContent = '⚠ Bitte einen Namen eingeben.'; return; }
  try {
    const payload = await _oilBuildPayload();
    const r = await fetch('/oilspray/presets', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name, payload }) });
    if (!r.ok) throw new Error(await r.text());
    if (nameEl) nameEl.value = '';
    if (st) st.textContent = '✓ Darstellung gespeichert.';
    oilRefreshPresets();
  } catch (e) { if (st) st.textContent = '❌ ' + e.message; }
}
async function oilRefreshPresets() {
  const box = document.getElementById('oil_presets_list');
  try {
    const r = await fetch('/oilspray/presets');
    window._oilPresets = r.ok ? await r.json() : [];
  } catch (e) { window._oilPresets = []; }
  if (!box) return;
  if (!window._oilPresets.length) {
    box.innerHTML = '<div style="color:#778">Noch keine Darstellungen gespeichert.</div>';
    return;
  }
  box.innerHTML = window._oilPresets.map((p, i) =>
    `<div style="display:flex;gap:8px;align-items:center;padding:4px 0;border-bottom:1px solid #2a2a30">
       <input type="checkbox" class="oil-preset-ck" data-id="${escHtml(p.id)}" style="width:auto">
       <span style="color:#889;width:1.6em;text-align:right">${i + 1}.</span>
       <b style="flex:1">${escHtml(p.name || 'Darstellung')}</b>
       <span style="color:#778;font-size:.74rem">${escHtml(p.ts || '')}</span>
       <button onclick="oilDeletePreset('${escHtml(p.id)}')" style="background:#5a2f2f;width:auto;padding:3px 8px">✖</button>
     </div>`).join('');
}
async function oilDeletePreset(id) {
  try { await fetch('/oilspray/presets/' + encodeURIComponent(id) + '/delete', { method: 'POST' }); }
  catch (e) {}
  oilRefreshPresets();
}
async function oilQueuePackage() {
  const st = document.getElementById('oil_preset_status');
  const ids = Array.from(document.querySelectorAll('.oil-preset-ck:checked')).map(c => c.dataset.id);
  if (!ids.length) { if (st) st.textContent = '⚠ Keine Darstellung ausgewählt.'; return; }
  const items = [];
  for (const id of ids) {
    const p = window._oilPresets.find(x => x.id === id);
    if (p && p.payload) items.push({ type: 'oilspray', title: '💧 ' + (p.name || 'Darstellung'), payload: p.payload });
  }
  if (!items.length) { if (st) st.textContent = '⚠ Ausgewählte Darstellungen haben kein Payload.'; return; }
  await enqueueJobs(items, st);
}

async function startOilspray() {
  const st = document.getElementById('oil_status');
  const btn = document.getElementById('oil_btn');
  btn.disabled = true; st.style.color = '#9c9'; st.textContent = '⏳ Starte Spritzöl-Simulation…';
  document.getElementById('oil_results').style.display = 'none';
  document.getElementById('oil_progress_wrap').style.display = 'block';
  try {
    const payload = await _oilBuildPayload();
    const r = await fetch('/oilspray', { method:'POST', headers:{'Content-Type':'application/json'},
                                         body: JSON.stringify(payload) });
    if (r.status === 503) {
      const j = await r.json(); st.style.color = '#e57';
      st.innerHTML = '⚠ ' + escHtml(j.error || 'Blender fehlt').replace(/\n/g,'<br>');
      btn.disabled = false; document.getElementById('oil_progress_wrap').style.display = 'none'; return;
    }
    if (!r.ok) { const j = await r.json().catch(()=>({})); st.style.color='#e57';
      st.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false;
      document.getElementById('oil_progress_wrap').style.display = 'none'; return; }
    document.getElementById('oil_abort_btn').style.display = 'inline-block';
    _pollOil();
  } catch (e) { st.style.color='#e57'; st.textContent = 'Fehler: ' + e.message; btn.disabled = false;
    document.getElementById('oil_progress_wrap').style.display = 'none'; }
}

// Schnelle Zwischenansicht: nur Geometrie + Düsen + Strahl-Ziellinien, OHNE Fluid-Bake.
async function startOilPreview() {
  const st = document.getElementById('oil_status');
  const btn = document.getElementById('oil_btn');
  const pbtn = document.getElementById('oil_preview_btn');
  btn.disabled = true; if (pbtn) pbtn.disabled = true;
  st.style.color = '#9c9'; st.textContent = '⏳ Vorschau wird gerendert (kein Bake) …';
  document.getElementById('oil_results').style.display = 'none';
  document.getElementById('oil_progress_wrap').style.display = 'block';
  try {
    const payload = await _oilBuildPayload();
    const r = await fetch('/oilspray/preview', { method:'POST', headers:{'Content-Type':'application/json'},
                                                 body: JSON.stringify(payload) });
    if (r.status === 503) {
      const j = await r.json(); st.style.color = '#e57';
      st.innerHTML = '⚠ ' + escHtml(j.error || 'Blender fehlt').replace(/\n/g,'<br>');
      btn.disabled = false; if (pbtn) pbtn.disabled = false;
      document.getElementById('oil_progress_wrap').style.display = 'none'; return;
    }
    if (!r.ok) { const j = await r.json().catch(()=>({})); st.style.color='#e57';
      st.textContent = '⚠ ' + (j.error || r.status); btn.disabled = false; if (pbtn) pbtn.disabled = false;
      document.getElementById('oil_progress_wrap').style.display = 'none'; return; }
    document.getElementById('oil_abort_btn').style.display = 'inline-block';
    _pollOil();
  } catch (e) { st.style.color='#e57'; st.textContent = 'Fehler: ' + e.message; btn.disabled = false;
    if (pbtn) pbtn.disabled = false; document.getElementById('oil_progress_wrap').style.display = 'none'; }
}

function _renderOilPreview(res) {
  const box = document.getElementById('oil_results');
  const st = document.getElementById('oil_status');
  st.style.color = '#6c6';
  st.textContent = '✓ Vorschau — die 🔴 Linien zeigen die Strahlrichtung (noch kein Fluid berechnet).';
  const cfg = res.config || {};
  const bits = [];
  if (cfg.view_mode) bits.push(cfg.view_mode === 'full' ? 'Gesamt' : 'Ausschnitt');
  if (cfg.closeup) bits.push('Nahaufnahme');
  if (cfg.orientation) bits.push(cfg.orientation === 'vertical' ? 'vertikal' : 'horizontal');
  bits.push((cfg.nozzle_count ?? '–') + ' Düse(n)');
  if (cfg.jet_tilt_deg) bits.push('Neigung ' + cfg.jet_tilt_deg + '°');
  if (cfg.jet_yaw_deg) bits.push('Schwenk ' + cfg.jet_yaw_deg + '°');
  if (cfg.nozzle_offset_deg) bits.push('Düsen-Versatz ' + cfg.nozzle_offset_deg + '°');
  if (cfg.jet_cone_deg) bits.push('Sprühfächer ' + cfg.jet_cone_deg + '°');
  if (cfg.view_down && cfg.view_down !== 'auto') bits.push('unten ' + cfg.view_down.toUpperCase());
  if (cfg.material) bits.push('Materialien');
  if (cfg.light_preset) bits.push('Licht: ' + cfg.light_preset);
  const imgs = Array.isArray(res.images) && res.images.length ? res.images
             : (res.image ? [res.image] : []);
  const turn = imgs.length > 1;
  let h = '<div class="e3-card"><div class="section-title">🔍 Vorschau — Strahlrichtung (ohne Bake)</div>'
        + `<div style="font-size:.82rem;color:#9aa;margin-bottom:8px">${escHtml(bits.join(' · '))}</div>`;
  if (imgs.length) {
    const cursor = turn ? 'grab' : 'default';
    h += `<img id="oil_pv_img" src="data:image/png;base64,${imgs[0]}" `
       + `style="max-width:100%;border-radius:6px;cursor:${cursor};user-select:none;-webkit-user-drag:none">`;
  }
  if (turn)
    h += '<div style="margin-top:6px;display:flex;align-items:center;gap:8px;flex-wrap:wrap">'
       + `<span style="font-size:.74rem;color:#889">🔄 Ziehen zum Drehen</span>`
       + `<input id="oil_pv_slider" type="range" min="0" max="${imgs.length-1}" value="0" style="flex:1;min-width:120px">`
       + `<button type="button" onclick="_oilLockCamera(${imgs.length})" `
       + `style="width:auto;padding:4px 10px;font-size:.74rem">🔒 Diese Ansicht fürs Video übernehmen</button>`
       + '</div><div id="oil_cam_lock_status" style="margin-top:4px;font-size:.74rem;color:#889"></div>';
  h += '<div style="margin-top:8px;font-size:.74rem;color:#889">Die leuchtenden Linien markieren, '
     + 'wohin jeder Ölstrahl zeigt. Das Koordinatensystem (X&nbsp;rot · Y&nbsp;grün · Z&nbsp;blau, '
     + 'Z&nbsp;=&nbsp;Motorachse) zeigt die Lage. Passt die Richtung, unten die volle Simulation starten.</div>';
  if (res.debug_log) h += `<div style="margin-top:4px;font-size:.7rem;color:#667">📄 Debug-Log `
     + `(alle Einstellungen, bei Rückfragen mitschicken): <code>${escHtml(res.debug_log)}</code></div>`;
  h += '</div>';
  box.innerHTML = h; box.style.display = 'block';
  // Eine neue Vorschau invalidiert einen zuvor fixierten Kamera-Winkel (Index↔Winkel-Zuordnung
  // gilt nur für DIESE Drehteller-Bilderserie).
  window._oilCamLockDeg = null;
  if (turn) _oilInitTurntable(imgs);
}

// Kamera-Fixwinkel: die im Drehteller gewählte Position wird 1:1 im echten Bake-Video
// wiederverwendet (dieselbe Rotationsformel wie der Drehteller: 360°·index/Anzahl), statt die
// Standard-3/4-Ansicht neu zu berechnen.
function _oilLockCamera(n) {
  const sld = document.getElementById('oil_pv_slider');
  const idx = sld ? +sld.value : 0;
  window._oilCamLockDeg = 360 * idx / n;
  const st = document.getElementById('oil_cam_lock_status');
  if (st) st.innerHTML = `🔒 Kamera für das Video fixiert bei ${window._oilCamLockDeg.toFixed(1)}° — `
    + `<a href="javascript:void(0)" onclick="_oilUnlockCamera()">zurücksetzen</a>`;
}
function _oilUnlockCamera() {
  window._oilCamLockDeg = null;
  const st = document.getElementById('oil_cam_lock_status');
  if (st) st.innerHTML = '';
}

// Drehteller: Ziehen (oder Slider) blättert durch die vorab gerenderten Kamera-Winkel → das
// Standbild lässt sich frei drehen, ohne den teuren Bake. Reines Frontend über die base64-Liste.
function _oilInitTurntable(imgs) {
  const img = document.getElementById('oil_pv_img');
  const sld = document.getElementById('oil_pv_slider');
  if (!img) return;
  const n = imgs.length;
  let idx = 0;
  const show = i => { idx = ((i % n) + n) % n; img.src = 'data:image/png;base64,' + imgs[idx];
                      if (sld) sld.value = idx; };
  if (sld) sld.oninput = () => show(+sld.value);
  let dragging = false, x0 = 0, i0 = 0;
  const perImg = 12;  // Pixel Ziehweg pro Winkelschritt
  const down = e => { dragging = true; x0 = (e.touches ? e.touches[0].clientX : e.clientX); i0 = idx;
                      img.style.cursor = 'grabbing'; e.preventDefault(); };
  const move = e => { if (!dragging) return;
                      const x = (e.touches ? e.touches[0].clientX : e.clientX);
                      show(i0 + Math.round((x - x0) / perImg)); e.preventDefault(); };
  const up = () => { dragging = false; img.style.cursor = 'grab'; };
  img.addEventListener('mousedown', down); window.addEventListener('mousemove', move);
  window.addEventListener('mouseup', up);
  img.addEventListener('touchstart', down, {passive:false});
  img.addEventListener('touchmove', move, {passive:false});
  img.addEventListener('touchend', up);
}

async function abortOilspray() {
  const b = document.getElementById('oil_abort_btn'); if (b) b.disabled = true;
  const st = document.getElementById('oil_status');
  if (st) { st.style.color = '#fb0'; st.textContent = '⛔ Breche ab… (Blender stoppen)'; }
  try { await fetch('/oilspray/abort', { method: 'POST' }); } catch (e) {}
  if (b) b.disabled = false;
}

async function _pollOil() {
  const st = document.getElementById('oil_status');
  const done = () => { document.getElementById('oil_btn').disabled = false;
    const pb = document.getElementById('oil_preview_btn'); if (pb) pb.disabled = false;
    document.getElementById('oil_abort_btn').style.display = 'none';
    document.getElementById('oil_progress_wrap').style.display = 'none'; };
  try {
    const s = await fetch('/oilspray/status').then(x => x.json());
    if (Array.isArray(s.log) && s.log.length) st.textContent = s.log.slice(-6).join('\n');
    const pw = document.getElementById('oil_progress'); if (pw) pw.style.width = (s.progress || 0) + '%';
    if (s.status === 'done' || s.status === 'aborted') {
      done();
      if (s.result && s.result.preview) _renderOilPreview(s.result);
      else if (s.result) _renderOil(s.result);
      if (s.status === 'aborted') { st.style.color = '#fb0';
        st.textContent = '⛔ Abgebrochen. Neustart jederzeit möglich.'; }
      return;
    }
    if (s.status === 'error') { st.style.color='#e57'; st.textContent = '⚠ ' + (s.error || 'Fehlgeschlagen'); done(); return; }
  } catch (e) {}
  setTimeout(_pollOil, 1500);
}

function _renderOil(res) {
  const box = document.getElementById('oil_results');
  const st = document.getElementById('oil_status');
  if (!res) { return; }
  const m = res.metrics || {}, cfg = res.config || {}, imgs = res.images || {};
  st.style.color = '#6c6';
  st.textContent = '✓ Spritzöl-Simulation fertig — im Projekt gespeichert (📼 jederzeit wieder ladbar).';
  const pid = res.project_id || (window._activeProject && window._activeProject.id) || 'current';
  const f1 = v => (v == null ? '–' : (+v).toFixed(1));
  const vsrc = res.video_src
    ? (res.video_src + (res.video_src.indexOf('?') < 0 ? '?' : '&') + 't=' + Date.now())
    : `/project/${encodeURIComponent(pid)}/video/oil?t=${Date.now()}`;
  let h = '<div class="e3-card"><div class="section-title">💧 Ergebnis — Spritzöl-Kühlung (qualitativ)</div>';
  if (m.jet_underres) {
    const fixes = [];
    if (cfg.housing_collide) fixes.push('🧱 Kollisionswand ausschalten (fokussiert die Domain)');
    if (!cfg.closeup) fixes.push('Nahaufnahme aktivieren');
    fixes.push('Auflösung erhöhen');
    h += `<div style="margin:2px 0 10px;padding:8px 10px;border-radius:6px;background:#3a2a12;`
       + `border:1px solid #a56b1e;color:#f0c070;font-size:.8rem">`
       + `⚠ <b>Ölstrahl unter-aufgelöst.</b> Die ${f1(cfg.nozzle_d_mm)}-mm-Bohrung ist bei `
       + `Auflösung ${cfg.resolution} nur ~${f1(m.jet_cells)} Zellen breit `
       + `(Voxel ≈ ${f1(m.voxel_mm)} mm) — der Strahl bildet kaum ein sichtbares Öl-Mesh. `
       + `Abhilfe: ${fixes.map(escHtml).join(' · ')}.</div>`;
  }
  if (res.video)
    h += `<div id="oil_vwrap" style="overflow:hidden;border-radius:6px;position:relative;touch-action:none"`
       + ` title="Mausrad: Zoom · Ziehen: Verschieben (wenn gezoomt) · Doppelklick: Zurücksetzen">`
       + `<video id="oil_video" controls loop autoplay muted playsinline`
       + ` style="max-width:100%;display:block;transform-origin:center center"`
       + ` src="${vsrc}"></video></div>`
       + `<div style="display:flex;gap:6px;align-items:center;margin-top:6px;font-size:.78rem;color:#9aa">`
       + `<button onclick="_oilZoom(1/1.3)" style="width:auto;padding:2px 10px">🔍−</button>`
       + `<span id="oil_zoom_lbl" style="min-width:44px;text-align:center">100%</span>`
       + `<button onclick="_oilZoom(1.3)" style="width:auto;padding:2px 10px">🔍+</button>`
       + `<button onclick="_oilZoomReset()" style="width:auto;padding:2px 10px">⟲ Reset</button>`
       + `<span>Mausrad zoomt · gezoomtes Bild mit der Maus verschieben</span></div>`;
  h += '<div style="display:flex;gap:20px;flex-wrap:wrap;margin-top:10px;font-size:.84rem">'
     + `<div><b>Benetzung (Spitze)</b><br>${f1(m.wetted_pct_peak)} %</div>`
     + `<div><b>Benetzung (Mittel)</b><br>${f1(m.wetted_pct_mean)} %</div>`
     + `<div><b>Tropfen/Fragmente (max)</b><br>${m.droplets_peak ?? '–'}</div>`
     + `<div><b>Spritzring</b><br>${cfg.pressure_bar ?? '–'} bar · ${cfg.nozzle_count ?? '–'} Düsen`
     + `${cfg.jet_speed_mps ? ' · '+cfg.jet_speed_mps+' m/s' : ''}</div>`
     + `<div><b>Auflösung</b><br>${cfg.resolution} · ${cfg.frames} Frames</div>`
     + (cfg.slowmo > 1 ? `<div><b>Zeitlupe</b><br>${cfg.slowmo}×</div>` : '')
     + (cfg.winding_full ? `<div><b>Wickelkopf</b><br>komplett (alle Nuten)</div>` : '')
     + (cfg.hidden_pins && cfg.hidden_pins.length ? `<div><b>Ausgeblendete Hairpins</b><br>${cfg.hidden_pins.length}</div>` : '')
     + (cfg.camera_angle_deg != null ? `<div><b>Kamera</b><br>fixiert bei ${(+cfg.camera_angle_deg).toFixed(1)}°</div>` : '')
     + (cfg.light_preset ? `<div><b>Beleuchtung</b><br>${escHtml(cfg.light_preset)}</div>` : '')
     + '</div>'
     + `<div style="margin-top:8px;font-size:.72rem;color:#889">${escHtml(res.note || '')}</div>`
     + (res.debug_log ? `<div style="margin-top:4px;font-size:.7rem;color:#667">📄 Debug-Log `
        + `(alle Einstellungen, bei Rückfragen mitschicken): <code>${escHtml(res.debug_log)}</code></div>` : '')
     + '</div>';
  const charts = [['oil_wetting','Benetzung über die Zeit (Proxy)'],
                  ['oil_droplets','Tröpfchenbildung / Fragmentierung über die Zeit'],
                  ['oil_coverage','Benetzungs-Heatmap (Abdeckung je Fläche)']];
  for (const [k, lbl] of charts) if (imgs[k])
    h += `<div class="e3-card"><div class="section-title">${lbl}</div>`
       + `<img src="data:image/png;base64,${imgs[k]}" style="max-width:100%;border-radius:6px"></div>`;
  box.innerHTML = h; box.style.display = 'block';
  _oilInitZoom();
  refreshOilVariants();
}

// ── Gespeicherte Öl-Varianten (jeder Lauf wird automatisch als eigene Variante abgelegt) ──
async function refreshOilVariants() {
  const el = document.getElementById('oil_variants_list');
  if (!el) return;
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    const list = await fetch(`/project/${encodeURIComponent(pid)}/oilspray/saved`).then(x => x.json());
    if (!Array.isArray(list) || !list.length) {
      el.innerHTML = '<span style="color:#889">— noch keine gespeicherten Läufe —</span>'; return; }
    let h = '<div style="display:flex;flex-direction:column;gap:6px">';
    for (const v of list) {
      const bits = [];
      if (v.view_mode) bits.push(v.view_mode === 'full' ? 'Gesamt' : 'Ausschnitt');
      if (v.closeup) bits.push('Nahaufnahme');
      if (v.orientation) bits.push(v.orientation === 'vertical' ? 'vertikal' : 'horizontal');
      if (v.slowmo > 1) bits.push(v.slowmo + '×');
      if (v.resolution) bits.push('RES ' + v.resolution);
      if (v.frames) bits.push(v.frames + ' Fr.');
      if (v.wetted_pct_mean != null) bits.push('Benetz. ⌀ ' + (+v.wetted_pct_mean).toFixed(1) + '%');
      h += `<div style="display:flex;gap:8px;align-items:center;background:#1c2024;border:1px solid #333;`
         + `border-radius:5px;padding:6px 9px">`
         + `<span style="flex:1"><b>${escHtml(v.timestamp || v.id)}</b>`
         + `<span style="color:#889;font-size:.9em"> — ${escHtml(bits.join(' · '))}</span>`
         + `${v.video ? '' : ' <span style="color:#c85">(kein Video)</span>'}</span>`
         + `<button onclick="loadOilVariant('${encodeURIComponent(v.id)}')" style="width:auto;padding:3px 10px">📼 Ansehen</button>`
         + `<button onclick="deleteOilVariant('${encodeURIComponent(v.id)}')" style="width:auto;padding:3px 9px;background:#7a3030">🗑</button>`
         + `</div>`;
    }
    el.innerHTML = h + '</div>';
  } catch (e) {
    el.innerHTML = '<span style="color:#c66">⚠ Varianten-Liste nicht ladbar.</span>';
  }
}

async function loadOilVariant(rid) {
  const st = document.getElementById('oil_status');
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    const res = await fetch(`/project/${encodeURIComponent(pid)}/oilspray/saved/${rid}`).then(x => x.json());
    if (res.error) { if (st) { st.style.color = '#e57'; st.textContent = '⚠ ' + res.error; } return; }
    _renderOil(res);
    if (st) { st.style.color = '#6c6'; st.textContent = `📼 Variante ${res.timestamp || rid} geladen.`; }
  } catch (e) { if (st) { st.style.color = '#e57'; st.textContent = '⚠ ' + e; } }
}

async function deleteOilVariant(rid) {
  if (!confirm('Diese gespeicherte Variante wirklich löschen?')) return;
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    await fetch(`/project/${encodeURIComponent(pid)}/oilspray/saved/${rid}/delete`, { method: 'POST' });
  } catch (e) {}
  refreshOilVariants();
}

// Zoom/Pan für das Spritzöl-Video (CSS-Transform): Mausrad zoomt (auch übers Video),
// Ziehen verschiebt (nur wenn gezoomt, damit die Video-Controls bei 100 % normal bedienbar
// bleiben), Doppelklick/⟲ setzt zurück. Bis 8× — reine Frontend-Lupe, kein Re-Render.
function _oilInitZoom() {
  const wrap = document.getElementById('oil_vwrap');
  const vid = document.getElementById('oil_video');
  if (!wrap || !vid) return;
  let s = 1, tx = 0, ty = 0, drag = null;
  const apply = () => {
    vid.style.transform = `translate(${tx}px,${ty}px) scale(${s})`;
    const l = document.getElementById('oil_zoom_lbl');
    if (l) l.textContent = Math.round(s * 100) + '%';
    wrap.style.cursor = s > 1 ? 'grab' : '';
  };
  window._oilZoom = f => { s = Math.min(8, Math.max(1, s * f)); if (s === 1) { tx = ty = 0; } apply(); };
  window._oilZoomReset = () => { s = 1; tx = ty = 0; apply(); };
  wrap.addEventListener('wheel', e => { e.preventDefault(); _oilZoom(e.deltaY < 0 ? 1.2 : 1 / 1.2); },
                        { passive: false });
  wrap.addEventListener('pointerdown', e => {
    if (s === 1) return;                      // bei 100 % Video-Controls nicht blockieren
    drag = { x: e.clientX - tx, y: e.clientY - ty };
    wrap.setPointerCapture(e.pointerId); wrap.style.cursor = 'grabbing'; e.preventDefault();
  });
  wrap.addEventListener('pointermove', e => {
    if (drag) { tx = e.clientX - drag.x; ty = e.clientY - drag.y; apply(); }
  });
  const end = () => { drag = null; wrap.style.cursor = s > 1 ? 'grab' : ''; };
  wrap.addEventListener('pointerup', end);
  wrap.addEventListener('pointercancel', end);
  wrap.addEventListener('dblclick', () => _oilZoomReset());
  apply();
}

// Gespeicherten Spritzöl-Lauf des aktiven Projekts laden (Speicherfunktion des 💧-Tabs).
// explicit=true → vom Knopf (mit Fehlermeldung); false → stilles Auto-Laden beim Tab-Öffnen.
async function loadOilSaved(explicit) {
  const st = document.getElementById('oil_status');
  const pid = (window._activeProject && window._activeProject.id) || 'current';
  try {
    const r = await fetch(`/project/${encodeURIComponent(pid)}/oilspray`);
    if (!r.ok) {
      if (explicit) { st.style.color = '#fb0';
        st.textContent = (await r.json().catch(() => ({}))).error
          || '⚠ Kein gespeicherter Spritzöl-Lauf im aktiven Projekt.'; }
      return false;
    }
    const res = await r.json();
    _renderOil(res);
    st.style.color = '#6c6';
    st.textContent = `📼 Gespeicherter Spritzöl-Lauf geladen (Projekt ${res.project_id || pid}).`;
    return true;
  } catch (e) {
    if (explicit) { st.style.color = '#e57'; st.textContent = '⚠ ' + e; }
    return false;
  }
}

// ── 🧪 Spray-Test-Tab (iteratives Spray-Tuning auf dem Prüfstand) ─────────────
// Runden-Store liegt SERVER-seitig unter ~/cae_projekte/_spraytest (projektunabhängig).
// window._stRound = die aktuell angezeigte Runde (round.json-Inhalt).
window._stRound = null;

function _stFmtParams(p) {
  return `${(+p.pressure_bar).toFixed(1)} bar · ${Math.round(+p.jet_cone_deg)}° · ` +
         `σ ${(+p.surface_tension).toFixed(4)} · ν ${(+p.viscosity).toFixed(4)} · ` +
         `Ø ${(+p.nozzle_d_mm).toFixed(1)} mm`;
}

async function stRefresh() {
  try {
    const rounds = await (await fetch('/spraytest/rounds')).json();
    const sel = document.getElementById('st_round_sel');
    if (sel) {
      const cur = window._stRound ? window._stRound.rid : '';
      sel.innerHTML = rounds.length
        ? rounds.map(r => `<option value="${r.rid}" ${r.rid === cur ? 'selected' : ''}>` +
            `Runde ${r.round_no} — ${r.ts} (${r.n_variants} Varianten` +
            `${r.aborted ? ', abgebrochen' : ''})</option>`).join('')
        : '<option value="">— noch keine Runde —</option>';
    }
    // Beim Tab-Öffnen die neueste Runde still anzeigen (wenn nichts läuft/angezeigt wird)
    if (!window._stRound && rounds.length && !document.getElementById('st_btn_start').disabled)
      stLoadRound(rounds[0].rid);
  } catch (e) {}
  stRefreshFavs();
}

async function stLoadRound(rid) {
  if (!rid) return;
  try {
    const r = await fetch(`/spraytest/round/${encodeURIComponent(rid)}`);
    if (!r.ok) return;
    stRenderRound(await r.json());
  } catch (e) {}
}

function _stVideoUrl(round, v, beauty) {
  return `/spraytest/video/${encodeURIComponent(round.rid)}/${encodeURIComponent(v.id)}` +
         `?${beauty ? 'beauty=1&' : ''}t=${Date.now()}`;
}

// Mini-Sparkline: Tropfenzahl (Mesh-Inseln + Sekundärpartikel) über die Frames.
function _stSparkline(canvas, series, big) {
  if (!canvas || !Array.isArray(series) || series.length < 2) return false;
  const vals = series.map(s => (s.n_islands || 0) + (s.n_snd || 0));
  const max = Math.max(...vals, 1);
  const ctx = canvas.getContext('2d');
  const W = canvas.width, H = canvas.height, pad = 2;
  ctx.clearRect(0, 0, W, H);
  ctx.beginPath();
  vals.forEach((val, i) => {
    const x = pad + (W - 2 * pad) * i / (vals.length - 1);
    const y = H - pad - (H - 2 * pad) * val / max;
    i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
  });
  ctx.strokeStyle = '#3a8adf'; ctx.lineWidth = big ? 2 : 1.2; ctx.stroke();
  ctx.lineTo(W - pad, H - pad); ctx.lineTo(pad, H - pad); ctx.closePath();
  ctx.fillStyle = 'rgba(58,138,223,.18)'; ctx.fill();
  return true;
}

function stRenderRound(round) {
  window._stRound = round;
  const card = document.getElementById('st_grid_card');
  const grid = document.getElementById('st_grid');
  const title = document.getElementById('st_grid_title');
  if (!card || !grid) return;
  card.style.display = '';
  title.textContent = `Runde ${round.round_no} — ${round.ts}` +
    ` (Auflösung ${round.resolution || ({schnell:48,normal:64,fein:96}[round.quality] || '?')}` +
    `${round.aborted ? ', abgebrochen — Teilrunde' : ''})` +
    ' · ⭐ die Besten markieren, dann „Nächste Runde" · Klick aufs Video = Großansicht';
  const marked = new Set(round.marked || []);
  grid.innerHTML = (round.variants || []).map(v => {
    const isM = marked.has(v.id);
    const vsrc = _stVideoUrl(round, v, !!v.beauty);
    const badge = v.source === 'parent'
      ? `<span style="background:#2e5a7d;color:#cde;padding:1px 6px;border-radius:3px;font-size:.68rem">Elter${v.src_round ? ' (' + v.src_round.split('_')[0] + ')' : ''}</span>`
      : '';
    const bBadge = v.beauty
      ? `<span title="Schönheits-Render (Auflösung ${v.beauty_res || '?'})"
              style="background:#6d5a1a;color:#fda;padding:1px 6px;border-radius:3px;font-size:.68rem">✨${v.beauty_res || ''}</span>`
      : '';
    const body = v.ok
      ? `<video muted loop autoplay playsinline src="${vsrc}" onclick="stOpenBig('${v.id}')"
           title="Klick = Großansicht"
           style="width:100%;border-radius:4px;background:#000;display:block;cursor:zoom-in"></video>`
      : `<div style="padding:22px 8px;text-align:center;color:#e57;font-size:.78rem;background:#1a1214;border-radius:4px">
           ⚠ fehlgeschlagen<br><span style="color:#977">${(v.error || '').slice(0, 90)}</span></div>`;
    return `<div style="border:2px solid ${isM ? '#e5b93a' : '#333'};border-radius:6px;padding:6px;background:#161a1e">
      ${body}
      <div style="display:flex;align-items:center;gap:6px;margin-top:5px">
        <button onclick="stToggleMark('${v.id}')" title="als Elter für die nächste Runde markieren"
                style="width:auto;padding:3px 9px;font-size:.85rem;background:${isM ? '#8a6d1a' : '#333'}">⭐</button>
        <span style="font-size:.72rem;color:#9ab;flex:1">${_stFmtParams(v.params)}</span>
        ${badge}${bBadge}
      </div>
      <canvas id="st_spark_${v.id}" width="240" height="36"
              style="width:100%;height:36px;margin-top:4px;display:none"></canvas>
      <div style="display:flex;gap:6px;margin-top:5px;align-items:center;flex-wrap:wrap">
        <button onclick='stAdopt(${JSON.stringify(v.params)})' title="Parameter in den 💧-Spritzöl-Tab übernehmen"
                style="width:auto;padding:3px 9px;font-size:.72rem;background:#2e7d4a">✔ Übernehmen</button>
        ${v.ok ? `<button onclick="stBeauty('${v.id}')" title="Diese Variante hochauflösend neu backen"
                style="width:auto;padding:3px 9px;font-size:.72rem;background:#6d5a1a">✨ Schön rendern</button>` : ''}
        <button onclick="stSaveFavorite('${v.id}')" title="Diesen Strahl benannt als Favorit speichern (für die echte 💧-Berechnung)"
                style="width:auto;padding:3px 9px;font-size:.72rem;background:#2e5a7d">💾 Favorit</button>
        ${v.droplets_peak != null ? `<span style="font-size:.7rem;color:#789">≈${v.droplets_peak} Tropfen max.</span>` : ''}
      </div>
    </div>`;
  }).join('') || '<div style="color:#9aa;font-size:.8rem">— keine Varianten —</div>';
  // Sparklines nach dem DOM-Aufbau zeichnen (Canvas braucht existierende Elemente)
  (round.variants || []).forEach(v => {
    const cv = document.getElementById(`st_spark_${v.id}`);
    if (cv && _stSparkline(cv, v.series)) cv.style.display = '';
  });
}

// ── 🔍 Großansicht ────────────────────────────────────────────────────────────
window._stBigVid = null;

function stOpenBig(vid) {
  const round = window._stRound;
  if (!round) return;
  const v = (round.variants || []).find(x => x.id === vid);
  if (!v || !v.ok) return;
  window._stBigVid = vid;
  document.getElementById('st_big_title').textContent =
    `Runde ${round.round_no} · Variante ${vid}` + (v.source === 'parent' ? ' (Elter)' : '');
  document.getElementById('st_big_params').textContent = _stFmtParams(v.params) +
    (v.droplets_peak != null ? ` · ≈${v.droplets_peak} Tropfen max.` : '');
  const spark = document.getElementById('st_big_spark');
  spark.style.display = _stSparkline(spark, v.series, true) ? '' : 'none';
  document.getElementById('st_big_toggle').style.display = v.beauty ? '' : 'none';
  stBigSrc(!!v.beauty);
  _stBigSyncMark();
  document.getElementById('st-big-modal').style.display = 'flex';
}

function stBigSrc(beauty) {
  const round = window._stRound;
  const v = round && (round.variants || []).find(x => x.id === window._stBigVid);
  if (!v) return;
  document.getElementById('st_big_video').src = _stVideoUrl(round, v, beauty && v.beauty);
}

function stCloseBig() {
  document.getElementById('st-big-modal').style.display = 'none';
  const vd = document.getElementById('st_big_video');
  vd.pause(); vd.removeAttribute('src'); vd.load();
  window._stBigVid = null;
}

function _stBigSyncMark() {
  const round = window._stRound;
  const btn = document.getElementById('st_big_mark');
  if (!round || !btn || !window._stBigVid) return;
  const isM = (round.marked || []).includes(window._stBigVid);
  btn.style.background = isM ? '#8a6d1a' : '#333';
  btn.textContent = isM ? '⭐ Markiert' : '⭐ Markieren';
}

async function stBigMark() {
  if (window._stBigVid) { await stToggleMark(window._stBigVid); _stBigSyncMark(); }
}

function stBigAdopt() {
  const round = window._stRound;
  const v = round && (round.variants || []).find(x => x.id === window._stBigVid);
  if (v) stAdopt(v.params);
}

// ── ✨ Schönheits-Render ──────────────────────────────────────────────────────
async function stBeauty(vid) {
  const round = window._stRound;
  const st = document.getElementById('st_status');
  if (!round || !vid) return;
  stCloseBig();
  // Beauty rendert IMMER hochauflösend: mindestens 256, oder das Feld, wenn höher.
  const resIn = parseInt(document.getElementById('st_res').value) || 64;
  const spec = { rid: round.rid, vid: vid,
                 resolution: Math.min(512, Math.max(256, resIn)),
                 frames: parseInt(document.getElementById('st_frames').value) || 60,
                 slowmo: parseFloat(document.getElementById('st_slowmo').value) || 3 };
  try {
    const r = await fetch('/spraytest/beauty', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(spec) });
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      st.style.color = r.status === 503 ? '#e57' : '#fb0';
      st.textContent = '⚠ ' + (j.error || ('HTTP ' + r.status)); return;
    }
    ['st_btn_start', 'st_btn_next'].forEach(id => document.getElementById(id).disabled = true);
    document.getElementById('st_btn_abort').disabled = false;
    document.getElementById('st_progress_wrap').style.display = '';
    st.style.color = '#9aa';
    st.textContent = `✨ Schönheits-Render ${vid} läuft (Auflösung ${spec.resolution}) …`;
    _pollSt();
  } catch (e) { st.style.color = '#e57'; st.textContent = '⚠ ' + e; }
}

async function stToggleMark(vid) {
  const round = window._stRound;
  if (!round) return;
  const marked = new Set(round.marked || []);
  if (marked.has(vid)) marked.delete(vid); else marked.add(vid);
  round.marked = [...marked];
  stRenderRound(round);                      // sofortiges visuelles Feedback
  try {
    await fetch(`/spraytest/round/${encodeURIComponent(round.rid)}/marked`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ marked: round.marked }) });
  } catch (e) {}
}

function stAdopt(params) {
  const map = { pressure_bar: 'oil_pressure', jet_cone_deg: 'oil_jet_cone',
                surface_tension: 'oil_surft', viscosity: 'oil_visc',
                nozzle_d_mm: 'oil_nozzle_d' };
  for (const [k, id] of Object.entries(map)) {
    const el = document.getElementById(id);
    if (el && params[k] != null) {
      // Auf die Feldgrenzen klemmen — Altrunden/-Favoriten können noch Werte aus den
      // früheren, weiteren Bereichen tragen (z. B. 8 bar / Ø 3 mm).
      let v = parseFloat(params[k]);
      if (el.min !== '') v = Math.max(parseFloat(el.min), v);
      if (el.max !== '') v = Math.min(parseFloat(el.max), v);
      el.value = v;
    }
  }
  const st = document.getElementById('st_status');
  if (st) { st.style.color = '#6c6';
    st.textContent = `✔ Übernommen in den 💧-Spritzöl-Tab: ${_stFmtParams(params)}`; }
}

// ── 💾 Spray-Favoriten (benannte Sprays für die echte 💧-Berechnung) ──────────
window._stFavs = [];

async function stRefreshFavs() {
  try {
    window._stFavs = await (await fetch('/spraytest/favorites')).json();
  } catch (e) { window._stFavs = []; }
  const box = document.getElementById('st_fav_list');
  if (box) {
    box.innerHTML = (window._stFavs || []).map(f => `
      <div style="display:flex;align-items:center;gap:8px;border:1px solid #333;border-radius:5px;padding:6px 8px;background:#161a1e;flex-wrap:wrap">
        <b style="font-size:.8rem;color:#cde">${(f.name || '').replace(/</g, '&lt;')}</b>
        <span style="font-size:.72rem;color:#9ab;flex:1">${_stFmtParams(f.params)}
          <span style="color:#678">· Prüfstand: ${f.sim ? f.sim.resolution : '?'}er, ${f.ts || ''}</span></span>
        <button onclick="stApplyFavorite('${f.id}')" title="In die Felder der echten Spritzöl-Berechnung schreiben"
                style="width:auto;padding:3px 10px;font-size:.72rem;background:#2e7d4a">✔ in 💧 übernehmen</button>
        <button onclick="stDeleteFavorite('${f.id}')" style="width:auto;padding:3px 8px;font-size:.72rem;background:#444">🗑</button>
      </div>`).join('') ||
      '<span style="font-size:.78rem;color:#789">— noch keine Favoriten —</span>';
  }
  // Dropdown im 💧-Tab mitpflegen
  const sel = document.getElementById('oil_fav_sel');
  if (sel) {
    sel.innerHTML = '<option value="">— Spray-Favorit wählen —</option>' +
      (window._stFavs || []).map(f =>
        `<option value="${f.id}">${(f.name || '').replace(/</g, '&lt;')} (${_stFmtParams(f.params)})</option>`).join('');
  }
}

async function stSaveFavorite(vid) {
  const round = window._stRound;
  const v = round && (round.variants || []).find(x => x.id === vid);
  if (!v) return;
  const name = prompt('Name für diesen Spray-Favoriten:',
                      `Spray ${(+v.params.pressure_bar).toFixed(1)} bar / Ø${(+v.params.nozzle_d_mm).toFixed(1)}`);
  if (name === null) return;
  try {
    await fetch('/spraytest/favorites', { method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name, params: v.params,
        sim: { resolution: round.resolution, frames: round.frames, slowmo: round.slowmo },
        src: { rid: round.rid, vid: vid } }) });
    const st = document.getElementById('st_status');
    if (st) { st.style.color = '#6c6'; st.textContent = `💾 Favorit „${name}" gespeichert.`; }
    stRefreshFavs();
  } catch (e) {}
}

function stApplyFavorite(fid) {
  const f = (window._stFavs || []).find(x => x.id === fid);
  if (!f) return;
  stAdopt(f.params);
  switchTab('oil');                    // direkt hinspringen — dort landet der Strahl
}

async function stDeleteFavorite(fid) {
  const f = (window._stFavs || []).find(x => x.id === fid);
  if (f && !confirm(`Favorit „${f.name}" löschen?`)) return;
  try {
    await fetch(`/spraytest/favorites/${encodeURIComponent(fid)}/delete`, { method: 'POST' });
  } catch (e) {}
  stRefreshFavs();
}

function oilApplyFavorite() {
  const sel = document.getElementById('oil_fav_sel');
  if (sel && sel.value) stApplyFavorite(sel.value);
}

// Gemeinsame Sim-Einstellungen (Auflösung/Frames/Zeitlupe) aus der Kopfkarte lesen.
function _stSimSettings() {
  return {
    resolution: Math.min(512, Math.max(32, parseInt(document.getElementById('st_res').value) || 64)),
    frames: Math.max(24, Math.min(120, parseInt(document.getElementById('st_frames').value) || 44)),
    slowmo: Math.max(1, Math.min(50, parseFloat(document.getElementById('st_slowmo').value) || 3)),
    show_rods: document.getElementById('st_rods').checked,
  };
}

// Runde/Einzel-Strahl an den Server schicken + Poll-Flow starten (geteilt).
async function _stPostRound(spec, label) {
  const st = document.getElementById('st_status');
  try {
    const r = await fetch('/spraytest', { method: 'POST',
      headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(spec) });
    if (r.status === 503) {
      const j = await r.json().catch(() => ({}));
      st.style.color = '#e57'; st.textContent = '⚠ ' + (j.error || 'Blender fehlt'); return;
    }
    if (!r.ok) {
      const j = await r.json().catch(() => ({}));
      st.style.color = '#fb0'; st.textContent = '⚠ ' + (j.error || ('HTTP ' + r.status)); return;
    }
    ['st_btn_start', 'st_btn_next', 'st_btn_single'].forEach(id => {
      const el = document.getElementById(id); if (el) el.disabled = true; });
    document.getElementById('st_btn_abort').disabled = false;
    document.getElementById('st_progress_wrap').style.display = '';
    st.style.color = '#9aa';
    st.textContent = label;
    _pollSt();
  } catch (e) { st.style.color = '#e57'; st.textContent = '⚠ ' + e; }
}

async function stStartRound(first) {
  const st = document.getElementById('st_status');
  const spec = Object.assign({
    n: Math.max(1, Math.min(12, parseInt(document.getElementById('st_n').value) || 10)),
    round_no: 1, parents: []
  }, _stSimSettings());
  if (!first) {
    const round = window._stRound;
    const marked = new Set((round && round.marked) || []);
    if (!round || !marked.size) {
      st.style.color = '#fb0';
      st.textContent = '⚠ Erst mindestens eine Kachel mit ⭐ markieren — die nächste Runde sampelt UM die Markierten.';
      return;
    }
    spec.round_no = (round.round_no || 1) + 1;
    spec.parents = (round.variants || []).filter(v => marked.has(v.id)).map(v => ({
      params: v.params, src_round: round.rid, src_vid: v.id }));
  }
  _stPostRound(spec, `🧪 Runde ${spec.round_no} läuft (${spec.n} Varianten, sequenziell) …`);
}

// 🎯 EINEN Strahl mit exakt den eingestellten Parametern backen (Ein-Kachel-Runde).
async function stStartSingle() {
  const params = {
    pressure_bar:    parseFloat(document.getElementById('st_e_p').value) || 3,
    jet_cone_deg:    parseFloat(document.getElementById('st_e_cone').value) || 0,
    surface_tension: parseFloat(document.getElementById('st_e_surft').value) || 0.01,
    viscosity:       parseFloat(document.getElementById('st_e_visc').value) || 0.004,
    nozzle_d_mm:     parseFloat(document.getElementById('st_e_noz').value) || 1,
  };
  const spec = Object.assign({ n: 1, round_no: 1, parents: [], exact_params: params },
                             _stSimSettings());
  _stPostRound(spec, `🎯 Einzel-Strahl läuft (Auflösung ${spec.resolution}) …`);
}

// Die aktuellen Spray-Werte des 💧-Tabs in die Einzel-Strahl-Felder holen.
function stSingleFromOil() {
  const map = { st_e_p: 'oil_pressure', st_e_cone: 'oil_jet_cone', st_e_surft: 'oil_surft',
                st_e_visc: 'oil_visc', st_e_noz: 'oil_nozzle_d' };
  for (const [dst, src] of Object.entries(map)) {
    const s = document.getElementById(src), d = document.getElementById(dst);
    if (s && d && s.value !== '') d.value = s.value;
  }
}

async function _pollSt() {
  const st = document.getElementById('st_status');
  try {
    const s = await (await fetch('/spraytest/status')).json();
    st.style.color = '#9aa';
    st.textContent = (s.log || []).slice(-6).join('\n');
    document.getElementById('st_progress').style.width = (s.progress || 0) + '%';
    if (s.status === 'running') { setTimeout(_pollSt, 1500); return; }
    ['st_btn_start', 'st_btn_next', 'st_btn_single'].forEach(id => {
      const el = document.getElementById(id); if (el) el.disabled = false; });
    document.getElementById('st_btn_abort').disabled = true;
    document.getElementById('st_progress_wrap').style.display = 'none';
    if (s.status === 'error') { st.style.color = '#e57'; st.textContent = '⚠ ' + (s.error || 'Fehler'); }
    if (s.result) {
      if (s.result.variants) { stRenderRound(s.result); stRefresh(); }  // fertige Runde
      else if (s.result.rid) stLoadRound(s.result.rid);                 // ✨ Beauty → Runde neu laden
    }
  } catch (e) { setTimeout(_pollSt, 3000); }
}

async function stAbort() {
  try { await fetch('/spraytest/abort', { method: 'POST' }); } catch (e) {}
}

async function stDeleteRound() {
  const round = window._stRound;
  if (!round) return;
  if (!confirm(`Runde ${round.round_no} (${round.rid}) wirklich löschen?`)) return;
  try {
    await fetch(`/spraytest/round/${encodeURIComponent(round.rid)}/delete`, { method: 'POST' });
  } catch (e) {}
  window._stRound = null;
  document.getElementById('st_grid_card').style.display = 'none';
  stRefresh();
}
