"""Local penetration-depth probing for the planar-contact interference case.

Cylindrical fits don't need this: for two coaxial, axially-overlapping
cylindrical faces, BRepExtrema_DistShapeShape (Shape.distToShape) already
returns exactly |radius_shaft - radius_bore| -- verified empirically against
a real press-fit fixture. That's the interference/clearance magnitude
directly, no boolean/probing needed (see fine_phase.py).

Planar contact has no such closed-form shortcut: distToShape reports 0 both
for two faces that merely touch and for two faces whose solids have pushed
past each other by some depth (the surfaces still cross, hence distance 0
either way). Distinguishing those needs a local interference test at the
contact point. A first version of this used the whole-pair boolean
common() volume projected onto the contact normal, but that conflates
*all* overlap regions between the two solids (e.g. a genuine press fit
elsewhere on the same two parts) with the one specific planar contact
being evaluated. Probing along the normal from the actual contact point
with Shape.isInside is local to that contact and doesn't have that
problem.
"""
from __future__ import annotations

_NUDGE = 1e-4
_BISECT_STEPS = 12


def probe_local_penetration_depth(shape_a, shape_b, point, direction, max_probe: float) -> float:
    """How far solid_a and solid_b's material overlaps around `point`,
    searched along +/-`direction` (a FreeCAD.Vector; need not be
    normalized). 0.0 if the two solids don't actually share material
    there (e.g. a genuine flush touch, not an interference)."""
    direction = direction.normalize()

    def both_inside(t: float) -> bool:
        p = point + direction * t
        return shape_a.isInside(p, 1e-6, True) and shape_b.isInside(p, 1e-6, True)

    def extent(sign: float) -> float:
        if not both_inside(sign * _NUDGE):
            return 0.0
        lo, hi = 0.0, max_probe
        for _ in range(_BISECT_STEPS):
            mid = (lo + hi) / 2.0
            if both_inside(sign * mid):
                lo = mid
            else:
                hi = mid
        return lo

    return extent(1.0) + extent(-1.0)
