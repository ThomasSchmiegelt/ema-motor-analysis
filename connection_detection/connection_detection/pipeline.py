"""End-to-end detection pipeline: STEP file / open document -> ConnectionGraph.

Single entry point shared by cli.py and the FreeCAD GUI command so the two
front ends can never drift apart in behavior.
"""
from __future__ import annotations

from .detection.broad_phase import find_candidate_pairs
from .detection.config import DetectionConfig
from .detection.fine_phase import evaluate_pair
from .io.step_reader import parts_from_document, read_step
from .model.graph import ConnectionGraph
from .model.part import Part


def detect_connections(filepath: str, config: DetectionConfig | None = None) -> ConnectionGraph:
    _doc, parts = read_step(filepath)
    return _build_graph(parts, config or DetectionConfig())


def detect_connections_in_document(doc, config: DetectionConfig | None = None) -> ConnectionGraph:
    """Run detection against an already-open FreeCAD document (GUI use:
    the user imported/built the assembly themselves, no re-import)."""
    return _build_graph(parts_from_document(doc), config or DetectionConfig())


def _build_graph(parts: list[Part], config: DetectionConfig) -> ConnectionGraph:
    graph = ConnectionGraph()
    for part in parts:
        graph.add_part(part)

    if graph.is_single_body():
        return graph  # single-body mode: no connection detection needed

    parts_by_id = {p.id: p for p in parts}
    for id_a, id_b in find_candidate_pairs(parts, config):
        for candidate in evaluate_pair(parts_by_id[id_a], parts_by_id[id_b], config):
            graph.add_candidate(candidate)

    return graph
