"""Eine von Hand konstruierte Technic-Greifhand als Pruefstein fuer die Bewertung.

Zweck: ``score.py`` muss an einem *bekannt guten* Modell bestehen, bevor es taugt,
generierte Entwuerfe zu beurteilen. Ein Bewertungsmassstab, der nie an etwas
Richtigem kalibriert wurde, misst nichts.

Aufbau (Technic, alles Standardteile):

* Handflaeche: ``32316`` technic beam 5 — Loecher entlang Z bei -40..+40 LDU,
  Lochachse in Y.
* Je Finger: ``3673`` technic pin in ein Handflaechenloch, darauf ein
  ``32523`` technic beam 3 als Fingerglied, optional ein zweites Glied.

Der Kniff: Pin- und Lochachse zeigen beide in Y, also bliebe ein direkt aufgestecktes
Fingerglied parallel zur Handflaeche liegen und mit dem Nachbarfinger kollidieren.
Die Finger werden deshalb um 90 Grad um die Pinachse gedreht angesetzt — das ist
derselbe Freiheitsgrad, den spaeter die Beugung nutzt.

Aufruf::

    python -m articulation.reference_hand -o data/reference_hand.ldr
"""

from __future__ import annotations

import argparse
from pathlib import Path

import bricknet
import numpy as np

PALM = "32316"  # technic beam 5
SEG = "32523"  # technic beam 3
PIN = "3673"  # technic pin


def _rot_y(theta: float) -> np.ndarray:
    c, s = np.cos(theta), np.sin(theta)
    return np.array([[c, 0, s, 0], [0, 1, 0, 0], [-s, 0, c, 0], [0, 0, 0, 1.0]])


def _ldr_line(color: int, T: np.ndarray, stem: str) -> str:
    m, t = T[:3, :3], T[:3, 3]
    return "1 %d %g %g %g %s %s.dat" % (
        color,
        t[0],
        t[1],
        t[2],
        " ".join(f"{x:g}" for x in m.flatten()),
        stem,
    )


def build(
    n_fingers: int = 3,
    segments: int = 2,
    spread_deg: float = 90.0,
    thumb: bool = True,
    thumb_hole: int = 3,
    thumb_spread_deg: float = -90.0,
) -> str:
    """LDraw-Text einer Greifhand: ``n_fingers`` Finger plus optional ein Daumen.

    Der Daumen ist der Grund, warum die Hand ueberhaupt greifen kann. Alle Loecher
    der Handflaeche liegen in einer Reihe und ihre Achsen sind parallel — Finger auf
    *derselben* Flaeche schwenken deshalb gleichsinnig und naehern sich nie; eine
    solche Hand ist ein Kamm, kein Greifer, und ``score.py`` gibt ihr korrekt einen
    Greifschluss von 0. Die Gegenflaeche hat die gespiegelte Lochachse (-Y statt +Y);
    ein dort angesetzter Daumen krummt sich bei gleichem Winkel entgegengesetzt und
    laeuft den Fingern entgegen.

    ``thumb_hole`` und ``thumb_spread_deg`` sind nicht geraten, sondern abgetastet:
    ueber alle Loecher der Gegenflaeche und Ansatzwinkel in 45-Grad-Schritten ist
    Loch 3 bei -90 Grad die einzige Kombination, die in Ruhelage kollisionsfrei ist
    *und* nennenswerten Greifschluss erreicht (22 %, Gesamtnote 0.16). Bei +90 Grad
    zeigt der Daumen mit den Fingern statt gegen sie und der Schluss faellt auf 0.
    """
    cat = bricknet.load_catalog()
    conns = bricknet.load_connectors()
    palm_holes = [v for k, v in conns[cat.stem_to_id[PALM]].items() if k[0] == "hole"][0]
    seg_holes = [v for k, v in conns[cat.stem_to_id[SEG]].items() if k[0] == "hole"][0]
    pin_conn = [v for k, v in conns[cat.stem_to_id[PIN]].items() if k[0] == "pin"][0]

    half = len(palm_holes) // 2
    front, back = palm_holes[:half], palm_holes[half:]
    picks = [
        (front, i, spread_deg) for i in np.linspace(0, half - 1, n_fingers).round().astype(int)
    ]
    if thumb:
        picks.append((back, min(thumb_hole, half - 1), thumb_spread_deg))

    lines = ["0 Referenz-Greifhand", "0 Name: reference_hand.ldr", _ldr_line(0, np.eye(4), PALM)]
    for k, (face, hi, turn_deg) in enumerate(picks):
        # Pin in das Handflaechenloch, dann das Glied um 90 Grad verdreht aufsetzen,
        # damit der Finger von der Handflaeche weg zeigt statt laengs zu liegen.
        anchor = face[hi] @ np.linalg.inv(pin_conn[0])
        lines.append(_ldr_line(4, anchor, PIN))
        frame = anchor @ pin_conn[1] @ _rot_y(np.deg2rad(turn_deg))
        for s in range(segments):
            seg_T = frame @ np.linalg.inv(seg_holes[0])
            lines.append(_ldr_line(14 + k, seg_T, SEG))
            if s + 1 < segments:
                # Naechstes Gelenk am aeusseren Loch desselben Glieds.
                joint = seg_T @ seg_holes[2] @ np.linalg.inv(pin_conn[0])
                lines.append(_ldr_line(4, joint, PIN))
                frame = joint @ pin_conn[1]
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-o", "--out", type=Path, default=Path("data/reference_hand.ldr"))
    ap.add_argument("--fingers", type=int, default=3)
    ap.add_argument("--segments", type=int, default=2)
    ap.add_argument("--spread", type=float, default=90.0, help="Ansatzwinkel der Finger in Grad")
    args = ap.parse_args()

    txt = build(args.fingers, args.segments, args.spread)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(txt)

    from . import pose as posing
    from . import sweep as sweeping

    g = bricknet.parse_ldr(txt)
    print(f"-> {args.out}")
    print(posing.summarize(g))
    coll = sweeping.check(g)
    print(f"Kollisionen in Ruhelage: {coll if coll else 'keine'}")


if __name__ == "__main__":
    main()
