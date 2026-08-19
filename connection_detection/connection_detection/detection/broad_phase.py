"""Broad-phase pair filtering via an R-tree over enlarged part bounding boxes.

Pure-geometry (plain bbox tuples), no FreeCAD dependency -> unit-testable
with plain python3. Uses the `rtree` package (libspatialindex bindings),
the same class of structure FreeCAD's own CAM module uses internally
(boost::geometry::index::rtree in Area.cpp) for box-overlap queries.
"""
from __future__ import annotations

from rtree import index

from ..model.part import Part
from .config import DetectionConfig


def find_candidate_pairs(
    parts: list[Part], config: DetectionConfig
) -> list[tuple[str, str]]:
    """Return deduplicated (part_id_a, part_id_b) pairs whose enlarged
    bounding boxes overlap. a < b lexicographically to keep pairs unique."""
    if len(parts) < 2:
        return []

    properties = index.Property()
    properties.dimension = 3
    idx = index.Index(properties=properties)
    for i, part in enumerate(parts):
        idx.insert(i, part.enlarged_bbox(config.broad_phase_margin))

    seen: set[tuple[str, str]] = set()
    pairs: list[tuple[str, str]] = []
    for i, part in enumerate(parts):
        for j in idx.intersection(part.enlarged_bbox(config.broad_phase_margin)):
            if j == i:
                continue
            a, b = sorted((part.id, parts[j].id))
            if (a, b) not in seen:
                seen.add((a, b))
                pairs.append((a, b))
    return pairs
