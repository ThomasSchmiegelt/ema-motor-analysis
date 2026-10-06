# Axialfluss — eigenständige Ansicht

**Bewusst getrennt von `ema.html`.** Diese Seite hat keinen Server, keine
Abhängigkeit und keine gemeinsame Datei mit der Hauptoberfläche. Sie wird mit
`file://` geöffnet:

    xdg-open cae_orchestrator/axialfluss/ansicht.html

## Warum getrennt

`ema.html` ist auf die Radialflussmaschine gebaut — 643 kB, keine `@media`-Regel,
Layout aus Splittern, und drei Viertel ihrer hundert `geom`-Felder bedeuten axial
nichts. Etwas dort einzubauen, das noch nicht stimmt, hieße die eine Oberfläche
zu belasten, die funktioniert. Hier wird erst gezeigt, **dass** die Maschine
richtig gezeichnet ist; integriert wird danach und als Entscheidung, nicht
nebenbei.

## Was die Seite tut — und was nicht

Sie **zeichnet**. Was in der Kennwerttabelle steht, ist aus der Zeichnung
abgelesen oder unmittelbar daraus gerechnet (Zahnbreite, Polteilung,
Spalt/Polteilung, Baulänge/Durchmesser, Maxwell-Normalspannung). **Keine
Auslegung, keine Kennzahl, die irgendwo gespeichert würde.**

Sobald es um Zahlen geht, gilt `ema_axial_fdm.py` (Stufe 2) — und dessen offene
Punkte stehen in `BEFUNDE.md`: die Amplitude ist nicht konvergiert, und die
beiden Momentwege liegen um den Faktor 3 auseinander.

## Dateien

| | |
|---|---|
| `ansicht.html` | Maske und drei Leinwände |
| `ansicht.js` | Zeichenlogik: Draufsicht, r–z-Halbschnitt, abgewickelter Schnitt |
| `geometrie.js` | `stapelLagen` — die Schichtung, EINE Quelle für alle drei Ansichten und den Löser |
| `feld.js` | der Feldlöser der abgewickelten Scheibe (qualitativ) |
| `schnitt.js` | der **Schnitt durch die Achse**, mehrschnittig gerechnet |
| `pruefe.js` | misst den Löser **ohne Browser** nach: `node pruefe.js` |

## Der Schnitt durch die Achse

Die r–z-Ebene ist die eine Ebene dieser Maschine, in der ein 2-D-Löser **nicht**
rechnen kann, und das ist kein Mangel an Mühe: zweidimensional heißt invariant
in der dritten Richtung, die dritte Richtung ist hier θ, und in θ liegt der
Polwechsel. Eine in θ invariante Maschine hätte gar keine Pole.

Rechnen lässt sie sich trotzdem — nur nicht als **ein** Problem. `schnitt.js`
löst die abgewickelte θ–z-Ebene bei mehreren Radien und legt die Lösungen
übereinander (Mehrschnitt / Quasi-3-D, das Standardverfahren der
Axialflussrechnung). Dass das ohne Interpolation geht, liegt daran, dass die
Schichtung nicht am Radius hängt: alle Scheiben haben dasselbe z-Gitter
(`pruefe.js` §9 prüft es).

**Ein Winkel oder alle 360° kostet dasselbe.** Eine Scheibe wird bei einem
Radius gelöst und trägt danach ihren ganzen Umfang; den Schnittwinkel zu ändern
heißt, eine andere Spalte abzulesen. Gemessen: 360 Winkel in 55 ms gegen 559 ms
für **einen** Löserlauf. Deshalb fällt die 360°-Ansicht (B_z in der Spaltmitte
über der ganzen Scheibe) gratis mit ab. Was einen neuen Lauf kostet, ist jede
Änderung an der **Erregung** — Strom, Stromwinkel —, und die ist deshalb
entprellt.

**Eine Eichung für alle Scheiben.** `eichung` pinnt die Spaltspitze auf die
Arbeitsgerade, und die hängt nicht vom Radius ab: jede Scheibe einzeln geeicht
hätte per Konstruktion überall dieselbe Spaltspitze, und die radiale Änderung —
derentwegen der Schnitt überhaupt gezeichnet wird — wäre exakt wegnormiert.
Dieselbe Entscheidung wie `sf_ref` in `ema_analysis.run_em_analysis`.

**Was dabei herauskommt, ist die Signatur der Bauart, gemessen:**

| r [mm] | 77 | 91 | 105 | 118 | 128 |
|---|---:|---:|---:|---:|---:|
| τ_s [mm] | 10,1 | 11,9 | 13,7 | 15,5 | 16,7 |
| B_Zahn [T] | **1,83** | 1,29 | 1,16 | 1,07 | **1,09** |
| B_Spalt [T] | 0,851 | 0,819 | 0,814 | 0,809 | 0,829 |

B_Spalt steht auf 2,6 % — der Spaltleitwert hängt nicht am Radius. B_Zahn fällt
um Faktor 1,7, und zwar allein, weil τ_s mit r wächst und die Nutbreite nicht:
**der kritische Punkt liegt am Innenrand.** Genau das behauptet die Zeichnung
seit dem ersten Entwurf; hier steht es als Messung.

**Was fallengelassen ist, steht als Zahl da.** Der Mehrschnitt lässt `∂/∂r`
weg. `radialeKopplung` misst, wie stark sich das Feld über dem Radius ändert,
und rechnet es auf eine Luftspaltlänge um: **0,047 %** je Luftspaltlänge auf
dieser Geometrie — so lange das klein gegen die axiale Änderung ist, ist das
Weglassen vertretbar. **Feldlinien in dieser Ebene gibt es bewusst nicht:** in
der r–z-Ebene sind die beiden Komponenten B_r und B_z, und B_r setzt das
Scheibenmodell per Konstruktion auf null. Gezeichnet werden Pfeile für den
axialen Fluss — und *dass* er axial steht, ist die Aussage.

**Drehzahl.** Eine magnetostatische Rechnung kennt keine Drehzahl; sichtbar wird
sie allein über den Stromvektor. Deshalb gibt es hier `Ankerrückwirkung [%]` und
`Stromwinkel β` — β = 0 ist die q-Achse (dreht die Resultierende), β = ±90° die
d-Achse (verstärkt bzw. schwächt). Die Abbildung Drehzahl → (i_d, i_q) hat diese
Seite **nicht**; die steht in `ema_analysis.estimate_dq_currents`, also auf dem
Python-Weg. Dabei kam ein Befund heraus: der alte Regler „Ständerstrom" bewegte
über seinen ganzen Stellbereich 0,02 % — `BEFUNDE.md`, 06.10.2026.

## Wie viele Magnete, wie viele Zähne

Beides ist einstellbar, und zwar genau so weit, wie es eine Einstellung ist:

* **Ständerzähne** sind keine eigene Größe. Ein genuteter Ring hat so viele
  Zähne wie Nuten — zwei Felder dafür wären eine Einstellung, die es nicht gibt.
  Das Feld heißt deshalb „Ständernuten Q = Zähne".
* **Magnete** haben zwei: Segmente je Pol **umfangs** (gegen Wirbelstrom­verluste
  und weil eine große Platte kaum zu handhaben ist) und **über dem Radius**
  (weil der Polbogen nach außen breiter wird und eine Platte über Ri…Ro sonst
  ein ungünstiges Seitenverhältnis hat). Die Zahl steht in der Tabelle:
  `2p × umfangs × radial`.
* **Läuferzähne/-stäbe** des Käfigläufers sind frei setzbar, `0` leitet sie ab.
  Die Ableitung ist ein **Spiegel von `ema_asm.stabzahl`** — ≈0,85·Q, aber nicht
  gleich Q, nicht um 0/±p/±2p/±3p daneben und kein Vielfaches der Polzahl;
  `pruefe.js` §8 hält die JS-Fassung über 30 Fälle gegen die Python-Fassung.
  Eine von Hand gesetzte Zahl wird **gezeichnet und benannt**, nicht geklemmt.

Zwei Dinge, die dabei gemessen und nicht angenommen wurden:

* Die **Fuge zwischen zwei Segmenten ist eine radiale Linie**, also ein fester
  Winkel — so sind Ringsektormagnete gefertigt. Ihre mm-Angabe gilt am mittleren
  Radius. Dadurch ist sie als Bruchteil der Polteilung radiusunabhängig, und
  genau deshalb können alle drei Ansichten UND der Löser dieselbe Funktion
  lesen. Sie kostet: 4×3 statt 1×1 nimmt bei 1 mm Fuge 12,1 % der Magnetfläche,
  und B1 fällt von 0,8082 auf 0,7485 T — der Löser sieht die Fugen.
* Die **radiale Segmentierung ist im abgewickelten Schnitt unsichtbar**, und das
  ist richtig: eine radiale Fuge liegt auf konstantem Radius, der Schnitt steht
  bei einem Radius. Sie erscheint in der Draufsicht und im r–z-Halbschnitt, und
  die Tabelle sagt es.

Dabei ist ein Befund herausgekommen: das **Halbach-Array trug die doppelte
Polzahl** (`seg = 4`, `[1,0,-1,0]` je Polteilung = 360° statt 180°), und `Mx`
fehlte ganz im Quellterm. Beides behoben, gemessen und in `BEFUNDE.md`
(06.10.2026) aufgeschrieben.

## Der Feldlöser

Finite Volumen, harmonisch gemittelte Flächenleitwerte, **Jacobi-vorkonditioniertes
CG** (gemessen 40× schneller als SOR bei µr-Sprüngen 1 → 500; der Operator ist
SPD). Zwei Dinge sind dabei besser als auf dem Python-Weg:

* **Rechteckiges Gitter** — `A = 0` sitzt auf den Jochaußenflächen und den
  Polgrenzen, wo es hingehört. Keine Luft- oder Eisenpolsterung, und damit keine
  Abhängigkeit von der Fensterbreite.
* **Die y-Linien liegen auf den Schichtgrenzen.** Der Luftspalt ist exakt 1 mm,
  gleich wie fein gerechnet wird. Erst dadurch konvergiert B1 **monoton**
  (8,99 → 3,86 → 3,20 → 0,43 → 0 %); mit gleichmäßigem dy streut es um ±6 %.
  Siehe `BEFUNDE.md`, 06.10.2026 — das widerruft eine Einschränkung vom Vortag.

`node pruefe.js` misst das nach: Konvergenz, Linearität (J → 2J gibt exakt
2,000000), Gitterkonvergenz und die Flussbilanz (Ständermitte führt 89 % des
Spaltflusses, beide Spalte gleich).

## Die Bauart

Gezeichnet nach Igelspacher, *Zur Theorie der Axialfluss-Asynchronmaschine als
ausfallsicherer Antrieb*, Diss. TU München 2018/2020, Kap. 2. Die eine Stelle,
an der sich die Bauart entscheidet, ist die **parallelflankige radiale Nut**:
konstante Breite über dem Radius, also nach außen breiter werdende Zähne und
eine Zahnflussdichte, die am **Innenrand** kritisch ist.
