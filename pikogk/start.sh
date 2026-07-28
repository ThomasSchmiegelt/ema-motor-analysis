#!/usr/bin/env bash
#
# Starts the PicoGK Hairpin-Test web UI (backend + static frontend).
# Local proof-of-concept only, no external services.
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEBAPI_DIR="$SCRIPT_DIR/PicoGKWebApi"

export DOTNET_ROOT="$HOME/.dotnet"
export PATH="$HOME/.dotnet:$PATH"

# PicoGK always opens a native GLFW/OpenGL viewer window internally
# (Library.Go), even when driven via the web API - it needs a real X display.
export DISPLAY="${DISPLAY:-:1}"

if [ ! -d "$WEBAPI_DIR" ]; then
  echo "Fehler: $WEBAPI_DIR nicht gefunden." >&2
  exit 1
fi

if [ ! -f "$HOME/.dotnet/dotnet" ]; then
  echo "Fehler: .NET 9 SDK nicht in ~/.dotnet gefunden. Siehe EXPERIENCE_REPORT.md, Abschnitt 3." >&2
  exit 1
fi

if [ ! -f "$SCRIPT_DIR/PicoGKRuntime/Dist/picogk.so" ]; then
  echo "Fehler: native PicoGK-Runtime (picogk.so) nicht gefunden." >&2
  echo "Siehe EXPERIENCE_REPORT.md, Abschnitt 4, um sie zu bauen." >&2
  exit 1
fi

# Beende evtl. noch laufende alte Instanzen - sonst blockiert ein verwaister
# Prozess (z.B. nach geschlossenem Terminal) Port 5266 mit einer alten Version,
# waehrend der Browser schon die neue Seite laedt (fuehrte zu "keine values"-Fehlern).
# Muster = voller Binary-Pfad, NICHT nur der Name: pkill -f matcht sonst jeden
# Prozess, der den String zufaellig in der Kommandozeile traegt (z.B. ein
# grep/curl darauf) - das hat beim Testen prompt die eigene Shell getroffen.
OLD_INSTANCE_PATTERN="PicoGKWebApi/bin/[^ ]*/PicoGKWebApi"
if pgrep -f "$OLD_INSTANCE_PATTERN" >/dev/null 2>&1; then
  echo "Beende noch laufende PicoGKWebApi-Instanz(en) ..."
  pkill -f "$OLD_INSTANCE_PATTERN" || true
  # warten bis der Prozess weg ist (max. 5s) - SIGTERM gibt zwar den Port
  # frei, der Prozess selbst haengt aber manchmal (nativer PicoGK-Viewer-
  # Thread), daher danach SIGKILL als Eskalation.
  for _ in $(seq 1 10); do
    if ! pgrep -f "$OLD_INSTANCE_PATTERN" >/dev/null 2>&1; then
      break
    fi
    sleep 0.5
  done
  if pgrep -f "$OLD_INSTANCE_PATTERN" >/dev/null 2>&1; then
    echo "Alte Instanz reagiert nicht auf SIGTERM - erzwinge Beendigung (SIGKILL) ..."
    pkill -9 -f "$OLD_INSTANCE_PATTERN" || true
    sleep 1
  fi
  if ss -tln 2>/dev/null | grep -q ':5266 '; then
    echo "Fehler: Port 5266 ist weiterhin belegt - alte Instanz liess sich nicht beenden." >&2
    exit 1
  fi
fi

echo "Starte PicoGK Web API (DISPLAY=$DISPLAY) ..."
echo "Ein PicoGK-Viewer-Fenster oeffnet sich zusaetzlich auf dem Desktop - das ist normal (PicoGK benoetigt es intern)."
echo "Es startet leer/weiss und zeigt erst nach dem ersten Klick auf 'Generieren' etwas an."
echo "Die eigentliche Bedienoberflaeche (das Menue) ist die Browser-Seite, die sich gleich automatisch oeffnet: http://localhost:5266"
echo
echo "Zylinderkopf-Skills: fertige Instanzen und deren Referenzdaten ueberstehen"
echo "sowohl das Schliessen des Browser-Tabs als auch einen Neustart dieses Skripts."
echo "Ein Skill-Lauf, der genau beim Beenden/Kill aktiv war, wird beim naechsten Start"
echo "als 'fehlgeschlagen' erkannt (PicoGK kann laufende Berechnungen nicht fortsetzen) -"
echo "in dem Fall den Skill in der Seite einfach erneut ausfuehren."
echo

cd "$WEBAPI_DIR"
dotnet run --no-launch-profile &
SERVER_PID=$!

# Poll until the server answers, then open the actual web UI in the browser -
# without this, only the (initially blank) native PicoGK viewer window is
# visible and it's easy to miss that the real menu is a browser page.
(
  for _ in $(seq 1 60); do
    if curl -sf http://localhost:5266/ >/dev/null 2>&1; then
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open http://localhost:5266 >/dev/null 2>&1 &
      else
        echo "Bitte manuell im Browser oeffnen: http://localhost:5266"
      fi
      break
    fi
    sleep 0.5
  done
) &

wait "$SERVER_PID"
