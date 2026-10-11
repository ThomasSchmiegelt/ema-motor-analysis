/* schnitt.js — der Schnitt DURCH DIE ACHSE, mehrschnittig gerechnet.
 *
 * WARUM DAS NICHT EINFACH „NOCH EIN 2-D-LAUF" IST
 * -----------------------------------------------
 * Die r-z-Ebene ist die eine Ebene dieser Maschine, in der ein 2-D-Loeser
 * NICHT rechnen kann, und der Grund ist nicht Bequemlichkeit: zweidimensional
 * heisst invariant in der dritten Richtung, die dritte Richtung ist hier theta,
 * und in theta liegt der POLWECHSEL. Eine in theta invariante Maschine haette
 * gar keine Pole. (Genau das steht seit dem ersten Entwurf ueber `halbschnitt`
 * in `ansicht.js` — dort wird die Ebene gezeichnet, nicht gerechnet.)
 *
 * Rechnen laesst sie sich trotzdem, nur nicht als EIN Problem: man loest die
 * abgewickelte theta-z-Ebene bei mehreren Radien und legt die Loesungen
 * uebereinander (Mehrschnitt-/Quasi-3-D-Verfahren, das Standardverfahren der
 * Axialflussrechnung). Was dabei fallengelassen wird, ist `d/dr` — und das ist
 * eine benannte Naeherung, keine Kleinigkeit: siehe `radialeKopplung` unten,
 * die sie MISST statt sie zu behaupten.
 *
 * DER WINKEL KOSTET NICHTS, und das ist die eigentliche Pointe
 * ------------------------------------------------------------
 * Eine Scheibe wird bei EINEM Radius geloest und traegt danach ihren ganzen
 * Umfang. Den Schnittwinkel zu aendern heisst, eine andere SPALTE abzulesen —
 * kein neuer Loeserlauf. „Ein Winkel" und „alle 360 Grad" kosten deshalb
 * dasselbe, und die 360-Grad-Ansicht (die Spaltebene als Scheibe) faellt
 * nebenbei mit ab.
 *
 * Was einen neuen Lauf kostet, ist jede Aenderung an der ERREGUNG: Laeuferlage,
 * Stromhoehe, Stromwinkel. Das ist dieselbe Trennung wie im Hauptwerkzeug
 * zwischen `rotate` (Rotorwinkel, neues mu, neue Faktorisierung) und dem
 * blossen Ablesen eines fertigen Feldes.
 *
 * EINE EICHUNG FUER ALLE SCHEIBEN — sonst misst man nichts
 * --------------------------------------------------------
 * `eichung` pinnt die Spaltspitze auf die Arbeitsgerade `Br*hm/(hm+mu_r*kc*g)`,
 * und die haengt NICHT vom Radius ab. Jede Scheibe einzeln geeicht haette damit
 * per Konstruktion dieselbe Spaltspitze — die radiale Aenderung, derentwegen
 * dieser Schnitt ueberhaupt gezeichnet wird, waere exakt wegnormiert. Geeicht
 * wird deshalb EINMAL, an der mittleren Scheibe, und der Faktor gilt fuer alle;
 * dieselbe Entscheidung und derselbe Grund wie `sf_ref` in
 * `ema_analysis.run_em_analysis`.
 */
"use strict";

/* Alle Scheiben loesen. Teuer, aber genau einmal je Erregung. */
function schnittRechnen(p, nSch, nyZiel, iter, melde) {
  const scheiben = [];
  for (let k = 0; k < nSch; k++) {
    const r = p.ri + (p.ro - p.ri) * (k + 0.5) / nSch;
    const pk = { ...p, rs: r };
    const g0 = feldGitter(pk, 8, 8);
    const nx = Math.max(24, Math.round(nyZiel * (g0.breite / g0.hGes)));
    const g = feldGitter(pk, nx, nyZiel);
    const loe = loeseFeld(pk, g, iter);
    const { Bx, By } = feldAus(g, loe.A);
    scheiben.push({ r, g, A: loe.A, Bx, By, nx, pkMag: loe.pkMag,
                    schritte: loe.schritte, relRest: loe.relRest });
    if (melde) melde(k + 1, nSch);
  }
  // EINE Eichung, an der mittleren Scheibe. S. Modulkopf.
  const km = Math.floor(nSch / 2), sm = scheiben[km];
  const eich = eichung({ ...p, rs: sm.r }, sm.g, sm.By, sm.pkMag, iter);
  for (const s of scheiben) s.sf = eich.sf;
  const g0 = scheiben[0].g;
  return { scheiben, eich, nSch, poles: p.poles, ri: p.ri, ro: p.ro,
           ny: g0.ny, yk: g0.yk, yc: g0.yc, dyv: g0.dyv, bnd: g0.bnd,
           hGes: g0.hGes, jGap: eich.jGap,
           schritte: scheiben.reduce((a, s) => a + s.schritte, 0),
           relRest: Math.max(...scheiben.map((s) => s.relRest)) };
}

/* Das (r,z)-Feld bei EINEM Winkel — reines Ablesen, kein Loeserlauf.
 *
 * `Br` fehlt und ist nicht vergessen: eine Scheibe ist `B = curl(A e_r)`, also
 * hat sie per Konstruktion keine Radialkomponente. In der r-z-Ebene sind die
 * beiden Komponenten IN der Ebene aber gerade Br und Bz — Feldlinien liessen
 * sich hier also nur zeichnen, indem man Br erfindet. Gezeichnet wird deshalb
 * Bz (in der Ebene, axial) und Bt (aus der Ebene heraus, umfangs), und das
 * Bild sagt es.
 */
function rzBei(erg, theta) {
  const { scheiben, ny, poles } = erg, nS = scheiben.length;
  const Bz = new Float64Array(nS * ny), Bt = new Float64Array(nS * ny);
  const Bm = new Float64Array(nS * ny);
  // Das Fenster ist 2 Polteilungen = 1 elektrische Periode breit. Sein
  // MECHANISCHER Winkel ist 2*(2pi/2p) und haengt nicht vom Radius ab -- ein
  // Winkel trifft in jeder Scheibe dieselbe physikalische Stelle, auch wenn er
  // dort bei einer anderen Bogenlaenge x liegt. Ohne diesen Umweg ueber den
  // Winkel laege der Schnitt bei grossem r an einer anderen Polstelle als bei
  // kleinem und waere gar kein Schnitt.
  const thW = 2 * (2 * Math.PI / poles);
  let th = theta % thW; if (th < 0) th += thW;
  for (let k = 0; k < nS; k++) {
    const s = scheiben[k], g = s.g;
    let i = Math.floor((th * s.r) / g.dx);
    i = Math.max(1, Math.min(g.nx - 2, i));
    for (let j = 0; j < ny; j++) {
      const o = k * ny + j, q = j * g.nx + i;
      Bz[o] = s.By[q] * s.sf; Bt[o] = s.Bx[q] * s.sf;
      Bm[o] = Math.hypot(Bz[o], Bt[o]);
    }
  }
  return { Bz, Bt, Bm, nS, ny, theta: th };
}

/* B_z in der Zahnmitte ueber dem Radius — die SIGNATUR dieser Bauart.
 *
 * Die Nut ist parallelflankig: `tau_s = 2*pi*r/Q` waechst mit r, die Nutbreite
 * nicht, also wird der Zahn nach aussen breiter und die Zahnflussdichte faellt.
 * Die Zeichnung behauptet das seit dem ersten Entwurf; hier wird es GEMESSEN
 * und gegen die Geometrie gehalten (`B_zahn = B_spalt * tau_s/(tau_s - b)`).
 */
function zahnVerlauf(erg, p) {
  const aus = [];
  const st = erg.bnd.find((b) => b.art === "stator");
  if (!st) return aus;
  // Zeile in der MITTE des Zahnbandes. `seite` sagt, wo der Spalt liegt; bei
  // "beide" (ESDR) traegt die ganze Schicht Zaehne.
  const zMitte = st.seite === "unten" ? st.y1 - p.zahn / 2
               : st.seite === "beide" ? (st.y0 + st.y1) / 2
               : st.y0 + p.zahn / 2;
  let jz = 1, best = Infinity;
  for (let j = 1; j < erg.ny - 1; j++) {
    const d = Math.abs(erg.yc[j] - zMitte);
    if (d < best) { best = d; jz = j; }
  }
  for (const s of erg.scheiben) {
    const g = s.g, tauS = g.tauS;
    // Zahnmitten liegen auf Vielfachen von tau_s (die Nuten auf tau_s/2).
    let bz = 0, bg = 0;
    for (let m = 0; m * tauS < g.breite; m++) {
      const i = Math.round((m * tauS) / g.dx);
      if (i < 1 || i > g.nx - 2) continue;
      bz = Math.max(bz, Math.abs(s.By[jz * g.nx + i] * s.sf));
    }
    for (let i = 1; i < g.nx - 1; i++)
      bg = Math.max(bg, Math.abs(s.By[erg.jGap * g.nx + i] * s.sf));
    aus.push({ r: s.r, tauS, zahn: tauS - p.bnut, b_zahn: bz, b_spalt: bg,
               b_zahn_geo: bg * tauS / Math.max(tauS - p.bnut, 1e-6) });
  }
  return aus;
}

/* Was das Scheibenmodell NICHT kann, als Zahl statt als Vorbehalt.
 *
 * Jede Scheibe ist in sich divergenzfrei (`B = curl(A e_r)` erzwingt das), der
 * Fehler steckt also nicht IN einer Scheibe, sondern zwischen zweien: `d/dr`
 * ist vollstaendig fallengelassen. Gemessen wird deshalb, wie stark sich das
 * Feld von Scheibe zu Scheibe aendert. Solange die radiale Aenderung ueber eine
 * LUFTSPALTLAENGE klein ist, ist das Fallenlassen vertretbar — und genau das
 * ist das Verhaeltnis, das hier herauskommt.
 */
function radialeKopplung(erg, p) {
  const sp = [];
  for (const s of erg.scheiben) {
    let pk = 0;
    for (let i = 1; i < s.g.nx - 1; i++)
      pk = Math.max(pk, Math.abs(s.By[erg.jGap * s.g.nx + i] * s.sf));
    sp.push({ r: s.r, b: pk });
  }
  let maxSchritt = 0, iMax = 0;
  for (let k = 1; k < sp.length; k++) {
    const d = Math.abs(sp[k].b - sp[k - 1].b) / Math.max(sp[k - 1].b, 1e-12);
    if (d > maxSchritt) { maxSchritt = d; iMax = k; }
  }
  const dr = (p.ro - p.ri) / erg.nSch;
  const spanne = Math.abs(sp[sp.length - 1].b - sp[0].b) / Math.max(sp[0].b, 1e-12);
  // Relative Aenderung je Luftspaltlaenge: die Groesse, an der sich entscheidet,
  // ob `d/dr` neben `d/dz` vernachlaessigbar ist.
  const jeSpalt = (spanne / Math.max(p.ro - p.ri, 1e-9)) * p.spalt;
  return { spalt: sp, spanne, maxSchritt, iMax, dr, jeSpalt };
}

/* ---- Zeichnen: der Schnitt durch die Achse ------------------------------ */
/* Achse unten, r nach oben, z nach rechts — dieselbe Lage wie der gezeichnete
 * Halbschnitt daneben, damit die beiden zusammen gelesen werden koennen. */
function zeichneSchnittRZ(cv, p, erg, theta, deckel) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const f = rzBei(erg, theta);
  const pad = 56, achs = 42;
  const s = Math.min((W - 2 * pad) / erg.hGes, (H - pad - achs) / p.ro);
  const z0 = 40 + (W - 40 - s * erg.hGes) / 2, achse = H - achs;
  const X = (z) => z0 + s * z, Y = (r) => achse - s * r;

  // |B| als Flaeche. Rechtecke statt ImageData, weil das Gitter in z
  // UNGLEICHMAESSIG ist (die Zeilen liegen auf den Schichtgrenzen) -- ein
  // gleichmaessig gestrecktes Bild verschoebe genau den Luftspalt.
  const dr = (p.ro - p.ri) / erg.nSch;
  for (let k = 0; k < f.nS; k++) {
    const r0 = p.ri + k * dr;
    for (let j = 0; j < f.ny; j++) {
      ctx.fillStyle = farbe(Math.min(1, f.Bm[k * f.ny + j] / deckel));
      ctx.fillRect(X(erg.yk[j]) - .5, Y(r0 + dr) - .5,
                   s * erg.dyv[j] + 1, s * dr + 1);
    }
  }

  // Schichtgrenzen + Beschriftung
  ctx.strokeStyle = "rgba(190,205,225,.45)"; ctx.lineWidth = 1;
  for (const b of erg.bnd) {
    ctx.beginPath(); ctx.moveTo(X(b.y0), Y(p.ri)); ctx.lineTo(X(b.y0), Y(p.ro));
    ctx.stroke();
  }
  ctx.beginPath(); ctx.moveTo(X(erg.hGes), Y(p.ri)); ctx.lineTo(X(erg.hGes), Y(p.ro)); ctx.stroke();
  ctx.fillStyle = "rgba(220,232,248,.8)"; ctx.font = "10px system-ui"; ctx.textAlign = "center";
  for (const b of erg.bnd)
    ctx.fillText(b.art + (b.seite ? "·" + b.seite : ""), X((b.y0 + b.y1) / 2), Y(p.ro) - 5);

  // Welle und Scheibenblatt -- sonst schwebt der Ringraum im Nichts.
  ctx.fillStyle = "#5d6470";
  ctx.fillRect(X(-6), Y(p.welle), s * (erg.hGes + 12), s * p.welle);
  ctx.fillStyle = "rgba(93,100,112,.45)";
  ctx.fillRect(X(0), Y(p.ri), s * erg.hGes, s * (p.ri - p.welle));

  // Der Fluss steht hier AXIAL -- und das ist die Aussage des Bildes. Pfeile
  // statt Feldlinien, denn Feldlinien IN dieser Ebene brauchten Br, und das
  // Scheibenmodell hat keines (s. `rzBei`).
  const spalte = erg.bnd.filter((b) => b.art === "spalt");
  ctx.strokeStyle = "#8fe3ff"; ctx.lineWidth = 1.4;
  for (const b of spalte)
    for (let k = 1; k < f.nS; k += Math.max(1, Math.round(f.nS / 7))) {
      const r = p.ri + (k + .5) * dr, jj = Math.round(erg.jGap);
      const bz = f.Bz[k * f.ny + jj];
      if (Math.abs(bz) < deckel * .08) continue;
      const xm = X((b.y0 + b.y1) / 2), y = Y(r), L = s * (b.y1 - b.y0) * .42;
      const vz = Math.sign(bz);
      ctx.beginPath(); ctx.moveTo(xm - vz * L, y); ctx.lineTo(xm + vz * L, y);
      ctx.moveTo(xm + vz * L * .3, y - 3); ctx.lineTo(xm + vz * L, y);
      ctx.lineTo(xm + vz * L * .3, y + 3); ctx.stroke();
    }

  // Achse + Masse
  ctx.strokeStyle = "#6b7482"; ctx.setLineDash([9, 5]);
  ctx.beginPath(); ctx.moveTo(X(-10), achse); ctx.lineTo(X(erg.hGes + 10), achse); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui"; ctx.textAlign = "left";
  ctx.fillText("Drehachse", X(-8), achse + 17);
  ctx.fillText(`${erg.nSch} Scheiben · ${erg.schritte} CG-Schritte gesamt · ` +
               `rel. Rest ${erg.relRest.toExponential(1)}`, 10, 16);
  ctx.textAlign = "right";
  ctx.fillText(`θ = ${(f.theta * 180 / Math.PI).toFixed(1)}° mech · ` +
               `|B| 0 … ${deckel.toFixed(2)} T · EINE Eichung für alle Scheiben`,
               W - 10, 16);
  // Radiusachse LINKS am Bildrand. Sie stand vorher bei `X(-40)`, also je nach
  // Baulaenge ausserhalb der Leinwand -- unsichtbar, und niemand haette es
  // gemerkt, weil ein fehlender Text wie ein leerer Rand aussieht.
  ctx.textAlign = "left"; ctx.strokeStyle = "#6b7482"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(26, Y(p.ri)); ctx.lineTo(26, Y(p.ro)); ctx.stroke();
  for (const [r, t] of [[p.ri, "Ri"], [p.ro, "Ro"]]) {
    ctx.beginPath(); ctx.moveTo(22, Y(r)); ctx.lineTo(X(0) - 4, Y(r)); ctx.stroke();
    ctx.fillStyle = "#e8a33d";
    ctx.fillText(`${t} ${r.toFixed(0)}`, 30, Y(r) + (r === p.ri ? 14 : -6));
  }
  ctx.fillStyle = "#8a93a3"; ctx.save();
  ctx.translate(14, (Y(p.ri) + Y(p.ro)) / 2); ctx.rotate(-Math.PI / 2);
  ctx.textAlign = "center"; ctx.fillText("Radius", 0, 0); ctx.restore();
  // Die waagerechte Baenderung IST die Scheibenzahl -- sie zu glaetten hiesse,
  // die Aufloesung des Modells zu verstecken.
  ctx.textAlign = "left"; ctx.fillStyle = "#8a93a3"; ctx.font = "11px system-ui";
  ctx.fillText(`Bänder = Scheiben (${erg.nSch}); Feldlinien gibt es hier nicht, ` +
               `sie bräuchten B_r — das Scheibenmodell hat keines`, 26, H - 6);
  return f;
}

/* ---- Zeichnen: die Spaltebene ueber ALLE 360 Grad ------------------------
 * Faellt beim Mehrschnitt gratis ab und ist die eigentliche Antwort auf „ein
 * Winkel oder alle": die Scheiben tragen ihren ganzen Umfang, es wird nur
 * abgelesen. Ein Fenster ist EINE elektrische Periode, also wird es `p` mal
 * umlaufend wiederholt — ohne Vorzeichenwechsel, denn eine Periode ist zwei
 * Pole. */
function zeichneSpaltScheibe(cv, p, erg, theta, deckel) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2, s = (Math.min(W, H) / 2 - 30) / (p.ro + 6);
  const nA = 360, dr = (p.ro - p.ri) / erg.nSch;
  const thW = 2 * (2 * Math.PI / p.poles);
  for (let a = 0; a < nA; a++) {
    const th0 = a * 2 * Math.PI / nA, th1 = (a + 1) * 2 * Math.PI / nA;
    const tw = ((th0 % thW) + thW) % thW;
    for (let k = 0; k < erg.nSch; k++) {
      const sc = erg.scheiben[k], g = sc.g;
      let i = Math.floor((tw * sc.r) / g.dx);
      i = Math.max(1, Math.min(g.nx - 2, i));
      const bz = sc.By[erg.jGap * g.nx + i] * sc.sf;
      const t = Math.max(-1, Math.min(1, bz / deckel));
      // Vorzeichen zeigen: rot = zum Staender, blau = zurueck. Der Betrag
      // allein verschwiege den Polwechsel, und der ist hier die Hauptsache.
      const u = Math.abs(t);
      ctx.fillStyle = t >= 0 ? `rgb(${(40+215*u)|0},${(35+40*u)|0},${(45+30*u)|0})`
                             : `rgb(${(35+30*u)|0},${(40+95*u)|0},${(50+185*u)|0})`;
      ctx.beginPath();
      ctx.arc(cx, cy, s * (p.ri + (k + 1) * dr), -th1, -th0, false);
      ctx.arc(cx, cy, s * (p.ri + k * dr), -th0, -th1, true);
      ctx.closePath(); ctx.fill();
    }
  }
  // Der gerade betrachtete Schnitt als Strahl
  ctx.strokeStyle = "#e8a33d"; ctx.lineWidth = 1.6; ctx.setLineDash([6, 4]);
  ctx.beginPath();
  ctx.moveTo(cx + s * (p.ri - 8) * Math.cos(theta), cy - s * (p.ri - 8) * Math.sin(theta));
  ctx.lineTo(cx + s * (p.ro + 8) * Math.cos(theta), cy - s * (p.ro + 8) * Math.sin(theta));
  ctx.stroke(); ctx.setLineDash([]);
  ctx.fillStyle = "#5d6470"; ctx.beginPath(); ctx.arc(cx, cy, s * p.welle, 0, 2 * Math.PI); ctx.fill();
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`B_z in der Spaltmitte · ${erg.nSch} Ringe × 360° — abgelesen, nicht gerechnet`, 10, 18);
  ctx.textAlign = "right";
  ctx.fillText(`rot ±${deckel.toFixed(2)} T blau`, W - 10, 18);
}

/* ---- Zeichnen: B_Zahn ueber dem Radius ---------------------------------- */
function zeichneZahnKurve(cv, p, erg) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const v = zahnVerlauf(erg, p);
  if (!v.length) return v;
  const pad = { l: 58, r: 14, o: 26, u: 34 };
  const bmax = Math.max(...v.map((a) => Math.max(a.b_zahn, a.b_zahn_geo, a.b_spalt))) * 1.12;
  const X = (r) => pad.l + (W - pad.l - pad.r) * (r - p.ri) / (p.ro - p.ri);
  const Y = (b) => H - pad.u - (H - pad.o - pad.u) * b / bmax;
  ctx.strokeStyle = "#2e333d"; ctx.lineWidth = 1;
  for (let t = 0; t <= 4; t++) {
    const y = Y(bmax * t / 4);
    ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
    ctx.fillStyle = "#8a93a3"; ctx.font = "11px system-ui"; ctx.textAlign = "right";
    ctx.fillText((bmax * t / 4).toFixed(2), pad.l - 6, y + 4);
  }
  const kurve = (holen, farb, br, strich) => {
    ctx.strokeStyle = farb; ctx.lineWidth = br;
    ctx.setLineDash(strich || []); ctx.beginPath();
    v.forEach((a, i) => (i ? ctx.lineTo(X(a.r), Y(holen(a))) : ctx.moveTo(X(a.r), Y(holen(a)))));
    ctx.stroke(); ctx.setLineDash([]);
  };
  kurve((a) => a.b_spalt, "#7fd4ff", 1.6);
  kurve((a) => a.b_zahn_geo, "#8a93a3", 1.4, [5, 4]);
  kurve((a) => a.b_zahn, "#e8a33d", 2.2);
  ctx.fillStyle = "#8a93a3"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
  ctx.fillText("Ri", X(p.ri), H - 14); ctx.fillText("Ro", X(p.ro), H - 14);
  ctx.fillText("Radius", (pad.l + W - pad.r) / 2, H - 2);
  ctx.textAlign = "left"; ctx.font = "12px system-ui";
  ctx.fillStyle = "#e8a33d"; ctx.fillText("B_Zahn gemessen", pad.l + 8, 16);
  ctx.fillStyle = "#8a93a3"; ctx.fillText("· aus der Geometrie (B_Spalt·τs/(τs−b))", pad.l + 128, 16);
  ctx.fillStyle = "#7fd4ff"; ctx.fillText("· B_Spalt", W - 76, 16);
  return v;
}

if (typeof module !== "undefined" && module.exports)
  module.exports = { schnittRechnen, rzBei, zahnVerlauf, radialeKopplung };
