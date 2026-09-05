"""ASM-Feld harmonisch in 3-D (Elmer ``WhitneyAVHarmonicSolver``) -- Stufe D.

Wozu, wenn Stufe B schon rechnet
---------------------------------

Weil Stufe B eine Sache **grundsaetzlich** nicht kann und das auch sagt: ein
2-D-Querschnitt hat keine Stirnseite. Die Kaefigstaebe sind dort ideal
kurzgeschlossen, der **Kurzschlussring fehlt**. Die analytische Stufe schlaegt
ihn mit ``ema_asm.KURZSCHLUSSRING_ZUSCHLAG = 0,20`` auf -- eine Zahl, die
gesetzt und nie gemessen wurde.

Diese Stufe misst sie. Gerechnet wird dieselbe Maschine, mit demselben
Querschnitt (``ema_em2d_harm.quer_flaechen`` -- eine Geometrie, nicht zwei),
aber in die Laenge gezogen und mit beiden Ringen. Der Unterschied zwischen
Stufe B und Stufe D ist damit **genau der Ring** und sonst nichts.

Das ist der Sinn einer Gegenrechnung: nicht ein zweites, besseres Ergebnis,
sondern eine Aussage darueber, was im ersten fehlte.

Wie das Modell gebaut ist
--------------------------

* Der 2-D-Querschnitt wird ueber die Paketlaenge extrudiert. Alle Koerper
  (Welle, Laeuferblech, Staebe, Stege, Luftspalt, Statoreisen, Nuten) behalten
  ihre Rolle.
* An beiden Stirnseiten sitzt je ein **Kurzschlussring** mit dem Querschnitt,
  den ``ema_asm.kaefig`` ansetzt -- derselbe Wert, der im CAD gezeichnet wird.
* Um die Stirnseiten liegt **Luft**, sonst haette das Stirnfeld keinen Weg und
  der Ring waere wieder nur ein Widerstand ohne Feld.
* Leitfaehigkeit ``sigma_eff = s*sigma`` auf Staeben UND Ringen -- dieselbe
  Herleitung wie in Stufe B (dort im Modulkopf), damit beide Stufen denselben
  Betriebspunkt meinen.
* Statorstrom als Stromdichte je Nut, aus derselben 60-Grad-Zonenwicklung
  (``ema_em2d_harm.stator_stroeme``).

Was FEHLT, und warum das den Feldlauf heute unbrauchbar macht
--------------------------------------------------------------

In 3-D muss sich der Statorstrom **schliessen**. ``ema_em3d`` loest das fuer die
Magnetostatik mit zwei Stirnring-Leitern, die den azimutalen Rueckstrom tragen,
und haelt im Modulkopf fest, was ohne sie passiert: „sonst explodiert das
Vektorpotential (B~10^4 T)".

**Diese Ringe gibt es hier nicht.** Der Kopf dieses Moduls hat sie eine Zeit
lang beschrieben, obwohl sie nirgends gebaut wurden -- und das Ergebnis war
genau das angekuendigte: gemessen 2,7*10^6 T Flussdichte und eine Stromdichte
von 1,2*10^10 A/m^2. Das ist kein Feld, sondern ein offener Strompfad.

Bis die Rueckleiter da sind, ist der **Feldlauf dieser Stufe nicht gueltig**.
``pruefe_feld`` weist ein solches Ergebnis darum ausdruecklich ab, statt Zahlen
herauszugeben, die niemandem widersprechen. Nutzbar ist heute allein
``netzkosten()`` -- die Netzgroesse und ihre Kosten, und die sind gemessen.

Der Kurzschlussring-Vergleich (``ring_wirkung``) ist damit vorbereitet, aber
noch nicht belegt: er braucht ein gueltiges Feld.

Was hier bewusst NICHT gerechnet wird
--------------------------------------

* **Keine Schraegung.** Sie waere in 3-D moeglich und ist ein eigener Schritt.
* **Lineares Eisen** wie in Stufe B, Steg gesaettigt angesetzt.
* **Keine Schraegung.**

Der Luftspalt ist hier NICHT aufgeloest -- und warum das trotzdem geht
-----------------------------------------------------------------------

Das ist die wichtigste Einschraenkung dieser Stufe, und sie ist gemessen:

    Verfeinerungsband auf den Luftspalt (0,7 mm), 150 mm Paket:
        nach 1 h 56 min abgebrochen, kein Netz
        zweiter Versuch, 500 s Deckel: kein Netz
    ohne Verfeinerungsband, 3 mm kleinstes Element, 30 mm Paket:
        30.010 Tetraeder in 3 s
    ohne Verfeinerungsband, 2 mm kleinstes Element, 60 mm Paket:
        79.345 Tetraeder in 14 s
    volles Modell mit Ringen und Stirnluft, 1,5 mm, 60 mm Paket:
        138.666 Tetraeder in 26 s (Geometrie davon 10 s)

Ein Luftspalt von 0,7 mm ueber 0,6 m Umfang und 0,15 m Laenge braucht in 3-D
Millionen Elemente -- auf dieser Maschine nicht rechenbar. Mit 2-3 mm grossen
Elementen ist der Spalt dagegen gar nicht aufgeloest, und das **absolute**
Moment aus einem solchen Netz waere keine Aussage.

Das Netz ist damit NICHT der teure Teil dieser Stufe -- der Loeser ist es. Ein
harmonisches Kantenelement-System ist komplex und hat doppelt so viele
Unbekannte wie das magnetostatische; ``netzkosten()`` laesst sich deshalb
einzeln aufrufen, um die Netzgroesse zu kennen, BEVOR ein Lauf gestartet wird.

Deshalb misst diese Stufe kein absolutes Moment, sondern ein **Verhaeltnis**:
``ring_wirkung()`` loest ZWEIMAL auf demselben Netz -- einmal mit leitenden
Kurzschlussringen, einmal mit isolierenden. Alles andere ist identisch, bis auf
das letzte Element. Der Netzfehler steckt in beiden Laeufen gleich und faellt im
Verhaeltnis weitgehend heraus.

Und genau das Verhaeltnis ist die Frage: ``ema_asm`` schlaegt den Ring mit
``KURZSCHLUSSRING_ZUSCHLAG = 0,20`` auf -- eine Zahl, die gesetzt und nie
gemessen wurde. Ein absolutes 3-D-Moment haette sie nicht ueberpruefen koennen;
dieses Verhaeltnis kann es.
"""

from __future__ import annotations

import math
import os

import elmer_runner
import ema_em2d_harm as H

MU0 = H.MU0

# Physikalische Gruppen-Nummern der 3-D-Stufe. Wieder luecklos ab 1, aus dem
# Grund, der in ``ema_em2d_harm`` steht: ``ElmerGrid -autoclean`` nummeriert um.
GID_WELLE  = 1
GID_ROTOR  = 2
GID_STAEBE = 3
GID_STEG   = 4
GID_LUFT   = 5
GID_STATOR = 6
GID_RING   = 7          # beide Kurzschlussringe
GID_STIRN  = 8          # Luft an den Stirnseiten
GID_NUT0   = 9          # Nut k -> GID_NUT0 + k
GID_RAND   = 1          # Aussenflaeche (eigener Nummernkreis, 2D)

# Axiale Laenge der Stirnluft, als Vielfaches der Ringbreite. Zu kurz gewaehlt
# klemmt die Randbedingung das Stirnfeld ab und der Ring erscheint wirkungslos.
STIRNLUFT_FAKTOR = 3.0


def baue_netz(geom: dict, kaefig: dict, axial_mm: float, msh_pfad: str,
              gap_lagen: int = 2, lc_eisen_mm: float = 0.0,
              lagen_axial: int = 6) -> dict:
    """3-D-Netz: Querschnitt extrudiert, plus beide Ringe und die Stirnluft."""
    import gmsh

    gmsh.initialize()
    gmsh.option.setNumber("General.Terminal", 0)
    try:
        gmsh.model.add("asm3d")
        occ = gmsh.model.occ
        q = H.quer_flaechen(gmsh, geom, kaefig)
        m = q["masse"]
        L = float(axial_mm) / 1000.0

        # Ringquerschnitt als Rechteck mit dem Seitenverhaeltnis des Stabes --
        # dieselbe Umrechnung wie im CAD (ema_freecad), damit Modell und
        # Zeichnung denselben Ring meinen.
        a_ring = m["A_ring_m2"]
        ring_h = math.sqrt(a_ring * m["t_stab"] / max(m["b_stab"], 1e-6))
        ring_w = math.sqrt(a_ring * m["b_stab"] / max(m["t_stab"], 1e-6))
        ring_h = min(ring_h, m["r_stab_a"] - m["r_wel"] - 1e-3)
        stirn = STIRNLUFT_FAKTOR * ring_w

        flaechen = ([(2, t) for t in q["welle"] + q["rotor"] + q["staebe"]
                     + q["stege"] + q["luft"] + q["stator"]]
                    + [(2, t) for f in q["nut_f"] for t in f])
        aus = occ.extrude(flaechen, 0, 0, L)
        occ.synchronize()

        # ``extrude`` gibt je Eingangsflaeche vier Eintraege zurueck
        # (Deckflaeche, Volumen, Mantelflaechen); das Volumen ist der Eintrag
        # mit dim == 3. Die Reihenfolge folgt der Eingabe, also laesst sich
        # jedem Koerper sein Volumen ohne Schwerpunktsuche zuordnen.
        vols = [t for (d, t) in aus if d == 3]
        if len(vols) != len(flaechen):
            raise RuntimeError(f"Extrusion gab {len(vols)} Volumen fuer "
                               f"{len(flaechen)} Flaechen")
        i = 0
        gruppen = {}
        for name in ("welle", "rotor", "staebe", "stege", "luft", "stator"):
            n = len(q[name])
            gruppen[name] = vols[i:i + n]
            i += n
        nut_v = []
        for f in q["nut_f"]:
            nut_v.append(vols[i:i + len(f)])
            i += len(f)

        # Kurzschlussringe an beiden Stirnseiten.
        ringe = []
        for z0 in (-ring_w, L):
            aussen = occ.addCylinder(0, 0, z0, 0, 0, ring_w, m["r_stab_a"])
            innen = occ.addCylinder(0, 0, z0 - 1e-4, 0, 0, ring_w + 2e-4,
                                    max(m["r_stab_a"] - ring_h, 1e-4))
            r, _ = occ.cut([(3, aussen)], [(3, innen)])
            ringe.append(r[0][1])

        # Stirnluft: zwei Zylinder bis r_so, aus denen die Ringe geschnitten sind.
        stirnluft = []
        for z0 in (-ring_w - stirn, L):
            zyl = occ.addCylinder(0, 0, z0, 0, 0, ring_w + stirn, m["r_so"])
            stirnluft.append(zyl)
        out, abb = occ.fragment([(3, t) for t in stirnluft],
                                [(3, t) for t in ringe])
        occ.synchronize()
        # Was aus den Ringen kam, IST der Ring; der Rest der Stirnzylinder ist Luft.
        ring_v = set()
        for grp in abb[len(stirnluft):]:
            ring_v.update(t for (d, t) in grp if d == 3)
        stirn_v = set()
        for grp in abb[:len(stirnluft)]:
            stirn_v.update(t for (d, t) in grp if d == 3)
        stirn_v -= ring_v
        if not ring_v:
            raise RuntimeError("Kurzschlussringe nach dem Verschneiden nicht "
                               "wiedergefunden")

        # Alles zusammenkleben, damit die Felder ueber die Stirnflaeche stetig sind.
        alle = ([(3, t) for t in vols] + [(3, t) for t in sorted(ring_v)]
                + [(3, t) for t in sorted(stirn_v)])
        _, abb2 = occ.fragment(alle[:1], alle[1:])
        occ.synchronize()

        def neu(alte):
            aus_ = []
            for t in alte:
                idx = [k for k, (d, x) in enumerate(alle) if d == 3 and x == t]
                if idx:
                    aus_ += [v for (d, v) in abb2[idx[0]] if d == 3]
            return sorted(set(aus_))

        gmsh.model.addPhysicalGroup(3, neu(gruppen["welle"]), GID_WELLE, "welle")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["rotor"]), GID_ROTOR, "rotoreisen")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["staebe"]), GID_STAEBE, "staebe")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["stege"]), GID_STEG, "stege")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["luft"]), GID_LUFT, "luftspalt")
        gmsh.model.addPhysicalGroup(3, neu(gruppen["stator"]), GID_STATOR, "statoreisen")
        gmsh.model.addPhysicalGroup(3, neu(sorted(ring_v)), GID_RING, "ringe")
        gmsh.model.addPhysicalGroup(3, neu(sorted(stirn_v)), GID_STIRN, "stirnluft")
        for k, v in enumerate(nut_v):
            gmsh.model.addPhysicalGroup(3, neu(v), GID_NUT0 + k, f"nut{k}")

        # Aussenrand: alle Flaechen auf r_so plus die beiden aeusseren Stirnflaechen.
        rand = []
        for (d, t) in gmsh.model.getEntities(2):
            bb = gmsh.model.getBoundingBox(2, t)
            weite = max(bb[3] - bb[0], bb[4] - bb[1]) / 2.0
            z_lo, z_hi = bb[2], bb[5]
            aussen_zyl = abs(weite - m["r_so"]) < 1e-4 * m["r_so"] + 1e-9 \
                and (z_hi - z_lo) > 1e-6
            stirn_flaeche = abs(z_hi - z_lo) < 1e-9 and (
                abs(z_lo + ring_w + stirn) < 1e-9 or abs(z_lo - (L + ring_w + stirn)) < 1e-9)
            if aussen_zyl or stirn_flaeche:
                rand.append(t)
        if not rand:
            raise ValueError("Aussenrand nicht gefunden")
        gmsh.model.addPhysicalGroup(2, rand, GID_RAND, "aussenrand")

        # KEIN Verfeinerungsband auf den Luftspalt (anders als in 2-D). Gemessen:
        # mit Band bricht das Netzen bei 0,7 mm Spalt und 150 mm Paket nach
        # 1 h 56 min ohne Ergebnis ab; ohne Band stehen 30.010 Tetraeder in 3 s.
        # Der Spalt ist damit nicht aufgeloest -- das absolute Moment aus diesem
        # Netz waere keine Aussage, das Verhaeltnis zweier Laeufe darauf schon
        # (s. Modulkopf und ``ring_wirkung``).
        lc_eisen = (lc_eisen_mm / 1000.0) if lc_eisen_mm > 0 else max(
            L / max(int(lagen_axial), 1), 4.0e-3)
        lc_gap = max(m["gap_m"] / max(int(gap_lagen), 1), 1.5e-3)
        gmsh.option.setNumber("Mesh.MeshSizeFromPoints", 0)
        gmsh.option.setNumber("Mesh.MeshSizeFromCurvature", 0)
        gmsh.option.setNumber("Mesh.MeshSizeExtendFromBoundary", 0)
        gmsh.option.setNumber("Mesh.MeshSizeMin", lc_gap)
        gmsh.option.setNumber("Mesh.MeshSizeMax", lc_eisen)
        gmsh.option.setNumber("Mesh.Algorithm3D", 10)      # HXT, schnell
        gmsh.model.mesh.generate(3)

        gmsh.option.setNumber("Mesh.MshFileVersion", 2.2)
        gmsh.option.setNumber("Mesh.SaveAll", 0)
        os.makedirs(os.path.dirname(os.path.abspath(msh_pfad)) or ".", exist_ok=True)
        gmsh.write(msh_pfad)
        knoten = len(gmsh.model.mesh.getNodes()[0])
        _, el, _ = gmsh.model.mesh.getElements(3)
        tets = sum(len(e) for e in el)
    finally:
        gmsh.finalize()

    return {"msh": msh_pfad, "knoten": int(knoten), "tets": int(tets),
            "n_stab": m["n_stab"], "n_nut": len(q["nuten"]),
            "L_m": L, "ring_h_m": ring_h, "ring_w_m": ring_w,
            "A_ring_m2": a_ring, "stirn_m": stirn,
            "r_wel": m["r_wel"], "r_rot": m["r_rot"], "r_si": m["r_si"],
            "r_so": m["r_so"], "gap_m": m["gap_m"],
            "lc_gap_m": lc_gap, "lc_eisen_m": lc_eisen,
            "A_nut_m2": q["A_nut_m2"], "A_stab_m2": float(kaefig["A_stab_mm2"]) * 1e-6}


def schreibe_sif(netz: dict, omega1: float, sigma_eff: float, j_nut: dict,
                 work_dir: str, mu_r_steg: float, mesh_name: str = "mesh",
                 ring_leitet: bool = True) -> str:
    """``case.sif`` fuer ``WhitneyAVHarmonicSolver`` (3-D, komplex)."""
    os.makedirs(os.path.join(work_dir, "results"), exist_ok=True)
    n_nut = int(netz["n_nut"])

    S = [f'Header\n  Mesh DB "." "{mesh_name}"\nEnd\n',
         "Simulation\n"
         "  Max Output Level = 4\n"
         "  Coordinate System = Cartesian\n"
         "  Simulation Type = Steady State\n"
         "  Steady State Max Iterations = 1\n"
         "  Output Intervals = 1\nEnd\n",
         f"Constants\n  Permeability of Vacuum = {MU0:.12e}\nEnd\n"]

    koerper = [(GID_WELLE, 1, None), (GID_ROTOR, 1, None), (GID_STAEBE, 3, None),
               (GID_STEG, 4, None), (GID_LUFT, 2, None), (GID_STATOR, 1, None),
               (GID_RING, 3 if ring_leitet else 2, None), (GID_STIRN, 2, None)]
    koerper += [(GID_NUT0 + k, 2, k + 1) for k in range(n_nut)]
    for i, (gid, mat, bf) in enumerate(koerper, start=1):
        S.append(f"Body {i}\n  Target Bodies(1) = {gid}\n  Equation = 1\n"
                 f"  Material = {mat}\n"
                 + (f"  Body Force = {bf}\n" if bf else "") + "End\n")

    S.append(f"Material 1\n  Relative Permeability = {H.MU_R_EISEN}\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    S.append("Material 2\n  Relative Permeability = 1.0\n"
             "  Electric Conductivity = 0.0\nEnd\n")
    # Staebe UND Ringe leiten. Der Ring ist der ganze Grund fuer diese Stufe:
    # in 2-D gibt es ihn nicht, hier traegt er Strom und Feld.
    S.append("! sigma_eff = s*sigma (Herleitung im Kopf von ema_em2d_harm).\n"
             f"Material 3\n  Relative Permeability = 1.0\n"
             f"  Electric Conductivity = {sigma_eff:.6e}\nEnd\n")
    S.append(f"Material 4\n  Relative Permeability = {mu_r_steg}\n"
             "  Electric Conductivity = 0.0\nEnd\n")

    for k in range(n_nut):
        j = j_nut.get(H.GID_NUT0 + k, 0j)
        S.append(f"Body Force {k + 1}\n"
                 f"  Current Density 3 = Real {j.real:.6e}\n"
                 f"  Current Density Im 3 = Real {j.imag:.6e}\nEnd\n")

    # Direkter Loeser (MUMPS), NICHT iterativ. ``ema_em3d`` hat denselben Fehler
    # schon einmal gelernt und im Modulkopf festgehalten: „der iterative
    # BiCGStabL stagniert ohne aufwaendige Vorkonditionierung" am
    # curl-curl-Kantenelement-System. Gemessen hier: 6000 Iterationen, Residuum
    # bleibt bei 1,5, neunzehn Minuten Rechenzeit und am Ende kein Feld.
    # MUMPS geht auf Tetraedern mit der niedrigst-ordnigen Kantenbasis und dem
    # Tree-Gauge -- beides ist hier der Fall.
    S.append("Solver 1\n"
             '  Equation = "MgDyn3DHarmonic"\n'
             '  Procedure = "MagnetoDynamics" "WhitneyAVHarmonicSolver"\n'
             '  Variable = "AV[AV re:1 AV im:1]"\n'
             f"  Angular Frequency = Real {omega1:.9e}\n"
             "  Use Tree Gauge = Logical True\n"
             "  Linear System Solver = Direct\n"
             "  Linear System Direct Method = MUMPS\n"
             "  Steady State Convergence Tolerance = 1.0e-8\n"
             "End\n")
    # Der Nachbearbeitungsloeser braucht seinen EIGENEN Gleichungsloeser. Ohne
    # ihn bricht Elmer nach dem Hauptlauf ab:
    #     ERROR:: SolveLinearSystem: Give "Linear System Solver"
    # Das kostet den ganzen Lauf, und zwar NACH der teuren Rechnung -- der
    # Fehler faellt also erst auf, wenn alles gerechnet ist. Dieselben
    # Einstellungen wie in ``ema_em3d`` (CG + ILU0): das Feld-System dort ist
    # symmetrisch positiv definit und braucht kein BiCGStabL.
    S.append("Solver 2\n"
             '  Equation = "MgDynCalc"\n'
             '  Procedure = "MagnetoDynamics" "MagnetoDynamicsCalcFields"\n'
             '  Potential Variable = String "AV"\n'
             "  Calculate Magnetic Field Strength = Logical True\n"
             "  Calculate Joule Heating = Logical True\n"
             "  Calculate Current Density = Logical True\n"
             "  Linear System Solver = Iterative\n"
             "  Linear System Iterative Method = CG\n"
             "  Linear System Preconditioning = ILU0\n"
             "  Linear System Max Iterations = 5000\n"
             "  Linear System Convergence Tolerance = 1.0e-8\n"
             "End\n")
    S.append("Solver 3\n"
             '  Equation = "ErgebnisAusgabe"\n'
             '  Procedure = "ResultOutputSolve" "ResultOutputSolver"\n'
             '  Output File Name = "asm3d"\n'
             '  Output Format = String "vtu"\n'
             "  Save Geometry Ids = Logical True\n"
             '  Output Directory = "results"\n'
             "  Vtu Format = Logical True\n"
             "End\n")
    S.append("Equation 1\n  Active Solvers(3) = 1 2 3\nEnd\n")
    S.append(f"Boundary Condition 1\n  Target Boundaries(1) = {GID_RAND}\n"
             "  AV re {e} = Real 0.0\n  AV im {e} = Real 0.0\n"
             "  AV re = Real 0.0\n  AV im = Real 0.0\nEnd\n")

    pfad = os.path.join(work_dir, "case.sif")
    with open(pfad, "w") as fh:
        fh.write("\n".join(S))
    with open(os.path.join(work_dir, "ELMERSOLVER_STARTINFO"), "w") as fh:
        fh.write("case.sif\n1\n")
    return pfad


def netzkosten(geom: dict, kaefig: dict, axial_mm: float, work_dir: str,
               gap_lagen: int = 2, lagen_axial: int = 6,
               lc_eisen_mm: float = 0.0, log=None) -> dict:
    """Nur das Netz bauen und **messen**, was diese Stufe kostet.

    Getrennt aufrufbar, weil die Netzgroesse in 3-D die eigentliche Frage ist:
    ein Luftspalt von 0,7 mm ueber 0,6 m Umfang laesst sich beliebig teuer
    aufloesen. Wer wissen will, ob ein Lauf ueberhaupt in Frage kommt, soll das
    erfahren, ohne ihn zu starten.
    """
    import time
    t0 = time.time()
    msh = os.path.join(work_dir, "asm3d.msh")
    os.makedirs(work_dir, exist_ok=True)
    netz = baue_netz(geom, kaefig, axial_mm, msh, gap_lagen=gap_lagen,
                     lc_eisen_mm=lc_eisen_mm, lagen_axial=lagen_axial)
    netz["netzzeit_s"] = round(time.time() - t0, 1)
    if log:
        log(f"3-D-Netz: {netz['tets']} Tetraeder, {netz['knoten']} Knoten "
            f"in {netz['netzzeit_s']:.0f} s")
    return netz


def _loese(ctx: dict, ring_leitet: bool, timeout: int) -> dict:
    """EIN 3-D-Lauf auf dem vorhandenen Netz."""
    schreibe_sif(ctx["netz"], ctx["omega1"], ctx["sigma_eff"], ctx["j_nut"],
                 ctx["work_dir"], ctx["mu_r_steg"], ring_leitet=ring_leitet)
    rs = elmer_runner.run_elmersolver(os.path.join(ctx["work_dir"], "case.sif"),
                                      ctx["work_dir"], timeout=timeout)
    if not rs.get("ok"):
        raise RuntimeError("ElmerSolver (3-D): "
                           + (rs.get("stderr") or rs.get("error", ""))[:400]
                           + "\n" + rs.get("stdout", "")[-1500:])
    vtu = _finde_vtu(os.path.join(ctx["work_dir"], "results"))
    if not vtu:
        raise RuntimeError("Keine Ergebnisdatei geschrieben — "
                           "ResultOutputSolver pruefen")
    # ERST pruefen, ob es ueberhaupt ein Feld ist. Ein offener Strompfad gibt
    # keine Fehlermeldung, sondern Zahlen -- und die sehen aus wie Ergebnisse.
    feld = pruefe_feld(vtu)
    p_je_koerper = verluste_je_koerper(vtu)
    joule = sum(p_je_koerper.get(g, 0.0) for g in (GID_STAEBE, GID_RING))
    s = ctx["schlupf"]
    omega_syn_mech = ctx["omega1"] / ctx["p"]
    return {"P_luftspalt_W": round(joule, 1),
            "P_laeufer_W": round(s * joule, 1),
            "T_leistung_Nm": round(joule / max(omega_syn_mech, 1e-12), 3),
            "P_staebe_W": round(p_je_koerper.get(GID_STAEBE, 0.0), 1),
            "P_ringe_W": round(p_je_koerper.get(GID_RING, 0.0), 1),
            "B_max_T": feld["B_max_T"], "vtu": vtu,
            "ring_leitet": ring_leitet}


def _aufbau(payload: dict, rpm: float, last_nm: float, work_dir: str,
            schlupf: float, mu_r_steg: float, gap_lagen: int,
            lagen_axial: int, lc_eisen_mm: float, log=None) -> dict:
    """Betriebspunkt, Netz und ElmerGrid -- alles, was beide Laeufe teilen."""
    import ema_asm
    import ema_maschinenart
    import ema_radien
    from ema_pipeline import HAIRPIN_MATS

    geom = payload.get("geom", payload)
    art = ema_maschinenart.art_code(payload)
    ema_maschinenart.pruefe_stufe(art, "em3d")
    ema_radien.pruefe_bauform(payload, "em3d")   # Netz ist auf Innenlaeufer gebaut
    if art != "asm":
        raise ema_maschinenart.ArtNichtUnterstuetzt(
            f"Die harmonische 3-D-Stufe ist die Kaefiglaeufer-Stufe; "
            f"'{art}' gehoert nicht hierher.")

    axial = float(geom.get("axialLen") or payload.get("axial_len") or 80.0)
    p = max(int(geom["p"]), 1)
    bp = ema_asm.betriebspunkt(geom, axial, rpm, last_nm)
    kf = dict(bp["kaefig"])
    kf["steg_mm"] = ema_asm.KAEFIG_STEG_MM
    s = max(float(schlupf) or float(bp["schlupf"]), H.S_MIN)
    mu = float(mu_r_steg) or H.MU_R_STEG

    mat = HAIRPIN_MATS.get(geom.get("barMat") or ema_asm.KAEFIG_VORGABE,
                           HAIRPIN_MATS[ema_asm.KAEFIG_VORGABE])
    sigma_eff = s * (1.0 / float(mat["rho_el"]))
    omega1 = 2.0 * math.pi * p * float(rpm) / 60.0

    netz = netzkosten(geom, kf, axial, work_dir, gap_lagen=gap_lagen,
                      lagen_axial=lagen_axial, lc_eisen_mm=lc_eisen_mm, log=log)
    mesh_dir = os.path.join(work_dir, "mesh")
    if log:
        log("ElmerGrid: 3-D-Netz umsetzen…")
    rg = elmer_runner.run_elmergrid(netz["msh"], mesh_dir)
    if not rg.get("ok"):
        raise RuntimeError("ElmerGrid: " + (rg.get("stderr") or rg.get("error", ""))[:300])

    i_pk_phys = float(bp["I_s_A"]) / max(ema_asm.k_norm(geom), 1e-12)
    return {"geom": geom, "p": p, "bp": bp, "netz": netz, "work_dir": work_dir,
            "omega1": omega1, "sigma_eff": sigma_eff, "schlupf": s,
            "mu_r_steg": mu, "axial_mm": axial,
            "j_nut": H.stator_stroeme(geom, i_pk_phys, netz["A_nut_m2"]),
            "stabmaterial": mat["label"], "i_pk_phys": i_pk_phys}


def ring_wirkung(payload: dict, rpm: float, last_nm: float, work_dir: str,
                 schlupf: float = 0.0, mu_r_steg: float = 0.0,
                 gap_lagen: int = 1, lagen_axial: int = 6,
                 lc_eisen_mm: float = 8.0, timeout: int = 7200,
                 log=None) -> dict:
    """Was der Kurzschlussring ausmacht -- zweimal dasselbe Netz, einmal ohne ihn.

    Der einzige Unterschied zwischen den beiden Laeufen ist die Leitfaehigkeit
    der Ringe. Netz, Betriebspunkt, Statorstrom, Schlupf, Steg-Permeabilitaet:
    identisch. Der Netzfehler eines nicht aufgeloesten Luftspalts steckt damit in
    beiden Zahlen gleich und faellt im Verhaeltnis weitgehend heraus.

    Verglichen wird gegen ``ema_asm.KURZSCHLUSSRING_ZUSCHLAG`` -- die 20 %, mit
    denen die analytische Stufe den Ring bisher ansetzt, ohne ihn je gemessen zu
    haben.
    """
    import ema_asm

    def _log(t):
        if log:
            log(t)

    ctx = _aufbau(payload, rpm, last_nm, work_dir, schlupf, mu_r_steg,
                  gap_lagen, lagen_axial, lc_eisen_mm, log=log)
    _log(f"ElmerSolver: 3-D harmonisch MIT Ring "
         f"({ctx['netz']['tets']} Tetraeder)…")
    mit = _loese(ctx, True, timeout)
    _log("ElmerSolver: derselbe Lauf OHNE Ring (Ringe isolierend)…")
    ohne = _loese(ctx, False, timeout)

    t_mit, t_ohne = mit["T_leistung_Nm"], ohne["T_leistung_Nm"]
    anteil = (t_mit - t_ohne) / max(abs(t_mit), 1e-12)
    return {
        "T_mit_Ring_Nm": t_mit, "T_ohne_Ring_Nm": t_ohne,
        "P_mit_Ring_W": mit["P_luftspalt_W"], "P_ohne_Ring_W": ohne["P_luftspalt_W"],
        "ring_anteil": round(anteil, 4),
        "ring_anteil_pct": round(100.0 * anteil, 2),
        "zuschlag_analytisch_pct": round(100.0 * ema_asm.KURZSCHLUSSRING_ZUSCHLAG, 1),
        "schlupf": ctx["schlupf"], "mu_r_steg": ctx["mu_r_steg"],
        "f1_Hz": round(ctx["omega1"] / (2 * math.pi), 2),
        "tets": ctx["netz"]["tets"], "knoten": ctx["netz"]["knoten"],
        "netzzeit_s": ctx["netz"]["netzzeit_s"],
        "ring_h_mm": round(1000 * ctx["netz"]["ring_h_m"], 2),
        "ring_w_mm": round(1000 * ctx["netz"]["ring_w_m"], 2),
        "gap_aufgeloest": bool(ctx["netz"]["lc_gap_m"] <= ctx["netz"]["gap_m"]),
        "work_dir": work_dir, "analytisch": ctx["bp"],
    }


def rechne(payload: dict, rpm: float, last_nm: float, work_dir: str,
           schlupf: float = 0.0, mu_r_steg: float = 0.0, gap_lagen: int = 1,
           lagen_axial: int = 6, lc_eisen_mm: float = 8.0,
           timeout: int = 7200, log=None) -> dict:
    """EIN 3-D-Lauf. Das absolute Moment steht unter dem Vorbehalt des Netzes.

    Wer wissen will, was der Kurzschlussring ausmacht, nimmt ``ring_wirkung`` --
    dort faellt der Netzfehler im Verhaeltnis heraus. Diese Funktion gibt den
    einzelnen Lauf, und sie sagt im Ergebnis (``gap_aufgeloest``), ob der
    Luftspalt ueberhaupt aufgeloest war.
    """
    ctx = _aufbau(payload, rpm, last_nm, work_dir, schlupf, mu_r_steg,
                  gap_lagen, lagen_axial, lc_eisen_mm, log=log)
    if log:
        log(f"ElmerSolver: 3-D harmonisch, {ctx['netz']['tets']} Tetraeder, "
            f"{ctx['omega1'] / (2 * math.pi):.1f} Hz, "
            f"Schlupf {100 * ctx['schlupf']:.2f} %…")
    r = _loese(ctx, True, timeout)
    r.update({
        "schlupf": ctx["schlupf"], "mu_r_steg": ctx["mu_r_steg"],
        "f1_Hz": round(ctx["omega1"] / (2 * math.pi), 2),
        "sigma_eff_S_m": round(ctx["sigma_eff"], 1),
        "tets": ctx["netz"]["tets"], "knoten": ctx["netz"]["knoten"],
        "netzzeit_s": ctx["netz"]["netzzeit_s"],
        "ring_h_mm": round(1000 * ctx["netz"]["ring_h_m"], 2),
        "ring_w_mm": round(1000 * ctx["netz"]["ring_w_m"], 2),
        "gap_aufgeloest": bool(ctx["netz"]["lc_gap_m"] <= ctx["netz"]["gap_m"]),
        "work_dir": work_dir, "analytisch": ctx["bp"],
    })
    return r


# Groesste Flussdichte, die in einer Maschine noch vorstellbar ist. Kobalt-Eisen
# saettigt bei rund 2,3 T; an einer Kante rechnet ein P1-Netz auch einmal das
# Doppelte. 20 T ist also grosszuegig um den Faktor zehn -- wer darueber liegt,
# hat kein Feld, sondern einen Rechenfehler. Genau dieser Fall ist hier
# eingetreten (gemessen 2,7*10^6 T, s. Modulkopf).
B_UNMOEGLICH_T = 20.0


def _lies_vtu_zellen(vtu_pfad: str):
    """Zellwerte der Ergebnisdatei: Koerper-Id, Volumen, Joule-Dichte, |B|.

    Ausgewertet werden die ZELLfelder (``… e``), nicht die Knotenfelder: die
    Joule-Dichte ist eine Groesse je Element, und ihr Volumenintegral ist die
    Verlustleistung. Ueber die Knoten gemittelt waere sie das nicht.
    """
    import numpy as np
    import vtk
    from vtk.util.numpy_support import vtk_to_numpy

    rd = vtk.vtkXMLUnstructuredGridReader()
    rd.SetFileName(vtu_pfad)
    rd.Update()
    grid = rd.GetOutput()
    cd = grid.GetCellData()

    def hole(name):
        a = cd.GetArray(name)
        return vtk_to_numpy(a) if a is not None else None

    gid = hole("GeometryIds")
    if gid is None:
        raise KeyError("GeometryIds fehlen in der VTU "
                       "(Save Geometry Ids = Logical True gesetzt?)")
    joule = hole("joule heating e")
    b_re, b_im = hole("magnetic flux density re e"), hole("magnetic flux density im e")

    n = grid.GetNumberOfCells()
    vol = np.zeros(n)
    for i in range(n):
        c = grid.GetCell(i)
        if c.GetNumberOfPoints() == 4:                       # Tetraeder
            p = [np.array(c.GetPoints().GetPoint(k)) for k in range(4)]
            vol[i] = abs(np.dot(p[1] - p[0], np.cross(p[2] - p[0], p[3] - p[0]))) / 6.0

    b_abs = None
    if b_re is not None and b_im is not None:
        b_abs = np.sqrt((b_re ** 2).sum(axis=1) + (b_im ** 2).sum(axis=1))
    return gid.astype(np.int64), vol, joule, b_abs


def pruefe_feld(vtu_pfad: str) -> dict:
    """Ist das gerechnete Feld ueberhaupt eines? Sonst ein klarer Fehler.

    Ein offener Strompfad gibt in 3-D keine Fehlermeldung, sondern ein
    Vektorpotential, das ins Unermessliche laeuft -- und daraus dann Momente und
    Verluste, die wie Zahlen aussehen. Diese Pruefung faengt das ab, BEVOR eine
    einzige Kennzahl gebildet wird.
    """
    import numpy as np
    gid, vol, joule, b_abs = _lies_vtu_zellen(vtu_pfad)
    if b_abs is None:
        raise RuntimeError("Die Ergebnisdatei enthaelt keine Flussdichte — "
                           "MagnetoDynamicsCalcFields hat nicht gerechnet.")
    b_max = float(np.max(b_abs))
    if b_max > B_UNMOEGLICH_T:
        raise RuntimeError(
            f"Das Feld ist keines: groesste Flussdichte {b_max:.3g} T "
            f"(moeglich waeren hoechstens {B_UNMOEGLICH_T:.0f} T). Ursache ist "
            f"der fehlende Rueckleiter fuer den Statorstrom — in 3-D muss sich "
            f"der Strom schliessen, und dieses Modell hat dafuer keinen Weg "
            f"(s. Modulkopf). Bis das gebaut ist, traegt die Stufe nur "
            f"netzkosten().")
    return {"B_max_T": round(b_max, 4), "zellen": int(len(gid))}


def verluste_je_koerper(vtu_pfad: str) -> dict:
    """Verlustleistung [W] je Koerper -- Volumenintegral der Joule-Dichte.

    Frueher wurde die Joule-Leistung aus der **Bildschirmausgabe** von Elmer
    gelesen. Sie steht dort nicht: gemessen schreibt dieser Elmer keine Zeile
    „Joule Heating" auf stdout, und die Auswertung gab darum immer 0,0 W --
    kommentarlos, und daraus dann ein Moment von 0,000 Nm. Eine angenommene
    Ausgabe ist keine Schnittstelle; die Ergebnisdatei ist eine.
    """
    import numpy as np
    gid, vol, joule, _b = _lies_vtu_zellen(vtu_pfad)
    if joule is None:
        raise KeyError("'joule heating e' fehlt in der VTU — "
                       "Calculate Joule Heating im Solver gesetzt?")
    aus = {}
    for k in np.unique(gid):
        m = gid == k
        aus[int(k)] = float(np.sum(joule[m] * vol[m]))
    return aus


def bericht(kz: dict) -> str:
    """Was der Kurzschlussring ausmacht -- die Zahl, fuer die es Stufe D gibt."""
    z = []
    z.append(f"ASM-Feld harmonisch in 3-D (Elmer), {kz['f1_Hz']:.1f} Hz, "
             f"Schlupf {100 * kz['schlupf']:.2f} %")
    z.append(f"  Netz  {kz['tets']} Tetraeder, {kz['knoten']} Knoten, "
             f"{kz['netzzeit_s']:.0f} s. Ring "
             f"{kz['ring_h_mm']:.1f} x {kz['ring_w_mm']:.1f} mm.")
    if not kz.get("gap_aufgeloest", False):
        z.append("  ACHTUNG: der Luftspalt ist in diesem Netz NICHT aufgeloest. "
                 "Das absolute Moment ist damit keine Aussage; das Verhaeltnis "
                 "der beiden Laeufe unten schon.")
    z.append(f"  Moment MIT  Kurzschlussring {kz['T_mit_Ring_Nm']:9.3f} Nm")
    z.append(f"  Moment OHNE Kurzschlussring {kz['T_ohne_Ring_Nm']:9.3f} Nm")
    z.append(f"  -> Der Ring traegt {kz['ring_anteil_pct']:+.1f} % des Moments bei.")
    z.append(f"     ema_asm setzt ihn mit {kz['zuschlag_analytisch_pct']:.0f} % "
             f"Zuschlag auf den Stabverlust an -- eine Zahl, die bis hierher "
             f"gesetzt und nie gemessen war.")
    return "\n".join(z)


