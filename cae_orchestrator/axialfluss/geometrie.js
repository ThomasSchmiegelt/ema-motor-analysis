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
