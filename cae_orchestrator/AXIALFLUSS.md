# Axialflussmaschine — Umsetzungsplan bis Stufe 4

**Stand 05.10.2026: Stufen 0, 1 und 2 sind gebaut, Stufen 3–4 nicht.** Dieses
Dokument ist der Plan; was davon steht, sagt die Spalte unten.

> **Zwei Angaben in §1 waren falsch und sind korrigiert** — beide erst beim Bauen
> von Stufe 1 aufgefallen, beide in `BEFUNDE.md` (05.10.2026): λ = 1/√3 ist
> **nicht herleitbar**, und der Kragstreifen in §1.7 war eine **untere**, keine
> obere Schranke. Die ursprünglichen Zahlen stehen dort zum Nachvollziehen.

| Stufe | Stand |
|---|---|
| **0 Tor** | ✅ gebaut — `ema_fluss.py`, `fluxPath` im Schema, Tor an drei Stellen, `test_fluss.py` 35/35 |
| **1 analytisch** | ✅ gebaut — `ema_axial.py` (Kreisringplatte, Anzug, Bandage, Zahnform, λ-Grenze), `test_axial.py` **69/69** |
| **2 feld** | ✅ gebaut — `ema_axial_fdm.py` (abgewickelter Mehrschnitt durch den **unveränderten** Haus-FDM), `test_axial_fdm.py` **46/46**. **Belastbar sind ψ und B_gap(r), das Moment NICHT** |
| 3 em3d | offen |
| 4 cad | offen |

Was das Werkzeug heute mit einer Axialflussmaschine tut, steht als
Befund in `BEFUNDE.md` (05.10.2026) — kurz: es rechnet sie als Radialflussmaschine
und beschriftet sie mit ihrem Namen, an zwölf Stellen, ohne Fehlermeldung.

Die Reihenfolge hier ist nicht verhandelbar: **das Tor kommt vor der ersten
Formel.** Ein Schemaschlüssel `fluxPath` ohne Tor wäre schlimmer als der heutige
Zustand, weil eine auswählbare Bauform behauptet, das Werkzeug trage sie.

---

## 1. Die Physik, die das Werkzeug nicht hat

### 1.1 Das Momentgesetz wechselt die Potenz

```
radial:  T = σ · R · (2πR·L)   = 2πσ R²L              ← ema_thermal.rated_torque ✓
axial:   T = σ · ∫ r·2πr dr    = 2πσ (Ro³−Ri³)/3      je Luftspalt
```

An der Vorgabegeometrie (Stator 280/190, Rotor 188,6, L = 80, water = 40 kPa),
axial mit Ro = 130 mm, λ = Ri/Ro = 0,577:

| | T_dauer | zu radial |
|---|---|---|
| radial, Paket 80 mm | 178,8 Nm | 1,00 |
| axial, 1 Spalt (einseitig) | 148,6 Nm | 0,83 |
| axial, 2 Spalte (YASA/TORUS/AFIR) | 297,2 Nm | **1,66** |

**Der Kreuzungspunkt liegt im Schema** (`axialLen` reicht bis 300 mm):

| L | T_radial | axial/radial |
|---|---|---|
| 40 mm | 89,4 Nm | 3,33 |
| 80 mm | 178,8 Nm | 1,66 |
| **133 mm** | 297,2 Nm | **1,00** |
| 200 mm | 447,0 Nm | 0,67 |
| 300 mm | 670,5 Nm | 0,44 |

Das ist die ganze Aussage über Axialfluss: er gewinnt am **flachen** Bauraum und
verliert am langen. Keine Bauform ist besser — das Seitenverhältnis entscheidet,
und genau diese Auskunft kann das Werkzeug heute nicht geben.

### 1.2 Zwei Momente über derselben Ringfläche — der Kern

`compute_performance` rechnet `psi_pm = p·(2/π)·B_gap·R_gap·L_ax`. Darin ist
`R_gap·L_ax` die **Flussfläche** (r¹-Gewichtung). Das Moment braucht die
r²-Gewichtung. Radial fallen beide auf `R_gap` zusammen; axial nicht:

| | radial | axial (2 Spalte) | Faktor |
|---|---|---|---|
| Flussfläche `R_gap·L` / `n(Ro²−Ri²)/2` | 75,44 cm² | 112,66 cm² | 1,49 |
| Momentintegral `R²L` / `n(Ro³−Ri³)/3` | 711 | 1183 | 1,66 |

Daraus folgt die Form von Stufe 0: **nicht ein Ersatzradius, sondern zwei
getrennte Integrale aus einer Funktion.** Wer sie zusammenlegt, hat danach
entweder `Kt` oder das thermische Dauermoment richtig, nie beide.

### 1.3 Teilungsverhältnis λ = Ri/Ro — ein neuer bindender Parameter

| λ | Ri | T (water, 2 Spalte) |
|---|---|---|
| 0,30 | 39,0 mm | 358,2 Nm |
| 0,50 | 65,0 mm | 322,1 Nm |
| **0,577** | 75,1 mm | **297,2 Nm** |
| 0,70 | 91,0 mm | 241,8 Nm |
| 0,80 | 104,0 mm | 179,6 Nm |

**Korrigiert am 05.10.2026.** Hier stand: „Mit endlichem Strombelag ergibt sich
λ = 1/√3 = 0,577." Das ist nicht herleitbar. Nachgerechnet:

```
T = 2πσ·Ro³·(1−λ³)/3   →   dT/dλ = −2πσ·Ro³·λ²  < 0  für jedes λ > 0
```

**monoton fallend, kein inneres Maximum.** Und σ ist über r konstant, solange der
Zahn keilförmig ist: der Leiterquerschnitt je Nut wächst mit der Nutteilung, also
mit r, und der Flächenstrombelag `K = J·swr·h_z` hängt damit **nicht** von r ab.

Der Literaturwert **λ = 1/3** stammt aus der Mitteldurchmesser-Näherung
`T ≈ σ·(π·D_m·L_e)·(D_m/2)`, und die liegt bei λ → 0 um **25 %** zu niedrig
(1,5708 gegen 2,0944 in Einheiten von σ·Ro³). Sie erzeugt damit ein Maximum, das
die Maschine nicht hat. **1/√3 = 0,5774 ist überhaupt keiner der beiden Werte.**

| λ | T_exakt/(σRo³) | T_Näherung | Näherung/exakt |
|---|---|---|---|
| 0,000 | 2,0944 | 1,5708 | 0,750 |
| **1/3** | 2,0168 | **1,8617** | 0,923 |
| 0,577 | 1,6913 | 1,6518 | 0,977 |
| 0,950 | 0,2987 | 0,2986 | 1,000 |

**Was λ wirklich bindet, ist die Zeichnung am Innenrand** (`ema_axial.lambda_grenze`):
dort wird die Nut zu schmal oder der Zahn zu dünn, beides aus `slots` und
`slotWidthRatio`. Gemessen bei Q = 48, swr = 0,5 und 2 mm Fertigungsboden:
**λ_min = 0,2351**, bindend die Nut; bei Q = 72 sind es 0,3526. Das beste λ ist
das kleinste **zeichenbare**, und welche Grenze bindet, wird genannt. Ein Optimum
entsteht erst durch ein **zweites** Ziel (Masse, Rückenblech, Durchbiegung) —
nicht durch das Moment allein.

### 1.4 Die Geometrie läuft mit dem Radius — kein Querschnitt stellt die Maschine dar

| r | Polteilung | Nutteilung | Spalt/Polteilung |
|---|---|---|---|
| 75,1 mm (Ri) | 78,60 mm | 8,73 mm | 0,0089 |
| 102,5 mm | 107,37 mm | 11,93 mm | 0,0065 |
| 130,0 mm (Ro) | 136,14 mm | 15,13 mm | 0,0051 |

Spalt/Polteilung — die einzige Kennzahl, die eine 2-D-Schnittrechnung bestimmt —
ändert sich über dem Radius um 1/λ = **1,73**. Deshalb ist die Feldstufe ein
**Quasi-3-D-Mehrschnitt**: k abgewickelte Zylinderschnitte, jeder ein *linearer*
2-D-Fall, Moment und Fluss über r summiert.

### 1.5 Zahnform entscheidet die Sättigung

`ema_saettigung` kürzt die Nutteilung heraus (`:52`, dokumentiert). Das gilt nur,
weil radial alle Zähne auf einem Radius sitzen:

| Zahnform | B_zahn(Ro) | B_zahn(Ri) |
|---|---|---|
| keilförmig (b ∝ r) | 1,299 T | 1,299 T |
| parallel (konstante Breite) | 1,299 T | **2,250 T** |

Bei parallelen Zähnen gilt B_zahn ∝ 1/r — der Innenrand sättigt um genau 1/λ
früher. Das ist ein **Tor**, keine Korrektur: ein paralleler Zahn in einer
Axialflussmaschine ist eine Auslegungsentscheidung mit einem Faktor 1,7 daran.

### 1.6 Die Last, die es radial nicht gibt

Aus dem Scheibenlauf (§4): ⟨B_n²⟩/2µ₀ = **345,8 kPa**, auf 353,7 cm²
= **12,23 kN axialer Anzug je Spalt** gegen 40 kPa momentbildende
Schubspannung — **8,6 : 1**. Bei zwei Spalten hebt es sich nur bei mittigem
Stator auf:

| Statorversatz | in % des Spalts | Restschub | in % einer Spaltkraft |
|---|---|---|---|
| 0,02 mm | 2 % | 0,98 kN | 8,0 % |
| 0,05 mm | 5 % | 2,46 kN | 20,1 % |
| 0,10 mm | 10 % | 4,99 kN | 40,8 % |
| 0,20 mm | 20 % | 10,62 kN | 86,8 % |

Die Kraft wirkt **in Richtung des Versatzes**: destabilisierend. Der Stator muss
sie als **Steifigkeit** aufbringen, nicht nur tragen. `ema_deck`, `ema_z88`,
`ema_aster` kennen Fliehkraft; eine Axiallast gibt es nirgends.

### 1.7 Polzahl und Scheibensteifigkeit koppeln gegensinnig

Das Rückenblech ist **magnetisch** bemessen (Φ/2 durch (Ro−Ri)·t bei B_fe ≤ 1,5 T)
und wird vom Anzug belastet:

| 2p | t magnetisch nötig | Durchbiegung (obere Schranke) | Anteil am 1-mm-Spalt |
|---|---|---|---|
| 8 | 25,70 mm | 0,001 mm | 0,1 % |
| 16 | 12,85 mm | 0,011 mm | 1,1 % |
| 24 | 8,57 mm | 0,037 mm | 3,7 % |
| 32 | 6,43 mm | 0,089 mm | 8,9 % |
| 40 | 5,14 mm | 0,173 mm | **17,3 %** |

**Korrigiert am 05.10.2026: der Kragstreifen war eine UNTERE Schranke, keine
obere.** Hier stand, die Zahlen seien obere Schranken, weil die Ringscheibe
umfangs mittrage. Der Denkfehler lag eine Ebene darunter: gerechnet war ein
Kragstreifen über dem **aktiven** Ring (Ro − Ri = 55 mm), die Scheibe ist aber an
der **Nabe** eingespannt. Der Hebel ist damit 100 mm statt 55 — (100/55)⁴ ≈ 11,
abzüglich der um 1/(1−ν²) höheren Plattensteifigkeit bleibt **Faktor 9**.

`ema_axial.ruecken` rechnet deshalb die **Kreisringplatte** (`_platte`,
achssymmetrische Plattengleichung, innen eingespannt, außen frei, Druck nur auf
dem aktiven Ring) und keine Schranke. Geprüft gegen den Kragstreifen im Grenzfall
des schmalen Rings (0,26 % bei 1 mm Ringbreite), Randrest ~1e-21, Linearität in q
exakt 2,000000 und in t exakt 8,000000 (`test_axial.py`). Gemessen mit magnetisch
bemessener Dicke, Nabe bei r = 30 mm:

| 2p | t magnetisch | w (Kreisringplatte) | Anteil am 1-mm-Spalt | *alt (Kragstreifen)* |
|---|---|---|---|---|
| 8 | 25,70 mm | 13,1 µm | 1,3 % | *1,4 µm* |
| 16 | 12,85 mm | **105,0 µm** | **10,5 %** | *11,1 µm* |
| 24 | 8,57 mm | 354,3 µm | 35,4 % | *37,5 µm* |
| 32 | 6,43 mm | 839,9 µm | 84,0 % | *88,8 µm* |
| 40 | 5,14 mm | 1640,4 µm | 164,0 % | *173,5 µm* |

Die Durchbiegung bindet also **viel früher** als hier stand. Zwei Aussagen kommen
dazu, und sie sind die eigentliche Auslegungsauskunft:

**Die Steifigkeitsforderung ist polzahlUNABHÄNGIG** — sie hängt am Druck und an
der Geometrie, nicht daran, wie sich der Fluss aufteilt; die magnetische fällt mit
der Polzahl. Deshalb **kreuzen** sie sich, und `ruecken()` sagt wo: mit Nabe bei
30 mm bindet der Fluss bis 2p = 8 und danach die Durchbiegung, mit einer Nabe bis
an Ri erst ab 2p = 40.

**Die Nabe ist der Haupthebel, nicht die Blechdicke.** Von 30 auf 75 mm
Einspannradius fällt die Durchbiegung um **Faktor 9** (105,0 → 11,1 µm bei
gleicher Dicke), die nötige Dicke für 10 % Spaltanteil von 13,06 auf 6,17 mm. Das
ist der Griff, den eine Auslegung zuerst anfassen sollte — `axialNabeD` ist
deshalb ein eigener Schemaparameter. Dieselbe Art „welche Grenze bindet"-Auskunft
wie `joch_bindet` beim Schenkelpol.

### 1.8 Magnethaltung: die Fliehkraft wechselt die Ebene

| 1/min | u bei Ro | Magnetsegment (99,5 g) | F_flieh |
|---|---|---|---|
| 3 000 | 40,8 m/s | | 1,01 kN |
| 6 000 | 81,7 m/s | | 4,03 kN |
| 12 000 | 163,4 m/s | | **16,11 kN** |

`ema_radien.magnethaltung()` gibt heute zwei Aussagen: Innenläufer → der Steg
hält, Außenläufer → der Ring hält. Axial gilt **keine von beiden**: der
Sektormagnet wird radial nach außen gezogen, **in der Scheibenebene**, und dort
ist kein Blech. Es hält nur Klebung oder eine Bandage am Außenrand — die am
größten Radius sitzt und unmagnetisch sein muss. Bei 12 000 1/min ist diese
Kraft größer als der axiale Anzug und hat kein tragendes Bauteil.

Derselbe Befundtyp wie bei der EESM: `rotor_layout_check` gab „Layout OK", weil
es Magnettaschen prüfte, die es dort nicht gab. Hier wäre es ein Stegtest an
einer Scheibe, die keinen Steg hat.

### 1.9 Die Blechung bestimmt die Fertigung

Radial: Bleche axial gestapelt, Fluss in der Blechebene — `ema_pipeline.LAMINATES`
beschreibt genau das. Axial steht der Zahnfluss **senkrecht** zur Ebene eines
flachen Blechstapels; das ist unzulässig. Drei Auswege:

| Kernart | Fluss | Folge |
|---|---|---|
| **bandgewickelt** (Spiralband) | umfangs + axial in Bandebene | nur TORUS-NN; Nuten nachträglich |
| **SMC** | isotrop | Zahnform frei; B_sat ~1,6 T, **Hystereseverlust hoch, Wirbelstromverlust niedrig** |
| **Segmentblech je Zahn** (radial orientiert) | in der Blechebene | ergibt den Keilzahn von selbst; 2p·3 Einzelteile |

`LAMINATES` ist der richtige Ort für SMC — aber `specific_loss_Wkg` als *eine*
Zahl trägt ein umgekehrtes Frequenzverhalten nicht. Das ist eine eigene,
kleine Erweiterung (Hysterese- und Wirbelstromanteil getrennt).

### 1.10 Die vier Bauformen

| Bauform | Spalte | Axialkraft | Joch | Bemerkung |
|---|---|---|---|---|
| **einseitig** | 1 | 12,2 kN **unausgeglichen aufs Lager** | Rotor + Stator | einfachste Fertigung, schlechteste Mechanik |
| **AFIR** (2 Stat., 1 Rot.) | 2 | hebt sich am Rotor auf | Rotor jochlos möglich | Wicklung außen → gut kühlbar |
| **TORUS-NN** (2 Rot., 1 Stat.) | 2 | hebt sich am Stator auf | Stator braucht Umfangsjoch | bandgewickelter Toroid |
| **YASA / TORUS-NS** | 2 | hebt sich am Stator auf | **Stator jochlos** | höchste Momentdichte, schwierigste Kühlung |

**Mehrstufig** stapelt n Einheiten: T linear, Durchmesser gleich — der einzige
Weg zu *langen* Axialflussmaschinen, und er kostet n Sätze Lager und Toleranzen.

Kühlung: beim YASA sitzt der verlustreichste Teil zwischen zwei rotierenden
Scheiben, der Wärmepfad geht über die Zahnstirnseiten nach außen oder mit Öl.
`ema_thermal`s LPTN ist ein Schalennetz von innen nach außen — hier nicht falsch
parametriert, sondern die falsche **Topologie**. Beim AFIR liegt die Wicklung
außen, und das ist ein Vorteil, den der σ-Ansatz gar nicht abbilden kann, weil σ
dort an der Kühlart hängt und nicht an der Bauform.

### 1.11 Maschinenart × Flussweg ist nicht voll besetzt

| Art | axial | warum |
|---|---|---|
| **PSM** | ✅ die beherrschende Form | YASA/TORUS/AFIR, Sektormagnete flach auf der Scheibe |
| **GSM** | ✅ klassisch | der **Scheibenläufer** mit gedrucktem/eisenlosem Anker ist historisch *die* Axialflussmaschine — kein Rastmoment, kleinste Trägheit |
| **EESM** | ⚠️ möglich, selten | Ringerregerspule axial, Schleifringe wie bisher |
| **ASM** | ⚠️ schlecht | Scheibenkäfig schwer herstellbar, Schlupfverlust in der schlechtest gekühlten Scheibe |
| **SynRM** | ❌ praktisch nicht | Anisotropie braucht orientiertes Blech in einer Scheibe — nicht blechbar |

Bemerkenswert: die **GSM** hat axial eine klassische Bauform, ist aber die
einzige Art ohne Feldstufe (`feldweg="keiner"`, kommutierter Anker ist nicht
magnetostatisch). Der eisenlose Scheibenanker ändert daran nichts — die
Begründung bleibt, und sie bleibt richtig.

---

## 2. Stufe 0 — das Tor (vor allem anderen) — **GEBAUT 05.10.2026**

Abnahme gemessen: `test_fluss.py` **35/35**; `test_radien.py` 38/38, `test_maschinenart.py` 129/129, `test_cae_cli.py`, `test_topology.py` und `smoke_test.py` **23/23** unverändert. `flaechen()` gibt für den Radialfall ziffernweise `r_gap_m*L` und `(rotorOD/2)²*L` zurück, `psi_pm` und `rated_torque` kommen hindurch unverändert heraus (178,8 Nm bleibt 178,8 Nm). Axialfluss wird an allen fünf Stufen abgewiesen.

Zwei Dinge sind beim Bauen dazugekommen, die im Plan nicht standen:

- **`_validate` ließ `fluxPath` fallen** (alle `adv`-Schlüssel werden übersprungen). Ein axialer Payload aus Text→Auslegung oder `ema_design_ai` wäre damit still radial geworden — und dann hätte das Tor nie gefeuert. Jetzt wird er durchgereicht, nach demselben Muster wie `rotorPosition` und mit derselben Begründung; `_validate({})` bleibt dabei unverändert lang.
- **Ein Befund**: `rated_torque` nimmt am Außenläufer `rotorOD/2` statt der Spaltfläche, gemessen **+22,5 %** Dauermoment. Siehe `BEFUNDE.md` (05.10.2026) — nicht repariert, weil die Invarianzbedingung von Stufe 0 Vorrang hat.

**Was entsteht.** `ema_fluss.py`, nach dem Muster von `ema_radien`: nicht „ist es
axial", sondern die Größen selbst, damit die Aufrufer den Flussweg nicht kennen
müssen.

```python
FLUSSWEGE   = ("radial", "axial")
VORGABE     = "radial"
STUFEN_AXIAL = ()          # ehrlich: heute keine

def flussweg(quelle) -> str                  # geom["fluxPath"], unbekannt -> radial
def pruefe_flussweg(quelle, stufe) -> str    # sonst FlusswegNichtUnterstuetzt
def flaechen(geom) -> dict:
    """A_fluss (r¹) und A_moment (r²) -- GETRENNT, weil sie es axial sind
    und radial nur zufaellig zusammenfallen.

    radial:  A_fluss = R_gap*L          A_moment = R_gap**2 * L
    axial:   A_fluss = n*(Ro^2-Ri^2)/2  A_moment = n*(Ro^3-Ri^3)/3
    """
def traeger(geom) -> dict    # welches Bauteil die Luftspaltkraft traegt
```

Dazu:
- `fluxPath` als Enum in `ema_text2ema.SCHEMA` (`geom: True`, zunächst `adv: True`)
- `ema_fluss.py` in `ema_werkzeugstand._MODULE` eintragen (Pflichtstelle — eine
  Änderung daran bewegt eine Kennzahl)
- `pruefe_flussweg` an die Stufeneingänge, wie `pruefe_bauform` in
  `ema_em2d_harm:814` und `ema_em3d_harm:754`
- `ema_grenzen`: der Flussweg gehört zu den Toren, die **immer** gelten
- `test_fluss.py` nach dem Muster von `test_radien.py`

**Abnahme, messbar.**
1. Alle bestehenden Tests laufen **unverändert** durch (`smoke_test.py`,
   `test_topology.py`, `test_radien.py`, `test_maschinenart.py`, …).
2. `flaechen()` gibt für jeden radialen Payload **ziffernweise** `R_gap*L` und
   `R_gap²*L` zurück — die Invarianzprobe, ohne die Stufe 1 nicht beginnen darf.
3. `fluxPath=axial` wird an jeder Stufe mit **benanntem Grund** abgewiesen; kein
   Pipelinelauf endet mit `done`.

**Aufwand:** klein. Ein Modul, ein Test, ein Schemaschlüssel, ~8 Aufrufstellen.
**Gewinn sofort:** ein begründetes Nein statt zwölf plausibler falscher Zahlen.

---

## 3. Stufe 1 — analytisch — **GEBAUT 05.10.2026**

Abnahme gemessen: `test_axial.py` **69/69**, `test_fluss.py` 35/35, dazu `test_radien` 38/38, `test_maschinenart` 129/129, `test_saettigung`, `test_zyklen` 116/116, `test_paarvergleich` 102/102, `test_cae_cli`, `test_topology` und `smoke_test` **23/23** unverändert. **178,8 Nm radial bleibt 178,8 Nm**: `psi_pm` ist über 216 geprüfte Geometrien bitgleich, `rated_torque` innerhalb eines ulp (2,0e-16 relativ — die Multiplikationsreihenfolge ändert sich, der Wert nicht).

Entstanden ist `ema_axial.py` mit `auslegung`, `lambda_grenze`, `zahnform`, `anzug`, `_platte`, `ruecken`, `bandage`, `moment`, `uebersicht`. Umgebaut: `compute_performance` und `rated_torque` gehen durch `ema_fluss.flaechen`. Neue Tore: `rotor_layout_check`, `rotor_stress_check` und `ema_saettigung.bewerten` weisen Axialfluss ab und **nennen die Funktion, die es rechnet** — statt eine Ringspannung auf eine Scheibe oder eine gekürzte Nutteilung auf zwei Radien anzuwenden.

**Was NICHT getragen ist:** `screen`, `paarvergleich`, `steckbrief` und `sicherheit` sind radial verdrahtet (Zylindervolumen, Magnettaschen, LPTN-Schalennetz). Sie gehören zur analytischen Stufe, aber nicht zu `ema_axial`, und sie sind **nicht** axial gebaut — wer sie braucht, baut sie; bis dahin ist `ema_axial.uebersicht` die Auskunft.

**Was entsteht.** `ema_axial.py` — und zwar nach der Hausregel, dass jede Größe
sagt, welche Grenze bindet:

| Funktion | gibt heraus |
|---|---|
| `auslegung(geom)` | Ro, Ri aus λ, n_spalte, Bauform (einseitig/afir/torus/yasa), Stufenzahl |
| `moment(geom, sigma)` | über `ema_fluss.flaechen()["A_moment"]` |
| `ruecken(geom)` | t magnetisch **und** t aus der Durchbiegung — `rueckenblech_bindet` sagt, welche (§1.7) |
| `anzug(geom, B_gap)` | Anzug je Spalt, Restschub über Versatz, **destabilisierend ja/nein** (§1.6) |
| `bandage(geom, rpm)` | Fliehkraft in der Scheibenebene; sagt ausdrücklich, dass **kein Steg** sie trägt (§1.8) |
| `zahnform(geom)` | B_zahn(Ri) gegen B_zahn(Ro); Tor bei parallelem Zahn (§1.5) |
| `lambda_aus_fenster(geom)` | λ aus dem **gezeichneten** Wickelfenster, nicht aus der Literatur |

**Umbauten am Bestehenden** (die riskante Hälfte):
- `compute_performance` → `psi_pm` über `flaechen()["A_fluss"]`
- `ema_thermal.rated_torque` → über `flaechen()["A_moment"]`
- `ema_saettigung` → Zahnform-Zweig; die Kürzung bleibt für radial wörtlich
- `ema_analysis.luftspalt_mm` / `r_gap_m` → über `ema_fluss`
- `ema_rotorcheck` → Scheibenzweig: Axialzug + Bandage statt Lamé-Ring + Steg
- `ema_maschinenart` × `ema_fluss`: die Matrix aus §1.11 als Tabelle, mit
  `ohne_bedeutung` für die Kennzahlen, die axial nicht gebildet werden

**Was danach trägt:** `paarvergleich`, `screen`, `rotor-check`, `sicherheit`,
`steckbrief`, `zyklus`, `getriebe`, `zielwert`, `studie`, `aehnlich`. Letzteres
ohne Zutun: λ und n_spalte sind schon dimensionslos, also genau die Features, mit
denen `aehnlich` vergleicht.

**Abnahme, messbar.**
1. **178,8 Nm bleibt 178,8 Nm** — jede radiale Kennzahl jedes Bestandsprojekts
   ziffernweise unverändert (`test_flaechen_invarianz.py`).
2. Die 297,2 Nm aus §1.1 kommen aus dem Werkzeug, nicht aus einem Skript.
3. `rotor-check` nennt bei 12 000 1/min die **Bandage** als bindend, nicht den Steg.
4. `ruecken()` nennt bei 2p = 40 die **Durchbiegung** als bindend, nicht den Fluss.
5. Eine SynRM mit `fluxPath=axial` wird abgewiesen, eine PSM nicht.

**Aufwand:** mittel bis groß, und der Umbau ist die Arbeit, nicht das neue Modul.

---

## 4. Stufe 2 — Feld: Quasi-3-D-Mehrschnitt — **GEBAUT 05.10.2026**

Abnahme gemessen: `test_axial_fdm.py` **46/46**; nutloser Ständer gibt
Grundwelle/Spitze **1,2622** gegen 4/π = 1,2732 (0,9 %), Linearitätsprobe exakt
2,000000, Leerlaufmoment −0,55 Nm gegen −311,6 Nm unter Last, Carterfaktor
gemessen 1,03 / 1,09 / 1,19 über die Nutbreite. Die übrige Suite unverändert
(`smoke_test` 23/23, `test_axial` 69/69, `test_fluss` 36/36).

**Drei Dinge kamen anders heraus als geplant** — alle drei in `BEFUNDE.md`:

- **ψ konvergiert über der Schnittzahl (16,0 → 0,14 %), das Moment nicht.** ψ
  hängt an EINEM geeichten Feld, die Maxwellsche Schubspannung am Produkt zweier
  unabhängig geeichter. Der Plan nannte die Momentreihe als Abnahme — gemessen
  ist ψ der belastbare Teil, und das steht in jeder Ausgabe.
- **Zwei Momentwege, Faktor ~3 auseinander**, über den Strom konstant — ein
  Normierungsunterschied (ψ auf 1 Windung/Nut, `_analytical_Barm` auf
  `N_ph = slots/3`; vgl. `ema_asm.k_norm`). Nicht aufgelöst: das entscheidet
  Stufe 3 und nicht ein Korrekturfaktor.
- **Das quadratische Gitter wird mit EISEN gepolstert, nicht mit Luft.** Mit Luft
  hängt das Ergebnis an der Fensterbreite und konvergiert nicht (0,864 → 0,824 T
  über Faktor 4); mit Eisen sind es 1,29 %. Alle Schnitte teilen dieselbe Breite,
  damit der stufige Wechsel nicht als Sprung in die Schnittreihe geht.

**Das Tor folgt dem ASM-Muster:** `STUFEN_AXIAL` trägt `feld`, aber
`FELDWEG_AXIAL = fdm_scheibe` — die Pipeline fragt
`ema_fluss.pruefe_feldweg(data, fdm)` und weist die Scheibe weiterhin ab, mit der
Adresse des richtigen Werkzeugs. Ohne das hätte „feld trägt“ geheißen, die
radiale FDM dürfe eine Scheibe rechnen.

**Die gute Nachricht zuerst.** `_build_fv_matrix(mu)` und `_solve_fdm(mu, J)`
nehmen nur Material- und Stromfelder auf einem gleichmäßigen kartesischen Gitter;
sie kennen keinen Radius. **Gemessen** (abgewickelte Scheibe, r = 102,5 mm,
2p = 16, 400×400, Luftspalt 5 px, unveränderte Hausfunktionen):

```
Permeanz hm/(hm+µr·kc·g)  0,8325  →  B_an 0,9573 T
B_axial Spitze            0,9573 T
B_axial Grundwelle        1,2098 T  = 1,264 × Spitze   (4/π = 1,273 → nahezu rechteckig)
B_tangential Spitze       0,3839 T  (40,1 % der Normalkomponente)
Klirranteil               42,6 %
Linearitätsprobe J → 2J   2,000000 × A
```

Radiusgebunden sind nur `_rasterise` und `_sample_airgap`. **Die Feldstufe wäre
damit die billigste im ganzen Werkzeug**, nicht die teuerste: fünf Schnitte sind
fünf FDM-Läufe, also Sekunden.

Nachrechenbar: `PYTHONPATH=. venv/bin/python axialfluss_scheibenprobe.py`
(Probe, ausdruecklich kein Test — ein gruener Test waere die Aussage „wird
getragen", und Stufe 0 weist heute richtigerweise ab).

**Der eine Trick, der dokumentiert werden muss.** Fenster = **genau ganzzahlige
Polteilungen**, Polgrenze bei x = 0. Dann ist Dirichlet A = 0 am Seitenrand die
*richtige* Bedingung (A ~ sin(πx/τ) hat dort Nullen) und nicht nur eine weit
genug entfernte — der Hausrand bleibt unverändert, es braucht kein periodisches
Verfahren.

**Was entsteht.** `ema_axial_fdm.py`:

```python
def rastere_scheibe(geom, r_mm, N) -> (mu, J)   # abgewickelt: x = Umfang, y = axial
def sample_spalt(A, ...)            -> (B_n(x), B_t(x))
def felder(geom, k_schnitte=5)      -> dict     # Summe über r: T, psi, B_gap(r), Oberwellen
```

**Was noch fehlt und benannt werden muss:** `_analytical_Bgap` kennt keinen
axialen Spalt, und der FDM eicht seine Amplitude darauf (`sf = B_analytical /
pk_fdm`). Es braucht einen axialen Zweig in `zielfeld_luftspalt` — mit derselben
Permeanzbeziehung, aber dem axialen Spalt. Sonst passiert genau das, was am
20.09.2026 bei fünf Bauarten passierte: der Löser rechnet die richtige Geometrie
und meldet trotzdem die PSM-Zahl.

**Abnahme, messbar.**
1. Nutloser Stator: Grundwelle/Spitze = 1,26…1,27 gegen 4/π = 1,273.
2. Linearitätsprobe exakt 2,000000.
3. **Schnittkonvergenz als Zahl**, nicht als Annahme: T(k=3), T(k=5), T(k=9).
4. Gegenprobe gegen Stufe 1 an dem Punkt, an dem beide gelten müssen.
5. Ein `feldbild`-Gegenstück: Schnittbilder plus die Kurve B_gap(r).

**Ehrliche Grenze:** der Mehrschnitt vernachlässigt die radiale Streuung an Ri
und Ro und die radialen Stromkomponenten im Wickelkopf. Typisch wenige Prozent
auf das Moment bei moderatem λ — **nachzumessen an Stufe 3, nicht anzunehmen.**

**Aufwand:** klein bis mittel. Der Löser ist da.

---

## 5. Stufe 3 — 3-D-Feld (Elmer)

**Hier läuft der Hausbefund mit dem Strich statt gegen ihn.** `ema_em3d_harm`
baut Scheiben eines Querschnitts, weil *„radiale Auflösung kostet DREIECKE,
axiale nur LAGEN"* — so wurden aus 166 614 Elementen mit einer Lage im 0,7-mm-Spalt
59 796 Knoten mit zwei.

**Bei Axialfluss liegt der Spalt in der Extrusionsrichtung.** Er wird also von
Natur aus durch Lagen aufgelöst. Die Netzebene ist ein r-θ-Ringsektor, dessen
kleinstes Merkmal die Zahnkante ist — Millimeter, nicht 0,7 mm. Die schwerste
3-D-Einschränkung des Werkzeugs (*„der 0,7-mm-Luftspalt ist in einem bezahlbaren
3-D-Netz nicht auflösbar"*, weshalb die Ringzahl nur eine untere Schranke ist)
**gilt axial nicht.** Das ist der erste Ort im Werkzeug, an dem eine absolute
Luftspaltamplitude in 3-D belastbar wäre.

**Was entsteht.** `ema_em3d_axial.py`: ein Polpaarsektor der Scheibe, Prismen
axial gestapelt, Periodizität am Sektorrand. `--nur-netz` sagt wie bei `feld3d`,
was ein Lauf kostet, bevor er gestartet wird.

**Abnahme, messbar.** Knotenzahl und Laufzeit aufgeschrieben; Linearitätsprobe;
Momentvergleich gegen Stufe 2; und die eine saubere Grenzprobe: **λ → 1**
(schmaler Ringraum) muss gegen den Mehrschnitt konvergieren, weil die radiale
Variation dann verschwindet. Wie beim Kurzschlussring gilt: eine getragene Stufe
ist keine Zusicherung über jede Zahl, die aus ihr fällt — was sie **nicht** gibt,
steht als Warnung an jedem Lauf.

**Aufwand:** mittel.

---

## 6. Stufe 4 — CAD und Struktur

**Was entsteht.** `ema_axial_cad.py` als **Quelle**, nicht als Zeichnung — nach
der Regel, die `ema_laeuferbild` seit dem 20.09.2026 trägt: eine Teileliste, aus
der Leinwand, FDM-Raster und FreeCAD gleichzeitig bauen. Vier Abschriften einer
Geometrie wären vier Gelegenheiten zum Auseinanderlaufen.

- **FreeCAD:** Sektormagnete, Keilzähne, Segmentkerne, Rückenblechscheiben
- **`ema_deck` (Gmsh + CalculiX):** die Scheibe unter **Axialzug** — ein *neuer
  Lastfall*. Heute gibt es nur Fliehkraft.
- **`ema_z88` / `ema_aster`:** zweite und dritte Meinung. Hier sogar leichter als
  radial: Z88 hat **keine Fliehkraft** (sein `OMEGA` ist der SOR-Relaxationsfaktor),
  ein axialer Flächendruck ist dagegen eine gewöhnliche Last.
- **Der Lastfall ist zweiteilig und muss es bleiben:** Anzug (statisch,
  destabilisierend) **und** Fliehkraft in der Scheibenebene (§1.8). Sie wirken
  senkrecht zueinander; eine zusammengefasste Vergleichsspannung verschweigt,
  welche bindet.

**Abnahme, messbar.** Ein echter FreeCAD-Bau; Rotorvolumen gegen die gezeichnete
Fläche auf 0,00 % — dieselbe Probe, die `ema_synrm_cad` bestanden hat. Und
`u_max` aus ccx gegen Aster, mit der Erwartung aus dem Hausbefund: zwei korrekte
direkte Löser auf **einem** Tet4-Netz müssen auf Rundungsfehler übereinstimmen;
eine bitgleiche Zahl wäre die verdächtige.

**Aufwand:** groß — und der Großteil davon ist Oberfläche, nicht Physik (§7).

---

## 7. Oberfläche: **kein neues Tab.** Drei Stellen.

Zur direkten Frage: ein eigenes Geometrie-Tab wäre ein Fehler. Drei Gründe, alle
am Bestand ablesbar.

**1. Die Tableiste hat eine Grammatik, und Flussweg passt nicht darin.**
`ema.html:241–262` führt **22 Tabs**: ① Projekt → ② Geometrie → ③ Betrieb →
④ Berechnung sind *Schritte*, der Rest sind *Werkzeuge* (Designer, STEP-Import,
Getriebe, 3D-Feld, Öl, CFD, FluidX3D, Bericht, KI, Jobs, Agenten). Der Flussweg
ist keins von beidem — er ist eine **Eigenschaft der Maschine**, genau wie
`machineType`, und `machineType` steht in ② Geometrie. Ein 23. Tab, das nur
manchmal gilt, macht die Leiste für jeden schlechter.

**2. Der Mechanismus ist schon da und getestet.** `ema.html:794–1002` trägt
`class="art-feld" data-arten="asm eesm gsm"`, und `_updateArtVis()`
(`:13703–13725`) blendet nach `machine_art` ein und aus — mit der ausgesprochenen
Begründung: *„Ein Ankerwerkstoff an einer Asynchronmaschine wäre ein Feld ohne
Wirkung, und ein wirkungsloses Feld liest sich wie ein defektes."* Genau das gilt
für `statorID` und `rotorOD` an einer Scheibe. Der Umbau ist entsprechend klein:

- `_updateArtVis()` → `_updateVis()`, liest **beide** Selektoren
- `data-fluss="radial"` an die rein radialen Felder (`statorID`, `rotorOD`),
  `data-fluss="axial"` an eine neue Gruppe `grp_axial`
  (Ro, λ, n_spalte, Bauform, t_magnet, t_ruecken, Zahnform, Kernart, Stufen)
- Beschriftungen, die ihre Bedeutung wechseln, nicht ihren Schlüssel:
  `axialLen` → „Baulänge", `slotDepth` → „Zahnlänge (axial)"
- `fluxPath` kommt aus `/param_schema` wie `machineType`, über **dieselbe**
  `_ART_FELDER`-Tabelle — keine zweite Quelle

**3. Ein zweites Geometrie-Tab wäre eine zweite Quelle für dieselben Werte.**
Polzahl, Nuten, Wicklung, Werkstoffe, Umrichter, Kühlung gelten für beide
Flusswege — rund vierzig Felder. Sie zweimal zu führen ist genau die Drift, gegen
die dieses Repo überall gebaut ist (`_ART_FELDER` als *eine* Tabelle für Python
und JS; `test_topology.py`, das die JS-Abschrift festnagelt; `ema_laeufer.js`,
das keine Geometrie enthält, weil `ema.html` schon eine handgespiegelte Fassung
hält und `CLAUDE.md` sie die gefährlichste Stelle im Werkzeug nennt).

### Wo wirklich etwas Neues hin muss: der Designer

Der **einzige** echte Oberflächenbedarf. Heute ist `panel-designer`
(`ema.html:1443`) eine radiale Querschnittsleinwand mit `dsn_statorOD`,
`dsn_rotorOD`, `dsn_airgap` — und ein radialer Querschnitt **stellt eine
Axialflussmaschine nicht dar** (§1.4). Axial braucht es zwei Ansichten:

| Ansicht | zeigt | wozu |
|---|---|---|
| **r-z-Halbschnitt** | den Stapel: Scheibe, Magnet, Spalt, Stator, Spalt, Magnet, Scheibe | Bauform, Spaltzahl, Dicken, der Anzugspfad |
| **abgewickelte Scheibe** bei wählbarem r | Pole, Zähne, Nuten auf diesem Radius | ist **dasselbe Objekt**, das Stufe 2 rechnet |

Dass die zweite Ansicht und das Feldmodell derselbe Gegenstand sind, ist der
Gewinn: der Radiusschieber zeigt unmittelbar, wie Spalt/Polteilung über r
wandert (1,73 über λ = 0,577) — die Kerneinsicht wird sichtbar statt erklärt.

Das wird eine **Ansichtsumschaltung im Designer**, kein neues Tab. Und der Hebel
dafür ist schon gebaut: `ema_laeufer.js` ist absichtlich dünn — *„Python schickt
Zahlen, JavaScript malt."* Die axiale Zeichnung geht über **dieselbe** Route
`POST /laeuferbild` und dieselbe `teile()`-Quelle, erweitert um einen
Rahmenvermerk je Teil (`rahmen: "r_theta" | "r_z" | "abgewickelt"`). Damit liegt
der Großteil der Zeichenarbeit in Python, und die eine handgespiegelte
`magnetLegs`-Fassung in JS wird nicht angefasst.

### Drei kleine Dinge, die nicht vergessen werden dürfen

- **Das Nein muss sichtbar sein.** Stufe 0 weist ab — und eine Abweisung, die
  unten an einen langen Kasten gehängt wird, steht außerhalb des Bildes. Sie
  gehört in denselben Torkasten („DAS HILFT") mit konkreten Vorschlägen: *auf
  radial zurückstellen*, *auf eine Stufe gehen, die es trägt*.
- **Live-Vorschau (▶) und 3D-Feld (🧲)** brauchen kein Tab, nur den axialen
  Rasterzweig; die `--guete`-Voreinstellungen (`ema_text2ema.GUETE`) gelten
  unverändert, weil sie Auflösung und nicht Geometrie setzen.
- **`feldbild`** bekommt eine neue Bildart: B_gap über dem Radius. Das ist die
  Kurve, die radial eine Konstante ist und axial die Auslegung entscheidet.

---

## 8. Risiken, und was zuerst schiefgeht

1. **Der Umbau von `compute_performance` und `rated_torque` verschiebt Zahlen
   bestehender Projekte**, falls `flaechen()` den Radialfall nicht ziffernweise
   reproduziert. Das ist das größte Risiko des ganzen Plans. Gegenmittel: die
   Invarianzprobe als **erste** Abnahme von Stufe 0, nicht als letzte von Stufe 1.
   Beide Module stehen in `ema_werkzeugstand._MODULE` — der Fingerabdruck meldet
   die Änderung an jeder gespeicherten Rechnung, und das arbeitet hier für uns.
2. **Die Eichung auf `_analytical_Bgap`** ist die Stelle, an der am 20.09.2026
   fünf Bauarten dieselbe Zahl meldeten, obwohl der Löser längst richtig rechnete.
   Axial wird derselbe Fehler gemacht, wenn `zielfeld_luftspalt` keinen axialen
   Zweig bekommt — und er fällt genauso wenig auf.
3. **λ aus der Literatur statt aus dem Wickelfenster** wäre eine Konstante von
   der Art der flachen 20 % Kurzschlussringzuschlag, die `feld3d` um mindestens
   das Dreifache widerlegt hat.
4. **Die Durchbiegung als obere Schranke** (§1.7) darf nicht als Ergebnis
   auftreten. Entweder die Ringscheibenlösung oder ein Deck-Lauf — oder die Zahl
   trägt ausdrücklich „obere Schranke" mit sich, wie die Ringzahl in `feld3d`.
5. **Die Bandage (§1.8) ist ein Bauteil, das es im Werkzeug nicht gibt** — wie
   die Polbefestigung vor dem 19.09.2026. Ohne sie bekommt eine Scheibe bei
   12 000 1/min ein „Layout OK" und hat 16,11 kN ohne tragendes Teil.

## 9. Was dieser Plan absichtlich offen lässt

- **Welche Bauform zuerst.** YASA hat die höchste Momentdichte und die
  schwierigste Kühlung, AFIR ist mechanisch und thermisch gutmütiger. Das ist
  eine Auslegungsentscheidung, keine Reihenfolge im Code.
- **SMC-Verlustmodell.** `specific_loss_Wkg` als eine Zahl trägt das umgekehrte
  Frequenzverhalten nicht (§1.9); ob das eine Erweiterung von `LAMINATES` oder
  ein eigener Zweig wird, entscheidet die erste echte SMC-Auslegung.
- **Mehrstufige Maschinen** (n Einheiten auf einer Welle) sind in Stufe 1 ein
  Faktor und in Stufe 4 eine Baugruppe. Ob sie überhaupt gebraucht werden, sagt
  der Kreuzungspunkt aus §1.1 am konkreten Bauraum.
- **Die Lagerung.** Beim einseitigen Aufbau liegen 12,2 kN dauerhaft am Lager.
  Das ist eine Lebensdauerfrage, und das Werkzeug rechnet heute keine Lager —
  auch nicht radial.
