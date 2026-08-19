"""Serialize/deserialize a ConnectionGraph to plain JSON.

This is the interchange format both the FEM side (.inp constraint
generation) and the future tolerance-chain analysis are meant to consume,
so it must not encode FEM- or tolerance-specific assumptions -- see
fem_mapping.py for the FEM-specific translation layer.
"""
from __future__ import annotations

import json
from dataclasses import asdict

from ..model.candidate import ConnectionCandidate
from ..model.graph import ConnectionGraph
from ..model.part import Part

SCHEMA_VERSION = 1


def to_dict(graph: ConnectionGraph) -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "parts": [
            {k: v for k, v in asdict(part).items() if k != "shape"}
            for part in graph.parts.values()
        ],
        "candidates": [asdict(c) for c in graph.candidates],
    }


def to_json(graph: ConnectionGraph, indent: int = 2) -> str:
    return json.dumps(to_dict(graph), indent=indent)


def write_json(graph: ConnectionGraph, filepath: str) -> None:
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(to_json(graph))


def from_dict(data: dict) -> ConnectionGraph:
    graph = ConnectionGraph()
    for part_data in data["parts"]:
        graph.add_part(Part(**part_data))
    for cand_data in data["candidates"]:
        graph.add_candidate(ConnectionCandidate(**cand_data))
    return graph


def read_json(filepath: str) -> ConnectionGraph:
    with open(filepath, "r", encoding="utf-8") as f:
        return from_dict(json.load(f))
