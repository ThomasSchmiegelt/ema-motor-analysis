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

## 2026-10-23 (e) · Die Umbenennung einer Methode liess `guete` die halbe FEM nicht mehr sehen

**Beobachtung.** `test_db.py` wurde rot, nachdem `safety_factor_fem` von der
Methode `fem3d` auf das dimensionsoffene `fem` umgestellt wurde (2026-10-23 (b):
`kontakt_eben` rechnet eine EBENE Scheibe, und `fem3d` daran ist ein Etikett, das
nicht widerspricht und falsch ist). Die Umstellung war an EINER Stelle
mitgezogen — `importiere_projekt` schreibt Loeser, Netz und Status nur an
FEM-Kennwerte —, an der zweiten nicht.

**Messung.** `ema_db.guete` filtert `k["methode"] == "fem3d"`. Am Halbfall des
Tests (Feld gerechnet, Festigkeit nicht geliefert) fiel `fem_erwartet` damit von
**2 auf 1**, `fem_loeser` und `fem_aufloesung` auf den Rest. Das ist genau die
Zahl, an der ein Lauf OHNE Festigkeit von einem mit unterschieden wird — der
Zweck dieser Funktion.

**Fundstelle.** `ema_db.guete` (Vergleich auf eine Zeichenkette),
`ema_db.importiere_projekt`.

**Stand.** Behoben. `ema_db.FEM_METHODEN` ist die EINE Liste, beide Stellen lesen
sie, und `_METHODE_KURZ` benennt die neue Marke, statt sie als `fem` in die
Steckbrief-Tabelle zu schreiben. Nebenbei nachgetragen: `B_gap_last_T` und
`saettigung_engstelle` standen in **keinem** Register — der Test „alle
vorkommenden Kennwerte sind im Register" war deshalb schon vor diesem Stand rot.
Das erste ist nicht `B_gap_T`: jenes ist das Leerlauffeld der Magnete, dieses das
resultierende am Betriebspunkt, und die Saettigungsaussage haengt an diesem.

---

## 2026-10-23 (d) · Der MAGNETKÖRPER war im räumlichen Lauf nie aufgelöst — seine Spannung kam um Faktor 2 zu niedrig heraus

**Beobachtung.** Der ebene Lauf gab am Magneten konvergiert **16,4 MPa**
Hauptzugspannung (P99), der räumliche **7,18**. Faktor 2,3 ist zu viel, um es
durchgehen zu lassen — entweder rechnet einer von beiden falsch, oder einer ist
nicht aufgelöst. Nachgesehen: `ema_kontakt.baue` legt genau **ein**
Verfeinerungsfeld, eine Distance→Threshold auf die **Pad-Flächen** — und die
liegen auf der **Eisenseite**. Der Magnetkörper selbst blieb damit auf dem
Grundmaß: bei 6 mm Netz trägt ein 6 mm dicker Magnet etwa zwei Elemente über
seine Dicke. Ein C3D4 ist ein Element konstanter Dehnung, also das steifste,
das es gibt; zwei davon über die Dicke können die örtliche Biegung an einer
3-mm-Anlage nicht abbilden, und zu steif heißt **zu wenig Spannung**.

**Messung.** Dieselbe Geometrie, dieselben Anlagen, Anlagennetz konstant
1,25 mm — verfeinert wird **nur der Magnetkörper** (`mesh_magnet_mm`, neu):

| Magnetnetz [mm] | 6,0 (= Grundnetz) | 3,0 | 2,0 |
|---|---:|---:|---:|
| Elemente im Magneten | 33.153 | 64.768 | 172.932 |
| **Magnet Zug P99** [MPa] | 7,18 | 11,01 | **13,46** |
| Magnet Zug max [MPa] | 12,71 | 20,34 | 23,92 |
| Magnetvolumen [mm³] | 243.292 | 243.292 | 243.292 |
| Eisen P99 [MPa] | 219,5 | 219,8 | 219,8 |
| Eisen Mittel je Volumen [MPa] | 45,31 | 45,34 | **45,39** |
| ccx [s] | 309 | 344 | 528 |

**Die Kontrolle ist die wichtigere Hälfte der Messung.** Über die ganze Reihe
bewegt sich das Eisen um **0,18 %** (45,31 → 45,39), das Eisen-P99 um 0,14 %
und das Magnetvolumen um **keine Stelle** — die Verfeinerung tut also genau
das, was sie behauptet, und nichts sonst. Die Magnetzahl steigt dabei
**monoton um 87 %** (7,18 → 11,01 → 13,46) und läuft in die Richtung, die der
ebene Lauf unabhängig belegt. Damit ist die 2-D/3-D-Abweichung **erklärt**: sie
war Auflösung, kein Modellunterschied — und die Richtung war vorher bekannt,
denn ein zu steifes Element kann die Spannung nur unterschätzen.

**Was folgt, und das ist die eigentliche Auskunft.** Der räumliche Lauf kann
den Magneten **nicht bezahlbar** auflösen: bei 2 mm Magnetnetz stehen
172.932 Elemente im Magneten (5,2-fach) und 528 s auf der Uhr, und mit
13,46 MPa fehlen immer noch **18 %** zu den 16,4, die der ebene Lauf belegt.
Die Reihe ist bei 2 mm nicht konvergiert, nur unterwegs. Der ebene Lauf
erreicht die Zahl bei 10.672 Knoten in 6,6 s,
und dort ist sie **dreifach belegt** (CPE3 fein 16,50 · CPE6 grob 16,07 · CPS6
mittel 16,55 MPa — drei Wege, die sich in Elementgrad, Netz UND ebenem Zustand
unterscheiden, auf 3 %). **Für eine Aussage über den Magneten ist der ebene
Lauf also nicht die billigere, sondern die einzige belastbare Wahl.**

**Und die Vorgabe bleibt die alte** (`mesh_magnet_mm=None` = wie `mesh_mm`),
damit jeder gespeicherte Lauf Ziffer für Ziffer derselbe bleibt — nachgeprüft:
die Reihe bei 6,0 reproduziert die dokumentierten 219,5 / 45,31 / 12,71 / 7,18
und 158.676 Tetraeder exakt. Eine zu optimistische Zahl darf aber nicht
schweigend dastehen: `structural_fem.magnet.aufloesung` sagt es, das Protokoll
warnt, die Ergebniskarte zeigt es bernsteinfarben, und der Bericht führt die
Zeile „Vorbehalt zur Magnetspannung" **in** der Tabelle — nicht als Fußnote,
weil die Zahl sonst wie jede andere gerechnete daneben gelesen wird. Gemessen
heißt das SF **11 statt ~5**.

**Fundstelle.** `ema_kontakt.baue` (Constant-Feld auf die Magnetvolumen, über
`Min` mit dem Pad-Feld kombiniert), `ema_kontakt.KontaktNetz.netz_magnet_mm`,
`cae_cli.py struktur --mesh-magnet`, `ema_pipeline._struktur_kontakt`
(Warnung + `magnet.aufloesung`), `ema_report._single_md_tables`,
`oberflaeche/ergebnis.js`.

**Stand.** Behoben im Sinne von *messbar und benannt*. Nicht behoben ist die
Physik der Wahl: wer den Magneten räumlich rechnen will, zahlt dafür mit einem
Netz, das auf dieser Maschine nicht konvergiert (gemessen 18 % Rest bei 528 s
und 5,2-facher Elementzahl) — deshalb steht die Empfehlung auf dem ebenen
Lauf, und `konvergenz(3)["magnet_nicht_belastbar"]` sagt es an der Kennzahl.

---

## 2026-10-23 (c) · CalculiX meldet eine TEILLAST als Ergebnis — Exit 0, gültige `.frd`, Zahlen um Faktor 8 zu niedrig

**Beobachtung.** Beim Vermessen des ebenen Laufs 2. Ordnung kam bei 2,0/0,6 mm
Netz heraus:

```
dehnung 2  2.0/0.6  40.008 Knoten  FeMax 56,8  FeP99 27,9  MitV 6,24  MgP99 3,64
dehnung 2  3.0/1.0  21.799 Knoten  FeMax 459,0 FeP99 263,2 MitV 49,76 MgP99 16,07
```

Das **feinere** Netz lieferte ein Achtel der Spannung. `ccx` beendete sich mit
**0**, schrieb eine `.frd` mit gültigem DISP-Block und eine `.dat` mit
Elementspannungen — `ema_deck.loese_ccx` meldete deshalb `solver_status: "OK"`.

**Messung.** Die `.sta` des Laufs endet bei

```
     1         14     1U   15  0.136418E+00  0.136418E+00  0.325888E-04
```

also **Schrittzeit 0,136 von 1,0**. ccx halbiert das Inkrement, wenn die
Kontaktiteration nicht konvergiert, lief in das Inkrementlimit (`*STEP, INC=200`)
und gab auf — die Spannungen in der `.dat` gehören zu **13,6 % der Fliehkraft**.
Verhältnis der Mittelwerte 6,24/49,76 = 0,125, also genau die erreichte Last.
Die durchgelaufenen Läufe enden alle bei `0.100000E+01`.

**Warum das die gefährlichste Sorte Fehler ist.** Das Ergebnis ist der *Form*
nach vollständig plausibel: ein zusammenhängendes Spannungsfeld, Spitze an der
Anlagenkante, Magnet unter Zug, Blech unter Ringspannung — nur um den Faktor der
erreichten Last zu klein. Es sieht nicht wie ein Fehlschlag aus, sondern wie
eine **besonders gute Maschine**: Sicherheitsfaktor 12 statt 1,5. Ein Tor, das
auf dieser Zahl sitzt, winkt sie durch.

**Es betrifft nicht nur die zweite Ordnung.** `loese_ccx` ist der gemeinsame
Löseraufruf für `ema_deck`, `ema_kontakt` (räumlich und eben) und `ema_topopt`.
Bei einem *linearen Lauf ohne Kontakt* läuft der Schritt in einem Inkrement
durch, und die Lücke fällt nie auf — genau deshalb hat sie den Mehrkörperlauf
überlebt, der erst seit dem 22.10.2026 existiert.

**Offener Punkt, der daraus folgt.** Die räumliche Konvergenzreihe vom
22.10.2026 (c) wurde **ohne** diesen Wächter gemessen, und zwei ihrer Spalten
springen in genau dem Muster, das eine Teillast erzeugt: σ max
527,4 / 726,2 / 851,1 / **505,0** und Magnet Zug max
46,93 / 16,19 / **24,15** / 12,71. Als Singularität gedeutet ist das richtig
möglich — als Teillast aber auch, und die Rohdaten jener vier Läufe sind nicht
mehr vorhanden. **Die Reihe ist nachzumessen**, bevor jemand die Sprünge als
Eigenschaft des Netzes erklärt; `konvergenz(3)` nennt den Vorbehalt.

**Fundstelle.** `ema_deck.loese_ccx` (prüfte nur `.frd` + DISP-Block),
`ema_deck._ccx_schrittzeit` (neu, Spalte 6 der `.sta`).

**Stand.** Behoben. `loese_ccx` gibt `solver_status: "TEILLAST"` samt erreichtem
Anteil und dem Satz, dass die Spannungen kein Ergebnis sind; `schrittzeit`
reist bei JEDEM Lauf mit, auch bei den gelungenen. **Keine Auskunft ist kein
Fehlschlag** — nicht jeder Satz schreibt eine `.sta`, und ein Wert, den es nicht
gibt, darf keinen gültigen Lauf abweisen. Test: `test_kontakt.py` [4c].
Nebenbefund: damit ist auch gesagt, dass CPE6 am feineren Netz mit diesem
Kontakt **nicht rechenbar** ist — das steht in `grenzen(2)`, statt eine Zahl
daraus zu machen.

---

## 2026-10-23 (b) · Der ebene Lauf — und zwei Kennzahlen, die gegeneinander laufen

**Beobachtung.** Angemerkt wurde, dass sich der Mehrkörperfall auch
**zweidimensional** rechnen ließe. Das ist richtig, und zwar aus einem Grund,
der im Modell schon stand: der Lastfall ist planar (die Fliehkraft liegt im
Querschnitt), und der räumliche Lauf hält **beide Stirnflächen in z** fest —
das *ist* der ebene Verzerrungszustand. Die dritte Dimension kostet ~126.000
Tetraeder und trägt nichts bei, was die Scheibe nicht auch sagt.

**Messung (ebene Reihe, fünf echte Läufe, 12.000 1/min).**

| Netz (Grund/Anlage) [mm] | 6,0/1,25 | 3,0/1,0 | 2,0/0,6 | 1,5/0,4 | 1,0/0,3 |
|---|---:|---:|---:|---:|---:|
| Knoten | 3.061 | 5.947 | 10.672 | 17.256 | 34.391 |
| ccx [s] | 1,9 | 3,2 | 6,6 | 10,5 | 29,0 |
| σ **max** [MPa] | 358,2 | 368,4 | 399,4 | 429,0 | 475,6 |
| σ P99 **je Element** [MPa] | 237,6 | 235,3 | 220,4 | 215,8 | 212,5 |
| σ P99 **je Volumen** [MPa] | 181,8 | 173,9 | 185,3 | 189,2 | 197,3 |
| Mittel **je Volumen** [MPa] | 46,98 | 48,27 | 48,73 | 49,01 | 49,25 |
| Magnet Zug P99 [MPa] | 11,43 | 13,56 | 15,56 | 16,01 | 16,50 |
| Eisenvolumen [10⁶ mm³] | 1,740 | 1,740 | 1,740 | 1,739 | 1,739 |

Zum räumlichen Lauf am feinsten Netz (6/1,25): Mittel je Volumen **45,31**
gegen 49,25 MPa, Eisenvolumen 1,743 gegen 1,739·10⁶ mm³ (**0,2 %**) — die
unabhängige Gegenprobe, dass beide denselben Körper beschreiben. Rechenzeit
~286 s gegen 29 s.

**Der eigentliche Befund ist aber einer über die KENNZAHL.** Die beiden P99
laufen **gegeneinander**: der elementgewichtete fällt (237,6 → 212,5), der
volumengewichtete steigt (181,8 → 197,3). Der Grund ist derselbe, der 2026-10-22 (c)
schon für den *Mittelwert* notiert wurde, nur in der anderen Richtung: eine
Verfeinerung legt viele kleine Elemente in die heiße Zone, die damit
**übervertreten** ist, während das Volumen-Hundertstel die Spitze erst auflöst.
Dass die räumliche Reihe (2026-10-22 (c)) den elementgewichteten P99 als
„gesetzt" auswies, war deshalb zum Teil die **Aufhebung zweier Netzeffekte** —
mit vier Punkten und ohne die Volumengewichtung war das nicht zu sehen.
Belastbar ist die **Klammer** (am feinsten Netz 197…213 MPa), nicht eine der
beiden Zahlen; konvergiert ist das Mittel je Volumen (+0,5 % im letzten
Schritt).

**Und der ELEMENTGRAD bewegt das Gate stärker als das Netz.** CPE6 am groben
Netz (3,0/1,0) gegen CPE3 am selben Netz: σ P99 je Element **263,2** gegen
235,3 MPa, je Volumen 201,8 gegen 173,9, Mittel je Volumen 49,76 gegen 48,27.
Das Blech-P99 ist also keine konvergierte Größe — es hängt zum Teil an der
Singularität an der Anlagenkante, und ein besseres Element löst die **besser
auf** statt sie wegzurechnen; der Sicherheitsfaktor kippt dadurch von 1,54 auf
**1,29**, also über die Gate-Schwelle 1,3. Konvergiert sind das
volumengewichtete Mittel (1,5 % über beide Grade) und die **Hauptzugspannung im
Magneten**: CPE6 am groben Netz liefert 16,07 MPa, wofür CPE3 ein sechsfach
feineres Netz braucht (16,50) — zwei unabhängige Wege auf dieselbe Zahl.

**Zwei Fallen bei der zweiten Ordnung, beide gemessen.** (1) Gmsh projiziert die
Mittenknoten auf die Geometrie, und auf den gekrümmten Taschenkappen kippt dabei
ein Element um: ccx brach mit *nonpositive jacobian determinant in element 7760*
ab — das sah wie ein Kontaktproblem aus und war ein Netzproblem
(`Mesh.SecondOrderLinear = 1`). (2) Danach brach die **Kontaktiteration** nach
288 s mit *too many cutbacks* ab: die Mittenknoten einer quadratischen Kante
tragen eine andere Lastaufteilung als die Ecken. Mit
`TYPE=NODE TO SURFACE` konvergiert derselbe Fall in 13,4 s. Die beiden
Elementgrade rechnen damit **nicht denselben Kontaktalgorithmus** — das steht in
`grenzen(2)`.

**Fundstelle.** `ema_kontakt.baue_eben` (neu), `ema_kontakt.schreibe_inp`
(dimensions- und gradabhängig), `ema_kontakt._elvol` (ersetzt `_tetvol`:
Dreiecksfläche × Paketlänge, damit `kennzahlen` in beiden Dimensionen dasselbe
wiegt), `ema_kontakt.kennzahlen` (`stress_p99_vol_MPa`,
`magnet.hauptzug_p99_vol_MPa`, `volumen_magnet_mm3`),
`ema_kontakt.konvergenz(2)`, `ema_kontakt.grenzen(2)`.

**Stand.** Umgesetzt. Erreichbar als `struktur --solver kontakt --modell eben`
(mit `--ebener-zustand`, `--ordnung`), als `run analyse --set
struct_solver=kontakt_eben` und im Browser. Der ebene Weg aus dem Modul
reproduziert den Prototyp, an dem er gemessen wurde, **Ziffer für Ziffer**
(368,4 / 235,3 / 13,56 bei 3,0/1,0 und so für jeden Fall). Das Gate sitzt
weiterhin auf `stress_p99_MPa` — es zu verschieben hieße, jede gespeicherte
Zahl zu verschieben; die volumengewichteten Größen stehen **daneben**.

---

## 2026-10-23 (a) · `struct_solver` stand in keinem Schema — der Mehrkörperlauf war über `run analyse` nicht erreichbar

**Beobachtung.** `SKILL.md` und `CLAUDE.md` nannten beide den Weg
„`run analyse --set struct_solver=kontakt`". Den gab es nicht.
`cae_cli.apply_sets` prüft jeden `--set`-Schlüssel gegen `/param_schema` **und**
den Grundpayload und weist ab, was in keinem von beiden steht
(`cae_cli.py:578`, „steht weder im Schema noch im Grundpayload").
`struct_solver` stand in **keinem** von beiden: nicht in
`ema_text2ema.SCHEMA` und nicht in `frischer_payload()`. Der Agent konnte den
Mehrkörperlauf also nur über das *eigene* Verb `struktur --solver kontakt`
auslösen — nicht über einen Pipelinelauf, und damit nie mit Bericht, Steckbrief,
Ablage und `sicherheit` daran.

**Messung.** Nachgeprüft mit gestelltem Schema (Muster `test_cae_cli.py`):

```
struct_solver=kontakt   -> 'struct_solver' steht weder im Schema
                           noch im Grundpayload
```

Dieselbe Lücke wie beim Fahrzyklus (2026-09-06): ein Schlüssel, den die Pipeline
liest, aber kein Schema führt. Sie wiegt hier mehr als eine Gütestufe, denn
`struct_solver` wählt die **Physik** und nicht die Genauigkeit — verschmiert
gegen Mehrkörper unterscheidet sich am Tor gemessen um Faktor 1,9.

**Warum es nicht auffiel.** Die übrigen Rechenknöpfe (`fdm_resolution`,
`struct_mesh_mm`, `n_frames` …) stehen absichtlich in keinem Schema und werden
über `--guete entwurf|detail` gesetzt — das ist dokumentiert und richtig.
`struct_solver` sieht aus wie einer von ihnen und steht sogar in den
`GUETE`-Voreinstellungen (`ccx` bzw. `freecad`), also wirkte die Lücke wie
Absicht. Nur bietet `--guete` genau diese zwei Werte an; `kontakt` war über
keinen Weg wählbar.

**Fundstelle.** `ema_text2ema.SCHEMA["struct_solver"]` (neu),
`ema_text2ema.STRUKTUR_LOESER` (die eine Liste),
`ema_pipeline.run_pipeline` (liest sie jetzt von dort statt aus einem eigenen
Tupel), `server.py` `enum_opts["struct_solver"]` (lesbare Beschriftung).

**Stand.** Behoben. `--set struct_solver=kontakt|kontakt_eben` wird angenommen
und geprüft; ein erfundener Wert nennt die zulässigen. Die Liste steht **einmal**
— vorher als Tupel in `run_pipeline` und als `<option>`-Reihe in `ema.html`.

---

## 2026-10-22 (c) · Das Netz an den Auflagen war zu grob — und eine meiner Kennzahlen wanderte mit ihm

**Beobachtung.** Gefragt wurde, ob sich das Netz im Bereich der Auflagen feiner
auflösen lässt. Es ließ sich nicht: `ema_kontakt.baue` vernetzte mit **einer**
Zellgröße. Eine 3-mm-Anlagefläche trägt bei 6 mm Netz nicht einmal ein Element
in ihrer Breite — und genau dort sitzt die Spannungsspitze, um derentwillen es
den Mehrkörperlauf gibt.

**Messung.** Konvergenzreihe am frischen Payload (Grundnetz 6 mm, Anlagennetz
6 / 3 / 2 / 1,25 mm, 12.000 1/min, vier echte Kontaktläufe à ~5 min):

| Anlagennetz [mm] | 6,00 | 3,00 | 2,00 | 1,25 |
|---|---:|---:|---:|---:|
| Knoten | 26.214 | 35.366 | 44.149 | 50.277 |
| σ **max** [MPa] | 527,4 | 726,2 | 851,1 | 505,0 |
| σ **P99** [MPa] | 247,8 | 225,9 | 229,6 | 219,5 |
| Mittel **je Element** [MPa] | 57,40 | 52,27 | 51,27 | 46,28 |
| Mittel **je Volumen** [MPa] | 45,84 | 45,40 | 45,38 | 45,31 |
| Magnet Zug **max** [MPa] | 46,93 | 16,19 | 24,15 | 12,71 |
| Magnet Zug **P99** [MPa] | 8,43 | 7,63 | 7,14 | 7,18 |
| Eisenvolumen [10⁶ mm³] | 1,741 | 1,744 | 1,743 | 1,743 |

**Drei Befunde, und einer davon betrifft mich selbst.**

1. **σ max konvergiert nicht** — 527 → 726 → 851 → 505, es springt. An der
   Kante, wo die Anlage auf die Taschenwand trifft, ist die Spannung
   theoretisch unendlich; ein feineres Netz tastet nur näher an den singulären
   Punkt heran. Dieselbe Sorte Zahl wie das Rohmaximum an der Taschenecke, und
   ebenso wenig als Tor tauglich. Dasselbe am Magneten (46,9 / 16,2 / 24,2 /
   12,7).
2. **σ P99 setzt sich** — ab 3 mm bei 225 ± 5, von 3,0 auf 1,25 mm noch
   −2,8 %. Der **unverfeinerte** Lauf ist der Ausreißer: die Last hängt an ein
   bis zwei Elementen und treibt die Spannung künstlich hoch. Damit ist die
   Vorgabe `mesh_anlage = mesh/3` belegt und nicht geraten.
3. **`stress_mean_MPa` ist mesh-abhängig** (−19 % über dieselbe Reihe), weil er
   über **Elemente** mittelt und ein kleines wie ein großes zählt — die
   Verfeinerung legt viele kleine in einen kleinen Bereich. Das ist eine
   Eigenschaft der Kennzahl, nicht der Maschine: der **volumengewichtete**
   Mittelwert steht über dieselbe Reihe auf 45,3–45,8 MPa (**−1,2 %**). Das
   Eisenvolumen bleibt bei 1,74·10⁶ mm³ — die unabhängige Gegenprobe, dass alle
   vier Netze denselben Körper beschreiben.

**Fundstelle.** `ema_kontakt.baue` (eine Zellgröße), `ema_kontakt.kennzahlen`
(`stress_mean_MPa`), `ema_deck.kennzahlen` (bildet denselben Mittelwert).

**Status: behoben.** `baue(..., mesh_anlage_mm=…, saum_faktor=…)` verfeinert an
den Anlageflächen (Distance → Threshold auf ihren Flächen, Auslauf über
`saum_faktor · mesh_anlage` auf das Grundmaß — ein Sprung von 0,8 auf 6 mm auf
einer Elementkante gäbe entartete Tetraeder). Dafür musste die Flächensuche
**vor** das Vernetzen wandern (`_flaechen_suchen`); zweimal suchen wären zwei
Gelegenheiten, verschiedene zu finden. `stress_mean_vol_MPa` steht neben dem
alten Mittelwert (der bleibt, damit er mit `ema_deck` vergleichbar ist).
`konvergenz()` sagt in jedem Ergebnis, welche Zahl belastbar ist und welche
nicht; `test_kontakt.py` nagelt das fest, samt der Gegenprobe, dass sich das
Volumenmittel von hundert winzigen Elementen nicht kippen lässt (10,9 gegen
99,9 MPa).

**Offen:** `ema_deck.kennzahlen` bildet denselben elementgewichteten Mittelwert
für die drei anderen Löser. Dort ist er bisher nicht aufgefallen, weil diese
Netze gleichmäßig sind — aber die Kennzahl hat dieselbe Eigenschaft.

---

## 2026-10-22 (b) · Der Magnet liegt **nicht auf der ganzen Wand** an — und die Zeichnung hält ihn in Längsrichtung gar nicht

**Beobachtung.** Gefragt wurde:

> kannst du auch die magnete mit reinnehmen? das wäre dann aber eine
> Mehrkörpersimulation. In den Magnettaschen müssten dann auch kleine
> anlagefläche definiert werden, an denen die magnete partiell anliegen

Beides trifft zu. Der Vormittagsstand (`ema_magnetlast`) trägt die
Magnetfliehkraft als Knotenkräfte **gleichmäßig über die ganze Taschenwand**
auf. Das ist besser als nichts (vorher war die Last gar nicht da), aber es ist
nicht, was passiert: die Tasche ist um den Klebespalt größer als der Magnet, er
berührt sie nur dort, wo Blech ihn trägt.

**Messung 1 — was die Anlageflächen ändern.** Dieselbe Geometrie, dasselbe
Netzmaß (frischer Payload, 12.000 1/min, 6 mm), einmal verschmiert und einmal
als Mehrkörper mit Kontakt:

| | verschmiert | mit Anlageflächen |
|---|---:|---:|
| Eisen P99 (**das Gate**) | 127,5 MPa | **237,7 MPa** (×1,86) |
| Eisen Median | 46,0 MPa | 39,8 MPa (×0,87) |
| Rechenzeit | 3 s | 212 s |

Beides zusammen ist das Bild: die maßgebende Spannung **steigt**, weil dieselbe
Kraft durch rund ein Siebtel der Fläche geht (gemessen tragen die Anlagen
**14,1 %** der Taschenwand), und der Blechkörper als Ganzes wird **entlastet**,
weil die Magnete jetzt mittragen.

**Messung 2 — die rpm²-Linearität überlebt.** Das war die Frage, an der der Weg
hätte scheitern können: Kontakt ist eine nichtlineare Randbedingung, und die
ganze Nachbearbeitung dieser Kette (drei Betriebspunkte aus EINER Lösung,
Berstdrehzahl, Rampenvideo) ruht auf `σ ~ ω²`. Zwei Läufe bei exakt verdoppelter
Drehzahl:

| | 6.000 1/min | 12.000 1/min | Verhältnis |
|---|---:|---:|---:|
| Eisen Spitze | 131,84 MPa | 527,37 MPa | **4,0001** |
| Eisen P99 | 61,94 MPa | 247,75 MPa | **3,9998** |
| Eisen Mittel | 14,35 MPa | 57,40 MPa | **4,0000** |
| Magnet Hauptzug | 11,71 MPa | 46,93 MPa | **4,0077** |

Abweichung **0,19 %**. Der Grund ist benennbar und nicht Zufall: die Anlagen
liegen **spaltfrei** an, und die Fliehkraft kann sie nur zudrücken — der
Kontaktzustand ändert sich nie, und ein immer geschlossener Kontakt ist eine
lineare Kopplung. `ema_kontakt.linearitaetsprobe` fährt genau das nach; wer an
den Anlagen etwas ändert (Spalt statt Berührung), muss sie wiederholen.

**Messung 3 — der Magnet selbst.** Zum ersten Mal überhaupt sagt die Kette etwas
über ihn: größte Hauptzugspannung 46,9 MPa (P99 8,4) gegen ~80 MPa
Zugfestigkeit, SF 9,5. Dass er dabei 64,3 MPa **Vergleichsspannung** trägt, ist
nachrichtlich — ein gesinterter Magnet ist spröde und trägt auf Druck rund das
Dreizehnfache dessen, was er auf Zug trägt. Wer ihn über von Mises beurteilt,
beurteilt ihn mit dem Kriterium eines zähen Werkstoffs.

**Der eigentliche Befund steckt aber in der Geometrie.** Damit ein Kontaktmodell
überhaupt wohlgestellt ist, muss der Magnet gehalten sein. Nachgerechnet hält
ihn in seiner **Längsrichtung nichts**: die Taschenkappe ist ein Halbzylinder
vom Radius `dicke/2 + spalt`, der Magnet endet flach — zwischen Magnetstirn und
Kappenkuppe stehen am Beispiel **3,1 mm Luft**. Reibung reicht nicht: die
Längskomponente der Fliehkraft ist am V-Schenkel 0,747 davon, die Reibung an der
Flanke höchstens `µ · 0,664`, bei µ = 0,2 also 0,133. **Der Magnet rutscht**,
bis er irgendwo ansteht.

Das ist keine Modellierungsfeinheit, sondern eine Aussage über die gezeichnete
Maschine: *die Tasche positioniert den Magneten in Längsrichtung nicht.* In der
Wirklichkeit hält ihn die Klebung — eine Klebung, die bei 17,5 kN je Magnet
nirgends in dieser Kette nachgewiesen wird.

**Fundstelle.** `ema_topology` (Taschenkappe), `ema_freecad`
(build_full_motor_script, obround pocket), `ema_magnetlast` (verschmierte Last).

**Status: gebaut als eigener Weg, nicht als neue Vorgabe.** `ema_kontakt.py`,
`struct_solver="kontakt"`. Eisen und Magnete sind getrennte Körper (bewusst
**nicht** fragmentiert, damit an der Berührfläche doppelte Knoten entstehen —
ein konformes Netz wäre eine Verklebung, die auch Zug überträgt). Die Anlagen
sind Parameter (`anlageBreiteMm`, `anlageProFlanke`, `anlageEndeMm`,
`anlageReibung`) und als **Entwurfsannahme** gekennzeichnet. Dazu das Kriterium
`magnetbruch` in `ema_sicherheit`, das Mehrkörper-Schnittbild mit **zwei**
Farbskalen (Blech 248 MPa gegen Magnet 8,4 MPa — auf einer Skala wäre der Magnet
schwarz wie Luft) und `test_kontakt.py` (18 Prüfungen ohne Löser, `--echt`
rechnet zwei Läufe und fährt die Linearitätsprobe).

**Offen und ausdrücklich benannt:** der **Endanschlag** ist Eisen in der
Luftkappe und nimmt am Beispiel **31 %** davon ein — das Feldmodell dieser Kette
weiß davon nichts (`ema_topology` zeichnet keine Anlagen). Wer ihn baut, hat dort
einen magnetischen Nebenschluss, den niemand rechnet; wer ihn wegläßt
(`anlageEndeMm = 0`), hat einen Magneten, den nur Reibung hält. Ebenfalls offen:
die Klebung trägt im Modell nichts, der Reibbeiwert 0,2 ist eine Annahme, und
E/ν/Festigkeiten des Magneten sind Literaturgrößen der Werkstoffklasse
(`MAGNETS[...]["mech_beleg"] == "annahme"`), keine Messung.

---

## 2026-10-22 · Die Struktur-FEM rechnete die Magnete **nicht mit** — und am Steg sind sie der größere Posten

**Beobachtung.** Gemeldet als:

> ich möchte die fem berechnung vertiefen. die gewichte der magnete sollen auch
> berücksichtigt werden. auch die darstellung der FE Analyse gefällt mir nicht.

Beide Hälften stimmten. `ema_freecad.build_rotor_fem_script` vernetzt
ausdrücklich **nur das Rotoreisen** („the magnets must NOT be part of the
centrifugal FEM") und lädt es mit `*DLOAD CENTRIF` — einer Volumenkraft über die
Dichte des **Blechs**. Die Magnettaschen sind in diesem Modell Luft. Gerechnet
wurde also die Fliehkraft des Eisens und **keine einzige Newton** der Magnete,
obwohl der Magnet das schwerste Einzelteil im Läufer ist und sein ganzes Gewicht
an der dünnsten Stelle hängt, die es dort gibt. Dasselbe im eigenen Rechensatz
(`ema_deck.baue` schneidet die Taschen als Löcher, `zentrifugal_lasten` kennt nur
`dichte_kg_m3` des Blechs).

**Warum es nicht auffiel.** Beide Vergleichswerte teilen den Fehler: die
analytische Ringspannung (`ema_rotorcheck._bore_hoop_mpa`) ist die eines
**glatten** rotierenden Ringes, und `KT_POCKET = 1.5` darüber ist ein Kerbfaktor
für die scharfe Taschenecke — kein Zuschlag für eine zusätzliche Last. Das
Tier-2-Tor verglich also eine Spannung ohne Magnete mit einer Spannung ohne
Magnete, und die FEM bestätigte sie. `ema_radien.magnethaltung` nennt den
Blechsteg seit jeher „das bindende Bauteil" — gerechnet hat die Last auf ihn
niemand.

**Messung 1 — die Größenordnung** (frischer Payload, V-Form, 2p = 6, Läufer
Ø 188,6 mm, L = 80 mm, Magnet 42,2 × 6,0 mm, Schwerpunkt r = 72,9 mm, NdFeB):

| Drehzahl | je Magnet | je Pol | alle Pole |
|---|---:|---:|---:|
| 12.000 1/min | 17,5 kN | 35,0 kN | 210,1 kN |
| 20.000 1/min | 48,6 kN | 97,3 kN | 583,7 kN |

Der Steg darunter ist `ema_topology.BRIDGE_MM` = **1,3 mm** breit. Zwei davon je
Pol tragen bei L = 80 mm zusammen 208 mm²; 35 kN darauf sind **168 MPa** neben
einer Ringspannung von **93,6 MPa** bei derselben Drehzahl. Die vergessene Last
ist also kein Zuschlag, sondern der **größere** Posten an der bindenden Stelle.

**Messung 2 — was die FEM damit anders sagt.** Dieselbe Geometrie
(`smoke_test.GEOM`, 16.000 1/min, Netz 4 mm, 307.000 Tet4), einmal ohne und
einmal mit der Magnetlast, sonst Zeichen für Zeichen derselbe Lauf:

| | ohne Magnetlast | mit Magnetlast | Faktor |
|---|---:|---:|---:|
| σ_v Rohmaximum | 2983,8 MPa | 4311,3 MPa | ×1,44 |
| **σ_v P99 (das GATE)** | **582,0 MPa** | **893,0 MPa** | **×1,53** |
| u_max | 108,9 µm | 157,1 µm | ×1,44 |

Am Vorgabe-Payload bei 12.000 1/min fällt die maximale sichere Drehzahl dadurch
von 12.000 auf **9951 1/min** (SF_FEM 0,89 statt bestanden). **Jedes gespeicherte
Projekt mit eingelassenen Magneten ist davon betroffen** — seine
`safety_factor_fem` und `max_safe_rpm` sind ohne diese Last entstanden und mit
den neuen nicht vergleichbar.

**Zweiter Befund, beim Rechnen gefunden: die Magnetdichte stand an zwei Stellen
und in der Werkstofftabelle gar nicht.** `ema_screen.MAG_DICHTE_KG_M3` = 7600,
`ema_thermal` = 7500 als Literal, `MAGNETS` ohne `density`. Damit war **Ferrit
genauso schwer wie NdFeB**, obwohl es rund 35 % leichter ist — und seit die
Magnetmasse über eine Spannung entscheidet, ist das keine Frage der Stückliste
mehr. Gemessen am frischen Payload: Magnetmasse Ferrit 1,849 → **1,192 kg**,
Kosten 102 → 66 €; NdFeB N35 1,849 → 1,825 kg (7600 → 7500).

**Fundstelle.** `ema_freecad.build_rotor_fem_script` · `ema_deck.schreibe_inp` ·
`ema_rotorcheck.rotor_stress_check` · `ema_screen.MAG_DICHTE_KG_M3` ·
`ema_thermal.compute_capacities`.

**Status: behoben.** Neu `ema_magnetlast.py` als die eine Quelle: die
Fliehkraft jedes eingelassenen Magneten wird exakt in die Taschenbasis zerlegt
(Flanke + Endkappe, Vektorsumme = Fliehkraft) und als **Knotenkräfte** auf die
Wandknoten gelegt — in allen vier Lösern dieser Kette (CalculiX über
`*CLOAD`, Z88 über `Art 1`, Code Aster über `FORCE_NODALE` auf einer
`GROUP_NO`). Nur in einem von ihnen wäre schlimmer als in keinem: der
Löservergleich nennt die Differenz sonst eine Löserabweichung. Der
Knotenauswahl-Kern steht **einmal** (`ema_magnetlast.KERN`, per `exec` geladen
und wörtlich ins FreeCAD-Skript geschrieben), die Dichte je Sorte in `MAGNETS`.
Dazu der analytische Richtwert `stegspannung` (mit benannter Annahme über die
Zahl der tragenden Stege), das Kriterium `magnetsteg` in `ema_sicherheit`
(Schwere `hinweis`, denn ein Richtwert darf kein Tor schließen) und die Zeile im
`rotor-check`. Test: `test_magnetlast.py`.

**Offen geblieben, ausdrücklich:** Käfigstäbe, Ankerwicklung und Erregerspulen
tragen dieselbe Lücke in ihren eigenen Bauteilen (ihre Prüfungen
`ema_asm.steg_check` / `ema_schenkelpol.befestigung` rechnen die Masse, die
Struktur-FEM nicht); die Klebung gilt als nicht tragend; und der **Schrumpfsitz**
bringt eine Ringvorspannung mit, die `connection_assessment` analytisch rechnet
und die FEM nach wie vor nicht sieht.

---

## 2026-10-22 · Die FE-Darstellung war eine Punktwolke, keine Schnittfläche — und zeigte die falsche Größe

**Beobachtung.** Zweite Hälfte derselben Meldung („auch die darstellung der FE
Analyse gefällt mir nicht"). `ema_pipeline._render_deform_single` zeichnete
`ax.scatter(xs, ys, c=um, s=3)` — **alle** Knoten des Volumennetzes, auf die
xy-Ebene projiziert.

**Messung.** Drei Mängel, jeder einzeln ausreichend:

1. **Projektion statt Schnitt.** Über die ganze Paketlänge liegen die Knoten
   übereinander; sichtbar ist der zuletzt gezeichnete. Die Magnettaschen — die
   Stelle, auf die es ankommt — sind von Stirnflächenknoten zugedeckt und als
   Löcher nicht erkennbar.
2. **Falsche Größe.** Gezeigt wurde die **Verschiebung** (am gemessenen Lauf
   28,6 µm). Die Vergleichsspannung lag im `.frd`, wurde geparst (`_stress_vm`)
   und in **kein** Bild gezeichnet.
3. **Es sah aus wie ein Netz und war keines.** Genau diese Verwechslung steht
   schon im Kopf von `_render_deform_analytical` („got mistaken for a mesh");
   dort wurde sie für den analytischen Rückfall behoben, für das **echte**
   FEM-Ergebnis blieb die Punktwolke stehen.

Dahinter lag der eigentliche Grund: `_parse_frd_full` las Knoten, Verschiebungen
und Spannungen — aber **nicht die Elementtabelle**. Ohne Knotenverbindungen gibt
es keine Fläche, keinen Schnitt und kein Loch an der Stelle der Tasche. Der Block
steht in jeder `.frd` (`    3C`), er wurde nur übersprungen.

**Fundstelle.** `ema_pipeline._render_deform_single` · `_parse_frd_full`.

**Status: behoben.** `_parse_frd_full` liest die Elemente mit; neu
`ema_struktbild.py` schneidet das Tetraedernetz bei halber Paketlänge (je
Tetraeder das Schnittpolygon aus den Kantenschnittpunkten, Feldwert entlang der
Kante interpoliert) und zeichnet **drei** Größen statt einer: Spannung,
**Sicherheit** (R_e/σ, mit roter SF-1-Marke) und Verformung, jede bei Nennlast /
Maximaldrehzahl / Berstdrehzahl. Gemessen am Beispiellauf: 7050 Schnittflächen,
0,3 s für den Schnitt, der über alle neun Bilder **einmal** gerechnet und nur
skaliert wird. Die Farbskala hängt am 99,5. Hundertstel und nicht am Maximum —
das sitzt an einer scharfen Taschenecke und ist eine Gitter-Singularität
(gemessen 4311 MPa Rohmax gegen 893 MPa P99 am selben Lauf); daran skaliert wäre
das halbe Blech schwarz. Das Rampenvideo läuft über denselben Schnitt, sonst
zeigten Video und Standbild desselben Laufs zwei Darstellungen derselben Zahlen.
Ohne Elementtabelle bleibt die Punktwolke und **sagt es im Untertitel**.

---

## 2026-10-17 · Die Eingaben entstanden erst am Lauf**ende** — 224 von 369 Projekten haben keine

**Beobachtung.** Gemeldet als:

> ich hbae das gefühl das die geometrie bei den maschinen nicht abgespeichert
> wird. immer wenn ich ein gepichertes projekt aufrufe, erscheint der default
> geometrie stand.

**Messung.** `meta.json` — und damit `meta["payload"]`, aus dem
`/project/<id>/template` das Formular wiederherstellt — wurde ausschließlich im
Speicherblock am **Ende** von `run_pipeline` geschrieben
(`ema_pipeline.py`, „Persist project metadata + results to disk"). Gezählt über
`~/cae_projekte`:

| | Zahl |
|---|---:|
| Projektordner | 369 |
| **ohne `meta.json`** | **224** (61 %) |
| davon mit Eingaben in `project.json` (`inputs.payload`) | **0** |

Das heißt: für knapp zwei Drittel aller Projekte ist die Geometrie **nicht
wiederherstellbar**, und sie war es nie — `/template` antwortet dort
`{"payload": {"geom": {}}, "reconstructed": true}`, `applyPayload` schreibt
nichts, und die Maske zeigt ihre Vorgaben. Genau das ist der gemeldete
„Default-Geometriestand".

Betroffen ist jeder Weg, der den Speicherblock nicht erreicht: eine gerissene
Stufe 0, ein Fehlschlag in FreeCAD oder im Löser, ein Abbruch, ein
Serverneustart — und der häufigste Fall, die **reine CAD-Vorschau**
(`build_cad_preview` hat keinen Speicherblock; 47 der 224 Ordner heißen
`*_cad_vorschau`). `ema_projekt.init` legt `project.json` von Anfang an, aber
`inputs.payload` füllt erst `record_run`, also ebenfalls erst am Ende.

**Fundstelle.** `ema_pipeline.run_pipeline` (Speicherblock), `build_cad_preview`
(keiner), `ema_projekt.record_run`.

**Status: behoben.** `ema_pipeline.eingaben_sichern(proj, data, state)` legt
`meta.json` mit dem Eingabepayload ab, **bevor** irgendetwas gerechnet wird —
gerufen in `run_pipeline` (vor den Toren, also auch wenn eines reißt) und in
`build_cad_preview`. Eine vorhandene Datei wird **ergänzt, nicht ersetzt**
(nach einem gerechneten Lauf trägt sie Werkstofflabel und `rpm_range`, und das
darf ein späterer Vorschauklick nicht wegnehmen); `results.json` entsteht dabei
ausdrücklich nicht, damit „Eingaben da, nichts gerechnet" weiterhin an dieser
Datei ablesbar bleibt. Im Teil-Nachrechnen wird nicht vorab geschrieben: dort
liegt der Payload per Definition schon da, und ihn vor einem möglichen
Fehlschlag durch den halb eingestellten zu ersetzen wäre eine
Verschlechterung. `record_run` diffe weiter gegen
`project.json`s `inputs.payload` — die wird absichtlich **nicht** vorab gesetzt,
sonst wäre `changed_inputs` jeder Evolutionsstufe leer.

**Was NICHT behoben ist:** die 224 Altprojekte. Ihre Eingaben stehen in keiner
Datei (nachgeprüft: weder `meta.json` noch `inputs.payload` noch `datasheet`),
sind also nicht rekonstruierbar. Wo `motor.FCStd` liegt, ließe sich die
Geometrie *messen* (`ema_step_import.derive_geom` tut das für STEP) — das wäre
eine eigene Arbeit und steht hier als offener Punkt, nicht als Zusage.

---

## 2026-10-17 · Die Scheibenbilder waren Leerlaufbilder mit „Last" darüber — die Eichung fehlte

**Beobachtung.** Beim Nachmessen für die beiden fehlenden Feld-Darstellungsarten
(Befund darunter) gefunden, nicht gemeldet: `ema_axial_fdm.frames` und
`schnitt_figur` lösten **selbst**, auf der rohen Summe
`j_magnet + j_anker`, und zeichneten `|rot A|` daraus.

**Messung.** Die beiden Anteile brauchen Eichfaktoren, die um Faktor **1343**
auseinanderliegen — `schnitt` rechnet sie längst getrennt aus (dieselbe
Aufteilung, aus der radial `run_em_analysis` seine Magnet- und Ankereichung
bezieht):

| | Eichfaktor |
|---|---:|
| Magnet (`sf_m`) | 1,188·10⁻⁶ |
| Anker (`sf_a`) | 1,596·10⁻³ |

Roh addiert trägt der Anker damit ein Tausendstel seines Gewichts. Gemessen am
Projekt `20261016_203313_261016` (torus_nn, 2p = 8, 100 Nm):

| | roh (bis 17.10.) | geeicht |
|---|---:|---:|
| \|B\| p98, Leerlauf → Volllast | 1 864 997 → 1 865 108 (**+0,006 %**) | 2,216 → 2,507 T (**+13 %**) |
| Spaltspitze `b_n_spitze_T` | — | 1,384 → **2,486 T** (+80 %) |

Die Animation zeigte also den Leerlauf, auch wenn „Last" im Titel stand — und
eine Last-Rampe darauf wäre eine Reihe gleicher Bilder gewesen.

**Fundstelle.** `ema_axial_fdm.frames`, `ema_axial_fdm.schnitt_figur` (eigener
`_solve_fdm`-Lauf auf `j_magnet + j_anker`), gegen `ema_axial_fdm.schnitt`
(getrennte Eichung).

**Was es kostet, und das wird gesagt:** die Eichung braucht einen zweiten
Löserlauf je Bild — den **nutlosen** Begleitlauf, an dessen Spitze geeicht wird
(`schnitt`, Eichung `spitze_nutlos`). Sein `mu` ist ein anderes, also hilft der
LU-Cache dort nicht, während der Ankerlauf sich die Faktorisierung des
Magnetlaufs teilt. Gemessen ohne das Zeichnen: **166 → 331 ms je Bild bei
N = 200, 507 → 1007 ms bei N = 300, also Faktor 2,0.** Die Entwurfsvoreinstellung
(12 Bilder) kostet damit ~4 s statt ~2 s; das ist der Preis dafür, dass im Bild
die Last zu sehen ist.

**Status: behoben.** `schnitt(..., bilddaten=True)` gibt die **geeichte** Summe
`A`/`bx`/`by` heraus und ist damit die eine Quelle für Kennwerte UND Bild;
`frames` und `schnitt_figur` lösen nicht mehr selbst. Opt-in, weil `felder`
den Schnitt k-mal aufsammelt und drei `(N, N)`-Felder je Schnitt sonst in
`results.json` landen würden. Die Einzelbild-Vorschau (`/preview_field`) hängt
an `schnitt_figur` und ist mitbehoben.

---

## 2026-10-17 · Ankerrückwirkung und Last-Rampe: angehakt, nicht gerechnet, nichts gesagt

**Beobachtung.** Gemeldet als:

> bei der axialflussfaschine kann ich kein drehzahlband im fdm solver rechnen
> auch wird das „Feld-Darstellung (Rotor-Rotation immer aktiv):
> Ankerrückwirkung (Rotor steht, Stromwinkel β) / Last-Rampe (Rotor steht,
> Last 0→Volllast)" nicht gerechnet.

**Messung.** Beides stimmt, und zwar aus zwei verschiedenen Gründen.

*(1) Die beiden Darstellungsarten.* `ema_pipeline` führt die drei Modi als
`field_modes`; ihre Schleife steht zweimal als
`for mode in (field_modes if not _axial_lauf else [])`. Beim Axialfluss waren
die Haken also wirkungslos — **ohne eine Zeile im Protokoll**, und
`results["em"]["field_modes"]` trug nur `rotate`. Anhaken, warten, und ein
Ergebnis bekommen, das von dem ohne Haken nicht zu unterscheiden ist.

Darstellbar sind sie, und das war von Anfang an so: `rastere_scheibe` baut den
Strombelag aus `iq` **und** `id_` auf (`id_*cos(el) - iq*sin(el)`) — der
Stromwinkel steckt dort längst, es hat ihn nur niemand durchgefahren.

*(2) Das Drehzahlband.* Hier ist „geht nicht" die richtige Antwort, und sie ist
gemessen. `ema_axial_fdm.betriebspunkt` hat **keinen Drehzahlterm**: es rechnet
`i_q = T/Kt`, setzt `i_d = 0` (Oberflächenmagnete, keine Salienz, MTPA ist
i_d = 0) und prüft **keine Spannungsgrenze**. Am Projekt
`20261016_203313_261016` bei 100 Nm:

| Drehzahl [1/min] | 500 | 1 000 | 3 000 | 6 000 | 12 000 | 30 000 |
|---|---:|---:|---:|---:|---:|---:|
| i_q [A] | 489,828 | 489,828 | 489,828 | 489,828 | 489,828 | 489,828 |
| i_d [A] | 0 | 0 | 0 | 0 | 0 | 0 |

Ziffer für Ziffer derselbe Strom — obwohl die Eckdrehzahl dieser Maschine bei
**12 920 1/min** liegt (`ema_analysis.eckdrehzahl`), oberhalb also
Feldschwächung einsetzen MUSS. Eine Bildreihe über das Band wäre damit *n*
gleiche Bilder, und das ist schlimmer als keine: sie sieht nach einer Messung
aus.

**Fundstelle.** `ema_pipeline` (die beiden `if not _axial_lauf`-Schleifen),
`ema_axial_fdm.betriebspunkt` (kein `rpm` im Rumpf außer in der Signatur).

**Status: zur Hälfte behoben, zur Hälfte offen.**
* `ema_axial_fdm.frames(..., art=…)` rechnet jetzt alle drei Arten
  (`ARTEN_BILD`), auf **einer** Lösung, **einer** Eichung und **einer**
  festgehaltenen Farbskala; `_bildpunkte` liefert je Art nur die drei Zahlen je
  Bild (iq, id, Winkel). Die Pipeline fährt sie in die Unterordner
  `frames`/`frames_react`/`frames_load`, also durch dieselben Routen
  (`/field/<mode>/<n>`, `/project/<id>/video/<mode>`) wie radial. Ohne Last
  gibt es **keine** Bildreihe und dafür den Grund (`grund`), statt *n* gleicher
  Bilder.
* Die **Feldschwächung der Scheibe** bleibt offen. Sie nachzutragen heißt, eine
  Spannungsgrenze und damit `i_d < 0` oberhalb der Eckdrehzahl einzuführen —
  das verschiebt jeden Strom, jeden Verlust und jede Temperatur jedes
  Axialprojekts und ist keine Nebenbei-Änderung. Bis dahin steht der Grund am
  Haken (`#fm_axial_hinweis` in ④ Berechnung) und im Protokoll des Laufs,
  statt dass das Band stillschweigend nichts tut.

---

## 2026-10-17 · Der schnelle Bewerter rechnete für alle fünf Maschinenarten dieselbe Maschine

**Beobachtung.** Gefragt als:

> parameterstudien habe ich nicht überprüft. greifen die parameterstudien auch
> bei reluktanz, synchronmaschine, gsm und eesm?

Sie griffen — und gaben für jede Bauart die Kennwerte einer PSM aus.

**Messung.** `ema_optimize._eval_geom` ist der gemeinsame Bewertungskern von
Parameterstudie, Zielwertsuche, Magnet-Feinoptimierer, `screen`, `leistung`,
`ausreizen` und der Vorsortierung der KI-Entwürfe. Er enthielt **null** Treffer
auf `machineType`. Am frischen Payload, nur `geom.machineType` umgestellt:

| Art | `_eval_geom` Kt | B_gap | Betriebspunkt der Art (Kt) | B_gap | Quelle |
|---|---:|---:|---:|---:|---|
| PSM | 0,0410 | 0,630 | 0,0410 | 0,630 | `fdm` |
| ASM | 0,0410 | 0,630 | **0,0520** | 0,800 | `ema_asm` |
| SynRM | 0,0410 | 0,630 | **0,0180** | 0,283 | `ema_synrm` |
| EESM | 0,0410 | 0,630 | **0,0520** | 0,800 | `ema_eesm` |
| GSM | 0,0410 | 0,630 | **0,0968** | 0,800 | `ema_gsm` |

Fünfmal Ziffer für Ziffer dasselbe. Beim Reluktanzläufer lag die Studie damit um
Faktor **2,3 zu hoch**, bei der Gleichstrommaschine um **2,4 zu niedrig** — und
man sah es nicht, denn eine Kurve mit falschem Niveau sieht aus wie eine Kurve.

Die Ursache ist dieselbe wie am 20.09.2026 eine Etage tiefer im Rasterer:
`run_em_analysis` eicht seine Amplitude auf `_analytical_Bgap`, und die rechnet
aus `Br_NdFeB` und `magThick`. Die Pipeline hat dafür seit jenem Tag
`_perf_der_art`; dieser Bewerter rief sie nicht.

**Zweiter Teil: das Tor der Maschinenart fehlte ebenfalls.** `_baubar` rief
`rotor_layout_check` — die Prüfung der **Magnettaschen**. Ein Käfig-,
Schenkelpol- oder Ankerläufer hat keine, also war `baubar = True` dort eine
Aussage über etwas, das es nicht gibt: leer bestanden. Genau dieser Fehler stand
am 19.09.2026 schon einmal in `cae_cli.py rotor-check`.

**Fundstelle.** `ema_optimize._eval_geom`, `ema_optimize._baubar`;
`ema_pipeline._perf_der_art` und `ema_pipeline._gate_laeufer` als die
vorhandenen, nicht gerufenen Gegenstücke.

**Status: behoben, mit einer benannten Grenze.** `_eval_geom` ruft
`_perf_der_art` — **sie**, nicht eine zweite Fassung daneben — und führt
`perf_quelle` in den Kennwerten mit; `_baubar` ruft `_gate_laeufer` mit
`rpm_to` (ohne die Drehzahl rechnet das Tor die Polbefestigung gar nicht, und
ein 2×M6-Schenkelpol ging im ersten Anlauf als „baubar" durch). Kosten ~1,5 ms
je Punkt neben einem FDM-Lauf. Gegengeprüft: bei 20 000 1/min weist der
Bewerter den Schenkelpol jetzt mit 467,7 kN je Pol ab (SF 0,16 statt 1,3) und
die GSM mit 128,4 m/s Umfangsgeschwindigkeit gegen 40 m/s. Die PSM bleibt
Ziffer für Ziffer unberührt (`quelle = "fdm"`).

**Was NICHT mitwandert, und das steht in `perf_quelle`:** Verluste und
Temperaturen kommen weiter aus `ema_thermal` auf dem PSM-Weg
(Magnetwirbelstrom statt Käfig-, Erreger- oder Bürstenverlust), und der Strom
aus `estimate_dq_currents` (PSM-MTPA) statt aus `ema_asm.betriebspunkt`s
`hypot(i_mag, i_q)`. Für die ASM fehlt damit der Magnetisierungsstrom in
`P_total`, für die GSM der Bürstenabfall (am gemessenen Auslegungspunkt
**1488,6 W gegen 793,9 W** Ankerkupfer — also der größere Posten). Das ist der
nächste Schritt und keine Zusage.

**Nebenbefund.** Der GSM-Zweig von `_gate_laeufer` wirft noch nacktes
`RuntimeError` (Ankerwicklung, Kommutator, Kommutierung), während alle anderen
Zweige längst `AuslegungReisst` mit gerechneten Entlastungswegen werfen — die
Kette aus `server._run` → `e.wege` → Knöpfe in der Oberfläche bedient die
Gleichstrommaschine deshalb nicht. `_baubar` liest beide Formen als Nein; der
Umbau des Zweigs selbst steht offen.

---

## 2026-10-16 · Der Axialfluss-Reiter rechnete bei jedem Tastendruck — 207 ms gegen 1,2 ms Zeichnen

*Nachgetragen am 17.10.2026: behoben war das mit `f19d1be`, aber weder hier noch
in `CLAUDE.md` festgehalten — und ein Befund, der nur in einer Commit-Meldung
steht, ist für den nächsten Leser nicht vorhanden.*

**Beobachtung.** Gemeldet als „das Aendern der Werte im Tab Axialfluss geht sehr
zaeh", dazu die doppelte Absage beim Drehzahlband.

**Messung.** Der Kommentar an der Aufrufstelle sagte, das Feld werde „nur auf
Zuruf" gerechnet, „sonst haengt die Maske bei jedem Tastendruck" — nur **ist**
der Zuruf das Häkchen `feldAn`, und das steht per Vorgabe an. `zeichne()` hängt
an `input` jedes Feldes, also lief bei jedem Zeichen ein voller CG-Lauf.

Gemessen am Vorgabe-Entwurf (ny = 110, 132×110 = 15 312 Zellen, Magnetlauf +
nutloser Eichlauf):

| | Leerlauf | unter Last |
|---|---:|---:|
| ny = 110 | **207 ms** | 235 ms |
| ny = 160 | 387 ms | — |
| ny = 220 | 1000 ms | — |

Alles andere in `zeichne()` zusammen kostet gut eine Millisekunde (mit gezählten
Canvas-Aufrufen: Draufsicht 1,05 ms bei 867 Aufrufen, Halbschnitt 0,07,
Abwicklung 0,06, Tabelle 0,04) — **Verhältnis 170 : 1**, also genau eine Stelle
zu heilen. Eine dreistellige Zahl zu tippen kostete ~0,6 s stehende Oberfläche,
ein gezogener Regler feuert laufend.

**Fundstelle.** `axialfluss/ansicht.js`, `zeichne()` → Feldlauf an `input`.

**Status: behoben** (`f19d1be`), nach dem Muster einer Ebene tiefer
(`rzAnstossen` beim Mehrschnitt): `feldMarke` merkt, woran das Bild hängt
(`rs` gehört dazu, `rzN` und `theta` nicht — der Winkel liest nur ab),
`feldAnstossen` entprellt mit `FELD_PAUSE_MS = 260` und zeigt bis dahin
„rechnet das Feld …" statt eines veralteten Feldes, das zu anderen Zahlen
gehört. Die Zeichnungen bleiben sofort. `rechnen()` ist der ausdrückliche
Zuruf: es rechnet sofort und setzt den Merker, damit der entprellte Lauf es
nicht gleich noch einmal tut. **Offen:** die 260 ms sind am gemessenen
Rechenaufwand gewählt und im Browser nicht nachgefühlt — fühlt es sich träge
an, ist `FELD_PAUSE_MS` die eine Stellschraube.

**Zwei Kleinigkeiten derselben Meldung, mitbehoben.** Das **Drehzahlband** wird
für die Scheibe nicht mehr angeboten: es kann sie nicht geben, weil der axiale
Ringsektor den Leerlauf rechnet und über Drehzahl und Last nichts zu variieren
hat — die Karte ist gesperrt und trägt die Begründung, statt den Lauf erst
starten zu lassen (gemeldet wurde genau die umgekehrte Reihenfolge). Und
dieselbe Begründung stand **zweimal** da (einmal in voller Länge rot im
Meldefeld, einmal als ℹ im Protokoll); steht sie im Protokoll, zeigt das
Meldefeld nur noch einen Einzeiler. *Nicht zu verwechseln mit dem Drehzahlband
der FDM-Animation in ④ Berechnung — das ist der Befund vom 17.10.2026, und dort
ist der Grund ein anderer (`betriebspunkt` ohne Drehzahlterm).*

---

## 2026-10-16 · Die Scheibe lief in das Layouttor der Zylindermaschine — in vier 3-D-Einstiegen

**Beobachtung.** Gemeldet aus dem Reiter 🧲, Knopf „🔁 Schnelle Pol-Berechnung
(Symmetrie)", bei gesetztem `fluxPath = "axial"`:

> ⚠ Die Geometrie faellt durch das Rotor-Layouttor — das ist ein Fehler der
> ZEICHNUNG, nicht des Netzes, und kein Netzbau behebt ihn: · Axialfluss:
> dieses Tor prueft Magnettaschen in einem Querschnitt senkrecht zur Drehachse
> und Stege gegen den Rotorrand — **eine Scheibe hat beides nicht.** […]
> Abhilfe: die genannte Tasche kleiner/weiter aussen setzen, die Welle
> duenner, oder — wenn es so gemeint ist — `geom.layoutFreigabe` setzen.

Die Meldung widerspricht sich in sich: sie verwirft eine Zeichnung und sagt im
selben Atemzug, dass sie daran nichts prüfen kann. Die drei angebotenen
Abhilfen bedeuten an einem Scheibenläufer nichts.

**Die Absage war der harmlose Teil — gefährlich war die Freigabe.**
`_build_sector_mesh` setzt konzentrische Zylinder um die Drehachse und
schneidet Magnete aus `magnet_legs` hinein. Ein Axialpayload trägt die
radialen Schemavorgaben weiter mit; gemessen am frischen Payload mit
`fluxPath=axial`:

| | Payload (radial) | gezeichnete Scheibe |
|---|---:|---:|
| Außendurchmesser | `statorOD` 280 mm | `axialAktivOD` **260 mm** |
| Läufer | `rotorOD` 188,6 mm | — (Scheibe) |
| Welle | `shaftD` 60 mm | — |

Mit `layoutFreigabe=true` wäre daraus klaglos ein 280-mm-Zylinder mit sechs
V-Magneten entstanden, und nichts am Ergebnis hätte gesagt, dass es zu einer
anderen Maschine gehört. Das ist dieselbe Lage wie bei einer Bauart ohne
Magnete (Befund vom 20.09.2026), nur eine Ebene höher: dort entscheidet die
**Maschinenart**, hier der **Flussweg** — und der Axialfluss ist payloadseitig
eine PSM, kommt also an der Artabfrage vorbei.

**Gemessen: vier Einstiege, einer gemeldet.** `run_em3d` verzweigt seit dem
07.10.2026 richtig (`ema_fluss.flussweg` vor der Maschinenart). Die vier
anderen Wege in denselben Netzbauer taten es nicht und landeten alle über
`_tor_layout` → `ema_rotorcheck.rotor_layout_check` in derselben Layoutabsage:

| Einstieg | Route / Knopf | vorher |
|---|---|---|
| `run_em3d_sector` | `/em3d/sector`, „🔁 Pol-Berechnung" | Layoutabsage |
| `run_em3d_sweep` | `/em3d_sweep`, Drehzahlband | Layoutabsage |
| `run_em3d_refine` | `/em3d/submodel`, ROI | Layoutabsage |
| `render_model_preview` | `/em3d/preview`, „🧊 3D-Modell ansehen" | Layoutabsage |

**Derselbe Fehler eine Etage tiefer:** `cae_cli.py rotor-check` meldete für
dieselbe Scheibe **„Layout ABGELEHNT" mit Exit 1**, während zehn Zeilen
darunter das Fliehkrafttor denselben Fall sauber als ℹ führt und sagt, was
statt dessen rechnet (`ema_axial.ruecken`/`bandage`). Eine Ausgabe, die oben
verwirft, was sie unten gar nicht beurteilt, ist schlechter als keine — und
ein Agent liest den Exit-Code.

**Behoben.**

* Neuer Typ `ema_em3d.FlusswegFalsch` (**kein** `LayoutUngueltig` — sonst böte
  `ema_diagnose` Knöpfe für Taschenlage und Wellendurchmesser an) und
  `_tor_flussweg(geom, was, statt)`. Es steht als erste Zeile in `_tor_layout`,
  also **vor** der Maschinenart und an dem einen Punkt, durch den
  `_build_mesh_capped` **und** `_build_sector_mesh` beide gehen: kein Netzbauer
  kann eine Scheibe mehr als Zylinder bauen, auch wenn an einer Tür die
  Abzweigung fehlt.
* **`layoutFreigabe` öffnet diese Tür ausdrücklich nicht.** Eine Freigabe
  heißt „ich kenne das Risiko dieser Zeichnung"; hier gibt es kein Risiko
  abzuwägen, sondern nur das falsche Modell.
* Sweep, ROI-Verfeinerung und Modellvorschau sagen zusätzlich, **was für die
  Scheibe an ihre Stelle tritt** (Feldstufe `ema_axial_fdm` für die Last,
  `mesh_cl`/`gap_cl` für die Feinheit, Reiter ⊙ Axialfluss für die Zeichnung).
* **Die Pol-Berechnung wird nicht abgewiesen, sondern geführt.** Was sie
  verspricht — eine Polteilung, anti-periodisch gekoppelt, zum vollen Kranz
  gespiegelt — IST der axiale 3-D-Weg; `run_em3d_sector` verzweigt deshalb wie
  `run_em3d` auf `_run_em3d_axial`. Derselbe Knopf, der richtige Löser.
  Gemessen über diesen Knopf (frischer Payload, `fluxPath=axial`, k = 3,
  N = 300): **253.545 Knoten, Sektor 60,0° (ein Pol von 2p = 6), +1,9 % im
  Mittel gegen den Mehrschnitt**, Randabfall innen 81 % / außen 85 % — und
  über die Route `/em3d/sector` ebenso, mit einem Payload, der **keine einzige
  axiale Zahl** trug (`_axial_ergaenzen` füllt sie benannt auf).
  Das `node_budget_pct` steuert die Zielsuche des *radialen* Sektornetzes und
  wird **gemeldet statt überhört** (Muster `paarvergleich --n_max`).
* `cae_cli.py rotor-check` führt für den Axialfluss „Layout: NICHT zuständig"
  und lässt es weder in das Urteil noch in den Exit-Code eingehen —
  `layout_ok is None` zählt wie jedes andere nicht geführte Tor.
* Oberfläche (`oberflaeche/feld3d.js`, `_e3AxialKarte`): die Modellvorschau
  wird für die Scheibe gesperrt (sie rendert das radiale Vollmodell und hat
  dort kein Gegenstück), der Hinweistext der Pol-Berechnung und das
  Knoten-Kontingent folgen dem Flussweg. Das ist **Auskunft, keine Sicherung**
  — die sitzt im Server, sonst wären `cae_cli.py` und die Job-Warteschlange
  ungeschützt.

**Derselbe Befund eine Etage tiefer, beim Nachmessen gefunden und
mitbehoben:** `ema_optimize._baubar` ruft dasselbe Layouttor, und der schnelle
Bewerter ist der gemeinsame Kern von `leistung`, `ausreizen`, `studie`,
`zielwert` und der KI-Vorsortierung. Gemessen gab er für eine Scheibe
`baubar=False` mit genau demselben Magnettaschen-Text, und
`cae_cli.py leistung --set fluxPath=axial` brach damit ab als
**„nicht baubar: Axialfluss: dieses Tor prueft Magnettaschen …"**. Das Urteil
ist richtig (dieser Bewerter rechnet Zylinderringe mal Blechpaketlänge, eine
Scheibe gehört dort nicht hinein, und jede unzulässige Lösung muss unter jeder
zulässigen rangieren) — die **Begründung** war es nicht. `_baubar` nennt jetzt
den Grund und den Weg (`cae_cli.py axial`, `paarvergleich` über
`ema_axial_vergleich`) und setzt `baubar_art="flussweg"`; `ema_leistung`
schreibt darüber „Dieses Werkzeug ist hier nicht zuständig" statt „nicht
baubar" — *unbaubar* ist ein Urteil über eine Zeichnung, und hier wird keine
beurteilt.

**Nebenbefund, mitbehoben: drei Tests in `test_em3d.py` standen unter `main()`
und liefen nie.** Genau der Fall, den dieselbe Datei am 20.09.2026 schon
einmal festhält („ein Test, der nie läuft, ist grün, weil er schweigt").
Einer davon, `test_tor_nennt_den_weg_der_wirklich_traegt`, war seit dem
20.09.2026 **rot**: er erwartete für die EESM weiterhin eine Absage, während
`laeufer_profile` den Schenkelpolläufer längst baut und `write_sif` der
Erregerwicklung ihre Gleichstromdichte gibt. Alle drei stehen jetzt in
`main()`, der veraltete Zweig ist auf das gemessene Verhalten berichtigt
(EESM geht durch, **mit** der Wickelkopf-Einschränkung; ASM → `feld3d`,
GSM → kein 3-D-Weg).

**Fundstellen.** `ema_em3d.FlusswegFalsch` / `_tor_flussweg` / `_tor_layout` /
`run_em3d_sector` / `run_em3d_sweep` / `run_em3d_refine` /
`render_model_preview`; `cae_cli.py` (Verb `rotor-check`); `server.py`
(`_em3d_finish_error`, `_sauber`; dazu `/em3d/preview` und `/em3d/submodel`,
die ihre **eigene** Fehlerbehandlung samt Traceback führten statt
`_em3d_finish_error` — unter einem begründeten Nein standen dort sechs Zeilen
Python; beide ergänzen jetzt auch `_axial_ergaenzen`, wie die übrigen
em3d-Türen); `ema_optimize._baubar`; `ema_leistung`; `ema_diagnose.diagnose`
(Zweig `FlusswegFalsch`); `oberflaeche/feld3d.js` (`_e3AxialKarte`);
`ema.html` (`#e3_sector_hint`).

**Nicht angefasst.** `ema_rotorcheck.rotor_layout_check` gibt für den
Axialfluss weiterhin `ok=False` mit `flussweg="axial"` zurück — ein „OK" wäre
dort schlimmer als ein Nein (so steht es seit jeher in seinem Docstring), und
alle Aufrufer werten das Feld jetzt aus. Eine **3-D-Modellvorschau für die
Scheibe** gibt es nicht; die Scheibe ist im Reiter ⊙ Axialfluss gezeichnet,
und die gerechneten 3-D-Ansichten liefert der Lauf. **Status: BEHOBEN.**

---

## 2026-10-16 · Das `(2/pi)` in der Flussverkettung stand auf einem MITTELWERT — axial

**Beobachtung.** Seit dem 06.10.2026 steht als offener Punkt in `AXIALFLUSS.md`
und in jedem Bericht über diese Arbeit: *das `(2/pi)` in `betriebspunkt` wird
auf einen schon gemittelten Wert angewandt; das bewegt Kt und jede Temperatur
jedes Axialprojekts und gehört gegen eine bekannte Maschine gemessen.* Hier
ist die Messung.

**Was der Term voraussetzt.** `psi = p*(2/pi)*B*A_fluss` steht an zwei Stellen
(`ema_analysis.compute_performance:1439`, `ema_axial_fdm.betriebspunkt`). Das
`(2/pi)` ist der Mittelwert einer halben Sinuswelle über ihre **Amplitude**:
`Phi = (2/pi)*B1*tau_p*L` ist der Grundwellenfluss je Pol. Der Term setzt also
voraus, dass `B` eine **Grundwellenamplitude** ist. Eingesetzt wurde axial
`eichung_magnet`, und dessen eigener Docstring sagt: *„Diese Zahl ist ein
MITTELWERT, keine Spitze und keine Grundwelle"* (`Spitze * alpha`).

**Messung 1 — am gelösten Verlauf, ohne jede Konvention.** Vorgabe-Payload,
alpha = 0,85, mittlerer Schnitt, 600 Punkte, Polteilung 107,37 mm:

| | mWb/m je Pol | |
|---|---:|---|
| direkt integriert (Gesamtfluss) | **81,27** | = `B_mittel * tau_p`, per Definition exakt |
| `(2/pi)*B1*tau_p` (Grundwellenfluss) | **75,00** | 0,923 × Gesamtfluss — die Oberwellen, die keine verteilte Wicklung verkettet |
| `(2/pi)*B_mittel*tau_p` ← gerechnet | **51,74** | 0,6366 × Gesamtfluss, also **genau 2/pi** |

Der gerechnete Wert ist **weder** der Gesamtfluss **noch** der
Grundwellenfluss.

**Messung 2 — das Werkzeug trägt seinen eigenen Maßstab.** `ema_asm.k_norm =
pi*k_w*N_ph/p^2` rechnet die Hauskonvention auf die Physik um; sie ist über die
**Momenterhaltung** hergeleitet und in `test_maschinenart.py` nachgerechnet.
Gegen `psi_phys = k_w*N_ph*Phi_grundwelle`:

| `psi_haus * k_norm / psi_phys` | |
|---|---:|
| mit dem Flussmittelwert | 0,6866 |
| mit der Grundwelle | **1,0000** |

Die Brücke geht nur mit der Grundwelle auf. Das ist die stärkere Probe als
jede Fremdmaschine: das Werkzeug widerspricht sich selbst.

**Messung 3 — die beiden Stufen desselben Moduls gaben zwei Kt.** Der
Modulkopf von `felder` lädt ausdrücklich dazu ein: *„Stufe 1 rechnet sie mit
einem analytischen B_gap, Stufe 2 mit einem gelösten B1(r). Kommt dabei etwas
anderes heraus, ist das eine Aussage über die Formel und nicht über die
Summation."* Über 13 Geometrien (Polbedeckung, Polzahl, Spalt, Magnetdicke,
Nutzahl, lambda, alle vier Bauformen), `psi_gemessen / psi_analytisch`:

| | Spanne | Streubreite |
|---|---|---:|
| mit dem Flussmittelwert | 1,095 … **1,499** | 37 % |
| mit der Grundwelle | 0,860 … 0,946 | **10 %** |

Und das Restglied läuft monoton mit dem **gemessenen** Carterfaktor
(`carter()`: 1,048 … 1,126) — wo mehr Nutung gemessen wird, bleibt die gelöste
Grundwelle weiter unter der idealen Rechteckwelle. Was übrig bleibt, ist also
Nutung und Streuung, die die Arbeitsgerade nicht kennt: ein physikalischer
Effekt, kein Formelfehler.

**Behoben.** `ema_axial_fdm.formfaktor_grundwelle(geom) = (4/pi)*sin(a*pi/2)/a`
— reine Fourier-Arithmetik der Rechteckwelle, keine Modellwahl — wird
**multipliziert** und ersetzt nichts, wirkt also auch auf ein gemessenes `B`.
Angewandt an beiden Stellen: in `betriebspunkt` und in
`compute_performance` (dort nur im axialen Zweig). `B1_T` steht neben
`B_gap_T` im Ergebnis, damit psi nicht so aussieht, als käme es aus `B_gap`.

**Das bewegt jedes Axialprojekt.** Vorgabe-Payload bei alpha = 0,85
(Formfaktor 1,4565):

| | vorher | nachher |
|---|---:|---:|
| Kt | 0,0790 | **0,1150** (+45,6 %) |
| EMK Spitze | 16,5 V | **24,0 V** |
| Eckdrehzahl | 33.591 | **23.094 1/min** (−31 %) |
| i_q bei 50 Nm | 634,6 A | **435,7 A** |

Bei alpha = 1,0 sind es 4/pi = +27,3 %. `P_Cu` bewegt sich **nicht**: der
Kupferverlust kommt aus Stromdichte × Kupfervolumen und nicht aus i_q (so
gebaut, s. `ema_thermal`). Betroffen sind damit Moment je Ampere, Gegen-EMK,
Feldschwächung und das Kriterium `umrichter` in `ema_sicherheit`.

**Was NICHT angefasst ist, und warum.** Radial steht dieselbe Formel, und
`_analytical_Bgap` liefert für Oberflächenmagnete ebenfalls `Br*perm*alpha`,
also einen Mittelwert. Dort ist die Lage aber **eine andere**:
`run_em_analysis` pinnt die **Spitze** des gelösten Feldes auf genau diesen
Wert, und die gelöste Grundwelle landet damit nahe daran — gemessen SPM
**0,956×**, V-Form 0,570×. Ob das eine richtige Konvention ist oder eine
Folge der Eichung, ist hier **nicht entschieden**; es mitzuändern würde jedes
abgelegte radiale Projekt verschieben, und das ist eine Entscheidung und keine
Reparatur. Steht als offener Punkt.

**Die Fremdmaschine fehlt weiterhin, und das wird gesagt.** Gesucht wurde eine
veröffentlichte Axialflussmaschine mit vollständiger Geometrie **und**
gemessener Leerlauf-EMK. Erreichbar war davon keine, die zur modellierten
Bauform passt: MDPI und EPJ antworten mit 403, der NREL-Server ist von hier
nicht auflösbar, und die eine frei abrufbare Arbeit mit Prototyp und Messung
(Juan de Santiago Ochoa, Uppsala, diva2:436792, Tab. 4.1: Ro 150 / Ri 110 mm,
14 Polpaare, Magnet 10 mm, Br 1,2 T) ist eine **kernlose**
Schwungradmaschine mit **16 mm** Luftspalt — ohne Zähne, ohne Nuten, ohne
Carter. Sie würde das Modell an seiner Topologie messen und nicht an diesem
Term. Die drei Messungen oben sind dafür nicht der Ersatz, sondern die
schärfere Probe: zwei davon sind Arithmetik, die dritte ist der eigene Löser.
Eine passende Fremdmaschine bleibt offen.

**Was die Reparatur NICHT bessert, und das gehört dazu.** Der alte Eintrag vom
06.10.2026 nannte als Symptom das Verhältnis der beiden Momentwege
(`T_verhaeltnis`, „gemessen 4,18…4,85"). Das wird durch diese Reparatur nicht
kleiner, sondern bei kleinem Moment **größer** — der Nenner `1,5*p*psi*i_q`
schrumpft, weil i_q mit dem größeren Kt sinkt. Es war nie derselbe Befund: das
Momentverhältnis ist der seit jeher getrennt benannte Widerspruch um
`T_maxwell` (zwei unabhängig geeichte Felder), und der Modulkopf sagt dazu
weiterhin „BELASTBAR sind psi und B_gap(r); das MOMENT ist es nicht".

**Nebenbefund, mitbehoben:** die Warnung selbst nannte „Faktor ~3, über den
Strom nahezu konstant". Beides stimmt nicht mehr — gemessen **42,9 / 26,2 /
14,8 / 14,8** über 25 / 50 / 100 / 200 Nm; die Zahl ist mit den
Feldreparaturen desselben Tages gewandert, und ab ~100 Nm steht sie nur still,
weil der Strom an der Umrichtergrenze klemmt (ein Anschlag, kein Befund). Eine
Warnung mit einer falschen Zahl ist schlechter als eine ohne: wer sie liest,
glaubt den Abstand zu kennen. `_widerspruch_text` setzt jetzt die **gemessene**
ein, die ohnehin als `T_verhaeltnis` im Ergebnis steht.

**Fundstelle.** `ema_axial_fdm.formfaktor_grundwelle`/`betriebspunkt`/
`_widerspruch_text`, `ema_analysis.compute_performance`. **Status:** axial
behoben, Wächter in `test_axial_fdm.py` (85 → 99 Prüfungen); radial und die
Fremdmaschine offen.

---

## 2026-10-16 · Axialfluss: die Spaltzahl stand im Payload statt in der Bauform

**Beobachtung.** Beim ersten Lauf des neuen axialen Paarvergleichs
(`ema_axial_vergleich`) lieferte die Bauform-Achse für **jede** der vier
Bauformen dasselbe Dauermoment. Die einseitige Maschine hat aber nur einen
Luftspalt; ihr Moment muss die Hälfte sein.

**Messung.** `--set axialBauform=einseitig` ergab **2** Luftspalte statt
einem — also die doppelte Ringfläche, das doppelte Moment, und
`hebt_sich_auf = True`, obwohl ein einseitiger Aufbau den Anzug gerade nicht
aufhebt (`ema_axial.anzug` liest `n_spalte > 1`). Über die **Zeichenseite**
war dieselbe Maschine richtig.

**Die Ursache.** `ema_fluss.masse_axial` las

```python
n = int(g.get("axialSpalte", 0) or 0) or AXIAL_BAUFORMEN[bauform]["spalte"]
```

— der gespeicherte Schlüssel gewann, die Bauform war nur der Rückfall.
Abgeleitet wurde `axialSpalte` aber ausschließlich in `ema_fluss.aus_seite`,
also auf dem Weg über die Zeichenseite. Wer `axialBauform` direkt setzt —
`cae_cli --set`, der Agent, jeder Payload aus `axial_vorgabe`, die
Vergleichsachse — bekam die Spaltzahl des **vorigen** Standes. Und
`AXIAL_VORGABE` trug `axialSpalte: 2` als Vorgabewert, war also selbst die
Quelle des Widerspruchs.

**Behoben.** `n = AXIAL_BAUFORMEN[bauform]["spalte"] * axialStapel`; der
Schlüssel ist aus `AXIAL_VORGABE` heraus und im Schema auf `lo = 0, def = 0`
(„0 = folgt der Bauform"). Ein widersprechender gespeicherter Wert wird
**überstimmt und gemeldet** (`spalte_korrigiert = (alt, neu)` durch
`flaechen` → `ema_axial.auslegung` → eine Zeile in `uebersicht`), nicht
abgewiesen: abweisen träfe jeden Altpayload, der die Zahl noch trägt — das
Werkzeug hat sie selbst hineingeschrieben. Ein zwischenzeitlich eingebauter
harter `ValueError` ist aus genau dem Grund wieder verworfen worden.

**Gemessen danach** (Vorgabe-Payload, Kühlung water):

| Bauform | Spalte | T_dauer [Nm] | Masse [kg] | hebt auf |
|---|---:|---:|---:|---|
| yasa | 2 | 297,2 | 29,00 | ja |
| torus_nn | 2 | 297,2 | 40,14 | ja |
| afir | 2 | 297,2 | 33,65 | ja |
| einseitig | **1** | **148,6** | 24,36 | **nein** |

**Fundstelle.** `ema_fluss.masse_axial`/`flaechen`/`AXIAL_VORGABE`,
`ema_text2ema.SCHEMA["axialSpalte"]`, `ema_axial.auslegung`/`uebersicht`.
**Status:** behoben, Wächter in `test_fluss.py` (alle vier Bauformen, Stapel,
Überstimmen samt Meldung, Gegenprobe ohne Abweichung).

---

## 2026-10-16 · Axialfluss: Thermik und Feldmodell meinten zwei verschiedene Bauhöhen

**Beobachtung.** Beim selben ersten Lauf bewegte die Bauform-Achse auch die
**Masse** nicht. Eine TORUS-NN hat ein Umfangsjoch im Ständer, eine YASA
nicht; das muss wiegen.

**Die Ursache.** `ema_axial_thermik` führte Zahnlänge, Ständerjoch und
Rückenblech **selbst** (`_zahl(geom, "axialZahnLaengeMm", 25.0)`,
`…"axialJochStaenderMm", 12.0`, `…"axialJochLaeuferMm", 13.0`) und fragte die
Bauform dabei nicht. `ema_axial_fdm` entscheidet sie seit dem 06./16.10.2026
anders, in drei Punkten:

* ein **jochloser** Ständer (YASA) hat kein Joch — hier bekam er 12 mm Eisen,
  das es nicht gibt;
* wo die Bauform eines braucht, wird es **aus dem Fluss bemessen**
  (`_jochhoehe`, gemessen 10,92 mm) statt aus einer Vorgabezahl;
* **beidseitig genutet heißt zwei Zahnbänder** (TORUS-NN, seit dem
  16.10.2026) — hier zählte eines.

**Messung** (Bauhöhe derselben Maschine, Feld gegen Masse):

| Bauform | `ema_axial_fdm` | `ema_axial_thermik` |
|---|---:|---:|
| yasa | 65,00 mm | 65,00 mm |
| torus_nn | **100,92 mm** | 65,00 mm |
| afir | **98,84 mm** | 71,00 mm |
| einseitig | **55,92 mm** | 45,00 mm |

Nur YASA stimmte überein — die Bauform, an der entwickelt worden war. Die
Bauhöhe geht in Wellen- und Gehäusemasse ein, die Jochdicke in das
Ständereisen, die Zahnbandzahl in Zahneisen **und** Nutkupfer; zwei Bauhöhen
sind zwei Maschinen.

**Behoben.** `ema_axial_thermik._dicken` liest die drei Dicken aus
`ema_axial_fdm` (`zahnlaenge`, `_jochhoehe` nur wenn `_BAUFORMEN[bf]["joch"]`,
`_rueckenhoehe`) und `stapelhoehe` delegiert an `ema_axial_fdm.stapelhoehe`
statt die Schichtung ein zweites Mal zu summieren — `lagen` weist sich seit
dem 07.10.2026 ausdrücklich als die eine Quelle aus. `_zahnlagen` verdoppelt
beim TORUS-NN Nutkupfer, Zahneisen, Nutwand und Wickelkopffläche.

**Gemessen danach** (Randband Ständer → Gehäuse / Gesamtmasse): yasa
30,6 W/K / 25,43 kg · torus_nn **74,6** / **36,38** · afir **88,0** / **29,99**
· einseitig **44,0** / **21,69**.

**Fundstelle.** `ema_axial_thermik._dicken`/`_geo`/`masse`/`leitwerte`/
`stapelhoehe`. **Status:** behoben, Wächter in `test_axial_thermik.py`
(Bauhöhe Feld = Thermik für jede Bauform, Stapel, doppelte Nutwand bei
TORUS-NN).

---

## 2026-10-16 · Der axiale Paarvergleich: drei Achsen bewegten nichts, zwei davon zu Unrecht

**Beobachtung.** Der erste vollständige Lauf von `ema_axial_vergleich` zeigte
drei Achsen mit durchweg gleichen Zeilen: Nutzahl, Magnetwerkstoff,
Blechsorte.

**Messung und Ursache.**

* **Magnetwerkstoff:** viermal dasselbe `B_gap = 0,8137 T`, von NdFeB N35 bis
  Ferrit Y30. `ema_axial_fdm.eichung_magnet_spitze` rechnet
  `EA.Br_NdFeB * hm/(hm + EA.MU_R_MAG*kc*g)` — über die **Modul-Globalen** von
  `ema_analysis`, genau wie `run_pipeline` und `ema_paarvergleich._setz_magnet`.
  Der Payload-Schlüssel allein erreicht sie nicht. Nach dem Umsetzen (eng um
  den Aufruf, Rücksetzen im `finally`): N35 0,9573 T, Ferrit Y30 0,3319 T,
  N42/N50 sättigen den Zahn.
* **Blechsorte:** `ema_axial.zahnform(geom, b_gap, b_sat_t=None)` fiel auf
  seine Modulvorgabe **1,70 T** zurück, weil niemand `B_sat_T` übergab — die
  Achse wirkt aber *ausschließlich* über diese eine Zahl. Jetzt übergeben;
  M250-35A (1,65 T) fällt als einzige aus, und das **ist** das Ergebnis der
  Achse. Ebenso bekommt `ema_axial.ruecken` das Läuferblech für E und nu.
* **Nutzahl:** hier kürzt sich die Nutteilung wirklich heraus — aber nur,
  wenn `axialNutBreiteMm = 0` ist, die Breite also ein **Anteil** der Teilung
  ist (`slotWidthRatio`); dann ist `B_zahn = B_gap/((1-swr)*k_fe)`
  nutzahlunabhängig und `q*b_nut` konstant. Steht dort ein **Millimetermaß**
  (die Nut ist parallelflankig), bewegt die Nutzahl den Zahn sehr wohl:
  gemessen 1,211 bis 1,653 T über 24…54 Nuten. Ein fester Erklärungssatz wäre
  in einem der beiden Fälle eine Behauptung gegen die Messung gewesen.

**Was daraus folgte.** Eine flache Achse wird jetzt **benannt** — dieselbe
Regel wie `ema_paramstudy.wirkungslos_grund` und aus demselben Grund: eine
Tabelle mit sechs gleichen Zeilen sieht nach einem Rechenfehler aus und ist
meistens keiner, und wo doch, soll es auffallen. `vergleiche` setzt
`wirkungslos`, wenn bei **mindestens zwei baubaren** Optionen keine gezählte
Kennzahl sich bewegt, und hängt den Grund an; steht keiner da, ist das selbst
die Auskunft. Dafür musste `_spannweite` Spannen von 0,0 % **weglassen** —
eingetragen war das Dict nie leer und die Erkennung blind.

**Zwei Dinge, die weiterhin falsch wären, wenn man sie zählte** und deshalb als
Notiz unter ihrer Achse stehen: `MAGNETS` führt weder Dichte noch Preis je
Sorte und `PREISE_EUR_KG["magnet"]` ist **ein** Betrag für alle — Ferrit kommt
in Masse und Kosten genauso heraus wie NdFeB, und gerade der Preis ist sein
Grund. `LAMINATES` führt keine Dichte, die Blechsorte bewegt also auch die
Masse nicht. Beides ist eine Lücke der **Tabellen**, nicht der Rechnung; sie
hier mit Literaturwerten zu füllen hieße, Zahlen zu erfinden, die der radiale
Pfad nicht hat.

**Fundstelle.** `ema_axial_vergleich.bewerte`/`_spannweite`/`vergleiche`/
`ACHSEN`. **Status:** behoben bzw. benannt, Wächter in
`test_axial_vergleich.py` (27 Prüfungen).

---

## 2026-10-16 · Axialfluss: die seitliche Randbedingung war Dirichlet, wo sie periodisch sein muss — und der Ersatzstrom lief nicht um

**Beobachtung.** Beim Umstellen der Polsterung (Befund darunter) sprang die
Grundwelle plötzlich mit der Läuferstellung: 11,8 % über eine Polteilung, wo
vorher 2,0 % standen. Die Polsterung war nicht die Ursache, sondern der
Vorhang: das Eisen daneben hatte einen Randfehler weich gemacht.

**Der Fehler.** Der Modulkopf begründete Dirichlet `A = 0` am Seitenrand mit
*„`A ~ sin(pi*x/tau)` hat dort Nullen"*. Das ist herum vertauscht. Liegt die
**Polgrenze** bei x = 0 — und dort liegt sie, `pol = floor(x/tau_p) % 2` —,
dann ist A dort **extremal** und nicht null; die Nullen von A liegen in den
Polmitten. Und `A = const` auf einer senkrechten Linie heißt `B_x = 0`, also
**kein Umfangsfluss** — erzwungen ausgerechnet an der Polgrenze, wo der
Umfangsfluss im Joch sein Maximum hat.

**Messung.** Grundwelle B1 bei r = 102,5 mm, Vorgabemaschine, mit Fluss-Sperre
als Polsterung (ohne sie ist der Fehler weich und damit unsichtbar):

| | Dirichlet (vorher) | periodisch (jetzt) |
|---|---:|---:|
| über eine Läuferdrehung | 11,8 % | **0,6 %** (= die Nutung) |
| über die Fensterbreite 2/4/8 | 7,4 % | **0,37 %** |
| Polmitte statt Polgrenze am Rand | 0,06 % bei n = 2/4 | — |

Die dritte Zeile war die Probe: schiebt man den Läufer um eine halbe
Polteilung, sodass eine **Polmitte** auf dem Rand liegt, stimmen n = 2 und
n = 4 auf 0,06 % überein. Genau dort ist `A = 0` die richtige Symmetrie, denn
dort ist der Umfangsfluss wirklich null. Das ist aber nur EINE Läuferstellung —
für die anderen braucht es Periodizität.

**Zweiter Fehler, erst dadurch sichtbar.** Mit periodischem Rand brach B1 bei
Läuferwinkel **0** auf 0,6102 statt 1,1356 T ein (−46 %), und nur dort. Der
Ersatz-Flächenstrom kam aus einer zentralen Differenz ohne Umlauf
(`j_mag[:, 1:-1] = (My[:, 2:] - My[:, :-2])/2`) — die beiden Randspalten
blieben **null**, und genau dorthin fällt der Polwechsel bei Winkel 0. Das ist
die Stellung jedes Standbildes und jedes ersten Frames.

**Fundstelle.** `ema_analysis._build_fv_matrix` (Dirichlet auf allen vier
Rändern), `ema_axial_fdm.rastere_scheibe` (`j_mag`), Modulkopf-Abschnitt „Der
eine Trick, ohne den es nicht geht".

**Status: behoben am 16.10.2026.** `_build_fv_matrix(mu, periodisch_x=True)` —
eine Maskenzeile, das `np.roll` darunter wickelt ohnehin um; in y bleibt
Dirichlet und hält das System positiv definit. Die Flagge geht in den
LU-Cache-Schlüssel ein (dasselbe `mu` periodisch und nicht periodisch sind zwei
Faktorisierungen). **Vorgabe aus — der Radialpfad rechnet Ziffer für Ziffer
weiter** (`test_fdm_golden.py` grün). `j_mag` läuft jetzt mit `np.roll` um.
Wächter: `test_axial_fdm.py`, Abschnitt „Die Seitenbedingung ist PERIODISCH".

---

## 2026-10-16 · Axialfluss, Mehrschnitt: die Eisenpolsterung führt den Rückfluss — und der gezeichnete Rücken wirkt dadurch gar nicht

**Beobachtung.** Gemeldet als Frage zum Feldbild: *„bei einer Simulation der afm
sollten die magnetlinien doch immer in richtung der Achse fließen oder habe ich
da einen Denkfehler"*. Kein Denkfehler, aber auch nicht ganz: **axial ist der
Spaltdurchtritt, umfangs der Rückweg**. Im Bild des abgewickelten Schnitts
(`schnitt_figur`) läuft der Rückweg jedoch nicht im gezeichneten Rückenblech,
sondern in großen Schleifen durch die **Polsterung** — das Eisen, mit dem das
Fenster auf Quadratform aufgefüllt wird. Der Modulkopf behauptet das Gegenteil
(`ema_axial_fdm.py:73`): „Mit Eisen ist die Polsterung **wirkungslos**: jenseits
des Joches gibt es keine Quelle, das zusätzliche Eisen führt keinen Fluss".

**Messung.** Vorgabe-Payload, YASA, r = 102,5 mm, N = 400, Leerlauf, nutlos.
Rückfluss je Band über ΔA (A ist die Stromfunktion, also ist die Differenz der
Fluss dazwischen):

| Rücken gezeichnet | rohe Spaltspitze | Φ im Rücken | Φ in der Polsterung | Anteil Polsterung |
|---:|---:|---:|---:|---:|
| 4 mm | 758327,1 | 1,578e7 | 1,344e8 | **89,5 %** |
| 8 mm | 758327,1 | 2,952e7 | 1,206e8 | 80,3 % |
| **13 mm (gezeichnet)** | 758327,1 | 4,226e7 | 1,079e8 | **71,9 %** |
| 25 mm | 758327,1 | 6,722e7 | 8,291e7 | 55,2 % |
| 40 mm | 758327,1 | 9,202e7 | 5,812e7 | 38,7 % |

**Gegenprobe mit LUFT als Polsterung** (nur `mu` außerhalb des Stapels auf 1
gesetzt, sonst identisch): Anteil Polsterung 2,8 / 1,2 / 0,7 / 0,3 / 0,2 %, und
die rohe Spaltspitze bewegt sich dann wirklich — 723969 → 755867 über
4 → 40 mm (**+4,4 %**). Mit Eisen steht sie auf allen fünf Dicken **Ziffer für
Ziffer gleich**.

Die Folge am fertigen Kennwert, über `schnitt()` (also mit Eichung):

| `axialJochLaeuferMm` | B1 Spalt | Spitze | σ_t | Klirr |
|---:|---:|---:|---:|---:|
| 4 / 8 / 13 / 25 / 40 mm | 1,12336 T | 1,25838 T | −158,93 Pa | 0,5337 |

Zehnfache Dicke, **keine einzige Stelle Unterschied**. Das Feldmodell sieht ein
unendlich dickes Rückenblech; ein zu dünnes kann es nicht melden. `ema_axial`
bemisst den Rücken weiterhin richtig (`ruecken`, 11,10 mm nötig gegen 13,00 mm
gezeichnet) — nur rechnet die Feldstufe daneben.

**Fundstelle.** `ema_axial_fdm.py:555-556` (`mu` wird mit `MU_R_IRON` vorbelegt,
nur der Stapel selbst auf 1 gesetzt — alles außerhalb bleibt Eisen) und die
Behauptung dazu in `ema_axial_fdm.py:73`.

**Einordnung.** Die Entscheidung für Eisen ist begründet und gemessen (mit Luft
hängt B1 an der Fensterbreite, Modulkopf Zeilen 60-71) — falsch ist nur der
Satz, sie sei wirkungslos. Der Preis ist beziffert: die Spaltamplitude ist
ohnehin auf `eichung_magnet_spitze` geeicht, verloren geht also nicht die Höhe,
sondern die **Empfindlichkeit** gegenüber Rücken und Joch (4,4 % über das
geprüfte Band) und die Lesbarkeit des Feldbildes. Der radiale Pfad hat dieselbe
Lektion schon gelernt und blendet seine Polsterung im Bild aus
(`_field_frame`, Maske bei r > 1,02·statorOD/2, CLAUDE.md „Outside-stator
masking") — der axiale zeichnet sie mit.

**Status: behoben am 16.10.2026** — aber nicht allein. Der erste Versuch,
nur die Polsterung umzustellen (`POLSTER_MU_R`, eine Fluss-Sperre statt Eisen),
machte etwas anderes schlechter: die Schwankung der Grundwelle über eine
Läuferdrehung stieg von 2,0 auf **11,8 %**. Die Eisenpolsterung hatte einen
zweiten Fehler weich gemacht — die seitliche Randbedingung (eigener Befund
darunter). Erst beide zusammen ergeben ein stimmiges Modell:

| | Rücken 4→40 mm | Fluss außerhalb | Fensterbreite 2/4/8 | Läuferdrehung |
|---|---:|---:|---:|---:|
| Eisen (vorher) | +0,0 % | 59,1 % | 0,34 % | 2,0 % |
| Sperre, alte Randbed. | +18,9 % | 0,0 % | 10,6 % | 11,8 % |
| **Sperre + periodisch** | **+4,1 %** | **1,9 %** | **0,37 %** | **0,6 %** |

Die +4,1 % sind die ehrliche Zahl; die +18,9 % des Zwischenstands waren der
Randfehler und nicht das Rückenblech. Gegenprobe: mit LUFT statt Sperre kommen
unter derselben Randbedingung +4,0 % heraus — die Wahl ist nach der
Randreparatur fast gleichgültig geworden, und das steht bei `POLSTER_MU_R`.

Am Vorgabe-Payload bewegt sich B1 dadurch um −0,2 % (1,1234 → 1,1212 T): das
gezeichnete Rückenblech ist dick genug. Spürbar wird es, wo es das nicht ist —
bei 4 Polen −10,9 % gegenüber einem unendlich dicken. **Sättigung zeigt der
lineare FDM weiterhin nicht**; ob der Rücken dick genug ist, sagt
`ema_axial.ruecken`.

Verwandt und **weiterhin offen**: der „Luftrand" des 3-D-Ringsektors ist Eisen
(Befund E vom 11.10.2026) — derselbe Fehler eine Dimension höher, und am
16.10.2026 an den exportierten Feldlinien nachgemessen (s. unten).

---

## 2026-10-16 · Axialfluss: die Nut schneidet durch das Ständerjoch — jede Bauform mit Joch hat im Feldmodell keines

**Beobachtung.** Beim Nachmessen des Befundes darüber: in `torus_nn`, `afir` und
`einseitig` steht im Raster **kein zusammenhängendes Ständerjoch**. Die Nuten
werden so tief geschnitten wie das ganze Ständerband hoch ist.

**Messung.** Vorgabe-Payload, N = 400, Nutbreite 50 %. „Voll eisern" = Rasterzeilen
mit 100 % Eisen über dem Umfang, also das Joch:

| Bauform | Ständerband | Zahn + Joch | davon voll eisern | erwartet |
|---|---:|---|---:|---:|
| yasa | 25,0 mm | 25,0 + 0,0 | 0,0 mm | 0,0 mm ✔ |
| torus_nn | 37,0 mm | 25,0 + 12,0 | **0,0 mm** | 12,0 mm ✗ |
| afir | 37,0 mm | 25,0 + 12,0 | **0,5 mm** | 12,0 mm ✗ |
| einseitig | 37,0 mm | 25,0 + 12,0 | **0,0 mm** | 12,0 mm ✗ |

Was es kostet (rohe Spaltwelle, Joch nachträglich ins `mu` zurückgesetzt, sonst
identisch): `afir` Grundwelle **+0,9 %**, `einseitig` **+0,8 %** — klein, weil
die Eisenpolsterung (Befund darüber) für das fehlende Joch einspringt. Der eine
Befund **maskiert** den anderen.

**`torus_nn` ist der Fall, in dem es nicht klein bleibt.** Dort heißt
`kenn = "beide"`, die Nut wird also von BEIDEN Seiten über die volle Bandhöhe
geschnitten — übrig bleiben nur die Zahnsäulen, kein Joch. Gemessen gegen YASA
bei sonst gleicher Maschine:

| | rohe Spitze | rohe Grundwelle | Klirr |
|---|---:|---:|---:|
| yasa | 9,968e5 | 8,898e5 | 0,534 |
| torus_nn | 1,062e6 | **8,815e4** | **3,037** |

Faktor **10 weniger Grundwelle bei dreifachem Klirranteil** — die Polwelle ist
praktisch weg, übrig ist Nutwelligkeit. Nach der Eichung steht das als
B1 = 0,092…0,171 T im Ergebnis (gegen 1,123 T bei YASA), und es wandert mit der
Jochdicke, sieht also nach einem gerechneten Zusammenhang aus.

**Und man kommt mit EINER Eingabe dorthin.** `ema_fluss.aus_seite:678-681`
schaltet YASA → TORUS-NN, sobald `axialJochStaenderMm > 0,5` ist. Wer im Reiter
⊙ Axialfluss ein Ständerjoch einträgt — die naheliegende Handlung, wenn man ein
Joch haben will — bekommt eine Bauform, deren Joch das Feldmodell wegschneidet.

**Fundstelle.**

* `ema_axial_fdm.py:539-540` — `t_nut = statorhoehe(geom)` und `t_joch = 0.0`.
  `statorhoehe` **enthält das Joch** seit dem 06.10.2026 (`:313`,
  `h += _jochhoehe(g)`). Die Bandhöhe `t_nut + t_joch` stimmt deshalb weiter,
  aber `t_nut` ist zugleich die **Schnitttiefe** der Nut — das Joch ist aus der
  einen Variablen in die andere gerutscht. Der Entwurf meinte sichtbar
  `t_nut` = Zahn, `t_joch` = Joch.
* `ema_axial_fdm.py:636,638` — `tiefe |= (Y >= lg["y1"] - t_nut)` bzw.
  `(Y <= lg["y0"] + t_nut)`.
* Bei `"beide"` kommt dazu, dass `statorhoehe` nur `Zahn + Joch` rechnet, ein
  beidseitig genuteter Ständer aber `Zahn + Joch + Zahn` hoch ist.
* Gezeichnet wird das Joch sehr wohl: `ema_axial_cad.py:212` ruft
  `AF._jochhoehe` selbst — CAD und Feld meinen also verschiedene Maschinen.

**Status: behoben am 16.10.2026.** `zahnlaenge()` ist jetzt eine eigene Größe
(die Schnitttiefe EINER Nut), `statorhoehe()` rechnet `_zahnlagen() * Zahn +
Joch`, und `rastere_scheibe` gibt `_nuten` die Zahnlänge statt der Bandhöhe.
Nachgemessen am Raster:

| Bauform | Joch erwartet | vorher | nachher |
|---|---:|---:|---:|
| yasa | 0,0 mm | 0,0 ✔ | 0,0 ✔ |
| torus_nn | 12,0 mm | 0,0 | **11,7** |
| afir | 12,0 mm | 0,5 | **12,5** |
| einseitig | 12,0 mm | 0,0 | **11,9** |

TORUS-NN: B1 0,0922 → **1,0675 T**, Klirranteil 3,04 → **0,46**. Sein
Ständerband ist jetzt 62 mm statt 37 (2 × Zahn + Joch) — das wandert über
`lagen()` in Thermik, CAD und den 3-D-Sektor mit, die alle dieselbe Quelle
lesen. afir/einseitig +0,9 / +0,8 %. YASA Ziffer für Ziffer unverändert.
Wächter: `test_axial_fdm.py`, Abschnitt „Die Nut schneidet NICHT durch das
Joch" — gemessen wird am **Raster** und nicht an einer Höhenangabe, denn eine
Lage, die es laut `lagen()` gibt, kann im `mu` trotzdem weggeschnitten sein.

---

## 2026-10-12 · `run em3d --from-project`: die Schrägung kommt im 3D-Lauf nicht an

**Beobachtung.** Auslegung mit `skew_deg=10` (Runde 3 — Rastmoment 73,6 % →
46,9 % durch die Schrägung). Die 3D-Gegenprobe des selben Projekts lief
**ohne** Schrägung: `results.json/em3d` meldet `skew_deg: 0.0,
skew_segments: 1`, während der Design-Payload 10° trägt. Der Berichtstext
der Kette notiert zwar „Schrägung im 3D-Modell nicht vorhanden", kann sie
aber nicht kennen — er beschreibt einen Zustand, der aus dem Payload nicht
hervorgeht.

**Messung.**

| | Projekt 20261012_160155 |
|---|---|
| Design (ausgeführt) | `skew_deg: 10` (Ausgang `run analyse`; Log 16:10) |
| `meta.json.payload` (persistiert) | top-level: **nicht vorhanden**; `geom.skew_deg: 10` — der Wert ist in den `geom`-Block verlegt |
| em3d aus `--from-project` (16:10) | `skew_deg: 0.0`, `skew_segments: 1`, 6 Magnete, B_gap 3D 0.751 T |
| `run em3d --set skew_deg=10` | Log `skew_deg: 0 → 10` — `apply_sets/_locate` legt es **wieder in `geom`** (Schema), top-level bleibt leer; em3d-Ergebnis weiterhin `skew_deg: 0.0`, Mesh „wiederverwendet" |
| `run em3d --payload-file` mit **top-level** `skew_deg=10` | `skew_deg: 10.0`, `skew_segments: 4` (6 × 4 = 24 Magnete im Mesh), B_gap 3D 0.307 T, Phasenversatz +9.8° (erklärt durch die Staffelung 4×2.5°) |

**Fundstelle.**

* `ema_em3d.py:444,573` — liest `opts.get("skew_deg")` **top-level** aus; das
  `geom`-Nest schaut es nicht an. Bei 0 baut es ein ungeschrägtes Mesh
  (`skew_segments: 1`).
* `cae_cli.py:581` (`_locate` in `apply_sets`) — `skew_deg` ist im
  `geom`-Schema; die `--set`-Zuweisung wird deshalb in `geom` abgelegt —
  genau dort, wo der Konsument nicht hinsieht. Der `--set`-Mechanismus
  kann den Mangel also nicht heben; nur ein `--payload-file` mit
top-level-Schlüssel.
* Die Persistenz in `meta.json` verlegt den Wert bereits beim ersten
  Speichern in `geom` — der em3d-Aufruf hatte nie einen top-levelWert,
  und der Mesh-Cache ("Geometrie unverändert") verwertete die `--set`-Nachlieferung
  dann auch nicht, weil die in `geom` landete.

**Status: offen — nicht repariert.** Die em3d-Zahlen des Erstlaufs
(B_gap 3D 0.751 T) stammen aus dem **ungeschrägten** 3D-Lauf; das ist für
die Grundwelle vertretbar (Schrägung breitet vor allem Oberwellen aus),
aber vollständig ist es nicht. Der geschrägte 3D-Lauf (0.307 T bei
Paketmitte) ist danach in `results.json/em3d` nachgetragen,
Phasenorientierung in beiden Längen übereinstimmend (−0.7° bzw. +9.8°
mit Erklärung). Die Behebung gehört an `ema_em3d` (auch `geom.skew_deg`
lesen) oder an die Persistenz (Schlüsselposition stabil halten) — nicht
in den Aufruf.

---

## 2026-10-12 · Detail-Lauf über `--from-project` rechnete Pkw-WLTP neben dem Lastspiel — die Lastspiel-Bindung übersteht den Knoten nicht

**Beobachtung.** Endstand einer Auslegung (Mähwerk, Lastspiel `maehwerk_80cm`,
3000 1/min · 8 Nm Dauer · 14 Nm Spitzen) als Detail-Lauf fortgesetzt:
`cae_cli.py run analyse --from-project 20261012_154005 --guete detail`.
Der neue Lauf (20261012_154518) trug zusätzlich einen
**Fahrzeugzyklus WLTP3B mit 1600 kg, 10163 1/min, η=−1381 %** — eine Maschine,
es gibt sie nicht, auf einer Welle, die keinen Weg fährt. Die Quelle des Projekts
zeigte korrekt "Lastspiel (csv)"; der Detail-Lauf zeigte "Fahrzeugzyklus (WLTP3B)".
Ein Lastspiel mit 8 Nm Dauer lastet keinen 1600-kg-Pkw — und genau dieser
Pkw-Zyklus auf einer Maschine, die kein Pkw ist, ist die Fallgrube, die
AGENTS.md benennt.

**Messung.**

| Projekt | Aufruf | Logzeile | Knoten-Payload |
|---|---|---|---|
| 20261012_154005 (Runde 3) | `--frisch --zyklus maehwerk_80cm` | `⚙ Lastspiel (Lastspiel (csv))` — korrekt | `cycle: lastspiel`, `cycle_csv:` **fehlt**, `vehicle: 1600 kg` |
| 20261012_154518 (Detail) | `--from-project 154005 --guete detail` | zusätzlich `🚗 Zyklus (WLTP3B) … 0.7 km · 0.01 kWh/100km · η−1381 %`, `T_winding=654°C` | `cycle: lastspiel`, `cycle_csv:` **fehlt**, `vehicle: 1600 kg` |

Die ausgeführte und die gespeicherte Payload sind nicht dieselbe: der Lauf
rechnet mit `cycle_csv` (1807 Zeichen Inline-CSV, `ema_zyklen.holen`), und die
gespeicherten Knoten (153221, 154005, 154518 — alle drei) tragen
`cycle: lastspiel` **ohne** `cycle_csv`, aber **mit** dem
`vehicle`-Block der Schemavorgabe. Was ausführt, kommt nicht an; was nicht
dorthin gehören sollte, bleibt stehen.

**Fundstelle.**

* `ema_zyklen.anwenden` (`ema_zyklen.py:387`) — der einzige Schreiber von
  `payload["cycle_csv"]`; wird nur aufgerufen, wenn der Aufruf das Flag
  `--zyklus` trägt (`cae_cli.py:713–720`).
* `ema_projekt.knoten_setzen` (`ema_projekt.py:344–383`) — speichert den
  Payload aus dem Manifest (`m["inputs"]["payload"]`), nicht den
  ausgeführten; das Manifest trägt die Schemavorgaben (darin
  `vehicle` 1600 kg), und `cycle_csv` ist in keinem der drei Knoten.
* `ema_pipeline.py:4812–4831` — der gefährliche Zweig: bei
  `cycle in ("csv","lastspiel") and cycle_csv` wird die CSV gelesen; **ist
  `cycle_csv` leer, fällt der Lauf in die `else`-Klausel und rechnet
  `ema_drivecycle.wltp_class3()` mit dem `vehicle`-Block.** Stillschweigend.
  Default ist ohnehin `cycle="wltp3"` (`ema_pipeline.py:3538`).

**Status: offen — nicht repariert.** Die Behebung ist zweigeteilt und
berührt beide Seiten der Pipeline: (1) der ausgeführte Payload ist der zu
speichernde (oder der Knoten trägt neben der `cycle`-Art den Zyklus-Namen und
`--from-project` wendet ihn neu an — `ema_zyklen.anwenden` ist dafür schon
da); (2) `cycle ∈ {csv, lastspiel}` mit leerem `cycle_csv` ist ein harter
Fehler statt eines Rückfalls auf einen fremden Fahrzeugzyklus. Bis dahin:
**jeder** `analyse`-Aufruf, der auf einem Projekt aufsetzt, trägt das
`--zyklus`-Flag selbst — ein `--from-project` ohne Flag ist für einen
Lastspiel- oder CSV-Zyklus nicht verlässlich. Die WLTP-Zahlen in 20261012_154518
sind für den Bericht nicht verwendbar; der Lastspiel-Block und alle
anderen Stufe desselben Projekts sind identisch mit 154005.

---

## 2026-10-12 · Der Axialfluss-FDM im Browser: Einzelbild zeichnete die falsche Maschine, der volle Lauf zeigte nichts

**Gemeldet.** *„der fdm Solver bei der Axialfluss geht immer noch [nicht]. Es
geht eine Einzelbildberechnung. aber dann werden auch radialmagnete mit
berechnet. Das ist ganz einfach falsch. Auch wenn ich ein ganzen durchlauf
berechnen will, bekomme ich keine darstellung wie bei einer psm. gar nichts."*

Beide Hälften stimmen, und es waren **vier** voneinander unabhängige Defekte.
Gemeinsam ist ihnen ein Muster: jeder einzelne ist eine Stelle, an der etwas
GERECHNET und dann nicht ausgeliefert wurde.

---

### A · `render_preview_frame` kannte den Flussweg nicht · **behoben**

**Messung.** `ema_pipeline.render_preview_frame` enthielt die Zeichenkette
`flux`/`axial` **null mal**. Es ruft unbedingt `ema_analysis.run_em_analysis`
und `_field_frame`, also `_rasterise` über `hypot(X, Y)` mit
`ema_topology.magnet_legs` — einen Zylinderquerschnitt mit RADIALEN Magneten.
Auf einen axialen Payload angewandt zeichnete die Vorschau eine IPM-Maschine,
die es nicht gibt, und zwar an der Stelle, an der man schnell nachsieht, ob die
Geometrie stimmt.

**Fundstelle.** `ema_pipeline.py`, `render_preview_frame`; Route
`POST /preview_field`; Knopf `#btn_preview` im Reiter ▶ Live-Simulation.

**Stand.** Behoben: `_axial_preview_frame` zeichnet denselben abgewickelten
Schnitt wie der Lauf (`ema_axial_fdm.schnitt_figur`) beim mittleren Radius, mit
den Höhenlinien von A als Feldlinien. Gemessen: 557 kB PNG, B_gap 0,5745 T bei
r = 102,5 mm, `torus_nn`, 2 Polteilungen, Betriebspunkt i_q = 178,4 A. Die
Bildunterschrift nennt den Radius — ein abgewickelter Schnitt ohne ihn ist keine
Aussage, weil Pol- und Nutteilung mit r wachsen.

---

### B · Das Diagramm `B_gap(r)` gab es ZWEIMAL, und die ausgelieferte Fassung las einen Schlüssel, den es nicht gibt · **behoben**

**Messung.** `ema_pipeline._axial_bgap_chart` las `axfeld["r_schnitte_m"]`.
`ema_axial_fdm.felder` liefert den Radiusvektor als **`radien_m`**. Der
Schlüssel fehlte also immer, die Funktion gab in ihrer zweiten Zeile `None`
zurück, `charts/airgap.png` wurde beim Axiallauf **nie** geschrieben, und der
Untertab 📈 Luftspalt blieb leer. Nachgemessen am Lauf vom 11.10.2026:
`charts/` enthielt `axial_struktur · connection · em_curve ·
feld_axial_bgap_r · feld_axial_schnitt · power · thermal` — kein `airgap.png`.

**Die Ursache ist die Doppelung, nicht der Tippfehler.** Dieselbe Kurve wurde an
zwei Stellen unabhängig gezeichnet, und die beiden liefen auseinander: die
Fassung in `ema_axial_fdm.bilder` lief und stellte die gemessene Grundwelle
gegen `eichung_magnet`, einen flussgewichteten **Mittelwert** — genau die
Verwechslung, die am 06.10.2026 als Befund aufgeschrieben wurde. Die Fassung mit
der richtigen Bezugslinie war die, die nie lief.

**Stand.** Behoben: eine Fassung (`ema_axial_fdm.bgap_figur`), Bezugslinie
`eichung_magnet_grundwelle`, und sie **wirft** bei fehlenden Daten statt leer
zurückzukommen — ein stilles `None` hat genau das hier verdeckt.

---

### C · Derselbe Schlüsselfehler im 3-D-Vergleich, dort von einem Rückfall verdeckt · **behoben**

**Messung.** `ema_axial_em3d.vergleich` las
`viele.get("r_schnitte_m") or np.linspace(r3[0], r3[-1], len(...))`. Der erste
Zweig griff nie; verglichen wurde gegen eine **gleichmäßig über den Ringraum
gelegte Ersatzachse** statt gegen die wirklichen Schnittradien (Scheibenmitten
bei `ri + (ro−ri)·(k+0,5)/k`).

**Das ist der schlimmere der beiden.** Bei B war das Ergebnis ein fehlendes
Bild — sichtbar. Hier war es eine Kurve, die richtig aussieht.

**Stand.** Behoben: `radien_m` wird gelesen, und bei fehlender oder
unpassender Achse kommt ein benannter Fehlschlag statt einer geratenen.

---

### D · Die Scheiben-Animation existierte und wurde nie gerufen · **behoben**

**Messung.** `ema_axial_fdm.frames` dreht den Läufer durch den abgewickelten
Schnitt, schreibt `frame_XXXX.png` und kodiert `anim.mp4` — vollständig, seit
dem 07.10.2026. Aufrufer: `cae_cli.py` an zwei Stellen, **sonst niemand**. Die
Pipeline übersprang die Animation statt dessen mit dem Satz, eine bewegte
Scheibe „bräuchte den abgewickelten Mehrschnitt über dem Rotorwinkel, und das
ist eine neue Stufe und keine Reparatur" — die Stufe war zu dem Zeitpunkt
bereits geschrieben. Ein Knopf, den nur die CLI hat, ist für den Browser nicht
vorhanden; das ist hier sonst überall die Regel.

**Zweiter Fund an derselben Stelle:** der Übersprung lag **hinter** dem radialen
Referenzlauf (`run_em_analysis` bei `frame_res`, mit Sättigungsdurchgang). Der
lief für die Scheibe also voll durch, nur um den Farbdeckel eines Bildes zu
setzen, das nie gezeichnet wurde.

**Stand.** Behoben: die Pipeline ruft `ema_axial_fdm.frames`, füllt die
Frame-Puffer, setzt `rpm_list`/`frames_per_rpm`/`frame_angle_deg`/`videos` wie
der radiale Weg — der vorhandene Player und der Video-Knopf bedienen sie ohne
Änderung. Die Winkelachse ist die **elektrische Periode** (zwei Polteilungen),
nicht `pole_pitch`: über eine ganze Umdrehung wäre es p-mal dasselbe Bild. Der
radiale Referenzlauf entfällt für die Scheibe.

---

### E · Gezeichnet und nicht ausgeliefert · **behoben**

**Messung.** Nach dem Lauf vom 11.10.2026 lagen `feld_axial_schnitt.png` und
`feld_axial_bgap_r.png` in `charts/` — und **kein** `results`-Schlüssel nannte
sie. `results["em"]` trug `airgap_chart_b64 = None`, `frames = None`,
`rpm_list = None`, `field_modes = []`. Der Ergebnis-Reiter kann nur zeigen, was
ihm jemand nennt; der Untertab ⚡ EM-Feld blieb deshalb leer. Auch bei
funktionierendem Diagramm hätte der axiale Zweig `airgap_chart_b64` nicht
gesetzt — das tat nur der radiale `else`.

**Stand.** Behoben: `airgap_chart_b64`, `axial_schnitt_b64` und
`axial_bgap_bild_b64` gehen ins Ergebnis, und `renderField` zeigt für den
Axialfluss einen eigenen Block (abgewickelter Schnitt, B_gap(r), die Grenze der
Mehrschnitt-Stufe im Klartext) über dem nun ebenfalls gefüllten Player.

---

## 2026-10-11 (abends) · Die Axialfluss-Ergebnisse im Browser — und der Luftrand, der Eisen ist

**Gemeldet.** *„die ergebnisse der 3d feld berechnung in Elmer der
axialflussmaschine will ich auch im Browser sehen. Ich möchte die
Magnetfeldlinien sehen. das gilt auch für die Live simulation. da möchte ich
auch magnetfeldlinien sehen."*

---

### A · Der Axiallauf schrieb keine Browser-Dateien · **behoben**

**Beobachtung.** Der fertige Axiallauf zeigte im Reiter 🧲 eine
Kennwerttabelle und sonst nichts: `ui_nach.bilder` = 0, kein Feldbild, kein
eingebetteter Betrachter, keine Feldlinien — während derselbe Knopf für die PSM
sechs Bilder und den 3-D-Betrachter liefert.

**Messung.** Die VTU lag die ganze Zeit auf der Platte
(`<projekt>/axial_em3d/results/case_t0001.vtu`, 13.785 Knoten). Was fehlte, war
der Schritt von ihr zu den beiden Dateien, die `vtk.js` lädt — dieselbe Lücke
wie beim harmonischen ASM-Lauf am 20.09.2026 und mit derselben Antwort.

**Fundstelle.** `ema_axial_em3d.browser_dateien` (neu) ·
`ema_em3d._run_em3d_axial` · `ema_em3d.export_browser_streamlines`.

**Stand.** Behoben. Drei Dinge waren dabei inhaltlich und nicht technisch:

1. **Gezeigt wird der Vollkranz, nicht der Sektor.** Gerechnet ist eine
   Polteilung (22,5°); ein Tortenstück von 22,5° ist nichts, woran man eine
   Maschine erkennt, und eine Feldlinie, die an der Periodikfläche aufhört,
   sähe aus wie ein Ende des Flusses. Gespiegelt wird mit dem **vorhandenen**
   `ema_em3d._pattern_full_motor` — die Symmetrie des Axialsektors ist dieselbe
   wie die des radialen Ein-Pol-Sektors (Drehung um z, anti-periodisch).
2. **Die Startpunkte der Feldlinien mussten zur Scheibe passen.** Das Raster in
   `export_browser_streamlines` ist für einen Zylinder gebaut und beginnt knapp
   über der WELLE: gemessen bei r = 70,7 mm, während der Ringraum dieser
   Scheibe erst bei Ri = 75 mm anfängt. `vtkStreamTracer` verwirft Startpunkte
   außerhalb des Netzes **stillschweigend** — es gäbe weniger Linien und keine
   Meldung. `export_browser_streamlines` nimmt jetzt `seeds=` entgegen; das
   Tracen, die Abbruchschwelle und das Abschneiden bleiben an EINER Stelle.
3. **Gezählt statt geglaubt.** `ema_em3d.zaehle_linien` (aus
   `ema_em3d_harm._zaehle_linien` herausgehoben, die jetzt dorthin delegiert) —
   derselbe Fallstrick trifft jeden Löser, der diese Dateien schreibt.

Gemessen danach über die Maske: 12,0 s Lauf, **4800 Feldlinien aus 2400
Startpunkten**, `browser.vtp` 7,6 MB, `browser_lines.vtp` 7,2 MB, beide über die
BESTEHENDEN Routen `/em3d/vtp` und `/em3d/streamlines` (HTTP 200) — keine neue
Route. Betrachter 1014 × 480 px, Farbskala |B| 0,14 … 2,42 T.

---

### B · Der Knopf „🧊 Im Browser ansehen" war im Berichtszweig TOT · **behoben**

**Beobachtung.** Beim Verdrahten von (A) erschien der Knopf sofort — und tat
nichts. Kein Bild, kein Fehler in der Konsole.

**Messung.** `_renderEm3d` hat zwei Zweige. Der Betrachter-RAHMEN
(`#e3_viewer3d`) samt Bedienleiste (`#e3_clipbar` mit Feldlinien-Schalter,
Dichteregler, Schnittebene, Ansichtsknöpfen) wurde **nur im PSM-Zweig** gebaut;
der Zweig für `res.bericht` zeichnete den Knopf, aber nicht den Rahmen, den
`openBrowser3d()` sucht — und die Funktion kehrt in ihrer zweiten Zeile zurück
(`const div = …; if (!div) return;`). Nachgemessen über die Maske:
`document.querySelector('#e3_viewer3d canvas')` = `null`,
`document.getElementById('e3_lines_on')` = nicht vorhanden.

**Das betrifft nicht nur den Axialfluss.** Derselbe Zweig bedient die
**harmonische Asynchronmaschine**, deren Browser-Dateien am 20.09.2026
ausdrücklich dafür gebaut wurden („die Ergebnisse sollen im Browser dargestellt
werden, auch die 3D Ergebnisse wie Feldlinien"). Geschrieben wurden sie — der
Weg in den Betrachter fehlte seither.

**Fundstelle.** `ema.html` `_renderEm3d`, Berichtszweig.

**Stand.** Behoben. Das Markup liegt jetzt in `_e3BetrachterHtml()` und wird von
beiden Zweigen gerufen; eine zweite Abschrift wäre dieselbe Falle noch einmal.
Gemessen danach: Betrachter 1014 × 480 px, Feldlinien-Schalter vorhanden und
wirksam.

---

### C · Die Live-Simulation hat Feldlinien — in der ABWICKLUNG · **gebaut**

**Beobachtung.** Die Vorschau zeigte drei Bilder (Scheibe, Abwicklung, Kurve),
alle ohne Feldlinien. Die Abwicklung war ausdrücklich „gezeichnet, nicht
gelöst".

**Entscheidung und ihr Grund.** Die Feldlinien stehen jetzt in der Abwicklung,
und zwar nicht als Zugeständnis an den verfügbaren Platz: der Schnitt löst
`B = rot(A·e_r)` in genau dieser θ-z-Ebene, also **SIND** die Höhenlinien von A
dort die Feldlinien — exakt, ohne Nachintegrieren eines abgetasteten
Vektorfeldes, ohne Startpunktwahl, ohne Schrittweite.

**Auf der Scheibe von vorn gibt es keine, und das ist eine Aussage über das
Modell.** Eine Scheibe trägt per Konstruktion keine Radialkomponente (derselbe
Grund, aus dem `rzBei` sein Bild aus Bz und Bt baut); in der Stirnansicht liegen
in der Ebene aber gerade Br und Bt. Linien gäbe es dort nur, indem man Br
erfindet — und ein erfundenes Linienbild ist schlimmer als keines, weil niemand
es nachmisst. Das Bild sagt es selbst, statt die Lücke stillschweigend zu
lassen.

**Fundstelle.** `axialfluss/live.js` (`liveKonturen`, `liveVersatz`,
`zeichneLiveAbwicklung`), `axialfluss/ansicht.js`, `ema.html`.

**Stand.** Gebaut. Drei Dinge daran sind gemessen und nicht geraten:

* **Die Höhenlinienwerte stehen EINMAL fest** (`folge.aDeckel`), wie die
  Farbskala und aus demselben Grund: je Rahmen neu gewählt änderte sich die
  Zahl der Linien mit der Drehung, und dann sähe eine Änderung der SKALA aus wie
  eine Änderung des FELDES. Gleich viele Linien heißen gleich viel Fluss
  zwischen ihnen — das ist der ganze Grund, warum man ein Linienbild lesen kann.
* **Gezeichnet wird maßstäblich.** Der Streifen war 460 × 120 px bei einem
  Seitenverhältnis von 1,20 — ein 1 mm dicker Luftspalt in 65 mm Bauhöhe sähe
  darin wie 10 % der Maschine aus, und Feldlinien in einem verzerrten Bild
  treffen die falschen Winkel.
* **Struktur und Feld kommen aus EINEM Array** (`g.rolle` und `s.A` am selben
  Gitter). Eine daneben gezeichnete Geometrie könnte gegen das Feld verrutschen,
  und beide Bilder sähen richtig aus.

Gemessen im Browser: **8 von 8** verschiedenen Bildern über 13 s, 496…656
Bildpunkte in der Linienfarbe je Rahmen (die Linien sind da UND sie bewegen
sich), bei Stop 1 von 3 — es steht dann still. Keine Konsolenfehler.

---

### D · `live.js` berief sich auf eine Messung, die es nicht gab · **berichtigt**

**Beobachtung.** Der Modulkopf schrieb über die Antiperiodizität „in
`pruefe.js` nachgemessen, nicht angenommen". In `pruefe.js` stand dazu **nichts**
(null Treffer auf `rotorVersatz`). Die Messung war im Bauen von Hand gemacht und
nicht festgehalten worden.

**Warum das zählt.** Eine Behauptung über eine Messung, die es nicht gibt, ist
schlechter als keine Behauptung: sie lädt dazu ein, sich darauf zu verlassen.

**Stand.** Berichtigt — die Messung steht jetzt da (`pruefe.js`, Abschnitt 10).
Gemessen am festen Ort in der Spaltmitte: **0,5821 → −0,5821 → 0,5821 T** über
zwei Polteilungen, Betragsverhältnis 1,0000. Dass es *exakt* kippt und nicht nur
näherungsweise, ist die richtige Erwartung und kein Verdacht: das Fenster ist
zwei Polteilungen breit, eine Verschiebung um eine Polteilung bildet das Gitter
auf sich selbst ab. Dazu die Gegenprobe, dass ohne Angabe nichts passiert
(Ziffer für Ziffer die alte Rechnung). `pruefe.js` 27 → 42 Prüfungen.

---

### E · Der „Luftrand" des Axialsektors ist EISEN · **offen**

**Beobachtung.** Beim Nachsehen der exportierten Oberfläche fiel auf, dass das
Eisen bis r = 149,2 mm reicht, obwohl die Scheibe bei Ro = 130 mm endet.

**Messung.** Körperweise aus der VTU (Radien je `GeometryIds`):

| Body | Bedeutung | r_min | r_max |
|---|---|---:|---:|
| 1 | Eisen | 55,8 | 149,2 |
| 3, 4 | Magnete | 75,0 | 130,0 |

Ri = 75,0 · Ro = 130,0 · r_in = 55,75 · r_out = 149,25 (`RAND_ANTEIL` = 0,35).

**Das widerspricht dem Modulkopf.** Dort steht: *„Deshalb bekommt das Modell
hier Luftränder innen und außen (`RAND_ANTEIL`), und genau in ihnen steht das,
was der Mehrschnitt nicht hat."* Gebaut wird etwas anderes: `baue_netz` legt
**jede Schicht über den vollen Bereich `[r_in, r_out]`** an, und die Zuordnung
entscheidet am **Volumenschwerpunkt** (`im_ring = ri <= r <= ro`). Eine
Jochschicht wird von nichts radial zerschnitten, bleibt also EIN Stück, dessen
Schwerpunktradius bei 109,6 mm liegt — mitten im Ring — und wird Eisen. Nur die
Magnetschichten (vom Magnetsektor zerschnitten) und der Spalt werden Luft. Die
Jochfläche des Modells ist damit **1,70-mal** so groß wie die der Scheibe.

**Wirkung, gemessen** (`RAND_ANTEIL` je Lauf gesetzt, Modul unverändert):

| Bauform | Luftrand | Jochfläche | Knoten | B₃D Mitte | Abw. ggü. Mehrschnitt |
|---|---:|---:|---:|---:|---:|
| YASA | 35 % | ×1,70 | 25.784 | 1,1601 T | +5,7 % |
| YASA | 2 % | ×1,04 | 16.877 | 1,1528 T | +6,2 % |
| TORUS-NN | 35 % | ×1,70 | 26.014 | 1,1439 T | +100,6 % |
| TORUS-NN | 2 % | ×1,04 | 17.005 | 0,9377 T | +65,9 % |

**Was daraus folgt — und was NICHT.** Der Überstand ist bei YASA fast
wirkungslos (0,6 % auf B₃D) und bei TORUS-NN groß (18 %), und das ist
physikalisch stimmig: YASA hat kein Ständerjoch, der Fluss geht axial durch den
Zahn; TORUS-NN führt ihn **umfangs im Ständerjoch** — also gerade durch den
Körper, der 1,70-fach zu groß ist.

**Er erklärt die offene +100 %-Abweichung (Befund 6) aber NUR ZUM TEIL**: ohne
Überstand bleiben +65,9 %. Was er erklärt, ist etwas anderes und war bisher
rätselhaft — dass der 3-D-Sektor für YASA und TORUS-NN **fast dasselbe** Feld
lieferte (1,1601 gegen 1,1439 T, 1,4 % auseinander), während der Mehrschnitt sie
klar trennt (1,0661 gegen 0,5518 T). Ohne den Überstand trennt der 3-D-Sektor
sie auch: 1,1528 gegen 0,9377 T, also 19 % statt 1,4 %. **Das überzählige Eisen
hat den Unterschied zwischen den beiden Bauformen verdeckt.**

**Fundstelle.** `ema_axial_em3d.baue_netz`, Schritt 1 (Schichten über
`[r_in, r_out]`) und Schritt 4 (Zuordnung am Schwerpunkt), Modulkopf
`RAND_ANTEIL`.

**Status: behoben am 16.10.2026** — und die Reparatur hat einen zweiten Fehler
freigelegt, den dieser hier verdeckt hatte.

Ausgelöst wurde es von einem Bild: *„ich habe immer noch das Gefühl, dass das
nicht richtig ist — im Bereich der Spulen scheinen die Magnetfeldlinien wie bei
einer Radialflussmaschine zu laufen."* An den exportierten Feldlinien eines
Laufs nachgemessen (219.334 Linienabschnitte, Richtung je Abschnitt in
axial/radial/umfangs zerlegt) war das genau so:

| z-Band | Lage | axial | radial | umfangs |
|---|---|---:|---:|---:|
| Rückenblech | Rückweg | 0,22 | 0,35 | **0,77** ✔ |
| Magnet + Spalt | Durchtritt | **0,90** ✔ | 0,18 | 0,17 |
| **Ständer** | Zähne/Nuten | 0,31–0,39 | **0,56–0,63** | 0,29–0,43 |

Im Überstand stand ein radialer Rückweg offen, den es nicht gibt.

**Die Reparatur, in zwei Teilen.** (1) `baue_netz` baut die Schichten jetzt über
`[ri, ro]`, und der Luftrand ist ein **eigener Körper** über die Stapelhöhe —
die Zuordnung am Schwerpunkt erklärt ihn damit von selbst zu Luft. (2) Danach
fiel auf, dass die Nut auch hier **durch das Joch** schneidet (`lg["d"]`, die
ganze Bandhöhe, statt einer Zahnlänge) — derselbe Fehler wie in
`ema_axial_fdm._nuten`, nur bisher vom Eisenrand überdeckt, der als
Ersatz-Rückweg einsprang. `kenn` entscheidet jetzt über die Zahnbänder, und die
Zahnlänge kommt aus `ema_axial_fdm.zahnlaenge` — derselben Quelle.

**Gemessen** (Elmer, Vorgabemaschine, k = 5, N = 300, Abweichung des
3-D-Ringsektors gegen den Mehrschnitt):

| Bauform | vorher | nur Rand repariert | Rand **und** Joch |
|---|---:|---:|---:|
| YASA | 2,47 % | 1,91 % | **1,91 %** |
| TORUS-NN | 5,52 % | **−55,77 %** | **1,64 %** |

Die mittlere Spalte ist der Beleg für die Paarung: allein repariert fiel
TORUS-NN auf B₃D 0,4966 T gegen 1,0660 T aus dem Mehrschnitt, weil ihm nun
Rand **und** Joch fehlten. YASA ist von Teil (2) unberührt — sein Ständer ist
jochlos (`kenn = "durch"`), und das ist die Gegenprobe.

Am Feldbild nachgemessen: Festkörper jetzt **75,1…130,0 mm** (vorher
55,8…149,2), Ständer **axial 0,60–0,90** statt radial, Rückenblech umfangs
0,82–0,89. Wächter: `test_axial_em3d.py` — das Eisen endet am Ringraum, die
Luft füllt den Rand, auf Zahnhöhe steht Luft im Ringraum und auf Jochhöhe
keine, und beidseitig genutet heißt doppelt so viele Nutkörper.

---

## 2026-10-11 · Alle fünf Maschinenarten durch Elmer, aus der MASKE — und was dabei herauskam

**Beobachtung.** Gefahren wurde die Oberfläche selbst (Chromedriver auf
`localhost:5000`), nicht die CLI: je Art im Geometrie-Reiter `machineType`
setzen, in den Reiter 🧲 3-D-Feld wechseln, Knotenziel 30.000, Betriebspunkt
3000 1/min / 20 Nm, `#e3_btn` drücken, `/em3d/status` lesen. Grundgeometrie das
Bestandsformular (Stator 280 / Rotor 188,6 / Welle 60 / Spalt 0,70 mm, **2p = 16**,
48 Nuten, L = 80 mm, `magShape = spm`).

| Art | Weg | Ergebnis |
|---|---|---|
| PSM | `ema_em3d`, magnetostatisch | ✅ 84 s, 33.606 Knoten, B_gap 3-D 1,494 T gegen 2-D 0,837 T |
| ASM | `ema_em3d_harm`, harmonisch | ✅ 183 s, 74.048 Knoten / 406.080 Tet, 0,2528 T, 6005 Feldlinien — **bei 20 Nm**; bei den Vorgabe-150 Nm abgewiesen |
| SynRM | `ema_em3d`, magnetostatisch | ❌ 23 min im ersten Netzversuch, kein Fortschritt; Server musste neu gestartet werden |
| EESM | `ema_em3d`, magnetostatisch | ❌ 877 s, ganze Selbstheil-Leiter, 3534 entartete Tetraeder — bei **2p = 6** dagegen ✅ 316 s, 33.670 Knoten |
| GSM | — | ✅ Absage nach 13,6 s, mit Grund, Stand und dem ausdrücklichen „es wird NICHT ersatzweise mit PSM-Physik gerechnet" |
| Axialfluss | `ema_axial_em3d`, Ringsektor | ✅ 13 s, 13.785 Knoten — aber unter falscher Überschrift und mit +100 % Abweichung (s. 5/6) |

---

### 1 · Das SynRM-3-D-Netz entsteht aus einem Prisma je POLYGONSEGMENT

`ema_em3d.barrier_rects` (Z. 220–237) zerlegt den Barrieren-Polygonzug und legt
für **jedes Segment** ein eigenes Rechteck-Prisma an. Gemessen bei 2p = 6:
**336 Prismen von 0,885 mm Länge und 10,3 mm Dicke** (2 Barrieren je Pol ×
28 Segmente × 6 Pole); bei 2p = 16 sind es **896**. Das sind stark überlappende
Platten, 12× breiter als lang — der 2-D-Rasterer verträgt das (er stempelt),
OCCs `fragment` macht daraus Sliver.

**`build_mesh` ohne Selbstheil-Leiter, derselbe Payload, nur die Polzahl:**

| 2p | Prismen | Zeit | Ausgang |
|---:|---:|---:|---|
| 4 | 224 | 134 s | 454 entartete Tetraeder |
| 6 | 336 | 415 s | `Invalid boundary mesh (overlapping facets) on surface 316` |
| 8 | 448 | 418 s | 2541 entartete Tetraeder, 4 invertiert |
| 16 | 896 | >23 min | kein Ende in Sicht (aus der Maske) |

**Feiner hilft nicht** — bei 2p = 6 mit `mag_cl` 3,89 (268 s) und 2,0 (351 s)
derselbe `overlapping facets`-Abbruch.

**Und die Decke, die genau das verhindern soll, misst die falsche Kante.**
`_cl_decke` (Z. 3019 ff.) nimmt beim SynRM `ema_synrm_cad.barrieren(...)
["dicke_mm"]` = 10,3 mm und deckelt `mag_cl` auf 0,8 × 10,3 = **8,24 mm**. Die
kleinste Abmessung dieser Körper ist aber ihre **Länge**, 0,885 mm (0,8 × = 0,708
mm) — die Decke ist um den Faktor 12 zu großzügig und greift nie.

**Die Maske bietet es trotzdem an:** `ARTEN["synrm"].stufen` führt `em3d`, der
Knopf ist frei. Die eigens dafür geschriebene Sonderabsage in `run_em3d`
(Z. 3800–3809, „das 3-D-NETZ dieser Bauart ist gebaut und gemessen … was fehlt,
ist ein freigegebener Löserlauf") ist dadurch **unerreichbarer Code**.

**Dazu: ein hängender Netzbau ist nicht abbrechbar.** `/em3d/abort` beendet
`ElmerSolver`; gmsh läuft im Serverprozess und wird davon nicht berührt. Der
Lauf musste über einen Serverneustart beendet werden.

### 2 · EESM: an der Polzahl, nicht am Weg

Bei 2p = 16 lief der Schenkelpollaeufer **877 s** durch die ganze
Selbstheil-Leiter — Netzqualität, Magnet-Mesh ×1,5, Zonenverhältnisse,
Gesamtnetz ×1,8, Taschenkappen aus, Statornuten aus, Wuchtbolzen aus — und
endete mit **3534 entarteten Tetraedern**. Derselbe Knopf, dieselbe Maschine,
nur **2p = 6 / 36 Nuten**: Netz in zwei Vergröberungsschritten auf 33.670
Knoten, Löser durch, **316 s**, B_gap 3-D 0,899 T gegen 2-D-FDM 0,837 T, sechs
Bilder. Der 3-D-Weg der EESM trägt also — er trägt nur nicht die Polzahl, mit
der das Formular dasteht. Das ist dieselbe Klasse wie der SynRM-Befund darüber
(je Pol zwei Spulenquader plus Schuh und Kern, die mit wachsender Polzahl
immer schmaler aneinanderrücken), und vorher gesagt wird es nirgends.

### 3 · Der Ziel-Knoten-Regler wirkt auf dem ASM-Weg nicht — und seine Schätzung gilt dort nicht

Gesetzt 30.000; gebaut hat `ema_em3d_harm` **74.048 Knoten / 406.080 Tetraeder**,
zweimal (mit und ohne Ring). `_run_em3d_harmonisch` (Z. 3924 ff.) liest aus dem
Payload nur `rpm` und `load_nm`; `target_nodes`, `mesh_cl`, `gap_cl`, `mag_cl`
und das Auswahlfeld **Anregung** erreichen ihn nicht. Die Zeile unter dem Regler
(„≈ 1,8 GiB RAM, ≈ 18 s Solve") beschreibt damit einen Lauf, der nicht
stattfindet.

### 4 · Reißt das ASM-Feld, nennt die Absage den falschen Ausweg

Bei 3000 1/min / **150 Nm** (den Vorgabewerten der Karte „Betriebspunkt") liegen
**1,80 % des Volumens über 20 T, größter Wert 683 T**; `ema_em3d_harm` weist ab
— mit dem Satz „Die Feldstufe dieser Bauart trägt dann weiterhin
`cae_cli.py feld2d`". Das schickt vom Browser weg, obwohl der Browser trägt:
**dieselbe Geometrie, dasselbe Netz (406.080 Tetraeder), bei 20 Nm** läuft
derselbe Knopf durch. Gegenprobe über die CLI:
`cae_cli.py feld3d --frisch --set machineType=asm --set p=8 --set slots=48`
baut Ziffer für Ziffer dasselbe Netz und rechnet ebenfalls durch. Gebunden hat
der **Betriebspunkt**, und davon steht in der Absage nichts.
`ema_asm.betriebspunkt` hält beide Lasten für erreichbar (I_s 221,3 A bei 20 Nm,
468,9 A bei 150 Nm gegen 800 A Grenze) — die Schranke liegt also im 3-D-Modell
und nicht in der Maschine, auch das gehört in den Text.

### 5 · Das Axialfluss-Ergebnis erscheint unter der ASM-Überschrift

`_renderEm3d` (`ema.html:10309`) verzweigt auf **`if (res.bericht)`** — einen
Schlüssel, den der Axiallauf genauso trägt. Der Axialfluss bekommt dadurch den
Kopf „🧲 3-D harmonisch — Asynchronmaschine" samt dem Satz über den Käfig, und
`#e3_msg` meldet „✓ 3-D harmonisch (Kurzschlussring) · 13785 Knoten". Die
Zahlen darunter sind die richtigen (die Sektor-gegen-Mehrschnitt-Tabelle), die
Überschrift gehört einer anderen Maschine. Der Unterschied steht im Ergebnis:
axial `art="axial"`, `source="axial_em3d"`, `flussweg`, `sektor`; ASM
`art="asm"`, `source="em3d_harm"`, `harmonisch`.

**Behoben am 11.10.2026.** `_renderEm3d` verzweigt auf
`res.art === 'axial' || res.source === 'axial_em3d'` und gibt dem Ringsektor
eine eigene Karte samt Sektorwinkel. Nachgemessen aus der Maske: „✓ Axialfluss-
Ringsektor · 13.785 Knoten, 75.529 Tetraeder · ein Pol (22,5°)".

### 6 · Axialfluss, TORUS-NN: Sektor und Mehrschnitt um Faktor 2 auseinander — und es ist nicht das Netz

`ema_axial_em3d.vergleich` ist genau dafür gebaut, den `∂/∂r`-Term zu messen, und
gibt seine Abweichung als Ergebnis aus. Gemessen an der Scheibe des Projekts
(Ø 260 mm, λ 0,577, 2p 16, Q 48, Spalt 1 mm):

| Bauform | Zellgrößen | Knoten | Abw. Mittel | max |
|---|---|---:|---:|---:|
| yasa | Reiter (12,0 / 1,5) | 13.756 | +6,2 % | 11,5 % |
| yasa | Modul (selbst) | 99.638 | +5,6 % | 17,1 % |
| torus_nn | Reiter (12,0 / 1,5) | 13.785 | **+100,3 %** | 129,9 % |
| torus_nn | Modul (selbst) | 100.050 | **+99,9 %** | 131,2 % |

**Auflösung ist es also nicht** — 13,8 k und 100 k Knoten geben dasselbe. Die
beiden Wege unterscheiden sich auch nicht um einen festen Faktor: das Verhältnis
3-D/Mehrschnitt wächst über dem Radius von **1,35 auf 2,31**. Wo die Bewegung
herkommt, ist messbar: das **3-D-Feld ist für beide Bauformen praktisch
gleich** (innen/Mitte/außen 0,889 / 1,138 / 0,952 T gegen yasa 0,897 / 1,154 /
0,957 T), der **Mehrschnitt nicht** (0,657 / 0,552 / 0,483 T gegen 1,082 /
1,066 / 1,061 T). Die Schichttabelle trägt das Bauformvorzeichen korrekt
(`ema_axial_fdm.lagen`: yasa `kenn` 1/1, torus `kenn` 1/−1), und
`ema_axial_em3d` liest es (Z. 250) — im Luftspaltfeld des Sektors kommt es
trotzdem nicht an.

Welcher der beiden Wege für NN danebenliegt, ist hier **nicht** entschieden.
Festgehalten ist: für diese Bauform widersprechen sie sich um Faktor 2, und die
Zahl wird ohne jede Plausibilitätsschranke als „die Abweichung IST das Ergebnis"
ausgegeben — der radiale 3-D-Pfad hat dafür `_b_gap_plausibility`, dieser nicht.

**Nebenbefund:** die Netzfelder des 3-D-Reiters sind radiale Vorgaben und werden
unverändert an den Axialpfad durchgereicht (`_run_em3d_axial`, Z. 3854 f.).
`gap_cl = 1,5 mm` ist bei 1 mm Scheibenspalt die **2,25-fache** Zelle gegenüber
dem, was sich `ema_axial_em3d.baue_netz` selbst ausrechnet
(`max(0,4; Spalt/1,5)` = 0,67 mm). An dieser Scheibe gemessen bewegt es wenig
(6,2 statt 5,6 %), beschriftet ist es nicht.

### 7 · Die Taschenwarnung trifft zwei Bauarten, die keine Tasche haben können

Beim PSM-Lauf (`magShape="spm"`) steht im Protokoll und in der Ergebniskarte:
„0 Magnettaschen gebaut, aber 0 als Luft zugeordnet — 3D-Rotor ohne
Flussbarrieren" und „die Magnete sitzen im 3D-Modell in massivem Eisen, die
2D-FDM-Lösung hat Luftkappen". Beides trifft nicht zu: ein Oberflächenmagnet hat
per Bauart keine Tasche (`_use_pockets = _pockets and clr > 0 and bool(_interior)`,
Z. 1479 — `_interior` ist leer), und `ema_analysis._rasterise` legt die Luftkappen
ausdrücklich nur für `placement == "interior"` an (Z. 467), es gibt also auch
keine Abweichung zur 2-D-Lösung. Die Bedingung (Z. 3515) schließt seit dem
20.09.2026 die Bauarten **ohne** Magnete aus (`n_magnets > 0`), nicht aber die
mit **oberflächlichen**; `n_pockets_want > 0` träfe beide. Es ist derselbe
Fehler, den der Kommentar zwei Zeilen darüber beschreibt.

**Und die Oberfläche hat denselben Fehler ein zweites Mal, ungeteilt.**
`ema.html:10369` zeigt den Kasten allein an `res.mesh.n_magnets != null` und
`n_pockets > 0`. Beim **EESM**-Lauf steht dort deshalb wörtlich „🧲 Netz:
**0 Magnete** · keine Magnettaschen — die Magnete sitzen im 3D-Modell in
massivem Eisen … an dieser Maschine gemessen +75 % Grundwelle · Knoten-Ziel
erhöhen und neu rechnen" — für eine Maschine ohne einen einzigen Magneten,
samt Handlungsempfehlung. Die Python-Seite hat diesen Fall am 20.09.2026
ausgeschlossen (`n_magnets > 0`), die Browser-Seite nicht; `n_pockets_want > 0`
wäre die Bedingung, die beide Seiten bräuchten.

### 8 · Vor dem Lauf sagt der 3-D-Reiter nicht, welcher Löser läuft

`_em3dGeomSummaryHtml` (`ema.html:7928`) hat genau einen solchen Satz, und der
hängt am **Flussweg** (Z. 7937). Für die ASM verzweigt `run_em3d` (Z. 3791) nach
`feldweg` in einen anderen Löser mit einem anderen Ergebnis (Ringbefund statt
Kennwerttabelle) — das steht erst hinterher in der Ergebniskarte, drei Minuten
später. Bei der GSM zeigt der Reiter eine gewöhnliche Zusammenfassung und einen
freien Startknopf, obwohl das Auswahlfeld eine Zeile weiter oben „getragen:
analytisch, cad" sagt.

### 9 · Die „Live-Simulation" der Scheibe lief nicht — sie war ein Standbild

**Gemeldet** als „die live simulation der axialflussmaschine funktioniert
nicht". Das stimmte, und meine erste Prüfung hatte am Ziel vorbeigemessen: sie
sah nach, ob ein BILD da ist, nicht ob sich etwas BEWEGT.

**Messung** (Prüfsumme von `#simCanvas`, je 3 s):

| | Stichproben | verschiedene Bilder |
|---|---:|---:|
| Axialfluss | 6 über 15 s | **1** — Pixel für Pixel dasselbe |
| radial (Gegenprobe) | 5 über 12 s | 5 |

Der Lastregler bewegte nichts, der Start/Stop-Knopf stand auf „Start", Drücken
änderte nichts. **Ursache:** `loop()` kehrte im Axialzweig VOR `stepPhysics`,
`rasterizeGeometry`, `solveField` und `draw` zurück; `_axialVorschau` kopierte
einmal je Sekunde zwei fertige Leinwände per `drawImage` herüber. Kein
Läuferwinkel, keine Zeitachse, kein Feld. Der Hinweiskasten sagte, dass die
*Echtzeitdaten* ausgesetzt sind — dass der *Lauf* gar nicht stattfindet, sagte
nichts, und Regler, Start/Stop und der Reitername „▶ Live-Simulation" standen
unverändert da. Dazu verdeckte der Kasten (oben rechts) im Hochformat die obere
rechte Ecke der Zeichnung.

**Behoben am 11.10.2026 — und es ist keine gedrehte Zeichnung.** Dreht sich der
Läufer, ändert sich die Lage Magnet gegen NUT und damit das Feld; `theta`
verschob bisher nur den SCHNITT (`rzBei`), nicht den Läufer. `feld.js` bekam
deshalb `rotorVersatz` — angewandt an genau den zwei Stellen, die zum Läufer
gehören (Magnete, Käfignuten), **nicht** an den Magneten des Scheibenankers,
die am Ständer sitzen. Bei 0 ist jede bisherige Rechnung bitgleich (nachgemessen);
bei einer Polteilung kippt das Feld exakt das Vorzeichen.

Flüssig wird es über die Wiederholung: `live.js` löst **eine Periode** in zwölf
Läuferstellungen (gemessen **1,0 s** für alle zwölf bei 3 Ringen), danach ist
jede Drehung Ablesen (200 Winkel < 1 ms). Die Periode ist dabei **nicht** die
Polteilung, sondern `2π/ggT(2p, Q)` — eine Drehung bildet den Ständer nur bei
einem Vielfachen der Nutteilung auf sich ab (16/48 → 22,5°; 10/12 → 180°, fünf
Polteilungen).

**Ein Vorzeichen war zuerst zu viel, und die Messung hat es gefunden:** am
festen Ort muss das Feld nach einer Polteilung kippen; mit dem zusätzlichen
`(−1)^m` kam es unverändert heraus (1,0149 statt −1,0149 T). Das gelöste Fenster
ist zwei Polteilungen breit und in sich schon antiperiodisch — die starre
Drehung liest von selbst am Gegenpol ab. Wer beides tut, hebt es auf.

Gezeigt werden drei Bilder: die Scheibe von vorn mit `B_z` im Luftspalt, der
abgewickelte Streifen (Zähne stehen, Magnete wandern) und `B_z(θ)` mit
mitlaufender Marke. Die Farbskala wird **einmal** für alle Stellungen gesetzt —
eine je Rahmen neu gewählte atmete mit der Drehung, und eine Änderung der SKALA
sähe aus wie eine Änderung des FELDES.

**Was ausdrücklich NICHT mitläuft:** Moment und Ströme. Das dq-Modell dieser
Leinwand ist das der radialen Maschine; die Drehzahl kommt deshalb vom
Drehzahl-Sollwert (sonst 3.000 1/min), und die **Zeitlupe steht im Bild**
(gemessen 1 : 143) — eine Scheibe bei 3.000 1/min dreht 50-mal je Sekunde, das
sieht niemand, und eine Anzeige ohne diesen Faktor wäre eine Aussage über eine
Drehzahl, die sie nicht zeigt. Der Kasten sitzt jetzt unten und sein Platz wird
von der Zeichenfläche **abgezogen** statt überzeichnet.

Nachgemessen nach dem Umbau: **8 von 8** bzw. **6 von 6** verschiedene Bilder,
Stop hält an, Start läuft weiter, keine Konsolenfehler — und das auch, ohne den
Reiter ⊙ vorher zu öffnen.

### 10 · Dasselbe über den AGENTEN — die Kette trägt, und sie trägt die falsche Aussage mit

Gegenprobe über den zweiten Bedienweg: `cae_cli.py` und ein laufender PI-Kopf.
**Die Verdrahtung ist in Ordnung** — je Art führt das richtige Verb wirklich
durch (`feld2d synrm` 110.259 Dreiecke, Anisotropie 1,719, Bezugsfall glatter
Läufer 1,0002; `feld2d eesm` 108.801 Dreiecke, 1,667, mit ehrlicher Warnung über
89 % Klirranteil; `axial --sektor` 260.824 Knoten, +2,7 % gegen den Mehrschnitt,
dazu Stufe 1 und 2 in einem Aufruf), eine Art am falschen Verb wird mit **Exit 2**
und dem Hinweis auf das richtige abgewiesen (`feld2d pmsm`, `feld3d synrm`,
`feld2d/feld3d gsm`), und `run em3d` für die GSM kommt über HTTP mit **Exit 1**
samt vollständiger Begründung zurück. Ein echter Kopf (PI 0.85.1,
`qwen-gross:latest`, Denken aus) startete gebunden ans Projekt, machte **genau
einen** Werkzeugaufruf, las das Ergebnis, antwortete nach 63 s und legte
`protokoll_*.md` + `ereignisse_*.jsonl` ab, über `/agent/laeufe` und
`/agent/lauf` wieder abrufbar.

**Und genau deshalb ist Befund 1 auf diesem Weg schlimmer, nicht harmloser.**
Der Kopf antwortete wörtlich: „SynRM trägt laut Werkzeug vier Stufen … und das
3-D-Feld. Die Feldstufen laufen über Elmer (2-D wie 3-D)." Das ist korrekt
wiedergegeben — `ARTEN["synrm"].stufen` sagt es —, und es ist falsch. Wer dem
Kopf glaubt, startet einen Lauf, der nicht endet.

**Zwei eigene Lücken auf diesem Weg:**

* `cae_cli.py maschinenart --help` nennt als Codes nur `pmsm|asm|synrm|eesm`.
  Die **GSM fehlt**, obwohl das Verb sie vollständig beantwortet. Ein Agent liest
  die Hilfe und schließt daraus, dass es sie nicht gibt.
* `run em3d --dry-run` druckt den Payload und führt **kein einziges Tor** —
  weder die Maschinenart noch das Rotor-Layout. Für alle sechs Fälle (auch GSM,
  auch SynRM) kommt Exit 0 und ein Payload zurück. Das ist die Stelle, an der ein
  Agent vorher nachsieht, und sie sagt nichts; `rotor-check` führt die Tore
  wirklich, `--dry-run` nicht.

**Status.** **5 und 9 behoben** (11.10.2026, s. dort). Offen bleiben 1, 2, 3, 4,
6, 7, 8 und 10. Keiner der Punkte bewegt eine schon abgelegte Zahl; 1, 2 und 6
sind Rechenbefunde, die übrigen Auskunft und Darstellung.

---

## 2026-10-11 · Die Scheibe hatte keine Festigkeitsaussage — und ihr Lauf ließ sich nicht einmal ansehen

**Beobachtung.** Nach der Reparatur vom 09.10. lief der Axialfluss aus der Maske
durch, aber das Festigkeitskapitel blieb leer: Struktur-FEM und Lamé-Kennlinie
sind für die Scheibe beide übersprungen, und darunter stand nur ein Verweis auf
`cae_cli.py axial`. Ein Weg, den nur die Kommandozeile hat, ist für den, der vor
dem Bildschirm sitzt, nicht vorhanden — dieselbe Regel, die dieses Repo für die
Agentenköpfe aufstellt.

**Messung.** `ema_axial.anzug`/`ruecken`/`bandage` waren gerechnet, getestet und
hatten **keinen Aufrufer in der Pipeline**. Was sie liefern, ist keine Nuance:

| | |
|---|---:|
| axialer Anzug (die HAUPTlast, 8,6 : 1 zum Schub) | 212,4 kPa = **7,52 kN je Luftspalt** |
| negative Steifigkeit um die Mittellage | 30,1 MN/m |
| Rückenblech magnetisch nötig / aus der Durchbiegung | 9,28 / **11,10 mm** (bindend: Durchbiegung) |
| gezeichnet 13,0 mm → Durchbiegung | 62,3 µm = **6,2 % des Luftspalts** (zulässig 10 %) |
| Magnetfliehkraft IN der Scheibenebene bei 6000 1/min | **56,9 kN**, Klebung 1,89 MPa |

**Drei Fehler kamen beim Verdrahten heraus, jeder nur im Browser sichtbar:**

1. **Ein fertiger Axiallauf ließ sich im Browser GAR NICHT öffnen.**
   `renderSummary` griff ungeprüft zu: `s.max_safe_rpm.toLocaleString()` und
   `s.mass_g.toFixed(1)`. Bei der Scheibe sind beide per Konstruktion `null`
   (sie trägt weder Lamé-Ring noch Struktur-FEM, und ihre Masse kommt nicht aus
   dem Zylindermodell). Gemessen: `loadProjectById` brach mit
   `Fehler beim Laden: Cannot read properties of null (reading 'toLocaleString')`
   ab — alle Ergebnisse unerreichbar, obwohl sie auf der Platte lagen. Eine 0
   einzusetzen wäre der zweite Fehler gewesen: sie liest sich wie ein Messwert.
   Jetzt „–" plus „nicht gerechnet".
2. **`GET /field/0` → 404 bei jedem Laden.** Seit die Feld-Animation für die
   Scheibe übersprungen wird, ist `em.field_modes` eine **leere Liste** — und
   `renderField` fiel bei jedem falsy-Wert auf `rotate` zurück und ließ den
   Spieler Rahmen 0 anfordern. `undefined` (Altprojekt ohne Metadaten) und `[]`
   (ausdrücklich keine gerechnet) sind nicht dasselbe.
3. **`ema_axial.ruecken(..., lam=…)` nahm die Blechsorte entgegen und las sie
   nie.** Die Platte rechnete immer mit 200 GPa und ν = 0,30. Heute bewegt das
   keine Ziffer — alle fünf Sorten tragen `E = 200000` MPa und `nu = 0,30`,
   nachgemessen — und genau deshalb war es nicht aufgefallen; eine Signatur, die
   etwas entgegennimmt und wegwirft, ist trotzdem eine Falle für den nächsten
   Werkstoff. Gegenprobe im Test: ein Blech mit E = 100 GPa braucht jetzt mehr
   Dicke.

**Fundstelle.** `ema_pipeline.run_pipeline` (Stufe 6, der `_axial_lauf`-Zweig),
`ema.html:renderSummary`/`renderField`/`showFrame`, `ema_axial.ruecken`.

**Stand: behoben.** `_axial_struktur` ruft die drei Funktionen und baut
**nichts** nach; `_axial_struktur_chart` zeichnet Dicke→Durchbiegung, die
durchgebogene Scheibe im Schnitt und die Magnethaltung über der Drehzahl. Die
Zahlen stehen im `summary` (und damit in Steckbrief, Bericht, `ema_db` und dem
Ergebnisreiter), `ema_sicherheit` bekam ein eigenes Kriterium `durchbiegung`
und sagt beim Axialfluss **nicht** mehr den Satz über „Ringformel" und
„Spannungsspitzen an den Stegen über den Magnettaschen" — den es dort Wort für
Wort nicht gibt.

**Was ausdrücklich NICHT gerechnet wird, und warum keine Höchstdrehzahl
herauskommt.** Der Anzug hängt an B_gap und nicht an der Drehzahl; die
Magnethaltung bräuchte eine zulässige Spannung für Klebung oder Bandage, und
dafür führt dieses Werkzeug **keine Werkstofftabelle** (`LAMINATES`, `MAGNETS`,
`HAIRPIN_MATS` kennen weder Klebstoff noch Faserverbund). Wer eine hat, trägt
sie als `axialKlebeZulMpa`/`axialBandageZulMpa` ein (Feld in ③ Betrieb) und
bekommt ein Ja oder Nein; ohne sie steht die Kraft da und kein erfundener
Querschnitt. Offen bleibt außerdem die **Fliehkraftspannung des Blechs gegen
seine Streckgrenze** — hier steht die Last der MAGNETE auf ihrer Halterung,
nicht die des Blechs auf sich selbst —, und die Verbindung Scheibe–Nabe, die
`ruecken` als starre Einspannung annimmt und an der der größte Hebel sitzt.
Alles drei steht als „Nicht gerechnet" unter dem Ergebnis, im Protokoll und im
Steckbrief.

---

## 2026-10-09 · Der Browser konnte den Axialfluss wählen, aber nicht rechnen

**Beobachtung.** „Axialfluss" in der Fußleiste gewählt, „⚙ Echte Berechnung"
gedrückt — und im Protokollfenster stand ein nackter Traceback:

```
❌ FEHLER: 'axialAktivOD' fehlt -- fuer Axialfluss wird der AKTIVE
Aussendurchmesser gebraucht. … Traceback: ema_pipeline.py:3284 →
ema_axial_cad.pruefen → teile → ema_axial.auslegung:123
```

Dasselbe an der Elmer-Tür („auch geht es in Elmer nicht, ich kann die Geometrie
nicht übernehmen") und bei „🧊 CAD ansehen".

**Messung.** Der Reiter ② Geometrie hat **kein einziges `axial*`-Feld** — die
Scheibe wird im Reiter ⊙ Axialfluss gezeichnet, und das ist Absicht
(`axialfluss/LIESMICH.md`: 643 kB Maske, drei Viertel ihrer `geom`-Felder
bedeuten axial nichts). `buildPayload` schickte deshalb `fluxPath="axial"` **mit
dem radialen Vokabular und ohne eine einzige axiale Zahl**. Nachgestellt mit
genau diesem Payload:

| | vorher | nachher |
|---|---|---|
| `ema_fluss.flaechen` | `ValueError: 'axialAktivOD' fehlt` | 0,011266 m² |
| `ema_axial_cad.pruefen` | derselbe Abbruch | 123 Teile, 12 Magnete, zeichenbar |
| `POST /analyse` (Browserform) | Lauf endet an Stufe 1 | durchgelaufen, **CAD gebaut**: 46 Paare überlappfrei, 3.053.373 mm³, STEP |
| `POST /em3d` | — | Sektor gegen Mehrschnitt −4,5 % im Mittel, 19,6 % max; 31.112 Knoten, 173.923 Tets |

Zweiter, verdeckter Teil desselben Fehlers: **`ema_axial_thermik._geo` las
`axialNutBreiteMm` roh**. Dort ist 0 keine Nut von 0 mm, sondern die Anweisung
„aus `slotWidthRatio` ableiten" (so steht es in `AXIAL_VORGABE`, und so liest es
`ema_axial.nutbreite_mm`, das sich selbst als **die EINE Quelle** ausweist —
siehe den Befund vom 07.10.2026 darunter). Mit `axialNutBreiteMm = 0` starb
deshalb `ema_axial_em3d.baue_netz` an einem Quader der Breite null:

```
Exception: Degenerate box   (gmsh.addBox, ema_axial_em3d.py:116)
```

Gemessen: b_nut **0,000 → 7,563 mm** (abgeleitet aus `slotWidthRatio` = 0,5 bei
Q = 54); eine ausdrücklich gesetzte Nutbreite bleibt unberührt (6 mm bleiben
6 mm). Das war die zweite Quelle für dieselbe Größe — genau die Sorte, gegen die
`nutbreite_mm` gebaut wurde.

**Fundstelle.** `ema.html:buildPayload` (schickte keine axialen Schlüssel),
`ema_axial_thermik._geo` (`"b_nut": _zahl(geom, "axialNutBreiteMm", 6.0)`),
`ema_fluss.axial_vorgabe` (vorhanden, aber **nur** von `cae_cli.py` gerufen —
wieder der Fall „gerechnet und unerreichbar").

**Stand: behoben, in dieser Reihenfolge.**

1. **Der Browser holt die gezeichnete Scheibe.** `buildPayload` liest bei
   `fluxPath = axial` das Formular des ⊙-Reiters (gleicher Ursprung,
   `werteLesen()`) und lässt es über **`POST /axialfluss/geom`** umrechnen —
   dieselbe `ema_fluss.aus_seite`, die auch „↑ ins Projekt übernehmen" benutzt.
   Eine zweite Zuordnungstabelle in JavaScript wäre dieselbe Falle wie die
   handgespiegelte `magnetLegs`. Gemessen schickt die Maske jetzt **22 axiale
   Schlüssel** mit den Werten der Zeichnung.
2. **Der Server füllt, was fehlt — und sagt es.** `ema_fluss.axial_ergaenzen`
   ist `axial_vorgabe` mit Auskunft: es gibt zurück, WAS es gesetzt hat.
   `server._axial_ergaenzen` hängt an vier Türen (`/analyse` über
   `_payload_auffuellen`, `/cad_preview`, `/em3d`, `/em3d/sector`), die Pipeline
   wiederholt es für Warteschlange und `cae_cli.py` (idempotent: ein zweiter
   Durchgang ergänzt nichts). Jede Ergänzung steht im Protokoll, mit dem Satz,
   dass sie ein **Ausgangspunkt und keine Auslegung** ist. Still zu füllen wäre
   der Fehler, gegen den `ema_fluss` überhaupt gebaut ist.
3. **Wo 0 „ableiten" heißt, sagt das Protokoll es** (`NULL_HEISST`): sonst liest
   sich „axialNabeD = 0.0" als ergänztes Maß, und ein Nabendurchmesser von null
   wäre keine Maschine.
4. **`_geo` geht durch `ema_axial.nutbreite_mm`.**

**Zweiter Nebenbefund, beim Nachmessen des reparierten Laufs gefunden:** die
Feld-**Animation** war für den Axialfluss nicht abgeschaltet. Die Standbilder
sind es seit dem 07.10.2026 (`ema_axial_fdm.bilder` statt `em_field.png`, weil
`_field_frame` `hypot(X, Y)` rastert — einen Zylinderschnitt, in dem eine
Scheibe ein Ring ohne Merkmal ist); die Schleife eine Ebene darunter lief
weiter. Gemessen am Browserlauf: **72 Rahmen × ~9 s ≈ zehn Minuten für ein Bild
der falschen Maschine**, unmittelbar nachdem die richtigen Bilder geschrieben
worden waren. Jetzt übersprungen, mit dem Satz, was es statt dessen gibt.
Ersetzt wird nichts: eine bewegte Scheibe bräuchte den abgewickelten
Mehrschnitt über dem Rotorwinkel, und das ist eine neue Stufe, keine Reparatur.

**Nebenbefund, mitbehoben:** die Oberfläche behauptete an drei Stellen, der
Axialfluss trage **kein CAD** („Für die Scheibe gibt es keinen CAD-Aufbau",
„CAD und Struktur-FEM tragen ihn nicht") — veraltet seit `ema_axial_cad`
(07.10.2026); `STUFEN_AXIAL` führt `cad` und `em3d` längst, nur der
Modulkopf von `ema_fluss` und die Maske sagten das Gegenteil. Ebenso der
Smoke-Test: er lief nie mit FreeCAD und hatte **überhaupt keinen axialen
Prüfpunkt**.

---

## 2026-10-07 · Zwei Schlüssel für die Nutbreite — 42 %, und 29 % auf ein Sättigungsurteil

**Beobachtung.** Beim Bauen des Axialfluss-CAD gesucht, wie breit die Nut ist. Ein
Zeichner muss sich entscheiden, und genau dabei fiel auf, dass es zwei Antworten gab.

**Messung** (Vorgabe-Payload, Ro = 130 mm, Q = 48, Nutteilung aussen 17,017 mm):

| Quelle | Nut aussen |
|---|---:|
| `slotWidthRatio` = 0,50 (der RADIALE Schlüssel, den `ema_axial.zahnform` liest) | 8,508 mm |
| `axialNutBreiteMm` (der AXIALE Schlüssel, seit 06.10.2026 im Parametersatz) | 6,000 mm |

**42 % auseinander**, und daraus fielen **B_zahn 1,312 gegen 1,014 T** am Aussenrand —
ein Sättigungsurteil über einen Zahn, den niemand gezeichnet hat. `axialNutBreiteMm`
war ausdrücklich dafür eingeführt worden (*„in mm statt als Verhältnis, weil die Nut
parallelflankig ist"*), und `zahnform` las ihn nicht einmal.

**Fundstelle.** `ema_axial.zahnform` (`swr = geom["slotWidthRatio"]`),
`ema_text2ema.SCHEMA["axialNutBreiteMm"]`, `ema_axial_thermik._geo` (las schon den
axialen Schlüssel).

**Status: behoben.** `ema_axial.nutbreite_mm(geom, r)` ist die EINE Quelle, gelesen von
`zahnform` UND vom CAD. Vorrang hat der axiale Schlüssel; ist er 0, gilt weiter
`slotWidthRatio` und **bestehende Auslegungen bewegen sich um keine Ziffer** (im Test
gegen 1,3125 T festgenagelt). `nutbreite_befund` nennt in jedem Ergebnis, welche
Quelle gilt und was die andere ergeben hätte — 42 % schweigend auszutauschen wäre der
Fehler, den diese Datei verhindern soll.

**Nebenbefund, mitberichtigt:** `zahnform` rechnete die Überhöhung am Innenrand als
`b_aussen/lambda` — eine Näherung. Exakt ist `B_zahn(r) = B_gap·τ_s(r)/(b_zahn(r)·k_fe)`
mit `b_zahn = τ_s(r) − b_nut(r)`, und daraus fällt für den **Keilzahn** die Überhöhung
**exakt 1,000** (die Nutteilung kürzt sich heraus — das ist die Aussage der Zahnform,
und sie soll aus der Geometrie FALLEN, nicht gesetzt sein) und für den parallelen Zahn
1,66 statt der genäherten 1,73.

---

## 2026-10-07 · Der Agent konnte keine Axialflussmaschine anlegen

**Beobachtung.** Gewünscht als „eine Axialflussmaschine soll für den Agenten auch eine
Möglichkeit sein". Nachgemessen war sie für ihn **nicht vorhanden**, in zwei Stufen.

**Messung.** `SKILL.md` — die Unterlage, die der Agent als Autorität liest — enthielt
das Wort „Axialfluss" **null** mal (alle sieben Treffer auf „axial" betrafen die
Getriebe-Baulänge und die 2-D-Grenzen des FDM). Die Verbtabelle führte `axial` nicht,
`maschinenart` nannte fünf Erregungsarten und keinen Flussweg, und `aufgabe`s
`PFLICHTPUNKTE` — die Liste dessen, was vor einem Lauf feststehen muss — hatte keinen
Punkt dafür.

Und selbst wer davon wusste, kam nicht weiter:

```
$ cae_cli.py axial --frisch --set fluxPath=axial
FEHLER: Wandmodus: Auch der kuerzeste Magnet passt nicht zwischen die Waende
```

`frischer_payload` läuft durch `ema_screen.einpassen` — die **radiale**
Taschen-Einpassung. Eine Scheibe hat keine Magnettasche und keine Taschenwände; der
Sektormagnet wird von Klebung oder einer Bandage am Außenrand gehalten. Dahinter lag
die zweite Hälfte: `ema_text2ema.SCHEMA` trägt für die axialen Schlüssel `def: None`
bzw. `0` (die Zeichenseite setzt sie ohnehin alle), ein frischer Payload war also eine
Sammlung von Nullen, und der erste Zugriff darauf starb (`'axialAktivOD' fehlt`).

**Fundstelle.** `.agents/skills/cae-orchestrator/SKILL.md`, `cae_cli.frischer_payload`,
`cae_cli.PFLICHTPUNKTE`, `cae_cli.cmd_maschinenart`, `ema_steckbrief.maschine`.

**Status: behoben.** `ema_fluss.axial_vorgabe` ist die EINE Quelle eines tragfähigen
Startpunkts (die Maschine aus `AXIALFLUSS.md` §1, gegen die alle fünf Stufen gemessen
sind); `frischer_payload(flussweg)` nimmt sie und **überspringt die radiale
Einpassung**, erkannt über `_flussweg_aus_set` — der Agent soll EINEN Schlüssel kennen
(`fluxPath`), nicht zwei Wege ihn zu setzen. `AXIAL_PFLICHT` trennt dabei die
Schlüssel, bei denen 0 „ableiten" heißt (Joch, Nabe, Nutbreite), von denen, bei denen
0 eine Lücke ist — daran scheiterte der erste Anlauf. Dazu: `maschinenart` nennt die
Flusswege **zuerst** samt Weg je Stufe, `PFLICHTPUNKTE` hat den Punkt `flussweg` **vor**
der Maschinenart (er entscheidet mehr), die Verbtabelle führt `axial` und
`maschinenart`, `SKILL.md` hat einen eigenen Abschnitt, und der **Steckbrief** nennt
den Flussweg in Zeile 1 des Maschinenblocks.

**Und der Steckbrief beschrieb eine Scheibe als Zylindermaschine.** Er druckte
`statorOD`/`statorID`/`Luftspalt` — im Payload einer Scheibe nur noch der Rest der
radialen Maske — und „V-Form (IPM)" als Anordnung, weil `magShape` dort auf der
Schemavorgabe stehenbleibt. Jetzt: Scheiben-Außendurchmesser, λ, Bauform, Spaltzahl,
und als Anordnung die **Läuferart** (Sektormagnete / Halbach / Käfig / Scheibenanker).
Das ist die Stelle, an der ein Agent sich orientiert; eine Falschangabe dort pflanzt
sich in jede folgende Entscheidung fort.

---

## 2026-10-07 · Das Axialfluss-CAD — und vier Dinge, die FreeCAD nicht verzeiht

**Beobachtung.** Gewünscht als „jetzt das CAD Modell angehen". Es gab keines: `cad` war
die letzte Stufe, die der Axialfluss nicht trug, weil `ema_freecad` einen Zylinder mit
Nuten in der Mantelfläche zeichnet.

**Status: gebaut** (`ema_axial_cad.py`, `bau_axial.py`, `test_axial_cad.py`). Die
Geometrie steht als **Zahlen** in `teile()` — stünde sie nur im erzeugten Skript, gäbe
es sie genau einmal und weder ein Test noch ein Bild käme an sie heran (derselbe Fall
wie bei `ema_wicklung.hairpin_radien` und `ema_eesm_cad`). Gelesen wird ausschließlich
aus `ema_axial.auslegung`, `ema_axial_fdm.lagen` und der hier neu angelegten
Python-Fassung der Stückelung.

**Gemessen am fertigen Körper**, nicht an den Zahlen davor — alle Varianten:

| Variante | Teile | Volumen | Durchdringung |
|---|---:|---:|---|
| YASA, parallel | 131 | 3.059.700 mm³ | 0 von 46 Paaren |
| YASA, Keilzahn | 131 | 3.058.786 mm³ | 0 von 46 |
| AFIR (zwei Ständer) | 228 | 4.439.032 mm³ | 0 von 43 |
| TORUS NN (mit Joch) | 132 | 3.492.709 mm³ | 0 von 46 |
| einseitig | 115 | 2.573.809 mm³ | 0 von 43 |
| 3×2 Magnetsegmente | 291 | 3.032.399 mm³ | 0 von 46 |
| Halbach, 4 Segmente | 227 | 3.081.218 mm³ | 0 von 46 |
| Käfigläufer | — | — | **abgewiesen mit Grund** |

Jedes Teil ein gültiger Festkörper mit Volumen > 0. Gegen die geschlossene Formel:
Magnet 11.289 gegen 11.291 mm³ gerechnet (0,02 %), Läuferscheibe und Welle exakt, Zahn
10.196 gegen 10.200 mm³.

**Vier Dinge, die beim Bauen schiefgingen** — jedes einzeln tödlich:

1. **`ViewObject` ist in `FreeCADCmd` `None`.** Ein nackter `_o.ViewObject.ShapeColor`
   liess das **ganze** Skript scheitern: 131 Teile gebaut, keines gespeichert, Meldung
   `'NoneType' object has no attribute 'ShapeColor'`. Die Farbe ist Zierat, der Bau
   nicht.
2. **Die Markerzeile trägt Anhang.** `json.loads` auf `AX_TEILE:` warf *Extra data:
   column 8205* — FreeCAD schreibt eigene Meldungen ohne Rücksicht auf Zeilengrenzen.
   Gelesen wird mit `raw_decode`, derselbe Fallstrick wie bei `ema_agent._zerlegen` und
   der `\r`-Fortschrittszeile von FluidX3D.
3. **`makeCylinder(..., angle)` läuft von 0 bis `angle`**, nicht symmetrisch um die
   Mitte — gedreht wird daher um `th_mitte − th_halb`.
4. **Der OCC-Fehlschlagfall.** `common().Volume` liefert bei einem gescheiterten
   Schnitt bitgleich das Volumen eines Operanden (am Planetengetriebe gemessen); die
   Durchdringungsprobe verwirft deshalb jeden Schnitt, der so groß ist wie ein ganzer
   Operand, und meldet ihn als *nicht nachweisbar* statt als Durchdringung.

**Was NICHT gebaut ist, steht an jeder Ausgabe** (`ungeprueft`): Lager, Gehäuse und die
Verschraubung der Nabe (eine Konstruktionsentscheidung, keine Ableitung aus dem
Magnetkreis); die **Bandage** (`ema_axial.bandage` rechnet die Kraft, aber ein
Bandagenwerkstoff steht in keiner Tabelle dieses Werkzeugs); die Wicklung als Windungen
(die Spule ist ein Volumen); und der **Verguss des jochlosen Ständers** — der YASA
bleibt deshalb bewusst MEHRERE Festkörper. Einen Ring zu erfinden hiesse, den
magnetischen Kurzschluss zu zeichnen, den die Bauform gerade vermeidet.

**Zwei radiale Reste fielen dabei auf und sind behoben:** `_struct_sweep` lief auch
weiter (s. Befund vom selben Tag), und die **Berichts-Feldbilder** (`em_field.png`)
entstanden aus `_field_frame`, das `hypot(X, Y)` rastert — ein Ringfeld unter dem Namen
der Scheibe, und das an der Stelle, an der man die Bauart nachsieht. Jetzt zeichnet
`ema_axial_fdm.bilder` den abgewickelten Schnitt und `B_gap(r)`.

**Und die Schichtung stand zweimal.** `stapelhoehe` führte die Lagenschleife für die
Summe, `ema_axial_em3d._lagen` für die Lagen selbst; mit dem CAD wäre es die dritte
Fassung geworden — und genau dort war der erste Entwurf des Elmer-Sektors schon einmal
25 mm zu hoch. `ema_axial_fdm.lagen` ist jetzt die Quelle, `_lagen` eine Hülle, und
`test_axial_cad.py` prüft, dass alle drei Leser dasselbe bekommen.

---

## 2026-10-07 · Aus dem Browser lief KEIN Axiallauf — das Tor prüfte den ganzen Satz

**Beobachtung.** Gemeldet als „ich möchte den FDM Solver aus dem Berechnungs-Tab
starten können". Nachgemessen war es schärfer als gefragt: ein Axiallauf aus der
Oberfläche brach **immer** ab, und zwar bevor irgendetwas gerechnet war.

**Messung.** `_gate_maschinenart` rief für den Axialfluss
`ema_fluss.stufen_pruefen(data, stufen or _ALLE_STUFEN)` — und `stages` ist aus
dem Browser **immer `None`** (die Auswahl gibt es nur im „Stufen nachrechnen"-
Panel). Geprüft wurde damit der volle Satz, der `geometry` und `structural`
enthält, und die wirft:

```
FlusswegNichtUnterstuetzt: Axialfluss: die Stufe(n) geometry, structural
tragen ihn nicht. Getragen waeren hier: drivecycle, field, thermal.
```

Also: der Lauf wies sich selbst ab und nannte dabei korrekt die drei Stufen, die
er hätte rechnen können. Genau diese Lehre stand eine Ebene tiefer schon
ausgeschrieben — `_gate_maschinenart` hatte denselben Fehler bei den
Maschinenarten (vier von fünf brachen bei 4 % ab, weil EINE Stufe woanders
liegt) und war dafür korrigiert worden. Beim Flussweg wiederholte er sich.

**Fundstelle.** `ema_pipeline._gate_maschinenart` (Zeile mit
`stufen or _ALLE_STUFEN`), `ema_fluss.stufen_pruefen`.

**Status: behoben.** `ema_fluss.stufen_aufteilen(geom, stufen)` gibt
`(traegt, uebersprungen)` zurück; `run_pipeline` **verengt** den Stufensatz,
statt ihn abzuweisen, und das Protokoll nennt jede übersprungene Stufe samt dem,
was sie stattdessen rechnet (`ema_fluss.STUFE_STATTDESSEN`). `stufen_pruefen`
bleibt unverändert für den AUSDRÜCKLICH verlangten Einzelschritt — dort ist ein
Nein richtig.

**Vier weitere Tore lagen dahinter, jedes erst nach dem vorigen sichtbar** —
jedes hätte den Lauf einzeln getötet, und keines wäre ohne einen echten
Durchlauf aufgefallen:

1. **`estimate_saliency`** warf `_axial_tor`. Richtig war der Grund (die
   V-Taschen-Salienz der Schemavorgabe, gemessen 2,589, hat eine Scheibe nicht),
   falsch die Härte: **1,0 ist hier die richtige Antwort** — Oberflächenmagnete,
   Ld = Lq, und genau das setzt `ema_axial_fdm.betriebspunkt` ohnehin voraus und
   sagt es in seiner `grenzen`-Liste.
2. **`_analytical_Bgap`** warf ebenfalls. Hier ist weder Werfen noch eine
   radiale Zahl richtig, sondern **Delegieren**: `ema_axial_fdm.eichung_magnet`
   ist die Arbeitsgerade der Scheibe, dieselbe, auf die Zeichenseite und
   Mehrschnitt eichen. Die Abzweigung steht jetzt VOR `geom["statorID"]` — eine
   Scheibe hat keine Statorbohrung.
3. **`ema_thermal.compute_losses`** starb an `int(geom.get("nAx", 1))`: der
   `.get`-Ersatzwert greift nur bei einem FEHLENDEN Schlüssel, nicht bei einem
   vorhandenen mit dem Wert `None` — und `ema_text2ema.SCHEMA` trägt `None` für
   jeden Eintrag, während `ema_fluss.aus_seite` die radialen Magnetschlüssel
   überhaupt nicht setzt. Die Meldung war `⚠ Thermal-Analyse fehlgeschlagen:
   int() argument … not 'NoneType'`, **ohne den Schlüssel zu nennen**. Damit war
   die Thermik für den Axialfluss unerreichbar, obwohl `ema_axial_thermik` sie
   seit dem 06.10. rechnet. Behoben über `ema_thermal._z` an zehn Stellen —
   dieselbe Kur wie `ema_axial_thermik._zahl` einen Tag vorher, also derselbe
   Fehler zweimal in zwei Modulen.
4. **Die analytische Strukturkennlinie lief weiter** und meldete „max. sichere
   Drehzahl ≈ 3000 U/min" für eine Scheibe — aus `_struct_sweep`, der
   Ringspannung eines rotierenden RINGES (Lamé). Sie steht in `summary` und im
   Bericht. Geschützt war sie durch **kein** `_do("structural")`, weil die
   billigen Grundstufen immer laufen. Jetzt übersprungen, `max_safe_rpm` ist
   `None` = *nicht gerechnet*, und wo eine Zahl zum Weiterrechnen gebraucht wird
   (Kennfeld), tritt die angeforderte Höchstdrehzahl ein — ausdrücklich als
   Betriebs- und nicht als Festigkeitsgrenze.

---

## 2026-10-07 · `ema_axial_em3d` war fertig und nur über die Kommandozeile erreichbar

**Beobachtung.** Gefragt als „wie bekomme ich die Axialfluss-Maschine nach
Elmer? Geometrie Axialfluss gibt es dort nicht."

**Messung.** Zutreffend. `ema_axial_em3d` rechnete seit dem 06.10. den
anti-periodischen Ringsektor, war gegen den Mehrschnitt gemessen (+2,5 %) und
hatte 35 Prüfungen — erreichbar war es ausschließlich über
`cae_cli.py axial --sektor`. Der 3-D-Reiter kannte nur zwei Geometriequellen
(Geometrie-Tab / Designer) und keinen Flussweg; `ema_em3d.run_em3d` verzweigte
nach **Maschinenart**, und eine Axialflussmaschine ist payloadseitig eine PSM
(`machineType` bleibt `"pmsm"`) — sie wäre also stillschweigend in den
magnetostatischen Vollmotorweg gelaufen, der konzentrische Zylinder baut.

Dieselbe Lage und dieselbe Antwort wie bei der ASM am 20.09.2026: *derselbe
Knopf, der richtige Löser.*

**Fundstelle.** `ema_em3d.run_em3d` (Verzweigung nach `feldweg`), `ema_fluss`
(kein 3-D-Weg geführt), `ema.html` (`_em3dGeomSummaryHtml`).

**Status: behoben.** `ema_fluss.em3d_weg`/`pruefe_em3d_weg` +
`STUFEN_AXIAL` trägt `"em3d"`; `run_em3d` prüft den **Flussweg VOR der
Maschinenart** und ruft `_run_em3d_axial`. Gerechnet wird nicht nur der Sektor,
sondern `vergleich` — Sektor UND Mehrschnitt auf derselben Geometrie, weil die
Abweichung über dem Radius das Ergebnis ist und ein Sektor allein eine Zahl ohne
Bezug. Gemessen über die Route: 25.784 Knoten, Sektor 22,5°, **+5,7 % im
Mittel**, Randabfall innen 85 % / außen 90 %. Der Reiter sagt jetzt in der
Geometriezusammenfassung, welcher Löser läuft, statt es zu verschweigen.

---

## 2026-10-07 · `build_em_rotor_script` hatte keinen Aufrufer

**Beobachtung.** Beim Einrichten der CAD-Auswahl in der Fußleiste gesucht, was
es überhaupt zu wählen gibt.

**Messung.** `ema_freecad.build_em_rotor_script` (Läufer allein, 95 Zeilen) wird
von **nirgends** gerufen — `grep` über den ganzen Baum findet nur die Definition.
Gebaut wurde ausschließlich der Vollmotor, über `build_cad_preview`.

**Fundstelle.** `ema_freecad.build_em_rotor_script`, `ema_pipeline.build_cad_preview`.

**Status: erreichbar gemacht.** `build_cad_preview` nimmt `cad_modell`
(`vollmotor` = Vorgabe, also jeder bisherige Aufruf unverändert · `laeufer`), und
die Fußleiste wählt es. Für die Scheibe ist das Feld gesperrt und sagt warum:
`ema_freecad` zeichnet einen Zylinder mit Nuten im Mantel, einen CAD-Aufbau der
Axialflussmaschine gibt es nicht.

---

## 2026-10-06 · Die Eichung der Axialfluss-Feldstufe pinnte eine SPITZE auf einen MITTELWERT — 45 %

**Beobachtung.** Der neue Elmer-Ringsektor (`ema_axial_em3d.vergleich`) wurde
gegen den Mehrschnitt gestellt — die Gegenrechnung, für die er gebaut ist. Die
beiden lagen **+49,0 % im Mittel und 68,1 % in der Spitze** auseinander. Das ist
zu viel für einen Geometrieeffekt; der Faktor sah nach einer Definition aus.

**Messung.** Er ist eine. `eichung_magnet` liefert die Arbeitsgerade

    B = Br · hm/(hm + µr·kc·g) · alpha_i = 1,15 · 0,8325 · 0,85 = 0,8137 T

— das `alpha_i` am Ende ist die Polbedeckung, also ein **flussgewichteter
Mittelwert über die Polteilung**. `schnitt()` pinnte darauf die **SPITZE** des
gelösten Feldes (`sf_m = b_an / max(pk_m, 1e-30)`) und meldete anschließend eine
**GRUNDWELLE** (`b_n_grundwelle_T = 2·|k[h1]|`). Drei verschiedene Größen:

| | Wert | Verhältnis |
|---|---:|---:|
| Mittel `Br·perm·alpha` | 0,8137 T | 1,000 |
| Spitze `Br·perm` | 0,9573 T | 1,176 |
| Grundwelle `4/pi·Br·perm·sin(alpha·pi/2)` | 1,1852 T | **1,457** |

Nachgemessen am Schnitt bei r = 102,5 mm: `b_n_spitze_T` = 0,81374 T gegen
`eichung_magnet` = 0,81374 T, also **auf sechs Stellen dieselbe Zahl** — die
Spitze war wirklich auf den Mittelwert gepinnt.

**Und eine zweite Hälfte, die sich dazu multipliziert.** Gepinnt wurde die Spitze
des **genuteten** Feldes, und die ist kein Maß für den Fluss: über einem Zahn ist
er gebündelt. Gemessen steigt die rohe Spitze durch die Nutung um **23,5 %**,
während die rohe Grundwelle um 9,6 % **fällt**. Genau dieser Befund stand schon
im Docstring von `carter()` zwei Funktionen weiter — *„an der Grundwelle und
ausdrücklich **nicht an der Spitze**: … ein Carterfaktor von 0,82, also kleiner
als eins, was es nicht geben kann"* —, und dieselbe Datei eichte trotzdem an der
Spitze. Ein Modul, das an einer Stelle weiß, dass ein Maß untauglich ist, und es
an der anderen als Anker nimmt.

Das Verhältnis Grundwelle/Spitze trennt beides sauber:

| | ohne Nut | mit Nut | Rechteck alpha=0,85 |
|---|---:|---:|---:|
| Grundwelle/Spitze | **1,2257** | 0,9056 | 1,2381 |

Der nutlose Verlauf trifft die Fourierreihe der Rechteckwelle auf **1,0 %** —
Löser und Wellenform sind also in Ordnung, und der ganze Fehler saß im Anker.

**Fundstelle.** `ema_axial_fdm.schnitt` (Eichung), `ema_axial_fdm.eichung_magnet`
(der mehrdeutige Rückgabewert), `ema_axial_fdm.carter` (der Docstring, der es
schon wusste).

**Status: behoben.** Drei **benannte** Anker statt eines mehrdeutigen —
`eichung_magnet_spitze` (Flachdachwert, der einzige, den Modell und Löser gleich
definieren), `eichung_magnet_grundwelle` (Fourier-Grundwelle) und
`eichung_magnet` (unverändert der Mittelwert, jetzt im Docstring als solcher
benannt, damit die vorhandenen Aufrufer Ziffer für Ziffer gleich bleiben).
`schnitt()` eicht an der **Spitze des NUTLOSEN Begleitlaufs** gegen
`eichung_magnet_spitze`; der Nutungsverlust wird damit **gemessen** statt aus
`KC` angenommen. Kosten: ein zweiter Lösererlauf je Schnitt.

Gemessen danach, derselbe Vergleich:

| r [mm] | 3-D | Mehrschnitt alt | neu | Abw. alt | Abw. neu |
|---:|---:|---:|---:|---:|---:|
| 76,1 | 1,0135 | 0,8163 | 1,0794 | +24,2 % | −6,1 % |
| 89,9 | 1,1242 | 0,7352 | 1,0775 | +52,9 % | +4,3 % |
| 117,4 | 1,1618 | 0,7376 | 1,0623 | +57,5 % | +9,4 % |
| | | | | **+44,9 %** | **+2,5 %** |

**Der Rest ist das Ergebnis, nicht der Fehler:** die Abweichung wechselt von
innen nach außen das Vorzeichen, weil der Mehrschnitt über r flach ist
(1,079 → 1,062 T, −1,6 %) und das 3-D-Feld steigt (1,0135 → 1,1618 T, +14,6 %).
Das ist genau der `d/dr`-Term, den der Mehrschnitt fallen lässt — die Größe, für
die der Sektor gebaut wurde.

**Nebenwirkung, die die Stufe besser macht.** Die Schnittkonvergenz von `psi`
sprang vorher, weil jeder Schnitt an SEINER EIGENEN genuteten Spitze geeicht war
und die davon abhängt, wo bei diesem Radius eine Nut gegenüber dem Magneten
steht: der Eichfaktor sprang von Schnitt zu Schnitt. Jetzt liegt **k=2 bei 1,2 %**
gegen k=8, wo vorher mehr als 8 % gefordert waren. `test_axial_fdm.py` hielt das
alte Verhalten als Anforderung fest („k=2 ist deutlich zu grob") — die Erwartung
ist nachgezogen und sagt, warum.

**Die Zeichenseite hatte denselben Fehler, Zeichen für Zeichen.**
`axialfluss/feld.js:eichung` rechnete `bAn = BR * perm * p.alpha` und
`sf = bAn / pk` — dieselbe Verwechslung in einer zweiten Implementierung, und
damit genau der Fall, für den dieses Repo seine JS↔Python-Spiegeltests hat. Sie
ist mitberichtigt (nutloser Begleitlauf, Anker `BR * perm`), und der Spiegel in
`test_fluss.py` prüft es jetzt, indem er `feld.js` **mit `node` ausführt** statt
die Formel abzuschreiben — die Abschrift stand bis dahin dort und hätte die
Änderung der Zeichenseite nicht sehen können.

**Ein Zwischenstand, der verworfen wurde, und warum** (er sah besser aus): als
Anker zuerst die **Grundwelle** statt der Spitze — ein Integral über die ganze
Spaltlinie statt eines Maximums auf einer getreppten Kante, also numerisch
ruhiger. Der Test hat es gefangen: eine Grundwelle trägt die Polbedeckung UND
die Fugen der Magnetstückelung, der Bezugslauf trägt sie auch, und im Verhältnis
kürzen sie sich heraus — mit 1-mm-Fugen fiel B1 nur noch von 1,1350 auf
1,1359 T (0,1 %) statt um 11,7 %. Ein Regler, dessen Wirkung die Eichung
wegnormiert, ist derselbe Fehler wie der Ständerstrom vor seinem Umbau. Die
**Spitze** ist der richtige Anker, weil sie genau das misst, was die Formel
beschreibt und nichts sonst: `Br·perm` ist der Flachdachwert unter einem
Magneten, unabhängig von Bedeckung, Stückelung und Nutung — alle drei bleiben
damit im gemeldeten Wert.

**Was NICHT mitgeändert wurde und offen bleibt,** steht als eigener Befund
darunter (`(2/pi)` auf einem Mittelwert).

---

## 2026-10-06 · Das Staenderjoch war auf alpha² bemessen — 28 % zu duenn

**Beobachtung.** Beim Durchsehen aller Aufrufer von `eichung_magnet` (s. Befund
darüber) fiel `_jochhoehe` auf.

**Messung.** Dort stand

    phi = eichung_magnet(geom) * a["polbedeckung"] * pi*(ro²-ri²)/poles

— `eichung_magnet` **trägt die Polbedeckung schon**, sie ist ja der
flussgewichtete Mittelwert. Noch einmal multipliziert bemisst das Joch auf
`alpha² = 0,7225` des Flusses, den es führen muss. Am Beispiel (Ro 130 mm,
λ 0,577, 2p 16, YASA): abgeleitetes Ständerjoch **7,889 statt 10,919 mm**, also
28 % zu dünn.

**Die Gegenprobe steckte daneben:** das Rückenblech wird von `ema_axial.ruecken`
bemessen, das den Doppelzähler nicht hat, und kommt auf **11,102 mm**. Beide
führen den halben Polfluss umfangs über ähnliche Fläche, müssen also beieinander
liegen — 7,889 gegen 11,102 mm war der sichtbare Widerspruch, den niemand
verglichen hatte. Nach der Berichtigung 10,92 gegen 11,10 mm (1,6 %).

**Fundstelle.** `ema_axial_fdm._jochhoehe`.

**Status: behoben**, und `test_axial_fdm.py` vergleicht Ständerjoch gegen
Rückenblech, damit der Doppelzähler nicht zurückkommt. Betroffen war nur die
**abgeleitete** Höhe; wo `axialJochStaenderMm` gezeichnet ist, gewinnt weiter das
Gezeichnete, und dann ändert sich nichts.

---

## 2026-10-06 · `(2/pi)` auf einem schon gemittelten B — BEHOBEN am 16.10.2026

**Beobachtung.** `ema_axial_fdm.betriebspunkt` rechnet

    psi = p * (2/pi) * b_gap * a_fluss      mit b_gap = eichung_magnet(geom)

Das `(2/pi)` ist der Mittelwert einer Halbsinuswelle über ihre Halbperiode, die
Formel erwartet also eine **Amplitude** — das ist die Hauskonvention des
Radialpfads (`psi_pm = p·(2/pi)·B_gap·R·L`, wo `B_gap` aus `_analytical_Bgap`
amplitudenartig ist). Axial bekommt sie einen **Mittelwert**.

**Messung.** Der Fluss je Pol ist `eichung_magnet · A_pol` (das IST der Mittelwert
über die Polteilung); die Formel liefert `(2/pi)·0,8137·A = 0,518·A`, also **36 %
weniger**. Sichtbar wird das am Verhältnis der beiden Momentwege, das die Stufe
ohnehin ausgibt und als `widerspruch` benennt: gemessen **4,18…4,85 über 25…200 Nm**
(16 % Spanne, also eine Normierung und keine Stromabhängigkeit).

**Warum es hier nicht geändert wird.** Es bewegt `Kt`, `psi`, das Moment und jede
daraus gerechnete Temperatur **jedes** Axialfluss-Projekts, und es greift in die
Normierungsbrücke ein, mit der dieses Werkzeug seit jeher rechnet (eine Windung
je Nut, `ema_asm.k_norm = pi·k_w·N_ph/p²`). Eine Berichtigung gehört gegen eine
bekannte Maschine gemessen, nicht nebenbei mitgenommen — und still zu ändern wäre
genau das, wogegen diese Datei existiert.

**Fundstelle.** `ema_axial_fdm.betriebspunkt` (`psi = p*(2/pi)*b_gap*a_fluss`),
`ema_axial_fdm.felder` (`T_verhaeltnis`, `widerspruch`).

**Status: behoben am 16.10.2026** (eigener Eintrag oben). Gemessen wurde es
dann doch nicht an einer Fremdmaschine, sondern an drei Dingen, die schärfer
sind: am direkt integrierten Fluss des gelösten Verlaufs, an der Hausbrücke
`k_norm` (sie geht nur mit der Grundwelle auf, 1,0000 gegen 0,6866) und am
eigenen Löser desselben Moduls, dessen `psi` seit jeher aus der Grundwelle
kommt. `formfaktor_grundwelle` bringt den Mittelwert auf die Grundwelle, an
beiden Stellen. Die vermutete Richtung dieses Eintrags stimmte; die Begründung
„`_analytical_Bgap` ist amplitudenartig" war dagegen nur zur Hälfte richtig —
für Oberflächenmagnete ist auch sie `Br*perm*alpha`, und warum der radiale Pfad
damit trotzdem trägt, steht im neuen Eintrag. `T_maxwell` bleibt der von der
Eichung unabhängige Weg.

---

## 2026-10-06 · `dict.get(k, ersatz)` schuetzt nicht gegen ein ausdrueckliches `None`

**Beobachtung.** Beim Bauen von `test_axial_em3d.py` brach die Thermik mit
`TypeError: float() argument must be a string or a real number, not 'NoneType'`
ab — mitten in `_geo`, und die Meldung nannte den Schlüssel nicht.

**Messung.** `float(geom.get("axialNabeD", 0) or geom.get("shaftD", 60))`: der
Ersatzwert einer `dict.get` greift nur bei einem **fehlenden** Schlüssel, nicht
bei einem vorhandenen mit dem Wert `None`. Und `ema_text2ema.SCHEMA` trägt für
**jeden** axialen Schlüssel `default: None` — wer einen Payload aus dem Schema
aufbaut (wie jedes Testfile hier und `cae_cli --frisch`), bekommt Nullen. Sieben
Stellen in `_geo` hatten dieselbe Falle.

**Fundstelle.** `ema_axial_thermik._geo`.

**Status: behoben** über `ema_axial_thermik._zahl(geom, schluessel, ersatz)`, das
`None` und `""` als FEHLT behandelt — an einer Stelle statt siebenmal.

---

## 2026-10-06 · Der Laeufer der Scheibe drehte sich nicht — gefunden an einer Bildreihe

**Beobachtung.** Auf den Wunsch nach Frames in den Projektordnern entstand eine
Bildreihe ueber den Laeuferwinkel (`ema_axial_fdm.frames`). Zwei Frames, 180°
elektrisch auseinander, sahen **gleich** aus.

**Messung.** Der Schwerpunkt von `j_magnet` ueber eine ganze elektrische
Periode:

| Winkel mech | 0,00° | 5,62° | 11,25° | 16,88° | 22,50° |
|---|---:|---:|---:|---:|---:|
| Magnetschwerpunkt | 40,170 | 40,170 | 40,170 | 40,170 | 40,170 mm |

Jeder Winkel gab **dasselbe Raster**. `rastere_scheibe` nimmt `rotor_winkel`
entgegen, reicht ihn aber nur an `_nuten` weiter, wo er die Phase der
STAENDERstroeme verschiebt; die Magnete klebten an `X % tau_p`.

**Status: behoben.** `x_rot = X - rotor_winkel·r·1000` verschiebt das
Polmuster; Laeufer und Stromwelle wandern damit zusammen und der Lastwinkel
bleibt stehen — genau wie im radialen `_rasterise`. Nachgemessen:

* nach einer **vollen** elektrischen Periode ist das Raster identisch (max|Δ| = 0),
* nach einer **halben** (= eine Polteilung) exakt umgepolt (0 von 57.600 Zellen daneben),
* und ein Achtel weiter sieht es anders aus.

`test_axial_fdm.py` nagelt alle drei fest. **Aufgefallen ist es nur am Bild** —
die 53 bestehenden Pruefungen liefen gruen, weil keine den Winkel bewegte.

---

## 2026-10-06 · Drei Bauhöhen für dieselbe Scheibe, und zwei Schlüssel für den Ständer

**Beobachtung.** Beim Bau des Elmer-Ringsektors (Stufe 3) musste dessen
Schichtung mit der des Mehrschnitts übereinstimmen — sonst vernetzt das
3-D-Modell eine andere Maschine als die, gegen die es gemessen werden soll.
Gemessen auf **einer** Geometrie:

| | Bauhöhe |
|---|---:|
| `ema_axial_fdm.stapelhoehe` | 61,2 mm |
| `ema_axial_thermik.stapelhoehe` | **65,0 mm** |
| erster Entwurf `ema_axial_em3d._lagen` | **90,0 mm** |

Drei Zahlen, drei Module. **Zwei Ursachen:**

1. **Der erste Sektor-Entwurf schrieb die Schichtung ein drittes Mal auf** und
   legte beim YASA zwei Zahnbänder übereinander (90 statt 65 mm). Die
   kanonische Tabelle steht in `ema_axial_fdm._BAUFORMEN` und trägt zusätzlich
   das **Magnetvorzeichen** (`kenn`) — den ganzen Unterschied zwischen YASA
   (NS, Fluss axial durch den Zahn) und TORUS (NN, Fluss umfangs im Joch). Wer
   sie neu schreibt, verliert das.
2. **Zwei Schlüssel für dieselbe Größe.** Der Ständer hieß im Mehrschnitt
   `slotDepth` (die *radiale* Nuttiefe) und im axialen Parametersatz seit dem
   06.10.2026 `axialZahnLaengeMm`. Beide haben die Vorgabe 25 — sie fielen also
   nur **zufällig** zusammen. Ebenso das Rückenblech: `ema_axial_fdm`
   *rechnete* es aus dem Fluss (11,10 mm), während die Zeichenseite
   `axialJochLaeuferMm` = 13,00 mm liefert.

**Status: behoben.** `ema_axial_fdm.statorhoehe` ist die eine Quelle für die
Ständerhöhe und bevorzugt den axialen Schlüssel; `_rueckenhoehe` und
`_jochhoehe` nehmen das **GEZEICHNETE** vor dem gerechneten. Das ist die
richtige Arbeitsteilung: hier die Geometrie, und ob sie reicht, sagt weiterhin
`ema_axial.ruecken`. `ema_axial_em3d._lagen` liest `_BAUFORMEN` statt eine
dritte Beschreibung zu führen. Danach: **65,00 / 65,00 / 65,00 mm.**

---

## 2026-10-06 · Der Schwerpunkt trennt den Magneten nicht von seinem Loch

**Beobachtung.** Der Sektor meldete **vier** Magnete, wo es zwei gibt (eine
Lage je Läuferscheibe).

**Messung.** Eine Magnetlage besteht aus dem Ringsektor-Magneten (Bogen
0,85·Polteilung, Ri…Ro) in einer Schicht, die radial bis in die Lufträder
reicht. Nach `occ.fragment`:

| Stück | Volumen | r | θ |
|---|---:|---:|---:|
| Magnet | 11 289,1 mm³ | 104,48 mm | **11,25°** |
| Rest der Schicht | 11 267,9 mm³ | 113,31 mm | **11,25°** |

Der Rest ist ein **C um den Magneten herum** — und sein Flächenschwerpunkt
liegt auf demselben Winkel und im selben Radiusband. Die Winkelprobe
(`|θ − α/2| ≤ Bogen/2`) erklärte deshalb beide zu Magneten.

Es ist dieselbe Lektion wie in `ema_em2d_stat` („die Fläche allein genügt
nicht: die 54 Statornuten sind flächengleich") und in `ema_em3d`
(`single=True`, weil Magnet-Prisma und Tasche denselben COM teilen) — hier nur
mit dem Winkel statt der Fläche.

**Status: behoben.** Klassifiziert wird über die **Fragment-Karte**: `fragment`
nennt zu jedem Eingabekörper seine Ausgabestücke, und nur den Magneten
beansprucht der Magnet-Eingang. Dieselbe Technik wie im radialen Ein-Pol-Sektor.
Danach 2 Magnete und 3 Nuten je Polteilung (48 Nuten / 16 Pole = 3 ✓).

---

## 2026-10-06 · Die Feldbilder waren Dateien mit 95 % Durchsicht

**Beobachtung**, gemeldet als: *„hier ist der hintergrund durchsichtig. hat das
einen grund? insgesamt wäre ein schwarzer hintergrund als std. besser."*

Gemessen an den erzeugten PNG:

| | Alphakanal | durchsichtige Fläche |
|---|---|---:|
| `frames_feld/` (ASM, SynRM, EESM, GSM) | ja | **94,7 %** |
| `frames_axial/`, `frames/` (Pipeline) | nein | 0,0 % |

**Es hatte einen Grund, und der Grund trägt nur die halbe Strecke.**
`ema_feldbild` macht die Deckkraft zur Flussdichte (`durchsicht_cmap`): wo kein
Fluss ist, ist nichts zu sehen, man schaut durch die Maschine auf das, was
Fluss führt. `_leinwand` setzte dafür `fig.patch.set_alpha(0)`. In der rechten
Agentenspalte liegt das Bild auf einem dunklen Schachbrett (`.kachel
img.durchsicht`) und sieht richtig aus — **als Datei im Projektordner** liegt es
auf dem weißen Grund des Bildbetrachters und sieht falsch aus. Dieselbe Falle,
die `ema_agent.html` für die Kachel schon gelöst hatte, nur eine Ebene weiter.

**Status: behoben, ohne die Idee aufzugeben.** `GRUND = "#0d1014"` ist die neue
Vorgabe, die Durchsicht wird darauf VERRECHNET statt als Alphakanal in die
Datei geschrieben. Das Bild sieht aus wie zuvor auf dem Schachbrett, die Datei
ist aber überall richtig. `_leinwand(grund=None)` gibt die alte Fassung, und
`_speichern` liest die Entscheidung aus der Leinwand statt sie ein zweites Mal
zu treffen. `test_feldbild.py` misst die Aussage weiter nach — nur in
HELLIGKEIT statt in Alpha: ein gutes Viertel der Fläche muss dunkel sein
(„die Luft ist unsichtbar"), und der weggeschnittene Sektor muss dunkler sein
als das volle Bild.

**Zwei Dinge fielen beim Nachsehen auf und sind mitbehoben:**

* Auf der FESTEN Leinwand (Bildreihe) wird alles abgeschnitten, was außerhalb
  der Achse liegt — der Titel verlor links wie rechts Buchstaben, und eine
  mehrzeilige Farbleistenbeschriftung war gar nicht zu sehen. Jetzt stehen die
  Ränder von Hand (`subplots_adjust`), und der Titel ist kurz (`GSM —
  Läuferwinkel 0,0° mech` statt des vollen Artnamens).
* **Was die Farben bedeuten, stand nirgends** — ebenfalls gemeldet. Die Leiste
  trug nur „Flussdichte |B| (T) — Deckkraft = |B|". Die Legende nennt jetzt
  jede Schicht: Feldlinie (eng = viel Fluss), hell/weiß = hohe Flussdichte,
  violett/dunkel = wenig bis kein Fluss, grau = Blechumriss (Geometrie, kein
  Feld), rot = Magnet. Dass die Leiste ihre Farben VOLL deckend zeigt, während
  sie es im Bild nicht sind, steht als Kommentar an der Stelle — sonst liest
  jemand aus ihr die Deckkraft ab.

---

## 2026-10-06 · Eine Feldbildreihe ohne Erregung, und eine mit wackelnder Leinwand

Zwei Fehler im selben neuen Weg (`ema_feldbild.frames`, die Bildreihe fuer die
vier Arten, fuer die die Pipeline keine Frames schreibt):

**1. Kein Feld.** Die erste Reihe fuer die ASM zeigte nur die GEOMETRIE:
Farbleiste 0,00 … 0,30 T und nichts darin. Grund: eine magnetlose Maschine im
Leerlauf hat keine Quelle — ohne Magnet und ohne Strom ist das Feld null.
Behoben, indem der Betriebspunkt aus der ART kommt (`ema_asm.betriebspunkt`
usw., gemessen i_q = 569 A fuer die ASM, 566/566 fuer den SynRM, 800 A fuer die
EESM, 620 A fuer die GSM) und **nicht** aus `estimate_dq_currents`: die rechnet
MTPA ueber eine Salienz, die auf `magnet_legs` steht und fuer diese Arten
nichts bedeutet. Danach mittlere Bildaenderung zwischen zwei Frames 13,35 von
255 statt 0,54.

**2. Wackelnde Leinwand.** `_speichern` schneidet mit `bbox_inches="tight"` auf
den Inhalt zu — fuer ein EINZELbild richtig, fuer eine Reihe falsch: ueber zehn
Frames kamen zwei Breiten heraus (1411 und 1431 px, weil der Titel mit dem
Laeuferwinkel mal drei- und mal vierstellig ist), ffmpeg machte daraus ein
1412 px breites Video und skalierte acht von zehn Bildern. Das Wackeln sieht
aus wie eine Bewegung der Maschine. Behoben mit `fest=True` (feste Leinwand,
kein Zuschnitt); danach alle zehn Frames 1395 × 1395.

**Und was dabei KEIN Fehler war:** eine erste Messung meldete „ASM dreht
nicht" und „GSM dreht um −8°". Beides war der Messaufbau: der Abtastkreis lag
bei der ASM im massiven Eisen UNTER den Kaefigstaeben, und −55,25° beim EESM
ist bei 60° Polteilung dasselbe wie +4,75°. Dicht unter dem Laeuferrand
gemessen drehen **alle fuenf** radialen Arten richtig (5,0° befohlen → 5,00 bis
5,25° gemessen). Das steht hier, damit die Fehlmeldung nicht als Befund
stehenbleibt.

---

## 2026-10-06 · Die EESM-Feldstufe brach an einem Rundungssplitter ab

**Beobachtung.** Beim verlangten Durchlauf aller Varianten lief `cae_cli.py
feld2d` fuer SynRM sauber durch und brach fuer die **EESM** ab:

    Koerper 'rotoreisen' (2.2 mm^2 bei (0.0|0.0) mm) nicht wiedererkannt
    -- die Zuordnung Name->Elmer-Nummer waere geraten
    Netz: 108801 Dreiecke, 54613 Knoten, 72 Koerper

Das Abweisen ist richtig: `zuordnen` erkennt eine Gruppe nach ElmerGrids
Umnummerierung an Flaeche UND Schwerpunkt wieder, und ein 2,2-mm²-Splitter am
Ursprung ist kein Griff. Falsch war, dass es diesen Koerper ueberhaupt gab.

**Ursache.** `rotoreisen` ist eine **Restgruppe**: das Laeuferblech, soweit es
kein Zeichenteil belegt. Beim Schenkelpollaeufer kacheln die Teile die Scheibe
aber vollstaendig — gemessen 37 Teile (12 Polschuhe, 12 Kerne, 12 Spulen, ein
Jochring) —, uebrig bleiben nur Rundungssplitter der Booleschen Operationen:
**2,2 mm² bei 27.936 mm² Laeuferflaeche, also 0,008 %.** Das Blech steckt
vollstaendig in der Gruppe `laeuferpole`.

Unauffaellig blieb es, weil die anderen Bauarten einen echten Rest lassen: beim
Kaefiglaeufer das Blech zwischen den Nuten, beim Reluktanzlaeufer das Eisen
zwischen den Flussbarrieren.

**Status: behoben.** Ein Rest unter `REST_MIN_ANTEIL` (1e-3 der Laeuferflaeche)
wird **kein** Koerper mehr, und der Befund steht als `rest_befund` im Ergebnis
statt zu verschwinden. Nachgemessen laeuft die EESM danach durch: Anisotropie
1,667, Linearitaet **2,000x** (die Probe, die ein linearer Loeser bestehen
muss), Bezugsfall glatter Laeufer 1,0002. Dass der Klirranteil dort 89 %
erreicht, ist kein Fehler, sondern die Bauart — ausgepraegte Pole mit Luecken
dazwischen —, und die Stufe sagt es.

---

## 2026-10-06 · Die Thermik kennt nur die PSM — ASM, EESM und GSM bekommen fremde Verluste

**Beobachtung.** Beim verlangten Durchlauf aller Varianten (je ein Projekt, je
`stages={"thermal","drivecycle"}`) kamen drei Zeilen **Ziffer für Ziffer
gleich** heraus:

| Variante | B_gap | T_Wicklung | P_total | WLTP |
|---|---:|---:|---:|---:|
| PSM | 0,630 T | 46,5 °C | 320,6 W | 14,419 kWh/100 km |
| **ASM** | 0,800 T | **47,7 °C** | **404,3 W** | **14,456** |
| SynRM | 0,283 T | 45,0 °C | 211,6 W | 14,371 |
| **EESM** | 0,800 T | **47,7 °C** | **404,3 W** | **14,456** |
| **GSM** | 0,800 T | **47,7 °C** | **404,3 W** | **14,456** |
| Axial | 0,814 T | 44,0 °C | 191,5 W | 13,744 |

Drei verschiedene Maschinen, eine Temperatur. (Dass B_gap bei allen dreien
0,800 T ist, ist dagegen RICHTIG — es ist `geom.bZielT`, eine Vorgabe und kein
Ergebnis.)

**Ursache.** Die Thermikstufe rechnet ihre Verluste mit
`ema_thermal.design_point_losses`, und das ist das Verlustmodell der
**permanenterregten** Maschine: Statorkupfer über die Stromdichte,
Statoreisen über `B_gap²·m_st`, Magnet-Wirbelstrom, Lager. Was eine ASM, eine
EESM oder eine GSM thermisch AUSMACHT, kommt darin nicht vor. Jede Art rechnet
es selbst (`ema_asm.verluste`, `ema_eesm.verluste`, `ema_gsm.verluste`) — nur
liest das niemand:

| Art | Thermikstufe | die Art selbst | Faktor | was fehlt |
|---|---:|---:|---:|---|
| ASM | 404,3 W | **797,6 W** | 2,0 | Käfig 333,8 W |
| EESM | 404,3 W | **469,9 W** | 1,16 | Erreger 116,4 W + Schleifring 64,0 W |
| GSM | 404,3 W | **4443,8 W** | **11,0** | Bürsten 1240,4 W, Ankerkupfer 2943,3 W |

Beim Gleichstrommotor ist es **Faktor elf**: gemeldet werden 47,7 °C für eine
Maschine, die 4,4 kW verheizt. Der Bürstenabfall allein (1240 W bei 800 A über
zwei Kohlekontakte) ist größer als alles, was das LPTN überhaupt kennt — und er
steht in `ema_gsm` ausgerechnet daneben.

**Zweiter, kleinerer Teil: Magnetverlust ohne Magnete.** Dieselbe Rechnung wies
ASM, EESM und GSM **9,5 W Magnet-Wirbelstromverlust** zu. `P_Mag_unseg = 0,005·P_Cu
+ 0,02·P_Fe·(f/200)²` steht auf Kupfer und Eisen und fragt nicht, ob es etwas
gibt, worin ein Wirbelstrom fließen könnte.

**Status: der kleinere Teil behoben, der größere NICHT.** `compute_losses` setzt
`P_Mag_unseg = 0`, wo `ema_maschinenart.hole(...).hat_magnete` falsch ist —
das ist eindeutig und kostet drei Zeilen.

Die **Kopplung der artspezifischen Verluste ins LPTN ist offen**, und zwar
bewusst: sie ist keine Verdrahtung, sondern eine Physikentscheidung. Die fünf
Wärmequellen des Netzes sind Wicklung, Ständereisen, Läufereisen, Magnet und
Welle; ein **Käfigverlust** gehört an den Läuferknoten, eine **Erregerwicklung**
auch — aber sie ist eine WICKLUNG auf dem Läufer, und das Netz hat dafür keinen
eigenen Knoten mit eigener Isolationsgrenze. Der **Bürstenverlust** entsteht am
Kommutator, also weder im Eisen noch in der Wicklung. Das still zu verdrahten
hieße, diese Zuordnungen im Vorbeigehen zu treffen; sie gehören erst
entschieden, dann gebaut (`AXIALFLUSS.md`-Muster: Stufe benennen, dann bauen).

**Was bis dahin gilt:** für ASM, EESM und GSM ist die Temperatur der Thermikstufe
eine **untere Schranke** und als solche zu lesen. Die belastbaren Verlustzahlen
stehen in `ema_asm`/`ema_eesm`/`ema_gsm` und sind über `cae_cli.py` erreichbar.

---

## 2026-10-06 · Ein Teil-Lauf ohne Strukturstufe bricht am Ende ab

**Beobachtung.** Gefragt wurde, woher der Knopf „Echte Berechnung" weiß, ob er
axial oder radial rechnet. Beim Nachgehen lief ein Teil-Lauf
(`stages={"thermal","drivecycle"}`) vollständig durch — Thermik gerechnet,
beide Fahrzyklen gerechnet, Temperaturen im Protokoll — und brach **danach** ab:

    TypeError: unsupported operand type(s) for *: 'NoneType' and 'int'
    ema_pipeline.py:4087   f_el = rpm_fem * int(geom["p"]) / 60

`rpm_fem` wird erst in der **Strukturstufe** gesetzt. Wird die übersprungen,
ist sie `None`, und der Werkstoffblock ganz am Ende rechnet damit.

**Nicht axialspezifisch.** Gegengeprüft mit einem **radialen** `--frisch`-Payload
und `stages={"thermal"}`: derselbe Abbruch. Das trifft also jedes „🔁 Stufen
nachrechnen", das die Struktur-FEM nicht mit anhakt — und das ist der Normalfall,
wenn man eine vergessene Thermik nachzieht.

**Unauffällig blieb es,** weil der äußere Fang die Ausnahme in ein „❌ FEHLER"
im Protokoll verwandelt, die bis dahin gerechneten Ergebnisse aber stehen lässt.
Von außen sieht es aus wie ein Lauf, der fertig wurde und sich am Schluss
beschwert.

**Status: behoben.** `_rpm_eisen = rpm_fem if rpm_fem else rpm_to` — `rpm_to`
ist die Drehzahl, auf die sich der Rest der Zusammenfassung ohnehin bezieht.
Der Eisenverlust-Schätzwert `materials.P_fe_W_est` bezieht sich dann auf sie
statt auf die FEM-Drehzahl; bei einem vollen Lauf ändert sich nichts.

---

## 2026-10-06 · „Echte Berechnung" konnte nicht sagen, welche Maschine sie rechnet

**Beobachtung**, und die Frage war genau richtig gestellt: `ema.html` enthielt
`fluxPath` **null** mal. Der Schlüssel existierte nur im Schema. Dass ein axial
geladenes Projekt trotzdem axial rechnete, lag an einer einzigen Zeile in
`applyPayload` (`for (const [k,v] of Object.entries(G)) GEOM[k] = v; // incl.
input-less keys`) und am `{...GEOM}` in `buildPayload` — also an einem
Durchreichen, das niemand als Entscheidung geschrieben hat.

**Zwei Folgen, beide schlecht:**

1. **Nichts zeigte es.** Der Knopf hieß „⚙ Echte Berechnung", und welche der
   beiden Maschinen er rechnet, stand nirgends — bis Stufe 0 im Protokoll
   abwies.
2. **`GEOM` überlebt in `localStorage`.** Ein `fluxPath: "axial"` aus einer
   früheren Sitzung bleibt damit hängen und macht den nächsten, radial
   gemeinten Entwurf axial — dieselbe Falle, die bei `customLegs` schon einmal
   zugeschlagen hat („nur Durchmesser übernommen, Magnete ignoriert").

Es ist derselbe Befund wie bei `machineType` am 18.09.2026, dessen Behebung in
`buildPayload` zwei Zeilen darüber steht: *„Ohne diese Zeile rechnete der
Browser IMMER eine PSM."*

**Status: behoben.** Eigenes Auswahlfeld **vor** der Maschinenart (der Flussweg
ist die Entscheidung davor — er bestimmt, ob der Luftspalt ein Zylindermantel
oder eine Ringfläche ist), `buildPayload` setzt ihn ausdrücklich,
`applyPayload` stellt ihn zurück, und der Knopf heißt bei axialem Flussweg
**„⚙ Echte Berechnung (axial)"**. Darunter steht, welche Stufen dann laufen und
welche Stufe 0 abweist.

---

## 2026-10-06 · Stufe 0 prüfte an der Scheibe radiale Maße und fand sie gut

**Beobachtung.** Beim ersten Pipelinelauf einer übernommenen Scheibe meldete das
Grenzen-Tor:

    🛡 Luftspalt 0.700 mm ✅
    🛡 Wickelkopf aussen 246.4 mm gegen Stator 280.0 mm ✅
    🛡 Nuttiefe 25.0 mm in 45.0 mm Statorwand ✅

Die Maschine hat **1,0 mm** Luftspalt und einen Ringraum von **260 mm**. Die
geprüften Werte sind die `--frisch`-Schemavorgaben, die
`_payload_auffuellen` unter den Payload legt; auf einer Scheibe bedeuten
`statorID`, `rotorOD`, `airGap` und `slotDepth` nichts. Ein grünes Urteil über
Maße, die es nicht gibt, ist schlechter als keine Prüfung.

Zwei weitere Tore **stürzten ab** statt zu urteilen: `_gate_rotor_layout` mit
`KeyError: 'layout'` (für die Scheibe gibt `rotor_layout_check` kein `layout`
zurück — sie hat keine Magnettaschen in einem Querschnitt senkrecht zur Achse),
und `_gate_rotor_stress` ließ die `FlusswegNichtUnterstuetzt` von
`rotor_stress_check` durch und beendete damit einen Lauf, der Thermik und
Fahrzyklus rechnen sollte.

**Status: behoben.** `_gate_grenzen_axial` prüft, was die Scheibe wirklich hat:
den **axialen** Luftspalt gegen dieselbe Spanne `ema_grenzen.LUFTSPALT_MM` und
die λ-Schranke am Innenrand aus `ema_axial.lambda_grenze` — dort wird die Nut
zu schmal, und das ist die Grenze, die diese Bauart bindet (gemessen
λ_min = 0,2351 gegen gewählte 0,5770). Die beiden Rotor-Tore fangen den
Flussweg-Einspruch und **sagen**, wo die Scheibe statt dessen gerechnet wird
(`ema_axial.ruecken` für die Durchbiegung unter dem axialen Anzug,
`ema_axial.bandage` für die Fliehkraft in der Scheibenebene).

---

## 2026-10-06 · Die beiden Axialfluss-Stufen hatten keinen einzigen Aufrufer

**Beobachtung.** `ema_axial.py` (Stufe 1, analytisch) und `ema_axial_fdm.py`
(Stufe 2, abgewickelter Mehrschnitt) sind am 05.10.2026 gebaut und getestet
worden — 69 bzw. 50 Prüfungen, alle grün. Beim Zusammenführen der Zeichenseite
fiel auf, dass sie **außerhalb ihrer eigenen Tests nirgends gerufen werden**:
`ema_pipeline` ruft sie nicht, `cae_cli.py` hatte kein Verb, `server.py` keine
Route, `ema.html` keinen Knopf. Ein `grep` über den Baum ergibt außer
`test_axial*.py` und einem Kommentar in `ema_rotorcheck` keinen Treffer.

Das ist dieselbe Lage wie bei den Agentenläufen vor `/agent/laeufe` und bei den
Parameterstudien vor ihrer Ablage: gerechnet und unerreichbar ist dasselbe wie
nicht gerechnet.

**Status: behoben.** Verb `cae_cli.py axial` (beide Stufen, `--stufe
analytisch|feld|beides`), Route `POST /axialfluss/rechnen`, Reiter
**⊙ Axialfluss** in `ema.html`. Dazu `GET /axialfluss/vorgabe` und
`POST /axialfluss/uebernehmen` als Weg ins Projekt, und
`ema_fluss.SEITE_FELDER` als die EINE Zuordnung Feldname ↔ Schemaschlüssel.

---

## 2026-10-06 · Die beiden Feldstufen widersprechen sich — und nur eine konvergiert

**Beobachtung.** Mit der Zusammenführung standen zum ersten Mal zwei
unabhängige Feldlöser auf derselben Scheibe: `ema_axial_fdm` (Python,
quadratisches Gitter, Eisenpolsterung) und `axialfluss/schnitt.js` (JS,
rechteckiges Gitter mit **schichtbündigen** Gitterlinien). Sie geben
verschiedene Antworten.

**Messung** (identische Geometrie: Ro 130, λ 0,577, 2p 16, Q 48, Spalt 1 mm,
Magnet 6 mm; Arbeitsgerade analytisch **0,8137 T**):

| Löser | B_gap über r [T] | Mittel | gegen analytisch |
|---|---|---:|---:|
| JS, schichtbündig | 0,8378 0,8322 0,8137 0,8247 0,8214 | 0,826 | **+1,5 %** |
| Python, gleichmäßig | 0,7516 0,7158 0,7100 0,6921 0,6988 | 0,711 | **−12,6 %** |

Und die entscheidende Gegenprobe — **konvergiert die Python-Stufe über N?**

| N | 300 | 450 | 700 | 1000 |
|---|---:|---:|---:|---:|
| Mittel [T] | 0,7109 | 0,7363 | 0,7594 | 0,7350 |
| gegen analytisch | −12,6 % | −9,5 % | −6,7 % | −9,7 % |

Nein. Sie wandert ohne Richtung, und der radiale **Verlauf kippt dazu**: bei
N = 450 steigt B_gap nach außen, bei N = 1000 fällt es. 37 s bei N = 1000, und
die Zahl steht immer noch nicht. Der JS-Löser konvergiert auf derselben
Geometrie monoton (8,99 → 3,86 → 3,20 → 0,43 → 0 %).

**Ursache** ist die schon am selben Tag gemessene: das gleichmäßige Gitter
lässt die dünnen Schichten (1 mm Spalt) darauf *schnappen*, und eine halbe
Zellbreite Versatz ändert den wirksamen Spalt um Prozente.
`ema_analysis._build_fv_matrix` rechnet mit EINER Maschenweite auf
quadratischem Gitter — ein schichtbündiges, ungleichmäßiges y bräuchte dort
einen eigenen Matrixaufbau. Das ist der Preis dafür, bisher den HausLöser
unverändert benutzt zu haben, und er ist damit beziffert.

**Status: gemessen und BENANNT, nicht repariert.** Der Umbau von
`ema_axial_fdm` auf ein schichtbündiges Gitter ist der nächste Schritt und
nicht Teil dieser Zusammenführung — still mitten im Lauf zu reparieren hieße,
dass die Zahlen davor und danach aus zwei verschiedenen Werkzeugen stammen,
ohne dass man es ihnen ansieht (s. `ema_werkzeugstand.py`). Statt dessen:

* `ema_axial_fdm.felder` führt die Nicht-Konvergenz samt Zahlen in seiner
  `grenzen`-Liste, also sieht sie **jeder** Aufrufer;
* `cae_cli.py axial` schreibt bei mehr als 3 % Abweichung ausdrücklich
  „das ist überwiegend das GITTER, nicht die Physik" darunter — ohne den Satz
  liest sich −6,7 % wie ein Streuungs- oder Sättigungseffekt;
* belastbar ist bis dahin der Wert des Reiters ⊙ Axialfluss.

**Was dabei ÜBEREINSTIMMT, und das ist die Gegenprobe:** beide Wege eichen auf
dieselbe Arbeitsgerade `Br·hm/(hm + µ_r·kc·g)·α`. Python rechnet 0,81370 T,
die Zeichenseite 0,81370 T — Ziffer für Ziffer, über zwei getrennte
Implementierungen. In `test_fluss.py` festgenagelt. Der Unterschied steckt
also wirklich im Löser und nicht in der Modellannahme.

**Zweiter Punkt, der dabei zusammenpasst:** Stufe 1 sagt für den parallelen
Zahn `B_Zahn ~ 1/r`, also innen/außen = Ro/Ri = **1,73×**. Der JS-Mehrschnitt
misst **1,68×**. Zwei unabhängige Wege, 3 % auseinander — die Aussage der
Bauart trägt auf beiden.

---

### Nachtrag 06.10.2026, späterer Tag: **die Ursache oben ist falsch** — behoben

Die gemessene Streuung war echt. Die **Begründung war es nicht.** Der Verdacht
fiel auf das gleichmäßige Gitter, weil derselbe Befund am selben Tag für die
JS-Seite gemessen und dort durch schichtbündige Gitterlinien behoben worden war
— eine naheliegende Übertragung, und sie war die falsche.

Wirkliche Ursache war die **Eichung**: geeicht wurde an der Spitze des
**genuteten** Feldes, und die sitzt auf einer getreppten Zahnkante, deren Lage
mit N wandert. Also wanderte der Eichfaktor, nicht das Feld. Dazu war der Anker
ein Mittelwert, wo eine Spitze stand (eigener Befund weiter oben). Nach der
Berichtigung, gleiche Geometrie, gleiche Stufe:

| N | 300 | 450 | 700 |
|---|---:|---:|---:|
| Mittel B_gap(r) | 1,0656 T | 1,0655 T | 1,0643 T |

**0,1 % über eine Verdopplung von N**, auf demselben gleichmäßigen Gitter, das
hier als Ursache benannt war. Der Umbau auf ein schichtbündiges Gitter ist damit
**nicht nötig** — das ist der eigentliche Wert dieses Nachtrags, denn er war als
„nächster Schritt" vorgemerkt.

**Und die drei Löser liegen jetzt beieinander** (dieselbe Scheibe, Leerlauf;
analytische Grundwelle der Arbeitsgeraden ohne Nut 1,1852 T):

| Weg | Mittel | gegen analytisch |
|---|---:|---:|
| `axialfluss/schnitt.js` (JS, schichtbündig) | 1,0819 T | −8,7 % |
| `ema_axial_fdm.felder` (Python, gleichmäßig) | 1,0643 T | −10,2 % |
| `ema_axial_em3d` (Elmer 3-D, Ringsektor) | ~1,10 T | −7,2 % |

Drei unabhängige Löser innerhalb von **3 %**, und die −8…−10 % gegen die
analytische Grundwelle sind der **gemessene Nutungsverlust**: `carter` misst an
derselben Scheibe 1,096, also −8,8 %, wo die Arbeitsgerade mit angenommenen
`KC = 1,15` rechnet.

**Mitgezogen wurden die Stellen, an denen das Werkzeug das Alte über sich
sagte** — eine stehengelassene Selbstaussage ist schlimmer als keine:
`ema_axial_fdm.felder`s `grenzen`-Liste, der `⚠ … überwiegend das GITTER"`-Satz
in `cae_cli axial` (jetzt ein `ⓘ` über die Nutung), die Monotonie-Behauptung in
`axialfluss/pruefe.js` (gemessen ist die Konvergenz **beschränkt**, ±1,8 %, aber
nicht monoton — die frühere Monotonie kam daher, dass ein Verhältnis zweier
korrelierter Größen aus EINEM Lauf gemeldet wurde, was einen Teil des
Diskretisierungsfehlers herauskürzt) und die Spiegelprüfung in `test_fluss.py`,
die den JS-Anker **als Formel abgeschrieben** hatte und ihn jetzt mit `node` aus
`feld.js` ausrechnen lässt.

---

## 2026-10-06 · Der Ständerstrom der Ansichtsseite war ein Regler, der nichts tat

**Beobachtung.** Beim Bau des Achsschnitts (`axialfluss/schnitt.js`) sollte der
Stromwinkel β dazu — die Größe, über die eine Drehzahländerung in einem
magnetostatischen Feld überhaupt sichtbar wird. Dabei fiel auf, dass schon der
vorhandene Regler „Ständerstrom" nichts bewegt.

**Messung** (`axialfluss/feld.js`, 16 Pole, 48 Nuten, Grundwelle der
Normalkomponente in der Spaltmitte, ungeeicht):

| `last` | B₁ | Ankeranteil |
|---:|---:|---:|
| 0 | 8,9067e5 | — |
| **200** (Reglerrand ±400) | 8,9073e5 | **0,01 %** |
| 10 000 | 8,9866e5 | 0,90 % |
| 100 000 | 1,3412e6 | 50,6 % |

Über seinen **ganzen** Stellbereich bewegte der Regler das Feld um 0,02 %.

**Ursache.** `iq` stand roh im Quellterm (`J[k] += -iq*sin(el)`), während die
Magnete als `curl M` mit `magAmp = Br/(µ₀·µ_r) ≈ 8,7e5` und geteilt durch `dx`
in **denselben** Vektor gingen — ein Verhältnis von rund 6·10⁶. Es gab also
keine Einheit, in der die Zahl im Eingabefeld etwas bedeutet hätte; der Wert
daneben war beliebig und das Ergebnis entsprechend.

**Status: behoben, und zwar ohne Eichfaktor.** Der Löser ist linear, also ist
`A = A_Magnet + A_Anker`. `feldGitter` führt den Ständerstrom jetzt in einem
eigenen Vektor `Js` mit **Einheitsamplitude**, `loeseFeld` löst beide Teile und
setzt den Ankeranteil auf `last` Prozent der **Magnet-Grundwelle im Spalt** —
gemessen, nicht geeicht. Das Feld heißt deshalb nicht mehr „Ständerstrom",
sondern **„Ankerrückwirkung [%]"**: 100 % heißt „Ankerfeld so stark wie der
Magnet". Anders als `COIL_J_SCALE` im 3-D-Pfad (an EINER Maschine geeicht, was
dort auch dasteht) gibt es hier keine Konstante, die bei einer anderen
Geometrie danebenläge.

**Zwei Dinge, die dabei falsch gewesen wären und gemessen auffielen:**

1. **Über die SPITZE normiert geht die Rechnung nicht auf.** Die Spitze des
   Ankerfeldes sitzt über der Nut und ist eine örtliche Zacke; gekoppelt wird,
   was als Grundwelle umläuft. Mit der Spitze als Maß ergab β = ∓90° bei
   `last` = 100 % nicht die erwartete Summe (gemessen 0,301 T statt 0 T bzw.
   1,616 T). Über die **Grundwelle** normiert schließt die Algebra: β = −90°
   gibt 1,6162 T gegen ein gefordertes 2 × 0,8082 = 1,6164 T (0,01 % daneben),
   β = +90° gibt 0,0216 T (soll 0), β = 0 gibt 1,433× gegen √2 = 1,414×
   (der Überschuss sind die Harmonischen des Ankerfeldes). Die **Eichung**
   bleibt dagegen eine Spitze — die Arbeitsgerade `Br·hm/(hm+µ_r·kc·g)` ist ein
   Spitzenwert. Zwei Maße für zwei Zwecke, beide im Quelltext benannt.
2. **Geeicht werden darf nur der MAGNETanteil.** `eichung` pinnte die Spitze
   des SUMMENfeldes auf die magnetische Arbeitsgerade — dann hängt der Maßstab
   an der Last, und jede Last sähe gleich stark aus. Gemessen bewegte sich die
   Grundwelle dadurch um 0,0 %, obwohl der Ankeranteil längst richtig skaliert
   war. `loeseFeld` reicht deshalb `pkMag` durch. Das ist derselbe Fehler, den
   das Hauptwerkzeug schon einmal hatte („die Magnete werden unter Last
   ignoriert", s. `CLAUDE.md`, geteilte Eichung in `run_em_analysis`) — und
   dieselbe Lösung.

**Fundstelle.** `axialfluss/feld.js` (`feldGitter`, `loeseFeld`, `eichung`),
Prüfungen in `axialfluss/pruefe.js` §10.

**Was dadurch teurer wird:** unter Last zwei Lösungen je Gitter statt einer.
Im Leerlauf (`last = 0`) ist der Weg Ziffer für Ziffer der alte, `Js` ist dann
überall null und wird nicht gelöst.

---

## 2026-10-06 · Das Halbach-Array der Ansichtsseite trug die doppelte Polzahl

**Beobachtung.** Beim Einbau einstellbarer Magnet- und Zahnzahlen in
`cae_orchestrator/axialfluss/` fiel auf, dass die Magnetisierung des
Halbach-Arrays an drei Stellen einzeln ausgeschrieben war — in der Draufsicht,
in der Abwicklung und im Feldlöser — und zwar überall als

    seg = 4;  My = [1, 0, -1, 0][idx % 4]          mit  w = tau_p / 4

Das sind vier Segmente **je Polteilung** und eine volle Drehung der
Magnetisierung über dieselbe Strecke. Eine Halbach-Wellenlänge sind aber **zwei**
Polteilungen: über eine Polteilung dreht die Magnetisierung 180°, nicht 360°.
Das gezeichnete Array hatte damit die doppelte Polzahl der Einstellung daneben.

**Messung** (`axialfluss/pruefe.js` §7, 16 Pole, 4 Segmente je Polteilung,
Fenster = 2 Polteilungen breit, Harmonische der Normalkomponente in der
Spaltmitte):

| | Grundwelle (λ = 2 τ_p) | 2. Harmonische (λ = τ_p) |
|---|---:|---:|
| alte Regel | 2,087e4 | **5,472e5** |
| berichtigt | **5,605e5** | 1,609e4 |

Die alte Regel legte also das **26-fache** in die Harmonische, die zur doppelten
Polzahl gehört; berichtigt trägt die Grundwelle das **35-fache** der zweiten.
Bei 2p = 16 zeichnete und rechnete die Seite eine 32-polige Maschine.

**Zweiter Teil: `Mx` fehlte im Quellterm.** `feldGitter` setzte nur `My` und
rechnete `J = dMy/dx`; der Kommentar begründete das damit, die x-Komponente
stecke „im Sprung zwischen den Segmenten und damit ohnehin in curl M". Das gilt
für `dMy/dx`, nicht für den zweiten Term: `(curl M)_z = dMy/dx − dMx/dy`, und
`−dMx/dy` ist ein Flächenstrom auf der **oberen und unteren** Fläche des
Magnetbandes. Bei Sektormagneten ist `Mx = 0` und der Term wirklich null — beim
Halbach trägt er die halbe Erregung, und gerade die Umfangskomponente ist der
Grund, aus dem ein Halbach-Array den Fluss einseitig bündelt.

**Fundstelle.** `axialfluss/ansicht.js` (Draufsicht und Abwicklung),
`axialfluss/feld.js:feldGitter`. Dass es drei Fassungen waren, ist derselbe
Befund in klein: die Datei `geometrie.js` ist ausdrücklich dagegen gebaut
(„zwei Beschreibungen derselben Geometrie wären genau die Drift"), die
Magnetbelegung stand trotzdem daneben.

**Status: behoben.** `geometrie.js` führt jetzt `magnetSegmente`,
`magnetRinge` und `magnetRichtung` als die EINE Quelle; `magnetRichtung` dreht
`π/nU` je Segment über `pol + k/nU`, also 180° je Polteilung. Die Segmente sind
dabei so gelegt, dass das erste die **Polgrenze** überspannt (dort tangential)
und das mittlere auf der **Polachse** steht (dort normal) — die klassische
Anordnung. `pruefe.js` §7 misst beides und führt die alte Regel als Gegenprobe
mit, damit der Befund nachprüfbar bleibt statt nur behauptet zu sein.

**Was NICHT betroffen ist:** die Sektormagnete. Ein Magnet je Pol reproduziert
den Stand vor dem Umbau Ziffer für Ziffer (B1 0,80818 T, in `pruefe.js` §6
festgenagelt), und die vier Prüfungen 1–5 stehen unverändert.

**Offen bleibt `ema_axial_fdm.py`**: dort gibt es noch gar keinen Halbach-Zweig
(`_BAUFORMEN` kennt yasa/torus_nn/afir/einseitig, alle mit Sektormagneten), die
Bauart ist auf dem Python-Weg also nicht etwa falsch, sondern nicht vorhanden.
Wer sie dort einbaut, nimmt `magnetRichtung` als Vorlage und nicht die alte
Zeichnung.

---

## 2026-10-06 · B_gap war sehr wohl konvergierbar — es lag am gleichmäßigen Gitter

**Widerruft den Befund vom 05.10.2026** („B_gap(r) aus dem Mehrschnitt ist NICHT
konvergiert"). Dort stand, die Amplitude oszilliere über N = 320…1280 zwischen
0,874 und 0,973 T, weil der 1-mm-Luftspalt und der 6-mm-Magnet auf das Gitter
schnappen — und daraus folgte die Einschränkung, nur Verhältnisgrößen seien
belastbar. Die Beobachtung stimmt, der Schluss war zu früh.

**Gemessen am JS-Feldlöser der Ansichtsseite** (`axialfluss/feld.js`, derselbe
abgewickelte Schnitt, eigenes Gitter). Mit gleichmäßigem dy, rechteckig statt
quadratisch — also ohne den Quadratzwang und ohne Polsterung:

    72×60   84×78   120×106  168×146  192×160
    0,79201 0,76763 0,86127  —        0,80873   T     → ±6 %, nicht monoton

Mit **y-Linien auf den Schichtgrenzen** (ungleichmäßiges dy, jede Grenze ist
eine Zellfläche, der Luftspalt bekommt mindestens 5 Zeilen):

    60×58   84×78   120×106  168×146  228×195
    0,85351 0,81333 0,80818  0,78649  0,78313   T
    Abweichung zum feinsten: 8,99 %  3,86 %  3,20 %  0,43 %  0

**Monoton fallend.** Es ist also kein prinzipielles Problem des kartesischen
Rasters, sondern eine Folge davon, dass die Gitterlinien die dünnen Schichten
schneiden statt auf ihnen zu liegen. Der Spalt ist dann exakt 1 mm, gleich wie
fein gerechnet wird.

**Was daraus für `ema_axial_fdm.py` folgt:** derselbe Umbau ist dort möglich und
würde die Einschränkung aufheben. Er ist allerdings nicht gratis —
`ema_analysis._build_fv_matrix` rechnet mit EINER Maschenweite und einem
quadratischen Gitter; ein ungleichmäßiges y bräuchte einen eigenen
Matrixaufbau. Das ist der Preis dafür, bisher den Hauslöser unverändert benutzt
zu haben, und er ist jetzt beziffert.

**Zwei weitere Messungen aus demselben Lauf:**

*CG schlägt SOR um Faktor 40.* Der Operator ist SPD (Finite Volumen, harmonisch
gemittelte Flächenleitwerte, Dirichlet) — bei µr-Sprüngen 1 → 500 verdirbt die
Kondition genau SORs Rate. Gemessen auf 120×100: SOR ω=1,95 braucht 5000
Durchgänge / 4,1 s, Jacobi-vorkonditioniertes CG 451 Schritte / 0,10 s, beide
auf B1 = 0,77118 T.

*Die Flussbilanz schließt.* Ständermitte führt **89 %** des Spaltflusses (Rest
streut über die Nuten), und beide Luftspalte führen denselben Fluss
(Verhältnis 1,000) — der Fluss geht wirklich axial durch den Zahn und kehrt
umfangs im Joch zurück. `axialfluss/pruefe.js` misst das ohne Browser nach,
5 Prüfungen.

**Nicht geändert:** der Faktor ~3 zwischen den beiden Momentwegen
(Normierungsunterschied, BEFUNDE 05.10.2026) ist davon unberührt — er hängt
nicht am Gitter.


## 2026-10-06 · Kapitel 2 der Dissertation gelesen — drei Stellen des Axialflussbaus sind falsch

Gestern habe ich die Quelle **gefunden und nicht gelesen** und stattdessen aus
Allgemeinwissen gebaut. Nachgeholt (Igelspacher, Diss. TU München 2018/2020,
Kap. 2 „Axialfluss-Asynchronmaschinen mit Käfigläufer", S. 5–13). Drei Befunde
gegen den eigenen Bau, alle wörtlich belegbar.

**1. `ema_axial.zahnform` kennt die richtige Nutform nicht — beide Fälle sind falsch.**

> „verlaufen die Nuten radial und werden **parallelflankig** ausgeführt, da die
> Anzahl an Leiter bzw. deren Abmessungen sich in radialer Richtung nicht
> verändern. Als Konsequenz werden **die Zähne von kleinen zu großen Radien hin
> breiter**, weshalb der kritische Punkt bei Betrachtung der Zahninduktionen
> **beim Innenradius** liegt. Hierin liegt auch die Tatsache begründet, dass die
> Flussdichte in den Zähnen von Axialflussmaschinen **mit steigendem Radius
> abnimmt**."

Gebaut sind zwei Fälle: `keil` (b_Zahn ∝ r, also konstantes `slotWidthRatio`)
und `parallel` (b_Zahn konstant). Die wirkliche Bauart ist **keiner von beiden**:
parallelflankig ist die **NUT**, also `b_nut = const` und

    b_zahn(r) = 2*pi*r/Q − b_nut        →   B_zahn(r) = B_gap · tau_s(r) / (b_zahn(r)·k_fe)

Das fällt mit r (richtig) und läuft gegen `B_gap/k_fe` für große r. Meine
Vorgabe `keil` liefert B_zahn **konstant über r** — die Quelle sagt ausdrücklich
das Gegenteil. Der kritische Punkt am Innenradius stimmt bei mir zufällig, aber
aus dem falschen Grund (ich hatte ihn nur im Fall `parallel`).

**2. `ema_axial.lambda_grenze` bindet an der falschen Größe.**

> „Da die Windungen radial verlaufen, befindet sich außen und innen ein
> Wickelkopf bzw. im Falle eines Käfigs die Kurzschlussringe. [...] so ist der
> **Platzbedarf für den Wickelkopf innerhalb** der Maschine als kritisch
> anzusehen, da der Bauraum durch die **Welle** begrenzt ist. Der Innenradius
> wird folglich **maßgeblich durch den benötigten Platzbedarf für den
> Wickelkopf** beeinflusst."

Gebaut ist eine Schranke aus Nut- und Zahnbreite am Innenrand gegen einen
2-mm-Fertigungsboden. Das ist ein Stellvertreter, nicht die Sache: bindend ist
der **innere Wickelkopf** gegen die Welle. Dass λ „aus der Zeichnung" kommt, war
richtig; die gezeichnete Größe war die falsche.

**3. `_BAUFORMEN` trägt PM-Namen und bildet die ASM-Topologien nicht ab.**

Die neutralen Namen der Quelle sind **ESER / DSER / ESDR** (ein/zwei Statoren,
ein/zwei Rotoren), und sie gelten für PM *und* Käfig:

| | Joch | Spalte | Kernaussage |
|---|---|---|---|
| **ESER** | beide | 1 | einfachste Konstruktion; `σ_L ≈ B²/(2µ0)` hängt vom **Betrag** der Flussdichte ab, nicht von der Richtung, „weswegen er sich entlang der Luftspaltfläche **nicht wie im Fall der Radialflussmaschine ausgleichen** kann" → ein Lager trägt das dauerhaft, daher kleine Leistungen |
| **DSER** | **Rotor braucht keins** (nur Restjoch zur Wellenanbindung) — der Fluss geht axial durch die **Rotorzähne** von Stator zu Stator | 2 | Wicklungen 120° el. verdreht **und gespiegelt**, sonst wirken die Flüsse gegeneinander; geteilte Statorwicklung → deutlich besser kühlbar → große Leistungen |
| **ESDR** | Stator theoretisch ohne (Restjoch für die Festigkeit der Wicklung) | 2 | Wicklung beidseitig um den Stator, **keine Kreuzungen im Wickelkopf** → kompakter; dafür zwei Rotorjoche → größere rotierende Masse |

Mein `afir`-Stapel (`stator|spalt|magnet|ruecken|magnet|spalt|stator`) kann die
**DSER-ASM gar nicht abbilden**: dort trägt der Rotor **Zähne und Käfig und
kein Joch**. Und zwei Variationen fehlen ganz:

* **Stapelbauweise** — mehrere Teilmaschinen auf einer Welle, „rein **mechanisch**
  gekoppelte Maschinen, die sich trotz der konstruktiven Nähe elektromagnetisch
  nicht beeinflussen"; bei gerader Anzahl ESER heben sich die axialen Kräfte in
  Summe auf.
* **DSDR mit reduziertem Rotorjoch** — aus zwei ESER, Rotorjoch halbiert, um
  rotierende Masse zu senken und die Momentdichte zu heben. Der Preis ist, dass
  die Teilmaschinen dadurch **magnetisch** gekoppelt werden: fällt eine aus,
  schließt sich der Fluss der intakten „nicht nur über das Rotorjoch sondern auch
  über die ausgefallene Teilmaschine, was einer **fiktiven Luftspaltvergrößerung**
  entspricht" → höherer Magnetisierungsstrom. Das ist der Gegenstand der ganzen
  Dissertation.

**Bestätigt, nicht widerlegt:** der axiale Anzug `σ_L ≈ B²/(2µ0)` und seine
Begründung decken sich mit dem hier gemessenen 8,6 : 1 (BEFUNDE 05.10.2026).

**Noch nicht repariert.** Punkt 1 ist eine Formel und klein; Punkt 2 braucht ein
Wickelkopfmodell, das es axial nicht gibt; Punkt 3 ist ein Umbau von
`_BAUFORMEN` samt Namensgebung. Reihenfolge in `AXIALFLUSS.md` §10.


## 2026-10-05 · Die „Axialflussmaschine" trug innen einen V-Magnet-IPM-Läufer

**Vom Menschen gefunden, nicht vom Werkzeug** — gemeldet als *„deine maschine
sieht aus wie eine psm mit magneten in v-anordnung. schau mal nach"*. Er hatte
recht, und zwar an der empfindlichsten Stelle.

**Gemessen** an genau dem Payload, mit dem der Gesamtdurchlauf lief
(`fluxPath="axial"`, `axialAktivOD=260`, 2p=16, 48 Nuten):

| | |
|---|---|
| `magShape` im axialen Payload | **`"v"`** — die Schemavorgabe, nie abgewiesen |
| `magnet_legs(geom)` | **2 V-Schenkel je Pol**, `tilt = ±1,047 rad` (±60°), `len 24,08`, `dick 6,00` |
| `estimate_saliency(geom)` | **2,589** — die Salienz einer V-Tasche |
| `estimate_dq_currents` | i_q 189,2 A, **i_d −9,9 A** |
| dieselbe Geometrie mit `magShape="spm"` | Salienz 1,02, **i_d 0,0 A** |

Der Betriebspunkt der axialen Feldstufe kam also aus einem **IPM-Läufer mit
V-Tasche**, den eine Scheibe nicht hat — und über das Ankerfeld ging er in B_t
und damit ins Moment ein. `_analytical_Bgap` am selben Payload liefert 0,8807 T
aus der IPM-Formel (mit einer Polteilung aus `statorID`); benutzt wurde sie
nicht, erreichbar war sie.

**Warum es keine der Prüfungen gefunden hat:** die Tore in `ema_fluss` fragen
nach dem *Flussweg* und nach der *Maschinenart*, und beide Antworten waren
richtig. Die **Läufertopologie** ist eine dritte Achse, und nach der hat nichts
gefragt. `test_axial_fdm` prüft Form, Linearität, Carterzahl und Konvergenz —
alles Größen, die der Phantom-Läufer gar nicht berührt, weil er nur über den
STROM wirkt. Der Fehler saß genau im Spalt zwischen zwei richtigen Toren.

**Behoben.** `estimate_saliency` und `_analytical_Bgap` weisen Axialfluss jetzt
ab (`_axial_tor`) und nennen den Grund; `ema_axial_fdm.betriebspunkt` rechnet
i_q aus dem **axialen** Kt (über `ema_fluss.flaechen`) mit `i_d = 0`. Das ist
keine Vereinfachung, sondern die Bauart: Oberflächenmagnete flach auf der
Scheibe heißt Ld = Lq, also kein Reluktanzmoment. Gemessen danach i_q 182,1 A
statt 189,2, i_d 0,0 statt −9,9. Dass eine Scheibenmaschine mit vergrabenem
Magnet oder als Reluktanzläufer **doch** salient wäre, steht als Grenze im
Ergebnis statt mit einer fremden Salienz gefüllt zu werden.

**Offen geblieben:** der Payload trägt weiterhin `statorOD/statorID/rotorOD/
shaftD/magShape/magWidth/…` aus der Radialmaschine. Sie sind axial
bedeutungslos, werden aber mitgeschleppt und sind damit die nächste Stelle
derselben Art. Ein eigener, vollständiger axialer Parametersatz mit Abweisung
der radialen Maße steht aus.


## 2026-10-05 · Zwei Urteile über Maschinen, die keine Befunde waren

In `ema_fluss.ART_AXIAL` stand:

    asm:   "ein Scheibenkaefig ist schwer herstellbar [...] Nicht getragen"
    synrm: "die Anisotropie braucht orientiertes Blech IN einer Scheibe --
            nicht blechbar. Nicht getragen"

Beides war **Vermutung in der Form eines Befunds** — und das erste ist falsch.
Der Mensch hat dagegengehalten:

* **Igelspacher, „Zur Theorie der Axialfluss-Asynchronmaschine als
  ausfallsicherer Antrieb", Diss. TU München 2018/2020** (207 S.) — Kapitel 2
  behandelt Axialfluss-Asynchronmaschinen mit Käfigläufer samt allen drei
  Bauformen (1 Stator/1 Rotor, 2 Statoren/1 Rotor, 1 Stator/2 Rotoren), der
  Stapelbauweise, einer Variante mit **reduziertem Rotorjoch** zur Erhöhung der
  Leistungsdichte und einer Beispielmaschine. Eine Maschine, der jemand eine
  Dissertation widmet, ist nicht „schwer herstellbar, nicht getragen".
* **HAW Hamburg, Forschungsgruppe Elektrische Mobilität** — Pancake-Design,
  Single-Rotor-Single-Stator / DRSS / DSSR, Halbacharrays (erlauben den Verzicht
  auf ferromagnetisches Rotormaterial), kernlose Luftspulenwicklungen.
* **Wikipedia „Scheibenläufermotor"** — eisenloser bzw. gedruckter Scheibenanker,
  „das Magnetfeld verläuft parallel zur Drehachse", „der Durchmesser der Motoren
  ist größer als deren Länge", magnetischer Kreis außerhalb der Scheibe
  geschlossen.

**Korrigiert.** Die Tabelle sagt jetzt, was dieses WERKZEUG trägt, und nicht,
was es für baubar hält: `asm` ist „NICHT GEBAUT — und das ist eine Aussage über
dieses Werkzeug, nicht über die Maschine", mit dem Verweis auf die Dissertation
und der konkreten Lücke (Scheibenkäfig in `ema_asm`, harmonischer Löser auf dem
abgewickelten Schnitt). Bei `synrm` ist „nicht blechbar" zurückgenommen.

**Die Regel dahinter, zum Mitschreiben:** ein Tor darf sagen „das rechne ich
nicht". Es darf nicht sagen „das gibt es nicht", und erst recht nicht in einem
Tonfall, der wie eine Messung klingt. Alle drei Quellen standen im Netz; keine
wurde gelesen, bevor die Zeile geschrieben wurde.


## 2026-10-05 · Gesamtdurchlauf: B_gap(r) aus dem Mehrschnitt ist NICHT konvergiert

**Beim ersten vollständigen Durchlauf gemessen** — also genau dort, wo ein
Modul aufhört, Testfälle zu rechnen, und anfängt, eine Maschine zu beschreiben.
Der Lauf (8 Schnitte, N = 520, 3000 1/min, 120 Nm) gab aus:

    B_gap(r) [T]   0,9787  0,9759  0,9578  0,7900  0,7815  0,9249  0,9275  0,9115
    r [mm]           78,5    85,4    92,2    99,1   106,0   112,8   119,7   126,6

Eine **Delle** von 20 % mitten im Ringraum, und sie sieht aus wie ein Befund
über die Maschine. Sie ist keiner: dieselben Radien bei drei Auflösungen
gerechnet **wandert die Delle mit N**. Konvergenz an EINEM Radius
(r = 102,5 mm, Fenster 4 Polteilungen, bis zu 7,9 Pixel im Luftspalt):

    N      320      480      640      800     1000     1280
    B1   0,9726   0,8998   0,9331   0,8995   0,9195   0,8739  T
    Abw.  11,3 %    3,0 %    6,8 %    2,9 %    5,2 %      —

Es **oszilliert** und konvergiert nicht monoton; selbst bei 1280 Punkten liegen
benachbarte Stufen 3…5 % auseinander. Die abgetastete Zeile liegt dabei
nachweislich zu 100 % in Luft (geprüft) — die Ursache ist nicht die Abtastung,
sondern dass die dünnen Schichten des Stapels (Luftspalt 1 mm, Magnet 6 mm) auf
das Gitter **schnappen**: eine halbe Pixelbreite Versatz ändert den wirksamen
Spalt um Prozente, und die Form der Luftspaltwelle hängt daran.

**Damit ist die Stufe-2-Aussage „belastbar sind ψ und B_gap(r)" zu stark und in
`AXIALFLUSS.md` korrigiert.** Belastbar sind die Größen, die eine
**Verhältnis**bildung tragen oder an einer geschlossenen Form hängen:

| hält | Beleg |
|---|---|
| Form der reinen Magnetwelle | nutlos 1,2622 gegen 4/π = 1,2732 (0,9 %) |
| Linearität | J → 2J gibt exakt 2,000000 |
| Leerlaufmoment ≈ 0 | −0,55 Nm gegen −311,6 Nm unter Last |
| Carterfaktor | 1,03 / 1,09 / 1,19 über die Nutbreite, Verhältnis zweier Läufe |
| Unabhängigkeit von der Fensterbreite | 1,29 % über Faktor 4 |

**Nicht belastbar** sind die absolute Amplitude und ihr Verlauf über dem Radius —
dieselbe Lage wie beim Statoreisen-|B| des radialen FDM, und aus demselben
Grund: ein Merkmal, das nur wenige Pixel breit ist, ist nicht aufgelöst, und die
Zahl darüber konvergiert nicht. Der radiale Weg hat damit übrigens dasselbe
Problem an derselben Stelle: `luftspalt_im_netz` meldet bei N = 520 **1,04
Pixel** im 0,7-mm-Spalt.

**Nicht repariert.** Der Ausweg wäre ein körperangepasstes Netz (Elmer) statt
eines kartesischen Rasters — also Stufe 3, und dort steht die Aufgabe ohnehin
schon: den Normierungswiderschied beim Moment entscheiden. Was dieser Lauf
ändert, ist die Beschriftung, nicht die Rechnung.

**Zwei Dinge aus demselben Durchlauf, die nicht den Axialfluss betreffen:**

*Die Thermik lief für eine Axialflussmaschine klaglos durch* und meldete
T_winding 68,2 / T_magnet 81,8 °C — plausible Zahlen für eine Maschine, die es
nicht gibt, und die 80-°C-Magnetgrenze schon überschritten. Das LPTN ist ein
Schalennetz von innen nach außen; beim YASA sitzt der Ständer ZWISCHEN zwei
Scheiben und hat diesen Weg nicht, beim AFIR liegt die Wicklung außen. Das ist
nicht die falsche Parametrierung, sondern die falsche Netztopologie.
`run_thermal_analysis` weist Axialfluss jetzt ab und nennt den Grund; die
Schubspannungsgrenze `rated_torque` gilt weiter, sie geht über `ema_fluss`.

*Der radiale Durchlauf bestätigt zwei schon bekannte Posten* (nicht neu, aber
jetzt am vollen Lauf): `ema_saettigung` meldet **B_zahn = 8,712 T** und
`saett_pct = None` — unphysikalisch, vgl. den Eintrag vom 2026-10-04; und
`T_cogging_Nm = 116,78` steht neben einem Dauermoment von 178,8 Nm, also bei
65 % davon. Beides nicht untersucht.


## 2026-10-05 · Axialfluss Stufe 2: ψ konvergiert, das MOMENT nicht — zwei Ursachen

Beim Bauen der axialen Feldstufe (`ema_axial_fdm`, abgewickelter Mehrschnitt)
gemessen. Beide Punkte sind **nicht repariert**, sondern benannt — der zweite
ließe sich durch einen Faktor zum Verschwinden bringen, und genau das wäre falsch.

**1. Zwei Momentwege, Faktor ~3 auseinander, über den Strom konstant.**

| Last | i_q | T_maxwell | 1,5·p·ψ·i_q | Verhältnis |
|---|---|---|---|---|
| 50 Nm | 83,4 A | 164,35 Nm | 52,25 Nm | 3,145 |
| 100 Nm | 159,1 A | 311,57 Nm | 100,90 Nm | 3,088 |
| 200 Nm | 308,9 A | 600,73 Nm | 204,86 Nm | 2,932 |

Dass das Verhältnis über den Strom nahezu konstant ist, schließt einen
Physikfehler weitgehend aus: es ist ein **Normierungsunterschied**. `psi` ist auf
**eine Windung je Nut** normiert — so rechnet `compute_performance`, und
`conductorsPerSlot` geht dort gar nicht ein —, während `_analytical_Barm`, der
Eichanker des Ankerfeldes und damit von `B_t`, mit der **physikalischen**
Durchflutung `N_ph = slots/3` rechnet. Genau diese Brücke heißt in `ema_asm`
`k_norm = π·k_w·N_ph/p²`, und dort steht auch, was passiert, wenn man sie
vergisst: man vergleicht zwei verschieden große Ampere. Dem Radialweg fällt es
nicht auf, weil er `T_maxwell` und `Kt` nie gegeneinander hält.

**Nicht aufgelöst, und zwar absichtlich.** Welcher Bezug gilt, entscheidet ein
unabhängiger Löser (Stufe 3, Elmer-Ringsektor) und nicht ein Faktor, der die
Abweichung verschwinden lässt. `felder()` gibt beide Zahlen heraus und schreibt
den Widerspruch dazu — dasselbe Verfahren wie `ema_leistung`, das den Widerspruch
zwischen `rated_torque` und dem LPTN über die Kennlinie schreibt, statt ihn zu
glätten.

**2. Über der Schnittzahl konvergiert ψ, das Moment nicht.** Gemessen
(k = 2 / 4 / 8, Bezug k = 8, 100 Nm, 3000 1/min):

    psi   0,05826 -> 0,05207 -> 0,04977 Wb    Abweichung 16,0 % -> 0,14 % -> 0
    T     streut; k = 4 liegt weiter von k = 8 entfernt als k = 2

Der Grund ist strukturell: `psi` hängt an EINEM geeichten Feld, die Maxwellsche
Schubspannung am **Produkt zweier unabhängig geeichter** Felder (B_n am
Magnetanker, B_t überwiegend am Ankeranker), und B_t ist dabei die kleine Größe.
Beide Eichfehler gehen multiplikativ ein.

**Daraus folgt der Geltungsbereich von Stufe 2, und er steht in jeder Ausgabe:
belastbar sind ψ und B_gap(r), das Moment ist es nicht.** Dieselbe Haltung wie
beim Statoreisen-|B| des radialen FDM (konvergiert auch nicht, und was statt
dessen geht).

**Zwei eigene Fehler auf dem Weg dahin, beide behoben** — sie stehen hier, weil
beide plausibel aussahen:

*Das quadratische Gebiet wurde mit LUFT gepolstert.* Der FDM-Matrixbauer verlangt
ein quadratisches Gitter, der Stapel ist aber niedriger als das Fenster breit.
Mit Luft gefüllt hängt das Ergebnis an der Fensterbreite, weil mit dem Quadrat
auch der Streuweg wächst — gemessen bei r = 102,5 mm und gleicher Maschenweite:
B1 = 0,86410 / 0,84730 / 0,83494 / 0,82445 T über 2 / 4 / 6 / 8 Polteilungen,
**ohne zu konvergieren**. Mit EISEN gepolstert ist die Polsterung wirkungslos
(jenseits des Joches gibt es keine Quelle), und die Abhängigkeit fällt auf
1,29 % über denselben Faktor 4. Physikalisch ist das auch die richtige Aussage:
ein Joch schließt den Fluss ein.

*Die nötige Fensterbreite springt mit dem Radius* (innen ist die Polteilung
kleiner), also sprang mit ihr das Ergebnis mitten im Ringraum — die Schnittreihe
war dadurch nicht monoton und sah aus wie ein Verfahren, das nicht konvergiert.
Alle Schnitte benutzen jetzt dieselbe Breite, die des Innenrands.

*Und ein drittes, das keine Spur hinterlassen hätte:* der Lastfall rechnete mit
Strom **null**, weil `estimate_dq_currents` ein Tupel zurückgibt und kein Dict
und kein `axial_mm` kennt — ein stilles `except` hat den `TypeError` verschluckt.
Heraus kam das Leerlaufmoment (−0,18 Nm statt 100 Nm Soll), und nichts
widersprach. Ein Fehlschlag dort ist jetzt ein benannter Grund im Ergebnis
(`strom_fehlschlag`, `last_gerechnet`) und kein Nullstrom.

**Nebenbefund, der die Hauskonstante bestätigt:** der Carterfaktor dieser Nut ist
gemessen **1,03 / 1,09 / 1,19** bei `slotWidthRatio` 0,3 / 0,5 / 0,7 und klammert
damit die angenommenen 1,15 ein — anders als beim Käfigläufer, wo der 2-D-Lauf
3,2 gegen 1,15 fand. Gemessen wird er an der **Grundwelle**: an der Spitze
gerechnet kam 0,82 heraus, also kleiner als eins, was es nicht geben kann — über
einem Zahn ist der Fluss gebündelt, die lokale Spitze steigt durch die Nutung,
während der Fluss je Pol fällt.


## 2026-10-05 · `rotor-check` meldet FAIL bei der Drehzahl, die es selbst vorschlägt

**Beobachtung, nicht diagnostiziert.** `test_rotorcheck.py` schlägt an zwei
Prüfungen fehl: „Verb: bei der vorgeschlagenen Drehzahl hält es (Exit 0)" und
„und meldet dort PASS statt FAIL". Das Verb rechnet also einen Entlastungsweg aus
(`ema_rotorcheck.entlastung`, Höchstdrehzahl), und bei genau dieser Drehzahl
besteht sein eigenes Tor nicht.

**Gegengeprüft, dass es nicht von diesem Tag stammt:** mit `git stash` auf die
unveränderte `ema_rotorcheck.py` zurückgesetzt schlagen dieselben zwei Prüfungen
identisch fehl. Der Axialfluss-Umbau vom 05.10.2026 (das neue Flussweg-Tor am
Anfang von `rotor_layout_check`/`rotor_stress_check`) ist nicht die Ursache.

**Warum das wichtig ist:** `entlastung` ist ausdrücklich dafür gebaut, dass
**jeder Weg gegen DASSELBE Tor nachgeprüft wird, bevor er vorgeschlagen wird** —
„einer, der es erneut reissen lässt, ist keiner" (s. `cae_orchestrator/CLAUDE.md`).
Genau diese Zusicherung hält hier nicht, und der Vorschlag ist dann schlimmer als
keiner: er schickt eine Auslegungsentscheidung in eine Drehzahl, die wieder
abgewiesen wird. Die Rundung „auf die sichere Seite" (dokumentiert: auf 50
aufgerundet lag die Sicherheit wieder bei 1,297 statt 1,30) ist der erste Ort,
an dem man suchen würde.

**Nicht repariert** — dieser Befund entstand beim Durchmessen der Testsätze für
einen anderen Umbau, und eine Reparatur am Fliehkrafttor mitten in einem
Axialfluss-Umbau wäre genau die stille Vermischung, gegen die
`ema_werkzeugstand` gebaut ist.


## 2026-10-05 · Zwei Angaben in `AXIALFLUSS.md` §1 waren falsch — beide beim Bauen gemessen

Beide standen in der ersten Fassung des Plans vom selben Tag, beide sind dort
jetzt mit Begründung korrigiert. Sie stehen hier, weil ein korrigierter Plan nicht
zeigt, **dass** korrigiert wurde — und weil beide Fehler eine Art haben, die
wiederkommt.

**1. λ = 1/√3 ist nicht herleitbar.** Der Plan nannte es „den klassischen Wert
bei endlichem Strombelag". Nachgerechnet:

    T = 2π·σ·Ro³·(1−λ³)/3   →   dT/dλ = −2π·σ·Ro³·λ²  < 0  für jedes λ > 0

Das Momentintegral ist in λ **monoton fallend**, es hat gar kein inneres Maximum.
Und die Voraussetzung hält: σ ist über r konstant, solange der Zahn keilförmig
ist — der Leiterquerschnitt je Nut wächst mit der Nutteilung, also mit r, und der
Flächenstrombelag `K = J·swr·h_z` hängt damit nicht von r ab.

Der Literaturwert ist **λ = 1/3** und stammt aus der Mitteldurchmesser-Näherung
`T ≈ σ·(π·D_m·L_e)·(D_m/2)`. Die liegt bei λ → 0 um **25 %** zu niedrig (1,5708
gegen 2,0944 in Einheiten von σ·Ro³) und erzeugt dadurch ein Maximum, das die
Maschine nicht hat. **1/√3 = 0,5774 ist keiner der beiden Werte** — es war von
Anfang an eine Zahl ohne Herleitung, genau die Art Konstante, die der Plan im
selben Abschnitt zu vermeiden verspricht (Vorbild: die flachen 20 %
Kurzschlussring-Zuschlag, die `feld3d` um mindestens das Dreifache widerlegt hat).

Bindend ist statt dessen die **Zeichnung am Innenrand** (`ema_axial.lambda_grenze`):
dort wird die Nut zu schmal oder der Zahn zu dünn, beides aus `slots` und
`slotWidthRatio`. Gemessen bei Q = 48, swr = 0,5, 2 mm Fertigungsboden:
λ_min = **0,2351**, bindend die Nut; bei Q = 72 λ_min = 0,3526.

**2. Der Kragstreifen in §1.7 war eine UNTERE Schranke, obwohl „obere" dastand.**
Gerechnet war ein Kragstreifen über dem **aktiven** Ring (Ro − Ri = 55 mm), mit
der Begründung, die Ringscheibe trage umfangs mit und sei steifer. Das zweite
stimmt und ist unerheblich: die Scheibe ist nicht am Innenrand des Ringraums
eingespannt, sondern an der **Nabe**. Der Hebel ist damit 100 mm statt 55 —
(100/55)⁴ ≈ 11, abzüglich der um 1/(1−ν²) höheren Plattensteifigkeit bleibt
**Faktor 9**.

Gemessen an der Kreisringplatte (`ema_axial._platte`, innen eingespannt, außen
frei, Druck nur auf dem aktiven Ring, Nabe bei r = 30 mm), gegen die alten Zahlen:

| 2p | t magnetisch | w (Platte) | Anteil 1-mm-Spalt | alt (Kragstreifen) |
|---|---|---|---|---|
| 8 | 25,70 mm | 13,1 µm | 1,3 % | 1,4 µm |
| 16 | 12,85 mm | **105,0 µm** | **10,5 %** | 11,1 µm |
| 24 | 8,57 mm | 354,3 µm | 35,4 % | 37,5 µm |
| 40 | 5,14 mm | 1640,4 µm | 164,0 % | 173,5 µm |

Die Durchbiegung bindet also **viel früher** als der Plan sagte. Der Plattenlöser
ist gegen den Kragstreifen im Grenzfall des schmalen Rings geprüft (0,26 %
Abweichung bei 1 mm Ringbreite), Randrest ~1e-21, Linearität in q exakt 2,000000
und in t exakt 8,000000 (`test_axial.py`).

**Was daraus als Auslegungsauskunft folgt** — und was ohne die Rechnung nicht zu
sehen war: die Steifigkeitsforderung ist **polzahlunabhängig** (sie hängt am Druck
und an der Geometrie, nicht an der Flussaufteilung), die magnetische fällt mit der
Polzahl, also kreuzen sie sich. Und der Haupthebel ist nicht die Blechdicke,
sondern der **Einspannradius**: von 30 auf 75 mm fällt die Durchbiegung um
Faktor 9 (105,0 → 11,1 µm), die nötige Dicke von 13,06 auf 6,17 mm.

**Beides behoben** (das ist der Unterschied zu den anderen Einträgen hier): die
Angaben waren noch nicht in Gebrauch, es hing keine gespeicherte Rechnung daran.
`AXIALFLUSS.md` trägt beide Korrekturen mit den alten Zahlen zum Nachvollziehen.

## 2026-10-05 · `rated_torque` nimmt am Außenläufer den falschen Radius (+22,5 %)

**Beim Bauen von `ema_fluss` (Stufe 0) gemessen**, nicht gesucht: die beiden
Kennzahlen, die aus der Luftspaltfläche kommen, benutzen **verschiedene
Radien**.

| | Radius | Fundstelle |
|---|---|---|
| `psi_pm` → `Kt`, EMK | **mittlerer Spaltradius** `r_gap_m(geom)` → `ema_radien` | `ema_analysis.compute_performance:1370` |
| `T_dauer` | **Läuferaußenradius** `rotorOD/2` | `ema_thermal.rated_torque:78` |

Am Innenläufer ist das der halbe Luftspalt und damit gleichgültig — gemessen an
der Vorgabegeometrie **−0,7 %** (178,8 gegen 180,1 Nm). Am **Außenläufer** ist
`rotorOD/2` nicht die Spaltfläche, sondern die **Außenfläche des Läuferrings**:

    Aussenlaeufer (statorOD 180, statorID 60, rotorID 181,4, rotorOD 200)
      Laeuferflaeche am Spalt      r =  90,70 mm
      mittlerer Spaltradius        r =  90,35 mm
      rated_torque rechnet mit     r = 100,00 mm
      T_dauer  201,1 Nm   statt   164,1 Nm      ->  +22,5 %

Das ist kein Grenzfall, sondern ein lebender Wert: `STUFEN_AUSSEN =
("analytisch",)` — der Außenläufer **ist** auf der analytischen Stufe getragen,
und `rated_torque` gehört zu ihr. Die Schubspannung greift an der Fläche an,
die dem Spalt zugewandt ist; `ema_radien.radien()` gibt sie als
`r_rotor_gap_mm` längst heraus und wird hier nicht gefragt. Die Richtung des
Fehlers ist dabei die unangenehme: das Dauermoment kommt zu **groß** heraus.

**Nicht repariert.** `ema_fluss.flaechen()` reproduziert beide Ausdrücke
Ziffer für Ziffer, einschließlich dieses — die erste Abnahmebedingung von
Stufe 0 ist, dass sich an keiner radialen Kennzahl etwas bewegt
(`test_fluss.py`). Eine Reparatur mitten in einem Umbau wäre genau die stille
Änderung, gegen die `ema_werkzeugstand` gebaut ist: sie verschöbe das
Dauermoment jedes bestehenden Projekts, ohne dass der Umbau es ankündigt. Jetzt
steht der Unterschied wenigstens an **einer** Stelle sichtbar beieinander
(`ema_fluss.flaechen` gibt `r_fluss_m` und `r_moment_m` getrennt heraus, und
`uebersicht()` druckt beide).

## 2026-10-05 · Axialfluss: zwölf Stellen geben eine Zahl, wo ein Nein hingehört

**Beobachtung.** Das Werkzeug hat kein Tor für den **Flussweg**. `machineType`
hat eines (`ema_maschinenart`), die Läuferbauform hat eines (`ema_radien`,
`pruefe_bauform`) — die Richtung, in der der Luftspalt liegt, hat keines, weil
sie nie als Begriff auftaucht: `grep -i "axial|AFPM|YASA|Scheibenläufer"` findet
im ganzen Baum nur `axialLen`/`axial_mm`, also die *Paketlänge* einer
Radialflussmaschine. Eine Axialflussmaschine wird deshalb nicht abgewiesen,
sondern **als Radialflussmaschine gerechnet und mit ihrem Namen beschriftet** —
derselbe Fehlertyp, gegen den `ema_maschinenart` gebaut ist („er bekommt
PSM-Zahlen mit einem anderen Etikett").

**Gemessen, wie weit die radiale Annahme reicht.** 93 Dateien lesen
`statorID`/`statorOD`/`rotorOD` unmittelbar; **17** fragen `ema_radien`
(59 Aufrufstellen). Die Kapselung, die für Innen-/Außenläufer gebaut wurde,
deckt also ein Fünftel der Lesestellen ab — und sie kapselt die falsche Frage:
`radien()` ordnet Radien, setzt aber voraus, dass der Spalt eine **Differenz
zweier Radien** ist. Axial ist er eine axiale Strecke.

**Die zwölf Stellen, die eine Zahl liefern würden** (keine wirft einen Fehler):

| Stelle | was herauskäme |
|---|---|
| `ema_thermal.rated_torque` (2σ·πR²L) | Zylinderformel auf eine Scheibe: beliebiger Wert |
| `ema_analysis.compute_performance` (`psi_pm = p(2/π)B·R_gap·L`) | falsches Flächenintegral, gemessen Faktor 1,49 daneben |
| `ema_saettigung` (`B_zahn = B_gap/((1−swr)·k_fe)`) | die dokumentierte Kürzung der Nutteilung (`:52`) gilt nur auf **einem** Radius |
| `ema_analysis.luftspalt_mm` | `(statorID − rotorOD)/2` — bildet den Spalt nicht |
| `ema_radien.radien` | wirft `spalt ≤ 0` oder prüft eine Ringwand, die es nicht gibt — ein Fehler, aber der falsche |
| `ema_rotorcheck` (Lamé-Ring) | eine Scheibe unter Axialzug ist kein rotierender Ring |
| `ema_rotorcheck`/`rotor_layout_check` | prüft den Blechsteg, den eine Scheibe nicht hat (vgl. Befund „Polbefestigung") |
| `ema_thermal` LPTN | Schalennetz von innen nach außen; beim jochlosen Stator die falsche Topologie |
| `ema_analysis.estimate_saliency` | legt `magThick` in den d-Pfad; axial ist das die axiale Richtung |
| `ema_analysis._rasterise` / `_sample_airgap` | `R = hypot(X,Y)`-Ringe: baut eine Radialmaschine |
| `ema_em3d.baue_netz` / `ema_em3d_harm.baue_netz` | Scheiben **eines** Querschnitts — den gibt es axial nicht |
| `ema_analysis.r_gap_m` | ein Radius für zwei verschiedene Integrale (s. u.) |

**Gemessen, warum ein Radius nicht reicht.** Flussverkettung wiegt die
Ringfläche mit r¹, das Moment mit r². Radial fallen beide auf `R_gap` zusammen —
axial nicht. An der Vorgabegeometrie (Stator 280/190, Rotor 188,6, L = 80,
water = 40 kPa aus `COOLING_RATING`), axial mit Ro = 130 mm, λ = Ri/Ro = 0,577,
zwei Luftspalten:

| | radial | axial (2 Spalte) | Faktor |
|---|---|---|---|
| Flussfläche `R_gap·L` bzw. `n·(Ro²−Ri²)/2` | 75,44 cm² | 112,66 cm² | 1,49 |
| Momentintegral `R²L` bzw. `n(Ro³−Ri³)/3` | 711 | 1183 | 1,66 |
| T_dauer | **178,8 Nm** | **297,2 Nm** | 1,66 |

Die 178,8 Nm sind die Gegenprobe: dieselbe Zahl steht im Docstring von
`ema_thermal.mit_umrichtergrenze`. Wer `R_gap·L` durch *eine* Ersatzfläche
ersetzt, hat danach entweder `Kt` oder das thermische Dauermoment richtig, nie
beide.

**Gemessen, dass der Hauslöser es trägt.** `_build_fv_matrix(mu)` und
`_solve_fdm(mu, J)` nehmen nur Material- und Stromfelder auf einem
gleichmäßigen kartesischen Gitter — sie kennen keinen Radius. Eine abgewickelte
Axialfluss-Scheibe (r = 102,5 mm, 2p = 16, Fenster = genau 2 Polteilungen mit
Polgrenze bei x = 0, damit Dirichlet A = 0 am Seitenrand die *richtige*
Bedingung ist, 400×400, Luftspalt 5 px) durch die **unveränderten**
Hausfunktionen `_solve_fdm`, `_material_labels`, `_curl_a`:

    Permeanz hm/(hm+µr·kc·g)  0,8325  →  B_an 0,9573 T
    B_axial Spitze            0,9573 T
    B_axial Grundwelle        1,2098 T  = 1,264 × Spitze   (4/π = 1,273 → nahezu rechteckig)
    B_tangential Spitze       0,3839 T  (40,1 % der Normalkomponente)
    Klirranteil               42,6 %
    Linearitätsprobe J → 2J   2,000000 × A

Radiusgebunden sind also nur `_rasterise` und `_sample_airgap`, nicht der
Löserkern. Nachrechenbar mit `axialfluss_scheibenprobe.py`. Der Stator ist in diesem Lauf massives Eisen ohne Nuten; der Lauf
trägt keine Nutungsaussage.

**Gemessen, welche Last dabei fehlt.** Aus derselben Scheibe:
⟨B_n²⟩/2µ₀ = **345,8 kPa** Normalspannung, auf 353,7 cm² Ringfläche
**12,23 kN axialer Anzug je Luftspalt** — gegen 40 kPa Schubspannung, die das
Moment macht. Verhältnis **8,6 : 1**. Bei zwei Spalten hebt sich das nur bei
mittigem Stator auf; 0,10 mm Versatz aus 1,0 mm Spalt lassen 4,99 kN übrig,
und zwar **in Richtung des Versatzes** (destabilisierend). Keine der
Strukturstufen kennt diese Lastart: `ema_deck`, `ema_z88`, `ema_aster` rechnen
Fliehkraft, `ema_schenkelpol` die Polbefestigung. Eine Axiallast gibt es
nirgends.

**Nicht repariert, und bewusst nicht.** Was hier fehlt, ist keine Formel,
sondern ein Tor — und ein Tor ohne die Stufen dahinter ist richtig, ein
Schemaschlüssel `fluxPath` ohne Tor wäre schlimmer als der heutige Zustand
(dann hieße eine ausgewählte Bauform, das Werkzeug trage sie). Die Reihenfolge
steht in `AXIALFLUSS.md`: erst das Tor und das begründete Nein, dann die vier
Stufen. Der Umbau von `compute_performance` und `rated_torque` auf getrennte
Flächenintegrale verschiebt Zahlen **bestehender** Projekte, falls er den
Radialfall nicht Stelle für Stelle reproduziert; beide Module stehen in
`ema_werkzeugstand._MODULE`, der Fingerabdruck meldet die Änderung also an
jeder gespeicherten Rechnung.

## 2026-10-04 · Alle fünf Bauarten laufen durch — drei Stufen wissen nicht, welche

**Gemessen.** Ein Pipelinelauf je Maschinenart, gleicher frischer Payload, nur
`machineType` getauscht (Projekte `20261004_0755…_synrm`, `_0759…_asm`,
`_0804…_gsm`, `_0808…_pmsm`, `20261004_073715_EESM_Durchlauf`). **Alle fünf
beenden mit `done`** und schreiben je acht Ergebnisblöcke. Das CAD ist dabei
sauber nach Art getrennt — fünf echte FreeCAD-Läufe, fünf verschiedene
Rotorvolumen (PSM 1.728.350 · ASM 1.911.551 · SynRM 1.401.226 · EESM 814.464 ·
GSM 1.693.032 mm³). Drei Stufen danach sind es nicht:

**1. Die Struktur-FEM liefert für vier Bauarten denselben Sicherheitsfaktor.**
`safety_factor_fem = 9.687` für SynRM, ASM, GSM **und** PSM — Ziffer für Ziffer.
Vier verschiedene Läufer (Flussbarrieren, Käfig, Anker, Magnettaschen) können
nicht dieselbe Fliehkraftsicherheit haben. Bestätigt den schon notierten Befund,
dass `ema_deck` für jede Art dasselbe Rotorblech vernetzt — jetzt über alle
Arten gemessen statt nur an PSM/ASM. Die EESM liefert gar keinen Wert.

**2. GSM und PSM haben eine bitgleiche Leistungshüllkurve.** `P_max` 176,5 kW,
`T_peak` 280,9 Nm, beide „begrenzt durch kuehlung". Eine Gleichstrommaschine mit
Kommutator und eine permanenterregte Synchronmaschine können dieselbe Hüllkurve
nicht teilen; `power_envelope` rechnet dq-Größen, die es bei der GSM nicht gibt
(`ARTEN['gsm'].ohne_bedeutung` führt sie bereits als bedeutungslos — die
Hüllkurve fragt das nicht).

**3. Magnettemperatur für Maschinen ohne Magnete.** SynRM 43,9 · ASM 51,4 ·
GSM 51,4 · EESM 67,1 °C, bei `hat_magnete = False` und ohne Magnetmasse. Der
Wert ist nicht nur unnötig, er ist das Kriterium, an dem `ema_sicherheit` die
Entmagnetisierung prüft — eine Grenze für ein Bauteil, das es nicht gibt.

**Nicht repariert.** Alle drei sind Rechenstufen, deren Umbau die Zahlen
bestehender Projekte verschiebt; welche davon wie nach Art verzweigen soll, ist
eine Auslegungsentscheidung. Was sie gemeinsam haben: die Stufe fragt
`ema_maschinenart` nicht. `gilt()`/`filtern()` gibt es dafür seit jeher.


## 2026-10-03 · Der Vorgabe-Zweig der Erregerspule kann NICHT bestehen — für keinen Wert

**Stand 03.10.2026, nachmittags: behoben.** Der Sitz folgt jetzt der ECKE statt dem
Boden des Polschuhs — dieselbe Regel wie im abgeleiteten Weg (`_spule_einpassen`):
`r_spule_aussen = min(r_kern_aussen - SPULE_UNTER_SCHUH_MM, sqrt(r_spule_max² - y²))`.
Gemessen über denselben Sweep: **187 von 480** bestehen jetzt (vorher 0), die 27 von 40
ohne Vorgabe sind unberührt. Dass die Reparatur keine tragende Auslegung verschieben
kann, ist genau der Befund unten: es gab keine. Reicht der Platz zwischen Sitz und
Wickelboden danach nicht, wird das als Befund MIT beiden Zahlen gemeldet statt die Höhe
still zu kürzen. Der zweite Punkt (Spanne gegen abgeleiteten Wert) bleibt offen, der
dritte (`nabe_zusammen` als Warnung) ebenfalls.

**Beobachtung.** Sobald `erregerSpuleDickeMm` **oder** `erregerSpuleHoeheMm` gesetzt
ist, weist `ema_eesm_cad.koerper` die Geometrie ab — unabhängig vom Wert, auch
mitten im Intervall, das dieselbe Funktion als „darstellbar" nennt. Gemessen am
frischen EESM-Payload (p=5, Stator 280/190, Rotor 188, Welle 100, L=80):

| Vorgabe | `passt` | abgeleitete Dicke |
|---|---|---|
| keine (beide 0) | **True** | 8,19 mm |
| Dicke 10,0 | False | 8,19 mm |
| Dicke 4,59 (= genannte Obergrenze) | False | 4,59 mm |
| **Dicke 2,0 (= genannte Untergrenze)** | **False** | 2,00 mm |
| Höhe 15,0 | False | 8,19 mm |

**Ursache, geometrisch.** Im Vorgabe-Zweig (`ema_eesm_cad.py`, Block
`if _d_gesetzt or _h_gesetzt:`) wird der Spulensitz auf
`r_spule_aussen = r_kern_aussen - SPULE_UNTER_SCHUH_MM` gesetzt. Die Prüfung
darunter verlangt
`hypot(r_spule_aussen, y) <= r_spule_max` mit
`r_spule_max = r_kern_aussen - SPULE_SCHUH_LUFT_MM` (`:627`). **Beide Konstanten
sind 0,5 mm**, also ist `r_spule_aussen == r_spule_max`. Die Ecke eines Rechtecks
liegt für jede halbe Breite `y > 0` weiter von der Achse entfernt als seine
Oberkante — die Bedingung ist damit **für jede Spule mit Breite > 0 unerfüllbar**.
Nachgemessen: r_kern_aussen 84,713 · r_spule_aussen 84,213 · r_spule_max 84,213 ·
Ecke bei y = 0,1 mm bereits 84,213…, bei y = 5 mm 84,361.

**Warum es nicht auffiel.** Der ABGELEITETE Weg geht nicht durch diesen Zweig: dort
löst `_spule_einpassen` Dicke und Höhe gekoppelt und legt die Ecke auf
`r_rot - RAND_LUFT_MM` — die richtige Bedingung. Geprüft ist genau dieser Weg; der
Vorgabe-Zweig wurde am 20.09.2026 ergänzt („0 heißt ableiten, ein gesetzter Wert
wird genommen und NACHGERECHNET"), und seine Nachrechnung ist seitdem tot.

**Zweiter, kleinerer Befund daneben.** Die genannte Spanne und der abgeleitete Wert
widersprechen sich: `koerper` meldet „Spulendicke darstellbar 2,00…4,59 mm" und
leitet im selben Lauf **8,19 mm** ab. `_d_max` kommt aus
`(b_schuh_k - b_kern_aussen)/2 - SCHUH_UEBERSTAND_MM`, der abgeleitete Wert aus dem
Füllungs-Pfad — zwei Rechnungen über dieselbe Größe.

**Nicht repariert.** Beides ändert gezeichnete Geometrie für jede Auslegung, die
diese Vorgaben setzt, und die Entscheidung, auf welche der beiden Bedingungen der
Sitz gelegt wird, ist eine Auslegungsentscheidung. Der naheliegende Weg wäre, den
Vorgabe-Zweig dieselbe `_spule_einpassen`-Platzierung benutzen zu lassen wie den
abgeleiteten.

**Was stattdessen geschehen ist (03.10.2026).** Das Tor sagt jetzt, was hilft, statt
nur abzusagen: `masse_schranken` trägt die Spannen als ZAHLEN (vorher nur im
Begründungssatz), `ema_eesm_cad.entlastung` und `ema_schenkelpol.entlastung` rechnen
Auswege und prüfen jeden gegen dasselbe Tor, `ema_pipeline._gate_laeufer` wirft
`AuslegungReisst` statt `RuntimeError` (vorher: Traceback ohne Vorschlag, obwohl der
Flussbarrieren-Zweig elf Zeilen darüber es längst richtig machte), und
`ema_diagnose._wege_laeufer` kennt die Läufer-Tore. Für genau diesen Fall meldet die
Entlastung ehrlich **keinen** Einzelweg, sondern: „Keine EINZELNE dieser Vorgaben
heilt das Tor — erst alle zusammen." Das ist die richtige Auskunft, solange der
Befund oben steht.

**Offen, dritter Punkt.** `nabe_zusammen = False` („die Polkörper berühren sich an
der Bohrung NICHT — der Läufer zerfällt in Einzelarme", `ema_pipeline.py:258`) ist
eine **Warnung**, während drei harmlosere Befunde harte Ablehnungen sind. Die
Begründung im Code („ein zu dünnes Joch sättigt, es bricht nicht") gilt für
`nabe_reicht`; `nabe_zusammen` sagt aber nicht „zu dünn", sondern „nicht
vorhanden". Die beiden teilen sich dort eine Schwere.


## 2026-09-20 · umrichter-Kriterium und Niedrigdrehzahl-Direktantrieb sind unvereinbar

**Beobachtung.** Das Sicherheitskriterium `umrichter` verlangt, dass die Maschine bei
`rpm_to` (Minimum im Schema: 500 1/min, `geom`: Untergrenze 500) mit 40–100 % der
Klemmenspannung GEMK belegt (`ok = 0.4 ≤ ausnutzung ≤ reserve`). Bei 48 V Klemmen,
Stator-D 420 mm, L 150 mm, p=12, B_gap 0.439 T sind es
**171 % mit einer Windung je Nut** — und `n_soll = max(1, floor(0.58)) = 1`
empfiehlt denselben Zustand als „passend". Keine Windungszahl erfüllt das Kriterium
bei dieser Geometrie, und eine Geometrie, die es bei 200 Nm Dauerlast und 48 V
erfüllt, müsste den Luftspaltflus mehr als halbieren — verliert damit Kt, braucht
doppelten Strom, und die thermischen Kriterien (Magnet 80 °C / Wicklung) werden
verletzt. Die beiden Kriterien schließen sich für diese Bauart aus.

**Wozu die Maschine gedacht ist.** 2,5-t-Einachsanhänger, Rad Ø 650 mm, max. 6 km/h
= **49.3 1/min am Rad, Direktantrieb** (Übersetzung 1). Mit einer Windung/Nut
(Gegen-EMK 47.4 V bei 500 1/min) sind das
49.3/500 × 47.4 V = **4.7 V = 17 % von 27.7 V (48/√3)** bei der Betriebsgrenze —
weit unter der Klemmenspannung. Die Eigenschaft, die das Kriterium schützen will
(Umrichter weder ungenutzt noch überfordert), ist am wirklichen Betriebspunkt
erfüllt; verletzt ist nur der Vergleich mit der 10-fachen, nirgends betriebenen
Drehzahl.

**Gemessen an Projekt** 20260920_213045 (Entwurf, guete=entwurf):
`sicherheit` → „✗ umrichter — Gegen-EMK bei 500 1/min belegt 171 % der
Klemmenspannung (48 V bei 1 Wdg/Nut) — passend waeren 1 Wdg/Nut". Dagegen in
derselben Rechnung: „✓ zyklusdrehzahl — Custom CSV verlangt 49 1/min gegen sichere
500 1/min" und „✓ drehzahl — sichere 500 gegen Betriebsmaximum 500 1/min".

**Fundstellen.**
- `ema_analysis.py:1062` `umrichter_passt()` — Kriterien `0.4 ≤ emf_1t·n_wdg/v_ph ≤ SPANNUNGSRESERVE`,
  `n_soll = max(1, floor(reserve·v_ph/emf_1t))`; `v_ph = v_dc/√3`.
- `ema_sicherheit.py:347–360` — Übernahme des Kriteriums in `sicherheit`,
  Bewertung bei `rpm_to` (= `payload['rpm_to']`), nicht bei der Zyklusdrehzahl.
- `ema_pipeline.py:825` `MAGNETS`: alle drei NdFeB-Grade mit `T_op_max = 80 °C`;
  nur Ferrit Y30 mit 250 °C (Br 0.40 T — für diese Last unbrauchbar), d. h. ein
  Magnet mit höherer Dauergrenze ist im Werkzeug nicht vorhanden.

**Konsequenz.** Nicht repariert. Wer eine 48-V-Niedrigdrehzahl-Auslegung prüft,
bekannt: das `umrichter`-Kriterium ist für die hier zulässige Kombination
(rpm_to ≥ 500, vdc = 48, Direktantrieb) mit 200 Nm Dauerlast **nicht erfüllbar**,
und die Verletzung ist im Bericht als solche ausgewiesen, nicht als Betriebsgrenze.

---

## 2026-09-20 · Magnet-Dauergrenze 80 °C bei Auslegungspunkt 500 1/min / 200 Nm (Projekt 20260920_213045)

`magnet_dauer` verletzt um 4 K (84 °C ≥ Grenze 80, NdFeB N35) am **Auslegungspunkt
500 1/min / 200 Nm** — einem Punkt, den der Zyklus nie erreicht (max. 49 1/min,
T_rms 165 Nm; dort: Magnet 67 °C, erfüllt). Im Werkzeug ist nur N35/N42/N50 mit
80 °C oder Ferrit mit 0.4 T Br wählbar (Fundstelle: `ema_pipeline.py:825`);
Kühlung `forced` ist der beste nicht-flüssige Zustand, den `cooling` hergibt
(natural/forced/water/oil). Ob Ölbad die 80 °C am Auslegungspunkt unterbietet,
wird in Runde 3 gemessen.

## 2026-09-20 — Der Feldlöser sah bei allen fünf Bauarten denselben PM-Läufer

**Beobachtung** (gemeldet): „die geometrie wird zur zeit nicht korrekt an den
feldlöser weitergereicht. überprüfe auch die berechnungen der anderen neuen
maschinen" — und nachgereicht: „auch die berechnung in elmer haut nicht hin."

**Messung.** `ema_analysis.py` enthält die Zeichenkette `machineType` **null
mal**. Der 2-D-FDM-Rasterer baut den Läufer aus `magnet_legs` — also Magnete,
und sonst nichts. Nachgemessen über alle fünf Bauarten, Raster 200 × 200,
derselbe Payload:

| Art | Magnetzellen | Eisenzellen |
|---|---:|---:|
| PSM | 1224 | 15627 |
| ASM | 1224 | 15627 |
| SynRM | 1224 | 15627 |
| EESM | 1224 | 15627 |
| GSM | 1224 | 15627 |

**Bit für Bit dieselbe Maschine.** Eine Asynchronmaschine bekam Permanent­magnete
und keinen Käfig; ein Reluktanzläufer Magnete statt leerer Barrieren; ein
Schenkelpolläufer Magnete statt Polen und Erregerspulen; die Gleichstrom­maschine
Magnete statt eines gewickelten Ankers.

Am Schenkelpolläufer (2p = 8, Polbedeckung 0,55) in Zahlen, die den Kern der
Sache treffen: **2,2 % Luft im Läuferring, wo 45 % hingehören.** Der
Reluktanz­unterschied — der die Bauart *ausmacht* — fehlte vollständig.

**Warum es niemandem auffiel:** die Pipeline weist die Feldstufe für diese Arten
ab (`_gate_maschinenart`), und dort schaut man hin. Jeder **andere** Einstieg in
denselben Löser tat es nicht: `feldbild`, `ema_welle.pruefen` (ein echter
Feldlauf, auf dem die Getriebe-Bohrungsentscheidung ruht),
`ema_optimize._eval_geom` (und damit Zielwertsuche, Parameterstudie,
`screen`, `leistung`, `ausreizen`, die KI-Vorsortierung), der Handy-Pfad.
Keines dieser Module nennt die Maschinenart auch nur.

**Und Elmer genauso.** `ema_em3d.py`: null Treffer auf `maschinenart`, elf auf
`magnet_legs`/`magnet_rects` — der 3-D-Pfad baut denselben PM-Läufer. Die beiden
ASM-Löser (`ema_em2d_harm`, `ema_em3d_harm`) sind sauber, sie rufen
`pruefe_stufe`; sie sind aber auch nur für die ASM gebaut.

**Status: behoben.**

1. **Der Läufer kommt aus DERSELBEN Quelle wie die Leinwand.** `_rasterise`
   fragt `ema_maschinenart`; hat die Art keine Magnete, stempelt es
   `ema_laeuferbild.teile()` ins Gitter — genau die Teile, die die Live-Vorschau
   zeichnet. Damit können Bild und Feld nicht auseinanderlaufen, sie lesen eine
   Funktion. Neu dafür `ema_laeuferbild.rastere`/`_stempel`, der **Python-
   Zwilling** von `rastere`/`_stempel` in `ema_laeufer.js` (dieselbe Lage wie
   `magnet_legs` und sein JS-Spiegel).
   Die eingeprägte **Erregerdurchflutung** geht als Stromdichte mit: Gleichstrom
   ist magnetostatisch exakt darstellbar, anders als der Käfig.
   Gemessen danach — Luft im Läuferring, Raster 300:

   | Art | Magnetzellen | Luft im Ring |
   |---|---:|---:|
   | PSM | 2752 | 1,7 % |
   | ASM | 0 | 13,1 % |
   | SynRM | 0 | 18,8 % |
   | EESM | 0 | 54,7 % |
   | GSM | 0 | 18,1 % |

   **Die PSM bleibt Ziffer für Ziffer dieselbe** — `test_fdm_golden.py` grün.

2. **Der SynRM war dabei der zweite Fund.** Seine Flussbarrieren kommen als Form
   `tasche`, und die fehlte im ersten Wurf des Python-Stempels: gemessen **0,0 %
   Luft**, also ein Vollzylinder — ein Reluktanzläufer ohne Reluktanz­unterschied
   ist keine Maschine. Jetzt 18,8 %.

3. **Der 3-D-Elmer-Pfad weist ab, statt zu nähern.** `ema_em3d._tor_layout`
   fragt zuerst die Maschinenart und nennt für die ASM den Weg, den es gibt
   (`feld3d`/`ema_em3d_harm`, harmonisch), statt nur abzusagen — dieselbe
   Haltung wie `ema_maschinenart` überall.

## 2026-09-20 — Der Schenkelpol hatte keine Millimeter

**Beobachtung** (gemeldet): „ich möchte auch abmasse der eesm eingeben … breite
spule, breite kern, polschuh, höhe der spule, kegelwinkel. Das soll sich dann
auch im canvas ändern."

Jede Abmessung des Schenkelpols war ein **Verhältnis** (`polbedeckung`,
`polSchuhAnteil`, `polKernAnteil`, `polHoeheAnteil`, `KEGEL_VERJUENGUNG`).
Richtig für einen ersten Wurf und falsch, sobald jemand eine Zeichnung vor sich
hat: dort stehen Millimeter.

**Status: behoben.** Fünf neue Schlüssel — `polSchuhBreiteMm`,
`polKernBreiteMm`, `erregerSpuleDickeMm`, `erregerSpuleHoeheMm`,
`polKegelWinkelGrad` — im Geometrie-Reiter unter *Maschinenart*, über
`cae_cli --set` und in der Parametertabelle.

Zwei Entscheidungen dabei, beide der Hausregel folgend:

* **0 heißt „wie bisher ableiten".** Jede bestehende Auslegung bleibt damit
  Ziffer für Ziffer dieselbe.
* **Ein gesetzter Wert wird genommen und nachgerechnet, nicht geklemmt.** Ein
  geklemmter Wert sieht für den Aufrufer wie ein angenommener aus (dieselbe
  Regel wie `cae_cli --set`), und bei einer Zeichnung ist das besonders schlimm:
  wer 24 mm einträgt und 21,7 zurückbekommt, ohne dass es jemand sagt, zeichnet
  die falsche Maschine. Was nicht geht, steht mit **beiden** Zahlen in
  `masse_befund` und macht `passt` falsch — etwa „Spulendicke: 40,00 mm liegt
  außerhalb dessen, was hier darstellbar ist (2,00…5,36 mm)".

Der **Kegelwinkel** ersetzt das Verhältnis: ein Winkel ist das, was auf einer
Zeichnung steht, das Verhältnis hängt an der Kernhöhe.

Die Kette ist geschlossen und nachgemessen — dieselbe Vorgabe bewegt Zeichnung
*und* Feld, weil beide `teile()` lesen: Polschuh 55 mm → Luft im Läuferring
54,7 → 37,8 %; Spule 4 × 35 mm → Zellen mit Spulenstrom 1764 → 2020; Kegel 5° →
54,7 → 56,1 %.

**Nebenbefund, mitbehoben:** die Begründung, warum ein Pol nicht passt, stürzte
ab. `schranken[bindend]` führt nur die vier *geometrischen* Schranken, `bindend`
kann aber auch `kernfluss` oder (neu) `vorgabe` sein — `KeyError` an genau der
Stelle, die erklären soll, warum etwas nicht geht.

---

## 2026-09-19 — Der Planetensatz waren drei lose Räder, und niemand maß nach

**Beobachtung** (gemeldet): „hier `/home/cae/t2g/TextToGeometry` gibt es noch ein
Planetengetriebe bzw. Skripte zum Bau anderer Getriebe. Die möchte ich bei uns
integriert haben, in die Getriebeauslegung."

Beim Portieren fiel auf, dass unsere eigene Zeichnung vier Fehler hatte — alle
still, weil der gezeichnete Satz **nie nachgemessen** wurde. `ema_getriebe`
rechnet den Planetensatz seit jeher vollständig (Montage- und
Nachbarbedingung, Tragfähigkeit, zwei Stufen, Einbau in der Welle); gezeichnet
wurden davon Sonne, Planeten und Hohlrad — und sonst nichts.

**Messung** (2p-Satz z = 25/20/65, m = 2, b = 20, drei Planeten; alle Zahlen
über paarweises `common().Volume` am gebauten Körper):

1. **Die Zahnphase fehlte.** FCGear setzt auf *jedes* Rad einen Zahn auf die
   +x-Achse; zwei so erzeugte Räder stehen Zahn auf Zahn. Gemessen über einen
   Versatzlauf in zwölf Schritten: 0° → **336,7 mm³** Durchdringung Sonne ↔
   Planet, **9,00° = genau eine halbe Zahnteilung → 0,000 mm³** — und zwar am
   Planeten bei 0° *wie* bei 120°. Das Hohlrad ebenso: 0° → 437,0 mm³, Minimum
   bei 2,77° = einer halben Hohlradteilung.
   **Der naheliegende Term ist falsch.** `Stellwinkel · z_Sonne/z_Planet` ist
   die Verdrehung, die ein *abrollender* Planet erfährt — Kinematik, nicht
   Zeichnung. Mit ihm blieben 262,9 mm³ stehen, ohne ihn 0,0.
   **Warum das jahrelang niemandem auffiel:** der Phasenfehler verschwindet in
   Zähnen gerechnet genau dann, wenn `z_Sonne/n_Planeten` aufgeht. Der von
   unserer eigenen Auslegung erzeugte Satz (z_Sonne 24, drei Planeten) trifft
   das zufällig — 8,000 Zähne. Bei 25/3 sind es 8,333, und dann frisst sich
   jeder Planet durch die Sonne.

2. **Die Räder hatten keine Bohrung.** FCGear zeichnet eine volle Scheibe.
   Gemessen steckte die Sonnenwelle zu **27,0 %** im Sonnenrad und jeder
   Planetenbolzen zu **58,8 %** im Planetenrad.

3. **Die FCGear-Quellobjekte blieben im Dokument stehen** — an ihrem Ursprung,
   also mitten in der Baugruppe. Ein gespeicherter Planetensatz enthielt jedes
   Rad **zweimal**, einmal richtig platziert und einmal in der Mitte. Der
   STEP-Export war davon nicht betroffen (er exportiert nur den Verbund), die
   `.FCStd` sehr wohl — und wer sie öffnet, sieht den Salat.

4. **Es gab keinen Steg.** Kein Planetenträger, keine Bolzen, keine Wellen —
   drei Räder, die im Raum stehen. Das ist keine Baugruppe, und die Frage
   „passt der Satz in die Hohlwelle?" lässt sich daran nicht beantworten.

**Status: behoben.** Jeder Planet und das Hohlrad werden um eine halbe
Zahnteilung *ihres eigenen* Rades gedreht; Sonne und Planeten bekommen ihre
Bohrung; das FCGear-Objekt wird nach dem Kopieren entfernt; dazu Planetenbolzen,
zwei Stegwangen mit Bohrungen für Sonnenwelle und Bolzen, Sonnen- und Stegwelle.
Neu auch die **Verzahnungsart** (gerade · schräg · Pfeil, `erg["verzahnung"]` /
`beta_grad`) — `ema_getriebe.zahnform` rechnet `beta` längst mit, gezeichnet
wurde es nur bei der Stirnradstufe.

**Und der Satz wird nachgemessen**, wie der EESM-Läufer in `bau_eesm.py`:
paarweise `common().Volume`, Ergebnis in `durchdringung_pct` /
`durchdringung_paare`. Nach der Korrektur **0,0 %**.

### Der Schiedsrichter darf keine zweite Boolesche sein

Dabei kam ein eigener Befund heraus: **OCCs `common()` liefert bei einem
gescheiterten Schnitt bitgleich das Volumen eines Operanden.** Gemessen an
Planet 0 gegen das Hohlrad: 22.364,90 mm³ = exakt das Planetenvolumen, also
„der Planet steckt vollständig im Hohlrad" — während die beiden baugleichen
Nachbarn 0,0 % zeigten und der Planet sichtbar im *Loch* des Rings saß.

Zwei naheliegende Gegenproben versagen: der **Hüllquader** entscheidet nichts
(der eines Planeten liegt sehr wohl in dem des Hohlrads), und ein zweites
`cut()` scheitert an derselben Stelle und *bestätigt* den Fehler. Der
Schiedsrichter ist deshalb eine **Punktprobe**: 600 Würfe in den Hüllquader des
kleineren Körpers, gezählt wird, wie viele in beiden liegen. Ergebnis
**0,0 % aus 346 Proben** — die Boolesche irrt. Der Fund wird als *nicht
nachweisbar* gemeldet und nicht als Durchdringung: eine 100-%-Meldung, die in
Wirklichkeit ein Fehlschlag ist, schickt die Suche ans falsche Ende.

### Und der Satz landet im Motor

`ema_getriebe_cad.in_motor_bauen` öffnet das **gebaute** Motordokument und legt
den Planetensatz mittig auf die Achse. Ein dritter Erzeuger wäre die dritte
Abschrift derselben Geometrie gewesen — dieselbe Stelle, an der in diesem Repo
schon zweimal etwas auseinanderlief. Der Bohrungsdurchmesser wird dabei am
Läuferkörper **abgelesen** (kleinster Zylinder um die Drehachse), nicht aus dem
Payload geglaubt, und Getriebe gegen Motor wird paarweise nachgemessen. Passt
es nicht, ist das ein Befund mit zwei Zahlen: gemessen braucht der i = 5-Satz
**100,6 mm** Bohrung, gezeichnet waren **100,0 mm**.

**Zur Herkunft.** Die Bauteile (Steg mit Bohrungen, Bolzen, Wellen, das
Nachmessen) stammen als Vorbild aus `Tools/planetengetriebe.py` in
`/home/cae/t2g/TextToGeometry`, die Verzahnungsarten aus
`Tools/getriebe_fcgear.py`. **Portiert, nicht kopiert**, und dafür gibt es zwei
harte Gründe: T2G steht unter PolyForm-Noncommercial-1.0.0-NoMilitary, dieses
Repo unter MIT und öffentlich auf GitHub — beide gehören demselben Urheber, er
darf das also entscheiden, aber eine wörtliche Übernahme wäre eine stille
Umlizenzierung und keine Nebenwirkung. Und technisch: T2Gs Module importieren
FreeCAD auf Modulebene und laufen *in* FreeCAD, während `ema_getriebe_cad` Text
für einen fremden Prozess schreibt — eine wörtliche Kopie liefe hier gar nicht.

---

## 2026-09-19 — Der Wickelraum hatte zwei Quellen, und beide waren falsch

**Beobachtung** (gemeldet): „versuche jetzt die Spulen kegelig zu machen und
den Bauraum maximal auszunutzen. Das ‚Dach' oben bzw. außen muss ggf. in der
Breite mitwandern."

**Messung.** Der Zwischenpolraum war zu 12,5 % genutzt (`fenster_ausl`). Der
Grund ist nicht die Zeichnung, sondern eine Auslegungsvorgabe: `A_cu =
F_pol/J` mit J = 5 A/mm² — die Stromdichte bemisst die Wicklung, der Platz
spielt keine Rolle. Nachgemessen am Polkörper (2p = 8, Rotor 188,6, Welle 38,
Polbedeckung 0,55), halbe freie Breite neben dem Kern über dem Radius:

| r [mm] | 19 | 30,2 | 40 | 49,3 | 60 | 85 |
|---|---:|---:|---:|---:|---:|---:|
| Polteilung erlaubt | −4,4 | 0,0 | 3,9 | 7,5 | 11,7 | 21,5 |
| Polschuh deckt | 5,5 | 5,5 | 5,5 | 5,5 | 5,5 | 5,5 |

Unter r = 30,2 mm ist **kein** Platz (dort überdecken sich die Polkörper —
das ist die Nabe), von 30,2 bis 49,3 bindet die **Polteilung** (also ein
Kegel), darüber der **Polschuh**, der die Spule gegen die Fliehkraft halten
muss. Gezeichnet war eine Spule von r 65,0 bis 84,5.

**Und die analytische Fensterformel wusste von alldem nichts.**
`ema_eesm._pol_fenster` rechnet ein Rechteck (Fensterbreite × Fensterhöhe) und
kennt weder den Polschuh noch das Schrumpfen der Polteilung: **2024 mm²
analytisch gegen 443 mm² zeichenbar** — Faktor 4,6. Der Kupferquerschnitt hatte
damit zwei Quellen, und die Zeichnung war die kleinere.

**Status: behoben.** `ema_eesm_cad.wickelraum` ist die EINE Quelle; sie ruft
`erregung` ausdrücklich nicht auf, damit `erregung` sie umgekehrt lesen kann.
Neu `geom.erregerSpuleFuellung`:

* `vorgabe` (Standard) — die Stromdichte bemisst, jede bestehende Auslegung
  rechnet Ziffer für Ziffer weiter.
* `max` — der gezeichnete Bauraum bemisst. Gemessen am selben Läufer: Kupfer je
  Pol **106 → 184 mm²**, Stromdichte **5,00 → 2,87 A/mm²**, Erregerverlust
  **154,1 → 88,6 W**, Läuferverlust **218,1 → 152,6 W**; die Spule wird von
  19,45 auf **38,16 mm** hoch und leicht kegelig.

**Das „Dach" wandert mit — aber nur, soweit es sich rechnet.**
`wickelraum_max` fährt die Polbedeckung über ihre erlaubte Spanne und misst.
Ein breiterer Schuh überdeckt eine dickere Spule, zwingt aber zugleich einen
breiteren Kern (er nimmt mehr Fluss auf), und der frisst den Platz fast so
schnell, wie der Überstand ihn gewinnt: 0,55 → **0,58** bringt 443 → 446 mm²,
also 0,6 %. Nach unten wird nicht gesucht — die Polbedeckung ist eine
magnetische Entscheidung des Menschen, hier darf sie nur folgen.

**Vier Fehler kamen dabei heraus, jeder still:**

1. **`0.5 * b` ist der Entartungsradius.** Der Verrundungsradius der Wicklung
   war genau die halbe Kernbreite — der Wert, bei dem OCC mit „BRep_API:
   command not done" aussteigt. Bei der kleinen Spule lag er weit darunter, bei
   der ausgefüllten traf er ihn (b = 20,24 mm, Radius 10,12) und **beide**
   Körper blieben eckig; die scharfen Ecken der Spule steckten dann im Blech,
   weil die Tasche daneben sehr wohl gerundet war. Jetzt 0,45, dazu eine
   Leiter 1,0/0,6/0,35/0,2 in beiden Verrundern.
2. **Spule und Tasche rechneten ihren Radius getrennt** — dieselbe Formel, aber
   die Tasche maß die Kernbreite 0,3 mm weiter innen. Gemessen blieben
   **26,33 mm³** Kupfer im Blech. Jetzt EINE Funktion (`_spulenradius`).
3. **Die Rand-Schranke klemmte die falsche Seite.** `schranken["rotorrand"] /
   kegel` unterstellt, der Kern sei innen breiter; `KEGEL_VERJUENGUNG` = 0,80
   macht ihn aber außen breiter. Gemessen bei 2p = 2 stand die Kernecke bei
   **95,43 mm** gegen einen Rand von 94,30 mm.
4. **`b_pol` ist eine Bogenlänge und wurde als Breite benutzt.** Bei 2p = 2 und
   α = 0,85 sind das 251,8 mm an einem Läufer von 188,6 mm Durchmesser. Jetzt
   als Sehne gedeckelt.

Wo `max` nicht geht (sehr wenige, sehr breite Pole — 2p = 2), wird **nicht**
abgewiesen, sondern auf die Stromdichte zurückgefallen und das gesagt
(`fuellung_hinweis`).

Gegenprobe: ein Festkörper und keine Durchdringung bei 2p = 2/4/8/12, jeweils
`vorgabe`/`rechteck`, `vorgabe`/`kegel` und `max`/`kegel`; Werkbank und
Pipeline Ziffer für Ziffer gleich (1.002.512,91 ↔ 1.002.513 · 1.112.690,99 ↔
1.112.691 · 1.075.942,09 ↔ 1.075.942 · 1.176.503,52 ↔ 1.176.504).

**Was dabei SCHLECHTER wird, und das steht so im Ergebnis:** der kegelige Kern
ist am Bohrungsrand schmaler, also wird die Nabe kleiner — 9,36 → 4,92 mm,
B_Nabe 1,81 → 3,64 T gegen 1,70 T Blechgrenze. Der Befund „die Nabe trägt den
Fluss erst ab 2p = 12" verschärft sich damit; gerechnet und gemeldet wird er,
geheilt nicht.

---

## 2026-09-19 — Der Polfuß war ein Keil, und er verdeckte eine Zeichnerdrift

**Beobachtung** (gemeldet, am FreeCAD-Modell): „die muss noch etwas mehr
überstehen. unten muss der Polschuh tiefer in den Rotor reichen, zur Zeit ist
dort eine Art Keil."

**Messung.** Am Schnitt des gebauten Läufers (EESM, 2p = 8, Rotor Ø 188,6,
Welle Ø 38, Polbedeckung 0,55) nachgemessen, nicht am Parameter:

1. **Der Keil.** `ema_eesm_cad.koerper` setzte den Polfuß **oberhalb** des
   Jochrings an: über den unteren 5,834 mm der 26,517 mm Kernhöhe öffnete sich
   der Kern von **21,70 auf 43,92 mm**, also auf die halbe Polteilung. Im
   Zwischenpolraum stand dadurch je Pol eine messerförmige Eisenspitze, und der
   Wickelraum musste in 19,45 statt 26,5 mm untergebracht werden.
   Zwei Dinge sprachen dagegen, beide nachprüfbar: der Fuß stammte aus der
   Zeit, als der Kern selbst noch ein nach innen schmaleres Trapez war und zum
   Joch hin ein Dreieck klaffte — seit `b_kern_innen == b_kern_aussen` schloss
   er eine Lücke, die es nicht mehr gab; und er widersprach der **daneben
   gerechneten** Befestigung: `ema_schenkelpol.befestigung` legt den Hals mit
   `HALS_ZU_KERN = 0,70` **schmaler** als den Kern (15,2 mm) und in eine Nut im
   Joch, gezeichnet war das Gegenteil.

2. **Der Rest des Polschuhs.** Die Spulentasche endete seitlich an der Spule
   (halbe Breite 17,63 mm), der Polschuh reicht aber bis 20,4 mm. Seine
   Unterseite ist ein **Bogen** (r = 84,48), die Taschendecke eine **Ebene**
   (x = 84,98) — am Taschenrand taucht der Bogen um die Stichhöhe
   `r − √(r² − y²)` = **1,85 mm** unter die Ebene und blieb als Keil aus
   Schuheisen stehen.

3. **Die Drift, die der Fuß verdeckte.** `ema_freecad._pol_koerper` baute den
   kegeligen Polkörper mit `b_kern_spuleanfang_mm` an der Jochkante,
   `bau_eesm.py` dagegen mit `b_kern_innen_mm` — zwei Neigungen aus derselben
   Quelle. Gemessen am selben Payload (2p = 6, kegelig): **1.395.722 gegen
   1.394.947 mm³**, 775 mm³ Unterschied. Solange der Fuß darüber lag, fiel das
   nicht auf. Derselbe Fehler steckte in den Innenschneidern von Spule und
   Tasche: sie reichen 1 mm über den Kern hinaus und interpolierten ihre Breite
   zwischen den beiden Endradien, bekamen also beim Kegel eine andere Neigung
   als der Kern — gemessen **102,45 mm³** Kupfer im Blech bei 2p = 6, nach der
   ersten Korrektur noch 0,03 mm³.

**Fundstelle.** `ema_eesm_cad.py` (`POLFUSS_ANTEIL`, Fußrechnung in `koerper`),
`ema_freecad.py` (`_pol_koerper`, `_pol_spule`, `_pol_spulentasche`),
`ema_laeuferbild._eesm`, `ema_pipeline.render_cross_section` (EESM-Zweig),
`bau_eesm.py` (`_schuh`/`_trapez`-Schleife, `_spulentasche`).

**Status: behoben.** Der Polkörper läuft jetzt mit voller Breite bis auf den
Jochring durch; der Fuß liegt **unter** `r_fuss_mm`, also im Joch
(`h_fuss_mm` tief, Hals `b_hals_mm`, unten `b_fuss_mm`), und wird **nicht**
gezeichnet — Joch und Pol sind EIN Festkörper, eine Nut darin wäre im Schnitt
unsichtbar; gerechnet wird sie weiter in `ema_schenkelpol.befestigung`. Die
Spulentasche reicht seitlich bis `r · tan(halber Schuhwinkel)` plus
`TASCHE_UEBERSTAND_MM` = 0,5 mm und nach unten bis auf den Jochring, der Schuh
bekommt damit eine **flache** Unterseite über seinen ganzen Überstand. Beide
Innenschneider werten mit `_b_kern_bei` dieselbe Kerngerade aus.
Nachgemessen am gebauten Körper: keine Durchdringung (`common().Volume = 0`)
bei 2p = 4/6/8/12, mit und ohne Dämpferkäfig, rechteckig und kegelig; der
Taschenschnitt nimmt 37.869 statt 25.983 mm³ Eisen heraus, das Rotorvolumen
fällt von 1.395.371 auf 1.334.898 mm³. **Werkbank und Pipeline bauen jetzt
Ziffer für Ziffer denselben Läufer** — rechteckig 1.334.898,12 gegen 1.334.898,
kegelig 1.394.946,8 gegen 1.394.947.

Der Zweig für einen Fuß **über** dem Joch bleibt in allen vier Zeichnern
stehen (`r_fuss_mm > r_joch_aussen_mm + 0,2`), damit ein gespeicherter
Maßsatz aus der Zeit davor unverändert gezeichnet wird.

**Nachtrag, gleicher Tag — der Jochring fällt ganz weg.** Gemeldet: „du musst
den Kern, auf dem die Spule gewickelt ist, einfach bis zur Rotorachse
verlängern. Am Ende den Wellendurchmesser abziehen." Umgesetzt: der Polkörper
läuft mit seiner Breite bis auf die Wellenbohrung durch, die Bohrung wird nach
dem Verschmelzen abgezogen, und ein Jochring wird nur noch für gespeicherte
Maßsätze gezeichnet (`r_joch_aussen_mm > r_welle_mm + 0,05`). Die Kernhöhe
steigt damit von 26,5 auf **66,0 mm**.

**Das Joch ist dann das, was die Polkörper miteinander bilden**, und das wird
gerechnet statt angenommen: zwei Körper der halben Breite `w`, deren Achsen
`2π/2p` auseinanderliegen, überdecken sich bis `r_nabe = w/sin(π/2p)`.
Gemessen am selben Läufer (Rotor Ø 188,6, Welle Ø 38, Polbedeckung 0,55):

| 2p | b_kern | r_nabe | Nabenhöhe | Fluss verlangt | B_Nabe |
|---:|---:|---:|---:|---:|---:|
| 4 | 43,41 | 30,69 | 11,70 | 25,15 | 2,90 T |
| 6 | 28,94 | 28,94 | 9,94 | 16,76 | 2,28 T |
| 8 | 21,70 | 28,36 | 9,36 | 12,57 | 1,81 T |
| 12 | 14,47 | 27,96 | 8,96 | 8,38 | 1,26 T |

**Zusammen hängt der Läufer in allen vier Fällen** (`r_nabe > r_welle` = 19 mm,
ein Solid, in FreeCAD nachgemessen) — **den Fluss trägt die Nabe erst ab
2p = 12.** Darunter steht sie über der Sättigungsgrenze des Blechs (M270-35A,
1,70 T), bei 2p = 4 um den Faktor 1,7. Das ist ein **Befund und keine stille
Korrektur**: `nabe_reicht`, `h_nabe_mm` und `B_nabe_T` stehen im Ergebnis und
in jeder Ausgabe von `bau_eesm.py`. Wer die Nabe tragfähig will, hat drei
gerechnete Hebel — mehr Pole, breiterer Kern, oder ein ausdrücklich gesetztes
`polHoeheAnteil`, das den alten Jochring zurückholt.

**Was NICHT mitwächst, und warum:** die Spule bleibt 6,48 × 19,45 mm. Ihr
Kupferquerschnitt kommt aus `A_cu = F_pol/J`, also aus Strom und Stromdichte —
nicht aus dem Platz. Der gewonnene Wickelraum ist Reserve, kein Kupfer.

Zwei Stellen mussten dabei mitgezogen werden, beide gemessen: die
Kernbreitenschranke „Platz am Joch" hing an der Polteilung **am Wellenradius**,
wo sich die Körper jetzt überdecken sollen — sie zählt jetzt am **Spulenfuß**
(`teilung`), wo zwei Wicklungen sich wirklich nicht berühren dürfen; und die
Spulentasche darf **nicht** bis zur Bohrung durchgezogen werden: ihre halbe
Breite ist 17,6 mm, die halbe Polteilung an der Bohrung aber 7,9 mm — sie hätte
die Nachbarpole weggeschnitten und genau die Nabe zerstört.

**Zweiter Nachtrag — der Vielzahn an der Bohrung.** Gemeldet: „bitte bis zur
Achse verlängern und dann den Wellendurchmesser abziehen, sonst entsteht ein
merkwürdiger Vielzahn." Genau so war es, und es ist rechenbar: die Stirnfläche
eines Arms ist eine **ebene Sehne**. Endet sie bei `r0`, erreicht der Arm den
Bohrungskreis nur innerhalb von `acos(r0/r_welle)` um die eigene Achse — bei
r0 = 18,5 und r_welle = 19 sind das **±13,2°**, während die halbe Polteilung
bei acht Polen **22,5°** beträgt. Dazwischen blieb die Bohrung unbedeckt, und
heraus kam ein Vielzahn statt eines Kreises. Ab der Achse gezeichnet deckt
derselbe Arm ±89,7°, die Lücke kann nicht mehr entstehen. Gemessen an der
fertigen Bohrungskontur: **r = 19,0000 … 19,0000 mm, Abweichung 0,0000 mm.**

Drei Fälle mussten dabei mit, alle drei am Läufer nachgemessen:

1. **Zwei Pole liegen auf einer Geraden.** Bei `ACHSE_MM = +0,1` blieb zwischen
   zwei gegenüberliegenden Körpern ein 0,2 mm breiter Schlitz über die ganze
   Bauhöhe; ab 2p = 4 deckt ihn ein anderer Arm zu, bei 2p = 2 zerschnitt er
   den Läufer — **6 Festkörper statt einem**. `ACHSE_MM = −0,5` (ein Stück
   *jenseits* der Achse) kostet nichts, weil die Bohrung ohnehin abgezogen wird.
2. **`r1·tan(halber Schuhwinkel)` divergiert.** Bei 2p = 2 (halber Schuhwinkel
   49,5°) stand die Taschenbreite bei 99,4 mm.
3. **Die Taschendecke ist eine Ebene, der Läuferrand ein Kreis.** Über der
   Breite, die die Spule braucht, muss oberhalb der Decke noch Eisen stehen —
   sonst trennt die Tasche den Polschuh ab (gemessen bei 2p = 2: **vier
   Schuhspitzen zu je 23.347 mm³**). Die Decke sinkt deshalb auf
   `sqrt(r_rotor² − ya²) − TASCHE_STEG_MM`, aber nie unter die Spulenoberkante
   plus Isolierluft — dort fehlten sonst 0,03 mm und es blieben 25,95 mm³
   Kupfer im Blech. Bei acht Polen bindet keines von beidem, die Decke bleibt
   `r_kern_aussen`.

Gegenprobe nach dem Umbau: **ein Festkörper und keine Durchdringung bei
2p = 2/4/6/8/12**, rechteckig und kegelig; Werkbank und Pipeline weiter Ziffer
für Ziffer gleich (1.134.813,98 ↔ 1.134.814 · 1.099.772,24 ↔ 1.099.772 ·
1.028.000,62 ↔ 1.028.001 · 1.111.818,64 ↔ 1.111.819 · 1.116.060,13 ↔
1.116.060).

---

## 2026-09-19 — Die Polzahl war bei drei von fünf Bauarten nicht einstellbar

**Beobachtung** (gemeldet): „Wie stelle ich bei der EESM die Anzahl der Pole
ein. eigentlich bräuchte ich auch immer die Einstellparameter des Stators im
Geometrie-Tab. Die Anzahl der Stäbe und alle anderen maschinenartspezifischen
Parameter müssen dann unter Maschinenart einstellbar sein."

**Messung.** Das Feld `p_pairs` stand im Abschnitt **Magnet-Topologie**
(`grp_magnet_topo`), und `_updateArtVis` blendet den bei jeder Bauart ohne
Magnete aus. Im Browser nachgemessen (Sichtbarkeit über die ganze
Elternkette): `p_pairs` war für **ASM, EESM und GSM „aus"** — die Polzahl, die
jede dieser Maschinen hat, war über die Oberfläche nicht erreichbar. Sie
existierte nur noch über `cae_cli --set p=…` und die Parameter-Tabelle.

Dazu fehlten **zwölf weitere art-spezifische Parameter** vollständig, obwohl
sie im Schema standen und gerechnet wurden: `rotorType`, `rotorBars`,
`rotorSkewSlots`, `rotorTurnsPerSlot`, `bZielT`, `polBefestigung`,
`polBolzen`, `polBolzenGewinde`, `daempferkaefig`, `daempferStaebeJePol`,
`daempferMat`, `armatureWinding`. Für den, der davorsitzt, gab es sie nicht —
dieselbe Lage wie bei den Wicklungswerkstoffen einen Tag zuvor.

Und eine dreizehnte Größe gab es überhaupt nicht: die **Polbedeckung des
Schenkelpols** war die Konstante `ema_eesm.POLBEDECKUNG = 0.68`. Sie
entscheidet über Grundwelle, Erregerdurchflutung, Kupfermasse und den Platz
für die Spule — gemessen senkt 0,80 statt 0,68 die nötige Durchflutung von
459 auf 423 A je Pol und verbreitert den Polschuh von 67,2 auf 79,0 mm.

**Fundstelle.** `ema.html` (Abschnitt Magnet-Topologie / Maschinenart,
`_updateArtVis`, `_matLaden`, `applyPayload`), `ema_eesm.polmasse` /
`erregung`, `ema_gsm.staenderpole` / `ankerrueckwirkung`.

**Stand: behoben.**

- Die Polzahl steht bei der **Maschinenart** — sie gehört jeder Bauart, nicht
  den Magneten —, mit der abgeleiteten Polzahl daneben (in der Maschine zählt
  2p). Hauptabmessungen und Stator/Wicklung waren und bleiben immer sichtbar.
- Alles, was nur eine Bauart hat, sitzt unter der Maschinenart und wird über
  `data-arten` ein- und ausgeblendet (`.art-feld`). **`_ART_FELDER` ist die
  eine Tabelle** Elementkennung → Schemaschlüssel: gefüllt, gebunden und in
  `applyPayload` zurückgeschrieben aus derselben Zuordnung. Grenzen,
  Auswahllisten und Vorgaben kommen aus `/param_schema` — ein Wert, den die
  Maske anbietet und `--set` abweist, wäre die nächste stille Lücke.
- `ema_eesm.polbedeckung(geom)` ist die eine Quelle der Polbedeckung; ohne
  Angabe bleibt es bei 0,68, also rechnet jede bestehende Auslegung Ziffer für
  Ziffer weiter. Ein **eigener** Parameter und ausdrücklich nicht
  `poleArcFrac`: das ist die Magnetbedeckung der PSM (0,83), ein Schenkelpol
  liegt bei 0,65…0,75.

**Und der Kennwertkasten der Vorschau nahm die halbe Spalte.** Gemeldet als
„bei den neuen Varianten nehmen die Echtzeitdaten die Hälfte der
Geometrieeinstellung ein". Gemessen: der Kasten ist schrumpfend breit
(`position:absolute` ohne Breite), also bestimmt ihn sein **breitestes Kind**.
Solange das die Kennwertzeilen waren, blieb er bei **231 px**; der
Läuferhinweis — mehrere Sätze, bei einem nicht auslegbaren Käfig über 400
Zeichen — zog ihn auf **425 px** und in der Höhe über die halbe Vorschau.
Behoben zweifach: `max-width: 250px` auf dem Kasten (darunter bricht der Text
um, statt zu ziehen) und ein **gekürzter** Hinweis mit Aufklappen
(`_HINWEIS_KURZ`), der beim ⚠ anfängt — das ist der Grund, warum er dasteht,
nicht die Beschreibung der Bauart. Nachgemessen: 250 px breit, drei Zeilen
höher als bei der PSM statt doppelt so breit.

**Nicht behoben, weil kein Fehler.** Die Meldung
`Gtk-Message: Not loading module "atk-bridge"` kommt vom Browser, den
`start.sh` öffnet, nicht vom Server — GTK sagt dort, dass es eine
Barrierefreiheits-Brücke selbst mitbringt. Sie erscheint auch ohne dieses
Werkzeug und hat keine Wirkung. Was in derselben Ausgabe eine echte Auskunft
ist: `Address already in use` — dann läuft bereits ein Server auf `:5000`, und
der neue beendet sich sofort, während der **alte** weiter bedient. Beim Testen
ist das die Falle: die Seite lädt, zeigt aber den Stand vor der Änderung.

---

## 2026-09-19 — Drei Bauteile, die nur als Lücke benannt waren

**Beobachtung.** Drei Dinge standen im Werkzeug ausschließlich als Text darüber,
dass es sie nicht gibt:

* `ema_eesm_cad.koerper` gab seit jeher `ungeprueft: "Polbefestigung
  (Schwalbenschwanz/Bolzen) und die Fliehkraft am Polfuss sind NICHT
  gerechnet"` heraus — und das war alles.
* Der Modulkopf von `ema_eesm` führte „keine Dämpferwicklung" unter dem, was
  das Modell nicht kennt. Ein Dämpferkäfig kam sonst nirgends vor.
* Schleifring und Kommutator wurden zwar gerechnet und gezeichnet, aber nur als
  Nebenwirkung: `ema_freecad` rief `ema_schleifring` direkt, `ema_eesm` hatte
  gar keine eigene Funktion dafür, und der Kommutator existierte nur als
  **Grenze** (`ema_gsm.kommutierung`), nie als Bauteil. In keiner Stückliste,
  keinem Steckbrief, keinem Paarvergleich.

**Messung.**

1. **Die Polbefestigung ist keine Formalie.** Am frischen Payload (6 Pole,
   Läufer Ø 188,6, L = 80 mm) wiegt ein Pol samt Erregerspule **1,49 kg**, sein
   Schwerpunkt liegt bei r = 71,8 mm. Bei 12.000 1/min zieht er mit
   **169 kN**; über den Halsquerschnitt (0,70 × Kernbreite × Paketlänge) und
   einen Kerbfaktor von 1,8 sind das 90 MPa gegen 340 MPa Fließgrenze
   (SF 2,62) — es hält. Mit `polBefestigung=bolzen` und der Vorgabe 2 × M10
   dagegen **1457 MPa gegen 640 MPa** (Klasse 8.8): SF 0,44, es hält nicht, und
   nötig wären 17 × M10. Die Bauart entscheidet also, und zwar um mehr als eine
   Größenordnung.
2. **`n_zulaessig` ist drehzahlunabhängig, und das ist die Probe.** σ ~ n², also
   ist `n_zul = n·sqrt(SF/SF_ziel)` unabhängig von dem n, mit dem gerechnet
   wurde (gemessen 17052 1/min bei 3000, 6000 und 12000 1/min). Käme dort etwas
   anderes heraus, wäre eine der beiden Formeln falsch — der Test prüft genau
   das statt einer festgenagelten Zahl.
3. **Die Kommutatorlänge war eine ZEICHENregel.** `L_KOMM_ANTEIL · axialLen`
   (Vorgabe 24 mm bei L = 80). Gemessen braucht ein Ankerstrom von 800 A bei
   10 A/cm² Bürstenstromdichte **80 cm²** Kontaktfläche; auf 6 Bürstenarmen à
   8,9 mm Breite sind das 149,6 mm Bürstenlänge. Der gezeichnete Kommutator war
   damit um den **Faktor 6 zu kurz**, ohne dass irgendetwas widersprochen hätte.
   Die Bürstenfläche bemisst den Kommutator, nicht ein Anteil der Paketlänge.
4. **Die Zeichenmarke der Leinwand sah den Dämpfer nicht.**
   `_laeuferMarkeBauen` führte 18 Felder, darunter keines der neuen und auch
   nicht `erregerSpuleForm`, `bZielT`, `poleArcFrac` oder `slotDepth`. Wer den
   Dämpferkäfig einschaltete, bekam die alte Zeichnung — und die sah richtig
   aus. Eine Marke, die eine Änderung nicht bemerkt, ist schlimmer als keine.

**Fundstelle.** `ema_schenkelpol.py` (neu), `ema_eesm.schleifringe`,
`ema_gsm.kommutator`, `ema_pipeline._gate_laeufer`, `cae_cli.cmd_rotor_check`,
`ema_paarvergleich` (Achsen `polbefestigung`, `daempferkaefig`), `ema.html`
`_laeuferMarkeBauen`.

**Stand: behoben.**

- `ema_schenkelpol.befestigung` rechnet die Fliehkraft des ganzen Pols (Schuh +
  Kern + Spule, aus `ema_eesm_cad.koerper` — derselben Funktion, aus der
  gezeichnet wird) gegen beide Bauarten und nennt die bindende. Das Nein trägt
  den Weg mit (nötige Halsbreite bzw. Schraubenzahl, zulässige Drehzahl).
- `ema_schenkelpol.daempferkaefig` bemisst die Stäbe nach einer **benannten
  Auslegungsregel** (0,25 × Ständerkupfer je Pol; Stabteilung 0,8 ×
  Ständernutteilung, Say / IEEE Std 115) und weist sie als Regel aus. Der
  Görges-Sattel wird geprüft: läuft die Stabteilung in die Nähe der
  Nutteilung, steht es da. Was der Dämpfer **nützt**, geht in keine Kennzahl
  ein — dafür fehlt der zeitabhängige Lauf —, und genau das steht in `wirkung`
  und als ⓘ unter der Paarvergleichsoption, damit „2:0 für ohne Dämpfer" nicht
  als Urteil über den Dämpfer gelesen wird.
- Die Kommutatorlänge folgt jetzt der Bürstenfläche (Boden bleibt die alte
  Zeichenregel); wird er länger als das Blechpaket, ist das ein **Befund** und
  keine Ablehnung — bei Gleichstrommaschinen üblich, aber es verlängert die
  Maschine. `zeichenmasse` liest dieselbe Funktion, sonst säße die gerechnete
  Bürste auf einem anderen Kommutator als der gezeichnete.
- `rotor-check` führt jetzt auch `_gate_laeufer` — dasselbe Tor der Pipeline,
  keine zweite Fassung. Geurteilt wird an „ABGELEHNT" und **nicht** am
  Warnzeichen: ein ⚠ kann ein Befund sein, der nichts verbietet.
- Der Dämpferkäfig wird gezeichnet (Leinwand, Querschnitt, CAD als
  `Damper_Cage` samt Bohrungen im Läufer) — aber **nur, wenn er auch passt**.
  Stäbe zu zeigen, die das Tor gerade abgewiesen hat, wäre eine Zeichnung, die
  der Rechnung widerspricht.

**Was bewusst offen bleibt.** Der Dämpfer ist im Feldmodell Luft und sonst
nichts: asynchroner Anlauf und Pendeldämpfung brauchen einen zeitabhängigen
Lauf. Die Flankenpressung der Schwalbenschwanzführung ist nicht gerechnet (der
Flankenwinkel ist kein Parameter dieses Werkzeugs), ebenso Dauerfestigkeit,
Presssitz und die Biegung des Pols aus einseitigem Magnetzug; das steht als
`ungeprueft` im Ergebnis. Wendepole und Kompensationswicklung der
Gleichstrommaschine bleiben wie bisher draußen.

---

## 2026-09-19 — Die Leinwand zeigte vier verschiedene Maschinen falsch

**Beobachtung** (gemeldet): „die geometrische Darstellung ist im html canvas
falsch. in der Asynchronmaschine werden keine Stäbe sondern Magnete angezeigt.
in der Reluktanzmaschine hast du einfach die Magnete entfernt, und in der
fremderregten Maschine kollidieren Rotor und Stator. die Magnetfelder in der
fremderregten Gleichstrommaschine sind auch falsch."

Alle vier Punkte sind im Browser nachgestellt worden (Chromium 153 headless über
das DevTools-Protokoll, `http://localhost:5000/#geo`, Bildschirmaufnahme der
`#simCanvas`-Fläche je Maschinenart). Die Vorschau war vorher **nie in einem
Browser** geprüft worden — nur über `node` mit gestelltem Kontext und über ein
aus dem JS-Raster gerendertes PNG. Genau die vier Fehler liegen zwischen diesen
beiden Prüfungen.

**Messung.** Startgeometrie der Seite (`ema.html` `GEOM`): Rotor Ø 170, Bohrung
Ø 171,6, Stator Ø 295, Welle Ø 80, p = 2, 36 Nuten, L = 225 mm.

1. **ASM: Magnete statt Stäbe.** `ema_asm.kaefig` meldet für diese Geometrie
   `bemessung = "nicht auslegbar"` (Magnetisierung auf 0,80 T braucht 963 A,
   die Umrichtergrenze liegt bei 800 A). `ema_laeuferbild._asm` gab daraufhin
   eine **leere Teileliste** heraus — und `drawRotor` las genau daran ab, ob
   Magnete zu zeichnen sind (`const legs = _lt ? [] : magnetLegs(GEOM)`). Eine
   leere Liste heißt aber „nichts zu zeichnen“, niemals „zeichne Magnete“, und
   leer war sie ausgerechnet in den interessanten Fällen: nicht auslegbarer
   Käfig, Abruf noch unterwegs, Serverfehler. Im Bild stand die V-Anordnung
   einer PSM auf einem Asynchronläufer.
2. **EESM: Rotor und Stator kollidieren.** Gemessen an den Zeichenteilen: die
   Erregerspule reichte mit ihrer **Ecke** bis r = 88,63 mm, der Polkern bis
   85,80 mm — bei einem Läuferhalbmesser von 85,00 mm und einer Statorbohrung
   ab 85,80 mm. Im gerenderten Bild (3,36 px/mm) liegt die Polfarbe bis
   r = 86,5 mm, also 0,7 mm im Ständer. Ursache ist eine Rechenregel, die man
   nicht sieht: Kern und Spule sind **Rechtecke**, der Läufer ist ein **Kreis**
   — ein Rechteck der halben Breite `y` mit der Oberkante bei `r` hat seine
   Ecken bei `sqrt(r² + y²)`. Geprüft wurde die Oberkante, gezeichnet wurden
   die Ecken. Derselbe Fehler steckte in `render_cross_section` und in
   `ema_freecad._pol_spule`, weil alle drei dieselbe Zahl (`r_kern_aussen_mm`)
   lasen.
3. **GSM: ein Drehfeld auf einer Gleichstrommaschine.** Der Ständer der
   Vorschau ist eine Drehstromwicklung in Nuten (`rasterizeGeometry`,
   Nutschleife mit `PHYS.id/iq` über `feldWinkel`). Für die GSM wurden die
   Schenkelpole zwar GEZEICHNET (`staender`-Teile seit dem 18.09.), aber
   **nicht gerastert** — `LAEUFER.rastere` bekam nur die Läuferteile. Das
   Feldbild zeigte also ein rotierendes Dreiphasenfeld auf einem Ständer, der
   keines hat, und der Wickelraum zwischen den Polen war magnetisch Eisen.
4. **SynRM: „die Magnete einfach entfernt“.** Hier war die Zeichnung richtig
   (8 leere Taschen, Ziffer für Ziffer dieselbe Quelle wie das
   Querschnittsbild), der **Griff** fehlte: `_updateArtVis` blendete die
   Magnet-Topologie für jede Art ohne Magnete aus — auch für den
   Reluktanzläufer, bei dem diese Anordnung die Lage der Flussbarrieren ist und
   damit das Einzige, was die Maschine ausmacht. Übrig blieb ein IPM ohne
   Magnete, ohne jede Möglichkeit, daran zu drehen.

**Fundstelle.** `ema_laeuferbild._asm`/`_eesm`/`_gsm`/`teile`,
`ema_eesm_cad.koerper`, `ema.html` `drawRotor`/`rasterizeGeometry`/
`_updateArtVis`, `ema_pipeline.render_cross_section` (EESM-Zweig),
`ema_freecad._pol_spule`, `ema_laeufer.js` `rastere`.

**Stand: behoben.**

- Die Magnete hängen an der **Bauart** (`hat_magnete` aus `ema_maschinenart`,
  über `/laeuferbild`), nicht mehr daran, ob Teile ankamen.
- Ein nicht bemessbarer Käfig wird **gezeichnet** — `ema_asm.kaefig` gibt die
  Geometrie ausdrücklich auch dann heraus („der Zeichner und das Netz brauchen
  etwas“) — und der Hinweis sagt, dass es der Fertigungsboden ist. Das harte
  Nein bleibt beim Vernetzen (`ema_em2d_harm`) und beim CAD.
- `ema_eesm_cad` rechnet den zulässigen Spulenradius aus
  (`_spule_einpassen`, `RAND_LUFT_MM = 1,0`): Dicke und Höhe der Spule werden
  **gekoppelt** gelöst, so dass `d·h` den Wickelraum trägt UND die Ecke auf dem
  Läuferrand liegt. Neu heraus kommen `r_spule_aussen_mm` und
  `b_kern_spulenende_mm`, die alle drei Zeichner lesen. Gemessen an der
  gemeldeten Geometrie: Ecke 88,63 → **84,00 mm** bei r_Läufer 85,00.
  Zusätzlich eine vierte Schranke `rotorrand` für den Kern und, als letzter
  Riegel, `ema_laeuferbild._im_kreis` über **jedes** Teil jeder Bauart —
  56 Fälle (4 Arten × 7 Polzahlen × 2 Spulenformen) ohne Überstand.
- Die GSM meldet `staenderfeld: False`; die Seite lässt die Drehstromnuten dann
  weg, rastert die Ständerteile mit (Luft zwischen den Polen) und prägt die
  **Erregerspulen als Gleichstrom** ein (`durchflutung_A` je Spulenseite, Wert
  aus `ema_eesm.erregung`). Dasselbe bei der EESM. Das ist keine Erweiterung des
  Modells, sondern sein eigentlicher Fall: eine eingeprägte Gleichdurchflutung
  kann ein magnetostatischer Löser exakt. Im Bild steht danach ein stehendes
  Vierpolfeld, das aus jedem Ständerpol austritt und über den Nachbarpol
  zurückkehrt.
- Beim Reluktanzläufer bleibt die Anordnung sichtbar und heißt dort
  „Flussbarrieren (Anordnung)“; der Hinweis nennt `pmasynrm`/`vv` für einen
  mehrlagigen Läufer (gemessen 6 Barrieren je Pol in 3 Lagen gegen 2 in 1).

**Was bewusst offen bleibt.** Unter dem Polschuh-Überstand, neben der Spule,
zeichnet die Leinwand weiterhin Läufereisen statt Luft — Zeichnung und Raster
sind dort einig, also widerspricht sich das Bild nicht; richtig wäre trotzdem
Luft. Das braucht eine Eisen-Rolle im Rasterer (`rastere` trägt heute nur
Unmagnetisches ein) und ist deshalb ein eigener Schritt. Ebenso: die Feldspule
der GSM ist ein Rechteck bis an den Jochinnenradius, ihre Ecken liegen damit im
Jocheisen (gemessen 141,7 mm gegen einen Jochinnenradius von 124,6 mm bei
Stator-r 147,5) — innerhalb der Maschine und innerhalb ihres eigenen
Polfensters, also keine Kollision, aber eine Vereinfachung.

---

## 2026-09-18 — Die EESM-Schulenspulen liegen im eigenen Eisen

**Beobachtung.** Die CAD-Vorschau der fremderregten Synchronmaschine (Projekt
`20260918_203052_cad_vorschau`) zeigt Erregerspulen, die von den Polen des
eigenen Rotors durchschnitten werden, und einen Modellbaum, in dem sich das
Rotor-Eisen, die Erregerspulen, die Schleifringe und die Bürsten als vier
getrennte Objekte neben dem Rotor stehen. Die Spulen überdecken nicht die
gesamte Polteilung; zwischen zwei benachbten Spulen liegt ein offener Spalt.

**Messung** (FreeCAD-1.1.1-`FreeCADCmd` über `motor.FCStd`, Pair-Kollision über
`Shape.common`):

- 24 Paare `Rotor` × `Field_Coils_*` mit gemeinsamem Volumen, je
  **533,3 mm³**. Summe ≈ 12,8 cm³ Kupfer, die in 205 cm³ Rotor-Eisen liegen
  — die Spulen sind etwa zu 9 % im Eisen begraben.
- Ursache: `ema_freecad.py:_pol_spule` baut die Spule radial bis zu
  `r_kern_aussen`; `POL_UEBERLAPP_MM = 0.5` zwingt den Polschuh
  (`_pol_koerper`) auf den Band `r_kern_aussen − 0.5 … r_kern_aussen`
  radial zu überdecken, damit der Rotor als EINES Solid fused bleibt.
  Die Spule fällt exakt in dieses Überdeckungsband.
- `ema_eesm_cad.koerper` rechnet `d_spule = a_wick / (2·h_kern)` — die Spule
  hat also die Breite des Kupferquerschnitts, nicht die des freien
  Polraums. Bei `p=8, Teilung 19,91 mm`: belegt
  `b_kern 9,744 + 2·3,983 = 17,71 mm`, frei 2,20 mm (1,10 mm je Seite).
- **Nicht** betroffen: `Rotor` selbst ist in der FCStd genau 1 Solid
  (fuse erfolgreich, `POL_UEBERLAPP_MM` wirkt); die Trennung von Kupfer
  und Eisen ist als Materialtrennung korrekt, gehört aber visuell in einen
  Rotor-Gruppe, nicht neben ihn.

**Fundstelle.** `ema_freecad.py:550–620` (`POL_UEBERLAPP_MM`, `_pol_koerper`,
`_pol_spule`), `ema_eesm_cad.py:67–130` (`koerper`, `d_spule`, `SPULENLUFT_MM = 2.0`).

**Status.** **Teil 1 geschlossen, dann neu bewertet** (21. September, gleiche Sitzung).

*Treffer 1 — behoben.* Der boolesche Weg (`.cut(Rotor)`) wurde verworfen: OCC erzeugt an beruehrenden/kongruenten Flaechen defekte Festkoerper (gemessen: danach enthielt eine Spule einen Punkt in der Nachbar-Spule). Statt dessen geometrisch in `_pol_spule`: die Spule endet jetzt 0,55 mm innerhalb des Kernradius' und haelt je 0,05 mm zu Joch, Kernseite und Poleschuh. Die urspruengliche Meldung (Spule in der eigenen Schuhbahn, 533,3 mm³) ist damit konstruktiv weg; die Spule liegt voll in der Polzwischenlucke.

*Neue, schärfere Messung.* Die verbliebenen Kollisionen sind **keine** Boolesch-Artefakte — sie verkleinern monoton mit jeder Verkleinerung der Spule (Rotor×Spule 533,3 → 403,9 → 388,3 → 376,2 mm³) und die Analytikgeometrie bestaetigt sie: **die 16 Spulenquerschnitte (je Pol zwei, ~248 mm²) sind zu groß für die 45°-Polteilung dieser Auslegung.** Schon auf der äusseren Polebene (r=25,35) beträgt die Teilung 2·r·sin(11,25°) = 19,31 mm, waehrend Kern + 2 Spulenquerschnitte + 2,0 mm Luft 19,71 mm fordern; bei mittlerem Radius ist der Lueckenquerschnitt nur ~28 mm² gegen ~248 mm² Spule. Kein radialer Versatz, keine Verkleinerung und kein Boolescher kann die rechteckigen Querschnitte in die Luecke bringen — die Auslegung ist ueberschrieben (Spulenquerschnitt gegen Polteilung). Die Ueberlappung benachbarter Spulen (2546,1 mm³) ist derselbe Befund in der Nachbarluücke.

*Dazukommender Werkzeugbefund.* Die `koerper.passt`-Pruefung (`b_kern + 2·d_spule + 2,0 < Teilung`, `ema_eesm_cad.koerper`) ist eine Linienprüfung bei einem Radius; sie sagt nichts ueber die Eckpunkte der Spule in der gekruemmten Lücke. Die Auslegung hat sie getragen, das CAD nicht — der Mangel ist der der Pruefung, nicht des CAD.

*Entscheidung liegt beim Auslegenden* (CAD-Ebene, EM-Modell bleibt ueberall identisch — die Spulengeometrie fliesst weder in das Feld noch in Massen ein):

1. Spulen als Keile in die Lücke zeichnen — die wahrere Form (ein Spulenquerschnitt pro Lücke), aber sichtbar duedner als das EM-`a_wick`; Vorschau-Ehrlichkeit gegen EM-Bild.
2. Rechteckig beibehalten und die Ueberlappung als Vorschauernaherung akzeptieren — dann steht hier, dass der CAD-Wert ein Bild, kein Bauplan ist.
3. Auslegung neu optimieren (Radius, Polzahl oder Kupferquerschnitt), bis SpULEN UND POLE passen — das verändert `erregung` und damit Kennzahlen; das ist ein neuer Auftrag, keine CAD-Fix.

---

## 2026-09-19 — Die Erregerspule war keine Spule, und der Pol passte nicht ans Joch

**Beobachtung.** Gemeldet als „die Spulen müssen komplett abgedeckt sein … im CAD
muss die Spule geschlossen sein, das sind sie nicht … es sieht so aus, als würde
der Rotor aus unterschiedlichen Bodies bestehen".

**Messung, erster Fall: die Spule war keine.** `_pol_spule` baute **zwei
getrennte Quader** links und rechts des Kerns. Das sind zwei Leiterstäbe. Eine
Spule ist eine geschlossene Schleife um den Kern — die beiden Stücke an den
**Stirnseiten** (z = ±L/2, die Wickelköpfe) fehlten ganz. Gebaut wird jetzt
Außenkörper minus Innenkörper; nachgemessen in FreeCAD: **10 Flächen, eine
Schale, Füllgrad 0,17** — ein Rahmen mit Loch, und **ein** Festkörper je Pol
statt zweier loser Blöcke.

**Damit erledigt sich auch der Eindruck „verschiedene Bodies":** `Rotor` war
immer schon **ein** gültiger Solid (nachgemessen: `Solids=1, gueltig=True`) —
die losen Körper waren die Spulen selbst.

**Messung, zweiter Fall: die Deckung war Zufall.** Der Polschuh hat eine
mechanische Aufgabe — er hält die Spule gegen die Fliehkraft („salient pole tips
overhang the pole body to secure the field coil in place against the action of
centrifugal force", US3089049A). Die Kernbreite kam aber aus einem festen
Verhältnis (`0,72 · b_schuh`), und ob darunter noch Platz für die Spule blieb,
ergab sich zufällig.

**Messung, dritter Fall — der schwerste, und er fiel erst durch die neue
Prüfung auf:** geprüft wurde die Polteilung nur am **Kernradius**, wo reichlich
Platz ist. Die Polteilung ist aber am **Jochradius** am kleinsten, und der Kern
ist über die ganze Höhe gleich breit. Gemessen am frischen Payload:

| Pole | τ am Joch | Kern + Spule | frei |
|---|---:|---:|---:|
| 4 (p=2) | 86,6 mm | 73,1 mm | +13,6 |
| 6 (p=3) | 49,0 mm | 48,9 mm | **+0,1** |
| 8 (p=4) | 33,4 mm | 37,3 mm | **−3,9** |

Ab acht Polen **durchdringen sich die Spulen benachbarter Pole am Joch** — und
gezeichnet wurde es trotzdem.

**Status.** Behoben. Der Kern gehorcht jetzt **drei** Schranken, und es gilt die
engste: Deckung (Schuh über Spule plus `SCHUH_UEBERSTAND_MM`), Platz am Joch,
und die alte obere Schranke. Welche bindet, steht als `bindend` im Ergebnis —
gemessen bindet bis p=2 der Kernanteil, ab p=3 das Joch. Reicht es nicht, ist
das ein begründetes Nein mit Abhilfe statt einer Zeichnung.

**Und die kegelige Wicklung als Bauform** (`geom.erregerSpuleForm`): der Pol ist
an der Jochseite breiter, die Wicklung folgt seiner Neigung („the base
(rotor-side) … is wider than the top (stator-side) … the field windings will
follow the taper", WO2006026200A1). `rechteck` bleibt Vorgabe und lässt jede
bisherige Zeichnung Ziffer für Ziffer stehen. Gemessen bringt der Kegel +3,0 %
Läufereisen (1.457.113 gegen 1.414.307 mm³) bei gleicher Deckung.

**Fundstelle.** `ema_freecad._pol_spule` / `_pol_koerper`;
`ema_eesm_cad.koerper`; `ema_pipeline.render_cross_section` (EESM-Zweig);
`ema_laeuferbild._eesm`.

**Ein eigener Fehlgriff, zum zweiten Mal in derselben Sitzung:** ich habe
`_pol_spule` einen `"""`-Docstring gegeben. Dieser Block wird als **Text** in
das FreeCAD-Skript geschrieben, und das dreifache Anführungszeichen beendet
dort die umschließende f-Zeichenkette. Steht jetzt als Warnung über der
Funktion. Ebenso zum zweiten Mal: ein gescheitertes `assert` **nach** einem
gelungenen `replace` verwirft die ganze Datei, weil erst am Ende geschrieben
wird — die Zeichenverzweigung fehlte danach stillschweigend, und erst der Test
(9 statt 21 Füllungen) hat es gezeigt.

---

## 2026-09-19 — Die Blechsorte erreichte Elmer nie, und der SynRM-Läufer war leer

**Beobachtung.** Gemeldet als „die Materialien sollen auch durchgereicht werden,
also in CalculiX und auch Elmer" — und als Schlussprobe „probiere alle Modelle
durch, mach von ihnen ein Bild und prüfe es auf Schlüssigkeit".

**Messung, Werkstoffe.** CalculiX bekommt das Blech (Dichte, E, ν, Fließgrenze
über `_mat_fc` bzw. `ema_deck`). **Elmer nicht:** alle drei Stufen rechneten mit
einer fest verdrahteten Permeabilität, und `LAMINATES` kam in den harmonischen
Modulen mit **null** Treffern überhaupt nicht vor. Wer M250-35A gegen M800-65A
stellte, bekam dasselbe Feld. Dazu kam, dass die Tabelle gar kein `mu_r` führte.

Zwei verschiedene feste Werte, beide Betriebspunkte: `ema_em3d.MU_R_IRON = 500`
(magnetostatisch, entspricht rund 2500 A/m) und `ema_em2d_harm.MU_R_EISEN =
5000` (harmonisch, rund 160 A/m; von der 3-D-Stufe mitbenutzt).

Aus der Lieferliste (thyssenkrupp powercore, DIN EN 10106) folgt µr = J/(µ₀·H)
bei 2500 A/m:

| Sorte | J@2500 | µr | Faktor |
|---|---:|---:|---:|
| M250-35A | 1,49 T | 474 | 1,000 |
| M270-35A | 1,49 T | 474 | 1,000 |
| M400-50A | 1,53 T | 487 | 1,027 |
| M800-65A | 1,60 T | 509 | 1,074 |

**Der Befund darin ist die Richtung:** die GROBEN Sorten haben die HÖHERE
Polarisation (mehr Eisen, weniger Silizium). Niedriger Ummagnetisierungsverlust
wird mit weniger Permeabilität bezahlt — und der Unterschied ist mit 7 % klein.
Wer vom Blechwechsel ein deutlich anderes Feld erwartet, erwartet das Falsche.
Nebenbei: die verdrahtete 500 liegt genau in diesem Band und war keine schlechte
Zahl, nur eine blinde.

**Was NICHT ableitbar ist, wird auch nicht behauptet:** die 5000 der harmonischen
Stufen entspricht rund 160 A/m, und das Datenblatt misst erst ab 2500 A/m. Sie
durch 474 zu ersetzen wäre kein besserer Wert, sondern ein anderer
Betriebspunkt unter altem Namen — dazu hängt an diesen Zahlen die Validierung
der ASM-Feldstufen (0,3 % / 0,14 %). Durchgereicht wird deshalb der
**Sortenfaktor** (`mu_r_faktor`): jeder Löser behält seinen Betriebspunkt und
multipliziert ihn. Die Vorgabesorte gibt exakt 1,000, also bleibt jede
gerechnete Auslegung Ziffer für Ziffer dieselbe — und die Blechwahl wirkt
trotzdem (M800-65A: 536,9 statt 500 bzw. 5369 statt 5000).

**Messung, Bilder.** Alle sechs Bauarten nebeneinander gerendert. Fünf
schlüssig; der **SynRM-Läufer war eine leere Scheibe** — 275 Formen gegen 311
bei der PSM, genau die fehlenden Taschen. `render_cross_section` hatte Zweige
für ASM, EESM und GSM, aber keinen für SynRM: `hat_magnete` ist False, also
zeichnete die Magnetschleife nichts. Ausgerechnet die Bauart, deren ganzes
Moment aus der Läufergeometrie kommt, zeigte gar keine Geometrie.

**Ein eigener Irrtum, gemessen widerlegt:** am kleinen Bild sah es so aus, als
ragten die Ständerpole der GSM über den Ständeraußendurchmesser hinaus. Über
alle gezeichneten Formen nachgemessen ist der größte Radius bei JEDER Bauart
exakt 140,0 mm = D_a/2. Nichts ragt hinaus; der Eindruck kam von der Kachelgröße.

**Fundstelle.** `ema_pipeline.LAMINATES` / neu `mu_r_faktor`;
`ema_em3d.write_sif`, `ema_em2d_harm.schreibe_sif`, `ema_em3d_harm.schreibe_sif`;
`ema_pipeline.render_cross_section` (fehlender SynRM-Zweig).

**Status.** Behoben. `LAMINATES` trägt `mu_r` und die drei Polarisationspunkte
mit Herkunftsvermerk; die beiden Vollmaterialien sind ausdrücklich `"annahme"`.
Die Dichte des M250-35A ist nach Datenblatt von 7650 auf 7600 kg/m³ berichtigt.
Der SynRM-Querschnitt zeichnet dieselben leeren Taschen wie die Leinwand, aus
derselben Quelle (`magnet_legs`). `test_laeuferbild.py` bekommt die Regel, die
den Fall gefunden hätte: **keine Bauart darf einen Läufer ohne Formen zeichnen**
(gemessen im Läuferring, Welle und Ständer zählen nicht).

---

## 2026-09-19 — Jede Wicklung rechnete bei 20 °C, und der Kaefig aus Draht

**Beobachtung.** Gemeldet als „die Materialangaben müssen angepasst werden,
allgemein auch für die ASM". Nachgesehen — und es waren zwei Dinge, beide
tool-weit.

**Messung, erster Fall: die Temperatur fehlte ganz.** `HAIRPIN_MATS` führte
`rho_el`, `density`, `E`, `nu` — und **keinen Temperaturbeiwert**. Damit rechnete
JEDER Leiterwiderstand des Werkzeugs bei 20 °C: Ständerkupfer
(`ema_thermal:174`, `:727`), Strangwiderstand (`ema_wicklung:386`), Käfigstab und
Läuferwicklung (`ema_asm:836`, `:606`), Erregerwicklung (`ema_eesm:224`),
Ankerwicklung (`ema_gsm:251`) — **und die Leitfaehigkeit, mit der Elmer den
Käfig löst** (`ema_em2d_harm:838`, `ema_em3d_harm:759`). Ein Motor läuft nicht
bei 20 °C: nach IEC 60228 (Kupfer α₂₀ = 0,00393/K, Aluminium 0,00403/K) hat eine
Klasse-F-Wicklung bei 155 °C **53 % mehr Widerstand**.

**Messung, zweiter Fall: der Käfig war aus Draht.** `KAEFIG_VORGABE = "al_1350"`
— eine **Knetlegierung** mit 61 % IACS — und der Kommentar in derselben Zeile
sagte „Aludruckguss". Absicht und Wert waren also seit jeher verschieden. Ein
echter Druckgusslaeufer erreicht recherchiert **40–45 % IACS** (Lufteinschlüsse
und Oxide beim Druckgießen); der Käfigwiderstand lag damit um rund 40 % zu
niedrig — und mit ihm der Schlupf, der direkt daran hängt.

**Was sich dadurch bewegt** (frischer Payload, 120 Nm @ 5000 1/min, gemessen
über `paarvergleich --achsen maschinenart`, Verlustleistung in W):

| | vorher | nachher |
|---|---:|---:|
| PSM | 638,7 | 833,4 |
| ASM | 1380 | 1928 |
| SynRM | 1070 | 1459 |
| EESM | 850,8 | 1077 |
| GSM | 5448 | 6810 |

Am Auslegungspunkt einzeln nachgemessen: Kupferverlust 130,4 → 179,0 W
(+37,3 %, also genau `rho(115)/rho(20)`), Gesamtverlust 247,7 → 296,3 W,
Wicklungstemperatur 59,9 → 61,2 °C. **Jedes gespeicherte Projekt verschiebt
sich** in Verlust, Wirkungsgrad und Temperatur; die Kennwerte davor und danach
sind nicht vergleichbar.

**Fundstelle.** `ema_pipeline.HAIRPIN_MATS` / neu `rho_bei` +
`leitertemperatur`; die sieben Rechenstellen oben; `ema_asm.KAEFIG_VORGABE`.

**Status.** Behoben. `alpha_20` an jedem Werkstoff, `rho_bei(mat, T)` als die
EINE Umrechnung, neu `al_guss` (43 % IACS) und `cu_guss` (91 % IACS), Käfig
defaultet auf Guss. `_HAIR` im Schema ist jetzt aus der Tabelle **abgeleitet**
statt danebengeschrieben — ein neuer Werkstoff erscheint damit ohne Zutun in
CLI, Parametertabelle und Browser. Neu erreichbar: `geom.barMat` (war lesbar und
in keinem Schema, also für den Agenten nicht vorhanden) und `geom.tLeiterC`.
Der Paarvergleich bekommt die Achse **`kaefigwerkstoff`** — gemessen
Kupferdruckguss 1751 W gegen Aluminium 1928 W bei +1 kg und +14 €, Schlupf
1,01 statt 1,52 %; und die Ständerachse lässt den Guss weg, weil ein gegossener
Käfig kein Hairpin ist.

**Die Gegenprobe war das Wertvollste.** `test_werkstoffe.py` sucht nicht nur,
wo `rho_bei` steht, sondern nach **rohen 20-°C-Werten**, die noch als Widerstand
durchgehen — und fand damit die eine Stelle, die ich übersehen hatte
(`ema_asm:606`, die Läuferwicklung des Schleifringläufers).

**Offen und ausdrücklich benannt: die Temperatur ist eine ANNAHME, und sie
widerspricht der gerechneten.** `T_LEITER_AUSLEGUNG_C = 115 °C` ist der
Auslegungspunkt einer Klasse-F-Wicklung, **kein Normwert** — belegt ist nur der
Temperaturbeiwert. Am gemessenen Punkt gibt das LPTN daneben **61,2 °C** aus.
Richtig wäre eine Iteration (Verlust → Temperatur → Widerstand → Verlust); die
gibt es hier nicht. Wer es genauer will, setzt `tLeiterC` auf die gerechnete
Temperatur. Das steht hier, statt dass die beiden Zahlen unkommentiert
nebeneinander stehen.

---

## 2026-09-19 — `rotor-check` liess genau das Tor aus, an dem der Lauf scheitert

**Beobachtung.** Beim Abarbeiten der Abnahme aus §12 des Plans (`run cad --frisch
--set machineType=…`) wurde jede Bauart von Stufe 0 abgewiesen. Der Verdacht fiel
zuerst auf die neuen Laeufer — falsch: es war das allgemeine Fliehkrafttor, und es
weist die **PSM am selben Payload Ziffer fuer Ziffer genauso ab**.

**Messung.** `--frisch` (Rotor 188,6 / Welle 60 mm, `rpm_to` = 20.000) gibt an der
Bohrung 390,1 MPa Spitzenspannung gegen 340 MPa Fliessgrenze, **SF 0,87** — der
Laeufer fliesst. Fuer `pmsm`, `asm`, `eesm` identisch, weil das Tor die
Maschinenart gar nicht fragt (Ringspannung aus Radien, Dichte und Drehzahl).
Belegt als *nicht von dieser Arbeit verursacht*: `ema_rotorcheck.py` und
`cae_cli.py` sind seit `c1148e8` — dem Stand **vor** Stufe 1 — unveraendert.

**Der eigentliche Fund steht daneben.** `cae_cli.py rotor-check --frisch` meldete
fuer genau diesen Payload:

    Layout OK — keine Kollision, Stege ueber Grenze, Taschen im Ring.

mit **Exit 0**. Die Pipeline fuehrt vor jedem Geometriebau **zwei** harte Tore —
`_gate_rotor_layout` und `_gate_rotor_stress` —, das Verb fuehrte nur das erste
(plus `ema_grenzen`). Ein Verb, das es einem ersparen soll, vierzig Sekunden
FreeCAD zu starten, und dabei ausgerechnet das Tor auslaesst, an dem der Lauf
dann scheitert, kehrt seinen Zweck um: es sagt „geht" und der Lauf sagt „Rotor
fliesst sicher". `cae_orchestrator/CLAUDE.md` behauptete die Deckung sogar
ausdruecklich („Die gleiche Pruefung ist eigenstaendig erreichbar als
`cae_cli.py rotor-check`"), und zwar fuer **beide** Tore.

Mitgenommen wurde dabei auch `ema_rotorcheck.entlastung` — die gerechneten Wege
aus einem gerissenen Tor, jeder vor dem Vorschlagen gegen dasselbe Tor
nachgeprueft. Sie existieren seit dem 12.09.2026 und erreichten den Agenten auf
diesem Weg nie.

**Fundstelle.** `cae_cli.cmd_rotor_check`; `ema_pipeline._gate_rotor_stress`.

**Status.** Behoben. `rotor-check` ruft jetzt **das Tor der Pipeline selbst** —
keine zweite Fassung, also dieselbe Drehzahlregel (`target.n_max` vor `rpm_to`),
derselbe Werkstoff aus `LAMINATES`, derselbe Wortlaut und dieselben
Entlastungswege — und gibt Exit 1, wenn es reisst. Am frischen Payload nennt es
jetzt: Hoechstdrehzahl auf 16.350 min-1, oder ein Blech ab 507 MPa, oder Rotor-Ø
153,7 mm. Gegenprobe: bei 16.350 min-1 steht SF **1,30** und das Verb gibt Exit 0
— der Vorschlag traegt, was das Tor von sich behauptet.

**Offen und ausdruecklich NICHT geaendert:** der frische Payload bleibt, wie er
ist. Dass seine 20.000 min-1 an diesem Laeufer nicht gehen, ist eine Aussage
ueber die Auslegung und kein Fehler des Payloads; das Tor sagt sie jetzt an der
Stelle, an der man sie braucht, mit Zahl, Grund und Ausweg. Eine Vorgabe
stillschweigend zu senken hiesse, die Frage zu verstecken statt sie zu
beantworten.

---

## 2026-09-18 — Der Browser rechnete immer eine PSM

**Beobachtung.** `machineType` steht seit der Einfuehrung von
`ema_maschinenart` im Schema und ist ueber die Parameter-Tabelle und
`cae_cli --set` erreichbar. In `ema.html` kam der Schluessel **gar nicht vor**.

**Messung.** `grep -c machineType ema.html` -> **0**. `buildPayload` baut `geom`
aus `{...GEOM, …}`, und `GEOM` fuehrte den Schluessel nicht; die Pipeline liest
`geom.get("machineType", "pmsm")`. Der Browser hat also **jede** Auslegung als
permanenterregte Synchronmaschine gerechnet — auch nach Stufe 1 bis 3, die ASM,
EESM und GSM zeichenbar gemacht haben. Wer die neuen Bauarten benutzen wollte,
musste ueber die CLI oder die Parameter-Tabelle gehen; ein Knopf, den nur die
CLI hat, ist fuer den, der vor der Oberflaeche sitzt, nicht vorhanden — dasselbe
Argument, aus dem `studie` und `zielwert` Verben bekommen haben.

**Fundstelle.** `ema.html`, `buildPayload`/`applyPayload` und der Geometrie-Reiter;
`ema_text2ema.SCHEMA["machineType"]` (dessen `desc` ausserdem noch von vier Arten
sprach und die Feldstufen falsch beschrieb).

**Status.** Behoben (§10 des Plans). Abschnitt „Maschinenart" im Geometrie-Reiter
vor der Magnet-Topologie, Auswahl aus `/param_schema` geladen statt im HTML
abgeschrieben, `GEOM.machineType` als der eine Ort, `buildPayload` schickt sie
ausdruecklich mit, `applyPayload` und `T2E_APPLY` stellen sie wieder her, und bei
einer Art ohne Magnete entfaellt die Magnet-Topologie. `test_maschinenart.py`
nagelt alles sechs fest, samt der Gegenprobe, dass **keine** Art als fester
`<option>` im HTML steht.

---

## 2026-09-18 — Die GSM wog wie die PSM, und ihr Staender hatte Zaehne, die es nicht gibt

**Beobachtung.** Der Paarvergleich über die Achse `maschinenart` stellt seit
Stufe 3 fünf Bauarten nebeneinander. Beim Nachsehen der Zahlen — der Schritt, den
§9 des Plans ausdrücklich verlangt („zu prüfen ist nur, ob die Kennzahlvergleiche
tragen") — trugen zwei Spalten nicht.

**Messung, erster Fall.** Die GSM stand mit **Ziffer für Ziffer derselben Masse
und denselben Kosten wie die PSM** da (40,53 kg / 197 EUR), während ASM, SynRM
und EESM darunter lagen. Ursache: `ema_gsm.massen_und_kosten` übernahm die Basis
aus `ema_screen` — und die rechnet eine Drehfeldmaschine: Magnete im Läufer, einen
GENUTETEN Ständerring (Faktor 0,78) und Strangkupfer darin (0,30 × 0,55 des
Ringvolumens). Keines davon hat die GSM. Gesetzt wurde nur `magnet_kg = 0`;
`gesamt_kg` und `kosten` trugen die Magnete weiter. `erreger_cu_kg` stand
obendrein immer auf `None`, weil `ema_eesm.erregung` gar keinen Schlüssel
`m_cu_kg` führt und der Code ihn abfragte. Neu gerechnet aus den eigenen Teilen:
60,78 kg / 270 EUR gegen 48,78 kg / 166 EUR der PSM — und die Summe der Posten
ist die Gesamtmasse, im Test nachgerechnet.

**Messung, zweiter Fall.** In der Spalte `B_Zahn` stand für die GSM **8,885 T** —
exakt derselbe Wert wie für ASM und EESM. `ema_saettigung` rechnet die
Zahnflussdichte über die **Nutteilung**; weil sich die Teilung dabei herauskürzt,
hängt die Zahl nur an `B_gap` und `slotWidthRatio` und weiß von der Maschine
nichts. Der GSM-Ständer trägt Schenkelpole und hat überhaupt keine Nuten — das
war eine Formel auf eine Geometrie, die es nicht gibt. Dazu: der Hinweis am
Umrichter-Limit las „800 A **bei 1 Wdg/Nut**", die Normierung der
Drehfeldmaschinen; `ema_gsm.klemmenstrom` liest `i_max_A` und nicht `i_max_1t`,
dort ist der Zusatz schlicht falsch.

**Dritter Befund, derselbe Griff.** `ema_maschinenart.ohne_bedeutung` sagt seit
jeher, welche Kennzahl für welche Art nichts bedeutet — **`ema_paarvergleich` hat
sie nie gelesen.** Damit ist ausgerechnet die Tabelle, in der eine
bedeutungslose Zahl neben gerechneten steht und genauso aussieht, der eine Ort,
an dem die Registrierung nicht galt.

**Fundstelle.** `ema_gsm.massen_und_kosten`; `ema_paarvergleich`, Zusatzspalten-
Block (`ema_saettigung`) und die Umrichter-Warnung; `ema_maschinenart.ARTEN["gsm"]`.

**Status.** Behoben. Die Massen entstehen aus den eigenen Teilen (Ankereisen
abzüglich der Ankernuten, Ständerjoch + Schenkelpole ohne Nutfaktor, Anker- und
Erregerkupfer), neu `_STAENDERNUT_KENNZAHLEN` in der Registrierung, und der
Sättigungsblock fragt `gilt()` — die Spalte bleibt leer statt eine Zahl zu
erfinden. `test_gsm.py` Abschnitte 13 und 14 nageln beides fest, samt der
Gegenprobe, dass PSM und ASM die Sättigungsspalte behalten.

---

## 2026-09-18 — Der frische Payload ist kein Gleichstrom-Payload, und die Legende deckte den Titel zu

**Beobachtung.** Der erste End-zu-End-Lauf der neuen Gleichstrommaschine durch
`build_cad_preview` wurde vom Kommutierungstor abgewiesen — zu Recht, aber aus
einem Grund, der nichts mit der Auslegung zu tun hatte: `cae_cli.frischer_payload`
trägt `rpm_to = 20000`, die Vorgabe eines Traktions-PSM. Am Kommutator sind das
**128,4 m/s gegen 40 m/s Grenze** (Ausnutzung 321 %), dazu 43,3 V Lamellenspitze
gegen 35. Das Tor tut genau, was es soll; falsch ist die Erwartung, `--frisch`
liefere einen Startpunkt für *jede* Maschinenart. Bei 3000 1/min läuft derselbe
Payload durch (19,3 m/s, 48 % Ausnutzung, bindend `umfang`).

**Messung.** Derselbe Lauf bei 3000 1/min baut in FreeCAD: `Rotor` **ein** gültiger
Solid (1.903.685 mm³), 24 Ankerbündel, 48 Kommutatorlamellen, 4 Bürsten, `Stator`
ein Solid (Joch + vier einwärts gerichtete Pole verschmolzen), 4+4 Erregerspulen,
**keine** Magnete, keine Statornuten, keine Hairpins.

**Zweiter Befund aus demselben Bild.** Im erzeugten Querschnitt überdeckte die
Legende den Titel. Ursache ist nicht die Legende, sondern der **längere Titel**:
`render_cross_section` zeichnet ihn als `ax.text` in Datenkoordinaten mittig oben,
die Legende sitzt auf `loc='upper right'` derselben Achse — solange „PSM —
Querschnitt (XY)" 204 px breit war, ging das gut; „ASM — Asynchronmaschine
(Kaefiglaeufer) — Querschnitt (XY)" ist **338 px** breit und stößt an. Gemessen
(Figur 10x10, dpi 130): ASM überdeckt um 3 px, GSM im gespeicherten Bild sichtbar
um rund 20. Eine erste Messung meldete fälschlich „keine Überdeckung" — sie
verglich gegen `ax.title`, und der ist hier leer.

**Fundstelle.** `cae_cli.frischer_payload` (`rpm_to`); `ema_pipeline.render_cross_section`,
Legende am Ende der Funktion.

**Status.** Die Legende bekommt `bbox_to_anchor=(1.0, 0.94)` und sitzt damit unter
dem Titelband — für alle fünf Bauarten nachgemessen. Der Payload bleibt, wie er
ist: eine Vorgabe je Maschinenart wäre eine zweite Quelle neben dem Schema, und
das Tor sagt bereits mit Zahl und Grund, was nicht geht. Ein begründetes Nein ist
ein Ergebnis.

---

## 2026-09-18 — Die Lamellenspannung hängt nicht an der Leiterzahl

**Beobachtung.** Eine Prüfung in `test_gsm.py` sollte die Lamellenspannung über
**viele Leiter** zum Reißen bringen (12 Leiter/Nut, 48 Nuten, 3000 1/min) und kam
mit `befunde: []` zurück. Der erste Verdacht war ein Fehler im Tor.

**Messung.** Es ist Algebra, kein Fehler: mit `U_l = 2a·E/k`, `E ∝ z` und `k ∝ z`
kürzt sich die Leiterzahl heraus, übrig bleibt `U_l ≈ 2·r·B·α·L·ω`. Nachgemessen
ändern **288 statt 48 Lamellen** die mittlere Lamellenspannung nicht (1,62 V in
beiden Fällen), während die doppelte **Baulänge** sie verdoppelt (3,25 V) und die
Umfangsgeschwindigkeit dabei stehen lässt. Welche der drei Grenzen bindet, hängt
deshalb an der Bauform, und der Übergang ist scharf — bei 6000 1/min:

| Paket | U_l (Spitze) | v_komm | bindend | |
|---:|---:|---:|---|---|
| 100 mm | 6,49 V (12,99) | 38,5 m/s | `umfang` 0,96 | hält |
| 300 mm | 19,48 V (38,96) | 38,5 m/s | `lamelle_spitze` 1,11 | **reißt** |

**Fundstelle.** `ema_gsm.kommutierung`; `test_gsm.py` Abschnitt 5.

**Status.** Die Prüfung ist umgeschrieben: sie nagelt jetzt fest, dass die
Leiterzahl sich herauskürzt und die Baulänge es nicht tut, und treibt die
Lamellengrenze über ein **langes Paket** statt über die Leiterzahl. Für den, der
einen Kommutator entlasten will, ist das die eigentliche Auskunft — mehr Lamellen
helfen nicht.

---

## 2026-09-18 — Der Käfig war gezeichnet und unerreichbar, und der Läufer ohne Magnete bekam welche

**Beobachtung.** Auf die Bitte, eine Asynchronmaschine mit n Polen in CAD
darzustellen, war die erste Vermutung „das muss gebaut werden". Nachgesehen:
`ema_freecad.build_full_motor_script` zeichnet den Käfig **seit jeher** —
Läufernuten, Stäbe und **beide** Kurzschlussringe, gespeist aus
`ema_asm.kaefig`, derselben Funktion, aus der auch der analytische Widerstand
und das 2-D-Feldnetz kommen. Drei Dinge machten ihn unerreichbar bzw. falsch,
und jedes für sich sah harmlos aus.

**Messung.**

1. **Das Tor ließ den eigenen Erzeuger nicht durch.** `ARTEN["asm"].stufen`
   führte `("analytisch", "feld", "em3d")`; `_gate_maschinenart(data, state,
   "cad")` (`ema_pipeline.py:1887`) wies die ASM deshalb ab. Der Kommentar
   daneben sagte sogar, das sei „keine Lücke im Sinne von noch nicht gemacht,
   sondern eine ehrliche: `ema_freecad` zeichnet Magnete und Hairpins, keinen
   Druckguss-Käfig mit Kurzschlussringen" — und genau das stimmte nicht.

2. **`GEN_MAGNETS` fragte die Maschinenart nicht** (`ema_freecad.py:214`,
   `gen_magnets = bool(geom.get("genMagnets", True))`). Gemessen am erzeugten
   Skript hätte ein ASM-Läufer Magnettaschen **und** Magnete **und** einen Käfig
   bekommen — einen Läufer, den es nicht gibt. Der Taschenschnitt hing dabei
   nicht einmal an `GEN_MAGNETS`, sondern lief unbedingt.

3. **Ein nicht auslegbarer Käfig wäre still gezeichnet worden.** `kaefig` fällt
   dann auf den 2-mm-Fertigungsboden zurück und meldet
   `bemessung: "nicht auslegbar"` — `ema_em2d_harm` weigert sich daraufhin zu
   vernetzen, der Zeichner fragte es nicht. Gemessen am Ventilatorfall (p = 1,
   24 Nuten): die Magnetisierung braucht 1686 A gegen eine Grenze von 800 A, es
   bleibt kein momentbildender Strom — und heraus käme eine breite, flache Nut,
   an der der 2-D-Lauf ein Carter von 3,2 statt 1,15 misst.

**Und dieselbe Blindheit steckte im Querschnittsbild.**
`ema_pipeline.render_cross_section` ist die EINE Zeichnung für CAD-Bild,
Bilddatensatz und Sättigungsbild — sie zeichnete Magnete aus `magnet_legs` ohne
jede Verzweigung. Jedes dieser Bilder hätte für eine ASM einen PM-Läufer
gezeigt.

**Fundstelle.** `ema_maschinenart.ARTEN["asm"].stufen`; `ema_freecad.py:214`
(`gen_magnets`), `ema_freecad.py` Block „2. ROTOR IRON" (Taschenschleife) und
der `CAGE`-Block; `ema_pipeline.render_cross_section`.

**Status: behoben** (18.09.2026), mit vier Stücken.

1. `stufen` führt `"cad"`. Das Tor lässt die ASM durch — Feld und 3-D weist es
   weiterhin ab, weil sie dort über `feld2d`/`feld3d` (Elmer, harmonisch) und
   nicht über die magnetostatische Kette dieser Pipeline gehen. **„Trägt die
   Stufe" und „geht DIESEN Weg" sind zwei Fragen**, und `server._art_optionen`
   hatte sie vermischt: der Hinweis auf den Feldweg stand im `else`-Zweig „nicht
   alle Stufen getragen" und wäre mit dem CAD genau für die eine Art
   verschwunden, die ihn braucht. Er hängt jetzt am Weg.
2. `gen_magnets &= ema_maschinenart.hole(...).hat_magnete`, und die
   Taschenschleife hängt an einem eigenen `HAT_MAGNETE` — wer die Magnete nur
   ausblendet (`genMagnets=False`, der stufenweise Aufbau), soll den Läufer
   weiterhin mit seinen Taschen sehen; eine Asynchronmaschine hat dagegen gar
   keine. Ebenso `_gate_rotor_layout`: ein Läufer ohne Magnettaschen bekommt
   statt der Taschenprüfung `_gate_laeufer` (Steg über der Nut, über
   `ema_asm.steg_check`). Ein grünes Urteil über etwas Nichtvorhandenes ist
   schlechter als keines.
3. Ein nicht auslegbarer Käfig wird **abgewiesen**, mit der Begründung aus
   `ema_asm.nicht_erreichbar_text` — ausdrücklich überstimmbar über
   `geom.kaefigFreigabe` (Muster `luftspaltFreigabe`), dann steht die
   Überschreitung als ⚠ im Protokoll.
4. `render_cross_section` verzweigt nach `art_code` und zeichnet die
   Läufernuten aus **denselben** Funktionen wie das CAD.

**Nachgemessen am echten Bau** (FreeCADCmd 1.1.1, `build_cad_preview` durch alle
Tore):

| | Körper |
|---|---|
| Käfigläufer (31 Nuten, Schrägung 1 Nutteilung) | Shaft · Rotor · **Cage_Bars (186 = 31 × 6 Segmente)** · Cage_Rings (2) · Stator · Coils_A/B/C — **keine Magnete** |
| Schleifringläufer (18 Nuten) | Shaft · Rotor · **Rotor_Winding (18)** · **Slip_Rings (3)** · **Brushes (3)** · Stator · Coils — **kein Käfig daneben** |
| Käfigläufer p = 1 (Ventilatorfall) | **abgewiesen**: „nicht auslegbar, also nicht zeichenbar … 1686 A gegen 800 A" |

**Nachtrag gleichen Tags: die EESM ebenso, und zwei Dinge dabei gemessen.**
`ema_eesm.polgeometrie`/`erregung` rechnen den Schenkelpol seit jeher —
Polschuhbreite, Wickelfenster, Jochhöhe, Kupferquerschnitt je Pol — nur
gezeichnet hatte ihn nie jemand. `ema_eesm_cad.koerper` leitet daraus die Teile
ab, `ARTEN["eesm"].stufen` führt `"cad"` (Feld weiterhin **nicht**: die 2-D-FDM
ist reell und magnetostatisch und kann eine Gleichstrom-Erregerwicklung so wenig
darstellen wie einen Käfig). Zwei Befunde beim Bauen:

* **Der Läufer kam als sieben getrennte Körper heraus.** Joch und Pole berühren
  einander nur an einer Fläche, und OCCs `fuse` macht daraus einen Verbund aus
  mehreren Solids statt eines. Gemessen: `Rotor Solids=7` bei 6 Polen — und die
  Struktur-FEM vernetzt genau diesen `Rotor`, hätte also einen zerfallenen
  Läufer gerechnet. `POL_UEBERLAPP_MM` = 0,5 ist deshalb kein Schönheitsmaß,
  sondern der Unterschied zwischen einem Bauteil und sieben (danach `Solids=1`,
  `gueltig=True`).
* **Die Stromdichte der Erregerwicklung war über `geom` nicht erreichbar.**
  `erregung` nahm `J_F_VORGABE_APMM2` als Modulvorgabe und einen Funktions-
  parameter, den kein Aufrufer setzte — in einer Parameterstudie oder einer
  Zielwertsuche war sie damit unsichtbar, obwohl sie die Wicklung bemisst.
  Jetzt `geom.fieldCurrentDensity`, dasselbe Muster wie `barCurrentDensity`
  (Käfig) und `rotorCurrentDensity` (Schleifringläufer).

Dazu neu: die **zweite Läuferbauform** (`rotorType="schleifring"` — Drehstrom-
wicklung mit Anlasswiderstand, `ema_asm.laeuferwicklung`/`anlasswiderstand`/
`schleifringe`) und die **Schrägung der Läufernuten** (`rotorSkewSlots`, in
Läufernutteilungen, gestuft gezeichnet wie `ema_em3d` es staffelt — ein um die
eigene Achse tordiertes Prisma ist nicht robust vernetzbar). Test:
`test_laeufer_cad.py` — es führt das **erzeugte Skript** mit einem
Stellvertreter-FreeCAD wirklich aus und zählt, was dabei entsteht, statt eine
Zuweisung zu prüfen.

---

## 2026-09-15 — Die Übersetzung 80 ist das Vierfache der eigenen Feldgrenze, und niemand hält sie auf

**Beobachtung.** Im selben Zyklusergebnis (`20260915_091253_Pescord`) steht
`vehicle.gear_ratio = 80` bei `r_wheel_m = 0,55`. Daraus kommen die
49.958 min⁻¹. Das Eingabefeld der Oberfläche sagt selbst etwas anderes:

    ema.html:3096  <input id="veh_gear" value="9.5" min="1" max="20" step="0.5">
    ema.html:3092  <input id="veh_rwheel" value="0.32" min="0.15" max="0.55">

`max="20"` markiert das Feld nur als `:invalid` — gelesen wird
`+document.getElementById('veh_gear').value` (`ema.html:11422`), und **der Server
prüft den `vehicle`-Block überhaupt nicht** (`server.py` kennt `vehicle` nur in
zwei Kommentaren). Die 80 läuft also ungebremst durch die ganze Kette. Der
Radhalbmesser 0,55 m liegt genau auf dem `max` desselben Formulars.

**Messung.** Die Antriebsstrangrechnung selbst ist richtig — mit dem
gespeicherten `vehicle` nachgerechnet kommen `rpm_max 49958`, `rpm_rms 22418`,
`T_max 153,1`, `T_rms 16,0` **ziffernidentisch** heraus. Falsch ist nicht die
Formel, sondern was hineingeht:

| | Wert | Grenze im selben `results.json` |
|---|---|---|
| Übersetzung | **80** | zulässig ≤ **27,2** (aus `max_safe_rpm_fem` 17.018) |
| Motordrehzahl | 49.958 min⁻¹ | 17.018 min⁻¹ |

Und die Übersetzung lässt sich nicht einfach zurücknehmen: bei i = 27,2 stiege
`T_max` auf **450 Nm** gegen ein Spitzenmoment der Maschine von 279,3 Nm — Faktor
1,61 zu wenig. Die Maschine passt an keinem Punkt zu diesem Fahrzeug.

**`ema_getriebe` lief hier nie — und der Browser hätte es ohnehin weggeworfen.**
`vehicle.getriebe` fehlt, also greift in `ema_drivecycle.compute_drivetrain:673`
der `else`-Zweig: die skalare Übersetzung **und** das feste `eta_drive = 0,95`,
genau die beiden Konstanten, gegen die `ema_getriebe` gebaut wurde.

Eine erste Fassung dieses Befundes schrieb, die Oberfläche habe keinen Weg zur
Getriebeauslegung. **Das war falsch** — den Reiter ⚙ Getriebe samt Häkchen
„Übernehmen" gibt es, und er schreibt `vehicle.getriebe` nach `meta.json`.
Nachgemessen ist der Mangel ein anderer und schlimmer: **`buildPayload` baut
`vehicle` ausschließlich aus seinen sieben Formularfeldern**
(`ema.html:11423-11431`), und `applyPayload` stellt den Schlüssel auch nicht
wieder her. Wer im ⚙-Reiter übernimmt und dann im Browser „⚙ Echte Berechnung"
drückt, verliert die ausgelegte Verzahnung also still und rechnet wieder mit
skalarer Übersetzung und festem η. Über `cae_cli.py run --from-project` bleibt
sie erhalten, weil dort der ganze Payload geerbt wird — der Fehler trifft genau
den Weg, auf dem die Auslegung bedient wird.

**Und das Feld war falsch beschriftet.** `veh_rwheel` trug das Etikett
**„Raddurchmesser"**, während `compute_drivetrain` mit `omega_w = v / r_wheel_m`
den **Halbmesser** meint. Wer den Durchmesser einträgt, bekommt die doppelte
Drehzahl — bei einem Vorgabewert von 0,32 m (Halbmesser eines 205/55R16) fällt
das niemandem auf, weil beide Lesarten eine plausible Zahl ergeben.

**Was das für die Bilanz heißt.** Die Traktionsenergie hängt nicht an der
Übersetzung — 8148 Wh am Rad und 31,2 kWh/100 km bleiben. Die Übersetzung
entscheidet allein über die **Aufteilung** in Drehzahl und Moment und damit über
die 327 Wh Verlustspalte und die 96,8 %.

**Nebenbefund am Zyklus selbst — und die Ursache lag noch eine Stufe tiefer.**
`T_max = 153,1 Nm` steht bei **t = 1800 s**, dem letzten Abtastwert. Die
naheliegende Erklärung war die zweimalige Glättung mit
`np.convolve(v, ones(3)/3, mode="same")`, die an den Rändern **nullgepolstert**
ist. Randfortsetzung allein brachte aber nur −12,1 → −8,1 m/s²; gemessen am
**ungeglätteten** Profil steht dort `[… 129,8 131,3 131,3 **0,0**]`. Alle drei
synthetischen Bauer legen `np.zeros(TOTAL_T + 1)` an und füllen die Phasen über
`[t_start, t_end)` — der **letzte Abtastwert wird nie beschrieben** und bleibt
0. Das sind −36 m/s² in einer Sekunde; die Glättung hat den Sprung nur verteilt
und dadurch unauffällig gemacht, nicht kleiner. `_build_stadtland` setzte
`v[-1] = 0.0` sogar ausdrücklich, ohne Rampe.

Davon unabhängig liegen **3,8 %** der 1801 Sekunden außerhalb des echten
WLTP-Beschleunigungsbandes (+1,67 / −1,50 m/s²); die Spitzen der Näherung
erreichen +3,0 m/s². Der Name sagt „approximiert" — die **Momentenspitze** einer
Auslegung sollte trotzdem nicht aus einem Randeffekt kommen.

**Fundstelle.** `ema.html:3092,3096` (Felder), `ema.html:11423-11431`
(`buildPayload` ohne `getriebe`), `ema_drivecycle.compute_drivetrain`
(Antriebsstrang), `_build_wltp3b`/`_build_vollast`/`_build_stadtland`/
`_build_anhaenger` (Profilabschluss), `cae_cli.py:2622` `_getriebe_uebernehmen`
(der einzige Weg, der `gear_ratio` aus einer Rechnung setzt).

**Status: behoben** (15.09.2026), in vier getrennten Stücken.

1. **Die Prüfung Übersetzung × Rad** sitzt dort, wo sie hingehört — an der
   Drehzahl, die daraus folgt (siehe den Befund zu `rpm_base` oben): 
   `cycle_energy(..., rpm_max_zul=max_safe_rpm)` → `speed_warning`, plus das
   Kriterium `zyklusdrehzahl` in `ema_sicherheit`. Der Wert 80 selbst wird
   **nicht** abgewiesen: `ema_getriebe` kann zweistufig planetar bis i = 100
   auslegen, falsch ist nicht die Zahl, sondern ihre Paarung mit dieser
   Maschine — und die sagt jetzt die Drehzahl.
2. **`ema_drivecycle.FAHRZEUG_GRENZEN`** ist die eine Quelle für die Grenzen des
   Fahrzeugblocks; `fahrzeug_pruefen` **benennt** Überschreitungen, klemmt sie
   aber nicht (geklemmt sähe der Wert für den Aufrufer wie ein angenommener aus)
   und weist sie nicht ab (abgewiesen wäre ein bestehendes Projekt unrechenbar).
   Die Felder in `ema.html` tragen dieselben Zahlen, und das Radfeld heißt jetzt
   **Radhalbmesser**.
3. **Die ausgelegte Verzahnung überlebt den Browser.** `_vehGetriebe` hält sie,
   `applyPayload` liest sie aus dem Payload, der ⚙-Reiter setzt sie nach einer
   erfolgreichen Übernahme, `buildPayload` hängt sie wieder an — und unter dem
   Übersetzungsfeld steht, ob gerade mit η(T, n) oder mit festem η gerechnet
   wird. Vorher war „übernommen" eine Aussage, die der nächste Knopfdruck
   zurücknahm, ohne es zu sagen.
4. **Der Profilabschluss ist eine Funktion** (`_profil_abschluss`) statt in
   jedem Bauer ein eigener — und in zweien gar keiner: letzter Abtastwert
   füllen, randfortgesetzt glätten, mit zulässiger Verzögerung **ausrollen**
   (ein Zyklus endet im Stand) und auf `BESCHLEUNIGUNG_BAND` klemmen. Die
   Reihenfolge ist nicht beliebig — glättet man nach dem Ausrollen und setzt
   danach `v[-1] = 0`, reißt genau der Sprung wieder auf (gemessen −2,14 m/s²).

**Gemessen am WLTP-3b-Profil**, alle vier Zyklen nun innerhalb ihres Bandes:

| | vorher | nachher | Sollwert |
|---|---:|---:|---:|
| Strecke | 23,25 km | **23,33 km** | 23,26 km |
| v_max | 129,5 km/h | **129,1 km/h** | 131,3 km/h |
| a | −8,06 … +3,00 m/s² | **−1,50 … +1,67** | −1,50 / +1,67 |
| `T_max` (gemeldete Auslegung) | 153,1 Nm bei t = 1800 s | **45,3 Nm** | — |

Die Rate­begrenzung trifft die Sollstrecke sogar besser als vorher (+0,3 %
statt −0,1 % bei einem Profil, dessen letzter Wert nicht definiert war).
**Das bewegt Altbestand:** `T_max`, `T_rms` und damit jede Kupferzahl eines
Zyklusergebnisses ändern sich. Test: `test_zyklen.py` B, C, D.

---

## 2026-09-15 — `rpm_base` im Zyklus ist die erste Zeile der Bilderliste, nicht die Eckdrehzahl

**Beobachtung.** Eine Energiebilanz (WLTP 3b, Projekt
`20260915_091253_Pescord`) weist **Cu 316 Wh gegen Fe 8,6 Wh** aus. Bei
`rpm_RMS = 22.418 min⁻¹` und `p = 3` sind das **1121 Hz** Grundfrequenz — dort
kann der Eisenverlust nicht 2,7 % des Kupferverlusts sein, erst recht nicht bei
**8,7 % Momentauslastung** (`T_RMS` 16,0 Nm gegen `T_Nenn` 183,9 Nm).

**Messung.** `ema_pipeline.py:2315` setzt

    rpm_base = float(sweep_rpms[0])

— das ist der **erste Eintrag der Drehzahlliste der Feldanimation** (hier
`[600, 2000, … 18500]`, also **600**), gewählt vom Menschen als Anfang des
Bilderlaufs. Dieselbe Zahl geht bei `ema_pipeline.py:2948` als `rpm_base` in
`ema_thermal.cycle_loss_series`, wo sie die Feldschwächung stellt:

    fw = clip((rpm − rpm_base)/rpm_base, 0, 1.5)

Über dem gemessenen Zyklus (aus `drivecycle.op_points`):

| | mit `rpm_base = 600` | ohne Feldschwächung |
|---|---|---|
| `fw` im Mittel | **1,419** (Anschlag 1,5) | 0 |
| `flux_fac²` im Mittel | **0,202** | 1,000 |
| Anteil `J_d²` an `J²` | **98,9 %** | 0 % |

Also: der Eisenverlust wird mit **0,20** multipliziert, und **98,9 % des
ausgewiesenen Kupferverlusts** sind ein Feldschwächstrom, den allein diese Zahl
erzeugt. Bereinigt stünden dort rund **3,5 Wh Kupfer gegen 43 Wh Eisen** — die
Rangfolge dreht sich um.

Die echte Eckdrehzahl dieser Maschine liegt bei `psi_pm = 0,0062 Wb` und p = 3
über **40.000 min⁻¹**; auf diesem Zyklus fände Feldschwächung praktisch **gar
nicht** statt.

**Fundstelle.** `ema_pipeline.py:2315` (Zuweisung), `ema_pipeline.py:2948`
(Übergabe), `ema_thermal.py:176-192` (Wirkung). `server._rpm_base_von` rechnet
die Eckdrehzahl bereits richtig aus `emf_1` und `v_dc` — sie steht nur an dieser
Stelle nicht zur Verfügung.

**Nebenbefund derselben Bilanz.** `ema_drivecycle.cycle_energy` prüfte die
Überlastung ausschließlich am **Moment** (`T_rms > T_rated`). Dieser Zyklus
läuft mit `rpm_max = 49.958 min⁻¹` gegen eine FEM-Grenze von **17.018 min⁻¹**
(`structural_ok: false`) — Faktor 2,94 — und die Zyklusauswertung sagte dazu
nichts. Schlimmer: auch die **Momentwarnung** wurde nirgends ausgegeben —
`overload_warning` kam in keiner Datei außer ihrer eigenen vor.

**Status: behoben** (15.09.2026). `ema_analysis.eckdrehzahl(geom, b_gap_t, v_dc)`
ist die eine Quelle: `estimate_dq_currents` rechnet intern damit,
`server._rpm_base_von` delegiert (dort stand eine richtige, aber **zweite**
Fassung derselben Formel), und `ema_pipeline` erbt sie nicht mehr, sondern
rechnet sie — an **allen fünf** Stellen, nicht nur im Zyklus: Referenzframe,
Rotationsframes, Sättigungsbilder, `summary` und Zyklus. Der Ersatzwert heißt
jetzt `ECKDREHZAHL_ERSATZ` statt dreimal nackt `5000.0` dazustehen. Auch
`render_preview_frame` gab `rpm_base=rpm` mit — „dieser Punkt liegt per
Definition an der Eckdrehzahl", also nie Feldschwächung; es rechnet sie jetzt
ebenfalls selbst.

**Nachgemessen am gemeldeten Lauf** (gleiche Geometrie, gleicher Zyklus, nur
`rpm_base` getauscht):

| `rpm_base` | Cu | Fe | Mg | Lg | Summe | η |
|---|---:|---:|---:|---:|---:|---:|
| 600 (erste Zeile der Bilderliste) | **317,4** Wh | **8,7** Wh | 0,3 | 2,0 | 328,3 Wh | 96,6 % |
| 583.428 (gerechnet) | **1,9** Wh | **54,0** Wh | 0,3 | 2,0 | 58,2 Wh | 99,4 % |

Die Rangfolge dreht sich um, wie es bei 1119 Hz Grundfrequenz sein muss. Dass
die Eckdrehzahl dieser Maschine so hoch liegt, ist kein Rechenfehler, sondern
ihre Aussage: `psi_pm` = 0,0062 Wb (Ferrit, `B_gap` 0,169 T) — sie erreicht die
Spannungsgrenze nie.

Die Drehzahlprüfung ist mitgekommen: `cycle_energy` nimmt `rpm_max_zul`,
liefert `speed_warning` und nennt bei einer Fahrt die **Übersetzung als Hebel**
(„80,0 statt höchstens 27,3"); beide Warnungen stehen jetzt im Laufprotokoll,
und `ema_sicherheit` hat das Kriterium `zyklusdrehzahl` (14 Kriterien). Eine
nicht übergebene Grenze heißt `None` und nicht „bestanden".

**Das bewegt Altbestand:** jede gespeicherte Kupfer- und Eisenzahl eines
Zyklusergebnisses hängt an der gewählten Anfangsdrehzahl des Bilderlaufs und ist
mit einem neuen Lauf nicht vergleichbar. Test: `test_zyklen.py` A, C, E.

---

## 2026-09-13 — Negative Wellenmasse: `_clamp` kennt keine Beziehungen zwischen Parametern

**Beobachtung.** Der erste Lauf des neuen Ausreiz-Optimierers (`ema_ausreizen`,
Ziel Leistungsdichte) steigerte den Zielwert von 0,3625 auf **26,89 kW/kg** —
Faktor 74. Das ist kein Entwurfsgewinn, sondern ein Loch im Modell. Das
Protokoll zeigt, wohin er lief: `shaftD` von 96 auf **39,32 mm** herunter,
`shaftBore` gleichzeitig von 110 auf **190,1 mm** hinauf. Eine Bohrung von
190 mm in einer Welle von 39 mm.

**Messung** (`ema_screen.massen_und_kosten`, 305-mm-Maschine, L = 150 mm):

| shaftD | shaftBore | welle_kg | gesamt_kg |
|---:|---:|---:|---:|
| 120,00 | 110,00 | 3,26 | 72,97 |
| 96,00 | 132,00 | **−11,64** | 63,72 |
| 61,44 | 158,40 | **−30,23** | 51,31 |
| 39,32 | 190,10 | **−49,05** | 35,24 |

`m_welle = π/4·(d_wel² − d_bohr²)·(L+80)·ρ` (`ema_screen.py:646`) wird negativ,
sobald die Bohrung größer ist als die Welle, und eine negative Masse **senkt die
Gesamtmasse**. Damit ist Leistung/Masse beliebig steigerbar, ohne dass sich an
der Maschine etwas verbessert.

**Ursache — und sie ist allgemeiner als dieser eine Ausdruck.**
`ema_optimize._clamp` klemmt jeden freien Parameter **einzeln** gegen sein
`lo`/`hi`. `shaftD = 39,32` ist für sich zulässig (8…400), `shaftBore = 190,1`
ebenso (0…380) — die Kombination ist es nicht. **`_clamp` kennt keine
Beziehungen zwischen Parametern**, und jede Suche über `FREE_PARAMS` kann
deshalb geometrisch unmögliche Kombinationen erzeugen.

Die Regel selbst fehlt nicht: `ema_text2ema._validate:301` erzwingt seit jeher
`shaftBoreD >= shaftD − 2 → 0` und die ganze radiale Ordnung. Sie läuft auf dem
**Suchpfad** nur nicht mit, weil `_validate` dort nie gerufen wird.

**Das ist der dritte Fall desselben Musters an einem Tag** — nach dem fehlenden
Layouttor im Bewerter und der fehlenden Sättigung. Immer dieselbe Form: die
Zielgröße belohnt etwas, das es nicht gibt, und nichts widerspricht. Ein
Optimierer ist dabei kein Verursacher, sondern ein **Messgerät**: er findet
zuverlässig die schwächste Stelle des Modells, und genau deshalb ist sein erster
Lauf so aufschlussreich.

**Behoben, und ausdrücklich nicht still:**
* `ema_screen.massen_und_kosten` klemmt die Bohrung auf `shaftD − 2`. Eine
  negative Masse ist kein Modellierungsstandpunkt, sondern falsch; die Zahl
  ändert sich nur für Geometrien, die es ohnehin nicht geben kann (gemessen:
  −49,05 → 0,22 kg).
* `ema_optimize._stimmig(geom)` prüft die radiale Ordnung im **gemeinsamen**
  Bewertungskern, wie `_baubar` und `_saettigung` — damit sehen sie
  Zielwertsuche, Parameterstudie, Magnetfeinschliff und Ausreizen zugleich statt
  eine von vieren. `_violation` rangiert `stimmig is False` wie das Unbaubare
  (1e8). `ema_leistung.kennlinie` fragt das Tor **vor** dem Layouttor: wessen
  Radien nicht ineinander passen, hat keine Geometrie, über die sich das
  Magnet-Layout äußern könnte.

**Nicht angefasst:** die Pipeline-Stufe 0. Eine neue Ausschlussregel dort würde
bestehende Auslegungen von einem Tag auf den anderen verweigern — dieselbe
Zurückhaltung wie bei `zusatzteile_check`.

**Status: behoben (Bewerterpfad), offen als Bauprinzip.** `_clamp` kennt
weiterhin keine Beziehungen; `_stimmig` prüft *nach* dem Klemmen. Wer künftig
einen freien Parameter hinzufügt, der mit einem anderen zusammenhängt, muss die
Beziehung dort eintragen — es gibt keinen Mechanismus, der ihn daran erinnert.

---

## 2026-09-13 — Das körperangepasste Netz entscheidet die Eichungsfrage NICHT — es macht die Spanne größer

**Anlass.** Der offene Punkt aus dem Eintrag „Die Sättigungszahl ist um Faktor
1,8 unsicher": dieselbe Geometrie durch ein Netz rechnen, in dem die Nutöffnung
wirklich aufgelöst ist. `ema_em2d_harm` scheidet aus — es ist **ASM-only**
(`pruefe_stufe(art, "feld")`). Also `run_em3d_sector`: Ein-Pol-Sektor,
anti-periodisch, Leerlauf, mit Statornuten und Magnettaschen, zum vollen Motor
gespiegelt.

**Die Lösung ist physikalisch sauber** — das ist geprüft, bevor sie benutzt wird:
dominante Umfangsharmonische **genau p = 6**, daneben die 3. und 5. der Polwelle
(Ordnung 18 und 30), Anti-Periodizität über eine Polteilung mit **0,0 %**
Restfehler, und die eigene Kennzahl des Laufs (`b_gap_mid_peak = 0,375 T`)
stimmt mit der unabhängigen Abtastung überein.

**Messung** (Probeprojekt, Leerlauf, 234.360 Knoten im gespiegelten Motor):

| | Spitze \|Br\| | Formfaktor | Grundwelle | B_Zahn |
|---|---:|---:|---:|---:|
| Formel (Flusserhaltung, analytisches B_gap) | 0,506 T | — | — | **1,054 T** |
| FDM, auf 0,506 T geeicht | 0,506 T | 0,354 | 0,242 T | **0,588 T** |
| **Elmer, körperangepasst** | **0,375 T** | **0,250** | **0,135 T** | **0,303 T** |

Die Kette fällt in zwei Stufen zu je rund **1,8** — FDM/Elmer = 1,79 ist
derselbe Faktor, der schon zwischen Formel und FDM stand. Die drei Wege spannen
zusammen **Faktor 3,5**.

**Was das heißt und was nicht.** Es heißt **nicht**, dass Elmer recht hat. Drei
Vorbehalte an genau diesem Lauf:

* `torque_Nm = 64,64` bei einem **Leerlauf**-Fall, dessen eigene Notiz „Netto-Moment
  ≈ 0" sagt. 64 Nm sind kein Rundungsfehler; entweder ist das ein Rastmoment-
  Artefakt der Vernetzung oder die Momentauswertung greift hier daneben. Für die
  *Form* der Luftspaltkurve spricht das nicht dagegen, für die *Höhe* schon.
* Knotenbudget 45 % (55.000 im Sektor) bei 0,80 mm Luftspalt — die Auflösung im
  Spalt ist damit nicht großzügig.
* Die Magnettaschen sind im 3-D-Pfad anders gebaut als im 2-D-Raster, und ihr
  Einfluss ist dokumentiert groß (ohne Taschen steigt die 2-D-Grundwelle
  gemessen um 75 %).

**Der belastbare Schluss ist deshalb ein anderer, und er ist unbequem:** es gibt
in diesem Werkzeug **drei Wege zur Luftspaltflussdichte und drei verschiedene
Antworten**, und keiner davon ist gegen eine Messung beglaubigt. Die Formel
liegt dabei durchweg am höchsten — für ein **Tor** ist das die sichere Seite
(sie meldet eher Sättigung, als sie übersieht), für eine **ausgewiesene Zahl**
ist es eine Unsicherheit von bis zu 3,5.

Und die Folge reicht weiter als bis zur Sättigung: liegt Elmer richtig, ist
`_analytical_Bgap` — und damit `Kt` — zu hoch. Das ist eine viel größere Aussage
als die über den Zahn, und sie ist mit diesem einen Lauf **nicht** zu treffen.

**Status: offen, Spanne erweitert und sichtbar.** Unter jeder Sättigungsausgabe
stehen jetzt alle drei Wege mit ihrem Verhältnis statt nur der 1,8. Nicht
angefasst: die Eichung, `_analytical_Bgap` und `K_LEAK_STEG`.

**Was es klären würde:** ein Lastfall gegen ein gemessenes Moment, oder ein
2-D-Netzlauf derselben Geometrie mit aufgelöster Nutöffnung und deutlich
feinerem Spalt. Beides ist ein eigener Arbeitsschritt, kein Nebenbefund.

---

## 2026-09-13 — Zwei Konstanten, wo die Physik Geometrie ist: Live-Elektrik und Stegstreuung

**(a) Die Live-Vorschau rechnete eine erfundene Maschine.** `PHYS` in `ema.html`
trug feste Werte, und die Regelgrößen standen als Literale im Quelltext:

```js
const PHYS = { voltage: 800, Rs: 0.02, Ld: 0.0003, Lq: 0.0008, Psi: 0.09 };
const tiq = Math.min((PHYS.load+20)*1.5, 800);   // Stromgrenze
let tid = -0.4*tiq;                              // d/q, kein MTPA
if (rpm > 5000) tid -= …                         // Eckdrehzahl
```

Das **Feldbild** der Vorschau nutzte die gezeichnete Geometrie, das dq-Modell
darüber nicht. Gemessen an der Probemaschine `20260913_201143_saettigungsprobe`:

| | Festwert | wirklich | Faktor |
|---|---:|---:|---:|
| `Ld` | 0,3 mH | 0,0167 mH | **18** |
| `psi_pm` | 0,09 Wb | 0,0248 Wb | 3,6 |
| Eckdrehzahl | 5000 1/min | 35.529 1/min | 7,1 |
| ξ | (implizit 2,67) | 2,14 | — |

Folge: Moment, Ströme und Feldschwächung der Vorschau gehörten einer anderen
Maschine, und die neue Umrichterkarte war dort **wirkungslos** — wer 200 A
einstellte, sah weiter 800 A.

**Behoben** (`9975973`): `psi`, `Ld`, `Lq`, Grenzen und Eckdrehzahl kommen über
`POST /umrichter` aus `compute_advanced_em` und `umrichter()`. Die MTPA-Formel
steht notgedrungen zweimal — die Vorschau rechnet 60 Mal je Sekunde und kann
nicht fragen — und ist deshalb per **Spiegeltest** an die Python-Fassung
genagelt (`test_livesim.py`, acht Fälle, größte Abweichung 1,14·10⁻¹³), wie
`magnetLegs` es seit jeher ist.

**(b) `K_LEAK_STEG` ist eine Konstante, wo die Physik eine Schranke gibt.**
`_analytical_Bgap` nimmt die Stegstreuung fest mit `K_LEAK_STEG = 0,924` an
(7,6 %). Ein **gesättigter** Steg lässt aber höchstens `B_sat·w·L` durch, und
das wandert mit Stegbreite, Baulänge und Polfluss:

| | Probemaschine |
|---|---:|
| Steg 1,30 mm, zwei je Pol, gesättigt bei 1,70 T | ≤ 0,663 mWb |
| Polfluss | 2,171 mWb |
| Streuanteil höchstens | 23,4 % |
| daraus `k_leak_steg` mindestens | 0,766 |
| angenommen | 0,924 |

Hier liegt die Annahme **innerhalb** der Schranke — kein Widerspruch. Gemessen
wird sie **unmöglich ab rund 0,35 mm Stegbreite** (bei 0,30 mm: k_min 0,933
gegen angenommene 0,924). Das ist dünn, aber real — Stanzgrenzen liegen bei
0,3–0,5 mm, und `BRIDGE_MM` wurde erst kürzlich von 2,0 auf 1,3 gesenkt. Dort
setzt das Werkzeug dann **mehr Streuung an, als durch den Steg passt**, und
`B_gap` und `Kt` fallen zu niedrig aus.

**Nicht repariert, gemeldet:** `ema_saettigung.rotorsteg()` rechnet die Schranke,
`sicherheit` führt das Kriterium `stegstreuung` **nur im unmöglichen Fall**, und
jede Sättigungsausgabe nennt den Steg als *planmäßig gesättigt* samt Schranke.
Eine geänderte Streukonstante verschöbe rückwirkend jede abgelegte Rechnung.

**Bewusst KEIN Sättigungskriterium für den Steg selbst:** er ist planmäßig
gesättigt, das ist sein Zweck. Ihn neben Zahn und Joch bei 100 % zu führen
ließe jede Maschine verletzt aussehen und machte die Liste wertlos.

---

## 2026-09-13 — Die Sättigungszahl ist um Faktor 1,8 unsicher: die Feld-EICHUNG nagelt eine Spitze auf einen Flachdachwert

**Anlass.** Auf die Frage „bist du dir sicher, dass die Sättigungsprobe richtig
ist?" habe ich die Formel gegen die gerechnete Luftspaltkurve gehalten — also
gegen die eine Größe, die dieses Werkzeug für den Luftspalt als belastbar
ausweist (`_sample_airgap`: `B_r = (1/r)·∂A/∂θ`, „robust at any N"). **Sie
stimmen nicht überein.**

**Messung** (Projekt `20260913_153549_super_auto_52`, Leerlauf, N = 700,
36 Nuten / 12 Pole, `slotWidthRatio` 0,5):

| | Zahnflussdichte |
|---|---:|
| Formel `B_gap·τ_nut/(b_zahn·k_fe)` | **1,054 T** |
| aus `Br(θ)` integriert, über die Nutteilung mit dem **größten** Fluss | **0,588 T** |
| Verhältnis | **1,79** |

Ebenso beim Polfluss: analytisch `(2/π)·B·τ_pol·L` = 2,171 mWb gegen 1,498 mWb
gemessen, Faktor 1,45.

**Ursache, und sie liegt nicht in der Sättigungsformel.**
`run_em_analysis` eicht das Feld mit `sf = _analytical_Bgap / max|Br_fdm|`
(`ema_analysis.py:1831`, `pk_mag = float(np.max(np.abs(Br_m)))`). Es nagelt also
die **Spitze** der gerechneten Kurve auf einen Wert, der seiner Herleitung nach
ein **Flachdach** ist: `_analytical_Bgap` ist Magnet-Arbeitsgerade × Polbedeckung
und hat keinen Eisenterm — eine mittlere Flussdichte unter dem Pol, keine Spitze.

Ist die Kurve spitz, skaliert das ganze Feld dadurch systematisch zu klein. Und
sie **ist** spitz: gemessen Mittel/Spitze = **0,354** gegen 0,637 beim Sinus.
Das ist bei dieser Zeichnung zu erwarten — das Werkzeug zieht **offene** Nuten
(4,03 mm Öffnung über 0,70 mm Luftspalt, s. den Rastmoment-Nebenbefund), und die
halbe Bohrung ist Nutöffnung.

**Was daraus NICHT folgt.** Es folgt nicht, dass die Formel falsch ist. Sie ist
mit der Art, wie dieses Werkzeug `B_gap` definiert und `psi_pm`/`Kt` daraus
bildet, in sich stimmig — beide ruhen auf derselben analytischen Größe. Es folgt
auch nicht, dass die Messung recht hat: ihr Maßstab kommt aus genau der Eichung,
die hier in Frage steht. **Beide können nicht zugleich stimmen, und ohne ein
konvergiertes Feld oder eine echte Messung ist das hier nicht zu entscheiden.**

Bemerkenswert ist die Richtung: die Formel liegt **höher**, meldet also eher
Sättigung als zu wenig. Für ein Tor ist das die richtige Seite — für eine Zahl,
die im Steckbrief und im Bericht steht, ist es trotzdem eine Unsicherheit von
80 %, und die gehört danebengeschrieben.

**Nicht repariert — gemeldet und sichtbar gemacht:**
* `ema_saettigung.gegenprobe_fdm()` rechnet den Vergleich auf Zuruf und nennt
  Formel, Messung, Verhältnis und den Formfaktor der Kurve.
* Unter **jeder** Sättigungsausgabe steht jetzt die Spanne mit Ursache und
  Verweis hierher, statt einer Zahl, die wie eine Messung aussieht.
* Die Eichung selbst bleibt unangetastet: sie trägt `B_gap`, `Kt`, `psi_pm` und
  jede Animation. Sie zu ändern verschöbe rückwirkend den gesamten Bestand, und
  welche Seite danebenliegt, ist nicht geklärt.

**Was es klären würde:** eine Luftspaltkurve aus einem körperangepassten Netz
(`ema_em2d_harm` rechnet bereits harmonisch in Elmer 2-D) gegen dieselbe
Geometrie — dort ist die Nutöffnung wirklich aufgelöst, und der Formfaktor wäre
gemessen statt gerastert.

**Status: offen, gemeldet, Spanne sichtbar.**

---

## 2026-09-13 — |B| im STATOREISEN konvergiert auch nicht (und was statt dessen geht)

**Beobachtung.** Für die Sättigungsgrenze lag es nahe, |B| im Statoreisen aus dem
Feldlauf abzulesen. Für das *Rotoreisen* steht in diesem Werkzeug längst, dass
das nicht geht (dünne Stege, 1 px breit, nicht aufgelöst). Für den Stator — Zähne
von 7,5 mm und ein Joch von 36,7 mm — war die Erwartung, dass es konvergiert.
**Tut es nicht.**

**Messung** (Projekt `20260913_153549_super_auto_52`, 30 Nm bei 4440 1/min,
p98 von |B| im Eisen ohne Randschicht):

| N | 300 | 420 | 600 | 800 | Streuung der letzten drei |
|---|---:|---:|---:|---:|---:|
| Zahn | 0,209 | 0,206 | 0,128 | 0,465 T | **72,5 %** |
| Joch | 0,056 | 0,052 | 0,038 | 0,128 T | **70,6 %** |
| Rotor | 1,139 | 1,433 | 1,196 | 12,247 T | 90,2 % |

Nicht konvergent und nicht einmal monoton. Die Werte sind zusätzlich
unplausibel **niedrig** — ein IPM-Zahn unter Last läuft bei 1,5…1,8 T, nicht bei
0,2.

**Eine Falle dabei, die fast zum falschen Schluss geführt hätte.** Der erste
Durchgang erodierte die Randschicht um eine feste Zahl von **Zellen** (3, wie
`test_fdm_golden._iron_bulk_p98`). Bei N = 180 sind das 6,4 mm je Seite und bei
N = 800 nur 1,4 mm — verglichen wurden also verschiedene *Gebiete*, nicht
verschiedene Auflösungen; bei N = 180 blieb vom Zahn gar nichts übrig (`nan`).
Mit fester Erosionstiefe von 1,5 mm bleibt die Nicht-Konvergenz bestehen, sie
ist also echt und kein Maskenartefakt. **Hinweis für `test_fdm_golden`:** dessen
`b_iron_bulk_p98` erodiert weiterhin in Zellen. Als *Regressionsanker* bei
festem N ist das in Ordnung — als Größe, die man über N vergleicht, nicht.

**Fundstelle.** `ema_analysis._solve_fdm` + `_curl_a`; der Anker ist
`_analytical_Bgap`, an den der Luftspaltwert gepinnt wird, während das Eisenfeld
frei mitläuft.

**Folge — und sie ist konstruktiv.** Die Sättigungsgrenze (`ema_saettigung.py`,
seit heute) wird deshalb **nicht** aus dem Feldbild genommen, sondern über die
**Flusserhaltung** aus `B_gap` — der Größe, die in diesem Werkzeug ausdrücklich
auflösungsunabhängig ist (über N = 120…600 auf vier Stellen identisch, weil sie
aus der Formel kommt und nicht aus dem Raster). Gegenprobe: der Polfluss aus
`B_gap` und der Fluss durch die Zähne stimmen auf **0,019 %** überein, und die
Werte sind physikalisch plausibel (Zahn 1,05 T im Leerlauf, 1,29 T bei 30 Nm,
102 % der Blechgrenze bei 60 Nm).

**Status: offen für das Feldbild, umgangen für die Grenze.** Wer |B| im Eisen
quantitativ braucht — etwa für die örtliche Überhöhung am Zahnfuß — braucht ein
körperangepasstes Netz; `ema_em2d_harm` sättigt den Rotorsteg bereits messend.

---

## 2026-09-13 — Das „Dauermoment" ist eine Bemessungsformel, keine Thermikrechnung

**Beobachtung.** Beim Bau der Leistungsermittlung (`ema_leistung.py`) stellte sich
heraus, dass das Werkzeug **zwei einander widersprechende Aussagen über dieselbe
Größe** führt: `results["power"]["P_cont_max_kW"] = 223,4 kW` für eine Maschine,
deren Magnete nach dem eigenen Thermikmodell bei einem Bruchteil dieser Last
schon über 250 °C liegen. Beide Zahlen stehen in derselben `results.json`.

**Messung** (Projekt `20260913_153549_super_auto_52`, Rotor-Ø 188,6, L = 150 mm,
Kühlung `forced`, NdFeB N35 mit 80 °C Dauergrenze):

| Quelle | Dauermoment | was daraus folgt |
|---|---:|---|
| `ema_thermal.rated_torque` (2·σ·V_rotor, σ aus `COOLING_RATING`) | **122,6 Nm** | Kurve „Dauer" im Kennfeld, `P_cont_max_kW = 223,4`, `cont_limited_by = "kuehlung"` |
| dasselbe LPTN-Netz, stationär, bei genau 122,6 Nm und 4440 1/min | — | Magnet **277,6 °C**, Wicklung **293,6 °C**, P_verlust 2832 W |
| Bisektion gegen die Grenzen aus `ema_sicherheit` | **30,0 Nm** | 13,9 kW bei 4440 1/min |

Das sind **Faktor 4,1 im Moment und Faktor 16 in der Leistung**. Der Magnet steht
am Bemessungsmoment auf **347 %** seiner Grenze.

Ab 7400 1/min ist die Maschine nach dem LPTN **im Leerlauf** unzulässig (Magnet
110 % bei 0,05 Nm, steigend auf 175 % bei 14.800 1/min) — dort binden allein die
drehzahlabhängigen Verluste. Das Kennfeld weist für dieselben Drehzahlen
ungebrochen 204,0 Nm Spitzenmoment aus.

**Fundstelle.** `ema_thermal.rated_torque` (`ema_thermal.py:72`) rechnet
`T = 2·σ·V_rotor` — die klassische Bemessungsbeziehung über die
Luftspaltschubspannung. Das ist als Auslegungs*schätzung* richtig und auch so
dokumentiert („standard electromagnetic sizing relation"). Zum Mangel wird es
durch die **Beschriftung**: `ema_analysis.power_envelope` nimmt den Wert als
`T_rated_Nm`, nennt die damit gedeckelte Kurve „continuous" und setzt
`cont_limited_by = "kuehlung"` — eine ausdrückliche Aussage darüber, dass die
Kühlung binde. Geprüft hat das gegen das Thermikmodell nie jemand; die beiden
Pfade berühren sich an keiner Stelle.

**Warum das zählt.** σ kommt aus einem Preset je Kühlungsart und kennt weder die
Verlustleistung dieser Maschine noch ihre Wärmewiderstände noch die Drehzahl. Bei
einer schnelldrehenden Maschine mit hohen Eisen- und Magnetverlusten liegt es
deshalb systematisch zu hoch — und zwar genau dort, wo die Magnete ohnehin das
bindende Bauteil sind. Eine Zahl, die „Dauerleistung" heißt und das Sechzehnfache
des thermisch Zulässigen nennt, ist schlechter als keine.

**Was NICHT entschieden ist.** Welche der beiden Seiten danebenliegt, ist hier
nicht geklärt und gehört in die Thermik, nicht in die Leistungsermittlung: es
kann ebenso gut sein, dass die LPTN-Wärmewiderstände für diese Baugröße zu
pessimistisch sind. Beides zusammen zu messen hieße, das Thermikmodell gegen eine
Messung zu halten, und die gibt es hier nicht.

**Status: offen, gemeldet.** Nicht repariert — nach der Hausregel bekommt ein
Werkzeug, das man für falsch hält, einen Befund und keine stille Reparatur; eine
geänderte `rated_torque` verschöbe rückwirkend jede abgelegte Dauerleistung.
`ema_leistung.kennlinie` **rechnet die Gegenprobe bei jedem Lauf** (Feld
`widerspruch`) und druckt sie als „⚠ WIDERSPRUCH im Werkzeug" über die Kennlinie,
sobald das Bemessungsmoment eine Grenze um mehr als 5 % reißt. Damit steht der
Widerspruch neben beiden Zahlen, statt dass jemand sie für zwei Meinungen über
dieselbe Maschine hält.

---

## 2026-09-13 — Parameterstudie und Zielwertsuche fragen das Layouttor NICHT

**Beobachtung (vom Nutzer gemeldet).** Eine Polpaar-Studie über p = 1…8 lieferte
für jeden Punkt Kennwerte, und `B_gap` stieg dabei **exakt linear mit p**:
0,084 / 0,169 / 0,253 / 0,337 / 0,422 / 0,506 / 0,590 / 0,675 T — `B_gap/p` ist
über alle acht Punkte auf vier Stellen konstant (0,0843…0,0845). `Kt` folgt
daraus **exakt p³** (Verhältnis zu p = 1: 1 / 8 / 28 / 66 / 129 / 223 / 354 /
528 gegen 1 / 8 / 27 / 64 / 125 / 216 / 343 / 512), denn
`Kt = 1,5·p·psi_pm` mit `psi_pm ∝ p·B_gap`.

**Messung.** Die Ursache ist keine Physik, sondern eine fehlende Prüfung.
`_analytical_Bgap` rechnet die Polbedeckung als
`alpha_i = n_legs·magWidth/pole_pitch` mit `pole_pitch = π·statorID/(2p)` — ein
**Verhältnis**, das linear mit p wächst, solange `magWidth` steht. Die Studie
hält `magWidth` aber fest (sie variiert nur p), und ab einer gewissen Polzahl
passt der Zähler nicht mehr in den Nenner: die Magnete benachbarter Pole
**durchdringen einander**. An der gemeldeten Geometrie (Stator 305 / Rotor 170 /
Welle 120, `bar`, magWidth 27 mm) gemessen:

| p | Pol-Teilung | Magnet/Pol | Bedeckung | Layouttor |
|---|---:|---:|---:|---|
| 6 | 44,9 mm | 27,0 mm | 0,60 | OK |
| 7 | 38,5 mm | 27,0 mm | 0,70 | **reißt** |
| 8 | 33,7 mm | 27,0 mm | 0,80 | **reißt** |

Bei p = 8 meldet `rotor_layout_check` wörtlich *„Kollision: Tasche (Pol 14,
Leg 0) <-> Tasche (Pol 15, Leg 0) - Überlappung 1.25 mm"*, `min_web_found_mm` =
**−1,253** — eine negative Stegbreite. Und ausgerechnet p = 7 und p = 8 sind die
beiden Zeilen, die in der Studie Temperaturen tragen (440 °C Magnet bei p = 7,
gegen 80 °C Grenze für N35).

**Der eigentliche Schaden liegt nicht in der Studie, sondern im Optimierer.**
`_violation` kennt nur die vom Menschen gesetzten Kennzahl-Grenzen und **keine
geometrische Zulässigkeit**. Weil `B_gap` mit der Überdeckung wächst, **belohnt
die Zielgröße das Unbaubare**; an derselben Maschine bei p = 6 gemessen:

| magWidth | Steg | Layouttor | B_gap | Kt |
|---:|---:|---|---:|---:|
| 34 mm | 2,95 mm | OK | 0,637 T | 0,281 |
| 38 mm | 2,86 mm | OK | 0,712 T | **0,314** |
| 41 mm | 2,86 mm | **reißt** | 0,768 T | 0,338 |
| 55 mm | 2,86 mm | **reißt** | 0,911 T | **0,401** |

Eine Zielwertsuche auf `max Kt` hätte also den Rotor mit überlappenden Taschen
zum Sieger erklärt — **+28 % gegenüber dem letzten baubaren Punkt** —, und
nichts hätte widersprochen. Der Deckel `alpha_i ≤ 0,92` rettet das **nicht
verlässlich**: er greift je nach Geometrie vor oder nach dem Tor (am frischen
Payload bei magWidth ≈ 55 und damit vor dem Tor bei ≈ 70, an der gemeldeten
Maschine erst danach).

**Fundstelle.** `ema_analysis.py:1111` (`alpha_i`), `ema_optimize.py:305`
(`_violation`), `ema_paramstudy.py:167` (die Schleife) — **null Treffer** auf
`rotor_layout_check` in beiden Modulen. Das Tor selbst gibt es seit jeher, es
kostet Millisekunden reiner 2-D-Algebra und führt die Pipeline als Stufe 0
(`ema_pipeline._gate_rotor_layout`) sowie seit dem 12.09. auch den 3-D-Netzbau
(`ema_em3d._tor_layout`) — gefragt hat es ausgerechnet an den beiden Stellen
niemand, die die meisten Zahlen je Zeiteinheit erzeugen.

**Status: BEHOBEN** (13.09.2026). `ema_optimize._baubar` fragt das Tor im
**gemeinsamen** Bewertungskern `_eval_geom`, sodass Parameterstudie,
Zielwertsuche und Magnet-Feinschliff es zugleich sehen; die Metriken tragen
`baubar`/`baubar_grund`. `_violation` gibt für `baubar is False` dieselbe 1e8
zurück wie für eine unerreichbare Auslegung — unter jeder gültigen Lösung, über
einem echten Fehler. Die Studie **bricht nicht ab** (eine Studie soll zeigen, WO
die Grenze liegt), sondern führt das Urteil je Schritt mit: rotes Band im
Diagramm, Spalte `baubar` in der CSV, und ein Hinweis, der den ersten Grund und
den Schwellwert nennt. Tests in `test_paramstudy.py`
(`test_unbaubare_punkte_werden_BENANNT`,
`test_die_zielgroesse_belohnt_das_unbaubare_NICHT_mehr` — letzterer prüft
ausdrücklich mit, dass Kt jenseits des Tors **steigt**, sonst prüfte er nichts).

**Nachtrag (13.09.2026) — die zweite Hälfte: Kt ∝ p³ = p² × p.**
Auf die Rückfrage „macht das Sinn, die Sättigung wird doch mit mehr Magneten
geringer?" nachgemessen. Hält man die **Polbedeckung konstant** (magWidth mit
der Polteilung skaliert), steht `B_gap` über p = 1…8 **exakt still** (0,6747 T
auf vier Stellen) — der lineare Anstieg war also restlos die feste Magnetlänge.
`Kt` steigt trotzdem weiter, und zwar genau mit **p²**: 0,0080 → 0,5280 = ×64.

Das ist **keine Physik, sondern die Hauskonvention „eine Windung je Nut"**
(`psi_pm = p·(2/π)·B_gap·R·L`, `Kt = 1,5·p·psi_pm`). Mit der dokumentierten
Normierungsbrücke `ema_asm.k_norm = π·k_w·N_ph/p²` zurückgerechnet ist der
**physikalische** Kt über dieselbe Reihe **exakt konstant** — ungerundet
0,118232 Nm/A für jedes p (die 3 % Streuung eines ersten Versuchs waren allein
die Rundung von Kt auf vier Stellen, bei p = 1 ist Kt 0,0033). Das ist auch das
klassische Ergebnis: bei gleichem Luftspaltfeld und gleicher Wicklung hängt das
Moment **nicht** an der Polzahl.

**Zur Sättigung selbst:** der Einwand trifft eine reale Größe, aber sie kann in
diesen Zahlen gar nicht stecken. `_analytical_Bgap` enthält **keinen Eisenterm**
— es rechnet nur die Magnet-Arbeitsgerade `h_m/(h_m+µ_r·k_c·g)` mal Polbedeckung
und setzt das Eisen implizit unendlich permeabel; der FDM-Löser ist linear mit
`MU_R_IRON = 500`, der Sättigungsdurchgang wirkt ausschließlich im
Anzeigepfad (`_saturate_field`). Weniger Sättigung kann also weder `B_gap` noch
`Kt` gutgeschrieben werden — **und mehr Sättigung wird auch nicht bestraft.**

Was der Effekt wirklich ist, exakt aus der Flusserhaltung (kein Löser nötig):
der Fluss je Pol fällt mit 1/p, gemessen 8,687 → 1,448 mWb über p = 2…12. Für
ein 1,5-T-Joch heißt das 19,3 → 3,2 mm Jochhöhe, also **84 % weniger
Rückeneisen**. Das ist der Grund, aus dem es hochpolige Maschinen gibt — nur
rechnet dieses Werkzeug es nicht von selbst gut: wer es einlösen will, muss
`statorOD`/`slotDepth` selbst verkleinern.

**Und die Sättigung verschwindet nicht, sie WANDERT.** Während das Joch
entlastet wird, werden die Stege zwischen benachbarten Taschen schmaler
(gemessen 22,19 → 3,46 mm über p = 4…10 bei konstanter Bedeckung) und tragen
die Last. Die Richtung ist im FDM sichtbar, **die Höhe nicht belastbar**: über
N = 300/420/700 wandern die Rotorwerte um Faktor 1,18 bis 2,76, sie sind also
nicht konvergiert (derselbe Vorbehalt, der in `CLAUDE.md` unter „die dünnen
Eisenstege" steht). Deshalb steht hier keine Tesla-Zahl für den Rotor.

`ema_paramstudy.deutungsfalle` schreibt die Normierung jetzt an jede
`p`-Studie — das Gegenstück zu `wirkungslos_grund`: dort steht eine Kurve still
und sieht nach einem Rechenfehler aus, hier steigt sie steil und sieht nach
einem Gewinn aus, der keiner ist.

**Was das NICHT behebt:** dass eine Polpaar-Studie bei festem `magWidth`
überhaupt eine seltsame Frage ist. Eine reale Auslegung verkleinert die Magnete
mit wachsender Polzahl; die Kurve vergleicht sonst Maschinen, die sich in mehr
als einem Merkmal unterscheiden. Das Tor sagt jetzt, ab wo sie gar nicht mehr
existieren — welche der verbleibenden Punkte man vergleichen *möchte*, bleibt
eine Auslegungsfrage.

---

## 2026-09-12 — `results.json` und `meta.json` wurden nicht atomar geschrieben

**Beobachtung.** `ema_projekt._write` schreibt die Projektakte seit jeher über
`tmp` + `os.replace` — atomar, also entweder die alte Datei oder die neue, nie
eine halbe. Die beiden **größten** Dateien desselben Projekts gingen dagegen
durch ein blankes `open(..., "w")`.

**Messung.** Ein gerechnetes `results.json` ist an der Beispielmaschine
**1,7 MB** groß. Bricht der Schreibvorgang ab (Neustart, voller Datenträger),
bleibt eine abgeschnittene Datei liegen — und die ist schlimmer als gar keine:
jeder Leser hier fängt `json.load` weich ab und meldet anschließend „nichts
gerechnet" über einen Lauf, der stundenlang gerechnet hat.

**Fundstelle.** `ema_pipeline.py:3072-3075` (vorher), Muster in
`ema_projekt.py:115`.

**Status: BEHOBEN** (12.09.2026). Neuer Helfer `ema_pipeline._json_atomar`,
beide Schreibvorgänge gehen hindurch.

---

## 2026-09-12 — `frames/` war der einzige Frame-Ordner, der nicht geräumt wurde

**Beobachtung.** `ema_oilspray`, `ema_paramstudy`, `ema_em3d` und `ema_fluidx3d`
leeren ihren Frame-Ordner, bevor sie hineinrendern. `run_pipeline` tat es als
einziges nicht.

**Messung.** `_make_video` nimmt `frame_%04d.png` **ohne Obergrenze**. Ein Lauf
mit weniger Frames als der vorige erbt dessen Reste, und das Video zeigt hinten
die Geometrie des alten Laufs — stumm, ohne Warnung, und in einem Video fällt
das erst auf, wenn jemand bis zum Ende schaut.

**Fundstelle.** `ema_pipeline.py:2323/2353/2368` (die drei
`FIELD_SUBDIRS`-Zweige), Vorbild `ema_paramstudy.py:270`.

**Status: BEHOBEN** (12.09.2026). Neuer Helfer `ema_pipeline._frames_raeumen`,
gerufen je Modus — im Teil-Nachrechnen bleibt der Ordner der nicht gerechneten
Modi damit unberührt.

---

## 2026-09-12 — Gelöscht wurde ohne Rückfrage, und nichts war rückholbar

**Beobachtung.** `/project/<id>/delete` war ein nacktes `shutil.rmtree(path)`.
Gefragt hat **allein der Browser**; die Route führte aus, was ihr gesagt wurde.
Dasselbe Muster an rund einem Dutzend weiterer Stellen (Berichte, Ansichten,
Studien, gespeicherte Öl-/em3d-/FluidX3D-Läufe), mehrere davon als
`rmtree(ignore_errors=True)` — das meldet nicht einmal, ob es geklappt hat.

**Messung.** Ein gerechnetes Projekt ist an der Beispielmaschine **5,7 MB** mit
Diagrammen, mit 3-D-Feld und Öl-Video ein Vielfaches davon, und es steckt eine
Pipeline-Laufzeit von 30 min bis 4 h darin. Wer die Route mit `curl` traf, einen
Agentenkopf danebenlaufen ließ oder eine Kennung vertippte, war das ohne
Rückfrage und ohne Rückweg los. Eine Zusicherung in einer Maske ist keine,
sobald es einen zweiten Weg zur Funktion gibt — und hier gibt es immer einen
zweiten Weg (CLI, Route, Agentenkopf).

**Fundstelle.** `server.py:3901` (vorher), dazu `server.py:1505`/`:3492`,
`ema_bericht.py:246`/`:619`, `ema_paramstudy.py:577`, `ema_ansichten.py:130`,
`ema_oilspray.py:2169`, `ema_fluidx3d.py:950`.

**Status: BEHOBEN** (12.09.2026). Neues Modul `ema_ablage` als die EINE
Löschstelle: ohne `bestaetigt=True` passiert nichts (der Aufruf gibt dann
zurück, was geschehen *würde*), sonst wandert es nach `<projekt>/.papierkorb/`
und ist über `papierkorb zurueck --marke <M>` rückholbar. Zwischenstände
(Frame-Ordner, Blender-Cache, Elmer-Netz) bleiben bewusst draußen — sie
entstehen bei jedem Lauf neu und ließen den Platz davonlaufen —, bekommen aber
eine Zeile in die Zeitleiste.

---

## 2026-09-12 — Die Marke im Papierkorb war nicht eindeutig (beim Bauen gefunden)

**Beobachtung.** Beim Schreiben von `test_ablage.py` fiel auf, dass drei
unmittelbar nacheinander entsorgte Dateien **zwei** verschiedene Marken hatten.

**Messung.** Drei Entsorgungen in einer Schleife, gemessen:
`…735_000 w1.json`, `…735_000 w2.json`, `…734_999 w0.json` — zwei Einträge
teilen sich eine Millisekunde. Die Ordner kollidieren dabei nicht (verschiedene
Dateinamen), aber die **Marke ist der Griff**, mit dem `wiederherstellen`
zurückholt: bei zwei gleichen erwischt es immer denselben, und das zweite liegt
unerreichbar im Korb. Das ist kein Sonderfall — schon das Kappen der
Berichtsfassungen entsorgt mehrere in EINER Schleife.

**Fundstelle.** `ema_ablage.py` (`_jetzt` als Marke, vor dem Fix).

**Status: BEHOBEN** vor der ersten Benutzung. `_freie_marke` zählt hoch wie
`ema_projekt.knoten_setzen`, und `inhalt()` sortiert über `_marke_key` nach
(Zeit, Nummer) — als Zeichenkette sortierte `…000-2` sonst unter `…000`.

---

## 2026-09-12 — Die Baulänge erreicht das analytische EM-Modell nicht (Kt hängt nicht an L)

**Beobachtung.** In einer Testreihe von elf Parameterstudien à 15 Schritten blieb
`Kt` über die **Blechpaketlänge** von 40 bis 120 mm auf **0,0410 Nm/A stehen**,
während die Masse im selben Lauf sauber mit 3 skalierte (7 665 → 22 995 g). Das
kann nicht sein: `psi_pm = p·(2/π)·B_gap·R_gap·L_ax` und `Kt = 1,5·p·psi_pm`
(`ema_analysis.py:1159`/`:1163`) sind in L **linear**. Eine doppelt so lange
Maschine muss das doppelte Moment je Ampere liefern.

**Messung.** Dieselbe Geometrie, einmal über den schnellen Bewerter, einmal direkt:

| Baulänge | `_eval_geom` (so rechnet die Studie) | `run_em_analysis(…, axial_mm=L)` |
|---:|---:|---:|
| 40 mm | Kt = 0,0410 | Kt = 0,0210 |
| 80 mm | Kt = 0,0410 | Kt = 0,0410 |
| 120 mm | Kt = 0,0410 | Kt = 0,0620 |

Bei 40 mm ist der Wert damit **um den Faktor 2 zu hoch**, bei 120 mm um ein
Drittel zu niedrig. `B_gap` ist korrekt unverändert (es kommt aus der Formel und
kennt kein L), `mass_g` ist korrekt proportional — nur der Pfad über `psi_pm`
ist es nicht.

**Fundstelle.** `ema_analysis.run_em_analysis` nimmt `axial_mm` als **optionales**
Argument und fällt ohne Angabe auf **fest 80 mm** zurück
(`ema_analysis.py:1804`: `L_ax = (axial_mm/1000.0) if axial_mm is not None else 0.080`,
ebenso `compute_performance`, `ema_analysis.py:1155`). Vier Produktivstellen geben
es nicht mit:

* `ema_optimize._eval_geom` — `run_em_analysis(geom, N=N, rotor_angle=0.0)`. Das
  ist der **schnelle Bewerter**, und an ihm hängen die Zielwertoptimierung
  (`axial` ist dort selbst ein freier Parameter!), die Parameterstudie, der
  Magnet-Feinoptimierer und die Vorsortierung der KI-Entwürfe samt ihrer
  Trainingslabels.
* `ema_paramstudy._render_field_series` — dieselbe Auslassung für die Feldbilder;
  `O._apply_params` gibt die Länge zwar zurück (`geom, _ax`), sie wird aber
  verworfen.
* `ema_pipeline` — die statische EM-Stufe (`ema_pipeline.py:2156`) und der
  Drehzahl-Sweep (`:2343`, `compute_performance(geom, B_gap, rpm)`).
* `ema_mobil` (`:423`).

`compute_advanced_em` und `moment_erreichbar` bekommen die Länge dagegen
**positional** und sind richtig — was den Fehler schwer sichtbar macht: in
demselben Ergebnisdict steht ein längenblindes `Kt` neben längenrichtigen
abgeleiteten Größen.

**Warum es lange unauffällig blieb.** Die Vorgabe *ist* 80 mm, und 80 mm ist die
Blechpaketlänge des `--frisch`-Payloads und der meisten Testgeometrien. Am
Auslegungspunkt stimmt die Zahl deshalb zufällig; falsch wird sie erst, sobald
jemand die Länge ändert — also genau in einer Längenstudie oder in einer
Optimierung, die an der Länge dreht.

**Naheliegende Abhilfe** (bewusst NICHT im selben Zug gemacht): der Rückfall
gehört nicht auf eine feste Zahl, sondern auf `geom["axialLen"]`; dann ist jeder
heutige und künftige Aufrufer richtig, der die Länge ohnehin in seiner Geometrie
führt, und ein ausdrückliches `axial_mm` gewinnt weiterhin. Das verschiebt die
Kennzahlen **jeder** Auslegung mit L ≠ 80 mm — auch gespeicherter — und ist
deshalb eine Entscheidung des Menschen, kein Nebenprodukt einer Parameterstudie
(`ema_werkzeugstand`: ein Ziel wird nie durch eine stille Änderung am Rechenkern
erreicht).

**Status: BEHOBEN am 12.09.2026.** Der Rückfall liegt jetzt in **einer**
Funktion, `ema_analysis.stapellaenge_m(geom, axial_mm)`, und geht in dieser
Reihenfolge: ausdrückliche Angabe → `geom["axialLen"]` → 80 mm. Sie wird von
`compute_performance`, `compute_advanced_em` und `run_em_analysis` benutzt; die
festen 80 mm bleiben nur noch als letzter Rückfall stehen, damit eine Geometrie
ohne `axialLen` (Handzeichnungen, ältere Testsätze) weiter rechnet. Zusätzlich
geben die vier Stellen die Länge jetzt ausdrücklich mit, an denen sie **neben**
der Geometrie geführt wird: `ema_optimize._eval_geom`,
`ema_paramstudy._render_field_series` und die Pipeline (statische EM-Stufe +
Drehzahl-Sweep). `ema_optimize._apply_params` schreibt die Länge außerdem **in**
die Geometrie zurück — zwei Wahrheiten über dieselbe Größe sind eine zu viel.

Nachgemessen am schnellen Bewerter: Kt 0,0210 / 0,0410 / 0,0620 bei 40 / 80 /
120 mm, Verhältnis 2,95 statt vorher 1,00. Die Wicklungstemperatur derselben
Studie fällt jetzt von 143,9 °C (40 mm) auf 75,6 °C (120 mm) — die längere
Maschine braucht für dasselbe Moment weniger Strom.

**Was sich dadurch bewegt.** Von 74 gespeicherten Projekten haben **50** eine
Baulänge ≠ 80 mm; deren Kt, ψ_pm, EMK und alles daraus Abgeleitete verschieben
sich linear mit L/80 — bei 60 mm also um −25 %, bei 160 mm um +100 %. Zwei
festgenagelte Erwartungen in `test_zyklen.py` waren davon betroffen und sind
korrigiert: der 75-mm-Antrieb dort trägt `axialLen=60`, seine
Spannungsausnutzung fällt von 310 % auf 231 % und die passende Windungszahl
steigt von 2 auf 3. `test_fdm_golden.py` gibt `axial_mm` seit jeher
ausdrücklich mit und ist unberührt.

Festgenagelt in `test_zyklen.py` (`stapellaenge_m` in allen drei Fällen, Kt
linear in L).

---

## 2026-09-12 — Zwei Rückkehrpunkte in derselben Millisekunde überschreiben sich

**Beobachtung.** `test_bruecke.py` war flatterhaft: gemessen **rund jeder vierte
Lauf** rot, ohne dass sich am Code etwas geändert hätte, und immer an derselben
Stelle — „zurück auf 'None'", der Knoten war nicht auffindbar.

**Messung.** `ema_projekt._marke_jetzt` liefert `%Y%m%d_%H%M%S_%f` auf
Millisekunden gekürzt, und `knoten_setzen` schrieb ohne jede Prüfung nach
`knoten/<marke>.json`. Ein gerechneter Lauf legt automatisch einen Rückkehrpunkt
an; wer unmittelbar danach von Hand abzweigt, trifft dieselbe Millisekunde. 25
Läufe nach der Absicherung: 25 grün. 50 Knoten in Folge ergeben jetzt 50
verschiedene Marken (vorher gemessen Kollisionen).

**Warum das nicht kosmetisch ist.** Der zweite Knoten überschrieb den ersten,
und `zurueck` führte danach an den **falschen Stand** — der eigentliche
Rückkehrpunkt war weg. Das ist genau die Sorte Verlust, gegen die die
Schnappschüsse gebaut sind.

**Fundstelle.** `ema_projekt.knoten_setzen` (`:360`) und `knoten_holen` (`:411`).
Letzteres prüfte die Marke gegen `[0-9_]{1,32}` — der Kollisionszusatz `-2`
wäre daran gescheitert, der Knoten also geschrieben und trotzdem unerreichbar
gewesen. Beides zusammen gehört.

**Status: BEHOBEN am 12.09.2026.** Dieselbe Absicherung wie in
`ema_steckbrief.ablegen` und `ema_paramstudy.studie_anlegen`: existiert die
Datei, wird `-2`, `-3`, … angehängt; das Markenmuster kennt den Zusatz, weist
aber Pfade und erfundene Zusätze weiter ab. Festgenagelt in `test_bruecke.py`.

---

## 2026-09-11 — Vier Verben laufen im System-Python nicht, und melden dabei das Falsche

**Beobachtung.** `python3 cae_cli.py struktur --frisch` bricht ab mit
`FEHLER: Vernetzung fehlgeschlagen: No module named 'gmsh'`, Exit 1. Der Satz ist
zweimal irreführend, und zwar in der Richtung, die einen Agenten in die falsche
Arbeit schickt: **die Vernetzung ist nicht fehlgeschlagen** — sie hat gar nicht
angefangen, weil dem Interpreter das Modul fehlt; und **Exit 1 heißt in dieser CLI
„Gegenstelle"**, also „das Werkzeug hat gearbeitet und sagt Nein zu deiner
Geometrie". Wer das liest, ändert `magDist`, `mesh_mm` oder die Taschenlage — und
bekommt beim nächsten Versuch denselben Satz. Richtig wäre „Bedienfehler" (Exit 2)
und ein Text, der den Interpreter nennt.

Der Grund, dass es überhaupt so weit kommt: `gmsh` wird **erst im Aufruf**
importiert (damit der Rest der CLI schlank bleibt und stdlib-nah startet). Der
`ModuleNotFoundError` fällt deshalb mitten in `ema_deck.baue` an, wo
`cmd_struktur` ihn mit `except Exception` als Vernetzungsfehler einsammelt —
genau der Stelle, die für „gmsh kommt mit dieser Geometrie nicht zurecht" gebaut
ist.

**Messung.**

- Module im System-Python (`/usr/bin/python3`, 3.12.3) gegen die venv:

  | | numpy | scipy | matplotlib | vtk | **gmsh** | flask |
  |---|---|---|---|---|---|---|
  | `/usr/bin/python3` | ✓ | ✓ | ✓ | ✓ | **fehlt** | fehlt |
  | `venv/bin/python` | ✓ | ✓ | ✓ | ✓ | **✓** | ✓ |

  `gmsh` steht in `requirements.txt:12` und liegt damit **nur** in der venv.
  `/usr/bin/gmsh` (4.12.1) ist das Programm, nicht das Python-Modul, und hilft
  hier nicht.

- Betroffen sind vier Verben, alle mit demselben Muster:

  | Aufruf (System-Python) | Meldung | Exit |
  |---|---|---|
  | `struktur --frisch --mesh 12` | `Vernetzung fehlgeschlagen: No module named 'gmsh'` | 1 |
  | `topopt --frisch --iterationen 1` | `Vernetzung fehlgeschlagen: No module named 'gmsh'` | 1 |
  | `feld2d --frisch --set machineType=asm` | `Feldlauf fehlgeschlagen: ModuleNotFoundError: No module named 'gmsh'` | **4** |
  | `feld3d --frisch --set machineType=asm --nur-netz` | `3-D-Netzbau fehlgeschlagen: ModuleNotFoundError: No module named 'gmsh'` | **4** |

  **Bei `feld2d`/`feld3d` ist der Exit-Code eine eigene, größere Sache: 4 heißt in
  dieser CLI „Zeitüberschreitung".** Gemeldet wird also „der Lauf war zu lang" für
  ein fehlendes Modul — und das schickt einen Agenten zum Vergröbern des Netzes
  oder zum Heraufsetzen der Zeitgrenze, beides wirkungslos. Die Ursache steht
  in zwei Zeilen: `cae_cli.py:1341` und `:1475` geben die **nackte Zahl `4`**
  zurück, wo sonst überall die benannten Konstanten stehen
  (`EXIT_OK, EXIT_REMOTE, EXIT_USAGE, EXIT_DOWN, EXIT_TIMEOUT = 0, 1, 2, 3, 4`,
  `cae_cli.py:42`). Es sind die **einzigen** zwei Stellen im ganzen Verb-Satz, an
  denen ein Exit-Code als Literal steht; an einer benannten Konstante wäre
  niemandem entgangen, dass dort `EXIT_TIMEOUT` gemeint gewesen wäre. Das gilt
  unabhängig von Gmsh — **jeder** Fehlschlag dieser beiden Feldstufen wird heute
  als Zeitüberschreitung gemeldet.

- Die Module selbst laden alle sauber (`import ema_deck`, `ema_topopt`,
  `ema_z88`, `ema_aster`, `ema_em2d_harm`, `ema_em3d_harm`, `ema_em3d`,
  `ema_bilddaten`, `ema_getriebe`, `ema_feldbild`, `ema_welle` — 11 von 11 ohne
  Fehler). Es gibt also keinen Import-Zeitpunkt, an dem das auffiele.

- Gegenprobe: `venv/bin/python cae_cli.py struktur --frisch --mesh 12` läuft
  durch (`Netz: 566 Knoten, 1.734 Tet4, ein Polsektor, 15000 min-1`).

- **Und die Unterlagen zeigen genau den Aufruf, der nicht geht:** `python3
  cae_cli.py …` steht **70 mal** in `.agents/skills/cae-orchestrator/SKILL.md`
  und **10 mal** in `AGENTS.md`; `venv/bin/python cae_cli` steht **null mal** in
  beiden. Die venv wird in der `SKILL.md` überhaupt nicht erwähnt. Ein Modell
  folgt den Beispielen — das ist derselbe Mechanismus, aus dem `--frisch`
  entstanden ist (alle Beispiele zeigten `--from-project last`, also erbte jede
  neue Auslegung die vorige).

**Fundstelle.** `cae_cli.py:991` und `:1088` (`_die(f"Vernetzung fehlgeschlagen:
{e}", EXIT_REMOTE)`); `cae_cli.py:1341` und `:1475` (Literal `4` statt einer
benannten Konstante, gegen `cae_cli.py:42`); `requirements.txt:12`;
`.agents/skills/cae-orchestrator/SKILL.md` (jedes Beispiel).

**Status.** Punkt 1 und 2 **behoben am 2026-09-11**, Punkt 3 offen. Es ist kein
Defekt der Physik, sondern einer der Bedienung, und er hatte drei mögliche
Antworten, die sich nicht ausschließen:

1. **Beim Fehlschlag die Wahrheit sagen.** Ein `ModuleNotFoundError` im Netzbau
   ist kein Geometriebefund: eigener Zweig, Exit 2 (Bedienfehler), und der Text
   nennt `sys.executable` samt dem Aufruf, der geht. Das ist die kleinste
   Änderung und behebt den eigentlichen Schaden — die falsche Fährte.
   **Die beiden Literale `4` sind davon unabhängig zu berichtigen**, denn sie
   verfälschen jeden Fehlschlag der Feldstufen, nicht nur diesen.

   *Umgesetzt.* `_oertlicher_fehlschlag(e, was)` (`cae_cli.py:106`) ordnet den
   Fehler ein und ist die EINE Stelle für alle vier Fundstellen — vier
   Abschriften wären die, die beim nächsten Mal auseinanderlaufen. Ein
   `ImportError` gibt `EXIT_USAGE` und einen Text, der das Modul, den
   `sys.executable` und den Aufruf nennt, der geht, und ausdrücklich dazusagt,
   dass an der Auslegung **nichts geprüft** wurde; alles andere bleibt
   `EXIT_REMOTE` samt Fehlertyp. Die beiden `4`-Literale sind damit weg.
   Nachgemessen nach der Änderung, alle vier im System-Python:

   ```
   struktur --frisch --mesh 12                        Exit 2
   topopt   --frisch --iterationen 1                  Exit 2
   feld2d   --frisch --set machineType=asm            Exit 2
   feld3d   --frisch --set machineType=asm --nur-netz Exit 2
   FEHLER: Modul 'gmsh' fehlt in diesem Python (/usr/bin/python3) — Vernetzung
   hat deshalb NICHT begonnen. Die Auslegung ist damit NICHT beanstandet: an
   ihr wurde nichts geprueft. Aufruf mit …/venv/bin/python cae_cli.py …
   ```

   Festgenagelt in `test_cae_cli.py::test_fehlendes_modul_ist_kein_geometriebefund`
   — samt der Gegenrichtung (ein `RuntimeError` bleibt Exit 1 mit
   „Feldlauf fehlgeschlagen") und einer Prüfung am Quelltext, dass **kein**
   Exit-Code mehr als nackte Zahl dasteht.
2. **Beim Start prüfen.** Die Verben, die Gmsh brauchen, sagen es, bevor sie
   rechnen, statt mittendrin. — *Nicht umgesetzt und bewusst nicht:* nach der
   Berichtigung aus Punkt 1 ist der Unterschied nur noch, ob die Meldung vor
   oder nach dem Payload-Aufbau steht (Bruchteile einer Sekunde), und eine
   zweite Liste „welches Verb braucht welches Modul" wäre genau die Art von
   Abschrift, die still veraltet.
3. **Den Interpreter in den Unterlagen richtigstellen.** Das ist die Frage
   dahinter und keine reine Textänderung: `cae_cli.py` ist ausdrücklich für den
   System-Python gebaut (Kern stdlib-only, kein `requests`), und `feldbild`,
   `welle`, `getriebe`, `steckbrief`, `paarvergleich` laufen dort auch wirklich —
   nur die vier gmsh-Verben nicht. Ob alle Beispiele auf die venv umgestellt
   werden oder nur diese vier, ist eine Entscheidung über den Charakter der CLI
   und gehört nicht in einen Befund.

Gefunden beim Einbau von Code Aster als drittem Löser (`--solver alle`), also
beim ersten Aufruf von `struktur` aus dem System-Python seit längerem. Der
FreeCAD-Weg und der Browser sind **nicht** betroffen: der Server läuft in der
venv.

---

## 2026-09-10 — Code_Aster ist nicht verfügbar — und bleibt es, solange AppArmor unprivilegierte userns sperrt

**Beobachtung.** `ster`/`salome` gibt es systemweit nicht. Spack 1.3.0 user-space
ist installiert, kennt das Paket `code-aster` aber nicht (`spack code-aster` →
`does not exist` — der PR ist nicht merged). `codeaster/src` @ 18.1.5 ist unter
`~/aster-build/src/src` geklont (32 852 Dateien, WAF-Build, keine CMake).

**Messung.**
- `which aster`, `which salome` → nicht gefunden.
- `spack spec code-aster` → `cannot concretize 'code-aster', since 'code-aster' does not exist`.
- Code_Aster 18 braucht Doflux und SALOME (SMESH, MED, BRep) als externe Libs.
  Die öffentlichen Repos (`gitlab.com/doflux/doflux`,
  `gitlab.com/salome-platform/SALOME-Platform`) sind **nicht öffentlich**
  (HTTP 302 → `gitlab.com/users/sign_in`). Ohne die Libs start
  der WAF-Build nicht.
- Als: SIF-Bundle `salome_meca-lgpl-2025.1.0-1-20251026-scibian-12.sif`
  (5,4 GB) in `~/Downloads`. Apptainer 1.5.3 aus DEB entpackt unter
  `~/apptainer-pkg`. Start bricht an:
  `apparmor_restrict_unprivileged_userns = 1` und
  `unshare -Urmp` → `/proc/self/uid_map: Operation not permitted`.
  Kein sudo → setuid-Binär nicht setzbar. Beide Modi (userns, setuid) sind in
  dieser Umgebung nicht nutzbar.

**Fundstelle.** `~/aster-build/src/src/` (Code_Aster 18.1.5),
`~/apptainer-pkg/` (Apptainer 1.5.3), SIF in `~/Downloads/`.

**Status.** Behoben am 2026-09-10. Der SIF-RootFS wurde mit `unsquashfs`
direkt aus dem SIF extrahiert (`tail -c +65537 SIF | unsquashfs -d salome-img`);
userns / AppArmor / setuid sind nicht mehr nötig. Code_Aster 17.4.0
(`lib64/aster/code_aster/`) läuft als reines Python-Paket mit eingebauten
Libraries (HDF5 1.10.9, MUMPS 5.6.2, MED 4.1, MFront 4.2, SCOTCH 7.0.4) unter
`~/aster-build/salome-img/`. Start-Wrap

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

---

## 2026-10-30 — `magnetschluss` ist nicht reproduzierbar; Schwelle liegt im Rauschen

**Beobachtet:** gleicher Payload, gleiche Maschine (Projekt `20261030_140522`,
`pocketMode=position, magWidth=30–34, magThick=4, magLayers=2, magAngle=120,
rotorOD=146`) liefert je Lauf **streuanteil 0.355 (N400) und 0.438 (N400)**,
beide deterministisch in sich, aber nicht übereinander wiederholbar.
`N=300`/`N=400` unterscheiden sich um 0.06–0.10 — exakt die Größe, auf der
`STABIL_TOL = 0.08` ("unsicher") greift.

**Wo gemessen:** `cae_cli.py magnetschluss` (FDM-Feld, `ema_magnetschluss.messen`),
Ring ±0.4 mm um die Spaltmitte, `A_spalt = peak|A|`. Der Peak von A sitzt auf
einem Pixelrand; numerische Rauschen im Relaxationslauf verschiebt ihn, und ein
Rauschen von 0,5 % des Feldes schmeißt 0.355 auf 0.35 — die Schwelle.

**Folge fürs Auslegungswerkzeug:** Ob eine Maschine bei D ≤ 200 mm "stufe ok"
(<35 %, stabil) oder "auffaellig" ist, kann nicht aus der Abweichung um
±0.02–0.05 gefolgert werden. Jede Entscheidung, die auf dieser Größe steht,
braucht einen zweiten Lauf zur Bestätigung — und die beiden Läufe können
widersprüchen. Das ist kein Einstellfehler, sondern die Eigentliche Auflösung
der Messung.

**Gemessen an dem Tag:** D = 200 mm, p = 5, 24 Nuten: keine Konfiguration
(V-Wand, V-Position, Spoke, SPM, Balken, U, Doppel-U, Delta, V-asym) unter
0.35 stabil; SPM 0.038 "ok" aber Sättigung 207 % im Leerlauf (Eisentor 115 %);
Spoke 0.327 "ok" bei N=400 aber 0.58 bei N=300; V 0.44–0.52 "auffaellig/kurzschluss".
D = 280 mm (Frisch-Vorgabe) 0.32/0.33 "ok". Der Konflikt Magnetfluss-Schließung
und Eisen-Sättigung bei OD ≤ 200 mm ist geometrisch (Magnetquerschnitt /
Spalt-Ringfläche), nicht parametrisch.

---

## Befund 31.10.2026 — Leistungszile Zeigt Drehzahlen, die nicht zum Punkt passen (umrichterBezug=wicklung)

**Was beobachtet:** In den Auslegungslaufen vom 30.10.2026 (Entwurfsmodus, Projekt
20261030_203841 und 20261030_205253 mit `umrichterBezug=wicklung`) zeigt die
Zile "Leistung" Drehzahlen, die weder mit der Motor-Drehzahl noch mit sich selbst
konsequent sind:
- 20261030_203841: `P_max ~ 59 kW @ 409 U/min | T_max ~ 1411 Nm bis 204 U/min`
- 20261030_205253: `P_max ~ 62 kW @ 1839 U/min | T_max ~ 359 Nm bis 1431 U/min`
- Vergleich 20261030_202321 (gleiche Maschine, `umrichterBezug=einwindung`):
  `P_max ~ 58 kW @ 10500 U/min | T_max ~ 53 Nm` — hier ist das "@-Drehzahl"
  die zul. Betriebsmax.

Rechnung: 62 kW / 1839 U/min entspraeche 323 Nm (anstatt 359), und 1839 U/min
= 16350 / 8,9, also die **Felddrehzahl** des Zyklusfahrzeugs (Uebersetzung 8,9)
— die Zile mischt Motorleistung mit Felddrehzahl und ist intern nicht
konstant. Die Sicherheitswerte und die thermische Leistung (755 W am Punkt)
sind davon nicht betroffen; die Zile darf nicht ins Protokoll.

**Wo gemessen:** Laufende Zeile nach `run analyse --wait`, Ausgabe der
Pipeline-Stufe "Leistung" (Ausbau bei `ema_pipeline.py` Zeile ~5446,
`Demag-Reserve` auf der Zeile; die "Leistung"-Zeile davor im selben Block).
Alle drei Laeufe Entwurfsmodul, gleiche Geometrie, nur umrichterBezug/
turnsPerSlot/Skew/Rotorblech geaendert.

**Fundstelle:** `ema_pipeline.py` (Leistungszile im Analyse-Ausbau),
eingespielt gegen `ema_analysis.power_envelope` / `umrichter`-Referenz
(`ema_analysis.py` ~Z1850-1900, "auf EINE Windung je Nut bezogen").
