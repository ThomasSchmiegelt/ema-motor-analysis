#!/bin/bash
# install.sh — Einmalige Einrichtung des Surrogat-Dienstes (physics_surrogate).
# Prüft Voraussetzungen, legt die venv an, installiert PhysicsNeMo/Torch und macht
# einen Rauchtest (Import + CUDA-Verfügbarkeit).

set -e
cd "$(dirname "$0")"

GREEN="\033[0;32m"
YELLOW="\033[1;33m"
RED="\033[0;31m"
BLUE="\033[0;34m"
NC="\033[0m"

ok()   { echo -e "  ${GREEN}[OK]${NC}    $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}  $*"; }
fail() { echo -e "  ${RED}[FEHLER]${NC} $*"; }
info() { echo -e "  ${BLUE}[INFO]${NC}  $*"; }

ERRORS=0
WARNINGS=0

ORCH_DIR="$(cd .. && pwd)/cae_orchestrator"
NEEDED_GB=8

echo ""
echo "========================================"
echo "  PhysicsNeMo-Surrogat — Installation"
echo "========================================"
echo ""

# ── Python ────────────────────────────────────────────────────────────────────
# nvidia-physicsnemo 2.1.1 verlangt >=3.11,<3.14.
echo "Python:"
PY=""
for cand in python3.12 python3.13 python3.11 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
        v=$("$cand" -c 'import sys; print("%d.%d" % sys.version_info[:2])')
        case "$v" in
            3.11|3.12|3.13) PY="$cand"; ok "$cand ($v)"; break ;;
        esac
    fi
done
if [ -z "$PY" ]; then
    fail "Kein Python 3.11–3.13 gefunden (nvidia-physicsnemo verlangt >=3.11,<3.14)"
    ERRORS=$((ERRORS+1))
fi

# ── GPU (optional — Inferenz läuft auf CPU, Training praktisch nicht) ─────────
echo ""
echo "GPU:"
if command -v nvidia-smi >/dev/null 2>&1; then
    gpu=$(nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv,noheader | head -1)
    ok "$gpu"
else
    warn "nvidia-smi nicht gefunden — Training ohne GPU ist nicht praktikabel"
    WARNINGS=$((WARNINGS+1))
fi

# ── Geteilter Encoder: der Orchestrator muss importierbar sein ────────────────
# `ema_analysis`/`ema_em3d`/`ema_topology` importieren auf Modulebene nur math/numpy
# (gmsh/vtk werden lazy geladen), also sind sie ohne FreeCAD/Elmer/Gmsh nutzbar. Der
# Encoder verwendet daher die ECHTE Rasterisierung statt eines Nachbaus.
echo ""
echo "Geteilter Encoder:"
if [ -f "$ORCH_DIR/ema_analysis.py" ]; then
    ok "cae_orchestrator gefunden: $ORCH_DIR"
else
    fail "cae_orchestrator/ema_analysis.py nicht gefunden (erwartet: $ORCH_DIR)"
    ERRORS=$((ERRORS+1))
fi

# ── Platte ────────────────────────────────────────────────────────────────────
echo ""
echo "Plattenplatz:"
free_gb=$(df -BG --output=avail . | tail -1 | tr -dc '0-9')
if [ "${free_gb:-0}" -ge "$NEEDED_GB" ]; then
    ok "${free_gb} GB frei (Torch+PhysicsNeMo brauchen ~5–6 GB)"
else
    fail "nur ${free_gb} GB frei — mindestens ${NEEDED_GB} GB nötig"
    ERRORS=$((ERRORS+1))
fi

if [ "$ERRORS" -gt 0 ]; then
    echo ""
    fail "$ERRORS Fehler — Installation abgebrochen."
    exit 1
fi

# ── venv + Abhängigkeiten ─────────────────────────────────────────────────────
echo ""
echo "Virtuelle Umgebung:"
if [ ! -d ".venv" ]; then
    info "erstelle .venv ($PY)"
    "$PY" -m venv .venv
else
    info ".venv existiert bereits"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
pip install --upgrade pip -q
info "installiere Abhängigkeiten (mehrere GB, dauert einige Minuten)..."
pip install -r requirements.txt

# ── Rauchtest ─────────────────────────────────────────────────────────────────
echo ""
echo "Rauchtest:"
python - <<'PY'
import sys
import physicsnemo, torch
print(f"  physicsnemo {physicsnemo.__version__}, torch {torch.__version__}")
cuda = torch.cuda.is_available()
print(f"  torch.cuda.is_available() = {cuda}")
if cuda:
    print(f"  Gerät: {torch.cuda.get_device_name(0)} "
          f"({torch.cuda.get_device_properties(0).total_memory / 1e9:.1f} GB)")
else:
    print("  WARNUNG: keine CUDA-GPU sichtbar — Training nicht praktikabel")
sys.exit(0)
PY

echo ""
if [ "$WARNINGS" -gt 0 ]; then
    warn "$WARNINGS Warnung(en) — s. oben."
fi
ok "Installation abgeschlossen. Start: ./start.sh (Dienst auf :5300)"
echo ""
