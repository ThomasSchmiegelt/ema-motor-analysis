#!/usr/bin/env python3
"""Werkbank: NUR die Axialflussmaschine bauen und am fertigen Koerper nachmessen.

    ./venv/bin/python bau_axial.py [--bauform yasa] [--zahnform parallel]
                                   [--segu 3] [--segr 2] [--gui]

Sie rechnet **keine** Geometrie, sondern liest ``ema_axial_cad`` -- und genau das
macht sie zur Driftprobe: dasselbe Skript, das die Pipeline baut, hier allein und
mit Nachmessung. Dieselbe Rolle wie ``bau_eesm.py`` beim Schenkelpol, und dort
hat sie zwei Fehler gefunden, die kein Bild gezeigt haette.

Nachgemessen wird, was sich am Koerper messen laesst: Volumen je Teil, Zahl der
Festkoerper, Gueltigkeit -- und **paarweise Durchdringung**. Letztere ueber eine
PUNKTPROBE und nicht ueber `common().Volume`: OCC liefert bei einem gescheiterten
Schnitt bitgleich das Volumen eines Operanden (gemessen am Planetengetriebe,
22.364,90 mm3 fuer ein Teil, das im LOCH des anderen sass).
"""
import argparse
import json
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import ema_axial_cad as AC                                        # noqa: E402
import ema_text2ema as T                                          # noqa: E402
from freecad_runner import run_freecad_script, _pixi_cmd          # noqa: E402


def payload(**zu) -> dict:
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


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--bauform", default="yasa")
    ap.add_argument("--zahnform", default="parallel")
    ap.add_argument("--segu", type=int, default=1)
    ap.add_argument("--segr", type=int, default=1)
    ap.add_argument("--laeufer", default="sektor")
    ap.add_argument("--gui", action="store_true")
    ap.add_argument("--out", default=os.path.expanduser("~/cae_projekte/_bau_axial"))
    a = ap.parse_args()

    g = payload(axialBauform=a.bauform, axialZahnform=a.zahnform,
                axialMagSegUmfang=a.segu, axialMagSegRadial=a.segr,
                axialLaeuferart=a.laeufer)
    pr = AC.pruefen(g, 25.0)
    t = pr["teile"]
    print(f"Bauform {a.bauform} · Zahn {a.zahnform} · Segmente "
          f"{a.segu}x{a.segr} · Laeufer {a.laeufer}")
    print(f"  Ringraum {t['r_innen_mm']:.1f} .. {t['r_aussen_mm']:.1f} mm · "
          f"Hoehe {t['hoehe_mm']:.1f} mm · Nabe r {t['r_nabe_mm']:.1f} mm")
    print(f"  Lagen    {[l['art'] for l in t['lagen']]}")
    print(f"  Teile    {len(t['teile'])} · Magnete {t['n_magnet']} · "
          f"Zaehne {t['slots']} · Nut aussen {t['b_nut_aussen_mm']:.2f} mm")
    if pr["nutbreite"].get("hinweis"):
        print("  ⚠ " + pr["nutbreite"]["hinweis"])
    for b in pr["befunde"]:
        print("  ! " + b)
    if not pr["ok"]:
        print("\nNICHT gebaut — s. Befunde.")
        return 2

    os.makedirs(a.out, exist_ok=True)
    fcstd = os.path.join(a.out, "axial.FCStd")
    code = AC.baue_skript(g, 25.0, fcstd)
    print(f"\n  Skript {len(code)} Zeichen, {code.count('addObject')} Objekte — "
          f"FreeCAD laeuft…")
    res = run_freecad_script(code, timeout=900)
    if not res.get("cad_success"):
        print("  FEHLGESCHLAGEN:\n" + (res.get("stderr") or "")[-1500:])
        return 1

    # Gelesen wird mit `raw_decode`, nicht mit `json.loads`: hinter dem Objekt
    # kann in einer Markerzeile weiterer Text stehen (gemessen "Extra data:
    # column 8205"), und FreeCAD schreibt seine eigenen Meldungen ohne Ruecksicht
    # auf Zeilengrenzen. Derselbe Fallstrick wie bei `ema_agent._zerlegen` und
    # der `\r`-Fortschrittszeile von FluidX3D.
    teile = {}
    _dec = json.JSONDecoder()
    for ln in (res.get("stdout") or "").splitlines():
        i = ln.find("AX_TEILE:")
        if i >= 0:
            try:
                teile, _ = _dec.raw_decode(ln[i + len("AX_TEILE:"):])
            except ValueError:
                pass
    ueb = {}
    for ln in (res.get("stdout") or "").splitlines():
        i = ln.find("AX_UEBERLAPP:")
        if i >= 0:
            try:
                ueb, _ = _dec.raw_decode(ln[i + len("AX_UEBERLAPP:"):])
            except ValueError:
                pass
    print(f"  ✓ Volumen gesamt {res.get('volume', 0):.0f} mm3, "
          f"{len(teile)} Teile gemessen")
    nach_rolle = {}
    for nm, d in teile.items():
        rolle = nm.split("_")[0]
        s = nach_rolle.setdefault(rolle, {"n": 0, "v": 0.0, "solids": 0,
                                         "ungueltig": 0})
        s["n"] += 1
        s["v"] += d.get("v", 0.0)
        s["solids"] += d.get("solids", 0)
        if not d.get("gueltig", True):
            s["ungueltig"] += 1
    print(f"\n  {'Teil':18s} {'n':>4s} {'Volumen [mm3]':>15s} "
          f"{'Solids':>7s} {'ungueltig':>10s}")
    for rolle, s in sorted(nach_rolle.items()):
        print(f"  {rolle:18s} {s['n']:4d} {s['v']:15.1f} "
              f"{s['solids']:7d} {s['ungueltig']:10d}")
    schlecht = [nm for nm, d in teile.items()
                if d.get("fehler") or not d.get("gueltig", True)
                or d.get("v", 0) <= 0]
    if schlecht:
        print(f"\n  ⚠ {len(schlecht)} Teil(e) ungueltig oder leer: "
              f"{schlecht[:6]}")
    else:
        print("\n  ✓ jedes Teil ist ein gueltiger Koerper mit Volumen > 0")
    if ueb:
        bf = ueb.get("befunde") or []
        if not bf:
            print(f"  ✓ {ueb['geprueft']} bedeutsame Paare geprueft, KEINE "
                  f"Durchdringung — der Luftspalt steht, die Isolation haelt, "
                  f"die Fugen sind offen")
        else:
            print(f"  ⚠ {len(bf)} von {ueb['geprueft']} Paaren durchdringen "
                  f"sich:")
            for d in bf[:8]:
                print(f"      {d['a']} ∩ {d['b']}: "
                      + ("nicht nachweisbar (OCC-Schnitt gescheitert)"
                         if d.get("unklar") else f"{d['v']} mm3"))
    print(f"\n  {fcstd}")
    for u in pr["ungeprueft"]:
        print("  ℹ " + u[:118])
    if a.gui:
        subprocess.Popen(_pixi_cmd("build/release/bin/FreeCAD", fcstd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
