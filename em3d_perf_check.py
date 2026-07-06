#!/usr/bin/env python3
"""Performance-Check für die 3D-Magnetfeldberechnung (Elmer FEM).

Fährt die Netzfeinheit schrittweise hoch (Skalierung der Zell-Größen gap_cl/mag_cl/mesh_cl)
und misst pro Stufe **Knotenzahl, Rechenzeit (Mesh / ElmerGrid / ElmerSolver) und den
Spitzen-RAM-Bedarf** (via ``/usr/bin/time -v`` → "Maximum resident set size"). So lässt sich
belegen, wo der praktische Deckel liegt (siehe ``EM3D_MAX_NODES`` in ``ema_em3d.py`` — bislang
empirisch auf 55000 gesetzt, ohne dokumentierte RAM-Grundlage).

Der Solve läuft als **Leerlauf-Magnetostatik** (nur Magnete, keine Statorströme) — das isoliert
die reine Löser-Skalierung und ist über alle Stufen vergleichbar.

Ablauf je Stufe:
  build_mesh (Gmsh)  →  ElmerGrid (MSH→Elmer-Mesh)  →  write_sif  →  ElmerSolver (unter /usr/bin/time -v)

Sicherheit:
  * Ergebnisse werden **nach jeder Stufe** inkrementell als CSV + JSON geschrieben — bricht eine
    Stufe ab (Timeout / OOM / Solverfehler), bleiben die vorherigen erhalten.
  * Vor jedem Solve wird gegen den freien RAM geprüft; überschreitet die letzte Messung
    ``--ram-stop`` (Default 80 % des Gesamt-RAM), wird abgebrochen (höhere Knotenzahlen wären nur
    schlechter). Return-Code 137 (OOM-Kill) wird als solcher erkannt.

Lauf (im venv):
    source venv/bin/activate
    python em3d_perf_check.py                       # Standard-Leiter bis ~500k Knoten
    python em3d_perf_check.py --calibrate           # nur meshen (Faktor→Knoten kartieren, kein Solve)
    python em3d_perf_check.py --max-nodes 300000 --timeout 1800
"""

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

import ema_em3d as E3
import elmer_runner as ER

# Repräsentative IPM-Geometrie (identisch zu test_em3d._GEOM: 8-polig, 48 Nuten, V-Magnete).
GEOM = {"statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "p": 4,
        "slots": 48, "slotDepth": 25, "magThick": 6, "magWidth": 40, "magAngle": 130,
        "magDepthRel": 0.5, "magDist": 3, "poleArcFrac": 0.83, "magOrient": "transverse",
        "magShape": "v", "magnet": "ndfeb_n42"}
AXIAL = 120.0

TIME_BIN = "/usr/bin/time"


def _total_ram_kb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


def _avail_ram_kb():
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1])
    except Exception:
        pass
    return 0


def _fmt_kb(kb):
    return f"{kb / 1024 / 1024:.2f} GiB" if kb else "?"


def _auto_cl(geom):
    """Reproduziert die Auto-Zellgrößen aus _build_mesh_once (mm) als Startpunkt (Faktor 1.0)."""
    r_so = geom["statorOD"] / 2.0
    gap = (geom["statorID"] - geom["rotorOD"]) / 2.0
    mesh_cl = max(2.0, r_so / 18.0)
    gap_cl = max(0.35, gap * 0.6)
    mag_cl = max(gap_cl, mesh_cl * 0.5)
    return gap_cl, mag_cl, mesh_cl


def build_one_mesh(scale, work, log):
    """Baut EIN Mesh bei Zellgrößen-Skalierung ``scale`` (<1 = feiner). Returns (tags, secs, msh_path)."""
    gap0, mag0, mesh0 = _auto_cl(GEOM)
    opts = {"skew_deg": 0.0,
            "gap_cl":  gap0 * scale,
            "mag_cl":  mag0 * scale,
            "mesh_cl": mesh0 * scale}
    msh = os.path.join(work, "motor3d.msh")
    t0 = time.perf_counter()
    tags = E3.build_mesh(GEOM, AXIAL, opts, msh)   # direkt (umgeht den EM3D_MAX_NODES-Cap)
    secs = time.perf_counter() - t0
    mz = tags.get("mesh_zones", {})
    log(f"    Mesh: {tags['n_nodes']:>8d} Knoten  ({secs:5.1f}s)  "
        f"cl=[gap {mz.get('gap_cl',0):.3f} / mag {mz.get('mag_cl',0):.2f} / grob {mz.get('mesh_cl',0):.2f}]")
    return tags, secs, msh


def solve_one(work, timeout, log):
    """ElmerGrid + write_sif + ElmerSolver (Leerlauf) unter /usr/bin/time -v.
    Returns dict mit Zeiten, Peak-RSS (kB), Elmer-DOFs, ok/Fehler."""
    out = {"grid_s": None, "solve_s": None, "peak_rss_kb": None,
           "dofs": None, "ok": False, "error": None, "returncode": None}

    # ElmerGrid
    t0 = time.perf_counter()
    rg = ER.run_elmergrid(os.path.join(work, "motor3d.msh"), os.path.join(work, "mesh"))
    out["grid_s"] = time.perf_counter() - t0
    if not rg["ok"]:
        out["error"] = "ElmerGrid: " + (rg.get("stderr") or rg.get("error", ""))[:200]
        return out

    # sif (Leerlauf-Magnetostatik)
    E3.write_sif(GEOM, {"skew_deg": 0.0}, _LAST_TAGS[0], work, mesh_name="mesh")

    # ElmerSolver unter /usr/bin/time -v → Peak-RSS
    cmd = [TIME_BIN, "-v", ER.ELMERSOLVER, "case.sif"]
    t0 = time.perf_counter()
    try:
        proc = subprocess.run(cmd, cwd=work, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        out["error"] = f"ElmerSolver Timeout (> {timeout}s)"
        out["solve_s"] = float(timeout)
        return out
    out["solve_s"] = time.perf_counter() - t0
    out["returncode"] = proc.returncode

    terr = proc.stderr or ""
    m = re.search(r"Maximum resident set size \(kbytes\):\s*(\d+)", terr)
    if m:
        out["peak_rss_kb"] = int(m.group(1))
    sout = proc.stdout or ""
    md = re.search(r"Number of (?:degrees of freedom|dofs)\s*[:=]?\s*(\d+)", sout, re.I)
    if md:
        out["dofs"] = int(md.group(1))
    out["ok"] = ("ELMER SOLVER FINISHED" in sout.upper()) or ("ALL DONE" in sout.upper())
    if not out["ok"]:
        if proc.returncode == 137 or "killed" in terr.lower():
            out["error"] = "ElmerSolver OOM-Killed (RC 137)"
        else:
            out["error"] = "ElmerSolver nicht beendet (RC %s): %s" % (
                proc.returncode, (terr[-200:] or sout[-200:]))
    return out


_LAST_TAGS = [None]   # Brücke zwischen build_one_mesh und solve_one


def main():
    ap = argparse.ArgumentParser(description="Performance-Check der 3D-Elmer-Berechnung")
    ap.add_argument("--max-nodes", type=int, default=500000,
                    help="Obergrenze der Knotenzahl, bei der abgebrochen wird (Default 500000)")
    ap.add_argument("--timeout", type=int, default=2400,
                    help="Timeout je ElmerSolver-Lauf in Sekunden (Default 2400 = 40 min)")
    ap.add_argument("--ram-stop", type=float, default=0.80,
                    help="Abbruch, wenn Peak-RSS diesen Anteil des Gesamt-RAM übersteigt (Default 0.80)")
    ap.add_argument("--calibrate", action="store_true",
                    help="Nur meshen (Faktor→Knoten kartieren), NICHT lösen — schnell + RAM-arm")
    ap.add_argument("--factors", type=str, default="",
                    help="Komma-Liste eigener Zellgrößen-Skalierungen (sonst automatische Leiter)")
    ap.add_argument("--out", type=str,
                    default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "em3d_perf"),
                    help="Ausgabe-Basispfad (.csv/.json)")
    args = ap.parse_args()

    if not ER.ELMER_OK and not args.calibrate:
        print("Elmer nicht gefunden — nur --calibrate möglich.\n" + ER.INSTALL_HINT)
        return 1
    if not os.path.exists(TIME_BIN) and not args.calibrate:
        print(f"{TIME_BIN} fehlt (für RAM-Messung nötig). apt install time")
        return 1

    total_ram = _total_ram_kb()
    print("=" * 78)
    print("  3D-EM Performance-Check (Elmer Magnetostatik, Leerlauf)")
    print(f"  Geometrie: {GEOM['statorOD']}mm OD, {GEOM['p']*2} Pole, {GEOM['slots']} Nuten, "
          f"V-Magnete, L={AXIAL:.0f}mm")
    print(f"  System-RAM gesamt: {_fmt_kb(total_ram)}, frei jetzt: {_fmt_kb(_avail_ram_kb())}")
    print(f"  Aktuelles EM3D_MAX_NODES = {E3.EM3D_MAX_NODES}")
    print(f"  Ziel bis {args.max_nodes} Knoten | Solve-Timeout {args.timeout}s | "
          f"RAM-Stop {args.ram_stop*100:.0f}%")
    print("=" * 78)

    # Zellgrößen-Skalierungs-Leiter (kleiner = feiner). Empirisch so gestaffelt, dass die
    # Knotenzahl grob verdoppelt bis ~500k. Wird bei Bedarf dynamisch weiter verfeinert.
    if args.factors.strip():
        ladder = [float(x) for x in args.factors.split(",") if x.strip()]
    else:
        # Empirisch (V-Motor, 280mm): scale 1.30 → ~163k Knoten; die Auto-Zellgröße (1.0)
        # liegt also schon WEIT über EM3D_MAX_NODES=55k (Produktion vergröbert per Cap darauf).
        # Daher spannt die Leiter von GROB (scale≈3.6 → ~15k) bis FEIN (scale≈0.80 → ~500k+).
        ladder = [3.6, 2.9, 2.3, 1.85, 1.5, 1.30, 1.10, 0.95, 0.83, 0.72]

    work = os.path.join("/tmp", "em3d_perf_work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work, exist_ok=True)

    rows = []
    hdr = (f"{'#':>2} {'scale':>6} {'Knoten':>9} {'Mesh s':>8} {'Grid s':>8} "
           f"{'Solve s':>9} {'Peak RSS':>11} {'kB/Knoten':>10}  Status")
    print("\n" + hdr)
    print("-" * len(hdr))

    last_rss = 0
    for i, scale in enumerate(ladder, 1):
        try:
            tags, mesh_s, _ = build_one_mesh(scale, work, log=lambda m: None)
        except Exception as e:
            print(f"{i:>2} {scale:>6.3f}  Mesh-Fehler: {e}")
            continue
        n = tags["n_nodes"]
        _LAST_TAGS[0] = tags

        row = {"i": i, "scale": scale, "n_nodes": n, "mesh_s": round(mesh_s, 1),
               "grid_s": None, "solve_s": None, "peak_rss_kb": None,
               "kb_per_node": None, "dofs": None, "ok": None, "status": ""}

        if args.calibrate:
            row["status"] = "nur Mesh"
            print(f"{i:>2} {scale:>6.3f} {n:>9d} {mesh_s:>8.1f} {'—':>8} "
                  f"{'—':>9} {'—':>11} {'—':>10}  (calibrate)")
            rows.append(row)
            _save(args.out, rows, total_ram)
            if n >= args.max_nodes:
                print(f"\n→ {args.max_nodes} Knoten erreicht — Kalibrierung fertig.")
                break
            continue

        # RAM-Wächter (auf Basis der letzten Messung)
        if last_rss and total_ram and last_rss > args.ram_stop * total_ram:
            print(f"\n→ Abbruch: letzter Peak-RSS {_fmt_kb(last_rss)} > "
                  f"{args.ram_stop*100:.0f}% von {_fmt_kb(total_ram)}.")
            break

        res = solve_one(work, args.timeout, log=lambda m: None)
        row.update({"grid_s": None if res["grid_s"] is None else round(res["grid_s"], 1),
                    "solve_s": None if res["solve_s"] is None else round(res["solve_s"], 1),
                    "peak_rss_kb": res["peak_rss_kb"], "dofs": res["dofs"],
                    "ok": res["ok"]})
        if res["peak_rss_kb"] and n:
            row["kb_per_node"] = round(res["peak_rss_kb"] / n, 2)
        row["status"] = "OK" if res["ok"] else (res["error"] or "Fehler")[:40]

        print(f"{i:>2} {scale:>6.3f} {n:>9d} {mesh_s:>8.1f} "
              f"{(row['grid_s'] if row['grid_s'] is not None else 0):>8.1f} "
              f"{(row['solve_s'] if row['solve_s'] is not None else 0):>9.1f} "
              f"{_fmt_kb(res['peak_rss_kb']):>11} "
              f"{(row['kb_per_node'] if row['kb_per_node'] else 0):>10.2f}  {row['status']}")

        rows.append(row)
        _save(args.out, rows, total_ram)

        if res["peak_rss_kb"]:
            last_rss = res["peak_rss_kb"]
        if not res["ok"]:
            print(f"\n→ Abbruch bei {n} Knoten: {res['error']}")
            break
        if n >= args.max_nodes:
            print(f"\n→ {args.max_nodes} Knoten erreicht/überschritten — Ziel erreicht.")
            break

    print("\nGespeichert: %s.csv / %s.json" % (args.out, args.out))
    _summary(rows, total_ram)
    return 0


def _save(base, rows, total_ram):
    with open(base + ".json", "w") as f:
        json.dump({"total_ram_kb": total_ram, "rows": rows}, f, indent=2)
    cols = ["i", "scale", "n_nodes", "dofs", "mesh_s", "grid_s", "solve_s",
            "peak_rss_kb", "kb_per_node", "ok", "status"]
    with open(base + ".csv", "w") as f:
        f.write(",".join(cols) + "\n")
        for r in rows:
            f.write(",".join(str(r.get(c, "")) for c in cols) + "\n")


def _summary(rows, total_ram):
    done = [r for r in rows if r.get("ok")]
    if len(done) < 2:
        return
    print("\n" + "=" * 60 + "\n  Auswertung\n" + "=" * 60)
    # RAM-Skalierung linear extrapolieren (kB/Knoten des größten erfolgreichen Laufs)
    biggest = max(done, key=lambda r: r["n_nodes"])
    if biggest.get("kb_per_node"):
        kpn = biggest["kb_per_node"]
        print(f"  Größter OK-Lauf: {biggest['n_nodes']} Knoten, "
              f"{_fmt_kb(biggest['peak_rss_kb'])}, {biggest['solve_s']}s "
              f"({kpn:.2f} kB/Knoten)")
        if total_ram:
            n_ram = total_ram / kpn
            print(f"  → linear extrapoliert reicht der RAM ({_fmt_kb(total_ram)}) "
                  f"für ~{n_ram/1000:.0f}k Knoten")
    # Solve-Zeit-Skalierung (Potenzgesetz-Fit über die letzten Punkte)
    if len(done) >= 3:
        import math as _m
        a, b = done[0], done[-1]
        if a["solve_s"] and b["solve_s"] and a["n_nodes"] != b["n_nodes"]:
            p = _m.log(b["solve_s"] / a["solve_s"]) / _m.log(b["n_nodes"] / a["n_nodes"])
            print(f"  Solve-Zeit skaliert ~ Knoten^{p:.2f}  "
                  f"({a['n_nodes']}→{b['n_nodes']} Knoten: {a['solve_s']}→{b['solve_s']}s)")


if __name__ == "__main__":
    sys.exit(main())
