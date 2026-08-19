---
name: cae-orchestrator
description: Bedient die CAE-Toolchain für E-Maschinen (Geometrie, 2D-Feld, 3D-Elmer, Struktur-FEM, Thermik, Kühlung, Bericht) über cae_orchestrator/cae_cli.py. Verwenden, wenn nach Motorauslegung, Flussdichte, Moment, Wicklung, Magnettaschen, Rotorfestigkeit, Ölkühlung, einem Rechenlauf, einem Projektergebnis oder einem CAE-Bericht gefragt wird.
---

# CAE-Orchestrator bedienen

Rechnet IPM-E-Maschinen: Geometrie (FreeCAD) → EM-Feld 2D/3D (FDM/Elmer) →
Struktur-FEM (CalculiX) → Thermik → Fahrzyklus → PDF-Bericht.

**Alles läuft über ein CLI, nicht über HTTP von Hand:**

```bash
cd ~/ai-workspace/cae_orchestrator
python3 cae_cli.py <verb> ...
```

## Zuerst immer

```bash
python3 cae_cli.py health
```

Exit-Code 3 heißt: Server läuft nicht. Dann starten und **10 s warten**:

```bash
cd ~/ai-workspace/cae_orchestrator && ./start.sh
```

Exit-Codes durchgängig: `0` ok · `1` Fehler der Gegenstelle · `2` Bedienfehler ·
`3` Server aus · `4` Zeitüberschreitung. Am Code entscheiden, nicht am Text.

## Verben

| Verb | Zweck |
|---|---|
| `health` | Erreichbarkeit, Pipeline-Zustand, Projektanzahl |
| `status` | Fortschritt + letzte Logzeilen des laufenden Vorgangs |
| `geom [name]` | Parameterschema: Namen, Grenzen, Vorgaben. `geom mag` filtert |
| `projects` | gespeicherte Projekte (Ordner unter `~/cae_projekte`) |
| `results [pfad]` | Ergebnisse lesen — **immer mit Abschnitt** |
| `run <stufe>` | Rechnung starten |
| `wait` | auf Abschluss warten |
| `routes [--grep x]` | alle 135 Serverrouten auflisten |
| `raw GET/POST <pfad>` | beliebige Route — Notausgang für alles Übrige |

## Ergebnisse lesen — die wichtigste Regel

`results.json` ist mehrere MB groß und enthält eingebettete PNGs. **Nie ohne
Abschnitt abrufen.** Erst die Abschnitte zeigen, dann gezielt eintauchen:

```bash
python3 cae_cli.py results --sections --project 20260813_140556_...
python3 cae_cli.py results em.performance --project 20260813_140556_...
```

Das CLI entfernt Base64-Daten selbstständig und kürzt bei 12 000 Zeichen
(`--full` hebt nur die Kürzung auf). Punktpfade gehen beliebig tief:
`em3d.compare_2d`, `thermal.T_magnet_C`, `structural_fem`.

## Rechenläufe starten

Ein Lauf braucht einen Payload mit rund 90 Schlüsseln. **Nie von Hand schreiben** —
eine bestehende Auslegung übernehmen und mit `--set` nur ändern, was gefragt ist:

```bash
python3 cae_cli.py run analyse --from-project last --wait          # unverändert nachrechnen
python3 cae_cli.py run cad     --from-project last --dry-run \
        --set slotDepth=30 --set p=8 --set magShape=v              # erst zeigen …
python3 cae_cli.py run cad     --from-project last --wait \
        --set slotDepth=30 --set p=8 --set project_name=Variante_A #  … dann bauen
```

* `--from-project last` nimmt die jüngste **gerechnete** Auslegung (die mit `meta.json`).
* `--set KEY=WERT`, beliebig oft. Der Wert wird als JSON gelesen — `12`, `1.5`, `true`,
  `[1,2]` bleiben Typen, alles Übrige ist Text (`magShape=v` ohne Anführungszeichen).
* Wohin der Wert gehört, entscheidet `cae_cli.py` selbst (`geom` oder obere Ebene).
  Verschachteltes per Punktpfad: `--set vehicle.mass_kg=1750`.
* **Ein unbekannter Name wird abgewiesen**, mit Vorschlag bei Tippfehlern. Ein Name,
  der nicht durchkommt, ist nicht gesetzt worden — nie so tun, als sei er es.
* Grenzverletzungen werden **abgewiesen, nicht geklemmt** (Exit-Code 2, nichts gestartet).
  `--force` hebt die Prüfung auf, `--dry-run` baut den Payload und zeigt ihn, ohne
  irgendetwas zu starten.
* Immer `--set project_name=…` mitgeben, wenn eine Variante entsteht — sonst trägt sie
  den Namen der Vorlage.

**Was `--set` kennt: 26 Hauptparameter + 22 Feinparameter.** Die Feinparameter sind die
Stellschrauben unterhalb der Grundgeometrie — Wicklung (`conductorsPerSlot`,
`slotWidthRatio`), Magnetlagen und Polkontur (`magLayers`, `magLayerGap`, `poleArcFrac`,
`segPerPole`, `magAngle2`, `magAsym`, `magTangLen`, `magGapMm`, `magOrient`), Magnettasche
(`pocketMode`, `pocketOuterD`, `pocketInnerD`), Flusssperren (`genFluxBarrierD/Q`,
`fluxBarrierDepth`, `fluxBarrierWidth`) und Wuchtbohrungen (`genBalanceBolts`,
`balanceBoltCircleD`, `balanceBoltOffsetDeg`, `balanceBoltThread`). Alle mit Grenzen,
Typ und Auswahlliste — `python3 cae_cli.py raw GET /param_schema` zeigt sie samt `desc`.

* **Viele Feinparameter gelten nur für bestimmte Topologien**, und das steht in ihrem
  `desc`: `poleArcFrac` nur `spm`/`halbach`, `magLayers` nur `pmasynrm`, `magAsym` nur
  `vasym`, `magAngle2` nur `vv`, `magTangLen` nur `u`/`delta`, `pocket*` nur `v`.
  Auf einer anderen Topologie wird der Wert **angenommen und tut nichts** — vor dem
  Setzen also `desc` lesen, sonst wird eine unveränderte Maschine als geändert gemeldet.
* Schalter sind **echte Booleans**: `--set genFluxBarrierQ=true`. `1`, `0` oder `ja`
  werden abgewiesen (die Pipeline prüft mit `bool(...)`, wo jeder Text wahr wäre).

**Nicht im Schema, aber im Payload:** reine CAD-Schalter (`genBearingA`, `splineTeeth`,
`windingHeadStyle` …). Die gehen weiterhin durch, wenn sie in der Vorlage stehen — aber
ohne Grenzen und ohne Typprüfung. Was das Feld beeinflusst, steht im Schema.

**Die Grenzen aus `geom` sagen NICHT, ob eine Geometrie baubar ist.** Sie sind die
Suchbox des Optimierers und weit größer als das Baubare (gemessen: blind gezogen sind
nur ~4 % baubar; `slotDepth` erlaubt 60 mm bei ~44 mm Statorwand). Nach jeder
Geometrieänderung deshalb **zuerst `run cad --wait`** (~1 min) — schlägt der fehl,
lohnt der Analyselauf über Stunden nicht.

| Stufe | Was | Dauer | Voraussetzung |
|---|---|---|---|
| `cad` | nur Geometrie bauen | ~1 min | FreeCAD (pixi) |
| `analyse` | volle Pipeline inkl. Bericht | **30 min–4 h** | FreeCAD + CalculiX |
| `em3d` | 3D-Feld | 5–30 min | Elmer |
| `em3d_sweep` | 3D über Betriebspunkte | Stunden | Elmer |
| `cfd` | Kühlung (OpenFOAM) | **Stunden** | OpenFOAM v2406 |
| `oilspray` | Ölnebel (Blender/Mantaflow) | 10–60 min | Blender |
| `smoke` | Selbsttest | ~15 s | — |

`--wait` blockiert bis zum Ende (Vorgabe 7200 s). **Ohne `--wait` läuft der Lauf
serverseitig weiter** — der Startaufruf nennt dann die Statusroute zum Wiederanhängen
(`wait --status-path …`). Jede Stufe hat ihre eigene; `status` allein zeigt nur die
volle Pipeline, bei einem CAD- oder 3D-Lauf steht dort weiter `idle`. Nur EINE
Pipeline gleichzeitig; ein zweiter Start gibt HTTP 409.

Bei langen Läufen nicht in einer engen Schleife pollen — `wait` macht das mit
5 s Abstand selbst.

## Alles Übrige

Die 135 Routen sind über `raw` erreichbar; `routes --grep` findet sie.

```bash
python3 cae_cli.py routes --grep oilspray
python3 cae_cli.py raw GET /project/20260813_140556_.../oilspray
python3 cae_cli.py raw POST /chat --data '{"message":"Wie hoch ist das Moment?"}'
```

Referenz mit allen Routen nach Themen: `references/routes.md`.

## Was NICHT zu tun ist

* **Keine Zahl erfinden.** Kommt eine Größe nicht aus `results`, dann sagen, dass
  sie nicht gerechnet wurde.
* **`/opt/freecad-1.1` nie benutzen** — das ist in Wahrheit 1.2 mit einem
  Darstellungsfehler.
* **Nie `pixi self-update`** — 0.68+ zerstört die schreibgeschützte FreeCAD-Umgebung.
* Nichts im Repo redet über `localhost` hinaus. Keine Gegenstelle außerhalb setzen.
* Läufe nicht abbrechen, ohne zu fragen — manche kosten Stunden.
* Keinen Payload von Hand zusammensetzen und keinen abgewiesenen `--set` als gesetzt
  ausgeben. Wenn ein Parameter fehlt: `geom <text>` fragen, nicht raten.

## Zahlen, die man kennen sollte

Diese Toolchain kalibriert das FDM-Feld auf eine **analytische** Luftspaltformel;
`Kt`, `B_gap` und die Eisenverluste kommen aus dieser Formel, nicht aus dem
Feldbild. Das Feldbild ist Anschauung. Wer nach der Herkunft einer Zahl gefragt
wird, sagt das dazu.
