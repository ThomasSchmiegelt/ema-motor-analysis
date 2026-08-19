"""Erzeugt den Trainingsdatensatz für das 2D-FDM-Surrogat (Stufe 1).

Läuft im **Flask-venv** des Orchestrators (kein Torch nötig) und ruft den echten Löser:
je Geometrie einmal `_rasterise` + eine Faktorisierung, dann zwei Rücksubstitutionen für
die beiden Quellen (Magnete / Statorströme). Das ist derselbe Hebel, den die Pipeline
schon nutzt — der FV-Operator hängt nur von µ ab, nicht von der Quelle
(`ema_analysis.py:27-45`), also kostet die zweite Quelle fast nichts.

Ein Datensatz-Eintrag ist ein Paar (Material, Quelle) → A, siehe
`physics_surrogate/data/encode2d.py`. Gespeichert wird bereits **normiert**, also genau
das, was der Verlust sieht.

    python gen_fdm_dataset.py --dry-run              # 3 Geometrien + Selbsttests
    python gen_fdm_dataset.py --n 500                # Pilotlauf (~20 min)
    python gen_fdm_dataset.py --n 5000 --workers 2   # Vollausbau (nachts, nohup)

Wiederaufnehmbar: ein Lauf hängt an `manifest.jsonl` an und überspringt fertige Indizes.
"""

import argparse
import json
import os
import sys
import time
import traceback

import numpy as np

sys.path.insert(0, os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "..", "physics_surrogate", "data")))

import domain                      # noqa: E402  (geteilte Gültigkeitsgrenze)
import encode2d                    # noqa: E402
import ema_analysis as ea          # noqa: E402
import ema_optimize as eo          # noqa: E402

# Basismaschine: dieselbe V-IPM wie in smoke_test/test_fdm_golden, damit alle Tests über
# dieselbe Maschine reden. Was NICHT in FREE_PARAMS steht (statorOD/rotorOD/shaftD/slots),
# bleibt fest — der trainierte Bereich ist genau die Suchbox des Optimierers.
BASE_GEOM = {
    "statorOD": 280, "statorID": 190, "rotorOD": 188.6, "shaftD": 60, "shaftBoreD": 0,
    "slots": 54, "slotDepth": 25, "slotWidthRatio": 0.5, "p": 3,
    "magShape": "v", "magAngle": 120, "magDepthRel": 0.7, "magWidth": 45, "magThick": 6,
    "magDist": 2, "magLayers": 3, "magLayerGap": 8, "poleArcFrac": 0.83, "segPerPole": 6,
    "nAx": 1, "nCirc": 1, "magTangLen": 0, "magAngle2": 90, "pocketMode": "position",
    "pocketOuterD": 178, "pocketInnerD": 150, "magOrient": "transverse",
}
BASE_AXIAL = 120.0

# Topologien, über die mitgesampelt wird (magShape steckt nicht in FREE_PARAMS, prägt das
# Feld aber stärker als jeder Zahlenwert). "custom" bleibt draußen — v1 ist parametrisch.
SHAPES = ("v", "vasym", "vv", "u", "delta", "pmasynrm", "spm", "halbach", "spoke", "bar")

# Statorstromamplitude für die Statorquelle. Der Wert ist **irrelevant**: `_rasterise`
# ist linear in (iq, id_), und `encode2d` normiert auf max|J|. Nur der Stromwinkel β
# prägt das Muster, deshalb wird der gesampelt.
I_AMP = 200.0


def sampling_bounds() -> dict:
    """Die Box, in der gezogen wird: FREE_PARAMS ∩ baubar, ohne die inerten Parameter."""
    return domain.effective_bounds(BASE_GEOM, exclude=domain.STAGE1_INERT)


def _sample(n_draw: int, seed: int) -> list[dict]:
    """Latin-Hypercube über die wirksamen, baubaren Parameter + magShape + Winkel.

    Gezogen wird in `sampling_bounds()`, NICHT in der rohen FREE_PARAMS-Box: die ist
    erheblich größer als die baubare Menge dieser Basismaschine (gemessen ~4 % Annahme,
    dominiert von `slotDepth` ≤ 150 mm gegen ~44 mm Statorwand). Blind ziehen und
    verwerfen würde die Raumfüllung des LHS zerstören.

    Der Machbarkeitsfilter in `_build` bleibt trotzdem aktiv — die geschnittene Box ist
    notwendig, aber nicht hinreichend (z. B. hängen `magWidth`/`magAngle`/`magDepthRel`
    zusammen und werden erst von `magnet_legs` geklemmt).
    """
    try:
        from scipy.stats import qmc
    except ImportError:                                       # pragma: no cover
        raise SystemExit("scipy.stats.qmc fehlt — bitte scipy>=1.7 installieren.")

    box = sampling_bounds()
    keys = list(box)
    # +3 Extra-Dimensionen: magShape, Rotorwinkel, Stromwinkel
    sampler = qmc.LatinHypercube(d=len(keys) + 3, seed=seed)
    u = sampler.random(n_draw)

    out = []
    for row in u:
        params = {}
        for j, key in enumerate(keys):
            lo, hi = box[key]
            params[key] = lo + row[j] * (hi - lo)
        out.append({
            "params": eo._clamp(params),                       # Typ + Bereichsklemmung
            "magShape": SHAPES[min(int(row[-3] * len(SHAPES)), len(SHAPES) - 1)],
            "rotor_u": float(row[-2]),                         # Anteil einer Polteilung
            "beta": float(row[-1] * 2 * np.pi),                # Stromwinkel
        })
    return out


def _build(cand: dict) -> tuple[dict, float, float, float, float] | None:
    """Kandidat → (geom, axial, rotor_angle, iq, id_) oder None, wenn nicht baubar."""
    geom, axial = eo._apply_params(BASE_GEOM, BASE_AXIAL, cand["params"])
    geom["magShape"] = cand["magShape"]
    problems = domain.feasibility_problems(geom, axial)
    if problems:
        return None, problems
    # Rotorwinkel innerhalb EINER Polteilung — darüber hinaus ist das Feld periodisch.
    pole_pitch = np.pi / max(1, int(geom["p"]))
    rotor_angle = cand["rotor_u"] * pole_pitch
    iq = I_AMP * np.sin(cand["beta"])
    id_ = I_AMP * np.cos(cand["beta"])
    return (geom, axial, float(rotor_angle), float(iq), float(id_)), []


def _one(job: tuple) -> dict:
    """EINE Geometrie rechnen und als NPZ ablegen. Läuft ggf. im Worker-Prozess."""
    idx, cand, n, out_dir = job
    t0 = time.time()
    built, problems = _build(cand)
    if built is None:
        return {"i": idx, "ok": False, "reason": "; ".join(problems)}
    geom, axial, rotor_angle, iq, id_ = built

    try:
        mat, j_mag, j_stat, maps = encode2d.rasterise(geom, n, rotor_angle, iq, id_)
        rp = domain.raster_problems(maps, n)
        if rp:
            return {"i": idx, "ok": False, "reason": "; ".join(rp)}

        # µ exakt aus der Materialmaske — dieselbe Matrix, die _rasterise gebaut hat
        # (im --dry-run gegen das Original assertiert).
        mu = encode2d.mu_from_mat(mat)

        x_mag, alpha_mag = encode2d.encode(mat, j_mag)
        x_stat, alpha_stat = encode2d.encode(mat, j_stat)

        # Eine Faktorisierung (µ), zwei Rücksubstitutionen (die Quellen).
        a_mag = ea._solve_fdm(mu, j_mag)
        a_stat = ea._solve_fdm(mu, j_stat)

        a_mag_n = encode2d.encode_target(a_mag, alpha_mag)
        a_stat_n = encode2d.encode_target(a_stat, alpha_stat)
        for name, arr in (("A_magnet", a_mag_n), ("A_stator", a_stat_n)):
            if not np.all(np.isfinite(arr)):
                return {"i": idx, "ok": False, "reason": f"{name} nicht endlich"}

        # Quelle in float32, Ziel in float16 — der Unterschied ist NICHT Kosmetik:
        # Das Ziel wurde aus der float32-Quelle gelöst. Legt man die Quelle in float16 ab,
        # ist das Paar (Eingang, Ziel) inkonsistent, denn der Löser verstärkt Rauschen in
        # der Quelle deutlich (die Statorquelle lebt von Auslöschung zwischen benachbarten
        # Nuten, das Quantisierungsrauschen löscht sich nicht mit aus). Gemessen über 12
        # Geometrien: Median 0,7e-3 (Magnet) bzw. 2,4e-3 (Stator), Maximum 1,2e-2 — bei
        # einem Genauigkeitsziel von 3 % wäre das ein Drittel des Budgets, verschenkt an
        # eine Ablage-Entscheidung. Kosten der Korrektur: +1 MB je Geometrie.
        # Das Ziel selbst darf float16 bleiben: dessen Quantisierung (~8e-4 relativ) wird
        # nicht verstärkt, sie ist unverzerrtes Label-Rauschen weit unter dem Ziel.
        path = os.path.join(out_dir, f"{idx:06d}.npz")
        np.savez(
            path,
            mat=mat,                                   # uint8, Material
            j_magnet=x_mag[3],                         # float32, bereits normiert (Kanal 3)
            j_stator=x_stat[3],
            a_magnet=a_mag_n.astype(np.float16),       # normierte Zielgrößen
            a_stator=a_stat_n.astype(np.float16),
        )
        return {
            "i": idx, "ok": True, "file": os.path.basename(path), "n": n,
            "magShape": geom["magShape"], "params": cand["params"],
            "rotor_angle": rotor_angle, "iq": iq, "id": id_,
            "alpha_magnet": alpha_mag, "alpha_stator": alpha_stat,
            "secs": round(time.time() - t0, 2),
        }
    except Exception as e:                                     # pragma: no cover
        return {"i": idx, "ok": False,
                "reason": f"{type(e).__name__}: {str(e)[:160]}",
                "trace": traceback.format_exc()[-400:]}
    finally:
        # Jede Geometrie hat ihr eigenes µ ⇒ der LU-Cache (48 Einträge) würde bei N=512
        # sonst GB fressen.
        ea.clear_lu_cache()


def _dry_run(n: int):
    """Drei Geometrien + die Selbsttests, die den Encoder-Vertrag festnageln."""
    print(f"Dry-Run bei N={n}\n" + "=" * 60)
    box = sampling_bounds()
    print("Sampling-Box (FREE_PARAMS ∩ baubar):")
    for k, (lo, hi) in box.items():
        raw = domain.FREE_PARAMS[k]
        mark = "  ← geschnitten" if (lo, hi) != (raw["lo"], raw["hi"]) else ""
        print(f"  {k:12s} [{lo:8.3g}, {hi:8.3g}]   roh [{raw['lo']:g}, {raw['hi']:g}]{mark}")
    print(f"  nicht gesampelt (ohne Wirkung aufs 2D-Feld): {', '.join(domain.STAGE1_INERT)}")
    print()
    cands = _sample(24, seed=0)
    done = 0
    for idx, cand in enumerate(cands):
        built, problems = _build(cand)
        if built is None:
            print(f"  [{idx:02d}] verworfen: {problems[0]}")
            continue
        geom, axial, ra, iq, id_ = built

        mat, j_mag, j_stat, maps = encode2d.rasterise(geom, n, ra, iq, id_)

        # 1. Die Materialmaske codiert µ vollständig und exakt.
        mu_ref, _j, _s, _c = ea._rasterise(geom, n, rotor_angle=ra, iq=iq, id_=id_)
        assert np.array_equal(encode2d.mu_from_mat(mat), mu_ref), \
            "mu_from_mat(mat) != mu aus _rasterise — Maskencodierung ist verlustbehaftet"

        # 2. Die Quellenaufspaltung ist exakt (Linearität in J).
        assert np.allclose(j_mag + j_stat, _j, atol=1e-5), "J_magnet + J_stator != J"

        # 3. encode/decode ist ein Rundlauf.
        x, alpha = encode2d.encode(mat, j_mag)
        a = ea._solve_fdm(mu_ref, j_mag)
        ea.clear_lu_cache()
        assert np.allclose(encode2d.decode_target(encode2d.encode_target(a, alpha), alpha),
                           a, rtol=1e-5), "encode_target/decode_target ist kein Rundlauf"
        assert x.shape == (encode2d.N_CHANNELS, n, n) and x.dtype == np.float32
        # Die drei Masken partitionieren das Gitter (One-Hot).
        assert np.array_equal(x[0] + x[1] + x[2], np.ones((n, n), np.float32))
        assert abs(float(np.max(np.abs(x[3]))) - 1.0) < 1e-6, "Kanal J ist nicht auf 1 normiert"

        a_n = encode2d.encode_target(a, alpha)
        print(f"  [{idx:02d}] {geom['magShape']:9s} p={geom['p']:2d} "
              f"Luftspalt={(geom['statorID'] - geom['rotorOD']) / 2:.2f} mm  "
              f"α={alpha:8.3f}  |A_n|max={np.max(np.abs(a_n)):6.3f}  "
              f"Magnet-px={float(maps['magnet'].sum()) / n / n:.3%}")
        done += 1
        if done >= 3:
            break

    assert done == 3, "keine 3 baubaren Geometrien in 24 Zügen — Filter zu streng?"
    print("\n✓ Maskencodierung verlustfrei · Quellenaufspaltung exakt · "
          "encode/decode-Rundlauf · Kanäle normiert")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=500, help="Anzahl baubarer Geometrien")
    ap.add_argument("--grid", type=int, default=512, help="Gitterauflösung N")
    ap.add_argument("--out", default=None, help="Zielverzeichnis (Vorgabe: datasets/fdm_<N>)")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1,
                    help="Parallele Prozesse (je ~1 GB RSS bei N=512)")
    ap.add_argument("--oversample", type=float, default=3.0,
                    help="Faktor, um den mehr Kandidaten gezogen als gebraucht werden")
    ap.add_argument("--shapes", default=None,
                    help="nur diese Topologien (Komma-Liste) — für gezielten Nachschlag, "
                         "wenn eine Topologie überdurchschnittlich verworfen wurde. "
                         "--n zählt dann die ZIELZAHL für diese Topologien.")
    ap.add_argument("--index-offset", type=int, default=0,
                    help="Versatz der Sample-Indizes, damit ein Nachschlag mit anderem "
                         "--seed nicht mit vorhandenen Dateien kollidiert")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    want_shapes = (set(s.strip() for s in args.shapes.split(",") if s.strip())
                   if args.shapes else None)
    if want_shapes and not want_shapes <= set(SHAPES):
        raise SystemExit(f"unbekannte Topologie(n): {want_shapes - set(SHAPES)}")

    if args.dry_run:
        _dry_run(args.grid)
        return

    out_dir = args.out or os.path.normpath(os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "..", "physics_surrogate",
        "datasets", f"fdm_{args.grid}"))
    os.makedirs(out_dir, exist_ok=True)
    man_path = os.path.join(out_dir, "manifest.jsonl")
    rej_path = os.path.join(out_dir, "rejected.jsonl")

    # Wiederaufnahme: was schon im Manifest steht, wird übersprungen. `have` zählt nur
    # die Einträge, die zur aktuellen Zielmenge gehören (bei --shapes also nur diese).
    done_idx = set()
    have = 0
    if os.path.exists(man_path):
        with open(man_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                done_idx.add(rec["i"])
                if not want_shapes or rec.get("magShape") in want_shapes:
                    have += 1
        print(f"Wiederaufnahme: {len(done_idx)} Einträge vorhanden, davon {have} "
              f"in der Zielmenge.")

    # meta.json beschreibt den Datensatz als Ganzes; ein Nachschlag darf es nicht
    # überschreiben (sonst stünde dort der Seed des Nachschlags statt des Hauptlaufs),
    # sondern hängt sich als Eintrag an.
    meta_path = os.path.join(out_dir, "meta.json")
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            meta = json.load(f)
        meta.setdefault("topups", []).append(
            {"shapes": sorted(want_shapes) if want_shapes else "alle",
             "seed": args.seed, "index_offset": args.index_offset, "target": args.n,
             "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
    else:
        meta = {"grid": args.grid, "seed": args.seed, "base_geom": BASE_GEOM,
                "base_axial": BASE_AXIAL, "shapes": list(SHAPES), "i_amp": I_AMP,
                "a_scale": encode2d.A_SCALE,
                "bounds": {k: list(v) for k, v in sampling_bounds().items()},
                "inert_params": list(domain.STAGE1_INERT),
                "channels": list(encode2d.CHANNEL_NAMES),
                "created": time.strftime("%Y-%m-%dT%H:%M:%S")}
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=1)

    # Bei --shapes muss entsprechend stärker überabgetastet werden (nur ein Bruchteil der
    # Kandidaten trägt die gesuchte Topologie).
    draw = int(args.n * args.oversample)
    if want_shapes:
        draw = int(draw * len(SHAPES) / len(want_shapes))
    cands = _sample(draw, seed=args.seed)
    jobs = [(i + args.index_offset, c, args.grid, out_dir)
            for i, c in enumerate(cands)
            if (i + args.index_offset) not in done_idx
            and (not want_shapes or c["magShape"] in want_shapes)]

    print(f"Ziel {args.n} Geometrien"
          + (f" der Topologie(n) {sorted(want_shapes)}" if want_shapes else "")
          + f" bei N={args.grid} → {out_dir}")
    print(f"{len(jobs)} Kandidaten zu prüfen, {args.workers} Worker\n")

    kept = have
    added = 0
    rejected = 0
    t0 = time.time()

    def _handle(res, man, rej):
        nonlocal kept, added, rejected
        if res.get("ok"):
            man.write(json.dumps(res) + "\n"); man.flush()
            kept += 1
            added += 1
            rate = (time.time() - t0) / added
            print(f"  [{kept:5d}/{args.n}] {res['magShape']:9s} {res['secs']:5.2f}s  "
                  f"⌀{rate:4.2f}s  Rest ≈{(args.n - kept) * rate / 60:5.1f} min", flush=True)
        else:
            rej.write(json.dumps(res) + "\n"); rej.flush()
            rejected += 1

    with open(man_path, "a") as man, open(rej_path, "a") as rej:
        if args.workers > 1:
            import multiprocessing as mp
            with mp.get_context("spawn").Pool(args.workers) as pool:
                for res in pool.imap_unordered(_one, jobs):
                    _handle(res, man, rej)
                    if kept >= args.n:
                        pool.terminate()
                        break
        else:
            for job in jobs:
                _handle(_one(job), man, rej)
                if kept >= args.n:
                    break

    el = time.time() - t0
    size_gb = sum(os.path.getsize(os.path.join(out_dir, f))
                  for f in os.listdir(out_dir) if f.endswith(".npz")) / 1e9
    print(f"\nFertig: {kept} Geometrien, {rejected} verworfen "
          f"({rejected / max(1, kept + rejected):.0%} Ausschuss), "
          f"{el / 60:.1f} min, {size_gb:.2f} GB")
    if kept < args.n:
        print(f"WARNUNG: nur {kept} von {args.n} erreicht — --oversample erhöhen.")


if __name__ == "__main__":
    main()
