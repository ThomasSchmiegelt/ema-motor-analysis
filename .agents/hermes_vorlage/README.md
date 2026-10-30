# Vorlage fuer ein Hermes-Projekt

`start_hermes.sh` legt bei `--neu-projekt` ein frisches Projekt an und beschreibt dessen
`_agent/hermes/` aus dieser Vorlage:

* `memories/MEMORY.md` -- der Start-Speicher, EINMAL je Projekt kopiert (nur wenn dort noch keiner liegt).
  Er ersetzt den gemeinsamen Maschinenspeicher `~/.hermes/memories/`, der Erinnerungen aus fremden
  Aufgaben (Wasserstoff, Fusion, ...) in jede Auslegung hineintraegt.
* `toolsets` -- die Werkzeugsaetze, mit denen Hermes startet (`-t`). Ohne `web` und `browser`:
  dieses Setup spricht nur mit localhost.

Skills, `config.yaml` und `.env` werden NICHT kopiert, sondern verlinkt (eine Quelle, keine Drift).
Der Speicher darf kopiert werden: er ist Zustand des Projekts und waechst dort weiter.
