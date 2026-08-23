"""Erzeugte Proben parsen und als Mechanik bewerten.

Schliesst die Kette, die das Projekt ausmacht: Modelltext -> BrickNet-Graph ->
Funktionsnote gegen die ORCA-Zielkinematik (``articulation/score.py``). Ohne diesen
Schritt sagt eine Generierung nur, dass das Modell *irgendwas* geschrieben hat.

Aufruf (aus dem Projektwurzelverzeichnis, venv aktiv, ``BRICKNET_DATA`` gesetzt):

.. code-block:: bash

    python -m eval.score_samples --input data/out_pt.jsonl --report data/eval_pt.jsonl

Das Textformat von BrickNet ist zeilenweise und **ungerade lang**: Zeile 0 ist der
Wurzelknoten ``a``, danach folgen Paare aus Knoten- und Kantenzeile.

.. code-block:: text

    a plate 1x1 | bright light blue        <- Knoten a (ohne Kante)
    b plate 1x1 | bright light blue        <- Knoten b
    a stud open a tube a 0                 <- Kante a->b
    c minifig food carrot top | orange     <- Knoten c
    b axle clip a bar a regular 270 -10    <- Kante b->c

Daraus folgt der einzige Reparaturschritt hier: bricht die Generierung nach einer
*geraden* Zeilenzahl ab, haengt der letzte Knoten ohne seine Kante in der Luft und
``parse_sample`` verwirft die ganze Probe (``dangling node without edge``). Die
angehaengte Knotenzeile wird verworfen, der Rest ist unangetastet gueltig. Beide
Quoten werden getrennt ausgewiesen (``roh`` vs. ``repariert``), damit ein
Abschneidefehler des Erzeugers nicht als Modellqualitaet durchgeht.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import bricknet

from articulation import pose as posing
from articulation import score as scoring
from articulation import sweep as sweeping


def split_lines(text: str) -> list[str]:
    """Nichtleere Zeilen einer Probe."""
    return [ln for ln in text.strip("\n").split("\n") if ln.strip()]


def repair(text: str) -> tuple[str, list[str]]:
    """Probe auf eine strukturell vollstaendige Form kuerzen.

    Gibt den reparierten Text (mit abschliessendem Zeilenumbruch, den
    ``parse_sample`` verlangt) und die Liste der Eingriffe zurueck. Es wird nur
    *gekuerzt*, nie ergaenzt oder umgeschrieben — was das Modell geschrieben hat,
    bleibt unveraendert.
    """
    notes: list[str] = []
    lines = split_lines(text)

    # Ein Token-Limit kappt die letzte Zeile mitten im Wort; sie ist am fehlenden
    # Zeilenumbruch erkennbar und nicht rekonstruierbar.
    if lines and not text.endswith("\n"):
        lines.pop()
        notes.append("abgeschnittene letzte Zeile verworfen")

    # Gerade Zeilenzahl = letzter Knoten ohne Kante (s. Modul-Docstring).
    if len(lines) % 2 == 0 and lines:
        lines.pop()
        notes.append("haengender Knoten ohne Kante verworfen")

    return "\n".join(lines) + "\n", notes


def to_graph(text: str) -> bricknet.Graph:
    """Probentext als Graph. Wirft ``ValueError`` mit der Parsermeldung."""
    result = bricknet.parse_sample(text)
    if getattr(result, "error", None):
        raise ValueError(str(result.error))
    return bricknet.tree_to_graph(result.tree)


def parses(text: str) -> tuple[bool, str | None]:
    """Ob der Text als Graph durchgeht — ohne Ausnahme nach aussen."""
    try:
        to_graph(text)
    except Exception as exc:  # Parserfehler wie Aufbaufehler zaehlen beide als Fehlschlag.
        return False, str(exc)
    return True, None


def evaluate(record: dict, *, step_deg: float = 15.0) -> dict:
    """Eine Probe: roh parsen, reparieren, bewerten."""
    text = record["text"]
    out: dict = {"id": record.get("id"), "sample": record.get("sample")}

    # Der abschliessende Zeilenumbruch ist reine Serialisierung (das erzwungene EOS
    # frisst ihn), keine inhaltliche Reparatur — deshalb schon fuer "roh" ergaenzt.
    raw_ok, raw_err = parses(text if text.endswith("\n") else text + "\n")
    out["parse_raw"] = raw_ok
    out["parse_raw_error"] = raw_err

    fixed, notes = repair(text)
    out["repairs"] = notes
    out["n_lines"] = len(split_lines(fixed))

    try:
        graph = to_graph(fixed)
    except Exception as exc:
        out["parse_ok"] = False
        out["parse_error"] = str(exc)
        return out

    out["parse_ok"] = True
    out["parse_error"] = None
    out["n_parts"] = len(graph.part_ids)
    out["n_edges"] = len(graph.edges)
    out["families"] = dict(Counter(str(e["family"]) for e in graph.edges))
    out["n_joints"] = len(posing.joints(graph))

    # Erklaert eine Beweglichkeit von null: ``range_of_motion`` prueft den GANZEN
    # Graphen, eine Durchdringung irgendwo blockiert daher jedes Gelenk.
    try:
        out["n_collisions_rest"] = len(sweeping.check(graph))
    except Exception as exc:
        out["n_collisions_rest"] = None
        out["collision_error"] = str(exc)

    try:
        s = scoring.score(graph, step_deg=step_deg)
    except Exception as exc:
        out["score_error"] = str(exc)
        return out

    out["score"] = {
        "total": s.total,
        "digits": s.digits,
        "depth": s.depth,
        "mobility": s.mobility,
        "grip": s.grip,
        "n_chains": s.n_chains,
        "mean_depth": s.mean_depth,
        "mean_span_deg": s.mean_span_deg,
        "grip_closure": s.grip_closure,
    }
    return out


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def summarize(results: list[dict]) -> str:
    """Ergebnisuebersicht — Quoten getrennt nach roh und repariert."""
    n = len(results)
    raw = sum(1 for r in results if r["parse_raw"])
    ok = [r for r in results if r.get("parse_ok")]
    scored = [r for r in ok if "score" in r]
    joints = [r for r in ok if r.get("n_joints", 0) > 0]

    lines = [
        f"{'Proben':<26}{n:>8}",
        f"{'parsebar roh':<26}{raw:>8}  {raw / n:>6.0%}" if n else "",
        f"{'parsebar repariert':<26}{len(ok):>8}  {len(ok) / n:>6.0%}" if n else "",
        f"{'davon mit Gelenk':<26}{len(joints):>8}",
    ]

    if ok:
        lines += [
            "",
            f"{'Teile je Probe (Mittel)':<26}{_mean([r['n_parts'] for r in ok]):>8.1f}",
            f"{'Kanten je Probe':<26}{_mean([r['n_edges'] for r in ok]):>8.1f}",
            f"{'Gelenke je Probe':<26}{_mean([r['n_joints'] for r in ok]):>8.1f}",
        ]
        rest = [r["n_collisions_rest"] for r in ok if r.get("n_collisions_rest") is not None]
        if rest:
            lines += [
                f"{'Durchdringungen (Ruhe)':<26}{_mean(rest):>8.1f}",
                f"{'davon kollisionsfrei':<26}{sum(1 for c in rest if c == 0):>8}",
            ]
        fams: Counter = Counter()
        for r in ok:
            fams.update(r.get("families", {}))
        total_edges = sum(fams.values()) or 1
        lines.append("")
        lines.append("Kantenfamilien:")
        for fam, cnt in fams.most_common():
            lines.append(f"  {fam:<24}{cnt:>8}  {cnt / total_edges:>6.0%}")

    if scored:
        totals = [r["score"]["total"] for r in scored]
        lines += [
            "",
            f"{'Funktionsnote Mittel':<26}{_mean(totals):>8.3f}",
            f"{'Funktionsnote Maximum':<26}{max(totals):>8.3f}",
            f"{'Proben mit Note > 0':<26}{sum(1 for t in totals if t > 0):>8}",
            "",
            "Teilnoten (Mittel):",
            f"  {'Finger':<24}{_mean([r['score']['digits'] for r in scored]):>8.2f}",
            f"  {'Gelenke je Finger':<24}{_mean([r['score']['depth'] for r in scored]):>8.2f}",
            f"  {'Beweglichkeit':<24}{_mean([r['score']['mobility'] for r in scored]):>8.2f}",
            f"  {'Greifschluss':<24}{_mean([r['score']['grip'] for r in scored]):>8.2f}",
        ]

    if not ok:
        errs = Counter(r.get("parse_error", "?") for r in results)
        lines += ["", "Haeufigste Parserfehler:"]
        lines += [f"  {cnt:>4}x  {err[:70]}" for err, cnt in errs.most_common(5)]

    return "\n".join(ln for ln in lines if ln != "")


def best(results: list[dict]) -> dict | None:
    """Probe mit der hoechsten Funktionsnote."""
    scored = [r for r in results if "score" in r]
    return max(scored, key=lambda r: r["score"]["total"]) if scored else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-i", "--input", type=Path, required=True, help="JSONL mit Feld 'text' (Ausgabe von scripts/generate.py)")
    ap.add_argument("-r", "--report", type=Path, default=None, help="JSONL je Probe schreiben")
    ap.add_argument("--best-ldr", type=Path, default=None, help="beste Probe als LDraw ablegen")
    ap.add_argument("--limit", type=int, default=None, help="nur die ersten N Proben")
    ap.add_argument("--step-deg", type=float, default=15.0, help="Winkelschritt der Bewegungspruefung")
    args = ap.parse_args()

    records = [json.loads(ln) for ln in args.input.read_text().splitlines() if ln.strip()]
    if args.limit:
        records = records[: args.limit]
    assert records, f"keine Proben in {args.input}"

    results = [evaluate(r, step_deg=args.step_deg) for r in records]

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text("".join(json.dumps(r) + "\n" for r in results))
        print(f"-> {args.report}")

    print(summarize(results))

    top = best(results)
    if top and top["score"]["total"] > 0:
        print(f"\nBeste Probe: id={top['id']} sample={top['sample']}")
    if top and args.best_ldr:
        text, _ = repair(records[results.index(top)]["text"])
        args.best_ldr.parent.mkdir(parents=True, exist_ok=True)
        args.best_ldr.write_text(posing.to_ldr(to_graph(text)))
        print(f"-> {args.best_ldr}")


if __name__ == "__main__":
    main()
