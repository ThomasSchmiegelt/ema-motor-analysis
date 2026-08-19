#!/usr/bin/env bash
# Studio 2.0 (BrickLink) unter Wine einrichten.
#
# Studio ist offiziell nur Windows/macOS. Unter Linux laeuft es via Wine; getestet
# mit Wine 9.0. Wir legen einen *eigenen* Prefix an, damit ein bestehendes ~/.wine
# unberuehrt bleibt und der Zustand mit dem Projekt geloescht werden kann.
#
# Rolle von Studio in diesem Projekt: Betrachter fuer die erzeugten .ldr-Modelle,
# Bauanleitung und Teileliste. Nicht als Datenquelle — dafuer dient LDraw/OMR.
# Fuer den Alltag ist LDView der schnellere Betrachter; Studio brauchen wir fuer
# Anleitung und Stueckliste.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export WINEPREFIX="${WINEPREFIX:-$ROOT/data/wine-studio}"
export WINEARCH=win64
export DISPLAY="${DISPLAY:-:1}"
export PATH="$HOME/.local/bin:$PATH"
# Wine-Debugmeldungen sind hier reines Rauschen.
export WINEDEBUG="${WINEDEBUG:--all}"

INSTALLER="$ROOT/data/downloads/Studio2.0.exe"
URL="https://studio.download.bricklink.info/Studio2.0/Studio+2.0.exe"

log() { printf '\n=== %s\n' "$*"; }

command -v wine >/dev/null || { echo "wine fehlt" >&2; exit 1; }

if [[ ! -f "$INSTALLER" ]]; then
  log "Installer laden (436 MB)"
  mkdir -p "$(dirname "$INSTALLER")"
  curl -L --retry 3 -o "$INSTALLER" "$URL"
fi

log "Wine-Prefix initialisieren: $WINEPREFIX"
mkdir -p "$WINEPREFIX"
wineboot --init 2>&1 | grep -viE '^(wine: |[0-9a-f]{4}:)' || true
wineserver -w

log "Windows-Version auf 10 setzen"
wine reg add 'HKCU\Software\Wine' /v Version /d win10 /f >/dev/null 2>&1

# Virtueller Desktop: verhindert, dass Studio den Eingabefokus verliert oder beim
# Alt-Tab einfriert — das haeufigste Problem dieser Kombination.
log "Virtuellen Desktop aktivieren (1600x900)"
wine reg add 'HKCU\Software\Wine\Explorer' /v Desktop /d Default /f >/dev/null 2>&1
wine reg add 'HKCU\Software\Wine\Explorer\Desktops' /v Default /d 1600x900 /f >/dev/null 2>&1

# corefonts braucht cabextract, das ohne sudo nicht nachinstallierbar ist. Die unten
# kopierten Systemschriften decken den Bedarf ab; der Schritt ist daher optional.
log "corefonts installieren (optional, braucht cabextract)"
if command -v cabextract >/dev/null; then
  winetricks -q corefonts 2>&1 | tail -3 || echo "  (corefonts fehlgeschlagen)"
else
  echo "  cabextract fehlt — uebersprungen, Systemschriften genuegen"
fi

# Ohne echte TrueType-Schriften bleibt die Bauanleitungs-Vorschau leer.
log "Systemschriften in den Prefix kopieren"
FONTDIR="$WINEPREFIX/drive_c/windows/Fonts"
mkdir -p "$FONTDIR"
# Ohne das Umleiten in eine Datei wuerde `head` die Pipe schliessen, `find` ein
# SIGPIPE kassieren und `set -o pipefail` das ganze Skript beenden — vor dem Setup.
mapfile -t FONTS < <(find /usr/share/fonts -name '*.ttf' 2>/dev/null | head -200)
for f in "${FONTS[@]}"; do
  cp -n "$f" "$FONTDIR/" 2>/dev/null || true
done
echo "  $(ls "$FONTDIR" | wc -l) Schriftdateien"

log "Studio 2.0 installieren (Inno Setup, unbeaufsichtigt)"
wine "$INSTALLER" /VERYSILENT /SUPPRESSMSGBOXES /NORESTART /SP- 2>&1 | tail -5 || true
wineserver -w

EXE="$(find "$WINEPREFIX/drive_c" -iname 'Studio.exe' -o -iname 'Stud.io.exe' 2>/dev/null | head -1)"
if [[ -n "$EXE" ]]; then
  log "Installiert: ${EXE#$WINEPREFIX/}"
  printf '%s\n' "$EXE" > "$ROOT/data/studio_exe.path"
else
  log "Studio.exe nicht gefunden — Installation pruefen"
  find "$WINEPREFIX/drive_c" -maxdepth 4 -iname '*studio*' 2>/dev/null | head -10
  exit 1
fi

cat <<EOF

Starten:
  WINEPREFIX=$WINEPREFIX DISPLAY=$DISPLAY wine "$EXE"
oder:
  $ROOT/studio/run_studio.sh
EOF
