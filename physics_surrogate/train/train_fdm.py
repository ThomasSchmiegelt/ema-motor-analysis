"""Training Stufe 1 — 2D-UNet lernt den FDM-Operator (Material+Quelle → A).

    physics_surrogate/.venv/bin/python train/train_fdm.py                # Vorgabe
    ... train/train_fdm.py --set train.epochs=3 --set data.limit=200     # Pilotlauf
    ... train/train_fdm.py --resume                                      # fortsetzen

**Anhalten und weitermachen.** ``touch <out.dir>/PAUSE`` (oder ein ``SIGTERM``/``Strg-C``)
hält innerhalb weniger Sekunden an, schreibt `last.pt` und beendet sich sauber;
``--resume`` nimmt den Faden mitten in der Epoche wieder auf — die Lernrate läuft über
den gespeicherten Scheduler-Zustand nahtlos weiter, s. `Stopper`.

Vorhergesagt wird das **Muster** ``A/RMS(A)``, nicht die Amplitude: `run_em_analysis`
skaliert jede Quelle ohnehin auf ihren analytischen Luftspalt-Spitzenwert und verwirft
dabei die Amplitude des Lösers. Der Versuch, die Amplitude mitzulernen, ist am 31.07.2026
gemessen gescheitert (Streuung 1514× über den Datensatz) — Begründung im Docstring von
`data/encode2d.py`.

**Verlust = relatives L2 auf A + `w_br` · relatives L2 auf B_r(θ).** Der zweite Term ist
der wichtige: `A` ist global glatt, ein reiner L2-Verlust darauf sieht gut aus, während
die Luftspaltableitung — aus der das Moment kommt — prozentual weit daneben liegen kann.
`train/airgap_torch.py` spiegelt dafür `_sample_airgap` bitgenau (2e-14 gegen die
Numpy-Fassung, `tests/test_airgap_torch.py`), sodass Verlust und Abnahme derselbe
Operator sind.

Aufgeteilt wird **nach Geometrie**, nicht nach Sample: Magnet- und Statorquelle einer
Geometrie teilen sich das Material, und läge eines im Training und das andere in der
Validierung, wäre die Validierung geschönt.

Der beste Checkpoint wird nach `val/rel_l2_A` gewählt und mit `physicsnemo.Module.save`
geschrieben — der legt die Konstruktorargumente mit ab, sodass der Dienst das Netz später
ohne Architekturwissen laden kann. Daneben liegt `fdm.meta.json` mit Gitter, Kanälen,
A_SCALE und Basismaschine für die Bereichsprüfung.
"""

import argparse
import csv
import math
import os
import signal
import time

import torch

import augment as AUG
import common as C

PAUSE_FILE = "PAUSE"
STEP_CHECK = 20        # so oft wird auf Pause geprüft (≈ alle 3 s)


class Stopper:
    """Anhalten ohne Verlust — auf ``SIGINT``/``SIGTERM`` oder eine Flagdatei.

    Warum nicht einfach ``kill``: ein hart abgeschossener Lauf verliert alles seit der
    letzten Epoche (bei diesem Netz ~10 min). Hier wird stattdessen ein Wunsch gemerkt,
    der laufende Schritt zu Ende gerechnet und `last.pt` geschrieben — `--resume` setzt
    danach exakt auf dem Lernraten-Schritt auf, an dem angehalten wurde (`LambdaLR`
    führt den Schrittzähler in seinem Zustand mit).

    Die Flagdatei ist der Weg für den Nutzer: ``touch <out_dir>/PAUSE`` braucht keine
    PID und funktioniert auch, wenn der Lauf unter `nohup` in einer anderen Sitzung
    hängt. Sie wird beim Anhalten wieder entfernt, damit `--resume` nicht sofort erneut
    stehen bleibt.
    """

    def __init__(self, flag_path: str):
        self.flag = flag_path
        self.reason: str | None = None
        if os.path.exists(self.flag):          # Rest eines früheren Halts
            os.remove(self.flag)
        for sig in (signal.SIGINT, signal.SIGTERM):
            signal.signal(sig, self._on_signal)

    def _on_signal(self, signum, _frame) -> None:
        if self.reason is None:
            self.reason = signal.Signals(signum).name
            print(f"\n[{self.reason}] Pause vorgemerkt — es wird nach dem laufenden "
                  f"Schritt gespeichert.", flush=True)

    def requested(self) -> bool:
        if self.reason is None and os.path.exists(self.flag):
            self.reason = f"Flagdatei {os.path.basename(self.flag)}"
            print(f"\n[{self.reason}] Pause vorgemerkt — es wird nach dem laufenden "
                  f"Schritt gespeichert.", flush=True)
        return self.reason is not None

    def clear_flag(self) -> None:
        if os.path.exists(self.flag):
            os.remove(self.flag)


def _lr_lambda(cfg: dict, steps_per_epoch: int):
    warm = int(cfg["train"]["warmup_epochs"]) * steps_per_epoch
    total = int(cfg["train"]["epochs"]) * steps_per_epoch

    def fn(step: int) -> float:
        if step < warm:
            return (step + 1) / max(1, warm)
        t = (step - warm) / max(1, total - warm)
        return 0.5 * (1.0 + math.cos(math.pi * min(t, 1.0)))
    return fn


def _batch_loss(model, airgap, x, y, r, w_br, dtype, device):
    with torch.autocast(device, dtype=dtype, enabled=dtype != torch.float32):
        pred = model(x)
    pred = pred.float()
    l_a = C.rel_l2(pred, y)
    # Luftspaltkurve in float32: die Ableitung entlang θ auf einem interpolierten Kreis
    # verliert in bfloat16 zu viele Stellen, um noch ein sinnvolles Gradientensignal
    # zu geben.
    br_p = airgap(pred, r)
    br_t = airgap(y, r)
    l_br = C.rel_l2(br_p, br_t)
    return l_a + w_br * l_br, l_a.detach(), l_br.detach()


@torch.no_grad()
def validate(model, airgap, loader, dtype, device) -> dict:
    model.eval()
    tot = {"rel_l2_A": 0.0, "rel_l2_Br": 0.0, "rmse_Br_rel_peak": 0.0}
    n = 0
    for x, y, r in loader:
        x = x.to(device, non_blocking=True)
        y = y.to(device, non_blocking=True)
        r = r.to(device, non_blocking=True)
        with torch.autocast(device, dtype=dtype, enabled=dtype != torch.float32):
            pred = model(x)
        pred = pred.float()
        br_p, br_t = airgap(pred, r), airgap(y, r)
        b = x.shape[0]
        tot["rel_l2_A"] += C.rel_l2(pred, y).item() * b
        tot["rel_l2_Br"] += C.rel_l2(br_p, br_t).item() * b
        # Identisch zur Gate-Definition in `evaluate.py`: jede Kurve auf ihren EIGENEN
        # Spitzenwert beziehen — genau die Kalibrierung von `run_em_analysis:1053`.
        br_pn = br_p / br_p.abs().amax(dim=1, keepdim=True).clamp_min(1e-12)
        br_tn = br_t / br_t.abs().amax(dim=1, keepdim=True).clamp_min(1e-12)
        tot["rmse_Br_rel_peak"] += (br_pn - br_tn).pow(2).mean(dim=1).sqrt().sum().item()
        n += b
    model.train()
    return {k: v / max(1, n) for k, v in tot.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "conf", "fdm.yaml"))
    ap.add_argument("--set", action="append", default=[], metavar="KEY=WERT",
                    help="Konfigurationsschlüssel überschreiben, z. B. train.epochs=5")
    ap.add_argument("--resume", action="store_true",
                    help="letzten Zustand aus out.dir/last.pt fortsetzen")
    args = ap.parse_args()

    cfg = C.load_config(args.config, args.set)
    torch.manual_seed(int(cfg["train"]["seed"]))
    device = "cuda" if torch.cuda.is_available() else "cpu"
    dtype = C.amp_dtype(cfg) if device == "cuda" else torch.float32
    out_dir = cfg["out"]["dir"]
    os.makedirs(out_dir, exist_ok=True)

    meta, tr_recs, va_recs = C.make_splits(cfg)
    tr_loader = C.make_loader(cfg, meta, tr_recs, train=True)
    va_loader = C.make_loader(cfg, meta, va_recs, train=False)
    n_grid = int(meta["grid"])

    model = C.build_model(cfg).to(device)
    airgap = C.AirgapBr(n_grid).to(device)
    n_par = sum(p.numel() for p in model.parameters())

    opt = torch.optim.AdamW(model.parameters(), lr=float(cfg["train"]["lr"]),
                            weight_decay=float(cfg["train"]["weight_decay"]))
    steps_per_epoch = max(1, len(tr_loader))
    sched = torch.optim.lr_scheduler.LambdaLR(opt, _lr_lambda(cfg, steps_per_epoch))

    start_epoch, best = 0, float("inf")
    last_path = os.path.join(out_dir, "last.pt")
    if args.resume and os.path.exists(last_path):
        ck = torch.load(last_path, map_location=device, weights_only=False)
        model.load_state_dict(ck["model"])
        opt.load_state_dict(ck["opt"])
        sched.load_state_dict(ck["sched"])
        start_epoch, best = ck["epoch"] + 1, ck["best"]
        print(f"fortgesetzt bei Epoche {start_epoch} (bestes rel_l2_A {best:.4f})")

    print(f"Training Stufe 1 — {device}, {dtype}".replace("torch.", ""))
    print(f"  Datensatz {cfg['data']['root']}  N={n_grid}")
    print(f"  {len(tr_recs)} Geometrien Training / {len(va_recs)} Validierung "
          f"→ {len(tr_loader.dataset)} / {len(va_loader.dataset)} Beispiele")
    aug_txt = (f"{cfg['train'].get('augment_mode', 'd4_sign')}"
               if cfg["train"].get("augment") else "aus")
    print(f"  Netz: Tiefe {cfg['model']['model_depth']}, {n_par / 1e6:.1f} M Parameter, "
          f"Batch {cfg['train']['batch_size']}, w_br={cfg['loss']['w_br']}, "
          f"Augmentierung {aug_txt}\n")

    log_path = os.path.join(out_dir, "history.csv")
    new_log = not os.path.exists(log_path)
    log = open(log_path, "a", newline="")
    writer = csv.writer(log)
    if new_log:
        writer.writerow(["epoch", "lr", "train_loss", "train_rel_l2_A", "train_rel_l2_Br",
                         "val_rel_l2_A", "val_rel_l2_Br", "val_rmse_Br_rel_peak",
                         "secs", "peak_gb"])

    def save_last(ep: int, best_val: float) -> None:
        torch.save({"model": model.state_dict(), "opt": opt.state_dict(),
                    "sched": sched.state_dict(), "epoch": ep, "best": best_val},
                   last_path)

    w_br = float(cfg["loss"]["w_br"])
    clip = float(cfg["train"]["grad_clip"])
    do_aug = bool(cfg["train"].get("augment", False))
    aug_mode = str(cfg["train"].get("augment_mode", "d4_sign"))
    if do_aug and aug_mode not in AUG.MODES:
        raise SystemExit(f"train.augment_mode={aug_mode!r}: erlaubt sind {AUG.MODES}")
    aug_gen = torch.Generator().manual_seed(int(cfg["train"]["seed"]) + 1)
    stopper = Stopper(os.path.join(out_dir, PAUSE_FILE))
    print(f"  Pause jederzeit mit:  touch {os.path.join(out_dir, PAUSE_FILE)}\n")

    for epoch in range(start_epoch, int(cfg["train"]["epochs"])):
        t0 = time.time()
        if device == "cuda":
            torch.cuda.reset_peak_memory_stats()
        run = {"loss": 0.0, "a": 0.0, "br": 0.0}
        seen = 0
        for step, (x, y, r) in enumerate(tr_loader):
            x = x.to(device, non_blocking=True)
            y = y.to(device, non_blocking=True)
            r = r.to(device, non_blocking=True)
            if do_aug:
                # Exakte Symmetrien des Operators, s. augment.py. Der Ringradius `r`
                # bleibt unberührt — genau dafür ist der 1-px-Rückschub da.
                x, y = AUG.augment(x, y, aug_gen, mode=aug_mode)
            loss, l_a, l_br = _batch_loss(model, airgap, x, y, r, w_br, dtype, device)
            opt.zero_grad(set_to_none=True)
            loss.backward()
            if clip > 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), clip)
            opt.step()
            sched.step()
            b = x.shape[0]
            run["loss"] += loss.item() * b
            run["a"] += l_a.item() * b
            run["br"] += l_br.item() * b
            seen += b
            if step % 100 == 0:
                print(f"  E{epoch:03d} {step:5d}/{steps_per_epoch}  "
                      f"loss={run['loss'] / max(1, seen):.4f}  "
                      f"A={run['a'] / max(1, seen):.4f}  Br={run['br'] / max(1, seen):.4f}",
                      flush=True)
            if step % STEP_CHECK == 0 and stopper.requested():
                # Ohne Validierung: eine Pause soll schnell sein. Die angebrochene
                # Epoche gilt als erledigt — `--resume` beginnt die nächste mit frisch
                # gemischten Daten, die Lernrate läuft über den Scheduler-Zustand
                # nahtlos weiter.
                save_last(epoch, best)
                log.close()
                stopper.clear_flag()
                print(f"\nangehalten in Epoche {epoch} nach {step}/{steps_per_epoch} "
                      f"Schritten ({stopper.reason}).")
                print(f"Zustand in {last_path}, bestes val rel_l2_A {best:.4f}")
                print(f"weiter mit:  .venv/bin/python train/train_fdm.py --resume")
                return

        val = validate(model, airgap, va_loader, dtype, device)
        secs = time.time() - t0
        peak_gb = torch.cuda.max_memory_allocated() / 1e9 if device == "cuda" else 0.0
        print(f"E{epoch:03d}  train loss={run['loss'] / max(1, seen):.4f}  "
              f"| val {C.format_metrics(val)}  | {secs:.0f} s, {peak_gb:.1f} GB", flush=True)
        writer.writerow([epoch, f"{sched.get_last_lr()[0]:.3e}",
                         run["loss"] / max(1, seen), run["a"] / max(1, seen),
                         run["br"] / max(1, seen), val["rel_l2_A"], val["rel_l2_Br"],
                         val["rmse_Br_rel_peak"], f"{secs:.1f}", f"{peak_gb:.2f}"])
        log.flush()

        save_last(epoch, min(best, val["rel_l2_A"]))
        if val["rel_l2_A"] < best:
            best = val["rel_l2_A"]
            model.save(os.path.join(out_dir, C.CHECKPOINT_NAME))
            C.write_meta(cfg, meta, val, epoch, os.path.join(out_dir, C.META_NAME))
            print(f"   ↳ neuer bester Checkpoint (rel_l2_A {best:.4f})", flush=True)

        if stopper.requested():
            log.close()
            stopper.clear_flag()
            print(f"\nangehalten nach Epoche {epoch} ({stopper.reason}). "
                  f"weiter mit:  .venv/bin/python train/train_fdm.py --resume")
            return

    log.close()
    print(f"\nfertig — bestes val rel_l2_A {best:.4f}, Checkpoint in {out_dir}")
    print("Abnahme:  .venv/bin/python train/evaluate.py")


if __name__ == "__main__":
    main()
