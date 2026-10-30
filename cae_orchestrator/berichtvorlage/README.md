# Berichtsvorlage

LaTeX-Vorlage des Einzelberichts (`bericht.pdf`, `bericht_agentisch.pdf`), gerendert von `ema_report.render_pdf`.

| Datei | Inhalt |
|---|---|
| `kopf.tex` | Layout: Farben, Überschriften, Kopf-/Fußzeile (Projekt, Werkzeugstand, Seite x von y), Tabellen, `kennbox` |
| `titelseite.tex` | Titelseite mit Eckdaten, Kennzahlen und Inhaltsverzeichnis |

`@@FELD@@` füllt `ema_report.titelseite_tex` (Sonderzeichen werden für LaTeX maskiert; leere Felder entfallen nicht,
sondern zeigen „—“). Felder: `TITEL UNTERTITEL PROJEKT DATUM MASCHINE AUFGABE WERKZEUG MODELL KENNZAHLEN`.

Anpassen: Farben/Abstände in `kopf.tex`, Aufbau der Titelseite in `titelseite.tex`. Fehlt der Ordner oder bricht
das Rendern damit ab, fällt `render_pdf` auf das bisherige Layout zurück — ein Bericht scheitert nie an der Vorlage.
Vergleichs- und Studienberichte nutzen die Vorlage nicht (sie rendern kapitelweise).
