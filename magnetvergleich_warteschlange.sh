#!/usr/bin/env bash
# Magnetanordnungs-Vergleich: A/B/C nacheinander, jeweils nachdem die
# Pipeline frei ist. Basis: StadtLand_1t-Konfiguration (p=3, 54 Nuten, v).
set -u
cd /home/cae/ai-workspace/cae_orchestrator || exit 1
CLI=(python3 cae_cli.py)
BASE_ID=20260830_164541_StadtLand_1t_Kosten

log(){ echo "[$(date '+%F %T')] $*"; }

# --- Phase 0: laufender Rechenlauf muss fertig werden --------------------------
log "Phase 0: warte auf den laufenden Rechenlauf (StadtLand_1t, Stand 42 %) ..."
i=0
while :; do
  st=$("${CLI[@]}" status 2>/dev/null | grep -m1 'Zustand')
  if [ -n "$st" ] && ! printf '%s' "$st" | grep -qi running; then
    log "Pipeline frei: $st"; break
  fi
  i=$((i+1)); sleep 30
  if [ $i -ge 840 ]; then log "FEHLER: nach ~7 h keine freie Pipeline — Abbruch"; exit 1; fi
done

# Basis-Auslegung: der StadtLand-Lauf, falls er abgeschlossen ist
if [ -f "$HOME/cae_projekte/$BASE_ID/meta.json" ]; then
  BASE=$BASE_ID
else
  BASE=last
  log "WARNUNG: $BASE_ID hat kein meta.json (Lauf nicht abgeschlossen?) — nutze --from-project last"
fi
log "Basis-Auslegung: $BASE"

# --- Varianten: name|magShape --------------------------------------------------
VARIANTEN=(
  "MVG_A_3p36Nuten_V|v"
  "MVG_B_3p36Nuten_U|u"
  "MVG_C_3p36Nuten_Spoken|spoke"
)

rc_tot=0
for v in "${VARIANTEN[@]}"; do
  NAME=${v%%|*}; MAG=${v##*|}
  log "=== Variante $NAME (p=3, 36 Nuten, magShape=$MAG) ==="

  # 1) Bauzaehigkeits-Gate (lokal, ms)
  if ! "${CLI[@]}" rotor-check --from-project "$BASE" \
        --set p=3 --set slots=36 --set magShape="$MAG" >/dev/null 2>&1; then
    log "ABGEBROCHEN: rotor-check lehnt $NAME ab — naechste Variante"
    rc_tot=$((rc_tot+1)); continue
  fi

  # 2) Geometrie (FreeCAD) — scheitert hier, geht der Analyselauf nicht an
  if ! "${CLI[@]}" run cad --from-project "$BASE" \
        --set p=3 --set slots=36 --set magShape="$MAG" \
        --set project_name="$NAME" --wait --timeout 18000; then
    log "ABGEBROCHEN: run cad fehlerhaft fuer $NAME (Exit != 0) — naechste Variante"
    rc_tot=$rc_tot+1; continue
  fi

  # 3) Volle Pipeline (Feld/FEM/Thermik/Zyklus/Bericht)
  if "${CLI[@]}" run analyse --from-project last --wait --timeout 18000; then
    log "FERTIG: $NAME"
  else
    log "FEHLER: analyse $NAME nicht zu Ende gebracht — naechste Variante"
    rc_tot=$((rc_tot+1))
  fi
done
log "Warteschlange beendet, $rc_tot Varianten mit Fehlern."
exit 0
