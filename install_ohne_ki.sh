#!/bin/bash
# install_ohne_ki.sh -- das CAE-System OHNE KI-Komponenten einrichten.
#
# Gedacht fuer einen kleinen Rechner ohne GPU/Ollama. Installiert und richtet ein:
#   * cae_orchestrator (Flask, :5000) mit venv und den Rechen-Abhaengigkeiten
#   * FreeCAD, CalculiX, Elmer, Gmsh (Pakete des Systems, KEIN Quellbau, KEIN pixi)
#   * pandoc/pdflatex fuer PDF-Berichte (optional: --ohne-pdf)
#
# Bewusst NICHT dabei: Ollama, PI, Hermes, physics_surrogate (Torch/CUDA), lego,
# pikogk (.NET + native Bibliothek), FluidX3D/OpenFOAM/Blender (gross, GPU).
# Der Orchestrator laeuft ohne Ollama vollstaendig; nur Bericht-Text, Chat,
# KI-Entwurf und Agenten-Reiter fallen weg (die Routen antworten 503).
#
# FreeCAD-Anbindung: der Code ruft FreeCAD ueber ~/freecad_1.1_quellcode und
# `pixi run` auf. Dieses Skript baut dort ein duennes Geruest (pixi-Attrappe,
# FreeCADCmd-/ccx-Verweise auf die Systempakete), damit der Code unveraendert
# laeuft. Eine vorhandene echte Installation dort wird NIE angefasst.
# Achtung: die Systempakete sind FreeCAD 0.21.x, nicht das 1.1.x, gegen das der
# Code geschrieben wurde -- FreeCAD-Stufen (CAD, Struktur-FEM ueber FreeCAD)
# koennen abweichen. Der eigene Rechensatz (ema_deck: Gmsh + ccx) braucht
# FreeCAD nicht.
#
# Aufruf:  ./install_ohne_ki.sh [--ohne-pdf] [--ohne-elmer] [--pruefen]
# Braucht fuer apt root oder sudo; ohne beides werden fehlende Pakete nur genannt.

set -u
cd "$(dirname "$0")"
REPO="$(pwd)"

GREEN="\033[0;32m"; YELLOW="\033[1;33m"; RED="\033[0;31m"; BLUE="\033[0;34m"; NC="\033[0m"
ok()   { echo -e "  ${GREEN}[OK]${NC}     $*"; }
warn() { echo -e "  ${YELLOW}[WARN]${NC}   $*"; WARNUNGEN=$((WARNUNGEN + 1)); }
fail() { echo -e "  ${RED}[FEHLER]${NC} $*"; FEHLER=$((FEHLER + 1)); }
info() { echo -e "  ${BLUE}[INFO]${NC}   $*"; }
FEHLER=0; WARNUNGEN=0

PDF=1; ELMER=1; NUR_PRUEFEN=0
for a in "$@"; do
    case "$a" in
        --ohne-pdf)   PDF=0 ;;
        --ohne-elmer) ELMER=0 ;;
        --pruefen)    NUR_PRUEFEN=1 ;;
        -h|--help)    sed -n '2,28p' "$0"; exit 0 ;;
        *) echo "unbekannte Option: $a"; exit 2 ;;
    esac
done

FREECAD_ROOT="${FREECAD_ROOT:-$HOME/freecad_1.1_quellcode}"
PROJECTS_ROOT="$HOME/cae_projekte"

echo ""
echo "========================================"
echo "  CAE-System ohne KI -- Installation"
echo "========================================"

# ── Rechte / Paketverwaltung ──────────────────────────────────────────────────
if [ "$(id -u)" -eq 0 ]; then SUDO=""
elif command -v sudo >/dev/null 2>&1 && sudo -n true 2>/dev/null; then SUDO="sudo"
else SUDO="-"; fi

if ! command -v apt-get >/dev/null 2>&1; then
    fail "apt-get fehlt -- das Skript ist fuer Debian/Ubuntu geschrieben"
    exit 1
fi

fehlend=()
brauche() {   # brauche <paket>... : merkt vor, was nicht installiert ist
    local p
    for p in "$@"; do
        dpkg -s "$p" >/dev/null 2>&1 || fehlend+=("$p")
    done
}

echo -e "\n${BLUE}1. Systempakete${NC}"
brauche python3 python3-venv python3-pip build-essential
brauche freecad calculix-ccx gmsh
[ "$PDF" = 1 ]   && brauche pandoc texlive-latex-base texlive-fonts-recommended
# vtk (offscreen) braucht diese Bibliotheken; ohne sie scheitert der pip-Import
brauche libgl1 libxrender1 libglu1-mesa

# Elmer: Ubuntu-Archiv fuehrt es nicht immer; PPA des Elmer-Projekts als Rueckfall
ELMER_PAKET=""
if [ "$ELMER" = 1 ]; then
    if command -v ElmerSolver >/dev/null 2>&1 && command -v ElmerGrid >/dev/null 2>&1; then
        ok "Elmer vorhanden: $(command -v ElmerSolver)"
    elif apt-cache show elmerfem-csc >/dev/null 2>&1; then
        ELMER_PAKET=elmerfem-csc
    elif apt-cache show elmer >/dev/null 2>&1; then
        ELMER_PAKET=elmer
    else
        ELMER_PAKET=elmerfem-csc; ELMER_PPA=1
    fi
    [ -n "$ELMER_PAKET" ] && brauche "$ELMER_PAKET"
fi

if [ ${#fehlend[@]} -eq 0 ]; then
    ok "alle Pakete vorhanden"
elif [ "$NUR_PRUEFEN" = 1 ]; then
    warn "wuerden installiert: ${fehlend[*]}"
elif [ "$SUDO" = "-" ]; then
    fail "root/sudo fehlt, es fehlen: ${fehlend[*]}"
    info "als Administrator:  sudo apt install -y ${fehlend[*]}"
else
    if [ "${ELMER_PPA:-0}" = 1 ]; then
        info "Elmer-PPA wird eingetragen"
        $SUDO apt-get install -y software-properties-common >/dev/null 2>&1
        $SUDO add-apt-repository -y ppa:elmer-csc-ubuntu/elmer-csc-ppa >/dev/null 2>&1 \
            || warn "PPA nicht eintragbar -- Elmer (3D-Feld, 2D-Feld) bleibt aus"
    fi
    info "installiere: ${fehlend[*]}"
    $SUDO apt-get update -qq
    if DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends "${fehlend[@]}"; then
        ok "Pakete installiert"
    else
        # ein fehlendes Einzelpaket soll nicht alles kippen: einzeln nachholen
        for p in "${fehlend[@]}"; do
            DEBIAN_FRONTEND=noninteractive $SUDO apt-get install -y --no-install-recommends "$p" \
                >/dev/null 2>&1 && ok "$p" || fail "$p nicht installierbar"
        done
    fi
fi

# ── Python-Version ────────────────────────────────────────────────────────────
echo -e "\n${BLUE}2. Python${NC}"
if python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)' 2>/dev/null; then
    ok "Python $(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
else
    fail "Python >= 3.10 erforderlich"
fi

# ── FreeCAD-Geruest ───────────────────────────────────────────────────────────
echo -e "\n${BLUE}3. FreeCAD / CalculiX anbinden${NC}"
FCCMD="$(command -v freecadcmd || command -v FreeCADCmd || true)"
CCX="$(command -v ccx || command -v ccx_2.21 || true)"
if [ -e "$FREECAD_ROOT/build/release/bin/FreeCADCmd" ] && [ -e "$FREECAD_ROOT/.pixi/envs/default/bin/ccx" ]; then
    ok "vorhandene FreeCAD-Installation bleibt unberuehrt: $FREECAD_ROOT"
elif [ -z "$FCCMD" ] || [ -z "$CCX" ]; then
    warn "freecadcmd/ccx nicht im PATH -- Geruest nicht gebaut"
else
    mkdir -p "$FREECAD_ROOT/build/release/bin" "$FREECAD_ROOT/.pixi/envs/default/bin"
    ln -sfn "$FCCMD" "$FREECAD_ROOT/build/release/bin/FreeCADCmd"
    ln -sfn "$FCCMD" "$FREECAD_ROOT/build/release/bin/FreeCAD"
    ln -sfn "$CCX"   "$FREECAD_ROOT/.pixi/envs/default/bin/ccx"
    : > "$FREECAD_ROOT/pixi.toml"
    ok "Geruest: $FREECAD_ROOT (-> $FCCMD, $CCX)"
fi

# pixi-Attrappe: `pixi run --manifest-path X -- cmd args…` -> cmd args (Arbeitsverz. bleibt)
if command -v pixi >/dev/null 2>&1 && ! grep -q "attrappe-ohne-ki" "$(command -v pixi)" 2>/dev/null; then
    ok "echtes pixi vorhanden, wird nicht ersetzt"
else
    mkdir -p "$HOME/.local/bin"
    cat > "$HOME/.local/bin/pixi" <<'ATTRAPPE'
#!/bin/bash
# attrappe-ohne-ki: ersetzt `pixi run --manifest-path X -- <befehl…>` durch den Befehl selbst.
[ "${1:-}" = "run" ] || { echo "pixi-Attrappe: nur 'run' unterstuetzt" >&2; exit 2; }
shift
while [ $# -gt 0 ]; do
    case "$1" in
        --manifest-path) shift 2 ;;
        --) shift; break ;;
        *) break ;;
    esac
done
exec "$@"
ATTRAPPE
    chmod +x "$HOME/.local/bin/pixi"
    ok "pixi-Attrappe: $HOME/.local/bin/pixi"
    case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *)
        warn "~/.local/bin nicht im PATH -- in ~/.bashrc:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
    esac
fi

# ── Elmer / Gmsh Pruefung ─────────────────────────────────────────────────────
echo -e "\n${BLUE}4. Solver${NC}"
[ -n "$CCX" ] && ok "CalculiX: $CCX" || fail "CalculiX (ccx) fehlt"
[ -n "$FCCMD" ] && ok "FreeCAD: $FCCMD" || warn "FreeCAD fehlt -- nur der eigene Rechensatz (Gmsh+ccx) laeuft"
if [ "$ELMER" = 1 ]; then
    if command -v ElmerSolver >/dev/null 2>&1 && command -v ElmerGrid >/dev/null 2>&1; then
        ok "Elmer: $(command -v ElmerSolver)"
    else
        warn "Elmer fehlt -- 3D-Feld-Reiter deaktiviert"
    fi
fi

# ── venv ──────────────────────────────────────────────────────────────────────
echo -e "\n${BLUE}5. Python-Umgebung (cae_orchestrator)${NC}"
if [ "$NUR_PRUEFEN" = 1 ]; then
    info "uebersprungen (--pruefen)"
else
    cd "$REPO/cae_orchestrator"
    # ddgs/trafilatura gehoeren nur zur Agenten-Recherche (braucht KI) -> weglassen
    grep -v -E '^(ddgs|trafilatura)\b' requirements.txt > /tmp/requirements_ohne_ki.$$.txt
    [ -d venv ] || python3 -m venv venv
    # shellcheck disable=SC1091
    source venv/bin/activate
    pip install --upgrade pip -q
    if pip install -r /tmp/requirements_ohne_ki.$$.txt -q; then
        ok "Abhaengigkeiten installiert (ohne ddgs/trafilatura)"
    else
        fail "pip install fehlgeschlagen"
    fi
    rm -f /tmp/requirements_ohne_ki.$$.txt
    mkdir -p workspace
    cd "$REPO"
fi

mkdir -p "$PROJECTS_ROOT" && ok "Projekte-Ordner: $PROJECTS_ROOT"

# ── Zusammenfassung ───────────────────────────────────────────────────────────
echo ""
echo "========================================"
if [ $FEHLER -eq 0 ]; then
    echo -e "  ${GREEN}Fertig${NC} ($WARNUNGEN Warnung(en))"
    echo ""
    echo "  Starten:   cd cae_orchestrator && CAE_NO_BROWSER=1 ./start.sh"
    echo "  Aufruf:    http://localhost:5000"
    echo ""
    echo "  Hinweis: start.sh meldet Ollama als nicht erreichbar -- das ist hier gewollt."
else
    echo -e "  ${RED}$FEHLER Fehler${NC}, $WARNUNGEN Warnung(en) -- oben beheben, dann erneut ausfuehren."
fi
echo "========================================"
[ $FEHLER -eq 0 ]
