#!/usr/bin/env python3
"""Was in diesem Projekt schon gerechnet ist — als Stichpunkte fuer den Agenten.

Aufgerufen von ``start_hermes.sh``/``start_agent.sh`` beim Erzeugen von
``AGENTS.projekt.md``. Bewusst ein eigenes Skript und kein Here-Dokument im
Startskript: verschachtelte Anfuehrungszeichen in einem ``bash``-Here-Dokument sind
eine der zuverlaessigsten Fehlerquellen ueberhaupt, und ein Syntaxfehler dort haette
den ganzen Agentenstart lahmgelegt.

Der Inhalt kommt aus ``cae_orchestrator/ema_steckbrief.py`` — **derselben Quelle**,
aus der auch der Browserkopf seine Projektakte fuellt und aus der
``cae_cli.py steckbrief`` liest. Vorher stand hier eine eigene Kennwertliste; zwei
Auflegungen von „was weiss dieses Projekt" waeren zwei, die auseinanderlaufen, und
der Unterschied faellt erst auf, wenn der Terminalkopf etwas anderes glaubt als der
Browserkopf. Er beschreibt jetzt auch die MASCHINE (Art, Pole, Nuten, Bauraum,
Werkstoffe, Betriebspunkt), nicht nur ihre Kennwerte: auf „erstelle kurz einen
Steckbrief ueber das Projekt" beschrieb ein Agent am 04.09. das Monorepo, weil ihm
ueber die Maschine nichts vorlag.

Es MELDET nur und wertet nicht — was fehlt, steht als fehlend da. Ein Agent, der
glaubt, die Festigkeit sei gerechnet, waehrend die FEM still auf die analytische
Naeherung zurueckgefallen ist, zieht daraus falsche Schluesse; genau das ist in
diesem Repo schon dreimal unbemerkt passiert.

Aufruf: ``projektstand.py <projektordner>``. Ein Pfad auf eine ``results.json``
wird weiterhin angenommen (aeltere Startskripte gaben den) und auf ihren Ordner
zurueckgefuehrt.
"""

import os
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("- (kein Projekt angegeben)")
        return 2
    ziel = sys.argv[1]
    if os.path.isfile(ziel):            # alter Aufruf: Pfad auf results.json
        ziel = os.path.dirname(ziel)
    if not os.path.isdir(ziel):
        print(f"- Projektordner nicht gefunden: {ziel}")
        return 1

    sys.path.insert(0, os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "cae_orchestrator"))
    try:
        import ema_steckbrief
    except Exception as e:                                   # noqa: BLE001
        print(f"- Projektstand nicht lesbar ({type(e).__name__})")
        return 1
    print(ema_steckbrief.als_markdown(
        ema_steckbrief.steckbrief(ziel, mit_laeufen=True)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
