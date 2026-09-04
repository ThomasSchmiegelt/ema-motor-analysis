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
#   ./start_hermes.sh --projekt <id>      an ein CAE-Projekt binden ('letztes' = juengstes)
#   ./start_hermes.sh --kein-projekt      ohne Projektbindung (gemeinsamer Speicher)
#   ./start_hermes.sh --neu               ohne Rueckfrage eine neue Sitzung
#   ./start_hermes.sh --weiter            ohne Rueckfrage die letzte Sitzung fortsetzen
#   ./start_hermes.sh --nur-vorbereiten   Projektbindung + Kontext erzeugen, dann Ende
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
MODEL_ID="ca8ec377441f"          # aus `ollama list` — pinnt das Modell, nicht nur den Namen
# 02.09.2026 nachgezogen: qwen-gross wurde auf qwen3.8:27b-mtp-q4_K_M neu gebaut
# (identische Blobs, nur num_ctx 65536 ergaenzt). Der Wechsel ist geprueft und
# gewollt: MTP-Spekulativdekodierung, warm gemessen 93,1 statt 86,7 tok/s bei
# 65536 Kontext, und jetzt 100 % GPU statt 94 %. Vorher: 6b9d840acbf5.
PORT=5000
OLLAMA_URL="http://localhost:11434"
OLLAMA_HOSTPORT="127.0.0.1:11434"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$ROOT/cae_orchestrator"
LOG="${TMPDIR:-/tmp}/cae_server_$USER.log"

export PATH="$HOME/.local/bin:$PATH"   # hermes liegt hier (Installation ohne sudo)

BROWSER=1; NUR_SERVER=0; NUR_PRUEFEN=0; NUR_VORB=0; PROJEKT=""; OHNE_PROJEKT=0
SITZUNGSWAHL=""; ARGS=(); erwarte_projekt=""
for a in "$@"; do
    if [ -n "$erwarte_projekt" ]; then PROJEKT="$a"; erwarte_projekt=""; continue; fi
    case "$a" in
        --kein-browser) BROWSER=0 ;;
        --nur-server)   NUR_SERVER=1 ;;
        --nur-pruefen)  NUR_PRUEFEN=1 ;;
        --nur-vorbereiten) NUR_VORB=1 ;;
        --kein-projekt) OHNE_PROJEKT=1 ;;
        --projekt)      erwarte_projekt=1 ;;
        --projekt=*)    PROJEKT="${a#--projekt=}" ;;
        --neu)          SITZUNGSWAHL="neu" ;;
        --weiter)       SITZUNGSWAHL="weiter" ;;
        *)              ARGS+=("$a") ;;
    esac
done
[ -n "$erwarte_projekt" ] && { echo "FEHLER: --projekt braucht eine Kennung" >&2; exit 1; }

PROJEKTE="$HOME/cae_projekte"

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

if [ "$NUR_VORB" -eq 1 ]; then
    warn "Nur-Vorbereiten: der Orchestrator wird nicht gestartet."
elif health; then
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

# ── 5a. Projektbindung ──────────────────────────────────────────────────────
# Hermes' eingebauter Speicher ist EINE Datei fuer die ganze Maschine
# (~/.hermes/memories/MEMORY.md, gedeckelt auf 2200 Zeichen) — es gibt in der
# Konfiguration keinen Weg, ihn je Projekt zu fuehren. Ohne Gegenmassnahme
# vermischen sich damit die Erinnerungen aus verschiedenen Auslegungen: was der
# Agent ueber den Alpenpass-Antrieb gelernt hat, liest er beim Stadtantrieb als
# Tatsache wieder.
#
# Der Hebel ist HERMES_HOME. Es verschiebt die GANZE Hermes-Ablage — und das ist
# zu viel: eine je Projekt kopierte config.yaml ist genau die Drift, die dieses
# Repo beim Skill bewusst vermeidet (PI und Hermes lesen EINE Skill-Datei, keine
# Kopie). Deshalb wird die Ablage aufgeteilt: das Geteilte wird VERLINKT
# (config.yaml, .env, skills — eine Quelle, keine Kopie), projekteigen sind nur
# memories/ und sessions/. Nachgemessen: die verlinkte Konfiguration wird
# gelesen (model.default kommt als qwen-gross:latest zurueck), der Sitzungs-
# speicher ist leer und damit projekteigen.
# Das `|| true` ist nicht kosmetisch: findet `ls` nichts, gibt es 2 zurueck, die
# Funktion reicht das durch, und unter `set -e` bricht schon die Zuweisung ab — die
# eigene Fehlermeldung ("Kein Projekt zu ... gefunden") kaeme nie zum Vorschein.
# Gemessen: Abbruch mit Code 2 und LEERER Ausgabe.
projekt_pfad() {
    local kennung="$1"
    if [ "$kennung" = "letztes" ] || [ -z "$kennung" ]; then
        ls -d "$PROJEKTE"/2* 2>/dev/null | sort | tail -1 || true
    elif [ -d "$PROJEKTE/$kennung" ]; then
        echo "$PROJEKTE/$kennung"
    else
        ls -d "$PROJEKTE"/*"$kennung"* 2>/dev/null | sort | tail -1 || true
    fi
}

# ── Projektwahl am Terminal ─────────────────────────────────────────────────
#
# PI bindet einfach das juengste Projekt und fragt nur nach der Sitzung. Bei Hermes
# reicht das nicht: hier haengen ERINNERUNGEN am Projekt (HERMES_HOME), nicht nur
# ein Kontexttext. Wer versehentlich im falschen Projekt landet, bekommt das
# Gelernte einer anderen Auslegung als Tatsache serviert -- und merkt es nicht.
# Die Wahl kostet eine Zeile und verhindert genau das.
#
# Gefragt wird NUR am Terminal und nur, wenn weder --projekt noch --kein-projekt
# gesetzt ist; jeder Skript- oder Cron-Aufruf verhaelt sich unveraendert.
# Die Vorgabe ist das juengste Projekt, also genau das bisherige Verhalten.
# Ein neues Projekt anlegen -- mit DERSELBEN Funktion, die auch der Server hinter
# POST /project/new benutzt (``ema_pipeline.create_project_dir``, origin "manual").
# Ein blosses ``mkdir`` waere hier der naheliegende Fehler: es entstuende ein
# Verzeichnis ohne ``project.json``, und die Projektakte -- Status, Abstammung,
# Evolutionsverlauf -- fehlte genau bei den Projekten, die der Agent selbst anlegt.
# Der Server muss dafuer nicht laufen; die Funktion ist reines Dateisystem.
projekt_anlegen() {
    local name pfad
    read -r -p "Name des neuen Projekts (leer = nur Zeitstempel): " name || name=""
    # Aus $ORCH heraus, damit ema_pipeline seine Nachbarmodule findet -- kein
    # sys.path-Gebastel und keine zweite Vorstellung davon, wo der Code liegt.
    pfad="$(cd "$ORCH" && ./venv/bin/python -c '
import sys
from ema_pipeline import create_project_dir
voll, _pid = create_project_dir(sys.argv[1], sys.argv[2], origin="manual")
print(voll)' "$PROJEKTE" "$name" 2>/dev/null || true)"
    if [ -z "$pfad" ] || [ ! -d "$pfad" ]; then
        warn "Projekt konnte nicht angelegt werden — es bleibt beim juengsten."
        return 1
    fi
    PROJEKT="$(basename "$pfad")"
    ok "Angelegt: $PROJEKT"
    return 0
}

projekt_menue() {
    local liste
    liste="$(ls -d "$PROJEKTE"/2* 2>/dev/null | sort -r | head -8 || true)"
    echo
    if [ -z "$liste" ]; then
        # Frueher stieg das Menue hier aus (``[ -n "$liste" ] || return 0``) -- dann
        # war beim allerersten Start weder ein Projekt da noch eines anzulegen.
        echo "Noch keine Projekte in $PROJEKTE."
        local w0
        read -r -p "Neues Projekt anlegen [n] oder gemeinsamer Speicher [g]? (Vorgabe: n) " w0 || w0=""
        case "$w0" in
            g|G) OHNE_PROJEKT=1 ;;
            *)   projekt_anlegen || OHNE_PROJEKT=1 ;;
        esac
        return 0
    fi
    echo "Projekte in $PROJEKTE (neueste zuerst):"
    local i=0 pfade=() pf name stand hermes
    while IFS= read -r pf; do
        [ -d "$pf" ] || continue
        i=$((i+1)); pfade+=("$pf")
        name="$(basename "$pf")"
        # ASCII, nicht "—": printf zaehlt Bytes, und ein Gedankenstrich sind drei —
        # die Spalte rutscht dann um zwei Zeichen. Dieselbe Falle wie bei der
        # Sitzungsliste (dort geloest, indem bash die Zeichenkette selbst kuerzt).
        if [ -f "$pf/results.json" ]; then stand="gerechnet"; else stand="offen"; fi
        if [ -f "$pf/_agent/hermes/state.db" ]; then
            hermes="Hermes seit $(date -r "$pf/_agent/hermes/state.db" '+%d.%m. %H:%M')"
        else
            hermes="Hermes neu"
        fi
        printf "  %d) %-42s  %-10s  %s\n" "$i" "${name:0:42}" "$stand" "$hermes"
    done <<< "$liste"
    echo "  n) NEUES Projekt anlegen"
    echo "  g) gemeinsamer Speicher (ohne Projektbindung)"
    local wahl
    read -r -p "Projekt [1-$i], neu [n], gemeinsam [g]? (Vorgabe: 1) " wahl || wahl=""
    case "$wahl" in
        ''|1)   PROJEKT="$(basename "${pfade[0]}")" ;;
        n|N)    projekt_anlegen || PROJEKT="$(basename "${pfade[0]}")" ;;
        g|G)    OHNE_PROJEKT=1 ;;
        *) if [ "$wahl" -ge 1 ] 2>/dev/null && [ "$wahl" -le "$i" ]; then
               PROJEKT="$(basename "${pfade[$((wahl-1))]}")"
           else
               warn "'$wahl' ist keines der angebotenen Projekte — juengstes."
               PROJEKT="$(basename "${pfade[0]}")"
           fi ;;
    esac
}

if [ "$OHNE_PROJEKT" -eq 0 ] && [ -z "$PROJEKT" ] && [ "$NUR_SERVER" -eq 0 ] \
   && [ -t 0 ] && [ -t 1 ]; then
    projekt_menue
fi

PROJ_DIR=""
if [ "$OHNE_PROJEKT" -eq 0 ]; then
    PROJ_DIR="$(projekt_pfad "${PROJEKT:-letztes}")"
    if [ -z "$PROJ_DIR" ] || [ ! -d "$PROJ_DIR" ]; then
        if [ -n "$PROJEKT" ]; then
            die "Kein Projekt zu '$PROJEKT' in $PROJEKTE gefunden."
        fi
        warn "Noch kein Projekt in $PROJEKTE — Hermes laeuft mit gemeinsamem Speicher."
    fi
fi

if [ -n "$PROJ_DIR" ] && [ -d "$PROJ_DIR" ]; then
    HH="$PROJ_DIR/_agent/hermes"
    mkdir -p "$HH/memories" "$HH/sessions"
    # Geteiltes verlinken statt kopieren. -f, damit ein Wechsel der Quelle greift.
    for geteilt in config.yaml .env skills; do
        [ -e "$HOME/.hermes/$geteilt" ] || continue
        ln -sfn "$HOME/.hermes/$geteilt" "$HH/$geteilt"
    done
    export HERMES_HOME="$HH"
    ok "Projekt: $(basename "$PROJ_DIR")  (Erinnerungen + Sitzungen unter _agent/hermes/)"

    # ── Projektkontext: ERZEUGT, nicht kopiert ──────────────────────────────
    # Die Bitte war, eine Kopie der Master-AGENTS.md ins Projektverzeichnis zu
    # legen und mit der zu arbeiten. Eine Kopie waere aber genau der Fehler, den
    # dieses Repo beim Skill vermeidet: sie laeuft still auseinander, und dann
    # arbeiten zwei Agenten nach zwei Regelwerken, die beide plausibel aussehen.
    # Zweitens findet weder PI noch Hermes eine AGENTS.md im Projektordner — beide
    # lesen sie im Arbeitsverzeichnis, und das MUSS die Repo-Wurzel bleiben (PI
    # sortiert Sitzungen nach cwd).
    # Also andersherum: die Master-AGENTS.md bleibt die eine, unveraenderte Quelle,
    # und daneben entsteht bei JEDEM Start frisch eine Ergaenzung mit den Fakten
    # DIESES Projekts. Weil sie jedes Mal neu geschrieben wird, kann sie nicht
    # driften; sie ist nicht versioniert und nicht von Hand zu aendern.
    kontext="$ROOT/AGENTS.projekt.md"
    {
        echo "# Aktuelles Projekt — ERZEUGT von start_hermes.sh, nicht von Hand aendern"
        echo
        echo "Diese Datei wird bei jedem Agentenstart neu geschrieben. Die Regeln stehen"
        echo "in AGENTS.md; hier stehen nur die Fakten des Projekts, an dem gerade"
        echo "gearbeitet wird."
        echo
        echo "- Kennung: \`$(basename "$PROJ_DIR")\`"
        echo "- Verzeichnis: \`$PROJ_DIR\`"
        echo "- Erinnerungen/Sitzungen dieses Projekts: \`$PROJ_DIR/_agent/hermes/\`"
        echo "- Stand: $(date '+%d.%m.%Y %H:%M')"
        echo
        # Der volle Steckbrief, nicht nur die Kennwerte aus results.json:
        # Maschinenart, Pole, Nuten, Bauraum, Werkstoffe, Betriebspunkt — und
        # was daran schon gerechnet ist. Aus derselben Quelle wie der
        # Browserkopf (ema_steckbrief), damit Terminal und Browser nicht
        # Verschiedenes ueber dasselbe Projekt glauben. Er wird IMMER
        # geschrieben, auch ohne results.json: dass nichts gerechnet ist, sagt
        # er selbst.
        echo "## Steckbrief dieses Projekts"
        echo
        "$ROOT/.agents/projektstand.py" "$PROJ_DIR" \
            2>/dev/null || echo "- (Projektstand nicht lesbar)"
        echo
        echo "Ausfuehrlich, samt Herkunft jeder Zahl und frueheren Laeufen:"
        echo "\`python3 cae_orchestrator/cae_cli.py steckbrief $(basename "$PROJ_DIR") --laeufe\`"
        echo
        # Der Skill liegt da, aber `skill_view` findet ihn in `hermes acp`
        # v0.20.5 nicht (gemessen 04.09.2026). Ohne diesen Hinweis sucht der
        # Kopf danach -- oder arbeitet ohne ihn, und dann fehlen ihm Verben,
        # Laufzeiten, Exit-Codes und die Fallen.
        echo "## Der Skill"
        echo
        echo "Der Skill \`cae-orchestrator\` liegt als Datei unter"
        echo "\`.agents/skills/cae-orchestrator/SKILL.md\`. **Lies ihn dort.**"
        echo "Findet \`skill_view\` ihn nicht, ist das kein Grund zu suchen und"
        echo "keiner, ohne ihn zu arbeiten — eine Datei lesen, weiterarbeiten."
    } > "$kontext"
    ok "Projektkontext erzeugt: AGENTS.projekt.md"
else
    # Ohne Projektbindung wurde die Datei bisher gar nicht angefasst -- die des
    # letzten Laufs blieb liegen und war mit "Aktuelles Projekt" ueberschrieben.
    # Wer ausdruecklich OHNE Projekt startet, um etwas Neues zu entwerfen, bekam
    # so den vorigen Entwurf als seinen eigenen serviert, und das Modell hatte
    # keinen Anlass, daran zu zweifeln. Eine falsche Akte ist schlimmer als keine.
    {
        echo "# Aktuelles Projekt — ERZEUGT von start_hermes.sh, nicht von Hand aendern"
        echo
        echo "Diese Datei wird bei JEDEM Agentenstart neu geschrieben — auch wenn kein"
        echo "Projekt gebunden ist. Die Regeln stehen in AGENTS.md."
        echo
        echo "- Stand: $(date '+%d.%m.%Y %H:%M')"
        echo "- Agentenkopf: Hermes (start_hermes.sh)"
        echo "- Projekt: **keines gebunden** (gemeinsamer Speicher)"
        echo
        echo "**Es gibt kein aktuelles Projekt.** Was in frueheren Laeufen entworfen"
        echo "wurde, ist fuer diese Aufgabe keine Vorgabe und keine Vorlage. Eine neue"
        echo "Auslegung beginnt mit"
        echo "\`python3 cae_orchestrator/cae_cli.py aufgabe \"<Aufgabe>\"\` und danach"
        echo "\`paarvergleich --frisch\` — NICHT mit \`--from-project last\`."
    echo
    # Der Skill liegt da, aber `skill_view` findet ihn in `hermes acp` v0.20.5
    # nicht (gemessen 04.09.2026). Ohne diesen Hinweis sucht der Kopf danach --
    # oder arbeitet ohne ihn, und dann fehlen ihm Verben, Laufzeiten und Fallen.
    echo "## Der Skill"
    echo
    echo "Der Skill \`cae-orchestrator\` liegt als Datei unter"
    echo "\`.agents/skills/cae-orchestrator/SKILL.md\`. **Lies ihn dort.**"
    echo "Findet \`skill_view\` ihn nicht, ist das kein Grund zu suchen und"
    echo "keiner, ohne ihn zu arbeiten — eine Datei lesen, weiterarbeiten."
    echo
    } > "$ROOT/AGENTS.projekt.md"
fi

# ── 5b. Neue oder alte Sitzung? ─────────────────────────────────────────────
# Hermes kann beides (`--continue`, `--resume <id>`), fragte aber nie danach — und
# was nicht gefragt wird, wird nicht benutzt: eine neue Sitzung faengt bei null an,
# obwohl nebenan eine mit dem ganzen Verlauf liegt. Gefragt wird NUR interaktiv und
# nur, wenn nichts anderes vorgegeben ist; -z/--continue/--resume und ein fehlendes
# Terminal muessen sich unveraendert verhalten, sonst blockiert ein Skriptaufruf.
eigene_wahl=0
for a in ${ARGS[@]+"${ARGS[@]}"}; do
    case "$a" in
        -z|--continue|--continue=*|--resume|--resume=*|-z*) eigene_wahl=1 ;;
    esac
done

# `hermes sessions list` gibt nur eine Menschentabelle aus — kein JSON, keine Option
# dafuer. Der Sitzungsspeicher ist eine SQLite-Datei, deren Schema hier aber nichts zu
# suchen hat: daran gebunden bricht das Skript beim naechsten Hermes-Update still.
# Also die Tabelle lesen, aber nur an dem, was sicher ist -- die Kennung steht als
# letztes Feld und hat ein festes Muster (JJJJMMTT_HHMMSS_hex). Das `\r` muss weg:
# ueber ein Pseudoterminal (etwa `script`) endet jede Zeile auf CR, und das ueberschreibt
# beim Ausgeben den Zeilenanfang -- aus "E-Motor Konzept entwerfen" wurde "or Konzep".
sitzungen_hermes() {           # $1 = Anzahl; je Zeile: id <TAB> Titel <TAB> Alter
    hermes sessions list --limit "${1:-10}" 2>/dev/null | awk -v n="${1:-10}" '
        { gsub(/\r/, "") }
        $NF ~ /^[0-9]{8}_[0-9]{6}_[0-9a-f]+$/ {
            id = $NF
            alter = (NF >= 3) ? $(NF-2) " " $(NF-1) : ""
            titel = ""
            for (i = 1; i <= NF - 4; i++) titel = titel (i > 1 ? " " : "") $i
            if (titel == "") titel = "(ohne Titel)"
            print id "\t" titel "\t" alter
            if (++c >= n) exit
        }'
}

if [ "$eigene_wahl" -eq 0 ] && [ "$NUR_SERVER" -eq 0 ]; then
    # Am Terminal wird gefragt, sonst nicht: ein Skript- oder Cron-Aufruf darf nicht
    # auf eine Eingabe warten. -z ist oben schon als eigene Wahl erkannt.
    [ -z "$SITZUNGSWAHL" ] && [ -t 0 ] && [ -t 1 ] && {
        liste="$(sitzungen_hermes 5)"
        if [ -z "$liste" ]; then
            # Frueher wurde hier stillschweigend nichts angezeigt. Bei projekteigenem
            # HERMES_HOME ist der Sitzungsspeicher eines frischen Projekts IMMER leer
            # -- das Menue erschien also nie, und es sah aus, als gaebe es keines.
            echo
            echo "Noch keine Hermes-Sitzung in diesem Projekt — es wird eine neue angelegt."
            SITZUNGSWAHL="neu"
        else
            echo
            echo "Sitzungen in diesem Projekt:"
            i=0; ids=()
            while IFS=$'\t' read -r id titel alter; do
                i=$((i+1)); ids+=("$id")
                # Zeichen zaehlen, nicht Bytes — sonst zerschneidet die Kuerzung
                # Umlaute mitten im UTF-8-Zeichen. GNU `cut -c` taugt dafuer nicht.
                t="${titel:-—}"
                printf "  %d) %-34s  %s\n" "$i" "${t:0:34}" "$alter"
            done <<< "$liste"
            echo "  n) neue Sitzung"
            read -r -p "Fortsetzen [1-$i] oder neu [n]? (Vorgabe: n) " wahl || wahl="n"
            case "$wahl" in
                ''|n|N|neu) SITZUNGSWAHL="neu" ;;
                *) if [ "$wahl" -ge 1 ] 2>/dev/null && [ "$wahl" -le "$i" ]; then
                       SITZUNGSWAHL="id:${ids[$((wahl-1))]}"
                   else
                       warn "'$wahl' ist keine der angebotenen Sitzungen — neue Sitzung."
                       SITZUNGSWAHL="neu"
                   fi ;;
            esac
        fi
    }
    case "$SITZUNGSWAHL" in
        weiter)  ARGS=(--continue ${ARGS[@]+"${ARGS[@]}"}) ;;
        id:*)    ARGS=(--resume "${SITZUNGSWAHL#id:}" ${ARGS[@]+"${ARGS[@]}"}) ;;
    esac
fi

# NICHT `hermes skills list | grep -q`: grep -q schliesst die Leitung beim ersten
# Treffer, hermes bekommt SIGPIPE, und mit `pipefail` gilt die ganze Pipeline als
# gescheitert — die Warnung erschien dann, obwohl der Skill geladen war.
skill_liste="$(hermes skills list 2>/dev/null || true)"
if ! grep -q 'cae-orchestrator' <<<"$skill_liste"; then
    warn "Der Skill cae-orchestrator ist nicht sichtbar — einmalig freigeben:"
    warn "    hermes skills trust $ROOT"
fi

if [ "$NUR_VORB" -eq 1 ]; then
    echo
    ok "Vorbereitet. Aufruf waere: hermes --model $MODEL ${ARGS[*]-}"
    exit 0
fi

echo
exec hermes --model "$MODEL" ${ARGS[@]+"${ARGS[@]}"}
