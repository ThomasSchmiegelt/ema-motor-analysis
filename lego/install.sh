#!/usr/bin/env bash
# Werkzeugkette fuer das LEGO-Roboterhand-Projekt einrichten.
#
# Alles landet unterhalb von lego/ bzw. ~/.local — kein sudo, keine systemweiten
# Aenderungen. Das Skript ist idempotent: bereits erledigte Schritte werden
# uebersprungen, ein Abbruch kann also einfach wiederholt werden.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
export PATH="$HOME/.local/bin:$PATH"

log() { printf '\n=== %s\n' "$*"; }

log "uv"
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
uv --version

log "Virtuelle Umgebung + Pakete"
[[ -d .venv ]] || uv venv --python 3.12 .venv
# shellcheck disable=SC1091
source .venv/bin/activate
# bricknet bringt die Teile-, Konnektor- und Aliastabellen selbst mit.
uv pip install -q bricknet torch transformers accelerate peft datasets
python -c "import bricknet, torch; print('bricknet ok | torch', torch.__version__, '| CUDA', torch.cuda.is_available())"

log "BrickNet-Kollisionsnetze (369 MB gepackt / 1.6 GB entpackt)"
export BRICKNET_DATA="$ROOT/data/bricknet"
mkdir -p "$BRICKNET_DATA"
if [[ ! -d "$BRICKNET_DATA/inset" ]]; then
  python -m bricknet fetch-meshes
fi
echo "  $(ls "$BRICKNET_DATA/inset" | wc -l) Kollisionsnetze"

log "LDraw-Teilebibliothek (145 MB)"
mkdir -p data/downloads
if [[ ! -d data/ldraw ]]; then
  [[ -f data/downloads/ldraw_complete.zip ]] || \
    curl -L --retry 3 -o data/downloads/ldraw_complete.zip \
      https://library.ldraw.org/library/updates/complete.zip
  unzip -q -o data/downloads/ldraw_complete.zip -d data
fi
echo "  $(ls data/ldraw/parts/*.dat 2>/dev/null | wc -l) Teiledateien"

log "ORCA-Referenzkinematik"
for f in v1/models/urdf/orcahand_right.urdf v1/models/mjcf/orcahand_right.mjcf; do
  [[ -f "reference/orca/$(basename "$f")" ]] || \
    curl -sL -o "reference/orca/$(basename "$f")" \
      "https://raw.githubusercontent.com/orcahand/orcahand_description/main/$f"
done
python reference/orca_spec.py

cat <<'EOF'

Fertig. Umgebung aktivieren:

    source .venv/bin/activate
    export BRICKNET_DATA="$PWD/data/bricknet"
    export LDRAW_LIBRARY_PATH="$PWD/data/ldraw"

Studio 2.0 (Betrachter/Bauanleitung) separat einrichten:

    ./studio/install_studio.sh
EOF
