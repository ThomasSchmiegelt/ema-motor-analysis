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
| `steckbrief [id]` | **Was dieses Projekt IST und was daran gerechnet wurde** — Maschinenart, Pole/Nuten, Bauraum, Werkstoffe, Betriebspunkt, welche Stufen gelaufen sind, die Kennwerte **samt Herkunft**, und was offen ist. Rechnet nichts; was fehlt, steht als fehlend da. `--laeufe` listet zusätzlich die früheren Agentenläufe und die abgelegten Rechnungen |
| `welle` | **Vollwelle oder Hohlwelle — gemessen.** Rechnet EIN Feld und sagt, ob durch die Welle Fluss läuft und wie groß die Bohrung höchstens sein darf. Exit 0 = Hohlwelle möglich, 1 = Vollwelle nötig |
| `rotor-check` | Rotorlayout **lokal** prüfen: Taschenkollision, Stegbreite, Einschluss im Blechpaket. Millisekunden, ohne CAD, ohne Server |
| `paarvergleich` | **Die Gestaltungsentscheidungen gegenüberstellen — VOR der Geometrie.** Dreizehn Achsen (Magnetanordnung, **V-Öffnungswinkel**, Leiter je Nut, Magnet-/Blech-/Leiterwerkstoff, Kühlung, Wellenverbindung, Wuchtverschraubung, Flussbarrieren, Durchmesser, Länge, **Wellendurchmesser**), je Achse jede Option gegen jede. Sagt auch, **welche Entscheidung zuerst ansteht**. 0,7 s, rein analytisch. `--referenz` zeigt statt eines Vergleichs die **recherchierten Vergleichswerte** mit Quellen |
| `screen` | **Bauformen vorauswählen**, bevor eine teuer gerechnet wird: Polzahl, Nutzahl, Magnetanordnung, Leiter je Nut. 384 Konfigurationen in ~20 s, rein analytisch. Erkennt aus `--auftrag` das Ziel (günstig / Leistung) |
| `bilddaten <was>` | **Bilddatensatz zum optischen Bewerten**: `erzeugen` · `seite` · `einlesen` · `regel` · `stand`. Zieht zufaellige Rotorquerschnitte, behaelt nur die, die das Layouttor bestehen, und zeichnet sie. **Die Bewertung macht ein Mensch** — du kannst sie nur vorbereiten und hinterher auswerten |
| `feldbild` | **Magnetfeldlinien zum Ansehen** in den Projektordner legen: `linien` (Durchsicht) · `schnitt` (Stator ueber einen Sektor weggenommen) · `pol` (ein Polsektor gross) · `laengs` (Achsschnitt, gerechnetes Feld nur mit 3-D-Lauf). Durchsichtige PNG, ein FDM-Lauf, Sekunden bis Minuten — **kein** Pipelinelauf |
| `struktur` | Rotor-Festigkeit auf dem **eigenen Rechensatz**, ohne FreeCAD. `--solver ccx` (Polsektor, ~2 s) · `--solver z88` · `--solver beide` (Vollrotor, ~7 s, mit Gegenüberstellung) |
| `topopt` | Topologieoptimierung des Rotorblechs. `--verfahren sko` (Vorgabe) oder `simp`. 20–60 s. Ergebnis ist ein **Dichtefeld, kein Bauteil** |
| `db <was>` | **Rechnungsdatenbank**: `import` · `liste` · `zeige --lauf X` · `guete --lauf X` · `vergleich`. Kennwerte **mit Herkunft je Größe** |
| `lernen <was>` | **was aus dem eigenen Bestand folgt**: `zeige` · `merke --regel … --beleg …` · `pruefe` · **`probieren`** = geplanter Versuch: jede Bauform ueber jede Polzahl, mit `--merken` landen die Befunde als belegte Regeln im Speicher |
| `recherche <was>` | **Internet**: `suche <begriffe>` · `hole <adresse>` |
| `raw GET/POST <pfad>` | beliebige Route — Notausgang für alles Übrige |

**`--frisch` gegen `--from-project`** — gilt für `run`, `rotor-check`, `screen`, `paarvergleich`, `bilddaten`, `lernen`, `struktur`, `topopt`, `feldbild`:

* **`--frisch`** baut den Grundpayload aus den Schemavorgaben und passt ihn ein. Kein Altprojekt, keine geerbte Polzahl, Anordnung, Kühlung oder Werkstoffwahl. **Das ist der Start jeder neuen Auslegung.**
* **`--from-project <id>`** erbt ALLE Entscheidungen dieses Projekts. Richtig zum Nachrechnen, Verfeinern und für gezielte Einzeländerungen — sonst nicht.


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

### Bei einer NEUEN Aufgabe: erst zerlegen, dann suchen

```bash
python3 cae_cli.py aufgabe "Nabenmotor fuer ein Lastenrad, 28 Zoll, 140 kg, 27 Nm bei 210 U/min"
```

Das ist der Schritt **vor** jeder Recherche und vor jedem Rechenlauf. Ins Netz zu gehen
ist billig, aber ungezielt: wer nicht weiß, welche Angabe fehlt, sucht nach dem, was er
ohnehin schon hat. `aufgabe` stellt drei Dinge nebeneinander:

1. **Was feststehen muss**, bevor gerechnet wird — Einsatz, Betriebspunkt, Lastfall,
   Bauraum, Kühlung, Umgebung, Werkstoffe, Anordnung, Stromrichter, Sicherheit.
2. **Was der eigene Bestand schon hergibt** — abgelegte Fahrzyklen, gemessene Regeln und
   Erfahrungen, gerechnete Läufe, Treffer in der Wissensbasis.
3. **Was offen bleibt.** Genau das — und nur das — rechtfertigt eine Suche.

Drei Zustände, und sie bedeuten Verschiedenes:

* `ABLEITBAR` — das Werkzeug entscheidet es (Schema, `paarvergleich`). Nicht fragen.
* `PRUEFEN` — es gibt schon etwas Passendes im Bestand. **Ansehen, nicht neu erfinden.**
* `OFFEN` — fehlt. Zwei Wege, und sie sind nicht austauschbar:
  * **Was nur der Auftraggeber wissen kann** (Bauraum, geforderter Betriebspunkt,
    Einsatzzweck, Spannungsebene) wird **gefragt**, nicht recherchiert. Eine
    recherchierte Antwort auf eine Frage nach dem Bauraum ist geraten.
  * **Was allgemein bekannt ist** (typische Stegbreiten, übliche Pol-/Nutkombinationen,
    Werkstoffgrenzen) wird recherchiert — und mit Beleg abgelegt (unten).
* `FEST` — eine Annahme der Toolchain, die man nur **nennen** kann. Vor allem:
  **Zwischenkreis 800 V und Strangstromgrenze 800 A sind fest verdrahtet**
  (`ema_analysis.INVERTER_*`) und **nicht einstellbar**. Für ein 48-V-Fahrradsystem ist
  das falsch — das gehört in den Bericht, statt die Peak-Zahlen unkommentiert zu zitieren.

Erst danach recherchieren, und die Suche mit dem formulieren, was offen war — nicht mit
der Aufgabe als Ganzes.

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

* `--frisch` baut den Payload aus den Schemavorgaben — **kein Altprojekt**. Das ist der
  Start jeder neuen Auslegung; alles Weitere entscheidest du mit `paarvergleich`.
* `--from-project last` nimmt die jüngste **gerechnete** Auslegung (die mit `meta.json`)
  und erbt damit ALLE ihre Entscheidungen — nur zum Nachrechnen und Verfeinern.
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

### Noch davor: WELCHE MASCHINENART?

Das Werkzeug ist als **permanenterregte Synchronmaschine (PSM) mit Hairpins**
gewachsen. Die Vorgabe `geom.machineType = pmsm` ist deshalb keine Wahl, sondern eine
**Annahme** — und sie entscheidet über die Bedeutung fast aller übrigen Entscheidungen:
eine Maschine ohne Magnete hat keine Magnetanordnung, keinen Magnetwerkstoff, keinen
V-Öffnungswinkel, keine Entmagnetisierungsreserve und kein Kurzschlussmoment.

```bash
python3 cae_cli.py maschinenart          # alle Arten und wie weit jede getragen ist
python3 cae_cli.py maschinenart asm      # eine im Einzelnen
```

| Art | was | analytisch | Feld | CAD | 3-D |
|---|---|---|---|---|---|
| `pmsm` | permanenterregt (Vorgabe) | ✔ | ✔ | ✔ | ✔ |
| `asm` | Asynchron, Käfigläufer | ✔ | — | — | — |
| `synrm` | Reluktanz, ohne Magnete | — | — | — | — |
| `eesm` | fremderregt | — | — | — | — |

* **Setzen:** `--set geom.machineType=asm`.
* **Vergleichen:** `paarvergleich --achse maschinenart` stellt PSM und ASM am
  **gemeinsamen** Betriebspunkt gegeneinander — gleiche Kennzahlen, gleiche Einheiten.
  Nicht getragene Arten stehen als Zeile **mit Begründung** da, statt den Vergleich
  abzureißen.
* **Was `run analyse` mit `asm` macht: es bricht ab.** Das ist Absicht. Die 2-D-FDM
  dieses Werkzeugs ist reell, linear und magnetostatisch — sie kennt weder σ noch
  ∂A/∂t und kann einen Käfigläufer grundsätzlich nicht abbilden. Ein Durchlauf würde
  **PSM-Zahlen unter fremdem Namen** liefern: ein Feld aus Magneten, die es nicht gibt,
  ein Moment ohne Schlupf, eine Entmagnetisierungsreserve für einen Läufer aus Blech
  und Aluminium. Die ASM-Feldstufe braucht Elmers `MagnetoDynamics2DHarmonic` und ist
  noch nicht gebaut.
* Auch `screen` (Vorauswahl) weist magnetlose Arten ab — sie fährt den Magnet-
  Kombinationsraum ab.
* **Beim Lesen der ASM-Zeile:** das PSM-Luftspaltfeld ist durch die Magnete
  **festgelegt**, das der ASM wird über den Magnetisierungsstrom **eingestellt**
  (Zielwert `geom.bZielT`, Vorgabe 0,80 T). Ob dieser Strom aufzubringen ist, sagt
  `I_s` und die Warnung am Umrichter-Limit — sonst wäre das Feld geschenkt. Der Preis
  steht daneben: `I_s` trägt den Magnetisierungsstrom **dauernd** mit, und der
  Schlupfverlust fällt im **Läufer** an, also an der thermisch schlechtesten Stelle.

### Ganz zuerst: WELCHER Lastfall? (Fahrzyklus + Fahrzeug)

Ein Fahrzyklus ist eine Geschwindigkeit über der Zeit — welches **Moment** daraus wird,
entscheidet das **Fahrzeug** (Masse, Radhalbmesser, Übersetzung, Luft- und Rollwiderstand).
Beide gehören zusammen, und beide sind eine **Wahl am Anfang**:

```bash
python3 cae_cli.py zyklus liste          # was es gibt, und für WELCHES Fahrzeug
```

* `--frisch` setzt **`cycle=off`** — ohne Wahl wird kein Fahrzyklus gerechnet. Das ist
  Absicht: früher fehlte der Schlüssel ganz, die Pipeline fiel still auf `wltp3` zurück
  (das zusätzlich die **Autobahn-Volllastfahrt** nach sich zieht), gerechnet am
  **1600-kg-Pkw** mit Übersetzung 9,5. Ein Fahrrad-Nabenmotor bekam so 23 km WLTP und
  220 km/h Autobahn — Zahlen, die eine andere Maschine beschreiben als die bestellte.
* **Passt ein eingebauter Zyklus, nimm ihn:** `run analyse --zyklus stadtland …`
* **Passt keiner, definiere einen — und behalte ihn.** Er landet in der gemeinsamen
  Datenbank, also steht er beim nächsten Mal schon da (und zwei Auslegungen für
  denselben Einsatz sind über denselben Zyklus gerechnet und damit vergleichbar):

```bash
python3 cae_cli.py zyklus anlegen pedelec_stadt \
    --phasen "0:5,18:12,18:120,25:15,25:240,12:10,12:60,0:12" \
    --fahrzeug mass_kg=140 --fahrzeug r_wheel_m=0.35 --fahrzeug gear_ratio=1.0 \
    --fahrzeug cwA_m2=0.5 --fahrzeug cr=0.006 \
    --beschreibung "Stadtfahrt Pedelec, 25 km/h Spitze"
python3 cae_cli.py run analyse --frisch --zyklus pedelec_stadt --wait
```

* `--phasen` sind `ziel_kmh:dauer_s`, durch Komma getrennt; in jeder Phase läuft die
  Geschwindigkeit linear auf das Ziel. Konstantfahrt = denselben Wert wiederholen.
* **Direktantrieb heißt `gear_ratio=1.0`.** Die Vorgabe 9,5 ist ein Pkw-Getriebe; mit ihr
  rechnet ein Nabenmotor das Neunfache an Raddrehzahl.
* `--zyklus` setzt **Zyklus UND Fahrzeug** — nie nur eins davon. Ein eigener Zyklus mit
  dem Fahrzeugmodell eines 1600-kg-Autos ergibt wieder die Momente eines Autos.
* `run analyse` schreibt den Lastfall **vor** dem Start in einer Zeile hin. Steht dort
  nicht, was du meinst, brich ab — die Analyse dauert Stunden.
* Für Maschinen ohne Fahrprofil (Spindel, Pumpe, Prüfstand) ist `off` richtig: dann
  zählen Auslegungspunkt und Kennfeld, und es steht kein fremdes Fahrzeug im Bericht.

### Nach jedem Lauf: Sicherheitskriterien prüfen

```bash
python3 cae_cli.py sicherheit --from-project <pid>     # Exit 0 = bestanden, 1 = verletzt
```

Die Pipeline **meldet** ihre Grenzwertverletzungen im Protokoll, aber sie hält nichts an
und schreibt „✅ Analyse abgeschlossen" darunter. Geprüft werden deshalb an einer Stelle:

| Kriterium | Grenze | woher |
|---|---|---|
| Festigkeit | FEM-Sicherheitsfaktor ≥ 1,5 (< 1,0 = Versagen) | `summary.safety_factor_fem` |
| Drehzahl | sichere Drehzahl ≥ Betriebsmaximum | `summary.max_safe_rpm` |
| Magnet (Dauer + Spitze) | **Dauergrenze des Werkstoffs** — NdFeB N35: 80 °C, Ferrit: 250 °C | Werkstofftabelle |
| Wicklung | 180 °C dauernd, 200 °C kurzzeitig (Klasse H) | `thermal` + je Zyklus |
| Entmagnetisierung | Abstand zum Knie | `em_advanced.demag` |
| Fahrprofil | Zyklus und Fahrzeug müssen im Payload stehen | `meta.payload` |

* **`safety_factor_fem = null` heißt NICHT „sicher", sondern „nicht gerechnet".** Dann
  ruht die Festigkeitsaussage allein auf der Ringformel, die die Spannungsspitzen an den
  dünnen Stegen über den Magnettaschen nicht kennt — das melden.
* Die Temperaturen werden über **alle** gerechneten Zyklen genommen, nicht nur am
  Auslegungspunkt: der Auslegungspunkt kann 46 °C zeigen, während derselbe Lauf im
  Zyklus 210 °C erreicht.
* Ein verletztes Kriterium ist **kein Nebensatz im Abschlussbericht**. Entweder du
  behebst es (Kühlung, Magnetwerkstoff, Drehzahlgrenze, Geometrie) oder du sagst
  ausdrücklich, dass die Auslegung so nicht einsetzbar ist.

### Nach `analyse` gehört der 3D-Lauf dazu — nicht als Zugabe

Das 2D-FDM-Feld ist analytisch verankert, aber **zweidimensional**: axiale Streuung,
Schrägung und die Endwirkung an den Stirnseiten sieht es nicht. Der Elmer-Lauf ist die
unabhängige Gegenrechnung dazu; `em3d.compare_2d` stellt beide nebeneinander. Eine
Auslegung ohne ihn ist eine 2D-Zahl ohne Gegenprobe.

```bash
python3 cae_cli.py run analyse --from-project last --wait      # 30 min – 4 h
python3 cae_cli.py run em3d --from-project <pid> --wait        # 5–30 min
python3 cae_cli.py raw POST /project/<pid>/report --data '{}'  # Bericht MIT 3D-Abschnitt
```

* **Immer `--from-project <pid>` mit der Kennung des gerade gerechneten Projekts.**
  Der Payload trägt daraus `project_id`, und das 3D-Ergebnis landet im selben Projekt
  wie die 2D-Rechnung. Ohne das nimmt `/em3d` das im Server zuletzt aktive Projekt —
  dann vergleicht `compare_2d` zwei Fremde oder es entsteht ein eigenes `…_em3d`-Projekt.
* **Der Bericht entsteht NICHT in der Pipeline**, sondern über `POST
  /project/<pid>/report`. Sobald `results["em3d"]` existiert, nehmen beide Berichtsarten
  den bebilderten 3D-Abschnitt und die 2D-gegen-3D-Tabelle von selbst auf. Also: erst
  `em3d`, dann den Bericht — sonst steht die Gegenprobe nicht darin.
* **503 heißt: Elmer fehlt.** Das melden, nicht stillschweigend überspringen.
* `run em3d` hat eine **eigene** Statusroute (`/em3d/status`). `status` allein zeigt
  weiter die Pipeline und meldet `idle`, während der 3D-Lauf rechnet.
* `em3d_sweep` (mehrere Betriebspunkte, Stunden) ist NICHT Teil des Regelwegs — nur
  auf ausdrückliche Ansage.

### `lernen probieren` — den Raum einmal kartieren

`screen` waehlt aus, `lernen probieren` **kartiert**. Es faehrt jede Bauform ueber jede
Polzahl ab und haelt fest, was dabei herauskommt:

```bash
python3 cae_cli.py lernen probieren --frisch --merken
```

Drei Arten von Befund, alle nachpruefbar:

1. **Baubarkeit je Bauform** — bei welchen Polzahlen sie in voller Magnetgroesse passt,
   ab wann der Magnet verkleinert werden muss (mit Massstab), und wo sie gar nicht geht.
   Das ist Geometrie; ein Feldlauf kann es nicht umstossen.
2. **Welche Achse eine Kennzahl gar nicht bewegt.** Beispiel aus dem echten Versuch:
   `Kt` und `B_gap` haengen auf der analytischen Stufe weder von der Nutzahl noch von der
   Leiterzahl ab, und **V und U sind dort ununterscheidbar** (gleiche Kt, gleiche B_gap).
   Das musst du nicht selbst herausfinden — steht nach dem Versuch in `lernen zeige`.
3. **Welche Nut/Pol-Paarungen wicklungsfaehig sind** — reine Arithmetik.

Mit `--merken` gehen die Befunde als belegte Regeln in den Lernspeicher; ohne `--merken`
werden sie nur angezeigt. **Rangfolgen werden nie gemerkt** — die haengen am Verfahren,
und das ist hier analytisch.

### `bilddaten` — was das Auge sieht und keine Kennzahl misst

Manches am Querschnitt beurteilt ein Mensch besser als jede Formel: ob die Stege
gleichmaessig sind, ob der Magnet zur Polteilung passt, ob das Blech ausgewogen wirkt.
`bilddaten` bereitet genau diese Frage vor.

```bash
python3 cae_cli.py bilddaten erzeugen --anzahl 500 --seed 1
python3 cae_cli.py bilddaten seite
```

Das zieht Zufallsgeometrien, wirft alles weg, was `rotor_layout_check` ablehnt (das sind
rund **drei Viertel** — geometrisch unmoegliche Maschinen, die niemand ansehen muss),
zeichnet den Rest und schreibt eine HTML-Seite. **Dann bist du fertig und musst es
sagen:** die Seite gehoert in einen Browser, und die Urteile faellt der Mensch. Ein
Modell, das die Bilder selbst bewertet, hat den Zweck der Uebung aufgehoben.

Danach:

```bash
python3 cae_cli.py bilddaten einlesen --datei ~/Downloads/urteile.json
python3 cae_cli.py bilddaten regel --merken
```

`regel` sucht eine **Schranke** ueber messbaren Groessen des Blechschnitts (Stegbreite,
Polbedeckung, Nabenanteil …), die die Urteile trifft, und prueft sie auf einem
zurueckgehaltenen Drittel. Haelt sie dort nicht, wird sie **nicht** abgelegt — mit
Begruendung. Das ist der Sinn der Sache: eine Schranke, die nur den Lernteil trifft,
ist eine Eigenschaft des Datensatzes und keine des Rotors.

Was NICHT passiert: kein neuronales Netz, keine Heuristik-Vorbelegung der Bilder. Die
Bewertungsseite zeigt das Bild und sonst nichts — wer eine Vermutung vorschlaegt,
bekommt sie bestaetigt zurueck.

### Erst schnell entscheiden, dann genau rechnen — `--guete`

```bash
python3 cae_cli.py run analyse --frisch --guete entwurf --wait   # Minuten
python3 cae_cli.py run analyse --from-project <pid> --guete detail --wait
```

**Das ist die wichtigste Arbeitsweise in diesem Werkzeug, und sie war dir bisher
verschlossen:** die Regler für die Rechengüte (Auflösung, Netzweite, Bildzahl)
stehen in **keinem** Schema, `--set fdm_resolution=300` wurde als unbekannt
abgewiesen — jeder Entwurfsversuch lief also in Detailgenauigkeit, Stunden statt
Minuten.

| | `entwurf` | `detail` |
|---|---|---|
| FDM-Auflösung | 300 | 800 |
| Struktur | eigener Satz (`ccx`), 4 mm | FreeCAD, 2,5 mm |
| Bilder je Umlauf | 12 | 36 |
| Drehzahlschritt | 1000 | 500 |
| wofür | durchspielen, entscheiden, verwerfen | die Zahl, die in den Bericht geht |

**Warum sich mit `entwurf` überhaupt entscheiden lässt** (gemessen am Projekt
`20260827_170019_Alpenpass`): `B_gap` und `Kt` hängen **nicht** an der Auflösung
— sie kommen aus der analytischen Formel. Ein Entwurfslauf verliert also keinen
Kennwert, nur Bildschärfe und die Feinform der Luftspaltwelle. Deshalb geht auch
keine Stufe unter N=300: darunter liegt die Wellenform um die Hälfte daneben.

Der Mensch gibt dir in der Startmaske eine **Zahl von Entwurfsschleifen** vor.
Halte dich daran: so viele schnelle Runden mit `--guete entwurf`, nach jeder
`sicherheit --from-project <pid>` und daraus die nächste Änderung — und erst
wenn ein Stand alle Kriterien hält, EIN Lauf mit `--guete detail`. Sag in jeder
Antwort, in welcher Runde du bist. Brauchst du mehr, frag; laufe nicht
stillschweigend weiter.


### `welle` — Vollwelle oder Hohlwelle, und du entscheidest das

```bash
python3 cae_cli.py welle --from-project <pid>          # Leerlauf
python3 cae_cli.py welle --from-project <pid> --last   # unter Last
```

Eine Wellenbohrung (`shaftBoreD`, 0 = Vollwelle) spart Masse und Trägheit und
nimmt Kühlmittel oder eine Steckverzahnung auf — sie ist **erst dann falsch,
wenn durch die Welle Fluss läuft**. Das ist messbar, also wird es gemessen: ein
FDM-Lauf, das radiale Profil von |B| im Rotor, und daraus der größte Radius,
unter dem nirgends Fluss steht.

Der Befund sagt dir die Änderung fertig hin (`--set shaftBoreD=58.0`) — oder
dass eine Vollwelle nötig ist. **Er ist magnetisch**: ob die Welle Moment und
Fliehkraft trägt, sagt `struktur` bzw. `sicherheit`. Eine magnetisch
unbedenkliche Bohrung kann mechanisch unzulässig sein; gib das so weiter.


### `steckbrief` — was dieses Projekt ist, bevor du etwas daran änderst

```bash
python3 cae_cli.py steckbrief                       # das jüngste Projekt
python3 cae_cli.py steckbrief 20260903_183044       # ein bestimmtes
python3 cae_cli.py steckbrief last --laeufe         # + frühere Läufe und Ablagen
```

**Fragt dich jemand nach einem „Steckbrief" oder „was ist das für ein Projekt",
ist DAS gemeint — die Maschine, nicht das Repo.** Der Unterschied ist einmal
schiefgegangen: auf „erstelle kurz einen Steckbrief über das Projekt" kam eine
Beschreibung des Monorepos samt Ports und Git-Zweig. Über die Maschine dagegen
steht alles hier: Art, Pole, Nuten, Bauraum, Luftspalt, Werkstoffe,
Betriebspunkt, gelaufene Stufen, Kennwerte.

Zwei Dinge, auf die du dich verlassen kannst und die du nicht überschreiben
darfst:

* **Es wird nichts gerechnet und nichts aufgefüllt.** Was auf der Platte fehlt,
  steht als fehlend da — nicht als 0, nicht als Näherung.
* **Jeder Kennwert trägt seine Herkunft**: `[analytisch]` ist die geschlossene
  Formel, `[fdm2d]` das gelöste 2D-Feld, `[fem3d]` die FEM. `B_gap_T` und
  `T_maxwell_Nm` stehen im selben `summary` nebeneinander und sähen ohne diese
  Angabe gleichwertig aus. Sie sind es nicht. Gib die Herkunft mit weiter.

Der Steckbrief steht auch am Anfang von `AGENTS.projekt.md`, sobald ein Projekt
gebunden ist — du musst ihn also nicht erst abrufen, um zu wissen, woran du
arbeitest.


### Was du rechnest, bleibt im Projekt liegen

`paarvergleich`, `screen`, `rotor-check`, `sicherheit` und `feldbild` schreiben
ihr Ergebnis **von selbst** nach `<projekt>/rechnungen/<zeit>_<verb>.txt` (mit
dem Aufruf im Kopf) und hängen eine Zeile an das Projekttagebuch in
`project.json`. Das gilt, sobald ein Projekt bestimmt ist — über
`--from-project <id>` oder `--projekt <id>`.

**Warum dich das angeht:** vorher ging ein Ergebnis nur auf den Schirm, und die
Begründung eines Entwurfs überlebte den Entwurf nicht. Zwei Folgerungen für
deine Arbeitsweise:

* Arbeite **mit** einem Projekt, sobald eine Auslegung ernst wird. Mit
  `--frisch` oder `--payload` gibt es keinen Ort für das Ergebnis, und es
  bleibt nirgends.
* Bevor du eine Entscheidung neu ausrechnest, sieh mit
  `steckbrief <id> --laeufe` nach, ob sie schon einmal ausgerechnet wurde. Die
  abgelegten Dateien sind dein eigener Bestand, nicht der eines Fremden.

`--ohne-ablage` schaltet das ab — nur für ein Ausprobieren, das nirgends
hingehört.


### `feldbild` — das Feld zeigen, ohne einen Lauf zu starten

Wer zusieht, fragt irgendwann „wie sieht das Feld dazu aus?". Die Antwort darauf ist
**nicht** ein neuer Pipelinelauf. `feldbild` rechnet EINEN FDM-Lauf auf der Geometrie,
die gerade zur Debatte steht, und legt die Bilder in `<projekt>/charts/` — dort, wo die
rechte Spalte sie ohnehin findet.

```bash
python3 cae_cli.py feldbild --from-project last                    # alle vier Ansichten
python3 cae_cli.py feldbild --from-project last --ansicht pol --n 700
python3 cae_cli.py feldbild --from-project last --last             # unter Last statt Leerlauf
```

Vier Ansichten, jede beantwortet eine andere Frage:

| Ansicht | Wofuer |
|---|---|
| `linien` | Wo laeuft der Fluss ueberhaupt? Ganzer Querschnitt, Blech durchscheinend |
| `schnitt` | Wie sieht es im Luftspalt und in den Taschen aus? Stator ueber 90° weggenommen |
| `pol` | Stege, Barrieren, Streupfade EINZELN — im Vollbild sind sie ein Knaeuel |
| `laengs` | Achsschnitt (r–z), Endeffekt an den Paketenden |

**Die Darstellung ist durchsichtig, und zwar nach der Flussdichte**: Luft ist unsichtbar,
gesaettigtes Blech nahezu deckend. Man sieht deshalb durch die Maschine hindurch auf das,
was Fluss fuehrt.

**Der Laengsschnitt ist der eine Fall, in dem nicht immer ein gerechnetes Feld drinsteht.**
Die 2-D-FDM kennt kein z; Feldlinien ueber der Paketlaenge gibt es nur aus einem
3-D-Elmer-Lauf. Liegt keiner im Projekt, zeigt das Bild die Geometrie und **sagt das im
Bild**. Erfinde dazu nichts — `run em3d` ist der Weg, nicht eine Beschreibung.

Vorgabe ist der **Leerlauf** (nur Magnetfluss). `--last` nimmt Drehzahl und Last aus dem
Payload und rechnet den MTPA-Punkt — dieselbe Schaetzung, mit der die Pipeline ihre
Lastbilder rechnet. Beide nebeneinander zeigen die Ankerrueckwirkung; einzeln ist keines
davon „das Feld der Maschine".

### Noch davor: `paarvergleich` — worüber überhaupt entschieden wird

> **Pflichtschritt bei jedem Projektstart.** Bevor du eine Zahl vorschlägst oder
> irgendetwas rechnest, lässt du `paarvergleich --frisch` über **alle** Achsen
> laufen und trägst dem Nutzer die Befunde vor: Rotor- und Statorabmaße,
> Magnetanordnung, V-Öffnungswinkel, Polzahl, Leiter je Nut, Kühlung, Werkstoffe,
> Wellendurchmesser, Wellenverbindung, Verschraubung und was Flussbarrieren
> bringen. **Übernimm dafür nichts aus einem alten Projekt.** Auch wenn ein
> Projekt gebunden ist und daneben liegt: seine Entscheidungen sind seine, nicht
> die der neuen Maschine. Erst wenn der Nutzer gewählt hat, geht es weiter.

`screen` variiert Polzahl, Nutzahl, Bauform und Leiterzahl und gibt eine Rangliste
heraus. Das beantwortet „welche Variante nehme ich?". Eine Stufe früher steht aber
eine andere Frage: **woran hängt die Maschine überhaupt?** Magnetanordnung, Zahl der
Hairpins, Werkstoffe, Kühlung, Durchmesser, Länge — das sind die Entscheidungen, die
eine Auslegung prägen, und sie fallen der Reihe nach.

```bash
python3 cae_cli.py paarvergleich --frisch                       # ALLE Achsen — der Pflichtstart
python3 cae_cli.py paarvergleich --frisch --achsen anordnung,kuehlung,durchmesser
python3 cae_cli.py paarvergleich --frisch --achsen verschraubung,flussbarrieren
python3 cae_cli.py paarvergleich --frisch --achsen anordnung,v_oeffnung,wellendurchmesser
python3 cae_cli.py paarvergleich --referenz                     # recherchierte Werte + Quellen
python3 cae_cli.py paarvergleich --from-project <id>            # NUR zum Nachvollziehen
```

Zwei Ausgaben, und die zweite ist die wichtigere:

1. **Die Paare.** Je Achse jede Option gegen jede, mit der Angabe, welche Kennzahl
   für welche Seite spricht — und welche sich zwischen beiden **gar nicht** bewegt.
2. **„Was bewegt was".** Die Spannweite jeder Kennzahl über die Optionen EINER
   Achse. Daraus fällt die Reihenfolge der Entscheidungen heraus, statt geraten zu
   werden. Gemessen an einer 260-mm-Maschine: die Magnetanordnung bewegt Kt um
   **230 %**, der Durchmesser um 59 %, die Nutzahl um 0 %.

**Es gibt hier bewusst keine Gesamtnote und keinen Sieger.** Eine Gewichtung über
Kt, Kosten und Masse ist eine Zielentscheidung, keine Rechnung — `screen --ziel`
macht sie bereits offen und nachvollziehbar. Der Paarvergleich stellt gegenüber;
die Wahl trifft der Mensch. Trag ihm die Achsen vor, die seine Frage betreffen, und
sag dazu, was sich **nicht** bewegt — das ist oft die nützlichere Hälfte.

### Die Anordnungen vergleicht man über den STROM, nicht über Kt

Das ist die wichtigste Lesehilfe der ganzen Tabelle. **`Kt` ist reines
Magnetmoment** — die analytische Formel ist `1,5·p·ψ_pm`, das Reluktanzmoment
kommt darin nicht vor. Genau daran unterscheiden sich aber V, asymmetrisches V,
U, Delta, Doppel-V und PMa-SynRM in erster Linie.

Deshalb trägt die Tabelle **`I_s [A]`**: den Strangstrom, den diese Anordnung für
den **gemeinsamen** Betriebspunkt braucht (MTPA, also mit Reluktanzmoment). Klein
ist besser. Dort — und nur dort — zeigt sich der Nutzen der Anordnung.

An der Beispielmaschine gemessen: PMa-SynRM hat mit 0,021 das **kleinste** Kt der
ganzen Achse und braucht mit 525 A den **kleinsten** Strom; SPM hat mit 0,061 das
größte Kt und läuft ins Umrichter-Limit. Wer nach Kt sortiert, dreht die Reihenfolge
also um. Doppel-V (644 A) und Delta (656 A) liegen deutlich unter dem einfachen V
(798 A) — das ist der Grund, aus dem mehrlagige Anordnungen gebaut werden.

Zwei Zusatzspalten ordnen ein (sie zählen **nicht** in der Bilanz):
`xi_LqLd` = Lq/Ld aus dem recherchierten Band je Anordnung, `T_rel_pct` = Anteil des
Reluktanzmoments. **Achtung:** der Anteil folgt nicht dem xi — eine Speiche mit
kleinem xi kann einen größeren Reluktanzanteil haben, weil ihr ψ_pm kleiner ist.

Steht unter einer Zeile **⚠ Strom am Umrichter-Limit**, ist `I_s` dort kein Messwert
mehr, sondern ein Anschlag: die Option erreicht das geforderte Moment gar nicht, und
zwei gedeckelte Optionen sehen mit demselben Wert gleich aus. Sag das dazu, statt die
Zahl zu vergleichen.

### V-Öffnungswinkel: es gibt ein Optimum, keine Richtung

Die Achse `v_oeffnung` gilt nur für die Formen, die `magAngle` überhaupt lesen
(V, asym. V, U, Doppel-V, Delta, PMa-SynRM) — bei Balken, Oberfläche und Speiche
meldet sie selbst, dass sie bedeutungslos ist.

Der Zielkonflikt ist belegt: **Momentdichte steigt mit dem Öffnungswinkel, das
Reluktanzmoment fällt.** Es gibt deshalb ein Optimum; die Literatur nennt für eine
8-polige Maschine **115°** als Kompromiss (Polbogenwinkel 130°). Die Reihe ist um
diesen Wert gelegt und beschriftet ihn als das, was er ist: ein Anhaltspunkt aus
einer fremden Maschine, kein Sollwert.

### Woher die recherchierten Werte kommen

`python3 cae_cli.py paarvergleich --referenz` zeigt sie mit Quelle und Fundstelle.
**Es ist Fremdtext** — abgerufene Veröffentlichungen, nicht gerechnet und nicht
nachgerechnet. Zwei Sorten, sauber getrennt: **wörtlich übernommene Messpunkte**
(mit Zitat) und **abgeleitete Bänder** (unsere Einordnung, jedes nennt die
Messpunkte, auf denen es ruht). Nenne sie in einer Antwort nie ohne Quelle und nie
als Ersatz für eine Zahl aus der Rechnungsdatenbank.

Dieselbe Quelle trägt die **Bauverhältnisse** von sieben abgerufenen Maschinen
(Rotor/Stator, Wellenbohrung/Rotor, Länge/Durchmesser, Luftspalt). Liegt eine Option
außerhalb, steht das mit ⓘ darunter — **kein Tor**: außerhalb heißt nicht falsch,
sondern nur, dass die Vorbilder dort keine Auskunft geben.

Drei Modellgrenzen, die in der Antwort mitgehören:

* Die **Kühlung** wirkt nur über eine Tabelle von Schubspannungen je Kühlart
  (`COOLING_RATING`), nicht über einen gerechneten Wärmeübergang. Sie bewegt das
  Dauermoment und sonst nichts.
* **Nutzahl und Leiterzahl bewegen Kt und B_gap auf dieser Stufe nicht** — die
  analytische Momentformel kennt weder Windungs- noch Nutzahl. Die Hairpin-Achse
  ist eine Achse über Widerstand, Verlusten und Aufwand.
* Beim **Durchmesser** wird geometrisch ähnlich skaliert, der **Luftspalt bleibt
  aber stehen** — der ist fertigungsbedingt.
* **Flussbarrieren und Wuchtverschraubung** bewegen analytisch nur die Masse
  (weggenommenes Eisen). Ihre entscheidende Auskunft ist eine andere: ob sie in
  eine Magnettasche schneiden. Das steht mit ⚠ unter der Option und zählt in der
  Paarbilanz als „Platz im Blech". Die **magnetische** Wirkung der Barrieren kennt
  erst der Feldlauf — wer sie hier nach Kt beurteilt, beurteilt sie nach der einen
  Größe, die sie nicht abbildet. Sag das dazu.

Danach erst `screen`, dann `rotor-check`, dann `run`.

### Ganz am Anfang: `screen`

**Bei einer NEUEN Auslegung nimm `--frisch`, nicht `--from-project last`.**

`--frisch` baut den Grundpayload aus den Schemavorgaben — kein Altprojekt, keine
geerbten Entscheidungen. `--from-project last` erbt dagegen **alles**: Polzahl,
Nutzahl, Magnetanordnung, Kühlung, Werkstoffe, Barrieren. Das sind genau die
Entscheidungen, die bei einer neuen Maschine neu zu treffen sind. Wer damit
anfängt, legt keine Maschine aus, sondern schreibt die vorige ab.

```bash
python3 cae_cli.py screen --frisch --auftrag "<der Auslegungsauftrag>"
python3 cae_cli.py screen --frisch --ziel leistung \
        --pole 3,4,5 --nuten 36,48 --formen v,vasym,spoke --leiter 4,6
```

`--from-project <id>` ist richtig, wenn du eine **bestehende** Auslegung nachrechnest,
verfeinerst oder gezielt einen Wert daran änderst — also überall dort, wo das Erbe
gewollt ist. Sonst nicht.

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
willst statt Platz 1 zu nehmen. Achte auf die **12-000-Zeichen-Kürzung** — sie gilt
für die JSON-Ausgabe ALLER Verben (nicht nur `results`, `emit()` in `cae_cli.py`):
Rangliste plus eingepasste Geometrie je Zeile überschreiten sie schnell, und das
Ergebnis ist abgeschnittenes, nicht parsebares JSON — der Bruch sitzt mitten in der
Zeile, `json.load` meldet „Invalid control character" oder „Unterminated string".
`--full` hebt die Kürzung auf; `--zeige N` verkürzt zusätzlich die Rangliste. Wer
die JSON in ein Skript leitet: `--full` immer mitgeben, sonst ist das `json.loads`
ein Wurf ins Kalkül.

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
python3 cae_cli.py rotor-check --frisch --set p=4 --set magShape=vv
python3 cae_cli.py rotor-check --from-project <id> --set magLayerGap=4 --set magDist=6
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
| `analyse` | volle Pipeline (Bericht NICHT — der ist `POST /project/<pid>/report`) | **30 min–4 h** | FreeCAD + CalculiX |
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
