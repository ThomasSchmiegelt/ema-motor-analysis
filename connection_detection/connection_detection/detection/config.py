"""Tolerances and thresholds for connection detection. All lengths in mm."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DetectionConfig:
    # broad phase
    broad_phase_margin: float = 0.5  # bbox enlargement before overlap test

    # fine phase (face-pair distance filter)
    clearance_max: float = 0.3   # accept face pairs up to this gap
    overlap_max: float = 0.1     # accept penetration depth up to this value

    # cylinder/cylinder classification
    radius_tolerance: float = 0.05
    axis_parallel_tolerance_deg: float = 2.0
    axis_offset_tolerance: float = 0.05  # max lateral distance between axes

    # plane/plane classification
    normal_antiparallel_tolerance_deg: float = 2.0
    planar_gap_tolerance: float = 0.05  # coplanarity check, independent of clearance_max
