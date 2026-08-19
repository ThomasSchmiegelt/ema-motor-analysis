"""Connection graph: nodes = parts, edges = connection candidates.

Deliberately FEM-agnostic and tolerance-agnostic. Consumers (CalculiX .inp
export, future tolerance-chain analysis) read this graph without the graph
itself knowing about either.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .candidate import ConnectionCandidate
from .part import Part


@dataclass
class ConnectionGraph:
    parts: dict[str, Part] = field(default_factory=dict)
    candidates: list[ConnectionCandidate] = field(default_factory=list)

    def add_part(self, part: Part) -> None:
        self.parts[part.id] = part

    def add_candidate(self, candidate: ConnectionCandidate) -> None:
        self.candidates.append(candidate)

    def confirmed_connections(self) -> list[ConnectionCandidate]:
        return [c for c in self.candidates if c.confirmed]

    def candidates_for_part(self, part_id: str) -> list[ConnectionCandidate]:
        return [c for c in self.candidates if part_id in (c.part_a, c.part_b)]

    def is_single_body(self) -> bool:
        return len(self.parts) <= 1
