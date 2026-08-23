"""Sliver-tet purge for CalculiX rotor FEM inputs (.inp).

CalculiX refuses to solve a mesh if ANY C3D4 tet has a non-positive Jacobian
(negative / zero volume). Gmsh reliably leaves a handful of "flat" sliver tets
(|volume| ~ 1e-16..1e-9 mm^3) in the thin iron bridges between aggressive
multi-layer magnet pockets; ccx then writes a results-less .frd and the whole
stage comes back as a failure even though the mesh is otherwise fine.

Removing those slivers (<< 0.1 % of the elements, essentially zero real
volume) leaves a valid, essentially-conformal mesh. DEFINITIVE PROOF: the
clean test_pi_c2 rotor (244 slivers out of 797 275 tets) then solves in ~156 s
and returns a coherent, analytically-consistent von-Mises field.

The purge works on the .inp TEXT: every *Node line is kept, and only the
*Element definition lines of tets whose signed volume is negative or below a
floor are dropped. Node references / ELSETs stay consistent because the main
set (Evolumes) is declared implicitly via the *Element header, so dropping a
definition line removes it from the set automatically; explicit ID lists
(e.g. *NSET=Fixed, *ELSET=Eall) contain one ID per line and are never touched.

SAFETY: if > 5 % of tets come back "degenerate" the file is NOT modified and a
ValueError is raised — that pattern means a parser glitch (e.g. empty node map
=> every element "dangling"), never a real mesh.

Standalone (stdlib only) so it can also run inside FreeCAD:

    from ema_purge import purge_slivers_inp, write_helper
    n, m = purge_slivers_inp("Mesh.inp")
    write_helper(out_dir)      # standalone _sliver_purge.py in out_dir
"""

from __future__ import annotations

import os

_VOLCUT = 1e-6   # mm^3: below this (or negative) a tet is a degenerate sliver


def _tvol(a, b, c, d):
    """Signed volume [mm^3] of tet (a,b,c,d) — 6-term Sarrus, /6."""
    ax, ay, az = a
    return ((b[0] - ax) * (c[1] - ay) * (d[2] - az)
            + (b[1] - ay) * (c[2] - az) * (d[0] - ax)
            + (b[2] - az) * (c[0] - ax) * (d[1] - ay)
            - (d[0] - ax) * (c[1] - ay) * (b[2] - az)
            - (d[1] - ay) * (c[2] - az) * (b[0] - ax)
            - (d[2] - az) * (c[0] - ax) * (b[1] - ay)) / 6.0


def _parse(inp: str):
    """Minimal .inp reader: node coords {id:(x,y,z)} + el rows (eid,n1..n4)."""
    nodes: dict = {}
    els: list = []
    in_node = False
    in_el = False
    with open(inp, errors="ignore") as f:
        for ln in f:
            s = ln.strip()
            h = s.lower()
            if h.startswith("*node"):
                in_node, in_el = True, False
                continue
            if h.startswith("*element"):
                in_el, in_node = True, False
                continue
            if s.startswith("*"):
                in_node = in_el = False
                continue
            if in_node:
                p = s.split(",")
                if len(p) >= 4:
                    try:
                        nodes[p[0].strip()] = (float(p[1]), float(p[2]), float(p[3]))
                    except ValueError:
                        pass
            elif in_el:
                p = [x.strip() for x in s.split(",") if x.strip().isdigit()]
                if len(p) >= 5:
                    els.append(tuple(p[:5]))
    return nodes, els


def _is_sliver(nodes: dict, e, volcut: float = None) -> bool:
    cs = []
    for nid in e[1:5]:
        if nid not in nodes:
            return True                       # dangling reference -> bad
        cs.append(nodes[nid])
    v = _tvol(cs[0], cs[1], cs[2], cs[3])
    return (v < 0.0) or (abs(v) < (_VOLCUT if volcut is None else volcut))


def _drop_ids(nodes: dict, els: list, volcut: float = None) -> set:
    """Element IDs to drop; hard-aborts if the fraction is implausibly high."""
    if not els:
        return set()
    bad = {e[0] for e in els if _is_sliver(nodes, e, volcut)}
    if len(bad) > 0.05 * len(els):
        raise ValueError(
            "sliver purge aborted: %d/%d tets flagged degenerate (>5%%) "
            "- parser glitch, input left untouched" % (len(bad), len(els)))
    return bad


def _drop_line(t: str, bad: set) -> bool:
    """True only for 5-field tet definition lines whose ID is in ``bad``."""
    if not t or t.startswith("*"):
        return False
    parts = t.split(",")
    if len(parts) != 5 or not all(x.strip().isdigit() for x in parts):
        return False
    return parts[0].strip() in bad


def purge_slivers_inp(inp: str, volcut: float | None = None) -> tuple[int, int]:
    """Drop degenerate/flat C3D4 tets from ``inp`` (in place).

    Returns (n_dropped, n_total). Idempotent; on an already-clean mesh it
    drops 0. Raises ValueError (without touching the file) if > 5 % of tets
    are flagged.
    """
    # ``volcut`` wirkt NUR fuer diesen Aufruf. Frueher wurde hier die
    # Modulglobale ``_VOLCUT`` ueberschrieben — ein einziger Aufruf mit
    # abweichendem Schwellwert haette damit still alle spaeteren Laeufe des
    # Prozesses mitverstellt.
    if not (inp and os.path.exists(inp)):
        return (0, 0)
    nodes, els = _parse(inp)
    bad = _drop_ids(nodes, els, volcut)
    if not bad:
        return (0, len(els))

    kept: list[str] = []
    with open(inp, errors="ignore") as f:
        for ln in f:
            if _drop_line(ln.strip(), bad):
                continue
            kept.append(ln)
    with open(inp, "w") as f:
        f.writelines(kept)
    print("SLIVER_PURGE: removed %d of %d flat tets (%.4f %% of mesh %s)"
          % (len(bad), len(els), 100.0 * len(bad) / len(els),
             "- treat result with caution" if len(bad) > 0.005 * len(els) else ""))
    return (len(bad), len(els))


# ── Standalone text (imported inside FreeCAD — must NOT import this module) ──

_STANDALONE = '''"""Sliver-tet purge for CalculiX .inp (standalone, stdlib only)."""
import os

def _tvol(a, b, c, d):
    ax, ay, az = a
    return ((b[0] - ax) * (c[1] - ay) * (d[2] - az)
            + (b[1] - ay) * (c[2] - az) * (d[0] - ax)
            + (b[2] - az) * (c[0] - ax) * (d[1] - ay)
            - (d[0] - ax) * (c[1] - ay) * (b[2] - az)
            - (d[1] - ay) * (c[2] - az) * (b[0] - ax)
            - (d[2] - az) * (c[0] - ax) * (b[1] - ay)) / 6.0

def purge_slivers_inp(inp, volcut=None):
    volcut = 1e-6 if volcut is None else volcut

    def _is_sliver(nodes, e):
        cs = []
        for nid in e[1:5]:
            if nid not in nodes:
                return True
            cs.append(nodes[nid])
        v = _tvol(cs[0], cs[1], cs[2], cs[3])
        return (v < 0.0) or (abs(v) < volcut)

    def _drop_line(t, bad):
        if not t or t.startswith("*"):
            return False
        parts = t.split(",")
        if len(parts) != 5 or not all(x.strip().isdigit() for x in parts):
            return False
        return parts[0].strip() in bad

    if not (inp and os.path.exists(inp)):
        return (0, 0)
    nodes = {}; els = []; in_node = False; in_el = False
    with open(inp, errors="ignore") as f:
        for ln in f:
            s = ln.strip(); h = s.lower()
            if h.startswith("*node"):
                in_node = True; in_el = False; continue
            if h.startswith("*element"):
                in_el = True; in_node = False; continue
            if s.startswith("*"):
                in_node = False; in_el = False; continue
            if in_node:
                p = s.split(",")
                if len(p) >= 4:
                    try:
                        nodes[p[0].strip()] = (float(p[1]), float(p[2]), float(p[3]))
                    except Exception:
                        pass
            elif in_el:
                p = [x.strip() for x in s.split(",") if x.strip().isdigit()]
                if len(p) >= 5: els.append(tuple(p[:5]))
    if not els:
        return (0, 0)
    bad = {e[0] for e in els if _is_sliver(nodes, e)}
    if not bad:
        return (0, len(els))
    if len(bad) > 0.05 * len(els):
        raise ValueError("sliver purge aborted: %d/%d tets flagged degenerate (>5%%)"
                         % (len(bad), len(els)))
    kept = []
    with open(inp, errors="ignore") as f:
        for ln in f:
            if _drop_line(ln.strip(), bad):
                continue
            kept.append(ln)
    with open(inp, "w") as f:
        f.writelines(kept)
    print("SLIVER_PURGE: removed %d of %d flat tets (%.4f %% of mesh %s)"
          % (len(bad), len(els), 100.0 * len(bad) / len(els),
             "- treat result with caution" if len(bad) > 0.005 * len(els) else ""))
    return (len(bad), len(els))
'''


def write_helper(out_dir: str) -> str:
    """Write a standalone `_sliver_purge.py` (no deps, no f-strings) into
    ``out_dir`` so the FreeCAD FEM script can
    `from _sliver_purge import purge_slivers_inp`."""
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "_sliver_purge.py")
    with open(path, "w") as f:
        f.write(_STANDALONE.lstrip())
    return path


if __name__ == "__main__":
    import sys
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    n, m = purge_slivers_inp(sys.argv[1])
    print(f"purged: dropped={n} total={m}")
