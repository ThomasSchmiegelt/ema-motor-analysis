"""Map a confirmed connection's proposed_type to a CalculiX constraint class.

Kept as a small, explicit lookup rather than embedding FEM assumptions into
the graph/candidate model itself, so the same graph can later feed a
tolerance-chain analysis without carrying FEM baggage.
"""
from __future__ import annotations

from ..model.candidate import ConnectionCandidate

_TYPE_TO_CONSTRAINT = {
    "press_fit": "tie",           # rigid/linear: bonded, no relative motion expected
    "bonded_contact": "tie",
    "clearance_fit": "contact",   # nonlinear: gap present, may open/close under load
    "sliding_contact": "contact",
}


def fem_constraint_for(candidate: ConnectionCandidate) -> str:
    constraint_type = candidate.proposed_type
    return _TYPE_TO_CONSTRAINT.get(constraint_type, "contact")  # unknown -> safer nonlinear default


def apply_fem_constraints(candidates: list[ConnectionCandidate]) -> None:
    """In-place: set fem_constraint on every *confirmed* candidate."""
    for c in candidates:
        if c.confirmed:
            c.fem_constraint = fem_constraint_for(c)
