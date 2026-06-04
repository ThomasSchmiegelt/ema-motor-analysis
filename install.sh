#!/bin/bash
# install.sh — Einmalige Einrichtung für E-Maschinen Analyse
# Prüft alle Voraussetzungen, legt die venv an und gibt eine Zusammenfassung aus.

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

echo ""
echo "========================================"
echo "  E-Maschinen Analyse — Installation"
echo "========================================"
echo ""

# ── Pfad-Konfiguration ────────────────────────────────────────────────────────
# Passe FREECAD_ROOT an, falls FreeCAD an einem anderen Ort liegt.
FREECAD_ROOT="${FREECAD_ROOT:-$HOME/freecad_1.1_quellcode}"
FREECAD_CMD="$FREECAD_ROOT/build/release/bin/FreeCADCmd"
CCX_CMD="$FREECAD_ROOT/.pixi/envs/default/bin/ccx"
OLLAMA_URL="${OLLAMA_URL:-http://localhost:11434}"
PROJECTS_ROOT="$HOME/cae_projekte"

echo -e "${BLUE}Konfiguration:${NC}"
info "FREECAD_ROOT : $FREECAD_ROOT"
info "OLLAMA_URL   : $OLLAMA_URL"
info "Projekte     : $PROJECTS_ROOT"
echo ""

# ── Python ───────────────────────────────────────────────────────────────────
echo -e "${BLUE}1. Python${NC}"
if command -v python3 >/dev/null 2>&1; then
    PY_VER=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
    PY_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
    PY_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")
    if [ "$PY_MAJOR" -ge 3 ] && [ "$PY_MINOR" -ge 10 ]; then
        ok "Python $PY_VER"
    else
        fail "Python $PY_VER — mindestens 3.10 erforderlich"
        ERRORS=$((ERRORS + 1))
    fi
else
    fail "Python 3 nicht gefunden"
    ERRORS=$((ERRORS + 1))
fi

# ── pixi ─────────────────────────────────────────────────────────────────────
echo -e "${BLUE}2. pixi${NC}"
if command -v pixi >/dev/null 2>&1; then
    ok "pixi $(pixi --version 2>/dev/null | head -1)"
else
    fail "pixi nicht gefunden"
    info "Installation: curl -fsSL https://pixi.sh/install.sh | bash"
    info "Danach Shell neu starten oder: source ~/.bashrc"
    ERRORS=$((ERRORS + 1))
fi

# ── FreeCAD 1.1.x ────────────────────────────────────────────────────────────
echo -e "${BLUE}3. FreeCAD 1.1.x${NC}"
if [ -x "$FREECAD_CMD" ]; then
    ok "FreeCAD: $FREECAD_CMD"
else
    fail "FreeCAD-Binary nicht gefunden: $FREECAD_CMD"
    info "FreeCAD aus Quellcode bauen:"
    info "  git clone https://github.com/FreeCAD/FreeCAD $FREECAD_ROOT"
    info "  cd $FREECAD_ROOT && git checkout 0.22"
    info "  pixi run install-release"
    info ""
    info "Abweichender Pfad? FREECAD_ROOT=/dein/pfad ./install.sh"
    info "Und anschließend FREECAD_ROOT in freecad_runner.py (Zeile 14)"
    info "und in start.sh (Zeile 5) anpassen."
    ERRORS=$((ERRORS + 1))
fi

# ── CalculiX ─────────────────────────────────────────────────────────────────
echo -e "${BLUE}4. CalculiX (ccx)${NC}"
if [ -x "$CCX_CMD" ]; then
    ok "CalculiX: $CCX_CMD"
elif command -v ccx >/dev/null 2>&1; then
    warn "ccx gefunden via PATH, aber nicht im pixi-Env"
    warn "FEM-Analysen laufen möglicherweise nicht korrekt"
    WARNINGS=$((WARNINGS + 1))
else
    fail "CalculiX nicht gefunden: $CCX_CMD"
    info "CalculiX ist im FreeCAD-Pixi-Environment enthalten."
    info "Wenn FreeCAD korrekt gebaut wurde, erscheint ccx automatisch."
    ERRORS=$((ERRORS + 1))
fi

# ── Ollama (optional — nur für PDF-Berichte) ──────────────────────────────────
echo -e "${BLUE}5. Ollama (optional, nur für PDF-Berichte)${NC}"
if curl -s --max-time 5 "$OLLAMA_URL" >/dev/null 2>&1; then
    ok "Ollama erreichbar: $OLLAMA_URL"
    if curl -s --max-time 5 "$OLLAMA_URL/api/tags" 2>/dev/null | grep -q "ministral-3"; then
        ok "Modell ministral-3:14b vorhanden"
    else
        warn "Modell ministral-3:14b fehlt (wird für PDF-Berichte benötigt)"
        info "Modell laden: ollama pull ministral-3:14b"
        WARNINGS=$((WARNINGS + 1))
    fi
else
    warn "Ollama nicht erreichbar ($OLLAMA_URL) — PDF-Berichte nicht verfügbar"
    info "Für PDF-Berichte: https://ollama.com installieren, dann:"
    info "  ollama serve && ollama pull ministral-3:14b"
    info "Die Analyse-Pipeline (FDM, Thermik, FEM) läuft vollständig ohne Ollama."
    WARNINGS=$((WARNINGS + 1))
fi

# ── pandoc + pdflatex (optional) ──────────────────────────────────────────────
echo -e "${BLUE}6. pandoc + pdflatex (optional, nur für PDF-Berichte)${NC}"
HAVE_PANDOC=0
HAVE_PDFLATEX=0
if command -v pandoc >/dev/null 2>&1; then
    ok "pandoc $(pandoc --version | head -1)"
    HAVE_PANDOC=1
else
    warn "pandoc nicht gefunden — PDF-Berichtsgenerierung nicht verfügbar"
    info "Installation: sudo apt install pandoc"
    WARNINGS=$((WARNINGS + 1))
fi
if command -v pdflatex >/dev/null 2>&1; then
    ok "pdflatex vorhanden"
    HAVE_PDFLATEX=1
else
    warn "pdflatex nicht gefunden — PDF-Berichtsgenerierung nicht verfügbar"
    info "Installation: sudo apt install texlive-latex-base texlive-fonts-recommended"
    WARNINGS=$((WARNINGS + 1))
fi

# ── Python-Umgebung (venv) ────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}7. Python-Umgebung${NC}"
if [ -d "venv" ]; then
    info "Vorhandene venv wird aktualisiert..."
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    ok "Abhängigkeiten aktualisiert"
else
    info "Neue virtuelle Umgebung wird erstellt..."
    python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip -q
    pip install -r requirements.txt -q
    ok "Virtuelle Umgebung erstellt und Abhängigkeiten installiert"
fi

# ── Verzeichnisse anlegen ────────────────────────────────────────────────────
echo ""
echo -e "${BLUE}8. Verzeichnisse${NC}"
mkdir -p workspace
ok "workspace/ angelegt"
mkdir -p "$PROJECTS_ROOT"
ok "Projekte-Ordner: $PROJECTS_ROOT"

# ── Zusammenfassung ───────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo "  Zusammenfassung"
echo "========================================"

if [ $ERRORS -eq 0 ] && [ $WARNINGS -eq 0 ]; then
    echo -e "  ${GREEN}Alles bereit!${NC}"
    echo ""
    echo "  Starten mit:  ./start.sh"
elif [ $ERRORS -eq 0 ]; then
    echo -e "  ${YELLOW}$WARNINGS Warnung(en) — Tool startet, einige Funktionen fehlen.${NC}"
    echo ""
    echo "  Starten mit:  ./start.sh"
else
    echo -e "  ${RED}$ERRORS Fehler — bitte die Fehler oben beheben und install.sh erneut ausführen.${NC}"
    if [ $WARNINGS -gt 0 ]; then
        echo -e "  ${YELLOW}$WARNINGS Warnung(en) zusätzlich vorhanden.${NC}"
    fi
    echo ""
    echo "  Pfade in start.sh und freecad_runner.py ggf. anpassen,"
    echo "  dann erneut:  ./install.sh"
fi

echo ""

# Aktivierung der venv in Erinnerung rufen
if [ $ERRORS -eq 0 ]; then
    echo "  Hinweis: start.sh aktiviert die venv automatisch."
    echo "  Für manuelle Ausführung: source venv/bin/activate"
    echo ""
fi
