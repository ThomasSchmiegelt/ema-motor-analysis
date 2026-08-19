"""Bewerten, ob ein Entwurf eine *funktionale* Hand ist — nicht nur eine Ansammlung Steine.

BrickGPT prueft, ob ein Modell stehen bleibt. Fuer eine Roboterhand ist das zu wenig:
sie muss sich bewegen und greifen koennen. Dieses Modul misst genau das, und zwar
gegen die Kinematik der ORCA-Hand (17 DoF, ETH Zurich) als Vorlage — siehe
``reference/orca_spec.py``.

Vier Kriterien, alle aus dem Graphen berechenbar:

1. **Finger**   — Anzahl unabhaengiger Gelenkketten an einer gemeinsamen Wurzel.
2. **Tiefe**    — Gelenke je Kette in Reihe (ORCA: mindestens 2 Beugegelenke je Finger).
3. **Beweglichkeit** — kollisionsfreie Winkelspanne je Gelenk, relativ zu ORCAs
   medianer Beugespanne.
4. **Greifschluss** — laufen die Fingerspitzen beim Beugen zusammen? Ein Entwurf mit
   beweglichen Gelenken, die voneinander *weg* zeigen, ist keine Hand.

Der Gesamtwert ist bewusst ein Produkt: faellt ein Kriterium auf null, ist der
Entwurf keine Hand, egal wie gut die anderen sind.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import bricknet
import numpy as np

from . import pose as posing
from . import sweep as sweeping

SPEC_PATH = Path(__file__).resolve().parent.parent / "reference" / "orca" / "joint_spec.json"


def load_target(path: Path = SPEC_PATH) -> dict:
    """ORCA-Zielspezifikation laden (von ``reference/orca_spec.py`` erzeugt)."""
    return json.loads(path.read_text())["targets"]


@dataclass
class Chain:
    """Eine Gelenkkette ab der Handwurzel — der Kandidat fuer einen Finger."""

    parts: list[int]
    joints: list[int]
    spans_deg: list[float] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.joints)

    @property
    def tip(self) -> int:
        return self.parts[-1]


@dataclass
class HandScore:
    """Bewertungsergebnis mit allen Teilnoten — damit nachvollziehbar bleibt, woran es lag."""

    n_chains: int
    mean_depth: float
    mean_span_deg: float
    grip_closure: float
    chains: list[Chain]
    root: int

    digits: float = 0.0
    depth: float = 0.0
    mobility: float = 0.0
    grip: float = 0.0
    total: float = 0.0

    def report(self) -> str:
        lines = [
            f"Wurzel (Handflaeche): Teil {self.root}",
            f"{'Kriterium':<22}{'gemessen':>14}{'Note':>9}",
            "-" * 45,
            f"{'Finger (Ketten)':<22}{self.n_chains:>14}{self.digits:>9.2f}",
            f"{'Gelenke je Finger':<22}{self.mean_depth:>14.1f}{self.depth:>9.2f}",
            f"{'Beweglichkeit':<22}{self.mean_span_deg:>13.0f}°{self.mobility:>9.2f}",
            f"{'Greifschluss':<22}{self.grip_closure:>13.0%}{self.grip:>9.2f}",
            "-" * 45,
            f"{'GESAMT':<22}{'':>14}{self.total:>9.2f}",
        ]
        return "\n".join(lines)


def find_root(graph: bricknet.Graph) -> int:
    """Teil mit den meisten Gelenkverbindungen — die Handflaeche.

    Heuristik, aber eine belastbare: an der Handflaeche haengen alle Finger, also
    traegt sie die meisten Gelenkkanten. Bei Gleichstand gewinnt der niedrigere Index,
    damit das Ergebnis reproduzierbar bleibt.
    """
    deg: dict[int, int] = {}
    for j in posing.joints(graph):
        deg[j.parent] = deg.get(j.parent, 0) + 1
        deg[j.child] = deg.get(j.child, 0) + 1
    if not deg:
        return 0
    return min(deg, key=lambda p: (-deg[p], p))


def find_chains(graph: bricknet.Graph, root: int) -> list[Chain]:
    """Gelenkketten, die an ``root`` beginnen — je Kette ein Fingerkandidat.

    Ueber einen Breitensuchbaum ab der Wurzel: jedes Teil bekommt genau einen
    Elternteil und damit eine feste Tiefe, jede Kette ist der Weg von der Wurzel zu
    einem Blatt. Das ist entscheidend — ein naiver Lauf „immer weiter nach aussen"
    wandert ueber die Handflaeche in den *naechsten* Finger und meldet eine einzige
    Riesenkette statt fuenf Fingern.

    Mehrfachkanten zwischen denselben zwei Teilen (bei Technic ueblich: ein Pin
    greift mit beiden Enden) zaehlen als ein Gelenk.
    """
    adj: dict[int, list[tuple[int, int]]] = {}
    for j in posing.joints(graph):
        adj.setdefault(j.parent, []).append((j.child, j.edge))
        adj.setdefault(j.child, []).append((j.parent, j.edge))

    parent: dict[int, tuple[int, int]] = {}
    order = [root]
    seen = {root}
    while order:
        nxt = []
        for part in order:
            for child, edge in adj.get(part, ()):
                if child in seen:
                    continue
                seen.add(child)
                parent[child] = (part, edge)
                nxt.append(child)
        order = nxt

    inner = {p for p, _ in parent.values()}
    chains: list[Chain] = []
    for leaf in sorted(seen - inner - {root}):
        parts, joints_ = [leaf], []
        node = leaf
        while node != root:
            up, edge = parent[node]
            joints_.append(edge)
            parts.append(up)
            node = up
        chains.append(Chain(parts[::-1], joints_[::-1]))
    return chains


def grip_closure(graph: bricknet.Graph, chains: list[Chain], *, close_deg: float = 60.0) -> float:
    """Relative Annaeherung der Fingerspitzen beim Beugen.

    1.0 heisst, die Spitzen treffen sich; 0.0 heisst, sie bleiben gleich weit
    auseinander oder entfernen sich. Weniger als zwei Ketten ergeben keinen Griff.
    """
    if len(chains) < 2:
        return 0.0

    def spread(g: bricknet.Graph) -> float:
        pts = np.array([posing.tip_position(g, c.tip) for c in chains])
        return float(np.mean([np.linalg.norm(a - b) for i, a in enumerate(pts) for b in pts[i + 1 :]]))

    open_spread = spread(graph)
    if open_spread <= 1e-6:
        return 0.0
    # Alle Gelenke gleichsinnig beugen — die einfachste Greifbewegung.
    angles = {e: np.deg2rad(close_deg) for c in chains for e in c.joints}
    closed = spread(posing.pose(graph, angles))
    return float(np.clip((open_spread - closed) / open_spread, 0.0, 1.0))


def score(graph: bricknet.Graph, *, target: dict | None = None, step_deg: float = 15.0) -> HandScore:
    """Vollstaendige Bewertung eines Entwurfs gegen die ORCA-Zielkinematik."""
    tgt = target or load_target()
    root = find_root(graph)
    chains = find_chains(graph, root)

    for c in chains:
        c.spans_deg = [
            sweeping.range_of_motion(graph, e, step_deg=step_deg)[1]
            - sweeping.range_of_motion(graph, e, step_deg=step_deg)[0]
            for e in c.joints
        ]

    n = len(chains)
    mean_depth = float(np.mean([c.depth for c in chains])) if chains else 0.0
    all_spans = [s for c in chains for s in c.spans_deg]
    mean_span = float(np.mean(all_spans)) if all_spans else 0.0
    closure = grip_closure(graph, chains)

    s = HandScore(n, mean_depth, mean_span, closure, chains, root)
    s.digits = min(n / tgt["n_digits"], 1.0)
    s.depth = min(mean_depth / tgt["min_flexion_joints_per_digit"], 1.0)
    s.mobility = min(mean_span / tgt["median_flexion_span_deg"], 1.0)
    s.grip = closure
    # Produkt statt Mittel: eine Hand ohne Greifschluss ist keine Hand.
    s.total = s.digits * s.depth * s.mobility * s.grip
    return s


__all__ = ["Chain", "HandScore", "find_chains", "find_root", "grip_closure", "load_target", "score"]
