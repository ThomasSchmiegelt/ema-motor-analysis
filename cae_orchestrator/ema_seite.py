# -*- coding: utf-8 -*-
"""Die ausgelieferte Oberflaeche als EIN Text -- fuer alles, was sie LIEST.

``ema.html`` war 16.096 Zeilen gross, davon 11.568 JavaScript in zwei
``<script>``-Bloecken. Seit dem 16.10.2026 liegt das JavaScript in
``oberflaeche/*.js`` und wird von der Seite in einer festgelegten Reihenfolge
eingebunden (``oberflaeche/LIESMICH.md`` sagt, in welcher und warum).

**Warum dieses Modul ueberhaupt:** elf Tests lesen die Seite als Text und
suchen darin -- nach einer Elementkennung, nach einem Funktionsnamen, nach
einem Satz, nach dem Spiegelblock von ``magnet_legs``. Haetten sie nach der
Aufteilung weiter ``ema.html`` gelesen, waeren sie nicht rot geworden, sondern
**gruen und blind**: die gesuchte Zeichenkette steht dann einfach nicht mehr
da, und ein ``in``-Test auf etwas Abwesendes meldet keinen Fehler, sondern
schweigt. Genau diese Sorte stiller Luecke soll ein Test nicht haben.

Deshalb EINE Stelle, die weiss, woraus die Seite besteht. Kommt eine Datei
dazu, erscheint sie hier und damit in allen elf Tests zugleich; ein zweiter
Dateiname in einem Test waere die naechste Abschrift, die auseinanderlaeuft.

Gelesen wird die Reihenfolge aus der SEITE (``<script src="/oberflaeche/…">``)
und nicht aus einer Liste daneben -- eine Liste daneben waere wieder eine
zweite Wahrheit ueber dieselbe Sache.
"""

from __future__ import annotations

import io
import os
import re

HIER = os.path.dirname(os.path.abspath(__file__))
SEITE = os.path.join(HIER, "ema.html")
SKRIPT_ORDNER = os.path.join(HIER, "oberflaeche")

_SRC = re.compile(r'<script\s+src="/oberflaeche/([A-Za-z0-9_.-]+)"')


def skriptnamen() -> list[str]:
    """Die Skriptdateien in der Reihenfolge, in der die Seite sie laedt."""
    html = io.open(SEITE, encoding="utf-8").read()
    return _SRC.findall(html)


def skripte() -> str:
    """Nur das JavaScript, in Ladereihenfolge aneinandergehaengt."""
    teile = []
    for name in skriptnamen():
        pfad = os.path.join(SKRIPT_ORDNER, name)
        teile.append(f"\n// ===== {name} =====\n")
        teile.append(io.open(pfad, encoding="utf-8").read())
    return "".join(teile)


def quelltext() -> str:
    """Markup, Stil und JavaScript zusammen -- was der Browser wirklich sieht.

    Die Skripte stehen am Ende, also dort, wo sie frueher auch standen; wer im
    Text nach einer Reihenfolge sucht (``_html.split("function pjSetActive")``
    und dergleichen), bekommt damit dasselbe wie vorher.
    """
    return io.open(SEITE, encoding="utf-8").read() + skripte()
