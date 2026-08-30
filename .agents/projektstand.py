#!/usr/bin/env python3
"""Was in diesem Projekt schon gerechnet ist — als Stichpunkte fuer den Agenten.

Aufgerufen von ``start_hermes.sh``/``start_agent.sh`` beim Erzeugen von
``AGENTS.projekt.md``. Bewusst ein eigenes Skript und kein Here-Dokument im
Startskript: verschachtelte Anfuehrungszeichen in einem ``bash``-Here-Dokument sind
eine der zuverlaessigsten Fehlerquellen ueberhaupt, und ein Syntaxfehler dort haette
den ganzen Agentenstart lahmgelegt.

Es MELDET nur und wertet nicht — was fehlt, steht als fehlend da. Ein Agent, der
glaubt, die Festigkeit sei gerechnet, waehrend die FEM still auf die analytische
Naeherung zurueckgefallen ist, zieht daraus falsche Schluesse; genau das ist in
diesem Repo schon dreimal unbemerkt passiert.
"""

import json
import sys

# Kennwerte, die einen Entwurf beschreiben — knapp gehalten, der Projektblock soll
# den Kontext des Modells nicht auffressen.
KENNWERTE = [
    ("B_gap_T", "Luftspaltflussdichte [T]"),
    ("Kt_Nm_per_A", "Momentkonstante [Nm/A]"),
    ("T_max_Nm", "Spitzenmoment [Nm]"),
    ("P_max_kW", "Spitzenleistung [kW]"),
    ("max_safe_rpm", "hoechste sichere Drehzahl [1/min]"),
    ("safety_factor_fem", "Sicherheit aus der FEM"),
    ("structural_basis", "Grundlage der Festigkeit"),
    ("T_magnet_C", "Magnettemperatur [C]"),
    ("T_winding_C", "Wicklungstemperatur [C]"),
]

STUFEN = [("em", "EM-Feld"), ("structural", "Festigkeit"),
          ("thermal", "Thermik"), ("cycle", "Fahrzyklus")]


def main() -> int:
    try:
        with open(sys.argv[1], encoding="utf-8") as f:
            erg = json.load(f)
    except Exception as e:                                   # noqa: BLE001
        print(f"- results.json nicht lesbar: {type(e).__name__}")
        return 1

    zus = erg.get("summary") or {}
    zeilen = [f"- {text}: {zus[k]}" for k, text in KENNWERTE if zus.get(k) is not None]
    print("\n".join(zeilen) if zeilen else "- (keine Kennwerte in results.json)")

    fehlt = [text for k, text in STUFEN if not erg.get(k)]
    if fehlt:
        print("- NOCH NICHT gerechnet: " + ", ".join(fehlt))

    # Der wichtigste Einzelhinweis. `structural_basis == "analytisch"` heisst, dass
    # die FEM NICHT gelaufen ist und die Zahl aus der Ringformel kommt — sie sieht
    # aber genauso aus wie ein FEM-Ergebnis.
    if zus.get("structural_basis") == "analytisch":
        print("- ACHTUNG: die Festigkeitszahl ist ANALYTISCH, die FEM ist nicht "
              "gelaufen. Sie kennt die Spannungsspitzen an den Stegen nicht.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
