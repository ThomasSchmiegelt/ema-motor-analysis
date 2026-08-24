"""Eigener Rechensatz für die Rotor-Festigkeit — Gmsh statt FreeCAD.

Warum es diesen Weg zusätzlich zu ``ema_freecad.build_rotor_fem_script`` gibt:

1. **Topologieoptimierung braucht je Element einen eigenen E-Modul.** FreeCADs
   ``.inp``-Schreiber kann das nicht, Z88 kann es über Materialsätze und CalculiX
   über ``*SOLID SECTION`` je ``ELSET``. Wer die Dichteschleife will, muss den
   Rechensatz selbst schreiben.
2. **Ein Polsektor statt des ganzen Rotors.** Gemessen am Projekt
   ``20260820_083301_test_pi_c2`` (Delta-IPM, 3 Polpaare): der FreeCAD-Weg liefert
   **797.275 C3D4-Tets / 177.392 Knoten / 40 MB .inp** für den vollen Rotor, und davor
   liegen ~40 s FreeCAD-Start. Derselbe Rotor als **ein** Polsektor bei 6 mm:
   **13.669 Tets in 0,4 s**, ohne Unterprozess. Eine Optimierung sind 30–80 Löserläufe —
   das ist der Unterschied zwischen Sekunden und Tagen.
3. **Beide Löser sehen bitgleich dasselbe Netz.** ``schreibe_inp`` und
   ``ema_z88.schreibe_satz`` speisen aus **einer** ``Netz``-Struktur. Nur so ist der
   Vergleich CalculiX ↔ Z88 eine Aussage über die Löser und nicht über zwei Netze.

**Der bestehende FreeCAD/ccx-Pfad bleibt unberührt** und ist weiter die Vorgabe;
dieser hier wird über ``struct_deck="eigen"`` gewählt.

Zwei Netzformen, weil die Randbedingungen es erzwingen
------------------------------------------------------

``baue(geom, sektoren=1)``   ein Polsektor mit **periodisch gepaarten** Schnittflächen.
                             Nur für CalculiX — ``*CYCLICSYMMETRYMODEL`` ist dessen
                             eigene Fähigkeit. Der schnelle Pfad für die Optimierung.
``baue(geom, sektoren=0)``   der **volle** Rotor. Z88 kennt keine zyklische Symmetrie,
                             und die Schnittebenen eines Pols liegen nicht auf
                             Koordinatenachsen — eine Spiegel-Randbedingung ließe sich
                             mit Z88s achsweisen Freiheitsgraden nicht ausdrücken.
                             Für den ehrlichen Vergleich rechnen deshalb **beide** Löser
                             den vollen Rotor.

Lastfall und Randbedingungen
----------------------------

Fliehkraft bei ``rpm``. Axial werden **beide Stirnflächen** in z festgehalten — das ist
der ebene Verzerrungszustand, also genau der konservative Fall, auf den
``ema_rotorcheck.rotor_stress_check`` schon heute torwacht (``lam = nu/(1-nu)``).

In der Ebene ist die Fliehkraft am vollen Ring **selbstausgeglichen**; es bleiben nur
drei Starrkörpermoden. Die werden an drei Bohrungsknoten (bei 0°, 90°, 180°) minimal
unterdrückt, statt die Bohrung rundum einzuspannen — eine eingespannte Bohrung wäre ein
*anderes* Problem als die analytische Formel des frei rotierenden Rings, und der
Vergleich wäre wertlos. Dass diese drei Fesseln fast keine Kraft tragen, ist prüfbar
(``Z88O4.TXT`` bzw. die ccx-Reaktionen) und wird in ``test_deck.py`` geprüft.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field

from ema_topology import magnet_legs, leg_records

# Gmsh-Kennzahlen der Elementtypen, die hier vorkommen.
_GMSH_TET4, _GMSH_TET10 = 4, 11

# Knotenzahl je Elementtyp
KNOTEN_JE_TYP = {1: 4, 2: 10}

# CalculiX-Name je Ordnung
CCX_TYP = {1: "C3D4", 2: "C3D10"}

# Z88-Elementtyp je Ordnung (Elementbibliothek S. 5/6: Nr. 16 = Tet10, Nr. 17 = Tet4)
Z88_TYP = {1: 17, 2: 16}


@dataclass
class Netz:
    """Netzkern — bewusst formatfrei. Beide Schreiber speisen hieraus."""
    knoten: dict                      # id -> (x, y, z) [mm], ids 1..N lückenlos
    elemente: dict                    # id -> tuple[node ids], ids 1..M lückenlos
    ordnung: int                      # 1 = Tet4 | 2 = Tet10
    nset_bohrung: list = field(default_factory=list)
    nset_stirn_a: list = field(default_factory=list)   # z = 0
    nset_stirn_b: list = field(default_factory=list)   # z = axialLen
    paare: list = field(default_factory=list)          # [(knoten_a, knoten_b)] Sektorschnitt
    flaeche_a: list = field(default_factory=list)      # Flächen-Tags Schnitt A (nur Sektor)
    flaeche_b: list = field(default_factory=list)
    poles: int = 0
    sektoren: int = 0                 # 0 = voller Rotor, sonst Zahl der enthaltenen Pole
    r_rot: float = 0.0
    r_shaft: float = 0.0
    axial_len: float = 0.0
    volumen_occ_mm3: float = 0.0      # von OpenCASCADE, UNABHÄNGIG von den Tets

    @property
    def n_knoten(self) -> int:
        return len(self.knoten)

    @property
    def n_elemente(self) -> int:
        return len(self.elemente)

    def volumen_tets_mm3(self) -> float:
        """Summe der Tet-Volumina — der Gegenwert zu ``volumen_occ_mm3``."""
        return sum(abs(_tetvol(self, e)) for e in self.elemente.values())


# ── Geometrie + Vernetzung ────────────────────────────────────────────────────

def baue(geom: dict, mesh_mm: float = 3.0, ordnung: int = 1,
         sektoren: int = 1) -> Netz:
    """Rotoreisen vernetzen.

    ``sektoren=1``  ein Polsektor mit periodisch gepaarten Schnittflächen (nur ccx)
    ``sektoren=0``  der volle Rotor (beide Löser)

    Die Magnettaschen kommen aus ``ema_topology.magnet_legs`` — derselben Quelle, aus
    der 2D-FDM und FreeCAD ihre Geometrie beziehen, einschließlich der im Designer
    gezeichneten ``custom``-Topologie.
    """
    import gmsh                                    # erst hier, damit der Import billig bleibt

    if ordnung not in (1, 2):
        raise ValueError(f"ordnung muss 1 oder 2 sein, nicht {ordnung!r}")

    p       = int(geom["p"])
    poles   = 2 * p
    r_rot   = float(geom["rotorOD"]) / 2.0
    r_shaft = float(geom["shaftD"])  / 2.0
    L       = float(geom["axialLen"])
    if not (0 < r_shaft < r_rot):
        raise ValueError(f"unbrauchbare Radien: shaftD/2={r_shaft}, rotorOD/2={r_rot}")

    half  = math.pi / poles                        # halber Polwinkel
    recs  = [r for r in leg_records(magnet_legs(geom)[0])
             if r["placement"] == "interior"]      # Oberflächenmagnete schneiden nichts

    # interruptible=False ist Pflicht, NICHT Geschmackssache: gmsh setzt sonst beim
    # Start einen Signalhandler, und das geht nur im Hauptthread. Aus einem
    # Flask-Worker heraus scheitert die Vernetzung dann mit „signal only works in
    # main thread of the main interpreter" — also genau dann, wenn die Route im
    # Browser benutzt wird, und nie im Test.
    gmsh.initialize(interruptible=False)
    try:
        gmsh.option.setNumber("General.Terminal", 0)
        occ = gmsh.model.occ

        ring = occ.cut([(2, occ.addDisk(0, 0, 0, r_rot, r_rot))],
                       [(2, occ.addDisk(0, 0, 0, r_shaft, r_shaft))])[0]

        if sektoren:
            flaeche = occ.intersect(ring, [(2, _keil(occ, half, r_rot))])[0]
            winkel  = [0.0]
        else:
            flaeche = ring
            winkel  = [i * 2 * half for i in range(poles)]

        taschen = []
        for pole_ang in winkel:
            for r in recs:
                s = occ.addRectangle(-r["length"] / 2, -r["thick"] / 2, 0,
                                     r["length"], r["thick"])
                occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, r["rot"])
                occ.translate([(2, s)], r["cx"], r["cy"], 0)
                if pole_ang:
                    occ.rotate([(2, s)], 0, 0, 0, 0, 0, 1, pole_ang)
                taschen.append((2, s))
        if taschen:
            flaeche = occ.cut(flaeche, taschen)[0]

        koerper = occ.extrude(flaeche, 0, 0, L)
        occ.synchronize()

        vol_occ = float(sum(occ.getMass(d, t) for d, t in koerper if d == 3))

        fa, fb = ([], [])
        if sektoren:
            fa, fb = _schnittflaechen(gmsh, half, L)
            if fa and fb:
                c, s = math.cos(2 * half), math.sin(2 * half)
                gmsh.model.mesh.setPeriodic(
                    2, fb, fa, [c, -s, 0, 0, s, c, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1])

        gmsh.option.setNumber("Mesh.CharacteristicLengthMax", mesh_mm)
        gmsh.option.setNumber("Mesh.CharacteristicLengthMin", mesh_mm / 4.0)
        gmsh.option.setNumber("Mesh.ElementOrder", ordnung)
        if ordnung == 2:
            # Mittelknoten auf die echte Geometrie ziehen — sonst ist der Sektor innen
            # facettiert und die Massenbilanz gegen OpenCASCADE geht nicht auf.
            gmsh.option.setNumber("Mesh.SecondOrderLinear", 0)
        gmsh.model.mesh.generate(3)

        netz = _ernte(gmsh, ordnung, r_rot, r_shaft, L, poles,
                      sektoren, fa, fb, vol_occ)
    finally:
        gmsh.finalize()
    return netz


def _keil(occ, half: float, r_rot: float):
    """Sektorkeil als Polygon — gilt auch für Sektoren ≥ 180° (p = 1)."""
    R   = r_rot * 1.5
    pts = [occ.addPoint(0, 0, 0)]
    n   = 8
    for i in range(n + 1):
        a = -half + 2 * half * i / n
        pts.append(occ.addPoint(R * math.cos(a), R * math.sin(a), 0))
    linien = [occ.addLine(pts[i], pts[i + 1]) for i in range(len(pts) - 1)]
    linien.append(occ.addLine(pts[-1], pts[0]))
    return occ.addPlaneSurface([occ.addCurveLoop(linien)])


def _schnittflaechen(gmsh, half: float, L: float):
    """Die beiden radialen Schnittflächen des Sektors finden (nicht Stirn, nicht Mantel)."""
    fa, fb = [], []
    for _dim, tag in gmsh.model.getEntities(2):
        x, y, z = gmsh.model.occ.getCenterOfMass(2, tag)
        if abs(z) < 1e-9 or abs(z - L) < 1e-9 or math.hypot(x, y) < 1e-9:
            continue
        phi = math.atan2(y, x)
        if   abs(phi + half) < 1e-6: fa.append(tag)
        elif abs(phi - half) < 1e-6: fb.append(tag)
    return fa, fb


def _ernte(gmsh, ordnung, r_rot, r_shaft, L, poles, sektoren, fa, fb, vol_occ) -> Netz:
    """Gmsh-Netz in die formatfreie ``Netz``-Struktur überführen.

    Knoten und Elemente werden **lückenlos ab 1 neu nummeriert** — Z88 verlangt
    streng aufsteigende Nummern ohne Lücken (Theorie-Handbuch, 2./3. Eingabegruppe).
    """
    tags, koords, _ = gmsh.model.mesh.getNodes()
    # float() ist NICHT kosmetisch: gmsh liefert numpy.float64, und die reisen sonst
    # durch Lasten, Kennzahlen und Optimierung bis in results.json — wo der
    # stdlib-JSON-Kodierer sie nicht schreiben kann und der Lauf am Ende scheitert.
    roh = {int(t): (float(koords[3 * i]), float(koords[3 * i + 1]),
                    float(koords[3 * i + 2]))
           for i, t in enumerate(tags)}

    gtyp = _GMSH_TET4 if ordnung == 1 else _GMSH_TET10
    el_tags, el_knoten = gmsh.model.mesh.getElementsByType(gtyp)
    nje = KNOTEN_JE_TYP[ordnung]
    if not len(el_tags):
        raise RuntimeError("Gmsh hat keine Tetraeder erzeugt")

    benutzt = sorted({int(n) for n in el_knoten})
    neu     = {alt: i + 1 for i, alt in enumerate(benutzt)}
    knoten  = {neu[a]: roh[a] for a in benutzt}

    elemente = {}
    for i, _t in enumerate(el_tags):
        roh_ids = [int(n) for n in el_knoten[i * nje:(i + 1) * nje]]
        elemente[i + 1] = tuple(neu[n] for n in roh_ids)

    tol = max(1e-6, 1e-4 * r_rot)
    bohrung = [i for i, (x, y, _z) in knoten.items()
               if abs(math.hypot(x, y) - r_shaft) < tol]
    stirn_a = [i for i, (_x, _y, z) in knoten.items() if abs(z) < tol]
    stirn_b = [i for i, (_x, _y, z) in knoten.items() if abs(z - L) < tol]

    paare = []
    for tag in fb:
        _t, nb, na, _m = gmsh.model.mesh.getPeriodicNodes(2, tag)
        for a, b in zip(na, nb):
            if int(a) in neu and int(b) in neu:
                paare.append((neu[int(a)], neu[int(b)]))

    netz_ = Netz(knoten=knoten, elemente=elemente, ordnung=ordnung,
                nset_bohrung=sorted(bohrung), nset_stirn_a=sorted(stirn_a),
                nset_stirn_b=sorted(stirn_b), paare=paare,
                flaeche_a=list(fa), flaeche_b=list(fb),
                 poles=poles, sektoren=sektoren, r_rot=r_rot, r_shaft=r_shaft,
                 axial_len=L, volumen_occ_mm3=float(vol_occ))
    if ordnung == 2:
        _pruefe_tet10(netz_)
    return netz_


def _pruefe_tet10(netz: Netz) -> None:
    """Die angenommene Gmsh-Kantenreihenfolge gegen die echten Koordinaten prüfen.

    ``_TET10_KANTEN`` ist die einzige Stelle, an der dieses Modul der Gmsh-Doku
    glaubt statt zu messen. Stimmte sie nicht, wären Formfunktionen, Lastvektor und
    der geschriebene CalculiX-Satz still falsch — die Rechnung liefe durch und die
    Zahlen sähen plausibel aus. Also wird an einer Stichprobe geprüft, dass jeder
    Kantenknoten wirklich nahe der Mitte seiner beiden Eckknoten liegt.
    """
    import random

    schluessel = list(netz.elemente)
    stich = random.Random(0).sample(schluessel, min(50, len(schluessel)))
    for eid in stich:
        ids = netz.elemente[eid]
        ecken = [netz.knoten[i] for i in ids[:4]]
        kante = max(math.dist(ecken[a], ecken[b])
                    for a in range(4) for b in range(a + 1, 4))
        for k, (a, b) in enumerate(_TET10_KANTEN):
            mitte = tuple((ecken[a][t] + ecken[b][t]) / 2.0 for t in range(3))
            ist   = netz.knoten[ids[4 + k]]
            # Grosszuegig: bei gekruemmten Raendern weicht der Kantenknoten bewusst ab,
            # aber nie um mehr als einen Bruchteil der laengsten Elementkante.
            if math.dist(mitte, ist) > 0.35 * kante:
                raise RuntimeError(
                    f"Gmsh-Tet10-Knotenreihenfolge passt nicht zu _TET10_KANTEN "
                    f"(Element {eid}, Kante {k} = {(a, b)}): Knoten liegt "
                    f"{math.dist(mitte, ist):.3f} mm von der Kantenmitte entfernt, "
                    f"laengste Kante {kante:.3f} mm. _TET10_KANTEN pruefen.")


# ── Fliehkraft als Knotenkräfte (für Z88, das keine Rotationslast kennt) ──────

# Gauss-Regeln auf dem Einheitstetraeder in Baryzentrik (L1..L4); die Gewichte summieren
# sich zu 1 und werden mit dem Referenzvolumen 1/6 sowie |det J| multipliziert.
# Grad 2 reicht für Tet4 (N_i linear × Last linear), Grad 3 für Tet10.
_A, _B = 0.5854101966249685, 0.1381966011250105
_REGEL_GRAD2 = [((_A, _B, _B, _B), 0.25), ((_B, _A, _B, _B), 0.25),
                ((_B, _B, _A, _B), 0.25), ((_B, _B, _B, _A), 0.25)]
_REGEL_GRAD3 = [((0.25, 0.25, 0.25, 0.25), -0.8),
                ((0.5, 1 / 6, 1 / 6, 1 / 6), 0.45), ((1 / 6, 0.5, 1 / 6, 1 / 6), 0.45),
                ((1 / 6, 1 / 6, 0.5, 1 / 6), 0.45), ((1 / 6, 1 / 6, 1 / 6, 0.5), 0.45)]

# dL_m/dxi_k — die vier Baryzentrischen über den drei Referenzkoordinaten.
_DL = ((-1.0, -1.0, -1.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0))

# Gmsh-Tet10: 4 Ecken, dann die Kanten in genau dieser Reihenfolge. Die Annahme wird
# beim Ernten des Netzes gegen die echten Koordinaten geprüft (_pruefe_tet10), damit
# eine geänderte Gmsh-Reihenfolge auffällt, statt still falsche Lasten zu erzeugen.
_TET10_KANTEN = ((0, 1), (1, 2), (0, 2), (0, 3), (2, 3), (1, 3))


def _formfunktionen(L, ordnung: int):
    """Formfunktionen am baryzentrischen Punkt ``L`` in Gmsh-Knotenreihenfolge."""
    if ordnung == 1:
        return list(L)
    N = [Lm * (2 * Lm - 1) for Lm in L]
    N += [4 * L[i] * L[j] for i, j in _TET10_KANTEN]
    return N


def _formableitungen(L, ordnung: int):
    """``dN_i/dxi_k`` am Punkt ``L`` — Liste von Dreitupeln, Gmsh-Reihenfolge."""
    if ordnung == 1:
        return [tuple(_DL[m]) for m in range(4)]
    ab = []
    for m in range(4):                                   # Ecken
        f = 4 * L[m] - 1
        ab.append(tuple(f * _DL[m][k] for k in range(3)))
    for i, j in _TET10_KANTEN:                           # Kantenmitten
        ab.append(tuple(4 * (L[j] * _DL[i][k] + L[i] * _DL[j][k]) for k in range(3)))
    return ab


def _tetvol(netz: Netz, ids) -> float:
    """Vorzeichenbehaftetes Volumen [mm³] aus den vier Eckknoten (geradlinig)."""
    a, b, c, d = (netz.knoten[i] for i in ids[:4])
    u = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
    v = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
    w = (d[0] - a[0], d[1] - a[1], d[2] - a[2])
    return (u[0] * (v[1] * w[2] - v[2] * w[1])
            - u[1] * (v[0] * w[2] - v[2] * w[0])
            + u[2] * (v[0] * w[1] - v[1] * w[0])) / 6.0


def _detj(xyz, dN) -> float:
    """|det J| der isoparametrischen Abbildung an einem Gausspunkt."""
    J = [[sum(q[r] * d[k] for q, d in zip(xyz, dN)) for k in range(3)] for r in range(3)]
    return abs(J[0][0] * (J[1][1] * J[2][2] - J[1][2] * J[2][1])
               - J[0][1] * (J[1][0] * J[2][2] - J[1][2] * J[2][0])
               + J[0][2] * (J[1][0] * J[2][1] - J[1][1] * J[2][0]))


def zentrifugal_lasten(netz: Netz, dichte_kg_m3: float, rpm: float,
                       rho_je_element: dict | None = None) -> dict:
    """Knotenkräfte [N] aus der Fliehkraft — ``{knoten: (fx, fy, fz)}``.

    Z88 kennt keine Rotationslast (das ``OMEGA`` in ``z88r`` ist der
    SOR-Relaxationsfaktor). Also wird die Volumenkraft ``b = ρ ω² r`` **konsistent**
    integriert: ``f_i = ∫ N_i · b dV``, isoparametrisch, mit echter Jacobi-Determinante
    an jedem Gausspunkt. Das ist bei Tet10 nicht optional — dort liegen die
    Kantenknoten auf der gekrümmten Berandung, und ein geradlinig genähertes
    Elementvolumen wäre systematisch zu klein.

    **Bei Tet10 sind die Eckkräfte negativ** (die klassische −1/20 / +1/5-Verteilung).
    Wer die Quadratur prüfen will, darf deshalb *nicht* ``Σ|f_i|`` gegen das Integral
    stellen, sondern muss eine Größe nehmen, die die Verteilung mitträgt —
    ``zentrifugal_arbeit`` tut das.

    ``rho_je_element`` skaliert die **Masse** je Element (Topologieoptimierung). Das ist
    nicht optional, sondern der Kern: wer nur den E-Modul senkt und die Dichte stehen
    lässt, hängt volle Masse an weiches Material — die verbleibenden steifen Bereiche
    tragen dann alles und die Spannung läuft davon (gemessen: 1822 MPa gegen eine
    Fließgrenze von 340 MPa, bevor das hier eingebaut war).

    Einheiten: Netz in mm, ``dichte_kg_m3`` in kg/m³ → ρ in t/mm³ (das mm/N/MPa/t-System,
    das auch CalculiX benutzt), Ergebnis in N.
    """
    rho   = float(dichte_kg_m3) / 1e12                # kg/m³ -> t/mm³
    omega = 2.0 * math.pi * float(rpm) / 60.0         # rad/s
    ow2   = rho * omega * omega
    regel = _REGEL_GRAD2 if netz.ordnung == 1 else _REGEL_GRAD3
    vorab = [(_formfunktionen(L, netz.ordnung), _formableitungen(L, netz.ordnung), w)
             for L, w in regel]

    lasten = {i: [0.0, 0.0, 0.0] for i in netz.knoten}
    for eid, ids in netz.elemente.items():
        anteil = 1.0 if rho_je_element is None else float(rho_je_element.get(eid, 1.0))
        if anteil <= 0.0:
            continue
        xyz = [netz.knoten[i] for i in ids]
        for N, dN, w in vorab:
            det = _detj(xyz, dN)
            if det <= 0.0:
                continue
            gx = sum(n * q[0] for n, q in zip(N, xyz))
            gy = sum(n * q[1] for n, q in zip(N, xyz))
            skal = w * det / 6.0 * anteil              # Referenzvolumen des Tetraeders
            bx, by = ow2 * gx * skal, ow2 * gy * skal
            for n, i in zip(N, ids):
                lasten[i][0] += n * bx
                lasten[i][1] += n * by
    return {i: tuple(v) for i, v in lasten.items()}


def zentrifugal_arbeit(netz: Netz, lasten: dict) -> float:
    """``Σ f_i · x_i`` [N·mm] — das ordnungsunabhängige Prüfmaß der Quadratur.

    Der konsistente Lastvektor leistet gegen **jedes** Verschiebungsfeld aus dem
    Ansatzraum dieselbe Arbeit wie die verteilte Last. Für das lineare Feld ``u = x``
    gilt darum exakt ``Σ f_i·x_i = ∫ b·x dV = ρω² ∫ r² dV`` — bei Tet4 wie bei Tet10,
    und anders als ``Σ|f_i|`` auch dann, wenn einzelne Knotenkräfte negativ sind.
    """
    return sum(f[0] * netz.knoten[i][0] + f[1] * netz.knoten[i][1]
               + f[2] * netz.knoten[i][2] for i, f in lasten.items())


def zentrifugal_arbeit_analytisch(netz: Netz, dichte_kg_m3: float, rpm: float) -> float:
    """``ρω² ∫ r² dV = ρω² · 2πL (b⁴−a⁴)/4`` für den **taschenfreien** Ring [N·mm].

    Gegenstück zu ``zentrifugal_arbeit``. Nur für den taschenfreien Fall gedacht — mit
    Magnettaschen stimmt es absichtlich nicht, und ``test_deck.py`` trennt deshalb die
    Quadratur (leerer Ring) von der Geometrie (Volumen gegen OpenCASCADE).
    """
    rho   = float(dichte_kg_m3) / 1e12
    omega = 2.0 * math.pi * float(rpm) / 60.0
    a, b  = netz.r_shaft, netz.r_rot
    anteil = 1.0 if not netz.sektoren else netz.sektoren / netz.poles
    return (rho * omega * omega * 2 * math.pi * netz.axial_len
            * (b ** 4 - a ** 4) / 4.0) * anteil


def zentrifugal_summe_analytisch(netz: Netz, dichte_kg_m3: float, rpm: float) -> float:
    """``∫ ρω²r dV = ρω² · 2πL (b³-a³)/3`` für den taschenfreien Vollring [N].

    Gilt als Vergleich für ``Σ|f_i|`` **nur bei Tet4**, wo alle Formfunktionen
    nichtnegativ sind und deshalb jede Knotenkraft nach außen zeigt.
    """
    rho   = float(dichte_kg_m3) / 1e12
    omega = 2.0 * math.pi * float(rpm) / 60.0
    a, b  = netz.r_shaft, netz.r_rot
    anteil = 1.0 if not netz.sektoren else netz.sektoren / netz.poles
    return (rho * omega * omega * 2 * math.pi * netz.axial_len
            * (b ** 3 - a ** 3) / 3.0) * anteil


# ── CalculiX-Schreiber ────────────────────────────────────────────────────────

def schreibe_inp(netz: Netz, mat: dict, rpm: float, pfad: str,
                 rho_je_element: dict | None = None, simp_p: float = 1.0) -> str:
    """CalculiX-Rechensatz schreiben; gibt den Dateipfad zurück.

    ``rho_je_element`` (optional) ordnet Elementnummern eine **relative Dichte**
    ``rho ∈ (0, 1]`` zu — der Zugang für die Topologieoptimierung. Daraus folgen
    **beide** Materialgrößen: ``E = E0 · rho^simp_p`` und ``Dichte = rho0 · rho``.
    Nur den E-Modul zu senken wäre bei einer Volumenlast falsch (s.
    ``zentrifugal_lasten``). Die Werte werden in Stufen zusammengefasst, damit nicht
    je Element ein eigenes ``*MATERIAL`` entsteht.

    **Zyklische Symmetrie über ``*EQUATION``, nicht über ``*CYCLICSYMMETRYMODEL``.**
    Gmsh liefert die Knotenpaare der beiden Schnittflächen exakt (``netz.paare``);
    daraus wird je Paar die Drehbedingung ``u_b = R(2·half)·u_a`` als drei
    Gleichungen geschrieben. Das ist explizit und nachrechenbar, während
    ``*CYCLICSYMMETRYMODEL`` zusätzlich Flächendefinitionen verlangt, deren
    Zuordnung wir raten müssten.
    """
    os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
    omega  = 2.0 * math.pi * float(rpm) / 60.0
    rho_t  = float(mat["density"]) / 1e12
    nu     = float(mat["nu"])
    e0     = float(mat["E"])

    stufen = _materialstufen(netz, rho_je_element)

    z = []
    z.append("** Rotor-Fliehkraft, erzeugt von ema_deck.py (ohne FreeCAD)")
    z.append(f"** {netz.n_knoten} Knoten, {netz.n_elemente} {CCX_TYP[netz.ordnung]}, "
             f"{'Polsektor' if netz.sektoren else 'Vollrotor'}, {rpm:.0f} min-1")
    z.append("*NODE, NSET=Nall")
    for i in sorted(netz.knoten):
        x, y, zz = netz.knoten[i]
        z.append(f"{i}, {x:.9g}, {y:.9g}, {zz:.9g}")

    # Elemente: EIN *ELEMENT-Block (Eall), die Materialstufen danach als eigene ELSETs.
    z.append(f"*ELEMENT, TYPE={CCX_TYP[netz.ordnung]}, ELSET=Eall")
    for eid in sorted(netz.elemente):
        z.append(f"{eid}, " + ", ".join(str(n) for n in netz.elemente[eid]))

    for stufe, (rho_rel, elems) in enumerate(stufen):
        if len(stufen) > 1:
            z.append(f"*ELSET, ELSET=E{stufe}")
            z.extend(_id_zeilen(elems))
        elset = f"E{stufe}" if len(stufen) > 1 else "Eall"
        z.append(f"*MATERIAL, NAME=M{stufe}")
        z.append("*ELASTIC")
        z.append(f"{max(e0 * rho_rel ** simp_p, e0 * 1e-9):.6g}, {nu:.6g}")
        z.append("*DENSITY")
        z.append(f"{rho_t * rho_rel:.9g}")
        z.append(f"*SOLID SECTION, ELSET={elset}, MATERIAL=M{stufe}")

    z.append("*NSET, NSET=Nstirn")
    z.extend(_id_zeilen(sorted(set(netz.nset_stirn_a) | set(netz.nset_stirn_b))))

    stirn = sorted(set(netz.nset_stirn_a) | set(netz.nset_stirn_b))
    z.append("*BOUNDARY")
    z.append("Nstirn, 3, 3, 0.0")                   # ebener Verzerrungszustand
    fesseln = _ebene_fesseln(netz)
    for kn, fg in fesseln:
        z.append(f"{kn}, {fg}, {fg}, 0.0")

    if netz.sektoren and netz.paare:
        # CalculiX verbietet, dass ein Freiheitsgrad zugleich festgehalten (SPC) und
        # abhaengige Seite einer Gleichung (MPC) ist. Die betroffenen Gleichungen sind
        # ohnehin redundant: liegen beide Partner auf einer Stirnflaeche, ist u_z bei
        # beiden schon null. Also werden genau diese uebersprungen.
        gefesselt = {(kn, fg) for kn, fg in fesseln}
        gefesselt |= {(kn, 3) for kn in stirn}
        c = math.cos(2 * math.pi / netz.poles)
        s = math.sin(2 * math.pi / netz.poles)
        z.append("*EQUATION")
        for a, b in netz.paare:
            if a == b:
                continue
            if (b, 1) not in gefesselt and (b, 2) not in gefesselt:
                z.append("3")
                z.append(f"{b}, 1, 1.0, {a}, 1, {-c:.12g}, {a}, 2, {s:.12g}")
                z.append("3")
                z.append(f"{b}, 2, 1.0, {a}, 1, {-s:.12g}, {a}, 2, {-c:.12g}")
            if (b, 3) not in gefesselt:
                z.append("2")
                z.append(f"{b}, 3, 1.0, {a}, 3, -1.0")

    z.append("*STEP")
    z.append("*STATIC")
    z.append("*DLOAD")
    z.append(f"Eall, CENTRIF, {omega * omega:.9g}, 0.0, 0.0, 0.0, 0.0, 0.0, 1.0")
    z.append("*NODE FILE")
    z.append("U, RF")
    z.append("*EL FILE")
    z.append("S, E")
    # Zusaetzlich die INTEGRATIONSPUNKT-Spannungen in die .dat. Das .frd traegt
    # knotengemittelte Werte, Z88 dagegen Gausspunkte — ein Vergleich der beiden
    # waere ein Vergleich zweier Glaettungen. Fuer C3D4 hat CalculiX genau EINEN
    # Integrationspunkt (Elementmitte), Z88 liefert fuer Typ 17 konstante Spannung
    # ueber das Element: damit stehen auf beiden Seiten dieselben Groessen.
    z.append("*EL PRINT, ELSET=Eall")
    z.append("S")
    z.append("*END STEP")

    with open(pfad, "w", encoding="utf-8") as f:
        f.write("\n".join(z) + "\n")
    return pfad


def _ebene_fesseln(netz: Netz) -> list:
    """Fesseln gegen die ebenen Starrkörpermoden — ``[(knoten, fg)]``, fg 1=x 2=y.

    **Vollrotor:** drei Fesseln (uy bei 0°, uy bei 180°, ux bei 90°). Die Fliehkraft
    am geschlossenen Ring ist selbstausgeglichen, also tragen sie fast keine Kraft.
    Die Bohrung rundum einzuspannen wäre ein *anderes* Problem als der frei rotierende
    Ring der analytischen Formel — der Vergleich wäre wertlos.

    **Sektor:** die zyklischen Gleichungen unterbinden schon jede Starrkörper-
    *verschiebung* (für ``poles > 2``); übrig bleibt allein die Drehung um z. Dagegen
    genügt **eine** Fessel: ``uy = 0`` am Bohrungsknoten nächst der x-Achse, auf der
    ``uy`` tangential steht.

    Beide Male gilt: die Reaktionen an diesen Knoten müssen verschwindend klein sein.
    ``test_deck.py`` prüft das gegen die Gesamtfliehkraft.
    """
    if not netz.nset_bohrung:
        raise RuntimeError("keine Bohrungsknoten gefunden")

    def naechster(ziel_phi):
        best, best_d = None, 9e99
        for i in netz.nset_bohrung:
            x, y, zz = netz.knoten[i]
            if abs(zz) > 1e-9:                      # auf die Stirnfläche z=0 beschränken
                continue
            phi = math.atan2(y, x)
            d = abs(math.atan2(math.sin(phi - ziel_phi), math.cos(phi - ziel_phi)))
            if d < best_d:
                best, best_d = i, d
        return best

    if netz.sektoren:
        n0 = naechster(0.0)
        if n0 is None:
            raise RuntimeError("kein Bohrungsknoten auf z=0 für die Drehfessel")
        return [(n0, 2)]

    n0, n90, n180 = naechster(0.0), naechster(math.pi / 2), naechster(math.pi)
    if None in (n0, n90, n180) or len({n0, n90, n180}) < 3:
        raise RuntimeError("zu wenige Bohrungsknoten für die Starrkörperfesseln")
    return [(n0, 2), (n180, 2), (n90, 1)]           # uy, uy, ux


def _id_zeilen(ids, je_zeile: int = 8):
    """Ganzzahllisten für CalculiX/Abaqus in Zeilen zu höchstens ``je_zeile`` Einträgen."""
    return [", ".join(str(n) for n in ids[i:i + je_zeile])
            for i in range(0, len(ids), je_zeile)]


def _materialstufen(netz: Netz, rho_je_element: dict | None,
                    n_stufen: int = 24):
    """Elemente nach relativer Dichte in höchstens ``n_stufen`` Gruppen bündeln.

    Ohne ``rho_je_element`` gibt es genau eine Stufe mit ``rho = 1``. Mit — also in der
    Topologieoptimierung — wird quantisiert, weil sonst je Element ein eigenes
    ``*MATERIAL`` bzw. eine eigene Z88-Materialdatei entstünde. Rückgabe:
    ``[(rho_der_stufe, [elementnummern]), …]``.
    """
    if not rho_je_element:
        return [(1.0, sorted(netz.elemente))]

    lo = min(rho_je_element.values())
    hi = max(rho_je_element.values())
    if hi - lo < 1e-9:
        return [(hi, sorted(netz.elemente))]

    eimer = {}
    for eid in sorted(netz.elemente):
        r = float(rho_je_element.get(eid, 1.0))
        k = min(n_stufen - 1, int((r - lo) / (hi - lo) * n_stufen))
        eimer.setdefault(k, []).append(eid)
    return [(lo + (k + 0.5) * (hi - lo) / n_stufen, sorted(elems))
            for k, elems in sorted(eimer.items())]


# ── CalculiX fahren und auswerten ─────────────────────────────────────────────

CCX_CMD = os.path.expanduser("~/freecad_1.1_quellcode/.pixi/envs/default/bin/ccx")


def loese_ccx(pfad: str, kerne: int = 4, timeout: int = 3600) -> dict:
    """``ccx`` auf einen mit ``schreibe_inp`` geschriebenen Satz ansetzen.

    ``pfad`` ist die ``.inp``-Datei. CalculiX wird **ohne FreeCAD** aufgerufen — die
    Binärdatei liegt in derselben pixi-Umgebung, aus der auch der FreeCAD-Weg sie holt
    (``freecad_runner.CCX_CMD``), nur ohne den 40-s-Start des Unterprozesses.
    """
    import subprocess

    if not os.path.isfile(CCX_CMD):
        return {"solver_status": "CCX_FEHLT", "meldung": f"kein ccx unter {CCX_CMD}"}
    ordner = os.path.dirname(os.path.abspath(pfad))
    name   = os.path.splitext(os.path.basename(pfad))[0]
    for endung in (".frd", ".dat", ".sta", ".cvg"):
        try:
            os.remove(os.path.join(ordner, name + endung))   # keine Altstaende
        except OSError:
            pass

    env = dict(os.environ)
    env["OMP_NUM_THREADS"] = str(max(1, int(kerne)))
    try:
        r = subprocess.run([CCX_CMD, name], cwd=ordner, env=env,
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return {"solver_status": "ZEITUEBERSCHREITUNG",
                "meldung": f"ccx ueber {timeout} s"}

    frd = os.path.join(ordner, name + ".frd")
    # Der DISP-Block steht am ENDE der .frd, nicht am Anfang — nur die ersten Kilobytes
    # zu lesen meldet an jedem groesseren Lauf faelschlich einen Fehlschlag.
    if not os.path.isfile(frd) or not _frd_hat_disp(frd):
        hinweis = [z for z in (r.stdout or "").splitlines() if "ERROR" in z.upper()]
        return {"solver_status": "KEINE_ERGEBNISSE", "returncode": r.returncode,
                "meldung": " | ".join(hinweis[:3]) or (r.stdout or "")[-300:]}
    return {"solver_status": "OK", "returncode": r.returncode,
            "frd": frd, "dat": os.path.join(ordner, name + ".dat")}


def _frd_hat_disp(frd: str) -> bool:
    """Traegt die .frd wirklich einen Verschiebungsblock? (ergebnislose .frd erkennen)"""
    with open(frd, errors="ignore") as f:
        return any(" -4  DISP" in z for z in f)


def lies_dat_spannungen(pfad: str) -> dict:
    """CalculiX-``.dat`` → ``{element: (sxx, syy, szz, sxy, sxz, syz)}``.

    **Achtung Spaltenreihenfolge:** die ``.dat`` schreibt ``sxx syy szz sxy sxz syz``,
    das ``.frd`` dagegen ``sxx syy szz sxy syz szx``. Wer die beiden verwechselt,
    bekommt eine plausibel aussehende, falsche Vergleichsspannung.
    """
    werte, drin = {}, False
    for L in open(pfad, errors="ignore"):
        t = L.strip()
        if not t:
            continue
        if t.lower().startswith("stresses"):
            drin = True
            continue
        if drin and not t[0].isdigit():
            drin = False
            continue
        if not drin:
            continue
        w = t.split()
        if len(w) < 8:
            continue
        try:
            werte[int(w[0])] = tuple(float(x) for x in w[2:8])
        except ValueError:
            continue
    return werte


def von_mises(sxx, syy, szz, s12, s13, s23) -> float:
    return math.sqrt(0.5 * ((sxx - syy) ** 2 + (syy - szz) ** 2 + (szz - sxx) ** 2
                            + 6.0 * (s12 * s12 + s13 * s13 + s23 * s23)))


def element_mitte(netz: Netz, eid: int):
    """Schwerpunkt der vier Eckknoten [mm] — auch bei Tet10 die Elementmitte."""
    ids = netz.elemente[eid][:4]
    return tuple(sum(netz.knoten[i][k] for i in ids) / 4.0 for k in range(3))


def kennzahlen(netz: Netz, spannungen: dict, yield_mpa: float = 0.0,
               bohrung_faktor: float = 1.06) -> dict:
    """Vergleichbare Kennzahlen aus elementweisen Spannungen — für beide Löser gleich.

    ``spannungen``: ``{element: (sxx, syy, szz, s_xy, s_xz, s_yz)}``.

    Geliefert werden Spitze und **P99** der Vergleichsspannung (die Spitze allein hängt
    am Netz und sitzt an einer Taschenecke) sowie der Median der **Ringspannung an der
    Bohrung** — die einzige Größe, für die es eine geschlossene Vergleichsformel gibt
    (``ema_rotorcheck._bore_hoop_mpa``).
    """
    vm, hoop = [], []
    grenze = netz.r_shaft * bohrung_faktor
    for eid, (sxx, syy, szz, s12, s13, s23) in spannungen.items():
        vm.append(von_mises(sxx, syy, szz, s12, s13, s23))
        if eid not in netz.elemente:
            continue
        x, y, _z = element_mitte(netz, eid)
        r = math.hypot(x, y)
        if 1e-9 < r <= grenze:
            c, sn = x / r, y / r
            hoop.append(sn * sn * sxx - 2 * c * sn * s12 + c * c * syy)
    if not vm:
        return {"solver_status": "KEINE_SPANNUNGEN"}
    vm.sort()
    hoop.sort()
    p99 = vm[min(len(vm) - 1, int(0.99 * len(vm)))]
    aus = {"stress_peak_MPa": round(vm[-1], 2),
           "stress_p99_MPa": round(p99, 2),
           "stress_mean_MPa": round(sum(vm) / len(vm), 2),
           "n_elemente": len(vm)}
    if hoop:
        aus["bore_hoop_median_MPa"] = round(hoop[len(hoop) // 2], 2)
        aus["bore_hoop_n"] = len(hoop)
    if yield_mpa > 0 and p99 > 0:
        aus["safety_factor_p99"] = round(yield_mpa / p99, 2)
    return aus
