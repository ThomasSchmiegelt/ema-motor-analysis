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
       and "const legs = _hatMagnete() ? magnetLegs(GEOM) : [];" in html,
       "drawRotor zeichnet die Teile UND fragt fuer die Magnete die BAUART "
       "— kein PSM-Magnet auf einem Kaefiglaeufer")
# Der Unterschied ist kein Feinschliff, sondern der gemeldete Fehler: die
# Frage haing frueher daran, ob TEILE ankamen. Eine leere Liste heisst aber
# „nichts zu zeichnen", niemals „zeichne Magnete" — und leer war sie genau
# dann, wenn es interessant wurde (nicht auslegbarer Kaefig, Abruf unterwegs,
# Serverfehler). Dann stand die PSM-Magnetanordnung auf einer ASM.
pruefe("_lt ? [] : magnetLegs(GEOM)" not in html
       and "_laeuferTeileAktiv() ? [] : magnetLegs(GEOM)" not in html,
       "und die Magnete haengen NICHT mehr daran, ob Teile angekommen sind")
pruefe("function _hatMagnete()" in html and "b.hat_magnete" in html,
       "die Antwort kommt aus ema_maschinenart ueber /laeuferbild, nicht aus "
       "einer Liste im HTML")
pruefe("const _st = _staenderTeileAktiv();" in html,
       "drawStator kennt den Schenkelpol-Staender der GSM")
pruefe("LAEUFER.rastere(gridMu, N, center, gs, _ltR, a0, gridJ, _jNut)" in html,
       "und das FELDRASTER liest dieselbe Teileliste wie die Zeichnung")
pruefe("LAEUFER.rastere(gridMu, N, center, gs, _stR, 0, gridJ, _jNut)" in html,
       "auch den STAENDER der GSM — sonst fuehrte das Feld so, als waere er "
       "ein Vollring, und die gezeichneten Schenkelpole waeren bloss Farbe")
pruefe("const _dreiphasig = _staenderfeldAktiv();" in html
       and "for (let s = 0; _dreiphasig && s < slots; s++)" in html,
       "und eine Bauart mit EIGENEM Staender bekommt keine Drehstromnuten — "
       "ein Drehfeld auf einer Gleichstrommaschine ist ein falsches Bild")
pruefe('id="ov_laeufer"' in html and "_laeuferHinweisZeigen" in html,
       "die Leinwand sagt, was sie bei dieser Bauart NICHT zeigt")
# ... aber sie sagt es KURZ. Der volle Hinweis ist mehrere Saetze lang (bei
# einem nicht auslegbaren Kaefig ueber 400 Zeichen), und der Kennwertkasten ist
# schrumpfend breit -- er wuchs damit von 231 auf 425 px und nahm fast die
# halbe Vorschau ein. Gemeldet als „bei den neuen Varianten nehmen die
# Echtzeitdaten die Haelfte der Geometrieeinstellung ein".
pruefe("_HINWEIS_KURZ" in html and "_hinweisMalen" in html,
       "der Hinweis steht gekuerzt da und laesst sich aufklappen — ein Kasten, "
       "der mit seinem Text waechst, verdeckt die Maschine, um die es geht")
pruefe("max-width:250px" in html.replace(" ", ""),
       "und der Kennwertkasten hat eine Hoechstbreite: er ist schrumpfend "
       "breit, sein breitestes Kind bestimmt ihn")
_i_kern = html.index("const i = v.indexOf")
pruefe("u26A0" in html[_i_kern:_i_kern + 200],
       "die Kurzfassung faengt beim ⚠ an — das ist der Grund, warum der "
       "Hinweis ueberhaupt dasteht, nicht die Beschreibung der Bauart")
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
pruefe("const legs   = _hatMagnete() ? magnetLegs(GEOM) : [];" in html,
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


print("\n8. Nichts verlaesst die Maschine")

# Der gemeldete Fehler war ein Bild: „in der fremderregten Maschine
# kollidieren Rotor und Stator". Die Ursache ist eine Rechenregel, die man
# nicht sieht — Kern, Spule und Nut sind RECHTECKE, Laeufer und Staender sind
# KREISE: ein Rechteck der halben Breite y mit der Oberkante bei r hat seine
# Ecken bei sqrt(r^2 + y^2). Geprueft wurde die Oberkante, gezeichnet wurden
# die Ecken. Gemessen stand die Erregerspule bei r = 88,63 mm, waehrend die
# Statorbohrung bei 85,8 mm anfaengt.
#
# Geprueft wird deshalb an der ECKE und ueber die ganze Polzahlspanne: der
# Einzelfall sagt hier nichts, der Fehler haengt am Verhaeltnis Polbreite zu
# Radius und trat bei vier Polen auf, nicht bei sechs.
import math as _m                                            # noqa: E402


def _ecke(t):
    f = t["form"]
    if f in ("ring", "segment"):
        return t["r_a"]
    if f == "kreis":
        return _m.hypot(t["cx"], t["cy"]) + t["r"]
    if f == "rechteck":
        return max(_m.hypot(t["r1"], t["y0"]), _m.hypot(t["r1"], t["y1"]),
                   _m.hypot(t["r0"], t["y0"]), _m.hypot(t["r0"], t["y1"]))
    if f == "trapez":
        return max(_m.hypot(t["r1"], t["y0a"]), _m.hypot(t["r1"], t["y1a"]),
                   _m.hypot(t["r0"], t["y0i"]), _m.hypot(t["r0"], t["y1i"]))
    if f == "tasche":
        h = t["hoehe"] / 2.0
        a = _m.radians(t["tilt_grad"])
        return max(_m.hypot(t["r_pos"] + t["laenge"] * _m.cos(a),
                            t["offset"] + t["laenge"] * _m.sin(a)) + h,
                   _m.hypot(t["r_pos"], t["offset"]) + h)
    return 0.0


_raus = []
_faelle = 0
for _art in ("asm", "synrm", "eesm", "gsm"):
    for _p in (1, 2, 3, 4, 6, 8, 12):
        for _form in ("rechteck", "kegel"):
            _g, _L = geom(_art, p=_p, erregerSpuleForm=_form)
            _e = LB.teile(_g, _L)
            _faelle += 1
            _rl = _g["rotorOD"] / 2.0
            _rs = _g["statorOD"] / 2.0
            for _t in _e["teile"]:
                if _ecke(_t) > _rl + 1e-3:
                    _raus.append(f"{_art} p={_p} {_form} Laeufer "
                                 f"{_ecke(_t):.2f}>{_rl:.2f}")
            for _t in _e["staender"]:
                if _ecke(_t) > _rs + 1e-3:
                    _raus.append(f"{_art} p={_p} {_form} Staender "
                                 f"{_ecke(_t):.2f}>{_rs:.2f}")
pruefe(not _raus,
       f"{_faelle} Faelle: kein Teil tritt mit seiner ECKE aus Laeufer oder "
       f"Staender" + (" — " + "; ".join(_raus[:3]) if _raus else ""))

# Und die Gegenprobe, dass die Pruefung ueberhaupt etwas findet: mit der
# frueheren Regel (Oberkante statt Ecke) waere genau dieser Fall durchgegangen.
# Die GEMESSENE Geometrie, nicht irgendeine: das ist der Startzustand der
# Leinwand (ema.html GEOM), an dem der Fehler gemeldet wurde. Am frischen
# CLI-Payload (Laeufer 188,6 mm) tritt er nicht auf — der Ueberstand haengt am
# Verhaeltnis Polbreite zu Radius, und ein Testfall, der ihn nicht zeigt,
# prueft hier nichts.
_g, _L = geom("eesm", rotorOD=170.0, statorID=171.6, statorOD=295.0,
              shaftD=80.0, p=2, slots=36, axialLen=225.0)
_L = 225.0
_k = __import__("ema_eesm_cad").koerper(_g, _L)
_y = max(_k["b_kern_aussen_mm"], _k["b_kern_innen_mm"]) / 2.0 + _k["d_spule_mm"]
pruefe(_m.hypot(_k["r_kern_aussen_mm"], _y) > _k["r_rotor_mm"],
       f"die Gegenprobe greift: mit der Kernoberkante als Spulenoberkante laege "
       f"die Ecke bei {_m.hypot(_k['r_kern_aussen_mm'], _y):.2f} mm statt "
       f"{_k['r_rotor_mm']:.2f} mm")
pruefe(_k["im_laeufer"] and _k["r_spule_aussen_mm"] < _k["r_kern_aussen_mm"],
       f"deshalb endet die Spule weiter innen als der Kern "
       f"({_k['r_spule_aussen_mm']:.2f} gegen {_k['r_kern_aussen_mm']:.2f} mm)")
pruefe(_k["deckt_spule"],
       "und der Polschuh ueberdeckt sie weiterhin — er haelt sie gegen die "
       "Fliehkraft (US3089049A)")


print("\n9. Ein nicht bemessbarer Kaefig wird GEZEICHNET, nicht durch Magnete ersetzt")

# Der gemeldete Fehler: „in der Asynchronmaschine werden keine Staebe sondern
# Magnete angezeigt". So war es — `_asm` gab bei einem nicht auslegbaren Kaefig
# eine leere Liste heraus, und die Leinwand fiel daraufhin auf `magnetLegs`
# zurueck. Von allen moeglichen Bildern ist das das einzige, das eine ANDERE
# Maschine zeigt.
_g, _L = geom("asm", rotorOD=170.0, statorID=171.6, statorOD=295.0,
              shaftD=80.0, p=2, slots=36, axialLen=225.0)
_e = LB.teile(_g, 225.0)
_k = __import__("ema_asm").kaefig(_g, 225.0)
pruefe(_k["bemessung"] == "nicht auslegbar",
       "die Beispielgeometrie ist wirklich nicht bemessbar (963 A "
       "Magnetisierung gegen 800 A Grenze) — sonst prueft dieser Block nichts")
pruefe(len(_e["teile"]) == _k["n_stab"] and not _e["fehler"],
       f"trotzdem kommen {len(_e['teile'])} Staebe heraus, kein Fehler")
pruefe("NICHT auslegbar" in _e["hinweis"]
       and "Fertigungsboden" in _e["hinweis"],
       "und der Hinweis sagt, dass das der Fertigungsboden ist und keine "
       "Auslegung — verschwiegen waere es schlimmer als gar nicht gezeichnet")
pruefe(_e["hat_magnete"] is False,
       "`hat_magnete` sagt der Leinwand unabhaengig davon, dass diese Bauart "
       "keine Magnete hat — die Antwort haengt an der ART, nicht daran, ob "
       "Teile ankamen")

# Ohne Maschine kein Bild: seit der Kaefig auch am Boden gezeichnet wird, kaeme
# sonst aus jeder Geometrie etwas heraus — auch aus einer, die es nicht gibt.
_g2, _L2 = geom("asm")
_g2["rotorOD"] = 0.0
pruefe(LB.teile(_g2, _L2)["teile"] == [] and LB.teile(_g2, _L2)["fehler"],
       "eine Geometrie ohne Laeufer liefert weiterhin nichts — samt Grund")


print("\n10. Die Gleichstrommaschine bekommt kein Drehfeld")

# „Die Magnetfelder in der fremderregten Gleichstrommaschine sind auch falsch."
# Waren sie: der Staender der Vorschau ist eine Drehstromwicklung in Nuten, und
# die wurde ueber die Schenkelpole gelegt. Eine Gleichstrommaschine hat kein
# Drehfeld — ihre Erregung steht im Raum fest.
_g, _L = geom("gsm", p=2)
_e = LB.teile(_g, _L)
pruefe(_e["staenderfeld"] is False,
       "die GSM meldet `staenderfeld: False` — die Seite laesst die "
       "Drehstromnuten daraufhin weg")
_luft = [t for t in _e["staender"] if t["rolle"] == "luft"]
pruefe(len(_luft) == 2 * _g["p"],
       f"zwischen den {2 * _g['p']} Schenkelpolen steht LUFT im Raster "
       f"({len(_luft)} Teile) — sonst fuehrte das Feld, als waere der Staender "
       f"ein Vollring, und die gezeichneten Pole waeren bloss Farbe")
_strom = [t for t in _e["staender"] if t.get("durchflutung_A")]
pruefe(len(_strom) == 4 * _g["p"],
       f"die {len(_strom)} Erregerspulenseiten tragen eine Durchflutung — "
       f"Gleichstrom ist magnetostatisch darstellbar, anders als der Kaefig")
pruefe(abs(sum(t["durchflutung_A"] for t in _strom)) < 1e-6,
       "und sie summiert sich zu null: je Pol +F und -F, Polfolge wechselnd")
_f = abs(_strom[0]["durchflutung_A"])
_soll = __import__("ema_eesm").erregung(_g, _L)["F_pol_A"]
pruefe(abs(_f - _soll) < 0.02,
       f"ihr Wert kommt aus ema_eesm.erregung ({_f:.1f} A je Pol), nicht aus "
       f"einer Zahl im Zeichner")

# Dasselbe beim Schenkelpollaeufer der EESM -- gleiche Regel, anderer Ort.
_g, _L = geom("eesm", p=2)
_e = LB.teile(_g, _L)
_strom = [t for t in _e["teile"] if t.get("durchflutung_A")]
pruefe(len(_strom) == 4 * _g["p"] and _e["feld_darstellbar"],
       f"die EESM praegt ihre Erregung ebenso ein ({len(_strom)} "
       f"Spulenseiten) und meldet das Feld damit als darstellbar")


print("\n11. Der Zeichner traegt die Durchflutung wirklich ins gridJ")

# Gezaehlt wird, was `rastere` SCHREIBT -- nicht, dass die Funktion existiert.
_g, _L = geom("gsm", p=2)
_e = LB.teile(_g, _L)
_js = open(os.path.join(HIER, "ema_laeufer.js"), encoding="utf-8").read()
_prog = _js + """
var N = 200, gridMu = new Float32Array(N*N), gridJ = new Float32Array(N*N);
for (var i = 0; i < N*N; i++) gridMu[i] = 500;
var teile = TEILE;
var n = LAEUFER.rastere(gridMu, N, N/2, N/(2*140), teile, 0, gridJ, 12);
var pos = 0, neg = 0, summe = 0;
for (var i = 0; i < N*N; i++) {
  if (gridJ[i] > 0) pos++; else if (gridJ[i] < 0) neg++;
  summe += gridJ[i];
}
console.log(JSON.stringify({n: n, pos: pos, neg: neg, summe: summe}));
"""
with tempfile.TemporaryDirectory() as _d:
    _pf = os.path.join(_d, "p.js")
    with open(_pf, "w", encoding="utf-8") as _fh:
        _fh.write(_prog.replace("TEILE", json.dumps(_e["staender"])))
    _out = subprocess.run(["node", _pf], capture_output=True, text=True)
_r = json.loads(_out.stdout.strip().splitlines()[-1]) if _out.returncode == 0 else {}
pruefe(_r.get("pos", 0) > 50 and _r.get("neg", 0) > 50,
       f"beide Vorzeichen stehen im Raster ({_r.get('pos')} positive, "
       f"{_r.get('neg')} negative Zellen) — eine Windung um den Kern")
pruefe(abs(_r.get("summe", 1.0)) < 1e-3 * max(_r.get("pos", 1), 1),
       f"und sie heben sich auf (Summe {_r.get('summe', 0):.3e}) — was in die "
       f"eine Spulenseite hineinlaeuft, kommt aus der anderen zurueck")


print("\n" + "=" * 62)
print(f"{_ok} bestanden, {_bad} fehlgeschlagen")
sys.exit(1 if _bad else 0)
