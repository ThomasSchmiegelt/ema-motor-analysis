"""Gültigkeitsbereich des 2D-Surrogats — EINE Definition für Erzeuger und Dienst.

Der Datensatzgenerator (`cae_orchestrator/gen_fdm_dataset.py`, läuft im Flask-venv) und
der Inferenzdienst (`service/`, läuft im Torch-venv) müssen sich über die Grenzen des
trainierten Bereichs einig sein — sonst extrapoliert das Modell still, statt **422** zu
liefern. Deshalb liegt die Definition hier und wird von beiden Seiten importiert.

Reines numpy + Orchestrator-Import, KEIN Torch (damit der Generator es laden kann).

Zwei Ebenen:

* ``bounds_violations`` — liegt der Parametersatz im Trainingsbereich? Der Bereich ist
  `ema_optimize.FREE_PARAMS` (dieselbe Box, über die der Optimierer sucht), plus die
  Basismaße, die der Generator NICHT variiert.
* ``feasibility_problems`` — ist die Geometrie überhaupt baubar/sinnvoll? Eine
  Latin-Hypercube-Stichprobe über 11 unabhängige Parameter erzeugt sonst Unsinn
  (Nuten durch das Statorjoch, mehr Pole als Nuten, Magnete dicker als der Rotor).

Die Regeln spiegeln, was der Rest des Repos schon als gültig ansieht — nicht neu
erfundene Auslegungsregeln:

* radiale Ordnung statorOD > statorID > rotorOD > shaftD > shaftBoreD und
  `slots` als Vielfaches von 3: `ema_text2ema._validate` (dort reparierend, hier prüfend)
* Statorwand muss Nuten UND Rückenjoch tragen: `ema_design_ai.STATOR_SPLIT`
* Magnetlänge wird nicht geprüft, weil `ema_topology.magnet_legs` sie über
  `_max_magnet_width` bereits auf die passende Länge klemmt (Brücke `BRIDGE_MM`)

**Qualität wird bewusst NICHT gefiltert.** Ein schlechtes, aber baubares Design gehört in
den Trainingsdatensatz — der Optimierer wertet solche Punkte ja auch aus. Gefiltert wird
nur, was geometrisch nicht existieren kann. (`ema_design_ai._quick_eval` wäre ein
Qualitätsfilter und ist hier absichtlich nicht im Spiel.)
"""

import os
import sys

import numpy as np


def _add_orchestrator_to_path() -> str:
    """`cae_orchestrator` importierbar machen (auch ohne start.sh, z. B. in Tests)."""
    here = os.path.dirname(os.path.abspath(__file__))
    orch = os.path.normpath(os.path.join(here, "..", "..", "cae_orchestrator"))
    if orch not in sys.path:
        sys.path.insert(0, orch)
    return orch


_add_orchestrator_to_path()

import ema_analysis as ea          # noqa: E402  (Pfad muss vorher stehen)
import ema_optimize as eo          # noqa: E402
import ema_topology as et          # noqa: E402

# Der Trainingsbereich IST die Suchbox des Optimierers — so deckt das Surrogat genau
# den Raum ab, in dem es später gefragt wird.
FREE_PARAMS = eo.FREE_PARAMS

# Basismaße, die der Generator NICHT variiert (sie stecken nicht in FREE_PARAMS). Wird
# eine Anfrage außerhalb dieser Toleranz gestellt, ist sie außerhalb des Trainings.
BASE_KEYS = ("statorOD", "rotorOD", "shaftD", "slots")
BASE_TOL = 0.02          # ±2 % auf die Basismaße

# Anteil der Statorwand, der maximal für Nuten draufgehen darf; der Rest ist Rückenjoch.
# Spiegelt ema_design_ai.STATOR_SPLIT (dort: Bohrung ≤ 0,68·OD, damit eine echte Wand
# bleibt statt einer Hülse).
SLOT_WALL_FRAC = 0.85
# Mindest-Nuten pro Pol. Weniger Nuten als Pole ist keine Maschine mehr; 1,2 lässt
# konzentrierte Bruchlochwicklungen zu und schneidet nur den Unsinn ab.
MIN_SLOTS_PER_POLE = 1.2
BRIDGE_MM = getattr(et, "BRIDGE_MM", 2.0)


# Parameter aus FREE_PARAMS, die auf das 2D-Feld NACHWEISLICH keine Wirkung haben und
# deshalb in Stufe 1 nicht gesampelt werden (sie würden nur LHS-Dimensionen und damit
# Trainingsvielfalt verschwenden — zwei Samples, die sich nur darin unterscheiden, sind
# für den Löser identisch):
#   axial   — kommt in `_rasterise`/`_solve_fdm` nicht vor, erst in `compute_performance`
#   magGap  — `magGapMm` taucht in ema_analysis.py und ema_topology.py überhaupt nicht
#             auf; es ist der Klebespalt der 3D-Magnettasche (ema_em3d)
STAGE1_INERT = ("axial", "magGap")


def effective_bounds(base_geom: dict, exclude: tuple = ()) -> dict:
    """FREE_PARAMS, geschnitten mit dem, was auf DIESER Basismaschine baubar ist.

    Hintergrund (am 30.07. gemessen): eine Latin-Hypercube-Stichprobe über die rohen
    `FREE_PARAMS` liefert nur **~4 % baubare** Geometrien — die Suchbox des Optimierers
    ist erheblich größer als die zulässige Menge. Beispiel: `slotDepth` darf bis 150 mm,
    die Statorwand dieser Maschine misst aber nur ~44 mm. Blind zu ziehen und dann zu
    verwerfen würde die Raumfüllung des LHS zerstören; stattdessen wird die Box vorher
    auf den machbaren Bereich geschnitten, dann ist die Stichprobe darin wieder
    gleichmäßig.

    Ist zugleich der Bereich, gegen den der Dienst später prüft (422) — Erzeuger und
    Dienst teilen sich diese Funktion.
    """
    b = {k: (float(s["lo"]), float(s["hi"])) for k, s in FREE_PARAMS.items()
         if k not in exclude}

    so = float(base_geom["statorOD"]); ro = float(base_geom["rotorOD"])
    sh = float(base_geom["shaftD"]);   slots = int(base_geom["slots"])

    # Statorwand im ungünstigsten Fall (größter Luftspalt ⇒ größte Bohrung ⇒ dünnste Wand)
    if "slotDepth" in b:
        gap_hi = b.get("airgap", (0.0, 0.0))[1]
        wall_min = (so - (ro + 2.0 * gap_hi)) / 2.0
        lo, hi = b["slotDepth"]
        b["slotDepth"] = (lo, min(hi, SLOT_WALL_FRAC * wall_min))

    # Polzahl aus der Nutzahl (Nuten pro Pol)
    if "p" in b:
        lo, hi = b["p"]
        b["p"] = (lo, min(hi, np.floor(slots / (2.0 * MIN_SLOTS_PER_POLE))))

    # Radiales Budget im Rotor für die (fest vorgegebenen) Magnetlagen
    if "magThick" in b:
        layers = max(1, int(base_geom.get("magLayers", 1) or 1))
        lgap = float(base_geom.get("magLayerGap", 0) or 0)
        room = (ro - sh) / 2.0 - 2 * BRIDGE_MM
        lo, hi = b["magThick"]
        b["magThick"] = (lo, min(hi, max(lo, (room - (layers - 1) * lgap) / layers)))

    return b


def _params_of(geom: dict, axial: float) -> dict:
    """Die FREE_PARAMS-Werte aus einer fertigen Geometrie zurücklesen.

    Umkehrung von `ema_optimize._apply_params` (:79) — inklusive der beiden `special`-
    Parameter `axial` (steckt nicht in geom) und `airgap` (aus statorID − rotorOD).
    """
    out = {}
    for key, spec in FREE_PARAMS.items():
        if spec.get("special") == "axial":
            out[key] = float(axial)
        elif spec.get("special") == "airgap":
            out[key] = (float(geom["statorID"]) - float(geom["rotorOD"])) / 2.0
        elif spec["geom"] in geom:
            out[key] = float(geom[spec["geom"]])
    return out


def bounds_violations(geom: dict, axial: float, base_geom: dict | None = None,
                      bounds: dict | None = None) -> list[str]:
    """Leere Liste ⇒ innerhalb des trainierten Bereichs; sonst je Verstoß ein Text.

    `bounds` sollte die `effective_bounds` des Datensatzes sein (der Dienst liest sie aus
    dessen `meta.json`), nicht die rohe FREE_PARAMS-Box — trainiert wurde nur der
    geschnittene Bereich.
    """
    bad = []
    box = bounds or {k: (s["lo"], s["hi"]) for k, s in FREE_PARAMS.items()}
    for key, val in _params_of(geom, axial).items():
        if key not in box:
            continue                       # in Stufe 1 nicht gesampelt (s. STAGE1_INERT)
        lo, hi = box[key]
        if not (lo <= val <= hi):
            bad.append(f"{key}={val:g} außerhalb [{lo:g}, {hi:g}]")
    if base_geom:
        for key in BASE_KEYS:
            ref, got = float(base_geom[key]), float(geom.get(key, 0.0))
            if ref > 0 and abs(got - ref) / ref > BASE_TOL:
                bad.append(f"{key}={got:g} weicht >{BASE_TOL:.0%} vom Trainingswert "
                           f"{ref:g} ab (nicht mittrainiert)")
    if str(geom.get("magShape")) == "custom":
        bad.append("magShape='custom' (Designer/STEP) ist in v1 nicht trainiert")
    return bad


def feasibility_problems(geom: dict, axial: float) -> list[str]:
    """Leere Liste ⇒ die Geometrie ist baubar. Sonst je Problem ein Text."""
    bad = []
    try:
        so = float(geom["statorOD"]); si = float(geom["statorID"])
        ro = float(geom["rotorOD"]);  sh = float(geom["shaftD"])
        bore = float(geom.get("shaftBoreD", 0) or 0)
        slots = int(geom["slots"]);   p = int(geom["p"])
    except (KeyError, TypeError, ValueError) as e:
        return [f"unvollständige Geometrie: {e}"]

    # radiale Ordnung (Regeln aus ema_text2ema._validate, hier prüfend statt reparierend)
    if not so > si:
        bad.append(f"statorOD {so} ≤ statorID {si}")
    if not si > ro:
        bad.append(f"statorID {si} ≤ rotorOD {ro} (kein Luftspalt)")
    if not ro > sh:
        bad.append(f"rotorOD {ro} ≤ shaftD {sh}")
    if bore and not sh > bore:
        bad.append(f"shaftD {sh} ≤ shaftBoreD {bore}")
    if slots % 3:
        bad.append(f"slots={slots} ist kein Vielfaches von 3 (keine Drehstromwicklung)")

    # Nuten müssen in die Statorwand passen und ein Rückenjoch übrig lassen
    wall = (so - si) / 2.0
    if float(geom["slotDepth"]) > SLOT_WALL_FRAC * wall:
        bad.append(f"slotDepth {geom['slotDepth']:g} > {SLOT_WALL_FRAC:.0%} der "
                   f"Statorwand ({wall:.1f} mm) — kein Rückenjoch übrig")

    # Nuten pro Pol
    poles = 2 * p
    if poles and slots / poles < MIN_SLOTS_PER_POLE:
        bad.append(f"{slots} Nuten auf {poles} Pole = {slots / poles:.2f} < "
                   f"{MIN_SLOTS_PER_POLE} Nuten/Pol")

    # Radiales Budget im Rotor für die Magnetlagen
    layers = max(1, int(geom.get("magLayers", 1) or 1))
    need = layers * float(geom["magThick"]) + (layers - 1) * float(geom.get("magLayerGap", 0) or 0)
    room = (ro - sh) / 2.0 - 2 * BRIDGE_MM
    if need > room:
        bad.append(f"{layers} Magnetlage(n) brauchen {need:.1f} mm radial, "
                   f"verfügbar {room:.1f} mm")

    # Zum Schluss die Topologie selbst befragen — sie klemmt Längen und kann Magnete
    # verwerfen, die nicht passen.
    try:
        legs, _meta = et.magnet_legs(geom)
    except Exception as e:                                    # pragma: no cover
        return bad + [f"magnet_legs() scheitert: {str(e)[:120]}"]
    if not legs:
        bad.append("magnet_legs() liefert keine Magnete")
    else:
        if min(lg.length for lg in legs) < 1.0:
            bad.append("Magnetlänge nach Klemmung < 1 mm")
        if min(lg.thickness for lg in legs) < 0.5:
            bad.append("Magnetdicke < 0,5 mm")
    return bad


# Empirische Untergrenzen: die Geometrie muss auf dem Zielgitter überhaupt ankommen.
# Ein Magnet, der bei N=512 auf null Pixel schrumpft, ist als Trainingsbeispiel wertlos
# (das Feld wäre das einer magnetlosen Maschine).
MIN_MAGNET_FRAC = 5e-4       # ≥ 0,05 % der Pixel magnetisch  (bei 512² ≈ 131 px)
MIN_IRON_FRAC = 0.05         # ≥ 5 % der Pixel Eisen


def raster_problems(maps: dict, n: int) -> list[str]:
    """Prüft die FERTIGE Rasterisierung (`_rasterise(..., maps=True)`) auf dem Zielgitter."""
    bad = []
    total = float(n * n)
    f_mag = float(maps["magnet"].sum()) / total
    f_iron = float(maps["iron"].sum()) / total
    if f_mag < MIN_MAGNET_FRAC:
        bad.append(f"nur {f_mag:.4%} Magnet-Pixel bei N={n} (< {MIN_MAGNET_FRAC:.2%})")
    if f_iron < MIN_IRON_FRAC:
        bad.append(f"nur {f_iron:.2%} Eisen-Pixel bei N={n} (< {MIN_IRON_FRAC:.0%})")
    if not np.any(np.hypot(maps["Mx"], maps["My"]) > 0):
        bad.append("keine Magnetisierung im Raster")
    return bad
