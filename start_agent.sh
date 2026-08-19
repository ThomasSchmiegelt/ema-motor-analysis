#!/bin/bash
# Startet die gesamte Kette und haengt eine PI-Sitzung mit dem LOKALEN Modell an.
#
#   ./start_agent.sh                      interaktive Sitzung
#   ./start_agent.sh -p "Wie viele …"     eine Frage, dann Ende
#   ./start_agent.sh --kein-browser       Server ohne Browserfenster starten
#   ./start_agent.sh --nur-server         nur den Orchestrator, kein PI
#
# Alles Weitere wird unveraendert an `pi` durchgereicht (z. B. --model).
set -euo pipefail

MODEL="qwen3.8:latest"
MODEL_ID="22130167c4c2"          # aus `ollama list` — pinnt das Modell, nicht nur den Namen
PORT=5000
OLLAMA_URL="http://localhost:11434"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$ROOT/cae_orchestrator"
LOG="${TMPDIR:-/tmp}/cae_server_$USER.log"

export PATH="$HOME/.npm-global/bin:$PATH"   # pi liegt hier, weil ohne sudo installiert

BROWSER=1; NUR_SERVER=0; ARGS=()
for a in "$@"; do
    case "$a" in
        --kein-browser) BROWSER=0 ;;
        --nur-server)   NUR_SERVER=1 ;;
        *)              ARGS+=("$a") ;;
    esac
done

ok()   { echo "[OK] $*"; }
warn() { echo "[--] $*"; }
die()  { echo "FEHLER: $*" >&2; exit 1; }

# ── 1. Ollama ───────────────────────────────────────────────────────────────
curl -sf --max-time 3 "$OLLAMA_URL" >/dev/null \
    || die "Ollama nicht erreichbar ($OLLAMA_URL). Starten: sudo systemctl start ollama"
ok "Ollama: $OLLAMA_URL"

# ── 2. Modell — auf die ID festgenagelt ─────────────────────────────────────
# Der Name allein genuegt nicht: ein `ollama pull` unter gleichem Namen tauscht die
# Gewichte still aus, und dann rechnet ein anderes Modell als das gepruefte.
if [ "$NUR_SERVER" -eq 0 ]; then
    line="$(ollama list 2>/dev/null | awk -v m="$MODEL" '$1 == m {print; exit}')" || true
    [ -n "$line" ] || die "Modell '$MODEL' nicht in Ollama. Vorhandene: $(ollama list | awk 'NR>1{print $1}' | paste -sd' ')"
    have="$(awk '{print $2}' <<<"$line")"
    if [ "$have" != "$MODEL_ID" ]; then
        die "Modell '$MODEL' hat die ID $have, erwartet war $MODEL_ID.
       Entweder wurde es neu geladen, oder MODEL_ID in diesem Skript ist veraltet.
       Weiter nur, wenn das beabsichtigt ist — dann MODEL_ID anpassen."
    fi
    ok "Modell: $MODEL ($MODEL_ID)"

    command -v pi >/dev/null || die "pi nicht gefunden. Einrichtung: .agents/README.md"
    [ -f "$HOME/.pi/agent/models.json" ] || die "~/.pi/agent/models.json fehlt (Ollama-Anbieter)"
fi

# ── 3. Orchestrator ─────────────────────────────────────────────────────────
health() { curl -sf --max-time 3 "http://localhost:$PORT/status" >/dev/null; }

if health; then
    ok "Orchestrator laeuft bereits auf :$PORT"
else
    # Wer den Port haelt, ist die Frage — nicht, wie der Prozess heisst. `pkill -f`
    # vergleicht die ganze Kommandozeile und trifft dabei leicht den eigenen Aufruf
    # oder eine Shell, in der das Muster nur zufaellig vorkommt; ueber den Port ist es
    # eindeutig. start.sh raeumt ihn nicht selbst (anders als pikogk/start.sh) — die
    # Meldung "Address already in use" landete sonst im Hintergrundlog statt hier.
    if fuser -s "$PORT/tcp" 2>/dev/null; then
        warn "Port $PORT ist belegt, antwortet aber nicht — Prozess wird beendet"
        fuser -k -TERM "$PORT/tcp" 2>/dev/null || true
        for _ in $(seq 1 20); do fuser -s "$PORT/tcp" 2>/dev/null || break; sleep 0.5; done
        fuser -s "$PORT/tcp" 2>/dev/null && die "Port $PORT bleibt belegt — bitte von Hand nachsehen"
    fi

    echo "Starte Orchestrator (Log: $LOG) …"
    [ "$BROWSER" -eq 0 ] && export CAE_NO_BROWSER=1
    # setsid --fork loest den Server aus Sitzung UND Elternschaft des Skripts. Ohne das bleibt
    # er ein KIND von start_agent.sh (gemessen: PPID des Servers zeigte auf das Skript),
    # das Skript wartet beim Beenden auf ihn, und `./start_agent.sh | tee start.log`
    # haengt fuer immer — der Server laeuft, die Shell kommt nie zurueck. Das </dev/null
    # kappt die letzte geerbte Leitung. Nebeneffekt, der ebenso zaehlt: Strg-C im
    # aufrufenden Terminal beendet den Server nicht mehr mit.
    ( cd "$ORCH" && setsid --fork nohup ./start.sh >"$LOG" 2>&1 </dev/null & )

    for i in $(seq 1 60); do
        health && break
        sleep 1
        [ "$i" -eq 60 ] && { tail -20 "$LOG" >&2; die "Server nach 60 s nicht bereit — Log oben"; }
    done
    ok "Orchestrator: http://localhost:$PORT"
fi

if [ "$NUR_SERVER" -eq 1 ]; then
    echo "Nur-Server-Modus — PI nicht gestartet. Beenden: fuser -k $PORT/tcp"
    exit 0
fi

# ── 4. PI ───────────────────────────────────────────────────────────────────
# Aus dem Wurzelverzeichnis, sonst findet PI weder AGENTS.md noch .agents/skills/.
cd "$ROOT"
echo ""
echo "=== PI mit $MODEL — Skill 'cae-orchestrator' geladen ==="
echo ""
exec pi --provider ollama --model "$MODEL" "${ARGS[@]}"
