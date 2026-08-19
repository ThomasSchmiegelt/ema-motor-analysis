# AGENTS.md — Kontext für Agent-Harnesses (PI u. a.)

Monorepo einer CAE-Toolchain für E-Maschinen. Drei eigenständige Teilprojekte, die
über lokale HTTP-Dienste miteinander reden. Läuft unter dem eingeschränkten Nutzer
**`cae`** — **kein sudo**.

| Ordner | Was | Dienst |
|---|---|---|
| `cae_orchestrator/` | Browser-CAE für IPM-Motoren: Geometrie → EM-Feld → Struktur-FEM → Thermik → Fahrzyklus → PDF | `:5000` |
| `pikogk/` | PicoGK-Geometriekern + HTTP-API (Voxel/implizit, LLM-erzeugte „Skills") | `:5266` |
| `physics_surrogate/` | ML-Surrogat für die Löserstufen (PhysicsNeMo/Torch) | `:5300` |
| `connection_detection/` | FreeCAD-Workbench: Verbindungserkennung in STEP-Baugruppen | — (CLI) |
| `lego/` | LEGO-Technic-Mechaniken per LLM | — |

Ollama läuft auf `:11434`.

## Die wichtigste Regel

**Bediene den Orchestrator über sein CLI, nicht über HTTP von Hand.** Dafür gibt es
den Skill `cae-orchestrator` (`.agents/skills/cae-orchestrator/`). Er kennt die
Verben, die Laufzeiten, die Exit-Codes und die Fallen. `curl` gegen `:5000` ist der
Umweg, nicht die Abkürzung.

```bash
cd ~/ai-workspace/cae_orchestrator && python3 cae_cli.py health
```

## Harte Grenzen — nicht verhandelbar

* **Nichts hier redet über `localhost` hinaus.** Kein Auth, kein TLS, absichtlich
  (lokaler Machbarkeitsnachweis). Keine externe Gegenstelle einbauen.
* **`/opt/freecad-1.1` niemals benutzen** — das ist in Wahrheit 1.2 und hat einen
  Darstellungsfehler. Das richtige FreeCAD liegt unter `~/freecad_1.1_quellcode`
  (pixi), CalculiX (`ccx`) in derselben Umgebung.
* **Niemals `pixi self-update`** — pixi ist auf 0.67.0 festgenagelt, 0.68+ zerstört
  die schreibgeschützte FreeCAD-Umgebung.
* **`.gitignore` kennt keine Kommentare am Zeilenende** — ein `# …` hinter dem
  Muster wird Teil des Pfads und die Regel greift stillschweigend nicht mehr. So
  sind hier einmal 17 GB Datensatz beinahe in die Historie gerutscht.
* Laufzeitdaten (`~/cae_projekte`, `datasets/`, `checkpoints/`) werden **nie**
  versioniert.

## Rechenzeiten realistisch einschätzen

Eine volle Pipeline dauert **30 min bis 4 h**, ein OpenFOAM-Lauf **Stunden**. Läufe
laufen serverseitig weiter, wenn der Aufrufer weggeht. Nicht in engen Schleifen
pollen, nichts ungefragt abbrechen.

## Zahlen ehrlich zuordnen

Das 2D-FDM-Feld wird auf eine **analytische** Luftspaltformel kalibriert. `Kt`,
`B_gap` und die Eisenverluste kommen aus dieser Formel, nicht aus dem Feldbild; das
Feldbild ist Anschauung. Wer nach der Herkunft einer Zahl gefragt wird, sagt das
dazu. Kommt eine Größe nicht aus `results`, wurde sie nicht gerechnet — dann sagen,
nicht schätzen.

## Ausführliche Dokumentation

`CLAUDE.md` (Wurzel) für das Zusammenspiel, `cae_orchestrator/CLAUDE.md` für die
Pipeline im Detail (sehr ausführlich — dort nachsehen statt aus dem Quelltext
herzuleiten), `pikogk/EXPERIENCE_REPORT.md` für den Linux-Port,
`pikogk/INTEGRATION.md` für den HTTP-Vertrag.
