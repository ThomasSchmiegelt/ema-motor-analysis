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
| `pruefe.js` | misst den Löser **ohne Browser** nach: `node pruefe.js` |

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
