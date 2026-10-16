"""Pruefungen des Flusswegs (``ema_fluss``, Stufe 0 aus ``AXIALFLUSS.md``).

Die erste Pruefung ist die wichtigste und hat nichts mit Axialfluss zu tun:
**bewegt sich am Radialfluss etwas?** ``flaechen()`` legt zwei Formeln
zusammen, die bisher an zwei Stellen standen (``compute_performance`` und
``rated_torque``) -- eine Umstellung, keine Aenderung. Wenn sie eine Aenderung
waere, verschoebe sie die Kennzahlen jedes bestehenden Projekts, und zwar um
Promille: nicht genug, um aufzufallen, genug, um Vergleiche wertlos zu machen.
Deshalb wird ziffernweise verglichen und nicht mit Toleranz.

Danach das Tor. Alle Faelle, gegen die hier geprueft wird, waeren ohne Absturz
durchgelaufen und haetten eine plausible Zahl geliefert:

* ``rated_torque`` legt ``2*sigma*pi*R^2*L`` auf eine Scheibe -- eine
  Zylinderformel auf eine Geometrie ohne Zylinder;
* ``psi_pm`` nimmt ``R_gap*L`` fuer einen Ringraum (gemessen Faktor 1,49);
* das Raster baut ``R = hypot(X, Y)``-Ringe, das 3-D-Netz Scheiben EINES
  Querschnitts -- den es axial nicht gibt.

Und die Probe, die den Kern festnagelt: Fluss waechst mit r^1, Moment mit r^2.
Radial fallen beide auf einen Radius zusammen, axial nicht. Ein Ersatzradius
kann nur eines von beiden treffen, und ein Test, der das nicht prueft, laesst
genau den Fehler durch, um den es geht.
"""

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_analysis
import ema_fluss as F
import ema_text2ema as T
import ema_thermal

_ok, _fehl = 0, 0


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def vorgabe(**auf):
    g = {k: v.get("def") for k, v in T.SCHEMA.items() if v.get("geom")}
    g["axialLen"] = T.SCHEMA["axialLen"]["def"]
    g.update(auf)
    return g


print("\n— 1. Invarianz: am Radialfluss darf sich NICHTS bewegen —")

g = vorgabe()
L_mm = g["axialLen"]
f = F.flaechen(g, L_mm)

# Genau die Ausdruecke, die compute_performance und rated_torque heute bilden.
soll_fluss = ema_analysis.r_gap_m(g) * ema_analysis.stapellaenge_m(g, L_mm)
soll_mom = (g["rotorOD"] / 2 / 1000) ** 2 * (L_mm / 1000)
pruefe(f["a_fluss_m2"] == soll_fluss,
       f"a_fluss ist ziffernweise r_gap_m*L  ({f['a_fluss_m2']!r})")
pruefe(f["a_moment_m3"] == soll_mom,
       f"a_moment ist ziffernweise (rotorOD/2)^2*L  ({f['a_moment_m3']!r})")

# Und durch die beiden Kennzahlen hindurch.
B, p, rpm = 0.63, int(g["p"]), 1000.0
perf = ema_analysis.compute_performance(g, B, rpm, L_mm)
psi_aus_flaechen = p * (2 / math.pi) * B * f["a_fluss_m2"]
pruefe(round(psi_aus_flaechen, 4) == perf["psi_pm_Wb"],
       f"psi_pm aus flaechen() == compute_performance ({perf['psi_pm_Wb']} Wb)")

t_haus = ema_thermal.rated_torque(g, L_mm, "water")
t_flaechen = 2 * math.pi * 40e3 * f["a_moment_m3"]
pruefe(abs(t_flaechen - t_haus) < 1e-9,
       f"T = 2*pi*sigma*a_moment == rated_torque ({t_haus:.4f} Nm, water)")
pruefe(round(t_haus, 1) == 178.8,
       f"und das ist die Zahl aus dem Docstring von mit_umrichtergrenze "
       f"({t_haus:.1f} Nm)")

# Die Bauform darf die Invarianz nicht aufheben.
for pos in ("innen", "aussen"):
    ga = vorgabe(rotorPosition=pos)
    if pos == "aussen":
        ga.update(statorOD=180, statorID=60, rotorID=181.4, rotorOD=200, shaftD=40)
    fa = F.flaechen(ga, L_mm)
    pruefe(fa["a_fluss_m2"] == ema_analysis.r_gap_m(ga)
           * ema_analysis.stapellaenge_m(ga, L_mm),
           f"auch beim {pos.capitalize()}laeufer unveraendert")

print("\n— 2. Das Tor: kein Axialfluss unter fremdem Namen —")

# Stufe 0 hatte hier `== ()`. Seit Stufe 1 (05.10.2026) traegt `analytisch`
# den Axialfluss ueber `ema_axial`; die Tabelle ist der Sinn des Moduls, und ein
# Test, der sie auf leer festnagelt, verhindert genau den Ausbau, fuer den das
# Tor gebaut wurde. Festgenagelt wird statt dessen, WAS NICHT traegt.
# Seit dem 07.10.2026 traegt auch `em3d` -- aber ueber `ema_axial_em3d`
# (anti-periodischer Ringsektor), nicht ueber den magnetostatischen Vollmotor.
# Dieselbe Unterscheidung wie bei `feld`, und der Grund steht in `em3d_weg`.
pruefe(set(F.STUFEN_AXIAL) == {"analytisch", "feld", "em3d", "cad", "thermik", "zyklus"},
       "STUFEN_AXIAL traegt analytisch, feld, em3d, cad, thermik und zyklus — jedes auf SEINEM Weg")
# Die Gegenprobe ist die eigentliche Aussage: was NICHT getragen wird,
# muss abgewiesen werden -- sonst waere die Liste eine Behauptung.
for _nicht in ("struktur",):
    pruefe(_nicht not in F.STUFEN_AXIAL,
           f"{_nicht} traegt den Axialfluss NICHT — dort gibt es keine "
           f"Scheibengeometrie")
pruefe(F.flussweg(vorgabe()) == "radial" and F.flussweg({}) == "radial"
       and F.flussweg(None) == "radial",
       "ohne Angabe gilt radial (Vorgabe, nicht Rateschritt)")
pruefe(F.flussweg({"geom": {"fluxPath": "axial"}}) == "axial"
       and F.flussweg({"fluxPath": "AFPM"}) == "axial",
       "axial wird in geom UND oben im Payload erkannt, auch als Synonym")

ax = {"geom": vorgabe(fluxPath="axial", axialAktivOD=260.0)}
pruefe(F.pruefe_flussweg(ax, "analytisch") == "axial",
       "'analytisch' laeuft durch (ema_axial rechnet sie)")
# 'feld' traegt seit Stufe 2 -- aber auf einem EIGENEN Loeser. Die Unterscheidung
# ist die von ema_maschinenart: "traegt die Stufe" ist nicht "geht DIESEN Weg".
pruefe(F.pruefe_flussweg(ax, "feld") == "axial",
       "'feld' laeuft durch (Stufe 2, ema_axial_fdm)")
try:
    F.pruefe_feldweg(ax, "fdm")
    pruefe(False, "aber die radiale FDM muesste abweisen")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "aber NICHT ueber die radiale FDM der Pipeline")
for stufe in ("lauf",):
    try:
        F.pruefe_flussweg(ax, stufe)
        pruefe(False, f"Stufe '{stufe}' muesste abweisen — tut es nicht")
    except F.FlusswegNichtUnterstuetzt as e:
        pruefe("AXIALFLUSS.md" in str(e) and "1,49" in str(e),
               f"Stufe '{stufe}' weist ab und nennt Plan und Groessenordnung")
# 'em3d' laeuft durch -- aber nur auf dem RICHTIGEN Loeser. Ohne die zweite
# Pruefung hiesse "em3d traegt" , der Vollmotorweg duerfe eine Scheibe
# vernetzen, und der haette klaglos konzentrische Zylinder gebaut.
pruefe(F.pruefe_flussweg(ax, "em3d") == "axial",
       "'em3d' laeuft durch (ema_axial_em3d, Ringsektor)")
# Seit dem 07.10.2026 traegt auch `cad` -- ueber `ema_axial_cad` (Scheibe,
# radiale Nuten), nicht ueber `build_full_motor_script` (Zylinder, Nuten im
# Mantel). Dritte Stufe mit eigenem Weg, dieselbe Unterscheidung.
pruefe(F.pruefe_flussweg(ax, "cad") == "axial",
       "'cad' laeuft durch (ema_axial_cad, Scheibe)")
pruefe(F.cad_weg(ax["geom"]) == "scheibe"
       and F.cad_weg(vorgabe()) == "vollmotor",
       "und der CAD-Erzeuger haengt am Flussweg, nicht am Aufrufer")
try:
    F.pruefe_cad_weg(ax["geom"], "vollmotor")
    pruefe(False, "aber der Vollmotorerzeuger muesste abweisen")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "aber NICHT ueber build_full_motor_script — der zeichnet einen "
                 "Zylinder mit Nuten im Mantel")
pruefe(F.em3d_weg(ax["geom"]) == "sektor_axial"
       and F.em3d_weg(vorgabe()) == "elmer3d_stat",
       "und der 3-D-Weg haengt am Flussweg, nicht am Aufrufer")
try:
    F.pruefe_em3d_weg(ax["geom"], "elmer3d_stat")
    pruefe(False, "aber der magnetostatische Vollmotor muesste abweisen")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "aber NICHT ueber den magnetostatischen Vollmotor")
pruefe(F.pruefe_flussweg({"geom": vorgabe()}, "feld") == "radial",
       "radial laeuft durch alle Stufen wie bisher")

print("\n— 3. Das zentrale Pipelinetor fragt den Flussweg wirklich —")

import ema_pipeline

# **Der LAUF wird aufgeteilt, nicht abgewiesen** (geaendert am 07.10.2026). Hier
# stand die Erwartung, `_gate_maschinenart(..., "lauf")` werfe -- und genau das
# war der Fehler: `stages` ist aus dem Browser immer `None`, also prueft das Tor
# den vollen Satz, bleibt an `geometry`/`structural` haengen und **kein einziger
# Axiallauf aus der Oberflaeche** kam zustande, obwohl Feld, Thermik und
# Fahrzyklus tragen. Ein Test, der das festnagelt, verteidigt den Defekt.
#
# Geprueft wird jetzt, was gelten soll: der Lauf laeuft durch, und die
# AUFTEILUNG benennt beide Seiten.
try:
    ema_pipeline._gate_maschinenart(ax, None, "lauf")
    pruefe(True, "_gate_maschinenart laesst den LAUF durch und verengt ihn")
except Exception as e:                                  # pragma: no cover
    pruefe(False, f"_gate_maschinenart wirft beim Lauf: {type(e).__name__}: {e}")
_tr, _off = F.stufen_aufteilen(ax["geom"], ema_pipeline._ALLE_STUFEN)
pruefe(set(_tr) == {"field", "thermal", "drivecycle", "geometry"}
       and set(_off) == {"structural"},
       f"und die Aufteilung ist die richtige: {sorted(_tr)} laufen, "
       f"{sorted(_off)} nicht")
pruefe(all(F.STUFE_STATTDESSEN.get(o) for o in _off),
       "zu jeder uebersprungenen Stufe steht da, was sie STATTDESSEN rechnet — "
       "stillschweigend weglassen waere schlimmer als abweisen")
# Ein AUSDRUECKLICH verlangter Einzelschritt wird weiter abgewiesen: dort ist
# ein Nein die richtige Antwort und nennt den Weg, der geht.
try:
    F.stufen_pruefen(ax["geom"], {"structural"})
    pruefe(False, "ein ausdrueckliches 'structural' muesste abweisen")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "ein ausdrueckliches 'structural' weist ab — die Scheibe "
                 "traegt die Fliehkraft-FEM nicht")

print("\n— 4. Der Kern: zwei Integrale, nicht ein Ersatzradius —")

# Die Axialflussmaschine aus AXIALFLUSS.md §1: Ro = 130, lambda = 0,577, 2 Spalte.
gax = vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=0.5774,
              axialSpalte=2, axialBauform="yasa")
fx = F.flaechen(gax, L_mm)
ro, ri, n = fx["r_aussen_m"], fx["r_innen_m"], fx["n_spalte"]
pruefe(abs(fx["a_fluss_m2"] - n * (ro ** 2 - ri ** 2) / 2) < 1e-15,
       f"a_fluss = n*(Ro^2-Ri^2)/2 = {fx['a_fluss_m2'] * 1e4:.2f} cm^2")
pruefe(abs(fx["a_moment_m3"] - n * (ro ** 3 - ri ** 3) / 3) < 1e-18,
       f"a_moment = n*(Ro^3-Ri^3)/3 = {fx['a_moment_m3'] * 1e6:.2f} cm^3")

v_fluss = fx["a_fluss_m2"] / f["a_fluss_m2"]
v_mom = fx["a_moment_m3"] / f["a_moment_m3"]
pruefe(round(v_fluss, 2) == 1.49 and round(v_mom, 2) == 1.66,
       f"und sie sind VERSCHIEDEN: Fluss x{v_fluss:.2f}, Moment x{v_mom:.2f} "
       f"— ein Ersatzradius trifft nur eines von beiden")

t_ax = 2 * math.pi * 40e3 * fx["a_moment_m3"]
pruefe(round(t_ax, 1) == 297.2,
       f"T_axial(water, 2 Spalte) = {t_ax:.1f} Nm gegen {t_haus:.1f} Nm radial")

# Der Kreuzungspunkt: ab welcher Paketlaenge gewinnt der Radialfluss zurueck?
L_kreuz = t_ax / (2 * math.pi * 40e3 * (g["rotorOD"] / 2 / 1000) ** 2) * 1000
pruefe(round(L_kreuz) == 133 and L_kreuz < T.SCHEMA["axialLen"]["hi"],
       f"Kreuzungspunkt bei L = {L_kreuz:.0f} mm — INNERHALB der Schemagrenze "
       f"({T.SCHEMA['axialLen']['hi']:.0f} mm), also eine erreichbare Auslegung")

print("\n— 5. Verlangte Masse und Aussagen —")

try:
    F.flaechen(vorgabe(fluxPath="axial"), L_mm)
    pruefe(False, "axialAktivOD fehlt und wird nicht verlangt")
except ValueError as e:
    pruefe("axialAktivOD" in str(e) and "statorOD" in str(e),
           "ohne axialAktivOD ein klarer Fehler, der sagt, warum es nicht aus "
           "statorOD kommt")
f0 = F.flaechen(vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=0.0),
                L_mm)
pruefe(round(f0["lambda"], 4) == 0.5774,
       "lambda=0 heisst 'nicht gesetzt' und faellt auf 1/sqrt(3) — nicht auf "
       "einen Ringraum ohne Innenradius")
for lam in (0.99, 1.5, -0.2):
    try:
        F.flaechen(vorgabe(fluxPath="axial", axialAktivOD=260.0, axialLambda=lam),
                   L_mm)
        pruefe(False, f"lambda={lam} muesste abgewiesen werden")
    except ValueError:
        pruefe(True, f"lambda={lam} wird abgewiesen (Ringraum verschwindet)")

tr = F.traeger(gax)
pruefe(tr["kraft_hebt_sich_auf"] and not tr["lastart_vorhanden"]
       and "ema_deck" in tr["aussage"],
       "traeger() sagt: Kraft hebt sich am Staender auf, die Lastart gibt es "
       "aber in keiner Strukturstufe")
tr1 = F.traeger(vorgabe(fluxPath="axial", axialAktivOD=260.0,
                        axialBauform="einseitig", axialSpalte=1))
pruefe(not tr1["kraft_hebt_sich_auf"] and tr1["traeger"] == "das Lager",
       "beim einseitigen Aufbau traegt das LAGER, und das sagt es")
pruefe(F.traeger(vorgabe())["lastart_vorhanden"],
       "radial ist die bemessende Last (Fliehkraft) vorhanden und gerechnet")

print("\n— 6. Schema und Werkzeugstand fuehren denselben Stand —")

pruefe(T.SCHEMA["fluxPath"]["opts"] == list(F.FLUSSWEGE)
       and T.SCHEMA["fluxPath"]["def"] == F.VORGABE,
       "das Schema fuehrt die Flusswege aus ema_fluss")
pruefe(T.SCHEMA["fluxPath"].get("adv") is True,
       "und als Feinparameter — Text->Auslegung erfragt ihn nicht, solange "
       "keine Stufe ihn traegt")
pruefe(sorted(T.SCHEMA["axialBauform"]["opts"]) == sorted(F.AXIAL_BAUFORMEN),
       "die Axialfluss-Bauformen ebenfalls aus EINER Quelle")
import ema_werkzeugstand
pruefe("ema_fluss.py" in ema_werkzeugstand.PHYSIK,
       "ema_fluss.py steht im Fingerabdruck (PHYSIK) — es bewegt Kt und das "
       "Dauermoment")

# Die Zurechtrueckung im Schema darf den Flussweg nicht aufheben.
roh = {k: v.get("def") for k, v in T.SCHEMA.items()}
roh.update(fluxPath="axial", axialAktivOD=260.0)
v = T._validate(roh)
pruefe(v.get("fluxPath") == "axial" and float(v.get("axialAktivOD", 0)) == 260.0,
       "_validate haelt fluxPath und axialAktivOD (zieht sie nicht still auf "
       "radial zurueck)")


# ---------------------------------------------------------------------------
# Die Zusammenfuehrung: Zeichenseite <-> Schema <-> Stufen
# ---------------------------------------------------------------------------
print("\n— Zeichenseite und Schema —")

SEITE = dict(ro=130, lam=0.577, poles=16, q=48, bnut=6, spalt=1, zahn=25,
             jochS=0, jochR=13, magd=6, alpha=0.85, welle=60, wkI=14,
             stapel=1, magSegU=4, magSegR=3, magFuge=1, qr=0,
             topo="esdr", laeufer="sektor")

# JEDER Feldname der Seite muss einen Schemaschluessel haben. Faellt einer
# heraus, traegt der Payload ihn nicht, und die Uebernahme verliert ihn
# STILL -- genau die Falle, wegen der `_validate` die adv-Schluessel einzeln
# aufzaehlt.
_fehlt = [sl for _, (sl, _) in F.SEITE_FELDER.items() if sl not in T.SCHEMA]
pruefe(not _fehlt, f"jedes Feld der Seite hat einen Schemaschluessel "
                   f"({len(F.SEITE_FELDER)} Felder)" +
                   (f" — es fehlen {_fehlt}" if _fehlt else ""))

g = F.aus_seite(SEITE)
pruefe(g["fluxPath"] == "axial",
       "aus_seite setzt fluxPath=axial — wer die Seite uebernimmt, meint eine Scheibe")

# Die drei Umrechnungen, die man genau einmal falsch macht.
pruefe(abs(g["axialAktivOD"] - 260.0) < 1e-9,
       "Radius -> Durchmesser: ro = 130 wird axialAktivOD = 260")
pruefe(g["p"] == 8, "Polzahl -> Polpaare: 2p = 16 wird p = 8")
pruefe(g["axialBauform"] == "yasa" and F.BAUFORM_TOPO["yasa"] == "esdr",
       "topo und axialBauform sind EIN Merkmal in zwei Vokabularen (esdr <-> yasa)")
pruefe(F.aus_seite({**SEITE, "jochS": 12})["axialBauform"] == "torus_nn",
       "yasa gegen torus_nn folgt aus dem Staenderjoch, nicht aus einem zweiten Feld")
pruefe(F.aus_seite({**SEITE, "topo": "eser"})["axialSpalte"] == 1
       and F.aus_seite({**SEITE, "topo": "dser"})["axialSpalte"] == 2,
       "die Spaltzahl wird aus der Bauform ABGELEITET, nicht daneben eingestellt")
pruefe(F.aus_seite({**SEITE, "stapel": 3})["axialSpalte"] == 6,
       "der Stapel vervielfacht die Luftspalte (3 Teilmaschinen -> 6 Spalte)")

# Hin und zurueck. Ohne das koennte die Uebernahme eine Maschine schreiben und
# eine andere zurueckgeben, und beide saehen richtig aus.
zur = F.zur_seite(g)
_schief = [k for k, v in SEITE.items()
           if (str(zur.get(k)) != str(v) if isinstance(v, str)
               else abs(float(zur.get(k, -1e9)) - float(v)) > 1e-9)]
pruefe(not _schief, f"Seite -> Schema -> Seite ist verlustfrei" +
                    (f" — schief: {_schief}" if _schief else ""))

# Ein RADIALES Projekt hat keine axialen Schluessel. `zur_seite` darf dann
# nichts erfinden: die Seite behaelt ihre eigenen Werte, und das steht da.
pruefe(len(F.zur_seite({"statorOD": 280, "p": 3})) <= 2,
       "zur_seite erfindet nichts, was im Projekt nicht steht")

# Der Payload ueberlebt `_validate` -- ein adv-Schluessel, der dort
# herausfaellt, macht einen axialen Payload still wieder radial.
_v = T._validate(dict(g))
_weg = [k for k in g if k not in _v]
pruefe(not _weg, f"kein axialer Schluessel geht bei _validate verloren" +
                 (f" — verloren: {_weg}" if _weg else ""))

print("\n— Die Stufen sind erreichbar —")
# Der eigentliche Befund der Zusammenfuehrung: `ema_axial` und `ema_axial_fdm`
# hatten ausserhalb ihrer eigenen Tests keinen einzigen Aufrufer.
import importlib, inspect
_cli = importlib.import_module("cae_cli")
pruefe(hasattr(_cli, "cmd_axial"), "cae_cli traegt das Verb `axial`")
_q = inspect.getsource(_cli.cmd_axial)
pruefe("ema_axial" in _q and "ema_axial_fdm" in _q,
       "das Verb ruft BEIDE Stufen — analytisch und Feld")
pruefe("fluxPath" in _q and "RADIAL" in _q,
       "es weist einen radialen Payload ab, statt Ringraumzahlen aus "
       "Zylindermassen zu rechnen")

import ema_axial_fdm as _AF
_g = dict(g)
_an = _AF.eichung_magnet(_g)
pruefe(0.5 < _an < 1.2,
       f"die Arbeitsgerade der Scheibe liegt bei {_an:.4f} T")

# Die DREI Anker sind drei verschiedene Groessen, und sie zu verwechseln war der
# Fund vom 06.10.2026 (BEFUNDE.md): `schnitt` pinnte die SPITZE des geloesten
# Feldes auf den MITTELWERT und meldete davon die GRUNDWELLE -- 45 % zu klein.
_sp, _h1 = _AF.eichung_magnet_spitze(_g), _AF.eichung_magnet_grundwelle(_g)
pruefe(_an < _sp < _h1,
       f"Mittel {_an:.4f} < Spitze {_sp:.4f} < Grundwelle {_h1:.4f} T")

# Und die Zeichenseite eicht auf DENSELBEN Anker -- nachgerechnet mit `node`
# gegen `feld.js`, NICHT mit einer hier abgeschriebenen Formel. Die Abschrift
# stand bis zum 06.10.2026 genau hier (`1.15 * (6.0/(6.0+1.05*1.15*1.0)) * 0.85`)
# und war damit dieselbe Sorte Drift, gegen die der Test gebaut ist: sie haette
# die Aenderung der Zeichenseite gar nicht sehen koennen.
import json as _json
import subprocess as _sp2
import tempfile as _tf
_kern = r"""
const fs = require("fs"), vm = require("vm");
const dir = process.argv[2];
const ctx = { console, performance: { now: () => Date.now() }, Math,
              Float64Array, Uint8Array, Number, Set, document: null };
vm.createContext(ctx);
for (const f of ["geometrie.js", "feld.js"])
  vm.runInContext(fs.readFileSync(dir + "/" + f, "utf8"), ctx, f);
// Gerufen wird die ECHTE `eichung` ueber den echten Weg (Gitter, Loeser), statt
// ihren Quelltext zu zerschneiden: nur so prueft der Spiegel die Funktion, die
// die Seite benutzt. Das Gitter ist absichtlich grob -- `bAn` haengt nicht
// daran, und ein feines kostete hier Sekunden.
const p = JSON.parse(process.argv[3]);
const g0 = ctx.feldGitter(p, 8, 8);
const nx = Math.max(16, Math.round(24 * (g0.breite / g0.hGes)));
const g = ctx.feldGitter(p, nx, 24);
const loe = ctx.loeseFeld(p, g, 200);
const { By } = ctx.feldAus(g, loe.A);
const e = ctx.eichung(p, g, By, loe.pkMag, 200);
console.log(JSON.stringify({ bAn: e.bAn, art: e.art, geeicht: e.geeicht }));
"""
# Dieselbe Scheibe, die auch `pruefe.js` rechnet (BASIS dort).
_pj = {"topo": "esdr", "laeufer": "sektor", "stapel": 1, "ro": 130,
       "ri": 75.01, "lam": 0.577, "poles": 16, "q": 48, "bnut": 6,
       "spalt": 1, "zahn": 25, "jochS": 12, "jochR": 13, "magd": 6,
       "alpha": 0.85, "welle": 30, "wkI": 14, "rs": 102.5, "last": 0,
       "magSegU": 1, "magSegR": 1, "magFuge": 1, "qr": 0, "beta": 0,
       "rotorOhneJoch": False, "statorOhneJoch": True, "nSpalte": 2}
_js = None
try:
    with _tf.NamedTemporaryFile("w", suffix=".js", delete=False) as _fh:
        _fh.write(_kern)
        _pf = _fh.name
    _dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "axialfluss")
    _r = _sp2.run(["node", _pf, _dir, _json.dumps(_pj)],
                  capture_output=True, text=True, timeout=180)
    if _r.returncode == 0:
        _aus = _json.loads(_r.stdout.strip().splitlines()[-1])
        _js = float(_aus["bAn"])
        _jsart = _aus.get("art")
    else:
        _jsgrund = (_r.stderr or "").strip()[-300:]
    os.unlink(_pf)
except Exception as _e:                                            # noqa: BLE001
    _js = None
if _js is None:
    pruefe(False, "der Anker der Zeichenseite liess sich mit `node` nicht "
                  "auslesen — die Spiegelpruefung ist damit NICHT gelaufen"
                  + (f" ({_jsgrund})" if "_jsgrund" in dir() else ""))
else:
    pruefe(abs(_js - _sp) / _sp < 0.02,
           f"die Zeichenseite ankert auf {_js:.4f} T und Python auf "
           f"{_sp:.4f} T — dieselbe SPITZE der Arbeitsgeraden "
           f"({abs(_js/_sp-1)*100:.2f} % auseinander)")
    pruefe(abs(_js - _an) / _an > 0.05,
           f"und ausdruecklich NICHT auf den Mittelwert {_an:.4f} T — genau "
           f"diese Verwechslung kostete 45 %")
    pruefe(_jsart == "spitze_nutlos",
           f"und sie misst ihn am NUTLOSEN Lauf ({_jsart}) — die genutete "
           f"Spitze liegt 23 % hoeher, weil der Fluss ueber dem Zahn "
           f"gebuendelt ist")

# Die Grenzen muessen sagen, WAS die Abweichung zur Arbeitsgeraden ist. Bis zum
# 06.10.2026 stand dort "NICHT konvergiert, Ursache gleichmaessiges Gitter" --
# die Streuung war echt, die Ursache nicht: sie sass in der Eichung. Jetzt steht
# dort die Nutung, und die ist eine Aussage ueber die Maschine.
_f = _AF.felder(_g, k_schnitte=3, N=200, rpm=1000.0, last_nm=0.0)
pruefe(any("NUTUNG" in x.upper() and "carter" in x.lower()
           for x in _f["grenzen"]),
       "die Feldstufe nennt selbst, dass die Abweichung zur Arbeitsgeraden "
       "die NUTUNG ist, und nennt den Weg sie nachzumessen (`carter`)")
pruefe(not any("gleichmaessige Gitter" in x for x in _f["grenzen"]),
       "und sie behauptet NICHT mehr, es sei das gleichmaessige Gitter — "
       "gemessen konvergiert sie ueber N = 300…700 auf 0,1 %")


print("\n— 9. Bedienbar: Fussleiste, CAD-Wahl, 3-D-Verzweigung —")

import inspect
import re as _re

import ema_seite
_html = ema_seite.quelltext()   # Markup + oberflaeche/*.js

# Die Fussleiste traegt beide Auswahlfelder -- dort wird gestartet, also gehoert
# die Entscheidung "WAS wird gerechnet" dorthin und nicht nur in einen Reiter,
# den man beim Starten gar nicht offen hat.
pruefe('id="foot_flux"' in _html and 'id="foot_cad"' in _html,
       "die Fussleiste traegt die Auswahl Fluss UND CAD-Modell")
_i_fl, _i_btn = _html.index('id="foot_flux"'), _html.index('id="btn_analyse"')
pruefe(_i_fl < _i_btn,
       "und sie steht VOR dem Startknopf — danach waere sie eine Fussnote")

# **EIN Zustand.** Das Fussleistenfeld schreibt in `#flux_path` und loest sein
# `change` aus; zwei Zustaende fuer denselben Schalter sind die Stelle, an der
# Knopfbeschriftung und Rechnung auseinanderlaufen.
pruefe("function footFlussSetzen" in _html
       and "dispatchEvent(new Event('change'))" in _html,
       "der Fluss-Schalter schreibt in das EINE Feld statt einen zweiten "
       "Zustand zu fuehren")
pruefe("foot_flux" in _html.split("function _flussZeigen")[1][:900],
       "und _flussZeigen zieht die Fussleiste nach, egal wer umgestellt hat")

# Das CAD-Feld wird fuer die Scheibe GESPERRT und sagt warum -- ausblenden
# liesse den Eindruck, es sei weg.
_fz = _html.split("function _flussZeigen")[1][:1800]
pruefe("foot_cad" in _fz and "disabled" in _fz and "Axialfluss" in _fz,
       "fuer die Scheibe ist die CAD-Wahl gesperrt und nennt den Grund")

# Der Payload traegt die Wahl wirklich -- ein Feld, das nirgends ankommt, ist
# dasselbe wie keines.
pruefe("payload.cad_modell" in _html,
       "`cad_modell` reist mit dem Vorschau-Payload")
import ema_pipeline as _P
_src = inspect.getsource(_P.build_cad_preview)
pruefe('cad_modell' in _src and 'build_em_rotor_script' in _src,
       "und build_cad_preview waehlt daraus den Erzeuger — `laeufer` macht "
       "ema_freecad.build_em_rotor_script erreichbar, das keinen Aufrufer hatte")
pruefe('"vollmotor"' in _src,
       "Vorgabe bleibt der Vollmotor, also aendert sich kein bisheriger Aufruf")

# **Die Reihenfolge der Verzweigung ist nicht beliebig.** Eine
# Axialflussmaschine ist payloadseitig eine PSM (`machineType` bleibt "pmsm") --
# wer zuerst die Maschinenart fragt, schickt sie stillschweigend in den
# magnetostatischen Vollmotorweg.
import ema_em3d as _E3
_rs = inspect.getsource(_E3.run_em3d)
_i_flux = _rs.find('_FLX.flussweg(geom) == "axial"')
_i_art = _rs.find('_MAr.art_code(geom)')
pruefe(_i_flux >= 0 and _i_art >= 0 and _i_flux < _i_art,
       "run_em3d prueft den FLUSSWEG vor der Maschinenart")
pruefe(hasattr(_E3, "_run_em3d_axial"),
       "und hat dafuer einen eigenen Runner (ema_axial_em3d, Ringsektor)")
_ra = inspect.getsource(_E3._run_em3d_axial)
pruefe("vergleich(" in _ra,
       "der NICHT nur den Sektor rechnet, sondern den Vergleich gegen den "
       "Mehrschnitt — ein Sektor allein waere eine Zahl ohne Bezug")

# Die Feldstufe der Pipeline rechnet den Mehrschnitt, mit den Einstellungen des
# Berechnungs-Reiters, und im LEERLAUF (sonst ist die Zahl das Ankerfeld).
_rp = inspect.getsource(_P.run_pipeline)
pruefe("_AF.felder(" in _rp,
       "die Pipeline-Feldstufe ruft ema_axial_fdm.felder — vorher nahm sie nur "
       "die Arbeitsgerade und verwies auf die Kommandozeile")
pruefe("axial_schnitte" in _rp and "last_nm=0.0" in _rp,
       "mit der Schnittzahl aus dem Payload und im Leerlauf")
import ema_text2ema as _T2
pruefe(all("axial_schnitte" in g["felder"] for g in _T2.GUETE.values()),
       "und beide Guetestufen fuehren sie (Entwurf 5, Detail 9)")

# ---------------------------------------------------------------------------
# Was ergaenzt wird, muss gesagt werden -- `axial_ergaenzen`
# ---------------------------------------------------------------------------
#
# Der Fall, gegen den es gebaut ist, ist der Payload der HAUPTMASKE: sie hat
# kein einziges `axial*`-Feld (die Scheibe wird im Reiter ⊙ Axialfluss
# gezeichnet), schickte aber `fluxPath="axial"` mit. Der Lauf starb am ersten
# Zugriff -- „❌ FEHLER: 'axialAktivOD' fehlt" samt Traceback im
# Protokollfenster, gemeldet am 09.10.2026.
print("\n— Ergaenzen und es sagen —")

_browser = {"fluxPath": "axial", "statorOD": 280, "p": 3, "slots": 54, "shaftD": 60}
_g, _erg = F.axial_ergaenzen(dict(_browser))
pruefe(bool(_erg) and any("axialAktivOD" in z for z in _erg),
       "axial_ergaenzen nennt axialAktivOD — still zu fuellen hiesse, eine "
       "fremde Maschine unter eigenem Namen zu rechnen")
pruefe(all(float(_g[k]) > 0 for k in F.AXIAL_PFLICHT),
       f"danach tragen alle {len(F.AXIAL_PFLICHT)} Pflichtschluessel eine Zahl > 0")
pruefe(not F.axial_ergaenzen(_g)[1],
       "und ein zweiter Durchgang ergaenzt nichts mehr (sonst meldete jeder "
       "Lauf eine Vorgabe, die schon drinsteht)")
pruefe(_g["p"] == 3 and _g["slots"] == 54,
       "gesetzte Werte bleiben stehen: p/slots der Maske werden nicht ueberschrieben")
pruefe(F.axial_ergaenzen({**_browser, "axialAktivOD": 300.0})[0]["axialAktivOD"] == 300.0
       and not any("axialAktivOD" in z
                   for z in F.axial_ergaenzen({**_browser, "axialAktivOD": 300.0})[1]),
       "ein ausdruecklich gesetzter Aussendurchmesser wird weder geaendert "
       "noch als ergaenzt gemeldet")
pruefe(F.axial_ergaenzen({"fluxPath": "axial"})[0] == F.axial_vorgabe({"fluxPath": "axial"}),
       "axial_ergaenzen und axial_vorgabe liefern denselben Payload — eine "
       "Quelle, zwei Tueren")
# Wo 0 „ableiten" heisst, darf das Protokoll sie nicht als Mass lesen.
_null = [z for z in _erg if z.startswith("axialNabeD")]
pruefe(_null and "shaftD" in _null[0],
       "eine 0, die „ableiten“ bedeutet, sagt das auch: "
       + (_null[0] if _null else "—"))
pruefe(set(F.NULL_HEISST) <= set(F.AXIAL_VORGABE)
       and not (set(F.NULL_HEISST) & set(F.AXIAL_PFLICHT)),
       "NULL_HEISST steht nur auf Schluesseln, bei denen 0 wirklich eine Wahl "
       "ist — nie auf einem Pflichtschluessel")

# Und die Scheibe muss danach wirklich durchgehen: Flaechen, Zeichnung, Netz.
import ema_axial as _AX, ema_axial_cad as _AC
pruefe(F.flaechen(_g, 25.0)["a_fluss_m2"] > 0,
       "ema_fluss.flaechen rechnet auf dem ergaenzten Payload (vorher: ValueError)")
pruefe(_AC.pruefen(_g, 25.0)["ok"],
       "ema_axial_cad zeichnet ihn — der Weg, den der Browserlauf nimmt")
# Die Nutbreite ist EINE Quelle. `axialNutBreiteMm = 0` heisst „aus
# slotWidthRatio", nicht „0 mm breit" -- als zweite Quelle las
# `ema_axial_thermik._geo` den Schluessel roh, und `ema_axial_em3d.baue_netz`
# starb daran mit einem nackten `Exception: Degenerate box` aus Gmsh.
import ema_axial_thermik as _AT
_b0 = _AT._geo(_g)["b_nut"] * 1000.0
pruefe(_b0 > 0.5,
       f"b_nut der Thermik/des 3-D-Netzes ist bei axialNutBreiteMm = 0 "
       f"abgeleitet, nicht null ({_b0:.3f} mm)")
pruefe(abs(_b0 - _AX.nutbreite_mm(_g, F.flaechen(_g, 25.0)["r_aussen_m"] * 1000.0)) < 1e-9,
       "und zwar aus ema_axial.nutbreite_mm, der EINEN Quelle")
pruefe(abs(_AT._geo({**_g, "axialNutBreiteMm": 6.0})["b_nut"] * 1000.0 - 6.0) < 1e-9,
       "eine gesetzte Nutbreite bleibt dabei unberuehrt (6 mm bleiben 6 mm)")


print("\n— Die Spaltzahl FOLGT der Bauform —")
# Befund vom 16.10.2026: `masse_axial` nahm `axialSpalte` aus dem Payload und
# fiel nur ersatzweise auf die Bauform zurueck. Abgeleitet wurde der Schluessel
# aber allein in `aus_seite` (der Zeichenseite) -- wer `axialBauform` direkt
# setzt (`cae_cli --set`, der Agent, `axial_vorgabe`), bekam die Spaltzahl des
# VORIGEN Standes: `einseitig` mit zwei Luftspalten, also doppeltes Moment und
# ein Anzug, der sich laut Modell aufhebt, obwohl er es gerade nicht tut.
_soll = {"yasa": 2, "torus_nn": 2, "afir": 2, "einseitig": 1}
for _bf, _n in _soll.items():
    _f = F.flaechen({**_g, "axialBauform": _bf}, 25.0)
    pruefe(_f["n_spalte"] == _n,
           f"{_bf}: {_f['n_spalte']} Luftspalt(e) — aus der Bauform, "
           f"nicht aus dem Schluessel")
pruefe(F.flaechen({**_g, "axialBauform": "yasa", "axialStapel": 3},
                  25.0)["n_spalte"] == 6,
       "gestapelt vervielfacht sie sich (3 x YASA = 6 Luftspalte)")
# Ein widersprechender gespeicherter Wert wird UEBERSTIMMT **und gemeldet** --
# nicht stillschweigend uebergangen und nicht abgewiesen (abweisen traefe jeden
# Altpayload, der die Zahl noch traegt; das Werkzeug hat sie selbst
# hineingeschrieben).
_w = F.flaechen({**_g, "axialBauform": "einseitig", "axialSpalte": 2}, 25.0)
pruefe(_w["n_spalte"] == 1 and _w["spalte_korrigiert"] == (2, 1),
       f"ein widersprechender Payloadwert wird ueberstimmt und gemeldet: "
       f"{_w['spalte_korrigiert']}")
pruefe(F.flaechen({**_g, "axialBauform": "yasa", "axialSpalte": 2},
                  25.0)["spalte_korrigiert"] is None,
       "ein UEBEREINSTIMMENDER Wert meldet nichts — eine Meldung ohne "
       "Abweichung liest sich wie ein Fehler")
# Und die Meldung erreicht den, der davorsitzt: sie steht in der Uebersicht,
# die das Verb `axial` druckt.
_t = _AX.uebersicht({**_g, "axialBauform": "einseitig", "axialSpalte": 2},
                    1.0, 3000.0, 25.0)
pruefe("widerspricht der Bauform" in _t,
       "… und sie steht in ema_axial.uebersicht — geschrieben und "
       "unerreichbar waere dasselbe wie nicht geschrieben")
pruefe("axialSpalte" not in F.AXIAL_VORGABE,
       "AXIAL_VORGABE traegt den Schluessel gar nicht mehr — ein Vorgabewert "
       "waere ein gespeicherter Stand, der der naechsten Bauformwahl "
       "widerspricht")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
