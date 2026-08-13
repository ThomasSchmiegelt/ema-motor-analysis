#!/bin/bash
# start.sh — Startet den Surrogat-Inferenzdienst auf :5300.
#
# Muster wie pikogk/start.sh (verwaiste Instanz auf dem Port beenden, dann starten),
# aber OHNE Browser-Aufruf: das ist ein reiner HTTP-Dienst, die Bedienung läuft über
# die Orchestrator-UI auf :5000.

set -euo pipefail
cd "$(dirname "$0")"

SCRIPT_DIR="$(pwd)"
PORT=5300
ORCH_DIR="$(cd .. && pwd)/cae_orchestrator"

# matplotlib headless (wie im Orchestrator) — der Dienst rendert Vorschau-PNGs.
export MPLBACKEND="${MPLBACKEND:-Agg}"

# Der geteilte Encoder importiert ema_analysis/ema_em3d/ema_topology aus dem
# Orchestrator (kein Nachbau der Rasterisierung — s. install.sh).
export PYTHONPATH="$ORCH_DIR${PYTHONPATH:+:$PYTHONPATH}"

if [ ! -x ".venv/bin/python" ]; then
    echo "FEHLER: .venv fehlt — bitte zuerst ./install.sh ausführen." >&2
    exit 1
fi

if [ ! -f "$ORCH_DIR/ema_analysis.py" ]; then
    echo "FEHLER: cae_orchestrator nicht gefunden ($ORCH_DIR)." >&2
    exit 1
fi

# ── Verwaiste eigene Instanz auf dem Port beenden ─────────────────────────────
# Bewusst NICHT `pkill -f python`: das Muster würde fremde Prozesse treffen (die
# pikogk-Erfahrung — ein zu weites Muster erwischte die eigene Shell). Stattdessen
# gezielt über den Port und nur, wenn der Prozess unsere venv-Python ist.
#
# Identifiziert wird über Arbeitsverzeichnis + Kommandozeile, NICHT über /proc/<pid>/exe:
# `.venv/bin/python` ist ein Symlink auf /usr/bin/python3.12, `readlink -f` liefert also
# den Systempfad und ein Präfix-Test auf die venv schlägt immer fehl (getestet — der
# eigene Dienst wurde dadurch als "fremder Prozess" gemeldet).
if command -v ss >/dev/null 2>&1; then
    for pid in $(ss -ltnpH "sport = :$PORT" 2>/dev/null \
                 | grep -oP 'pid=\K[0-9]+' | sort -u); do
        cwd="$(readlink -f "/proc/$pid/cwd" 2>/dev/null || true)"
        cmd="$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null || true)"
        if [ "$cwd" = "$SCRIPT_DIR" ] && [ "${cmd#*service/app.py}" != "$cmd" ]; then
            echo "[..] beende verwaiste Instanz auf :$PORT (PID $pid)"
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
        else
            echo "FEHLER: Port $PORT ist von einem fremden Prozess belegt (PID $pid: ${cmd:-?})." >&2
            exit 1
        fi
    done
fi

echo "=== PhysicsNeMo-Surrogat ==="
.venv/bin/python -c "
import torch
print('[OK] torch %s, CUDA %s' % (torch.__version__,
      torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'nicht verfügbar'))
"
echo ""
echo "Starte Dienst auf http://localhost:$PORT ..."
echo "Drücke Ctrl+C zum Beenden."
echo ""

exec .venv/bin/python service/app.py
