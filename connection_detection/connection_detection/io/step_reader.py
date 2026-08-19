"""STEP import producing a flat list of `Part` model objects.

Uses FreeCAD's `Import` module, which for AP214/AP242 files goes through
ImportOCAFAssembly (XCAFDoc_ShapeTool) and creates one Part::Feature per
solid/shell with its absolute (world) placement already applied and its
Label set to the STEP product name (confirmed in
src/Mod/Import/App/ImportOCAFAssembly.cpp:189-260 of the FreeCAD source).
Since assemblies are already correctly positioned on import, we don't need
to walk any separate assembly/product tree ourselves -- ImportOCAFAssembly
already flattened it into world-space Part::Feature shapes.

If a document instead contains App::Part groups (e.g. produced by the
newer Assembly import strategy), those are walked recursively and their
child Part::Feature shapes are used with getGlobalPlacement() applied.
"""
from __future__ import annotations

from ..model.part import Part

_SOLID_SHAPE_TYPES = {"Solid", "Compound", "CompSolid", "Shell"}


def read_step(filepath: str, doc_name: str | None = None) -> tuple[object, list[Part]]:
    # imported lazily: this module must stay importable (e.g. for
    # broad_phase unit tests) without a running FreeCAD session
    import FreeCAD
    import Import

    doc_name = doc_name or "ConnectionDetection"
    doc = FreeCAD.newDocument(doc_name) if doc_name not in FreeCAD.listDocuments() else FreeCAD.getDocument(doc_name)
    Import.insert(filepath, doc.Name)
    doc.recompute()
    return doc, parts_from_document(doc)


def parts_from_document(doc) -> list[Part]:
    """Collect Part model objects from an already-open document (e.g. the
    active FreeCAD GUI document), without (re-)importing anything."""
    import FreeCAD

    if not _has_element_maps(doc):
        FreeCAD.Console.PrintWarning(
            "connection_detection: imported shapes have no TNP element map. "
            "Enable 'Topological naming' in Import preferences for stable "
            "face references across re-imports.\n"
        )
    return [_to_part(obj) for obj in _iter_shape_objects(doc)]


def _iter_shape_objects(doc):
    for obj in doc.Objects:
        if obj.TypeId == "App::Part":
            continue  # container, its children are visited directly below
        shape = getattr(obj, "Shape", None)
        if shape is None or shape.isNull():
            continue
        if shape.ShapeType not in _SOLID_SHAPE_TYPES:
            continue
        yield obj


def _to_part(obj) -> Part:
    shape = obj.Shape
    bbox = shape.BoundBox
    return Part(
        id=obj.Name,
        label=obj.Label,
        bbox=(bbox.XMin, bbox.YMin, bbox.ZMin, bbox.XMax, bbox.YMax, bbox.ZMax),
        doc_name=obj.Document.Name,
        doc_object_name=obj.Name,
        shape=shape,
    )


def _has_element_maps(doc) -> bool:
    for obj in _iter_shape_objects(doc):
        if obj.Shape.ElementMapSize > 0:
            return True
    return False
