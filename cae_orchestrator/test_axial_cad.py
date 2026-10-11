#!/usr/bin/env python3
"""Die Scheibe als CAD — Zahlen und Skript OHNE FreeCAD.

    ./venv/bin/python test_axial_cad.py            # ohne FreeCAD
    ./venv/bin/python test_axial_cad.py --echt     # baut wirklich und misst nach

Geprueft wird gegen INVARIANTEN und gegen die anderen Quellen, nicht gegen
festgenagelte Zahlen: eine festgenagelte Zahl prueft nur, dass sich nichts
geaendert hat, waehrend ein Volumen, das aus einer geschlossenen Formel folgt,
wirklich etwas prueft.

**Die gefaehrlichste Stelle ist die Stueckelung.** `segmente`/`ringe` gab es bis
zum 07.10.2026 nur in JavaScript (`axialfluss/geometrie.js`); fuer das CAD
brauchte es sie in Python. Zwei Fassungen derselben Geometrie sind genau die
Drift, gegen die dieses Repo seine Spiegeltests hat — also wird die JS-Fassung
mit `node` AUSGEFUEHRT und Zahl fuer Zahl verglichen, wie bei `magnetLegs`
(`test_topology.py`) und der Halbpol-Umrechnung (`test_mobil.py`).
"""
import json
import math
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_axial                                                   # noqa: E402
import ema_axial_cad as AC                                         # noqa: E402
import ema_axial_fdm as AF                                         # noqa: E402
import ema_text2ema as T                                           # noqa: E402

_ok = _fehl = 0
ECHT = "--echt" in sys.argv
HIER = os.path.dirname(os.path.abspath(__file__))


def pruefe(b, text):
    global _ok, _fehl
    if b:
        _ok += 1
        print(f"  ✓ {text}")
    else:
        _fehl += 1
        print(f"  ✗ {text}")


def geom(**zu):
    g = {k: v.get("def") for k, v in T.SCHEMA.items() if v.get("geom")}
    g.update({"fluxPath": "axial", "p": 8, "slots": 48, "axialAktivOD": 260.0,
              "axialLambda": 0.577, "axialSpalte": 2, "axialBauform": "yasa",
              "axialSpaltMm": 1.0, "axialMagnetDicke": 6.0,
              "axialPolbedeckung": 0.85, "axialZahnform": "parallel",
              "axialNabeD": 0, "axialBminMm": 2.0, "axialNutBreiteMm": 6.0,
              "axialZahnLaengeMm": 25.0, "axialJochStaenderMm": 0.0,
              "axialJochLaeuferMm": 13.0, "axialWickelkopfMm": 14.0,
              "axialStapel": 1, "axialLaeuferart": "sektor",
              "axialMagSegUmfang": 1, "axialMagSegRadial": 1,
              "axialMagFugeMm": 1.0, "shaftD": 60.0, "magnet": "ndfeb_n35"})
    g.update(zu)
    return g


G = geom()

print("— 1. Die Schichtung kommt aus EINER Quelle —")

t = AC.teile(G, 25.0)
pruefe(t["lagen"] == AF.lagen(G),
       "die Lagen sind die von ema_axial_fdm.lagen, nicht eine zweite Fassung")
pruefe(abs(t["hoehe_mm"] - AF.stapelhoehe(G)) < 1e-9,
       f"und die Bauhoehe ist Ziffer fuer Ziffer dieselbe ({t['hoehe_mm']:.3f} mm)")
# Die Gegenprobe, die das traegt: alle drei Leser derselben Quelle.
import ema_axial_em3d as E3                                        # noqa: E402
pruefe(E3._lagen(G) == AF.lagen(G),
       "auch der Elmer-Sektor liest sie — drei Leser, EINE Quelle")

print("\n— 2. Die Stueckelung: Python gegen die Zeichenseite (node) —")


def js(p: dict) -> dict:
    kern = r"""
const fs = require("fs"), vm = require("vm");
const dir = process.argv[2];
const ctx = { console, performance: { now: () => Date.now() }, Math,
              Float64Array, Uint8Array, Number, Set, document: null };
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(dir + "/geometrie.js", "utf8"), ctx, "g.js");
const p = JSON.parse(process.argv[3]);
const s = ctx.magnetSegmente(p), r = ctx.magnetRinge(p);
console.log(JSON.stringify({
  nU: s.nU, bed: s.bed, fug: s.fug, breit: s.breit, hal: s.hal, eng: s.eng,
  mitten: s.seg.map((x) => x.mitte),
  nR: r.nR, h: r.h, r0: r.rg.map((x) => x.r0) }));
"""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
        fh.write(kern)
        pf = fh.name
    try:
        r = subprocess.run(["node", pf, os.path.join(HIER, "axialfluss"),
                            json.dumps(p)], capture_output=True, text=True,
                           timeout=60)
        if r.returncode != 0:
            return {}
        return json.loads(r.stdout.strip().splitlines()[-1])
    finally:
        os.unlink(pf)


def js_p(g: dict) -> dict:
    """Derselbe Fall in der Sprache der Zeichenseite (s. ema_fluss.SEITE_FELDER)."""
    a = ema_axial.auslegung(g)
    return {"laeufer": g["axialLaeuferart"], "poles": a["poles"],
            "ri": a["r_innen_m"] * 1000.0, "ro": a["r_aussen_m"] * 1000.0,
            "alpha": a["polbedeckung"],
            "magSegU": g["axialMagSegUmfang"], "magSegR": g["axialMagSegRadial"],
            "magFuge": g["axialMagFugeMm"]}


_faelle = [("1x1 Vorgabe", {}),
           ("3 umfangs", {"axialMagSegUmfang": 3}),
           ("2 radial", {"axialMagSegRadial": 2}),
           ("4x3 mit Fuge", {"axialMagSegUmfang": 4, "axialMagSegRadial": 3,
                             "axialMagFugeMm": 1.5}),
           ("Halbach 4", {"axialLaeuferart": "halbach", "axialMagSegUmfang": 4}),
           ("ohne Fuge", {"axialMagFugeMm": 0.0}),
           ("Bedeckung 1,0", {"axialPolbedeckung": 1.0})]
_node_ok = True
for nm, zu in _faelle:
    g = geom(**zu)
    j = js(js_p(g))
    if not j:
        _node_ok = False
        pruefe(False, f"{nm}: node konnte geometrie.js nicht ausfuehren — die "
                      f"Spiegelpruefung ist damit NICHT gelaufen")
        continue
    sp, rp = AC.segmente(g), AC.ringe(g)
    gleich = (sp["nU"] == j["nU"] and abs(sp["bed"] - j["bed"]) < 1e-12
              and abs(sp["fug"] - j["fug"]) < 1e-12
              and abs(sp["breit"] - j["breit"]) < 1e-12
              and sp["hal"] == j["hal"] and bool(sp["eng"]) == bool(j["eng"])
              and all(abs(a - b) < 1e-12
                      for a, b in zip([x["mitte"] for x in sp["seg"]],
                                      j["mitten"]))
              and rp["nR"] == j["nR"] and abs(rp["h"] - j["h"]) < 1e-9
              and all(abs(a - b) < 1e-9
                      for a, b in zip([x["r0"] for x in rp["rg"]], j["r0"])))
    pruefe(gleich, f"{nm}: Python und geometrie.js Ziffer fuer Ziffer gleich "
                   f"({sp['nU']}x{rp['nR']}, Breite {sp['breit']:.6f} "
                   f"Polteilungen, Ringhoehe {rp['h']:.4f} mm)")

print("\n— 3. Die Teile: gegen geschlossene Formeln, nicht gegen Festwerte —")

a = ema_axial.auslegung(G, 25.0)
ro, ri = a["r_aussen_m"] * 1000.0, a["r_innen_m"] * 1000.0
rollen = {}
for x in t["teile"]:
    rollen[x["rolle"]] = rollen.get(x["rolle"], 0) + 1
pruefe(rollen.get("magnet") == a["poles"] * t["segmente"]["nU"]
       * t["ringe"]["nR"] * len([l for l in t["lagen"] if l["art"] == "magnet"]),
       f"Magnetzahl = Pole x Segmente x Ringe x Magnetlagen "
       f"({rollen.get('magnet')})")
pruefe(rollen.get("zahn") == a["slots"] and rollen.get("spule") == a["slots"],
       f"je Nut ein Zahn und eine Spule ({a['slots']})")
pruefe(rollen.get("laeufer") == len([l for l in t["lagen"]
                                    if l["art"] == "ruecken"]),
       "je Rueckenlage eine Laeuferscheibe")
pruefe("joch" not in rollen,
       "und der YASA hat KEIN Staenderjoch — das ist der Sinn der Bauform")
pruefe("joch" in {x["rolle"] for x in AC.teile(geom(axialBauform="torus_nn"),
                                              25.0)["teile"]},
       "der TORUS dagegen hat eines (der Fluss laeuft dort umfangs)")

# Die Zaehne sitzen auf s*2pi/Q, die Nut dazwischen -- wie im FDM-Raster. Ohne
# das zeichnet das CAD eine um eine halbe Nutteilung verdrehte Maschine.
_zn = [x for x in t["teile"] if x["rolle"] == "zahn"]
pruefe(abs(_zn[0]["th_mitte"]) < 1e-12
       and abs(_zn[1]["th_mitte"] - 2 * math.pi / a["slots"]) < 1e-12,
       "Zahn 0 liegt auf 0, Zahn 1 eine Nutteilung weiter — dieselbe Teilung "
       "wie im FDM-Raster")

# Magnetvorzeichen: YASA gleichsinnig (NS), TORUS gegensinnig (NN).
def _vz(g):
    tt = AC.teile(g, 25.0)
    lag = [i for i, l in enumerate(tt["lagen"]) if l["art"] == "magnet"]
    aus = []
    for i in lag:
        m = [x for x in tt["teile"]
             if x["rolle"] == "magnet" and x["name"].startswith(f"Magnet_{i}_0_")]
        aus.append(m[0]["pol"] if m else None)
    return aus


pruefe(_vz(G) == [1, 1],
       f"YASA: beide Magnetlagen gleichsinnig {_vz(G)} (NS, Fluss axial durch "
       f"den Zahn)")
pruefe(_vz(geom(axialBauform="torus_nn")) == [1, -1],
       f"TORUS: gegensinnig {_vz(geom(axialBauform='torus_nn'))} (NN, Fluss "
       f"umfangs im Joch)")

print("\n— 4. Die Nutbreite: EINE Quelle, und sie sagt es —")

nb = ema_axial.nutbreite_befund(G)
pruefe(nb["quelle"] == "axialNutBreiteMm" and abs(nb["b_nut_aussen_mm"] - 6.0) < 1e-9,
       f"gezeichnet wird {nb['b_nut_aussen_mm']:.3f} mm aus dem axialen "
       f"Schluessel")
pruefe(nb.get("hinweis") and "slotWidthRatio" in nb["hinweis"],
       f"und der Befund NENNT, was slotWidthRatio ergeben haette "
       f"({nb['aus_slotWidthRatio_mm']:.3f} mm) — 42 % Unterschied schweigend "
       f"auszutauschen waere der Fehler")
# Ohne den axialen Schluessel bleibt jede Altauslegung Ziffer fuer Ziffer gleich.
_g0 = geom(axialNutBreiteMm=0)
_zf0 = ema_axial.zahnform(_g0, 0.63)
pruefe(abs(_zf0["b_zahn_aussen_t"] - 0.63 / ((1 - 0.5) * 0.96)) < 2e-3,
       f"ohne ihn gilt weiter slotWidthRatio ({_zf0['b_zahn_aussen_t']:.4f} T) "
       f"— bestehende Auslegungen bewegen sich nicht")
# Keil kuerzt die Nutteilung heraus, parallel nicht. Das ist die Aussage der
# Zahnform, und sie muss aus der Geometrie FALLEN, nicht gesetzt sein.
_zk = ema_axial.zahnform(geom(axialZahnform="keil"), 0.63)
_zp = ema_axial.zahnform(geom(axialZahnform="parallel"), 0.63)
pruefe(abs(_zk["ueberhoehung"] - 1.0) < 1e-6,
       f"Keilzahn: B_zahn ueber r konstant (Ueberhoehung "
       f"{_zk['ueberhoehung']:.4f}) — die Nutteilung kuerzt sich heraus")
pruefe(_zp["ueberhoehung"] > 1.5,
       f"paralleler Zahn: am Innenrand {_zp['ueberhoehung']:.2f}x so viel — "
       f"die bindende Saettigungsstelle ist der INNENrand")
pruefe(abs(ema_axial.nutbreite_mm(geom(axialZahnform="keil"), ri)
           - 6.0 * ri / ro) < 1e-9,
       "und beim Keil waechst die Nut mit r (konstanter Winkel)")
pruefe(abs(ema_axial.nutbreite_mm(geom(axialZahnform="parallel"), ri) - 6.0) < 1e-9,
       "waehrend sie parallel konstant bleibt")

print("\n— 5. Ein Nein ist ein Ergebnis —")

for art, wort in (("kaefig", "Kurzschlussring"), ("eisenlos", "WICKLUNG")):
    pr = AC.pruefen(geom(axialLaeuferart=art), 25.0)
    pruefe(not pr["ok"] and any(wort in b for b in pr["befunde"]),
           f"Laeuferart '{art}' wird NICHT gezeichnet und sagt warum "
           f"({wort})")
# Zu viele Segmente passen nicht -- das ist eine Aussage, keine Ausnahme.
pr = AC.pruefen(geom(axialMagSegUmfang=16, axialMagFugeMm=10.0), 25.0)
pruefe(not pr["ok"] and any("Polbedeckung" in b for b in pr["befunde"]),
       "16 Segmente mit 10-mm-Fugen passen nicht in die Polbedeckung — und das "
       "wird gesagt, statt Magnete negativer Breite zu zeichnen")
pr = AC.pruefen(geom(slots=240, axialNutBreiteMm=6.0), 25.0)
pruefe(not pr["ok"] and any("Innenrand" in b for b in pr["befunde"]),
       "und ein Zahn unter dem Fertigungsboden am INNENrand ebenso — dort ist "
       "die Engstelle jeder Scheibe")
pruefe(len(AC.ungeprueft()) >= 4
       and any("BANDAGE" in u for u in AC.ungeprueft())
       and any("Verguss" in u for u in AC.ungeprueft()),
       "und was NICHT gebaut ist, steht da (Bandage, Verguss, Lager) — "
       "Schweigen liesse sich als geprueft lesen")

print("\n— 6. Das Skript: gueltiges Python, und die Fallen vermieden —")

code = AC.baue_skript(G, 25.0, "/tmp/pruef.FCStd")
import ast
try:
    ast.parse(code)
    pruefe(True, f"das erzeugte Skript ist gueltiges Python "
                 f"({len(code)} Zeichen, {code.count('addObject')} Objekte)")
except SyntaxError as e:                                           # pragma: no cover
    pruefe(False, f"SYNTAXFEHLER im erzeugten Skript: {e}")
pruefe('"""' not in code,
       "und es enthaelt kein dreifaches Anfuehrungszeichen — das beendet die "
       "umschliessende Zeichenkette, in diesem Repo zweimal passiert")
pruefe('getattr(_o, "ViewObject", None)' in code,
       "der ViewObject-Zugriff ist abgesichert: FreeCADCmd hat keinen, und ein "
       "nackter Zugriff liess das GANZE Skript scheitern (131 Teile gebaut, "
       "keines gespeichert)")
pruefe(code.count("addObject") == len(t["teile"]),
       "je Teil ein Objekt — nichts fehlt und nichts ist doppelt")
pruefe("AX_UEBERLAPP" in code and "_ueberlapp" in code,
       "und es misst die Durchdringung am FERTIGEN Koerper nach")
pruefe("0.999 * min(" in code,
       "dabei wird der OCC-Fehlschlagfall abgefangen: ein Schnitt so gross wie "
       "ein ganzer Operand ist keine Durchdringung, sondern ein gescheiterter "
       "Schnitt (gemessen am Planetengetriebe)")

print("\n— 7. Der Flussweg traegt die Stufe, auf SEINEM Weg —")

import ema_fluss as F                                              # noqa: E402
pruefe("cad" in F.STUFEN_AXIAL,
       "'cad' traegt den Axialfluss")
pruefe(F.cad_weg(G) == "scheibe" and F.cad_weg({"fluxPath": "radial"}) == "vollmotor",
       "und der Erzeuger haengt am Flussweg, nicht am Aufrufer")
try:
    F.pruefe_cad_weg(G, "vollmotor")
    pruefe(False, "der Vollmotorerzeuger muesste abgewiesen werden")
except F.FlusswegNichtUnterstuetzt:
    pruefe(True, "aber NICHT ueber build_full_motor_script (Zylinder, Nuten im "
                 "Mantel)")
import inspect                                                     # noqa: E402
import ema_pipeline as P                                           # noqa: E402
_src = inspect.getsource(P.run_pipeline)
pruefe('_FLS.cad_weg(geom) == "scheibe"' in _src,
       "und die Pipeline-Geometriestufe fragt ihn")
pruefe("ema_axial_cad" in inspect.getsource(P.build_cad_preview),
       "ebenso die CAD-Vorschau (der Knopf 🧊 CAD ansehen)")

import ema_werkzeugstand as W                                      # noqa: E402
pruefe("ema_axial_cad.py" in W.PHYSIK,
       "ema_axial_cad.py steht im Fingerabdruck — es entscheidet, was "
       "gezeichnet UND was gesaettigt wird")

if ECHT:
    print("\n— 8. Wirklich gebaut (--echt) —")
    from freecad_runner import run_freecad_script
    with tempfile.TemporaryDirectory() as td:
        fc = os.path.join(td, "a.FCStd")
        r = run_freecad_script(AC.baue_skript(G, 25.0, fc), timeout=900)
        if not r.get("cad_success"):
            pruefe(False, "FreeCAD-Lauf gescheitert: "
                          + (r.get("stderr") or "")[-200:])
        else:
            m = AC.messung_aus_stdout(r.get("stdout") or "")
            pruefe(m["n_teile"] == len(t["teile"]),
                   f"{m['n_teile']} Teile gebaut und gemessen")
            pruefe(not m["ungueltig"],
                   "jedes Teil ist ein gueltiger Koerper mit Volumen > 0")
            pruefe(m.get("ueberlapp") == 0,
                   f"und KEINE Durchdringung bei "
                   f"{m.get('ueberlapp_geprueft')} bedeutsamen Paaren — der "
                   f"Luftspalt steht")
            # Gegen die geschlossene Formel: ein Magnet ist ein Ringsektor.
            mg = [v["v"] for n, v in (m["teile"] or {}).items()
                  if n.startswith("Magnet_")]
            sg = AC.segmente(G)
            soll = (0.5 * (sg["breit"] * 2 * math.pi / a["poles"])
                    * (ro ** 2 - ri ** 2) * a["magnet_dicke_m"] * 1000.0)
            pruefe(mg and abs(mg[0] / soll - 1) < 0.01,
                   f"und das Magnetvolumen trifft die geschlossene Formel "
                   f"({mg[0]:.1f} gegen {soll:.1f} mm³)")
else:
    print("\n  (ohne --echt: der Bau braucht FreeCAD)")

print(f"\n{_ok} bestanden, {_fehl} fehlgeschlagen")
sys.exit(1 if _fehl else 0)
