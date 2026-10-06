/* pruefe.js — den Feldloeser OHNE Browser nachmessen.
 *
 *     node pruefe.js
 *
 * Eine Zeichenseite, die man nur ansehen kann, belegt nichts. Hier wird
 * gemessen, was sich messen laesst: ob der Loeser konvergiert, ob er linear
 * ist, ob die Flussbilanz schliesst und ob das Ergebnis am Gitter haengt.
 */
"use strict";
const fs = require("fs"), vm = require("vm");
const ctx = { console, performance: { now: () => Date.now() }, Math, Float64Array,
              Uint8Array, document: null };
vm.createContext(ctx);
for (const f of ["geometrie.js", "feld.js"])
  vm.runInContext(fs.readFileSync(__dirname + "/" + f, "utf8"), ctx, f);

const BASIS = {
  topo: "esdr", laeufer: "sektor", stapel: 1,
  ro: 130, ri: 75.01, lam: 0.577, poles: 16, q: 48, bnut: 6,
  spalt: 1, zahn: 25, jochS: 12, jochR: 13, magd: 6, alpha: 0.85,
  welle: 30, wkI: 14, rs: 102.5, last: 0,
  rotorOhneJoch: false, statorOhneJoch: true, nSpalte: 2,
};
const P = (o) => ({ ...BASIS, ...o });

let ok = 0, fehl = 0;
const pr = (b, t) => { b ? ok++ : fehl++; console.log(`  ${b ? "✓" : "✗"} ${t}`); };

function lauf(p, ny, iter) {
  const g0 = ctx.feldGitter(p, 8, 8);
  const nx = Math.round(ny * (g0.breite / g0.hGes));
  const g = ctx.feldGitter(p, nx, ny);
  const { A, relRest, schritte } = ctx.loeseCG(g, iter, 1e-11);
  const rest = relRest;
  const { Bx, By } = ctx.feldAus(g, A);
  const e = ctx.eichung(p, g, By);
  let amax = 0; for (const v of A) amax = Math.max(amax, Math.abs(v));
  // Grundwelle der Normalkomponente in der Spaltmitte
  const j = e.jGap, N = nx; let re = 0, im = 0;
  for (let i = 0; i < N; i++) {
    const b = By[j * N + i] * e.sf, th = 2 * Math.PI * i / N;
    re += b * Math.cos(th); im += b * Math.sin(th);
  }
  const b1 = 2 * Math.hypot(re, im) / N;
  return { g, A, Bx, By, e, rest, amax, b1, nx, ny: g.ny, schritte, relRest: rest };
}

console.log("\n— 1. Konvergiert der CG? —");
for (const it of [60, 150, 400, 1200]) {
  const r = lauf(P(), 100, it);
  console.log(`   ${String(it).padStart(5)} Schritte (${String(r.schritte).padStart(4)} gebraucht): ` +
    `rel. Rest ${r.relRest.toExponential(2)}  B1 ${r.b1.toFixed(5)} T`);
}
pr(lauf(P(), 100, 1200).relRest < 1e-9, "erreicht rel. Rest < 1e-9");

console.log("\n— 3. Linearität (ein linearer Löser MUSS sie treffen) —");
const g1 = ctx.feldGitter(P(), 120, 100);
const a1 = ctx.loeseCG(g1, 3000, 1e-12).A;
const g2 = ctx.feldGitter(P(), 120, 100);
for (let k = 0; k < g2.J.length; k++) g2.J[k] *= 2;
const a2 = ctx.loeseCG(g2, 3000, 1e-12).A;
let m1 = 0, m2 = 0;
for (let k = 0; k < a1.length; k++) { m1 = Math.max(m1, Math.abs(a1[k])); m2 = Math.max(m2, Math.abs(a2[k])); }
pr(Math.abs(m2 / m1 - 2) < 1e-6, `J → 2J gibt ${(m2 / m1).toFixed(6)}× A (soll 2,000000)`);

console.log("\n— 4. Hängt B1 am Gitter? —");
const reihe = [];
for (const ny of [50, 70, 100, 140, 190]) {
  const r = lauf(P(), ny, 3000);
  reihe.push(r); console.log(`   ${r.nx}×${r.ny}: B1 ${r.b1.toFixed(5)} T  relRest ${r.relRest.toExponential(2)}`);
}
const letzte = reihe[reihe.length - 1].b1;
const abw = reihe.map((r) => Math.abs(r.b1 - letzte) / letzte * 100);
console.log("   Abweichung zum feinsten: " + abw.map((a) => a.toFixed(2) + " %").join("  "));
pr(abw.every((a, i) => i === 0 || a <= abw[i - 1] + 1e-9),
   "B1 konvergiert MONOTON mit dem Gitter — das tut es nur, weil die y-Linien " +
   "auf den Schichtgrenzen liegen (mit gleichmäßigem dy streute es um ±6 %)");

console.log("\n— 5. Flussbilanz: geht der Fluss axial durch den Ständer? —");
{
  const r = lauf(P(), 140, 3000);
  const { g, By, e } = r, N = r.nx;
  const flussJePol = (j) => {
    let s = 0; const bis = Math.round(g.tauP / g.dx);
    for (let i = 0; i < bis; i++) s += By[j * N + i] * e.sf * g.dx;
    return s;
  };
  const yMitte = (b) => { const ym = (b.y0 + b.y1) / 2; let j = 1, d = Infinity;
    for (let q = 1; q < g.ny - 1; q++) { const e2 = Math.abs(g.yc[q] - ym);
      if (e2 < d) { d = e2; j = q; } } return j; };
  for (const b of g.bnd)
    console.log(`   ${(b.art + (b.seite ? "/" + b.seite : "")).padEnd(16)}` +
      ` y=${((b.y0 + b.y1) / 2).toFixed(1).padStart(5)} mm   Φ/Pol ${flussJePol(yMitte(b)).toExponential(3)}`);
  const sp = g.bnd.filter((b) => b.art === "spalt").map((b) => flussJePol(yMitte(b)));
  const st = g.bnd.filter((b) => b.art === "stator").map((b) => flussJePol(yMitte(b)));
  if (sp.length && st.length) {
    const v = Math.abs(st[0] / sp[0]);
    pr(v > 0.7, `Ständermitte führt ${(v * 100).toFixed(0)} % des Spaltflusses ` +
                `— der Fluss geht axial DURCH (Rest streut über die Nuten)`);
  }
  if (sp.length === 2)
    pr(Math.abs(sp[0] / sp[1] - 1) < 0.08,
       `beide Spalte führen denselben Fluss (${(sp[0] / sp[1]).toFixed(3)}) — symmetrisch`);
}

console.log(`\n${ok} bestanden, ${fehl} fehlgeschlagen`);
process.exit(fehl ? 1 : 0);
