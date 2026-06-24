#!/bin/bash
set -e
cd "$(dirname "$0")"

FREECAD_ROOT="$HOME/freecad_1.1_quellcode"
FREECAD_CMD="$FREECAD_ROOT/build/release/bin/FreeCADCmd"
CCX_CMD="$FREECAD_ROOT/.pixi/envs/default/bin/ccx"
OLLAMA_URL="http://localhost:11434"
PORT=5000

echo "=== E-Maschinen Analyse ==="
echo ""

# Check FreeCAD 1.1.1 (the /opt/freecad-1.1 binary is actually 1.2 with a
# visualisation bug — we use the source-built 1.1.1 via pixi instead)
if [ ! -x "$FREECAD_CMD" ]; then
    echo "FEHLER: FreeCAD 1.1.1 nicht gefunden: $FREECAD_CMD"
    echo "        (in $FREECAD_ROOT mit 'pixi run install-release' bauen)"
    exit 1
fi
echo "[OK] FreeCAD 1.1.1: $FREECAD_CMD"

if ! command -v pixi >/dev/null 2>&1; then
    echo "FEHLER: pixi nicht gefunden — wird zum Aufruf von FreeCAD benötigt"
    exit 1
fi

# Check CalculiX
if [ ! -x "$CCX_CMD" ]; then
    echo "FEHLER: CalculiX nicht gefunden: $CCX_CMD"
    exit 1
fi
echo "[OK] CalculiX:      $CCX_CMD"

# Check Ollama (optional — warn only)
if curl -s --max-time 3 "$OLLAMA_URL" > /dev/null 2>&1; then
    echo "[OK] Ollama:     $OLLAMA_URL"
else
    echo "[--] Ollama nicht erreichbar ($OLLAMA_URL) — pipeline läuft ohne LLM-Zusammenfassung"
fi

# Check Elmer (optional — nur für den 3D-Magnetfeld-Tab)
if command -v ElmerSolver >/dev/null 2>&1 && command -v ElmerGrid >/dev/null 2>&1; then
    echo "[OK] Elmer:      $(command -v ElmerSolver) (3D-Feld verfügbar)"
else
    echo "[--] Elmer nicht gefunden — 3D-Feld-Tab deaktiviert"
    echo "     Installation: sudo add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa && sudo apt install -y elmerfem-csc"
fi

echo ""

# Setup / update venv
if [ ! -d "venv" ]; then
    echo "Erstelle virtuelle Umgebung..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    echo "[OK] Abhängigkeiten installiert"
else
    source venv/bin/activate
    pip install -r requirements.txt -q 2>/dev/null || true
fi

echo ""
echo "Starte Server auf http://localhost:$PORT ..."
echo "Drücke Ctrl+C zum Beenden."
echo ""

# Auto-open browser after short delay (background)
( sleep 1.5 && xdg-open "http://localhost:$PORT" ) &

exec python server.py
