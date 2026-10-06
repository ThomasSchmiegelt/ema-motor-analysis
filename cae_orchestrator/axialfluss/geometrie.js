/* geometrie.js — die Schichtung des Stapels, EINE Quelle.
 *
 * Sie wird von drei Stellen gelesen: dem Halbschnitt, der Abwicklung und dem
 * Feldloeser. Zwei Beschreibungen derselben Geometrie waeren genau die Drift,
 * gegen die `ema_laeufer.js` im Hauptwerkzeug absichtlich duenn gehalten ist
 * ("Python schickt Zahlen, JavaScript malt").
 *
 * In einer eigenen Datei, damit sie sich OHNE Browser pruefen laesst --
 * `pruefe.js` laeuft unter node und rechnet die Konvergenz des Feldloesers
 * nach. Eine Zeichenseite, die man nur ansehen und nicht nachmessen kann, ist
 * genau das, was hier vermieden werden soll.
 */
"use strict";

function stapelLagen(p) {
  const L = [];
  const st = (seite) => ({ art: "stator", d: p.zahn + (p.statorOhneJoch ? 2 : p.jochS), seite });
  const rot = (seite) => ({ art: "rotor", seite,
                            d: p.magd + (p.rotorOhneJoch ? 3 : p.jochR) });
  // ``seite`` sagt, wo der LUFTSPALT liegt: dorthin zeigt der Magnet bzw. der
  // Laeuferzahn, das Joch liegt auf der anderen Seite.
  if (p.topo === "eser") { L.push(st("oben"), { art: "spalt", d: p.spalt }, rot("unten")); }
  else if (p.topo === "dser") { L.push(st("oben"), { art: "spalt", d: p.spalt }, rot("beide"),
                                       { art: "spalt", d: p.spalt }, st("unten")); }
  else { L.push(rot("oben"), { art: "spalt", d: p.spalt }, st("beide"),
                { art: "spalt", d: p.spalt }, rot("unten")); }
  const ges = [];
  for (let k = 0; k < p.stapel; k++) {
    if (k) ges.push({ art: "fuge", d: Math.max(4, p.spalt * 4) });
    for (const l of L) ges.push({ ...l });
  }
  return ges;
}

/* ---- Wie viele Magnete, wie viele Zaehne ---------------------------------
 *
 * Beides war bisher NICHT einstellbar, und zwar auf zwei verschiedene Weisen:
 *
 *  * Die Magnetzahl war an die Polzahl GEKETTET -- ein Magnet je Pol. Wirklich
 *    gebaut wird ein Pol aber meist aus mehreren Platten: umfangs gegen
 *    Wirbelstromverluste und weil eine grosse Platte kaum zu handhaben ist,
 *    und ueber dem Radius, weil der Polbogen nach aussen breiter wird und EINE
 *    Platte ueber Ri..Ro deshalb ein unguenstiges Seitenverhaeltnis hat.
 *    Beim Halbach-Array ist die Segmentzahl ueberhaupt der Entwurfsparameter.
 *  * Die Laeuferstabzahl war `round(0,86 * q)` -- eine Zahl ohne Pruefung, an
 *    DREI Stellen einzeln ausgeschrieben.
 *
 * Die Zahl der StaenderZAEHNE ist dagegen keine eigene Groesse: ein genuteter
 * Ring hat so viele Zaehne wie Nuten. Zwei Felder dafuer anzubieten waere eine
 * Einstellung, die es nicht gibt.
 */

/* Die Magnetsegmente EINER Polteilung, in Bruchteilen der Polteilung.
 * Der Aufrufer skaliert auf mm (Abwicklung, Feld) oder auf Winkel (Draufsicht).
 *
 * Die Fuge zwischen zwei Segmenten ist eine RADIALE Linie, also ein fester
 * WINKEL -- so sind Ringsektormagnete gefertigt. Ihre mm-Angabe gilt am
 * mittleren Radius; aussen ist sie weiter, innen enger. Als Bruchteil der
 * Polteilung ist sie damit radiusUNABHAENGIG, und genau deshalb kann diese
 * Funktion in Bruchteilen rechnen und von allen drei Ansichten geteilt werden.
 */
function magnetSegmente(p) {
  const hal = p.laeufer === "halbach";
  const nU = Math.max(1, Math.min(16, Math.round(p.magSegU || 1)));
  // Das Halbach-Array deckt die Polteilung VOLL ab -- das ist sein Zweck; eine
  // Polbedeckung < 1 waere dort ein Widerspruch und wird nicht gezeichnet.
  const bed = hal ? 1 : Math.max(0, Math.min(1, p.alpha));
  const rm = (p.ri + p.ro) / 2;
  // Ein fehlender Wert ist KEINE Fuge. Ohne diese Klammer machte ein NaN das
  // ganze Magnetband zu Luft, und das Feld kam stumm als 0 heraus.
  const fmm = Number.isFinite(p.magFuge) ? Math.max(0, p.magFuge) : 0;
  const fug = rm > 0 ? (fmm * p.poles) / (2 * Math.PI * rm) : 0;
  // Halbach liegt periodisch, hat also nU Fugen je Polteilung. Bei Bedeckung
  // unter 1 sind es nU-1 -- die Luecke zum Nachbarpol ist keine Fuge.
  const nFug = hal ? nU : nU - 1;
  const breit = (bed - nFug * fug) / nU;
  const seg = [];
  const u0 = (1 - bed) / 2;
  for (let k = 0; k < nU; k++) {
    // Halbach: das Segment k sitzt auf k/nU, also ueberspannt das erste die
    // POLGRENZE (dort ist die Magnetisierung tangential) und das mittlere steht
    // auf der POLACHSE (dort normal) -- die klassische Anordnung.
    const mitte = hal ? k / nU : u0 + k * (breit + fug) + breit / 2;
    seg.push({ k, mitte, breit, u0: mitte - breit / 2, u1: mitte + breit / 2 });
  }
  return { seg, nU, bed, hal, fug, breit, eng: breit <= 0 };
}

/* Die Magnetringe ueber dem Radius. Sie sind im abgewickelten Schnitt NICHT
 * sichtbar: eine radiale Fuge liegt auf konstantem Radius, der Schnitt steht
 * bei EINEM Radius. Sichtbar werden sie in der Draufsicht und im r-z-Schnitt.
 */
function magnetRinge(p) {
  const nR = Math.max(1, Math.min(8, Math.round(p.magSegR || 1)));
  const fmm = Number.isFinite(p.magFuge) ? Math.max(0, p.magFuge) : 0;
  const h = (p.ro - p.ri - (nR - 1) * fmm) / nR;
  const rg = [];
  for (let k = 0; k < nR; k++) {
    const r0 = p.ri + k * (h + fmm);
    rg.push({ k, r0, r1: r0 + h, h });
  }
  return { rg, nR, h, fuge: fmm, eng: h <= 0 };
}

/* Magnetisierung eines Segments als Einheitsvektor (Mx umfangs, My axial).
 * ``pol`` zaehlt ueber den Umfang, ``k`` innerhalb der Polteilung.
 *
 * **Berichtigt am 06.10.2026.** Hier stand `[1, 0, -1, 0][idx % 4]` bei vier
 * Segmenten JE POLTEILUNG -- also eine volle Drehung der Magnetisierung je
 * Polteilung. Eine Wellenlaenge sind aber ZWEI Polteilungen, das Array trug
 * damit die doppelte Polzahl. Siehe BEFUNDE.md.
 */
function magnetRichtung(p, pol, k, nU, hal) {
  if (!hal) return [0, pol % 2 ? -1 : 1];
  const ph = Math.PI * (pol + k / nU - 0.5);
  return [Math.sin(ph), Math.cos(ph)];
}

/* Zahl der Laeuferstaebe bzw. -zaehne des Kaefiglaeufers.
 *
 * **Spiegel von `ema_asm.stabzahl`** -- zeichengetreu dieselbe Auswahlregel:
 * rund 0,85 x Staendernutzahl, aber nicht gleich ihr, nicht um 0/+-p/+-2p/+-3p
 * daneben (synchrone Oberwellenmomente, Kleben beim Anlauf) und kein
 * Vielfaches der Polzahl. `pruefe.js` haelt die beiden Fassungen gegeneinander,
 * wie `test_mobil.py` es fuer die Halbpol-Umrechnung tut -- zwei Regeln
 * nebeneinander waeren zwei verschiedene Laeufer, und beide saehen richtig aus.
 */
function stabzahl(p) {
  if (p.qr && p.qr > 0) return Math.max(6, Math.round(p.qr));
  const nS = Math.round(p.q), pp = Math.max(1, Math.round(p.poles / 2));
  const verboten = new Set([0, pp, 2 * pp, 3 * pp]);
  const ziel = Math.max(6, Math.round(0.85 * nS));
  for (let d = 0; d < nS; d++)
    for (const kand of [ziel - d, ziel + d]) {
      if (kand < 6 || kand === nS) continue;
      if (verboten.has(Math.abs(kand - nS))) continue;
      if (kand % (2 * pp) === 0) continue;
      return kand;
    }
  return Math.max(6, nS - 1);
}

/* Wogegen eine von Hand gesetzte Stabzahl verstoesst -- als Satz, nicht als
 * Nein: die Zahl wird gezeichnet und gerechnet, der Befund steht daneben. */
function stabzahlBefund(p) {
  const nR = stabzahl(p), nS = Math.round(p.q), pp = Math.max(1, Math.round(p.poles / 2));
  const d = Math.abs(nR - nS), warn = [];
  if (nR === nS) warn.push("gleich der Ständernutzahl");
  else if ([0, pp, 2 * pp, 3 * pp].includes(d))
    warn.push(`um ${d} = ${d === pp ? "p" : d === 2 * pp ? "2p" : d === 3 * pp ? "3p" : "0"} daneben`);
  if (nR % (2 * pp) === 0) warn.push("Vielfaches der Polzahl");
  return { nR, gesetzt: !!(p.qr && p.qr > 0), warn };
}

if (typeof module !== "undefined" && module.exports)
  module.exports = { stapelLagen, magnetSegmente, magnetRinge, magnetRichtung,
                     stabzahl, stabzahlBefund };
