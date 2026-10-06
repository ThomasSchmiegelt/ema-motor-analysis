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
    magSegU: +$("magSegU").value, magSegR: +$("magSegR").value,
    magFuge: +$("magFuge").value, qr: +$("qr").value,
    spalt: +$("spalt").value, zahn: +$("zahn").value,
    jochS: +$("jochS").value, jochR: +$("jochR").value,
    magd: +$("magd").value, alpha: +$("alpha").value,
    welle: +$("welle").value / 2, wkI: +$("wkI").value,
    sektor: +$("sektor").value * Math.PI / 180,
    fluss: $("fluss").checked, masse: $("masse").checked,
    last: +$("last").value, netz: +$("netz").value, iter: +$("iter").value,
    feldAn: $("feldAn").checked,
    beta: +$("beta").value * Math.PI / 180,
    rzAn: $("rzAn").checked, rzN: +$("rzN").value,
    theta: +$("theta").value * Math.PI / 180,
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
  const MZ = magnetSegmente(p), RZ = magnetRinge(p);
  const laeuferZahl =
      p.laeufer === "kaefig"   ? `${stabzahl(p)} Läuferzähne`
    : p.laeufer === "eisenlos" ? `${p.poles * 9} Leiterbahnen`
    : `${p.poles * MZ.nU * RZ.nR} Magnete (${p.poles}×${MZ.nU}×${RZ.nR})`;
  ctx.fillText(`Ständer: ${p.q} Nuten = ${p.q} Zähne · 2p = ${p.poles} · ` +
               `Läufer: ${laeuferZahl}`, 10, 18);
}

function laeuferFlaeche(ctx, cx, cy, s, p, a0, a1) {
  const imSektor = (mid, rand) => {
    const d = ((mid - (a0 + a1) / 2 + Math.PI * 3) % TAU) - Math.PI;
    return Math.abs(d) <= (a1 - a0) / 2 + rand;
  };
  if (p.laeufer === "kaefig") {
    const qr = stabzahl(p);
    ctx.fillStyle = "#49525f";
    ring(ctx, cx, cy, s, p.ri, p.ro, a0, a1); ctx.fill();
    for (let i = 0; i < qr; i++) {
      const th = i * TAU / qr;
      if (!imSektor(th, .05)) continue;
      if (nutPfad(ctx, cx, cy, s, th, p.bnut * .8, p.ri, p.ro)) {
        ctx.fillStyle = "#9aa4b0"; ctx.fill();
      }
    }
    ctx.fillStyle = "#9aa4b0";
    ring(ctx, cx, cy, s, p.ro, p.ro + 4, a0, a1); ctx.fill();
    ring(ctx, cx, cy, s, p.ri - 4, p.ri, a0, a1); ctx.fill();
    ctx.fillStyle = "#dfe4ec"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    ctx.fillText(`${qr} Läuferzähne + Käfig`,
                 cx + s * (p.ro * .7) * Math.cos((a0 + a1) / 2),
                 cy - s * (p.ro * .7) * Math.sin((a0 + a1) / 2));
  } else if (p.laeufer === "eisenlos") {
    // Scheibenanker: KEIN Eisen, nur radiale Leiterbahnen.
    const nl = p.poles * 9;
    ctx.strokeStyle = "#c87f3a"; ctx.lineWidth = Math.max(1, s * p.bnut * .35);
    for (let i = 0; i < nl; i++) {
      const th = i * TAU / nl;
      if (!imSektor(th, 0)) continue;
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
    // Sektormagnete bzw. Halbach: die Belegung kommt aus `magnetSegmente`
    // (umfangs) und `magnetRinge` (radial) -- EINE Quelle fuer Draufsicht,
    // Abwicklung und Feldloeser.
    const M = magnetSegmente(p), R = magnetRinge(p);
    const wPol = TAU / p.poles;
    if (!M.hal) {
      ctx.fillStyle = "#39414c"; ring(ctx, cx, cy, s, p.ri, p.ro, a0, a1); ctx.fill();
    }
    if (M.eng || R.eng) {                       // Fuge frisst die Platte auf
      ctx.fillStyle = "#e06c5a"; ctx.font = "12px system-ui"; ctx.textAlign = "center";
      ctx.fillText("Fuge breiter als die Platte", cx, cy - s * (p.ri + p.ro) / 2);
      return;
    }
    for (let pol = 0; pol < p.poles; pol++)
      for (const sg of M.seg) {
        const th0 = (pol + sg.u0) * wPol, th1 = (pol + sg.u1) * wPol;
        if (!imSektor((th0 + th1) / 2, wPol)) continue;
        // Die Farbe folgt der AXIALEN Komponente der Magnetisierung, nicht
        // einem Zaehlindex -- dieselbe Regel wie `ema_em3d._magnet_klasse`:
        // bei Halbach kippt der Index dort, wo die Physik nicht kippt.
        const [, my] = magnetRichtung(p, pol, sg.k, M.nU, M.hal);
        ctx.fillStyle = Math.abs(my) < 0.3 ? "#8e44ad"
                      : my > 0 ? "#c0392b" : "#2e6fb7";
        for (const rg of R.rg) {
          ring(ctx, cx, cy, s, rg.r0, rg.r1, th0, th1);
          ctx.save(); ctx.clip();
          ring(ctx, cx, cy, s, rg.r0, rg.r1, a0, a1); ctx.fill(); ctx.restore();
        }
      }
    ctx.fillStyle = "#dfe4ec"; ctx.font = "11px system-ui"; ctx.textAlign = "center";
    const n = p.poles * M.nU * R.nR;
    ctx.fillText((M.hal ? "Halbach — kein Rotoreisen · " : "Sektormagnete · ") +
                 `${n} Platten`,
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
        ctx.fillStyle = "#dfe4ec"; ctx.font = "10px system-ui"; ctx.textAlign = "center";
        ctx.save(); ctx.translate(x_ + dm / 2, Y((p.ri + p.ro) / 2)); ctx.rotate(-Math.PI / 2);
        ctx.fillText(`${stabzahl(p)} Stäbe`, 0, 3); ctx.restore();
        ctx.fillStyle = "#9aa4b0";
        ctx.fillRect(x_, Y(p.ro + 4), dm, s * 4);     // Kurzschlussring aussen
        ctx.fillRect(x_, Y(p.ri), dm, s * 4);         // und innen
      } else if (p.laeufer === "eisenlos") {
        ctx.fillStyle = "#c87f3a"; ctx.fillRect(x_, Y(p.ro), dm * .5, s * (p.ro - p.ri));
      } else {
        // EIN Pol: der Schnitt steht an einer Winkellage, der Polwechsel liegt
        // in theta. Ueber dem Radius die Polung zu wechseln waere eine Maschine
        // mit Polen in RADIALER Richtung -- die es nicht gibt.
        // Was ueber dem Radius WECHSELT, ist die PLATTE: hier werden die
        // radialen Fugen sichtbar, die der abgewickelte Schnitt nicht zeigt.
        const R = magnetRinge(p);
        ctx.fillStyle = "#c0392b";
        for (const rg of R.rg)
          if (rg.h > 0) ctx.fillRect(x_, Y(rg.r1), dm, s * rg.h);
        ctx.fillStyle = "#dfe4ec"; ctx.font = "10px system-ui"; ctx.textAlign = "center";
        ctx.save(); ctx.translate(x_ + dm / 2, Y((p.ri + p.ro) / 2)); ctx.rotate(-Math.PI / 2);
        ctx.fillText(R.nR > 1 ? `N · ${R.nR} Ringe` : "N", 0, 3); ctx.restore();
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
        const qr = stabzahl(p), tauR = TAU * p.rs / qr;
        ctx.fillStyle = "#49525f"; ctx.fillRect(X(0), mTop, s * breite, dm);
        ctx.fillStyle = "#9aa4b0";
        for (let i = 0; (i + .5) * tauR < breite; i++)
          ctx.fillRect(X((i + .5) * tauR - p.bnut * .4), mTop + dm * .1, s * p.bnut * .8, dm * .8);
      } else if (p.laeufer === "eisenlos") {
        ctx.fillStyle = "#c87f3a";
        for (let i = 0; i * tauS * .5 < breite; i++)
          ctx.fillRect(X(i * tauS * .5), mTop, Math.max(1, s * p.bnut * .3), dm);
      } else {
        // Die radiale Segmentierung ist hier UNSICHTBAR, und das ist richtig:
        // eine radiale Fuge liegt auf konstantem Radius, dieser Schnitt steht
        // bei EINEM Radius. Sichtbar wird sie in Draufsicht und r-z-Schnitt.
        const M = magnetSegmente(p);
        for (let pol = 0; pol * tauP < breite + tauP; pol++)
          for (const sg of M.seg) {
            const u0 = (pol + sg.u0) * tauP, w = sg.breit * tauP;
            if (u0 >= breite || u0 + w <= 0) continue;
            const [, my] = magnetRichtung(p, pol, sg.k, M.nU, M.hal);
            ctx.fillStyle = Math.abs(my) < 0.3 ? "#8e44ad"
                          : my > 0 ? "#c0392b" : "#2e6fb7";
            const a = Math.max(0, u0), b = Math.min(breite, u0 + w);
            ctx.fillRect(X(a), mTop, s * (b - a), dm);
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

/* ---- Stueckzahlen -------------------------------------------------------
 * Wie VIELE Magnete, wie viele Zaehne -- und was die Stueckelung kostet.
 * Sie rechnet nichts, was eine Auslegung waere: die Plattengroesse folgt
 * unmittelbar aus der Zeichnung, und die Stabzahlregel kommt aus
 * `ema_asm.stabzahl` (gespiegelt in `geometrie.js`, von `pruefe.js` gegen die
 * Python-Fassung gehalten).
 */
function stueckzahlen(p) {
  const bad = (c, t) => c ? `<span class="bad">${t}</span>` : t;
  const warn = (c, t) => c ? `<span class="warn">${t}</span>` : t;
  const r = [["Ständerzähne", `${p.q} — so viele wie Nuten, das ist keine zweite Größe`]];

  if (p.laeufer === "kaefig") {
    const b = stabzahlBefund(p);
    r.push(["Läuferzähne / Stäbe",
      `<b>${b.nR}</b> ` + (b.gesetzt ? "(gesetzt)" : "(abgeleitet: ≈0,85·Q, Auswahlregel)") +
      (b.warn.length
        ? ` — <span class="warn">${b.warn.join(", ")}</span>: synchrone ` +
          `Oberwellenmomente, Kleben beim Anlauf`
        : " — besteht die Auswahlregel ✓")]);
    r.push(["Läufernutteilung bei r_s",
      `${(2 * Math.PI * p.rs / b.nR).toFixed(2)} mm (Ständer ${(2 * Math.PI * p.rs / p.q).toFixed(2)} mm)`]);
    return r;
  }
  if (p.laeufer === "eisenlos") {
    r.push(["Leiterbahnen im Läufer", `${p.poles * 9} — gezeichnet, nicht ausgelegt`]);
    return r;
  }

  const M = magnetSegmente(p), R = magnetRinge(p);
  const n = p.poles * M.nU * R.nR;
  const bSeg = M.breit * 2 * Math.PI * ((p.ri + p.ro) / 2) / p.poles;  // mm am mittleren Radius
  r.push(["Magnete", `<b>${n}</b> = ${p.poles} Pole × ${M.nU} umfangs × ${R.nR} radial` +
    (M.hal ? " — beim Halbach ist das der Entwurfsparameter" : "")]);
  r.push(["Platte (mittlerer Radius)",
    bad(M.eng || R.eng,
        `${bSeg.toFixed(1)} × ${R.h.toFixed(1)} mm × ${p.magd} mm` +
        (M.eng || R.eng ? " — Fuge breiter als die Platte" : ""))]);
  if (M.nU > 1 || R.nR > 1) {
    // Was die Stueckelung an Magnetflaeche KOSTET -- die Fugen sind Luft.
    const belegt = M.nU * M.breit * R.nR * R.h;
    const voll = M.bed * (p.ro - p.ri);
    r.push(["Fugenverlust an Magnetfläche",
      warn(belegt < voll * 0.9,
        `${((1 - belegt / Math.max(voll, 1e-9)) * 100).toFixed(1)} % ` +
        `(${p.magFuge} mm Fuge, ${M.nU - (M.hal ? 0 : 1)}× umfangs + ${R.nR - 1}× radial)`)]);
  }
  if (M.hal)
    r.push(["Halbach-Wellenlänge",
      `${(2 * M.nU)} Segmente = 2 Polteilungen — die Magnetisierung dreht ` +
      `${(180 / M.nU).toFixed(0)}° je Segment`]);
  r.push(["radiale Fugen im abgewickelten Schnitt",
    R.nR > 1 ? "<b>nicht sichtbar</b> — sie liegen auf konstantem Radius, " +
               "der Schnitt steht bei einem Radius"
             : "keine"]);
  return r;
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
    ...stueckzahlen(p),
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

/* ---- Der Schnitt durch die Achse ---------------------------------------
 *
 * Er wird GEMERKT und nicht bei jedem Tastendruck neu gerechnet. Was ihn
 * ungueltig macht, ist alles ausser dem Schnittwinkel: der ist reines Ablesen
 * (s. Modulkopf von `schnitt.js`). Dieselbe Trennung wie im Hauptwerkzeug
 * zwischen einem neuen `mu` — neue Faktorisierung — und einem weiteren
 * Betriebspunkt auf derselben.
 */
let RZ = null, RZ_MARKE = "", UMLAUF = 0, RZ_TIMER = 0;

function rzMarke(p) {
  return JSON.stringify([p.topo, p.laeufer, p.stapel, p.ro, p.ri, p.poles, p.q,
    p.bnut, p.spalt, p.zahn, p.jochS, p.jochR, p.magd, p.alpha, p.welle,
    p.magSegU, p.magSegR, p.magFuge, p.qr, p.last, p.beta, p.rzN, p.netz, p.iter]);
}

/* Ein Scheibenlauf kostet GEMESSEN 0,6 s im Leerlauf und 2,3 s unter Last
 * (dort zwei Loesungen je Scheibe, s. `loeseFeld`). An `input` gehaengt waere
 * das ein Lauf je Tastendruck. Also erst, wenn die Eingabe steht -- und bis
 * dahin sagt die Flaeche, dass sie rechnet, statt ein veraltetes Feld zu
 * zeigen, das zu anderen Zahlen gehoert.
 */
function rzAnstossen(p) {
  if (RZ && RZ_MARKE === rzMarke(p)) { rzZeichnen(p, RZ); return; }
  clearTimeout(RZ_TIMER);
  rzWartenZeigen();
  RZ_TIMER = setTimeout(() => {
    const q = P();
    if (!q.rzAn) return;
    rzZeichnen(q, rzSorgen(q));
  }, 420);
}

function rzWartenZeigen() {
  for (const id of ["c_rz", "c_scheibe", "c_zahn"]) {
    const cv = $(id), ctx = cv.getContext("2d");
    ctx.fillStyle = "#101216"; ctx.fillRect(0, 0, cv.width, cv.height);
    ctx.fillStyle = "#8a93a3"; ctx.font = "15px system-ui"; ctx.textAlign = "center";
    ctx.fillText("rechnet die Scheiben …", cv.width / 2, cv.height / 2);
  }
}

function rzSorgen(p) {
  const m = rzMarke(p);
  if (RZ && RZ_MARKE === m) return RZ;
  RZ = schnittRechnen(p, p.rzN, Math.max(40, Math.min(160, p.netz)), p.iter);
  RZ_MARKE = m;
  return RZ;
}

/* Was trifft der Schnitt? Beides sind RADIALE Linien — Nutflanke wie
 * Polgrenze —, ihre Winkel haengen also nicht vom Radius ab, und derselbe
 * Schnitt trifft bei Ri dieselbe Stelle im Pol wie bei Ro. Das ist keine
 * Nebensaechlichkeit: bei einer Radialflussmaschine waere es anders. */
function schnittLage(p, theta) {
  const thP = 2 * Math.PI / p.poles, thS = 2 * Math.PI / p.q;
  const fP = ((theta % thP) + thP) % thP / thP;
  const fS = ((theta % thS) + thS) % thS / thS;
  const dS = Math.min(fS, 1 - fS);
  const wo = dS < 0.12 ? "<b>Zahnmitte</b>"
           : Math.abs(fS - 0.5) < 0.12 ? "<b>Nutmitte</b>" : "Zahnflanke";
  const imPol = Math.abs(fP - 0.5) < 0.08 ? "Polmitte"
              : Math.min(fP, 1 - fP) < 0.08 ? "Polgrenze"
              : `${(fP * 100).toFixed(0)} % der Polteilung`;
  return `${wo} · ${imPol} — Nut- und Polgrenze sind beide RADIAL, der Schnitt ` +
         `trifft bei Ri dieselbe Stelle wie bei Ro.`;
}

function rzZeichnen(p, erg) {
  const deckel = erg.eich.geeicht ? B_KNIE
    : Math.max(...Array.from(rzBei(erg, p.theta).Bm)) || 1e-9;
  zeichneSchnittRZ($("c_rz"), p, erg, p.theta, deckel);
  zeichneSpaltScheibe($("c_scheibe"), p, erg, p.theta, deckel * 0.55);
  const v = zeichneZahnKurve($("c_zahn"), p, erg);
  $("th_v").textContent = (p.theta * 180 / Math.PI).toFixed(1);
  $("th_hint").innerHTML = schnittLage(p, p.theta);
  rzTabelle(p, erg, v);
}

/* Die Zeilen, die der Achsschnitt BEITRAEGT -- und die eine, die seine
 * Naeherung beziffert statt sie nur zu nennen. */
function rzTabelle(p, erg, v) {
  const rk = radialeKopplung(erg, p);
  const i = v.length - 1;
  const bad = (c, t) => c ? `<span class="bad">${t}</span>` : t;
  const r = [
    ["B_Zahn innen → außen (gemessen)",
      `${v[0].b_zahn.toFixed(3)} → ${v[i].b_zahn.toFixed(3)} T ` +
      `(×${(v[0].b_zahn / Math.max(v[i].b_zahn, 1e-9)).toFixed(2)}) — ` +
      `das ist die Signatur der parallelflankigen Nut` +
      // Oberhalb des Knies rechnet ein LINEARER Loeser nicht mehr richtig: in
      // Wirklichkeit saettigt das Eisen und schiebt den Fluss zur Seite. Das
      // VERHAELTNIS innen/aussen bleibt die Aussage, die Hoehe nicht.
      (v[0].b_zahn > B_KNIE
        ? `<br><span class="bad">über dem Sättigungsknie (${B_KNIE} T) — ` +
          `dieser Löser ist linear (µr = 500 ohne B-H-Kurve), die HÖHE ist ` +
          `dort nicht belastbar, das Verhältnis innen/außen schon</span>` : "")],
    ["… gegen die Geometrie B_Spalt·τs/(τs−b)",
      `${(v[0].b_zahn / v[0].b_zahn_geo * 100).toFixed(0)} % innen, ` +
      `${(v[i].b_zahn / v[i].b_zahn_geo * 100).toFixed(0)} % außen — ` +
      `der Rest streut über die Nut statt durch den Zahn`],
    ["B_Spalt über dem Radius",
      `${(rk.spanne * 100).toFixed(1)} % Spanne — der Spaltleitwert hängt nicht ` +
      `am Radius, die Zahnänderung kommt allein aus der Geometrie`],
    ["Tragfähigkeit der Scheiben-Näherung",
      bad(rk.jeSpalt > 0.05,
        `${(rk.jeSpalt * 100).toFixed(3)} % Feldänderung je Luftspaltlänge. ` +
        `∂/∂r ist fallengelassen; vertretbar, solange das klein gegen die ` +
        `axiale Änderung ist`)],
    ["Kosten", `${erg.nSch} Löserläufe für die Erregung · jeder weitere ` +
      `Schnittwinkel kostet nichts`],
  ];
  $("tab").insertAdjacentHTML("beforeend",
    r.map(([a, b]) => `<tr><td>${a}</td><td>${b}</td></tr>`).join(""));
}

/* ---- Anstoss ------------------------------------------------------------ */
function zeichne() {
  const p = P();
  $("topo_hint").textContent = TOPO_TEXT[p.topo];
  $("lf_hint").textContent = LF_TEXT[p.laeufer];
  const MH = magnetSegmente(p), RH = magnetRinge(p);
  $("mag_hint").innerHTML = p.laeufer === "kaefig"
    ? "Der Käfigläufer hat keine Magnete — hier wirkt nur die Stabzahl darunter."
    : p.laeufer === "eisenlos"
    ? "Beim Scheibenanker trägt der STÄNDER die Magnete; die Segmentierung wirkt dort."
    : `<b>${p.poles * MH.nU * RH.nR} Magnete</b> = ${p.poles} × ${MH.nU} × ${RH.nR}. ` +
      (MH.hal ? "Beim Halbach dreht die Magnetisierung " +
                `${(180 / MH.nU).toFixed(0)}° je Segment (Wellenlänge = 2 Polteilungen). `
              : "Umfangs gegen Wirbelstromverluste, radial weil der Polbogen nach außen breiter wird. ") +
      "Die Fuge ist eine radiale Linie, also ein fester Winkel — ihre mm-Angabe gilt am mittleren Radius.";
  const QB = stabzahlBefund(p);
  $("qr_hint").innerHTML = p.laeufer !== "kaefig"
    ? "wirkt nur beim Käfigläufer"
    : `<b>${QB.nR}</b> ${QB.gesetzt ? "gesetzt" : "abgeleitet"} — ` +
      (QB.warn.length ? `<span class="warn">${QB.warn.join(", ")}</span>`
                      : "besteht die Auswahlregel") +
      ". 0 = ableiten (≈0,85·Q, wie <code>ema_asm.stabzahl</code>).";
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
  for (const id of ["fig_rz", "fig_scheibe", "fig_zahn"])
    $(id).style.display = p.rzAn ? "" : "none";
  if (p.rzAn) rzAnstossen(p);
  else clearTimeout(RZ_TIMER);
}

/* Der Schnittwinkel loest KEINEN neuen Lauf aus -- sonst waere die
 * Eigenschaft, um derentwegen der Mehrschnitt so gebaut ist, am Regler nicht
 * zu merken. */
function nurWinkel() {
  const p = P();
  if (!p.rzAn || !RZ || RZ_MARKE !== rzMarke(p)) { zeichne(); return; }
  rzZeichnen(p, RZ);
}

for (const el of document.querySelectorAll("input,select"))
  if (el.id !== "theta") el.addEventListener("input", zeichne);
$("theta").addEventListener("input", nurWinkel);

$("btn_best").addEventListener("click", () => {
  // Den staerksten Schnitt SUCHEN statt ihn zu raten: 360 Ablesungen auf den
  // schon geloesten Scheiben, also einen Wimpernschlag.
  if (!$("rzAn").checked) $("rzAn").checked = true;
  clearTimeout(RZ_TIMER);
  const erg = rzSorgen(P());      // ausdruecklicher Zuruf: sofort, nicht warten
  let best = 0, bw = -1;
  for (let a = 0; a < 720; a++) {
    const th = a * Math.PI / 360, f = rzBei(erg, th);
    let m = 0;
    for (let k = 0; k < f.nS; k++) m = Math.max(m, Math.abs(f.Bz[k * f.ny + erg.jGap]));
    if (m > bw) { bw = m; best = th; }
  }
  $("theta").value = (best * 180 / Math.PI).toFixed(1);
  zeichne();
});

$("btn_um").addEventListener("click", () => {
  if (UMLAUF) { cancelAnimationFrame(UMLAUF); UMLAUF = 0; $("btn_um").textContent = "▶ 360°"; return; }
  if (!$("rzAn").checked) { $("rzAn").checked = true; zeichne(); }
  $("btn_um").textContent = "⏸ halt";
  const t0 = performance.now(), th0 = +$("theta").value;
  const takt = () => {
    const th = (th0 + (performance.now() - t0) / 24) % 360;
    $("theta").value = th.toFixed(1);
    nurWinkel();
    UMLAUF = requestAnimationFrame(takt);
  };
  UMLAUF = requestAnimationFrame(takt);
});

zeichne();
