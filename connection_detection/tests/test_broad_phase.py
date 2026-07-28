"""Broad phase is pure geometry (bbox tuples + rtree) -> runs under plain
python3, no FreeCAD needed."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from connection_detection.detection.broad_phase import find_candidate_pairs
from connection_detection.detection.config import DetectionConfig
from connection_detection.model.part import Part


def make_part(id_, xmin, ymin, zmin, xmax, ymax, zmax):
    return Part(id=id_, label=id_, bbox=(xmin, ymin, zmin, xmax, ymax, zmax))


def test_overlapping_pair_found():
    a = make_part("A", 0, 0, 0, 10, 10, 10)
    b = make_part("B", 9, 0, 0, 20, 10, 10)
    pairs = find_candidate_pairs([a, b], DetectionConfig())
    assert pairs == [("A", "B")]


def test_far_apart_pair_excluded():
    a = make_part("A", 0, 0, 0, 10, 10, 10)
    b = make_part("B", 100, 100, 100, 110, 110, 110)
    pairs = find_candidate_pairs([a, b], DetectionConfig())
    assert pairs == []


def test_margin_bridges_small_gap():
    a = make_part("A", 0, 0, 0, 10, 10, 10)
    b = make_part("B", 10.3, 0, 0, 20, 10, 10)  # 0.3 mm gap
    config = DetectionConfig(broad_phase_margin=0.5)
    assert find_candidate_pairs([a, b], config) == [("A", "B")]
    config_tight = DetectionConfig(broad_phase_margin=0.1)
    assert find_candidate_pairs([a, b], config_tight) == []


def test_dedup_and_no_self_pairs():
    parts = [make_part(str(i), 0, 0, 0, 5, 5, 5) for i in range(4)]  # all overlapping
    pairs = find_candidate_pairs(parts, DetectionConfig())
    assert len(pairs) == 6  # C(4,2)
    assert len(set(pairs)) == 6
    assert all(a != b for a, b in pairs)


def test_single_part_no_pairs():
    assert find_candidate_pairs([make_part("A", 0, 0, 0, 1, 1, 1)], DetectionConfig()) == []


if __name__ == "__main__":
    import traceback

    tests = [v for k, v in list(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS {t.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {t.__name__}")
            traceback.print_exc()
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    sys.exit(1 if failed else 0)
