# `oberflaeche/` — das JavaScript der Hauptmaske

Bis zum 16.10.2026 stand hier nichts: `ema.html` war **16.096 Zeilen**, davon

| Abschnitt | Zeilen |
|---|---:|
| `<style>` | 242 |
| Markup (21 Reiter-Panels + Modale) | 4.275 |
| `<script>` 1 (Masken-Logik) | 9.802 |
| `<script>` 2 (Live-Vorschau, Kapsel) | 1.766 |

**72 % der Datei waren JavaScript.** Jetzt liegt es hier, in sechzehn Dateien;
`ema.html` ist auf 4.549 Zeilen Markup und Stil geschrumpft.

Es ist eine reine **Verschiebung**: keine Zeile Logik wurde geändert, kein
Baumschritt kam dazu, kein Modulsystem. Das sind klassische Skripte — sie
teilen sich einen globalen Gültigkeitsbereich, genau wie vorher der eine große
Block, und `onclick="sendChat()"` im Markup findet seine Funktion weiterhin.

## Reihenfolge ist Bedeutung

Die Seite lädt sie in dieser Reihenfolge:

```
rahmen.js · nebenreiter.js · vergleich.js · animation.js · projekt.js
berechnung.js · designer.js · getriebe_import.js · feld3d.js · kuehlung.js
bericht.js · chat.js · formular.js · ergebnis.js · verdrahtung.js · sim.js
```

Zwei Stellen hängen wirklich daran, und beide sind gemessen und nicht vermutet:

1. **`verdrahtung.js` muss hinter alle anderen.** In EINEM `<script>` durfte
   `document.getElementById('btn_analyse').addEventListener('click', startAnalysis)`
   ganz oben stehen, obwohl `startAnalysis` tausend Zeilen weiter unten steht —
   Funktionsdeklarationen werden **innerhalb eines Skripts** hochgezogen. Über
   mehrere Dateien verteilt gilt das nicht mehr. Dreizehn solcher Zuweisungen
   gab es; sie stehen jetzt dort und nirgends sonst.
2. **`sim.js` zuletzt.** Es ruft am Ende sein eigenes `init()` und startet die
   Zeichenschleife; es liest dabei `_ptabSchema` (aus `vergleich.js`) und hängt
   sich an Formularfelder.

Alles andere in diesen Dateien sind Deklarationen — sie laufen erst, wenn
jemand einen Knopf drückt.

## Was wohin gehört

| Datei | Inhalt |
|---|---|
| `rahmen.js` | Reiterleiste, Flussweg radial/axial, Vorschau der Scheibe, Deep-Link |
| `nebenreiter.js` | 🧠 KI-Training und ⏳ Jobs — zwei Reiter, die nur zusehen |
| `vergleich.js` | ⚖ Vergleich, Variantensätze, Parametertabelle |
| `animation.js` | Feldanimation, Laufzeitschätzer, Voreinstellungen Entwurf/Detail |
| `projekt.js` | ① Projekt: Akte, Auftrag, Papierkorb, Galerie, Wissensbasis, Speichern |
| `berechnung.js` | Zielwertoptimierung, Parameterstudie |
| `designer.js` | Leinwand-Designer und der KI-Entwurfspfad |
| `getriebe_import.js` | ⚙ Getriebe, 📥 STEP-Import |
| `feld3d.js` | 🧲 3D-Feld samt vtk.js-Betrachter und Abspieler |
| `kuehlung.js` | 💧 Mantaflow, 🌊 OpenFOAM, 🌀 FluidX3D, 🧪 Spray-Prüfstand |
| `bericht.js` | 📝 selbst geschriebener Bericht |
| `chat.js` | Ergebnis-Chat |
| `formular.js` | `buildPayload`/`applyPayload`, Brücke, Abzweige, Lauf-Start, Torvorschläge |
| `ergebnis.js` | der Ergebnisreiter — reine Darstellung |
| `verdrahtung.js` | die Knöpfe an ihre Funktionen, und sonst nichts |
| `sim.js` | die Live-Vorschau als Kapsel, samt Spiegel von `magnet_legs` |

## Drei Dinge, die man dabei leicht übersieht

- **Der Spiegel von `ema_topology.magnet_legs`** steht in `sim.js` zwischen
  `<<MIRROR-START>>` und `<<MIRROR-END>>`. `test_topology.py` schneidet den
  Block heraus und fährt ihn mit `node` gegen die Python-Fassung. Wer dort
  etwas ändert, ändert beide Seiten oder keine.
- **Wer die Seite als Text liest, liest sie über `ema_seite.quelltext()`** und
  nicht über `open("ema.html")`. Elf Tests tun das. Täten sie es weiter direkt,
  wären sie nach dieser Aufteilung nicht rot, sondern **grün und blind** — eine
  gesuchte Zeichenkette, die nicht mehr in der Datei steht, meldet keinen
  Fehler, sie fehlt einfach.
- **Eine neue Datei gehört in drei Listen**: in die `<script src>`-Folge in
  `ema.html` (daraus liest `ema_seite` die Reihenfolge), und in
  `ema_werkzeugstand.OBERFLAECHE` + `_AUSGELIEFERT` — sonst meldet
  `/oberflaeche` einen Stand, der einen Teil der Seite nicht kennt, und eine
  stundenlang offene Agentenseite erfährt nicht, dass sie veraltet ist.

Ausgeliefert werden sie über `GET /oberflaeche/<datei>` (`server.py`, Muster
wie `/axialfluss/<datei>`: nur echte Dateien, nur harmlose Namen,
`Cache-Control: no-cache`).
