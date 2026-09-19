/* ema_laeufer.js — den Laeufer zeichnen, der NICHT aus Magneten besteht.
 *
 * Warum diese Datei so duenn ist
 * ------------------------------
 * Hier steht **keine Geometrie**. Die Teile kommen fertig aus
 * `ema_laeuferbild.py` (Route `POST /laeuferbild`), das sie wiederum aus den
 * Funktionen holt, die die Maschine RECHNEN — `ema_asm.kaefig`,
 * `ema_eesm_cad.koerper`, `ema_gsm.ankerwicklung`, `ema_topology.magnet_legs`.
 *
 * Das ist die ganze Absicht: `ema.html` haelt mit `magnetLegs` bereits EINE
 * handgespiegelte Fassung einer Python-Funktion, und `CLAUDE.md` nennt sie die
 * gefaehrlichste Stelle im Werkzeug (`test_topology.py` haelt sie mit `node`
 * zusammen). Kaefig, Schenkelpol und Anker haetten daraus vier weitere
 * Abschriften gemacht, jede mit eigenem Spiegeltest. Stattdessen: Python
 * schickt Zahlen, JavaScript malt.
 *
 * Die PSM bleibt ausdruecklich auf ihrem alten Weg — `drawRotor` zeichnet ihre
 * Magnete weiter aus `magnetLegs`. An der einen Darstellung zu drehen, die seit
 * jeher stimmt und getestet ist, waere Risiko ohne Gewinn.
 *
 * Zwei Aufgaben, eine Quelle
 * --------------------------
 *   `zeichne`  — die Leinwand
 *   `rastere`  — das Feldraster der Live-Vorschau (alles Unmagnetische, s. u.)
 *
 * Beide lesen DIESELBE Teileliste. Ohne das zeigte die Leinwand Schenkelpole,
 * waehrend die Feldlinien sich verhielten, als waere der Laeufer eine
 * Vollscheibe — ein Bild, das sich selbst widerspricht.
 *
 * Was gerastert wird und was nicht
 * --------------------------------
 * Eingetragen wird alles **Unmagnetische**: `luft`, `kupfer` und `alu`. Das
 * ist keine Vereinfachung, sondern die Sache selbst — Kupfer und Aluminium
 * haben mu_r ~ 1, die Nut ist magnetisch Luft, ob ein Stab darin liegt oder
 * nicht. Ohne das zeigte die Leinwand Kaefignuten und das Feld verhielte sich,
 * als waere der Laeufer eine Vollscheibe.
 *
 * Der STROM wird eingetragen, wo er GLEICHSTROM ist: ein Teil mit
 * `durchflutung_A` (Erregerspule der EESM, Feldspule der GSM) landet als
 * Quelle im `gridJ`. Das ist keine Erweiterung des Modells, sondern sein
 * eigentlicher Fall — ein magnetostatischer Loeser kann eine eingepraegte
 * GLEICHdurchflutung exakt. Nicht darstellbar bleibt, was zeitabhaengig
 * ist: der Kaefigstab (kein sigma, kein dA/dt) und die kommutierte
 * Ankerdurchflutung, die der Kommutator im Raum festhaelt. Genau das
 * meldet `feld_darstellbar: false`, und die Seite schreibt es hin.
 */

(function (global) {
  "use strict";

  // Dieselben Farben wie `ema_pipeline.render_cross_section`. Wer sie aendert,
  // aendert sie dort mit -- Querschnittsbild und Leinwand sind fuer den, der
  // davorsitzt, dasselbe Bauteil.
  var FARBE = {
    eisen:  { fill: "#2d3748", rand: "#4a5568" },
    pol:    { fill: "#3c4a60", rand: "#6b7c99" },
    luft:   { fill: "#11131c", rand: "#11131c" },
    kupfer: { fill: "#b87333", rand: "#e0a060" },
    alu:    { fill: "#b0b4bb", rand: "#dfe3e8" }
  };
  var GRAD = Math.PI / 180;

  function farbe(rolle) { return FARBE[rolle] || FARBE.eisen; }

  /* Ein Teil zeichnen. `s` = Bildpunkte je Millimeter; der Kontext ist bereits
   * auf die Wellenachse verschoben und um den Rotorwinkel gedreht. */
  function _teil(ctx, t, s) {
    var f = farbe(t.rolle);
    ctx.fillStyle = f.fill;
    ctx.strokeStyle = f.rand;
    ctx.lineWidth = 1;

    if (t.form === "ring") {
      ctx.beginPath();
      ctx.arc(0, 0, t.r_a * s, 0, 2 * Math.PI);
      ctx.arc(0, 0, t.r_i * s, 0, 2 * Math.PI, true);
      ctx.fill();
      return;
    }
    if (t.form === "kreis") {
      ctx.beginPath();
      ctx.arc(t.cx * s, t.cy * s, t.r * s, 0, 2 * Math.PI);
      ctx.fill(); ctx.stroke();
      return;
    }
    if (t.form === "segment") {
      var a0 = (t.grad - t.halb) * GRAD, a1 = (t.grad + t.halb) * GRAD;
      ctx.beginPath();
      ctx.arc(0, 0, t.r_a * s, a0, a1, false);
      ctx.arc(0, 0, (t.r_a - t.dicke) * s, a1, a0, true);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      return;
    }
    if (t.form === "rechteck") {
      ctx.save();
      ctx.rotate(t.grad * GRAD);
      ctx.fillRect(t.r0 * s, t.y0 * s, (t.r1 - t.r0) * s, (t.y1 - t.y0) * s);
      ctx.strokeRect(t.r0 * s, t.y0 * s, (t.r1 - t.r0) * s, (t.y1 - t.y0) * s);
      ctx.restore();
      return;
    }
    if (t.form === "trapez") {
      // Vier Ecken: innen (r0) und aussen (r1) verschieden breit -- der
      // kegelige Schenkelpol und die Spule, die seiner Neigung folgt. Bei der
      // Rechteckwicklung sind beide Kanten gleich und es entsteht dasselbe
      // Rechteck wie zuvor.
      ctx.save();
      ctx.rotate(t.grad * GRAD);
      ctx.beginPath();
      ctx.moveTo(t.r0 * s, t.y0i * s);
      ctx.lineTo(t.r1 * s, t.y0a * s);
      ctx.lineTo(t.r1 * s, t.y1a * s);
      ctx.lineTo(t.r0 * s, t.y1i * s);
      ctx.closePath();
      ctx.fill(); ctx.stroke();
      ctx.restore();
      return;
    }
    if (t.form === "tasche") {
      // Langloch im Schenkelrahmen -- dieselbe Form wie die IPM-Tasche in
      // `drawRotor`: Ursprung am inneren Ende, um `tilt` gedreht, zwei
      // Halbkreiskappen. Beim Reluktanzlaeufer bleibt sie leer.
      ctx.save();
      ctx.rotate(t.grad * GRAD);
      ctx.translate(t.r_pos * s, t.offset * s);
      ctx.rotate(t.tilt_grad * GRAD);
      var L = t.laenge * s, r = (t.hoehe / 2) * s;
      ctx.fillRect(0, -r, L, 2 * r);
      ctx.beginPath(); ctx.arc(0, 0, r, 0, 2 * Math.PI); ctx.fill();
      ctx.beginPath(); ctx.arc(L, 0, r, 0, 2 * Math.PI); ctx.fill();
      ctx.restore();
      return;
    }
  }

  /* Alle Teile zeichnen. Die Reihenfolge ist die der Liste: Python legt das
   * Joch zuerst und die Spulen zuletzt, damit nichts Wichtiges uebermalt wird. */
  function zeichne(ctx, teile, s) {
    if (!ctx || !teile || !teile.length) return 0;
    for (var i = 0; i < teile.length; i++) _teil(ctx, teile[i], s);
    return teile.length;
  }

  /* --- Feldraster -------------------------------------------------------- */

  /* Waehrend eines Stempels: hier werden die getroffenen Zellen gesammelt.
   *
   * Eine Karte (kein Feld), weil dieselbe Zelle mehrfach getroffen wird -- die
   * Abtastung laeuft in halben Zellen, und eine doppelt gezaehlte Zelle machte
   * die Stromdichte darin falsch. Modulweit statt als Parameter, damit die
   * `_setz`-Aufrufe in `_stempel` unveraendert bleiben. */
  var _SAMMLER = null;

  /* Eine Gitterzelle setzen, wenn sie im Gitter liegt. */
  function _setz(gridMu, N, ix, iy, wert) {
    if (ix >= 0 && ix < N && iy >= 0 && iy < N) {
      var k = iy * N + ix;
      gridMu[k] = wert;
      if (_SAMMLER) _SAMMLER[k] = 1;
    }
  }

  /* Ein Teil in das mu-Gitter stempeln.
   *
   * Abgetastet wird der KOERPER (nicht sein Rand), in Schritten von einer
   * halben Gitterzelle: gerechnet wird in Millimetern und erst am Schluss auf
   * das Gitter umgerechnet, damit ein Teil bei jeder Aufloesung dieselbe
   * Flaeche belegt. Der Reihe nach ueber Radius und Breite zu laufen ist hier
   * billiger als eine Umhuellende zu bilden -- es sind wenige Dutzend Teile,
   * und derselbe Ansatz steht schon im Flussbarrieren-Block von `ema.html`.
   */
  function _stempel(gridMu, N, center, gs, t, a0, wert) {
    var schritt = 0.5 / Math.max(gs, 1e-9);   // eine halbe Zelle, in mm
    var i, j, r, w, a, ca, sa, x, y;

    if (t.form === "ring") {
      for (r = t.r_i; r <= t.r_a; r += schritt) {
        var n = Math.max(8, Math.ceil(2 * Math.PI * r / schritt));
        for (i = 0; i < n; i++) {
          a = a0 + 2 * Math.PI * i / n;
          _setz(gridMu, N, Math.floor(center + r * Math.cos(a) * gs),
                Math.floor(center + r * Math.sin(a) * gs), wert);
        }
      }
      return;
    }
    if (t.form === "segment") {
      var g0 = (t.grad - t.halb) * GRAD, g1 = (t.grad + t.halb) * GRAD;
      for (r = t.r_a - t.dicke; r <= t.r_a; r += schritt) {
        var m = Math.max(4, Math.ceil(r * (g1 - g0) / schritt));
        for (i = 0; i <= m; i++) {
          a = a0 + g0 + (g1 - g0) * i / m;
          _setz(gridMu, N, Math.floor(center + r * Math.cos(a) * gs),
                Math.floor(center + r * Math.sin(a) * gs), wert);
        }
      }
      return;
    }
    if (t.form === "rechteck") {
      a = a0 + t.grad * GRAD; ca = Math.cos(a); sa = Math.sin(a);
      for (r = t.r0; r <= t.r1; r += schritt) {
        for (w = t.y0; w <= t.y1; w += schritt) {
          _setz(gridMu, N, Math.floor(center + (r * ca - w * sa) * gs),
                Math.floor(center + (r * sa + w * ca) * gs), wert);
        }
      }
      return;
    }
    if (t.form === "trapez") {
      a = a0 + t.grad * GRAD; ca = Math.cos(a); sa = Math.sin(a);
      for (r = t.r0; r <= t.r1; r += schritt) {
        // Die beiden Kanten linear ueber den Radius ueberblenden -- dieselbe
        // Form, die `_teil` zeichnet, damit Bild und Feld uebereinstimmen.
        var u = (r - t.r0) / Math.max(t.r1 - t.r0, 1e-9);
        var wa = t.y0i + (t.y0a - t.y0i) * u;
        var wb = t.y1i + (t.y1a - t.y1i) * u;
        for (w = wa; w <= wb; w += schritt) {
          _setz(gridMu, N, Math.floor(center + (r * ca - w * sa) * gs),
                Math.floor(center + (r * sa + w * ca) * gs), wert);
        }
      }
      return;
    }
    if (t.form === "tasche") {
      a = a0 + t.grad * GRAD; ca = Math.cos(a); sa = Math.sin(a);
      var tc = Math.cos(t.tilt_grad * GRAD), ts = Math.sin(t.tilt_grad * GRAD);
      var hr = t.hoehe / 2;
      for (i = -hr; i <= t.laenge + hr; i += schritt) {
        for (j = -hr; j <= hr; j += schritt) {
          // Kappen: ausserhalb der geraden Strecke gilt der Kreisradius.
          if (i < 0 && (i * i + j * j) > hr * hr) continue;
          if (i > t.laenge) {
            var d = i - t.laenge;
            if ((d * d + j * j) > hr * hr) continue;
          }
          // Schenkelrahmen -> Polrahmen -> Laeuferrahmen.
          x = t.r_pos + i * tc - j * ts;
          y = t.offset + i * ts + j * tc;
          _setz(gridMu, N, Math.floor(center + (x * ca - y * sa) * gs),
                Math.floor(center + (x * sa + y * ca) * gs), wert);
        }
      }
    }
  }

  // Was magnetisch Luft IST. Kupfer und Aluminium gehoeren dazu: mu_r ~ 1.
  var UNMAGNETISCH = { luft: 1, kupfer: 1, alu: 1 };

  /* Das Unmagnetische der Teile ins Raster eintragen.
   *
   * `a0` ist der Rotorwinkel: der Laeufer dreht sich, die Teile drehen mit --
   * genauso, wie es der Flussbarrieren-Block in `ema.html` seit jeher macht.
   * Gibt die Zahl der eingetragenen Teile zurueck, damit die Seite sagen kann,
   * ob ueberhaupt etwas gewirkt hat.
   */
  function rastere(gridMu, N, center, gs, teile, a0, gridJ, jNut) {
    if (!gridMu || !teile || !teile.length) return 0;
    var n = 0;
    for (var i = 0; i < teile.length; i++) {
      var t = teile[i];
      if (!UNMAGNETISCH[t.rolle]) continue;
      var f = gridJ ? +(t.durchflutung_A || 0) : 0;
      _SAMMLER = f ? {} : null;
      _stempel(gridMu, N, center, gs, t, a0 || 0, 1);
      if (f) {
        var ks = Object.keys(_SAMMLER), nk = ks.length;
        // Dieselbe Rechnung wie die Staendernut in `ema.html`: dort steht je
        // Zelle der NUTstrom, die Durchflutung der Nut ist also
        // `I * Zellen_je_Nut`. Damit eine Spule mit F Amperewindungen im
        // selben Bild dasselbe Gewicht bekommt, traegt jede ihrer Zellen
        // `F / Zellen_der_Spule * Zellen_je_Nut`. Das Verhaeltnis Spule:Nut
        // ist dann genau F:I -- physikalisch, nicht geschaetzt.
        var wert = nk ? (f / nk) * (jNut || 0) : 0;
        for (var q = 0; q < nk; q++) gridJ[ks[q] | 0] = wert;
      }
      _SAMMLER = null;
      n++;
    }
    return n;
  }

  global.LAEUFER = { zeichne: zeichne, rastere: rastere, FARBE: FARBE };
})(typeof window !== "undefined" ? window : globalThis);
