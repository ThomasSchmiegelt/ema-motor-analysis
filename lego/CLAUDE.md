# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

Ergaenzt die Wurzel-`CLAUDE.md` des Monorepos. Projektuebersicht und Quellenlage
stehen in `README.md` — hier nur, was beim Arbeiten im Code sonst teuer neu
herzuleiten waere.

## Umgebung

Jeder Aufruf braucht drei Dinge, sonst schlaegt er unauffaellig fehl:

```bash
source .venv/bin/activate
export BRICKNET_DATA="$PWD/data/bricknet"      # sonst laedt bricknet Meshes ins Home
export LDRAW_LIBRARY_PATH="$PWD/data/ldraw"
```

Ohne `BRICKNET_DATA` findet die Kollisionspruefung keine Netze und meldet stumm
*keine* Kollision — das ist der gefaehrlichste Fehlerfall im Projekt, weil er wie ein
gutes Ergebnis aussieht.

Kein sudo. `uv` und `winetricks` liegen in `~/.local/bin`.

## bricknet-API — die nicht offensichtlichen Stellen

Die Bibliothek ist gut, aber ihre Datenstrukturen sind an mehreren Punkten anders,
als die Namen vermuten lassen:

* `graph.edges` ist ein **numpy structured array**, kein Iterable von `Edge`-Objekten.
  Felder: `a, b, a_conn, b_conn, family, yaw, flip, rot`. `family` ist ein String
  (`stud`/`hinge`/`axle`/`ball`/`fixed`). `type(e).__name__` liefert `void`, nicht die
  Kantenklasse — immer `e['family']` benutzen.
* `decode_graph(graph)` gibt eine **Liste von 4x4-Matrizen je Teil** zurueck, nicht
  je Komponente. `T[part_index]` ist die Pose.
* `parse_sample(text)` liefert ein `ParseResult` mit `.tree` und `.error` — nicht
  direkt einen `Tree`.
* Konnektoren: `load_connectors()` ist nach **Teile-ID** (int) geschluesselt, nicht
  nach Stem. Weg dorthin: `load_catalog().stem_to_id['3673']`. Der Wert ist
  `{(subtype, polarity): array_of_4x4}` — der erste Tupelteil ist der **Subtyp**
  (`pin`, `hole`, `cross`, `socket`, `stud`, …), nicht die Familie.
* Freiheitsgrade je Familie: `axle` → `rot[0]` Drehung + `yaw` Verschiebung (LDU),
  `hinge` → `yaw` Winkel, `ball` → `rot[0..2]`. Siehe `articulation/pose.py`.

## Probentext: ungerade Zeilenzahl, gesetzter Wurzelknoten

Das Textformat ist Zeile 0 = Wurzelknoten `a`, danach **Paare** aus Knoten- und
Kantenzeile. Eine vollstaendige Probe hat damit immer eine **ungerade** Zeilenzahl.
Zwei Fehler daraus haben je eine ganze Generierung wertlos gemacht (beide gefixt,
13.08.2026 — an `data/out_pt.jsonl` und `data/out.jsonl` nachgemessen):

* **Abbruch auf gerader Zeilenzahl.** `StopAfterNewlines` erzwingt EOS nach N
  Zeilenumbruechen; bei geradem N haengt der letzte Knoten ohne Kante und
  `parse_sample` verwirft die **komplette** Probe (`dangling node without edge`) —
  59 gute Zeilen fallen wegen einer halben. War 0/16 parsebar; N wird jetzt intern
  auf ungerade aufgerundet ⇒ 15/16.
* **Fehlender Wurzelknoten im Bedingungsmodus.** Der `--prompts_file`-Pfad gab dem
  Modell nur die Bildunterschrift und schrieb `text = generated`. Das Modell setzt
  eine *begonnene* Probe fort: ohne gesetztes `a` faengt es bei `b` an, jede Kante
  auf `a` haengt in der Luft, 0/4 parsebar. Der Wurzelknoten (`--prompt`, Standard
  `a`) gehoert in **beide** Modi in den Prompt UND vor den Probentext; die
  Bildunterschrift ist Kontext und gehoert **nicht** in den Text.

`eval/score_samples.py` kuerzt beim Einlesen trotzdem auf die letzte vollstaendige
Form (nur kuerzen, nie ergaenzen) und weist die Quote **roh vs. repariert** getrennt
aus — sonst geht ein Abbruchfehler des Erzeugers als Modellqualitaet durch.

## Technic-Geometrie, die man sonst dreimal falsch macht

* Ein Technic-Balken hat seine Loecher entlang **Z**, die Lochachse zeigt in **Y**.
  Die Konnektorliste enthaelt **beide Seiten**: bei `32316` (beam 5) sind Index 0–4
  die Vorderseite (Achse +Y), 5–9 die Rueckseite (Achse −Y).
* Pin- und Lochachse zeigen beide in Y. Ein direkt aufgestecktes Folgeglied bleibt
  deshalb **parallel** zum Traeger liegen und kollidiert mit dem Nachbarn. Glieder
  muessen um 90 Grad um die Pinachse gedreht angesetzt werden — mit derselben
  Rotation, die spaeter die Beugung nutzt (`_rot_y` in `reference_hand.py`).
* Finger auf **derselben** Handflaechenseite haben parallele Drehachsen, schwenken
  gleichsinnig und koennen nie greifen. Opposition entsteht nur ueber die
  Gegenflaeche mit gespiegelter Lochachse.

## Bewertung

`articulation/score.py` multipliziert vier Teilnoten (Finger, Tiefe, Beweglichkeit,
Greifschluss) statt zu mitteln — faellt eine auf null, ist der Entwurf keine Hand.
Bezugsgroessen kommen aus `reference/orca/joint_spec.json`.

Kalibriert an `articulation/reference_hand.py`. **Jede Aenderung an der Bewertung
muss dort gegengeprueft werden**: eine Hand ohne opponierten Daumen muss 0.00
bekommen, die Referenzhand rund 0.16. Ein Massstab, der beide gleich bewertet, ist
kaputt — das ist genau der Fehler, der beim Aufbau zuerst auftrat.

`sweep.check()` nimmt direkt verbundene Teilepaare aus: ein Pin *soll* im Loch
stecken. Die Netze sind zusaetzlich um 0.25 LDU nach innen versetzt.

`range_of_motion` prueft den **ganzen** Graphen: eine Durchdringung irgendwo im
Modell setzt die Beweglichkeit **jedes** Gelenks auf 0. Bei erzeugten Proben ist das
der Normalfall (13 bzw. 28 durchdringende Paare im Mittel), deshalb fuehrt
`eval/score_samples.py` `n_collisions_rest` mit — ohne diese Zahl sieht eine
Beweglichkeit von 0 nach kaputtem Massstab aus statt nach kaputtem Entwurf.

**Bekannte Schwaeche des Massstabs (gemessen, noch offen).** `depth` und `mobility`
sind auf 1.0 gedeckelt (`min(x/ziel, 1)`). Eine erzeugte Probe aus zwei langen
Ketten duenner Stangen (22 + 8 Gelenke, 236° mittlere Spanne) zieht damit beide
Teilnoten auf Anschlag und kommt auf **0.24** — mehr als die handgebaute Referenzhand
(0.16), obwohl sie eine Peitsche ist und keine Hand. Eine Obergrenze fuer die
Kettenlaenge oder eine Bestrafung ueberlanger Ketten fehlt. Wer das anfasst: die
Referenzhand muss ihre 0.16 behalten und der Kamm seine 0.00.

## Studio 2.0 unter Wine

Eigener Prefix in `data/wine-studio`, nie `~/.wine`. Installiert unter
`drive_c/Program Files/Studio 2.0/Studio.exe`. Rolle: Betrachter, Bauanleitung,
Teileliste — **nicht** Datenquelle; `.io` wird bewusst nicht geparst.

`corefonts` braucht `cabextract`, das ohne sudo fehlt; die 200 kopierten
Systemschriften genuegen. Beim Schreiben von Wine-Skripten: `find | head | while`
reisst unter `set -o pipefail` das Skript ab (SIGPIPE) — `mapfile` benutzen.

## Offen

* Massstab gegen ueberlange Ketten haerten (s. oben, „Bekannte Schwaeche").
* `corpus/` — OMR-Sets (Direktdownload liefert 404, braucht Scraper ueber die
  Set-Seiten) und Studio-Exporte zu Pfadtext.
* `train/` — LoRA auf `kulits/BrickNet-1.7B-PT`; 0.6B/1.7B laufen bequem auf der 3090.
* BrickNet-Datensaetze sind gated (Formular, s. `README.md`) — nur fuer Grosstraining
  noetig, nicht fuer die Bibliothek.
