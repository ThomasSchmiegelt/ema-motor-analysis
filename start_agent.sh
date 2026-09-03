#!/bin/bash
# Startet die gesamte Kette und haengt eine PI-Sitzung mit dem LOKALEN Modell an.
#
#   ./start_agent.sh                      interaktive Sitzung
#   ./start_agent.sh -p "Wie viele …"     eine Frage, dann Ende
#   ./start_agent.sh --kein-browser       Server ohne Browserfenster starten
#   ./start_agent.sh --nur-server         nur den Orchestrator, kein PI
#   ./start_agent.sh --weiter             letzte Sitzung dieses Verzeichnisses fortsetzen
#   ./start_agent.sh --sitzung <id>       eine bestimmte Sitzung fortsetzen (Teil-UUID reicht)
#   ./start_agent.sh <id>                 dasselbe — eine nackte, bekannte Kennung genuegt
#   ./start_agent.sh --sitzungen          die letzten Sitzungen auflisten und beenden
#
# Alles Weitere wird unveraendert an `pi` durchgereicht (z. B. --model).
set -euo pipefail

MODEL="qwen-gross:latest"
MODEL_ID="ca8ec377441f"          # aus `ollama list` — pinnt das Modell, nicht nur den Namen
# 02.09.2026 nachgezogen: qwen-gross wurde auf qwen3.8:27b-mtp-q4_K_M neu gebaut
# (identische Blobs, nur num_ctx 65536 ergaenzt). Der Wechsel ist geprueft und
# gewollt: MTP-Spekulativdekodierung, warm gemessen 93,1 statt 86,7 tok/s bei
# 65536 Kontext, und jetzt 100 % GPU statt 94 %. Vorher: 6b9d840acbf5.
PORT=5000
OLLAMA_URL="http://localhost:11434"

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH="$ROOT/cae_orchestrator"
LOG="${TMPDIR:-/tmp}/cae_server_$USER.log"

export PATH="$HOME/.npm-global/bin:$PATH"   # pi liegt hier, weil ohne sudo installiert

BROWSER=1; NUR_SERVER=0; WEITER=0; LISTE=0; SITZUNG=""; ARGS=()
erwarte_id=""
for a in "$@"; do
    if [ -n "$erwarte_id" ]; then SITZUNG="$a"; erwarte_id=""; continue; fi
    case "$a" in
        --kein-browser) BROWSER=0 ;;
        --nur-server)   NUR_SERVER=1 ;;
        --weiter)       WEITER=1 ;;
        --sitzungen)    LISTE=1 ;;
        --sitzung)      erwarte_id=1 ;;
        --sitzung=*)    SITZUNG="${a#--sitzung=}" ;;
        --)             ;;   # ueblicher Trenner "ab hier keine eigenen Optionen mehr".
                             # NICHT weiterreichen: `pi` kennt ihn nicht und bricht mit
                             # "Unknown option: --" ab, nachdem alles andere schon lief.
        *)              ARGS+=("$a") ;;
    esac
done
[ -n "$erwarte_id" ] && { echo "FEHLER: --sitzung braucht eine Kennung (--sitzungen zeigt sie)" >&2; exit 1; }

# ── Sitzungen dieses Verzeichnisses ─────────────────────────────────────────
# PI legt sie unter ~/.pi/agent/sessions/<kodiertes cwd>/ ab. Wie das cwd kodiert
# wird, ist nirgends zugesagt; die ERSTE Zeile jeder Datei traegt es aber im Klartext.
# Danach wird gefiltert, statt den Verzeichnisnamen aus dem Pfad zu raten.
sitzungen() {           # $1 = Anzahl; Ausgabe je Zeile: id <TAB> Zeitpunkt <TAB> erste Frage
    python3 - "$HOME/.pi/agent/sessions" "$ROOT" "${1:-1}" 2>/dev/null <<'PYSESS'
import glob, json, os, sys
basis, cwd, n = sys.argv[1], sys.argv[2], int(sys.argv[3])
treffer = []
for f in glob.glob(os.path.join(basis, "*", "*.jsonl")):
    try:
        with open(f, encoding="utf-8") as fh:
            kopf = json.loads(fh.readline())
            if kopf.get("type") != "session" or kopf.get("cwd") != cwd:
                continue
            titel = ""
            for zeile in fh:
                try:
                    d = json.loads(zeile)
                except ValueError:
                    continue
                m = d.get("message")
                if d.get("type") == "message" and isinstance(m, dict) and m.get("role") == "user":
                    for c in m.get("content") or []:
                        if isinstance(c, dict) and c.get("type") == "text":
                            titel = " ".join(str(c.get("text", "")).split())[:64]
                            break
                if titel:
                    break
    except (OSError, ValueError, KeyError):
        continue
    treffer.append((os.path.getmtime(f), kopf["id"],
                    kopf.get("timestamp", "")[:16].replace("T", " "), titel))
for _, sid, ts, titel in sorted(treffer, reverse=True)[:n]:
    print(f"{sid}\t{ts}\t{titel}")
PYSESS
}

if [ "$LISTE" -eq 1 ]; then
    aus="$(sitzungen 15)"
    [ -n "$aus" ] || { echo "Noch keine PI-Sitzung in $ROOT."; exit 0; }
    echo "Sitzungen in $ROOT (neueste zuerst):"
    echo ""
    printf '%s\n' "$aus" | while IFS=$'\t' read -r sid ts titel; do
        printf '  %s  %s  %s\n' "$sid" "$ts" "$titel"
    done
    echo ""
    echo "Fortsetzen: ./start_agent.sh --sitzung <id>   |   letzte: ./start_agent.sh --weiter"
    exit 0
fi

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
# Aus dem Wurzelverzeichnis, sonst findet PI weder AGENTS.md noch .agents/skills/ —
# und --continue griffe in die falsche Ablage, denn PI sortiert Sitzungen nach cwd.
cd "$ROOT"

# ── Projektkontext: ERZEUGT, nicht kopiert ──────────────────────────────────
# Dieselbe Datei, die start_hermes.sh schreibt, mit demselben Erzeuger — damit
# beide Agentenkoepfe denselben Projektstand sehen. AGENTS.md bleibt die eine,
# unveraenderte Regelquelle; kopiert wird sie NICHT (eine Kopie laeuft still
# auseinander, und dann arbeiten zwei Agenten nach zwei Regelwerken).
#
# PI bekommt KEINE projekteigene Sitzungsablage: PI sortiert Sitzungen nach cwd,
# und das cwd muss die Repo-Wurzel bleiben — sonst findet PI weder AGENTS.md noch
# .agents/skills/. Das ist der Unterschied zu Hermes, wo HERMES_HOME die Ablage
# verschieben kann, ohne das Arbeitsverzeichnis anzufassen.
PROJ_DIR="$(ls -d "$HOME/cae_projekte"/2* 2>/dev/null | sort | tail -1)"
# Die Projektakte wird IMMER neu geschrieben -- auch ohne Projektbindung.
#
# Vorher stand hier ein `if [ -n "$PROJ_DIR" ]` um den ganzen Block: wer
# ausdruecklich OHNE Projekt startete, um etwas Neues zu entwerfen, bekam die
# Akte des vorigen Laufs stehen -- ueberschrieben mit "Aktuelles Projekt" und
# vom Modell zu Recht geglaubt. Gemessen lag am 03.09. ein Flugzeugantrieb vom
# 02.09. darin. Eine falsche Akte ist schlimmer als keine.
{
    echo "# Aktuelles Projekt — ERZEUGT beim Agentenstart, nicht von Hand aendern"
    echo
    echo "Diese Datei wird bei JEDEM Agentenstart neu geschrieben — auch wenn kein"
    echo "Projekt gebunden ist. Die Regeln stehen in AGENTS.md; hier stehen nur die"
    echo "Fakten des Laufs, der gerade beginnt."
    echo
    echo "- Stand: $(date '+%d.%m.%Y %H:%M')"
    echo "- Agentenkopf: PI im Terminal (start_agent.sh)"
    if [ -n "$PROJ_DIR" ] && [ -d "$PROJ_DIR" ]; then
        echo "- Kennung: \`$(basename "$PROJ_DIR")\`"
        echo "- Verzeichnis: \`$PROJ_DIR\`"
        echo
        echo "Das gebundene Projekt ist der ABLAGEORT dieses Laufs, **keine** Vorlage:"
        echo "Polzahl, Nutzahl, Magnetanordnung, Kuehlung und Werkstoffe werden nicht"
        echo "daraus uebernommen."
        echo
        if [ -f "$PROJ_DIR/results.json" ]; then
            echo "Bereits gerechnet (aus results.json):"
            "$ROOT/.agents/projektstand.py" "$PROJ_DIR/results.json" \
                2>/dev/null || echo "- (results.json nicht lesbar)"
        else
            echo "Noch nichts gerechnet — es gibt keine results.json."
        fi
    else
        echo "- Projekt: **keines gebunden**"
        echo
        echo "**Es gibt kein aktuelles Projekt.** Was in frueheren Laeufen entworfen"
        echo "wurde, ist fuer diese Aufgabe keine Vorgabe und keine Vorlage. Eine neue"
        echo "Auslegung beginnt mit"
        echo "\`python3 cae_orchestrator/cae_cli.py aufgabe \"<Aufgabe>\"\` und danach"
        echo "\`paarvergleich --frisch\` — NICHT mit \`--from-project last\`."
    fi
} > "$ROOT/AGENTS.projekt.md"

# Hat der Aufrufer PIs eigene Sitzungsflaggen benutzt, gilt seine Wahl unangetastet:
# nichts hinzufuegen, nichts herausloesen (sonst risse die Erkennung unten den Wert aus
# `--session <id>` heraus und `--session` verschluckte das naechste Argument), und auch
# keinen Hinweis auf die letzte Sitzung zeigen, der dann falsch waere.
eigene_wahl=0
# Eine Einmalfrage (-p) ist bereits die Entscheidung "eine Frage, dann Ende" — dort
# nach einer fortzusetzenden Sitzung zu fragen, wuerde einen Aufruf blockieren, der
# gerade NICHT auf eine Antwort warten soll.
EINMALFRAGE=0
for a in ${ARGS[@]+"${ARGS[@]}"}; do
    case "$a" in
        --session|--session=*|--session-id|--session-id=*|--continue|-c|--resume|-r|--fork|--fork=*|--no-session) eigene_wahl=1 ;;
        -p|--prompt|--prompt=*|-p*) EINMALFRAGE=1 ;;
    esac
done

# Eine nackte Sitzungskennung als Argument ist die naheliegende Eingabe — PI schreibt
# beim Beenden selbst "To resume this session: pi --session <uuid>", und der Griff
# danach landet leicht bei `./start_agent.sh -- <uuid>` oder `./start_agent.sh <uuid>`.
# Erkannt wird sie NICHT ueber ein Muster, sondern durch Abgleich mit den wirklich
# vorhandenen Sitzungen: was keine ist, geht unveraendert an `pi` weiter.
if [ -z "$SITZUNG" ] && [ "$WEITER" -eq 0 ] && [ "$eigene_wahl" -eq 0 ] \
   && [ "$NUR_SERVER" -eq 0 ] && [ ${#ARGS[@]} -gt 0 ]; then
    bekannte="$(sitzungen 999 | cut -f1)"
    rest=()
    for a in "${ARGS[@]}"; do
        if [ -z "$SITZUNG" ] && [ ${#a} -ge 8 ] && grep -qF -- "$a" <<<"$bekannte" 2>/dev/null; then
            SITZUNG="$a"
        else
            rest+=("$a")
        fi
    done
    [ -n "$SITZUNG" ] && ARGS=(${rest[@]+"${rest[@]}"})
fi

if [ -n "$SITZUNG" ]; then
    ARGS=(--session "$SITZUNG" ${ARGS[@]+"${ARGS[@]}"})
    echo "Setze Sitzung $SITZUNG fort."
elif [ "$eigene_wahl" -eq 1 ]; then
    :                       # PI entscheidet — nichts hinzufuegen, nichts anmerken
elif [ "$WEITER" -eq 1 ]; then
    letzte="$(sitzungen 1)"
    [ -n "$letzte" ] || die "Keine fortsetzbare Sitzung in $ROOT — dann einfach ohne --weiter starten."
    IFS=$'\t' read -r s_id s_zeit s_titel <<<"$letzte"
    ARGS=(--continue ${ARGS[@]+"${ARGS[@]}"})
    echo "Setze fort: $s_id  ($s_zeit)  $s_titel"
elif [ -t 0 ] && [ -t 1 ] && [ "$EINMALFRAGE" -eq 0 ]; then
    # Am Terminal wird GEFRAGT statt nur hingewiesen. Der Hinweis stand hier vorher
    # schon ("Fortsetzen mit: --weiter"), aber ein Hinweis am Ende einer Startausgabe
    # wird ueberlesen, und dann faengt jede Frage wieder bei null an, obwohl nebenan
    # die Sitzung mit dem ganzen Verlauf liegt.
    #
    # Die Vorgabe bleibt trotzdem NEU (Eingabetaste = neu): ein fortgesetzter Verlauf
    # schleppt den vorigen mit, und bei 64 k Kontext faellt das erst auf, wenn vorne
    # etwas herausfaellt. Automatisch fortsetzen waere darum falsch — fragen ist der
    # Mittelweg. Nicht gefragt wird ohne Terminal (Skriptaufruf) und nicht bei -p.
    liste="$(sitzungen 5)"
    if [ -z "$liste" ]; then
        # Sagen statt schweigen: ohne diese Zeile sieht ein leerer Sitzungsspeicher
        # genauso aus wie ein kaputtes Menue. Bei Hermes war das der Fall.
        echo
        echo "Noch keine PI-Sitzung in diesem Verzeichnis — es wird eine neue angelegt."
    else
        echo
        echo "Sitzungen in diesem Verzeichnis:"
        i=0; ids=()
        while IFS=$'\t' read -r s_id s_zeit s_titel; do
            i=$((i+1)); ids+=("$s_id")
            # `%-30.30s` kuerzt nach BYTES und zerschneidet dabei Umlaute mitten im
            # UTF-8-Zeichen ("e-maschine f<?>"). GNU `cut -c` hilft nicht, es ist
            # trotz des Namens ebenfalls bytebasiert; bashs Teilzeichenkette dagegen
            # zaehlt in einer UTF-8-Umgebung Zeichen.
            t="${s_titel:-—}"
            printf "  %d) %-30s  %s\n" "$i" "${t:0:30}" "$s_zeit"
        done <<< "$liste"
        echo "  n) neue Sitzung"
        read -r -p "Fortsetzen [1-$i] oder neu [n]? (Vorgabe: n) " wahl || wahl="n"
        case "$wahl" in
            ''|n|N|neu) ;;
            *) if [ "$wahl" -ge 1 ] 2>/dev/null && [ "$wahl" -le "$i" ]; then
                   ARGS=(--session "${ids[$((wahl-1))]}" ${ARGS[@]+"${ARGS[@]}"})
                   echo "Setze Sitzung ${ids[$((wahl-1))]} fort."
               else
                   warn "'$wahl' ist keine der angebotenen Sitzungen — neue Sitzung."
               fi ;;
        esac
    fi
else
    letzte="$(sitzungen 1)"
    if [ -n "$letzte" ]; then
        IFS=$'\t' read -r s_id s_zeit s_titel <<<"$letzte"
        warn "Letzte Sitzung: $s_id  ($s_zeit)  $s_titel"
        warn "Fortsetzen mit: ./start_agent.sh --weiter    (alle: --sitzungen)"
    fi
fi

echo ""
echo "=== PI mit $MODEL — Skill 'cae-orchestrator' geladen ==="
echo ""
exec pi --provider ollama --model "$MODEL" ${ARGS[@]+"${ARGS[@]}"}
