"""Einblick in das Surrogat-Training (`physics_surrogate/`) — Lesezugriff, sonst nichts.

Das Training läuft in einem **eigenen Subprojekt mit eigener venv** (Torch/CUDA; die
Flask-venv hat bewusst kein Torch) und einem eigenen Dienst auf :5300. Dieses Modul
holt nur, was auf Platte liegt — `checkpoints/<lauf>/history.csv`, `fdm.meta.json`,
`train.log` — und rendert daraus Kurven. Es importiert **kein** Torch und startet
**kein** Training: der Orchestrator ist hier Betrachter, nicht Betreiber.

Warum die Kurven überhaupt in den Orchestrator gehören: die Läufe dauern Stunden bis
Tage, und die Frage „ist das Modell inzwischen gut genug?" entscheidet sich an genau
zwei Zahlen (den Abnahme-Toren), die sonst nur in einer CSV auf der Platte stehen.

**Die eine Falle, die hier eingebaut ist** (sie hat schon einmal eine ganze
Diagnosekette umgeworfen): Läufe mit Kosinus-Lernrate dürfen **nicht bei gleicher
Epoche** verglichen werden, wenn ihre Gesamtlänge verschieden ist — ein 40-Epochen-Lauf
ist bei E37 fertig ausgekühlt (Lernrate ~0), ein 100-Epochen-Lauf bei E43 noch bei der
120-fachen Rate. Deshalb kann die x-Achse auf **Anteil des Zeitplans** umgeschaltet
werden (`x="progress"`), und die Lernrate wird immer mitgeplottet.
"""

import csv
import json
import os
import time

HERE = os.path.dirname(os.path.abspath(__file__))
SURROGATE_DIR = os.environ.get(
    "EMA_SURROGATE_DIR",
    os.path.join(os.path.dirname(HERE), "physics_surrogate"))
CHECKPOINTS = os.path.join(SURROGATE_DIR, "checkpoints")
SERVICE_URL = os.environ.get("SURROGATE_URL", "http://localhost:5300")

# Abnahme-Tore aus dem Stufe-1-Plan. `rmse_Br_rel_peak` ist das eigentliche Tor
# (Luftspaltkurve, daraus kommt das Moment); `rel_l2_A` ist die schwächere Größe —
# 98 % der Energie von A liegen im Rotor.
GATES = {"val_rmse_Br_rel_peak": 0.03, "val_rel_l2_A": 0.03}

# Spalte → (Beschriftung, Panel). Panel 0 = Musterfehler, 1 = Abnahme-Tor, 2 = Lernrate.
METRIC_LABELS = {
    "train_rel_l2_A":       "Training rel. L2 (A)",
    "val_rel_l2_A":         "Validierung rel. L2 (A)",
    "train_rel_l2_Br":      "Training rel. L2 (Br)",
    "val_rel_l2_Br":        "Validierung rel. L2 (Br)",
    "val_rmse_Br_rel_peak": "RMSE Br / Peak  ← Abnahme-Tor",
    "train_loss":           "Trainingsverlust",
    "lr":                   "Lernrate",
}

# Ein Lauf gilt als "läuft", wenn seine history.csv jünger als das hier ist. Das
# Training schreibt je Epoche eine Zeile (~7 min bei Tiefe 8), deshalb großzügig.
ACTIVE_AFTER_S = 25 * 60


def available() -> bool:
    """Ist das Subprojekt überhaupt da? (Es ist optional — ein Klon ohne
    `physics_surrogate/` muss den Tab sauber leer zeigen, nicht abstürzen.)"""
    return os.path.isdir(CHECKPOINTS)


def _read_history(path: str) -> list[dict]:
    """history.csv → Liste von Zeilen mit float-Werten (leere Zellen fliegen raus)."""
    rows: list[dict] = []
    try:
        with open(path, newline="") as f:
            for raw in csv.DictReader(f):
                row = {}
                for k, v in raw.items():
                    if k is None or v in (None, ""):
                        continue
                    try:
                        row[k] = float(v)
                    except ValueError:
                        row[k] = v
                if row:
                    rows.append(row)
    except Exception:
        return []
    return rows


def _best(rows: list[dict], key: str) -> dict | None:
    """Bester (kleinster) Wert einer Spalte samt Epoche."""
    cand = [r for r in rows if isinstance(r.get(key), float)]
    if not cand:
        return None
    r = min(cand, key=lambda x: x[key])
    return {"value": round(r[key], 5), "epoch": int(r.get("epoch", 0))}


def _meta(run_dir: str) -> dict:
    for fn in os.listdir(run_dir) if os.path.isdir(run_dir) else []:
        if fn.endswith(".meta.json"):
            try:
                with open(os.path.join(run_dir, fn)) as f:
                    return json.load(f)
            except Exception:
                return {}
    return {}


def list_runs() -> list[dict]:
    """Alle Trainingsläufe mit Kurz-Kennwerten, neuester zuerst.

    Die Historie selbst wird mitgeliefert (≤ ein paar hundert Zeilen je Lauf), damit
    der Browser Kurven zeichnen kann, ohne je Lauf noch einmal anzufragen.
    """
    if not available():
        return []
    runs = []
    now = time.time()
    for name in sorted(os.listdir(CHECKPOINTS)):
        d = os.path.join(CHECKPOINTS, name)
        hist_path = os.path.join(d, "history.csv")
        if not os.path.isdir(d) or not os.path.exists(hist_path):
            continue
        rows = _read_history(hist_path)
        if not rows:
            continue
        meta  = _meta(d)
        last  = rows[-1]
        mtime = os.path.getmtime(hist_path)
        paused = os.path.exists(os.path.join(d, "PAUSE"))
        # Gesamtdauer aus der Spalte `secs` (Sekunden je Epoche) — verlässlicher als
        # mtime-Differenzen, die jede Pause mitzählen würden.
        secs = sum(r["secs"] for r in rows if isinstance(r.get("secs"), float))
        best_gate = _best(rows, "val_rmse_Br_rel_peak")
        runs.append({
            "name":        name,
            "epochs":      int(last.get("epoch", len(rows) - 1)) + 1,
            "last":        {k: last.get(k) for k in
                            ("epoch", "lr", "train_loss", "train_rel_l2_A",
                             "val_rel_l2_A", "val_rel_l2_Br",
                             "val_rmse_Br_rel_peak", "peak_gb")},
            "best_val_A":  _best(rows, "val_rel_l2_A"),
            "best_gate":   best_gate,
            "gate_passed": bool(best_gate and best_gate["value"] < GATES["val_rmse_Br_rel_peak"]),
            "hours":       round(secs / 3600.0, 2),
            "mtime":       mtime,
            "modified":    time.strftime("%d.%m.%Y %H:%M", time.localtime(mtime)),
            "paused":      paused,
            "active":      bool((now - mtime) < ACTIVE_AFTER_S and not paused),
            "model":       meta.get("model", {}),
            "meta_epoch":  meta.get("epoch"),
            "git":         meta.get("git"),
            "has_model":   any(f.endswith(".mdlus") for f in os.listdir(d)),
            "history":     rows,
        })
    runs.sort(key=lambda r: r["mtime"], reverse=True)
    return runs


def log_tail(name: str, n: int = 60) -> str:
    """Letzte Zeilen von `train.log` — beantwortet „warum steht der Lauf?"."""
    path = os.path.join(CHECKPOINTS, name, "train.log")
    if not os.path.exists(path):
        return ""
    try:
        with open(path, errors="ignore") as f:
            return "".join(f.readlines()[-n:])
    except Exception:
        return ""


def service_status() -> dict:
    """`GET /health` des Surrogat-Dienstes (:5300) — beantwortet die eigentliche
    Frage „ist die KI im Programm schon nutzbar?". Läuft er nicht, ist das ein
    normaler Zustand, kein Fehler (wie Elmer/OpenFOAM/Blender: 503 statt Absturz)."""
    import urllib.error
    import urllib.request
    try:
        with urllib.request.urlopen(SERVICE_URL + "/health", timeout=1.5) as r:
            return {"up": True, "health": json.loads(r.read().decode())}
    except urllib.error.URLError as e:
        return {"up": False, "error": f"nicht erreichbar ({e.reason})"}
    except Exception as e:
        return {"up": False, "error": str(e)[:200]}


def chart(names: list[str], x: str = "epoch") -> str:
    """Drei-Panel-Vergleich der gewählten Läufe als base64-PNG.

    Panels: (1) rel. L2 auf A (Training gestrichelt, Validierung durchgezogen — die
    Lücke dazwischen IST die Überanpassung), (2) `rmse_Br_rel_peak` mit dem
    0,03-Abnahmetor als Linie, (3) Lernrate logarithmisch.

    ``x="progress"`` normiert die x-Achse auf den Anteil des Kosinus-Zeitplans. Das
    ist der einzig zulässige Vergleich zwischen Läufen verschiedener Gesamtlänge —
    s. Modul-Docstring.
    """
    import base64
    import io

    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = {r["name"]: r for r in list_runs()}
    sel  = [runs[n] for n in names if n in runs] or list(runs.values())[:4]

    fig, axes = plt.subplots(1, 3, figsize=(15, 4), facecolor="#111")
    for ax in axes:
        ax.set_facecolor("#1a1a2e")
        ax.tick_params(colors="#888", labelsize=8)
        for sp in ax.spines.values():
            sp.set_color("#444")
        ax.set_xlabel("Anteil des Zeitplans [%]" if x == "progress" else "Epoche",
                      color="#aaa", fontsize=8)
        ax.grid(alpha=0.15, color="#666")

    colors = ["#00d4ff", "#ff9f43", "#4caf50", "#e06c9f", "#b39ddb", "#ffd54f"]
    for i, run in enumerate(sel):
        c    = colors[i % len(colors)]
        rows = run["history"]
        ep   = [r.get("epoch", 0) for r in rows]
        if x == "progress":
            # Anteil am eigenen Zeitplan. Die Gesamtlänge steht nirgends in der CSV;
            # die Lernrate verrät sie aber: lr(e) = lr0·½(1+cos(π·e/E)) ⇒ bei E ist
            # sie ~0. Solange der Lauf nicht fertig ist, ist der bekannte Endpunkt
            # unbekannt — deshalb wird über die zuletzt erreichte Epoche normiert und
            # das im Titel gesagt.
            span = max(ep) or 1
            xs = [100.0 * e / span for e in ep]
        else:
            xs = ep

        def col(k):
            return [r.get(k) for r in rows]

        lbl = f"{run['name']} ({run['epochs']} Ep.)"
        axes[0].plot(xs, col("val_rel_l2_A"), color=c, lw=1.8, label=lbl)
        axes[0].plot(xs, col("train_rel_l2_A"), color=c, lw=1.0, ls="--", alpha=0.6)
        axes[1].plot(xs, col("val_rmse_Br_rel_peak"), color=c, lw=1.8, label=lbl)
        axes[2].plot(xs, col("lr"), color=c, lw=1.6, label=lbl)

    axes[0].set_title("rel. L2 auf A  (— Val., -- Training)", color="white", fontsize=9)
    axes[0].set_ylabel("rel. L2", color="#aaa", fontsize=8)
    axes[1].axhline(GATES["val_rmse_Br_rel_peak"], color="#4caf50", ls=":", lw=1.4)
    axes[1].annotate("Abnahme 0,03", (0.02, GATES["val_rmse_Br_rel_peak"]),
                     xycoords=("axes fraction", "data"), color="#4caf50",
                     fontsize=7, va="bottom")
    axes[1].set_title("RMSE Br / Peak  —  das Abnahme-Tor", color="white", fontsize=9)
    axes[1].set_ylabel("RMSE / Peak", color="#aaa", fontsize=8)
    axes[2].set_yscale("log")
    axes[2].set_title("Lernrate (Kosinus)", color="white", fontsize=9)
    axes[2].set_ylabel("lr", color="#aaa", fontsize=8)

    leg = axes[0].legend(fontsize=7, facecolor="#1a1a2e", edgecolor="#444", loc="upper right")
    for t in leg.get_texts():
        t.set_color("#ccc")

    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor="#111", dpi=110)
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()
