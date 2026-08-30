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
| `routes [--grep x]` | alle Serverrouten auflisten |
| `rotor-check` | Rotorlayout **lokal** prüfen: Taschenkollision, Stegbreite, Einschluss im Blechpaket. Millisekunden, ohne CAD, ohne Server |
| `screen` | **Bauformen vorauswählen**, bevor eine teuer gerechnet wird: Polzahl, Nutzahl, Magnetanordnung, Leiter je Nut. 384 Konfigurationen in ~20 s, rein analytisch. Erkennt aus `--auftrag` das Ziel (günstig / Leistung) |
| `struktur` | Rotor-Festigkeit auf dem **eigenen Rechensatz**, ohne FreeCAD. `--solver ccx` (Polsektor, ~2 s) · `--solver z88` · `--solver beide` (Vollrotor, ~7 s, mit Gegenüberstellung) |
| `topopt` | Topologieoptimierung des Rotorblechs. `--verfahren sko` (Vorgabe) oder `simp`. 20–60 s. Ergebnis ist ein **Dichtefeld, kein Bauteil** |
| `db <was>` | **Rechnungsdatenbank**: `import` · `liste` · `zeige --lauf X` · `guete --lauf X` · `vergleich`. Kennwerte **mit Herkunft je Größe** |
| `lernen <was>` | **was aus dem eigenen Bestand folgt**: `zeige` · `merke --regel … --beleg …` · `pruefe` |
| `recherche <was>` | **Internet**: `suche <begriffe>` · `hole <adresse>` |
| `raw GET/POST <pfad>` | beliebige Route — Notausgang für alles Übrige |

### `struktur` und `topopt` — wann welches

Beide rechnen **lokal**, ohne den Server und ohne FreeCAD; sie bauen das Netz selbst
(Gmsh) aus derselben Magnetgeometrie, aus der auch das 2D-Feld kommt.

```bash
python3 cae_cli.py struktur --from-project last --solver ccx            # ~2 s
python3 cae_cli.py struktur --from-project last --solver beide --voll   # ~7 s
python3 cae_cli.py topopt   --from-project last --iterationen 25        # ~20 s
```

* **`--solver beide`** rechnet dasselbe Netz zweimal, mit CalculiX und mit Z88Aurora,
  und stellt die Zahlen samt der analytischen Ringformel gegenüber. Gemessene
  Abweichung an der Beispielmaschine: **unter 0,1 %**. Wer gefragt wird, was das
  belegt, sagt: es prüft **Löser und Rechensatz**, nicht das Netz und nicht das
  Modell. Ein Netz, das beide gleich falsch sehen, sehen beide gleich falsch.
* **Z88 kann keinen Polsektor** — es kennt weder zyklische Symmetrie noch schiefe
  Symmetrieebenen. Bei `--solver z88` und `beide` deshalb `--voll` angeben.
* **`topopt` liefert ein Dichtefeld, kein Bauteil.** Die `ableseempfehlung` im
  Ergebnis nennt den Radialbereich, in dem das Eisen mechanisch wenig trägt. Das ist
  ein Hinweis, wo eine Flussbarriere vertretbar *wäre* — **nach** einer EM-Rechnung,
  nicht davor. Wer daraus eine Geometrieempfehlung macht, sagt das dazu.

### Zuerst nachsehen, was schon bekannt ist

```bash
python3 cae_cli.py lernen zeige      # gemessene Regeln + belegte Erfahrungen
python3 cae_cli.py db liste          # welche Laeufe es gibt
python3 cae_cli.py db guete --lauf last
```

`lernen zeige` zählt aus den vorhandenen Läufen aus, was tatsächlich funktioniert hat —
etwa bei welcher Netzweite die Struktur-FEM Werte geliefert hat. **Vor der Wahl einer
Einstellung dort nachsehen**, statt sie zu raten.

Wer etwas Überraschendes herausfindet, legt es ab — **mit Beleg**:

```bash
python3 cae_cli.py lernen merke \
  --regel "struct_mesh_mm=2 laeuft hier in die Zeitueberschreitung" \
  --beleg "3 Laeufe 20260827_*: solver_status FAILED; Kontrolllauf bei 3 mm 414 s"
```

Ohne Beleg wird die Notiz abgewiesen (Exit 2). Eine Regel ohne Beleg ist ein Gerücht
mit Zeitstempel — und das nächste Modell liest sie als Tatsache.

### Herkunft: welche Zahl von welchem Verfahren

`db zeige` und `db vergleich` geben je Kennwert das Verfahren mit: `analytisch`,
`fdm2d`, `fem3d`, `lptn`, `zyklus`, `geometrisch`, `tabelle`, `abgeleitet`. Das ist
nicht Zierde — `B_gap_T` kommt aus der **analytischen** Luftspaltformel, `T_maxwell_Nm`
dagegen aus dem **gelösten FDM-Feld**. Beide stehen im selben Kennwertsatz nebeneinander
und wären ohne diese Spalte nicht zu unterscheiden.

Besonders zu beachten: **`structural_basis`** sagt, ob die Festigkeitsaussage auf einer
FEM-Rechnung beruht (`fem`) oder nur auf der Ringformel (`analytisch`), weil die FEM
nichts geliefert hat. Ein grünes `structural_ok` allein sagt das nicht.

### Internetrecherche

```bash
python3 cae_cli.py recherche suche "IPM Rotor Stegbreite Auslegung" --treffer 5
python3 cae_cli.py recherche hole https://…
```

Beides liefert **Fremdtext**, der als solcher markiert ist. Er darf **nie** eine
gerechnete Zahl ersetzen und gehört in einen Bericht nur **mit Quellenangabe**. Wer
eine Behauptung aus dem Netz übernimmt, sagt dazu, dass sie von dort stammt — dieselbe
Regel wie bei „diese Zahl ist analytisch, nicht gerechnet".

**Was wesentlich ist, unter dem Projekt ablegen** — dann steht es später im Bericht:

```bash
python3 cae_cli.py recherche merke --projekt last \
  --adresse https://… \
  --notiz "wofuer herangezogen" \
  --bild https://…/abbildung.png \
  --wert "stegbreite_mm=1.8 mm :: Typische Stegbreiten liegen bei IPM-Rotoren zwischen 1,5 und 2,0 mm."
python3 cae_cli.py recherche quellen --projekt last
```

Das legt Text und Bilder unter `<projekt>/recherche/` ab und schreibt die genannten
Werte in die Datenbank — **in die Tabelle `referenzwerte`, nicht zu den gerechneten
Kennwerten.** Ein recherchierter Wert kann richtig sein, ist aber nicht nachgerechnet;
`db vergleich` und die Kennwerttabelle finden ihn deshalb nicht.

Zwei Pflichten, sonst wird abgewiesen:

* **`--wert` braucht die Belegstelle** nach `::`. Eine Zahl ohne Zitat ist von einer
  erfundenen nicht zu unterscheiden.
* **Zahlen niemals selbst aus dem Fließtext klauben.** Nur übernehmen, was man
  wörtlich zitieren kann. Ein Regelausdruck über Fließtext verwechselt früher oder
  später eine Seitenzahl mit einer Stegbreite, und es fällt niemandem auf, weil das
  Ergebnis plausibel aussieht.

Heruntergeladene **Abbildungen bleiben fremdes Werk** — die Quelladresse wird
mitgespeichert und im Bericht genannt; die Rechtelage vor einer Weitergabe klären.

## Ergebnisse lesen — die wichtigste Regel

`results.json` ist mehrere MB groß und enthält eingebettete PNGs. **Nie ohne
Abschnitt abrufen.** Erst die Abschnitte zeigen, dann gezielt eintauchen:

```bash
python3 cae_cli.py results --sections --project last          # welche Abschnitte gibt es?
python3 cae_cli.py results summary --project last
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

### Ganz am Anfang: `screen`

**Fang nicht beim letzten Stand an.** `--from-project last` ist bequem und führt in einen
engen Pfad: Polzahl, Nutzahl und Magnetanordnung des ersten Entwurfs bleiben stehen,
obwohl gerade sie die Maschine prägen. Wenn eine **neue** Auslegung ansteht, spiel sie
zuerst durch:

```bash
python3 cae_cli.py screen --from-project last --auftrag "<der Auslegungsauftrag>"
python3 cae_cli.py screen --from-project last --ziel leistung \
        --pole 3,4,5 --nuten 36,48 --formen v,vasym,spoke --leiter 4,6
```

Das kostet ~20 s gegen 30 min bis 4 h für einen vollen Lauf.

**Übernimm NICHT von Hand.** Unter der Rangliste steht ein fertiger Befehl — benutze
genau den. Der Grund steht in Spalte `Mag`: passt eine Bauform nicht in den Pol,
verkleinert die Vorauswahl den Magneten, und dann gehören `magWidth`, `magThick` und
`magDist` **zur Empfehlung dazu**. Wer nur `p`, `slots` und `magShape` überträgt, baut eine
andere Maschine, und `rotor-check` lehnt sie zu Recht ab.

Das ist kein theoretisches Risiko: genau so ist es passiert. Ein Lauf empfahl p=5 mit
V-Anordnung, prüfte mit `rotor-check --set p=5 --set magShape=v` nach, bekam „Kollision,
Überlappung 6,20 mm" und meldete dem Nutzer, die eigene Empfehlung sei unbaubar. Sie war
baubar — mit `magWidth` 21,8 statt 32, `magThick` 4,09 statt 6 und `magDist` 6,48 statt
13,5.

Mit `--json` kommt die eingepasste Geometrie je Zeile mit, wenn du selbst auswählen
willst statt Platz 1 zu nehmen.

**Drei Dinge, die du dabei nicht verwechseln darfst:**

1. Die Vorauswahl ist **analytisch**. Ihre Kennwerte tragen die Herkunft `analytisch` und
   sind kein Ersatz für Feldlauf oder FEM. Sie sortiert aus und rangiert — sie entscheidet
   nichts.
2. `Kt` und `B_gap` hängen auf dieser Stufe **nicht** von Nutzahl und Leiterzahl ab (die
   analytische Formel kennt beide nicht). Die Nutzahl wird über das kgV aus Nut- und
   Polzahl (Rundlauf) und den Fertigungsaufwand bewertet. Wer sie elektromagnetisch
   beurteilen will, braucht den Feldlauf.
3. Passt eine Bauform nicht in den Pol, wird der Magnet **verkleinert** — Spalte `Mag`
   (im JSON `s_koerper`). Ein Wert von 0,64 heißt: diese Variante ist nur mit einem um gut
   ein Drittel kleineren Magneten baubar. Nenne das, wenn du sie empfiehlst, und nimm die
   Maße aus dem Übernahmebefehl mit.
4. `--polpaare` nimmt **Polpaare p**, die Rangliste zeigt daneben die **Polzahl 2p**.
   `--polpaare 2,3` ergibt also Maschinen mit 4 und 6 Polen — das ist kein Fehler.

### Vor `run cad`: `rotor-check`

Die teure Schleife ist „Geometrie ändern → 40 s FreeCAD → Fehler". `rotor-check`
rechnet dieselbe Frage in Millisekunden vor, rein zweidimensional und **ohne den
Server**:

```bash
python3 cae_cli.py rotor-check --from-project last
python3 cae_cli.py rotor-check --from-project last --set magLayerGap=4 --set magDist=6
python3 cae_cli.py rotor-check --payload-file entwurf.json --web 2.5
```

Geprüft wird dreierlei: überschneiden sich Magnettaschen, bleibt zwischen ihnen der
Mindeststeg (Vorgabe `ema_topology.BRIDGE_MM` = 2 mm, überschreibbar mit `--web`),
und liegt jede Tasche vollständig zwischen Wellenbohrung und Rotorrand. Exit **0**
heißt bestanden, **1** heißt abgelehnt — mit Begründung je Fund.

Zwei Dinge, die dabei zu wissen sind:

* **`--set` braucht doch den Server**, weil die Zuweisung gegen `/param_schema`
  geprüft wird. Ohne `--set` läuft das Verb vollständig lokal.
* **Es prüft nicht alles.** Wuchtbohrungen und Flussbarrieren sind noch nicht
  abgedeckt; ein bestandener `rotor-check` schließt einen Durchbruch dort nicht aus.
  Dieselbe Prüfung läuft ohnehin als Tor in `run cad` und `run analyse` — das Verb
  nimmt sie nur vor.

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

**Manche Routen arbeiten auf dem Serverzustand, nicht auf einer Projektkennung** — `/chat`
gehört dazu und antwortet ohne geladenes Projekt mit
`"Kein Projekt geladen — erst eine Analyse ausführen oder ein Projekt laden"`. Das ist
keine Störung, sondern die Vorbedingung: erst `run analyse --wait` oder ein Laden über die
Oberfläche. Für Zahlen aus einem beliebigen Projekt ist ohnehin
`results <abschnitt> --project <id>` der direkte Weg — ohne Umweg über ein Sprachmodell.

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
