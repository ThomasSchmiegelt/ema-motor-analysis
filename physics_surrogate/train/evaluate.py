"""Abnahme Stufe 1 auf dem Halteset.

    physics_surrogate/.venv/bin/python train/evaluate.py            # ganzes Halteset
    ... train/evaluate.py --n 400                                   # Stichprobe
    ... train/evaluate.py --checkpoint /pfad/fdm.mdlus

Gemessen wird auf **denselben** Geometrien, die `train_fdm.py` nie gesehen hat (gleicher
Split-Seed, gleiche Aufteilung nach Geometrie).

Vorhergesagt wird das **Muster** ``A/RMS(A)`` — die Amplitude liefert der Orchestrator
analytisch (`encode2d.pattern`). Die Luftspalt-Gates bilden deshalb genau dessen
Kalibrierung nach: jede Kurve wird auf ihren eigenen ``max|B_r|`` bezogen, so wie
`run_em_analysis:1053` mit ``sf = B_analytisch/max|Br|`` skaliert. Der ausgewiesene
Fehler ist damit der Fehler in Tesla, den der Nutzer sehen würde.

**Die Luftspaltkurven kommen hier aus der echten Numpy-Funktion `_sample_airgap`**, nicht
aus der Torch-Spiegelung des Trainings. Das ist Absicht: die Abnahme soll die Größe
messen, die der Orchestrator später tatsächlich benutzt. Dass beide bitgenau
übereinstimmen, prüft `tests/test_airgap_torch.py` — hier wird es nicht vorausgesetzt.

Gates (aus dem Plan):

    rel. L2 auf A            < 3 %
    RMSE B_r(θ)              < 3 % des B_r-Spitzenwerts
    RMSE B_t(θ)              < 8 % des B_r-Spitzenwerts
    Inferenz (1 Sample, GPU) < 100 ms

`T_maxwell` ist **kein** Gate: es folgt aus `mean(B_r·B_t)` und ist über die Auflösung
nicht stabil (0,29 → 0,91 → 0,52 Nm bei N = 360/512/700). Es wird bei festem N=512 als
Beobachtungsgröße mitgeloggt, damit man die Größenordnung im Blick behält.
"""

import argparse
import json
import os
import time

import numpy as np
import torch

import common as C
import dataset as D
from physicsnemo import Module

GATES = {
    "rel_l2_A": 0.03,
    "rmse_Br_rel_peak": 0.03,
    "rmse_Bt_rel_Br_peak": 0.08,
    "latency_ms": 100.0,
}


def _items(meta: dict, recs: list[dict]) -> list[tuple]:
    out = []
    for rec in recs:
        geom = D.geom_of(meta, rec)
        out.append((rec, "magnet", geom))
        if float(rec.get("alpha_stator", 0)) > 0:
            out.append((rec, "stator", geom))
    return out


def _latency_ms(model, n: int, n_ch: int, device: str, dtype, reps: int = 30) -> float:
    """Zeit für EIN Sample, warm — das ist die Zahl, die die UI später spürt.

    Nur der Netzdurchlauf. Rasterisierung (~30 ms) und, falls aktiv, der Freiraumkanal
    (~9 ms bei N=512) kommen im Dienst obendrauf; sie stehen in AP1.4 im Budget.
    """
    x = torch.zeros(1, n_ch, n, n, device=device)
    with torch.no_grad():
        for i in range(reps + 5):
            if i == 5 and device == "cuda":
                torch.cuda.synchronize()
                t0 = time.perf_counter()
            with torch.autocast(device, dtype=dtype, enabled=dtype != torch.float32):
                model(x)
        if device == "cuda":
            torch.cuda.synchronize()
    return (time.perf_counter() - t0) / reps * 1000.0


def evaluate(cfg: dict, ckpt: str, n_max: int = 0, batch: int = 4) -> dict:
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = C.amp_dtype(cfg) if device == "cuda" else torch.float32
    meta, _tr, va = C.make_splits(cfg)
    items = _items(meta, va)
    if n_max:
        items = items[:n_max]
    n_grid = int(meta["grid"])
    root = cfg["data"]["root"]

    model = Module.from_checkpoint(ckpt).to(device).eval()
    n_ch = len(C.encode2d.channel_names(C.free_space(cfg)))
    lat = _latency_ms(model, n_grid, n_ch, device, dtype)

    rows = []
    t0 = time.time()
    for start in range(0, len(items), batch):
        chunk = items[start:start + batch]
        xs, ys = zip(*(D.load_sample(root, rec, src, free_space=C.free_space(cfg))
                       for rec, src, _g in chunk))
        x = torch.from_numpy(np.stack(xs)).to(device)
        with torch.no_grad(), torch.autocast(device, dtype=dtype,
                                             enabled=dtype != torch.float32):
            pred = model(x)
        pred = pred.float().cpu().numpy()[:, 0]

        for (rec, src, geom), p, t in zip(chunk, pred, ys):
            # Genau die Kalibrierung des Orchestrators nachvollziehen: jede Kurve wird
            # auf ihren EIGENEN Br-Spitzenwert bezogen, weil `run_em_analysis:1053`
            # mit `sf = B_analytisch / max|Br|` skaliert. Der so gemessene Fehler ist
            # damit der Fehler, den der Nutzer in Tesla sieht.
            br_p, bt_p = C.np_airgap(p, geom, n_grid)
            br_t, bt_t = C.np_airgap(t, geom, n_grid)
            sf_p = 1.0 / max(float(np.max(np.abs(br_p))), 1e-30)
            sf_t = 1.0 / max(float(np.max(np.abs(br_t))), 1e-30)
            br_p, bt_p = br_p * sf_p, bt_p * sf_p
            br_t, bt_t = br_t * sf_t, bt_t * sf_t
            tm_t, tm_p = float(np.mean(br_t * bt_t)), float(np.mean(br_p * bt_p))
            rows.append({
                "file": rec["file"], "src": src, "magShape": rec["magShape"],
                "rel_l2_A": float(np.linalg.norm(p - t) / max(np.linalg.norm(t), 1e-30)),
                "rmse_Br_rel_peak": float(np.sqrt(np.mean((br_p - br_t) ** 2))),
                "rmse_Bt_rel_Br_peak": float(np.sqrt(np.mean((bt_p - bt_t) ** 2))),
                "Bt_peak_rel": float(np.max(np.abs(bt_t))),
                "T_maxwell_rel_err": (abs(tm_p - tm_t) / abs(tm_t)
                                      if abs(tm_t) > 1e-30 else float("nan")),
            })
        if start % (batch * 50) == 0:
            print(f"  {start + len(chunk)}/{len(items)} …", flush=True)

    return {"rows": rows, "latency_ms": lat, "device": device, "grid": n_grid,
            "secs": time.time() - t0, "n_val_geometries": len(va)}


def _stats(rows: list[dict], key: str) -> dict:
    v = np.array([r[key] for r in rows], dtype=float)
    v = v[np.isfinite(v)]
    if not len(v):
        return {"mean": float("nan"), "p95": float("nan"), "max": float("nan")}
    return {"mean": float(v.mean()), "p95": float(np.percentile(v, 95)),
            "max": float(v.max())}


def report(res: dict) -> bool:
    rows = res["rows"]
    print(f"\nHalteset: {res['n_val_geometries']} Geometrien → {len(rows)} Beispiele, "
          f"N={res['grid']}, {res['device']}, {res['secs']:.0f} s\n")
    print(f"{'Metrik':24s} {'Mittel':>9s} {'p95':>9s} {'max':>9s}   Gate")
    ok = True
    for key in ("rel_l2_A", "rmse_Br_rel_peak", "rmse_Bt_rel_Br_peak"):
        s = _stats(rows, key)
        gate = GATES[key]
        good = s["mean"] < gate
        ok &= good
        print(f"{key:24s} {s['mean']:9.4f} {s['p95']:9.4f} {s['max']:9.4f}   "
              f"< {gate:.2f}  {'✓' if good else '✗'}")
    good = res["latency_ms"] < GATES["latency_ms"]
    ok &= good
    print(f"{'latency_ms (1 Sample)':24s} {res['latency_ms']:9.1f} "
          f"{'':9s} {'':9s}   < {GATES['latency_ms']:.0f}    {'✓' if good else '✗'}")

    s = _stats(rows, "T_maxwell_rel_err")
    print(f"\nBeobachtung (kein Gate) — T_maxwell ∝ mean(B_r·B_t) bei festem N={res['grid']}:")
    print(f"  rel. Fehler  Mittel {s['mean']:.3f}  p95 {s['p95']:.3f}  max {s['max']:.3f}")
    s = _stats(rows, "Bt_peak_rel")
    print(f"  |B_t|max / |B_r|max im Ziel: Mittel {s['mean']:.3f}  max {s['max']:.3f}")

    print("\nnach Quelle:")
    for src in ("magnet", "stator"):
        sub = [r for r in rows if r["src"] == src]
        if sub:
            print(f"  {src:7s} n={len(sub):5d}  A {_stats(sub, 'rel_l2_A')['mean']:.4f}  "
                  f"Br {_stats(sub, 'rmse_Br_rel_peak')['mean']:.4f}  "
                  f"Bt {_stats(sub, 'rmse_Bt_rel_Br_peak')['mean']:.4f}")
    print("\nnach Topologie (rel. L2 auf A):")
    for shape in sorted({r["magShape"] for r in rows}):
        sub = [r for r in rows if r["magShape"] == shape]
        print(f"  {shape:10s} n={len(sub):5d}  {_stats(sub, 'rel_l2_A')['mean']:.4f}  "
              f"Br {_stats(sub, 'rmse_Br_rel_peak')['mean']:.4f}")
    print("\n" + ("ABNAHME BESTANDEN ✅" if ok else "ABNAHME NICHT BESTANDEN ❌"))
    return ok


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "conf", "fdm.yaml"))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=WERT")
    ap.add_argument("--checkpoint", default=None)
    ap.add_argument("--n", type=int, default=0, help="nur die ersten N Beispiele")
    ap.add_argument("--json", default=None, help="Rohwerte je Beispiel dorthin schreiben")
    args = ap.parse_args()

    cfg = C.load_config(args.config, args.set)
    ckpt = args.checkpoint or os.path.join(cfg["out"]["dir"], C.CHECKPOINT_NAME)
    if not os.path.exists(ckpt):
        raise SystemExit(f"kein Checkpoint unter {ckpt} — erst train_fdm.py laufen lassen")
    print(f"Abnahme Stufe 1 — {ckpt}")
    meta_path = os.path.join(os.path.dirname(ckpt), C.META_NAME)
    if os.path.exists(meta_path):
        with open(meta_path) as f:
            m = json.load(f)
        print(f"  trainiert bis Epoche {m['epoch']}, Datensatz {m['dataset']}, "
              f"git {m.get('git', '?')}")

    res = evaluate(cfg, ckpt, args.n)
    ok = report(res)
    if args.json:
        with open(args.json, "w") as f:
            json.dump(res, f, indent=1)
        print(f"Rohwerte → {args.json}")
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
