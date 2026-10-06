/* axialfluss_ansicht.js — drei Ansichten einer Axialflussmaschine.
 *
 * Die eine Stelle, an der sich diese Bauart von jeder anderen unterscheidet,
 * ist die NUT: sie verlaeuft radial und ist PARALLELFLANKIG, weil die Leiter
 * ihre Abmessung ueber dem Radius nicht aendern (Igelspacher, Kap. 2.1).
 * Daraus folgt alles Weitere -- die Zaehne werden nach aussen breiter, die
 * Zahnflussdichte ist am Innenrand am hoechsten, und der Innenradius wird vom
 * inneren Wickelkopf bestimmt, nicht vom Platz fuer den Magneten.
 *
 * Eine Nut, die als Kreissektor gezeichnet waere (zwei Radien als Flanken),
 * waere die haeufigste falsche Darstellung und zugleich eine andere Maschine:
 * dann haetten Zahn und Nut ueber dem Radius ein festes Verhaeltnis, die
 * Zahnflussdichte waere konstant, und der kritische Punkt am Innenrand gaebe
 * es nicht. `nutPfad` zeichnet deshalb zwei GERADEN im Abstand b und schliesst
 * sie mit Boegen auf Ri und Ro.
 */
"use strict";

const $ = (id) => document.getElementById(id);
const TAU = Math.PI * 2;

const TOPO_TEXT = {
  eser: "Ein magnetisch wirksamer Luftspalt. Einfachste Konstruktion, wenigste " +
        "Toleranzketten — aber der axiale Längszug gleicht sich NICHT aus und " +
        "muss dauerhaft von einem Lager getragen werden. Daher eher kleine Leistungen.",
  dser: "Der Läufer braucht grundsätzlich KEIN Joch: der Fluss geht axial durch " +
        "seine Zähne von einem Ständer zum anderen. Nur ein Restjoch zur " +
        "Wellenanbindung. Zwei Spalte → Kräfte heben sich bei mittigem Läufer auf. " +
        "Die beiden Wicklungen müssen 120° el. verdreht UND gespiegelt sein.",
  esdr: "Der Ständer kann theoretisch ohne Joch ausgeführt werden (Restjoch für " +
        "die Festigkeit der Wicklung). Die Wicklung läuft beidseitig herum, ohne " +
        "Kreuzungen im Wickelkopf → kompakter. Dafür zwei Läuferjoche, also mehr " +
        "rotierende Masse.",
};
const LF_TEXT = {
  sektor:   "Sektormagnete flach auf der Scheibe — keine Tasche, kein Steg, kein " +
            "Reluktanzmoment (Ld = Lq).",
  halbach:  "Halbach-Array: die Magnetisierung dreht von Segment zu Segment und " +
            "bündelt den Fluss auf einer Seite — erlaubt den Verzicht auf " +
            "ferromagnetisches Läufermaterial.",
  kaefig:   "Läuferzähne mit Kurzschlusskäfig: die Stäbe liegen radial, die " +
            "Kurzschlussringe innen UND außen. Das ist die Axialfluss-ASM.",
  eisenlos: "Eisenloser bzw. gedruckter Scheibenanker: der Läufer trägt die " +
            "WICKLUNG, nicht die Magnete, und hat keinerlei Eisen. Kein " +
            "Rastmoment, kleinste Trägheit — die älteste axiale Bauform.",
};

function P() {
  const ro = +$("ro").value, lam = +$("lam").value;
  const p = {
    topo: $("topo").value, laeufer: $("laeufer").value,
    stapel: +$("stapel").value,
    ro, ri: lam * ro, lam,
    poles: +$("poles").value, q: +$("q").value, bnut: +$("bnut").value,
    spalt: +$("spalt").value, zahn: +$("zahn").value,
    jochS: +$("jochS").value, jochR: +$("jochR").value,
    magd: +$("magd").value, alpha: +$("alpha").value,
    welle: +$("welle").value / 2, wkI: +$("wkI").value,
    sektor: +$("sektor").value * Math.PI / 180,
    fluss: $("fluss").checked, masse: $("masse").checked,
    last: +$("last").value, netz: +$("netz").value, iter: +$("iter").value,
    feldAn: $("feldAn").checked,
  };
  p.rs = p.ri + (p.ro - p.ri) * (+$("rschnitt").value / 100);
  // Der Laeufer der DSER-Bauart traegt Zaehne und Kaefig und KEIN Joch --
  // das ist der Kern dieser Topologie, nicht eine Einstellung.
  p.rotorOhneJoch = (p.topo === "dser");
  p.statorOhneJoch = (p.topo === "esdr");
  p.nSpalte = p.topo === "eser" ? 1 : 2;
  return p;
}

/* ---- die parallelflankige Nut ------------------------------------------ */
function nutPfad(ctx, cx, cy, s, theta, b, ri, ro) {
  // Flanken: zwei Geraden im Abstand b, parallel zur Radiusrichtung theta.
  // Ein Punkt r*u + t*n hat den Betrag sqrt(r^2+t^2); die Ecken liegen also
  // nicht bei Winkel theta, sondern um asin((b/2)/R) versetzt.
  const h = b / 2;
  if (h >= ri) return false;                    // Nut breiter als die Bohrung
  const aO = Math.asin(Math.min(1, h / ro));
  const aI = Math.asin(Math.min(1, h / ri));
  const Pt = (r, t) => [cx + s * (r * Math.cos(theta) - t * Math.sin(theta)),
                        cy - s * (r * Math.sin(theta) + t * Math.cos(theta))];
  const rO = Math.sqrt(Math.max(0, ro * ro - h * h));
  const rI = Math.sqrt(Math.max(0, ri * ri - h * h));
  ctx.beginPath();
  const [x0, y0] = Pt(rI, +h); ctx.moveTo(x0, y0);
  const [x1, y1] = Pt(rO, +h); ctx.lineTo(x1, y1);
  ctx.arc(cx, cy, s * ro, -(theta + aO), -(theta - aO), false);
  const [x3, y3] = Pt(rI, -h); ctx.lineTo(x3, y3);
  ctx.arc(cx, cy, s * ri, -(theta - aI), -(theta + aI), true);
  ctx.closePath();
  return true;
}

function ring(ctx, cx, cy, s, ri, ro, a0, a1) {
  ctx.beginPath();
  ctx.arc(cx, cy, s * ro, -a1, -a0, false);
  ctx.arc(cx, cy, s * ri, -a0, -a1, true);
  ctx.closePath();
}

/* ---- 1. Draufsicht ------------------------------------------------------ */
function draufsicht(cv, p) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const cx = W / 2, cy = H / 2;
  const rAussen = p.ro + p.wkI * 0.9 + 8;
  const s = (Math.min(W, H) / 2 - 26) / rAussen;

  // Wickelkopf aussen und innen -- beide gehoeren zur Bauart.
  ctx.fillStyle = "#6b4a24";
  ring(ctx, cx, cy, s, p.ro, p.ro + p.wkI * 0.9, 0, TAU); ctx.fill();
  ring(ctx, cx, cy, s, Math.max(p.welle, p.ri - p.wkI), p.ri, 0, TAU); ctx.fill();

  // Staenderblech
  ctx.fillStyle = "#49525f";
  ring(ctx, cx, cy, s, p.ri, p.ro, 0, TAU); ctx.fill();

  // Nuten -- parallelflankig. Hier entscheidet sich, ob das Bild stimmt.
  const nutbar = [];
  for (let i = 0; i < p.q; i++) {
    const th = i * TAU / p.q;
    if (nutPfad(ctx, cx, cy, s, th, p.bnut, p.ri, p.ro)) {
      ctx.fillStyle = "#101216"; ctx.fill();
      ctx.fillStyle = "#c87f3a"; ctx.globalAlpha = .55;
      if (nutPfad(ctx, cx, cy, s, th, p.bnut * .72, p.ri, p.ro)) ctx.fill();
      ctx.globalAlpha = 1; nutbar.push(th);
    }
  }

  // Laeufer, ueber dem Sektor aufgeschnitten
  if (p.sektor > 0.01) {
    const a0 = -p.sektor / 2, a1 = p.sektor / 2;
    ctx.save();
    ctx.beginPath(); ctx.moveTo(cx, cy);
    ctx.arc(cx, cy, s * (p.ro + 2), -a1, -a0, false); ctx.closePath(); ctx.clip();
    ctx.fillStyle = "#0b0d11";
    ring(ctx, cx, cy, s, p.ri - 1, p.ro + 1, a0, a1); ctx.fill();
    laeuferFlaeche(ctx, cx, cy, s, p, a0, a1);
    ctx.restore();
    ctx.strokeStyle = "#e8a33d"; ctx.lineWidth = 1.1; ctx.setLineDash([5, 4]);
    for (const a of [a0, a1]) {
      ctx.beginPath();
      ctx.moveTo(cx + s * (p.ri - 6) * Math.cos(a), cy - s * (p.ri - 6) * Math.sin(a));
      ctx.lineTo(cx + s * (p.ro + 10) * Math.cos(a), cy - s * (p.ro + 10) * Math.sin(a));
      ctx.stroke();
    }
    ctx.setLineDash([]);
  }

  // Welle
  ctx.fillStyle = "#5d6470"; ctx.beginPath();
  ctx.arc(cx, cy, s * p.welle, 0, TAU); ctx.fill();

  // Bemassung: Zahnbreite innen gegen aussen -- die Aussage des Bildes
  if (p.masse && nutbar.length > 1) {
    const zi = TAU * p.ri / p.q - p.bnut, za = TAU * p.ro / p.q - p.bnut;
    ctx.font = "12px system-ui"; ctx.textAlign = "center";
    ctx.fillStyle = "#e8a33d";
    ctx.fillText(`Zahn innen ${zi.toFixed(1)} mm`, cx, cy - s * (p.ri + 9));
    ctx.fillText(`Zahn außen ${za.toFixed(1)} mm`, cx, cy - s * (p.ro - 5));
    ctx.fillStyle = "#8a93a3";
    ctx.fillText(`Nut ${p.bnut.toFixed(1)} mm — über r konstant`, cx, cy + s * p.ro + 17);
  }
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`Ständer: ${p.q} radiale Nuten · 2p = ${p.poles}`, 10, 18);
}

function laeuferFlaeche(ctx, cx, cy, s, p, a0, a1) {
  const n = p.poles, pb = p.alpha;
  if (p.laeufer === "kaefig") {
    const qr = Math.max(6, Math.round(p.q * 0.86));
    ctx.fillStyle = "#49525f";
    ring(ctx, cx, cy, s, p.ri, p.ro, a0, a1); ctx.fill();
    for (let i = 0; i < qr; i++) {
      const th = i * TAU / qr;
      let d = ((th - (a0 + a1) / 2 + Math.PI * 3) % TAU) - Math.PI;
      if (Math.abs(d) > (a1 - a0) / 2 + .05) continue;
      if (nutPfad(ctx, cx, cy, s, th, p.bnut * .8, p.ri, p.ro)) {
        ctx.fillStyle = "#9aa4b0"; ctx.fill();
      }
    }
    ctx.fillStyle = "#9aa4b0";
    ring(ctx, cx, cy, s, p.ro, p.ro + 4, a0, a1); ctx.fill();
    ring(ctx, cx, cy, s, p.ri - 4, p.ri, a0, a1); ctx.fill();
    ctx.fillStyle = "#dfe4ec"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText("Läuferzähne + Käfig", cx + s * (p.ro * .7) * Math.cos((a0 + a1) / 2),
                 cy - s * (p.ro * .7) * Math.sin((a0 + a1) / 2));
  } else if (p.laeufer === "eisenlos") {
    // Scheibenanker: KEIN Eisen, nur radiale Leiterbahnen.
    const nl = p.poles * 9;
    ctx.strokeStyle = "#c87f3a"; ctx.lineWidth = Math.max(1, s * p.bnut * .35);
    for (let i = 0; i < nl; i++) {
      const th = i * TAU / nl;
      let d = ((th - (a0 + a1) / 2 + Math.PI * 3) % TAU) - Math.PI;
      if (Math.abs(d) > (a1 - a0) / 2) continue;
      ctx.beginPath();
      ctx.moveTo(cx + s * p.ri * Math.cos(th), cy - s * p.ri * Math.sin(th));
      ctx.lineTo(cx + s * p.ro * Math.cos(th), cy - s * p.ro * Math.sin(th));
      ctx.stroke();
    }
    ctx.fillStyle = "#dfe4ec"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText("eisenloser Anker — Leiterbahnen", 
                 cx + s * (p.ro * .72) * Math.cos((a0 + a1) / 2),
                 cy - s * (p.ro * .72) * Math.sin((a0 + a1) / 2));
  } else {
    const seg = p.laeufer === "halbach" ? 4 : 1;
    if (p.laeufer !== "halbach") {
      ctx.fillStyle = "#39414c"; ring(ctx, cx, cy, s, p.ri, p.ro, a0, a1); ctx.fill();
    }
    for (let k = 0; k < n * seg; k++) {
      const w = TAU / (n * seg), th0 = k * w, th1 = th0 + w * (seg > 1 ? 1 : pb);
      const m0 = th0 + w * (1 - (seg > 1 ? 1 : pb)) / 2;
      const mid = (m0 + m0 + w * (seg > 1 ? 1 : pb)) / 2;
      let d = ((mid - (a0 + a1) / 2 + Math.PI * 3) % TAU) - Math.PI;
      if (Math.abs(d) > (a1 - a0) / 2 + w) continue;
      const pol = seg > 1 ? (k % 4) : (k % 2);
      ctx.fillStyle = seg > 1
        ? ["#c0392b", "#8e44ad", "#2e6fb7", "#8e44ad"][pol]
        : (pol ? "#2e6fb7" : "#c0392b");
      ring(ctx, cx, cy, s, p.ri, p.ro, m0, m0 + w * (seg > 1 ? 1 : pb));
      ctx.save(); ctx.clip();
      ring(ctx, cx, cy, s, p.ri, p.ro, a0, a1); ctx.fill(); ctx.restore();
    }
    ctx.fillStyle = "#dfe4ec"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText(p.laeufer === "halbach" ? "Halbach — kein Rotoreisen" : "Sektormagnete",
                 cx + s * (p.ro * .72) * Math.cos((a0 + a1) / 2),
                 cy - s * (p.ro * .72) * Math.sin((a0 + a1) / 2));
  }
}

/* ---- 2. Halbschnitt r-z ------------------------------------------------- */
/* Die Achse liegt UNTEN, r waechst nach oben. Diese Ansicht traegt die eine
 * Aussage, die der abgewickelte Schnitt nicht geben kann: dass der Durchmesser
 * groesser ist als die Baulaenge und der Fluss parallel zur Drehachse laeuft.
 * Sie ist zugleich die Ebene, in der man NICHT rechnen kann -- Invarianz in
 * theta hiesse eine Maschine ohne Pole. */

function halbschnitt(cv, p) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const lagen = stapelLagen(p);
  const hGes = lagen.reduce((a, l) => a + l.d, 0);
  const rMax = p.ro + p.wkI * 0.9 + 6;
  const pad = 54;
  const s = Math.min((W - 2 * pad) / Math.max(hGes * 1.25, 1), (H - 2 * pad) / rMax);
  const z0 = W / 2 - s * hGes / 2, achse = H - pad;
  const Y = (r) => achse - s * r, X = (z) => z0 + s * z;

  // Welle ueber die ganze Baulaenge -- sie ist der Grund, warum der innere
  // Wickelkopf den Innenradius bindet.
  ctx.fillStyle = "#5d6470";
  ctx.fillRect(X(-16), Y(p.welle), s * (hGes + 32), s * p.welle);
  ctx.strokeStyle = "#767e8b"; ctx.lineWidth = 1;
  ctx.strokeRect(X(-16), Y(p.welle), s * (hGes + 32), s * p.welle);

  let z = 0;
  for (const l of lagen) {
    const x = X(z), w = s * l.d;
    if (l.art === "spalt") {
      ctx.fillStyle = "#e8a33d"; ctx.globalAlpha = .3;
      ctx.fillRect(x, Y(p.ro), w, s * (p.ro - p.ri)); ctx.globalAlpha = 1;
    } else if (l.art === "stator") {
      const dz = p.zahn * s, dj = w - dz;
      // Joch: voller Ring. Zahnband: Zaehne mit Nuten dazwischen.
      const jx = l.seite === "unten" ? x : (l.seite === "beide" ? x + dz / 2 : x + dz);
      if (dj > 0.5) { ctx.fillStyle = "#49525f";
        ctx.fillRect(l.seite === "beide" ? x + dz / 2 : jx, Y(p.ro), dj, s * (p.ro - p.ri)); }
      const zx = l.seite === "unten" ? x + dj : x;
      ctx.fillStyle = "#49525f"; ctx.fillRect(zx, Y(p.ro), dz, s * (p.ro - p.ri));
      ctx.fillStyle = "#c87f3a";
      const nl = 9;
      for (let i = 0; i < nl; i++) {
        const rr = p.ri + (p.ro - p.ri) * (i + .5) / nl;
        ctx.globalAlpha = .75;
        ctx.fillRect(zx + dz * .18, Y(rr) - 1.5, dz * .64, 3);
      }
      ctx.globalAlpha = 1;
      // Wickelkoepfe innen UND aussen
      ctx.fillStyle = "#6b4a24";
      ctx.fillRect(zx - s * 2, Y(p.ro + p.wkI * .9), dz + s * 4, s * p.wkI * .9);
      ctx.fillRect(zx - s * 2, Y(p.ri), dz + s * 4, s * Math.min(p.wkI, p.ri - p.welle));
    } else if (l.art === "rotor") {
      const dm = p.magd * s, dj = w - dm;
      // Im r-z-Bild waechst z nach RECHTS. "unten" heisst: der Spalt liegt bei
      // kleinerem z, also LINKS -- dorthin gehoert der Magnet.
      const mx = (l.seite === "oben") ? x + dj : x;
      const jxr = (l.seite === "oben") ? x : x + dm;
      if (dj > .5) { ctx.fillStyle = "#39414c"; ctx.fillRect(jxr, Y(p.ro), dj, s * (p.ro - p.ri)); }
      const x_ = mx;
      if (p.laeufer === "kaefig") {
        ctx.fillStyle = "#49525f"; ctx.fillRect(x_, Y(p.ro), dm, s * (p.ro - p.ri));
        ctx.fillStyle = "#9aa4b0";
        for (let i = 0; i < 9; i++) {
          const rr = p.ri + (p.ro - p.ri) * (i + .5) / 9;
          ctx.fillRect(x_ + dm * .2, Y(rr) - 1.5, dm * .6, 3);
        }
        ctx.fillRect(x_, Y(p.ro + 4), dm, s * 4);     // Kurzschlussring aussen
        ctx.fillRect(x_, Y(p.ri), dm, s * 4);         // und innen
      } else if (p.laeufer === "eisenlos") {
        ctx.fillStyle = "#c87f3a"; ctx.fillRect(x_, Y(p.ro), dm * .5, s * (p.ro - p.ri));
      } else {
        // EIN Pol: der Schnitt steht an einer Winkellage, der Polwechsel liegt
        // in theta. Ueber dem Radius die Polung zu wechseln waere eine Maschine
        // mit Polen in RADIALER Richtung -- die es nicht gibt.
        ctx.fillStyle = "#c0392b";
        ctx.fillRect(x_, Y(p.ro), dm, s * (p.ro - p.ri));
        ctx.fillStyle = "#dfe4ec"; ctx.font = "10px system-ui"; ctx.textAlign = "center";
        ctx.save(); ctx.translate(x_ + dm / 2, Y((p.ri + p.ro) / 2)); ctx.rotate(-Math.PI / 2);
        ctx.fillText("N", 0, 3); ctx.restore();
      }
      // Scheibenblatt bis zur Nabe -- der Laeufer haengt an der Welle, er
      // schwebt nicht im Ringraum.
      ctx.fillStyle = "#39414c";
      const blatt = Math.max(dj, dm * .5);
      ctx.fillRect(dj > .5 ? jxr : x, Y(p.ri), blatt, s * (p.ri - p.welle));
    }
    z += l.d;
  }

  // Flusspfad: axial durch Spalt und Zaehne, umfangs im Joch -- im r-z-Schnitt
  // nur als Andeutung, denn umfangs steht hier senkrecht zur Bildebene.
  if (p.fluss) {
    ctx.strokeStyle = "#7fd4ff"; ctx.lineWidth = 1.6; ctx.globalAlpha = .85;
    const rr = (p.ri + p.ro) / 2;
    ctx.beginPath(); ctx.moveTo(X(0), Y(rr)); ctx.lineTo(X(hGes), Y(rr)); ctx.stroke();
    for (const t of [0.22, 0.78]) {
      const xx = X(hGes * t);
      ctx.beginPath(); ctx.moveTo(xx - 7, Y(rr) - 5); ctx.lineTo(xx + 5, Y(rr));
      ctx.lineTo(xx - 7, Y(rr) + 5); ctx.stroke();
    }
    ctx.globalAlpha = 1;
    ctx.fillStyle = "#7fd4ff"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText("Fluss ∥ Drehachse", X(hGes / 2), Y(rr) - 10);
  }

  // Achse + Bemassung
  ctx.strokeStyle = "#6b7482"; ctx.setLineDash([9, 5]); ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(X(-18), achse); ctx.lineTo(X(hGes + 18), achse); ctx.stroke();
  ctx.setLineDash([]);
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui";
  ctx.textAlign = "left"; ctx.fillText("Drehachse", X(-16), achse + 16);
  if (p.masse) {
    ctx.textAlign = "center"; ctx.fillStyle = "#e8a33d";
    ctx.fillText(`Baulänge ${hGes.toFixed(0)} mm`, X(hGes / 2), achse + 16);
    ctx.fillText(`Ø ${(2 * p.ro).toFixed(0)} mm`, X(hGes / 2), Y(p.ro) - 22);
    ctx.fillStyle = hGes < 2 * p.ro ? "#8a93a3" : "#e06c5a";
    ctx.fillText(hGes < 2 * p.ro ? "Durchmesser > Baulänge ✓ (Pancake)"
                                 : "⚠ länger als dick — keine Scheibenbauform",
                 X(hGes / 2), achse + 32);
  }
  ctx.fillStyle = "#8a93a3"; ctx.textAlign = "left";
  ctx.fillText(p.topo.toUpperCase() + (p.stapel > 1 ? ` · ${p.stapel}× Stapel` : ""), 10, 18);
}

/* ---- 3. Abgewickelter Schnitt bei r ------------------------------------- */
/* x = Umfang bei r, y = axial. Die EINZIGE Ebene, in der ein 2-D-Loeser
 * rechnen kann: die Invarianzrichtung ist r, und die gilt lokal. Eine Ebene
 * durch die Achse (r-z) verlangte Invarianz in theta -- und dort liegt der
 * Polwechsel, also haette eine solche Maschine gar keine Pole. */
function abwicklung(cv, p) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const lagen = stapelLagen(p).filter(l => l.art !== "fuge");
  const hGes = lagen.reduce((a, l) => a + l.d, 0);
  const tauP = TAU * p.rs / p.poles, tauS = TAU * p.rs / p.q;
  const nPol = 2, breite = nPol * tauP;
  const pad = 34;
  const s = Math.min((W - 2 * pad) / breite, (H - 2 * pad) / hGes);
  const x0 = (W - s * breite) / 2, y0 = H - pad;
  const X = (u) => x0 + s * u, Y = (z) => y0 - s * z;

  let z = 0;
  for (const l of lagen) {
    const yT = Y(z + l.d), hh = s * l.d;
    if (l.art === "spalt") {
      ctx.fillStyle = "#e8a33d"; ctx.globalAlpha = .22;
      ctx.fillRect(X(0), yT, s * breite, hh); ctx.globalAlpha = 1;
    } else if (l.art === "stator") {
      const dz = p.zahn * s, dj = hh - dz;
      ctx.fillStyle = "#49525f"; ctx.fillRect(X(0), yT, s * breite, hh);
      // Nuten: HIER sind sie gleich breit wie ueberall -- sie sind ja
      // parallelflankig. Was sich mit r aendert, ist ihr ABSTAND.
      const zTop = l.seite === "unten" ? yT + dj : yT;
      ctx.fillStyle = "#101216";
      for (let i = 0; i * tauS < breite + tauS; i++) {
        const u = (i + .5) * tauS;
        if (u - p.bnut / 2 > breite) break;
        ctx.fillRect(X(u - p.bnut / 2), zTop, s * p.bnut, dz);
        ctx.fillStyle = "#c87f3a"; ctx.globalAlpha = .6;
        ctx.fillRect(X(u - p.bnut * .36), zTop + dz * .12, s * p.bnut * .72, dz * .76);
        ctx.globalAlpha = 1; ctx.fillStyle = "#101216";
      }
    } else if (l.art === "rotor") {
      const dm = p.magd * s, dj = hh - dm;
      // yT ist die OBERkante des Bandes. "oben" = Spalt oberhalb -> Magnet oben.
      const mTop = (l.seite === "unten") ? yT + dj : yT;
      const jTop = (l.seite === "unten") ? yT : yT + dm;
      if (dj > .5) { ctx.fillStyle = "#39414c"; ctx.fillRect(X(0), jTop, s * breite, dj); }
      if (p.laeufer === "kaefig") {
        const qr = Math.max(6, Math.round(p.q * .86)), tauR = TAU * p.rs / qr;
        ctx.fillStyle = "#49525f"; ctx.fillRect(X(0), mTop, s * breite, dm);
        ctx.fillStyle = "#9aa4b0";
        for (let i = 0; (i + .5) * tauR < breite; i++)
          ctx.fillRect(X((i + .5) * tauR - p.bnut * .4), mTop + dm * .1, s * p.bnut * .8, dm * .8);
      } else if (p.laeufer === "eisenlos") {
        ctx.fillStyle = "#c87f3a";
        for (let i = 0; i * tauS * .5 < breite; i++)
          ctx.fillRect(X(i * tauS * .5), mTop, Math.max(1, s * p.bnut * .3), dm);
      } else {
        const seg = p.laeufer === "halbach" ? 4 : 1, wSeg = tauP / seg;
        for (let i = 0; i * wSeg < breite; i++) {
          const u = i * wSeg, bw = wSeg * (seg > 1 ? 1 : p.alpha);
          const off = wSeg * (1 - (seg > 1 ? 1 : p.alpha)) / 2;
          const k = i % (seg > 1 ? 4 : 2);
          ctx.fillStyle = seg > 1 ? ["#c0392b", "#8e44ad", "#2e6fb7", "#8e44ad"][k]
                                  : (k ? "#2e6fb7" : "#c0392b");
          ctx.fillRect(X(u + off), mTop, s * bw, dm);
        }
      }
    }
    z += l.d;
  }

  if (p.masse) {
    ctx.strokeStyle = "#e8a33d"; ctx.lineWidth = 1; ctx.setLineDash([4, 3]);
    for (let i = 0; i <= nPol; i++) {
      ctx.beginPath(); ctx.moveTo(X(i * tauP), Y(0) + 6);
      ctx.lineTo(X(i * tauP), Y(hGes) - 6); ctx.stroke();
    }
    ctx.setLineDash([]);
    ctx.fillStyle = "#e8a33d"; ctx.font = "12px system-ui"; ctx.textAlign = "center";
    ctx.fillText(`Polteilung ${tauP.toFixed(1)} mm`, X(tauP / 2), Y(hGes) - 10);
    ctx.fillStyle = "#8a93a3";
    ctx.fillText(`Nutteilung ${tauS.toFixed(1)} mm · Nut ${p.bnut} mm · ` +
                 `Zahn ${(tauS - p.bnut).toFixed(1)} mm`, X(breite / 2), Y(0) + 20);
  }
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`abgewickelt bei r = ${p.rs.toFixed(1)} mm`, 10, 18);
}

/* ---- Masse aus der Zeichnung -------------------------------------------- */
function tabelle(p) {
  const zi = TAU * p.ri / p.q - p.bnut, za = TAU * p.ro / p.q - p.bnut;
  const rMinZahn = p.q * p.bnut / TAU;            // Zahnbreite -> 0
  const rMinWk = p.welle + p.wkI;                 // innerer Wickelkopf
  const tauI = TAU * p.ri / p.poles, tauA = TAU * p.ro / p.poles;
  const hGes = stapelLagen(p).reduce((a, l) => a + l.d, 0);
  const B = 0.95, sig = B * B / (2 * 4e-7 * Math.PI);
  const A = Math.PI * ((p.ro / 1e3) ** 2 - (p.ri / 1e3) ** 2);
  const bad = (c, t) => c ? `<span class="bad">${t}</span>` : t;
  const warn = (c, t) => c ? `<span class="warn">${t}</span>` : t;
  const r = [
    ["Ringraum", `Ri ${p.ri.toFixed(1)} … Ro ${p.ro.toFixed(1)} mm   (λ = ${p.lam.toFixed(3)})`],
    ["Zahnbreite innen → außen",
      bad(zi <= 0, `${zi.toFixed(2)} → ${za.toFixed(2)} mm  (×${(za / Math.max(zi, 1e-6)).toFixed(2)})`)],
    ["B_Zahn innen / außen",
      `${(tauI / p.poles * p.poles / Math.max(zi, 1e-6) / (tauA / Math.max(za, 1e-6))).toFixed(2)}× — ` +
      `kritisch am <b>Innen</b>rand`],
    ["Ri aus Zahnbreite ≥ 0", bad(p.ri < rMinZahn, `${rMinZahn.toFixed(1)} mm`)],
    ["Ri aus innerem Wickelkopf",
      warn(p.ri < rMinWk, `${rMinWk.toFixed(1)} mm` + (p.ri < rMinWk ? " — Ri zu klein" : ""))],
    ["bindend für Ri", (() => {
        const grenze = Math.max(rMinZahn, rMinWk);
        const wer = rMinWk > rMinZahn ? "innerer Wickelkopf (Welle begrenzt ihn)" : "Zahnbreite";
        if (p.ri > grenze * 1.02)
          return `keine — Ri ist frei gewählt, beide Schranken liegen bei ` +
                 `≤ ${grenze.toFixed(1)} mm. Enger ginge bis dahin.`;
        return `<b>${wer}</b> bei ${grenze.toFixed(1)} mm`;
      })()],
    ["Polteilung innen → außen", `${tauI.toFixed(1)} → ${tauA.toFixed(1)} mm`],
    ["Spalt / Polteilung", `${(p.spalt / tauI).toFixed(4)} innen → ${(p.spalt / tauA).toFixed(4)} außen ` +
      `(×${(tauA / tauI).toFixed(2)} über r)`],
    ["Baulänge / Durchmesser",
      bad(hGes >= 2 * p.ro, `${hGes.toFixed(0)} / ${(2 * p.ro).toFixed(0)} mm = ${(hGes / (2 * p.ro)).toFixed(2)}`)],
    ["Luftspalte", `${p.nSpalte * p.stapel}` + (p.nSpalte > 1 ? " — Anzug hebt sich auf" :
      " — <span class='warn'>Anzug liegt am Lager</span>")],
    ["axialer Anzug je Spalt (bei B = 0,95 T)",
      `${(sig * A / 1e3).toFixed(1)} kN   (σ = ${(sig / 1e3).toFixed(0)} kPa)`],
    ["Läuferjoch", p.rotorOhneJoch ? "<b>entfällt</b> — Fluss geht axial durch die Läuferzähne"
                                   : `${p.jochR} mm`],
    ["Ständerjoch", p.statorOhneJoch ? "<b>entfällt</b> (Restjoch für die Wicklung)" : `${p.jochS} mm`],
  ];
  $("tab").innerHTML = r.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join("");
}

/* ---- Anstoss ------------------------------------------------------------ */
function zeichne() {
  const p = P();
  $("topo_hint").textContent = TOPO_TEXT[p.topo];
  $("lf_hint").textContent = LF_TEXT[p.laeufer];
  $("sek_v").textContent = Math.round(p.sektor * 180 / Math.PI);
  $("rs_v").textContent = p.rs.toFixed(0);
  $("rs_t").textContent = `r = ${p.rs.toFixed(1)} mm`;
  draufsicht($("c_front"), p);
  halbschnitt($("c_schnitt"), p);
  abwicklung($("c_abw"), p);
  tabelle(p);
  // Das Feld kostet Rechenzeit und wird deshalb nur auf Zuruf gerechnet --
  // sonst haengt die Maske bei jedem Tastendruck.
  $("fig_feld").style.display = p.feldAn ? "" : "none";
  if (p.feldAn) zeichneFeld($("c_feld"), p);
}
for (const el of document.querySelectorAll("input,select"))
  el.addEventListener("input", zeichne);
zeichne();
