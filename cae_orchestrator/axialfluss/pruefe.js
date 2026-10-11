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
              Uint8Array, Number, Set, document: null };
vm.createContext(ctx);
for (const f of ["geometrie.js", "feld.js", "schnitt.js"])
  vm.runInContext(fs.readFileSync(__dirname + "/" + f, "utf8"), ctx, f);

const BASIS = {
  topo: "esdr", laeufer: "sektor", stapel: 1,
  ro: 130, ri: 75.01, lam: 0.577, poles: 16, q: 48, bnut: 6,
  spalt: 1, zahn: 25, jochS: 12, jochR: 13, magd: 6, alpha: 0.85,
  welle: 30, wkI: 14, rs: 102.5, last: 0,
  magSegU: 1, magSegR: 1, magFuge: 1, qr: 0, beta: 0,
  rotorOhneJoch: false, statorOhneJoch: true, nSpalte: 2,
};
const P = (o) => ({ ...BASIS, ...o });

let ok = 0, fehl = 0;
const pr = (b, t) => { b ? ok++ : fehl++; console.log(`  ${b ? "✓" : "✗"} ${t}`); };

function lauf(p, ny, iter) {
  const g0 = ctx.feldGitter(p, 8, 8);
  const nx = Math.round(ny * (g0.breite / g0.hGes));
  const g = ctx.feldGitter(p, nx, ny);
  const loe = ctx.loeseFeld(p, g, iter);
  const { A, relRest, schritte } = loe;
  const rest = relRest;
  const { Bx, By } = ctx.feldAus(g, A);
  const e = ctx.eichung(p, g, By, loe.pkMag);
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

// Geprueft wird die Monotonie am ROHEN Lauf, nicht am geeichten Wert — und das
// ist seit dem 06.10.2026 ein Unterschied. Vorher war der Eichfaktor eine
// Konstante gegen die eigene Spitze, der gemeldete Wert also bis auf einen
// Faktor der rohe; seither ist er `analytische Grundwelle x GEMESSENER
// Nutungsverlust`, und der Verlust ist ein Verhaeltnis ZWEIER Loeserlaeufe
// (genutet gegen nutlos). Zwei Konvergenzpfade geteilt muessen nicht monoton
// sein, auch wenn jeder einzelne es ist. Die Gitterfrage — liegen die y-Linien
// richtig? — haengt am rohen Lauf, und dort wird sie gestellt.
const rohe = reihe.map((r) => r.b1 / r.e.sf);
const rl = rohe[rohe.length - 1];
const abwRoh = rohe.map((v) => Math.abs(v - rl) / rl * 100);
console.log("   roh (ungeeicht), Abweichung zum feinsten: "
            + abwRoh.map((a) => a.toFixed(2) + " %").join("  "));
// **Gemessen ist die Konvergenz BESCHRAENKT, nicht monoton** — und die frühere
// Monotonie war ein Artefakt. Bis zum 06.10.2026 meldete die Seite
// `bAn_mittel x h1/pk` aus EINEM Lauf: Grundwelle und Spitze wandern mit dem
// Gitter gemeinsam, ihr Verhältnis kürzt also einen Teil des
// Diskretisierungsfehlers heraus und sah dadurch monotoner aus als der Löser
// ist. Die rohe Grundwelle selbst streut 0,35 / 0,16 / 1,54 / 1,06 / 0,00 %,
// mit einem Ausreißer bei 120x106. Die Aussage, für die es diesen Test gibt —
// das schichtbündige Gitter hält den 1-mm-Spalt exakt, statt ihn aufs Raster
// schnappen zu lassen — trägt weiterhin: ±1,8 % gegen die ±6 % des
// gleichmäßigen dy. Nur „monoton" war zu viel behauptet.
pr(Math.max(...abwRoh) < 3.0,
   `die ROHE Grundwelle bleibt über eine 4-fache Netzverfeinerung in ${Math.max(...abwRoh).toFixed(2)} % `
   + `— das tut sie nur, weil die y-Linien auf den Schichtgrenzen liegen (mit `
   + `gleichmäßigem dy streute sie um ±6 %). MONOTON ist sie nicht, s. Kommentar`);
pr(Math.max(...abw) < 3.0,
   `und der geeichte Wert bleibt dabei in einem engen Band (${Math.max(...abw).toFixed(2)} % `
   + `über eine 4-fache Netzverfeinerung) — er ist ein Verhältnis zweier Läufe, `
   + `also nicht monoton, aber beschränkt`);

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

console.log("\n— 6. Stückzahlen: wie viele Magnete, wie viele Zähne? —");
{
  for (const [nU, nR] of [[1, 1], [3, 1], [1, 2], [4, 3]]) {
    const p = P({ magSegU: nU, magSegR: nR });
    const M = ctx.magnetSegmente(p), R = ctx.magnetRinge(p);
    const n = p.poles * M.nU * R.nR;
    pr(n === p.poles * nU * nR,
       `${nU} umfangs × ${nR} radial → ${n} Magnete ` +
       `(Platte ${(M.breit * 2 * Math.PI * ((p.ri + p.ro) / 2) / p.poles).toFixed(1)} × ` +
       `${R.h.toFixed(1)} mm)`);
  }
  // Die Fugen sind Luft und muessen Magnetflaeche KOSTEN -- sonst waere die
  // Stueckelung eine Einstellung, die nichts bewegt.
  const a = (nU, nR) => { const p = P({ magSegU: nU, magSegR: nR });
    const M = ctx.magnetSegmente(p), R = ctx.magnetRinge(p);
    return M.nU * M.breit * R.nR * R.h; };
  const f0 = a(1, 1), f1 = a(4, 3);
  pr(f1 < f0 * 0.98,
     `4×3 statt 1×1 kostet ${((1 - f1 / f0) * 100).toFixed(1)} % Magnetfläche ` +
     `(1 mm Fugen) — die Stückelung ist nicht gratis`);
  // Und sie muss im FELD ankommen, nicht nur in der Zeichnung.
  const b0 = lauf(P(), 100, 3000).b1, b4 = lauf(P({ magSegU: 4 }), 100, 3000).b1;
  pr(b4 < b0 && b4 > b0 * 0.8,
     `B1 fällt mit den Fugen von ${b0.toFixed(4)} auf ${b4.toFixed(4)} T ` +
     `(${((b4 / b0 - 1) * 100).toFixed(1)} %) — der Löser sieht sie`);
  // Die Vorgabe (ein Magnet je Pol) muss die Zeichnung vor der Stueckelung
  // reproduzieren, sonst ist jener Umbau nicht nur eine Erweiterung gewesen.
  //
  // **Der Festwert ist am 06.10.2026 von 0,80818 auf 1,12066 T gesetzt worden**,
  // und zwar nicht weil sich die Zeichnung geaendert haette, sondern die
  // EICHUNG: sie pinnte die Spitze des gelösten Feldes auf `Br*perm*alpha`,
  // einen flussgewichteten MITTELWERT, und meldete davon die Grundwelle. Der
  // Faktor 1,386 setzt sich zusammen aus 1/alpha = 1,176 (der Mittelwert stand
  // an der Stelle einer Spitze) und 1,18 (geeicht wurde an der GENUTETEN
  // Spitze, die durch die Bündelung über dem Zahn um 23 % über der nutlosen
  // liegt). Gegengerechnet gegen den Elmer-Ringsektor: vorher +49 % Abweichung,
  // danach +2,5 %. Voller Befund in `BEFUNDE.md`.
  pr(Math.abs(b0 - 1.12066) < 5e-4,
     `1×1 reproduziert den Stand der Stückelung: B1 ${b0.toFixed(5)} T ` +
     `(Festwert 1,12066 — vor der Eichberichtigung am 06.10.2026 waren es 0,80818)`);
}

console.log("\n— 7. Halbach: eine Wellenlänge sind ZWEI Polteilungen —");
{
  // Das Fenster ist genau 2 Polteilungen breit. Harmonische 1 ueber dem
  // Fenster IST also die Polteilungs-Grundwelle; Harmonische 2 hat die
  // Wellenlaenge EINER Polteilung, also die doppelte Polzahl.
  const har = (p, n) => {
    const r = lauf(p, 120, 4000), N = r.nx, j = r.e.jGap;
    let re = 0, im = 0;
    for (let i = 0; i < N; i++) {
      const th = 2 * Math.PI * n * i / N, b = r.By[j * N + i];
      re += b * Math.cos(th); im += b * Math.sin(th);
    }
    return 2 * Math.hypot(re, im) / N;
  };
  const hp = P({ laeufer: "halbach", magSegU: 4 });
  const h1 = har(hp, 1), h2 = har(hp, 2);
  console.log(`   jetzt:  Grundwelle ${h1.toExponential(3)} · 2. Harmonische ${h2.toExponential(3)}`);
  pr(h1 > 4 * h2,
     `die Grundwelle trägt ${(h1 / Math.max(h2, 1e-30)).toFixed(0)}× die 2. Harmonische ` +
     `— das Array hat die Polzahl, die eingestellt ist`);
  // Gegenprobe mit der ALTEN Regel ([1,0,-1,0] je Polteilung): sie dreht die
  // Magnetisierung volle 360 Grad je Polteilung und traegt damit die doppelte
  // Polzahl. Siehe BEFUNDE.md, 06.10.2026.
  const echt = ctx.magnetRichtung;
  ctx.magnetRichtung = (p, pol, k, nU, hal) =>
    hal ? [0, [1, 0, -1, 0][(pol * nU + k) % 4]] : echt(p, pol, k, nU, hal);
  const a1 = har(hp, 1), a2 = har(hp, 2);
  ctx.magnetRichtung = echt;
  console.log(`   alt:    Grundwelle ${a1.toExponential(3)} · 2. Harmonische ${a2.toExponential(3)}`);
  pr(a2 > 4 * a1,
     `die alte Regel legte ${(a2 / Math.max(a1, 1e-30)).toFixed(0)}× so viel in die ` +
     `2. Harmonische — sie zeichnete 2p = ${2 * hp.poles} statt ${hp.poles}`);
}

console.log("\n— 8. Läuferstabzahl gegen die Python-Fassung —");
{
  // `geometrie.js:stabzahl` ist ein Spiegel von `ema_asm.stabzahl`. Zwei Regeln
  // nebeneinander waeren zwei verschiedene Läufer, und beide sähen richtig aus
  // — dieselbe Falle wie `magnetLegs` im Hauptwerkzeug, dieselbe Absicherung
  // wie `test_mobil.py` (JS mit node ausführen und vergleichen).
  const { execFileSync } = require("child_process");
  const faelle = [];
  for (const q of [24, 36, 48, 54, 60, 72]) for (const pp of [1, 2, 3, 4, 8])
    faelle.push([q, pp]);
  let py;
  try {
    py = JSON.parse(execFileSync("python3", ["-c",
      "import sys,json,ema_asm;print(json.dumps([ema_asm.stabzahl({'slots':q,'p':p})" +
      " for q,p in json.loads(sys.argv[1])]))", JSON.stringify(faelle)],
      { cwd: __dirname + "/..", encoding: "utf8" }));
  } catch (e) {
    console.log("   übersprungen — ema_asm nicht erreichbar: " + e.message.split("\n")[0]);
    py = null;
  }
  if (py) {
    const js = faelle.map(([q, pp]) => ctx.stabzahl(P({ q, poles: 2 * pp, qr: 0 })));
    const schief = faelle.filter((_, i) => js[i] !== py[i]);
    pr(schief.length === 0,
       `${faelle.length} Fälle (Q × p) stimmen mit ema_asm.stabzahl überein` +
       (schief.length ? ` — ab: ${schief.slice(0, 3).map(([q, pp], i) => `Q${q}/p${pp}`).join(" ")}` : ""));
  }
  // Eine gesetzte Zahl wird GENOMMEN und der Befund daneben gestellt -- nicht
  // geklemmt: ein geklemmter Wert sieht wie ein angenommener aus.
  const b = ctx.stabzahlBefund(P({ q: 48, poles: 16, qr: 48 }));
  pr(b.nR === 48 && b.warn.length >= 1,
     `qr = Q = 48 wird gezeichnet und benannt: ${b.warn.join(", ")}`);
  pr(ctx.stabzahlBefund(P({ q: 48, poles: 16, qr: 0 })).warn.length === 0,
     `die abgeleitete Zahl (${ctx.stabzahl(P({ q: 48, poles: 16, qr: 0 }))}) besteht die Regel selbst`);
}

console.log("\n— 9. Achsschnitt: der Mehrschnitt trägt, was ein 2-D-Lauf nicht kann —");
{
  const p = P();
  const t0 = Date.now();
  const erg = ctx.schnittRechnen(p, 12, 80, 3000);
  const tSolve = Date.now() - t0;
  console.log(`   12 Scheiben, ${erg.ny} Zeilen, ${tSolve} ms, ` +
              `${erg.schritte} CG-Schritte, rel. Rest ${erg.relRest.toExponential(1)}`);

  // Die Scheiben lassen sich nur deshalb ohne Umrechnung stapeln, weil die
  // Schichtung nicht am Radius hängt. Wäre das nicht so, wäre jedes (r,z)-Bild
  // eine Interpolation und der Luftspalt verschmierte.
  const yk = erg.scheiben.map((s) => s.g.yk);
  pr(yk.every((y) => y.length === yk[0].length &&
                     y.every((v, i) => Math.abs(v - yk[0][i]) < 1e-12)),
     "alle Scheiben haben dasselbe z-Gitter — stapelbar ohne Interpolation");

  // Die Pointe: der Winkel ist Ablesen, kein Lauf.
  const t1 = Date.now();
  for (let a = 0; a < 360; a++) ctx.rzBei(erg, a * Math.PI / 180);
  const tLesen = Date.now() - t1;
  pr(tLesen < tSolve / 5,
     `360 Schnittwinkel abgelesen in ${tLesen} ms gegen ${tSolve} ms für EINEN ` +
     `Lauf — „alle 360°" kostet ${(tLesen / Math.max(tSolve, 1)).toFixed(2)}× einen Winkel`);

  // DIE Aussage dieser Bauart: parallelflankige Nut ⇒ tau_s wächst mit r,
  // die Nutbreite nicht ⇒ der Zahn wird außen breiter ⇒ B_Zahn fällt.
  const v = ctx.zahnVerlauf(erg, p);
  console.log("   r [mm]   τs    Zahn   B_Spalt  B_Zahn  B_Zahn(geo)");
  for (const a of v)
    console.log(`   ${a.r.toFixed(1).padStart(5)} ${a.tauS.toFixed(2).padStart(6)} ` +
      `${a.zahn.toFixed(2).padStart(6)} ${a.b_spalt.toFixed(4).padStart(8)} ` +
      `${a.b_zahn.toFixed(4).padStart(7)} ${a.b_zahn_geo.toFixed(4).padStart(10)}`);
  const fallend = v.every((a, i) => i === 0 || a.b_zahn <= v[i - 1].b_zahn * 1.06);
  pr(fallend && v[0].b_zahn > v[v.length - 1].b_zahn * 1.3,
     `B_Zahn fällt ${v[0].b_zahn.toFixed(3)} → ${v[v.length - 1].b_zahn.toFixed(3)} T ` +
     `(×${(v[0].b_zahn / v[v.length - 1].b_zahn).toFixed(2)}) — kritisch am INNENrand`);

  // Gegenprobe, dass das wirklich die NUT ist und nicht der Spalt: der
  // Spaltleitwert hängt nicht am Radius, also muss B_Spalt fast stehen.
  const rk = ctx.radialeKopplung(erg, p);
  pr(rk.spanne < 0.10,
     `B_Spalt steht dabei auf ${(rk.spanne * 100).toFixed(1)} % — die ` +
     `Zahnänderung kommt aus der Geometrie, nicht aus dem Spalt`);

  // Und die Naeherung wird beziffert statt nur genannt.
  pr(rk.jeSpalt < 0.05,
     `∂/∂r fallengelassen: das Feld ändert sich um ${(rk.jeSpalt * 100).toFixed(3)} % ` +
     `je Luftspaltlänge — die Scheiben-Näherung trägt hier`);

  // Eine Eichung fuer ALLE Scheiben. Jede einzeln geeicht ergaebe per
  // Konstruktion dieselbe Spaltspitze und loeschte genau das aus, was dieser
  // Schnitt zeigen soll.
  pr(new Set(erg.scheiben.map((s) => s.sf)).size === 1,
     "eine einzige Eichung für alle Scheiben — sonst wäre die radiale " +
     "Änderung wegnormiert, bevor man sie sieht");
  const je = erg.scheiben.map((s) => ctx.radialeKopplung(
    { ...erg, scheiben: [s] }, p).spalt[0].b);
  console.log(`   Gegenprobe: je Scheibe einzeln geeicht wäre B_Spalt überall ` +
              `${(ctx.eichung ? "" : "")}gleich; mit EINER Eichung spannt es ` +
              `${Math.min(...je).toFixed(4)} … ${Math.max(...je).toFixed(4)} T`);
}

console.log("\n— 10. Stromwinkel β: was eine Drehzahländerung im Feld bewegt —");
{
  // Eine magnetostatische Rechnung kennt keine Drehzahl. Sichtbar wird sie
  // allein über den Stromvektor — unter Feldschwächung dreht er in die
  // d-Achse. β ist also die ehrliche Achse; die Abbildung Drehzahl → (i_d,i_q)
  // hat diese Seite NICHT (die steht in ema_analysis.estimate_dq_currents).
  const b = (beta, last) => lauf(P({ last, beta: beta * Math.PI / 180 }), 100, 3000).b1;
  const leer = b(0, 0);
  const q = b(0, 200), d = b(-90, 200), dp = b(90, 200);
  console.log(`   Leerlauf ${leer.toFixed(4)} · β=0 (q-Achse) ${q.toFixed(4)} ` +
              `· β=−90° ${d.toFixed(4)} · β=+90° ${dp.toFixed(4)} T`);
  // Der Anker ist auf `last` Prozent der MAGNETgrundwelle gesetzt. Dann muss
  // bei last = 100 gelten: beta = 0 addiert in QUADRATUR (der q-Strom dreht die
  // Resultierende), beta = -+90 addiert bzw. subtrahiert direkt. Das ist eine
  // Rechnung, die aufgehen MUSS, wenn die Normierung stimmt -- und sie ging
  // ueber die Spitze normiert nicht auf.
  const e1 = b(0, 100), d1 = b(-90, 100), p1 = b(90, 100);
  console.log(`   last = 100 %:  β=0 ${e1.toFixed(4)} (soll √2·${leer.toFixed(4)} = ` +
              `${(leer * Math.SQRT2).toFixed(4)}) · β=−90° ${d1.toFixed(4)} ` +
              `(soll 2×  = ${(2 * leer).toFixed(4)}) · β=+90° ${p1.toFixed(4)} (soll 0)`);
  pr(Math.abs(e1 / (leer * Math.SQRT2) - 1) < 0.08,
     `β = 0 addiert in Quadratur: ${(e1 / leer).toFixed(3)}× statt ${Math.SQRT2.toFixed(3)}× ` +
     `— der q-Strom dreht die Resultierende, er schwächt nicht`);
  pr(Math.abs(d1 / (2 * leer) - 1) < 0.08 && p1 < leer * 0.15,
     `β = ∓90° addiert/subtrahiert direkt: ${(d1 / leer).toFixed(3)}× und ` +
     `${(p1 / leer).toFixed(3)}× — Feldverstärkung und -schwächung`);
  pr(Math.abs(q - leer) / leer > 0.3,
     `und der Regler WIRKT: bei 200 % steht die Grundwelle auf ` +
     `${(q / leer).toFixed(2)}× statt auf 1,000× (roh war der Hub bei ±400 ` +
     `ganze 0,02 %)`);
}

console.log(`\n${ok} bestanden, ${fehl} fehlgeschlagen`);
process.exit(fehl ? 1 : 0);
