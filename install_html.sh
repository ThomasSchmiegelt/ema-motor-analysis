#!/bin/bash
# install_html.sh -- nur die Browser-Oberflaeche (cae_orchestrator, :5000), schlank.
#
# Braucht nur Python >= 3.10 mit venv. KEIN apt, KEIN sudo, KEIN FreeCAD/Elmer,
# keine KI. Es laufen: Feld (FDM), Thermik, Fahrzyklus, Canvas-Designer, Analysen,
# Gmsh-Netze. Es fehlen: FreeCAD-Stufen, CalculiX-Struktur-FEM, Elmer-Feld,
# PDF-Bericht, alle KI-Reiter. Dafuer gibt es install_ohne_ki.sh.
#
# Aufruf:  ./install_html.sh [--start]

set -eu
cd "$(dirname "$0")/cae_orchestrator"

python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' \
    || { echo "FEHLER: Python >= 3.10 noetig"; exit 1; }
python3 -c 'import venv, ensurepip' 2>/dev/null \
    || { echo "FEHLER: python3-venv fehlt  (sudo apt install python3-venv)"; exit 1; }

[ -d venv ] || python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip -q
# ddgs/trafilatura nur fuer die Agenten-Recherche -> weglassen
grep -v -E '^(ddgs|trafilatura)\b' requirements.txt | pip install -r /dev/stdin -q
mkdir -p workspace "$HOME/cae_projekte"

echo ""
echo "Fertig. Starten:  cd cae_orchestrator && python server.py   ->  http://localhost:5000"
echo "(./start.sh bricht ohne FreeCAD ab, deshalb hier direkt server.py)"

if [ "${1:-}" = "--start" ]; then
    exec python server.py
fi
