"""Gemeinsames für Training und Abnahme der Stufe 1 — Konfiguration, Split, Metriken.

Liegt bewusst getrennt von `train_fdm.py`: `evaluate.py` muss **genau denselben** Split
und **genau dieselben** Metrikdefinitionen benutzen wie das Training, sonst misst die
Abnahme etwas anderes als der Verlust optimiert hat.
"""

import json
import os
import sys

import numpy as np
import torch

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
for _p in (os.path.join(_ROOT, "data"), os.path.join(_ROOT, "models"), _HERE):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import dataset as D          # noqa: E402  (setzt den Orchestrator-Pfad)
import encode2d              # noqa: E402
import ema_analysis as ea    # noqa: E402
from airgap_torch import AirgapBr   # noqa: E402,F401  (Re-Export)
from unet2d import UNet2D           # noqa: E402,F401  (Re-Export)

CHECKPOINT_NAME = "fdm.mdlus"     # physicsnemo.Module.save besteht auf dieser Endung
META_NAME = "fdm.meta.json"


# ── Konfiguration ─────────────────────────────────────────────────────────────

def load_config(path: str, overrides: list[str] | None = None) -> dict:
    """YAML laden und `--set a.b=wert`-Überschreibungen anwenden.

    Kein Hydra: nirgends sonst im Monorepo, und für eine Datei mit 25 Schlüsseln wäre
    die zusätzliche Abhängigkeit (plus ihr Arbeitsverzeichnis-Umbau) mehr Aufwand als
    Nutzen.
    """
    import yaml
    with open(path) as f:
        cfg = yaml.safe_load(f)
    for ov in overrides or []:
        key, _, val = ov.partition("=")
        node = cfg
        parts = key.split(".")
        for p in parts[:-1]:
            node = node[p]
        if parts[-1] not in node:
            raise SystemExit(f"--set {key}: unbekannter Schlüssel")
        cur = node[parts[-1]]
        try:
            node[parts[-1]] = type(cur)(val) if not isinstance(cur, bool) else val == "true"
        except (TypeError, ValueError):
            node[parts[-1]] = val
    # Pfade NACH den Überschreibungen auflösen, relativ zur Konfigurationsdatei —
    # sonst hinge das Ergebnis am Arbeitsverzeichnis des Aufrufers.
    base = os.path.dirname(os.path.abspath(path))
    for section, key in (("data", "root"), ("out", "dir")):
        if not os.path.isabs(cfg[section][key]):
            cfg[section][key] = os.path.normpath(os.path.join(base, cfg[section][key]))
    return cfg


# ── Daten ─────────────────────────────────────────────────────────────────────

def make_splits(cfg: dict):
    """``(meta, train_recs, val_recs)`` — Aufteilung **nach Geometrie**, deterministisch."""
    root = cfg["data"]["root"]
    meta = D.read_meta(root)
    recs = D.read_manifest(root)
    limit = int(cfg["data"].get("limit") or 0)
    if limit:
        recs = recs[:limit]
    tr, va = D.split_by_geometry(recs, cfg["data"]["val_frac"], cfg["data"]["split_seed"])
    return meta, tr, va


def free_space(cfg: dict) -> bool:
    return bool(cfg["data"].get("free_space", False))


def make_loader(cfg: dict, meta: dict, recs: list[dict], *, train: bool):
    ds = D.torch_dataset(cfg["data"]["root"], recs, meta, free_space=free_space(cfg))
    nw = int(cfg["data"]["num_workers"])
    return torch.utils.data.DataLoader(
        ds, batch_size=int(cfg["train"]["batch_size"]), shuffle=train,
        num_workers=nw, pin_memory=True, drop_last=train,
        persistent_workers=nw > 0, prefetch_factor=4 if nw > 0 else None)


# ── Metriken ──────────────────────────────────────────────────────────────────

def rel_l2(pred: torch.Tensor, target: torch.Tensor) -> torch.Tensor:
    """Relative L2-Norm **je Sample**, dann Mittel über den Batch.

    Je Sample, nicht über den ganzen Batch: sonst dominieren Samples mit großer
    Amplitude die Norm, und genau die Amplitudenstreuung sollte die α-Normierung ja
    schon entfernt haben.
    """
    p = pred.flatten(1)
    t = target.flatten(1)
    return ((p - t).norm(dim=1) / t.norm(dim=1).clamp_min(1e-12)).mean()


def build_model(cfg: dict) -> UNet2D:
    return UNet2D(in_channels=len(encode2d.channel_names(free_space(cfg))),
                  out_channels=1, **cfg["model"])


def amp_dtype(cfg: dict):
    return {"bfloat16": torch.bfloat16, "float16": torch.float16,
            "float32": torch.float32}[cfg["train"]["amp_dtype"]]


def write_meta(cfg: dict, meta: dict, metrics: dict, epoch: int, path: str) -> None:
    """Begleitdatei zum Checkpoint — der Dienst prüft daran seine Gültigkeitsgrenze.

    Ohne sie müsste `service/predict.py` Gitter, Kanalreihenfolge, A_SCALE und die
    Basismaschine erneut hart kodieren — vier Stellen, an denen es still vom trainierten
    Modell abweichen könnte.
    """
    import subprocess
    try:
        rev = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=_ROOT,
                             capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):        # pragma: no cover
        rev = ""
    payload = {
        "stage": "fdm",
        "grid": meta["grid"],
        "channels": list(encode2d.channel_names(free_space(cfg))),
        "target": "pattern",          # A/RMS(A) — Amplitude kommt aus der Kalibrierung
        "a_scale": encode2d.A_SCALE,
        "base_geom": meta["base_geom"],
        "base_axial": meta["base_axial"],
        "shapes": meta["shapes"],
        "dataset": os.path.basename(cfg["data"]["root"]),
        "n_geometries": meta.get("n_geometries"),
        "model": dict(cfg["model"]),
        "epoch": epoch,
        "metrics": {k: float(v) for k, v in metrics.items()},
        "git": rev,
    }
    with open(path, "w") as f:
        json.dump(payload, f, indent=1)


def format_metrics(m: dict) -> str:
    return "  ".join(f"{k}={v:.4f}" for k, v in m.items())


def np_airgap(a_norm: np.ndarray, geom: dict, n: int):
    """Echte Numpy-Luftspaltkurve auf einem (normierten) A — für die Abnahme.

    Bewusst `_sample_airgap` selbst und nicht die Torch-Spiegelung: die Abnahme soll die
    Größe messen, die der Orchestrator später tatsächlich benutzt. Br/Bt sind linear in
    A, also bleiben *relative* Fehler von der Normierung unberührt.
    """
    sc = encode2d.scale_px_per_mm(geom, n)
    br, bt, _theta, _bx, _by = ea._sample_airgap(
        np.asarray(a_norm, np.float64), geom, sc, n / 2.0, n)
    return br, bt
