"""Fine phase: per-part-pair face matching within the tolerance band.

For every face pair (face_a from part_a, face_b from part_b):
1. Cheap bound: skip unless distToShape is within max(clearance_max,
   overlap_max) -- neither branch below could accept it otherwise.
2. Classify by surface type (surface_classify.py), geometry-only.
3. Interpret the measured distance per surface type -- see
   `_measure` for why cylinder and plane pairs are handled differently.
"""
from __future__ import annotations

from ..model.candidate import ConnectionCandidate
from ..model.part import Part
from .config import DetectionConfig
from .penetration import probe_local_penetration_depth
from .surface_classify import classify_face_pair

_TOUCH_EPS = 1e-6


def evaluate_pair(part_a: Part, part_b: Part, config: DetectionConfig) -> list[ConnectionCandidate]:
    shape_a = part_a.shape
    shape_b = part_b.shape
    outer_bound = max(config.clearance_max, config.overlap_max)

    candidates: list[ConnectionCandidate] = []
    for i, face_a in enumerate(shape_a.Faces):
        for j, face_b in enumerate(shape_b.Faces):
            dist, pts, _info = face_a.distToShape(face_b)
            if dist > outer_bound:
                continue

            geo = classify_face_pair(face_a, face_b, config)
            if geo is None:
                continue

            measured = _measure(shape_a, shape_b, geo, dist, pts, config)
            if measured is None:
                continue
            measured_distance, penetration = measured

            candidates.append(_build_candidate(part_a, part_b, i, face_a, j, face_b, geo, measured_distance, penetration))
    return candidates


def _measure(shape_a, shape_b, geo: dict, dist: float, pts, config: DetectionConfig):
    """Return (distance, penetration) or None to reject the pair.

    Cylinder pairs: distToShape between two coaxial, axially-overlapping
    cylindrical faces already equals |radius_shaft - radius_bore| exactly
    -- no boolean/probing needed, and geometry_params["radius_delta"]'s
    sign tells us interference vs. clearance directly.

    Planar pairs: a real gap (dist > eps) is an ordinary clearance/contact
    reading, used as-is. dist <= eps means the faces touch *or* cross --
    only then is a local isInside probe needed to tell "flush touch"
    (probe depth 0) from "pushed past by some depth" (probe depth > 0).
    """
    if geo["surface_type"] == "cylinder_fit":
        radius_delta = geo["geometry_params"]["radius_delta"]
        penetration = radius_delta > _TOUCH_EPS
        limit = config.overlap_max if penetration else config.clearance_max
        if dist > limit:
            return None
        return dist, penetration

    # planar_contact
    if dist > _TOUCH_EPS:
        if dist > config.clearance_max:
            return None
        return dist, False

    point = pts[0][0]
    depth = probe_local_penetration_depth(shape_a, shape_b, point, geo["measurement_direction"], config.overlap_max)
    if depth <= _TOUCH_EPS:
        return 0.0, False
    if depth > config.overlap_max:
        return None
    return depth, True


def _build_candidate(part_a, part_b, i, face_a, j, face_b, geo, distance, penetration) -> ConnectionCandidate:
    face_a_name = _stable_face_name(part_a, face_a, i)
    face_b_name = _stable_face_name(part_b, face_b, j)

    surface_type = geo["surface_type"]
    proposed_type = _propose_type(surface_type, penetration, geo["geometry_params"])

    return ConnectionCandidate(
        part_a=part_a.id,
        part_b=part_b.id,
        face_a=face_a_name,
        face_b=face_b_name,
        surface_type=surface_type,
        distance=distance,
        penetration=penetration,
        geometry_params=geo["geometry_params"],
        proposed_type=proposed_type,
    )


def _stable_face_name(part: Part, face, index: int) -> str:
    """Prefer the TNP-mitigated mapped name (App.ComplexGeoData.getElementMappedName,
    inherited by TopoShape) over the plain positional index; fall back to the
    index if the shape has no element map (e.g. TNP mitigation disabled on
    import, or a shape produced without name propagation)."""
    indexed_name = f"Face{index + 1}"
    try:
        mapped = part.shape.getElementMappedName(indexed_name)
    except Exception:
        mapped = None
    return mapped or indexed_name


def _propose_type(surface_type: str, penetration: bool, geometry_params: dict) -> str:
    if surface_type == "cylinder_fit":
        return "press_fit" if penetration else "clearance_fit"
    if surface_type == "planar_contact":
        # geometry alone can't distinguish bonded vs. sliding contact;
        # default to the safer (nonlinear) assumption for user review.
        return "sliding_contact"
    return "unknown"
