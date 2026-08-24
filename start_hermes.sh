#!/bin/bash
# Startet die Kette und haengt eine HERMES-Sitzung mit dem LOKALEN Modell an.
# Schwesterskript zu start_agent.sh (PI). Beide bedienen dieselbe Toolchain ueber
# denselben Skill — ./.agents/skills/cae-orchestrator/SKILL.md.
#
#   ./start_hermes.sh                     interaktive Sitzung
#   ./start_hermes.sh -z "Wie viele …"    eine Frage, dann Ende
#   ./start_hermes.sh --nur-pruefen       nur der Nachweis, dass nichts nach draussen geht
#   ./start_hermes.sh --kein-browser      Server ohne Browserfenster starten
#   ./start_hermes.sh --nur-server        nur den Orchestrator, kein Hermes
#
# Alles Weitere wird unveraendert an `hermes` durchgereicht.
#
# WARUM DER NETZNACHWEIS (--nur-pruefen, laeuft auch vor jedem normalen Start):
# Hermes' mitgelieferte Vorgabe ist `provider: auto` mit
# `base_url: https://openrouter.ai/api/v1`. Zwei offene Fehler im Projekt
# (NousResearch/hermes-agent #57255 und #14676) beschreiben ausserdem, dass
# `provider: ollama` bei einer base_url mit /v1 still auf `custom` durchfaellt und ein
# blankes `custom` ohne aufgeloeste base_url auf OpenRouter zeigt. Auf einer Maschine,
# deren Prinzip "nichts ueber das Heimnetz hinaus" ist, waere das ein stiller Abfluss.
# Die Konfigurationsdatei als Beleg genuegt darum nicht — geprueft wird, was in der
# Konfiguration steht UND ob ein echter Aufruf wirklich nur :11434 anspricht.
set -euo pipefail

MODEL="qwen-gross:latest"
MODEL_ID="6b9d840acbf5"          # aus `ollama list` — pinnt das Modell, nicht nur den Namen
PORT=5000
OLLAMA_URL="http://localhost:11434"
OLLAMA_HOSTPORT="127.0.0.1:11434"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$ROOT/cae_orchestrator"
LOG="${TMPDIR:-/tmp}/cae_server_$USER.log"

export PATH="$HOME/.local/bin:$PATH"   # hermes liegt hier (Installation ohne sudo)

BROWSER=1; NUR_SERVER=0; NUR_PRUEFEN=0; ARGS=()
for a in "$@"; do
    case "$a" in
        --kein-browser) BROWSER=0 ;;
        --nur-server)   NUR_SERVER=1 ;;
        --nur-pruefen)  NUR_PRUEFEN=1 ;;
        *)              ARGS+=("$a") ;;
    esac
done

ok()   { echo "[OK] $*"; }
warn() { echo "[--] $*"; }
die()  { echo "FEHLER: $*" >&2; exit 1; }

# ── 1. Ollama ───────────────────────────────────────────────────────────────
curl -sf --max-time 3 "$OLLAMA_URL" >/dev/null \
    || die "Ollama nicht erreichbar ($OLLAMA_URL)."
ok "Ollama: $OLLAMA_URL"

# ── 2. Modell — auf die ID festgenagelt ─────────────────────────────────────
# Wie bei PI: der Name allein genuegt nicht, ein `ollama pull` unter gleichem Namen
# tauscht die Gewichte still aus.
line="$(ollama list 2>/dev/null | awk -v m="$MODEL" '$1 == m {print; exit}')" || true
[ -n "$line" ] || die "Modell '$MODEL' nicht in Ollama."
have="$(awk '{print $2}' <<<"$line")"
[ "$have" = "$MODEL_ID" ] || die "Modell '$MODEL' hat die ID $have, erwartet war $MODEL_ID.
       Entweder wurde es neu geladen, oder MODEL_ID in diesem Skript ist veraltet."
ok "Modell: $MODEL ($MODEL_ID)"

command -v hermes >/dev/null || die "hermes nicht gefunden. Einrichtung: .agents/README.md"

# ── 3. Der Netznachweis ─────────────────────────────────────────────────────
netznachweis() {
    local cfg="$HOME/.hermes/config.yaml"
    [ -f "$cfg" ] || die "$cfg fehlt — 'hermes config set model.provider ollama' usw."

    local prov base modl
    prov="$(awk '/^model:/{m=1} m && /^[[:space:]]+provider:/{gsub(/[",]/,"");print $2; exit}' "$cfg")"
    base="$(awk '/^model:/{m=1} m && /^[[:space:]]+base_url:/{gsub(/[",]/,"");print $2; exit}' "$cfg")"
    modl="$(awk '/^model:/{m=1} m && /^[[:space:]]+default:/{gsub(/[",]/,"");print $2; exit}' "$cfg")"

    [ "$prov" = "ollama" ] || die "model.provider ist '$prov', erwartet 'ollama'."
    case "$base" in
        http://localhost:11434/*|http://127.0.0.1:11434/*) ;;
        *) die "model.base_url ist '$base' — das zeigt nicht auf das lokale Ollama." ;;
    esac
    [ "$modl" = "$MODEL" ] || warn "model.default ist '$modl', dieses Skript pinnt '$MODEL'"
    ok "Konfiguration: provider=$prov  base_url=$base  model=$modl"

    # Fremdschluessel duerfen nicht gesetzt sein — sonst koennte ein Rueckfall greifen.
    local env="$HOME/.hermes/.env" gefunden=""
    if [ -f "$env" ]; then
        gefunden="$(grep -vE '^[[:space:]]*#' "$env" 2>/dev/null \
                    | grep -oE '^(OPENROUTER|OPENAI|ANTHROPIC|NOUS|GEMINI|GOOGLE|FIREWORKS)_API_KEY' \
                    || true)"
    fi
    [ -z "$gefunden" ] || die "In $env stehen fremde Schluessel: $(tr '\n' ' ' <<<"$gefunden")
       Solange die gesetzt sind, kann ein Rueckfall nach draussen greifen."
    ok "Keine Fremdschluessel in ~/.hermes/.env"

    # Und jetzt gemessen statt geglaubt: ein echter Aufruf, dabei die Verbindungen
    # des hermes-Prozesses mitschreiben.
    local spur; spur="$(mktemp)"
    # ACHTUNG set -e: ohne das `|| true` beendet sich diese Unterschale beim ERSTEN
    # Durchlauf, in dem grep nichts findet — also bevor Hermes ueberhaupt verbunden
    # ist. Die Spur bliebe leer, und eine leere Spur sah dann aus wie ein bestandener
    # Nachweis. Genau das ist hier einmal passiert.
    # Spalten von `ss -tnp`: 4 = eigene Adresse, 5 = GEGENSTELLE, 6 = Prozess.
    ( for _ in $(seq 1 240); do
          ss -tnp 2>/dev/null | grep '"hermes"' | awk '{print $5}' || true
          sleep 0.25
      done ) > "$spur" 2>&1 || true &
    local wach=$!
    local antwort; antwort="$(timeout 180 hermes -z "Antworte nur mit dem Wort BEREIT." 2>&1 | tail -1)" || true
    sleep 1; kill "$wach" 2>/dev/null || true

    local fremd; fremd="$(sort -u "$spur" | grep -vE "^${OLLAMA_HOSTPORT}$|^\[?::1\]?:|^$" || true)"
    if [ -n "$fremd" ]; then
        echo "$fremd" >&2
        rm -f "$spur"
        die "Hermes hat Verbindungen ausserhalb von $OLLAMA_HOSTPORT aufgebaut (oben)."
    fi
    local n; n="$(grep -c "^${OLLAMA_HOSTPORT}$" "$spur" || true)"
    rm -f "$spur"
    # Keine beobachtete Verbindung ist KEIN bestandener Nachweis, sondern ein
    # fehlgeschlagener: dann hat die Messung nichts gesehen und belegt nichts.
    [ "$n" -gt 0 ] || die "Es wurde KEINE Verbindung zu $OLLAMA_HOSTPORT beobachtet.
       Damit ist nichts nachgewiesen — der Nachweis gilt als nicht bestanden.
       (Antwort war: ${antwort:0:60})"
    ok "Gemessen: $n Beobachtungen, alle auf $OLLAMA_HOSTPORT, keine Gegenstelle
     ausserhalb. Antwort: ${antwort:0:40}"
}

if [ "$NUR_PRUEFEN" -eq 1 ]; then
    netznachweis
    echo "Nachweis bestanden — nichts gestartet."
    exit 0
fi

# ── 4. Orchestrator ─────────────────────────────────────────────────────────
health() { curl -sf --max-time 3 "http://localhost:$PORT/status" >/dev/null; }

if health; then
    ok "Orchestrator laeuft bereits auf :$PORT"
else
    if fuser -s "$PORT/tcp" 2>/dev/null; then
        warn "Port $PORT ist belegt, antwortet aber nicht — Prozess wird beendet"
        fuser -k -TERM "$PORT/tcp" 2>/dev/null || true
        for _ in $(seq 1 20); do fuser -s "$PORT/tcp" 2>/dev/null || break; sleep 0.5; done
        fuser -s "$PORT/tcp" 2>/dev/null && die "Port $PORT bleibt belegt"
    fi
    echo "Starte Orchestrator (Log: $LOG) …"
    [ "$BROWSER" -eq 0 ] && export CAE_NO_BROWSER=1
    # setsid --fork wie in start_agent.sh: sonst bleibt der Server ein Kind dieses
    # Skripts und `./start_hermes.sh | tee` haengt fuer immer.
    ( cd "$ORCH" && setsid --fork nohup ./start.sh >"$LOG" 2>&1 </dev/null & )
    for i in $(seq 1 60); do
        health && break
        sleep 1
        [ "$i" -eq 60 ] && { tail -20 "$LOG" >&2; die "Server nach 60 s nicht bereit"; }
    done
    ok "Orchestrator: http://localhost:$PORT"
fi

if [ "$NUR_SERVER" -eq 1 ]; then
    echo "Nur-Server-Modus — Hermes nicht gestartet. Beenden: fuser -k $PORT/tcp"
    exit 0
fi

# ── 5. Hermes ───────────────────────────────────────────────────────────────
# Aus dem Wurzelverzeichnis, sonst findet Hermes weder AGENTS.md noch die
# repo-eigenen Skills unter ./.agents/skills/ — die lädt es nur in einem Projekt,
# das mit `hermes skills trust .` freigegeben wurde. Genau darum wird KEIN Skill
# kopiert oder verlinkt: PI und Hermes lesen dieselbe Datei.
cd "$ROOT"

# NICHT `hermes skills list | grep -q`: grep -q schliesst die Leitung beim ersten
# Treffer, hermes bekommt SIGPIPE, und mit `pipefail` gilt die ganze Pipeline als
# gescheitert — die Warnung erschien dann, obwohl der Skill geladen war.
skill_liste="$(hermes skills list 2>/dev/null || true)"
if ! grep -q 'cae-orchestrator' <<<"$skill_liste"; then
    warn "Der Skill cae-orchestrator ist nicht sichtbar — einmalig freigeben:"
    warn "    hermes skills trust $ROOT"
fi

echo
exec hermes --model "$MODEL" ${ARGS[@]+"${ARGS[@]}"}
