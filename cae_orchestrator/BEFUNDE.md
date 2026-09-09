# Befunde

Was am Werkzeug selbst falsch ist — beobachtet, gemessen, mit Fundstelle.

Diese Datei gibt es, weil ein Agent, der einen Mangel findet, zwei schlechte
Auswege hätte: ihn still zu reparieren (dann stammen die Zahlen vor und nach der
Reparatur aus zwei verschiedenen Werkzeugen, und man sieht ihnen das nicht an —
siehe `ema_werkzeugstand.py`), oder ihn zu verschweigen und um ihn herum zu
rechnen. Ein Befund ist der dritte Weg: aufschreiben, was beobachtet wurde, wo es
gemessen wurde und an welcher Stelle es steht — und dann weiterarbeiten oder
begründet Nein sagen.

**Form:** neuester Eintrag oben, Datum als Überschrift, darin *Beobachtung ·
Messung · Fundstelle · Status*. Ein behobener Punkt bleibt stehen und bekommt
seinen Stand dazu; gelöschte Befunde sind Befunde, die niemand mehr nachprüfen
kann.

---

## 2026-09-09 — Der Fahrzyklus konnte das Getriebe lesen, aber niemand schrieb es hin

**Beobachtung.** `ema_drivecycle.compute_drivetrain` liest seit dem Getriebe-Umbau
`vehicle["getriebe"]` und rechnet daraus Übersetzung, η(T, n), Masse und die
reduzierte Trägheit. Gesucht nach der Gegenstelle: **kein einziger Schreiber** im
ganzen Repo — nicht das Verb, nicht die Route, nicht die Oberfläche.

**Messung.** `grep -rn 'vehicle\["getriebe"\]' --include=*.py` findet außer der
Lesestelle selbst nur Tests. Jeder Lauf rechnete also weiter mit `gear_ratio` 9,5
und `eta_drive` 0,95, während daneben eine gerechnete Auslegung im Projekt lag —
genau der Zustand, gegen den der Umbau gebaut war („solange das Ergebnis die zwei
Konstanten nicht ersetzt, ist es ein Werkzeug, das nichts berührt").

**Fundstelle.** `ema_drivecycle.py:623` (die Lesestelle); die fehlende
Schreibstelle in `cae_cli.cmd_getriebe` und `server.getriebe_start`.

**Status: behoben** (09.09.2026). `cae_cli._getriebe_uebernehmen` schreibt die
Auslegung nach `meta.json` unter `vehicle.getriebe` und setzt `gear_ratio`
mit — eine skalare Angabe, die etwas anderes behauptet als das Getriebe daneben,
wäre schlimmer als keine. Ausgelöst wird es ausdrücklich: `--uebernehmen` am Verb,
Häkchen im Reiter, `uebernehmen: true` an der Route; die Route ruft dieselbe
Funktion. Übernommen wird nur, wenn die Verzahnung **trägt** — ob der Satz an
seinen Einbauort passt, geht den Fahrzyklus nichts an. Gemessen am
Stadt-Land-Zyklus: n_max 7475,5 → 7488,7 1/min und ein anderes Spitzenmoment,
weil η jetzt an der Last hängt und `J_red` beim Beschleunigen wie Masse wirkt.
`test_getriebe.py` [14] prüft die ganze Strecke; ohne den Schlüssel bleibt jede
bestehende Rechnung Ziffer für Ziffer dieselbe.

**Und der Agent fand das Verb gar nicht erst.** `getriebe` stand nicht in der
Verbtabelle der `SKILL.md` — nur in einem eigenen Abschnitt weiter unten —,
während der Fahrzyklus-Abschnitt daneben zum Handeintrag von `gear_ratio` riet.
Beides ergänzt: die Tabelle führt das Verb, und an der `gear_ratio`-Stelle steht,
dass eine von Hand gesetzte Zahl eine Annahme ohne Zähnezahlen, ohne
Tragfähigkeit und mit lastunabhängigem Wirkungsgrad ist.

---

## 2026-09-09 — `child_env` warf `/usr/bin` aus dem PATH, sobald der Aufrufer im System-Python lief

**Beobachtung.** `python3 cae_cli.py getriebe … --cad` meldete „CAD nicht
erzeugt: FreeCAD meldete keinen Erfolg". Derselbe Aufruf mit
`venv/bin/python cae_cli.py …` zeichnete anstandslos.

**Messung.** `freecad_runner.child_env` nimmt `sys.prefix/bin` aus dem PATH des
FreeCAD-Unterprozesses — richtig, solange der Aufrufer im venv läuft (dort liegt
der `gmsh`-Wrapper, der sonst ein Netz mit 0 Knoten erzeugt, ohne zu warnen). Im
**System-Python** ist `sys.prefix` aber `/usr`, und damit fiel `/usr/bin`
heraus. Gemessen scheitert dann schon pixi:
`failed to activate environment · An activation error occurred:
IoError(Os { code: 2, kind: NotFound })` — also **jeder** FreeCAD-Aufruf aus
`cae_cli.py`, das ausdrücklich im System-Python läuft.

Latent war das, solange nur der Server zeichnete (der läuft im venv) und die CLI
ihre CAD-Arbeit über HTTP an ihn gab. Das erste CLI-Verb, das FreeCAD **selbst**
aufruft, ist `getriebe --cad` — daran fiel es auf.

**Fundstelle.** `freecad_runner.py`, `child_env()`
(`drop = {os.path.realpath(os.path.join(sys.prefix, "bin"))}`).

**Status: behoben** (09.09.2026). Herausgenommen wird nur noch eine **echte**
virtuelle Umgebung — `sys.prefix != sys.base_prefix`, das ist die Bedingung, die
venv definiert; `VIRTUAL_ENV` wird wie bisher zusätzlich beachtet. Nachgemessen
in beiden Interpretern: System-Python behält `/usr/bin` und FreeCAD läuft, venv
verliert weiterhin sein `bin/`. `test_getriebe.py` [12] prüft beide Fälle.

---

## 2026-09-09 — Zweierlei zusammengeworfen: „traegt nicht" und „passt nicht"

**Beobachtung.** Ein Planetensatz i = 5 in einer 90-mm-Welle wurde als
`haelt: false` abgelegt, obwohl beide Sicherheiten seiner einzigen Stufe standen
(S_F 2,49 gegen Ziel 1,4 · S_H 1,06 gegen Ziel 1,0) und die Stufe selbst
`haelt: true` meldete. Der Satz passte lediglich nicht in die Bohrung: gebraucht
100,6 mm, verfügbar 58,0 mm.

**Messung.** `ema_getriebe.auslegen` verrechnete beim Einbau in der Welle
`haelt` mit `passt` zu einem einzigen Wert. Der ausgegebene Text hatte den
Unterschied schon berücksichtigt — er rechnete `verzahnung_haelt` eigens aus den
Stufen zurück und trug den Grund dafür als Kommentar —, der **abgelegte
Schlüssel** aber nicht. Jeder spätere Leser (Steckbrief, Bericht) erbte damit
die Verwechslung, und die schickt die Suche in die falsche Richtung: eine
Verzahnung, die trägt und nur nicht in die Bohrung geht, braucht mehr Platz,
nicht mehr Modul.

**Fundstelle.** `ema_getriebe.py`, Ende von `auslegen` (`erg["haelt"] =
bool(erg["haelt"] and erg["passt"])`) und `als_text` (die Rückrechnung).

**Status: behoben** (09.09.2026). `haelt` ist wieder ausschließlich die Aussage
über die Verzahnung; wer beides zugleich braucht, fragt `haelt and passt` — so
macht es das Verb für seinen Exit-Code. `als_text` liest den Schlüssel jetzt
direkt statt ihn zurückzurechnen. `test_getriebe.py` [6] nagelt den Unterschied
an genau diesem Fall fest.

## 2026-09-09 — Zwei Rechnungen in derselben Sekunde standen in der falschen Reihenfolge

**Beobachtung.** Zwei nacheinander abgelegte `getriebe`-Auslegungen in einem
Projekt: die **ältere** wurde als die jüngere ausgelesen.

**Messung.** `ema_steckbrief._freie_marke` hängt bei einer Kollision ein `-2` an
(`20260101_000000` → `20260101_000000-2`), und `rechnungen()` sortierte die
Marken als **Zeichenketten** absteigend. Im Dateinamen folgt auf die Marke ein
Unterstrich (0x5F), auf die Nummer ein Bindestrich (0x2D) — `..._getriebe.json`
sortiert damit über `...-2_getriebe.json`, und der erste Eintrag war der ältere.
Zwei Verben in einem Agentenzug sind beide in Millisekunden fertig; das ist der
Normalfall und nicht der Sonderfall.

**Fundstelle.** `ema_steckbrief.py`, `rechnungen()` (`sort(key=lambda r:
r["marke"])`). Dass sich die Dateien nicht überschreiben, war geprüft — die
Reihenfolge nicht.

**Status: behoben** (09.09.2026). `_marke_key` liest die Nummer als **Zahl**;
`rechnungen()` und `getriebe()` sortieren darüber. `test_getriebe.py` [13] legt
zwei Auslegungen in derselben Sekunde ab und verlangt die jüngere.

## 2026-09-08 (17:13 Uhr) — Die Pipeline stürzt ab, wenn der Luftspalt nicht aufgelöst ist

**Beobachtung.** Lauf des Stadtfahr-Zykklus `stadt_pkw_1400` (PSM, 1200 V,
rpm 500–4000, Güte `entwurf`): alle Gates bestehen (Rotor-Festigkeit 4000 U/min
SF 21,8), CAD fertig (112 Flächen, STEP exportiert), dann stirbt der Lauf in
der EM-Stufe mit
`TypeError: unsupported format string passed to NoneType.__format__` bei
`_log(state, f"… Maxwell-Moment ≈ {perf['T_maxwell_Nm']:.1f} Nm", 38)`
(`ema_pipeline.py:2158`).

**Messung.** `ema_analysis.py:1764` liefert seit dem Befund vom 08.09.2026
bewusst `T_maxwell_Nm = None` plus Begründung in `T_maxwell_grund`, wenn das
Luftband im FDM-Raster weniger als 2,5 Bildpunkte breit ist — korrekt, denn
dann wäre eine 0,0 Nm-Figur aus Sichtbarkeit eine Messung gewesen und es
gibt keine. Die Logzeile in `ema_pipeline.py:2158` wurde dabei nicht mit
angepasst und formatiert das `None` hart. Zusätzlich erzwinge `ema_pipeline.py:2869`
das `None` bei der Ablage auf 0 — dieselbe Falle, die im 08.09.-Befund
gegen genau dieses Verhalten argumentiert.

**Fundstelle.** `ema_pipeline.py:2158` (Log, Crashtreiber) und `:2869`
(Defaults bei der Ablage); Quelle des `None`: `ema_analysis.py:1761–1767`.

**Status: behoben** (08.09.2026, 17:20 Uhr). `ema_pipeline.py:2158` meldet
jetzt die Begründung aus `T_maxwell_grund`, falls das Moment nicht berechnet
wurde; `:2869` erzwingt keinen Default mehr. Kleiner Einzelfehler — der Befund
bleibt stehen und dokumentiert, wie diese Falle entstand.
**Offen bleibt die Ursache selbst:** bei einer 0,7-mm-Luftspalt-Maschine dieser
Größe ist das Band im FDM-Raster selbst bei hoher Güte nicht breiter als ca.
0,6 Bildpunkte (Befund oben) — `T_maxwell_Nm` bleibt dort `None`, und genau
das ist die richtige Antwort. Was diese Grundauslage dem Nutzer liefert, ist
`B_gap` und `Kt` aus der Analyseformel; die Feldstufen liefern Anschauung
und Maxwell-moment, wenn der Spalt aufgelöst ist, sonst nicht.

---

## 2026-09-08 — Der Schnellbewerter sah die gezeichnete Geometrie nicht

**Beobachtung.** Vor dem Bau einer freien („wilden") Magnetsuche wurde die
Grundlage nachgemessen: `ema_optimize._eval_geom`, der Schnellbewerter hinter
KI-Entwurf, Magnetfeinschliff, Parameterstudie und Zielwertsuche. Sechs
gezeichnete Layouts (`magShape:"custom"`, 280er-Maschine, sonst identisch):

| gezeichnet | Kt | B_gap | T_maxwell | T_Magnet | P_ges |
|---|---:|---:|---:|---:|---:|
| 2 Magnete, 24 mm lang, 6 mm dick | 0,0270 | 0,413 | 0,00 | 125,8 | 5504 |
| 2 Magnete, **6 mm** lang | 0,0270 | 0,413 | 0,00 | 125,8 | 5504 |
| 2 Magnete, **60 mm** lang | 0,0270 | 0,413 | 0,00 | 125,8 | 5504 |
| 2 Magnete, **2 mm** dick | 0,0270 | 0,413 | 0,00 | 125,8 | 5504 |
| 2 Magnete, **35° geschrägt** | 0,0270 | 0,413 | 0,00 | 125,8 | 5504 |
| **4** Magnete, 24 mm | 0,0540 | 0,827 | 0,00 | 126,8 | 5217 |

**Länge, Dicke und Neigung bewegten nichts; allein die Anzahl bewegte alles, und
die genau linear.**

### 1. Der Anker las die parametrischen Felder

**Messung/Fundstelle.** `ema_analysis._analytical_Bgap` rechnete im
Innenläufer-Zweig `alpha_i = n_legs · geom["magWidth"] / pole_pitch · …` und
`perm = f(geom["magThick"])` — also mit den **parametrischen** Schemafeldern, die
bei einer gezeichneten Geometrie nichts über die Zeichnung aussagen. Der Wert ist
zugleich der Anker, an dem das FDM-Feld kalibriert wird; er trägt `Kt`, den Strom
und über ihn die Verluste.

**Was daran am schwersten wiegt:** der Magnetfeinschliff
(`ema_design_optimize`, Knopf „🎯 Magnete fein-optimieren") verschiebt
Magnetkoordinaten und bewertet mit genau diesem Bewerter — seine Zielgröße
änderte sich also nie, er optimierte nichts. Dasselbe traf die
Qualitäts-Vorsortierung der KI-Entwürfe (`ema_design_ai._quick_eval`), das
Auto-Label und damit die Zeilen im Trainingsdatensatz. Der Defekt hat sich
versteckt, weil das Werkzeug, das ihn aufgedeckt hätte, selbst blind war.

**Status: behoben.** Für `meta.code == "custom"` wird je Leg gerechnet:
`Σ perm(h_i) · (len_i / pole_pitch) · |sin(tilt_i)|`. Für lauter gleiche Legs ist
das exakt die alte Formel — die parametrischen Bauformen ändern sich um **keine
Stelle** (zehn Bauformen nachgemessen, `test_bewerter.py`). Die Neigung geht als
radiale Projektion der Magnetisierung ein, dieselbe, die `_orient_factor`
rechnet — damit trifft eine gezeichnete V-, VAsym- oder U-Geometrie ihren
parametrischen Zwilling jetzt **auf sechs Nachkommastellen**. Bei VV und Delta
bleibt eine Abweichung (28 % / 54 %), und das ist richtig: die parametrische
Fassung mittelt dort über zwei verschieden geneigte Lagen bzw. trägt einen
eigenen Beiwert für das tangentiale Deck.

**Was sich für bestehende Projekte ändert:** Designer- und KI-Entwürfe
(`magShape:"custom"`) bekommen ein anderes `B_gap`. Sie standen bisher auf einer
Zahl, die ihre eigene Zeichnung nicht kannte.

**Grenze, die bleibt:** die Formel ist damit *empfindlich* für die Zeichnung,
nicht automatisch *richtig* für jede denkbare Anordnung. `len_i/pole_pitch`
unterstellt, dass der Magnet zum Spalt hin wirkt. Die belastbare Aussage kommt
aus `feld2d`.

### 2. `T_maxwell` war überall 0,0 — und sah wie eine Messung aus

**Messung.** Die einzige Kennzahl aus dem **gelösten** Feld war in jedem Fall
0,00 Nm — auch in `results.json` echter Projekte, mit der Herkunft `fdm2d`
daneben. Ursache: `_sample_airgap` fittet die Tangentialkomponente auf zwei
Kreisen im aufgelösten Luftband und fällt auf **exakt null** zurück, wenn das Band
schmaler als 2,5 Bildpunkte ist. Nachgemessen an einer 280er-Maschine mit 0,7 mm
Spalt: das Band ist bei N=140 **0,0** und selbst bei N=800 nur **0,6** Bildpunkte
breit. `T_maxwell` war dort also immer null, bei jeder Gütestufe.

**Fundstelle.** `ema_analysis._sample_airgap` (`if r_out - r_in > 1.5`),
`ema_analysis.run_em_analysis` (Maxwell-Block).

**Status: behoben** — dieselbe Falle wie die 0,0 Nm der ASM: eine Null liest sich
wie eine Messung. `T_maxwell_Nm` ist jetzt **`None`** mit einer Begründung
(`T_maxwell_grund`) daneben, wo der Luftspalt im Raster nicht aufgelöst ist. Die
Verbraucher tragen es: Steckbrief zeigt „—", Trainingssatz lässt es leer, die
Lagerreibung rechnet mit 0, die Oberfläche ruft kein `toFixed` auf `null`. Die
Zielwertoptimierung stand als **Vorgabe** auf genau dieser Kennzahl — jetzt auf
`Kt`.

**Verworfen (gemessen, nicht vermutet):** ein zweiter, *belasteter* FDM-Lauf im
Schnellbewerter, um ein echtes Moment zu bekommen. Er kostet — und liefert
garantiert null, solange das Luftband unter 2,5 Bildpunkten liegt. Ein
aufgelöstes Band bräuchte für diese Maschine N ≳ 1250, das ist drei
Größenordnungen über dem, was ein Schnellbewerter kosten darf.

---

## 2026-09-08 — Der 230-V-Ventilatorantrieb: eine Kette aus drei Punkten

**Beobachtung.** Der Versuch, einen netzgespeisten Ventilatorantrieb zu rechnen
(1~230 V, rund 125 W, 24 Nuten, p=1, Rotor Ø 88,6 mm), lieferte kein Nein,
sondern Zahlen: `T_ist = 0,0 Nm` und daneben eine Verlustleistung von
**2,8·10²⁰ W**. Wer das liest, sucht den Rechenfehler. Der Befund war aber die
ganze Zeit „andere Maschinenklasse" — er wurde nur nirgends ausgesprochen.

Es ist **kein** Rechenfehler in dem Sinn, dass eine Formel falsch wäre. Es ist
ein Modell, das für seine Bezugsklasse geschlossen ist (umrichtergespeiste
Traktion, kW-Bereich, 86 Läufe in der Datenbank) und dem der Netzbetrieb
strukturell fehlt. Drei Stufen, jede für sich unauffällig:

### 1. Der Betriebspunkt ist im analytischen Modell nicht schaltbar

**Messung.** Für diese Geometrie braucht allein die Magnetisierung auf
B_m = 0,80 T einen Strom von **i_mag = 1686 A** (auf 1 Wdg/Nut bezogen, wie Kt).
Die Umrichter-Stromgrenze des Modells liegt bei **800 A**. Also
`i_q_max = √(800² − 1686²) = 0`, `T_ist = 0,0 Nm`, `strom_limit = True`.

**Fundstelle.** `ema_asm.betriebspunkt` (`ema_asm.py:468`),
`ema_asm.auslegungsstrom_stab` (`:435`), `ema_asm.magnetisierungsstrom`.

**Die 2,8·10²⁰ W sind das Symptom, nicht die Ursache.** `ema_asm.verluste`
skalierte das Statorkupfer mit `(I_s / max(i_q, 1e-9))²` — bei `i_q = 0` ist das
eine Division durch fast Null und liefert eine Zahl, die wie Physik aussieht.
Eine fehlende Klemme, keine Aussage über die Maschine.

**Status: behoben** (08.09.2026). `I_Q_MIN_ANTEIL` (`ema_asm.py:412`) ist eine
echte Schwelle — ein Tausendstel der Stromgrenze, nicht `1e-9`; darunter gibt
`betriebspunkt` `erreichbar: False` samt Begründung zurück und die abgeleiteten
Größen als `None`, nicht als 0,0. `verluste` und `dauermoment` rechnen dann gar
nicht erst. `ema_paarvergleich`, `ema_em2d_harm` und `cae_cli` drucken den Grund
statt einer Zahl.

### 2. Die 800-A-Grenze ist eine Vorgabe, kein Gesetz

**Messung.** `INVERTER_V_DC = 800.0` und `INVERTER_I_MAX = 800.0` stehen im Code
ausdrücklich als „Vorgabe, über geom änderbar" und sind seit dem 06.09.2026 über
`geom.inverterVdc` / `geom.inverterImax` einstellbar.

**Fundstelle.** `ema_analysis.py:111-112`, gelesen über `ema_analysis.umrichter`.

**Warum das trotzdem nicht reicht.** Für diesen Antrieb müsste dort der Strom
eines wirklichen Umrichters stehen — und einen gibt es nicht: die Maschine hängt
unmittelbar am Netz. Es fehlt also nicht ein Zahlenwert, sondern ein
**Betriebspunkt ohne Stromrichter** (feste Spannung, feste Frequenz, Schlupf
stellt sich ein).

**Status: benannt, nicht behoben.** `ema_referenz.GELTUNG["speisung"]` sagt
seit dem 08.09.2026 ausdrücklich, dass Netzbetrieb nicht modelliert ist, und
`geltung_pruefen` meldet es an Steckbrief, `sicherheit` und `beitrag`. Der
netzgespeiste Betriebspunkt selbst ist **eine neue Stufe, keine Reparatur** —
er wird hier nicht nebenbei gebaut.

### 3. Der 2-D-Lauf zeichnet einen Rotor, der das Spaltfeld nicht trägt

**Messung.** Die Käfignutbreite kommt aus dem analytischen `kaefig()` (7 mm), die
**Tiefe** wird aus dem benötigten Stabstrom abgeleitet. Ist der nach Punkt 1
null, greift still der Fertigungs-Bodenwert **2 mm** — heraus kommt eine breite,
flache Nut statt einer schmalen, tiefen. Der 2-D-Feldlauf misst daran ein
**Carter von 3,2** gegen die analytisch angenommenen **1,15** und ein
Leerlauffeld von **0,29 T** statt 0,80 T; das Moment fällt auf rund ein Siebtel
(0,07 Nm), selbst wenn Strom flösse. Das erklärt alle drei No-Load-Messungen
dieses Laufs — sie liegen alle gleich schief.

**Fundstelle.** `ema_asm.kaefig`, Bodenwert in `ema_asm.py:212`;
Verbraucher `ema_em2d_harm.harmonische_stufe` (`ema_em2d_harm.py:801`).

**Status: behoben** (08.09.2026). Ist der Auslegungsstrom null, meldet `kaefig`
`erreichbar: False` und `bemessung: "nicht auslegbar"`; `ema_em2d_harm`
weigert sich, daraus einen Rotor zu vernetzen, statt eine halbe Stunde Elmer an
eine Maschine zu hängen, die es nicht gibt.

### Was offen bleibt

Ein **netzgespeister Betriebspunkt ohne Stromrichter**. Das ist eine eigene
Stufe im Modell (Spannungs- statt Stromeinprägung, Schlupf als Unbekannte), kein
Justierstich an einer Grenze. Bis es sie gibt, ist die richtige Antwort auf eine
solche Maschine ein begründetes Nein — und das gibt das Werkzeug jetzt.
