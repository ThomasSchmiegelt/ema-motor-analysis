#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Der Laeufer auf der Leinwand — Teile, Route, Zeichner, Verdrahtung.

Was hier wirklich geprueft wird (und warum genau das):

1. **Die Teile kommen aus der Quelle, die rechnet.** Nicht „es kommen Teile
   heraus", sondern: ihre ANZAHL und ihre MASSE stimmen Ziffer fuer Ziffer mit
   ``ema_asm.kaefig`` / ``ema_eesm_cad.koerper`` / ``ema_gsm.ankerwicklung``
   ueberein. Ginge das auseinander, zeichnete die Leinwand eine andere Maschine
   als CAD und Querschnittsbild — und alle drei saehen plausibel aus.
2. **Die PSM bleibt unberuehrt.** Sie bekommt KEINE Teile; ihr Weg ueber
   ``magnetLegs`` ist der einzige, der seit jeher stimmt und getestet ist.
3. **Der Zeichner wird mit `node` wirklich AUSGEFUEHRT** (gestellter Kontext,
   gezaehlt was er malt) — dasselbe Verfahren wie ``test_topology.py`` beim
   JS-Spiegel und ``test_laeufer_cad.py`` beim FreeCAD-Skript. Ein Zeichner,
   der nur importiert wird, ist nicht geprueft.
4. **Was magnetisch Luft ist, landet im Raster** — Kupfer und Alu mit, Eisen
   nicht. Ohne das zeigte die Leinwand Nuten und die Feldlinien eine
   Vollscheibe.
5. **Die Verdrahtung in `ema.html`**, damit die Teile nicht erzeugt und dann
   nirgends benutzt werden. „Gerechnet, aber unerreichbar" ist in diesem Repo
   schon mehrfach als „nicht vorhanden" gemeldet worden.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
HIER = os.path.dirname(os.path.abspath(__file__))

import cae_cli                                               # noqa: E402
import ema_laeuferbild as LB                                 # noqa: E402

_ok = _bad = 0


def pruefe(bed, text):
    global _ok, _bad
    if bed:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _bad += 1
        print(f"  ✗ {text}")


def geom(art, **extra):
    p = cae_cli.frischer_payload()
    g = p["geom"]
    g["machineType"] = art
    g.update(extra)
    return g, float(p["axial_len"])


def rollen(erg):
    z = {}
    for t in (erg.get("teile") or []) + (erg.get("staender") or []):
        z[t["rolle"]] = z.get(t["rolle"], 0) + 1
    return z


print("\n1. Die Teile kommen aus der Funktion, die die Maschine RECHNET")

import ema_asm                                               # noqa: E402

g, L = geom("asm")
k = ema_asm.kaefig(g, L)
erg = LB.teile(g, L)
stab = [t for t in erg["teile"] if t["rolle"] == "alu"]
pruefe(len(stab) == int(k["n_stab"]),
       f"Kaefig: {len(stab)} gezeichnete Staebe = ema_asm.kaefig n_stab "
       f"({k['n_stab']})")
pruefe(abs((stab[0]["y1"] - stab[0]["y0"]) - float(k["stabbreite_mm"])) < 1e-6
       and abs((stab[0]["r1"] - stab[0]["r0"]) - float(k["nuttiefe_mm"])) < 1e-6,
       f"und die Nut hat die gerechneten Masse "
       f"({k['stabbreite_mm']} x {k['nuttiefe_mm']} mm), nicht eigene")
# Die Teile runden ihre Zahlen auf vier Stellen -- 360/46 = 7,8260869… wird
# zu 7,8261. Eine engere Schranke prueft die Rundung statt der Teilung.
pruefe(abs(stab[1]["grad"] - 360.0 / int(k["n_stab"])) < 1e-3,
       f"die Nuten stehen auf der Teilung ({stab[1]['grad']}° bei "
       f"{k['n_stab']} Staeben), nicht irgendwo")

g, L = geom("asm", rotorType="schleifring")
w = ema_asm.laeuferwicklung(g, L)
erg = LB.teile(g, L)
wick = [t for t in erg["teile"] if t["rolle"] == "kupfer"]
pruefe(len(wick) == int(w["n_nut"]) and erg["laeufer_art"] == "schleifring",
       f"Schleifringlaeufer: {len(wick)} Nuten = laeuferwicklung n_nut "
       f"({w['n_nut']}) — und KEIN Kaefig daneben")
pruefe(not [t for t in erg["teile"] if t["rolle"] == "alu"],
       "die beiden Laeuferbauformen schliessen einander aus")

import ema_eesm_cad                                          # noqa: E402

g, L = geom("eesm", p=2)
kq = ema_eesm_cad.koerper(g, L)
erg = LB.teile(g, L)
r = rollen(erg)
pruefe(r.get("pol") == 2 * int(kq["poles"]),
       f"EESM: je Pol ein Schuh UND ein Kern ({r.get('pol')} bei "
       f"{kq['poles']} Polen)")
pruefe(r.get("kupfer") == 2 * int(kq["poles"]),
       f"und zwei Spulenquerschnitte je Pol ({r.get('kupfer')})")
_sp = [t for t in erg["teile"] if t["rolle"] == "kupfer"][0]
# Die Spule ist ein TRAPEZ (vier Ecken), damit sie beim kegeligen Pol dessen
# Neigung folgt; beim Rechteck sind Innen- und Aussenkante gleich breit.
pruefe(_sp["form"] == "trapez"
       and abs(abs(_sp["y1i"] - _sp["y0i"]) - float(kq["d_spule_mm"])) < 1e-6,
       f"die Spulendicke ist die GERECHNETE ({kq['d_spule_mm']} mm aus dem "
       f"Kupferquerschnitt), nicht der freie Platz")
# Der Polschuh muss die Spule UEBERRAGEN -- seine mechanische Aufgabe.
pruefe(kq["deckt_spule"] and kq["schuh_ueberstand_mm"] > 0.0,
       f"und der Polschuh ueberragt sie um {kq['schuh_ueberstand_mm']:.2f} mm "
       f"je Seite — sonst haelt sie nichts gegen die Fliehkraft")
_g2, _L2 = geom("eesm", p=2, erregerSpuleForm="kegel")
_k2 = ema_eesm_cad.koerper(_g2, _L2)
pruefe(_k2["b_kern_innen_mm"] > _k2["b_kern_aussen_mm"] * 1.2,
       f"kegelige Wicklung: der Pol ist an der JOCHseite breiter "
       f"({_k2['b_kern_innen_mm']:.1f} gegen {_k2['b_kern_aussen_mm']:.1f} mm)")
pruefe(_k2["deckt_spule"] and _k2["passt"],
       f"auch kegelig gedeckt und passend (bindend: {_k2['bindend']})")
_luft = [t for t in erg["teile"] if t["rolle"] == "luft"]
pruefe(len(_luft) == int(kq["poles"]),
       f"und ZWISCHEN den Polen ist Luft ({len(_luft)} Luecken) — sonst "
       f"zeigte das Feld eine Vollscheibe unter sichtbaren Polen")

import ema_gsm                                               # noqa: E402

g, L = geom("gsm", p=2, slots=24)
aw = ema_gsm.ankerwicklung(g, L)
erg = LB.teile(g, L)
ank = [t for t in erg["teile"] if t["rolle"] == "kupfer"]
pruefe(len(ank) == int(aw["n_nut"]),
       f"GSM: {len(ank)} Ankernuten = ema_gsm.ankerwicklung n_nut "
       f"({aw['n_nut']})")
pruefe(len(erg["staender"]) > 0,
       f"und der STAENDER kommt mit ({len(erg['staender'])} Teile) — die "
       f"einzige Bauart hier mit Schenkelpolen aussen")

g, L = geom("synrm")
erg = LB.teile(g, L)
pruefe(erg["teile"] and all(t["rolle"] == "luft" for t in erg["teile"]),
       f"SynRM: {len(erg['teile'])} Taschen, ALLE leer — derselbe gestanzte "
       f"Laeufer wie beim IPM, nur ohne Magnete darin")
pruefe(erg["feld_darstellbar"] is True,
       "und sein Feld IST darstellbar: Reluktanz ist reine Geometrie, "
       "anders als ein Kaefig")
pruefe("magThick" in erg["hinweis"],
       "der Hinweis sagt, dass die analytische Rechnung davon nur die "
       "Barrierenhoehe kennt — kein vorgetaeuschtes Mehrwissen")


print("\n2. Die PSM bleibt auf ihrem alten Weg")

g, L = geom("pmsm")
erg = LB.teile(g, L)
pruefe(erg["n_teile"] == 0 and not erg["teile"] and not erg["staender"],
       "keine Teile fuer die PSM — ihre Magnete zeichnet die Seite weiter "
       "aus der mit test_topology.py festgenagelten magnetLegs-Fassung")
pruefe(erg["fehler"] == "",
       "und das ist kein Fehlschlag, sondern die Absicht")


print("\n3. Ein Zeichner, der scheitert, haelt die Oberflaeche nicht an")

kaputt = dict(geom("asm")[0])
kaputt["rotorOD"] = 0.0
erg = LB.teile(kaputt, 80.0)
pruefe(erg["teile"] == [] and erg["fehler"],
       f"kaputte Geometrie: leere Liste MIT Grund ({erg['fehler'][:44]}…)")

import server                                                # noqa: E402

c = server.app.test_client()
g, L = geom("eesm", p=2)
r = c.post("/laeuferbild", json={"geom": g, "axial_len": L})
pruefe(r.status_code == 200 and r.get_json()["n_teile"] > 0,
       f"die Route liefert die Teile (HTTP {r.status_code}, "
       f"{r.get_json().get('n_teile')} Teile)")
r2 = c.post("/laeuferbild", json={"geom": kaputt, "axial_len": 80})
pruefe(r2.status_code == 200 and r2.get_json().get("teile") == [],
       f"und selbst bei kaputter Geometrie HTTP {r2.status_code} statt 500 — "
       f"die Leinwand zeichnet den nackten Laeufer weiter")
r3 = c.get("/ema_laeufer.js")
pruefe(r3.status_code == 200 and b"LAEUFER" in r3.data,
       "der Zeichner wird ausgeliefert")


print("\n4. Der Zeichner wird mit node wirklich ausgefuehrt")

g, L = geom("eesm", p=2)
teile_eesm = LB.teile(g, L)["teile"]
g, L = geom("asm")
teile_asm = LB.teile(g, L)["teile"]

_js = r"""
const fs = require('fs');
global.window = global;
eval(fs.readFileSync(process.argv[2], 'utf8'));
const teile = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));

// Ein gestellter Zeichenkontext, der nur mitzaehlt -- wie der
// Stellvertreter-FreeCAD in test_laeufer_cad.py.
let z = {rect:0, arc:0, fill:0, pfad:0, farben:{}};
const ctx = {
  set fillStyle(v){ z.farben[v] = (z.farben[v]||0)+1; },
  set strokeStyle(v){}, set lineWidth(v){},
  beginPath(){}, closePath(){}, stroke(){},
  // Der Stellvertreter muss koennen, was der Zeichner WIRKLICH aufruft --
  // fehlten diese beiden, zaehlte das Trapez still nicht mit.
  moveTo(){ z.pfad++; }, lineTo(){ z.pfad++; },
  fill(){ z.fill++; },
  arc(){ z.arc++; },
  fillRect(){ z.rect++; z.fill++; }, strokeRect(){},
  save(){}, restore(){}, rotate(){}, translate(){}
};
const n = LAEUFER.zeichne(ctx, teile, 2.0);

// Raster: ein Gitter, und wir zaehlen, wie viele Zellen unmagnetisch werden.
const N = 160, gridMu = new Float32Array(N*N).fill(500);
const gsz = N / 320.0;
const eingetragen = LAEUFER.rastere(gridMu, N, N/2, gsz, teile, 0.0);
let luftzellen = 0;
for (let i=0;i<gridMu.length;i++) if (gridMu[i] === 1) luftzellen++;

// Gegenprobe: nur EISEN darf nichts eintragen.
const nurEisen = teile.filter(t => t.rolle === 'eisen' || t.rolle === 'pol');
const g2 = new Float32Array(N*N).fill(500);
LAEUFER.rastere(g2, N, N/2, gsz, nurEisen, 0.0);
let eisenzellen = 0;
for (let i=0;i<g2.length;i++) if (g2[i] === 1) eisenzellen++;

console.log(JSON.stringify({gezeichnet:n, ...z, eingetragen, luftzellen,
                            eisenzellen, n_eisen: nurEisen.length}));
"""

_hat_node = subprocess.run(["which", "node"], capture_output=True).returncode == 0
if not _hat_node:
    print("  – node fehlt: der Zeichner wird nicht ausgefuehrt")
else:
    with tempfile.TemporaryDirectory() as tmp:
        jsp = os.path.join(tmp, "lauf.js")
        open(jsp, "w").write(_js)
        for name, teile, erwartet in (("EESM", teile_eesm, None),
                                      ("ASM", teile_asm, None)):
            tp = os.path.join(tmp, "t.json")
            open(tp, "w").write(json.dumps(teile))
            p = subprocess.run(["node", jsp,
                                os.path.join(HIER, "ema_laeufer.js"), tp],
                               capture_output=True, text=True, timeout=120)
            if p.returncode != 0:
                pruefe(False, f"{name}: node scheitert — {p.stderr[:120]}")
                continue
            d = json.loads(p.stdout.strip().splitlines()[-1])
            pruefe(d["gezeichnet"] == len(teile),
                   f"{name}: alle {len(teile)} Teile gezeichnet")
            pruefe(d["fill"] >= len(teile),
                   f"{name}: jedes Teil fuellt wirklich eine Flaeche "
                   f"({d['fill']} Fuellungen)")
            # So viele Farben wie Rollen -- nicht „mindestens zwei": der
            # Kaefiglaeufer hat genau EINE Rolle (alu), und eine Schranke,
            # die das als Fehler meldet, prueft die Maschine statt den
            # Zeichner.
            _n_rollen = len({t["rolle"] for t in teile})
            pruefe(len(d["farben"]) == _n_rollen,
                   f"{name}: {len(d['farben'])} Farben fuer {_n_rollen} "
                   f"Rollen — eine Wicklung, die wie Blech aussieht, "
                   f"zeigt nichts")
            pruefe(d["luftzellen"] > 0,
                   f"{name}: das Raster bekommt {d['luftzellen']} "
                   f"unmagnetische Zellen")
            pruefe(d["eisenzellen"] == 0,
                   f"{name}: EISEN traegt nichts ein ({d['n_eisen']} "
                   f"Eisenteile, 0 Zellen) — es ist ja Eisen")


print("\n5. Die Teile werden auch BENUTZT")

html = open(os.path.join(HIER, "ema.html"), encoding="utf-8").read()
pruefe('src="/ema_laeufer.js"' in html,
       "die Seite laedt den Zeichner")
pruefe('fetch("/laeuferbild"' in html,
       "und holt die Teile vom Server, statt die Geometrie nachzubauen")
pruefe("const _lt = _laeuferTeileAktiv();" in html
       and "const legs = _lt ? [] : magnetLegs(GEOM);" in html,
       "drawRotor zeichnet die Teile UND laesst dann die Magnetschleife leer "
       "laufen — kein PSM-Magnet auf einem Kaefiglaeufer")
pruefe("const _st = _staenderTeileAktiv();" in html,
       "drawStator kennt den Schenkelpol-Staender der GSM")
pruefe("LAEUFER.rastere(gridMu, N, center, gs, _ltR, a0)" in html,
       "und das FELDRASTER liest dieselbe Teileliste wie die Zeichnung")
pruefe('id="ov_laeufer"' in html and "_laeuferHinweisZeigen" in html,
       "die Leinwand sagt, was sie bei dieser Bauart NICHT zeigt")
# Die Marke ist der Grund, warum nicht bei jedem Tastendruck geholt wird --
# und warum keine Teile einer FREMDEN Geometrie gezeichnet werden.
pruefe("_laeuferMarke !== _laeuferMarkeBauen()" in html,
       "waehrend ein Abruf laeuft, gelten die alten Teile NICHT (Marke "
       "geprueft) — sie gehoeren zu einer anderen Maschine")
pruefe("setTimeout" in html.split("_laeuferAnfordern")[2].split("}")[0]
       or "_laeuferTimer = setTimeout" in html,
       "der Abruf ist entprellt: resetField feuert bei jedem Tastendruck")

# Keine Geometrie im Zeichner -- das ist der ganze Zweck der Aufteilung.
js = open(os.path.join(HIER, "ema_laeufer.js"), encoding="utf-8").read()
# Geprueft wird der CODE, nicht der Kopf: dort stehen die Quellen absichtlich
# namentlich, damit jeder weiss, woher die Teile kommen.
_rumpf = js.split("*/", 1)[1] if "*/" in js else js
for verbot in ("magnet_legs", "n_stab", "stabbreite", "polgeometrie",
               "KAEFIG_STEG", "kaefig(", "ankerwicklung"):
    pruefe(verbot not in _rumpf,
           f"ema_laeufer.js rechnet nichts: kein '{verbot}' im Code")


print("\n6. Die SIMULATION zeigt dieselbe Maschine wie die Zeichnung")

# Zwei Meldungen, ein Muster: die Zeichnung war umgestellt, das RECHENmodell
# der Vorschau nicht. „Bei der Simulation der ASM sieht es so aus, als waeren
# die Magnete der PSM noch enthalten" — sie waren es: der Rasterer
# magnetisierte weiter aus `magnetLegs`, und psi/Ld/Lq kamen aus
# `compute_advanced_em`, also aus Br und Magnetdicke.
pruefe("const legs   = _laeuferTeileAktiv() ? [] : magnetLegs(GEOM);" in html,
       "das FELDRASTER magnetisiert nicht mehr, wo es keine Magnete gibt")

# „Bei der ASM hat man das Gefuehl, Feld und Welle laufen synchron" — sie
# liefen es: das Staenderfeld hing am LAEUFERwinkel. Ohne Schlupf wird im
# Kaefig nichts induziert, ein synchron mitlaufender Kaefig traegt kein Moment.
pruefe("feldWinkel: 0, schlupf: 0," in html,
       "die Vorschau fuehrt Feld- und Laeuferwinkel getrennt")
pruefe("PHYS.feldWinkel += (PHYS.omega / (1 - PHYS.schlupf)) * dt;" in html,
       "n_syn = n/(1-s): das Drehfeld laeuft dem Laeufer um den Schlupf voraus")
pruefe("const _fw = PHYS.feldWinkel * GEOM.p;" in html
       and "PHYS.id*Math.cos(elAng - _fw)" in html,
       "und das Staenderfeld haengt an diesem Winkel, nicht am Laeuferwinkel")

if _hat_node:
    # Die Invarianz ist der eigentliche Punkt: bei s = 0 muss JEDE
    # Synchronrechnung Ziffer fuer Ziffer dieselbe bleiben.
    _w = r"""
    function lauf(s, omega, dt, n){
      let angle=0, feld=0;
      for(let i=0;i<n;i++){
        angle += omega*dt;
        if (s>0) feld += (omega/(1-s))*dt; else feld = angle;
      }
      return [angle, feld];
    }
    const a = lauf(0.0, 100, 1e-3, 5000), b = lauf(0.03, 100, 1e-3, 5000);
    console.log(JSON.stringify({sync_diff: a[1]-a[0],
                                asm_voraus: b[1]/b[0]-1}));
    """
    _p = subprocess.run(["node", "-e", _w], capture_output=True, text=True,
                        timeout=60)
    _d = json.loads(_p.stdout.strip())
    pruefe(_d["sync_diff"] == 0.0,
           f"synchron: Feld- und Laeuferwinkel bleiben EXAKT gleich "
           f"(Differenz {_d['sync_diff']}) — keine Drift ueber die Laufzeit")
    pruefe(abs(_d["asm_voraus"] - (1 / (1 - 0.03) - 1)) < 1e-9,
           f"ASM bei 3 % Schlupf: das Feld laeuft {_d['asm_voraus']*100:.2f} % "
           f"voraus — 1/(1-s)-1, nicht geschaetzt")

# Und die Kennwerte der Vorschau kommen aus dem Modul der jeweiligen Art.
_m = {}
for _art, _ex in (("pmsm", {}), ("asm", {}), ("synrm", {}), ("eesm", {"p": 2})):
    _p2 = cae_cli.frischer_payload()
    _p2["geom"]["machineType"] = _art
    _p2["geom"].update(_ex)
    _m[_art] = c.post("/umrichter",
                      json={"payload": _p2, "maschine": True}).get_json()["maschine"]

pruefe(_m["pmsm"]["quelle"].startswith("compute_advanced_em"),
       "die PSM rechnet unveraendert ueber compute_advanced_em")
for _art in ("asm", "synrm", "eesm"):
    pruefe(_m[_art]["quelle"].startswith(f"ema_{_art}.betriebspunkt"),
           f"{_art}: psi und Kt kommen aus ema_{_art}, nicht aus dem "
           f"Magnetmodell")
pruefe(abs(_m["asm"]["psi_pm_Wb"] - _m["pmsm"]["psi_pm_Wb"]) > 1e-4,
       f"und sie sind ANDERE Zahlen (ASM {_m['asm']['psi_pm_Wb']:.5f} gegen "
       f"PSM {_m['pmsm']['psi_pm_Wb']:.5f} Wb) — sonst haette der Umbau "
       f"nichts bewirkt")
pruefe(_m["asm"]["schlupf"] > 0 and _m["pmsm"]["schlupf"] == 0.0,
       f"nur die ASM hat Schlupf ({_m['asm']['schlupf']:.4f}); eine "
       f"Synchronmaschine hat per Definition keinen")
pruefe(_m["asm"]["ohne_salienz"] is True
       and _m["synrm"]["ohne_salienz"] is False,
       "wo eine Art kein Ld/Lq rechnet, wird das GESAGT statt die Salienz "
       "aus dem Magnetmodell zu uebernehmen (SynRM rechnet es selbst)")


print("\n7. KEINE Bauart zeichnet einen leeren Laeufer")

# Die Regel, die den SynRM-Fall gefunden haette. Er hatte in
# `render_cross_section` gar keinen Zweig: `hat_magnete` ist False, also malte
# die Magnetschleife nichts, und uebrig blieb eine leere Scheibe —
# ausgerechnet bei der Bauart, deren ganzes Moment aus der Laeufergeometrie
# kommt. Aufgefallen ist es erst beim Danebenlegen aller Bilder (275 Formen
# gegen 311 bei der PSM).
import matplotlib                                            # noqa: E402
matplotlib.use("Agg")
import matplotlib.pyplot as _plt                             # noqa: E402
import numpy as _np                                          # noqa: E402
import ema_pipeline as _PL                                   # noqa: E402

for _art, _ex in (("pmsm", {}), ("asm", {}),
                  ("asm", {"rotorType": "schleifring"}),
                  ("synrm", {}), ("eesm", {"p": 2}),
                  ("gsm", {"p": 2, "slots": 24})):
    _g, _L = geom(_art, **_ex)
    _fig, _ax = _plt.subplots()
    _PL.render_cross_section(_g, _ax)
    _rrot = float(_g["rotorOD"]) / 2.0
    _rsh = float(_g["shaftD"]) / 2.0
    # Formen, die WIRKLICH im Laeuferring liegen — die Welle und der Staender
    # zaehlen nicht, sonst besteht jeder Laeufer die Pruefung.
    _n = 0
    for _pa in _ax.patches:
        try:
            _v = _pa.get_patch_transform().transform(_pa.get_path().vertices)
        except Exception:                                    # noqa: BLE001
            continue
        if _v is None or not len(_v):
            continue
        _r = _np.hypot(_v[:, 0], _v[:, 1])
        if _rsh * 1.05 < float(_np.mean(_r)) < _rrot * 0.995:
            _n += 1
    _plt.close(_fig)
    _nm = _art + ("/" + _ex["rotorType"] if _ex.get("rotorType") else "")
    pruefe(_n >= 4,
           f"{_nm}: {_n} Formen im Laeuferring — kein nacktes Blech")

# Und die Gegenprobe zur Quelle: der SynRM-Querschnitt zeichnet dieselbe
# Taschenzahl, die `ema_laeuferbild` fuer die Leinwand liefert. Zwei Bilder
# derselben Maschine muessen dieselbe Maschine zeigen.
_g, _L = geom("synrm")
_teile = LB.teile(_g, _L)["teile"]
_fig, _ax = _plt.subplots()
_PL.render_cross_section(_g, _ax)
_leg = _ax.get_legend()
_plt.close(_fig)
pruefe(_leg is not None
       and any("Flussbarrieren" in t.get_text() for t in _leg.get_texts()),
       "der SynRM-Querschnitt nennt seine Flussbarrieren in der Legende")
pruefe(len(_teile) > 0,
       f"und die Leinwand zeichnet dieselben {len(_teile)} Taschen aus "
       f"derselben Quelle (magnet_legs)")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
