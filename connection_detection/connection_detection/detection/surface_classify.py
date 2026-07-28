"""Classify a face pair by underlying surface type and propose a fit/contact.

Uses FreeCAD's Part API, which wraps the corresponding OCCT classes:
Face.Surface -> Part.Cylinder / Part.Plane (BRepAdaptor_Surface equivalent),
giving typed Radius/Axis/Center (cylinder) or a normal via Face.normalAt.

Only decides *geometric* plausibility and raw parameters. Whether a fit is
actually a press fit vs. clearance fit (which needs the measured distance /
penetration depth) is decided by fine_phase.py, which owns the distance
measurement. This module never guesses press_fit vs clearance_fit itself
for planar contacts, since bonded-vs-sliding is an engineering decision the
tool deliberately leaves for user confirmation.
"""
from __future__ import annotations

import math
from typing import Optional

from .config import DetectionConfig


def classify_face_pair(face_a, face_b, config: DetectionConfig) -> Optional[dict]:
    """Return geometry classification dict or None if the pair doesn't match
    a known rule. Does not consider distance/penetration."""
    surf_a = face_a.Surface
    surf_b = face_b.Surface
    type_a = type(surf_a).__name__
    type_b = type(surf_b).__name__

    if type_a == "Cylinder" and type_b == "Cylinder":
        return _classify_cylinder_pair(face_a, surf_a, face_b, surf_b, config)
    if type_a == "Plane" and type_b == "Plane":
        return _classify_plane_pair(face_a, surf_a, face_b, surf_b, config)
    return None


def _is_concave_cylinder(face, surf) -> bool:
    """True if the face normal points toward the axis (bore/hole), False if
    it points away (shaft/outer surface)."""
    u_mid = (face.ParameterRange[0] + face.ParameterRange[1]) / 2.0
    v_mid = (face.ParameterRange[2] + face.ParameterRange[3]) / 2.0
    point = surf.value(u_mid, v_mid)
    normal = face.normalAt(u_mid, v_mid)
    to_axis = (surf.Center - point)
    # project onto the plane perpendicular to the cylinder axis
    axis_dir = surf.Axis.normalize()
    to_axis = to_axis - axis_dir * to_axis.dot(axis_dir)
    if to_axis.Length < 1e-9:
        return False
    return normal.dot(to_axis.normalize()) > 0


def _line_distance(p1, d1, p2, d2) -> float:
    """Minimum distance between two 3D lines (p, direction)."""
    d1 = d1.normalize()
    d2 = d2.normalize()
    cross = d1.cross(d2)
    diff = p2 - p1
    if cross.Length < 1e-9:
        # parallel lines
        proj = diff - d1 * diff.dot(d1)
        return proj.Length
    return abs(diff.dot(cross)) / cross.Length


def _classify_cylinder_pair(face_a, surf_a, face_b, surf_b, config: DetectionConfig) -> Optional[dict]:
    axis_a = surf_a.Axis.normalize()
    axis_b = surf_b.Axis.normalize()
    angle_deg = math.degrees(axis_a.getAngle(axis_b))
    # axes anti-parallel is the same physical alignment as parallel
    if angle_deg > 90.0:
        angle_deg = 180.0 - angle_deg
    if angle_deg > config.axis_parallel_tolerance_deg:
        return None

    offset = _line_distance(surf_a.Center, axis_a, surf_b.Center, axis_b)
    if offset > config.axis_offset_tolerance:
        return None

    if abs(surf_a.Radius - surf_b.Radius) > config.radius_tolerance:
        return None

    concave_a = _is_concave_cylinder(face_a, surf_a)
    concave_b = _is_concave_cylinder(face_b, surf_b)
    if concave_a == concave_b:
        # both bores or both shafts facing each other -> not a fit geometry
        return None

    bore_radius = surf_a.Radius if concave_a else surf_b.Radius
    shaft_radius = surf_b.Radius if concave_a else surf_a.Radius

    return {
        "surface_type": "cylinder_fit",
        "geometry_params": {
            "radius_bore": bore_radius,
            "radius_shaft": shaft_radius,
            "radius_delta": shaft_radius - bore_radius,  # >0 -> nominal interference
            "axis_point": tuple(surf_a.Center),
            "axis_direction": tuple(axis_a),
        },
        "measurement_direction": axis_a,
    }


def _classify_plane_pair(face_a, surf_a, face_b, surf_b, config: DetectionConfig) -> Optional[dict]:
    u_a = (face_a.ParameterRange[0] + face_a.ParameterRange[1]) / 2.0
    v_a = (face_a.ParameterRange[2] + face_a.ParameterRange[3]) / 2.0
    u_b = (face_b.ParameterRange[0] + face_b.ParameterRange[1]) / 2.0
    v_b = (face_b.ParameterRange[2] + face_b.ParameterRange[3]) / 2.0
    normal_a = face_a.normalAt(u_a, v_a)
    normal_b = face_b.normalAt(u_b, v_b)

    cos_angle = max(-1.0, min(1.0, normal_a.dot(normal_b)))
    angle_deg = math.degrees(math.acos(cos_angle))
    if abs(180.0 - angle_deg) > config.normal_antiparallel_tolerance_deg:
        return None

    return {
        "surface_type": "planar_contact",
        "geometry_params": {
            "normal": tuple(normal_a),
            "point_a": tuple(surf_a.value(u_a, v_a)),
        },
        "measurement_direction": normal_a,
    }
