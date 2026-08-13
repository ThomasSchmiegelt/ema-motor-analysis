"""Bewegungsbereich eines Gelenks abfahren und je Pose auf Kollision pruefen.

Das ist das Gegenstueck zu BrickGPTs Stabilitaetspruefung: dort muss ein Entwurf
stehen bleiben, hier muss er sich *bewegen* lassen. Ein Entwurf gilt nur dann als
funktionale Mechanik, wenn seine Gelenke einen nennenswerten Winkelbereich
kollisionsfrei durchlaufen.

Die Kollisionsnetze sind um 0.25 LDU nach innen versetzt, damit eine regulaere
Steckverbindung nicht als Durchdringung zaehlt. Direkt verbundene Teilepaare werden
zusaetzlich ausgenommen: ein Pin *soll* im Loch stecken.
"""

from __future__ import annotations

from typing import Iterable, NamedTuple, Sequence

import bricknet
import numpy as np
from bricknet import collision

from . import pose as posing


class PoseResult(NamedTuple):
    """Ergebnis einer einzelnen Pose."""

    angle_deg: float
    collisions: tuple[tuple[int, int], ...]

    @property
    def ok(self) -> bool:
        return not self.collisions


def connected_pairs(graph: bricknet.Graph) -> set[tuple[int, int]]:
    """Teilepaare, die eine Kante teilen — legitime Beruehrung, keine Kollision."""
    return {
        (min(int(e["a"]), int(e["b"])), max(int(e["a"]), int(e["b"])))
        for e in graph.edges
    }


def check(graph: bricknet.Graph, *, ignore: set[tuple[int, int]] | None = None) -> tuple[tuple[int, int], ...]:
    """Kollidierende Teilepaare einer konkreten Pose."""
    mats = posing.realize(graph)
    pairs = collision.colliding_pairs(graph.part_ids, mats)
    skip = connected_pairs(graph) if ignore is None else ignore
    return tuple(
        (a, b) for a, b in ((min(p), max(p)) for p in pairs) if (a, b) not in skip
    )


def sweep(
    graph: bricknet.Graph,
    edge: int,
    angles_deg: Sequence[float],
    *,
    hold: dict[int, float] | None = None,
) -> list[PoseResult]:
    """Ein Gelenk ueber ``angles_deg`` fahren, je Pose auf Kollision pruefen.

    ``hold`` haelt weitere Gelenke auf festen Winkeln (Radiant) — noetig, um einen
    Finger im Kontext einer bereits geschlossenen Hand zu pruefen.
    """
    ignore = connected_pairs(graph)
    results = []
    for deg in angles_deg:
        angles = dict(hold or {})
        angles[edge] = np.deg2rad(deg)
        results.append(PoseResult(float(deg), check(posing.pose(graph, angles), ignore=ignore)))
    return results


def range_of_motion(
    graph: bricknet.Graph,
    edge: int,
    *,
    lo_deg: float = -120.0,
    hi_deg: float = 120.0,
    step_deg: float = 5.0,
    hold: dict[int, float] | None = None,
) -> tuple[float, float]:
    """Groesstes kollisionsfreies Winkelintervall, das die Ruhelage 0 enthaelt.

    Gibt ``(0.0, 0.0)`` zurueck, wenn schon die Ruhelage kollidiert — dann ist das
    Gelenk blockiert und der Entwurf als Mechanik unbrauchbar.
    """
    ignore = connected_pairs(graph)

    def free(deg: float) -> bool:
        angles = dict(hold or {})
        angles[edge] = np.deg2rad(deg)
        return not check(posing.pose(graph, angles), ignore=ignore)

    if not free(0.0):
        return (0.0, 0.0)

    bounds = []
    for direction, limit in ((-1.0, lo_deg), (+1.0, hi_deg)):
        reached = 0.0
        deg = 0.0
        while abs(deg) < abs(limit):
            deg += direction * step_deg
            if abs(deg) > abs(limit):
                deg = limit
            if not free(deg):
                break
            reached = deg
        bounds.append(reached)
    return (bounds[0], bounds[1])


def mobility_report(graph: bricknet.Graph, **kw) -> list[dict]:
    """Bewegungsbereich fuer jedes Gelenk des Graphen.

    Das Ergebnis trennt die eigentliche Mechanik von zufaelliger Gelenkgeometrie:
    ein Entwurf kann viele ``axle``-Kanten haben und trotzdem starr sein, wenn jede
    davon sofort blockiert.
    """
    rows = []
    for j in posing.joints(graph):
        lo, hi = range_of_motion(graph, j.edge, **kw)
        rows.append(
            {
                "edge": j.edge,
                "family": j.family,
                "parent": j.parent,
                "child": j.child,
                "lo_deg": lo,
                "hi_deg": hi,
                "span_deg": hi - lo,
            }
        )
    return rows


__all__ = [
    "PoseResult",
    "check",
    "connected_pairs",
    "mobility_report",
    "range_of_motion",
    "sweep",
]
