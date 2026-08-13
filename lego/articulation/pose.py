"""Gelenke eines BrickNet-Graphen finden, stellen und als LDraw realisieren.

Grundlage, an einem Technic-Pin im Balkenloch (3673 in 32523) empirisch verifiziert:
bricknet parst die Verbindung als Kante mit ``family='axle'``. Deren ``rot[0]`` ist die
Rotation um die Pinachse, ``yaw`` die Verschiebung laengs der Achse in LDU. Ein
Fingergelenk ist damit ein einziger Kantenparameter — Stellen heisst, den Parameter zu
setzen und den Graphen neu zu realisieren.

Freiheitsgrade je Kantenfamilie (vgl. BrickNet DATA.md):

===========  ====================================================
family       stellbare Groessen
===========  ====================================================
``axle``     ``rot[0]`` Rotation (rad), ``yaw`` Verschiebung (LDU)
``hinge``    ``yaw`` Winkel (rad)
``ball``     ``rot[0..2]`` xyz-Eulerwinkel (rad)
===========  ====================================================
"""

from __future__ import annotations

import dataclasses
from typing import Iterable, Mapping, NamedTuple

import bricknet
import numpy as np

#: Kantenfamilien, die einen Freiheitsgrad tragen. ``stud`` und ``fixed`` sind starr.
JOINT_FAMILIES = ("axle", "hinge", "ball")

#: Welcher Kantenparameter je Familie der primaere Drehwinkel ist.
_PRIMARY_ANGLE = {"axle": "rot0", "hinge": "yaw", "ball": "rot0"}


class Joint(NamedTuple):
    """Ein stellbares Gelenk: eine Graphkante mit Freiheitsgrad."""

    edge: int
    """Index in ``graph.edges``."""
    family: str
    """``axle``, ``hinge`` oder ``ball``."""
    parent: int
    """Teileindex der Elternseite."""
    child: int
    """Teileindex der Kindseite."""

    @property
    def angle_field(self) -> str:
        return _PRIMARY_ANGLE[self.family]


def joints(graph: bricknet.Graph) -> list[Joint]:
    """Alle stellbaren Gelenke eines Graphen, in Kantenreihenfolge."""
    return [
        Joint(i, str(e["family"]), int(e["a"]), int(e["b"]))
        for i, e in enumerate(graph.edges)
        if str(e["family"]) in JOINT_FAMILIES
    ]


def joint_angle(graph: bricknet.Graph, edge: int) -> float:
    """Aktueller Winkel des Gelenks an ``edge`` in Radiant."""
    e = graph.edges[edge]
    return float(e["yaw"] if _PRIMARY_ANGLE[str(e["family"])] == "yaw" else e["rot"][0])


def pose(graph: bricknet.Graph, angles: Mapping[int, float]) -> bricknet.Graph:
    """Graph mit gesetzten Gelenkwinkeln.

    ``angles`` bildet Kantenindex auf Winkel in Radiant ab. Kanten ohne
    Freiheitsgrad werden abgelehnt, statt still ignoriert zu werden — ein
    stummer Fehlgriff hier wuerde sich erst als unerklaerliche Pose zeigen.

    Der Rueckgabewert ist ein neuer Graph; ``graph`` bleibt unveraendert.
    """
    edges = graph.edges.copy()
    for edge, value in angles.items():
        family = str(edges[edge]["family"])
        if family not in JOINT_FAMILIES:
            raise ValueError(f"Kante {edge} ist '{family}' und hat keinen Freiheitsgrad")
        if _PRIMARY_ANGLE[family] == "yaw":
            edges[edge]["yaw"] = value
        else:
            edges[edge]["rot"][0] = value
    # transforms=None erzwingt die Neuberechnung aus den Kanten.
    return dataclasses.replace(graph, edges=edges, transforms=None)


def realize(graph: bricknet.Graph) -> list[np.ndarray]:
    """Absolute 4x4-Posen je Teil, aus den Kantenparametern berechnet."""
    return bricknet.decode_graph(graph)


def to_ldr(graph: bricknet.Graph) -> str:
    """Gestellten Graphen als LDraw-Text — direkt in Studio oder LDView zu oeffnen."""
    return bricknet.graph_to_ldr(graph)


def tip_position(graph: bricknet.Graph, part: int) -> np.ndarray:
    """Ursprung eines Teils in Weltkoordinaten (LDU), fuer Fingerspitzen-Metriken."""
    return np.asarray(realize(graph)[part])[:3, 3]


def chain_from(graph: bricknet.Graph, root: int) -> list[Joint]:
    """Gelenkkette von ``root`` nach aussen, in Reihenfolge wachsender Tiefe.

    Bildet ab, was eine Fingerkette ausmacht: von der Handwurzel aus jeweils dem
    naechsten Gelenk folgen. Kanten werden ungerichtet betrachtet, weil die
    kanonische Kantenrichtung von bricknet der Konnektorpolaritaet folgt und nicht
    der Kinematik.
    """
    by_part: dict[int, list[Joint]] = {}
    for j in joints(graph):
        by_part.setdefault(j.parent, []).append(j)
        by_part.setdefault(j.child, []).append(j)

    seen_parts = {root}
    seen_edges: set[int] = set()
    frontier = [root]
    chain: list[Joint] = []
    while frontier:
        nxt = []
        for part in frontier:
            for j in by_part.get(part, ()):
                if j.edge in seen_edges:
                    continue
                seen_edges.add(j.edge)
                chain.append(j)
                other = j.child if j.parent == part else j.parent
                if other not in seen_parts:
                    seen_parts.add(other)
                    nxt.append(other)
        frontier = nxt
    return chain


def summarize(graph: bricknet.Graph) -> str:
    """Kurzer Ueberblick: Teile, Kanten, Gelenke nach Familie."""
    from collections import Counter

    fam = Counter(str(e["family"]) for e in graph.edges)
    art = sum(v for k, v in fam.items() if k in JOINT_FAMILIES)
    parts = [f"{len(graph.part_ids)} Teile", f"{len(graph.edges)} Kanten"]
    parts.append(f"{art} Gelenke (" + ", ".join(f"{k}:{fam[k]}" for k in JOINT_FAMILIES if fam[k]) + ")")
    return " | ".join(parts)


def load_ldr(path: str) -> bricknet.Graph:
    """LDraw-Datei als Graph einlesen."""
    with open(path, errors="ignore") as fh:
        return bricknet.parse_ldr(fh.read())


__all__ = [
    "JOINT_FAMILIES",
    "Joint",
    "chain_from",
    "joint_angle",
    "joints",
    "load_ldr",
    "pose",
    "realize",
    "summarize",
    "tip_position",
    "to_ldr",
]
