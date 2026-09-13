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
