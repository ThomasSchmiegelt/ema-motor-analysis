/* Die Scheibe in BEWEGUNG — Laeuferstellungen, einmal geloest.
 *
 * Wozu es dieses Modul gibt
 * -------------------------
 * Der Reiter „▶ Live-Simulation" in `ema.html` zeigte fuer den Axialfluss ein
 * STANDBILD: `loop()` kehrte im Axialzweig vor `stepPhysics`, `solveField` und
 * `draw` zurueck, und `_axialVorschau` kopierte einmal je Sekunde zwei fertige
 * Leinwaende herueber. Gemessen am 11.10.2026: sechs Stichproben ueber 15 s,
 * EIN Bild, Pixel fuer Pixel dasselbe — waehrend dieselbe Messung radial fuenf
 * verschiedene lieferte. Die Regler darueber blieben bedienbar und bewegten
 * nichts.
 *
 * Warum das nicht einfach „die Zeichnung drehen" ist
 * --------------------------------------------------
 * Ein gedrehtes Bild waere gelogen. Dreht sich der Laeufer, aendert sich die
 * Lage Magnet gegen NUT — und damit das Feld. Der Schnitt muss also je
 * Laeuferstellung neu geloest werden; `theta` verschob bisher nur den SCHNITT
 * (`rzBei`), nicht den Laeufer.
 *
 * Warum es trotzdem fluessig laeuft
 * ---------------------------------
 * Weil die Stellungen sich wiederholen. Nach einer Polteilung steht der
 * Laeufer wieder gleich zum Staender, nur mit vertauschten Polen: das Feld ist
 * dann exakt das NEGATIVE (in `pruefe.js` nachgemessen, nicht angenommen —
 * dieselbe Antiperiodik, mit der `ema_axial_em3d` seinen Ringsektor koppelt).
 * Eine volle Umdrehung kostet deshalb keine weiteren Loeserlaeufe, sondern
 * eine starre Drehung um m Perioden.
 *
 * **Und KEIN zusaetzliches Vorzeichen** — das war der erste Entwurf, und die
 * Messung hat ihn widerlegt: am festen Ort muss das Feld nach EINER Polteilung
 * kippen (dort stand ein Nordpol, jetzt steht ein Suedpol), mit dem Zusatz-
 * vorzeichen kam es unveraendert heraus (1,0149 gegen 1,0186 T statt -1,0149).
 * Der Grund ist, dass das geloeste Fenster ZWEI Polteilungen breit ist und in
 * sich schon antiperiodisch: die starre Drehung liest dann von selbst am
 * Gegenpol ab. Wer beides tut, hebt es auf.
 *
 * **Die Periode ist nicht die Polteilung.** Eine Drehung bildet den STAENDER
 * nur dann auf sich ab, wenn sie ein Vielfaches der Nutteilung ist, und den
 * Laeufer nur bei einem Vielfachen der Polteilung. Die kleinste Drehung, die
 * beides tut, ist `2*pi/ggT(2p, Q)`. Bei 2p=16/Q=48 ist das genau eine
 * Polteilung; bei einer Bruchlochwicklung ist es mehr, und wer dort die
 * Polteilung naehme, saehe einen Sprung je Periode.
 */
"use strict";

const LIVE_STELLUNGEN = 12;      // Loeserlaeufe je Periode
const LIVE_SCHEIBEN   = 3;       // Ringe fuer die Vorschau (die Seite nimmt mehr)
const LIVE_NETZ       = 52;      // Zeilen je Schnitt

function _liveGgt(a, b) { a = Math.abs(a | 0); b = Math.abs(b | 0);
                          while (b) { const t = a % b; a = b; b = t; } return a || 1; }

/* Die kleinste Drehung, nach der Laeufer UND Staender wieder gleich stehen,
 * und wie viele Polteilungen darin liegen (daraus folgt das Vorzeichen). */
function livePeriode(p) {
  const tauP = 2 * Math.PI / p.poles;
  const per = 2 * Math.PI / _liveGgt(p.poles, p.q);
  return { per, tauP, mP: Math.max(1, Math.round(per / tauP)) };
}

let _LIVE = null, _LIVE_MARKE = "";

/* Einmal rechnen, danach nur noch ablesen. `melde(k, n)` fuer den Fortschritt —
 * das dauert Sekunden, und ein stummes Fenster sieht aus wie ein Fehler.
 *
 * Die `marke` kommt von DRAUSSEN (die Seite reicht `rzMarke(p)` herein). Eine
 * eigene zu bilden hiesse, dieselbe Liste von Groessen ein zweites Mal zu
 * fuehren — und die zweite laeuft beim naechsten neuen Parameter auseinander.
 */
function liveSorgen(p, nPos, melde, marke) {
  nPos = Math.max(2, nPos || LIVE_STELLUNGEN);
  const m = JSON.stringify([marke || "", nPos, LIVE_SCHEIBEN, LIVE_NETZ]);
  if (_LIVE && _LIVE_MARKE === m) return _LIVE;
  const { per, tauP, mP } = livePeriode(p);
  const rahmen = [];
  for (let k = 0; k < nPos; k++) {
    const q = Object.assign({}, p, { rotorVersatz: k * per / nPos });
    rahmen.push(schnittRechnen(q, LIVE_SCHEIBEN, LIVE_NETZ, p.iter));
    if (melde) melde(k + 1, nPos);
  }
  // Die Farbskala wird EINMAL gesetzt und gilt fuer alle Rahmen. Je Rahmen neu
  // gewaehlt wuerde sie mit der Drehung atmen, und dann saehe eine Aenderung
  // der SKALA aus wie eine Aenderung des FELDES — in einer laufenden Anzeige
  // der schlimmste Fehler, weil ihn niemand nachmisst.
  let deckel = 0;
  for (const e of rahmen)
    for (let k = 0; k < e.nSch; k++)
      for (let a = 0; a < 120; a++)
        deckel = Math.max(deckel, Math.abs(
          _liveBz(e, k, a * 2 * Math.PI / 120, p.poles)));
  _LIVE = { rahmen, nPos, per, tauP, mP, poles: p.poles,
            ri: p.ri, ro: p.ro, welle: p.welle,
            deckel: deckel > 1e-6 ? deckel : 1 };
  _LIVE_MARKE = m;
  return _LIVE;
}

/* Welcher Rahmen, wie weit starr gedreht, welches Vorzeichen? */
function liveBei(folge, theta) {
  const { nPos, per } = folge;
  let m = Math.floor(theta / per);
  let rest = theta - m * per;
  let k = Math.round(rest / per * nPos);
  if (k >= nPos) { k = 0; m += 1; }
  return { erg: folge.rahmen[k], k, dreh: m * per };
}

/* B_z in der Spaltmitte bei EINEM Umfangswinkel und EINEM Ring — die eine
 * Ablesung, auf der Scheibenbild und Kurve beide beruhen. */
function _liveBz(erg, kRing, aRel, poles) {
  const sc = erg.scheiben[kRing], g = sc.g;
  const thW = 2 * (2 * Math.PI / poles);
  const tw = ((aRel % thW) + thW) % thW;
  let i = Math.floor((tw * sc.r) / g.dx);
  i = Math.max(1, Math.min(g.nx - 2, i));
  return sc.By[erg.jGap * g.nx + i] * sc.sf;
}

/* ---- Die Scheibe von vorn, mit dem Feld, in Bewegung ------------------- */
function zeichneLiveScheibe(cv, p, folge, theta, deckel) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.fillStyle = "#101216"; ctx.fillRect(0, 0, W, H);
  const { erg, dreh } = liveBei(folge, theta);
  const cx = W / 2, cy = H / 2, s = (Math.min(W, H) / 2 - 26) / (p.ro + 6);
  const nA = 240, nS = erg.nSch, dr = (p.ro - p.ri) / nS;
  for (let a = 0; a < nA; a++) {
    const th0 = a * 2 * Math.PI / nA, th1 = (a + 1) * 2 * Math.PI / nA;
    for (let k = 0; k < nS; k++) {
      const bz = _liveBz(erg, k, th0 - dreh, p.poles);
      const t = Math.max(-1, Math.min(1, bz / deckel)), u = Math.abs(t);
      ctx.fillStyle = t >= 0 ? `rgb(${(40+215*u)|0},${(35+40*u)|0},${(45+30*u)|0})`
                             : `rgb(${(35+30*u)|0},${(40+95*u)|0},${(50+185*u)|0})`;
      ctx.beginPath();
      ctx.arc(cx, cy, s * (p.ri + (k + 1) * dr), -th1, -th0, false);
      ctx.arc(cx, cy, s * (p.ri + k * dr), -th0, -th1, true);
      ctx.closePath(); ctx.fill();
    }
  }
  // Eine Polmarke, damit man die Drehung SIEHT und nicht nur das Muster wandern
  // laesst -- bei 16 Polen sind zwei Rahmen sonst kaum zu unterscheiden.
  ctx.strokeStyle = "#e8a33d"; ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(cx + s * p.welle * Math.cos(theta), cy - s * p.welle * Math.sin(theta));
  ctx.lineTo(cx + s * (p.ro + 4) * Math.cos(theta), cy - s * (p.ro + 4) * Math.sin(theta));
  ctx.stroke();
  ctx.fillStyle = "#5d6470";
  ctx.beginPath(); ctx.arc(cx, cy, s * p.welle, 0, 2 * Math.PI); ctx.fill();
  ctx.fillStyle = "#8a93a3"; ctx.font = "11px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`B_z in der Spaltmitte · ${nS} Ringe`, 8, 14);
  ctx.textAlign = "right";
  ctx.fillText(`rot ±${deckel.toFixed(2)} T blau`, W - 8, 14);
}

/* ---- B_z ueber dem Umfang, mit mitlaufender Marke ---------------------- */
function zeichneLiveKurve(cv, p, folge, theta, deckel) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.fillStyle = "#101216"; ctx.fillRect(0, 0, W, H);
  const { erg, dreh } = liveBei(folge, theta);
  const kR = Math.floor(erg.nSch / 2), r = erg.scheiben[kR].r;
  const pad = 26, x0 = pad, x1 = W - 8, y0 = H - 18, y1 = 16;
  const X = (f) => x0 + (x1 - x0) * f, Y = (b) => (y0 + y1) / 2 - (b / deckel) * (y0 - y1) / 2;
  ctx.strokeStyle = "#2a2f37"; ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(x0, Y(0)); ctx.lineTo(x1, Y(0)); ctx.stroke();
  ctx.strokeStyle = "#e8a33d"; ctx.lineWidth = 1.6; ctx.beginPath();
  const n = 240;
  for (let i = 0; i <= n; i++) {
    const a = i / n * 2 * Math.PI;
    const b = _liveBz(erg, kR, a - dreh, p.poles);
    const xx = X(i / n), yy = Y(b);
    i ? ctx.lineTo(xx, yy) : ctx.moveTo(xx, yy);
  }
  ctx.stroke();
  // Die Marke laeuft mit dem Laeufer -- sie ist der Grund, warum man hier
  // ueberhaupt eine Bewegung sieht: die WELLE wandert, ihre Form nicht.
  const f = ((theta % (2 * Math.PI)) + 2 * Math.PI) % (2 * Math.PI) / (2 * Math.PI);
  ctx.strokeStyle = "#8bc34a"; ctx.lineWidth = 1.4;
  ctx.beginPath(); ctx.moveTo(X(f), y1); ctx.lineTo(X(f), y0); ctx.stroke();
  ctx.fillStyle = "#8a93a3"; ctx.font = "11px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`B_z(θ) bei r = ${r.toFixed(0)} mm`, 6, 12);
  ctx.textAlign = "right";
  ctx.fillText(`0 … 360°`, W - 6, H - 5);
}

/* ---- Der abgewickelte Streifen, mit dem WANDERNDEN Laeufer -------------
 *
 * Das ist das Bild, an dem man die Drehung ueberhaupt erkennt: die Zaehne
 * stehen, die Magnete wandern. In der Draufsicht sind 16 Pole bei 22,5°
 * Periode kaum auseinanderzuhalten, hier ist es offensichtlich.
 *
 * Gezeichnet, nicht geloest — die Feldaussage steht in den beiden anderen
 * Bildern, und das sagt die Beschriftung auch.
 */
function zeichneLiveAbwicklung(cv, p, theta) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.fillStyle = "#101216"; ctx.fillRect(0, 0, W, H);
  const TAU2 = 2 * Math.PI;
  const rs = p.rs || (p.ri + p.ro) / 2;
  const tauP = TAU2 * rs / p.poles, tauS = TAU2 * rs / p.q;
  const breite = 2 * tauP, s = W / breite;
  const X = (u) => u * s;
  const hZ = Math.round(H * 0.34), hSp = Math.max(2, Math.round(H * 0.07));
  const yZ = Math.round(H * 0.08), yM = yZ + hZ + hSp, hM = Math.round(H * 0.26);

  ctx.fillStyle = "#49525f"; ctx.fillRect(0, yZ, W, hZ);          // Staenderzahn
  ctx.fillStyle = "#101216";
  for (let i = -1; (i + 0.5) * tauS < breite + tauS; i++) {       // Nuten: STEHEN
    const u = (i + 0.5) * tauS;
    ctx.fillRect(X(u - p.bnut / 2), yZ, s * p.bnut, hZ);
  }
  ctx.fillStyle = "#e8a33d"; ctx.globalAlpha = 0.22;              // Luftspalt
  ctx.fillRect(0, yZ + hZ, W, hSp); ctx.globalAlpha = 1;

  // Der Laeufer WANDERT -- derselbe Versatz, mit dem auch geloest wird.
  const vx = theta * rs;
  const M = magnetSegmente(p);
  ctx.fillStyle = "#39414c"; ctx.fillRect(0, yM, W, hM);
  for (let pol = -2; pol * tauP < breite + 2 * tauP; pol++)
    for (const sg of M.seg) {
      const u0 = (pol + sg.u0) * tauP + (vx % tauP) - tauP, w = sg.breit * tauP;
      if (u0 >= breite || u0 + w <= 0) continue;
      const my = magnetRichtung(p, pol + Math.floor(vx / tauP), sg.k, M.nU, M.hal)[1];
      ctx.fillStyle = Math.abs(my) < 0.3 ? "#8e44ad" : my > 0 ? "#c0392b" : "#2e6fb7";
      ctx.fillRect(X(Math.max(0, u0)), yM,
                   s * (Math.min(breite, u0 + w) - Math.max(0, u0)), hM);
    }
  ctx.fillStyle = "#8a93a3"; ctx.font = "10px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`abgewickelt bei r = ${rs.toFixed(0)} mm · Zähne stehen, Magnete wandern`, 6, 11);
}
