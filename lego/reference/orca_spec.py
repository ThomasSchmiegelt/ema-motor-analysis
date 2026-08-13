"""ORCA-Hand-URDF in eine Ziel-Kinematikspezifikation uebersetzen.

Die ORCA-Hand (ETH Zurich Soft Robotics Lab, 17 DoF, sehnengetrieben) liefert das,
was diesem Projekt sonst fehlen wuerde: eine *validierte* anthropomorphe Gelenk-
topologie mit realen Bewegungsgrenzen. Statt ein Bewertungskriterium zu erfinden,
misst ``articulation/score.py`` gegen diese Vorlage.

Quellen und Lizenzen:

* ``orcahand_description`` (URDF/MJCF) — MIT
* ``orcahand_hardware`` (STL/STEP) — CC BY 4.0, "ORCA Hand by ORCA Dexterity, Inc."

Aufruf::

    python reference/orca_spec.py            # schreibt reference/orca/joint_spec.json
    python reference/orca_spec.py --print    # zusaetzlich als Tabelle
"""

from __future__ import annotations

import argparse
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
URDF = HERE / "orca" / "orcahand_right.urdf"
OUT = HERE / "orca" / "joint_spec.json"

#: Die fuenf Finger plus Handwurzel, in der Reihenfolge, in der wir sie berichten.
DIGITS = ("thumb", "index", "middle", "ring", "pinky")

#: Gelenkrollen: Beugung traegt die Greifbewegung, Spreizung die Handoeffnung.
FLEXION = ("mcp", "pip", "dip")
ABDUCTION = ("abd",)


def _digit_of(name: str) -> str | None:
    for d in DIGITS:
        if f"_{d}_" in name or name.endswith(f"_{d}"):
            return d
    return None


def _role_of(name: str) -> str:
    tail = name.rsplit("_", 1)[-1]
    if tail in FLEXION:
        return "flexion"
    if tail in ABDUCTION:
        return "abduction"
    return "wrist" if "wrist" in name else "other"


def parse_urdf(path: Path = URDF) -> dict:
    """URDF in eine kompakte Gelenkspezifikation ueberfuehren."""
    root = ET.parse(path).getroot()
    joints = []
    for j in root.findall("joint"):
        if j.get("type") == "fixed":
            continue
        axis = j.find("axis")
        limit = j.find("limit")
        name = j.get("name")
        lo = float(limit.get("lower")) if limit is not None else None
        hi = float(limit.get("upper")) if limit is not None else None
        joints.append(
            {
                "name": name,
                "digit": _digit_of(name),
                "role": _role_of(name),
                "type": j.get("type"),
                "parent": j.find("parent").get("link"),
                "child": j.find("child").get("link"),
                "axis": [float(v) for v in axis.get("xyz").split()] if axis is not None else None,
                "lower_rad": lo,
                "upper_rad": hi,
                "lower_deg": None if lo is None else round(math.degrees(lo), 1),
                "upper_deg": None if hi is None else round(math.degrees(hi), 1),
                "span_deg": None if lo is None else round(math.degrees(hi - lo), 1),
            }
        )

    chains: dict[str, list[str]] = {d: [] for d in DIGITS}
    for j in joints:
        if j["digit"]:
            chains[j["digit"]].append(j["name"])

    flex = [j for j in joints if j["role"] == "flexion"]
    return {
        "source": {
            "model": "ORCA Hand v1 (right)",
            "urdf": URDF.name,
            "description_repo": "https://github.com/orcahand/orcahand_description",
            "hardware_repo": "https://github.com/orcahand/orcahand_hardware",
            "licenses": {"description": "MIT", "hardware": "CC BY 4.0"},
            "attribution": "ORCA Hand by ORCA Dexterity, Inc. - CC BY 4.0",
        },
        "dof": len(joints),
        "chains": chains,
        "joints": joints,
        "targets": {
            # Woran sich ein LEGO-Entwurf messen lassen muss.
            "n_digits": len(DIGITS),
            "min_flexion_joints_per_digit": 2,
            "median_flexion_span_deg": round(
                sorted(j["span_deg"] for j in flex)[len(flex) // 2], 1
            ),
            "min_flexion_span_deg": round(min(j["span_deg"] for j in flex), 1),
            "opposable_thumb": any(
                j["digit"] == "thumb" and j["role"] == "abduction" for j in joints
            ),
        },
    }


def as_table(spec: dict) -> str:
    rows = [f"{'Gelenk':<22}{'Finger':<8}{'Rolle':<11}{'Achse':<16}{'Bereich':>18}"]
    rows.append("-" * 75)
    for j in spec["joints"]:
        axis = ",".join(f"{v:+.0f}" if abs(v) > 0.99 or v == 0 else f"{v:+.2f}" for v in j["axis"])
        rows.append(
            f"{j['name']:<22}{str(j['digit'] or '-'):<8}{j['role']:<11}{axis:<16}"
            f"{j['lower_deg']:>7.0f}° .. {j['upper_deg']:>+4.0f}°"
        )
    t = spec["targets"]
    rows.append("-" * 75)
    rows.append(
        f"{spec['dof']} DoF | {t['n_digits']} Finger | mediane Beugespanne "
        f"{t['median_flexion_span_deg']}° | opponierbarer Daumen: "
        f"{'ja' if t['opposable_thumb'] else 'nein'}"
    )
    return "\n".join(rows)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--urdf", type=Path, default=URDF)
    ap.add_argument("--out", type=Path, default=OUT)
    ap.add_argument("--print", dest="show", action="store_true", help="Tabelle ausgeben")
    args = ap.parse_args()

    spec = parse_urdf(args.urdf)
    args.out.write_text(json.dumps(spec, indent=2, ensure_ascii=False))
    if args.show:
        print(as_table(spec))
    print(f"\n-> {args.out.relative_to(Path.cwd()) if args.out.is_relative_to(Path.cwd()) else args.out}")


if __name__ == "__main__":
    main()
