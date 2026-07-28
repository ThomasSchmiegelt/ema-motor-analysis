"""Connection candidate produced by the fine phase / surface classification."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ConnectionCandidate:
    part_a: str
    part_b: str
    face_a: str  # TNP-stable element-map name (fallback: "FaceN")
    face_b: str
    surface_type: str  # "cylinder_fit" | "planar_contact"
    distance: float  # mm; >=0 clearance, or penetration depth if `penetration` is True
    penetration: bool
    geometry_params: dict = field(default_factory=dict)
    proposed_type: str = ""  # "press_fit" | "clearance_fit" | "bonded_contact" | "sliding_contact"

    # confirmed by user in GUI / accepted programmatically; None = undecided
    confirmed: Optional[bool] = None
    fem_constraint: Optional[str] = None  # "tie" | "contact", filled by fem_mapping

    # tolerance-analysis extension point, not populated in step 1
    nominal_value: Optional[float] = None
    tolerance_field: Optional[str] = None

    def key(self) -> tuple[str, str, str, str]:
        return (self.part_a, self.face_a, self.part_b, self.face_b)
