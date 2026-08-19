"""Inferenzdienst des Surrogats — Flask auf :5300.

Eigenständiger lokaler HTTP-Dienst neben `pikogk` (:5266) und Ollama (:11434); der
`cae_orchestrator` spricht ihn per `urllib.request` an (`ema_surrogate.py`). Kein
Auth/TLS — bewusst, wie überall in diesem Monorepo (lokaler PoC-Scope).

Stand AP1.0: nur `GET /health`. Die Vorhersage-Routen antworten mit **503**, solange
kein trainierter Checkpoint vorliegt (AP1.3) — genau wie `/em3d` ohne Elmer bzw. `/cfd`
ohne OpenFOAM im Orchestrator. Der Orchestrator muss diesen Zustand aushalten, ohne
kaputtzugehen; das ist Teil der Testmatrix (`test_surrogate.py`).
"""

import os

from flask import Flask, jsonify

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CHECKPOINTS = os.path.join(ROOT, "checkpoints")

# Modell-Registry: Stufe → Checkpoint-Datei. Existiert die Datei nicht, ist die Stufe
# nicht verfügbar und die Route antwortet 503 statt zu raten.
# Endung `.mdlus`: darauf besteht `physicsnemo.Module.save` — der Checkpoint enthält
# damit auch die Konstruktorargumente, sodass hier keine Architektur hart kodiert werden
# muss (`Module.from_checkpoint`).
STAGES = {
    # `fdm_v2`: der zweite Trainingsanlauf (Augmentierung + Tiefe 8), s. conf/fdm.yaml.
    # Muss mit `out.dir` dort übereinstimmen — sonst liefert der Dienst still ein
    # anderes Modell als das, was die Abnahme gemessen hat.
    "fdm":  os.path.join("fdm_v2", "fdm.mdlus"),  # Stufe 1 — 2D-FDM (AP1.3)
    "em3d": os.path.join("em3d", "em3d.mdlus"),  # Stufe 2/3 — 3D-Elmer (AP2.3/AP3.2)
}

app = Flask(__name__)


def _checkpoint(stage: str) -> str | None:
    """Pfad des Checkpoints, oder None wenn (noch) keiner da ist."""
    name = STAGES.get(stage)
    if not name:
        return None
    path = os.path.join(CHECKPOINTS, name)
    return path if os.path.exists(path) else None


def _device_info() -> dict:
    """Torch-/Gerätezustand. Import lokal, damit ein Import-Fehler als JSON sichtbar
    wird statt den Dienst am Start zu töten."""
    try:
        import torch
    except Exception as e:                                  # pragma: no cover
        return {"torch": None, "device": None, "error": str(e)[:200]}
    cuda = torch.cuda.is_available()
    return {
        "torch":  torch.__version__,
        "device": torch.cuda.get_device_name(0) if cuda else "cpu",
        "cuda":   cuda,
    }


def _version_info() -> dict:
    try:
        import physicsnemo
        pn = getattr(physicsnemo, "__version__", "?")
    except Exception as e:                                  # pragma: no cover
        pn = f"nicht importierbar: {str(e)[:80]}"
    return {"physicsnemo": pn}


@app.get("/health")
def health():
    """Zustand des Dienstes: welche Stufen bedienbar sind, auf welchem Gerät.

    Der Orchestrator nutzt das für seinen `SURROGATE_OK`-Schalter (Muster
    `elmer_runner.ELMER_OK`), die UI zeigt die Modellversion im Ehrlichkeits-Banner.
    """
    models = {}
    for stage in STAGES:
        cp = _checkpoint(stage)
        models[stage] = {
            "available": cp is not None,
            "checkpoint": os.path.basename(cp) if cp else None,
            "trained_at": (__import__("datetime").datetime.fromtimestamp(
                os.path.getmtime(cp)).isoformat(timespec="seconds") if cp else None),
        }
    return jsonify({
        "status": "ok",
        "service": "physics_surrogate",
        "models": models,
        **_device_info(),
        **_version_info(),
    })


@app.post("/predict/fdm")
def predict_fdm():
    """Stufe 1 — 2D-FDM-Feld. Implementierung folgt in AP1.4."""
    return jsonify({
        "error": "Stufe 1 (2D-FDM) ist noch nicht trainiert — kein Checkpoint "
                 f"({os.path.join('checkpoints', STAGES['fdm'])}). Siehe AP1.2/AP1.3.",
    }), 503


@app.post("/predict/em3d")
def predict_em3d():
    """Stufe 2/3 — 3D-Feld. Implementierung folgt in AP2.3."""
    return jsonify({
        "error": "Stufe 2 (3D-Elmer) ist noch nicht trainiert — kein Checkpoint "
                 f"({os.path.join('checkpoints', STAGES['em3d'])}). Siehe AP2.2/AP2.3.",
    }), 503


if __name__ == "__main__":
    os.makedirs(CHECKPOINTS, exist_ok=True)
    # threaded=False: die Inferenz läuft auf EINER GPU; parallele Requests würden sich
    # nur den VRAM zerlegen. Serielle Abarbeitung wie im pikogk-Worker.
    app.run(host="127.0.0.1", port=5300, threaded=False)
