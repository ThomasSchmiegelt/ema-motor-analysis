"""Part representation used throughout detection and graph export.

Kept decoupled from FreeCAD's Part.Shape where possible (bbox is a plain
6-tuple) so broad-phase logic is testable without a running FreeCAD session.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Part:
    id: str
    label: str
    bbox: tuple[float, float, float, float, float, float]  # xmin,ymin,zmin,xmax,ymax,zmax
    doc_name: Optional[str] = None
    doc_object_name: Optional[str] = None
    shape: Any = None  # Part.Shape, only set when running inside FreeCAD
    step_product_id: Optional[str] = None
    metadata: dict = field(default_factory=dict)

    def enlarged_bbox(self, margin: float) -> tuple[float, float, float, float, float, float]:
        xmin, ymin, zmin, xmax, ymax, zmax = self.bbox
        return (
            xmin - margin, ymin - margin, zmin - margin,
            xmax + margin, ymax + margin, zmax + margin,
        )
