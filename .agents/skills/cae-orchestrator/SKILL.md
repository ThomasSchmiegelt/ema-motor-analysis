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

Ein Lauf braucht einen Payload. Der einfachste Weg ist, den eines bestehenden
Projekts zu übernehmen und nur zu ändern, was gefragt ist:

```bash
python3 cae_cli.py run analyse --from-project 20260813_140556_... --wait
```

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
serverseitig weiter** — mit `status` oder `wait` wieder anhängen. Nur EINE
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

## Zahlen, die man kennen sollte

Diese Toolchain kalibriert das FDM-Feld auf eine **analytische** Luftspaltformel;
`Kt`, `B_gap` und die Eisenverluste kommen aus dieser Formel, nicht aus dem
Feldbild. Das Feldbild ist Anschauung. Wer nach der Herkunft einer Zahl gefragt
wird, sagt das dazu.
