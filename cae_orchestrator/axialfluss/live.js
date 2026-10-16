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
 *
 * Wo die FELDLINIEN stehen -- und wo nicht
 * ----------------------------------------
 * Gemeldet als: *„das gilt auch fuer die Live simulation. da moechte ich auch
 * magnetfeldlinien sehen."* Sie stehen in der **Abwicklung**, und zwar nicht
 * als Zugestaendnis, sondern weil das die eine Ebene ist, in der sie EXAKT
 * sind: der Schnitt loest `B = curl(A e_r)` in der theta-z-Ebene, und dort
 * sind die Hoehenlinien von A die Feldlinien -- kein Nachintegrieren eines
 * abgetasteten Vektorfeldes, keine Startpunktwahl, keine Schrittweite.
 *
 * **Auf der Scheibe von vorn gibt es keine**, und das ist eine Aussage ueber
 * das Modell und nicht ueber die Zeichnung: eine Scheibe traegt per
 * Konstruktion KEINE Radialkomponente (derselbe Grund, aus dem `rzBei` sein
 * Bild aus Bz und Bt baut). In der Stirnansicht liegen in der Ebene aber
 * gerade Br und Bt -- Linien liessen sich dort nur zeichnen, indem man Br
 * erfindet. Gezeigt wird deshalb B_z, also das Feld AUS der Ebene heraus, und
 * die Beschriftung sagt es.
 *
 * **Die Hoehenlinienwerte stehen EINMAL fest** (`aDeckel`), wie die Farbskala
 * und aus demselben Grund: je Rahmen neu gewaehlt aendert sich die Zahl der
 * Linien mit der Drehung, und dann saehe eine Aenderung der SKALA aus wie eine
 * Aenderung des FELDES. Gleich viele Linien heissen gleich viel Fluss zwischen
 * ihnen -- das ist der ganze Grund, warum man ein Linienbild lesen kann.
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
  // Der Deckel der HOEHENLINIEN -- dieselbe Ueberlegung wie bei der Farbskala
  // (s. Modulkopf): einmal fest, sonst waechst und schrumpft die Zahl der
  // Linien mit der Drehung und das Bild erzaehlt etwas ueber die Skala statt
  // ueber das Feld. Gemessen wird am MITTLEREN Schnitt, weil die Abwicklung
  // ihn zeigt.
  let aDeckel = 0;
  const kM = Math.floor(rahmen[0].nSch / 2);
  for (const e of rahmen)
    for (const v of e.scheiben[kM].A) {
      const q = Math.abs(v); if (q > aDeckel) aDeckel = q;
    }
  const gM = rahmen[0].scheiben[kM].g;
  _LIVE = { rahmen, nPos, per, tauP, mP, poles: p.poles,
            ri: p.ri, ro: p.ro, welle: p.welle,
            deckel: deckel > 1e-6 ? deckel : 1,
            aDeckel: aDeckel > 1e-30 ? aDeckel : 1,
            // Das Seitenverhaeltnis der Abwicklung. Sie wird MASSSTAEBLICH
            // gezeichnet: ein 1 mm dicker Luftspalt in einem 3,8:1 gequetschten
            // Streifen saehe wie 10 % der Bauhoehe aus, und Feldlinien in einem
            // verzerrten Bild treffen die falschen Winkel.
            aspekt: gM.breite / gM.hGes };
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
  // **Warum hier keine Feldlinien stehen, steht hier.** Eine Scheibe traegt
  // keine Radialkomponente; in DIESER Ebene liegen aber gerade Br und Bt.
  // Linien gaebe es nur, indem man Br erfindet -- und ein erfundenes
  // Linienbild ist schlimmer als keines, weil man es nicht nachmisst.
  ctx.textAlign = "center"; ctx.fillStyle = "#6f7785";
  ctx.fillText("Feldlinien: in der Abwicklung (hier steht B_z senkrecht zur Ebene)",
               W / 2, H - 7);
  ctx.textAlign = "left";
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

/* ---- Hoehenlinien von A = die Feldlinien, als Streckenzug ---------------
 *
 * Marching Squares, und zwar als STRECKEN und nicht als Punktwolke: die
 * Fassung in `feld.js` setzt je Kreuzung ein 1-px-Rechteck (`ctx.rect`), was
 * fuer ein Standbild reicht, in einer laufenden Anzeige aber flimmert und bei
 * schraegen Linien ausfranst.
 *
 * `lies(i, j)` gibt A am Knoten (i, j) -- die Entkopplung ist Absicht: der
 * Aufrufer kann damit eine starr gedrehte Spalte liefern, ohne dass hier etwas
 * von Drehung wissen muss.
 *
 * `luecke` ist die eine Spalte, an der die starre Drehung im Fenster umbricht;
 * dort sind die beiden Nachbarn KEINE Nachbarn, und eine Linie darueber waere
 * erfunden. Beide Seiten tragen dort den Dirichlet-Wert 0, Hoehenlinien
 * ungleich 0 kreuzen also ohnehin nicht -- ausgenommen wird sie trotzdem,
 * weil „trifft hier zufaellig nicht zu" keine Begruendung ist.
 */
function liveKonturen(ctx, nx, ny, lies, X, Y, stufen, luecke) {
  for (const lv of stufen) {
    ctx.beginPath();
    for (let j = 0; j < ny - 1; j++)
      for (let i = 0; i < nx - 1; i++) {
        if (i === luecke) continue;
        const a = lies(i, j), b = lies(i + 1, j),
              c = lies(i + 1, j + 1), d = lies(i, j + 1);
        const pk = [];
        if ((a < lv) !== (b < lv)) pk.push([X(i + (lv - a) / (b - a)), Y(j, 0)]);
        if ((b < lv) !== (c < lv)) pk.push([X(i + 1), Y(j, (lv - b) / (c - b))]);
        if ((d < lv) !== (c < lv)) pk.push([X(i + (lv - d) / (c - d)), Y(j + 1, 0)]);
        if ((a < lv) !== (d < lv)) pk.push([X(i), Y(j, (lv - a) / (d - a))]);
        if (pk.length === 2) {
          ctx.moveTo(pk[0][0], pk[0][1]); ctx.lineTo(pk[1][0], pk[1][1]);
        } else if (pk.length === 4) {
          // Sattelpunkt: zwei Strecken, Paarung willkuerlich aber stetig.
          ctx.moveTo(pk[0][0], pk[0][1]); ctx.lineTo(pk[3][0], pk[3][1]);
          ctx.moveTo(pk[1][0], pk[1][1]); ctx.lineTo(pk[2][0], pk[2][1]);
        }
      }
    ctx.stroke();
  }
}

/* Welche GELOESTE Spalte zeigt die Anzeige an der Stelle `i`?
 *
 * Die starre Drehung um `dreh` ist im Fenster eine Verschiebung um ganze
 * Spalten. Gerundet wird dabei auf die Zelle -- und das ist kein Zugestaendnis:
 * `dreh` ist immer ein Vielfaches der Periode und innerhalb einer Periode
 * KONSTANT, die fluessige Bewegung kommt aus den geloesten Stellungen. Ein
 * halber Zellversatz einmal je Periode ist unsichtbar und bewegt keinen Wert.
 */
function liveVersatz(folge, theta, nx) {
  const { dreh } = liveBei(folge, theta);
  const thW = 2 * (2 * Math.PI / folge.poles);
  return ((Math.round((dreh / thW) * nx) % nx) + nx) % nx;
}

/* ---- Der abgewickelte Streifen: GELOEST, mit Feldlinien -----------------
 *
 * Das ist das Bild, an dem man die Drehung ueberhaupt erkennt (die Zaehne
 * stehen, die Magnete wandern) -- und seit dem 11.10.2026 auch das, in dem die
 * FELDLINIEN stehen. Vorher war es gezeichnet und nicht geloest; gemeldet
 * wurde genau das: *„da moechte ich auch magnetfeldlinien sehen."*
 *
 * Es ist die richtige Stelle dafuer und nicht die bequemste: der Schnitt loest
 * `B = curl(A e_r)` in DIESER Ebene, also sind die Hoehenlinien von A hier die
 * Feldlinien -- exakt, nicht nachintegriert. Auf der Scheibe von vorn gibt es
 * keine (s. Modulkopf).
 *
 * **Gezeichnet wird massstaeblich**, nicht auf die Leinwand gequetscht: der
 * Luftspalt ist 1 mm in 65 mm Bauhoehe, und in einem 3,8:1 gestreckten
 * Streifen saehe er wie 10 % der Maschine aus -- Feldlinien darin traefen die
 * falschen Winkel, und gerade an ihrem Winkel liest man ab, wo Fluss quer
 * laeuft statt durch.
 *
 * **Struktur und Feld kommen aus EINEM Array** (`g.rolle` bzw. `s.A`, beide am
 * selben Gitter): eine daneben gezeichnete Geometrie koennte gegen das Feld
 * verrutschen, und das waere die stille Sorte Fehler -- beide Bilder sehen
 * richtig aus.
 */
function zeichneLiveAbwicklung(cv, p, folge, theta) {
  const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
  ctx.fillStyle = "#0c0e12"; ctx.fillRect(0, 0, W, H);
  const { erg } = liveBei(folge, theta);
  const kR = Math.floor(erg.nSch / 2), sc = erg.scheiben[kR], g = sc.g;
  const nx = g.nx, ny = g.ny;
  const iSh = liveVersatz(folge, theta, nx);
  const q = (i) => ((i - iSh) % nx + nx) % nx;     // Anzeige -> geloeste Spalte
  // Die Spalte, an der die Verschiebung umbricht (s. `liveKonturen`).
  let luecke = -1;
  for (let i = 0; i < nx - 1; i++) if (q(i + 1) !== (q(i) + 1) % nx) { luecke = i; break; }

  // Massstaeblich und zentriert einpassen.
  const pad = 14, obR = 13;
  const sk = Math.min((W - 2 * pad) / g.breite, (H - pad - obR) / g.hGes);
  const x0 = (W - sk * g.breite) / 2, y0 = H - (H - obR - sk * g.hGes) / 2;
  const X = (i) => x0 + sk * i * g.dx;             // Knoten -> Bildpunkt
  const Yk = (z) => y0 - sk * z;
  const Y = (j, f) => Yk(g.yc[j] + (f || 0) * (g.yc[Math.min(j + 1, ny - 1)] - g.yc[j]));

  // ── 1. Die Struktur, Spalte fuer Spalte aus `rolle` ─────────────────────
  // Zusammengefasst in Laeufe: eine Schicht ist ueber viele Zeilen dasselbe
  // Material, und ein Rechteck je Zelle waere bei 59x52 Zellen je Rahmen
  // dreitausend Aufrufe fuer ein Bild, das aus acht Baendern besteht.
  // Gedaempft: die Struktur ist hier die Kulisse, die Linien sind die Aussage.
  const FARBE = ["#0c0e12", "#3f4752", null, "#7a5631"];   // Luft, Eisen, Magnet, Leiter
  for (let i = 0; i < nx; i++) {
    const qi = q(i), xA = X(i), xB = X(i + 1);
    let j0 = 0;
    const kenn = (j) => {
      const k = j * nx + qi, r = g.rolle[k];
      if (r !== 2) return "r" + r;
      const my = g.My[k];
      return "m" + (Math.abs(my) < 1e-12 ? 0 : my > 0 ? 1 : -1);
    };
    let akt = kenn(0);
    for (let j = 1; j <= ny; j++) {
      const nk = j < ny ? kenn(j) : null;
      if (nk === akt) continue;
      let f;
      if (akt[0] === "m")
        f = akt === "m1" ? "#8e3b31" : akt === "m-1" ? "#2d5a86" : "#6d4a86";
      else f = FARBE[+akt.slice(1)] || "#0c0e12";
      ctx.fillStyle = f;
      ctx.fillRect(xA, Yk(g.yk[j]), Math.ceil(xB - xA) + 0.5,
                   sk * (g.yk[j] - g.yk[j0]));
      j0 = j; akt = nk;
    }
  }

  // ── 2. Die Schichtgrenzen, damit der Spalt ablesbar bleibt ─────────────
  ctx.strokeStyle = "rgba(190,205,225,.22)"; ctx.lineWidth = 1;
  for (const b of g.bnd) {
    ctx.beginPath();
    ctx.moveTo(X(0), Yk(b.y0)); ctx.lineTo(X(nx), Yk(b.y0)); ctx.stroke();
  }

  // ── 3. Die Feldlinien ──────────────────────────────────────────────────
  // Die Stufen stehen EINMAL fest (`folge.aDeckel`, s. Modulkopf): gleich
  // viele Linien heissen gleich viel Fluss zwischen ihnen, und nur deshalb
  // laesst sich ein Linienbild ueberhaupt lesen.
  const NST = 9, stufen = [];
  for (let k = 0; k < NST; k++) {
    const u = ((k + 0.5) / NST) * folge.aDeckel;
    stufen.push(u, -u);
  }
  ctx.strokeStyle = "#8fe3ff"; ctx.lineWidth = 1.1; ctx.globalAlpha = 0.9;
  liveKonturen(ctx, nx, ny, (i, j) => sc.A[j * nx + q(i)], X, Y, stufen, luecke);
  ctx.globalAlpha = 1;

  // Kurz halten: was das Bild IST, steht in der Bildunterschrift der Vorschau;
  // hier steht nur, was man sonst nirgends ablesen kann.
  ctx.fillStyle = "#8a93a3"; ctx.font = "10px system-ui"; ctx.textAlign = "left";
  ctx.fillText(`r = ${sc.r.toFixed(0)} mm · Zähne stehen, Magnete wandern`, 6, 10);
  ctx.textAlign = "right";
  ctx.fillText(`${2 * NST} Feldlinien · feste Stufen`, W - 6, 10);
}
