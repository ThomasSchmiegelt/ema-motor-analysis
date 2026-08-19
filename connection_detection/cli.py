"""Batch entry point. Needs FreeCAD's Python (Import/Part modules), so run
it through FreeCADCmd, not plain python3:

    /opt/freecad-1.1/build/release/bin/FreeCADCmd cli.py -- input.step -o candidates.json

(FreeCADCmd forwards everything after `--` as sys.argv to the script; if
your FreeCAD build forwards args directly, drop the `--`.)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from connection_detection import DetectionConfig, detect_connections
from connection_detection.graph_export import write_json


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="Detect part-to-part connections in a STEP assembly.")
    parser.add_argument("step_file")
    parser.add_argument("-o", "--output", default="candidates.json")
    parser.add_argument("--clearance-max", type=float, default=DetectionConfig.clearance_max)
    parser.add_argument("--overlap-max", type=float, default=DetectionConfig.overlap_max)
    parser.add_argument("--broad-phase-margin", type=float, default=DetectionConfig.broad_phase_margin)
    args = parser.parse_args(argv)

    config = DetectionConfig(
        clearance_max=args.clearance_max,
        overlap_max=args.overlap_max,
        broad_phase_margin=args.broad_phase_margin,
    )
    graph = detect_connections(args.step_file, config)
    write_json(graph, args.output)
    print(f"{len(graph.parts)} parts, {len(graph.candidates)} candidates -> {args.output}")
    return 0


if __name__ == "__main__":
    argv = sys.argv[1:]
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    raise SystemExit(main(argv))
