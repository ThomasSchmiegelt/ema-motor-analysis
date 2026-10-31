---
name: picogk
description: Baut Voxel- und Implizitgeometrie über die PicoGK-Web-API (pikogk/picogk_cli.py) und legt sie als STL ab. Verwenden bei TPMS-/Gyroid-Kernen, Wärmetauscher- und Kühlkernen, Gitterstrukturen, Düsen, Zylinderkopf-Bauteilen oder wenn nach PicoGK, ShapeKernel, LatticeLibrary oder einer Freiform gefragt wird. NICHT für E-Maschinen-Auslegung — dafür ist cae-orchestrator zuständig.
---

# PicoGK bedienen

Zweiter, unabhängiger Geometrieweg neben FreeCAD: **Voxel und implizite Flächen**
statt Flächenmodell. Gut für Dinge, die ein Flächenmodell schlecht beschreibt —
Gyroide, Gitter, Wärmetauscherkerne, verwundene Kanäle. Schlecht für alles, was
hinterher in ein FEM-Netz muss: das Ergebnis ist eine Dreieckshülle, kein
Volumennetz, und der Elmer-/CalculiX-Weg der Rechenkette fängt sie nicht auf.

**Es gibt keine Verbindung zum CAE-Orchestrator.** Kein Verb, keine Route, kein
Import. Was hier entsteht, ist eine STL-Datei auf der Platte und sonst nichts.

```bash
cd ~/ai-workspace/pikogk
python3 picogk_cli.py <verb> ...
```

## Zuerst immer

```bash
python3 picogk_cli.py health
```

Exit-Codes: `0` ok · `1` Fehler der Gegenstelle · `2` Bedienfehler · `3` Server aus ·
`4` Zeitüberschreitung. **Am Code entscheiden, nicht am Text.**

Exit 3 heißt: Server starten und ~15 s warten.

```bash
cd ~/ai-workspace/pikogk && ./start.sh
```

## Verben

| Verb | Zweck |
|---|---|
| `health` | Erreichbarkeit, Anzahl und Namen der geladenen Formen |
| `formen` | alle Formen mit Parametern, Vorgabewerten, Grenzen, Auswahllisten |
| `erzeuge --typ <name> --set k=v ...` | eine Form bauen, STL ablegen, Dreiecke und Hüllquader melden |
| `deuten "<freitext>"` | Freitext durch das lokale Modell in Typ + Werte übersetzen |
| `hol <pfad> --ziel <datei>` | eine erzeugte Datei abholen |

```bash
python3 picogk_cli.py formen
python3 picogk_cli.py erzeuge --typ cylinder --set radius=15 --set height=80
python3 picogk_cli.py erzeuge --typ tpmsring \
    --set innerRadius=40 --set outerRadius=70 --set height=25 \
    --set unitSize=8 --set wallThickness=1 --set pattern=1 --ziel /tmp/kern.stl
```

## Was `deuten` ist und was nicht

`deuten` fragt das lokale Modell, welche Form ein Freitext beschreibt und mit welchen
Werten. Das ist ein **Vorschlag**, keine Auslegung. Das Modell rechnet die Maße nicht,
es liest sie aus dem Satz — und rechnet dabei gelegentlich mit, etwa Durchmesser in
Radius. Gemessen: „eine Düse, Einlass 12 mm, Auslass 30 mm, 90 mm lang" ergibt
`inletRadius 6, outletRadius 15, convergingLength 45, divergingLength 45`. Die
Halbierung ist richtig, die Aufteilung der 90 mm auf konvergent/divergent ist geraten.

**Also: Werte ansehen, dann `erzeuge` aufrufen.** `--und-erzeuge` baut ungeprüft und
ist für den Fall gedacht, dass die Form egal ist.

Ist das Modell nicht geladen, antwortet `deuten` mit Exit 1 und HTTP 502. Der erste
Aufruf nach einem Serverstart kann das treffen: ein kalter Ladevorgang des Modells
dauert länger als das Zeitlimit der Route. Einfach nochmal aufrufen — beim zweiten Mal
liegt es im Speicher (gemessen 2,3 s gegen 20 s Zeitlimit). Das Modell kommt aus
`CAE_LLM_MODEL`; ist der Tag bei Ollama nicht vorhanden, nennt das Serverprotokoll ihn.

## TPMS-Kerne (`tpmsring`)

Ringförmiger Wärmetauscherkern aus einer dreifach periodischen Minimalfläche. Baut auf
LEAP 71s ShapeKernel und LatticeLibrary auf, nicht auf eigener Geometrie.

`pattern`: `0` Gyroid kartesisch · `1` Gyroid **radial** · `2` Schwarz-Diamant ·
`3` Schwarz-Primitiv · `4` Lidinoid.

**In einen Ring gehört das radiale Muster.** Ein kartesisches Gyroid wird von der
Bohrung beliebig angeschnitten: die Zellenzahl pro Umlauf fällt aus dem x/y-Gitter und
das Muster schließt sich nicht. Die radiale Fassung nimmt eine ganze Zahl Zellen pro
Umlauf; `unitSize` bleibt eine Kantenlänge in mm und die Zahl wird am mittleren Radius
daraus abgeleitet.

Drei Grenzen werden vorher geprüft und mit Begründung abgewiesen, nicht erst beim Netz:

* **Wandstärke unter zwei Voxeln** (0,5 mm bei 0,25 mm Voxelgröße). Eine dünnere Wand
  kommt nicht dünn heraus, sondern als Löcher — die Fläche fällt zwischen die
  Gitterpunkte.
* **Ringbreite kleiner als eine Zelle.** Darin steht keine vollständige Zelle.
* **Wandstärke ab der halben Zellgröße.** Dann wächst die Fläche zu und der Kern wird massiv.

## Kosten, bevor du es startest

Die Gegenstelle bricht eine Erzeugung nach **60 s** ab. Teuer ist nicht das Bauteil,
sondern sein **Hüllquader**: die implizite Fläche wird je Voxel darin ausgewertet, also
wächst der Aufwand mit dem Quadrat des Außenradius mal der Höhe, nicht mit dem Material.

Gemessen auf diesem Rechner (0,25 mm Voxel):

| Ring | Hüllquader | Zeit | Dreiecke | STL |
|---|---|---|---|---|
| Ri 10, Ro 20, h 10, Zelle 5 | 2,6 Mio Voxel | 0,7 s | 0,6 Mio | 31 MB |
| Ri 30, Ro 50, h 15, Zelle 8 (Vorgabe) | 9,6 Mio Voxel | 3,7 s | 2,9 Mio | 146 MB |
| Ri 40, Ro 70, h 25, Zelle 8 | 31 Mio Voxel | 9,2 s | 10,2 Mio | 509 MB |
| Ri 60, Ro 110, h 50, Zelle 10 | 96 Mio Voxel | 50,2 s | 39,0 Mio | 1,95 GB |

**Die Datei ist das Problem, nicht die Zeit.** Der letzte Fall lief in 50 s durch und
schrieb 1,95 GB; gelöscht wird in `PicoGKWebApi/output/` nichts. Deshalb wird oberhalb
von geschätzt 8 Mio Dreiecken abgewiesen, und die Meldung nennt die geschätzte
Dateigröße. Billiger wird es über eine größere Zelle oder eine kleinere Höhe (beide
gehen linear ein) als über den Außenradius.

## Fallen

* **Ein Auftrag zur Zeit.** PicoGK erlaubt eine Library je Prozess; alle Aufträge
  laufen seriell über einen Worker. Zwei gleichzeitige Aufrufe werden nacheinander
  bedient, nicht parallel.
* **Der Server braucht ein X-Display** (`DISPLAY`, Vorgabe `:1`) und ein vorhandenes
  `~/Documents` — PicoGK legt sein Protokoll dort ab und bricht beim Start ab, wenn der
  Ordner fehlt. Das trifft jedes neue Benutzerkonto.
* **Wird das Viewer-Fenster geschlossen, ist der Worker tot** und jede Erzeugung
  antwortet mit HTTP 503. Dann hilft nur ein Neustart des Servers.
* **`voxIntersectImplicit` von PicoGK beendet bei dieser Voxelgröße den ganzen
  Serverprozess** (Einheitenfehler im nativen Teil, mm in einen Voxelzähler). Nicht
  benutzen; `TpmsRingGeometry.voxBuild` zeigt im Kommentar, wie es stattdessen geht.
  Wenn ein Aufruf den Server ohne Fehlermeldung verschwinden lässt, ist das der
  erste Verdacht — im Serverprotokoll steht dann `terminate called after throwing`.
* **Kein Zugriffsschutz, kein TLS.** Lokal gedacht. Nicht ins Netz hängen.

## Weiterlesen

* `pikogk/INTEGRATION.md` — der HTTP-Vertrag, falls ein Verb nicht reicht
* `pikogk/EXPERIENCE_REPORT.md` — wie der Linux-Bau zustande kam, mit allen Hürden
* `pikogk/THIRD-PARTY-NOTICES.md` — die mitgelieferten LEAP-71-Bibliotheken und ihre Lizenz
