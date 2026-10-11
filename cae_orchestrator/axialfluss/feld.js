/* feld.js — Magnetfeld der abgewickelten Scheibe, in der Seite gerechnet.
 *
 * WOZU, und wozu NICHT
 * --------------------
 * Dies ist eine QUALITATIVE Felddarstellung zur Pruefung der ZEICHNUNG. Sie
 * beantwortet: laeuft der Fluss dorthin, wo die Bauart ihn hinschickt? Geht er
 * axial durch Zahn und Spalt? Kehrt er im Joch umfangs zurueck? Zeigt der
 * Magnet zum Spalt? Das sind Fragen an die Geometrie, und ein Feld beantwortet
 * sie schaerfer als jede Beschriftung -- vier Zeichenfehler sind am gerenderten
 * Bild gefunden worden, nicht am Quelltext.
 *
 * Sie ist AUSDRUECKLICH keine Rechnung. Wer Zahlen will (B_gap, psi, Moment),
 * nimmt ``ema_axial_fdm.py``; dessen offene Punkte stehen in ``BEFUNDE.md``.
 *
 * EIN VORTEIL GEGENUEBER DEM PYTHON-WEG, und er ist nicht kosmetisch
 * ---------------------------------------------------------------------
 * ``ema_analysis._build_fv_matrix`` legt ``cid`` als (N, N) an und rechnet mit
 * EINER Maschenweite -- das Gebiet muss quadratisch sein. Der abgewickelte
 * Schnitt ist es nicht (zwei Polteilungen breit, ein Stapel hoch), also musste
 * dort mit Eisen aufgefuellt werden, und die Fensterbreite blieb mit 1,3 %
 * im Ergebnis (BEFUNDE 05.10.2026).
 *
 * Hier ist das Gitter RECHTECKIG mit dx != dy. Damit entfaellt die Polsterung
 * ganz: ``A = 0`` sitzt auf den Aussenflaechen der Joche, wo es hingehoert --
 * das ist die Aussage "das Joch schliesst den Fluss ein" --, und seitlich auf
 * den Polgrenzen, wo A ohnehin null ist. Keine Modellwahl, die sich im
 * Ergebnis niederschlaegt.
 *
 * Verfahren: Finite Volumen, harmonisch gemittelte Flaechenleitwerte,
 * Rot-Schwarz-SOR. Geeicht wird die Spitze im Spalt auf die Arbeitsgerade
 * ``Br*hm/(hm + mu_r*kc*g)`` -- dieselbe Eichung wie im Hausloeser, damit
 * Bild und Rechnung dieselbe Amplitude meinen.
 */
"use strict";

const MU0 = 4e-7 * Math.PI;
const BR = 1.15, MUR_MAG = 1.05, MUR_FE = 500, KC = 1.15;
// Deckel der Farbskala, geteilt mit `schnitt.js`: ueber dem Saettigungsknie
// ist die lineare Rechnung ohnehin nicht mehr zustaendig. Ohne Deckel setzt
// immer eine Eisenecke die Skala und das halbe Bild ist weiss.
const B_KNIE = 2.1;

/* Welcher Magnet sitzt bei x, und wie ist er magnetisiert?
 *
 * EINE Stelle fuer Zeichnung und Loeser -- die Belegung kommt aus
 * `magnetSegmente`/`magnetRichtung` in `geometrie.js`. Vorher stand sie an
 * DREI Stellen einzeln: `seg = 4` plus `[1, 0, -1, 0]` in der Draufsicht, in
 * der Abwicklung und hier. Null heisst Luft (Fuge oder Polluecke).
 */
function magnetBei(p, M, x, tauP) {
  const u = x / tauP, pol = Math.floor(u), rest = u - pol;
  for (const sg of M.seg)
    // Beim Halbach ueberspannt Segment 0 die POLGRENZE, liegt also zur Haelfte
    // im Nachbarpol -- deshalb wird um +-1 Polteilung mitgesucht, und die
    // Magnetisierung gehoert dann auch zu dem Nachbarpol.
    for (const vs of [0, 1, -1])
      if (Math.abs(rest - (sg.mitte + vs)) <= sg.breit / 2)
        return magnetRichtung(p, pol + vs, sg.k, M.nU, M.hal);
  return null;
}

/* Gitter aus der Schichtung: mu und J, rechteckig. ``stapelLagen`` ist DIE
 * Quelle -- dieselbe, aus der auch gezeichnet wird. Zwei Beschreibungen
 * derselben Geometrie waeren genau die Drift, gegen die `ema_laeufer.js`
 * absichtlich duenn ist. */
function feldGitter(p, nx, ny, ohneNut) {
  // `ohneNut` baut denselben Staender OHNE Nutschlitze. Das ist kein Schalter
  // fuer den Menschen, sondern der Bezugsfall der EICHUNG: geeicht wird an der
  // Spitze des nutlosen Feldes, weil nur die mit der Arbeitsgeraden dieselbe
  // Groesse meint (s. `eichung`). Die Nutung wird damit GEMESSEN statt aus
  // `KC` angenommen.
  // ny ist ein ZIEL; die wirkliche Zeilenzahl folgt aus den Schichtgrenzen.
  const lagen = stapelLagen(p).filter((l) => l.art !== "fuge");
  const hGes = lagen.reduce((a, l) => a + l.d, 0);
  const tauP = (2 * Math.PI * p.rs) / p.poles;
  const tauS = (2 * Math.PI * p.rs) / p.q;
  const breite = 2 * tauP;                 // genau 2 Polteilungen = 1 el. Periode
  const dx = breite / nx;

  // Schichtgrenzen in y
  let z = 0; const bnd = [];
  for (const l of lagen) { bnd.push({ ...l, y0: z, y1: z + l.d }); z += l.d; }

  // **Das Gitter in y ist UNGLEICHMAESSIG und liegt auf den Schichtgrenzen.**
  //
  // Mit gleichmaessigem dy schnappen die duennen Schichten (Spalt 1 mm, Magnet
  // 6 mm) auf das Raster, und eine halbe Zellbreite Versatz aendert den
  // wirksamen Spalt um Prozente. Gemessen streute B1 dadurch um +-6 % ueber
  // 72x60 ... 192x160, ohne zu konvergieren -- derselbe Befund wie auf dem
  // Python-Weg (BEFUNDE 05.10.2026), und er hat dort nichts mit dem
  // quadratischen Gitter zu tun.
  //
  // Jede Schichtgrenze ist jetzt eine ZELLFLAECHE: der Spalt ist exakt 1 mm,
  // egal wie fein gerechnet wird. Der Luftspalt bekommt dabei mindestens
  // SPALT_ZEILEN Zeilen, weil er das duennste Merkmal ist und alles andere an
  // ihm haengt.
  const dyZiel = hGes / ny, SPALT_ZEILEN = 5;
  const yk = [0];
  for (const b of bnd) {
    const n = Math.max(b.art === "spalt" ? SPALT_ZEILEN : 2,
                       Math.round(b.d / dyZiel));
    for (let i = 1; i <= n; i++) yk.push(b.y0 + (b.d * i) / n);
  }
  ny = yk.length - 1;
  const dyv = new Float64Array(ny), yc = new Float64Array(ny);
  for (let j = 0; j < ny; j++) { dyv[j] = yk[j + 1] - yk[j]; yc[j] = (yk[j] + yk[j + 1]) / 2; }

  const mu = new Float64Array(nx * ny).fill(1);
  // Mx traegt beim Halbach die halbe Erregung und fehlte hier ganz: der frueher
  // notierte Grund ("die x-Komponente steckt im Sprung zwischen den Segmenten")
  // gilt nur fuer dMy/dx. Der Term -dMx/dy ist ein Flaechenstrom auf der OBEREN
  // und UNTEREN Magnetflaeche und hat damit nichts zu tun.
  const My = new Float64Array(nx * ny);
  const Mx = new Float64Array(nx * ny);
  const J = new Float64Array(nx * ny);     // Magnete (curl M)
  // Der Staenderstrom wird GETRENNT gefuehrt und mit EINHEITSAMPLITUDE
  // aufgebaut. Grund: der Loeser ist linear, also ist A = A_Magnet + A_Anker,
  // und dann laesst sich der Ankeranteil hinterher auf einen MESSBAREN Bruchteil
  // des Magnetanteils setzen, statt ihn in willkuerlichen Einheiten anzugeben.
  // Vorher stand `iq` roh im Quellterm, und bei +-400 -- dem ganzen Stellbereich
  // des Reglers -- bewegte sich das Feld um 0,02 %: ein Regler, der nichts tut.
  // Dieselbe Aufteilung und derselbe Grund wie die geteilte Eichung in
  // `ema_analysis.run_em_analysis` (Magnet gegen `_analytical_Bgap`, Anker gegen
  // `_analytical_Barm`).
  const Js = new Float64Array(nx * ny);
  const rolle = new Uint8Array(nx * ny);   // 0 Luft 1 Eisen 2 Magnet 3 Leiter

  const iq = p.last ? 1 : 0;                // Einheitsamplitude, s. oben
  const magAmp = BR / (MU0 * MUR_MAG);
  const M = magnetSegmente(p);              // EINE Quelle, s. geometrie.js
  const qr = stabzahl(p);                   // dito -- Regel aus ema_asm

  for (let j = 0; j < ny; j++) {
    const y = yc[j];
    const lg = bnd.find((b) => y >= b.y0 && y < b.y1);
    if (!lg) continue;
    for (let i = 0; i < nx; i++) {
      const x = (i + 0.5) * dx, k = j * nx + i;
      if (lg.art === "spalt") { mu[k] = 1; continue; }

      if (lg.art === "stator") {
        if (p.laeufer === "eisenlos") {
          // Scheibenlaeufer: der STAENDER traegt die Magnete, nicht der Laeufer.
          const tief = lg.seite === "unten" ? (y - lg.y0 < p.magd)
                                            : (lg.y1 - y < p.magd);
          if (tief) {
            const m = magnetBei(p, M, x, tauP);
            if (m) { mu[k] = MUR_MAG; rolle[k] = 2;
                     Mx[k] = magAmp * m[0]; My[k] = magAmp * m[1]; }
            else mu[k] = 1;
          } else { mu[k] = MUR_FE; rolle[k] = 1; }
          continue;
        }
        mu[k] = MUR_FE; rolle[k] = 1;
        const imSchlitz = lg.seite === "unten" ? (y - lg.y0 < p.zahn)
                        : lg.seite === "beide" ? true
                        : (lg.y1 - y < p.zahn);
        if (imSchlitz) {
          const u = x % tauS, mid = tauS / 2;
          if (!ohneNut && Math.abs(u - mid) <= p.bnut / 2) {
            mu[k] = 1; rolle[k] = 3;
            if (iq !== 0) {
              const sIdx = Math.floor(x / tauS);
              const el = (sIdx + 0.5) * tauS / p.rs * (p.poles / 2);
              // `beta` ist der STROMWINKEL gegen die q-Achse, elektrisch. Er
              // war nicht da, und ohne ihn gibt es nur reines q-Moment: der
              // Feldschwaechbetrieb -- also das, was eine Drehzahlaenderung im
              // magnetostatischen Feld ueberhaupt SICHTBAR macht -- war nicht
              // einstellbar. Dieselben drei Darstellungsarten wie
              // `field_modes` im Hauptwerkzeug: Laeuferlage, Stromwinkel,
              // Last-Rampe.
              Js[k] += -iq * Math.sin(el + (p.beta || 0));
            }
          }
        }
        continue;
      }

      if (lg.art === "rotor") {
        const aktiv = lg.seite === "unten" ? (y - lg.y0 < p.magd)
                    : lg.seite === "beide" ? true
                    : (lg.y1 - y < p.magd);
        if (!aktiv) { mu[k] = MUR_FE; rolle[k] = 1; continue; }
        if (p.laeufer === "kaefig") {
          const tauR = (2 * Math.PI * p.rs) / qr;
          const u = x % tauR;
          if (Math.abs(u - tauR / 2) <= p.bnut * 0.4) { mu[k] = 1; rolle[k] = 3; }
          else { mu[k] = MUR_FE; rolle[k] = 1; }
        } else if (p.laeufer === "eisenlos") {
          mu[k] = 1; rolle[k] = 3;          // blanker Leiter, kein Eisen
        } else {
          const m = magnetBei(p, M, x, tauP);
          if (m) { mu[k] = MUR_MAG; rolle[k] = 2;
                   Mx[k] = magAmp * m[0]; My[k] = magAmp * m[1]; }
          else { mu[k] = 1; rolle[k] = 0; }   // Fuge oder Polluecke
        }
        continue;
      }
    }
  }
  // J = (curl M)_z = dMy/dx - dMx/dy.
  // Der zweite Term war weggelassen, weil Mx bei Sektormagneten null ist. Beim
  // Halbach ist er es nicht, und er sitzt genau dort, wo das Array arbeitet:
  // auf den beiden FLAECHEN des Magnetbandes. In y ist das Gitter ungleich-
  // maessig, also mit den Abstaenden der Zellmitten differenzieren.
  for (let j = 0; j < ny; j++)
    for (let i = 1; i < nx - 1; i++)
      J[j * nx + i] += (My[j * nx + i + 1] - My[j * nx + i - 1]) / (2 * dx);
  for (let j = 1; j < ny - 1; j++) {
    const h = (yc[j + 1] - yc[j - 1]);
    for (let i = 0; i < nx; i++)
      J[j * nx + i] -= (Mx[(j + 1) * nx + i] - Mx[(j - 1) * nx + i]) / h;
  }
  return { mu, J, Js, Mx, My, rolle, nx, ny, dx, dyv, yc, yk, breite, hGes,
           tauP, tauS, bnd, qr, nMag: p.poles * M.nU * magnetRinge(p).nR };
}

/* Rot-Schwarz-SOR auf dem rechteckigen Gitter.
 * A = 0 auf allen vier Raendern: seitlich auf den POLGRENZEN (dort ist A
 * ohnehin null, das Fenster ist genau zwei Polteilungen breit), oben und unten
 * auf den AUSSENFLAECHEN der Joche -- die Aussage, dass das Joch den Fluss
 * einschliesst. Deshalb braucht es hier keine Polsterung. */
function loese(g, iter = 900, omega = 1.85) {
  const { mu, J, nx, ny, dx, dy } = g;
  const A = new Float64Array(nx * ny);
  const nu = new Float64Array(nx * ny);
  for (let k = 0; k < nu.length; k++) nu[k] = 1 / mu[k];
  const hx = dy / dx, hy = dx / dy, vol = dx * dy;
  const har = (a, b) => (2 * a * b) / (a + b);
  let rest = 0;
  for (let it = 0; it < iter; it++) {
    rest = 0;
    for (let farbe = 0; farbe < 2; farbe++) {
      for (let j = 1; j < ny - 1; j++) {
        for (let i = 1 + ((j + farbe) % 2); i < nx - 1; i += 2) {
          const k = j * nx + i;
          const ne = har(nu[k], nu[k + 1]) * hx, nw = har(nu[k], nu[k - 1]) * hx;
          const nn = har(nu[k], nu[k + nx]) * hy, ns = har(nu[k], nu[k - nx]) * hy;
          const d = ne + nw + nn + ns;
          if (d <= 0) continue;
          const neu = (ne * A[k + 1] + nw * A[k - 1] + nn * A[k + nx] +
                       ns * A[k - nx] + J[k] * vol) / d;
          const dA = neu - A[k];
          A[k] += omega * dA;
          const ad = Math.abs(dA); if (ad > rest) rest = ad;
        }
      }
    }
    if (it > 60 && rest < 1e-12) break;
  }
  return { A, rest };
}


/* Vorkonditioniertes CG statt SOR.
 *
 * Der Operator ist derselbe wie im Hausloeser und wie dort **symmetrisch
 * positiv definit** (Finite Volumen, harmonisch gemittelte Flaechenleitwerte,
 * Dirichlet am Rand). Python loest ihn direkt (`splu`); das geht in JS nicht
 * ohne eine Sparse-Bibliothek, aber SPD heisst, dass CG passt -- und CG ist bei
 * mu-Spruengen von 1 auf 500 um Groessenordnungen besser als SOR, weil dessen
 * Konvergenzrate an der Kondition haengt, die genau dieser Sprung verdirbt.
 *
 * Vorkonditioniert mit der Diagonalen (Jacobi): billig, und sie faengt genau
 * den Materialsprung ab, weil die Diagonale die Summe der Flaechenleitwerte
 * ist.
 */
function loeseCG(g, iter = 600, tol = 1e-10, quelle = null) {
  const { mu, nx, ny, dx, dyv } = g;
  const J = quelle || g.J;
  const n = nx * ny;
  const nu = new Float64Array(n);
  for (let k = 0; k < n; k++) nu[k] = 1 / mu[k];
  // Bei ungleichmaessigem dy ist das harmonische Mittel mit den ABSTAENDEN zu
  // gewichten, sonst sitzt der Leitwert nicht auf der Flaeche zwischen den
  // beiden Zellmitten.
  const harY = (a, b, da, db) => (da + db) / (da / a + db / b);
  const har = (a, b) => (2 * a * b) / (a + b);
  // Flaechenleitwerte einmal vorrechnen -- sie haengen nur am Material.
  const ce = new Float64Array(n), cw = new Float64Array(n),
        cn = new Float64Array(n), cs = new Float64Array(n), dg = new Float64Array(n);
  const innen = (i, j) => i > 0 && j > 0 && i < nx - 1 && j < ny - 1;
  for (let j = 1; j < ny - 1; j++)
    for (let i = 1; i < nx - 1; i++) {
      const k = j * nx + i;
      const dyj = dyv[j];
      ce[k] = har(nu[k], nu[k + 1]) * dyj / dx;
      cw[k] = har(nu[k], nu[k - 1]) * dyj / dx;
      cn[k] = harY(nu[k], nu[k + nx], dyj, dyv[j + 1]) * dx / ((dyj + dyv[j + 1]) / 2);
      cs[k] = harY(nu[k], nu[k - nx], dyj, dyv[j - 1]) * dx / ((dyj + dyv[j - 1]) / 2);
      dg[k] = ce[k] + cw[k] + cn[k] + cs[k];
    }
  const mul = (x, y) => {                       // y = A x  (nur Innenpunkte)
    for (let j = 1; j < ny - 1; j++)
      for (let i = 1; i < nx - 1; i++) {
        const k = j * nx + i;
        y[k] = dg[k] * x[k] - ce[k] * x[k + 1] - cw[k] * x[k - 1]
                            - cn[k] * x[k + nx] - cs[k] * x[k - nx];
      }
  };
  const A = new Float64Array(n), r = new Float64Array(n), z = new Float64Array(n),
        pv = new Float64Array(n), Ap = new Float64Array(n);
  let b2 = 0;
  for (let j = 1; j < ny - 1; j++)
    for (let i = 1; i < nx - 1; i++) {
      const k = j * nx + i; r[k] = J[k] * dx * dyv[j]; b2 += r[k] * r[k];
    }
  if (b2 === 0) return { A, rest: 0, schritte: 0, relRest: 0 };
  const bn = Math.sqrt(b2);
  let rz = 0;
  for (let k = 0; k < n; k++) { if (dg[k] > 0) { z[k] = r[k] / dg[k]; pv[k] = z[k]; rz += r[k] * z[k]; } }
  let it = 0, rn = bn;
  for (; it < iter; it++) {
    mul(pv, Ap);
    let pAp = 0;
    for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++)
      { const k = j * nx + i; pAp += pv[k] * Ap[k]; }
    if (!(pAp > 0)) break;
    const al = rz / pAp;
    let r2 = 0;
    for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++) {
      const k = j * nx + i; A[k] += al * pv[k]; r[k] -= al * Ap[k]; r2 += r[k] * r[k];
    }
    rn = Math.sqrt(r2);
    if (rn / bn < tol) { it++; break; }
    let rz2 = 0;
    for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++)
      { const k = j * nx + i; z[k] = r[k] / dg[k]; rz2 += r[k] * z[k]; }
    const be = rz2 / rz; rz = rz2;
    for (let j = 1; j < ny - 1; j++) for (let i = 1; i < nx - 1; i++)
      { const k = j * nx + i; pv[k] = z[k] + be * pv[k]; }
  }
  return { A, rest: rn, relRest: rn / bn, schritte: it };
}

/* B = curl A, materialbewusst: ueber eine Materialgrenze wird NICHT zentral
 * differenziert. Nur die Normalkomponente ist dort stetig, die Tangentiale
 * springt um bis zu mu_r -- dieselbe Begruendung wie in
 * ``ema_analysis._curl_a``, wo es an einem Golden-Test haengt. */
function feldAus(g, A) {
  const { nx, ny, dx, dyv, rolle } = g;
  const Bx = new Float64Array(nx * ny), By = new Float64Array(nx * ny);
  const gl = (a, b) => rolle[a] === rolle[b];
  for (let j = 1; j < ny - 1; j++)
    for (let i = 1; i < nx - 1; i++) {
      const k = j * nx + i;
      const n = k + nx, s = k - nx, e = k + 1, w = k - 1;
      const dn = (dyv[j] + dyv[j + 1]) / 2, ds = (dyv[j] + dyv[j - 1]) / 2;
      Bx[k] = gl(k, n) && gl(k, s) ? (A[n] - A[s]) / (dn + ds)
            : gl(k, n) ? (A[n] - A[k]) / dn
            : gl(k, s) ? (A[k] - A[s]) / ds : (A[n] - A[s]) / (dn + ds);
      By[k] = -(gl(k, e) && gl(k, w) ? (A[e] - A[w]) / (2 * dx)
             : gl(k, e) ? (A[e] - A[k]) / dx
             : gl(k, w) ? (A[k] - A[w]) / dx : (A[e] - A[w]) / (2 * dx));
    }
  return { Bx, By };
}

/* Die Gitterzeile in der Mitte des ersten Luftspalts. Steckte in `eichung`
 * fest und wird jetzt auch von der geteilten Loesung gebraucht. */
function spaltZeile(g) {
  const sp = g.bnd.find((b) => b.art === "spalt");
  if (!sp) return -1;
  const ym = (sp.y0 + sp.y1) / 2;
  let j = 1, best = Infinity;
  for (let q = 1; q < g.ny - 1; q++) {
    const d = Math.abs(g.yc[q] - ym);
    if (d < best) { best = d; j = q; }
  }
  return j;
}

/* Die GRUNDWELLE der Normalkomponente im Spalt. Das Fenster ist genau eine
 * elektrische Periode breit, Harmonische 1 ist also die Grundwelle.
 *
 * Fuer das Verhaeltnis Anker/Magnet ist sie das richtige Mass und die Spitze
 * das falsche: die Spitze des Ankerfeldes sitzt ueber der Nut und ist eine
 * oertliche Zacke, waehrend gekoppelt wird, was als Grundwelle umlaeuft.
 * Gemessen: ueber die Spitze normiert kam bei reinem d-Strom nicht die
 * erwartete Summe heraus, ueber die Grundwelle schon. (Die EICHUNG bleibt
 * dagegen eine SPITZE -- die Arbeitsgerade `Br*hm/(hm+mu_r*kc*g)` ist ein
 * Spitzenwert. Zwei Masse fuer zwei Zwecke, und beide stehen hier.)
 */
function spaltGrundwelle(g, By, j) {
  let re = 0, im = 0;
  for (let i = 0; i < g.nx; i++) {
    const th = (2 * Math.PI * i) / g.nx;
    re += By[j * g.nx + i] * Math.cos(th);
    im += By[j * g.nx + i] * Math.sin(th);
  }
  return (2 * Math.hypot(re, im)) / g.nx;
}

function spaltSpitze(g, By, j) {
  let pk = 0;
  for (let i = 1; i < g.nx - 1; i++) pk = Math.max(pk, Math.abs(By[j * g.nx + i]));
  return pk;
}

/* Magnet und Anker GETRENNT loesen und zusammensetzen.
 *
 * `p.last` ist dadurch keine willkuerliche Zahl mehr, sondern der Ankeranteil
 * in PROZENT der Magnetspitze im Spalt -- eine Groesse, die sich aussprechen
 * laesst. 100 heisst: die Ankerrueckwirkung ist so stark wie der Magnet.
 * Gemessen wird sie, nicht gerechnet; es gibt also keinen Eichfaktor, der bei
 * einer anderen Geometrie danebenlaege (anders als `COIL_J_SCALE` im
 * 3-D-Pfad, das an EINER Maschine geeicht ist und das auch sagt).
 *
 * Kostet bei Last ZWEI Loeserlaeufe statt einem. Ohne Last ist es Ziffer fuer
 * Ziffer der alte Weg -- `g.Js` ist dann ueberall null und wird nicht geloest.
 */
function loeseFeld(p, g, iter) {
  const m = loeseCG(g, iter, 1e-11, g.J);
  const j = spaltZeile(g);
  const Bm = j < 0 ? null : feldAus(g, m.A).By;
  const pm = Bm ? spaltSpitze(g, Bm, j) : 0;        // fuer die Eichung
  const gm = Bm ? spaltGrundwelle(g, Bm, j) : 0;    // fuer das Verhaeltnis
  if (!p.last)
    return { A: m.A, relRest: m.relRest, schritte: m.schritte, anker: 0, pkMag: pm };
  const a = loeseCG(g, iter, 1e-11, g.Js);
  const ga = spaltGrundwelle(g, feldAus(g, a.A).By, j);
  if (!(ga > 0) || !(gm > 0))
    return { A: m.A, relRest: m.relRest, schritte: m.schritte, anker: 0,
             pkMag: pm, grund: "Ankerfeld nicht messbar" };
  const f = (p.last / 100) * (gm / ga);
  const A = new Float64Array(m.A.length);
  for (let k = 0; k < A.length; k++) A[k] = m.A[k] + f * a.A[k];
  // `pkMag` reist mit: geeicht wird am MAGNETanteil. Am Summenfeld geeicht
  // hinge der Massstab an der Last, und dann saehe jede Last gleich stark aus.
  return { A, relRest: Math.max(m.relRest, a.relRest),
           schritte: m.schritte + a.schritte, anker: p.last / 100, pkMag: pm };
}

/* Eichung: die Spitze der Normalkomponente des NUTLOSEN Feldes auf die Spitze
 * der Arbeitsgeraden. Dieselbe Groesse und dieselbe Begruendung wie im
 * Hausloeser -- der rohe Loeserwert haengt an der willkuerlichen Amplitude
 * von J. Gibt es keinen Magneten (Kaefig, Scheibenlaeufer ohne Erregung), wird
 * NICHT geeicht, und das Bild traegt dann keine Tesla-Achse, sondern eine
 * relative.
 *
 * **Zwei Dinge daran sind am 06.10.2026 berichtigt worden** (BEFUNDE.md), und
 * beide auf dem Python-Weg genauso -- `test_fluss.py` nagelt die Anker
 * gegeneinander fest:
 *
 * 1. Geeicht wird auf `BR * perm`, die **SPITZE** der Arbeitsgeraden, und
 *    NICHT auf `BR * perm * alpha`. Das `alpha` ist die Polbedeckung, also ein
 *    flussgewichteter MITTELWERT ueber die Polteilung; eine Spitze darauf zu
 *    pinnen rechnete alles um den Faktor `alpha` zu klein. Gemessen lag der
 *    Mehrschnitt dadurch 45 % unter dem Elmer-Ringsektor.
 * 2. Gemessen wird die Spitze des **nutlosen** Feldes. Die genutete Spitze ist
 *    kein Mass fuer den Fluss: ueber einem Zahn ist er gebuendelt, die lokale
 *    Spitze steigt durch die Nutung um gemessene 23 %, waehrend der Fluss je
 *    Pol faellt. Derselbe Befund steht im Hausloeser im Kopf von
 *    `ema_axial_fdm.carter`, das aus genau diesem Grund an der Grundwelle und
 *    ausdruecklich nicht an der Spitze rechnet.
 *
 * Gegenprobe, die das traegt: das nutlose Verhaeltnis Grundwelle/Spitze kommt
 * auf 1,2257 heraus, die Fourierreihe der Rechteckwelle fordert
 * `4/pi*sin(alpha*pi/2)` = 1,2381 -- 1,0 % auseinander. Der Loeser und die
 * Wellenform waren also in Ordnung, der ganze Fehler sass im Anker.
 *
 * Kostet EINEN zusaetzlichen Loeserlauf je Eichung -- im Mehrschnitt genau
 * einen insgesamt, weil dort ohnehin nur an der mittleren Scheibe geeicht wird.
 */
function eichung(p, g, By, pkVor, iter) {
  const perm = p.magd / (p.magd + MUR_MAG * KC * p.spalt);
  // Die SPITZE der Arbeitsgeraden, ohne Polbedeckung -- und sie ist der richtige
  // Anker, weil sie GENAU das misst, was die Formel beschreibt und nichts
  // sonst: `Br*perm` ist der Flachdachwert unter einem Magneten, unabhaengig
  // von Polbedeckung, Stueckelung und Nutung.
  //
  // Mit der GRUNDWELLE als Anker ging das schief, und der Test hat es gefangen:
  // eine Grundwelle traegt die Polbedeckung UND die Fugen der Stueckelung,
  // der Bezugslauf traegt sie auch, und im Verhaeltnis kuerzen sie sich heraus
  // -- gemessen fiel B1 mit 1-mm-Fugen nur noch von 1,1350 auf 1,1359 T (0,1 %)
  // statt um 11,7 %. Ein Regler, dessen Wirkung die Eichung wegnormiert, ist
  // derselbe Fehler wie der Staenderstrom vor dem Umbau.
  const bAn = BR * perm;
  const j = spaltZeile(g);
  if (j < 0) return { sf: 1, bAn: 0, geeicht: false };
  const hatMag = g.rolle.includes(2);
  if (!hatMag) {
    const pk0 = pkVor > 0 ? pkVor : spaltSpitze(g, By, j);
    return { sf: pk0 < 1e-30 ? 1 : 1 / pk0, bAn: 0, geeicht: false, jGap: j,
             pk: pk0 };
  }
  // Bezugsfall: derselbe Staender ohne Nutschlitze, gleiche Aufloesung.
  let pk = 0, nutlos = true;
  try {
    const g0 = feldGitter(p, g.nx, g.ny, true);
    const j0 = spaltZeile(g0);
    if (j0 >= 0) {
      const m0 = loeseCG(g0, iter || 400, 1e-11, g0.J);
      pk = spaltSpitze(g0, feldAus(g0, m0.A).By, j0);
    }
  } catch (e) { pk = 0; }
  if (!(pk > 1e-30)) {
    // Scheitert der Bezugsfall, wird die genutete Spitze genommen UND gesagt,
    // dass die Nutung dann in der Eichung steckt statt gemessen zu sein.
    pk = pkVor > 0 ? pkVor : spaltSpitze(g, By, j);
    nutlos = false;
  }
  if (!(pk > 1e-30)) return { sf: 1, bAn: 0, geeicht: false, jGap: j, pk: 0 };
  return { sf: bAn / pk, bAn, geeicht: true, jGap: j, pk,
           art: nutlos ? "spitze_nutlos" : "spitze_genutet",
           hinweis: nutlos ? null
                  : "Bezugsfall ohne Nut nicht loesbar -- die Nutung steckt in "
                    + "der Eichung statt gemessen zu sein" };
}

/* ---- Zeichnen ----------------------------------------------------------- */
function farbe(t) {                       // magma-aehnlich, 0..1
  const s = [[0,0,4],[40,11,84],[101,21,110],[159,42,99],[212,72,66],
             [245,125,21],[252,193,54],[252,253,191]];
  const u = Math.max(0, Math.min(0.999, t)) * (s.length - 1);
  const i = Math.floor(u), f = u - i, a = s[i], b = s[i + 1];
  return `rgb(${a[0]+(b[0]-a[0])*f|0},${a[1]+(b[1]-a[1])*f|0},${a[2]+(b[2]-a[2])*f|0})`;
}

function zeichneFeld(cv, p) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.clearRect(0, 0, W, H);
  const t0 = performance.now();
  const ny = Math.max(40, Math.min(220, +p.netz));
  const g0 = feldGitter(p, 8, 8);                       // nur fuer die Masse
  const nx = Math.round(ny * (g0.breite / g0.hGes));
  const g = feldGitter(p, nx, ny);
  // CG statt SOR: gemessen 451 Schritte / 100 ms gegen 5000 SOR-Durchgaenge /
  // 4 s bei gleichem Ergebnis (B1 0,77118 T). Der Operator ist SPD, und SORs
  // Rate haengt an der Kondition, die der mu-Sprung 1 -> 500 verdirbt.
  const loe = loeseFeld(p, g, +p.iter);
  const A = loe.A, rest = loe.relRest;
  const { Bx, By } = feldAus(g, A);
  const e = eichung(p, g, By, loe.pkMag, +p.iter);

  // Bildbereich
  const pad = 32;
  const s = Math.min((W - 2 * pad) / g.breite, (H - 2 * pad - 14) / g.hGes);
  const x0 = (W - s * g.breite) / 2, y0 = H - pad;
  const X = (u) => x0 + s * u, Y = (z) => y0 - s * z;

  // |B| als Flaeche
  // Deckel der Farbskala. Ohne ihn setzt die hoechste Zelle die Skala, und das
  // ist immer eine Eisenecke -- dann ist das halbe Bild weiss und man sieht
  // nichts. Dieselbe Entscheidung wie `IRON_B_SAT_DISPLAY` im Hauptwerkzeug:
  // ueber dem Saettigungsknie ist die lineare Rechnung ohnehin nicht mehr
  // zustaendig, also wird dort abgeschnitten und das gesagt.
  const Bm = new Float64Array(nx * g.ny);
  for (let k = 0; k < Bm.length; k++) Bm[k] = Math.hypot(Bx[k], By[k]) * Math.abs(e.sf);
  let deckel;
  if (e.geeicht) deckel = B_KNIE;
  else {                                   // ohne Eichung: 98. Perzentil
    const v = Array.from(Bm).sort((a, b) => a - b);
    deckel = Math.max(v[Math.floor(v.length * 0.98)], 1e-9);
  }
  const NY = g.ny;
  const img = ctx.createImageData(nx, NY);
  for (let j = 0; j < NY; j++)
    for (let i = 0; i < nx; i++) {
      const k = j * nx + i, o = ((NY - 1 - j) * nx + i) * 4;
      const t = Math.min(1, Bm[k] / deckel);
      const c = farbe(t);
      const m = c.match(/\d+/g);
      img.data[o] = +m[0]; img.data[o+1] = +m[1]; img.data[o+2] = +m[2];
      img.data[o+3] = 255;
    }
  const tmp = document.createElement("canvas");
  tmp.width = nx; tmp.height = NY; tmp.getContext("2d").putImageData(img, 0, 0);
  ctx.imageSmoothingEnabled = true;
  ctx.drawImage(tmp, X(0), Y(g.hGes), s * g.breite, s * g.hGes);

  // Feldlinien = Hoehenlinien von A (Marching Squares, grob aber ehrlich)
  let amin = Infinity, amax = -Infinity;
  for (const v of A) { if (v < amin) amin = v; if (v > amax) amax = v; }
  if (amax - amin > 1e-30) {
    ctx.strokeStyle = "#8fe3ff"; ctx.lineWidth = 1; ctx.globalAlpha = .8;
    const N = 26;
    for (let c = 1; c < N; c++) {
      const lv = amin + (amax - amin) * c / N;
      ctx.beginPath();
      for (let j = 0; j < NY - 1; j++)
        for (let i = 0; i < nx - 1; i++) {
          const a = A[j*nx+i], b = A[j*nx+i+1], d = A[(j+1)*nx+i];
          const px = (u) => X((i + u) * g.dx);
          const py = (v) => Y(g.yc[j] + v * (g.yc[j + 1] - g.yc[j]));
          if ((a < lv) !== (b < lv)) {
            const t = (lv - a) / (b - a);
            ctx.moveTo(px(t), py(0.5)); ctx.lineTo(px(t), py(0.5));
            ctx.rect(px(t) - .5, py(0.5) - .5, 1, 1);
          }
          if ((a < lv) !== (d < lv)) {
            const t = (lv - a) / (d - a);
            ctx.rect(px(0.5) - .5, py(t) - .5, 1, 1);
          }
        }
      ctx.stroke();
    }
    ctx.globalAlpha = 1;
  }

  // Schichtgrenzen und Beschriftung
  ctx.lineWidth = 1;
  ctx.strokeStyle = "rgba(190,205,225,.35)";
  for (const b of g.bnd) {
    ctx.beginPath(); ctx.moveTo(X(0), Y(b.y0)); ctx.lineTo(X(g.breite), Y(b.y0));
    ctx.stroke();
    ctx.fillStyle = "rgba(220,232,248,.75)"; ctx.font = "10px system-ui";
    ctx.textAlign = "left";
    ctx.fillText(b.art + (b.seite ? " (" + b.seite + ")" : ""),
                 X(0) + 4, Y((b.y0 + b.y1) / 2) + 3);
  }
  ctx.beginPath(); ctx.moveTo(X(0), Y(g.hGes)); ctx.lineTo(X(g.breite), Y(g.hGes));
  ctx.stroke();
  // Polgrenzen
  ctx.strokeStyle = "#e8a33d"; ctx.setLineDash([4, 3]);
  for (const u of [0, g.tauP, g.breite]) {
    ctx.beginPath(); ctx.moveTo(X(u), Y(0)); ctx.lineTo(X(u), Y(g.hGes)); ctx.stroke();
  }
  ctx.setLineDash([]);

  const ms = (performance.now() - t0) | 0;
  ctx.fillStyle = "#8a93a3"; ctx.font = "12px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`${nx}×${g.ny} · ${loe.schritte} CG-Schritte · ${ms} ms · ` +
               `rel. Rest ${rest.toExponential(1)} · y-Linien auf den ` +
               `Schichtgrenzen`, 10, 16);
  ctx.textAlign = "right";
  ctx.fillText(e.geeicht
      ? `|B| 0 … ${deckel.toFixed(2)} T (Sättigungsknie, darüber beschnitten) · ` +
        `Spalt geeicht auf ${e.bAn.toFixed(3)} T`
      : "ohne Magnet — relative Skala, keine Tesla", W - 10, 16);
  return { e, g, bmax: deckel, ms, rest };
}
